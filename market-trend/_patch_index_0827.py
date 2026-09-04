# -*- coding: utf-8 -*-
"""Patch index.html to fold in the 2026-08-27 issue (9th report)."""
import re

P = "G:/ai/股票/web/psychology/index.html"
s = open(P, encoding="utf-8").read()
fails = []

def rep(old, new, label, count=1):
    n = s.count(old)
    if n != count:
        fails.append("WARN %s: expected %d got %d" % (label, count, n))
    return s.replace(old, new, -1 if count == 0 else count)

# ---- A. masthead HTML default (t_updated) ----
s = rep(
    '      <span data-i18n="t_updated">最近更新：2026-08-26（收录 08-17 ~ 08-26 共 8 期，08-22~08-23 周末休市）</span>',
    '      <span data-i18n="t_updated">最近更新：2026-08-27（收录 08-17 ~ 08-27 共 9 期，08-22~08-23 周末休市）</span>',
    "A masthead html")

# ---- B. stat num 8 -> 9 ----
s = rep(
    '      <div class="num">8 <small data-i18n="s_issues">期</small></div>',
    '      <div class="num">9 <small data-i18n="s_issues">期</small></div>',
    "B stat num")

# ---- C. HTML s_risk_lbl ----
s = rep(
    '      <div class="lbl" data-i18n="s_risk_lbl">各期风险等级（8 期同为「高」）</div>',
    '      <div class="lbl" data-i18n="s_risk_lbl">各期风险等级（9 期同为「高」）</div>',
    "C risk lbl")

# ---- D. HTML s_span num 08-26 -> 08-27 ----
s = rep(
    '      <div class="num">08-17<small> ~ 08-26</small></div>',
    '      <div class="num">08-17<small> ~ 08-27</small></div>',
    "D span num")

# ---- E. HTML trend-note (line 187) ----
s = rep(
    '低质量反弹）。08-22~08-23 周末休市无交易；08-26 为最新一期。全线 8 期风险等级均为「高」。',
    '低质量反弹），08-27 放量反包广度回升至 61%（成交放量 +3172亿 至 ¥2.1259万亿、涨停扩至 78、量价背离修复，官方「狂热」标签由涨停>50触发与真实 61% 广度略超前但量价已共振）。08-22~08-23 周末休市无交易；08-27 为最新一期。全线 9 期风险等级均为「高」。',
    "E trend note html")

# ---- F+K. HTML traj-note (198) & I18N zh t_traj_note (242) share tail ----
s = rep(
    '官方「狂热」标签虚高）。08-22~08-23 周末休市。',
    '官方「狂热」标签虚高），08-27 转入「修复确认 / 放量共振」（放量反包、成交放量至¥2.1259万亿、涨股比回升至61%、涨停扩至78、三指齐涨涨幅扩大、MACD金叉、量价背离修复，但趋势仍弱、估值偏高、结构分化）。08-22~08-23 周末休市。',
    "FK traj note html+zh", 2)

# ---- G. I18N zh t_updated ----
s = rep(
    '      t_updated:"最近更新：2026-08-26（收录 08-17 ~ 08-26 共 8 期，08-22~08-23 周末休市）",',
    '      t_updated:"最近更新：2026-08-27（收录 08-17 ~ 08-27 共 9 期，08-22~08-23 周末休市）",',
    "G zh t_updated")

# ---- H. I18N zh s_risk_lbl ----
s = rep(
    '      s_all:"全部", s_risk_lbl:"各期风险等级（8 期同为「高」）",',
    '      s_all:"全部", s_risk_lbl:"各期风险等级（9 期同为「高」）",',
    "H zh s_risk_lbl")

# ---- I. I18N zh s_span_lbl ----
s = rep(
    '      s_span_lbl:"覆盖交易日跨度（08-22~08-23 周末休市；最新 08-26）",',
    '      s_span_lbl:"覆盖交易日跨度（08-22~08-23 周末休市；最新 08-27）",',
    "I zh s_span_lbl")

