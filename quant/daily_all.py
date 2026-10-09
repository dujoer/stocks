# -*- coding: utf-8 -*-
"""每日全链编排器 —— 一条命令跑完 15 步（SOP 落地执行版）。

为什么需要它：`build_portal.py` 里的 `update_steps` 是**给人看的清单**，
`daily_update.py` 只串了 2 步（龙虎榜 + 门户），其余 13 步全靠人记、手动敲 ——
这是每日更新最容易漏步骤、进而「旧数据冒充当日」的根源。

本脚本把 SOP 拆成两类：
  * **AUTO**（本脚本自动跑，纯本地脚本、不需要 MCP 联网抓取）
  * **MANUAL**（必须由 agent/用户经 westock MCP 实拉当日原始数据才能跑；
    本脚本**只检测落盘是否就绪并跳过**，绝不拿旧数据凑 —— 这条是红线）

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
    (1, "auto", "统一数据底座（8 维度汇总）",
     "_datahub.py --date {D}", "_datahub.py --date {D}"),
    (2, "auto", "龙虎榜主看板",
     "build_lhb_enriched.py --date {D} && build_dashboards.py --date {D}",
     ["build_lhb_enriched.py --date {D}", "build_dashboards.py --date {D}"]),
    (3, "manual", "高管增减持（需 MCP tool_event(manager_sharechg)）",
     "gen_exec.py --date {D} && build_exec.py --date {D}",
     ["gen_exec.py --date {D}", "build_exec.py --date {D}"]),
    (4, "manual", "大宗交易（需 MCP block_past_30）",
     "gen_block.py --date {D} && build_block.py --date {D}",
     ["gen_block.py --date {D}", "build_block.py --date {D}"]),
    # ★ 2026-10-09 修：原命令写的是占位符 `<f>`（照抄人工指引），实际执行必然退出码 1
    #   —— 表现为「板块强度每天报失败」。现改为真实路径（cwd=quant）。
    (5, "manual", "★ 板块强度（不可回溯，漏跑永久断档）",
     "run_daily_sector.py --date {D} --industry sector_industry_{DS}.json "
     "--concept sector_concept_{DS}.json",
     ["sector_industry_{DS}.json", "sector_concept_{DS}.json"]),
    (6, "auto", "群体心理风险雷达（读 ①~⑤ 产物）",
     "build_psychology.py --date {D}", "build_psychology.py --date {D}"),
    # ★ 2026-10-09 补：`build_selected.py`（主升精选=主推模块）此前**从未进过链路**，
    #   线上 `web/selected/` 一直靠手工跑（10-08 之后停更 → coverage 报 selected 缺期）。
    #   纯本地（读全市场日K + 冻结模型），1s 级，与精选池同族，并入本步。
    (7, "auto", "精选池 + 主升精选：生成 → 归档 → 构建 → 回测 → 稳健分选",
     "gen_picks.py --date {D} --window 20 --top 40; build_picks.py --date {D}; "
     "backtest_picks.py; scan_stable.py --date {D}; build_selected.py {D}",
     ["gen_picks.py --date {D} --window 20 --top 40", "build_picks.py --date {D}",
      "backtest_picks.py", "scan_stable.py --date {D}", "build_selected.py {D}"]),
    (8, "auto", "做T池：强势扫描 → 三源并集 → 引擎",
     "scan_strong.py --date {D} && gen_tplus.py --date {D} && build_tplus.py --date {D}",
     ["scan_strong.py --date {D}", "gen_tplus.py --date {D}", "build_tplus.py --date {D}"]),
    (9, "auto", "反转池（本地日K，无需联网）",
     "rev_pool.py run {D}; fetch_rev_flow.py --date {D} --src sina; "
     "fetch_rev_enrich.py --date {D} --render; gen_watchlist.py {D}",
     ["rev_pool.py run {D}", "fetch_rev_flow.py --date {D} --src sina",
      "fetch_rev_enrich.py --date {D} --render", "gen_watchlist.py {D}"]),
    (10, "auto", "MACD + 高胜率（离线链：本地日K + 新浪资金流）",
     "_gen_macd_offline_all.py --date {D}",
     ["_gen_macd_offline_all.py --date {D}"]),
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
    (13, "auto", "量化策略板 + 全市场横截面 + 三连阴观察池",
     "build_quant_strategy.py {D}; build_cross_section.py --date {D}; build_3yl.py {D}",
     ["build_quant_strategy.py {D}", "build_cross_section.py --date {D}",
      "build_3yl.py {D}"]),
    (14, "auto", "数据库 + 门户 + 板块 + 主题收尾",
     "db_update.py {D}; db_export.py; build_portal.py; build_sections.py; _apply_theme.py",
     ["db_update.py {D}", "db_export.py", "build_portal.py", "build_sections.py",
      "_apply_theme.py"]),
    (15, "gate", "五道门禁（链接/JS/覆盖/策略/数据底座）",
     "_link_check.py; _js_check.py --all; _coverage_check.py --until {D}; "
     "_strategy_gate.py; _datahub_gate.py --date {D}",
     ["_link_check.py", "_js_check.py --all", "_coverage_check.py --until {D}",
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
