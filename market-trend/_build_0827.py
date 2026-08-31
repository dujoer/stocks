# -*- coding: utf-8 -*-
import re, sys

SRC = "crowd-psychology-risk-radar-20260826.html"
OUT = "crowd-psychology-risk-radar-20260827.html"
I18N_FILE = "_i18n_0827.txt"

html = open(SRC, encoding="utf-8").read()
i18n = open(I18N_FILE, encoding="utf-8").read().strip()

# ---- 1. replace entire I18N block ----
html, n_i18n = re.subn(r'var I18N = \{[\s\S]*?\n  \};', i18n, html, count=1)
assert n_i18n == 1, ("I18N replace count", n_i18n)

# ---- 2. replace BIAS array (08-27) ----
bias = r'''var BIAS = [
    {zh:"羊群效应",en:"Herding",sev:4,zhd:"涨股比61%偏多、成交放量至¥2.1259万亿、权重与小盘共振，资金扎堆电子硬件（非金属材料+9.63%/半导体+4.54%/元件+5.09%）与连板（深中华A 5板），跟随放量反包而非独立判断。",end:"Up-ratio 61% net-long, turnover expanded to ¥2.1259tn, weights & small-caps resonated; capital crowds electronics hardware (non-metal +9.63%/semis +4.54%/components +5.09%) and streaks (Shenzhen China-A 5 boards) — following the volume-expanded rebound, not conviction."},
    {zh:"损失厌恶",en:"Loss Aversion",sev:3,zhd:"在放量反包中融资追涨电子硬件（新易盛+3.11亿/剑桥科技+2.82亿/英维克+2.75亿），把前期浮亏当已发生损失回避止损、在放量上涨中反手加仓高位科技。",end:"In the volume-expanded rebound, margin chases electronics hardware (Neways +0.311bn/CIGC +0.282bn/Envicool +0.275bn) — avoiding the realized loss, doubling down on high-level tech on rising volume."},
    {zh:"心理账户/赌徒谬误",en:"Mental Acct / Gambler",sev:3,zhd:"创业板60日-15.76%下仍在放量反包中博弈科技/资源反弹（新易盛+3.11亿），把亏损仓当赌资、博「AI算力/资源刚需」回本。",end:"Amid ChiNext 60d -15.76% still margin-betting on tech/resource rebound (Neways +0.311bn) in a volume-expanded rebound; treating loss books as gambling capital."},
    {zh:"过度自信",en:"Overconfidence",sev:4,zhd:"技术面「极强」延续+三大指数齐涨且涨幅扩大（上证+1.13%/深成+1.50%/创业板+1.71%），误判「反转」，把单日放量反包当趋势恢复、追电子硬件/非金属材料，忽视趋势仍弱势下跌、估值偏高、结构分化（银行/光伏/白电领跌）。",end:"Reading technics 'extremely strong' + all-three-up with widening gains (SH +1.13%/SZ +1.50%/ChiNext +1.71%) as 'reversal', treating a single-day volume-expanded rebound as trend recovery, chasing electronics/non-metal — ignoring trend still weak-down, valuation elevated, structural divergence (banks/PV/white-appliances lag)."},
    {zh:"处置效应",en:"Disposition",sev:3,zhd:"反弹中卖盈（光伏设备-2.33%中微导纳米+8.19%个股强但板块弱，获利了结）持亏（资源/科技套牢未割），结构分化、调仓滞后。",end:"Selling winners (PV equipment -2.33% yet Micro-conductor +8.19% stock-strong but sector-weak, profit-taking) while holding losers (resources/tech traps untrimmed) — split structure, lagging rotation."},
    {zh:"锚定偏差",en:"Anchoring",sev:3,zhd:"锚定前期高点与官方「狂热」标签（涨停>50触发、涨股比61%<70%阈值），难接受趋势仍弱势下跌（创业板60日-15.76%、深成60日-10.54%）与放量但结构分化的现实。",end:"Anchored to prior highs and the official 'Euphoria' tag (triggered by limit-up>50, real up-ratio 61%<70%); rejecting mid-term weakness (ChiNext 60d -15.76%, SZSE 60d -10.54%) and the volume-up-but-divergent reality."},
    {zh:"确认偏误",en:"Confirmation Bias",sev:4,zhd:"只看技术「极强」+涨停78+三指齐涨+放量，忽略趋势方向仍弱势下跌（长短线均偏弱）、估值偏高（PE分位70-90%）、真实涨股比仅61%（官方狂热标签略超前广度）、结构分化（银行/光伏/白电领跌）。",end:"Only watching technics 'extremely strong' + 78 limit-ups + all-three-up + volume-up, ignoring trend direction still weak-down, valuation elevated (PE pctile 70-90%), real up-ratio only 61% (official Euphoria tag slightly ahead of breadth), structural divergence (banks/PV/white-appliances lag)."},
    {zh:"近因偏差",en:"Recency",sev:3,zhd:"外推08-25普涨+08-26反包+08-27放量反包的「回暖」，对趋势仍弱势下跌（创业板60日-15.76%）与结构分化反应钝化。",end:"Extrapolating 08-25 broad rally + 08-26 rebound + 08-27 volume-expanded rebound 'recovery'; blunted by the mid-term weakness (ChiNext 60d -15.76%) and structural divergence."},
    {zh:"叙事偏差",en:"Narrative",sev:4,zhd:"「电子硬件/AI算力/资源刚需」叙事在放量反包中仍被资金强化（非金属材料+9.63%/半导体+4.54%/融资追涨新易盛+3.11亿），故事未证伪且被加仓自我实现，但估值偏高下叙事脆弱。",end:"The 'electronics/AI-compute/resource-must-have' narrative reinforced by capital even in a volume-expanded rebound (non-metal +9.63%/semis +4.54%/margin chasing Neways +0.311bn) — story un-falsified, self-reinforced by buying, but fragile under elevated valuation."},
    {zh:"代表性启发",en:"Representativeness",sev:3,zhd:"被非金属材料+9.63%（联瑞新材+20.00%）/半导体+4.54%（赛微电子+20.01%）单日赚钱效应代表，误判市场全面转暖、忽视放量反包下的结构分化（银行/光伏/白电领跌）与涨股比仅61%。",end:"Non-metal +9.63% (Lianrui +20.00%) / semis +4.54% (Saiwei +20.01%) profit taken as representative; mistaking a sector rally for a broad turn, ignoring the volume-expanded rebound's structural divergence (banks/PV/white-appliances lag) and up-ratio only 61%."}
  ];'''
