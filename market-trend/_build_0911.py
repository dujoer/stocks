# -*- coding: utf-8 -*-
"""群体心理风险雷达 2026-09-11：以 09-10 页面为模板，覆盖全部动态内容。

数据来源（全部为 2026-09-11 真实收盘；两融/主力5日接口降级，已如实标注未编造）：
  广度 = westock data_changedist(type=0)（与 iFinD 涨停 40 只交叉吻合）
  指数/技术 = iFinD get_security_indicators + westock data_kline 自算
  （MA/MACD/KDJ/BOLL/RSI 与 westock 原生口径核验偏差 0.0000）
  板块 = westock data_sector；连板 = iFinD 涨停名单 + 历史 LimitUpDays 递推
  估值 = iFinD PE_TTM 20.09（52周分位 33.9%；3/5/10 年分位缺，未编造）
"""
import os, re

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "..", "web", "psychology", "crowd-psychology-risk-radar-20260910.html")
OUT = os.path.join(HERE, "..", "web", "psychology", "crowd-psychology-risk-radar-20260911.html")

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
# 1) 09-11 叙述覆盖（中文）—— 所有动态键均覆盖，避免残留 09-10 文案
# ============================================================
ZH = {
 "t_headline_sub": "2026-09-11 · 收盘",
 "hk_stage": "阶段定性", "hv_stage": "<b>放量普跌 · 恐慌扩散</b>（09-11）",
 "hk_upratio": "涨股比", "hv_upratio": "<b>12%</b>（前次 09-10 17% · ↓ 5pct，广度续崩）",
 "hk_lim": "涨停 / 跌停", "hv_lim": "<b>40</b> / <b>21</b>（跌停由 2 暴增至 21，恐慌确认）",
 "hk_amt": "成交额", "hv_amt": "<b>¥1.97万亿</b>（放量普跌，为 5 日均 105.3%、20 日均 97.8%）",
 "hk_cycle": "情绪周期", "hv_cycle": "<b>放量普跌 · 恐慌扩散</b>",
 "hk_risk": "风险等级", "hv_risk": "<b class=\"hl-risk\">高</b>（09-10 预设触发条件全部应验）",
 "hk_flag": "关键提示",
 "hv_flag": "涨股比 17%→<b>12%</b>、跌停 2→<b>21</b>（>10 触发线）、上证 −1.18% 跌破 MA60（3941.72）且盘中击穿 BOLL 下轨（3866.35）——09-10 页预设的「退潮加速」触发条件<b>全部应验</b>；成交反放量至 ¥1.97万亿（5 日均 105.3%）＝<b>放量普跌、恐慌出清</b>；927 个板块仅 33 收红、733 呈主力「出货」；两融与主力5日数据降级期暂缺，未编造。",
 "tk1": "阶段定性", "tv1": "A股 09-11 由 09-10「缩量普跌 · 退潮加速」恶化至「<b>放量普跌 · 恐慌扩散</b>」：涨股比再腰斩至 <b>12%</b>（643涨 / 4870跌 / 平49，由 17% 再落 −5pct），涨停 <b>40</b>（38→40 持平微增）、跌停 <b>21</b>（由 2 暴增 19 只，越过 09-10 预设的 10 只警戒线），下跌家数占比 88.3%；上证 <b>−1.18%</b>（3888.11，盘中最低 3852.03）跌破 MA5/10/20/60 全部均线，盘中击穿 BOLL 下轨（3866.35）收于下轨附近；深成 <b>−1.08%</b>（13471.26）、创业板 <b>−0.49%</b>（3322.04）同步收跌。与 09-10 的关键差异：<b>成交放量</b>至 ¥1.97万亿（5 日均 105.3%、环比 +3200亿）——缩量阴跌转为放量恐慌，出清特征明确。风险等级由中上调至<b>高</b>。",
 "tk2": "广度崩塌加剧", "tv2": "涨股比 <b>12%</b>（前次 17% ↓5pct）· 涨停 <b>40</b>（38→40）· 跌停 <b>21</b>（2→21，恐慌确认）· 成交 <b>¥1.97万亿</b>（5 日均 105.3%、10 日均 103.2%、20 日均 97.8%，放量）——与 09-10「阴跌式退潮」不同，跌停 21 只 + 放量组合表明<b>恐慌性抛售已现</b>；927 个板块中仅 33 个收红（涨 33 / 跌 892），733 个板块呈主力「出货」行为，广度崩塌叠加行为恶化。",
 "tk3": "技术破位", "tv3": "上证 <b>−1.18%</b>（3888.11）收盘低于 MA5（3929.45）/ MA10（3942.71）/ MA20（3934.80）/ MA60（3941.72）全部均线，盘中最低 3852.03 击穿 BOLL 下轨（3866.35）、收于下轨附近；MACD <b>−7.23</b>（DIF 1.80 / DEA 5.41，绿柱由 09-10 的 +0.08 转负放大，死叉确认）；RSI6 <b>28.43</b>（接近超卖）、KDJ_J 15.2（低位）——<b>破位与超卖并存</b>：趋势已坏，但短线超卖带来技术性反抽的可能；深成 −1.08%、创业板 −0.49%（相对抗跌，此前已先跌）。",
 "tk4": "板块结构", "tv4": "<b>地面兵装Ⅱ +4.44%</b>（主力净流入 +50.22亿，行为「抢筹」）领涨，<b>玻璃玻纤 +2.63%</b> / <b>元件 +1.80%</b>（主力 +638.35亿）/ <b>通信设备 +1.66%</b>（主力 +839.89亿，全行业第一）跟随——<b>军工 + 电子硬科技是恐慌日唯一有主力真实承接的方向</b>；<b>工业金属 −5.04%</b> 领跌（表面主力净流入 +261亿，但散户流入 +304亿更多，暗盘 −42.6亿 → 实为「出货」），<b>农产品加工 −4.36%</b> / <b>渔业 −4.34%</b> 跟随——资源与前期题材在恐慌中集中补跌。",
 "tk5": "连板结构", "tv5": "连板共 <b>40 只</b>（较前日持平），最高板维持 <b>4 板</b>但龙头更替：<b>瑞尔特</b>接棒（桂林旅游退坡），3板鼎信通讯 / 闽东电力，2板凯盛新能 / 超声电子 / 九鼎新材 / 中新赛克——<b>高度未降但龙头一日一换、题材快速轮动</b>，投机资金在恐慌中仍留守少数筹码紧凑标的，赚钱效应极度收窄。",
 "tk6": "资金：两融暂缺", "tv6": "两融数据接口降级（service error），<b>未编造</b>；从可见信号看，主力资金在恐慌日呈现极端分化：通信设备 +839.89亿、元件 +638.35亿（电子硬科技承接）与地面兵装Ⅱ +50.22亿（军工抢筹）集中流入，而 733 个板块「出货」、资源类（工业金属）散户接盘——<b>资金弃中庸、抢两端：硬科技与军工逆势吸筹，其余普跌</b>；杠杆风险因两融缺失无法确认，恐慌放量下保持谨慎。",
 "tk7": "估值 / 风格", "tv7": "PE_TTM <b>20.09</b>（52周分位 <b>33.9%</b>，PB 1.78、股息率 2.02%；3/5/10 年长周期分位缺，未编造）——随下跌小幅消化（09-10 口径 20.44）；风格上防御显著占优：全指价值 20 日 <b>+3.19%</b> vs 全指成长 20 日 <b>−4.27%</b>（差 7.5pct），沪深300 5日 −0.83% / 中证1000 5日 −1.08%——<b>价值/成长的极端分化是本轮调整的主轴</b>，恐慌日进一步强化。",
 "tk8": "情绪周期", "tv8": "由 09-10「缩量普跌 · 退潮加速」恶化至「<b>放量普跌 · 恐慌扩散</b>」：涨股比 17%→12%、跌停 2→21（触发线 10 被越过）、上证跌破 MA60 且盘中破布林下轨，成交由缩转放（环比 +3200亿）——09-10 页预设的「退潮进一步加速」条件<b>全部应验</b>，情绪周期进入<b>恐慌出清段</b>；历史上恐慌放量常对应阶段性情绪极值，但右侧确认仍需量价信号，风险等级上调至<b>高</b>。",
 "t_tldr_text": "A股 09-11 呈现「放量普跌 · 恐慌扩散」：涨股比 17%→12%（643涨/4870跌/平49），涨停 38→40、跌停 2→21（越过 09-10 预设 10 只警戒线），下跌家数占比 88.3%；上证 −1.18%（3888.11）跌破全部均线、盘中击穿布林下轨（3852.03 vs 3866.35），MACD 绿柱转负放大（−7.23）、RSI6 28.43 接近超卖；深成 −1.08%（13471.26）、创业板 −0.49%（3322.04）。成交放量至 ¥1.97万亿（5 日均 105.3%、环比 +3200亿）——缩量阴跌转为放量恐慌。地面兵装Ⅱ +4.44%（主力 +50.22亿 抢筹）领涨，通信设备 +1.66%（主力 +839.89亿）/ 元件 +1.80%（+638.35亿）跟随——军工+电子硬科技是唯一有主力承接的方向；工业金属 −5.04% 领跌（散户接盘、实为出货），农产品加工 −4.36% / 渔业 −4.34% 跟随。927 板块仅 33 收红、733 出货。连板 40 只持平、4板瑞尔特（新龙头）。两融与主力5日数据降级期暂缺（未编造）。估值 PE_TTM 20.09（52周分位 33.9%）。全指价值 20日 +3.19% vs 全指成长 −4.27%，防御/成长极端分化。09-10 预设触发条件全部应验，风险等级上调至高。",
 "t_risk": "风险等级", "t_risk_hi": "高",
 "c_upratio": "涨股比", "c_limitup": "涨停", "c_board": "连板高度", "c_pe": "估值 PE分位", "c_pmi": "制造业PMI", "c_turn": "两市成交",
 "t_sec_bias": "行为偏差热力图", "t_cycle": "情绪周期定位（六阶段）",
 "r1": "绝望", "r2": "怀疑", "r3": "乐观", "r4": "狂热", "r5": "焦虑", "r6": "自满",
 "t_cycle_note": "注：上方「恐慌 / 退潮」为实时群体心理定位（放量普跌 · 恐慌扩散）——09-11 涨跌分布（涨股比 12%、涨停 40、跌停 21、成交 ¥1.97万亿）显示恐慌确认：跌停暴增越过 09-10 预设警戒线（10 只）、上证破位全部均线且盘中击穿布林下轨、成交放量（5 日均 105.3%）＝恐慌出清特征；两融数据暂缺、估值分位随跌消化。若 09-14 跌停回落至 10 只以内且涨股比回升至 20% 上方，恐慌缓和；若跌停继续扩大至 30 只以上或上证收于 3850 下方，恐慌升级。",
 "t_leg": "严重度（由数据综合映射）", "t_bias_note": "注：偏差严重度为基于下方真实数据的模型映射（1=低，5=高），用于呈现群体心理的脆弱点分布，并非对个股的买卖建议。",
 "t_sec_radar": "风险雷达",
 "t_radar_note": "六维风险读数（0–100，由下方真实数据综合映射，越高代表该维度群体脆弱性越强）：拥挤度 64 / 融资 68 / 换手 50 / 广度 90 / 媒体 42 / 估值 85。广度由 82 升至 90（09-11 涨股比 17%→12%、下跌家数 88.3%、跌停 21 只恐慌扩散、927 板块仅 33 收红，广度脆弱性逼近极值）；换手由 44 升至 50（成交放量至 ¥1.97万亿、5 日均 105.3%，恐慌换手放大）；融资由 66 升至 68（两融数据降级暂缺、杠杆无法确认，但放量恐慌 + 破位下杠杆踩踏风险继续上升，谨慎上调）；拥挤度由 62 升至 64（资金极端收敛至通信设备/元件/军工等少数承接方向，733 板块出货，集中度上升）；媒体由 46 降至 42（跌停 21 只、三大指数全跌、破位失守，情绪温度降至冰点附近）；估值由 87 降至 85（PE_TTM 20.44→20.09 随跌小幅消化，52周分位 33.9%，长周期分位缺）。整体脆弱性由「广度 + 恐慌换手」主导——恐慌出清段，广度逼近极值是最主要风险源，估值风险边际缓和。",
 "ax_crowd": "拥挤度", "ax_margin": "融资", "ax_turn": "换手", "ax_breadth": "广度", "ax_media": "媒体情绪", "ax_val": "估值",
 "b_up": "上涨", "b_down": "下跌", "b_flat": "平盘", "b_limitup": "涨停", "b_limitdn": "跌停", "b_amt": "成交额",
 "t_breadth_note": "涨股比 17%→12%、涨停 38→40（持平微增）、跌停 2→21（恐慌确认），下跌家数占比 88.3%；成交 ¥1.97万亿（5 日均 105.3%、环比 +3200亿）放量普跌。三大指数全跌且技术破位：上证 −1.18%（3888.11，跌破 MA5/10/20/60，盘中击穿布林下轨 3866.35）/ 深成 −1.08%（13471.26）/ 创业板 −0.49%（3322.04）；地面兵装Ⅱ +4.44%（主力 +50.22亿 抢筹）领涨，工业金属 −5.04%（散户接盘实为出货）领跌——927 板块仅 33 收红，733 呈主力「出货」。",
 "th_metric": "指标", "th_read": "真实读数", "th_interp": "行为金融解读",
 "ev_market": "一、市场广度与总览",
 "ev_upratio": "涨股比",
 "ev_upratio_i": "由 17% 降至 12%（−5pct），涨 643 / 跌 4870 / 平 49，参与度进一步塌陷；跌停 21 只（2→21）越过警戒线，由「阴跌式退潮」升级为「放量恐慌出清」",
 "ev_limit": "涨停 / 跌停",
 "ev_limit_i": "涨停 40（38→40 持平微增）、跌停 21（2→21 暴增 19 只，越过 09-10 预设 10 只警戒线），连板高度 4 板但龙头更替（瑞尔特接棒）——投机热度高度钝化、轮动极快",
 "ev_amount": "两市成交额",
 "ev_amount_i": "量能 ¥1.97万亿（5 日均 105.3%、10 日均 103.2%、20 日均 97.8%，环比 +3200亿）——由连续缩量转为放量，恐慌性出清特征：下跌由「阴跌磨损」转为「集中抛售」",
 "ev_index": "二、核心指数表现（2026-09-11 收盘）",
 "ev_sh": "上证指数",
 "ev_sh_i": "−1.18%（3888.11，盘中最低 3852.03），收盘跌破 MA5（3929.45）/ MA10（3942.71）/ MA20（3934.80）/ MA60（3941.72）全部均线，盘中击穿 BOLL 下轨（3866.35）收于下轨附近；MACD −7.23（DIF 1.80 / DEA 5.41，绿柱转负放大，死叉确认）、RSI6 28.43 接近超卖、KDJ_J 15.2；PE_TTM 20.09（52周分位 33.9%，长周期分位缺）",
 "ev_sz": "深证成指",
 "ev_sz_i": "深成 −1.08%（13471.26），跟随破位下行，中期弱势加深",
 "ev_cyb": "创业板指",
 "ev_cyb_i": "创业板 −0.49%（3322.04）相对抗跌（此前已先跌），成长风格内部出现分化（硬科技元件/通信获主力承接）",
 "ev_sector": "三、板块排行与主线",
 "ev_secup": "领涨行业",
 "ev_secup_i": "地面兵装Ⅱ +4.44%（主力净流入 +50.22亿，行为「抢筹」）领涨，玻璃玻纤 +2.63% / 元件 +1.80%（主力 +638.35亿）/ 通信设备 +1.66%（主力 +839.89亿，全行业第一）跟随——军工 + 电子硬科技是恐慌日唯一有主力真实承接的方向，927 个板块仅 33 个收红",
 "ev_secdn": "领跌行业",
 "ev_secdn_i": "工业金属 −5.04% 领跌（表面主力净流入 +261亿，但散户流入 +304亿更多，暗盘 −42.6亿 → 实为「出货」）/ 农产品加工 −4.36% / 渔业 −4.34%——资源与前期题材在恐慌中集中补跌，733 个板块呈「出货」行为",
 "ev_board": "极端题材",
 "ev_board_i": "连板共 40 只（持平），最高板 4板（瑞尔特，新龙头接棒桂林旅游）；3板鼎信通讯 / 闽东电力——高度持平但龙头一日一换，题材快速轮动，赚钱效应极度收窄",
 "ev_flow": "四、资金：连板 / 主力 / 两融",
 "ev_height": "连板高度",
 "ev_height_i": "高度 4板（瑞尔特，2026-09-11 收盘，新龙头）；题材以卫浴出海 + 电子（鼎信通讯/超声电子）+ 电力（闽东电力）为主，恐慌日筹码紧凑标的成避险池",
 "ev_main": "主力5日净流入TOP",
 "ev_main_i": "主力5日净流入数据降级期无法更新（westock tool_ranking service error，09-09 口径沿用、未编造）；当日可见信号：主力单日极端分化——通信设备 +839.89亿 / 元件 +638.35亿 / 地面兵装Ⅱ +50.22亿 集中流入，733 板块「出货」；两融数据暂缺，未编造。",
 "ev_margin": "融资单日变动TOP",
 "ev_margin_i": "两融数据接口降级（service error），融资单日变动与两融余额均暂缺，<b>未编造</b>；放量恐慌 + 技术破位下，杠杆踩踏风险无法确认，谨慎对待——若两融余额在恐慌日显著下降，反而利于后续出清。",
 "ev_hot": "热搜 / 领涨TOP",
 "ev_hot_i": "恐慌日热点极度收敛：瑞尔特 4板（卫浴出海）/ 地面兵装Ⅱ +4.44%（主力 +50.22亿 抢筹）/ 通信设备 +1.66%（主力 +839.89亿）/ 元件 +1.80%（+638.35亿）；防御与硬科技双主线，与「全指价值 20日 +3.19% vs 全指成长 −4.27%」的风格分化一致",
 "ev_margintotal": "市场两融余额",
 "ev_margintotal_i": "缺口：聚合两融余额与融资单日变动接口降级（service error），已如实标注、未编造；涨跌分布 / 指数 / 成交额 / 板块 / 连板梯队均为 2026-09-11 真实收盘，主力5日净流入为 09-09 口径（降级期无法更新）",
 "ev_macro": "五、核心宏观指标",
 "ev_pmi": "制造业PMI（7月）",
 "ev_pmi_i": "基本面收缩，与「高估值 + 恐慌破位」共振放大下行压力；非制造业新订单偏弱",
 "ev_capu": "产能利用率（Q2）",
 "ev_capu_i": "实物经济动能走弱，价格缺乏业绩支撑",
 "ev_cpi": "CPI（7月）",
 "ev_cpi_i": "低通胀、需求偏弱，难证景气全面复苏",
 "ev_social": "社融（7月）",
 "ev_social_i": "信用需求弱，资金绕道股市 = 流动性驱动特征，恐慌日流动性预期同样承压",
 "ev_m1m2": "M1-M2 剪刀差",
 "ev_m1m2_i": "活钱偏弱，资金空转，典型后周期现象",
 "ev_yield": "10Y 国债收益率",
 "ev_yield_i": "极低无风险利率，既支撑估值也反映增长担忧",
 "ev_lpr": "LPR",
 "ev_lpr_i": "宽松基调未变",
 "t_ev_note": "数据口径：宏观指标多截至 2026-07（月频）或沿用前期值；涨跌分布 / 指数 / 成交额 / 板块 / 连板梯队均为 2026-09-11 真实收盘（广度来自 data_changedist 替代源、指数/技术来自 iFinD+自算，与 westock 原生口径核验偏差 0.0000）。估值 PE_TTM 20.09 为 2026-09-11 当日 iFinD 口径（52周分位 33.9%，长周期分位缺）；两融与主力5日降级期暂缺，已如实标注未编造。详见末尾「数据来源与日期口径」。",
 "t_sec_risk": "风险分层",
 "rc1_tag": "红线区 · 恐慌出清 + 技术破位（杠杆数据暂缺）",
 "rc1_t": "放量恐慌 + 全面破位（杠杆暂缺）",
 "rc1_d": "09-11 放量普跌（跌停 21 只、下跌 88.3%、成交 5 日均 105.3%）+ 上证跌破全部均线并盘中击穿布林下轨 + MACD 绿柱转负放大——09-10 预设的「退潮加速」触发条件全部应验；两融缺失无法确认杠杆，但放量恐慌下杠杆踩踏风险最高——风险等级上调至高，仓位纪律优先。",
 "rc1_rep": "代表：两融集中且已破位的高位主线 / 资源类（工业金属 −5.04%，散户接盘实为出货）/ 农业链（农产品加工 −4.36%、渔业 −4.34%）",
 "rc1_cond": "条件框架：严格执行 09-10 页预设纪律（触发即降仓至 ≤3 成）；不加杠杆、不抄正在下跌的刀；以「跌停回落至 10 只以内 + 涨股比回升 20% 上方」为恐慌缓和的最低确认。",
 "rc2_tag": "黄线区 · 恐慌出清与超卖的博弈",
 "rc2_t": "恐慌扩散 vs 超卖反抽",
 "rc2_d": "上证 RSI6 28.43 接近超卖、KDJ_J 15.2 低位、创业板相对抗跌——技术性反抽条件在积累；但放量恐慌的惯性通常需要 1–2 日消化，且 MACD 绿柱刚转负放大、中期趋势已坏，反抽大概率是弱势修复而非反转。",
 "rc2_rep": "代表：创业板（−0.49% 抗跌）/ 超跌硬科技（元件/通信设备获主力承接）/ 前期超跌题材",
 "rc2_cond": "条件框架：反抽不追、以观察为主；若反抽缩量（量能回落至 5 日均下方）则视为弱反弹，警惕二次探底；右侧确认 = 放量收复 MA5/MA10 且跌停清零。",
 "rc3_tag": "绿线区 · 军工 + 硬科技（主力真实承接）",
 "rc3_t": "军工 / 电子硬科技逆势吸筹",
 "rc3_d": "地面兵装Ⅱ +4.44%（主力 +50.22亿 抢筹）、通信设备 +1.66%（主力 +839.89亿，全行业第一）、元件 +1.80%（主力 +638.35亿）——恐慌日唯一有主力真实承接的方向；全指价值 20日 +3.19% vs 全指成长 −4.27% 的极端分化下，硬科技成为资金「弃中庸、抢两端」的进攻端。",
 "rc3_rep": "代表：地面兵装Ⅱ（抢筹）/ 通信设备 / 元件 / 玻璃玻纤（建仓）",
 "rc3_cond": "条件框架：仅作观察与结构跟踪，恐慌日不追高；确认信号 = 该方向在指数企稳后仍保持主力净流入且换手不萎缩；若恐慌加剧其补跌，则确认全线出清。",
 "t_sec_outlook": "下个交易日（09-14 周一）展望",
 "o_logic": "研判逻辑（基于 09-11 收盘 + 群体心理定位）",
 "o_logic_text": "由 09-11 的「放量普跌 · 恐慌扩散」延伸：09-10 页预设触发条件全部应验（跌停 21>10、上证破 MA60），情绪周期进入恐慌出清段——涨股比 12%、跌停 21、成交放量至 ¥1.97万亿（5 日均 105.3%）、上证破全部均线且盘中破布林下轨，但 RSI6 28.43 接近超卖、军工/硬科技获主力真实承接。基于此推演 09-14 的板块方向与交易规则（<b>不涉及具体个股推荐</b>）。",
 "o1_tag": "军工 / 硬科技承接方向（观察）",
 "o1_t": "地面兵装Ⅱ / 通信设备 / 元件 / 玻璃玻纤",
 "o1_d": "09-11 恐慌日唯一获主力真实承接的方向（地面兵装Ⅱ 抢筹 +50.22亿、通信设备 +839.89亿、元件 +638.35亿）；若恐慌缓和，该方向大概率率先企稳。",
 "o1_cond": "注意：恐慌日收红 ≠ 避险港，若恐慌升级（跌停 >30）其补跌将确认全线出清；观察「指数企稳后主力净流入是否延续」，不追恐慌日涨幅。",
 "o2_tag": "资源 / 前期题材（回避）",
 "o2_t": "工业金属 / 农业链 / 前期高位主线",
 "o2_d": "工业金属 −5.04% 且散户接盘（暗盘 −42.6亿 出货）、农产品加工 −4.36% / 渔业 −4.34% 延续退潮；733 个板块呈「出货」——恐慌中流动性最差的板块抛压最重。",
 "o2_cond": "注意：散户接盘型下跌（暗盘为负）通常有第二段惯性下探；不抢反弹，等待暗盘转正或缩量止跌信号。",
 "o3_tag": "恐慌缓和信号（观望）",
 "o3_t": "跌停回落 / 涨股比修复 / 超卖反抽",
 "o3_d": "09-11 恐慌确认（跌停 21、涨股比 12%），但 RSI6 28.43 接近超卖、KDJ_J 15.2——技术性反抽条件在积累；观察 09-14 是否出现「跌停回落至 10 只以内 + 涨股比回升至 20% 上方」的缓和信号。",
 "o3_cond": "注意：恐慌出清段不预判底部；反抽缩量视为弱反弹（警惕二次探底）；右侧确认 = 放量收复 MA5/MA10（3929/3943）且跌停清零，此前仓位纪律优先。",
 "o_rules_t": "交易规则（09-14）",
 "o_r1": "<b>仓位</b>：执行 09-10 预设纪律——触发条件已应验，<b>仓位降至 ≤3 成</b>，不加杠杆；恐慌出清段保住本金优先。",
 "o_r2": "<b>恐慌缓和确认</b>：跌停回落至 10 只以内且涨股比回升至 20% 上方，方视为恐慌缓和；若跌停继续扩大至 30 只以上或上证收于 3850 下方，视为恐慌升级，进一步压缩风险敞口。",
 "o_r3": "<b>主线参与</b>：军工/硬科技承接方向仅作结构观察（主力净流入是否延续），不追恐慌日涨幅；资源/农业链等散户接盘型下跌回避，等待暗盘转正。",
 "o_r4": "<b>回避清单</b>：工业金属等散户接盘板块、农业链退潮方向、两融集中且已破位的高位主线、连板高标接力（龙头一日一换、轮动极快）。",
 "o_r5": "<b>风控</b>：反抽缩量视为弱反弹、警惕二次探底；右侧确认 = 放量收复 MA5/MA10 且跌停清零；两融数据恢复前不加重杠杆。",
 "o_compliance": "<b>合规说明：</b>本展望仅给出板块方向与交易规则，不涉及具体个股推荐；群体心理定位与板块推断基于 2026-09-11 真实行情数据，市场有风险，决策须独立。",
 "t_sec_source": "数据来源与日期口径",
 "s_breadth": "涨跌分布 / 总览",
 "s_breadth_v": "westock · data_changedist(type=0)（market_overview 降级期替代源，与 iFinD 涨停 40 只交叉吻合）；2026-09-11 收盘",
 "s_portrait": "市场画像 summary",
 "s_portrait_v": "替代快照：iFinD get_security_indicators + westock data_changedist 组装（westock data_market_overview 降级期）；2026-09-11（涨股比 12%、放量恐慌）",
 "s_index": "指数表现",
 "s_index_v": "iFinD get_security_indicators + westock data_kline 自算（MA/MACD/KDJ/BOLL/RSI 与 westock 原生口径核验偏差 0.0000）；2026-09-11 收盘",
 "s_sector": "板块排行 / 资金流",
 "s_sector_v": "westock · data_sector(mode=ranking, kind=industry/concept)；2026-09-11（927 板块，含主力/散户/暗盘行为分类）",
 "s_hot": "热搜股票",
 "s_hot_v": "westock · data_hot(kind=board)；2026-09-11（军工 / 电子硬科技 / 防御居前）",
 "s_macro": "核心宏观",
 "s_macro_v": "westock · data_macro(cn_pmi, cn_capacity_utilization, cn_financing 等)；PMI/产能/社融为前期复核（月频，无新发布），CPI/M1-M2/10Y/LPR 沿用前期值",
 "s_margin": "两融（个股）",
 "s_margin_v": "westock · 两融接口降级（data_market_overview type=margin service error），数据暂缺，未编造",
 "s_main": "主力5日净流入",
 "s_main_v": "westock · tool_ranking 降级期（service error），09-09 口径沿用；当日主力行为由 data_sector 板块资金（主力/散户/暗盘）替代呈现",
 "s_board": "连板高度",
 "s_board_v": "iFinD search_securities 涨停名单 + 历史 LimitUpDays 递推（tool_ranking 降级期替代；与 data_changedist 涨停 40 只交叉吻合）；2026-09-11（共 40 只，最高板 4板）",
 "s_gap": "数据缺口",
 "s_gap_v": "两融余额与融资单日变动接口降级（service error），已如实标注、未编造；估值 PE_TTM 20.09 为 iFinD 口径（52周分位 33.9%，3/5/10 年长周期分位缺，已标注）；主力5日净流入为 09-09 口径（降级期无法更新）",
 "t_src_note": "时间口径：所有时点按北京时间。宏观为月频 / 季频，与日频行情不可直接对齐，已分别标注。涨跌分布 / 指数 / 板块 / 连板梯队均为 2026-09-11 当日真实数据（广度/指数/技术来自降级期替代源并经口径核验）；估值长周期分位、两融、主力5日暂缺，均已标注。",
 "disc1": "免责声明：以上内容基于公开数据和量化分析，仅供参考，不构成投资建议。市场有风险，投资需谨慎。任何投资决策应结合个人风险承受能力、资金状况和投资目标独立判断，必要时咨询持牌专业机构。过往表现不预示未来收益。",
 "disc2": "本研判为「群体心理 / 条件框架」分析，非买卖指令；风险读数与偏差严重度为模型综合映射，须与价格结构、估值、资金流向交叉验证，不可单独作为交易依据。",
 "t_foot": "群体心理风险雷达 · 由 westock / iFinD 官方行情数据生成 · 仅供研究参考",
}

