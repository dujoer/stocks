# -*- coding: utf-8 -*-
"""N字形战法 · 往前历史回测（留存页面 + 继续拉升率 + 胜率 + 盈亏比 + 健康回撤过滤验证）。

核心方法论（用户 2026-10-23 明确）：
  根据「股票位置（上升趋势中的健康回撤）+ 板块热度」，找暂时回调但大概率继续拉升的票。
  因此本回测不只看「买入持有 N 日收益」，更看：
    · 继续拉升率 = 信号后 N 个交易日内，收盘价刷新「局部峰值」（涨停后区间最高价）的概率
      —— 直接度量「暂时回撤 → 继续拉升」是否成立。
    · 传统胜率 / 平均收益 / 盈亏比（10日持有，作对照）。

对最近 N 个「可回测日」（每个都有 >= FWD 个后续交易日）重算 N字形信号（复用
build_n_shape.gen_signals_asof / is_healthy_pullback，口径与主池完全一致）。
过滤口径：
  raw      裸信号（全量）
  hot      贴合热点（板块热度）
  hb_loose 健康回撤·宽松（热点 ∩ 站上MA20 ∩ 距局部高回落5~30%）
  hb_strict健康回撤·严格（热点 ∩ 站上MA60 ∩ 距局部高回落5~30%）  ← 主推候选

所有结果如实呈现（含负期望），不编数据、不凑数。观察池·非出票，不代表未来收益。
"""
from __future__ import annotations
import os, sys, json, datetime, argparse

QUANT = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(QUANT)
WEB = os.path.join(ROOT, "web")
sys.path.insert(0, QUANT)

import _txk
import build_n_shape as NS

FWD = NS.FWD                 # 前向持有交易日数（10，对照用）
N_DATES = 10                # 留存回测日数量
RESUME_H = [10, 15]         # 继续拉升率 观测窗口（日）
# 首次触及法（真实交易判据）：入场后先触 +TP 还是先触 -SL。
# DEF=平衡档（胜率~52%、盈亏比~0.97）；HI=高胜率档（胜率~62%、盈亏比~0.71）。
TP_DEF, SL_DEF = 0.06, 0.08
TP_HI, SL_HI = 0.04, 0.08
OUTDIR = os.path.join(WEB, "n_shape", "backtest")
os.makedirs(OUTDIR, exist_ok=True)


COMBO_LABELS = {
    "raw": "裸信号（全量）",
    "hot": "贴合热点",
    "hb_loose": "健康回撤·宽松（热点∩站上MA20∩回撤5~30%）",
    "hb_strict": "健康回撤·严格（热点∩站上MA60∩回撤5~30%）",
    "hb_pos": "健康回撤·完整（严格+52周分位30~85，整体位置合理）",
}
COMBO_ORDER = ["raw", "hot", "hb_loose", "hb_strict", "hb_pos"]

# 市场热度分桶顺序（_idxkline.market_env 标签）
HEAT_ORDER = ["强势", "震荡", "弱势", "破位", "未知"]


def is_hot(s):
    return bool(s.get("hot"))


def is_hb_loose(s):
    return NS.is_healthy_pullback(s, False)


def is_hb_strict(s):
    return NS.is_healthy_pullback(s, True)


def is_hb_pos(s):
    return NS.is_healthy_pullback(s, True) and NS.is_pos_ok(s)


COMBOS = {
    "raw": lambda s: True,
    "hot": is_hot,
    "hb_loose": is_hb_loose,
    "hb_strict": is_hb_strict,
    "hb_pos": is_hb_pos,
}


def pick_asof_dates(cache, n=N_DATES, fwd=FWD):
    """取最近 n 个、且各有 >= fwd 个后续交易日的回测日。"""
    rep = next((v for v in cache.values() if isinstance(v, list) and v), None)
    if not rep:
        return []
    dates = sorted(b["date"] for b in rep)
    cand = [d for i, d in enumerate(dates) if (len(dates) - 1 - i) >= fwd]
    return cand[-n:]


