# -*- coding: utf-8 -*-
"""上海九百(sh600838) 三周期调研报告生成器 · 2026-09-03 收盘口径"""
import io, os, sys
from _nav import selfcontained_nav

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "web", "research", "research-600838-20260904.html")
NAV = selfcontained_nav("research", home="../../index.html")

# ---------- 数据（全部来自 westock-mcp 实拉） ----------
Q = dict(price=8.45, chg=-1.97, pe=72.67, pe_fwd=67.55, pb=2.18, mktcap=33.87,
         ytd=-21.66, lo52=6.49, hi52=15.43, turn=5.74, vr=0.76, div=0.4,
         c5=1.56, c10=12.52, c20=16.14, c60=10.66, shares=4.0088)

# 周线收盘（旧->新）
W = [8.01,8.03,8.17,8.29,8.54,8.52,8.64,8.69,8.82,9.21,9.07,8.86,8.69,8.46,8.41,
     8.36,8.18,8.69,8.80,8.80,9.06,8.50,9.04,8.89,8.47,11.06,11.04,10.79,13.48,
     12.34,13.79,11.96,11.99,11.09,11.12,10.83,10.69,10.41,10.46,9.74,10.16,10.05,
     9.58,9.56,9.58,8.87,8.50,8.47,7.97,7.70,7.59,7.10,7.34,7.03,7.05,6.57,7.27,
     7.21,7.33,7.42,8.60,8.45]
WLAB = ["25/06","","","","","25/08","","","","","25/10","","","","","25/12","","",
        "","26/01","","","","26/02","","","26/03","","","","26/04","","","","26/05",
        "","","26/06","","","","26/07","","","","26/08","","","26/09"]

# 半年度与单季拆分（万元）
FIN = [
    ("2024H1", 4554.88,  0.04, 2373.18, -32.07, 25.57),
    ("2025H1", 4505.35, -1.09, 2378.97,   0.24, 25.89),
    ("2026H1", 4322.53, -4.06, 2507.39,   5.40, 23.45),
]
QTR = [
    ("2025Q1", 2310.25,  0.02, 1233.56,  22.12),
    ("2025Q2", 2195.10, -2.23, 1145.41, -15.97),
    ("2026Q1", 2343.00,  1.42,  986.31, -20.04),
    ("2026Q2", 1979.53, -9.82, 1521.08,  32.80),
]

# 股东（2026-06-30）
HOLD = [
    ("上海新南西(集团)有限公司", 25.66, "0", "控股股东·静安区国资"),
    ("上海静安资本投资运营有限公司", 6.93, "0", "静安区国资"),
    ("程蓓", 2.32, "+39.0万", "自然人·增持"),
    ("百联集团有限公司", 1.84, "0", "上海国资"),
    ("陈哲育", 1.45, "0", "自然人"),
    ("UBS AG", 0.67, "0", "外资"),
    ("阙晨", 0.59, "+1.0万", "自然人·增持"),
    ("王晓妍", 0.57, "+0.06万", "自然人·增持"),
    ("南方中证全指房地产ETF", 0.55, "-115.56万", "被动指数·减持"),
    ("翁其文", 0.54, "0", "自然人"),
]

# 融资余额（亿）
MARGIN = [1.570,1.601,1.624,1.668,1.691,1.661,1.666,1.651,1.614,1.633,1.631,1.562,
          1.674,1.645,1.700,1.754,1.764,1.776]
MLAB = ["8/10","","","","8/14","","","","8/20","","8/24","","8/26","","8/28","","9/01","9/02"]

# 主力资金（万元）
FLOW = [("今日", -1666.42), ("5日", 1683.29), ("10日", 7285.46), ("20日", 6856.19)]

# 七条标准
RULE = [
    ("强趋势", "mid", "20日 +16.14% 反弹，但 YTD −21.66%，距 1 月高点 15.43 仍 −45%，处于大级别下降通道内的反弹"),
    ("相对低位", "ok", "8.45 距 52 周高 −45%；但已自 6.49 低点反弹 +30%，性价比下降"),
    ("量价健康", "mid", "8/28 放量突破（周换手 35%）；但 9/3 量比 0.76 缩量回落，主力净流出 1666 万"),
    ("机构主导", "bad", "零公募、零社保、零北向；唯一持有的房地产 ETF 减持 115.56 万股；资金评分 46.76（周 −39.14）"),
    ("订单业绩可验证", "bad", "Q2 单季营收 −9.82%；利润靠投资收益，毛利率反降至 23.45%"),
    ("瓶颈环节", "bad", "酒类批发＋物业租赁＋洗染，无技术壁垒、无议价权"),
    ("换手适中", "mid", "5.74% 偏高，1 月曾单周换手 116.73%，游资主导特征明显"),
]