EN = {
 "t_headline_sub": "2026-09-11 · Close",
 "hk_stage": "Stage", "hv_stage": "<b>Volume-expanding broad sell-off / Panic spreads</b> (09-11)",
 "hk_upratio": "Up-ratio", "hv_upratio": "<b>12%</b> (prev 09-10 17% · ↓ 5pct, breadth keeps collapsing)",
 "hk_lim": "Limit-up / -down", "hv_lim": "<b>40</b> / <b>21</b> (limit-down surges 2→21, panic confirmed)",
 "hk_amt": "Turnover", "hv_amt": "<b>¥1.97tn</b> (expanding on a down day, 105.3% of 5d avg, 97.8% of 20d avg)",
 "hk_cycle": "Sentiment cycle", "hv_cycle": "<b>Volume-expanding broad sell-off / Panic spreads</b>",
 "hk_risk": "Risk level", "hv_risk": "<b class=\"hl-risk\">High</b> (all 09-10 pre-set triggers fired)",
 "hk_flag": "Key flag",
 "hv_flag": "Up-ratio 17%→<b>12%</b>, limit-down 2→<b>21</b> (>10 trigger), SSE −1.18% below MA60 (3941.72) with an intraday break of the BOLL lower band (3866.35) — the 'ebb acceleration' triggers pre-set on the 09-10 page <b>all fired</b>; turnover expanded to ¥1.97tn (105.3% of 5d avg) = <b>expanding sell-off, panic washing out</b>; only 33 of 927 sectors green, 733 in main-capital 'distribution'; margin & main-5d data missing in the degraded window, not fabricated.",
 "tk1": "Stage", "tv1": "A-shares 09-11 worsen from 09-10's 'volume-shrinking broad sell-off / ebb accelerates' into '<b>volume-expanding broad sell-off / panic spreads</b>': up-ratio halves again to <b>12%</b> (643 up / 4870 down / 49 flat, −5pct from 17%), limit-up <b>40</b> (38→40), limit-down <b>21</b> (surges from 2, crossing the 10-name warning line pre-set on 09-10), down-stocks 88.3%; SSE <b>−1.18%</b> (3888.11, intraday low 3852.03) closes below MA5/10/20/60 all at once, pierced the BOLL lower band (3866.35) intraday and closed near it; SZ <b>−1.08%</b> (13471.26), ChiNext <b>−0.49%</b> (3322.04). The key difference from 09-10: <b>turnover expanded</b> to ¥1.97tn (105.3% of 5d avg, +¥320bn d/d) — a shrinking grind turned into expanding panic, clear wash-out features. Risk raised from Medium to <b>High</b>.",
 "tk2": "Breadth collapse deepens", "tv2": "Up-ratio <b>12%</b> (prev 17%, ↓5pct) · limit-up <b>40</b> (38→40) · limit-down <b>21</b> (2→21, panic confirmed) · turnover <b>¥1.97tn</b> (105.3% of 5d avg, 103.2% of 10d, 97.8% of 20d, expanding) — unlike 09-10's 'grinding ebb', 21 limit-downs + expansion signal <b>panic selling has arrived</b>; only 33 of 927 sectors green (33 up / 892 down), 733 in main-capital 'distribution' — breadth collapse plus behaviour deterioration.",
 "tk3": "Technical breakdown", "tv3": "SSE <b>−1.18%</b> (3888.11) closes below MA5 (3929.45) / MA10 (3942.71) / MA20 (3934.80) / MA60 (3941.72) all at once, pierced the BOLL lower band (3866.35) intraday (low 3852.03) and closed near it; MACD <b>−7.23</b> (DIF 1.80 / DEA 5.41, histogram flipped negative and expanding from 09-10's +0.08, dead-cross confirmed); RSI6 <b>28.43</b> (near oversold), KDJ_J 15.2 (low) — <b>breakdown and oversold coexist</b>: trend is broken, but short-term oversold leaves room for a technical bounce; SZ −1.08%, ChiNext −0.49% (relatively resilient, having fallen earlier).",
 "tk4": "Sector structure", "tv4": "<b>Ground ArmamentⅡ +4.44%</b> (main net inflow +¥5.02bn, 'offensive buying') leads, <b>Glass-Fiber +2.63%</b> / <b>Components +1.80%</b> (main +¥63.8bn) / <b>Comm Equipment +1.66%</b> (main +¥83.99bn, #1 of all industries) follow — <b>defence + electronics hardware are the only direction with real main-capital absorption on a panic day</b>; <b>Industrial Metals −5.04%</b> leads losers (main inflow +¥26.1bn on the surface, but retail inflow +¥30.4bn was larger, dark flow −¥4.26bn → effectively 'distribution'), <b>Farm-Product Processing −4.36%</b> / <b>Fisheries −4.34%</b> follow — resources and prior themes dumped in the panic.",
 "tk5": "Limit-up ladder", "tv5": "Ladder totals <b>40 names</b> (flat d/d), top board holds at <b>4 boards</b> but the leader rotates: <b>Ruierte</b> takes over (Guilin Tourism fades), 3-board Dingxin Communications / Mindong Electric, 2-board Kaisheng New Energy / Ultrasonic Electronics / Jiuding New Material / Zhongxin Saike — <b>height holds but the leader changes daily, themes rotate fast</b>; speculative money stays only in tightly-held names, profit effect extremely narrow.",
 "tk6": "Capital: margin missing", "tv6": "The margin data interface is degraded (service error), <b>not fabricated</b>; from visible signals, main capital shows extreme divergence on the panic day: Comm Equipment +¥83.99bn, Components +¥63.8bn (electronics hardware absorbing) and Ground ArmamentⅡ +¥5.02bn (offensive buying) concentrated inflows, while 733 sectors 'distributed' and retail absorbed resources (Industrial Metals) — <b>capital abandons the middle and grabs the extremes: hardware tech and defence absorb against the trend, everything else sells off broadly</b>; leverage risk unconfirmed with margin missing, stay cautious amid expanding panic.",
 "tk7": "Valuation / style", "tv7": "PE_TTM <b>20.09</b> (52-week percentile <b>33.9%</b>, PB 1.78, dividend yield 2.02%; 3/5/10-year percentiles missing, not fabricated) — modestly digested by the fall (09-10 basis 20.44); style: defensives clearly lead — All-Share Value 20-day <b>+3.19%</b> vs All-Share Growth <b>−4.27%</b> (7.5pct gap), HS300 5-day −0.83% / CSI1000 5-day −1.08% — <b>the value/growth extreme divergence is the axis of this correction</b>, reinforced on the panic day.",
 "tk8": "Sentiment cycle", "tv8": "From 09-10's 'volume-shrinking broad sell-off / ebb accelerates' into '<b>volume-expanding broad sell-off / panic spreads</b>': up-ratio 17%→12%, limit-down 2→21 (crossing the trigger of 10), SSE below all MAs with an intraday BOLL-band break, turnover flipped from shrinking to expanding (+¥320bn d/d) — the 'further ebb acceleration' condition pre-set on 09-10 <b>all fired</b>; the cycle enters the <b>panic wash-out phase</b>. Expanding panic historically marks an extreme of sentiment, but right-side confirmation still needs volume-price signals; risk raised to <b>High</b>.",
 "t_tldr_text": "A-shares 09-11 = 'volume-expanding broad sell-off / panic spreads': up-ratio 17%→12% (643 up / 4870 down / 49 flat), limit-up 38→40, limit-down 2→21 (crossing the 10-name warning line pre-set on 09-10), down-stocks 88.3%; SSE −1.18% (3888.11) below all MAs, pierced the BOLL lower band intraday (3852.03 vs 3866.35), MACD histogram flipped negative and expanding (−7.23), RSI6 28.43 near oversold; SZ −1.08% (13471.26), ChiNext −0.49% (3322.04). Turnover expanded to ¥1.97tn (105.3% of 5d avg, +¥320bn d/d) — a shrinking grind became expanding panic. Ground ArmamentⅡ +4.44% (main +¥5.02bn offensive buying) leads, Comm Equipment +1.66% (main +¥83.99bn) / Components +1.80% (+¥63.8bn) follow — defence + hardware tech are the only direction with real absorption; Industrial Metals −5.04% leads losers (retail absorbing, effectively distribution), Farm-Product Processing −4.36% / Fisheries −4.34% follow. Only 33 of 927 sectors green, 733 distributing. Ladder 40 names flat, top board 4 (Ruierte, new leader). Margin & main-5d data missing (not fabricated). PE_TTM 20.09 (52w pctile 33.9%). All-Share Value 20d +3.19% vs Growth −4.27%. All 09-10 pre-set triggers fired; risk raised to High.",
 "t_risk": "Risk level", "t_risk_hi": "High",
 "c_upratio": "Up-ratio", "c_limitup": "Limit-up", "c_board": "Ladder height", "c_pe": "PE pctile", "c_pmi": "Mfg PMI", "c_turn": "Turnover",
 "t_sec_bias": "Behavioral Bias Heatmap", "t_cycle": "Sentiment Cycle (6-stage)",
 "r1": "Despair", "r2": "Doubt", "r3": "Optimism", "r4": "Euphoria", "r5": "Anxiety", "r6": "Complacency",
 "t_cycle_note": "Note: the 'Panic / Washout' tag above is the live crowd-psychology position (volume-expanding broad sell-off / panic spreads) — 09-11 breadth (up-ratio 12%, limit-up 40, limit-down 21, turnover ¥1.97tn) confirms panic: limit-down surged past the 10-name warning line pre-set on 09-10, SSE broke all MAs and pierced the BOLL lower band intraday, turnover expanded (105.3% of 5d avg) = wash-out features; margin data missing, valuation percentile digested with the fall. If 09-14 sees limit-down back under 10 and up-ratio above 20%, panic eases; if limit-down widens past 30 or the SSE closes below 3850, panic escalates.",
 "t_leg": "Severity (model-mapped)", "t_bias_note": "Note: bias severity is a model mapping from the real data below (1=low, 5=high), used to show where crowd psychology is fragile — not a buy/sell recommendation for any stock.",
 "t_sec_radar": "Risk Radar",
 "t_radar_note": "Six-dimension risk readings (0–100, mapped from the real data below; higher = greater crowd fragility on that axis): crowding 64 / margin 68 / turnover 50 / breadth 90 / media 42 / valuation 85. Breadth 82→90 (up-ratio 17%→12%, down-stocks 88.3%, limit-down 21 spreading panic, only 33 of 927 sectors green — breadth fragility near its extreme); turnover 44→50 (turnover expanded to ¥1.97tn, 105.3% of 5d avg, panic churn); margin 66→68 (margin data degraded and missing, leverage unconfirmed, but expanding panic + breakdown keep raising margin-crash risk, nudged up cautiously); crowding 62→64 (capital converges extremely into Comm Equipment / Components / defence while 733 sectors distribute, concentration rises); media 46→42 (21 limit-downs, all three indices down, breakdown — sentiment temperature near freezing); valuation 87→85 (PE_TTM 20.44→20.09 modestly digested by the fall, 52w pctile 33.9%, long-cycle percentiles missing). Fragility is now led by 'breadth + panic churn' — the wash-out phase, with breadth near its extreme as the dominant risk source and valuation risk easing at the margin.",
 "ax_crowd": "Crowding", "ax_margin": "Margin", "ax_turn": "Turnover", "ax_breadth": "Breadth", "ax_media": "Media mood", "ax_val": "Valuation",
 "b_up": "Up", "b_down": "Down", "b_flat": "Flat", "b_limitup": "Limit-up", "b_limitdn": "Limit-down", "b_amt": "Turnover",
 "t_breadth_note": "Up-ratio 17%→12%, limit-up 38→40 (flat), limit-down 2→21 (panic confirmed), down-stocks 88.3%; turnover ¥1.97tn (105.3% of 5d avg, +¥320bn d/d) — expanding on a down day. All three indices fall with technical breakdowns: SSE −1.18% (3888.11, below MA5/10/20/60, pierced the BOLL lower band 3866.35 intraday) / SZ −1.08% (13471.26) / ChiNext −0.49% (3322.04); Ground ArmamentⅡ +4.44% (main +¥5.02bn offensive buying) leads, Industrial Metals −5.04% (retail absorbing, effectively distribution) lags — only 33 of 927 sectors green, 733 in 'distribution'.",
 "th_metric": "Metric", "th_read": "Real reading", "th_interp": "Behavioral read",
 "ev_market": "I. Market breadth & overview",
 "ev_upratio": "Up-ratio",
 "ev_upratio_i": "17%→12% (−5pct), 643 up / 4870 down / 49 flat; participation collapses further; limit-down 21 (2→21) crosses the warning line — from a 'grinding ebb' to an 'expanding panic wash-out'",
 "ev_limit": "Limit-up / -down",
 "ev_limit_i": "Limit-up 40 (38→40 flat), limit-down 21 (surges 19 from 2, crossing the 10-name warning pre-set on 09-10), ladder height 4 boards but the leader rotates (Ruierte takes over) — speculative heat plateaus, rotation extremely fast",
 "ev_amount": "Turnover",
 "ev_amount_i": "Volume ¥1.97tn (105.3% of 5d avg, 103.2% of 10d, 97.8% of 20d, +¥320bn d/d) — flipped from consecutive shrinking to expanding: panic wash-out features; selling shifts from 'grinding erosion' to 'concentrated dumping'",
 "ev_index": "II. Core indices (2026-09-11 close)",
 "ev_sh": "SSE Composite",
 "ev_sh_i": "−1.18% (3888.11, intraday low 3852.03), closes below MA5 (3929.45) / MA10 (3942.71) / MA20 (3934.80) / MA60 (3941.72) all at once, pierced the BOLL lower band (3866.35) intraday and closed near it; MACD −7.23 (DIF 1.80 / DEA 5.41, histogram flipped negative and expanding, dead-cross confirmed), RSI6 28.43 near oversold, KDJ_J 15.2; PE_TTM 20.09 (52w pctile 33.9%, long-cycle percentiles missing)",
 "ev_sz": "SZ Component",
 "ev_sz_i": "SZ −1.08% (13471.26), follows the breakdown, mid-term weakness deepens",
 "ev_cyb": "ChiNext",
 "ev_cyb_i": "ChiNext −0.49% (3322.04) relatively resilient (having fallen earlier), divergence within the growth style (hardware Components / Comm Equipment got main-capital absorption)",
 "ev_sector": "III. Sector ranking & main line",
 "ev_secup": "Leading sectors",
 "ev_secup_i": "Ground ArmamentⅡ +4.44% (main net inflow +¥5.02bn, 'offensive buying') leads, Glass-Fiber +2.63% / Components +1.80% (main +¥63.8bn) / Comm Equipment +1.66% (main +¥83.99bn, #1 of all industries) follow — defence + electronics hardware are the only direction with real main-capital absorption on a panic day; only 33 of 927 sectors green",
 "ev_secdn": "Lagging sectors",
 "ev_secdn_i": "Industrial Metals −5.04% leads (main inflow +¥26.1bn on the surface, but retail inflow +¥30.4bn larger, dark flow −¥4.26bn → effectively 'distribution') / Farm-Product Processing −4.36% / Fisheries −4.34% — resources and prior themes dumped in the panic, 733 sectors in 'distribution'",
 "ev_board": "Extreme themes",
 "ev_board_i": "Ladder totals 40 names (flat), top board 4 (Ruierte, new leader taking over from Guilin Tourism); 3-board Dingxin Communications / Mindong Electric — height holds but the leader changes daily, themes rotate fast, profit effect extremely narrow",
 "ev_flow": "IV. Capital: ladder / main / margin",
 "ev_height": "Ladder height",
 "ev_height_i": "Height 4 boards (Ruierte, 2026-09-11 close, new leader); themes: bath-fixture exports + electronics (Dingxin / Ultrasonic) + power (Mindong) — tightly-held names become the panic-day shelter pool",
 "ev_main": "Main capital 5d net inflow TOP",
 "ev_main_i": "Main-5d data cannot be updated in the degraded window (westock tool_ranking service error, 09-09 basis carried, not fabricated); visible same-day signal: extreme main-capital divergence — Comm Equipment +¥83.99bn / Components +¥63.8bn / Ground ArmamentⅡ +¥5.02bn concentrated inflows while 733 sectors 'distribute'; margin data missing, not fabricated.",
 "ev_margin": "Daily margin change TOP",
 "ev_margin_i": "The margin interface is degraded (service error); both daily margin change and aggregate margin balance are unavailable — <b>not fabricated</b>; with expanding panic + breakdown, leverage-crash risk is unconfirmed, treat with caution — a notable margin paydown on the panic day would actually aid the wash-out.",
 "ev_hot": "Hot / top gainers",
 "ev_hot_i": "Hotspots converge extremely on the panic day: Ruierte 4 boards (bath fixtures) / Ground ArmamentⅡ +4.44% (main +¥5.02bn offensive buying) / Comm Equipment +1.66% (main +¥83.99bn) / Components +1.80% (+¥63.8bn); defence and hardware tech dual lines, consistent with the style split 'All-Share Value 20d +3.19% vs Growth −4.27%'",
 "ev_margintotal": "Aggregate margin balance",
 "ev_margintotal_i": "Gap: both aggregate margin balance and daily margin change interfaces are degraded (service error) — flagged honestly, not fabricated; breadth / indices / turnover / sectors / ladder are real 2026-09-11 closes, main-5d net inflow is 09-09 basis (cannot update in the degraded window)",
 "ev_macro": "V. Core macro indicators",
 "ev_pmi": "Mfg PMI (Jul)",
 "ev_pmi_i": "Fundamentals contract, resonating with 'high valuation + panic breakdown' to amplify the downside; non-mfg new orders soft",
 "ev_capu": "Capacity utilisation (Q2)",
 "ev_capu_i": "Real-economy momentum weakens, prices lack earnings support",
 "ev_cpi": "CPI (Jul)",
 "ev_cpi_i": "Low inflation, weak demand, hard to confirm a broad recovery",
 "ev_social": "Social financing (Jul)",
 "ev_social_i": "Weak credit demand, capital detours into stocks = liquidity-driven feature; liquidity expectations also pressured on the panic day",
 "ev_m1m2": "M1-M2 spread",
 "ev_m1m2_i": "Active money weak, capital idles, typical late-cycle phenomenon",
 "ev_yield": "10Y gov bond yield",
 "ev_yield_i": "Extremely low risk-free rate, supports valuation yet reflects growth worry",
 "ev_lpr": "LPR",
 "ev_lpr_i": "Accommodative stance unchanged",
 "t_ev_note": "Data basis: macro indicators are monthly (to 2026-07) or carried forward; breadth / indices / turnover / sectors / ladder are real 2026-09-11 closes (breadth from the data_changedist fallback, indices/technicals from iFinD + self-computed, cross-checked against native westock with 0.0000 deviation). Valuation PE_TTM 20.09 is same-day iFinD basis (52w pctile 33.9%, long-cycle percentiles missing); margin & main-5d missing in the degraded window, flagged, not fabricated. See 'Sources and date basis' at the end.",
 "t_sec_risk": "Risk Stratification",
 "rc1_tag": "Red zone · Panic wash-out + technical breakdown (leverage data missing)",
 "rc1_t": "Expanding panic + full breakdown (leverage missing)",
 "rc1_d": "09-11 expanding sell-off (21 limit-downs, down 88.3%, turnover 105.3% of 5d avg) + SSE below all MAs with an intraday BOLL-band break + MACD histogram flipped negative and expanding — all 'ebb acceleration' triggers pre-set on 09-10 fired; margin missing so leverage is unconfirmed, but leverage-crash risk peaks in expanding panic — risk raised to High; position discipline comes first.",
 "rc1_rep": "Represented by: margin-concentrated broken main lines / resources (Industrial Metals −5.04%, retail absorbing, effectively distribution) / agriculture chain (Farm-Product Processing −4.36%, Fisheries −4.34%)",
 "rc1_cond": "Condition frame: strictly execute the 09-10 pre-set discipline (trigger fired → cut to ≤30%); no leverage, no catching a falling knife; minimum easing confirmation = 'limit-down back under 10 + up-ratio above 20%'.",
 "rc2_tag": "Amber zone · Panic wash-out vs oversold bounce",
 "rc2_t": "Panic spreading vs oversold rebound",
 "rc2_d": "SSE RSI6 28.43 near oversold, KDJ_J 15.2 low, ChiNext relatively resilient — conditions for a technical bounce are accumulating; but expanding panic usually takes 1–2 sessions to digest, the MACD histogram just flipped negative and expanding, and the mid-term trend is broken — a bounce would likely be a weak repair, not a reversal.",
 "rc2_rep": "Represented by: ChiNext (−0.49% resilient) / oversold hardware tech (Components / Comm Equipment with main absorption) / prior oversold themes",
 "rc2_cond": "Condition frame: do not chase bounces, observe first; a shrinking-volume bounce = weak rebound, beware a second leg down; right-side confirmation = expanding volume reclaiming MA5/MA10 with limit-downs cleared.",
 "rc3_tag": "Green zone · Defence + hardware tech (real main-capital absorption)",
 "rc3_t": "Defence / electronics hardware absorbing against the trend",
 "rc3_d": "Ground ArmamentⅡ +4.44% (main +¥5.02bn offensive buying), Comm Equipment +1.66% (main +¥83.99bn, #1 of all industries), Components +1.80% (main +¥63.8bn) — the only direction with real main-capital absorption on the panic day; under the extreme style split (All-Share Value 20d +3.19% vs Growth −4.27%), hardware tech is the offensive end of 'abandon the middle, grab the extremes'.",
 "rc3_rep": "Represented by: Ground ArmamentⅡ (offensive buying) / Comm Equipment / Components / Glass-Fiber (accumulation)",
 "rc3_cond": "Condition frame: observe and track structure only, do not chase on a panic day; confirmation = the direction keeps main net inflows and stable turnover after the index stabilises; if it dumps as panic escalates, that confirms a full wash-out.",
 "t_sec_outlook": "Next session (09-14 Mon) outlook",
 "o_logic": "Reasoning (based on the 09-11 close + crowd-psychology position)",
 "o_logic_text": "Extending 09-11's 'volume-expanding broad sell-off / panic spreads': all triggers pre-set on 09-10 fired (limit-down 21>10, SSE below MA60), the cycle enters the panic wash-out phase — up-ratio 12%, limit-down 21, turnover expanded to ¥1.97tn (105.3% of 5d avg), SSE below all MAs with an intraday BOLL-band break; yet RSI6 28.43 is near oversold and defence / hardware tech got real main-capital absorption. Sector directions and trading rules for 09-14 follow (<b>no individual stock recommendations</b>).",
 "o1_tag": "Defence / hardware absorption (watch)",
 "o1_t": "Ground ArmamentⅡ / Comm Equipment / Components / Glass-Fiber",
 "o1_d": "The only direction with real main-capital absorption on the panic day (Ground ArmamentⅡ offensive buying +¥5.02bn, Comm Equipment +¥83.99bn, Components +¥63.8bn); if panic eases, this direction likely stabilises first.",
 "o1_cond": "Caution: green on a panic day ≠ safe haven; if panic escalates (limit-down >30), its dump would confirm a full wash-out; watch 'whether main net inflows persist after the index stabilises', do not chase the panic-day gains.",
 "o2_tag": "Resources / prior themes (avoid)",
 "o2_t": "Industrial Metals / agriculture chain / prior high-position lines",
 "o2_d": "Industrial Metals −5.04% with retail absorbing (dark flow −¥4.26bn, distribution), Farm-Product Processing −4.36% / Fisheries −4.34% keep ebbing; 733 sectors 'distribute' — the least liquid sectors carry the heaviest selling in a panic.",
 "o2_cond": "Caution: retail-absorbing declines (negative dark flow) usually have a second惯性 leg down; do not grab the bounce, wait for the dark flow to turn positive or a shrinking-volume stabilisation.",
 "o3_tag": "Panic-easing signals (stand by)",
 "o3_t": "Limit-down recedes / up-ratio repairs / oversold bounce",
 "o3_d": "09-11 confirmed panic (limit-down 21, up-ratio 12%), but RSI6 28.43 near oversold and KDJ_J 15.2 — conditions for a technical bounce are accumulating; watch whether 09-14 shows 'limit-down back under 10 + up-ratio above 20%'.",
 "o3_cond": "Caution: do not pre-empt the bottom in a wash-out; a shrinking-volume bounce = weak rebound (beware a second leg); right-side confirmation = expanding volume reclaiming MA5/MA10 (3929/3943) with limit-downs cleared; until then, position discipline first.",
 "o_rules_t": "Trading rules (09-14)",
 "o_r1": "<b>Position</b>: execute the 09-10 pre-set discipline — triggers fired, <b>cut to ≤30%</b>, no leverage; capital preservation first in the wash-out phase.",
 "o_r2": "<b>Panic-easing confirmation</b>: only treat as easing if limit-down falls back under 10 and up-ratio rebounds above 20%; if limit-down widens past 30 or the SSE closes below 3850, treat as escalation and shrink risk exposure further.",
 "o_r3": "<b>Main-line participation</b>: defence / hardware absorption only as structural observation (do main inflows persist?), no chasing panic-day gains; avoid retail-absorbing declines (Industrial Metals, agriculture chain), wait for the dark flow to turn positive.",
 "o_r4": "<b>Avoid list</b>: retail-absorbing sectors like Industrial Metals, the ebbing agriculture chain, margin-concentrated broken high-position lines, ladder-top relay (leader changes daily, rotation extremely fast).",
 "o_r5": "<b>Risk control</b>: a shrinking-volume bounce = weak rebound, beware a second leg down; right-side confirmation = expanding volume reclaiming MA5/MA10 with limit-downs cleared; do not add leverage until margin data resumes.",
 "o_compliance": "<b>Compliance:</b> this outlook gives sector directions and trading rules only, with no individual stock recommendations; the crowd-psychology position and sector inferences are based on real 2026-09-11 market data. Markets carry risk; decisions must be independent.",
 "t_sec_source": "Sources & date basis",
 "s_breadth": "Breadth / overview",
 "s_breadth_v": "westock · data_changedist(type=0) (fallback while market_overview is degraded, cross-checked with iFinD limit-up 40); 2026-09-11 close",
 "s_portrait": "Market portrait summary",
 "s_portrait_v": "Fallback snapshot: iFinD get_security_indicators + westock data_changedist assembled (westock data_market_overview degraded); 2026-09-11 (up-ratio 12%, expanding panic)",
 "s_index": "Index performance",
 "s_index_v": "iFinD get_security_indicators + westock data_kline self-computed (MA/MACD/KDJ/BOLL/RSI cross-checked against native westock with 0.0000 deviation); 2026-09-11 close",
 "s_sector": "Sector ranking / flows",
 "s_sector_v": "westock · data_sector(mode=ranking, kind=industry/concept); 2026-09-11 (927 sectors, incl. main/retail/dark-flow behaviour classes)",
 "s_hot": "Hot stocks",
 "s_hot_v": "westock · data_hot(kind=board); 2026-09-11 (defence / hardware tech on top)",
 "s_macro": "Core macro",
 "s_macro_v": "westock · data_macro(cn_pmi, cn_capacity_utilization, cn_financing etc.); PMI/capacity/social-financing reviewed earlier (monthly, no new release), CPI/M1-M2/10Y/LPR carried forward",
 "s_margin": "Margin (stocks)",
 "s_margin_v": "westock · margin interface degraded (data_market_overview type=margin service error), data missing, not fabricated",
 "s_main": "Main capital 5d net inflow",
 "s_main_v": "westock · tool_ranking degraded (service error), 09-09 basis carried; same-day main behaviour shown via data_sector sector flows (main/retail/dark)",
 "s_board": "Ladder height",
 "s_board_v": "iFinD search_securities limit-up list + historical LimitUpDays recursion (tool_ranking degraded fallback; cross-checked with data_changedist limit-up 40); 2026-09-11 (40 names, top board 4)",
 "s_gap": "Data gaps",
 "s_gap_v": "Aggregate margin balance and daily margin change interfaces degraded (service error) — flagged honestly, not fabricated; valuation PE_TTM 20.09 is iFinD basis (52w pctile 33.9%, 3/5/10-year percentiles missing, flagged); main-5d net inflow is 09-09 basis (cannot update in the degraded window)",
 "t_src_note": "Timing: all timestamps are Beijing time. Macro data are monthly/quarterly and cannot be aligned directly with daily quotes; each is flagged. Breadth / indices / sectors / ladder are real 2026-09-11 data (breadth/indices/technicals from degraded-window fallbacks, cross-checked); valuation long-cycle percentiles, margin, main-5d missing — all flagged.",
 "disc1": "Disclaimer: the above is based on public data and quantitative analysis, for reference only, not investment advice. Markets carry risk; investment decisions should be made independently per your own risk tolerance, financial status and goals, and consult a licensed professional when necessary. Past performance does not predict future returns.",
 "disc2": "This assessment is 'crowd psychology / conditional framework' analysis, not a trading order; risk readings and bias severities are model mappings and must be cross-validated with price structure, valuation and flows, not used alone as a trade basis.",
 "t_foot": "Crowd Psychology Risk Radar · generated from westock / iFinD official market data · research reference only",
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
# 2) 重建 BIAS 数组（09-11 恐慌视角）
# ============================================================
BIAS = [
 {"zh":"羊群效应","en":"Herding","sev":5,
  "zhd":"跌停暴增至 21 只、4870 家下跌（88.3%）、成交放量至 ¥1.97万亿（5 日均 105.3%）——恐慌情绪自我强化，抛售由「各自决策」变为「相互踩踏」；仅通信设备/元件/军工获主力承接，群体在恐慌中进一步放弃独立判断。",
  "end":"Limit-down surges to 21, 4870 down (88.3%), turnover expands to ¥1.97tn (105.3% of 5d avg) — panic self-reinforces, selling turns from individual decisions into mutual stampeding; only Comm Equipment / Components / defence get main absorption, the herd abandons independent judgement further in panic."},
 {"zh":"损失厌恶","en":"Loss Aversion","sev":4,
  "zhd":"放量下跌中「扛单的痛苦」超过「割肉的痛苦」，止损盘与被动扛单者集中释放——跌停 21 只即损失实现的高峰形态；对「错过军工/硬科技避险」的厌恶同步放大追高冲动。",
  "end":"In an expanding sell-off the pain of holding exceeds the pain of cutting; stop-losses and passive holders release together — 21 limit-downs mark the peak of loss realisation; aversion to 'missing the defence/hardware shelter' simultaneously amplifies chasing."},
 {"zh":"心理账户/赌徒谬误","en":"Mental Acct / Gambler","sev":3,
  "zhd":"把军工/元件/通信设备的恐慌日收红记入「避风港」账户并外推为「资金避难所」，忽视 733 个板块出货、指数全面破位的系统性现实——局部强势≠账户安全。",
  "end":"Booking the panic-day greens (defence/Components/Comm Equipment) into a 'safe-haven' account and extrapolating it into 'where capital shelters', ignoring 733 distributing sectors and the systemic breakdown — local strength ≠ account safety."},
 {"zh":"过度自信","en":"Overconfidence","sev":2,
  "zhd":"恐慌日过度自信暂时消失（追涨冲动被恐惧压制），但「超卖必反弹」的抄底自信开始萌芽——RSI6 28.43 的超卖读数易被误读为「见底信号」，而 MACD 绿柱刚转负放大、中期趋势已坏。",
  "end":"Overconfidence temporarily vanishes on the panic day (chasing suppressed by fear), but 'oversold must bounce' bottom-fishing confidence sprouts — RSI6 28.43 is easily misread as a 'bottom signal', while the MACD histogram just flipped negative and the mid-term trend is broken."},
 {"zh":"处置效应","en":"Disposition","sev":3,
  "zhd":"割肉跌停股与弱势股（损失实现集中）、持有军工/硬科技「强势仓」——处置效应在恐慌日反向体现：卖出亏损、紧握浮盈，若恐慌升级后者同样面临回吐。",
  "end":"Cutting limit-down and weak names (loss realisation concentrated) while holding the 'strong' defence/hardware books — disposition reverses on the panic day: sell losers, clutch winners; if panic escalates, the winners give back too."},
 {"zh":"锚定偏差","en":"Anchoring","sev":4,
  "zhd":"一部分人锚定前期高点认为「回调是上车机会」，另一部分锚定 3852「跌这么多该反弹了」——缺乏新定价锚时，3888/3852 等整数位成为群体博弈焦点，易在半山腰互接。",
  "end":"Some anchor to prior highs ('a dip is a chance to board'), others anchor to 3852 ('fallen this much, it should bounce') — without a new pricing anchor, round numbers like 3888/3852 become the crowd's battleground, easy to catch falling knives at mid-slope."},
 {"zh":"确认偏误","en":"Confirmation Bias","sev":3,
  "zhd":"空头只看跌停 21、破位、放量恐慌的「崩盘证据」，忽视 RSI6 28.43 接近超卖、KDJ_J 15.2、创业板相对抗跌与军工/硬科技主力承接的修复线索——恐慌日的信息处理天然偏空。",
  "end":"Bears only watch the 'crash evidence' (21 limit-downs, breakdown, expanding panic), ignoring repair clues like RSI6 28.43 near oversold, KDJ_J 15.2, ChiNext resilience and main-capital absorption in defence/hardware — information processing is naturally bearish-biased on a panic day."},
 {"zh":"近因偏差","en":"Recency","sev":4,
  "zhd":"把 09-11 单日恐慌外推为「崩盘开始」，忽视 09-09→09-11 已连续三日退潮、恐慌放量往往是情绪极值而非趋势起点；同样有人把单日超卖外推为「必反弹」——两个方向的近因外推都在放大波动。",
  "end":"Extrapolating the single panic day into 'the crash begins', ignoring that the ebb has run three sessions (09-09→09-11) and expanding panic often marks a sentiment extreme rather than a trend start; equally, some extrapolate single-day oversold into 'must bounce' — recent-bias extrapolation in both directions amplifies volatility."},
 {"zh":"叙事偏差","en":"Narrative","sev":3,
  "zhd":"「军工景气 + 硬科技自主可控」叙事在恐慌日被主力资金强化（地面兵装Ⅱ 抢筹 +50.22亿、通信设备 +839.89亿），故事与资金短期共振；但叙事一旦在恐慌缓和后被证伪，承接盘的回撤同样剧烈。",
  "end":"The 'defence prosperity + hardware self-reliance' narrative is reinforced by main capital on the panic day (Ground ArmamentⅡ offensive buying +¥5.02bn, Comm Equipment +¥83.99bn), story and capital resonate short-term; but if the narrative is falsified after the panic eases, the absorption books would retrace just as hard."},
 {"zh":"代表性启发","en":"Representativeness","sev":3,
  "zhd":"把工业金属 −5.04% 代表「资源全崩」、把军工收红代表「市场无恙」——927 板块中 33 涨 892 跌的极端分布下，任何单一样本都不具代表性；全指价值 20日 +3.19% vs 全指成长 −4.27% 才是本轮的真实主轴。",
  "end":"Reading Industrial Metals −5.04% as 'resources all collapsing' or the defence greens as 'the market is fine' — with 33 up / 892 down of 927 sectors, no single sample is representative; All-Share Value 20d +3.19% vs Growth −4.27% is the real axis of this correction."},
]
bias_js = "var BIAS = [\n" + ",\n".join(
    "    {zh:\"%s\",en:\"%s\",sev:%d,zhd:\"%s\",end:\"%s\"}" % (esc(b["zh"]), esc(b["en"]), b["sev"], esc(b["zhd"]), esc(b["end"]))
    for b in BIAS) + "\n  ];"
html, _n = re.subn(r'var BIAS = \[.*?\n  \];', bias_js, html, count=1, flags=re.S)
assert _n == 1, "BIAS 替换失败"

# ============================================================
# 3) 静态 body 证据表 + 涨跌分布 SVG 修正
#    OLD = 09-10 值（源 20260910.html），NEW = 09-11 值
# ============================================================
BODY = [
 # SVG rects（12% → 58、88% → 442；0910 页 node id 已被 _apply_theme 剥离，用裸锚点）
 ('<rect x="14" y="14" width="85" height="26" fill="#d8392b"/>',
  '<rect x="14" y="14" width="58" height="26" fill="#d8392b"/>'),
 ('<rect x="99" y="14" width="405" height="26" fill="#1a9e5a"/>',
  '<rect x="72" y="14" width="442" height="26" fill="#1a9e5a"/>'),
 # SVG texts
 ('<text x="167" y="33" fill="#fff" font-size="14" font-weight="800" text-anchor="middle">17%</text>',
  '<text x="167" y="33" fill="#fff" font-size="14" font-weight="800" text-anchor="middle">12%</text>'),
 ('<text x="407" y="33" fill="#fff" font-size="14" font-weight="800" text-anchor="middle">81%</text>',
  '<text x="407" y="33" fill="#fff" font-size="14" font-weight="800" text-anchor="middle">88%</text>'),
 ('<text x="514" y="33" fill="#6b675f" font-size="11" font-weight="700" text-anchor="end">2% 平盘</text>',
  '<text x="514" y="33" fill="#6b675f" font-size="11" font-weight="700" text-anchor="end">1% 平盘</text>'),
 # stat rows
 ('<text x="340" y="72" fill="#d8392b">955</text>',
  '<text x="340" y="72" fill="#d8392b">643</text>'),
 ('<text x="340" y="92" fill="#1a9e5a">4512</text>',
  '<text x="340" y="92" fill="#1a9e5a">4870</text>'),
 ('<text x="340" y="112" fill="#6b675f">94</text>',
  '<text x="340" y="112" fill="#6b675f">49</text>'),
 ('<text x="340" y="138" fill="#d8392b">38</text>',
  '<text x="340" y="138" fill="#d8392b">40</text>'),
 ('<text x="340" y="158" fill="#1a9e5a">2</text>',
  '<text x="340" y="158" fill="#1a9e5a">21</text>'),
 ('<text x="340" y="184" fill="#1c1b19">¥1.65万亿</text>',
  '<text x="340" y="184" fill="#1c1b19">¥1.97万亿</text>'),
 # annotations
 ('<text x="355" y="72">（占 17%，较上一报告日（09-09） −15pct）</text>',
  '<text x="355" y="72">（占 12%，较上一报告日（09-10） −5pct）</text>'),
 ('<text x="355" y="92">（占 81%，较上一报告日（09-09） +13pct）</text>',
  '<text x="355" y="92">（占 88%，较上一报告日（09-10） +7pct）</text>'),
 ('<text x="355" y="112">（占 4%）</text>',
  '<text x="355" y="112">（占 1%）</text>'),
 ('<text x="355" y="138">（较前日 −4 只，连板高度 4板）</text>',
  '<text x="355" y="138">（较前日 +2 只，连板高度 4板）</text>'),
 ('<text x="355" y="158">（较前日 +2 只，跌停 2 只）</text>',
  '<text x="355" y="158">（较前日 +19 只，恐慌扩散）</text>'),
 ('<text x="355" y="184">（环比 −2100亿，继续缩量）</text>',
  '<text x="355" y="184">（环比 +3200亿，放量普跌）</text>'),
 # evidence table number cells
 ('<td><span class="val up">17%</span>（涨955 / 跌4512 / 平94）</td>',
  '<td><span class="val up">12%</span>（涨643 / 跌4870 / 平49）</td>'),
 ('<td><span class="val up">38</span> / <span class="val down">2</span></td>',
  '<td><span class="val up">40</span> / <span class="val down">21</span></td>'),
 ('<td><span class="val">¥1.65万亿</span>（较前次 −2100亿，继续缩量）</td>',
  '<td><span class="val">¥1.97万亿</span>（较前次 +3200亿，放量普跌）</td>'),
 ('<td><span class="val down">3934.40　−0.43%</span></td>',
  '<td><span class="val down">3888.11　−1.18%</span></td>'),
 ('<td><span class="val down">13617.67　−0.77%</span></td>',
  '<td><span class="val down">13471.26　−1.08%</span></td>'),
 ('<td><span class="val down">3338.42　−0.49%</span></td>',
  '<td><span class="val down">3322.04　−0.49%</span></td>'),
 ('<td><span class="val up">航海装备Ⅱ +2.76%</span>（换手 5.72%、主力净流入 +4.64亿）<br>城商行Ⅱ +2.39% / 玻璃玻纤 +2.23% 跟随<br>全市场 124 个行业绝大多数下跌，仅约 2 成行业收红</td>',
  '<td><span class="val up">地面兵装Ⅱ +4.44%</span>（主力净流入 +50.22亿，行为「抢筹」）<br>通信设备 +1.66%（主力 +839.89亿，全行业第一）/ 元件 +1.80%（+638.35亿）/ 玻璃玻纤 +2.63% 跟随<br>全市场 927 个板块仅 33 个收红，733 个呈主力「出货」</td>'),
 ('<td><span class="val down">种植业 −5.09%</span>（换手 11.15%）<br>渔业 −4.69% / 农产品加工 −4.65%<br>农业链集体重挫，与 09-09 领涨的橡胶/航运/资源剧烈反转</td>',
  '<td><span class="val down">工业金属 −5.04%</span>（主力 +261.18亿 但散户流入 +303.79亿更多，暗盘 −42.6亿 → 实为「出货」）<br>农产品加工 −4.36% / 渔业 −4.34%<br>资源与前期题材在恐慌中集中补跌</td>'),
 ('<td><span class="val up">连板高度 4 板</span>（桂林旅游）<br>共 40 只连板；题材由消费/资源切换至旅游（桂林旅游 4板），轮动加快、高度下降</td>',
  '<td><span class="val up">连板高度 4 板</span>（瑞尔特，新龙头接棒桂林旅游）<br>共 40 只连板（持平）；3板：鼎信通讯 / 闽东电力；2板：凯盛新能 / 超声电子 / 九鼎新材 / 中新赛克——龙头一日一换</td>'),
 ('<td><span class="val up">桂林旅游 4板</span>（2026-09-10）</td>',
  '<td><span class="val up">瑞尔特 4板</span>（2026-09-11）</td>'),
 ('<td><span class="val">主力5日净流入 TOP（09-09 口径，当日暂缺）</span></td>',
  '<td><span class="val">主力5日净流入 TOP（tool_ranking 降级期，09-09 口径沿用）</span></td>'),
 ('<td><span class="val">融资单日变动 TOP（两融接口返回空，数据暂缺）</span></td>',
  '<td><span class="val">融资单日变动 TOP（两融接口降级，数据暂缺，未编造）</span></td>'),
 ('<td><span class="val up">桂林旅游 4板</span>（旅游）<br>航海装备Ⅱ +2.76%（主力净流入 +4.64亿）<br>城商行Ⅱ +2.39% / 玻璃玻纤 +2.23%<br>种植业 −5.09%（换手 11.15%）/ 渔业 −4.69%</td>',
  '<td><span class="val up">瑞尔特 4板</span>（卫浴出海）<br>地面兵装Ⅱ +4.44%（主力 +50.22亿 抢筹）<br>通信设备 +1.66% / 元件 +1.80% / 玻璃玻纤 +2.63%<br>工业金属 −5.04% / 农产品加工 −4.36% / 渔业 −4.34%</td>'),
 # static header date + Next-Session
 ('<b>2026-09-10 收盘（北京时间，盘后）</b>',
  '<b>2026-09-11 收盘（北京时间，盘后）</b>'),
 ("Next-Session Outlook (09-11 Fri)", "Next-Session Outlook (09-14 Mon)"),
 # 顶部 chips 静态值
 ('<span data-i18n="c_upratio">涨股比</span> <b>17%</b></span>',
  '<span data-i18n="c_upratio">涨股比</span> <b>12%</b></span>'),
 ('<span data-i18n="c_limitup">涨停</span> <b>38</b></span>',
  '<span data-i18n="c_limitup">涨停</span> <b>40</b></span>'),
 ('<span data-i18n="c_pe">估值 PE分位</span> <b>70-90%</b></span>',
  '<span data-i18n="c_pe">估值 PE分位</span> <b>34%（52周）</b></span>'),
 ('<span data-i18n="c_turn">两市成交</span> <b>¥1.65万亿</b></span>',
  '<span data-i18n="c_turn">两市成交</span> <b>¥1.97万亿</b></span>'),
]
for old, new in BODY:
    if old in html:
        html = html.replace(old, new, 1)
    else:
        print("[skip-body] 未命中: %r" % old[:60])

# ============================================================
# 4) 雷达数值标签（红字组）—— 六维：拥挤64/融资68/换手50/广度90/媒体42/估值85
#    （0910 页 node id 已剥离，用裸锚点）
# ============================================================
old_radar = '<text x="160" y="71">62</text><text x="237" y="120">66</text><text x="209" y="194">44</text>\n            <text x="160" y="167">82</text><text x="109" y="201">46</text><text x="55" y="118">87</text>'
new_radar = '<text x="160" y="71">64</text><text x="237" y="120">68</text><text x="209" y="194">50</text>\n            <text x="160" y="167">90</text><text x="109" y="201">42</text><text x="55" y="118">85</text>'
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

# ============================================================
# 6) hub（web/psychology/index.html）插入 0911 条目
# ============================================================
HUB = os.path.join(HERE, "..", "web", "psychology", "index.html")
hub = open(HUB, encoding="utf-8").read()
if "crowd-psychology-risk-radar-20260911.html" not in hub:
    entry = """    },
    {
      file:"crowd-psychology-risk-radar-20260911.html", date:"2026-09-11",
      risk:"高", riskEn:"High",
      cycleZh:"放量普跌 · 恐慌扩散", cycleEn:"Volume-expanding broad sell-off / Panic spreads",
      cycleNoteZh:"涨股比12%·跌停21只", cycleNoteEn:"Up-ratio 12% · Limit-down 21",
      up:"12%", limitup:"40", board:"4板", turn:"¥1.97万亿",
      summaryZh:"涨股比17%→12%（643涨/4870跌/平49）、涨停38→40、跌停2→21（越过09-10预设10只警戒线），下跌家数占比88.3%；上证−1.18%（3888.11）跌破MA5/10/20/60全部均线、盘中击穿布林下轨（3852.03 vs 3866.35），MACD绿柱转负放大（−7.23）、RSI6 28.43接近超卖；深成−1.08%（13471.26）、创业板−0.49%（3322.04）。成交放量至¥1.97万亿（5日均105.3%、环比+3200亿）——缩量阴跌转为放量恐慌。地面兵装Ⅱ+4.44%（主力+50.22亿抢筹）领涨，通信设备+1.66%（主力+839.89亿）/元件+1.80%（+638.35亿）跟随——军工+电子硬科技是唯一有主力承接的方向；工业金属−5.04%领跌（散户接盘实为出货），农产品加工−4.36%/渔业−4.34%跟随。927板块仅33收红、733出货。连板40只持平、4板瑞尔特（新龙头）。两融与主力5日数据降级期暂缺（未编造）。估值PE_TTM 20.09（52周分位33.9%）。09-10预设触发条件全部应验，风险等级上调至高。",
      summaryEn:"Up-ratio 17%→12% (643 up / 4870 down / 49 flat), limit-up 38→40, limit-down 2→21 (crossing the 10-name warning pre-set on 09-10), down-stocks 88.3%; SSE −1.18% (3888.11) below all MAs with an intraday BOLL-band break (3852.03 vs 3866.35), MACD histogram flipped negative and expanding (−7.23), RSI6 28.43 near oversold; SZ −1.08% (13471.26), ChiNext −0.49% (3322.04). Turnover expanded to ¥1.97tn (105.3% of 5d avg, +¥320bn d/d) — a shrinking grind became expanding panic. Ground ArmamentⅡ +4.44% (main +¥5.02bn offensive buying) leads, Comm Equipment +1.66% (main +¥83.99bn) / Components +1.80% (+¥63.8bn) follow — defence + hardware tech are the only direction with real absorption; Industrial Metals −5.04% leads losers (retail absorbing, effectively distribution). Only 33 of 927 sectors green, 733 distributing. Ladder 40 names flat, top board 4 (Ruierte, new leader). Margin & main-5d data missing (not fabricated). PE_TTM 20.09 (52w pctile 33.9%). All 09-10 pre-set triggers fired; risk raised to High.\""""
    tail = "    }\n  ];\n  REPORTS.reverse();"
    assert tail in hub, "hub tail not found"
    hub = hub.replace(tail, entry + "\n    }\n  ];\n  REPORTS.reverse();", 1)
    open(HUB, "w", encoding="utf-8").write(hub)
    print("[ok] hub 已插入 0911 条目")
else:
    print("[skip] hub 已有 0911 条目")

# ============================================================
# 7) 写出 + 校验
# ============================================================
open(OUT, "w", encoding="utf-8").write(html)
print("[ok] 写出 %s (%d bytes)" % (OUT, len(html)))

leftover = ["17%</text>", "81%</text>", "955", "4512", "航海装备Ⅱ", "种植业 −5.09%",
            "桂林旅游 4板", "¥1.65万亿", "3934.40", "13617.67", "3951.51",
            "（环比 −2100亿", "09-10 · 收盘", "缩量普跌 · 退潮加速", "Next-Session Outlook (09-11",
            "城商行Ⅱ +2.39%", "中际旭创"]
bad = [s for s in leftover if s in html]
print("[校验] 残留旧数据:", bad if bad else "无")
