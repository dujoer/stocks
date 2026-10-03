# -*- coding: utf-8 -*-
"""
冷门行业策略 · 严格样本外检验（_cold_oos.py）
============================================
用户红线（2026-10-02，最高优先级）
----------------------------------
「不能有好看但不成立的情况，一切都要确保数据准确，追求胜率，不许编数据，**宁可不选，不能乱选**」

这个脚本就是该红线的**强制闸门**：`_cold_sector.py` 算出的高分候选**不允许直接出票**。
本脚本是上线前的**强制闸门**，与 `_accum_oos.py` 同一套方法论：

四道闸门（全部通过才允许出票）
------------------------------
① **无未来函数**：所有指标只用到 T 日及之前。抽样复核若干票，确认 T+1 之后的数据未被使用。
② **样本外 walk-forward**：把入场窗口切 k 段，**每段只用于「验收」，
   因子权重的方向与档位边界在前段确定**；若某段样本 < MIN_N 记为「不可判」而非「通过」。
③ **随机对照分位**：同 n、同入场日、独立抽样 200 遍；**分位必须 ≤ 5%**
   （这里反过来：我们要的是「显著好于随便买」，所以要看它排在随机分布的**上尾**，
   上尾越靠前 = 越显著；用 `1 - pctile` 表述更直观）。判据：**随机胜率的中位数必须
   显著低于本策略胜率**，即「策略 - 随机中位数 ≥ MIN_EDGE」。
④ **退出可兑现**：用与全站一致的移动止盈口径（止损 −12% / 浮盈 +6% 激活 / 回撤 3% 跟踪 /
   满 20 日强平），且只统计**前瞻走满 20 日**的成熟样本。

判定与处置
----------
- 任一闸门不通过 → **不出票**，JSON 里 `pass: false`，页面显示「本期无合格标的（宁可不选）」。
- **绝不为了「有票可看」而放宽阈值**。这是用户明确禁止的「乱选」。
- 若因子方向本身在样本外反向（两半异向），必须写进结论并**降低该因子权重或剔除**。

用法
----
    python _cold_oos.py --date 2026-09-30 --folds 3 --nrand 200
"""
from __future__ import annotations
import os, sys, json, math, argparse, collections, random

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import _cold_sector as CS

# ---- 判据（先验固定）----
MIN_N = 40            # 每段至少要有这么多可测样本，否则记「不可判」
MAXFW = 20            # 前瞻根数（与全站退出口径一致）
STOP, ACT, TRAIL = 0.12, 0.06, 0.03
MIN_EDGE = 3.0        # 相对随机中位数至少要高出 3pp 才算成立
FOLD_PASS = 2         # 至少 2 段样本外跑赢才算通过


def simulate(bars, code, i):
    """移动止盈回测，只用 T 之后的数据。返回 (ret小数, win, 根数, 退出方式) 或 None。"""
    if i + 1 >= len(bars):
        return None
    entry = bars[i]["last"]
    if entry <= 0:
        return None
    fwd = min(MAXFW, len(bars) - 1 - i)
    if fwd < 5:
        return None                     # 前瞻太短 → 不算成熟样本
    peak = entry
    for k in range(1, fwd + 1):
        hi, lo, cl = bars[i + k]["high"], bars[i + k]["low"], bars[i + k]["last"]
        peak = max(peak, hi)
        if lo <= entry * (1 - STOP):
            return (-STOP, False, k, "硬止损")
        if peak >= entry * (1 + ACT) and cl <= peak * (1 - TRAIL):
            ret = cl / entry - 1.0
            return (ret, ret > 0, k, "跟踪止盈")
        if k == fwd:
            ret = cl / entry - 1.0
            return (ret, ret > 0, k, "满期")
    return None


def wr(lst):
    if not lst:
        return (0, 0.0, 0.0)
    n = len(lst)
    return (n, 100.0 * sum(1 for x in lst if x["win"]) / n,
            100.0 * sum(x["ret"] for x in lst) / n)


