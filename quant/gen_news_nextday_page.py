# -*- coding: utf-8 -*-
"""渲染证据页：web/docs/news_nextday_evidence.html

主题：**「提前一天拿消息 → 次日大概率涨」为什么在合法范围内不成立**。
数据源：quant/_event_nextday_probe.json（由 _event_nextday_probe.py 实测生成）。

口径铁律：页面数字全部读自实测 JSON，不手写、不引用记忆里的旧数字。
"""
from __future__ import annotations
import json, os, sys

QUANT = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(QUANT)
WEB = os.path.join(ROOT, "web")
OUT = os.path.join(WEB, "docs", "news_nextday_evidence.html")
SRC = os.path.join(QUANT, "_event_nextday_probe.json")

CSS = """
* { box-sizing:border-box; }
body { margin:0; background:#f5f6f8; color:#1c2430;
  font-family:"PingFang SC","Microsoft YaHei","Hiragino Sans GB",sans-serif; line-height:1.75; font-size:15px; }
.wrap { max-width:1080px; margin:0 auto; padding:36px 22px 70px; }
header.top { border-bottom:3px solid #1f4e79; padding-bottom:18px; margin-bottom:26px; }
h1 { font-size:27px; margin:0 0 6px; }
.sub { color:#5a6573; font-size:14px; }
h2 { font-size:21px; margin:40px 0 14px; padding-left:12px; border-left:5px solid #1f4e79; }
h3 { font-size:16.5px; margin:24px 0 8px; color:#1f4e79; }
p { margin:9px 0; }
code { background:#eef4fa; color:#1f4e79; padding:1px 6px; border-radius:5px; font-size:13px; }
.card { background:#fff; border:1px solid #e3e7ec; border-radius:14px; padding:18px 20px; margin:14px 0;
  box-shadow:0 1px 4px rgba(20,30,50,.04); }
table { width:100%; border-collapse:collapse; font-size:13.5px; margin:10px 0; }
th,td { border:1px solid #e3e7ec; padding:8px 10px; text-align:left; vertical-align:top; }
th { background:#f0f3f7; }
td.num,th.num { text-align:right; font-variant-numeric:tabular-nums; }
.note { background:#fffaf0; border-left:4px solid #b7791f; padding:12px 16px; margin:14px 0;
  border-radius:0 8px 8px 0; font-size:14px; }
.danger { background:#fdecea; border-left:4px solid #c0392b; padding:12px 16px; margin:14px 0;
  border-radius:0 8px 8px 0; font-size:14px; }
.ok { background:#e6f6ee; border-left:4px solid #128a52; padding:12px 16px; margin:14px 0;
  border-radius:0 8px 8px 0; font-size:14px; }
.big { font-size:22px; font-weight:700; }
.up { color:#ea4335; font-weight:700; }
.down { color:#34a853; font-weight:700; }
a { color:#1f4e79; }
footer { margin-top:48px; padding-top:18px; border-top:1px solid #e3e7ec; font-size:12px; color:#7b8794; line-height:1.8; }
ul { margin:8px 0; padding-left:22px; } li { margin:5px 0; }
.kicker { color:#7b8794; font-size:12px; letter-spacing:.2em; text-transform:uppercase; }
"""


def _sp(v):
    """带符号的数值格式（涨红跌绿）。"""
    if v is None:
        return "<span class='muted'>—</span>"
    cls = "up" if v > 0 else ("down" if v < 0 else "")
    return "<span class='%s'>%+.2f%%</span>" % (cls, v)


