# -*- coding: utf-8 -*-
"""群体心理风险雷达 2026-09-07：以 09-04 页面为模板，覆盖全部动态内容。

数据来源（全部为 2026-09-07 真实收盘）：
  data_market_overview(type=all) / tool_ranking(limitup_days) /
  tool_ranking(margin_chg_d) / tool_ranking(cap_main_5d) / data_sector(ranking)
"""
import os, re, shutil

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "..", "web", "psychology", "crowd-psychology-risk-radar-20260904.html")
OUT = os.path.join(HERE, "..", "web", "psychology", "crowd-psychology-risk-radar-20260907.html")

html = open(SRC, encoding="utf-8").read()


def extract_inner(html, marker):
    if marker == "zh":
        m = re.search(r'zh:\{(.*?)\n    \},', html, re.S)
    else:
        m = re.search(r'en:\{(.*?)\n    \}', html, re.S)
    assert m, "找不到 %s 块" % marker
    return m


def parse(inner):
    d = {}
    pat = re.compile(r'([A-Za-z_][A-Za-z0-9_]*)\s*:\s*"((?:[^"\\]|\\.)*)"')
    for line in inner.split("\n"):
        for mm in pat.finditer(line):
            d[mm.group(1)] = mm.group(2)
    return d


def esc(s):
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


m_zh = extract_inner(html, "zh")
m_en = extract_inner(html, "en")
zh0 = parse(m_zh.group(1))
en0 = parse(m_en.group(1))
print("[ok] 解析 zh 键 %d / en 键 %d" % (len(zh0), len(en0)))

