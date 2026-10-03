# -*- coding: utf-8 -*-
"""
非价量因子「领先性」检验（_nonprice_lead.py）
==========================================
用户 2026-10-03 确认走方向 1：在资金流被证伪后，验**非价量**维度（估值/位置）是否有真增量。

★ 硬约束（本脚本能做什么、不能做什么，先说清）
------------------------------------------------
腾讯**日K 不含估值字段**（PE/PB 只在当日快照里）→ **估值无法回溯**，
  只能做当日截面，**无法做时间序列检验**。
位置类因子（距 N 日高/低、区间位置）**可以从日K 重建** → 可回溯、可检验。

所以本脚本分两段：
  【A】位置类（可回溯）→ 做完整 walk-forward + 对照组，**能出结论**
  【B】估值类（不可回溯）→ 只报当日截面分布，**明确标注不可检验**，不出结论

为什么必须这样分
----------------
上一轮资金流的教训：截面「单调」≠ 有增量（要对照涨幅才知是不是影子）。
估值若只做截面，就会重犯「看着不错其实无效」的错误。**不可回溯的维度不给结论。**

候选维度（先验固定，不扫参数）
----------------------------
位置类（全部可回溯）：
  · `pos250`  250 日区间位置（0=最低, 100=最高）      方向待定，先看分档
  · `d_hi250` 距 250 日高（负值）                    越高越接近新高
  · `d_lo250` 距 250 日低（正值）                    越低越接近底部
  · `pos120`  120 日区间位置                          中期位置
对照（判定增量用）：
  · `mom5`    T 之前 5 日涨幅（与资金流检验同款对照）
  · `mom20`   T 之前 20 日涨幅

判据
----
对每个维度：算「按该因子分 5 档 → T+1~T+5 平均收益」的**档间差**（高档−低档）。
- 与 `mom5` 对照比：**档间差超出对照 0.5pp 以上** 才算有增量。
- 样本：入场日间隔 5 日（结果窗口不重叠），每档 n≥30，入场日≥6。
- 任何一条不满足 → 判「不成立」或「不可判」，**不给出可用结论**。

用法
----
    python _nonprice_lead.py --date 2026-09-30
"""
from __future__ import annotations
import os, sys, json, argparse, collections, statistics

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import _datahub as DH

CUM_WIN = 5
N_BUCKET = 5
FWD_WIN = 5
MIN_N = 30
MIN_DAYS = 6
MIN_EDGE = 0.5      # 超出对照组的最小增量（pp）

# 位置类因子定义（先验固定）：(key, 中文名, 计算方式)
POS_DIMS = [
    ("pos250", "250日区间位置", "pos"),
    ("pos120", "120日区间位置", "pos"),
    ("d_hi250", "距250日高", "dhi"),
    ("d_lo250", "距250日低", "dlo"),
]
MOM_DIMS = [("mom5", "T前5日涨幅"), ("mom20", "T前20日涨幅")]