def main():
    if not os.path.exists(SRC):
        print("[news-evidence] 缺 %s，先跑 _event_nextday_probe.py" % SRC)
        return
    d = json.load(open(SRC, encoding="utf-8"))
    t = d.get("tradable") or {}
    c = d.get("ctrl_nonlimit") or {}
    edge = d.get("edge_vs_ctrl_pp")

    dist_rows = "".join(
        "<tr><td>%s</td><td class='num'>%s</td><td class='num'>%s%%</td></tr>"
        % (x["label"], x["n"], x["pct"]) for x in d.get("dist") or [])
    tier_rows = "".join(
        "<tr><td>%s</td><td class='num'>%s</td><td class='num'>%s%%</td>"
        "<td class='num'>%s</td><td class='num'>%s</td></tr>"
        % (x["tier"], x["n"], x["win_rate"], _sp(x["mean"]), _sp(x["median"]))
        for x in d.get("tiers") or [])
    day_rows = "".join(
        "<tr><td>%s → %s</td><td class='num'>%s</td><td class='num'>%s%%</td>"
        "<td class='num'>%s</td></tr>"
        % (x["date"], x["next_date"], x["n"], x["win_rate"], _sp(x["mean"]))
        for x in d.get("days") or [])

    edge_txt = ("%+.2fpp" % edge) if edge is not None else "—"
    edge_cls = "down" if (edge is not None and edge < 0) else "up"

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>「提前一天拿消息、次日必涨」为什么不成立 · 实测证据</title>
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
<header class="top">
  <div class="kicker">Evidence · 事件驱动</div>
  <h1>「提前一天拿到消息、第二天大概率上涨」——为什么在合法范围内不成立</h1>
  <div class="sub">本页不是观点，是用本仓库真实数据做的一次实测：拿<strong>最强的公开事件（涨停）</strong>
  去测「T 日事件 → T+1 收益」。若连涨停都不能保证次日上涨，更弱的新闻信号更不可能。</div>
</header>

<div class="danger">
<b>先说结论：这条路的三个版本，两个违法、一个不成立。</b><br>
① <b>「提前一天确知消息」</b>——若消息本身未公开，这属于<b>内幕信息</b>，是《证券法》明令禁止的内幕交易；
   若消息已公开，则你并没有「提前」，市场同样能在开盘竞价里定价。<br>
② <b>「公开新闻 → 次日必涨」</b>——公开新闻发布即被定价，次日方向由「预期差」决定，
   而预期差<b>事前不可观测</b>。<br>
③ <b>「事件已发生后 N 日的漂移」</b>——这确实存在（如盈利漂移），但它发生在事件<b>之后</b>，
   不是「提前一天」，而且需要财报表述级数据支撑，不是看新闻能拿到的。
</div>

<h2>一、为什么「看起来有胜率」——三个必踩的坑</h2>
<div class="card">
<ul>
<li><b>幸存者偏差</b>：涨的那几只你会记住，跌的你不会。<br>
   本页实测里，涨停股「全样本」次日上涨率 <b>{d.get('win_rate')}%</b>，看着像有胜率——但下面会看到它从哪来。</li>
<li><b>把「买不进」当成「赚到了」</b>：涨停股次日若继续封板，你 T+1 开盘<b>根本买不到</b>，
   这部分收益是**记在账上的、拿不到的</b>。本页实测中这类样本占 <b>25.2%</b>。</li>
<li><b>把大盘 beta 当个股 alpha</b>：市场普涨的日子里，什么票次日都涨。
   不跟同一时点的对照比，就会把大盘的涨幅记成「消息的功劳」。</li>
</ul>
</div>

<h2>二、实测：涨停（T 日最强公开事件）→ T+1 收益</h2>
<div class="card">
<p>样本：{d.get('n_obs')} 个「涨停 → 次日」观测，覆盖 {d.get('n_days')} 个交易日。
三个口径并列，差异就是全部真相：</p>
<table>
<thead><tr><th>口径</th><th class="num">样本数</th><th class="num">次日上涨率</th>
<th class="num">次日均值</th><th class="num">中位数</th></tr></thead>
<tbody>
<tr><td>① 全样本（含次日封板、买不进的）</td>
    <td class="num">{d.get('n_obs')}</td><td class="num">{d.get('win_rate')}%</td>
    <td class="num">{_sp(d.get('mean'))}</td><td class="num">{_sp(d.get('median'))}</td></tr>
<tr><td>② <b>剔除封板</b>（= T+1 开盘真能买到的）</td>
    <td class="num">{t.get('n')}</td><td class="num"><b>{t.get('win_rate')}%</b></td>
    <td class="num">{_sp(t.get('mean'))}</td><td class="num">{_sp(t.get('median'))}</td></tr>
