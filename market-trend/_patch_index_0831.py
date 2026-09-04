# -*- coding: utf-8 -*-
"""Patch market-trend/index.html to fold in the 2026-08-31 issue (10th report)."""
import re

P = "G:/ai/股票/web/psychology/index.html"
s = open(P, encoding="utf-8").read()
fails = []

def rep(old, new, label, count=1):
    n = s.count(old)
    if n != count:
        fails.append("WARN %s: expected %d got %d" % (label, count, n))
    return s.replace(old, new, -1 if count == 0 else count)

# ---- canonical new narrative strings ----
NEW_TREND_ZH = ("08-19 广度崩至 8%（恐慌/踩踏），08-20 修复至 73%，08-21 反弹后分化回落至 45%，"
    "08-24 放量普跌广度再崩至 26%，08-25 缩量普涨广度暴拉回 76%（官方「狂热」标签与真实广度共振向上，"
    "但量缩、技术极弱 = 低质量反弹），08-26 技术反包广度回落至 53%（无量反包、量价背离，官方「狂热」标签虚高），"
    "08-27 放量反包广度回升至 61%（成交放量 +3172亿 至 ¥2.1259万亿、涨停扩至 78、量价背离修复，"
    "官方「狂热」标签由涨停>50触发与真实 61% 广度略超前但量价已共振），"
    "08-31 缩量滞涨广度回落至 57%（成交 ¥2.131万亿 微增 +293亿、涨停 89、跌停 13、连板高度升至 6 板，"
    "但涨股比由 61% 回落、指数红而广度不济、结构分化加剧、估值高位 = 缩量滞涨 / 结构分化）。"
    "08-22~08-23 与 08-29~08-30 周末休市无交易；08-31 为最新一期。全线 10 期风险等级均为「高」。")

NEW_TRAJ_ZH = ("六阶段框架：绝望 → 怀疑 → 乐观 → 狂热 → 焦虑 → 自满。本序列由 08-17「狂热」经分歧、恐慌，"
    "08-21 回落至「怀疑（分歧加剧）」，08-24 转入「恐慌 / 退潮」（广度崩塌），"
    "08-25 由恐慌回「修复 / 分歧（弱反弹）」（缩量普涨、广度回暖至 76%，但量缩、技术极弱），"
    "08-26 转入「修复延续 / 量价背离」（技术反包、MACD金叉、三指齐涨、连板维持5板，但成交继续缩、广度回落至53%、官方「狂热」标签虚高），"
    "08-27 转入「修复确认 / 放量共振」（放量反包、成交放量至¥2.1259万亿、涨股比回升至61%、涨停扩至78、三指齐涨涨幅扩大、MACD金叉、量价背离修复，但趋势仍弱、估值偏高、结构分化），"
    "08-31 转入「缩量滞涨 / 结构分化」（指数红、涨股比由61%回落至57%、成交¥2.131万亿仅微增、涨停89但跌停13、连板高度升至6板、"
    "结构分化加剧——影视/数字媒体领涨而贵金属/光伏/白电/乘用车领跌、估值高位），风险由「修复」退向「滞涨」。"
    "08-22~08-23 与 08-29~08-30 周末休市。")

NEW_TREND_EN = ("Breadth collapsed to 8% on 08-19 (panic), rebounded to 73% on 08-20, fell to 45% on 08-21, "
    "collapsed again to 26% on 08-24 amid broad sell-off, then roared back to 76% on 08-25 in a volume-shrinking rally "
    "(official 'Euphoria' tag now aligns upward with real breadth, yet volume-down & technics weak = low-quality bounce), "
    "then 08-26 technical rebound pulled breadth back to 53% (volume-less rebound / price-volume divergence, official 'Euphoria' tag overstated), "
    "then 08-27 volume-expanded rebound lifted breadth to 61% (turnover expands +317.2bn to ¥2.1259tn, limit-up widens to 78, divergence repaired; "
    "official 'Euphoria' tag triggered by limit-up>50 slightly ahead of real 61% breadth but price-volume now resonates), "
    "then 08-31 volume-flat stall pulled breadth back to 57% (turnover only +29.3bn to ¥2.131tn, 89 limit-up, 13 limit-down, "
    "board height rises to 6, yet up-ratio falls from 61%, indices red-but-breadth-thin, structure divergence deepens, "
    "valuation elevated = volume-flat stall / structural divergence). 08-22/23 & 08-29/30 weekend closed; 08-31 is the latest issue. "
    "All 10 issues rated High risk.")

