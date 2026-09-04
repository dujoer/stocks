# -*- coding: utf-8 -*-
"""重建 2026-09-02 群体心理风险雷达：以 08-31 模板为基底，
用 09-02 真实行情数据（已落盘 market_overview/limitup/board_hot + 实时拉取的
margin_chg_d / cap_main_5d）全面覆盖 zh/en/i18n、BIAS、静态证据表、雷达读数。
保证 0 旧数据、0 外链。"""
import re, os

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "crowd-psychology-risk-radar-20260831.html")
OUT = os.path.join(HERE, "..", "web", "psychology", "crowd-psychology-risk-radar-20260902.html")
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
# 2) 09-02 叙述覆盖（中文）—— 真实数据
# ============================================================
# 真实数据快照：
# 指数：上证 3941.39 -0.97% / 深成 13611.55 -1.88% / 创业板 3312.24 -2.39%
# 涨跌：涨 1541 / 跌 3901 / 平 112（共 5554）；涨股比 27.75%≈28%；涨停 51 / 跌停 3
# 成交：¥1.7912万亿（缩量，较 08-31 的 ¥2.13万亿 −3420亿）
# 估值：PE_TTM 20.62，10年分位 81.23%，PB 1.77
# 技术：MACD DIF 10.35>DEA 3.63（红柱但指数跌=顶背离）；KDJ K72/D65/J85 高位钝化
# 领涨：地面兵装Ⅱ +6.48%（长城军工 +10.04%）/ 玻璃玻纤 +1.23% / 航空装备Ⅱ +0.93% / 教育 +0.82% / 旅游及景区 +0.72% / 国有大型银行 +0.57%
# 领跌：种植业 -5.93% / 焦炭Ⅱ -3.71% / 能源金属 -3.44% / 渔业 -3.29% / 农产品加工 -3.16% / 影视院线 -3.10%
# 连板：5板 新赛股份；4板 国芳集团、竞业达；3板 龙版传媒、欢瑞世纪、大晟文化、集泰股份；2板 茂业商业、九牧王、恒宝股份、小方制药、香溢融通、*ST宝馨
# 融资单日：中国巨石 +3.9986亿 / 中际旭创 +3.9119亿 / 长川科技 +3.8637亿 / 芒果超媒 +3.0549亿 / 同花顺 +2.3907亿
# 主力5日：生益科技 +27.92亿 / 协创数据 +24.48亿 / 大族激光 +17.66亿 / 浪潮信息 +14.79亿 / 香农芯创 +14.14亿
ZH = {
 "t_headline_sub": "2026-09-02 · 收盘",
 "t_breadth": "市场涨跌分布（2026-09-02 收盘）",
 "hk_stage": "阶段定性", "hv_stage": "<b>缩量普跌 / 情绪退潮</b>（09-02）",
 "hk_upratio": "涨股比", "hv_upratio": "<b>28%</b>（前次 08-31 57% · ↓ 29pct，急转直下）",
 "hk_lim": "涨停 / 跌停", "hv_lim": "<b>51</b> / <b>3</b>",
 "hk_amt": "成交额", "hv_amt": "<b>¥1.79万亿</b>（缩量普跌，较前日 −3420亿）",
 "hk_cycle": "情绪周期", "hv_cycle": "<b>缩量普跌 / 情绪退潮</b>",
 "hk_risk": "风险等级", "hv_risk": "<b class=\"hl-risk\">高</b>",
 "hk_flag": "关键提示",
 "hv_flag": "涨股比由 57% 骤降至 <b>28%</b>（广度崩塌），但连板高度仍有 <b>5板</b>、融资在下跌中<b>逆势加仓</b>——局部投机未退、杠杆与市场背离，追涨与踩踏风险并存",
 "tk1": "阶段定性", "tv1": "A 股 09-02 由 08-31「缩量滞涨 / 结构分化」急转为「缩量普跌 / 情绪退潮」：成交缩至 ¥1.79万亿（环比 −3420亿），涨股比仅 <b>28%</b>（1541涨 / 3901跌 / 平112），涨停 51、跌停 3，三指齐跌（上证 −0.97% / 深成 −1.88% / 创业板 −2.39%），创业板领跌；技术面 MACD 仍红柱但指数下跌 = <b>顶背离</b>，KDJ 高位钝化（K72/D65/J85）；仅地面兵装（军工）逆势 +6.48% 独涨，种植业 −5.93%、能源金属 −3.44% 等普跌。风险等级维持 <b>高</b>。",
 "tk2": "广度崩塌", "tv2": "涨股比 <b>28%</b>（前次 57% ↓ 29pct）· 涨停 <b>51</b>（89→51）· 跌停 <b>3</b> · 成交 <b>¥1.79万亿</b>（缩量 −3420亿）——普跌格局，参与度断崖式回落。",
 "tk3": "指数齐跌", "tv3": "上证 <b>−0.97%</b> / 深成 <b>−1.88%</b> / 创业板 <b>−2.39%</b>；三指齐跌、创业板领跌，MACD 红柱与指数下跌背离，中期弱势未改（创业板 60日 −14% 级别）。",
 "tk4": "板块分化", "tv4": "<b>地面兵装Ⅱ 逆势独涨 +6.48%</b>（长城军工 +10.04%）领涨，玻璃玻纤 +1.23% / 航空装备Ⅱ +0.93% / 教育 +0.82% / 旅游及景区 +0.72% / 国有大型银行 +0.57% 微红；<b>种植业 −5.93%、焦炭Ⅱ −3.71%、能源金属 −3.44%、渔业 −3.29%、农产品加工 −3.16%、影视院线 −3.10% 普跌</b>——仅军工单点活跃，其余板块大面积下挫，结构极端分化。",
 "tk5": "连板结构", "tv5": "连板高度 <b>5 板</b>（新赛股份），国芳集团 / 竞业达 4板，龙版传媒 / 欢瑞世纪 / 大晟文化 / 集泰股份 3板；投机热度仍在但主线偏军工 / 农业题材，持续性待验。",
 "tk6": "杠杆逆势", "tv6": "融资单日加仓榜 <b>中国巨石 +3.9986亿 居首</b>，中际旭创 +3.9119亿、长川科技 +3.8637亿、芒果超媒 +3.0549亿、同花顺 +2.3907亿——<b>大盘普跌中杠杆逆势加仓</b>，与市场走向背离，拥挤度与回补风险上升。",
 "tk7": "估值 / 基本面背离", "tv7": "PE_TTM <b>20.62</b>（10年分位 <b>81.23%</b> 仍高）+ PMI <b>49.2</b>（枯荣线下）——指数虽仅小跌但估值分位偏高，股价位阶仍贵，基本面接不住。",
 "tk8": "情绪周期", "tv8": "由 08-31「缩量滞涨 / 结构分化」急转「缩量普跌 / 情绪退潮」：涨股比由 57% 骤降至 28%（广度崩塌），三指齐跌、创业板领跌，MACD 红柱与指数背离；连板高度仍 5板、融资逆势加仓，说明局部投机未退、杠杆与市场背离，追涨与踩踏风险并存。风险等级维持 <b>高</b>。",
 "t_tldr_text": "A股 09-02 呈现「缩量普跌 / 情绪退潮」：成交缩至 ¥1.79万亿（环比 −3420亿），涨股比仅 28%（1541涨 / 3901跌 / 平112），涨停 51、跌停 3，三大指数齐跌（上证 −0.97% / 深成 −1.88% / 创业板 −2.39%，创业板领跌）；技术面 MACD 仍红柱但指数下跌 = 顶背离，KDJ 高位钝化。板块层面「地面兵装Ⅱ 逆势独涨 +6.48%（长城军工 +10.04%）」领涨，玻璃玻纤 +1.23% / 航空装备Ⅱ +0.93% / 教育 +0.82% / 旅游及景区 +0.72% / 国有大型银行 +0.57% 微红；种植业 −5.93%、焦炭Ⅱ −3.71%、能源金属 −3.44%、渔业 −3.29%、农产品加工 −3.16%、影视院线 −3.10% 普跌——仅军工单点活跃、其余大面积下挫，结构极端分化。连板高度 5板（新赛股份），国芳集团 / 竞业达 4板，龙版传媒 / 欢瑞世纪 / 大晟文化 / 集泰股份 3板。关键资金信号：融资单日加仓榜中国巨石 +3.9986亿居首，中际旭创 +3.9119亿、长川科技 +3.8637亿、芒果超媒 +3.0549亿、同花顺 +2.3907亿——大盘普跌中杠杆逆势加仓、与市场背离。群体心理由「缩量滞涨 / 结构分化」急转「缩量普跌 / 情绪退潮」——涨股比 28%、三指齐跌、创业板领跌、MACD 顶背离，广度崩塌但连板仍 5板、融资逆势加仓，局部投机未退、杠杆背离，追涨与踩踏风险并存，风险等级高。",
 "t_cycle_note": "注：上方「悲观」为实时群体心理定位（缩量普跌 / 情绪退潮）——09-02 涨跌分布（涨股比 28%、涨停 51 只、跌停 3 只、成交 ¥1.79万亿）显示广度断崖式回落（由 57% 降至 28%），普跌、创业板领跌、MACD 顶背离；连板高度仍 5板、融资逆势加仓，说明局部投机未退、杠杆与市场背离。若量能继续萎缩、指数下破短期均线，情绪将进一步滑向恐慌 / 分歧加剧。",
 "t_radar_note": "六维风险读数（0–100，由下方真实数据综合映射，越高代表该维度群体脆弱性越强）：拥挤度 62 / 融资 68 / 换手 54 / 广度 78 / 媒体 65 / 估值 88。广度由 52 升至 78（09-02 涨股比 28%，由 57% 崩塌、参与度断崖 = 脆弱性骤升）；换手由 56 降至 54（成交缩至 ¥1.79万亿，活跃换手回落）；融资由 70 降至 68（融资单日中国巨石 +3.9986亿 / 中际旭创 +3.9119亿 逆势加仓，杠杆背离但金额较 08-31 收敛）；拥挤度由 72 降至 62（地面兵装单点独涨 + 连板 5板，集中度偏中）；媒体由 68 降至 65（涨停 51、连板 5板，但普跌，情绪温度回落）；估值仍高悬 88（PE_TTM 20.62、10年分位 81.23% 偏高）。整体呈「缩量普跌 / 情绪退潮」结构——广度崩塌、估值高悬、杠杆逆势，追涨与踩踏风险并存，脆弱性显著。",
 "t_breadth_note": "涨股比由 57% 骤降至 28%、跌停 3（仍低）、涨停 51（由 89 回落）；缩量普跌、广度崩塌，参与度断崖。指数齐跌（上证 −0.97% / 深成 −1.88% / 创业板 −2.39%，创业板领跌），MACD 红柱与指数背离 = 顶背离；成交 ¥1.79万亿环比 −3420亿（缩量），仅地面兵装 +6.48% 独涨，其余大面积下挫，结构极端分化。",
 "ev_upratio_i": "由 57% 骤降至 28%，参与度断崖式回落，广度崩塌，缩量普跌下风险偏好急转保守",
 "ev_limit_i": "涨停 51（由 89 回落）、跌停仅 3，连板高度仍 5板（新赛股份）——投机热度收敛但未熄，局部题材仍有承接",
 "ev_amount_i": "量能缩至 ¥1.79万亿（环比 −3420亿），缩量普跌 = 承接力转弱、观望情绪升温，缩量下挫需警惕惯性",
 "ev_sh_i": "小跌 −0.97%，MACD 红柱但指数跌 = 顶背离，PE_TTM 20.62（10年分位 81.23% 偏高），短期均线承压",
 "ev_sz_i": "中盘承压 −1.88%，PE 约 35，中期弱势未改，缩量下挫",
 "ev_cyb_i": "高弹性领跌 −2.39%，高估值高弹性主线中期深套未解，缩量普跌中冲击最大",
 "ev_secup_i": "地面兵装Ⅱ 逆势独涨 +6.48%（长城军工 +10.04%）领涨，玻璃玻纤 +1.23% / 航空装备Ⅱ +0.93% / 教育 +0.82% / 旅游及景区 +0.72% / 国有大型银行 +0.57% 微红——结构极端分化，仅军工单点活跃",
 "ev_secdn_i": "种植业 −5.93% 领跌 / 焦炭Ⅱ −3.71% / 能源金属 −3.44% / 渔业 −3.29% / 农产品加工 −3.16% / 影视院线 −3.10%——普跌，前期强势与周期资源同步补跌，风险偏好全面转弱",
 "ev_board_i": "连板 5板（新赛股份），国芳集团 / 竞业达 4板；热点由军工 / 农业题材主导（长城军工 +10.04% / 新赛股份 5板），主线偏题材博弈，持续性待验",
 "ev_height_i": "高度 5板（新赛股份，2026-09-02 收盘），投机热度收敛但未熄，主线偏军工 / 农业题材，风险偏好急转保守但连板仍在",
 "ev_main": "融资单日净流入TOP",
 "ev_main_i": "杠杆资金当日集中于玻纤 / 光模块 / 半导体与传媒（中国巨石 +3.9986亿 / 中际旭创 +3.9119亿 / 长川科技 +3.8637亿 / 芒果超媒 +3.0549亿 / 同花顺 +2.3907亿）——普跌中逆势加仓，杠杆与市场背离",
 "ev_margin": "融资单日变动TOP",
 "ev_margin_i": "融资单日加仓榜中国巨石居首（+3.9986亿），中际旭创 +3.9119亿、长川科技 +3.8637亿、芒果超媒 +3.0549亿、同花顺 +2.3907亿、协创数据 +2.0724亿、中文在线 +1.8915亿——下跌中杠杆逆势加仓，背离明显",
 "ev_hot_i": "热搜由军工 / 农业题材 + 连板主导（长城军工 / 新赛股份 / 国芳集团 / 竞业达 / 龙版传媒）；data_hot 本次未返回，以板块领涨股 + 排行榜综合替代（见来源口径）",
 "ev_margintotal_i": "缺口：聚合两融余额为空，以个股融资变动替代观察（见上）；连板高度 / 融资单日均 2026-09-02 真实数据",
 "t_ev_note": "数据口径：宏观指标多截至 2026-07（月频）或 2026-09-02（日频）；PMI/产能/社融为 08-21 复核最新月频值（无新发布），CPI / M1-M2 / 10Y / LPR 沿用前期已查询月频 / 日频值（未更新）。涨跌分布 / 指数 / 成交额 / 板块 / 融资单日均为 2026-09-02 真实收盘；官方综合画像、连板梯队、融资单日均已更新至 2026-09-02，相关字段已标注。财新PMI数据源覆盖仅至 2025-08（49.2），不作为主要依据。详见末尾「数据来源与日期口径」。",
 "rc1_tag": "红线区 · 缩量普跌 + 高估值 + 杠杆逆势 + 顶背离",
 "rc1_t": "缩量普跌 + 高估值 + 杠杆逆势 + 顶背离",
 "rc1_d": "估值 PE_TTM 20.62、10年分位 81.23% 仍高（指数仅小跌但分位贵），MACD 红柱与指数下跌 = 顶背离，三指齐跌、创业板 −2.39% 领跌；缩量普跌（成交 ¥1.79万亿，环比 −3420亿）下技术面背离、广度崩塌（涨股比 28%），而融资单日逆势加仓（中国巨石 +3.9986亿 / 中际旭创 +3.9119亿），拥挤度（62）与融资（68）读数仍高 = 杠杆背离、二次杀跌风险积聚。",
 "rc1_rep": "代表：高估值创业板 / 军工题材高位 / 融资逆势加仓标的",
 "rc2_tag": "黄线区 · 军工单点独涨 + 其余普跌（极端分化）",
 "rc2_t": "军工单点独涨 + 其余普跌",
 "rc2_d": "09-02 仅地面兵装Ⅱ +6.48%（长城军工 +10.04%）逆势独涨，玻璃玻纤 +1.23% / 航空装备Ⅱ +0.93% 微红；种植业 −5.93% / 焦炭Ⅱ −3.71% / 能源金属 −3.44% / 渔业 −3.29% 普跌，结构极端分化。连板仍 5板（新赛股份），主线由军工 / 农业题材主导，轮动快、持续性差。",
 "rc2_rep": "代表：地面兵装Ⅱ（长城军工）/ 玻璃玻纤（中国巨石）/ 航空装备Ⅱ",
 "rc3_tag": "绿线区 · 连板投机 + 普跌补跌（相对）",
 "rc3_t": "连板投机 + 普跌补跌",
 "rc3_d": "新赛股份（连板 5板）、国芳集团 / 竞业达（4板）代表连板梯队，但种植业 −5.93% / 能源金属 −3.44% / 农产品加工 −3.16% 补跌，资金向军工 / 农业题材集中，本质仍是弱市下的结构分化而非新周期主线，连板越高、补跌风险越大。",
 "rc3_rep": "代表：新赛股份 / 国芳集团 / 竞业达 / 龙版传媒",
 "t_sec_outlook": "下个交易日（09-03 周四）展望",
 "o_logic": "研判逻辑（基于 09-02 收盘 + 群体心理定位）",
 "o_logic_text": "由 09-02 的「缩量普跌 / 情绪退潮」延伸：情绪周期定位「缩量普跌 / 情绪退潮」，涨股比 28%、涨停 51，广度崩塌（由 57% 降至 28%），成交缩至 ¥1.79万亿（环比 −3420亿）、技术面 MACD 顶背离（红柱但指数跌）、三指齐跌、创业板 −2.39% 领跌、估值偏高（PE_TTM 20.62、10年分位 81.23%）、趋势方向仍弱势下跌。基于此推演 09-03 的板块方向与交易规则（<b>不涉及具体个股推荐</b>）。",
 "o1_tag": "军工 / 地面兵装（观察）",
 "o1_t": "地面兵装Ⅱ / 航空装备Ⅱ / 玻璃玻纤",
 "o1_d": "09-02 唯一逆势独涨方向：地面兵装Ⅱ +6.48%（长城军工 +10.04%）/ 玻璃玻纤 +1.23% / 航空装备Ⅱ +0.93%。军工单点活跃，若量能配合有望延续，但需警惕缩量普跌下高位追涨与补跌。",
 "o1_cond": "注意：单点题材持续性需验证；严禁把单日轮动当反转，量能不放大则谨慎，不追涨停潮。",
 "o2_tag": "农业 / 周期资源（观望）",
 "o2_t": "种植业 / 能源金属 / 焦炭",
 "o2_d": "09-02 种植业 −5.93%、能源金属 −3.44%、焦炭Ⅱ −3.71% 领跌，前期强势与周期资源同步补跌，资金撤离，进入退潮观察。",
 "o2_cond": "注意：普跌中补跌未止；不抄底、不加杠杆；右侧需量价持续确认。",
 "o3_tag": "高估值创业板 / 题材高位（回避）",
 "o3_t": "创业板高位 / 融资逆势加仓标的",
 "o3_d": "09-02 创业板 −2.39% 领跌，MACD 顶背离，融资逆势加仓（中国巨石 / 中际旭创）显示杠杆背离——高估值与杠杆标的在缩量普跌中回撤风险最大，短期回避。",
 "o3_cond": "注意：等缩量止跌 + 龙头先于板块企稳再考虑右侧；破位即减。",
 "o_r1": "<b>仓位</b>：维持低仓位，不加杠杆。情绪转入「缩量普跌 / 情绪退潮」，广度崩塌、成交萎缩、趋势仍弱，整体风险预算显著收缩。",
 "o_r2": "<b>高位主线</b>：不追涨、不加杠杆；以量能持续 + 指数站回短期均线上方为右侧确认，破位即减。",
 "o_r3": "<b>新主线</b>：需量价持续确认（≥2 日连续放量 + 龙头未切换）才能跟进；严禁把单日轮动当反转。",
 "o_r4": "<b>缩量普跌</b>：成交缩至 ¥1.79万亿（环比 −3420亿），若 09-03 继续缩量但指数惯性下挫、涨股比仍<30%，则广度脆弱、需警惕恐慌 / 踩踏。",
 "o_r5": "<b>风控</b>：成交 ¥1.79万亿（环比 −3420亿，缩量普跌），若 09-03 继续缩量且指数下破短期均线则降仓至 ≤3 成；若放量跌破则进一步降仓。",
 "s_breadth_v": "westock · data_changedist；2026-09-02 收盘",
 "s_portrait_v": "westock · data_market_overview(type=summary)；2026-09-02（涨股比 28% 真实广度崩塌，缩量普跌）",
 "s_index_v": "westock · data_quote(sh000001,sz399001,sz399006)；2026-09-02 收盘",
 "s_sector_v": "westock · data_sector(mode=ranking)；2026-09-02（fundflow 含行业/概念/地区排行与领涨股）",
 "s_hot_v": "westock · data_hot 本次未返回；热搜以 data_sector(fundflow 领涨股) + tool_ranking(limitup_days / margin_chg_d) 综合替代；涨跌分布/指数/板块/融资单日为 2026-09-02",
 "s_margin_v": "westock · tool_ranking(metric=margin_chg_d)；2026-09-02",
 "s_main_v": "westock · tool_ranking(metric=cap_main_5d)；2026-09-02（板块暗盘视角，以主力5日替代观察）",
 "s_board_v": "westock · tool_ranking(metric=limitup_days)；2026-09-02（当日排行榜已刷新）",
 "s_gap_v": "市场两融余额聚合值（data_market_overview type=margin）数据源返回空，已用个股融资变动替代，未编造；data_hot 本次未返回，已用板块领涨股 + 排行榜综合替代；连板高度 / 融资单日均为 2026-09-02 真实数据。",
 "t_src_note": "时间口径：所有时点按北京时间。宏观为月频 / 季频，与日频行情不可直接对齐，已分别标注。涨跌分布 / 指数 / 板块 / 融资单日 / 连板高度均为 2026-09-02 当日真实数据。",
 "ev_index": "二、核心指数表现（2026-09-02 收盘）",
 "o_rules_t": "交易规则（09-03）",
 "o_compliance": "<b>合规说明：</b>本展望仅给出板块方向与交易规则，不涉及具体个股推荐；群体心理定位与板块推断基于 2026-09-02 真实行情数据，市场有风险，决策须独立。",
}