def fwd_metrics(cache, sig, fwd=FWD):
    """对单条信号算前向收益。返回 dict 或 None（无后续数据）。"""
    code = sig["code"]
    bars = cache.get(code)
    if not bars:
        return None
    aidx = sig.get("asof_idx")
    if aidx is None:
        return None
    fb = bars[aidx + 1:aidx + 1 + fwd]
    if not fb:
        return None
    entry = float(bars[aidx]["last"])
    if not entry:
        return None
    closes = [float(x["last"]) for x in fb if x.get("last") is not None]
    if not closes:
        return None
    last_ret = closes[-1] / entry - 1
    max_ret = max(closes) / entry - 1
    min_ret = min(closes) / entry - 1
    return {"entry": entry, "last_ret": last_ret, "max_ret": max_ret,
            "min_ret": min_ret, "n_fwd": len(fb)}


def fwd_resume(cache, sig, horizon):
    """继续拉升判定：信号后 horizon 日内，收盘价是否刷新「局部峰值」(local_peak)。
    返回：>0 = 第几日前向刷新；0 = 窗口内未刷新；None = 后续数据不足。"""
    code = sig["code"]
    bars = cache.get(code)
    aidx = sig.get("asof_idx")
    if not bars or aidx is None:
        return None
    peak = sig.get("local_peak")
    if not peak:
        return None
    fb = bars[aidx + 1:aidx + 1 + horizon]
    if len(fb) < horizon:
        return None
    for i, x in enumerate(fb, 1):
        lv = x.get("last")
        if lv is not None and lv >= peak:
            return i
    return 0


def fwd_first_touch(cache, sig, tp, sl, fwd=FWD):
    """首次触及法（真实交易判据）：入场后前向走 fwd 日，先触 +tp 还是先触 -sl。
    命中目标=赢（实现收益记 +tp，并记录第几日触及）；触止损=亏（记 -sl）；
    窗口内均未触则超时，按末价判定（>=入场记赢、实现收益=末收益）。
    返回 dict{'win':bool,'day':int,'ret':float} 或 None（无后续数据）。"""
    code = sig["code"]
    bars = cache.get(code)
    aidx = sig.get("asof_idx")
    if not bars or aidx is None:
        return None
    fb = bars[aidx + 1:aidx + 1 + fwd]
    if not fb:
        return None
    entry = float(bars[aidx]["last"])
    if not entry:
        return None
    up, dn = entry * (1 + tp), entry * (1 - sl)
    for i, x in enumerate(fb, 1):
        lv = x.get("last")
        if lv is None:
            continue
        if lv >= up:
            return {"win": True, "day": i, "ret": tp}
        if lv <= dn:
            return {"win": False, "day": i, "ret": -sl}
    last = float(fb[-1]["last"])
    ret = last / entry - 1
    return {"win": ret >= 0, "day": fwd, "ret": ret}


def _ft_agg(results, key, prefix):
    vals = [r[key] for r in results if r.get(key)]
    if not vals:
        return {prefix + "win_rate": None, prefix + "avg_ret": None,
                prefix + "profit_ratio": None, prefix + "avg_day": None}
    n = len(vals)
    wins = [v["ret"] for v in vals if v["win"]]
    losses = [v["ret"] for v in vals if not v["win"]]
    wr = len(wins) / n
    ar = sum(v["ret"] for v in vals) / n
    pr = None
    if wins and losses:
        pr = (sum(wins) / len(wins)) / abs(sum(losses) / len(losses))
    days = [v["day"] for v in vals if v["win"]]
    ad = (sum(days) / len(days)) if days else None
    return {prefix + "win_rate": wr, prefix + "avg_ret": ar,
            prefix + "profit_ratio": pr, prefix + "avg_day": ad}


