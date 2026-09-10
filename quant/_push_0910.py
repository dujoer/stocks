# -*- coding: utf-8 -*-
"""2026-09-10 每日更新 · 精准推送今日新增/改动文件。

避开全量 _push_lhb.py 在推到约 62 个文件后被沙箱 SIGTERM 截断的已知问题。
用法（必须关闭沙箱，否则 GitHub API 外网被拦）：
  python quant/_push_0910.py
"""
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _push_lhb import push_file  # noqa: E402

ROOT = r"G:/ai/股票"

HTMLS = [
    "index.html",
    "web/sections/index.html",
    "web/psychology/index.html",
    "web/psychology/crowd-psychology-risk-radar-20260910.html",
    "web/sector/index.html",
    "web/sector/sector-strength-20260910.html",
    "web/sector/sector-strength-trend.html",
    "web/sector/trend.html",
    "web/lhb/lhb.html",
    "web/lhb/index.html",
    "web/lhb/lhb_2026-09-10.html",
    "web/block/index.html",
    "web/block/block.html",
    "web/block/archive.html",
    "web/block/block_2026-09-10.html",
    "web/exec/index.html",
    "web/market/index.html",
    "web/market/hotmoney.html",
    "web/market/status_2026-09-10.html",
    "web/db/index.html",
]

SCRIPTS = [
    "quant/_relay_sector_0910.py",
    "quant/_relay_lhb_0910.py",
    "quant/_push_0910.py",
]


def main():
    targets = []
    for rel in HTMLS:
        p = os.path.join(ROOT, rel)
        if os.path.exists(p):
            targets.append(rel)
        else:
            print("[skip-missing]", rel)

    # 数据中心列式分片（db_export 产物）
    for p in sorted(glob.glob(os.path.join(ROOT, "web", "data", "*.json"))):
        targets.append(os.path.relpath(p, ROOT).replace("\\", "/"))

    for rel in SCRIPTS:
        p = os.path.join(ROOT, rel)
        if os.path.exists(p):
            targets.append(rel)

    print("待推送 %d 个文件\n" % len(targets))
    ok, fail = 0, []
    for i, rel in enumerate(targets, 1):
        try:
            push_file(rel)
            ok += 1
            print("[%d/%d] OK %s" % (i, len(targets), rel))
        except Exception as e:
            fail.append((rel, str(e)))
            print("[%d/%d] FAIL %s -> %s" % (i, len(targets), rel, e))
    print("\n完成：成功 %d / 失败 %d" % (ok, len(fail)))
    for rel, e in fail:
        print("  FAILED", rel, e)


if __name__ == "__main__":
    main()
