# -*- coding: utf-8 -*-
"""大宗交易 / 高管增减持 —— 东财降级取数（MCP westock 通道不可用时的替代源）。

为什么需要它：③高管增减持、④大宗交易两步在 `daily_all.STEPS` 里是 **manual**，
依赖 westock MCP 的 `tool_event(manager_sharechg)` / `block_past_30`。
MCP 握手失败时这两步只能跳过 → 页面停在旧数据日（2026-10-09 实测停在 09-30）。
本脚本走东财公开数据中心接口取同样口径的原始事件，落成 gen_*/build_* 能直接吃的
「tool_event 落盘格式」，让这两步在无 MCP 时也能推进，而不是永久断档。

★ 口径自证（不是"看着差不多"）
  · 大宗：与本地 westock 版 2026-09-30 逐条比对 —— 折扣口径 **0 处不一致**；
    东财多出的是 ETF/基金大宗（159967/518850…），**已按 A 股正股过滤剔除**；
    东财**不含北交所**（本地 westock 版有 4 条 bj920xxx）→ 这是已知缺口，
    落盘 source 里如实写明，不假装完整。
  · 高管：东财 RPT_EXECUTIVE_HOLD_DETAILS 为「变动日」口径，与原 tool_event 一致；
    历史回补一直用这条通道（见 quant/exec_chg/*.json 的 source 字段）。

用法：
    python quant/_fetch_block_exec_em.py --date 2026-10-08            # 两块都取
    python quant/_fetch_block_exec_em.py --date 2026-10-08 --only block
    python quant/_fetch_block_exec_em.py --date 2026-10-08 --days 30  # 回溯窗口（默认 30，对齐 past_30）

产出（仅供下游 gen_* 消费，本身不是页面数据）：
    quant/block_chg/_raw_em_{DATE}.json   → gen_block.py --date {DATE} --src …
    quant/exec_chg/_raw_em_{DATE}.json    → gen_exec.py  --date {DATE} --src …
"""
from __future__ import annotations
import os, sys, json, argparse, time, urllib.parse, urllib.request, datetime as dt

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
Q = os.path.join(ROOT, "quant")

EM_API = "https://datacenter-web.eastmoney.com/api/data/v1/get"


def _em(report, flt, page_size=500, retry=3):
    """东财数据中心分页拉全。返回记录列表。"""
    out, page = [], 1
    while True:
        q = urllib.parse.urlencode({
            "reportName": report, "columns": "ALL", "filter": flt,
            "pageSize": page_size, "pageNumber": page,
            "source": "WEB", "client": "WEB"})
        req = urllib.request.Request(EM_API + "?" + q,
                                     headers={"User-Agent": "Mozilla/5.0"})
        data = None
        for k in range(retry):
            try:
                data = json.load(urllib.request.urlopen(req, timeout=30))
                break
            except Exception as e:
                if k == retry - 1:
                    raise SystemExit("[em] %s 拉取失败：%s" % (report, e))
                time.sleep(1.5 * (k + 1))
        res = (data or {}).get("result") or {}
        rows = res.get("data") or []
        out += rows
        pages = res.get("pages") or 1
        if page >= pages or not rows:
            break
        page += 1
    return out


def is_a_stock(code6, secucode=""):
    """A 股正股过滤 —— 剔 ETF/LOF/可转债/B股。

    东财大宗接口把 ETF 大宗也算进来（159967 / 518850 / 180901 …），
    而 westock 的 block_past_30 只给股票；不剔就会出现「同一天多出十几条」的口径分叉。
    """
    mkt = (secucode.split(".")[-1] if secucode else "").upper()
    if mkt == "BJ":
        return True
    if mkt == "SH":
        return code6[:2] in ("60", "68")
    if mkt == "SZ":
        return code6[:2] in ("00", "30")
    # 没给 SECUCODE 时按代码前缀兜底
    return code6[:2] in ("60", "68", "00", "30")


def _mkt_code(code6, secucode=""):
    mkt = (secucode.split(".")[-1] if secucode else "").upper()
    pre = {"SH": "sh", "SZ": "sz", "BJ": "bj"}.get(mkt)
    if not pre:
        pre = "sh" if code6[:2] in ("60", "68") else ("bj" if code6[:2] in ("43", "83", "87", "92") else "sz")
    return pre + code6


