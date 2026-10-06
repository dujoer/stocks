# -*- coding: utf-8 -*-
"""
将本次「全站 web/ 分层重构」后的全部网页、生成器与数据源推送到 GitHub 仓库 dujoer/stocks。

结构约定（2026-09-04 重构后）：
  - 根 index.html            = 总门户
  - web/<板块>/...           = 各版块按目录分层存放
  - web/docs/DAILY_UPDATE_SOP.html = 操作手册
  - 所有网页均为自包含 HTML（内联 CSS/JS/数据），不依赖外部资源

鉴权方式：读取环境变量 GH_PAT（或 GITHUB_TOKEN）作为 Bearer Token，绝不硬编码。
本地私有 token 文件路径（~/.workbuddy，不在仓库内、不会被上传）：C:/Users/nonoy/.workbuddy/gh_pat.txt
用法：
    python quant/_push_lhb.py --dry-run     # 只列差异清单，不写入（推荐先跑这个）
    python quant/_push_lhb.py               # 逐文件 PUT（Contents API）
    python quant/_push_lhb.py --only web/docs/   # 只推某子目录
说明：本脚本仅做 Contents API 的 create/update；每个文件独立提交。
      ⚠ **大批量（数百文件）请改用 `_push_incremental.py`** —— 它按 git blob sha 算增量、
      走 Git Data API 批量提交，快得多（本脚本逐文件 PUT 在沙箱 10 分钟硬超时下会被 SIGTERM）。
      本脚本适合小批量/单文件精修。
      强制排除任何含 portfolio / bottom-up / portfolio_analysis 的文件（硬规矩：不对外展示持仓/选股）。
"""
import os, sys, json, base64, glob as _glob, re, urllib.request, urllib.error

REPO = "dujoer/stocks"
BRANCH = "main"
API = f"https://api.github.com/repos/{REPO}/contents"

# token 仅来自运行时环境 / 本地私有文件，绝不硬编码、绝不以明文写入会被推送的文件。
_LOCAL_TOKEN_FILE = os.path.expanduser("~/.workbuddy/gh_pat.txt")
def _load_token():
    t = os.environ.get("GH_PAT") or os.environ.get("GITHUB_TOKEN")
    if t:
        return t
    try:
        if os.path.exists(_LOCAL_TOKEN_FILE):
            with open(_LOCAL_TOKEN_FILE, "r", encoding="utf-8") as f:
                return f.read().strip()
    except Exception:
        pass
    return None
TOKEN = _load_token()

# 强制排除名单（路径含以下任一子串即跳过）—— 不对外展示个人持仓 / 选股
# 2026-09-11：补充 web/research —— 个股调研页含个人持仓快照，按项目硬性边界一律不对外推送。
EXCLUDE_FRAGMENTS = ("portfolio", "bottom-up", "portfolio_analysis", "_all_store", "web/research",
                     "_mcp_cache")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# commit message 前缀。历史坑：原实现把一段**写死的旧文案**贴在每个文件上
# （「做T池加箱体…修复排序双重绑定」），与当次改动无关 —— 记录失真。
# 现改为可用环境变量 PUSH_MSG 覆盖，默认中性描述。
COMMIT_MSG = os.environ.get("PUSH_MSG") or "chore: 日更同步（页面/生成器/数据源）"

