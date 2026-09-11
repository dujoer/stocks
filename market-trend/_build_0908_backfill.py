# -*- coding: utf-8 -*-
"""群体心理风险雷达 2026-09-08 回补：以 09-11 页为模板，全部动态内容覆盖。

数据来源（全部真实、口径逐一标注）：
  指数/成交/技术 = westock data_kline 260根自算（与官方 market_statis_technical@09-07 锚点核验偏差 0.0000）
  广度 = iFinD search_securities 历史日筛选（09-08 涨3414/跌2025，平=总数-涨-跌）
  涨停/连板 = westock tool_ranking 快照 quant/limitup/2026-09-08.json（74只，最高4板）
  板块 = quant/sector_daily/2026-09-08.json（当日快照）
  估值/轮动 = quant/market_overview/2026-09-09.json（滞后一交易日发布 → 09-08 口径，与 09-09 页引用一致）
  两融 = 接口当时降级，缺失未编造；跌停家数历史源缺失，未编造
"""
import os, re

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "..", "web", "psychology", "crowd-psychology-risk-radar-20260911.html")
OUT = os.path.join(HERE, "..", "web", "psychology", "crowd-psychology-risk-radar-20260908.html")

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

ZH = {
 "t_headline_sub": "2026-09-08 · 收盘",
 "hk_stage": "阶段定性", "hv_stage": "<b>高位轮动 / 沪强创弱</b>（09-08）",
 "hk_upratio": "涨股比", "hv_upratio": "<b>63%</b>（前次 09-07 57% · ↑ 6pct，广度维持偏多）",
 "hk_lim": "涨停 / 跌停", "hv_lim": "<b>74</b> / <b>—</b>（涨停由 90 回落，跌停数据源缺）",
 "hk_amt": "成交额", "hv_amt": "<b>¥1.96万亿</b>（微幅放量 +143亿，为 5 日均 103.3%）",
 "hk_cycle": "情绪周期", "hv_cycle": "<b>高位轮动 / 沪强创弱</b>",
 "hk_risk": "风险等级", "hv_risk": "<b class=\"hl-risk\">中</b>（维持）",
 "hk_flag": "关键提示",
 "hv_flag": "涨股比 57%→<b>63%</b> 维持偏多，但结构急变：09-07 领涨的电子硬件集体回落（半导体 −1.30%、消费电子 −1.79%、电池 −2.06%），资金切向农业链（种植业 +4.91%）与周期（焦炭Ⅱ +5.23%）；创业板 −1.15%（前日 +3.41% 大涨后回落）、上证 +0.20% 沪强创弱；连板高度由 6 板骤降至 4 板（龙版传媒断板），题材一日一换——<b>热度未散、轮动加速</b>；两融与跌停数据缺失，未编造。",
 "tk1": "阶段定性", "tv1": "A股 09-08 由 09-07「科技反攻 / 普涨回暖」转入「<b>高位轮动 / 沪强创弱</b>」：涨股比升至 <b>63%</b>（3414涨 / 2025跌 / 平123，由 57% 再升 6pct），涨停 <b>74</b>（由 90 回落 16 只）、跌停数据源缺失；上证 <b>+0.20%</b>（3940.55，盘中高 3951.32）收于 MA5（3937.37）/ MA20（3936.14）上方、MA10（3947.43）/ MA60（3950.33）下方，均线缠绕；深成 <b>−0.52%</b>（13703.21）、创业板 <b>−1.15%</b>（3359.72，前日 +3.41% 后回落）。与 09-07 的关键差异：<b>指数分化</b>——沪市靠周期与农业链接力，而前日领涨的电子硬件（09-07 反攻主力）集体休整；成交 ¥1.96万亿（5 日均 103.3%、环比 +143亿）量能平稳。情绪仍处高位，但<b>轮动加速本身就是过热后的分歧信号</b>。",
 "tk2": "广度维持偏多", "tv2": "涨股比 <b>63%</b>（前次 57% ↑6pct）· 涨停 <b>74</b>（90→74 回落）· 成交 <b>¥1.96万亿</b>（5 日均 103.3%、10 日均 99.6%、20 日均 94.2%，环比 +143亿）——广度连续第二日改善；但板块结构揭示分化：926 个板块 672 涨 / 250 跌（72.6% 收红）而个股层面 449 个板块呈主力「出货」，上涨由农业链（种植业 主力 +68.63亿建仓 / 农产品加工 +49.91亿抢筹）与周期（焦炭Ⅱ 抢筹）接力，<b>宽度在、主线散</b>。",
 "tk3": "技术缠绕未破位", "tv3": "上证 <b>+0.20%</b>（3940.55）收于 MA5（3937.37）/ MA20（3936.14）上方、MA10（3947.43）/ MA60（3950.33）下方——<b>四线缠绕、方向未选</b>；BOLL（上4001.07 / 中3936.14 / 下3871.21）中轨附近；MACD <b>+1.55</b>（DIF 6.82 / DEA 6.04，红柱较 09-07 的 +2.56 收窄，多头动能衰减）；RSI6 <b>51.09</b>（中性）、KDJ_J 33.97（K 50.73 下穿 D 59.10 死叉雏形）——<b>动能收敛但未破位</b>：创业板 −1.15% 回踩，深成 BOLL 中轨（13992.23）得而复失，短线结构转弱先行于沪市。",
 "tk4": "板块结构", "tv4": "<b>焦炭Ⅱ +5.23%</b>（主力 +5.61亿，抢筹）领涨，<b>农产品加工 +5.02%</b>（主力 +49.91亿 抢筹）/ <b>种植业 +4.91%</b>（主力 +68.63亿 建仓，亚盛集团涨停晋级4板）/ 油服工程 +4.71% / 房地产服务 +4.69% 跟随——<b>农业链 + 周期接力，低价与涨价预期成为避险方向</b>；<b>电池 −2.06%</b>（暗盘 −16.78亿 出货）/ <b>消费电子 −1.79%</b>（−32.38亿 出货）/ 计算机设备 −1.68% / 半导体 −1.30%——09-07 反攻的电子硬件全线休整，926 板块中 449 呈「出货」。",
 "tk5": "连板结构", "tv5": "连板高度由 09-07 的 6 板（龙版传媒）骤降至 <b>4 板</b>（龙版传媒断板退出），<b>亚盛集团 / 百大集团 / 爱仕达</b>由 3 板晋级 4 板，3板海欣食品 / 中国出版 / 敦煌种业，2板13只（中百集团 / 桂林旅游 / 华脉科技 / 科森科技等）；涨停共 74 只（90→74）——<b>龙头断板、高度降级但梯队厚度仍在</b>，农业（亚盛/敦煌种业/海欣食品）与消费（百大/中百）接棒，题材由科技切向农业消费，轮动极快。",
 "tk6": "资金：两融暂缺", "tv6": "两融数据接口降级（service error），<b>未编造</b>；从板块资金看：种植业 主力 +68.63亿（建仓）、农产品加工 +49.91亿（抢筹）、油服工程 +19.38亿——<b>主力在涨价链集中建仓</b>；而消费电子暗盘 −32.38亿、计算机设备 −27.60亿、电池 −16.78亿——<b>09-07 反攻的电子硬件遭主力兑现</b>；杠杆方向无法确认（两融缺），高位轮动期杠杆风险不可视，保持谨慎。",
 "tk7": "估值 / 风格", "tv7": "PE_TTM <b>20.40</b>（10年分位 <b>79.6%</b>、5年 79.68%、3年 66.14%，口径 09-08，较 09-07 的 20.39 微升）；风格：沪深300 5日 <b>+0.54%</b> vs 中证1000 5日 <b>+0.86%</b> 小盘略占优，但 20 日维度全指价值 <b>+3.24%</b> vs 全指成长 <b>−2.82%</b>（差 6.06pct）——<b>价值占优的中期主轴未变</b>，09-08 的农业/周期接力恰是价值防御逻辑的延续；创业板 −1.15% 回吐 09-07 涨幅，成长内部再度分化。",
 "tk8": "情绪周期", "tv8": "由 09-07「科技反攻 / 普涨回暖」转入「<b>高位轮动 / 沪强创弱</b>」：涨股比 63% 维持偏多、涨停 74 只热度仍在，但<b>连板高度 6板→4板、电子硬件休整、农业周期接力</b>——情绪未退潮、结构在换挡；MACD 红柱收窄 + KDJ 死叉雏形提示动能衰减；历史经验：主线一日一换的高位轮动往往是情绪顶部区的典型形态，需以「涨停是否跌破 50 + 涨股比是否失守 50%」作为退潮确认线，风险等级维持<b>中</b>。",
 "t_tldr_text": "A股 09-08 呈现「高位轮动 / 沪强创弱」：涨股比 57%→63%（3414涨/2025跌/平123），涨停 90→74、跌停数据源缺失；上证 +0.20%（3940.55）收于 MA5/20 上方、MA10/60 下方四线缠绕，MACD 红柱收窄（+1.55）、KDJ 死叉雏形；深成 −0.52%（13703.21）、创业板 −1.15%（3359.72，回吐前日 +3.41% 涨幅）。成交 ¥1.96万亿（5 日均 103.3%、环比 +143亿）量能平稳。焦炭Ⅱ +5.23%（抢筹）/ 农产品加工 +5.02%（主力 +49.91亿）/ 种植业 +4.91%（主力 +68.63亿 建仓，亚盛集团晋级4板）领涨——农业链+周期接力；电池 −2.06%（出货）/ 消费电子 −1.79%（−32.38亿 出货）/ 半导体 −1.30%——09-07 反攻的电子硬件集体休整；926 板块 672 涨但 449 呈「出货」。连板高度 6板→4板（龙版传媒断板，亚盛/百大/爱仕达晋级）。两融数据降级缺失（未编造）。估值 PE_TTM 20.40（10Y 分位 79.6%）。全指价值 20日 +3.24% vs 全指成长 −2.82%。热度未散、轮动加速，风险等级维持中。",
 "t_risk": "风险等级", "t_risk_hi": "中",
 "c_upratio": "涨股比", "c_limitup": "涨停", "c_board": "连板高度", "c_pe": "估值 PE分位", "c_pmi": "制造业PMI", "c_turn": "两市成交",
 "t_sec_bias": "行为偏差热力图", "t_cycle": "情绪周期定位（六阶段）",
 "r1": "绝望", "r2": "怀疑", "r3": "乐观", "r4": "狂热", "r5": "焦虑", "r6": "自满",
 "t_cycle_note": "注：上方「乐观 / 高位轮动」为实时群体心理定位（高位轮动 / 沪强创弱）——09-08 涨跌分布（涨股比 63%、涨停 74、成交 ¥1.96万亿）显示热度延续但动能收敛：连板高度 6板→4板、电子硬件休整、MACD 红柱收窄，情绪处「乐观→自满」过渡带；两融与跌停数据缺失。若 09-09 涨停跌破 50 只且涨股比失守 50%，确认退潮启动；若农业/周期接力失败且电子硬件无第二波，轮动将转为普跌。",
 "t_leg": "严重度（由数据综合映射）", "t_bias_note": "注：偏差严重度为基于下方真实数据的模型映射（1=低，5=高），用于呈现群体心理的脆弱点分布，并非对个股的买卖建议。",
 "t_sec_radar": "风险雷达",
 "t_radar_note": "六维风险读数（0–100，由下方真实数据综合映射，越高代表该维度群体脆弱性越强）：拥挤度 59 / 融资 67 / 换手 52 / 广度 45 / 媒体 58 / 估值 87。拥挤度由 58 升至 59（主线一日一换：电子硬件→农业周期，题材轮动加速但梯队厚度仍在）；融资由 70 降至 67（两融数据降级暂缺，杠杆无法确认，按轮动期中性偏谨慎回落）；换手由 54 降至 52（成交 ¥1.96万亿 与前日 1.95万亿 基本持平，量能平稳）；广度由 46 降至 45（涨股比 57%→63% 连续改善，涨跌结构仍偏多，但 449 板块「出货」提示内部分化，脆弱性维持低位）；媒体由 62 降至 58（涨停 90→74 回落、龙头断板，情绪温度自高位小幅降温）；估值 87 持平（PE_TTM 20.39→20.40 微升，10年分位 79.6% 高悬）。整体脆弱性由「估值 + 融资」主导——热度未散、估值高悬，轮动加速期最大的风险是追高换挡主线。",
 "ax_crowd": "拥挤度", "ax_margin": "融资", "ax_turn": "换手", "ax_breadth": "广度", "ax_media": "媒体情绪", "ax_val": "估值",
 "b_up": "上涨", "b_down": "下跌", "b_flat": "平盘", "b_limitup": "涨停", "b_limitdn": "跌停", "b_amt": "成交额",
 "t_breadth_note": "涨股比 57%→63%（3414涨/2025跌/平123）连续第二日改善、涨停 90→74 回落；成交 ¥1.96万亿（5 日均 103.3%、环比 +143亿）平稳。上证 +0.20%（3940.55，四线缠绕）/ 深成 −0.52%（13703.21）/ 创业板 −1.15%（3359.72）沪强创弱；焦炭Ⅱ +5.23% / 农产品加工 +5.02% / 种植业 +4.91%（主力 +68.63亿）领涨，电池 −2.06% / 消费电子 −1.79% / 半导体 −1.30% 领跌——926 板块 672 收红但 449 呈主力「出货」，宽度在、主线散。",
 "th_metric": "指标", "th_read": "真实读数", "th_interp": "行为金融解读",
 "ev_market": "一、市场广度与总览",
 "ev_upratio": "涨股比",
 "ev_upratio_i": "由 57% 升至 63%（+6pct），涨 3414 / 跌 2025 / 平 123，广度连续第二日改善、参与度偏多；但板块层面 449/926 呈主力「出货」，个股宽度与板块行为背离——上涨质量存疑",
 "ev_limit": "涨停 / 跌停",
 "ev_limit_i": "涨停 74（90→74 回落 16 只）、跌停家数历史数据源缺失（未编造）；连板高度 6板→4板（龙版传媒断板），亚盛集团/百大集团/爱仕达晋级4板——高度降级但梯队仍在，题材由科技切向农业消费",
 "ev_amount": "两市成交额",
 "ev_amount_i": "量能 ¥1.96万亿（5 日均 103.3%、10 日均 99.6%、20 日均 94.2%，环比 +143亿）——量能平稳、 neither 放量出清 nor 缩量避险，高位轮动期的「温水」量价结构",
 "ev_index": "二、核心指数表现（2026-09-08 收盘）",
 "ev_sh": "上证指数",
 "ev_sh_i": "+0.20%（3940.55，盘中高 3951.32 / 低 3925.72），收于 MA5（3937.37）/ MA20（3936.14）上方、MA10（3947.43）/ MA60（3950.33）下方，四线缠绕方向未选；MACD +1.55（DIF 6.82 / DEA 6.04，红柱自 09-07 的 +2.56 收窄）、RSI6 51.09 中性、KDJ_J 33.97（K/D 死叉雏形）；BOLL 中轨（3936.14）附近；PE_TTM 20.40（10年分位 79.6%）",
 "ev_sz": "深证成指",
 "ev_sz_i": "−0.52%（13703.21），BOLL 中轨（13992.23）得而复失，短线结构先行转弱；60 日维度仍深弱",
 "ev_cyb": "创业板指",
 "ev_cyb_i": "−1.15%（3359.72），回吐 09-07 +3.41% 大部分涨幅——科技反攻未能延续，成长风格内部资金再度流出（电池/消费电子/半导体暗盘齐出货）",
 "ev_sector": "三、板块排行与主线",
 "ev_secup": "领涨行业",
 "ev_secup_i": "焦炭Ⅱ +5.23%（主力 +5.61亿 抢筹）领涨，农产品加工 +5.02%（主力 +49.91亿 抢筹）/ 种植业 +4.91%（主力 +68.63亿 建仓，亚盛集团涨停晋级4板）/ 油服工程 +4.71% / 房地产服务 +4.69% 跟随——农业链 + 周期涨价预期接力，926 板块 672 收红（72.6%）",
 "ev_secdn": "领跌行业",
 "ev_secdn_i": "电池 −2.06%（暗盘 −16.78亿 出货）/ 消费电子 −1.79%（−32.38亿 出货）/ 计算机设备 −1.68%（−27.60亿 出货）/ 半导体 −1.30%——09-07 反攻主力电子硬件集体休整并遭主力兑现，领跌集中于前日强势方向",
 "ev_board": "极端题材",
 "ev_board_i": "连板高度 4板（亚盛集团 / 百大集团 / 爱仕达，由3板晋级）；3板：海欣食品 / 中国出版 / 敦煌种业；2板13只（中百集团 / 桂林旅游 / 华脉科技 / 科森科技等）；涨停共 74 只（90→74）——农业消费接棒科技，轮动极快",
 "ev_flow": "四、资金：连板 / 主力 / 两融",
 "ev_height": "连板高度",
 "ev_height_i": "高度 4板（亚盛集团 / 百大集团 / 爱仕达，2026-09-08 收盘，westock 连板名单口径，共 74 只涨停）；龙版传媒 6板断板退出——高度骤降但梯队厚度仍在，投机资金转向农业（亚盛/敦煌种业/海欣食品）与消费（百大/中百）",
 "ev_main": "主力5日净流入TOP",
 "ev_main_i": "主力5日净流入排名接口降级期（tool_ranking service error），无法更新、未编造；当日可见信号：种植业 主力 +68.63亿（建仓）/ 农产品加工 +49.91亿（抢筹）/ 油服工程 +19.38亿 集中流入涨价链，消费电子暗盘 −32.38亿 / 计算机设备 −27.60亿 流出——主力弃「昨日主线」、抢「涨价接力」",
 "ev_margin": "融资单日变动TOP",
 "ev_margin_i": "两融数据接口降级（service error），融资单日变动与两融余额均暂缺，<b>未编造</b>；高位轮动 + 均线缠绕下杠杆方向无法确认，谨慎对待——若融资盘仍集中于电子硬件，其休整将放大杠杆回撤",
 "ev_hot": "热搜 / 领涨TOP",
 "ev_hot_i": "热点由 TMT 切向农业/周期：亚盛集团 4板（种植业涨停）/ 焦炭Ⅱ +5.23%（云煤能源 +10.10%）/ 农产品加工 +5.02%（*ST广糖 +10.08%）/ 房地产服务 +4.69%（世联行 +10.17%）；与「全指价值 20日 +3.24% vs 全指成长 −2.82%」的价值占优主轴一致",
 "ev_margintotal": "市场两融余额",
 "ev_margintotal_i": "缺口：聚合两融余额与融资单日变动接口降级（service error），已如实标注、未编造；涨跌分布（iFinD 历史日筛选）/ 指数（K线自算，与官方锚点偏差0.0000）/ 板块 / 连板名单均为 2026-09-08 真实数据",
 "ev_macro": "五、核心宏观指标",
 "ev_pmi": "制造业PMI（7月）",
 "ev_pmi_i": "基本面收缩，与「高估值 + 高位轮动」组合共存——情绪热度缺乏基本面增量支撑，轮动加速即分歧信号",
 "ev_capu": "产能利用率（Q2）",
 "ev_capu_i": "实物经济动能走弱，涨价链（农业/周期）的预期缺乏产能端验证",
 "ev_cpi": "CPI（7月）",
 "ev_cpi_i": "低通胀、需求偏弱，农产品涨价的持续性待数据确认",
 "ev_social": "社融（7月）",
 "ev_social_i": "信用需求弱，资金绕道股市 = 流动性驱动特征，高位轮动期流动性预期敏感",
 "ev_m1m2": "M1-M2 剪刀差",
 "ev_m1m2_i": "活钱偏弱，资金空转，典型后周期现象",
 "ev_yield": "10Y 国债收益率",
 "ev_yield_i": "极低无风险利率，既支撑估值也反映增长担忧",
 "ev_lpr": "LPR",
 "ev_lpr_i": "宽松基调未变",
 "t_ev_note": "数据口径：宏观指标多截至 2026-07（月频）或沿用前期值；涨跌分布（iFinD 历史日筛选：涨3414/跌2025）/ 指数与成交（data_kline 自算，与官方 market_statis_technical@09-07 锚点核验偏差 0.0000）/ 板块（sector_daily 当日快照）/ 连板（westock 连板名单 74 只）均为 2026-09-08 真实数据。估值 PE_TTM 20.40 为 09-08 口径（中证全指，滞后一交易日发布，与 09-09 页引用一致）；两融与跌停家数缺失，已如实标注未编造。详见末尾「数据来源与日期口径」。",
 "t_sec_risk": "风险分层",
 "rc1_tag": "红线区 · 估值高悬 + 杠杆不可视",
 "rc1_t": "高位轮动下的估值与杠杆盲区",
 "rc1_d": "PE_TTM 10年分位 79.6% 高悬 + 两融数据缺失（杠杆方向不可视）+ 连板高度骤降（6板→4板）——情绪热度与估值风险错配：热度掩盖估值，一旦退潮估值回归与杠杆踩踏同步发生；涨股比 63% 的偏多宽度不构成安全垫。",
 "rc1_rep": "代表：两融集中且已现暗盘流出的电子硬件（消费电子 −32.38亿 / 计算机设备 −27.60亿）/ 高位连板接力（龙版传媒断板示范）",
 "rc1_cond": "条件框架：不追高换挡主线；对「昨日强势+今日暗盘流出」方向保持警惕；跌停与两融数据恢复前，杠杆暴露只减不加。",
 "rc2_tag": "黄线区 · 轮动加速的博弈",
 "rc2_t": "主线一日一换 vs 梯队厚度",
 "rc2_d": "连板高度 6板→4板但 2板仍有 13 只、涨停 74 只——高度降级、厚度仍在：投机情绪未死、只是换挡；农业（亚盛/敦煌种业/海欣食品）与消费（百大/中百）接棒电子硬件。轮动加速期 chase 容易两头挨打。",
 "rc2_rep": "代表：农业链（种植业/农产品加工/渔业）/ 周期涨价（焦炭Ⅱ/油服工程）/ 消费低位（百货）",
 "rc2_cond": "条件框架：轮动期只做观察跟踪，不追当日涨幅；确认信号 = 新主线连续 2 日主力净流入且高度重新向上；若接力失败（涨停跌破 50），转入防守。",
 "rc3_tag": "绿线区 · 涨价链主力建仓",
 "rc3_t": "农业 / 周期涨价链获主力真实建仓",
 "rc3_d": "种植业 主力 +68.63亿（建仓）、农产品加工 +49.91亿（抢筹）、油服工程 +19.38亿（建仓）、焦炭Ⅱ +5.61亿（抢筹）——主力在涨价预期方向真实投放筹码，与 20 日维度价值占优（+3.24% vs −2.82%）的中期主轴一致。",
 "rc3_rep": "代表：种植业（亚盛集团 4板）/ 农产品加工 / 焦炭Ⅱ / 油服工程 / 房地产服务",
 "rc3_cond": "条件框架：仅作结构跟踪，涨停潮次日不追高；确认信号 = 该方向主力净流入延续且板块换手不萎缩；若 CPI/产业数据证伪涨价预期，及时修正。",
 "t_sec_outlook": "下个交易日（09-09 周三）展望",
 "o_logic": "研判逻辑（基于 09-08 收盘 + 群体心理定位）",
 "o_logic_text": "由 09-08 的「高位轮动 / 沪强创弱」延伸：热度延续（涨股比 63%、涨停 74）但动能收敛（连板高度骤降、MACD 红柱收窄、KDJ 死叉雏形、电子硬件暗盘出货）——轮动加速期向「分化」演化的概率在上升。基于此推演 09-09 的板块方向与交易规则（<b>不涉及具体个股推荐</b>）。",
 "o1_tag": "涨价链接力方向（观察）",
 "o1_t": "种植业 / 农产品加工 / 焦炭Ⅱ / 油服工程",
 "o1_d": "09-08 获主力真实建仓/抢筹的方向（种植业 +68.63亿、农产品加工 +49.91亿），若 09-09 延续净流入，则轮动主线确认、情绪以「换挡」而非「退潮」消化。",
 "o1_cond": "注意：农业/周期题材对消息面敏感、持续性历史偏弱；确认标准 = 连续 2 日主力净流入 + 高度重新向上；若一日游，轮动将直接转入退潮。",
 "o2_tag": "电子硬件兑现方向（回避）",
 "o2_t": "消费电子 / 计算机设备 / 电池 / 高位连板",
 "o2_d": "09-07 反攻主力在 09-08 遭主力兑现（消费电子暗盘 −32.38亿、计算机设备 −27.60亿、电池 −16.78亿），创业板 −1.15% 同步回吐——若两融盘仍滞留其中，休整将放大为回撤。",
 "o2_cond": "注意：暗盘连续流出方向不做左侧承接；等待暗盘转正 + 缩量止跌；高位连板接力（龙头断板后）胜率显著下降。",
 "o3_tag": "退潮确认信号（警戒）",
 "o3_t": "涨停跌破 50 / 涨股比失守 50% / 高度不再",
 "o3_d": "09-08 涨停 74（90→74 连续回落）、连板高度 4 板（骤降）——若 09-09 涨停跌破 50 只或涨股比失守 50%，则「高位轮动」确认转为「退潮」，届时压缩风险敞口。",
 "o3_cond": "注意：轮动转退潮的过程通常伴随创业板补跌带动指数走弱；确认前维持中性仓位，确认后执行防守纪律；右侧信号 = 缩量企稳 + 新主线高度重建。",
 "o_rules_t": "交易规则（09-09）",
 "o_r1": "<b>仓位</b>：高位轮动期维持中性仓位（≤5 成），不加杠杆；涨股比 63% 的宽度不构成加仓理由——449 板块「出货」提示上涨质量存疑。",
 "o_r2": "<b>退潮确认</b>：涨停跌破 50 只或涨股比失守 50%，视为轮动转退潮，压缩至防守仓位；连板高度若重新向上（新龙头 5板+），视为情绪换挡成功。",
 "o_r3": "<b>主线参与</b>：涨价链（农业/周期）仅作结构观察（主力净流入是否延续），涨停潮次日不追；电子硬件等暗盘流出方向回避，等待暗盘转正。",
 "o_r4": "<b>回避清单</b>：暗盘连续流出的电子硬件高位方向、断板龙头（龙版传媒模式）、两融集中且杠杆不可视的方向、一日游题材追高。",
 "o_r5": "<b>风控</b>：均线缠绕期不预判方向，以 BOLL 中轨（上证 3936）为多空分界；跌破中轨且涨停续降，执行防守；两融数据恢复前不加重杠杆。",
 "o_compliance": "<b>合规说明：</b>本展望仅给出板块方向与交易规则，不涉及具体个股推荐；群体心理定位与板块推断基于 2026-09-08 真实行情数据，市场有风险，决策须独立。",
 "t_sec_source": "数据来源与日期口径",
 "s_breadth": "涨跌分布 / 总览",
 "s_breadth_v": "iFinD search_securities 历史日筛选（09-08 涨 3414 / 跌 2025，平 = 总数−涨−跌）；2026-09-08 收盘（westock updown 快照当日缺，回补期替代源）",
 "s_portrait": "市场画像 summary",
 "s_portrait_v": "回补组装：iFinD 历史日筛选 + data_kline 自算 + sector_daily 当日快照；2026-09-08（涨股比 63%、高位轮动）",
 "s_index": "指数表现",
 "s_index_v": "westock data_kline 260 根自算（MA/BOLL/MACD/RSI/KDJ 与官方 market_statis_technical@09-07 锚点核验偏差 0.0000）；2026-09-08 收盘",
 "s_sector": "板块排行 / 资金流",
 "s_sector_v": "westock · data_sector 当日快照（quant/sector_daily/2026-09-08.json）；2026-09-08（926 板块，672 收红、449 出货）",
 "s_hot": "热搜股票",
 "s_hot_v": "westock · 领涨板块+涨停名单综合（data_hot 历史缺，回补期以板块领涨股替代）；2026-09-08（农业/周期/地产服务居前）",
 "s_macro": "核心宏观",
 "s_macro_v": "westock · data_macro 前期复核（月频）；PMI/产能/社融为前期值，CPI/M1-M2/10Y/LPR 沿用前期",
 "s_margin": "两融（个股）",
 "s_margin_v": "westock · 两融接口降级（service error）+ 历史回补窗口无快照，数据暂缺，未编造",
 "s_main": "主力5日净流入",
 "s_main_v": "westock · tool_ranking 降级期（service error）+ 历史快照缺，无法回补；当日主力行为由 sector_daily 板块资金（主力/散户/暗盘）呈现",
 "s_board": "连板高度",
 "s_board_v": "westock · tool_ranking 连板名单快照（quant/limitup/2026-09-08.json，涨停共 74 只）；2026-09-08（最高 4板：亚盛集团/百大集团/爱仕达）",
 "s_gap": "数据缺口",
 "s_gap_v": "两融余额、融资单日变动、主力5日排名、跌停家数在 09-08 回补窗口无真实数据源，均已如实标注、未编造；估值 PE_TTM 20.40 为 09-08 口径（中证全指，滞后一交易日发布）；涨跌分布为 iFinD 历史日筛选口径（与 westock updown 口径或有细微差异）",
 "t_src_note": "时间口径：所有时点按北京时间。宏观为月频 / 季频，与日频行情不可直接对齐，已分别标注。涨跌分布 / 指数 / 板块 / 连板名单均为 2026-09-08 当日真实数据（回补期：广度来自 iFinD 历史筛选、指数技术来自 K 线自算并经官方锚点核验）；两融、主力5日、跌停家数暂缺，均已标注。",
 "disc1": "免责声明：以上内容基于公开数据和量化分析，仅供参考，不构成投资建议。市场有风险，投资需谨慎。任何投资决策应结合个人风险承受能力、资金状况和投资目标独立判断，必要时咨询持牌专业机构。过往表现不预示未来收益。",
 "disc2": "本研判为「群体心理 / 条件框架」分析，非买卖指令；风险读数与偏差严重度为模型综合映射，须与价格结构、估值、资金流向交叉验证，不可单独作为交易依据。",
 "t_foot": "群体心理风险雷达 · 由 westock / iFinD 官方行情数据生成 · 仅供研究参考",
}

