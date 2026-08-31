# -*- coding: utf-8 -*-
"""从枚举快照 enum_{DAY}_*.json / enum_bj_{DAY}_*.json 中提取代码清单。
tool_ranking 返回结构: {ok,data:{stocks:[{code,name,...}],totalStocks,offset,limit}}
输出 codes_{DAY}.txt (沪深) 与 codes_bj_{DAY}.txt (北交所)，去重排序。
"""
import json, glob, os, sys

DAY = sys.argv[1] if len(sys.argv) > 1 else "2026-08-21"
HERE = os.path.dirname(os.path.abspath(__file__))

def grab(pattern):
    codes = []
    for f in sorted(glob.glob(os.path.join(HERE, pattern))):
        try:
            with open(f, encoding="utf-8") as fh:
                obj = json.load(fh)
        except Exception:
            continue
        data = obj.get("data") if isinstance(obj, dict) else obj
        stocks = []
        if isinstance(data, dict):
            stocks = data.get("stocks") or []
        elif isinstance(data, list):
            stocks = data
        for s in stocks:
            if isinstance(s, dict):
                c = s.get("code") or s.get("symbol")
                if c:
                    codes.append(c)
    return codes

hs = sorted(set(grab(f"enum_{DAY}_*.json")))
bj = sorted(set(grab(f"enum_bj_{DAY}_*.json")))

with open(os.path.join(HERE, f"codes_{DAY}.txt"), "w", encoding="utf-8") as fh:
    fh.write("\n".join(hs) + ("\n" if hs else ""))
with open(os.path.join(HERE, f"codes_bj_{DAY}.txt"), "w", encoding="utf-8") as fh:
    fh.write("\n".join(bj) + ("\n" if bj else ""))

print(f"DAY={DAY} hs_codes={len(hs)} bj_codes={len(bj)}")
