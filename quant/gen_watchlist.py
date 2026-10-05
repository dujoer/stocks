# -*- coding: utf-8 -*-
"""底部反转观察池 · 入口页生成器（v5）。

消费 quant/watchlist_scan_{DATE}.json（由 rev_pool.py run 落盘：全市场域 + 先验固定因子集
横截面分位），渲染：
  web/reversal/index.html               板块入口（滚动更新：v5 方法论摘要 + 最新观察池 + 归档）

注意：watchlist_{DATE}.html **由 rev_pool.py 自己渲染**（v5 模板，含买卖点）。
本脚本若检测到 scan 是 rev_pool 产出（version 以 rev_v 开头）则只出入口页、不覆盖明细页，
避免两套渲染互相打架。

用法：
  python quant/gen_watchlist.py                 # 自动取最新 watchlist_scan_*.json
  python quant/gen_watchlist.py 20260918        # 指定数据日期（compact）

约定：
  - 浅色主题、红涨绿跌（A 股口径），与 _apply_theme 设计系统一致（本页不内嵌导航，
    _apply_theme.py 会按 web/reversal/ 目录统一注入）。
  - 不输出任何买卖建议，仅量化筛选与方法论。
"""
from __future__ import annotations
import os, re, json, glob, sys, datetime, argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _xhist as X
import _emlink as EM

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QUANT = os.path.join(ROOT, "quant")
WEB = os.path.join(ROOT, "web")
OUTDIR = os.path.join(WEB, "reversal")
os.makedirs(OUTDIR, exist_ok=True)

CSS = """:root{--bg:#fbfbfd;--card:#fff;--text:#1d1d1f;--muted:#6e6e73;--line:#e5e5e7;
  --up:#ff3b30;--dn:#34c759;--blue:#0071e3;--gold:#b8893b;--orange:#ff9500;--purple:#af52de;}
*{box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"PingFang SC","Microsoft YaHei",sans-serif;
  background:var(--bg);color:var(--text);line-height:1.7;margin:0;padding:0}
.wrap{max-width:880px;margin:0 auto;padding:28px 18px 56px}
h1{font-size:23px;font-weight:700;margin:0 0 6px;letter-spacing:-.02em}
h2{font-size:18px;font-weight:600;margin:28px 0 12px;padding-bottom:8px;border-bottom:2px solid var(--blue)}
.sub{color:var(--muted);font-size:13px;margin-bottom:8px}
.card{background:var(--card);border-radius:16px;padding:16px 20px;margin:12px 0;box-shadow:0 1px 3px rgba(0,0,0,.05)}
.box{border-left:4px solid var(--blue);background:#f0f7ff;padding:14px 18px;border-radius:0 12px 12px 0;margin:14px 0}
.box.gold{border-color:var(--gold);background:#fffaf0}
.box.warn{border-color:var(--up);background:#fdf1f0}
.box.red{border-color:var(--dn);background:#f0faf3}
/* 表格：**不再横向滚动** —— 宽屏自适应换行；窄屏整行堆成卡片（列名由 td 的 data-l 提供） */
.tbl-wrap{max-width:100%;border:1px solid var(--line);border-radius:10px;margin-top:4px;background:#fff;}
table{width:100%;border-collapse:collapse;font-size:12.5px;table-layout:auto;}
th,td{padding:7px 5px;border-bottom:1px solid var(--line);text-align:right;
      white-space:normal;word-break:break-word;vertical-align:middle;}
th:first-child,td:first-child{text-align:left;}
th{color:var(--muted);font-weight:600;font-size:11.5px;background:#fafafa;white-space:nowrap;}
@media(max-width:1040px){
  table.rt thead{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);}
  table.rt tr{display:block;border-bottom:2px solid var(--line);padding:8px 0;}
  table.rt tr:last-child{border-bottom:0;}
  table.rt td{display:flex;align-items:baseline;justify-content:space-between;gap:12px;
              border:0;padding:3px 12px;text-align:right;white-space:normal;}
  table.rt td::before{content:attr(data-l);flex:0 0 44%;color:var(--muted);font-size:11.5px;text-align:left;}
  table.rt tbody tr:hover{background:transparent;}
}
.num{font-variant-numeric:tabular-nums;}
.up{color:var(--up)}.dn{color:var(--dn)}.am{color:var(--blue)}.dim{color:#b0b3b8}
a{color:inherit}
.tag{display:inline-block;font-size:11px;padding:2px 8px;border-radius:10px;margin:1px 2px}
.tag.A{background:#e6f7ec;color:#1a7a45}
.tag.B{background:#fff3e0;color:#e65100}
.tag.C{background:#fdecea;color:#c0392b}
.tag.new{background:#e8f0fe;color:#1967d2;margin-left:3px}
.case{font-size:13px;margin:8px 0;padding:10px 14px;background:#fafafa;border-radius:10px;border-left:3px solid var(--purple)}
.case .h{font-weight:600;margin-bottom:3px}
.note{font-size:12px;color:var(--muted);margin-top:8px;padding-top:8px;border-top:1px dashed var(--line)}
.arch{font-size:13px;margin:4px 0}
.arch a{color:var(--blue);text-decoration:none}
.arch a:hover{text-decoration:underline}
.step{font-size:13.5px;margin:8px 0;padding:10px 14px;background:#fafafa;border-radius:10px;border-left:3px solid var(--purple)}
.foot{text-align:center;color:var(--muted);font-size:12px;margin-top:28px}
ul{margin:8px 0;padding-left:20px}li{margin:4px 0}
""" + X.BADGE_CSS