EN = {
 "t_headline_sub": "2026-09-08 · Close",
 "hk_stage": "Stage", "hv_stage": "<b>High-level rotation / SH strong, ChiNext weak</b> (09-08)",
 "hk_upratio": "Up-ratio", "hv_upratio": "<b>63%</b> (prev 09-07 57% · ↑ 6pct, breadth stays positive)",
 "hk_lim": "Limit-up / -down", "hv_lim": "<b>74</b> / <b>—</b> (limit-up eases from 90, limit-down data missing)",
 "hk_amt": "Turnover", "hv_amt": "<b>¥1.96tn</b> (slightly expanding +¥14.3bn, 103.3% of 5d avg)",
 "hk_cycle": "Sentiment cycle", "hv_cycle": "<b>High-level rotation / SH strong, ChiNext weak</b>",
 "hk_risk": "Risk level", "hv_risk": "<b class=\"hl-risk\">Medium</b> (unchanged)",
 "hk_flag": "Key flag",
 "hv_flag": "Up-ratio 57%→<b>63%</b> stays positive but the structure swung hard: Monday's electronics leaders all paused (Semis −1.30%, Consumer Electronics −1.79%, Batteries −2.06%) as capital rotated into the agriculture chain (Planting +4.91%) and cyclicals (CokeⅡ +5.23%); ChiNext −1.15% (giving back Monday's +3.41%), SSE +0.20% — SH strong, growth weak; ladder height collapsed 6→4 boards (Longban Media broke) — <b>heat intact, rotation accelerating</b>; margin & limit-down data missing, not fabricated.",
 "tk1": "Stage", "tv1": "A-shares 09-08 shift from 09-07's 'tech counterattack / broad recovery' into '<b>high-level rotation / SH strong, ChiNext weak</b>': up-ratio rises to <b>63%</b> (3414 up / 2025 down / 123 flat, +6pct from 57%), limit-up <b>74</b> (down 16 from 90), limit-down data missing; SSE <b>+0.20%</b> (3940.55, intraday high 3951.32) closes above MA5 (3937.37) / MA20 (3936.14), below MA10 (3947.43) / MA60 (3950.33) — MAs intertwined; SZ <b>−0.52%</b> (13703.21), ChiNext <b>−1.15%</b> (3359.72, giving back Monday's +3.41%). Key difference vs 09-07: <b>index divergence</b> — SH carried by cyclicals and agriculture while the electronics hardware that led Monday's counterattack rested; turnover ¥1.96tn (103.3% of 5d avg, +¥14.3bn) steady. Sentiment still elevated, but <b>accelerating rotation itself is a divergence signal after overheating</b>.",
 "tk2": "Breadth stays positive", "tv2": "Up-ratio <b>63%</b> (prev 57%, ↑6pct) · limit-up <b>74</b> (90→74) · turnover <b>¥1.96tn</b> (103.3% of 5d avg, 99.6% of 10d, 94.2% of 20d, +¥14.3bn) — breadth improves a second day; but sector structure reveals divergence: 672 of 926 sectors green (72.6%) while 449 sectors show main-capital 'distribution' — gains led by agriculture (Planting main +¥6.86bn accumulation / Farm-Product Processing +¥4.99bn offensive buying) and cyclicals (CokeⅡ offensive buying), <b>breadth yes, clear main line no</b>.",
 "tk3": "Technicals intertwined, no breakdown", "tv3": "SSE <b>+0.20%</b> (3940.55) closes above MA5 (3937.37) / MA20 (3936.14), below MA10 (3947.43) / MA60 (3950.33) — <b>four MAs intertwined, direction unresolved</b>; near BOLL mid-band (3936.14 of 4001.07/3936.14/3871.21); MACD <b>+1.55</b> (DIF 6.82 / DEA 6.04, histogram narrowing from 09-07's +2.56, momentum fading); RSI6 <b>51.09</b> (neutral), KDJ_J 33.97 (K 50.73 crossing below D 59.10, nascent dead-cross) — <b>momentum converging but no breakdown</b>: ChiNext −1.15% pulls back, SZ lost the BOLL mid-band (13992.23) — short-term structure weakening ahead of the SH side.",
 "tk4": "Sector structure", "tv4": "<b>CokeⅡ +5.23%</b> (main +¥0.56bn, offensive buying) leads, <b>Farm-Product Processing +5.02%</b> (main +¥4.99bn offensive buying) / <b>Planting +4.91%</b> (main +¥6.86bn accumulation, Yasheng Group limit-up to 4 boards) / Oilfield Services +4.71% / Real-Estate Services +4.69% follow — <b>agriculture chain + cyclicals take the baton, low-price and price-hike expectations become the shelter</b>; <b>Batteries −2.06%</b> (dark −¥1.68bn distribution) / <b>Consumer Electronics −1.79%</b> (−¥3.24bn distribution) / Computer Equipment −1.68% / Semiconductors −1.30% — Monday's electronics counterattack pauses across the board, 449 of 926 sectors 'distributing'.",
 "tk5": "Limit-up ladder", "tv5": "Ladder height collapses from 09-07's 6 boards (Longban Media) to <b>4 boards</b> (Longban Media broke), <b>Yasheng Group / Baida Group / Aishida</b> advance 3→4 boards, 3-board Haixin Food / China Publishing / Dunhuang Seed, 13 two-board names (Zhongbai Group / Guilin Tourism / Huamai Tech / Kesun Tech etc.); 74 limit-ups total (90→74) — <b>leader broke, height down, but the ladder's base remains</b>; agriculture (Yasheng/Dunhuang/Haixin) and consumer (Baida/Zhongbai) take over from tech, rotation extremely fast.",
 "tk6": "Capital: margin missing", "tv6": "The margin interface is degraded (service error), <b>not fabricated</b>; from sector flows: Planting main +¥6.86bn (accumulation), Farm-Product Processing +¥4.99bn (offensive buying), Oilfield Services +¥1.94bn — <b>mains genuinely building in the price-hike chain</b>; while Consumer Electronics dark −¥3.24bn, Computer Equipment −¥2.76bn, Batteries −¥1.68bn — <b>Monday's electronics leaders are being distributed</b>; leverage direction unconfirmable (margin missing), stay cautious in a high-level rotation.",
 "tk7": "Valuation / style", "tv7": "PE_TTM <b>20.40</b> (10Y percentile <b>79.6%</b>, 5Y 79.68%, 3Y 66.14%; 09-08 basis, up slightly from 09-07's 20.39); style: HS300 5-day <b>+0.54%</b> vs CSI1000 5-day <b>+0.86%</b> — small caps slightly ahead; on 20 days All-Share Value <b>+3.24%</b> vs All-Share Growth <b>−2.82%</b> (6.06pct gap) — <b>the value-over-growth medium-term axis is intact</b>; the agriculture/cyclical relay is exactly the defensive-value logic continuing; ChiNext −1.15% gives back Monday's gain, growth diverging again internally.",
 "tk8": "Sentiment cycle", "tv8": "From 09-07's 'tech counterattack / broad recovery' into '<b>high-level rotation / SH strong, ChiNext weak</b>': up-ratio 63% stays positive, 74 limit-ups keep the heat, but <b>ladder 6→4 boards, electronics resting, agriculture/cyclicals relaying</b> — sentiment not ebbing, structure shifting gears; MACD histogram narrowing + nascent KDJ dead-cross flag fading momentum; historically, main lines changing daily in a high-level rotation is a classic top-zone pattern — use 'limit-ups below 50 + up-ratio losing 50%' as the ebbing confirmation line; risk stays <b>Medium</b>.",
 "t_tldr_text": "A-shares 09-08 = 'high-level rotation / SH strong, ChiNext weak': up-ratio 57%→63% (3414 up / 2025 down / 123 flat), limit-up 90→74, limit-down data missing; SSE +0.20% (3940.55) above MA5/20, below MA10/60 with MAs intertwined, MACD histogram narrowing (+1.55), nascent KDJ dead-cross; SZ −0.52% (13703.21), ChiNext −1.15% (3359.72, giving back +3.41%). Turnover ¥1.96tn (103.3% of 5d avg, +¥14.3bn) steady. CokeⅡ +5.23% (offensive buying) / Farm-Product Processing +5.02% (main +¥4.99bn) / Planting +4.91% (main +¥6.86bn, Yasheng to 4 boards) lead — agriculture + cyclicals relay; Batteries −2.06% (distribution) / Consumer Electronics −1.79% (−¥3.24bn) / Semis −1.30% — Monday's electronics leaders all pause; 672 of 926 sectors green but 449 distributing. Ladder 6→4 boards (Longban Media broke; Yasheng/Baida/Aishida advance). Margin data missing (not fabricated). PE_TTM 20.40 (10Y pctile 79.6%). All-Share Value 20d +3.24% vs Growth −2.82%. Heat intact, rotation accelerating; risk stays Medium.",
 "t_risk": "Risk level", "t_risk_hi": "Medium",
 "c_upratio": "Up-ratio", "c_limitup": "Limit-up", "c_board": "Ladder height", "c_pe": "PE pctile", "c_pmi": "Mfg PMI", "c_turn": "Turnover",
 "t_sec_bias": "Behavioral Bias Heatmap", "t_cycle": "Sentiment Cycle (6-stage)",
 "r1": "Despair", "r2": "Doubt", "r3": "Optimism", "r4": "Euphoria", "r5": "Anxiety", "r6": "Complacency",
 "t_cycle_note": "Note: the 'Optimism / high-level rotation' tag above is the live crowd-psychology position (high-level rotation / SH strong, ChiNext weak) — 09-08 breadth (up-ratio 63%, limit-up 74, turnover ¥1.96tn) shows heat continuing while momentum converges: ladder 6→4 boards, electronics resting, MACD histogram narrowing — the mood sits in the 'Optimism→Complacency' transition band; margin & limit-down data missing. If 09-09 sees limit-ups below 50 and up-ratio losing 50%, the ebb is confirmed; if the agriculture/cyclical relay fails and electronics find no second wave, rotation turns into a broad decline.",
 "t_leg": "Severity (model-mapped)", "t_bias_note": "Note: bias severity is a model mapping from the real data below (1=low, 5=high), used to show where crowd psychology is fragile — not a buy/sell recommendation for any stock.",
 "t_sec_radar": "Risk Radar",
 "t_radar_note": "Six-dimension risk readings (0–100, mapped from the real data below; higher = greater crowd fragility on that axis): crowding 59 / margin 67 / turnover 52 / breadth 45 / media 58 / valuation 87. Crowding 58→59 (main line changes daily: electronics→agriculture/cyclicals, rotation accelerating though the ladder base remains); margin 70→67 (margin data degraded and missing, leverage unconfirmable, eased to neutral-cautious for a rotation phase); turnover 54→52 (turnover ¥1.96tn roughly flat vs 1.95tn); breadth 46→45 (up-ratio 57%→63% improving a second day, structure still positive, yet 449 sectors 'distributing' hints at internal divergence — fragility stays low); media 62→58 (limit-ups 90→74, leader broke — temperature easing from the high); valuation 87 flat (PE_TTM 20.39→20.40, 10Y percentile 79.6% elevated). Fragility is led by 'valuation + margin' — heat intact with valuation stretched; the biggest risk in an accelerating rotation is chasing the shifting main line at the top.",
 "ax_crowd": "Crowding", "ax_margin": "Margin", "ax_turn": "Turnover", "ax_breadth": "Breadth", "ax_media": "Media mood", "ax_val": "Valuation",
 "b_up": "Up", "b_down": "Down", "b_flat": "Flat", "b_limitup": "Limit-up", "b_limitdn": "Limit-down", "b_amt": "Turnover",
 "t_breadth_note": "Up-ratio 57%→63% (3414 up / 2025 down / 123 flat) improves a second day, limit-ups 90→74 easing; turnover ¥1.96tn (103.3% of 5d avg, +¥14.3bn) steady. SSE +0.20% (3940.55, MAs intertwined) / SZ −0.52% (13703.21) / ChiNext −1.15% (3359.72) — SH strong, growth weak; CokeⅡ +5.23% / Farm-Product Processing +5.02% / Planting +4.91% (main +¥6.86bn) lead, Batteries −2.06% / Consumer Electronics −1.79% / Semis −1.30% lag — 672 of 926 sectors green while 449 'distribute': breadth yes, quality questionable.",
 "th_metric": "Metric", "th_read": "Real reading", "th_interp": "Behavioral read",
 "ev_market": "I. Market breadth & overview",
 "ev_upratio": "Up-ratio",
 "ev_upratio_i": "57%→63% (+6pct), 3414 up / 2025 down / 123 flat — breadth improves a second day, participation positive; yet 449/926 sectors show main-capital 'distribution' — stock breadth diverges from sector behaviour, quality of the advance is in question",
 "ev_limit": "Limit-up / -down",
 "ev_limit_i": "Limit-up 74 (90→74, −16), limit-down count missing for this historical window (not fabricated); ladder height 6→4 boards (Longban Media broke), Yasheng / Baida / Aishida advance to 4 — height down but base intact, themes rotating from tech to agriculture/consumer",
 "ev_amount": "Turnover",
 "ev_amount_i": "¥1.96tn (103.3% of 5d avg, 99.6% of 10d, 94.2% of 20d, +¥14.3bn) — volume steady, neither expanding wash-out nor shrinking shelter: the 'lukewarm' volume-price texture of a high-level rotation",
 "ev_index": "II. Core indices (2026-09-08 close)",
 "ev_sh": "SSE Composite",
 "ev_sh_i": "+0.20% (3940.55, high 3951.32 / low 3925.72), above MA5 (3937.37) / MA20 (3936.14), below MA10 (3947.43) / MA60 (3950.33) — four MAs intertwined, direction unresolved; MACD +1.55 (DIF 6.82 / DEA 6.04, histogram narrowing from +2.56), RSI6 51.09 neutral, KDJ_J 33.97 (K/D nascent dead-cross); near BOLL mid-band (3936.14); PE_TTM 20.40 (10Y pctile 79.6%)",
 "ev_sz": "SZ Component",
 "ev_sz_i": "−0.52% (13703.21), lost the BOLL mid-band (13992.23) — short-term structure weakening first; still deeply weak on 60 days",
 "ev_cyb": "ChiNext",
 "ev_cyb_i": "−1.15% (3359.72), giving back most of 09-07's +3.41% — the tech counterattack failed to extend, growth-style capital flowing out again (Batteries / Consumer Electronics / Semis dark flows all negative)",
 "ev_sector": "III. Sector ranking & main line",
 "ev_secup": "Leading sectors",
 "ev_secup_i": "CokeⅡ +5.23% (main +¥0.56bn offensive buying) leads, Farm-Product Processing +5.02% (main +¥4.99bn offensive buying) / Planting +4.91% (main +¥6.86bn accumulation, Yasheng limit-up to 4 boards) / Oilfield Services +4.71% / Real-Estate Services +4.69% follow — agriculture chain + cyclical price-hike expectations relay; 672 of 926 sectors green (72.6%)",
 "ev_secdn": "Lagging sectors",
 "ev_secdn_i": "Batteries −2.06% (dark −¥1.68bn distribution) / Consumer Electronics −1.79% (−¥3.24bn distribution) / Computer Equipment −1.68% (−¥2.76bn distribution) / Semiconductors −1.30% — Monday's electronics leaders pause collectively and are being distributed; laggards cluster in yesterday's strength",
 "ev_board": "Extreme themes",
 "ev_board_i": "Ladder height 4 boards (Yasheng Group / Baida Group / Aishida, advanced from 3); 3-board Haixin Food / China Publishing / Dunhuang Seed; 13 two-board names (Zhongbai / Guilin Tourism / Huamai / Kesun etc.); 74 limit-ups total (90→74) — agriculture & consumer take over from tech, rotation extremely fast",
 "ev_flow": "IV. Capital: ladder / main / margin",
 "ev_height": "Ladder height",
 "ev_height_i": "Height 4 boards (Yasheng / Baida / Aishida, 2026-09-08 close, westock ladder-list basis, 74 limit-ups total); Longban Media's 6-board run broke — height collapsed but the base holds; speculative money shifts to agriculture (Yasheng/Dunhuang/Haixin) and consumer (Baida/Zhongbai)",
 "ev_main": "Main capital 5d net inflow TOP",
 "ev_main_i": "Main-5d ranking interface degraded (tool_ranking service error) — cannot update, not fabricated; visible same-day signals: Planting main +¥6.86bn (accumulation) / Farm-Product Processing +¥4.99bn (offensive buying) / Oilfield Services +¥1.94bn concentrated into the price-hike chain; Consumer Electronics dark −¥3.24bn / Computer Equipment −¥2.76bn out — mains abandon 'yesterday's line' and grab the 'price-hike relay'",
 "ev_margin": "Daily margin change TOP",
 "ev_margin_i": "The margin interface is degraded (service error); daily margin change and aggregate balance both unavailable — <b>not fabricated</b>; with high-level rotation + intertwined MAs, the leverage direction is unconfirmable — if margin remains concentrated in electronics hardware, its pause would amplify the leveraged drawdown",
 "ev_hot": "Hot / top gainers",
 "ev_hot_i": "Hotspots rotate from TMT to agriculture/cyclicals: Yasheng Group 4 boards (Planting limit-up) / CokeⅡ +5.23% (Yunmei Energy +10.10%) / Farm-Product Processing +5.02% (*ST Guangtang +10.08%) / Real-Estate Services +4.69% (Shilianhang +10.17%); consistent with the value-over-growth axis (All-Share Value 20d +3.24% vs Growth −2.82%)",
 "ev_margintotal": "Aggregate margin balance",
 "ev_margintotal_i": "Gap: aggregate margin balance and daily margin change interfaces degraded (service error) — flagged honestly, not fabricated; breadth (iFinD historical-day screen) / indices (kline self-computed, 0.0000 deviation vs official anchor) / sectors / ladder list are all real 2026-09-08 data",
 "ev_macro": "V. Core macro indicators",
 "ev_pmi": "Mfg PMI (Jul)",
 "ev_pmi_i": "Fundamentals contract while 'high valuation + high-level rotation' coexist — sentiment heat lacks a fundamental catalyst; accelerating rotation = divergence signal",
 "ev_capu": "Capacity utilisation (Q2)",
 "ev_capu_i": "Real-economy momentum weakens; the price-hike chain's (agriculture/cyclicals) expectations lack capacity-side verification",
 "ev_cpi": "CPI (Jul)",
 "ev_cpi_i": "Low inflation, weak demand; the durability of agricultural price gains awaits data confirmation",
 "ev_social": "Social financing (Jul)",
 "ev_social_i": "Weak credit demand, capital detours into stocks = liquidity-driven; in a high-level rotation, liquidity expectations are sensitive",
 "ev_m1m2": "M1-M2 spread",
 "ev_m1m2_i": "Active money weak, capital idles, typical late-cycle phenomenon",
 "ev_yield": "10Y gov bond yield",
 "ev_yield_i": "Extremely low risk-free rate, supports valuation yet reflects growth worry",
 "ev_lpr": "LPR",
 "ev_lpr_i": "Accommodative stance unchanged",
 "t_ev_note": "Data basis: macro indicators are monthly (to 2026-07) or carried forward; breadth (iFinD historical-day screen: 3414 up / 2025 down) / indices & turnover (data_kline self-computed, 0.0000 deviation vs official market_statis_technical@09-07 anchor) / sectors (sector_daily same-day snapshot) / ladder (westock list, 74 limit-ups) are real 2026-09-08 data. Valuation PE_TTM 20.40 is 09-08 basis (CSI All-Share, published with a one-session lag, consistent with the 09-09 page citation); margin & limit-down count missing — flagged, not fabricated. See 'Sources and date basis' at the end.",
 "t_sec_risk": "Risk Stratification",
 "rc1_tag": "Red zone · Stretched valuation + invisible leverage",
 "rc1_t": "Valuation and leverage blind spots in a high-level rotation",
 "rc1_d": "PE_TTM 10Y percentile 79.6% elevated + margin data missing (leverage invisible) + ladder height collapsing (6→4 boards) — sentiment heat and valuation risk are mismatched: heat masks valuation, and once the ebb starts, mean-reversion and leveraged unwinding hit together; the positive 63% up-ratio is no safety cushion.",
 "rc1_rep": "Represented by: electronics hardware with dark-flow outflows (Consumer Electronics −¥3.24bn / Computer Equipment −¥2.76bn) / high-ladder relay (Longban Media's break as the showcase)",
 "rc1_cond": "Condition frame: do not chase the shifting main line at highs; stay wary of 'yesterday strong + today dark outflow' directions; until limit-down and margin data resume, leverage exposure only shrinks.",
 "rc2_tag": "Amber zone · Accelerating rotation",
 "rc2_t": "Main line changing daily vs ladder depth",
 "rc2_d": "Ladder height 6→4 boards but 13 two-board names and 74 limit-ups remain — height down, depth intact: speculative sentiment is not dead, just shifting gears; agriculture (Yasheng/Dunhuang/Haixin) and consumer (Baida/Zhongbai) take over from electronics. In an accelerating rotation, chasing both ways gets whipsawed.",
 "rc2_rep": "Represented by: agriculture chain (Planting / Farm-Product Processing / Fisheries) / cyclical price-hike (CokeⅡ / Oilfield Services) / low-position consumer (dept stores)",
 "rc2_cond": "Condition frame: rotation phases are for observation only, no chasing the day's gains; confirmation = the new line keeps main inflows 2 straight days and height rebuilds upward; if the relay fails (limit-ups below 50), switch to defence.",
 "rc3_tag": "Green zone · Main capital building in the price-hike chain",
 "rc3_t": "Agriculture / cyclical price-hike chain gets real accumulation",
 "rc3_d": "Planting main +¥6.86bn (accumulation), Farm-Product Processing +¥4.99bn (offensive buying), Oilfield Services +¥1.94bn (accumulation), CokeⅡ +¥0.56bn (offensive buying) — mains genuinely deploying into price-hike expectations, consistent with the 20-day value-over-growth axis (+3.24% vs −2.82%).",
 "rc3_rep": "Represented by: Planting (Yasheng 4 boards) / Farm-Product Processing / CokeⅡ / Oilfield Services / Real-Estate Services",
 "rc3_cond": "Condition frame: structure tracking only, no chasing the day after a limit-up wave; confirmation = sustained main inflows and unshrinking turnover; if CPI/industry data falsify the price-hike expectation, correct promptly.",
 "t_sec_outlook": "Next session (09-09 Wed) outlook",
 "o_logic": "Reasoning (based on the 09-08 close + crowd-psychology position)",
 "o_logic_text": "Extending 09-08's 'high-level rotation / SH strong, ChiNext weak': heat intact (up-ratio 63%, 74 limit-ups) but momentum converging (ladder collapse, MACD histogram narrowing, nascent KDJ dead-cross, dark outflows in electronics) — the odds of the rotation evolving into 'divergence' are rising. Sector directions and trading rules for 09-09 follow (<b>no individual stock recommendations</b>).",
 "o1_tag": "Price-hike relay (watch)",
 "o1_t": "Planting / Farm-Product Processing / CokeⅡ / Oilfield Services",
 "o1_d": "The direction with genuine main accumulation/offensive buying on 09-08 (Planting +¥6.86bn, Farm-Product Processing +¥4.99bn); if 09-09 keeps the inflows, the rotation main line is confirmed and sentiment digests via 'gear shift' rather than 'ebb'.",
 "o1_cond": "Caution: agriculture/cyclical themes are news-sensitive and historically short-lived; confirmation = 2 straight days of main inflows + height rebuilding; if it's a one-day wonder, the rotation turns straight into an ebb.",
 "o2_tag": "Electronics distribution (avoid)",
 "o2_t": "Consumer Electronics / Computer Equipment / Batteries / high-ladder names",
 "o2_d": "Monday's counterattack leaders were distributed on 09-08 (Consumer Electronics dark −¥3.24bn, Computer Equipment −¥2.76bn, Batteries −¥1.68bn) as ChiNext −1.15% gave back — if margin positions remain trapped there, the pause amplifies into a drawdown.",
 "o2_cond": "Caution: no left-side buying into directions with consecutive dark outflows; wait for dark flow to turn positive + shrinking-volume stabilisation; post-break ladder relay win-rates drop sharply.",
 "o3_tag": "Ebbing confirmation signals (alert)",
 "o3_t": "Limit-ups below 50 / up-ratio losing 50% / no height",
 "o3_d": "09-08 limit-ups 74 (falling from 90), ladder 4 boards (collapsed) — if 09-09 sees limit-ups below 50 or up-ratio losing 50%, the 'high-level rotation' confirms into an 'ebb'; cut risk exposure then.",
 "o3_cond": "Caution: rotation-to-ebb transitions usually come with ChiNext dragging the indices down; hold a neutral book until confirmed, defensive discipline after; right-side signal = shrinking-volume stabilisation + a new main line rebuilding height.",
 "o_rules_t": "Trading rules (09-09)",
 "o_r1": "<b>Position</b>: keep a neutral book (≤50%) in the rotation, no leverage; a 63% up-ratio is no reason to add — 449 'distributing' sectors question the quality of the advance.",
 "o_r2": "<b>Ebbing confirmation</b>: limit-ups below 50 or up-ratio losing 50% = rotation turns to ebb, cut to defensive; ladder height rebuilding upward (a new 5-board leader) = gear shift succeeded.",
 "o_r3": "<b>Main-line participation</b>: price-hike chain as structure observation only (do main inflows persist?), no chasing the day after limit-up waves; avoid dark-outflow electronics, wait for the dark flow to turn positive.",
 "o_r4": "<b>Avoid list</b>: electronics hardware with consecutive dark outflows, broken ladder leaders (the Longban Media pattern), margin-concentrated directions with invisible leverage, one-day-wonder chases.",
 "o_r5": "<b>Risk control</b>: with MAs intertwined, do not pre-judge direction — use the BOLL mid-band (SSE 3936) as the bull/bear line; below it with limit-ups still fading, execute defence; no added leverage until margin data resumes.",
 "o_compliance": "<b>Compliance:</b> this outlook gives sector directions and trading rules only, with no individual stock recommendations; the crowd-psychology position and sector inferences are based on real 2026-09-08 market data. Markets carry risk; decisions must be independent.",
 "t_sec_source": "Sources & date basis",
 "s_breadth": "Breadth / overview",
 "s_breadth_v": "iFinD search_securities historical-day screen (09-08: 3414 up / 2025 down, flat = total − up − down); 2026-09-08 close (same-day westock updown snapshot missing, backfill fallback)",
 "s_portrait": "Market portrait summary",
 "s_portrait_v": "Backfill assembly: iFinD historical-day screen + data_kline self-computed + sector_daily same-day snapshot; 2026-09-08 (up-ratio 63%, high-level rotation)",
 "s_index": "Index performance",
 "s_index_v": "westock data_kline 260 bars self-computed (MA/BOLL/MACD/RSI/KDJ cross-checked against the official market_statis_technical@09-07 anchor with 0.0000 deviation); 2026-09-08 close",
 "s_sector": "Sector ranking / flows",
 "s_sector_v": "westock · data_sector same-day snapshot (quant/sector_daily/2026-09-08.json); 2026-09-08 (926 sectors, 672 green, 449 distributing)",
 "s_hot": "Hot stocks",
 "s_hot_v": "westock · leading sectors + limit-up list composite (data_hot missing historically, backfill uses sector leaders); 2026-09-08 (agriculture / cyclicals / real-estate services on top)",
 "s_macro": "Core macro",
 "s_macro_v": "westock · data_macro carried forward (monthly); PMI/capacity/social-financing are prior values; CPI/M1-M2/10Y/LPR carried forward",
 "s_margin": "Margin (stocks)",
 "s_margin_v": "westock · margin interface degraded (service error) + no snapshot in the backfill window, data missing, not fabricated",
 "s_main": "Main capital 5d net inflow",
 "s_main_v": "westock · tool_ranking degraded (service error) + no historical snapshot, cannot backfill; same-day main behaviour shown via sector_daily sector flows (main/retail/dark)",
 "s_board": "Ladder height",
 "s_board_v": "westock · tool_ranking ladder-list snapshot (quant/limitup/2026-09-08.json, 74 limit-ups); 2026-09-08 (top 4 boards: Yasheng / Baida / Aishida)",
 "s_gap": "Data gaps",
 "s_gap_v": "Margin balance, daily margin change, main-5d ranking and limit-down count have no real data source in the 09-08 backfill window — all flagged, not fabricated; valuation PE_TTM 20.40 is 09-08 basis (CSI All-Share, one-session publication lag); breadth is the iFinD historical-screen basis (minor deviation from westock updown possible)",
 "t_src_note": "Timing: all timestamps are Beijing time. Macro data are monthly/quarterly and cannot be aligned directly with daily quotes; each is flagged. Breadth / indices / sectors / ladder list are real 2026-09-08 data (backfill: breadth from the iFinD historical screen, indices/technicals self-computed and anchor-verified); margin, main-5d and limit-down count missing — all flagged.",
 "disc1": "Disclaimer: the above is based on public data and quantitative analysis, for reference only, not investment advice. Markets carry risk; investment decisions should be made independently per your own risk tolerance, financial status and goals, and consult a licensed professional when necessary. Past performance does not predict future returns.",
 "disc2": "This assessment is 'crowd psychology / conditional framework' analysis, not a trading order; risk readings and bias severities are model mappings and must be cross-validated with price structure, valuation and flows, not used alone as a trade basis.",
 "t_foot": "Crowd Psychology Risk Radar · generated from westock / iFinD official market data · research reference only",
}

