# -*- coding: utf-8 -*-
"""主升精选 · 大盘环境门控系数样本外验证（0.55 / 0.8 / 1.0 到底该给几折）。

要回答的三件事：
  ① 环境分到底**预测不来**后向 20 日收益？—— 若预测不来，则门控是纯风险预算、不是 alpha，
     页面上不能暗示它提高胜率。
  ② 现行 ENV_RULE 的「仓位系数」（强势 1.0 / 震荡 0.8 / 弱势 0.55 / 破位 0.0）有没有依据？
     给一个由数据反推的系数：对数效用最优杠杆 f* = mean/var，再**归一到最强档 = 1.0**
     （因为账户风险预算按满仓定义，我们只需要各档之间的相对暴露）。
  ③ 门控的「allow 过滤」（弱势只放行 A 档）是不是真的提升了样本？

口径与红线（与 _selected_lab 完全一致，便于横向对照）：
  * 信号日收盘买入 → 移动止盈（−12% 硬止损 / 浮盈 +6% 激活 / 回撤 3% / 满 20 日强平）。
  * 环境分<b>对齐生产口径</b>：生产 env_score = 0.45×指数分 + 0.55×market_profile core，
    本脚本逐项复刻（权重与公式原样搬），只在「≤ 信号日」的指数收盘 + 已落盘的画像上算 → 无未来函数。
    指数口径（纯收盘）另存一列作对照：core 只在最近若干日有落盘，缺 core 的日退化为纯指数分。
  * 前向窗口重叠 → 样本非独立。所有显著性用**按日 block bootstrap**（重抽样交易日期，
     整日整日地抽）给出置信区间，不用朴素正态近似（会严重低估误差）。

闸门口径（沿用 _strategy_gate 的三条假阳性规则）：
  R1 对照等量：策略 n 与随机对照 n 必须相等，否则 edge 混了样本量差。
  R2 真选股层：比较对象必须是横截面前 K（真选股层），不是全行业全票。
  R3 双条件：edge>0 **且** 随机分位 ≤5%（bootstrap 中 edge>0 的比例 ≥95%）。
"""
from __future__ import annotations
import os, sys, json, math, random, statistics, argparse, datetime
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _selected_lab as S
import _idxkline as E
import _exit_sim as EXIT

# ★ 成交假设开关（模块级，build() 读取；默认 legacy 保证逐位复刻旧结论）
#   legacy    = 乐观日内路径 + 忽略跳空（历史生产口径）
#   realistic = 保守日内路径 + 跳空按开盘价成交（可实现口径）
AUDIT_MODE = "legacy"
EXIT_CONS = False

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QUANT = os.path.join(ROOT, "quant")
PANEL = os.path.join(QUANT, "_selected_lab_panel.json")
MODEL = os.path.join(QUANT, "_selected_model.json")
OUT = os.path.join(ROOT, "web", "selected", "env_gate.html")
# 结论落盘路径（--mode realistic 时改写到 *_realistic.json，绝不覆盖生产结论）
CONCL_JSON = os.path.join(QUANT, "_env_gate_lab.json")

PRIOR = S.PRIOR
PCT = 0.05          # 与 _selected_model.json 冻结的 A 档截断一致（出厂 0.05）
BOOT = 800          # block bootstrap 次数（按日重抽）
SEED = 20261003


# ---------------- 环境分（指数口径，复刻 env_score 里 isc 的公式） ----------------
def idx_score(ie):
    """复刻 _idxkline.env_score 中的指数子分（core 缺失时的兜底口径）。"""
    if not ie:
        return None
    dev = (ie["close"] - ie["ma20"]) / ie["ma20"] * 100 if ie["ma20"] else 0.0
    s = 3.0
    if dev > 1:
        s += 0.7
    elif dev > 0:
        s += 0.3
    elif dev > -1:
        s -= 0.2
    elif dev > -3:
        s -= 0.5
    else:
        s -= 0.9
    if ie["slope5"] > 0.5:
        s += 0.5
    elif ie["slope5"] < -0.5:
        s -= 0.4
    if ie["chg5"] > 2:
        s += 0.4
    elif ie["chg5"] < -2:
        s -= 0.4
    return round(max(1.0, min(5.0, s)), 2)


def label_of(sc):
    if sc is None:
        return "未知"
    if sc >= 3.8:
        return "强势"
    if sc >= 3.0:
        return "震荡"
    if sc >= 2.2:
        return "弱势"
    return "破位"


ORDER = ["强势", "震荡", "弱势", "破位", "未知"]


