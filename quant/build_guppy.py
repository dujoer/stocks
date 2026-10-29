# -*- coding: utf-8 -*-
"""顾比倒数线 · 每日全市场扫描页（**观察池 · 非出票**）。

每天做的事：扫全市场 → 用 K 线识别「重要低点」→ 自该点向左倒数 3 条重要 K 线 →
取第 3 条最高价画水平**入场线**；同理自「重要高点」倒数取最低价画**止损线**。
产出两张清单：
    ① 今日收盘**站上**入场线（且昨日未站上）= 教科书式「趋势转折确认」触发
    ② 今日收盘**跌破**止损线（且昨日未跌破）= 教科书式「离场」触发
两张清单都**只是机械条件的记录**：页面顶部与底部的证据面板直接给出这条规则在三个
不同时间窗上的 canonical 检验结果（逐日平衡 edge / R3 / 留一），数字全部来自
quant/guppy/*.json 当日产物，**页面不写死任何统计数字**；产物缺失时显示「未生成」。

用法：python3 quant/build_guppy.py 2026-10-29   （或 --date YYYY-MM-DD）
"""
from __future__ import annotations
import argparse
import glob
import json
import os
import re
import sys

QUANT = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(QUANT)
WEB = os.path.join(ROOT, "web")
sys.path.insert(0, QUANT)
os.chdir(ROOT)

import _txk                      # noqa: E402
import _guppy_core as GU         # noqa: E402
import build_n_shape as NS       # noqa: E402

OUTDIR = os.path.join(WEB, "guppy")
EVID_DIR = os.path.join(QUANT, "guppy")
AMT_MIN = 30_000_000      # 20 日均成交额下限（与 N 字形同一流动性口径）
TOP_SHOW = 60             # 每张清单展示上限（超出的只计数，不截断数据）
CB_AGE_WARN = 60          # 倒数线来源距今 ≥ 该交易日数 → 标记为「远期」水平位（只提示，不筛选）
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}\.json$")


# ---------------------------------------------------------------- 扫描
def idx_of_date(bars, d):
    for i, b in enumerate(bars):
        if b["date"] == d:
            return i
        if b["date"] > d:
            return None
    return None


def scan_asof(cache, D):
    """扫全市场当日，返回 (可评估全部行, 今日站上行, 今日跌破止损行)。"""
    rows, up_rows, dn_rows = [], [], []
    for code, bars in cache.items():
        if not isinstance(bars, list) or len(bars) < GU.MIN_BARS:
            continue
        if NS.EXCLUDE_BJ and str(code).lower().startswith("bj"):
            continue
        i = idx_of_date(bars, D)
        if i is None:
            continue
        st = GU.eval_stock(code, bars, i)
        if st is None:
            continue
        st["amt20"] = None
        try:
            from _mkt_emo import amount_of
            seg = bars[max(0, i - 19):i + 1]
            vals = [amount_of(code, b.get("last"), b.get("volume")) for b in seg]
            vals = [v for v in vals if v]
            st["amt20"] = sum(vals) / len(vals) if vals else None
        except Exception:
            pass
        if st["amt20"] is None or st["amt20"] < AMT_MIN:
            continue
        rows.append(st)
        if st["cross_up"]:
            up_rows.append(st)
        if st["stop_break"]:
            dn_rows.append(st)
    return rows, up_rows, dn_rows


# ------------------------------------------------------- 证据读取（不写死）
def load_evidence():
    """读 guppy 目录下的证据产物；缺文件返回空，页面显示「未生成」。

    ★ 只认**最新数据日**的产物：证据脚本每天跑，目录里会攒下多天的
    variants_*/exit_pair_*（文件名带数据日）。若全部读入，证据面板会混进
    过期窗口 —— 那正是「拿旧数据冒充当日」。这里按产物内嵌的 date 字段取最大值，
    只加载该批；读不到 date 的一律不用（宁可不显示，也不猜它属于哪天）。
    """

    def _latest(pattern):
        """返回 (该批最新日期, [(path, json)])。"""
        got = []
        for p in sorted(glob.glob(os.path.join(EVID_DIR, pattern))):
            try:
                j = json.load(open(p, encoding="utf-8"))
            except Exception:
                continue
            d = j.get("date")
            if d:
                got.append((d, p, j))
        if not got:
            return None, []
        top = max(g[0] for g in got)
        return top, [(p, j) for d, p, j in got if d == top]

    ev = {"variants": [], "exit": None, "backtest": None}
    _, vs = _latest("variants_*.json")
    for p, j in vs:
        ev["variants"].append({"file": os.path.basename(p), **j})
    _, xs = _latest("exit_pair_*.json")
    if xs:
        ev["exit"] = {"file": os.path.basename(xs[-1][0]), **xs[-1][1]}
    _, bs = _latest("backtest_*.json")
    if bs:
        ev["backtest"] = {"file": os.path.basename(bs[-1][0]), **bs[-1][1]}
    return ev


