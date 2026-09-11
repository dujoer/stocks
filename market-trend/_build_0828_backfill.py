# -*- coding: utf-8 -*-
"""群体心理风险雷达 2026-08-28 回补：以 09-11 页为模板，全部动态内容覆盖。

数据来源（全部真实、口径逐一标注）：
  指数/成交/技术 = westock data_kline 260根自算（与官方 market_statis_technical@09-07 锚点核验偏差 0.0000）
  广度 = iFinD search_securities 历史日筛选（08-28 涨3007/跌2384）
  板块 = quant/sector_daily/2026-08-28.json（当日快照：925板块、行为分布、领涨领跌）
  估值 = quant/market_overview/2026-08-31.json valuation（滞后一交易日发布 → 08-28 口径）
  缺口：涨停/跌停/连板明细、两融、风格轮动在回补窗口无真实数据源 → 全部如实标注、未编造
"""
import os, re

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "..", "web", "psychology", "crowd-psychology-risk-radar-20260911.html")
OUT = os.path.join(HERE, "..", "web", "psychology", "crowd-psychology-risk-radar-20260828.html")

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
 "t_headline_sub": "2026-08-28 · 收盘",
 "hk_stage": "阶段定性", "hv_stage": "<b>冲高分化 / 结构换挡</b>（08-28）",
 "hk_upratio": "涨股比", "hv_upratio": "<b>56%</b>（前次 08-27 61% · ↓ 5pct，广度自高位回落）",
 "hk_lim": "涨停 / 跌停", "hv_lim": "<b>—</b> / <b>—</b>（涨跌停明细数据源缺，未编造）",
 "hk_amt": "成交额", "hv_amt": "<b>¥2.10万亿</b>（微缩 −242亿，仍为 5 日均 106.4%）",
 "hk_cycle": "情绪周期", "hv_cycle": "<b>冲高分化 / 结构换挡</b>",
 "hk_risk": "风险等级", "hv_risk": "<b class=\"hl-risk\">高</b>（维持）",
 "hk_flag": "关键提示",
 "hv_flag": "涨股比 61%→<b>56%</b> 自高位回落、成交 ¥2.10万亿 微缩 −242亿——指数冲高乏力（上证 −0.11%、盘中 3970.31 后回落）；结构剧烈换挡：08-27 放量反包的电子硬件遭主力大额兑现（半导体暗盘 −122.58亿、通信设备 −59.20亿、均「出货」），资金切向渔业/地产服务/饰品与信创/跨境电商/软件开发（暗盘合计 +73亿）；925 板块中 499 个「出货」占 54%——<b>热度掩盖下的分化正在加深</b>；涨跌停/连板/两融明细缺失，未编造。",
 "tk1": "阶段定性", "tv1": "A股 08-28 由 08-27「放量反包 / 量价共振」转入「<b>冲高分化 / 结构换挡</b>」：涨股比回落至 <b>56%</b>（3007涨 / 2384跌 / 平171，由 61% 降 5pct），上证 <b>−0.11%</b>（3952.18，盘中冲高 3970.31 后回落）、深成 <b>−0.68%</b>（13953.07）、创业板 <b>−1.41%</b>（3424.40）；成交 ¥2.10万亿（5 日均 106.4%、环比 −242亿）维持高位但停止放大。与 08-27 的关键差异：<b>量价共振破裂</b>——指数仍在 MA5/10/20 上方的强势区，但资金已在大规模换手：08-27 领涨的电子硬件当日暗盘流出逾 180亿，上涨由渔业（+4.55%）/地产服务（+3.75%）/饰品（+3.42%）等低位方向接力。<b>指数的平静与资金的躁动并存</b>，是典型的顶部区分化形态。",
 "tk2": "广度自高位回落", "tv2": "涨股比 <b>56%</b>（前次 61% ↓5pct）· 成交 <b>¥2.10万亿</b>（5 日均 106.4%、10 日均 99.4%、20 日均 93.6%，环比 −242亿 微缩）——广度自 61% 的高位回落但仍在 50% 上方；板块层面分化更烈：925 个板块 550 涨 / 368 跌（59.5%），而 <b>499 个板块（54%）呈主力「出货」</b>，抢筹仅 89 个——上涨家数维持偏多与主力行为的全面出货并存，<b>宽度是最后才会证伪的指标</b>。",
 "tk3": "技术强势区内的暗涌", "tv3": "上证 <b>−0.11%</b>（3952.18）收于 MA5（3918.54）/ MA10（3926.90）/ MA20（3916.06）上方、MA60（3957.86）下方——短中期均线多头、中期均线压制，结构未破但空间受限；MACD <b>+10.65</b>（DIF 2.97 上穿 DEA −2.36 金叉确认，红柱放大）、RSI6 <b>62.44</b>（偏强）、KDJ_J 71.63（偏高）——<b>技术读数偏强与资金大额流出并存</b>：技术指标是滞后的，暗盘是领先的；创业板 −1.41% 已率先跌破 MA5（3428.41），高弹性方向率先转弱。",
 "tk4": "板块结构", "tv4": "<b>渔业 +4.55%</b>（主力 +3.38亿，抢筹，中水渔业涨停）领涨，<b>房地产服务 +3.75%</b>（主力 +7.23亿 抢筹，我爱我家涨停）/ <b>饰品 +3.42%</b>（主力 +18.53亿 建仓）/ 炼化及贸易 +2.66%（华锦股份涨停）/ 农产品加工 +2.65% 跟随——<b>低位低价方向全面补涨</b>；<b>生物制品 −2.73%</b> / 医疗服务 −2.13% / <b>半导体 −2.12%</b>（暗盘 −122.58亿，出货）/ 电子化学品Ⅱ −1.80% / 通信设备 −1.56%（暗盘 −59.20亿 出货）——08-27 放量反包的电子硬件与医药链遭主力集中兑现，<b>兑现规模为本轮调整以来单日最大级别</b>。",
 "tk5": "连板结构", "tv5": "连板明细数据源缺失（回补窗口无真实名单，<b>未编造</b>）；参考信号：08-27 口径连板高度 5 板（深中华A，数据源延迟取 08-26）、08-31 口径 6 板（海鸥住工）——08-28 处于「5板→6板」晋级通道中，投机热度延续；个股佐证：深中华A 08-28 +9.99%、中水渔业/我爱我家/华锦股份涨停——<b>低位低价补涨潮通常对应情绪末端的高位换手</b>。",
 "tk6": "资金：电子硬件遭大额兑现", "tv6": "两融数据缺失（接口降级 + 回补窗口无快照，<b>未编造</b>）；板块资金揭示的核心事实：<b>半导体暗盘 −122.58亿、通信设备 −59.20亿、医疗服务 −14.83亿</b>且行为全部标记「出货」——08-27 放量反包的做多主力正在撤退；同时<b>信创 +25.53亿（建仓）/ 跨境电商 +25.24亿（抢筹）/ 软件开发 +22.46亿（抢筹）</b>承接——资金并未离场，而是从硬件切向软件与题材，<b>存量博弈下的高低切换</b>，风险偏好名义未降、实际脆弱性上升。",
 "tk7": "估值 / 风格", "tv7": "PE_TTM <b>21.15</b>（10年分位 <b>87.22%</b>、5年 83.25%、3年 72.09%，口径 08-28，中证全指滞后一交易日发布）——估值分位较 09 月初（20.39 / 79.52%）明显更高，<b>08-28 是本轮区间估值最贵的时点之一</b>；风格：沪深300 08-28 −0.46%、中证1000 −0.36%（价值/成长的 5/20 日轮动读数历史快照缺，未编造）；从板块行为看资金弃「高位硬件」取「低位题材」，本质是估值锚支配的避险，<b>高估值 + 高换手 + 低位补涨 = 情绪末端三信号齐备</b>。",
 "tk8": "情绪周期", "tv8": "由 08-27「放量反包 / 量价共振」转入「<b>冲高分化 / 结构换挡</b>」：广度自 61% 回落、量能停止放大、主力在领涨方向大额出货（半导体 −122.58亿）而群体仍在低位股中寻找补涨——<b>Smart money 退出、dumb money 接力的经典顶部结构</b>；技术读数尚强（MACD 金叉、RSI 62）恰是「情绪惯性掩盖资金撤退」的危险组合；估值 10 年分位 87.22% 高悬，风险等级维持<b>高</b>。",
 "t_tldr_text": "A股 08-28 呈现「冲高分化 / 结构换挡」：涨股比 61%→56%（3007涨/2384跌/平171），涨跌停明细数据源缺失（未编造）；上证 −0.11%（3952.18，盘中 3970.31 冲高回落）收于 MA5/10/20 上方、MA60 下方，MACD 金叉红柱放大（+10.65）、RSI6 62.44；深成 −0.68%（13953.07）、创业板 −1.41%（3424.40，率先跌破 MA5）。成交 ¥2.10万亿（5 日均 106.4%、环比 −242亿）停止放大。渔业 +4.55%（中水渔业涨停）/ 房地产服务 +3.75%（我爱我家涨停）/ 饰品 +3.42% 领涨——低位低价全面补涨；生物制品 −2.73% / 医疗服务 −2.13% / 半导体 −2.12%（暗盘 −122.58亿 出货）/ 通信设备 −1.56%（−59.20亿 出货）——08-27 反包主力遭大额兑现。925 板块 550 收红但 499 个（54%）「出货」，信创/跨境电商/软件开发暗盘合计 +73亿 承接——存量高低切换。估值 PE_TTM 21.15（10Y 分位 87.22%，本轮区间最贵时点之一）。连板/两融明细缺失。风险等级维持高。",
 "t_risk": "风险等级", "t_risk_hi": "高",
 "c_upratio": "涨股比", "c_limitup": "涨停", "c_board": "连板高度", "c_pe": "估值 PE分位", "c_pmi": "制造业PMI", "c_turn": "两市成交",
 "t_sec_bias": "行为偏差热力图", "t_cycle": "情绪周期定位（六阶段）",
 "r1": "绝望", "r2": "怀疑", "r3": "乐观", "r4": "狂热", "r5": "焦虑", "r6": "自满",
 "t_cycle_note": "注：上方「自满 / 冲高分化」为实时群体心理定位（冲高分化 / 结构换挡）——08-28 涨跌分布（涨股比 56%、成交 ¥2.10万亿 停止放大）与资金行为（半导体暗盘 −122.58亿出货、低位股补涨潮）显示 Smart money 撤退、群体自满于指数强势；涨跌停/连板明细缺失。若 08-31 涨股比失守 50% 且量能继续萎缩，确认退潮；若软件/题材承接失败（暗盘转负），分化将直接转为普跌。",
 "t_leg": "严重度（由数据综合映射）", "t_bias_note": "注：偏差严重度为基于下方真实数据的模型映射（1=低，5=高），用于呈现群体心理的脆弱点分布，并非对个股的买卖建议。",
 "t_sec_radar": "风险雷达",
 "t_radar_note": "六维风险读数（0–100，由下方真实数据综合映射，越高代表该维度群体脆弱性越强）：拥挤度 70 / 融资 67 / 换手 55 / 广度 51 / 媒体 67 / 估值 89。拥挤度由 68 升至 70（连板高度向 6 板晋级、低位低价补涨潮扩散，投机筹码加速集中）；融资由 64 升至 67（两融数据缺失，杠杆不可视，按存量博弈高位谨慎上调）；换手由 54 升至 55（成交 ¥2.10万亿 维持 5 日均 106.4%，高位大换手——但换手的性质已从「共识」转为「分歧」）；广度由 50 升至 51（涨股比 61%→56% 回落但仍在 50% 上方，499 板块出货的对冲下脆弱性微升）；媒体由 66 升至 67（指数强势、低位股涨停潮，情绪温度维持高位）；估值由 90 降至 89（PE_TTM 21.15、10年分位 87.22%，仍处本轮区间最贵一档）。整体脆弱性由「拥挤 + 估值」主导——典型顶部区读数：广度尚可、资金已在撤退。",
 "ax_crowd": "拥挤度", "ax_margin": "融资", "ax_turn": "换手", "ax_breadth": "广度", "ax_media": "媒体情绪", "ax_val": "估值",
 "b_up": "上涨", "b_down": "下跌", "b_flat": "平盘", "b_limitup": "涨停", "b_limitdn": "跌停", "b_amt": "成交额",
 "t_breadth_note": "涨股比 61%→56%（3007涨/2384跌/平171）自高位回落、涨跌停明细缺失（未编造）；成交 ¥2.10万亿（5 日均 106.4%、环比 −242亿）停止放大。上证 −0.11%（3952.18，盘中 3970.31 冲高回落，MA60 3957.86 得而复失）/ 深成 −0.68%（13953.07）/ 创业板 −1.41%（3424.40 破 MA5）；渔业 +4.55% / 房地产服务 +3.75% / 饰品 +3.42% 领涨，生物制品 −2.73% / 半导体 −2.12%（暗盘 −122.58亿 出货）领跌——925 板块 550 收红但 499 个（54%）「出货」。",
 "th_metric": "指标", "th_read": "真实读数", "th_interp": "行为金融解读",
 "ev_market": "一、市场广度与总览",
 "ev_upratio": "涨股比",
 "ev_upratio_i": "由 61% 回落至 56%（−5pct），涨 3007 / 跌 2384 / 平 171，广度自高位回落；板块层面 499/925（54%）呈主力「出货」——个股宽度与主力行为大幅背离，上涨由低位补涨支撑",
 "ev_limit": "涨停 / 跌停",
 "ev_limit_i": "涨跌停家数在回补窗口无真实数据源（iFinD 数值筛选口径不可靠），<b>未编造</b>；个股佐证：中水渔业 / 我爱我家 / 华锦股份 / 深中华A(+9.99%) 等低位低价股涨停/准涨停——补涨潮是情绪末端的典型微观结构",
 "ev_amount": "两市成交额",
 "ev_amount_i": "量能 ¥2.10万亿（5 日均 106.4%、10 日均 99.4%、20 日均 93.6%，环比 −242亿）——08-27 的 ¥2.13万亿 放量未能延续，量能在高位停止放大＝「共振」转「分歧」的第一个量价信号",
 "ev_index": "二、核心指数表现（2026-08-28 收盘）",
 "ev_sh": "上证指数",
 "ev_sh_i": "−0.11%（3952.18，盘中高 3970.31 / 低 3947.80，冲高回落），收于 MA5（3918.54）/ MA10（3926.90）/ MA20（3916.06）上方、MA60（3957.86）下方——短均多头、中均压制；MACD +10.65（DIF 2.97 / DEA −2.36，金叉确认红柱放大）、RSI6 62.44 偏强、KDJ_J 71.63 偏高；BOLL（上4010.01 / 中3916.06 / 下3822.12）中上轨间；PE_TTM 21.15（10年分位 87.22%，口径 08-28）",
 "ev_sz": "深证成指",
 "ev_sz_i": "−0.68%（13953.07），冲高 14148.68 回落，短线动能衰减；60 日维度仍深弱",
 "ev_cyb": "创业板指",
 "ev_cyb_i": "−1.41%（3424.40），率先跌破 MA5（3428.41）——高弹性方向对资金撤退最敏感，与半导体/通信设备的暗盘大额流出互为印证",
 "ev_sector": "三、板块排行与主线",
 "ev_secup": "领涨行业",
 "ev_secup_i": "渔业 +4.55%（主力 +3.38亿 抢筹，中水渔业涨停）领涨，房地产服务 +3.75%（主力 +7.23亿 抢筹，我爱我家涨停）/ 饰品 +3.42%（主力 +18.53亿 建仓）/ 炼化及贸易 +2.66%（华锦股份涨停）/ 农产品加工 +2.65% 跟随——低位低价方向全面补涨，主线散乱；925 板块 550 收红（59.5%）",
 "ev_secdn": "领跌行业",
 "ev_secdn_i": "生物制品 −2.73% / 医疗服务 −2.13% / 半导体 −2.12%（暗盘 −122.58亿，行为「出货」）/ 电子化学品Ⅱ −1.80% / 通信设备 −1.56%（暗盘 −59.20亿 出货）——08-27 放量反包的电子硬件与医药链遭主力集中兑现，兑现规模为单日最大级别",
 "ev_board": "极端题材",
 "ev_board_i": "连板明细数据源缺失（回补窗口无真实名单，未编造）；参考：08-27 口径高度 5板（深中华A）、08-31 口径 6板（海鸥住工）——08-28 处晋级通道；深中华A +9.99%、中水渔业/我爱我家/华锦股份涨停——低位补涨潮延续",
 "ev_flow": "四、资金：连板 / 主力 / 两融",
 "ev_height": "连板高度",
 "ev_height_i": "08-28 当日连板名单缺（未编造）；结构信号：概念暗盘承接集中于信创 +25.53亿（建仓）/ 跨境电商 +25.24亿（抢筹）/ 软件开发 +22.46亿（抢筹）——投机资金未离场、只换仓，高度博弈延续至 08-31 的 6板",
 "ev_main": "主力5日净流入TOP",
 "ev_main_i": "主力5日净流入排名在回补窗口无快照（tool_ranking 降级期 + 历史缺），<b>未编造</b>；当日可见信号：半导体暗盘 −122.58亿 / 通信设备 −59.20亿 大额出货，饰品主力 +18.53亿 / 炼化及贸易 +50.92亿 / 农产品加工 +35.39亿 流入——硬件→软件题材、高位→低位的存量切换",
 "ev_margin": "融资单日变动TOP",
 "ev_margin_i": "两融数据接口降级 + 回补窗口无快照，融资单日变动与两融余额均暂缺，<b>未编造</b>；高位大换手 + 估值 10 年分位 87.22% 组合下，杠杆集中度不可视是最大的盲区——历史经验：此阶段的融资盘多聚于当期主线（电子硬件），其兑现将放大杠杆回撤",
 "ev_hot": "热搜 / 领涨TOP",
 "ev_hot_i": "热点结构：深中华A +9.99%（饰品，08-27 口径 5板）/ 中水渔业涨停（渔业 +4.55%）/ 我爱我家涨停（房地产服务 +3.75%）/ 华锦股份涨停（炼化及贸易）——低位低价股涨停潮 + 题材暗盘承接（信创/跨境电商/软件），赚钱效应表面热闹、结构上靠后",
 "ev_margintotal": "市场两融余额",
 "ev_margintotal_i": "缺口：两融余额与融资单日变动在 08-28 回补窗口无真实数据源，已如实标注、未编造；涨跌分布（iFinD 历史日筛选）/ 指数（K线自算，官方锚点核验偏差 0.0000）/ 板块（当日快照）均为 2026-08-28 真实数据",
 "ev_macro": "五、核心宏观指标",
 "ev_pmi": "制造业PMI（7月）",
 "ev_pmi_i": "基本面收缩，与「10年分位 87.22% 的估值」构成当期最尖锐的宏观-估值背离",
 "ev_capu": "产能利用率（Q2）",
 "ev_capu_i": "实物经济动能走弱，题材补涨缺乏产业景气支撑",
 "ev_cpi": "CPI（7月）",
 "ev_cpi_i": "低通胀、需求偏弱，涨价叙事缺乏数据支撑",
 "ev_social": "社融（7月）",
 "ev_social_i": "信用需求弱，资金绕道股市 = 流动性驱动特征，顶部区流动性依赖度最高",
 "ev_m1m2": "M1-M2 剪刀差",
 "ev_m1m2_i": "活钱偏弱，资金空转，典型后周期现象",
 "ev_yield": "10Y 国债收益率",
 "ev_yield_i": "极低无风险利率，既支撑估值也反映增长担忧",
 "ev_lpr": "LPR",
 "ev_lpr_i": "宽松基调未变",
 "t_ev_note": "数据口径：宏观指标多截至 2026-07（月频）或沿用前期值；涨跌分布（iFinD 历史日筛选：涨3007/跌2384）/ 指数与成交（data_kline 自算，与官方 market_statis_technical@09-07 锚点核验偏差 0.0000）/ 板块（sector_daily 当日快照）均为 2026-08-28 真实数据。估值 PE_TTM 21.15 为 08-28 口径（中证全指，滞后一交易日发布）；涨跌停家数、连板名单、两融、主力5日排名缺失，已如实标注未编造。详见末尾「数据来源与日期口径」。",
 "t_sec_risk": "风险分层",
 "rc1_tag": "红线区 · 估值极值 + Smart money 撤退",
 "rc1_t": "高位分歧下的兑现与杠杆盲区",
 "rc1_d": "PE_TTM 10年分位 87.22%（本轮区间最贵档）+ 半导体暗盘单日 −122.58亿出货 + 499 板块（54%）「出货」+ 两融不可视——指数强势是惯性，资金行为是先行：典型顶部区「数量信号尚可、行为信号恶化」组合，风险等级维持高。",
 "rc1_rep": "代表：暗盘大额流出的电子硬件（半导体 −122.58亿 / 通信设备 −59.20亿）/ 医药链（生物制品 −2.73%、医疗服务 −2.13%）/ 两融集中方向（不可视）",
 "rc1_cond": "条件框架：不追高位方向、不接暗盘流出主线；估值极值区只减不加；两融与连板数据恢复前，以暗盘流向为唯一可信的资金信号。",
 "rc2_tag": "黄线区 · 低位补涨的博弈",
 "rc2_t": "低位低价补涨潮的持续性",
 "rc2_d": "渔业/房地产服务/饰品/炼化等低位方向获主力小额抢筹并批量涨停——补涨潮是情绪末端的典型形态，赚钱效应尚在但不断下沉至更弱的标的；参与窗口极短，接力风险高。",
 "rc2_rep": "代表：渔业（中水渔业）/ 房地产服务（我爱我家）/ 饰品 / 炼化及贸易（华锦股份）/ 农产品加工",
 "rc2_cond": "条件框架：补涨方向只做观察不做接力；确认信号 = 主力净流入连续 2 日且换手不萎缩；若涨停潮次日集体熄火，确认情绪末端成立。",
 "rc3_tag": "绿线区 · 软件题材承接（脆弱）",
 "rc3_t": "信创 / 跨境电商 / 软件开发暗盘承接",
 "rc3_d": "信创 +25.53亿（建仓）/ 跨境电商 +25.24亿（抢筹）/ 软件开发 +22.46亿（抢筹）——资金从硬件切向软件与题材，存量博弈下风险偏好名义未降；但「承接」建立在硬件兑现之上，硬件若止跌回流，承接盘将被抽血。",
 "rc3_rep": "代表：信创 / 跨境电商 / 软件开发（对应行业软件开发 +0.60% 暗盘 +22.46亿 抢筹）",
 "rc3_cond": "条件框架：仅作结构观察；确认信号 = 硬件暗止流出收敛 + 软件承接延续；若硬件继续大额出货且软件承接转负，确认全面撤退。",
 "t_sec_outlook": "下个交易日（08-31 周一）展望",
 "o_logic": "研判逻辑（基于 08-28 收盘 + 群体心理定位）",
 "o_logic_text": "由 08-28 的「冲高分化 / 结构换挡」延伸：指数强势区（MACD 金叉、RSI 62）与资金大额撤退（半导体 −122.58亿）并存，低位补涨潮延续、题材承接未断——情绪末端的多空拉锯。基于此推演 08-31 的板块方向与交易规则（<b>不涉及具体个股推荐</b>）。",
 "o1_tag": "软件 / 题材承接方向（观察）",
 "o1_t": "信创 / 跨境电商 / 软件开发 / 传媒 AI 应用",
 "o1_d": "08-28 暗盘承接最集中的方向（合计 +73亿），若 08-31 延续净流入且硬件兑现收敛，情绪以「高低切换」而非「退潮」消化——事实上 08-31 传媒/AI 应用确实接力（数字媒体 +7.19%）。",
 "o1_cond": "注意：承接建立在硬件出货之上，硬件止跌回流则承接盘被抽血；确认标准 = 承接延续 + 高度晋级（6板）同时成立，缺一即视为末端接力。",
 "o2_tag": "电子硬件 / 医药兑现方向（回避）",
 "o2_t": "半导体 / 通信设备 / 生物制品 / 医疗服务",
 "o2_d": "08-28 暗盘大额流出且行为标记「出货」（半导体 −122.58亿、通信设备 −59.20亿），医药链同步领跌——Smart money 撤退的方向不做左侧承接。",
 "o2_cond": "注意：暗盘连续大额流出方向，等待流出收敛 + 缩量企稳再评估；若 08-31 流出进一步放大，确认全面撤退、压缩风险敞口。",
 "o3_tag": "退潮确认信号（警戒）",
 "o3_t": "涨股比失守 50% / 量能续缩 / 补涨潮熄火",
 "o3_d": "08-28 涨股比 56%（自 61% 回落）、量能停止放大——若 08-31 涨股比失守 50% 且成交跌破 ¥2万亿，确认情绪末端转入退潮。",
 "o3_cond": "注意：退潮确认前维持中性偏低仓位；确认后执行防守纪律；右侧信号 = 缩量企稳 + 新主线高度重建（连板数据恢复后跟踪）。",
 "o_rules_t": "交易规则（08-31）",
 "o_r1": "<b>仓位</b>：估值 10 年分位 87.22% 极值区 + 主力大额兑现——仓位降至 ≤4 成，不加杠杆；指数强势不构成持仓理由，资金行为优先。",
 "o_r2": "<b>退潮确认</b>：涨股比失守 50% 或成交跌破 ¥2万亿，确认退潮，进一步压缩至防守仓位；低位补涨潮若 08-31 集体熄火，同样视为确认信号。",
 "o_r3": "<b>主线参与</b>：软件/题材承接方向仅作结构观察（暗盘是否延续），不追涨停潮；硬件/医药等兑现方向回避，等待流出收敛。",
 "o_r4": "<b>回避清单</b>：暗盘大额流出的半导体/通信设备、医药链弱势方向、两融集中且不可视的高位方向、补涨潮涨停股的次日接力。",
 "o_r5": "<b>风控</b>：以 MA60（上证 3957.86）为多空分界，08-28 已失守——若 08-31 收复失败且量能续缩，执行防守；两融数据恢复前不加重杠杆。",
 "o_compliance": "<b>合规说明：</b>本展望仅给出板块方向与交易规则，不涉及具体个股推荐；群体心理定位与板块推断基于 2026-08-28 真实行情数据，市场有风险，决策须独立。",
 "t_sec_source": "数据来源与日期口径",
 "s_breadth": "涨跌分布 / 总览",
 "s_breadth_v": "iFinD search_securities 历史日筛选（08-28 涨 3007 / 跌 2384，平 = 总数−涨−跌）；2026-08-28 收盘（westock updown 快照当日缺，回补期替代源）",
 "s_portrait": "市场画像 summary",
 "s_portrait_v": "回补组装：iFinD 历史日筛选 + data_kline 自算 + sector_daily 当日快照；2026-08-28（涨股比 56%、冲高分化）",
 "s_index": "指数表现",
 "s_index_v": "westock data_kline 260 根自算（MA/BOLL/MACD/RSI/KDJ 与官方 market_statis_technical@09-07 锚点核验偏差 0.0000）；2026-08-28 收盘",
 "s_sector": "板块排行 / 资金流",
 "s_sector_v": "westock · data_sector 当日快照（quant/sector_daily/2026-08-28.json）；2026-08-28（925 板块，550 收红、499 出货）",
 "s_hot": "热搜股票",
 "s_hot_v": "westock · 领涨板块+涨停个股综合（data_hot 历史缺，回补期以板块领涨股替代）；2026-08-28（渔业/地产服务/饰品居前，深中华A +9.99%）",
 "s_macro": "核心宏观",
 "s_macro_v": "westock · data_macro 前期复核（月频）；PMI/产能/社融为前期值，CPI/M1-M2/10Y/LPR 沿用前期",
 "s_margin": "两融（个股）",
 "s_margin_v": "westock · 两融接口降级 + 回补窗口无快照，数据暂缺，未编造",
 "s_main": "主力5日净流入",
 "s_main_v": "westock · tool_ranking 降级期 + 历史快照缺，无法回补；当日主力行为由 sector_daily 板块资金（主力/散户/暗盘）呈现",
 "s_board": "连板高度",
 "s_board_v": "08-28 当日连板名单数据源缺失（未编造）；参考口径：08-27 页 5板（深中华A，延迟取 08-26）、08-31 页 6板（海鸥住工）",
 "s_gap": "数据缺口",
 "s_gap_v": "涨跌停家数、连板名单、两融余额、融资单日变动、主力5日排名、风格轮动读数在 08-28 回补窗口均无真实数据源，已如实标注、未编造；估值 PE_TTM 21.15 为 08-28 口径（中证全指，滞后一交易日发布）；涨跌分布为 iFinD 历史日筛选口径",
 "t_src_note": "时间口径：所有时点按北京时间。宏观为月频 / 季频，与日频行情不可直接对齐，已分别标注。涨跌分布 / 指数 / 板块均为 2026-08-28 当日真实数据（回补期：广度来自 iFinD 历史筛选、指数技术来自 K 线自算并经官方锚点核验）；涨跌停、连板、两融、主力5日暂缺，均已标注。",
 "disc1": "免责声明：以上内容基于公开数据和量化分析，仅供参考，不构成投资建议。市场有风险，投资需谨慎。任何投资决策应结合个人风险承受能力、资金状况和投资目标独立判断，必要时咨询持牌专业机构。过往表现不预示未来收益。",
 "disc2": "本研判为「群体心理 / 条件框架」分析，非买卖指令；风险读数与偏差严重度为模型综合映射，须与价格结构、估值、资金流向交叉验证，不可单独作为交易依据。",
 "t_foot": "群体心理风险雷达 · 由 westock / iFinD 官方行情数据生成 · 仅供研究参考",
}

