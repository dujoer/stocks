# -*- coding: utf-8 -*-
"""
解析 tool-results 下所有 data_quote 自动落盘文件，抽取每只股票在 2026-06-30 / 2026-09-01
的快照价，存为 _prices_raw.json = { "code|YYYY-MM-DD": price }。
统一从落盘文件读取，不占上下文。
"""
import json, os, glob, re

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(BASE))
cands = []
cands += glob.glob(os.path.join(ROOT, "tool-results", "mcp-westock-mcp-data_quote-*.txt"))
cands += glob.glob(os.path.join(BASE, "tool-results", "mcp-westock-mcp-data_quote-*.txt"))
cands += glob.glob(os.path.join(ROOT, ".workbuddy", "tool-results", "mcp-westock-mcp-data_quote-*.txt"))
import glob as _g
cands += _g.glob(os.path.join(os.path.expanduser("~"), ".workbuddy", "projects",
                              "**", "tool-results", "mcp-westock-mcp-data_quote-*.txt"), recursive=True)

prices = {}
n_file = 0
for f in cands:
    try:
        txt = open(f, encoding="utf-8").read()
    except Exception:
        continue
    n_file += 1
    # 取第一个 { 到最后一个 } 之间的 JSON
    s = txt.find("{")
    e = txt.rfind("}")
    if s < 0 or e < 0 or e <= s:
        continue
    seg = txt[s:e + 1]
    try:
        d = json.loads(seg)
    except Exception:
        continue
    data = d.get("data", {})
    if not isinstance(data, dict):
        continue
    for code, info in data.items():
        if not isinstance(info, dict):
            continue
        price = info.get("price")
        t = info.get("time")
        if price is None or t is None:
            continue
        prices["{}|{}".format(code, t)] = price

json.dump(prices, open(os.path.join(BASE, "_prices_raw.json"), "w"), ensure_ascii=False)
from collections import Counter
c = Counter(k.split("|")[1] for k in prices)
print("已读落盘文件:", n_file, " 价格条目:", len(prices))
print("按日期:", dict(c))