# ============================================================
# 1) 09-07 叙述覆盖（中文）
# ============================================================
ZH = {
 "t_headline_sub": "2026-09-07 · 收盘",
 "t_breadth": "市场涨跌分布（2026-09-07 收盘）",
 "hk_stage": "阶段定性", "hv_stage": "<b>科技反攻 / 普涨回暖</b>（09-07）",
 "hk_upratio": "涨股比", "hv_upratio": "<b>57%</b>（前次 09-04 46% · ↑ 11pct，广度显著修复）",
 "hk_lim": "涨停 / 跌停", "hv_lim": "<b>90</b> / <b>1</b>（涨停翻倍，跌停近乎清零）",
 "hk_amt": "成交额", "hv_amt": "<b>¥1.95万亿</b>（小幅缩量 −840亿，仍为 10 日均 99.5%）",
 "hk_cycle": "情绪周期", "hv_cycle": "<b>科技反攻 / 普涨回暖</b>",
 "hk_risk": "风险等级", "hv_risk": "<b class=\"hl-risk\">中</b>（维持）",
 "hk_flag": "关键提示",
 "hv_flag": "涨股比 46%→<b>57%</b>、涨停 42→<b>90</b>、创业板 <b>+3.41%</b>——广度与赚钱效应同步回暖；但成交小幅缩量 −840亿，且融资单日前五（天孚通信 +3.04亿 / 新易盛 +1.99亿 / 剑桥科技 +1.75亿 / 德科立 +1.48亿）与主力5日前八（中际旭创 +44.39亿起）高度集中于光模块/PCB，杠杆与主线拥挤度明显上升，估值 PE_TTM 20.39（10年分位 79.52%）仍偏高",
 "tk1": "阶段定性", "tv1": "A 股 09-07 由 09-04「放量分化 / 修复反弹」升级为「<b>科技反攻 / 普涨回暖</b>」：涨股比升至 <b>57%</b>（3167涨 / 2196跌 / 平195，由 46% 再修复 +11pct），涨停 <b>90</b>（42→90，翻倍），跌停仅 1；创业板 <b>+3.41%</b>（3398.68）、深成 +1.91%（13774.91）、上证 +0.07%（3932.70）三指齐涨，成长风格大幅跑赢。成交 ¥1.95万亿（环比 <b>−840亿</b>，仍达 10 日均 99.5%）。风险等级维持<b>中</b>。",
 "tk2": "广度显著修复", "tv2": "涨股比 <b>57%</b>（前次 46% ↑ 11pct）· 涨停 <b>90</b>（42→90）· 跌停 <b>1</b>（近乎清零）· 成交 <b>¥1.95万亿</b>（小幅缩量 −840亿，10 日均 99.5%）——赚钱效应与参与度同步回升，指数与个股背离彻底收敛。",
 "tk3": "指数转强", "tv3": "上证 <b>+0.07%</b>（3932.70）几乎平收、深成 <b>+1.91%</b>（13774.91）、创业板 <b>+3.41%</b>（3398.68）——成长风格全面占优；上证收 3932.70 仍贴近 MA20（3935.82）与布林中轨，MACD 红柱 2.557（DIF 7.13 > DEA 5.85）但较前期收敛，KDJ 中位（K57.9/D63.3/J47.1），RSI_12 50.35 中性。",
 "tk4": "板块结构", "tv4": "<b>元件 +7.55%</b>（迅捷兴 +20%）与 <b>通信设备 +7.15%</b>（太辰光 +14.5%）领涨，非金属材料Ⅱ +4.72%（长江材料 +10%）/ 渔业 +4.59%（中水渔业 +9.96%）/ 电子化学品Ⅱ +4.51%（中石科技 +17.39%）/ 种植业 +4.48%（亚盛集团 +10.09%）/ 自动化设备 +4.12% 跟随——<b>光模块 / PCB / 元件 / 电子化学品构成 TMT 主线</b>；<b>保险Ⅱ −3.00%</b>（中国人保 −1.75%）领跌，贵金属 −2.91%（山金国际 −1.71%）/ 煤炭开采 −2.63% / 厨卫电器 −2.34% / 化学纤维 −1.97% / 国有大型银行Ⅱ −1.88%——红利与资源方向集体退潮。",
 "tk5": "连板结构", "tv5": "连板高度 <b>6 板</b>（龙版传媒，由 5 板晋级，但公司已公告 AI 视频业务营收占比不足 0.01%、上半年净利同比 −34.46%）；3板 3 只（亚盛集团 / 百大集团 / 爱仕达）、2板 9 只（安记食品 / 敦煌种业 / 中水渔业 / 天沃科技 / 播恩集团 / 华天酒店 / 海欣食品 / 罗牛山 / 中国出版）、首板 81 只——<b>高度上移但题材由农业食品/地产链切换至 TMT</b>。",
 "tk6": "杠杆转向", "tv6": "融资单日加仓榜 <b>天孚通信 +3.04亿 居首</b>，新易盛 +1.99亿、我爱我家 +1.85亿、剑桥科技 +1.75亿、德科立 +1.48亿、协创数据 +1.31亿——<b>杠杆由电池/玻纤全面转向光模块（前五占三席）</b>，方向高度集中；与 09-04「中国巨石加仓却被闷杀」不同，本次杠杆加仓方向与当日领涨主线一致，短期共振但拥挤度快速累积。",
 "tk7": "估值 / 风格", "tv7": "PE_TTM <b>20.39</b>（10年分位 <b>79.52%</b> 仍偏高）+ PB 1.75（估值口径 09-03）；风格 20 日口径<b>价值仍占优</b>（价值 +1.43% vs 成长 −3.48%），但当日成长大幅反攻（创业板 +3.41%）——属超跌成长的技术性修复，尚未扭转中期价值主导格局。",
 "tk8": "情绪周期", "tv8": "由 09-04「放量分化 / 修复反弹」转入「<b>科技反攻 / 普涨回暖</b>」：广度 57%、涨停翻倍至 90、跌停近乎清零、创业板 +3.41% 领涨，恐慌基本出清；但成交小幅缩量 −840亿、杠杆与主资金高度集中于光模块/PCB、估值分位 79.52% 仍高、连板 6 板龙头基本面已公告不匹配——<b>回暖确认但结构拥挤，风险等级维持中</b>。",
 "t_tldr_text": "A股 09-07 呈现「科技反攻 / 普涨回暖」：涨股比 46%→57%（3167涨/2196跌/平195），涨停 42→90 翻倍，跌停仅 1，创业板 +3.41%（3398.68）领涨、深成 +1.91%、上证 +0.07%（3932.70）；成交 ¥1.95万亿（环比 −840亿，仍为 10 日均 99.5%）。元件 +7.55%（迅捷兴 +20%）/ 通信设备 +7.15%（太辰光 +14.5%）领涨，非金属材料Ⅱ +4.72% / 渔业 +4.59% / 电子化学品Ⅱ +4.51%（中石科技 +17.39%）/ 种植业 +4.48% 跟随，TMT 主线成型；保险Ⅱ −3.00% 领跌，贵金属 −2.91% / 煤炭开采 −2.63% / 国有大型银行Ⅱ −1.88% 红利资源退潮。连板高度 6板（龙版传媒，已公告 AI 业务营收占比<0.01%），3板 3 只、2板 9 只、首板 81 只。资金信号：融资单日天孚通信 +3.04亿居首（新易盛 +1.99亿、剑桥科技 +1.75亿、德科立 +1.48亿，光模块占前五三席）；主力5日中际旭创 +44.39亿第一、新易盛 +33.80亿、工业富联 +22.25亿、剑桥科技 +19.61亿。估值 PE_TTM 20.39（10年分位 79.52%）仍偏高——回暖确认但杠杆与主线拥挤，风险等级中。",
 "t_cycle_note": "注：上方「中性偏暖」为实时群体心理定位（科技反攻 / 普涨回暖）——09-07 涨跌分布（涨股比 57%、涨停 90、跌停 1、成交 ¥1.95万亿）显示广度显著修复、恐慌出清、赚钱效应回升；但成交小幅缩量、融资与主力资金高度集中于光模块/PCB、估值分位 79.52% 仍高。若 09-08 涨股比守住 50% 上方且成交不再缩量，回暖延续；若光模块主线放量滞涨或龙头断板，则视为情绪透支，回撤风险上升。",
 "t_radar_note": "六维风险读数（0–100，由下方真实数据综合映射，越高代表该维度群体脆弱性越强）：拥挤度 58 / 融资 70 / 换手 54 / 广度 46 / 媒体 62 / 估值 87。广度由 58 降至 46（09-07 涨股比升至 57%、跌停近乎清零，参与度实质改善）；换手由 56 降至 54（成交 ¥1.95万亿，10 日均 99.5%，量能小幅回落）；融资由 64 升至 70（单日加仓前五中光模块占三席：天孚通信 +3.04亿 / 新易盛 +1.99亿 / 剑桥科技 +1.75亿，杠杆方向高度集中）；拥挤度由 52 升至 58（主线收敛至光模块/PCB/元件，主力5日前十中 7 只为光通信或 PCB，赚钱效应集中）；媒体由 55 升至 62（涨停 90、6 板龙头、创业板 +3.41%，情绪温度明显升温）；估值 87 持平（PE_TTM 20.39、10年分位 79.52%，口径 09-03 未变）。整体脆弱性由「广度+估值」转向「融资+拥挤+媒体」——情绪回暖确认，但杠杆与主线集中度上升成为新的风险源。",
 "t_breadth_note": "涨股比由 46% 升至 57%、涨停 42→90 翻倍、跌停维持近零（1 只）；成交 ¥1.95万亿环比 −840亿（小幅缩量，仍为 10 日均 99.5%）。指数全面转强：创业板 +3.41% / 深成 +1.91% / 上证 +0.07%，上证收 3932.70 贴近 MA20（3935.82）与布林中轨；元件 +7.55% / 通信设备 +7.15% 领涨，保险Ⅱ −3.00% / 贵金属 −2.91% 领跌——TMT 主线成型、红利资源退潮。",
 "ev_upratio_i": "由 46% 升至 57%（+11pct），涨 3167 / 跌 2196 / 平 195，参与度显著回升，跌停近乎清零显示恐慌盘彻底出清",
 "ev_limit_i": "涨停 90（42→90 翻倍）、跌停 1，连板高度升至 6板（龙版传媒）——投机热度明显升温，赚钱效应集中於 TMT",
 "ev_amount_i": "量能 ¥1.95万亿（环比 −840亿，10 日均的 99.5%），小幅缩量但仍在均位附近——回暖由存量资金再分配驱动，增量尚不显著",
 "ev_sh_i": "微涨 +0.07%（3932.70），收于 MA20 3935.82 与布林中轨略下方，MACD 红柱 2.557 收敛（DIF 7.13 > DEA 5.85），RSI_12 50.35 中性，PE_TTM 20.39（10年分位 79.52% 偏高）",
 "ev_sz_i": "深成 +1.91%（13774.91），跟随创业板走强，中期弱势边际改善，但仍需量能确认",
 "ev_cyb_i": "创业板 +3.41%（3398.68）领涨三大指数，成长风格全面反攻，属超跌技术性修复",
 "ev_secup_i": "元件 +7.55%（迅捷兴 +20%）/ 通信设备 +7.15%（太辰光 +14.5%）领涨，非金属材料Ⅱ +4.72%（长江材料 +10%）/ 渔业 +4.59%（中水渔业 +9.96%）/ 电子化学品Ⅱ +4.51%（中石科技 +17.39%）/ 种植业 +4.48%（亚盛集团 +10.09%）/ 自动化设备 +4.12%——光模块 / PCB / 元件 / 电子化学品构成 TMT 主线",
 "ev_secdn_i": "保险Ⅱ −3.00%（中国人保 −1.75%）领跌 / 贵金属 −2.91%（山金国际 −1.71%）/ 煤炭开采 −2.63% / 厨卫电器 −2.34% / 化学纤维 −1.97% / 国有大型银行Ⅱ −1.88%——红利、资源与前期防御方向集体退潮",
 "ev_board_i": "连板 6板（龙版传媒），3板 3 只（亚盛集团 / 百大集团 / 爱仕达），2板 9 只（安记食品 / 敦煌种业 / 中水渔业 / 天沃科技 / 播恩集团 / 华天酒店 / 海欣食品 / 罗牛山 / 中国出版），首板 81 只；热点由农业食品 / 地产链切换至 TMT（迅捷兴 +20% / 太辰光 +14.5% / 中石科技 +17.39%）",
 "ev_height_i": "高度 6板（龙版传媒，2026-09-07 收盘），由 5 板晋级；但公司已公告 AI 视频业务 6 月营收约 80 元、7 月约 7.5 万元，占 2025 年营收不足 0.01%，上半年归母净利同比 −34.46%——题材与基本面严重背离",
 "ev_main": "主力5日净流入TOP",
 "ev_main_i": "主力5日净流入高度集中于光模块 / PCB：中际旭创 +44.39亿 居首、新易盛 +33.80亿、工业富联 +22.25亿、剑桥科技 +19.61亿、光迅科技 +17.41亿、方正科技 +16.37亿、天孚通信 +13.24亿、德科立 +12.95亿；中国船舶 +12.89亿为前十中唯一非 TMT——主力定价权集中于单一赛道",
 "ev_margin": "融资单日变动TOP",
 "ev_margin_i": "融资单日加仓榜天孚通信居首（+3.04亿），新易盛 +1.99亿、我爱我家 +1.85亿、剑桥科技 +1.75亿、德科立 +1.48亿、协创数据 +1.31亿、云铝股份 +1.21亿、精智达 +1.15亿、宁德时代 +1.15亿、恒宝股份 +1.14亿——前五中光模块占三席，杠杆方向由电池/玻纤切换至光通信",
 "ev_hot_i": "热点由 TMT 主导：龙版传媒 6板（文化传媒）/ 迅捷兴 +20%（元件）/ 太辰光 +14.5%（通信设备）/ 中石科技 +17.39%（电子化学品Ⅱ）/ 中水渔业 +9.96%（渔业）/ 亚盛集团 +10.09%（种植业）；data_hot 板块榜首位为通信设备、元件、共封装光模块(CPO)，与主力资金高度一致",
 "ev_margintotal_i": "缺口：聚合两融余额（data_market_overview type=margin）返回空，以个股融资变动替代观察（见上）；连板高度 / 融资单日 / 主力5日均为 2026-09-07 真实数据",
 "t_ev_note": "数据口径：宏观指标多截至 2026-07（月频）或 2026-09-07（日频）；涨跌分布 / 指数 / 成交额 / 板块 / 融资单日 / 主力5日 / 连板梯队均为 2026-09-07 真实收盘。估值 PE_TTM 20.39 为 2026-09-03 口径（中证全指估值滞后发布），已在正文标注。详见末尾「数据来源与日期口径」。",
 "rc1_tag": "红线区 · 光模块杠杆与主力双集中 + 高估值",
 "rc1_t": "光模块杠杆与主力双集中 + 高估值",
 "rc1_d": "融资单日前五中光模块占三席（天孚通信 +3.04亿 / 新易盛 +1.99亿 / 剑桥科技 +1.75亿），主力5日前十中 7 只为光通信或 PCB（中际旭创 +44.39亿起）——杠杆与主力定价权同时集中于同一赛道，一旦证伪回撤幅度大；叠加 PE_TTM 20.39、10年分位 79.52% 仍偏高，6 板龙头龙版传媒已公告 AI 业务营收占比不足 0.01%——题材与基本面严重背离。",
 "rc1_rep": "代表：光模块（中际旭创 / 新易盛 / 天孚通信）/ PCB（迅捷兴 / 兴森科技）/ 6板龙头（龙版传媒）",
 "rc2_tag": "黄线区 · 成交缩量下的普涨（量价背离）",
 "rc2_t": "成交缩量下的普涨",
 "rc2_d": "涨停翻倍至 90、涨股比 57%、创业板 +3.41%，但成交环比 −840亿至 ¥1.95万亿（10 日均 99.5%）——回暖由存量资金再分配驱动而非增量入场，量价存在背离；上证 +0.07% 几乎平收、仍收于 MA20 与布林中轨略下方，权重股未跟进。",
 "rc2_rep": "代表：创业板 / 深成指（成长风格反攻）/ 上证权重（未同步）",
 "rc3_tag": "绿线区 · 红利与资源退潮（相对）",
 "rc3_t": "红利 / 资源方向退潮",
 "rc3_d": "保险Ⅱ −3.00%（中国人保 −1.75%）领跌，贵金属 −2.91%（山金国际 −1.71%）/ 煤炭开采 −2.63% / 化学纤维 −1.97% / 国有大型银行Ⅱ −1.88% / 农商行Ⅱ −1.66%——前期防御与资源方向在风险偏好回升时被抛售，属资金再平衡而非基本面恶化，但提示高低切换仍在进行。",
 "rc3_rep": "代表：保险Ⅱ（中国人保）/ 贵金属（山金国际）/ 煤炭开采（上海能源）",
 "t_sec_outlook": "下个交易日（09-08 周二）展望",
 "o_logic": "研判逻辑（基于 09-07 收盘 + 群体心理定位）",
 "o_logic_text": "由 09-07 的「科技反攻 / 普涨回暖」延伸：情绪周期定位「科技反攻 / 普涨回暖」，涨股比 57%、涨停 90、跌停 1、创业板 +3.41%，广度与赚钱效应同步修复；但成交小幅缩量 −840亿、融资与主力资金高度集中于光模块/PCB、估值分位 79.52% 仍高、6 板龙头基本面已公告不匹配。基于此推演 09-08 的板块方向与交易规则（<b>不涉及具体个股推荐</b>）。",
 "o1_tag": "光模块 / PCB（观察）",
 "o1_t": "通信设备 / 元件 / 电子化学品Ⅱ",
 "o1_d": "09-07 最强主线：元件 +7.55%（迅捷兴 +20%）/ 通信设备 +7.15%（太辰光 +14.5%），主力5日中际旭创 +44.39亿、新易盛 +33.80亿居前——价格与资金双共振，主线地位短期难以撼动。",
 "o1_cond": "注意：杠杆与主力双集中 = 拥挤度高，单日暴涨后忌追高；若龙头放量滞涨或涨停家数骤降，视为透支信号，只做回踩不追突破。",
 "o2_tag": "成长超跌修复（观望）",
 "o2_t": "半导体 / 消费电子 / 自动化设备",
 "o2_d": "09-07 半导体 +3.36% / 消费电子 +2.78% / 自动化设备 +4.12% 跟随创业板 +3.41% 反攻，属估值分位偏高背景下的技术性修复，尚未得到业绩或订单验证。",
 "o2_cond": "注意：修复需 2 日以上量价确认；成交若继续缩量，反弹持续性不足，不重仓、不加杠杆。",
 "o3_tag": "红利 / 资源退潮（回避）",
 "o3_t": "保险Ⅱ / 贵金属 / 煤炭开采",
 "o3_d": "09-07 保险Ⅱ −3.00% 领跌、贵金属 −2.91%（山金国际 −1.71%）/ 煤炭开采 −2.63% / 国有大型银行Ⅱ −1.88% 集体退潮——风险偏好回升期的资金再平衡，短期承压。",
 "o3_cond": "注意：属高低切换而非基本面恶化，不盲目杀跌；但主线未确认前不宜左侧抄底，等待缩量止跌信号。",
 "o_r1": "<b>仓位</b>：中性（5 成左右），不加杠杆。情绪由「放量分化 / 修复反弹」升级「科技反攻 / 普涨回暖」，风险等级维持中，可参与但不追高。",
 "o_r2": "<b>量价确认</b>：涨股比 ≥50% 且成交回升至 ¥2 万亿上方，方可将仓位提至上限；若成交继续缩量至 ¥1.8万亿以下，视为回暖动力不足，降仓至 ≤3 成。",
 "o_r3": "<b>主线参与</b>：光模块 / PCB 只做回踩不追高，重点看龙头是否放量滞涨；成长超跌修复方向需 2 日以上量价确认再介入。",
 "o_r4": "<b>回避清单</b>：6 板及以上高位连板（龙版传媒已公告 AI 业务营收占比<0.01%，题材与基本面严重背离）、杠杆与主力双集中且已连续大涨的光模块个股追高、红利资源左侧抄底。",
 "o_r5": "<b>风控</b>：若 09-08 光模块主线龙头断板或涨停家数较 90 家腰斩，视为情绪透支，立即降仓；上证跌破 MA20（3935.82）则转防守。",
 "s_breadth_v": "westock · data_market_overview(market_statis_updown)；2026-09-07 收盘",
 "s_portrait_v": "westock · data_market_overview(type=summary)；2026-09-07（涨股比 57% 真实广度修复，科技反攻）",
 "s_index_v": "westock · data_market_overview(market_statis_daily_trade)；2026-09-07 收盘",
 "s_sector_v": "westock · data_sector(mode=ranking, kind=industry/concept)；2026-09-07",
 "s_hot_v": "westock · data_hot(kind=board)；2026-09-07（通信设备 / 元件 / CPO 居前）",
 "s_margin_v": "westock · tool_ranking(metric=margin_chg_d)；2026-09-07",
 "s_main_v": "westock · tool_ranking(metric=cap_main_5d)；2026-09-07（中际旭创 +44.39亿 居首）",
 "s_board_v": "westock · tool_ranking(metric=limitup_days)；2026-09-07（当日排行榜已刷新，共 94 只）",
 "s_gap_v": "市场两融余额聚合值（data_market_overview type=margin）数据源返回空，已用个股融资变动替代，未编造；估值 PE_TTM 20.39 为 2026-09-03 口径（中证全指估值滞后发布），已标注。",
 "t_src_note": "时间口径：所有时点按北京时间。宏观为月频 / 季频，与日频行情不可直接对齐，已分别标注。涨跌分布 / 指数 / 板块 / 融资单日 / 主力5日 / 连板梯队均为 2026-09-07 当日真实数据；估值为 2026-09-03 口径。",
 "ev_index": "二、核心指数表现（2026-09-07 收盘）",
 "o_rules_t": "交易规则（09-08）",
 "o_compliance": "<b>合规说明：</b>本展望仅给出板块方向与交易规则，不涉及具体个股推荐；群体心理定位与板块推断基于 2026-09-07 真实行情数据，市场有风险，决策须独立。",
 "t_risk_hi": "中",
}

