#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
A股板块强度 · 每日累积编排脚本（post-pull orchestrator）

前置: 已通过 westock data_sector(mode=ranking) 拉取当日行业/概念原始 JSON 并存盘:
  python quant/run_daily_sector.py \
      --date 2026-08-28 \
      --industry quant/sector_industry_20260828.json \
      --concept  quant/sector_concept_20260828.json

本脚本依次调用:
  1. collect_sector.py     原始行业/概念 -> 统一强度记录 sector_strength_data_<date>.json
  2. build_sector_daily.py 记录 -> sector_daily/<date>.json (同时更新 sector_trend.json 汇总)
  3. build_sector_strength.py 每日明细页 web/sector-strength-<YYYYMMDD>.html
  4. build_sector_trend.py    趋势看板 web/sector-strength-trend.html
  5. build_sector_index.py    首页索引 web/sector-strength-index.html

说明:
  westock data_sector 的 date 参数被忽略,只返回"最新快照"。因此本管道按"拉取日期"固化,
  不做任何历史回测/编造。每日(交易日)跑一次即可让趋势自然累积。
  完整的"自动拉取+本脚本"可由 WorkBuddy 计划任务(交易日 16:10 后)触发。
"""
import argparse, os, subprocess, sys, datetime

ROOT = os.path.dirname(os.path.abspath(__file__))


def run(py, args):
    cmd = [sys.executable, os.path.join(ROOT, py)] + args
    print("\n$ " + " ".join(cmd))
    r = subprocess.run(cmd, cwd=ROOT)
    if r.returncode != 0:
        raise SystemExit(f"[fail] {py} 退出码 {r.returncode}")
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True, help="拉取日期 YYYY-MM-DD")
    ap.add_argument("--industry", required=True, help="行业原始 JSON(来自 data_sector kind=industry)")
    ap.add_argument("--concept", required=True, help="概念原始 JSON(来自 data_sector kind=concept)")
    ap.add_argument("--skip-pull-check", action="store_true",
                    help="跳过对原始文件存在性/行数的基本校验")
    args = ap.parse_args()

    date = args.date
    compact = date.replace("-", "")
    industry = args.industry
    concept = args.concept

    if not args.skip_pull_check:
        for f in (industry, concept):
            if not os.path.exists(f):
                raise SystemExit(f"[fail] 原始文件不存在: {f}")
        # 行数粗校验
        import json
        for f, expected_kind in ((industry, "industry"), (concept, "concept")):
            d = json.load(open(f, encoding="utf-8"))
            rows = d.get("data", {}).get("rows", [])
            kind = d.get("data", {}).get("kind")
            print(f"[check] {f}: kind={kind} rows={len(rows)}")
            if kind != expected_kind:
                raise SystemExit(f"[fail] {f} kind={kind} 期望 {expected_kind}")

    strength_data = os.path.join(ROOT, f"sector_strength_data_{compact}.json")
    daily_json = os.path.join(ROOT, "sector_daily", f"{date}.json")
    web_daily = os.path.join(ROOT, "..", "web", "sector", f"sector-strength-{compact}.html")

    t0 = datetime.datetime.now()
    # 1. 合成
    run("collect_sector.py", ["--industry", industry, "--concept", concept, "--out", strength_data])
    # 2. 每日固化 + 趋势汇总
    run("build_sector_daily.py", ["--records", strength_data, "--date", date])
    # 3. 每日明细页
    run("build_sector_strength.py", ["--daily", daily_json, "--output", web_daily])
    # 4. 趋势看板
    run("build_sector_trend.py", ["--trend", os.path.join(ROOT, "sector_trend.json")])
    # 5. 首页索引
    run("build_sector_index.py", ["--trend", os.path.join(ROOT, "sector_trend.json")])

    dt = datetime.datetime.now() - t0
    print(f"\n[done] {date} 板块强度全链路完成, 耗时 {dt.total_seconds():.1f}s")
    print(f"   每日页 : web/sector/sector-strength-{compact}.html")
    print(f"   趋势看板: web/sector/sector-strength-trend.html")
    print(f"   首页索引: web/sector/sector-strength-index.html")


if __name__ == "__main__":
    main()
