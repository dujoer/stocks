# -*- coding: utf-8 -*-
import re, sys

SRC = "index.html"
OUT = "index.html"
bak = SRC + ".bak"
html0 = open(SRC, encoding="utf-8").read()
open(bak, "w", encoding="utf-8").write(html0)
html = html0

def must_replace(old, new, n=1):
    global html
    c = html.count(old)
    if c != n:
        sys.stderr.write("WARN count=%d for:\n%r\n" % (c, old[:80]))
    html = html.replace(old, new, n)

# ---- 1. weekend gap marker x 495 -> 433 ----
must_replace(
    '<line x1="495" y1="40" x2="495" y2="200" stroke="#b8893b" stroke-width="1.2" stroke-dasharray="5 4"/>',
    '<line x1="433" y1="40" x2="433" y2="200" stroke="#b8893b" stroke-width="1.2" stroke-dasharray="5 4"/>')
must_replace(
    '<text class="axislab" x="495" y="34" text-anchor="middle" fill="#b8893b">08-22/23 休市</text>',
    '<text class="axislab" x="433" y="34" text-anchor="middle" fill="#b8893b">08-22/23 休市</text>')

# ---- 2. trend chart SVG area/polyline/circles/daylabels (recompute 8 pts) ----
svg_old = '''          <!-- area -->
          <polygon fill="url(#area)" points="60,75.2 157,139.2 253,187.2 350,83.2 447,128.0 543,158.4 640,78.4 640,200 60,200"/>
          <!-- line -->
          <polyline fill="none" stroke="#b8332a" stroke-width="2.5" stroke-linejoin="round"
            points="60,75.2 157,139.2 253,187.2 350,83.2 447,128.0 543,158.4 640,78.4"/>
          <!-- points + value labels -->
          <circle cx="60" cy="75.2" r="5" fill="#b8332a"/>
          <text class="vallab" x="60" y="62" text-anchor="middle">78%</text>
          <circle cx="157" cy="139.2" r="5" fill="#b8332a"/>
          <text class="vallab" x="157" y="156" text-anchor="middle">38%</text>
          <circle cx="253" cy="187.2" r="6" fill="#8a1810"/>
          <text class="vallab" x="253" y="204" text-anchor="middle" fill="#8a1810">8%</text>
          <circle cx="350" cy="83.2" r="5" fill="#b8332a"/>
          <text class="vallab" x="350" y="70" text-anchor="middle">73%</text>
          <circle cx="447" cy="128.0" r="5" fill="#b8332a"/>
          <text class="vallab" x="447" y="115" text-anchor="middle">45%</text>
          <circle cx="543" cy="158.4" r="5" fill="#b8332a"/>
          <text class="vallab" x="543" y="175" text-anchor="middle">26%</text>
          <circle cx="640" cy="78.4" r="5" fill="#b8332a"/>
          <text class="vallab" x="640" y="65" text-anchor="middle">76%</text>
          <!-- day labels -->
          <text class="daylab" x="60" y="222" text-anchor="middle">08-17</text>
          <text class="daylab" x="157" y="222" text-anchor="middle">08-18</text>
          <text class="daylab" x="253" y="222" text-anchor="middle">08-19</text>
          <text class="daylab" x="350" y="222" text-anchor="middle">08-20</text>
          <text class="daylab" x="447" y="222" text-anchor="middle">08-21</text>
          <text class="daylab" x="543" y="222" text-anchor="middle">08-24</text>
          <text class="daylab" x="640" y="222" text-anchor="middle">08-25</text>'''