EN = {
 "t_headline_sub": "2026-09-07 · Close",
 "t_breadth": "Market breadth (2026-09-07 close)",
 "hk_stage": "Stage", "hv_stage": "<b>Tech counter-offensive / Broad recovery</b> (09-07)",
 "hk_upratio": "Up-ratio", "hv_upratio": "<b>57%</b> (prev 09-04 46% · ↑ 11pct, breadth repairs notably)",
 "hk_lim": "Limit-up / -down", "hv_lim": "<b>90</b> / <b>1</b> (limit-up doubles, limit-down near zero)",
 "hk_amt": "Turnover", "hv_amt": "<b>¥1.95tn</b> (−¥84bn vs prev, still 99.5% of 10d avg)",
 "hk_cycle": "Sentiment cycle", "hv_cycle": "<b>Tech counter-offensive / Broad recovery</b>",
 "hk_risk": "Risk level", "hv_risk": "<b class=\"hl-risk\">Medium</b> (unchanged)",
 "hk_flag": "Key flag",
 "hv_flag": "Up-ratio 46%→<b>57%</b>, limit-up 42→<b>90</b>, ChiNext <b>+3.41%</b> — breadth and profit effect recover together; yet turnover shrinks −¥84bn, and both margin top-5 (TFC +¥304mn / Innolight +¥199mn / Cambridge +¥175mn / Dekel +¥148mn) and main-5d top-8 (Innolight #1 +¥4.44bn) cluster heavily in optical modules / PCB; valuation PE_TTM 20.39 (10y pctile 79.52%) still rich",
 "tk1": "Stage", "tv1": "A-shares 09-07 upgrade from 09-04's \"volume-rebound / repair with divergence\" to \"<b>tech counter-offensive / broad recovery</b>\": up-ratio rises to <b>57%</b> (3167 up / 2196 down / 195 flat, +11pct from 46%), limit-up <b>90</b> (42→90, doubled), limit-down just 1; ChiNext <b>+3.41%</b> (3398.68), SZ Component +1.91% (13774.91), SSE +0.07% (3932.70) — all three up, growth style outperforms. Turnover ¥1.95tn (−<b>¥84bn</b> QoQ, still 99.5% of the 10d average). Risk level stays <b>Medium</b>.",
 "tk2": "Breadth repairs", "tv2": "Up-ratio <b>57%</b> (prev 46%, ↑11pct) · limit-up <b>90</b> (42→90) · limit-down <b>1</b> (near zero) · turnover <b>¥1.95tn</b> (−¥84bn, 99.5% of 10d avg) — profit effect and participation rebound together; the index/stock divergence fully converges.",
 "tk3": "Indices turn up", "tv3": "SSE <b>+0.07%</b> (3932.70) nearly flat, SZ Component <b>+1.91%</b> (13774.91), ChiNext <b>+3.41%</b> (3398.68) — growth style dominates; SSE closes at 3932.70, still just below MA20 (3935.82) and the BOLL mid; MACD bar 2.557 narrowing (DIF 7.13 > DEA 5.85), KDJ mid (K57.9/D63.3/J47.1), RSI_12 50.35 neutral.",
 "tk4": "Sector structure", "tv4": "<b>Components +7.55%</b> (Xunjiexing +20%) and <b>Comms equipment +7.15%</b> (T&S Comm +14.5%) lead; Non-metal MaterialsⅡ +4.72% (Changjiang Materials +10%) / Fisheries +4.59% (Zhongshui +9.96%) / Electronic ChemicalsⅡ +4.51% (Zhongshi Tech +17.39%) / Planting +4.48% (Yasheng +10.09%) / Automation +4.12% follow — <b>optical modules / PCB / components / electronic chemicals form the TMT main line</b>; <b>InsuranceⅡ −3.00%</b> (PICC −1.75%) leads losers, Precious Metals −2.91% (Shanjin −1.71%) / Coal Mining −2.63% / Kitchen & Bath −2.34% / Chemical Fibre −1.97% / State-owned BanksⅡ −1.88% — dividend and resource names retreat together.",
 "tk5": "Limit-up ladder", "tv5": "Ladder height <b>6 boards</b> (Longban Media, up from 5) — though the company disclosed AI-video revenue <0.01% of 2025 sales and H1 net profit −34.46% YoY; 3-board ×3 (Yasheng / Bauda / Aishida), 2-board ×9 (Anji Food / Dunhuang Seed / Zhongshui / Tianwo / Boen / Huatian Hotel / Haixin Food / Luoniu / China Publishing), first-board ×81 — <b>height rises while themes rotate from agri/property to TMT</b>.",
 "tk6": "Leverage rotation", "tv6": "Daily margin add: <b>TFC Optical +¥304mn #1</b>, Innolight +¥199mn, Wuwo Wujia +¥185mn, Cambridge Tech +¥175mn, Dekel +¥148mn, Xiechuang Data +¥131mn — <b>leverage rotates wholesale from batteries/fiberglass into optical modules (3 of top 5)</b>; unlike 09-04 (adding into trapped fiberglass), this time leverage aligns with the day's leading line — short-term resonance, but crowding builds fast.",
 "tk7": "Valuation / style", "tv7": "PE_TTM <b>20.39</b> (10y pctile <b>79.52%</b>, still rich) + PB 1.75 (valuation as of 09-03); on a 20d view <b>value still leads</b> (value +1.43% vs growth −3.48%), yet growth counter-attacks intraday (ChiNext +3.41%) — a technical bounce in oversold growth, not yet a reversal of the medium-term value-led regime.",
 "tk8": "Sentiment cycle", "tv8": "From 09-04's \"volume-rebound / repair with divergence\" into \"<b>tech counter-offensive / broad recovery</b>\": breadth 57%, limit-up doubled to 90, limit-down near zero, ChiNext +3.41% leads — panic essentially cleared; yet turnover shrinks ¥84bn, leverage and main capital cluster in optical modules/PCB, valuation pctile 79.52% still rich, and the 6-board leader has disclosed fundamentals that do not match the story — <b>recovery confirmed but structure crowded; risk stays Medium</b>.",
 "t_tldr_text": "A-shares 09-07 = \"tech counter-offensive / broad recovery\": up-ratio 46%→57% (3167 up / 2196 down / 195 flat), limit-up 42→90, limit-down just 1, ChiNext +3.41% (3398.68) leads, SZ +1.91%, SSE +0.07% (3932.70); turnover ¥1.95tn (−¥84bn, 99.5% of 10d avg). Components +7.55% (Xunjiexing +20%) / Comms equipment +7.15% (T&S +14.5%) lead; Non-metal MaterialsⅡ +4.72% / Fisheries +4.59% / Electronic ChemicalsⅡ +4.51% (Zhongshi +17.39%) / Planting +4.48% follow — the TMT main line forms; InsuranceⅡ −3.00% leads losers, Precious Metals −2.91% / Coal −2.63% / State BanksⅡ −1.88% retreat. Ladder height 6 boards (Longban Media, AI revenue <0.01% disclosed), 3-board ×3, 2-board ×9, first-board ×81. Capital: daily margin TFC +¥304mn #1 (Innolight +¥199mn, Cambridge +¥175mn, Dekel +¥148mn, optical modules take 3 of top 5); main-5d Innolight +¥4.44bn #1, XYS +¥3.38bn, Foxconn Industrial +¥2.22bn, Cambridge +¥1.96bn. Valuation PE_TTM 20.39 (10y pctile 79.52%) still rich — recovery confirmed but leverage and main-line crowding rise; risk Medium.",
 "t_cycle_note": "Note: the \"neutral-to-warm\" tag above is the live crowd-psychology position (tech counter-offensive / broad recovery) — 09-07 breadth (up-ratio 57%, limit-up 90, limit-down 1, turnover ¥1.95tn) shows breadth repairing, panic cleared and profit effect returning; yet turnover shrinks, leverage and main capital concentrate in optical modules/PCB, valuation pctile 79.52% remains rich. If 09-08 holds up-ratio above 50% and turnover stops shrinking, the recovery extends; if the optical-module line stalls on volume or the ladder leader breaks, treat it as sentiment exhaustion and downside risk rises.",
 "t_radar_note": "Six-dimension risk readings (0–100, mapped from the real data below; higher = greater crowd fragility on that axis): crowding 58 / margin 70 / turnover 54 / breadth 46 / media 62 / valuation 87. Breadth 58→46 (up-ratio rises to 57%, limit-down near zero, participation materially improves); turnover 56→54 (¥1.95tn, 99.5% of 10d avg, volume eases slightly); margin 64→70 (3 of the top-5 daily adds are optical modules: TFC +¥304mn / Innolight +¥199mn / Cambridge +¥175mn, leverage highly concentrated); crowding 52→58 (the main line narrows to optical modules/PCB/components, 7 of the main-5d top-10 are optical or PCB); media 55→62 (limit-up 90, 6-board leader, ChiNext +3.41%, sentiment heats up); valuation 87 flat (PE_TTM 20.39, 10y pctile 79.52%, as of 09-03). Fragility shifts from \"breadth + valuation\" to \"margin + crowding + media\" — recovery confirmed, but leverage and main-line concentration become the new risk source.",
 "t_breadth_note": "Up-ratio rises 46%→57%, limit-up doubles 42→90, limit-down stays near zero (1); turnover ¥1.95tn, −¥84bn QoQ (slight shrink, still 99.5% of the 10d average). Indices turn broadly stronger: ChiNext +3.41% / SZ +1.91% / SSE +0.07%, with SSE closing at 3932.70 just under MA20 (3935.82) and the BOLL mid; Components +7.55% / Comms equipment +7.15% lead, InsuranceⅡ −3.00% / Precious Metals −2.91% lag — TMT main line forms while dividend/resource names retreat.",
 "ev_upratio_i": "46%→57% (+11pct), 3167 up / 2196 down / 195 flat; participation rebounds, limit-down near zero shows panic fully cleared",
 "ev_limit_i": "Limit-up 90 (42→90, doubled), limit-down 1, ladder height up to 6 boards (Longban Media) — speculative heat rises, profit effect concentrates in TMT",
 "ev_amount_i": "Turnover ¥1.95tn (−¥84bn QoQ, 99.5% of the 10d average) — slight shrink but still near average; the recovery is driven by reallocation of existing capital, not fresh inflows",
 "ev_sh_i": "+0.07% (3932.70), closing just below MA20 3935.82 and the BOLL mid; MACD bar 2.557 narrowing (DIF 7.13 > DEA 5.85), RSI_12 50.35 neutral, PE_TTM 20.39 (10y pctile 79.52%, rich)",
 "ev_sz_i": "SZ Component +1.91% (13774.91), following ChiNext higher; the medium-term downtrend improves marginally but still needs volume confirmation",
 "ev_cyb_i": "ChiNext +3.41% (3398.68) leads all three indices; growth style counter-attacks broadly — a technical bounce from oversold levels",
 "ev_secup_i": "Components +7.55% (Xunjiexing +20%) / Comms equipment +7.15% (T&S +14.5%) lead; Non-metal MaterialsⅡ +4.72% (Changjiang Materials +10%) / Fisheries +4.59% (Zhongshui +9.96%) / Electronic ChemicalsⅡ +4.51% (Zhongshi Tech +17.39%) / Planting +4.48% (Yasheng +10.09%) / Automation +4.12% — optical modules / PCB / components / electronic chemicals form the TMT main line",
 "ev_secdn_i": "InsuranceⅡ −3.00% (PICC −1.75%) leads losers / Precious Metals −2.91% (Shanjin −1.71%) / Coal Mining −2.63% / Kitchen & Bath −2.34% / Chemical Fibre −1.97% / State-owned BanksⅡ −1.88% — dividend, resource and former defensive names retreat together",
 "ev_board_i": "Ladder 6 boards (Longban Media), 3-board ×3 (Yasheng / Bauda / Aishida), 2-board ×9 (Anji Food / Dunhuang Seed / Zhongshui / Tianwo / Boen / Huatian Hotel / Haixin Food / Luoniu / China Publishing), first-board ×81; hotspots rotate from agri-food/property to TMT (Xunjiexing +20% / T&S +14.5% / Zhongshi Tech +17.39%)",
 "ev_height_i": "Height 6 boards (Longban Media, 2026-09-07 close), up from 5; yet the company disclosed AI-video revenue of ~¥80 in June and ~¥75k in July, <0.01% of 2025 sales, with H1 net profit −34.46% YoY — the story diverges sharply from fundamentals",
 "ev_main": "Main capital 5d net inflow TOP",
 "ev_main_i": "Main-5d inflow concentrates in optical modules / PCB: Innolight +¥4.44bn #1, XYS +¥3.38bn, Foxconn Industrial +¥2.22bn, Cambridge Tech +¥1.96bn, Accelink +¥1.74bn, Founder Tech +¥1.64bn, TFC +¥1.32bn, Dekel +¥1.30bn; China Shipbuilding +¥1.29bn is the only non-TMT in the top ten — pricing power concentrates in a single track",
 "ev_margin": "Daily margin change TOP",
 "ev_margin_i": "Daily margin adds: TFC Optical +¥304mn #1, Innolight +¥199mn, Wuwo Wujia +¥185mn, Cambridge Tech +¥175mn, Dekel +¥148mn, Xiechuang Data +¥131mn, Yunnan Aluminium +¥121mn, Jingzhida +¥115mn, CATL +¥115mn, Hengbao +¥114mn — optical modules take 3 of the top 5; leverage rotates from batteries/fiberglass to optical comms",
 "ev_hot_i": "Hotspots led by TMT: Longban Media 6 boards (media) / Xunjiexing +20% (components) / T&S Comm +14.5% (comms equipment) / Zhongshi Tech +17.39% (electronic chemicalsⅡ) / Zhongshui +9.96% (fisheries) / Yasheng +10.09% (planting); the data_hot board ranking leads with Comms Equipment, Components and CPO — fully consistent with main capital flows",
 "ev_margintotal_i": "Gap: aggregate margin balance (data_market_overview type=margin) returns empty, substituted with per-stock margin changes (see above); ladder height / daily margin / main-5d are all real 2026-09-07 data",
 "t_ev_note": "Data basis: macro indicators are monthly (mostly to 2026-07) or daily (to 2026-09-07); breadth / indices / turnover / sectors / daily margin / main-5d / ladder are all real 2026-09-07 closes. Valuation PE_TTM 20.39 is as of 2026-09-03 (CSI All-Share valuation published with a lag) and is flagged in the text. See \"Sources and date basis\" at the end.",
 "rc1_tag": "Red zone · Optical-module leverage & main-capital double concentration + rich valuation",
 "rc1_t": "Optical-module double concentration + rich valuation",
 "rc1_d": "Three of the top-5 daily margin adds are optical modules (TFC +¥304mn / Innolight +¥199mn / Cambridge +¥175mn) and 7 of the main-5d top-10 are optical or PCB (Innolight +¥4.44bn at the top) — leverage and main-capital pricing power concentrate in the same track, so a falsification would mean a deep drawdown; plus PE_TTM 20.39 at a 79.52% 10y pctile, and the 6-board leader has disclosed AI revenue <0.01% of sales — story and fundamentals diverge badly.",
 "rc1_rep": "Represented by: optical modules (Innolight / XYS / TFC) / PCB (Xunjiexing / Xingsen) / 6-board leader (Longban Media)",
 "rc2_tag": "Amber zone · Broad rally on shrinking turnover (volume-price divergence)",
 "rc2_t": "Broad rally on shrinking volume",
 "rc2_d": "Limit-up doubles to 90, up-ratio 57%, ChiNext +3.41% — yet turnover falls ¥84bn to ¥1.95tn (99.5% of the 10d average): the recovery is driven by reallocation of existing capital rather than fresh inflows, a volume-price divergence; the SSE adds just +0.07% and still closes slightly below MA20 and the BOLL mid, with heavyweights not following.",
 "rc2_rep": "Represented by: ChiNext / SZ Component (growth bounce) / SSE heavyweights (not following)",
 "rc3_tag": "Green zone · Dividend & resource retreat (relative)",
 "rc3_t": "Dividend / resource retreat",
 "rc3_d": "InsuranceⅡ −3.00% leads losers, Precious Metals −2.91% (Shanjin −1.71%) / Coal Mining −2.63% / Chemical Fibre −1.97% / State-owned BanksⅡ −1.88% / Rural Commercial BanksⅡ −1.66% — former defensive and resource names are sold as risk appetite returns; this is capital rebalancing rather than fundamental deterioration, but it signals the high-to-low switch is still running.",
 "rc3_rep": "Represented by: InsuranceⅡ (PICC) / Precious Metals (Shanjin) / Coal Mining (Shanghai Energy)",
 "t_sec_outlook": "Next session (09-08 Tue) outlook",
 "o_logic": "Reasoning (based on the 09-07 close + crowd-psychology position)",
 "o_logic_text": "Extending 09-07's \"tech counter-offensive / broad recovery\": the cycle sits at \"tech counter-offensive / broad recovery\", with up-ratio 57%, limit-up 90, limit-down 1 and ChiNext +3.41% — breadth and profit effect repair together; yet turnover shrinks ¥84bn, leverage and main capital concentrate in optical modules/PCB, valuation pctile 79.52% stays rich, and the 6-board leader's disclosed fundamentals do not match the story. Sector directions and trading rules for 09-08 follow (<b>no individual stock recommendations</b>).",
 "o1_tag": "Optical modules / PCB (watch)",
 "o1_t": "Comms equipment / Components / Electronic chemicalsⅡ",
 "o1_d": "09-07's strongest line: Components +7.55% (Xunjiexing +20%) / Comms equipment +7.15% (T&S +14.5%), with main-5d Innolight +¥4.44bn and XYS +¥3.38bn at the top — price and capital resonate; the main-line status is hard to shake near term.",
 "o1_cond": "Caution: leverage and main capital both concentrated = high crowding; do not chase after a one-day surge. If leaders stall on heavy volume or limit-up counts collapse, treat it as exhaustion — only buy pullbacks, not breakouts.",
 "o2_tag": "Oversold growth repair (wait)",
 "o2_t": "Semiconductors / Consumer electronics / Automation",
 "o2_d": "09-07 Semiconductors +3.36% / Consumer electronics +2.78% / Automation +4.12% follow ChiNext's +3.41% bounce — a technical repair against a rich valuation percentile, not yet validated by earnings or orders.",
 "o2_cond": "Caution: the repair needs 2+ sessions of volume-price confirmation; if turnover keeps shrinking, the bounce lacks stamina — no heavy positions, no leverage.",
 "o3_tag": "Dividend / resource retreat (avoid)",
 "o3_t": "InsuranceⅡ / Precious metals / Coal mining",
 "o3_d": "09-07 InsuranceⅡ −3.00% leads losers; Precious Metals −2.91% (Shanjin −1.71%) / Coal Mining −2.63% / State-owned BanksⅡ −1.88% retreat together — capital rebalancing as risk appetite returns; near-term pressure persists.",
 "o3_cond": "Caution: this is a high-to-low switch, not fundamental deterioration — do not panic-sell; but avoid left-side bottom-fishing before the main line is confirmed; wait for a shrinking-volume stabilisation signal.",
 "o_r1": "<b>Position</b>: neutral (~50%), no leverage. The cycle upgrades from \"volume-rebound / repair with divergence\" to \"tech counter-offensive / broad recovery\"; risk stays Medium — participate, but do not chase.",
 "o_r2": "<b>Volume-price confirmation</b>: only raise to the position cap if up-ratio ≥50% and turnover climbs back above ¥2tn; if turnover keeps shrinking below ¥1.8tn, treat the recovery as underpowered and cut to ≤30%.",
 "o_r3": "<b>Main-line participation</b>: in optical modules / PCB, buy pullbacks only, not breakouts — watch whether leaders stall on heavy volume; for oversold growth repairs, wait 2+ sessions of volume-price confirmation before entering.",
 "o_r4": "<b>Avoid list</b>: ladders at 6 boards or above (Longban Media disclosed AI revenue <0.01% of sales — story and fundamentals diverge sharply); chasing optical-module names that are both leverage- and main-capital concentrated after consecutive surges; left-side bottom-fishing in dividend/resources.",
 "o_r5": "<b>Risk control</b>: if optical-module leaders break their boards on 09-08 or limit-up counts halve from 90, treat it as sentiment exhaustion and cut exposure immediately; if the SSE breaks MA20 (3935.82), switch to defence.",
 "s_breadth_v": "westock · data_market_overview(market_statis_updown); 2026-09-07 close",
 "s_portrait_v": "westock · data_market_overview(type=summary); 2026-09-07 (up-ratio 57%, genuine breadth repair, tech counter-offensive)",
 "s_index_v": "westock · data_market_overview(market_statis_daily_trade); 2026-09-07 close",
 "s_sector_v": "westock · data_sector(mode=ranking, kind=industry/concept); 2026-09-07",
 "s_hot_v": "westock · data_hot(kind=board); 2026-09-07 (Comms Equipment / Components / CPO on top)",
 "s_margin_v": "westock · tool_ranking(metric=margin_chg_d); 2026-09-07",
 "s_main_v": "westock · tool_ranking(metric=cap_main_5d); 2026-09-07 (Innolight +¥4.44bn #1)",
 "s_board_v": "westock · tool_ranking(metric=limitup_days); 2026-09-07 (ranking refreshed, 94 names)",
 "s_gap_v": "Aggregate margin balance (data_market_overview type=margin) returns empty; per-stock margin changes substituted, nothing fabricated. Valuation PE_TTM 20.39 is as of 2026-09-03 (CSI All-Share valuation published with a lag) and is flagged.",
 "t_src_note": "Timing: all timestamps are Beijing time. Macro data are monthly/quarterly and cannot be aligned directly with daily quotes; each is flagged. Breadth / indices / sectors / daily margin / main-5d / ladder are real 2026-09-07 data; valuation is as of 2026-09-03.",
 "ev_index": "II. Core indices (2026-09-07 close)",
 "o_rules_t": "Trading rules (09-08)",
 "o_compliance": "<b>Compliance:</b> this outlook gives sector directions and trading rules only, with no individual stock recommendations; the crowd-psychology position and sector inferences are based on real 2026-09-07 market data. Markets carry risk; decisions must be independent.",
 "t_risk_hi": "Medium",
}

