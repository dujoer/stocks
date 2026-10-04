# -*- coding: utf-8 -*-
"""主升精选 · 收益归因 + 退出规则网格（_selected_attrib.py）

用户问（2026-10-04）：「那怎么优化，我想筛选赚钱的」

已有体系（build_selected v2）：全市场正股域 → 9 先验因子等权横截面分位 → 前 5% A 档
→ 移动止盈退出（-12% 硬止损 / +6% 激活 / 3% 回撤 / 满 20 日强平）→ 环境门控二值。

本探针回答三个可证伪的问题
------------------------
  Q1 **收益归因**：A 档收益里多少来自「选股」（相对口径），多少只是「行情」（绝对口径）？
  Q2 **入场侧还有优化吗**：9 个因子里哪些两半同向（真稳定）、哪些两半反向（噪声/状态代理）？
  Q3 **退出侧还有优化吗**：现行 (-12/+6/3/20) 在整张退出网格里处于什么位置？
     是否存在「两半平均更优 **且** 两半同向」的参数？

方法论（skill quant-factor-oos-lab，逐条对应）
-------------------------------------------
  · 入场能力只看**前向收益分布**，绝不与退出规则混算（「退出规则冒充入场能力」是经典坑）；
  · 相对口径（前向收益 > 同日池面等权中位数）≈ alpha；绝对口径 = alpha + beta；
  · **两半对照是核心表**：同向才叫稳定，反向说明只是市场状态代理；
  · 退出网格按**两半平均**排名，不在测试半挑最优（那是又一次样本内拟合）；
  · 报胜率必须同时报**单笔均值**（胜率与单笔均值是一对权衡）。

⚠ 与 `_selected_lab.build_panel` 的两处刻意差异（本探针更严）
----------------------------------------------------------
  ① 采样日**统一对齐**：主升按「每票各自的位置」采样（range(MINI, n-FMAX, step)），
     不同票的采样日错位 → 横截面分位密度漂移（skill 坑表「采样日错位」）。
     本探针改为全市场交易日历 `cal[::step]` 统一采样。
  ② 额外存**完整前向收盘序列**（T+1..T+20），使任意持有期的到期平仓价都精确
     （主升面板只存 T+20 的 close，无法精确模拟 hold=5/10）。

用法
----
    python _selected_attrib.py --date 2026-09-30
    python _selected_attrib.py --date 2026-09-30 --step 10
"""
from __future__ import annotations
import os, sys, json, argparse, statistics, collections
from array import array

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _selected_lab as S
import _gate_common as G

ROOT = os.path.dirname(HERE)
QUANT = HERE
CACHE_TXK = S.CACHE                                  # 主升生产用（约 252 根 ≈ 10 个月）
CACHE_LONG = os.path.join(QUANT, "_long_kline.json")  # 长历史（约 780 根 ≈ 3 年）
OUT = os.path.join(QUANT, "_selected_attrib.json")

MINI = S.MINI
FMAX = S.FMAX
AMT_MIN = S.AMT_MIN
PRICE_MIN = S.PRICE_MIN
PRIOR = S.PRIOR
PRIOR_CN = S.PRIOR_CN

# 现行退出参数（要与 build_selected 一致；改动须同步）
CUR = {"stop": S.STOP, "act": S.ACT, "trail": S.TRAIL, "hold": S.MAXFWD}

# ---- 退出网格（先验给定，不做细密搜索；只为看现行参数在网格中的相对位置）----
GRID_STOP = [0.06, 0.08, 0.12, 0.15, 0.20]
GRID_ACT = [999.0, 0.0, 0.06, 0.10]   # 999=永不激活（只硬止损+到期）；0=买入即跟踪止盈；
                                      # 0.06=现行（浮盈6%才激活）；0.10=更晚激活
GRID_TRAIL = [0.03, 0.05, 0.08]
GRID_HOLD = [5, 10, 20]


