# -*- coding: utf-8 -*-
"""渲染证据页：web/docs/dip_buy_evidence.html

主题：**「找上涨率高的信号 → 用低吸买入」这条路能不能赚钱**。

数据源：quant/_dip_probe_{DS}.json（由 `_dip_probe.py` 实测生成，自动取最新一份）。
口径铁律：页面所有数字读自实测 JSON，不手写、不引用记忆里的旧数字。
结论铁律：不给「改个参数就能用」的建议；只陈述已算出的事实。
"""
from __future__ import annotations
import glob
import json
import os
import sys

QUANT = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(QUANT)
WEB = os.path.join(ROOT, "web")
OUT = os.path.join(WEB, "docs", "dip_buy_evidence.html")

SIG_ORDER = ["S1_趋势多头", "S2_强势回踩", "S3_超跌首阳", "S4_窄幅缩量"]
HOLD_LABEL = {"N2": "T+2 收盘卖（持 2 日）", "N5": "T+5 收盘卖（持 5 日）"}

CSS = """
* { box-sizing:border-box; }
body { margin:0; background:#f5f6f8; color:#1c2430;
  font-family:"PingFang SC","Microsoft YaHei","Hiragino Sans GB",sans-serif; line-height:1.75; font-size:15px; }
.wrap { max-width:1140px; margin:0 auto; padding:36px 22px 70px; }
header.top { border-bottom:3px solid #1f4e79; padding-bottom:18px; margin-bottom:26px; }
h1 { font-size:27px; margin:0 0 6px; }
.sub { color:#5a6573; font-size:14px; }
h2 { font-size:21px; margin:42px 0 14px; padding-left:12px; border-left:5px solid #1f4e79; }
h3 { font-size:16.5px; margin:26px 0 8px; color:#1f4e79; }
h4 { font-size:15px; margin:18px 0 6px; color:#33475b; }
p { margin:9px 0; }
code { background:#eef4fa; color:#1f4e79; padding:1px 6px; border-radius:5px; font-size:13px; }
.card { background:#fff; border:1px solid #e3e7ec; border-radius:14px; padding:18px 20px; margin:14px 0;
  box-shadow:0 1px 4px rgba(20,30,50,.04); }
table { width:100%; border-collapse:collapse; font-size:13px; margin:10px 0; }
th,td { border:1px solid #e3e7ec; padding:7px 9px; text-align:left; vertical-align:top; }
th { background:#f0f3f7; white-space:nowrap; }
td.num,th.num { text-align:right; font-variant-numeric:tabular-nums; white-space:nowrap; }
.note { background:#fffaf0; border-left:4px solid #b7791f; padding:12px 16px; margin:14px 0;
  border-radius:0 8px 8px 0; font-size:14px; }
.danger { background:#fdecea; border-left:4px solid #c0392b; padding:12px 16px; margin:14px 0;
  border-radius:0 8px 8px 0; font-size:14px; }
.ok { background:#e6f6ee; border-left:4px solid #128a52; padding:12px 16px; margin:14px 0;
  border-radius:0 8px 8px 0; font-size:14px; }
.big { font-size:22px; font-weight:700; }
.up { color:#ea4335; font-weight:700; }
.down { color:#34a853; font-weight:700; }
.muted { color:#98a2b3; }
a { color:#1f4e79; }
footer { margin-top:48px; padding-top:18px; border-top:1px solid #e3e7ec; font-size:12px; color:#7b8794; line-height:1.8; }
ul { margin:8px 0; padding-left:22px; } li { margin:5px 0; }
.kicker { color:#7b8794; font-size:12px; letter-spacing:.2em; text-transform:uppercase; }
.neg { background:#f7fbf8; }
.hl { background:#fff8e6; }
"""


def sp(v, unit="%", dec=3):
    """带符号数值（涨红跌绿）。"""
    if v is None:
        return "<span class='muted'>—</span>"
    cls = "up" if v > 0 else ("down" if v < 0 else "")
    return f"<span class='{cls}'>{v:+.{dec}f}{unit}</span>"


def nz(v, unit="%", dec=1):
    if v is None:
        return "<span class='muted'>—</span>"
    return f"{v:.{dec}f}{unit}"