html, n_bias = re.subn(r'var BIAS = \[[\s\S]*?\n  \];', bias, html, count=1)
assert n_bias == 1, ("BIAS replace count", n_bias)

# ---- 3. static body replacements (08-26 -> 08-27) ----
repls = [
  # masthead date
  ('<b>2026-08-26 收盘（北京时间，盘后）</b>', '<b>2026-08-27 收盘（北京时间，盘后）</b>'),
  # chips
  ('<span class="chip"><span data-i18n="c_upratio">涨股比</span> <b>53%</b></span>',
   '<span class="chip"><span data-i18n="c_upratio">涨股比</span> <b>61%</b></span>'),
  ('<span class="chip"><span data-i18n="c_limitup">涨停</span> <b>56</b></span>',
   '<span class="chip"><span data-i18n="c_limitup">涨停</span> <b>78</b></span>'),
  ('<span class="chip"><span data-i18n="c_turn">两市成交</span> <b>¥1.8087万亿</b></span>',
   '<span class="chip"><span data-i18n="c_turn">两市成交</span> <b>¥2.1259万亿</b></span>'),
  # radar polygon (geometry recomputed from 08-26 vertices)
  ('<polygon points="160,84 237,123 200,191 160,166 112,200 57,115"',
   '<polygon points="160,75 235,124 207,198 160,171 107,205 55,114"'),
  # radar value labels (split to avoid whitespace ambiguity)
  ('<text x="160" y="80">60</text><text x="239" y="119">66</text><text x="202" y="187">46</text>',
   '<text x="160" y="71">68</text><text x="237" y="120">64</text><text x="209" y="194">54</text>'),
  ('<text x="160" y="162">38</text><text x="112" y="196">60</text><text x="57" y="119">88</text>',
   '<text x="160" y="167">50</text><text x="109" y="201">66</text><text x="55" y="118">90</text>'),
  # radar vertex circles
  ('<circle cx="160" cy="86" r="3.2"/>', '<circle cx="160" cy="75" r="3.2"/>'),
  ('<circle cx="244" cy="121" r="3.2"/>', '<circle cx="235" cy="124" r="3.2"/>'),
  ('<circle cx="202" cy="193" r="3.2"/>', '<circle cx="207" cy="198" r="3.2"/>'),
  ('<circle cx="160" cy="160" r="3.2"/>', '<circle cx="160" cy="171" r="3.2"/>'),
  ('<circle cx="110" cy="202" r="3.2"/>', '<circle cx="107" cy="205" r="3.2"/>'),
  ('<circle cx="57" cy="115" r="3.2"/>', '<circle cx="55" cy="114" r="3.2"/>'),
  # breadth bar rects
  ('<rect x="14" y="14" width="265" height="26" fill="#d8392b"/>',
   '<rect x="14" y="14" width="305" height="26" fill="#d8392b"/>'),
  ('<rect x="279" y="14" width="220" height="26" fill="#1a9e5a"/>',
   '<rect x="319" y="14" width="175" height="26" fill="#1a9e5a"/>'),
  # breadth % texts
  ('<text x="147" y="33" fill="#fff" font-size="14" font-weight="800" text-anchor="middle">53%</text>',
   '<text x="167" y="33" fill="#fff" font-size="14" font-weight="800" text-anchor="middle">61%</text>'),
  ('<text x="389" y="33" fill="#fff" font-size="14" font-weight="800" text-anchor="middle">44%</text>',
   '<text x="407" y="33" fill="#fff" font-size="14" font-weight="800" text-anchor="middle">35%</text>'),
  ('<text x="514" y="33" fill="#6b675f" font-size="11" font-weight="700" text-anchor="end">3% 平盘</text>',
   '<text x="514" y="33" fill="#6b675f" font-size="11" font-weight="700" text-anchor="end">4% 平盘</text>'),
  # breadth stat numbers
  ('<text x="340" y="72" fill="#d8392b">2946</text>', '<text x="340" y="72" fill="#d8392b">3394</text>'),
  ('<text x="340" y="92" fill="#1a9e5a">2448</text>', '<text x="340" y="92" fill="#1a9e5a">1944</text>'),
  ('<text x="340" y="112" fill="#6b675f">156</text>', '<text x="340" y="112" fill="#6b675f">212</text>'),
  ('<text x="340" y="138" fill="#d8392b">56</text>', '<text x="340" y="138" fill="#d8392b">78</text>'),
  ('<text x="340" y="158" fill="#1a9e5a">2</text>', '<text x="340" y="158" fill="#1a9e5a">4</text>'),
  ('<text x="340" y="184" fill="#1c1b19">¥1.8087万亿</text>', '<text x="340" y="184" fill="#1c1b19">¥2.1259万亿</text>'),
  # breadth change annotations
  ('<text x="355" y="72">（占 53%，较前日 −23pct）</text>', '<text x="355" y="72">（占 61%，较前日 +8pct）</text>'),
  ('<text x="355" y="92">（占 44%，较前日 +22pct）</text>', '<text x="355" y="92">（占 35%，较前日 −18pct）</text>'),
  ('<text x="355" y="112">（占 3%）</text>', '<text x="355" y="112">（占 4%）</text>'),
  ('<text x="355" y="138">（较前日 −14 只，连板高度维持 5板）</text>', '<text x="355" y="138">（较前日 +22 只，连板高度维持 5板）</text>'),
  ('<text x="355" y="158">（较前日 −2 只）</text>', '<text x="355" y="158">（较前日 +2 只）</text>'),
  ('<text x="355" y="184">（环比 −231亿，继续缩量）</text>', '<text x="355" y="184">（环比 +3172亿，放量）</text>'),
  # evidence: upratio cell
  ('<td><span class="val up">53%</span>（涨2946 / 跌2448 / 平156）</td>',
   '<td><span class="val up">61%</span>（涨3394 / 跌1944 / 平212）</td>'),
  # evidence: limit cell
  ('<td><span class="val up">56</span> / <span class="val down">2</span></td>',
   '<td><span class="val up">78</span> / <span class="val down">4</span></td>'),
  # evidence: amount cell
  ('<td><span class="val">≈¥1.8087万亿</span>（较前日 −231亿，继续缩量）</td>',
   '<td><span class="val">≈¥2.1259万亿</span>（较前日 +3172亿，放量）</td>'),
  # evidence: index values (full-width space U+3000 preserved)
  ('<td><span class="val up">3912.52　+0.59%</span></td>',
   '<td><span class="val up">3956.57　+1.13%</span></td>'),
  ('<td><span class="val up">13841.33　+0.69%</span></td>',
   '<td><span class="val up">14048.88　+1.50%</span></td>'),
  ('<td><span class="val up">3414.88　+0.51%</span></td>',
   '<td><span class="val up">3473.35　+1.71%</span></td>'),
  # evidence: secup cell (领涨)
  ('<td><span class="val up">造纸 +3.79%</span>（青山纸业 +10.16%）<br>工业金属 +3.33%（精艺股份 +10.03%）/ 证券Ⅱ +2.75%（锦龙股份 +10.05%）/ 冶钢原料 +2.71%<br>农化制品 +2.25%（新农股份 +9.99%）/ 保险Ⅱ +2.06% / 水泥 +2.01%（西藏天路 +6.44%）/ 酒店餐饮 +1.94%（华天酒店 +9.95%）</td>',
   '<td><span class="val up">非金属材料 +9.63%</span>（联瑞新材 +20.00%）<br>电子化学品 +5.56%（宏昌电子 +10.02%）/ 玻璃玻纤 +5.36%（中国巨石 +7.95%）/ 元件 +5.09%（生益电子 +14.32%）<br>半导体 +4.54%（赛微电子 +20.01%）/ 通信设备 +3.85% / 小金属 +4.00%</td>'),
  # evidence: secdn cell (领跌)
  ('<td><span class="val down">小家电 −1.35%</span>（由领涨转领跌）<br>出版 −1.44% / 医疗服务 −1.34% / 贵金属 −0.64% / 数字媒体 −1.10%<br>电机 −0.95% / 地面兵装 −0.89% / 工程机械 −0.88% / 食品加工 −0.64% / 游戏 −0.63%（半导体 0% / 通信设备 0% 横盘企稳）</td>',
   '<td><span class="val down">光伏设备 −2.33%</span>（微导纳米 +8.19% 个股强但板块弱）<br>白色家电 −1.56% / 股份制银行 −1.10%（中信银行）/ 国有大行 −1.16% / 电网设备 −1.21%<br>贵金属续弱 −0.64%</td>'),
  # evidence: board cell
  ('<td><span class="val up">连板高度 5 板</span>（深中华A — 接棒汉森制药）<br>4板：楚天龙；3板：海鸥住工<br>2板：华阳国际 / 冀衡医药 / 青山纸业 / 捷荣技术 / 康盛股份 / 青岛金王 / 华天酒店 / 豪尔赛 / 浙江世宝 / 万向德农<br>新热点：青山纸业 +10.16%（造纸）/ 锦龙股份 +10.05%（证券）/ 华天酒店 +9.95%（酒店）/ 万向德农 +10.03%（种植业）/ 新农股份 +9.99%（农化）</td>',
   '<td><span class="val up">连板高度 5 板</span>（深中华A — 数据源延迟取 08-26 收盘）<br>4板：楚天龙；3板：海鸥住工<br>2板：华阳国际 / 冀衡医药 / 青山纸业 / 捷荣技术 / 康盛股份 / 青岛金王 / 华天酒店 / 豪尔赛 / 浙江世宝 / 万向德农<br>新热点：联瑞新材 +20.00%（非金属材料）/ 赛微电子 +20.01%（半导体）/ 生益电子 +14.32%（元件）/ 中国巨石 +7.95%（玻璃玻纤）/ 宏昌电子 +10.02%（电子化学品）</td>'),
  # evidence: height cell
  ('<td><span class="val up">深中华A 5板</span>（2026-08-26）</td>',
   '<td><span class="val up">深中华A 5板</span>（数据源延迟取 2026-08-26）</td>'),
  # evidence: main cell (5d, delay-noted)
  ('<td>紫金矿业 <span class="val up">+34.96亿</span><br>洛阳钼业 +24.31亿 / C高凯 +23.98亿 / 英维克 +15.42亿 / 剑桥科技 +15.14亿<br>江西铜业 +14.10亿 / 白银有色 +13.14亿 / 长飞光纤 +13.00亿 / 比亚迪 +12.58亿 / 湖南白银 +12.43亿 / 兴业银锡 +12.19亿</td>',
   '<td>紫金矿业 <span class="val up">+34.96亿</span>（5日，数据源延迟取 08-26）<br>洛阳钼业 +24.31亿 / C高凯 +23.98亿 / 英维克 +15.42亿 / 剑桥科技 +15.14亿<br>江西铜业 +14.10亿 / 白银有色 +13.14亿 / 长飞光纤 +13.00亿 / 比亚迪 +12.58亿 / 湖南白银 +12.43亿 / 兴业银锡 +12.19亿</td>'),
  # evidence: margin cell (daily 08-27)
  ('<td>天孚通信 <span class="val up">+2.34亿</span>（光模块）<br>盐湖股份 +1.65亿 / 申菱环境 +1.62亿 / 兆易创新 +1.55亿 / 中油资本 +1.49亿<br>英维克 +1.44亿 / 宁德时代 +1.37亿</td>',
   '<td>新易盛 <span class="val up">+3.11亿</span>（光模块）<br>剑桥科技 +2.82亿 / 英维克 +2.75亿 / 同花顺 +2.60亿 / 海光信息 +2.09亿<br>罗博特科 +1.77亿 / 联特科技 +1.72亿</td>'),
  # evidence: hot cell
  ('<td>青山纸业 +10.16%（造纸）<br>锦龙股份 +10.05%（证券）/ 华天酒店 +9.95%（酒店）/ 万向德农 +10.03%（种植业）/ 新农股份 +9.99%（农化）<br>深中华A +10.04%（连板 5板）</td>',
   '<td>联瑞新材 +20.00%（非金属材料）<br>赛微电子 +20.01%（半导体）/ 生益电子 +14.32%（元件）/ 中国巨石 +7.95%（玻璃玻纤）/ 宏昌电子 +10.02%（电子化学品）<br>深中华A +10.04%（连板 5板，数据源延迟取 08-26）</td>'),
]

