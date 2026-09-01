# -*- coding: utf-8 -*-
"""合并 tool-results 中落盘的股东数据批次，输出 _merged_shareholder.json，并报告缺失代码。"""
import json, os, re, glob

TR = r"C:\Users\nonoy\.workbuddy\projects\g-ai-股票\e3ab6e4e-351f-47a8-a451-53f648954b46\tool-results"
BASE = os.path.dirname(os.path.abspath(__file__))

files = sorted(glob.glob(os.path.join(TR, "mcp-westock-mcp-data_shareholder-*.txt")))
print("落盘文件数:", len(files))

merged = {}
bad = []
for fn in files:
    raw = open(fn, encoding="utf-8", errors="replace").read()
    m = re.search(r'\{"ok"\s*:\s*true', raw)
    if not m:
        bad.append(os.path.basename(fn))
        continue
    try:
        d = json.loads(raw[m.start():])
    except Exception as e:
        bad.append((os.path.basename(fn), str(e)[:60]))
        continue
    for code, v in d.get("data", {}).items():
        merged[code] = v

# 补充：内联返回、未落盘的批次（手工存为 _batchNNN.json，内容为内层 data 字典）
extra = sorted(glob.glob(os.path.join(BASE, "_batch*.json")))
for fn in extra:
    if os.path.basename(fn) == "_batches.json":
        continue
    try:
        d = json.load(open(fn, encoding="utf-8"))
    except Exception as e:
        bad.append((os.path.basename(fn), str(e)[:60]))
        continue
    for code, v in d.items():
        merged[code] = v
print("内联补充批次:", len(extra))

print("合并代码数:", len(merged))
print("解析失败:", bad if bad else "无")

out = os.path.join(BASE, "_merged_shareholder.json")
with open(out, "w", encoding="utf-8") as f:
    json.dump(merged, f, ensure_ascii=False)
print("已保存", out)

batches = json.load(open(os.path.join(BASE, "_batches.json"), encoding="utf-8"))["batches"]
allcodes = set()
for b in batches:
    allcodes |= set(b)
miss = sorted(allcodes - set(merged))
print("全市场代码数:", len(allcodes))
print("缺失代码数:", len(miss))
if miss:
    print("缺失样例:", miss[:30])
    with open(os.path.join(BASE, "_missing.json"), "w", encoding="utf-8") as f:
        json.dump(miss, f, ensure_ascii=False)
    print("缺失清单已保存 _missing.json")
