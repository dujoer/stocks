# -*- coding: utf-8 -*-
"""群体心理风险雷达 2026-09-09：以 09-07 页面为模板，覆盖全部动态内容。

数据来源（全部为 2026-09-09 真实收盘）：
  data_market_overview(type=all) / tool_ranking(limitup_days) /
  tool_ranking(margin_chg_d) / tool_ranking(cap_main_5d) / data_sector(ranking) / data_hot
"""
import os, re, shutil

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "..", "web", "psychology", "crowd-psychology-risk-radar-20260907.html")
OUT = os.path.join(HERE, "..", "web", "psychology", "crowd-psychology-risk-radar-20260909.html")

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
# 1) 09-09 叙述覆盖（中文）
# ============================================================
ZH = {
 "t_headline_sub": "2026-09-09 · 收盘",
 "t_breadth": "市场涨跌分布（2026-09-09 收盘）",
 "hk_stage": "阶段定性", "hv_stage": "<b>缩量分化 / 短线退潮</b>（09-09）",
 "hk_upratio": "涨股比", "hv_upratio": "<b>32%</b>（前次 09-07 57% · ↓ 25pct，广度大幅回落）",
 "hk_lim": "涨停 / 跌停", "hv_lim": "<b>42</b> / <b>0</b>（涨停腰斩，跌停清零）",
 "hk_amt": "成交额", "hv_amt": "<b>¥1.86万亿</b>（缩量 −900亿，为 10 日均 94%）",
 "hk_cycle": "情绪周期", "hv_cycle": "<b>缩量分化 / 短线退潮</b>",
 "hk_risk": "风险等级", "hv_risk": "<b class=\"hl-risk\">中</b>（维持）",
 "hk_flag": "关键提示",
 "hv_flag": "涨股比 57%→<b>32%</b>、涨停 90→<b>42</b>、创业板 <b>−0.14%</b> 翻绿——广度与赚钱效应同步退潮；成交缩量 −900亿（10 日均 94%），前期主线光模块虽仍有主力5日净流入（中际旭创 +76.9亿居首），但融资单日转向中际旭创 +5.61亿、兴森科技 +4.92亿、摩尔线程 +4.23亿，杠杆与主力仍高度集中于光模块/PCB，估值 PE_TTM 20.40（10年分位 79.6%）仍偏高",
 "tk1": "阶段定性", "tv1": "A 股 09-09 由 09-07「科技反攻 / 普涨回暖」回落为「<b>缩量分化 / 短线退潮</b>」：涨股比骤降至 <b>32%</b>（1794涨 / 3642跌 / 平124，由 57% 回落 −25pct），涨停 <b>42</b>（90→42，腰斩），跌停 0；上证 <b>+0.28%</b>（3951.51）微涨站上 MA20（3936.39），深成 +0.15%（13723.32），但创业板 <b>−0.14%</b>（3354.97）翻绿——指数红而个股绿，涨指数不涨个股。成交 ¥1.86万亿（环比 <b>−900亿</b>，10 日均 94%）明显缩量。风险等级维持<b>中</b>。",
 "tk2": "广度大幅退潮", "tv2": "涨股比 <b>32%</b>（前次 57% ↓ 25pct）· 涨停 <b>42</b>（90→42 腰斩）· 跌停 <b>0</b>（清零）· 成交 <b>¥1.86万亿</b>（缩量 −900亿，10 日均 94%）——赚钱效应与参与度同步回落，指数与个股背离重新放大（涨指数跌个股）。",
 "tk3": "指数虚红", "tv3": "上证 <b>+0.28%</b>（3951.51）微涨、收站 MA20（3936.39）上方，深成 <b>+0.15%</b>（13723.32），但创业板 <b>−0.14%</b>（3354.97）翻绿——权重托指数、个股普跌；MACD 红柱 2.13（DIF 7.37 > DEA 6.31 金叉延续），RSI_12 54.14 中性偏强。",
 "tk4": "板块结构", "tv4": "<b>橡胶 +4.07%</b>（黑猫股份 +10%）与 <b>航运港口 +3.86%</b>（南京港 +10.03%）领涨，非金属材料Ⅱ +3.51% / 渔业 +3.29%（中水渔业 +9.98%）/ 煤炭开采 +3.04%（郑州煤电 +10.04%）/ 农产品加工 +2.98% / 地面兵装Ⅱ +2.37% 跟随——<b>主线切换至橡胶/航运/资源，TMT 热度明显降温</b>；<b>数字媒体 −4.12%</b>（风语筑 +2.30%）领跌，房地产服务 −3.79% / 出版 −3.45% / 游戏Ⅱ −2.82%（迅游科技 −0.30%）/ 广告营销 −2.70% / 电视广播 −2.35%——前期 AI 应用/传媒方向集体退潮。",
 "tk5": "连板结构", "tv5": "连板高度回落至 <b>5 板</b>（百大集团，由 6 板降级）；3板 4 只（中百集团 / 金正大 / 华脉科技 / 桂林旅游）、2板 9 只（云煤能源 / 泸天化 / 黑猫股份 / 中粮科技 / 红棉股份 / 华康股份 / 精华制药 / 精艺股份 / 众泰汽车）、首板 35 只（共 49 只）——<b>高度下降、题材由 TMT 切换至消费/资源/旅游</b>。",
 "tk6": "杠杆与主力仍集中于光模块", "tv6": "融资单日加仓榜 <b>中际旭创 +5.61亿 居首</b>，兴森科技 +4.92亿、摩尔线程 +4.23亿、飞龙股份 +2.90亿、药明康德 +2.84亿、宁德时代 +2.42亿、中国平安 +2.19亿——<b>杠杆仍偏向光模块（中际旭创/兴森科技）及新题材摩尔线程</b>；主力5日净流入中际旭创 +76.9亿、新易盛 +41.0亿、东山精密 +31.3亿、天孚通信 +25.5亿、工业富联 +24.4亿仍居前——<b>光模块/PCB 定价权未散，但短线个股已退潮，资金陷入「看多主线、做多分化」</b>。",
 "tk7": "估值 / 风格", "tv7": "PE_TTM <b>20.40</b>（10年分位 <b>79.6%</b> 仍偏高）+ 估值口径 09-08；风格 20 日口径<b>价值占优延续</b>，当日红利资源（煤炭 +3.04%）与消费（中百/桂林旅游）接力，成长（创业板 −0.14%）转弱——属高位轮动而非趋势反转，估值分位仍高。",
 "tk8": "情绪周期", "tv8": "由 09-07「科技反攻 / 普涨回暖」转入「<b>缩量分化 / 短线退潮</b>」：涨股比 57%→32%、涨停 90→42 腰斩、创业板 −0.14% 翻绿，广度与赚钱效应同步退潮；但成交缩量 −900亿、杠杆与主力仍集中于光模块/PCB、估值分位 79.6% 仍高、指数虚红（涨指数跌个股）——<b>退潮确认但非系统性恐慌，风险等级维持中</b>。",
 "t_tldr_text": "A股 09-09 呈现「缩量分化 / 短线退潮」：涨股比 57%→32%（1794涨/3642跌/平124），涨停 90→42 腰斩，跌停 0，创业板 −0.14%（3354.97）翻绿、深成 +0.15%、上证 +0.28%（3951.51，站上MA20 3936.39）；成交 ¥1.86万亿（环比 −900亿，为 10 日均 94%）。橡胶 +4.07%（黑猫股份 +10%）/ 航运港口 +3.86%（南京港 +10.03%）领涨，非金属材料Ⅱ +3.51% / 渔业 +3.29%（中水渔业 +9.98%）/ 煤炭开采 +3.04%（郑州煤电 +10.04%）/ 农产品加工 +2.98% 跟随，主线切换至橡胶/航运/资源；数字媒体 −4.12% 领跌，房地产服务 −3.79% / 出版 −3.45% / 游戏Ⅱ −2.82% / 广告营销 −2.70% 前期 AI 应用传媒退潮。连板高度 5板（百大集团），3板 4 只、2板 9 只、首板 35 只。资金信号：融资单日中际旭创 +5.61亿居首（兴森科技 +4.92亿、摩尔线程 +4.23亿），主力5日中际旭创 +76.9亿第一、新易盛 +41.0亿、东山精密 +31.3亿。估值 PE_TTM 20.40（10年分位 79.6%）仍偏高——退潮确认但非系统性恐慌，风险等级中。",
 "t_cycle_note": "注：上方「中性偏冷」为实时群体心理定位（缩量分化 / 短线退潮）——09-09 涨跌分布（涨股比 32%、涨停 42、跌停 0、成交 ¥1.86万亿）显示广度大幅回落、赚钱效应退潮、指数虚红（涨指数跌个股）；但成交缩量、杠杆与主力仍集中于光模块/PCB、估值分位 79.6% 仍高。若 09-10 涨股比回升至 40% 上方且成交回到 ¥1.95万亿，退潮缓和；若光模块主线继续分化且涨停跌破 30，则短线情绪进一步降温。",
 "t_radar_note": "六维风险读数（0–100，由下方真实数据综合映射，越高代表该维度群体脆弱性越强）：拥挤度 60 / 融资 64 / 换手 50 / 广度 62 / 媒体 52 / 估值 87。广度由 46 升至 62（09-09 涨股比骤降至 32%、跌停清零，参与度实质恶化，广度风险回升）；换手由 54 降至 50（成交 ¥1.86万亿，10 日均 94%，量能明显回落）；融资由 70 降至 64（单日加仓前五仍含光模块中际旭创 +5.61亿、兴森科技 +4.92亿，但杠杆方向部分转向摩尔线程等新题材，集中度边际缓和）；拥挤度由 58 升至 60（主线由光模块/PCB 收敛，但橡胶/航运/资源接力，赚钱效应分散）；媒体由 62 降至 52（涨停 42、5 板高度、创业板翻绿，情绪温度回落）；估值 87 持平（PE_TTM 20.40、10年分位 79.6%，口径 09-08）。整体脆弱性由「融资+拥挤+媒体」转向「广度+估值」——退潮确认，广度恶化成为主要风险源。",
 "t_breadth_note": "涨股比由 57% 骤降至 32%、涨停 90→42 腰斩、跌停维持 0 只；成交 ¥1.86万亿环比 −900亿（缩量，10 日均 94%）。指数虚红：创业板 −0.14% / 深成 +0.15% / 上证 +0.28%（3951.51 站上 MA20 3936.39），上证收 3951.51 创阶段新高但个股普跌；橡胶 +4.07% / 航运港口 +3.86% 领涨，数字媒体 −4.12% / 房地产服务 −3.79% 领跌——主线切换、TMT 退潮。",
 "ev_upratio_i": "由 57% 降至 32%（−25pct），涨 1794 / 跌 3642 / 平 124，参与度大幅回落，个股普跌但跌停清零显示非恐慌性杀跌",
 "ev_limit_i": "涨停 42（90→42 腰斩）、跌停 0，连板高度降至 5板（百大集团）——投机热度明显降温，赚钱效应收缩",
 "ev_amount_i": "量能 ¥1.86万亿（环比 −900亿，10 日均的 94%），明显缩量——退潮由存量资金收缩与主线分歧驱动",
 "ev_sh_i": "微涨 +0.28%（3951.51），站上 MA20 3936.39 上方，MACD 红柱 2.13（DIF 7.37 > DEA 6.31 金叉延续），RSI_12 54.14 中性偏强，PE_TTM 20.40（10年分位 79.6% 偏高）",
 "ev_sz_i": "深成 +0.15%（13723.32），跟随上证微红，中期弱势边际平稳",
 "ev_cyb_i": "创业板 −0.14%（3354.97）翻绿，成长风格退潮，与 09-07 的 +3.41% 形成强烈反差",
 "ev_secup_i": "橡胶 +4.07%（黑猫股份 +10%）/ 航运港口 +3.86%（南京港 +10.03%）领涨，非金属材料Ⅱ +3.51% / 渔业 +3.29%（中水渔业 +9.98%）/ 煤炭开采 +3.04%（郑州煤电 +10.04%）/ 农产品加工 +2.98% / 地面兵装Ⅱ +2.37%——主线由 TMT 切换至橡胶/航运/资源",
 "ev_secdn_i": "数字媒体 −4.12%（风语筑 +2.30%）领跌 / 房地产服务 −3.79% / 出版 −3.45% / 游戏Ⅱ −2.82%（迅游科技 −0.30%）/ 广告营销 −2.70% / 电视广播 −2.35%——前期 AI 应用与传媒方向集体退潮",
 "ev_board_i": "连板 5板（百大集团），3板 4 只（中百集团 / 金正大 / 华脉科技 / 桂林旅游），2板 9 只（云煤能源 / 泸天化 / 黑猫股份 / 中粮科技 / 红棉股份 / 华康股份 / 精华制药 / 精艺股份 / 众泰汽车），首板 35 只；热点由 TMT 切换至消费（中百/桂林旅游）/ 资源（黑猫/郑州煤电）/ 航运（南京港）",
 "ev_height_i": "高度 5板（百大集团，2026-09-09 收盘），由 6 板降级；题材由百货零售接力，基本面以区域百货为主，无显著题材泡沫",
 "ev_main": "主力5日净流入TOP",
 "ev_main_i": "主力5日净流入仍集中于光模块 / PCB：中际旭创 +76.9亿 居首、新易盛 +41.0亿、东山精密 +31.3亿、天孚通信 +25.5亿、工业富联 +24.4亿、摩尔线程 +21.0亿、华工科技 +19.5亿、三环集团 +18.6亿、德科立 +17.4亿、紫金矿业 +14.9亿——光模块/PCB 定价权未散，但短线个股已退潮",
 "ev_margin": "融资单日变动TOP",
 "ev_margin_i": "融资单日加仓榜中际旭创居首（+5.61亿），兴森科技 +4.92亿、摩尔线程 +4.23亿、飞龙股份 +2.90亿、药明康德 +2.84亿、宁德时代 +2.42亿、中国平安 +2.19亿、天通股份 +1.94亿、剑桥科技 +1.92亿、西部矿业 +1.65亿——杠杆仍偏向光模块（中际旭创/兴森科技）及新题材摩尔线程",
 "ev_hot_i": "热点由消费/资源主导：百大集团 5板（百货零售）/ 黑猫股份 +10%（橡胶）/ 南京港 +10.03%（航运港口）/ 郑州煤电 +10.04%（煤炭开采）/ 中水渔业 +9.98%（渔业）/ 中百集团 3板（一般零售）/ 桂林旅游 3板（旅游）；data_hot 板块榜首位为电力、电脑硬件、航运港口，与主力资金部分一致但 TMT 降温",
 "ev_margintotal_i": "缺口：聚合两融余额（data_market_overview type=margin）返回空，以个股融资变动替代观察（见上）；连板高度 / 融资单日 / 主力5日均为 2026-09-09 真实数据",
 "t_ev_note": "数据口径：宏观指标多截至 2026-07（月频）或 2026-09-09（日频）；涨跌分布 / 指数 / 成交额 / 板块 / 融资单日 / 主力5日 / 连板梯队均为 2026-09-09 真实收盘。估值 PE_TTM 20.40 为 2026-09-08 口径（中证全指估值滞后发布），已在正文标注。详见末尾「数据来源与日期口径」。",
 "rc1_tag": "红线区 · 光模块杠杆与主力双集中 + 高估值",
 "rc1_t": "光模块杠杆与主力双集中 + 高估值",
 "rc1_d": "融资单日中际旭创 +5.61亿、兴森科技 +4.92亿，主力5日前十中中际旭创 +76.9亿、新易盛 +41.0亿、东山精密 +31.3亿仍居前——杠杆与主力定价权仍集中于光模块/PCB，但短线个股已退潮（涨停腰斩、创业板翻绿），一旦证伪回撤幅度大；叠加 PE_TTM 20.40、10年分位 79.6% 仍偏高。",
 "rc1_rep": "代表：光模块（中际旭创 / 新易盛 / 天孚通信）/ PCB（兴森科技 / 东山精密）/ 高位连板（百大集团）",
 "rc2_tag": "黄线区 · 指数虚红下的个股普跌（涨指数跌个股）",
 "rc2_t": "指数虚红 / 个股普跌",
 "rc2_d": "上证 +0.28% 站上 MA20、深成微红，但创业板 −0.14% 翻绿、涨股比仅 32%、涨停腰斩——指数被权重托住而个股普跌，量价与广度背离；成交缩量 −900亿至 ¥1.86万亿（10 日均 94%），存量资金收缩。",
 "rc2_rep": "代表：上证权重（托指数）/ 创业板（翻绿）/ 中小票（普跌）",
 "rc3_tag": "绿线区 · 前期 AI 应用/传媒退潮（相对）",
 "rc3_t": "AI 应用 / 传媒方向退潮",
 "rc3_d": "数字媒体 −4.12%（风语筑 +2.30%）领跌，房地产服务 −3.79% / 出版 −3.45% / 游戏Ⅱ −2.82%（迅游科技 −0.30%）/ 广告营销 −2.70% / 电视广播 −2.35%——前期 AI 应用与传媒方向在退潮期被抛售，属题材轮动而非基本面恶化，但提示高位题材风险。",
 "rc3_rep": "代表：数字媒体（风语筑）/ 出版（中国出版）/ 游戏Ⅱ（迅游科技）",
 "t_sec_outlook": "下个交易日（09-10 周四）展望",
 "o_logic": "研判逻辑（基于 09-09 收盘 + 群体心理定位）",
 "o_logic_text": "由 09-09 的「缩量分化 / 短线退潮」延伸：情绪周期定位「缩量分化 / 短线退潮」，涨股比 32%、涨停 42、跌停 0、创业板 −0.14% 翻绿，广度与赚钱效应同步退潮；但成交缩量 −900亿、杠杆与主力仍集中于光模块/PCB、估值分位 79.6% 仍高、指数虚红（涨指数跌个股）。基于此推演 09-10 的板块方向与交易规则（<b>不涉及具体个股推荐</b>）。",
 "o1_tag": "光模块 / PCB（观察）",
 "o1_t": "通信设备 / 元件 / 电子化学品Ⅱ",
 "o1_d": "主力5日中际旭创 +76.9亿、新易盛 +41.0亿仍居前，融资单日中际旭创 +5.61亿、兴森科技 +4.92亿——价格与资金中长期共振仍在，但 09-09 短线个股已退潮（涨停腰斩、创业板翻绿）。",
 "o1_cond": "注意：杠杆与主力双集中 = 拥挤度高，短线退潮期忌追高；若龙头继续分化或涨停家数跌破 30，视为情绪进一步降温，只做回踩不追突破。",
 "o2_tag": "消费 / 资源接力（观望）",
 "o2_t": "橡胶 / 航运港口 / 煤炭开采 / 百货零售",
 "o2_d": "09-09 橡胶 +4.07%（黑猫股份 +10%）/ 航运港口 +3.86%（南京港 +10.03%）/ 煤炭开采 +3.04%（郑州煤电 +10.04%）/ 百货零售（百大集团 5板、中百集团 3板）接力领涨，属退潮期的高低切换与题材轮动。",
 "o2_cond": "注意：接力方向多为事件/低价驱动，持续性待验证；成交若继续缩量，轮动加快、操作难度上升，不追后排、只做前排核心。",
 "o3_tag": "前期 AI 应用 / 传媒退潮（回避）",
 "o3_t": "数字媒体 / 出版 / 游戏Ⅱ / 广告营销",
 "o3_d": "09-09 数字媒体 −4.12% 领跌、房地产服务 −3.79% / 出版 −3.45% / 游戏Ⅱ −2.82% / 广告营销 −2.70% 集体退潮——前期 AI 应用与传媒方向在退潮期被抛售，短期承压。",
 "o3_cond": "注意：属题材轮动而非基本面恶化，不盲目杀跌；但退潮期回避高位题材，等待缩量止跌信号。",
 "o_r1": "<b>仓位</b>：中性偏谨慎（4–5 成），不加杠杆。情绪由「科技反攻 / 普涨回暖」回落「缩量分化 / 短线退潮」，风险等级维持中，退潮期控制仓位、不追高。",
 "o_r2": "<b>量价确认</b>：涨股比回升至 40% 上方且成交回到 ¥1.95万亿，方视为退潮缓和；若成交继续缩量至 ¥1.8万亿以下或涨停跌破 30，降仓至 ≤3 成。",
 "o_r3": "<b>主线参与</b>：光模块 / PCB 退潮期只做回踩不追高，重点看龙头是否止跌；消费/资源接力方向只做前排核心，不追后排轮动。",
 "o_r4": "<b>回避清单</b>：前期高位 AI 应用/传媒题材（数字媒体/出版/游戏）、杠杆与主力双集中且已退潮的光模块后排个股追高、退潮期高位连板接力。",
 "o_r5": "<b>风控</b>：若 09-10 光模块主线继续分化且涨停家数跌破 30，视为短线情绪进一步降温，立即降仓；上证跌破 MA20（3936.39）则转防守。",
 "s_breadth_v": "westock · data_market_overview(market_statis_updown)；2026-09-09 收盘",
 "s_portrait_v": "westock · data_market_overview(type=summary)；2026-09-09（涨股比 32% 广度退潮，缩量分化）",
 "s_index_v": "westock · data_market_overview(market_statis_daily_trade)；2026-09-09 收盘",
 "s_sector_v": "westock · data_sector(mode=ranking, kind=industry/concept)；2026-09-09",
 "s_hot_v": "westock · data_hot(kind=board)；2026-09-09（电力 / 电脑硬件 / 航运港口 居前）",
 "s_margin_v": "westock · tool_ranking(metric=margin_chg_d)；2026-09-09",
 "s_main_v": "westock · tool_ranking(metric=cap_main_5d)；2026-09-09（中际旭创 +76.9亿 居首）",
 "s_board_v": "westock · tool_ranking(metric=limitup_days)；2026-09-09（当日排行榜已刷新，共 49 只）",
 "s_gap_v": "市场两融余额聚合值（data_market_overview type=margin）数据源返回空，已用个股融资变动替代，未编造；估值 PE_TTM 20.40 为 2026-09-08 口径（中证全指估值滞后发布），已标注。",
 "t_src_note": "时间口径：所有时点按北京时间。宏观为月频 / 季频，与日频行情不可直接对齐，已分别标注。涨跌分布 / 指数 / 板块 / 融资单日 / 主力5日 / 连板梯队均为 2026-09-09 当日真实数据；估值为 2026-09-08 口径。",
 "ev_index": "二、核心指数表现（2026-09-09 收盘）",
 "o_rules_t": "交易规则（09-10）",
 "o_compliance": "<b>合规说明：</b>本展望仅给出板块方向与交易规则，不涉及具体个股推荐；群体心理定位与板块推断基于 2026-09-09 真实行情数据，市场有风险，决策须独立。",
 "t_risk_hi": "中",
}

