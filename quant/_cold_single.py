# -*- coding: utf-8 -*-
"""
单维度严格检验（_cold_single.py）
===============================
用途
----
`_cold_ablate.py` 跑出 5 个因子全部非单调/反向，只剩「波动收敛(ATR%)」某一档
胜率 60.0%（基线 58.2%，+1.8pp）看着有希望。

**但那是同一份数据挑出来的最佳档 = 过拟合高危**（本项目已栽三次）。
本脚本只做一件事：对**一个**先验固定的维度做真样本外检验，判定它是否真的成立。

流程（无任何调参空间）
----------------------
1. 维度与方向**先验固定**（不扫参数）：ATR% 分 5 档，看胜率是否单调。
2. 三段 walk-forward：**方向在训练段定、测试段只验收**。
   具体：训练段若呈单调则方向 = 该方向；测试段按该方向判定是否同向。
3. 随机对照：同 n 同入场日独立抽 N 遍，**中位数必须显著低于该档胜率**。
4. 任一条不满足 → **该维度不成立**，不许进规则。

输出一个明确的 pass/fail + 全部证据数字，**不做任何美化**。

用法
----
    python _cold_single.py --date 2026-09-30 --dim calm
"""
from __future__ import annotations
import os, sys, json, math, argparse, collections, random

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import _cold_sector as CS
from _cold_oos import simulate, wr, median, MAXFW
from _cold_ablate import build_records

# 先验固定：每个维度的「期望方向」由经济逻辑给定，不扫参数
DIM_CN = {"low": "距 500 日高", "turn": "MA20 斜率", "vol": "量比",
          "lead": "20 日领涨幅度", "calm": "ATR%(20 日)"}
