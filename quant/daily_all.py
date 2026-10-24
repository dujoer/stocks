# -*- coding: utf-8 -*-
"""每日全链编排器 —— 一条命令跑完 15 步（SOP 落地执行版）。

为什么需要它：`build_portal.py` 里的 `update_steps` 是**给人看的清单**，
`daily_update.py` 只串了 2 步（龙虎榜 + 门户），其余 13 步全靠人记、手动敲 ——
这是每日更新最容易漏步骤、进而「旧数据冒充当日」的根源。

本脚本把 SOP 拆成：
  * **AUTO**（本脚本自动跑，含联网取数）
  * **MANUAL**（历史上需经 westock MCP 实拉当日原始数据；但 westock MCP 长期 502
    且 mcp.json 未配置，故已改为由第 1 步的 `_fetch_manual.py` 经 westock CLI + 东财
    **自动补齐**，不再依赖 MCP。原 MANUAL 步（lhb/exec/block/sector）已转 AUTO。）

★ 取数通道：westock MCP 已**旁路**（不依赖、不重试）。板块强度/龙虎榜主榜走 westock CLI
  （与 MCP 同源同口径），大宗/高管/龙虎榜席位明细走东财数据中心接口。任一路源失败，
  对应步会失败并停止推送（绝不拿旧数据凑）。

用法：
    python quant/daily_all.py                      # 自动取最新数据日
    python quant/daily_all.py 2026-09-30           # 指定数据日期
    python quant/daily_all.py --date 2026-09-30 --push    # 跑完并推送
    python quant/daily_all.py --date 2026-09-30 --only auto     # 只跑自动段
    python quant/daily_all.py --date 2026-09-30 --from 9 --to 13   # 只跑第 9~13 步
    python quant/daily_all.py --check             # 只体检：哪些步能做/哪些缺数据
    python quant/daily_all.py --list              # 打印全部步骤与命令

★ 关于「数据日期」：默认取 **最新数据日**（各子系统快照日的最大值），不是日历今天。
  周末/节假日跑不会写出一个没有数据的日期。
"""
from __future__ import annotations
import os, re, sys, glob, json, argparse, subprocess, datetime, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QUANT = os.path.join(ROOT, "quant")
WEB = os.path.join(ROOT, "web")
PY = sys.executable

# 需要联网（MCP/沙箱外）的步骤：agent 必须先实拉原始数据落盘
PUSH = "PUSH"        # 需要 dangerouslyDisableSandbox 的步骤


def _latest_data_date():
    """取各子系统最新快照日的最大值 = 最新数据日（不是日历今天）。"""
    pats = [
        (os.path.join(QUANT, "market_overview", "*.json"), "mkt"),
        (os.path.join(QUANT, "hub", "2*.json"), "hub"),
        (os.path.join(QUANT, "lhb_enriched_*.json"), "lhb"),
        (os.path.join(QUANT, "exec_chg", "*.json"), "exec"),
        (os.path.join(QUANT, "block_chg", "*.json"), "blk"),
        (os.path.join(QUANT, "psy", "raw_*.json"), "psy"),
        (os.path.join(WEB, "macd", "watchlist_*.html"), "macd"),
        (os.path.join(QUANT, "tplus", "universe_*.json"), "tplus"),
    ]
    best = None
    for d, tag in pats:
        for p in sorted(glob.glob(d)):
            m = re.search(r"(\d{4})[-_]?(\d{2})[-_]?(\d{2})", os.path.basename(p))
            if not m:
                continue
            try:
                dt = datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except ValueError:
                continue
            if best is None or dt > best:
                best = dt
    return best or datetime.date.today()


def _has(*relpats):
    """判断依赖文件是否已落盘（用于 MANUAL 段的「数据是否就绪」）。"""
    for rp in relpats:
        if not glob.glob(os.path.join(QUANT, rp)):
            return False
    return True