# (本地相对仓库根的路径) — 框架 / 生成器 / 门户 / 手册（本次重构真实改动/新增的文件）
FILES = [
    # —— 总门户 + 操作手册 ——
    "index.html",
    ".nojekyll",                       # ★ 关掉 Jekyll，否则 quant/_*.py 在线上一律 404（无法复现）
    "web/docs/DAILY_UPDATE_SOP.html",
    # —— 导航与门户/总览生成器 ——
    "quant/_nav.py",
    "quant/build_dashboards.py",
    "quant/build_portal.py",
    "quant/build_sections.py",
    "quant/_apply_nav.py",
    "quant/_link_check.py",
    "quant/_push_lhb.py",
    "quant/_fix_archive_nav.py",
    # —— 情绪真源 + 龙道诀胜率实验室（2026-10-06）——
    "quant/_mkt_emo.py",
    "quant/_dragon_odds.py",
    "quant/dragon/odds_2026-09-30.json",
    "quant/_dragon_stage_use.py",   # ★ 四阶段「能不能用」预注册检验（全市场等权口径，不出票）
    "quant/dragon/stage_use_20260930.json",  # 上述检验产物（页面第九节读它）
    "quant/_dragon_pos_rule.py",      # ★ 四阶段「当仓位开关」第二道预注册检验（全市场等权口径，不出票）
    "quant/dragon/pos_rule_20260930.json",  # 上述检验产物（页面第十节读它）
    # —— 龙虎榜 + 游资 + 当日快照 ——
    "quant/build_lhb_enriched.py",
    "quant/build_sw1_mapping.py",
    "quant/_merge_lhb_subtabs.py",
    "quant/gen_lhb_nextday_backtest.py",
    "quant/build_interactive_sector.py",
    # —— 高管增减持（董监高）——
    "quant/gen_exec.py",
    "quant/build_exec.py",
    "quant/exec_elite_xref.json",
    # —— 板块强度子系统 ——
    "quant/gen_sector_raw.py",
    "quant/run_daily_sector.py",
    "quant/build_sector_strength.py",
    "quant/build_sector_trend.py",
    "quant/build_sector_index.py",
    # —— 大宗交易 ——
    "quant/gen_block.py",
    "quant/build_block.py",
    "quant/build_block_stocks.py",
    # —— 个股调研 / 行业最强榜 ——
    "quant/build_research_301110.py",
    "quant/build_research_600838.py",
    "quant/build_q2_industry_page.py",
    # —— 行业知名 Top20 私募/牛散 策划清单 + 5544 只全市场 Q2 中报真实现身佐证 + 机会扫描器 + 股票增持扫描 ——
    "quant/_shareholder/build_top_elite.py",
    "quant/_shareholder/scan_elite_coverage.py",
    "quant/_shareholder/build_stock_accumulation.py",
    "quant/_shareholder/elite_coverage.json",
    "quant/_shareholder/_quotes_elite.json",
    "quant/_shareholder/_elite_codes.json",
    # —— 知名加仓股 量价健康度二次过滤（50 只样本 + 技术面/行情快照 + 生成器）——
    "quant/_shareholder/extract_known_inc.py",
    "quant/_shareholder/build_known_accumulation_health.py",
    "quant/_shareholder/known_inc_50.json",
    "quant/_shareholder/_tech_b1.json",
    "quant/_shareholder/_tech_b2.json",
    "quant/_shareholder/_quote_b1.json",
    "quant/_shareholder/_quote_b2.json",
    # —— 重构/自检辅助脚本（记录本次分层过程，便于复现）——
    "quant/_cleanup_flat.py",
    "quant/_verify_dupes.py",
    "quant/_fix_psy_paths.py",
    # —— 本地数据库 + 静态数据切片（数据中心查询页）——
    "quant/db.py",
    "quant/db_export.py",
    "quant/db_update.py",
    # —— 离线数据层 + MCP 客户端 + 个股外链（2026-09-20：降限额的三件套，便于复现）——
    "quant/_tx_fetch.py",            # 腾讯离线行情（快照/日K，带 _txk_cache）
    "quant/fetch_fin_snapshot.py",   # 东财全市场财务快照（季度频率）
    "quant/fetch_pick_klines.py",    # 精选池日K价格档案（腾讯离线优先）
    # —— 精选池样本外实验室（2026-09-21）：因子功效检验 + 稳健分落地 ——
    "quant/_pick_lab.py",            # 实验室（面板/特征功效/五道检验/环境门控）
    "quant/pick_score.py",           # 稳健分（先验固定因子集，供 build_picks/scan_stable 消费）
    "quant/scan_stable.py",          # 全市场稳健分选股（可交易域内横截面排序）
    # —— 日更链路曾漏登记的生成器（2026-10-05 由门禁 C2 抓出：页面在册、脚本不在册
    #    → 线上能看数字却无法复算）。登记后 C2 判据才有意义，缺一即失效。 ——
    "quant/gen_picks.py",            # 精选候选池（三路信号：增减持/高管/大宗）
    "quant/build_picks.py",          # 精选池合并打分 → picks/*.json
    "quant/backtest_picks.py",       # 精选池历史胜率回测
    "quant/scan_strong.py",          # 做T 强趋势扫描（_strong_scan_{D}.json）
    "quant/gen_tplus.py",            # 做T 池 universe 生成
    "quant/build_tplus.py",          # 做T 页面渲染（index + tplus-{D} + history）
    "quant/gen_highwin.py",          # 高胜率候选页（web/picks/highwin_{D}.html）
    "quant/build_highwin.py",        # 高胜率候选池 → picks/highwin_{D}.json
    "quant/gen_macd.py",             # MACD 候选页（watchlist_{D}.html + index + method）
    "quant/macd_build.py",           # MACD 三层漏斗扫描 → macd_scan_{D}.json
    "quant/build_macd_extra.py",     # MACD 附加维度（供 macd_build 合并）
    "quant/rev_pool.py",             # 反转观察池（谷底锚定写盘 + watchlist 渲染）
    "quant/gen_watchlist.py",        # 反转观察页（web/reversal/index.html）
    "quant/_mkt_emo.py",             # ★ 市场情绪指标唯一真源（涨停/炸板/连板/涨跌家数），龙道诀+大盘概览+连板周报共用
    "quant/_fetch_macd_raw.py",      # MACD 三段原始数据（pool/tech/flow）落盘，daily_all 第⑩ 步先跑它
    "quant/build_psychology.py",     # 情绪雷达页（web/psychology/*.html）
    "quant/build_dragon.py",         # ★ 龙道诀情绪周期择时台生成器（走统一层 _txk）
    "web/dragon/index.html",         # ★ 龙道诀页面本体（生成器改了、页面没登记＝内容不上线）
    "quant/dragon/cycle_20260930.json",  # ★ 周期快照（门户卡片读它；新一期需在此追加，FILES 不支持通配）
    "quant/_pick_model.json",        # 冻结模型 + 样本外证据摘要
    "quant/_pick_lab_result.json",   # 实验室完整结果（供审计/复现）
    "quant/fetch_rev_flow.py",       # 反转池主力资金流（MCP 优先 · 新浪离线兜底）
    "quant/fetch_rev_enrich.py",     # 反转池补数（名称/流通市值/PE + 资金流合并）
    "quant/_wsmcp.py",               # MCP 客户端（磁盘缓存 + 限频熔断）
    "quant/_wsboot.py",              # MCP 引导（live 端口优先，本地文件仅兜底）
    "quant/_emlink.py",              # 东财个股页 URL + 全市场名称表
    "quant/linkify.py",              # 全站个股名称外链后处理器
    # —— 增仓精选（2026-09-21）：机构/私募 × 融资融券 1/3/5 日净增仓 条件模块 ——
    "quant/_accum_lab.py",           # 实验室（信号帧 + 移动止盈回测 + 模块组合/阈值敏感性）
    "quant/build_accum.py",          # 每日选股页（S=融资强增仓×机构私募；胜率由 matured 口径每日重算）
    "quant/_fetch_margin_em.py",     # 东财 datacenter 融资融券日频批量抓取（margin_em/ 本地缓存不推送，可复抓）
    "quant/_accum_ablate.py",        # 因子消融实验室（留一法/分档/清洗后重组合）
    "quant/_accum_oos.py",           # 严格样本外 + 随机对照（防过拟合闸门）
    # 冷门行业池（2026-10-03）：引擎 / 闸门 / 消融 / 页面生成器 + 事实数据
    "quant/_fetch_long_kline.py",    # 两年日K 底座抓取（_long_kline.json 本地缓存不推送，可复抓）
    "quant/_cold_sector.py",         # 行业指数重建 + 主升识别 + 冷门榜引擎
    "quant/_cold_oos.py",            # 四道闸门（未过则不出票）
    "quant/_cold_ablate.py",         # 5 因子消融
    "quant/_cold_single.py",         # 单维度严格检验
    "quant/build_cold_sector.py",    # 冷门榜页面（只陈述事实，不含个股推荐）
    # 统一数据底座（2026-10-03）：每日一次抓取、各模块只读
    "quant/_datahub.py",             # 8 维度汇总落 hub/{DATE}.json + manifest
    "quant/_datahub_api.py",         # 模块接入层（只读 API / 零改造垫片 / 口径核对）
    "quant/_datahub_gate.py",        # 底座门禁（覆盖 8/8、数据日一致性、防旧底座冒充当日）
    "quant/build_cross_section.py",  # 全市场横截面页（数据能力展示，非选股结论）
    "quant/_datahub_archive.py",     # 每日底座沉淀（hist 精简切片 + 资金流序列副本）
    "quant/_selected_flow_probe.py", # 资金流因子截面可行性探查（结论：无增量）
    "quant/_flow_lead_lag.py",       # 资金流领先/滞后判定（结论：领先但无增量，不进规则）
    "quant/_nonprice_lead.py",       # 非价量（位置类）因子检验（结论：低位有效应但无超额）
    "quant/_pullback_probe.py",      # 强势行业回调买点检验（结论：9 定义全负，不出票）
    "quant/_strategy_gate.py",       # ★策略结论门禁（R1等量/R2真选股层/R3判定双条件）
    "quant/_event_nextday_probe.py",  # ★「提前拿消息→次日必涨」实测（结论：剔封板后超额 −0.78pp）
    # ★ 证据页本体也要登记（2026-10-05 补）：只登记「生成器」的话，
    #   页面内容改了不会上线（生成器只在被跑时才重写页面）。
    "web/docs/news_nextday_evidence.html",
    "web/docs/dip_buy_evidence.html",
    "web/docs/exit_assumption_evidence.html",
    "web/docs/selected_attrib_evidence.html",
    "quant/gen_news_nextday_page.py",  # 上述结论证据页生成器 → web/docs/news_nextday_evidence.html
    "quant/_dip_probe.py",            # ★「高上涨率 + 低吸」实测（结论：低吸池化净期望全面劣于追高）
    "quant/gen_dip_page.py",          # 上述结论证据页生成器 → web/docs/dip_buy_evidence.html
    "quant/_diag_remote_diff.py",     # 本地 vs 远端 blob 差异诊断（判断「谁新」，避免推错方向）
    "quant/_selected_attrib.py",      # ★ 主升精选收益归因 + 退出网格（发现：成交假设支配结论）
    "quant/gen_attrib_page.py",       # 上述结论证据页生成器 → web/docs/selected_attrib_evidence.html
    "quant/_exit_sim.py",             # ★ 移动止盈「单一退出模拟口径」（日内路径 × 跳空 两个开关）
    "quant/_exit_assumption_audit.py",  # ★ 在生产主升面板上复核生产胜率的成交假设审计
    "quant/gen_exit_gate_page.py",    # 上述审计证据页生成器 → web/docs/exit_assumption_evidence.html
    # ---- 成交假设审计「推广到全部池」（2026-10-05）----
    "quant/_env_gate_lab.py",         # ★ 主升精选出票依据（环境门控）→ 加 --mode legacy|realistic 两口径
    "quant/_env_gate_lab_realistic.json",  # 可实现口径产物（env_gate.html 第七节的对照数字来源）
    "quant/_selected_model_realistic.json",  # 可实现口径截断曲线（lab.html 右两列 + 证据页第七节来源）
    "quant/_3yl_lab.py",              # ★ 三连阴 outcome_gap（只修跳空：穿线日按开盘价成交）
    "quant/_3yl_tier_gate.py",        # 三连阴门禁 + exit_assumption 段
    "quant/_3yl_gate_page.py",        # 三连阴证据页 → web/three_yin/tier_gate.html
    "quant/_tplus_lab.py",            # ★ 做T _sim_realistic（反T 遵守 A 股 T+1：当日买不可当日卖）
    "quant/_tplus_tier_gate.py",      # 做T门禁 + exit_assumption 段
    "quant/_tplus_gate_page.py",      # 做T证据页 → web/tplus/tier_gate.html
    "web/accumulation/accum_result.json",  # 回测汇总（模块组合/敏感性，供主页卡与审计）
    # 消融/样本外结论：build_accum._ablate_block() 动态读这两个 JSON 渲染页面结论，
    # 不推送 → 线上页面会退化成「尚未运行」，等于结论丢失。
    "web/accumulation/accum_ablate.json",
    "web/accumulation/accum_oos.json",
    # ---- 数据与逻辑一致性审计「统一获取 / 不重复 / 筛选严格」（2026-10-05）----
    "quant/_gate_common.py",          # ★ 出票许可公共统计层（跨窗口判据 tier_license_windows 单一真源）
    "quant/_accum_tier_gate.py",      # ★ 增仓池分档门禁（判据统一 + 数据有效性闸 + 窗口固定 2000）
    "quant/_rev_gate_page.py",        # 反转池证据页生成器（许可返回值的语义反义修正）
    "quant/_data_integrity_audit.py", # ★ 上述审计结论证据页生成器 → web/docs/data_integrity_audit.html
    "web/docs/data_integrity_audit.html",  # ★ 生成的证据页本体（supplement 已含生成器，
                                           #   但页面改动不走生成器 → 不登记就永远不更新上线）
    "quant/_longk.py",                # ★ 长K单一加载层（mtime 感知进程内缓存 + 缺文件不静默回退）
    "quant/_txk.py",                  # ★ 日K主缓存单一加载层（同 _longk：缓存 + 陈旧 fail-safe + WB_TXK_LOG）
    # ↓ 原漏网：不在 FILES = 线上不存在 = 结论不可复现（2026-10-05 补）
    "quant/daily_all.py",             # 13 步主入口（它不在自己链路里，故由 _coverage_check 的 C2 单列）
    "quant/_apply_theme.py",          # 主题注入层（丢注入层会让页面没样式，务必在册）
    "quant/backtest_picks.py",        # step7 回测
    "quant/_selected_lab.py",         # 主升精选选股模型（主推池的依据）
    "quant/_rev_lab.py",              # 底部反转面板
    "quant/_rev_tier_gate.py",        # 反转分档门禁
    "quant/_hw_tier_gate.py",         # 高胜率分档门禁
    "quant/_hw_gate_page.py",         # 高胜率证据页
    "quant/_tplus_env_gate.py",       # 做T池环境门控
    "quant/_macd_offline.py",         # MACD 离线口径
]

