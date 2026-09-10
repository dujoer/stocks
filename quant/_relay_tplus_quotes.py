# -*- coding: utf-8 -*-
"""合并 data_quote 落盘结果 → quant/tplus/quotes_{D}.json（code → 行情快照）。"""
import json, os, sys, glob, argparse, datetime

BASE = r"C:/Users/nonoy/.workbuddy/projects/g-ai-股票/e3ab6e4e-351f-47a8-a451-53f648954b46/tool-results"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "tplus")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=datetime.date.today().strftime("%Y-%m-%d"))
    a = ap.parse_args()
    os.makedirs(OUT_DIR, exist_ok=True)

    # 取最近 6 个 data_quote 落盘文件（本次 4 批 + 余量）
    files = sorted(glob.glob(os.path.join(BASE, "mcp-westock-mcp-data_quote-*.txt")),
                   key=os.path.getmtime)[-6:]
    merged = {}
    for fp in files:
        try:
            d = json.load(open(fp, encoding="utf-8"))
        except Exception as e:
            print("skip", os.path.basename(fp), e); continue
        data = d.get("data") if isinstance(d, dict) else None
        if not isinstance(data, dict):
            continue
        for k, v in data.items():
            if isinstance(v, dict) and v.get("code"):
                merged[v["code"]] = v
        print(f"  {os.path.basename(fp)}: +{len(data)}")

    out = os.path.join(OUT_DIR, f"quotes_{a.date}.json")
    json.dump(merged, open(out, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"[relay_tplus_quotes] {a.date}: 合并 {len(merged)} 只 → {out}")


if __name__ == "__main__":
    main()