for i,(old,new) in enumerate(repls):
    c = html.count(old)
    if c != 1:
        sys.stderr.write("WARN repl %d count=%d: %r\n" % (i, c, old[:50]))
    html = html.replace(old, new)

open(OUT, "w", encoding="utf-8").write(html)
print("Written:", OUT, "len", len(html))

# ---- 4. validations ----
ext = len(re.findall(r'https?://', html))
srcref = len(re.findall(r'<script[^>]*\src=', html))
print("external http(s):", ext, "script src:", srcref)

# I18N key coverage
used = set(re.findall(r'data-i18n="([^"]+)"', html))
m = re.search(r'var I18N = \{([\s\S]*?)\n  \};', html)
block = m.group(1)
zh_keys, en_keys = set(), set()
cur = None
for line in block.splitlines():
    s = line.strip()
    if s.startswith('zh:{'): cur='zh'; continue
    if s.startswith('en:{'): cur='en'; continue
    if s in ('}','},'):
        continue
    for km in re.finditer(r'([A-Za-z0-9_]+)\s*:', s):
        k = km.group(1)
        if cur=='zh': zh_keys.add(k)
        elif cur=='en': en_keys.add(k)
missing_zh = used - zh_keys
missing_en = used - en_keys
print("used keys:", len(used), "zh:", len(zh_keys), "en:", len(en_keys))
print("missing zh:", missing_zh)
print("missing en:", missing_en)
assert not missing_zh and not missing_en

# must-present new strings
must = ["61%","¥2.1259万亿","78","3956.57","14048.88","3473.35",
        "新易盛","非金属材料 +9.63%","联瑞新材","光伏设备","放量反包","深中华A","5板"]
for s in must:
    assert s in html, ("missing present", s)
print("must-present OK")

# must-gone static old values (verified absent from 08-27 I18N + static cells).
# NOTE: 天孚通信 legitimately remains only inside the rc1_rep data-i18n *default fallback*
# text (08-24 stale), which is overwritten by the I18N JS at runtime — same as all prior reports.
gone = ["2946","2448","3912.52","13841.33","3414.88"]
for s in gone:
    assert s not in html, ("still present", s)
print("must-gone OK")
print("ALL STATIC CHECKS PASSED")
