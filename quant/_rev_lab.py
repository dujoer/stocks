# -*- coding: utf-8 -*-
"""底部反转 · 特征功效实验室（rev_lab v2）。

问题：旧档位阈值是「照回测胜率手调」出来的 → 样本内过拟合，回测好看、实盘不涨。

科学口径（三处关键设计）：
  A. 目标解耦 —— 前向收益同时记「绝对胜率(wr)」与「相对胜率(bwr=个股前向收益 > 同期宇宙等权中位数)」。
     绝对胜率 = alpha + beta（行情给的）；相对胜率 = 纯选股 alpha。只有 bwr 上的稳定增益才叫「选股能力」。
  B. 时间切分 —— 前 60% 交易日=训练，后 40%=测试；分位切点只用训练集算，再套测试集（无泄漏）。
  C. 无未来信息 walk-forward —— 按月扩窗，每月只用该月之前的数据「筛特征 + 定方向」，报当期真实前向表现；
     并与旧 v3 规则在同一当期 apples-to-apples 对照。特征方向一律按**相对胜率**学，避免把行情方向学进模型。
  D. 横截面分位 —— 十分位在**每个交易日内**排序后聚合（全局排序会把「日期」混进分位，量到的是 beta）。

局限（必须写明）：
  · 种子名单 = 今日基本面快照套历史价格 → 基本面维度有前视偏差，绝对胜率被高估；
    但偏差对所有桶同等作用，**桶间相对 lift 仍有效**，故结论建立在相对 lift 上。
  · 前向 20 日窗口重叠 → 样本非独立；差异显著性按**日期聚类**理解，不做逐票独立性假设。

输出：quant/_rev_lab_result.json、quant/_rev_lab_panel.json、web/reversal/lab.html
"""
from __future__ import annotations
import _txk
import os, sys, json, math, statistics

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rev_pool as R
import _idxkline as E
import _tx_fetch as T

ROOT = R.ROOT
QUANT = R.QUANT
OUTDIR = R.OUTDIR
STEP = 3
MINI = 60
FMAX = 20

# ---- 全市场反转域门槛（v5，2026-09-21 起反转池改全市场） ----
DIST_GATE = -18.0     # 距 52 周高回撤 ≥ 18% 才算「深跌」，进反转候选域
MA60_GUARD = 0.75     # 收盘 < MA60×0.75 = 长期崩塌（飞刀），剔除
AMT_MIN = 3.0e7       # 20 日均成交额下限（元）—— 可交易性下限，剔僵尸票
LIQ_WIN = 20
LAST_UNIVERSE_N = 0   # build_panel 最近一次的宇宙规模（供页面展示）

CONT = ["dist52", "dist_lo20", "dist_lo60", "gap_lo52", "decline_dur", "vol_dry", "vol_expand",
        "vol_day", "accum", "atr_pct", "atr_comp", "clv5", "up10", "slope", "ma20_dev",
        "ma60_dev", "rs20", "rs5", "rsi14", "hist_up", "consec_down", "range20", "mv_log"]
BIN = ["div", "golden", "reclaim", "short_align", "bottom_confirm", "idx_above"]

# ---- 先验固定因子集（方向由经济逻辑给定，不来自回测筛选；v5 起为默认） ----
# 反转经济逻辑三条：①离底部越近（超跌未修复）越好 ②量能越枯竭越好 ③波动/箱体越收敛越好。
# 全部 dir = −1（数值越低越好），等权、不拟合权重。规模因子单列（小市值弹性）。
PRIOR_PRICE = ["dist_lo20", "dist_lo60", "gap_lo52", "vol_dry", "atr_pct", "range20",
               "ma60_dev", "slope"]
PRIOR_SIZE = ["mv_log"]
PRIOR_SET = PRIOR_PRICE + PRIOR_SIZE


# ---------------- 面板 ----------------
def _atr(H, L, C, n, i):
    if i < n:
        return None
    s = 0.0
    for j in range(i - n + 1, i + 1):
        s += max(H[j] - L[j], abs(H[j] - C[j - 1]), abs(L[j] - C[j - 1]))
    return s / n


def _shares_map():
    """用东财业绩快照 netprofit ÷ eps 反推股本 → 历史市值 = 当日收盘 × 股本（约点时，无前视）。

    股本变动（送转/增发）会造成偏差，但：①同一批标的同向作用 ②本因子只在**横截面分位**上使用，
    偏差被同期同域的其他票抵消 → 相对 lift 有效。ep/bp/roe 等按期财报类因子**不纳入**（前视更重）。
    """
    p = os.path.join(QUANT, "fin", "snapshot.json")
    if not os.path.exists(p):
        return {}
    snap = json.load(open(p, encoding="utf-8")).get("stocks", {})
    out = {}
    for c, v in snap.items():
        npf, eps = v.get("netprofit"), v.get("eps")
        if npf and eps and eps > 0:
            out[c] = npf / eps
    return out


def _prefix(arr):
    ps = [0.0]
    for v in arr:
        ps.append(ps[-1] + (v or 0.0))
    return ps


def _rollma(ps, i, n):
    """前缀和滚动均值（O(1)）：均值(arr[i-n+1..i])。i+1 < n 返回 None。"""
    if i + 1 < n:
        return None
    return (ps[i + 1] - ps[i + 1 - n]) / n


def build_panel(step=STEP):
    """全市场反转面板：宇宙 = `_txk_cache.json` 全部可用标的（**不再依赖 220 只种子名单**）。

    硬门槛（进域条件）：距 52 周高回撤 ≥ 18% ＋ 未跌破 MA60×0.75 ＋ 20 日均成交额 ≥ 3000 万。
    只有过门槛的 (标的, 交易日) 才写入面板 —— 域外样本对冲截面排序无意义，且能让面板体量小一个量级。
    """
    cache = _txk.load()
    codes = [c for c in cache if len(cache[c]) >= MINI + FMAX + 5]
    global LAST_UNIVERSE_N
    LAST_UNIVERSE_N = len(codes)
    SH = _shares_map()
    print("[lab] 全市场可用 %d 只（缓存 %d 只）；股本反推命中 %d 只"
          % (len(codes), len(cache), sum(1 for c in codes if c in SH)))

    # 市场代理：全市场等权中位数（自包含）。mk* = 截至当日的过去收益；mkf* = 自当日起的前向收益
    trail, fwd = {}, {}
    for c in codes:
        bars = cache[c]
        for p in range(20, len(bars) - 1):
            d = bars[p]["date"]
            if bars[p - 20]["last"]:
                trail.setdefault(d, []).append(bars[p]["last"] / bars[p - 20]["last"] - 1)
        for p in range(0, len(bars) - FMAX - 1):
            d = bars[p]["date"]
            if bars[p]["last"]:
                fwd.setdefault(d, []).append(bars[p + FMAX]["last"] / bars[p]["last"] - 1)
    mk20 = {d: statistics.median(v) * 100 for d, v in trail.items() if v}
    mkf20 = {d: statistics.median(v) * 100 for d, v in fwd.items() if v}
    print("[lab] 市场代理：过去 %d 日 / 前向 %d 日" % (len(mk20), len(mkf20)))

    idx = E.get_index("sh000001", 200)
    idx_dates = sorted(idx)
    _ist = {}

    def idx_state(d):
        if d in _ist:
            return _ist[d]
        ds = [x for x in idx_dates if x <= d]
        r = None
        if len(ds) >= 21:
            ser = [idx[x] for x in ds]
            ma20 = sum(ser[-20:]) / 20
            ma60 = sum(ser[-60:]) / 60 if len(ser) >= 60 else None
            prev = sum(ser[-25:-5]) / 20 if len(ser) >= 25 else ma20
            r = {"above": ser[-1] > ma20,
                 "dev": (ser[-1] - ma20) / ma20 * 100 if ma20 else 0.0,
                 "slope5": (ma20 - prev) / prev * 100 if prev else 0.0,
                 "above60": (ser[-1] > ma60) if ma60 else None}
        _ist[d] = r
        return r

    rows = []
    for ci, c in enumerate(codes):
        bars = cache[c]
        C = [b["last"] for b in bars]; H = [b["high"] for b in bars]
        L = [b["low"] for b in bars]; O = [b["open"] for b in bars]
        V = [b["volume"] for b in bars]
        u = T.vol_unit(c)
        A = [V[k] * u * C[k] for k in range(len(bars))]     # 成交额（统一口径：元）
        psC, psV, psA = _prefix(C), _prefix(V), _prefix(A)
        pmaxH, pminL = [], []
        mh, ml = -1e18, 1e18
        for k in range(len(bars)):
            mh = max(mh, H[k]); ml = min(ml, L[k])
            pmaxH.append(mh); pminL.append(ml)
        dif, dea = R.macd_series(C)
        hist = [a - b for a, b in zip(dif, dea)]
        rsi = R.rsi_series(C, 14)
        sh = SH.get(c)
        for i in range(MINI, len(bars) - FMAX - 1, step):
            d = bars[i]["date"]
            close = C[i]
            if not close:
                continue
            # —— 前置剪枝：先用最便宜的量判硬门槛，域外样本直接跳过 ——
            h52 = pmaxH[i]
            if not h52:
                continue
            dist52 = (close - h52) / h52 * 100
            if dist52 > DIST_GATE:
                continue
            ma60 = _rollma(psC, i, 60)
            if ma60 is not None and close < ma60 * MA60_GUARD:
                continue
            amt20 = (psA[i + 1] - psA[i + 1 - LIQ_WIN]) / LIQ_WIN
            if amt20 < AMT_MIN:
                continue
            # —— 域内：算全部特征 ——
            cC, cH, cL, cV, cO = C[:i + 1], H[:i + 1], L[:i + 1], V[:i + 1], O[:i + 1]
            l52 = pminL[i]
            lo20, lo60 = min(cL[-20:]), min(cL[-60:])
            ma5, ma10, ma20 = _rollma(psC, i, 5), _rollma(psC, i, 10), _rollma(psC, i, 20)
            ma20p = _rollma(psC, i - 5, 20)
            slope = (ma20 - ma20p) / ma20p * 100 if (ma20 and ma20p) else 0.0
            v20 = (psV[i + 1] - psV[i + 1 - 20]) / 20
            v60 = (psV[i + 1] - psV[i + 1 - 60]) / 60 if i + 1 >= 60 else v20
            v5 = (psV[i + 1] - psV[i + 1 - 5]) / 5
            v15 = (psV[i - 4] - psV[i + 1 - 20]) / 15 if i + 1 >= 20 else v20
            vol_dry = v20 / v60 if v60 else 1.0
            vol_expand = v5 / v15 if v15 else 1.0
            vol_day = cV[-1] / v60 if v60 else 1.0
            accum = sum(1 for k in range(i - 19, i + 1) if cC[k] > cO[k] and cV[k] > v60 * 1.2)
            a20 = _atr(cH, cL, cC, 20, i); a10 = _atr(cH, cL, cC, 10, i); a30 = _atr(cH, cL, cC, 30, i)
            atr_pct = (a20 / close * 100) if a20 else 0.0
            atr_comp = (a10 / a30) if (a10 and a30) else 1.0
            clv5 = 0.0
            for k in range(1, 6):
                if cH[-k] > cL[-k]:
                    clv5 += (cC[-k] - cL[-k]) / (cH[-k] - cL[-k])
            clv5 /= 5.0
            up10 = sum(1 for k in range(1, 11) if cC[-k] > cC[-k - 1]) / 10.0
            div, _ = R.bullish_divergence(cC, dif[:i + 1], window=60)
            golden = dif[i] > dea[i]
            reclaim = ma20 is not None and close > ma20
            short_align = bool(ma5 and ma10 and ma20 and ma5 > ma10 > ma20)
            bottom_confirm = min(cL[-10:]) >= lo20 * 0.985 if len(cL) >= 10 else False
            decline_dur = len(cC) - 1 - cH.index(h52)
            hu = 0
            for k in range(len(hist) - 1, 0, -1):
                if hist[k] > hist[k - 1]:
                    hu += 1
                else:
                    break
            cd = 0
            for k in range(len(cC) - 1, 0, -1):
                if cC[k] < cC[k - 1]:
                    cd += 1
                else:
                    break
            ret20p = (cC[-1] / cC[-21] - 1) * 100 if len(cC) > 21 and cC[-21] else 0.0
            ret5p = (cC[-1] / cC[-6] - 1) * 100 if len(cC) > 6 and cC[-6] else 0.0
            m20 = mk20.get(d)
            rs20 = (ret20p - m20) if m20 is not None else None
            rs5 = (ret5p - mk20.get(d, 0.0)) if m20 is not None else None
            ist = idx_state(d)
            hard = True
            # 旧口径 v3
            def _bv(x, a, b, lo, hi, mx):
                if x is None:
                    return 0.0
                if a <= x <= b:
                    return float(mx)
                if x < a:
                    return float(mx) * (x - lo) / (a - lo) if a > lo else 0.0
                return float(mx) * (hi - x) / (hi - b) if hi > b else 0.0
            s_mat = 12.0 if decline_dur >= 60 else (9.0 if decline_dur >= 40 else (5.0 if decline_dur >= 25 else 2.0))
            s_acc = 14.0 if accum >= 6 else (9.0 if accum >= 4 else (4.0 if accum >= 2 else 0.0))
            s_div = 18.0 if div is True else (10.0 if div == "weak" else 0.0)
            s_ma = 0.0
            if reclaim and slope > 0 and short_align:
                s_ma = 20.0
            elif reclaim and slope > 0:
                s_ma = 15.0
            elif reclaim:
                s_ma = 10.0
            elif slope > 0:
                s_ma = 6.0
            total = (_bv(dist52, -45, -25, -10, -5, 22) + s_mat + _bv(vol_dry, 0.55, 0.8, 0.95, 1.15, 14)
                     + s_acc + s_div + s_ma)
            if not hard:
                tier_v3 = "C"
            elif (total >= 50 and (div is True or div == "weak" or reclaim)
                  and vol_dry <= 0.95 and (accum >= 2 or golden)):
                tier_v3 = "A"
            elif total >= 45 and (div is True or div == "weak" or reclaim) and vol_dry <= 1.05:
                tier_v3 = "B"
            else:
                tier_v3 = "C"
            ret20 = (C[i + FMAX] / close - 1) * 100
            ret10 = (C[i + 10] / close - 1) * 100
            ret5 = (C[i + 5] / close - 1) * 100
            mf = mkf20.get(d)
            rel20 = (ret20 - mf) if mf is not None else None
            sh = SH.get(c)
            mv = (close * sh) if sh else None
            rows.append({
                "code": c, "date": d, "hard": hard,
                "v3": {"score": round(total, 1), "tier": tier_v3},
                "f": {
                    "dist52": dist52, "decline_dur": decline_dur,
                    "dist_lo20": (close / lo20 - 1) * 100, "dist_lo60": (close / lo60 - 1) * 100,
                    "gap_lo52": (close - l52) / l52 * 100 if l52 else 0.0,
                    "vol_dry": vol_dry, "vol_expand": vol_expand, "vol_day": vol_day,
                    "accum": accum, "atr_pct": atr_pct, "atr_comp": atr_comp,
                    "clv5": clv5, "up10": up10, "slope": slope,
                    "ma20_dev": ((close - ma20) / ma20 * 100) if ma20 else 0.0,
                    "ma60_dev": ((close - ma60) / ma60 * 100) if ma60 else 0.0,
                    "rs20": rs20, "rs5": rs5, "rsi14": rsi[i], "hist_up": hu,
                    "consec_down": cd, "range20": (max(cH[-20:]) - min(cL[-20:])) / close * 100,
                    "mv_log": (math.log(mv) if (mv and mv > 0) else None),
                    "div": 1.0 if div is True else (0.5 if div == "weak" else 0.0),
                    "golden": 1.0 if golden else 0.0, "reclaim": 1.0 if reclaim else 0.0,
                    "short_align": 1.0 if short_align else 0.0,
                    "bottom_confirm": 1.0 if bottom_confirm else 0.0,
                    "idx_above": (1.0 if ist["above"] else 0.0) if ist else None,
                    "idx_dev": ist["dev"] if ist else None,
                    "idx_slope5": ist["slope5"] if ist else None,
                },
                "y": {"ret5": ret5, "ret10": ret10, "ret20": ret20, "win20": 1 if ret20 > 0 else 0,
                      "rel20": rel20, "beat20": (1 if (rel20 is not None and rel20 > 0) else 0) if rel20 is not None else None,
                      "mae": (min(L[i + 1:i + FMAX + 1]) / close - 1) * 100,
                      "mfe": (max(H[i + 1:i + FMAX + 1]) / close - 1) * 100},
            })
        if len(rows) % 4000 < step * 4:
            print("[lab] 面板 %d 行…" % len(rows))
    print("[lab] 面板完成 %d 行" % len(rows))
    return rows