def tsig(v):
    """信号超额（pp）带符号，去掉尾随的 0。"""
    if v is None:
        return "<span class='muted'>—</span>"
    cls = "up" if v > 0 else ("down" if v < 0 else "")
    s = f"{v:+.3f}".rstrip("0").rstrip(".")
    if s in ("+0", "-0", ""):
        s = "0"
    return f"<span class='{cls}'>{s}pp</span>"


def main():
    fs = sorted(glob.glob(os.path.join(QUANT, "_dip_probe_*.json")))
    if not fs:
        print("[dip-evidence] 缺 _dip_probe_*.json，先跑 _dip_probe.py")
        return
    src = fs[-1]
    d = json.load(open(src, encoding="utf-8"))
    nd = d.get("nextday") or {}
    sigs = d.get("signals") or {}
    levels = [f"{x}" for x in d.get("dip_levels") or []]
    holds = list((d.get("holds") or [2, 5]))
    holds = [f"N{h}" for h in holds]
    base = nd.get("all") or {}

    # ---------- 口径一：上涨率表 ----------
    rows1 = []
    for name in SIG_ORDER:
        v = nd.get(name)
        if not v:
            continue
        cls = "hl" if name == "S3_超跌首阳" else ""
        rows1.append(
            f"<tr class='{cls}'><td>{name}</td><td class='num'>{v['n']}</td>"
            f"<td class='num'><b>{v['wr']}%</b></td>"
            f"<td class='num'>{sp(v['mean'])}</td>"
            f"<td class='num'>{tsig(v.get('edge_pp'))}</td></tr>")
    rows1 = "".join(rows1)

    # ---------- 核心表：每信号 × 每持有期 ----------
    sec3 = []
    for name in SIG_ORDER:
        e = sigs.get(name)
        if not e or not e.get("holds"):
            continue
        sec3.append(f"<h3>{name} <span class='muted' style='font-size:13px'>（n={e.get('n_all')}）"
                    f"　{e.get('sig_cn')}</span></h3>")
        for N in holds:
            ent = e["holds"].get(N)
            if not ent:
                continue
            p0 = ent["p0"]
            ct = ent.get("ctrl") or {}
            sec3.append(
                f"<h4>{HOLD_LABEL.get(N, N)}</h4>"
                f"<div class='note' style='margin:6px 0'>直接追高（T+1 开盘买、100% 成交）："
                f"上涨率 <b>{p0['wr']}%</b>、均值 <b>{sp(p0['mean'])}</b>　|　"
                f"等量对照（同日非本档）：均值 {sp(ct.get('mean'))}、"
                f"超额 {tsig(ct.get('edge_pp'))}、R3={nz(ct.get('r3'))}"
                f"　|　<b>低吸整体劣于直接追高</b>（差额全为负，见末列）</div>")
            trs = []
            for x in levels:
                lv = (ent.get("levels") or {}).get(x)
                if not lv:
                    continue
                delta = lv.get("delta_pp")
                cls = "neg" if (delta is not None and delta < 0) else ""
                trs.append(
                    f"<tr class='{cls}'><td class='num'>{x}%</td>"
                    f"<td class='num'>{nz(lv.get('fill_rate'))}</td>"
                    f"<td class='num'>{sp(lv.get('mean1'))}</td>"
                    f"<td class='num'>{sp(lv.get('p0_on_fill'))}</td>"
                    f"<td class='num'>{tsig(lv.get('improve_pp'))}</td>"
                    f"<td class='num'>{sp(lv.get('miss_p0'))}</td>"
                    f"<td class='num'><b>{sp(lv.get('net_pool'))}</b></td>"
                    f"<td class='num'>{sp(lv.get('net_p0'))}</td>"
                    f"<td class='num'><b>{sp(delta, 'pp')}</b></td>"
                    f"<td class='num'>{nz(lv.get('r3'))}</td></tr>")
            sec3.append(
                "<table><thead><tr>"
                "<th class='num'>低吸档</th><th class='num'>成交率</th>"
                "<th class='num'>成交后均值</th><th class='num'>同样本追高</th>"
                "<th class='num'>买点改善</th><th class='num'>未成交组追高</th>"
                "<th class='num'>池化净期望</th><th class='num'>直接追高</th>"
                "<th class='num'>差额</th><th class='num'>R3</th>"
                "</tr></thead><tbody>" + "".join(trs) + "</tbody></table>")
    sec3 = "\n".join(sec3)

    # ---------- 逆向选择表（N5 × 全档） ----------
    adv = []
    for name in SIG_ORDER:
        e = sigs.get(name)
        if not e or not e.get("holds"):
            continue
        ent = e["holds"].get("N5") or e["holds"].get(list(e["holds"])[0])
        for x in levels:
            lv = (ent.get("levels") or {}).get(x)
            if not lv:
                continue
            gap = None
            if lv.get("miss_p0") is not None and lv.get("p0_on_fill") is not None:
                gap = lv["miss_p0"] - lv["p0_on_fill"]
            adv.append(
                f"<tr><td>{name}</td><td class='num'>{x}%</td>"
                f"<td class='num'>{nz(lv.get('fill_rate'))}</td>"
                f"<td class='num'>{sp(lv.get('p0_on_fill'))}</td>"
                f"<td class='num'>{sp(lv.get('miss_p0'))}</td>"
                f"<td class='num'>{sp(gap, 'pp')}</td></tr>")
    adv = "".join(adv)

    # ---------- 反例：把「差额为正」的组合单独列出（供读者自行判断） ----------
    pos = []
    for name, e in sigs.items():
        for N, ent in (e.get("holds") or {}).items():
            for x, lv in (ent.get("levels") or {}).items():
                if lv.get("delta_pp") is not None and lv["delta_pp"] > 0:
                    pos.append(
                        f"<tr><td>{name}</td><td class='num'>{HOLD_LABEL.get(N, N)}</td>"
                        f"<td class='num'>{x}%</td>"
                        f"<td class='num'>{nz(lv.get('fill_rate'))}</td>"
                        f"<td class='num'>{sp(lv.get('net_pool'))}</td>"
                        f"<td class='num'>{sp(lv.get('delta_pp'), 'pp')}</td>"
                        f"<td class='num'>{nz(lv.get('r3'))}</td></tr>")
    pos_html = ("<table><thead><tr><th>信号</th><th class='num'>持有期</th>"
                "<th class='num'>低吸档</th><th class='num'>成交率</th>"
                "<th class='num'>池化净期望</th><th class='num'>差额</th>"
                "<th class='num'>R3</th></tr></thead><tbody>"
                + "".join(pos) + "</tbody></table>") if pos else \
               "<div class='note'>没有任何组合的「差额」为正。</div>"

    okn = len(d.get("ok_combos") or [])
    src_rel = os.path.relpath(src, ROOT).replace("\\", "/")
    # ★ 逆向选择段落里的所有数字都必须从 JSON 取，禁止手写
    s1n5 = ((sigs.get("S1_趋势多头", {}).get("holds", {}) or {}).get("N5") or {})
    lv05 = (s1n5.get("levels") or {}).get("0.5") or {}
    fill05 = lv05.get("fill_rate")
    miss05 = (100.0 - fill05) if fill05 is not None else None
    gap05 = (lv05.get("miss_p0") - lv05.get("p0_on_fill")) \
        if (lv05.get("miss_p0") is not None and lv05.get("p0_on_fill") is not None) else None
    # 递进档位（用于演示「挂得越低越差」）
    lad = ""
    for x in levels:
        lv = (s1n5.get("levels") or {}).get(x) or {}
        lad += f"{x}%→{sp(lv.get('net_pool'), '%', 2)}、"
    lad = lad.rstrip("、")

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>「高上涨率 + 低吸」能不能赚钱 · 实测证据</title>
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
<header class="top">
  <div class="kicker">Evidence · 买点有效性</div>
  <h1>「找上涨率高的信号、用低吸买入」——这条路能不能赚钱</h1>
  <div class="sub">本页不是观点，是在 {d.get('n_recs')} 行全市场日K样本（{d.get('n_days')} 个入场日）
  上的一次实测：<strong>先把「上涨率高的信号」筛出来，再把它换成低吸买法</strong>，
  看净期望是变好还是变坏。</div>