# ── 步骤表 ────────────────────────────────────────────────────────────
# kind: auto（直接跑） / manual（须先实拉，脚本只检依赖） / gate（校验）
STEPS = [
    # ★ 2026-10-12 修：大盘快照与各池行情此前**从未进过日更链路** ——
    #   而这正是「步骤 ②⑥⑧ 每次必崩」的单一根因，且崩得完全没有报错线索：
    #      · build_psychology   [fail] 缺少 quant/market_overview/{D}.json
    #      · build_tplus        [build_tplus] 缺少 quant/tplus/quotes_{D}.json
    #      · _datahub_gate      [FAIL] quotes/{D}.json、picks/quotes_{D}.json 缺失
    #   按本站铁律「没进 daily_all = 不会更新，且没有任何报错」，补登记这两个生成器。
    # ★ 2026-10-13 修（两个真问题，干净环境必爆）：
    #   ① **全市场日K刷新必须排在第 1 步首位**。_gen_market_overview_offline.py 直接读
    #      `_txk_cache.json`（不经过 hub），`scan_one_day(code, bars, TGT_D)` 对末根
    #      < TGT_D 的票返回 None —— 缓存不刷新，market_overview 就写「涨0 跌0 涨停0」
    #      空壳且退出码 0；同时 _datahub.py 的新鲜度自检（_T.stale_codes，asof=数据日）
    #      会把 >2% 陈旧的缓存判 FAIL（10-13 实测 5051/5051 全陈旧 → 闸 FAIL）。
    #      此前链路里**没有任何一步**做全市场日K刷新（fetch_full_kline 只补缺失标的、
    #      跳过已缓存；MACD 离线链只补自己那一小池）—— 又是「没进 daily_all」。
    #   ② **长K（780 根 / 3.2 年）同样必须日更**。它喂 _datahub 的 kline 维度与龙道诀
    #      胜率统计（_dragon_odds 样本期），此前全靠手工补 → 长K 永远比短K 慢一天，
    #      datahub 闸每天报「双缓存涨停判定不一致（短 67 / 长 0）」。
    #      ⚠ 判据是「末根日期 < asof」不是根数（旧判据「根数达标就跳过」会让达标票
    #      永远补不进最新交易日，一直停在补数那一天）—— 这正是 --asof 的存在理由。
    #   ③ **_datahub.py 必须排在 _gen_pool_quotes.py 之前**：后者 market 段读
    #      `hub/{DS}.json` 的 dims.quotes（_gen_pool_quotes.py:174-177），hub 不存在
    #      就静默打印「market 跳过：hub 无 quotes」→ quotes/{D}.json 缺 market 段。
    # ★ 2026-10-15 修（根治 westock MCP 长期 502）：原本 ②③④⑤ 标为 MANUAL，只检依赖、
    #   不在就跳过，等 agent 经 MCP 实拉 —— 而 MCP 根本没配置（mcp.json 无 westock），
    #   导致每天手动降级补齐。现把 proven 的降级路径固化为主路径：第 1 步末尾接
    #   `_fetch_manual.py`（走 westock CLI + 东财，不依赖 MCP），②~⑤ 改为 AUTO 自跑。
    (1, "auto", "全市场日K/长K刷新 + 大盘概览 + 统一数据底座 + 各池行情 + 补齐 manual 原始数据",
     "_txk_refresh.py --end {D}; _fetch_long_kline.py --n 780 --asof {D}; "
     "_gen_market_overview_offline.py --date {D}; "
     "_datahub.py --date {D}; _gen_pool_quotes.py --date {D} && "
     "_fetch_manual.py --date {D}",
     ["_txk_refresh.py --end {D}", "_fetch_long_kline.py --n 780 --asof {D}",
      "_gen_market_overview_offline.py --date {D}", "_datahub.py --date {D}",
      "_gen_pool_quotes.py --date {D}", "_fetch_manual.py --date {D}"]),
    (2, "auto", "龙虎榜主看板（读 _fetch_manual 落盘的 lhb 主榜 + 席位明细）",
     "build_lhb_enriched.py --date {D} && build_dashboards.py --date {D}",
     ["build_lhb_enriched.py --date {D}", "build_dashboards.py --date {D}"]),
    (3, "auto", "高管增减持（东财降级源，_fetch_manual 已落盘 _raw_em_{D}.json）",
     "gen_exec.py --date {D} --src exec_chg/_raw_em_{D}.json && build_exec.py --date {D}",
     ["gen_exec.py --date {D} --src exec_chg/_raw_em_{D}.json", "build_exec.py --date {D}"]),
    (4, "auto", "大宗交易（东财降级源，_fetch_manual 已落盘 _raw_em_{D}.json）",
     "gen_block.py --date {D} --src block_chg/_raw_em_{D}.json && build_block.py --date {D}",
     ["gen_block.py --date {D} --src block_chg/_raw_em_{D}.json", "build_block.py --date {D}"]),
    # ★ 2026-10-09 修：原命令写的是占位符 `<f>`（照抄人工指引），实际执行必然退出码 1
    #   —— 表现为「板块强度每天报失败」。现改为真实路径（cwd=quant）。
    # ★ 2026-10-15 修：run_daily_sector 的 --industry/--concept 经 collect_sector.py 子进程时
    #   cwd 切到 quant/，相对路径会 FileNotFoundError → **必须绝对路径**（QUANT 固定值）。
    (5, "auto", "★ 板块强度（不可回溯，漏跑永久断档；westock CLI 同源落盘）",
     "run_daily_sector.py --date {D} "
     "--industry /Users/jackal/Downloads/workbuddy/股票/quant/sector_industry_{DS}.json "
     "--concept /Users/jackal/Downloads/workbuddy/股票/quant/sector_concept_{DS}.json",
     ["sector_industry_{DS}.json", "sector_concept_{DS}.json"]),
    (6, "auto", "群体心理风险雷达（读 ①~⑤ 产物）",
     "build_psychology.py --date {D}", "build_psychology.py --date {D}"),
    # ★ 2026-10-09 补：`build_selected.py`（主升精选=主推模块）此前**从未进过链路**，
    #   线上 `web/selected/` 一直靠手工跑（10-08 之后停更 → coverage 报 selected 缺期）。
    #   纯本地（读全市场日K + 冻结模型），1s 级，与精选池同族，并入本步。
    # ★ 2026-10-12 补：`build_picks.py` 需要 `picks/quotes_{D}.json`，而它只能由
    #   `_gen_pool_quotes.py` 在 **gen_picks 产出 candidates 之后** 才能补出来 ——
    #   所以这一步必须插在 gen_picks 与 build_picks 之间（幂等，重复跑无害 ~15s）。
    (7, "auto", "精选池 + 主升精选：生成 → 补行情 → 归档 → 构建 → 回测 → 稳健分选",
     "gen_picks.py --date {D} --window 20 --top 40; _gen_pool_quotes.py --date {D}; "
     "build_picks.py --date {D}; "
     "backtest_picks.py; scan_stable.py --date {D}; build_selected.py {D}",
     ["gen_picks.py --date {D} --window 20 --top 40", "_gen_pool_quotes.py --date {D}",
      "build_picks.py --date {D}",
      "backtest_picks.py", "scan_stable.py --date {D}", "build_selected.py {D}"]),
    # ★ 2026-10-12 补：`build_tplus.py` 需要 `tplus/quotes_{D}.json` 与 `tplus/kline_{D}.json`，
    #   二者同样来自 `_gen_pool_quotes.py`，且该脚本要读 `scan_strong` 产出的票池清单
    #   —— 因此必须排在 scan_strong 之后、build_tplus 之前（幂等）。
    (8, "auto", "做T池：强势扫描 → 补行情 → 三源并集 → 引擎",
     "scan_strong.py --date {D}; _gen_pool_quotes.py --date {D}; "
     "gen_tplus.py --date {D}; build_tplus.py --date {D}",
     ["scan_strong.py --date {D}", "_gen_pool_quotes.py --date {D}",
      "gen_tplus.py --date {D}", "build_tplus.py --date {D}"]),
    (9, "auto", "反转池（本地日K，无需联网）",
     "rev_pool.py run {D}; fetch_rev_flow.py --date {D} --src sina; "
     "fetch_rev_enrich.py --date {D} --render; gen_watchlist.py {D}",
     ["rev_pool.py run {D}", "fetch_rev_flow.py --date {D} --src sina",
      "fetch_rev_enrich.py --date {D} --render", "gen_watchlist.py {D}"]),
    # ★ 2026-10-13 修：`_hw_tier_gate.py`（高胜率出票合法性证据，gen_highwin.py:341 每天读它）
    #   此前**从未进过日更链路** —— 证据 JSON 停在 10-08（面板止 09-30）、step3 派生停在 10-04，
    #   而底池已被离线链重扫 →「过期证据冒充当日」（既能误拒、也可能误放行，方向可逆）。
    #   _page_registry 的闸页面族早已声明这两条命令（script 字段），此处只是补接线。
    #   冒烟测试（--limit 200 --sens）2s 通过；全量约 1 分钟。排在离线链**之前**：
    #   ① 证据面板只用截至昨日的数据（无前视）；② gen_highwin 当天读到的即是新证据。
    (10, "auto", "高胜率出票闸证据 + MACD + 高胜率（离线链：本地日K + 新浪资金流）",
     "_hw_tier_gate.py; _hw_tier_gate.py --sens --step 3; "
     "_gen_macd_offline_all.py --date {D}",
     ["_hw_tier_gate.py", "_hw_tier_gate.py --sens --step 3",
      "_gen_macd_offline_all.py --date {D}"]),
    (11, "auto", "增仓精选（含融资融券日频更新）",
     "_fetch_margin_em.py --workers=8; build_accum.py {D}",
     ["_fetch_margin_em.py --workers=8", "build_accum.py {D}"]),
    # ★ 2026-10-08 补登记：龙道诀全模块此前**从未进过日更链路**（页面停在手工跑的那天）。
    #   顺序有讲究：先出证据产物（odds/stage_use/pos_rule/tier_gate），最后 build_dragon 才渲染页面。
    (12, "auto", "龙道诀（情绪周期 · 四道检验 · 出票闸 · 页面）",
     "_dragon_odds.py --date {D}; _dragon_stage_use.py --date {D}; "
     "_dragon_pos_rule.py --date {D}; _dragon_tier_gate.py --date {D} --emit; "
     "build_dragon.py --date {D}",
     ["_dragon_odds.py --date {D}", "_dragon_stage_use.py --date {D}",
      "_dragon_pos_rule.py --date {D}", "_dragon_tier_gate.py --date {D} --emit",
      "build_dragon.py --date {D}"]),
    # ★ 2026-10-09 补登记：这三个模块此前**从未进过日更链路**（build_quant_strategy /
    #   build_cross_section / build_3yl 全靠手工跑，页面停在 09-30 那一次）。
    #   三者都只读本地日K + hub 底座，不联网，单次合计 <5s，放在收尾前安全。
    # ★ 2026-10-12 补登记：「精中取精」两页（build_selected_elite / build_highwin_elite）此前
    #   完全在链路外，靠手工跑 → coverage 报「未登记页面」且停在旧数据日。
    #   放在第 13 步（第 14 步注入导航之前），保证新产出的页面能拿到统一导航与主题。
    (13, "auto", "量化策略板 + 全市场横截面 + 三连阴 + 精中取精 + 研报分析（观察候选）",
     "build_quant_strategy.py {D}; build_cross_section.py --date {D}; build_3yl.py {D}; "
     "build_selected_elite.py {D}; build_highwin_elite.py {D}; build_n_shape.py {D}; "
     "build_n_shape_backtest.py {D}; build_n_shape_sim.py {D}; build_research.py {D}",
     ["build_quant_strategy.py {D}", "build_cross_section.py --date {D}",
      "build_3yl.py {D}", "build_selected_elite.py {D}", "build_highwin_elite.py {D}",
      "build_n_shape.py {D}", "build_n_shape_backtest.py {D}", "build_n_shape_sim.py {D}",
      "build_research.py {D}"]),
    # ★ 2026-10-13 修：孤儿页（无任何入链的归档页）此前靠手工跑 `_fix_orphans.py`，
    #   而各索引页每天被自家生成器重建 → 插好的归档链接块**第二天就被冲掉**，
    #   孤儿数从 0 反弹到 55（coverage 报 GAP、exit 1）。又是「没进 daily_all」。
    #   _fix_orphans 幂等（先删旧块再插），必须排在**所有页面生成器与主题注入之后**。
    (14, "auto", "数据库 + 门户 + 板块 + 热力图 + 主题收尾 + 孤儿页回链",
     "db_update.py {D}; db_export.py; build_portal.py; build_sections.py; "
     "build_sector_heatmap.py; _apply_theme.py; _fix_orphans.py",
     ["db_update.py {D}", "db_export.py", "build_portal.py", "build_sections.py",
      "build_sector_heatmap.py", "_apply_theme.py", "_fix_orphans.py"]),
    # ★ 2026-10-15 修：manual 原始数据（lhb/block/exec/sector）由 _fetch_manual 在第 1 步落盘，
    #   但第 1 步里的 _datahub.py 跑在取数之前 → hub 记录不到这些源。门禁前**必须重扫**底座，
    #   否则 _datahub_gate 会因「lhb 等缺失」FAIL（此前只能手动补跑 _datahub.py 才过）。
    (15, "gate", "刷新数据底座 + 五道门禁（链接/JS/覆盖/策略/数据底座）",
     "_datahub.py --date {D}; "
     "_link_check.py; _js_check.py --all; _coverage_check.py --until {D}; "
     "_strategy_gate.py; _datahub_gate.py --date {D}",
     ["_datahub.py --date {D}",
      "_link_check.py", "_js_check.py --all", "_coverage_check.py --until {D}",
      "_strategy_gate.py", "_datahub_gate.py --date {D}"]),
]

