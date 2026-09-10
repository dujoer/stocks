# -*- coding: utf-8 -*-
"""做T池 · 候选池生成（Stage 1）。

目的：从「机构底仓池」里产出当日待筛代码，供后续拉行情 → 打分 → 出页。

机构底仓口径（顶级机构规则）：
  - 公募基金（含"证券投资基金/混合型/股票型/灵活配置/指数型"）持有十大流通股比例合计 ≥ 3%
  - 或 社保 / 养老 / 年金 / 险资 / 汇金 / 证金 / QFII 出现在十大流通股东
数据源：quant/q2_full/_merged_shareholder.json（2026-Q2 全市场十大股东）
        quant/q2_full/_code2industry.json（代码 → 申万一级）

输出：
  quant/tplus/codes_{D}.txt         逗号分隔代码（供 data_quote 批量拉取）
  quant/tplus/universe_{D}.json     [{code,name,industry,fund_ratio,top_inst,inst_names}]

用法：
  python gen_tplus.py [--date YYYY-MM-DD] [--min-fund 3.0] [--all]
      --all  忽略机构门槛，使用全市场（5544 只）作为候选，用于全市场扫描
"""
import os, sys, json, argparse, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
Q2 = os.path.join(ROOT, "quant", "q2_full")
MERGED = os.path.join(Q2, "_merged_shareholder.json")
C2I = os.path.join(Q2, "_code2industry.json")
OUT_DIR = os.path.join(ROOT, "quant", "tplus")

FUND_KW = ["证券投资基金", "混合型", "股票型", "灵活配置", "指数型", "交易型开放式"]
TOP_KW = ["社保", "养老", "年金", "保险", "汇金", "证金", "中国证券金融", "QFII", "北向",
          "国新", "国调", "中央汇金"]


def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=datetime.date.today().strftime("%Y-%m-%d"))
    ap.add_argument("--min-fund", type=float, default=5.0, help="公募持股比例门槛（%）")
    ap.add_argument("--all", action="store_true", help="忽略机构门槛，全市场扫描")
    return ap.parse_args()


def main():
    a = parse_args()
    merged = json.load(open(MERGED, encoding="utf-8"))
    c2i = json.load(open(C2I, encoding="utf-8"))
    os.makedirs(OUT_DIR, exist_ok=True)

    universe = []
    for code, rec in merged.items():
        hs = rec.get("top10FloatShareholders") or []
        fund_ratio = 0.0
        top_inst, inst_names = 0, []
        for h in hs:
            nm = (h.get("name") or "").strip()
            pct = h.get("holdPct") or 0
            if any(k in nm for k in FUND_KW):
                fund_ratio += pct
            if any(k in nm for k in TOP_KW):
                top_inst += 1
                inst_names.append(nm)
        keep = a.all or (fund_ratio >= a.min_fund) or (top_inst >= 2)
        if not keep:
            continue
        universe.append({
            "code": code,
            "name": rec.get("name") or code,
            "industry": c2i.get(code) or "—",
            "fund_ratio": round(fund_ratio, 2),
            "top_inst": top_inst,
            "inst_names": inst_names[:4],
        })

    # 排序：顶级机构优先，其次基金比例
    universe.sort(key=lambda x: (x["top_inst"] > 0, x["fund_ratio"]), reverse=True)

    codes = [u["code"] for u in universe]
    cpath = os.path.join(OUT_DIR, f"codes_{a.date}.txt")
    upath = os.path.join(OUT_DIR, f"universe_{a.date}.json")
    with open(cpath, "w", encoding="utf-8") as f:
        f.write(",".join(codes))
    with open(upath, "w", encoding="utf-8") as f:
        json.dump(universe, f, ensure_ascii=False)

    print(f"[gen_tplus] {a.date}: 候选 {len(codes)} 只（min_fund={a.min_fund}, all={a.all}）")
    print(f"  → {cpath}")
    print(f"  → {upath}")


if __name__ == "__main__":
    main()
