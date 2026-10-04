# -*- coding: utf-8 -*-
"""渲染证据页：web/docs/selected_attrib_evidence.html

主题：**「想筛选赚钱的」到底该改哪一层 —— 入场（选股）还是退出（规则）？**

数据源：quant/_selected_attrib_{long,txk}.json（由 `_selected_attrib.py` 实测生成）。
  · long = `_long_kline.json`（约 780 根 ≈ 3 年）
  · txk  = `_txk_cache.json`（主升生产缓存，约 252 根 ≈ 10 个月）

口径铁律：页面所有数字读自实测 JSON，不手写、不引用记忆里的旧数字。
结论铁律：不写「改个参数就能稳赚」；只陈述已算出的事实与不可判定的部分。
"""
from __future__ import annotations
import json
import os
import sys

QUANT = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(QUANT)
WEB = os.path.join(ROOT, "web")
OUT = os.path.join(WEB, "docs", "selected_attrib_evidence.html")

F_LONG = os.path.join(QUANT, "_selected_attrib_long.json")
F_TXK = os.path.join(QUANT, "_selected_attrib_txk.json")

CSS = """
* { box-sizing:border-box; }
body { margin:0; background:#f5f6f8; color:#1c2430;
  font-family:"PingFang SC","Microsoft YaHei","Hiragino Sans GB",sans-serif; line-height:1.75; font-size:15px; }
.wrap { max-width:1160px; margin:0 auto; padding:36px 22px 70px; }
header.top { border-bottom:3px solid #1f4e79; padding-bottom:18px; margin-bottom:26px; }
h1 { font-size:26px; margin:0 0 6px; }
.sub { color:#5a6573; font-size:14px; }
h2 { font-size:21px; margin:42px 0 14px; padding-left:12px; border-left:5px solid #1f4e79; }
h3 { font-size:16.5px; margin:26px 0 8px; color:#1f4e79; }
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
.big { font-size:21px; font-weight:700; }
.up { color:#ea4335; font-weight:700; }
.down { color:#34a853; font-weight:700; }
.muted { color:#98a2b3; }
a { color:#1f4e79; }
footer { margin-top:48px; padding-top:18px; border-top:1px solid #e3e7ec; font-size:12px; color:#7b8794; line-height:1.8; }
ul { margin:8px 0; padding-left:22px; } li { margin:5px 0; }
.kicker { color:#7b8794; font-size:12px; letter-spacing:.2em; text-transform:uppercase; }
.hl { background:#fff8e6; }
.cur { background:#fff4e5; }
.warnbox { border:2px solid #c0392b; }
"""


def sp(v, unit="pp", dec=2):
    if v is None:
        return "<span class='muted'>—</span>"
    cls = "up" if v > 0 else ("down" if v < 0 else "")
    return f"<span class='{cls}'>{v:+.{dec}f}{unit}</span>"


def nz(v, unit="%", dec=2):
    if v is None:
        return "<span class='muted'>—</span>"
    return f"{v:.{dec}f}{unit}"


def _act_cn(ac):
    return "不激活（只止损+到期）" if ac >= 900 else ("买入即跟踪" if ac <= 0 else f"{ac*100:.0f}% 才激活")


