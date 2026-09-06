# -*- coding: utf-8 -*-
"""重建 2026-09-04 群体心理风险雷达：以 09-03 模板为基底，
用 09-04 真实行情数据（已落盘 market_overview / limitup / sector_daily +
实时拉取的 margin_chg_d / cap_main_5d）全面覆盖 zh/en/i18n、BIAS、
静态证据表、雷达读数。保证 0 旧数据、0 外链。

数据快照（2026-09-04 收盘，均为真实查询）：
  指数：上证 3930.12 −0.30% / 深成 13516.97 −0.79% / 创业板 3286.55 −0.78%
  涨跌：涨 2444 / 跌 2914 / 平 198（共 5556）；涨股比 46%（09-03 33% → +13pct）
  涨停 42（09-03 46）/ 蛾停 0（09-03 17 → 清零）
  成交：¥2.03万亿（环比 +2700亿，放量）
  估值：PE_TTM 20.39，10年分位 79.52%，PB 1.75
  技术：DIF 8.22>DEA 5.53（红柱 5.38 收窄）；KDJ K64/D66/J61 中位；RSI_12 49.9；收于 MA20 3937.5 / 布林中轨下方
  领涨：航海装备Ⅱ +6.49%（中国船舶 +9.18%）/ 养殖业 +5.30%（罗牛山 +10.05%）/ 饲料 +4.79%（播恩集团 +10.04%）
        / 渔业 +3.96%（中水渔业 +9.98%）/ 广告营销 +3.87%（易点天下 +11.12%）/ 房地产服务 +3.85%（我爱我家 +10.14%）
  领跌：玻璃玻纤 −4.86% / 电子化学品Ⅱ −3.86% / 非金属材料Ⅱ −3.35% / 其他电子Ⅱ −3.09% / 能源金属 −2.89% / 小金属 −2.86%
  连板：5板 龙版传媒；2板 6只（恒盛能源/爱仕达/海通发展/新炬网络/亚盛集团/百大集团）；首板 35只（农业养殖食品/传媒出版/地产白酒）
  融资单日：宁德时代 +3.57亿 / 中国巨石 +2.86亿 / 麦格米特 +2.61亿 / 浪潮信息 +2.23亿 / 紫金矿业 +2.21亿
  主力5日：中国船舶 +19.70亿 / 协创数据 +17.66亿 / 大族激光 +13.47亿 / 中国平安 +11.13亿 / 方正科技 +11.00亿
  板块行为：抢筹144 / 建仓106 / 洗盘157 / 出货519（926 板块），暗盘净流出 −137.65亿
  风格：价值主导（10日 价值 +3.43% vs 成长 −1.31%）
"""
import re, os, shutil

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "..", "web", "psychology", "crowd-psychology-risk-radar-20260903.html")
OUT = os.path.join(HERE, "..", "web", "psychology", "crowd-psychology-risk-radar-20260904.html")
html = open(SRC, encoding="utf-8").read()

# ============================================================
# 1) 解析原 zh / en 块
# ============================================================
def extract_inner(html, marker):
    if marker == "zh":
        m = re.search(r'zh:\{(.*?)\n    \},', html, re.S)
    else:
        m = re.search(r'en:\{(.*?)\n    \}', html, re.S)
    assert m, f"找不到 {marker} 块"
    return m

def parse(inner):
    d = {}
    pat = re.compile(r'([A-Za-z_][A-Za-z0-9_]*)\s*:\s*"((?:[^"\\]|\\.)*)"')
    for line in inner.split("\n"):
        for mm in pat.finditer(line):
            d[mm.group(1)] = mm.group(2)
    return d

m_zh = extract_inner(html, "zh")
m_en = extract_inner(html, "en")
zh0 = parse(m_zh.group(1))
en0 = parse(m_en.group(1))
print(f"[ok] 解析 zh 键 {len(zh0)} / en 键 {len(en0)}")

