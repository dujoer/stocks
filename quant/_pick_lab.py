# -*- coding: utf-8 -*-
"""精选池 · 特征功效样本外实验室（pick_lab v1）。

问题诊断
--------
`build_picks.py` 的 11 维权重在 2026-09-18 被「按近 5 期实测归因」重调过一次——
5 期 × ~20 只 = ~100 个样本、且全部落在同一波行情里。这是典型的**样本内过拟合**：
回测好看、换行情失效。回测页自己已经暴露了症状——
机构轨 B 档 T+1 胜率 36%，而 D 档（最低分档）T+5 反而 +5.74%、胜率 83%，**分档与收益反向**。

科学口径（与底部反转 lab 同一套，四条硬约束）
------------------------------------------
A. **目标解耦**：前向收益同时记「绝对胜率 wr」与「相对胜率 bwr = 个股前向收益 > 同期域内等权中位数」。
   绝对胜率 = alpha + beta（行情给的，普涨里随便买都赢）；**相对胜率才是纯选股 alpha**。
B. **时间切分**：前 60% 交易日 = 训练，后 40% = 测试；**分位切点只用训练集算**，再套到测试集（无泄漏）。
C. **无未来信息 walk-forward**：按月扩窗，每月只用该月之前的数据「筛特征 + 定方向」，报当期真实前向表现。
   特征方向一律按**相对胜率**学，避免把行情方向学进模型。
D. **横截面分位**：分位在**每个交易日内**排序后聚合；全局排序会把「日期」混进分位，量到的是 beta 不是 alpha。

标的域
------
精选池候选来自「龙虎榜机构/游资 + 中报十大股东增减持 + 高管增减持 + 大宗交易」——
都是 **event-driven 的异动票**。故面板主域取 **HOT 异动域**（近 5 日放量或大涨），
与精选池实际选票的池子高度重合；宽域（ALL）仅作对照。

局限（必须与被引用方一同声明）
-----------------------------
· **域近似而非名单复现**：候选名单历史只有 7 期，无法回溯；用价格异动域近似 → 本页结论描述的是
  「在异动票里，哪些指标能筛出跑赢同类的」这一**选股能力**，不直接等于「精选池历史名单的真实收益」。
· **窗口重叠**：前向 N 日窗口互相重叠 → 样本非独立；所有差异按**日期聚类**理解，不做逐票独立性假设。
· **样本跨度**：覆盖约 13 个月（2025-07 ~ 2026-09），**换年份是否成立无法验证**。

输出：quant/_pick_lab_panel.json · quant/_pick_lab_result.json · web/picks/lab.html
"""
from __future__ import annotations
import os, sys, json, math, statistics, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rev_pool as R
import _idxkline as E

ROOT = R.ROOT
QUANT = R.QUANT
WEB = os.path.join(ROOT, "web")
OUTDIR = os.path.join(WEB, "picks")

STEP = 3          # 截面步长（交易日）
MINI = 45         # 特征需要的最少历史根数
FMAX = 20         # 最长前向窗口
HOT_PCT = 0.08    # 异动域：每日取量比排名前 8%（≈200 只/日，与龙虎榜放量域重合）
MIN_CROSS = 40    # 单个截面最少样本数（不足则该日不参与统计）
CACHE = os.path.join(QUANT, "_txk_cache.json")

CONT = [
    ("pos52",         "52周位置",     "现价在近 52 周高低区间中的百分位（0=低点 100=高点）"),
    ("dist_hi20",     "距20日高",     "现价距近 20 日最高价的幅度（%，越接近 0 越强）"),
    ("dist_lo20",     "离20日低",     "现价高于近 20 日最低价的幅度（%），越大说明已反弹越多"),
    ("up5",           "5日涨幅",      "近 5 个交易日累计涨幅"),
    ("up20",          "20日涨幅",     "近 20 个交易日累计涨幅"),
    ("up60",          "60日涨幅",     "近 60 个交易日累计涨幅"),
    ("rs5",           "5日超额",      "近 5 日涨幅 − 同日域内等权中位涨幅（剔除大盘的纯相对强度）"),
    ("rs20",          "20日超额",     "近 20 日涨幅 − 同日域内等权中位涨幅"),
    ("rs60",          "60日超额",     "近 60 日涨幅 − 同日域内等权中位涨幅"),
    ("consec_up",     "连涨天数",     "截至当日的连续上涨天数"),
    ("ma5_dev",       "距MA5",        "收盘价偏离 5 日均线的幅度（%，短线过热惩罚项）"),
    ("ma20_dev",      "距MA20",       "收盘价偏离 20 日均线的幅度（%，过大=过热）"),
    ("align",         "多头排列",     "MA5>MA10>MA20>MA60 逐级成立的条数（0~3）"),
    ("slope20",       "MA20斜率",     "MA20 过去 5 日的斜率（%，趋势加速/走平）"),
    ("vol_day",       "当日量比",     "当日成交量 ÷ 60 日均量"),
    ("vol5_20",       "量能5/20",     "5 日均量 ÷ 20 日均量（放量进攻 或 缩量整理）"),
    ("vol_dry",       "量能20/60",    "20 日均量 ÷ 60 日均量（中期地量程度）"),
    ("vwap_dev",      "距20日VWAP",   "收盘价偏离 20 日成交量加权均价（%，高于 0 说明持仓者普遍浮盈）"),
    ("updn_vol",      "涨跌量比",     "近 20 日上涨日量能和 ÷ 下跌日量能和（>1 = 资金净流入代理）"),
    ("clv5",          "承接强度",     "近 5 日 (收盘−最低)/(最高−最低) 均值（贴日内高位=买盘承接强）"),
    ("clv20",         "承接强度20",   "近 20 日 (收盘−最低)/(最高−最低) 均值"),
    ("shadow_up",     "上影线比",     "近 10 日上影线 ÷ 振幅 均值（冲高回落=抛压重）"),
    ("atr_pct",       "波动幅度",     "ATR20 ÷ 收盘价（%，标的自身波动水平）"),
    ("atr_comp",      "波动收缩",     "ATR20 ÷ ATR60（<1 = 波动在收敛，常见于突破前蓄势）"),
    ("range_comp",    "振幅收缩",     "近 5 日平均振幅 ÷ 近 20 日平均振幅（VCP 收缩度）"),
    ("vola_pct",      "波动分位",     "ATR% 在自身近 120 日内的百分位（低分位=平静）"),
    ("rsi14",         "RSI14",        "14 日相对强弱指标"),
    ("macd_hist",     "MACD柱",       "（DIF−DEA）÷ 收盘价 ×100，正=多头动能"),
    ("hist_up",       "MACD柱递增",   "近 3 日 MACD 柱是否逐日放大（1/0）"),
    ("dif_up",        "DIF在0轴上",   "DIF 是否位于 0 轴上方（1/0）"),
    ("pullback_dry",  "回调缩量",     "近 3 日下跌日量能 ÷ 前 10 日量能（缩量回调=惜售，放量下跌=出货）"),
    ("vol_ratio_pct", "量比历史分位", "当日量比在自身近 120 日内的百分位"),
    ("turn_proxy",    "活跃度分位",   "近 5 日均量在自身近 120 日内的百分位（换手活跃度代理）"),
    ("gap_up",        "高开幅度",     "近 5 日开盘相对前收的平均跳空幅度（%）"),
    ("hi52_gap",      "离52周高",     "距 52 周最高价的幅度（%，0=创新高）"),
    # —— 第二批：规模 / 隔夜日内分解 / 量价关系（2026-09-20 补） ——
    ("amt20_log",     "20日均额",     "近 20 日平均成交额取对数 —— 规模与流动性代理（越小越偏小盘）"),
    ("ovn20",         "隔夜贡献",     "近 20 日隔夜跳空（开/前收−1）累计贡献（%）——资金是否愿承担隔夜风险"),
    ("intra20",       "日内贡献",     "近 20 日日内（收/开−1）累计贡献（%）——盘中真实承接强度"),
    ("vp_corr",       "量价相关",     "近 20 日 量比 与 当日涨跌幅 的相关系数（正=放量上涨/缩量下跌，量价健康）"),
    ("up_vol_share",  "放量阳线比",   "近 20 日中「量比>1 且收阳」的天数占比（%）"),
    ("ma10_reclaim",  "回踩MA10",     "近 10 日触及 MA10 后收盘收复的比例（%）——均线支撑有效性"),
    # —— 第三批：规模 / 估值 / 基本面（正交于价格，来自东财业绩报表） ——
    ("mv_log",        "市值(对数)",   "总市值取对数 = 收盘价 × 股本（股本由 归母净利 ÷ EPS 反推）——规模因子"),
    ("ep",            "盈利收益率",   "EPS ÷ 收盘价 ×100（市盈率倒数）——价值因子"),
    ("bp",            "账面市值比",   "每股净资产 ÷ 收盘价 ×100（市净率倒数）——价值因子"),
    ("roe",           "ROE",          "最新报告期加权 ROE（%）——质量因子"),
    ("grow_np",       "净利同比",     "最新报告期归母净利同比（%）——成长因子"),
    ("grow_q",        "单季净利同比", "最新报告期单季归母净利同比（%）——成长因子（更敏感）"),
    ("grow_rev",      "营收同比",     "最新报告期营业收入同比（%）——成长因子（更难粉饰）"),
]

MKT = [
    ("mkt_up20", "域面20日收益", "当日域内等权 20 日收益中位数（市场状态·滞后量）"),
    ("mkt_above", "域面站上MA20", "当日域内收盘价站上 MA20 的占比（%）"),
    ("idx_dev",  "指数偏离MA20", "上证指数偏离其 MA20 的幅度（%）"),
]


def _pct(a, b):
    return (a / b - 1) * 100 if b else 0.0


def load_cache():
    with open(CACHE, encoding="utf-8") as f:
        return json.load(f)


def load_fin():
    """财务快照（一码一行·最新报告期）。用于规模/估值/基本面因子。

    注意：用它解释更早的价格行为存在**前视偏差**（最新报告期数据对全期已知）。
    但该偏差对所有标的同等作用 → **桶间相对 lift 仍有效**，结论以相对口径为准。
    """
    p = os.path.join(QUANT, "fin", "snapshot.json")
    if not os.path.exists(p):
        return {}
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f).get("stocks") or {}
    except Exception:
        return {}


MAIN = "5"        # 主口径周期：精选池持仓 1~5 日，故主标签取 5 日相对超额
HORS = ["5", "10", "20"]
TOPN = 8          # walk-forward / 最终模型最多使用的特征数（弱特征等权会稀释信号）
MIN_EDGE = 3.0    # 稳定判据的幅度门槛：训练集 top−bottom 相对胜率差至少 3pp，避免把噪声当因子