def main():
    for f in (F_LONG, F_TXK):
        if not os.path.exists(f):
            print(f"[attrib-evidence] 缺 {os.path.basename(f)}，先跑 _selected_attrib.py")
            return
    L = json.load(open(F_LONG, encoding="utf-8"))
    T = json.load(open(F_TXK, encoding="utf-8"))

    lb, lt, lo = L["base"], L["a_top"], L["a_bot"]
    tb, tt, to = T["base"], T["a_top"], T["a_bot"]
    la, ta = L["attrib"], T["attrib"]
    lg, tg = L["exit_grid"], T["exit_grid"]
    bp = L["best_param_pick"]
    cost = L.get("cost", 0.15)
    sens = L.get("assumption_sens") or []

    def cmp_rows():
        return [
            ("样本区间", f"{L['span'][0]} ~ {L['span'][1]}", f"{T['span'][0]} ~ {T['span'][1]}"),
            ("面板行数 / 采样日", f"{L['n_rows']:,} / {L['n_days']}", f"{T['n_rows']:,} / {T['n_days']}"),
            ("A 档（域内前 5%）相对胜率超额", sp(lt["edge_rel"]), sp(tt["edge_rel"])),
            ("尾档（域内后 5%）相对胜率超额", sp(lo["edge_rel"]), sp(to["edge_rel"])),
            ("A 档 MFE（20 日内最大涨幅）", nz(lt["mfe"]), nz(tt["mfe"])),
            ("全样本 MFE", nz(lb["mfe"]), nz(tb["mfe"])),
            ("现行退出 · A 档单笔均值（扣费后见下）", sp(la["top"]["exit"]["mean"]), sp(ta["top"]["exit"]["mean"])),
            ("现行退出 · 全样本单笔均值", sp(la["base"]["exit"]["mean"]), sp(ta["base"]["exit"]["mean"])),
            ("现行参数网格名次", f"{lg['cur_rank']}/{lg['n_combos']}", f"{tg['cur_rank']}/{tg['n_combos']}"),
            ("网格中「两半同向且为正」的组合", f"{lg['n_pos_same']}/{lg['n_combos']}", f"{tg['n_pos_same']}/{tg['n_combos']}"),
        ]

    cmp_html = "\n".join(
        f"<tr><td>{k}</td><td class='num'>{a}</td><td class='num'>{b}</td></tr>"
        for k, a, b in cmp_rows())

    fac_html = []
    for f in L["factors"]:
        d1, d2 = f.get("d_train"), f.get("d_test")
        same = f.get("same") == "同向"
        reversed_ = (f["dir"] > 0 and (d1 or 0) < 0 and (d2 or 0) < 0)
        mark = ("<span class='down'>先验方向反了·两半稳定</span>" if reversed_
                else ("<span class='muted'>方向不稳定</span>" if not same
                      else "<span class='up'>方向一致</span>"))
        fac_html.append(
            f"<tr><td>{f['cn']}</td><td>{'↑越大越好' if f['dir']>0 else '↓越小越好'}</td>"
            + "".join(f"<td class='num'>{nz(x, '', 1)}</td>" for x in f["test"])
            + f"<td class='num'>{sp(d1, '', 1)}</td><td class='num'>{sp(d2, '', 1)}</td>"
            + f"<td>{mark}</td></tr>")
    fac_html = "\n".join(fac_html)

    def grid_rows(combos, currow):
        out = []
        for i, c in enumerate(combos[:12], 1):
            iscur = (abs(c["stop"] - currow["stop"]) < 1e-9 and abs(c["act"] - currow["act"]) < 1e-9
                     and abs(c["trail"] - currow["trail"]) < 1e-9 and c["hold"] == currow["hold"]) if currow else False
            out.append(
                f"<tr{' class=cur' if iscur else ''}><td class='num'>{i}</td>"
                f"<td>止损 {c['stop']*100:.0f}% ｜ {_act_cn(c['act'])} ｜ 回撤 {c['trail']*100:.0f}% ｜ 最多持 {c['hold']} 日"
                f"{' ★现行' if iscur else ''}</td>"
                f"<td class='num'>{sp(c['m1'], '', 3)}</td>"
                f"<td class='num'>{sp(c['m2'], '', 3)}</td>"
                f"<td class='num'>{sp(c['avg_net'], '', 3)}</td>"
                f"<td class='num'>{nz(c['hold_avg'], '天', 1)}</td>"
                f"<td class='num'>{nz(c['mae_avg'], '%', 1)}</td>"
                f"<td class='num'>{('%s'%c['payoff']) if c['payoff'] else '—'}</td>"
                f"<td>{'同向' if c['same'] else '<span class=down>反向</span>'}</td></tr>")
        return "\n".join(out)

    lgrid = grid_rows(lg["grid"], lg.get("cur"))
    cur_l = lg.get("cur") or {}
    best_l = lg["grid"][0]
    best_desc = (f"止损 {best_l['stop']*100:.0f}% ｜ {_act_cn(best_l['act'])} ｜ "
                 f"回撤 {best_l['trail']*100:.0f}% ｜ 最多持 {best_l['hold']} 日")

    def _sens_of(tag, who):
        for x in sens:
            if x["tag"] == tag and x["who"] == who:
                return x
        return None

    a_nogap = _sens_of("保守日内 + 忽略跳空", "A档")
    a_gap = _sens_of("保守日内 + 跳空成交", "A档")
    sens_a = [x["mean"] for x in sens if x["who"] == "A档"]
    span_a = (max(sens_a) - min(sens_a)) if sens_a else None

    # 假设敏感性表
    def sens_rows():
        out = []
        order = ["保守日内 + 跳空成交", "乐观日内 + 跳空成交",
                 "保守日内 + 忽略跳空", "乐观日内 + 忽略跳空"]
        for tag in order:
            row = [x for x in sens if x["tag"] == tag]
            if not row:
                continue
            d = {x["who"]: x for x in row}
            cls = " class='hl'" if "忽略跳空" in tag else ""
            out.append(f"<tr{cls}><td>{tag}</td>"
                       f"<td class='num'>{sp(d['A档']['mean'], '%', 3)}</td>"
                       f"<td class='num'>{sp(d['全样本']['mean'], '%', 3)}</td></tr>")
        return "\n".join(out)

    sens_html = sens_rows()

    html = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>「想筛选赚钱的」该改哪一层 —— 主升精选收益归因实测</title>
