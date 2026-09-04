# -*- coding: utf-8 -*-
"""把群体心理风险雷达日报索引（market-trend/index.html）补齐到 2026-09-02：
1) t_updated / 期数(10->11) / 跨度(08-31->09-02)
2) REPORTS 数组新增 09-02 卡片（置于末尾，render 时 reverse 后居首）
3) 涨股比走势 SVG 增加 09-02(28%) 点，x 轴均分 11 点（60~810，间距75）
不改动任何既有数据，仅追加最新一期。"""
import os, io
HERE = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(HERE, "..", "web", "psychology", "index.html")
s = open(PATH, encoding="utf-8").read()

reps = 0
def rep(old, new):
    global s, reps
    assert old in s, "未命中: " + old[:50]
    s = s.replace(old, new, 1); reps += 1

# ---- 1) 元数据 ----
rep('最近更新：2026-08-31（收录 08-17 ~ 08-31 共 10 期，08-22~08-23 与 08-29~08-30 周末休市）',
    '最近更新：2026-09-02（收录 08-17 ~ 09-02 共 11 期，08-22~08-23 与 08-29~08-30 周末休市）')
rep('Last updated: 2026-08-31 (10 issues, 08-17 ~ 08-31; 08-22/23 & 08-29/30 weekend closed)',
    'Last updated: 2026-09-02 (11 issues, 08-17 ~ 09-02; 08-22/23 & 08-29/30 weekend closed)')
rep('<div class="num">10 <small data-i18n="s_issues">期</small></div>',
    '<div class="num">11 <small data-i18n="s_issues">期</small></div>')
rep('s_risk_lbl:"各期风险等级（10 期同为「高」）"',
    's_risk_lbl:"各期风险等级（11 期同为「高」）"')
rep('s_risk_lbl:"Risk level per issue (all 10 = High)"',
    's_risk_lbl:"Risk level per issue (all 11 = High)"')
rep('s_span_lbl:"覆盖交易日跨度（08-22~08-23 与 08-29~08-30 周末休市；最新 08-31）"',
    's_span_lbl:"覆盖交易日跨度（08-22~08-23 与 08-29~08-30 周末休市；最新 09-02）"')
rep('s_span_lbl:"Trading-day coverage span (08-22/23 & 08-29/30 weekend closed; latest 08-31)"',
    's_span_lbl:"Trading-day coverage span (08-22/23 & 08-29/30 weekend closed; latest 09-02)"')
rep('<div class="num">08-17<small> ~ 08-31</small></div>',
    '<div class="num">08-17<small> ~ 09-02</small></div>')

# ---- 2) REPORTS 数组新增 09-02 卡片（插在末尾，reverse 后居首）----
REP = '''    }
    ,
    {
      file:"crowd-psychology-risk-radar-20260902.html", date:"2026-09-02",
      risk:"高", riskEn:"High",
      cycleZh:"缩量普跌 / 情绪退潮", cycleEn:"Volume-shrink selloff / sentiment ebb",
      cycleNoteZh:"涨股比崩塌 / 广度崩塌", cycleNoteEn:"Breadth crash / participation cliff",
      up:"28%", limitup:"51", board:"5板", turn:"¥1.79万亿",
      summaryZh:"涨股比由57%骤降至28%、涨停51、跌停3、成交缩至¥1.79万亿（−3420亿）；三指齐跌（上证−0.97%/深成−1.88%/创业板−2.39%），MACD红柱与指数背离=顶背离，仅地面兵装Ⅱ逆势独涨+6.48%（长城军工+10.04%）；融资单日逆势加仓（中国巨石+3.9986亿居首），杠杆与市场背离，追涨与踩踏风险并存 = 缩量普跌 / 情绪退潮。",
      summaryEn:"Up-ratio crashes 57%→28%, 51 limit-up, 3 limit-down, turnover shrinks to ¥1.79tn (−342bn); all three indices down (SSE −0.97% / SZ −1.88% / ChiNext −2.39%), MACD red vs index-down = top divergence, only Ground-arm EquipmentⅡ rises alone +6.48% (Great Wall Military +10.04%); margin daily adds against the tide (China Jushi +¥0.3999bn leads), leverage diverges from market, chase & stampede risks coexist = volume-shrink selloff / sentiment ebb."
    }
  ];'''
