# -*- coding: utf-8 -*-
"""
中继脚本：把 westock data_sector 的 MCP 落盘结果搬运到 quant/，
按 kind(industry/concept) 分组，每个 kind 取 mtime 最新的文件。

用法: python _relay_sector_0910.py
"""
import glob, json, os

PROJECT_BASE = r"C:/Users/nonoy/.workbuddy/projects/g-ai-股票"
OUT_DIR = os.path.dirname(os.path.abspath(__file__))
DATE_TAG = "20260910"

# 递归扫描所有 tool-results 下的 data_sector 文件(.txt/.json)
PATTERNS = [
    os.path.join(PROJECT_BASE, "**", "tool-results", "**", "*data_sector*.txt"),
    os.path.join(PROJECT_BASE, "**", "tool-results", "**", "*data_sector*.json"),
]


def main():
    files = []
    for pat in PATTERNS:
        files.extend(glob.glob(pat, recursive=True))
    files = sorted(set(files))
    print(f"[scan] 找到 {len(files)} 个 data_sector 文件")

    latest = {}  # kind -> (mtime, path)
    for f in files:
        try:
            d = json.load(open(f, encoding="utf-8"))
        except Exception as e:
            print(f"  [skip:json] {os.path.basename(f)} -> {e}")
            continue
        data = d.get("data") if isinstance(d, dict) else None
        if not isinstance(data, dict):
            print(f"  [skip:no-data] {os.path.basename(f)}")
            continue
        kind = data.get("kind")
        if kind not in ("industry", "concept"):
            print(f"  [skip:kind={kind}] {os.path.basename(f)}")
            continue
        mtime = os.path.getmtime(f)
        if kind not in latest or mtime > latest[kind][0]:
            latest[kind] = (mtime, f)

    for kind in ("industry", "concept"):
        if kind not in latest:
            print(f"[WARN] 未找到 kind={kind} 的文件！")
            continue
        mtime, f = latest[kind]
        d = json.load(open(f, encoding="utf-8"))
        rows = d["data"]["rows"]
        out_path = os.path.join(OUT_DIR, f"sector_{kind}_{DATE_TAG}.json")
        json.dump(d, open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        import datetime
        mt = datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
        print(f"[ok] {kind}: {os.path.basename(f)} (mtime={mt}) -> {out_path}  rows={len(rows)}")


if __name__ == "__main__":
    main()