# ---- J. I18N zh t_trend_note ----
s = rep(
    '官方「狂热」标签虚高）。08-22~08-23 周末休市无交易；08-26 为最新一期。全线 8 期风险等级均为「高」。',
    '官方「狂热」标签虚高），08-27 放量反包广度回升至 61%（成交放量 +3172亿 至 ¥2.1259万亿、涨停扩至 78、量价背离修复，官方「狂热」标签由涨停>50触发与真实 61% 广度略超前但量价已共振）。08-22~08-23 周末休市无交易；08-27 为最新一期。全线 9 期风险等级均为「高」。',
    "J zh t_trend_note")

# ---- L. I18N en t_updated ----
s = rep(
    '      t_updated:"Last updated: 2026-08-26 (8 issues, 08-17 ~ 08-26; 08-22/23 weekend closed)",',
    '      t_updated:"Last updated: 2026-08-27 (9 issues, 08-17 ~ 08-27; 08-22/23 weekend closed)",',
    "L en t_updated")

# ---- M. I18N en s_risk_lbl ----
s = rep(
    '      s_all:"all", s_risk_lbl:"Risk level per issue (all 8 = High)",',
    '      s_all:"all", s_risk_lbl:"Risk level per issue (all 9 = High)",',
    "M en s_risk_lbl")

# ---- N. I18N en s_span_lbl ----
s = rep(
    '      s_span_lbl:"Trading-day coverage span (08-22/23 weekend closed; latest 08-26)",',
    '      s_span_lbl:"Trading-day coverage span (08-22/23 weekend closed; latest 08-27)",',
    "N en s_span_lbl")

# ---- O. I18N en t_trend_note ----
s = rep(
    "official 'Euphoria' tag overstated). 08-22/23 weekend closed; 08-26 is the latest issue. All 8 issues rated High risk.",
    "official 'Euphoria' tag overstated), then 08-27 volume-expanded rebound lifted breadth to 61% (turnover expands +317.2bn to ¥2.1259tn, limit-up widens to 78, divergence repaired; official 'Euphoria' tag triggered by limit-up>50 slightly ahead of real 61% breadth but price-volume now resonates). 08-22/23 weekend closed; 08-27 is the latest issue. All 9 issues rated High risk.",
    "O en t_trend_note")

# ---- P. I18N en t_traj_note ----
s = rep(
    "official 'Euphoria' tag overstated). 08-22/23 weekend closed.",
    "official 'Euphoria' tag overstated); 08-27 moves to Repair confirmed / volume resonance (volume-expanded rebound, turnover to ¥2.1259tn, breadth recovers to 61%, limit-up widens to 78, all three indices up with widening gains, MACD golden cross, divergence repaired, yet trend still weak, valuation elevated, structure diverged). 08-22/23 weekend closed.",
    "P en t_traj_note")