# ============================================================
# 2) 09-04 叙述覆盖（中文）—— 真实数据
# ============================================================
ZH = {
 "t_headline_sub": "2026-09-04 · 收盘",
 "t_breadth": "市场涨跌分布（2026-09-04 收盘）",
 "hk_stage": "阶段定性", "hv_stage": "<b>放量分化 / 修复反弹</b>（09-04）",
 "hk_upratio": "涨股比", "hv_upratio": "<b>46%</b>（前次 09-03 33% · ↑ 13pct，广度修复）",
 "hk_lim": "涨停 / 跌停", "hv_lim": "<b>42</b> / <b>0</b>（跌停清零）",
 "hk_amt": "成交额", "hv_amt": "<b>¥2.03万亿</b>（放量 +2700亿）",
 "hk_cycle": "情绪周期", "hv_cycle": "<b>放量分化 / 修复反弹</b>",
 "hk_risk": "风险等级", "hv_risk": "<b class=\"hl-risk\">中</b>（由高回落）",
 "hk_flag": "关键提示",
 "hv_flag": "涨股比 33%→<b>46%</b>、跌停 17→<b>0</b>、放量 <b>+2700亿</b>——广度实质修复；但指数仍小跌、出货板块 519/926（56%）、暗盘净流出 −137.65亿，反弹成色待验；玻璃玻纤 −4.86% 领跌 = 融资逆势加仓被闷杀，杠杆亏损兑现",
 "tk1": "阶段定性", "tv1": "A 股 09-04 由 09-03「低位弱修复 / 主线散乱」升级为「<b>放量分化 / 修复反弹</b>」：成交放量至 ¥2.03万亿（环比 <b>+2700亿</b>），涨股比 <b>46%</b>（2444涨 / 2914跌 / 平198，由 33% 修复 +13pct），涨停 42、<b>跌停清零</b>（17→0）；三指仍小跌（上证 −0.30% / 深成 −0.79% / 创业板 −0.78%），收于 MA20（3937.5）与布林中轨下方。结构剧烈反转：昨日领跌第一的房地产服务（−3.47%）今日 <b>+3.85%</b> 领涨，船舶 / 农业养殖 / 地产链 / 传媒多线开花。风险等级由高回落至<b>中</b>。",
 "tk2": "广度修复", "tv2": "涨股比 <b>46%</b>（前次 33% ↑ 13pct）· 涨停 <b>42</b>（46→42）· <b>跌停 0</b>（17→0 清零）· 成交 <b>¥2.03万亿</b>（放量 +2700亿）——参与度实质性回升，恐慌盘出清。",
 "tk3": "指数仍弱", "tv3": "上证 <b>−0.30%</b>（3930.12）/ 深成 <b>−0.79%</b> / 创业板 <b>−0.78%</b>；指数微跌但个股普涨 = <b>指数-个股背离收敛</b>；收于 MA20 3937.5 与布林中轨下方，MACD 红柱 5.38 收窄（DIF 8.22 > DEA 5.53），KDJ 中位（K64/D66/J61），RSI_12 49.9 中性。",
 "tk4": "板块反转", "tv4": "<b>航海装备Ⅱ +6.49%</b>（中国船舶 +9.18%，主力5日 +19.70亿 全市场第一）领涨，养殖业 +5.30%（罗牛山 +10.05%）/ 饲料 +4.79%（播恩集团 +10.04%）/ 渔业 +3.96%（中水渔业 +9.98%）/ 广告营销 +3.87%（易点天下 +11.12%）/ <b>房地产服务 +3.85%</b>（我爱我家 +10.14%，昨日领跌第一大反转）；<b>玻璃玻纤 −4.86%</b>（融资连续加仓方向被闷杀）领跌，电子化学品Ⅱ −3.86% / 非金属材料Ⅱ −3.35% / 能源金属 −2.89% 等资源材料普跌。",
 "tk5": "连板结构", "tv5": "连板高度 <b>5 板</b>（龙版传媒，连续第三日锁 5 板：新赛股份→国芳集团→龙版传媒，<b>龙头一日一换</b>）；2板 6 只（恒盛能源 / 爱仕达 / 海通发展 / 新炬网络 / 亚盛集团 / 百大集团）；首板 35 只集中于农业养殖食品（新希望 / 天邦食品 / 新五丰 / 正虹科技 / 敦煌种业）、传媒出版（中国出版 / 欢瑞世纪）、地产白酒（古越龙山 / 会稽山）。",
 "tk6": "杠杆转向", "tv6": "融资单日加仓榜 <b>宁德时代 +3.57亿 居首</b>，中国巨石 +2.86亿、麦格米特 +2.61亿、浪潮信息 +2.23亿、紫金矿业 +2.21亿——杠杆由玻纤/光模块扩散至电池/军工/算力；但 <b>中国巨石方向（玻纤）今日 −4.86% 领跌</b>，前期逆势加仓被闷杀，杠杆亏损兑现、拥挤度消化。",
 "tk7": "估值 / 风格", "tv7": "PE_TTM <b>20.39</b>（10年分位 <b>79.52%</b> 仍偏高）+ PB 1.75；风格<b>价值主导</b>（10日 价值 +3.43% vs 成长 −1.31%），大小盘均衡（差异 <±3%）——修复以低估值方向接力为主，高估值成长仍受压。",
 "tk8": "情绪周期", "tv8": "由 09-03「低位弱修复 / 主线散乱」转入「<b>放量分化 / 修复反弹</b>」：广度实质修复（46%、跌停清零）、量能放量（+2700亿）、主线由散乱转向多线（船舶/农业/地产/传媒）；但指数仍小跌、板块暗盘净流出 −137.65亿（出货板块 519/926 占 56%）、估值分位 79.5% 仍高、连板高度锁 5 且龙头一日一换——修复与分歧并存，风险等级<b>中</b>。",
 "t_tldr_text": "A股 09-04 呈现「放量分化 / 修复反弹」：成交放量至 ¥2.03万亿（环比 +2700亿），涨股比 46%（2444涨 / 2914跌 / 平198，由 33% 修复），涨停 42、跌停清零（17→0），三指仍小跌（上证 −0.30% / 深成 −0.79% / 创业板 −0.78%）。结构剧烈反转：航海装备Ⅱ +6.49%（中国船舶 +9.18%，主力5日 +19.70亿 第一）领涨，养殖业 +5.30%（罗牛山 +10.05%）/ 饲料 +4.79%（播恩集团 +10.04%）/ 渔业 +3.96%（中水渔业 +9.98%）/ 广告营销 +3.87%（易点天下 +11.12%）/ 房地产服务 +3.85%（我爱我家 +10.14%，昨日领跌第一大反转）；玻璃玻纤 −4.86%（融资连续加仓方向被闷杀）领跌，电子化学品Ⅱ −3.86% / 非金属材料Ⅱ −3.35% / 能源金属 −2.89% 普跌。连板高度 5板（龙版传媒，龙头一日一换），2板 6 只，首板 35 只集中农业养殖食品/传媒出版/地产白酒。关键资金信号：融资单日宁德时代 +3.57亿居首（中国巨石 +2.86亿次之但玻纤方向领跌=杠杆被闷），主力5日中国船舶 +19.70亿第一。估值 PE_TTM 20.39（10年分位 79.52%）仍偏高，风格价值主导（10日 价值 +3.43% vs 成长 −1.31%）。板块暗盘净流出 −137.65亿（出货 519/926）——修复与分歧并存，风险等级中。",
 "t_cycle_note": "注：上方「中性偏暖」为实时群体心理定位（放量分化 / 修复反弹）——09-04 涨跌分布（涨股比 46%、涨停 42、跌停 0、成交 ¥2.03万亿）显示广度实质修复（由 33% 升至 46%）、恐慌盘出清、量能放量；但指数仍小跌、暗盘净流出、估值分位仍高。若 09-07 涨股比守住 45% 上方且上证站回 MA5（3956），修复延续；否则反复。",
 "t_radar_note": "六维风险读数（0–100，由下方真实数据综合映射，越高代表该维度群体脆弱性越强）：拥挤度 52 / 融资 64 / 换手 56 / 广度 58 / 媒体 55 / 估值 87。广度由 76 大幅降至 58（09-04 涨股比 46%、跌停清零，参与度实质改善）；换手由 50 升至 56（成交放量至 ¥2.03万亿，活跃换手回升）；融资由 66 降至 64（单日加仓分散至宁德时代 +3.57亿 / 中国巨石 +2.86亿，但巨石方向被闷杀=杠杆亏损兑现、逆势程度下降）；拥挤度由 60 降至 52（题材由散乱转向船舶/农业/地产/传媒多线，高位玻纤退潮，集中度回落）；媒体由 60 降至 55（涨停 42、跌停 0、热点多点开花，情绪温度温和修复）；估值 88→87（PE_TTM 20.39、10年分位 79.52% 仍偏高）。整体呈「放量分化 / 修复反弹」结构——广度修复、估值仍高、暗盘分歧，反弹成色待验。",
 "t_breadth_note": "涨股比由 33% 修复至 46%、跌停 17→0 清零、涨停 42（46→42 微降）；放量修复、参与度实质回升。指数仍小跌（上证 −0.30% / 深成 −0.79% / 创业板 −0.78%），收于 MA20 3937.5 与布林中轨下方；成交 ¥2.03万亿环比 +2700亿（放量），船舶/农业养殖/地产/传媒多线领涨，玻璃玻纤 −4.86% 领跌，结构反转剧烈。",
 "ev_upratio_i": "由 33% 修复至 46%（+13pct），参与度实质回升，跌停清零显示恐慌盘出清，风险偏好回暖",
 "ev_limit_i": "涨停 42（46→42 微降）、跌停 0（17→0 清零），连板高度 5板（龙版传媒）——投机热度平稳、恐慌出清，首板 35 只多线开花",
 "ev_amount_i": "量能放量至 ¥2.03万亿（环比 +2700亿，10日均的 103.5%），放量修复 = 承接力回升，反弹动能改善但仍需确认",
 "ev_sh_i": "小跌 −0.30%（3930.12），收于 MA20 3937.5 与布林中轨下方，MACD 红柱 5.38 收窄，PE_TTM 20.39（10年分位 79.52% 偏高）",
 "ev_sz_i": "深成 −0.79%（13516.97），跟跌但跌幅收敛，中期弱势未改，量能修复下韧性略增",
 "ev_cyb_i": "创业板 −0.78%（3286.55），微跌但个股修复，高估值成长风格仍受价值主导风格压制",
 "ev_secup_i": "航海装备Ⅱ +6.49%（中国船舶 +9.18%，主力5日 +19.70亿 第一）领涨，养殖业 +5.30%（罗牛山 +10.05%）/ 饲料 +4.79%（播恩集团 +10.04%）/ 渔业 +3.96%（中水渔业 +9.98%）/ 广告营销 +3.87%（易点天下 +11.12%）/ 房地产服务 +3.85%（我爱我家 +10.14%，昨日领跌第一大反转）——多线开花、超跌反转与景气共振",
 "ev_secdn_i": "玻璃玻纤 −4.86% 领跌（融资连续加仓方向被闷杀）/ 电子化学品Ⅱ −3.86% / 非金属材料Ⅱ −3.35% / 其他电子Ⅱ −3.09% / 能源金属 −2.89% / 小金属 −2.86%——资源材料与前期杠杆集中方向集体退潮",
 "ev_board_i": "连板 5板（龙版传媒，龙头一日一换），2板 6 只（恒盛能源 / 爱仕达 / 海通发展 / 新炬网络 / 亚盛集团 / 百大集团）；热点由船舶 / 农业养殖 / 地产 / 传媒多线主导（中国船舶 +9.18% / 罗牛山 +10.05% / 我爱我家 +10.14%），广度改善但主线仍在轮动",
 "ev_height_i": "高度 5板（龙版传媒，2026-09-04 收盘），连续第三日锁 5 板但龙头一日一换（新赛→国芳→龙版传媒），接力风险大、持续性存疑",
 "ev_main": "融资单日净流入TOP",
 "ev_main_i": "杠杆资金当日扩散至电池 / 玻纤 / 军工电源 / 算力（宁德时代 +3.57亿 / 中国巨石 +2.86亿 / 麦格米特 +2.61亿 / 浪潮信息 +2.23亿 / 紫金矿业 +2.21亿）——逆势程度下降、方向分散化，但巨石方向被闷杀提示杠杆接盘风险",
 "ev_margin": "融资单日变动TOP",
 "ev_margin_i": "融资单日加仓榜宁德时代居首（+3.57亿），中国巨石 +2.86亿、麦格米特 +2.61亿、浪潮信息 +2.23亿、紫金矿业 +2.21亿、星网锐捷 +2.13亿、飞龙股份 +1.93亿、方正科技 +1.79亿——加仓方向分散，杠杆亏损兑现后边际收敛",
 "ev_hot_i": "热点由船舶 / 农业养殖 / 地产 / 传媒多线主导（中国船舶 +9.18% / 罗牛山 +10.05% / 我爱我家 +10.14% / 龙版传媒 5板）；data_hot 本次未返回，以板块领涨股 + 连板梯队综合替代（见来源口径）",
 "ev_margintotal_i": "缺口：聚合两融余额为空，以个股融资变动替代观察（见上）；连板高度 / 融资单日 / 主力5日均为 2026-09-04 真实数据",
 "t_ev_note": "数据口径：宏观指标多截至 2026-07（月频）或 2026-09-04（日频）；PMI/产能/社融为 08-21 复核最新月频值（无新发布），CPI / M1-M2 / 10Y / LPR 沿用前期已查询月频 / 日频值（未更新）。涨跌分布 / 指数 / 成交额 / 板块 / 融资单日 / 主力5日均为 2026-09-04 真实收盘；官方综合画像、连板梯队、融资单日均已更新至 2026-09-04，相关字段已标注。财新PMI数据源覆盖仅至 2025-08（49.2），不作为主要依据。详见末尾「数据来源与日期口径」。",
 "rc1_tag": "红线区 · 高估值 + 杠杆闷杀 + 暗盘流出",
 "rc1_t": "高估值 + 杠杆闷杀 + 暗盘流出",
 "rc1_d": "估值 PE_TTM 20.39、10年分位 79.52% 仍偏高，指数收于 MA20 / 布林中轨下方；玻璃玻纤 −4.86% 领跌 = 融资连续加仓方向被闷杀（中国巨石 +2.86亿仍在加），杠杆亏损兑现；板块暗盘净流出 −137.65亿、出货板块 519/926（56%）——修复之下主力仍在兑现，二次回落风险未除。",
 "rc1_rep": "代表：高估值成长 / 玻纤等杠杆集中方向 / 出货占主导的高位板块",
 "rc2_tag": "黄线区 · 船舶 / 农业养殖多线轮动（节奏快）",
 "rc2_t": "船舶·农业养殖多线轮动",
 "rc2_d": "航海装备Ⅱ +6.49%（中国船舶 +9.18%，主力5日 +19.70亿 第一，价格与资金共振）为最强主线；养殖业 / 饲料 / 渔业涨停潮（罗牛山 / 播恩集团 / 中水渔业）为情绪先锋；但连板龙头一日一换、轮动快，单线持续性待验。",
 "rc2_rep": "代表：航海装备Ⅱ（中国船舶）/ 养殖业（罗牛山）/ 饲料（播恩集团）",
 "rc3_tag": "绿线区 · 地产链 / 传媒超跌反转（相对）",
 "rc3_t": "地产链 / 传媒超跌反转",
 "rc3_d": "房地产服务 +3.85%（我爱我家 +10.14%）由昨日领跌第一反转领涨，广告营销 +3.87%（易点天下 +11.12%）、传媒出版（中国出版 / 龙版传媒 5板）活跃——超跌方向接力修复，但属低位补涨性质，需量价持续确认而非新周期主线。",
 "rc3_rep": "代表：房地产服务（我爱我家）/ 广告营销（易点天下）/ 传媒（龙版传媒）",
 "t_sec_outlook": "下个交易日（09-07 周一）展望",
 "o_logic": "研判逻辑（基于 09-04 收盘 + 群体心理定位）",
 "o_logic_text": "由 09-04 的「放量分化 / 修复反弹」延伸：情绪周期定位「放量分化 / 修复反弹」，涨股比 46%、跌停清零、成交放量 +2700亿至 ¥2.03万亿，广度实质修复；但指数仍小跌、收于 MA20 / 布林中轨下方、暗盘净流出 −137.65亿、估值分位 79.52% 仍高、趋势长期方向弱势下跌。基于此推演 09-07 的板块方向与交易规则（<b>不涉及具体个股推荐</b>）。",
 "o1_tag": "船舶 / 高端装备（观察）",
 "o1_t": "航海装备Ⅱ / 军工装备",
 "o1_d": "09-04 最强主线：航海装备Ⅱ +6.49%（中国船舶 +9.18%），主力5日 +19.70亿 全市场第一 = 价格与资金双共振；若 09-07 量能维持 2万亿上方且板块不熄，主线地位可延续。",
 "o1_cond": "注意：单日暴涨后忌追高；回踩 5 日线不破再考虑右侧；主力5日数据为滞后确认，防高位兑现。",
 "o2_tag": "农业养殖 / 地产链（观望）",
 "o2_t": "养殖业 / 饲料 / 房地产服务",
 "o2_d": "09-04 养殖业 +5.30% / 饲料 +4.79% / 渔业 +3.96% 涨停潮（罗牛山 / 播恩集团 / 中水渔业），房地产服务 +3.85% 由领跌第一反转领涨（我爱我家 +10.14%）——超跌反转 + 政策预期，但属低位补涨性质。",
 "o2_cond": "注意：涨停潮次日分化概率大，只做龙头不追跟风；地产链需连续 2 日以上量价确认，不抄底不加杠杆。",
 "o3_tag": "玻纤 / 资源材料（回避）",
 "o3_t": "玻璃玻纤 / 能源金属 / 小金属",
 "o3_d": "09-04 玻璃玻纤 −4.86% 领跌（融资连续加仓的中国巨石方向被闷杀），能源金属 −2.89% / 小金属 −2.86% / 电子化学品Ⅱ −3.86% 集体退潮——杠杆集中 + 前期强势方向的补跌风险仍在释放。",
 "o3_cond": "注意：杠杆闷杀方向短期回避；等融资余额下降 + 缩量止跌再观察；不接飞刀。",
 "o_r1": "<b>仓位</b>：中性偏低（≤5 成），不加杠杆。情绪由「低位弱修复」升级「放量分化 / 修复反弹」，风险等级由高转中，风险预算边际改善但未到进攻位。",
 "o_r2": "<b>右侧确认</b>：涨股比 ≥45% 且上证站回 MA5（3956）/ MA20（3938）上方并放量，方可将仓位提至上限；反之缩量即减。",
 "o_r3": "<b>主线参与</b>：船舶（资金+价格双共振）只做回踩不追高；农业养殖/地产链只做龙头，涨停潮次日不追跟风。",
 "o_r4": "<b>回避清单</b>：玻璃玻纤等杠杆闷杀方向、能源金属/小金属补跌方向、高位 5板连板（龙头一日一换，接力必套）。",
 "o_r5": "<b>风控</b>：若 09-07 缩量至 ¥1.8万亿以下且涨股比回落 <40%，视为修复夭折，降仓至 ≤3 成；跌破布林中轨（3937）则进一步防守。",
 "s_breadth_v": "westock · data_market_overview(market_statis_updown)；2026-09-04 收盘",
 "s_portrait_v": "westock · data_market_overview(type=summary)；2026-09-04（涨股比 46% 真实广度修复，放量分化）",
 "s_index_v": "westock · data_quote(sh000001,sz399001,sz399006)；2026-09-04 收盘",
 "s_sector_v": "westock · data_sector(mode=ranking)；2026-09-04（fundflow 含行业/概念/地区排行与领涨股）",
 "s_hot_v": "westock · data_hot 本次未返回；热搜以 data_sector(fundflow 领涨股) + tool_ranking(limitup_days) 综合替代；涨跌分布/指数/板块/融资单日为 2026-09-04",
 "s_margin_v": "westock · tool_ranking(metric=margin_chg_d)；2026-09-04",
 "s_main_v": "westock · tool_ranking(metric=cap_main_5d)；2026-09-04（中国船舶 +19.70亿 居首）",
 "s_board_v": "westock · tool_ranking(metric=limitup_days)；2026-09-04（当日排行榜已刷新）",
 "s_gap_v": "市场两融余额聚合值（data_market_overview type=margin）数据源返回空，已用个股融资变动替代，未编造；data_hot 本次未返回，已用板块领涨股 + 连板梯队综合替代；连板高度 / 融资单日 / 主力5日均为 2026-09-04 真实数据。",
 "t_src_note": "时间口径：所有时点按北京时间。宏观为月频 / 季频，与日频行情不可直接对齐，已分别标注。涨跌分布 / 指数 / 板块 / 融资单日 / 主力5日 / 连板高度均为 2026-09-04 当日真实数据。",
 "ev_index": "二、核心指数表现（2026-09-04 收盘）",
 "o_rules_t": "交易规则（09-07）",
 "o_compliance": "<b>合规说明：</b>本展望仅给出板块方向与交易规则，不涉及具体个股推荐；群体心理定位与板块推断基于 2026-09-04 真实行情数据，市场有风险，决策须独立。",
 "t_risk_hi": "中",
}