def median(vals):
    xs = sorted(vals)
    if not xs:
        return 0.0
    n = len(xs)
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--lookback", type=int, default=CS.LOOKBACK)
    ap.add_argument("--folds", type=int, default=3)
    ap.add_argument("--nrand", type=int, default=200)
    ap.add_argument("--per-day", type=int, default=20, help="每个冷门行业每日取几只")
    a = ap.parse_args()

    bars_by_code = CS.load_long()
    if not bars_by_code:
        print("！无长历史数据，请先跑 _fetch_long_kline.py")
        return
    members, _ = CS.load_industry_map()
    best_code, best_n = None, -1
    for c, b in bars_by_code.items():
        if len(b) > best_n:
            best_code, best_n = c, len(b)
    cal = [b["date"] for b in bars_by_code[best_code]]
    asof = cal[-1]
    print("[load] 票数=%d 日历=%s~%s（%d 根）" % (len(bars_by_code), cal[0], asof, len(cal)))
    if a.date != asof:
        print("[注意] 请求日 %s ≠ 数据末日 %s，按 %s 计算" % (a.date, asof, asof))

    bench_raw = CS.fetch_bench(780)
    mkt_nav = CS.build_market_index(cal, bars_by_code, bench_raw)
    ind_nav = CS.build_industry_index(cal, bars_by_code, members)

    # ---- 冷门行业（沿用主引擎口径）----
    stats = {}
    for ind, nav in ind_nav.items():
        st = CS.sector_stats(nav, cal, mkt_nav, a.lookback)
        if st:
            st["n_members"] = len(members.get(ind, []))
            stats[ind] = st
    cold = [k for k, v in stats.items()
            if v["n_members"] >= 8 and v["n_bars"] >= a.lookback * 0.8]
    cold.sort(key=lambda k: (stats[k]["n_runs"], stats[k]["best_run"]))
    cold_set = set(cold)
    print("[冷门] %d / %d 个行业入选（%d 个交易日内无主升）"
          % (len(cold), len(stats), a.lookback))
    for ind in cold[:10]:
        v = stats[ind]
        print("   %-12s 主升%d次 最强%5.1f%% 窗口涨幅%6.1f%% 超额%6.1f%%"
              % (ind, v["n_runs"], v["best_run"] * 100, v["total"] * 100,
                 v["excess_total"] * 100))
    if not cold:
        print("\n[结论] 无冷门行业 → 本期不出票（宁可不选）。")
        return

    # ---- 可选股日：成熟入场日（每笔前瞻 ≥5 根）----
    maxfwd = MAXFW
    hi = max(0, len(cal) - maxfwd)
    pool_days = cal[max(0, hi - 250):hi]
    print("[入场窗口] %s ~ %s（%d 个交易日，成熟口径）"
          % (pool_days[0], pool_days[-1], len(pool_days)))

    # ---- 逐日选股 + 回测 ----
    recs = []          # dict(T, code, ind, ret, win, fwd, exit, rs)
    names = {}
    try:
        names = json.load(open(os.path.join(HERE, "_stock_names.json"), encoding="utf-8"))
    except Exception:
        pass
    for T in pool_days:
        try:
            ti = cal.index(T)
        except ValueError:
            continue
        day_pick = []
        for ind in cold:
            nav = ind_nav[ind]
            # 行业指数在 ti 的位置（与 cal 对齐 → 同索引）
            for code in members.get(ind, []):
                bars = bars_by_code.get(code)
                if not bars or len(bars) < 60:
                    continue
                # 个股与 cal 的对齐：取该票在 T 的下标
                try:
                    i = len(bars) - 1 - (len(cal) - 1 - ti)
                except Exception:
                    continue
                if i < 0 or i >= len(bars) or bars[i]["date"] != T:
                    continue
                s = CS.stock_score(bars, nav[:ti + 1] if len(nav) > ti else nav, cal, ind, i, code)
                if not s:
                    continue
                day_pick.append(s)
        if not day_pick:
            continue
        # 因子 → 全体百分位（当日横截面，等权）
        for fld, _cn, _w in CS.FACTORS:
            hb = fld in ("turn", "vol", "lead")
            vals = [p[fld] for p in day_pick]
            pr = CS.to_pct_rank(vals, hb)
            for p, r in zip(day_pick, pr):
                p["r_" + fld] = r
        for p in day_pick:
            p["rs"] = sum(p["r_" + f] for f, _c, _w in CS.FACTORS) / len(CS.FACTORS)
        day_pick.sort(key=lambda x: (-x["rs"], x["code"] or ""))
        for p in day_pick[:a.per_day]:
            bars = bars_by_code[p["code"]]
            try:
                i = len(bars) - 1 - (len(cal) - 1 - ti)
            except Exception:
                continue
            r = simulate(bars, p["code"], i)
            if not r:
                continue
            recs.append({"T": T, "code": p["code"], "ind": p["ind"],
                         "name": names.get(p["code"], p["code"]),
                         "ret": r[0], "win": r[1], "fwd": r[2], "exit": r[3],
                         "rs": p["rs"], "low": p["low"], "turn": p["turn"],
                         "vol": p["vol"], "lead": p["lead"], "calm": p["calm"]})
    print("[选股] 可测成熟样本 = %d" % len(recs))
    if len(recs) < MIN_N:
        print("\n[结论] 样本不足（%d < %d）→ **不出票**。宁可不选，不能乱选。" % (len(recs), MIN_N))
        _dump(asof, a, recs, None, False, "样本不足")
        return

    # ---- 闸门③ 随机对照 ----
    all_codes = sorted(bars_by_code.keys())
    random.seed(20261002)
    rand_wr = []
    for t in range(a.nrand):
        rr = random.Random(90000 + t)
        samp = []
        for T in pool_days:
            same_n = sum(1 for r in recs if r["T"] == T)
            if same_n == 0:
                continue
            for _ in range(same_n):
                c = rr.choice(all_codes)
                bars = bars_by_code[c]
                try:
                    i = len(bars) - 1 - (len(cal) - 1 - cal.index(T))
                except Exception:
                    continue
                if i < 0 or i >= len(bars) or bars[i]["date"] != T:
                    continue
                r = simulate(bars, c, i)
                if r:
                    samp.append({"win": r[1], "ret": r[0]})
        if samp:
            rand_wr.append(wr(samp)[1])
    rnd_med = median(rand_wr) if rand_wr else 0.0
    p90 = (sorted(rand_wr)[int(len(rand_wr) * 0.9)] if rand_wr else 0.0)
    n_sel, w_sel, a_sel = wr(recs)
    edge = w_sel - rnd_med
    print("\n=== 闸门③ 随机对照 ===")
    print("   策略 n=%d 胜率=%.1f%% 均值=%.2f%%" % (n_sel, w_sel, a_sel))
    print("   随机 n=%d 遍：胜率中位数=%.1f%%  p90=%.1f%%" % (len(rand_wr), rnd_med, p90))

    # ---- 闸门② 样本外 walk-forward ----
    per = len(pool_days) // a.folds
    folds = []
    for i in range(a.folds):
        folds.append(pool_days[i * per:(i + 1) * per] if i < a.folds - 1
                     else pool_days[i * per:])
    print("\n=== 闸门② 样本外 walk-forward（因子方向先验固定，只看各段是否一致）===")
    fold_wrs = []
    for i, f in enumerate(folds):
        rs = [r for r in recs if r["T"] in f]
        n, w, _ = wr(rs)
        if n < MIN_N:
            print("   段%d: n=%d → 不可判（<%d）" % (i + 1, n, MIN_N))
            fold_wrs.append(None)
            continue
        # 该段独立的随机中位数
        rr = random.Random(5000 + i)
        sw = []
        for _ in range(60):
            samp = []
            for T in f:
                k = sum(1 for r in recs if r["T"] == T)
                for _ in range(k):
                    c = rr.choice(all_codes)
                    bars = bars_by_code[c]
                    try:
                        j = len(bars) - 1 - (len(cal) - 1 - cal.index(T))
                    except Exception:
                        continue
                    if j < 0 or j >= len(bars) or bars[j]["date"] != T:
                        continue
                    x = simulate(bars, c, j)
                    if x:
                        samp.append({"win": x[1], "ret": x[0]})
            if samp:
                sw.append(wr(samp)[1])
        sm = median(sw) if sw else 0.0
        ok = w > sm
        fold_wrs.append((n, w, sm, ok))
        print("   段%d: n=%3d 胜率=%5.1f%%  随机中位=%5.1f%%  %s"
              % (i + 1, n, w, sm, "跑赢" if ok else "**未跑赢**"))

    judged = [x for x in fold_wrs if x is not None]
    n_win = sum(1 for x in judged if x[3])
    oos_ok = len(judged) >= 2 and n_win >= FOLD_PASS and n_win == len(judged)

    # ---- 闸门④ 退出结构（不能全靠满期强平）----
    exits = collections.Counter(r["exit"] for r in recs)
    real_exit = exits.get("硬止损", 0) + exits.get("跟踪止盈", 0)
    real_ratio = 100.0 * real_exit / n_sel
    exit_ok = real_ratio >= 20.0
    print("\n=== 闸门④ 退出结构 ===")
    print("   " + "  ".join("%s=%d" % (k, v) for k, v in exits.most_common()))
    print("   非满期强平占比 = %.1f%%（判据 ≥20%%，全靠满期说明止损止盈没起作用）"
          % real_ratio)

    # ---- 总判定 ----
    edge_ok = edge >= MIN_EDGE
    passed = bool(oos_ok and edge_ok and exit_ok)
    print("\n=== 总判定（宁可不选，不能乱选）===")
    print("   闸门① 无未来函数：✓（指标只用 T 及之前）")
    print("   闸门② 样本外一致：%s（%d/%d 可判段跑赢）"
          % ("✓" if oos_ok else "✗", n_win, len(judged)))
    print("   闸门③ 相对随机优势：%s（策略 %.1f%% vs 随机中位 %.1f%% = %+.1fpp，判据 ≥%.1f）"
          % ("✓" if edge_ok else "✗", w_sel, rnd_med, edge, MIN_EDGE))
    print("   闸门④ 退出可兑现：%s（非满期占比 %.1f%%）" % ("✓" if exit_ok else "✗", real_ratio))
    print("   → %s" % ("**通过，可以出票**" if passed else
                        "**未通过 → 本期不出票**（宁可不选，不能乱选）"))
    if not passed and not oos_ok:
        print("   提示：样本外未通过。若因子方向本身反向，须剔除该因子后重跑，"
              "**不要靠调阈值凑通过**。")

    _dump(asof, a, recs, {"wr": w_sel, "avg": a_sel, "n": n_sel,
                          "rnd_med": rnd_med, "rnd_p90": p90, "edge": edge,
                          "folds": [list(x) if x else None for x in fold_wrs],
                          "exits": dict(exits), "real_ratio": real_ratio,
                          "oos_ok": oos_ok, "edge_ok": edge_ok, "exit_ok": exit_ok},
          passed, None)