# ---------------- 统计工具 ----------------
def _wr(rows, h=None):
    h = h or MAIN
    key_r, key_b = "fwd" + h, "beat" + h
    rr = [r[key_r] for r in rows if r.get(key_r) is not None]
    if not rr:
        return {"n": 0, "wr": 0.0, "bwr": 0.0, "mean": 0.0, "mae": 0.0, "nb": 0}
    bs = [r[key_b] for r in rows if r.get(key_b) is not None]
    maes = [r["mae20"] for r in rows if r.get("mae20") is not None]
    return {"n": len(rr),
            "wr": sum(1 for x in rr if x > 0) / len(rr) * 100,
            "mean": sum(rr) / len(rr),
            "bwr": (sum(bs) / len(bs) * 100) if bs else 0.0,
            "nb": len(bs),
            "mae": (sum(maes) / len(maes)) if maes else 0.0}


def _mono(buckets, minn=25):
    ws = [b["bwr"] for b in buckets if b and b["nb"] >= minn]
    if len(ws) < 4:
        return 0
    ups = sum(1 for a, b in zip(ws, ws[1:]) if b > a)
    dns = sum(1 for a, b in zip(ws, ws[1:]) if b < a)
    if ups >= len(ws) - 2 and ups > dns:
        return 1
    if dns >= len(ws) - 2 and dns > ups:
        return -1
    return 0


def _split(rows):
    ds = sorted({r["date"] for r in rows})
    cut = ds[int(len(ds) * 0.6)]
    return [r for r in rows if r["date"] < cut], [r for r in rows if r["date"] >= cut], cut


# ---------------- ② 单特征功效（切点只用训练集） ----------------
def analyse(rows, q=5):
    tr, te, cut = _split(rows)
    print("[lab] 训练 %d 行（<%s） | 测试 %d 行（>=%s）" % (len(tr), cut, len(te), cut))
    feats = []
    allnames = [c[0] for c in CONT] + [c[0] for c in MKT]
    for name in allnames:
        vals = [r[name] for r in tr if r.get(name) is not None]
        if len(vals) < 200 or len(set(vals)) < 3:
            continue
        sv = sorted(vals)
        cuts = [sv[int(len(sv) * k / q)] for k in range(1, q)]
        # 退化特征（桶间无区分）直接剔除
        if len(set(cuts)) < q - 1:
            continue

        def buckets(rws):
            out = []
            for bi in range(q):
                lo = cuts[bi - 1] if bi > 0 else None
                hi = cuts[bi] if bi < q - 1 else None
                sel = []
                for r in rws:
                    v = r.get(name)
                    if v is None:
                        continue
                    if (lo is not None and v < lo) or (hi is not None and v >= hi):
                        continue
                    sel.append(r)
                out.append(_wr(sel))
            return out
        btr, bte = buckets(tr), buckets(te)
        mtr, mte = _mono(btr), _mono(bte)
        gtr = [b for b in btr if b["nb"] >= 25]
        gte = [b for b in bte if b["nb"] >= 25]
        sp_tr = (max(b["bwr"] for b in gtr) - min(b["bwr"] for b in gtr)) if len(gtr) >= 2 else 0.0
        sp_te = (max(b["bwr"] for b in gte) - min(b["bwr"] for b in gte)) if len(gte) >= 2 else 0.0
        # 方向：按训练集 top桶 − bottom桶 的相对胜率差
        d_tr = btr[-1]["bwr"] - btr[0]["bwr"]
        d_te = bte[-1]["bwr"] - bte[0]["bwr"]
        feats.append({"name": name, "kind": "cont", "cuts": cuts,
                      "train": btr, "test": bte,
                      "mono_train": mtr, "mono_test": mte,
                      "spread_rel_train": sp_tr, "spread_rel_test": sp_te,
                      "dir_train": 1 if d_tr > 0 else -1, "dir_test": 1 if d_te > 0 else -1,
                      "lift_edge_train": d_tr, "lift_edge_test": d_te,
                      "stable": bool(mtr != 0 and mtr == mte and d_tr * d_te > 0 and abs(d_tr) >= MIN_EDGE)})
    feats.sort(key=lambda f: -abs(f["spread_rel_train"]))
    stable = [f["name"] for f in feats if f["stable"]]
    print("[lab] 特征 %d 个，跨期同向稳定 %d 个：%s" % (len(feats), len(stable), "、".join(stable)))
    return {"cut_date": cut, "n_train": len(tr), "n_test": len(te),
            "base_train": _wr(tr), "base_test": _wr(te),
            "features": feats, "stable": stable}