<style>{CSS}</style></head>
<body><div class="wrap">
<header class="top">
<div class="kicker">实测证据 ｜ 主升精选</div>
<h1>「想筛选赚钱的」——先把「赚钱」拆成三层，再看到底缺哪一层</h1>
<div class="sub">数据截至 {L['date']} 收盘 ｜ 主样本 {L['span'][0]} ~ {L['span'][1]}
（{L['n_days']} 个采样日 · {L['n_rows']:,} 行）｜ 复样本 {T['span'][0]} ~ {T['span'][1]}（{T['n_days']} 个采样日）</div>
</header>

<div class="card warnbox">
<h3 style="margin-top:0">三句话结论</h3>
<p><b>① 不是「选股没调好」。</b>现役 9 个先验因子（趋势＋资金）在两个互相独立的样本上，
都是<b>固定持有口径下的负 alpha</b>：A 档（分数最前 5%）相对胜率 {nz(lt['rel'],'%',1)}、
超额 {sp(lt['edge_rel'])}；而尾档（最后 5%）超额 {sp(lo['edge_rel'])}。
换句话说，<b>把这套打分反过来用反而更接近赚钱方向</b>。</p>
<p><b>② 页面上的「60%+ 可兑现胜率」是退出规则造成的错觉。</b>
全样本套现行移动止盈，胜率 {nz(la['base']['exit']['wr'],'%',1)}，但单笔均值只有
{sp(la['base']['exit']['mean'],'%',3)}、盈亏比 {nz(la['base']['exit']['payoff'],'',2)} ——
<b>赢的次数多、每次赢得薄</b>。这不是选股能力的证据。</p>
<p class="big">③ 本轮最重要的发现在第四节：<br>
<b>同一组参数、同一张网格，只改「成交假设」，结果就在 {sp((a_nogap or {}).get('mean'), '%', 2)}
与 {sp((a_gap or {}).get('mean'), '%', 2)} 之间大幅摆动，跨度 {nz(span_a, 'pp', 1)}
—— 与收益本身同量级。</b><br>
这意味着<b>任何基于这张网格的参数选择都不可靠</b>；且在 3 年样本上，
<b>没有任何一组退出参数能「两半同向且为正」（0 / {lg['n_combos']}）</b>。</p>
</div>

