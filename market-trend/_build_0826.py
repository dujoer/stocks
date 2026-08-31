# -*- coding: utf-8 -*-
import re, sys

SRC = "crowd-psychology-risk-radar-20260825.html"
OUT = "crowd-psychology-risk-radar-20260826.html"
I18N_FILE = "_i18n_0826.txt"

html = open(SRC, encoding="utf-8").read()
i18n = open(I18N_FILE, encoding="utf-8").read().strip()

# ---- 1. replace entire I18N block ----
html, n_i18n = re.subn(r'var I18N = \{[\s\S]*?\n  \};', i18n, html, count=1)
assert n_i18n == 1, ("I18N replace count", n_i18n)

# ---- 2. replace BIAS array ----
bias = r'''var BIAS = [
    {zh:"羊群效应",en:"Herding",sev:4,zhd:"涨股比53%仍偏多但成交继续缩至¥1.8087万亿、小盘占优（中证1000>沪深300），资金扎堆金融/工业金属/造纸（锦龙股份+10.05%/精艺股份+10.03%/青山纸业+10.16%）与连板（深中华A5板），跟随反包而非独立判断。",end:"Up-ratio 53% still net-long but turnover kept shrinking to ¥1.8087tn and small-caps led (CSI1000>CSI300); capital crowds finance/industrial-metals/paper (Jinlong +10.05%/Jingyi +10.03%/Qingshan +10.16%) and streaks (Shenzhen China-A 5 boards) — following the rebound, not conviction."},
    {zh:"损失厌恶",en:"Loss Aversion",sev:3,zhd:"08-26 无量反包中融资仍小幅回补（英维克+1.44亿），把前期浮亏当已发生损失回避止损、在缩量反弹中反手加仓高位科技/资源。",end:"In the 08-26 volume-less rebound, margin still slightly covers back (Envicool +0.144bn) — avoiding the realized loss, doubling down on high-level tech/resources in a shrinking-volume bounce."},
    {zh:"心理账户/赌徒谬误",en:"Mental Acct / Gambler",sev:3,zhd:"创业板60日-15.8%下仍在无量反包中博弈科技/资源反弹（天孚通信+2.34亿），把亏损仓当赌资、博「AI算力/资源刚需」回本。",end:"Amid ChiNext 60d -15.8% still margin-betting on tech/resource rebound (T&S +0.234bn) in a volume-less rebound; treating loss books as gambling capital."},
    {zh:"过度自信",en:"Overconfidence",sev:4,zhd:"技术面由「极弱」翻为「极强」+三大指数齐涨，误判「反转」，把单日无量反包当趋势恢复、追金融/工业金属（证券+2.75%/工业金属+3.33%），忽视趋势仍弱势下跌、估值偏高、量能继续萎缩。",end:"Reading technics flipped extremely-weak→strong + all three indices up as 'reversal', treating a single-day volume-less rebound as trend recovery, chasing finance/industrial-metals (securities +2.75%/industrial-metals +3.33%) — ignoring trend still weak-down, valuation elevated, volume keeps shrinking."},
    {zh:"处置效应",en:"Disposition",sev:3,zhd:"反弹中卖盈（小家电获利了结-1.35%，由领涨转领跌）持亏（资源/科技套牢未割），结构分化、调仓滞后。",end:"Selling winners (small-appliances profit-taking -1.35%, rolled from leader to lagger) while holding losers (resources/tech traps untrimmed) — split structure, lagging rotation."},
    {zh:"锚定偏差",en:"Anchoring",sev:3,zhd:"锚定前期高点与官方「狂热」标签（仅由涨停>50触发、涨股比53%未达70%阈值），难接受趋势仍弱势下跌（创业板60日-15.8%、深成60日-11.22%）与缩量现实。",end:"Anchored to prior highs and the official 'Euphoria' tag (triggered only by limit-up>50, real up-ratio 53%<70%); rejecting mid-term weakness (ChiNext 60d -15.8%, SZSE 60d -11.22%) and the volume-down reality."},
    {zh:"确认偏误",en:"Confirmation Bias",sev:4,zhd:"只看技术「极强」+涨停56+三大指数齐涨，忽略量能继续萎缩（¥1.8087万亿，环比−231亿）、趋势方向仍弱势下跌（长短线均2）、估值偏高（PE分位70-90%）、真实涨股比仅53%（官方狂热标签虚高）。",end:"Only watching technics 'extremely strong' + 56 limit-ups + all-three-up, ignoring volume keeps shrinking (¥1.8087tn, -23.1bn vs prior), trend direction still weak-down (long & short both 2), valuation elevated (PE pctile 70-90%), real up-ratio only 53% (official Euphoria tag overstated)."},
    {zh:"近因偏差",en:"Recency",sev:3,zhd:"外推08-25普涨+08-26技术反包的「回暖」，对缩量（连续两日萎缩）与广度回落（76%→53%）反应钝化。",end:"Extrapolating the 08-25 broad rally + 08-26 technical rebound 'recovery'; blunted by the volume-shrinking (two days running) and breadth pullback (76%→53%)."},
    {zh:"叙事偏差",en:"Narrative",sev:4,zhd:"「金融搭台/资源刚需」叙事在缩量反包中仍被资金强化（证券+2.75%/工业金属+3.33%/紫金5日+34.96亿），故事未证伪且被加仓自我实现，但量价背离下叙事脆弱。",end:"The 'finance leads / resource-must-have' narrative reinforced by capital even in a volume-less rebound (securities +2.75%/industrial-metals +3.33%/Zijin 5d +3.496bn) — story un-falsified, self-reinforced by buying, but fragile under price-volume divergence."},
    {zh:"代表性启发",en:"Representativeness",sev:3,zhd:"被造纸+3.79%（青山纸业+10.16%）/证券+2.75%（锦龙+10.05%）单日赚钱效应代表，误判市场全面转暖、忽视无量反包的低质量（涨股比仅53%、成交继续缩）。",end:"Paper +3.79% (Qingshan +10.16%) / securities +2.75% (Jinlong +10.05%) profit taken as representative; mistaking a sector rally for a broad turn, ignoring the volume-less rebound's low quality (up-ratio only 53%, volume keeps shrinking)."}
  ];'''