# ============================================================
# 3) 09-04 叙述覆盖（英文）—— 平行翻译
# ============================================================
EN = {
 "t_headline_sub": "2026-09-04 · Close",
 "t_breadth": "Market Breadth (2026-09-04 close)",
 "t_breadth": "Market Breadth (2026-09-04 close)",
 "hk_stage": "Stage", "hv_stage": "<b>Volume-rebound / Repair with divergence</b> (09-04)",
 "hk_upratio": "Up-ratio", "hv_upratio": "<b>46%</b> (prior 09-03 33% · ↑ 13pct, breadth repaired)",
 "hk_lim": "Limit-up / Down", "hv_lim": "<b>42</b> / <b>0</b> (limit-down cleared)",
 "hk_amt": "Turnover", "hv_amt": "<b>¥2.03tn</b> (expanded +¥270bn)",
 "hk_cycle": "Sentiment cycle", "hv_cycle": "<b>Volume-rebound / Repair with divergence</b>",
 "hk_risk": "Risk level", "hv_risk": "<b class=\"hl-risk\">Medium</b> (down from High)",
 "hk_flag": "Key flag",
 "hv_flag": "Up-ratio 33%→<b>46%</b>, limit-down 17→<b>0</b> cleared, turnover <b>+¥270bn</b> — breadth genuinely repaired; yet indices still dip, 519/926 (56%) sectors distributing, dark-pool outflow −¥13.77bn, rebound quality unproven; glass-fiber −4.86% leads down = margin-chasing trapped, leverage losses realized",
 "tk1": "Stage", "tv1": "On 09-04 A-shares upgraded from 09-03's 'low-level weak recovery / scattered leaders' into '<b>volume-rebound / repair with divergence</b>': turnover expanded to ¥2.03tn (+¥270bn), up-ratio <b>46%</b> (2444 up / 2914 down / 198 flat, repaired from 33%), limit-up 42, <b>limit-down cleared</b> (17→0); three indices still dip (SSE −0.30% / SZSE −0.79% / ChiNext −0.78%), closing below MA20 (3937.5) and BOLL mid. Sharp reversal: yesterday's worst loser real-estate services (−3.47%) today <b>+3.85%</b> leads; shipping / agri-breeding / property-chain / media bloom on multiple lines. Risk down from High to <b>Medium</b>.",
 "tk2": "Breadth repair", "tv2": "Up-ratio <b>46%</b> (prior 33% ↑ 13pct) · Limit-up <b>42</b> (46→42) · <b>Limit-down 0</b> (17→0 cleared) · Turnover <b>¥2.03tn</b> (+¥270bn) — participation genuinely rebounds, panic selling flushed out.",
 "tk3": "Indices still weak", "tv3": "SSE <b>−0.30%</b> (3930.12) / SZSE <b>−0.79%</b> / ChiNext <b>−0.78%</b>; indices dip while stocks broadly recover = <b>index-vs-stock divergence narrows</b>; close below MA20 3937.5 & BOLL mid, MACD red bar narrows to 5.38 (DIF 8.22 > DEA 5.53), KDJ mid (K64/D66/J61), RSI_12 49.9 neutral.",
 "tk4": "Sector reversal", "tv4": "<b>Marine EquipmentⅡ +6.49%</b> (China Shipbuilding +9.18%, main-5d +¥1.97bn #1 marketwide) leads, breeding +5.30% (Luoniu +10.05%) / feed +4.79% (Boen +10.04%) / fishery +3.96% (Zhongshui +9.98%) / ad-marketing +3.87% (Yidian +11.12%) / <b>real-estate services +3.85%</b> (Wuwo Wujia +10.14%, yesterday's worst-loser reversal); <b>glass-fiber −4.86%</b> (margin-chased direction trapped) leads down, e-chemicalsⅡ −3.86% / non-metallicⅡ −3.35% / energy-metals −2.89% broadly down.",
 "tk5": "Streak structure", "tv5": "Board height <b>5 boards</b> (Longban Media, third straight day locked at 5: Xinsai→Guofang→Longban, <b>leader rotates daily</b>); 2-board ×6 (Hengsheng / Aishida / Haitong Dev / Xinju / Yasheng / Baida); 35 first-boards cluster in agri-breeding-food (New Hope / Tianbang / Xiwufeng / Zhenghong / Dunhuang), media-publishing (China Publishing / Huanrui), property-liquor (Guyue Longshan / Huiji Mountain).",
 "tk6": "Leverage rotates", "tv6": "Margin daily-add led by <b>CATL +¥0.357bn (#1)</b>, China Jushi +0.286bn, Megmeet +0.261bn, Inspur +0.223bn, Zijin +0.221bn — leverage spreads from fiberglass/optical to battery/defense-power/computing; but <b>China Jushi's fiberglass direction fell −4.86% today</b>, prior against-tide adds trapped, leverage losses realized, crowding digested.",
 "tk7": "Valuation / style", "tv7": "PE_TTM <b>20.39</b> (10y pctile <b>79.52%</b> still rich) + PB 1.75; style <b>value-led</b> (10d value +3.43% vs growth −1.31%), large/small-cap balanced (±3%) — the repair is led by low-valuation directions, rich-valuation growth still pressured.",
 "tk8": "Sentiment cycle", "tv8": "From 09-03 'low-level weak recovery / scattered leaders' into '<b>volume-rebound / repair with divergence</b>': breadth genuinely repaired (46%, limit-down cleared), volume expanded (+¥270bn), main line from scattered to multi-line (shipping/agri/property/media); yet indices still dip, dark-pool outflow −¥13.77bn (distributing 519/926 = 56%), valuation pctile 79.5% still rich, streak locked at 5 with daily leader rotation — repair and divergence coexist, risk <b>Medium</b>.",
 "t_tldr_text": "On 2026-09-04 A-shares showed 'volume-rebound / repair with divergence': turnover expanded to ¥2.03tn (+¥270bn), up-ratio 46% (2444 up / 2914 down / 198 flat, repaired from 33%), limit-up 42, limit-down cleared (17→0), three indices still dip (SSE −0.30% / SZSE −0.79% / ChiNext −0.78%). Sharp reversal: Marine EquipmentⅡ +6.49% (China Shipbuilding +9.18%, main-5d +¥1.97bn #1) leads, breeding +5.30% (Luoniu +10.05%) / feed +4.79% (Boen +10.04%) / fishery +3.96% (Zhongshui +9.98%) / ad-marketing +3.87% (Yidian +11.12%) / real-estate services +3.85% (Wuwo Wujia +10.14%, yesterday's worst-loser reversal); glass-fiber −4.86% (margin-chased direction trapped) leads down, e-chemicalsⅡ −3.86% / non-metallicⅡ −3.35% / energy-metals −2.89% broadly down. Streak 5 boards (Longban Media, leader rotates daily), 2-board ×6, 35 first-boards in agri-food/media-publishing/property-liquor. Key flow: margin daily CATL +0.357bn leads (China Jushi +0.286bn second but fiberglass leads down = trapped), main-5d China Shipbuilding +¥1.97bn #1. Valuation PE_TTM 20.39 (10y pctile 79.52%) still rich, value-led style (10d value +3.43% vs growth −1.31%). Dark-pool outflow −¥13.77bn (distributing 519/926) — repair and divergence coexist, risk Medium.",
 "t_cycle_note": "Note: 'Neutral-warm' above is the live crowd positioning (volume-rebound / repair with divergence) — the 09-04 breadth (up-ratio 46%, limit-up 42, limit-down 0, turnover ¥2.03tn) shows genuine breadth repair (33%→46%), panic flushed, volume expanded; yet indices dip, dark-pool outflows, valuation pctile still rich. If 09-07 holds up-ratio ≥45% and SSE reclaims MA5 (3956), the repair extends; otherwise it stalls.",
 "t_radar_note": "Six-dimension risk readings (0–100, model-mapped, higher = more fragility): Crowding 52 / Margin 64 / Turnover 56 / Breadth 58 / Media 55 / Valuation 87. Breadth 76→58 sharply down (09-04 up-ratio 46%, limit-down cleared, participation genuinely improved); Turnover 50→56 (turnover expanded to ¥2.03tn, active turnover rebounds); Margin 66→64 (daily adds spread to CATL +0.357bn / China Jushi +0.286bn, but Jushi's direction trapped = leverage losses realized, against-tide degree falls); Crowding 60→52 (themes rotate from scattered to multi-line shipping/agri/property/media, high-level fiberglass fades, concentration falls); Media 60→55 (limit-up 42, limit-down 0, hotspots bloom, sentiment mildly warms); Valuation 88→87 (PE_TTM 20.39, 10y pctile 79.52% still elevated). Overall a 'volume-rebound / repair with divergence' structure — breadth repaired, valuation still rich, dark-pool divergence, rebound quality unproven.",
 "t_breadth_note": "Up-stock ratio repaired 33%->46%, limit-down 17→0 cleared, limit-up 42 (46→42 mild dip); volume-rebound repair, participation genuinely recovers. Indices still dip (SSE −0.30% / SZSE −0.79% / ChiNext −0.78%), close below MA20 3937.5 & BOLL mid; turnover ¥2.03tn +270bn (expanded), shipping/agri/property/media multi-line lead, glass-fiber −4.86% leads down, sharp structural reversal.",
 "ev_upratio_i": "Repaired 33%->46% (+13pct), participation genuinely rebounds, limit-down cleared shows panic flushed, risk appetite warms",
 "ev_limit_i": "Limit-up 42 (46→42), limit-down 0 (17→0 cleared), streak still 5 boards (Longban Media) — speculative heat steady, panic flushed, 35 first-boards bloom on multi-lines",
 "ev_amount_i": "Turnover expanded to ¥2.03tn (+270bn vs prior, 103.5% of 10d avg); volume-rebound repair = better absorption, momentum improving but needs confirmation",
 "ev_sh_i": "Mild −0.30% (3930.12), below MA20 3937.5 & BOLL mid, MACD red bar narrows to 5.38, PE_TTM 20.39 (10y pctile 79.52% rich)",
 "ev_sz_i": "SZSE −0.79% (13516.97), follows down but narrower, mid-term weakness unchanged, resilience slightly better on volume repair",
 "ev_cyb_i": "ChiNext −0.78% (3286.55), mild dip but stocks recover, rich-valuation growth still capped by value-led style",
 "ev_secup_i": "Marine EquipmentⅡ +6.49% (China Shipbuilding +9.18%, main-5d +¥1.97bn #1) leads, breeding +5.30% (Luoniu +10.05%) / feed +4.79% (Boen +10.04%) / fishery +3.96% (Zhongshui +9.98%) / ad-marketing +3.87% (Yidian +11.12%) / real-estate services +3.85% (Wuwo Wujia +10.14%, yesterday's worst-loser reversal) — multi-line bloom, oversold reversal meets prosperity",
 "ev_secdn_i": "Glass-fiber −4.86% leads (margin-chased direction trapped) / e-chemicalsⅡ −3.86% / non-metallicⅡ −3.35% / other-electronicsⅡ −3.09% / energy-metals −2.89% / minor-metals −2.86% — resources & prior-leverage directions retreat together",
 "ev_board_i": "Streak 5 boards (Longban Media, leader rotates daily), 2-board ×6 (Hengsheng / Aishida / Haitong Dev / Xinju / Yasheng / Baida); hotspots led by shipping / agri-breeding / property / media multi-lines (China Shipbuilding +9.18% / Luoniu +10.05% / Wuwo Wujia +10.14%), breadth improves but main line still rotating",
 "ev_height_i": "Rose to 5 boards (Longban Media, 2026-09-04 close), third straight day locked at 5 but leader rotates daily (Xinsai→Guofang→Longban), high relay risk, persistence unproven",
 "ev_main": "Margin daily net-inflow TOP",
 "ev_main_i": "Margin capital spread that day to battery / fiberglass / defense-power / computing (CATL +0.357bn / China Jushi +0.286bn / Megmeet +0.261bn / Inspur +0.223bn / Zijin +0.221bn) — against-tide degree falls, direction diversifies, but Jushi's trapped direction flags leverage-chasing risk",
 "ev_margin": "Margin daily change TOP",
 "ev_margin_i": "Margin daily-add led by CATL (+0.357bn), China Jushi +0.286bn, Megmeet +0.261bn, Inspur +0.223bn, Zijin +0.221bn, Star-net +0.213bn, Feilong +0.193bn, Founder Tech +0.179bn — adds diversify, leverage marginally contracts after losses realized",
 "ev_hot_i": "Hotspots led by shipping / agri-breeding / property / media multi-lines (China Shipbuilding +9.18% / Luoniu +10.05% / Wuwo Wujia +10.14% / Longban Media 5 boards); data_hot unavailable this round, proxied by sector leaders + streak ladder (see Sources)",
 "ev_margintotal_i": "Gap: aggregate margin balance empty; proxied by per-stock margin changes (above); streak height / margin daily / main-5d are all 2026-09-04 real data",
 "t_ev_note": "Time caliber: macro mostly as of 2026-07 (monthly) or 2026-09-04 (daily); PMI/capacity/financing re-checked 08-21 (no new release, monthly), CPI/M1-M2/10Y/LPR from prior pulls (unchanged). Breadth / indices / turnover / sectors / margin daily / main-5d are all 2026-09-04 real close; official portrait, streak ladder, margin daily all updated to 2026-09-04 and labeled. Caixin PMI source only to 2025-08 (49.2), not primary. See 'Data Sources & Time Caliber' at end.",
 "rc1_tag": "RED · Rich valuation + leverage trapped + dark-pool outflow",
 "rc1_t": "Rich valuation + leverage trapped + dark-pool outflow",
 "rc1_d": "PE_TTM 20.39, 10y pctile 79.52% still rich, index below MA20 / BOLL mid; glass-fiber −4.86% leads down = margin-chased direction trapped (China Jushi +0.286bn still adding), leverage losses realized; dark-pool outflow −¥13.77bn, distributing sectors 519/926 (56%) — under the repair, mains still realize profits, second-selloff risk not removed.",
 "rc1_rep": "Names: rich-valuation growth / fiberglass & leverage-crowded directions / high-level distributing sectors",
 "rc2_tag": "AMBER · Shipbuilding / agri-breeding multi-line rotation (fast)",
 "rc2_t": "Shipbuilding · agri-breeding multi-line rotation",
 "rc2_d": "Marine EquipmentⅡ +6.49% (China Shipbuilding +9.18%, main-5d +¥1.97bn #1, price & capital dual-resonance) is the strongest line; breeding/feed/fishery limit-up wave (Luoniu / Boen / Zhongshui) is the sentiment spearhead; but streak leader rotates daily, fast rotation, single-line persistence unproven.",
 "rc2_rep": "Names: Marine EquipmentⅡ (China Shipbuilding) / breeding (Luoniu) / feed (Boen)",
 "rc3_tag": "GREEN · Property-chain / media oversold reversal (relative)",
 "rc3_t": "Property-chain / media oversold reversal",
 "rc3_d": "Real-estate services +3.85% (Wuwo Wujia +10.14%) flips from yesterday's worst loser to leader, ad-marketing +3.87% (Yidian +11.12%), media-publishing (China Publishing / Longban 5 boards) active — oversold directions relay the repair, but low-level catch-up in nature; needs sustained volume-price confirmation, not a new-cycle main line.",
 "rc3_rep": "Names: real-estate services (Wuwo Wujia) / ad-marketing (Yidian) / media (Longban)",
 "t_sec_outlook": "Next-Session Outlook (09-07 Mon)",
 "o_logic": "Inference logic (based on 09-04 close + crowd positioning)",
 "o_logic_text": "Extending 09-04's 'volume-rebound / repair with divergence': crowd cycle at 'Volume-rebound / Repair with divergence', up-ratio 46%, limit-down cleared, turnover expanded +¥270bn to ¥2.03tn, breadth genuinely repaired; yet indices dip, close below MA20 / BOLL mid, dark-pool outflow −¥13.77bn, valuation pctile 79.52% still rich, long-term trend weak-down. Projecting 09-07 sector direction and trading rules (<b>no individual stock picks</b>).",
 "o1_tag": "Shipbuilding / high-end equipment (watch)",
 "o1_t": "Marine EquipmentⅡ / defense equipment",
 "o1_d": "09-04 strongest line: Marine EquipmentⅡ +6.49% (China Shipbuilding +9.18%), main-5d +¥1.97bn #1 marketwide = price & capital dual-resonance; if 09-07 holds turnover above ¥2tn and the sector stays alive, main-line status extends.",
 "o1_cond": "Note: never chase after a one-day surge; consider right-side only on pullback holding the 5-day line; main-5d data is a lagging confirmation, beware high-level profit-taking.",
 "o2_tag": "Agri-breeding / property-chain (stand aside)",
 "o2_t": "Breeding / feed / real-estate services",
 "o2_d": "09-04 breeding +5.30% / feed +4.79% / fishery +3.96% limit-up wave (Luoniu / Boen / Zhongshui), real-estate services +3.85% flips from worst loser to leader (Wuwo Wujia +10.14%) — oversold reversal + policy expectation, but low-level catch-up in nature.",
 "o2_cond": "Note: limit-up waves likely diverge next session; trade leaders only, never chase followers; property-chain needs 2+ sessions of volume-price confirmation; no bottom-fishing, no leverage.",
 "o3_tag": "Fiberglass / resource materials (avoid)",
 "o3_t": "Glass-fiber / energy-metals / minor-metals",
 "o3_d": "09-04 glass-fiber −4.86% leads down (margin-chased China Jushi direction trapped), energy-metals −2.89% / minor-metals −2.86% / e-chemicalsⅡ −3.86% retreat together — leverage-crowded & prior-strong directions still releasing correction risk.",
 "o3_cond": "Note: avoid leverage-trapped directions short-term; wait for margin balance falling + volume-dry stabilization; never catch falling knives.",
 "o_r1": "<b>Book</b>: neutral-low (≤50%), no leverage. Cycle upgraded from 'low-level weak recovery' to 'volume-rebound / repair with divergence', risk High→Medium, risk budget marginally better but not at offense level.",
 "o_r2": "<b>Right-side gate</b>: only raise to max exposure when up-ratio ≥45% AND SSE reclaims MA5 (3956) / MA20 (3938) on volume; otherwise cut on shrinking volume.",
 "o_r3": "<b>Main-line participation</b>: shipbuilding (capital + price dual-resonance) only on pullbacks, never chase; agri-breeding / property-chain trade leaders only, never chase followers the day after a limit-up wave.",
 "o_r4": "<b>Avoid list</b>: glass-fiber & leverage-trapped directions, energy-metals / minor-metals correction directions, high-level 5-board streaks (leader rotates daily — relay = trapped).",
 "o_r5": "<b>Risk gate</b>: if 09-07 shrinks below ¥1.8tn AND up-ratio falls back <40%, treat the repair as failed, cut to ≤30%; a break below BOLL mid (3937) means further defense.",
 "s_breadth_v": "westock · data_market_overview(market_statis_updown); 2026-09-04 close",
 "s_portrait_v": "westock · data_market_overview(type=summary); 2026-09-04 (up-ratio 46% real breadth repair, volume-rebound with divergence)",
 "s_index_v": "westock · data_quote(sh000001,sz399001,sz399006); 2026-09-04 close",
 "s_sector_v": "westock · data_sector(mode=ranking); 2026-09-04 (fundflow includes industry/concept/region rankings and leaders)",
 "s_hot_v": "westock · data_hot unavailable this round; proxied by data_sector(fundflow leaders) + tool_ranking(limitup_days); breadth/index/sector/margin daily are 2026-09-04",
 "s_margin_v": "westock · tool_ranking(metric=margin_chg_d); 2026-09-04",
 "s_main_v": "westock · tool_ranking(metric=cap_main_5d); 2026-09-04 (China Shipbuilding +¥1.97bn #1)",
 "s_board_v": "westock · tool_ranking(metric=limitup_days); 2026-09-04 (same-day ranking refreshed)",
 "s_gap_v": "Aggregate margin balance (data_market_overview type=margin) returned empty by source; proxied by per-stock margin changes, not fabricated. data_hot unavailable this round; proxied by sector leaders + streak ladder. Streak height / margin daily / main-5d are all 2026-09-04 real data.",
 "t_src_note": "Time caliber: all timestamps in Beijing time. Macro is monthly/quarterly and not directly aligned with daily quotes; labeled separately. Breadth / index / sector / margin daily / main-5d / streak height are all 2026-09-04 same-day real data.",
 "ev_index": "II. Core Index Performance (2026-09-04 close)",
 "o_rules_t": "Trading rules (09-07)",
 "o_compliance": "<b>Compliance note:</b> this outlook provides sector direction and trading rules only — no individual stock recommendations. Crowd positioning and sector inference are based on 2026-09-04 live market data; markets carry risk, decide independently.",
 "t_risk_hi": "Medium",
}

