# -*- coding: utf-8 -*-
"""N字形战法 · 往前 10 日历史回测（留存页面 + 胜率 + 盈亏比 + 组合过滤验证）。

对最近 N 个「可回测日」（每个都有 >= FWD 个后续交易日）重算 N字形信号（复用
build_n_shape.gen_signals_asof，口径与主池完全一致），再以信号日收盘价买入、正向持有
FWD(=10) 个交易日的近似收益（未计滑点/次日开盘跳空），统计：
  · 胜率      = 10日后收益 > 0 的占比
  · 平均收益率 = 所有信号 10日后收益均值
  · 盈亏比    = 盈利均值 / |亏损均值|

增强（2026-10-23 选项A）：叠加「强档(强度分≥70) ∩ 贴合热点 ∩ 回撤充分(距前高≤−25%)」
三重组合过滤，并做单因子分解（强档 / 热点 / 回撤 各自单独），验证裸信号经过滤后
10日持有期望能否翻正。所有结果如实呈现（含负期望），不编数据、不凑数。
本回测仅用于验证策略历史表现（观察池·非出票），不代表未来收益。
"""
from __future__ import annotations
import os, sys, json, datetime, argparse

QUANT = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(QUANT)
WEB = os.path.join(ROOT, "web")
sys.path.insert(0, QUANT)

import _txk
import build_n_shape as NS

FWD = NS.FWD                 # 前向持有交易日数（10）
N_DATES = 10                # 留存回测日数量（往前回测 10 天）
OUTDIR = os.path.join(WEB, "n_shape", "backtest")
os.makedirs(OUTDIR, exist_ok=True)

# 三重组合过滤阈值
DRAW_PCT = -25.0            # 距前高（涨停日高点）回撤至少 25% 才算「回撤充分、有空间」

COMBO_LABELS = {
    "raw": "裸信号（全量）",
    "strong": "强档（强度分≥%d）" % NS.TIER_STRONG,
    "hot": "贴合热点",
    "drawdown": "回撤充分（距前高≤%+.0f%%）" % DRAW_PCT,
    "hot_dd": "热点∩回撤充分（距前高≤%+.0f%%）" % DRAW_PCT,
    "combo": "三重组合（强档∩热点∩回撤）",
}
COMBO_ORDER = ["raw", "strong", "hot", "drawdown", "hot_dd", "combo"]


def is_strong(s):
    return s.get("tier") == "强"


def is_hot(s):
    return bool(s.get("hot"))


def is_drawdown(s):
    d = s.get("dist_prev_peak")
    return d is not None and d <= DRAW_PCT