# 板块
SECT = dict(name="一般零售（申万二级）", chg=0.09, turn=3.03, up="20/60",
            today=6.15, d5=14.72, d20=21.33, rank=2, total=124,
            leader="百大集团 +10.02%")

SCORE = [("资金", 46.76, -39.14), ("技术", 75.62, -11.06), ("基本面", 72.52, 2.49),
         ("风险", 82.46, 2.36), ("综合", 70.15, -3.96)]

# ---------- SVG 助手 ----------
def spark(vals, w=1000, h=230, lo=None, hi=None, pad=14):
    lo = lo or min(vals); hi = hi or max(vals)
    rng = (hi - lo) or 1
    n = len(vals)
    def X(i): return pad + i * (w - 2*pad) / (n - 1)
    def Y(v): return h - pad - (v - lo) / rng * (h - 2*pad)
    pts = " ".join("%.1f,%.1f" % (X(i), Y(v)) for i, v in enumerate(vals))
    area = "%s %.1f,%.1f %.1f,%.1f" % (pts, X(n-1), h-pad, X(0), h-pad)
    g = []
    # 关键位参考线
    for lv, col, lab in ((8.82,"#b8893b","8.82 布林上轨"), (7.82,"#9aa4b2","7.82 布林中轨"),
                         (6.49,"#1a9e5a","6.49 52周低")):
        if lo <= lv <= hi:
            y = Y(lv)
            g.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="%s" '
                     'stroke-width="1" stroke-dasharray="4 4" opacity=".75"/>' % (pad, y, w-pad, y, col))
            g.append('<text x="%.1f" y="%.1f" fill="%s" font-size="10.5" '
                     'text-anchor="end">%s</text>' % (w-pad-2, y-4, col, lab))
    g.append('<polygon points="%s" fill="#b8893b" opacity=".08"/>' % area)
    g.append('<polyline points="%s" fill="none" stroke="#b8893b" stroke-width="2" '
             'stroke-linejoin="round"/>' % pts)
    # urrent point
    cx, cy = X(n-1), Y(vals[-1])
    g.append('<circle cx="%.1f" cy="%.1f" r="4" fill="#b8332a"/>' % (cx, cy))
    g.append('<text x="%.1f" y="%.1f" fill="#b8332a" font-size="12" font-weight="700" '
             'text-anchor="end">8.45</text>' % (cx-7, cy-6))
    # 头部高点标注
    iy = vals.index(max(vals))
    g.append('<circle cx="%.1f" cy="%.1f" r="3.2" fill="#1a9e5a"/>' % (X(iy), Y(max(vals))))
    g.append('<text x="%.1f" y="%.1f" fill="#1a9e5a" font-size="11" font-weight="700">'
             '13.79 周收盘高</text>' % (X(iy)+7, Y(max(vals))-6))
    return ('<svg class="chart" viewBox="0 0 %d %d" preserveAspectRatio="xMidYMid meet">%s</svg>'
            % (w, h, "".join(g)))

def margin_chart(vals, w=1000, h=190, pad=16):
    lo, hi = min(vals)*0.985, max(vals)*1.015
    rng = hi - lo
    n = len(vals)
    def X(i): return pad + i * (w - 2*pad) / (n - 1)
    def Y(v): return h - pad - (v - lo) / rng * (h - 2*pad)
    pts = " ".join("%.1f,%.1f" % (X(i), Y(v)) for i, v in enumerate(vals))
    g = ['<polyline points="%s" fill="none" stroke="#b8332a" stroke-width="2" '
         'stroke-linejoin="round"/>' % pts]
    for i, v in enumerate(vals):
        if i in (0, 11, 12, 14, n-1):
            g.append('<circle cx="%.1f" cy="%.1f" r="3" fill="#b8332a"/>' % (X(i), Y(v)))
            g.append('<text x="%.1f" y="%.1f" fill="#6b7280" font-size="10.5" '
                     'text-anchor="middle">%.3f</text>' % (X(i), Y(v)-8, v))
    g.append('<text x="%.1f" y="%d" fill="#9aa4b2" font-size="10.5" text-anchor="start">%s</text>'
             % (pad, h-3, MLAB[0]))
    g.append('<text x="%.1f" y="%d" fill="#9aa4b2" font-size="10.5" text-anchor="end">%s</text>'
             % (w-pad, h-3, MLAB[-1]))
    return ('<svg class="chart" viewBox="0 0 %d %d" preserveAspectRatio="xMidYMid meet">%s</svg>'
            % (w, h, "".join(g)))