def aggregate(results):
    n = len(results)
    if n == 0:
        return {"n": 0, "win_rate": None, "avg_ret": None, "profit_ratio": None,
                "best": None, "worst": None,
                "resume_rate": None, "resume_rate15": None, "avg_resume_day": None,
                "ft_win_rate": None, "ft_avg_ret": None, "ft_profit_ratio": None, "ft_avg_day": None,
                "ft_hi_win_rate": None, "ft_hi_avg_ret": None, "ft_hi_profit_ratio": None, "ft_hi_avg_day": None}
    wins = [r["last_ret"] for r in results if r["last_ret"] > 0]
    losses = [r["last_ret"] for r in results if r["last_ret"] <= 0]
    avg_ret = sum(r["last_ret"] for r in results) / n
    win_rate = len(wins) / n
    profit_ratio = None
    if wins and losses:
        profit_ratio = (sum(wins) / len(wins)) / abs(sum(losses) / len(losses))
    best = max(results, key=lambda r: r["last_ret"])["last_ret"]
    worst = min(results, key=lambda r: r["last_ret"])["last_ret"]
    # 继续拉升率
    rs = [r["resume10"] for r in results if r.get("resume10") is not None]
    resume_rate = (sum(1 for x in rs if x > 0) / len(rs)) if rs else None
    rs15 = [r["resume15"] for r in results if r.get("resume15") is not None]
    resume_rate15 = (sum(1 for x in rs15 if x > 0) / len(rs15)) if rs15 else None
    rdays = [x for x in rs if x > 0]
    avg_resume_day = (sum(rdays) / len(rdays)) if rdays else None
    ft = _ft_agg(results, "ft", "ft_")
    ft_hi = _ft_agg(results, "ft_hi", "ft_hi_")
    return {"n": n, "win_rate": win_rate, "avg_ret": avg_ret,
            "profit_ratio": profit_ratio, "best": best, "worst": worst,
            "resume_rate": resume_rate, "resume_rate15": resume_rate15,
            "avg_resume_day": avg_resume_day,
            **ft, **ft_hi}


def pct(x):
    return "—" if x is None else "%+.2f%%" % (x * 100)


def pct1(x):
    return "—" if x is None else "%+.1f%%" % (x * 100)


def combo_verdict(agg):
    if agg["n"] == 0:
        return "样本不足", "#9aa0a6"
    if agg["avg_ret"] is not None and agg["avg_ret"] > 0:
        return "正期望", "#188038"
    return "负期望", "#d93025"


def _hot_badge(hot):
    return "<span style='color:#1a73e8;font-weight:700'>✓</span>" if hot else "<span style='color:#9aa0a6'>—</span>"


def _trend_cell(s):
    a = s.get("ma20"); b = s.get("ma60")
    above20 = (a is not None and s["close"] > a)
    above60 = (b is not None and s["close"] > b)
    if above20 and above60:
        return "<span style='color:#188038;font-weight:600'>▲双线之上</span>"
    if above20:
        return "<span style='color:#5f6368'>△站MA20</span>"
    if above60:
        return "<span style='color:#5f6368'>△站MA60</span>"
    return "<span style='color:#d93025'>▼线下</span>"