EN = {
 "t_headline_sub": "2026-09-09 · Close",
 "t_breadth": "Market breadth (2026-09-09 close)",
 "hk_stage": "Stage", "hv_stage": "<b>Volume-shrinking divergence / Short-term ebb</b> (09-09)",
 "hk_upratio": "Up-ratio", "hv_upratio": "<b>32%</b> (prev 09-07 57% · ↓ 25pct, breadth falls sharply)",
 "hk_lim": "Limit-up / -down", "hv_lim": "<b>42</b> / <b>0</b> (limit-up halved, limit-down cleared)",
 "hk_amt": "Turnover", "hv_amt": "<b>¥1.86tn</b> (−¥90bn, 94% of 10d avg)",
 "hk_cycle": "Sentiment cycle", "hv_cycle": "<b>Volume-shrinking divergence / Short-term ebb</b>",
 "hk_risk": "Risk level", "hv_risk": "<b class=\"hl-risk\">Medium</b> (unchanged)",
 "hk_flag": "Key flag",
 "hv_flag": "Up-ratio 57%→<b>32%</b>, limit-up 90→<b>42</b>, ChiNext <b>−0.14%</b> turns red — breadth and profit effect ebb together; turnover shrinks −¥90bn (94% of 10d avg), and though the former main line optical modules still show main-5d net inflow (Innolight +¥7.69bn #1), daily margin rotates to Innolight +¥561mn, Xingsen +¥492mn, Moore Thread +¥423mn — leverage and main capital still cluster in optical modules / PCB; valuation PE_TTM 20.40 (10y pctile 79.6%) still rich",
 "tk1": "Stage", "tv1": "A-shares 09-09 retreat from 09-07's \"tech counter-offensive / broad recovery\" into \"<b>volume-shrinking divergence / short-term ebb</b>\": up-ratio plunges to <b>32%</b> (1794 up / 3642 down / 124 flat, −25pct from 57%), limit-up <b>42</b> (90→42, halved), limit-down 0; SSE <b>+0.28%</b> (3951.51) rises slightly above MA20 (3936.39), SZ +0.15% (13723.32), but ChiNext <b>−0.14%</b> (3354.97) turns red — indices green while stocks red, up-index not up-stocks. Turnover ¥1.86tn (−<b>¥90bn</b> QoQ, 94% of 10d avg) shrinks visibly. Risk level stays <b>Medium</b>.",
 "tk2": "Breadth ebbs", "tv2": "Up-ratio <b>32%</b> (prev 57%, ↓25pct) · limit-up <b>42</b> (90→42 halved) · limit-down <b>0</b> (cleared) · turnover <b>¥1.86tn</b> (shrink −¥90bn, 94% of 10d avg) — profit effect and participation fall together; the index/stock divergence widens again (up-index, down-stocks).",
 "tk3": "Indices fake-red", "tv3": "SSE <b>+0.28%</b> (3951.51) ticks up, closing above MA20 (3936.39); SZ <b>+0.15%</b> (13723.32); but ChiNext <b>−0.14%</b> (3354.97) turns red — weights prop the index while stocks fall broadly; MACD bar 2.13 (DIF 7.37 > DEA 6.31, golden cross continues), RSI_12 54.14 neutral-to-strong.",
 "tk4": "Sector structure", "tv4": "<b>Rubber +4.07%</b> (Black Cat +10%) and <b>shipping ports +3.86%</b> (Nanjing Port +10.03%) lead; Non-metal MaterialsⅡ +3.51% / Fisheries +3.29% (Zhongshui +9.98%) / Coal Mining +3.04% (Zhengzhou Coal +10.04%) / Farm Product Processing +2.98% / Ground ArmamentⅡ +2.37% follow — <b>the main line rotates to rubber / shipping / resources, TMT heat cools markedly</b>; <b>Digital Media −4.12%</b> (Fengyuzhu +2.30%) leads losers, Real-estate Services −3.79% / Publishing −3.45% / GamesⅡ −2.82% (Xunyou −0.30%) / Ad Marketing −2.70% / TV Broadcasting −2.35% — former AI-application / media names retreat together.",
 "tk5": "Limit-up ladder", "tv5": "Ladder height falls to <b>5 boards</b> (Baida Group, down from 6); 3-board ×4 (Zhongbai / Jinzhengda / Huamai / Guilin Tourism), 2-board ×9 (Yunmei / Lutianhua / Black Cat / COFCO Tech / Redcotton / Huakang / Jinghua / Jingyi / Zhongtai), first-board ×35 (49 total) — <b>height drops, themes rotate from TMT to consumer / resources / tourism</b>.",
 "tk6": "Leverage & main capital still in optical modules", "tv6": "Daily margin add: <b>Innolight +¥561mn #1</b>, Xingsen +¥492mn, Moore Thread +¥423mn, Feilong +¥290mn, WuXi AppTec +¥284mn, CATL +¥242mn, Ping An +¥219mn — <b>leverage still leans to optical modules (Innolight / Xingsen) and the new theme Moore Thread</b>; main-5d net inflow still led by Innolight +¥7.69bn, XYS +¥4.10bn, Dongshan +¥3.13bn, TFC +¥2.55bn, Foxconn Industrial +¥2.44bn — <b>optical-module / PCB pricing power intact, but short-term stocks have ebbed; capital is 'bullish the main line, trading the divergence'</b>.",
 "tk7": "Valuation / style", "tv7": "PE_TTM <b>20.40</b> (10y pctile <b>79.6%</b>, still rich) + valuation as of 09-08; on a 20d view <b>value still leads</b>, with dividends/resources (coal +3.04%) and consumer (Zhongbai / Guilin) taking over while growth (ChiNext −0.14%) weakens — a high-level rotation, not a trend reversal; valuation pctile stays high.",
 "tk8": "Sentiment cycle", "tv8": "From 09-07's \"tech counter-offensive / broad recovery\" into \"<b>volume-shrinking divergence / short-term ebb</b>\": up-ratio 57%→32%, limit-up 90→42 halved, ChiNext −0.14% red — breadth and profit effect ebb together; yet turnover shrinks −¥90bn, leverage and main capital still cluster in optical modules/PCB, valuation pctile 79.6% stays rich, and indices are fake-red (up-index, down-stocks) — <b>ebb confirmed but not a systemic panic; risk stays Medium</b>.",
 "t_tldr_text": "A-shares 09-09 = \"volume-shrinking divergence / short-term ebb\": up-ratio 57%→32% (1794 up / 3642 down / 124 flat), limit-up 90→42 (halved), limit-down 0; ChiNext −0.14% (3354.97) turns red, SZ +0.15%, SSE +0.28% (3951.51, above MA20 3936.39); turnover ¥1.86tn (−¥90bn QoQ, 94% of 10d avg). Rubber +4.07% (Black Cat +10%) / shipping ports +3.86% (Nanjing Port +10.03%) lead; Non-metal MaterialsⅡ +3.51% / Fisheries +3.29% (Zhongshui +9.98%) / Coal Mining +3.04% (Zhengzhou Coal +10.04%) / Farm Product Processing +2.98% follow — the main line rotates to rubber/shipping/resources; Digital Media −4.12% leads losers, Real-estate Services −3.79% / Publishing −3.45% / GamesⅡ −2.82% / Ad Marketing −2.70% retreat. Ladder height 5 boards (Baida Group), 3-board ×4, 2-board ×9, first-board ×35. Capital: daily margin Innolight +¥561mn #1 (Xingsen +¥492mn, Moore Thread +¥423mn); main-5d Innolight +¥7.69bn #1, XYS +¥4.10bn, Dongshan +¥3.13bn. Valuation PE_TTM 20.40 (10y pctile 79.6%) still rich — ebb confirmed but no systemic panic; risk Medium.",
 "t_cycle_note": "Note: the \"neutral-to-cool\" tag above is the live crowd-psychology position (volume-shrinking divergence / short-term ebb) — 09-09 breadth (up-ratio 32%, limit-up 42, limit-down 0, turnover ¥1.86tn) shows breadth falling sharply, profit effect ebbing, indices fake-red (up-index, down-stocks); yet turnover shrinks, leverage and main capital cluster in optical modules/PCB, valuation pctile 79.6% remains rich. If 09-10 holds up-ratio above 40% and turnover returns to ¥1.95tn, the ebb eases; if the optical-module line keeps diverging and limit-ups fall below 30, short-term sentiment cools further.",
 "t_radar_note": "Six-dimension risk readings (0–100, mapped from the real data below; higher = greater crowd fragility on that axis): crowding 60 / margin 64 / turnover 50 / breadth 62 / media 52 / valuation 87. Breadth 46→62 (up-ratio plunges to 32%, limit-down cleared, participation worsens materially, breadth risk rises); turnover 54→50 (¥1.86tn, 94% of 10d avg, volume eases visibly); margin 70→64 (top-5 daily adds still include optical-module Innolight +¥561mn / Xingsen +¥492mn, but leverage partially rotates to new themes like Moore Thread, concentration eases marginally); crowding 58→60 (the main line narrows from optical modules/PCB, yet rubber/shipping/resources take over, profit effect disperses); media 62→52 (limit-up 42, 5-board height, ChiNext red, sentiment cools); valuation 87 flat (PE_TTM 20.40, 10y pctile 79.6%, as of 09-08). Fragility shifts from \"margin + crowding + media\" to \"breadth + valuation\" — ebb confirmed, breadth deterioration becomes the main risk source.",
 "t_breadth_note": "Up-ratio plunges 57%→32%, limit-up 90→42 halved, limit-down stays 0; turnover ¥1.86tn, −¥90bn QoQ (shrinks, 94% of 10d avg). Indices fake-red: ChiNext −0.14% / SZ +0.15% / SSE +0.28% (3951.51 above MA20 3936.39) — SSE closes at 3951.51 a new phase high yet stocks fall broadly; Rubber +4.07% / shipping ports +3.86% lead, Digital Media −4.12% / Real-estate Services −3.79% lag — main line rotates, TMT retreats.",
 "ev_upratio_i": "57%→32% (−25pct), 1794 up / 3642 down / 124 flat; participation falls sharply, stocks fall broadly yet limit-down cleared shows no panic selling",
 "ev_limit_i": "Limit-up 42 (90→42 halved), limit-down 0, ladder height down to 5 boards (Baida Group) — speculative heat cools, profit effect contracts",
 "ev_amount_i": "Turnover ¥1.86tn (−¥90bn QoQ, 94% of 10d avg) — visible shrink; the ebb is driven by contracting existing capital and main-line divergence",
 "ev_sh_i": "+0.28% (3951.51), closing above MA20 3936.39; MACD bar 2.13 (DIF 7.37 > DEA 6.31, golden cross continues), RSI_12 54.14 neutral-to-strong, PE_TTM 20.40 (10y pctile 79.6%, rich)",
 "ev_sz_i": "SZ Component +0.15% (13723.32), following SSE mildly green; the medium-term downtrend improves marginally",
 "ev_cyb_i": "ChiNext −0.14% (3354.97) turns red; growth style ebbs, a sharp contrast to 09-07's +3.41%",
 "ev_secup_i": "Rubber +4.07% (Black Cat +10%) / shipping ports +3.86% (Nanjing Port +10.03%) lead; Non-metal MaterialsⅡ +3.51% / Fisheries +3.29% (Zhongshui +9.98%) / Coal Mining +3.04% (Zhengzhou Coal +10.04%) / Farm Product Processing +2.98% / Ground ArmamentⅡ +2.37% — main line rotates from TMT to rubber/shipping/resources",
 "ev_secdn_i": "Digital Media −4.12% (Fengyuzhu +2.30%) leads losers / Real-estate Services −3.79% / Publishing −3.45% / GamesⅡ −2.82% (Xunyou −0.30%) / Ad Marketing −2.70% / TV Broadcasting −2.35% — former AI-application and media names retreat together",
 "ev_board_i": "Ladder 5 boards (Baida Group), 3-board ×4 (Zhongbai / Jinzhengda / Huamai / Guilin Tourism), 2-board ×9 (Yunmei / Lutianhua / Black Cat / COFCO Tech / Redcotton / Huakang / Jinghua / Jingyi / Zhongtai), first-board ×35; hotspots rotate from TMT to consumer (Zhongbai / Guilin) / resources (Black Cat / Zhengzhou Coal) / shipping (Nanjing Port)",
 "ev_height_i": "Height 5 boards (Baida Group, 2026-09-09 close), down from 6; the theme is taken over by department-store retail, fundamentals are regional retail, no notable narrative bubble",
 "ev_main": "Main capital 5d net inflow TOP",
 "ev_main_i": "Main-5d net inflow still concentrates in optical modules / PCB: Innolight +¥7.69bn #1, XYS +¥4.10bn, Dongshan +¥3.13bn, TFC +¥2.55bn, Foxconn Industrial +¥2.44bn, Moore Thread +¥2.10bn, HG Tech +¥1.95bn, Three Rings +¥1.86bn, Dekel +¥1.74bn, Zijin +¥1.49bn — optical-module / PCB pricing power intact, but short-term stocks have ebbed",
 "ev_margin": "Daily margin change TOP",
 "ev_margin_i": "Daily margin adds: Innolight #1 (+¥561mn), Xingsen +¥492mn, Moore Thread +¥423mn, Feilong +¥290mn, WuXi AppTec +¥284mn, CATL +¥242mn, Ping An +¥219mn, Tiantong +¥194mn, Cambridge +¥192mn, Western Mining +¥165mn — leverage still leans to optical modules (Innolight / Xingsen) and the new theme Moore Thread",
 "ev_hot_i": "Hotspots led by consumer / resources: Baida Group 5 boards (department store) / Black Cat +10% (rubber) / Nanjing Port +10.03% (shipping ports) / Zhengzhou Coal +10.04% (coal mining) / Zhongshui +9.98% (fisheries) / Zhongbai 3 boards (general retail) / Guilin Tourism 3 boards — data_hot board ranking leads with Power, Computer Hardware, Shipping Ports, partly consistent with main capital but TMT cools",
 "ev_margintotal_i": "Gap: aggregate margin balance (data_market_overview type=margin) returns empty, substituted with per-stock margin changes (see above); ladder height / daily margin / main-5d are all real 2026-09-09 data",
 "t_ev_note": "Data basis: macro indicators are monthly (mostly to 2026-07) or daily (to 2026-09-09); breadth / indices / turnover / sectors / daily margin / main-5d / ladder are all real 2026-09-09 closes. Valuation PE_TTM 20.40 is as of 2026-09-08 (CSI All-Share valuation published with a lag) and is flagged in the text. See \"Sources and date basis\" at the end.",
 "rc1_tag": "Red zone · Optical-module leverage & main-capital double concentration + rich valuation",
 "rc1_t": "Optical-module double concentration + rich valuation",
 "rc1_d": "Daily margin Innolight +¥561mn, Xingsen +¥492mn, and main-5d top-10 still led by Innolight +¥7.69bn, XYS +¥4.10bn, Dongshan +¥3.13bn — leverage and main-capital pricing power still concentrate in optical modules/PCB, yet short-term stocks have ebbed (limit-up halved, ChiNext red); a falsification would mean a deep drawdown; plus PE_TTM 20.40 at a 79.6% 10y pctile.",
 "rc1_rep": "Represented by: optical modules (Innolight / XYS / TFC) / PCB (Xingsen / Dongshan) / high ladder (Baida Group)",
 "rc2_tag": "Amber zone · Stocks fall under fake-red indices (up-index, down-stocks)",
 "rc2_t": "Fake-red indices / broad stock decline",
 "rc2_d": "SSE +0.28% above MA20 and SZ mildly green, yet ChiNext −0.14% red, up-ratio only 32%, limit-up halved — indices propped by weights while stocks fall broadly, a volume-price and breadth divergence; turnover shrinks −¥90bn to ¥1.86tn (94% of 10d avg), existing capital contracts.",
 "rc2_rep": "Represented by: SSE weights (prop indices) / ChiNext (red) / small-mid stocks (broad decline)",
 "rc3_tag": "Green zone · Former AI-application / media retreat (relative)",
 "rc3_t": "AI-application / media retreat",
 "rc3_d": "Digital Media −4.12% (Fengyuzhu +2.30%) leads losers, Real-estate Services −3.79% / Publishing −3.45% / GamesⅡ −2.82% (Xunyou −0.30%) / Ad Marketing −2.70% / TV Broadcasting −2.35% — former AI-application and media names are sold in the ebb; this is thematic rotation, not fundamental deterioration, but it flags high-positioned-theme risk.",
 "rc3_rep": "Represented by: Digital Media (Fengyuzhu) / Publishing (China Publishing) / GamesⅡ (Xunyou)",
 "t_sec_outlook": "Next session (09-10 Thu) outlook",
 "o_logic": "Reasoning (based on the 09-09 close + crowd-psychology position)",
 "o_logic_text": "Extending 09-09's \"volume-shrinking divergence / short-term ebb\": the cycle sits at \"volume-shrinking divergence / short-term ebb\", with up-ratio 32%, limit-up 42, limit-down 0 and ChiNext −0.14% red — breadth and profit effect ebb together; yet turnover shrinks −¥90bn, leverage and main capital still cluster in optical modules/PCB, valuation pctile 79.6% stays rich, and indices are fake-red (up-index, down-stocks). Sector directions and trading rules for 09-10 follow (<b>no individual stock recommendations</b>).",
 "o1_tag": "Optical modules / PCB (watch)",
 "o1_t": "Comms equipment / Components / Electronic chemicalsⅡ",
 "o1_d": "Main-5d Innolight +¥7.69bn, XYS +¥4.10bn still lead, daily margin Innolight +¥561mn, Xingsen +¥492mn — price and capital still resonate medium-term, but 09-09 short-term stocks have ebbed (limit-up halved, ChiNext red).",
 "o1_cond": "Caution: leverage and main capital both concentrated = high crowding; avoid chasing in the ebb; if leaders keep diverging or limit-ups fall below 30, treat it as further cooling — buy pullbacks, not breakouts.",
 "o2_tag": "Consumer / resource rotation (wait)",
 "o2_t": "Rubber / Shipping ports / Coal mining / Department-store retail",
 "o2_d": "09-09 Rubber +4.07% (Black Cat +10%) / shipping ports +3.86% (Nanjing Port +10.03%) / coal mining +3.04% (Zhengzhou Coal +10.04%) / department-store retail (Baida 5 boards, Zhongbai 3 boards) take over — a high-low switch and thematic rotation in the ebb.",
 "o2_cond": "Caution: rotation names are mostly event / low-price driven, sustainability unproven; if turnover keeps shrinking, rotation accelerates and execution gets harder — do not chase laggards, only front-core names.",
 "o3_tag": "Former AI-application / media retreat (avoid)",
 "o3_t": "Digital Media / Publishing / GamesⅡ / Ad Marketing",
 "o3_d": "09-09 Digital Media −4.12% leads losers, Real-estate Services −3.79% / Publishing −3.45% / GamesⅡ −2.82% / Ad Marketing −2.70% retreat together — former AI-application and media names sold in the ebb, near-term pressure.",
 "o3_cond": "Caution: this is thematic rotation, not fundamental deterioration — do not panic-sell; but avoid high-positioned themes in the ebb, wait for a shrinking-volume stabilisation signal.",
 "o_r1": "<b>Position</b>: neutral-to-cautious (40–50%), no leverage. The cycle falls from \"tech counter-offensive / broad recovery\" to \"volume-shrinking divergence / short-term ebb\"; risk stays Medium — control size in the ebb, do not chase.",
 "o_r2": "<b>Volume-price confirmation</b>: only ease the ebb if up-ratio rebounds above 40% and turnover returns to ¥1.95tn; if turnover keeps shrinking below ¥1.8tn or limit-ups fall below 30, cut to ≤30%.",
 "o_r3": "<b>Main-line participation</b>: in optical modules / PCB during the ebb, buy pullbacks only, not breakouts — watch whether leaders stabilise; for consumer/resource rotation, only front-core names, no laggard chasing.",
 "o_r4": "<b>Avoid list</b>: former high-positioned AI-application / media themes (digital media / publishing / games), chasing optical-module laggards that are both leverage- and main-capital concentrated yet have ebbed, high-ladder relay in the ebb.",
 "o_r5": "<b>Risk control</b>: if optical-module leaders keep diverging and limit-ups fall below 30 on 09-10, treat it as further short-term cooling and cut immediately; if the SSE breaks MA20 (3936.39), switch to defence.",
 "s_breadth_v": "westock · data_market_overview(market_statis_updown); 2026-09-09 close",
 "s_portrait_v": "westock · data_market_overview(type=summary); 2026-09-09 (up-ratio 32%, breadth ebb, volume-shrinking divergence)",
 "s_index_v": "westock · data_market_overview(market_statis_daily_trade); 2026-09-09 close",
 "s_sector_v": "westock · data_sector(mode=ranking, kind=industry/concept); 2026-09-09",
 "s_hot_v": "westock · data_hot(kind=board); 2026-09-09 (Power / Computer Hardware / Shipping Ports on top)",
 "s_margin_v": "westock · tool_ranking(metric=margin_chg_d); 2026-09-09",
 "s_main_v": "westock · tool_ranking(metric=cap_main_5d); 2026-09-09 (Innolight +¥7.69bn #1)",
 "s_board_v": "westock · tool_ranking(metric=limitup_days); 2026-09-09 (ranking refreshed, 49 names)",
 "s_gap_v": "Aggregate margin balance (data_market_overview type=margin) returns empty; per-stock margin changes substituted, nothing fabricated. Valuation PE_TTM 20.40 is as of 2026-09-08 (CSI All-Share valuation published with a lag) and is flagged.",
 "t_src_note": "Timing: all timestamps are Beijing time. Macro data are monthly/quarterly and cannot be aligned directly with daily quotes; each is flagged. Breadth / indices / sectors / daily margin / main-5d / ladder are real 2026-09-09 data; valuation is as of 2026-09-08.",
 "ev_index": "II. Core indices (2026-09-09 close)",
 "o_rules_t": "Trading rules (09-10)",
 "o_compliance": "<b>Compliance:</b> this outlook gives sector directions and trading rules only, with no individual stock recommendations; the crowd-psychology position and sector inferences are based on real 2026-09-09 market data. Markets carry risk; decisions must be independent.",
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
# 2) 重建 BIAS 数组（09-09 真实数据）
# ============================================================
BIAS = [
 {"zh":"羊群效应","en":"Herding","sev":4,
  "zhd":"涨股比骤降至32%、涨停腰斩至42，但资金仍蜂拥涌向橡胶（黑猫股份+10%）、航运港口（南京港+10.03%）与煤炭（郑州煤电+10.04%）等事件驱动题材，光模块虽短线退潮但主力5日仍集中；群体从单一赛道（光模块）转向多热点轮动，独立判断被板块赚钱效应淹没。",
  "end":"Up-ratio plunges to 32% and limit-up halves to 42, yet capital still crowds into event-driven themes — rubber (Black Cat +10%), shipping ports (Nanjing Port +10.03%), coal (Zhengzhou Coal +10.04%); optical modules ebb short-term but main-5d stays concentrated — the herd rotates from one track to many, and independent judgement is drowned by sector profit effects."},
 {"zh":"损失厌恶","en":"Loss Aversion","sev":2,
  "zhd":"创业板−0.14%翻绿、个股普跌（跌3642只），持有者在退潮首日选择切换而非止损，把「错过资源/消费接力」视为更大损失——由前日追涨转为错失恐惧（FOMO）下的快速换仓。",
  "end":"ChiNext −0.14% red and stocks fall broadly (3642 down); holders switch rather than cut losses on the first ebb day, treating 'missing the resource/consumer relay' as the bigger loss — from chasing yesterday to rapid rotation under FOMO."},
 {"zh":"心理账户/赌徒谬误","en":"Mental Acct / Gambler","sev":2,
  "zhd":"把光模块主力5日净流入（中际旭创+76.9亿）外推为「主线仍强、还会再涨」，忽视09-09短线个股已退潮（涨停腰斩、创业板翻绿）、连板高度降至5板，题材与资金短期背离。",
  "end":"Extrapolating the main-5d optical-module inflow (Innolight +¥7.69bn) into 'the main line is still strong and will keep rising', ignoring that 09-09 short-term stocks have ebbed (limit-up halved, ChiNext red), ladder down to 5 boards — story and capital diverge short-term."},
 {"zh":"过度自信","en":"Overconfidence","sev":3,
  "zhd":"把上证+0.28%（3951.51站上MA20）读作「指数突破、趋势向好」，忽视涨股比仅32%、创业板翻绿、成交缩量−900亿、估值分位79.6%仍高，指数虚红掩盖个股普跌。",
  "end":"Reading SSE +0.28% (3951.51 above MA20) as 'index breakout, trend turning up', ignoring up-ratio of only 32%, ChiNext red, turnover shrink −¥90bn and valuation pctile 79.6% high — fake-red indices mask broad declines."},
 {"zh":"处置效应","en":"Disposition","sev":2,
  "zhd":"卖盈（前期AI应用/传媒方向在退潮首日被抛售）持亏（光模块套牢盘被视为「回本仓」仍加杠杆），融资单日中际旭创+5.61亿、兴森科技+4.92亿即为佐证——杠杆仍集中于光模块。",
  "end":"Selling winners (former AI-application / media sold on the first ebb day) while holding losers (trapped optical-module books treated as 'break-even' and levered further) — evidenced by daily margin Innolight +¥561mn and Xingsen +¥492mn still in optical modules."},
 {"zh":"锚定偏差","en":"Anchoring","sev":3,
  "zhd":"锚定09-07「涨股比57%、创业板+3.41%」的暖值与光模块主线高位，对09-09的32%广度回落缺乏定价锚，容易在单日指数虚红中误判「回调即买点」。",
  "end":"Anchored to 09-07's warm readings (up-ratio 57%, ChiNext +3.41%) and the optical-module high, lacking a pricing anchor at 09-09's 32% breadth drop — prone to mistaking a single fake-red day for 'dip = buy'."},
 {"zh":"确认偏误","en":"Confirmation Bias","sev":4,
  "zhd":"只看上证+0.28%站上MA20、主力5日中际旭创+76.9亿的「主线未死」信号，忽略涨股比32%、涨停腰斩至42、创业板翻绿、成交缩量−900亿、前期AI应用/传媒集体退潮的现实。",
  "end":"Only watching SSE +0.28% above MA20 and the main-5d Innolight +¥7.69bn 'main line not dead' signal, while ignoring up-ratio 32%, limit-up halved to 42, ChiNext red, turnover shrink −¥90bn and the former AI-application / media retreat."},
 {"zh":"近因偏差","en":"Recency","sev":3,
  "zhd":"外推单日指数虚红为「调整结束」，对09-04恐慌（28%）与09-07退潮转折的记忆迅速淡化，忽视退潮需要2日以上量价确认，短线极易抄在半山腰。",
  "end":"Extrapolating a single fake-red day into 'the correction is over'; memories of 09-04 panic (28%) and the 09-07 turn fade fast, ignoring that an ebb needs 2+ sessions of volume-price confirmation — easy to catch a falling knife."},
 {"zh":"叙事偏差","en":"Narrative","sev":4,
  "zhd":"「AI算力/光模块景气」叙事被主力5日资金榜强化（中际旭创+76.9亿、新易盛+41.0亿、东山精密+31.3亿），故事与资金自我实现；但融资单日中际旭创/兴森科技仍居前，叙事一旦证伪回撤幅度极大。",
  "end":"The 'AI compute / optical-module prosperity' narrative is reinforced by the main-5d leaderboard (Innolight +¥7.69bn, XYS +¥4.10bn, Dongshan +¥3.13bn); story and capital self-reinforce — but with daily margin still led by Innolight / Xingsen, the drawdown would be severe if the story is falsified."},
 {"zh":"代表性启发","en":"Representativeness","sev":3,
  "zhd":"被橡胶+4.07%、航运港口+3.86%的单日赚钱效应代表整体市场，误判「主线切换、结构健康」，忽视涨股比仅32%、创业板翻绿、数字媒体−4.12%领跌与成交缩量的现实。",
  "end":"Rubber +4.07% and shipping ports +3.86% one-day profit effects taken as representative of the whole market; mistaking it for 'healthy rotation' while ignoring up-ratio 32%, ChiNext red, Digital Media −4.12% leading losers and shrinking turnover."},
]
bias_js = "var BIAS = [\n" + ",\n".join(
    "    {zh:\"%s\",en:\"%s\",sev:%d,zhd:\"%s\",end:\"%s\"}" % (esc(b["zh"]), esc(b["en"]), b["sev"], esc(b["zhd"]), esc(b["end"]))
    for b in BIAS) + "\n  ];"
html, _n = re.subn(r'var BIAS = \[.*?\n  \];', bias_js, html, count=1, flags=re.S)
assert _n == 1, "BIAS 替换失败"

# ============================================================
# 3) 静态 body 证据表 + 涨跌分布 SVG 修正
#    OLD = 09-07 实际值（源 20260907.html 中内容），NEW = 09-09 值
# ============================================================
BODY = [
 ("<span class=\"chip\"><span data-i18n=\"c_upratio\">涨股比</span> <b>57%</b></span>",
  "<span class=\"chip\"><span data-i18n=\"c_upratio\">涨股比</span> <b>32%</b></span>"),
 ("<span class=\"chip\"><span data-i18n=\"c_limitup\">涨停</span> <b>90</b></span>",
  "<span class=\"chip\"><span data-i18n=\"c_limitup\">涨停</span> <b>42</b></span>"),
 ("<span class=\"chip\"><span data-i18n=\"c_turn\">两市成交</span> <b>¥1.95万亿</b></span>",
  "<span class=\"chip\"><span data-i18n=\"c_turn\">两市成交</span> <b>¥1.86万亿</b></span>"),
 ("<text x=\"167\" y=\"33\" fill=\"#fff\" font-size=\"14\" font-weight=\"800\" text-anchor=\"middle\">57%</text>",
  "<text x=\"167\" y=\"33\" fill=\"#fff\" font-size=\"14\" font-weight=\"800\" text-anchor=\"middle\">32%</text>"),
 ("<text x=\"407\" y=\"33\" fill=\"#fff\" font-size=\"14\" font-weight=\"800\" text-anchor=\"middle\">43%</text>",
  "<text x=\"407\" y=\"33\" fill=\"#fff\" font-size=\"14\" font-weight=\"800\" text-anchor=\"middle\">68%</text>"),
 ("<text x=\"340\" y=\"72\" fill=\"#d8392b\">3167</text>",
  "<text x=\"340\" y=\"72\" fill=\"#d8392b\">1794</text>"),
 ("<text x=\"340\" y=\"92\" fill=\"#1a9e5a\">2196</text>",
  "<text x=\"340\" y=\"92\" fill=\"#1a9e5a\">3642</text>"),
 ("<text x=\"340\" y=\"112\" fill=\"#6b675f\">195</text>",
  "<text x=\"340\" y=\"112\" fill=\"#6b675f\">124</text>"),
 ("<text x=\"340\" y=\"138\" fill=\"#d8392b\">90</text>",
  "<text x=\"340\" y=\"138\" fill=\"#d8392b\">42</text>"),
 ("<text x=\"340\" y=\"158\" fill=\"#1a9e5a\">1</text>",
  "<text x=\"340\" y=\"158\" fill=\"#1a9e5a\">0</text>"),
 ("<text x=\"340\" y=\"184\" fill=\"#1c1b19\">¥1.95万亿</text>",
  "<text x=\"340\" y=\"184\" fill=\"#1c1b19\">¥1.86万亿</text>"),
 ("（占 57%，较上一报告日（09-04） +11pct）", "（占 32%，较上一报告日（09-07） −25pct）"),
 ("（占 43%，较上一报告日（09-04） −11pct）", "（占 68%，较上一报告日（09-07） +25pct）"),
 ("（较前日 +48 只，连板高度 6板）", "（较前日 −48 只，连板高度 5板）"),
 ("（较前日 +1 只，跌停近乎清零）", "（较前日 −1 只，跌停清零）"),
 ("（环比 −840亿，小幅缩量）", "（环比 −900亿，缩量明显）"),
 ('<rect x="14" y="14" width="285" height="26" fill="#d8392b"/>',
  '<rect x="14" y="14" width="160" height="26" fill="#d8392b"/>'),
 ('<rect x="299" y="14" width="215" height="26" fill="#1a9e5a"/>',
  '<rect x="174" y="14" width="340" height="26" fill="#1a9e5a"/>'),
 ("<td><span class=\"val up\">57%</span>（涨3167 / 跌2196 / 平195）</td>",
  "<td><span class=\"val up\">32%</span>（涨1794 / 跌3642 / 平124）</td>"),
 ("<td><span class=\"val up\">90</span> / <span class=\"val down\">1</span></td>",
  "<td><span class=\"val up\">42</span> / <span class=\"val down\">0</span></td>"),
 ("<span class=\"val\">¥1.95万亿</span>（较前日 −840亿，小幅缩量）",
  "<span class=\"val\">¥1.86万亿</span>（较前次 −900亿，缩量明显）"),
 ("<td><span class=\"val up\">3932.70　+0.07%</span></td>",
  "<td><span class=\"val up\">3951.51　+0.28%</span></td>"),
 ("<td><span class=\"val up\">13774.91　+1.91%</span></td>",
  "<td><span class=\"val up\">13723.32　+0.15%</span></td>"),
 ("<td><span class=\"val up\">3398.68　+3.41%</span></td>",
  "<td><span class=\"val down\">3354.97　−0.14%</span></td>"),
 ("<span class=\"val up\">元件 +7.55%</span>（迅捷兴 +20%）<br>通信设备 +7.15%（太辰光 +14.5%）/ 非金属材料Ⅱ +4.72%（长江材料 +10%）<br>渔业 +4.59%（中水渔业 +9.96%）/ 电子化学品Ⅱ +4.51%（中石科技 +17.39%）/ 种植业 +4.48%（亚盛集团 +10.09%）",
  "<span class=\"val up\">橡胶 +4.07%</span>（黑猫股份 +10%）<br>航运港口 +3.86%（南京港 +10.03%）/ 非金属材料Ⅱ +3.51%<br>渔业 +3.29%（中水渔业 +9.98%）/ 煤炭开采 +3.04%（郑州煤电 +10.04%）/ 农产品加工 +2.98%"),
 ("<span class=\"val down\">保险Ⅱ −3.00%</span>（中国人保 −1.75%）/ 贵金属 −2.91%（山金国际 −1.71%）<br>煤炭开采 −2.63% / 厨卫电器 −2.34% / 化学纤维 −1.97% / 国有大型银行Ⅱ −1.88%",
  "<span class=\"val down\">数字媒体 −4.12%</span>（风语筑 +2.30%）/ 房地产服务 −3.79%<br>出版 −3.45% / 游戏Ⅱ −2.82%（迅游科技 −0.30%）/ 广告营销 −2.70% / 电视广播 −2.35%"),
 ("<span class=\"val up\">连板高度 6 板</span>（龙版传媒，已公告 AI 营收占比<0.01%）<br>3板 3 只：亚盛集团 / 百大集团 / 爱仕达；2板 9 只：安记食品 / 敦煌种业 / 中水渔业 / 天沃科技 / 播恩集团<br>新热点：迅捷兴 +20%（元件）/ 太辰光 +14.5%（通信设备）/ 中石科技 +17.39%（电子化学品Ⅱ）",
  "<span class=\"val up\">连板高度 5 板</span>（百大集团）<br>3板 4 只：中百集团 / 金正大 / 华脉科技 / 桂林旅游；2板 9 只：云煤能源 / 泸天化 / 黑猫股份 / 中粮科技 / 红棉股份 / 华康股份 / 精华制药 / 精艺股份 / 众泰汽车<br>新热点：黑猫股份 +10%（橡胶）/ 南京港 +10.03%（航运港口）/ 郑州煤电 +10.04%（煤炭开采）"),
 ("<span class=\"val up\">龙版传媒 6板</span>（2026-09-07）", "<span class=\"val up\">百大集团 5板</span>（2026-09-09）"),
 ("天孚通信 <span class=\"val up\">+3.04亿</span>（光模块）<br>新易盛 +1.99亿（光模块） / 我爱我家 +1.85亿 / 剑桥科技 +1.75亿（光模块） / 德科立 +1.48亿<br>协创数据 +1.31亿 / 云铝股份 +1.21亿 / 精智达 +1.15亿",
  "中际旭创 <span class=\"val up\">+5.61亿</span>（光模块）<br>兴森科技 +4.92亿 / 摩尔线程 +4.23亿 / 飞龙股份 +2.90亿<br>药明康德 +2.84亿 / 宁德时代 +2.42亿 / 中国平安 +2.19亿 / 天通股份 +1.94亿 / 剑桥科技 +1.92亿"),
 ("天孚通信 <span class=\"val up\">+3.04亿</span>（光模块）<br>新易盛 +1.99亿（光模块） / 我爱我家 +1.85亿 / 剑桥科技 +1.75亿（光模块） / 德科立 +1.48亿<br>协创数据 +1.31亿 / 云铝股份 +1.21亿 / 精智达 +1.15亿",
  "中际旭创 <span class=\"val up\">+5.61亿</span>（光模块）<br>兴森科技 +4.92亿 / 摩尔线程 +4.23亿 / 飞龙股份 +2.90亿<br>药明康德 +2.84亿 / 宁德时代 +2.42亿 / 中国平安 +2.19亿 / 天通股份 +1.94亿 / 剑桥科技 +1.92亿"),
 ("中际旭创 +44.39亿", "中际旭创 +76.9亿"),
 ("龙版传媒 6板（文化传媒，AI 营收占比<0.01%）<br>迅捷兴 +20%（元件）/ 太辰光 +14.5%（通信设备）/ 中石科技 +17.39%（电子化学品Ⅱ）<br>中水渔业 +9.96%（渔业）/ 亚盛集团 +10.09%（种植业）/ 中国出版 +10.03%（出版）",
  "百大集团 5板（百货零售）<br>黑猫股份 +10%（橡胶）/ 南京港 +10.03%（航运港口）/ 郑州煤电 +10.04%（煤炭开采）<br>中水渔业 +9.98%（渔业）/ 中百集团 3板（一般零售）/ 桂林旅游 3板（旅游）"),
 ("二、核心指数表现（2026-09-07 收盘）", "二、核心指数表现（2026-09-09 收盘）"),
 ("<b>2026-09-07 收盘（北京时间，盘后）</b>", "<b>2026-09-09 收盘（北京时间，盘后）</b>"),
 ("Next-Session Outlook (09-08 Tue)", "Next-Session Outlook (09-10 Thu)"),
]
for old, new in BODY:
    if old in html:
        html = html.replace(old, new, 1)
    else:
        print("[skip-body] 未命中: %r" % old[:46])

# ============================================================
# 4) 雷达数值标签（红字组）
# ============================================================
old_radar = '<text x="160" y="71">58</text><text x="237" y="120">70</text><text x="209" y="194">54</text>\n            <text x="160" y="167">46</text><text x="109" y="201">62</text><text x="55" y="118">87</text>'
new_radar = '<text x="160" y="71">60</text><text x="237" y="120">64</text><text x="209" y="194">50</text>\n            <text x="160" y="167">62</text><text x="109" y="201">52</text><text x="55" y="118">87</text>'
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
for _a, _b in [("2026-09-07 · 收盘", "2026-09-09 · 收盘"), ("2026-09-07 · Close", "2026-09-09 · Close")]:
    html = html.replace(_a, _b)

# ============================================================
# 6) hub（web/psychology/index.html）插入 0909 条目
# ============================================================
HUB = os.path.join(HERE, "..", "web", "psychology", "index.html")
hub = open(HUB, encoding="utf-8").read()
if "crowd-psychology-risk-radar-20260909.html" not in hub:
    entry = """    },
    {
      file:"crowd-psychology-risk-radar-20260909.html", date:"2026-09-09",
      risk:"中", riskEn:"Medium",
      cycleZh:"缩量分化 / 短线退潮", cycleEn:"Volume-shrinking divergence / Short-term ebb",
      cycleNoteZh:"涨停腰斩·创业板翻绿", cycleNoteEn:"Limit-up halves · ChiNext turns red",
      up:"32%", limitup:"42", board:"5板", turn:"¥1.86万亿",
      summaryZh:"涨股比57%→32%、涨停90→42腰斩、跌停0，创业板−0.14%（3354.97）翻绿、深成+0.15%、上证+0.28%（3951.51，站上MA20）；成交¥1.86万亿（−900亿）缩量，为10日均94%。橡胶+4.07%（黑猫股份+10%）/航运港口+3.86%（南京港+10.03%）领涨，非金属材料Ⅱ+3.51%/渔业+3.29%（中水渔业+9.98%）/煤炭开采+3.04%（郑州煤电+10.04%）跟随，主线切换至橡胶/航运/资源；数字媒体−4.12%领跌，房地产服务−3.79%/出版−3.45%/游戏Ⅱ−2.82%前期AI应用传媒退潮。连板5板（百大集团），3板4只、2板9只、首板35只。融资单日中际旭创+5.61亿居首（兴森科技+4.92亿、摩尔线程+4.23亿），主力5日中际旭创+76.9亿第一。估值PE_TTM 20.40（10年分位79.6%）仍偏高——退潮确认但非系统性恐慌，风险等级中。",
      summaryEn:"Up-ratio 57%→32%, limit-up 90→42 (halved), limit-down 0; ChiNext −0.14% (3354.97) turns red, SZ +0.15%, SSE +0.28% (3951.51, above MA20); turnover ¥1.86tn (−¥90bn) shrinks, 94% of 10d avg. Rubber +4.07% (Black Cat +10%) / shipping ports +3.86% (Nanjing Port +10.03%) lead; non-metal materialsⅡ +3.51% / fisheries +3.29% (Zhongshui +9.98%) / coal mining +3.04% (Zhengzhou Coal +10.04%) follow — the main line rotates to rubber/shipping/resources; digital media −4.12% leads losers, real-estate services −3.79% / publishing −3.45% / gamesⅡ −2.82% retreat. Ladder 5 boards (Baida Group), 3-board ×4, 2-board ×9, first-board ×35. Daily margin Innolight +¥561mn #1 (Xingsen +¥492mn, Moore Thread +¥423mn); main-5d Innolight +¥7.69bn #1. Valuation PE_TTM 20.40 (10y pctile 79.6%) still rich — ebb confirmed but no systemic panic; risk Medium.\""""
    tail = "    }\n  ];\n  REPORTS.reverse();"
    assert tail in hub, "hub tail not found"
    # 注意：entry 必须以对象闭合 "    }" 结尾，否则 hub JS 报 SyntaxError（0904 脚本遗留坑）
    hub = hub.replace(tail, entry + "\n    }\n  ];\n  REPORTS.reverse();", 1)
    open(HUB, "w", encoding="utf-8").write(hub)
    print("[ok] hub 已插入 0909 条目")
else:
    print("[skip] hub 已有 0909 条目")

# ============================================================
# 7) 写出 + 校验
# ============================================================
open(OUT, "w", encoding="utf-8").write(html)
print("[ok] 写出 %s (%d bytes)" % (OUT, len(html)))

leftover = ["57%</text>", "43%</text>", "3167", "2196", "龙版传媒 6板", "¥1.95万亿",
            "元件 +7.55%", "保险Ⅱ −3.00%", "天孚通信 +3.04亿", "3398.68", "13774.91",
            "3932.70", "90</text>", "中际旭创 +44.39亿", "（环比 −840亿，小幅缩量）"]
bad = [s for s in leftover if s in html]
print("[校验] 残留旧数据:", bad if bad else "无")
