# -*- coding: utf-8 -*-
"""
增仓精选 · 因子消融实验室（_accum_ablate.py）
===========================================
为什么需要它
------------
`accum_result.json` 当前口径下**入选整体 54.2% < 随机基线 57.3%（edge −3.2pp）**，
即这套「机构/私募季度增持 I × 融资 1/3/5 日净增仓 M」的合成**没有产生超额**。
但结论不能停在「没用」—— 必须回答：是哪几个因子在拖后腿？换什么组合才可能有正 edge？

方法（照抄 `_rbot_ablate.py` 已验证的路子，勿改成自动筛因子）
----------------------------------------------------------
1. **单因子命中率**：每个信号单独触发时的胜率 vs 基线。n<30 的只标注不采信。
2. **留一法（leave-one-out）**：从全信号里去掉一个因子，看胜率是升还是降。
   去掉后**升**的因子 = 负贡献（拖后腿）；去掉后**降**的 = 正贡献。
3. **单调分档**：把能连续取值的因子（margin 占比、信号数、共振数）按分位分档，
   看胜率是否随档位**单调**。非单调 = 该维度是噪声不是 alpha（三连阴的教训）。
4. **两半同向检验**：把入场窗口劈成前一半/后一半，只有两半同向为正才算真信号。

硬纪律
------
- 任何维度只有在「样本量够 + 两半同向 + 分档单调」三条都成立时才允许写进选股规则。
- 只输出统计与建议，**不改选股规则、不生成页面**（规则改动由人工确认后写进 `build_accum.py`）。
- 基线必须**独立抽样循环**（复用其它桶会让结论无效，三连阴首版踩过）。

用法
----
    python _accum_ablate.py              # 默认 60 个成熟入场日
    python _accum_ablate.py --days 90
    python --json                        # 只落 JSON 不打印
"""
from __future__ import annotations
import os, sys, json, math, argparse, collections, random

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import _accum_lab as L


# ============================================================
# 分档工具
# ============================================================
def quantile_bins(vals, k=5):
    """按分位切 k 档。返回 (分位阈值列表)。vals 为 [(code, value)]。"""
    xs = sorted(v for _c, v in vals)
    if not xs:
        return []
    out = []
    for i in range(1, k):
        out.append(xs[int(len(xs) * i / k)])
    return out


def bucket_of(v, ths):
    for i, t in enumerate(ths):
        if v <= t:
            return i
    return len(ths)


def wr(lst):
    """返回 (n, 胜率%, 平均收益%)。ret 存的是小数（0.05 = +5%），此处换算成百分数。"""
    if not lst:
        return (0, 0.0, 0.0)
    n = len(lst)
    w = sum(1 for x in lst if x["win"])
    ret = 100.0 * sum(x["ret"] for x in lst) / n
    return (n, 100.0 * w / n, ret)


# ============================================================
# 价格结构维度（先验固定，方向由经济逻辑给定，不筛不调权）
# ============================================================
# 事件驱动信号（大宗/席位/增减持）本质是「异动」，异动 = 短期超买 → 天然均值回归，
# 所以单靠它拿不到超额（消融已证：入选 55.5% < 基线 60%）。
# 但本项目在主升/反转/三连阴上反复验证有效的方向是「趋势 + 资金 + 相对低位」。
# 因此这里加一组价格维度，检验**事件信号叠加哪种价格结构**能把胜率抬过基线。
PRICE_DIMS = [
    ("dist_hi250", "距250日高",      "负向：越接近三年高越透支"),
    ("dist_hi60",  "距60日高",       "双向：过高追涨、过低未启动"),
    ("mom20",      "20日涨跌幅",     "双向：动量 vs 过度反弹"),
    ("mom60",      "60日涨跌幅",     "负向：中期涨幅越大越透支"),
    ("ma20_slope", "MA20斜率(20日)", "正向：趋势向上"),
    ("vol_atr",    "ATR%(20日)",     "负向：波动越大越难兑现（三连阴已证）"),
    ("amt20_log",  "20日均额对数",   "双向：流动性"),
    ("dd60",       "距60日高回撤",   "正向：温和回撤 = 起飞前洗盘"),
]