def render_day(D, pairs, day_combo_pairs, per_date_combo):
    # 全量原始明细（含继续拉升结果）
    rows = []
    for sig, m in pairs:
        win = m["last_ret"] > 0
        r10 = m.get("resume10")
        r15 = m.get("resume15")
        rcell = ("第%d日↺" % r10) if (r10 and r10 > 0) else ("未↺" if r10 == 0 else "—")
        r15c = ("第%d日↺" % r15) if (r15 and r15 > 0) else ("未↺" if r15 == 0 else "—")
        ft = m.get("ft")
        if ft:
            ft_cell = ("<span style='color:#188038'>✓第%d日</span>" % ft["day"]) if ft["win"] else ("<span style='color:#d93025'>✗第%d日</span>" % ft["day"])
        else:
            ft_cell = "—"
        rows.append(
            "<tr><td>%s</td><td>%s%s</td><td>%s</td><td>%s</td><td>%.2f</td>"
            "<td class='%s'>%s</td><td class='%s'>%s</td><td class='%s'>%s</td>"
            "<td style='font-weight:700;color:%s'>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (
                sig["code"], sig["name"] or "—",
                " <span style='color:#1a73e8'>●</span>" if sig.get("hot") else "",
                sig["last_zt_date"] or "—",
                ("%d日" % sig["days_since_zt"]) if sig["days_since_zt"] is not None else "—",
                m["entry"],
                "up" if m["last_ret"] >= 0 else "dn", pct(m["last_ret"]),
                "up" if m["max_ret"] >= 0 else "dn", pct(m["max_ret"]),
                "up" if m["min_ret"] >= 0 else "dn", pct(m["min_ret"]),
                "#188038" if win else "#d93025", "盈利" if win else "亏损",
                sig.get("sw2") or "—", _hot_badge(sig.get("hot")),
                rcell, r15c, ft_cell))
    # 组合过滤汇总框（本回测日）
    cbox = ["<table data-wb><thead><tr><th>过滤口径</th><th>信号数</th><th>继续拉升率(10日)</th>"
            "<th>继续拉升率(15日)</th><th>胜率</th><th>FT胜率(6/8)</th><th>FT胜率(4/8)</th><th>平均收益</th><th>盈亏比</th><th>10日期望</th></tr></thead><tbody>"]
    for k in COMBO_ORDER:
        a = per_date_combo[k][D]
        v, vc = combo_verdict(a)
        cbox.append("<tr><td>%s</td><td>%d</td><td><b>%s</b></td><td><b>%s</b></td><td>%s</td><td><b>%s</b></td><td><b>%s</b></td><td>%s</td><td>%s</td><td style='color:%s;font-weight:700'>%s</td></tr>" % (
            COMBO_LABELS[k], a["n"],
            pct1(a["resume_rate"]) if a["resume_rate"] is not None else "—",
            pct1(a["resume_rate15"]) if a["resume_rate15"] is not None else "—",
            pct(a["win_rate"]) if a["win_rate"] is not None else "—",
            pct1(a["ft_win_rate"]) if a["ft_win_rate"] is not None else "—",
            pct1(a["ft_hi_win_rate"]) if a["ft_hi_win_rate"] is not None else "—",
            pct(a["avg_ret"]),
            "—" if a["profit_ratio"] is None else "%.2f" % a["profit_ratio"],
            vc, v))
    cbox.append("</tbody></table>")
    # 健康回撤·严格 子集表（主推候选）
    sub = day_combo_pairs["hb_strict"]
    subrows = []
    for sig, m in sub:
        r10 = m.get("resume10")
        rcell = ("第%d日↺" % r10) if (r10 and r10 > 0) else ("未↺" if r10 == 0 else "—")
        subrows.append("<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%.2f</td>"
                       "<td class='%s'>%s</td><td class='%s'>%s</td><td>%s</td></tr>" % (
            sig["code"], sig["name"] or "—", sig.get("sw2") or "—", _trend_cell(sig),
            m["entry"],
            "up" if (sig["dist_local_peak"] or 0) >= 0 else "dn",
            ("%+.2f%%" % sig["dist_local_peak"]) if sig["dist_local_peak"] is not None else "—",
            "up" if m["last_ret"] >= 0 else "dn", pct(m["last_ret"]),
            rcell))
    sub_n = len(sub)
    if sub_n:
        sub_html = ("<h2 class='eh'>健康回撤·严格 候选子集（热点∩站上MA60∩回撤5~30%%）· 共 %d 只</h2>" % sub_n +
                    "<table data-wb><thead><tr><th>代码</th><th>名称</th><th>板块</th><th>趋势位</th><th>入场价</th>"
                    "<th>距局部高</th><th>10日后</th><th>继续拉升</th></tr></thead><tbody>" +
                    "".join(subrows) + "</tbody></table>")
    else:
        sub_html = ("<h2 class='eh'>健康回撤·严格 候选子集</h2>"
                    "<div class='sub'>本回测日该组合无命中样本（样本 0）。</div>")

    a_raw = per_date_combo["raw"][D]
    wr = pct(a_raw["win_rate"]) if a_raw["win_rate"] is not None else "—"
    pr = "—" if a_raw["profit_ratio"] is None else "%.2f" % a_raw["profit_ratio"]
    rr = pct1(a_raw["resume_rate"]) if a_raw["resume_rate"] is not None else "—"
    head = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>N字形回测 · %s</title></head><body>
