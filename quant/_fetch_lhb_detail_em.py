# -*- coding: utf-8 -*-
"""龙虎榜 · 个股席位明细 —— 东财降级源（westock MCP data_lhb_detail 不可用时）。

背景：`lhb_detail/{DATE}_batch*.json` 由 westock 提供（含买入/卖出席位 + 游资标签）。
MCP 不通时该目录停更（10-08/10-09 缺位）→ 页面「席位」与「游资介入度」两列退化。

本脚本用东财数据中心两个接口重建**同构**文件：
  RPT_BILLBOARD_DAILYDETAILSBUY   买入营业部排行
  RPT_BILLBOARD_DAILYDETAILSSELL  卖出营业部排行
字段对齐 build_lhb_enriched.parse_seats：
  LhbTradingDetails = [{RankType,Reason,Rank,Name,Buy,Sell,HotMoneyTags}]

⚠ 诚实边界：东财**无游资标签**（HotMoneyTags 一律留空）。
   本文件顶层写 "hotmoney_tag": false，供页面如实标注「游资等级：源不可判」，
   严禁把「无标签」显示成「低」——那是把缺失当结论。
用法：python quant/_fetch_lhb_detail_em.py --date 2026-10-09
"""
from __future__ import annotations
import os, sys, json, time, argparse, urllib.parse, urllib.request

Q = os.path.dirname(os.path.abspath(__file__))
API = "https://datacenter-web.eastmoney.com/api/data/v1/get"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120 Safari/537.36"


def _get(report, date, page, size):
    flt = "(TRADE_DATE='%s')" % date
    q = {"reportName": report, "columns": "ALL", "filter": flt,
         "pageSize": str(size), "pageNumber": str(page), "source": "WEB", "client": "WEB"}
    url = API + "?" + urllib.parse.urlencode(q)
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": "https://data.eastmoney.com/"})
    raw = urllib.request.urlopen(req, timeout=25).read().decode("utf-8", "ignore")
    j = json.loads(raw)
    res = j.get("result") or {}
    return res.get("pages") or 0, (res.get("data") or [])


def fetch_all(report, date, size=500):
    rows, page = [], 1
    while True:
        pages, data = _get(report, date, page, size)
        rows.extend(data)
        if not data or page >= pages:
            break
        page += 1
        time.sleep(0.25)
    return rows


def code_of(rec):
    sec = str(rec.get("SECURITY_CODE") or "").strip()
    suf = (rec.get("SECUCODE") or "").split(".")[-1].upper()
    pre = {"SZ": "sz", "SH": "sh", "BJ": "bj"}.get(suf)
    if not pre:
        pre = "sh" if sec.startswith(("6", "9")) else ("bj" if sec.startswith(("4", "8")) else "sz")
    return pre + sec


def _f(v):
    try:
        return float(v)
    except Exception:
        return 0.0


def build(date):
    DS = date.replace("-", "")
    buy = fetch_all("RPT_BILLBOARD_DAILYDETAILSBUY", date)
    sell = fetch_all("RPT_BILLBOARD_DAILYDETAILSSELL", date)
    print("[em] 买入席位 %d 条 / 卖出席位 %d 条" % (len(buy), len(sell)))

    grp = {}

    def put(recs, kind):
        for r in recs:
            c = code_of(r)
            g = grp.setdefault(c, {"buy": [], "sell": [], "meta": {}})
            item = {"Reason": r.get("EXPLANATION") or "", "RankType": kind,
                    "Name": r.get("OPERATEDEPT_NAME") or "",
                    "Buy": _f(r.get("BUY")), "Sell": _f(r.get("SELL")),
                    "HotMoneyTags": ""}
            (g["buy"] if kind.startswith("买入") else g["sell"]).append(item)
            g["meta"].setdefault("name", None)
            g["meta"]["closePrice"] = _f(r.get("CLOSE_PRICE"))
            g["meta"]["changePct"] = _f(r.get("CHANGE_RATE"))

    put(buy, "买入营业部排行榜")
    put(sell, "卖出营业部排行榜")

    # 名称与总额：优先取 lhb/{DATE}.json（站点主表，已含 code/name/买卖额）
    lhb_p = os.path.join(Q, "lhb", f"{date}.json")
    name_map, amt_map = {}, {}
    if os.path.exists(lhb_p):
        d = (json.load(open(lhb_p, encoding="utf-8")).get("data") or {})
        for r in (d.get("all") or []):
            if r.get("code"):
                name_map[r["code"]] = r.get("name")
                amt_map[r["code"]] = r
    if not name_map:
        try:
            name_map = {c: n for c, n in json.load(
                open(os.path.join(Q, "_stock_names.json"), encoding="utf-8")).items()}
        except Exception:
            pass

    data = {}
    cnt_seats = 0
    for c, g in grp.items():
        # 席位榜各自按金额降序、编号 rank
        bu = sorted(g["buy"], key=lambda x: x["Buy"], reverse=True)[:5]
        se = sorted(g["sell"], key=lambda x: x["Sell"], reverse=True)[:5]
        for i, x in enumerate(bu, 1):
            x["Rank"] = i
        for i, x in enumerate(se, 1):
            x["Rank"] = i
        details = bu + se
        cnt_seats += len(details)
        a = amt_map.get(c) or {}
        reason = next((x["Reason"] for x in details if x["Reason"]), "")
        data[c] = {
            "code": c,
            "name": name_map.get(c) or "",
            "date": date,
            "changePct": a.get("changePct", g["meta"].get("changePct")),
            "closePrice": g["meta"].get("closePrice"),
            "LhbInfos": json.dumps([{"Reason": reason,
                                     "TotalBuy": a.get("buyAmount"), "TotalSell": a.get("sellAmount"),
                                     "NetBuy": a.get("netBuyAmount")}], ensure_ascii=False),
            "LhbTradingDetails": json.dumps(details, ensure_ascii=False),
            "Reason": reason,
            "TotalBuy": a.get("buyAmount"), "TotalSell": a.get("sellAmount"),
            "NetBuy": a.get("netBuyAmount"),
        }

    out = {"ok": True, "src": "eastmoney", "hotmoney_tag": False,
           "note": "东财降级源：含买卖席位明细；无游资标签（HotMoneyTags 留空），游资等级不可判。",
           "data": data}
    dst = os.path.join(Q, "lhb_detail", f"{date}_batch1.json")
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    json.dump(out, open(dst, "w", encoding="utf-8"), ensure_ascii=False)
    print("[em] 写完 %s：%d 只 / %d 条席位｜游资标签：无" % (dst, len(data), cnt_seats))


def main():
    ap = argparse.ArgumentParser(description="龙虎榜席位明细（东财降级源）")
    ap.add_argument("--date", required=True, help="交易日期 YYYY-MM-DD")
    a = ap.parse_args()
    build(a.date)


if __name__ == "__main__":
    main()