def build_panel_ext(step=5, cache_path=None):
    """全市场可交易域面板（统一样本日）——每行带完整前向 C/H/L 序列。"""
    cache_path = cache_path or CACHE_TXK
    cache = json.load(open(cache_path, encoding="utf-8"))
    NM = {}
    try:
        NM = json.load(open(os.path.join(QUANT, "_stock_names.json"), encoding="utf-8"))
    except Exception:
        pass
    codes = [c for c in cache
             if (c.startswith("sh6") or c.startswith("sz0") or c.startswith("sz3"))
             and len(cache[c]) >= MINI + FMAX + 5]

    # 交易日历（覆盖度过滤，剔早期稀疏日）
    cover = collections.Counter()
    for c in codes:
        for b in cache[c]:
            cover[b["date"]] += 1
    cutoff = max(cover.values()) * 0.25 if cover else 0
    cal = sorted(d for d, n in cover.items() if n >= cutoff)
    ci = {d: j for j, d in enumerate(cal)}
    samples = cal[::step]
    print("[panel] 票=%d  日历=%s~%s（%d 根）  样本日=%d（步长%d）"
          % (len(codes), cal[0], cal[-1], len(cal), len(samples), step))

    rows = []
    sk = collections.Counter()
    for c in codes:
        if S._bad_name(NM.get(c) or ""):
            sk["bad"] += 1
            continue
        bars = cache[c]
        n = len(bars)
        C = [b["last"] for b in bars]
        H = [b["high"] for b in bars]
        L = [b["low"] for b in bars]
        O = [b["open"] for b in bars]
        V = [b["volume"] for b in bars]
        psC = S._prefix(C)
        vu = 1.0 if c.startswith("sh688") else 100.0
        bidx = {b["date"]: i for i, b in enumerate(bars)}
        for T in samples:
            i = bidx.get(T)
            if i is None or i < MINI or i + FMAX >= n:
                continue
            close = C[i]
            if not close or close < PRICE_MIN:
                sk["price"] += 1
                continue
            amt20_yi = sum(V[k] * vu * C[k] for k in range(i - 19, i + 1)) / 20 / 1e8
            if amt20_yi < AMT_MIN / 1e8:
                sk["amt"] += 1
                continue
            f = S.factors_at(C, H, L, O, V, psC, i, c)
            if not f:
                continue
            fC = array("f", C[i + 1:i + 1 + FMAX])
            fH = array("f", H[i + 1:i + 1 + FMAX])
            fL = array("f", L[i + 1:i + 1 + FMAX])
            fO = array("f", O[i + 1:i + 1 + FMAX])   # ★ 前向开盘价：跳空跌破止损线时以开盘价成交
            if len(fC) < FMAX:
                continue
            ret20 = fC[-1] / close - 1
            rows.append({"code": c, "date": T, "f": f, "close": close,
                         "fC": fC, "fH": fH, "fL": fL, "fO": fO,
                         "ret20": ret20,
                         "mfe": (max(fH) / close - 1) * 100,
                         "mae": (min(fL) / close - 1) * 100})
    del cache
    print("[panel] 面板 %d 行（剔 ST/退 %d · 低价 %d · 流动性 %d）"
          % (len(rows), sk["bad"], sk["price"], sk["amt"]))
    return rows, cal


# ---------------- 退出模拟（支持任意持有期，到期价精确取 T+hold 收盘） ----------------
def sim_exit(fC, fH, fL, px, stop, act, trail, hold, cons=False, fO=None):
    """信号日收盘 px 买入：
      · 未盈利前（浮盈 < act，act>0）跌破 px×(1−stop) → 硬止损；
      · 浮盈 ≥ act 后（act≤0 视为全程激活）止损上移至「持仓最高价 ×(1−trail)」；
      · 满 hold 日按 T+hold 收盘平仓（精确，非 T+20 近似）。

    `cons`（保守版）★ 关键：跟踪止盈的止损价依赖「当日最高价」，而**当日最低价是否先于
    最高价出现是未知的**。乐观版（cons=False）在同根 K 线内「先冲高 → 后回落」，
    于是几乎必然能以「最高价×(1−trail)」成交 —— 这对跟踪止盈是**系统性高估**。
    保守版（cons=True）先用「截至前一日的跟踪价」判断当日是否跌破，再用当日高点上移止损线。

    `fO`（前向开盘价）★ 同样关键：若当日**开盘**已跌破止损线（跳空低开），
    限价单不可能以止损价成交，必须以开盘价成交。缺这一步会把大阴线/跳空的亏损
    系统性低估成「刚好止损在线上」，收益被大幅高估。
    """
    hi = px
    cur = px * (1 - stop)
    activated = (act <= 0)
    m = min(hold, len(fL))
    lo = fL[0]
    for j in range(m):
        # ★ 跳空优先：开盘已在止损线之下 → 以开盘价成交（两版都适用）
        if fO is not None and fO[j] > 0 and fO[j] <= cur:
            return (fO[j] / px - 1) * 100, j + 1, (lo / px - 1) * 100
        if cons:
            if fL[j] <= cur:
                return (cur / px - 1) * 100, j + 1, (lo / px - 1) * 100
            if fH[j] > hi:
                hi = fH[j]
            if fL[j] < lo:
                lo = fL[j]
            if not activated and hi >= px * (1 + act):
                activated = True
            if activated:
                ts = hi * (1 - trail)
                if ts > cur:
                    cur = ts
            continue
        if fH[j] > hi:
            hi = fH[j]
        if fL[j] < lo:
            lo = fL[j]
        if not activated and hi >= px * (1 + act):
            activated = True
        if activated:
            ts = hi * (1 - trail)
            if ts > cur:
                cur = ts
        if fL[j] <= cur:
            return (cur / px - 1) * 100, j + 1, (lo / px - 1) * 100
    return (fC[m - 1] / px - 1) * 100, m, (lo / px - 1) * 100