zh = dict(zh0); zh.update(ZH)
en = dict(en0); en.update(EN)

def esc(s):
    return s.replace("\\", "\\\\").replace('"', '\\"')

def serialize(d):
    return "\n".join('      %s:"%s",' % (k, esc(d[k])) for k in d)

new_en = "en:{\n" + serialize(en) + "\n    }"
html = html[:m_en.start()] + new_en + html[m_en.end():]
new_zh = "zh:{\n" + serialize(zh) + "\n    },"
html = html[:m_zh.start()] + new_zh + html[m_zh.end():]

# ============================================================
# 4) 重建 BIAS 数组（09-04 真实数据）
# ============================================================
BIAS = [
 {"zh":"羊群效应","en":"Herding","sev":3,
  "zhd":"涨股比修复至46%、跌停清零，资金跟随船舶（中国船舶+9.18%/主力5日+19.70亿第一）与农业养殖涨停潮（罗牛山+10.05%/播恩集团+10.04%）多线涌入——修复初期群体转向跟随强势方向，独立判断仍不足。",
  "end":"Up-ratio repairs to 46%, limit-down cleared; capital follows shipbuilding (China Shipbuilding +9.18%/main-5d +¥1.97bn #1) and the agri-breeding limit-up wave (Luoniu +10.05%/Boen +10.04%) on multi-lines — the crowd chases strong directions early in the repair, conviction still thin."},
 {"zh":"损失厌恶","en":"Loss Aversion","sev":3,
  "zhd":"融资仍在给被闷杀的玻纤方向加仓（中国巨石+2.86亿，当日玻璃玻纤−4.86%领跌），把浮亏当已发生损失回避止损，杠杆亏损被动兑现中仍不愿认错。",
  "end":"Margin still adds to the trapped fiberglass direction (China Jushi +0.286bn while glass-fiber −4.86% leads down) — treating floating losses as avoided realized losses, refusing to admit error while leverage losses passively realize."},
 {"zh":"心理账户/赌徒谬误","en":"Mental Acct / Gambler","sev":2,
  "zhd":"在修复反弹中把前期亏损仓押注地产链/农业超跌反转（我爱我家+10.14%/罗牛山+10.05%），博「跌多了就该涨」，忽视低位补涨与趋势反转的区别。",
  "end":"In the repair bounce, betting loss books on property-chain/agri oversold reversals (Wuwo Wujia +10.14%/Luoniu +10.05%), gambling that 'what fell much must rise', ignoring the difference between low-level catch-up and trend reversal."},
 {"zh":"过度自信","en":"Overconfidence","sev":3,
  "zhd":"把单日广度修复（33%→46%）误读为趋势反转、追船舶与涨停潮，忽视指数仍收于 MA20 下方、暗盘净流出 −137.65亿（出货板块 519/926）、估值分位 79.52% 仍高。",
  "end":"Misreading a single-day breadth repair (33%→46%) as trend reversal and chasing shipbuilding & limit-up waves — ignoring the index still below MA20, dark-pool outflow −¥13.77bn (519/926 distributing), valuation pctile 79.52% still rich."},
 {"zh":"处置效应","en":"Disposition","sev":2,
  "zhd":"修复中卖盈（船舶/农业涨停获利了结压力上升）持亏（玻纤/资源材料套牢未割），暗盘净流出 −137.65亿显示兑现盘活跃，调仓行为分化。",
  "end":"Selling winners (shipbuilding/agri limit-up profit-taking pressure rises) while holding losers (fiberglass/resources traps untrimmed) — dark-pool outflow −¥13.77bn shows active realization, rotation behavior splits."},
 {"zh":"锚定偏差","en":"Anchoring","sev":3,
  "zhd":"锚定 09-02「涨股比 28%」的恐慌低点与 08-25 高位（61%），对 46% 的中性修复水平缺乏定价锚，易在情绪摆动中追涨杀跌。",
  "end":"Anchored to 09-02's panic low (up-ratio 28%) and the 08-25 high (61%), lacking a pricing anchor at the neutral 46% level — prone to chase-and-dump in sentiment swings."},
 {"zh":"确认偏误","en":"Confirmation Bias","sev":3,
  "zhd":"只看涨停 42、跌停清零与船舶主线资金共振，忽略指数仍小跌、收于 MA20/布林中轨下方、暗盘净流出、出货板块占 56%、估值分位仍高。",
  "end":"Only watching limit-up 42, limit-down cleared and shipbuilding's capital resonance — ignoring indices still dipping, close below MA20/BOLL mid, dark-pool outflow, 56% distributing sectors, valuation pctile still rich."},
 {"zh":"近因偏差","en":"Recency","sev":2,
  "zhd":"外推单日「放量修复」为持续性反转，对 09-02 恐慌（28%）与 09-03 跌停急升（17）的记忆迅速淡化，忽视修复需要 2 日以上量价确认。",
  "end":"Extrapolating a single-day 'volume-repair' into a sustained reversal; memories of 09-02 panic (28%) and 09-03's limit-down surge (17) fade fast, ignoring that repair needs 2+ sessions of volume-price confirmation."},
 {"zh":"叙事偏差","en":"Narrative","sev":3,
  "zhd":"「船舶景气 + 农业猪周期反转」叙事被涨停潮强化（中国船舶+9.18%/罗牛山+10.05%），故事与资金共振自我实现，但连板龙头一日一换提示叙事的持续性未被证实。",
  "end":"The 'shipbuilding prosperity + hog-cycle reversal' narrative reinforced by the limit-up wave (China Shipbuilding +9.18%/Luoniu +10.05%), story and capital self-reinforce — but the daily leader rotation flags the narrative's persistence as unproven."},
 {"zh":"代表性启发","en":"Representativeness","sev":2,
  "zhd":"被航海装备Ⅱ +6.49% 的单日赚钱效应代表整体市场，误判「全面转暖」，忽视玻璃玻纤 −4.86% 闷杀、资源材料普跌与风格价值主导的现实。",
  "end":"Marine EquipmentⅡ +6.49%'s one-day profit effect taken as representative of the whole market; mistaking it for a broad turn while ignoring glass-fiber −4.86% trapped, resource materials broadly down and the value-led style."},
]
bias_js = "var BIAS = [\n" + ",\n".join(
    "    {zh:\"%s\",en:\"%s\",sev:%d,zhd:\"%s\",end:\"%s\"}" % (esc(b["zh"]), esc(b["en"]), b["sev"], esc(b["zhd"]), esc(b["end"]))
    for b in BIAS) + "\n  ];"