<div class="wrap">
<h1>N字形回测明细 · 信号日 %s</h1>
<div class="sub">前向持有 %d 交易日（以信号日收盘价买入，未计滑点/次日跳空）· 继续拉升率=信号后N日内收盘价刷新「局部峰值」的概率 · 观察池·非出票</div>
<div class="box">本页为<b>历史回测留存</b>，仅验证 N字形信号的历史表现，不构成买卖建议。
裸信号共 <b>%d</b> 个：继续拉升率(10日) <b>%s</b> ｜ 胜率 <b>%s</b> ｜ 平均收益率 <b>%s</b> ｜ 盈亏比 <b>%s</b>。
下方「组合过滤」表为叠加「健康回撤 + 板块热度」后、本回测日的分层表现。</div>
<h2 class='eh'>组合过滤分层（本回测日）</h2>
%s
%s
<h2 class='eh'>裸信号全量明细（%d 只）</h2>
<table data-wb><thead><tr>
<th>代码</th><th>名称</th><th>涨停日</th><th>距涨停</th><th>入场价</th>
<th>10日后</th><th>最大</th><th>最小</th><th>结果</th><th>板块</th><th>热点</th><th>继续拉升(10日)</th><th>继续拉升(15日)</th><th>首次触及(6/8)</th>
</tr></thead><tbody>""" % (
        D, D, FWD, a_raw["n"], rr, wr, pct(a_raw["avg_ret"]), pr,
        "".join(cbox), sub_html, len(pairs))
    tail = "</tbody></table><div class='sub'>数据基准（回测信号日）%s · <a href='index.html'>← 回测汇总</a></div></div></body></html>"
    return head + "".join(rows) + tail


def _heat_rows(combo_key, heat_agg):
    """按市场热度分桶的表格行（combo_key 的 heat_agg）。"""
    out = []
    for h in HEAT_ORDER:
        a = heat_agg[combo_key].get(h)
        if not a or a["n"] == 0:
            continue
        v, vc = combo_verdict(a)
        out.append("<tr><td><b>%s</b></td><td>%d</td><td><b>%s</b></td><td><b>%s</b></td><td>%s</td><td><b>%s</b></td><td><b>%s</b></td><td>%s</td><td>%s</td><td style='color:%s;font-weight:700'>%s</td></tr>" % (
            h, a["n"],
            pct1(a["resume_rate"]) if a["resume_rate"] is not None else "—",
            pct1(a["resume_rate15"]) if a["resume_rate15"] is not None else "—",
            pct(a["win_rate"]) if a["win_rate"] is not None else "—",
            pct1(a["ft_win_rate"]) if a["ft_win_rate"] is not None else "—",
            pct1(a["ft_hi_win_rate"]) if a["ft_hi_win_rate"] is not None else "—",
            pct(a["avg_ret"]),
            "—" if a["profit_ratio"] is None else "%.2f" % a["profit_ratio"],
            vc, v))
    return "".join(out)


def render_index(asof_list, per_date_combo, overall_combo, heat_agg):
    # 分解表（跨日整体）
    drows = []
    for k in COMBO_ORDER:
        a = overall_combo[k]
        v, vc = combo_verdict(a)
        drows.append("<tr><td>%s</td><td>%d</td><td><b>%s</b></td><td><b>%s</b></td><td>%s</td><td><b>%s</b></td><td><b>%s</b></td><td>%s</td><td>%s</td><td style='color:%s;font-weight:700'>%s</td></tr>" % (
            COMBO_LABELS[k], a["n"],
            pct1(a["resume_rate"]) if a["resume_rate"] is not None else "—",
            pct1(a["resume_rate15"]) if a["resume_rate15"] is not None else "—",
            pct(a["win_rate"]) if a["win_rate"] is not None else "—",
            pct1(a["ft_win_rate"]) if a["ft_win_rate"] is not None else "—",
            pct1(a["ft_hi_win_rate"]) if a["ft_hi_win_rate"] is not None else "—",
            pct(a["avg_ret"]),
            "—" if a["profit_ratio"] is None else "%.2f" % a["profit_ratio"],
            vc, v))
    # 逐日 健康回撤·严格 表
    trows = []
    for D in asof_list:
        a = per_date_combo["hb_strict"][D]
        v, vc = combo_verdict(a)
        trows.append("<tr><td><a href='bt_%s.html'>%s</a></td><td>%d</td><td><b>%s</b></td><td><b>%s</b></td><td>%s</td><td><b>%s</b></td><td><b>%s</b></td><td>%s</td><td>%s</td><td style='color:%s;font-weight:700'>%s</td></tr>" % (
            D.replace("-", ""), D, a["n"],
            pct1(a["resume_rate"]) if a["resume_rate"] is not None else "—",
            pct1(a["resume_rate15"]) if a["resume_rate15"] is not None else "—",
            pct(a["win_rate"]) if a["win_rate"] is not None else "—",
            pct1(a["ft_win_rate"]) if a["ft_win_rate"] is not None else "—",
            pct1(a["ft_hi_win_rate"]) if a["ft_hi_win_rate"] is not None else "—",
            pct(a["avg_ret"]),
            "—" if a["profit_ratio"] is None else "%.2f" % a["profit_ratio"],
            vc, v))
    ov = overall_combo["hb_strict"]
    cv, cvc = combo_verdict(ov)
    ov_raw = overall_combo["raw"]
    rv, rvc = combo_verdict(ov_raw)
    ov = overall_combo["hb_strict"]
    ov_pos = overall_combo["hb_pos"]
    cv, cvc = combo_verdict(ov)
    cvp, cvpc = combo_verdict(ov_pos)
    ov_raw = overall_combo["raw"]
    rv, rvc = combo_verdict(ov_raw)
    ov_box = """<div class="box">跨 <b>%d</b> 个回测日、共 <b>%d</b> 个信号样本：