def flow_chart(items, w=1000, h=170, pad=18):
    mx = max(abs(v) for _, v in items)
    n = len(items)
    bw = (w - 2*pad) / n
    zero = h - 46
    g = ['<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="#c9ced6" stroke-width="1"/>' % (pad, zero, w-pad, zero)]
    for i, (lab, v) in enumerate(items):
        cx = pad + bw*i + bw/2
        hh = abs(v)/mx * 92
        col = "#b8332a" if v >= 0 else "#1a9e5a"
        y = zero - hh if v >= 0 else zero
        g.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="%s" rx="3"/>'
                 % (cx-bw*0.26, y, bw*0.52, hh, col))
        vy = y - 6 if v >= 0 else y + hh + 13
        g.append('<text x="%.1f" y="%.1f" fill="%s" font-size="12" font-weight="700" '
                 'text-anchor="middle">%+.0f</text>' % (cx, vy, col, v))
        g.append('<text x="%.1f" y="%d" fill="#6b7280" font-size="11.5" '
                 'text-anchor="middle">%s</text>' % (cx, h-8, lab))
    return ('<svg class="chart" viewBox="0 0 %d %d" preserveAspectRatio="xMidYMid meet">%s</svg>'
            % (w, h, "".join(g)))

def tag(k):
    return {"ok":'<span class="tag ok">符合</span>', "mid":'<span class="tag mid">部分</span>',
            "bad":'<span class="tag bad">不符</span>'}[k]

def pct(v, dig=2):
    return ('<span class="up">+%.*f%%</span>' if v >= 0 else '<span class="dn">%.*f%%</span>') % (dig, v)

