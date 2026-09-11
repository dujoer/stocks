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
                   'sector/sector-strength-trend.html',
                   'sector-strength-trend.html'],
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

    dict(key='picks_entry', label='信号池入口/回测',
         patterns=['picks/index.html', 'picks/backtest.html'],
         entry='picks/index.html', script='build_picks.py', freq='daily',
         dated=False, start=None, date_re=None, need='同 picks'),

    dict(key='tplus', label='做T池日页', patterns=['tplus/tplus-*.html'],
         entry='tplus/index.html', script='build_tplus.py', freq='daily',
         dated=True, start='20260910', date_re=r'(\d{4}-\d{2}-\d{2})',
         need='机构底仓池 + 箱体筛选'),

    dict(key='tplus_entry', label='做T池入口', patterns=['tplus/index.html'],
         entry='tplus/index.html', script='build_tplus.py', freq='daily',
         dated=False, start=None, date_re=None, need='同 tplus'),

    dict(key='research', label='个股调研', patterns=['research/research-*.html'],
         entry='research/index.html', script=None, freq='on_demand',
         dated=True, start=None, date_re=r'(\d{8})', need='按需触发'),

    dict(key='research_entry', label='个股调研入口',
         patterns=['research/index.html'], entry='research/index.html',
         script=None, freq='on_demand', dated=False, start=None,
         date_re=None, need=None),

    dict(key='shareholder', label='行业最强/牛人', patterns=['shareholder/*.html'],
         entry='shareholder/2026-q2-industry-elite.html', script=None,
         freq='quarterly', dated=False, start=None, date_re=None,
         need='季报/中报十大股东'),

    dict(key='db', label='数据中心', patterns=['db/*.html'],
         entry='db/index.html', script='db_update.py;db_export.py;build_db.py',
         freq='daily', dated=False, start=None, date_re=None,
         need='各模块 JSON 落盘'),

    dict(key='sections', label='版块总览', patterns=['sections/*.html'],
         entry='sections/index.html', script='build_sections.py', freq='daily',
         dated=False, start=None, date_re=None, need='各模块页已生成'),

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
)


def repo_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def web_root():
    return os.path.join(repo_root(), 'web')
