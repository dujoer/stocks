# -*- coding: utf-8 -*-
import re, sys, subprocess

BASE = "G:/ai/股票/market-trend/crowd-psychology-risk-radar-20260825.html"
I18N = "G:/ai/股票/market-trend/_i18n_0825.txt"

with open(BASE, encoding="utf-8") as f:
    html = f.read()
with open(I18N, encoding="utf-8") as f:
    new_i18n = f.read().rstrip("\n")

# ---- 1) Replace I18N block ----
start_marker = "\n  var I18N = {"
end_marker = "\n  };"
si = html.index(start_marker)
ei = html.index(end_marker, si) + len(end_marker)
html = html[:si] + "\n" + new_i18n + html[ei:]
print("I18N replaced:", si, ei)

# ---- 2) BIAS array rewrite (08-25 narrative, real data) ----
NEW_BIAS = '''  var BIAS = [
    {zh:"羊群效应",en:"Herding",sev:4,zhd:"涨股比76%普涨，但成交缩至¥1.8318万亿、小盘占优（中证1000>沪深300），资金扎堆消费/低位题材（小家电+8.02%/化妆品+5.23%）与连板（汉森制药5板），跟随普涨而非独立判断。",end:"Up-ratio 76% broad rally, but turnover shrank to ¥1.8318tn and small-caps led (CSI1000>CSI300); capital crowds consumer/low-level themes (small-appliances +8.02%/cosmetics +5.23%) and streaks (Hansen 5 boards) — following the rally, not conviction."},
    {zh:"损失厌恶",en:"Loss Aversion",sev:3,zhd:"08-25 缩量反弹中融资逆势回补中际旭创+8.16亿（AI硬件光模块），把前期浮亏当已发生损失回避止损、反手加仓高位科技。",end:"In the 08-25 volume-shrinking bounce, margin contrarian-add Zhongji Innolight +0.816bn (AI optical-module) — avoiding the realized loss, doubling down on high-level tech."},
    {zh:"心理账户/赌徒谬误",en:"Mental Acct / Gambler",sev:3,zhd:"创业板60日-14.01%下仍在缩量反弹中融资博光模块/科技反弹（中际旭创+8.16亿），把亏损仓当赌资、博「AI算力刚需」回本。",end:"Amid ChiNext 60d -14.01% still margin-betting on optical-module/tech rebound (Zhongji +0.816bn) in a volume-shrinking bounce; treating loss books as gambling capital."},
    {zh:"过度自信",en:"Overconfidence",sev:4,zhd:"普涨76%下误判「反转」，把单日缩量反弹当趋势恢复、追消费/题材（小家电+8.02%/化妆品+5.23%），忽视技术极弱（MACD死叉）与估值偏高。",end:"Reading the 76% rally as 'reversal', treating a single-day volume-shrinking bounce as trend recovery, chasing consumer/themes (small-appliances +8.02%/cosmetics +5.23%) — ignoring extremely weak technics (MACD death-cross) and elevated valuation."},
    {zh:"处置效应",en:"Disposition",sev:3,zhd:"反弹中卖盈（贵金属获利了结-3.83%）持亏（AI套牢未割且反手加仓中际旭创+8.16亿），结构分化、调仓滞后。",end:"Selling winners (precious metals profit-taking -3.83%) while holding losers (AI traps untrimmed, even re-added Zhongji +0.816bn) — split structure, lagging rotation."},
    {zh:"锚定偏差",en:"Anchoring",sev:3,zhd:"锚定前期高点与官方「狂热」标签，难接受中期弱势（创业板60日-14.01%、深成60日-10.39%）与缩量现实。",end:"Anchored to prior highs and the official 'Euphoria' tag; rejecting mid-term weakness (ChiNext 60d -14.01%, SZSE 60d -10.39%) and the volume-down reality."},
    {zh:"确认偏误",en:"Confirmation Bias",sev:4,zhd:"只看涨停70/普涨76%与「狂热」标签，忽略缩量（5日均88.85%）、技术极弱（MACD死叉/均线空头）、估值偏高（PE分位70-90%）。",end:"Only watching 70 limit-ups / 76% breadth and the 'Euphoria' tag, ignoring volume-down (88.85% of 5-day avg), extremely weak technics (MACD death-cross / bearish MA), elevated valuation (PE pctile 70-90%)."},
    {zh:"近因偏差",en:"Recency",sev:3,zhd:"外推08-24暴跌后单日反弹的「回暖」，对缩量低质量反弹（¥1.8318万亿、量能缩）反应钝化。",end:"Extrapolating the post-08-24-selloff one-day 'recovery'; blunted by the volume-shrinking low-quality bounce (¥1.8318tn, volume down)."},
    {zh:"叙事偏差",en:"Narrative",sev:4,zhd:"AI硬件「光模块=算力刚需」叙事在缩量反弹中仍被杠杆回补（中际旭创+8.16亿、紫金+5.59亿）强化，故事未证伪且被加仓自我实现。",end:"The 'optical-module = AI compute must-have' narrative reinforced by margin add-backs even in a volume-shrinking bounce (Zhongji +0.816bn, Zijin +0.559bn) — story un-falsified, self-reinforced by buying."},
    {zh:"代表性启发",en:"Representativeness",sev:3,zhd:"被小家电+8.02%（石头科技+20%）、化妆品+5.23%单日赚钱效应代表，误判市场全面转暖、忽视缩量普涨的低质量。",end:"Small-appliances +8.02% (Roborock +20%) / cosmetics +5.23% profit taken as representative; mistaking a sector rally for a broad turn, ignoring the volume-shrinking low-quality bounce."}
  ];'''