EN = {
 "t_headline_sub": "2026-08-28 · Close",
 "hk_stage": "Stage", "hv_stage": "<b>High-then-divergence / structural gear shift</b> (08-28)",
 "hk_upratio": "Up-ratio", "hv_upratio": "<b>56%</b> (prev 08-27 61% · ↓ 5pct, breadth eases from the high)",
 "hk_lim": "Limit-up / -down", "hv_lim": "<b>—</b> / <b>—</b> (limit counts missing at source, not fabricated)",
 "hk_amt": "Turnover", "hv_amt": "<b>¥2.10tn</b> (slightly shrinking −¥24.2bn, still 106.4% of 5d avg)",
 "hk_cycle": "Sentiment cycle", "hv_cycle": "<b>High-then-divergence / structural gear shift</b>",
 "hk_risk": "Risk level", "hv_risk": "<b class=\"hl-risk\">High</b> (unchanged)",
 "hk_flag": "Key flag",
 "hv_flag": "Up-ratio 61%→<b>56%</b> off the high, turnover ¥2.10tn stops expanding (−¥24.2bn) — indices fade after the push (SSE −0.11%, intraday 3970.31 then back off); the structure swung violently: Monday's electronics leaders were distributed en masse (Semis dark −¥12.26bn, Comm Equipment −¥5.92bn, both 'distribution') while capital rotated into Fisheries / Real-Estate Services / Accessories and Xinchuang / Cross-border E-commerce / Software (dark flows +¥7.3bn combined); 499 of 925 sectors (54%) 'distributing' — <b>divergence deepening beneath a calm surface</b>; limit counts / ladder / margin details missing, not fabricated.",
 "tk1": "Stage", "tv1": "A-shares 08-28 shift from 08-27's 'expanding reversal / volume-price resonance' into '<b>high-then-divergence / structural gear shift</b>': up-ratio eases to <b>56%</b> (3007 up / 2384 down / 171 flat, −5pct from 61%), SSE <b>−0.11%</b> (3952.18, pushed to 3970.31 then faded), SZ <b>−0.68%</b> (13953.07), ChiNext <b>−1.41%</b> (3424.40); turnover ¥2.10tn (106.4% of 5d avg, −¥24.2bn) stays elevated but stops expanding. Key difference vs 08-27: <b>the volume-price resonance broke</b> — indices remain in the strong zone above MA5/10/20, yet capital is changing hands massively: the electronics hardware that led Monday's reversal saw dark outflows over ¥18bn that day, while gains rotated into low-position names (Fisheries +4.55% / Real-Estate Services +3.75% / Accessories +3.42%). <b>Index calm with capital restlessness coexisting</b> — a classic top-zone divergence pattern.",
 "tk2": "Breadth eases from the high", "tv2": "Up-ratio <b>56%</b> (prev 61%, ↓5pct) · turnover <b>¥2.10tn</b> (106.4% of 5d avg, 99.4% of 10d, 93.6% of 20d, −¥24.2bn) — breadth eases from 61% but holds above 50%; sector-level divergence is fiercer: 550 up / 368 down of 925 sectors (59.5%) while <b>499 sectors (54%) show main-capital 'distribution'</b> and only 89 'offensive buying' — a positive stock count coexisting with wholesale distribution: <b>breadth is the last indicator to be falsified</b>.",
 "tk3": "Undercurrents inside a strong tape", "tv3": "SSE <b>−0.11%</b> (3952.18) closes above MA5 (3918.54) / MA10 (3926.90) / MA20 (3916.06), below MA60 (3957.86) — short/mid MAs bullish, the 60-day MA caps; MACD <b>+10.65</b> (DIF 2.97 crossing above DEA −2.36, golden cross confirmed, histogram expanding), RSI6 <b>62.44</b> (firm), KDJ_J 71.63 (elevated) — <b>firm technical readings coexisting with massive outflows</b>: technicals lag, dark flows lead; ChiNext −1.41% already broke MA5 (3428.41) — the high-beta side weakens first.",
 "tk4": "Sector structure", "tv4": "<b>Fisheries +4.55%</b> (main +¥0.34bn, offensive buying; Zhongshui Fisheries limit-up) leads, <b>Real-Estate Services +3.75%</b> (main +¥0.72bn offensive buying; Woai Woja limit-up) / <b>Accessories +3.42%</b> (main +¥1.85bn accumulation) / Refining & Trade +2.66% (Huajin limit-up) / Farm-Product Processing +2.65% follow — <b>a broad low-position, low-price catch-up rally</b>; <b>Biologics −2.73%</b> / Medical Services −2.13% / <b>Semiconductors −2.12%</b> (dark −¥12.26bn, distribution) / Electronic ChemicalsⅡ −1.80% / Comm Equipment −1.56% (dark −¥5.92bn distribution) — the electronics hardware and pharma chain that led Monday's reversal were cashed out heavily, <b>the largest single-day distribution scale of this adjustment</b>.",
 "tk5": "Limit-up ladder", "tv5": "Ladder details missing at source for this backfill window (<b>not fabricated</b>); reference signals: 08-27 basis height 5 boards (Shenzhonghua A, source-delayed to 08-26), 08-31 basis 6 boards (Haiou Zhugong) — 08-28 sat in the promotion channel; stock-level evidence: Shenzhonghua A +9.99%, Zhongshui Fisheries / Woai Woja / Huajin limit-ups — <b>a low-position catch-up wave typically marks the high-churn end of sentiment</b>.",
 "tk6": "Capital: hardware cashed out massively", "tv6": "Margin data missing (degraded interface + no snapshot in the window, <b>not fabricated</b>); sector flows reveal the core fact: <b>Semis dark −¥12.26bn, Comm Equipment −¥5.92bn, Medical Services −¥1.48bn</b>, all flagged 'distribution' — the mains that led Monday's reversal are retreating; meanwhile <b>Xinchuang +¥2.55bn (accumulation) / Cross-border E-commerce +¥2.52bn (offensive buying) / Software Development +¥2.25bn (offensive buying)</b> absorb — capital did not leave, it rotated from hardware into software and themes, <b>a high-low switch in a zero-sum game</b>; nominal risk appetite unchanged, actual fragility rising.",
 "tk7": "Valuation / style", "tv7": "PE_TTM <b>21.15</b> (10Y percentile <b>87.22%</b>, 5Y 83.25%, 3Y 72.09%; 08-28 basis, CSI All-Share with one-session publication lag) — noticeably richer than early September (20.39 / 79.52%): <b>08-28 was one of the most expensive points of this range</b>; style: HS300 −0.46% vs CSI1000 −0.36% (5/20-day rotation readings missing historically, not fabricated); from sector behaviour, capital abandons 'high-position hardware' for 'low-position themes' — valuation-anchored defence in essence; <b>high valuation + high churn + low-position catch-ups = all three end-of-sentiment signals present</b>.",
 "tk8": "Sentiment cycle", "tv8": "From 08-27's 'expanding reversal / volume-price resonance' into '<b>high-then-divergence / structural gear shift</b>': breadth off 61%, volume stops expanding, mains distribute the leaders massively (Semis −¥12.26bn) while the crowd hunts catch-ups in low-priced names — <b>the classic top structure of smart money exiting and dumb money relaying</b>; still-strong technicals (golden cross, RSI 62) are exactly the dangerous mix of 'sentiment inertia masking capital retreat'; valuation at the 87.22% 10Y percentile; risk stays <b>High</b>.",
 "t_tldr_text": "A-shares 08-28 = 'high-then-divergence / structural gear shift': up-ratio 61%→56% (3007 up / 2384 down / 171 flat), limit counts missing at source (not fabricated); SSE −0.11% (3952.18, intraday 3970.31 then faded) above MA5/10/20, below MA60; MACD golden cross expanding (+10.65), RSI6 62.44; SZ −0.68% (13953.07), ChiNext −1.41% (3424.40, broke MA5 first). Turnover ¥2.10tn (106.4% of 5d avg, −¥24.2bn) stops expanding. Fisheries +4.55% (Zhongshui limit-up) / Real-Estate Services +3.75% (Woai Woja limit-up) / Accessories +3.42% lead — broad low-position catch-ups; Biologics −2.73% / Medical Services −2.13% / Semis −2.12% (dark −¥12.26bn distribution) / Comm Equipment −1.56% (−¥5.92bn) — Monday's reversal leaders cashed out heavily. 550 of 925 sectors green but 499 (54%) 'distributing'; Xinchuang / Cross-border E-commerce / Software absorbed +¥7.3bn — a high-low switch in a zero-sum game. PE_TTM 21.15 (10Y pctile 87.22%, among the priciest of this range). Ladder / margin details missing. Risk stays High.",
 "t_risk": "Risk level", "t_risk_hi": "High",
 "c_upratio": "Up-ratio", "c_limitup": "Limit-up", "c_board": "Ladder height", "c_pe": "PE pctile", "c_pmi": "Mfg PMI", "c_turn": "Turnover",
 "t_sec_bias": "Behavioral Bias Heatmap", "t_cycle": "Sentiment Cycle (6-stage)",
 "r1": "Despair", "r2": "Doubt", "r3": "Optimism", "r4": "Euphoria", "r5": "Anxiety", "r6": "Complacency",
 "t_cycle_note": "Note: the 'Complacency / high-then-divergence' tag above is the live crowd-psychology position — 08-28 breadth (up-ratio 56%, turnover ¥2.10tn stopping its expansion) and capital behaviour (Semis dark −¥12.26bn distribution, low-position catch-up wave) show smart money retreating while the crowd stays complacent about index strength; limit counts / ladder details missing. If 08-31 sees up-ratio losing 50% with continued volume shrinkage, the ebb is confirmed; if the software/theme absorption fails (dark flows turning negative), divergence turns straight into a broad decline.",
 "t_leg": "Severity (model-mapped)", "t_bias_note": "Note: bias severity is a model mapping from the real data below (1=low, 5=high), used to show where crowd psychology is fragile — not a buy/sell recommendation for any stock.",
 "t_sec_radar": "Risk Radar",
 "t_radar_note": "Six-dimension risk readings (0–100, mapped from the real data below; higher = greater crowd fragility on that axis): crowding 70 / margin 67 / turnover 55 / breadth 51 / media 67 / valuation 89. Crowding 68→70 (ladder heading to 6 boards, low-position catch-up wave spreading, speculative chips concentrating); margin 64→67 (margin data missing, leverage invisible, nudged up cautiously for a high-churn zero-sum phase); turnover 54→55 (turnover ¥2.10tn, 106.4% of 5d avg — but the churn has turned from 'consensus' to 'divergence'); breadth 50→51 (up-ratio 61%→56% off the high yet above 50%, fragility nudging up against the 995-distribution backdrop); media 66→67 (index strength, low-position limit-up waves — temperature stays high); valuation 90→89 (PE_TTM 21.15, 10Y percentile 87.22%, still the richest tier of this range). Fragility is led by 'crowding + valuation' — a classic top-zone reading: breadth adequate, capital already retreating.",
 "ax_crowd": "Crowding", "ax_margin": "Margin", "ax_turn": "Turnover", "ax_breadth": "Breadth", "ax_media": "Media mood", "ax_val": "Valuation",
 "b_up": "Up", "b_down": "Down", "b_flat": "Flat", "b_limitup": "Limit-up", "b_limitdn": "Limit-down", "b_amt": "Turnover",
 "t_breadth_note": "Up-ratio 61%→56% (3007 up / 2384 down / 171 flat) eases from the high, limit counts missing (not fabricated); turnover ¥2.10tn (106.4% of 5d avg, −¥24.2bn) stops expanding. SSE −0.11% (3952.18, faded from 3970.31, lost MA60 3957.86) / SZ −0.68% (13953.07) / ChiNext −1.41% (3424.40, broke MA5); Fisheries +4.55% / Real-Estate Services +3.75% / Accessories +3.42% lead, Biologics −2.73% / Semis −2.12% (dark −¥12.26bn distribution) lag — 550 of 925 sectors green while 499 (54%) 'distribute'.",
 "th_metric": "Metric", "th_read": "Real reading", "th_interp": "Behavioral read",
 "ev_market": "I. Market breadth & overview",
 "ev_upratio": "Up-ratio",
 "ev_upratio_i": "61%→56% (−5pct), 3007 up / 2384 down / 171 flat — breadth eases from the high; 499/925 sectors (54%) show main-capital 'distribution' — stock breadth diverges sharply from main behaviour, gains propped by low-position catch-ups",
 "ev_limit": "Limit-up / -down",
 "ev_limit_i": "Limit counts have no real data source in this backfill window (iFinD numeric screening unreliable), <b>not fabricated</b>; stock evidence: Zhongshui Fisheries / Woai Woja / Huajin limit-ups, Shenzhonghua A +9.99% — a low-position catch-up wave is the classic micro-structure of late-stage sentiment",
 "ev_amount": "Turnover",
 "ev_amount_i": "¥2.10tn (106.4% of 5d avg, 99.4% of 10d, 93.6% of 20d, −¥24.2bn) — 08-27's ¥2.13tn expansion not sustained; volume stalling at a high = the first volume-price signal of 'resonance' turning 'divergence'",
 "ev_index": "II. Core indices (2026-08-28 close)",
 "ev_sh": "SSE Composite",
 "ev_sh_i": "−0.11% (3952.18, high 3970.31 / low 3947.80, faded from the push), above MA5 (3918.54) / MA10 (3926.90) / MA20 (3916.06), below MA60 (3957.86); MACD +10.65 (DIF 2.97 / DEA −2.36, golden cross confirmed, histogram expanding), RSI6 62.44 firm, KDJ_J 71.63 elevated; BOLL (4010.01 / 3916.06 / 3822.12) upper-mid; PE_TTM 21.15 (10Y pctile 87.22%, 08-28 basis)",
 "ev_sz": "SZ Component",
 "ev_sz_i": "−0.68% (13953.07), pushed to 14148.68 then faded; short-term momentum decaying; still deeply weak on 60 days",
 "ev_cyb": "ChiNext",
 "ev_cyb_i": "−1.41% (3424.40), first to break MA5 (3428.41) — the high-beta side is most sensitive to capital retreat, corroborating the heavy dark outflows in Semis / Comm Equipment",
 "ev_sector": "III. Sector ranking & main line",
 "ev_secup": "Leading sectors",
 "ev_secup_i": "Fisheries +4.55% (main +¥0.34bn offensive buying; Zhongshui Fisheries limit-up) leads, Real-Estate Services +3.75% (main +¥0.72bn; Woai Woja limit-up) / Accessories +3.42% (main +¥1.85bn accumulation) / Refining & Trade +2.66% (Huajin limit-up) / Farm-Product Processing +2.65% follow — low-position low-price names catch up broadly, the main line scattered; 550 of 925 sectors green (59.5%)",
 "ev_secdn": "Lagging sectors",
 "ev_secdn_i": "Biologics −2.73% / Medical Services −2.13% / Semiconductors −2.12% (dark −¥12.26bn, 'distribution') / Electronic ChemicalsⅡ −1.80% / Comm Equipment −1.56% (dark −¥5.92bn distribution) — the electronics hardware and pharma chain that led Monday's reversal cashed out at the largest single-day scale",
 "ev_board": "Extreme themes",
 "ev_board_i": "Ladder details missing at source for the backfill window (not fabricated); reference: 08-27 basis height 5 boards (Shenzhonghua A), 08-31 basis 6 boards (Haiou Zhugong) — 08-28 sat in the promotion channel; Shenzhonghua A +9.99%, Zhongshui Fisheries / Woai Woja / Huajin limit-ups — the catch-up wave continues",
 "ev_flow": "IV. Capital: ladder / main / margin",
 "ev_height": "Ladder height",
 "ev_height_i": "No same-day ladder list for 08-28 (not fabricated); structural signals: concept dark-flows concentrated in Xinchuang +¥2.55bn (accumulation) / Cross-border E-commerce +¥2.52bn (offensive buying) / Software Development +¥2.25bn (offensive buying) — speculative money stayed, only switched; the height game ran on to 08-31's 6 boards",
 "ev_main": "Main capital 5d net inflow TOP",
 "ev_main_i": "No main-5d ranking snapshot in the backfill window (tool_ranking degraded + historical gap), <b>not fabricated</b>; visible same-day signals: Semis dark −¥12.26bn / Comm Equipment −¥5.92bn massive distribution; Accessories main +¥1.85bn / Refining & Trade +¥5.09bn / Farm-Product Processing +¥3.54bn inflows — hardware→software, high→low switching within a closed system",
 "ev_margin": "Daily margin change TOP",
 "ev_margin_i": "Margin interface degraded + no snapshot in the window — daily change and aggregate balance both unavailable, <b>not fabricated</b>; with high churn + valuation at the 87.22% 10Y percentile, invisible leverage concentration is the biggest blind spot — historically, margin concentrates in the current main line (electronics hardware), and its distribution amplifies the leveraged drawdown",
 "ev_hot": "Hot / top gainers",
 "ev_hot_i": "Hotspot structure: Shenzhonghua A +9.99% (Accessories, 5 boards on the 08-27 basis) / Zhongshui Fisheries limit-up (Fisheries +4.55%) / Woai Woja limit-up (Real-Estate Services +3.75%) / Huajin limit-up (Refining & Trade) — a low-position limit-up wave with theme absorption (Xinchuang / Cross-border E-commerce / Software): the profit effect looks lively but is structurally late-stage",
 "ev_margintotal": "Aggregate margin balance",
 "ev_margintotal_i": "Gap: margin balance and daily change have no real data source in the 08-28 backfill window — flagged honestly, not fabricated; breadth (iFinD historical-day screen) / indices (kline self-computed, 0.0000 deviation vs official anchor) / sectors (same-day snapshot) are all real 2026-08-28 data",
 "ev_macro": "V. Core macro indicators",
 "ev_pmi": "Mfg PMI (Jul)",
 "ev_pmi_i": "Fundamentals contract — forming the sharpest macro-valuation divergence of the period against the 87.22% 10Y percentile",
 "ev_capu": "Capacity utilisation (Q2)",
 "ev_capu_i": "Real-economy momentum weakens; theme catch-ups lack industry-boom support",
 "ev_cpi": "CPI (Jul)",
 "ev_cpi_i": "Low inflation, weak demand; price-hike narratives lack data support",
 "ev_social": "Social financing (Jul)",
 "ev_social_i": "Weak credit demand, capital detours into stocks = liquidity-driven; top zones are most liquidity-dependent",
 "ev_m1m2": "M1-M2 spread",
 "ev_m1m2_i": "Active money weak, capital idles, typical late-cycle phenomenon",
 "ev_yield": "10Y gov bond yield",
 "ev_yield_i": "Extremely low risk-free rate, supports valuation yet reflects growth worry",
 "ev_lpr": "LPR",
 "ev_lpr_i": "Accommodative stance unchanged",
 "t_ev_note": "Data basis: macro indicators are monthly (to 2026-07) or carried forward; breadth (iFinD historical-day screen: 3007 up / 2384 down) / indices & turnover (data_kline self-computed, 0.0000 deviation vs the official market_statis_technical@09-07 anchor) / sectors (sector_daily same-day snapshot) are real 2026-08-28 data. Valuation PE_TTM 21.15 is 08-28 basis (CSI All-Share, one-session publication lag); limit counts, ladder list, margin, main-5d ranking missing — flagged, not fabricated. See 'Sources and date basis' at the end.",
 "t_sec_risk": "Risk Stratification",
 "rc1_tag": "Red zone · Extreme valuation + smart money retreating",
 "rc1_t": "Distribution and the leverage blind spot at a high-divergence top",
 "rc1_d": "PE_TTM 10Y percentile 87.22% (richest tier of this range) + Semis dark −¥12.26bn single-day distribution + 499 sectors (54%) 'distributing' + margin invisible — index strength is inertia, capital behaviour leads: the classic top-zone mix of 'adequate quantity signals, deteriorating behaviour signals'; risk stays High.",
 "rc1_rep": "Represented by: electronics hardware with massive dark outflows (Semis −¥12.26bn / Comm Equipment −¥5.92bn) / pharma chain (Biologics −2.73%, Medical Services −2.13%) / margin-concentrated directions (invisible)",
 "rc1_cond": "Condition frame: no chasing high positions, no catching dark-outflow main lines; at valuation extremes only reduce; until margin and ladder data resume, treat dark flows as the only credible capital signal.",
 "rc2_tag": "Amber zone · The low-position catch-up game",
 "rc2_t": "Durability of the low-position low-price catch-up wave",
 "rc2_d": "Fisheries / Real-Estate Services / Accessories / Refining get small main inflows and batch limit-ups — a catch-up wave is the classic form of late-stage sentiment: the profit effect lives on but sinks into ever-weaker names; the participation window is short and relay risk high.",
 "rc2_rep": "Represented by: Fisheries (Zhongshui Fisheries) / Real-Estate Services (Woai Woja) / Accessories / Refining & Trade (Huajin) / Farm-Product Processing",
 "rc2_cond": "Condition frame: observe catch-ups only, no relaying; confirmation = main inflows 2 straight days with unshrinking turnover; if the limit-up wave dies the next session, late-stage sentiment is confirmed.",
 "rc3_tag": "Green zone · Software-theme absorption (fragile)",
 "rc3_t": "Xinchuang / Cross-border E-commerce / Software Development dark absorption",
 "rc3_d": "Xinchuang +¥2.55bn (accumulation) / Cross-border E-commerce +¥2.52bn (offensive buying) / Software Development +¥2.25bn (offensive buying) — capital switches from hardware to software and themes; in a zero-sum game nominal risk appetite is unchanged; but the 'absorption' is built on hardware distribution — if hardware stabilises and flows back, the absorption side gets drained.",
 "rc3_rep": "Represented by: Xinchuang / Cross-border E-commerce / Software Development (industry dark +¥2.25bn offensive buying)",
 "rc3_cond": "Condition frame: structure observation only; confirmation = hardware outflows converging + software absorption continuing; if hardware keeps distributing heavily and software absorption turns negative, a full retreat is confirmed.",
 "t_sec_outlook": "Next session (08-31 Mon) outlook",
 "o_logic": "Reasoning (based on the 08-28 close + crowd-psychology position)",
 "o_logic_text": "Extending 08-28's 'high-then-divergence / structural gear shift': a strong tape (MACD golden cross, RSI 62) coexists with massive capital retreat (Semis −¥12.26bn), low-position catch-ups continue and theme absorption holds — an end-of-sentiment tug-of-war. Sector directions and trading rules for 08-31 follow (<b>no individual stock recommendations</b>).",
 "o1_tag": "Software / theme absorption (watch)",
 "o1_t": "Xinchuang / Cross-border E-commerce / Software Development / Media-AI",
 "o1_d": "The most concentrated dark absorption on 08-28 (+¥7.3bn combined); if 08-31 keeps inflows while hardware distribution converges, sentiment digests via a 'high-low switch' rather than an 'ebb' — indeed Media/AI did relay on 08-31 (Digital Media +7.19%).",
 "o1_cond": "Caution: the absorption is built on hardware distribution — if hardware stabilises and flows back, the absorption side gets drained; confirmation = absorption continuing + height promoting (6 boards) at once; missing either, treat it as an end-stage relay.",
 "o2_tag": "Hardware / pharma distribution (avoid)",
 "o2_t": "Semiconductors / Comm Equipment / Biologics / Medical Services",
 "o2_d": "Massive dark outflows flagged 'distribution' on 08-28 (Semis −¥12.26bn, Comm Equipment −¥5.92bn) with pharma leading down — do not left-side catch the directions smart money is leaving.",
 "o2_cond": "Caution: for directions with consecutive heavy dark outflows, wait for convergence + shrinking-volume stabilisation before reassessing; if 08-31 sees further expansion, a full retreat is confirmed — cut risk exposure.",
 "o3_tag": "Ebbing confirmation signals (alert)",
 "o3_t": "Up-ratio losing 50% / volume shrinking / catch-up wave dying",
 "o3_d": "08-28 up-ratio 56% (off 61%), volume stopped expanding — if 08-31 sees up-ratio losing 50% and turnover below ¥2tn, the end-of-sentiment phase confirms into an ebb.",
 "o3_cond": "Caution: hold a neutral-to-low book until confirmed; defensive discipline after; right-side signal = shrinking-volume stabilisation + a new main line rebuilding height (track once ladder data resumes).",
 "o_rules_t": "Trading rules (08-31)",
 "o_r1": "<b>Position</b>: valuation at the 87.22% 10Y percentile + heavy main distribution — cut to ≤40%, no leverage; index strength is no reason to hold; capital behaviour comes first.",
 "o_r2": "<b>Ebbing confirmation</b>: up-ratio losing 50% or turnover below ¥2tn confirms the ebb — cut further to defensive; the catch-up wave dying together on 08-31 is an equally valid confirmation.",
 "o_r3": "<b>Main-line participation</b>: software/theme absorption as structure observation only (is the dark flow persisting?), no chasing limit-up waves; avoid distribution directions (hardware / pharma), wait for convergence.",
 "o_r4": "<b>Avoid list</b>: Semis / Comm Equipment with heavy dark outflows, weak pharma directions, margin-concentrated invisible high positions, next-day relays of catch-up limit-ups.",
 "o_r5": "<b>Risk control</b>: use MA60 (SSE 3957.86) as the bull/bear line — 08-28 already lost it; a failed reclaim on 08-31 with shrinking volume = execute defence; no added leverage until margin data resumes.",
 "o_compliance": "<b>Compliance:</b> this outlook gives sector directions and trading rules only, with no individual stock recommendations; the crowd-psychology position and sector inferences are based on real 2026-08-28 market data. Markets carry risk; decisions must be independent.",
 "t_sec_source": "Sources & date basis",
 "s_breadth": "Breadth / overview",
 "s_breadth_v": "iFinD search_securities historical-day screen (08-28: 3007 up / 2384 down, flat = total − up − down); 2026-08-28 close (same-day westock updown snapshot missing, backfill fallback)",
 "s_portrait": "Market portrait summary",
 "s_portrait_v": "Backfill assembly: iFinD historical-day screen + data_kline self-computed + sector_daily same-day snapshot; 2026-08-28 (up-ratio 56%, high-then-divergence)",
 "s_index": "Index performance",
 "s_index_v": "westock data_kline 260 bars self-computed (MA/BOLL/MACD/RSI/KDJ cross-checked against the official market_statis_technical@09-07 anchor with 0.0000 deviation); 2026-08-28 close",
 "s_sector": "Sector ranking / flows",
 "s_sector_v": "westock · data_sector same-day snapshot (quant/sector_daily/2026-08-28.json); 2026-08-28 (925 sectors, 550 green, 499 distributing)",
 "s_hot": "Hot stocks",
 "s_hot_v": "westock · leading sectors + limit-up stocks composite (data_hot missing historically, backfill uses sector leaders); 2026-08-28 (Fisheries / Real-Estate Services / Accessories on top, Shenzhonghua A +9.99%)",
 "s_macro": "Core macro",
 "s_macro_v": "westock · data_macro carried forward (monthly); PMI/capacity/social-financing are prior values; CPI/M1-M2/10Y/LPR carried forward",
 "s_margin": "Margin (stocks)",
 "s_margin_v": "westock · margin interface degraded + no snapshot in the backfill window, data missing, not fabricated",
 "s_main": "Main capital 5d net inflow",
 "s_main_v": "westock · tool_ranking degraded + historical snapshot missing, cannot backfill; same-day main behaviour shown via sector_daily sector flows (main/retail/dark)",
 "s_board": "Ladder height",
 "s_board_v": "08-28 same-day ladder list missing at source (not fabricated); reference basis: 08-27 page 5 boards (Shenzhonghua A, delayed to 08-26), 08-31 page 6 boards (Haiou Zhugong)",
 "s_gap": "Data gaps",
 "s_gap_v": "Limit counts, ladder list, margin balance, daily margin change, main-5d ranking and style-rotation readings all lack real data sources in the 08-28 backfill window — flagged, not fabricated; valuation PE_TTM 21.15 is 08-28 basis (CSI All-Share, one-session publication lag); breadth is the iFinD historical-screen basis",
 "t_src_note": "Timing: all timestamps are Beijing time. Macro data are monthly/quarterly and cannot be aligned directly with daily quotes; each is flagged. Breadth / indices / sectors are real 2026-08-28 data (backfill: breadth from the iFinD historical screen, indices/technicals self-computed and anchor-verified); limit counts, ladder, margin, main-5d missing — all flagged.",
 "disc1": "Disclaimer: the above is based on public data and quantitative analysis, for reference only, not investment advice. Markets carry risk; investment decisions should be made independently per your own risk tolerance, financial status and goals, and consult a licensed professional when necessary. Past performance does not predict future returns.",
 "disc2": "This assessment is 'crowd psychology / conditional framework' analysis, not a trading order; risk readings and bias severities are model mappings and must be cross-validated with price structure, valuation and flows, not used alone as a trade basis.",
 "t_foot": "Crowd Psychology Risk Radar · generated from westock / iFinD official market data · research reference only",
}