KEY_VARIANTS = [
    ("raw_cross_up", "原生：收盘站上入场线"),
    ("cu_ma20", "＋站上MA20"),
    ("cu_vol15", "＋放量≥1.5倍"),
    ("confirm2", "连续2日站上"),
    ("cu_ret20_le10", "＋20日涨幅≤10%（不追高）"),
    ("combo_core", "＋MA20＋量能1.2倍（组合）"),
    ("stop_break", "对照：跌破止损线"),
]

MIN_N_ROWS = 1000     # 低于此样本量不进结论 （off120 那种个位/百位样本不参与定型）
COST_PP = 0.15        # 双边成本地板（佣金.05+印花.05+过户.002+滑点.05）


def verdict_of(ev):
    """由证据**现算**结论（不是把结论写死在页面上）。"""
    recs = []
    for v in ev["variants"]:
        win = "%s → %s" % (v.get("window", ["?", "?"])[0], v.get("window", ["?", "?"])[1])
        tag = v["file"].replace("variants_", "").replace(".json", "")
        for key, label in KEY_VARIANTS:
            r = (v.get("variants") or {}).get(key)
            if not r or r.get("edge") is None:
                continue
            recs.append({"win": win, "tag": tag, "key": key, "label": label,
                         "n": r.get("n_rows"), "edge": r["edge"], "r3": r.get("r3"),
                         "loo": r.get("loo_min")})
    big = [r for r in recs if (r["n"] or 0) >= MIN_N_ROWS and r["key"] != "stop_break"]
    lines, ok = [], False
    if not big:
        lines.append("未读到样本量充足的入场口径证据（≥%d 条），按「无证据」处理：不出票。" % MIN_N_ROWS)
    else:
        best = max(big, key=lambda r: r["edge"])
        signs = {r["edge"] > 0 for r in big}
        windows = sorted({r["win"] for r in big})
        lines.append("共 %d 条「入场类」口径参与定型，覆盖 %d 个时间窗：%s。"
                     % (len(big), len(windows), "、".join(windows)))
        lines.append("最强口径「%s」在最优窗 edge <b>%+.3fpp</b>（R3 %.1f%%，留一下限 %+.3fpp）；"
                     "符号在不同窗口<b>%s</b>。"
                     % (best["label"], best["edge"], best["r3"] or 0, best["loo"] or 0,
                        "一致" if len(signs) == 1 else "<span style='color:#d93025'>不一致</span>"))
        if len(signs) != 1:
            lines.append("→ 结论随行情段翻转（顺势暴露，不是无条件超额），<b>不可出票</b>。")
        elif best["edge"] <= 0:
            lines.append("→ 全窗口负超额，<b>不可出票</b>。")
        elif (best["r3"] or 0) < 95:
            lines.append("→ R3 未过 95%，robustness 不足，<b>不可出票</b>。")
        elif best["edge"] < COST_PP:
            lines.append("→ edge 低于双边成本地板 %.2fpp，<b>经济上不可执行</b>。" % COST_PP)
        else:
            ok = True
            lines.append("→ 通过门槛（可继续按第五/六道闸复核），但本页仍按观察池处理。")
    return ok, lines, big


# ---------------------------------------------------------------- 渲染
def _num(x, fmt="%.2f"):
    return "—" if x is None else fmt % x


def _updn(x, fmt="%+.2f%%"):
    if x is None:
        return "<td>—</td>"
    cls = "up" if x >= 0 else "dn"
    return "<td class='%s'>%s</td>" % (cls, fmt % x)


