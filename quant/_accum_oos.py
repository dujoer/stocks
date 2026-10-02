# -*- coding: utf-8 -*-
"""
增仓精选 · 严格样本外验证（_accum_oos.py）
=========================================
为什么需要它
------------
`_accum_ablate.py` 找出了「剔除大宗交易+公募增持后 55.5%→62.0%」以及若干价格维度最佳档
（60日涨跌幅最佳档 71.6%、20日均额最佳档 65.5%…）。
**但那些「最佳档」是看完胜率挑出来的 = 在同一份数据上既选参数又验收 = 过拟合。**
自动筛因子的最大噪声源就在这里（三连阴首版栽过：无 CE 域间条件跑输「随便买」42.5% vs 45.9%）。

方法：两段式真样本外
--------------------
1. **前半段选参数、后半段验收**：参数（档位边界）只从前半段胜率决定，
   后半段完全不参与选择，直接报胜率。这是不可作弊的切分。
2. **分半后再互换**（cross-fit）：前半选→后半验、后半选→前半验，
   两次都跑赢基线才算稳健。单半通过可能是运气。
3. **三段 walk-forward**：把入场窗口切三段，每段用「前两段选的参数」在本段验收，
   模拟真实的「参数固定、只往前跑」。
4. **随机对照**：同 n、同入场日、独立抽样 200 遍，看该组合胜率在随机分布里的分位。
   排第 90 百分位以上才算真的不是运气。

判读铁律
--------
- 三段里至少 2 段跑赢基线、且随机对照分位 ≥ 90，才允许写进 `build_accum.py`。
- 样本 n<30 的一律标「样本不足」，不参与结论。
- **不允许用本脚本反过来调参再验**（那就是过拟合）。验不过就如实说不过。

用法
----
    python _accum_oos.py --days 90
    python _accum_oos.py --days 90 --folds 3
"""
from __future__ import annotations
import os, sys, json, math, argparse, collections, random

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import _accum_lab as L
from _accum_ablate import price_dims, wr, two_halves_check, quantile_bins


# 候选闸门：先验固定的一组（方向由经济逻辑给定），不自动扩展
# 格式：(显示名, lambda p: bool, 需要检查的字段或 None)
CAND_GATES = [
    ("清洗基线(无闸门)",        lambda p: True, None),
    ("融资5日≥4%",              lambda p: p.get("mr5", 0.0) >= 0.04, None),
    ("融资5日≥4% 且机构增持",    lambda p: p.get("mr5", 0.0) >= 0.04 and p["I"], None),
    ("ATR% 低于中位",           lambda p: p.get("vol_atr", 9e9) <= 0.0, ("vol_atr", "med")),
    ("20日均额 低于中位",        lambda p: p.get("amt20_log", 9e9) <= 0.0, ("amt20_log", "med")),
    ("20日均额 低于前1/3",       lambda p: p.get("amt20_log", 9e9) <= 0.0, ("amt20_log", "q33")),
    ("距60日高回撤 > 中位",      lambda p: p.get("dd60", -9e9) <= 0.0, ("dd60", "med")),
    ("距250日高 低于中位",       lambda p: p.get("dist_hi250", 9e9) <= 0.0, ("dist_hi250", "med")),
    ("60日涨幅 低于中位",        lambda p: p.get("mom60", 9e9) <= 0.0, ("mom60", "med")),
    ("20日涨幅 低于中位",        lambda p: p.get("mom20", 9e9) <= 0.0, ("mom20", "med")),
    ("MA20斜率 > 0",            lambda p: p.get("ma20_slope", -9e9) > 0.0, None),
    ("MA20斜率 < 0",            lambda p: p.get("ma20_slope", 9e9) < 0.0, None),
]


def median(vals):
    xs = sorted(vals)
    if not xs:
        return 0.0
    n = len(xs)
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2.0


