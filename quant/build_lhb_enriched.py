import json, os, re

Q = r"G:/ai/股票/quant"

def load(p):
    return json.load(open(os.path.join(Q, p), encoding="utf-8"))

master = load("lhb/2026-09-02.json")["data"]
batch1 = load("lhb_detail/2026-09-02_batch1.json")["data"]
batch2 = load("lhb_detail/2026-09-02_batch2.json")["data"]
batch3 = load("lhb_detail/2026-09-02_batch3.json")["data"]
code2sw1 = load("q2_full/_code2industry.json")
name2sw2 = load("_name2sw2.json")
sw1_detail = load("sw1_detail.json")
sw2_chg = load("sw2_chg_live.json")

# override sw1 for the 3 special codes (from data_profile / business)
SPECIAL_SW1 = {
    "sz301697": "基础化工",   # N贝特利 精细化学品(IPO首日,推测)
    "sh601123": "有色金属",   # N马矿 铁/钼矿(IPO首日,推测)
    "sz301655": "汽车",       # 绿控传动 profile.industry=汽车
}
SPECIAL_SW2 = {
    "sz301697": "化学制品",
    "sh601123": "小金属",
    "sz301655": None,  # 走 _name2sw2
}

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
    det = batch1.get(code) or batch2.get(code) or batch3.get(code) or {}
    reason = det.get("Reason") or ""
    buy_seats, sell_seats = parse_seats(det.get("LhbTradingDetails", "[]"))
    all_seats = buy_seats + sell_seats
    tags = sorted({s["tag"] for s in all_seats if s["tag"]})
    hotmoney_seats = [s for s in all_seats if s["tag"]]
    hotmoney_net = round(sum(s["buy"] - s["sell"] for s in hotmoney_seats), 2)
    n_tag = len(tags)
    level = "高" if n_tag >= 4 else ("中" if n_tag >= 1 else "低")

    # industry (sw1)
    sw1 = SPECIAL_SW1.get(code) or code2sw1.get(code)
    sw1_chg = sw1_detail.get(sw1, {}).get("changePct") if sw1 else None
    # industry2 (sw2)
    sw2 = SPECIAL_SW2.get(code)
    if sw2 is None:
        sw2 = name2sw2.get(name)
    sw2_chg_val = sw2_chg.get(sw2) if sw2 else None
    ipo = code in SPECIAL_SW1  # IPO 首日、行业为推测

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
        "ipo": ipo,
        "buySeats": buy_seats,
        "sellSeats": sell_seats,
        "hotmoneyTags": tags,
        "hotmoneyNet": hotmoney_net,
        "hotmoneyLevel": level,
        "hotmoneyCount": n_tag,
    }

out = {"date": master["date"], "count": len(enriched), "stocks": enriched}
json.dump(out, open(os.path.join(Q, "lhb_enriched_2026-09-02.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)

# report
print("\ncoverage:")
no_sw1 = [c for c,d in enriched.items() if not d["sw1"]]
no_sw2 = [c for c,d in enriched.items() if not d["sw2"]]
print("  no sw1:", no_sw1)
print("  no sw2:", no_sw2)
print("  sw1 with chg None:", [c for c,d in enriched.items() if d["sw1"] and d["sw1Chg"] is None])
print("  sw2 with chg None:", [c for c,d in enriched.items() if d["sw2"] and d["sw2Chg"] is None])
print("  sw2 chg val sample:", [(d["name"],d["sw2"],d["sw2Chg"]) for d in list(enriched.values())[:3]])
print("  hotmoney high:", sum(1 for d in enriched.values() if d["hotmoneyLevel"]=="高"))
print("  hotmoney mid :", sum(1 for d in enriched.values() if d["hotmoneyLevel"]=="中"))
print("  hotmoney low :", sum(1 for d in enriched.values() if d["hotmoneyLevel"]=="低"))
print("\nsample (大晟文化):")
s = enriched.get("sh600892") or {}
print(json.dumps(s, ensure_ascii=False, indent=1)[:1200])
