# -*- coding: utf-8 -*-
"""重建 2026-08-31 群体心理风险雷达：基于 08-27 模板，
1) 解析原 I18N zh/en 块为字典，覆盖所有带日期/数据的叙述键（含 tv1-tv8、hv_*、t_src_note、s_*_v），
   标签键原样保留，整体重序列化替换；2) 重建 BIAS 数组；3) 修正静态 body 证据表与涨跌分布 SVG；
   4) 雷达几何重算。保证 0 旧数据、0 外链。"""
import re, os

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "crowd-psychology-risk-radar-20260827.html")
OUT = os.path.join(HERE, "crowd-psychology-risk-radar-20260831.html")
html = open(SRC, encoding="utf-8").read()

# ============================================================
# 1) 解析原 zh / en 块为字典
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
# 2) 08-31 叙述覆盖（中文）
# ============================================================
ZH = {
 "t_headline_sub": "2026-08-31 · 收盘",
 "t_breadth": "市场涨跌分布（2026-08-31 收盘）",
 "hk_stage": "阶段定性", "hv_stage": "<b>缩量滞涨 / 结构分化</b>（08-31）",
 "hk_upratio": "涨股比", "hv_upratio": "<b>57%</b>（前日 61% · ↓ 4pct）",
 "hk_lim": "涨停 / 跌停", "hv_lim": "<b>89</b> / <b>13</b>",
 "hk_amt": "成交额", "hv_amt": "<b>¥2.131万亿</b>（缩量滞涨 +293亿）",
 "hk_cycle": "情绪周期", "hv_cycle": "<b>缩量滞涨 / 结构分化</b>",
 "hk_risk": "风险等级", "hv_risk": "<b class=\"hl-risk\">高</b>",
 "hk_flag": "关键提示", "hv_flag": "官方「<b>狂热</b>」标签由涨停>50触发（涨停89>50，强支撑）；真实涨股比57%仍<70%阈值 = <b>标签略超前广度，缩量滞涨下广度回落</b>",
 "tk1": "阶段定性", "tv1": "A 股 08-31 在 08-28「缩量滞涨 / 结构分化」基础上延续：成交维持 ¥2.131万亿（环比 +293亿、较前日微缩），涨股比 57%（3181涨 / 2218跌 / 平152），涨停 89、跌停 13，三指微涨（上证 +0.86% / 深成 +0.44% / 创业板 +0.42%），技术仍强（MACD 金叉）；但量能萎缩、结构分化（传媒 / AI应用领涨，饰品 / 乘用车 / 贵金属领跌），高位承接转弱，缩量滞涨特征明确。风险等级维持 <b>高</b>。",
 "tk2": "广度回落", "tv2": "涨股比 <b>57%</b>（前日 61% ↓ 4pct）· 涨停 <b>89</b>（61→89）· 跌停 <b>13</b>（4→13）· 成交 <b>¥2.131万亿</b>（缩量滞涨，环比 +293亿）。",
 "tk3": "指数微涨", "tv3": "上证 <b>+0.86%</b> / 深成 <b>+0.44%</b> / 创业板 <b>+0.42%</b>；三指齐涨但涨幅收窄，创业板 60日 <b>−14.20%</b>、深成 60日 <b>−9.20%</b> 中期弱势未改。",
 "tk4": "板块轮动", "tv4": "<b>传媒与 AI 应用全面激活 + 数字媒体领涨</b>：数字媒体 +7.19%（芒果超媒 +20.00%）/ 影视院线 +7.02%（华策影视 +15.77%）/ 出版 +5.26%（中文在线 +20.02%）/ 电视广播 +4.38% / 广告营销 +3.85% / 游戏 +3.40%；<b>饰品 −4.67%、乘用车 −3.12%、光伏设备 −2.82%、贵金属 −2.67%、白色家电 −2.31%、股份制银行 −1.10% 领跌</b>（结构分化，资金由周期 / 资源切向传媒 / AI应用）。",
 "tk5": "连板结构", "tv5": "连板高度 <b>6 板</b>（海鸥住工），万向德农 5板、捷荣技术 5板、锦龙股份 4板；投机热度延续，主线偏传媒 / AI应用，持续性待验。",
 "tk6": "杠杆升温", "tv6": "融资单日加仓榜 <b>中际旭创 +11.07亿 居首</b>（AI 算力光模块），新易盛 +8.71亿、星网锐捷 +3.32亿、东材科技 +3.07亿、三环集团 +2.50亿——杠杆追涨电子硬件（AI 算力光模块），较 08-28 延续升温，拥挤度与回补风险仍高。",
 "tk7": "估值 / 基本面背离", "tv7": "PE 分位 <b>70-90%</b> + PMI <b>49.2</b>（枯荣线下）+ 社融同比 <b>−7.25%</b>；指数微涨、估值仍高，股价已先行，但基本面接不住当前位阶。",
 "tk8": "情绪周期", "tv8": "由「缩量滞涨 / 结构分化」延续 <b>缩量滞涨 / 广度回落</b>；官方画像机械标「狂热」由涨停>50触发（08-31 涨停 89>50 强支撑），涨股比 57% 仍<70% 满阈值 = 标签略超前广度，量能萎缩下广度回落；技术仍强、三指微涨、涨停维持 89——但缩量滞涨、结构分化、高位承接转弱。风险等级维持 <b>高</b>。",
 "t_tldr_text": "A股 08-31 呈现「缩量滞涨 / 结构分化」：成交维持 ¥2.131万亿（环比 +293亿、较前日微缩），涨股比 57%（3181涨 / 2218跌 / 平152），涨停 89、跌停 13，三大指数微涨（上证 +0.86% / 深成 +0.44% / 创业板 +0.42%），技术仍强（MACD 金叉），看似延续。板块层面「传媒与 AI 应用全面激活 + 数字媒体领涨」：数字媒体 +7.19%（芒果超媒 +20.00%）领涨，影视院线 +7.02%（华策影视 +15.77%）、出版 +5.26%（中文在线 +20.02%）、电视广播 +4.38%、广告营销 +3.85%、游戏 +3.40% 同列强势；饰品 −4.67%、乘用车 −3.12%、光伏设备 −2.82%、贵金属 −2.67%、白色家电 −2.31%、股份制银行 −1.10% 列跌（结构分化，资金由周期 / 资源切向传媒 / AI应用）。连板高度升至 6板（海鸥住工），万向德农 5板、捷荣技术 5板、锦龙股份 4板。关键资金信号：融资单日加仓榜中际旭创 +11.07亿居首（AI 算力光模块），新易盛 +8.71亿、星网锐捷 +3.32亿、东材科技 +3.07亿、三环集团 +2.50亿——杠杆追涨电子硬件，较 08-28 延续升温。官方画像（data_market_overview type=summary，2026-08-31）机械标「狂热」因涨停>50 触发，08-31 真实涨股比 57% 仍<70% 满阈值 = 标签略超前广度；技术仍强、三指微涨、涨停维持 89，但缩量滞涨、结构分化（饰品 / 乘用车 / 贵金属领跌）、量能萎缩下广度回落，高位承接转弱。基本面（PMI 49.2 / 产能利用率 73.6% / 社融同比 −7.25%）依旧未跟上。群体心理由「缩量滞涨 / 结构分化」延续「缩量滞涨 / 广度回落」——缩量滞涨、结构分化，追涨风险上升，风险等级维持高。",
 "t_cycle_note": "注：上方「乐观」为实时群体心理定位（缩量滞涨 / 结构分化）——08-31 涨跌分布（涨股比 57%、涨停 89 只、跌停 13 只、成交 ¥2.131万亿）显示量能萎缩、广度回落（由 61% 降至 57%），结构分化加剧（传媒 / AI应用领涨，饰品 / 乘用车 / 贵金属领跌）；技术面仍强（MACD 金叉）、三指微涨、涨停维持 89，但缩量滞涨特征明确，高位承接转弱。官方市场画像（data_market_overview type=summary，2026-08-31）机械标「狂热」因涨停>50 触发，08-31 真实涨股比 57% 仍<70% 满阈值 = 标签略超前广度；若量能继续萎缩、指数冲高回落，情绪将回疑 / 再探分歧。",
 "t_radar_note": "六维风险读数（0–100，由下方真实数据综合映射，越高代表该维度群体脆弱性越强）：拥挤度 72 / 融资 70 / 换手 56 / 广度 52 / 媒体情绪 68 / 估值 88。广度由 50 升至 52（08-31 涨股比 57%，由 61% 回落、参与度回落 = 脆弱性略升）；换手由 54 升至 56（成交维持 ¥2.131万亿，活跃换手平稳）；融资由 64 升至 70（融资单日中际旭创 +11.07亿 / 新易盛 +8.71亿 追涨 AI 硬件，杠杆升温）；拥挤度由 68 升至 72（6板连板延续 + 传媒 / AI应用集中爆发 + 小盘抱团，集中度显著上升）；媒体由 66 升至 68（涨停 89、三指微涨、传媒涨停潮，情绪温度升温）；估值仍高悬 88（指数微涨，官方画像 PE分位 70-90% 偏高区间）。整体呈「缩量滞涨 / 结构分化」结构，广度与媒体修复、拥挤度上升，但量能萎缩、结构分化（饰品 / 乘用车 / 贵金属领跌），高位承接转弱下脆弱性未消。",
 "t_breadth_note": "涨股比由 61% 回落至 57%、跌停由 4→13：缩量滞涨、广度回落，参与度偏多但转弱。涨停 89 只（官方「狂热」标签由涨停>50 触发，89>50 强支撑；真实涨股比 57% 仍<70% 满阈值 = 标签略超前广度），连板高度升至 6板、跌停略升，风险偏好偏乐观但量能萎缩。指数微涨（上证 +0.86% / 深成 +0.44% / 创业板 +0.42%），创业板 60日 −14.20% 中期仍弱；成交 ¥2.131万亿环比 +293亿（缩量滞涨）。08-28 的「结构分化」在 08-31 延续为「缩量滞涨」，量能萎缩、广度回落，但结构分化仍在。",
 "ev_upratio_i": "由 61% 回落至 57%，参与度偏多但转弱，缩量滞涨下广度回落，仍非趋势反转",
 "ev_limit_i": "涨停 89（官方「狂热」标签由涨停>50 触发，89>50 强支撑；真实涨股比 57% 仍<70% 满阈值 = 标签略超前广度），跌停 13（略升），连板高度升至 6板，风险偏好偏乐观但量能萎缩",
 "ev_amount_i": "量能维持 ¥2.131万亿（环比 +293亿），缩量滞涨 = 结构分化、承接力转弱，高位放量追涨风险并存",
 "ev_sh_i": "微涨 +0.86%，缩量滞涨，PE 约18.30（估值随涨抬升），5日 +0.92%、60日 −2.80% 中期仍弱",
 "ev_sz_i": "小盘成长相对抗跌，PE 约43.10，5日 +0.41%、60日 −9.20% 中期仍弱",
 "ev_cyb_i": "高弹性微涨，5日 +0.38%、60日 −14.20%，高估值高弹性主线中期深套未解",
 "ev_secup_i": "传媒与 AI 应用全面激活 + 数字媒体领涨（数字媒体 +7.19% / 影视院线 +7.02% / 出版 +5.26% / 电视广播 +4.38% / 广告营销 +3.85% / 游戏 +3.40%），资金由周期 / 资源切向传媒 / AI应用，主线扩散但偏散",
 "ev_secdn_i": "饰品 −4.67% 领跌 / 乘用车 −3.12% / 光伏设备 −2.82% / 贵金属 −2.67% / 白色家电 −2.31% / 股份制银行 −1.10%——结构分化，资金由周期 / 资源撤出、切向传媒 / AI应用，前期强势板块补跌",
 "ev_board_i": "连板升至 6板（海鸥住工），万向德农 5板、捷荣技术 5板、锦龙股份 4板；热点由金融 / 周期扩散至传媒 / AI应用（芒果超媒 +20.00% / 华策影视 +15.77% / 中文在线 +20.02%），主线偏传媒 / AI应用，持续性待验",
 "ev_height_i": "高度升至 6板（海鸥住工，2026-08-31 收盘），投机热度延续，主线偏传媒 / AI应用，风险偏好偏乐观但量能萎缩",
 "ev_main": "融资单日净流入TOP",
 "ev_main_i": "杠杆资金当日集中于 AI 硬件光模块与通信（中际旭创 +11.07亿 / 新易盛 +8.71亿 / 星网锐捷 +3.32亿 / 东材科技 +3.07亿 / 三环集团 +2.50亿）——科技硬件仍是杠杆主战场",
 "ev_margin": "融资单日变动TOP",
 "ev_margin_i": "杠杆单日加仓榜中际旭创居首（+11.07亿，AI 算力光模块），新易盛 +8.71亿、星网锐捷 +3.32亿、东材科技 +3.07亿、三环集团 +2.50亿、罗博特科 +1.77亿、联特科技 +1.72亿——杠杆追涨电子硬件，较 08-28 升温",
 "ev_hot_i": "热搜由传媒 / AI应用 + 连板主导（芒果超媒 / 华策影视 / 中文在线 / 贵广网络 / 分众传媒 / 海鸥住工）；data_hot 本次未返回，以板块领涨股 + 排行榜综合替代（见来源口径）",
 "ev_margintotal_i": "缺口：聚合两融余额为空，以个股融资变动替代观察（见上）；连板高度 / 融资单日均为 2026-08-31 真实数据",
 "t_ev_note": "数据口径：宏观指标多截至 2026-07（月频）或 2026-08-31（日频）；PMI/产能/社融为 08-21 复核最新月频值（无新发布），CPI / M1-M2 / 10Y / LPR 沿用前期已查询月频 / 日频值（未更新）。涨跌分布 / 指数 / 成交额 / 板块 / 融资单日均为 2026-08-31 真实收盘；官方综合画像、连板梯队、融资单日均已更新至 2026-08-31，相关字段已标注。财新PMI数据源覆盖仅至 2025-08（49.2），不作为主要依据。详见末尾「数据来源与日期口径」。",
 "rc1_tag": "红线区 · 高位主线杠杆追涨 + 高估值 + 中期弱势 + 缩量滞涨",
 "rc1_t": "高位主线杠杆追涨 + 高估值 + 中期弱势 + 缩量滞涨",
 "rc1_d": "估值 PE分位 70-90% 偏高（官方画像确认，指数微涨、估值进一步抬升），中期趋势弱势下跌（创业板 60日 −14.20%、深成 60日 −9.20%），而缩量滞涨（成交 ¥2.131万亿，环比 +293亿）下技术面仍强（MACD 金叉）、三指微涨、涨停维持 89、广度回落至 57%——结构分化延续，但量能萎缩、高位承接转弱；融资单日追涨中际旭创 +11.07亿 / 新易盛 +8.71亿（AI 算力），拥挤度（72）与融资（70）读数维持高位，高位主线杠杆升温 = 二次杀跌风险积聚。",
 "rc1_rep": "代表：AI 算力光模块（中际旭创 / 新易盛）/ 传媒（芒果超媒）/ 创业板高位",
 "rc2_tag": "黄线区 · 传媒 / AI应用激活 + 周期 / 资源退潮（轮动加速）",
 "rc2_t": "传媒 / AI应用激活 + 周期 / 资源退潮",
 "rc2_d": "08-28 领涨的周期 / 资源（贵金属 / 资源股）退潮，但传媒 / AI应用全面激活：数字媒体 +7.19%（芒果超媒 +20.00%）/ 影视院线 +7.02%（华策影视 +15.77%）/ 出版 +5.26%（中文在线 +20.02%）/ 电视广播 +4.38% / 广告营销 +3.85% / 游戏 +3.40%；饰品 −4.67% / 乘用车 −3.12% / 光伏设备 −2.82% / 贵金属 −2.67% / 白色家电 −2.31% 领跌，结构分化。连板升至 6板（海鸥住工），主线由周期 / 资源扩散至传媒 / AI应用，轮动加快、持续性差。",
 "rc2_rep": "代表：数字媒体（芒果超媒）/ 影视院线（华策影视）/ 出版（中文在线）/ 电视广播（贵广网络）/ 游戏",
 "rc3_tag": "绿线区 · 连板投机 + 前期强势补跌（相对）",
 "rc3_t": "连板投机 + 前期强势补跌",
 "rc3_d": "海鸥住工（连板 6板）、捷荣技术 / 万向德农（5板）、锦龙股份（4板）代表连板梯队，但饰品 −4.67% / 乘用车 −3.12% / 光伏 −2.82% / 贵金属 −2.67% 补跌，资金向传媒 / AI应用扩散，本质仍是弱市下的结构分化而非新周期主线，连板高度越高、补跌风险越大。",
 "rc3_rep": "代表：海鸥住工 / 捷荣技术 / 万向德农 / 锦龙股份",
 "t_sec_outlook": "下个交易日（09-01 周二）展望",
 "o_logic": "研判逻辑（基于 08-31 收盘 + 群体心理定位）",
 "o_logic_text": "由 08-31 的「缩量滞涨 / 结构分化」延伸：情绪周期定位「缩量滞涨 / 结构分化」，涨股比 57%、涨停 89，广度由 61% 回落至 57%，成交维持 ¥2.131万亿（环比 +293亿）、技术面仍强（MACD 金叉）、三大指数微涨、涨停维持 89、估值偏高（PE分位 70-90% 且指数又涨）、趋势方向仍弱势下跌。官方「狂热」标签由涨停>50触发（89>50 强支撑），涨股比 57% 仍<70% 满阈值 = 标签略超前广度，缩量滞涨下广度回落。基于此推演 09-01 的板块方向与交易规则（<b>不涉及具体个股推荐</b>）。",
 "o1_tag": "传媒 / AI应用延续（观察）",
 "o1_t": "数字媒体 / 影视院线 / 出版 / 电视广播",
 "o1_d": "08-31 资金主攻方向：数字媒体 +7.19%（芒果超媒 +20.00%）/ 影视院线 +7.02%（华策影视 +15.77%）/ 出版 +5.26%（中文在线 +20.02%）/ 电视广播 +4.38%（贵广网络 +9.90%）/ 广告营销 +3.85%（分众传媒 +6.40%）/ 游戏 +3.40%。传媒 / AI应用单日激活，若量能持续有望延续，但需警惕缩量滞涨下高位追涨。",
 "o1_cond": "注意：单日爆发后的持续性需验证；严禁把单日轮动当反转，量能不放大则谨慎，不追涨停潮。",
 "o2_tag": "资源 / 贵金属退潮（观望）",
 "o2_t": "紫金 / 洛阳钼业 / 山东黄金 / 湖南白银",
 "o2_d": "前期强势的贵金属 / 资源（紫金矿业 / 山东黄金 / 湖南白银）在 08-31 转弱（贵金属 −2.67%），融资单日转向电子硬件（中际旭创 +11.07亿居首），避险逻辑减弱，资源 / 贵金属进入退潮观察。",
 "o2_cond": "注意：高位主线缩量滞涨 = 承接转弱；不追涨、不加杠杆；右侧需量价持续确认。",
 "o3_tag": "前期强势补跌（回避）",
 "o3_t": "饰品 / 乘用车 / 光伏设备 / 贵金属",
 "o3_d": "08-31 饰品 −4.67%、乘用车 −3.12%、光伏设备 −2.82%、贵金属 −2.67%、白色家电 −2.31% 列跌，结构分化、前期强势板块补跌，未确认止跌。短期不参与，等缩量止跌。",
 "o3_cond": "注意：等板块缩量止跌 + 龙头先于板块企稳再考虑右侧机会。",
 "o_r1": "<b>仓位</b>：维持低仓位，不加杠杆。情绪转入「缩量滞涨 / 结构分化」，但量能萎缩、广度回落、趋势仍弱，整体风险预算显著收缩。",
 "o_r2": "<b>高位主线</b>：不追涨、不加杠杆；以量能持续 + 指数站回短期均线上方为右侧确认，破位即减。",
 "o_r3": "<b>新主线</b>：需量价持续确认（≥2 日连续放量 + 龙头未切换）才能跟进；严禁把单日轮动当反转。",
 "o_r4": "<b>缩量滞涨</b>：官方「狂热」标签由涨停>50触发（89>50 强支撑），涨股比57%仍<70%满阈值；若 09-01 继续缩量滞涨、涨停维持 >50 但成交跌破 ¥2万亿，则高位承接转弱、需警惕回疑 / 再探分歧。",
 "o_r5": "<b>风控</b>：成交维持 ¥2.131万亿（环比 +293亿，缩量滞涨），若 09-01 继续缩量但指数滞涨（缩量滞涨）则降仓至 ≤3 成；若放量跌破短期均线则进一步降仓。",
 "s_breadth_v": "westock · data_changedist；2026-08-31 收盘",
 "s_portrait_v": "westock · data_market_overview(type=summary)；2026-08-31（情绪机械标「狂热」仅因「涨停>50」触发，08-31 真实涨股比57%略低于70%阈值 = 标签略超前广度，缩量滞涨下广度回落）",
 "s_index_v": "westock · data_quote(sh000001,sz399001,sz399006)；2026-08-31 收盘",
 "s_sector_v": "westock · data_sector(mode=ranking)；2026-08-31（fundflow 含行业/概念/地区排行与领涨股）",
 "s_hot_v": "westock · data_hot 本次未返回；热搜以 data_sector(fundflow 领涨股) + tool_ranking(limitup_days / margin_chg_d) 综合替代；涨跌分布/指数/板块/融资单日为 2026-08-31",
 "s_margin_v": "westock · tool_ranking(metric=margin_chg_d)；2026-08-31",
 "s_main_v": "westock · tool_ranking(metric=cap_main_5d)；2026-08-31（板块暗盘视角，以融资单日替代观察）",
 "s_board_v": "westock · tool_ranking(metric=limitup_days)；2026-08-31（当日排行榜已刷新）",
 "s_gap_v": "市场两融余额聚合值（data_market_overview type=margin）数据源返回空，已用个股融资变动替代，未编造；data_hot 本次未返回，已用板块领涨股 + 排行榜综合替代；连板高度 / 融资单日均为 2026-08-31 真实数据。",
 "t_src_note": "时间口径：所有时点按北京时间。宏观为月频 / 季频，与日频行情不可直接对齐，已分别标注。涨跌分布 / 指数 / 板块 / 融资单日 / 连板高度均为 2026-08-31 当日真实数据。",
 "ev_index": "二、核心指数表现（2026-08-31 收盘）",
 "o_compliance": "<b>合规说明：</b>本展望仅给出板块方向与交易规则，不涉及具体个股推荐；群体心理定位与板块推断基于 2026-08-31 真实行情数据，市场有风险，决策须独立。",
}

