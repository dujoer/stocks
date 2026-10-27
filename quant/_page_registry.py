# -*- coding: utf-8 -*-
"""全站页面族登记表 —— 每日更新覆盖度自检的唯一权威来源。

字段：
  key      : 族标识
  label    : 中文名
  patterns : 相对 web/ 的 glob 列表（fnmatch；不支持 **，需要就写多条）
  entry    : 导航入口页（相对 web/），须存在
  script   : 产出脚本（相对仓库根，多个用 ; 分隔），None=手工
  freq     : daily（每交易日必更）/ on_demand / quarterly / ad_hoc
  dated    : True=该族按日归档（文件名含日期），False=单页滚动更新
  start    : 该族首个应有日期（yyyymmdd），早于此日不计缺口
  date_re  : 从文件名提取日期的正则（组1）
  need     : 依赖的上游数据（说明性）

维护约定：新增页面必须在此登记，否则 _coverage_check.py 报 UNREGISTERED。
"""
import os

FAMILIES = [
    dict(key='portal', label='首页门户', patterns=['../index.html'],
         entry=None, script='build_portal.py', freq='daily', dated=False,
         start=None, date_re=None, need='各模块页生成后重跑'),

    # 历史归档：09-04 后 build_dashboards 改为只出 market/index.html（单页滚动），
    # daily_overview_{DATE}.html 不再新增。保留旧档供回溯，不参与缺口判定。
    dict(key='market_daily', label='每日总览历史归档（已停更）',
         patterns=['market/daily_overview_*.html'],
         entry='market/index.html', script=None, freq='ad_hoc',
         dated=False, start=None, date_re=r'(\d{4}-\d{2}-\d{2})',
         need='09-04 后已并入 market/index.html，不再新增'),

    dict(key='market_status', label='市场状态报告（活跃）',
         patterns=['market/status_*.html'],
         entry='market/index.html', script='build_dashboards.py', freq='daily',
         dated=True, start='20260817', date_re=r'(\d{4}-\d{2}-\d{2})',
         need='build_dashboards 状态段'),

    dict(key='market_misc', label='每日总览入口/游资/周报',
         patterns=['market/index.html', 'market/hotmoney.html',
                   'market/limitup_weekly_*.html'],
         entry='market/index.html', script='build_dashboards.py', freq='daily',
         dated=False, start=None, date_re=None,
         need='index/hotmoney 每日；limitup_weekly 为一次性产出'),

    dict(key='lhb', label='龙虎榜归档', patterns=['lhb/lhb_*.html'],
         entry='lhb/lhb.html', script='build_dashboards.py', freq='daily',
         dated=True, start='20260817', date_re=r'(\d{4}-\d{2}-\d{2})',
         need='lhb 5 接口 + 4 分项 + lhb_detail + build_lhb_enriched'),

    dict(key='lhb_entry', label='龙虎榜入口/归档页',
         patterns=['lhb/lhb.html', 'lhb/index.html', 'lhb/archive.html'],
         entry='lhb/lhb.html', script='build_dashboards.py', freq='daily',
         dated=False, start=None, date_re=None, need='同 lhb'),

    dict(key='cross_section', label='全市场横截面（数据能力展示）',
         patterns=['cross_section/index.html', 'cross_section/cross_2*.html'],
         entry='cross_section/index.html', script='build_cross_section.py',
         freq='daily', dated=True, start='20260930',
         date_re=r'cross_(\d{8})\.html',
         need='读 hub/{DATE}.json（统一数据底座，**全市场** quotes+flow，不联网）；'
              '★只演示数据能力与字段覆盖，示例打分**未过样本外检验**，不构成选股结论'),

    dict(key='cold_sector', label='冷门行业榜（两年未主升·仅陈述事实）',
         patterns=['cold_sector/index.html', 'cold_sector/cold_2*.html'],
         entry='cold_sector/index.html', script='build_cold_sector.py',
         freq='weekly', dated=True, start='20260930',
         date_re=r'cold_(\d{8})\.html',
         need='引擎 _cold_sector.py（等权行业指数，两年日K底座 _long_kline.json）；'
              '★只陈述「哪些行业两年零主升」这一已发生事实，**不产生任何个股推荐**（闸门未通过），'
              '页面禁止出现买入/目标价/买点语境'),

    dict(key='sector', label='板块强度日页',
         patterns=['sector/sector-strength-2*.html'],
         entry='sector/index.html', script='run_daily_sector.py', freq='daily',
         dated=True, start='20260827', date_re=r'(\d{8})',
         need='data_sector industry+concept 快照（前瞻累积，漏跑永久断档）'),

    dict(key='sector_entry', label='板块强度入口/趋势',
         patterns=['sector/index.html', 'sector/trend.html',
                   'sector/sector-strength-trend.html'],
         entry='sector/index.html', script='run_daily_sector.py', freq='daily',
         dated=False, start=None, date_re=None, need='同 sector'),
    dict(key='sector_heatmap', label='板块强度热力图（交互）',
         patterns=['sector/heatmap.html'],
         entry='sector/index.html', script='build_sector_heatmap.py', freq='daily',
         dated=False, start=None, date_re=None,
         need='sector_daily/*.json（读真实快照编排可视化，不生成统计数字）'),

    dict(key='statement', label='实盘交割单复盘 / 退出规则回放（脱敏公开版）',
         patterns=['statement/index.html', 'statement/exit-replay.html'],
         entry='statement/index.html',
         script='build_statement_report.py --public; build_exit_replay.py --public',
         freq='manual', dated=False, start=None, date_re=None,
         need='quant/_stmt_analysis.json（analyze_statement.py 手工导入交割单产出；'
              '脱敏版不进日更链，避免把真实金额写进公开站点）'),

    dict(key='exec', label='高管增减持', patterns=['exec/*.html'],
         entry='exec/index.html', script='gen_exec.py;build_exec.py', freq='daily',
         dated=False, start=None, date_re=None,
         need='manager_sharechg（30 日滚动窗口，单页滚动更新）'),

    dict(key='block', label='大宗交易归档', patterns=['block/block_*.html'],
         entry='block/index.html', script='build_block.py', freq='daily',
         dated=True, start='20260817', date_re=r'(\d{4}-\d{2}-\d{2})',
         need='block_chg/{DATE}.json'),

    dict(key='block_entry', label='大宗交易入口/归档页',
         patterns=['block/index.html', 'block/block.html', 'block/archive.html',
                   'block/stocks.html'],
         entry='block/index.html', script='build_block.py', freq='daily',
         dated=False, start=None, date_re=None, need='同 block'),

    dict(key='psychology', label='群体心理雷达明细',
         patterns=['psychology/crowd-psychology-risk-radar-*.html'],
         entry='psychology/index.html', script='market-trend/_build_*.py',
         freq='daily', dated=True, start='20260817', date_re=r'(\d{8})',
         need='market_overview + limitup + board_hot + sector 当日快照'),

    dict(key='dragon', label='龙道诀 · 情绪周期择时台',
         patterns=['dragon/index.html'],
         entry='dragon/index.html', script='build_dragon.py', freq='daily',
         dated=False, start=None, date_re=None,
         need='_txk_cache.json（日K）+ sector_concept/industry 快照'),

    dict(key='psychology_entry', label='群体心理索引页',
         patterns=['psychology/index.html'],
         entry='psychology/index.html', script='market-trend/_build_*.py',
         freq='daily', dated=False, start=None, date_re=None,
         need='各期明细页'),

    dict(key='picks', label='个股信号池日页', patterns=['picks/pick_*.html'],
         entry='picks/index.html',
         script='gen_picks.py;build_picks.py;backtest_picks.py',
         freq='daily', dated=True, start='20260910',
         date_re=r'(\d{4}-\d{2}-\d{2})',
         need='四路候选 + 行情补齐 + chip/fundflow（须等 lhb/block/exec 跑完）'),

    # ⚠ stable_*.html 是**按日归档**的（每日一份快照），原先挂在 dated=False 的
    # picks_entry 下 → scan_stable.py 整族漏跑也不会被门禁发现。已拆出独立族。
    dict(key='picks_stable', label='全市场稳健分选股日快照',
         patterns=['picks/stable_*.html'],
         entry='picks/index.html', script='scan_stable.py',
         freq='daily', dated=True, start='20260910',
         date_re=r'(\d{4}-\d{2}-\d{2})',
         need='须在 build_picks.py 之后跑（入口页只在 stable 页存在时才入链）；'
              '先验 12 因子横截面分位，扫全市场可交易域'),

    dict(key='picks_entry', label='信号池入口/回测/实验室',
         patterns=['picks/index.html', 'picks/backtest.html', 'picks/lab.html'],
         entry='picks/index.html', script='build_picks.py;_pick_lab.py',
         freq='daily',
         dated=False, start=None, date_re=None,
         need='同 picks；lab.html = 因子样本外功效实验室（先验固定集 vs 自动筛，_pick_lab.py）；'
              'stable_YYYY-MM-DD.html 见 picks_stable 族'),

    dict(key='highwin_tiergate', label='高胜率池 · 分档出票核验（出票许可依据）',
         patterns=['picks/highwin_tier_gate.html'],
         entry='picks/index.html',
         script='_hw_tier_gate.py;_hw_tier_gate.py --sens --step 3;_hw_gate_page.py',
         freq='on_demand',
         dated=False, start=None, date_re=None,
         need='【2026-10-04 新增】按可得维度（技术25+位置15=40分，缺 60 分不可前推→记 0 降级）'
              '重建面板，CORE 档 edge −1.31pp / R3 4.2% / step3 −0.60pp → 统计上不可出票；'
              '但更硬的结论是**数据闸**：MACD 底池自 2026-09-24 起连续 4 期逐字节未重扫，'
              '其 close 反查 35/35 精确等于 2026-09-11 = 旧快照冒充当日 → 一律不出票。'
              'gen_highwin.py 读 emit_license()，读不到即 fail-safe 不出票'),

    # ★ 2026-10-12 补登记「高胜率池·精中取精（观察候选）」。
    #   必须排在下面的 `highwin` 族**之前**：两个族的 pattern 都覆盖 picks/highwin_*，
    #   而 match_family 取「首个匹配」——放后面会被 highwin 先认领，本族被判「无页面」。
    #   性质是**观察候选·非可执行**（CORE 档样本外 edge 全负、未过第五道闸与 0.15pp 成本闸）。
    dict(key='picks_highwin_elite', label='高胜率池·精中取精（综合分最靠前 · 观察用 · 非可执行）',
         patterns=['picks/highwin_elite_*.html'],
         entry='picks/index.html', script='build_highwin_elite.py', freq='daily',
         dated=True, start='20261009', date_re=r'(\d{8})',
         need='picks/highwin_{DATE}.json（emit_ok/emit_why）+ _freq_robust_hw.json（CORE 档第五道闸）'
              '+ _hw_tier_gate.json（底池冻结 / 退出成交假设）；三者均**现读不写死**'),
    dict(key='highwin', label='高胜率候选池（每日多因子扫描）',
         patterns=['picks/highwin_*.html'],
         entry='picks/index.html',
         script='build_highwin.py --date {DATE};gen_highwin.py --date {DATE}',
         freq='daily', dated=True, start='20260914',
         date_re=r'(\d{8})',
         need='基底=MACD水上金叉池(macd_scan_{DATE}.json)；增强=data_quote→_raw_extract/quote_{DATE}.json、data_technical→tech、data_chip→chip + sector_daily + lhb + exec_chg + block_chg'),

    dict(key='tplus_tiergate', label='做T池 · 分档出票核验（出票许可依据）',
         patterns=['tplus/tier_gate.html'],
         entry='tplus/index.html',
         script='_tplus_tier_gate.py;_tplus_tier_gate.py --sens --step 3;_tplus_gate_page.py',
         freq='on_demand',
         dated=False, start=None, date_re=None,
         need='【2026-10-04 新增】做T是区间操作，**逐日平衡与池化口径可反向**：A 档逐日 edge +0.5368pp / '
              'R3 95.0% / 留一[+0.395,+0.674] 全正 / 前后半同向（看着能出票），'
              '但「触买后」池化期望 **−0.2823%**、往返率仅 5.15%（同域非 A 档 12.65%）'
              '= 分数越高越难成交。故在 _gate_common.emit_license 新增**池化闸**(pool_key)；'
              'build_tplus.py 许可不过 → 主榜与操作手册清空 + 红框'),

    dict(key='tplus', label='做T池日页', patterns=['tplus/tplus-*.html'],
         entry='tplus/index.html', script='build_tplus.py', freq='daily',
         dated=True, start='20260910', date_re=r'(\d{4}-\d{2}-\d{2})',
         need='机构底仓池 + 箱体筛选'),

    dict(key='tplus_entry', label='做T池入口', patterns=['tplus/index.html', 'tplus/lab.html'],
         entry='tplus/index.html', script='build_tplus.py', freq='daily',
         dated=False, start=None, date_re=None,
         need='同 tplus；lab.html = 做T特征功效实验室（全市场域样本外实证，_tplus_lab.py 生成，'
              '选股能力与买卖点参数以此为准）'),

    dict(key='tplus_envgate', label='做T池·环境门控样本外验证（共用 ENV_RULE 折数的独立场景检验 → 判「不可判」）',
         patterns=['tplus/env_gate.html'],
         entry='tplus/env_gate.html', script='_tplus_env_gate.py', freq='once',
         dated=False, start=None, date_re=None,
         need='_tplus_lab_panel.json（93331 行 / 196 日做T面板）+ _idxkline.env_score（生产 composite 口径复刻）+ '
              '_tplus_lab._sim_default（线上现行做T模拟）；结论：四档 edge 95% 区间全部跨 0、R3 通过率仅 48%~78%、'
              '反推相对区间宽到 ±3 → 与环境分连续分位非单调，判「不可判」，做T池 ENV_RULE 保持原值不动，'
              '且不套用主升精选的二值门控（做T点估计上弱势档 +1.50 高于强势 +1.00，照搬会做反）'),
    dict(key='research', label='个股调研', patterns=['research/research-*.html'],
         entry='research/index.html', script=None, freq='on_demand',
         dated=True, start=None, date_re=r'(\d{8})', need='按需触发'),

    dict(key='research_entry', label='个股调研入口',
         patterns=['research/index.html'], entry='research/index.html',
         script=None, freq='on_demand', dated=False, start=None,
         date_re=None, need=None),

    # 【2026-10-04 新增】四层研判是把「个股调研」的方法论换成 v2：
    # 调研＝七条标准逐项对照；研判＝四道否决先证伪再打分。两者并存，不互相覆盖。
    dict(key='diagnosis', label='个股四层研判（数据地基 → 四道独立否决 → 两段式打分 → 三周期）',
         patterns=['diagnosis/diag-*.html'],
         entry='diagnosis/index.html',
         script='build_diag.py', freq='on_demand',
         dated=True, start=None, date_re=r'(\d{8})',
         need='按需触发：python quant/build_diag.py --code <代码>。'
              'stock_diag.diagnose() 经 westock CLI 实拉 利润表 / 现金流 / 资产负债表 / 行情 / 技术指标 → '
              '落 quant/diag/{code}_{DS}.json（含 verdict 档位，单一来源）→ diag_render 渲染。'
              '人工补充走 quant/diag/{code}_{DS}.meta.json（B 组判定 / 内部人行为 / 三周期结论）。'
              '★ 只出「可被证伪的判断清单」，不给买卖结论；未被否决 ≠ 通过；硬否决成立即出局'),

    dict(key='diagnosis_entry', label='个股四层研判入口',
         patterns=['diagnosis/index.html'], entry='diagnosis/index.html',
         script='build_diag.py', freq='on_demand', dated=False, start=None,
         date_re=None,
         need='python quant/build_diag.py --rebuild-index（扫描 quant/diag/*.json 自动重建，'
              '按最新研判日倒序，带历史各期横链）'),

    dict(key='reversal', label='底部反转观察池（每日扫描 · v5 全市场域）',
         patterns=['reversal/watchlist_*.html'],
         entry='reversal/index.html', script='rev_pool.py', freq='daily',
         dated=True, start='20260911', date_re=r'(\d{8})',
         need='v5：全市场深跌域（A 股正股剔 ST/退，20 日均额≥3000万，距52周高回撤≥18% 且未破 MA60×0.75）'
              '× 先验固定因子集（9 因子等权横截面分位）→ 域内前 10% 为 A 档；'
              '流程：rev_pool.py run {DATE} → fetch_rev_flow.py --date {DATE} --src sina → '
              'fetch_rev_enrich.py --date {DATE} --render'),

    dict(key='reversal_entry', label='底部反转板块入口',
         patterns=['reversal/index.html', 'reversal/backtest.html', 'reversal/lab.html'],
         entry='reversal/index.html',
         script='gen_watchlist.py', freq='daily', dated=False, start=None,
         date_re=None, need='入口页由 gen_watchlist.py 生成（只出入口页，检测到 rev_pool scan 时不覆盖明细页，'
                            '避免两套渲染互相打架）；backtest.html 为旧种子宇宙的退出规则对照（仅参考）；'
                            'lab.html 为特征功效实验室（14 节样本外实证，选股能力以此为准，由 _rev_lab.py 生成）'),

    dict(key='reversal_tiergate', label='底部反转 · 分档出票核验（出票许可依据）',
         patterns=['reversal/tier_gate.html'], entry='reversal/index.html',
         script='_rev_tier_gate.py;_rev_gate_page.py', freq='on_demand',
         dated=False, start=None, date_re=None,
         need='【2026-10-04 新增】按生产真实出票口径（旧硬门槛 ∩ 阶段底部＋启动证据≥2 ∩ 组合分前 10%）'
              '在全市场日K上重建面板，逐日平衡 edge（对照＝同日全市场域）＋按日 block bootstrap＋R3＋留一法'
              '＋前后半＋步长敏感性。结论：A 档（现行出票）edge −0.238pp、R3 29.9%、留一全负、跨步长符号翻转 '
              '→ 判「不可出票」；B 档点估计最正但 R3 跨步长不过线；真正稳定为负的是旧硬门槛（跌得多）本身 −0.56pp。'
              'rev_pool.py 只读本页产出的 emit_license()，读不到即 fail-safe 不出票'),

    dict(key='reversal_method', label='底部反转方法论 Playbook',
         patterns=['reversal/method.html'], entry='reversal/index.html',
         script=None, freq='on_demand', dated=False, start=None,
         date_re=None, need='六步法常驻方法论，随框架迭代更新'),

    dict(key='reversal_cases', label='底部反转案例（松发/候选/复核/大金）',
         patterns=['reversal/songfa*.html', 'reversal/dajin_*.html'],
         entry='reversal/index.html', script=None, freq='on_demand',
         dated=False, start=None, date_re=None, need='方法验证案例，随讨论补充'),

    dict(key='macd', label='MACD水上金叉观察池（已并入精选池 · 停更于 2026-09-18）',
         patterns=['macd/watchlist_*.html'],
         entry='macd/index.html', script='macd_build.py;gen_macd.py', freq='archived',
         dated=True, start='20260911', date_re=r'(\d{8})',
         need='【2026-09-19 起停更·仅归档】原三层漏斗的后两层（水上金叉 DIF>0&DEA>0&MACD红柱>0、MainNetFlow20D>0）已并入精选池 build_picks.py 作为技术确认门槛；本板块不再独立日更，页面已注入停更横幅'),

    dict(key='macd_entry', label='MACD板块入口/方法论（已并入精选池 · 停更）',
         patterns=['macd/index.html', 'macd/method.html'],
         entry='macd/index.html', script='gen_macd.py', freq='archived',
         dated=False, start=None, date_re=None, need='同 macd（归档入口 + 方法论常驻页，已标注停更并跳转精选池）'),

    dict(key='selected', label='主升精选合并页（全市场域 · 趋势+资金双确认高确定性池）',
         patterns=['selected/combined_*.html', 'selected/index.html', 'selected/lab.html', 'selected/purity.html'],
         entry='selected/index.html', script='build_selected.py', freq='daily',
         dated=True, start='20260918', date_re=r'(\d{8})',
         need='_txk_cache.json（全市场日K）+ _selected_lab.py（实验室冻结 _selected_model.json：9 因子等权横截面分位、A档前5%）+ _idxkline（环境门控）；不再依赖 macd_scan/picks 模型库'),
    # ★ 2026-10-12 补登记：「精中取精」观察候选页（用户要求「量化策略列出的股票=整个判断逻辑中胜率最高的」）。
    #   性质是**观察候选·非可执行**（相应档位样本外 edge 为负、未过第五道闸与 0.15pp 成本闸），
    #   所以 dated=True 但只是「每日跟到最新数据日」，不代表可以出票。
    dict(key='selected_elite', label='主升精选·精中取精（胜率候选 · 观察用 · 非可执行）',
         patterns=['selected/elite_*.html'],
         entry='selected/index.html', script='build_selected_elite.py', freq='daily',
         dated=True, start='20261009', date_re=r'(\d{8})',
         need='build_selected.scan 当日全市场域 + _selected_model.json（样本内胜率/样本外证据现读）；'
              '只有在「A 档前 5%（样本内胜率最高档）」里再取主升分最靠前 ≈全市场前 1%'),
    dict(key='selected_envgate', label='主升精选·环境门控系数样本外验证（0.55/0.8 折值的证伪证据）',
         patterns=['selected/env_gate.html'],
         entry='selected/env_gate.html', script='_env_gate_lab.py', freq='once',
         dated=False, start=None, date_re=None,
         need='_txk_cache.json（全市场日K 逐日重建完整横截面）+ _idxkline.index_env/env_score（生产 composite 口径逐项复刻）+ market_profile/{DATE}.json；结论：反推相对系数强势 +1.00[+0.62,+1.38] 显著为正、震荡 -0.16、弱势 -0.46、破位 -0.05 → 主升精选门控改二值（强势开仓、其余空仓）；做T池 ENV_RULE 未验证、保持原值不动'),
    dict(key='selected_envgate_sens', label='主升精选·环境门控结论的样本量/步长敏感性检验',
         patterns=['selected/env_gate_sens.html'],
         entry='selected/env_gate_sens.html', script='_env_gate_sens.py', freq='once',
         dated=False, start=None, date_re=None,
         need='复用 _env_gate_lab.build（加了 cache/nm 外部传入以支持多组步长共用一次扫描）；'
              'step=3 密扫描（243121 行 / 96 信号日）派生 3/6/9 + 基准 step=5 交叉校验口径。'
              '★ 结论：强势档跨 4 组步长绝对收益全正（开仓有据）、弱势档全负（空仓有据），'
              '但震荡/破位档符号随采样翻转 → 判「不可判」，生产仍空仓但那是纪律不是数据结论；'
              '口径要点：反推系数必须用「策略层绝对收益」而非相对 edge，否则会得出相反错觉'),
    dict(key='selected_envgate_freq', label='主升精选·环境门控跨采样频率稳健性（对齐 _freq_robust 第五道闸严判据）',
         patterns=['selected/env_gate_freq.html'],
         entry='selected/env_gate_freq.html', script='_env_gate_freq.py', freq='once',
         dated=False, start=None, date_re=None,
         need='step=1 密扫描派生 7 步网格 [1,2,3,5,8,10,20]；对强势开仓档逐频率算'
              '绝对均收益 + 按日移动块 bootstrap R3（块长=覆盖前推窗口 FMAX 个信号日）+ 相对同日全票 edge；'
              '三判据全满足才 PASS：7 步绝对收益全>0 且翻转0次 + 全步 R3≥95% + 全步相对 edge>0。'
              'bootstrap 固定 2000 次 / seed=20261010（与 _freq_robust 一致）；结论数字现读 JSON 不写死'),
    dict(key='selected_envgate_freq_real', label='主升精选·环境门控跨频率稳健性（可实现口径 · 严判据）',
         patterns=['selected/env_gate_freq_realistic.html'],
         entry='selected/env_gate_freq_realistic.html', script='_env_gate_freq.py', freq='once',
         dated=False, start=None, date_re=None,
         need='同 selected_envgate_freq，但成交假设改可行口径（保守日内路径 + 跳空按开盘价成交），'
              '验证「强势开仓」alpha 不被乐观退出口径虚高；运行 python quant/_env_gate_freq.py --mode realistic'),
    dict(key='accumulation', label='增仓精选（7 维增持/增仓信号 + 1/3/5 日多空增仓 · 共识选股池）',
        patterns=['accumulation/combined_*.html', 'accumulation/index.html',
                  'accumulation/lab.html', 'accumulation/history.html',
                  'accumulation/tier_gate.html'],
        entry='accumulation/index.html', script='_accum_lab.py;build_accum.py', freq='daily',
        dated=True, start='20260918', date_re=r'(\d{8})',
        need='block_chg/{DATE}.json（大宗交易）+ exec_chg/{DATE}.json（高管增持）+ lhb_detail/{DATE}_batch*.json（席位异动）+ margin_em/{code}.json（东财融资融券日频全量序列 · T+1 口径）+ q2_full/_merged_shareholder.json（私募/阳光私募/个人/公募增持·季度维度）+ _txk_cache.json（前向回测与事后兑现回填）；每日另出 stat_{DS}.json 快照并累积 quant/accum/history.json（history.html 为归档/兑现页）'),
    dict(key='freq_robust', label='跨采样频率稳健性（出票第五道闸）',
         patterns=['quant_strategy/freq-robust.html'],
         entry='quant_strategy/freq-robust.html',
         script='_freq_robust.py --pool 3yl; _freq_robust.py --pool rev; '
                '_freq_robust.py --pool hw; _freq_robust.py --pool tplus; '
                '_freq_robust.py --pool accum; build_freq_robust_page.py',
         freq='manual', dated=False, start=None, date_re=None,
         need='_freq_robust_{pool}.json（逐采样频率重建面板重算 edge/R3；五个池 3yl/rev/hw/tplus/accum 全扫，'
              '证据齐全后跑 build_freq_robust_page.py 汇总；样本外证据，按需重跑，不进日更链 —— '
              '频率扫描不随每日行情变化。★ 结论：五池可判定档位 0 通过；高胜率 CORE 与反转 A 为'
              '「符号一致但稳定为负」的负贡献档，三连阴/反转B/做T各档符号随频率翻转 → 全站无池可出票。'
              '做T 族走 family=tplus 自定义 build（_tplus_lab.build_panel(step) 全量重建，避免已稀疏面板二次抽稀自欺）；'
              '增仓族走 family=accum 自定义 build（复用 _accum_tier_gate.build(days=全量) 一次产全行，'
              '再按入场日 step 子集，tier 取自 RULES 的 S/A/B/C + M且I 候选档——排除「全候选域」对照基准以免 edge_stats 崩溃）'),
    dict(key='rev_sector_watch', label='板块共振反转观察（底部反转优化方向 · 观察池）',
         patterns=['quant_strategy/rev-sector-watch.html'],
         entry='quant_strategy/rev-sector-watch.html',
         script='_build_rev_sector_watch.py', freq='manual', dated=False, start=None, date_re=None,
         need='底部反转 A 档经跨频率稳健性严扫 0 通过（稳定负贡献）；本页探索「板块共振」优化方向——'
              '只把落在抢筹/建仓板块的反转候选列入观察（板块级，领涨股作风向标锚）。数据源 _rev_sector_state_20261009.json'
              '（板块强度/行为/5·20日净流合并）+ _freq_robust_rev.json + _rev_tier_gate_step5.json。'
              '★ 限制：个股→板块全量映射缺失（仅领涨股）、今日反转候选空（rev_enrich 未产出）、板块成员仅 2026-08 起'
              ' → 当前只能做板块土壤观察，个股级筛选待成员映射+候选管线补上；非出票，不输出买卖结论'),
    dict(key='accum_sector_watch', label='板块共振增仓观察（增仓精选优化方向 · 观察池）',
         patterns=['quant_strategy/accum-sector-watch.html'],
         entry='quant_strategy/accum-sector-watch.html',
         script='_build_accum_sector_watch.py', freq='manual', dated=False, start=None, date_re=None,
         need='增仓精选 _accum_tier_gate.json（三窗口 20/40/60 日显著性检验，boot=2000/seed 固定）显示：'
              '数据闸已修复（margin_em 补全量 3629 只，M 维覆盖 18.4%→98.06%，zero_days 44/60→0/60）→ S 档正式可评估：'
              '20 日 edge +0.96pp / R3 99.9%，但 40 日 R3 92.8%、60 日 R3 57.9%（跨窗口不稳健）、绝对收益 R3=0% → 仍 0 通过。'
              '进一步接入 _freq_robust 第五道闸（family=accum，复用 build(days=全量) 按入场日 step 子集）：'
              'S 档跨频翻转 3 次、A(M或I)/A(M且I) 各翻转 3 次 → 0 通过；唯一「符号不翻转」的档是 B 档（2信号观察仓，'
              'edge [+0.129,+1.012]pp 全正、R3 最低 62.4%）——方向稳健但幅度/R3 不达标，是后续优化靶点。'
              '本页探索「板块共振」优化方向（板块级，领涨股作风向标锚）；'
              '数据源 _rev_sector_state_20261009.json（板块强度/行为/净流合并，与反转页同份）+ _accum_tier_gate.json + _freq_robust_accum.json。'
              '★ 限制：个股→板块全量映射缺失、板块基准 10-09 未更新 → 非出票，不输出买卖结论'),
    dict(key='accum_b_purity', label='增仓 B 档提纯实验（B 档变体跨频率严扫 · 探索页）',
         patterns=['quant_strategy/accum-b-purity.html'],
         entry='quant_strategy/accum-b-purity.html',
         script='_accum_b_purity.py', freq='manual', dated=False, start=None, date_re=None,
         need='B 档（恰 2 信号）跨频率严扫中 edge 符号稳健为正（翻转 0）但 R3 仅 62.4% 不过闸，'
              '故做提纯实验：在 B 档内强制资金确认测 5 变体（B0基线/B1资金M或I/B2融资M/B3机构I/B4强合成）。'
              '复用 _accum_tier_gate.build 全量 + _gate_common.tier_analyse/edge_stats（无未来函数）。'
              '结论：无一变体过第五道闸；B2 融资确认最亮眼（40/60 日 edge +0.116pp、R3 98%，'
              '但 20 日窗口 R3 33% 拖垮跨频率一致性）→ 增仓 edge 短 horizon 脆弱，提纯方向成立但不过阈，仍空仓。'
              '数据源 _accum_b_purity.json（自产）。★ 探索页非生产规则，不输出买卖结论'),

    dict(key='quant_strategy', label='量化策略板（综合选股 + 买卖点 · 短/中/长三周期）',
        patterns=['quant_strategy/strategy_*.html', 'quant_strategy/index.html',
                  'quant_strategy/method.html'],
        entry='quant_strategy/index.html',
        script='build_quant_strategy.py', freq='daily', dated=True, start='20260928',
        date_re=r'(\d{8})',
        need='_txk_cache.json（全市场日K）+ rev/bottom_state.json（底部锚定）；先验固定因子集（短/中/长三族，等权横截面分位）→ 按持有周期分类并给量化买卖点（箱体/趋势/底部锚定）；环境只控β不控排序；综合视图非叠加alpha'),

    dict(key='three_yin_tiergate', label='三连阴 · 分档出票核验（出票许可依据）',
         patterns=['three_yin/tier_gate.html'],
         entry='three_yin/index.html',
         script='_3yl_tier_gate.py;_3yl_tier_gate.py --sens --step 3;_3yl_gate_page.py',
         freq='on_demand',
         dated=False, start=None, date_re=None,
         need='【2026-10-04 新增】核验页面原写「观察档(跌8~12%)两半同向跑赢基准、期望+0.43%(基准+0.01%)，本期主推」。'
              '那个对照是**该档 vs 全体三连阴母集（母集含它自己）**= 子集对母集、且无显著性区间。'
              '按统一口径逐日平衡重算：obs 档 n=4355 母集 edge +0.001pp / R3 50.4%、等量(同日非本档) +0.059pp / R3 59.8%、'
              '留一[-0.070,+0.087] 跨 0 → 判「不可出票」。原结论原样保留不删改。'
              'build_3yl.py 读 emit_license()，读不到即 fail-safe 不出票'),

    dict(key='three_yin', label='三连阴（量化错杀）观察池 + 实验室',
        patterns=['three_yin/sanyin_*.html', 'three_yin/index.html', 'three_yin/lab.html'],
        entry='three_yin/index.html',
        script='build_3yl.py', freq='daily', dated=True, start='20260929',
        date_re=r'(\d{8})',
        need='_txk_cache.json（全市场日K）+ _mktcap.json（流通市值）+ _name2sw2.json（行业）；'
             '回测引擎 _3yl_lab.py（284交易日/22.4万信号，结论：原条件集不产生超额，仅跌幅分档两半同向稳健）；'
             '按跌幅分档出票 + 量化买卖点（止损取结构位与-6%更宽者，目标=谷底+跌幅×0.382/0.618）'),

    dict(key='shareholder', label='行业最强/牛人', patterns=['shareholder/*.html'],
         entry='shareholder/2026-q2-industry-elite.html', script=None,
         freq='quarterly', dated=False, start=None, date_re=None,
         need='季报/中报十大股东'),

    dict(key='n_shape_bt', label='N字形战法 · 往前10日历史回测（胜率/盈亏比 · 观察池）',
         patterns=['n_shape/backtest/bt_*.html', 'n_shape/backtest/index.html'],
         entry='n_shape/backtest/index.html', script='build_n_shape_backtest.py', freq='daily',
         dated=False, start=None, date_re=None,
         need='_txk_cache.json（全市场日K，复用 gen_signals_asof）+ sector_strength_data.json（热点）；'
              '对最近10个可回测日（各有>=10后续交易日）重算 N字形信号，前向持有10交易日算胜率/盈亏比；'
              '回测日受数据末端限制（最新数据日无法前向回测），不做连续日期校验；观察池，非出票'),
    dict(key='n_shape_sim', label='N字形 · 首次触及法 实盘模拟器（可调参数 · 观察池）',
         patterns=['n_shape/sim/index.html'],
         entry='n_shape/sim/index.html', script='build_n_shape_sim.py', freq='daily',
         dated=False, start=None, date_re=None,
         need='_txk_cache.json（复用 gen_signals_asof/attach_attr/is_healthy_pullback/is_pos_ok）'
              '+ 最新 quotes 快照（名称，缺当日快照时回退最近一日）；把 hb_pos 真实信号的前向价格嵌入页面，'
              '用户调 目标%/止损%/持有天数/市场热度 即时重算首次触及胜率；回测日受数据末端限制，不做连续日期校验；观察池，非出票'),
    dict(key='research_report', label='研报分析（上传研报入库 · 逐股胜率排序 · 观察池）',
         patterns=['research_report/index.html', 'research_report/report_*.html'],
         entry='research_report/index.html', script='build_research.py', freq='daily',
         dated=False, start=None, date_re=None,
         need='quant/research/reports.json（人工校读上传PDF入库：报告日期/来源/观点/提及标的，'
              'PDF原文与提取文本留存 quant/research/）+ _txk_cache.json（全市场日K）'
              '+ 最新 quotes 快照（名称，缺当日快照回退最近一日）+ _name2sw2/sector_strength（热点）；'
              '逐股现算：近一年N字形信号首次触及胜率（+6%/-8%/10日，与回测DEF档同口径）、'
              '52周分位（K线缓存自算，quotes快照52周字段已证伪）、大盘环境门控、健康回撤判定；'
              '输出：按胜率排序 + 是否可建仓 + 参考买卖点（买点=MA20回踩，止损-8%，目标+6%/60日高）；'
              '观察池，非出票'),
    dict(key='n_shape', label='N字形战法筛选（近20日涨停+站上5日线 · 观察池）',
         patterns=['n_shape/n_shape_*.html', 'n_shape/index.html', 'n_shape/archive.html'],
         entry='n_shape/index.html', script='build_n_shape.py', freq='daily',
         dated=True, start='20261022', date_re=r'n_shape_(\d{8})\.html',
         need='_txk_cache.json（全市场日K）+ _mkt_emo（涨停口径）+ quotes/{DATE}.json（名称/现价）；'
              '筛选：近20交易日有收盘封涨停 且 收盘>MA5，剔除当日已封涨停；观察池，非出票'),
    dict(key='db', label='数据中心', patterns=['db/*.html'],
         entry='db/index.html', script='db_update.py;db_export.py;build_db.py',
         freq='daily', dated=False, start=None, date_re=None,
         need='各模块 JSON 落盘'),

    dict(key='sections', label='版块总览（已合并到总门户，保留重定向）',
         patterns=['sections/*.html'],
         entry='sections/index.html', script='build_sections.py', freq='ad_hoc',
         dated=False, start=None, date_re=None,
         need='内容已合并至首页门户；本页自动重定向，避免旧书签失效'),

    dict(key='docs', label='说明文档', patterns=['docs/*.html'],
         entry=None, script=None, freq='ad_hoc', dated=False, start=None,
         date_re=None, need=None),
]

# ---- 孤儿页白名单：允许「无静态入链」的页面 ------------------------------
# 归档明细页由列表页 JS 动态拼链接，静态扫描扫不到；文档页本就是入口。
ORPHAN_WHITELIST_SUBSTR = (
    'archive',
    '/db/',
    'docs/',
    'sections/',
    'selected/',
    'quant_strategy/',
    'three_yin/',
    'n_shape/',              # 每日归档页由 index.html 静态链接入链，二者互为入口
    'sector/trend.html',     # 旧名跳转桩（已迁移到 sector-strength-trend.html，见 build_sector_trend）
)


def repo_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def web_root():
    return os.path.join(repo_root(), 'web')