zh = dict(zh0); zh.update(ZH)
en = dict(en0); en.update(EN)


def serialize(d):
    return "\n".join('      %s:"%s",' % (k, esc(d[k])) for k in d)


new_en = "en:{\n" + serialize(en) + "\n    }"
html = html[:m_en.start()] + new_en + html[m_en.end():]
new_zh = "zh:{\n" + serialize(zh) + "\n    },"
html = html[:m_zh.start()] + new_zh + html[m_zh.end():]

# ============================================================
# 2) 重建 BIAS 数组（09-07 真实数据）
# ============================================================
BIAS = [
 {"zh":"羊群效应","en":"Herding","sev":4,
  "zhd":"涨股比升至57%、涨停翻倍至90，资金蜂拥涌入元件（+7.55%，迅捷兴+20%）与通信设备（+7.15%，太辰光+14.5%），主力5日前十中7只为光通信/PCB——群体高度跟随单一赛道，独立判断被赚钱效应淹没。",
  "end":"Up-ratio rises to 57% and limit-up doubles to 90; capital crowds into components (+7.55%, Xunjiexing +20%) and comms equipment (+7.15%, T&S +14.5%), with 7 of the main-5d top-10 in optical/PCB — the herd follows a single track and independent judgement is drowned by the profit effect."},
 {"zh":"损失厌恶","en":"Loss Aversion","sev":2,
  "zhd":"红利与资源方向被抛售（保险Ⅱ−3.00%/贵金属−2.91%/煤炭开采−2.63%），持有者在回暖首日选择切换而非止损，把「错过科技反弹」视为更大损失——由恐慌转为错失恐惧（FOMO）。",
  "end":"Dividend and resource names are sold (InsuranceⅡ −3.00% / precious metals −2.91% / coal −2.63%); holders switch rather than cut losses on the first recovery day, treating 'missing the tech bounce' as the bigger loss — panic morphs into fear of missing out."},
 {"zh":"心理账户/赌徒谬误","en":"Mental Acct / Gambler","sev":2,
  "zhd":"把光模块单日大涨外推为「主线已确立、还会再涨」，忽视连板6板龙头龙版传媒已公告AI业务营收占比不足0.01%、上半年净利同比−34.46%，题材与基本面严重背离。",
  "end":"Extrapolating one day's optical-module surge into 'the main line is set and will keep rising', ignoring that the 6-board leader Longban Media disclosed AI revenue <0.01% of sales and H1 net profit −34.46% YoY — story and fundamentals diverge badly."},
 {"zh":"过度自信","en":"Overconfidence","sev":3,
  "zhd":"把涨股比57%与涨停90读作「全面转牛」，忽视成交反而缩量−840亿、上证仅+0.07%且仍收于MA20（3935.82）下方、估值分位79.52%仍高。",
  "end":"Reading up-ratio 57% and 90 limit-ups as a full bull turn, ignoring that turnover instead shrank ¥84bn, the SSE added only +0.07% and still closed below MA20 (3935.82), with the valuation pctile at 79.52%."},
 {"zh":"处置效应","en":"Disposition","sev":2,
  "zhd":"卖盈（红利/资源方向在回暖首日被抛售兑现）持亏（前期套牢的光模块在反弹中被视为「回本仓」而继续加杠杆），融资单日前五中光模块占三席即为佐证。",
  "end":"Selling winners (dividend/resources dumped on the first recovery day) while holding losers (trapped optical-module positions treated as 'break-even books' and levered further) — evidenced by optical modules taking 3 of the top-5 daily margin adds."},
 {"zh":"锚定偏差","en":"Anchoring","sev":3,
  "zhd":"锚定 09-02「涨股比 28%」的恐慌低点与创业板前期高位，对 57% 的中性偏暖水平缺乏定价锚，容易在单日 +3.41% 的涨幅中追高。",
  "end":"Anchored to 09-02's panic low (up-ratio 28%) and ChiNext's prior highs, lacking a pricing anchor at the neutral-warm 57% level — prone to chasing after a single +3.41% day."},
 {"zh":"确认偏误","en":"Confirmation Bias","sev":4,
  "zhd":"只看涨停90、创业板+3.41%与主力5日中际旭创+44.39亿的共振，忽略成交缩量−840亿、杠杆与主力双集中于同一赛道、6板龙头基本面已公告不匹配。",
  "end":"Only watching the resonance of 90 limit-ups, ChiNext +3.41% and main-5d Innolight +¥4.44bn, while ignoring the −¥84bn turnover shrink, the double concentration of leverage and main capital in one track, and the 6-board leader's disclosed mismatch."},
 {"zh":"近因偏差","en":"Recency","sev":3,
  "zhd":"外推单日「科技反攻」为持续性反转，对 09-02 恐慌（28%）与 09-03 跌停急升（17）的记忆迅速淡化，忽视回暖需要 2 日以上量价确认。",
  "end":"Extrapolating a single day's 'tech counter-offensive' into a sustained reversal; memories of 09-02 panic (28%) and 09-03's limit-down surge (17) fade fast, ignoring that recovery needs 2+ sessions of volume-price confirmation."},
 {"zh":"叙事偏差","en":"Narrative","sev":4,
  "zhd":"「AI算力 / 光模块景气」叙事被涨停潮与主力5日资金榜强化（中际旭创+44.39亿、新易盛+33.80亿），故事与资金自我实现；但融资前五中光模块占三席，叙事一旦证伪回撤幅度极大。",
  "end":"The 'AI compute / optical-module prosperity' narrative is reinforced by the limit-up wave and the main-5d leaderboard (Innolight +¥4.44bn, XYS +¥3.38bn); story and capital self-reinforce — but with optical modules taking 3 of the top-5 margin adds, the drawdown would be severe if the story is falsified."},
 {"zh":"代表性启发","en":"Representativeness","sev":3,
  "zhd":"被元件 +7.55% 与通信设备 +7.15% 的单日赚钱效应代表整体市场，误判「全面回暖」，忽视保险Ⅱ −3.00% 领跌、红利资源集体退潮与成交缩量的现实。",
  "end":"Components +7.55% and comms equipment +7.15% one-day profit effects taken as representative of the whole market; mistaking it for a broad recovery while ignoring InsuranceⅡ −3.00% leading losers, the dividend/resource retreat and shrinking turnover."},
]
bias_js = "var BIAS = [\n" + ",\n".join(
    "    {zh:\"%s\",en:\"%s\",sev:%d,zhd:\"%s\",end:\"%s\"}" % (esc(b["zh"]), esc(b["en"]), b["sev"], esc(b["zhd"]), esc(b["end"]))
    for b in BIAS) + "\n  ];"