STEPS = [
    ("步骤 1 · 域（全市场深跌域）", "A 股正股全量（剔 ST/退 与 20 日均成交额 &lt;3000 万），"
     "硬门槛 = 距 52 周高回撤 ≥18% 且未跌破 MA60×0.75。"
     "<b>不再使用</b>「净利同比&gt;50 &amp; 0&lt;PE&lt;50 &amp; 总市值&lt;100亿」的条件选股种子"
     "——那个域只有 220 只、每日过门槛约 150 只，横截面分位的噪声太大。"),
    ("步骤 2 · 打分（先验固定因子集）", "9 个因子<b>等权横截面分位</b>：距 20/60 日低点、距 52 周低点、"
     "量能枯竭、ATR 占比、20 日箱体宽度、距 MA60、均线斜率、市值对数。"
     "方向由经济逻辑给定（越靠近低点 / 越缩量 / 越低波动 / 箱体越窄 / 均线越未修复 / 市值越小 → 越好），"
     "<b>不筛因子、不按回测调权重</b>——只有先验固定才能让全期都是干净的样本外。"),
    ("步骤 3 · 阶段底部（v6 新增 · 位置必须站住）", "先识别<b>本轮下跌段</b>（最近一个显著高点 → 谷底），再要求："
     "① <b>已止跌</b>：谷底形成 ≥4 个交易日且期间不再创新低；② <b>仍在底部区</b>：现价距谷底 ≤15%；"
     "③ <b>跌得透</b>：本轮跌幅 ≥30%。谷底与平台上沿<b>锚定写盘</b>（quant/rev/bottom_state.json），"
     "只有「破底 3% / 远离 +30% / 锁定超 60 日」才重算并升版本 —— 价位不会天天改。"),
    ("步骤 4 · 回升启动证据（v6 新增 · 必须已经在回升）", "在底部区内统计命中几条纯技术证据（全市场可得、不含主力资金）："
     "站上 MA10 / MA10 上翘 / MACD 金叉或底背离 / 量能放大 / 突破平台上沿，<b>≥2 条</b>才算「即将回升」。"
     "走前消融里这是唯一<b>两半同向且为正</b>的条件（前半 +2.0pp / 后半 +6.4pp）。"),
    ("步骤 5 · 目标位（v6 改：本轮回撤，不是 52 周高）", "<b>T1 = 谷底 + 本轮跌幅×0.382，T2 = ×0.618</b>。"
     "旧口径按「52 周高回撤 0.382/0.618」算出来的目标位常常在半年高点附近，几乎不可兑现；"
     "新目标以本轮下跌段为尺度，并给出最近的真实阻力<b>「平台上沿」</b>（到了那里就该减，不一定要等 T1）。"),
    ("步骤 6 · 档位与环境（只控 β）", "排序仍按域内组合分取前 10%（A 档），<b>最终展示 = 通过新闸门 ∩ A 档</b>；"
     "环境按全市场广度给<b>仓位系数</b>（&lt;35% 防守 0.4× / 35~55% 中性 0.7× / ≥55% 进攻 1.0×），"
     "该系数<b>不改变排序</b>：环境状态与选股 α 的关系实测在训练半/测试半方向相反。"),
    ("步骤 7 · 退出纪律（唯一跨期稳定的改进）", "买区 = 缩量回踩 MA10/MA20 <b>不追高</b>；"
     "止损 = <b>跌破谷底 3%</b>（底部结构失效）先减半，跌到 −15% 全出；<b>+8%~+10% 先止盈一半</b>；"
     "单笔试仓 3–5%。<b>退出纪律 &gt; 入场筛选</b>——这是本项目唯一在两半样本外都稳定的改进。"),
]


def load_scan(date_arg=None):
    if date_arg:
        p = os.path.join(QUANT, f"watchlist_scan_{date_arg}.json")
        if not os.path.exists(p):
            raise SystemExit(f"未找到扫描数据：{p}")
        return p, date_arg
    files = sorted(glob.glob(os.path.join(QUANT, "watchlist_scan_*.json")))
    if not files:
        raise SystemExit("quant/ 下无 watchlist_scan_*.json，请先运行六步扫描落盘。")
    p = files[-1]
    m = re.search(r"watchlist_scan_(\d{8})\.json$", p)
    return p, (m.group(1) if m else None)


def compact_date(s):
    return s.replace("-", "")


