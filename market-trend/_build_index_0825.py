# -*- coding: utf-8 -*-
import re, sys, subprocess

BASE = "G:/ai/股票/market-trend/index.html"
with open(BASE, encoding="utf-8") as f:
    html = f.read()

reps = [
 # weekend gap marker -> between 08-21(447) and 08-24(543), midpoint 495
 ('          <line x1="582" y1="40" x2="582" y2="200" stroke="#b8893b" stroke-width="1.2" stroke-dasharray="5 4"/>\n          <text class="axislab" x="582" y="34" text-anchor="middle" fill="#b8893b">08-22/23 休市</text>',
  '          <line x1="495" y1="40" x2="495" y2="200" stroke="#b8893b" stroke-width="1.2" stroke-dasharray="5 4"/>\n          <text class="axislab" x="495" y="34" text-anchor="middle" fill="#b8893b">08-22/23 休市</text>'),
 # area polygon
 ('          <polygon fill="url(#area)" points="60,75.2 176,139.2 292,187.2 408,83.2 524,128.0 640,158.4 640,200 60,200"/>',
  '          <polygon fill="url(#area)" points="60,75.2 157,139.2 253,187.2 350,83.2 447,128.0 543,158.4 640,78.4 640,200 60,200"/>'),
 # polyline
 ('            points="60,75.2 176,139.2 292,187.2 408,83.2 524,128.0 640,158.4"/>',
  '            points="60,75.2 157,139.2 253,187.2 350,83.2 447,128.0 543,158.4 640,78.4"/>'),
 # circles + value labels
 ('''          <circle cx="60" cy="75.2" r="5" fill="#b8332a"/>
          <text class="vallab" x="60" y="62" text-anchor="middle">78%</text>
          <circle cx="176" cy="139.2" r="5" fill="#b8332a"/>
          <text class="vallab" x="176" y="156" text-anchor="middle">38%</text>
          <circle cx="292" cy="187.2" r="6" fill="#8a1810"/>
          <text class="vallab" x="292" y="204" text-anchor="middle" fill="#8a1810">8%</text>
          <circle cx="408" cy="83.2" r="5" fill="#b8332a"/>
          <text class="vallab" x="408" y="70" text-anchor="middle">73%</text>
          <circle cx="524" cy="128.0" r="5" fill="#b8332a"/>
          <text class="vallab" x="524" y="115" text-anchor="middle">45%</text>
          <circle cx="640" cy="158.4" r="5" fill="#b8332a"/>
          <text class="vallab" x="640" y="145" text-anchor="middle">26%</text>''',
  '''          <circle cx="60" cy="75.2" r="5" fill="#b8332a"/>
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
          <text class="vallab" x="640" y="65" text-anchor="middle">76%</text>'''),
 # day labels
 ('''          <text class="daylab" x="60" y="222" text-anchor="middle">08-17</text>
          <text class="daylab" x="176" y="222" text-anchor="middle">08-18</text>
          <text class="daylab" x="292" y="222" text-anchor="middle">08-19</text>
          <text class="daylab" x="408" y="222" text-anchor="middle">08-20</text>
          <text class="daylab" x="524" y="222" text-anchor="middle">08-21</text>
          <text class="daylab" x="640" y="222" text-anchor="middle">08-24</text>''',
  '''          <text class="daylab" x="60" y="222" text-anchor="middle">08-17</text>
          <text class="daylab" x="157" y="222" text-anchor="middle">08-18</text>
          <text class="daylab" x="253" y="222" text-anchor="middle">08-19</text>
          <text class="daylab" x="350" y="222" text-anchor="middle">08-20</text>
          <text class="daylab" x="447" y="222" text-anchor="middle">08-21</text>
          <text class="daylab" x="543" y="222" text-anchor="middle">08-24</text>
          <text class="daylab" x="640" y="222" text-anchor="middle">08-25</text>'''),
 # masthead updated
 ('<span data-i18n="t_updated">最近更新：2026-08-25（收录 08-17 ~ 08-24 共 6 期，08-22~08-23 周末休市）</span>',
  '<span data-i18n="t_updated">最近更新：2026-08-25（收录 08-17 ~ 08-25 共 7 期，08-22~08-23 周末休市）</span>'),
 # stats num 6 -> 7
 ('      <div class="num">6 <small data-i18n="s_issues">期</small></div>',
  '      <div class="num">7 <small data-i18n="s_issues">期</small></div>'),
 # stats span 08-24 -> 08-25
 ('      <div class="num">08-17<small> ~ 08-24</small></div>',
  '      <div class="num">08-17<small> ~ 08-25</small></div>'),
 # trend note (HTML)
 ('<p class="note" data-i18n="t_trend_note" style="font-size:.8rem;color:var(--muted)">08-19 广度崩至 8%（恐慌/踩踏），08-20 修复至 73%，08-21 反弹后分化回落至 45%，08-24 放量普跌广度再崩至 26%。08-22~08-23 周末休市无交易。全线 6 期风险等级均为「高」。</p>',
  '<p class="note" data-i18n="t_trend_note" style="font-size:.8rem;color:var(--muted)">08-19 广度崩至 8%（恐慌/踩踏），08-20 修复至 73%，08-21 反弹后分化回落至 45%，08-24 放量普跌广度再崩至 26%，08-25 缩量普涨广度暴拉回 76%（官方「狂热」标签与真实广度共振向上，但量缩、技术极弱 = 低质量反弹）。08-22~08-23 周末休市无交易；08-25 为最新一期。全线 7 期风险等级均为「高」。</p>'),
 # traj note (HTML)
 ('<p class="note" data-i18n="t_traj_note" style="font-size:.8rem;color:var(--muted)">六阶段框架：绝望 → 怀疑 → 乐观 → 狂热 → 焦虑 → 自满。本序列由 08-17「狂热」经分歧、恐慌，08-21 回落至「怀疑（分歧加剧）」，08-24 进一步转入「恐慌 / 退潮」（广度崩塌）。08-22~08-23 周末休市。</p>',
  '<p class="note" data-i18n="t_traj_note" style="font-size:.8rem;color:var(--muted)">六阶段框架：绝望 → 怀疑 → 乐观 → 狂热 → 焦虑 → 自满。本序列由 08-17「狂热」经分歧、恐慌，08-21 回落至「怀疑（分歧加剧）」，08-24 转入「恐慌 / 退潮」（广度崩塌），08-25 由恐慌回「修复 / 分歧（弱反弹）」（缩量普涨、广度回暖至 76%，但量缩、技术极弱）。08-22~08-23 周末休市。</p>'),
 # REPORTS: append 08-25
 ('''      summaryEn:"Up-ratio collapses to 26%, 48 limit-up, 14 limit-down, turnover expands to ¥2.007tn (+128.2bn); tech sold at open, funds rotate to low-level defensives + precious metals; official 'Neutral' tag diverges from real 26% breadth = breadth collapse."
    }
  ];''',
  '''      summaryEn:"Up-ratio collapses to 26%, 48 limit-up, 14 limit-down, turnover expands to ¥2.007tn (+128.2bn); tech sold at open, funds rotate to low-level defensives + precious metals; official 'Neutral' tag diverges from real 26% breadth = breadth collapse."
    }
    ,
    {
      file:"crowd-psychology-risk-radar-20260825.html", date:"2026-08-25",
      risk:"高", riskEn:"High",
      cycleZh:"修复 / 分歧（弱反弹）", cycleEn:"Repair / Divergence (weak bounce)",
      cycleNoteZh:"缩量普涨 / 低质量反弹", cycleNoteEn:"Volume-shrinking rally / low-quality bounce",
      up:"76%", limitup:"70", board:"5板", turn:"¥1.8318万亿",
      summaryZh:"涨股比暴拉至76%、涨停70、跌停4、成交缩至¥1.8318万亿（−1756亿）；官方「狂热」标签与真实76%广度共振向上，但量缩、小盘占优、技术极弱、估值偏高 = 缩量普涨 / 低质量反弹。",
      summaryEn:"Up-ratio roars to 76%, 70 limit-up, 4 limit-down, turnover shrinks to ¥1.8318tn (−175.6bn); official 'Euphoria' tag aligns upward with real 76% breadth, yet volume-down, small-cap led, technics weak, valuation high = volume-shrinking rally / low-quality bounce."
    }
  ];'''),
 # I18N zh
 ('      t_updated:"最近更新：2026-08-25（收录 08-17 ~ 08-24 共 6 期，08-22~08-23 周末休市）",',
  '      t_updated:"最近更新：2026-08-25（收录 08-17 ~ 08-25 共 7 期，08-22~08-23 周末休市）",'),
 ('      s_all:"全部", s_risk_lbl:"各期风险等级（6 期同为「高」）",',
  '      s_all:"全部", s_risk_lbl:"各期风险等级（7 期同为「高」）",'),
 ('      s_span_lbl:"覆盖交易日跨度（08-22~08-23 周末休市）",',
  '      s_span_lbl:"覆盖交易日跨度（08-22~08-23 周末休市；最新 08-25）",'),
 ('      t_trend:"涨股比走势（市场广度）", t_trend_note:"08-19 广度崩至 8%（恐慌/踩踏），08-20 修复至 73%，08-21 反弹后分化回落至 45%，08-24 放量普跌广度再崩至 26%。08-22~08-23 周末休市无交易。全线 6 期风险等级均为「高」。",',
  '      t_trend:"涨股比走势（市场广度）", t_trend_note:"08-19 广度崩至 8%（恐慌/踩踏），08-20 修复至 73%，08-21 反弹后分化回落至 45%，08-24 放量普跌广度再崩至 26%，08-25 缩量普涨广度暴拉回 76%（官方「狂热」标签与真实广度共振向上，但量缩、技术极弱 = 低质量反弹）。08-22~08-23 周末休市无交易；08-25 为最新一期。全线 7 期风险等级均为「高」。",'),
 ('      t_traj:"情绪周期轨迹（六阶段定位）", t_traj_note:"六阶段框架：绝望 → 怀疑 → 乐观 → 狂热 → 焦虑 → 自满。本序列由 08-17「狂热」经分歧、恐慌，08-21 回落至「怀疑（分歧加剧）」，08-24 进一步转入「恐慌 / 退潮」（广度崩塌）。08-22~08-23 周末休市。",',
  '      t_traj:"情绪周期轨迹（六阶段定位）", t_traj_note:"六阶段框架：绝望 → 怀疑 → 乐观 → 狂热 → 焦虑 → 自满。本序列由 08-17「狂热」经分歧、恐慌，08-21 回落至「怀疑（分歧加剧）」，08-24 转入「恐慌 / 退潮」（广度崩塌），08-25 由恐慌回「修复 / 分歧（弱反弹）」（缩量普涨、广度回暖至 76%，但量缩、技术极弱）。08-22~08-23 周末休市。",'),
 # I18N en
 ('      t_updated:"Last updated: 2026-08-25 (6 issues, 08-17 ~ 08-24; 08-22/23 weekend closed)",',
  '      t_updated:"Last updated: 2026-08-25 (7 issues, 08-17 ~ 08-25; 08-22/23 weekend closed)",'),
 ('      s_all:"all", s_risk_lbl:"Risk level per issue (all 6 = High)",',
  '      s_all:"all", s_risk_lbl:"Risk level per issue (all 7 = High)",'),
 ('      s_span_lbl:"Trading-day coverage span (08-22/23 weekend closed)",',
  '      s_span_lbl:"Trading-day coverage span (08-22/23 weekend closed; latest 08-25)",'),
 ('      t_trend:"Up-Stock Ratio Trend (Breadth)", t_trend_note:"Breadth collapsed to 8% on 08-19 (panic/sell-off), rebounded to 73% on 08-20, fell back to 45% on 08-21 post-rebound divergence, then collapsed again to 26% on 08-24 amid broad sell-off on higher volume. 08-22/23 weekend closed. All 6 issues rated High risk.",',
  '      t_trend:"Up-Stock Ratio Trend (Breadth)", t_trend_note:"Breadth collapsed to 8% on 08-19 (panic), rebounded to 73% on 08-20, fell to 45% on 08-21, collapsed again to 26% on 08-24 amid broad sell-off, then roared back to 76% on 08-25 in a volume-shrinking rally (official \'Euphoria\' tag now aligns upward with real breadth, yet volume-down & technics weak = low-quality bounce). 08-22/23 weekend closed; 08-25 is the latest issue. All 7 issues rated High risk.",'),
 ('      t_traj:"Sentiment Cycle Path (6-stage)", t_traj_note:"Six-stage frame: Despair → Doubt → Optimism → Euphoria → Anxiety → Complacency. Path runs from 08-17 Euphoria through divergence & panic, to Doubt (divergence intensifying) on 08-21, then into Panic / Washout (breadth collapse) on 08-24. 08-22/23 weekend closed.",',
  '      t_traj:"Sentiment Cycle Path (6-stage)", t_traj_note:"Six-stage frame: Despair → Doubt → Optimism → Euphoria → Anxiety → Complacency. Path runs from 08-17 Euphoria through divergence & panic, to Doubt (divergence intensifying) on 08-21, into Panic / Washout (breadth collapse) on 08-24, then 08-25 shifts from panic back to Repair / Divergence (weak bounce) — volume-shrinking rally, breadth recovers to 76%, yet volume-down & technics weak. 08-22/23 weekend closed.",'),
]

