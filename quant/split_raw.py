# -*- coding: utf-8 -*-
"""将 westock data_quote 保存下来的(可能因过大被存盘)结果，按原始代码顺序
切分为每 100 只一个的 raw_{DAY}_{i:03d}.json 文件。

用法: python split_raw.py <saved_json_path> <DAY> <start_index> <codes_file>
  saved_json_path : 框架存盘的工具结果文本文件(内容为 {"ok":true,"data":{code:{...}}})
  DAY             : 如 2026-08-17
  start_index     : 本批在 codes 清单中的起始下标(0-based)
  codes_file      : 本次调用所用的逗号分隔代码串文件(决定顺序与分组)
"""
import json, sys, os

HERE = r"G:/ai/股票/quant"
saved_path = sys.argv[1]
DAY = sys.argv[2]
start_index = int(sys.argv[3])
codes_file = sys.argv[4]

with open(saved_path, encoding="utf-8") as f:
    obj = json.load(f)
data = obj.get("data") if isinstance(obj, dict) else obj
if data is None:
    data = obj

with open(codes_file, encoding="utf-8") as f:
    codes = [c for c in f.read().split(",") if c]

groups = [codes[i:i+100] for i in range(0, len(codes), 100)]
out_count = 0
missing = []
for j, g in enumerate(groups):
    bidx = start_index // 100 + j
    d = {}
    for c in g:
        if c in data:
            d[c] = data[c]
        else:
            missing.append(c)
    out = {"ok": True, "data": d}
    with open(os.path.join(HERE, f"raw_{DAY}_{bidx:03d}.json"), "w", encoding="utf-8") as outf:
        json.dump(out, outf, ensure_ascii=False)
    out_count += 1

print(f"split done: saved={saved_path}")
print(f"  groups_written={out_count} (batch {start_index//100}..{start_index//100+out_count-1})")
print(f"  codes_in_chunk={len(codes)} returned={len(data)} missing={len(missing)}")
if missing:
    print("  MISSING:", missing[:20])