# 自动纳入「带日期/版块」的页面与数据源，保证每一页都带统一导航、且数据可复现。
# 与 FILES 去重；EXCLUDE_FRAGMENTS 仍生效（不推送持仓/选股类文件）。
_AUTO_PATTERNS = [
    # 所有分层网页（递归）
    "web/**/*.html",
    # 龙虎榜 / 行情 / 涨停 / 大盘 当日与历史快照
    "quant/lhb/2026-*.json",
    "quant/quotes/2026-*.json",
    "quant/board_hot/2026-*.json",
    "quant/limitup/2026-*.json",
    "quant/market_overview/2026-*.json",
    "quant/exec_chg/2026-*.json",
    "quant/lhb_detail/*.json",
    # 板块强度
    "quant/sector_industry_2026*.json",
    "quant/sector_concept_2026*.json",
    "quant/sector_strength_data_2026*.json",
    "quant/sector_daily/2026-*.json",
    "quant/sector_trend.json",
    # 大宗交易
    "quant/block_chg/2026-*.json",
    "quant/quotes/block_2026-*.json",
    # 龙虎榜富集 / 次日回测 / 要闻 / 申万映射
    "quant/lhb_enriched_*.json",
    "quant/lhb_nextday_backtest/2026-*.json",
    "quant/sw2_chg_live.json",
    "quant/sw1_detail.json",
    "quant/news.json",
    # 心理雷达构建脚本（仍在 market-trend/，输出到 web/psychology/）
    "market-trend/*.py",
    # 数据中心静态切片（查询页数据源，由 quant/db_export.py 生成）
    "web/data/*.json",
    # 增仓精选每日统计快照（供门户卡片取数；历史累积 quant/accum/history.json 属本地，不推送）
    "web/accumulation/stat_*.json",
    # ⚠ 下面三族同样是「门户卡片取数用的每日 stat 快照」，早先漏在本清单外 →
    #   页面能推、stat json 推不上去，门户在远端会读不到数。os.walk 兜底只捞 .html，救不了 json。
    "web/selected/stat_*.json",
    "web/quant_strategy/stat_*.json",
    "web/three_yin/stat_*.json",
    "web/picks/stable_*.json",
]
# 覆盖度自检机制（2026-09-11 新增）：主题源 + 页面登记表 + 自检/归位/校验脚本
for _p in ("quant/_theme.css", "quant/_app.js", "quant/_page_registry.py",
           "quant/_coverage_check.py", "quant/_fix_orphans.py",
           "quant/_js_check.py", "quant/_sync_all.py", "quant/_curl_gate.py",
           "quant/_verify_psy_hub.py", "quant/_verify_psy_pages.py"):
    if _p not in FILES:
        FILES.append(_p)