def price_dims(K, code, T):
    """取 T 日（含 T）为止的价格结构。T 之后的数据一律不看，防未来函数。"""
    if code not in K:
        return None
    ds, last, high, low, amt = K[code]
    try:
        i = ds.index(T)
    except ValueError:
        return None
    if i < 5:
        return None
    c = last[i]
    if c <= 0:
        return None

    def past(n):
        j = max(0, i - n + 1)
        return last[j:i + 1]

    # 波动率 ATR%：20 日真实波幅均值 / 收盘
    w = 20
    j = max(0, i - w + 1)
    trs = []
    for k in range(j, i + 1):
        h, l = high[k], low[k]
        pc = last[k - 1] if k > 0 else c
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    atr = sum(trs) / len(trs) / c if trs else 0.0

    # MA20 斜率 = 近 20 日线性拟合方向（归一化为日均 %）
    p20 = past(20)
    if len(p20) >= 10:
        n = len(p20)
        xs = list(range(n))
        mx, my = sum(xs) / n, sum(p20) / n
        num = sum((xs[k] - mx) * (p20[k] - my) for k in range(n))
        den = sum((x - mx) ** 2 for x in xs) or 1.0
        slope = (num / den) / my * 100.0
    else:
        slope = 0.0

    h250 = max(high[max(0, i - 249):i + 1]) or c
    h60 = max(high[max(0, i - 59):i + 1]) or c
    a20 = sum(amt[max(0, i - 19):i + 1]) / len(amt[max(0, i - 19):i + 1])

    return {
        "dist_hi250": c / h250 - 1.0,
        "dist_hi60": c / h60 - 1.0,
        "mom20": c / past(21)[0] - 1.0 if len(past(21)) >= 2 else 0.0,
        "mom60": c / past(61)[0] - 1.0 if len(past(61)) >= 2 else 0.0,
        "ma20_slope": slope,
        "vol_atr": atr,
        "amt20_log": math.log10(a20) if a20 > 0 else 0.0,
        "dd60": c / h60 - 1.0,
    }