# MANUAL 步骤的取数指引（agent/用户照着做，做完再跑本脚本）
MANUAL_HOWTO = {
    # ★ 2026-10-09 补：这两步此前只说「降级期经东财回补」，但**没有可执行的降级脚本**，
    #   实际结果是 MCP 不通时这两块永久停在旧数据日（实测停在 09-30，页面读作「落后」）。
    #   现补 quant/_fetch_block_exec_em.py（东财数据中心接口，一条命令落 tool_event 同构格式）。
    3:  "① 优先：MCP tool_event(manager_sharechg, limit=700) 落 quant/exec_chg/_raw_tool_{D}.json → "
        "python quant/gen_exec.py --date {D} → python quant/build_exec.py --date {D}\n"
        "     ② MCP 不可用时（降级，一条命令取数）：python quant/_fetch_block_exec_em.py --date {D} --only exec\n"
        "        → python quant/gen_exec.py --date {D} --src quant/exec_chg/_raw_em_{D}.json "
        "--quotes quant/quotes/exec_{D}.json → python quant/build_exec.py --date {D}",
    4:  "① 优先：MCP block_past_30(limit=3000) 落 quant/block_chg/_raw_tool_{D}.json → "
        "python quant/gen_block.py --date {D} --src … → python quant/build_block.py --date {D}\n"
        "     ② MCP 不可用时（降级，一条命令取数）：python quant/_fetch_block_exec_em.py --date {D} --only block\n"
        "        → python quant/gen_block.py --date {D} --src quant/block_chg/_raw_em_{D}.json "
        "--quotes quant/quotes/block_{D}.json → python quant/build_block.py --date {D}\n"
        "     ⚠ 降级源不含北交所，且已剔 ETF/基金/转债；source 字段会如实标注降级源，勿手工改成 westock",
    5:  "① 优先：MCP industry(ranking, limit=300) + concept(limit=1000) 落盘后 → "
        "run_daily_sector.py --date {D} --industry <绝对路径> --concept <绝对路径>\n"
        "     ② MCP 不可用时（westock CLI 与 MCP 同源同口径，一条命令落盘）：\n"
        "        python quant/_westock_cli_fetch.py sector --date {D}  → 落 "
        "quant/sector_industry_{DS}.json / sector_concept_{DS}.json（12 字段同构，leader.code 按名称反查）\n"
        "        → python quant/run_daily_sector.py --date {D} "
        "--industry quant/sector_industry_{DS}.json --concept quant/sector_concept_{DS}.json\n"
        "     ③ 龙虎榜原始数据同理：python quant/_westock_cli_fetch.py lhb --date {D} → quant/lhb/{D}.json "
        "（主榜+机构/活跃席位/高胜率买入/高胜率席位）",
    10: "离线链一条命令：python quant/_gen_macd_offline_all.py --date {D}\n"
        "     _gen_macd_pool_offline（本地腾讯日K → 全市场正股初筛域）"
        " → _gen_tech_offline（本地日K 算 MACD/MA/RSI）"
        " → _gen_macd_flow_sina（新浪 20 日主力净流入）"
        " → _gen_hw_quote_offline（腾讯 qt 行情增强）"
        " → macd_build {DS} --raw → gen_macd → build_highwin → gen_highwin\n"
        "      ★ 2026-10-09：原依赖 westock MCP 三段原始数据，MCP 不通时 highwin/MACD 永久停更（曾停 09-23）。"
        "改离线链后每日可跑；口径如实标注 src=offline_txk_full（初筛域为全市场，非主力净流入 top200）",
}
# MANUAL 段各自额外的依赖判定（判定「当日原始数据是否已落盘」）
# 命名沿用各脚本自己的落盘约定：exec_chg/block_chg 用带横线日期，其余用紧凑 DS。
MANUAL_DEPS = {
    3:  ["exec_chg/{D}.json"],
    4:  ["block_chg/{D}.json"],
    5:  ["../web/sector/sector-strength-{DS}.html"],
}