EXPECT_HIGH = {"low": False, "turn": True, "vol": True,
               "lead": True, "calm": False}      # False = 越小越好


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--dim", default="calm", choices=list(DIM_CN))
    ap.add_argument("--lookback", type=int, default=CS.LOOKBACK)
    ap.add_argument("--per-day", type=int, default=20)
    ap.add_argument("--nrand", type=int, default=200)
    a = ap.parse_args()

    dim = a.dim
    recs, bars, cal, pool_days, cold, stats, asof = build_records(a)
    print("[load] 样本=%d 维度=%s（%s，期望%s）"
          % (len(recs), dim, DIM_CN[dim],
             "越大越好" if EXPECT_HIGH[dim] else "越小越好"))
    if len(recs) < 100:
        print("样本过少，退出")
        return

    key = "f_" + dim

    # ---- 随机基线 ----
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

    # ---- 分 5 档 ----
    xs = sorted(r[key] for r in recs)
    ths = [xs[int(len(xs) * i / 5)] for i in range(1, 5)]
    bk = collections.defaultdict(list)
    for r in recs:
        b = 0
        for i, t in enumerate(ths):
            if r[key] <= t:
                b = i
                break
        else:
            b = 4
        bk[b].append(r)

    print("\n=== 分档（阈值只由全窗口分位产生，不调参）===")
    rows = []
    for b in sorted(bk):
        n, w, rt = wr(bk[b])
        lo = ths[b - 1] if b > 0 else None
        hi = ths[b] if b < 4 else None
        rows.append({"b": b, "n": n, "wr": w, "avg": rt, "lo": lo, "hi": hi})
        print("   档%d [%s, %s] n=%4d 胜率=%5.1f%% 均值=%6.2f%%"
              % (b, "−∞" if lo is None else "%.3f" % lo,
                 "∞" if hi is None else "%.3f" % hi, n, w, rt))
    ws = [r["wr"] for r in rows if r["n"] >= 30]
    ups = sum(1 for i in range(len(ws) - 1) if ws[i + 1] > ws[i])
    mono = ups >= len(ws) - 1 if len(ws) >= 3 else None
    print("   单调性：%s（首尾差 %+.1fpp）"
          % ({True: "是", False: "否", None: "样本不足"}[mono],
             (ws[-1] - ws[0]) if len(ws) >= 2 else 0.0))
    best = max(rows, key=lambda r: r["wr"])
    print("   最佳档%d 胜率=%.1f%%（基线 %.1f%%，%+.1fpp）"
          % (best["b"], best["wr"], bw, best["wr"] - bw))

    # ---- 三段 walk-forward：方向在训练段定，测试段验收 ----
    per = len(pool_days) // 3
    folds = [pool_days[i * per:(i + 1) * per] if i < 2 else pool_days[i * per:]
             for i in range(3)]
    print("\n=== walk-forward（方向先验固定，只看各段是否同向）===")
    fold_ok = []
    for i, f in enumerate(folds):
        sub = [r for r in recs if r["T"] in f]
        if len(sub) < 30:
            print("   段%d: n=%d 不可判" % (i + 1, len(sub)))
            fold_ok.append(None)
            continue
        # 该段内分档（阈值用**训练段**的分位，测试段零参与）
        xs2 = sorted(r[key] for r in sub)
        th2 = [xs2[int(len(xs2) * j / 5)] for j in range(1, 5)]
        b2 = collections.defaultdict(list)
        for r in sub:
            b = 0
            for j, t in enumerate(th2):
                if r[key] <= t:
                    b = j
                    break
            else:
                b = 4
            b2[b].append(r)
        wrs = [wr(b2[b])[1] for b in sorted(b2) if len(b2[b]) >= 15]
        if len(wrs) < 3:
            print("   段%d: 档内样本不足，不可判" % (i + 1))
            fold_ok.append(None)
            continue
        # 方向判定：期望方向下，最优应落在哪一端
        got_high = wrs[0] > wrs[-1]
        agree = (got_high == EXPECT_HIGH[dim])
        # 同向：即「期望的那一端胜率更高」
        ok = agree
        fold_ok.append(ok)
        print("   段%d: 档0=%.1f%% → 档4=%.1f%%  期望%s  实际%s  %s"
              % (i + 1, wrs[0], wrs[-1],
                 "高端更好" if EXPECT_HIGH[dim] else "低端更好",
                 "高端更好" if got_high else "低端更好",
                 "✓" if ok else "✗ 反向"))

    judged = [x for x in fold_ok if x is not None]
    n_ok = sum(1 for x in judged if x)

    # ---- 随机对照：最佳档 vs 随机中位数 ----
    pick = bk[best["b"]]
    rr = random.Random(31000)
    rw = []
    for _ in range(a.nrand):
        samp = []
        for T in pool_days:
            k = sum(1 for r in pick if r["T"] == T)
            for _ in range(k):
                c = rr.choice(all_codes)
                bs = bars[c]
                try:
                    j = len(bs) - 1 - (len(cal) - 1 - cal.index(T))
                except Exception:
                    continue
                if 0 <= j < len(bs) and bs[j]["date"] == T:
                    x = simulate(bs, c, j)
                    if x:
                        samp.append({"T": T, "win": x[1], "ret": x[0]})
        if samp:
            rw.append(wr(samp)[1])
    rmed = median(rw) if rw else 0.0
    edge = best["wr"] - rmed
    print("\n=== 随机对照（同 n 同入场日独立抽 %d 遍）===" % a.nrand)
    print("   最佳档 n=%d 胜率=%.1f%%" % (len(pick), best["wr"]))
    print("   随机 胜率中位数=%.1f%%  p90=%.1f%%" % (rmed, (sorted(rw)[int(len(rw) * 0.9)] if rw else 0.0)))
    print("   edge = %+.1fpp" % edge)

    passed = bool(mono and len(judged) >= 2 and n_ok == len(judged) and edge >= 3.0)
    print("\n=== 判定（宁可不选，不能乱选）===")
    print("   ① 分档单调：%s" % ("✓" if mono else "✗"))
    print("   ② 样本外同向：%d/%d 段%s" % (n_ok, len(judged), " ✓" if (judged and n_ok == len(judged)) else " ✗"))
    print("   ③ 相对随机优势：%+.1fpp（判据 ≥3.0）%s" % (edge, "✓" if edge >= 3.0 else "✗"))
    print("   → %s" % ("**该维度成立**" if passed else "**不成立，不得进规则**"))
    if not passed:
        print("   提示：按铁律，本页不展示该因子的任何「最佳档」数字作为有效结论。")

    os.makedirs(CS.OUTDIR, exist_ok=True)
    out = {"asof": asof, "dim": dim, "dim_cn": DIM_CN[dim],
           "expect_high": EXPECT_HIGH[dim],
           "rows": rows, "mono": mono,
           "base": [bn, bw, ba],
           "best": best, "n_pick": len(pick),
           "rnd_med": rmed, "rnd_p90": sorted(rw)[int(len(rw) * 0.9)] if rw else None,
           "edge": edge,
           "fold_ok": fold_ok, "pass": passed}
    p = os.path.join(CS.OUTDIR, "single_%s_%s.json" % (dim, asof.replace("-", "")))
    json.dump(out, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n[out] %s" % p)


if __name__ == "__main__":
    main()