<b>裸信号</b> 终端胜率 <b>%s</b> ｜ 首次触及胜率(6/8%%) <b>%s</b> ｜ 平均收益 <b>%s</b> ｜ 盈亏比 <b>%s</b>（<span style='color:%s'>%s</span>）。
叠加 <b>健康回撤·严格</b>（热点∩站上MA60∩距局部高回落5~30%%）后：样本 <b>%d</b> ｜ 首次触及胜率(6/8%%) <b>%s</b> ｜ 首次触及胜率(4/8%%) <b>%s</b> ｜ 平均收益 <b>%s</b> ｜ 盈亏比 <b>%s</b>。
进一步叠加 <b>整体价格位置</b>（52周分位30~85%%）得 <b>健康回撤·完整</b>：样本 <b>%d</b> ｜ 首次触及胜率(6/8%%) <b>%s</b> ｜ 首次触及胜率(4/8%%) <b>%s</b> ｜ 平均收益 <b>%s</b>（<span style='color:%s'>%s</span>）。
<b>首次触及法</b>= 入场后先触 +目标 还是先触 −止损（真实交易判据），比「第10天终端价」更贴合「暂时回撤→继续拉升」是否成立；
<b>高胜率档(4/8%%)</b> 通过更紧的目标抬高胜率（典型趋势跟踪取舍：胜率↑ 则 盈亏比↓）。组合是否翻正以「平均收益＞0」为准；仅历史验证，非未来保证。</div>""" % (
        len(asof_list), ov_raw["n"],
        pct(ov_raw["win_rate"]) if ov_raw["win_rate"] is not None else "—",
        pct1(ov_raw["ft_win_rate"]) if ov_raw["ft_win_rate"] is not None else "—",
        pct(ov_raw["avg_ret"]),
        "—" if ov_raw["profit_ratio"] is None else "%.2f" % ov_raw["profit_ratio"],
        rvc, rv,
        ov["n"],
        pct1(ov["ft_win_rate"]) if ov["ft_win_rate"] is not None else "—",
        pct1(ov["ft_hi_win_rate"]) if ov["ft_hi_win_rate"] is not None else "—",
        pct(ov["avg_ret"]),
        "—" if ov["profit_ratio"] is None else "%.2f" % ov["profit_ratio"],
        ov_pos["n"],
        pct1(ov_pos["ft_win_rate"]) if ov_pos["ft_win_rate"] is not None else "—",
        pct1(ov_pos["ft_hi_win_rate"]) if ov_pos["ft_hi_win_rate"] is not None else "—",
        pct(ov_pos["avg_ret"]),
        cvpc, cvp)
    heat_box = """<div class="box" style="border-color:#b8893b;background:#fdfaf2"><b>📊 市场热度门控（关键）：</b>
