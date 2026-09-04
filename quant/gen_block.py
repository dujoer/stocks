# -*- coding: utf-8 -*-
"""大宗交易（block trade）数据生成：原始事件 → 按交易日筛选 → 合并行情 → 落盘。

数据源：westock-mcp `tool_event(names="block_past_30", limit=3000)`
    返回 evt_block_past_30.stocks[]，字段：
      code/name/TradeDay(YYYYMMDD)/TradePrice/TradeValue/TradeRatio/
      Discount(折溢价率%, 正=折价 负=溢价)/TradeType/BuySalesDepartment/SellSalesDepartment
    ⚠ limit 必须给足（默认 500 会截断当日数据，实测 09-04 当日 500 档只取到 32 条、
      3000 档取到全部 158 条）。

用法：
    python quant/gen_block.py --date 2026-09-04 \
        --src  <tool_event 落盘 JSON> \
        --quotes <data_quote 落盘 JSON>   # 可选，用于补当日涨跌幅/收盘价

输出：quant/block_chg/{DATE}.json
硬规矩：只展示公开披露的大宗交易，不输出任何个人持仓、组合、选股内容。
"""
import os, sys, json, argparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
Q = os.path.join(ROOT, "quant")
OUT_DIR = os.path.join(Q, "block_chg")

INST_FLAG = "机构专用"  # 买方/卖方营业部含此字样即视为机构席位


def load_quotes(path):
    """data_quote 落盘文件，支持两种格式：
       A) {code: {name, price, change_percent}, ...}
       B) westock data_quote 原始返回 {ok:true, data:{code:{name,price,change_percent,...}}}
    只抽取 name / price / change_percent 三字段。"""
    if not path or not os.path.exists(path):
        return {}
    d = json.load(open(path, encoding="utf-8"))
    inner = d
    if isinstance(d, dict):
        if isinstance(d.get("data"), dict):
            inner = d["data"]
    if not isinstance(inner, dict):
        return {}
    out = {}
    for code, info in inner.items():
        if not isinstance(info, dict):
            continue
        out[code] = {
            "name": info.get("name"),
            "price": info.get("price"),
            "change_percent": info.get("change_percent"),
        }
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True, help="交易日 YYYY-MM-DD")
    ap.add_argument("--src", required=True, help="tool_event(block_past_30) 落盘 JSON")
    ap.add_argument("--quotes", default="", help="data_quote 落盘 JSON（补涨跌幅/收盘价）")
    a = ap.parse_args()

    DATE = a.date
    DAY = DATE.replace("-", "")

    raw = json.load(open(a.src, encoding="utf-8"))
    data = raw.get("data", {})
    blk = data.get("evt_block_past_30") or data.get("block_past_30") or {}
    stocks = blk.get("stocks", [])
    if not stocks:
        print(f"✗ 源文件中未找到大宗交易数据: {a.src}")
        sys.exit(1)

    quotes = load_quotes(a.quotes)
    rows = [x for x in stocks if str(x.get("TradeDay")) == DAY]

    out_rows = []
    for x in rows:
        code = x.get("code", "")
        q = quotes.get(code, {})
        price = q.get("price")
        chg = q.get("change_percent")
        # 收盘价兜底：Discount=(close-tradePrice)/close*100 → close=tradePrice/(1-Discount/100)
        if price is None:
            d = x.get("Discount")
            tp = x.get("TradePrice")
            if d is not None and tp and abs(d - 100) > 1e-9:
                price = round(tp / (1 - d / 100.0), 4)
        out_rows.append({
            "code": code,
            "name": x.get("name", ""),
            "tradePrice": x.get("TradePrice"),
            "value": x.get("TradeValue") or 0,
            "ratio": x.get("TradeRatio"),
            "discount": x.get("Discount"),
            "type": x.get("TradeType", ""),
            "buyer": x.get("BuySalesDepartment", ""),
            "seller": x.get("SellSalesDepartment", ""),
            "price": price,
            "changePercent": chg,
        })
    out_rows.sort(key=lambda r: -(r["value"] or 0))

    # 个股聚合
    agg = {}
    for r in out_rows:
        k = r["code"]
        e = agg.setdefault(k, {"code": k, "name": r["name"], "count": 0, "value": 0,
                               "discSum": 0.0, "discN": 0, "changePercent": r["changePercent"],
                               "price": r["price"]})
        e["count"] += 1
        e["value"] += r["value"] or 0
        if r["discount"] is not None:
            e["discSum"] += r["discount"]
            e["discN"] += 1
    by_stock = []
    for e in agg.values():
        e["avgDiscount"] = round(e["discSum"] / e["discN"], 3) if e["discN"] else None
        e.pop("discSum"); e.pop("discN")
        by_stock.append(e)
    by_stock.sort(key=lambda r: -r["value"])

    total = sum(r["value"] or 0 for r in out_rows)
    discs = [r["discount"] for r in out_rows if r["discount"] is not None]

    result = {
        "date": DATE,
        "snapDate": blk.get("date"),
        "source": "westock tool_event(block_past_30)",
        "count": len(out_rows),
        "stockCount": len(by_stock),
        "totalValue": total,
        "avgDiscount": round(sum(discs) / len(discs), 3) if discs else None,
        "discCount": sum(1 for d in discs if d > 0),
        "premCount": sum(1 for d in discs if d < 0),
        "flatCount": sum(1 for d in discs if d == 0),
        "instBuyCount": sum(1 for r in out_rows if INST_FLAG in (r["buyer"] or "")),
        "instSellCount": sum(1 for r in out_rows if INST_FLAG in (r["seller"] or "")),
        "quoteMatched": sum(1 for r in out_rows if r["changePercent"] is not None),
        "rows": out_rows,
        "byStock": by_stock,
    }

    os.makedirs(OUT_DIR, exist_ok=True)
    dst = os.path.join(OUT_DIR, f"{DATE}.json")
    with open(dst, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    print(f"OK -> {dst}")
    print(f"    笔数 {result['count']}｜股票 {result['stockCount']} 只｜成交额 {total/1e8:.4f} 亿元"
          f"｜平均折溢价 {result['avgDiscount']}%｜折价 {result['discCount']} 溢价 {result['premCount']}"
          f"｜机构买方 {result['instBuyCount']} 机构卖方 {result['instSellCount']}"
          f"｜行情补齐 {result['quoteMatched']}/{result['count']}")


if __name__ == "__main__":
    main()