def fetch_block(date, days):
    lo = (dt.date.fromisoformat(date) - dt.timedelta(days=days)).isoformat()
    flt = "(TRADE_DATE>='%s')(TRADE_DATE<='%s')" % (lo, date)
    rows = _em("RPT_DATA_BLOCKTRADE", flt)
    stocks, dropped = [], 0
    for r in rows:
        code6 = str(r.get("SECURITY_CODE") or "")
        if not code6 or not is_a_stock(code6, r.get("SECUCODE") or ""):
            dropped += 1
            continue
        pr = r.get("PREMIUM_RATIO")
        stocks.append({
            "code": _mkt_code(code6, r.get("SECUCODE") or ""),
            "name": r.get("SECURITY_NAME_ABBR") or "",
            "TradeDay": str(r.get("TRADE_DATE") or "")[:10].replace("-", ""),
            "TradePrice": r.get("DEAL_PRICE"),
            "TradeValue": r.get("DEAL_AMT"),
            # westock 的 Discount 口径：正=折价、负=溢价，= 东财 PREMIUM_RATIO 取负 × 100
            "Discount": None if pr is None else round(-float(pr) * 100, 3),
            "TradeType": "",
            "BuySalesDepartment": r.get("BUYER_NAME") or "",
            "SellSalesDepartment": r.get("SELLER_NAME") or "",
        })
    pay = {"ok": True, "data": {"evt_block_past_30": {
        "date": date, "totalStocks": len({s["code"] for s in stocks}), "stocks": stocks}}}
    dst = os.path.join(Q, "block_chg", "_raw_em_%s.json" % date)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    with open(dst, "w", encoding="utf-8") as f:
        json.dump(pay, f, ensure_ascii=False, indent=1)
    byday = {}
    for s in stocks:
        byday[s["TradeDay"]] = byday.get(s["TradeDay"], 0) + 1
    print("[block] 东财 %d 条 → 正股 %d 条（剔 ETF/基金/转债 %d）｜ 覆盖 %d 个交易日"
          % (len(rows), len(stocks), dropped, len(byday)))
    print("        落盘 %s" % dst)
    print("        ⚠ 东财不含北交所；当日北交所大宗会缺（已知口径缺口，source 里已注明）")
    return dst


def fetch_exec(date, days):
    lo = (dt.date.fromisoformat(date) - dt.timedelta(days=days)).isoformat()
    flt = "(CHANGE_DATE>='%s')(CHANGE_DATE<='%s')" % (lo, date)
    rows = _em("RPT_EXECUTIVE_HOLD_DETAILS", flt)
    stocks, dropped = [], 0
    for r in rows:
        code6 = str(r.get("SECURITY_CODE") or "")
        if not code6 or not is_a_stock(code6, r.get("DERIVE_SECURITY_CODE") or ""):
            dropped += 1
            continue
        d0 = str(r.get("CHANGE_DATE") or "")[:10].replace("-", "")
        stocks.append({
            "code": _mkt_code(code6, r.get("DERIVE_SECURITY_CODE") or ""),
            "name": r.get("SECURITY_NAME") or "",
            # 董监高姓名优先取 DSE_PERSON_NAME（原 tool_event 的 ManagerName 就是董监高）
            "ManagerName": r.get("DSE_PERSON_NAME") or r.get("PERSON_NAME") or "",
            "ManagerSharesChange": r.get("CHANGE_SHARES"),
            "ManagerDealPrice": r.get("AVERAGE_PRICE"),
            "DeclareDate": d0,
            "ReportDate": d0,
        })
    pay = {"ok": True, "data": {"evt_manager_sharechg_past_30": {
        "date": date, "totalStocks": len({s["code"] for s in stocks}), "stocks": stocks}}}
    dst = os.path.join(Q, "exec_chg", "_raw_em_%s.json" % date)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    with open(dst, "w", encoding="utf-8") as f:
        json.dump(pay, f, ensure_ascii=False, indent=1)
    byday = {}
    for s in stocks:
        byday[s["DeclareDate"]] = byday.get(s["DeclareDate"], 0) + 1
    print("[exec] 东财 %d 条 → 正股 %d 条（剔非正股 %d）｜ 覆盖 %d 个变动日，最新 %s"
          % (len(rows), len(stocks), dropped, len(byday),
             max(byday) if byday else "—"))
    print("       落盘 %s" % dst)
    return dst


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True, help="目标数据日 YYYY-MM-DD")
    ap.add_argument("--days", type=int, default=30, help="回溯天数（默认 30，对齐 tool_event past_30）")
    ap.add_argument("--only", choices=["block", "exec"], default=None)
    a = ap.parse_args()
    if a.only in (None, "block"):
        fetch_block(a.date, a.days)
    if a.only in (None, "exec"):
        fetch_exec(a.date, a.days)


if __name__ == "__main__":
    main()