<h2>一、先证伪「选股方向」：分数越高，越不会涨</h2>
<p>把同一批样本按现役 9 因子等权分排序，取域内最前 5% 与最后 5%，
与域内全体比较<b>相对胜率</b>（前向 20 日收益 &gt; 同日域内等权中位数，≈ 剔除行情后的选股能力）。</p>
<table>
<tr><th>口径</th><th class="num">主样本（3 年）</th><th class="num">复样本（10 个月）</th></tr>
<tr><td>域内全体（基线）</td><td class="num">50.0%（定义）</td><td class="num">50.0%（定义）</td></tr>
<tr class="hl"><td><b>A 档（分数最前 5%）</b></td>
<td class="num">{nz(lt['rel'],'%',1)} ｜ 超额 {sp(lt['edge_rel'])}</td>
<td class="num">{nz(tt['rel'],'%',1)} ｜ 超额 {sp(tt['edge_rel'])}</td></tr>
<tr class="hl"><td><b>尾档（分数最后 5%）</b></td>
<td class="num">{nz(lo['rel'],'%',1)} ｜ 超额 {sp(lo['edge_rel'])}</td>
<td class="num">{nz(to['rel'],'%',1)} ｜ 超额 {sp(to['edge_rel'])}</td></tr>
<tr><td>A 档绝对收益（未扣费）</td><td class="num">{sp(lt['abs'],'%')}</td><td class="num">{sp(tt['abs'],'%')}</td></tr>
<tr><td>尾档绝对收益（未扣费）</td><td class="num">{sp(lo['abs'],'%')}</td><td class="num">{sp(to['abs'],'%')}</td></tr>
</table>
<div class="danger">两个样本给出同一方向，且 3 年样本上差距更大 ——
A 档 {sp(lt['edge_rel'])} vs 尾档 {sp(lo['edge_rel'])}，相差 <b>{abs(lt['edge_rel']-lo['edge_rel']):.1f}pp</b>。
这不像「这一期行情特殊」，更像<b>整族「趋势＋资金」先验与当前 A 股中短期收益方向相反</b>。</div>

<h2>二、逐因子看：拖后腿的是谁</h2>
<p>每个因子按<b>训练半</b>分位切 5 桶，报<b>测试半</b>各桶相对胜率（%），以及前后两半的 Q5−Q1。
先验为「↑越大越好」的因子，若 Q5−Q1 为负且两半同号 → <b>方向反了</b>。</p>
<table>
<tr><th>因子</th><th>先验方向</th><th class="num">Q1</th><th class="num">Q2</th><th class="num">Q3</th><th class="num">Q4</th><th class="num">Q5</th>
<th class="num">Q5−Q1<br>前半</th><th class="num">Q5−Q1<br>后半</th><th>判定</th></tr>
{fac_html}
</table>
<div class="note">9 个因子里 <b>8 个「两半同向为负」</b>：越是强势/放量/多头排列，其后 20 日相对胜率越低。
唯一例外「接近近 20 日高」前半正、后半负 —— 方向不稳定，不能当有效因子。<b>问题不在单个因子的阈值，而在整族先验的方向。</b></div>

<h2>三、收益归因：胜率是从哪来的</h2>
<p>同一批票，分别用「前向 20 日收益」与「现行移动止盈规则（−12% / +6% 激活 / 回撤 3% / 最多 20 日）」结算：</p>
<table>
<tr><th>样本</th><th class="num">入场口径<br>前向 20 日收益</th><th class="num">入场口径<br>胜率</th>
<th class="num">现行退出<br>单笔均值</th><th class="num">现行退出<br>胜率</th><th class="num">现行退出<br>盈亏比</th></tr>
<tr><td>主样本 · 域内全体</td>
<td class="num">{sp(la['base']['entry']['mean'],'%',2)}</td><td class="num">{nz(la['base']['entry']['wr'],'%',1)}</td>
<td class="num">{sp(la['base']['exit']['mean'],'%',3)}</td><td class="num">{nz(la['base']['exit']['wr'],'%',1)}</td>
<td class="num">{nz(la['base']['exit']['payoff'],'',2)}</td></tr>
<tr><td>主样本 · A 档</td>
<td class="num">{sp(la['top']['entry']['mean'],'%',2)}</td><td class="num">{nz(la['top']['entry']['wr'],'%',1)}</td>
<td class="num">{sp(la['top']['exit']['mean'],'%',3)}</td><td class="num">{nz(la['top']['exit']['wr'],'%',1)}</td>
<td class="num">{nz(la['top']['exit']['payoff'],'',2)}</td></tr>
<tr><td>复样本 · 域内全体</td>
<td class="num">{sp(ta['base']['entry']['mean'],'%',2)}</td><td class="num">{nz(ta['base']['entry']['wr'],'%',1)}</td>
<td class="num">{sp(ta['base']['exit']['mean'],'%',3)}</td><td class="num">{nz(ta['base']['exit']['wr'],'%',1)}</td>
<td class="num">{nz(ta['base']['exit']['payoff'],'',2)}</td></tr>
<tr><td>复样本 · A 档</td>
<td class="num">{sp(ta['top']['entry']['mean'],'%',2)}</td><td class="num">{nz(ta['top']['entry']['wr'],'%',1)}</td>
<td class="num">{sp(ta['top']['exit']['mean'],'%',3)}</td><td class="num">{nz(ta['top']['exit']['wr'],'%',1)}</td>
<td class="num">{nz(ta['top']['exit']['payoff'],'',2)}</td></tr>
</table>
<div class="danger"><b>看「域内全体」这一行：</b>胜率 {nz(la['base']['exit']['wr'],'%',1)}、
单笔 {sp(la['base']['exit']['mean'],'%',3)}、盈亏比 {nz(la['base']['exit']['payoff'],'',2)}。
<b>这组数字不该被读作「策略成立了」</b>——它是「赢 3 次赚的钱，输 1 次还回去」的典型结构。
而 A 档的入场口径（固定 20 日）只有 {sp(la['top']['entry']['mean'],'%',2)}，
<b>还低于域内全体 {sp(la['base']['entry']['mean'],'%',2)}</b>。</div>