for i,(old,new) in enumerate(reps):
    cnt = html.count(old)
    if cnt != 1:
        print("WARN rep#%d count=%d" % (i, cnt));
    html = html.replace(old, new)

# assertions
must_present = [
    "crowd-psychology-risk-radar-20260825.html", "08-25 缩量普涨广度暴拉回 76%",
    "08-25 由恐慌回「修复 / 分歧（弱反弹）」", "76%</text>", "08-25</text>",
    "收录 08-17 ~ 08-25 共 7 期", "7 期同为「高」",
]
for g in must_present:
    if g not in html:
        print("FAIL missing:", g); sys.exit(1)
must_gone = ["08-17 ~ 08-24 共 6 期", "all 6 = High", "All 6 issues rated High",
             "全线 6 期风险等级均为「高」", "<div class=\"num\">6 <small", "x=\"640\" y=\"222\" text-anchor=\"middle\">08-24</text>"]
for g in must_gone:
    if g in html:
        print("FAIL still present:", g); sys.exit(1)
print("index content assertions passed")

# I18N coverage
used = set(re.findall(r'data-i18n="([^"]+)"', html))
m = re.search(r'  var I18N = \{(.*?)\n  \};', html, flags=re.S)
block = m.group(1)
def keys_of(lang):
    seg = re.search(lang + r':\{(.*?)\n    \}', block, flags=re.S).group(1)
    return set(re.findall(r'([A-Za-z_][A-Za-z0-9_]*):', seg))
zh, en = keys_of("zh"), keys_of("en")
if used - zh: print("MISSING zh:", sorted(used-zh)); sys.exit(1)
if used - en: print("MISSING en:", sorted(used-en)); sys.exit(1)
print("I18N coverage OK (used=%d)" % len(used))

# external refs + JS syntax
ext = re.findall(r'https?://', html)
src = re.findall(r'<script[^>]*\ssrc=', html)
print("external http(s):", len(ext), "script src:", len(src))
if ext or src: print("FAIL external"); sys.exit(1)
blocks = re.findall(r'<script>(.*?)</script>', html, flags=re.S)
open("G:/ai/股票/market-trend/_check_idx.js","w",encoding="utf-8").write("\n".join(blocks))
r = subprocess.run(["C:/Users/nonoy/.workbuddy/binaries/node/versions/22.22.2/node.exe","--check","G:/ai/股票/market-trend/_check_idx.js"],capture_output=True,text=True)
print("node --check rc=", r.returncode)
if r.returncode!=0: print(r.stdout,r.stderr); sys.exit(1)
print("JS syntax OK")

with open(BASE,"w",encoding="utf-8") as f:
    f.write(html)
print("Written:", BASE)