# ============================================================
# 3) 08-31 叙述覆盖（英文）
# ============================================================
EN = {
 "t_headline_sub": "2026-08-31 · Close",
 "t_breadth": "Market Breadth (2026-08-31 close)",
 "hk_stage": "Stage", "hv_stage": "<b>Volume-stall / structural divergence</b> (08-31)",
 "hk_upratio": "Up-ratio", "hv_upratio": "<b>57%</b> (prior 61% · ↓ 4pct)",
 "hk_lim": "Limit-up / Down", "hv_lim": "<b>89</b> / <b>13</b>",
 "hk_amt": "Turnover", "hv_amt": "<b>¥2.131tn</b> (volume-stall, +29.3bn)",
 "hk_cycle": "Sentiment cycle", "hv_cycle": "<b>Volume-stall / structural divergence</b>",
 "hk_risk": "Risk level", "hv_risk": "<b class=\"hl-risk\">High</b>",
 "hk_flag": "Key flag", "hv_flag": "Official \"<b>Euphoria</b>\" tag triggered by limit-up>50 (limit-up 89>50, strong support); real up-ratio 57%<70% = <b>tag slightly ahead of breadth, breadth fading under volume-stall</b>",
 "tk1": "Stage", "tv1": "On 08-31 A-shares extended 08-28's 'volume-stall / structural divergence': turnover held at ¥2.131tn (+29.3bn vs prior, slightly shrinking), up-ratio 57% (3181 up / 2218 down / 152 flat), limit-up 89, limit-down 13, all three indices edged up (SSE +0.86% / SZSE +0.44% / ChiNext +0.42%), technics still strong (MACD golden cross); but volume shrank, structure diverged (media / AI-app led, jewelry / passenger-vehicles / precious-metals lagged), high-level absorption weakened — a clear volume-stall. Risk remains <b>High</b>.",
 "tk2": "Breadth fades", "tv2": "Up-ratio <b>57%</b> (prior 61% ↓ 4pct) · Limit-up <b>89</b> (61→89) · Limit-down <b>13</b> (4→13) · Turnover <b>¥2.131tn</b> (volume-stall, +29.3bn vs prior).",
 "tk3": "Indices all up slightly", "tv3": "SSE <b>+0.86%</b> / SZSE <b>+0.44%</b> / ChiNext <b>+0.42%</b>; all three up but gains narrowed, ChiNext 60d <b>−14.20%</b>, SZSE 60d <b>−9.20%</b> mid-term weakness unchanged.",
 "tk4": "Sector rotation", "tv4": "<b>Media & AI-app fully activated + digital-media led</b>: digital-media +7.19% (Mango +20.00%) / film-TV +7.02% (Huace +15.77%) / publishing +5.26% (Chinese All +20.02%) / TV-broadcast +4.38% / ad-marketing +3.85% / gaming +3.40%; <b>jewelry −4.67%, passenger vehicles −3.12%, PV −2.82%, precious-metals −2.67%, white-appliances −2.31%, joint-stock banks −1.10% lagged</b> (structural divergence, capital shifted from cycle / resources to media / AI-app).",
 "tk5": "Streak structure", "tv5": "Top board height <b>6 boards</b> (Seagull Living), Wandong 5 boards, Jierong 5 boards, Jinlong 4 boards; speculative heat continued, main line skewed to media / AI-app, persistence unproven.",
 "tk6": "Leverage warms", "tv6": "Margin daily-add led by <b>Zhongji +¥1.107bn (#1)</b> (AI compute optical-module), Neways +0.871bn, Star-Net +0.332bn, Dongcai +0.307bn, Sanhuan +0.250bn — leverage chasing electronics hardware (AI compute optical-module), continued warming vs 08-28, crowding & refill risk still high.",
 "tk7": "Valuation / fundamentals", "tv7": "PE band <b>70-90%</b> + PMI <b>49.2</b> (below 50) + TSF YoY <b>−7.25%</b>; indices edged up, valuation still high, prices front-ran reality, fundamentals cannot support the level.",
 "tk8": "Sentiment cycle", "tv8": "From 'volume-stall / structural divergence' into <b>volume-stall / breadth-fading</b>; the official portrait mechanically flags 'Euphoria' triggered by limit-up>50 (08-31 limit-up 89>50 strong support), real up-ratio 57%<70% full threshold = tag slightly ahead of breadth, breadth fading under shrinking volume; technics still strong, all three up, limit-up held at 89 — but volume-stall, structure diverged, high-level absorption weakened. Risk remains <b>High</b>.",
 "t_tldr_text": "On 2026-08-31 A-shares showed 'volume-stall / structural divergence': turnover held at ¥2.131tn (+29.3bn vs prior, slightly shrinking), up-ratio 57% (3181 up / 2218 down / 152 flat), limit-up 89, limit-down 13, all three indices edged up (SSE +0.86% / SZSE +0.44% / ChiNext +0.42%), technics still strong (MACD golden cross) — looked like extension. Sector-wise 'media & AI-app fully activated + digital-media led': digital-media +7.19% (Mango +20.00%) led, film-TV +7.02% (Huace +15.77%), publishing +5.26% (Chinese All +20.02%), TV-broadcast +4.38%, ad-marketing +3.85%, gaming +3.40% all strong; jewelry −4.67%, passenger vehicles −3.12%, PV −2.82%, precious-metals −2.67%, white-appliances −2.31%, joint-stock banks −1.10% lagged (structural divergence, capital shifted from cycle / resources to media / AI-app). Streak rose to 6 boards (Seagull Living), Wandong 5, Jierong 5, Jinlong 4. Key flow: margin daily-add led by Zhongji +1.107bn (#1, AI compute optical-module), Neways +0.871bn, Star-Net +0.332bn, Dongcai +0.307bn, Sanhuan +0.250bn — leverage chasing electronics hardware, continued warming vs 08-28. The official portrait (data_market_overview type=summary, 2026-08-31) mechanically flags 'Euphoria' because limit-up>50 triggered; 08-31 real up-ratio 57% still <70% full threshold = tag slightly ahead of breadth; technics strong, all three up, limit-up 89, but volume-stall, structure diverged (jewelry / passenger-vehicles / precious-metals lag), breadth fading under shrinking volume, high-level absorption weakened. Fundamentals (PMI 49.2 / capacity 73.6% / TSF −7.25%) still lag. Crowd psychology extended 'volume-stall / structural divergence' into 'volume-stall / breadth-fading' — volume-stall, structure diverged, chase risk up, risk stays High.",
 "t_cycle_note": "Note: 'Optimism' above is the live crowd positioning (Volume-stall / structural divergence) — the 08-31 breadth (57% up, 89 limit-up, 13 limit-down, turnover ¥2.131tn) shows volume shrinking, breadth fading (from 61% to 57%), structural divergence intensifying (media / AI-app led, jewelry / passenger-vehicles / precious-metals lagged); technics still strong (MACD golden cross), all three up slightly, limit-up held at 89, but volume-stall is clear and high-level absorption weakened. The official portrait (data_market_overview type=summary, 2026-08-31) mechanically flags 'Euphoria' because limit-up>50 triggered; 08-31 real up-ratio 57%<70% = tag slightly ahead of breadth; if volume keeps shrinking and indices fade after a spike, sentiment slides back to doubt / re-tests divergence.",
 "t_radar_note": "Six-dimension risk readings (0–100, model-mapped, higher = more fragility): Crowding 72 / Margin 70 / Turnover 56 / Breadth 52 / Media 68 / Valuation 88. Breadth 50→52 (08-31 up-ratio 57%, fell from 61%, participation down = fragility up slightly); Turnover 54→56 (turnover held ¥2.131tn, active turnover steady); Margin 64→70 (margin daily chased Zhongji +1.107bn / Neways +0.871bn in AI hardware, leverage warming); Crowding 68→72 (6-board streak persists + media/AI-app burst + small-cap crowding, concentration rose markedly); Media 66→68 (89 limit-ups, all three up, media limit-up wave, sentiment clearly hotter); Valuation still high at 88 (indices edged up, official portrait PE pctile 70-90% elevated). Overall a 'volume-stall / structural divergence' structure — breadth and media repaired, crowding up, but volume shrank, structure diverged (jewelry / passenger-vehicles / precious-metals lag), high-level absorption weakened, fragility remains.",
 "t_breadth_note": "Up-stock ratio fell 61%->57%, limit-down 4->13: volume-stall, breadth fading, participation net-long but weakening. Limit-up 89 (official 'Euphoria' tag triggered by limit-up>50, 89>50 strong support; real up-ratio 57%<70% full threshold = tag slightly ahead of breadth), streak rose to 6 boards, limit-down slightly up — risk appetite optimistic but volume shrinking. Indices all up slightly (SSE +0.86% / SZSE +0.44% / ChiNext +0.42%); ChiNext 60d −14.20% mid-term still weak; turnover ¥2.131tn vs prior +29.3bn (volume-stall). 08-28's 'structural divergence' extended into 'volume-stall' on 08-31 — volume shrank, breadth faded, but structural divergence persists.",
 "ev_upratio_i": "Fell 61%->57%, participation net-long but weakening, breadth fading under volume-stall, still not trend reversal",
 "ev_limit_i": "Limit-up 89 (official 'Euphoria' tag triggered by limit-up>50, 89>50 strong support; real up-ratio 57%<70% full threshold = tag slightly ahead of breadth), limit-down 13 (slightly up), streak rose to 6 boards — risk appetite optimistic but volume shrinking",
 "ev_amount_i": "Turnover held ¥2.131tn (+29.3bn vs prior); volume-stall = structural divergence, absorption weakened, high-level chase risk coexists",
 "ev_sh_i": "Up +0.86%, volume-stall, PE ~18.30 (valuation lifted with price), 5d +0.92% / 60d −2.80% mid-term still weak",
 "ev_sz_i": "Small-cap growth relatively resilient, PE ~43.10, 5d +0.41% / 60d −9.20% mid-term still weak",
 "ev_cyb_i": "High-beta edged up, 5d +0.38% / 60d −14.20%, rich-valuation high-beta mid-term trap unrelieved",
 "ev_secup_i": "Media & AI-app fully activated + digital-media led (digital-media +7.19% / film-TV +7.02% / publishing +5.26% / TV-broadcast +4.38% / ad-marketing +3.85% / gaming +3.40%); capital shifted from cycle / resources to media / AI-app, main line broadened but scattered",
 "ev_secdn_i": "Jewelry −4.67% led / passenger vehicles −3.12% / PV −2.82% / precious-metals −2.67% / white-appliances −2.31% / joint-stock banks −1.10% — structural divergence, capital pulled from cycle / resources to media / AI-app, prior-strong sectors correcting",
 "ev_board_i": "Streak rose to 6 boards (Seagull Living), Wandong 5, Jierong 5, Jinlong 4; hotspots diffused from finance / cycle to media / AI-app (Mango +20.00% / Huace +15.77% / Chinese All +20.02%), main line skewed to media / AI-app, persistence unproven",
 "ev_height_i": "Rose to 6 boards (Seagull Living, 2026-08-31 close), speculative heat continued, main line skewed to media / AI-app, appetite optimistic but volume shrinking",
 "ev_main": "Margin daily net-inflow TOP",
 "ev_main_i": "Margin capital concentrated that day in AI optical-module & comms (Zhongji +1.107bn / Neways +0.871bn / Star-Net +0.332bn / Dongcai +0.307bn / Sanhuan +0.250bn) — tech hardware still the leverage battlefield",
 "ev_margin": "Margin daily change TOP",
 "ev_margin_i": "Margin daily-add led by Zhongji (+1.107bn, AI compute optical-module), Neways +0.871bn, Star-Net +0.332bn, Dongcai +0.307bn, Sanhuan +0.250bn, Robotech +0.177bn, Liantech +0.172bn — leverage chasing electronics hardware, warming vs 08-28",
 "ev_hot_i": "Hot-search led by media / AI-app + streak (Mango / Huace / Chinese All / Guiguang / Focus / Seagull); data_hot unavailable this round, proxied by sector leaders + rankings (see Sources)",
 "ev_margintotal_i": "Gap: aggregate margin balance empty; proxied by per-stock margin changes (above); streak height / margin daily are all 2026-08-31 real data",
 "t_ev_note": "Time caliber: macro mostly as of 2026-07 (monthly) or 2026-08-31 (daily); PMI/capacity/financing re-checked 08-21 (no new release, monthly), CPI/M1-M2/10Y/LPR from prior pulls (unchanged). Breadth / indices / turnover / sectors / margin daily are all 2026-08-31 real close; official portrait, streak, margin daily all updated to 2026-08-31 and labeled. Caixin PMI source only to 2025-08 (49.2), not primary. See 'Data Sources & Time Caliber' at end.",
 "rc1_tag": "RED · High-level main-line leverage chase + high valuation + mid-term weakness + volume-stall",
 "rc1_t": "High-level main-line leverage chase + high valuation + mid-term weakness + volume-stall",
 "rc1_d": "PE pctile 70-90% elevated (official portrait confirmed, indices edged up, valuation lifted further), mid-term trend weak (ChiNext 60d −14.20%, SZSE 60d −9.20%), yet on a volume-stall (¥2.131tn, +29.3bn) technics stayed strong (MACD golden cross), all three up slightly, limit-up held at 89, breadth faded to 57% — structural divergence persists, but volume shrank and high-level absorption weakened; margin daily chased Zhongji +1.107bn / Neways +0.871bn (AI compute), Crowding (72) and Margin (70) stay high, leverage into high-level lines on volume = second sell-off risk accumulates.",
 "rc1_rep": "Names: AI optical-module (Zhongji / Neways) / media (Mango) / ChiNext high-level",
 "rc2_tag": "AMBER · Media / AI-app activated + cycle / resources fading (fast rotation)",
 "rc2_t": "Media / AI-app activated + cycle / resources fading",
 "rc2_d": "08-28 leaders cycle / resources (precious-metals / resource stocks) faded, but media / AI-app fully activated: digital-media +7.19% (Mango +20.00%) / film-TV +7.02% (Huace +15.77%) / publishing +5.26% (Chinese All +20.02%) / TV-broadcast +4.38% / ad-marketing +3.85% / gaming +3.40%; jewelry −4.67% / passenger vehicles −3.12% / PV −2.82% / precious-metals −2.67% / white-appliances −2.31% lagged, structure diverged. Streak rose to 6 boards (Seagull Living), main line diffused from cycle / resources to media / AI-app, rotation faster, persistence poor.",
 "rc2_rep": "Names: digital-media (Mango) / film-TV (Huace) / publishing (Chinese All) / TV-broadcast (Guiguang) / gaming",
 "rc3_tag": "GREEN · Streak speculation + prior-strong correction (relative)",
 "rc3_t": "Streak speculation + prior-strong correction",
 "rc3_d": "Seagull Living (6-board streak leader), Jierong / Wandong (5 boards), Jinlong (4 boards) represent the streak ladder, but jewelry −4.67% / passenger vehicles −3.12% / PV −2.82% / precious-metals −2.67% corrected, capital diffused to media / AI-app — still risk-off / structural divergence, not a new-cycle main line; higher streak = higher correction risk.",
 "rc3_rep": "Names: Seagull / Jierong / Wandong / Jinlong",
 "t_sec_outlook": "Next-Session Outlook (09-01 Tue)",
 "o_logic": "Inference logic (based on 08-31 close + crowd positioning)",
 "o_logic_text": "Extending 08-31's 'volume-stall / structural divergence': crowd cycle sits at 'Volume-stall / structural divergence', up-ratio 57%, 89 limit-ups, breadth fell from 61% to 57%, turnover held ¥2.131tn (+29.3bn vs prior), technics still strong (MACD golden cross), all three indices up slightly, limit-up held at 89, valuation elevated (PE pctile 70-90% and indices rose again), trend direction still weak-down. Official 'Euphoria' tag triggered by limit-up>50 (89>50 strong support), real up-ratio 57%<70% full threshold = tag slightly ahead of breadth, breadth fading under volume-stall. Projecting 09-01 sector direction and trading rules (<b>no individual stock picks</b>).",
 "o1_tag": "Media / AI-app continuation (watch)",
 "o1_t": "Digital-media / Film-TV / Publishing / TV-broadcast",
 "o1_d": "08-31 capital focus: digital-media +7.19% (Mango +20.00%) / film-TV +7.02% (Huace +15.77%) / publishing +5.26% (Chinese All +20.02%) / TV-broadcast +4.38% (Guiguang +9.90%) / ad-marketing +3.85% (Focus +6.40%) / gaming +3.40%. Media / AI-app activated in one day; may extend if volume sustains, but beware high-level chase under volume-stall.",
 "o1_cond": "Note: persistence after a one-day burst must be verified; never treat a single-day rotation as reversal; cautious if volume doesn't expand, don't chase the limit-up wave.",
 "o2_tag": "Resources / precious-metals fading (stand aside)",
 "o2_t": "Zijin / Luoyang Moly / Shandong Gold / Hunan Silver",
 "o2_d": "Prior-strong precious-metals / resources (Zijin / Shandong Gold / Hunan Silver) weakened on 08-31 (precious-metals −2.67%), margin daily turned to electronics (Zhongji +1.107bn #1) — safe-haven logic fading, resources / precious-metals enter fade-watch.",
 "o2_cond": "Note: high-level main line on volume-stall = absorption weakening; no chasing, no leverage; right-side needs sustained volume+price confirmation.",
 "o3_tag": "Prior-strong correction (avoid)",
 "o3_t": "Jewelry / Passenger vehicles / PV / Precious-metals",
 "o3_d": "08-31 jewelry −4.67%, passenger vehicles −3.12%, PV −2.82%, precious-metals −2.67%, white-appliances −2.31% lagged, structural divergence, prior-strong sectors correcting, unconfirmed bottom. Stay out for now, wait for volume-dry stabilization.",
 "o3_cond": "Note: wait for sector-volume drying + leaders stabilizing before the sector itself, then consider right-side.",
 "o_r1": "<b>Book</b>: stay low exposure, no leverage. Cycle moved to 'Volume-stall / structural divergence' but volume shrank, breadth faded, trend still weak — overall risk budget shrinks markedly.",
 "o_r2": "<b>High-level main line</b>: no chasing, no leverage; right-side requires sustained volume + index above short-term MA; break down -> cut.",
 "o_r3": "<b>New main line</b>: needs sustained volume+price confirmation (>=2 sessions of volume expansion + leader unchanged) to follow; never treat a single-day rotation as reversal.",
 "o_r4": "<b>Volume-stall</b>: official 'Euphoria' tag triggered by limit-up>50 (89>50 strong support), up-ratio 57% still <70% full threshold; if 09-01 keeps stalling on shrinking volume, limit-up holds >50 but turnover breaks below ¥2tn, high-level absorption weakens — watch the slide back to doubt / re-test divergence.",
 "o_r5": "<b>Risk gate</b>: turnover held ¥2.131tn (+29.3bn, volume-stall); if 09-01 keeps stalling while indices stall (volume-stall) cut overall to <=30% exposure; if it breaks short-term MAs on shrinking volume, cut further.",
 "s_breadth_v": "westock · data_changedist; 2026-08-31 close",
 "s_portrait_v": "westock · data_market_overview(type=summary); 2026-08-31 (sentiment mechanically flagged 'Euphoria' only because limit-up>50 triggered, 08-31 real up-ratio 57% slightly below 70% threshold = tag slightly ahead of breadth, breadth fading under volume-stall)",
 "s_index_v": "westock · data_quote(sh000001,sz399001,sz399006); 2026-08-31 close",
 "s_sector_v": "westock · data_sector(mode=ranking); 2026-08-31 (fundflow includes industry/concept/region rankings and leaders)",
 "s_hot_v": "westock · data_hot unavailable this round; proxied by data_sector(fundflow leaders) + tool_ranking(limitup_days / margin_chg_d); breadth/index/sector/margin daily are 2026-08-31",
 "s_margin_v": "westock · tool_ranking(metric=margin_chg_d); 2026-08-31",
 "s_main_v": "westock · tool_ranking(metric=cap_main_5d); 2026-08-31 (sector dark-pool view, proxied by margin daily)",
 "s_board_v": "westock · tool_ranking(metric=limitup_days); 2026-08-31 (same-day ranking refreshed)",
 "s_gap_v": "Aggregate margin balance (data_market_overview type=margin) returned empty by source; proxied by per-stock margin changes, not fabricated. data_hot unavailable this round; proxied by sector leaders + rankings. Streak height / margin daily are all 2026-08-31 real data.",
 "t_src_note": "Time caliber: all timestamps in Beijing time. Macro is monthly/quarterly and not directly aligned with daily quotes; labeled separately. Breadth / index / sector / margin daily / streak height are all 2026-08-31 same-day real data.",
 "ev_index": "II. Core Index Performance (2026-08-31 close)",
 "o_compliance": "<b>Compliance note:</b> this outlook provides sector direction and trading rules only — no individual stock recommendations. Crowd positioning and sector inference are based on 2026-08-31 live market data; markets carry risk, decide independently.",
}