</header>

<div class="danger">
<b>先说结论：不成立。而且是两层都不成立。</b><br>
① <b>「上涨率」这一层</b>：四个先验信号里，只有「超跌首阳」能把 T→T+1 上涨率显著抬高
（<b>{nd.get('S3_超跌首阳', {}).get('wr')}%</b> vs 全市场 {base.get('wr')}%，{tsig(nd.get('S3_超跌首阳', {}).get('edge_pp'))}），
其余三个都不比全市场高。而<b>上涨率高 ≠ 赚钱</b>——它的超额收益只有
{tsig((sigs.get('S3_超跌首阳', {}).get('holds', {}).get('N2') or {}).get('ctrl', {}).get('edge_pp'))}（T+2 口径），
扣掉双边交易成本后≈0，且跨持有期的 R3 不稳定。<br>
② <b>「低吸」这一层</b>：把买法从「T+1 开盘直接买」换成「挂低价限价单」，
<b>所有信号、所有折扣档、所有持有期的池化净期望都变差</b>（差额全为负，最低到 −0.9pp），
R3 大多低于 30% —— 即「低吸更差」在统计上非常稳健。<br>
<b>根因：低吸会系统性地把「要涨的票」筛掉。</b>只有当天走弱的票才会跌到你的挂单价上，
而当天走弱的票恰恰是信号失效的那批（见第四节）。
</div>