html, n_bias = re.subn(r'var BIAS = \[[\s\S]*?\n  \];', bias, html, count=1)
assert n_bias == 1, ("BIAS replace count", n_bias)

# ---- 3. static body replacements (non data-i18n hardcoded values) ----
repls = [
  # masthead date
  ('<b>2026-08-25 收盘（北京时间，盘后）</b>', '<b>2026-08-26 收盘（北京时间，盘后）</b>'),
  # chips
  ('<span class="chip"><span data-i18n="c_upratio">涨股比</span> <b>76%</b></span>',
   '<span class="chip"><span data-i18n="c_upratio">涨股比</span> <b>53%</b></span>'),
  ('<span class="chip"><span data-i18n="c_limitup">涨停</span> <b>70</b></span>',
   '<span class="chip"><span data-i18n="c_limitup">涨停</span> <b>56</b></span>'),
  ('<span class="chip"><span data-i18n="c_turn">两市成交</span> <b>¥1.8318万亿</b></span>',
   '<span class="chip"><span data-i18n="c_turn">两市成交</span> <b>¥1.8087万亿</b></span>'),
  # radar polygon
  ('<polygon points="160,86 244,121 202,193 160,160 110,202 57,115"',
   '<polygon points="160,84 237,123 200,191 160,166 112,200 57,115"'),
  # radar value labels
  ('<text x="160" y="82">58</text><text x="246" y="117">72</text><text x="206" y="189">48</text>\n            <text x="160" y="156">24</text><text x="110" y="198">62</text><text x="57" y="119">88</text>',
   '<text x="160" y="80">60</text><text x="239" y="119">66</text><text x="202" y="187">46</text>\n            <text x="160" y="162">38</text><text x="112" y="196">60</text><text x="57" y="119">88</text>'),
  # breadth bar rects
  ('<rect x="14" y="14" width="380" height="26" fill="#d8392b"/>',
   '<rect x="14" y="14" width="265" height="26" fill="#d8392b"/>'),
  ('<rect x="394" y="14" width="110" height="26" fill="#1a9e5a"/>',
   '<rect x="279" y="14" width="220" height="26" fill="#1a9e5a"/>'),
  # breadth % texts
  ('<text x="204" y="33" fill="#fff" font-size="14" font-weight="800" text-anchor="middle">76%</text>',
   '<text x="147" y="33" fill="#fff" font-size="14" font-weight="800" text-anchor="middle">53%</text>'),
  ('<text x="449" y="33" fill="#fff" font-size="14" font-weight="800" text-anchor="middle">22%</text>',
   '<text x="389" y="33" fill="#fff" font-size="14" font-weight="800" text-anchor="middle">44%</text>'),
  ('<text x="514" y="33" fill="#6b675f" font-size="11" font-weight="700" text-anchor="end">1% 平盘</text>',
   '<text x="514" y="33" fill="#6b675f" font-size="11" font-weight="700" text-anchor="end">3% 平盘</text>'),
  # breadth stat numbers
  ('<text x="340" y="72" fill="#d8392b">4234</text>', '<text x="340" y="72" fill="#d8392b">2946</text>'),
  ('<text x="340" y="92" fill="#1a9e5a">1246</text>', '<text x="340" y="92" fill="#1a9e5a">2448</text>'),
  ('<text x="340" y="112" fill="#6b675f">70</text>', '<text x="340" y="112" fill="#6b675f">156</text>'),
  ('<text x="340" y="138" fill="#d8392b">70</text>', '<text x="340" y="138" fill="#d8392b">56</text>'),
  ('<text x="340" y="158" fill="#1a9e5a">4</text>', '<text x="340" y="158" fill="#1a9e5a">2</text>'),
  ('<text x="340" y="184" fill="#1c1b19">¥1.8318万亿</text>', '<text x="340" y="184" fill="#1c1b19">¥1.8087万亿</text>'),
  # breadth change annotations
  ('<text x="355" y="72">（占 76%，较前日 +50pct）</text>', '<text x="355" y="72">（占 53%，较前日 −23pct）</text>'),
  ('<text x="355" y="92">（占 22%，较前日 −49pct）</text>', '<text x="355" y="92">（占 44%，较前日 +22pct）</text>'),
  ('<text x="355" y="112">（占 1%）</text>', '<text x="355" y="112">（占 3%）</text>'),
  ('<text x="355" y="138">（较前日 +22 只，连板高度升至 5板）</text>', '<text x="355" y="138">（较前日 −14 只，连板高度维持 5板）</text>'),
  ('<text x="355" y="158">（较前日 −10 只）</text>', '<text x="355" y="158">（较前日 −2 只）</text>'),
  ('<text x="355" y="184">（环比 −1756亿，缩量）</text>', '<text x="355" y="184">（环比 −231亿，继续缩量）</text>'),
  # evidence: upratio cell
  ('<td><span class="val up">76%</span>（涨4234 / 跌1246 / 平70）</td>',
   '<td><span class="val up">53%</span>（涨2946 / 跌2448 / 平156）</td>'),
  # evidence: limit cell
  ('<td><span class="val up">70</span> / <span class="val down">4</span></td>',
   '<td><span class="val up">56</span> / <span class="val down">2</span></td>'),
  # evidence: amount cell
  ('<td><span class="val">≈¥1.8318万亿</span>（较前日 −1756亿，缩量）</td>',
   '<td><span class="val">≈¥1.8087万亿</span>（较前日 −231亿，继续缩量）</td>'),
  # evidence: index values
  ('<td data-i18n="ev_sh">上证指数</td><td><span class="val up">3889.44　+0.19%</span></td>',
   '<td data-i18n="ev_sh">上证指数</td><td><span class="val up">3912.52　+0.59%</span></td>'),
  ('<td data-i18n="ev_sz">深证成指</td><td><span class="val down">13745.87　-0.35%</span></td>',
   '<td data-i18n="ev_sz">深证成指</td><td><span class="val up">13841.33　+0.69%</span></td>'),
  ('<td data-i18n="ev_cyb">创业板指</td><td><span class="val down">3397.52　-1.00%</span></td>',
   '<td data-i18n="ev_cyb">创业板指</td><td><span class="val up">3414.88　+0.51%</span></td>'),
  # evidence: secup cell
  ('<td><span class="val up">小家电 +8.02%</span>（石头科技 +20.00%）<br>化妆品 +5.23%（青岛金王 +10.02%）/ 房地产服务 +4.37%（我爱我家 +10.14%）/ 装修装饰 +3.64%<br>医疗服务 +3.40% / 旅游 +2.80% / 种植业 +2.75%（万向德农 +10.03%）</td>',
   '<td><span class="val up">造纸 +3.79%</span>（青山纸业 +10.16%）<br>工业金属 +3.33%（精艺股份 +10.03%）/ 证券Ⅱ +2.75%（锦龙股份 +10.05%）/ 冶钢原料 +2.71%<br>农化制品 +2.25%（新农股份 +9.99%）/ 保险Ⅱ +2.06% / 水泥 +2.01%（西藏天路 +6.44%）/ 酒店餐饮 +1.94%（华天酒店 +9.95%）</td>'),
  # evidence: secdn cell
  ('<td><span class="val down">贵金属 −3.83%</span>（资源链由强转弱，获利了结）<br>能源金属 −3.84% / 小金属 −2.54% / 电池 −2.40% / 工业金属 −2.25%<br>半导体 −0.20% / 通信设备 −0.46%（前期强势科技硬件止跌回稳）</td>',
   '<td><span class="val down">小家电 −1.35%</span>（由领涨转领跌）<br>出版 −1.44% / 医疗服务 −1.34% / 贵金属 −0.64% / 数字媒体 −1.10%<br>电机 −0.95% / 地面兵装 −0.89% / 工程机械 −0.88% / 食品加工 −0.64% / 游戏 −0.63%（半导体 0% / 通信设备 0% 横盘企稳）</td>'),
  # evidence: board cell
  ('<td><span class="val up">连板高度 5 板</span>（汉森制药 — 昨日连板已 +10.04%）<br>4板：深中华A；3板：楚天龙 / 新华百货<br>2板：上海能源 / 中南文化 / 海鸥住工 / 登海种业<br>新热点：石头科技 +20.00%（小家电）/ 我爱我家 +10.14%（地产服务）/ 万向德农 +10.03%（种植业）/ 汉森制药 +10.04%（连板）</td>',
   '<td><span class="val up">连板高度 5 板</span>（深中华A — 接棒汉森制药）<br>4板：楚天龙；3板：海鸥住工<br>2板：华阳国际 / 冀衡医药 / 青山纸业 / 捷荣技术 / 康盛股份 / 青岛金王 / 华天酒店 / 豪尔赛 / 浙江世宝 / 万向德农<br>新热点：青山纸业 +10.16%（造纸）/ 锦龙股份 +10.05%（证券）/ 华天酒店 +9.95%（酒店）/ 万向德农 +10.03%（种植业）/ 新农股份 +9.99%（农化）</td>'),
  # evidence: height cell
  ('<td><span class="val up">汉森制药 5板</span>（2026-08-25）</td>',
   '<td><span class="val up">深中华A 5板</span>（2026-08-26）</td>'),
  # evidence: main cell
  ('<td>紫金矿业 <span class="val up">+28.33亿</span><br>英维克 +14.08亿 / 兴业银锡 +10.39亿 / 湖南白银 +10.11亿 / 比亚迪 +9.24亿<br>太辰光 +8.60亿 / 盛达资源 +8.50亿 / 山东黄金 +8.11亿 / 飞龙股份 +8.00亿</td>',
   '<td>紫金矿业 <span class="val up">+34.96亿</span><br>洛阳钼业 +24.31亿 / C高凯 +23.98亿 / 英维克 +15.42亿 / 剑桥科技 +15.14亿<br>江西铜业 +14.10亿 / 白银有色 +13.14亿 / 长飞光纤 +13.00亿 / 比亚迪 +12.58亿 / 湖南白银 +12.43亿 / 兴业银锡 +12.19亿</td>'),
  # evidence: margin cell
  ('<td>中际旭创 <span class="val up">+8.16亿</span>（AI 硬件光模块龙头）<br>紫金矿业 +5.59亿 / 兴业银锡 +4.16亿 / 士兰微 +2.72亿 / 生益科技 +2.48亿<br>金钼股份 +2.33亿 / 飞龙股份 +2.27亿 / 云南锗业 +2.03亿 / 中金黄金 +1.95亿 / 键凯科技 +1.65亿</td>',
   '<td>天孚通信 <span class="val up">+2.34亿</span>（光模块）<br>盐湖股份 +1.65亿 / 申菱环境 +1.62亿 / 兆易创新 +1.55亿 / 中油资本 +1.49亿<br>英维克 +1.44亿 / 宁德时代 +1.37亿</td>'),
  # evidence: hot cell
  ('<td>石头科技 +20.00%（小家电）<br>青岛金王 +10.02%（化妆品）/ 我爱我家 +10.14%（地产服务）/ 万向德农 +10.03%（种植业）/ 汉森制药 +10.04%（连板）</td>',
   '<td>青山纸业 +10.16%（造纸）<br>锦龙股份 +10.05%（证券）/ 华天酒店 +9.95%（酒店）/ 万向德农 +10.03%（种植业）/ 新农股份 +9.99%（农化）<br>深中华A +10.04%（连板 5板）</td>'),
]

