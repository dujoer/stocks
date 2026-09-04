# -*- coding: utf-8 -*-
"""
青木科技(sz301110) 三周期调研报告生成器
数据源：westock-mcp（quote/kline/technical/finance/score/consensus/rating/
        shareholder/fund_flow/fund_margin/risk/dividend/news/sector）
口径日：2026-09-03 收盘
输出：web/research-301110-20260904.html（自包含、浅色、全中文标签、红涨绿跌）
"""
import os
from _nav import selfcontained_nav

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "web",
                   "research", "research-301110-20260904.html")
OUT = os.path.normpath(OUT)

# ---------------- 数据区（全部来自实测接口） ----------------
NAME, CODE = "青木科技", "sz301110"
PRICE, PREV = 36.25, 36.85
CHG_PCT = -1.63

# 近 59 个交易日收盘（前复权，正序）
CLOSES = [
    ("06-12", 38.94), ("06-15", 40.07), ("06-16", 40.13), ("06-17", 39.18),
    ("06-18", 39.47), ("06-22", 40.33), ("06-23", 39.01), ("06-24", 39.59),
    ("06-25", 38.11), ("06-26", 36.44), ("06-29", 37.68), ("06-30", 37.86),
    ("07-01", 38.63), ("07-02", 39.45), ("07-03", 39.52), ("07-06", 38.26),
    ("07-07", 38.65), ("07-08", 37.70), ("07-09", 37.47), ("07-10", 36.67),
    ("07-13", 34.30), ("07-14", 34.40), ("07-15", 35.45), ("07-16", 36.25),
    ("07-17", 35.35), ("07-20", 34.32), ("07-21", 33.85), ("07-22", 33.03),
    ("07-23", 32.88), ("07-24", 31.59), ("07-27", 32.81), ("07-28", 34.99),
    ("07-29", 35.32), ("07-30", 34.62), ("07-31", 36.60), ("08-03", 36.20),
    ("08-04", 37.50), ("08-05", 38.43), ("08-06", 38.01), ("08-07", 37.62),
    ("08-10", 38.00), ("08-11", 37.55), ("08-12", 37.29), ("08-13", 37.28),
    ("08-14", 37.48), ("08-17", 38.00), ("08-18", 36.81), ("08-19", 34.15),
    ("08-20", 35.07), ("08-21", 34.90), ("08-24", 33.65), ("08-25", 34.51),
    ("08-26", 34.53), ("08-27", 34.53), ("08-28", 35.00), ("08-31", 35.37),
    ("09-01", 37.88), ("09-02", 36.85), ("09-03", 36.25),
]

# 财务：报告期 / 营收亿 / 营收YoY / 归母净利亿 / 净利YoY / 毛利率 / 净利率 / ROE
FIN = [
    ("2025Q1",   2.745, 21.28, 0.100, -58.56, 52.25,  3.55, 0.70),
    ("2025中报", 6.681, 22.75, 0.517, -22.96, 57.03,  7.17, 3.61),
    ("2025三季", 10.207, 26.34, 0.796, 10.22, 56.33,  7.28, 5.46),
    ("2025年报", 14.148, 22.69, 1.230, 35.90, 55.27,  8.39, 8.19),
    ("2026Q1",   3.433, 25.07, 0.421, 320.53, 54.65, 12.32, 2.73),
    ("2026中报", 7.289,  9.10, 0.867, 67.90, 57.59, 11.53, 5.59),
]

# 单季拆分：季度 / 营收亿 / 营收YoY / 净利亿 / 净利YoY
QTR = [
    ("2025年二季度", 3.936, None,   0.416, None),
    ("2026年一季度", 3.433, 25.07,  0.421, 320.53),
    ("2026年二季度", 3.856, -2.04,  0.446, 7.13),
]

# 一致预期：年份 / EPS / 营收亿 / 营收YoY / 净利亿 / 净利YoY / PE
CONSENSUS = [
    (2026, 1.40, 16.995, 20.12, 1.812, 47.22, 26.36),
    (2027, 1.83, 20.121, 18.39, 2.370, 30.86, 20.16),
    (2028, 2.28, 23.351, 16.05, 2.958, 24.78, 16.15),
]

# 董事长减持：披露日 / 股数万 / 成交价(未复权) / 金额万
CHAIRMAN_SELL = [
    ("2025-12-29", 46.41, 59.68, 2769.4),
    ("2026-01-07", 38.43, 61.08, 2347.1),
    ("2026-01-08", 26.10, 61.08, 1594.2),
    ("2026-01-09", 53.75, 69.03, 3710.4),
    ("2026-01-12", 44.96, 91.09, 4094.4),
    ("2026-01-13", 21.64, 98.87, 2139.6),
    ("2026-01-14",  9.05, 92.50,  837.1),
    ("2026-01-16",  3.85, 79.00,  304.2),
    ("2026-01-19",  1.65, 75.31,  124.3),
    ("2026-01-20",  0.71, 77.14,   54.8),
]

# 资金流：日期 / 主力净额万 / 散户净额万
FLOW = [
    ("08-21",  -182.2,  -25.4),
    ("08-24",  -315.7,  468.5),
    ("08-25",    18.8,  241.2),
    ("08-26",   550.1, -451.5),
    ("08-27",   -19.6,  -19.7),
    ("08-28",  1791.7, -2241.9),
    ("08-31",  -344.7,  -55.7),
    ("09-01",  1422.6, -1946.5),
    ("09-02", -1513.4,  1590.0),
    ("09-03",  -947.7,  1077.3),
]