rep('    }\n  ];', REP)

# ---- 3) 涨股比走势 SVG：追加 09-02(28%) 点，x 均分 11 点 ----
rep('          <polygon fill="url(#area)" points="60,108.8 142.5,102.4 225.0,115.2 307.5,78.4 390.0,158.4 472.5,128.0 555.0,83.2 637.5,187.2 720.0,139.2 802.5,75.2 810.0,200 60,200"/>',
    '          <polygon fill="url(#area)" points="60,155.2 135,108.8 210,102.4 285,115.2 360,78.4 435,158.4 510,128.0 585,83.2 660,187.2 735,139.2 810,75.2 810,200 60,200"/>')
rep('            points="60,108.8 142.5,102.4 225.0,115.2 307.5,78.4 390.0,158.4 472.5,128.0 555.0,83.2 637.5,187.2 720.0,139.2 802.5,75.2"/>',
    '            points="60,155.2 135,108.8 210,102.4 285,115.2 360,78.4 435,158.4 510,128.0 585,83.2 660,187.2 735,139.2 810,75.2"/>')
rep('          <!-- points + value labels (08-31 left -> 08-17 right) -->',
    '          <!-- points + value labels (09-02 left -> 08-17 right) -->')
rep('          <line x1="431" y1="40" x2="431" y2="200" stroke="#b8893b" stroke-width="1.2" stroke-dasharray="5 4"/>',
    '          <line x1="472.5" y1="40" x2="472.5" y2="200" stroke="#b8893b" stroke-width="1.2" stroke-dasharray="5 4"/>')

OLD_C = '''          <circle cx="60" cy="108.8" r="5" fill="#b8332a"/>
          <text class="vallab" x="60" y="95" text-anchor="middle">57%</text>
          <circle cx="142.5" cy="102.4" r="5" fill="#b8332a"/>
          <text class="vallab" x="142.5" y="89" text-anchor="middle">61%</text>
          <circle cx="225.0" cy="115.2" r="5" fill="#b8332a"/>
          <text class="vallab" x="225.0" y="102" text-anchor="middle">53%</text>
          <circle cx="307.5" cy="78.4" r="5" fill="#b8332a"/>
          <text class="vallab" x="307.5" y="65" text-anchor="middle">76%</text>
          <circle cx="390.0" cy="158.4" r="5" fill="#b8332a"/>
          <text class="vallab" x="390.0" y="175" text-anchor="middle">26%</text>
          <circle cx="472.5" cy="128.0" r="5" fill="#b8332a"/>
          <text class="vallab" x="472.5" y="115" text-anchor="middle">45%</text>
          <circle cx="555.0" cy="83.2" r="5" fill="#b8332a"/>
          <text class="vallab" x="555.0" y="70" text-anchor="middle">73%</text>
          <circle cx="637.5" cy="187.2" r="6" fill="#8a1810"/>
          <text class="vallab" x="637.5" y="204" text-anchor="middle" fill="#8a1810">8%</text>
          <circle cx="720.0" cy="139.2" r="5" fill="#b8332a"/>
          <text class="vallab" x="720.0" y="156" text-anchor="middle">38%</text>
          <circle cx="802.5" cy="75.2" r="5" fill="#b8332a"/>
          <text class="vallab" x="802.5" y="62" text-anchor="middle">78%</text>'''