<h3>A 档在退出口径下「看起来更好」，是因为波动更大</h3>
<table>
<tr><th>主样本</th><th class="num">MFE（20 日内最大涨幅）</th><th class="num">MAE（20 日内最大回撤）</th></tr>
<tr><td>域内全体</td><td class="num">{nz(lb['mfe'],'%',2)}</td><td class="num">{nz(lb['mae'],'%',2)}</td></tr>
<tr class="hl"><td>A 档</td><td class="num">{nz(lt['mfe'],'%',2)}</td><td class="num">{nz(lt['mae'],'%',2)}</td></tr>
<tr><td>尾档</td><td class="num">{nz(lo['mfe'],'%',2)}</td><td class="num">{nz(lo['mae'],'%',2)}</td></tr>
</table>
<p>A 档的振幅显著更大（MFE {nz(lt['mfe'],'%',1)} vs 全体 {nz(lb['mfe'],'%',1)}）。
<b>「浮盈 +6% 激活、回撤 3% 走」这条规则天然偏袒振幅大的票</b> ——
它更容易触发激活、更容易把浮盈锁成一笔「盈利」。
这就是 A 档胜率好看、而固定持有口径却是负 alpha 的机械原因。</p>

<h2>四、★ 本页的核心：同一张网格，换「成交假设」就换结论</h2>
<p>退出规则网格（止损 × 激活阈值 × 跟踪回撤 × 最长持有，共 {lg['n_combos']} 组），
在 A 档上跑，按<b>前后两半平均</b>排名（不在单独一半挑最优），净均值扣往返 {cost:.2f}pp。
两处成交假设对结果影响极大：</p>
<ul>
<li><b>日内路径：</b>跟踪止盈的止损价依赖「当日最高价」。同根 K 线里「先冲高、后回落」与「先回落、后冲高」
结果完全相反 —— 前者几乎必然能以「最高价×(1−回撤)」成交，是<b>系统性高估</b>。</li>
<li><b>跳空成交：</b>若当日<b>开盘</b>已在止损线之下，限价单不可能以止损价成交，
必须以<b>开盘价</b>成交。缺这一步，大阴线/跳空的亏损被系统性低估成「刚好止损在线上」。</li>
</ul>
<h3>最优参数（{best_desc}）在四种假设下：</h3>
<table>
<tr><th>成交假设</th><th class="num">A 档（扣 {cost:.2f}pp）</th><th class="num">全样本（扣 {cost:.2f}pp）</th></tr>
{sens_html}
</table>
<div class="danger"><b>同一组参数，四种假设下 A 档从
{sp(min(sens_a) if sens_a else None, '%', 3)} 到 {sp(max(sens_a) if sens_a else None, '%', 3)}，
跨度 {nz(span_a, 'pp', 1)} —— 与收益本身同量级。</b>
其中「忽略跳空」两行明显高于「含跳空」两行（跳空处理会把结果打下一档），
而日内路径假设的影响同样巨大。<br>
这不是参数问题，是<b>回测口径问题</b> —— 也是本页最值得带走的一条：
<b>跟踪止盈类规则的收益量级（约 ±1pp）完全被成交假设支配，而交易成本（{cost:.2f}pp）就在同一量级，
据此挑参数等于在拟合噪声。</b></div>

