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

    dict(key='picks_entry', label='信号池入口/回测/实验室',
         patterns=['picks/index.html', 'picks/backtest.html', 'picks/lab.html',
                   'picks/stable_*.html'],
         entry='picks/index.html', script='build_picks.py;_pick_lab.py;scan_stable.py',
         freq='daily',
         dated=False, start=None, date_re=None,
         need='同 picks；lab.html = 因子样本外功效实验室（先验固定集 vs 自动筛，_pick_lab.py）；'
              'stable_YYYY-MM-DD.html = 全市场稳健分选股快照（scan_stable.py，由 picks 入口页静态入链）'),

    dict(key='highwin', label='高胜率候选池（每日多因子扫描）',
         patterns=['picks/highwin_*.html'],
         entry='picks/index.html',
         script='build_highwin.py --date {DATE};gen_highwin.py --date {DATE}',
         freq='daily', dated=True, start='20260914',
         date_re=r'(\d{8})',
         need='基底=MACD水上金叉池(macd_scan_{DATE}.json)；增强=data_quote→_raw_extract/quote_{DATE}.json、data_technical→tech、data_chip→chip + sector_daily + lhb + exec_chg + block_chg'),

    dict(key='tplus', label='做T池日页', patterns=['tplus/tplus-*.html'],
         entry='tplus/index.html', script='build_tplus.py', freq='daily',
         dated=True, start='20260910', date_re=r'(\d{4}-\d{2}-\d{2})',
         need='机构底仓池 + 箱体筛选'),

    dict(key='tplus_entry', label='做T池入口', patterns=['tplus/index.html', 'tplus/lab.html'],
         entry='tplus/index.html', script='build_tplus.py', freq='daily',
         dated=False, start=None, date_re=None,
         need='同 tplus；lab.html = 做T特征功效实验室（全市场域样本外实证，_tplus_lab.py 生成，'
              '选股能力与买卖点参数以此为准）'),

    dict(key='research', label='个股调研', patterns=['research/research-*.html'],
         entry='research/index.html', script=None, freq='on_demand',
         dated=True, start=None, date_re=r'(\d{8})', need='按需触发'),

    dict(key='research_entry', label='个股调研入口',
         patterns=['research/index.html'], entry='research/index.html',
         script=None, freq='on_demand', dated=False, start=None,
         date_re=None, need=None),

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
         patterns=['selected/combined_*.html', 'selected/index.html', 'selected/lab.html'],
         entry='selected/index.html', script='build_selected.py', freq='daily',
         dated=True, start='20260918', date_re=r'(\d{8})',
         need='_txk_cache.json（全市场日K）+ _selected_lab.py（实验室冻结 _selected_model.json：9 因子等权横截面分位、A档前5%）+ _idxkline（环境门控）；不再依赖 macd_scan/picks 模型库'),
    dict(key='accumulation', label='增仓精选（7 维增持/增仓信号 + 1/3/5 日多空增仓 · 共识选股池）',
         patterns=['accumulation/combined_*.html', 'accumulation/index.html', 'accumulation/lab.html'],
         entry='accumulation/index.html', script='_accum_lab.py;build_accum.py', freq='daily',
         dated=True, start='20260918', date_re=r'(\d{8})',
         need='block_chg/{DATE}.json（大宗交易）+ exec_chg/{DATE}.json（高管增持）+ lhb_detail/{DATE}_batch*.json（席位异动）+ picks/margin_*.json（多空增仓·快照稀疏近似）+ q2_full/_merged_shareholder.json（私募/阳光私募/个人/公募增持·季度维度）+ _txk_cache.json（前向回测）；A档=≥3信号共振'),
    dict(key='shareholder', label='行业最强/牛人', patterns=['shareholder/*.html'],
         entry='shareholder/2026-q2-industry-elite.html', script=None,
         freq='quarterly', dated=False, start=None, date_re=None,
         need='季报/中报十大股东'),

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
)


def repo_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def web_root():
    return os.path.join(repo_root(), 'web')