html, n = re.subn(r'  var BIAS = \[.*?\n  \];', NEW_BIAS, html, flags=re.S)
assert n == 1, ("BIAS replace count", n)
print("BIAS replaced")

# ---- 3) Body static (non data-i18n) replacements ----
reps = [
    ('：<b>2026-08-24 收盘（北京时间，盘后）</b>', '：<b>2026-08-25 收盘（北京时间，盘后）</b>'),
    ('<span class="chip"><span data-i18n="c_upratio">涨股比</span> <b>26%</b></span>',
     '<span class="chip"><span data-i18n="c_upratio">涨股比</span> <b>76%</b></span>'),
    ('<span class="chip"><span data-i18n="c_limitup">涨停</span> <b>48</b></span>',
     '<span class="chip"><span data-i18n="c_limitup">涨停</span> <b>70</b></span>'),
    ('<span class="chip"><span data-i18n="c_board">连板高度</span> <b>4板</b></span>',
     '<span class="chip"><span data-i18n="c_board">连板高度</span> <b>5板</b></span>'),
    ('<span class="chip"><span data-i18n="c_turn">两市成交</span> <b>¥2.007万亿</b></span>',
     '<span class="chip"><span data-i18n="c_turn">两市成交</span> <b>¥1.8318万亿</b></span>'),
    ('          <rect x="14" y="14" width="130" height="26" fill="#d8392b"/>',
     '          <rect x="14" y="14" width="380" height="26" fill="#d8392b"/>'),
    ('          <rect x="144" y="14" width="355" height="26" fill="#1a9e5a"/>',
     '          <rect x="394" y="14" width="110" height="26" fill="#1a9e5a"/>'),
    ('          <text x="79" y="33" fill="#fff" font-size="14" font-weight="800" text-anchor="middle">26%</text>',
     '          <text x="204" y="33" fill="#fff" font-size="14" font-weight="800" text-anchor="middle">76%</text>'),
    ('          <text x="321.5" y="33" fill="#fff" font-size="14" font-weight="800" text-anchor="middle">71%</text>',
     '          <text x="449" y="33" fill="#fff" font-size="14" font-weight="800" text-anchor="middle">22%</text>'),
    ('          <text x="514" y="33" fill="#6b675f" font-size="11" font-weight="700" text-anchor="end">3% 平盘</text>',
     '          <text x="514" y="33" fill="#6b675f" font-size="11" font-weight="700" text-anchor="end">1% 平盘</text>'),
    ('            <text x="340" y="72" fill="#d8392b">1434</text>',
     '            <text x="340" y="72" fill="#d8392b">4234</text>'),
    ('            <text x="340" y="92" fill="#1a9e5a">3915</text>',
     '            <text x="340" y="92" fill="#1a9e5a">1246</text>'),
    ('            <text x="340" y="112" fill="#6b675f">165</text>',
     '            <text x="340" y="112" fill="#6b675f">70</text>'),
    ('            <text x="340" y="138" fill="#d8392b">48</text>',
     '            <text x="340" y="138" fill="#d8392b">70</text>'),
    ('            <text x="340" y="158" fill="#1a9e5a">14</text>',
     '            <text x="340" y="158" fill="#1a9e5a">4</text>'),
    ('            <text x="340" y="184" fill="#1c1b19">¥2.007万亿</text>',
     '            <text x="340" y="184" fill="#1c1b19">¥1.8318万亿</text>'),
    ('            <text x="355" y="72">（占 26%，较前日 −19pct）</text>',
     '            <text x="355" y="72">（占 76%，较前日 +50pct）</text>'),
    ('            <text x="355" y="92">（占 71%，较前日 +19pct）</text>',
     '            <text x="355" y="92">（占 22%，较前日 −49pct）</text>'),
    ('            <text x="355" y="112">（占 3%）</text>',
     '            <text x="355" y="112">（占 1%）</text>'),
    ('            <text x="355" y="138">（较前日 −10 只，连板高度回升至 4板）</text>',
     '            <text x="355" y="138">（较前日 +22 只，连板高度升至 5板）</text>'),
    ('            <text x="355" y="158">（较前日 −1 只）</text>',
     '            <text x="355" y="158">（较前日 −10 只）</text>'),
    ('            <text x="355" y="184">（环比 +1282亿，由缩量转放量）</text>',
     '            <text x="355" y="184">（环比 −1756亿，缩量）</text>'),
    ('<td><span class="val up">26%</span>（涨1434 / 跌3915 / 平165）</td>',
     '<td><span class="val up">76%</span>（涨4234 / 跌1246 / 平70）</td>'),
    ('<td><span class="val up">48</span> / <span class="val down">14</span></td>',
     '<td><span class="val up">70</span> / <span class="val down">4</span></td>'),
    ('<td><span class="val">≈¥2.007万亿</span>（较前日 +1282亿，由缩量转放量）</td>',
     '<td><span class="val">≈¥1.8318万亿</span>（较前日 −1756亿，缩量）</td>'),
    ('<td><span class="val up">汉森制药 4板</span>（2026-08-24）</td>',
     '<td><span class="val up">汉森制药 5板</span>（2026-08-25）</td>'),
    ('          <polygon points="160,82 242,122 214,206 160,166 116,196 55,114"',
     '          <polygon points="160,86 244,121 202,193 160,160 110,202 57,115"'),
    ('            <circle cx="160" cy="82" r="3.2"/><circle cx="242" cy="122" r="3.2"/>\n'
     '            <circle cx="210" cy="202" r="3.2"/><circle cx="160" cy="174" r="3.2"/>\n'
     '            <circle cx="114" cy="198" r="3.2"/><circle cx="55" cy="114" r="3.2"/>',
     '            <circle cx="160" cy="86" r="3.2"/><circle cx="244" cy="121" r="3.2"/>\n'
     '            <circle cx="202" cy="193" r="3.2"/><circle cx="160" cy="160" r="3.2"/>\n'
     '            <circle cx="110" cy="202" r="3.2"/><circle cx="57" cy="115" r="3.2"/>'),
    ('            <text x="160" y="78">62</text><text x="244" y="118">70</text><text x="210" y="202">62</text>\n'
     '            <text x="160" y="170">40</text><text x="114" y="194">55</text><text x="58" y="118">90</text>',
     '            <text x="160" y="82">58</text><text x="246" y="117">72</text><text x="206" y="189">48</text>\n'
     '            <text x="160" y="156">24</text><text x="110" y="198">62</text><text x="57" y="119">88</text>'),
    ('<div class="s"><span data-i18n="r3">乐观</span><small>Optimism</small></div>',
     '<div class="s on"><span data-i18n="r3">乐观</span><small>Optimism</small></div>'),
    ('<div class="s on"><span data-i18n="r5">焦虑</span><small>Anxiety</small></div>',
     '<div class="s"><span data-i18n="r5">焦虑</span><small>Anxiety</small></div>'),
    # evidence value cells (static, real 08-25 data)
    ('<td><span class="val up">焦炭 +5.39%</span>（美锦能源 +9.89%，5日 +6.86% / 20日 +10.67%）<br>保险 +2.58%（中国平安 +2.94%）/ 煤炭 +2.17%（上海能源 +10.02%）/ 种植业 +2.06%（登海种业 +10.04%）/ 白酒 +1.73%（贵州茅台 +2.50%）<br>贵金属续强：湖南白银 +9.98%（白银概念 +1.58%，5日 +13.73% / 20日 +31.57% / 60日 +26.88%）</td>',
     '<td><span class="val up">小家电 +8.02%</span>（石头科技 +20.00%）<br>化妆品 +5.23%（青岛金王 +10.02%）/ 房地产服务 +4.37%（我爱我家 +10.14%）/ 装修装饰 +3.64%<br>医疗服务 +3.40% / 旅游 +2.80% / 种植业 +2.75%（万向德农 +10.03%）</td>'),
    ('<td><span class="val down">半导体 −3.13%</span>（20日 −8.92% / 60日 −8.14%）<br>通信设备 −5.21%（楚天龙 +10.01% 但板块跌）/ 元件 −4.18%（宝鼎科技 +4.91%）<br>概念：光芯片 −4.08% / CPO −2.63% / 芯片 −1.89%（高位 AI 硬件全面兑现）</td>',
     '<td><span class="val down">贵金属 −3.83%</span>（资源链由强转弱，获利了结）<br>能源金属 −3.84% / 小金属 −2.54% / 电池 −2.40% / 工业金属 −2.25%<br>半导体 −0.20% / 通信设备 −0.46%（前期强势科技硬件止跌回稳）</td>'),
    ('<td><span class="val up">连板高度 4 板</span>（汉森制药 — 昨日连板已 +10.04%）<br>3板 3只：深中华A / 中关村 / 哈森股份<br>2板：白银有色 / 楚天龙 / 湖南白银 / 东信和平 / 新华百货 / 天洋新材等<br>新热点：美锦能源 +9.89%（焦炭）/ 上海能源 +10.02%（煤炭）/ 中国平安 +2.94%（保险）/ 湖南白银 +9.98%（白银）</td>',
     '<td><span class="val up">连板高度 5 板</span>（汉森制药 — 昨日连板已 +10.04%）<br>4板：深中华A；3板：楚天龙 / 新华百货<br>2板：上海能源 / 中南文化 / 海鸥住工 / 登海种业<br>新热点：石头科技 +20.00%（小家电）/ 我爱我家 +10.14%（地产服务）/ 万向德农 +10.03%（种植业）/ 汉森制药 +10.04%（连板）</td>'),
    ('<td>紫金矿业 <span class="val up">+31.20亿</span><br>湖南白银 +12.59亿 / 兴业银锡 +10.70亿 / 山东黄金 +10.08亿 / 农业银行 +9.72亿<br>红星发展 +9.68亿 / 白银有色 +9.18亿 / 士兰微 +8.81亿 / 盛达资源 +8.77亿 / 歌尔股份 +8.62亿</td>',
     '<td>紫金矿业 <span class="val up">+28.33亿</span><br>英维克 +14.08亿 / 兴业银锡 +10.39亿 / 湖南白银 +10.11亿 / 比亚迪 +9.24亿<br>太辰光 +8.60亿 / 盛达资源 +8.50亿 / 山东黄金 +8.11亿 / 飞龙股份 +8.00亿</td>'),
    ('<td>中际旭创 <span class="val up">+5.36亿</span>（AI 硬件光模块龙头）<br>山东黄金 +4.29亿 / 沃森生物 +3.63亿 / 新易盛 +3.57亿 / 华大智造 +3.35亿 / 国瓷材料 +2.86亿<br>天孚通信 +2.54亿 / 中瓷电子 +2.49亿 / 湖南白银 +1.82亿 / 通鼎互联 +1.81亿</td>',
     '<td>中际旭创 <span class="val up">+8.16亿</span>（AI 硬件光模块龙头）<br>紫金矿业 +5.59亿 / 兴业银锡 +4.16亿 / 士兰微 +2.72亿 / 生益科技 +2.48亿<br>金钼股份 +2.33亿 / 飞龙股份 +2.27亿 / 云南锗业 +2.03亿 / 中金黄金 +1.95亿 / 键凯科技 +1.65亿</td>'),
    ('<td>美锦能源 +9.89%（焦炭）<br>上海能源 +10.02%（煤炭）/ 中国平安 +2.94%（保险）/ 湖南白银 +9.98%（白银）/ 汉森制药 +10.04%（连板）</td>',
     '<td>石头科技 +20.00%（小家电）<br>青岛金王 +10.02%（化妆品）/ 我爱我家 +10.14%（地产服务）/ 万向德农 +10.03%（种植业）/ 汉森制药 +10.04%（连板）</td>'),
]

