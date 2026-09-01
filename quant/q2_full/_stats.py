# -*- coding: utf-8 -*-
"""全市场 Q2 股东数据规模统计：评估行业映射需求量。"""
import json, os, sys, collections

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(BASE, ".."))

DATA = json.load(open(os.path.join(BASE, "_merged_shareholder.json"), encoding="utf-8"))
print("全市场股票数:", len(DATA))

# 复用分类器
import importlib.util
spec = importlib.util.spec_from_file_location("bq", os.path.join(BASE, "..", "build_q2_dashboard.py"))
# 直接复制判定逻辑，避免执行整个生成脚本
KNOWN_CATTLE = set()
src = open(os.path.join(BASE, "..", "build_q2_dashboard.py"), encoding="utf-8").read()
ns = {}
start = src.index("NATIONAL_TEAM_KEYWORDS")
end = src.index("def cat_group")
exec(src[start:end], ns)
KNOWN_CATTLE = set()
# KNOWN_CATTLE 在文件前部，单独解析
import re
m = re.search(r"KNOWN_CATTLE = \{(.*?)\}", src, re.S)
KNOWN_CATTLE = set(re.findall(r'"([^"]+)"', m.group(1)))
ns["KNOWN_CATTLE"] = KNOWN_CATTLE
classify_holder = ns["classify_holder"]

def collect(entry):
    by = {}
    for s_ in ("top10Shareholders", "top10FloatShareholders"):
        for s in entry.get(s_, []) or []:
            n = s["name"]
            if n not in by:
                by[n] = {"name": n, "holdChange": s.get("holdChange", 0),
                         "holdPct": s.get("holdPct", 0), "holdShares": s.get("holdShares", 0)}
            else:
                if s.get("holdChange", 0) != 0 and by[n]["holdChange"] == 0:
                    by[n]["holdChange"] = s["holdChange"]
                if s.get("holdShares", 0) > by[n]["holdShares"]:
                    by[n]["holdShares"] = s["holdShares"]
                    by[n]["holdPct"] = s.get("holdPct", 0)
    return list(by.values())

cat_cnt = collections.Counter()
records = 0
smart_records = 0          # 牛散/私募/公募 记录
smart_moved = 0            # 其中有变动的
codes_with_smart = set()
codes_with_smart_move = set()
holder_names = collections.Counter()   # 股东名 -> 出现股票数（聪明钱）

for code, e in DATA.items():
    hs = collect(e)
    for h in hs:
        records += 1
        c = classify_holder(h["name"])
        cat_cnt[c] += 1
        if c in ("牛散", "牛散候选", "私募", "公募"):
            smart_records += 1
            codes_with_smart.add(code)
            if h["holdChange"] != 0:
                smart_moved += 1
                codes_with_smart_move.add(code)
                holder_names[h["name"]] += 1

print("\n== 股东类别分布（全市场 %d 条记录）==" % records)
for k, v in cat_cnt.most_common():
    print(f"  {k:10s} {v:7d}  ({v*100.0/records:.1f}%)")

print("\n聪明钱(牛散/私募/公募)记录:", smart_records, " 其中有变动:", smart_moved)
print("涉及股票数(含聪明钱):", len(codes_with_smart))
print("涉及股票数(聪明钱有变动):", len(codes_with_smart_move))
print("聪明钱主体个数(有变动的):", len(holder_names))
print("\n出现股票数最多的聪明钱 Top20:")
for n, c in holder_names.most_common(20):
    print(f"  {n[:28]:30s} {c:4d}  [{classify_holder(n)}]")