# 板块：名称 / 当日涨跌 / 主力亿 / 5日亿 / 20日亿 / 广度
SECTORS = [
    ("AI营销",     -1.19, -14.15,  -1.03,  -89.41, "2/36"),
    ("AI智能体",   -0.50,   0.03,  24.63,   -7.45, "7/26"),
    ("电商概念",   -0.66,  -5.25,  33.09,  -57.65, "100/352"),
    ("跨境电商概念", -0.60, -7.93,  36.67, -131.45, "94/314"),
    ("AI应用",     -0.84,  -7.87,  -5.05,  -89.95, "14/49"),
]

# 诊股评分：维度 / 分值 / 月变动
SCORES = [
    ("基本面", 85.18, -3.11),
    ("技术面", 83.22, 38.30),
    ("综合",   77.64,  3.97),
    ("风险",   67.41,  0.12),
    ("资金面", 58.99,  7.95),
]

# 七条筛选标准对照
RULES = [
    ("强趋势",          "no",   "年线级下跌未反转，年内 −22.85%，距 1 月高点 −51.9%，仅日线级反弹"),
    ("相对低位",        "yes",  "52 周区间 31.20–75.36，现价处于下半区，回购均价 34.30 形成参考底"),
    ("量价健康",        "yes",  "9/1 放量突破（换手 9.33%）后连续两日缩量回踩，量比 0.76，未见放量派发"),
    ("机构主导",        "no",   "仅 1 家机构覆盖；养老金组合推算减持约 13.7%；9/2–9/3 主力净流出、散户接盘"),
    ("订单/业绩可验证", "part", "毛利率 57.59%、净利率 11.53% 改善为真；但二季度营收同比 −2.04%，增长动能待三季报验证"),
    ("瓶颈环节",        "no",   "电商代运营处于品牌与平台之间，议价权弱，非产业链瓶颈；AI 业务占比仅 6.23%"),
    ("换手适中",        "yes",  "换手 3.64%，处于 3%–15% 健康区间，无爆量特征"),
]

# ---------------- 绘图辅助 ----------------
def sparkline(data, w=1000, h=220, pad=28):
    vals = [v for _, v in data]
    lo, hi = min(vals), max(vals)
    span = hi - lo or 1
    n = len(vals)
    def X(i): return pad + i * (w - 2 * pad) / (n - 1)
    def Y(v): return pad + (hi - v) * (h - 2 * pad) / span
    pts = " ".join(f"{X(i):.1f},{Y(v):.1f}" for i, v in enumerate(vals))
    area = f"{pad},{h-pad} " + pts + f" {w-pad},{h-pad}"
    # 关键位横线
    lines = []
    for lv, lab, col in [(38.50, "颈线 38.50", "#b8332a"),
                         (36.14, "20日线 36.14", "#b8893b"),
                         (33.65, "8/24低 33.65", "#1a9e5a")]:
        if lo <= lv <= hi:
            y = Y(lv)
            lines.append(
                f'<line x1="{pad}" y1="{y:.1f}" x2="{w-pad}" y2="{y:.1f}" '
                f'stroke="{col}" stroke-width="1" stroke-dasharray="5 4" opacity=".55"/>'
                f'<text x="{w-pad-4}" y="{y-5:.1f}" text-anchor="end" font-size="11" '
                f'fill="{col}">{lab}</text>')
    marks = []
    for i, (d, v) in enumerate(data):
        if d in ("07-24", "08-24", "09-01", "09-03"):
            marks.append(
                f'<circle cx="{X(i):.1f}" cy="{Y(v):.1f}" r="4" fill="#fff" '
                f'stroke="#1c2430" stroke-width="2"/>'
                f'<text x="{X(i):.1f}" y="{Y(v)-11:.1f}" text-anchor="middle" '
                f'font-size="11" fill="#1c2430" font-weight="600">{v}</text>')
    return f'''<svg viewBox="0 0 {w} {h}" class="chart" role="img" aria-label="近三个月收盘走势">
<defs><linearGradient id="gp" x1="0" y1="0" x2="0" y2="1">
<stop offset="0%" stop-color="#b8893b" stop-opacity=".22"/>
<stop offset="100%" stop-color="#b8893b" stop-opacity="0"/></linearGradient></defs>
<polygon points="{area}" fill="url(#gp)"/>
{''.join(lines)}
<polyline points="{pts}" fill="none" stroke="#b8893b" stroke-width="2.2"
 stroke-linejoin="round"/>
{''.join(marks)}
<text x="{pad}" y="{h-8}" font-size="11" fill="#6b7280">{data[0][0]}</text>
<text x="{w-pad}" y="{h-8}" text-anchor="end" font-size="11" fill="#6b7280">{data[-1][0]}</text>
</svg>'''