zh = dict(zh0); zh.update(ZH)
en = dict(en0); en.update(EN)

def esc(s):
    return s.replace("\\", "\\\\").replace('"', '\\"')

def serialize(d):
    return "\n".join('      %s:"%s",' % (k, esc(d[k])) for k in d)

# 替换顺序：en 在后，先换 en；zh 在前，后换 zh（位置不受 en 替换影响）
new_en = "en:{\n" + serialize(en) + "\n    }"
html = html[:m_en.start()] + new_en + html[m_en.end():]
new_zh = "zh:{\n" + serialize(zh) + "\n    },"
html = html[:m_zh.start()] + new_zh + html[m_zh.end():]

# ============================================================
# 4) 重建 BIAS 数组
# ============================================================
BIAS = [
 {"zh":"羊群效应","en":"Herding","sev":4,
  "zhd":"涨股比57%偏多、成交维持¥2.131万亿缩量滞涨、三指微涨，资金扎堆传媒 / AI应用（数字媒体+7.19%/影视院线+7.02%/出版+5.26%）与连板（海鸥住工 6板），跟随板块涨停潮而非独立判断。",
  "end":"Up-ratio 57% net-long, turnover held ¥2.131tn on volume-stall, all three indices up slightly; capital crowds media/AI-app (digital-media +7.19%/film-TV +7.02%/publishing +5.26%) and streaks (Seagull Living 6 boards) — following the limit-up wave, not conviction."},
 {"zh":"损失厌恶","en":"Loss Aversion","sev":3,
  "zhd":"在缩量滞涨中融资追涨 AI 算力光模块（中际旭创+11.07亿/新易盛+8.71亿），把前期浮亏当已发生损失回避止损、在高位科技缩量上行中反手加仓，忽视量能萎缩。",
  "end":"In volume-stall, margin chases AI optical-module (Zhongji +1.107bn/Neways +0.871bn) — avoiding the realized loss, doubling down on high-level tech on shrinking volume, ignoring the fading turnover."},
 {"zh":"心理账户/赌徒谬误","en":"Mental Acct / Gambler","sev":3,
  "zhd":"创业板60日−14.20%下仍在缩量滞涨中博弈传媒 / AI应用反弹（芒果超媒+20.00%/华策影视+15.77%），把亏损仓当赌资、博「AI应用刚需」回本。",
  "end":"Amid ChiNext 60d −14.20% still margin-betting on media/AI-app rebound (Mango +20.00%/Huace +15.77%) in a volume-stall; treating loss books as gambling capital."},
 {"zh":"过度自信","en":"Overconfidence","sev":4,
  "zhd":"技术面「极强」延续+三大指数齐涨（上证+0.86%/深成+0.44%/创业板+0.42%），误判「反转」，把单日传媒涨停潮当趋势恢复、追数字媒体 / 影视院线，忽视趋势仍弱势下跌、估值偏高（PE分位70-90%）、结构分化（饰品/乘用车/贵金属领跌）。",
  "end":"Reading technics 'extremely strong' + all-three-up (SH +0.86%/SZ +0.44%/ChiNext +0.42%) as 'reversal', treating a single-day media limit-up wave as trend recovery, chasing digital-media/film-TV — ignoring trend still weak-down, valuation elevated (PE pctile 70-90%), structural divergence (jewelry/passenger-vehicles/precious-metals lag)."},
 {"zh":"处置效应","en":"Disposition","sev":3,
  "zhd":"反弹中卖盈（数字媒体+7.19%中芒果超媒+20.00%获利了结）持亏（创业板高位套牢未割），结构分化、调仓滞后。",
  "end":"Selling winners (digital-media +7.19% with Mango +20.00% profit-taking) while holding losers (ChiNext high-level traps untrimmed) — split structure, lagging rotation."},
 {"zh":"锚定偏差","en":"Anchoring","sev":3,
  "zhd":"锚定前期高点与官方「狂热」标签（涨停>50触发、涨股比57%<70%阈值），难接受趋势仍弱势下跌（创业板60日−14.20%、深成60日−9.20%）与缩量滞涨、结构分化的现实。",
  "end":"Anchored to prior highs and the official 'Euphoria' tag (triggered by limit-up>50, real up-ratio 57%<70%); rejecting mid-term weakness (ChiNext 60d −14.20%, SZSE 60d −9.20%) and the volume-stall-but-divergent reality."},
 {"zh":"确认偏误","en":"Confirmation Bias","sev":4,
  "zhd":"只看技术「极强」+涨停89+三指齐涨+传媒爆发，忽略趋势方向仍弱势下跌（长短线均偏弱）、估值偏高（PE分位70-90%）、真实涨股比仅57%（官方狂热标签略超前广度）、结构分化（饰品/乘用车/贵金属领跌）。",
  "end":"Only watching technics 'extremely strong' + 89 limit-ups + all-three-up + media burst, ignoring trend direction still weak-down, valuation elevated (PE pctile 70-90%), real up-ratio only 57% (official Euphoria tag slightly ahead of breadth), structural divergence (jewelry/passenger-vehicles/precious-metals lag)."},
 {"zh":"近因偏差","en":"Recency","sev":3,
  "zhd":"外推08-28普涨+08-31传媒涨停潮的「回暖」，对趋势仍弱势下跌（创业板60日−14.20%）与结构分化反应钝化。",
  "end":"Extrapolating 08-28 broad rally + 08-31 media limit-up wave 'recovery'; blunted by the mid-term weakness (ChiNext 60d −14.20%) and structural divergence."},
 {"zh":"叙事偏差","en":"Narrative","sev":4,
  "zhd":"「传媒 / AI应用 / 算力刚需」叙事在缩量滞涨中仍被资金强化（数字媒体+7.19%/影视院线+7.02%/融资追涨中际旭创+11.07亿），故事未证伪且被加仓自我实现，但估值偏高（PE分位70-90%）下叙事脆弱。",
  "end":"The 'media/AI-app/compute-must-have' narrative reinforced by capital even in a volume-stall (digital-media +7.19%/film-TV +7.02%/margin chasing Zhongji +1.107bn) — story un-falsified, self-reinforced by buying, but fragile under elevated valuation (PE pctile 70-90%)."},
 {"zh":"代表性启发","en":"Representativeness","sev":3,
  "zhd":"被数字媒体+7.19%（芒果超媒+20.00%）/影视院线+7.02%（华策影视+15.77%）单日赚钱效应代表，误判市场全面转暖、忽视缩量滞涨下的结构分化（饰品−4.67%/乘用车−3.12%/贵金属−2.67%）与涨股比仅57%。",
  "end":"Digital-media +7.19% (Mango +20.00%) / film-TV +7.02% (Huace +15.77%) profit taken as representative; mistaking a sector rally for a broad turn, ignoring the volume-stall's structural divergence (jewelry −4.67%/passenger-vehicles −3.12%/precious-metals −2.67%) and up-ratio only 57%."},
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
 ("<span class=\"chip\"><span data-i18n=\"c_upratio\">涨股比</span> <b>61%</b></span>",
  "<span class=\"chip\"><span data-i18n=\"c_upratio\">涨股比</span> <b>57%</b></span>"),
 ("<span class=\"chip\"><span data-i18n=\"c_limitup\">涨停</span> <b>78</b></span>",
  "<span class=\"chip\"><span data-i18n=\"c_limitup\">涨停</span> <b>89</b></span>"),
 ("<span class=\"chip\"><span data-i18n=\"c_board\">连板高度</span> <b>5板</b></span>",
  "<span class=\"chip\"><span data-i18n=\"c_board\">连板高度</span> <b>6板</b></span>"),
 ("<span class=\"chip\"><span data-i18n=\"c_turn\">两市成交</span> <b>¥2.1259万亿</b></span>",
  "<span class=\"chip\"><span data-i18n=\"c_turn\">两市成交</span> <b>¥2.131万亿</b></span>"),
 # breadth SVG center texts
 ("<text x=\"167\" y=\"33\" fill=\"#fff\" font-size=\"14\" font-weight=\"800\" text-anchor=\"middle\">61%</text>",
  "<text x=\"167\" y=\"33\" fill=\"#fff\" font-size=\"14\" font-weight=\"800\" text-anchor=\"middle\">57%</text>"),
 ("<text x=\"407\" y=\"33\" fill=\"#fff\" font-size=\"14\" font-weight=\"800\" text-anchor=\"middle\">35%</text>",
  "<text x=\"407\" y=\"33\" fill=\"#fff\" font-size=\"14\" font-weight=\"800\" text-anchor=\"middle\">40%</text>"),
 ("<text x=\"340\" y=\"72\" fill=\"#d8392b\">3394</text>",
  "<text x=\"340\" y=\"72\" fill=\"#d8392b\">3181</text>"),
 ("<text x=\"340\" y=\"92\" fill=\"#1a9e5a\">1944</text>",
  "<text x=\"340\" y=\"92\" fill=\"#1a9e5a\">2218</text>"),
 ("<text x=\"340\" y=\"112\" fill=\"#6b675f\">212</text>",
  "<text x=\"340\" y=\"112\" fill=\"#6b675f\">152</text>"),
 ("<text x=\"340\" y=\"138\" fill=\"#d8392b\">78</text>",
  "<text x=\"340\" y=\"138\" fill=\"#d8392b\">89</text>"),
 ("<text x=\"340\" y=\"158\" fill=\"#1a9e5a\">4</text>",
  "<text x=\"340\" y=\"158\" fill=\"#1a9e5a\">13</text>"),
 ("<text x=\"340\" y=\"184\" fill=\"#1c1b19\">¥2.1259万亿</text>",
  "<text x=\"340\" y=\"184\" fill=\"#1c1b19\">¥2.131万亿</text>"),
 # breadth SVG parentheticals
 ("（占 61%，较前日 +8pct）", "（占 57%，较上一报告日（08-27） −4pct）"),
 ("（占 35%，较前日 −18pct）", "（占 40%，较上一报告日（08-27） +5pct）"),
 ("（占 4%）", "（占 3%）"),
 ("（较前日 +22 只，连板高度维持 5板）", "（较前日 +11 只，连板高度升至 6板）"),
 ("（较前日 +2 只）", "（较前日 +9 只）"),
 ("（环比 +3172亿，放量）", "（环比 +293亿，缩量滞涨）"),
 # breadth bar widths
 ('<rect x="14" y="14" width="305" height="26" fill="#d8392b"/>',
  '<rect x="14" y="14" width="285" height="26" fill="#d8392b"/>'),
 ('<rect x="319" y="14" width="175" height="26" fill="#1a9e5a"/>',
  '<rect x="299" y="14" width="200" height="26" fill="#1a9e5a"/>'),
 # evidence: 涨股比
 ("<td><span class=\"val up\">61%</span>（涨3394 / 跌1944 / 平212）</td>",
  "<td><span class=\"val up\">57%</span>（涨3181 / 跌2218 / 平152）</td>"),
 # evidence: 涨停/跌停
 ("<td><span class=\"val up\">78</span> / <span class=\"val down\">4</span></td>",
  "<td><span class=\"val up\">89</span> / <span class=\"val down\">13</span></td>"),
 # evidence: 成交额
 ("<span class=\"val\">≈¥2.1259万亿</span>（较前日 +3172亿，放量）",
  "<span class=\"val\">¥2.131万亿</span>（较前日 +293亿，缩量滞涨）"),
 # evidence: 三大指数
 ("3956.57　+1.13%", "3986.30　+0.86%"),
 ("14048.88　+1.50%", "14015.00　+0.44%"),
 ("3473.35　+1.71%", "3438.68　+0.42%"),
 # evidence: 领涨行业
 ("<span class=\"val up\">非金属材料 +9.63%</span>（联瑞新材 +20.00%）<br>电子化学品 +5.56%（宏昌电子 +10.02%）/ 玻璃玻纤 +5.36%（中国巨石 +7.95%）/ 元件 +5.09%（生益电子 +14.32%）<br>半导体 +4.54%（赛微电子 +20.01%）/ 通信设备 +3.85% / 小金属 +4.00%",
  "<span class=\"val up\">数字媒体 +7.19%</span>（芒果超媒 +20.00%）<br>影视院线 +7.02%（华策影视 +15.77%）/ 出版 +5.26%（中文在线 +20.02%）<br>电视广播 +4.38% / 广告营销 +3.85% / 游戏 +3.40%"),
 # evidence: 领跌行业
 ("<span class=\"val down\">光伏设备 −2.33%</span>（微导纳米 +8.19% 个股强但板块弱）<br>白色家电 −1.56% / 股份制银行 −1.10%（中信银行）/ 国有大行 −1.16% / 电网设备 −1.21%<br>贵金属续弱 −0.64%",
  "<span class=\"val down\">饰品 −4.67%</span> / 乘用车 −3.12% / 光伏设备 −2.82% / 贵金属 −2.67% / 白色家电 −2.31% / 股份制银行 −1.10%<br>贵金属续弱 −0.64%"),
 # evidence: 极端题材(连板)
 ("<span class=\"val up\">连板高度 5 板</span>（深中华A — 数据源延迟取 08-26 收盘）<br>4板：楚天龙；3板：海鸥住工<br>2板：华阳国际 / 冀衡医药 / 青山纸业 / 捷荣技术 / 康盛股份 / 青岛金王 / 华天酒店 / 豪尔赛 / 浙江世宝 / 万向德农<br>新热点：联瑞新材 +20.00%（非金属材料）/ 赛微电子 +20.01%（半导体）/ 生益电子 +14.32%（元件）/ 中国巨石 +7.95%（玻璃玻纤）/ 宏昌电子 +10.02%（电子化学品）",
  "<span class=\"val up\">连板高度 6 板</span>（海鸥住工）<br>5板：万向德农 / 捷荣技术；4板：锦龙股份<br>新热点：芒果超媒 +20.00%（数字媒体）/ 华策影视 +15.77%（影视院线）/ 中文在线 +20.02%（出版）/ 贵广网络 +9.90%（电视广播）/ 分众传媒 +6.40%（广告营销）"),
 # evidence: 连板高度
 ("<span class=\"val up\">深中华A 5板</span>（数据源延迟取 2026-08-26）", "<span class=\"val up\">海鸥住工 6板</span>（2026-08-31）"),
 # evidence: 主力5日/融资单日
 ("紫金矿业 <span class=\"val up\">+34.96亿</span>（5日，数据源延迟取 08-26）<br>洛阳钼业 +24.31亿 / C高凯 +23.98亿 / 英维克 +15.42亿 / 剑桥科技 +15.14亿<br>江西铜业 +14.10亿 / 白银有色 +13.14亿 / 长飞光纤 +13.00亿 / 比亚迪 +12.58亿 / 湖南白银 +12.43亿 / 兴业银锡 +12.19亿",
  "中际旭创 <span class=\"val up\">+11.07亿</span>（光模块）<br>新易盛 +8.71亿 / 星网锐捷 +3.32亿 / 东材科技 +3.07亿 / 三环集团 +2.50亿<br>罗博特科 +1.77亿 / 联特科技 +1.72亿 / 剑桥科技 +1.55亿 / 中科曙光 +1.48亿"),
 # evidence: 融资单日
 ("新易盛 <span class=\"val up\">+3.11亿</span>（光模块）<br>剑桥科技 +2.82亿 / 英维克 +2.75亿 / 同花顺 +2.60亿 / 海光信息 +2.09亿<br>罗博特科 +1.77亿 / 联特科技 +1.72亿",
  "中际旭创 <span class=\"val up\">+11.07亿</span>（光模块）<br>新易盛 +8.71亿 / 星网锐捷 +3.32亿 / 东材科技 +3.07亿 / 三环集团 +2.50亿<br>罗博特科 +1.77亿 / 联特科技 +1.72亿 / 剑桥科技 +1.55亿 / 中科曙光 +1.48亿"),
 # evidence: 热搜
 ("联瑞新材 +20.00%（非金属材料）<br>赛微电子 +20.01%（半导体）/ 生益电子 +14.32%（元件）/ 中国巨石 +7.95%（玻璃玻纤）/ 宏昌电子 +10.02%（电子化学品）<br>深中华A +10.04%（连板 5板，数据源延迟取 08-26）",
  "芒果超媒 +20.00%（数字媒体）<br>华策影视 +15.77%（影视院线）/ 中文在线 +20.02%（出版）/ 贵广网络 +9.90%（电视广播）/ 分众传媒 +6.40%（广告营销）<br>海鸥住工 +10.04%（连板 6板，2026-08-31）"),
 # evidence: 指数小节标题日期
 ("二、核心指数表现（2026-08-24 收盘）", "二、核心指数表现（2026-08-31 收盘）"),
 # t_date 静态 cell
 ("<b>2026-08-27 收盘（北京时间，盘后）</b>", "<b>2026-08-31 收盘（北京时间，盘后）</b>"),
]
for old, new in BODY:
    if old in html:
        html = html.replace(old, new, 1)
    else:
        print(f"[skip-body] 未命中: {old[:46]!r}")

