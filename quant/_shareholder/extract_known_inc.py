#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从全市场 5544 只 Q2 中报数据中提取「知名私募/牛散加仓」的股票清单(known_inc>0)，
输出结构化 JSON 供技术面二次过滤使用。复用 build_stock_accumulation 的扫描逻辑。"""
import json, os, sys
BASE = os.path.dirname(__file__)
sys.path.insert(0, BASE)
from build_stock_accumulation import scan_stock, MATCH, is_institution  # noqa

SRC = os.path.join(BASE, "..", "q2_full", "_merged_shareholder.json")
OUT = os.path.join(BASE, "known_inc_50.json")

def main():
    raw = json.load(open(SRC, encoding="utf-8"))
    data = raw.get("data", raw)
    rows = []
    for code, rec in data.items():
        r = scan_stock(rec)
        if r["known_inc"] > 0:
            # 去重展示 主体:动作
            seen = {}
            for e, t, a in r["known"]:
                seen.setdefault(e, a)
            rows.append({
                "code": r["code"], "name": r["name"],
                "known_inc": r["known_inc"], "known_dec": r["known_dec"],
                "net_w": r["net_w"], "inc": r["inc"], "dec": r["dec"],
                "entities": [f"{e}{a}" for e, a in sorted(seen.items())],
            })
    rows.sort(key=lambda x: (-x["known_inc"], -x["net_w"]))
    json.dump({"count": len(rows), "rows": rows}, open(OUT, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("total known-inc:", len(rows))
    for i, r in enumerate(rows[:55], 1):
        print(f'{i:2d}. {r["name"]}({r["code"]}) 加仓主体={r["known_inc"]} 净增持={r["net_w"]}万 实体={",".join(r["entities"])}')

if __name__ == "__main__":
    main()