html, _n = re.subn(r'var BIAS = \[.*?\n  \];', bias_js, html, count=1, flags=re.S)
assert _n == 1, "BIAS 替换失败"

# ============================================================
# 3) 静态 body 证据表 + 涨跌分布 SVG 修正
# ============================================================
BODY = [
 ("<span class=\"chip\"><span data-i18n=\"c_upratio\">涨股比</span> <b>46%</b></span>",
  "<span class=\"chip\"><span data-i18n=\"c_upratio\">涨股比</span> <b>57%</b></span>"),
 ("<span class=\"chip\"><span data-i18n=\"c_limitup\">涨停</span> <b>42</b></span>",
  "<span class=\"chip\"><span data-i18n=\"c_limitup\">涨停</span> <b>90</b></span>"),
 ("<span class=\"chip\"><span data-i18n=\"c_turn\">两市成交</span> <b>¥2.03万亿</b></span>",
  "<span class=\"chip\"><span data-i18n=\"c_turn\">两市成交</span> <b>¥1.95万亿</b></span>"),
 ("<text x=\"167\" y=\"33\" fill=\"#fff\" font-size=\"14\" font-weight=\"800\" text-anchor=\"middle\">46%</text>",
  "<text x=\"167\" y=\"33\" fill=\"#fff\" font-size=\"14\" font-weight=\"800\" text-anchor=\"middle\">57%</text>"),
 ("<text x=\"407\" y=\"33\" fill=\"#fff\" font-size=\"14\" font-weight=\"800\" text-anchor=\"middle\">54%</text>",
  "<text x=\"407\" y=\"33\" fill=\"#fff\" font-size=\"14\" font-weight=\"800\" text-anchor=\"middle\">43%</text>"),
 ("<text x=\"340\" y=\"72\" fill=\"#d8392b\">2444</text>",
  "<text x=\"340\" y=\"72\" fill=\"#d8392b\">3167</text>"),
 ("<text x=\"340\" y=\"92\" fill=\"#1a9e5a\">2914</text>",
  "<text x=\"340\" y=\"92\" fill=\"#1a9e5a\">2196</text>"),
 ("<text x=\"340\" y=\"112\" fill=\"#6b675f\">198</text>",
  "<text x=\"340\" y=\"112\" fill=\"#6b675f\">195</text>"),
 ("<text x=\"340\" y=\"138\" fill=\"#d8392b\">42</text>",
  "<text x=\"340\" y=\"138\" fill=\"#d8392b\">90</text>"),
 ("<text x=\"340\" y=\"158\" fill=\"#1a9e5a\">0</text>",
  "<text x=\"340\" y=\"158\" fill=\"#1a9e5a\">1</text>"),
 ("<text x=\"340\" y=\"184\" fill=\"#1c1b19\">¥2.03万亿</text>",
  "<text x=\"340\" y=\"184\" fill=\"#1c1b19\">¥1.95万亿</text>"),
 ("（占 46%，较上一报告日（09-03） +13pct）", "（占 57%，较上一报告日（09-04） +11pct）"),
 ("（占 54%，较上一报告日（09-03） −13pct）", "（占 43%，较上一报告日（09-04） −11pct）"),
 ("（较前日 −4 只，连板高度 5板）", "（较前日 +48 只，连板高度 6板）"),
 ("（较前日 −17 只，跌停清零）", "（较前日 +1 只，跌停近乎清零）"),
 ("（环比 +2700亿，放量修复）", "（环比 −840亿，小幅缩量）"),
 ('<rect x="14" y="14" width="230" height="26" fill="#d8392b"/>',
  '<rect x="14" y="14" width="285" height="26" fill="#d8392b"/>'),
 ('<rect x="244" y="14" width="270" height="26" fill="#1a9e5a"/>',
  '<rect x="299" y="14" width="215" height="26" fill="#1a9e5a"/>'),
 ("<td><span class=\"val up\">46%</span>（涨2444 / 跌2914 / 平198）</td>",
  "<td><span class=\"val up\">57%</span>（涨3167 / 跌2196 / 平195）</td>"),
 ("<td><span class=\"val up\">42</span> / <span class=\"val down\">0</span></td>",
  "<td><span class=\"val up\">90</span> / <span class=\"val down\">1</span></td>"),
 ("<span class=\"val\">¥2.03万亿</span>（较前日 +2700亿，放量修复）",
  "<span class=\"val\">¥1.95万亿</span>（较前日 −840亿，小幅缩量）"),
 ("<td><span class=\"val down\">3930.12　−0.30%</span></td>",
  "<td><span class=\"val up\">3932.70　+0.07%</span></td>"),
 ("<td><span class=\"val down\">13516.97　−0.79%</span></td>",
  "<td><span class=\"val up\">13774.91　+1.91%</span></td>"),
 ("<td><span class=\"val down\">3286.55　−0.78%</span></td>",
  "<td><span class=\"val up\">3398.68　+3.41%</span></td>"),
 ("<span class=\"val up\">航海装备Ⅱ +6.49%</span>（中国船舶 +9.18%）<br>养殖业 +5.30%（罗牛山 +10.05%）/ 饲料 +4.79%（播恩集团 +10.04%）<br>渔业 +3.96%（中水渔业 +9.98%）/ 广告营销 +3.87%（易点天下 +11.12%）/ 房地产服务 +3.85%（我爱我家 +10.14%）",
  "<span class=\"val up\">元件 +7.55%</span>（迅捷兴 +20%）<br>通信设备 +7.15%（太辰光 +14.5%）/ 非金属材料Ⅱ +4.72%（长江材料 +10%）<br>渔业 +4.59%（中水渔业 +9.96%）/ 电子化学品Ⅱ +4.51%（中石科技 +17.39%）/ 种植业 +4.48%（亚盛集团 +10.09%）"),
 ("<span class=\"val down\">玻璃玻纤 −4.86%</span> / 电子化学品Ⅱ −3.86% / 非金属材料Ⅱ −3.35% / 其他电子Ⅱ −3.09% / 能源金属 −2.89% / 小金属 −2.86%",
  "<span class=\"val down\">保险Ⅱ −3.00%</span>（中国人保 −1.75%）/ 贵金属 −2.91%（山金国际 −1.71%）<br>煤炭开采 −2.63% / 厨卫电器 −2.34% / 化学纤维 −1.97% / 国有大型银行Ⅱ −1.88%"),
 ("<span class=\"val up\">连板高度 5 板</span>（龙版传媒，龙头一日一换）<br>2板 6 只：恒盛能源 / 爱仕达 / 海通发展 / 新炬网络 / 亚盛集团 / 百大集团<br>新热点：罗牛山 +10.05%（养殖）/ 播恩集团 +10.04%（饲料）/ 中水渔业 +9.98%（渔业）/ 我爱我家 +10.14%（房地产服务）",
  "<span class=\"val up\">连板高度 6 板</span>（龙版传媒，已公告 AI 营收占比<0.01%）<br>3板 3 只：亚盛集团 / 百大集团 / 爱仕达；2板 9 只：安记食品 / 敦煌种业 / 中水渔业 / 天沃科技 / 播恩集团<br>新热点：迅捷兴 +20%（元件）/ 太辰光 +14.5%（通信设备）/ 中石科技 +17.39%（电子化学品Ⅱ）"),
 ("<span class=\"val up\">龙版传媒 5板</span>（2026-09-04）", "<span class=\"val up\">龙版传媒 6板</span>（2026-09-07）"),
 ("宁德时代 <span class=\"val up\">+3.57亿</span>（电池）<br>中国巨石 +2.86亿（玻纤） / 麦格米特 +2.61亿 / 浪潮信息 +2.23亿 / 紫金矿业 +2.21亿<br>星网锐捷 +2.13亿 / 飞龙股份 +1.93亿 / 方正科技 +1.79亿",
  "天孚通信 <span class=\"val up\">+3.04亿</span>（光模块）<br>新易盛 +1.99亿（光模块） / 我爱我家 +1.85亿 / 剑桥科技 +1.75亿（光模块） / 德科立 +1.48亿<br>协创数据 +1.31亿 / 云铝股份 +1.21亿 / 精智达 +1.15亿"),
 ("宁德时代 <span class=\"val up\">+3.57亿</span>（电池）<br>中国巨石 +2.86亿（玻纤） / 麦格米特 +2.61亿 / 浪潮信息 +2.23亿 / 紫金矿业 +2.21亿<br>星网锐捷 +2.13亿 / 飞龙股份 +1.93亿 / 方正科技 +1.79亿",
  "天孚通信 <span class=\"val up\">+3.04亿</span>（光模块）<br>新易盛 +1.99亿（光模块） / 我爱我家 +1.85亿 / 剑桥科技 +1.75亿（光模块） / 德科立 +1.48亿<br>协创数据 +1.31亿 / 云铝股份 +1.21亿 / 精智达 +1.15亿"),
 ("中国船舶 +9.18%", "中际旭创 +44.39亿"),
 ("龙版传媒 5板（文化传媒，龙头一日一换）<br>罗牛山 +10.05%（养殖）/ 播恩集团 +10.04%（饲料）/ 中水渔业 +9.98%（渔业）<br>我爱我家 +10.14%（房地产服务）/ 易点天下 +11.12%（广告营销）/ 中国船舶 +9.18%（航海装备Ⅱ）",
  "龙版传媒 6板（文化传媒，AI 营收占比<0.01%）<br>迅捷兴 +20%（元件）/ 太辰光 +14.5%（通信设备）/ 中石科技 +17.39%（电子化学品Ⅱ）<br>中水渔业 +9.96%（渔业）/ 亚盛集团 +10.09%（种植业）/ 中国出版 +10.03%（出版）"),
 ("二、核心指数表现（2026-09-04 收盘）", "二、核心指数表现（2026-09-07 收盘）"),
 ("<b>2026-09-04 收盘（北京时间，盘后）</b>", "<b>2026-09-07 收盘（北京时间，盘后）</b>"),
 ("Next-Session Outlook (09-07 Mon)", "Next-Session Outlook (09-08 Tue)"),
]
for old, new in BODY:
    if old in html:
        html = html.replace(old, new, 1)
    else:
        print("[skip-body] 未命中: %r" % old[:46])

