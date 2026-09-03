# -*- coding: utf-8 -*-
"""龙虎榜净买入股票 · 次日表现回测。

输入：
  --date DATE                 龙虎榜口径日（如 2026-09-02）
  --quotes <file>            data_quote(date=次日) 的落盘 JSON（结构 {ok,data:{code:{...}}}）
  --next-date <date>         次日日期（仅用于标注；若省略则留空）

输出：
  quant/lhb_nextday_backtest/{DATE}.json
    { date, next_date, generated_at,
      groups: { inst / hot / all : {count,win,win_rate,avg_return,median_return,best,worst,stocks:[...]} },
      union_codes: [...] }

口径说明：
  次日收益 = data_quote(次日) 的 change_percent（相对前收盘），即「T 日上榜、T+1 日收盘」收益。
  净买入分组：
    inst 机构净买入 = jg(netBuyAmt>0) ∪ gslmr(netAmt>0)（按 code 合并净买额）
    hot  游资净买入 = all(netBuyAmount>0) 中、且出现在游资席位涉及个股(stockName) 的子集
    all  全体净买入 = all(netBuyAmount>0)
"""
from __future__ import annotations
import json, os, argparse, datetime, statistics

QUANT = os.path.dirname(os.path.abspath(__file__))
OUTDIR = os.path.join(QUANT, "lhb_nextday_backtest")
os.makedirs(OUTDIR, exist_ok=True)


def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def f1(x):
    try:
        return round(float(x), 2)
    except Exception:
        return 0.0


def collect(DATE):
    lhb = load(os.path.join(QUANT, "lhb", f"{DATE}.json"))
    data = lhb["data"] if isinstance(lhb, dict) and "data" in lhb else lhb

    # name -> code（来自 all 全榜，便于把游资席位 stockName 映射回 code）
    name2code = {}
    allrows = data.get("all", [])
    for r in allrows:
        if r.get("code") and r.get("name"):
            name2code[r["name"]] = r["code"]

    # 机构净买入：jg(netBuyAmt>0) + gslmr(netAmt>0)
    inst = {}
    for r in data.get("jg", []):
        amt = f1(r.get("netBuyAmt"))
        if amt > 0 and r.get("code"):
            inst[r["code"]] = {"name": r["name"], "amt": amt}
    for r in data.get("gslmr", []):
        amt = f1(r.get("netAmt"))
        if amt > 0 and r.get("code"):
            c = r["code"]
            cur = inst.get(c, {"name": r["name"], "amt": 0.0})
            cur["name"] = r["name"]
            cur["amt"] = round(cur["amt"] + amt, 2)
            inst[c] = cur

    # 全体净买入：all(netBuyAmount>0)
    allnet = {}
    for r in allrows:
        amt = f1(r.get("netBuyAmount"))
        if amt > 0 and r.get("code"):
            allnet[r["code"]] = {"name": r["name"], "amt": amt}

    # 游资净买入：all 净买 ∩ 游资席位涉及个股
    hot_names = set()
    for r in data.get("yyb", []):
        sn = (r.get("stockName") or "").strip()
        if sn:
            hot_names.add(sn)
    hot = {c: info for c, info in allnet.items() if info["name"] in hot_names}

    return {"inst": inst, "hot": hot, "all": allnet}


def analyze(group, quotes):
    stocks, chgs = [], []
    for code, info in group.items():
        q = quotes.get(code)
        if not q or not q.get("name"):
            continue  # 跳过无名称条目（如可转债）
        chg = f1(q.get("change_percent"))
        stocks.append({
            "code": code, "name": info["name"],
            "net_amt": info["amt"], "next_chg": chg, "win": chg > 0,
        })
        chgs.append(chg)
    n = len(stocks)
    if n == 0:
        return {"count": 0, "win": 0, "win_rate": None, "avg_return": None,
                "median_return": None, "best": None, "worst": None, "stocks": []}
    wins = sum(1 for s in stocks if s["win"])
    return {
        "count": n, "win": wins,
        "win_rate": round(wins / n * 100, 1),
        "avg_return": round(statistics.mean(chgs), 2),
        "median_return": round(statistics.median(chgs), 2),
        "best": max(chgs), "worst": min(chgs),
        "stocks": sorted(stocks, key=lambda s: -s["next_chg"]),
    }


def main():
    ap = argparse.ArgumentParser(description="龙虎榜净买入股票次日表现回测")
    ap.add_argument("--date", required=True, help="龙虎榜口径日 YYYY-MM-DD")
    ap.add_argument("--quotes", required=True, help="data_quote(date=次日) 落盘 JSON")
    ap.add_argument("--next-date", default=None, help="次日日期（标注用）")
    args = ap.parse_args()

    groups = collect(args.date)
    qj = load(args.quotes)
    quotes = qj.get("data", qj) if isinstance(qj, dict) else qj
    if isinstance(quotes, list):
        quotes = {x.get("code"): x for x in quotes if x.get("code")}

    result = {
        "date": args.date,
        "next_date": args.next_date or "",
        "generated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "groups": {
            "inst": analyze(groups["inst"], quotes),
            "hot": analyze(groups["hot"], quotes),
            "all": analyze(groups["all"], quotes),
        },
        "union_codes": sorted(set(groups["inst"]) | set(groups["hot"]) | set(groups["all"])),
    }
    out = os.path.join(OUTDIR, f"{args.date}.json")
    json.dump(result, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    g = result["groups"]
    print(f"OK: 次日回测 -> {out}")
    for k, label in (("inst", "机构净买"), ("hot", "游资净买"), ("all", "全体净买")):
        gg = g[k]
        wr = f"{gg['win_rate']}%" if gg["win_rate"] is not None else "—"
        av = f"{gg['avg_return']}%" if gg["avg_return"] is not None else "—"
        print(f"  {label}: 样本 {gg['count']} 只 | 次日胜率 {wr} | 平均次日 {av}")


if __name__ == "__main__":
    main()
