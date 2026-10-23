# -*- coding: utf-8 -*-
"""N字形战法 · 往前 10 日历史回测（留存页面 + 胜率 + 盈亏比）。

对最近 N 个「可回测日」（每个都有 >= FWD 个后续交易日）重算 N字形信号（复用
build_n_shape.gen_signals_asof，口径与主池完全一致），再以信号日收盘价买入、正向持有
FWD(=10) 个交易日的近似收益（未计滑点/次日开盘跳空），统计：
  · 胜率      = 10日后收益 > 0 的占比
  · 平均收益率 = 所有信号 10日后收益均值
  · 盈亏比    = 盈利均值 / |亏损均值|
并留存：web/n_shape/backtest/bt_{DS}.html（逐日明细）+ index.html（汇总）。

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


def render_day(D, sigs_with_ret, agg):
    rows = []
    for sig, m in sigs_with_ret:
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
    wr = pct(agg["win_rate"]) if agg["win_rate"] is not None else "—"
    pr = "—" if agg["profit_ratio"] is None else "%.2f" % agg["profit_ratio"]
    head = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>N字形回测 · %s</title></head><body>
<div class="wrap">
<h1>N字形回测明细 · 信号日 %s</h1>
<div class="sub">前向持有 %d 交易日（以信号日收盘价买入，未计滑点/次日跳空）· 观察池·非出票</div>
<div class="box">本页为<b>历史回测留存</b>，仅验证 N字形信号的历史表现，不构成买卖建议。
回测日共有 <b>%d</b> 个信号：胜率 <b>%s</b> ｜ 平均收益率 <b>%s</b> ｜ 盈亏比 <b>%s</b> ｜ 最佳 %s ／ 最差 %s。</div>
<table data-wb><thead><tr>
<th>代码</th><th>名称</th><th>涨停日</th><th>距涨停</th><th>入场价</th>
<th>10日后</th><th>最大</th><th>最小</th><th>结果</th><th>板块</th><th>热点</th>
</tr></thead><tbody>""" % (
        D, D, FWD, agg["n"], wr, pct(agg["avg_ret"]), pr, pct(agg["best"]), pct(agg["worst"]))
    tail = "</tbody></table><div class='sub'>数据基准（回测信号日）%s · <a href='index.html'>← 回测汇总</a></div></div></body></html>"
    return head + "".join(rows) + tail


def _hot_badge(hot):
    return "<span style='color:#1a73e8;font-weight:700'>✓</span>" if hot else "<span style='color:#9aa0a6'>—</span>"


def render_index(asof_list, per_date, overall):
    trs = []
    for D in asof_list:
        a = per_date[D]
        trs.append(
            "<tr><td><a href='bt_%s.html'>%s</a></td><td>%d</td>"
            "<td><b>%s</b></td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (
                D.replace("-", ""), D, a["n"],
                pct(a["win_rate"]) if a["win_rate"] is not None else "—",
                pct(a["avg_ret"]),
                "—" if a["profit_ratio"] is None else "%.2f" % a["profit_ratio"],
                pct(a["best"]), pct(a["worst"])))
    ov = """<div class="box">跨 %d 个回测日、共 <b>%d</b> 个信号样本：胜率 <b>%s</b> ｜ 平均收益率 <b>%s</b> ｜ 盈亏比 <b>%s</b>。
数值为正代表该窗口内 N字形信号整体有正向期望；<b>仅历史验证，非未来保证</b>。</div>""" % (
        len(asof_list), overall["n"],
        pct(overall["win_rate"]) if overall["win_rate"] is not None else "—",
        pct(overall["avg_ret"]),
        "—" if overall["profit_ratio"] is None else "%.2f" % overall["profit_ratio"])
    head = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>N字形回测汇总</title></head><body>
<div class="wrap">
<h1>N字形战法 · 往前 %d 日历史回测汇总</h1>
<div class="sub">每个回测日重算 N字形信号（与主池同口径），前向持有 %d 交易日 · 观察池·非出票</div>
%s
<h2 class='eh'>逐回测日表现</h2>
<table data-wb><thead><tr>
<th>回测信号日</th><th>信号数</th><th>胜率</th><th>平均收益率</th><th>盈亏比</th><th>最佳</th><th>最差</th>
</tr></thead><tbody>""" % (N_DATES, FWD, ov)
    tail = "</tbody></table><div class='sub'><a href='../index.html'>← 返回 N字形主池</a></div></div></body></html>"
    return head + "".join(trs) + tail


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("date", nargs="?", default=None)
    ap.add_argument("--date", dest="date", default=None)
    a = ap.parse_args()
    _d = _txk.last_date(_txk.load()) if False else None
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
    print("=== N字形回测 · 数据日 %s · 回测日 %d 个 ===" % (latest, len(asof_dates)))

    per_date = {}
    all_results = []
    for D in asof_dates:
        sigs = NS.gen_signals_asof(cache, D, name_map)
        NS.attach_attr(sigs, name2sw2, ind_map, concept_leaders, w52)
        pairs = []
        for s in sigs:
            m = fwd_metrics(cache, s, FWD)
            if m:
                pairs.append((s, m))
                all_results.append(m)
        agg = aggregate([m for _, m in pairs])
        per_date[D] = agg
        html = render_day(D, pairs, agg)
        open(os.path.join(OUTDIR, "bt_%s.html" % D.replace("-", "")), "w", encoding="utf-8").write(html)
        print("  %s: 信号 %d ｜ 胜率 %s ｜ 平均 %s ｜ 盈亏比 %s" % (
            D, agg["n"], pct(agg["win_rate"]) if agg["win_rate"] is not None else "—",
            pct(agg["avg_ret"]), "—" if agg["profit_ratio"] is None else "%.2f" % agg["profit_ratio"]))

    overall = aggregate(all_results)
    idx = render_index(asof_dates, per_date, overall)
    open(os.path.join(OUTDIR, "index.html"), "w", encoding="utf-8").write(idx)

    # 本地汇总 json（供门户卡片读取，不对外服务）
    summ = {"latest": latest, "n_dates": len(asof_dates), "asof_dates": asof_dates,
            "overall": {k: (round(v, 4) if isinstance(v, float) else v) for k, v in overall.items()},
            "per_date": {d: {k: (round(v, 4) if isinstance(v, float) else v) for k, v in a.items()} for d, a in per_date.items()}}
    jdir = os.path.join(QUANT, "n_shape")
    os.makedirs(jdir, exist_ok=True)
    json.dump(summ, open(os.path.join(jdir, "backtest_summary.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("  写出回测汇总 index.html + %d 个明细页 ｜ 整体胜率 %s 盈亏比 %s" % (
        len(asof_dates), pct(overall["win_rate"]) if overall["win_rate"] is not None else "—",
        "—" if overall["profit_ratio"] is None else "%.2f" % overall["profit_ratio"]))


if __name__ == "__main__":
    main()