for i,(old,new) in enumerate(repls):
    c = html.count(old)
    if c != 1:
        sys.stderr.write("WARN repl %d count=%d: %r\n" % (i, c, old[:40]))
    html = html.replace(old, new)

open(OUT, "w", encoding="utf-8").write(html)
print("Written:", OUT, "len", len(html))

# ---- 4. validations ----
# external refs
ext = len(re.findall(r'https?://', html))
srcref = len(re.findall(r'<script[^>]*\src=', html))
print("external http(s):", ext, "script src:", srcref)

# I18N key coverage
used = set(re.findall(r'data-i18n="([^"]+)"', html))
m = re.search(r'var I18N = \{([\s\S]*?)\n  \};', html)
block = m.group(1)
# extract zh and en key sets: keys are like  key:"..."  (allow zh: and en:)
zh_keys, en_keys = set(), set()
cur = None
for line in block.splitlines():
    s = line.strip()
    if s.startswith('zh:{'): cur='zh'; continue
    if s.startswith('en:{'): cur='en'; continue
    if s in ('}','},'):
        continue
    # capture EVERY key on the line (some lines pack multiple key:"..." pairs)
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
must = ["53%","¥1.8087万亿","56","深中华A","5板","3912.52","13841.33","3414.88",
        "造纸","技术反包","量价背离","天孚通信","紫金矿业 +34.96亿","青山纸业"]
for s in must:
    assert s in html, ("missing present", s)
print("must-present OK")

# must-gone static old values (not in I18N comparison text)
gone = ["3889.44","13745.87","3397.52","4234","¥1.8318万亿","小家电 +8.02%","中际旭创 <span"]
for s in gone:
    assert s not in html, ("still present", s)
print("must-gone OK")
print("ALL STATIC CHECKS PASSED")