NEW_C = '''          <circle cx="60" cy="155.2" r="6" fill="#8a1810"/>
          <text class="vallab" x="60" y="142" text-anchor="middle" fill="#8a1810">28%</text>
          <circle cx="135" cy="108.8" r="5" fill="#b8332a"/>
          <text class="vallab" x="135" y="95" text-anchor="middle">57%</text>
          <circle cx="210" cy="102.4" r="5" fill="#b8332a"/>
          <text class="vallab" x="210" y="89" text-anchor="middle">61%</text>
          <circle cx="285" cy="115.2" r="5" fill="#b8332a"/>
          <text class="vallab" x="285" y="102" text-anchor="middle">53%</text>
          <circle cx="360" cy="78.4" r="5" fill="#b8332a"/>
          <text class="vallab" x="360" y="65" text-anchor="middle">76%</text>
          <circle cx="435" cy="158.4" r="5" fill="#b8332a"/>
          <text class="vallab" x="435" y="175" text-anchor="middle">26%</text>
          <circle cx="510" cy="128.0" r="5" fill="#b8332a"/>
          <text class="vallab" x="510" y="115" text-anchor="middle">45%</text>
          <circle cx="585" cy="83.2" r="5" fill="#b8332a"/>
          <text class="vallab" x="585" y="70" text-anchor="middle">73%</text>
          <circle cx="660" cy="187.2" r="6" fill="#8a1810"/>
          <text class="vallab" x="660" y="204" text-anchor="middle" fill="#8a1810">8%</text>
          <circle cx="735" cy="139.2" r="5" fill="#b8332a"/>
          <text class="vallab" x="735" y="156" text-anchor="middle">38%</text>
          <circle cx="810" cy="75.2" r="5" fill="#b8332a"/>
          <text class="vallab" x="810" y="62" text-anchor="middle">78%</text>'''
rep(OLD_C, NEW_C)

OLD_D = '''          <text class="daylab" x="60" y="222" text-anchor="middle">08-31</text>
          <text class="daylab" x="142.5" y="222" text-anchor="middle">08-27</text>
          <text class="daylab" x="225.0" y="222" text-anchor="middle">08-26</text>
          <text class="daylab" x="307.5" y="222" text-anchor="middle">08-25</text>
          <text class="daylab" x="390.0" y="222" text-anchor="middle">08-24</text>
          <text class="daylab" x="472.5" y="222" text-anchor="middle">08-21</text>
          <text class="daylab" x="555.0" y="222" text-anchor="middle">08-20</text>
          <text class="daylab" x="637.5" y="222" text-anchor="middle">08-19</text>
          <text class="daylab" x="720.0" y="222" text-anchor="middle">08-18</text>
          <text class="daylab" x="802.5" y="222" text-anchor="middle">08-17</text>'''
NEW_D = '''          <text class="daylab" x="60" y="222" text-anchor="middle">09-02</text>
          <text class="daylab" x="135" y="222" text-anchor="middle">08-31</text>
          <text class="daylab" x="210" y="222" text-anchor="middle">08-27</text>
          <text class="daylab" x="285" y="222" text-anchor="middle">08-26</text>
          <text class="daylab" x="360" y="222" text-anchor="middle">08-25</text>
          <text class="daylab" x="435" y="222" text-anchor="middle">08-24</text>
          <text class="daylab" x="510" y="222" text-anchor="middle">08-21</text>
          <text class="daylab" x="585" y="222" text-anchor="middle">08-20</text>
          <text class="daylab" x="660" y="222" text-anchor="middle">08-19</text>
          <text class="daylab" x="735" y="222" text-anchor="middle">08-18</text>
          <text class="daylab" x="810" y="222" text-anchor="middle">08-17</text>'''
rep(OLD_D, NEW_D)

open(PATH, "w", encoding="utf-8").write(s)
print(f"[ok] 替换 {reps} 处，写出 {PATH} ({len(s)} bytes)")
print("09-02 卡片存在:", 'crowd-psychology-risk-radar-20260902.html' in s)
print("期数 11 存在:", '共 11 期' in s, "| 跨度 09-02 存在:", '~ 09-02' in s)
print("SVG 28% 点存在:", '>28%</text>' in s)
