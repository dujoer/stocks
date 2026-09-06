#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""龙虎榜富集数据生成器（参数化版）

读取:
  quant/lhb/{DATE}.json                      主榜（all/jg/yyb/gslmr/gslxw）
  quant/lhb_detail/{DATE}_batch*.json        个股席位明细（可选；缺失则游资标签/席位留空）
  quant/q2_full/_code2industry.json          代码 -> 申万一级
  quant/_name2sw2.json                       名称 -> 申万二级
  quant/sw1_detail.json                      申万一级当日涨跌幅
  quant/sw2_chg_live.json                    申万二级当日涨跌幅

输出:
  quant/lhb_enriched_{DATE}.json             {date, count, stocks{code: {...}}}

历史坑（2026-09-06 修复）：
  旧版把日期硬编码为 2026-09-02（第 8-11 行加载、第 108 行输出），
  导致 09-03 之后每天都生成不出富集文件，龙虎榜页全榜表格退化为简化版
  （缺 上榜原因 / 一级行业 / 二级行业 / 游资介入度 / 席位 五列）。
  现改为 --date 参数化，并对缺失的 lhb_detail 容错降级。

用法:
  python quant/build_lhb_enriched.py --date 2026-09-04
"""
import argparse, glob, json, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
Q = os.path.join(ROOT, "quant")


def load(rel):
    p = os.path.join(Q, rel)
    if not os.path.exists(p):
        return {}
    return json.load(open(p, encoding="utf-8"))


def fnum(s):
    try:
        return float(s) if s not in ("", None) else 0.0
    except Exception:
        return 0.0


def parse_seats(raw):
    try:
        rows = json.loads(raw) if isinstance(raw, str) else raw
    except Exception:
        return [], []
    buy, sell = [], []
    for r in rows:
        tag = (r.get("HotMoneyTags") or "").strip()
        name = r.get("Name", "")
        b = fnum(r.get("Buy"))
        s = fnum(r.get("Sell"))
        rec = {"name": name, "buy": b, "sell": s, "tag": tag}
        if "买入" in (r.get("RankType") or ""):
            buy.append(rec)
        elif "卖出" in (r.get("RankType") or ""):
            sell.append(rec)
    buy.sort(key=lambda x: x["buy"], reverse=True)
    sell.sort(key=lambda x: x["sell"], reverse=True)
    return buy[:5], sell[:5]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True, help="交易日 YYYY-MM-DD")
    args = ap.parse_args()
    date = args.date

    master_path = os.path.join(Q, "lhb", f"{date}.json")
    if not os.path.exists(master_path):
        raise SystemExit(f"[fail] 主榜不存在: {master_path}")
    master = load(os.path.join("lhb", f"{date}.json"))["data"]

    # 席位明细：按 {DATE}_batch*.json 全部合并；缺失则为空（降级：无游资/席位）
    detail = {}
    dfiles = sorted(glob.glob(os.path.join(Q, "lhb_detail", f"{date}_batch*.json")))
    for fp in dfiles:
        detail.update(load(os.path.join("lhb_detail", os.path.basename(fp))).get("data", {}))
    print(f"席位明细文件: {len(dfiles)} 个, 覆盖 {len(detail)} 只"
          + ("" if detail else "  → 降级：游资标签/席位将留空（行业列仍可用）"))

    code2sw1 = load("q2_full/_code2industry.json")
    name2sw2 = load("_name2sw2.json")
    sw1_detail = load("sw1_detail.json")
    sw2_chg = load("sw2_chg_live.json")

    # dedupe master rows by code (keep the one with max |netBuyAmount|)
    rows_by_code = {}
    for r in master["all"]:
        c = r["code"]
        if c not in rows_by_code or abs(r["netBuyAmount"]) > abs(rows_by_code[c]["netBuyAmount"]):
            rows_by_code[c] = r
    print("unique LHB codes:", len(rows_by_code))

    enriched = {}
    for code, m in rows_by_code.items():
        name = m["name"]
        det = detail.get(code) or {}
        reason = det.get("Reason") or ""
        buy_seats, sell_seats = parse_seats(det.get("LhbTradingDetails", "[]"))
        all_seats = buy_seats + sell_seats
        tags = sorted({s["tag"] for s in all_seats if s["tag"]})
        hotmoney_seats = [s for s in all_seats if s["tag"]]
        hotmoney_net = round(sum(s["buy"] - s["sell"] for s in hotmoney_seats), 2)
        n_tag = len(tags)
        level = "高" if n_tag >= 4 else ("中" if n_tag >= 1 else "低")

        sw1 = code2sw1.get(code)
        sw1_chg = sw1_detail.get(sw1, {}).get("changePct") if sw1 else None
        sw2 = name2sw2.get(name)
        sw2_chg_val = sw2_chg.get(sw2) if sw2 else None

        enriched[code] = {
            "code": code,
            "name": name,
            "changePct": m.get("changePct"),
            "netBuy": m.get("netBuyAmount"),
            "buy": m.get("buyAmount"),
            "sell": m.get("sellAmount"),
            "reason": reason,
            "sw1": sw1,
            "sw1Chg": sw1_chg,
            "sw2": sw2,
            "sw2Chg": sw2_chg_val,
            "ipo": False,
            "buySeats": buy_seats,
            "sellSeats": sell_seats,
            "hotmoneyTags": tags,
            "hotmoneyNet": hotmoney_net,
            "hotmoneyLevel": level,
            "hotmoneyCount": n_tag,
        }

    out = {"date": date, "count": len(enriched), "stocks": enriched}
    op = os.path.join(Q, f"lhb_enriched_{date}.json")
    json.dump(out, open(op, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    no_sw1 = [c for c, d in enriched.items() if not d["sw1"]]
    no_sw2 = [c for c, d in enriched.items() if not d["sw2"]]
    n_seat = sum(1 for d in enriched.values() if d["buySeats"] or d["sellSeats"])
    print(f"\n[ok] {op}")
    print(f"  count={len(enriched)}  有席位明细={n_seat}  no sw1={len(no_sw1)}  no sw2={len(no_sw2)}")
    print(f"  游资介入度: 高={sum(1 for d in enriched.values() if d['hotmoneyLevel']=='高')} "
          f"中={sum(1 for d in enriched.values() if d['hotmoneyLevel']=='中')} "
          f"低={sum(1 for d in enriched.values() if d['hotmoneyLevel']=='低')}")


if __name__ == "__main__":
    main()
