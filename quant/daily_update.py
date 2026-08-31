# -*- coding: utf-8 -*-
"""每日盘后一键编排：生成龙虎榜主看板 + 刷新总门户。

用法：
  python daily_update.py                 # 以今天为数据日期
  python daily_update.py 2026-08-31     # 指定数据日期

说明：
  - 本脚本负责「龙虎榜主看板」(build_dashboards) 与「总门户」(build_portal) 的自动化串联。
  - 板块强度 / 群体心理风险雷达 / 自下而上选股 三个子系统各有独立构建脚本与数据拉取步骤，
    需在运行本脚本前/后，按 quant/DAILY_UPDATE_SOP 完成对应数据落盘与构建（脚本会打印提示）。
  - 前置：当日 quant/{market_overview,board_hot,quotes,limitup,lhb}/*.json 与 news.json 须已落盘。
"""
import os, sys, subprocess, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QUANT = os.path.join(ROOT, "quant")
PY = r"C:\Users\nonoy\.workbuddy\binaries\python\versions\3.13.12\python.exe"

DATE = sys.argv[1] if len(sys.argv) > 1 else datetime.date.today().strftime("%Y-%m-%d")

def run(script, *args):
    cmd = [PY, os.path.join(QUANT, script)] + list(args)
    print(f"\n>>> 运行 {script} {' '.join(args)}")
    r = subprocess.run(cmd, cwd=QUANT)
    if r.returncode != 0:
        print(f"!! {script} 返回非零退出码 {r.returncode}")
    return r.returncode

print(f"=== A股每日更新编排 · 数据日期 {DATE} ===")

# 1) 龙虎榜主看板
rc = run("build_dashboards.py", "--date", DATE)
if rc != 0:
    print("龙虎榜主看板生成失败，中止。请检查 quant 下当日数据文件是否齐全。")
    sys.exit(rc)

# 2) 总门户（自动扫描各子系统最新日期）
run("build_portal.py")

print(f"""
=== 已完成 ===
  · 龙虎榜主看板 (web/) 已按 {DATE} 刷新
  · 总门户 (index.html) 已重建

=== 仍需你手动完成的子系统（各自有独立构建步骤） ===
  [板块强度]      若行业/概念快照已落盘 -> python quant\\run_daily_sector.py --date {DATE} --industry <file> --concept <file>
  [心理风险雷达]   按 market-trend/_build 范式，用当日 westock 真实数据生成 crowd-psychology-risk-radar-{DATE}.html 并入索引
  [自下而上选股]   产出 web/bottom-up-stock-picks-{DATE}.html
  完成以上任一项后，再次运行 python quant\\build_portal.py 即可让总门户带出最新日期。

=== 校验与推送 ===
  · 检查无外链/死链、JS 语法；
  · 经 GitHub 连接器推送 web/ 与 market-trend/ 至仓库。
""")