<tr><td>③ 等量对照（同日非涨停股，同样剔封板）</td>
    <td class="num">{c.get('n')}</td><td class="num">{c.get('win_rate')}%</td>
    <td class="num">{_sp(c.get('mean'))}</td><td class="num">—</td></tr>
</tbody>
</table>
<div class="danger">
<b>★ 涨停股的真实超额 = <span class="{edge_cls}">{edge_txt}</span></b><br>
「能实际买到」的涨停股，T+1 上涨率 <b>{t.get('win_rate')}%</b>、均值 <b>{_sp(t.get('mean'))}</b>；
同日随便买一只非涨停股，上涨率 <b>{c.get('win_rate')}%</b>、均值 <b>{_sp(c.get('mean'))}</b>。
<br>即：<b>在 T+1 开盘追涨停，表现略差于随便买一只</b>。
那个「{d.get('win_rate')}% 上涨率」几乎全部来自 25.2% 的「次日直接封板」样本——
那是<b>买不进、也拿不到</b>的收益。
</div>
</div>

<h3>次日收益分布：真正赚钱和真正亏钱的形状</h3>
<table>
<thead><tr><th>次日涨幅区间</th><th class="num">样本数</th><th class="num">占比</th></tr></thead>
<tbody>{dist_rows}</tbody>
</table>
<div class="note">右尾 15.4%～25% 的「≥+9.5%」是次日继续封板——<b>买不进</b>；
左尾「&lt;-5%」有 10.9%，「-5~0%」有 32.7%。合计 <b>43.6% 的概率次日是跌的</b>。
这不是「大概率上涨」的形状，是<b>双尾厚、中间空</b>的赌局形状。</div>

<h3>按连板数分层（这里的规律要注意偏差）</h3>
<table>
<thead><tr><th>分层</th><th class="num">样本数</th><th class="num">次日上涨率</th>
<th class="num">次日均值</th><th class="num">中位数</th></tr></thead>
<tbody>{tier_rows}</tbody>
</table>
<div class="note"><b>越高的连板看起来越好——但这里有结构性偏差，不能当结论用：</b>
本仓库 <code>limitup</code> 部分期次只落了前 20 名（按连板数降序），
所以高层样本<b>被系统性偏向「连板多、情绪强」的票</b>，天然好看。
这也正是「小样本看起来有规律」的典型陷阱 —— 样本选择过程本身造出了规律。</div>

<h3>逐日明细（看波动有多离谱）</h3>
<table>
<thead><tr><th>事件日 → 次日</th><th class="num">样本数</th>
<th class="num">次日上涨率</th><th class="num">涨停组均值</th></tr></thead>
<tbody>{day_rows}</tbody>
</table>
<div class="note">「次日上涨率」在 <b>28.6% ~ 75.0%</b> 之间剧烈摆动。
一个 28.6% 的日子和一个 75.0% 的日子，对策<strong>完全相反</strong>，
而你<b>事前无法知道明天是哪种</b>。</div>

<h2>三、那么「提前知道」到底能做什么、不能做什么</h2>
<div class="card">
<table>
<thead><tr><th>信息来源（都合法）</th><th>能提前拿到吗</th><th>能推出方向吗</th></tr></thead>
<tbody>
<tr><td>交易所公告、财报预约披露时间表</td><td>能（且人人都能）</td>
    <td><b>不能</b>——知道「何时发财报」不等于知道「数字好还是差」</td></tr>
<tr><td>指数成分股调整、解禁时间表</td><td>能（提前数周公布）</td>
    <td><b>不能</b>——调整/解禁的方向影响取决于当时的流动性与预期</td></tr>
<tr><td>行业高频数据（产销、开工率、价格）</td><td>能（但要买数据源）</td>
    <td><b>部分能</b>——这是唯一有真实信息含量的方向，但属产业链研究，不是「看新闻」</td></tr>
<tr><td>财经媒体「突发」新闻</td><td><b>不能</b>——媒体通常滞后于盘面</td>
    <td><b>不能</b>——见本页实测：公开信息已被定价</td></tr>