def _plan_cell(r):
    """买入/止损/目标：全部由真实 K 线算出，缺倒数止损线时明示兜底来源。"""
    p = GU.entry_plan(r)
    if not p:
        return "—", "—", "—"
    buy = round(p["buy"], 2)   # 保持为数值：模板里用 %.2f 输出（传字符串会报
                               # "must be real number, not str"）
    stop = "%.2f<br><span class='note'>%s</span>" % (p["stop"], p["stop_src"])
    res = "—" if p["resist"] is None else "%.2f<br><span class='note'>%s</span>" % (
        p["resist"], "空间 %+.1f%%" % p["resist_pct"])
    return buy, stop, res


def _up_table(ups, total):
    if not ups:
        return ("<h2 class='eh'>① 今日收盘站上倒数入场线</h2>"
                "<div class='sub'>今日<b>无</b>个股收盘首次站上倒数入场线（%d 只均不满足）。</div>" % total)
    ups = sorted(ups, key=lambda r: (r.get("line_dist_pct") if r.get("line_dist_pct") is not None else 999))
    shown = ups[:TOP_SHOW]
    h = ["<h2 class='eh'>① 今日收盘站上倒数入场线 · %d 只%s</h2>" % (
            len(ups), "（按站上幅度由小到大展示前 %d 只）" % TOP_SHOW if len(ups) > TOP_SHOW else ""),
         "<div class='sub'>「站上」= 当日<b>收盘价</b>（非盘中）高于倒数入场线、且昨日收盘未高于 → 教科书式转折确认触发。"
         "排序仅为机械口径（刚站上、离支撑更近者在前列），<b>不代表胜率高低</b>。</div>",
         "<table data-wb><thead><tr>"
         "<th>#</th><th>代码</th><th>名称</th><th>现价</th><th>倒数入场线</th><th>站上幅度</th>"
         "<th>重要低点(距今)</th><th>入场线来源日(距今)</th><th>量能比</th><th>20日涨幅</th>"
         "<th>参考买入</th><th>参考止损</th><th>20日高点/空间</th>"
         "</tr></thead><tbody>"]
    for i, r in enumerate(shown, 1):
        buy, stop, res = _plan_cell(r)
        # 倒数线来源过老 → 该水平线是「远期阻力」而非近端结构，必须标出来，
        # 不能让用户把它当成刚形成的关键位（此处只提示，不做筛选、不偷偷改口径）
        age = r.get("cb_age") or 0
        cb_cell = "%s<br><span class='note'>%d日前</span>" % (r.get("cb_date") or "—", age)
        if age >= CB_AGE_WARN:
            cb_cell += " <span title='倒数第3条重要K线距今较远，属远期水平位'>⚠远期</span>"
        h.append(
            "<tr><td>%d</td><td>%s</td><td>%s</td><td>%.2f</td><td>%.2f</td>%s"
            "<td>%s<br><span class='note'>%d日前</span></td><td>%s</td>"
            "<td>%s</td>%s<td>%.2f</td><td>%s</td><td>%s</td></tr>" % (
                i, r["code"], _name(r), r["close"], r["entry_line"],
                _updn(r.get("line_dist_pct")),
                r.get("pivot_date") or "—", r.get("pivot_age") or 0,
                cb_cell,
                _num(r.get("vol_ratio"), "%.2f"),
                _updn(r.get("ret20")), buy, stop, res))
    h.append("</tbody></table>")
    return "".join(h)