def flow_chart(data, w=1000, h=210, pad=30):
    mx = max(max(abs(a), abs(b)) for _, a, b in data) or 1
    n = len(data)
    slot = (w - 2 * pad) / n
    bw = slot * 0.34
    mid = h / 2
    half = (h - 2 * pad) / 2
    out = [f'<line x1="{pad}" y1="{mid}" x2="{w-pad}" y2="{mid}" stroke="#d8dbe0" stroke-width="1"/>']
    for i, (d, main, small) in enumerate(data):
        cx = pad + slot * (i + 0.5)
        for k, (v, col) in enumerate([(main, "#b8332a" if main >= 0 else "#1a9e5a"),
                                      (small, "#c9a06a" if small >= 0 else "#7fbf9a")]):
            bh = abs(v) / mx * half
            x = cx - bw + k * bw
            y = mid - bh if v >= 0 else mid
            out.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bw-2:.1f}" '
                       f'height="{bh:.1f}" fill="{col}" rx="1.5"/>')
        out.append(f'<text x="{cx:.1f}" y="{h-8}" text-anchor="middle" font-size="10.5" '
                   f'fill="#6b7280">{d}</text>')
        out.append(f'<text x="{cx:.1f}" y="{mid - main/mx*half - 6 if main>=0 else mid - main/mx*half + 13:.1f}" '
                   f'text-anchor="middle" font-size="9.5" fill="#4b5563">{main:.0f}</text>')
    return f'<svg viewBox="0 0 {w} {h}" class="chart" role="img" aria-label="主力与散户资金流">{"".join(out)}</svg>'


def sell_chart(data, w=1000, h=250, pad=34):
    prices = [p for _, _, p, _ in data]
    lo, hi = min(prices) * 0.94, max(prices) * 1.04
    amts = [a for _, _, _, a in data]
    mxa = max(amts)
    n = len(data)
    slot = (w - 2 * pad) / n
    def Y(p): return pad + (hi - p) * (h - 2 * pad - 34) / (hi - lo)
    out = []
    for i, (d, sh, px, amt) in enumerate(data):
        cx = pad + slot * (i + 0.5)
        bh = amt / mxa * (h - 2 * pad - 40)
        out.append(f'<rect x="{cx-13:.1f}" y="{h-pad-24-bh:.1f}" width="26" '
                   f'height="{bh:.1f}" fill="#1a9e5a" opacity=".30" rx="2"/>')
        out.append(f'<text x="{cx:.1f}" y="{h-pad-24-bh-5:.1f}" text-anchor="middle" '
                   f'font-size="10" fill="#127a45">{amt:.0f}万</text>')
        out.append(f'<text x="{cx:.1f}" y="{h-pad+2:.1f}" text-anchor="middle" '
                   f'font-size="10" fill="#6b7280">{d[5:]}</text>')
    pts = " ".join(f"{pad+slot*(i+0.5):.1f},{Y(p):.1f}" for i, (_, _, p, _) in enumerate(data))
    out.append(f'<polyline points="{pts}" fill="none" stroke="#b8332a" stroke-width="2.2"/>')
    for i, (_, _, p, _) in enumerate(data):
        cx = pad + slot * (i + 0.5)
        out.append(f'<circle cx="{cx:.1f}" cy="{Y(p):.1f}" r="3.4" fill="#b8332a"/>')
        if p in (98.87, 59.68):
            out.append(f'<text x="{cx:.1f}" y="{Y(p)-9:.1f}" text-anchor="middle" '
                       f'font-size="10.5" fill="#b8332a" font-weight="600">{p}</text>')
    return f'<svg viewBox="0 0 {w} {h}" class="chart" role="img" aria-label="董事长减持价格与金额">{"".join(out)}</svg>'


def bar(pct, col):
    return (f'<span class="bar"><i style="width:{max(2,min(100,pct)):.0f}%;'
            f'background:{col}"></i></span>')


# ---------------- 组装 HTML ----------------
def sgn(v, unit="%"):
    cls = "up" if v > 0 else ("dn" if v < 0 else "fl")
    s = f"+{v:.2f}" if v > 0 else f"{v:.2f}"
    return f'<span class="{cls}">{s}{unit}</span>'


fin_rows = "".join(
    f"<tr><td class='k'>{p}</td><td>{r:.3f}</td><td>{sgn(ry)}</td>"
    f"<td>{np:.3f}</td><td>{sgn(ny)}</td><td>{gm:.2f}%</td>"
    f"<td>{nm:.2f}%</td><td>{roe:.2f}%</td></tr>"
    for p, r, ry, np, ny, gm, nm, roe in FIN)

qtr_rows = "".join(
    f"<tr><td class='k'>{q}</td><td>{r:.3f}</td>"
    f"<td>{'—' if ry is None else sgn(ry)}</td><td>{np:.3f}</td>"
    f"<td>{'—' if ny is None else sgn(ny)}</td></tr>"
    for q, r, ry, np, ny in QTR)

cons_rows = "".join(
    f"<tr><td class='k'>{y} 年预测</td><td>{eps:.2f}</td><td>{rev:.3f}</td>"
    f"<td>{sgn(ry)}</td><td>{npf:.3f}</td><td>{sgn(ny)}</td><td>{pe:.2f}</td></tr>"
    for y, eps, rev, ry, npf, ny, pe in CONSENSUS)

sec_rows = "".join(
    f"<tr><td class='k'>{n}</td><td>{sgn(c)}</td>"
    f"<td class='{'up' if m>=0 else 'dn'}'>{m:+.2f}</td>"
    f"<td class='{'up' if f5>=0 else 'dn'}'>{f5:+.2f}</td>"
    f"<td class='{'up' if f20>=0 else 'dn'}'>{f20:+.2f}</td><td>{b}</td></tr>"
    for n, c, m, f5, f20, b in SECTORS)

score_rows = "".join(
    f"<tr><td class='k'>{n}</td><td class='num'>{v:.2f}</td>"
    f"<td>{bar(v, '#b8893b' if v>=75 else ('#c98b3b' if v>=65 else '#8a9099'))}</td>"
    f"<td>{sgn(c, '')}</td></tr>"
    for n, v, c in SCORES)