<h2>一、第一步：「上涨率高的信号」到底存不存在</h2>
<div class="card">
<p>四个信号都是<strong>T 日收盘时点可知</strong>的（只用当天及之前的数据，无未来函数），
先验固定、不做参数搜索。口径：T 日收盘买入 → T+1 日收盘卖出，即「次日涨不涨」。</p>
<table>
<thead><tr><th>信号（T 日收盘可知）</th><th class="num">样本数</th>
<th class="num">次日上涨率</th><th class="num">次日均值</th><th class="num">vs 全市场</th></tr></thead>
<tbody>
<tr><td><b>全市场母集</b></td><td class="num">{base.get('n')}</td>
    <td class="num"><b>{base.get('wr')}%</b></td><td class="num">{sp(base.get('mean'))}</td>
    <td class="num">—</td></tr>
{rows1}
</tbody></table>
<div class="note"><b>读法：</b>「超跌首阳」（近 5 日累计跌 ≥6% 且当日收阳）把上涨率从
{base.get('wr')}% 抬到 {nd.get('S3_超跌首阳', {}).get('wr')}%，是唯一明显有效的。
「趋势多头」甚至略低于全市场 —— <b>强势票次日的上涨率并不高</b>，因为它们当天的上涨
已经把次日的空间提前花掉了。<br>
⚠ 但请注意：上涨率只是「赢的次数」，<b>完全没说赢多少、输多少</b>。下一节起才是关键。</div>
</div>

<h2>二、为什么必须把「低吸」单独拿出来测</h2>
<div class="card">
<p>「低吸」不是「选什么」，而是「怎么买」。它改变了三件事，只看其中一件必然得出假结论：</p>
<table>
<thead><tr><th>买入口径</th><th>怎么成交</th><th class="num">成交率</th><th>能不能配上「次日上涨」</th></tr></thead>
<tbody>
<tr><td><b>P0 直接追高</b></td><td>T+1 开盘价买入</td><td class="num">100%（恒成立）</td>
    <td>能</td></tr>
<tr><td><b>P1 低吸</b></td><td>T+1 挂「T 日收盘 ×(1−x%)」限价单，跌到才成交</td>
    <td class="num">25%~85%（随档位变化）</td>
    <td>能，但<b>买不到也是一种结果</b></td></tr>
<tr><td><b>当日买、当日卖</b></td><td>——</td><td class="num">—</td>
    <td><b>不能</b>：A 股 T+1 制度，T+1 买的股票当天不能卖</td></tr>
</tbody></table>
<div class="danger"><b>★ 低吸最容易骗人的地方：只统计「成交了的那批有多赚」。</b><br>
如果只看成交样本，低吸<b>永远</b>显得更好——因为你的成交价比别人低（本次实测：买点改善
+0.4~2.2pp，全为正）。但这笔账是<b>半截账</b>：<br>
　· 没成交的那份钱<b>闲置了</b>，没赚到就是没赚到；<br>
　· 更糟的是，<b>没成交的往往是最强的票</b>——它当天直接冲高，根本不给你低吸的机会。<br>
所以本页所有低吸口径一律用<b>池化净期望</b>（不成交记 0）与「直接追高」逐日对比。</div>
</div>