def _prev_codes(dc):
    """上一期（日期 < dc 的最近一期）候选 6 位代码集合。"""
    files = sorted(glob.glob(os.path.join(QUANT, "watchlist_scan_*.json")))
    prev = None
    for p in files:
        m = re.search(r"watchlist_scan_(\d{8})\.json$", p)
        if m and m.group(1) < dc:
            prev = p
    if not prev:
        return set()
    try:
        j = json.load(open(prev, encoding="utf-8"))
    except Exception:
        return set()
    return {_code6(c) for c in (j.get("candidates") or [])}


def _code6(c):
    m = re.search(r"(\d{6})", str(c.get("code") or ""))
    return m.group(1) if m else str(c.get("code") or "")


def _num(v):
    """任意显示值 → 排序用数值；无法解析返回空串。"""
    if v is None:
        return ""
    if isinstance(v, (int, float)):
        return v
    s = str(v).replace(",", "").replace("%", "").replace("+", "").strip()
    if s in ("", "—", "-"):
        return ""
    mult = 1.0
    if s.endswith("亿"):
        s = s[:-1]
    elif s.endswith("万"):
        s, mult = s[:-1], 1.0 / 1e4
    try:
        return float(s) * mult
    except Exception:
        return ""


def pct_color(v):
    return "up" if v >= 0 else "dn"


def render_watchlist(scan):
    d = scan
    date = d["data_date"]
    dc = compact_date(date)
    cand = d["candidates"]
    nA = sum(1 for c in cand if c["tier"] == "A")
    nB = sum(1 for c in cand if c["tier"] == "B")
    nC = sum(1 for c in cand if c["tier"] == "C")

    hist = X.load_cross_history()
    P = d.get('presets') or {}
    prev_set = _prev_codes(dc)
    cur_codes = [_code6(c) for c in cand]
    new_c, cont_c, out_c = X.compare_sets(cur_codes, prev_set)
    cmp_html = (
        "<div class='xh-cmp'>"
        "<div class='cnew'><b>%d</b><span>本期与上期不重叠</span></div>"
        "<div class='ccont'><b>%d</b><span>连续在榜</span></div>"
        "<div class='cout'><b>%d</b><span>上期已退出</span></div>"
        "</div>"
        "<div class='note' style='border:none;padding:0;margin:0 0 6px'>口径提示：上一期（%s 前最近一期）为人工精选、样本远小于本期的机械筛选，"
        "「新进 / 退出」多为口径差异而非基本面变化，<b>对比仅供参考</b>；真正可比的是名称后的历史入选徽标。</div>"
        % (len(new_c), len(cont_c), len(out_c), dc))

    # 总表
    rows = []
    for c in cand:
        pcls = "up" if (c.get("dist_52hi") or 0) >= 0 else "dn"
        ycls = "up" if (c.get("ytd") or 0) >= 0 else "dn"
        mcls = "up" if (c["main20"] or "").startswith("+") else "dn"
        m5cls = "up" if (c.get("main5") or "").startswith("+") else "dn"
        g = _num(c.get("growth"))
        rows.append(
            f"<tr><td class='num' data-v=\"{c['_full'] if '_full' in c else c['code']}\">{c['code']}</td>"
            f"<td>{c['name']}{X.badge_html(hist, c['code'], date)}</td>"
            f"<td class='am num' data-v=\"{c.get('float_mv')}\">{c.get('float_mv')}</td>"
            f"<td class='num {pcls}' data-v=\"{c.get('dist_52hi')}\">{c.get('dist_52hi'):+.1f}%</td>"
            f"<td class='num {ycls}' data-v=\"{c.get('ytd')}\">{c.get('ytd'):+.1f}%</td>"
            f"<td class='num' data-v=\"{c.get('pe')}\">{c.get('pe')}</td>"
            f"<td class='num' data-v=\"{g if g is not None else ''}\">{('%.0f%%' % g) if g is not None else '—'}</td>"
            f"<td class='num {mcls}' data-v=\"{_num(c.get('main20'))}\">{c.get('main20')}</td>"
            f"<td class='num {m5cls}' data-v=\"{_num(c.get('main5'))}\">{c.get('main5')}</td>"
            f"<td class='num' data-v=\"{c.get('score')}\">{c.get('score')}</td>"
            f"<td><span class='tag {c['tier']}'>{c['tier']}</span></td>"
            f"<td class='xh-col'>{X.cell_html(hist, c['code'], date)}</td></tr>"
        )
    table = "".join(rows)

    # A 类
    a_cases = "".join(
        f"<div class='case'><div class='h hit'>✅ {c['name']} {c['code']} —— 低位+小盘+资金正+反转 共振</div>"
        f"{c['logic']}<br><b>操作：</b>{c.get('action','等信号确认。')}</div>"
        for c in cand if c["tier"] == "A")

    # B 类
    b_cases = "".join(
        f"<div class='case'><div class='h'>⚠️ {c['name']} {c['code']}</div>{c['logic']}</div>"
        for c in cand if c["tier"] == "B")

    # C 类
    c_rows = "".join(
        f"<tr><td class='num' data-v=\"{c['code']}\">{c['code']}</td>"
        f"<td>{c['name']}{X.badge_html(hist, c['code'], date)}</td>"
        f"<td class='am num' data-v=\"{c.get('float_mv')}\">{c.get('float_mv')}</td>"
        f"<td class='num {pct_color(c.get('dist_52hi') or 0)}' data-v=\"{c.get('dist_52hi')}\">{(c.get('dist_52hi') or 0):+.1f}%</td>"
        f"<td class='num {pct_color(c.get('ytd') or 0)}' data-v=\"{c.get('ytd')}\">{(c.get('ytd') or 0):+.1f}%</td>"
        f"<td class='num' data-v=\"{c.get('pe')}\">{c['pe']}</td>"
        f"<td class='num' data-v=\"{c.get('score')}\">{c.get('score')}</td>"
        f"<td>{c['logic']}</td></tr>"
        for c in cand if c["tier"] == "C")
    c_table = ("<table class='sortable'><thead><tr>"
               "<th data-k='code' data-t='s'>代码</th><th data-k='name' data-t='s'>名称</th>"
               "<th data-k='fmv' data-t='n'>流通亿</th><th data-k='d52' data-t='n'>距52高</th>"
               "<th data-k='ytd' data-t='n'>YTD</th><th data-k='pe' data-t='n'>PE(TTM)</th>"
               "<th data-k='score' data-t='n'>分</th><th data-k='why' data-t='s'>淘汰原因</th>"
               "</tr></thead><tbody>%s</tbody></table>") % c_rows

    a_action = next((c.get("action", "") for c in cand if c["tier"] == "A"), "")

    html = f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>底部反转观察池 · {date} 实测筛选</title><style>{CSS}</style></head>