zh = dict(zh0); zh.update(ZH)
en = dict(en0); en.update(EN)
assert set(zh0) <= set(zh), "zh 键丢失"
assert set(en0) <= set(en), "en 键丢失"
missing_zh = [k for k in zh0 if k not in ZH]
print("[info] zh 沿用模板值的键数:", len(missing_zh), missing_zh[:20])


def serialize(d):
    return "\n".join('      %s:"%s",' % (k, esc(d[k])) for k in d)


new_en = "en:{\n" + serialize(en) + "\n    }"
html = html[:m_en.start()] + new_en + html[m_en.end():]
new_zh = "zh:{\n" + serialize(zh) + "\n    },"
html = html[:m_zh.start()] + new_zh + html[m_zh.end():]

# ============================================================
# 2) 重建 BIAS 数组（09-08 高位轮动视角）
# ============================================================
BIAS = [
 {"zh":"过度自信","en":"Overconfidence","sev":4,
  "zhd":"涨股比 63% 的连续改善让群体把「轮动」误读为「牛市换挡」，追涨换挡主线的自信膨胀——但连板高度 6板→4板、MACD 红柱收窄、KDJ 死叉雏形都在提示动能衰减，过度自信恰在数据转弱时最危险。",
  "end":"Two days of improving up-ratio (63%) let the crowd misread 'rotation' as 'a bull-market gear shift', inflating confidence to chase the new line — while ladder 6→4 boards, a narrowing MACD histogram and a nascent KDJ dead-cross all flag fading momentum; overconfidence is most dangerous exactly when data weakens."},
 {"zh":"羊群效应","en":"Herding","sev":4,
  "zhd":"主力一日内集体弃电子硬件、抢农业周期（种植业 主力 +68.63亿），群体跟随资金迁徙一拥而上——上一天还在追光模块，今天就追涨停潮农业，羊群在轮动中被反复收割。",
  "end":"Mains collectively abandoned electronics for agriculture/cyclicals in one day (Planting main +¥6.86bn) and the herd stampedes after the migration — chasing optical modules one day, agricultural limit-up waves the next; the herd gets shorn repeatedly in rotation."},
 {"zh":"代表性启发","en":"Representativeness","sev":3,
  "zhd":"把单日涨股比 63% 代表「市场强势」、把农业涨停潮代表「新主线确立」——09-07 电子硬件反攻次日即休整的样本近在眼前，单日样本外推的代表性错误正在重演。",
  "end":"Reading one day's 63% up-ratio as 'market strength' or the agriculture limit-up wave as 'a new main line confirmed' — the sample of electronics' 09-07 counterattack pausing the very next day is right there; the representativeness error of single-day extrapolation is repeating."},
 {"zh":"锚定偏差","en":"Anchoring","sev":3,
  "zhd":"一部分人锚定 09-07 电子硬件的涨停潮认为「回调即上车」，另一部分锚定上证 3950「没破位就没事」——均线缠绕（MA5/10/20/60 四线收敛于 3936–3950）时，锚点失效最快。",
  "end":"Some anchor to 09-07's electronics limit-up wave ('a dip is a chance to board'), others to SSE 3950 ('no breakdown, no problem') — with four MAs converging in the 3936–3950 band, anchors fail fastest."},
 {"zh":"近因偏差","en":"Recency","sev":4,
  "zhd":"把「连续两日涨股比改善」外推为「广度行情启动」，忽视 20 日均量占比仅 94.2%、量能实际处于收缩通道；同样有人把单日电子硬件休整外推为「科技行情终结」——两个方向的近因外推都在制造追涨杀跌。",
  "end":"Extrapolating 'two days of improving breadth' into 'a breadth rally begins', ignoring that volume is only 94.2% of its 20-day average and actually shrinking; equally, some read one day of electronics pausing as 'the tech trade is over' — recent-bias extrapolation in both directions manufactures chases and panic sells."},
 {"zh":"处置效应","en":"Disposition","sev":3,
  "zhd":"电子硬件的持仓者在 −1%~−2% 的回撤中倾向「再等等」（处置效应延迟止损），而农业追高者一旦浮盈立即兑现——两类行为的叠加会放大轮动末端的波动。",
  "end":"Electronics holders tend to 'wait a bit more' on −1~−2% drawdowns (disposition delaying stops) while agriculture chasers take profits instantly — the combination amplifies volatility at the rotation's end."},
 {"zh":"心理账户/赌徒谬误","en":"Mental Acct / Gambler","sev":3,
  "zhd":"把「涨停 74 只仍高于 50」记入「情绪无恙」账户并外推「退潮还很远」，忽视涨停已从 90 连续回落、高度从 6板骤降至 4板——趋势的斜率比绝对水平更早报警。",
  "end":"Booking '74 limit-ups still above 50' into a 'sentiment fine' account and extrapolating 'the ebb is far away' ignores that limit-ups fell consecutively from 90 and height collapsed 6→4 — the slope warns earlier than the level."},
 {"zh":"确认偏误","en":"Confirmation Bias","sev":3,
  "zhd":"多头只看涨股比 63%、672 板块收红，忽视 449 板块「出货」与 20 日量比 94.2%；空头只看高度骤降与电子暗盘流出，忽视梯队厚度（2板仍有13只）与主力在涨价链的真实建仓。",
  "end":"Bulls watch only 63% up-ratio and 672 green sectors, ignoring 449 'distributing' sectors and the 94.2% 20-day volume ratio; bears watch only the collapsing height and electronics dark outflows, ignoring the ladder depth (13 two-board names) and genuine main accumulation in the price-hike chain."},
 {"zh":"叙事偏差","en":"Narrative","sev":3,
  "zhd":"「农业涨价 + 反内卷」叙事一日内接管市场注意力，故事与资金短期共振；但 CPI（7月）偏弱、产能利用率走弱的基本面并不支持涨价叙事全面展开——叙事被证伪时的回撤同样剧烈。",
  "end":"The 'agricultural price-hike + anti-involution' narrative captured market attention in a single day, story and capital resonating short-term; but weak July CPI and soft capacity utilisation do not support a full price-hike narrative — the drawdown when it is falsified would be just as sharp."},
 {"zh":"损失厌恶","en":"Loss Aversion","sev":2,
  "zhd":"市场普涨偏多（63% 上涨）背景下损失厌恶处于低位，但电子硬件持仓者的「浮盈回吐厌恶」开始发酵——前日浮盈今日回吐的心理痛感会放大后续的抛售冲动。",
  "end":"With the market broadly positive (63% up), loss aversion is low overall, but 'paper-profit give-back aversion' is fermenting among electronics holders — the psychological pain of yesterday's gains evaporating amplifies subsequent selling impulses."},
]
bias_js = "var BIAS = [\n" + ",\n".join(
    "    {zh:\"%s\",en:\"%s\",sev:%d,zhd:\"%s\",end:\"%s\"}" % (esc(b["zh"]), esc(b["en"]), b["sev"], esc(b["zhd"]), esc(b["end"]))
    for b in BIAS) + "\n  ];"