# ============================================================
# 4) 雷达数值标签（红字组）
# ============================================================
old_radar = '<text x="160" y="71">52</text><text x="237" y="120">64</text><text x="209" y="194">56</text>\n            <text x="160" y="167">58</text><text x="109" y="201">55</text><text x="55" y="118">87</text>'
new_radar = '<text x="160" y="71">58</text><text x="237" y="120">70</text><text x="209" y="194">54</text>\n            <text x="160" y="167">46</text><text x="109" y="201">62</text><text x="55" y="118">87</text>'
if old_radar in html:
    html = html.replace(old_radar, new_radar, 1)
else:
    print("[skip] radar 块未命中")

# ============================================================
# 5) 用字典值回写所有 data-i18n 兜底文本
# ============================================================
_pat = re.compile(r'<(\w+)([^>]*\bdata-i18n="([^"]+)"[^>]*)>(.*?)</\1>', re.S)


def _repl(m):
    _tag, _attrs, _key, _inner = m.group(1), m.group(2), m.group(3), m.group(4)
    if _key in zh:
        return "<%s%s>%s</%s>" % (_tag, _attrs, zh[_key], _tag)
    return m.group(0)


html = _pat.sub(_repl, html)
for _a, _b in [("2026-09-04 · 收盘", "2026-09-07 · 收盘"), ("2026-09-04 · Close", "2026-09-07 · Close")]:
    html = html.replace(_a, _b)

