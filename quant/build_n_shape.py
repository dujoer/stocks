# -*- coding: utf-8 -*-
"""N字形战法筛选板（观察池 · 非出票）。

筛选条件（用户给定示例）：
  1) 近 20 个交易日（含当日）内，至少 1 根日K 收盘封涨停（统一口径 _mkt_emo.is_limit_up）。
  2) 最新收盘价 > 5 日均线（MA5）。
「可建仓」附加：剔除当日已封涨停（一字/封死涨停盘中买不进）的标的。

增强（2026-10-23）：
  · 强度分(0~100) 五维加权 + 强/中/弱 分层 + 每日精选前 20。
  · 价格高点分析：当前价 vs 前高（涨停日高点）/ 52周高低，给出「价格优势」verdict。
  · 热点贴合：股票名→申万二级→板块强度（sector_strength_data）；并比对热门概念龙头股名。

本板仅按机械条件筛选、打分与归因，未过任何样本外稳健性检验，不构成买卖建议。
数据：_txk_cache.json（全市场日K）+ quotes/{D}.json（名称/现价/52周高低）。
输出：web/n_shape/n_shape_{DS}.html（每日归档）+ web/n_shape/index.html（滚动视图）。
"""
from __future__ import annotations
import os, sys, json, datetime, argparse

QUANT = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(QUANT)
WEB = os.path.join(ROOT, "web")
sys.path.insert(0, QUANT)

import _txk
import _mkt_emo as M
import _idxkline as E

OUTDIR = os.path.join(WEB, "n_shape")
os.makedirs(OUTDIR, exist_ok=True)

WINDOW = 20            # 近 N 个交易日查涨停
MIN_BARS = 30          # 最少历史根数
AMT_MIN = 30_000_000   # 20 日均成交额下限（元），剔除流动性差的
EXCLUDE_BJ = True      # 剔除北交所（30cm，口径不同）
FWD = 10               # 回测前向交易日数（往前回测 10 天）

# 强度分权重（合计 100）
W_REC, W_LIQ, W_MP, W_MO, W_PB = 35, 25, 20, 10, 10
TIER_STRONG, TIER_MID = 70, 52

# 行业热点阈值：行为∈{抢筹,建仓} 且 强度值 ≥ 全行业 60 分位 → 热点
HOT_PCTL = 0.60
HOT_BEHAVIORS = ("抢筹", "建仓")

# 整体价格位置（52周分位）合理区间：太高无空间、太低恐破位
POS_LO, POS_HI = 30, 85

# 市场热度门控：≤信号日的大盘环境（_idxkline.market_env，日更、无未来函数）
HEAT_GATE = {"强势": ("开仓", "#188038"), "震荡": ("开仓", "#188038"),
             "弱势": ("谨慎", "#b8893b"), "破位": ("暂停", "#d93025"), "未知": ("未知", "#9aa0a6")}


def latest_date():
    try:
        return _txk.last_date(_txk.load())
    except Exception:
        return None


def excluded_name(name):
    if not name:
        return True
    for k in ("ST", "*ST", "退", "ETF", "基金", "债", "B股"):
        if k in name:
            return True
    return False


# ----------------------------------------------------------------- 热点 / 板块
def load_hot_maps():
    """返回 (ind_map, concept_hot_leaders)。

    ind_map: 申万二级名 -> {'behavior':str,'strength':float,'hot':bool}
    concept_hot_leaders: set(热门概念的龙头股名) —— 用于「贴合概念热点」宽松判定。
    """
    ind_map, concept_hot_leaders = {}, set()
    p = os.path.join(QUANT, "sector_strength_data.json")
    if not os.path.exists(p):
        return ind_map, concept_hot_leaders
    try:
        ss = json.load(open(p, encoding="utf-8"))
    except Exception:
        return ind_map, concept_hot_leaders
    inds, cons = [], []
    for s in ss:
        if s.get("kind") == "行业":
            nm = s.get("name", "")
            nm = nm[:-2] if nm.endswith("行业") else nm
            inds.append((nm, s.get("behavior", ""), float(s.get("strengthVal") or 0)))
        elif s.get("kind") == "概念":
            cons.append((s.get("name", ""), s.get("behavior", ""),
                         float(s.get("strengthVal") or 0), s.get("leader", "")))
    # 行业阈值
    if inds:
        sv = sorted(v[2] for v in inds)
        k = max(0, min(len(sv) - 1, int(HOT_PCTL * len(sv))))
        thr = sv[k]
        for nm, beh, sval in inds:
            hot = (beh in HOT_BEHAVIORS) and (sval >= thr)
            ind_map[nm] = {"behavior": beh, "strength": sval, "hot": hot}
    # 概念龙头：行为∈热点 且 强度值位于概念前 30%
    if cons:
        csv = sorted(c[2] for c in cons)
        ck = max(0, min(len(csv) - 1, int(0.70 * len(csv))))
        cthr = csv[ck]
        for nm, beh, sval, leader in cons:
            if (beh in HOT_BEHAVIORS) and sval >= cthr and leader:
                # leader 形如 "天娱数科 +9.94%"
                lead_name = leader.split("+")[0].split("-")[0].strip()
                if lead_name:
                    concept_hot_leaders.add(lead_name)
    return ind_map, concept_hot_leaders


