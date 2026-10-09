# -*- coding: utf-8 -*-
"""MACD + 高胜率候选池 —— 离线一键链（MCP 三段原始数据不可用时降级）。

背景：第 10 步原依赖 westock MCP 三段（tool_filter / data_technical / data_fund_flow）。
MCP 不通时无任何可用数据 → macd_scan / highwin 永久停在旧数据日（此前停在 09-23）。
本脚本用**全部真实源**重建同一口径（不编造、不降级数值，只换数据来源）：

  1) _gen_macd_pool_offline   本地腾讯日K → 全市场正股初筛域（剔 ST/退/基金）
  2) _gen_tech_offline        本地腾讯日K → MACD(12,26,9) / MA / RSI，口径同 data_technical
  3) _gen_macd_flow_sina      新浪 MoneyFlow → 20 日主力净流入（只拉水上金叉票，防风控限频）
  4) _gen_hw_quote_offline    腾讯 qt → 高胜率行情增强（price/换手/量比/52周…）
  5) macd_build {DS} --raw    合成 macd_scan_{DS}.json（含来源如实标注 src=offline_txk_full）
  6) gen_macd {DS}            渲染 MACD 页
  7) build_highwin / gen_highwin  高胜率候选池（核心/观察/备选/回避）
  8) _apply_theme             注入主题与导航

★ 口径提示：离线初筛域为「全市场正股」，非 westock「主力净流入 top200」，页面已如实标注。
用法：python quant/_gen_macd_offline_all.py --date 2026-10-09
"""
from __future__ import annotations
import os, sys, subprocess, argparse, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PY = sys.executable


def run(title, args, soft=False):
    cmd = [PY] + args
    print("\n=== %s ===\n$ %s" % (title, " ".join(os.path.basename(x) if x.endswith(".py") else x for x in args)))
    t0 = time.time()
    rc = subprocess.run(cmd, cwd=HERE).returncode
    print("[%s] rc=%d  %.1fs" % (title, rc, time.time() - t0))
    if rc != 0 and not soft:
        raise SystemExit("✗ 中止：%s 失败（rc=%d）" % (title, rc))
    return rc


def main():
    ap = argparse.ArgumentParser(description="MACD + 高胜率 离线一键链")
    ap.add_argument("--date", required=True, help="数据日 YYYY-MM-DD")
    ap.add_argument("--skip-net", action="store_true",
                    help="跳过联网步骤（flow/quote）——仅在已备好这两份产物时用")
    a = ap.parse_args()
    D, DS = a.date, a.date.replace("-", "")

    run("1 初筛域（本地日K）", ["_gen_macd_pool_offline.py", "--date", D])
    run("2 MACD/MA/RSI（本地日K）", ["_gen_tech_offline.py", "--date", D])
    if a.skip_net:
        print("\n[skip] 跳过 3/4（联网步骤）")
    else:
        run("3 20日主力净流入（新浪）", ["_gen_macd_flow_sina.py", "--date", D])
        run("4 行情增强（腾讯qt）", ["_gen_hw_quote_offline.py", "--date", D])
    run("5 合成 MACD 扫描", ["macd_build.py", DS, "--raw"])
    run("6 渲染 MACD 页", ["gen_macd.py", DS])
    run("7 高胜率池构建", ["build_highwin.py", "--date", D])
    run("8 高胜率池渲染", ["gen_highwin.py", "--date", D])
    print("\n✓ 离线链完成：macd_scan_%s.json / picks/highwin_%s.json / web/picks/highwin_%s.html"
          % (DS, D, DS))


if __name__ == "__main__":
    main()