html, _n = re.subn(r'var BIAS = \[.*?\n  \];', bias_js, html, count=1, flags=re.S)
assert _n == 1, "BIAS 替换失败"

# ============================================================
# 3) 静态 body patch（OLD = 09-11 页值）
# ============================================================
BODY = [
 # SVG rects：涨 12%(58px)→63%(314px)；跌 88%(442px,x=72)→37%(186px,x=328)
 ('<rect x="14" y="14" width="58" height="26" fill="#d8392b"/>',
  '<rect x="14" y="14" width="314" height="26" fill="#d8392b"/>'),
 ('<rect x="72" y="14" width="442" height="26" fill="#1a9e5a"/>',
  '<rect x="328" y="14" width="186" height="26" fill="#1a9e5a"/>'),
 ('<text x="167" y="33" fill="#fff" font-size="14" font-weight="800" text-anchor="middle">12%</text>',
  '<text x="171" y="33" fill="#fff" font-size="14" font-weight="800" text-anchor="middle">63%</text>'),
 ('<text x="407" y="33" fill="#fff" font-size="14" font-weight="800" text-anchor="middle">88%</text>',
  '<text x="421" y="33" fill="#fff" font-size="14" font-weight="800" text-anchor="middle">37%</text>'),
 ('<text x="514" y="33" fill="#6b675f" font-size="11" font-weight="700" text-anchor="end">1% 平盘</text>',
  '<text x="514" y="33" fill="#6b675f" font-size="11" font-weight="700" text-anchor="end">2% 平盘</text>'),
 # stat rows
 ('<text x="340" y="72" fill="#d8392b">643</text>',
  '<text x="340" y="72" fill="#d8392b">3414</text>'),
 ('<text x="340" y="92" fill="#1a9e5a">4870</text>',
  '<text x="340" y="92" fill="#1a9e5a">2025</text>'),
 ('<text x="340" y="112" fill="#6b675f">49</text>',
  '<text x="340" y="112" fill="#6b675f">123</text>'),
 ('<text x="340" y="138" fill="#d8392b">40</text>',
  '<text x="340" y="138" fill="#d8392b">74</text>'),
 ('<text x="340" y="158" fill="#1a9e5a">21</text>',
  '<text x="340" y="158" fill="#1a9e5a">—</text>'),
 ('<text x="340" y="184" fill="#1c1b19">¥1.97万亿</text>',
  '<text x="340" y="184" fill="#1c1b19">¥1.96万亿</text>'),
 # annotations
 ('<text x="355" y="72">（占 12%，较上一报告日（09-10） −5pct）</text>',
  '<text x="355" y="72">（占 63%，较上一报告日（09-07） +6pct）</text>'),
 ('<text x="355" y="92">（占 88%，较上一报告日（09-10） +7pct）</text>',
  '<text x="355" y="92">（占 37%，较上一报告日（09-07） −6pct）</text>'),
 ('<text x="355" y="112">（占 1%）</text>',
  '<text x="355" y="112">（占 2%）</text>'),
 ('<text x="355" y="138">（较前日 +2 只，连板高度 4板）</text>',
  '<text x="355" y="138">（较前日 −16 只，连板高度 4板）</text>'),
 ('<text x="355" y="158">（较前日 +19 只，恐慌扩散）</text>',
  '<text x="355" y="158">（跌停家数历史数据源缺失，未编造）</text>'),
 ('<text x="355" y="184">（环比 +3200亿，放量普跌）</text>',
  '<text x="355" y="184">（环比 +143亿，量能平稳）</text>'),
 # evidence table number cells
 ('<td><span class="val up">12%</span>（涨643 / 跌4870 / 平49）</td>',
  '<td><span class="val up">63%</span>（涨3414 / 跌2025 / 平123）</td>'),
 ('<td><span class="val up">40</span> / <span class="val down">21</span></td>',
  '<td><span class="val up">74</span> / <span class="val down">—</span></td>'),
 ('<td><span class="val">¥1.97万亿</span>（较前次 +3200亿，放量普跌）</td>',
  '<td><span class="val">¥1.96万亿</span>（较前次 +143亿，量能平稳）</td>'),
 ('<td><span class="val down">3888.11　−1.18%</span></td>',
  '<td><span class="val up">3940.55　+0.20%</span></td>'),
 ('<td><span class="val down">13471.26　−1.08%</span></td>',
  '<td><span class="val down">13703.21　−0.52%</span></td>'),
 ('<td><span class="val down">3322.04　−0.49%</span></td>',
  '<td><span class="val down">3359.72　−1.15%</span></td>'),
 ('<td><span class="val up">地面兵装Ⅱ +4.44%</span>（主力净流入 +50.22亿，行为「抢筹」）<br>通信设备 +1.66%（主力 +839.89亿，全行业第一）/ 元件 +1.80%（+638.35亿）/ 玻璃玻纤 +2.63% 跟随<br>全市场 927 个板块仅 33 个收红，733 个呈主力「出货」</td>',
  '<td><span class="val up">焦炭Ⅱ +5.23%</span>（主力 +5.61亿，行为「抢筹」）<br>农产品加工 +5.02%（主力 +49.91亿 抢筹）/ 种植业 +4.91%（+68.63亿 建仓）/ 油服工程 +4.71% 跟随<br>全市场 926 个板块 672 个收红，449 个呈主力「出货」</td>'),
 ('<td><span class="val down">工业金属 −5.04%</span>（主力 +261.18亿 但散户流入 +303.79亿更多，暗盘 −42.6亿 → 实为「出货」）<br>农产品加工 −4.36% / 渔业 −4.34%<br>资源与前期题材在恐慌中集中补跌</td>',
  '<td><span class="val down">电池 −2.06%</span>（暗盘 −16.78亿，行为「出货」）<br>消费电子 −1.79%（暗盘 −32.38亿 出货）/ 计算机设备 −1.68%（−27.60亿）/ 半导体 −1.30%<br>09-07 反攻的电子硬件集体休整并遭主力兑现</td>'),
 ('<td><span class="val up">连板高度 4 板</span>（瑞尔特，新龙头接棒桂林旅游）<br>共 40 只连板（持平）；3板：鼎信通讯 / 闽东电力；2板：凯盛新能 / 超声电子 / 九鼎新材 / 中新赛克——龙头一日一换</td>',
  '<td><span class="val up">连板高度 4 板</span>（亚盛集团 / 百大集团 / 爱仕达，由3板晋级）<br>涨停共 74 只（90→74）；3板：海欣食品 / 中国出版 / 敦煌种业；2板13只——龙版传媒6板断板，高度骤降</td>'),
 ('<td><span class="val up">瑞尔特 4板</span>（2026-09-11）</td>',
  '<td><span class="val up">亚盛集团 / 百大集团 / 爱仕达 4板</span>（2026-09-08）</td>'),
 ('<td><span class="val">主力5日净流入 TOP（tool_ranking 降级期，09-09 口径沿用）</span></td>',
  '<td><span class="val">主力5日净流入 TOP（tool_ranking 降级期，历史快照缺，未编造）</span></td>'),
 ('<td><span class="val">融资单日变动 TOP（两融接口降级，数据暂缺，未编造）</span></td>',
  '<td><span class="val">融资单日变动 TOP（两融接口降级，数据暂缺，未编造）</span></td>'),
 ('<td><span class="val up">瑞尔特 4板</span>（卫浴出海）<br>地面兵装Ⅱ +4.44%（主力 +50.22亿 抢筹）<br>通信设备 +1.66% / 元件 +1.80% / 玻璃玻纤 +2.63%<br>工业金属 −5.04% / 农产品加工 −4.36% / 渔业 −4.34%</td>',
  '<td><span class="val up">亚盛集团 4板</span>（种植业）<br>焦炭Ⅱ +5.23%（抢筹）/ 农产品加工 +5.02%（+49.91亿）<br>种植业 +4.91%（+68.63亿 建仓）/ 油服工程 +4.71%<br>电池 −2.06% / 消费电子 −1.79% / 半导体 −1.30%</td>'),
 # static header date + Next-Session
 ('<b>2026-09-11 收盘（北京时间，盘后）</b>',
  '<b>2026-09-08 收盘（北京时间，盘后）</b>'),
 ("Next-Session Outlook (09-14 Mon)", "Next-Session Outlook (09-09 Wed)"),
 # 顶部 chips 静态值
 ('<span data-i18n="c_upratio">涨股比</span> <b>12%</b></span>',
  '<span data-i18n="c_upratio">涨股比</span> <b>63%</b></span>'),
 ('<span data-i18n="c_limitup">涨停</span> <b>40</b></span>',
  '<span data-i18n="c_limitup">涨停</span> <b>74</b></span>'),
 ('<span data-i18n="c_pe">估值 PE分位</span> <b>34%（52周）</b></span>',
  '<span data-i18n="c_pe">估值 PE分位</span> <b>80%（10Y）</b></span>'),
 ('<span data-i18n="c_turn">两市成交</span> <b>¥1.97万亿</b></span>',
  '<span data-i18n="c_turn">两市成交</span> <b>¥1.96万亿</b></span>'),
]
miss = 0
for old, new in BODY:
    if old in html:
        html = html.replace(old, new, 1)
    else:
        miss += 1
        print("[skip-body] 未命中: %r" % old[:70])