html = re.sub(r'var BIAS = \[.*?\n  \];', bias_js, html, count=1, flags=re.S)

# ============================================================
# 5) 静态 body 证据表 + 涨跌分布 SVG 修正
# ============================================================
BODY = [
 # chips
 ("<span class=\"chip\"><span data-i18n=\"c_upratio\">涨股比</span> <b>33%</b></span>",
  "<span class=\"chip\"><span data-i18n=\"c_upratio\">涨股比</span> <b>46%</b></span>"),
 ("<span class=\"chip\"><span data-i18n=\"c_limitup\">涨停</span> <b>46</b></span>",
  "<span class=\"chip\"><span data-i18n=\"c_limitup\">涨停</span> <b>42</b></span>"),
 ("<span class=\"chip\"><span data-i18n=\"c_turn\">两市成交</span> <b>¥1.76万亿</b></span>",
  "<span class=\"chip\"><span data-i18n=\"c_turn\">两市成交</span> <b>¥2.03万亿</b></span>"),
 # breadth SVG center texts
 ("<text x=\"167\" y=\"33\" fill=\"#fff\" font-size=\"14\" font-weight=\"800\" text-anchor=\"middle\">33%</text>",
  "<text x=\"167\" y=\"33\" fill=\"#fff\" font-size=\"14\" font-weight=\"800\" text-anchor=\"middle\">46%</text>"),
 ("<text x=\"407\" y=\"33\" fill=\"#fff\" font-size=\"14\" font-weight=\"800\" text-anchor=\"middle\">67%</text>",
  "<text x=\"407\" y=\"33\" fill=\"#fff\" font-size=\"14\" font-weight=\"800\" text-anchor=\"middle\">54%</text>"),
 ("<text x=\"514\" y=\"33\" fill=\"#6b675f\" font-size=\"11\" font-weight=\"700\" text-anchor=\"end\">2% 平盘</text>",
  "<text x=\"514\" y=\"33\" fill=\"#6b675f\" font-size=\"11\" font-weight=\"700\" text-anchor=\"end\">4% 平盘</text>"),
 ("<text x=\"340\" y=\"72\" fill=\"#d8392b\">1846</text>",
  "<text x=\"340\" y=\"72\" fill=\"#d8392b\">2444</text>"),
 ("<text x=\"340\" y=\"92\" fill=\"#1a9e5a\">3570</text>",
  "<text x=\"340\" y=\"92\" fill=\"#1a9e5a\">2914</text>"),
 ("<text x=\"340\" y=\"112\" fill=\"#6b675f\">139</text>",
  "<text x=\"340\" y=\"112\" fill=\"#6b675f\">198</text>"),
 ("<text x=\"340\" y=\"138\" fill=\"#d8392b\">46</text>",
  "<text x=\"340\" y=\"138\" fill=\"#d8392b\">42</text>"),
 ("<text x=\"340\" y=\"158\" fill=\"#1a9e5a\">17</text>",
  "<text x=\"340\" y=\"158\" fill=\"#1a9e5a\">0</text>"),
 ("<text x=\"340\" y=\"184\" fill=\"#1c1b19\">¥1.76万亿</text>",
  "<text x=\"340\" y=\"184\" fill=\"#1c1b19\">¥2.03万亿</text>"),
 # breadth SVG parentheticals
 ("（占 33%，较上一报告日（09-02） +5pct）", "（占 46%，较上一报告日（09-03） +13pct）"),
 ("（占 67%，较上一报告日（09-02） −3pct）", "（占 54%，较上一报告日（09-03） −13pct）"),
 ("（占 3%）", "（占 4%）"),
 ("（较前日 −5 只，连板高度 5板）", "（较前日 −4 只，连板高度 5板）"),
 ("（较前日 +14 只）", "（较前日 −17 只，跌停清零）"),
 ("（环比 −322亿，继续缩量）", "（环比 +2700亿，放量修复）"),
 # breadth bar widths（修复 0903 未更新的条宽：46% / 54% / 500px 满宽）
 ('<rect x="14" y="14" width="139" height="26" fill="#d8392b"/>',
  '<rect x="14" y="14" width="230" height="26" fill="#d8392b"/>'),
 ('<rect x="153" y="14" width="351" height="26" fill="#1a9e5a"/>',
  '<rect x="244" y="14" width="270" height="26" fill="#1a9e5a"/>'),
 # evidence: 涨股比
 ("<td><span class=\"val up\">33%</span>（涨1846 / 跌3570 / 平139）</td>",
  "<td><span class=\"val up\">46%</span>（涨2444 / 跌2914 / 平198）</td>"),
 # evidence: 涨停/跌停
 ("<td><span class=\"val up\">46</span> / <span class=\"val down\">17</span></td>",
  "<td><span class=\"val up\">42</span> / <span class=\"val down\">0</span></td>"),
 # evidence: 成交额
 ("<span class=\"val\">¥1.76万亿</span>（较前日 −322亿，继续缩量）",
  "<span class=\"val\">¥2.03万亿</span>（较前日 +2700亿，放量修复）"),
 # evidence: 三大指数
 ("<td><span class=\"val up\">3942.09　+0.02%</span></td>",
  "<td><span class=\"val down\">3930.12　−0.30%</span></td>"),
 ("<td><span class=\"val up\">13625.12　+0.1%</span></td>",
  "<td><span class=\"val down\">13516.97　−0.79%</span></td>"),
 ("<td><span class=\"val up\">3312.54　+0.01%</span></td>",
  "<td><span class=\"val down\">3286.55　−0.78%</span></td>"),
 # evidence: 领涨行业
 ("<span class=\"val up\">航运港口 +2.99%</span>（海通发展 +10%）<br>其他电源设备Ⅱ +2.74% / 保险Ⅱ +2.58% / 电机Ⅱ +2.45%<br>贵金属 +2.18% / 工业金属 +1.42%",
  "<span class=\"val up\">航海装备Ⅱ +6.49%</span>（中国船舶 +9.18%）<br>养殖业 +5.30%（罗牛山 +10.05%）/ 饲料 +4.79%（播恩集团 +10.04%）<br>渔业 +3.96%（中水渔业 +9.98%）/ 广告营销 +3.87%（易点天下 +11.12%）/ 房地产服务 +3.85%（我爱我家 +10.14%）"),
 # evidence: 领跌行业
 ("<span class=\"val down\">房地产服务 −3.47%</span> / 饲料 −2.75% / 玻璃玻纤 −2.24% / 地面兵装Ⅱ −2.16% / 广告营销 −1.91% / 国有大型银行Ⅱ −1.86%",
  "<span class=\"val down\">玻璃玻纤 −4.86%</span> / 电子化学品Ⅱ −3.86% / 非金属材料Ⅱ −3.35% / 其他电子Ⅱ −3.09% / 能源金属 −2.89% / 小金属 −2.86%"),
 # evidence: 极端题材(连板)
 ("<span class=\"val up\">连板高度 5 板</span>（国芳集团）<br>4板：集泰股份 / 龙版传媒；2板 6 只（博云新材 / 太阳电缆 / 云南旅游 / 光洋股份 / 金帝股份 / 信达地产）<br>新热点：国芳集团 5板（一般零售）/ 集泰股份·龙版传媒 4板（化工 / 传媒）",
  "<span class=\"val up\">连板高度 5 板</span>（龙版传媒，龙头一日一换）<br>2板 6 只：恒盛能源 / 爱仕达 / 海通发展 / 新炬网络 / 亚盛集团 / 百大集团<br>新热点：罗牛山 +10.05%（养殖）/ 播恩集团 +10.04%（饲料）/ 中水渔业 +9.98%（渔业）/ 我爱我家 +10.14%（房地产服务）"),
 # evidence: 连板高度
 ("<span class=\"val up\">国芳集团 5板</span>（2026-09-03）", "<span class=\"val up\">龙版传媒 5板</span>（2026-09-04）"),
 # evidence: 融资单日净流入TOP（两行同构，依次替换）
 ("宁德时代 <span class=\"val up\">+2.81亿</span>（电池）<br>天孚通信 +2.11亿 / 中远海控 +2.02亿 / 中兴通讯 +1.85亿 / 药明康德 +1.57亿",
  "宁德时代 <span class=\"val up\">+3.57亿</span>（电池）<br>中国巨石 +2.86亿（玻纤） / 麦格米特 +2.61亿 / 浪潮信息 +2.23亿 / 紫金矿业 +2.21亿<br>星网锐捷 +2.13亿 / 飞龙股份 +1.93亿 / 方正科技 +1.79亿"),
 ("宁德时代 <span class=\"val up\">+2.81亿</span>（电池）<br>天孚通信 +2.11亿 / 中远海控 +2.02亿 / 中兴通讯 +1.85亿 / 药明康德 +1.57亿",
  "宁德时代 <span class=\"val up\">+3.57亿</span>（电池）<br>中国巨石 +2.86亿（玻纤） / 麦格米特 +2.61亿 / 浪潮信息 +2.23亿 / 紫金矿业 +2.21亿<br>星网锐捷 +2.13亿 / 飞龙股份 +1.93亿 / 方正科技 +1.79亿"),
 # evidence: 热搜
 ("国芳集团 5板（一般零售）<br>集泰股份 4板（化学制品）/ 龙版传媒 4板（文化传媒）<br>博云新材·太阳电缆·云南旅游·光洋股份·金帝股份·信达地产 2板（军工 / 电缆 / 旅游 / 汽零 / 金属 / 地产）",
  "龙版传媒 5板（文化传媒，龙头一日一换）<br>罗牛山 +10.05%（养殖）/ 播恩集团 +10.04%（饲料）/ 中水渔业 +9.98%（渔业）<br>我爱我家 +10.14%（房地产服务）/ 易点天下 +11.12%（广告营销）/ 中国船舶 +9.18%（航海装备Ⅱ）"),
 # evidence: 指数小节标题日期
 ("二、核心指数表现（2026-09-02 收盘）", "二、核心指数表现（2026-09-04 收盘）"),
 # t_date 静态 cell
 ("<b>2026-09-03 收盘（北京时间，盘后）</b>", "<b>2026-09-04 收盘（北京时间，盘后）</b>"),
 # 硬编码英文小标题
 ("Next-Session Outlook (09-04 Fri)", "Next-Session Outlook (09-07 Mon)"),
]
for old, new in BODY:
    if old in html:
        html = html.replace(old, new, 1)
    else:
        print(f"[skip-body] 未命中: {old[:46]!r}")