zh = dict(zh0); zh.update(ZH)
en = dict(en0); en.update(EN)
assert set(zh0) <= set(zh) and set(en0) <= set(en), "键丢失"

def serialize(d):
    return "\n".join('      %s:"%s",' % (k, esc(d[k])) for k in d)


new_en = "en:{\n" + serialize(en) + "\n    }"
html = html[:m_en.start()] + new_en + html[m_en.end():]
new_zh = "zh:{\n" + serialize(zh) + "\n    },"
html = html[:m_zh.start()] + new_zh + html[m_zh.end():]

BIAS = [
 {"zh":"羊群效应","en":"Herding","sev":4,
  "zhd":"主力单日在半导体（暗盘 −122.58亿）与通信设备（−59.20亿）大额撤退的同时，群体正涌入渔业/地产服务/饰品等低位涨停潮——资金迁徙的两侧都是羊群：撤退侧踩踏、承接侧追涨。",
  "end":"While mains retreated massively from Semis (dark −¥12.26bn) and Comm Equipment (−¥5.92bn) in a single day, the crowd poured into low-position limit-up waves (Fisheries / Real-Estate Services / Accessories) — herds on both sides of the migration: stampeding out, chasing in."},
 {"zh":"过度自信","en":"Overconfidence","sev":4,
  "zhd":"指数仍处强势区（MACD 金叉、RSI6 62.44）让群体把「主力大额兑现」误读为「正常换手」，自信于「强势不改」——技术指标的滞后性恰在此刻制造最大的认知差。",
  "end":"A still-strong tape (MACD golden cross, RSI6 62.44) lets the crowd misread 'massive main distribution' as 'normal churn', confident that 'strength is intact' — the lagging nature of technicals creates the largest cognitive gap exactly now."},
 {"zh":"处置效应","en":"Disposition","sev":4,
  "zhd":"半导体/通信设备的持仓者在暗盘大额流出当日仍倾向持有（处置效应延迟止损），而低位补涨股的浮盈者迅速兑现——「抱着亏的不卖、赚的点就跑」在顶部区同时放大两侧的错配。",
  "end":"Semiconductor / Comm Equipment holders still tend to hold on the heavy dark-outflow day (disposition delaying stops) while low-position catch-up holders take profits instantly — 'clutching losers, flipping winners' amplifies both mismatches at the top."},
 {"zh":"叙事偏差","en":"Narrative","sev":3,
  "zhd":"「信创 + 跨境电商 + 软件承接」叙事为硬件的兑现提供了「高低切换、牛市没完」的安心故事——但承接总量（+73亿）远小于兑现总量（−180亿+），故事规模与资金规模并不匹配。",
  "end":"The 'Xinchuang + Cross-border E-commerce + software absorption' narrative offers a soothing 'high-low switch, the bull is intact' story for the hardware distribution — but absorption (+¥7.3bn) is far smaller than distribution (−¥18bn+): the story and the money do not match in scale."},
 {"zh":"锚定偏差","en":"Anchoring","sev":3,
  "zhd":"群体锚定 08-27 的「放量反包 = 主力进场」认为回调即买点，忽视当日暗盘才是资金真实投票；同样有人锚定上证 3970「前高不破就有新高」——MA60（3957.86）失守已给出不同答案。",
  "end":"The crowd anchors to 08-27's 'expanding reversal = mains entering' and reads any dip as a buy, ignoring that dark flows are the capital's real vote; others anchor to SSE 3970 ('no new high unless the old one breaks') — the loss of MA60 (3957.86) already answered differently."},
 {"zh":"确认偏误","en":"Confirmation Bias","sev":3,
  "zhd":"多头只看涨停潮与 550 板块收红，忽视 499 板块「出货」与估值 10 年分位 87.22%；空头只看暗盘流出，忽视题材承接 +73亿 与梯队晋级——两侧都在选择性取证。",
  "end":"Bulls watch only the limit-up wave and 550 green sectors, ignoring 499 'distributing' sectors and the 87.22% 10Y valuation percentile; bears watch only dark outflows, ignoring +¥7.3bn theme absorption and ladder promotion — both sides are cherry-picking evidence."},
 {"zh":"代表性启发","en":"Representativeness","sev":3,
  "zhd":"把「深中华A 5板、海鸥住工将晋级6板」的连板标杆代表「投机环境友好」，忽视标杆是个位数样本而全市场 54% 板块在出货——用极端样本代表总体是顶部区的常见误判。",
  "end":"Reading the ladder benchmarks (Shenzhonghua A 5 boards, Haiou Zhugong heading to 6) as 'a friendly speculative environment' ignores that benchmarks are single-digit samples while 54% of all sectors are distributing — representing the whole by extremes is a common top-zone misjudgement."},
 {"zh":"心理账户/赌徒谬误","en":"Mental Acct / Gambler","sev":3,
  "zhd":"把「指数没跌多少」记入「安全」账户、把「涨停家数还多」记入「热度」账户，分别评估而忽视联合概率：估值极值 + 主力兑现 + 量能停放的联合信号历史上极少良性收场。",
  "end":"Booking 'indices barely fell' into a 'safe' account and 'many limit-ups' into a 'heat' account, evaluated separately while ignoring the joint probability: extreme valuation + main distribution + stalling volume has rarely ended well historically."},
 {"zh":"近因偏差","en":"Recency","sev":4,
  "zhd":"08-27 的放量反包记忆犹新，群体把它外推为「趋势重启」，对 08-28 的兑现信号赋予过低权重——而 09 月初的走势（09-09 起退潮）证明 08-28 的分歧信号才是正确的前瞻。",
  "end":"The 08-27 expanding reversal is fresh, and the crowd extrapolates it into 'the trend restarts', underweighting 08-28's distribution signals — the early-September path (ebb from 09-09) proved 08-28's divergence signals were the correct forward read."},
 {"zh":"损失厌恶","en":"Loss Aversion","sev":2,
  "zhd":"补涨潮的快速轮转让踏空焦虑（错失厌恶）压倒损失厌恶，群体在「怕错过低位补涨」中接受了最差的赔率；对已兑现的硬件浮盈则产生「再来一波」的报复性期待。",
  "end":"In the fast-rotating catch-up wave, FOMO overrides loss aversion — the crowd accepts the worst odds 'for fear of missing the low-position relay', while harbouring revenge expectations of 'one more wave' on already-cashed hardware gains."},
]
bias_js = "var BIAS = [\n" + ",\n".join(
    "    {zh:\"%s\",en:\"%s\",sev:%d,zhd:\"%s\",end:\"%s\"}" % (esc(b["zh"]), esc(b["en"]), b["sev"], esc(b["zhd"]), esc(b["end"]))
    for b in BIAS) + "\n  ];"