def load_kl():
    p = os.path.join(HERE, "_long_kline.json")
    if not os.path.exists(p):
        p = os.path.join(HERE, "_txk_cache.json")
    return json.load(open(p, encoding="utf-8"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    a = ap.parse_args()

    hub = DH.load_hub(a.date)
    kl = load_kl()
    if not hub:
        print("！底座缺失，先跑 _datahub.py")
        return
    q = ((hub["dims"].get("quotes") or {}).get("data")) or {}

    def bad(v):
        nm = (v.get("name") or "").upper()
        return ("ST" in nm) or ("退" in nm)

    dom = [c for c, v in q.items()
           if not bad(v) and (v.get("last") or 0) >= 2.0
           and (v.get("turnover_rate") or 0) > 0 and c in kl]
    # 日历
    cal = collections.Counter()
    for c in dom:
        for b in kl[c]:
            cal[b["date"]] += 1
    dates = sorted(d for d, n in cal.items() if n >= len(dom) * 0.5)
    print("[load] 分析域 %d 只 | 日历 %d 个交易日 %s ~ %s"
          % (len(dom), len(dates), dates[0], dates[-1]))
    if len(dates) < 80:
        print("日K 太短，退出")
        return

    lo, hi = 25, len(dates) - FWD_WIN
    entry = dates[lo:hi:FWD_WIN]
    print("[入场日] %d 个（间隔 %d 日）%s ~ %s" % (len(entry), FWD_WIN, entry[0], entry[-1]))
    if len(entry) < MIN_DAYS:
        print("入场日不足 %d → 不可判" % MIN_DAYS)
        return

    # 预索引：每票 date -> bar
    idx = {}
    for c in dom:
        idx[c] = {b["date"]: b for b in kl[c]}

    def at(c, T, off):
        """T 在 cal 中的下标 + off（负=过去，正=未来）。越界返回 None。"""
        try:
            i = dates.index(T)
        except ValueError:
            return None
        j = i + off
        if j < 0 or j >= len(dates):
            return None
        d = dates[j]
        return idx[c].get(d)

    def pos_factor(c, T, kind, win):
        b = at(c, T, 0)
        if not b:
            return None
        # 取 T 之前 win 日的 bar（含 T）
        try:
            i = dates.index(T)
        except ValueError:
            return None
        j0 = max(0, i - win + 1)
        seg = []
        for k in range(j0, i + 1):
            bb = idx[c].get(dates[k])
            if bb:
                seg.append(bb)
        if len(seg) < win * 0.6:
            return None
        hi_ = max(x["high"] for x in seg)
        lo_ = min(x["low"] for x in seg)
        if kind == "pos":
            if hi_ <= lo_:
                return 50.0
            return (b["last"] - lo_) / (hi_ - lo_) * 100.0
        if kind == "dhi":
            return (b["last"] / hi_ - 1.0) * 100.0 if hi_ > 0 else None
        if kind == "dlo":
            return (b["last"] / lo_ - 1.0) * 100.0 if lo_ > 0 else None
        return None

    def mom(c, T, win):
        b0 = at(c, T, -win)
        b1 = at(c, T, 0)
        if not b0 or not b1 or not b0["last"]:
            return None
        return (b1["last"] / b0["last"] - 1.0) * 100.0

    def fwd(c, T, win):
        b0 = at(c, T, 0)
        b1 = at(c, T, win)
        if not b0 or not b1 or not b0["last"]:
            return None
        return (b1["last"] / b0["last"] - 1.0) * 100.0

    def run(fn, label):
        buckets = collections.defaultdict(list)
        used = 0
        for T in entry:
            vals = []
            for c in dom:
                v = fn(c, T)
                if v is None:
                    continue
                r = fwd(c, T, FWD_WIN)
                if r is None:
                    continue
                vals.append((v, r))
            if len(vals) < N_BUCKET * MIN_N:
                continue
            used += 1
            xs = sorted(x for x, _ in vals)
            ths = [xs[int(len(xs) * i / N_BUCKET)] for i in range(1, N_BUCKET)]
            for v, r in vals:
                b = 0
                for i, t in enumerate(ths):
                    if v <= t:
                        b = i
                        break
                else:
                    b = N_BUCKET - 1
                buckets[b].append(r)
        rows = [(b, len(buckets[b]), statistics.mean(buckets[b]))
                for b in sorted(buckets)]
        if not rows:
            return rows, 0.0, None, 0
        spread = rows[-1][2] - rows[0][2]
        ws = [r[2] for r in rows if r[1] >= MIN_N]
        mono = None
        if len(ws) >= 3:
            ups = sum(1 for i in range(len(ws) - 1) if ws[i + 1] > ws[i])
            downs = sum(1 for i in range(len(ws) - 1) if ws[i + 1] < ws[i])
            mono = "升" if ups > downs else ("降" if downs > ups else "平")
        return rows, spread, mono, used

    out = {}

    # ================= A. 位置类（可回溯，完整检验）=================
    print("\n=== A. 位置类因子（可回溯 → 完整 walk-forward）===")
    print("   口径：按 T 之前该因子分 5 档，看 T+%d 日平均收益" % FWD_WIN)
    ctrl = {}
    for k, cn in MOM_DIMS:
        rows, spread, mono, used = run(
            (lambda w: (lambda c, T: mom(c, T, w)))(int(k[3:])), k)
        ctrl[k] = {"spread": spread, "rows": rows, "mono": mono, "used": used}
        print("   [对照] %-12s 档间差 = %+.2fpp  趋势=%s  入场日=%d"
              % (cn, spread, mono, used))
    base_ctrl = ctrl["mom5"]["spread"]     # 基准对照 = 5 日涨幅
    print("   → 增量判据：档间差须比对照(%s) 高 %.1fpp" % ("%.2f" % base_ctrl, MIN_EDGE))

    pos_res = {}
    for k, cn, kind in POS_DIMS:
        win = int("".join(ch for ch in k if ch.isdigit()) or 250)
        rows, spread, mono, used = run(
            (lambda kd, w: (lambda c, T: pos_factor(c, T, kd, w)))(kind, win), k)
        inc = spread - base_ctrl
        ok = (abs(spread) > MIN_EDGE) and (inc > MIN_EDGE) and used >= 2
        pos_res[k] = {"cn": cn, "spread": spread, "inc": inc, "mono": mono,
                      "used": used, "rows": rows, "ok": ok}
        print("   %-14s 档间差 = %+.2fpp  增量 = %+.2fpp  趋势=%s  入场日=%d  → %s"
              % (cn, spread, inc, mono, used,
                 "★有增量" if ok else ("无增量" if used >= 2 else "不可判")))

    # ================= B. 估值类（不可回溯，只报分布）=================
    print("\n=== B. 估值类（★不可回溯 → 只报分布，不出结论）===")
    print("   原因：腾讯日K 不含 PE/PB 字段，只有当日快照有 → 无历史序列，无法 walk-forward")
    for k in ("pe_ratio", "pb_ratio"):
        vals = [(q[c].get(k) or 0) for c in dom]
        pos = [v for v in vals if v > 0]
        if pos:
            pos.sort()
            print("   %-10s 有值 %d/%d (%.1f%%)  p10=%.2f 中位=%.2f p90=%.2f"
                  % (k, len(pos), len(dom), 100.0 * len(pos) / len(dom),
                     pos[len(pos) // 10], pos[len(pos) // 2], pos[9 * len(pos) // 10]))
    print("   → 估值维度<b>不可检验</b>，本轮<b>不给任何结论</b>。")
    print("     若要检验，需先积累每日快照（底座已在做，hub/hist/），≥40 个交易日后方可。")

    # ================= 结论 =================
    print("\n=== 结论（位置类，可回溯）===")
    good = [k for k, v in pos_res.items() if v["ok"]]
    bad = [k for k, v in pos_res.items() if not v["ok"] and v["used"] >= 2]
    und = [k for k, v in pos_res.items() if v["used"] < 2]
    print("   有增量：%s" % ("、".join(pos_res[k]["cn"] for k in good) or "无"))
    print("   无增量：%s" % ("、".join(pos_res[k]["cn"] for k in bad) or "无"))
    if und:
        print("   不可判：%s" % ("、".join(pos_res[k]["cn"] for k in und) or "无"))
    if good:
        for k in sorted(good, key=lambda x: -pos_res[x]["inc"]):
            v = pos_res[k]
            print("   → 最佳：%s（档间差 %+.2fpp，增量 %+.2fpp）"
                  % (v["cn"], v["spread"], v["inc"]))
        print("   ★ 仍需过 `_accum_oos.py` 四道闸门（移动止盈回测+随机对照）才可进规则。")
    else:
        print("   → **无位置类维度有增量**。与资金流同结论：都不值得加进因子。")
        print("     「非价量有增量」这条路在当前数据下<b>暂未找到证据</b>。")

    out = {"date": a.date, "n_domain": len(dom), "entry_days": entry,
           "cand_win": CUM_WIN, "fwd_win": FWD_WIN, "min_edge": MIN_EDGE,
           "ctrl": {k: {"spread": v["spread"], "mono": v["mono"]} for k, v in ctrl.items()},
           "pos": {k: {kk: vv for kk, vv in v.items() if kk != "rows"}
                   for k, v in pos_res.items()},
           "pos_rows": {k: [[b, n, round(m, 3)] for b, n, m in v["rows"]]
                        for k, v in pos_res.items()},
           "verdict": {"good": good, "no_inc": bad, "undetermined": und,
                       "note": "估值类不可回溯，本轮不给结论"}}
    p = os.path.join(DH.HUB, "nonprice_lead_%s.json" % DH.DS(a.date))
    json.dump(out, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n[out] %s" % p)


if __name__ == "__main__":
    main()
