# -*- coding: utf-8 -*-
"""psychology/index.html 刷到 09-09（16 期）：
1) 静态头部/统计 09-07(15期) -> 09-09(16期)
2) 中英词典 t_updated / s_risk_lbl / s_span_lbl 同步
3) 涨股比注记 / 情绪轨迹注记补 09-09 一行
4) SVG 涨股比走势图加入 09-09 (32%) 并重算 16 点坐标
"""
import io, sys

P = r"G:\ai\股票\web\psychology\index.html"
s = io.open(P, encoding="utf-8").read()
orig_len = len(s)
fails = []


def rep(old, new, tag):
    global s
    if old not in s:
        fails.append(tag)
        return
    s = s.replace(old, new, 1)


# ---------- 1) 静态头部 / 统计 ----------
rep("最近更新：2026-09-07（收录 08-17 ~ 09-07 共 15 期，08-22~08-23 与 08-29~08-30 周末休市）",
    "最近更新：2026-09-09（收录 08-17 ~ 09-09 共 16 期，08-22~08-23 与 08-29~08-30 周末休市）",
    "hdr-updated")
rep('<div class="num">15 <small data-i18n="s_issues">期</small></div>',
    '<div class="num">16 <small data-i18n="s_issues">期</small></div>',
    "stat-num")
rep("各期风险等级（13 期「高」+ 09-04、09-07 两期「中」）",
    "各期风险等级（13 期「高」+ 09-04、09-07、09-09 三期「中」）",
    "stat-risk")
rep("08-17<small> ~ 09-07</small>",
    "08-17<small> ~ 09-09</small>",
    "stat-span")

# ---------- 2) zh 词典 ----------
rep('t_updated:"最近更新：2026-09-07（收录 08-17 ~ 09-07 共 15 期，08-22~08-23 与 08-29~08-30 周末休市）",',
    't_updated:"最近更新：2026-09-09（收录 08-17 ~ 09-09 共 16 期，08-22~08-23 与 08-29~08-30 周末休市）",',
    "zh-updated")
rep('s_all:"全部", s_risk_lbl:"各期风险等级（13 期「高」+ 09-04、09-07 两期「中」）",',
    's_all:"全部", s_risk_lbl:"各期风险等级（13 期「高」+ 09-04、09-07、09-09 三期「中」）",',
    "zh-risk")
rep('s_span_lbl:"覆盖交易日跨度（08-22~08-23 与 08-29~08-30 周末休市；最新 09-07）",',
    's_span_lbl:"覆盖交易日跨度（08-22~08-23 与 08-29~08-30 周末休市；最新 09-09）",',
    "zh-span")

zh_trend = ('<div class="nrow"><span class="d">09-09</span><span class="r">涨股比 32%</span>'
            '<span class="t">缩量分化·短线退潮：创业板 −0.14% 翻绿、涨停 90→42 腰斩、跌停 0；橡胶 +4.07% / 航运港口 +3.86% 领涨，主线切换至橡胶/航运/资源；成交 ¥1.86万亿（−900亿）缩量，杠杆与主力仍集中于光模块/PCB，风险等级维持「中」。</span></div>\n')
rep('t_trend:"涨股比走势（市场广度）", t_trend_note:`<div class="nrow"><span class="d">09-07</span>',
    't_trend:"涨股比走势（市场广度）", t_trend_note:`' + zh_trend + '<div class="nrow"><span class="d">09-07</span>',
    "zh-trend-note")

zh_traj = ('<div class="nrow"><span class="d">09-09</span><span class="r">短线退潮</span>'
           '<span class="t">缩量分化：涨股比 57%→32%、涨停腰斩至 42、创业板 −0.14% 翻绿，广度与赚钱效应同步退潮；但成交缩量 −900亿、杠杆与主力仍集中于光模块/PCB、估值分位 79.6% 仍高，风险等级维持「中」。</span></div>\n')