def agg(pnls):
    """赔率结构。"""
    if not pnls:
        return None
    n = len(pnls)
    wins = [x for x in pnls if x > 0]
    loss = [x for x in pnls if x <= 0]
    aw = sum(wins) / len(wins) if wins else 0.0
    al = sum(loss) / len(loss) if loss else 0.0
    return {"n": n, "wr": 100.0 * len(wins) / n, "mean": sum(pnls) / n,
            "avg_win": aw, "avg_loss": al,
            "payoff": (aw / abs(al)) if al else None,
            "p90": statistics.quantiles(pnls, n=10)[8] if n >= 20 else None}


# ---------------- 横截面打分（统一样本日，与主升等权口径一致） ----------------
def score_by_date(rows, use=None, dirs=None):
    use = use or list(PRIOR.keys())
    dirs = S._as_dir(dirs or PRIOR)
    byd = collections.defaultdict(list)
    for r in rows:
        byd[r["date"]].append(r)
    for d in sorted(byd):
        rs = byd[d]
        if len(rs) < 12:
            for r in rs:
                r["qs"] = None
            continue
        rk = {}
        for fac in use:
            vals = sorted([(r["f"].get(fac), r["code"]) for r in rs if r["f"].get(fac) is not None])
            if len(vals) < 6:
                continue
            for pos, (v, c) in enumerate(vals):
                rk.setdefault(c, {})[fac] = pos / (len(vals) - 1)
        for r in rs:
            tot = cnt = 0.0
            for fac in use:
                v = rk.get(r["code"], {}).get(fac)
                if v is None:
                    continue
                tot += (v if dirs[fac] > 0 else 1 - v)
                cnt += 1
            r["qs"] = (tot / cnt * 100) if cnt >= max(2, len(use) // 2) else None


def top_of_day(rows, pct):
    """每日分数前 pct 组成组合。"""
    byd = collections.defaultdict(list)
    for r in rows:
        if r.get("qs") is not None:
            byd[r["date"]].append(r)
    top = []
    for d in sorted(byd):
        rs = sorted(byd[d], key=lambda r: -r["qs"])
        k = max(1, int(round(len(rs) * pct)))
        top += rs[:k]
    return top


def bottom_of_day(rows, pct):
    """每日分数**后** pct（用于检验「把方向反过来会不会更好」）。"""
    byd = collections.defaultdict(list)
    for r in rows:
        if r.get("qs") is not None:
            byd[r["date"]].append(r)
    bot = []
    for d in sorted(byd):
        rs = sorted(byd[d], key=lambda r: -r["qs"])
        k = max(1, int(round(len(rs) * pct)))
        bot += rs[-k:]
    return bot


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--step", type=int, default=5)
    ap.add_argument("--pct", type=float, default=0.05, help="A 档截断比例（域内前 X%）")
    ap.add_argument("--source", choices=["txk", "long"], default="txk",
                    help="txk=主升生产缓存（约252根≈10个月）；long=长历史（约780根≈3年）")
    ap.add_argument("--cost", type=float, default=0.15,
                    help="单次往返交易成本（百分点），用于扣成本后的净均值")
    a = ap.parse_args()

    cp = CACHE_LONG if a.source == "long" else CACHE_TXK
    rows, cal = build_panel_ext(a.step, cp)
    if not rows:
        print("！无样本")
        return

    # 绝对 / 相对标签（相对 = 该日池面等权中位）
    byd = collections.defaultdict(list)
    for r in rows:
        byd[r["date"]].append(r)
    for d, rs in byd.items():
        med = statistics.median([x["ret20"] for x in rs])
        for r in rs:
            r["beat"] = r["ret20"] > med
    dates = sorted(byd)
    cut = dates[len(dates) // 2]
    print("[split] 两半切分 %s  | 前 %s~%s  后 %s~%s"
          % (cut, dates[0], dates[len(dates) // 2 - 1], cut, dates[-1]))

    score_by_date(rows)
    base_abs = statistics.mean([r["ret20"] for r in rows]) * 100
    base_rel = statistics.mean([1 if r["beat"] else 0 for r in rows]) * 100
    base_mfe = statistics.mean([r["mfe"] for r in rows])
    base_mae = statistics.mean([r["mae"] for r in rows])
    print("[base] 域内全样本 n=%d  绝对均值 %+.2f%%  相对胜率 %.1f%%  MFE %.2f%%  MAE %.2f%%"
          % (len(rows), base_abs, base_rel, base_mfe, base_mae))

    top = top_of_day(rows, a.pct)
    bot = bottom_of_day(rows, a.pct)

    def _lvl(sub):
        return {"n": len(sub),
                "abs": statistics.mean([r["ret20"] for r in sub]) * 100,
                "rel": statistics.mean([1 if r["beat"] else 0 for r in sub]) * 100,
                "mfe": statistics.mean([r["mfe"] for r in sub]),
                "mae": statistics.mean([r["mae"] for r in sub])}

    Lt, Lb = _lvl(top), _lvl(bot)
    print("[A档] n=%d（前 %.0f%%）绝对 %+.2f%%（超额 %+.2fpp）相对胜率 %.1f%%（超额 %+.1fpp）"
          " MFE %.2f%% MAE %.2f%%"
          % (Lt["n"], a.pct * 100, Lt["abs"], Lt["abs"] - base_abs, Lt["rel"],
             Lt["rel"] - base_rel, Lt["mfe"], Lt["mae"]))
    print("[尾档] n=%d（后 %.0f%%）绝对 %+.2f%%（超额 %+.2fpp）相对胜率 %.1f%%（超额 %+.1fpp）"
          " MFE %.2f%% MAE %.2f%%  ← 把打分方向反过来"
          % (Lb["n"], a.pct * 100, Lb["abs"], Lb["abs"] - base_abs, Lb["rel"],
             Lb["rel"] - base_rel, Lb["mfe"], Lb["mae"]))
    print("[信号方向] 前5%% 相对胜率 %+.1fpp vs 后5%% %+.1fpp → %s"
          % (Lt["rel"] - base_rel, Lb["rel"] - base_rel,
             "先验方向为正" if (Lt["rel"] - base_rel) > (Lb["rel"] - base_rel) else
             "**先验方向为负（反向更优）**"))
    t_abs, t_rel = Lt["abs"], Lt["rel"]

    res = {"date": a.date, "step": a.step, "pct": a.pct, "source": a.source,
           "cache": os.path.basename(cp),
           "n_rows": len(rows), "n_days": len(dates), "cut": cut,
           "span": [dates[0], dates[-1]], "cur_exit": CUR,
           "base": {"n": len(rows), "abs": round(base_abs, 3), "rel": round(base_rel, 2),
                    "mfe": round(base_mfe, 2), "mae": round(base_mae, 2)},
           "a_top": {"n": len(top), "abs": round(t_abs, 3), "rel": round(t_rel, 2),
                     "edge_abs": round(t_abs - base_abs, 3), "edge_rel": round(t_rel - base_rel, 2),
                     "mfe": round(Lt["mfe"], 2), "mae": round(Lt["mae"], 2)},
           "a_bot": {"n": len(bot), "abs": round(Lb["abs"], 3), "rel": round(Lb["rel"], 2),
                     "edge_abs": round(Lb["abs"] - base_abs, 3), "edge_rel": round(Lb["rel"] - base_rel, 2),
                     "mfe": round(Lb["mfe"], 2), "mae": round(Lb["mae"], 2)}}

    # ---------------- Q2 入场侧：单因子五分位（相对胜率 + 两半）----------------
    print("\n=== Q2 入场侧：单因子五分位（相对胜率 %，训练半 / 测试半）===")
    print("   因子              Q1     Q2     Q3     Q4     Q5   | Q5-Q1 前半 | Q5-Q1 后半 | 同向?")
    fac_tbl = []
    for fac in PRIOR:
        tr = [r for r in rows if r["date"] < cut and r["f"].get(fac) is not None]
        te = [r for r in rows if r["date"] >= cut and r["f"].get(fac) is not None]
        if len(tr) < 300:
            continue
        tv = sorted(x["f"][fac] for x in tr)
        qs = statistics.quantiles(tv, n=5)      # 4 个切点 → 5 桶

        def bk(sample):
            bs = [[] for _ in range(5)]
            for r in sample:
                v = r["f"][fac]
                idx = 4
                for k in range(4):
                    if v <= qs[k]:
                        idx = k
                        break
                bs[idx].append(1 if r["beat"] else 0)
            return [(sum(x) / len(x) * 100 if x else None) for x in bs]

        bt, be = bk(tr), bk(te)
        d1 = (bt[4] - bt[0]) if (bt[4] is not None and bt[0] is not None) else None
        d2 = (be[4] - be[0]) if (be[4] is not None and be[0] is not None) else None
        same = "同向" if (d1 is not None and d2 is not None and d1 * d2 > 0) else "反向"
        print("   %-14s %s | %+5.1f | %+5.1f | %s"
              % (PRIOR_CN.get(fac, fac),
                 " ".join("%5.1f" % (x if x is not None else 0) for x in bt),
                 d1 or 0, d2 or 0, same))
        fac_tbl.append({"fac": fac, "cn": PRIOR_CN.get(fac, fac), "dir": PRIOR[fac],
                        "train": [round(x, 1) if x is not None else None for x in bt],
                        "test": [round(x, 1) if x is not None else None for x in be],
                        "d_train": round(d1, 2) if d1 is not None else None,
                        "d_test": round(d2, 2) if d2 is not None else None,
                        "same": same})
    res["factors"] = fac_tbl

    # ---------------- Q1 收益归因：入场 vs 退出 ----------------
    print("\n=== Q1 收益归因：入场能力（前向收益）vs 退出规则（可兑现）===")
    for label, sub in (("域内全样本", rows), ("A 档（前 %.0f%%）" % (a.pct * 100), top)):
        ab = agg([r["ret20"] * 100 for r in sub])
        ex = [sim_exit(r["fC"], r["fH"], r["fL"], r["close"],
                       CUR["stop"], CUR["act"], CUR["trail"], CUR["hold"], True, r["fO"])[0]
              for r in sub]
        ae = agg(ex)
        print("   %-14s 入场口径：n=%d 均值 %+.2f%% 胜率 %.1f%% | 现行退出：均值 %+.3f%% 胜率 %.1f%% 盈亏比 %s"
              % (label, ab["n"], ab["mean"], ab["wr"], ae["mean"], ae["wr"],
                 ("%.2f" % ae["payoff"]) if ae["payoff"] else "—"))
    res["attrib"] = {}
    for tag, sub in (("base", rows), ("top", top)):
        ab = agg([r["ret20"] * 100 for r in sub])
        ex = [sim_exit(r["fC"], r["fH"], r["fL"], r["close"],
                       CUR["stop"], CUR["act"], CUR["trail"], CUR["hold"], True, r["fO"])[0]
              for r in sub]
        ae = agg(ex)
        res["attrib"][tag] = {"entry": {k: (round(v, 3) if isinstance(v, float) else v)
                                        for k, v in ab.items()},
                              "exit": {k: (round(v, 3) if isinstance(v, float) else v)
                                       for k, v in ae.items()}}

    # ---------------- Q3 退出网格（两半平均 + 两半一致性）----------------
    print("\n=== Q3 退出网格（在 A 档上跑；两半平均排名，另报两半是否同向）===")
    tr_top = [r for r in top if r["date"] < cut]
    te_top = [r for r in top if r["date"] >= cut]
    combos = []

    def _run(ss, st, ac, tl, hd):
        """→ (保守版汇总, MAE, 平均持有, 保守版扣费, 乐观版扣费)"""
        out = [sim_exit(r["fC"], r["fH"], r["fL"], r["close"], st, ac, tl, hd, True, r["fO"]) for r in ss]
        outo = [sim_exit(r["fC"], r["fH"], r["fL"], r["close"], st, ac, tl, hd, False, r["fO"]) for r in ss]
        pnls = [x[0] for x in out]
        holds = [x[1] for x in out]
        maes = [x[2] for x in out]
        return (agg(pnls), (statistics.mean(maes) if maes else None),
                (statistics.mean(holds) if holds else None),
                agg([p - a.cost for p in pnls]),
                agg([x[0] - a.cost for x in outo]))

    for st in GRID_STOP:
        for ac in GRID_ACT:
            for tl in GRID_TRAIL:
                if ac >= 900 and tl != GRID_TRAIL[0]:
                    continue      # ac=999（永不激活）时 trail 无意义，只留一档
                for hd in GRID_HOLD:
                    a1, mg1, hd1, n1, o1 = _run(tr_top, st, ac, tl, hd)
                    a2, mg2, hd2, n2, o2 = _run(te_top, st, ac, tl, hd)
                    if not a1 or not a2:
                        continue
                    combos.append({
                        "stop": st, "act": ac, "trail": tl, "hold": hd,
                        "m1": round(a1["mean"], 3), "w1": round(a1["wr"], 1),
                        "mae1": round(mg1, 2),
                        "m2": round(a2["mean"], 3), "w2": round(a2["wr"], 1),
                        "mae2": round(mg2, 2),
                        "avg": round((a1["mean"] + a2["mean"]) / 2, 3),
                        "avg_net": round((n1["mean"] + n2["mean"]) / 2, 3),
                        "avg_net_opt": round((o1["mean"] + o2["mean"]) / 2, 3),
                        "hold_avg": round((hd1 + hd2) / 2, 1),
                        "mae_avg": round((mg1 + mg2) / 2, 2),
                        "same": (a1["mean"] > 0) == (a2["mean"] > 0),
                        "wr_avg": round((a1["wr"] + a2["wr"]) / 2, 1),
                        "payoff": round(((a1["payoff"] or 0) + (a2["payoff"] or 0)) / 2, 2)
                                   if (a1["payoff"] and a2["payoff"]) else None,
                        "cur": (abs(st - CUR["stop"]) < 1e-9 and abs(ac - CUR["act"]) < 1e-9
                                and abs(tl - CUR["trail"]) < 1e-9 and hd == CUR["hold"])})
    print("   网格 %d 组（净均值已扣往返 %.2fpp；口径=保守版日内处理）" % (len(combos), a.cost))
    combos.sort(key=lambda x: -x["avg"])

    def _tag(c):
        ac = "不激活" if c["act"] >= 900 else ("即跟踪" if c["act"] <= 0 else "%.0f%%" % (c["act"] * 100))
        return "stop%2.0f%% act%-4s trail%.0f%% hold%2d" % (c["stop"] * 100, ac, c["trail"] * 100, c["hold"])

    print("   参数                     前半(胜率)         后半(胜率)         保守均值  净(保守)  净(乐观)  持天  MAE    盈亏比")
    for c in combos[:14]:
        print("   %-24s %+.3f%%(%4.1f%%)  %+.3f%%(%4.1f%%)  %+.3f%%  %+.3f%%  %+.3f%%  %4.1f  %5.1f%%  %s%s"
              % (_tag(c), c["m1"], c["w1"], c["m2"], c["w2"], c["avg"], c["avg_net"], c["avg_net_opt"],
                 c["hold_avg"], c["mae_avg"],
                 ("%.2f" % c["payoff"]) if c["payoff"] else "—",
                 " ★现行" if c["cur"] else ""))
    cur_row = [c for c in combos if c["cur"]]
    if cur_row:
        c = cur_row[0]
        print("   ★ 现行参数 stop12/act6/trail3/hold20：两半平均 %+.3f%%（排名 %d/%d），%s，MAE %.1f%%"
              % (c["avg"], combos.index(c) + 1, len(combos),
                 "两半同向" if c["same"] else "两半反向", c["mae_avg"]))
    pos_same = [c for c in combos if c["same"] and c["avg"] > 0]
    print("   两半同向 且 两半平均 > 0 的组合：%d/%d" % (len(pos_same), len(combos)))

    # ★ 前半选参 → 后半验证（「两半平均排名」本身也可能隐含选择偏差）
    b1 = max(combos, key=lambda x: x["m1"])
    b2 = max(combos, key=lambda x: x["m2"])
    print("   前半最优 %s → 前半 %+.3f%% / 后半 %+.3f%%" % (_tag(b1), b1["m1"], b1["m2"]))
    print("   后半最优 %s → 前半 %+.3f%% / 后半 %+.3f%%" % (_tag(b2), b2["m1"], b2["m2"]))
    rank_of_b1_in_2 = sorted(combos, key=lambda x: -x["m2"]).index(b1) + 1
    print("   前半最优参数在「后半」的名次：%d/%d %s"
          % (rank_of_b1_in_2, len(combos),
             "（跨期稳定）" if rank_of_b1_in_2 <= len(combos) * 0.25 else "（跨期不稳定）"))

    # ★ 用「两半平均最优」参数同时跑 A 档与全样本：检验选股是否还有增量
    best = combos[0]

    def _net_on(ss):
        out = [sim_exit(r["fC"], r["fH"], r["fL"], r["close"],
                        best["stop"], best["act"], best["trail"], best["hold"], True, r["fO"])
               for r in ss]
        return (agg([x[0] - a.cost for x in out]), statistics.mean([x[1] for x in out]))

    n_top, h_top = _net_on(top)
    n_all, h_all = _net_on(rows)
    d_pick = n_top["mean"] - n_all["mean"]
    print("   同一最优参数 %s：A档 净均值 %+.3f%%（持%.1f天） vs 全样本 %+.3f%%（持%.1f天）"
          " → 选股增量 %+.3fpp %s"
          % (_tag(best), n_top["mean"], h_top, n_all["mean"], h_all, d_pick,
             "（选股仍有增量）" if d_pick > 0.1 else "（**选股已无增量**）"))
    res["best_param_pick"] = {
        "param": {k: best[k] for k in ("stop", "act", "trail", "hold")},
        "top": {"n": n_top["n"], "mean_net": round(n_top["mean"], 3), "wr": round(n_top["wr"], 1),
                "hold": round(h_top, 1)},
        "all": {"n": n_all["n"], "mean_net": round(n_all["mean"], 3), "wr": round(n_all["wr"], 1),
                "hold": round(h_all, 1)},
        "delta_pp": round(d_pick, 3)}

    # ★★ 假设敏感性：同一组参数在四种「成交假设」下的结果
    # （本轮最重要的方法论发现：A 股的退出规则回测若不处理跳空/日内路径，会系统性高估）
    assume = []
    for tag, cons, gap in (("保守日内 + 跳空成交", True, True),
                           ("乐观日内 + 跳空成交", False, True),
                           ("保守日内 + 忽略跳空", True, False),
                           ("乐观日内 + 忽略跳空", False, False)):
        for who, ss in (("A档", top), ("全样本", rows)):
            fwd = [sim_exit(r["fC"], r["fH"], r["fL"], r["close"],
                            best["stop"], best["act"], best["trail"], best["hold"],
                            cons, (r["fO"] if gap else None))[0] - a.cost for r in ss]
            ag = agg(fwd)
            assume.append({"tag": tag, "who": who, "mean": round(ag["mean"], 3),
                           "wr": round(ag["wr"], 1)})
    print("\n=== ★ 假设敏感性（最优参数 %s，扣费后）===" % _tag(best))
    for tag in ("保守日内 + 跳空成交", "乐观日内 + 跳空成交",
                "保守日内 + 忽略跳空", "乐观日内 + 忽略跳空"):
        row = [x for x in assume if x["tag"] == tag]
        d = {x["who"]: x for x in row}
        print("   %-18s A档 %+.3f%%(%4.1f%%)   全样本 %+.3f%%(%4.1f%%)"
              % (tag, d["A档"]["mean"], d["A档"]["wr"], d["全样本"]["mean"], d["全样本"]["wr"]))
    res["assumption_sens"] = assume
    res["cost"] = a.cost
    res["exit_grid"] = {"grid": combos, "n_pos_same": len(pos_same),
                        "cur_rank": (combos.index(cur_row[0]) + 1) if cur_row else None,
                        "cur": cur_row[0] if cur_row else None,
                        "n_combos": len(combos),
                        "best_train": b1, "best_test": b2,
                        "best_train_rank_in_test": rank_of_b1_in_2}

    out = os.path.join(QUANT, "_selected_attrib_%s.json" % a.source)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    print("\n[out] %s" % out)


if __name__ == "__main__":
    main()