def _dn_table(dns, total):
    if not dns:
        return ("<h2 class='eh'>② 今日收盘跌破倒数止损线</h2>"
                "<div class='sub'>今日<b>无</b>个股收盘首次跌破倒数止损线。</div>")
    def _dp(r):
        """距止损线的幅度（负=已跌破）；用于「跌得越深越靠前」排序。"""
        sl = r.get("stop_line")
        if not sl or not r.get("close"):
            return 999.0
        return (r["close"] / sl - 1) * 100.0

    dns = sorted(dns, key=_dp)
    shown = dns[:TOP_SHOW]
    h = ["<h2 class='eh'>② 今日收盘跌破倒数止损线 · %d 只%s</h2>" % (
            len(dns), "（按跌破幅度由深到浅展示前 %d 只）" % TOP_SHOW if len(dns) > TOP_SHOW else ""),
         "<div class='sub'>「跌破」= 当日收盘低于倒数止损线、且昨日收盘未低于 → 教科书式离场触发。"
         "<b>给持仓者做离场自查用</b>；注意下方证据面板显示：把这条止损线当成万能离场规则，"
         "在全样本配对检验中<b>并未跑赢固定持有</b>，请勿机械照做。</div>",
         "<table data-wb><thead><tr>"
         "<th>#</th><th>代码</th><th>名称</th><th>现价</th><th>倒数止损线</th><th>距止损线</th>"
         "<th>重要高点(距今)</th><th>止损线来源日(距今)</th><th>量能比</th><th>20日涨幅</th><th>20日均额(亿)</th>"
         "</tr></thead><tbody>"]
    for i, r in enumerate(shown, 1):
        dist = r.get("stop_line")
        dp = None if not dist else (r["close"] / dist - 1) * 100
        h.append(
            "<tr><td>%d</td><td>%s</td><td>%s</td><td>%.2f</td><td>%.2f</td>%s"
            "<td>%s<br><span class='note'>%d日前</span></td><td>%s<br><span class='note'>%d日前</span></td>"
            "<td>%s</td>%s<td>%s</td></tr>" % (
                i, r["code"], _name(r), r["close"], dist or 0, _updn(dp),
                (r.get("high_pivot_date") or "—"), (r.get("high_pivot_age") or 0),
                r.get("stop_date") or "—", r.get("cb_age") or 0,
                _num(r.get("vol_ratio"), "%.2f"),
                _updn(r.get("ret20")),
                _num((r.get("amt20") or 0) / 1e8, "%.2f")))
    h.append("</tbody></table>")
    return "".join(h)


def _name(r):
    return r.get("name") or "—"


def _evidence_html(ev, ok, lines):
    if not ev["variants"] and not ev["exit"]:
        return ("<h2 class='eh'>③ 证据面板</h2>"
                "<div class='box'>尚未找到任何证据产物（<code>quant/guppy/*.json</code>）。"
                "按本站铁律「宁可不选、不编数据」，本页<b>不给出任何胜率或可交易结论</b>。</div>")
    color = "#188038" if ok else "#d93025"
    head = ("%s" % ("、".join(lines)))
    h = ["<h2 class='eh'>③ 证据面板（数字全部来自当日产物，页面不写死）</h2>",
         "<div class='box' style='border-left:4px solid %s'>"
         "<b style='color:%s'>结论：%s</b><br>%s</div>" % (
             color, color,
             "当前证据支持出票" if ok else "不可出票（观察池）", head)]

    if ev["variants"]:
        h.append("<div class='sub'>入场口径 canonical 检验：逐日平衡 edge（对照域 = 当日全部可判个股）、"
                 "按日 block bootstrap 的 R3 = P(edge&gt;0)、留一法下限。"
                 "样本量 &lt; %d 条的不参与定型。</div>" % MIN_N_ROWS)
        h.append("<table data-wb><thead><tr><th>时间窗</th><th>口径</th><th>样本</th>"
                 "<th>edge(pp)</th><th>R3%</th><th>留一下限(pp)</th></tr></thead><tbody>")
        for v in ev["variants"]:
            win = v.get("window") or ["?", "?"]
            tag = v["file"].replace("variants_", "").replace(".json", "")
            for key, label in KEY_VARIANTS:
                r = (v.get("variants") or {}).get(key)
                if not r:
                    continue
                if r.get("edge") is None:
                    h.append("<tr><td>%s→%s<br><span class='note'>%s</span></td><td>%s</td>"
                             "<td>%s</td><td colspan='3'>%s</td></tr>" % (
                                 win[0], win[1], tag, label, _num(r.get("n_rows"), "%d"),
                                 r.get("note") or "样本不足"))
                    continue
                small = (r.get("n_rows") or 0) < MIN_N_ROWS
                style = " style='color:#9aa0a6'" if small else ""
                ecls = "up" if r["edge"] >= 0 else "dn"
                h.append("<tr%s><td>%s→%s<br><span class='note'>%s</span></td><td>%s</td>"
                         "<td>%s</td><td class='%s'>%+.3f</td><td>%.1f</td><td>%+.3f</td></tr>" % (
                             style, win[0], win[1], tag, label,
                             _num(r.get("n_rows"), "%d"), ecls, r["edge"],
                             r.get("r3") or 0, r.get("loo_min") or 0))
        h.append("</tbody></table>")

    if ev["exit"]:
        e = ev["exit"]
        res = e.get("res") or {}
        h.append("<div class='sub'>离场规则配对检验：同一个开仓日同一批票，"
                 "「倒数止损线动态离场」对比「固定持有 %d 日」的逐日配对差 Δ。</div>" % e.get("hold", 0))
        h.append("<table data-wb><thead><tr><th>采样步长</th><th>样本日</th><th>固定持有%</th>"
                 "<th>止损线离场%</th><th>Δ(pp)</th><th>R3%</th><th>前半Δ</th><th>后半Δ</th>"
                 "</tr></thead><tbody>")
        for k in sorted(res):
            v = res[k]
            if not v:
                continue
            dcls = "up" if v["delta"] >= 0 else "dn"
            h.append("<tr><td>%s</td><td>%d</td><td>%+.3f</td><td>%+.3f</td><td class='%s'>%+.3f</td>"
                     "<td>%.1f</td><td>%+.3f</td><td>%+.3f</td></tr>" % (
                         k, v["n_days"], v["hold_A"], v["stop_B"], dcls, v["delta"],
                         v["r3"], v["half_first"], v["half_second"]))
        h.append("</tbody></table>")
        h.append("<div class='sub'>来源 <code>%s</code>｜跨步长同号：%s｜最差步长 R3：%s</div>" % (
            e.get("file", "—"),
            "是" if e.get("cross_step_same_sign") else "否",
            _num(e.get("min_r3"), "%.1f%%")))
    return "".join(h)