def _channel_health(todo):
    """MANUAL 步依赖 westock MCP 实时取数。通道不通时**提前告知**，
    否则会表现为「跑了一堆 [skip] 什么都没有」，甚至让下游误以为数据已就绪。

    实测故障形态（2026-10-04）：端点端口可连，但 `initialize` 握手稳定返回
    500 internal_error —— 连握手都不通，不是调用姿势问题，重试无意义。
    """
    if not any(k == "manual" for _, k, _, _ in todo):
        return
    print("\n--- 取数通道体检 ---")
    try:
        sys.path.insert(0, QUANT)
        import _wsboot as _W
    except Exception as ex:
        print("  无法加载 _wsboot：%s" % ex)
        return
    try:
        _W.ensure()
        print("  westock MCP：正常")
    except SystemExit as ex:
        print("  westock MCP：✗ 握手失败 —— %s" % ex)
        print("  端点端口可连但 initialize 报 500 → 后端会话不可用（重试无用）。")
        print("  后果：第 ③④⑤⑩ 步取不到当日数据 → 本脚本会**诚实跳过**，不用旧数据凑。")
        print("  建议：重启 WorkBuddy 应用；或在连接器里检查 westock-mcp 状态。")
    except Exception as ex:
        print("  westock MCP：✗ 异常 —— %s" % ex)