<body><div class="wrap">
<h1>底部反转观察池 · 实测筛选结果</h1>
<div class="sub">数据基准：{date} 收盘｜ 方法：六步 Playbook ｜ 种子表达式 {P.get('seed','—')} 只 → 低位保留 {len(cand)} 只 → 逐只验证分级</div>

<div class="box gold">
<b>一句话：</b>严格按纪律，当前市场仅 <b>{nA} 只</b>进入"较确定区"（A 类），另有 {nB} 只边缘观察（B 类），{nC} 只淘汰（C 类）。
绝大多数"反转信号"要么资金未确认、要么已涨高、要么有基本面陷阱——这正是严格筛选的意义：<b>宁可少选、不错选</b>。
</div>

<h2>一、初筛漏斗：从 {P.get('seed','—')} 只种子到 A 类 {nA} 只</h2>
<div class="card"><table>
<tr><th>步骤</th><th>条件</th><th>数量</th></tr>
<tr><td>① 种子（服务端表达式）</td><td>单季净利同比 &gt; 50% ＋ 0 &lt; PE(TTM) &lt; 50 ＋ 总市值 &lt; 100 亿</td><td class="num">{P.get('seed','—')}</td></tr>
<tr><td>② 位置过滤（硬过滤）</td><td>距 52 周高回撤 ≥ 20%（真低位）</td><td class="num">{len(cand)}</td></tr>
<tr><td>③ 资金验证（命中数）</td><td>20 日主力净流入 &gt; 0</td><td class="num">{P.get('flow_pos','—')}</td></tr>
<tr><td>④ 技术验证（命中数）</td><td>MACD 金叉（DIF &gt; DEA）</td><td class="num">{P.get('golden','—')}</td></tr>
<tr><td>⑤ 技术验证（命中数）</td><td>站上 MA20</td><td class="num">{P.get('above_ma20','—')}</td></tr>
<tr><td>⑥ 分级结果</td><td>A 较确定区 / B 边缘观察 / C 淘汰</td><td class="num">{nA} / {nB} / {nC}</td></tr>
</table><div class="note">口径说明：②为硬过滤（真过滤），③④⑤是对 ② 的<b>命中计数</b>，<b>不作硬过滤</b>，仅参与打分与分级，故各数值之间不构成递减关系。种子由服务端表达式一步取得。westock <code>tool_filter</code> 的 <code>date</code> 参数会被忽略（只返当日快照），故<b>反转池无法回溯历史日期</b>，本页为 {date} 当日实拉。</div></div>

<h2>二、观察池总表（{len(cand)} 只实测）</h2>
{cmp_html}
<div class="card">
<div class="note" style="border:none;padding:0;margin:0 0 8px">名称后带 <span class="xh-badge">日期</span> 标记 = 该股此前曾在任一选股池入选（<b>悬停</b>看全部日期与池别：MACD观察池 / 信号池 / 做T池 / 反转池）。<b>所有列均可点击表头排序。</b></div>
<div style="overflow-x:auto"><table class="sortable">
<thead><tr>
<th data-k="code" data-t="s">代码</th><th data-k="name" data-t="s">名称</th>
<th data-k="fmv" data-t="n">流通亿</th><th data-k="d52" data-t="n">距52高</th>
<th data-k="ytd" data-t="n">YTD</th><th data-k="pe" data-t="n">PE(TTM)</th>
<th data-k="gro" data-t="n">单季增速</th><th data-k="m20" data-t="n">20日主力</th>
<th data-k="m5" data-t="n">5日主力</th><th data-k="score" data-t="n">分</th>
<th data-k="tier" data-t="s">档</th><th data-k="hist" data-t="s">历史入选</th>
</tr></thead>
<tbody>{table}</tbody></table></div>
<div class="note">评分 6 项：①流通&lt;100亿 ②距52高回撤&gt;25% ③扣非PE合理(0&lt;PE&lt;50) ④20日主力净流入为正 ⑤MACD 金叉(DIF&gt;DEA) ⑥站上 MA20。A=≥5分且资金+技术双确认，B=4分边缘，C=≤3分淘汰。数值列按真实数值排序（不受 %/单位/文本干扰）。</div></div>