NEW_TRAJ_EN = ("Six-stage frame: Despair → Doubt → Optimism → Euphoria → Anxiety → Complacency. "
    "Path runs from 08-17 Euphoria through divergence & panic, to Doubt (divergence intensifying) on 08-21, "
    "into Panic / Washout (breadth collapse) on 08-24, then 08-25 shifts from panic back to Repair / Divergence (weak bounce) "
    "— volume-shrinking rally, breadth recovers to 76%, yet volume-down & technics weak; "
    "08-26 moves to Repair continues / price-volume divergence (technical rebound, MACD golden cross, all three up, streak holds 5 boards, "
    "yet volume keeps shrinking, breadth falls to 53%, official 'Euphoria' tag overstated); "
    "08-27 moves to Repair confirmed / volume resonance (volume-expanded rebound, turnover to ¥2.1259tn, breadth recovers to 61%, "
    "limit-up widens to 78, all three indices up with widening gains, MACD golden cross, divergence repaired, "
    "yet trend still weak, valuation elevated, structure diverged); "
    "08-31 moves to Volume-flat stall / Structural divergence (indices red, up-ratio falls 61%→57%, turnover only +29.3bn to ¥2.131tn, "
    "89 limit-up but 13 limit-down, board height rises to 6, structure divergence deepens — media/digital lead up while "
    "precious-metal/PV/white-goods lead down, valuation elevated), risk shifts from Repair back toward Stall. "
    "08-22/23 & 08-29/30 weekend closed.")

# ---- 1. HTML masthead t_updated ----
s = rep(
    '      <span data-i18n="t_updated">最近更新：2026-08-27（收录 08-17 ~ 08-27 共 9 期，08-22~08-23 周末休市）</span>',
    '      <span data-i18n="t_updated">最近更新：2026-08-31（收录 08-17 ~ 08-31 共 10 期，08-22~08-23 与 08-29~08-30 周末休市）</span>',
    "1 masthead html")

# ---- 2. stat num 9 -> 10 ----
s = rep(
    '      <div class="num">9 <small data-i18n="s_issues">期</small></div>',
    '      <div class="num">10 <small data-i18n="s_issues">期</small></div>',
    "2 stat num")

# ---- 3. HTML s_risk_lbl 9 -> 10 ----
s = rep(
    '      <div class="lbl" data-i18n="s_risk_lbl">各期风险等级（9 期同为「高」）</div>',
    '      <div class="lbl" data-i18n="s_risk_lbl">各期风险等级（10 期同为「高」）</div>',
    "3 risk lbl html")

# ---- 4. HTML s_span num 08-27 -> 08-31 ----
s = rep(
    '      <div class="num">08-17<small> ~ 08-27</small></div>',
    '      <div class="num">08-17<small> ~ 08-31</small></div>',
    "4 span num html")

# ---- 5. HTML trend note (data-i18n=t_trend_note) ----
m = re.search(r'(<p class="note" data-i18n="t_trend_note"[^>]*>)[^<]*(</p>)', s)
if not m:
    fails.append("WARN 5: trend note html not found")
else:
    s = s[:m.start()] + m.group(1) + NEW_TREND_ZH + m.group(2) + s[m.end():]

# ---- 6. HTML traj note (data-i18n=t_traj_note) ----
m = re.search(r'(<p class="note" data-i18n="t_traj_note"[^>]*>)[^<]*(</p>)', s)
if not m:
    fails.append("WARN 6: traj note html not found")