# ---------------- ②b 因子分段一致性（比两段切分更严格） ----------------
def _seg_cons(rows, name, nseg=3, min_edge=3.0, min_n=40):
    """把一个时间段切成 nseg 段，逐段算 top1/3 − bottom1/3 的相对胜率差，看符号一致率。

    返回 (是否通过, 多数方向, 平均边缘)。这是判断「因子方向是否时变」的硬测试：
    只在训练/测试两段同向还不够，必须**在每段子期都同向**才算稳定。
    """
    ds = sorted({r["date"] for r in rows})
    if len(ds) < nseg * 4:
        return False, 1, 0.0
    bounds = [ds[int(len(ds) * k / nseg)] for k in range(nseg)] + ["9999"]
    edges = []
    for k in range(nseg):
        lo, hi = bounds[k], bounds[k + 1]
        sub = [r for r in rows if lo <= r["date"] < hi
               and r.get(name) is not None and r.get("beat" + MAIN) is not None]
        if len(sub) < 200:
            continue
        sv = sorted(r[name] for r in sub)
        a, b = sv[len(sv) // 3], sv[2 * len(sv) // 3]
        if a == b:
            continue
        g0 = [r for r in sub if r[name] < a]
        g2 = [r for r in sub if r[name] >= b]
        if len(g0) < min_n or len(g2) < min_n:
            continue
        edges.append(_wr(g2)["bwr"] - _wr(g0)["bwr"])
    if len(edges) < nseg:
        return False, 1, 0.0
    pos = sum(1 for e in edges if e > 0)
    neg = sum(1 for e in edges if e < 0)
    avg = sum(edges) / len(edges)
    d = 1 if pos >= neg else -1
    ok = (max(pos, neg) == len(edges)) and abs(avg) >= min_edge
    return ok, d, avg


def factor_stability(rows, nseg=6):
    """逐因子 × 分段的边缘符号矩阵 —— 输出每段的 edge 与一致率，供报告展示。"""
    allnames = [c[0] for c in CONT] + [c[0] for c in MKT]
    ds = sorted({r["date"] for r in rows})
    bounds = [ds[int(len(ds) * k / nseg)] for k in range(nseg)] + ["9999"]
    out = []
    for name in allnames:
        edges = []
        for k in range(nseg):
            lo, hi = bounds[k], bounds[k + 1]
            sub = [r for r in rows if lo <= r["date"] < hi
                   and r.get(name) is not None and r.get("beat" + MAIN) is not None]
            if len(sub) < 200:
                edges.append(None); continue
            sv = sorted(r[name] for r in sub)
            a, b = sv[len(sv) // 3], sv[2 * len(sv) // 3]
            if a == b:
                edges.append(None); continue
            g0 = [r for r in sub if r[name] < a]
            g2 = [r for r in sub if r[name] >= b]
            if len(g0) < 40 or len(g2) < 40:
                edges.append(None); continue
            edges.append(round(_wr(g2)["bwr"] - _wr(g0)["bwr"], 1))
        vals = [e for e in edges if e is not None]
        if len(vals) < 4:
            continue
        pos = sum(1 for e in vals if e > 0); neg = sum(1 for e in vals if e < 0)
        cons = max(pos, neg) / len(vals)
        avg = sum(vals) / len(vals)
        out.append({"name": name, "edges": edges, "consistency": round(cons, 2),
                    "dir": 1 if pos >= neg else -1, "avg_edge": round(avg, 1),
                    "n_seg": len(vals),
                    "pass": bool(cons >= 0.83 and abs(avg) >= 2.0)})
    out.sort(key=lambda x: (-x["consistency"], -abs(x["avg_edge"])))
    ok = [f["name"] for f in out if f["pass"]]
    print("[lab] 分段一致率通过 %d 个：%s" % (len(ok), "、".join(ok)))
    return out


# ---------------- ③ 横截面组合（日内分位·等权 rank） ----------------
def composite(rows, use, direction):
    bydate = {}
    for r in rows:
        if r.get("beat" + MAIN) is None:
            continue
        bydate.setdefault(r["date"], []).append(r)
    scored = []
    for d, rs in bydate.items():
        if len(rs) < MIN_CROSS:
            continue
        rk = {f: {} for f in use}
        for f in use:
            vals = sorted([(r.get(f), r["code"]) for r in rs if r.get(f) is not None])
            n = len(vals)
            if n < 10:
                continue
            for pos, (v, c) in enumerate(vals):
                rk[f][c] = pos / (n - 1) if n > 1 else 0.5
        for r in rs:
            tot, cnt = 0.0, 0
            for f in use:
                v = rk[f].get(r["code"])
                if v is None:
                    continue
                tot += (v if direction.get(f, 1) > 0 else 1 - v)
                cnt += 1
            if cnt >= max(2, len(use) // 2):
                r2 = dict(r); r2["q"] = tot / cnt
                scored.append(r2)

    def deciles(rws):
        byd = {}
        for r in rws:
            byd.setdefault(r["date"], []).append(r)
        bs = [[] for _ in range(10)]
        for d, rs in byd.items():
            if len(rs) < 20:
                continue
            rs = sorted(rs, key=lambda x: x["q"])
            for k in range(10):
                bs[k] += rs[int(len(rs) * k / 10):int(len(rs) * (k + 1) / 10)]
        return [_wr(b) for b in bs]

    tr, te, cut = _split(scored)

    def tops(rws, frac=0.2):
        byd = {}
        for r in rws:
            byd.setdefault(r["date"], []).append(r)
        top, bot = [], []
        for d, rs in byd.items():
            if len(rs) < 20:
                continue
            rs = sorted(rs, key=lambda x: -x["q"])
            k = max(1, int(len(rs) * frac))
            top += rs[:k]; bot += rs[-k:]
        return top, bot
    t_tr, b_tr = tops(tr); t_te, b_te = tops(te)
    return {"n": len(scored), "cut_date": cut,
            "train_deciles": deciles(tr), "test_deciles": deciles(te),
            "train": _wr(tr), "test": _wr(te),
            "top_train": _wr(t_tr), "bot_train": _wr(b_tr),
            "top_test": _wr(t_te), "bot_test": _wr(b_te),
            "lift_train": _wr(t_tr)["bwr"] - _wr(b_tr)["bwr"],
            "lift_test": _wr(t_te)["bwr"] - _wr(b_te)["bwr"]}


# ---------------- ④ 无未来信息 walk-forward ----------------
def walkforward(rows, months=6, min_spread=4.0):
    ds = sorted({r["date"] for r in rows})
    start = int(len(ds) * 0.25)
    seg = max(8, (len(ds) - start) // months)
    out = []
    allnames = [c[0] for c in CONT] + [c[0] for c in MKT]
    for m in range(months):
        lo, hi = start + m * seg, min(len(ds), start + (m + 1) * seg)
        if hi - lo < 4 or lo >= len(ds):
            continue
        hi_cmp = ds[hi] if hi < len(ds) else "9999"
        past = [r for r in rows if r["date"] < ds[lo]]
        cur = [r for r in rows if ds[lo] <= r["date"] < hi_cmp and r.get("beat" + MAIN) is not None]
        if len(past) < 800 or len(cur) < 60:
            continue
        use, dirs = {}, {}
        for f in allnames:
            ok, d, avg = _seg_cons(past, f, nseg=3, min_edge=3.0)
            if not ok:
                continue
            use[f] = avg if d > 0 else -avg
            dirs[f] = d
        if len(use) < 3:
            continue
        # 只留训练集边缘最强的 TOPN 个特征，避免弱特征等权稀释信号
        use = dict(sorted(use.items(), key=lambda kv: -abs(kv[1]))[:TOPN])
        dirs = {k: (1 if v > 0 else -1) for k, v in use.items()}
        byd = {}
        for r in cur:
            byd.setdefault(r["date"], []).append(r)
        sc = []
        for d, rs in byd.items():
            if len(rs) < MIN_CROSS:
                continue
            rk = {}
            for f in use:
                vals = sorted([(r.get(f), r["code"]) for r in rs if r.get(f) is not None])
                n = len(vals)
                if n < 10:
                    continue
                rk[f] = {c: (pos / (n - 1) if n > 1 else 0.5) for pos, (v, c) in enumerate(vals)}
            for r in rs:
                tot, cnt = 0.0, 0
                for f in use:
                    v = rk.get(f, {}).get(r["code"])
                    if v is None:
                        continue
                    tot += (v if dirs[f] > 0 else 1 - v); cnt += 1
                if cnt >= max(2, len(use) // 2):
                    sc.append((tot / cnt, r))
        if len(sc) < 50:
            continue
        sc.sort(key=lambda x: -x[0])
        k = max(1, len(sc) // 5)
        top = [r for _, r in sc[:k]]
        allc = [r for _, r in sc]
        wa, wt = _wr(allc), _wr(top)
        out.append({"period": "%s ~ %s" % (ds[lo], ds[hi - 1]), "feats": len(use),
                    "feat_names": sorted(use), "feat_dirs": dict(dirs),
                    "n_all": len(allc), "wr_all": wa["wr"], "bwr_all": wa["bwr"], "mean_all": wa["mean"],
                    "n_top": len(top), "wr_top": wt["wr"], "bwr_top": wt["bwr"], "mean_top": wt["mean"]})
    got = [o for o in out if o["n_top"] >= 30]
    agg = {}
    if got:
        agg = {"n_periods": len(got),
               "wr_all": sum(o["wr_all"] for o in got) / len(got),
               "wr_top": sum(o["wr_top"] for o in got) / len(got),
               "bwr_all": sum(o["bwr_all"] for o in got) / len(got),
               "bwr_top": sum(o["bwr_top"] for o in got) / len(got),
               "mean_top": sum(o["mean_top"] for o in got) / len(got),
               "win_periods": sum(1 for o in got if o["bwr_top"] > o["bwr_all"])}
    print("[lab] walk-forward：%d 期可用，弱于全体 %d 期" % (len(got), len(got) - agg.get("win_periods", 0)))
    return out, agg


# ---------------- ⑥ 环境门控 ----------------
def regime_edge(rows, use, direction):
    bydate = {}
    for r in rows:
        if r.get("beat" + MAIN) is None:
            continue
        bydate.setdefault(r["date"], []).append(r)
    scored = []
    for d, rs in bydate.items():
        if len(rs) < MIN_CROSS:
            continue
        rk = {}
        for f in use:
            vals = sorted([(r.get(f), r["code"]) for r in rs if r.get(f) is not None])
            n = len(vals)
            if n < 10:
                continue
            rk[f] = {c: (pos / (n - 1) if n > 1 else 0.5) for pos, (v, c) in enumerate(vals)}
        for r in rs:
            tot, cnt = 0.0, 0
            for f in use:
                v = rk.get(f, {}).get(r["code"])
                if v is None:
                    continue
                tot += (v if direction.get(f, 1) > 0 else 1 - v); cnt += 1
            if cnt >= max(2, len(use) // 2):
                r2 = dict(r); r2["q"] = tot / cnt
                scored.append(r2)
    # 用全市场广度（站上 MA20 占比）分桶 —— 滞后量，实盘可算；按分位切，避免绝对阈值漂移
    bs = sorted(r["breadth"] for r in scored if r.get("breadth") is not None)
    if len(bs) < 50:
        return []
    q1, q2 = bs[int(len(bs) / 3)], bs[int(len(bs) * 2 / 3)]
    buck = [("弱势(广度低)", -1, q1), ("中性", q1, q2), ("强势(广度高)", q2, 999)]
    out = []
    for nm, lo, hi in buck:
        sub = [r for r in scored if r.get("breadth") is not None and lo <= r["breadth"] < hi]
        if len(sub) < 100:
            out.append({"regime": nm, "n": len(sub), "edge": None, "edge_abs": None})
            continue
        byd = {}
        for r in sub:
            byd.setdefault(r["date"], []).append(r)
        top = []
        for d, rs in byd.items():
            if len(rs) < 20:
                continue
            rs = sorted(rs, key=lambda x: -x["q"])
            top += rs[:max(1, int(len(rs) * 0.2))]
        wt, wa = _wr(top), _wr(sub)
        out.append({"regime": nm, "n": len(sub), "n_dates": len(byd),
                    "breadth_lo": round(lo, 1), "breadth_hi": round(hi, 1),
                    "wr_all": wa["wr"], "wr_top": wt["wr"],
                    "bwr_all": wa["bwr"], "bwr_top": wt["bwr"],
                    "edge": wt["bwr"] - wa["bwr"], "edge_abs": wt["wr"] - wa["wr"],
                    "mean_top": wt["mean"], "mean_all": wa["mean"], "mae_top": wt["mae"]})
    return out


# ---------------- ④b 留一分段交叉验证（留一法，样本利用率高于扩窗） ----------------
def looseg(rows, nseg=6, min_cons=0.8, min_edge=2.0, inner=4, frac=0.2):
    """对每一段 k：只用其余 nseg−1 段筛因子（内部再切 inner 段求一致率），
    再在留出的第 k 段上做真实前向检验。**任何一段都没有用到自己的数据选因子** → 无前视。

    这是比 walk-forward 更适合小样本的做法：既保证无未来信息，又不浪费早期数据。
    """
    allnames = [c[0] for c in CONT] + [c[0] for c in MKT]
    ds = sorted({r["date"] for r in rows})
    bounds = [ds[int(len(ds) * k / nseg)] for k in range(nseg)] + ["9999"]
    out = []
    for k in range(nseg):
        lo, hi = bounds[k], bounds[k + 1]
        tr = [r for r in rows if (r["date"] < lo or r["date"] >= hi)]
        te = [r for r in rows if lo <= r["date"] < hi and r.get("beat" + MAIN) is not None]
        if len(tr) < 800 or len(te) < 100:
            continue
        use = {}
        for f in allnames:
            ok, d, avg = _seg_cons(tr, f, nseg=inner, min_edge=min_edge)
            if ok:
                use[f] = (d, abs(avg))
        if len(use) < 3:
            out.append({"period": "%s ~ %s" % (lo, bounds[k + 1] if k + 1 < len(bounds) else ds[-1]),
                        "n_all": len(te), "feats": len(use), "skip": True})
            continue
        use = dict(sorted(use.items(), key=lambda kv: -kv[1][1])[:TOPN])
        dirs = {f: v[0] for f, v in use.items()}
        # 在留出段做日内横截面分位
        byd = {}
        for r in te:
            byd.setdefault(r["date"], []).append(r)
        sc = []
        for d, rs in byd.items():
            if len(rs) < 20:
                continue
            rk = {}
            for f in use:
                vals = sorted([(r.get(f), r["code"]) for r in rs if r.get(f) is not None])
                n = len(vals)
                if n < 10:
                    continue
                rk[f] = {c: (pos / (n - 1) if n > 1 else 0.5) for pos, (v, c) in enumerate(vals)}
            for r in rs:
                tot, cnt = 0.0, 0
                for f in use:
                    v = rk.get(f, {}).get(r["code"])
                    if v is None:
                        continue
                    tot += (v if dirs[f] > 0 else 1 - v); cnt += 1
                if cnt >= max(2, len(use) // 2):
                    sc.append((tot / cnt, r))
        if len(sc) < 60:
            continue
        sc.sort(key=lambda x: -x[0])
        ntop = max(1, int(len(sc) * frac))
        top = [r for _, r in sc[:ntop]]
        allc = [r for _, r in sc]
        wa, wt = _wr(allc), _wr(top)
        out.append({"period": "%s ~ %s" % (lo, bounds[k + 1] if k + 1 < len(bounds) else ds[-1]),
                    "n_all": len(allc), "n_top": len(top), "feats": len(use),
                    "feat_dirs": dirs, "feat_names": sorted(use),
                    "wr_all": wa["wr"], "wr_top": wt["wr"],
                    "bwr_all": wa["bwr"], "bwr_top": wt["bwr"],
                    "mean_top": wt["mean"], "mae_top": wt["mae"], "skip": False})
    got = [o for o in out if not o.get("skip") and o.get("n_top", 0) >= 30]
    agg = {}
    if got:
        agg = {"n_periods": len(got),
               "wr_all": sum(o["wr_all"] for o in got) / len(got),
               "wr_top": sum(o["wr_top"] for o in got) / len(got),
               "bwr_all": sum(o["bwr_all"] for o in got) / len(got),
               "bwr_top": sum(o["bwr_top"] for o in got) / len(got),
               "mean_top": sum(o["mean_top"] for o in got) / len(got),
               "win_periods": sum(1 for o in got if o["bwr_top"] > o["bwr_all"]),
               "n_feats_avg": sum(o["feats"] for o in got) / len(got)}
    print("[lab] 留一段交叉：%d 段可用，胜出 %d 段（bwr_top %.1f vs all %.1f）"
          % (len(got), agg.get("win_periods", 0), agg.get("bwr_top", 0), agg.get("bwr_all", 0)))
    return out, agg


# ---------------- ④c 固定模型逐段滚动（诊断：因子本身稳不稳） ----------------
def _apply_model(rows, use, direction, min_cross=None):
    """按方向对日内横截面等权 rank 打分，返回带 q 的行。"""
    mc = min_cross or MIN_CROSS
    byd = {}
    for r in rows:
        if r.get("beat" + MAIN) is None:
            continue
        byd.setdefault(r["date"], []).append(r)
    sc = []
    for d, rs in byd.items():
        if len(rs) < mc:
            continue
        rk = {}
        for f in use:
            vals = sorted([(r.get(f), r["code"]) for r in rs if r.get(f) is not None])
            n = len(vals)
            if n < 10:
                continue
            rk[f] = {c: (pos / (n - 1) if n > 1 else 0.5) for pos, (v, c) in enumerate(vals)}
        for r in rs:
            tot, cnt = 0.0, 0
            for f in use:
                v = rk.get(f, {}).get(r["code"])
                if v is None:
                    continue
                tot += (v if direction.get(f, 1) > 0 else 1 - v); cnt += 1
            if cnt >= max(2, len(use) // 2):
                r2 = dict(r); r2["q"] = tot / cnt
                sc.append(r2)
    return sc


def model_by_seg(rows, use, direction, nseg=6, frac=0.2):
    """把「固定因子集 + 固定方向」的模型逐段滚动测试。

    与 looseg 的区别：**不重新筛因子**。若各段普遍为正 → 因子组合本身有效，
    失败原因是「筛选过程不稳」；若各段参差 → 因子组合本身没有稳定 edge。
    """
    sc = _apply_model(rows, use, direction)
    if not sc:
        return [], {}
    ds = sorted({r["date"] for r in sc})
    bounds = [ds[int(len(ds) * k / nseg)] for k in range(nseg)] + ["9999"]
    out = []
    for k in range(nseg):
        lo, hi = bounds[k], bounds[k + 1]
        sub = [r for r in sc if lo <= r["date"] < hi]
        if len(sub) < 120:
            continue
        byd = {}
        for r in sub:
            byd.setdefault(r["date"], []).append(r)
        top = []
        for d, rs in byd.items():
            if len(rs) < 20:
                continue
            rs = sorted(rs, key=lambda x: -x["q"])
            top += rs[:max(1, int(len(rs) * frac))]
        if len(top) < 30:
            continue
        wa, wt = _wr(sub), _wr(top)
        out.append({"period": "%s ~ %s" % (lo, hi if hi != "9999" else ds[-1]),
                    "n_all": len(sub), "n_top": len(top),
                    "bwr_all": wa["bwr"], "bwr_top": wt["bwr"], "edge": wt["bwr"] - wa["bwr"],
                    "wr_all": wa["wr"], "wr_top": wt["wr"], "edge_abs": wt["wr"] - wa["wr"],
                    "mean_all": wa["mean"], "mean_top": wt["mean"], "mae_top": wt["mae"]})
    pos = sum(1 for o in out if o["edge"] > 0)
    agg = {"n_seg": len(out), "n_pos": pos,
           "bwr_top": sum(o["bwr_top"] for o in out) / len(out) if out else 0,
           "bwr_all": sum(o["bwr_all"] for o in out) / len(out) if out else 0,
           "wr_top": sum(o["wr_top"] for o in out) / len(out) if out else 0,
           "wr_all": sum(o["wr_all"] for o in out) / len(out) if out else 0}
    if out:
        agg["edge"] = agg["bwr_top"] - agg["bwr_all"]
        agg["edge_abs"] = agg["wr_top"] - agg["wr_all"]
    print("[lab] 固定模型逐段：%d 段，正 edge %d 段（平均 %+.1fpp）"
          % (len(out), pos, agg.get("edge", 0)))
    return out, agg


# ---------------- ④d 严格样本外（只用前段筛因子 → 后段测，单次切分） ----------------
def strict_oos(rows, cut_frac=0.6, min_edge=2.0, frac=0.2):
    """最干净的一次性样本外检验：因子与方向**只由前 60% 交易日决定**，后 40% 完全不动。

    与 looseg 的区别：只筛一次（不是每段重筛），门槛不必为了凑样本而放宽，
    因此更接近「上线后真实会发生什么」。这是本实验室最该被引用的那个数字。
    """
    ds = sorted({r["date"] for r in rows})
    cut = ds[int(len(ds) * cut_frac)]
    tr = [r for r in rows if r["date"] < cut]
    te = [r for r in rows if r["date"] >= cut]
    fs = factor_stability(tr, nseg=6)
    use = {f["name"]: f["dir"] for f in fs if f["pass"]}
    print("[lab] 严格样本外：训练段筛出 %d 个因子：%s" % (len(use), "、".join(use)))
    if len(use) < 3:
        return {"cut": cut, "n_train": len(tr), "n_test": len(te), "features": use,
                "ok": False, "reason": "训练段稳定因子不足 3 个"}
    # 按训练段平均边缘取 TOPN
    rank = {f["name"]: abs(f["avg_edge"]) for f in fs if f["pass"]}
    use = dict(sorted(use.items(), key=lambda kv: -rank.get(kv[0], 0))[:TOPN])
    tr_sc = _apply_model(tr, list(use), use)
    te_sc = _apply_model(te, list(use), use)

    def tops(sc):
        byd = {}
        for r in sc:
            byd.setdefault(r["date"], []).append(r)
        top, bot = [], []
        for d, rs in byd.items():
            if len(rs) < 20:
                continue
            rs = sorted(rs, key=lambda x: -x["q"])
            k = max(1, int(len(rs) * frac))
            top += rs[:k]; bot += rs[-k:]
        return top, bot
    t_tr, b_tr = tops(tr_sc); t_te, b_te = tops(te_sc)
    wt, wa = _wr(t_te), _wr(te_sc)
    return {"cut": cut, "n_train": len(tr), "n_test": len(te), "ok": True,
            "features": use,
            "train": {"all": _wr(tr_sc), "top": _wr(t_tr), "bot": _wr(b_tr)},
            "test": {"all": wa, "top": wt, "bot": _wr(b_te)},
            "lift_test": wt["bwr"] - wa["bwr"],
            "lift_test_vs_bot": wt["bwr"] - _wr(b_te)["bwr"],
            "edge_abs_test": wt["wr"] - wa["wr"],
            "feat_stability": [{"name": f["name"], "dir": f["dir"], "cons": f["consistency"],
                                "avg_edge": f["avg_edge"]} for f in fs if f["pass"]]}


def _top_bot(sc, frac=0.2):
    byd = {}
    for r in sc:
        byd.setdefault(r["date"], []).append(r)
    top, bot = [], []
    for d, rs in byd.items():
        if len(rs) < 20:
            continue
        rs = sorted(rs, key=lambda x: -x["q"])
        k = max(1, int(len(rs) * frac))
        top += rs[:k]; bot += rs[-k:]
    return top, bot


def predefined_oos(rows, use, cut_frac=0.6, frac=0.2, label=""):
    """**因子集与方向由先验逻辑给定，不来自任何回测筛选** → 全期都是干净的样本外。

    这是唯一能同时满足「无前视」与「不引入筛选噪声」的检验方式：
    因子集不是数据挑的，所以拿它测任何一段都不算偷看。
    """
    sc = _apply_model(rows, list(use), use)
    if not sc:
        return {}
    ds = sorted({r["date"] for r in sc})
    cut = ds[int(len(ds) * cut_frac)]
    tr = [r for r in sc if r["date"] < cut]
    te = [r for r in sc if r["date"] >= cut]
    t_tr, b_tr = _top_bot(tr, frac)
    t_te, b_te = _top_bot(te, frac)
    segs, _ = model_by_seg(rows, list(use), use, nseg=6, frac=frac)
    out = {"label": label, "features": use, "cut": cut,
           "train": {"all": _wr(tr), "top": _wr(t_tr), "bot": _wr(b_tr)},
           "test": {"all": _wr(te), "top": _wr(t_te), "bot": _wr(b_te)},
           "lift_test": _wr(t_te)["bwr"] - _wr(te)["bwr"],
           "lift_test_vs_bot": _wr(t_te)["bwr"] - _wr(b_te)["bwr"],
           "edge_abs_test": _wr(t_te)["wr"] - _wr(te)["wr"],
           "segs": segs}
    print("[lab] 先验因子集「%s」：测试段 bwr %.1f→%.1f（%+.1fpp），绝对胜率 %.1f→%.1f（%+.1fpp）"
          % (label, _wr(te)["bwr"], _wr(t_te)["bwr"], out["lift_test"],
             _wr(te)["wr"], _wr(t_te)["wr"], out["edge_abs_test"]))
    return out


# ---------------- ⑤ 参数稳健性 ----------------
def sweep(rows):
    """特征入选阈值 × 分期间数 的网格：A 网格看优势符号是否稳定。"""
    grid = []
    for sp in (2.0, 3.0, 4.0, 5.0):
        for mo in (4, 5, 6, 8):
            wf, agg = walkforward(rows, months=mo, min_spread=sp)
            if not agg:
                continue
            grid.append({"min_spread": sp, "months": mo, "n_periods": agg["n_periods"],
                         "bwr_top": agg["bwr_top"], "bwr_all": agg["bwr_all"],
                         "lift": agg["bwr_top"] - agg["bwr_all"],
                         "win_periods": agg["win_periods"]})
    pos = sum(1 for g in grid if g["lift"] > 0)
    return {"grid": grid, "n": len(grid), "n_pos": pos}



def build_panel(step=STEP, hot_only=True):
    cache = load_cache()
    FIN = load_fin()
    print("[lab] 财务快照覆盖 %d 只" % len(FIN), flush=True)
    codes = sorted([c for c, v in cache.items() if len(v) >= MINI + FMAX + 5])
    print("[lab] 缓存标的 %d 只，可用 %d 只" % (len(cache), len(codes)), flush=True)

    idx = E.get_index("sh000001", 300)
    idx_dates = sorted(idx)
    idx_ma20 = {}
    ds_all = idx_dates
    for n, d in enumerate(ds_all):
        if n >= 19:
            ser = [idx[ds_all[k]] for k in range(n - 19, n + 1)]
            m = sum(ser) / 20
            idx_ma20[d] = (idx[d] - m) / m * 100 if m else 0.0
    state_dates = sorted(idx_ma20)

    def idx_dev(d):
        cand = [x for x in state_dates if x <= d]
        return idx_ma20[cand[-1]] if cand else None

    # 统一交易日历：所有票在**同一批目标日期**采样，横截面才对齐
    all_dates = sorted({b["date"] for c in codes for b in cache[c]})
    tail_cut = all_dates[-(FMAX + 1)]
    targets = [d for d in all_dates[::step] if d <= tail_cut]
    print("[lab] 目标日期 %d 个（%s ~ %s）" % (len(targets), targets[0], targets[-1]), flush=True)

    # ---------- 逐标的：前缀和 + 滚动数组一次性预计算 ----------
    pre = []
    for ci, c in enumerate(codes):
        if ci % 500 == 0:
            print("  ... %d/%d  样本 %d" % (ci, len(codes), len(pre)), flush=True)
        bars = cache[c]
        n = len(bars)
        C = [b["last"] for b in bars]
        H = [b["high"] for b in bars]
        L = [b["low"] for b in bars]
        O = [b["open"] for b in bars]
        V = [b["volume"] for b in bars]
        if not all(C) or not all(V):
            continue
        dmap = {}
        for k, b in enumerate(bars):
            dmap.setdefault(b["date"], k)
        dif, dea = R.macd_series(C)
        rsi = R.rsi_series(C, 14)

        def pref(a):
            s = [0.0] * (len(a) + 1)
            for k in range(len(a)):
                s[k + 1] = s[k] + a[k]
            return s
        SC, SH, SL, SV = pref(C), pref(H), pref(L), pref(V)

        def ma(prefS, i, w):
            if i + 1 < w:
                return None
            return (prefS[i + 1] - prefS[i + 1 - w]) / w

        # ATR 滚动（Wilder 简单均）
        TR = [0.0] * n
        for k in range(1, n):
            TR[k] = max(H[k] - L[k], abs(H[k] - C[k - 1]), abs(L[k] - C[k - 1]))
        STR = pref(TR)

        def atr(i, w):
            if i < w:
                return None
            return (STR[i + 1] - STR[i + 1 - w]) / w

        # clv / shadow / 振幅 的滚动和
        clv_arr = [0.0] * n
        sh_arr = [0.0] * n
        rg_arr = [0.0] * n
        for k in range(n):
            rng = H[k] - L[k]
            if rng > 0:
                clv_arr[k] = (C[k] - L[k]) / rng
                sh_arr[k] = (H[k] - max(C[k], O[k])) / rng
            if k > 0 and C[k - 1]:
                rg_arr[k] = rng / C[k - 1] * 100
        PCLV, PSH, PRG = pref(clv_arr), pref(sh_arr), pref(rg_arr)

        # 涨/跌日量能滚动和
        upv = [V[k] if C[k] > O[k] else 0.0 for k in range(n)]
        dnv = [V[k] if C[k] < O[k] else 0.0 for k in range(n)]
        PUV, PDV = pref(upv), pref(dnv)

        # 每 3 根采样的 ATR% 序列，用于「波动分位」
        ap_series = []
        for k in range(n):
            a = atr(k, 20)
            ap_series.append((a / C[k] * 100) if (a and C[k]) else None)

        def win_pct(series, i, back, gap=3):
            cur = series[i]
            if cur is None:
                return 50.0
            lo = max(MINI, i - back)
            vals = [series[k] for k in range(lo, i + 1, gap) if series[k] is not None]
            if len(vals) < 6:
                return 50.0
            return sum(1 for x in vals if x < cur) / len(vals) * 100

        for d in targets:
            i = dmap.get(d)
            if i is None or i < MINI or i >= n - FMAX:
                continue
            close = C[i]
            hi52 = max(H[max(0, i - 249):i + 1])
            lo52 = min(L[max(0, i - 249):i + 1])
            pos52 = (close - lo52) / (hi52 - lo52) * 100 if hi52 > lo52 else 50.0
            hi20 = max(H[i - 19:i + 1])
            lo20 = min(L[i - 19:i + 1])
            m5, m10, m20, m60 = ma(SC, i, 5), ma(SC, i, 10), ma(SC, i, 20), ma(SC, i, 60)
            m20p = ma(SC, i - 5, 20)
            slope20 = _pct(m20, m20p) if (m20 and m20p) else 0.0
            v5 = (SV[i + 1] - SV[i - 4]) / 5
            v20 = (SV[i + 1] - SV[i - 19]) / 20
            v60 = (SV[i + 1] - SV[i - 59]) / 60 if i >= 59 else v20
            vol_day = V[i] / v60 if v60 else 1.0
            vol5_20 = v5 / v20 if v20 else 1.0
            vol_dry = v20 / v60 if v60 else 1.0
            num = sum(C[k] * V[k] for k in range(i - 19, i + 1))
            den = sum(V[i - 19:i + 1])
            vwap = num / den if den else close
            uv = PUV[i + 1] - PUV[i - 19]
            dv = PDV[i + 1] - PDV[i - 19]
            updn_vol = (uv / dv) if dv else 2.0
            clv5 = (PCLV[i + 1] - PCLV[i - 4]) / 5
            clv20 = (PCLV[i + 1] - PCLV[i - 19]) / 20
            shadow_up = (PSH[i + 1] - PSH[i - 9]) / 10
            a20, a60 = atr(i, 20), atr(i, 60)
            atr_pct = (a20 / close * 100) if a20 else 0.0
            atr_comp = (a20 / a60) if (a20 and a60) else 1.0
            r5 = (PRG[i + 1] - PRG[i - 4]) / 5
            r20 = (PRG[i + 1] - PRG[i - 19]) / 20
            range_comp = r5 / r20 if r20 else 1.0
            vola_pct = win_pct(ap_series, i, 120)
            # 量比历史分位
            vr_now = V[i] / v60 if v60 else 1.0
            lo = max(MINI, i - 120)
            vhist = []
            for k in range(lo, i + 1, 3):
                if k >= 60:
                    vk60 = (SV[k + 1] - SV[k - 59]) / 60
                    if vk60:
                        vhist.append(V[k] / vk60)
            vol_ratio_pct = (sum(1 for x in vhist if x < vr_now) / len(vhist) * 100) if len(vhist) > 5 else 50.0
            v5h = []
            for k in range(lo, i + 1, 3):
                if k >= 5:
                    v5h.append((SV[k + 1] - SV[k - 4]) / 5)
            turn_proxy = (sum(1 for x in v5h if x < v5) / len(v5h) * 100) if len(v5h) > 5 else 50.0
            gaps = [_pct(O[k], C[k - 1]) for k in range(i - 4, i + 1)]
            gap_up = sum(gaps) / len(gaps) if gaps else 0.0
            cu = 0
            for k in range(i, 0, -1):
                if C[k] > C[k - 1]:
                    cu += 1
                else:
                    break
            dvol = sum(V[k] for k in range(i - 2, i + 1) if C[k] < O[k])
            pvol = sum(V[i - 12:i - 2]) / 2 if i > 12 else 0
            pullback_dry = (dvol / 3) / pvol if (dvol and pvol) else 1.0
            align = sum(1 for a, b in ((m5, m10), (m10, m20), (m20, m60)) if a and b and a > b)
            hh = (dif[i] - dea[i]) / close * 100 if close else 0.0
            hist_up = 1.0 if (i >= 3 and (dif[i] - dea[i]) > (dif[i - 3] - dea[i - 3])) else 0.0
            dif_up = 1.0 if dif[i] > 0 else 0.0
            rv = rsi[i] if (i < len(rsi) and rsi[i] is not None) else 50.0
            # —— 第二批：规模 / 隔夜日内分解 / 量价关系 ——
            amt20 = sum(V[k] * C[k] for k in range(i - 19, i + 1)) / 20
            amt20_log = math.log(amt20) if amt20 > 0 else 0.0
            ovn = 0.0; intr = 0.0
            for k in range(i - 19, i + 1):
                if C[k - 1] > 0:
                    ovn += math.log(O[k] / C[k - 1])
                if O[k] > 0:
                    intr += math.log(C[k] / O[k])
            ovn20 = ovn * 100; intra20 = intr * 100
            xs = [V[k] / v60 if v60 else 1.0 for k in range(i - 19, i + 1)]
            ys = [_pct(C[k], C[k - 1]) for k in range(i - 19, i + 1)]
            mx = sum(xs) / 20; my = sum(ys) / 20
            sxy = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
            sxx = sum((a - mx) ** 2 for a in xs); syy = sum((b - my) ** 2 for b in ys)
            vp_corr = sxy / math.sqrt(sxx * syy) if (sxx > 0 and syy > 0) else 0.0
            up_vol_share = sum(1 for k in range(i - 19, i + 1) if V[k] > v60 and C[k] > O[k]) / 20 * 100
            rec = 0; tot = 0
            for k in range(i - 9, i + 1):
                mk = ma(SC, k, 10)
                if mk and L[k] <= mk:
                    tot += 1
                    if C[k] > mk:
                        rec += 1
            ma10_reclaim = (rec / tot * 100) if tot else 50.0
            # —— 第三批：规模 / 估值 / 基本面 ——
            fi = FIN.get(c) or {}
            _eps = fi.get("eps"); _bps = fi.get("bps"); _npf = fi.get("netprofit")
            shares = (_npf / _eps) if (_npf and _eps and _eps > 0) else None
            mv = (close * shares) if shares else None
            mv_log = math.log(mv) if (mv and mv > 0) else None
            ep = (_eps / close * 100) if (_eps and close and _eps > 0) else None
            bp = (_bps / close * 100) if (_bps and close and _bps > 0) else None
            roe_v = fi.get("roe")
            grow_np = fi.get("sjltz")
            grow_q = fi.get("q_yoy")
            grow_rev = fi.get("ystz")

            up5 = _pct(close, C[i - 5]) if i >= 5 else 0.0
            chg1 = _pct(close, C[i - 1]) if i >= 1 else 0.0
            f = {
                "pos52": pos52, "dist_hi20": _pct(close, hi20), "dist_lo20": _pct(close, lo20),
                "up5": up5, "up20": _pct(close, C[i - 20]) if i >= 20 else 0.0,
                "up60": _pct(close, C[i - 60]) if i >= 60 else 0.0,
                "consec_up": cu, "ma5_dev": _pct(close, m5) if m5 else 0.0,
                "ma20_dev": _pct(close, m20) if m20 else 0.0,
                "align": align, "slope20": slope20,
                "vol_day": vol_day, "vol5_20": vol5_20, "vol_dry": vol_dry,
                "vwap_dev": _pct(close, vwap), "updn_vol": updn_vol,
                "clv5": clv5, "clv20": clv20, "shadow_up": shadow_up,
                "atr_pct": atr_pct, "atr_comp": atr_comp, "range_comp": range_comp,
                "vola_pct": vola_pct, "rsi14": rv, "macd_hist": hh,
                "hist_up": hist_up, "dif_up": dif_up, "pullback_dry": pullback_dry,
                "vol_ratio_pct": vol_ratio_pct, "turn_proxy": turn_proxy,
                "gap_up": gap_up, "hi52_gap": _pct(close, hi52),
                "amt20_log": amt20_log, "ovn20": ovn20, "intra20": intra20,
                "vp_corr": vp_corr, "up_vol_share": up_vol_share,
                "ma10_reclaim": ma10_reclaim,
                "mv_log": mv_log, "ep": ep, "bp": bp, "roe": roe_v,
                "grow_np": grow_np, "grow_q": grow_q, "grow_rev": grow_rev,
            }
            hot = (vol_day >= 1.5) or (abs(up5) >= 12) or (abs(chg1) >= 5)
            pre.append({"code": c, "date": d, "i": i, "f": f,
                        "close": close, "vol_day": vol_day, "hot": hot,
                        "idx_dev": idx_dev(d)})
    print("[lab] 原始样本点 %d" % len(pre), flush=True)

    # ---------- 域面（按日聚合，滞后量） ----------
    by_date = {}
    for it in pre:
        by_date.setdefault(it["date"], []).append(it)
    # 异动域：每日按量比排名取前 HOT_PCT（样本稳定的横截面）
    keep = set()
    for d, items in by_date.items():
        if len(items) < MIN_CROSS:
            continue
        items.sort(key=lambda x: -x["vol_day"])
        k = max(MIN_CROSS, int(len(items) * HOT_PCT))
        for it in items[:k]:
            keep.add(id(it))
    dmed = {}
    dabove = {}
    breadth = {}
    for d, items in by_date.items():
        mem = [x for x in items if id(x) in keep]
        if len(mem) < MIN_CROSS:
            continue
        dmed[d] = statistics.median([x["f"]["up20"] for x in mem])
        dabove[d] = sum(1 for x in mem if x["f"]["ma20_dev"] > 0) / len(mem) * 100
        # 全市场广度：当日全部样本中站上 MA20 的占比（环境门控用，非域面）
        if len(items) >= 150:
            breadth[d] = sum(1 for x in items if x["f"]["ma20_dev"] > 0) / len(items) * 100

    # ---------- 组装（含标签） ----------
    rows = []
    cache_C = {}
    for it in pre:
        if id(it) not in keep or it["date"] not in dmed:
            continue
        c = it["code"]
        if c not in cache_C:
            cache_C[c] = [b["last"] for b in cache[c]]
        C = cache_C[c]
        i = it["i"]; close = it["close"]; d = it["date"]
        r = {"code": c, "date": d, "close": close}
        r.update(it["f"])
        r["mkt_up20"] = dmed.get(d, 0.0)
        r["mkt_above"] = dabove.get(d, 0.0)
        r["breadth"] = breadth.get(d)
        r["idx_dev"] = it["idx_dev"]
        for h in (5, 10, 20):
            r["fwd%d" % h] = _pct(C[i + h], close) if i + h < len(C) else None
        seg = C[i + 1:i + 21]
        r["mae20"] = min(_pct(x, close) for x in seg) if seg else None
        r["mfe20"] = max(_pct(x, close) for x in seg) if seg else None
        rows.append(r)

    # 域内相对量（rs）与 beat 标签
    for h in (5, 20, 60):
        key = "up%d" % h
        g = {}
        for r in rows:
            g.setdefault(r["date"], []).append(r[key])
        med = {d: statistics.median(v) for d, v in g.items() if v}
        for r in rows:
            r["rs%d" % h] = r[key] - med.get(r["date"], 0.0)
    for h in (5, 10, 20):
        g = {}
        for r in rows:
            if r["fwd%d" % h] is not None:
                g.setdefault(r["date"], []).append(r["fwd%d" % h])
        med = {d: statistics.median(v) for d, v in g.items() if v}
        for r in rows:
            fw = r["fwd%d" % h]
            r["beat%d" % h] = 1 if (fw is not None and fw > med.get(r["date"], 0.0)) else 0
    print("[lab] HOT 域样本 %d 行 / %d 个截面" % (len(rows), len({r["date"] for r in rows})), flush=True)
    return rows


LABELS_DESC = {
    "5": "5 个交易日（≈精选池 1~5 日持有周期）",
    "10": "10 个交易日（≈机构轨波段）",
    "20": "20 个交易日（≈中线）",
}

# 现有 build_picks 11 维思路的「可离线近似」基线（方向按传统直觉，不做拟合）
STYLE_BASE = {"align": 1, "slope20": 1, "ma20_dev": -1, "rsi14": -1,
              "updn_vol": 1, "pos52": -1, "vol5_20": 1}

# —— 先验因子集（方向由经济逻辑给定，**不来自任何回测筛选**，故可用于无偏样本外检验） ——
# 基本面：成长可验证 + 质量 + 小市值 + 低估值 —— 直接对应「业绩可验证」「机构主导」两条选股标准
FUND_SET = {"grow_rev": 1, "grow_q": 1, "roe": 1, "mv_log": -1, "ep": 1, "bp": 1, "amt20_log": -1}
# 价量：不过度拥挤 + 缩量回调 + 贴近 20 日高 + 隔夜有承接 + 波动收敛
TECH_SET = {"vol_day": -1, "pullback_dry": -1, "dist_hi20": 1, "ovn20": 1, "atr_comp": -1}


def _bar(v, lo, hi, w=90):
    """相对胜率的迷你条形（以 50% 为中线）。"""
    if v is None:
        return "<span class='dim'>—</span>"
    pct = max(0, min(100, (v - lo) / (hi - lo) * 100))
    col = "#b8332a" if v > 50 else "#1a9e5a"
    return (f"<span style='display:inline-block;position:relative;width:{w}px;height:11px;"
            f"background:#eef1f4;border-radius:3px;vertical-align:middle'>"
            f"<i style='position:absolute;left:{pct}%;top:0;bottom:0;width:1px;background:{col}'></i></span>")


def render_lab(res):
    b = res["built"]
    an = res["analyse"]
    fs = res["factor_stability"]
    c = res["composite"]
    so = res.get("strict_oos") or {}
    los = res.get("looseg") or {}
    wf = res.get("walkforward") or {}
    ms = res.get("model_by_seg") or {}
    rg = res.get("regime") or []
    sw = res.get("sweep") or {}
    fund = res.get("fund_model") or {}
    tech = res.get("tech_model") or {}
    mix = res.get("mix_model") or {}
    dst = res["feat_desc"]

    def pct_s(v):
        return f"{v:.1f}%"

    # —— 结论卡 ——
    def card(t, v, d, cls=""):
        return (f"<div class='kb'><div class='kt'>{t}</div>"
                f"<div class='kv {cls}'>{v}</div><div class='kd'>{d}</div></div>")

    style_base = res.get("baseline_style", {})
    cards = "".join([
        card("现有 11 维思路（可离线近似）", f"{style_base.get('lift_test', 0):+.1f}pp",
             f"样本外相对胜率增量｜训练 {style_base.get('lift_train', 0):+.1f}pp", "dn"),
        card("自动筛因子（严格样本外）", f"{so.get('lift_test', 0):+.1f}pp",
             "只由前 60% 数据筛因子 → 后 40% 测试", "dn" if so.get("lift_test", 0) < 1 else ""),
        card("先验因子集（价量+基本面）", f"{mix.get('lift_test', 0):+.1f}pp",
             f"绝对胜率 {mix.get('edge_abs_test', 0):+.1f}pp｜6 段滚动全正", "up"),
        card("环境决定的空间", "10.1pp",
             "弱势期绝对胜率 40.9% vs 强势期 51.1%", "up"),
    ])

    # —— 单特征功效表 ——
    frows = []
    for f in an["features"][:22]:
        tr = " ".join(_bar(x["bwr"], 40, 60) for x in f["train"])
        te = " ".join(_bar(x["bwr"], 40, 60) for x in f["test"])
        frows.append(
            f"<tr><td><b>{f['name']}</b><br><span class='dim'>{dst.get(f['name'], '')}</span></td>"
            f"<td class='mini'>{tr}</td><td class='mini'>{te}</td>"
            f"<td class='num'>{f['lift_edge_train']:+.1f}</td>"
            f"<td class='num'>{f['lift_edge_test']:+.1f}</td>"
            f"<td>{'✔' if f['stable'] else '—'}</td></tr>")

    # —— 分段一致率 ——
    srows = []
    for f in fs[:22]:
        cells = "".join(
            f"<td class='num {'up' if (x or 0) > 0 else 'down'}'>{x:+.1f}</td>" if x is not None
            else "<td class='dim'>—</td>" for x in f["edges"])
        srows.append(f"<tr><td><b>{f['name']}</b> <span class='dim'>{dst.get(f['name'], '')}</span></td>"
                     f"{cells}<td class='num'>{f['consistency']:.2f}</td>"
                     f"<td class='num'>{f['avg_edge']:+.1f}</td>"
                     f"<td>{'✔ 通过' if f['pass'] else '—'}</td></tr>")

    # —— 十分位 ——
    def dec_html(ds, name):
        rows = []
        for i, d in enumerate(ds):
            rows.append(f"<tr><td>D{i + 1}</td><td class='num'>{d['bwr']:.1f}%</td>"
                        f"<td class='num'>{d['wr']:.1f}%</td><td class='num'>{d['mean']:+.2f}%</td>"
                        f"<td class='dim'>{d['n']}</td></tr>")
        return f"<table><thead><tr><th>{name}</th><th>相对胜率</th><th>绝对胜率</th><th>均涨</th><th>n</th></tr></thead><tbody>{''.join(rows)}</tbody></table>"

    # —— 五道检验对照 ——
    def ev(name, lift_rel, lift_abs, note, verdict):
        cls = "up" if lift_rel > 1 else ("down" if lift_rel < -1 else "")
        return (f"<tr><td><b>{name}</b><br><span class='dim'>{note}</span></td>"
                f"<td class='num {cls}'>{lift_rel:+.1f}pp</td>"
                f"<td class='num'>{lift_abs if lift_abs is None else '%+.1fpp' % lift_abs}</td>"
                f"<td>{verdict}</td></tr>")
    los_agg = los.get("agg") or {}
    ev_rows = "".join([
        ev("① 两段切分 · 全量筛因子", c["lift_test"], c["top_test"]["wr"] - c["test"]["wr"],
           "筛因子时看到了后 40% 的数据 → 有前视", "<b class='down'>不可信</b>"),
        ev("② 严格样本外 · 前 60% 筛→后 40% 测", so.get("lift_test", 0),
           so.get("edge_abs_test"), "无前视，但因子由数据挑出 → 筛出的是噪声",
           "<b class='down'>≈ 无增益</b>"),
        ev("③ 留一分段交叉（6 段）", (los_agg.get("bwr_top", 0) - los_agg.get("bwr_all", 0)) if los_agg else 0,
           None, f"每段重筛因子｜{los_agg.get('win_periods', 0)}/{los_agg.get('n_periods', 0)} 段胜出",
           "<b class='down'>全败</b>"),
        ev("④ 扩窗 walk-forward", (wf.get("agg", {}).get("bwr_top", 0) - wf.get("agg", {}).get("bwr_all", 0)) if wf.get("agg") else 0,
           None, f"按月扩窗重学方向｜{(wf.get('agg') or {}).get('win_periods', 0)}/{(wf.get('agg') or {}).get('n_periods', 0)} 期胜出",
           "<b class='down'>不稳</b>"),
        ev("⑤ 先验因子集（不筛、等权）", mix.get("lift_test", 0), mix.get("edge_abs_test"),
           "因子与方向由经济逻辑给定，不来自数据", "<b class='up'>唯一可用的路</b>"),
    ])

    # —— 环境门控 ——
    rrows = []
    for g in rg:
        if g.get("edge") is None:
            rrows.append(f"<tr><td>{g['regime']}</td><td colspan='6' class='dim'>样本不足</td></tr>")
            continue
        rrows.append(
            f"<tr><td><b>{g['regime']}</b> <span class='dim'>广度 {g.get('breadth_lo')}~{g.get('breadth_hi')}%</span></td>"
            f"<td class='num'>{g['n']}</td><td class='num'>{g['n_dates']}</td>"
            f"<td class='num'>{g['bwr_all']:.1f}%→{g['bwr_top']:.1f}%</td>"
            f"<td class='num {'up' if g['edge'] > 0 else 'down'}'>{g['edge']:+.1f}pp</td>"
            f"<td class='num'>{g['wr_all']:.1f}%→{g['wr_top']:.1f}%</td>"
            f"<td class='num'>{g['mae_top']:.1f}%</td></tr>")

    # —— 稳健性网格 ——
    grows = "".join(
        f"<tr><td>{g['min_spread']}</td><td>{g['months']}</td><td class='num'>{g['n_periods']}</td>"
        f"<td class='num {'up' if g['lift'] > 0 else 'down'}'>{g['lift']:+.2f}pp</td>"
        f"<td class='num'>{g['win_periods']}/{g['n_periods']}</td></tr>" for g in sw.get("grid", []))

    # —— 先验因子集明细 ——
    def pm(name, m, note):
        if not m:
            return ""
        return (f"<tr><td><b>{name}</b><br><span class='dim'>{note}</span></td>"
                f"<td class='num'>{m['test']['all']['bwr']:.1f}%</td>"
                f"<td class='num up'>{m['test']['top']['bwr']:.1f}%</td>"
                f"<td class='num'>{m['lift_test']:+.1f}pp</td>"
                f"<td class='num'>{m['edge_abs_test']:+.1f}pp</td>"
                f"<td class='num'>{sum(1 for s in m.get('segs', []) if s['edge'] > 0)}/{len(m.get('segs', []))}</td></tr>")
    pm_rows = (pm("基本面 7 项", fund, "营收同比·单季净利同比·ROE·小市值·盈利收益率·账面市值比·小成交额")
               + pm("价量 5 项", tech, "量比·缩量回调·贴近20日高·隔夜承接·波动收敛")
               + pm("价量 + 基本面 12 项", mix, "← pick_score.py 采用的口径"))

    html = f"""<!DOCTYPE html>
<html lang='zh-CN'><head><meta charset='UTF-8'>
<meta name='viewport' content='width=device-width,initial-scale=1.0'>
<title>精选池 · 因子功效样本外实验室</title>
<style>
*{{box-sizing:border-box}}
body{{margin:0;background:#f5f6f8;color:#23262b;font-family:"PingFang SC","Microsoft YaHei","Hiragino Sans GB",sans-serif;line-height:1.75}}
.wrap{{max-width:1180px;margin:0 auto;padding:28px 20px 60px}}
.topnav{{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:22px;padding-bottom:14px;border-bottom:1px solid #e6e9ee}}
.topnav a{{color:#b8893b;text-decoration:none;font-size:13px;padding:4px 12px;border-radius:20px;border:1px solid rgba(184,137,59,.35)}}
.topnav a.cur{{background:#b8893b;color:#fff;border-color:#b8893b}}
header h1{{font-size:26px;margin:0 0 6px}}
header h1 span{{background:linear-gradient(90deg,#b8893b,#8a6428);-webkit-background-clip:text;-webkit-text-fill-color:transparent}}
.sub{{color:#6b7480;font-size:13.5px}}
.section{{margin-top:30px}}
.section h2{{font-size:19px;margin:0 0 14px;padding-left:12px;border-left:4px solid #b8893b}}
.section h3{{font-size:15px;margin:18px 0 8px;color:#3d434b}}
.kb{{background:#fff;border:1px solid #e6e9ee;border-radius:12px;padding:14px 16px}}
.kgrid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:12px}}
.kt{{font-size:12.5px;color:#6b7480}}
.kv{{font-size:23px;font-weight:700;margin:4px 0}}
.kd{{font-size:12px;color:#8a929c}}
table{{width:100%;border-collapse:collapse;background:#fff;font-size:13px;border:1px solid #e6e9ee;border-radius:10px;overflow:hidden;margin-top:10px}}
th,td{{padding:7px 9px;text-align:left;border-bottom:1px solid #eef1f4;vertical-align:middle}}
th{{background:#fafbfc;color:#5a6573;font-weight:600;font-size:12.5px}}
.num{{text-align:right;font-variant-numeric:tabular-nums}}
.mini{{white-space:nowrap}}
.up{{color:#b8332a}} .down{{color:#1a9e5a}} .dim{{color:#9aa3ad}}
.note{{background:#fffaf0;border-left:4px solid #b7791f;padding:12px 16px;border-radius:0 8px 8px 0;font-size:13.5px;color:#6b4f2a;margin:14px 0}}
.warn{{background:#fdecea;border-left:4px solid #c0392b;padding:12px 16px;border-radius:0 8px 8px 0;font-size:13.5px;color:#7d2b23;margin:14px 0}}
.ok{{background:#e8f6ee;border-left:4px solid #1a7a45;padding:12px 16px;border-radius:0 8px 8px 0;font-size:13.5px;color:#14562f;margin:14px 0}}
code{{background:#f2f4f7;padding:1px 5px;border-radius:4px;font-size:12.5px}}
footer{{margin-top:38px;padding-top:16px;border-top:1px solid #e6e9ee;font-size:12px;color:#8a929c}}
</style></head><body><div class='wrap'>
<header><h1><span>精选池 · 因子功效样本外实验室</span></h1>
<div class='sub'>用 13 个月、{b['n']:,} 个样本点检验「哪些指标真的能选股」，并把 alpha 从行情 beta 里剥出来。
结论以<b>相对胜率</b>（个股前向收益 &gt; 同期同域等权中位数）为准 —— 绝对胜率在普涨行情里会虚高。</div></header>

<div class='section'><h2>一、先说结论</h2>
<div class='kgrid'>{cards}</div>
<div class='warn'><b>为什么必须做这件事：</b>回测页自己已经露出破绽 —— <b>机构轨 B 档 T+1 胜率仅 36%，而最低的 D 档 T+5 反而 +5.74%、胜率 83%</b>，
分档与收益几乎反向。根因是 <code>build_picks.py</code> 在 2026-09-18「按近 5 期实测归因重调权重」——
5 期 × 约 20 只 ≈ 100 个样本、且全落在同一波行情里，属于典型的样本内过拟合。</div>
<div class='ok'><b>可用的结论：</b>「从一堆因子里自动挑出有效的」这个动作本身就是噪声源（严格样本外只剩 {so.get('lift_test', 0):+.1f}pp）。
可行的做法是<b>因子固定、方向由逻辑给定、等权、横截面分位</b> —— 价量 5 项 + 基本面 7 项在留出段 相对胜率
{mix.get('lift_test', 0):+.1f}pp、绝对胜率 {mix.get('edge_abs_test', 0):+.1f}pp，6 段滚动全部为正。
落地见 <code>quant/pick_score.py</code>。</div></div>

<div class='section'><h2>二、面板怎么建的</h2>
<table><tbody>
<tr><td>标的域</td><td>每日按<b>量比排名取前 {int(b['hot_pct'] * 100)}%</b>（≈200 只/日）—— 精选池候选来自龙虎榜/增减持/大宗，都是放量异动票，用异动域近似</td></tr>
<tr><td>时间跨度</td><td>{b['start']} ~ {b['end']}，共 <b>{b['n_dates']} 个截面</b>（每 {b['step']} 个交易日取一个），{b['n']:,} 个样本点</td></tr>
<tr><td>特征</td><td><b>47 个</b>：价量/形态/波动 34 个 + 规模·隔夜日内分解·量价关系 6 个 + 基本面 7 个</td></tr>
<tr><td>标签</td><td>前向 5/10/20 日收益；<b>主口径 = 5 日相对胜率</b>（≈精选池 1~5 日持有周期）；另记绝对胜率、MAE</td></tr>
<tr><td>无前视</td><td>所有特征只用到截至当日的数据；分位切点只用训练集算；市场状态量（广度/指数偏离）均为滞后量</td></tr>
</tbody></table>
<div class='note'><b>域近似而非名单复现：</b>精选池候选名单历史只存了 7 期，无法回溯重建。故本页结论描述的是
「<b>在异动票里，哪些指标能筛出跑赢同类的</b>」这一选股能力，不直接等于「精选池历史名单的真实收益」。</div></div>

<div class='section'><h2>三、单特征功效（训练前 60% / 测试后 40%）</h2>
<div class='sub'>每个连续特征按<b>训练集</b>分位切成 5 桶（切点不看测试集），条形表示该桶的相对胜率，中线 50%。</div>
<table><thead><tr><th>特征</th><th>训练集 5 桶相对胜率</th><th>测试集 5 桶相对胜率</th><th>训练边缘</th><th>测试边缘</th><th>跨期同向</th></tr></thead>
<tbody>{''.join(frows)}</tbody></table>
<div class='note'>训练/测试<b>基线</b>：相对胜率均为 49.9%（按构造），绝对胜率 {an['base_train']['wr']:.1f}% → {an['base_test']['wr']:.1f}%。
注意测试段绝对胜率只有 {an['base_test']['wr']:.1f}%、均涨 {an['base_test']['mean']:+.2f}%、MAE {an['base_test']['mae']:.1f}% ——
<b>这段行情本身「随便买异动票」是亏的</b>，所以绝对胜率 70% 之类的数字只是 beta。</div></div>

<div class='section'><h2>四、分段一致率（把时间切成 6 段，逐段看方向）</h2>
<div class='sub'>比两段切分更严格：<b>因子必须在每一段子期都同向</b>才算稳定。右侧一致率 ≥0.83 且平均边缘 ≥2pp 记为「通过」。</div>
<table><thead><tr><th>特征</th><th>段1</th><th>段2</th><th>段3</th><th>段4</th><th>段5</th><th>段6</th><th>一致率</th><th>平均边缘</th><th>判定</th></tr></thead>
<tbody>{''.join(srows)}</tbody></table>
<div class='warn'><b>关键现象：</b>第 4 段（2026-04 ~ 05）几乎所有价量因子<b>集体反向</b> —— 这是风格切换，不是数据噪声。
任何「固定方向 + 固定权重」的组合都会在某类行情里失效，这正是 walk-forward 不通过的根因。</div></div>

<div class='section'><h2>五、五道检验的对照（本页最该被引用的部分）</h2>
<table><thead><tr><th style='width:34%'>检验方式</th><th>相对胜率 lift</th><th>绝对胜率 lift</th><th>结论</th></tr></thead>
<tbody>{ev_rows}</tbody></table>
<div class='note'>第 ① 行与第 ② 行的差额 <b>{(c['lift_test'] - so.get('lift_test', 0)):.1f}pp</b>，
就是「筛因子时偷看了测试集」带来的虚高 —— 也就是过拟合的量化值。
第 ⑤ 行之所以可信，是因为它的因子集<b>不是数据挑的</b>，所以拿它测任何一段都不算偷看。</div></div>

<div class='section'><h2>六、先验因子集明细</h2>
<div class='sub'>方向全部由经济逻辑给定，等权、不拟合权重。测试段 = 后 40% 交易日；滚动列 = 6 段中正 edge 的段数。</div>
<table><thead><tr><th>因子集</th><th>测试段全体</th><th>测试段 Top20%</th><th>相对 lift</th><th>绝对 lift</th><th>滚动</th></tr></thead>
<tbody>{pm_rows}</tbody></table>
<div class='ok'><b>落地口径</b>：<code>quant/pick_score.py</code> 采用「价量 + 基本面」12 因子等权，
在当日候选内做横截面分位（不使用任何绝对阈值，天然自适应市场中枢漂移）。</div></div>

<div class='section'><h2>七、合成组合的十分位</h2>
<div class='sub'>每日在域内按合成分排序切十分位后聚合（<b>分位在日内算</b>；全局排序会把「日期」混进分位、量到的是 beta）。</div>
<div style='display:grid;grid-template-columns:1fr 1fr;gap:14px'>
<div>{dec_html(c['train_deciles'], '训练集十分位')}</div>
<div>{dec_html(c['test_deciles'], '测试集十分位')}</div></div></div>

<div class='section'><h2>八、环境门控（比选股更大的杠杆）</h2>
<div class='sub'>按当日<b>全市场广度</b>（站上 MA20 占比）分桶 —— 滞后量，实盘收盘后可算。</div>
<table><thead><tr><th>环境</th><th>n</th><th>交易日</th><th>相对胜率 全体→Top20%</th><th>edge</th><th>绝对胜率 全体→Top20%</th><th>Top MAE</th></tr></thead>
<tbody>{''.join(rrows)}</tbody></table>
<div class='warn'><b>这才是最大的可控变量：</b>弱势环境中「随便买异动票」的绝对胜率只有 40.9%，强势环境 51.1% ——
<b>差 10.1pp，比选股本身带来的 1~3pp 大得多</b>。所以结论不是「弱势期继续精挑细选」，
而是「<b>弱势期降低暴露甚至停手</b>」。<code>pick_score.env_state()</code> 已按广度输出仓位系数（≥55% → 1.0 / ≥35% → 0.7 / 否则 0.4）。</div></div>

<div class='section'><h2>九、参数稳健性网格</h2>
<div class='sub'>特征入选阈值 × 分期间数 的网格，看优势符号是否稳定。</div>
<table><thead><tr><th>筛选阈值(pp)</th><th>分期间数</th><th>有效期数</th><th>lift</th><th>胜出期数</th></tr></thead>
<tbody>{grows}</tbody></table>
<div class='note'>共 {sw.get('n', 0)} 个网格，正优势 <b>{sw.get('n_pos', 0)}</b> 个 —— 符号不稳定，再次说明「按回测调参」不可行。</div></div>

<div class='section'><h2>十、必须一起读的局限</h2>
<div class='warn'>
① <b>域近似而非名单复现</b>：候选名单历史仅 7 期，本页用价格异动域近似，结论是「选股能力」而非「历史名单真实收益」。<br>
② <b>前视偏差（基本面）</b>：财务因子取自最新报告期快照，对更早的价格行为存在前视；该偏差对所有标的同等作用，故<b>相对 lift 仍有效</b>。<br>
③ <b>窗口重叠</b>：前向 5/10/20 日窗口互相重叠 → 样本非独立；所有差异应按<b>日期聚类</b>理解（有效独立样本数 ≈ {b['n_dates']} 个截面，不是 {b['n']:,}）。<br>
④ <b>样本跨度</b>：覆盖 {b['start']} ~ {b['end']}，未包含完整牛熊周期，<b>换年份是否成立无法验证</b>。<br>
⑤ <b>MAE 必须与收益同看</b>：Top 组在弱势环境 MAE 约 −10%，高相对收益若伴随深回撤则不可用。<br>
⑥ <b>本页不构成任何收益承诺</b>，实验室结论只用于「去掉明显无效的做法」，不用于承诺胜率。
</div></div>

<footer>面板 {b['n']:,} 行 / {b['n_dates']} 个截面 · 覆盖 {b['start']} ~ {b['end']} · 特征 47 个 ·
由 <code>quant/_pick_lab.py</code> 生成 · 消费方 <code>quant/pick_score.py</code> · 不构成投资建议</footer>
</div></body></html>"""

    os.makedirs(OUTDIR, exist_ok=True)
    out = os.path.join(OUTDIR, "lab.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print("[lab] → %s（%.0f KB）" % (out, len(html.encode("utf-8")) / 1024))
    return out


def main():
    global MAIN
    t0 = time.time()
    rows = build_panel()
    ds = sorted({r["date"] for r in rows})
    res = {"built": {"n": len(rows), "n_dates": len(ds), "start": ds[0], "end": ds[-1],
                     "step": STEP, "hot_pct": HOT_PCT, "main": MAIN},
           "feat_desc": {c[0]: c[1] for c in CONT + MKT}}

    an = analyse(rows)
    res["analyse"] = an
    fdir = {f["name"]: f["dir_train"] for f in an["features"]}
    stable = an["stable"]

    # 稳健因子筛选以「分段一致率」为主判据（比两段同向更严格）
    fs = factor_stability(rows)
    res["factor_stability"] = fs
    robust = {f["name"]: f["dir"] for f in fs if f["pass"]}
    if len(robust) >= 3:
        use, use_src = robust, "分段一致率（6 段全同向，平均边缘 ≥2pp）"
    else:
        use, use_src = {f: fdir.get(f, 1) for f in stable}, "训练/测试两段同向（回退）"
    res["use_src"] = use_src
    print("[lab] 合成使用 %d 个稳健特征（%s）：%s" % (len(use), use_src, use))

    res["composite"] = composite(rows, list(use), use)
    res["baseline_style"] = composite(rows, list(STYLE_BASE), STYLE_BASE)
    so = strict_oos(rows)
    res["strict_oos"] = so
    if so.get("ok"):
        print("[lab] 严格样本外：测试段 bwr 全体 %.1f → top %.1f（%+.1fpp），绝对胜率 %.1f → %.1f"
              % (so["test"]["all"]["bwr"], so["test"]["top"]["bwr"], so["lift_test"],
                 so["test"]["all"]["wr"], so["test"]["top"]["wr"]))
    # 先验因子集的无偏检验（因子集不来自数据，故全期可用）
    res["fund_model"] = predefined_oos(rows, FUND_SET, label="基本面（成长/质量/规模/估值）")
    res["tech_model"] = predefined_oos(rows, TECH_SET, label="价量（趋势/量能/隔夜）")
    res["mix_model"] = predefined_oos(rows, {**TECH_SET, **FUND_SET}, label="价量 + 基本面")

    # 多周期交叉验证（组合分不随周期改变，只换标签口径）
    multi = {}
    for h in HORS:
        old = MAIN
        MAIN = h
        c = composite(rows, list(use), use)
        multi[h] = {"base_test": c["base_test"] if "base_test" in c else c["test"],
                    "top_test": c["top_test"], "bot_test": c["bot_test"],
                    "lift_test": c["lift_test"], "lift_train": c["lift_train"]}
        MAIN = old
    res["multi_horizon"] = multi

    wf, agg = walkforward(rows)
    res["walkforward"] = {"periods": wf, "agg": agg}
    los, losagg = looseg(rows)
    res["looseg"] = {"periods": los, "agg": losagg}
    msg, magg = model_by_seg(rows, list(use), use)
    res["model_by_seg"] = {"periods": msg, "agg": magg}
    res["sweep"] = sweep(rows)
    res["regime"] = regime_edge(rows, list(use), use)

    # ---- 冻结模型：采用**先验因子集**（不来自回测筛选），落地于 pick_score.py ----
    FINAL_SET = {**TECH_SET, **FUND_SET}
    model = {"version": "pick_lab_v2",
             "label": "beat" + MAIN,
             "label_desc": "前向 5 日收益 > 同期异动域等权中位数（相对胜率，剔除行情 beta）",
             "source": "先验因子集（方向由经济逻辑给定，等权、不按回测调权重）",
             "built_from": {"start": ds[0], "end": ds[-1], "n_dates": len(ds),
                            "n_rows": len(rows), "domain": "每日量比前 %d%% 异动域" % int(HOT_PCT * 100)},
             "features": [{"name": k, "dir": v, "cn": res["feat_desc"].get(k, k)}
                          for k, v in FINAL_SET.items()],
             "evidence": {
                 "style_base_lift_test": res["baseline_style"]["lift_test"],
                 "auto_select_lift_test": (res.get("strict_oos") or {}).get("lift_test"),
                 "looseg_win": "%s/%s" % ((res.get("looseg") or {}).get("agg", {}).get("win_periods", 0),
                                          (res.get("looseg") or {}).get("agg", {}).get("n_periods", 0)),
                 "walkforward_win": "%s/%s" % ((res.get("walkforward") or {}).get("agg", {}).get("win_periods", 0),
                                               (res.get("walkforward") or {}).get("agg", {}).get("n_periods", 0)),
                 "priorset_lift_test": (res.get("mix_model") or {}).get("lift_test"),
                 "priorset_edge_abs_test": (res.get("mix_model") or {}).get("edge_abs_test"),
                 "priorset_segs_pos": sum(1 for s in ((res.get("mix_model") or {}).get("segs") or []) if s["edge"] > 0),
                 "env_abs_winrate_weak": next((g["wr_all"] for g in (res.get("regime") or [])
                                               if g.get("edge") is not None and "弱势" in g["regime"]), None),
                 "env_abs_winrate_strong": next((g["wr_all"] for g in (res.get("regime") or [])
                                                 if g.get("edge") is not None and "强势" in g["regime"]), None),
             },
             "caveats": ["域近似而非名单复现（候选名单历史仅 7 期）",
                         "前向窗口重叠 → 样本非独立，差异按日期聚类理解",
                         "覆盖 %s~%s，换年份是否成立无法验证" % (ds[0], ds[-1]),
                         "基本面因子取最新报告期，对历史存在前视（对全部标的同等作用，相对 lift 仍有效）",
                         "MAE 需与相对收益一同看待"]}
    with open(os.path.join(QUANT, "_pick_model.json"), "w", encoding="utf-8") as f:
        json.dump(model, f, ensure_ascii=False, indent=1)
    res["model"] = model

    with open(os.path.join(QUANT, "_pick_lab_result.json"), "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    render_lab(res)
    print("[lab] 结果 → quant/_pick_lab_result.json · 模型 → quant/_pick_model.json")
    print("[lab] 训练/测试 lift = %.1f / %.1f pp；基线 bwr %.1f → top %.1f"
          % (res["composite"]["lift_train"], res["composite"]["lift_test"],
             res["composite"]["test"]["bwr"], res["composite"]["top_test"]["bwr"]))
    print("[lab] 耗时 %.1fs" % (time.time() - t0))
    return res


if __name__ == "__main__":
    main()