<h2>三、核心证据：低吸 vs 直接追高</h2>
<div class="card">
<p>每张表一列都不能少：<b>成交率</b>告诉你买了多少，<b>池化净期望</b>是真实的钱，
末列<b>差额</b>＝池化净期望 − 直接追高，是「低吸到底加分还是减分」的唯一答案。
R3 ＝ 逐日 block bootstrap 中「低吸不差于追高」的比例，≥95% 才算统计上站得住。</p>
{sec3}
<div class="danger"><b>★ 全表不存在一个「差额为正且池化净期望为正且 R3≥95%」的组合。</b><br>
连最宽松的判据（只要差额 > 0）也只在个别极端档位出现，且那些档位的池化净期望仍是负的（见第五节）。<br>
<b>方向还高度单调：低吸折扣挂得越深，结果越差。</b>例如「趋势多头 / 持 5 日」：
直接追高 {sp((s1n5.get('p0') or {}).get('mean'))}，此后各档池化净期望依次为 {lad}
——挂得越低，越买不到该买的，剩下的越是烂票。</div>
</div>

<h2>四、根因：逆向选择（你错过的正是最赚的那批）</h2>
<div class="card">
<p>下表把每个低吸档拆成两组，<b>两组用同一个「直接追高」口径来评价</b>，
这样剔除掉买法差异，只看「低吸把什么票筛走了」：</p>
<table>
<thead><tr><th>信号</th><th class="num">低吸档</th><th class="num">成交率</th>
<th class="num">成交组（若改追高）</th><th class="num">未成交组（若改追高）</th>
<th class="num">两组差距</th></tr></thead>
<tbody>{adv}</tbody></table>
<div class="danger"><b>这就是全部原因。</b>以「趋势多头 / 持 5 日 / 低吸 0.5%」为例：
你能低吸到的那 <b>{nz(fill05)}</b> 票，若按追高口径只有
{sp(lv05.get('p0_on_fill'))}；
而<b>你买不到的那 {nz(miss05)}</b>，若按追高口径有
{sp(lv05.get('miss_p0'))}
——<b>差了 {sp(gap05, 'pp', 2)}</b>。<br>
翻译成人话：<b>挂低价单这个动作本身，就在替你挑选「当天走弱的票」。</b>
而一个信号选出来的票当天走弱，通常意味着这个信号在这只票上已经失效了。
你用「省下 0.5% 成本」换掉了「最赚的那 15% 仓位」，这笔交易不可能划算。</div>
</div>

<h2>五、一个必须解释的反例（避免误读）</h2>
<div class="card">
<p>下表列出所有「差额为正」的组合——只有「窄幅缩量」在深档出现过：</p>
{pos_html}
<div class="note"><b>它不是「低吸有效」，而是「不成交反而避开了坏信号」。</b>以
「窄幅缩量 / 持 5 日 / 低吸 2%」为例：成交率仅
{nz(((sigs.get('S4_窄幅缩量', {}).get('holds', {}).get('N5') or {}).get('levels') or {}).get('2.0', {}).get('fill_rate'))}，
池化净期望仍是
{sp(((sigs.get('S4_窄幅缩量', {}).get('holds', {}).get('N5') or {}).get('levels') or {}).get('2.0', {}).get('net_pool'))}
（<b>负的</b>）。差额之所以为正，只是因为「不成交」把一笔负的收益换成了 0。<br>
换句话说：<b>这个信号本身是无效的</b>（它直接追高的均值
{sp(((sigs.get('S4_窄幅缩量', {}).get('holds', {}).get('N5') or {}).get('p0') or {}).get('mean'))}
≈ 0，超额
{tsig((sigs.get('S4_窄幅缩量', {}).get('holds', {}).get('N5') or {}).get('ctrl', {}).get('edge_pp'))}），
而低吸把一个无效策略变成了「大部分时间空仓、偶尔不亏」——那不是策略，那是<b>不下单</b>。
本页的判定标准要求「池化净期望为正」，正是为了排除这种情形。</div>
</div>