else:
    s = s[:m.start()] + m.group(1) + NEW_TRAJ_ZH + m.group(2) + s[m.end():]

# ---- 7. zh t_updated (line 241 full) ----
s = rep(
    '      t_updated:"最近更新：2026-08-27（收录 08-17 ~ 08-27 共 9 期，08-22~08-23 周末休市）",',
    '      t_updated:"最近更新：2026-08-31（收录 08-17 ~ 08-31 共 10 期，08-22~08-23 与 08-29~08-30 周末休市）",',
    "7 zh t_updated")

# ---- 8. zh s_risk_lbl (line 243 full) ----
s = rep(
    '      s_all:"全部", s_risk_lbl:"各期风险等级（9 期同为「高」）",',
    '      s_all:"全部", s_risk_lbl:"各期风险等级（10 期同为「高」）",',
    "8 zh s_risk_lbl")

# ---- 9. zh s_span_lbl (line 244 full) ----
s = rep(
    '      s_span_lbl:"覆盖交易日跨度（08-22~08-23 周末休市；最新 08-27）",',
    '      s_span_lbl:"覆盖交易日跨度（08-22~08-23 与 08-29~08-30 周末休市；最新 08-31）",',
    "9 zh s_span_lbl")

# ---- 10. zh t_trend_note (prefix-unique) ----
prefix = '      t_trend:"涨股比走势（市场广度）", t_trend_note:'
pat = re.compile(re.escape(prefix) + r'"[^"]*"')
if not pat.search(s):
    fails.append("WARN 10: zh t_trend_note not found")
else:
    s = pat.sub(lambda m: prefix + '"' + NEW_TREND_ZH + '"', s, count=1)

# ---- 11. zh t_traj_note (prefix-unique) ----
prefix = '      t_traj:"情绪周期轨迹（六阶段定位）", t_traj_note:'
pat = re.compile(re.escape(prefix) + r'"[^"]*"')
if not pat.search(s):
    fails.append("WARN 11: zh t_traj_note not found")
else:
    s = pat.sub(lambda m: prefix + '"' + NEW_TRAJ_ZH + '"', s, count=1)

# ---- 12. en t_updated (line 258 full) ----
s = rep(
    '      t_updated:"Last updated: 2026-08-27 (9 issues, 08-17 ~ 08-27; 08-22/23 weekend closed)",',
    '      t_updated:"Last updated: 2026-08-31 (10 issues, 08-17 ~ 08-31; 08-22/23 & 08-29/30 weekend closed)",',
    "12 en t_updated")

# ---- 13. en s_risk_lbl (line 260 full) ----
s = rep(
    '      s_all:"all", s_risk_lbl:"Risk level per issue (all 9 = High)",',
    '      s_all:"all", s_risk_lbl:"Risk level per issue (all 10 = High)",',
    "13 en s_risk_lbl")

# ---- 14. en s_span_lbl (line 261 full) ----
s = rep(
    '      s_span_lbl:"Trading-day coverage span (08-22/23 weekend closed; latest 08-27)",',
    '      s_span_lbl:"Trading-day coverage span (08-22/23 & 08-29/30 weekend closed; latest 08-31)",',
    "14 en s_span_lbl")

# ---- 15. en t_trend_note (prefix-unique) ----
prefix = '      t_trend:"Up-Stock Ratio Trend (Breadth)", t_trend_note:'
pat = re.compile(re.escape(prefix) + r'"[^"]*"')
if not pat.search(s):
    fails.append("WARN 15: en t_trend_note not found")
else:
    s = pat.sub(lambda m: prefix + '"' + NEW_TREND_EN + '"', s, count=1)

# ---- 16. en t_traj_note (prefix-unique) ----
prefix = '      t_traj:"Sentiment Cycle Path (6-stage)", t_traj_note:'
pat = re.compile(re.escape(prefix) + r'"[^"]*"')
if not pat.search(s):
    fails.append("WARN 16: en t_traj_note not found")