def load_name2sw2():
    p = os.path.join(QUANT, "_name2sw2.json")
    if not os.path.exists(p):
        return {}
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return {}


def load_name_map(latest):
    """code -> name（取自最新 quotes；名称稳定，回测也复用）。"""
    nm = {}
    p = os.path.join(QUANT, "quotes", "%s.json" % latest)
    if os.path.exists(p):
        try:
            qj = json.load(open(p, encoding="utf-8")).get("data", {})
            for code, v in qj.items():
                if isinstance(v, dict) and v.get("name"):
                    nm[code] = v["name"]
        except Exception:
            pass
    return nm


def load_52w(latest):
    """code -> (high_52w, low_52w)。"""
    d = {}
    p = os.path.join(QUANT, "quotes", "%s.json" % latest)
    if os.path.exists(p):
        try:
            qj = json.load(open(p, encoding="utf-8")).get("data", {})
            for code, v in qj.items():
                if isinstance(v, dict):
                    d[code] = (v.get("high_52week"), v.get("low_52week"))
        except Exception:
            pass
    return d


def load_market_heat(D):
    """大盘热度（≤信号日，无未来函数）：环境分/档位 + 指数偏离MA20 + 涨跌家数广度 + 涨跌停比。

    数据源：_idxkline.market_env（指数偏离 + 市场画像 composite）与 market_overview/{D}.json
    （原始涨跌家数/涨跌停比）。两者均为日更、落盘数据，离线可读。
    返回 dict，失败降级为 label=未知，不硬编。
    """
    out = {"date": D, "score": None, "label": "未知", "pos_scale": None,
           "idx_dev": None, "red": None, "green": None, "total": None,
           "breadth": None, "uplimit": None, "dnlimit": None}
    try:
        e = E.market_env(D)
        if e:
            out["score"] = e.get("score")
            out["label"] = e.get("label")
            out["pos_scale"] = e.get("pos_scale")
            idx = (e.get("detail") or {}).get("index") or {}
            if idx and idx.get("ma20"):
                out["idx_dev"] = round((idx["close"] - idx["ma20"]) / idx["ma20"] * 100, 2)
    except Exception:
        pass
    p = os.path.join(QUANT, "market_overview", "%s.json" % D)
    try:
        j = json.load(open(p, encoding="utf-8"))
        d = j.get("data")
        if isinstance(d, list):
            d = d[0] if d else {}
        row = (d or {}).get("row") or {}
        red, grn, tot = row.get("CNT_RED"), row.get("CNT_GREEN"), row.get("CNT_TOTAL")
        if tot:
            out["red"], out["green"], out["total"] = red, grn, tot
            if red is not None and grn is not None:
                out["breadth"] = round((red - grn) / tot * 100, 2)
            out["uplimit"] = row.get("RATIO_UPLIMIT")
            out["dnlimit"] = row.get("RATIO_DOWNLIMIT")
    except Exception:
        pass
    return out