# ---- Q. REPORTS: insert 08-27 entry before closing ]; ----
old_report_tail = (
    '      summaryEn:"Up-ratio falls 76%\u2192%53%, 56 limit-up, 2 limit-down, turnover \u00a51.8087tn (\u221223.1bn); '
    'technics flip to extremely-strong (MACD golden cross), all three indices up, streak holds 5 boards, '
    'yet volume keeps shrinking, trend still weak, valuation elevated = volume-less rebound / price-volume divergence. '
    'Official \'Euphoria\' tag triggered only by limit-up>50 (real 53%<70%) = tag overstated."\n'
    '    }\n'
    '  ];'
)
new_report_tail = (
    '      summaryEn:"Up-ratio falls 76%\u2192%53%, 56 limit-up, 2 limit-down, turnover \u00a51.8087tn (\u221223.1bn); '
    'technics flip to extremely-strong (MACD golden cross), all three indices up, streak holds 5 boards, '
    'yet volume keeps shrinking, trend still weak, valuation elevated = volume-less rebound / price-volume divergence. '
    'Official \'Euphoria\' tag triggered only by limit-up>50 (real 53%<70%) = tag overstated."\n'
    '    }\n'
    '    ,\n'
    '    {\n'
    '      file:"crowd-psychology-risk-radar-20260827.html", date:"2026-08-27",\n'
    '      risk:"\u9ad8", riskEn:"High",\n'
    '      cycleZh:"\u4fee\u590d\u786e\u8ba4 / \u653e\u91cf\u5171\u632f", cycleEn:"Repair confirmed / volume resonance",\n'
    '      cycleNoteZh:"\u653e\u91cf\u53cd\u5305 / \u91cf\u4ef7\u8fdd\u79bb\u4fee\u590d", cycleNoteEn:"Volume-expanded rebound / divergence repaired",\n'
    '      up:"61%", limitup:"78", board:"5\u677f", turn:"\u00a52.1259\u4e07\u4ebf",\n'
    '      summaryZh:"\u6da8\u80a1\u6bd4\u7531 53% \u56de\u5347\u81f3 61%\u3001\u6da8\u505c 78\u3001\u8dcc\u505c 4\u3001\u6210\u4ea4\u653e\u91cf\u81f3 \u00a52.1259\u4e07\u4ebf\uff08+3172\u4ebf\uff09\uff1b\u6280\u672f\u9762\u6781\u5f3a\uff08MACD\u91d1\u53c9\uff09\u3001\u4e09\u6307\u9f50\u6da8\u8dcc\u5e45\u6269\u5927\uff08\u521b\u4e1a\u677f+1.71%\uff09\u3001\u8fde\u677f\u7ef4\u6301 5 \u677f\uff0c\u91cf\u4ef7\u8fdd\u79bb\u4fee\u590d = \u653e\u91cf\u53cd\u5305 / \u91cf\u4ef7\u5171\u632f\u3002\u4f46\u8d8b\u52bf\u4ecd\u5f31\u3001\u4f30\u503c\u504f\u9ad8\uff08PE\u5206\u4f4d 70-90% \u4e14\u6307\u6570\u53c8\u6da8\uff09\u3001\u7ed3\u6784\u5206\u5316\uff08\u94f6\u884c/\u5149\u4f0f/\u767d\u7535\u9886\u8dcc\uff09\uff0c\u5b98\u65b9\u300c\u72c2\u70ed\u300d\u6807\u7b7e\u4ec5\u56e0\u6da8\u505c>50\u89e6\u53d1\uff08\u771f\u5b9e 61%<70% \u9608\u503c\uff09= \u6807\u7b7e\u7565\u8d85\u524d\u5e7f\u5ea6\u3002",\n'
    '      summaryEn:"Up-ratio recovers 53%\u219261%, 78 limit-up, 4 limit-down, turnover expands to \u00a52.1259tn (+317.2bn); technics extremely-strong (MACD golden cross), all three indices up with widening gains (ChiNext +1.71%), streak holds 5 boards, price-volume divergence repaired = volume-expanded rebound / volume resonance. Yet trend still weak, valuation elevated (PE 70-90% pct while indices rise again), structure diverged (banks/PV/white-goods lead down), and official \'Euphoria\' tag triggered only by limit-up>50 (real 61%<70%) = tag slightly ahead of breadth."\n'
    '    }\n'
    '  ];'
)
s = rep(old_report_tail, new_report_tail, "Q report insert", 1)