# ---------------- 统计工具 ----------------
def _wr(rows):
    if not rows:
        return {"n": 0, "wr": 0.0, "bwr": 0.0, "mean": 0.0, "rmean": 0.0, "mae": 0.0, "nb": 0}
    n = len(rows)
    b = [r for r in rows if r["y"].get("beat20") is not None]
    return {"n": n,
            "wr": sum(r["y"]["win20"] for r in rows) / n * 100,
            "mean": sum(r["y"]["ret20"] for r in rows) / n,
            "mae": sum(r["y"]["mae"] for r in rows) / n,
            "nb": len(b),
            "bwr": (sum(r["y"]["beat20"] for r in b) / len(b) * 100) if b else 0.0,
            "rmean": (sum(r["y"]["rel20"] for r in b) / len(b)) if b else 0.0}


def _mono(buckets, key="bwr"):
    ws = [b[key] for b in buckets if b and b["n"] >= 40 and b["nb"] >= 30]
    if len(ws) < 3:
        return 0
    ups = sum(1 for a, b in zip(ws, ws[1:]) if b > a)
    dns = sum(1 for a, b in zip(ws, ws[1:]) if b < a)
    if ups >= len(ws) - 2:
        return 1
    if dns >= len(ws) - 2:
        return -1
    return 0


def _universe_n(rows):
    """面板复用（不重算 build_panel）时也要正确报出宇宙规模。

    优先用 build_panel 记下的 LAST_UNIVERSE_N；否则按 run 口径现算（读日K缓存计长度）。
    """
    if LAST_UNIVERSE_N:
        return LAST_UNIVERSE_N
    try:
        cache = _txk.load()
        n = sum(1 for c in cache if len(cache[c]) >= MINI + FMAX + 5)
        del cache
        return n
    except Exception:
        return len({r["code"] for r in rows})


def analyse(rows, q=5):
    hr = [r for r in rows if r["hard"] and r["y"].get("beat20") is not None]
    ds = sorted({r["date"] for r in hr})
    cut = ds[int(len(ds) * 0.6)]
    tr = [r for r in hr if r["date"] < cut]
    te = [r for r in hr if r["date"] >= cut]
    print("[lab] 训练 %d 行(至 %s) | 测试 %d 行(自 %s)" % (len(tr), cut, len(te), cut))
    feats = []
    for name in CONT:
        vals = [r["f"][name] for r in tr if r["f"].get(name) is not None]
        if len(vals) < 300:
            continue
        sv = sorted(vals)
        cuts = [sv[int(len(sv) * k / q)] for k in range(1, q)]

        def bucket(rws):
            out = []
            for bi in range(q):
                lo = cuts[bi - 1] if bi > 0 else None
                hi = cuts[bi] if bi < q - 1 else None
                sel = []
                for r in rws:
                    v = r["f"].get(name)
                    if v is None:
                        continue
                    if (lo is not None and v < lo) or (hi is not None and v >= hi):
                        continue
                    sel.append(r)
                out.append(_wr(sel))
            return out
        btr, bte = bucket(tr), bucket(te)
        mtr, mte = _mono(btr), _mono(bte)
        good = [b for b in bte if b["nb"] >= 40]
        feats.append({"name": name, "kind": "cont", "cuts": cuts, "train": btr, "test": bte,
                      "mono_train": mtr, "mono_test": mte,
                      "spread_rel_train": (max(b["bwr"] for b in btr if b["nb"] >= 40) - min(b["bwr"] for b in btr if b["nb"] >= 40)) if len([b for b in btr if b["nb"] >= 40]) >= 2 else 0,
                      "spread_rel_test": (max(b["bwr"] for b in good) - min(b["bwr"] for b in good)) if len(good) >= 2 else 0,
                      "stable": bool(mtr != 0 and mtr == mte)})
    for name in BIN:
        def grp(rws, v):
            return [r for r in rws if r["f"].get(name) == v]
        one_tr, one_te = grp(tr, 1.0), grp(te, 1.0)
        zer_tr, zer_te = grp(tr, 0.0), grp(te, 0.0)
        if len(one_tr) < 150 or len(one_te) < 80 or len(zer_tr) < 150 or len(zer_te) < 80:
            continue
        w1t, w1s, w0t, w0s = _wr(one_tr), _wr(one_te), _wr(zer_tr), _wr(zer_te)
        feats.append({"name": name, "kind": "bin",
                      "train": [{"v": 0, **w0t}, {"v": 1, **w1t}],
                      "test": [{"v": 0, **w0s}, {"v": 1, **w1s}],
                      "lift_rel_train": w1t["bwr"] - w0t["bwr"],
                      "lift_rel_test": w1s["bwr"] - w0s["bwr"],
                      "mono_train": 1 if w1t["bwr"] > w0t["bwr"] else -1,
                      "mono_test": 1 if w1s["bwr"] > w0s["bwr"] else -1,
                      "stable": (w1t["bwr"] > w0t["bwr"]) == (w1s["bwr"] > w0s["bwr"])})
    return {"cut_date": cut, "n_train": len(tr), "n_test": len(te),
            "base_train": _wr(tr), "base_test": _wr(te),
            "base_train_A": _wr([r for r in tr if r["v3"]["tier"] == "A"]),
            "base_test_A": _wr([r for r in te if r["v3"]["tier"] == "A"]),
            "features": feats,
            "stable": [f["name"] for f in feats if f["stable"] and f["name"] != "bottom_confirm"]}


