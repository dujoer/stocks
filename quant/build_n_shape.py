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

    rows.sort(key=lambda r: (-(r["strength"] or 0),
                             r["days_since_zt"] if r["days_since_zt"] is not None else 999))
    elite = rows[:20]
    tier_counts = {"强": 0, "中": 0, "弱": 0}
    for r in rows:
        tier_counts[r["tier"]] = tier_counts.get(r["tier"], 0) + 1
    n_hot = sum(1 for r in rows if r["hot"])

    # 三重组合过滤候选（强档 ∩ 热点 ∩ 回撤充分），与主池同口径的下一步短名单
    combo_rows = [r for r in rows
                  if r["tier"] == "强" and r["hot"]
                  and (r.get("dist_prev_peak") is not None and r["dist_prev_peak"] <= -25)]
    # 历史 10 日期望（取自回测汇总单源，避免双份口径）
    combo_hist_str = None
    try:
        _bt = json.load(open(os.path.join(QUANT, "n_shape", "backtest_summary.json"), encoding="utf-8"))
        _c = _bt.get("overall") or {}
        if _c.get("avg_ret") is not None and _c.get("n"):
            wr = _c.get("win_rate"); ar = _c.get("avg_ret"); pr = _c.get("profit_ratio")
            vlabel = "正期望" if ar > 0 else "负期望"
            vcolor = "#188038" if ar > 0 else "#d93025"
            combo_hist_str = ("历史往前10日回测（同口径）：样本 %d ｜ 胜率 %s ｜ 平均收益 %s ｜ 盈亏比 %s"
                              "（<span style='color:%s;font-weight:700'>%s</span>）。本表为当日满足条件的候选，仅供观察，不构成建议。" % (
                _c.get("n"), "—" if wr is None else "%+.2f%%" % (wr * 100),
                "—" if ar is None else "%+.2f%%" % (ar * 100),
                "—" if pr is None else "%.2f" % pr, vcolor, vlabel))
    except Exception:
        pass

    print("  命中 %d 只（剔除当日涨停 %d 只）｜ 强 %d / 中 %d / 弱 %d ｜ 贴合热点 %d ｜ 三重组合候选 %d" % (
        len(rows), excluded_today_zt, tier_counts["强"], tier_counts["中"], tier_counts["弱"], n_hot, len(combo_rows)))

    jout = {"date": D, "count": len(rows), "excluded_today_zt": excluded_today_zt,
            "window": WINDOW, "tier_counts": tier_counts, "n_hot": n_hot,
            "rows": rows, "elite": elite, "combo_rows": combo_rows}
    jdir = os.path.join(QUANT, "n_shape")
    os.makedirs(jdir, exist_ok=True)
    json.dump(jout, open(os.path.join(jdir, "n_shape_%s.json" % DS), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    html = render_html(D, rows, excluded_today_zt, elite, tier_counts, n_hot,
                       "n_shape_%s.html" % DS, combo_rows, combo_hist_str)
    open(os.path.join(OUTDIR, "n_shape_%s.html" % DS), "w", encoding="utf-8").write(html)
    open(os.path.join(OUTDIR, "index.html"), "w", encoding="utf-8").write(html)
    print("  写出 n_shape_%s.html 与 index.html，共 %d 只" % (DS, len(rows)))


# ----------------------------------------------------------------- 渲染
def _tier_color(t):
    return {"强": "#1a73e8", "中": "#5f6368", "弱": "#9aa0a6"}.get(t, "#5f6368")


def _hot_badge(hot):
    return "<span style='color:#1a73e8;font-weight:700'>✓热点</span>" if hot else "<span style='color:#9aa0a6'>—</span>"


def _sector_cell(r):
    sw2 = r.get("sw2") or "—"
    beh = r.get("sector_behavior") or "—"
    color = "#1a73e8" if beh in ("抢筹",) else ("#188038" if beh == "建仓" else ("#d93025" if beh in ("出货",) else "#5f6368"))
    return "%s <span style='color:%s;font-size:12px'>(%s)</span>" % (sw2, color, beh)


def render_html(D, rows, excluded, elite, tiers, n_hot, archive_href, combo_rows=None, combo_hist_str=None):
    head = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>N字形战法筛选 · 近20日涨停+站上5日线</title>
</head><body>
<div class="wrap">
<h1>N字形战法筛选 · 可建仓观察池</h1>
<div class="sub">数据基准 %s · 条件：近20交易日有收盘涨停 且 收盘价&gt;MA5（已剔除当日封涨停）</div>
<div class="box">本页为<b>观察池·非出票</b>：仅按机械条件筛选、打分与归因，未过样本外稳健性检验，不构成买卖建议。
N字形=涨停启动 → 回调 → 再上穿均线，属短线动量延续形态。强度分综合<b>距涨停天数 / 流动性 / 站上MA5贴近度 / 当日动量 / 涨停后回撤</b>五维（0~100），仅供排序参考。
新增：<b>价格优势</b>（当前价 vs 前高/52周高，判断是否高位或仍有空间）与 <b>热点贴合</b>（申万二级板块强度 + 热门概念龙头）两栏归因。
<a href="backtest/index.html">📈 历史回测（往前10日胜率/盈亏比）→</a></div>
""" % D
    if archive_href:
        head += "<div class='sub'><a href='%s'>📅 历史归档页（%s）</a></div>\n" % (archive_href, D)

    # 每日精选 Top 20
    eh = ("<h2 class='eh'>每日精选 · 强度分前 20</h2>"
          "<div class='sub'>按强度分降序；档位 强(≥%d) / 中(≥%d) / 弱。蓝色=贴合热点。</div>"
          "<table data-wb><thead><tr>"
          "<th>#</th><th>代码</th><th>名称</th><th>强度分</th><th>档位</th><th>板块·热点</th>"
          "<th>距前高</th><th>52周位</th><th>距涨停</th><th>距MA5</th><th>涨停后回撤</th><th>20日均额(亿)</th>"
          "</tr></thead><tbody>") % (TIER_STRONG, TIER_MID)
    etr = []
    for i, r in enumerate(elite, 1):
        etr.append(
            "<tr><td>%d</td><td>%s</td><td>%s%s</td><td><b>%.1f</b></td>"
            "<td style='color:%s;font-weight:600'>%s</td><td>%s %s</td>"
            "<td class='%s'>%s</td><td class='%s'>%s</td><td>%s</td>"
            "<td class='%s'>%+.2f%%</td><td class='%s'>%+.2f%%</td><td>%.2f</td></tr>" % (
                i, r["code"], r["name"] or "—",
                " <span style='color:#1a73e8'>●</span>" if r["hot"] else "",
                r["strength"], _tier_color(r["tier"]), r["tier"],
                _sector_cell(r), _hot_badge(r["hot"]),
                "up" if (r["dist_prev_peak"] or 0) >= 0 else "dn",
                ("%+.2f%%" % r["dist_prev_peak"]) if r["dist_prev_peak"] is not None else "—",
                "up" if (r["dist_52w_high"] or 0) >= 0 else "dn",
                ("%+.2f%%" % r["dist_52w_high"]) if r["dist_52w_high"] is not None else "—",
                ("%d日" % r["days_since_zt"]) if r["days_since_zt"] is not None else "—",
                "up" if r["dist_ma5"] >= 0 else "dn", r["dist_ma5"],
                "dn" if r["pullback_pct"] < 0 else "up", r["pullback_pct"],
                r["avg_amt_yi"] or 0))
    etail = "</tbody></table>"

    # 三重组合过滤候选（强档 ∩ 热点 ∩ 回撤充分）
    combo_html = ""
    if combo_rows:
        ch = ["<h2 class='eh'>三重组合过滤候选（强档∩热点∩回撤≤−25%）· 共 %d 只</h2>" % len(combo_rows)]
        if combo_hist_str:
            ch.append("<div class='sub'>%s</div>" % combo_hist_str)
        ch.append("<table data-wb><thead><tr>"
                  "<th>#</th><th>代码</th><th>名称</th><th>强度分</th><th>板块·行为</th>"
                  "<th>距前高</th><th>52周位</th><th>价格位置</th><th>距涨停</th><th>20日均额(亿)</th>"
                  "</tr></thead><tbody>")
        for i, r in enumerate(combo_rows, 1):
            ch.append("<tr><td>%d</td><td>%s</td><td>%s%s</td><td><b>%.1f</b></td><td>%s</td>"
                      "<td class='%s'>%s</td><td class='%s'>%s</td><td>%s</td><td>%s</td><td>%.2f</td></tr>" % (
                i, r["code"], r["name"] or "—",
                " <span style='color:#1a73e8'>●</span>" if r["hot"] else "",
                r["strength"], _sector_cell(r),
                "up" if (r["dist_prev_peak"] or 0) >= 0 else "dn",
                ("%+.2f%%" % r["dist_prev_peak"]) if r["dist_prev_peak"] is not None else "—",
                "up" if (r["dist_52w_high"] or 0) >= 0 else "dn",
                ("%+.2f%%" % r["dist_52w_high"]) if r["dist_52w_high"] is not None else "—",
                r.get("price_verdict") or "—",
                ("%d日" % r["days_since_zt"]) if r["days_since_zt"] is not None else "—",
                r["avg_amt_yi"] or 0))
        ch.append("</tbody></table>")
        combo_html = "".join(ch)

    # 全量列表
    th = ("<h2 class='eh'>全量命中（按强度分降序，共 %d 只）</h2>"
          "<table data-wb><thead><tr>"
          "<th>#</th><th>代码</th><th>名称</th><th>现价</th><th>MA5</th><th>距MA5</th>"
          "<th>当日%%</th><th>强度分</th><th>档位</th><th>板块·行为</th><th>热点</th>"
          "<th>距前高</th><th>52周位</th><th>价格位置</th><th>最近涨停</th><th>距涨停</th>"
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
        trs.append(
            "<tr><td>%d</td><td>%s</td><td>%s%s</td><td>%.2f</td><td>%.2f</td>"
            "<td class='%s'>%+.2f%%</td><td class='%s'>%s%.2f%%</td>"
            "<td><b>%.1f</b></td><td style='color:%s;font-weight:600'>%s</td>"
            "<td>%s</td><td>%s</td>"
            "<td class='%s'>%s</td><td class='%s'>%s</td><td>%s</td>"
            "<td>%s</td><td>%s</td><td class='%s'>%+.2f%%</td><td>%.2f</td></tr>" % (
                i, r["code"], r["name"] or "—",
                " <span style='color:#1a73e8'>●</span>" if r["hot"] else "",
                r["close"], r["ma5"],
                "up" if r["dist_ma5"] >= 0 else "dn", r["dist_ma5"],
                cls, sign, chg,
                r["strength"], _tier_color(r["tier"]), r["tier"],
                _sector_cell(r), _hot_badge(r["hot"]),
                "up" if (r["dist_prev_peak"] or 0) >= 0 else "dn",
                ("%+.2f%%" % r["dist_prev_peak"]) if r["dist_prev_peak"] is not None else "—",
                "up" if (r["dist_52w_high"] or 0) >= 0 else "dn",
                ("%+.2f%%" % r["dist_52w_high"]) if r["dist_52w_high"] is not None else "—",
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
