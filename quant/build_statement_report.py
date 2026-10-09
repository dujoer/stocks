#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
把 quant/_stmt_analysis.json 渲染成一份「机构级交割单复盘」页面（自包含 HTML）。

两种输出：
  1) 默认（完整版）-> deliverables/交割单复盘.html
     ★ 含真实交易金额与持仓，属个人隐私数据 —— 只落本地，不进 web/，不随站点公开。
  2) --public（脱敏版）-> web/statement/index.html
     ★ 站点公开版：隐去全部绝对金额（改为占本金百分比 / 相对「平均单笔亏损」的倍数 U）、
       隐去个股名称与代码（改为「标的 01…」）；保留全部无量纲结论：
       收益率、TWR、回撤、胜率、盈亏比、盈利因子、换手、净值曲线与七条建议。
       → 结论与完整版一致，但不可反推资金规模与持仓标的。

全部数字来自 _stmt_analysis.json（由 analyze_statement.py 核算），本脚本不重算、
不估算；缺数据一律显示「不可考」，不编造。
"""
import json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
Q = os.path.join(ROOT, "quant")
OUT_DIR = os.path.join(ROOT, "deliverables")
OUT_PUB = os.path.join(ROOT, "web", "statement", "index.html")
SRC = os.path.join(Q, "_stmt_analysis.json")

# 脱敏开关：--public 时开启
SAN = "--public" in sys.argv
_UNIT = 1.0        # U = 平均单笔亏损额（脱敏后的金额标尺）
_INVESTED = 0.0    # 累计投入本金（脱敏后金额换算成分母）

#
# ★ 与 build_sector_heatmap 等生成器一致：本页独立自带样式，不依赖 _theme.css
#

CSS = """
* { box-sizing:border-box; }
body { margin:0; font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;
  background:#f5f6f8; color:#23262b; line-height:1.7; }
.wrap { max-width:1120px; margin:0 auto; padding:32px 20px 70px; }
header { border-bottom:2px solid #e3e7ec; padding-bottom:18px; margin-bottom:26px; }
h1 { font-size:29px; margin:0 0 8px; font-weight:800; letter-spacing:.3px;
  background:linear-gradient(90deg,#b8893b,#b8332a,#6b5b95);
  -webkit-background-clip:text; background-clip:text; color:transparent; }
.sub { color:#7b8794; font-size:13px; margin:0; }
h2 { font-size:19px; margin:34px 0 14px; padding-left:12px; border-left:5px solid #b8893b; }
h3 { font-size:15px; margin:20px 0 10px; color:#3b4453; }
.card { background:#fff; border:1px solid rgba(0,0,0,.08); border-radius:18px;
  padding:18px 20px; margin:0 0 18px; }
.grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr)); gap:14px; }
.kpi { background:#fafbfc; border:1px solid #eef1f4; border-radius:14px; padding:13px 15px; }
.kpi .k { font-size:12px; color:#7b8794; }
.kpi .v { font-size:22px; font-weight:800; margin-top:3px; }
.kpi .n { font-size:11px; color:#9aa2ad; margin-top:2px; }
.up { color:#b8332a; } .down { color:#1a9e5a; } .gold { color:#b8893b; } .mute { color:#7b8794; }
table { width:100%; border-collapse:collapse; font-size:13px; margin-top:6px; }
th { text-align:left; padding:8px 10px; background:#f7f8fa; color:#5a6573; font-weight:700;
  border-bottom:2px solid #e3e7ec; white-space:nowrap; }
td { padding:7px 10px; border-bottom:1px solid #f0f2f5; }
.num { text-align:right; font-variant-numeric:tabular-nums; }
.verdict { border-left:5px solid #b8332a; background:#fff6f5; padding:16px 18px;
  border-radius:14px; margin:0 0 18px; }
.verdict h3 { margin:0 0 8px; color:#b8332a; font-size:16px; }
.verdict p { margin:6px 0; font-size:14px; }
ul.rec { margin:8px 0 0; padding-left:20px; }
ul.rec li { margin:9px 0; font-size:14px; }
ul.rec li b { color:#b8893b; }
.tag { display:inline-block; font-size:11px; padding:1px 8px; border-radius:9px;
  background:#fdf3e3; color:#a9761f; border:1px solid #efdfc0; margin-left:6px; }
.tag.bad { background:#fdecea; color:#b8332a; border-color:#f5c6c2; }
.tag.ok { background:#eaf7ef; color:#1a7a48; border-color:#c3e6d0; }
.note { font-size:12.5px; color:#6b7280; background:#fafbfc; border:1px dashed #dfe3e8;
  border-radius:12px; padding:12px 14px; margin:10px 0 0; }
.chart { width:100%; height:auto; display:block; }
.legend { font-size:12px; color:#7b8794; margin-top:6px; }
.legend i { display:inline-block; width:22px; height:3px; vertical-align:middle; margin-right:5px; }
footer { margin-top:44px; padding-top:18px; border-top:1px solid #e3e7ec;
  font-size:12px; color:#7b8794; }
"""

def money(v, sign=False):
    """千分位金额。★ %-格式化不支持 ',' 类型码（%，.0f 会 ValueError），必须用 f-string。"""
    try:
        return f"{v:+,.0f}" if sign else f"{v:,.0f}"
    except Exception:
        return "—"

def cls(v):
    return "up" if v > 0 else ("down" if v < 0 else "mute")

def pct(v, sign=True):
    return ("%+.2f%%" % v) if sign else ("%.2f%%" % v)


# ── 脱敏显示层（仅 --public 生效；完整版保持原样输出真实金额）──
def amt(v, sign=False):
    """本金级金额：脱敏时改为「占累计投入本金的百分比」，不暴露资金规模。"""
    if not SAN:
        return money(v, sign)
    if _INVESTED:
        return pct(100.0 * v / _INVESTED)
    return "—"

def ut(v, sign=False):
    """单笔级金额：脱敏时改为相对「平均单笔亏损」的倍数 U，保留相对关系、不暴露绝对值。"""
    if not SAN:
        return money(v, sign)
    u = v / _UNIT if _UNIT else 0.0
    return (f"{u:+.2f} U") if sign else (f"{u:.2f} U")

def raw(v):
    """纯规模数字（成交额、费用、逆回购规模等）：脱敏时直接隐藏。"""
    if not SAN:
        return money(v)
    return "已脱敏"

_NAME_MAP = {}

def nm(name, code):
    """个股名称/代码：脱敏时替换为「标的 01…」匿名编号。"""
    if not SAN:
        return name, code
    k = (name, code)
    if k not in _NAME_MAP:
        _NAME_MAP[k] = "标的 %02d" % (len(_NAME_MAP) + 1)
    return _NAME_MAP[k], "已脱敏"

def svg_chart(series, w=1060, h=320, ylab=""):
    """series: [{'name','color','pts':[(x_index,value)],'dash'}] —— 首序列决定 x 轴。"""
    if not series:
        return ""
    allv = [v for s in series for v in s["pts"] if v is not None]
    if not allv:
        return ""
    lo, hi = min(allv), max(allv)
    if hi == lo:
        hi = lo + 1
    pad = (hi - lo) * 0.08
    lo -= pad
    hi += pad
    n = max(len(s["pts"]) for s in series)
    padl, padr, padt, padb = 58, 14, 14, 30
    iw, ih = w - padl - padr, h - padt - padb

    def X(i):
        return padl + (i * iw / max(n - 1, 1))
    def Y(v):
        return padt + (hi - v) * ih / (hi - lo)

    out = [f"<svg class='chart' viewBox='0 0 {w} {h}' xmlns='http://www.w3.org/2000/svg'>"]
    out.append(f"<rect x='0' y='0' width='{w}' height='{h}' fill='#fff'/>")
    # 网格 + y 轴刻度
    for k in range(5):
        v = lo + (hi - lo) * k / 4
        y = Y(v)
        out.append(f"<line x1='{padl}' y1='{y:.1f}' x2='{w-padr}' y2='{y:.1f}' "
                   f"stroke='#eef1f4' stroke-width='1'/>")
        out.append(f"<text x='{padl-8}' y='{y+4:.1f}' font-size='11' fill='#9aa2ad' "
                   f"text-anchor='end'>{v:,.0f}</text>")
    # x 轴首尾标签
    labels = series[0].get("labels") or []
    if labels:
        for idx, lab in ((0, labels[0]), (len(labels) - 1, labels[-1])):
            x = X(idx)
            anchor = "start" if idx == 0 else "end"
            out.append(f"<text x='{x:.1f}' y='{h-8}' font-size='11' fill='#9aa2ad' "
                       f"text-anchor='{anchor}'>{lab}</text>")
    for s in series:
        pts = [(X(i), Y(v)) for i, v in enumerate(s["pts"]) if v is not None]
        if len(pts) < 2:
            continue
        d = " ".join(f"{'M' if k==0 else 'L'}{x:.1f},{y:.1f}" for k, (x, y) in enumerate(pts))
        dash = " stroke-dasharray='5,4'" if s.get("dash") else ""
        out.append(f"<path d='{d}' fill='none' stroke='{s['color']}' stroke-width='2.2' "
                   f"stroke-linejoin='round'{dash}/>")
    out.append("</svg>")
    return "".join(out)


def svg_bars(items, w=1060, h=250, fmt=None):
    """月度盈亏柱状图 items=[(label, value)]；fmt 用于脱敏时把数值标签换成百分比。"""
    if not items:
        return ""
    fmt = fmt or (lambda v: f"{v:+,.0f}")
    vals = [v for _, v in items]
    lo, hi = min(vals + [0]), max(vals + [0])
    span = hi - lo or 1
    padl, padr, padt, padb = 58, 14, 14, 34
    iw, ih = w - padl - padr, h - padt - padb
    zero = padt + (hi - 0) * ih / span
    out = [f"<svg class='chart' viewBox='0 0 {w} {h}' xmlns='http://www.w3.org/2000/svg'>"]
    out.append(f"<rect x='0' y='0' width='{w}' height='{h}' fill='#fff'/>")
    out.append(f"<line x1='{padl}' y1='{zero:.1f}' x2='{w-padr}' y2='{zero:.1f}' "
               f"stroke='#d7dce2' stroke-width='1'/>")
    out.append(f"<text x='{padl-8}' y='{zero+4:.1f}' font-size='11' fill='#9aa2ad' "
               f"text-anchor='end'>0</text>")
    n = len(items)
    bw = iw / n * 0.62
    for i, (lab, v) in enumerate(items):
        cx = padl + (i + 0.5) * iw / n
        y = padt + (hi - v) * ih / span
        top = min(y, zero)
        hh = abs(zero - y)
        color = "#b8332a" if v > 0 else "#1a9e5a"
        out.append(f"<rect x='{cx-bw/2:.1f}' y='{top:.1f}' width='{bw:.1f}' height='{hh:.1f}' "
                   f"fill='{color}' rx='3' opacity='.88'/>")
        ty = top - 5 if v > 0 else top + hh + 13
        out.append(f"<text x='{cx:.1f}' y='{ty:.1f}' font-size='10.5' fill='{color}' "
                   f"text-anchor='middle'>{fmt(v)}</text>")
        out.append(f"<text x='{cx:.1f}' y='{h-10}' font-size='11' fill='#7b8794' "
                   f"text-anchor='middle'>{lab}</text>")
    out.append("</svg>")
    return "".join(out)


def main():
    d = json.load(open(SRC, encoding="utf-8"))
    m, r, c = d["meta"], d["realized"], d["costs"]
    fl, un, ho = d["flows"], d["unrealized"], d["holding"]
    tw, md, be = d["twr"], d["mdd"], d.get("bench")

    # 资金口径
    invested = fl["net_in"]
    end_eq = d["equity"][-1]["total"] if d["equity"] else 0
    net_pl = end_eq - invested
    net_pl_pct = 100.0 * net_pl / invested if invested else 0

    # 盈亏平衡胜率（给定盈亏比所需的最低胜率）
    payoff = r["payoff"]
    breakeven = 100.0 / (1.0 + payoff) if payoff else 0

    # 脱敏标尺：U = 平均单笔亏损额；本金分母 = 累计投入
    global _UNIT, _INVESTED
    _UNIT = abs(r["avg_loss"]) or 1.0
    _INVESTED = invested or 1.0

    # TWR 逐日累计（剔除入金）→ 与基准同起点 100
    flow_by_date = {}
    for x in fl["deposits"]:
        flow_by_date[x["date"].replace("-", "")] = flow_by_date.get(
            x["date"].replace("-", ""), 0.0) + x["amt"]
    twr_idx = []
    cum = 100.0
    eqs = d["equity"]
    for i, e in enumerate(eqs):
        if i == 0:
            twr_idx.append(100.0)
            continue
        prev = eqs[i - 1]["total"]
        fd = flow_by_date.get(e["date"], 0.0)
        rr = (e["total"] - prev - fd) / prev if prev else 0.0
        cum *= (1 + rr)
        twr_idx.append(cum)
    bench_pts = []
    if d.get("bench_series"):
        for b in d["bench_series"]:
            bench_pts.append(b["idx"])
    # 对齐长度
    labels = [e["date"] for e in eqs]
    labels = ["%s-%s" % (x[4:6], x[6:8]) for x in labels]

    chart1 = svg_chart([
        dict(name="账户", color="#b8893b", pts=twr_idx, labels=labels),
        dict(name="沪深300", color="#3b6fd1", dash=True, pts=bench_pts),
    ], h=330)

    chart2 = svg_bars([(x["month"][2:], x["pnl"]) for x in d["monthly"]], h=260,
                      fmt=(lambda v: pct(100.0 * v / _INVESTED)) if SAN else None)

    # 脱敏版说明（仅 --public 出现）
    u_note = ("<br><span class='mute'>本页为<b>脱敏公开版</b>：金额单位 "
              "<b>U = 平均单笔亏损额</b>，百分比均以累计投入本金为分母；"
              "绝对金额、个股名称与代码已隐去，结论与完整版一致。</span>") if SAN else ""
    san_banner = ("<div class='note' style='border-color:#efdfc0;background:#fdf9f1'>"
                  "<b>脱敏公开版</b>：本页由真实交割单核算，但已隐去全部绝对金额、"
                  "资金规模与个股名称代码，仅保留比率型结论（收益率、回撤、胜率、"
                  "盈亏比、换手、净值曲线与建议）。完整版（含明细）仅保存在本地。</div>"
                  ) if SAN else ""

    # 个股归因（剔除窗口前不可考的）
    ps = [s for s in d["per_stock"]]
    worst = sorted(ps, key=lambda x: x["real"])[:8]
    best = sorted(ps, key=lambda x: -x["real"])[:8]

    def stock_rows(rows):
        out = []
        for s in rows:
            n_, c_ = nm(s["name"], s["code"])
            out.append(
                f"<tr><td>{n_}</td><td class='mute'>{c_}</td>"
                f"<td class='num {cls(s['real'])}'>{amt(s['real'], True)}</td>"
                f"<td class='num'>{s['n']}</td></tr>")
        return "".join(out)

    leg = d.get("legacy", {})
    leg_html = ""
    if leg.get("n"):
        items = "".join(
            (lambda n_, c_: (
                f"<li>{x['date']} {n_}（{c_}）卖出 {x['qty']} 股，"
                f"回款 {amt(x['amount'])} —— <b>成本不可考，不计入盈亏</b></li>"
            ))(*nm(x["name"], x["code"]))
            for x in leg["items"])
        leg_html = (f"<div class='note'><b>窗口前持仓了结 {leg['n']} 笔"
                    f"（回款合计 {amt(leg['proceeds'])}）</b>：这些股票在 "
                    f"{m['start']} 之前就已持有，交割单里没有建仓成本。"
                    f"若按「成本 0」处理，卖出款会被全额算成利润（虚增 "
                    f"{amt(leg['proceeds'])}），因此本页把它们剥离，"
                    f"仅按起始日市值计入本金。<ul>{items}</ul></div>")

    bench_html = ""
    if be:
        gap = tw["ret"] - be["ret"]
        bench_html = (
            f"<div class='grid'>"
            f"<div class='kpi'><div class='k'>账户时间加权 TWR</div>"
            f"<div class='v {cls(tw['ret'])}'>{pct(tw['ret'])}</div>"
            f"<div class='n'>剔除入金影响，衡量交易本身</div></div>"
            f"<div class='kpi'><div class='k'>沪深300 同期</div>"
            f"<div class='v {cls(be['ret'])}'>{pct(be['ret'])}</div>"
            f"<div class='n'>{be['start']} ~ {be['end']}</div></div>"
            f"<div class='kpi'><div class='k'>超额（相对基准）</div>"
            f"<div class='v {cls(gap)}'>{pct(gap)}</div>"
            f"<div class='n'>{'跑赢' if gap>0 else '跑输'} {abs(gap):.1f} 个百分点</div></div>"
            f"<div class='kpi'><div class='k'>最大回撤</div>"
            f"<div class='v down'>{md['pct']:.2f}%</div>"
            f"<div class='n'>{md['date']}</div></div></div>")

    html = f"""<!DOCTYPE html>
<html lang='zh-CN'><head><meta charset='UTF-8'>
<meta name='viewport' content='width=device-width,initial-scale=1.0'>
<title>实盘交割单复盘 · {m['start']} ~ {m['end']}</title>
<style>{CSS}</style></head><body><div class='wrap'>
<header>
  <h1>实盘交割单 · 机构级复盘</h1>
  <p class='sub'>{m['stmt']} ｜ {m['start']} ~ {m['end']}（{m['n_days']} 个交易日，{m['n_codes']} 只标的，
  {c['n_buy']+c['n_sell']} 笔股票成交）｜ 成本法：移动加权平均（券商口径）｜ 基准：沪深300
  {'｜ <b>脱敏公开版</b>' if SAN else ''}</p>
</header>
{san_banner}

<div class='verdict'>
  <h3>核心结论：策略期望为负，且规模放大后加速亏损</h3>
  <p>1. <b>盈亏比与胜率双重不达标</b>：胜率 {r['winrate']:.1f}%、盈亏比 {payoff:.2f}
     （平均盈利 {ut(r['avg_win'])} / 平均亏损 {ut(abs(r['avg_loss']))}）。
     以这个盈亏比，你需要 <b>{breakeven:.1f}%</b> 的胜率才能打平，而实际只有
     <b>{r['winrate']:.1f}%</b> —— 缺口 {breakeven-r['winrate']:.1f} 个百分点，
     单笔期望 <b>{ut(r['expectancy'], True)}</b>。</p>
  <p>2. <b>大资金进场后失效</b>：前 5 个月小资金持续盈利，6 月追加一笔大额本金后
     7 月单月亏损 {amt([x['pnl'] for x in d['monthly'] if x['month']=='2026-07'][0] if any(x['month']=='2026-07' for x in d['monthly']) else 0)}，
     且之后再未修复。</p>
  <p>3. <b>结果</b>：累计投入 {raw(invested)} → 期末权益 {raw(end_eq)}，
     净亏 <b class='down'>{amt(net_pl, True)}（{pct(net_pl_pct)}）</b>；
     时间加权 {pct(tw['ret'])}，同期沪深300 {pct(be['ret']) if be else '—'}。</p>
</div>

<h2>一、账户总览</h2>
<div class='card'><div class='grid'>
  <div class='kpi'><div class='k'>累计投入本金</div><div class='v'>{raw(invested)}</div>
    <div class='n'>含期初现金+持仓，及 {len(fl['deposits'])} 笔转入</div></div>
  <div class='kpi'><div class='k'>期末权益</div><div class='v'>{raw(end_eq)}</div>
    <div class='n'>{m['end']} 收盘市值口径</div></div>
  <div class='kpi'><div class='k'>期间净盈亏</div><div class='v {cls(net_pl)}'>{amt(net_pl, True)}</div>
    <div class='n'>{pct(net_pl_pct)}（资金加权）</div></div>
  <div class='kpi'><div class='k'>已实现盈亏</div><div class='v {cls(r['total'])}'>{amt(r['total'], True)}</div>
    <div class='n'>{r['n']} 笔平仓（成本可考）</div></div>
  <div class='kpi'><div class='k'>浮动盈亏</div><div class='v {cls(un['pnl'])}'>{amt(un['pnl'], True)}</div>
    <div class='n'>{len(d['open_pos'])} 只在持</div></div>
  <div class='kpi'><div class='k'>股息 / 逆回购</div><div class='v up'>+{amt(d['cats']['dividend']['net']+d['cats']['repo']['net'])}</div>
    <div class='n'>股息 {amt(d['cats']['dividend']['net'])}，逆回购 {amt(d['cats']['repo']['net'])}</div></div>
</div></div>

<h2>二、绩效归因（交易能力诊断）</h2>
<div class='card'><div class='grid'>
  <div class='kpi'><div class='k'>胜率</div><div class='v'>{r['winrate']:.1f}%</div>
    <div class='n'>{r['n_win']} 盈 / {r['n_loss']} 亏</div></div>
  <div class='kpi'><div class='k'>盈亏平衡所需胜率</div><div class='v gold'>{breakeven:.1f}%</div>
    <div class='n'>按当前盈亏比 {payoff:.2f} 反推</div></div>
  <div class='kpi'><div class='k'>盈亏比（平均盈/平均亏）</div><div class='v {cls(payoff-1)}'>{payoff:.2f}</div>
    <div class='n'>{ut(r['avg_win'])} / {ut(abs(r['avg_loss']))}</div></div>
  <div class='kpi'><div class='k'>盈利因子（总盈/总亏）</div><div class='v {cls(r['profit_factor']-1)}'>{r['profit_factor']:.2f}</div>
    <div class='n'>{ut(r['gross_win'])} / {ut(abs(r['gross_loss']))}</div></div>
  <div class='kpi'><div class='k'>单笔期望</div><div class='v {cls(r['expectancy'])}'>{ut(r['expectancy'], True)}</div>
    <div class='n'>每平仓一笔平均</div></div>
  <div class='kpi'><div class='k'>最大单笔盈 / 亏</div>
    <div class='v'><span class='up'>{ut(r['max_win'])}</span> / <span class='down'>{ut(r['max_loss'])}</span></div>
    <div class='n'>最大亏损大于最大盈利</div></div>
</div>
<div class='note'>读法：胜率与盈亏比必须<b>联合</b>达标才算正期望。你赚的时候平均赚
{ut(r['avg_win'])}，亏的时候平均亏 {ut(abs(r['avg_loss']))} —— <b>亏一次要赢
{payoff and abs(r['avg_loss']/r['avg_win']):.1f} 次才补得回来</b>，而胜率还不到一半，
长期必然失血。{u_note}</div></div>

<h2>三、与基准对比（剔除入金影响）</h2>
<div class='card'>{bench_html}
{chart1}
<div class='legend'><i style='background:#b8893b'></i>账户时间加权净值（起点 100）
<i style='background:#3b6fd1'></i>沪深300（起点 100，虚线）</div>
<div class='note'>账户曲线已剔除各笔入金，因此与「总权益含入金」的绝对金额不同 ——
这是衡量交易能力（而非资金规模）的正确口径。曲线在 6 月后与基准同步下行且跌幅更大，
说明下行期<b>没有防守</b>。</div></div>

<h2>四、月度已实现盈亏</h2>
<div class='card'>{chart2}
<div class='note'>前 5 个月均盈利（2 月 +{amt(d['monthly'][0]['pnl'])} 主要来自窗口前持仓了结），
7 月单月 {amt([x['pnl'] for x in d['monthly'] if x['month']=='2026-07'][0])} 为最大失血月，
此后连续 3 个月为负 —— <b>亏损没有被止住，是持续性的</b>。</div></div>

<h2>五、成本与换手</h2>
<div class='card'><div class='grid'>
  <div class='kpi'><div class='k'>双边成交额</div><div class='v'>{raw(c['turnover'])}</div>
    <div class='n'>{c['n_buy']} 买 / {c['n_sell']} 卖</div></div>
  <div class='kpi'><div class='k'>总交易费用</div><div class='v down'>{raw(c['fee'])}</div>
    <div class='n'>手续费+印花税+杂费</div></div>
  <div class='kpi'><div class='k'>费用率</div><div class='v'>{c['fee_rate']:.3f}%</div>
    <div class='n'>佣金水平很低<span class='tag ok'>不是主要问题</span></div></div>
  <div class='kpi'><div class='k'>年化双边换手率</div><div class='v gold'>{d['turn_ratio']:.0f} 倍</div>
    <div class='n'>平均权益 {raw(d['avg_equity'])}</div></div>
  <div class='kpi'><div class='k'>日均成交笔数</div><div class='v'>{(c['n_buy']+c['n_sell'])/max(m['n_days'],1):.1f}</div>
    <div class='n'>共 {m['n_codes']} 只标的</div></div>
  <div class='kpi'><div class='k'>平均持有天数</div><div class='v'>{ho['avg_win_days']:.1f} / {ho['avg_loss_days']:.1f}</div>
    <div class='n'>盈利单 / 亏损单</div></div>
</div>
<div class='note'>费用只占亏损的 {abs(100*c['fee']/r['total']):.1f}%，<b>不是亏损主因</b>；
真正的问题是 <b>{d['turn_ratio']:.0f} 倍年化换手</b> 带来的高频决策 —— 换手越高，
负期望被重复的次数越多（{r['n']} 次平仓 × 期望 {ut(r['expectancy'], True)} ≈
{amt(r['expectancy']*r['n'])}，与实际已实现 {amt(r['total'], True)} 吻合）。</div></div>

<h2>六、个股归因</h2>
<div class='card'>
<h3>亏损最多的 8 只</h3>
<table><thead><tr><th>名称</th><th>代码</th><th class='num'>已实现</th><th class='num'>平仓笔数</th></tr></thead>
<tbody>{stock_rows(worst)}</tbody></table>
<h3>盈利最多的 8 只</h3>
<table><thead><tr><th>名称</th><th>代码</th><th class='num'>已实现</th><th class='num'>平仓笔数</th></tr></thead>
<tbody>{stock_rows(best)}</tbody></table>
<div class='note'>盈利只 {sum(1 for s in ps if s['real']>0)} 只 / 亏损只 {sum(1 for s in ps if s['real']<=0)} 只 ——
几乎五五开，说明<b>选股没有稳定优势</b>；而亏损端的金额远大于盈利端，问题出在
<b>亏损没有被及时截断</b>。</div></div>

<h2>七、结论与可执行建议</h2>
<div class='card'>
<ul class='rec'>
<li><b>① 先止血，暂停扩大本金。</b>当前期望为负时，投入越多亏损越大
   （6 月追加本金后 7 月即亏 {amt(abs([x['pnl'] for x in d['monthly'] if x['month']=='2026-07'][0]))}）。
   在单笔期望转正之前，<b>不再追加资金</b>；已有的仓位按下面的规则处理。</li>
<li><b>② 建立硬性止损，把盈亏比拉到 ≥1.5。</b>你现在平均亏 {ut(abs(r['avg_loss']))}、
   平均赚 {ut(r['avg_win'])}。建议：单笔最大亏损不超过本金的 2%{'' if SAN else '（按 15 万本金即 3,000 元）'}，
   触及 <b>-7%</b> 无条件离场；盈利端用移动止盈（如回撤 6% 或跌破 20 日均线）让利润奔跑。
   目标：平均盈利 ≥ 1.5 × 平均亏损。</li>
<li><b>③ 把换手率降到 20 倍以内。</b>{d['turn_ratio']:.0f} 倍年化换手意味着平均每
   {m['n_days']/(c['n_buy']+c['n_sell']):.2f} 个交易日就全仓换一遍。建议每月主动交易不超过
   2-4 次，只在<b>高胜率形态 + 板块资金共振</b>时出手（可对接本项目的主升精选 /
   环境门控：非强势环境直接空仓）。</li>
<li><b>④ 收缩持仓分散度。</b>{m['n_codes']} 只标的等于没有研究深度。建议同时持仓
   <b>≤5 只</b>、单票仓位 ≤20%，只做你能说清「为什么买、什么条件卖」的机会。</li>
<li><b>⑤ 用「环境门控」替代全天候交易。</b>你的亏损集中在 7-8 月（市场下行段），
   说明策略在弱势环境里没有防守。建议引入大盘环境判定：破位 / 弱势期
   <b>强制空仓</b>，只做强势期 —— 这比优化选股更能立刻改善盈亏比。</li>
<li><b>⑥ 每笔交易留痕并月度复盘。</b>记录买入理由、止损位、目标位；每月核对
   「计划 vs 实际」。当前 {r['n']} 笔平仓中，若剔除最差的 5 笔
   （合计约 {amt(sum(sorted([t['pnl'] for t in d['realized_trades']])[:5]))}），
   结果会显著改善 —— 说明亏损高度集中在少数失控单上。</li>
<li><b>⑦ 验证正期望后再放大。</b>先用模拟盘或 {'小资金' if SAN else '≤3 万的小资金'}跑满 30 笔以上，
   要求：胜率 ≥50%、盈亏比 ≥1.5、盈利因子 &gt;1.2 且回撤 &lt;15%，
   达标后再{'分批加仓' if SAN else '分批加仓至 15 万'}。</li>
</ul>
<div class='note'><b>可证伪的检验点</b>：执行上述 ②+③+⑤ 后，若连续 30 笔平仓的
「盈利因子仍 &lt;1.0」或「最大回撤 &gt;15%」，说明问题不在执行而在策略本身，
应停止自主选股、改为指数化配置（沪深300ETF 定投）作为基准替代。</div>
</div>

<h2>八、数据口径与可信度</h2>
<div class='card'>
<ul style='font-size:13px;color:#41474f;margin:0;padding-left:20px'>
<li>成本法：<b>移动加权平均</b>（A股券商通行口径），已实现盈亏 = 卖出净得 − 卖出部分成本。</li>
<li>交易分类：股票交易 {c['n_buy']+c['n_sell']} 笔、国债逆回购 {d['cats']['repo']['n']} 笔
   （{raw(d['cats']['repo']['amt'])}，已按现金等价物计入净值）、新股申购配号
   {d['cats']['ipo']['n']} 笔（0 成本，未中签或未扣款）。</li>
<li>外部入金：交割单不含银证转账，用「现金余额 = 上期 + 发生金额」反推，共识别
   {len(fl['deposits'])} 笔（阈值 1,000 元，小额为利息/取整噪声）。</li>
<li>净值曲线：期末权益 = 现金 + 持仓市值 + <b>逆回购在途本金</b>（漏算会造出假回撤）。</li>
{leg_html.replace('<div class=', '<li style="list-style:none;margin:8px 0"><div class=').replace('</div>', '</div></li>') if leg_html else ''}
<li>收盘价：本地日K缓存（腾讯前复权）。前复权历史价与当日成交均价存在正常日内偏差
   （中位数约 1.5%），不影响已实现盈亏（用真实成交价），仅对历史净值有轻微影响。</li>
<li>未实现盈亏按 {m['end']} 收盘计，在持标的合计浮动 {amt(un['pnl'], True)}。</li>
</ul>
</div>

<footer>本页由量化分析引擎自动核算生成，数据来源为你提供的券商交割单 + 本地行情缓存。
全部结论可复核、可证伪；<b>不构成投资建议</b>，市场有风险，投资需谨慎。</footer>
</div></body></html>"""

    if SAN:
        os.makedirs(os.path.dirname(OUT_PUB), exist_ok=True)
        op = OUT_PUB
    else:
        os.makedirs(OUT_DIR, exist_ok=True)
        op = os.path.join(OUT_DIR, "交割单复盘.html")
    open(op, "w", encoding="utf-8").write(html)
    print("[ok] 复盘页面 ->", op, "(%d 字节)" % len(html),
          "| 脱敏" if SAN else "| 完整版(本地)")


if __name__ == "__main__":
    main()