rep('t_traj:"情绪周期轨迹（六阶段定位）", t_traj_note:`<div class="nrow"><span class="d">09-07</span>',
    't_traj:"情绪周期轨迹（六阶段定位）", t_traj_note:`' + zh_traj + '<div class="nrow"><span class="d">09-07</span>',
    "zh-traj-note")

# ---------- 3) en 词典 ----------
rep('t_updated:"Last updated: 2026-09-07 (15 issues, 08-17 ~ 09-07; 08-22/23 & 08-29/30 weekend closed)",',
    't_updated:"Last updated: 2026-09-09 (16 issues, 08-17 ~ 09-09; 08-22/23 & 08-29/30 weekend closed)",',
    "en-updated")
rep('s_all:"all", s_risk_lbl:"Risk level per issue (13 High + 09-04 / 09-07 Medium)",',
    's_all:"all", s_risk_lbl:"Risk level per issue (13 High + 09-04 / 09-07 / 09-09 Medium)",',
    "en-risk")
rep('s_span_lbl:"Trading-day coverage span (08-22/23 & 08-29/30 weekend closed; latest 09-07)",',
    's_span_lbl:"Trading-day coverage span (08-22/23 & 08-29/30 weekend closed; latest 09-09)",',
    "en-span")

en_trend = ('<div class="nrow"><span class="d">09-09</span><span class="r">Up 32%</span>'
            '<span class="t">Volume-shrinking divergence / short-term ebb: ChiNext −0.14% turns red, limit-up halves 90→42, limit-down 0; rubber +4.07% / shipping ports +3.86% lead as the main line rotates to rubber/shipping/resources; turnover ¥1.86tn (−¥90bn) shrinks, leverage and main capital still cluster in optical modules / PCB; risk stays Medium.</span></div>\n')
rep('t_trend:"Up-Stock Ratio Trend (Breadth)", t_trend_note:`<div class="nrow"><span class="d">09-07</span>',
    't_trend:"Up-Stock Ratio Trend (Breadth)", t_trend_note:`' + en_trend + '<div class="nrow"><span class="d">09-07</span>',
    "en-trend-note")

en_traj = ('<div class="nrow"><span class="d">09-09</span><span class="r">Short ebb</span>'
           '<span class="t">Volume-shrinking divergence: up-ratio 57%→32%, limit-up halves to 42, ChiNext −0.14% turns red — breadth and profit effect ebb together; yet turnover shrinks ¥90bn and leverage / main capital still cluster in optical modules / PCB with valuation pctile 79.6% high; risk stays Medium.</span></div>\n')
rep('t_traj:"Sentiment Cycle Path (6-stage)", t_traj_note:`<div class="nrow"><span class="d">09-07</span>',
    't_traj:"Sentiment Cycle Path (6-stage)", t_traj_note:`' + en_traj + '<div class="nrow"><span class="d">09-07</span>',
    "en-traj-note")

# ---------- 4) SVG 走势图重算（16 点，左=最新） ----------
vals = [32, 57, 46, 33, 28, 61, 57, 61, 53, 76, 26, 45, 73, 8, 38, 78]
days = ["09-09", "09-07", "09-04", "09-03", "09-02", "09-01", "08-31", "08-27", "08-26", "08-25",
        "08-24", "08-21", "08-20", "08-19", "08-18", "08-17"]
step = 750.0 / (len(vals) - 1)
pts = [(60 + i * step, 200 - 1.6 * v) for i, v in enumerate(vals)]


def fmt(x):
    return ("%.1f" % x).rstrip("0").rstrip(".")


line_pts = " ".join("%s,%s" % (fmt(x), fmt(y)) for x, y in pts)
area_pts = line_pts + " 810,200 60,200"