ICON = {"yes": ("符合", "ok"), "no": ("不符合", "bad"), "part": ("部分符合", "mid")}
rule_rows = "".join(
    f"<tr><td class='k'>{i+1}. {n}</td>"
    f"<td><span class='tag {ICON[s][1]}'>{ICON[s][0]}</span></td>"
    f"<td class='desc'>{d}</td></tr>"
    for i, (n, s, d) in enumerate(RULES))

total_sell_sh = sum(s for _, s, _, _ in CHAIRMAN_SELL)
total_sell_amt = sum(a for _, _, _, a in CHAIRMAN_SELL)

NAV = selfcontained_nav("research", home="../../index.html")
HTML = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>青木科技（301110）三周期调研 · 2026-09-03 收盘口径</title>
<style>
:root{{
  --bg:#f5f6f8; --card:#ffffff; --ink:#1c2430; --ink2:#23262b; --sub:#6b7280;
  --line:#e5e7eb; --gold:#b8893b; --red:#b8332a; --green:#1a9e5a;
}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--ink2);
  font:15px/1.75 -apple-system,"PingFang SC","Microsoft YaHei",sans-serif}}
.wrap{{max-width:1080px;margin:0 auto;padding:28px 20px 64px}}
header{{background:var(--card);border:1px solid var(--line);border-radius:14px;
  padding:24px 26px;margin-bottom:18px}}
h1{{margin:0 0 4px;font-size:24px;color:var(--ink);letter-spacing:-.2px}}
.sub{{color:var(--sub);font-size:13px}}
.px{{display:flex;align-items:baseline;gap:12px;margin:14px 0 4px}}
.px b{{font-size:38px;color:var(--ink);font-weight:700;letter-spacing:-1px}}
.kv{{display:grid;grid-template-columns:repeat(auto-fit,minmax(132px,1fr));
  gap:10px;margin-top:16px}}
.kv div{{background:#fafbfc;border:1px solid var(--line);border-radius:9px;
  padding:9px 12px}}
.kv span{{display:block;color:var(--sub);font-size:11.5px}}
.kv b{{font-size:16px;color:var(--ink);font-weight:600}}
section{{background:var(--card);border:1px solid var(--line);border-radius:14px;
  padding:22px 26px;margin-bottom:18px}}
h2{{margin:0 0 6px;font-size:18px;color:var(--ink);
  border-left:3px solid var(--gold);padding-left:10px}}
h3{{margin:22px 0 8px;font-size:15px;color:var(--ink)}}
p{{margin:8px 0}}
.lead{{color:var(--sub);font-size:13.5px;margin:0 0 16px;padding-left:13px}}
table{{width:100%;border-collapse:collapse;font-size:13.5px;margin:10px 0}}
th,td{{padding:9px 10px;border-bottom:1px solid var(--line);text-align:right}}
th{{background:#fafbfc;color:var(--sub);font-weight:600;font-size:12.5px;
  text-align:right;white-space:nowrap}}