# ---------------- 组合（日内横截面分位，等权，不拟合权重） ----------------
def composite(rows, use, direction):
    hr = [r for r in rows if r["hard"] and r["y"].get("beat20") is not None]
    bydate = {}
    for r in hr:
        bydate.setdefault(r["date"], []).append(r)
    scored = []
    for d, rs in bydate.items():
        if len(rs) < 25:
            continue
        rk = {f: {} for f in use}
        for f in use:
            vals = sorted([(r["f"].get(f), r["code"]) for r in rs if r["f"].get(f) is not None])
            n = len(vals)
            if n < 5:
                continue
            for pos, (v, c) in enumerate(vals):
                rk[f][c] = pos / (n - 1) if n > 1 else 0.5
        for r in rs:
            tot, cnt = 0.0, 0
            for f in use:
                v = rk[f].get(r["code"])
                if v is None:
                    continue
                tot += (v if direction[f] > 0 else 1 - v)
                cnt += 1
            if cnt >= max(2, len(use) // 2):
                r2 = dict(r); r2["q"] = tot / cnt
                scored.append(r2)
    ds = sorted({r["date"] for r in scored})
    cut = ds[int(len(ds) * 0.6)]
    # 日内十分位
    for r in scored:
        bydate[r["date"]].append(r) if False else None

    def deciles(rws):
        byd = {}
        for r in rws:
            byd.setdefault(r["date"], []).append(r)
        buckets = [[] for _ in range(10)]
        for d, rs in byd.items():
            if len(rs) < 10:
                continue
            rs = sorted(rs, key=lambda x: x["q"])
            for k in range(10):
                buckets[k] += rs[int(len(rs) * k / 10):int(len(rs) * (k + 1) / 10)]
        return [_wr(b) for b in buckets]
    tr = [r for r in scored if r["date"] < cut]
    te = [r for r in scored if r["date"] >= cut]
    return {"n": len(scored), "cut_date": cut,
            "train_deciles": deciles(tr), "test_deciles": deciles(te),
            "train": _wr(tr), "test": _wr(te)}


# ---------------- 无未来信息 walk-forward ----------------
def walkforward(rows, months=6, min_spread=5.0):
    hr = [r for r in rows if r["hard"] and r["y"].get("beat20") is not None]
    ds = sorted({r["date"] for r in hr})
    start = int(len(ds) * 0.25)
    seg = max(10, (len(ds) - start) // months)
    out = []
    for m in range(months):
        lo = start + m * seg
        hi = min(len(ds), start + (m + 1) * seg)
        if hi - lo < 5 or lo >= len(ds):
            continue
        hi_cmp = ds[hi] if hi < len(ds) else "9999"
        past = [r for r in hr if r["date"] < ds[lo]]
        cur = [r for r in hr if ds[lo] <= r["date"] < hi_cmp]
        if len(past) < 400 or len(cur) < 60:
            continue
        use, dirs = {}, {}
        for f in CONT + BIN:
            pv = [r["f"].get(f) for r in past if r["f"].get(f) is not None]
            if len(pv) < 300 or len(set(pv)) < 2:
                continue
            sv = sorted(pv)
            a, b = sv[len(sv) // 3], sv[2 * len(sv) // 3]
            if a == b:      # 离散取值集中（如 0/1 二值）→ 直接组对组比较
                g0 = [r for r in past if r["f"].get(f) == 0.0]
                g2 = [r for r in past if r["f"].get(f) == 1.0]
                if len(g0) < 80 or len(g2) < 80:
                    continue
                sp = _wr(g2)["bwr"] - _wr(g0)["bwr"]
                if abs(sp) < min_spread:
                    continue
                use[f] = (0.5, 0.5)
                dirs[f] = 1 if sp > 0 else -1
                continue
            g0 = [r for r in past if r["f"].get(f) is not None and r["f"][f] < a]
            g2 = [r for r in past if r["f"].get(f) is not None and r["f"][f] >= b]
            if len(g0) < 80 or len(g2) < 80:
                continue
            sp = _wr(g2)["bwr"] - _wr(g0)["bwr"]
            if abs(sp) < min_spread:
                continue
            use[f] = (a, b)
            dirs[f] = 1 if sp > 0 else -1
        if len(use) < 3:
            continue

        def pts(r):
            tot, cnt = 0.0, 0
            for f, (a, b) in use.items():
                v = r["f"].get(f)
                if v is None:
                    continue
                p = 0.0 if v < a else (0.5 if v < b else 1.0)
                tot += (p if dirs[f] > 0 else 1 - p)
                cnt += 1
            return tot / cnt if cnt else None

        sc = [(pts(r), r) for r in cur]
        sc = [(p, r) for p, r in sc if p is not None]
        if len(sc) < 50:
            continue
        sc.sort(key=lambda x: -x[0])
        k = max(1, len(sc) // 5)
        top = [r for _, r in sc[:k]]
        allc = [r for _, r in sc]
        A = [r for r in cur if r["v3"]["tier"] == "A"]
        out.append({"period": "%s ~ %s" % (ds[lo], ds[hi - 1]), "feats": len(use),
                    "feat_names": sorted(use), "feat_dirs": dict(dirs),
                    "n_all": len(allc), "wr_all": _wr(allc)["wr"], "bwr_all": _wr(allc)["bwr"],
                    "mean_all": _wr(allc)["mean"],
                    "n_top": len(top), "wr_top": _wr(top)["wr"], "bwr_top": _wr(top)["bwr"],
                    "mean_top": _wr(top)["mean"], "rmean_top": _wr(top)["rmean"],
                    "n_A": len(A), "wr_A": _wr(A)["wr"], "bwr_A": _wr(A)["bwr"]})
    got = [o for o in out if o["n_top"] >= 30]
    agg = {}
    if got:
        gp = [o for o in got if o["n_A"] >= 10]
        agg = {"n_periods": len(got),
               "wr_all": sum(o["wr_all"] for o in got) / len(got),
               "wr_top": sum(o["wr_top"] for o in got) / len(got),
               "bwr_all": sum(o["bwr_all"] for o in got) / len(got),
               "bwr_top": sum(o["bwr_top"] for o in got) / len(got),
               "mean_top": sum(o["mean_top"] for o in got) / len(got),
               "wr_A": (sum(o["wr_A"] for o in gp) / len(gp)) if gp else None,
               "bwr_A": (sum(o["bwr_A"] for o in gp) / len(gp)) if gp else None,
               "n_A_periods": len(gp),
               "win_periods_top": sum(1 for o in got if o["bwr_top"] > o["bwr_all"]),
               "win_periods_A": sum(1 for o in gp if o["wr_A"] > o["wr_all"]) if gp else 0}
    return out, agg


def date_market():
    """日级市场状态（只用当日及之前的信息，实盘 scan 时可算）：全市场等权中位 20 日收益 + 广度(close>MA20 占比)。"""
    cache = _txk.load()
    codes = list(cache.keys())
    byd = {}
    for c in codes:
        C = [b["last"] for b in cache[c]]
        for p in range(20, len(C)):
            if not C[p] or not C[p - 20]:
                continue
            ma20 = sum(C[p - 19:p + 1]) / 20
            byd.setdefault(cache[c][p]["date"], []).append(
                (C[p] / C[p - 20] - 1, 1 if C[p] > ma20 else 0))
    return {d: {"mkt20": statistics.median(x[0] for x in v) * 100,
                "breadth": sum(x[1] for x in v) / len(v) * 100}
            for d, v in byd.items() if v}


def regime_edge(rows, use, direction):
    """在「日级市场状态」分桶内，比较组合 top20% 与基线的相对胜率 → 得环境门控阈值。"""
    mkt = date_market()
    hr = [r for r in rows if r["hard"] and r["y"].get("beat20") is not None and r["date"] in mkt]
    bydate = {}
    for r in hr:
        bydate.setdefault(r["date"], []).append(r)
    scored = []
    for d, rs in bydate.items():
        if len(rs) < 25:
            continue
        rk = {f: {} for f in use}
        for f in use:
            vals = sorted([(r["f"].get(f), r["code"]) for r in rs if r["f"].get(f) is not None])
            if len(vals) < 5:
                continue
            for pos, (v, c) in enumerate(vals):
                rk[f][c] = pos / (len(vals) - 1)
        for r in rs:
            tot, cnt = 0.0, 0
            for f in use:
                v = rk[f].get(r["code"])
                if v is None:
                    continue
                tot += (v if direction[f] > 0 else 1 - v)
                cnt += 1
            if cnt >= max(2, len(use) // 2):
                r2 = dict(r); r2["q"] = tot / cnt
                r2["_mkt20"] = mkt[d]["mkt20"]
                r2["_breadth"] = mkt[d]["breadth"]
                scored.append(r2)
    defs = [("mkt20", [(-1e9, -3), (-3, 0), (0, 3), (3, 1e9)],
             ["宇宙中位20日 < −3%", "−3%~0%", "0%~+3%", "> +3%"]),
            ("breadth", [(-1e9, 30), (30, 50), (50, 70), (70, 1e9)],
             ["广度 <30%", "30~50%", "50~70%", ">70%"])]
    out = []
    for key, ranges, labels in defs:
        for (lo, hi), lab in zip(ranges, labels):
            sub = [r for r in scored if lo <= r["_"+key] < hi]
            if len(sub) < 120:
                continue
            byd = {}
            for r in sub:
                byd.setdefault(r["date"], []).append(r)
            top, allc = [], []
            for d, rs in byd.items():
                if len(rs) < 10:
                    continue
                rs = sorted(rs, key=lambda x: -x["q"])
                top += rs[:max(1, len(rs) // 5)]
                allc += rs
            if len(top) < 40:
                continue
            wt, wa = _wr(top), _wr(allc)
            out.append({"var": key, "bucket": lab, "n": len(allc), "n_top": len(top),
                        "bwr_top": wt["bwr"], "bwr_all": wa["bwr"],
                        "wr_top": wt["wr"], "wr_all": wa["wr"],
                        "mean_top": wt["mean"], "mae_top": wt["mae"],
                        "edge_rel": wt["bwr"] - wa["bwr"], "edge_abs": wt["wr"] - wa["wr"]})
    return out


def _learn_feats(sample, min_spread=5.0):
    """只用一个样本段「筛特征 + 定方向」（按相对胜率三分组差），返回 (use, dirs)。"""
    use, dirs = {}, {}
    for f in CONT + BIN:
        pv = sorted([r["f"][f] for r in sample if r["f"].get(f) is not None])
        if len(pv) < 300 or len(set(pv)) < 2:
            continue
        a, b = pv[len(pv) // 3], pv[2 * len(pv) // 3]
        if a == b:
            g0 = [r for r in sample if r["f"].get(f) == 0.0]
            g2 = [r for r in sample if r["f"].get(f) == 1.0]
            if len(g0) < 80 or len(g2) < 80:
                continue
            sp = _wr(g2)["bwr"] - _wr(g0)["bwr"]
            if abs(sp) < min_spread:
                continue
            use[f] = (0.5, 0.5); dirs[f] = 1 if sp > 0 else -1
            continue
        g0 = [r for r in sample if r["f"].get(f) is not None and r["f"][f] < a]
        g2 = [r for r in sample if r["f"].get(f) is not None and r["f"][f] >= b]
        if len(g0) < 80 or len(g2) < 80:
            continue
        sp = _wr(g2)["bwr"] - _wr(g0)["bwr"]
        if abs(sp) < min_spread:
            continue
        use[f] = (a, b); dirs[f] = 1 if sp > 0 else -1
    return use, dirs


def _select_top(sample, use, dirs, pct=0.2):
    """日内横截面分位排序，返回 (每日前 pct 的行, 全部行)。"""
    byd = {}
    for r in sample:
        byd.setdefault(r["date"], []).append(r)
    top, allc = [], []
    for d, rs in byd.items():
        if len(rs) < 10:
            continue
        rk = {}
        for f in use:
            vals = sorted([(r["f"].get(f), r["code"]) for r in rs if r["f"].get(f) is not None])
            if len(vals) < 5:
                continue
            for pos, (v, c) in enumerate(vals):
                rk.setdefault(c, {})[f] = pos / (len(vals) - 1)
        scored = []
        for r in rs:
            tot, cnt = 0.0, 0
            for f in use:
                v = rk.get(r["code"], {}).get(f)
                if v is None:
                    continue
                tot += (v if dirs[f] > 0 else 1 - v); cnt += 1
            if cnt >= max(2, len(use) // 2):
                scored.append((tot / cnt, r))
        if len(scored) < 10:
            continue
        scored.sort(key=lambda x: -x[0])
        k = max(1, int(round(len(scored) * pct)))
        top += [r for _, r in scored[:k]]
        allc += [r for _, r in scored]
    return top, allc


def _rank_top(sample, use, dirs, pct=0.2):
    """日内横截面分位排序，取每日前 pct 组成组合，与全体对照。"""
    top, allc = _select_top(sample, use, dirs, pct)
    if len(top) < 40:
        return None
    wt, wa = _wr(top), _wr(allc)
    return {"n": len(allc), "n_top": len(top), "wr_top": wt["wr"], "bwr_top": wt["bwr"],
            "wr_all": wa["wr"], "bwr_all": wa["bwr"], "mean_top": wt["mean"], "mae_top": wt["mae"],
            "edge_rel": wt["bwr"] - wa["bwr"], "edge_abs": wt["wr"] - wa["wr"]}


def strict_oos(rows, pct=0.2):
    """严格样本外对照：①先验固定集（不筛，直接套测试段） ②自动筛（训练段学→测试段用）
    ③全量筛（含测试段，前视）—— ②−③ 的差额即「自动挑因子」这个动作制造的噪声量。"""
    hr = [r for r in rows if r["hard"] and r["y"].get("beat20") is not None]
    ds = sorted({r["date"] for r in hr})
    cut = ds[int(len(ds) * 0.6)]
    tr = [r for r in hr if r["date"] < cut]
    te = [r for r in hr if r["date"] >= cut]
    prior = {f: -1 for f in PRIOR_SET}
    out = {"cut_date": cut, "n_train": len(tr), "n_test": len(te),
           "prior_feats": list(PRIOR_SET),
           "prior": _rank_top(te, prior, prior, pct)}
    u2, d2 = _learn_feats(tr)
    out["auto_strict_feats"] = sorted(u2)
    out["auto_strict"] = _rank_top(te, u2, d2, pct) if len(u2) >= 3 else None
    u3, d3 = _learn_feats(hr)
    out["auto_insample_feats"] = sorted(u3)
    out["auto_insample"] = _rank_top(hr, u3, d3, pct) if len(u3) >= 3 else None
    if out["auto_strict"] and out["auto_insample"]:
        out["gap"] = out["auto_insample"]["edge_rel"] - out["auto_strict"]["edge_rel"]
    else:
        out["gap"] = None
    out["overlap"] = sorted(set(u2) & set(u3))
    return out


def _as_dir(use):
    """把「因子列表」或「{因子: 方向}」统一成 dict。"""
    if isinstance(use, dict):
        return dict(use)
    return {f: -1 for f in (use or PRIOR_SET)}


def topn_curve(rows, use=None, direction=None):
    """先验固定集在不同截断比例下的测试段表现 → 用于决定 A 档取前多少。"""
    use = _as_dir(use)
    direction = _as_dir(direction or use)
    hr = [r for r in rows if r["hard"] and r["y"].get("beat20") is not None]
    ds = sorted({r["date"] for r in hr})
    cut = ds[int(len(ds) * 0.6)]
    te = [r for r in hr if r["date"] >= cut]
    out = []
    for p in (0.05, 0.10, 0.15, 0.20, 0.30):
        r = _rank_top(te, use, direction, p)
        if r:
            r["pct"] = p
            out.append(r)
    return out


def regime_gate(rows, use=None, direction=None):
    """按日级广度三档，看先验固定集前 10% 的绝对/相对胜率 → 定仓位系数。"""
    use = _as_dir(use)
    direction = _as_dir(direction or use)
    mkt = date_market()
    hr = [r for r in rows if r["hard"] and r["y"].get("beat20") is not None and r["date"] in mkt]
    byd = {}
    for r in hr:
        byd.setdefault(r["date"], []).append(r)
    scored = []
    for d, rs in byd.items():
        if len(rs) < 25:
            continue
        rk = {}
        for f in use:
            vals = sorted([(r["f"].get(f), r["code"]) for r in rs if r["f"].get(f) is not None])
            if len(vals) < 5:
                continue
            for pos, (v, c) in enumerate(vals):
                rk.setdefault(c, {})[f] = pos / (len(vals) - 1)
        for r in rs:
            tot, cnt = 0.0, 0
            for f in use:
                v = rk.get(r["code"], {}).get(f)
                if v is None:
                    continue
                tot += (v if direction[f] > 0 else 1 - v); cnt += 1
            if cnt >= max(2, len(use) // 2):
                r2 = dict(r); r2["q"] = tot / cnt
                r2["_br"] = mkt[d]["breadth"]; r2["_mkt"] = mkt[d]["mkt20"]
                scored.append(r2)
    out = []
    for lo, hi, lab, coef in ((0, 35, "防守 · 广度<35%", 0.4),
                              (35, 55, "中性 · 广度35~55%", 0.7),
                              (55, 101, "进攻 · 广度≥55%", 1.0)):
        sub = [r for r in scored if lo <= r["_br"] < hi]
        if len(sub) < 120:
            continue
        bd = {}
        for r in sub:
            bd.setdefault(r["date"], []).append(r)
        top, allc = [], []
        for d, rs in bd.items():
            if len(rs) < 10:
                continue
            rs = sorted(rs, key=lambda x: -x["q"])
            top += rs[:max(1, int(round(len(rs) * 0.1)))]
            allc += rs
        if len(top) < 40:
            continue
        wt, wa = _wr(top), _wr(allc)
        out.append({"bucket": lab, "coef": coef, "n": len(allc), "n_top": len(top),
                    "bwr_top": wt["bwr"], "bwr_all": wa["bwr"], "wr_top": wt["wr"],
                    "wr_all": wa["wr"], "mean_top": wt["mean"], "mae_top": wt["mae"],
                    "edge_rel": wt["bwr"] - wa["bwr"], "edge_abs": wt["wr"] - wa["wr"]})
    return out


def _apply_exit(rows, stop, take, maxfwd=FMAX):
    """保守「止损优先」近似：先看 MAE 是否触发止损，再看 MFE 是否够目标，否则持到 maxfwd。

    take=0 表示不止盈（只留止损 + 时间止损）。忽略移动止盈与路径先后 → 对**所有规则同等保守**，
    故规则间相对比较有效，绝对值偏保守。
    """
    vals = []
    for r in rows:
        y = r["y"]
        mae, mfe, ret = y.get("mae"), y.get("mfe"), y.get("ret20")
        if mae is None or mfe is None or ret is None:
            continue
        if mae <= -stop:
            vals.append(-stop)
        elif take > 0 and mfe >= take:
            vals.append(take)
        else:
            vals.append(ret)
    if len(vals) < 40:
        return None
    return {"n": len(vals),
            "wr": sum(1 for v in vals if v > 0) / len(vals) * 100,
            "mean": sum(vals) / len(vals)}


def exit_lab(rows, pct=0.10):
    """退出规则样本外对照（域内 top pct，先验固定集）。

    A. 持有期 T+5 / T+10 / T+20 的绝对胜率 → 回答「该持多久」
    B. 止损 × 目标网格 → 可兑现胜率（止损优先，保守）
    规则在训练半挑、测试半验证；两半同向才算可用。
    """
    use = _as_dir(None)
    hr = [r for r in rows if r["hard"] and r["y"].get("beat20") is not None]
    ds = sorted({r["date"] for r in hr})
    cut = ds[int(len(ds) * 0.6)]
    out = {"cut_date": cut, "pct": pct}
    for half, part in (("train", [r for r in hr if r["date"] < cut]),
                       ("test", [r for r in hr if r["date"] >= cut])):
        top, allc = _select_top(part, use, use, pct)
        hz = []
        for n in (5, 10, 20):
            k = "ret%d" % n
            v = [r["y"][k] for r in top if r["y"].get(k) is not None]
            a = [r["y"][k] for r in allc if r["y"].get(k) is not None]
            if not v:
                continue
            hz.append({"h": n, "n": len(v),
                       "wr": sum(1 for x in v if x > 0) / len(v) * 100,
                       "mean": sum(v) / len(v),
                       "wr_all": (sum(1 for x in a if x > 0) / len(a) * 100) if a else None,
                       "mean_all": (sum(a) / len(a)) if a else None})
        grid = []
        for stop in (6.0, 8.0, 10.0, 12.0, 15.0):
            for take in (0.0, 8.0, 10.0, 12.0, 15.0, 20.0):
                r = _apply_exit(top, stop, take)
                if r:
                    r.update({"stop": stop, "take": take})
                    grid.append(r)
        out[half] = {"n_top": len(top), "horizons": hz, "grid": grid}
    return out


def oos_rank(rows, min_spread=5.0):
    """跨期方向迁移：在一个时期学「特征+方向」（用相对胜率三分组差），套到另一个时期做日内分位排序。
    两向都做——尤其「用上行期学 → 套弱势期」是检验因子是否只是 beta 的硬测试。"""
    hr = [r for r in rows if r["hard"] and r["y"].get("beat20") is not None]
    ds = sorted({r["date"] for r in hr})
    cut = ds[int(len(ds) * 0.6)]
    first = [r for r in hr if r["date"] < cut]     # 2025-09~2026-06 弱/震荡
    last = [r for r in hr if r["date"] >= cut]     # 2026-06~09 上行

    def learn(sample):
        use, dirs = {}, {}
        for f in CONT + BIN:
            pv = sorted([r["f"][f] for r in sample if r["f"].get(f) is not None])
            if len(pv) < 300 or len(set(pv)) < 2:
                continue
            a, b = pv[len(pv) // 3], pv[2 * len(pv) // 3]
            if a == b:
                g0 = [r for r in sample if r["f"].get(f) == 0.0]
                g2 = [r for r in sample if r["f"].get(f) == 1.0]
                if len(g0) < 80 or len(g2) < 80:
                    continue
                sp = _wr(g2)["bwr"] - _wr(g0)["bwr"]
                if abs(sp) < min_spread:
                    continue
                use[f] = (0.5, 0.5); dirs[f] = 1 if sp > 0 else -1
                continue
            g0 = [r for r in sample if r["f"].get(f) is not None and r["f"][f] < a]
            g2 = [r for r in sample if r["f"].get(f) is not None and r["f"][f] >= b]
            if len(g0) < 80 or len(g2) < 80:
                continue
            sp = _wr(g2)["bwr"] - _wr(g0)["bwr"]
            if abs(sp) < min_spread:
                continue
            use[f] = (a, b); dirs[f] = 1 if sp > 0 else -1
        return use, dirs

    def apply_rank(sample, use, dirs):
        """日内分位排序（相对口径），取 top20% vs 全体。"""
        byd = {}
        for r in sample:
            byd.setdefault(r["date"], []).append(r)
        top, allc = [], []
        for d, rs in byd.items():
            if len(rs) < 10:
                continue
            rk = {}
            for f in use:
                vals = sorted([(r["f"].get(f), r["code"]) for r in rs if r["f"].get(f) is not None])
                if len(vals) < 5:
                    continue
                for pos, (v, c) in enumerate(vals):
                    rk.setdefault(c, {})[f] = pos / (len(vals) - 1)
            scored = []
            for r in rs:
                tot, cnt = 0.0, 0
                for f in use:
                    v = rk.get(r["code"], {}).get(f)
                    if v is None:
                        continue
                    tot += (v if dirs[f] > 0 else 1 - v); cnt += 1
                if cnt >= max(2, len(use) // 2):
                    scored.append((tot / cnt, r))
            if len(scored) < 10:
                continue
            scored.sort(key=lambda x: -x[0])
            top += [r for _, r in scored[:max(1, len(scored) // 5)]]
            allc += [r for _, r in scored]
        if len(top) < 40:
            return None
        wt, wa = _wr(top), _wr(allc)
        return {"n": len(allc), "n_top": len(top), "bwr_top": wt["bwr"], "bwr_all": wa["bwr"],
                "wr_top": wt["wr"], "wr_all": wa["wr"], "mean_top": wt["mean"],
                "mae_top": wt["mae"], "edge_rel": wt["bwr"] - wa["bwr"], "edge_abs": wt["wr"] - wa["wr"]}

    out = []
    for nm, tr_s, te_s in (("弱市学→强市用", first, last), ("强市学→弱市用", last, first)):
        use, dirs = learn(tr_s)
        if len(use) < 3:
            out.append({"pair": nm, "feats": len(use), "result": None})
            continue
        out.append({"pair": nm, "feats": len(use), "feat_names": sorted(use),
                    "result": apply_rank(te_s, use, dirs)})
    return out


def consensus(res, wf):
    """共识特征表：①walk-forward 期被自动选中的次数（≥4/6 入选）②二值特征按训练/测试同向且 lift≥4pp 入选。"""
    out = []
    for f in CONT:
        n = sum(1 for o in wf if f in o.get("feat_dirs", {}))
        if n < 4:
            continue
        pos = sum(1 for o in wf if o.get("feat_dirs", {}).get(f) == 1)
        neg = sum(1 for o in wf if o.get("feat_dirs", {}).get(f) == -1)
        out.append({"name": f, "kind": "cont", "wf_count": n, "dir": 1 if pos >= neg else -1,
                    "wf_pos": pos, "wf_neg": neg})
    for f in res["features"]:
        if f["kind"] != "bin":
            continue
        lt, ls = f.get("lift_rel_train"), f.get("lift_rel_test")
        if lt is None or ls is None:
            continue
        if f["stable"] and abs(lt) >= 4 and abs(ls) >= 4:
            out.append({"name": f["name"], "kind": "bin", "wf_count": None,
                        "dir": 1 if ls > 0 else -1, "lift_tr": round(lt, 1), "lift_te": round(ls, 1)})
    return out


def sweep(rows):
    """稳健性扫描：特征筛选阈值与分期间数变化时，样本外优势是否稳定。"""
    out = []
    for ms in (3.0, 4.0, 6.0, 8.0):
        for mo in (4, 6, 8):
            _, a = walkforward(rows, months=mo, min_spread=ms)
            if a:
                out.append({"min_spread": ms, "months": mo, "periods": a["n_periods"],
                            "wr_top": a["wr_top"], "wr_all": a["wr_all"],
                            "bwr_top": a["bwr_top"], "bwr_all": a["bwr_all"],
                            "edge_rel": a["bwr_top"] - a["bwr_all"],
                            "win_periods": a["win_periods_top"]})
    return out


def latest_watchlist():
    """返回最新 watchlist_{YYYYMMDD}.html 文件名，供证据页链接。"""
    import re as _re
    fs = [f for f in os.listdir(OUTDIR) if _re.match(r"^watchlist_(\d{8})\.html$", f)]
    return sorted(fs)[-1] if fs else "index.html"


def render_lab(res):
    """证据页：把样本外检验的全部口径公开，供人工复核。"""
    btr, bte = res["base_train"], res["base_test"]
    Atr, Ate = res["base_train_A"], res["base_test_A"]
    wf, wagg = res["walkforward"], res.get("walkforward_agg") or {}
    comp = res["composite"]
    DIR = res["directions"]

    def base_row(lab, t):
        if not t or not t["n"]:
            return "<tr><td>%s</td><td colspan='6' class='muted'>—</td></tr>" % lab
        return ("<tr><td>%s</td><td class='num'>%d</td><td class='num'>%.1f%%</td><td class='num'>%.1f%%</td>"
                "<td class='num'>%+.2f%%</td><td class='num'>%+.2f%%</td><td class='num dn'>%.1f%%</td></tr>"
                % (lab, t["n"], t["wr"], t["bwr"], t["mean"], t["rmean"], t["mae"]))

    ft = []
    for f in res["features"]:
        if f["kind"] == "cont":
            tr = " ".join("%.0f" % b["bwr"] for b in f["train"])
            te = " ".join("%.0f" % b["bwr"] for b in f["test"])
            mark = "★稳定" if f["stable"] else ("⚠️反向" if f["mono_train"] != f["mono_test"] and f["mono_train"] != 0 else "—")
            ft.append("<tr><td>%s</td><td>连续5桶</td><td class='num'>%s</td><td class='num'>%s</td>"
                      "<td class='num'>%+.1fpp</td><td>%s</td></tr>"
                      % (f["name"], tr, te, f["spread_rel_test"], mark))
        else:
            t1 = [x for x in f["train"] if x["v"] == 1][0]
            s1 = [x for x in f["test"] if x["v"] == 1][0]
            t0 = [x for x in f["train"] if x["v"] == 0][0]
            s0 = [x for x in f["test"] if x["v"] == 0][0]
            ft.append("<tr><td>%s</td><td>是/否</td><td class='num'>%.0f / %.0f</td><td class='num'>%.0f / %.0f</td>"
                      "<td class='num'>%+.1fpp</td><td>%s</td></tr>"
                      % (f["name"], t1["bwr"], t0["bwr"], s1["bwr"], s0["bwr"],
                         f.get("lift_rel_test", 0), "★稳定" if f["stable"] else "⚠️反向"))
    dec = []
    for k in range(10):
        a = comp["train_deciles"][k]
        b = comp["test_deciles"][k]
        dec.append("<tr><td>D%d</td><td class='num'>%d</td><td class='num'>%.1f%%</td><td class='num'>%.1f%%</td>"
                   "<td class='num'>%.1f%%</td><td class='num'>%d</td><td class='num'>%.1f%%</td>"
                   "<td class='num'>%.1f%%</td><td class='num'>%+.2f%%</td><td class='num'>%.1f%%</td></tr>"
                   % (k + 1, a["n"], a["wr"], a["bwr"], a["mae"],
                      b["n"], b["wr"], b["bwr"], b["mean"], b["mae"]))
    wfr = []
    for o in wf:
        wfr.append("<tr><td>%s</td><td class='num'>%d</td><td class='num'>%d</td>"
                   "<td class='num'>%.1f%% / %.1f%%</td><td class='num'>%.1f%% / %.1f%%</td>"
                   "<td class='num %s'>%+.1fpp</td><td class='num'>%.1f%%</td><td class='num'>%d</td></tr>"
                   % (o["period"], o["feats"], o["n_all"], o["wr_all"], o["bwr_all"],
                      o["wr_top"], o["bwr_top"], "up" if o["bwr_top"] >= o["bwr_all"] else "dn",
                      o["bwr_top"] - o["bwr_all"], o["wr_A"], o["n_A"]))
    swr = "".join("<tr><td class='num'>%.0f</td><td class='num'>%d</td><td class='num'>%d</td>"
                  "<td class='num %s'>%+.1fpp</td><td class='num'>%.1f%%</td><td class='num'>%d/%d</td></tr>"
                  % (s["min_spread"], s["months"], s["periods"], "up" if s["edge_rel"] > 0 else "dn",
                     s["edge_rel"], s["wr_top"], s["win_periods"], s["periods"])
                  for s in res["sweep"])
    rgr = "".join("<tr><td>%s</td><td>%s</td><td class='num'>%d</td><td class='num'>%.1f%%</td>"
                  "<td class='num'>%.1f%%</td><td class='num %s'>%+.1fpp</td><td class='num'>%+.1fpp</td></tr>"
                  % (g["var"], g["bucket"], g["n"], g["bwr_top"], g["bwr_all"],
                     "up" if g["edge_rel"] > 0 else "dn", g["edge_rel"], g["edge_abs"])
                  for g in res["regime"])
    oosr = []
    for o in res["oos_rank"]:
        rr = o.get("result")
        if not rr:
            oosr.append("<tr><td>%s</td><td class='num'>%d</td><td colspan='5' class='muted'>特征不足</td></tr>"
                        % (o["pair"], o["feats"]))
            continue
        oosr.append("<tr><td>%s</td><td class='num'>%d</td><td class='num'>%.1f%% / %.1f%%</td>"
                    "<td class='num'>%.1f%% / %.1f%%</td><td class='num %s'>%+.1fpp</td>"
                    "<td class='num %s'>%+.1fpp</td><td class='num'>%d</td></tr>"
                    % (o["pair"], o["feats"], rr["wr_top"], rr["bwr_top"], rr["wr_all"], rr["bwr_all"],
                       "up" if rr["edge_rel"] > 0 else "dn", rr["edge_rel"],
                       "up" if rr["edge_abs"] > 0 else "dn", rr["edge_abs"], rr["n"]))
    # 冻结模型（先验固定集）表
    FEAT_CN = {"dist_lo20": "距 20 日低点（%），越低越贴底", "dist_lo60": "距 60 日低点（%）",
               "gap_lo52": "距 52 周低点（%）", "vol_dry": "20 日量能 / 60 日量能（枯竭度）",
               "atr_pct": "ATR20 / 收盘（波动水平）", "range20": "近 20 日振幅 / 收盘（箱体宽度）",
               "ma60_dev": "距 MA60（%）", "slope": "MA20 五日斜率（%）",
               "mv_log": "总市值对数（小市值）",
               "short_align": "短周期多头排列（旧 v4 口径）"}
    cons = "".join("<tr><td>%s</td><td>%s</td><td class='num'>%+d</td><td>%s</td></tr>"
                   % (f, "越小越好", -1, FEAT_CN.get(f, "—"))
                   for f in res["prior_set"])
    # 严格样本外对照
    so = res.get("strict_oos") or {}
    so_rows = []
    for k, lab in (("prior", "先验固定集（不筛，v5 冻结模型）"),
                   ("auto_strict", "自动筛 · 严格样本外（训练段学 → 测试段用）"),
                   ("auto_insample", "自动筛 · 全量（含测试段，前视）")):
        r = so.get(k)
        if not r:
            so_rows.append("<tr><td>%s</td><td colspan='6' class='muted'>—</td></tr>" % lab)
            continue
        so_rows.append("<tr><td>%s</td><td class='num'>%d</td><td class='num'>%.1f%%</td>"
                       "<td class='num'>%.1f%%</td><td class='num up'>%+.1fpp</td>"
                       "<td class='num'>%.1f%%</td><td class='num up'>%+.1fpp</td></tr>"
                       % (lab, r["n_top"], r["bwr_top"], r["bwr_all"], r["edge_rel"],
                          r["wr_top"], r["edge_abs"]))
    # 截断曲线
    tpn = "".join("<tr><td class='num'>%.0f%%</td><td class='num'>%d</td><td class='num'>%.1f%%</td>"
                  "<td class='num'>%.1f%%</td><td class='num up'>%+.1fpp</td><td class='num up'>%+.1fpp</td>"
                  "<td class='num'>%+.2f%%</td></tr>"
                  % (t["pct"] * 100, t["n_top"], t["wr_top"], t["bwr_top"], t["edge_rel"],
                     t["edge_abs"], t["mean_top"])
                  for t in res.get("topn_curve") or [])
    # 半年对照
    ho = res.get("half_oos") or {}
    hr_rows = ""
    for k, lab in (("train", "训练半（2025-11 ~ %s）" % ho.get("cut_date", "?")),
                   ("test", "测试半（%s ~ %s）" % (ho.get("cut_date", "?"), res["panel_max"]))):
        r = ho.get(k)
        if not r:
            continue
        cls = "up" if r["edge_rel"] > 0 else "dn"
        hr_rows += ("<tr><td>%s</td><td class='num'>%d</td><td class='num'>%.1f%%</td>"
                    "<td class='num'>%.1f%%</td><td class='num %s'>%+.1fpp</td>"
                    "<td class='num'>%.1f%%</td><td class='num %s'>%+.1fpp</td></tr>"
                    % (lab, r["n_top"], r["wr_top"], r["wr_all"], cls, r["edge_abs"],
                       r["bwr_top"], cls, r["edge_rel"]))
    # 退出规则
    ex = res.get("exit_lab") or {}
    ex_h = ""
    for lab, half in (("训练半", "train"), ("测试半", "test")):
        for h in (ex.get(half) or {}).get("horizons") or []:
            ex_h += ("<tr><td>%s</td><td class='num'>T+%d</td><td class='num'>%d</td>"
                     "<td class='num'>%.1f%%</td><td class='num'>%.1f%%</td><td class='num'>%+.2f%%</td>"
                     "<td class='num'>%.1f%%</td><td class='num'>%+.2f%%</td></tr>"
                     % (lab, h["h"], h["n"], h["wr"], h["wr_all"] or 0, h["mean"],
                        h["wr_all"] or 0, h["mean_all"] or 0))
    gtr = {(g["stop"], g["take"]): g for g in (ex.get("train") or {}).get("grid") or []}
    gte = {(g["stop"], g["take"]): g for g in (ex.get("test") or {}).get("grid") or []}
    ex_g = ""
    for stop in (6.0, 8.0, 10.0, 12.0, 15.0):
        for take in (0.0, 8.0, 10.0, 12.0, 15.0, 20.0):
            a, b = gtr.get((stop, take)), gte.get((stop, take))
            if not a or not b:
                continue
            ex_g += ("<tr><td class='num'>-%.0f%%</td><td class='num'>%s</td>"
                     "<td class='num'>%.1f%%</td><td class='num'>%+.2f%%</td>"
                     "<td class='num'>%.1f%%</td><td class='num'>%+.2f%%</td></tr>"
                     % (stop, ("+%.0f%%" % take) if take else "不止盈",
                        a["wr"], a["mean"], b["wr"], b["mean"]))
    # 退出规则摘要（动态算，避免硬编码数字随数据漂移）
    def _avg_wr(st, tk):
        a, b = gtr.get((st, tk)), gte.get((st, tk))
        return ((a["wr"] + b["wr"]) / 2.0) if a and b else None

    def _avg_mn(st, tk):
        a, b = gtr.get((st, tk)), gte.get((st, tk))
        return ((a["mean"] + b["mean"]) / 2.0) if a and b else None

    _cells = [k for k in gtr if k in gte]
    _tights = [k for k in _cells if k[0] == 6.0]
    ex_sum = ""
    if _cells:
        _bw = max(_cells, key=lambda k: _avg_wr(*k))
        _bm = max(_cells, key=lambda k: _avg_mn(*k))
        _tw = (sum(_avg_wr(*k) for k in _tights) / len(_tights)) if _tights else None
        ex_sum = ("两半平均胜率最高 ＝ <b>止损 −%.0f%% / 目标 %s</b>（%.1f%%）%s；"
                  "单笔均值最高的是 <b>止损 −%.0f%% / %s</b>（%+.2f%%）——"
                  "<b>胜率与单笔均值是一对权衡</b>，只看胜率会选到「赢得频繁但单笔很薄」的组合。"
                  % (_bw[0], ("+%.0f%%" % _bw[1]) if _bw[1] else "不止盈", _avg_wr(*_bw),
                     ("，而<b>最紧的 −6%% 止损全档平均只有 %.1f%%</b>" % _tw) if _tw is not None else "",
                     _bm[0], ("+%.0f%%" % _bm[1]) if _bm[1] else "不止盈", _avg_mn(*_bm)))
    # 环境门控 → 仓位系数
    gtr2 = "".join("<tr><td>%s</td><td class='num'>%.1f</td><td class='num'>%.1f%%</td>"
                   "<td class='num'>%.1f%%</td><td class='num %s'>%+.1fpp</td><td class='num'>%d</td></tr>"
                   % (g["bucket"], g["coef"], g["wr_top"], g["wr_all"],
                      "up" if g["edge_abs"] > 0 else "dn", g["edge_abs"], g["n"])
                   for g in res.get("regime_gate") or [])
    return f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>底部反转 · 特征功效实验室（样本外实证）</title><style>{R.STYLE}</style></head>
<body><div class="wrap">
<h1>底部反转 · 特征功效实验室</h1>
<div class="sub">目的：用<b>样本外实证</b>决定「哪些特征有效、方向如何、该在多大的域上选」，替代「照回测胜率手调阈值」。
面板：<b>全市场 {res.get('universe_n') or 0:,} 只 A 股</b>（<code>_txk_cache.json</code> 全量正股，只剔 K 线不足者；
未单独剔 ST/退市，占比 &lt;0.3%）× {res['panel_min']}~{res['panel_max']}，
步长 3 交易日，共 <b>{btr['n'] + bte['n']:,}</b> 个「股票×交易日」样本（均已过硬门槛）。时间切分：前 60%（至 {res['cut_date']}）训练，后 40% 测试。
（面板最新样本为 {res['panel_max']}：标签需要未来 20 交易日收益，故比最新交易日晚约 1 个月，<b>属方法固有滞后、非数据陈旧</b>；每日重跑面板会自然前移。）</div>

<div class="box gold"><b>核心结论（v5 · 全市场域）：</b>
① <b>域扩张是最实在的改进</b>：旧机制只覆盖 westock 条件选股（净利同比&gt;50 &amp; 0&lt;PE&lt;50 &amp; 市值&lt;100亿）的
<b>220 只</b>，每日硬门槛内仅约 150 只 → 横截面排序的域太窄。v5 改为<b>全市场深跌域</b>，每日域内
<b>数百至上千只</b>，分位噪声显著下降；市值/估值从硬门槛改为<b>因子</b>。
② <b>因子方向高度稳定</b>：{len(res['directions'])} 个特征训练/测试同向，方向一致为
「距低点越近、量能越枯竭、波动越低、箱体越窄、均线越未修复 → 越好」；旧 v3 的「收复 MA20 / 短均线多头排列 / 吸筹天数」
是<b>负向</b>——「越像已确认反转」的票越跑不赢篮子（过度确认陷阱）。
③ <b>十分位单调且幅度大</b>（测试段）：D1 绝对 {comp['test_deciles'][0]['wr']:.1f}% / 相对 {comp['test_deciles'][0]['bwr']:.1f}%
→ D10 绝对 {comp['test_deciles'][9]['wr']:.1f}% / 相对 {comp['test_deciles'][9]['bwr']:.1f}%
（D10−D1：绝对 {comp['test_deciles'][9]['wr'] - comp['test_deciles'][0]['wr']:+.1f}pp、相对 {comp['test_deciles'][9]['bwr'] - comp['test_deciles'][0]['bwr']:+.1f}pp）；
MAE 随分位升高而收窄（D1 {comp['test_deciles'][0]['mae']:.1f}% → D10 {comp['test_deciles'][9]['mae']:.1f}%）。
④ <b>「自动筛因子」依旧不成立</b>：严格样本外（前 60% 学 → 后 40% 测）top20% 相对 lift
<b>{so.get('auto_strict', {}).get('edge_rel', 0):+.1f}pp</b>；而<b>先验固定集（不筛）同口径 {so.get('prior', {}).get('edge_rel', 0):+.1f}pp</b>。
差额 {so.get('gap', 0):.1f}pp 就是「自动挑因子」这个动作制造的噪声量。
⑤ <b style="color:#b00020">最重要的一条（必须看清）</b>：优势<b>高度依赖期间</b>。同一套先验固定集、同一口径前 10%，
<b>训练半 {ho.get('train', {}).get('edge_rel', 0):+.1f}pp（绝对 {ho.get('train', {}).get('edge_abs', 0):+.1f}pp）、
测试半 {ho.get('test', {}).get('edge_rel', 0):+.1f}pp（绝对 {ho.get('test', {}).get('edge_abs', 0):+.1f}pp）</b>。
逐月 edge 在 −7.7pp ~ +25.4pp 之间摆动，4 负 5 正。
⑥ <b>并且没有可提前识别的失效信号</b>：广度、域内距低点中位数、域内创新低占比、量能枯竭中位数、波动中位数、距 MA60 中位数
—— 六类日级状态量在训练半/测试半<b>全部反向</b>：分桶差异被「时间段」淹没。故本模型<b>不宣称</b>能靠环境门控提高 alpha。
⑦ 既然 alpha 不稳定，胜率的可靠抓手落在<b>退出规则</b>（见第九节）：把持有期与止损/目标位按样本外对照固定下来，
而不是继续加因子。</div>

<h2>一、基线（同测试集口径）</h2>
<div class="card"><table>
<thead><tr><th>样本</th><th>n</th><th>绝对胜率</th><th>相对胜率</th><th>均值收益</th><th>相对均值</th><th>平均 MAE</th></tr></thead>
<tbody>{base_row("全体·训练期（至 %s）" % res['cut_date'], btr)}{base_row("全体·测试期（%s 起）" % res['cut_date'], bte)}
{base_row("旧 v3 A 档·训练期", Atr)}{base_row("旧 v3 A 档·测试期", Ate)}</tbody></table>
<div class="note">相对胜率 = 前向 20 日收益 &gt; 同期全市场等权中位数的占比（≈ alpha 口径）；绝对胜率 = 前向 20 日收益 &gt; 0（≈ alpha + beta）。
MAE = 平均最大不利偏移。注意全市场域下<b>训练期绝对胜率（{btr['wr']:.1f}%）反而高于测试期（{bte['wr']:.1f}%）</b>——
「训练期弱、测试期强」的旧说法只在 220 只种子池成立，全市场域下不成立，这说明<b>绝对胜率由行情决定</b>。</div></div>

<h2>二、单特征功效（相对胜率口径，训练集分桶 → 套测试集）</h2>
<div class="card"><table>
<thead><tr><th>特征</th><th>类型</th><th>训练各桶（低→高）</th><th>测试各桶（低→高）</th><th>测试极差</th><th>跨期一致性</th></tr></thead>
<tbody>{''.join(ft)}</tbody></table>
<div class="note">★稳定 = 训练与测试方向一致（只这些可入选）；⚠️反向 = 两期方向相反，说明该特征的「预测力」只是市场状态的代理。
二值特征列为「取值=1 / 取值=0」的相对胜率。</div></div>

<h2>三、组合打分 · 日内横截面十分位</h2>
<div class="card"><table>
<thead><tr><th>分位</th><th>训练 n</th><th>训练绝对</th><th>训练相对</th><th>训练MAE</th>
<th>测试 n</th><th>测试绝对</th><th>测试相对</th><th>测试均值</th><th>测试MAE</th></tr></thead>
<tbody>{''.join(dec)}</tbody></table>
<div class="note">十分位在<b>每个交易日内</b>按组合分排序后聚合（不是全局排序——全局排序会把「日期」混进分位，量到的是行情不是选股）。
测试期 D10−D1：绝对 {comp['test_deciles'][9]['wr'] - comp['test_deciles'][0]['wr']:+.1f}pp、
相对 {comp['test_deciles'][9]['bwr'] - comp['test_deciles'][0]['bwr']:+.1f}pp；
训练期 D10−D1：绝对 {comp['train_deciles'][9]['wr'] - comp['train_deciles'][0]['wr']:+.1f}pp、
相对 {comp['train_deciles'][9]['bwr'] - comp['train_deciles'][0]['bwr']:+.1f}pp —— <b>训练期明显弱于测试期</b>，
这是第四节「优势依赖期间」的第一手证据。MAE 随分位升高而收窄（测试期 D1 {comp['test_deciles'][0]['mae']:.1f}% → D10 {comp['test_deciles'][9]['mae']:.1f}%）。</div></div>

<h2>四、无未来信息 walk-forward（每月只用此前数据筛特征+定方向）</h2>
<div class="card"><table>
<thead><tr><th>期间</th><th>特征数</th><th>全体 n</th><th>全体 绝对/相对</th><th>top20% 绝对/相对</th><th>edge(相对)</th><th>旧v3A绝对</th><th>n</th></tr></thead>
<tbody>{''.join(wfr)}</tbody></table>
<div class="note">平均：top20% 绝对 {wagg.get('wr_top', 0):.1f}% / 相对 {wagg.get('bwr_top', 0):.1f}%，
全体 绝对 {wagg.get('wr_all', 0):.1f}% / 相对 {wagg.get('bwr_all', 0):.1f}%，
优势 {wagg.get('bwr_top', 0) - wagg.get('bwr_all', 0):+.1f}pp，{wagg.get('win_periods_top', 0)}/{wagg.get('n_periods', 0)} 期占优。
<b>注意：这是「自动筛因子」口径</b>（每期重新挑特征）——第九节会说明它在严格样本外几乎归零，
真正冻结的模型用的是先验固定集。</div></div>

<h2>五、参数稳健性扫描</h2>
<div class="card"><table>
<thead><tr><th>特征筛选阈值(pp)</th><th>分期间数</th><th>有效期间</th><th>edge(相对)</th><th>top20% 绝对</th><th>占优期</th></tr></thead>
<tbody>{swr}</tbody></table>
<div class="note">网格用于检验「自动筛因子」的符号是否稳健；即便多半为正，其幅度也远小于先验固定集
（见第九节），所以它只作诊断，不作为落地依据。</div></div>

<h2>六、环境分桶（<b style="color:#b00020">结论不成立，仅作透明度展示</b>）</h2>
<div class="card"><table>
<thead><tr><th>状态变量</th><th>分桶</th><th>n</th><th>top20% 相对</th><th>全体 相对</th><th>edge(相对)</th><th>edge(绝对)</th></tr></thead>
<tbody>{rgr}</tbody></table>
<div class="note">状态变量均为 scan 当日可算的滞后量：<code>mkt20</code>=全市场等权中位 20 日收益，<code>breadth</code>=站上 MA20 的占比。
<b style="color:#b00020">但按广度/行情分桶得出的 edge 差异在训练半与测试半方向相反</b>（另测了域内距低点中位数、域内创新低占比、
量能枯竭中位数、波动中位数、距 MA60 中位数，六类全部反向），差异被「时间段」淹没。
故本页<b>不把环境门控当作提高 alpha 的手段</b>。</div></div>

<h2>七、环境门控 → 仓位系数（仅用于绝对收益量级与仓位，不用于选股）</h2>
<div class="card"><table>
<thead><tr><th>状态桶</th><th>建议系数</th><th>前10% 绝对</th><th>域均 绝对</th><th>edge(绝对)</th><th>n</th></tr></thead>
<tbody>{gtr2}</tbody></table>
<div class="note">仓位系数只回答「今天该用多少仓位」这一件事（β 层面），<b>不改变选股排序</b>；
其分桶差异同样在两半不一致，故页面把它标注为<b>参考而非依据</b>。</div></div>

<h2>八、跨期方向迁移（日内分位排序口径）</h2>
<div class="card"><table>
<thead><tr><th>迁移方向</th><th>特征数</th><th>top20% 绝对/相对</th><th>全体 绝对/相对</th><th>edge 相对</th><th>edge 绝对</th><th>n</th></tr></thead>
<tbody>{''.join(oosr)}</tbody></table>
<div class="note">「弱市学→强市用」是标准样本外检验；「强市学→弱市用」是反向时间迁移（该段方向迁移为
{res['oos_rank'][1]['result']['edge_rel']:+.1f}pp）。两向差异就是第四节那条「优势依赖期间」的另一面。</div></div>

<h2>九、严格样本外对照（前 60% 训练 → 后 40% 测试）</h2>
<div class="card"><table>
<thead><tr><th>口径</th><th>n_top</th><th>top 相对</th><th>全体 相对</th><th>edge 相对</th><th>top 绝对</th><th>edge 绝对</th></tr></thead>
<tbody>{''.join(so_rows)}</tbody></table>
<div class="note"><b>先验固定集（不筛因子、等权、方向由经济逻辑给定）在严格样本外显著优于「自动筛因子」</b>；
而「自动筛·全量（含测试段）」比「自动筛·严格样本外」高出 <b>{so.get('gap', 0):.1f}pp</b>，
这 {so.get('gap', 0):.1f}pp 就是<b>挑选动作本身制造的过拟合量</b>，不是选股能力。
另：v5 的先验固定集与旧 v4 共识集实测几乎等价（9 个因子里 8 个相同，仅「规模因子」换掉了「短均线多头排列」），
所以<b>因子层面已无继续「加指标」的空间</b>，真正的改进来自域扩张与退出规则。</div></div>

<h2>十、截断比例曲线（先验固定集，测试段）</h2>
<div class="card"><table>
<thead><tr><th>每日取前</th><th>n_top</th><th>绝对胜率</th><th>相对胜率</th><th>edge 相对</th><th>edge 绝对</th><th>均值收益</th></tr></thead>
<tbody>{tpn}</tbody></table>
<div class="note">按比例截断的曲线在 5%~10% 见顶后缓慢衰减，故 A 档取<b>域内前 10%</b>。
另测「按绝对名次取前 N」（前 10/20/30/50/80/130/200 名）呈<b>递增</b>——因为域大小每日变动，
绝对名次会漂移，命中不了「最差的那批」，故<b>不采用绝对名次</b>。</div></div>

<h2>十一、退出规则对照（把胜率交给纪律，而不是交给预测）</h2>
<div class="card"><table>
<thead><tr><th>半段</th><th>持有期</th><th>n</th><th>前10% 绝对胜率</th><th>域均</th><th>前10% 均值</th><th>域均 均值</th></tr></thead>
<tbody>{ex_h}</tbody></table>
</div>
<div class="card" style="margin-top:10px"><table>
<thead><tr><th>止损</th><th>目标位</th><th>训练半 可兑现胜率</th><th>训练半 均值</th><th>测试半 可兑现胜率</th><th>测试半 均值</th></tr></thead>
<tbody>{ex_g}</tbody></table>
<div class="note">口径：以样本的 MAE/MFE 近似路径，<b>止损优先</b>（保守），未触发则持到 20 日；
忽略移动止盈与路径先后 → 对所有规则同等保守，故<b>规则间的相对比较有效</b>、绝对值偏保守。<br>
{ex_sum}<br>
结论：<b>持有期与止损/目标位在训练半选出的较好组合，在测试半同样成立</b>（两半同向），
这是本模型里<b>唯一跨期稳定</b>的改进来源。<br>
<b style="color:#b00020">⚠️ 与选股页的联动（必读）</b>：顶部十分位的<b>平均最大不利偏移（MAE）约
{comp['test_deciles'][9]['mae']:.1f}%</b> —— 也就是说「贴身止损（−5% 上下）」几乎必然被日常波动扫掉，
这与上表「−6% 止损档胜率最低」互为印证。因此落地纪律是：
<b>结构位（跌破近 20 日基底）当「减半」信号，−15% 当「全出」硬止损，+8%~+10% 先止盈一半</b>；
选股页给出的「止损」是<b>结构位</b>（普遍在 −3%~−8%），单用它当硬止损会系统性过早离场。</div></div>

<h2>十二、训练半 / 测试半对照（本次最重要的表）</h2>
<div class="card"><table>
<thead><tr><th>半段</th><th>n_top</th><th>前10% 绝对</th><th>域均 绝对</th><th>edge 绝对</th><th>前10% 相对</th><th>edge 相对</th></tr></thead>
<tbody>{hr_rows}</tbody></table>
<div class="note"><b style="color:#b00020">alpha 在训练半为负、在测试半为正。</b>
这意味着「+14pp」这类全期数字并不代表稳定能力；页面与选股结果都据此把
「因子失效期」明确标注出来，而不是用回测数字掩盖它。</div></div>

<h2>十三、冻结模型（先验固定集，写入 quant/_rev_model.json 供选股页消费）</h2>
<div class="card"><table>
<thead><tr><th>特征</th><th>方向</th><th>dir</th><th>说明</th></tr></thead>
<tbody>{cons}</tbody></table>
<div class="note">入选规则：<b>方向由经济逻辑给定、等权、不按回测调权重、不做因子筛选</b>——
只有「先验固定」才能让全期都是干净的样本外。当前 {len(res['prior_set'])} 项，全部为「越小越好」。
<b>特别注意</b>：本模型不包含「是否已收复 MA20 / 是否短均线多头排列 / 吸筹天数」等确认类信号，
因为它们在相对胜率上是<b>负向</b>（越确认越跑不赢）。</div></div>

<h2>十四、方法与局限（必读）</h2>
<div class="card"><div class="kv">
• <b>域（v5）</b>：全市场 A 股正股（<code>_txk_cache.json</code> 全量，只剔 K 线不足），
硬门槛 = 距 52 周高回撤 ≥18% 且未跌破 MA60×0.75 且 20 日均成交额 ≥3000 万。
实验室面板<b>未单独剔 ST/退市</b>（占比 &lt;0.3%，对结论无实质影响）；选股页 <code>rev_pool.py</code> 会另按名称剔除。<br>
<b>不再使用「净利同比&gt;50 &amp; 0&lt;PE&lt;50 &amp; 市值&lt;100亿」的条件选股种子</b>，市值/估值改为因子。<br>
• <b>目标</b>：前向 20 交易日收益（信号日收盘买入）与其相对同域等权中位数的超额。<br>
• <b>无泄漏</b>：分位在同一交易日内计算；walk-forward 只用该期之前的数据。<br>
• <b>不拟合权重</b>：等权分位合成，不做权重优化，避免二次过拟合。<br>
• <b>局限 1（重要）</b>：<b>优势依赖期间</b>（训练半为负、测试半为正），且未找到可提前识别的状态量；
样本仅 {res['panel_min']}~{res['panel_max']}（约 {res['panel_months']} 个月），换年份是否成立<b>无法验证</b>。<br>
• <b>局限 2</b>：前向 20 日窗口互相重叠 → 样本非独立，统计显著性须按<b>日期聚类</b>理解，不要把 pp 差当独立样本读。<br>
• <b>局限 3</b>：规模因子 <code>mv_log</code> 用「股本反推 × 收盘」近似，股本变动（送转/增发）会带来偏差；<br>
• <b>局限 4</b>：退出规则的路径用 MAE/MFE 近似（止损优先、忽略移动止盈），绝对值偏保守。<br>
• <b>结论不构成投资建议</b>；实证均为历史统计，不代表未来。</div></div>

<div class="foot">入口：<a href="index.html" style="color:var(--blue)">反转池首页</a> ·
<a href="{latest_watchlist()}" style="color:var(--blue)">最新选股页</a> ·
<a href="backtest.html" style="color:var(--blue)">回测页</a></div>
</div></body></html>"""


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--panel", default=os.path.join(QUANT, "_rev_lab_panel.json"))
    ap.add_argument("--rebuild", action="store_true")
    a = ap.parse_args()
    if os.path.exists(a.panel) and not a.rebuild:
        rows = json.load(open(a.panel, encoding="utf-8"))
        print("[lab] 复用面板 %d 行" % len(rows))
    else:
        rows = build_panel()
        json.dump(rows, open(a.panel, "w", encoding="utf-8"), ensure_ascii=False)
    res = analyse(rows)
    DIR = {f["name"]: f["mono_test"] for f in res["features"] if f["stable"]}
    use = [k for k in DIR if k != "idx_above"]
    res["directions"] = DIR
    res["composite_use"] = use
    # ① 旧「跨期一致筛选」组合（v4 口径，仅作对照）
    res["composite_stable"] = composite(rows, use, DIR)
    # ② 先验固定因子集（v5 落地模型，方向全 −1，不筛不调权）
    PRIOR_DIR = {f: -1 for f in PRIOR_SET}
    res["prior_set"] = PRIOR_SET
    res["composite"] = composite(rows, PRIOR_SET, PRIOR_DIR)
    wf, wf_agg = walkforward(rows)
    res["walkforward"] = wf
    res["walkforward_agg"] = wf_agg
    cons = consensus(res, wf)
    res["consensus"] = cons
    res["regime"] = regime_edge(rows, PRIOR_SET, PRIOR_DIR)
    res["oos_rank"] = oos_rank(rows)
    res["sweep"] = sweep(rows)
    res["strict_oos"] = strict_oos(rows)
    res["topn_curve"] = topn_curve(rows, PRIOR_DIR, PRIOR_DIR)
    res["regime_gate"] = regime_gate(rows, PRIOR_DIR, PRIOR_DIR)
    res["exit_lab"] = exit_lab(rows)
    res["universe_n"] = _universe_n(rows)
    # 训练半 / 测试半 的先验集表现（判断优势是否只集中在某段行情）
    _hr = [r for r in rows if r["hard"] and r["y"].get("beat20") is not None]
    _ds = sorted({r["date"] for r in _hr})
    _cut = _ds[int(len(_ds) * 0.6)]
    res["panel_min"] = _ds[0]
    res["panel_max"] = _ds[-1]
    from datetime import datetime as _dt
    _pa = _dt.strptime(res["panel_max"], "%Y-%m-%d")
    _pm = _dt.strptime(res["panel_min"], "%Y-%m-%d")
    res["panel_months"] = max(1, round((_pa - _pm).days / 30.4))
    res["half_oos"] = {
        "train": _rank_top([r for r in _hr if r["date"] < _cut], PRIOR_DIR, PRIOR_DIR, 0.10),
        "test": _rank_top([r for r in _hr if r["date"] >= _cut], PRIOR_DIR, PRIOR_DIR, 0.10),
        "cut_date": _cut}
    model = {"_doc": "底部反转 v5 选股模型（全市场域 · 先验固定因子集，方向由经济逻辑给定，勿手改）",
             "source": "quant/_rev_lab.py", "version": "rev_v5",
             "universe": "全市场（quant/_txk_cache.json 全部可用标的，约 5000 只）",
             "hard_gate": {"dist52_max": DIST_GATE, "ma60_guard": MA60_GUARD, "amt20_min": AMT_MIN},
             "cut_date": res["cut_date"],
             "panel": "全市场 × {pm}~{pa}，步长 3 交易日（样本外：前 60% 训练 / 后 40% 测试）".format(
                 pm=res["panel_min"], pa=res["panel_max"]),
             "features": [{"name": f, "kind": "cont", "dir": -1} for f in PRIOR_SET],
             "prior": True,
             "wf_agg": wf_agg,
             "evidence": {"strict_oos": res["strict_oos"], "topn": res["topn_curve"],
                          "regime_gate": res["regime_gate"]},
             "base": {"train": res["base_train"], "test": res["base_test"],
                      "train_A_v3": res["base_train_A"], "test_A_v3": res["base_test_A"]}}
    json.dump(model, open(os.path.join(QUANT, "_rev_model.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    json.dump(res, open(os.path.join(QUANT, "_rev_lab_result.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    html = render_lab(res)
    open(os.path.join(OUTDIR, "lab.html"), "w", encoding="utf-8").write(html)
    print("[lab] 写 web/reversal/lab.html")
    print("\n=== 基线 ===")
    for k in ("base_train", "base_test", "base_train_A", "base_test_A"):
        v = res[k]
        print("%-14s n=%5d  绝对胜率 %5.1f%%  相对胜率 %5.1f%%  均值 %+.2f%%  相对均值 %+.2f%%" % (
            k, v["n"], v["wr"], v["bwr"], v["mean"], v["rmean"]))
    print("\n=== 稳定特征（训练/测试同向，按相对胜率） ===")
    print(DIR)
    print("\n=== 横截面十分位（测试集，日内排序） ===")
    for k, d in enumerate(res["composite"]["test_deciles"]):
        print("D%-2d n=%4d  绝对 %5.1f%%  相对 %5.1f%%  均值 %+.2f%%" % (k + 1, d["n"], d["wr"], d["bwr"], d["mean"]))
    print("\n=== 无未来信息 walk-forward ===")
    for o in wf:
        print("%s base 绝%5.1f%%/相%5.1f%% (n%d) | new-top 绝%5.1f%%/相%5.1f%% (n%d) | v3A 绝%5.1f%% (n%d) | 特征%d" % (
            o["period"], o["wr_all"], o["bwr_all"], o["n_all"], o["wr_top"], o["bwr_top"],
            o["n_top"], o["wr_A"], o["n_A"], o["feats"]))
    print("\nAGG:", json.dumps(wf_agg, ensure_ascii=False))
    print("\n=== 共识特征（WF≥4/6 或 二值稳定 lift≥4pp） ===")
    for c in cons:
        print("  %-13s %-5s dir=%+d  wf=%s %s" % (
            c["name"], c["kind"], c["dir"],
            c["wf_count"], ("lift tr %+.1f / te %+.1f" % (c["lift_tr"], c["lift_te"])) if c["kind"] == "bin" else ""))
    print("\n=== 稳健性扫描（edge = 相对胜率 top20% − 全体） ===")
    print("%6s %6s %8s %9s %9s %6s" % ("minSp", "months", "periods", "edge_rel", "wr_top", "win"))
    for s in res["sweep"]:
        print("%6.1f %6d %8d %+8.1fpp %8.1f%% %4d/%d" % (
            s["min_spread"], s["months"], s["periods"], s["edge_rel"], s["wr_top"],
            s["win_periods"], s["periods"]))
    print("\n=== 环境门控（组合 top20% vs 基线，按日级市场状态分桶） ===")
    print("%-8s %-18s %6s | %8s %8s %9s %9s" % ("var", "bucket", "n", "bwr_top", "bwr_all", "edge_rel", "edge_abs"))
    for g in res["regime"]:
        print("%-8s %-18s %6d | %7.1f%% %7.1f%% %+8.1fpp %+8.1fpp" % (
            g["var"], g["bucket"], g["n"], g["bwr_top"], g["bwr_all"], g["edge_rel"], g["edge_abs"]))
    print("\n=== 跨期方向迁移（日内分位排序口径） ===")
    for o in res["oos_rank"]:
        rr = o.get("result")
        if not rr:
            print("  %s  特征不足(%d)" % (o["pair"], o["feats"]))
            continue
        print("  %-14s 特征%2d | top20%% 绝%5.1f%%/相%5.1f%%  全体 绝%5.1f%%/相%5.1f%%  edge 相%+5.1fpp/绝%+5.1fpp  n=%d" % (
            o["pair"], o["feats"], rr["wr_top"], rr["bwr_top"], rr["wr_all"], rr["bwr_all"],
            rr["edge_rel"], rr["edge_abs"], rr["n"]))

    so = res["strict_oos"]
    print("\n=== 严格样本外对照（前 60% 训练 → 后 40% 测试，top20%） ===")
    for k, lab in (("prior", "先验固定集（不筛）"), ("auto_strict", "自动筛·严格样本外"),
                   ("auto_insample", "自动筛·全量（含前视）")):
        r = so.get(k)
        print("  %-18s 相对 %5.1f%% vs 全体 %5.1f%% = edge %+5.1fpp | 绝对 %5.1f%% vs %5.1f%% = %+5.1fpp"
              % (lab, r["bwr_top"], r["bwr_all"], r["edge_rel"],
                 r["wr_top"], r["wr_all"], r["edge_abs"]) if r else "  %-18s —" % lab)
    print("  过拟合量（全量−严格） = %s pp | 自动筛特征 %d 个 / 训练段选中 %d 个 / 交集 %d 个"
          % ("%.1f" % so["gap"] if so["gap"] is not None else "—",
             len(so["auto_insample_feats"]), len(so["auto_strict_feats"]), len(so["overlap"])))

    print("\n=== 截断比例曲线（先验固定集，测试段） ===")
    print("%6s %7s %9s %9s %9s %9s %8s" % ("前%", "n_top", "绝对胜率", "相对胜率", "edge_rel", "edge_abs", "均值"))
    for t in res["topn_curve"]:
        print("%5.0f%% %7d %8.1f%% %8.1f%% %+8.1fpp %+8.1fpp %+7.2f%%" % (
            t["pct"] * 100, t["n_top"], t["wr_top"], t["bwr_top"], t["edge_rel"], t["edge_abs"], t["mean_top"]))

    print("\n=== 环境门控 → 仓位系数（先验固定集 top10%） ===")
    print("%-20s %6s %8s %8s %9s %9s %8s" % ("状态桶", "系数", "绝对top", "绝对全", "edge_rel", "edge_abs", "n"))
    for g in res["regime_gate"]:
        print("%-20s %6.1f %7.1f%% %7.1f%% %+8.1fpp %+8.1fpp %8d" % (
            g["bucket"], g["coef"], g["wr_top"], g["wr_all"], g["edge_rel"], g["edge_abs"], g["n"]))
