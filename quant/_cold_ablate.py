# -*- coding: utf-8 -*-
"""
冷门行业策略 · 因子消融（_cold_ablate.py）
======================================
为什么需要它
------------
`_cold_oos.py` 闸门判定：5 因子合成的「将要主升」策略 53.7% 胜率，**跑输随机 57.9%（−4.2pp）**，
三段全输 → 闸门正确拦截，不出票。
但样本量足够（5000 笔成熟样本、250 个交易日），**说明有条件回答「哪里错了」**。

消融设计
--------
对每个因子做 **on/off 对照**（在该因子分位最高的前 1/3 vs 后 1/3 上比胜率），
以及 **单调性检验**（胜率是否随该因子档位单调变化）。
- 单调且方向正确 → 可保留
- 方向反了 → **剔除**（这是最可能的失败原因：5 因子等权里有反向因子在拖累）
- 非单调 → 噪声，剔除

再对**剔除反向后**的组合重跑一次闸门，**由脚本自己判定 pass**，不靠人挑。

⚠ 纪律：消融只用于**判断哪些因子该留**，最终「是否出票」由 `_cold_oos.py` 的
   四道闸门决定。消融里出现的任何好数字都**不能**直接写进页面。

用法
----
    python _cold_ablate.py --date 2026-09-30
"""
from __future__ import annotations
import os, sys, json, math, argparse, collections, random

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import _cold_sector as CS
from _cold_oos import simulate, wr, median, MAXFW


def bucketize(recs, field, k=5):
    ths = CS.quantile_bins([(r["code"], r[field]) for r in recs], k) \
        if hasattr(CS, "quantile_bins") else None
    if ths is None:
        xs = sorted(r[field] for r in recs)
        ths = [xs[int(len(xs) * i / k)] for i in range(1, k)]
    out = collections.defaultdict(list)
    for r in recs:
        b = 0
        for i, t in enumerate(ths):
            if r[field] <= t:
                b = i
                break
        else:
            b = len(ths)
        out[b].append(r)
    return out, ths