print("[body] patch 完成，未命中 %d 处" % miss)

# ============================================================
# 4) 雷达六维数值标签：OLD 64/68/50/90/42/85 → NEW 59/67/52/45/58/87
# ============================================================
old_radar = '<text x="160" y="71">64</text><text x="237" y="120">68</text><text x="209" y="194">50</text>\n            <text x="160" y="167">90</text><text x="109" y="201">42</text><text x="55" y="118">85</text>'
new_radar = '<text x="160" y="71">59</text><text x="237" y="120">67</text><text x="209" y="194">52</text>\n            <text x="160" y="167">45</text><text x="109" y="201">58</text><text x="55" y="118">87</text>'
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
# 6) 写出（不写 hub —— hub 由统一脚本处理）
# ============================================================
open(OUT, "w", encoding="utf-8").write(html)
print("[ok] 写出 %s (%d bytes)" % (OUT, len(html)))

leftover = ["12%</text>", "88%</text>", "643", "4870", "地面兵装Ⅱ", "工业金属 −5.04%",
            "瑞尔特", "¥1.97万亿", "3888.11", "13471.26", "3322.04", "09-11 · 收盘",
            "放量普跌 · 恐慌扩散", "Next-Session Outlook (09-14", "鼎信通讯", "桂林旅游 4板"]
bad = [s for s in leftover if s in html]
print("[校验] 残留旧数据:", bad if bad else "无")