<h2>三、A 类 · 严格合格</h2>
{a_cases or '<div class="case">本批无 A 类。市场底部反转组合稀缺，空仓等待也是纪律。</div>'}

<h2>四、B 类 · 边缘观察（缺一项，等补全）</h2>
{b_cases or '<div class="case">本批无 B 类。</div>'}

<h2>五、C 类 · 淘汰原因</h2>
<div class="card">{c_table}</div>

<h2>六、介入建议（对应 15 万 / 15% 回撤）</h2>
<div class="box red"><b>当前可执行动作：</b>
<ul style="margin:8px 0 0;padding-left:20px;font-size:13.5px">
<li><b>A 类</b>：列入一档观察。{a_action or '等一档信号（缩量回踩不破前低 + 再次放量）再试仓 3–5%。'}</li>
<li><b>B 类</b>：加入监控，等资金面/扣非 PE 补全信号，暂不介入。</li>
<li><b>C 类</b>：全部淘汰，不纳入任何仓位。</li>
<li>整体：当前市场底部反转机会稀缺，<b>宁可空仓等待</b>，不降低标准勉强选。</li>
</ul></div>

<div class="foot">本观察池为基于 westock 实拉数据的量化筛选结果，非个股推荐、非买卖建议。市场每日变化，需按 Playbook 六步动态复核。决策责任在账户本人。<br>
数据基准 {date} 收盘；页面生成 {d.get('generated', datetime.date.today().isoformat())}。</div>
</div></body></html>"""
    html = html.replace("</body>", X.SORT_JS + "</body>")
    return html, f"watchlist_{dc}.html"

def render_index(scan, archive):
    d = scan
    date = d["data_date"]
    dc = compact_date(date)
    cand = d["candidates"]
    _pre = d.get("presets") or {}
    nA = _pre.get("A") or sum(1 for c in cand if c["tier"] == "A")
    nB = _pre.get("B") or sum(1 for c in cand if c["tier"] == "B")
    n_hard = d.get("hard") or len(cand)
    n_univ = d.get("seed") or n_hard
    bt = d.get("bot") or {}
    n_botok = bt.get("n_botok") or 0
    n_sel = bt.get("n_sel") or len(cand)
    flow_src = d.get("flow_src") or "—"
    mf_date = ""
    for _c in cand:
        if _c.get("mf_date"):
            mf_date = _c["mf_date"]
            break
    ab = list(cand)
    prev_codes = _prev_codes(dc)
    ab_new = [_code6(c) for c in ab if _code6(c) not in prev_codes] if prev_codes else []
    NEW_SET = set(ab_new)
    n_new = len(ab_new)
    n_cont = len(ab) - n_new
    hist = X.load_cross_history()
    rows = []
    for c in ab:
        b = c.get("bot") or {}
        d52 = c.get("dist52")
        if d52 is None:
            d52 = c.get("dist_52hi") or 0
        pcls = "up" if d52 >= 0 else "dn"
        stage = b.get("stage") or "—"
        scls = {"底部区": "am", "启动": "up"}.get(stage, "dim")
        mf20 = c.get("mf20")
        main20 = ("%+.2f" % (mf20 / 1e8)) if mf20 is not None else c.get("main20")
        mval = _num(main20)
        mcls = "up" if (mval != "" and mval >= 0) else "dn"
        fmv = c.get("float_mv")
        fmv_txt = ("%.1f" % fmv) if isinstance(fmv, (int, float)) else "—"
        qs = c.get("qs")
        close = c.get("close")
        elo, ehi = c.get("entry_lo"), c.get("entry_hi")
        buy = ("%.2f~%.2f" % (elo, ehi)) if (elo is not None and ehi is not None) else "—"
        stop, t1 = c.get("stop"), c.get("t1")
        space = ((t1 - close) / close * 100) if (t1 and close) else None
        nm = c.get("name") or ""
        nm_html = EM.link(c.get("_full") or c["code"], nm or c["code"])
        new_tag = ("<span class='tag new' title='本期新进'>新</span>"
                   if _code6(c) in NEW_SET else "")
        hits = "；".join(c.get("lift_hits") or []) or "—"
        rows.append(
            f"<tr>"
            f"<td data-l='名称 · 代码'>{nm_html}{new_tag}{X.badge_html(hist, c['code'], date)}"
            f"<span class='dim' style='font-size:11px'> {c['code']}</span></td>"
            f"<td class='num' data-l='组合分' data-v=\"{qs if qs is not None else ''}\">"
            f"{('%.0f' % qs) if qs is not None else '—'}</td>"
            f"<td data-l='阶段' data-v=\"{stage}\"><span class='{scls}'>{stage}</span></td>"
            f"<td class='num' data-l='谷底 · 锁定' data-v=\"{b.get('trough') if b.get('trough') is not None else ''}\">"
            f"{('<b>%.2f</b>' % b['trough']) if b.get('trough') is not None else '—'}"
            f"<span class='dim' style='font-size:11px'> 已锁 {b.get('age') or 0} 日</span></td>"
            f"<td class='num dn' data-l='本轮跌幅' data-v=\"{b.get('fall') if b.get('fall') is not None else ''}\">"
            f"{('%.0f%%' % b['fall']) if b.get('fall') is not None else '—'}</td>"
            f"<td class='num' data-l='距谷底' data-v=\"{b.get('rise') if b.get('rise') is not None else ''}\">"
            f"{('+%.1f%%' % b['rise']) if b.get('rise') is not None else '—'}</td>"
            f"<td class='num' data-l='启动证据' data-v=\"{c.get('lift') or 0}\" title=\"{hits}\">"
            f"<b>{c.get('lift') or 0}</b> 条</td>"
            f"<td class='num am' data-l='现价' data-v=\"{close if close is not None else ''}\">"
            f"{close if close is not None else '—'}</td>"
            f"<td class='num' data-l='买区' data-v=\"{elo if elo is not None else ''}\">{buy}</td>"
            f"<td class='num dn' data-l='止损' data-v=\"{stop if stop is not None else ''}\">"
            f"{stop if stop is not None else '—'}"
            f"{('（%+.0f%%）' % c['stop_pct']) if c.get('stop_pct') is not None else ''}</td>"
            f"<td class='num up' data-l='回升目标 T1' data-v=\"{t1 if t1 is not None else ''}\">"
            f"{t1 if t1 is not None else '—'}"
            f"{('（+%.0f%%）' % space) if space is not None else ''}</td>"
            f"<td class='num' data-l='RR' data-v=\"{c.get('rr')}\">{c.get('rr')}</td>"
            f"<td class='num {mcls}' data-l='20日主力(亿)' data-v=\"{mval}\">"
            f"{main20 if main20 is not None else '—'}</td>"
            f"</tr>")
    ab_table = "".join(rows)

    steps_html = "".join(
        f"<div class='step'><b>{t}</b><br>{b_}</div>" for t, b_ in STEPS)

    arch_html = "\n".join(
        f"<div class='arch'>· <a href='{fn}'>{dt} 观察池</a></div>"
        for dt, fn in archive)

    cases = scan_cases()
    cases_html = "\n".join(
        f"<div class='arch'>· <a href='{fn}'>{lb}</a></div>"
        for lb, fn in cases)

    html = f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>底部反转选股 · 板块</title><style>{CSS}</style></head>
<body><div class="wrap">
<h1>底部反转选股 · 板块</h1>
<div class="sub">数据基准：{date} 收盘｜ 每日随数据更新重扫 ｜ <b>v6</b>：阶段底部锚定 ＋ 回升启动确认 ＋ 本轮回撤目标</div>

<div class="box gold">
<b>核心：</b>v6 不再拿「距 52 周高回撤 ≥18%」当底部——那只说明<b>跌得多</b>，
可以是下跌中途，也可以是已经反弹一大截之后。现在先识别<b>本轮下跌段的谷底</b>，要求它
<b>站住了</b>（≥4 个交易日不再创新低、现价仍在谷底 +15% 以内、本轮跌幅 ≥30%），
再要求已经出现<b>回升启动证据 ≥{bt.get('lift_min', 2)} 条</b>；
目标位也改成<b>本轮下跌段的斐波那契回撤</b>（0.382 / 0.618），而不是过去那个按 52 周高算出来、
几乎不可兑现的天价。<br>
本期：入域 <b>{n_univ}</b> 只 → 旧硬门槛 <b>{n_hard}</b> 只 → 阶段底部 ＋ 启动证据 <b>{n_botok}</b> 只 →
∩ 组合分前 10% = <b>精选 {n_sel} 只</b>。<br>
<b style="color:#b00020">谷底与平台上沿一旦确立就锁死</b>（写入本地锚定文件）：
只有「跌破谷底 3% / 距谷底 +30% 以上 / 锁定超 60 个交易日」才重新检测并升版本 —— 不会天天变。
</div>

<div class="box" style="border-left:4px solid #b8332a;background:#fdf3f2">
<b>诚实披露 · 弱势期纪律（用之前必读）：</b><br>
① 反转池「组合分前 10%」相对胜率约 <b>62–65%</b>（健康区间），但样本外存在明确<b>期间依赖</b>：
half_oos 切分下训练半相对胜率 <b>−2.97pp</b>、测试半 <b>+16.35pp</b> —— 信号强度随市场环境大幅摆动，<b>不能假定稳定可兑现</b>。<br>
② 因此<b>环境只控仓位（β），不改排序</b>：全市场广度 &lt;35%（弱势）时仓位系数降到 0.4×，
并建议直接<b>空仓等待</b>，不靠选股对抗系统性下行；广度 35~55% 中性 0.7×；≥55% 进攻 1.0×。<br>
③ <b>退出纪律 &gt; 入场筛选</b>：严格止损（谷底×0.97）+ 移动止盈，是本项目唯一在两段样本外都稳定的改进。<br>
④ 本池<b>不宣称能靠环境提高 α</b> —— 它只解决「什么时候该收手」，不解决「选哪只一定涨」。
</div>

<h2>方法论（v6 · 阶段底部锚定 ＋ 启动确认）</h2>
<div class="card">{steps_html}
<div class="note"><a href="method.html" style="color:var(--blue);text-decoration:none;font-weight:600">→ 完整方法论 Playbook</a>
｜ <a href="lab.html" style="color:var(--blue);text-decoration:none;font-weight:600">→ 特征功效实验室（哪些因子真的有效）</a>
｜ <a href="backtest.html" style="color:var(--blue);text-decoration:none;font-weight:600">→ 退出规则回测</a></div>
</div>

<h2>最新精选（{date} · {n_sel} 只）</h2>
<div class="card">
<div class="note" style="border:none;padding:0;margin:0 0 8px">
本表<b>只展示通过全部闸门且属域内组合分前 10% 的标的</b>，参考票不列表。
其中相对上一期<b>新进 {n_new}</b> 只（名称后带 <span class="tag new">新</span>）/ 连续在榜 {n_cont} 只。
名称后徽标 = 跨池历史入选日期（悬停看全部）。<b>各列可点击表头排序；窄屏自动堆成卡片，不需要左右拖动。</b></div>
<div class="tbl-wrap"><table class="sortable rt">
<thead><tr><th data-k="name" data-t="s">名称 · 代码</th><th data-k="qs" data-t="n">组合分</th>
<th data-k="stage" data-t="s">阶段</th><th data-k="trough" data-t="n">谷底 · 锁定</th>
<th data-k="fall" data-t="n">本轮跌幅</th><th data-k="rise" data-t="n">距谷底</th>
<th data-k="lift" data-t="n">启动证据</th><th data-k="close" data-t="n">现价</th>
<th data-k="buy" data-t="n">买区</th><th data-k="stop" data-t="n">止损</th>
<th data-k="t1" data-t="n">回升目标 T1</th><th data-k="rr" data-t="n">RR</th>
<th data-k="m20" data-t="n">20日主力(亿)</th></tr></thead>
<tbody>{ab_table}</tbody></table></div>
<div class="note"><a href="watchlist_{dc}.html" style="color:var(--blue);text-decoration:none;font-weight:600">→ 查看 {date} 完整详情页（含走前验证与被取消原因）</a> ·
<a href="lab.html" style="color:var(--blue);text-decoration:none;font-weight:600">样本外证据实验室</a></div>

<div class="note" style="border-top:1px dashed var(--line)">数据口径：<b>名称 / 流通市值</b>来自腾讯行情快照；<b>20 日主力净流入</b>来自 {flow_src}{('，基准日 ' + mf_date) if mf_date else ''}（单位：亿元，红=净流入 / 绿=净流出）。
主力净额只作<b>弱辅助</b>，且<b>不计入「启动证据」门槛</b>（全市场并非每只都有值，避免因数据有无导致入选偏差）。
<b>所有股票名称可点击</b>，直达东方财富个股行情。</div>
</div>

<h2>这张表怎么用（操作路径）</h2>
<div class="card">
<div class="step"><b>第 1 步 · 先看「阶段」</b><br>
<b>底部区</b> = 已经止跌、仍在谷底附近横着；<b>启动</b> = 已突破谷底之后的平台上沿，但还没走远。
只要出现「下跌中 / 已脱离」就不会进这张表（前者还在创新低，后者已经涨超谷底 15%）。</div>
<div class="step"><b>第 2 步 · 认牢「谷底」这个数</b><br>
谷底价是<b>结构止损的基准</b>，锚定后不再天天改：后面写着「已锁 N 日 · 第 v 版」。
跌破谷底 3% 意味着底部结构失效 → 无条件减仓，不做「再等等」。</div>
<div class="step"><b>第 3 步 · 先看「平台上沿」，再看 T1 / T2</b><br>
T1 = 谷底 + 本轮跌幅 × 0.382，T2 = ×0.618 —— 按<b>本轮下跌段</b>算，比按 52 周高算的目标近得多。
但股价会先撞上<b>「平台上沿」</b>（谷底之后形成的前高，见详情页），那是最近的真实阻力，<b>到不了 T1 就先减一半</b>。</div>
<div class="step"><b>第 4 步 · 退出纪律（唯一跨期稳定的部分）</b><br>
买入等回踩，<b>不追高</b>。止损分两层：跌破<b>谷底结构位</b>先减半，跌到 <b>−15% 全出</b>；
<b>+8%~+10% 先止盈一半</b>；单笔试仓 3–5%。实验室把止损/目标两半对照后，
宽止损 + 早止盈是<b>两半同向</b>的最优组合（−15% / +8% → 训练半 54.7% / 测试半 55.8%），
而最紧的 −6% 止损只有 41.3% / 36.3%（因为前 10% 的平均最大不利偏移已达 −7.7%，贴身止损必被扫）。</div>
</div>

<div class="box red" style="border-color:#b00020"><b>⚠️ 诚实标注（必读）：</b>
位置约束<b>本身几乎是胜率中性甚至略负的</b>——单独要求「贴着谷底」并不提高前向收益
（大样本走前消融相对各自半区基线 −2.5pp / −0.8pp）。它换来的是<b>尾部风险下降</b>（平均最大不利偏移收窄），
也就是「不追高、不接飞刀」。真正稳定提供边际的是<b>「已经出现回升启动证据」</b>（同一消融 +2.0pp / +6.4pp）。
所以这套规则是<b>风险控制 ＋ 证据确认</b>的组合，不是「越跌越买」的反向交易系统。</div>

<div class="box warn"><b>仓位与红线：</b>
单笔试仓 <b>3%（可至 5%）</b>，按 −15% 硬止损折算 = 单笔最大亏损约 <b>总资金 0.45%~0.75%</b>。
总暴露乘当日<b>仓位系数</b>（广度 &lt;35% → 0.4× / 35~55% → 0.7× / ≥55% → 1.0×），
该系数<b>只控 β、不改排序</b>。反转策略靠「多次小亏换一次大赚」，<b>退出纪律 &gt; 入场筛选</b>。
本页所有价位都是量化区间，非买卖建议。</div>

<h2>方法验证案例</h2>
<div class="card">{cases_html or '<div class="note">暂无案例。</div>'}</div>

<h2>历史观察池归档</h2>
<div class="card">{arch_html or '<div class="note">暂无历史归档。</div>'}</div>

<div class="foot">本版块为基于离线前复权日K（腾讯）与样本外实证的量化筛选与方法论，非个股推荐、非买卖建议。决策责任在账户本人。</div>
</div></body></html>"""
    html = html.replace("</body>", X.SORT_JS + "</body>")
    return html