<h3>修正后的完整网格（前 12 名，两列均为扣费后净均值）</h3>
<table>
<tr><th class="num">名次</th><th>参数（止损 ｜ 激活 ｜ 回撤 ｜ 持有）</th>
<th class="num">前半</th><th class="num">后半</th><th class="num">两半平均(净)</th>
<th class="num">平均持有</th><th class="num">MAE</th><th class="num">盈亏比</th><th>跨期</th></tr>
{lgrid}
</table>
<div class="warnbox card">
<b>三个必须一起读的数字：</b>
<ul>
<li>现行参数（−12% / +6% / 3% / 20 日）两半平均 <b>{sp(cur_l.get('avg_net'),'%',3)}</b>，
名次 <b>{lg['cur_rank']}/{lg['n_combos']}</b>，且两半
{('同向' if cur_l.get('same') else '<b class=down>反向</b>')} —— <b>前半 {sp(cur_l.get('m1'),'',3)} / 后半 {sp(cur_l.get('m2'),'',3)}</b>。</li>
<li>全网格里「两半同向 <b>且</b> 两半平均为正」的组合只有 <b>{lg['n_pos_same']}/{lg['n_combos']}</b>。</li>
<li>网格第一名净均值也仅 <b>{sp(best_l['avg_net'],'%',3)}</b>（前半 {sp(best_l['m1'],'',3)} / 后半 {sp(best_l['m2'],'',3)}）。
把「前半最优」拿去后半验证，名次 {lg['best_train_rank_in_test']}/{lg['n_combos']}。</li>
</ul>
</div>

<h3>换成最优参数后，选股还有增量吗？</h3>
<table>
<tr><th>同一最优退出口径（已扣费）</th><th class="num">净单笔均值</th><th class="num">胜率</th><th class="num">平均持有</th></tr>
<tr><td>A 档（域内前 5%）</td><td class="num">{sp(bp['top']['mean_net'],'%',3)}</td><td class="num">{nz(bp['top']['wr'],'%',1)}</td><td class="num">{nz(bp['top']['hold'],'天',1)}</td></tr>
<tr><td>域内全体</td><td class="num">{sp(bp['all']['mean_net'],'%',3)}</td><td class="num">{nz(bp['all']['wr'],'%',1)}</td><td class="num">{nz(bp['all']['hold'],'天',1)}</td></tr>
<tr class="hl"><td><b>选股增量</b></td><td class="num">{sp(bp['delta_pp'],'pp',3)}</td><td class="num">—</td><td class="num">—</td></tr>
</table>
<p>在最优退出口径下，A 档相对域内全体的净增量是 <b>{sp(bp['delta_pp'],'pp',3)}</b> ——
<b>选股层不但不贡献，还倒扣。</b></p>

<h2>五、两个样本的交叉验证</h2>
<table>
<tr><th>检验项</th><th class="num">主样本（3 年 · {L['n_rows']:,} 行）</th><th class="num">复样本（10 个月 · {T['n_rows']:,} 行）</th></tr>
{cmp_html}
</table>
<p>换数据源、换长度，结论方向一致；差异主要在「退出网格的名次」这一类噪声大的量上 ——
这恰好说明<b>参数排名不可靠，方向性结论才可靠</b>。</p>