html, _n = re.subn(r'var BIAS = \[.*?\n  \];', bias_js, html, count=1, flags=re.S)
assert _n == 1, "BIAS 替换失败"

BODY = [
 # SVG rects：涨 12%(58px)→56%(280px)；跌 88%(442px,x=72)→44%(220px,x=294)
 ('<rect x="14" y="14" width="58" height="26" fill="#d8392b"/>',
  '<rect x="14" y="14" width="280" height="26" fill="#d8392b"/>'),
 ('<rect x="72" y="14" width="442" height="26" fill="#1a9e5a"/>',
  '<rect x="294" y="14" width="220" height="26" fill="#1a9e5a"/>'),
 ('<text x="167" y="33" fill="#fff" font-size="14" font-weight="800" text-anchor="middle">12%</text>',
  '<text x="154" y="33" fill="#fff" font-size="14" font-weight="800" text-anchor="middle">56%</text>'),
 ('<text x="407" y="33" fill="#fff" font-size="14" font-weight="800" text-anchor="middle">88%</text>',
  '<text x="404" y="33" fill="#fff" font-size="14" font-weight="800" text-anchor="middle">44%</text>'),
 ('<text x="514" y="33" fill="#6b675f" font-size="11" font-weight="700" text-anchor="end">1% 平盘</text>',
  '<text x="514" y="33" fill="#6b675f" font-size="11" font-weight="700" text-anchor="end">3% 平盘</text>'),
 # stat rows
 ('<text x="340" y="72" fill="#d8392b">643</text>',
  '<text x="340" y="72" fill="#d8392b">3007</text>'),
 ('<text x="340" y="92" fill="#1a9e5a">4870</text>',
  '<text x="340" y="92" fill="#1a9e5a">2384</text>'),
 ('<text x="340" y="112" fill="#6b675f">49</text>',
  '<text x="340" y="112" fill="#6b675f">171</text>'),
 ('<text x="340" y="138" fill="#d8392b">40</text>',
  '<text x="340" y="138" fill="#d8392b">—</text>'),
 ('<text x="340" y="158" fill="#1a9e5a">21</text>',
  '<text x="340" y="158" fill="#1a9e5a">—</text>'),
 ('<text x="340" y="184" fill="#1c1b19">¥1.97万亿</text>',
  '<text x="340" y="184" fill="#1c1b19">¥2.10万亿</text>'),
 # annotations
 ('<text x="355" y="72">（占 12%，较上一报告日（09-10） −5pct）</text>',
  '<text x="355" y="72">（占 56%，较上一报告日（08-27） −5pct）</text>'),
 ('<text x="355" y="92">（占 88%，较上一报告日（09-10） +7pct）</text>',
  '<text x="355" y="92">（占 44%，较上一报告日（08-27） +5pct）</text>'),
 ('<text x="355" y="112">（占 1%）</text>',
  '<text x="355" y="112">（占 3%）</text>'),
 ('<text x="355" y="138">（较前日 +2 只，连板高度 4板）</text>',
  '<text x="355" y="138">（涨跌停家数历史数据源缺失，未编造）</text>'),
 ('<text x="355" y="158">（较前日 +19 只，恐慌扩散）</text>',
  '<text x="355" y="158">（连板明细同样缺失；参考 08-27 口径 5板）</text>'),
 ('<text x="355" y="184">（环比 +3200亿，放量普跌）</text>',
  '<text x="355" y="184">（环比 −242亿，高位停止放大）</text>'),
 # evidence table number cells
 ('<td><span class="val up">12%</span>（涨643 / 跌4870 / 平49）</td>',
  '<td><span class="val up">56%</span>（涨3007 / 跌2384 / 平171）</td>'),
 ('<td><span class="val up">40</span> / <span class="val down">21</span></td>',
  '<td><span class="val">— / —</span>（数据源缺失）</td>'),
 ('<td><span class="val">¥1.97万亿</span>（较前次 +3200亿，放量普跌）</td>',
  '<td><span class="val">¥2.10万亿</span>（较前次 −242亿，高位停止放大）</td>'),
 ('<td><span class="val down">3888.11　−1.18%</span></td>',
  '<td><span class="val down">3952.18　−0.11%</span></td>'),
 ('<td><span class="val down">13471.26　−1.08%</span></td>',
  '<td><span class="val down">13953.07　−0.68%</span></td>'),
 ('<td><span class="val down">3322.04　−0.49%</span></td>',
  '<td><span class="val down">3424.40　−1.41%</span></td>'),
 ('<td><span class="val up">地面兵装Ⅱ +4.44%</span>（主力净流入 +50.22亿，行为「抢筹」）<br>通信设备 +1.66%（主力 +839.89亿，全行业第一）/ 元件 +1.80%（+638.35亿）/ 玻璃玻纤 +2.63% 跟随<br>全市场 927 个板块仅 33 个收红，733 个呈主力「出货」</td>',
  '<td><span class="val up">渔业 +4.55%</span>（主力 +3.38亿，行为「抢筹」，中水渔业涨停）<br>房地产服务 +3.75%（主力 +7.23亿 抢筹，我爱我家涨停）/ 饰品 +3.42%（+18.53亿 建仓）/ 炼化及贸易 +2.66% 跟随<br>全市场 925 个板块 550 个收红，499 个（54%）呈主力「出货」</td>'),
 ('<td><span class="val down">工业金属 −5.04%</span>（主力 +261.18亿 但散户流入 +303.79亿更多，暗盘 −42.6亿 → 实为「出货」）<br>农产品加工 −4.36% / 渔业 −4.34%<br>资源与前期题材在恐慌中集中补跌</td>',
  '<td><span class="val down">生物制品 −2.73%</span><br>医疗服务 −2.13% / 半导体 −2.12%（暗盘 −122.58亿，行为「出货」）/ 电子化学品Ⅱ −1.80% / 通信设备 −1.56%（暗盘 −59.20亿 出货）<br>08-27 反包主力电子硬件与医药链遭大额兑现</td>'),
 ('<td><span class="val up">连板高度 4 板</span>（瑞尔特，新龙头接棒桂林旅游）<br>共 40 只连板（持平）；3板：鼎信通讯 / 闽东电力；2板：凯盛新能 / 超声电子 / 九鼎新材 / 中新赛克——龙头一日一换</td>',
  '<td><span class="val">连板明细数据源缺失</span>（回补窗口无真实名单，未编造）<br>参考：08-27 口径 5板（深中华A，延迟取 08-26）→ 08-31 口径 6板（海鸥住工）<br>个股佐证：深中华A +9.99%、中水渔业/我爱我家/华锦股份涨停——低位补涨潮</td>'),
 ('<td><span class="val up">瑞尔特 4板</span>（2026-09-11）</td>',
  '<td><span class="val">连板名单缺失（08-28）</span></td>'),
 ('<td><span class="val">主力5日净流入 TOP（tool_ranking 降级期，09-09 口径沿用）</span></td>',
  '<td><span class="val">主力5日净流入 TOP（降级期 + 历史快照缺，未编造）</span></td>'),
 ('<td><span class="val">融资单日变动 TOP（两融接口降级，数据暂缺，未编造）</span></td>',
  '<td><span class="val">融资单日变动 TOP（两融接口降级 + 无快照，数据暂缺，未编造）</span></td>'),
 ('<td><span class="val up">瑞尔特 4板</span>（卫浴出海）<br>地面兵装Ⅱ +4.44%（主力 +50.22亿 抢筹）<br>通信设备 +1.66% / 元件 +1.80% / 玻璃玻纤 +2.63%<br>工业金属 −5.04% / 农产品加工 −4.36% / 渔业 −4.34%</td>',
  '<td><span class="val up">深中华A +9.99%</span>（饰品，08-27 口径 5板）<br>渔业 +4.55%（中水渔业涨停）/ 房地产服务 +3.75%（我爱我家涨停）<br>信创 +25.53亿 / 跨境电商 +25.24亿 / 软件开发 +22.46亿（暗盘承接）<br>半导体 −2.12%（−122.58亿 出货）/ 通信设备 −1.56%（−59.20亿）</td>'),
 # static header date + Next-Session
 ('<b>2026-09-11 收盘（北京时间，盘后）</b>',
  '<b>2026-08-28 收盘（北京时间，盘后）</b>'),
 ("Next-Session Outlook (09-14 Mon)", "Next-Session Outlook (08-31 Mon)"),
 # 顶部 chips 静态值
 ('<span data-i18n="c_upratio">涨股比</span> <b>12%</b></span>',
  '<span data-i18n="c_upratio">涨股比</span> <b>56%</b></span>'),
 ('<span data-i18n="c_limitup">涨停</span> <b>40</b></span>',
  '<span data-i18n="c_limitup">涨停</span> <b>—</b></span>'),
 ('<span data-i18n="c_pe">估值 PE分位</span> <b>34%（52周）</b></span>',
  '<span data-i18n="c_pe">估值 PE分位</span> <b>87%（10Y）</b></span>'),
 ('<span data-i18n="c_turn">两市成交</span> <b>¥1.97万亿</b></span>',
  '<span data-i18n="c_turn">两市成交</span> <b>¥2.10万亿</b></span>'),
]
miss = 0
for old, new in BODY:
    if old in html:
        html = html.replace(old, new, 1)
    else:
        miss += 1
        print("[skip-body] 未命中: %r" % old[:70])