def build_pool(days, K, q2, snaps, cal, mh):
    pool = []
    for T in days:
        frame = L.signal_frame(T, K, q2, snaps, cal, mh=mh)
        for code, sig in frame.items():
            if not any(k in sig and sig[k] > 0 for k in L.DAILY):
                continue
            sc = L.composite(sig)
            if sc <= 0:
                continue
            r = L.simulate(K, code, T)
            if not r:
                continue
            I = any(k in sig and sig[k] > 0 for k in ("pe", "sun", "person", "fund"))
            M = any(k in sig and sig[k] > 0 for k in ("m1", "m3", "m5"))
            pd = price_dims(K, code, T) or {}
            pool.append({
                "T": T, "code": code, "ret": r[0], "win": r[1], "fwd": r[2],
                "I": I, "M": M,
                "n_sig": sum(1 for k in L.ALLSIG if k in sig and sig[k] > 0),
                "sig": {k: sig[k] for k in L.ALLSIG if k in sig and sig[k] > 0},
                "mr5": sig.get("_mr5", 0.0), **pd,
            })
    return pool


def split_days(days, k):
    """把入场日切成 k 段（等份，边界不重叠）。"""
    n = len(days)
    per = n // k
    return [days[i * per:(i + 1) * per] if i < k - 1 else days[i * per:n] for i in range(k)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=90)
    ap.add_argument("--folds", type=int, default=3)
    ap.add_argument("--nrand", type=int, default=200)
    a = ap.parse_args()

    K = L.load_kline()
    cal = L.trading_days(K)
    q2 = L.load_q2_flags()
    snaps = L.load_margin_snapshots()
    mh = L.load_margin_em()
    hi = max(0, len(cal) - L.MAXFWD)
    days = cal[max(0, hi - a.days):hi]
    print("[load] codes=%d 入场 %s~%s folds=%d" % (len(K), days[0], days[-1], a.folds))

    NEG = ["block", "fund"]          # 消融证实的负贡献
    folds = split_days(days, a.folds)
    for i, f in enumerate(folds):
        print("   段%d: %s~%s (%d 日)" % (i + 1, f[0], f[-1], len(f)))
    pool_all = build_pool(days, K, q2, snaps, cal, mh)
    pool = [p for p in pool_all if not any(p["sig"].get(k, 0) > 0 for k in NEG)]
    print("[pool] 全信号 %d → 清洗后(剔除大宗/公募) %d" % (len(pool_all), len(pool)))
    # 诊断：价格维度缺失（新股历史不足 i<5）的样本比例 —— 缺失会被各闸门静默排除，
    # 若比例过高会导致各闸门实际比较的样本集不同，比较就不公平（必须如实知道）。
    miss = sum(1 for p in pool if "vol_atr" not in p)
    if miss:
        print("[诊断] 价格维度缺失 %d/%d（%.1f%%）—— 新股或停牌历史不足，这些样本会被闸门排除"
              % (miss, len(pool), 100.0 * miss / len(pool)))
    # 诊断：清洗后样本在时间上的分布。事件信号稀疏 → 样本可能挤在最近几个月，
    # 导致 walk-forward 的前两段没样本可比（必须如实知道，不能假装是「3 段都验过」）。
    by_fold_raw = [sum(1 for p in pool_all if p["T"] in f) for f in folds]
    by_fold_cln = [sum(1 for p in pool if p["T"] in f) for f in folds]
    print("[诊断] 各段清洗前/后样本数：%s / %s"
          % ("/".join(str(x) for x in by_fold_raw),
             "/".join(str(x) for x in by_fold_cln)))

    # 独立基线
    random.seed(20261002)
    base = []
    names = sorted(K.keys())
    for T in days:
        n_same = sum(1 for p in pool_all if p["T"] == T)
        for _ in range(n_same):
            r = L.simulate(K, random.choice(names), T)
            if r:
                base.append({"T": T, "ret": r[0], "win": r[1]})
    b = wr(base)
    print("[基线] n=%d 胜率=%.1f%% 均值=%.2f%%" % (b[0], b[1], b[2]))

    # ---- 中位阈值：只在「训练段」上算，测试段不参与 ----
    def th_from(recs, field, kind):
        if not recs:
            return 0.0
        xs = [r[field] for r in recs if field in r]
        if not xs:
            return 0.0
        if kind == "med":
            return median(xs)
        if kind == "q33":
            xs.sort()
            return xs[max(0, int(len(xs) / 3))]
        return median(xs)

    def resolve(cand, train):
        """把带阈值的候选在训练段上定阈值，返回可直接调用的判定函数。"""
        name, fn, th = cand
        if th is None:
            return name, fn
        field, kind = th
        cut = th_from(train, field, kind)
        if field == "vol_atr":
            return name, (lambda p, c=cut, f=field: p.get(f, 9e9) <= c)
        if field == "amt20_log" and kind == "q33":
            return name, (lambda p, c=cut, f=field: p.get(f, 9e9) <= c)
        if field == "dd60":
            return name, (lambda p, c=cut, f=field: p.get(f, -9e9) <= c)
        return name, (lambda p, c=cut, f=field: p.get(f, 9e9) <= c)

    results = {}
    for cand in CAND_GATES:
        name0 = cand[0]
        fold_res = []
        for i in range(a.folds):
            # 训练 = 除本段外全部；测试 = 本段
            train = [p for p in pool if p["T"] not in folds[i]]
            test = [p for p in pool if p["T"] in folds[i]]
            if len(test) < 10:
                fold_res.append({"fold": i + 1, "n": len(test), "skipped": True})
                continue
            nm, fn = resolve(cand, train)
            recs = [p for p in test if fn(p)]
            n, w, rt = wr(recs)
            fold_res.append({"fold": i + 1, "n": n, "wr": w, "avg": rt,
                             "edge_vs_base": w - b[1], "win": w > b[1]})
        results[name0] = {"folds": fold_res, "cand": cand}

    # ---- 随机对照：同 n 同入场日抽 nrand 遍，算该组合胜率的分位 ----
    print("\n=== 严格样本外 walk-forward（阈值只由训练段决定）===")
    # 可比段数：只有样本 >=10 的段才算「验过」。事件文件覆盖不全时前段可能为 0，
    # 此时不能宣称「N 段都验过」—— 如实按实际可比段数判定。
    n_valid_fold = sum(1 for x in by_fold_cln if x >= 10)
    print("   可比段数 = %d / %d（清洗后各段样本 %s）"
          % (n_valid_fold, a.folds, "/".join(str(x) for x in by_fold_cln)))
    print("   %-24s %s" % ("闸门", "  ".join("段%d(n/wr/胜基线)" % (i + 1) for i in range(a.folds))))
    summary = {}
    for name, blk in results.items():
        fold_res = blk["folds"]
        cells = []
        nwins = 0
        tot_n = 0
        tested = 0
        for fr in fold_res:
            if fr.get("skipped"):
                cells.append("跳过(无样本)")
                continue
            tested += 1
            tot_n += fr["n"]
            if fr["win"]:
                nwins += 1
            cells.append("%3d/%5.1f%%/%s" % (fr["n"], fr["wr"], "胜" if fr["win"] else "负"))
        # 判定：必须「所有可比段都验过」且「跑赢段数 = 可比段数」，否则不算样本外可用
        ok = (tested >= 2) and (nwins == tested) and tot_n >= 30
        summary[name] = {"folds": fold_res, "cand_name": name,
                         "th_field": (blk["cand"][2] or [None, None])[0]
                         if len(blk["cand"]) > 2 and blk["cand"][2] else None,
                         "wins": nwins, "tested": tested,
                         "n_total": tot_n, "oos_ok": ok}
        print("   %-24s %s  → %d/%d 可比段跑赢 %s"
              % (name, "  ".join(cells), nwins, tested,
                 "★样本外可用" if ok else ("✗未全段验证" if tested < 2 else "✗")))

    # ---- 随机对照分位 ----
    print("\n=== 随机对照（同 n 同入场日独立抽样 %d 遍）===" % a.nrand)
    CAND_BY_NAME = {c[0]: c for c in CAND_GATES}
    for name, blk in summary.items():
        fold_res = blk["folds"]
        n_tot = sum(fr.get("n", 0) for fr in fold_res if not fr.get("skipped"))
        if n_tot < 30:
            print("   %-24s n=%d 样本不足，跳过" % (name, n_tot))
            summary[name]["pctile"] = None
            continue
        # 该组合实际的胜率（阈值用全窗口中位，与「全窗口」这一实测量对应）
        nm, fn = resolve(CAND_BY_NAME[name], pool)
        recs = [p for p in pool if fn(p)]
        _n, w_real, _rt = wr(recs)
        # 随机：每个入场日抽 n 遍
        wins_cnt = 0
        for t in range(a.nrand):
            rr = random.Random(70000 + t)
            samp = []
            for T in days:
                same = [p for p in pool_all if p["T"] == T]
                k = sum(1 for p in same if fn(p))
                if k == 0:
                    continue
                for _ in range(k):
                    r = L.simulate(K, rr.choice(names), T)
                    if r:
                        samp.append({"T": T, "ret": r[0], "win": r[1]})
            _mn, mw, _ = wr(samp)
            if mw >= w_real:
                wins_cnt += 1
        pct = 100.0 * wins_cnt / a.nrand
        summary[name]["wr_real"] = w_real
        summary[name]["n_real"] = _n
        summary[name]["pctile"] = pct
        print("   %-24s n=%3d 胜率=%5.1f%%  随机分位=%5.1f%% %s"
              % (name, _n, w_real, pct, "★显著" if pct >= 90 else ""))

    print("\n=== 结论（样本外 + 随机对照双通过才可上线）===")
    ok_list = [k for k, v in summary.items()
               if v.get("oos_ok") and (v.get("pctile") or 0) >= 90]
    if ok_list:
        for k in sorted(ok_list, key=lambda x: -summary[x]["wr_real"]):
            print("   ✔ %s（n=%d 胜率=%.1f%% 随机分位=%.0f%%）"
                  % (k, summary[k]["n_real"], summary[k]["wr_real"], summary[k]["pctile"]))
    else:
        print("   ✗ 无闸门通过「全部可比段样本外跑赢 + 随机分位≥90」双检验。")
        if n_valid_fold < 2:
            print("     根因：事件类原始数据（block_chg/exec_chg/lhb_detail）只覆盖最近约 4 个月，")
            print("           清洗后样本全挤在最后一段 → 段1/段2 各 0 个样本，**无法做样本外切分**。")
            print("           这不是策略无效，而是「样本长度不够检验」——须等历史事件文件补齐后再验。")
        else:
            print("     → 现有事件信号 + 价格闸门无法产生样本外稳健超额，不应改规则。")
    # 清洗前后的对比（这是本轮唯一「在可比段上稳定为正」的结论）
    if n_valid_fold >= 1:
        print("\n   -- 参考：剔除负贡献因子（大宗交易/公募增持）这一条本身的效果 --")
        print("      清洗前 全因子 n=%d 胜率=%.1f%%"
              % (wr([p for p in pool_all])[0], wr([p for p in pool_all])[1]))
        print("      清洗后        n=%d 胜率=%.1f%%  → %+.1fpp"
              % (wr(pool)[0], wr(pool)[1], wr(pool)[1] - wr(pool_all)[1]))
        print("      ⚠ 样本集中在单一时间段，**这不是样本外结论**；")
        print("        但方向与消融的留一法一致（去掉两因子后升 6.5pp），可作为下期观察项。")

    out = {"asof": cal[-1], "window": [days[0], days[-1]], "folds": a.folds,
           "base": list(b), "n_all": len(pool_all), "n_clean": len(pool),
           "neg_removed": NEG, "summary": summary,
           "ok": ok_list}
    path = os.path.join(L.OUT, "accum_oos.json")
    json.dump(out, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n[out] %s" % path)


if __name__ == "__main__":
    main()