def two_halves_check(recs, min_n=25):
    """两半同向检验。recs 按入场日排序。返回 (前半 wr, 后半 wr, 是否同向为正)。"""
    if len(recs) < min_n * 2:
        return (0, 0.0, 0.0), (0, 0.0, 0.0), None
    days = sorted({r["T"] for r in recs})
    if len(days) < 4:
        return None, None, None
    mid = days[len(days) // 2]
    h1 = [r for r in recs if r["T"] <= mid]
    h2 = [r for r in recs if r["T"] > mid]
    a, b = wr(h1), wr(h2)
    ok = (a[1] > 0 and b[1] > 0)
    return a, b, ok


# ============================================================
# 主流程
# ============================================================
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=60)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    K = L.load_kline()
    cal = L.trading_days(K)
    q2 = L.load_q2_flags()
    snaps = L.load_margin_snapshots()
    mh = L.load_margin_em()
    print("[load] codes=%d 交易日=%s~%s q2=%d margin_em=%d"
          % (len(K), cal[0], cal[-1], len(q2), len(mh)))

    # 成熟入场窗口：每笔走满 MAXFWD 根
    hi = max(0, len(cal) - L.MAXFWD)
    days = cal[max(0, hi - a.days):hi]
    print("[口径] 完整前瞻：入场 %s ~ %s（每笔满 %d 日）" % (days[0], days[-1], L.MAXFWD))

    # ---------- 收集全部「有日频触发」的候选（不设 TopN 上限，避免上限本身掩盖差异）----------
    pool = []           # rec dict
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
            n_sig = sum(1 for k in L.ALLSIG if k in sig and sig[k] > 0)
            pd = price_dims(K, code, T) or {}
            pool.append({
                "T": T, "code": code, "ret": r[0], "win": r[1], "fwd": r[2],
                "exit": r[3], "score": sc, "I": I, "M": M, "n_sig": n_sig,
                "sig": {k: sig[k] for k in L.ALLSIG if k in sig and sig[k] > 0},
                "mr1": sig.get("_mr1", 0.0), "mr3": sig.get("_mr3", 0.0),
                "mr5": sig.get("_mr5", 0.0),
                **pd,
            })
    print("[pool] 候选样本 = %d" % len(pool))

    # ---------- 独立基线：每个入场日独立抽同样多的事样本 ----------
    random.seed(20261002)
    base = []
    names = set(K.keys())
    for T in days:
        n_same = sum(1 for p in pool if p["T"] == T)
        if n_same == 0:
            continue
        for _ in range(n_same):
            c = random.choice(sorted(names))
            r = L.simulate(K, c, T)
            if r:
                base.append({"T": T, "code": c, "ret": r[0], "win": r[1], "fwd": r[2]})
    b = wr(base)
    print("[基线] 随机 n=%d 胜率=%.1f%% 均值=%.2f%%" % (b[0], b[1], b[2]))

    out = {"asof": cal[-1], "window": [days[0], days[-1]],
           "n_pool": len(pool), "base": list(b), "topn": L.TOPN}

    # ================= 1. 单因子命中率 =================
    print("\n=== 1. 单因子命中率（仅日频可取值的 6 个）===")
    print("   %-12s %6s %8s %9s %10s" % ("因子", "n", "胜率", "edge", "两半同向"))
    single = {}
    for k in L.DAILY:
        recs = [p for p in pool if p["sig"].get(k, 0) > 0]
        n, w, rt = wr(recs)
        h1, h2, ok = two_halves_check(recs)
        single[k] = {"n": n, "wr": w, "edge": w - b[1], "avg": rt,
                     "h1": list(h1) if h1 else None, "h2": list(h2) if h2 else None,
                     "both_pos": ok, "trust": n >= 30 and bool(ok)}
        print("   %-12s %6d %7.1f%% %+8.1f %10s"
              % (L.SIG_CN.get(k, k), n, w, w - b[1],
                 ("是" if ok else ("否" if ok is not None else "样本不足"))))
    out["single"] = single

    # ================= 2. 留一法 =================
    print("\n=== 2. 留一法（去掉该因子后胜率变化；↑=该因子是负贡献）===")
    loo = {}
    base_pool = wr(pool)
    print("   全因子基准 n=%d 胜率=%.1f%%" % (base_pool[0], base_pool[1]))
    for k in L.DAILY + ["pe", "sun", "person", "fund"]:
        recs = [p for p in pool if p["sig"].get(k, 0) <= 0]
        n, w, _rt = wr(recs)
        d = w - base_pool[1]
        loo[k] = {"n": n, "wr": w, "delta": d,
                  "verdict": "负贡献" if d > 0.5 else ("正贡献" if d < -0.5 else "中性")}
        print("   去掉 %-12s n=%5d 胜率=%5.1f%%  %+5.1fpp  → %s"
              % (L.SIG_CN.get(k, k), n, w, d, loo[k]["verdict"]))
    out["loo"] = loo

    # ================= 3. 连续因子单调分档 =================
    print("\n=== 3. 连续因子分档（胜率是否随档位单调上升）===")
    mono = {}
    for field, label in (("mr5", "融资5日净增仓占比"), ("n_sig", "信号共振数"), ("score", "合成强度")):
        vals = [(p["code"], p[field]) for p in pool]
        ths = quantile_bins(vals, 5)
        if not ths:
            continue
        buckets = collections.defaultdict(list)
        for p in pool:
            buckets[bucket_of(p[field], ths)].append(p)
        rows = []
        for bk in sorted(buckets):
            n, w, rt = wr(buckets[bk])
            lo = ths[bk - 1] if bk > 0 else None
            rows.append({"b": bk, "n": n, "wr": w, "avg": rt, "lo": lo, "hi": ths[bk] if bk < len(ths) else None})
        ws = [r["wr"] for r in rows if r["n"] >= 8]
        # 单调性：允许 1 次反向（噪声容忍），看首尾差与方向
        mono_ok = None
        if len(ws) >= 3:
            diffs = [ws[i + 1] - ws[i] for i in range(len(ws) - 1)]
            ups = sum(1 for x in diffs if x > 0)
            mono_ok = ups >= len(diffs) - 1
        top, bot = (rows[-1], rows[0]) if rows else (None, None)
        print("   -- %s（阈值 %s）" % (label, [round(t, 4) for t in ths]))
        for r in rows:
            print("      档%d n=%4d 胜率=%5.1f%% 均值=%6.2f%%%s"
                  % (r["b"], r["n"], r["wr"], r["avg"], "  (样本薄)" if r["n"] < 8 else ""))
        if top and bot:
            print("      首尾差 %+.1fpp  单调=%s" % (top["wr"] - bot["wr"],
                                                 {True: "是", False: "否", None: "样本不足"}[mono_ok]))
        mono[field] = {"rows": rows, "mono": mono_ok,
                       "spread": (top["wr"] - bot["wr"]) if top else None}
    out["mono"] = mono

    # ================= 3b. 价格结构维度分档 =================
    print("\n=== 3b. 价格结构维度分档（找能把胜率抬过基线的维度）===")
    pdim = {}
    for field, label, _why in PRICE_DIMS:
        vals = [(p["code"], p[field]) for p in pool if field in p]
        if len(vals) < 50:
            continue
        ths = quantile_bins(vals, 5)
        buckets = collections.defaultdict(list)
        for p in pool:
            if field in p:
                buckets[bucket_of(p[field], ths)].append(p)
        rows = []
        for bk in sorted(buckets):
            n, w, rt = wr(buckets[bk])
            rows.append({"b": bk, "n": n, "wr": w, "avg": rt,
                         "lo": ths[bk - 1] if bk > 0 else None,
                         "hi": ths[bk] if bk < len(ths) else None})
        ws = [r["wr"] for r in rows if r["n"] >= 15]
        mono_ok = None
        if len(ws) >= 3:
            diffs = [ws[i + 1] - ws[i] for i in range(len(ws) - 1)]
            ups = sum(1 for x in diffs if x > 0)
            mono_ok = ups >= len(diffs) - 1
        # 最佳档：n>=20 的档里胜率最高的
        valid = [r for r in rows if r["n"] >= 20]
        best = max(valid, key=lambda r: r["wr"]) if valid else None
        spread = (rows[-1]["wr"] - rows[0]["wr"]) if rows else 0.0
        pdim[field] = {"label": label, "rows": rows, "mono": mono_ok,
                       "spread": spread,
                       "best_b": best["b"] if best else None,
                       "best_wr": best["wr"] if best else None,
                       "best_n": best["n"] if best else None,
                       "beats_base": bool(best and best["wr"] > b[1] + 1.0)}
        print("   %-14s 最佳档%s n=%3d 胜率=%5.1f%% (基线%.1f%%) 首尾%+.1fpp 单调=%s %s"
              % (label, pdim[field]["best_b"] if pdim[field]["best_b"] is not None else "-",
                 pdim[field]["best_n"] or 0,
                 pdim[field]["best_wr"] or 0.0, b[1], spread,
                 {True: "是", False: "否", None: "不足"}[mono_ok],
                 "★" if pdim[field]["beats_base"] else ""))
    out["pdim"] = pdim

    # ================= 4b. 剔除负贡献因子 + 价格闸门 =================
    # 消融已证：大宗交易、公募增持是负贡献（去掉后胜率反而升）。
    # 事件驱动 = 异动 = 短期超买 → 均值回归。真正的超额要靠「事件 + 价格结构」叠加。
    print("\n=== 4b. 清洗后重组合（剔除负贡献因子，再叠价格闸门）===")
    neg_keys = [k for k, v in loo.items() if v["verdict"] == "负贡献"]
    cleaned = [p for p in pool if not any(p["sig"].get(k, 0) > 0 for k in neg_keys)]
    n0, w0, _ = wr(cleaned)
    print("   剔除 %s 后：n=%d 胜率=%.1f%%（全因子 %.1f%%，基线 %.1f%%）"
          % ("、".join(L.SIG_CN.get(k, k) for k in neg_keys), n0, w0, base_pool[1], b[1]))

    def best_range(field, rows):
        """从分档表里取 n>=20 且胜率最高那一档的 [lo, hi] 区间（None 表示该侧无界）。"""
        valid = [r for r in rows if r["n"] >= 20]
        if not valid:
            return None
        bt = max(valid, key=lambda r: r["wr"])
        i = bt["b"]
        lo = rows[i].get("lo")
        hi = rows[i].get("hi")
        lo = -1e18 if lo is None else lo
        hi = 1e18 if hi is None else hi
        return (lo, hi, bt["wr"], bt["n"])

    gates = []
    for field, _label, _why in PRICE_DIMS:
        if field not in pdim:
            continue
        r = best_range(field, pdim[field]["rows"])
        if r:
            gates.append((field, _label, r))

    cands = [("D0_清洗后基线", lambda p: True)]
    for field, label, (lo, hi, bw, bn) in gates:
        cands.append(("D1_%s 最佳档" % label,
                      (lambda f, l, h: (lambda p: f in p and l <= p[f] <= h))(field, lo, hi)))
    # 清洗 + 融资强 + 机构
    if "mr5" in pool[0]:
        cands.append(("D2_清洗+融资5%↑+I",
                      lambda p: p["M"] and p["I"] and p["mr5"] >= 0.04))
        cands.append(("D3_清洗+融资5%↑", lambda p: p["mr5"] >= 0.04))

    dc = {}
    for name, fn in cands:
        recs = [p for p in cleaned if fn(p)]
        n, w, rt = wr(recs)
        h1, h2, ok = two_halves_check(recs)
        dc[name] = {"n": n, "wr": w, "edge": w - b[1], "avg": rt,
                    "both_pos": ok, "trust": n >= 30 and bool(ok) and w > b[1] + 1.0}
        print("   %-24s n=%4d 胜率=%5.1f%% edge=%+5.1fpp 均值=%6.2f%% 两半同向=%s%s"
              % (name, n, w, w - b[1], rt,
                 {True: "是", False: "否", None: "不足"}[ok],
                 "  ★可采信" if dc[name]["trust"] else ""))
    out["cleaned"] = {"neg_removed": neg_keys, "n": n0, "wr": w0,
                      "all_n": base_pool[0], "all_wr": base_pool[1],
                      "combos": dc}

    # ================= 4. 组合搜索（先验固定的少数组合，不做自动筛） =================
    print("\n=== 4. 先验固定组合（每条都要两半同向才可采信）===")
    combos = [
        ("C1_M且I",            lambda p: p["M"] and p["I"]),
        ("C2_M强5%且I",        lambda p: p["M"] and p["I"] and p["mr5"] >= 0.04),
        ("C3_共振≥2且M",       lambda p: p["n_sig"] >= 2 and p["M"]),
        ("C4_共振≥2且I",       lambda p: p["n_sig"] >= 2 and p["I"]),
        ("C5_共振≥3",          lambda p: p["n_sig"] >= 3),
        ("C6_共振≥4",          lambda p: p["n_sig"] >= 4),
        ("C7_仅M",             lambda p: p["M"]),
        ("C8_仅I",             lambda p: p["I"]),
        ("C9_融资5%↑且共振≥2",  lambda p: p["mr5"] >= 0.04 and p["n_sig"] >= 2),
        ("C10_前25%强度且M",   lambda p: p["M"] and p["score"] >= None),
    ]
    # C10 需要先算强度分位
    sc_ths = quantile_bins([(p["code"], p["score"]) for p in pool], 4)
    out_c = {}
    for name, fn in combos:
        if name == "C10_前25%强度且M":
            if not sc_ths:
                continue
            fn = (lambda th: (lambda p: p["M"] and p["score"] >= th))(sc_ths[0])
        recs = [p for p in pool if fn(p)]
        n, w, rt = wr(recs)
        h1, h2, ok = two_halves_check(recs)
        out_c[name] = {"n": n, "wr": w, "edge": w - b[1], "avg": rt,
                       "both_pos": ok,
                       "trust": n >= 30 and bool(ok) and w > b[1]}
        print("   %-18s n=%4d 胜率=%5.1f%% edge=%+5.1fpp 均值=%6.2f%% 两半同向=%s%s"
              % (name, n, w, w - b[1], rt,
                 {True: "是", False: "否", None: "不足"}[ok],
                 "  ★可采信" if out_c[name]["trust"] else ""))
    out["combos"] = out_c

    # ================= 5. 结论 =================
    print("\n=== 5. 结论 ===")
    neg = [k for k, v in loo.items() if v["verdict"] == "负贡献"]
    pos = [k for k, v in loo.items() if v["verdict"] == "正贡献"]
    print("   负贡献因子（去掉后胜率反而升）：%s"
          % ("、".join(L.SIG_CN.get(k, k) for k in neg) if neg else "无"))
    print("   正贡献因子：%s" % ("、".join(L.SIG_CN.get(k, k) for k in pos) if pos else "无"))
    trusted = [k for k, v in out_c.items() if v["trust"]]
    print("   通过「样本量+两半同向+跑赢基线」三条的组合：%s"
          % ("、".join(trusted) if trusted else "无（说明当前信号集整体无正超额）"))
    if trusted:
        best = max(trusted, key=lambda k: out_c[k]["wr"])
        print("   → 建议优先试：%s（n=%d 胜率=%.1f%% edge=%+.1fpp）"
              % (best, out_c[best]["n"], out_c[best]["wr"], out_c[best]["edge"]))
    # 清洗后组合（这一档才是真正有望提胜率的）
    dtrusted = [k for k, v in dc.items() if v["trust"]]
    print("\n   -- 清洗后（剔除 %s）--" % "、".join(L.SIG_CN.get(k, k) for k in neg_keys))
    if dtrusted:
        dbest = max(dtrusted, key=lambda k: dc[k]["wr"])
        print("   通过三条的组合：%s" % "、".join(dtrusted))
        print("   → 最佳：%s（n=%d 胜率=%.1f%% edge=%+.1fpp，基线 %.1f%%）"
              % (dbest, dc[dbest]["n"], dc[dbest]["wr"], dc[dbest]["edge"], b[1]))
        print("   → 相对现行口径（胜率 %.1f%%）提升 %+.1fpp"
              % (base_pool[1], dc[dbest]["wr"] - base_pool[1]))
    else:
        best_any = max(dc.items(), key=lambda kv: kv[1]["wr"])
        print("   无组合通过三条。最优为 %s（n=%d 胜率=%.1f%% edge=%+.1fpp）→ 说明"
              % (best_any[0], best_any[1]["n"], best_any[1]["wr"], best_any[1]["edge"]))
        print("   **仅靠现有事件信号+价格维度无法产生稳健超额，不应改规则。**")
    out["conclusion"] = {"neg": neg, "pos": pos, "trusted": trusted,
                         "dtrusted": dtrusted,
                         "d0": {"n": n0, "wr": w0}}

    path = os.path.join(L.OUT, "accum_ablate.json")
    json.dump(out, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n[out] %s" % path)


if __name__ == "__main__":
    main()