th:first-child,td:first-child{{text-align:left}}
td.k{{color:var(--ink);font-weight:600;white-space:nowrap}}
td.desc{{text-align:left;color:#4b5563;font-size:13px;line-height:1.65}}
td.num{{font-variant-numeric:tabular-nums;font-weight:600;color:var(--ink)}}
tr:last-child td{{border-bottom:none}}
.up{{color:var(--red);font-weight:600}} .dn{{color:var(--green);font-weight:600}}
.fl{{color:var(--sub)}}
.chart{{width:100%;height:auto;display:block;margin:14px 0 6px}}
.bar{{display:inline-block;width:120px;height:7px;background:#eef0f3;
  border-radius:4px;overflow:hidden;vertical-align:middle}}
.bar i{{display:block;height:100%;border-radius:4px}}
.tag{{display:inline-block;padding:2px 9px;border-radius:20px;font-size:11.5px;
  font-weight:600;white-space:nowrap}}
.tag.ok{{background:#e8f5ee;color:#127a45}}
.tag.bad{{background:#fbeceb;color:#a02b23}}
.tag.mid{{background:#fdf3e3;color:#9a6c25}}
.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));
  gap:14px;margin:14px 0}}
.card{{border:1px solid var(--line);border-radius:11px;padding:16px 17px;
  background:#fafbfc}}
.card .t{{font-size:12.5px;color:var(--sub);margin-bottom:6px}}
.card .v{{font-size:17px;font-weight:700;color:var(--ink);margin-bottom:6px}}
.card .d{{font-size:12.5px;color:#4b5563;line-height:1.6}}
.card.hot{{border-color:#e6c9a3;background:#fdfaf5}}
.card.warn{{border-color:#f0cdc9;background:#fdf6f5}}
.note{{background:#fdfaf5;border:1px solid #ecd9bb;border-radius:10px;
  padding:14px 17px;margin:14px 0;font-size:13.5px;color:#5b4526}}
.note b{{color:#8a6420}}
.alert{{background:#fdf5f4;border:1px solid #f0cdc9;border-radius:10px;
  padding:14px 17px;margin:14px 0;font-size:13.5px;color:#7d2f28}}
.alert b{{color:#a02b23}}
ul{{margin:8px 0;padding-left:20px}} li{{margin:5px 0}}
.legend{{font-size:12px;color:var(--sub);margin-top:2px}}
.legend i{{display:inline-block;width:10px;height:10px;border-radius:2px;
  margin:0 4px 0 12px;vertical-align:-1px}}
footer{{color:var(--sub);font-size:12px;text-align:center;padding:22px 10px;
  line-height:1.8}}
.lvl{{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));
  gap:10px;margin:12px 0}}
.lvl div{{border:1px solid var(--line);border-radius:9px;padding:11px 13px;
  background:#fafbfc;font-size:13px}}
.lvl b{{display:block;font-size:15px;color:var(--ink)}}
.lvl s{{display:block;color:var(--sub);font-size:11.5px;text-decoration:none}}
</style>
</head>
<body><div class="wrap">
{NAV}
<header>
  <h1>青木科技 · 301110</h1>
  <div class="sub">全域电商代运营 + AI 智能营销 · 商贸零售 · 创业板 · 数据口径 2026-09-03 收盘</div>
  <div class="px"><b>{PRICE}</b>{sgn(CHG_PCT)}<span class="sub">前收 {PREV}</span></div>
  <div class="kv">
    <div><span>市盈率（TTM）</span><b>29.70</b></div>
    <div><span>市净率</span><b>3.03</b></div>
    <div><span>总市值</span><b>46.96 亿</b></div>
    <div><span>流通市值</span><b>33.03 亿</b></div>
    <div><span>股息率</span><b>0.79%</b></div>
    <div><span>换手率</span><b>3.64%</b></div>
    <div><span>量比</span><b>0.76</b></div>
    <div><span>年内涨跌</span><b class="dn">−22.85%</b></div>
    <div><span>52 周区间</span><b>31.20 – 75.36</b></div>
    <div><span>距 52 周高点</span><b class="dn">−51.9%</b></div>
  </div>
</header>

<section>
  <h2>三周期结论</h2>
  <p class="lead">同一家公司在不同持有周期下的结论完全不同，核心分歧点在于「二季度增长熄火」与「董事长顶部套现」两条事实。</p>
  <div class="cards">
    <div class="card hot">
      <div class="t">短线 · 数日至数周</div>
      <div class="v">可参与，但只做回踩不追高</div>
      <div class="d">技术面刚完成零轴下方金叉 + 放量突破后缩量回踩，形态健康；但主力已连续两日净流出、散户在接盘，缺乏板块共振。属于「形态可做、资金不配合」的博弈型机会。</div>
    </div>
    <div class="card">
      <div class="t">中线 · 数周至数月</div>
      <div class="v">有条件持有，三季报是唯一裁判</div>
      <div class="d">毛利率 57.59%、净利率 11.53% 双创新高是真实改善；但二季度单季营收同比 −2.04%。中线成立的前提是 10 月底三季报营收增速回正、AI 业务继续放量。</div>
    </div>
    <div class="card warn">
      <div class="t">长线 · 数年</div>
      <div class="v">不适合作为「增值持有」核心仓位</div>
      <div class="d">三条硬伤：董事长在历史最高区精准套现约 1.80 亿；全市场仅 1 家机构覆盖；代运营模式夹在品牌与平台之间、缺乏议价权。可作小仓位成长股观察，不宜重仓长拿。</div>
    </div>
  </div>
</section>

<section>
  <h2>一、价格结构与关键位</h2>
  <p class="lead">1 月高点 75.36 起算跌幅 −58.6%，7/24 见底 31.59，8/24 回落至 33.65 未破前低 —— 低点被抬高，双底雏形成立，但颈线尚未突破。</p>
  {sparkline(CLOSES)}
  <div class="legend">标注点为 7/24 阶段低、8/24 抬高低点、9/1 放量突破高点、9/3 缩量回踩收盘</div>
  <h3>关键价位（按强弱排序）</h3>
  <div class="lvl">
    <div><s>第一阻力</s><b>37.88</b>9/1 突破日最高收盘</div>
    <div><s>颈线 · 关键</s><b>38.47 – 38.56</b>突破才确认双底成立</div>
    <div><s>第二阻力</s><b>40.50</b>7 月初平台</div>
    <div><s>近端支撑</s><b>36.14</b>20 日线 / 布林中轨</div>
    <div><s>次级支撑</s><b>35.37</b>8/31 起涨点</div>
    <div><s>止损位</s><b>33.65</b>8/24 抬高低点，破位形态失效</div>
    <div><s>生命线</s><b>31.20</b>7 月低点，跌破则趋势重启</div>
  </div>
  <h3>技术指标（9/3）</h3>
  <table>
    <tr><th>指标</th><th>数值</th><th>状态</th></tr>
    <tr><td class="k">MACD</td><td>DIF −0.1219 / DEA −0.3089 / 柱 +0.374</td>
        <td class="desc">9/1 零轴下方金叉，柱体连续三日为正，DIF 上攻零轴</td></tr>
    <tr><td class="k">KDJ</td><td>K 61.30 / D 52.45 / J 79.00</td>
        <td class="desc">金叉延续，J 值未进超买区</td></tr>
    <tr><td class="k">RSI</td><td>6 日 53.82 / 12 日 51.53 / 24 日 48.54</td>
        <td class="desc">中性区，2 日 RSI 已回落至 38.80，短线过热消化完毕</td></tr>
    <tr><td class="k">布林带</td><td>上 39.04 / 中 36.14 / 下 33.23</td>
        <td class="desc">现价 36.25 刚站上中轨，中轨得失是短线分水岭</td></tr>
    <tr><td class="k">量能</td><td>9/1 换手 9.33% → 9/2 5.19% → 9/3 3.64%</td>
        <td class="desc">放量突破后缩量回踩，未见放量派发，形态偏健康</td></tr>
  </table>
</section>

<section>
  <h2>二、基本面：漂亮的半年报，熄火的二季度</h2>
  <p class="lead">中报归母净利同比 +67.90% 看似强劲，但增量全部来自去年一季度的低基数；把单季拆开，二季度营收已经同比转负。</p>
  <table>
    <tr><th>报告期</th><th>营业收入（亿）</th><th>同比</th><th>归母净利（亿）</th>
        <th>同比</th><th>毛利率</th><th>净利率</th><th>净资产收益率</th></tr>
    {fin_rows}
  </table>
  <h3>单季拆分 —— 核心矛盾所在</h3>
  <table>
    <tr><th>单季</th><th>营业收入（亿）</th><th>同比</th><th>归母净利（亿）</th><th>同比</th></tr>
    {qtr_rows}
  </table>
  <div class="alert">
    <b>关键结论：</b>2025 年一季度净利仅 1002 万元（同比 −58.56%），造成 2026 年一季度 +320.53% 的失真高增速。剔除基数效应后，2026 年二季度营收 3.856 亿、同比 <b>−2.04%</b>，净利同比仅 <b>+7.13%</b> —— 收入端增长已经停滞，利润增长完全靠毛利率与费用率改善支撑，而这条路的空间是有限的。
  </div>
  <h3>盈利质量</h3>
  <div class="cards">
    <div class="card"><div class="t">毛利率</div><div class="v">57.59%</div>
      <div class="d">历史高位。对代运营行业而言异常之高，说明收入结构偏「服务 + 技术」而非低毛利的经销分销，是这家公司最扎实的一项优势。</div></div>
    <div class="card"><div class="t">净利率</div><div class="v">11.53%</div>
      <div class="d">去年同期 7.17%，提升 4.36 个百分点。降本增效真实有效，但也意味着未来利润弹性将更依赖收入增长。</div></div>
    <div class="card"><div class="t">净资产收益率（TTM）</div><div class="v">10.19%</div>
      <div class="d">总资产收益率 8.39%、投入资本回报率 5.11%。三年净利复合增速 28.06%，三年营收复合增速 17.03%。</div></div>
    <div class="card warn"><div class="t">经营现金流转化率</div><div class="v">中报 27% / 滚动年 89%</div>
      <div class="d">滚动一年经营现金流 1.406 亿对应净利 1.581 亿，属健康；但中报单期仅 2344 万，一季度甚至为 −1539 万。存在季节性，须以三季报验证。</div></div>
  </div>
  <div class="note">
    <b>AI 转型进度：</b>2026 年上半年「AI 智能营销与技术服务」收入 <b>4543.44 万元</b>，占总营收 <b>6.23%</b>。这是市场给它挂上 AI 概念的依据，方向正确、有真实收入落地，但当前占比还不足以改变基本盘。观察阈值：占比突破 15%–20% 才构成第二增长曲线。
  </div>
</section>

<section>
  <h2>三、内部人行为：最强的一记警告</h2>
  <p class="lead">董事长吕斌在 2025-12-29 至 2026-01-20 期间连续十笔减持，时间窗口精准覆盖股价历史最高区间。</p>
  {sell_chart(CHAIRMAN_SELL)}
  <div class="legend">红线为各笔减持成交价（未复权，1 月未复权高点 98.87 对应前复权 75.36 顶部）<i style="background:#1a9e5a;opacity:.3"></i>绿柱为单笔套现金额</div>
  <div class="alert">
    <b>合计减持 {total_sell_sh:.2f} 万股，套现约 {total_sell_amt/10000:.2f} 亿元。</b>
    最后三笔的成交价 98.87 / 92.50 / 79.00 恰好落在 1 月 13 日历史大顶及其右侧。内部人在这个价位大规模离场，是对当时估值最直接的否定。这条记录不会因为现在股价腰斩而消失 —— 它定义了管理层的估值锚。
  </div>
  <h3>对冲信号（三条偏正面）</h3>
  <table>
    <tr><th>事项</th><th>内容</th><th>解读</th></tr>
    <tr><td class="k">高管底部增持</td><td>王广翠 7/14 增持 4.5 万股 @33.87、7/15 增持 3.0 万股 @35.24</td>
        <td class="desc">合计约 258 万元，金额小但方向为正，且买在阶段底部区域</td></tr>
    <tr><td class="k">公司回购</td><td>截至 9/1 累计回购约 44 万股，均价 34.30 元</td>
        <td class="desc">回购均价低于现价 5.4%，为 34 元一带提供了心理支撑位</td></tr>
    <tr><td class="k">连续分红</td><td>2023 年报 10 派 6 转 4、2024 中报 10 派 4、2024 年报 10 派 4、2025 年报 10 派 4 转 4</td>
        <td class="desc">四期连续现金分红，年度分红 3701 万元约占净利 23.4%，回报意愿明确</td></tr>
  </table>
  <h3>股东结构与风险项</h3>
  <table>
    <tr><th>项目</th><th>数据</th><th>评估</th></tr>
    <tr><td class="k">前两大股东</td><td>吕斌 18.78% / 卢彬 14.98%</td>
        <td class="desc">控制权集中稳定，无控制权争夺风险</td></tr>
    <tr><td class="k">社保资金</td><td>基本养老保险基金一六〇三二组合持 471.87 万股（3.64%）</td>
        <td class="desc">按 10 转 4 被动增幅应为 +40%，实际仅 +20.9%，<b>推算期内减持约 13.7%</b></td></tr>
    <tr><td class="k">股东户数</td><td>6/30 为 1.54 万户，较上期 +9.64%</td>
        <td class="desc">筹码趋于分散，通常对应散户化，略偏负面</td></tr>
    <tr><td class="k">股权质押</td><td>质押 275.8 万股，质押比例 2.13%</td>
        <td class="desc">极低，无平仓风险</td></tr>
    <tr><td class="k">限售解禁</td><td>2025-09-08 已完成解禁，近期无新增解禁</td>
        <td class="desc">无解禁抛压</td></tr>
    <tr><td class="k">诉讼 / 再融资</td><td>无诉讼记录，无增发计划</td>
        <td class="desc">无额外风险项</td></tr>
  </table>
</section>

<section>
  <h2>四、资金面：主力在撤，散户在接</h2>
  <p class="lead">9/1 的放量突破由大单主导，但随后两个交易日资金结构立刻反转 —— 这是短线最需要警惕的信号。</p>
  {flow_chart(FLOW)}
  <div class="legend"><i style="background:#b8332a"></i>主力净流入<i style="background:#1a9e5a"></i>主力净流出<i style="background:#c9a06a"></i>散户净流入<i style="background:#7fbf9a"></i>散户净流出　单位：万元</div>
  <ul>
    <li><b>9/1 突破日：</b>主力净流入 1422.6 万，大单 +603 万、机构席位 +820 万，散户净流出 1946 万 —— 大资金买、散户卖，是健康结构。</li>
    <li><b>9/2 至 9/3：</b>主力连续净流出 1513.4 万与 947.7 万，散户反而净流入 1590 万与 1077 万 —— <b>结构反转，主力派发给散户</b>。</li>
    <li><b>近 19 个交易日累计：</b>主力净流出约 830 万元，整体中性偏弱，无持续建仓迹象。</li>
    <li><b>杠杆水位：</b>融资余额 1.697 亿元，占流通市值 <b>5.14%</b>（创业板均值约 2%–3%），偏高。9/1 单日融资买入 3273 万元骤增，说明这波反弹有明显杠杆推动，回调时存在被动平仓压力。融券余额仅 23.6 万元，可忽略。</li>
  </ul>
  <h3>诊股五维评分</h3>
  <table>
    <tr><th>维度</th><th>分值</th><th>相对水平</th><th>近一月变动</th></tr>
    {score_rows}
  </table>
  <div class="note">
    评分结构印证了上面的判断：<b>基本面 85.18 分最强、资金面 58.99 分最弱</b>。技术面一个月内急升 38.30 分，说明这是一次由技术形态与业绩预期驱动、而非资金推动的修复。同时基本面评分月度小幅下滑 3.11 分，与二季度增速回落方向一致。
  </div>
</section>

<section>
  <h2>五、板块背景：没有主线级支撑</h2>
  <p class="lead">青木科技对应的概念群当日全线主力净流出，20 日口径全部大幅失血 —— 这轮上涨是个股行为，不是板块共振。</p>
  <table>
    <tr><th>概念板块</th><th>当日涨跌</th><th>主力净流入（亿）</th><th>5 日（亿）</th>
        <th>20 日（亿）</th><th>上涨家数 / 成分</th></tr>
    {sec_rows}
  </table>
  <ul>
    <li><b>AI 营销</b>是贴合度最高的概念，但当日 −1.19%、20 日主力净流出 89.41 亿、板块内仅 2/36 家上涨 —— 板块极弱，无法提供助力。</li>
    <li><b>AI 智能体</b>是唯一 5 日资金转正的（+24.63 亿），9/1 工信部相关表态曾带动板块走高，可作为短线情绪触发点观察。</li>
    <li><b>电商与跨境电商</b>概念 5 日资金转正（+33.09 亿、+36.67 亿），但 20 日仍分别失血 57.65 亿与 131.45 亿 —— 属于超跌后的短期回流，尚未形成趋势性资金进入。</li>
  </ul>
</section>

<section>
  <h2>六、对照个股筛选七条标准</h2>
  <p class="lead">用既有的选股框架逐条打分，避免主观印象干扰判断。</p>
  <table>
    <tr><th>标准</th><th>判定</th><th>依据</th></tr>
    {rule_rows}
  </table>
  <div class="alert">
    <b>七条中符合 3 条、部分符合 1 条、不符合 3 条。</b>按既定框架，这不是一只「高胜率标的」，而是一只「业绩改善 + 相对低位 + 待验证」的<b>观察级标的</b>。三条不符合项中，「强趋势」与「机构主导」两条恰恰是决定胜率的核心权重项。
  </div>
</section>

<section>
  <h2>七、估值与机构预期</h2>
  <p class="lead">静态估值已回落至上市以来偏低区域，但覆盖机构数量少到无法形成有效共识。</p>
  <table>
    <tr><th>预测年度</th><th>每股收益（元）</th><th>营业收入（亿）</th><th>同比</th>
        <th>归母净利（亿）</th><th>同比</th><th>对应市盈率</th></tr>
    {cons_rows}
  </table>
  <div class="cards">
    <div class="card"><div class="t">机构目标价</div><div class="v">47.25 元</div>
      <div class="d">较现价 36.25 有 +30.3% 空间</div></div>
    <div class="card warn"><div class="t">覆盖机构数量</div><div class="v">仅 1 家</div>
      <div class="d">评级家数 1、上调家数 1。样本量过小，上述预测无法视为市场共识，任何一次业绩不达预期都会导致预测被整体推翻</div></div>
    <div class="card"><div class="t">市盈率水位</div><div class="v">滚动 29.70 / 静态 38.17</div>
      <div class="d">动态市盈率 27.07。年内下跌 22.85% 已消化大部分估值泡沫</div></div>
    <div class="card"><div class="t">发行价对比</div><div class="v">发行价 63.10 元</div>
      <div class="d">现价较发行价折让 42.6%（未考虑两次转增与分红的复权影响）</div></div>
  </div>
</section>

<section>
  <h2>八、操作规则与风险控制</h2>
  <p class="lead">以下为条件化的交易规则，不是买入指令；每一条都带可观测的触发与失效条件。</p>
  <h3>短线（数日至数周）</h3>
  <ul>
    <li><b>不追高：</b>现价 36.25 位于 9/1 突破后的回踩过程中，且主力已连续两日净流出，直接追进的风险收益比不佳。</li>
    <li><b>观察买区：</b>36.14（20 日线 / 布林中轨）至 35.37 区间，需要满足<b>缩量止跌</b>（换手降至 3% 以下且不破中轨收盘）。</li>
    <li><b>加仓条件：</b>放量突破颈线 <b>38.56</b> 并站稳，才确认双底成立，届时才具备加仓依据。</li>
    <li><b>止损：</b>收盘跌破 <b>33.65</b>（8/24 抬高低点）即形态失效离场，从 36.25 计约 −7.2%。</li>
    <li><b>失效信号：</b>放量跌破 20 日线、或主力单日净流出超 2000 万元同时股价收阴。</li>
  </ul>
  <h3>中线（数周至数月）</h3>
  <ul>
    <li><b>持有前提（必须同时满足）：</b>① 10 月底三季报单季营收同比<b>回正</b>；② AI 智能营销收入环比继续放量；③ 经营现金流转化率修复至 50% 以上。</li>
    <li><b>目标区间：</b>42–47 元（对应 2026 年预测每股收益 1.40 元的 30–34 倍市盈率），机构目标价 47.25 位于该区间上沿。</li>
    <li><b>证伪条件：</b>三季报单季营收继续负增长，或毛利率跌破 55% —— 出现任一即降级为纯短线交易品种。</li>
  </ul>
  <h3>长线（数年）</h3>
  <ul>
    <li><b>不建议作为增值持有的核心仓位。</b>理由不在于估值，而在于：管理层已在高位用真金白银表达了对估值的态度；商业模式缺乏议价权；利润增长当前依赖降本而非规模扩张。</li>
    <li><b>重新评估的触发条件：</b>AI 智能营销收入占比突破 15%–20%、覆盖机构增至 5 家以上、连续两个季度营收与净利同步双位数增长。三条同时满足才值得讨论长期配置。</li>
  </ul>
  <h3>仓位纪律</h3>
  <div class="note">
    结合 15 万元总资金与 15% 最大回撤预算：本标的属于<b>小市值 + 杠杆盘偏高 + 有减持history的高波动品种</b>，单一标的建议控制在 <b>8%–12%（约 1.2 万 – 1.8 万元）</b>。以 33.65 止损计，单笔最大亏损对总账户影响约 −0.6% 至 −0.9%，处于安全范围。禁止无止损持仓，禁止在颈线未突破前加仓。
  </div>
</section>

<section>
  <h2>九、每日验证清单</h2>
  <p class="lead">这五项是判断上述结论是否仍然成立的可观测指标。</p>
  <table>
    <tr><th>观察项</th><th>当前值</th><th>看多确认</th><th>看空警示</th></tr>
    <tr><td class="k">20 日线 / 布林中轨</td><td>36.14（现价上方站住）</td>
        <td class="desc">连续收盘站稳中轨</td><td class="desc">放量收于中轨之下</td></tr>
    <tr><td class="k">颈线 38.47–38.56</td><td>未突破</td>
        <td class="desc">放量突破并回踩不破</td><td class="desc">二次冲击失败形成双头</td></tr>
    <tr><td class="k">主力资金净额</td><td>9/2、9/3 连续净流出</td>
        <td class="desc">连续两日净流入且散户净流出</td>
        <td class="desc">继续流出且散户持续净流入</td></tr>
    <tr><td class="k">融资余额占流通市值</td><td>5.14%（偏高）</td>
        <td class="desc">回落至 4% 以下且股价不跌</td>
        <td class="desc">突破 6% 后股价滞涨</td></tr>
    <tr><td class="k">三季报（10 月底）</td><td>待披露</td>
        <td class="desc">单季营收同比回正 + AI 收入放量</td>
        <td class="desc">营收继续负增长或毛利率跌破 55%</td></tr>
  </table>
</section>

<footer>
  数据来源：腾讯自选股（行情 / K 线 / 技术指标 / 财报 / 诊股 / 一致预期 / 股东 / 资金流 / 两融 / 风险事件 / 分红送转 / 板块），口径日 2026-09-03 收盘。<br>
  本页为基于公开数据的条件框架分析，所有结论均附带可观测的验证与失效条件，<b>不构成投资建议</b>。<br>
  生成时间 2026-09-04 · 青木科技（301110）三周期调研
</footer>

</div></body></html>
"""

os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, "w", encoding="utf-8") as f:
    f.write(HTML)
print("OK ->", OUT, len(HTML), "chars")