#: [(命令, 秒数, 退出码)] —— 「有效率」自检的唯一数据源，不另设一套
TIMINGS = []


def run_one(cmd, dry=False):
    """跑一条命令（支持 && 与 ; 分隔）。返回 True 表示全部成功。"""
    ok = True
    for part in re.split(r"\s*&&\s*|\s*;\s*", cmd):
        part = part.strip()
        if not part:
            continue
        print("\n    $ python %s" % part)
        if dry:
            continue
        t0 = time.time()
        env = dict(os.environ)
        env["WB_TXK_LOG"] = "1"        # 开 txk 加载日志 → 收尾时能统计「128MB 到底解析了几次」
        r = subprocess.run([PY] + part.split(), cwd=QUANT, env=env)
        dt = time.time() - t0
        TIMINGS.append((part, round(dt, 2), r.returncode))
        print("    · 耗时 %.2fs（退出码 %d）" % (dt, r.returncode))
        if r.returncode != 0:
            print("    !! 退出码 %d —— %s" % (r.returncode, part))
            ok = False
    return ok


def _txk_summary():
    """汇总本轮所有子进程对 128MB 日K缓存的解析次数与耗时。

    这不是「优化了多少」的口号：把 `_txk_cache.json` 的加载次数数出来，
    才能证明统一层真的把重复解析降下来了（缺文件时不猜数字，返回 None）。
    """
    p = os.path.join(QUANT, "_txk_loadlog.jsonl")
    if not os.path.exists(p):
        return None
    rows = []
    try:
        with open(p, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
    except Exception:
        return None
    if not rows:
        return None
    per = {}
    for r in rows:
        k = r.get("script") or "?"
        per.setdefault(k, {"loads": 0, "secs": 0.0, "mb": 0.0})
        per[k]["loads"] += 1
        per[k]["secs"] = round(per[k]["secs"] + r.get("secs", 0.0), 3)
        per[k]["mb"] = round(per[k]["mb"] + r.get("mb", 0.0), 1)
    return {"n_loads": len(rows),
            "total_secs": round(sum(r.get("secs", 0.0) for r in rows), 2),
            "mb_per_load": rows[0].get("mb"),
            "total_mb_parsed": round(sum(r.get("mb", 0.0) for r in rows), 1),
            "per_script": [{"script": k, "loads": v["loads"], "secs": v["secs"],
                            "mb": v["mb"]} for k, v in sorted(per.items())]}


def dump_profile(date, failed):
    """落一份耗时清单：哪一步慢、慢多少。产物缺失一律不猜时间。"""
    if not TIMINGS:
        return None
    tot = round(sum(x[1] for x in TIMINGS), 2)
    slowest = sorted(TIMINGS, key=lambda x: -x[1])[:5]
    out = {"date": date, "n_cmds": len(TIMINGS), "total_secs": tot,
           "failed_steps": failed, "kline_load": None,
           "per_cmd": [{"cmd": c, "secs": s, "rc": rc} for c, s, rc in TIMINGS],
           "slowest": [{"cmd": c[:80], "secs": s} for c, s, _ in slowest]}
    try:
        import _longk
        out["kline_load"] = _longk.load_stats()
    except Exception:
        pass
    try:
        out["txk_load"] = _txk_summary()
    except Exception:
        pass
    p = os.path.join(QUANT, "_daily_profile.json")
    try:
        json.dump(out, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    except Exception as e:
        print("   （耗时清单落盘失败：%s）" % str(e)[:60])
    print("\n=== 耗时清单（%d 条命令，合计 %.1fs）===" % (len(TIMINGS), tot))
    for c, s, _ in sorted(TIMINGS, key=lambda x: -x[1])[:8]:
        print("    %7.2fs  %s" % (s, c[:96]))
    if out["kline_load"]:
        kl = out["kline_load"]
        print("    长K加载：%d 次 / %.2fs / %.1fMB（进程内共享缓存后应为 1 次）"
              % (kl["loads"], kl["secs"], kl["bytes_mb"]))
    tl = out.get("txk_load")
    if tl:
        print("    日K主缓存：%d 次解析 / 合计 %.2fs / 每次 %.1fMB"
              % (tl["n_loads"], tl["total_secs"], tl["mb_per_load"] or 0))
        for s in tl["per_script"][:6]:
            print("        %-28s %d 次 %.2fs" % (s["script"], s["loads"], s["secs"]))
        print("        ↑ 每脚本内多次 load 已由 _txk 进程内共享缓存合并")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("date_pos", nargs="?", default=None, help="数据日期 YYYY-MM-DD（可省）")
    ap.add_argument("--date", dest="date", default=None)
    ap.add_argument("--from", dest="frm", type=int, default=1)
    ap.add_argument("--to", dest="to", type=int, default=15)
    ap.add_argument("--only", dest="only", choices=["auto", "manual", "gate"], default=None)
    ap.add_argument("--push", action="store_true", help="跑完推送（沙箱外执行）")
    ap.add_argument("--check", action="store_true", help="只体检，不执行")
    ap.add_argument("--list", action="store_true", help="打印步骤表")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    if a.list:
        print("每日全链 15 步：")
        for n, kind, title, cmd, _ in STEPS:
            print("  %-3s %-6s %s" % (n, kind.upper(), title))
            print("       %s" % cmd)
            if n in MANUAL_HOWTO:
                print("       取数：%s" % MANUAL_HOWTO[n].replace("{D}", "{D}"))
        return

    D = a.date or a.date_pos or _latest_data_date().strftime("%Y-%m-%d")
    DS = D.replace("-", "")
    # 每轮清空 txk 加载日志：log 只描述「本轮」，profile 里的次数才可横向对比
    _lp = os.path.join(QUANT, "_txk_loadlog.jsonl")
    try:
        open(_lp, "w").close()
    except OSError:
        pass
    print("=== 每日全链 · 数据日期 %s（DS=%s）===" % (D, DS))
    if D == datetime.date.today().strftime("%Y-%m-%d"):
        print("提示：今天可能是非交易日。若无当日数据，请用 --date 指定最近交易日。")

    # 依赖就绪判定
    def deps_ok(n):
        for pat in MANUAL_DEPS.get(n, []):
            p = pat.replace("{D}", D).replace("{DS}", DS)
            if not glob.glob(os.path.join(QUANT, p)):
                return False, p
        return True, ""

    print("\n--- 体检（哪些步能做 / 哪些缺当日数据）---")
    todo = []
    for n, kind, title, cmd, dep in STEPS:
        if n < a.frm or n > a.to:
            continue
        if a.only and kind != a.only:
            continue
        if kind == "manual":
            ok, miss = deps_ok(n)
            tag = "可跑" if ok else "缺当日数据·跳过"
            print("  %-3s %-7s %-38s %s" % (n, kind.upper(), title, tag))
            if not ok:
                print("       缺：%s" % miss)
                print("       取数：%s" % MANUAL_HOWTO.get(n, "").replace("{DS}", DS))
        else:
            print("  %-3s %-7s %-38s 可跑" % (n, kind.upper(), title))
        todo.append((n, kind, title, cmd))

    if a.check:
        # 通道体检也要在 --check 里跑：这是「能不能更新当天数据」的前置条件
        _channel_health(todo)
        print("\n(check 模式，未执行任何命令)")
        return
    # MANUAL 步的取数通道体检：通道不通时提前告知，而不是跑完一堆 [skip] 才发现
    _channel_health(todo)

    print("\n--- 执行 ---")
    failed = []
    for n, kind, title, cmd in todo:
        if kind == "manual":
            ok, _miss = deps_ok(n)
            if not ok:
                print("\n[%s] %s —— ⏭ 跳过（缺当日原始数据）" % (n, title))
                print("     诚实跳过，不用旧数据冒充当日。取数指引见上（--check 可复看）。")
                continue
        print("\n[%s] %s" % (n, title))
        ok = run_one(cmd.format(D=D, DS=DS), dry=a.dry_run)
        if not ok:
            failed.append(n)
            # 门禁不过就停：后面步骤依赖前面的产物
            if kind == "gate":
                print("\n★ 门禁未通过，停止后续步骤（避免把不合格产物推上去）。")
                break

    if failed:
        print("\n=== 有失败的步骤：%s ===" % failed)
    else:
        print("\n=== 自动段全部完成 ===")
    dump_profile(D, failed)
    if any(k == "manual" for _, k, _, _ in todo):
        print("提示：MANUAL 段（③④⑤⑩）需先经 MCP 实拉当日原始数据，"
              "本脚本只检依赖、不代抓 —— 缺数据会诚实跳过。")

    if a.push and not failed:
        print("\n--- 推送（沙箱外）---")
        run_one("_push_incremental.py", dry=a.dry_run)


if __name__ == "__main__":
    main()