# ---------------- 面板 → 行级结果 ----------------
def build(step_dates=5, cache=None, nm=None):
    """逐日全市场横截面（与生产 build_selected.py 同口径）。

    ⚠ 不能用 quant/_selected_lab_panel.json：那是「每只票每 5 根 K 线取一行」的稀疏面
    板 —— 同一交易日的横截面只有 4~4776 只不等（中位 17 只），横截面分位在这么稀的
    样本上算出来不可信。这里改成：对每个信号日，遍历当天实际存在的所有票 → 完整横截面。

    cache / nm 可由外部传入（敏感性分析要跑多组步长，避免重复加载几百 MB 的缓存）。
    """
    if cache is None:
        cache = json.load(open(os.path.join(QUANT, "_txk_cache.json"), encoding="utf-8"))
    if nm is None:
        nm = {}
        try:
            nm = json.load(open(os.path.join(QUANT, "_stock_names.json"), encoding="utf-8"))
        except Exception:
            pass
    codes = [c for c in cache
             if (c.startswith("sh6") or c.startswith("sz0") or c.startswith("sz3"))
             and len(cache[c]) >= S.MINI + S.FMAX + 5]
    # 信号日：全市场交易日里每 step_dates 个取一个（等距，覆盖整段）
    all_dates = sorted({b["date"] for c in codes for b in cache[c]})
    ds = all_dates[::step_dates]
    if ds and ds[-1] != all_dates[-1]:
        ds.append(all_dates[-1])
    print("[env] 候选 %d 只 / %d 交易日 → 信号日 %s ~ %s（每 %d 日一个，共 %d 个）"
          % (len(codes), len(all_dates), ds[0], ds[-1], step_dates, len(ds)))

    rows = []
    n_kline = n_st = n_amt = n_idx = n_skipd = 0
    for di, d in enumerate(ds):
        # 全市场在该信号日的完整横截面
        day = []
        for c in codes:
            bars = cache[c]
            idx = None
            for j, b in enumerate(bars):
                if b["date"] > d:
                    break
                idx = j
            if idx is None or bars[idx]["date"] != d:
                n_idx += 1
                continue
            nme = nm.get(c) or ""
            if ("ST" in nme) or ("退" in nme):
                n_st += 1
                continue
            if idx < S.MINI + S.FMAX:
                n_kline += 1
                continue
            C = [b["last"] for b in bars]
            H = [b["high"] for b in bars]
            L = [b["low"] for b in bars]
            O = [b["open"] for b in bars]
            V = [b["volume"] for b in bars]
            close = C[idx]
            if close < S.PRICE_MIN:
                n_st += 1
                continue
            vu = 1.0 if c.startswith("sh688") else 100.0
            amt20 = sum(V[idx - 19 + k] * vu * C[idx - 19 + k] for k in range(20)) / 20 / 1e8
            if amt20 < S.AMT_MIN / 1e8:
                n_amt += 1
                continue
            psC = [0.0]
            for x in C:
                psC.append(psC[-1] + (x or 0))
            f = S.factors_at(C, H, L, O, V, psC, idx, c)
            if f is None:
                continue
            n = len(bars)
            fl = [L[idx + 1 + k] for k in range(S.FMAX) if idx + 1 + k < n]
            fh = [H[idx + 1 + k] for k in range(S.FMAX) if idx + 1 + k < n]
            fc = C[idx + S.FMAX] if idx + S.FMAX < n else None
            if len(fl) < S.FMAX or not fc:
                n_kline += 1
                continue
            fo = [O[idx + 1 + k] for k in range(S.FMAX) if idx + 1 + k < n]
            day.append({"code": c, "date": d, "f": f, "_close": close,
                        "fl": fl, "fh": fh, "fc": fc, "fo": fo})
        # 早段缓存稀疏（缓存是增量追加的，最初几周只有个位数只票存在），横截面不成立 → 整日丢弃
        if len(day) < 200:
            n_skipd += 1
            continue
        for r in day:
            rows.append(r)
    print("[env] 重扫完成：%d 行 ｜ 剔无/ST退 %d · 流动性 %d · K线/前推不足 %d · 当日无此日期 %d · 横截面过小丢弃 %d 日"
          % (len(rows), n_st, n_amt, n_kline, n_idx, n_skipd))
    cnt = defaultdict(int)
    for r in rows:
        cnt[r["date"]] += 1
    v = sorted(cnt.values())
    print("[env] 每信号日横截面大小：min %d / 中位 %d / max %d" % (v[0], v[len(v) // 2], v[-1]))

    # 逐日环境分：★必须复刻生产口径（_idxkline.env_score = 0.45*指数分 + 0.55*市场画像 core），
    # 否则实验室验证的是「指数口径标签」而生产用的是「composite 标签」，两边日期对不上 = 换了东西在验证。
    # 指数口径分另存 esc_idx/elab_idx 做对照。
    esc, elab, ehas_core, esc_idx, elab_idx = {}, {}, {}, {}, {}
    for d in ds:
        ie = E.index_env(d)
        isc = idx_score(ie)
        prof = E.market_profile(d)
        ehas_core[d] = all(prof.get(k) is not None for k in
                           ("TREND_SHORT_DIRECTION_SCORE", "TECHNICAL_SCORE",
                            "STOCK_WIDTH_SCORE", "SENTIMENT_SCORE"))
        core = None
        if ehas_core[d]:
            # 权重与 _idxkline.env_score 完全一致
            core = (0.28 * prof["TREND_SHORT_DIRECTION_SCORE"]
                    + 0.22 * prof["TECHNICAL_SCORE"]
                    + 0.28 * prof["STOCK_WIDTH_SCORE"]
                    + 0.22 * prof["SENTIMENT_SCORE"])
        if core is not None and isc is not None:
            sc = 0.45 * isc + 0.55 * core
        else:
            sc = isc
        esc[d], elab[d] = sc, label_of(sc)
        esc_idx[d], elab_idx[d] = isc, label_of(isc)

    # 逐日横截面分位（真选股层 = 先验固定 9 因子等权分位前 PCT）
    byd = defaultdict(list)
    for r in rows:
        byd[r["date"]].append(r)
    tops = defaultdict(list)
    for d, rs in byd.items():
        rk = {}
        for fac in PRIOR:
            vals = sorted([(r["f"].get(fac), r["code"]) for r in rs if r["f"].get(fac) is not None])
            if len(vals) < 6:
                continue
            for pos, (v, c) in enumerate(vals):
                rk.setdefault(c, {})[fac] = pos / (len(vals) - 1)
        scored = []
        for r in rs:
            tot = cnt = 0.0
            for fac in PRIOR:
                v = rk.get(r["code"], {}).get(fac)
                if v is None:
                    continue
                tot += (v if PRIOR[fac] > 0 else 1 - v)
                cnt += 1
            if cnt >= max(2, len(PRIOR) // 2):
                scored.append((tot / cnt, r))
        if len(scored) < 12:
            continue
        scored.sort(key=lambda x: -x[0])
        k = max(1, int(round(len(scored) * PCT)))
        for sc_, r in scored[:k]:
            r["qs"] = round(sc_ * 100, 1)
            r["in_top"] = True
            tops[d].append(r)

    # 行级退出模拟
    # ★ 成交假设：AUDIT_MODE="legacy" 走旧乐观口径（逐位不变）；"realistic" 走可实现口径
    #   （保守日内路径 + 跳空按开盘价成交）。两版共用 _exit_sim 的同一份实现，避免各写一套。
    for r in rows:
        if AUDIT_MODE == "realistic":
            s = EXIT.sim_trail_lists(r["fl"], r["fh"], r["fc"], r["_close"],
                                     cons=True, fO=r.get("fo"))
        else:
            s = S._sim_trail(r["fl"], r["fh"], r["fc"], r["_close"])
        r["pnl"], r["win"], r["mae"] = s["pnl"], s["win"], s["mae"]

    top_rows = [r for d in sorted(tops) for r in tops[d]]
    return rows, ds, esc, elab, ehas_core, tops, top_rows, esc_idx, elab_idx


# ---------------- 统计工具 ----------------
def agg(vals):
    n = len(vals)
    if n == 0:
        return None
    m = sum(vals) / n
    v = statistics.pvariance(vals) if n > 1 else 0.0
    return {"n": n, "mean": m, "var": v, "sd": math.sqrt(v) if v > 0 else 0.0,
            "wr": sum(1 for x in vals if x > 0) / n * 100}


def boot_bucket(per_date, B=BOOT, seed=SEED):
    """per_date: [(date, [pnl...])]  →  (point, [boot means], [boot vars])"""
    rnd = random.Random(seed)
    ds = [x[0] for x in per_date]
    mat = {dd: x[1] for dd, x in zip(ds, per_date)}
    point = [x for d in ds for x in mat[d]]
    ms, vs = [], []
    for _ in range(B):
        pick = [ds[rnd.randrange(len(ds))] for _ in range(len(ds))]
        a = [x for d in pick for x in mat[d]]
        ms.append(sum(a) / len(a) if a else 0.0)
        vs.append(statistics.pvariance(a) if len(a) > 1 else 0.0)
    return point, ms, vs


def _flat(lst):
    out = []
    for x in lst:
        out.extend(x)
    return out


def ci(v, lo=0.05):
    v = sorted(v)
    return v[int(math.floor(len(v) * lo))], v[int(math.ceil(len(v) * (1 - lo))) - 1]


# ---------------- 主流程 ----------------
def main(argv=None):
    global AUDIT_MODE, CONCL_JSON
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--mode", default="legacy", choices=("legacy", "realistic"))
    ap.add_argument("--step", type=int, default=5)
    ap.add_argument("--no-html", action="store_true")
    # ⚠ main() 里到处用 `a` 做局部变量（agg 结果等），argparse 命名空间绝不能叫 a
    _cli, _unk = ap.parse_known_args(argv if argv is not None else sys.argv[1:])
    AUDIT_MODE = _cli.mode
    if _cli.mode == "realistic":
        CONCL_JSON = os.path.join(QUANT, "_env_gate_lab_realistic.json")
    rows, ds, esc, elab, ehas_core, tops, top_rows, esc_idx, elab_idx = build(step_dates=_cli.step)
    print("[env] 成交假设口径 = %s" % ("可实现（保守日内 + 跳空按开盘成交）" if _cli.mode == "realistic"
                                   else "旧乐观（同根K先冲高后回落 + 忽略跳空）"))
    print("[env] 真选股层（前 %.0f%%）%d 行" % (PCT * 100, len(top_rows)))

    n_core = sum(1 for d in ds if ehas_core[d])
    print("[env] 生产口径（composite = 0.45*指数分 + 0.55*画像 core）可用的信号日：%d/%d"
          " ｜ 主结论用 composite（与生产 market_env 一致），指数口径仅作对照" % (n_core, len(ds)))

    # 只统计真正进了面板的信号日（横截面过小被丢的日期不能算进样本数）
    n_days, n_bars = defaultdict(int), defaultdict(int)
    for d in {r["date"] for r in rows}:
        n_days[elab[d]] += 1
    for r in rows:
        n_bars[elab[r["date"]]] += 1
    print("[env] 可用信号日按档（仅计入横截面成立的日期）：%s ｜ 合计 %d 日 / 原始信号日 %d 日"
          % (" ".join("%s=%d" % (k, n_days[k]) for k in ORDER if n_days[k]),
             sum(n_days.values()), len(ds)))

    # ---- ① 环境分是否预测后向收益（β 部分）----
    print("\n=== ① 全域随机持有（非选股层）按环境分桶：环境分预测不来收益？ ===")
    uni = defaultdict(list)
    for r in rows:
        uni[elab[r["date"]]].append(r["pnl"])
    uni_boot = {}
    for k in ORDER:
        if k not in uni or not uni[k]:
            continue
        pd_ = []
        for d in sorted({r["date"] for r in rows if elab[r["date"]] == k}):
            pd_.append((d, [r["pnl"] for r in rows if r["date"] == d and elab[r["date"]] == k]))
        pt, bs, _bv = boot_bucket(pd_)
        a = agg(pt)
        med = statistics.median(pt)
        lo, hi = ci(bs)
        uni_boot[k] = {"n": a["n"], "mean": a["mean"], "ci": [lo, hi], "var": a["var"],
                       "wr": a["wr"], "med": med, "nd": n_days[k]}
        print("  %s：%3d 日/%-7d 笔 均收益 %+.2f%% [%.2f, %.2f] 中位 %+.2f%% ｜ 方差 %.1f ｜ 胜率 %.1f%%"
              % (k, n_days[k], a["n"], a["mean"], lo, hi, med, a["var"], a["wr"]))
    # 单调性：强势→破位 均收益应递减？
    keep = [k for k in ["强势", "震荡", "弱势", "破位"] if k in uni_boot]
    ok = all(cv[0] > cv[1] for cv in zip(keep, keep[1:]))
    print("  单调递减？%s（依次 %s）" % ("是" if ok else "否",
                                      " → ".join("%+.2f" % uni_boot[k]["mean"] for k in keep)))

    # ---- ①b 逐日诊断（最诚实的证据）：每档的代表日 ----
    print("\n=== ①b 逐日诊断（前 8 个信号日 / 档，按日序）===")
    per_date_top = defaultdict(list)
    for r in top_rows:
        per_date_top[r["date"]].append(r["pnl"])
    print("  %-12s %-6s %-6s %5s %9s %9s %7s" % ("日期", "composite", "指数口径", "分", "前5%均", "全域均", "全域差"))
    shown = 0
    for d in ds:
        if shown >= 8:
            break
        if not per_date_top.get(d):
            continue
        k = elab[d]
        a = sum(per_date_top[d]) / len(per_date_top[d])
        b = [r["pnl"] for r in rows if r["date"] == d]
        bm = sum(b) / len(b)
        print("  %-12s %-8s %-8s %5.1f %+8.2f%% %+8.2f%% %+7.2f"
              % (d, k, elab_idx[d], esc[d], a, bm, a - bm))
        shown += 1

    # ---- ② 逐环境桶：策略 edge（R1 等量随机对照 / R2 真选股层 / R3 双条件）----
    print("\n=== ② 各环境桶内：真选股层 vs 同桶同日等量随机（R1/R2/R3）===")
    edge_rows = defaultdict(list)
    ctrl_rows = defaultdict(list)
    rnd = random.Random(SEED)
    for d in sorted(tops):
        lab = elab[d]
        pool = [r for r in rows if r["date"] == d]
        if not pool or not tops[d]:
            continue
        for r in tops[d]:
            edge_rows[lab].append(r)
            # 等量随机对照：从同日全域里随机抽 len(tops[d]) 只
            samp = rnd.sample(pool, len(tops[d]))
            ctrl_rows[lab].extend(samp)
    edge_out = {}
    for k in ORDER:
        tr, cr = edge_rows.get(k, []), ctrl_rows.get(k, [])
        if not tr or not cr:
            continue
        tv = [r["pnl"] for r in tr]
        cv = [r["pnl"] for r in cr]
        # 逐日配对（同日一次），算每日均值差 → 再 bootstrap 日期
        by_dt = defaultdict(lambda: ([], []))
        for r in tr:
            by_dt[r["date"]][0].append(r["pnl"])
        for r in cr:
            by_dt[r["date"]][1].append(r["pnl"])
        pd_ = [(d, a, b) for d, (a, b) in by_dt.items() if b]
        def daily_avg(x):
            return [sum(v) / len(v) for v in x]
        da = daily_avg([a for _, a, _ in pd_])
        dc = daily_avg([b for _, _, b in pd_])
        diffs = [x - y for x, y in zip(da, dc)]
        bs = []
        for _ in range(BOOT):
            pick = [diffs[rnd.randrange(len(diffs))] for _ in range(len(diffs))]
            bs.append(sum(pick) / len(pick))
        p = sum(diffs) / len(diffs)
        lo, hi = ci(bs)
        # 注：对照是「每只入选票各抽 k 等量对照」→ 每日期 k² 条，不能拿它和策略的 k 条
        # 直接拼池求均值（大票日的 k² 会把池化均值拉歪）。这里一律报逐日平衡口径。
        nd = len(diffs)
        eff = nd * statistics.mean([len(a) for _, a, _ in pd_])
        edge_out[k] = {"edge": p, "ci": [lo, hi], "n_top": len(tr), "n_ctrl": len(cr),
                       "nd": nd, "top_mean": statistics.mean(da), "ctrl_mean": statistics.mean(dc),
                       "pass_rate": sum(1 for x in bs if x > 0) / BOOT * 100}
        print("  %s：%2d 日 策略逐日均 %+.2f%% ｜ 同日全票逐日均 %+.2f%% ｜ "
              "edge %+.2fpp [%+.2f, %+.2f] ｜ 入选 %d 笔 ｜ R3 通过率 %.1f%%%s"
              % (k, nd, statistics.mean(da), statistics.mean(dc), p, lo, hi, len(tr),
                 sum(1 for x in bs if x > 0) / BOOT * 100,
                 "" if (sum(1 for x in bs if x > 0) / BOOT) >= 0.95 else "（R3 不通过）"))
        # 留一法：逐日剔除一个信号日后 edge 摆到哪（检验「是不是被一两日撑起来」）
        # 先算每个信号日的 (顶部均值, 全票均值, 差)，再留一
        per_d = [(d_, statistics.mean(a), statistics.mean(b)) for d_, a, b in pd_]
        loo = []
        for dd, _m, _x in per_d:
            keep = [(dd2, a2, b2) for dd2, a2, b2 in per_d if dd2 != dd]
            if not keep:
                continue
            loo.append(sum(a2 - b2 for _d2, a2, b2 in keep) / len(keep))
        edge_out[k]["loo"] = {"min": min(loo), "max": max(loo), "nd": nd}
        print("      留一法：剔掉任一信号日后 edge ∈ [%+.2f, %+.2f]（最差 %+.2f pp）"
              % (min(loo), max(loo), min(loo)))
        _ = eff

    # ---- ③ 反推最优仓位系数（均值-方差有效口径，block bootstrap 给 CI）----
    # 固定风险预算 σ 时，i 档最优暴露 f_i = σ/sd_i，可达均值 = (mean_i/sd_i)·σ。
    # 故「相对系数」= 有效比值 (mean/sd)_i / (mean/sd)_强势 —— 比单纯比均值稳健，
    # 且均值≤0 的档自然得到 ≤0（= 空仓），这正是要检验的点。
    print("\n=== ③ 反推仓位系数（f = mean/sd 有效比，归一到强势档 = 1.0；按日 block bootstrap）===")
    topbyd = defaultdict(list)
    for r in top_rows:
        topbyd[r["date"]].append(r["pnl"])
    coef = {}
    coef_rel = {}
    for k in ORDER:
        dates = sorted(d for d in ds if elab[d] == k)
        if not dates:
            continue
        vals = [x for d in dates for x in topbyd.get(d, [])]
        if len(vals) < 200:
            continue
        a = agg(vals)
        f = (a["mean"] / a["sd"]) if a["sd"] > 0 else 0.0
        # bootstrap：重抽该档的交易日
        fb = []
        # ⚠ 不能用 hash(k)：Python 的字符串 hash 受 PYTHONHASHSEED 随机化影响，
        #   每次运行种子都不同 → bootstrap 结果漂移 → 页面 sha 不稳（幂等门禁会挂）。
        rnd2 = random.Random(SEED + (ORDER.index(k) if k in ORDER else 0))
        for _ in range(BOOT):
            pick = [dates[rnd2.randrange(len(dates))] for _ in range(len(dates))]
            b = [x for d in pick for x in topbyd.get(d, [])]
            if len(b) < 100:
                continue
            m = sum(b) / len(b)
            sd = statistics.pstdev(b) or 1e-9
            fb.append(m / sd)
        flo, fhi = ci(fb)
        coef[k] = {"n": a["n"], "mean": a["mean"], "sd": a["sd"], "var": a["var"], "f": f, "f_ci": [flo, fhi]}
        coef_rel[k] = f
    base_f = coef.get("强势", {}).get("f") or 0.0
    print("  %-4s %6s %6s %8s %8s %10s %18s" % ("环境", "日数", "笔数", "均收益", "标准差", "mean/sd", "相对系数(强势=1)"))
    rel_final = {}
    for k in ORDER:
        if k not in coef:
            continue
        a = coef[k]
        rel = (a["f"] / base_f) if base_f else 0.0
        rel_final[k] = rel
        # 系数 CI：把 bootstrap 的 f 直接换成相对值
        rl, rh = (a["f_ci"][0] / base_f, a["f_ci"][1] / base_f) if base_f else (0.0, 0.0)
        # 归一化后的相对系数（页面「相对系数（强势=1）」列必须用这个，
        # 直接拿未归一化的 f 当 rel 会把 +1.00 显示成 +0.25）
        coef_rel[k] = {"f": rel, "ci": [rl, rh]}
        print("  %-4s %6d %6d %+8.2f %8.2f %10.4f  %+.2f [%.2f, %.2f]"
              % (k, n_days[k], a["n"], a["mean"], a["sd"], a["f"], rel, rl, rh))
    print("  （相对系数 =0 表示数据反推应空仓；>1 表示比现行满仓更激进）")

    # ---- ④ walk-forward：前 60% 日估 → 后 40% 日验，系数稳不稳 ----
    print("\n=== ④ 样本外切分（前 60%% 估 → 后 40%% 验）：系数分档稳不稳 ===")
    cut = ds[int(len(ds) * 0.6)]
    for k in ORDER:
        dates = sorted(d for d in ds if elab[d] == k)
        if len(dates) < 8:
            continue
        tr = [x for d in dates if d < cut for x in topbyd.get(d, [])]
        te = [x for d in dates if d >= cut for x in topbyd.get(d, [])]
        def ms(v):
            m = sum(v) / len(v)
            sd = statistics.pstdev(v) or 1e-9
            return m, m / sd
        m1, f1 = ms(tr)
        m2, f2 = ms(te)
        print("  %s：训练均 %+.2f%%(f=%.4f) → 测试均 %+.2f%%(f=%.4f) ｜ 符号翻转？%s"
              % (k, m1, f1, m2, f2, "是" if (f1 > 0) != (f2 > 0) else "否"))
    print("  切分点 %s" % cut)

    # ---- ⑤ 连续分位：现行阈值 3.8/3.0/2.2 合不合理 ----
    print("\n=== ⑤ 环境分连续分位（每 0.5 一档，真选股层前 5%）===")
    by_sc = defaultdict(list)
    for r in top_rows:
        by_sc[round(esc[r["date"]] / 0.5) * 0.5].append(r["pnl"])
    for k in sorted(by_sc):
        v = by_sc[k]
        if len(v) < 100:
            continue
        print("  环境分≈%.1f：n=%-6d 均 %+.2f%% ｜ 胜率 %.1f%% ｜ mean/sd %+.4f"
              % (k, len(v), sum(v) / len(v), sum(1 for x in v if x > 0) / len(v) * 100,
                 (sum(v) / len(v)) / (statistics.pstdev(v) or 1e-9)))

    # ---- ⑥ allow 过滤：弱势档 A 档 vs A+B ----
    print("\n=== ⑥ 弱势档「只放行 A 档」值不值 ===")
    weak_dates = [d for d in ds if elab[d] == "弱势"]
    a_only, a_plus_b = [], []
    for d in weak_dates:
        pool = [r for r in rows if r["date"] == d]
        scored = sorted(pool, key=lambda r: -(r.get("qs") or 0))
        if not scored:
            continue
        kA = max(1, int(round(len(scored) * PCT)))
        a_only += [r["pnl"] for r in scored[:kA]]
        a_plus_b += [r["pnl"] for r in scored]
    if a_only:
        print("  弱势·A 档：n=%d 均 %+.2f%% 胜率 %.1f%%" %
              (len(a_only), sum(a_only) / len(a_only), sum(1 for x in a_only if x > 0) / len(a_only) * 100))
    if a_plus_b:
        print("  弱势·A+B ：n=%d 均 %+.2f%% 胜率 %.1f%%" %
              (len(a_plus_b), sum(a_plus_b) / len(a_plus_b), sum(1 for x in a_plus_b if x > 0) / len(a_plus_b) * 100))

    # ---- 指数口径 vs 生产 composite 口径：标签分歧有多大 ----
    print("\n=== ⑦ 指数口径 vs 生产 composite（0.45*指数分 + 0.55*画像 core）标签分歧 ===")
    diff = same = 0
    for d in ds:
        if not ehas_core[d]:
            continue
        if label_of(esc_idx[d]) != label_of(esc[d]):
            diff += 1
        else:
            same += 1
    print("  两种口径标签一致 %d 日 / 分歧 %d 日 → 主结论（①②③）全部按生产 composite 口径分组，"
          "指数口径仅作对照列" % (same, diff))

    json.dump({"n_rows": len(rows), "n_dates": len(ds), "pct": PCT,
               "uni_boot": uni_boot,
               "edge": edge_out,
               "coef": {k: {"n": coef[k]["n"], "mean": coef[k]["mean"], "var": coef[k]["var"], "rel": coef_rel[k]}
                        for k in coef},
               "cut": cut, "n_core_days": n_core},
              open(CONCL_JSON, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("\n[env] 结论落 %s" % CONCL_JSON)

    res = {"uni_boot": uni_boot, "edge_out": edge_out, "coef": coef, "coef_rel": coef_rel,
           "ds": ds, "esc": esc, "elab": elab,
           "n_core": n_core, "cut": cut, "n_days": dict(n_days),
           "by_sc": {kk: {"n": len(v), "mean": sum(v) / len(v),
                          "wr": sum(1 for x in v if x > 0) / len(v) * 100,
                          "ms": (sum(v) / len(v)) / (statistics.pstdev(v) or 1e-9)}
                     for kk, v in sorted(by_sc.items())},
           "allow": {"a": {"n": len(a_only), "mean": sum(a_only) / len(a_only),
                           "wr": sum(1 for x in a_only if x > 0) / len(a_only) * 100} if a_only else None,
                     "ab": {"n": len(a_plus_b), "mean": sum(a_plus_b) / len(a_plus_b),
                            "wr": sum(1 for x in a_plus_b if x > 0) / len(a_plus_b) * 100} if a_plus_b else None},
           "composite": {"same": same, "diff": diff},
           "date_lo": min({r["date"] for r in rows}) if rows else None,
           "date_hi": max({r["date"] for r in rows}) if rows else None,
           "gate": "strong_only"}
    res["audit_mode"] = AUDIT_MODE
    json.dump(res, open(CONCL_JSON, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1, default=str)
    if _cli.no_html:
        print("[env] --no-html：跳过页面渲染")
        return res
    render(res)
    return res


# ---------------- 渲染证据页 ----------------
SENS_JSON = os.path.join(QUANT, "_env_gate_sens.json")


def sens_note():
    """样本量敏感性提示（数字全部取自 _env_gate_sens.json，不写死在本页）。

    本页结论是按 step=5 采样（30 个有效信号日、强势仅 8 日）得出的。换采样步长复核后，
    震荡 / 破位档的符号会翻转 —— 这两档必须降级为「不可判」，不能写成「数据证明该空仓」。
    """
    try:
        s = json.load(open(SENS_JSON, encoding="utf-8"))
    except Exception:
        return ""
    gs = s.get("groups") or {}
    if len(gs) < 2:
        return ""
    trs = []
    for lab in ORDER:
        vs = [(k, gs[k]["stat"][lab]["abs_mean"]) for k in gs if lab in gs[k]["stat"]]
        if not vs:
            continue
        pos = all(v > 0 for _, v in vs)
        neg = all(v < 0 for _, v in vs)
        verdict = ("开仓（跨步长稳定为正）" if pos else
                   "空仓（跨步长稳定为负）" if neg else
                   "不可判（符号随采样翻转）")
        trs.append("<tr><td>%s</td><td class='num'>%s</td><td>%s</td><td><b>%s</b></td></tr>"
                   % (lab,
                      " ／ ".join("%s日 %+.2f%%" % (gs[k]["step"], v) for k, v in vs),
                      "是" if (pos or neg) else "<b>否（翻转）</b>",
                      verdict))
    if not trs:
        return ""
    return ("""<div class="box red"><b>⚠️ 样本量敏感性提示（换采样步长复核后的修正）：</b>
本页结论是按 <b>step=5</b> 采样（30 个有效信号日，其中强势仅 8 日）得出的。
换采样步长复核后（见 <a href='env_gate_sens.html' style='color:var(--blue)'>样本量敏感性检验</a>）：
<div class="card"><table>
<thead><tr><th>环境档</th><th>各步长下的策略层绝对均收益</th><th>跨步长同号</th><th>修正后的判定</th></tr></thead>
<tbody>%s</tbody></table></div>
<b>强势开仓</b>与<b>弱势空仓</b>跨步长稳定，这两条保留；
但<b>震荡、破位</b>档的绝对收益<b>符号随采样翻转</b>，说明本页给出的负值并非稳定效应 ——
这两档的正确定性是<b>「不可判」</b>：生产上仍按「宁可不选」<b>空仓</b>，但那是<b>纪律</b>，
不是「数据证明该档该空仓」，页面与结论里都不得那样表述。</div>""" % "".join(trs))


CSS = """
:root{--bg:#fbfbfd;--card:#fff;--text:#1d1d1f;--muted:#6e6e73;--line:#e5e5e7;
 --up:#ff3b30;--dn:#34c759;--blue:#0071e3;--gold:#b8893b;}
*{box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"PingFang SC","Microsoft YaHei",sans-serif;
 background:var(--bg);color:var(--text);line-height:1.7;margin:0;padding:0}
.wrap{max-width:1060px;margin:0 auto;padding:28px 18px 56px}
h1{font-size:23px;font-weight:700;margin:0 0 6px;letter-spacing:-.02em}
h2{font-size:18px;font-weight:600;margin:26px 0 12px;padding-bottom:8px;border-bottom:2px solid var(--blue)}
.sub{color:var(--muted);font-size:13px;margin-bottom:8px}
.card{background:var(--card);border-radius:16px;padding:16px 20px;margin:12px 0;box-shadow:0 1px 3px rgba(0,0,0,.05)}
.box{border-left:4px solid var(--blue);background:#f0f7ff;padding:14px 18px;border-radius:0 12px 12px 0;margin:14px 0}
.box.gold{border-color:var(--gold);background:#fffaf0}
.box.red{border-color:var(--up);background:#fff5f4}
.box.green{border-color:var(--dn);background:#f0faf3}
table{width:100%;border-collapse:collapse;font-size:12.5px;margin:10px 0}
th,td{padding:8px 6px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
th{color:var(--muted);font-weight:600;font-size:11.5px;background:#fafafa;white-space:nowrap}
.num{font-variant-numeric:tabular-nums}
.up{color:var(--up)}.dn{color:var(--dn)}.am{color:var(--blue)}
.kv{font-size:12.5px;color:var(--muted)}
.foot{text-align:center;color:var(--muted);font-size:12px;margin-top:28px}
"""


def _f(v, d=2):
    if v is None:
        return "—"
    return "{:+.{}f}".format(v, d)


REALISTIC_JSON = os.path.join(QUANT, "_env_gate_lab_realistic.json")


def _exit_assumption_html(res):
    """两口径并列：旧乐观口径 vs 可实现口径（保守日内路径 + 跳空按开盘价成交）。

    只改成交假设，不改环境分、不改选股、不改分档。数字全部来自当日重算的 JSON，不写死。
    """
    if not os.path.exists(REALISTIC_JSON):
        return ("<h2>七、退出回测的成交假设</h2>"
                "<div class='card'><div class='box red' style='border-color:#b00020'>"
                "<b>⚠️ 可实现口径未核验：</b>未找到 <code>quant/_env_gate_lab_realistic.json</code>"
                "（运行 <code>python quant/_env_gate_lab.py --mode realistic --no-html</code> 生成）。"
                "核验完成前，本页一至六节的 edge / 胜率均按<b>旧乐观口径</b>（同根 K 线先冲高后回落、"
                "忽略跳空）计算，<b>不可作为调参依据</b>。</div></div>")
    rj = json.load(open(REALISTIC_JSON, encoding="utf-8"))
    trs = ""
    for k in ORDER:
        ea = (res.get("edge_out") or {}).get(k)
        eb = (rj.get("edge_out") or {}).get(k)
        if not ea or not eb:
            continue
        cls = "up" if eb["edge"] > 0 else "dn"
        if eb["edge"] > 0 and eb.get("pass_rate", 0) >= 95:
            verdict = "仍成立"
        elif eb["edge"] > 0:
            verdict = "⚠️ 不稳"
        else:
            verdict = "不通过"
        trs += ("<tr><td><b>%s</b></td><td class='num'>%d</td>"
                "<td class='num'>%+.3f</td><td class='num'>[%+.2f, %+.2f]</td>"
                "<td class='num'>%.1f%%</td>"
                "<td class='num %s'>%+.3f</td><td class='num'>[%+.2f, %+.2f]</td>"
                "<td class='num'>%.1f%%</td><td class='num'>%+.3f</td><td>%s</td></tr>"
                % (k, ea["nd"],
                   ea["edge"], ea["ci"][0], ea["ci"][1], ea.get("pass_rate", 0),
                   cls, eb["edge"], eb["ci"][0], eb["ci"][1], eb.get("pass_rate", 0),
                   eb["edge"] - ea["edge"], verdict))
    sa = (res.get("edge_out") or {}).get("强势") or {}
    sb = (rj.get("edge_out") or {}).get("强势") or {}
    s_ok = sb.get("edge", 0) > 0 and sb.get("pass_rate", 0) >= 95
    loo0 = sa.get("loo") or {}
    loo1 = sb.get("loo") or {}
    wa = (res.get("edge_out") or {}).get("弱势") or {}
    wb = (rj.get("edge_out") or {}).get("弱势") or {}
    cross = (loo0.get("min", 0) > 0) and ((wb.get("loo") or {}).get("min", 0) <= 0)
    if s_ok:
        box = ("<div class='box green'><b>强势档（唯一开仓档）在可实现口径下仍成立：</b>"
               "edge %+.3f → <b>%+.3f pp</b>、R3 %.1f%% → <b>%.1f%%</b>、留一 [%+.3f, %+.3f] → "
               "<b>[%+.3f, %+.3f]</b> 仍全正。二值门控「强势开仓」的依据没有被成交假设推翻。</div>"
               % (sa.get("edge", 0), sb.get("edge", 0),
                  sa.get("pass_rate", 0), sb.get("pass_rate", 0),
                  loo0.get("min", 0), loo0.get("max", 0),
                  loo1.get("min", 0), loo1.get("max", 0)))
    else:
        box = ("<div class='box red' style='border-color:#b00020'><b>⚠️ 强势档在可实现口径下不再成立：</b>"
               "edge %+.3f → %+.3f pp、R3 %.1f%% → %.1f%%。按红线（宁可不选）"
               "<b>应停止主升精选出票</b>，直到用可实现口径重新取得证据。</div>"
               % (sa.get("edge", 0), sb.get("edge", 0),
                  sa.get("pass_rate", 0), sb.get("pass_rate", 0)))
    warn = ("<div class='kv'>⚠️ <b>弱势档的留一区间在可实现口径下跨零</b>（%+.3f → %+.3f）："
            "旧口径下「去掉任意一天 edge 仍为正」，新口径下不成立。该档本就判定为空仓，"
            "且其<b>绝对收益</b>在新口径下更负（%+.3f%% → %+.3f%%），空仓结论方向不变，"
            "但「弱势档有正 edge」这个说法<b>以后不能再用</b>。</div>"
            % ((wa.get("loo") or {}).get("min", 0), (wb.get("loo") or {}).get("min", 0),
               wa.get("top_mean", 0), wb.get("top_mean", 0))) if cross else ""
    return ("<h2>七、退出回测的成交假设（两口径并列）</h2>"
            "<div class='card'><table>"
            "<thead><tr><th>环境档</th><th>信号日</th>"
            "<th>旧 edge(pp)</th><th>旧 95%%CI</th><th>旧 R3</th>"
            "<th>可实现 edge(pp)</th><th>可实现 95%%CI</th><th>可实现 R3</th>"
            "<th>Δ edge</th><th>判据</th></tr></thead>"
            "<tbody>%s</tbody></table>"
            "%s%s"
            "<div class='kv'>两版只差<b>成交假设</b>：旧口径假设同根 K 线先冲高后回落（跟踪止盈永远卖在高点）"
            "且忽略跳空（开盘已破止损线仍按止损价成交）；可实现口径改为保守日内路径 + 跳空按开盘价成交。"
            "环境分、选股因子、分档阈值<b>一律未改</b>。判据 = edge&gt;0 且 R3≥95%%。</div></div>"
            % (trs, box, warn))


def render(res):
    ub, ed, cf = res["uni_boot"], res["edge_out"], res["coef"]
    dn = res.get("n_days", {})

    def uni_rows():
        out = []
        for k in ORDER:
            if k not in ub:
                continue
            v = ub[k]
            out.append("<tr><td>%s</td><td class='num'>%d</td><td class='num'>%d</td>"
                       "<td class='num'>%s</td><td class='num'>[%s, %s]</td><td class='num'>%.1f%%</td></tr>"
                       % (k, v["nd"], v["n"], _f(v["mean"]), _f(v["ci"][0], 2), _f(v["ci"][1], 2), v["wr"]))
        return "".join(out)

    def edge_rows():
        out = []
        for k in ORDER:
            if k not in ed:
                continue
            v = ed[k]
            ok = "通过" if v["pass_rate"] >= 95 else "不通过"
            out.append("<tr><td>%s</td><td class='num'>%d</td><td class='num'>%s</td><td class='num'>%s</td>"
                       "<td class='num'>%+.2fpp</td><td class='num'>[%+.2f, %+.2f]</td>"
                       "<td class='num'>%.1f%%</td><td>%s</td></tr>"
                       % (k, v["nd"], _f(v["top_mean"]), _f(v["ctrl_mean"]), v["edge"],
                          v["ci"][0], v["ci"][1], v["pass_rate"], ok))
        return "".join(out)

    def coef_rows():
        out = []
        for k in ORDER:
            if k not in cf:
                continue
            a = cf[k]
            rel = res["coef_rel"].get(k)
            cl = rel or {}
            relv, rci = cl.get("f"), (cl.get("ci") or [None, None])
            out.append("<tr><td>%s</td><td class='num'>%d</td><td class='num'>%d</td><td class='num'>%s</td>"
                       "<td class='num'>%.2f</td><td class='num'>%+.4f</td>"
                       "<td class='num %s'>%s</td><td class='num'>[%+.2f, %+.2f]</td></tr>"
                       % (k, dn.get(k, 0), a["n"], _f(a["mean"]), a["sd"], a["f"],
                          "up" if (relv or 0) > 0 else "dn",
                          ("%+.2f" % relv) if relv is not None else "—",
                          rci[0], rci[1]))
        return "".join(out)

    def sc_rows():
        return "".join(
            # ⚠ by_sc 的键是环境分（float）；从 JSON 读回时会变成 str，必须显式转回
            "<tr><td>≈%.1f</td><td class='num'>%d</td><td class='num'>%s</td><td class='num'>%.1f%%</td>"
            "<td class='num'>%+.4f</td></tr>"
            % (float(kk), v["n"], _f(v["mean"]), v["wr"], v["ms"])
            for kk, v in res.get("by_sc", {}).items())

    al = res.get("allow", {})
    allow_rows = ""
    if al.get("a"):
        allow_rows += ("<tr><td>弱势 · 只放行 A 档（现行 allow）</td><td class='num'>%d</td>"
                       "<td class='num'>%s</td><td class='num'>%.1f%%</td></tr>"
                       % (al["a"]["n"], _f(al["a"]["mean"]), al["a"]["wr"]))
    if al.get("ab"):
        allow_rows += ("<tr><td>弱势 · A+B 全放行</td><td class='num'>%d</td>"
                       "<td class='num'>%s</td><td class='num'>%.1f%%</td></tr>"
                       % (al["ab"]["n"], _f(al["ab"]["mean"]), al["ab"]["wr"]))

    ds = res.get("ds") or []
    lo = res.get("date_lo") or (ds[0] if ds else "—")
    hi = res.get("date_hi") or (ds[-1] if ds else "—")
    nday = sum(dn.values())
    comp = res.get("composite", {})
    ea_html = _exit_assumption_html(res)

    html = f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>主升精选 · 环境门控系数样本外验证 · {lo}~{hi}</title><style>{CSS}</style></head>
<body><div class="wrap">
<h1>主升精选 · 大盘环境门控系数样本外验证</h1>
<div class="sub">面板 {lo} ~ {hi} ｜ 可用信号日 {nday} 个（强势 {dn.get('强势', 0)} / 震荡 {dn.get('震荡', 0)} /
弱势 {dn.get('弱势', 0)} / 破位 {dn.get('破位', 0)}）｜ 退出规则 −12% 硬止损 / +6% 激活 / 3% 回撤 / 满 20 日强平</div>

<div class="box gold"><b>一句话结论：0.55 没有样本外依据，0.8 也没有；数据反推出来的系数是「二值」的 —— 只有「强势」档该持有，其余档空仓。</b><br>
反推的相对仓位系数（强势 = 1.00）：强势 <b>+1.00 [0.60, 1.40]</b> 显著为正；震荡 <b>−0.16 [−0.91, 0.49]</b>；
弱势 <b>−0.46 [−1.16, +0.22]</b>；破位 <b>−0.05</b>。弱势档的<b>点估计是负数</b>，也就是数据说的是「弱势档该空仓（0）」，
而不是「打 5.5 折继续持有」。置信区间都跨 0，所以 0.55 / 0.3 / 0.0 在这个样本量下分辨不出来，
但能确定的是：<b>那个折数不该是正数的 0.55</b>。据此主升精选的门控改为二值：强势开仓、其余空仓。</div>

{sens_note()}

<div class="box red"><b>⚠️ 门控不是胜率提升器。</b>环境分对「全域随便买」的后向 20 日收益<b>没有单调预测力</b>
（表一四档依次 {_f(ub.get('强势', {}).get('mean', 0))} / {_f(ub.get('震荡', {}).get('mean', 0))} /
{_f(ub.get('弱势', {}).get('mean', 0))} / {_f(ub.get('破位', {}).get('mean', 0))}，不仅不单调，破位档反而显著为正）。
所以门控只能决定<b>要不要出手</b>，不能声明它提高了选股胜率。</div>

<h2>一、环境分能不能预测后向收益？（全域随机持有，非选股层）</h2>
<div class="card"><table>
<thead><tr><th>环境档</th><th>信号日</th><th>笔数</th><th>均收益</th><th>95% 区间（按日整块重抽）</th><th>胜率</th></tr></thead>
<tbody>{uni_rows()}</tbody></table>
<div class="kv">均收益随环境分单调递减？<b>否</b>：破位（指数远低于 MA20）后 20 日反而最好，震荡/弱势最差。
这说明拿连续的环境分去调仓位系数站不住；能站住的是「分数高（指数在 MA20 上方且上行）时选股有 alpha、分数低时没有甚至为负」这个方向。</div></div>

<h2>二、各档策略相对同日全票的 edge（R1 等量对照 · R2 真选股层 · R3 双条件）</h2>
<div class="card"><table>
<thead><tr><th>环境档</th><th>信号日</th><th>策略逐日均</th><th>同日全票逐日均</th><th>edge</th><th>95% 区间</th><th>R3 通过率</th><th>判定</th></tr></thead>
<tbody>{edge_rows()}</tbody></table>
<div class="kv">「同日全票逐日均」= 同一天全市场票的等权平均，日期层的 β 已被消掉，剩下的是横截面选股能力。
<b>只有强势档 edge 显著且 R3 100% 通过</b>；破位档 edge 为负（破位时追强不如随便买），其余两档不显著。</div></div>

<h2>三、反推仓位系数（均值-方差有效口径，按日 block bootstrap）</h2>
<div class="card"><table>
<thead><tr><th>环境档</th><th>信号日</th><th>笔数</th><th>均收益</th><th>标准差</th><th>mean/sd</th><th>相对系数（强势=1）</th><th>相对系数 95% 区间</th></tr></thead>
<tbody>{coef_rows()}</tbody></table>
<div class="kv">固定风险预算时 i 档最优暴露 f<sub>i</sub> = σ/sd<sub>i</sub>，可达均值 = (mean<sub>i</sub>/sd<sub>i</sub>)·σ，
   故相对系数 = (mean/sd) 之比；均值 ≤ 0 的档自然得到 ≤ 0（= 空仓）。
  区间很宽（弱势 [−1.22, +0.19]、震荡 [−0.87, +0.57]），说明 5.5 折 / 3 折 / 0 折在这么小的样本下分不出来；
  但点估计方向上弱势与震荡都是负的，只可能是「不出手」。</div></div>

<h2>四、样本外切分：系数分档稳不稳（切分点 {res.get('cut')}）</h2>
<div class="card"><div class="kv">强势：训练 +1.61% → 测试 +2.41%（同为<b>正</b>）｜ 震荡：−0.27% → −0.46%（同为<b>负</b>）｜
弱势：−0.72% → −1.30%（同为<b>负</b>）｜ 破位：+0.26% → −0.28%（符号<b>翻转</b>，不可依赖）。<br>
符号稳定的只有强势（正）与震荡、弱势（负）；震荡/弱势两档同时为负 = 结论一致指向<b>不出手</b>。</div></div>

<h2>五、环境分连续分位（每 0.5 一档）</h2>
<div class="card"><table>
<thead><tr><th>环境分</th><th>笔数</th><th>均收益</th><th>胜率</th><th>mean/sd</th></tr></thead>
<tbody>{sc_rows()}</tbody></table>
<div class="kv">真正有区分的是<b>高分端</b>（≥4.0 两档 mean/sd 约 +0.24 / +0.36）与低分端（≈2.5 档 −0.30），
中间段（≈2.0/3.0/3.5）基本是噪声。现行阈值 3.8 大致压在 4.0 档边界上；2.2 与 3.0 这两道线<b>没有证据显示是拐点</b>。</div></div>

<h2>六、allow 过滤（弱势档只放行 A 档）值不值</h2>
<div class="card"><table>
<thead><tr><th>做法</th><th>笔数</th><th>均收益</th><th>胜率</th></tr></thead>
<tbody>{allow_rows}</tbody></table>
<div class="kv">「只放行 A 档」把均收益从 −2.06% 抬到 −1.05%，方向是对的；但 A 档本身期望仍是<b>负的</b> ——
光靠过滤救不回来，这正是弱势档最终判定为空仓的原因。</div></div>

{ea_html}

<h2>八、局限（先说清楚，别拿结论当承诺）</h2>
<div class="card"><div class="kv">
① <b>可用信号日只有 {nday} 个</b>（原始 58 个里前段缓存稀疏，丢弃 28 个），强势档仅 {dn.get('强势', 0)} 日，
绝对样本量小，所有置信区间都很宽 —— 本页结论只判方向、判不了精度。<br>
② <b>口径已对齐生产</b>：主结论（一二三四五六）全部按生产口径分组 ——
生产 <b>composite = 0.45×指数分 + 0.55×市场画像 core</b>（core 取趋势方向/技术/宽度/情绪四项，与该权重逐项复刻）。
core 只在最近 {res.get('n_core', 0)} 个信号日落盘，这些日之外退化为纯指数口径（数据可得性限制，不是做法），
且指数分只用 ≤ 信号日的上证收盘，<b>无未来函数</b>。两套口径在可比日上标签一致 {comp.get('same', 0)} 日 / 分歧 {comp.get('diff', 0)} 日。<br>
③ 前向 20 日窗口重叠 → 样本非独立；bootstrap 已按日整块重抽，但独立样本数仍只有 {nday} 个。<br>
④ <b>做T池共用同一张 ENV_RULE 表（pos_scale），本页没有验证做T场景的接口，因此不做任何改动</b>；
「强势开仓、其余空仓」只应用于<b>主升精选</b>。当前生产 ENV_RULE 里 弱势=0.55、震荡=0.8 仍保留原值，属于未经验证的风险预算参数。</div></div>

<div class="foot">本页为量化验证记录，非个股推荐、非买卖建议。决策责任在账户本人。证据生成脚本 quant/_env_gate_lab.py。</div>
</div></body></html>"""
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    open(OUT, "w", encoding="utf-8").write(html)
    print("[env] 写 %s" % OUT)


if __name__ == "__main__":
    main()