_AUTO_ADDED = []
for _pat in _AUTO_PATTERNS:
    for _p in sorted(_glob.glob(os.path.join(ROOT, _pat), recursive=True)):
        _rel = os.path.relpath(_p, ROOT).replace(os.sep, "/")
        if _rel not in FILES:
            FILES.append(_rel)
            _AUTO_ADDED.append(_rel)
# 递归兜底：背景模式下 ** 递归 glob 偶发返回空，改用 os.walk 保证 web/ 下所有层级 html 都被纳入
for _root, _dirs, _files in os.walk(os.path.join(ROOT, "web")):
    for _fn in _files:
        if _fn.endswith(".html"):
            _rel = os.path.relpath(os.path.join(_root, _fn), ROOT).replace(os.sep, "/")
            if _rel not in FILES:
                FILES.append(_rel)
                _AUTO_ADDED.append(_rel)
if _AUTO_ADDED:
    print(f"[auto] 纳入 {len(_AUTO_ADDED)} 个带日期/版块页面与数据源以确保结构一致")

def api_req(url, data=None, method="GET"):
    import time as _time
    last = None
    for _attempt in range(4):
        try:
            req = urllib.request.Request(url, data=data, method=method)
            req.add_header("Authorization", f"Bearer {TOKEN}")
            req.add_header("Accept", "application/vnd.github+json")
            if data is not None:
                req.add_header("Content-Type", "application/json")
            return urllib.request.urlopen(req, timeout=120)
        except (urllib.error.HTTPError,) as e:
            if e.code == 404:
                raise
            last = e
            _time.sleep(2 + _attempt * 2)
        except Exception as e:  # 瞬时网络错误（IncompleteRead / 连接重置等）重试
            last = e
            _time.sleep(2 + _attempt * 2)
    raise last