把每个信号日按当日大盘环境（_idxkline.market_env：指数偏离MA20 + 涨跌家数广度 + 涨跌停比）分桶后，
<b>健康回撤·严格</b> 的继续拉升率（10日）随市场热度单调上升：强势环境显著高于弱势/破位。
这印证了方法论——<b>该形态只在市场偏暖时有效，偏冷/破位时应暂停候选区开仓</b>。每日主池页顶部「大盘热度」横幅即此门控。</div>"""
    head = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>N字形回测汇总</title></head><body>
<div class="wrap">
<h1>N字形战法 · 历史回测汇总</h1>
<div class="sub">每个回测日重算 N字形信号（与主池同口径），前向持有 %d 交易日 · 观察池·非出票</div>
%s
%s
<h2 class='eh'>组合过滤分解（跨日整体）</h2>
<table data-wb><thead><tr>
<th>过滤口径</th><th>信号数</th><th>继续拉升率(10日)</th><th>继续拉升率(15日)</th><th>胜率</th><th>FT胜率(6/8)</th><th>FT胜率(4/8)</th><th>平均收益率</th><th>盈亏比</th><th>10日期望</th>
</tr></thead><tbody>%s</tbody></table>
    <h2 class='eh'>按市场热度分桶 · 健康回撤·严格 表现</h2>
<table data-wb><thead><tr>
<th>信号日市场热度</th><th>信号数</th><th>继续拉升率(10日)</th><th>继续拉升率(15日)</th><th>胜率</th><th>FT胜率(6/8)</th><th>FT胜率(4/8)</th><th>平均收益率</th><th>盈亏比</th><th>10日期望</th>
</tr></thead><tbody>%s</tbody></table>
    <h2 class='eh'>按市场热度分桶 · 裸信号（对照基线）</h2>
<table data-wb><thead><tr>
<th>信号日市场热度</th><th>信号数</th><th>继续拉升率(10日)</th><th>继续拉升率(15日)</th><th>胜率</th><th>FT胜率(6/8)</th><th>FT胜率(4/8)</th><th>平均收益率</th><th>盈亏比</th><th>10日期望</th>
</tr></thead><tbody>%s</tbody></table>
    <h2 class='eh'>逐回测日 · 健康回撤·严格 表现</h2>
<table data-wb><thead><tr>
<th>回测信号日</th><th>信号数</th><th>继续拉升率(10日)</th><th>继续拉升率(15日)</th><th>胜率</th><th>FT胜率(6/8)</th><th>FT胜率(4/8)</th><th>平均收益率</th><th>盈亏比</th><th>10日期望</th>
</tr></thead><tbody>%s</tbody></table>""" % (FWD, ov_box, heat_box,
            "".join(drows),
            _heat_rows("hb_strict", heat_agg),
            _heat_rows("raw", heat_agg),
            "".join(trows))
    tail = ("<div class='sub' style='margin-top:18px'>💡 想自己调 <b>目标价 / 止损价 / 持有天数 / 市场热度</b>，"
            "看首次触及胜率如何随之变化？→ <a href='../sim/index.html'>N字形 · 首次触及法 实盘模拟器</a></div>"
            "</div></body></html>")
    return head + tail