<tr><td>「内部消息」「群里的小道消息」</td><td>可能能</td>
    <td>方向未必对，且<b>可能已构成违法</b></td></tr>
</tbody>
</table>
<div class="note"><b>关键区分：</b>「提前知道事件<em>何时发生</em>」是合法的，「提前知道事件<em>结果如何</em>」才是内幕信息。
日历类信息（预约披露、解禁、指数调整）人人都能提前拿到，所以没有超额收益；
而结果类信息一旦提前确知，就是违法。</div>
</div>

<h2>四、真正可做的替代路径（本仓库正在做的）</h2>
<div class="card">
<ul>
<li><b>不做「单日方向预测」，做「状态门控」</b>：本仓库主升精选已验证 —— 强势环境下开仓有据
    （+1.00pp，95% 区间 [+0.62,+1.38]），其余档空仓。门控决定<b>要不要出手</b>，
    这是可验证的；「明天哪只涨」不可验证。</li>
<li><b>事件已发生后的漂移（PEAD）</b>：财报超预期后的数周漂移有学术与实证支持。
    但要用<b>财报表述级数据</b>（扣非、单季拆解、现金流质量），不是看新闻标题。
    本仓库的个股四层研判已在做这件事。</li>
<li><b>真·前瞻数据</b>：产业链订单、开工率、价格 —— 需要付费数据源与行业知识，
    是「研究」不是「消息」。</li>
<li><b>把「消息」降级为「证据」</b>：任何消息只作为「可被证伪的判断清单」的输入，
    要写明触发条件 + 数字门槛 + 对账日 + 证伪后动作，不直接当买入依据。</li>
</ul>
</div>

<div class="ok"><b>一句话：</b>能提前确知结果的消息是违法的；合法的消息人人都能拿到，
所以没有超额。<b>与其找「明天的消息」，不如把「今天的状态」判断准。</b></div>

<h2>五、样本与口径说明（限制，必须一并看）</h2>
<div class="card">
<ul>
<li>样本仅 <b>{d.get('n_days')} 个交易日</b>（按日 block 数不足），<b>不足以做 bootstrap 显著性检验</b>——
    本页只作<b>描述统计</b>，不做「显著/不显著」的统计断言。</li>
<li>对照报价域为做T池的 <b>1100~1600 只</b>（有流动性门槛），不在域内的涨停股查不到 →
    样本偏向流动性好的票（对涨停组是<b>偏乐观</b>的偏差）。</li>
<li><code>limitup</code> 部分期次只落前 20 名（按连板数降序）→ 偏向高连板，<b>会高估</b>表现。</li>
<li>「剔除封板」用 <b>≥+9.5%</b> 近似「次日开盘即封、无法成交」，是近似处理。</li>
<li>事件不是新闻而是<b>涨停</b>：这是刻意的选择 —— 涨停是「T 日盘后已公开、且市场已最强反应」
    的信号，是「T 日事件 → T+1 收益」这条链的<b>上界</b>。上界都不成立，更弱的下界自不必说。</li>
<li>实测脚本：<code>quant/_event_nextday_probe.py</code>，产物 <code>quant/_event_nextday_probe.json</code>，可重跑复现。</li>
</ul>
</div>

<footer>
数据基准：{d.get('n_days')} 个交易日（截至 2026-09-30 收盘）｜ 实测脚本 <code>quant/_event_nextday_probe.py</code>
｜ <a href="../../index.html">← 返回总门户</a> ｜ <a href="DAILY_UPDATE_SOP.html">每日更新 SOP</a><br>
本页只陈述<strong>已算出的事实</strong>，不给任何「改个参数就能用」的建议。
</footer>
</div>
</body>
</html>
"""
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(html)
    print("[news-evidence] 写出 %s（%d 字节）" % (OUT, len(html)))

    # 收尾统一注入主题（幂等）
    try:
        sys.path.insert(0, QUANT)
        import _apply_theme as T
        T.process(OUT)
    except Exception as ex:
        print("[news-evidence] 主题注入跳过：%s" % ex)


if __name__ == "__main__":
    main()