for old, new in reps:
    cnt = html.count(old)
    if cnt != 1:
        print("WARN replace count=%d for: %r" % (cnt, old[:50]))
    html = html.replace(old, new)

# index values via regex (avoid full-width space mismatch)
html = re.sub(r'<td><span class="val up">3882\.01[^\n]*</span>',
              '<td><span class="val up">3889.44\u3000+0.19%</span>', html)
html = re.sub(r'<td><span class="val up">13794\.29[^\n]*</span>',
              '<td><span class="val down">13745.87\u3000-0.35%</span>', html)
html = re.sub(r'<td><span class="val up">3431\.89[^\n]*</td>',
              '<td><span class="val down">3397.52\u3000-1.00%</span></td>', html)

# ---- 4) Static-only assertions ----
# truly-static (non data-i18n) positions must no longer contain 08-24 literals
must_gone = [
    "2026-08-24 收盘（北京时间，盘后）",
    "涨股比</span> <b>26%</b>", "涨停</span> <b>48</b>", "连板高度</span> <b>4板</b>",
    "两市成交</span> <b>¥2.007万亿</b>",
    ">1434<", ">3915<", ">165<", "¥2.007万亿</text>",
    "涨1434 / 跌3915 / 平165",
    '<span class="val up">48</span> / <span class="val down">14</span>',
    "≈¥2.007万亿", "汉森制药 4板",
    'points="160,82 242,122 214,206 160,166 116,196 55,114"',
    "3882.01", "3431.89", "13794.29",
    "2026-08-24 收盘（北京时间",
]
for g in must_gone:
    if g in html:
        print("FAIL still present:", g); sys.exit(1)