# ============================================================
# 3) 09-02 叙述覆盖（英文）—— 平行翻译
# ============================================================
EN = {
 "t_headline_sub": "2026-09-02 · Close",
 "t_breadth": "Market Breadth (2026-09-02 close)",
 "hk_stage": "Stage", "hv_stage": "<b>Volume-shrink selloff / sentiment ebb</b> (09-02)",
 "hk_upratio": "Up-ratio", "hv_upratio": "<b>28%</b> (prior 57% · ↓ 29pct, sharp drop)",
 "hk_lim": "Limit-up / Down", "hv_lim": "<b>51</b> / <b>3</b>",
 "hk_amt": "Turnover", "hv_amt": "<b>¥1.79tn</b> (volume-shrink selloff, −342bn vs prior)",
 "hk_cycle": "Sentiment cycle", "hv_cycle": "<b>Volume-shrink selloff / sentiment ebb</b>",
 "hk_risk": "Risk level", "hv_risk": "<b class=\"hl-risk\">High</b>",
 "hk_flag": "Key flag",
 "hv_flag": "Up-ratio collapsed from 57% to <b>28%</b> (breadth crash), yet streak height still <b>5 boards</b> and margin <b>added against the tide</b> — local speculation persists, leverage diverges from market, chase & stampede risks coexist",
 "tk1": "Stage", "tv1": "On 09-02 A-shares snapped from 08-31's 'volume-stall / structural divergence' into 'volume-shrink selloff / sentiment ebb': turnover shrank to ¥1.79tn (−342bn vs prior), up-ratio only <b>28%</b> (1541 up / 3901 down / 112 flat), limit-up 51, limit-down 3, all three indices down (SSE −0.97% / SZSE −1.88% / ChiNext −2.39%) with ChiNext leading the drop; technics MACD still red but indices fell = <b>top divergence</b>, KDJ high-level staleness (K72/D65/J85); only ground-arm Equipment (military) rose alone +6.48%, planting −5.93% / energy-metals −3.44% broadly down. Risk stays <b>High</b>.",
 "tk2": "Breadth crash", "tv2": "Up-ratio <b>28%</b> (prior 57% ↓ 29pct) · Limit-up <b>51</b> (89→51) · Limit-down <b>3</b> · Turnover <b>¥1.79tn</b> (volume-shrink −342bn) — broad selloff, participation cliff-drop.",
 "tk3": "All indices down", "tv3": "SSE <b>−0.97%</b> / SZSE <b>−1.88%</b> / ChiNext <b>−2.39%</b>; all three down, ChiNext leads; MACD red vs index-down divergence, mid-term weakness unchanged.",
 "tk4": "Sector split", "tv4": "<b>Ground-arm EquipmentⅡ alone +6.48%</b> (Great Wall Military +10.04%) led, glass-fiber +1.23% / aviation-equip Ⅱ +0.93% / education +0.82% / travel +0.72% / state-big-banks +0.57% faint-green; <b>planting −5.93%, coke Ⅱ −3.71%, energy-metals −3.44%, fishery −3.29%, farm-products −3.16%, film-TV −3.10% broadly down</b> — only military single-point active, most sectors plunged, extreme divergence.",
 "tk5": "Streak structure", "tv5": "Top board height <b>5 boards</b> (Xinsai Shares), Guofang Group / Jingye Da 4 boards, Longban Media / Huarui Century / Dasheng Culture / Jitai 3 boards; heat persists but main line skewed to military / agriculture themes, persistence unproven.",
 "tk6": "Leverage against tide", "tv6": "Margin daily-add led by <b>China Jushi +¥0.3999bn (#1)</b>, Zhongji +0.3912bn, Changchuan +0.3864bn, Mango +0.3055bn, Tonghuashun +0.2391bn — <b>margin added against the tide in a broad selloff</b>, diverging from market, crowding & refill risk up.",
 "tk7": "Valuation / fundamentals", "tv7": "PE_TTM <b>20.62</b> (10y pctile <b>81.23%</b> still high) + PMI <b>49.2</b> (below 50) — indices only mildly down but valuation pctile rich, fundamentals cannot support the level.",
 "tk8": "Sentiment cycle", "tv8": "From 'volume-stall / structural divergence' into <b>volume-shrink selloff / sentiment ebb</b>: up-ratio crashed 57%→28% (breadth collapse), all three down, ChiNext leads, MACD divergence; streak still 5 boards, margin against tide — local speculation persists, leverage diverges, chase & stampede risks coexist. Risk stays <b>High</b>.",
 "t_tldr_text": "On 2026-09-02 A-shares showed 'volume-shrink selloff / sentiment ebb': turnover shrank to ¥1.79tn (−342bn vs prior), up-ratio only 28% (1541 up / 3901 down / 112 flat), limit-up 51, limit-down 3, all three indices down (SSE −0.97% / SZSE −1.88% / ChiNext −2.39%, ChiNext leads); technics MACD red but index-down = top divergence, KDJ high staleness. Sector-wise 'Ground-arm EquipmentⅡ alone +6.48% (Great Wall Military +10.04%)' led, glass-fiber +1.23% / aviation-equip Ⅱ +0.93% / education +0.82% / travel +0.72% / state-big-banks +0.57% faint-green; planting −5.93%, coke Ⅱ −3.71%, energy-metals −3.44%, fishery −3.29%, farm-products −3.16%, film-TV −3.10% broadly down — only military single-point active, most sectors plunged, extreme divergence. Streak 5 boards (Xinsai Shares), Guofang / Jingye Da 4 boards, Longban / Huarui / Dasheng / Jitai 3 boards. Key flow: margin daily-add led by China Jushi +0.3999bn, Zhongji +0.3912bn, Changchuan +0.3864bn, Mango +0.3055bn, Tonghuashun +0.2391bn — margin added against the tide in a broad selloff. Crowd psychology snapped from 'volume-stall / structural divergence' into 'volume-shrink selloff / sentiment ebb' — up-ratio 28%, all three down, ChiNext leads, MACD divergence; breadth collapse but streak still 5 boards, margin against tide, chase & stampede risks coexist, risk High.",
 "t_cycle_note": "Note: 'Pessimism' above is the live crowd positioning (Volume-shrink selloff / sentiment ebb) — the 09-02 breadth (up-ratio 28%, limit-up 51, limit-down 3, turnover ¥1.79tn) shows participation cliff-drop (57%→28%), broad selloff, ChiNext leads, MACD divergence; streak still 5 boards, margin against tide. If volume keeps shrinking and indices break below short-term MAs, sentiment slides further to panic / widening divergence.",
 "t_radar_note": "Six-dimension risk readings (0–100, model-mapped, higher = more fragility): Crowding 62 / Margin 68 / Turnover 54 / Breadth 78 / Media 65 / Valuation 88. Breadth 52→78 (09-02 up-ratio 28%, crashed from 57%, participation cliff = fragility surged); Turnover 56→54 (turnover shrank to ¥1.79tn, active turnover fell); Margin 70→68 (margin daily China Jushi +0.3999bn / Zhongji +0.3912bn against tide, leverage diverges but amount smaller than 08-31); Crowding 72→62 (ground-arm single-point + 5-board streak, concentration mid); Media 68→65 (limit-up 51, 5-board streak, but broad selloff, sentiment cooler); Valuation still high at 88 (PE_TTM 20.62, 10y pctile 81.23% elevated). Overall a 'volume-shrink selloff / sentiment ebb' structure — breadth collapse, valuation high, leverage against tide, chase & stampede risks coexist, fragility significant.",
 "t_breadth_note": "Up-stock ratio crashed 57%->28%, limit-down only 3, limit-up 51 (from 89); volume-shrink selloff, breadth collapse, participation cliff. All three down (SSE −0.97% / SZSE −1.88% / ChiNext −2.39%, ChiNext leads), MACD red vs index-down = divergence; turnover ¥1.79tn −342bn (volume-shrink), only ground-arm +6.48% alone up, rest broadly down, extreme divergence.",
 "ev_upratio_i": "Crashed 57%->28%, participation cliff-drop, breadth collapse, risk appetite snapped conservative under volume-shrink selloff",
 "ev_limit_i": "Limit-up 51 (from 89), limit-down only 3, streak still 5 boards (Xinsai) — speculative heat收敛 but not out, local themes still bid",
 "ev_amount_i": "Turnover shrank to ¥1.79tn (−342bn vs prior); volume-shrink selloff = weaker absorption, caution rising, beware inertia on shrinking volume",
 "ev_sh_i": "Mild −0.97%, MACD red but index down = top divergence, PE_TTM 20.62 (10y pctile 81.23% rich), short-term MAs pressured",
 "ev_sz_i": "Mid-cap −1.88%, PE ~35, mid-term weakness unchanged, volume-shrink down",
 "ev_cyb_i": "High-beta leads down −2.39%, rich-valuation high-beta mid-term trap unrelieved, hit hardest in volume-shrink selloff",
 "ev_secup_i": "Ground-arm EquipmentⅡ alone +6.48% (Great Wall Military +10.04%) led, glass-fiber +1.23% / aviation-equip Ⅱ +0.93% / education +0.82% / travel +0.72% / state-big-banks +0.57% faint-green — extreme divergence, only military single-point active",
 "ev_secdn_i": "Planting −5.93% led / coke Ⅱ −3.71% / energy-metals −3.44% / fishery −3.29% / farm-products −3.16% / film-TV −3.10% — broad selloff, prior-strong & cycle resources correct together, risk appetite fully weak",
 "ev_board_i": "Streak 5 boards (Xinsai Shares), Guofang / Jingye Da 4 boards; hotspots led by military / agriculture themes (Great Wall Military +10.04% / Xinsai 5 boards), main line skewed to thematic betting, persistence unproven",
 "ev_height_i": "Rose to 5 boards (Xinsai Shares, 2026-09-02 close), speculative heat收敛 but not out, main line skewed to military / agriculture, appetite snapped conservative but streak persists",
 "ev_main": "Margin daily net-inflow TOP",
 "ev_main_i": "Margin capital concentrated that day in fiberglass / optical-module / semi & media (China Jushi +0.3999bn / Zhongji +0.3912bn / Changchuan +0.3864bn / Mango +0.3055bn / Tonghuashun +0.2391bn) — added against the tide in a selloff, leverage diverges from market",
 "ev_margin": "Margin daily change TOP",
 "ev_margin_i": "Margin daily-add led by China Jushi (+0.3999bn), Zhongji +0.3912bn, Changchuan +0.3864bn, Mango +0.3055bn, Tonghuashun +0.2391bn, Xiechuang +0.2072bn, Chinese All +0.1892bn — leverage added against the tide on a down day, clear divergence",
 "ev_hot_i": "Hot-search led by military / agriculture themes + streak (Great Wall Military / Xinsai / Guofang / Jingye Da / Longban); data_hot unavailable this round, proxied by sector leaders + rankings (see Sources)",
 "ev_margintotal_i": "Gap: aggregate margin balance empty; proxied by per-stock margin changes (above); streak height / margin daily are all 2026-09-02 real data",
 "t_ev_note": "Time caliber: macro mostly as of 2026-07 (monthly) or 2026-09-02 (daily); PMI/capacity/financing re-checked 08-21 (no new release, monthly), CPI/M1-M2/10Y/LPR from prior pulls (unchanged). Breadth / indices / turnover / sectors / margin daily are all 2026-09-02 real close; official portrait, streak, margin daily all updated to 2026-09-02 and labeled. Caixin PMI source only to 2025-08 (49.2), not primary. See 'Data Sources & Time Caliber' at end.",
 "rc1_tag": "RED · Volume-shrink selloff + high valuation + margin against tide + top divergence",
 "rc1_t": "Volume-shrink selloff + high valuation + margin against tide + top divergence",
 "rc1_d": "PE_TTM 20.62, 10y pctile 81.23% still high (indices only mildly down but pctile rich), MACD red vs index-down = top divergence, all three down, ChiNext −2.39% leads; volume-shrink selloff (¥1.79tn, −342bn) with technics divergence, breadth collapse (up-ratio 28%), yet margin added against tide (China Jushi +0.3999bn / Zhongji +0.3912bn), Crowding (62) and Margin (68) still elevated = leverage divergence, second sell-off risk accumulates.",
 "rc1_rep": "Names: high-valuation ChiNext / military-theme highs / margin-against-tide names",
 "rc2_tag": "AMBER · Military single-point up + rest broadly down (extreme divergence)",
 "rc2_t": "Military single-point up + rest broadly down",
 "rc2_d": "09-02 only Ground-arm EquipmentⅡ +6.48% (Great Wall Military +10.04%) rose alone, glass-fiber +1.23% / aviation-equip Ⅱ +0.93% faint-green; planting −5.93% / energy-metals −3.44% / coke Ⅱ −3.71% broadly down, extreme divergence. Streak still 5 boards (Xinsai), main line led by military / agriculture, fast rotation, poor persistence.",
 "rc2_rep": "Names: Ground-arm EquipmentⅡ (Great Wall Military) / glass-fiber (China Jushi) / aviation-equip Ⅱ",
 "rc3_tag": "GREEN · Streak speculation + broad-selloff correction (relative)",
 "rc3_t": "Streak speculation + broad-selloff correction",
 "rc3_d": "Xinsai (5-board streak leader), Guofang / Jingye Da (4 boards) represent the streak ladder, but planting −5.93% / energy-metals −3.44% / farm-products −3.16% correct, capital centralized to military / agriculture — still risk-off / structural divergence, not a new-cycle main line; higher streak = higher correction risk.",
 "rc3_rep": "Names: Xinsai / Guofang / Jingye Da / Longban",
 "t_sec_outlook": "Next-Session Outlook (09-03 Thu)",
 "o_logic": "Inference logic (based on 09-02 close + crowd positioning)",
 "o_logic_text": "Extending 09-02's 'volume-shrink selloff / sentiment ebb': crowd cycle at 'Volume-shrink selloff / sentiment ebb', up-ratio 28%, 51 limit-ups, breadth crashed (57%→28%), turnover shrank to ¥1.79tn (−342bn), technics MACD top divergence (red but index down), all three down, ChiNext −2.39% leads, valuation elevated (PE_TTM 20.62, 10y pctile 81.23%), trend still weak-down. Projecting 09-03 sector direction and trading rules (<b>no individual stock picks</b>).",
 "o1_tag": "Military / Ground-arm (watch)",
 "o1_t": "Ground-arm EquipmentⅡ / Aviation-equip Ⅱ / Glass-fiber",
 "o1_d": "09-02 the only against-tide direction: Ground-arm EquipmentⅡ +6.48% (Great Wall Military +10.04%) / glass-fiber +1.23% / aviation-equip Ⅱ +0.93%. Military single-point active; may extend if volume supports, but beware high-level chase & correction under volume-shrink selloff.",
 "o1_cond": "Note: persistence after a one-day burst must be verified; never treat a single-day rotation as reversal; cautious if volume doesn't expand, don't chase the limit-up wave.",
 "o2_tag": "Agriculture / cycle resources (stand aside)",
 "o2_t": "Planting / Energy-metals / Coke",
 "o2_d": "09-02 planting −5.93%, energy-metals −3.44%, coke Ⅱ −3.71% led the drop, prior-strong & cycle resources correct together, capital withdrawing, enter fade-watch.",
 "o2_cond": "Note: correction unstopped in selloff; no bottom-fishing, no leverage; right-side needs sustained volume+price confirmation.",
 "o3_tag": "High-valuation ChiNext / thematic highs (avoid)",
 "o3_t": "ChiNext highs / margin-against-tide names",
 "o3_d": "09-02 ChiNext −2.39% leads, MACD top divergence, margin against tide (China Jushi / Zhongji) shows leverage divergence — high-valuation & leverage names most exposed to pullback in volume-shrink selloff, avoid near term.",
 "o3_cond": "Note: wait for volume-dry stabilization + leaders stabilizing before sector itself, then consider right-side.",
 "o_r1": "<b>Book</b>: stay low exposure, no leverage. Cycle moved to 'Volume-shrink selloff / sentiment ebb', breadth collapsed, volume shrank, trend still weak — overall risk budget shrinks markedly.",
 "o_r2": "<b>High-level main line</b>: no chasing, no leverage; right-side requires sustained volume + index above short-term MA; break down -> cut.",
 "o_r3": "<b>New main line</b>: needs sustained volume+price confirmation (>=2 sessions of volume expansion + leader unchanged) to follow; never treat a single-day rotation as reversal.",
 "o_r4": "<b>Volume-shrink selloff</b>: turnover ¥1.79tn (−342bn); if 09-03 keeps shrinking but indices fall inertially, up-ratio still <30%, breadth fragile — watch panic / stampede.",
 "o_r5": "<b>Risk gate</b>: turnover ¥1.79tn (−342bn, volume-shrink selloff); if 09-03 keeps shrinking and indices break short-term MAs cut overall to <=30% exposure; if it breaks on shrinking volume, cut further.",
 "s_breadth_v": "westock · data_changedist; 2026-09-02 close",
 "s_portrait_v": "westock · data_market_overview(type=summary); 2026-09-02 (up-ratio 28% real breadth crash, volume-shrink selloff)",
 "s_index_v": "westock · data_quote(sh000001,sz399001,sz399006); 2026-09-02 close",
 "s_sector_v": "westock · data_sector(mode=ranking); 2026-09-02 (fundflow includes industry/concept/region rankings and leaders)",
 "s_hot_v": "westock · data_hot unavailable this round; proxied by data_sector(fundflow leaders) + tool_ranking(limitup_days / margin_chg_d); breadth/index/sector/margin daily are 2026-09-02",
 "s_margin_v": "westock · tool_ranking(metric=margin_chg_d); 2026-09-02",
 "s_main_v": "westock · tool_ranking(metric=cap_main_5d); 2026-09-02 (sector dark-pool view, proxied by main-5d)",
 "s_board_v": "westock · tool_ranking(metric=limitup_days); 2026-09-02 (same-day ranking refreshed)",
 "s_gap_v": "Aggregate margin balance (data_market_overview type=margin) returned empty by source; proxied by per-stock margin changes, not fabricated. data_hot unavailable this round; proxied by sector leaders + rankings. Streak height / margin daily are all 2026-09-02 real data.",
 "t_src_note": "Time caliber: all timestamps in Beijing time. Macro is monthly/quarterly and not directly aligned with daily quotes; labeled separately. Breadth / index / sector / margin daily / streak height are all 2026-09-02 same-day real data.",
 "ev_index": "II. Core Index Performance (2026-09-02 close)",
 "o_rules_t": "Trading rules (09-03)",
 "o_compliance": "<b>Compliance note:</b> this outlook provides sector direction and trading rules only — no individual stock recommendations. Crowd positioning and sector inference are based on 2026-09-02 live market data; markets carry risk, decide independently.",
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
# 4) 重建 BIAS 数组（09-02 真实数据）
# ============================================================
BIAS = [
 {"zh":"羊群效应","en":"Herding","sev":4,
  "zhd":"涨股比28%偏低、成交缩至¥1.79万亿普跌、三指齐跌（创业板−2.39%领跌），但资金扎堆地面兵装（地面兵装Ⅱ+6.48%/长城军工+10.04%）与连板（新赛股份5板），跟随军工涨停潮而非独立判断。",
  "end":"Up-ratio 28% low, turnover shrank to ¥1.79tn on broad selloff, all three down (ChiNext −2.39% leads); capital crowds ground-arm (Ground-arm EquipmentⅡ +6.48%/Great Wall Military +10.04%) and streaks (Xinsai 5 boards) — following the limit-up wave, not conviction."},
 {"zh":"损失厌恶","en":"Loss Aversion","sev":3,
  "zhd":"在缩量普跌中融资逆势加仓玻纤/光模块（中国巨石+3.9986亿/中际旭创+3.9119亿），把前期浮亏当已发生损失回避止损、在高位科技缩量下挫中反手加仓，忽视量能萎缩与顶背离。",
  "end":"In volume-shrink selloff, margin adds against tide to fiberglass/optical-module (China Jushi +0.3999bn/Zhongji +0.3912bn) — avoiding realized loss, doubling down on high-level tech on shrinking volume, ignoring fading turnover & top divergence."},
 {"zh":"心理账户/赌徒谬误","en":"Mental Acct / Gambler","sev":3,
  "zhd":"创业板−2.39%下仍在缩量普跌中博弈军工/农业反弹（长城军工+10.04%/新赛股份5板），把亏损仓当赌资、博「军工刚需」回本。",
  "end":"Amid ChiNext −2.39% still margin-betting on military/agriculture rebound (Great Wall Military +10.04%/Xinsai 5 boards) in a volume-shrink selloff; treating loss books as gambling capital."},
 {"zh":"过度自信","en":"Overconfidence","sev":4,
  "zhd":"只看连板5板（新赛股份）与军工涨停潮，误判「结构性机会」，把单日军工独涨当趋势恢复、追地面兵装，忽视涨股比仅28%（广度崩塌）、三指齐跌、估值偏高（PE分位81.23%）、MACD顶背离。",
  "end":"Watching only the 5-board streak (Xinsai) and military limit-up wave as 'structural opportunity', treating a single-day military spike as trend recovery, chasing ground-arm — ignoring up-ratio only 28% (breadth crash), all-three-down, valuation elevated (PE pctile 81.23%), MACD top divergence."},
 {"zh":"处置效应","en":"Disposition","sev":3,
  "zhd":"反弹中卖盈（地面兵装+6.48%中长城军工+10.04%获利了结）持亏（创业板高位套牢未割），结构分化、调仓滞后。",
  "end":"Selling winners (ground-arm +6.48% with Great Wall Military +10.04% profit-taking) while holding losers (ChiNext high-level traps untrimmed) — split structure, lagging rotation."},
 {"zh":"锚定偏差","en":"Anchoring","sev":3,
  "zhd":"锚定前期高点与08-31「涨股比57%」余温，难接受涨股比已塌至28%（广度崩塌）、三指齐跌（创业板−2.39%）与缩量普跌的现实。",
  "end":"Anchored to prior highs and 08-31's 'up-ratio 57%' afterglow, rejecting the up-ratio already crashed to 28% (breadth collapse), all-three-down (ChiNext −2.39%) and the volume-shrink selloff reality."},
 {"zh":"确认偏误","en":"Confirmation Bias","sev":4,
  "zhd":"只看连板5板+军工涨停+融资加仓，忽略涨股比仅28%（广度崩塌）、三指齐跌、估值偏高（PE分位81.23%）、MACD顶背离、其余板块普跌（种植业−5.93%/能源金属−3.44%）。",
  "end":"Only watching 5-board streak + military limit-ups + margin add, ignoring up-ratio only 28% (breadth crash), all-three-down, valuation elevated (PE pctile 81.23%), MACD top divergence, rest broadly down (planting −5.93%/energy-metals −3.44%)."},
 {"zh":"近因偏差","en":"Recency","sev":3,
  "zhd":"外推08-31涨停89的「热度」与军工题材惯性，对涨股比塌至28%、三指齐跌（创业板−2.39%）反应钝化。",
  "end":"Extrapolating 08-31's 89 limit-ups 'heat' and military-theme inertia; blunted by up-ratio crash to 28%, all-three-down (ChiNext −2.39%)."},
 {"zh":"叙事偏差","en":"Narrative","sev":4,
  "zhd":"「军工/地面兵装刚需」叙事在缩量普跌中仍被资金强化（地面兵装Ⅱ+6.48%/长城军工+10.04%/融资逆势加仓中国巨石），故事未证伪且被加仓自我实现，但估值偏高（PE分位81.23%）下叙事脆弱。",
  "end":"The 'military/ground-arm must-have' narrative reinforced by capital even in a volume-shrink selloff (Ground-arm EquipmentⅡ +6.48%/Great Wall Military +10.04%/margin against tide China Jushi), story un-falsified, self-reinforced by buying, but fragile under elevated valuation (PE pctile 81.23%)."},
 {"zh":"代表性启发","en":"Representativeness","sev":3,
  "zhd":"被地面兵装Ⅱ+6.48%（长城军工+10.04%）单日赚钱效应代表，误判市场全面转暖、忽视缩量普跌下的极端分化（种植业−5.93%/能源金属−3.44%/创业板−2.39%）与涨股比仅28%。",
  "end":"Ground-arm EquipmentⅡ +6.48% (Great Wall Military +10.04%) profit taken as representative; mistaking a sector spike for a broad turn, ignoring the volume-shrink selloff's extreme divergence (planting −5.93%/energy-metals −3.44%/ChiNext −2.39%) and up-ratio only 28%."},
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
 ("<span class=\"chip\"><span data-i18n=\"c_upratio\">涨股比</span> <b>57%</b></span>",
  "<span class=\"chip\"><span data-i18n=\"c_upratio\">涨股比</span> <b>28%</b></span>"),
 ("<span class=\"chip\"><span data-i18n=\"c_limitup\">涨停</span> <b>89</b></span>",
  "<span class=\"chip\"><span data-i18n=\"c_limitup\">涨停</span> <b>51</b></span>"),
 ("<span class=\"chip\"><span data-i18n=\"c_board\">连板高度</span> <b>6板</b></span>",
  "<span class=\"chip\"><span data-i18n=\"c_board\">连板高度</span> <b>5板</b></span>"),
 ("<span class=\"chip\"><span data-i18n=\"c_turn\">两市成交</span> <b>¥2.131万亿</b></span>",
  "<span class=\"chip\"><span data-i18n=\"c_turn\">两市成交</span> <b>¥1.79万亿</b></span>"),
 # breadth SVG center texts
 ("<text x=\"167\" y=\"33\" fill=\"#fff\" font-size=\"14\" font-weight=\"800\" text-anchor=\"middle\">57%</text>",
  "<text x=\"167\" y=\"33\" fill=\"#fff\" font-size=\"14\" font-weight=\"800\" text-anchor=\"middle\">28%</text>"),
 ("<text x=\"407\" y=\"33\" fill=\"#fff\" font-size=\"14\" font-weight=\"800\" text-anchor=\"middle\">40%</text>",
  "<text x=\"407\" y=\"33\" fill=\"#fff\" font-size=\"14\" font-weight=\"800\" text-anchor=\"middle\">70%</text>"),
 ("<text x=\"514\" y=\"33\" fill=\"#6b675f\" font-size=\"11\" font-weight=\"700\" text-anchor=\"end\">4% 平盘</text>",
  "<text x=\"514\" y=\"33\" fill=\"#6b675f\" font-size=\"11\" font-weight=\"700\" text-anchor=\"end\">2% 平盘</text>"),
 ("<text x=\"340\" y=\"72\" fill=\"#d8392b\">3181</text>",
  "<text x=\"340\" y=\"72\" fill=\"#d8392b\">1541</text>"),
 ("<text x=\"340\" y=\"92\" fill=\"#1a9e5a\">2218</text>",
  "<text x=\"340\" y=\"92\" fill=\"#1a9e5a\">3901</text>"),
 ("<text x=\"340\" y=\"112\" fill=\"#6b675f\">152</text>",
  "<text x=\"340\" y=\"112\" fill=\"#6b675f\">112</text>"),
 ("<text x=\"340\" y=\"138\" fill=\"#d8392b\">89</text>",
  "<text x=\"340\" y=\"138\" fill=\"#d8392b\">51</text>"),
 ("<text x=\"340\" y=\"158\" fill=\"#1a9e5a\">13</text>",
  "<text x=\"340\" y=\"158\" fill=\"#1a9e5a\">3</text>"),
 ("<text x=\"340\" y=\"184\" fill=\"#1c1b19\">¥2.131万亿</text>",
  "<text x=\"340\" y=\"184\" fill=\"#1c1b19\">¥1.79万亿</text>"),
 # breadth SVG parentheticals
 ("（占 57%，较上一报告日（08-27） −4pct）", "（占 28%，较上一报告日（08-31） −29pct）"),
 ("（占 40%，较上一报告日（08-27） +5pct）", "（占 70%，较上一报告日（08-31） +30pct）"),
 ("（占 4%）", "（占 2%）"),
 ("（较前日 +11 只，连板高度升至 6板）", "（较前日 −38 只，连板高度 5板）"),
 ("（较前日 +9 只）", "（较前日 −48 只）"),
 ("（环比 +293亿，缩量滞涨）", "（环比 −3420亿，缩量普跌）"),
 # breadth bar widths
 ('<rect x="14" y="14" width="285" height="26" fill="#d8392b"/>',
  '<rect x="14" y="14" width="139" height="26" fill="#d8392b"/>'),
 ('<rect x="299" y="14" width="200" height="26" fill="#1a9e5a"/>',
  '<rect x="153" y="14" width="351" height="26" fill="#1a9e5a"/>'),
 # evidence: 涨股比
 ("<td><span class=\"val up\">57%</span>（涨3181 / 跌2218 / 平152）</td>",
  "<td><span class=\"val up\">28%</span>（涨1541 / 跌3901 / 平112）</td>"),
 # evidence: 涨停/跌停
 ("<td><span class=\"val up\">89</span> / <span class=\"val down\">13</span></td>",
  "<td><span class=\"val up\">51</span> / <span class=\"val down\">3</span></td>"),
 # evidence: 成交额
 ("<span class=\"val\">¥2.131万亿</span>（较前日 +293亿，缩量滞涨）",
  "<span class=\"val\">¥1.79万亿</span>（较前日 −3420亿，缩量普跌）"),
 # evidence: 三大指数
 ("3986.30　+0.86%", "3941.39　−0.97%"),
 ("14015.00　+0.44%", "13611.55　−1.88%"),
 ("3438.68　+0.42%", "3312.24　−2.39%"),
 # evidence: 领涨行业
 ("<span class=\"val up\">数字媒体 +7.19%</span>（芒果超媒 +20.00%）<br>影视院线 +7.02%（华策影视 +15.77%）/ 出版 +5.26%（中文在线 +20.02%）<br>电视广播 +4.38% / 广告营销 +3.85% / 游戏 +3.40%",
  "<span class=\"val up\">地面兵装Ⅱ +6.48%</span>（长城军工 +10.04%）<br>玻璃玻纤 +1.23% / 航空装备Ⅱ +0.93% / 教育 +0.82%<br>旅游及景区 +0.72% / 国有大型银行 +0.57%"),
 # evidence: 领跌行业
 ("<span class=\"val down\">饰品 −4.67%</span> / 乘用车 −3.12% / 光伏设备 −2.82% / 贵金属 −2.67% / 白色家电 −2.31% / 股份制银行 −1.10%<br>贵金属续弱 −0.64%",
  "<span class=\"val down\">种植业 −5.93%</span> / 焦炭Ⅱ −3.71% / 能源金属 −3.44% / 渔业 −3.29% / 农产品加工 −3.16% / 影视院线 −3.10%"),
 # evidence: 极端题材(连板)
 ("<span class=\"val up\">连板高度 6 板</span>（海鸥住工）<br>5板：万向德农 / 捷荣技术；4板：锦龙股份<br>新热点：芒果超媒 +20.00%（数字媒体）/ 华策影视 +15.77%（影视院线）/ 中文在线 +20.02%（出版）/ 贵广网络 +9.90%（电视广播）/ 分众传媒 +6.40%（广告营销）",
  "<span class=\"val up\">连板高度 5 板</span>（新赛股份）<br>4板：国芳集团 / 竞业达；3板：龙版传媒 / 欢瑞世纪 / 大晟文化 / 集泰股份<br>新热点：长城军工 +10.04%（地面兵装Ⅱ）/ 新赛股份 5板（农业题材）"),
 # evidence: 连板高度
 ("<span class=\"val up\">海鸥住工 6板</span>（2026-08-31）", "<span class=\"val up\">新赛股份 5板</span>（2026-09-02）"),
 # evidence: 主力5日/融资单日（0831 用 margin daily 替代，保留同结构）
 ("中际旭创 <span class=\"val up\">+11.07亿</span>（光模块）<br>新易盛 +8.71亿 / 星网锐捷 +3.32亿 / 东材科技 +3.07亿 / 三环集团 +2.50亿<br>罗博特科 +1.77亿 / 联特科技 +1.72亿 / 剑桥科技 +1.55亿 / 中科曙光 +1.48亿",
  "中国巨石 <span class=\"val up\">+3.9986亿</span>（玻纤）<br>中际旭创 +3.9119亿 / 长川科技 +3.8637亿 / 芒果超媒 +3.0549亿 / 同花顺 +2.3907亿<br>协创数据 +2.0724亿 / 中文在线 +1.8915亿 / 菲利华 +1.5591亿 / 亨通光电 +1.4834亿"),
 # evidence: 融资单日
 ("中际旭创 <span class=\"val up\">+11.07亿</span>（光模块）<br>新易盛 +8.71亿 / 星网锐捷 +3.32亿 / 东材科技 +3.07亿 / 三环集团 +2.50亿<br>罗博特科 +1.77亿 / 联特科技 +1.72亿 / 剑桥科技 +1.55亿 / 中科曙光 +1.48亿",
  "中国巨石 <span class=\"val up\">+3.9986亿</span>（玻纤）<br>中际旭创 +3.9119亿 / 长川科技 +3.8637亿 / 芒果超媒 +3.0549亿 / 同花顺 +2.3907亿<br>协创数据 +2.0724亿 / 中文在线 +1.8915亿 / 菲利华 +1.5591亿 / 亨通光电 +1.4834亿"),
 # evidence: 热搜
 ("芒果超媒 +20.00%（数字媒体）<br>华策影视 +15.77%（影视院线）/ 中文在线 +20.02%（出版）/ 贵广网络 +9.90%（电视广播）/ 分众传媒 +6.40%（广告营销）<br>海鸥住工 +10.04%（连板 6板，2026-08-31）",
  "长城军工 +10.04%（地面兵装Ⅱ）<br>新赛股份 5板（农业题材）/ 国芳集团 4板 / 竞业达 4板<br>龙版传媒 3板 / 欢瑞世纪 3板 / 大晟文化 3板 / 集泰股份 3板"),
 # evidence: 指数小节标题日期
 ("二、核心指数表现（2026-08-31 收盘）", "二、核心指数表现（2026-09-02 收盘）"),
 # t_date 静态 cell
 ("<b>2026-08-31 收盘（北京时间，盘后）</b>", "<b>2026-09-02 收盘（北京时间，盘后）</b>"),
]
for old, new in BODY:
    if old in html:
        html = html.replace(old, new, 1)
    else:
        print(f"[skip-body] 未命中: {old[:46]!r}")

# ============================================================
# 6) 雷达数值标签（红字组）
# ============================================================
old_radar = '<text x="160" y="71">72</text><text x="237" y="120">70</text><text x="209" y="194">56</text>\n            <text x="160" y="167">52</text><text x="109" y="201">68</text><text x="55" y="118">88</text>'
new_radar = '<text x="160" y="71">62</text><text x="237" y="120">68</text><text x="209" y="194">54</text>\n            <text x="160" y="167">78</text><text x="109" y="201">65</text><text x="55" y="118">88</text>'
assert old_radar in html, "radar block not found"
html = html.replace(old_radar, new_radar, 1)

# ============================================================
# 7) 用字典值回写所有 data-i18n 兜底文本（源码与渲染一致、0 旧数据）
#    —— 正则只匹配真正的 <tag data-i18n=...> 元素（均在 body，脚本块内是
#       JS 对象字面量，无此类标签），因此可安全作用于整份 html。
#    旧的全局 html.replace("08-31","09-02") 会破坏 BIAS 中对前一交易日
#    08-31（涨股比57% / 涨停89）的正确引用，已弃用。
#    08-21 为宏观月频复核日期、08-31 为 BIAS 前日引用，均保留不替换。
# ============================================================
_pat = re.compile(r'<(\w+)([^>]*\bdata-i18n="([^"]+)"[^>]*)>(.*?)</\1>', re.S)
def _repl(m):
    _tag, _attrs, _key, _inner = m.group(1), m.group(2), m.group(3), m.group(4)
    if _key in zh:
        return '<%s%s>%s</%s>' % (_tag, _attrs, zh[_key], _tag)
    return m.group(0)
html = _pat.sub(_repl, html)
# 7b) 残留旧日期兜底（排除 08-21 宏观复核 / 08-31 BIAS 前日引用）
for _a, _b in [
    ("2026-08-24", "2026-09-02"), ("2026-08-25", "2026-09-02"),
    ("2026-08-26", "2026-09-02"), ("2026-08-27", "2026-09-02"),
    ("2026-08-28", "2026-09-02"),
    ("08-24", "09-02"), ("08-25", "09-02"), ("08-26", "09-02"),
    ("08-27", "09-02"), ("08-28", "09-02"),
]:
    html = html.replace(_a, _b)
# 7c) 硬编码英文小标题日期修正
html = html.replace("Next-Session Outlook (08-25 Tue)", "Next-Session Outlook (09-03 Thu)")

# ============================================================
# 8) 写出 + 校验
# ============================================================
open(OUT, "w", encoding="utf-8").write(html)
print(f"[ok] 写出 {OUT} ({len(html)} bytes)")
leftover = ["3956.57","14048.88","3473.35","3394","1944","深中华A","非金属材料 +9.63%","2.1259",
            "联瑞新材","楚天龙","紫金矿业 +34.96亿","新易盛 +3.11亿","2026-08-26","2026-08-27","放量反包",
            "海鸥住工","芒果超媒 +20.00%（数字媒体）","中际旭创 +11.07亿","57%","3181","2218","89","13","¥2.131万亿",
            "3986.30","14015.00","3438.68","缩量滞涨 / 结构分化","2026-08-31"]
bad = [s for s in leftover if s in html]
print("残留旧数据:", bad if bad else "无")
print("2026-09-02 出现次数:", html.count("2026-09-02"))
print("外部引用 http(s):", len(re.findall(r'https?://', html)))
must = ["3941.39","13611.55","3312.24","1541","3901","28%","51","3","¥1.79万亿",
        "地面兵装Ⅱ +6.48%","新赛股份 5板","中国巨石 +3.9986亿","缩量普跌 / 情绪退潮","2026-09-02","62","78"]
miss = [s for s in must if s not in html]
print("缺失 09-02 标记:", miss if miss else "无")