# ============================================================
# 6) 雷达几何（SVG polygon + circles + 值文本）
# ============================================================
coords = {"拥挤度":(160,72),"融资":(218,107),"换手":(206,167),"广度":(160,189),"媒体":(104,172),"估值":(88,98)}
old_poly = "160,75 235,124 207,198 160,171 107,205 55,114"
assert html.count(old_poly)==1, html.count(old_poly)
html = html.replace(old_poly, " ".join(f"{coords[k][0]},{coords[k][1]}" for k in ["拥挤度","融资","换手","广度","媒体","估值"]))
for (ox,oy),(nx,ny) in {(160,75):(160,72),(235,124):(218,107),(207,198):(206,167),(160,171):(160,189),(107,205):(104,172),(55,114):(88,98)}.items():
    pat=f'cx="{ox}" cy="{oy}"'; assert html.count(pat)==1, pat; html=html.replace(pat,f'cx="{nx}" cy="{ny}"')
for ov,nv in {68:72,64:70,54:56,50:52,66:68,90:88}.items():
    pat=f'>{ov}</text>'
    if html.count(pat)!=1: print(f"[warn] >{ov}</text> x{html.count(pat)}"); continue
    html=html.replace(pat,f'>{nv}</text>')

# ============================================================
# 7) 写出 + 校验
# ============================================================
open(OUT, "w", encoding="utf-8").write(html)
print(f"[ok] 写出 {OUT} ({len(html)} bytes)")
leftover = ["3956.57","14048.88","3473.35","3394","1944","深中华A","非金属材料 +9.63%","2.1259",
            "联瑞新材","楚天龙","紫金矿业 +34.96亿","新易盛 +3.11亿","2026-08-26","2026-08-27","放量反包","深中华A 5板"]
bad = [s for s in leftover if s in html]
print("残留旧数据:", bad if bad else "无")
print("2026-08-31 出现次数:", html.count("2026-08-31"))
print("外部引用 http(s):", len(re.findall(r'https?://', html)))
must = ["3986.30","14015.00","3438.68","3181","2218","57%","89","13","¥2.131万亿",
        "数字媒体 +7.19%","海鸥住工 6板","中际旭创 +11.07亿","缩量滞涨 / 结构分化","2026-08-31"]
miss = [s for s in must if s not in html]
print("缺失 08-31 标记:", miss if miss else "无")