# ---- Trend chart SVG: replace whole block with 9-point version ----
NEW_SVG = '''        <svg viewBox="0 0 740 240" role="img" aria-label="up-stock ratio trend">
          <defs>
            <linearGradient id="area" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stop-color="#b8332a" stop-opacity="0.22"/>
              <stop offset="100%" stop-color="#b8332a" stop-opacity="0.02"/>
            </linearGradient>
          </defs>
          <!-- gridlines -->
          <line x1="60" y1="40" x2="720" y2="40" stroke="#e7e2d8" stroke-width="1"/>
          <line x1="60" y1="80" x2="720" y2="80" stroke="#e7e2d8" stroke-width="1"/>
          <line x1="60" y1="120" x2="720" y2="120" stroke="#e7e2d8" stroke-width="1"/>
          <line x1="60" y1="160" x2="720" y2="160" stroke="#e7e2d8" stroke-width="1"/>
          <line x1="60" y1="200" x2="720" y2="200" stroke="#cfc9bd" stroke-width="1.5"/>
          <!-- y labels -->
          <text class="axislab" x="50" y="44" text-anchor="end">100</text>
          <text class="axislab" x="50" y="84" text-anchor="end">75</text>
          <text class="axislab" x="50" y="124" text-anchor="end">50</text>
          <text class="axislab" x="50" y="164" text-anchor="end">25</text>
          <text class="axislab" x="50" y="204" text-anchor="end">0</text>
          <!-- weekend gap marker (08-22 / 08-23) -->
          <line x1="431" y1="40" x2="431" y2="200" stroke="#b8893b" stroke-width="1.2" stroke-dasharray="5 4"/>
          <text class="axislab" x="431" y="34" text-anchor="middle" fill="#b8893b">08-22/23 休市</text>
          <!-- area -->
          <polygon fill="url(#area)" points="60,75.2 142.5,139.2 225.0,187.2 307.5,83.2 390.0,128.0 472.5,158.4 555.0,78.4 637.5,115.2 720.0,102.4 720.0,200 60,200"/>
          <!-- line -->
          <polyline fill="none" stroke="#b8332a" stroke-width="2.5" stroke-linejoin="round"
            points="60,75.2 142.5,139.2 225.0,187.2 307.5,83.2 390.0,128.0 472.5,158.4 555.0,78.4 637.5,115.2 720.0,102.4"/>
          <!-- points + value labels -->
          <circle cx="60" cy="75.2" r="5" fill="#b8332a"/>
          <text class="vallab" x="60" y="62" text-anchor="middle">78%</text>
          <circle cx="142.5" cy="139.2" r="5" fill="#b8332a"/>
          <text class="vallab" x="142.5" y="156" text-anchor="middle">38%</text>
          <circle cx="225.0" cy="187.2" r="6" fill="#8a1810"/>
          <text class="vallab" x="225.0" y="204" text-anchor="middle" fill="#8a1810">8%</text>
          <circle cx="307.5" cy="83.2" r="5" fill="#b8332a"/>
          <text class="vallab" x="307.5" y="70" text-anchor="middle">73%</text>
          <circle cx="390.0" cy="128.0" r="5" fill="#b8332a"/>
          <text class="vallab" x="390.0" y="115" text-anchor="middle">45%</text>
          <circle cx="472.5" cy="158.4" r="5" fill="#b8332a"/>
          <text class="vallab" x="472.5" y="175" text-anchor="middle">26%</text>
          <circle cx="555.0" cy="78.4" r="5" fill="#b8332a"/>
          <text class="vallab" x="555.0" y="65" text-anchor="middle">76%</text>
          <circle cx="637.5" cy="115.2" r="5" fill="#b8332a"/>
          <text class="vallab" x="637.5" y="102" text-anchor="middle">53%</text>
          <circle cx="720.0" cy="102.4" r="5" fill="#b8332a"/>
          <text class="vallab" x="720.0" y="89" text-anchor="middle">61%</text>
          <!-- day labels -->
          <text class="daylab" x="60" y="222" text-anchor="middle">08-17</text>
          <text class="daylab" x="142.5" y="222" text-anchor="middle">08-18</text>
          <text class="daylab" x="225.0" y="222" text-anchor="middle">08-19</text>
          <text class="daylab" x="307.5" y="222" text-anchor="middle">08-20</text>
          <text class="daylab" x="390.0" y="222" text-anchor="middle">08-21</text>
          <text class="daylab" x="472.5" y="222" text-anchor="middle">08-24</text>
          <text class="daylab" x="555.0" y="222" text-anchor="middle">08-25</text>
          <text class="daylab" x="637.5" y="222" text-anchor="middle">08-26</text>
          <text class="daylab" x="720.0" y="222" text-anchor="middle">08-27</text>
        </svg>'''
m = re.search(r'<svg viewBox="0 0 680 240"[\s\S]*?</svg>', s)
if not m:
    fails.append("WARN: trend chart svg not found for replacement")
else:
    s = s[:m.start()] + NEW_SVG + s[m.end():]

open(P, "w", encoding="utf-8").write(s)

print("PATCH DONE")
if fails:
    print("\n".join(fails))
else:
    print("ALL REPLACEMENTS OK (counts matched)")
