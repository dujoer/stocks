#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""2026-09-10 龙虎榜中继落盘脚本。

本环境 westock-mcp 结果未自动落盘到 tool-results，故采用 _raw_lhb_0910.json
（由对话中 data_lhb 全量返回直接保存）作为唯一数据源。

行为：
  1) 读取 _raw_lhb_0910.json（结构 {"ok":true,"data":{"date","all","jg","yzb","yyb","gslmr","gslxw"}}）
  2) 校验 data.date == 2026-09-10
  3) 写出 quant/lhb/2026-09-10.json（与 09-09 同结构）
  4) 同时写出 quant/_lhb_{tab}_2026-09-10.json 中间文件（供 _merge_lhb_subtabs.py 使用）
  5) 提取 all 全榜去重股票代码到 quant/_lhb_codes_20260910.txt
"""
import json, os, sys

DATE = "2026-09-10"
ROOT = os.path.dirname(os.path.abspath(__file__))

raw_path = os.path.join(ROOT, "_raw_lhb_0910.json")
if not os.path.exists(raw_path):
    print("ERROR: 缺少原始文件 %s（请先保存本次 data_lhb 全量返回到该路径）" % raw_path)
    sys.exit(1)

doc = json.load(open(raw_path, encoding="utf-8"))
data = doc.get("data", {})
if not isinstance(data, dict):
    print("ERROR: data 不是 dict"); sys.exit(1)
if data.get("date") != DATE:
    print("ERROR: data.date=%r 期望 %r" % (data.get("date"), DATE)); sys.exit(1)

TABS = ("all", "jg", "yzb", "yyb", "gslmr", "gslxw")
out_doc = {"ok": True, "data": {}}
for t in TABS:
    arr = data.get(t, [])
    if not isinstance(arr, list):
        arr = []
    out_doc["data"][t] = arr
out_doc["data"]["date"] = DATE

# 写主榜
lhb_dir = os.path.join(ROOT, "lhb")
os.makedirs(lhb_dir, exist_ok=True)
lhb_path = os.path.join(lhb_dir, DATE + ".json")
json.dump(out_doc, open(lhb_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("wrote lhb/%s.json" % DATE)
for t in TABS:
    print("  %-6s %d" % (t, len(out_doc["data"][t])))

# 写分项中间文件
for t in ("jg", "yyb", "gslmr", "gslxw"):
    arr = out_doc["data"].get(t, [])
    if arr:
        sub = {"ok": True, "data": {t: arr, "date": DATE}}
        p = os.path.join(ROOT, "_lhb_%s_%s.json" % (t, DATE))
        json.dump(sub, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print("wrote _lhb_%s_%s.json (%d)" % (t, DATE, len(arr)))

# 提取代码
codes = []
seen = set()
for r in out_doc["data"].get("all", []):
    c = r.get("code")
    if c and c not in seen:
        seen.add(c); codes.append(c)
cp = os.path.join(ROOT, "_lhb_codes_20260910.txt")
open(cp, "w", encoding="utf-8").write("\n".join(codes))
print("unique codes in all board:", len(codes))
print("wrote", cp)