COMBOS = {
    "raw": lambda s: True,
    "strong": is_strong,
    "hot": is_hot,
    "drawdown": is_drawdown,
    "hot_dd": lambda s: is_hot(s) and is_drawdown(s),
    "combo": lambda s: is_strong(s) and is_hot(s) and is_drawdown(s),
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


def aggregate(results):
    n = len(results)
    if n == 0:
        return {"n": 0, "win_rate": None, "avg_ret": None, "profit_ratio": None,
                "best": None, "worst": None}
    wins = [r["last_ret"] for r in results if r["last_ret"] > 0]
    losses = [r["last_ret"] for r in results if r["last_ret"] <= 0]
    avg_ret = sum(r["last_ret"] for r in results) / n
    win_rate = len(wins) / n
    profit_ratio = None
    if wins and losses:
        profit_ratio = (sum(wins) / len(wins)) / abs(sum(losses) / len(losses))
    best = max(results, key=lambda r: r["last_ret"])["last_ret"]
    worst = min(results, key=lambda r: r["last_ret"])["last_ret"]
    return {"n": n, "win_rate": win_rate, "avg_ret": avg_ret,
            "profit_ratio": profit_ratio, "best": best, "worst": worst}


def pct(x):
    return "—" if x is None else "%+.2f%%" % (x * 100)


def combo_verdict(agg):
    if agg["n"] == 0:
        return "样本不足", "#9aa0a6"
    if agg["avg_ret"] is not None and agg["avg_ret"] > 0:
        return "正期望", "#188038"
    return "负期望", "#d93025"


def _hot_badge(hot):
    return "<span style='color:#1a73e8;font-weight:700'>✓</span>" if hot else "<span style='color:#9aa0a6'>—</span>"


def render_day(D, pairs, day_combo_pairs, per_date_combo):
    # 全量原始明细
    rows = []
    for sig, m in pairs:
        win = m["last_ret"] > 0
        rows.append(
            "<tr><td>%s</td><td>%s%s</td><td>%s</td><td>%s</td><td>%.2f</td>"
            "<td class='%s'>%s</td><td class='%s'>%s</td><td class='%s'>%s</td>"
            "<td style='font-weight:700;color:%s'>%s</td><td>%s</td><td>%s</td></tr>" % (
                sig["code"], sig["name"] or "—",
                " <span style='color:#1a73e8'>●</span>" if sig.get("hot") else "",
                sig["last_zt_date"] or "—",
                ("%d日" % sig["days_since_zt"]) if sig["days_since_zt"] is not None else "—",
                m["entry"],
                "up" if m["last_ret"] >= 0 else "dn", pct(m["last_ret"]),
                "up" if m["max_ret"] >= 0 else "dn", pct(m["max_ret"]),
                "up" if m["min_ret"] >= 0 else "dn", pct(m["min_ret"]),
                "#188038" if win else "#d93025", "盈利" if win else "亏损",
                sig.get("sw2") or "—",
                _hot_badge(sig.get("hot"))))
    # 组合过滤汇总框（本回测日）
    cbox = ["<table data-wb><thead><tr><th>过滤口径</th><th>信号数</th><th>胜率</th><th>平均收益</th><th>盈亏比</th><th>10日期望</th></tr></thead><tbody>"]
    for k in COMBO_ORDER:
        a = per_date_combo[k][D]
        v, vc = combo_verdict(a)
        cbox.append("<tr><td>%s</td><td>%d</td><td><b>%s</b></td><td>%s</td><td>%s</td><td style='color:%s;font-weight:700'>%s</td></tr>" % (
            COMBO_LABELS[k], a["n"],
            pct(a["win_rate"]) if a["win_rate"] is not None else "—",
            pct(a["avg_ret"]),
            "—" if a["profit_ratio"] is None else "%.2f" % a["profit_ratio"],
            vc, v))
    cbox.append("</tbody></table>")
    # 热点∩深度回撤 子集表（B 选项主推过滤）
    sub = day_combo_pairs["hot_dd"]
    subrows = []
    for sig, m in sub:
        subrows.append("<tr><td>%s</td><td>%s</td><td>%s</td><td>%.2f</td><td class='%s'>%s</td><td>%s</td><td>%s</td></tr>" % (
            sig["code"], sig["name"] or "—", sig.get("sw2") or "—",
            m["entry"],
            "up" if m["last_ret"] >= 0 else "dn", pct(m["last_ret"]),
            ("%+.2f%%" % sig["dist_prev_peak"]) if sig.get("dist_prev_peak") is not None else "—",
            ("%d日" % sig["days_since_zt"]) if sig["days_since_zt"] is not None else "—"))
    sub_n = len(sub)
    if sub_n:
        sub_html = ("<h2 class='eh'>热点∩深度回撤过滤子集（贴合热点 且 距前高≤%+.0f%%）· 共 %d 只</h2>" % (DRAW_PCT, sub_n) +
                    "<table data-wb><thead><tr><th>代码</th><th>名称</th><th>板块</th><th>入场价</th>"
                    "<th>10日后</th><th>距前高</th><th>距涨停</th></tr></thead><tbody>" +
                    "".join(subrows) + "</tbody></table>")
    else:
        sub_html = ("<h2 class='eh'>热点∩深度回撤过滤子集</h2>"
                    "<div class='sub'>本回测日该组合无命中样本（样本 0）。</div>")

    a_raw = per_date_combo["raw"][D]
    wr = pct(a_raw["win_rate"]) if a_raw["win_rate"] is not None else "—"
    pr = "—" if a_raw["profit_ratio"] is None else "%.2f" % a_raw["profit_ratio"]
    head = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>N字形回测 · %s</title></head><body>
<div class="wrap">
<h1>N字形回测明细 · 信号日 %s</h1>
<div class="sub">前向持有 %d 交易日（以信号日收盘价买入，未计滑点/次日跳空）· 观察池·非出票</div>
<div class="box">本页为<b>历史回测留存</b>，仅验证 N字形信号的历史表现，不构成买卖建议。
裸信号共 <b>%d</b> 个：胜率 <b>%s</b> ｜ 平均收益率 <b>%s</b> ｜ 盈亏比 <b>%s</b>。
下方「组合过滤」表为叠加强档/热点/回撤三重条件后、本回测日的分层表现。</div>
<h2 class='eh'>组合过滤分层（本回测日）</h2>
%s
%s
<h2 class='eh'>裸信号全量明细（%d 只）</h2>
<table data-wb><thead><tr>
<th>代码</th><th>名称</th><th>涨停日</th><th>距涨停</th><th>入场价</th>
<th>10日后</th><th>最大</th><th>最小</th><th>结果</th><th>板块</th><th>热点</th>
</tr></thead><tbody>""" % (
        D, D, FWD, a_raw["n"], wr, pct(a_raw["avg_ret"]), pr,
        "".join(cbox), sub_html, len(pairs))
    tail = "</tbody></table><div class='sub'>数据基准（回测信号日）%s · <a href='index.html'>← 回测汇总</a></div></div></body></html>"
    return head + "".join(rows) + tail


def render_index(asof_list, per_date_combo, overall_combo):
    # 分解表（跨日整体）
    drows = []
    for k in COMBO_ORDER:
        a = overall_combo[k]
        v, vc = combo_verdict(a)
        drows.append("<tr><td>%s</td><td>%d</td><td><b>%s</b></td><td>%s</td><td>%s</td><td style='color:%s;font-weight:700'>%s</td></tr>" % (
            COMBO_LABELS[k], a["n"],
            pct(a["win_rate"]) if a["win_rate"] is not None else "—",
            pct(a["avg_ret"]),
            "—" if a["profit_ratio"] is None else "%.2f" % a["profit_ratio"],
            vc, v))
    # 逐日三重组合表
    trows = []
    for D in asof_list:
        a = per_date_combo["hot_dd"][D]
        v, vc = combo_verdict(a)
        trows.append("<tr><td><a href='bt_%s.html'>%s</a></td><td>%d</td><td><b>%s</b></td><td>%s</td><td>%s</td><td style='color:%s;font-weight:700'>%s</td></tr>" % (
            D.replace("-", ""), D, a["n"],
            pct(a["win_rate"]) if a["win_rate"] is not None else "—",
            pct(a["avg_ret"]),
            "—" if a["profit_ratio"] is None else "%.2f" % a["profit_ratio"],
            vc, v))
    ov = overall_combo["hot_dd"]
    cv, cvc = combo_verdict(ov)
    ov_raw = overall_combo["raw"]
    rv, rvc = combo_verdict(ov_raw)
    ov_combo = overall_combo["combo"]
    ov_box = """<div class="box">跨 <b>%d</b> 个回测日、共 <b>%d</b> 个信号样本：
<b>裸信号</b> 胜率 <b>%s</b> ｜ 平均收益 <b>%s</b> ｜ 盈亏比 <b>%s</b>（<span style='color:%s'>%s</span>）。
叠加 <b>热点∩深度回撤</b>（贴合热点 且 距前高≤%+.0f%%）后：样本 <b>%d</b> ｜ 胜率 <b>%s</b> ｜ 平均收益 <b>%s</b> ｜ 盈亏比 <b>%s</b>（<span style='color:%s'>%s</span>）。
（注：原「强档∩热点∩回撤」三重组合样本为 <b>%d</b>，条件过严无命中，已弃用；强度分=动量分，在本形态里为反向指标。）
组合是否翻正以「平均收益＞0」为准；仅历史验证，非未来保证。</div>""" % (
        len(asof_list), ov_raw["n"],
        pct(ov_raw["win_rate"]) if ov_raw["win_rate"] is not None else "—",
        pct(ov_raw["avg_ret"]),
        "—" if ov_raw["profit_ratio"] is None else "%.2f" % ov_raw["profit_ratio"],
        rvc, rv,
        DRAW_PCT, ov["n"],
        pct(ov["win_rate"]) if ov["win_rate"] is not None else "—",
        pct(ov["avg_ret"]),
        "—" if ov["profit_ratio"] is None else "%.2f" % ov["profit_ratio"],
        cvc, cv,
        ov_combo["n"])
    head = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>N字形回测汇总</title></head><body>
<div class="wrap">
<h1>N字形战法 · 往前 %d 日历史回测汇总</h1>
<div class="sub">每个回测日重算 N字形信号（与主池同口径），前向持有 %d 交易日 · 观察池·非出票</div>
%s
<h2 class='eh'>组合过滤分解（跨日整体）</h2>
<table data-wb><thead><tr>
<th>过滤口径</th><th>信号数</th><th>胜率</th><th>平均收益率</th><th>盈亏比</th><th>10日期望</th>
</tr></thead><tbody>%s</tbody></table>
    <h2 class='eh'>逐回测日 · 热点∩深度回撤 表现</h2>
<table data-wb><thead><tr>
<th>回测信号日</th><th>信号数</th><th>胜率</th><th>平均收益率</th><th>盈亏比</th><th>10日期望</th>
</tr></thead><tbody>%s</tbody></table>""" % (N_DATES, FWD, ov_box, "".join(drows), "".join(trows))
    tail = "</div></body></html>"
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
    w52 = NS.load_52w(latest)

    asof_dates = pick_asof_dates(cache, N_DATES, FWD)
    if not asof_dates:
        print("无足够后续数据的回测日"); return
    print("=== N字形回测（含组合过滤） · 数据日 %s · 回测日 %d 个 ===" % (latest, len(asof_dates)))

    per_date_combo = {k: {} for k in COMBOS}
    overall_results = {k: [] for k in COMBOS}
    per_date_combo_pairs = {}

    for D in asof_dates:
        sigs = NS.gen_signals_asof(cache, D, name_map)
        NS.attach_attr(sigs, name2sw2, ind_map, concept_leaders, w52)
        for s in sigs:
            s["strength"] = NS.compute_strength(s)
            s["tier"] = NS.tier_of(s["strength"])
        pairs = []
        for s in sigs:
            m = fwd_metrics(cache, s, FWD)
            if m:
                pairs.append((s, m))
        day_combo_pairs = {}
        for k, pred in COMBOS.items():
            sub = [(s, m) for s, m in pairs if pred(s)]
            day_combo_pairs[k] = sub
            agg = aggregate([m for _, m in sub])
            per_date_combo[k][D] = agg
            overall_results[k].extend([m for _, m in sub])
        per_date_combo_pairs[D] = day_combo_pairs
        html = render_day(D, pairs, day_combo_pairs, per_date_combo)
        open(os.path.join(OUTDIR, "bt_%s.html" % D.replace("-", "")), "w", encoding="utf-8").write(html)
        a_raw = per_date_combo["raw"][D]
        a_combo = per_date_combo["combo"][D]
        print("  %s: 裸 n=%d 胜率%s 均%s 比%s ｜ 组合 n=%d 胜率%s 均%s 比%s" % (
            D, a_raw["n"], pct(a_raw["win_rate"]) if a_raw["win_rate"] is not None else "—",
            pct(a_raw["avg_ret"]), "—" if a_raw["profit_ratio"] is None else "%.2f" % a_raw["profit_ratio"],
            a_combo["n"], pct(a_combo["win_rate"]) if a_combo["win_rate"] is not None else "—",
            pct(a_combo["avg_ret"]), "—" if a_combo["profit_ratio"] is None else "%.2f" % a_combo["profit_ratio"]))

    overall_combo = {k: aggregate(overall_results[k]) for k in COMBOS}
    idx = render_index(asof_dates, per_date_combo, overall_combo)
    open(os.path.join(OUTDIR, "index.html"), "w", encoding="utf-8").write(idx)

    summ = {"latest": latest, "n_dates": len(asof_dates), "asof_dates": asof_dates,
            "draw_pct": DRAW_PCT,
            "overall": _round_agg(overall_combo["hot_dd"]),
            "overall_raw": _round_agg(overall_combo["raw"]),
            "overall_combo": _round_agg(overall_combo["combo"]),
            "breakdown": {k: _round_agg(overall_combo[k]) for k in COMBO_ORDER},
            "per_date": {d: {k: _round_agg(per_date_combo[k][d]) for k in COMBO_ORDER} for d in asof_dates}}
    jdir = os.path.join(QUANT, "n_shape")
    os.makedirs(jdir, exist_ok=True)
    json.dump(summ, open(os.path.join(jdir, "backtest_summary.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    ov = overall_combo["combo"]
    print("  写出回测汇总 index.html + %d 个明细页" % len(asof_dates))
    print("  裸信号  整体: 胜率 %s 平均 %s 盈亏比 %s" % (
        pct(overall_combo["raw"]["win_rate"]) if overall_combo["raw"]["win_rate"] is not None else "—",
        pct(overall_combo["raw"]["avg_ret"]),
        "—" if overall_combo["raw"]["profit_ratio"] is None else "%.2f" % overall_combo["raw"]["profit_ratio"]))
    print("  三重组合整体: n=%d 胜率 %s 平均 %s 盈亏比 %s (%s)" % (
        ov["n"], pct(ov["win_rate"]) if ov["win_rate"] is not None else "—",
        pct(ov["avg_ret"]), "—" if ov["profit_ratio"] is None else "%.2f" % ov["profit_ratio"],
        combo_verdict(ov)[0]))


if __name__ == "__main__":
    main()