def get_sha(path):
    try:
        with api_req(f"{API}/{path}?ref={BRANCH}") as r:
            return json.load(r).get("sha")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise

def push_file(rel):
    if any(frag in rel for frag in EXCLUDE_FRAGMENTS):
        print(f"  ⛔ 跳过(命中排除名单): {rel}")
        return
    local = os.path.join(ROOT, rel)
    if not os.path.exists(local):
        print(f"  跳过(不存在): {rel}")
        return
    with open(local, "rb") as f:
        raw = f.read()
    # 防御性清洗：剥离桌面预览注入的 data-page-node-id（污染），保证推送出去的 HTML 干净
    if rel.endswith(".html"):
        try:
            txt = raw.decode("utf-8")
            txt = re.sub(r' data-page-node-id="[^"]*"', "", txt)
            raw = txt.encode("utf-8")
        except Exception:
            pass
    content = base64.b64encode(raw).decode("ascii")
    sha = get_sha(rel)
    body = {
        "message": f"{COMMIT_MSG}（{rel}）",
        "content": content,
        "branch": BRANCH,
    }
    if sha:
        body["sha"] = sha
    url = f"{API}/{rel}"
    try:
        with api_req(url, data=json.dumps(body).encode("utf-8"), method="PUT") as r:
            ok = json.load(r)
            print(f"  {'更新' if sha else '新建'} 成功: {rel} -> {ok.get('commit',{}).get('html_url','')}")
    except urllib.error.HTTPError as e:
        print(f"  ❌ 失败 {rel}: HTTP {e.code} {e.read().decode('utf-8','replace')[:200]}")