# ============================================================
# 6) 雷达数值标签（红字组）—— 同步修正 0903 遗留的旧读数
# ============================================================
old_radar = '<text x="160" y="71">62</text><text x="237" y="120">68</text><text x="209" y="194">54</text>\n            <text x="160" y="167">78</text><text x="109" y="201">65</text><text x="55" y="118">88</text>'
new_radar = '<text x="160" y="71">52</text><text x="237" y="120">64</text><text x="209" y="194">56</text>\n            <text x="160" y="167">58</text><text x="109" y="201">55</text><text x="55" y="118">87</text>'
assert old_radar in html, "radar block not found"
html = html.replace(old_radar, new_radar, 1)

# ============================================================
# 7) 用字典值回写所有 data-i18n 兜底文本（源码与渲染一致、0 旧数据）
# ============================================================
_pat = re.compile(r'<(\w+)([^>]*\bdata-i18n="([^"]+)"[^>]*)>(.*?)</\1>', re.S)
def _repl(m):
    _tag, _attrs, _key, _inner = m.group(1), m.group(2), m.group(3), m.group(4)
    if _key in zh:
        return '<%s%s>%s</%s>' % (_tag, _attrs, zh[_key], _tag)
    return m.group(0)
html = _pat.sub(_repl, html)
# 7b) 残留旧日期兜底（09-03 现已为「前日引用」，仅替换残留的「当日」旧引用）
for _a, _b in [
    ("2026-09-02 · 收盘", "2026-09-04 · 收盘"),
    ("2026-09-02 · Close", "2026-09-04 · Close"),
]:
    html = html.replace(_a, _b)