svg_new = '''          <!-- area -->
          <polygon fill="url(#area)" points="60,75.2 142.9,139.2 225.7,187.2 308.6,83.2 391.4,128.0 474.3,158.4 557.1,78.4 640,115.2 640,200 60,200"/>
          <!-- line -->
          <polyline fill="none" stroke="#b8332a" stroke-width="2.5" stroke-linejoin="round"
            points="60,75.2 142.9,139.2 225.7,187.2 308.6,83.2 391.4,128.0 474.3,158.4 557.1,78.4 640,115.2"/>
          <!-- points + value labels -->
          <circle cx="60" cy="75.2" r="5" fill="#b8332a"/>
          <text class="vallab" x="60" y="62" text-anchor="middle">78%</text>
          <circle cx="142.9" cy="139.2" r="5" fill="#b8332a"/>
          <text class="vallab" x="142.9" y="156" text-anchor="middle">38%</text>
          <circle cx="225.7" cy="187.2" r="6" fill="#8a1810"/>
          <text class="vallab" x="225.7" y="204" text-anchor="middle" fill="#8a1810">8%</text>
          <circle cx="308.6" cy="83.2" r="5" fill="#b8332a"/>
          <text class="vallab" x="308.6" y="70" text-anchor="middle">73%</text>
          <circle cx="391.4" cy="128.0" r="5" fill="#b8332a"/>
          <text class="vallab" x="391.4" y="115" text-anchor="middle">45%</text>
          <circle cx="474.3" cy="158.4" r="5" fill="#b8332a"/>
          <text class="vallab" x="474.3" y="175" text-anchor="middle">26%</text>
          <circle cx="557.1" cy="78.4" r="5" fill="#b8332a"/>
          <text class="vallab" x="557.1" y="65" text-anchor="middle">76%</text>
          <circle cx="640" cy="115.2" r="5" fill="#b8332a"/>
          <text class="vallab" x="640" y="102" text-anchor="middle">53%</text>
          <!-- day labels -->
          <text class="daylab" x="60" y="222" text-anchor="middle">08-17</text>
          <text class="daylab" x="142.9" y="222" text-anchor="middle">08-18</text>
          <text class="daylab" x="225.7" y="222" text-anchor="middle">08-19</text>
          <text class="daylab" x="308.6" y="222" text-anchor="middle">08-20</text>
          <text class="daylab" x="391.4" y="222" text-anchor="middle">08-21</text>
          <text class="daylab" x="474.3" y="222" text-anchor="middle">08-24</text>
          <text class="daylab" x="557.1" y="222" text-anchor="middle">08-25</text>
          <text class="daylab" x="640" y="222" text-anchor="middle">08-26</text>'''
must_replace(svg_old, svg_new)

# ---- 3. stats HTML strip ----
must_replace('''      <div class="num">7 <small data-i18n="s_issues">期</small></div>
      <div class="lbl" data-i18n="s_issues_lbl">已归档日报（每日独立保留）</div>
    </div>
    <div class="stat">
      <div class="num" style="color:var(--accent)">高 <small data-i18n="s_all">全部</small></div>
      <div class="lbl" data-i18n="s_risk_lbl">各期风险等级（6 期同为「高」）</div>
    </div>
    <div class="stat">
      <div class="num">08-17<small> ~ 08-25</small></div>
      <div class="lbl" data-i18n="s_span_lbl">覆盖交易日跨度（08-22~08-23 周末休市）</div>
    </div>''',
'''      <div class="num">8 <small data-i18n="s_issues">期</small></div>
      <div class="lbl" data-i18n="s_issues_lbl">已归档日报（每日独立保留）</div>
    </div>
    <div class="stat">
      <div class="num" style="color:var(--accent)">高 <small data-i18n="s_all">全部</small></div>
      <div class="lbl" data-i18n="s_risk_lbl">各期风险等级（8 期同为「高」）</div>
    </div>
    <div class="stat">
      <div class="num">08-17<small> ~ 08-26</small></div>
      <div class="lbl" data-i18n="s_span_lbl">覆盖交易日跨度（08-22~08-23 周末休市）</div>
    </div>''')

# ---- 4. header t_updated default span ----
must_replace(
    '<span data-i18n="t_updated">最近更新：2026-08-25（收录 08-17 ~ 08-25 共 7 期，08-22~08-23 周末休市）</span>',
    '<span data-i18n="t_updated">最近更新：2026-08-26（收录 08-17 ~ 08-26 共 8 期，08-22~08-23 周末休市）</span>')

# ---- 5. trend note static default (data-i18n, overwritten at runtime) ----
must_replace(
    '08-25 为最新一期。全线 7 期风险等级均为「高」。</p>',
    '08-26 为最新一期。全线 8 期风险等级均为「高」。</p>')

# ---- 6. I18N values ----
# t_updated zh/en
must_replace(
    't_updated:"最近更新：2026-08-25（收录 08-17 ~ 08-25 共 7 期，08-22~08-23 周末休市）",',
    't_updated:"最近更新：2026-08-26（收录 08-17 ~ 08-26 共 8 期，08-22~08-23 周末休市）",')
must_replace(
    't_updated:"Last updated: 2026-08-25 (7 issues, 08-17 ~ 08-25; 08-22/23 weekend closed)",',
    't_updated:"Last updated: 2026-08-26 (8 issues, 08-17 ~ 08-26; 08-22/23 weekend closed)",')
# s_span_lbl zh/en
must_replace(
    's_span_lbl:"覆盖交易日跨度（08-22~08-23 周末休市；最新 08-25）",',
    's_span_lbl:"覆盖交易日跨度（08-22~08-23 周末休市；最新 08-26）",')