def _prepare(rel):
    """读出待推内容的最终字节（含与 push_file 相同的防御性清洗）。不存在返回 None。"""
    local = os.path.join(ROOT, rel)
    if not os.path.exists(local):
        return None
    with open(local, "rb") as f:
        raw = f.read()
    if rel.endswith(".html"):
        try:
            txt = raw.decode("utf-8")
            txt = re.sub(r' data-page-node-id="[^"]*"', "", txt)
            raw = txt.encode("utf-8")
        except Exception:
            pass
    return raw


def local_blob_sha(raw):
    """git blob sha —— 与 GitHub contents API 返回的 sha 同口径，用于 dry-run 比对。"""
    import hashlib
    h = hashlib.sha1()
    h.update(b"blob %d\0" % len(raw))
    h.update(raw)
    return h.hexdigest()


def dry_run(targets):
    """只比对本地与远端 blob sha，列出「待推/已一致/缺失」，不写入任何东西。

    ★ 2026-10-05 加：此前本脚本**没有 --dry-run**，误传该参数会被 argparse 之外
      的写法静默忽略 → 直接真实全量推送。补上后，推送前可先核对清单。
    """
    new = upd = same = miss = 0
    pend = []
    for rel in targets:
        raw = _prepare(rel)
        if raw is None:
            miss += 1
            print(f"  缺失(本地不存在): {rel}")
            continue
        remote = get_sha(rel)
        if remote is None:
            new += 1
            pend.append(rel)
            print(f"  [新建] {rel}")
        elif remote == local_blob_sha(raw):
            same += 1
        else:
            upd += 1
            pend.append(rel)
            print(f"  [更新] {rel}")
    print(f"\n=== dry-run 汇总 === 待推 {len(pend)} 个（新建 {new} / 更新 {upd}）｜"
          f"已一致 {same} 个｜本地缺失 {miss} 个")
    print("（dry-run：未写入任何文件。确认无误后去掉 --dry-run 再跑。）")
    return pend


if __name__ == "__main__":
    import argparse
    _ap = argparse.ArgumentParser(add_help=True,
                                  description="推送 web/ 全站页面、生成器与数据源到 GitHub")
    _ap.add_argument("--dry-run", action="store_true",
                     help="只列出与远端的差异（新建/更新/已一致），不实际推送")
    _ap.add_argument("--only", default=None,
                     help="只处理路径含该子串的文件（便于小批量推送）")
    _a, _unknown = _ap.parse_known_args()
    if _unknown:
        print("⚠ 忽略无法识别的参数：%s" % " ".join(_unknown))
    if not TOKEN:
        print("未检测到 GH_PAT / GITHUB_TOKEN 环境变量，无法推送。")
        print("请先执行： export GH_PAT=你的GitHubPAT  然后再运行本脚本。")
        sys.exit(2)
    _targets = [r for r in FILES if (not _a.only or _a.only in r)]
    print(f"推送到 {REPO}@{BRANCH} ... 目标 {len(_targets)} 个文件"
          + ("（dry-run，不写入）" if _a.dry_run else ""))
    if _a.dry_run:
        dry_run(_targets)
        sys.exit(0)
    for rel in _targets:
        push_file(rel)
    print("完成。")