# ============================================================
# 8) hub（web/psychology/index.html）插入 0904 条目
# ============================================================
HUB = os.path.join(HERE, "..", "web", "psychology", "index.html")
hub = open(HUB, encoding="utf-8").read()
if "crowd-psychology-risk-radar-20260904.html" not in hub:
    entry = """    },
    {
      file:"crowd-psychology-risk-radar-20260904.html", date:"2026-09-04",
      risk:"中", riskEn:"Medium",
      cycleZh:"放量分化 / 修复反弹", cycleEn:"Volume-rebound / Repair with divergence",
      cycleNoteZh:"涨股比修复·跌停清零", cycleNoteEn:"Breadth repairs · limit-down cleared",
      up:"46%", limitup:"42", board:"5板", turn:"¥2.03万亿",
      summaryZh:"涨股比由33%修复至46%、涨停42、跌停17→0清零、成交放量至¥2.03万亿（+2700亿）；指数仍小跌（上证−0.30%/深成−0.79%/创业板−0.78%），收于MA20/布林中轨下方。结构剧烈反转：昨日领跌第一的房地产服务+3.85%领涨，船舶（中国船舶+9.18%、主力5日+19.70亿第一）与农业养殖涨停潮（罗牛山/播恩集团/中水渔业）接力主线；玻璃玻纤−4.86%领跌=融资逆势加仓被闷杀；连板5板（龙版传媒）三日锁高、龙头一日一换=放量分化/修复反弹，风险等级由高转中。",
      summaryEn:"Up-ratio repairs 33%→46%, 42 limit-up, limit-down cleared 17→0, turnover expands to ¥2.03tn (+¥270bn); indices still dip (SSE −0.30% / SZ −0.79% / ChiNext −0.78%), below MA20 / BOLL mid. Sharp reversal: yesterday's worst loser real-estate services +3.85% now leads, shipbuilding (China Shipbuilding +9.18%, main-5d +¥1.97bn #1) & agri-breeding limit-up wave (Luoniu/Boen/Zhongshui) take over; glass-fiber −4.86% leads down = margin-chasing trapped; 5-board streak (Longban Media) locked 3rd day, leader rotates daily = volume-rebound / repair with divergence, risk High→Medium."""
    tail = "    }\n  ];\n  REPORTS.reverse();"
    assert tail in hub, "hub tail not found"
    hub = hub.replace(tail, entry + "\n  ];\n  REPORTS.reverse();", 1)
    open(HUB, "w", encoding="utf-8").write(hub)
    print("[ok] hub 已插入 0904 条目")