must_replace(
    's_span_lbl:"Trading-day coverage span (08-22/23 weekend closed; latest 08-25)",',
    's_span_lbl:"Trading-day coverage span (08-22/23 weekend closed; latest 08-26)",')
# s_risk_lbl zh/en
must_replace(
    's_risk_lbl:"各期风险等级（7 期同为「高」）",',
    's_risk_lbl:"各期风险等级（8 期同为「高」）",')
must_replace(
    's_risk_lbl:"Risk level per issue (all 7 = High)",',
    's_risk_lbl:"Risk level per issue (all 8 = High)",')
# t_trend_note zh/en
must_replace(
    't_trend_note:"08-19 广度崩至 8%（恐慌/踩踏），08-20 修复至 73%，08-21 反弹后分化回落至 45%，08-24 放量普跌广度再崩至 26%，08-25 缩量普涨广度暴拉回 76%（官方「狂热」标签与真实广度共振向上，但量缩、技术极弱 = 低质量反弹）。08-22~08-23 周末休市无交易；08-25 为最新一期。全线 7 期风险等级均为「高」。",',
    't_trend_note:"08-19 广度崩至 8%（恐慌/踩踏），08-20 修复至 73%，08-21 反弹后分化回落至 45%，08-24 放量普跌广度再崩至 26%，08-25 缩量普涨广度暴拉回 76%（官方「狂热」标签与真实广度共振向上，但量缩、技术极弱 = 低质量反弹），08-26 技术反包广度回落至 53%（无量反包、量价背离，官方「狂热」标签虚高）。08-22~08-23 周末休市无交易；08-26 为最新一期。全线 8 期风险等级均为「高」。",')
must_replace(
    "t_trend_note:\"Breadth collapsed to 8% on 08-19 (panic), rebounded to 73% on 08-20, fell to 45% on 08-21, collapsed again to 26% on 08-24 amid broad sell-off, then roared back to 76% on 08-25 in a volume-shrinking rally (official 'Euphoria' tag now aligns upward with real breadth, yet volume-down & technics weak = low-quality bounce). 08-22/23 weekend closed; 08-25 is the latest issue. All 7 issues rated High risk.\",",
    "t_trend_note:\"Breadth collapsed to 8% on 08-19 (panic), rebounded to 73% on 08-20, fell to 45% on 08-21, collapsed again to 26% on 08-24 amid broad sell-off, then roared back to 76% on 08-25 in a volume-shrinking rally (official 'Euphoria' tag now aligns upward with real breadth, yet volume-down & technics weak = low-quality bounce), then 08-26 technical rebound pulled breadth back to 53% (volume-less rebound / price-volume divergence, official 'Euphoria' tag overstated). 08-22/23 weekend closed; 08-26 is the latest issue. All 8 issues rated High risk.\",")
# t_traj_note zh/en
must_replace(
    't_traj_note:"六阶段框架：绝望 → 怀疑 → 乐观 → 狂热 → 焦虑 → 自满。本序列由 08-17「狂热」经分歧、恐慌，08-21 回落至「怀疑（分歧加剧）」，08-24 转入「恐慌 / 退潮」（广度崩塌），08-25 由恐慌回「修复 / 分歧（弱反弹）」（缩量普涨、广度回暖至 76%，但量缩、技术极弱）。08-22~08-23 周末休市。",',
    't_traj_note:"六阶段框架：绝望 → 怀疑 → 乐观 → 狂热 → 焦虑 → 自满。本序列由 08-17「狂热」经分歧、恐慌，08-21 回落至「怀疑（分歧加剧）」，08-24 转入「恐慌 / 退潮」（广度崩塌），08-25 由恐慌回「修复 / 分歧（弱反弹）」（缩量普涨、广度回暖至 76%，但量缩、技术极弱），08-26 转入「修复延续 / 量价背离」（技术反包、MACD金叉、三指齐涨、连板维持5板，但成交继续缩、广度回落至53%、官方「狂热」标签虚高）。08-22~08-23 周末休市。",')
must_replace(
    't_traj_note:"Six-stage frame: Despair → Doubt → Optimism → Euphoria → Anxiety → Complacency. Path runs from 08-17 Euphoria through divergence & panic, to Doubt (divergence intensifying) on 08-21, into Panic / Washout (breadth collapse) on 08-24, then 08-25 shifts from panic back to Repair / Divergence (weak bounce) — volume-shrinking rally, breadth recovers to 76%, yet volume-down & technics weak. 08-22/23 weekend closed.",',
    't_traj_note:"Six-stage frame: Despair → Doubt → Optimism → Euphoria → Anxiety → Complacency. Path runs from 08-17 Euphoria through divergence & panic, to Doubt (divergence intensifying) on 08-21, into Panic / Washout (breadth collapse) on 08-24, then 08-25 shifts from panic back to Repair / Divergence (weak bounce) — volume-shrinking rally, breadth recovers to 76%, yet volume-down & technics weak; 08-26 moves to Repair continues / price-volume divergence (technical rebound, MACD golden cross, all three up, streak holds 5 boards, yet volume keeps shrinking, breadth falls to 53%, official \'Euphoria\' tag overstated). 08-22/23 weekend closed.",')