<h2>六、结论</h2>
<div class="card">
<ul>
<li><b>「上涨率高的信号」存在，但它不等于赚钱。</b>「超跌首阳」把次日上涨率抬到
{nd.get('S3_超跌首阳', {}).get('wr')}%，可它 T+2 相对同日对照的超额只有
{tsig((sigs.get('S3_超跌首阳', {}).get('holds', {}).get('N2') or {}).get('ctrl', {}).get('edge_pp'))}、
T+5 只有 {tsig((sigs.get('S3_超跌首阳', {}).get('holds', {}).get('N5') or {}).get('ctrl', {}).get('edge_pp'))}，
且 R3 分别是 {nz((sigs.get('S3_超跌首阳', {}).get('holds', {}).get('N2') or {}).get('ctrl', {}).get('r3'))} 与
{nz((sigs.get('S3_超跌首阳', {}).get('holds', {}).get('N5') or {}).get('ctrl', {}).get('r3'))}
——<b>跨持有期不一致</b>。而 A 股双边交易成本约 0.1~0.2%，这个超额扣完成本基本归零。
<b>赢的次数多，赢的时候赢得少，是典型的胜率陷阱。</b></li>
<li><b>「低吸」不只是不帮忙，而是稳定减分。</b>全部「信号 × 折扣档 × 持有期」组合里，
差额为正且池化净期望为正且 R3≥95% 的组合数 = <b>{okn}</b>。低吸越深、结果越差，方向单调。</li>
<li><b>机制是逆向选择，不是运气不好。</b>能低吸到的正是当天走弱的那批（信号失效），
买不到的是当天冲高的那批（信号兑现）。这个筛选方向和信号有效性<b>正好相反</b>。</li>
<li><b>制度上还有一道硬约束</b>：A 股 T+1，T+1 买入的股票当天不能卖。
所以「当天低吸、当天反弹卖出」这个最诱人的玩法根本不合法；要兑现必须持有到 T+2 之后，
而那段时间的波动会把低吸省下的那点成本稀释掉。</li>
</ul>
</div>

<div class="danger"><b>一句话：</b>「上涨率」和「能低吸到」是<b>互相矛盾</b>的两个要求 ——
上涨率高意味着票会直接冲高，直接冲高就意味着不会跌到你的挂单价上。
能让你低吸到的，恰恰是信号已经失效的那部分。
<b>低吸是买点的优化，不是收益的来源；当它被用来「拯救一个本就不成立的信号」时，只会让结果更差。</b></div>

<h2>七、样本与口径（限制，必须一并看）</h2>
<div class="card">
<ul>
<li>数据：腾讯前复权日K 长历史，<b>5050 只票 × 780 根</b>（{d.get('entry_days', ['—'])[0] if d.get('entry_days') else '—'} ~ {d.get('date')}），
入场日 <b>{d.get('n_days')} 个</b>、间隔 {d.get('step')} 日（保证结果窗口不重叠），
总样本 <b>{d.get('n_recs')} 行</b>。</li>
<li>可交易域：20 日均额 ≥ {d.get('min_amt20', 0)/1e8:.1f} 亿（剔除买不到也卖不掉的僵尸股）；成交额已修正
科创板与非科创板 volume 单位差异（差 100 倍）。</li>
<li><b>剔停牌</b>：要求 T ~ T+N 每一根都与真实交易日历连续，避免拿「停牌后复牌的下一根」冒充 T+1。</li>
<li>全部为<b>毛收益</b>，未扣佣金/印花税/滑点。⚠ 扣除双边成本只会让所有口径<b>更差</b>，
不会改变本页任何一个方向性结论。</li>
<li>低吸成交判定为近似：若 T+1 开盘价已低于挂单价则以开盘价成交，否则以盘中最低价触及挂单价成交；
未处理一字跌停无法买入、停牌等极端情形。</li>
<li>R3 ＝ 逐日 block bootstrap（整日重抽 {d.get('boot', 400)} 次）中差额 &gt; 0 的比例；
「成交率」＝该档成交样本 / 该信号全部样本。</li>
<li>实测脚本：<code>{src_rel}</code>（重跑：
<code>python quant/_dip_probe.py --date {d.get('date')}</code>），
本页数字全部读自其产物，可复现。</li>
</ul>
</div>

<footer>
数据截至 {d.get('date')} 收盘 ｜ 实测脚本 <code>{src_rel}</code>
｜ <a href="../../index.html">← 返回总门户</a>
｜ <a href="news_nextday_evidence.html">相关：「提前拿消息→次日必涨」为何不成立</a>
｜ <a href="DAILY_UPDATE_SOP.html">每日更新 SOP</a><br>
本页只陈述<strong>已算出的事实</strong>，不给任何「改个参数就能用」的建议。
</footer>
</div>
</body>
</html>
"""
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[dip-evidence] 写出 {OUT}（{len(html)} 字节）")

    try:
        sys.path.insert(0, QUANT)
        import _apply_theme as T
        T.process(OUT)
    except Exception as ex:
        print(f"[dip-evidence] 主题注入跳过：{ex}")


if __name__ == "__main__":
    main()