else:
    print("[skip] hub 已有 0904 条目")

# ============================================================
# 9) 写出 + 校验
# ============================================================
open(OUT, "w", encoding="utf-8").write(html)
shutil.copyfile(OUT, os.path.join(HERE, "crowd-psychology-risk-radar-20260904.html"))
print(f"[ok] 写出 {OUT} ({len(html)} bytes)")

leftover = ["3942.09", "13625.12", "3312.54", "1846", "3570", "国芳集团 5板", "¥1.76万亿",
            "海通发展 5板", "宁德时代 +2.81亿", "航运港口 +2.99%", "房地产服务 −3.47%",
            "博云新材", "集泰股份 4板", "天孚通信", "中远海控", "33%","46</text>","17</text>"]
bad = [s for s in leftover if s in html]
print("残留旧数据:", bad if bad else "无")
print("2026-09-04 出现次数:", html.count("2026-09-04"))
print("外部引用 http(s):", len(re.findall(r'https?://', html)))
must = ["3930.12", "13516.97", "3286.55", "2444", "2914", "46%", "42", "¥2.03万亿",
        "航海装备Ⅱ +6.49%", "龙版传媒 5板", "宁德时代 +3.57亿", "放量分化 / 修复反弹", "2026-09-04", "52", "58"]
miss = [s for s in must if s not in html]
print("缺失 09-04 标记:", miss if miss else "无")