def render(D, rows, ups, dns, ev, ok, lines, heat):
    hb = ""
    if heat:
        lab = heat.get("label") or "未知"
        sc = heat.get("score")
        hb = ("<div class='heat'>📊 大盘热度：<b>%s</b>（环境分 %s）｜ "
              "指数偏离MA20 <b>%s</b> ｜ 涨跌家数广度 <b>%s</b></div>" % (
                  lab, "—" if sc is None else "%.2f" % sc,
                  "—" if heat.get("idx_dev") is None else "%+.2f%%" % heat["idx_dev"],
                  "—" if heat.get("breadth") is None else "%+.2f%%" % heat["breadth"]))
    head = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>顾比倒数线 · 每日扫描（观察池）</title>
</head><body>
<div class="wrap">
<h1>顾比倒数线 · 每日全市场扫描</h1>
<div class="sub">数据基准 %s ｜ 规则：自「重要低点」向左倒数 %d 条重要 K 线，取第 %d 条<b>最高价</b>画水平<b>入场线</b>；
自「重要高点」同样倒数取<b>最低价</b>画<b>止损线</b>；一律以<b>收盘价</b>判定（盘中穿越无效）</div>
%s
<div class="box">本页为<b>观察池 · 非出票</b>：只记录机械条件是否触发 + 真实 K 线算出的买卖参考位，
所有胜负数字摘自下方证据面板的当日产物，<b>页面不写死任何统计值</b>。
重要低点/高点用左右各 %d 根 K 线确认（pivot 至少滞后 %d 根才成立），因此重算历史任一日都不会用到当日之后的数据。
已剔除北交所与近 20 日日均成交额 &lt; %.0f 万元的个股，保证与回测口径同一流动性门槛。</div>
""" % (D, GU.CB_N, GU.CB_N, hb, GU.PIVOT_L, GU.PIVOT_R, AMT_MIN / 1e4)
    body = [_up_table(ups, len(rows)), _dn_table(dns, len(rows)),
            _evidence_html(ev, ok, lines),
            "<div class='box'><b>用法与边界</b><br>"
            "· 顾比倒数线的原始定位是<b>趋势转折的确认工具</b>，不是独立选股器。"
            "证据面板显示同一口径的 edge 会<b>随行情段翻转方向</b>——这更像是顺势暴露而非无条件超额，"
            "弱市里做多信号天然吃亏，请以面板当期数字为准。<br>"
            "· 「参考止损」优先取倒数止损线；取不到时退化为 −8% 兜底，并在单元格里明示来源，不冒充倒数线。<br>"
            "· 清单里没有任何排序具备事前预测能力的证据；把它当<b>候选观察名单</b>，配合板块/资金/基本面再自行判断。</div>"]
    tail = "</div></body></html>"
    return head + "".join(body) + tail


def build_archive():
    files = sorted(glob.glob(os.path.join(OUTDIR, "guppy_*.html")))
    items = "".join(
        "<li><a href='guppy_%s.html'>%s</a></li>" % (f, f)
        for f in (os.path.basename(p)[6:-5] for p in files))
    html = ("<!DOCTYPE html><html lang='zh-CN'><head><meta charset='utf-8'>"
            "<title>顾比倒数线 · 历史归档</title></head><body><div class='wrap'>"
            "<h1>顾比倒数线 · 历史归档</h1>"
            "<div class='sub'>每日扫描结果按交易日留存，最新一日见 <a href='index.html'>index.html</a></div>"
            "<ul>%s</ul></div></body></html>" % items)
    open(os.path.join(OUTDIR, "archive.html"), "w", encoding="utf-8").write(html)
    return len(files)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("date", nargs="?", default=None)
    ap.add_argument("--date", dest="date_opt", default=None)
    a = ap.parse_args()
    D = a.date or a.date_opt or NS.latest_date()
    if not D:
        print("无法确定数据日")
        return
    DS = D.replace("-", "")
    print("=== 顾比倒数线 · 每日扫描 · 数据日 %s ===" % D)

    _txk.set_asof(D)
    cache = _txk.load()
    name_map = NS.load_name_map(NS.latest_date() or D)
    rows, ups, dns = scan_asof(cache, D)
    for r in rows:
        r["name"] = name_map.get(r["code"])
    orig = len(rows)
    rows = [r for r in rows if not NS.excluded_name(r.get("name"))]
    ups = [r for r in ups if not NS.excluded_name(r.get("name"))]
    dns = [r for r in dns if not NS.excluded_name(r.get("name"))]
    print("  可判个股 %d 只（名称过滤前 %d）｜今日站上入场线 %d 只｜今日跌破止损线 %d 只"
          % (len(rows), orig, len(ups), len(dns)))

    try:
        heat = NS.load_market_heat(D)
    except Exception:
        heat = None
    ev = load_evidence()
    ok, lines, _big = verdict_of(ev)
    print("  证据结论：%s" % ("可出票（待复核）" if ok else "不可出票（观察池）"))
    for ln in lines:
        print("    · %s" % re.sub(r"<[^>]+>", "", ln))

    os.makedirs(OUTDIR, exist_ok=True)
    html = render(D, rows, ups, dns, ev, ok, lines, heat)
    open(os.path.join(OUTDIR, "guppy_%s.html" % DS), "w", encoding="utf-8").write(html)
    open(os.path.join(OUTDIR, "index.html"), "w", encoding="utf-8").write(html)
    n = build_archive()
    print("  写出 guppy_%s.html / index.html / archive.html（归档 %d 期）" % (DS, n))

    os.makedirs(EVID_DIR, exist_ok=True)
    slim = []
    for r in ups:
        keep = {k: r.get(k) for k in ("code", "name", "close", "entry_line", "stop_line",
                                      "line_dist_pct", "pivot_date", "pivot_age", "cb_date",
                                      "cb_age", "vol_ratio", "ret20", "ret60", "ma20", "ma60",
                                      "days_above", "amt20")}
        keep["plan"] = GU.entry_plan(r)
        slim.append(keep)
    jout = {"date": D, "n_evaluable": len(rows), "n_cross_up": len(ups),
            "n_stop_break": len(dns), "heat": heat,
            "verdict_ok": bool(ok), "verdict": [re.sub(r"<[^>]+>", "", x) for x in lines],
            "cross_up": slim}
    json.dump(jout, open(os.path.join(EVID_DIR, "scan_%s.json" % DS), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1, sort_keys=True)
    print("  写出 quant/guppy/scan_%s.json" % DS)


if __name__ == "__main__":
    main()