# ----------------------------------------------------------------- 信号（as-of 切片，回测/主池通用）
def gen_signals_asof(cache, D, name_map=None):
    """重算 N字形信号（数据截至 D，含 D）。纯 K线，回测与主池共用，保证口径一致。"""
    out = []
    for code, bars in cache.items():
        if not isinstance(bars, list) or len(bars) < MIN_BARS:
            continue
        if EXCLUDE_BJ and str(code).startswith("bj"):
            continue
        # 定位 as-of 根
        aidx = None
        for i, b in enumerate(bars):
            if b["date"] == D:
                aidx = i
                break
            if b["date"] > D:
                break
        if aidx is None:
            continue
        name = (name_map or {}).get(code)
        if excluded_name(name):
            continue

        lo = max(0, aidx - (WINDOW + 5))
        win = bars[lo:aidx + 1]
        # 扩展窗口用于 MA20/MA60（与主池/回测同口径，判断「股票位置」）
        ma_lo = max(0, aidx - 65)
        ma_win = bars[ma_lo:aidx + 1]
        def _sma(n):
            vs = [b.get("last") for b in ma_win[-n:] if b.get("last") is not None]
            return (sum(vs) / len(vs)) if len(vs) >= n else None
        ma20 = _sma(20)
        ma60 = _sma(60)
        recs = list(M.scan_one(code, win))
        if len(recs) < WINDOW:
            continue
        last20 = recs[-WINDOW:]

        today_zt = bool(last20[-1].get("closed"))
        has_zt = any(r.get("closed") for r in last20)
        if not has_zt:
            continue

        closes5 = [r["close"] for r in recs[-5:]]
        if not closes5 or any(c is None for c in closes5):
            continue
        ma5 = sum(closes5) / len(closes5)
        cur = last20[-1]["close"]
        if cur is None or ma5 is None:
            continue
        if not (cur > ma5):
            continue

        amts = [r.get("amount") or 0 for r in last20]
        avg_amt = sum(amts) / len(amts)
        if avg_amt < AMT_MIN:
            continue

        # 可建仓：剔除当日已封涨停（买不进）—— 回测与主池同口径
        if today_zt:
            continue

        # 涨停定位
        last_zt_idx = None
        for i in range(len(last20) - 1, -1, -1):
            if last20[i].get("closed"):
                last_zt_idx = i
                break
        last_zt_date = last20[last_zt_idx]["date"] if last_zt_idx is not None else None
        days_since = (len(last20) - 1 - last_zt_idx) if last_zt_idx is not None else None

        # 涨停后回撤：涨停收盘 → 其后最低价（越浅越强）
        pullback_pct = 0.0
        prev_peak_high = None
        if last_zt_idx is not None:
            zt_close = last20[last_zt_idx]["close"]
            prev_peak_high = last20[last_zt_idx].get("high")
            post = last20[last_zt_idx + 1:]
            lows = [r.get("low") for r in post if r.get("low") is not None]
            if zt_close and lows:
                pullback_pct = round((min(lows) / zt_close - 1) * 100, 2)

        # 局部峰值（涨停后至当前区间最高价）—— 用于「健康回撤」位置判断
        post_zt = last20[last_zt_idx:] if last_zt_idx is not None else last20
        local_peak = None
        for r in post_zt:
            h = r.get("high")
            if h is not None and (local_peak is None or h > local_peak):
                local_peak = h
        dist_local_peak = round((cur / local_peak - 1) * 100, 2) if local_peak else None

        # 当日%：as-of 根 vs 前一根
        chg_pct = 0.0
        if aidx >= 1:
            pc = float(bars[aidx - 1].get("last") or 0)
            if pc:
                chg_pct = round((cur / pc - 1) * 100, 2)

        out.append({
            "code": code, "name": name, "close": cur, "ma5": round(ma5, 2),
            "dist_ma5": round((cur / ma5 - 1) * 100, 2),
            "chg_pct": chg_pct, "last_zt_date": last_zt_date,
            "days_since_zt": days_since, "pullback_pct": pullback_pct,
            "avg_amt_yi": round(avg_amt / 1e8, 2),
            "prev_peak_high": prev_peak_high, "asof_idx": aidx,
            "ma20": round(ma20, 2) if ma20 is not None else None,
            "ma60": round(ma60, 2) if ma60 is not None else None,
            "local_peak": local_peak, "dist_local_peak": dist_local_peak,
        })
    return out


def compute_strength(r):
    d = r["days_since_zt"]
    if d <= 1: rec = W_REC
    elif d == 2: rec = 30
    elif d == 3: rec = 25
    elif d == 4: rec = 18
    elif d == 5: rec = 13
    elif d == 6: rec = 9
    else: rec = 5
    liq = min((r["avg_amt_yi"] or 0) / 15.0, 1.0) * W_LIQ
    dm = r["dist_ma5"] or 0
    if dm <= 3: mp = W_MP
    elif dm <= 6: mp = 16
    elif dm <= 10: mp = 12
    else: mp = 8
    c = r["chg_pct"] or 0
    if c >= 3: mo = W_MO
    elif c >= 0: mo = 7
    elif c >= -3: mo = 4
    else: mo = 2
    pb = r["pullback_pct"] or 0
    if pb >= -3: pbs = W_PB
    elif pb >= -6: pbs = 8
    elif pb >= -10: pbs = 5
    else: pbs = 2
    return round(rec + liq + mp + mo + pbs, 1)


def tier_of(s):
    if s >= TIER_STRONG: return "强"
    if s >= TIER_MID: return "中"
    return "弱"


def is_healthy_pullback(s, strict=False):
    """健康回撤（暂时回调但上升趋势完好）判定 —— 用户方法论核心。

    位置判断：涨停启动后，从「局部峰值」（涨停后区间最高价）回落 5%~30% 为健康区间
    （<5% 尚未真正回调，>30% 可能已破位，均不属于「暂时回撤」）。
    趋势结构：strict=True 要求站上 MA60（中长期趋势完好）；False 仅要求站上 MA20。
    叠加：必须贴合热点（板块热度，申万二级抢筹/建仓 或 概念龙头）。
    注：仅作观察池筛选，非出票、不构成建议。
    """
    d = s.get("dist_local_peak")
    if d is None:
        return False
    if not (-30 <= d <= -5):
        return False
    ref = s.get("ma60") if strict else s.get("ma20")
    if ref is not None and s["close"] <= ref:
        return False
    return bool(s.get("hot"))