# ---- 7. REPORTS: insert 08-26 entry ----
rep_old = '''      summaryEn:"Up-ratio roars to 76%, 70 limit-up, 4 limit-down, turnover shrinks to ¥1.8318tn (−175.6bn); official 'Euphoria' tag aligns upward with real 76% breadth, yet volume-down, small-cap led, technics weak, valuation high = volume-shrinking rally / low-quality bounce."
    }
  ];'''
rep_new = '''      summaryEn:"Up-ratio roars to 76%, 70 limit-up, 4 limit-down, turnover shrinks to ¥1.8318tn (−175.6bn); official 'Euphoria' tag aligns upward with real 76% breadth, yet volume-down, small-cap led, technics weak, valuation high = volume-shrinking rally / low-quality bounce."
    }
    ,
    {
      file:"crowd-psychology-risk-radar-20260826.html", date:"2026-08-26",
      risk:"高", riskEn:"High",
      cycleZh:"修复延续 / 量价背离", cycleEn:"Repair continues / price-volume divergence",
      cycleNoteZh:"技术反包 / 无量反包", cycleNoteEn:"Technical rebound / volume-less rebound",
      up:"53%", limitup:"56", board:"5板", turn:"¥1.8087万亿",
      summaryZh:"涨股比由76%回落至53%、涨停56、跌停2、成交缩至¥1.8087万亿（−231亿）；技术面翻极强（MACD金叉）、三指齐涨、连板维持5板，但量能继续萎缩、趋势仍弱、估值偏高 = 无量反包 / 量价背离。官方「狂热」标签仅因涨停>50触发（真实53%<70%阈值）= 标签虚高。",
      summaryEn:"Up-ratio falls 76%→53%, 56 limit-up, 2 limit-down, turnover ¥1.8087tn (−23.1bn); technics flip to extremely-strong (MACD golden cross), all three indices up, streak holds 5 boards, yet volume keeps shrinking, trend still weak, valuation elevated = volume-less rebound / price-volume divergence. Official 'Euphoria' tag triggered only by limit-up>50 (real 53%<70%) = tag overstated."
    }
  ];'''
must_replace(rep_old, rep_new)

open(OUT, "w", encoding="utf-8").write(html)
print("Written:", OUT, "len", len(html))

# ---- validations ----
ext = len(re.findall(r'https?://', html))
srcref = len(re.findall(r'<script[^>]*\src=', html))
print("external http(s):", ext, "script src:", srcref)
assert ext == 0 and srcref == 0

# I18N coverage
used = set(re.findall(r'data-i18n="([^"]+)"', html))
m = re.search(r'var I18N = \{([\s\S]*?)\n  \};', html)
block = m.group(1)
zh_keys, en_keys = set(), set()
cur = None
for line in block.splitlines():
    s = line.strip()
    if s.startswith('zh:{'): cur='zh'; continue
    if s.startswith('en:{'): cur='en'; continue
    if s in ('}','},'): continue
    for km in re.finditer(r'([A-Za-z0-9_]+)\s*:', s):
        k = km.group(1)
        if cur=='zh': zh_keys.add(k)
        elif cur=='en': en_keys.add(k)
missing_zh = used - zh_keys
missing_en = used - en_keys
print("used:", len(used), "zh:", len(zh_keys), "en:", len(en_keys), "missing_zh:", len(missing_zh), "missing_en:", len(missing_en))
assert not missing_zh and not missing_en

# must-present
must = ["crowd-psychology-risk-radar-20260826.html","08-26","53%","¥1.8087万亿","8 期","8 issues","Repair continues / price-volume divergence"]
for s in must:
    assert s in html, ("missing present", s)
print("must-present OK")

# must-gone
gone = ["共 7 期","All 7 issues","7 issues","7 期同为","08-25 为最新一期。全线 7 期","最新 08-25"]
for s in gone:
    assert s not in html, ("still present", s)
print("must-gone OK")

# JS syntax
m2 = re.search(r'<script>([\s\S]*?)</script>', html)
open("_chk_index.js","w",encoding="utf-8").write(m2.group(1))
print("ALL INDEX CHECKS PASSED")
