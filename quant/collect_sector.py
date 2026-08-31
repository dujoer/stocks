#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
把 westock data_sector 的"原始行业/概念 JSON"合成为统一板块强度记录文件。

用法:
  python collect_sector.py --industry sector_industry_YYYYMMDD.json \
       --concept sector_concept_YYYYMMDD.json --out sector_strength_data.json

原始字段(raw rows): changePct, turnover(万元), mainInflow(万元), mainOutflow(万元),
  mainNetInflow(万元), leader{name,changePct}
合成记录(单位统一为 元, 文本用 亿): 与 sector_strength_data.json 同 schema。
"""
import argparse, json, os


def yi(v):
    """元 -> 亿元文本(带正负)"""
    y = v / 1e8
    return ("+" if y > 0 else "") + format(y, ".2f")


def pct(v):
    return ("+" if v > 0 else "") + format(v, ".2f") + "%"


def behavior_of(s):
    if s >= 3:
        return "抢筹"
    if s >= 1:
        return "建仓"
    if s >= -1:
        return "洗盘"
    return "出货"


def conv_rows(rows, kind_label):
    out = []
    for r in rows:
        turn = float(r.get("turnover") or 0) * 10000        # 万元->元
        main = float(r.get("mainInflow") or 0) * 10000
        retail = float(r.get("mainOutflow") or 0) * 10000
        dark = float(r.get("mainNetInflow") or 0) * 10000
        s = (dark / turn * 100) if turn else 0
        p = float(r.get("changePct") or 0)
        leader = r.get("leader") or {}
        lname = leader.get("name", "")
        lpct = leader.get("changePct")
        ltext = (lname + (" +%.2f%%" % lpct if isinstance(lpct, (int, float)) else "")) if lname else ""
        out.append({
            "name": r.get("name"),
            "kind": kind_label,
            "pctText": pct(p), "pctVal": round(p, 2),
            "totalText": yi(turn), "totalVal": turn,
            "mainText": yi(main), "mainVal": main,
            "retailText": yi(retail), "retailVal": retail,
            "darkText": yi(dark), "darkVal": dark,
            "darkUp": dark >= 0,
            "strengthText": format(s, ".2f"), "strengthVal": round(s, 2),
            "behavior": behavior_of(s),
            "behaviorRank": {"抢筹": 4, "建仓": 3, "洗盘": 2, "出货": 1}[behavior_of(s)],
            "leader": ltext,
        })
    return out


def load_raw(path):
    d = json.load(open(path, encoding="utf-8"))
    if isinstance(d, dict) and "data" in d and "rows" in d["data"]:
        return d["data"]["rows"], d["data"].get("kind")
    if isinstance(d, list):
        return d, None
    raise ValueError("无法解析原始文件: " + path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--industry", required=True)
    ap.add_argument("--concept", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    irows, ikind = load_raw(args.industry)
    crows, ckind = load_raw(args.concept)
    # westock 原始 kind 为英文 industry/concept; 统一固化成中文标签, 避免下游页面出现英文
    recs = conv_rows(irows, "行业") + conv_rows(crows, "概念")
    recs.sort(key=lambda r: r["strengthVal"], reverse=True)
    json.dump(recs, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"[ok] 合成 {len(recs)} 条记录 -> {args.out} (行业 {len(irows)} / 概念 {len(crows)})")


if __name__ == "__main__":
    main()