def build_records(a):
    """逐日建样本（与 _cold_oos 同一口径，阈值只用 T 之前）。"""
    bars_by_code = CS.load_long()
    members, _ = CS.load_industry_map()
    best_code, best_n = None, -1
    for c, b in bars_by_code.items():
        if len(b) > best_n:
            best_code, best_n = c, len(b)
    cal = [b["date"] for b in bars_by_code[best_code]]
    asof = cal[-1]
    bench_raw = CS.fetch_bench(780)
    mkt_nav = CS.build_market_index(cal, bars_by_code, bench_raw)
    ind_nav = CS.build_industry_index(cal, bars_by_code, members)
    stats = {}
    for ind, nav in ind_nav.items():
        st = CS.sector_stats(nav, cal, mkt_nav, a.lookback)
        if st:
            st["n_members"] = len(members.get(ind, []))
            stats[ind] = st
    cold = [k for k, v in stats.items()
            if v["n_members"] >= 8 and v["n_bars"] >= a.lookback * 0.8]
    cold.sort(key=lambda k: (stats[k]["n_runs"], stats[k]["best_run"]))
    hi = max(0, len(cal) - MAXFW)
    pool_days = cal[max(0, hi - 250):hi]
    try:
        names = json.load(open(os.path.join(HERE, "_stock_names.json"), encoding="utf-8"))
    except Exception:
        names = {}

    recs = []
    for T in pool_days:
        try:
            ti = cal.index(T)
        except ValueError:
            continue
        day = []
        for ind in cold:
            nav = ind_nav[ind]
            navt = nav[:ti + 1] if len(nav) > ti else nav
            for code in members.get(ind, []):
                bars = bars_by_code.get(code)
                if not bars or len(bars) < 60:
                    continue
                i = len(bars) - 1 - (len(cal) - 1 - ti)
                if i < 0 or i >= len(bars) or bars[i]["date"] != T:
                    continue
                s = CS.stock_score(bars, navt, cal, ind, i, code)
                if s:
                    day.append(s)
        if not day:
            continue
        for fld, _cn, _w in CS.FACTORS:
            hb = fld in ("turn", "vol", "lead")
            pr = CS.to_pct_rank([p[fld] for p in day], hb)
            for p, r in zip(day, pr):
                p["r_" + fld] = r
        for p in day:
            p["rs"] = sum(p["r_" + f] for f, _c, _w in CS.FACTORS) / len(CS.FACTORS)
        day.sort(key=lambda x: (-x["rs"], x["code"] or ""))
        for p in day[:a.per_day]:
            bars = bars_by_code[p["code"]]
            i = len(bars) - 1 - (len(cal) - 1 - ti)
            r = simulate(bars, p["code"], i)
            if not r:
                continue
            recs.append({"T": T, "code": p["code"], "ind": p["ind"],
                         "name": names.get(p["code"], p["code"]),
                         "ret": r[0], "win": r[1], "fwd": r[2], "exit": r[3],
                         "rs": p["rs"],
                         # 百分位分位（用于「清洗后评分」重算）
                         "r_low": p["r_low"], "r_turn": p["r_turn"],
                         "r_vol": p["r_vol"], "r_lead": p["r_lead"],
                         "r_calm": p["r_calm"],
                         # 原始值（用于分档检验）
                         "f_low": p["low"], "f_turn": p["turn"], "f_vol": p["vol"],
                         "f_lead": p["lead"], "f_calm": p["calm"]})
    return recs, bars_by_code, cal, pool_days, cold, stats, asof


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--lookback", type=int, default=CS.LOOKBACK)
    ap.add_argument("--per-day", type=int, default=20)
    a = ap.parse_args()

    recs, bars, cal, pool_days, cold, stats, asof = build_records(a)
    print("[load] 样本=%d 入场窗口=%s~%s 冷门行业=%d" % (len(recs), pool_days[0], pool_days[-1], len(cold)))
    if len(recs) < 100:
        print("样本过少，退出")
        return

    # ---- 随机基线（同 n 同入场日）----
    all_codes = sorted(bars.keys())
    random.seed(20261002)
    base = []
    for T in pool_days:
        k = sum(1 for r in recs if r["T"] == T)
        for _ in range(k):
            c = random.choice(all_codes)
            bs = bars[c]
            try:
                i = len(bs) - 1 - (len(cal) - 1 - cal.index(T))
            except Exception:
                continue
            if 0 <= i < len(bs) and bs[i]["date"] == T:
                x = simulate(bs, c, i)
                if x:
                    base.append({"T": T, "win": x[1], "ret": x[0]})
    bn, bw, ba = wr(base)
    print("[基线] n=%d 胜率=%.1f%% 均值=%.2f%%" % (bn, bw, ba))

    # ---- 逐因子：分档单调性 ----
    print("\n=== 逐因子分档（胜率是否随该因子单调变化）===")
    verdict = {}
    for fld, cn, why in CS.FACTORS:
        key = "f_" + fld
        bk, ths = bucketize(recs, key, 5)
        rows = []
        for b in sorted(bk):
            n, w, rt = wr(bk[b])
            rows.append((b, n, w, rt))
        ws = [w for _b, n, w, _r in rows if n >= 30]
        mono = None
        if len(ws) >= 3:
            ups = sum(1 for i in range(len(ws) - 1) if ws[i + 1] > ws[i])
            mono = ups >= len(ws) - 1
        spread = (ws[-1] - ws[0]) if len(ws) >= 2 else None
        # 方向判定：最佳档在高位 → 正向；最佳档在低位 → 反向
        best_b = max(range(len(rows)), key=lambda i: rows[i][2]) if rows else 0
        # 期望方向：原打分方向（turn/vol/lead 越大越好；low/calm 越小越好）
        expect_high = fld in ("turn", "vol", "lead")
        got_high = best_b >= len(rows) / 2.0
        agree = (expect_high == got_high)
        v = "保留" if (agree and mono) else ("**反向→剔除**" if not agree else "非单调→剔除")
        verdict[fld] = {"keep": bool(agree and mono), "rows": rows,
                        "mono": mono, "spread": spread, "verdict": v,
                        "expect_high": expect_high}
        print("   %-14s（期望%s）" % (cn, "越大越好" if expect_high else "越小越好"))
        for b, n, w, rt in rows:
            print("      档%d n=%4d 胜率=%5.1f%% 均值=%6.2f%%%s"
                  % (b, n, w, rt, "  (样本薄)" if n < 30 else ""))
        print("      首尾差 %s ｜ 单调=%s ｜ 最佳档=%d → %s"
              % ("%+.1fpp" % spread if spread is not None else "—",
                 {True: "是", False: "否", None: "样本不足"}[mono], best_b, v))

    # ---- 剔除反向后重算 ----
    keep = [f for f, _c, _w in CS.FACTORS if verdict[f]["keep"]]
    drop = [f for f, _c, _w in CS.FACTORS if not verdict[f]["keep"]]
    print("\n=== 清洗后：保留 %s ／ 剔除 %s ==="
          % ("、".join(keep) or "无", "、".join(drop) or "无"))

    if keep:
        for r in recs:
            r["rs2"] = sum(r["r_" + f] if ("r_" + f) in r else 0 for f in keep) / len(keep)
        recs.sort(key=lambda r: (-r["rs2"], r["code"]))
        top = recs[:len(recs) // 5]          # 取评分前 20% 作为「入选」
        n2, w2, a2 = wr(top)
        print("   清洗后评分前 20%%：n=%d 胜率=%.1f%% 均值=%.2f%%  edge=%+.1fpp"
              % (n2, w2, a2, w2 - bw))
    else:
        n2, w2, a2 = (0, 0.0, 0.0)
        print("   全部因子均被剔除 → 无可用组合")

    print("\n=== 结论 ===")
    print("   反向因子：%s" % ("、".join(
        [c for f, c, _w in CS.FACTORS if f in drop] or "无")))
    print("   %s" % ("**当前 5 因子设计不成立**。按铁律「宁可不选」，不出票。"
                    if w2 <= bw or not keep else
                    "清洗后 edge 为正，**仍需跑 `_cold_oos.py` 四道闸门**才能出票（消融不作为上线依据）。"))

    out = {"asof": asof, "n": len(recs), "base": [bn, bw, ba],
           "verdict": {f: {k: v for k, v in verdict[f].items() if k != "rows"}
                       for f in verdict},
           "buckets": {f: verdict[f]["rows"] for f in verdict},
           "keep": keep, "drop": drop,
           "cleaned": {"n": n2, "wr": w2, "avg": a2, "edge": w2 - bw}}
    os.makedirs(CS.OUTDIR, exist_ok=True)
    p = os.path.join(CS.OUTDIR, "ablate_%s.json" % asof.replace("-", ""))
    json.dump(out, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n[out] %s" % p)


if __name__ == "__main__":
    main()