else:
    s = pat.sub(lambda m: prefix + '"' + NEW_TRAJ_EN + '"', s, count=1)

# ---- 17. REPORTS: insert 08-31 entry before closing ]; ----
old_tail = "    }\n  ];"
new_tail = (
    "    }\n"
    "    ,\n"
    "    {\n"
    '      file:"crowd-psychology-risk-radar-20260831.html", date:"2026-08-31",\n'
    '      risk:"高", riskEn:"High",\n'
    '      cycleZh:"缩量滞涨 / 结构分化", cycleEn:"Volume-flat stall / Structural divergence",\n'
    '      cycleNoteZh:"指数红而广度不济", cycleNoteEn:"Indices red yet breadth thin",\n'
    '      up:"57%", limitup:"89", board:"6板", turn:"¥2.131万亿",\n'
    '      summaryZh:"涨股比由61%回落至57%、涨停89、跌停13、成交¥2.131万亿（微增+293亿）；指数三红（上证+0.86%/深成+0.44%/创业板+0.42%）但广度不济、连板高度升至6板（海鸥住工），结构分化加剧——数字媒体+7.19%/影视院线+7.02%/出版+5.26%领涨，饰品−4.67%/乘用车−3.12%/光伏−2.82%领跌；估值高位、量能未有效放大 = 缩量滞涨 / 结构分化。",\n'
    '      summaryEn:"Up-ratio falls 61%→57%, 89 limit-up, 13 limit-down, turnover ¥2.131tn (+29.3bn); three indices up (SSE +0.86% / SZ +0.44% / ChiNext +0.42%) yet breadth thin, board height rises to 6 (Sea Gull Housing), structure divergence deepens — digital media +7.19% / cinema +7.02% / publishing +5.26% lead up, ornaments −4.67% / PV −3.12% / passenger cars −2.82% lead down; valuation elevated, volume not effectively expanded = volume-flat stall / structural divergence."\n'
    "    }\n"
    "  ];"
)
n = s.count(old_tail)
if n != 1:
    fails.append("WARN 17: REPORTS tail count = %d" % n)
else:
    s = s.replace(old_tail, new_tail, 1)

# ---- 18. Trend chart SVG: replace whole block with 10-point version ----
NEW_SVG = '''        <svg viewBox="0 0 860 240" role="img" aria-label="up-stock ratio trend">
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
          <!-- weekend gap marker (08-22 / 08-23) -->
          <line x1="431" y1="40" x2="431" y2="200" stroke="#b8893b" stroke-width="1.2" stroke-dasharray="5 4"/>
          <text class="axislab" x="431" y="34" text-anchor="middle" fill="#b8893b">08-22/23 休市</text>
          <!-- area -->
          <polygon fill="url(#area)" points="60,75.2 142.5,139.2 225.0,187.2 307.5,83.2 390.0,128.0 472.5,158.4 555.0,78.4 637.5,115.2 720.0,102.4 802.5,108.8 810.0,200 60,200"/>
          <!-- line -->
          <polyline fill="none" stroke="#b8332a" stroke-width="2.5" stroke-linejoin="round"
            points="60,75.2 142.5,139.2 225.0,187.2 307.5,83.2 390.0,128.0 472.5,158.4 555.0,78.4 637.5,115.2 720.0,102.4 802.5,108.8"/>
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
          <circle cx="802.5" cy="108.8" r="5" fill="#b8332a"/>
          <text class="vallab" x="802.5" y="95" text-anchor="middle">57%</text>
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
          <text class="daylab" x="802.5" y="222" text-anchor="middle">08-31</text>
        </svg>'''
m = re.search(r'<svg viewBox="0 0 740 240"[\s\S]*?</svg>', s)
if not m:
    fails.append("WARN 18: trend chart svg not found for replacement")
else:
    s = s[:m.start()] + NEW_SVG + s[m.end():]

open(P, "w", encoding="utf-8").write(s)

print("PATCH DONE")
if fails:
    print("\n".join(fails))
else:
    print("ALL REPLACEMENTS OK (counts matched)")
