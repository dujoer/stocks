# -*- coding: utf-8 -*-
"""群体心理风险雷达 2026-09-10：以 09-09 页面为模板，覆盖全部动态内容。

数据来源（全部为 2026-09-10 真实收盘；两融接口返回空，已如实标注未编造）：
  data_market_overview(type=all) / data_sector(行业快照) / tool_ranking(limitup_days)
  估值 PE_TTM 20.44 为 09-09 口径（中证全指估值滞后发布）
"""
import os, re, shutil

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "..", "web", "psychology", "crowd-psychology-risk-radar-20260909.html")
OUT = os.path.join(HERE, "..", "web", "psychology", "crowd-psychology-risk-radar-20260910.html")

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
# 1) 09-10 叙述覆盖（中文）—— 所有键均覆盖，避免残留 09-09 文案
# ============================================================
ZH = {
 "t_headline_sub": "2026-09-10 · 收盘",
 "t_breadth": "市场涨跌分布（2026-09-10 收盘）",
 "hk_stage": "阶段定性", "hv_stage": "<b>缩量普跌 · 退潮加速</b>（09-10）",
 "hk_upratio": "涨股比", "hv_upratio": "<b>17%</b>（前次 09-09 32% · ↓ 15pct，广度腰斩）",
 "hk_lim": "涨停 / 跌停", "hv_lim": "<b>38</b> / <b>2</b>（涨停小幅回落、跌停重现 2 只）",
 "hk_amt": "成交额", "hv_amt": "<b>¥1.65万亿</b>（继续缩量，为 10 日均 85.5%、20 日均 81.5%）",
 "hk_cycle": "情绪周期", "hv_cycle": "<b>缩量普跌 · 退潮加速</b>",
 "hk_risk": "风险等级", "hv_risk": "<b class=\"hl-risk\">中</b>（退潮加深，维持中但逼近上沿）",
 "hk_flag": "关键提示",
 "hv_flag": "涨股比 32%→<b>17%</b>、涨停 42→<b>38</b>、跌停 0→<b>2</b>，下跌家数达 81.1%；三大指数全部收跌（上证 −0.43% / 深成 −0.77% / 创业板 −0.49%），成交继续萎缩至 ¥1.65万亿（10 日均 85.5%）——<b>指数抗跌（银行/电力护盘）+ 个股普跌</b>的背离加剧；板块宽度\"全面下跌\"（上涨板块<20%），仅航海装备Ⅱ +2.76%、城商行Ⅱ +2.39% 等防御/权重方向收红；两融数据暂缺，未编造。",
 "tk1": "阶段定性", "tv1": "A股 09-10 由 09-09「缩量分化 / 短线退潮」恶化至「<b>缩量普跌 · 退潮加速</b>」：涨股比腰斩至 <b>17%</b>（955涨 / 4512跌 / 平94，由 32% 回落 −15pct），涨停 <b>38</b>（42→38）、跌停 <b>2</b>（由 0 重现），下跌家数占比 81.1%；上证 <b>−0.43%</b>（3934.40）失守 MA20（3936.76），深成 <b>−0.77%</b>（13617.67）、创业板 <b>−0.49%</b>（3338.42）同步收跌——<b>指数与个股同向下跌，但指数跌幅远小于个股中位数</b>，权重（银行/电力）护盘掩盖了个股赚钱效应塌陷。成交 ¥1.65万亿（10 日均 85.5%）继续萎缩。风险等级维持<b>中</b>但已逼近上沿。",
 "tk2": "广度崩塌", "tv2": "涨股比 <b>17%</b>（前次 32% ↓15pct）· 涨停 <b>38</b>（42→38）· 跌停 <b>2</b>（由 0 重现）· 成交 <b>¥1.65万亿</b>（10 日均 85.5%、20 日均 81.5%，继续缩量）——赚钱效应与参与度同步塌陷，板块宽度\"全面下跌\"（124 个行业中仅约 2 成收红），<b>阴跌式退潮而非恐慌踩踏</b>（跌停仅 2 只、涨停仍有 38 只）。",
 "tk3": "指数抗跌·个股普跌", "tv3": "上证 <b>−0.43%</b>（3934.40）失守 MA20（3936.76）与 BOLL 中轨（3936.76），收在 MA60（3945.09）下方；深成 <b>−0.77%</b>（13617.67）、创业板 <b>−0.49%</b>（3338.42）同步收跌——但指数跌幅远小于个股中位数（跌 81.1%），权重（银行/电力）护盘致\"指数抗跌、个股普跌\"背离加剧；MACD 0.0782（DIF 6.36 / DEA 6.32，缠绕）、RSI_12 50.20、KDJ_K 40.63，技术面弱势震荡。",
 "tk4": "板块结构", "tv4": "<b>航海装备Ⅱ +2.76%</b>（换手 5.72%，主力净流入 +4.64亿）领涨，<b>城商行Ⅱ +2.39%</b> / <b>玻璃玻纤 +2.23%</b> 跟随——<b>主线切换至防御/权重与局部题材，TMT 与前期资源全面退潮</b>；<b>种植业 −5.09%</b>（换手 11.15%）领跌，<b>渔业 −4.69%</b> / <b>农产品加工 −4.65%</b> 跟随——农业链集体重挫，与 09-09 领涨的橡胶/航运/资源形成剧烈反转。",
 "tk5": "连板结构", "tv5": "连板共 <b>40 只</b>，最高板降至 <b>4 板</b>（桂林旅游，由 5 板降级）；题材由 09-09 的消费/资源接力切换至旅游（桂林旅游 4板）等局部热点——<b>高度下降、轮动加快、赚钱效应收缩</b>，属退潮期典型特征。",
 "tk6": "资金：两融暂缺", "tv6": "两融数据接口当日返回空（数据缺失），<b>未编造</b>；从可见信号看，板块资金集中于航海装备Ⅱ（主力净流入 +4.64亿）与城商行Ⅱ等防御/权重方向，前期光模块/PCB 主力5日净流入虽仍居前但个股已退潮——<b>资金从高弹性成长切向低估值防御，避险特征明显</b>。",
 "tk7": "估值 / 风格", "tv7": "PE_TTM <b>20.44</b>（10年分位 <b>79.88%</b>、5年分位 <b>79.76%</b>，仍偏高，口径 09-09）＋ 估值未随指数回落而消化；风格上防御（银行/电力/航海）占优，成长（创业板 −0.49%）持续转弱——<b>高位估值 + 弱势指数</b>，风险预算应显著收缩。",
 "tk8": "情绪周期", "tv8": "由 09-09「缩量分化 / 短线退潮」恶化至「<b>缩量普跌 · 退潮加速</b>」：涨股比 32%→17%、涨停 42→38、跌停 0→2，下跌家数达 81.1%，三大指数全部收跌、成交继续萎缩至 ¥1.65万亿（10 日均 85.5%）；板块宽度\"全面下跌\"、仅防御/权重收红——<b>阴跌式退潮确认，指数抗跌掩盖个股普跌，风险等级维持中但逼近上沿</b>。",
 "t_tldr_text": "A股 09-10 呈现「缩量普跌 · 退潮加速」：涨股比 32%→17%（955涨/4512跌/平94），涨停 42→38、跌停 0→2，下跌家数占比 81.1%；上证 −0.43%（3934.40）失守 MA20（3936.76），深成 −0.77%（13617.67）、创业板 −0.49%（3338.42）同步收跌，但指数跌幅远小于个股中位数，权重（银行/电力）护盘致\"指数抗跌、个股普跌\"背离加剧；成交 ¥1.65万亿（10 日均 85.5%、20 日均 81.5%）继续萎缩。航海装备Ⅱ +2.76%（换手 5.72%、主力净流入 +4.64亿）领涨，城商行Ⅱ +2.39% / 玻璃玻纤 +2.23% 跟随，主线切向防御/权重；种植业 −5.09%（换手 11.15%）领跌，渔业 −4.69% / 农产品加工 −4.65% 跟随，农业链集体重挫，与 09-09 领涨的橡胶/航运/资源剧烈反转。连板 40 只、最高板 4 板（桂林旅游）。两融数据暂缺（未编造）。估值 PE_TTM 20.44（10年分位 79.88%、5年分位 79.76%）仍偏高——阴跌式退潮确认，风险等级中但逼近上沿。",
 "t_risk": "风险等级", "t_risk_hi": "中",
 "c_upratio": "涨股比", "c_limitup": "涨停", "c_board": "连板高度", "c_pe": "估值 PE分位", "c_pmi": "制造业PMI", "c_turn": "两市成交",
 "t_sec_bias": "行为偏差热力图", "t_cycle": "情绪周期定位（六阶段）",
 "r1": "绝望", "r2": "怀疑", "r3": "乐观", "r4": "狂热", "r5": "焦虑", "r6": "自满",
 "t_cycle_note": "注：上方「中性偏冷」为实时群体心理定位（缩量普跌 · 退潮加速）——09-10 涨跌分布（涨股比 17%、涨停 38、跌停 2、成交 ¥1.65万亿）显示广度崩塌、赚钱效应塌陷、指数抗跌（银行/电力护盘）与个股普跌背离加剧；成交继续缩量（10 日均 85.5%），两融数据暂缺，估值分位 79.88% 仍高。若 09-11 涨股比回升至 30% 上方且成交回到 ¥1.8万亿，退潮缓和；若跌停扩大至 10 只以上或上证跌破 MA60（3945.09），则退潮进一步加速。",
 "t_leg": "严重度（由数据综合映射）", "t_bias_note": "注：偏差严重度为基于下方真实数据的模型映射（1=低，5=高），用于呈现群体心理的脆弱点分布，并非对个股的买卖建议。",
 "t_sec_radar": "风险雷达",
 "t_radar_note": "六维风险读数（0–100，由下方真实数据综合映射，越高代表该维度群体脆弱性越强）：拥挤度 62 / 融资 66 / 换手 44 / 广度 82 / 媒体 46 / 估值 87。广度由 62 升至 82（09-10 涨股比骤降至 17%、下跌家数达 81.1%、板块宽度\"全面下跌\"仅约 2 成行业收红，广度风险骤升）；换手由 50 降至 44（成交 ¥1.65万亿，仅 10 日均 85.5%、20 日均 81.5%，量能继续萎缩）；融资由 64 升至 66（两融数据暂缺、无法确认杠杆，但指数退潮 + 高估值下杠杆踩踏风险边际上升，谨慎上调）；拥挤度由 60 升至 62（主线收敛至防御/权重与局部题材，资金抱团避险，集中度上升）；媒体由 52 降至 46（涨停 38、最高板 4 板、三大指数全跌，情绪温度继续回落）；估值 87 持平（PE_TTM 20.44、10年分位 79.88%，口径 09-09）。整体脆弱性由「广度 + 估值」双高主导——阴跌式退潮，广度崩塌成为最主要风险源。",
 "ax_crowd": "拥挤度", "ax_margin": "融资", "ax_turn": "换手", "ax_breadth": "广度", "ax_media": "媒体情绪", "ax_val": "估值",
 "t_breadth": "市场涨跌分布（2026-09-10 收盘）",
 "b_up": "上涨", "b_down": "下跌", "b_flat": "平盘", "b_limitup": "涨停", "b_limitdn": "跌停", "b_amt": "成交额",
 "t_breadth_note": "涨股比由 32% 骤降至 17%、涨停 42→38、跌停 0→2，下跌家数占比 81.1%；成交 ¥1.65万亿（10 日均 85.5%、20 日均 81.5%）继续缩量。指数与个股同向下跌但背离明显：上证 −0.43%（3934.40 失守 MA20 3936.76）/ 深成 −0.77%（13617.67）/ 创业板 −0.49%（3338.42），指数跌幅远小于个股中位数，权重（银行/电力）护盘掩盖个股赚钱效应塌陷；航海装备Ⅱ +2.76% 领涨，种植业 −5.09% 领跌——板块宽度\"全面下跌\"，仅防御/权重收红。",
 "t_sec_evidence": "关键证据表",
 "th_metric": "指标", "th_read": "真实读数", "th_interp": "行为金融解读",
 "ev_market": "一、市场广度与总览",
 "ev_upratio": "涨股比",
 "ev_upratio_i": "由 32% 降至 17%（−15pct），涨 955 / 跌 4512 / 平 94，参与度崩塌，个股普跌（下跌 81.1%），阴跌式退潮（跌停仅 2 只、非恐慌踩踏）",
 "ev_limit": "涨停 / 跌停",
 "ev_limit_i": "涨停 38（42→38 小幅回落）、跌停 2（由 0 重现），连板高度降至 4板（桂林旅游）——投机热度继续降温，赚钱效应收缩",
 "ev_amount": "两市成交额",
 "ev_amount_i": "量能 ¥1.65万亿（10 日均 85.5%、20 日均 81.5%，继续缩量）——退潮由存量资金收缩与主线缺失驱动，量价同步走弱",
 "ev_index": "二、核心指数表现（2026-09-10 收盘）",
 "ev_sh": "上证指数",
 "ev_sh_i": "−0.43%（3934.40），失守 MA20（3936.76）与 BOLL 中轨（3936.76），收在 MA60（3945.09）下方；MACD 0.0782（DIF 6.36 / DEA 6.32，缠绕）、RSI_12 50.20、KDJ_K 40.63，技术面弱势震荡；PE_TTM 20.44（10年分位 79.88% 偏高，口径 09-09）",
 "ev_sz": "深证成指",
 "ev_sz_i": "深成 −0.77%（13617.67），跟随市场下行，中期弱势延续",
 "ev_cyb": "创业板指",
 "ev_cyb_i": "创业板 −0.49%（3338.42）收跌，成长风格持续转弱",
 "ev_sector": "三、板块排行与主线",
 "ev_secup": "领涨行业",
 "ev_secup_i": "航海装备Ⅱ +2.76%（换手 5.72%、主力净流入 +4.64亿）领涨，城商行Ⅱ +2.39% / 玻璃玻纤 +2.23% 跟随——主线切换至防御/权重与局部题材，TMT 与前期资源全面退潮，全市场约 2 成行业收红",
 "ev_secdn": "领跌行业",
 "ev_secdn_i": "种植业 −5.09%（换手 11.15%）领跌 / 渔业 −4.69% / 农产品加工 −4.65%——农业链集体重挫，与 09-09 领涨的橡胶/航运/资源形成剧烈反转",
 "ev_board": "极端题材",
 "ev_board_i": "连板共 40 只，最高板 4板（桂林旅游，由 5 板降级）；题材由消费/资源切换至旅游（桂林旅游 4板）等局部热点，轮动加快、高度下降",
 "ev_flow": "四、资金：连板 / 主力 / 两融",
 "ev_height": "连板高度",
 "ev_height_i": "高度 4板（桂林旅游，2026-09-10 收盘），由 5 板降级；题材以旅游接力，基本面以区域旅游为主，无显著题材泡沫",
 "ev_main": "主力5日净流入TOP",
 "ev_main_i": "主力5日净流入仍集中于光模块 / PCB（中际旭创 +76.9亿 居首、新易盛 +41.0亿、东山精密 +31.3亿），但 09-10 当日板块资金已切向航海装备Ⅱ（主力净流入 +4.64亿）与城商行Ⅱ等防御/权重——资金从高弹性成长转向低估值避险，光模块个股已退潮；两融数据暂缺，未编造。",
 "ev_margin": "融资单日变动TOP",
 "ev_margin_i": "两融数据接口当日返回空（数据缺失），融资单日变动与两融余额均暂缺，<b>未编造</b>；从可见信号看资金切向防御/权重（航海装备Ⅱ +4.64亿、城商行Ⅱ），杠杆风险因缺失无法确认，谨慎对待。",
 "ev_hot": "热搜 / 领涨TOP",
 "ev_hot_i": "热点由防御/局部题材主导：桂林旅游 4板（旅游）/ 航海装备Ⅱ +2.76%（主力净流入 +4.64亿）/ 城商行Ⅱ +2.39% / 玻璃玻纤 +2.23%；data_hot 板块榜以航海装备、银行、电力居前，与护盘资金方向一致",
 "ev_margintotal": "市场两融余额",
 "ev_margintotal_i": "缺口：聚合两融余额（data_market_overview type=margin）与融资单日变动接口当日均返回空，已如实标注、未编造；涨跌分布 / 指数 / 成交额 / 板块 / 连板梯队均为 2026-09-10 真实收盘，主力5日净流入为 09-09 口径（当日暂缺）",
 "ev_macro": "五、核心宏观指标",
 "ev_pmi": "制造业PMI（7月）",
 "ev_pmi_i": "基本面收缩，与「高估值 + 中期弱势」明显背离；非制造业新订单偏弱",
 "ev_capu": "产能利用率（Q2）",
 "ev_capu_i": "实物经济动能走弱，价格缺乏业绩支撑",
 "ev_cpi": "CPI（7月）",
 "ev_cpi_i": "低通胀、需求偏弱，难证景气全面复苏",
 "ev_social": "社融（7月）",
 "ev_social_i": "信用需求弱，资金绕道股市 = 流动性驱动特征",
 "ev_m1m2": "M1-M2 剪刀差",
 "ev_m1m2_i": "活钱偏弱，资金空转，典型后周期现象",
 "ev_yield": "10Y 国债收益率",
 "ev_yield_i": "极低无风险利率，既支撑估值也反映增长担忧",
 "ev_lpr": "LPR",
 "ev_lpr_i": "宽松基调未变",
 "t_ev_note": "数据口径：宏观指标多截至 2026-07（月频）或 2026-09-09（日频）；涨跌分布 / 指数 / 成交额 / 板块 / 连板梯队均为 2026-09-10 真实收盘。估值 PE_TTM 20.44 为 2026-09-09 口径（中证全指估值滞后发布），已在正文标注；两融数据当日缺失，已如实标注未编造。详见末尾「数据来源与日期口径」。",
 "t_sec_risk": "风险分层",
 "rc1_tag": "红线区 · 高估值 + 阴跌退潮（杠杆数据暂缺）",
 "rc1_t": "高估值 + 退潮加速（杠杆暂缺）",
 "rc1_d": "PE_TTM 20.44、10年分位 79.88% 仍偏高，叠加 09-10 阴跌式退潮（涨股比 17%、下跌 81.1%、三大指数全跌）；两融数据暂缺无法确认杠杆，但高估值 + 弱势指数下，前期光模块/PCB 等高位主线一旦证伪回撤幅度大——风险预算应显著收缩。",
 "rc1_rep": "代表：高位光模块（中际旭创 / 新易盛）/ PCB（东山精密）/ 农业链高位题材（种植业 −5.09% 领跌）",
 "rc1_cond": "条件框架：高位主线不追涨、不加杠杆；以量能持续 + 指数站回短期均线上方为右侧确认，破位即减，杠杆仓位优先降。",
 "rc2_tag": "黄线区 · 指数抗跌掩盖个股普跌（背离）",
 "rc2_t": "指数抗跌 / 个股普跌",
 "rc2_d": "上证 −0.43%（3934.40 失守 MA20）、深成 −0.77%、创业板 −0.49% 同步收跌，但指数跌幅远小于个股中位数（下跌 81.1%），权重（银行/电力/航海装备）护盘致\"指数抗跌、个股普跌\"背离加剧；成交继续缩量至 ¥1.65万亿（10 日均 85.5%），存量资金收缩。",
 "rc2_rep": "代表：上证权重（护盘）/ 创业板（−0.49%）/ 中小票（普跌 81.1%）",
 "rc2_cond": "条件框架：不追日内领涨题材；新主线需量价持续确认，严禁把单日轮动当反转，警惕「狂热」标签下高位放量追涨。",
 "rc3_tag": "绿线区 · 农业链与前期题材集体重挫",
 "rc3_t": "农业链 / 前期题材退潮",
 "rc3_d": "种植业 −5.09%（换手 11.15%）领跌、渔业 −4.69% / 农产品加工 −4.65% 跟随，农业链集体重挫，与 09-09 领涨的橡胶/航运/资源形成剧烈反转；前期 TMT/传媒方向延续退潮——题材轮动至防御，风险偏好收缩。",
 "rc3_rep": "代表：种植业（换手 11.15%）/ 渔业 / 农产品加工 / 前期高位题材",
 "rc3_cond": "条件框架：仅作避险对冲与仓位保护；整体风险预算应显著收缩，等待量价确认信号。",
 "t_sec_outlook": "下个交易日（09-11 周五）展望",
 "o_logic": "研判逻辑（基于 09-10 收盘 + 群体心理定位）",
 "o_logic_text": "由 09-10 的「缩量普跌 · 退潮加速」延伸：情绪周期定位「缩量普跌 · 退潮加速」，涨股比 17%、涨停 38、跌停 2、三大指数全跌、成交继续萎缩至 ¥1.65万亿（10 日均 85.5%），板块宽度\"全面下跌\"仅约 2 成行业收红；指数抗跌（银行/电力护盘）与个股普跌背离加剧，估值分位 79.88% 仍高、两融数据暂缺。基于此推演 09-11 的板块方向与交易规则（<b>不涉及具体个股推荐</b>）。",
 "o1_tag": "防御/权重（观察）",
 "o1_t": "航海装备Ⅱ / 城商行Ⅱ / 电力 / 玻璃玻纤",
 "o1_d": "09-10 航海装备Ⅱ +2.76%（主力净流入 +4.64亿）、城商行Ⅱ +2.39%、玻璃玻纤 +2.23% 收红，资金切向防御/权重与局部题材；但退潮期不宜追高，仅作避险观察。",
 "o1_cond": "注意：防御方向多为护盘与避险驱动，持续性待验证；若成交继续缩量，轮动加快、操作难度上升，不追后排、只做前排核心。",
 "o2_tag": "前期高位题材（回避）",
 "o2_t": "光模块 / PCB / 农业链高位 / TMT",
 "o2_d": "前期光模块/PCB 主力5日仍集中但个股已退潮；农业链（种植业 −5.09%、渔业 −4.69%）与橡胶/航运/资源出现剧烈反转——高位题材在退潮期被抛售，短期承压。",
 "o2_cond": "注意：属题材退潮而非基本面恶化，不盲目杀跌；但退潮期回避高位题材，等待缩量止跌信号。",
 "o3_tag": "等待信号（观望）",
 "o3_t": "量能回升 / 涨股比修复",
 "o3_d": "09-10 涨股比仅 17%、成交 ¥1.65万亿（10 日均 85.5%），退潮加速；需观察 09-11 是否出现涨股比回升至 30% 上方、成交回到 ¥1.8万亿的缓和信号。",
 "o3_cond": "注意：退潮期不预判底部，等量价确认右侧；若跌停扩大至 10 只以上或上证跌破 MA60（3945.09），降仓至 ≤3 成。",
 "o_rules_t": "交易规则（09-11）",
 "o_r1": "<b>仓位</b>：中性偏谨慎（3–4 成），不加杠杆。情绪由「缩量分化 / 短线退潮」恶化至「缩量普跌 · 退潮加速」，风险等级维持中但逼近上沿，退潮期控制仓位、不追高。",
 "o_r2": "<b>量价确认</b>：涨股比回升至 30% 上方且成交回到 ¥1.8万亿，方视为退潮缓和；若成交继续缩量至 ¥1.6万亿以下或跌停扩大至 10 只以上，降仓至 ≤3 成。",
 "o_r3": "<b>主线参与</b>：防御/权重方向（航海装备/城商行/电力）仅作避险观察，不追后排；前期高位题材（光模块/PCB/农业链）退潮期回避。",
 "o_r4": "<b>回避清单</b>：前期高位题材（光模块/PCB/农业链/橡胶航运）、退潮期高位连板接力（桂林旅游 4板谨慎）、杠杆集中且已退潮的方向。",
 "o_r5": "<b>风控</b>：若 09-11 跌停扩大至 10 只以上或上证跌破 MA60（3945.09），视为退潮加速，立即降仓；两融数据恢复前不加重杠杆。",
 "o_compliance": "<b>合规说明：</b>本展望仅给出板块方向与交易规则，不涉及具体个股推荐；群体心理定位与板块推断基于 2026-09-10 真实行情数据，市场有风险，决策须独立。",
 "t_sec_source": "数据来源与日期口径",
 "s_breadth": "涨跌分布 / 总览",
 "s_breadth_v": "westock · data_market_overview(market_statis_updown)；2026-09-10 收盘",
 "s_portrait": "市场画像 summary",
 "s_portrait_v": "westock · data_market_overview(type=summary)；2026-09-10（涨股比 17% 广度崩塌，缩量普跌）",
 "s_index": "指数表现",
 "s_index_v": "westock · data_market_overview(market_statis_daily_trade)；2026-09-10 收盘",
 "s_sector": "板块排行 / 资金流",
 "s_sector_v": "westock · data_sector(mode=ranking, kind=industry/concept)；2026-09-10",
 "s_hot": "热搜股票",
 "s_hot_v": "westock · data_hot(kind=board)；2026-09-10（航海装备 / 银行 / 电力 居前）",
 "s_macro": "核心宏观",
 "s_macro_v": "westock · data_macro(cn_pmi, cn_capacity_utilization, cn_financing 等)；PMI/产能/社融为 08-21 复核（无新发布，月频），CPI/M1-M2/10Y/LPR 沿用前期值",
 "s_margin": "两融（个股）",
 "s_margin_v": "westock · 两融接口当日返回空（数据暂缺，未编造）",
 "s_main": "主力5日净流入",
 "s_main_v": "westock · tool_ranking(metric=cap_main_5d)；2026-09-09 口径（当日暂缺）",
 "s_board": "连板高度",
 "s_board_v": "westock · tool_ranking(metric=limitup_days)；2026-09-10（共 40 只，最高板 4板）",
 "s_gap": "数据缺口",
 "s_gap_v": "市场两融余额与融资单日变动接口当日均返回空，已如实标注、未编造；估值 PE_TTM 20.44 为 2026-09-09 口径（中证全指估值滞后发布），已标注；主力5日净流入为 09-09 口径。",
 "t_src_note": "时间口径：所有时点按北京时间。宏观为月频 / 季频，与日频行情不可直接对齐，已分别标注。涨跌分布 / 指数 / 板块 / 连板梯队均为 2026-09-10 当日真实数据；估值 / 主力5日为 2026-09-09 口径、两融当日缺失，均已标注。",
 "disc1": "免责声明：以上内容基于公开数据和量化分析，仅供参考，不构成投资建议。市场有风险，投资需谨慎。任何投资决策应结合个人风险承受能力、资金状况和投资目标独立判断，必要时咨询持牌专业机构。过往表现不预示未来收益。",
 "disc2": "本研判为「群体心理 / 条件框架」分析，非买卖指令；风险读数与偏差严重度为模型综合映射，须与价格结构、估值、资金流向交叉验证，不可单独作为交易依据。",
 "t_foot": "群体心理风险雷达 · 由 westock 官方行情数据生成 · 仅供研究参考",
}