# the 6 evidence VALUE cells are static; assert the NEW 08-25 content now present
must_present = [
    "小家电 +8.02%</span>（石头科技",
    "贵金属 −3.83%</span>（资源链",
    "连板高度 5 板</span>（汉森制药",
    '紫金矿业 <span class="val up">+28.33亿</span>',
    '中际旭创 <span class="val up">+8.16亿</span>',
    "石头科技 +20.00%（小家电）",
]
for g in must_present:
    if g not in html:
        print("FAIL new content missing:", g); sys.exit(1)
print("All static old-string assertions passed; 6 evidence value cells updated")

# ---- 5) I18N key coverage (zh & en must cover every data-i18n used) ----
used = set(re.findall(r'data-i18n="([^"]+)"', html))
m = re.search(r'  var I18N = \{(.*?)\n  \};', html, flags=re.S)
block = m.group(1)
def keys_of(lang):
    seg = re.search(lang + r':\{(.*?)\n    \}', block, flags=re.S).group(1)
    return set(re.findall(r'([A-Za-z_][A-Za-z0-9_]*):', seg))
zh, en = keys_of("zh"), keys_of("en")
missing_zh = used - zh
missing_en = used - en
print("used=%d zh=%d en=%d" % (len(used), len(zh), len(en)))
if missing_zh: print("MISSING zh keys:", sorted(missing_zh)); sys.exit(1)
if missing_en: print("MISSING en keys:", sorted(missing_en)); sys.exit(1)
if zh != en:
    print("NOTE zh/en key set differs (unused extra keys are harmless):", zh ^ en)
print("I18N key coverage OK (all used keys covered in both zh and en)")

# ---- 6) External references must be zero ----
ext = re.findall(r'https?://', html)
scripts_src = re.findall(r'<script[^>]*\ssrc=', html)
print("external http(s) refs:", len(ext), "| <script src=> :", len(scripts_src))
if ext or scripts_src:
    print("FAIL external reference found"); sys.exit(1)

# ---- 7) JS syntax check (extract all <script> blocks) ----
blocks = re.findall(r'<script>(.*?)</script>', html, flags=re.S)
js = "\n".join(blocks)
with open("G:/ai/股票/market-trend/_check0825.js", "w", encoding="utf-8") as f:
    f.write(js)
r = subprocess.run(["C:/Users/nonoy/.workbuddy/binaries/node/versions/22.22.2/node.exe",
                   "--check", "G:/ai/股票/market-trend/_check0825.js"],
                  capture_output=True, text=True)
print("node --check rc=", r.returncode)
if r.returncode != 0:
    print(r.stdout); print(r.stderr); sys.exit(1)
print("JS syntax OK")

with open(BASE, "w", encoding="utf-8") as f:
    f.write(html)
print("Written:", BASE)