print("[body] patch 完成，未命中 %d 处" % miss)

old_radar = '<text x="160" y="71">64</text><text x="237" y="120">68</text><text x="209" y="194">50</text>\n            <text x="160" y="167">90</text><text x="109" y="201">42</text><text x="55" y="118">85</text>'
new_radar = '<text x="160" y="71">70</text><text x="237" y="120">67</text><text x="209" y="194">55</text>\n            <text x="160" y="167">51</text><text x="109" y="201">67</text><text x="55" y="118">89</text>'
if old_radar in html:
    html = html.replace(old_radar, new_radar, 1)
else:
    print("[skip] radar 块未命中")

_pat = re.compile(r'<(\w+)([^>]*\bdata-i18n="([^"]+)"[^>]*)>(.*?)</\1>', re.S)


def _repl(m):
    _tag, _attrs, _key, _inner = m.group(1), m.group(2), m.group(3), m.group(4)
    if _key in zh:
        return "<%s%s>%s</%s>" % (_tag, _attrs, zh[_key], _tag)
    return m.group(0)


html = _pat.sub(_repl, html)

open(OUT, "w", encoding="utf-8").write(html)
print("[ok] 写出 %s (%d bytes)" % (OUT, len(html)))

leftover = ["12%</text>", "88%</text>", "643", "4870", "地面兵装Ⅱ", "工业金属 −5.04%",
            "瑞尔特", "¥1.97万亿", "3888.11", "13471.26", "3322.04", "09-11 · 收盘",
            "放量普跌 · 恐慌扩散", "Next-Session Outlook (09-14", "鼎信通讯"]
bad = [s for s in leftover if s in html]
print("[校验] 残留旧数据:", bad if bad else "无")