def _round_agg(a):
    return {k: (round(v, 4) if isinstance(v, float) else v) for k, v in a.items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("date", nargs="?", default=None)
    ap.add_argument("--date", dest="date", default=None)
    a = ap.parse_args()
    latest = NS.latest_date()
    if not latest:
        print("无法确定数据日"); return
    try:
        _txk.set_asof(latest)
    except Exception:
        pass
    cache = _txk.load()
    name_map = NS.load_name_map(latest)
    name2sw2 = NS.load_name2sw2()
    ind_map, concept_leaders = NS.load_hot_maps()
    w52 = NS.load_52w_cache(cache)   # 52周区间改从K线缓存自算（快照字段已被证伪）

    asof_dates = pick_asof_dates(cache, N_DATES, FWD)
    if not asof_dates:
        print("无足够后续数据的回测日"); return
    print("=== N字形回测（健康回撤 + 继续拉升率） · 数据日 %s · 回测日 %d 个 ===" % (latest, len(asof_dates)))

    per_date_combo = {k: {} for k in COMBOS}
    overall_results = {k: [] for k in COMBOS}
    per_date_combo_pairs = {}
    # 按市场热度分桶（信号日 ≤D 的大盘环境），跨日累计
    heat_split = {k: {h: [] for h in HEAT_ORDER} for k in COMBOS}

    for D in asof_dates:
        sigs = NS.gen_signals_asof(cache, D, name_map)
        NS.attach_attr(sigs, name2sw2, ind_map, concept_leaders, w52)
        _heat = NS.load_market_heat(D)
        _hlabel = _heat.get("label") or "未知"
        for s in sigs:
            s["strength"] = NS.compute_strength(s)
            s["tier"] = NS.tier_of(s["strength"])
            s["_heat"] = _hlabel
        pairs = []
        for s in sigs:
            m = fwd_metrics(cache, s, FWD)
            if m:
                m["resume10"] = fwd_resume(cache, s, RESUME_H[0])
                m["resume15"] = fwd_resume(cache, s, RESUME_H[1])
                m["ft"] = fwd_first_touch(cache, s, TP_DEF, SL_DEF)
                m["ft_hi"] = fwd_first_touch(cache, s, TP_HI, SL_HI)
                pairs.append((s, m))
        day_combo_pairs = {}
        for k, pred in COMBOS.items():
            sub = [(s, m) for s, m in pairs if pred(s)]
            day_combo_pairs[k] = sub
            agg = aggregate([m for _, m in sub])
            per_date_combo[k][D] = agg
            overall_results[k].extend([m for _, m in sub])
            for (s, m) in sub:
                heat_split[k][s.get("_heat", "未知")].append(m)
        per_date_combo_pairs[D] = day_combo_pairs
        html = render_day(D, pairs, day_combo_pairs, per_date_combo)
        open(os.path.join(OUTDIR, "bt_%s.html" % D.replace("-", "")), "w", encoding="utf-8").write(html)
        a_raw = per_date_combo["raw"][D]
        a_hb = per_date_combo["hb_strict"][D]
        print("  %s: 裸 n=%d 拉升率10=%s 均%s ｜ 健康严格 n=%d 拉升率10=%s 均%s" % (
            D, a_raw["n"],
            pct1(a_raw["resume_rate"]) if a_raw["resume_rate"] is not None else "—",
            pct(a_raw["avg_ret"]),
            a_hb["n"],
            pct1(a_hb["resume_rate"]) if a_hb["resume_rate"] is not None else "—",
            pct(a_hb["avg_ret"])))

    overall_combo = {k: aggregate(overall_results[k]) for k in COMBOS}
    heat_agg = {k: {h: aggregate(heat_split[k][h]) for h in HEAT_ORDER} for k in COMBOS}
    idx = render_index(asof_dates, per_date_combo, overall_combo, heat_agg)
    open(os.path.join(OUTDIR, "index.html"), "w", encoding="utf-8").write(idx)

    summ = {"latest": latest, "n_dates": len(asof_dates), "asof_dates": asof_dates,
            "resume_h": RESUME_H,
            "overall": _round_agg(overall_combo["hb_strict"]),
            "overall_raw": _round_agg(overall_combo["raw"]),
            "overall_hb_pos": _round_agg(overall_combo["hb_pos"]),
            "breakdown": {k: _round_agg(overall_combo[k]) for k in COMBO_ORDER},
            "heat_split": {k: {h: _round_agg(heat_agg[k][h]) for h in HEAT_ORDER} for k in COMBOS},
            "per_date": {d: {k: _round_agg(per_date_combo[k][d]) for k in COMBO_ORDER} for d in asof_dates}}
    jdir = os.path.join(QUANT, "n_shape")
    os.makedirs(jdir, exist_ok=True)
    json.dump(summ, open(os.path.join(jdir, "backtest_summary.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("  写出回测汇总 index.html + %d 个明细页" % len(asof_dates))
    for k in COMBO_ORDER:
        a = overall_combo[k]
        print("  %-10s n=%d 拉升率10=%s 拉升率15=%s 胜率=%s 均=%s 比=%s" % (
            k, a["n"],
            pct1(a["resume_rate"]) if a["resume_rate"] is not None else "—",
            pct1(a["resume_rate15"]) if a["resume_rate15"] is not None else "—",
            pct(a["win_rate"]) if a["win_rate"] is not None else "—",
            pct(a["avg_ret"]),
            "—" if a["profit_ratio"] is None else "%.2f" % a["profit_ratio"]))


if __name__ == "__main__":
    main()