def is_pos_ok(s):
    """整体价格位置合理判定（用户 2026-10-23 新增维度）。

    以 52周分位 pos_pctile 衡量：太高（>85%）上行空间有限、易双顶；
    太低（<30%）年线级别偏弱、恐破位。两者均不宜作为「暂时回撤后继续拉升」的标的。
    合理区间 [POS_LO, POS_HI] = [30, 85]。
    """
    p = s.get("pos_pctile")
    if p is None:
        return False
    return POS_LO <= p <= POS_HI


def price_verdict(dist_prev_peak, dist_52w_high):
    """价格优势 verdict：当前价相对前高/52周高的位置。"""
    if dist_52w_high is not None and dist_52w_high >= -3:
        return "近一年新高·高位"
    if dist_prev_peak is not None:
        if dist_prev_peak > 0:
            return "突破前高"
        if dist_prev_peak >= -8:
            return "接近前高·蓄势"
        if dist_prev_peak >= -25:
            return "回撤充分·有空间"
        return "低位·空间大"
    return "—"


def attach_attr(rows, name2sw2, ind_map, concept_leaders, w52):
    for r in rows:
        name = r.get("name")
        # 热点
        sw2 = name2sw2.get(name) if name else None
        r["sw2"] = sw2
        ind = ind_map.get(sw2) if sw2 else None
        industry_hot = bool(ind and ind.get("hot"))
        concept_hot = bool(name and name in concept_leaders)
        r["sector_behavior"] = ind.get("behavior") if ind else ("概念热点" if concept_hot else "—")
        r["sector_strength"] = ind.get("strength") if ind else None
        r["hot"] = industry_hot or concept_hot
        # 价格高点
        dist_prev_peak = None
        if r.get("prev_peak_high") and r["close"]:
            dist_prev_peak = round((r["close"] / r["prev_peak_high"] - 1) * 100, 2)
        r["dist_prev_peak"] = dist_prev_peak
        dist_52w_high = None
        h52, l52 = w52.get(r["code"], (None, None))
        if h52:
            dist_52w_high = round((r["close"] / h52 - 1) * 100, 2)
        r["dist_52w_high"] = dist_52w_high
        # 整体价格位置：52周分位（0=年内最低，100=年内最高）
        pos_pctile = None
        if h52 and l52 and h52 > l52 and r["close"]:
            pos_pctile = round((r["close"] - l52) / (h52 - l52) * 100, 1)
        r["pos_pctile"] = pos_pctile
        if pos_pctile is None:
            r["pos_band"] = "—"
        elif pos_pctile >= 85:
            r["pos_band"] = "高位"
        elif pos_pctile >= 50:
            r["pos_band"] = "中高"
        elif pos_pctile >= 30:
            r["pos_band"] = "中位"
        else:
            r["pos_band"] = "低位"
        r["pos_ok"] = is_pos_ok(r)
        r["price_verdict"] = price_verdict(dist_prev_peak, dist_52w_high)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("date", nargs="?", default=None)
    ap.add_argument("--date", dest="date", default=None)
    a = ap.parse_args()
    _d = latest_date()
    D = a.date or (_d if _d else None)
    if not D:
        print("无法确定数据日"); return
    DS = D.replace("-", "")
    print("=== N字形筛选 · 数据日 %s ===" % D)

    try:
        _txk.set_asof(D)
    except Exception:
        pass
    cache = _txk.load()

    name_map = load_name_map(_d or D)
    name2sw2 = load_name2sw2()
    ind_map, concept_leaders = load_hot_maps()
    w52 = load_52w(_d or D)
    heat = load_market_heat(D)

    rows = gen_signals_asof(cache, D, name_map)
    attach_attr(rows, name2sw2, ind_map, concept_leaders, w52)

    # 当日封涨停剔除计数（用于口径透明）
    excluded_today_zt = 0
    for code, bars in cache.items():
        if not isinstance(bars, list) or len(bars) < MIN_BARS:
            continue
        if EXCLUDE_BJ and str(code).startswith("bj"):
            continue
        aidx = None
        for i, b in enumerate(bars):
            if b["date"] == D:
                aidx = i; break
            if b["date"] > D:
                break
        if aidx is None:
            continue
        name = name_map.get(code)
        if excluded_name(name):
            continue
        win = bars[max(0, aidx - (WINDOW + 5)):aidx + 1]
        recs = list(M.scan_one(code, win))
        if len(recs) < WINDOW:
            continue
        last20 = recs[-WINDOW:]
        if not any(r.get("closed") for r in last20):
            continue
        closes5 = [r["close"] for r in recs[-5:]]
        if any(c is None for c in closes5):
            continue
        ma5 = sum(closes5) / len(closes5)
        cur = last20[-1]["close"]
        if cur is None or ma5 is None or not (cur > ma5):
            continue
        amts = [r.get("amount") or 0 for r in last20]
        if sum(amts) / len(amts) < AMT_MIN:
            continue
        if bool(last20[-1].get("closed")):
            excluded_today_zt += 1

    for r in rows:
        r["strength"] = compute_strength(r)
        r["tier"] = tier_of(r["strength"])
        r["healthy_loose"] = is_healthy_pullback(r, False)
        r["healthy_strict"] = is_healthy_pullback(r, True)
        r["pos_ok"] = is_pos_ok(r)

    rows.sort(key=lambda r: (-(r["strength"] or 0),
                             r["days_since_zt"] if r["days_since_zt"] is not None else 999))
    elite = rows[:20]
    tier_counts = {"强": 0, "中": 0, "弱": 0}
    for r in rows:
        tier_counts[r["tier"]] = tier_counts.get(r["tier"], 0) + 1
    n_hot = sum(1 for r in rows if r["hot"])

    # 候选（用户 2026-10-23 完整口径）：健康回撤∩热点∩整体价格位置合理
    # = 站上MA60 + 距局部高回落5~30% + 热点 + 52周分位在 [30,85]（非高位无空间、非低位破位）
    combo_rows = [r for r in rows if r.get("healthy_strict") and r.get("pos_ok")]
    # 历史回测期望（取自回测汇总单源，避免双份口径）
    combo_hist_str = None
    try:
        _bt = json.load(open(os.path.join(QUANT, "n_shape", "backtest_summary.json"), encoding="utf-8"))
        _c = _bt.get("overall_hb_pos") or _bt.get("overall") or {}
        if _c.get("avg_ret") is not None and _c.get("n"):
            fwr = _c.get("ft_win_rate"); fwr_hi = _c.get("ft_hi_win_rate")
            ar = _c.get("avg_ret"); pr = _c.get("profit_ratio")
            rr = _c.get("resume_rate"); rr15 = _c.get("resume_rate15")
            vlabel = "正期望(已验证)" if ar > 0 else "历史负期望"
            vcolor = "#188038" if ar > 0 else "#d93025"
            combo_hist_str = ("历史往前回测（同口径·健康回撤∩热点∩位置合理）：样本 %d ｜ "
                              "<b>首次触及胜率(先触+6%%/-8%%) %s</b> ｜ 高胜率档(4/8%%) %s ｜ "
                              "平均收益 %s ｜ 盈亏比 %s ｜ 继续拉升率(10/15日) %s/%s"
                              "（<span style='color:%s;font-weight:700'>%s</span>）。"
                              "「首次触及胜率」= 入场后先触达目标或止损的真实交易判据；本表为当日候选，仅供观察，不构成建议。" % (
                _c.get("n"),
                "—" if fwr is None else "%+.2f%%" % (fwr * 100),
                "—" if fwr_hi is None else "%+.2f%%" % (fwr_hi * 100),
                "—" if ar is None else "%+.2f%%" % (ar * 100),
                "—" if pr is None else "%.2f" % pr,
                "—" if rr is None else "%+.1f%%" % (rr * 100),
                "—" if rr15 is None else "%+.1f%%" % (rr15 * 100),
                vcolor, vlabel))
    except Exception:
        pass

    print("  命中 %d 只（剔除当日涨停 %d 只）｜ 强 %d / 中 %d / 弱 %d ｜ 贴合热点 %d ｜ 健康回撤∩热点∩位置候选 %d" % (
        len(rows), excluded_today_zt, tier_counts["强"], tier_counts["中"], tier_counts["弱"], n_hot, len(combo_rows)))

    jout = {"date": D, "count": len(rows), "excluded_today_zt": excluded_today_zt,
            "window": WINDOW, "tier_counts": tier_counts, "n_hot": n_hot,
            "heat": heat,
            "rows": rows, "elite": elite, "combo_rows": combo_rows}
    jdir = os.path.join(QUANT, "n_shape")
    os.makedirs(jdir, exist_ok=True)
    json.dump(jout, open(os.path.join(jdir, "n_shape_%s.json" % DS), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    html = render_html(D, rows, excluded_today_zt, elite, tier_counts, n_hot,
                       "n_shape_%s.html" % DS, combo_rows, combo_hist_str, heat)
    open(os.path.join(OUTDIR, "n_shape_%s.html" % DS), "w", encoding="utf-8").write(html)
    open(os.path.join(OUTDIR, "index.html"), "w", encoding="utf-8").write(html)
    print("  写出 n_shape_%s.html 与 index.html，共 %d 只" % (DS, len(rows)))


# ----------------------------------------------------------------- 渲染
def _tier_color(t):
    return {"强": "#1a73e8", "中": "#5f6368", "弱": "#9aa0a6"}.get(t, "#5f6368")


def _hot_badge(hot):
    return "<span style='color:#1a73e8;font-weight:700'>✓热点</span>" if hot else "<span style='color:#9aa0a6'>—</span>"


def _trend_cell(r):
    a = r.get("ma20"); b = r.get("ma60")
    above20 = (a is not None and r["close"] > a)
    above60 = (b is not None and r["close"] > b)
    if above20 and above60:
        return "<span style='color:#188038;font-weight:600'>▲双线之上</span>"
    if above20:
        return "<span style='color:#5f6368'>△站MA20</span>"
    if above60:
        return "<span style='color:#5f6368'>△站MA60</span>"
    return "<span style='color:#d93025'>▼线下</span>"


def _sector_cell(r):
    sw2 = r.get("sw2") or "—"
    beh = r.get("sector_behavior") or "—"
    color = "#1a73e8" if beh in ("抢筹",) else ("#188038" if beh == "建仓" else ("#d93025" if beh in ("出货",) else "#5f6368"))
    return "%s <span style='color:%s;font-size:12px'>(%s)</span>" % (sw2, color, beh)


def render_html(D, rows, excluded, elite, tiers, n_hot, archive_href, combo_rows=None, combo_hist_str=None, heat=None):
    # 大盘热度横幅
    hb = ""
    if heat:
        lab = heat.get("label") or "未知"
        gate, gcolor = HEAT_GATE.get(lab, ("未知", "#9aa0a6"))
        sc = heat.get("score")
        sc_s = "—" if sc is None else "%.2f" % sc
        dev = heat.get("idx_dev")
        dev_s = "—" if dev is None else "%+.2f%%" % dev
        br = heat.get("breadth")
        br_s = "—" if br is None else "%+.2f%%" % br
        upr = heat.get("uplimit"); dnr = heat.get("dnlimit")
        upr_s = "—" if upr is None else "%.2f" % upr
        dnr_s = "—" if dnr is None else "%.2f" % dnr
        # 候选区门控提示
        if lab in ("强势", "震荡"):
            gate_note = "当前市场热度<b>偏暖</b>，候选区有效（可重点跟踪）"
        elif lab == "弱势":
            gate_note = "当前市场热度<b>偏弱</b>，候选区仅供参考、谨慎对待"
        elif lab == "破位":
            gate_note = "当前市场热度<b>偏空（破位）</b>，候选区暂停开仓建议"
        else:
            gate_note = "市场热度数据缺失，按震荡保守处理"
        hb = ("<div class='heat' style='border-left:4px solid %s;background:%s'>"
              "📊 大盘热度：<b style='color:%s'>%s</b>（环境分 %s）｜ "
              "指数偏离MA20 <b>%s</b> ｜ 涨跌家数广度 <b>%s</b> ｜ 涨停/跌停比 <b>%s/%s</b><br>"
              "<span style='font-size:12.5px'>门控：%s</span></div>"
              ) % (gcolor, "#f3f8f4" if lab in ("强势", "震荡") else ("#fff7f3" if lab == "破位" else "#fdfaf2"),
                   gcolor, lab, sc_s, dev_s, br_s, upr_s, dnr_s, gate_note)
    head = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>N字形战法筛选 · 近20日涨停+站上5日线</title>
</head><body>
<div class="wrap">
<h1>N字形战法筛选 · 可建仓观察池</h1>
<div class="sub">数据基准 %s · 条件：近20交易日有收盘涨停 且 收盘价&gt;MA5（已剔除当日封涨停）</div>
%s
<div class="box">本页为<b>观察池·非出票</b>：仅按机械条件筛选、打分与归因，未过样本外稳健性检验，不构成买卖建议。
N字形=涨停启动 → 回调 → 再上穿均线，属短线动量延续形态。强度分综合<b>距涨停天数 / 流动性 / 站上MA5贴近度 / 当日动量 / 涨停后回撤</b>五维（0~100），仅供排序参考。
核心方法论：<b>根据股票位置（上升趋势中的健康回撤）+ 板块热度 + 整体价格位置，找暂时回调但大概率继续拉升的票</b>。「健康回撤」= 站上MA60（趋势完好）且从局部高点回落 5%%~30%% 且贴合热点；「整体价格位置」= 52周分位落在 [30,85]（非高位无空间、非低位破位）。详见下方候选区与<a href="backtest/index.html">历史回测</a>。
另有 <b>价格优势</b>（当前价 vs 前高/52周高）、<b>趋势位</b>（MA20/MA60）、<b>52周分位</b>三栏归因，以及顶部<b>大盘热度</b>门控。
<a href="backtest/index.html">📈 历史回测（按市场热度分桶 / 继续拉升率 / 胜率 / 盈亏比）→</a></div>
""" % (D, hb)
    if archive_href:
        head += "<div class='sub'><a href='%s'>📅 历史归档页（%s）</a></div>\n" % (archive_href, D)

    # 每日精选 Top 20
    eh = ("<h2 class='eh'>每日精选 · 强度分前 20</h2>"
          "<div class='sub'>按强度分降序；档位 强(≥%d) / 中(≥%d) / 弱。蓝色=贴合热点。▲双线之上=站上MA20与MA60（趋势完好）。52周分位=当前价在年内高低区间的位置（越高空间越小）。</div>"
          "<table data-wb><thead><tr>"
          "<th>#</th><th>代码</th><th>名称</th><th>强度分</th><th>档位</th><th>板块·热点</th><th>趋势位</th>"
          "<th>距前高</th><th>距局部高</th><th>52周位</th><th>52周分位</th><th>距涨停</th><th>距MA5</th><th>涨停后回撤</th><th>20日均额(亿)</th>"
          "</tr></thead><tbody>") % (TIER_STRONG, TIER_MID)
    etr = []
    for i, r in enumerate(elite, 1):
        pp = r.get("pos_pctile")
        pp_s = "—" if pp is None else "%.0f%%" % pp
        ppc = (" style='color:#d93025;font-weight:600'" if pp is not None and pp >= 85
               else (" style='color:#b8893b'" if pp is not None and pp < 30 else ""))
        etr.append(
            "<tr><td>%d</td><td>%s</td><td>%s%s</td><td><b>%.1f</b></td>"
            "<td style='color:%s;font-weight:600'>%s</td><td>%s %s</td><td>%s</td>"
            "<td class='%s'>%s</td><td class='%s'>%s</td><td class='%s'>%s</td><td%s>%s</td><td>%s</td>"
            "<td class='%s'>%+.2f%%</td><td class='%s'>%+.2f%%</td><td>%.2f</td></tr>" % (
                i, r["code"], r["name"] or "—",
                " <span style='color:#1a73e8'>●</span>" if r["hot"] else "",
                r["strength"], _tier_color(r["tier"]), r["tier"],
                _sector_cell(r), _hot_badge(r["hot"]),
                _trend_cell(r),
                "up" if (r["dist_prev_peak"] or 0) >= 0 else "dn",
                ("%+.2f%%" % r["dist_prev_peak"]) if r["dist_prev_peak"] is not None else "—",
                "up" if (r["dist_local_peak"] or 0) >= 0 else "dn",
                ("%+.2f%%" % r["dist_local_peak"]) if r["dist_local_peak"] is not None else "—",
                "up" if (r["dist_52w_high"] or 0) >= 0 else "dn",
                ("%+.2f%%" % r["dist_52w_high"]) if r["dist_52w_high"] is not None else "—",
                ppc, pp_s,
                ("%d日" % r["days_since_zt"]) if r["days_since_zt"] is not None else "—",
                "up" if r["dist_ma5"] >= 0 else "dn", r["dist_ma5"],
                "dn" if r["pullback_pct"] < 0 else "up", r["pullback_pct"],
                r["avg_amt_yi"] or 0))
    etail = "</tbody></table>"

    # 健康回撤∩热点∩整体价格位置候选（站上MA60 + 距局部高回落5~30% + 热点 + 52周分位[30,85]）
    combo_html = ""
    if combo_rows:
        ch = ["<h2 class='eh'>健康回撤∩热点∩位置合理候选（站上MA60 + 距局部高回落5~30%% + 贴合热点 + 52周分位30~85%%）· 共 %d 只</h2>" % len(combo_rows)]
        if combo_hist_str:
            ch.append("<div class='sub'>%s</div>" % combo_hist_str)
        ch.append("<table data-wb><thead><tr>"
                  "<th>#</th><th>代码</th><th>名称</th><th>强度分</th><th>板块·行为</th>"
                  "<th>距局部高</th><th>趋势位</th><th>距前高</th><th>52周位</th><th>52周分位</th><th>价格位置</th><th>距涨停</th><th>20日均额(亿)</th>"
                  "</tr></thead><tbody>")
        for i, r in enumerate(combo_rows, 1):
            pp = r.get("pos_pctile")
            pp_s = "—" if pp is None else "%.0f%%" % pp
            ppc = (" style='color:#d93025;font-weight:600'" if pp is not None and pp >= 85
                   else (" style='color:#b8893b'" if pp is not None and pp < 30 else ""))
            ch.append("<tr><td>%d</td><td>%s</td><td>%s%s</td><td><b>%.1f</b></td><td>%s</td>"
                      "<td class='%s'>%s</td><td>%s</td>"
                      "<td class='%s'>%s</td><td class='%s'>%s</td><td%s>%s</td><td>%s</td><td>%s</td><td>%.2f</td></tr>" % (
                i, r["code"], r["name"] or "—",
                " <span style='color:#1a73e8'>●</span>" if r["hot"] else "",
                r["strength"], _sector_cell(r),
                "up" if (r["dist_local_peak"] or 0) >= 0 else "dn",
                ("%+.2f%%" % r["dist_local_peak"]) if r["dist_local_peak"] is not None else "—",
                _trend_cell(r),
                "up" if (r["dist_prev_peak"] or 0) >= 0 else "dn",
                ("%+.2f%%" % r["dist_prev_peak"]) if r["dist_prev_peak"] is not None else "—",
                "up" if (r["dist_52w_high"] or 0) >= 0 else "dn",
                ("%+.2f%%" % r["dist_52w_high"]) if r["dist_52w_high"] is not None else "—",
                ppc, pp_s,
                r.get("price_verdict") or "—",
                ("%d日" % r["days_since_zt"]) if r["days_since_zt"] is not None else "—",
                r["avg_amt_yi"] or 0))
        ch.append("</tbody></table>")
        combo_html = "".join(ch)

    # 全量列表
    th = ("<h2 class='eh'>全量命中（按强度分降序，共 %d 只）</h2>"
          "<table data-wb><thead><tr>"
          "<th>#</th><th>代码</th><th>名称</th><th>现价</th><th>MA5</th><th>距MA5</th>"
          "<th>当日%%</th><th>强度分</th><th>档位</th><th>板块·行为</th><th>热点</th><th>趋势位</th>"
          "<th>距前高</th><th>距局部高</th><th>52周位</th><th>52周分位</th><th>价格位置</th><th>最近涨停</th><th>距涨停</th>"
          "<th>涨停后回撤</th><th>20日均额(亿)</th>"
          "</tr></thead><tbody>") % len(rows)
    trs = []
    for i, r in enumerate(rows, 1):
        chg = r["chg_pct"] or 0
        cls = "up" if chg >= 0 else "dn"
        sign = "+" if chg >= 0 else ""
        d_zt = r["days_since_zt"]
        d_zt_s = ("%d日" % d_zt) if d_zt is not None else "—"
        pv = r.get("price_verdict") or "—"
        pp = r.get("pos_pctile")
        pp_s = "—" if pp is None else "%.0f%%" % pp
        ppc = (" style='color:#d93025;font-weight:600'" if pp is not None and pp >= 85
               else (" style='color:#b8893b'" if pp is not None and pp < 30 else ""))
        trs.append(
            "<tr><td>%d</td><td>%s</td><td>%s%s</td><td>%.2f</td><td>%.2f</td>"
            "<td class='%s'>%+.2f%%</td><td class='%s'>%s%.2f%%</td>"
            "<td><b>%.1f</b></td><td style='color:%s;font-weight:600'>%s</td>"
            "<td>%s</td><td>%s</td><td>%s</td>"
            "<td class='%s'>%s</td><td class='%s'>%s</td><td class='%s'>%s</td><td%s>%s</td><td>%s</td>"
            "<td>%s</td><td>%s</td><td class='%s'>%+.2f%%</td><td>%.2f</td></tr>" % (
                i, r["code"], r["name"] or "—",
                " <span style='color:#1a73e8'>●</span>" if r["hot"] else "",
                r["close"], r["ma5"],
                "up" if r["dist_ma5"] >= 0 else "dn", r["dist_ma5"],
                cls, sign, chg,
                r["strength"], _tier_color(r["tier"]), r["tier"],
                _sector_cell(r), _hot_badge(r["hot"]), _trend_cell(r),
                "up" if (r["dist_prev_peak"] or 0) >= 0 else "dn",
                ("%+.2f%%" % r["dist_prev_peak"]) if r["dist_prev_peak"] is not None else "—",
                "up" if (r["dist_local_peak"] or 0) >= 0 else "dn",
                ("%+.2f%%" % r["dist_local_peak"]) if r["dist_local_peak"] is not None else "—",
                "up" if (r["dist_52w_high"] or 0) >= 0 else "dn",
                ("%+.2f%%" % r["dist_52w_high"]) if r["dist_52w_high"] is not None else "—",
                ppc, pp_s,
                pv,
                r["last_zt_date"] or "—", d_zt_s,
                "dn" if r["pullback_pct"] < 0 else "up", r["pullback_pct"],
                r["avg_amt_yi"] or 0))
    tail = ("</tbody></table>"
            "<div class='sub'>共 %d 只命中 · 已剔除当日封涨停 %d 只 · 强 %d / 中 %d / 弱 %d · 贴合热点 %d 只 · 数据基准 %s</div>"
            "</div></body></html>" % (len(rows), excluded,
                                      tiers.get("强", 0), tiers.get("中", 0), tiers.get("弱", 0),
                                      n_hot, D))
    return head + eh + "".join(etr) + etail + combo_html + th + "".join(trs) + tail


if __name__ == "__main__":
    main()