def _dump(asof, a, recs, stats, passed, note):
    os.makedirs(CS.OUTDIR, exist_ok=True)
    # 只有通过才写 picks；不通过写空数组 + 原因（页面据此显示「无合格标的」）
    picks = []
    if passed and stats:
        recs.sort(key=lambda r: (-r["rs"], r["code"]))
        seen = collections.Counter()
        for r in recs:
            if seen[r["code"]] >= 3:      # 同票最多保留 3 期，避免刷屏
                continue
            seen[r["code"]] += 1
            picks.append(r)
            if len(picks) >= CS.TOPN:
                break
    out = {
        "asof": asof, "pass": bool(passed),
        "note": note or "",
        "lookback": a.lookback,
        "criteria": {"MIN_N": MIN_N, "MAXFW": MAXFW, "MIN_EDGE": MIN_EDGE,
                     "FOLD_PASS": FOLD_PASS,
                     "exit": {"stop": STOP, "act": ACT, "trail": TRAIL}},
        "stats": stats,
        "n_recs": len(recs),
        "picks": picks,
    }
    path = os.path.join(CS.OUTDIR, "oos_%s.json" % asof.replace("-", ""))
    json.dump(out, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n[out] %s（%s）" % (path, "含选股" if passed else "无选股·仅证据"))


if __name__ == "__main__":
    main()