# ---------- HTML ----------
def build():
    P = []
    a = P.append
    a('<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">')
    a('<meta name="viewport" content="width=device-width,initial-scale=1">')
    a('<title>上海九百（600838）三周期调研 · 2026-09-03 收盘口径</title><style>')
    a(''':root{--bg:#f5f6f8;--card:#fff;--ink:#1c2430;--ink2:#23262b;--sub:#6b7280;
      --line:#e5e7eb;--gold:#b8893b;--red:#b8332a;--green:#1a9e5a}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink2);
 font:15px/1.75 -apple-system,"PingFang SC","Microsoft YaHei",sans-serif}
.wrap{max-width:1080px;margin:0 auto;padding:28px 20px 64px}
header{background:var(--card);border:1px solid var(--line);border-radius:14px;
 padding:24px 26px;margin-bottom:18px}
h1{margin:0 0 4px;font-size:24px;color:var(--ink);letter-spacing:-.2px}
.sub{color:var(--sub);font-size:13px}
.px{display:flex;align-items:baseline;gap:12px;margin:14px 0 4px}
.px b{font-size:38px;color:var(--ink);font-weight:700;letter-spacing:-1px}
.kv{display:grid;grid-template-columns:repeat(auto-fit,minmax(128px,1fr));gap:10px;margin-top:16px}
.kv div{background:#fafbfc;border:1px solid var(--line);border-radius:9px;padding:9px 12px}
.kv span{display:block;color:var(--sub);font-size:11.5px}
.kv b{font-size:16px;color:var(--ink);font-weight:600}
section{background:var(--card);border:1px solid var(--line);border-radius:14px;
 padding:22px 26px;margin-bottom:18px}
h2{margin:0 0 6px;font-size:18px;color:var(--ink);border-left:3px solid var(--gold);padding-left:10px}
h3{margin:22px 0 8px;font-size:15px;color:var(--ink)}
p{margin:8px 0}
.lead{color:var(--sub);font-size:13.5px;margin:0 0 16px;padding-left:13px}
table{width:100%;border-collapse:collapse;font-size:13.5px;margin:10px 0}
th,td{padding:9px 10px;border-bottom:1px solid var(--line);text-align:right}
th{background:#fafbfc;color:var(--sub);font-weight:600;font-size:12.5px;text-align:right;white-space:nowrap}
th:first-child,td:first-child{text-align:left}
td.k{color:var(--ink);font-weight:600;white-space:nowrap}
td.desc{text-align:left;color:#4b5563;font-size:13px;line-height:1.65}
td.num{font-variant-numeric:tabular-nums;font-weight:600;color:var(--ink)}
tr:last-child td{border-bottom:none}
.up{color:var(--red);font-weight:600}.dn{color:var(--green);font-weight:600}
.fl{color:var(--sub)}
.chart{width:100%;height:auto;display:block;margin:14px 0 6px}
.tag{display:inline-block;padding:2px 9px;border-radius:20px;font-size:11.5px;font-weight:600;white-space:nowrap}
.tag.ok{background:#e8f5ee;color:#127a45}.tag.bad{background:#fbeceb;color:#a02b23}
.tag.mid{background:#fdf3e3;color:#9a6c25}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(238px,1fr));gap:14px;margin:14px 0}
.card{border:1px solid var(--line);border-radius:11px;padding:16px 17px;background:#fafbfc}
.card .t{font-size:12.5px;color:var(--sub);margin-bottom:6px}
.card .v{font-size:17px;font-weight:700;color:var(--ink);margin-bottom:6px}
.card .d{font-size:13px;color:#4b5563;line-height:1.65}
.card.hot{border-color:#e8c98a;background:#fdf9f1}
.card.cold{border-color:#cfe6da;background:#f4fbf7}
.note{border-left:3px solid var(--gold);background:#fdf9f1;padding:13px 16px;
 border-radius:0 9px 9px 0;margin:14px 0;font-size:13.5px;line-height:1.7}
.note.warn{border-color:var(--red);background:#fdf4f3}
.note.good{border-color:var(--green);background:#f2faf6}
.note b{color:var(--ink)}
ul{margin:8px 0;padding-left:20px}li{margin:5px 0}
.chk{list-style:none;padding-left:2px}
.chk li{padding-left:24px;position:relative}
.chk li:before{content:"□";position:absolute;left:0;color:var(--gold);font-size:15px}
.bar{display:inline-block;width:118px;height:7px;background:#eef0f3;border-radius:4px;
 overflow:hidden;vertical-align:middle;margin-right:7px}
.bar i{display:block;height:100%;border-radius:4px}
footer{color:var(--sub);font-size:12px;text-align:center;padding:8px 0 0}
@media(max-width:640px){.wrap{padding:16px 12px 48px}section{padding:18px 16px}h1{font-size:20px}}''')
    a('</style></head><body><div class="wrap">')
    a(NAV)

    # header
    a('<header><h1>上海九百（600838）· 三周期调研</h1>')
    a('<div class="sub">上海主板 · 商贸零售／一般零售 · 酒类批发＋商业物业租赁＋股权投资＋洗染 · '
      '上市 1994-02-24 · 董事长 许騂</div>')
    a('<div class="px"><b>8.45</b><span class="dn" style="font-size:16px;font-weight:600">'
      '-1.97%</span><span class="fl">2026-09-03 收盘</span></div>')
    kv = [("市盈率 TTM", "72.67"), ("市净率", "2.18"), ("总市值", "33.87 亿"),
          ("年初至今", "-21.66%"), ("52 周区间", "6.49–15.43"), ("换手率", "5.74%"),
          ("20 日涨幅", "+16.14%"), ("股息率 TTM", "0.40%")]
    a('<div class="kv">' + "".join(
        '<div><span>%s</span><b class="%s">%s</b></div>' % (
            k, "dn" if v.startswith("-") else "", v) for k, v in kv) + '</div></header>')

    # 三周期结论
    a('<section><h2>三周期结论</h2>')
    a('<p class="lead">一句话：板块资金是全市场第 2 强，但个股基本面撑不起 72 倍 PE——'
      '这是「强板块 + 弱个股 + 游资主导」的组合，只能做短线博弈，不能做增值底仓。</p>')
    a('<div class="cards">')
    a('<div class="card hot"><div class="t">短线（1–5 个交易日）</div>'
      '<div class="v">不追高 · 回踩才参与</div>'
      '<div class="d">趋势仍向上（站上布林中轨、MACD 零轴上金叉），但动能已衰减：'
      'RSI6 从 81.9 回落到 61.9，KDJ 高位钝化，MACD 柱连续缩短。'
      '今日主力净流出 1666 万、超大单流出 1236 万，<b>跑输板块</b>。'
      '压力 8.82，生命线 7.82。</div></div>')
    a('<div class="card"><div class="t">中线（1–3 个月）</div>'
      '<div class="v">条件持有 · 三季报是裁判</div>'
      '<div class="d">唯一硬支撑是板块：一般零售 5 日主力净流入 +14.72 亿，'
      '全市场 124 个行业排第 2。但个股 Q2 单季营收 −9.82%，利润靠投资收益。'
      '国资控股 34.4%、无减持无质押是安全垫。三季报营收若继续负增长，中线逻辑瓦解。</div></div>')
    a('<div class="card cold"><div class="t">长线（6 个月以上）</div>'
      '<div class="v">不作增值核心仓</div>'
      '<div class="d">营收 3 年复合 −1.72%、归母净利 3 年复合 −10.47%、ROE 仅 3.0%、'
      '股息率 0.4%。33.87 亿市值对应 0.94 亿营收（PS≈36 倍），'
      '定价的是<b>静安核心商业物业 + 国资重组期权</b>，不是盈利能力。'
      '只在「国资重组明确落地」这一事件情景下成立。</div></div>')
    a('</div></section>')

    # 价格结构
    a('<section><h2>价格结构与关键位</h2>')
    a('<p class="lead">周线收盘（2025-06 至 2026-09）。这是一只典型的「投机冲高—漫长阴跌—放量反弹」走势。</p>')
    a(spark(W))
    a('<table><tr><th>阶段</th><th>区间</th><th>幅度</th><th>说明</th></tr>'
      '<tr><td class="k">底部平台</td><td class="num">7.5 – 9.2</td><td class="fl">—</td>'
      '<td class="desc">2025 年下半年横盘，成交清淡</td></tr>'
      '<tr><td class="k">投机冲高</td><td class="num">8.47 → 15.43</td><td class="up">+82%</td>'
      '<td class="desc">2025-12 至 2026-01，单周换手率峰值 <b>116.73%</b>，纯资金推动</td></tr>'
      '<tr><td class="k">单边阴跌</td><td class="num">15.43 → 6.49</td><td class="dn">-58%</td>'
      '<td class="desc">2026-01 至 07，历时 6 个月，抹去全部涨幅并创新低</td></tr>'
      '<tr><td class="k">放量反弹</td><td class="num">6.49 → 8.77</td><td class="up">+35%</td>'
      '<td class="desc">2026-07-31 见底，8/28 单周成交 1.41 亿股、换手 35.17% 突破</td></tr></table>')
    a('<h3>关键价位</h3>')
    a('<table><tr><th>位置</th><th>价格</th><th>含义</th></tr>'
      '<tr><td class="k">强阻力</td><td class="num">9.35 – 9.63</td>'
      '<td class="desc">2026-05 密集成交区，反弹第一目标上限</td></tr>'
      '<tr><td class="k">阻力</td><td class="num">8.82 / 8.97</td>'
      '<td class="desc">布林上轨 8.82；5 月高点 8.97</td></tr>'
      '<tr><td class="k">现价</td><td class="num">8.45</td><td class="desc">—</td></tr>'
      '<tr><td class="k">短线支撑</td><td class="num">7.82</td>'
      '<td class="desc"><b>布林中轨＝短线生命线</b>，跌破则反弹结束</td></tr>'
      '<tr><td class="k">强支撑</td><td class="num">7.19 – 7.42</td>'
      '<td class="desc">8 月整理平台</td></tr>'
      '<tr><td class="k">绝对底</td><td class="num">6.49</td>'
      '<td class="desc">52 周低（2026-07-31），破位无条件离场</td></tr></table>')
    a('<div class="note warn"><b>波动警示：</b>该股 2026-01-09 当周换手率高达 116.73%，'
      '意味着一周内全部流通筹码换手超过一遍。此类标的单日 ±5% 属常态，'
      '仓位必须按「小仓博弈」而非「核心持仓」来设计。</div>')
    a('</section>')

    # 基本面
    a('<section><h2>基本面：单季拆分拆掉「利润增长」的假象</h2>')
    a('<p class="lead">半年报净利 +5.40% 看似转正，但拆到单季就露出真面目：'
      'Q2 营收 −9.82%，利润 +32.80% 全靠投资收益。</p>')
    a('<h3>半年度口径</h3>')
    a('<table><tr><th>报告期</th><th>营收(万)</th><th>同比</th><th>归母净利(万)</th>'
      '<th>同比</th><th>毛利率</th></tr>')
    for d, r, rg, p, pg, gm in FIN:
        a('<tr><td class="k">%s</td><td class="num">%.2f</td><td>%s</td><td class="num">%.2f</td>'
          '<td>%s</td><td class="num">%.2f%%</td></tr>' % (d, r, pct(rg), p, pct(pg), gm))
    a('</table>')
    a('<h3>单季口径（关键）</h3>')
    a('<table><tr><th>单季</th><th>营收(万)</th><th>同比</th><th>归母净利(万)</th><th>同比</th></tr>')
    for d, r, rg, p, pg in QTR:
        hl = ' style="background:#fdf9f1"' if d == "2026Q2" else ''
        a('<tr%s><td class="k">%s</td><td class="num">%.2f</td><td>%s</td><td class="num">%.2f</td>'
          '<td>%s</td></tr>' % (hl, d, r, pct(rg), p, pct(pg)))
    a('</table>')
    a('<div class="note warn"><b>核心矛盾：利润增长不是主业挣来的。</b>'
      '2026H1 毛利率 23.45%（比去年同期 25.89% 还降了 2.4 个百分点），'
      '毛利仅 1013 万，营业利润却有 2507 万——'
      '多出来的约 1494 万来自<b>投资收益／公允价值变动</b>，占营业利润近 60%。'
      '换句话说，主业（酒类批发＋物业租赁＋洗染）在萎缩，'
      '报表利润靠投资端撑着，这种增长<b>不可持续、不可预测</b>。</div>')
    a('<h3>质量与估值</h3>')
    a('<table><tr><th>指标</th><th>数值</th><th>解读</th></tr>'
      '<tr><td class="k">ROE（TTM）</td><td class="num">3.00%</td>'
      '<td class="desc">极低，低于一年期定存，不具备价值创造能力</td></tr>'
      '<tr><td class="k">营收 3 年复合</td><td class="num dn">-1.72%</td>'
      '<td class="desc">主业持续收缩</td></tr>'
      '<tr><td class="k">归母净利 3 年复合</td><td class="num dn">-10.47%</td>'
      '<td class="desc">盈利中枢下移</td></tr>'
      '<tr><td class="k">市销率（TTM）</td><td class="num">36.1 倍</td>'
      '<td class="desc">33.87 亿市值 ÷ 0.94 亿营收，定价完全脱离经营</td></tr>'
      '<tr><td class="k">机构一致预期</td><td class="num">无</td>'
      '<td class="desc">零券商覆盖，无任何盈利预测</td></tr></table>')
    a('</section>')

    # 股东结构
    a('<section><h2>股东结构与内部人行为</h2>')
    a('<p class="lead">与青木科技最关键的差异：<b>控股股东和董监高都没有减持</b>，'
      '但机构也完全没有参与。</p>')
    a('<table><tr><th>股东</th><th>持股比例</th><th>本期变动</th><th>性质</th></tr>')
    for nm, p_, ch, nat in HOLD:
        cls = "dn" if ch.startswith("-") else ("up" if ch.startswith("+") else "fl")
        a('<tr><td class="k">%s</td><td class="num">%.2f%%</td><td class="%s">%s</td>'
          '<td class="desc">%s</td></tr>' % (nm, p_, cls, ch if ch != "0" else "持平", nat))
    a('</table>')
    a('<div class="cards">')
    a('<div class="card cold"><div class="t">国资控股</div><div class="v">34.43%</div>'
      '<div class="d">上海新南西集团 25.66% ＋ 静安资本 6.93% ＋ 百联集团 1.84%，'
      '均<b>未减持</b>。实控人为上海市静安区国资。</div></div>')
    a('<div class="card cold"><div class="t">风险项</div><div class="v">零瑕疵</div>'
      '<div class="d">股权质押：无 · 限售解禁：无 · 诉讼：无 · '
      '董监高减持：无。风险评分 82.46（越高越安全）。</div></div>')
    a('<div class="card hot"><div class="t">机构参与度</div><div class="v">完全缺席</div>'
      '<div class="d">前十股东中<b>零公募基金、零社保、零北向</b>；'
      '唯一在列的南方中证全指房地产 ETF 减持 115.56 万股。'
      '持仓全是自然人＋国资，典型的游资／散户定价。</div></div>')
    a('</div>')
    a('<div class="note"><b>股东户数减少 16.2%</b>（2026 中报口径），筹码在集中，'
      '配合 8 月底放量突破，说明有资金在低位收集。'
      '但收集主体是游资而非机构，稳定性差——这也解释了为什么资金评分只有 46.76。</div>')
    a('<div class="note"><b>治理变动：</b>2026 年 4 名监事离任，原因为「取消监事会」，'
      '属新《公司法》下的常规治理调整（改设审计委员会），<b>非负面事件</b>。</div>')
    a('</section>')

    # 资金面
    a('<section><h2>资金面：板块强势，个股却在流出</h2>')
    a('<p class="lead">这是本次调研最需要警惕的背离：板块资金极强，但个股主力今日在出货。</p>')
    a('<h3>主力净流入（万元）</h3>')
    a(flow_chart(FLOW))
    a('<table><tr><th>口径</th><th>净流入(万)</th><th>解读</th></tr>'
      '<tr><td class="k">今日</td><td class="num dn">-1,666</td>'
      '<td class="desc">超大单 −1,236 万、大单 −430 万；中单 +678 万、小单 +989 万'
      '——<b>大资金出、散户接</b></td></tr>'
      '<tr><td class="k">近 5 日</td><td class="num up">+1,683</td>'
      '<td class="desc">流入已大幅衰减</td></tr>'
      '<tr><td class="k">近 10 日</td><td class="num up">+7,285</td>'
      '<td class="desc">这是 8/28 那根放量突破阳线带来的</td></tr>'
      '<tr><td class="k">近 20 日</td><td class="num up">+6,856</td>'
      '<td class="desc">弱于 10 日，说明最近 10 天是<b>净流出回吐</b></td></tr></table>')
    a('<div class="note warn"><b>「先拉后出」迹象。</b>近 5 个交易日主力资金进出完全交替：'
      '8/28 +1838 万 → 8/31 −1600 万 → 9/1 −1616 万 → 9/2 +1642 万 → 9/3 −1666 万。'
      '这种高频对倒不是机构建仓的形态，是<b>游资边打边撤</b>。'
      '同时该股主力净流入全市场排名 4861 位，属资金关注度极低的尾部标的。</div>')
    a('<h3>融资余额（亿元）· 杠杆资金持续加仓</h3>')
    a(margin_chart(MARGIN))
    a('<table><tr><th>项目</th><th>数值</th><th>解读</th></tr>'
      '<tr><td class="k">融资余额（9/2）</td><td class="num">1.776 亿</td>'
      '<td class="desc">占流通市值 <b>5.24%</b>，属偏高水平</td></tr>'
      '<tr><td class="k">7 日变化</td><td class="num up">+1,460 万 (+9.0%)</td>'
      '<td class="desc">8/24 的 1.631 亿 → 9/2 的 1.776 亿</td></tr>'
      '<tr><td class="k">单日峰值</td><td class="num">8/26 买入 3,830 万</td>'
      '<td class="desc">杠杆资金在突破当天集中涌入</td></tr>'
      '<tr><td class="k">融券余额</td><td class="num">24.1 万</td>'
      '<td class="desc">可忽略，无做空压力</td></tr></table>')
    a('<div class="note warn"><b>杠杆资金拥挤是双刃剑。</b>融资盘在 8 月底集中涌入推高了股价，'
      '但一旦股价跌破融资成本区，平仓盘会放大跌幅。'
      '<b>把「融资余额见顶回落」作为离场信号之一。</b></div>')
    a('<h3>诊股五维评分</h3>')
    a('<table><tr><th>维度</th><th>评分</th><th>周变动</th><th>条</th></tr>')
    for nm, v, c in SCORE:
        col = "#b8332a" if v >= 70 else "#b8893b"
        a('<tr><td class="k">%s</td><td class="num">%.2f</td><td class="%s">%+.2f</td>'
          '<td><span class="bar"><i style="width:%.0f%%;background:%s"></i></span></td></tr>'
          % (nm, v, "up" if c >= 0 else "dn", c, v, col))
    a('</table>')
    a('<div class="note warn"><b>资金评分周内暴跌 −39.14、技术评分 −11.06</b>，'
      '而同期股价是涨的（周涨幅 +2.9% 到周收盘 8.60）。'
      '量价与评分背离，是短线见顶的常见前兆。</div>')
    a('</section>')

    # 板块背景
    a('<section><h2>板块背景：全市场资金第 2 强（唯一硬支撑）</h2>')
    s = SECT
    a('<p class="lead">所属申万二级行业「一般零售」在 2026-09-03 的资金排行中表现极为突出，'
      '这是本次调研中<b>最强的正面因素</b>。</p>')
    a('<div class="cards">')
    a('<div class="card hot"><div class="t">5 日主力净流入排名</div>'
      '<div class="v">第 %d / %d 名</div><div class="d">申万二级行业资金排行，'
      '仅次于航空装备Ⅱ。板块层面资金极强。</div></div>' % (s["rank"], s["total"]))
    a('<div class="card hot"><div class="t">5 日主力净流入</div>'
      '<div class="v">+14.72 亿</div><div class="d">20 日累计 <b>+21.33 亿</b>，'
      '是持续性的资金流入，不是一日游。</div></div>')
    a('<div class="card"><div class="t">当日表现</div>'
      '<div class="v">+0.09% · 20/60 上涨</div><div class="d">指数几乎平盘，'
      '但主力净流入 +6.15 亿——<b>资金在板块内做结构性切换</b>，不是普涨。</div></div>')
    a('<div class="card"><div class="t">板块龙头</div>'
      '<div class="v">%s</div><div class="d">板块换手率 3.03%%，'
      '个股 5.74%% —— 本股活跃度约为板块的 1.9 倍。</div></div>' % s["leader"])
    a('</div>')
    a('<div class="note"><b>催化剂：</b>① 公司层面——洗染业务扩张放量；'
      '② 政策层面——促消费政策密集落地，零售板块打开增量空间；'
      '③ 地产层面——房贷期限延长至 40 年、支持房企并购重组，利好商业物业估值重估；'
      '④ 隐含预期——上海静安区国资背景带来的资产注入／重组想象空间'
      '（这也是 33.87 亿市值配 72 倍 PE 的唯一解释）。</div>')
    a('<div class="note warn"><b>但要注意背离：</b>板块 5 日净流入全市场第 2，'
      '而本股同期主力净流入排名 4861 位、今日净流出 1666 万。'
      '<b>板块强不等于这只票强</b>——它既不是板块龙头（龙头是百大集团），'
      '也没有跟上板块资金，属于「搭车但没上车」的位置。</div>')
    a('</section>')

    # 七条标准
    a('<section><h2>个股筛选七条标准对照</h2>')
    a('<p class="lead">按既定框架逐条打分：<b>1.5 / 7 通过</b>'
      '（部分符合按 0.5 计），低于青木科技的 3/7。</p>')
    a('<table><tr><th>标准</th><th>判定</th><th>依据</th></tr>')
    for nm, k, d in RULE:
        a('<tr><td class="k">%s</td><td>%s</td><td class="desc">%s</td></tr>' % (nm, tag(k), d))
    a('</table>')
    a('<div class="note"><b>结论：它不是「高胜率标的」，是「高赔率博弈品」。</b>'
      '唯一的加分项是板块资金（一般零售全市场第 2），'
      '但个股层面在趋势、机构、业绩、壁垒四条上全部不合格。'
      '这类标的的正确用法是<b>小仓位、短周期、严格止损</b>，'
      '而不是中线持有等增值。</div>')
    a('</section>')

    # 操作规则
    a('<section><h2>操作规则与风控</h2>')
    a('<table><tr><th>周期</th><th>规则</th><th>触发条件</th></tr>'
      '<tr><td class="k">短线</td>'
      '<td class="desc">不追高。<b>回踩 7.82–8.00 不破</b>可轻仓介入；'
      '跌破 7.82（布林中轨）立即离场。</td>'
      '<td class="desc">突破 8.82 需<b>放量确认</b>（换手率 &gt; 7%），'
      '否则视为假突破</td></tr>'
      '<tr><td class="k">中线</td>'
      '<td class="desc">以三季报（10 月底）为裁判。'
      '见到<b>单季营收回正 + 洗染收入兑现</b>才加仓。</td>'
      '<td class="desc">三季报营收继续负增长 → 中线逻辑瓦解，清仓</td></tr>'
      '<tr><td class="k">长线</td>'
      '<td class="desc">不作增值底仓。'
      '仅在<b>国资重组／资产注入明确公告</b>时作为事件驱动参与。</td>'
      '<td class="desc">重组预期证伪或长期无进展 → 不参与</td></tr>'
      '<tr><td class="k">仓位</td>'
      '<td class="desc">建议不超过总仓位 <b>5%</b>。</td>'
      '<td class="desc">依据：曾单周换手 116.73%，波动率极高</td></tr>'
      '<tr><td class="k">止损</td>'
      '<td class="desc">第一止损 7.82（布林中轨，−7.5%）；'
      '绝对止损 7.40（8 月平台上沿，−12.4%）。</td>'
      '<td class="desc">6.49（52 周低）破位无条件清仓</td></tr></table>')
    a('<div class="note warn"><b>技术面当前状态（2026-09-03）：</b>'
      'MACD 在零轴上方金叉但柱体连续 4 日缩短（0.2477→0.2211→0.2306→0.2234→0.1814）；'
      'KDJ 的 K=82.5、D=80.2、J=87.0 高位钝化且 J 值已从 98.3 回落；'
      'RSI6 从 81.9 快速回落到 61.9。'
      '<b>趋势未坏，但动能已经转弱——这正是「不追高」的技术依据。</b></div>')
    a('</section>')

    # 验证清单
    a('<section><h2>每日验证清单</h2>')
    a('<p class="lead">持有期间每日收盘后逐项核对，任一项转负即减仓。</p>')
    a('<ul class="chk">')
    for t in [
        "主力资金：连续 3 日净流出 → 减仓一半（今日已 −1666 万，记 1 次）",
        "融资余额：当前 1.776 亿。见顶连续回落 2 日 → 杠杆退潮，减仓",
        "板块（一般零售）5 日主力净流入：是否仍保持全市场前 10。当前第 2 / +14.72 亿",
        "价格：是否守住 7.82（布林中轨）。跌破 → 清仓",
        "换手率：突破需 &gt; 7% 才算有效；健康回调应 &lt; 4%；若高位换手 &gt; 10% 而股价不涨 → 出货",
        "量比：当前 0.76（缩量）。放量突破需量比 &gt; 1.5",
        "板块内地位：是否成为一般零售板块领涨股。当前龙头是百大集团，本股为跟随",
    ]:
        a('<li>%s</li>' % t)
    a('</ul></section>')

    a('<footer>数据来源：腾讯自选股（westock-mcp），收盘口径 2026-09-03，'
      '生成于 2026-09-04。本报告为研究记录，不构成投资建议。</footer>')
    a('</div></body></html>')
    return "\n".join(P)

html = build()
with io.open(OUT, "w", encoding="utf-8") as f:
    f.write(html)
print("OK ->", OUT, len(html), "chars")