EN = {
 "t_headline_sub": "2026-09-10 · Close",
 "t_breadth": "Market breadth (2026-09-10 close)",
 "hk_stage": "Stage", "hv_stage": "<b>Volume-shrinking broad sell-off / Ebb accelerates</b> (09-10)",
 "hk_upratio": "Up-ratio", "hv_upratio": "<b>17%</b> (prev 09-09 32% · ↓ 15pct, breadth halves)",
 "hk_lim": "Limit-up / -down", "hv_lim": "<b>38</b> / <b>2</b> (limit-up eases, limit-down returns to 2)",
 "hk_amt": "Turnover", "hv_amt": "<b>¥1.65tn</b> (still shrinking, 85.5% of 10d avg, 81.5% of 20d avg)",
 "hk_cycle": "Sentiment cycle", "hv_cycle": "<b>Volume-shrinking broad sell-off / Ebb accelerates</b>",
 "hk_risk": "Risk level", "hv_risk": "<b class=\"hl-risk\">Medium</b> (ebb deepens, holds Medium but near upper edge)",
 "hk_flag": "Key flag",
 "hv_flag": "Up-ratio 32%→<b>17%</b>, limit-up 42→<b>38</b>, limit-down 0→<b>2</b>, down-stocks hit 81.1%; all three indices close lower (SSE −0.43% / SZ −0.77% / ChiNext −0.49%), turnover keeps shrinking to ¥1.65tn (85.5% of 10d avg) — the <b>divergence of 'index resilient (banks / power propping) + stocks broadly down' widens</b>; sector breadth is 'broad decline' (fewer than 20% of sectors up), only defensive / weight names like Marine EquipmentⅡ +2.76% and City Commercial BanksⅡ +2.39% close green; margin data is missing, not fabricated.",
 "tk1": "Stage", "tv1": "A-shares 09-10 worsen from 09-09's 'volume-shrinking divergence / short-term ebb' into '<b>volume-shrinking broad sell-off / ebb accelerates</b>': up-ratio halves to <b>17%</b> (955 up / 4512 down / 124 flat, −15pct from 32%), limit-up <b>38</b> (42→38), limit-down <b>2</b> (returns from 0), down-stocks 81.1%; SSE <b>−0.43%</b> (3934.40) loses MA20 (3936.76), SZ <b>−0.77%</b> (13617.67) and ChiNext <b>−0.49%</b> (3338.42) also close lower — <b>indices and stocks fall together, yet the index drop is far smaller than the median stock</b>, weights (banks / power) propping the index hide the collapse in stock profit effect. Turnover ¥1.65tn (85.5% of 10d avg) keeps shrinking. Risk stays <b>Medium</b> but nears the upper edge.",
 "tk2": "Breadth collapses", "tv2": "Up-ratio <b>17%</b> (prev 32%, ↓15pct) · limit-up <b>38</b> (42→38) · limit-down <b>2</b> (returns from 0) · turnover <b>¥1.65tn</b> (85.5% of 10d avg, 81.5% of 20d avg, still shrinking) — profit effect and participation collapse together; sector breadth is 'broad decline' (only ~20% of 124 sectors close up); this is a <b>grinding-ebb, not a panic crash</b> (limit-down only 2, limit-up still 38).",
 "tk3": "Index resilient / stocks down", "tv3": "SSE <b>−0.43%</b> (3934.40) loses MA20 (3936.76) and the BOLL mid-band (3936.76), closing below MA60 (3945.09); SZ <b>−0.77%</b> (13617.67) and ChiNext <b>−0.49%</b> (3338.42) also close lower — yet the index drop is far smaller than the median stock (down 81.1%); weights (banks / power) prop the index, widening the 'index resilient, stocks down' divergence; MACD 0.0782 (DIF 6.36 / DEA 6.32, coiled), RSI_12 50.20, KDJ_K 40.63 — technically weak and range-bound.",
 "tk4": "Sector structure", "tv4": "<b>Marine EquipmentⅡ +2.76%</b> (turnover 5.72%, main net inflow +¥464mn) leads, <b>City Commercial BanksⅡ +2.39%</b> / <b>Glass-Fiber +2.23%</b> follow — <b>the main line rotates to defensives / weights and local themes; TMT and prior resources retreat across the board</b>; <b>Farming −5.09%</b> (turnover 11.15%) leads losers, <b>Fisheries −4.69%</b> / <b>Farm-Product Processing −4.65%</b> follow — the agriculture chain collapses sharply, a violent reversal versus 09-09's leading rubber / shipping / resources.",
 "tk5": "Limit-up ladder", "tv5": "Ladder totals <b>40 names</b>, top board falls to <b>4 boards</b> (Guilin Tourism, down from 5); themes rotate from 09-09's consumer / resource relay to local hotspots like tourism (Guilin Tourism 4 boards) — <b>lower height, faster rotation, shrinking profit effect</b>, typical of an ebb phase.",
 "tk6": "Capital: margin missing", "tv6": "The margin data interface returns empty that day (data missing), <b>not fabricated</b>; from visible signals, sector capital concentrates in Marine EquipmentⅡ (main net inflow +¥464mn) and defensives / weights like City Commercial BanksⅡ, while the prior optical-module / PCB main-5d net inflows still lead but their stocks have ebbed — <b>capital rotates from high-beta growth to low-valuation defensives, clearly risk-off</b>.",
 "tk7": "Valuation / style", "tv7": "PE_TTM <b>20.44</b> (10y pctile <b>79.88%</b>, 5y pctile <b>79.76%</b>, still rich, as of 09-09) + valuation has not digested the index pullback; style favours defensives (banks / power / marine), growth (ChiNext −0.49%) keeps weakening — <b>high valuation + weak index</b>, risk budget should shrink markedly.",
 "tk8": "Sentiment cycle", "tv8": "From 09-09's 'volume-shrinking divergence / short-term ebb' into '<b>volume-shrinking broad sell-off / ebb accelerates</b>': up-ratio 32%→17%, limit-up 42→38, limit-down 0→2, down-stocks 81.1%, all three indices lower, turnover shrinks to ¥1.65tn (85.5% of 10d avg); sector breadth is 'broad decline', only defensives / weights close green — <b>grinding-ebb confirmed, index resilience masks broad stock declines; risk holds Medium but nears the upper edge</b>.",
 "t_tldr_text": "A-shares 09-10 = 'volume-shrinking broad sell-off / ebb accelerates': up-ratio 32%→17% (955 up / 4512 down / 124 flat), limit-up 42→38, limit-down 0→2, down-stocks 81.1%; SSE −0.43% (3934.40) loses MA20 (3936.76), SZ −0.77% (13617.67), ChiNext −0.49% (3338.42) all close lower, yet the index drop is far smaller than the median stock, and weights (banks / power) prop the index, widening the 'index resilient, stocks down' divergence; turnover ¥1.65tn (85.5% of 10d avg, 81.5% of 20d avg) keeps shrinking. Marine EquipmentⅡ +2.76% (turnover 5.72%, main net inflow +¥464mn) leads, City Commercial BanksⅡ +2.39% / Glass-Fiber +2.23% follow as the main line rotates to defensives / weights; Farming −5.09% (turnover 11.15%) leads losers, Fisheries −4.69% / Farm-Product Processing −4.65% follow, the agriculture chain collapses sharply versus 09-09's leading rubber / shipping / resources. Ladder 40 names, top board 4 (Guilin Tourism). Margin data missing (not fabricated). Valuation PE_TTM 20.44 (10y pctile 79.88%, 5y 79.76%) still rich — grinding-ebb confirmed, risk Medium but near upper edge.",
 "t_risk": "Risk level", "t_risk_hi": "Medium",
 "c_upratio": "Up-ratio", "c_limitup": "Limit-up", "c_board": "Ladder height", "c_pe": "PE pctile", "c_pmi": "Mfg PMI", "c_turn": "Turnover",
 "t_sec_bias": "Behavioral Bias Heatmap", "t_cycle": "Sentiment Cycle (6-stage)",
 "r1": "Despair", "r2": "Doubt", "r3": "Optimism", "r4": "Euphoria", "r5": "Anxiety", "r6": "Complacency",
 "t_cycle_note": "Note: the 'neutral-to-cool' tag above is the live crowd-psychology position (volume-shrinking broad sell-off / ebb accelerates) — 09-10 breadth (up-ratio 17%, limit-up 38, limit-down 2, turnover ¥1.65tn) shows breadth collapse and profit-effect breakdown, with index resilience (banks / power propping) versus broad stock declines diverging sharply; turnover keeps shrinking (85.5% of 10d avg), margin data missing, valuation pctile 79.88% still high. If 09-11 holds up-ratio above 30% and turnover returns to ¥1.8tn, the ebb eases; if limit-down widens past 10 or the SSE breaks MA60 (3945.09), the ebb accelerates further.",
 "t_leg": "Severity (model-mapped)", "t_bias_note": "Note: bias severity is a model mapping from the real data below (1=low, 5=high), used to show where crowd psychology is fragile — not a buy/sell recommendation for any stock.",
 "t_sec_radar": "Risk Radar",
 "t_radar_note": "Six-dimension risk readings (0–100, mapped from the real data below; higher = greater crowd fragility on that axis): crowding 62 / margin 66 / turnover 44 / breadth 82 / media 46 / valuation 87. Breadth 62→82 (09-10 up-ratio plunges to 17%, down-stocks 81.1%, sector breadth 'broad decline' with only ~20% sectors up — breadth risk spikes); turnover 50→44 (¥1.65tn, only 85.5% of 10d avg, 81.5% of 20d avg, volume keeps shrinking); margin 64→66 (margin data missing, leverage unconfirmed, but index ebb + high valuation raise marginal margin-crash risk, nudged up cautiously); crowding 60→62 (the main line narrows to defensives / weights and local themes, capital huddles into safety, concentration rises); media 52→46 (limit-up 38, top board 4, all three indices down — sentiment temperature keeps cooling); valuation 87 flat (PE_TTM 20.44, 10y pctile 79.88%, as of 09-09). Fragility is now led by 'breadth + valuation' — a grinding ebb with breadth collapse as the dominant risk source.",
 "ax_crowd": "Crowding", "ax_margin": "Margin", "ax_turn": "Turnover", "ax_breadth": "Breadth", "ax_media": "Media mood", "ax_val": "Valuation",
 "t_breadth": "Market breadth (2026-09-10 close)",
 "b_up": "Up", "b_down": "Down", "b_flat": "Flat", "b_limitup": "Limit-up", "b_limitdn": "Limit-down", "b_amt": "Turnover",
 "t_breadth_note": "Up-ratio plunges 32%→17%, limit-up 42→38, limit-down 0→2, down-stocks 81.1%; turnover ¥1.65tn (85.5% of 10d avg, 81.5% of 20d avg) keeps shrinking. Indices and stocks fall together but diverge visibly: SSE −0.43% (3934.40 loses MA20 3936.76) / SZ −0.77% (13617.67) / ChiNext −0.49% (3338.42) — the index drop is far smaller than the median stock, weights (banks / power) prop the index and hide the collapse in stock profit effect; Marine EquipmentⅡ +2.76% leads, Farming −5.09% lags — sector breadth is 'broad decline', only defensives / weights close green.",
 "t_sec_evidence": "Key Evidence",
 "th_metric": "Metric", "th_read": "Real reading", "th_interp": "Behavioral read",
 "ev_market": "I. Market breadth & overview",
 "ev_upratio": "Up-ratio",
 "ev_upratio_i": "32%→17% (−15pct), 955 up / 4512 down / 124 flat; participation collapses, stocks fall broadly (down 81.1%), a grinding ebb (limit-down only 2, not a panic)",
 "ev_limit": "Limit-up / -down",
 "ev_limit_i": "Limit-up 38 (42→38 slight ease), limit-down 2 (returns from 0), ladder height down to 4 boards (Guilin Tourism) — speculative heat keeps cooling, profit effect contracts",
 "ev_amount": "Turnover",
 "ev_amount_i": "Volume ¥1.65tn (85.5% of 10d avg, 81.5% of 20d avg, still shrinking) — the ebb is driven by contracting existing capital and missing leadership; volume and price weaken together",
 "ev_index": "II. Core indices (2026-09-10 close)",
 "ev_sh": "SSE Composite",
 "ev_sh_i": "−0.43% (3934.40), loses MA20 (3936.76) and BOLL mid-band (3936.76), closes below MA60 (3945.09); MACD 0.0782 (DIF 6.36 / DEA 6.32, coiled), RSI_12 50.20, KDJ_K 40.63 — technically weak and range-bound; PE_TTM 20.44 (10y pctile 79.88% rich, as of 09-09)",
 "ev_sz": "SZ Component",
 "ev_sz_i": "SZ Component −0.77% (13617.67), follows the market down, mid-term weakness persists",
 "ev_cyb": "ChiNext",
 "ev_cyb_i": "ChiNext −0.49% (3338.42) closes lower, growth style keeps weakening",
 "ev_sector": "III. Sector ranking & main line",
 "ev_secup": "Leading sectors",
 "ev_secup_i": "Marine EquipmentⅡ +2.76% (turnover 5.72%, main net inflow +¥464mn) leads, City Commercial BanksⅡ +2.39% / Glass-Fiber +2.23% follow — the main line rotates to defensives / weights and local themes; TMT and prior resources retreat across the board, only ~20% of sectors close up",
 "ev_secdn": "Lagging sectors",
 "ev_secdn_i": "Farming −5.09% (turnover 11.15%) leads losers / Fisheries −4.69% / Farm-Product Processing −4.65% — the agriculture chain collapses sharply, a violent reversal versus 09-09's leading rubber / shipping / resources",
 "ev_board": "Extreme themes",
 "ev_board_i": "Ladder totals 40 names, top board 4 (Guilin Tourism, down from 5); themes rotate from consumer / resources to local hotspots like tourism (Guilin Tourism 4 boards) — faster rotation, lower height",
 "ev_flow": "IV. Capital: ladder / main / margin",
 "ev_height": "Ladder height",
 "ev_height_i": "Height 4 boards (Guilin Tourism, 2026-09-10 close), down from 5; the theme relays to tourism, fundamentals are regional tourism, no notable narrative bubble",
 "ev_main": "Main capital 5d net inflow TOP",
 "ev_main_i": "Main-5d net inflow still concentrates in optical modules / PCB (Innolight +¥7.69bn #1, XYS +¥4.10bn, Dongshan +¥3.13bn), but on 09-10 sector capital has rotated to Marine EquipmentⅡ (main net inflow +¥464mn) and defensives / weights like City Commercial BanksⅡ — capital shifts from high-beta growth to low-valuation safety, optical-module stocks have ebbed; margin data missing, not fabricated.",
 "ev_margin": "Daily margin change TOP",
 "ev_margin_i": "The margin interface returns empty that day (data missing); both daily margin change and aggregate margin balance are unavailable — <b>not fabricated</b>; from visible signals capital rotates to defensives / weights (Marine EquipmentⅡ +¥464mn, City Commercial BanksⅡ), leverage risk cannot be confirmed due to the gap, treat with caution.",
 "ev_hot": "Hot / top gainers",
 "ev_hot_i": "Hotspots led by defensives / local themes: Guilin Tourism 4 boards (tourism) / Marine EquipmentⅡ +2.76% (main net inflow +¥464mn) / City Commercial BanksⅡ +2.39% / Glass-Fiber +2.23%; data_hot board ranking leads with marine equipment, banks, power — consistent with the propping capital direction",
 "ev_margintotal": "Aggregate margin balance",
 "ev_margintotal_i": "Gap: both aggregate margin balance (data_market_overview type=margin) and daily margin change return empty that day — flagged honestly, not fabricated; breadth / indices / turnover / sectors / ladder are real 2026-09-10 closes, main-5d net inflow is 09-09 (unavailable that day)",
 "ev_macro": "V. Core macro indicators",
 "ev_pmi": "Mfg PMI (Jul)",
 "ev_pmi_i": "Fundamentals contract, a clear divergence from 'high valuation + mid-term weakness'; non-mfg new orders soft",
 "ev_capu": "Capacity utilisation (Q2)",
 "ev_capu_i": "Real-economy momentum weakens, prices lack earnings support",
 "ev_cpi": "CPI (Jul)",
 "ev_cpi_i": "Low inflation, weak demand, hard to confirm a broad recovery",
 "ev_social": "Social financing (Jul)",
 "ev_social_i": "Weak credit demand, capital detours into stocks = liquidity-driven feature",
 "ev_m1m2": "M1-M2 spread",
 "ev_m1m2_i": "Active money weak, capital idles, typical late-cycle phenomenon",
 "ev_yield": "10Y gov bond yield",
 "ev_yield_i": "Extremely low risk-free rate, supports valuation yet reflects growth worry",
 "ev_lpr": "LPR",
 "ev_lpr_i": "Accommodative stance unchanged",
 "t_ev_note": "Data basis: macro indicators are monthly (to 2026-07) or daily (to 2026-09-09); breadth / indices / turnover / sectors / ladder are real 2026-09-10 closes. Valuation PE_TTM 20.44 is as of 2026-09-09 (CSI All-Share valuation published with a lag) and is flagged; margin data is missing that day and is flagged, not fabricated. See 'Sources and date basis' at the end.",
 "t_sec_risk": "Risk Stratification",
 "rc1_tag": "Red zone · High valuation + grinding ebb (leverage data missing)",
 "rc1_t": "High valuation + accelerating ebb (leverage missing)",
 "rc1_d": "PE_TTM 20.44 at a 79.88% 10y pctile stays rich, on top of 09-10's grinding ebb (up-ratio 17%, down 81.1%, all three indices lower); margin data is missing so leverage is unconfirmed, but with high valuation + weak indices, prior high-position main lines like optical modules / PCB would draw a deep drawdown if falsified — shrink risk budget markedly.",
 "rc1_rep": "Represented by: high-position optical modules (Innolight / XYS) / PCB (Dongshan) / agriculture-chain highs (Farming −5.09% leads losers)",
 "rc1_cond": "Condition frame: no chasing high-position main lines, no leverage; confirm with sustained volume + index back above short-term averages before right-side entry; cut on breakdown, leverage positions first.",
 "rc2_tag": "Amber zone · Index resilience masks broad stock declines (divergence)",
 "rc2_t": "Index resilient / stocks down",
 "rc2_d": "SSE −0.43% (3934.40 loses MA20), SZ −0.77%, ChiNext −0.49% all close lower, yet the index drop is far smaller than the median stock (down 81.1%); weights (banks / power / marine equipment) prop the index, widening the 'index resilient, stocks down' divergence; turnover shrinks to ¥1.65tn (85.5% of 10d avg), existing capital contracts.",
 "rc2_rep": "Represented by: SSE weights (propping) / ChiNext (−0.49%) / small-mid stocks (down 81.1%)",
 "rc2_cond": "Condition frame: do not chase intraday leaders; new main lines need sustained volume-price confirmation, never treat a single-day rotation as a reversal; beware chasing highs under an 'euphoria' tag.",
 "rc3_tag": "Green zone · Agriculture chain & prior themes collapse",
 "rc3_t": "Agriculture chain / prior themes retreat",
 "rc3_d": "Farming −5.09% (turnover 11.15%) leads losers, Fisheries −4.69% / Farm-Product Processing −4.65% follow, the agriculture chain collapses sharply, a violent reversal versus 09-09's leading rubber / shipping / resources; prior TMT / media keep retreating — themes rotate to defensives, risk appetite contracts.",
 "rc3_rep": "Represented by: Farming (turnover 11.15%) / Fisheries / Farm-Product Processing / prior high-position themes",
 "rc3_cond": "Condition frame: only as a hedge and position protection; shrink the overall risk budget and wait for volume-price confirmation.",
 "t_sec_outlook": "Next session (09-11 Fri) outlook",
 "o_logic": "Reasoning (based on the 09-10 close + crowd-psychology position)",
 "o_logic_text": "Extending 09-10's 'volume-shrinking broad sell-off / ebb accelerates': the cycle sits at 'volume-shrinking broad sell-off / ebb accelerates', with up-ratio 17%, limit-up 38, limit-down 2, all three indices down, turnover shrinking to ¥1.65tn (85.5% of 10d avg), sector breadth 'broad decline' with only ~20% sectors up; index resilience (banks / power propping) versus broad stock declines diverges sharply, valuation pctile 79.88% stays high, margin data missing. Sector directions and trading rules for 09-11 follow (<b>no individual stock recommendations</b>).",
 "o1_tag": "Defensives / weights (watch)",
 "o1_t": "Marine EquipmentⅡ / City Commercial BanksⅡ / Power / Glass-Fiber",
 "o1_d": "09-10 Marine EquipmentⅡ +2.76% (main net inflow +¥464mn), City Commercial BanksⅡ +2.39%, Glass-Fiber +2.23% close green as capital rotates to defensives / weights and local themes; but in an ebb, do not chase — only observe as a hedge.",
 "o1_cond": "Caution: defensives are mostly propping / risk-off driven, sustainability unproven; if turnover keeps shrinking, rotation accelerates and execution gets harder — do not chase laggards, only front-core names.",
 "o2_tag": "Prior high-position themes (avoid)",
 "o2_t": "Optical modules / PCB / agriculture highs / TMT",
 "o2_d": "Prior optical-module / PCB main-5d still lead but stocks have ebbed; the agriculture chain (Farming −5.09%, Fisheries −4.69%) and rubber / shipping / resources show a violent reversal — high-position themes are sold in the ebb, near-term pressure.",
 "o2_cond": "Caution: this is thematic rotation, not fundamental deterioration — do not panic-sell; but avoid high-position themes in the ebb, wait for a shrinking-volume stabilisation signal.",
 "o3_tag": "Wait for signals (stand by)",
 "o3_t": "Volume recovery / up-ratio repair",
 "o3_d": "09-10 up-ratio only 17%, turnover ¥1.65tn (85.5% of 10d avg), ebb accelerates; watch whether 09-11 shows up-ratio back above 30% and turnover returning to ¥1.8tn as an easing signal.",
 "o3_cond": "Caution: in an ebb do not pre-empt the bottom — wait for right-side volume-price confirmation; if limit-down widens past 10 or the SSE breaks MA60 (3945.09), cut to ≤30%.",
 "o_rules_t": "Trading rules (09-11)",
 "o_r1": "<b>Position</b>: neutral-to-cautious (30–40%), no leverage. Sentiment worsens from 'volume-shrinking divergence / short-term ebb' to 'volume-shrinking broad sell-off / ebb accelerates'; risk holds Medium but nears the upper edge — control size in the ebb, do not chase.",
 "o_r2": "<b>Volume-price confirmation</b>: only ease the ebb if up-ratio rebounds above 30% and turnover returns to ¥1.8tn; if turnover keeps shrinking below ¥1.6tn or limit-down widens past 10, cut to ≤30%.",
 "o_r3": "<b>Main-line participation</b>: defensives / weights (marine / city banks / power) only as a hedge watch, no laggard chasing; avoid prior high-position themes (optical modules / PCB / agriculture) in the ebb.",
 "o_r4": "<b>Avoid list</b>: prior high-position themes (optical modules / PCB / agriculture / rubber-shipping), high-ladder relay in the ebb (Guilin Tourism 4 boards, caution), leverage-concentrated names that have ebbed.",
 "o_r5": "<b>Risk control</b>: if 09-11 limit-down widens past 10 or the SSE breaks MA60 (3945.09), treat it as ebb acceleration and cut immediately; do not add leverage until margin data resumes.",
 "o_compliance": "<b>Compliance:</b> this outlook gives sector directions and trading rules only, with no individual stock recommendations; the crowd-psychology position and sector inferences are based on real 2026-09-10 market data. Markets carry risk; decisions must be independent.",
 "t_sec_source": "Sources & date basis",
 "s_breadth": "Breadth / overview",
 "s_breadth_v": "westock · data_market_overview(market_statis_updown); 2026-09-10 close",
 "s_portrait": "Market portrait summary",
 "s_portrait_v": "westock · data_market_overview(type=summary); 2026-09-10 (up-ratio 17% breadth collapse, volume-shrinking sell-off)",
 "s_index": "Index performance",
 "s_index_v": "westock · data_market_overview(market_statis_daily_trade); 2026-09-10 close",
 "s_sector": "Sector ranking / flows",
 "s_sector_v": "westock · data_sector(mode=ranking, kind=industry/concept); 2026-09-10",
 "s_hot": "Hot stocks",
 "s_hot_v": "westock · data_hot(kind=board); 2026-09-10 (marine equipment / banks / power on top)",
 "s_macro": "Core macro",
 "s_macro_v": "westock · data_macro(cn_pmi, cn_capacity_utilization, cn_financing etc.); PMI/capacity/social-financing reviewed 08-21 (no new release, monthly), CPI/M1-M2/10Y/LPR carried forward",
 "s_margin": "Margin (stocks)",
 "s_margin_v": "westock · margin interface returns empty that day (data missing, not fabricated)",
 "s_main": "Main capital 5d net inflow",
 "s_main_v": "westock · tool_ranking(metric=cap_main_5d); 2026-09-09 basis (unavailable that day)",
 "s_board": "Ladder height",
 "s_board_v": "westock · tool_ranking(metric=limitup_days); 2026-09-10 (40 names, top board 4)",
 "s_gap": "Data gaps",
 "s_gap_v": "Aggregate margin balance and daily margin change both return empty that day — flagged honestly, not fabricated; valuation PE_TTM 20.44 is as of 2026-09-09 (CSI All-Share valuation published with a lag) and is flagged; main-5d net inflow is 09-09 basis.",
 "t_src_note": "Timing: all timestamps are Beijing time. Macro data are monthly/quarterly and cannot be aligned directly with daily quotes; each is flagged. Breadth / indices / sectors / ladder are real 2026-09-10 data; valuation / main-5d are 2026-09-09 basis, margin missing that day — all flagged.",
 "disc1": "Disclaimer: the above is based on public data and quantitative analysis, for reference only, not investment advice. Markets carry risk; investment decisions should be made independently per your own risk tolerance, financial status and goals, and consult a licensed professional when necessary. Past performance does not predict future returns.",
 "disc2": "This assessment is 'crowd psychology / conditional framework' analysis, not a trading order; risk readings and bias severities are model mappings and must be cross-validated with price structure, valuation and flows, not used alone as a trade basis.",
 "t_foot": "Crowd Psychology Risk Radar · generated from westock official market data · research reference only",
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
# 2) 重建 BIAS 数组（09-10 真实数据）
# ============================================================
BIAS = [
 {"zh":"羊群效应","en":"Herding","sev":4,
  "zhd":"涨股比仅 17%、下跌 81.1%，但资金仍涌向航海装备Ⅱ（主力净流入 +4.64亿）、城商行Ⅱ等防御/权重护盘方向，前期光模块虽退潮但主力5日仍集中；群体从追逐弹性转向抱团避险，独立判断被「护盘」叙事淹没。",
  "end":"Up-ratio only 17% and down-stocks 81.1%, yet capital still crowds into defensives / weights like Marine EquipmentⅡ (main net inflow +¥464mn) and City Commercial BanksⅡ; the herd rotates from chasing beta to huddling into safety, and independent judgement is drowned by the 'propping' narrative."},
 {"zh":"损失厌恶","en":"Loss Aversion","sev":3,
  "zhd":"个股普跌（跌 4512 只、81.1%），持有者在退潮中由前日切换转为被动扛单，把「错过防御/旅游接力」视为损失——阴跌式退潮下抛压分散、跌停仅 2 只，非恐慌但磨损明显。",
  "end":"Stocks fall broadly (4512 down, 81.1%); holders shift from rotating to passively holding losers, treating 'missing the defensive / tourism relay' as the bigger loss — under a grinding ebb the selling is dispersed, limit-down only 2, not panic but clear erosion."},
 {"zh":"心理账户/赌徒谬误","en":"Mental Acct / Gambler","sev":3,
  "zhd":"把光模块主力5日净流入（中际旭创 +76.9亿）外推为「主线仍强」，忽视 09-10 个股普跌、连板降至 4 板、农业链反转，题材与资金短期背离。",
  "end":"Extrapolating the main-5d optical-module inflow (Innolight +¥7.69bn) into 'the main line is still strong', ignoring 09-10's broad declines, ladder down to 4 boards and the agriculture reversal — story and capital diverge short-term."},
 {"zh":"过度自信","en":"Overconfidence","sev":3,
  "zhd":"把上证仅 −0.43%（失守 MA20 但跌幅有限）读作「指数无忧」，忽视个股中位数大跌、成交缩量至 ¥1.65万亿（10 日均 85.5%）、估值分位 79.88% 仍高，权重护盘掩盖个股塌陷。",
  "end":"Reading SSE's mere −0.43% (losing MA20 but a limited drop) as 'index fine', ignoring the median stock's sharp fall, turnover shrink to ¥1.65tn (85.5% of 10d avg) and valuation pctile 79.88% high — weights prop the index and mask the stock collapse."},
 {"zh":"处置效应","en":"Disposition","sev":2,
  "zhd":"卖盈（农业链/前期题材在退潮中被抛）持亏（光模块套牢盘被视为「回本仓」），两融数据暂缺但杠杆风险无法证伪；被动扛单特征明显。",
  "end":"Selling winners (agriculture chain / prior themes dumped in the ebb) while holding losers (trapped optical-module books treated as 'break-even'), margin data missing so leverage risk unconfirmed — passive holding is evident."},
 {"zh":"锚定偏差","en":"Anchoring","sev":3,
  "zhd":"锚定 09-09「涨股比 32%」与前期暖值，对 09-10 的 17% 广度崩塌缺乏定价锚，易在单日指数抗跌中误判「回调即买点」。",
  "end":"Anchored to 09-09's 32% up-ratio and prior warm readings, lacking a pricing anchor at 09-10's 17% breadth collapse — prone to mistaking a single index-resilient day for 'dip = buy'."},
 {"zh":"确认偏误","en":"Confirmation Bias","sev":4,
  "zhd":"只看权重护盘（银行/电力/航海装备收红）的「指数抗跌」信号，忽略涨股比 17%、下跌 81.1%、三大指数全跌、成交缩量、农业链 −5.09% 领跌的现实。",
  "end":"Only watching the 'index resilient' signal from weights propping (banks / power / marine green), while ignoring up-ratio 17%, down 81.1%, all three indices lower, shrinking turnover and Farming −5.09% leading losers."},
 {"zh":"近因偏差","en":"Recency","sev":3,
  "zhd":"外推单日指数抗跌为「调整有限」，对 09-04 恐慌（28%）与 09-07 转折记忆淡化，忽视退潮需 2 日以上量价确认，易抄在半山腰。",
  "end":"Extrapolating a single index-resilient day into 'the correction is limited'; memories of 09-04 panic (28%) and the 09-07 turn fade fast, ignoring that an ebb needs 2+ sessions of volume-price confirmation — easy to catch a falling knife."},
 {"zh":"叙事偏差","en":"Narrative","sev":4,
  "zhd":"「防御/红利/航海景气」叙事被护盘资金强化，故事与资金短期共振；但两融暂缺、估值分位 79.88% 仍高，叙事一旦证伪回撤幅度大。",
  "end":"The 'defensive / dividend / marine-prosperity' narrative is reinforced by propping capital, story and capital resonate short-term; but margin is missing and valuation pctile 79.88% stays high, so a falsified narrative would mean a severe drawdown."},
 {"zh":"代表性启发","en":"Representativeness","sev":3,
  "zhd":"被航海装备Ⅱ +2.76%、城商行Ⅱ +2.39% 的单日收红代表整体，误判「结构健康」，忽视涨股比仅 17%、种植业 −5.09% 领跌、成交缩量的现实。",
  "end":"Marine EquipmentⅡ +2.76% and City Commercial BanksⅡ +2.39% one-day greens taken as representative of the whole market; mistaking it for 'healthy structure' while ignoring up-ratio 17%, Farming −5.09% leading losers and shrinking turnover."},
]
bias_js = "var BIAS = [\n" + ",\n".join(
    "    {zh:\"%s\",en:\"%s\",sev:%d,zhd:\"%s\",end:\"%s\"}" % (esc(b["zh"]), esc(b["en"]), b["sev"], esc(b["zhd"]), esc(b["end"]))
    for b in BIAS) + "\n  ];"
html, _n = re.subn(r'var BIAS = \[.*?\n  \];', bias_js, html, count=1, flags=re.S)
assert _n == 1, "BIAS 替换失败"

# ============================================================
# 3) 静态 body 证据表 + 涨跌分布 SVG 修正
#    OLD = 09-09 实际值（源 20260909.html 中内容），NEW = 09-10 值
# ============================================================
BODY = [
 # chips
 ("<b data-page-node-id=\"XYUMFmlTdm8XIY0AjuGqHl\">32%</b></span>",
  "<b data-page-node-id=\"XYUMFmlTdm8XIY0AjuGqHl\">17%</b></span>"),
 ("<b data-page-node-id=\"TGGkf6Aiq4W9rr7kZjE9Ny\">42</b></span>",
  "<b data-page-node-id=\"TGGkf6Aiq4W9rr7kZjE9Ny\">38</b></span>"),
 ("<b data-page-node-id=\"XjnG9DrCRjj9c2Yl1w5OtT\">5板</b></span>",
  "<b data-page-node-id=\"XjnG9DrCRjj9c2Yl1w5OtT\">4板</b></span>"),
 ("<b data-page-node-id=\"Iv15oHOTHUISIe9K67AUcw\">¥1.86万亿</b></span>",
  "<b data-page-node-id=\"Iv15oHOTHUISIe9K67AUcw\">¥1.65万亿</b></span>"),
 # breadth SVG rects
 ("width=\"160\" height=\"26\" fill=\"#d8392b\"",
  "width=\"85\" height=\"26\" fill=\"#d8392b\""),
 ("x=\"174\" y=\"14\" width=\"340\" height=\"26\" fill=\"#1a9e5a\"",
  "x=\"99\" y=\"14\" width=\"405\" height=\"26\" fill=\"#1a9e5a\""),
 # breadth SVG texts
 ("<text x=\"167\" y=\"33\" fill=\"#fff\" font-size=\"14\" font-weight=\"800\" text-anchor=\"middle\" data-page-node-id=\"KJRq05V4iS20do4qlroEAe\">32%</text>",
  "<text x=\"167\" y=\"33\" fill=\"#fff\" font-size=\"14\" font-weight=\"800\" text-anchor=\"middle\" data-page-node-id=\"KJRq05V4iS20do4qlroEAe\">17%</text>"),
 ("<text x=\"407\" y=\"33\" fill=\"#fff\" font-size=\"14\" font-weight=\"800\" text-anchor=\"middle\" data-page-node-id=\"SiDfcFpJrG6XXIlqQML5Tc\">68%</text>",
  "<text x=\"407\" y=\"33\" fill=\"#fff\" font-size=\"14\" font-weight=\"800\" text-anchor=\"middle\" data-page-node-id=\"SiDfcFpJrG6XXIlqQML5Tc\">81%</text>"),
 ("<text x=\"514\" y=\"33\" fill=\"#6b675f\" font-size=\"11\" font-weight=\"700\" text-anchor=\"end\" data-page-node-id=\"9JdeMEuoxvtAR2FB9vvwe2\">4% 平盘</text>",
  "<text x=\"514\" y=\"33\" fill=\"#6b675f\" font-size=\"11\" font-weight=\"700\" text-anchor=\"end\" data-page-node-id=\"9JdeMEuoxvtAR2FB9vvwe2\">2% 平盘</text>"),
 # breadth stat rows
 ("<text x=\"340\" y=\"72\" fill=\"#d8392b\" data-page-node-id=\"9FWjOmhuXe5y1xlsrBFCYJ\">1794</text>",
  "<text x=\"340\" y=\"72\" fill=\"#d8392b\" data-page-node-id=\"9FWjOmhuXe5y1xlsrBFCYJ\">955</text>"),
 ("<text x=\"340\" y=\"92\" fill=\"#1a9e5a\" data-page-node-id=\"TLqUd5jzLdQfCq2SZZQDs2\">3642</text>",
  "<text x=\"340\" y=\"92\" fill=\"#1a9e5a\" data-page-node-id=\"TLqUd5jzLdQfCq2SZZQDs2\">4512</text>"),
 ("<text x=\"340\" y=\"112\" fill=\"#6b675f\" data-page-node-id=\"Ckj5b8hdFgwhtpzCUB2OUz\">124</text>",
  "<text x=\"340\" y=\"112\" fill=\"#6b675f\" data-page-node-id=\"Ckj5b8hdFgwhtpzCUB2OUz\">94</text>"),
 ("<text x=\"340\" y=\"138\" fill=\"#d8392b\" data-page-node-id=\"erpCgdzAWQqHUaFCIB6ONh\">42</text>",
  "<text x=\"340\" y=\"138\" fill=\"#d8392b\" data-page-node-id=\"erpCgdzAWQqHUaFCIB6ONh\">38</text>"),
 ("data-page-node-id=\"IkP0POsbdIrZpTE6aLWZOs\">0</text>",
  "data-page-node-id=\"IkP0POsbdIrZpTE6aLWZOs\">2</text>"),
 ("<text x=\"340\" y=\"184\" fill=\"#1c1b19\" data-page-node-id=\"4IEjQsxpWGX3TlV1bJDu2v\">¥1.86万亿</text>",
  "<text x=\"340\" y=\"184\" fill=\"#1c1b19\" data-page-node-id=\"4IEjQsxpWGX3TlV1bJDu2v\">¥1.65万亿</text>"),
 # breadth annotations
 ("<text x=\"355\" y=\"72\" data-page-node-id=\"fMZlrdAm2QFbriIsk7PrmK\">（占 32%，较上一报告日（09-07） −25pct）</text>",
  "<text x=\"355\" y=\"72\" data-page-node-id=\"fMZlrdAm2QFbriIsk7PrmK\">（占 17%，较上一报告日（09-09） −15pct）</text>"),
 ("<text x=\"355\" y=\"92\" data-page-node-id=\"LcHh8sFFglQGbCDkF7OXLz\">（占 68%，较上一报告日（09-07） +25pct）</text>",
  "<text x=\"355\" y=\"92\" data-page-node-id=\"LcHh8sFFglQGbCDkF7OXLz\">（占 81%，较上一报告日（09-09） +13pct）</text>"),
 ("<text x=\"355\" y=\"138\" data-page-node-id=\"UOfK9e4xqIW5rwOGOi749u\">（较前日 −48 只，连板高度 5板）</text>",
  "<text x=\"355\" y=\"138\" data-page-node-id=\"UOfK9e4xqIW5rwOGOi749u\">（较前日 −4 只，连板高度 4板）</text>"),
 ("<text x=\"355\" y=\"158\" data-page-node-id=\"xZAnt7VByXOneccD4UJrCu\">（较前日 −1 只，跌停清零）</text>",
  "<text x=\"355\" y=\"158\" data-page-node-id=\"xZAnt7VByXOneccD4UJrCu\">（较前日 +2 只，跌停 2 只）</text>"),
 ("<text x=\"355\" y=\"184\" data-page-node-id=\"abK6rYywDKvCb1lfTGZhvu\">（环比 −900亿，缩量明显）</text>",
  "<text x=\"355\" y=\"184\" data-page-node-id=\"abK6rYywDKvCb1lfTGZhvu\">（环比 −2100亿，继续缩量）</text>"),
 # evidence table number cells
 ("<span class=\"val up\" data-page-node-id=\"Mr3zXE1cdvOA7YBKLFINSN\">32%</span>（涨1794 / 跌3642 / 平124）",
  "<span class=\"val up\" data-page-node-id=\"Mr3zXE1cdvOA7YBKLFINSN\">17%</span>（涨955 / 跌4512 / 平94）"),
 ("<span class=\"val up\" data-page-node-id=\"Gth81hvv1Ztc6nwXzEyWBd\">42</span> / <span class=\"val down\" data-page-node-id=\"21iGEfRDHSSI08ui6EYmr9\">0</span>",
  "<span class=\"val up\" data-page-node-id=\"Gth81hvv1Ztc6nwXzEyWBd\">38</span> / <span class=\"val down\" data-page-node-id=\"21iGEfRDHSSI08ui6EYmr9\">2</span>"),
 ("<span class=\"val\" data-page-node-id=\"kZiHFNJMsHHj4nPor0Aooz\">¥1.86万亿</span>（较前次 −900亿，缩量明显）",
  "<span class=\"val\" data-page-node-id=\"kZiHFNJMsHHj4nPor0Aooz\">¥1.65万亿</span>（较前次 −2100亿，继续缩量）"),
 # index number cells
 ("<span class=\"val up\" data-page-node-id=\"uB8Ci75PemCyQ26khKkCqv\">3951.51　+0.28%</span>",
  "<span class=\"val down\" data-page-node-id=\"uB8Ci75PemCyQ26khKkCqv\">3934.40　−0.43%</span>"),
 ("<span class=\"val up\" data-page-node-id=\"1XdQU9tQznkNJoACr8yKxV\">13723.32　+0.15%</span>",
  "<span class=\"val down\" data-page-node-id=\"1XdQU9tQznkNJoACr8yKxV\">13617.67　−0.77%</span>"),
 ("<span class=\"val down\" data-page-node-id=\"vP3bLD188hrSJHfiJeqrbN\">3354.97　−0.14%</span>",
  "<span class=\"val down\" data-page-node-id=\"vP3bLD188hrSJHfiJeqrbN\">3338.42　−0.49%</span>"),
 # static header date + Next-Session
 ("<b data-page-node-id=\"DsNwBezYd2kDSq4jEnUY3h\">2026-09-09 收盘（北京时间，盘后）</b>",
  "<b data-page-node-id=\"DsNwBezYd2kDSq4jEnUY3h\">2026-09-10 收盘（北京时间，盘后）</b>"),
 ("Next-Session Outlook (09-10 Thu)", "Next-Session Outlook (09-11 Fri)"),
]
for old, new in BODY:
    if old in html:
        html = html.replace(old, new, 1)
    else:
        print("[skip-body] 未命中: %r" % old[:60])

# ---------- 3b) 证据表「读数」单元格（含 <br>，用节点 id 正则整格替换） ----------
def cell_replace(nodeid, inner):
    global html
    pat = re.compile(r'(<td data-page-node-id="%s">).*?(</td>)' % re.escape(nodeid), re.S)
    html, n = pat.subn(lambda m: m.group(1) + inner + m.group(2), html)
    assert n == 1, "cell %s 未替换 (%d)" % (nodeid, n)

cell_replace("nq7dzJdZLVXbHvhGVgMjmm",
  '<span class="val up">航海装备Ⅱ +2.76%</span>（换手 5.72%、主力净流入 +4.64亿）<br>城商行Ⅱ +2.39% / 玻璃玻纤 +2.23% 跟随<br>全市场 124 个行业绝大多数下跌，仅约 2 成行业收红')
cell_replace("FuH6rpiGcPfQLNWdEAfE5C",
  '<span class="val down">种植业 −5.09%</span>（换手 11.15%）<br>渔业 −4.69% / 农产品加工 −4.65%<br>农业链集体重挫，与 09-09 领涨的橡胶/航运/资源剧烈反转')
cell_replace("G4W53x3pZtrVc3iDD8dyhd",
  '<span class="val up">连板高度 4 板</span>（桂林旅游）<br>共 40 只连板；题材由消费/资源切换至旅游（桂林旅游 4板），轮动加快、高度下降')
cell_replace("mJzF4exTKoSPGbyKJFGuol",
  '<span class="val up">桂林旅游 4板</span>（2026-09-10）')
cell_replace("ete9fyLbZeTylRxrAobLDX",
  '<span class="val">主力5日净流入 TOP（09-09 口径，当日暂缺）</span>')
cell_replace("UIeBrUPDeW47oNrPhcQYJA",
  '<span class="val">融资单日变动 TOP（两融接口返回空，数据暂缺）</span>')
cell_replace("Mr1pnwHFZvteytFzFDA7yP",
  '<span class="val up">桂林旅游 4板</span>（旅游）<br>航海装备Ⅱ +2.76%（主力净流入 +4.64亿）<br>城商行Ⅱ +2.39% / 玻璃玻纤 +2.23%<br>种植业 −5.09%（换手 11.15%）/ 渔业 −4.69%')

# ============================================================
# 4) 雷达数值标签（红字组）—— 六维：拥挤62/融资66/换手44/广度82/媒体46/估值87
#    调整依据：广度崩塌(17%→82)、换手继续萎缩(50→44)、融资因缺失谨慎上调(64→66)、
#    拥挤升至62(抱团避险)、媒体降温(52→46)、估值87持平(口径09-09)
# ============================================================
old_radar = '<text x="160" y="71" data-page-node-id="SznNDBJgmRR0hjomh3cTNc">60</text><text x="237" y="120" data-page-node-id="gBCaoioE16mEnFj93iVE7K">64</text><text x="209" y="194" data-page-node-id="XCOMaZBFFBCR7fO8PCsTsG">50</text>\n            <text x="160" y="167" data-page-node-id="D8keUupD4ZTiIwh0qPobCP">62</text><text x="109" y="201" data-page-node-id="c6EJsCd8PQAaZ8sUHv4BbP">52</text><text x="55" y="118" data-page-node-id="TsWMFkny4MBOVmEfaSpoNe">87</text>'
new_radar = '<text x="160" y="71" data-page-node-id="SznNDBJgmRR0hjomh3cTNc">62</text><text x="237" y="120" data-page-node-id="gBCaoioE16mEnFj93iVE7K">66</text><text x="209" y="194" data-page-node-id="XCOMaZBFFBCR7fO8PCsTsG">44</text>\n            <text x="160" y="167" data-page-node-id="D8keUupD4ZTiIwh0qPobCP">82</text><text x="109" y="201" data-page-node-id="c6EJsCd8PQAaZ8sUHv4BbP">46</text><text x="55" y="118" data-page-node-id="TsWMFkny4MBOVmEfaSpoNe">87</text>'
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
# 6) hub（web/psychology/index.html）插入 0910 条目
# ============================================================
HUB = os.path.join(HERE, "..", "web", "psychology", "index.html")
hub = open(HUB, encoding="utf-8").read()
if "crowd-psychology-risk-radar-20260910.html" not in hub:
    entry = """    },
    {
      file:"crowd-psychology-risk-radar-20260910.html", date:"2026-09-10",
      risk:"中", riskEn:"Medium",
      cycleZh:"缩量普跌 · 退潮加速", cycleEn:"Volume-shrinking broad sell-off / Ebb accelerates",
      cycleNoteZh:"涨股比17%·下跌81%", cycleNoteEn:"Up-ratio 17% · Down 81%",
      up:"17%", limitup:"38", board:"4板", turn:"¥1.65万亿",
      summaryZh:"涨股比32%→17%（955涨/4512跌/平94）、涨停42→38、跌停0→2，下跌家数占比81.1%；上证−0.43%（3934.40失守MA20）深成−0.77%（13617.67）创业板−0.49%（3338.42）三大指数全跌，但指数跌幅远小于个股中位数，权重（银行/电力）护盘致指数抗跌、个股普跌背离加剧；成交¥1.65万亿（10日均85.5%、20日均81.5%）继续缩量。航海装备Ⅱ+2.76%（换手5.72%、主力净流入+4.64亿）领涨，城商行Ⅱ+2.39%/玻璃玻纤+2.23%跟随，主线切向防御/权重；种植业−5.09%（换手11.15%）领跌，渔业−4.69%/农产品加工−4.65%跟随，农业链集体重挫，与09-09领涨的橡胶/航运/资源剧烈反转。连板40只、最高板4板（桂林旅游）。两融数据暂缺（未编造）。估值PE_TTM 20.44（10年分位79.88%）仍偏高——阴跌式退潮确认，风险等级中但逼近上沿。",
      summaryEn:"Up-ratio 32%→17% (955 up / 4512 down / 124 flat), limit-up 42→38, limit-down 0→2, down-stocks 81.1%; SSE −0.43% (3934.40 loses MA20), SZ −0.77% (13617.67), ChiNext −0.49% (3338.42) all close lower, yet the index drop is far smaller than the median stock — weights (banks / power) prop the index, widening the 'index resilient, stocks down' divergence; turnover ¥1.65tn (85.5% of 10d avg, 81.5% of 20d avg) keeps shrinking. Marine EquipmentⅡ +2.76% (turnover 5.72%, main net inflow +¥464mn) leads, City Commercial BanksⅡ +2.39% / Glass-Fiber +2.23% follow as the main line rotates to defensives / weights; Farming −5.09% (turnover 11.15%) leads losers, Fisheries −4.69% / Farm-Product Processing −4.65% follow, the agriculture chain collapses versus 09-09's leading rubber / shipping / resources. Ladder 40 names, top board 4 (Guilin Tourism). Margin data missing (not fabricated). Valuation PE_TTM 20.44 (10y pctile 79.88%) still rich — grinding ebb confirmed; risk Medium but near upper edge.\""""
    tail = "    }\n  ];\n  REPORTS.reverse();"
    assert tail in hub, "hub tail not found"
    # 注意：entry 必须以对象闭合 "    }" 结尾，否则 hub JS 报 SyntaxError（0904 脚本遗留坑）
    hub = hub.replace(tail, entry + "\n    }\n  ];\n  REPORTS.reverse();", 1)
    open(HUB, "w", encoding="utf-8").write(hub)
    print("[ok] hub 已插入 0910 条目")
else:
    print("[skip] hub 已有 0910 条目")

# ============================================================
# 7) 写出 + 校验
# ============================================================
open(OUT, "w", encoding="utf-8").write(html)
print("[ok] 写出 %s (%d bytes)" % (OUT, len(html)))

leftover = ["32%</text>", "68%</text>", "1794", "3642", "橡胶 +4.07%", "数字媒体 −4.12%",
            "百大集团 5板", "¥1.86万亿", "3951.51", "13723.32", "3354.97",
            "中际旭创 +5.61亿", "（环比 −900亿", "57%", "90→42", "09-09 · 收盘",
            "缩量分化 / 短线退潮", "Next-Session Outlook (09-10"]
bad = [s for s in leftover if s in html]
print("[校验] 残留旧数据:", bad if bad else "无")