# ============================================================
# 6) hub（web/psychology/index.html）插入 0907 条目
# ============================================================
HUB = os.path.join(HERE, "..", "web", "psychology", "index.html")
hub = open(HUB, encoding="utf-8").read()
if "crowd-psychology-risk-radar-20260907.html" not in hub:
    entry = """    },
    {
      file:"crowd-psychology-risk-radar-20260907.html", date:"2026-09-07",
      risk:"中", riskEn:"Medium",
      cycleZh:"科技反攻 / 普涨回暖", cycleEn:"Tech counter-offensive / Broad recovery",
      cycleNoteZh:"涨停翻倍·创业板+3.41%", cycleNoteEn:"Limit-up doubles · ChiNext +3.41%",
      up:"57%", limitup:"90", board:"6板", turn:"¥1.95万亿",
      summaryZh:"涨股比46%→57%、涨停42→90翻倍、跌停仅1，创业板+3.41%（3398.68）领涨、深成+1.91%、上证+0.07%；成交¥1.95万亿（环比−840亿，仍为10日均99.5%）。元件+7.55%（迅捷兴+20%）/通信设备+7.15%（太辰光+14.5%）领涨，TMT主线成型；保险Ⅱ−3.00%领跌，贵金属−2.91%/煤炭开采−2.63%/国有大型银行Ⅱ−1.88%红利资源退潮。连板6板（龙版传媒，已公告AI营收占比<0.01%），3板3只、2板9只、首板81只。融资单日天孚通信+3.04亿居首（新易盛+1.99亿、剑桥科技+1.75亿，光模块占前五三席）；主力5日中际旭创+44.39亿第一。估值PE_TTM 20.39（10年分位79.52%）仍偏高——回暖确认但杠杆与主线拥挤，风险等级中。",
      summaryEn:"Up-ratio 46%→57%, limit-up 42→90 (doubled), limit-down just 1; ChiNext +3.41% (3398.68) leads, SZ +1.91%, SSE +0.07%; turnover ¥1.95tn (−¥84bn QoQ, still 99.5% of 10d avg). Components +7.55% (Xunjiexing +20%) / comms equipment +7.15% (T&S +14.5%) lead — the TMT main line forms; InsuranceⅡ −3.00% leads losers, precious metals −2.91% / coal −2.63% / state banksⅡ −1.88% retreat. Ladder 6 boards (Longban Media, AI revenue <0.01% disclosed), 3-board ×3, 2-board ×9, first-board ×81. Daily margin TFC +¥304mn #1 (Innolight +¥199mn, Cambridge +¥175mn — optical modules take 3 of top 5); main-5d Innolight +¥4.44bn #1. Valuation PE_TTM 20.39 (10y pctile 79.52%) still rich — recovery confirmed but leverage and main-line crowding rise; risk Medium.\""""
    tail = "    }\n  ];\n  REPORTS.reverse();"
    assert tail in hub, "hub tail not found"
    # 注意：entry 必须以对象闭合 "    }" 结尾，否则 hub JS 报 SyntaxError（0904 脚本遗留坑）
    hub = hub.replace(tail, entry + "\n    }\n  ];\n  REPORTS.reverse();", 1)
    open(HUB, "w", encoding="utf-8").write(hub)
    print("[ok] hub 已插入 0907 条目")
else:
    print("[skip] hub 已有 0907 条目")

# ============================================================
# 7) 写出 + 校验
# ============================================================
open(OUT, "w", encoding="utf-8").write(html)
print("[ok] 写出 %s (%d bytes)" % (OUT, len(html)))

leftover = ["3930.12", "13516.97", "3286.55", "2444", "2914", "龙版传媒 5板", "¥2.03万亿",
            "玻璃玻纤 −4.86%", "中国巨石 +2.86亿", "宁德时代 +3.57亿", "46</text>", "42</text>"]
bad = [s for s in leftover if s in html]
print("[校验] 残留旧数据:", bad if bad else "无")