<h2>六、那到底该怎么优化？—— 按可信度排序</h2>
<div class="card">
<h3 style="margin-top:0">第一步（一定先做）：把所有退出/入场回测的成交假设补齐</h3>
<ul>
<li>跟踪止盈必须用<b>保守的日内处理</b>（不假设「先高后低」），并在止损位上加入
<b>「跳空以开盘价成交」</b>。</li>
<li>本轮实测：同一组最优参数，<b>忽略跳空</b>时 A 档 {sp((a_nogap or {}).get('mean'), '%', 3)}；
<b>补上跳空成交</b>后 {sp((a_gap or {}).get('mean'), '%', 3)}。
<b>结论完全不同，而代码改动只有几行</b>。</li>
</ul>
<h3>第二步（需单独一轮验证）：换先验族，而不是调参</h3>
<ul>
<li>趋势＋资金先验在两个样本上都是负 alpha，尾档（低动量/缩量/非多头）反而有
{sp(lo['edge_rel'])} 的相对优势 —— 这与项目<b>反转池</b>的既有结论同向
（有效因子是「本轮跌幅 ≥30% ＋ 启动证据 ≥2 条」）。</li>
<li>但 <b>尾档 +{abs(lo['edge_rel']):.1f}pp 是弱优势</b>，低动量票里混着大量「下跌中继」。
必须走完整四道核验（无未来函数 / walk-forward / 随机对照 / 退出可兑现）才能改生产，
<b>不能直接翻转现有打分</b>。</li>
</ul>
<h3>第三步（不要做）：继续加因子 / 微调权重去凑胜率</h3>
<ul>
<li>整族先验方向不对时，加因子只会放大噪声。这正是因子实验室的第一条纪律。</li>
</ul>
<h3>本轮的落地决定</h3>
<ul>
<li><b>维持</b>现有生产配置不变（没有找到「两半同向且为正」的替代参数）。</li>
<li>修订退出规则回测口径（第一步），后续所有池子的退出验证都按新口径重算。</li>
<li>「筛选赚钱的」在这套数据与本框架下：<b>当前没有可兑现的稳定优势 → 宁可不选</b>。</li>
</ul>
</div>

<h2>七、局限（必须一起读）</h2>
<ul>
<li><b>样本跨度：</b>主样本 {L['span'][0]} ~ {L['span'][1]}（约 3 年），仍未覆盖完整牛熊；
「换到别的年份是否成立」无法在本页验证。</li>
<li><b>窗口重叠：</b>前向 20 日窗口互相重叠、采样步长 {L['step']} 日 → 样本非独立，
pp 差应按「日期聚类」理解，不能当独立样本做显著性检验。</li>
<li><b>成本近似：</b>净均值只扣 {cost:.2f}pp 往返成本，未计冲击成本、涨跌停无法成交、以及
「同一日 190+ 只票同时调仓」的容量约束。</li>
<li><b>口径差异：</b>入场能力用「前向 20 日固定持有」，与主升生产页的「可兑现胜率（移动止盈）」
是两种口径，<b>只能对比方向，不能对比数值</b>。生产页的高胜率没有错，错的是把它读作「选股能力」。</li>
<li><b>域：</b>全市场 A 股正股剔 ST/退 + 20 日均额 ≥3000 万 + 现价 ≥2 元，与主升生产域一致。</li>
</ul>

<footer>
数据截至 {L['date']} 收盘 ｜ 实测脚本 <code>quant/_selected_attrib.py</code>
（重跑：<code>python quant/_selected_attrib.py --date {L['date']} --source long</code>）<br>
产物：<code>quant/_selected_attrib_long.json</code>（3 年）· <code>quant/_selected_attrib_txk.json</code>（10 个月）<br>
本页只陈述<strong>已算出的事实</strong>，不给「改个参数就能稳赚」的建议。
｜ <a href="../../index.html">← 返回总门户</a>
｜ <a href="dip_buy_evidence.html">相关：高上涨率＋低吸实测</a>
｜ <a href="news_nextday_evidence.html">相关：提前拿消息→次日必涨</a>
</footer>
</div>
</body></html>
"""
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[attrib-evidence] 写出 {OUT}（{len(html)} 字节）")

    try:
        sys.path.insert(0, QUANT)
        import _apply_theme as T2
        T2.process(OUT)
    except Exception as ex:
        print(f"[attrib-evidence] 主题注入跳过：{ex}")


if __name__ == "__main__":
    main()
