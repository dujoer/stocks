# -*- coding: utf-8 -*-
"""psychology/index.html 修复 + 刷到 09-04：
1) 修复 09-04 REPORTS 条目 summaryEn 缺收尾引号/闭合括号导致整个 <script> 语法报错
2) 头部/统计/中英词典过期文案 09-03(13期) -> 09-04(14期)
3) SVG 涨股比走势图加入 09-04 (46%) 并重算 14 点坐标
4) 涨股比注记 / 情绪轨迹注记补 09-01~09-04 四行
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

# ---------- 1) 修复 JS 语法断点 ----------
rep('risk High→Medium.\n  ];',
    'risk High→Medium."\n    }\n  ];',
    'fix-js-syntax')

# ---------- 2) 静态头部/统计 ----------
rep('最近更新：2026-09-03（收录 08-17 ~ 09-03 共 13 期，08-22~08-23 与 08-29~08-30 周末休市）',
    '最近更新：2026-09-04（收录 08-17 ~ 09-04 共 14 期，08-22~08-23 与 08-29~08-30 周末休市）',
    'hdr-updated')
rep('<div class="num">13 <small data-i18n="s_issues">期</small></div>',
    '<div class="num">14 <small data-i18n="s_issues">期</small></div>',
    'stat-num')
rep('各期风险等级（10 期同为「高」）',
    '各期风险等级（13 期「高」+ 09-04 一期「中」）',
    'stat-risk')
rep('08-17<small> ~ 09-03</small>',
    '08-17<small> ~ 09-04</small>',
    'stat-span')

# ---------- 3) zh 词典 ----------
rep('t_updated:"最近更新：2026-08-31（收录 08-17 ~ 08-31 共 10 期，08-22~08-23 与 08-29~08-30 周末休市）",',
    't_updated:"最近更新：2026-09-04（收录 08-17 ~ 09-04 共 14 期，08-22~08-23 与 08-29~08-30 周末休市）",',
    'zh-updated')
rep('s_all:"全部", s_risk_lbl:"各期风险等级（11 期同为「高」）",',
    's_all:"全部", s_risk_lbl:"各期风险等级（13 期「高」+ 09-04 一期「中」）",',
    'zh-risk')
rep('s_span_lbl:"覆盖交易日跨度（08-22~08-23 与 08-29~08-30 周末休市；最新 09-02）",',
    's_span_lbl:"覆盖交易日跨度（08-22~08-23 与 08-29~08-30 周末休市；最新 09-04）",',
    'zh-span')

zh_trend_pre = '''<div class="nrow"><span class="d">09-04</span><span class="r">涨股比 46%</span><span class="t">放量修复·跌停清零：成交放量+2700亿至¥2.03万亿、涨停42/跌停17→0；房地产服务领涨反转，船舶与农业养殖涨停潮接力主线，风险等级由高转中。</span></div>
<div class="nrow"><span class="d">09-03</span><span class="r">涨股比 33%</span><span class="t">低位弱修复·主线散乱：成交续缩至¥1.76万亿（−322亿）、涨停46/跌停17；仅航运港口/保险Ⅱ/贵金属逆势活跃，追涨谨慎。</span></div>
<div class="nrow"><span class="d">09-02</span><span class="r">涨股比 28%</span><span class="t">缩量普跌·情绪退潮：成交缩至¥1.79万亿（−3420亿）、三指齐跌、MACD红柱顶背离；融资单日逆势加仓，追涨与踩踏风险并存。</span></div>
<div class="nrow"><span class="d">09-01</span><span class="r">涨股比 61%</span><span class="t">高位震荡·指数-个股背离：指数微跌但个股普涨（3386涨/2040跌）、连板升至7板；KDJ超买、估值偏高，官方「狂热」标签虚高。</span></div>
'''
rep('t_trend:"涨股比走势（市场广度）", t_trend_note:`<div class="nrow"><span class="d">08-31</span>',
    't_trend:"涨股比走势（市场广度）", t_trend_note:`' + zh_trend_pre + '<div class="nrow"><span class="d">08-31</span>',
    'zh-trend-note')

zh_traj_pre = '''<div class="nrow"><span class="d">09-04</span><span class="r">修复/分歧</span><span class="t">放量修复反弹：跌停清零、成交+2700亿、涨股比33%→46%，风险等级由「高」转「中」，龙头一日一换=放量分化。</span></div>
<div class="nrow"><span class="d">09-03</span><span class="r">弱修复</span><span class="t">低位回升：涨股比28%→33%，主线散乱、量能续缩、跌停扩大至17家。</span></div>
<div class="nrow"><span class="d">09-02</span><span class="r">退潮</span><span class="t">缩量普跌：广度崩至28%、成交−3420亿、MACD顶背离。</span></div>
<div class="nrow"><span class="d">09-01</span><span class="r">高位震荡</span><span class="t">指数-个股背离：指数微跌个股普涨，连板7板、KDJ超买。</span></div>
'''
rep('t_traj:"情绪周期轨迹（六阶段定位）", t_traj_note:`<div class="nrow"><span class="d">08-31</span>',
    't_traj:"情绪周期轨迹（六阶段定位）", t_traj_note:`' + zh_traj_pre + '<div class="nrow"><span class="d">08-31</span>',
    'zh-traj-note')

# ---------- 4) en 词典 ----------
rep('t_updated:"Last updated: 2026-09-02 (11 issues, 08-17 ~ 09-02; 08-22/23 & 08-29/30 weekend closed)",',
    't_updated:"Last updated: 2026-09-04 (14 issues, 08-17 ~ 09-04; 08-22/23 & 08-29/30 weekend closed)",',
    'en-updated')
rep('s_all:"all", s_risk_lbl:"Risk level per issue (all 11 = High)",',
    's_all:"all", s_risk_lbl:"Risk level per issue (13 High + 09-04 Medium)",',
    'en-risk')
rep('s_span_lbl:"Trading-day coverage span (08-22/23 & 08-29/30 weekend closed; latest 09-02)",',
    's_span_lbl:"Trading-day coverage span (08-22/23 & 08-29/30 weekend closed; latest 09-04)",',
    'en-span')

en_trend_pre = '''<div class="nrow"><span class="d">09-04</span><span class="r">Up 46%</span><span class="t">Volume-expanded repair / limit-down cleared: turnover +¥270bn to ¥2.03tn, 42 limit-up / limit-down 17→0; real-estate services reversal leads, shipbuilding & agri-breeding limit-up wave takes over, risk High→Medium.</span></div>
<div class="nrow"><span class="d">09-03</span><span class="r">Up 33%</span><span class="t">Low-level weak recovery / scattered leaders: turnover ¥1.76tn (−32.2bn), 46 limit-up / 17 limit-down; only shipping / insurance / precious metals active, chase with caution.</span></div>
<div class="nrow"><span class="d">09-02</span><span class="r">Up 28%</span><span class="t">Volume-shrink selloff / sentiment ebb: turnover ¥1.79tn (−342bn), all three indices down, MACD top divergence; margin adds against the tide.</span></div>
<div class="nrow"><span class="d">09-01</span><span class="r">Up 61%</span><span class="t">High-level oscillation / index-vs-stock divergence: indices dip yet stocks broadly up (3386/2040), board to 7; KDJ overbought, official tag overstated.</span></div>
'''
rep("t_trend:\"Up-Stock Ratio Trend (Breadth)\", t_trend_note:`<div class=\"nrow\"><span class=\"d\">08-31</span>",
    "t_trend:\"Up-Stock Ratio Trend (Breadth)\", t_trend_note:`" + en_trend_pre + '<div class="nrow"><span class="d">08-31</span>',
    'en-trend-note')

en_traj_pre = '''<div class="nrow"><span class="d">09-04</span><span class="r">Repair</span><span class="t">Volume-rebound with divergence: limit-down cleared, turnover +¥270bn, up-ratio 33%→46%, risk High→Medium, leader rotates daily.</span></div>
<div class="nrow"><span class="d">09-03</span><span class="r">Weak repair</span><span class="t">Rebound from low: up-ratio 28%→33%, leaders scattered, volume shrinks, limit-down widens to 17.</span></div>
<div class="nrow"><span class="d">09-02</span><span class="r">Ebb</span><span class="t">Volume-shrink selloff: breadth crashes to 28%, turnover −342bn, MACD top divergence.</span></div>
<div class="nrow"><span class="d">09-01</span><span class="r">Oscillation</span><span class="t">Index-vs-stock divergence: indices dip, stocks broadly up, board 7, KDJ overbought.</span></div>
'''
rep('t_traj:"Sentiment Cycle Path (6-stage)", t_traj_note:`<div class="nrow"><span class="d">08-31</span>',
    't_traj:"Sentiment Cycle Path (6-stage)", t_traj_note:`' + en_traj_pre + '<div class="nrow"><span class="d">08-31</span>',
    'en-traj-note')

# ---------- 5) SVG 走势图重算（14 点，左=最新） ----------
vals = [46, 33, 28, 61, 57, 61, 53, 76, 26, 45, 73, 8, 38, 78]
days = ["09-04","09-03","09-02","09-01","08-31","08-27","08-26","08-25",
        "08-24","08-21","08-20","08-19","08-18","08-17"]
step = 750.0 / (len(vals) - 1)
pts = [(60 + i * step, 200 - 1.6 * v) for i, v in enumerate(vals)]

def fmt(x):
    return ('%.1f' % x).rstrip('0').rstrip('.')

line_pts = ' '.join('%s,%s' % (fmt(x), fmt(y)) for x, y in pts)
area_pts = line_pts + ' 810,200 60,200'

circles, labels, daylabs = [], [], []
for i, ((x, y), v) in enumerate(zip(pts, vals)):
    dark = v <= 28
    circles.append('<circle cx="%s" cy="%s" r="%d" fill="%s"/>' % (fmt(x), fmt(y), 6 if dark else 5, '#8a1810' if dark else '#b8332a'))
    ly = ('%.1f' % (y + 17)).rstrip('0').rstrip('.') if v <= 10 else ('%.1f' % (y - 13)).rstrip('0').rstrip('.')
    lc = ' fill="#8a1810"' if dark else ''
    labels.append('<text class="vallab" x="%s" y="%s" text-anchor="middle"%s>%d%%</text>' % (fmt(x), ly, lc, v))
    daylabs.append('<text class="daylab" x="%s" y="222" text-anchor="middle">%s</text>' % (fmt(x), days[i]))

# 周末休市分隔线：08-29/30 在 08-31 与 08-27 之间；08-22/23 在 08-24 与 08-21 之间
gap1 = fmt((pts[4][0] + pts[5][0]) / 2)   # 08-29/30
gap2 = fmt((pts[8][0] + pts[9][0]) / 2)   # 08-22/23

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
          <!-- points + value labels (09-04 left -> 08-17 right) -->
          @CIRCLES@
          @LABELS@
          <!-- day labels (newest -> oldest) -->
          @DAYS@
        </svg>'''
svg_new = (svg_new
           .replace('@G1@', gap1).replace('@G2@', gap2)
           .replace('@AREA@', area_pts).replace('@LINE@', line_pts)
           .replace('@CIRCLES@', '\n          '.join(circles))
           .replace('@LABELS@', '\n          '.join(labels))
           .replace('@DAYS@', '\n          '.join(daylabs)))

i0 = s.index('<svg viewBox="0 0 860 240"')
i1 = s.index('</svg>', i0) + len('</svg>')
s = s[:i0] + svg_new + s[i1:]

# ---------- 落盘 ----------
if fails:
    print('FAIL:', fails)
    sys.exit(1)
io.open(P, 'w', encoding='utf-8', newline='\n').write(s)
print('OK  %d -> %d bytes, all %d patches applied' % (orig_len, len(s), 20))