def scan_archive():
    """返回 [(日期串 YYYY-MM-DD, 文件名)]，按日期倒序。"""
    out = []
    for fn in os.listdir(OUTDIR):
        m = re.match(r"^watchlist_(\d{8})\.html$", fn)
        if not m:
            continue
        s = m.group(1)
        try:
            dt = datetime.datetime.strptime(s, "%Y%m%d").strftime("%Y-%m-%d")
        except Exception:
            dt = s
        out.append((dt, fn))
    out.sort(reverse=True)
    return out


CASE_LABELS = {
    "songfa-603268-20260911.html": "松发股份（603268）独立分析",
    "songfa_model_candidates_20260911.html": "松发模型 · 选股候选池",
    "songfa_verify_20260911.html": "候选真实性复核 + 胜率评估",
    "dajin_yangxian_20260911.html": "大金重工 · 3 倍量阳线解读",
}


def scan_cases():
    """返回 [(展示名, 文件名)]，用于入口页给案例页补入链、消除孤儿页。"""
    out = []
    for fn in sorted(os.listdir(OUTDIR)):
        if re.match(r"^songfa.*\.html$", fn) or re.match(r"^dajin_.*\.html$", fn):
            out.append((CASE_LABELS.get(fn, fn), fn))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("date", nargs="?", default=None, help="数据日期 compact YYYYMMDD")
    a = ap.parse_args()
    path, dc = load_scan(a.date)
    scan = json.load(open(path, encoding="utf-8"))

    # 观察池明细：rev_pool（v4/v5 横截面分位组合）已自行输出同文件，本脚本不覆盖，避免两套渲染互相打架
    doc = str(scan.get("_doc") or "")
    _ver = str(scan.get("version") or "")
    if "v4" in doc or "v5" in doc or _ver.startswith("rev_v"):
        print("检测到 rev_pool scan（version=%s，%s…）→ 跳过 watchlist 明细，避免覆盖" % (_ver or "—", doc[:26]))
    else:
        wl_html, wl_fn = render_watchlist(scan)
        open(os.path.join(OUTDIR, wl_fn), "w", encoding="utf-8").write(wl_html)
        print("生成", os.path.join("web/reversal", wl_fn))

    # 入口页（滚动更新）
    arch = scan_archive()
    idx_html = render_index(scan, arch)
    open(os.path.join(OUTDIR, "index.html"), "w", encoding="utf-8").write(idx_html)
    print("生成 web/reversal/index.html（最新数据日期", scan["data_date"], "）")

    print("完成。记得跑：python quant/_apply_theme.py 注入导航与主题，再 _link_check.py 校验。")


if __name__ == "__main__":
    main()