circles, labels, daylabs = [], [], []
for i, ((x, y), v) in enumerate(zip(pts, vals)):
    dark = v <= 28
    circles.append('<circle cx="%s" cy="%s" r="%d" fill="%s"/>' % (fmt(x), fmt(y), 6 if dark else 5, "#8a1810" if dark else "#b8332a"))
    ly = ("%.1f" % (y + 17)).rstrip("0").rstrip(".") if v <= 10 else ("%.1f" % (y - 13)).rstrip("0").rstrip(".")
    lc = ' fill="#8a1810"' if dark else ""
    labels.append('<text class="vallab" x="%s" y="%s" text-anchor="middle"%s>%d%%</text>' % (fmt(x), ly, lc, v))
    daylabs.append('<text class="daylab" x="%s" y="222" text-anchor="middle">%s</text>' % (fmt(x), days[i]))

gap1 = fmt((pts[5][0] + pts[6][0]) / 2)    # 08-29/30 休市
gap2 = fmt((pts[9][0] + pts[10][0]) / 2)   # 08-22/23 休市

svg_new = '''<svg viewBox="0 0 860 240" role="img" aria-label="up-stock ratio trend">
          <defs>
            <linearGradient id="area" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stop-color="#b8332a" stop-opacity="0.22"/>
              <stop offset="100%" stop-color="#b8332a" stop-opacity="0.02"/>
            </linearGradient>
          </defs>
          <!-- gridlines -->
          <line x1="60" y1="40" x2="810" y2="40" stroke="#e7e2d8" stroke-width="1"/>
          <line x1="60" y1="80" x2="810" y2="80" stroke="#e7e2d8" stroke-width="1"/>
          <line x1="60" y1="120" x2="810" y2="120" stroke="#e7e2d8" stroke-width="1"/>
          <line x1="60" y1="160" x2="810" y2="160" stroke="#e7e2d8" stroke-width="1"/>
          <line x1="60" y1="200" x2="810" y2="200" stroke="#cfc9bd" stroke-width="1.5"/>
          <!-- y labels -->
          <text class="axislab" x="50" y="44" text-anchor="end">100</text>
          <text class="axislab" x="50" y="84" text-anchor="end">75</text>
          <text class="axislab" x="50" y="124" text-anchor="end">50</text>
          <text class="axislab" x="50" y="164" text-anchor="end">25</text>
          <text class="axislab" x="50" y="204" text-anchor="end">0</text>
          <!-- weekend gap markers -->
          <line x1="@G1@" y1="40" x2="@G1@" y2="200" stroke="#b8893b" stroke-width="1.2" stroke-dasharray="5 4"/>
          <text class="axislab" x="@G1@" y="34" text-anchor="middle" fill="#b8893b">08-29/30 休市</text>
          <line x1="@G2@" y1="40" x2="@G2@" y2="200" stroke="#b8893b" stroke-width="1.2" stroke-dasharray="5 4"/>
          <text class="axislab" x="@G2@" y="34" text-anchor="middle" fill="#b8893b">08-22/23 休市</text>
          <!-- area -->
          <polygon fill="url(#area)" points="@AREA@"/>
          <!-- line (newest -> oldest) -->
          <polyline fill="none" stroke="#b8332a" stroke-width="2.5" stroke-linejoin="round"
            points="@LINE@"/>
          <!-- points + value labels (09-09 left -> 08-17 right) -->
          @CIRCLES@
          @LABELS@
          <!-- day labels (newest -> oldest) -->
          @DAYS@
        </svg>'''
svg_new = (svg_new
           .replace("@G1@", gap1).replace("@G2@", gap2)
           .replace("@AREA@", area_pts).replace("@LINE@", line_pts)
           .replace("@CIRCLES@", "\n          ".join(circles))
           .replace("@LABELS@", "\n          ".join(labels))
           .replace("@DAYS@", "\n          ".join(daylabs)))

i0 = s.index('<svg viewBox="0 0 860 240"')
i1 = s.index("</svg>", i0) + len("</svg>")
s = s[:i0] + svg_new + s[i1:]

# ---------- 落盘 ----------
if fails:
    print("FAIL:", fails)
    sys.exit(1)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("OK  %d -> %d chars, patches applied" % (orig_len, len(s)))
