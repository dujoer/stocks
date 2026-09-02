# -*- coding: utf-8 -*-
"""
高管（董监高）增减持 · 数据生成
--------------------------------
数据源：westock-mcp tool_event(names="manager_sharechg") —— 过去 1 个月内
        发生了董监高增减持披露的全市场记录（单条 = 一位高管的一次变动）。

本脚本做 4 件事：
  1) 读取 MCP 落盘原始文件（或从 --src 指定）
  2) 派生字段：方向（增持/减持）、变动股数、成交均价、变动金额
  3) 补维度：申万一级（按 code）、申万二级（按 name）
  4) 按「披露日 DeclareDate」分组落盘，供 build_exec.py 渲染

用法：
    python quant/gen_exec.py --date 2026-09-02
    python quant/gen_exec.py --date 2026-09-02 --src <落盘txt路径>

注意（硬规矩）：本脚本只处理公开披露的高管增减持，不涉及、不输出任何个人持仓/选股。
"""
import os, sys, json, argparse, collections

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
Q = os.path.join(ROOT, "quant")

# MCP 大响应自动落盘目录（本次 668 条全量落盘于此）
TOOL_RESULTS = r"C:/Users/nonoy/.workbuddy/projects/g-ai-股票/e3ab6e4e-351f-47a8-a451-53f648954b46/tool-results"


def load(p):
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def find_latest_src():
    """在 tool-results 中找最新的 manager_sharechg 落盘文件。"""
    if not os.path.isdir(TOOL_RESULTS):
        return None
    cands = [f for f in os.listdir(TOOL_RESULTS)
             if "tool_event" in f and f.endswith(".txt")]
    if not cands:
        return None
    cands.sort(key=lambda f: os.path.getmtime(os.path.join(TOOL_RESULTS, f)), reverse=True)
    for f in cands:
        p = os.path.join(TOOL_RESULTS, f)
        try:
            d = json.load(open(p, encoding="utf-8"))
            if "evt_manager_sharechg_past_30" in (d.get("data") or {}):
                return p
        except Exception:
            continue
    return None


def to_f(v, default=0.0):
    try:
        return float(v)
    except Exception:
        return default


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True, help="采集日 YYYY-MM-DD")
    ap.add_argument("--src", default=None, help="原始落盘文件路径（默认自动探测最新）")
    ap.add_argument("--quotes", default=None,
                    help="行情落盘文件路径（data_quote 全量拉取的 214 只）；提供则为每条记录补涨跌幅/现价/换手")
    args = ap.parse_args()

    DATE = args.date
    src = args.src or find_latest_src()
    if not src or not os.path.exists(src):
        print("未找到原始落盘文件，请先用 tool_event(names=manager_sharechg) 拉取后重试，或用 --src 指定。")
        sys.exit(2)

    raw = load(src)
    blk = raw["data"]["evt_manager_sharechg_past_30"]
    stocks = blk.get("stocks", [])
    snap_date = blk.get("date")
    total = blk.get("totalStocks", len(stocks))
    print(f"原始记录: {len(stocks)} / totalStocks={total} / 快照日={snap_date}")

    # ---- 行业映射 ----
    code2sw1 = load(os.path.join(Q, "q2_full", "_code2industry.json"))
    name2sw2 = load(os.path.join(Q, "_name2sw2.json"))

    recs = []
    for s in stocks:
        code = s.get("code", "")
        name = s.get("name", "")
        chg = to_f(s.get("ManagerSharesChange"))
        price = to_f(s.get("ManagerDealPrice"))
        ddate = str(s.get("DeclareDate", "")).strip()
        recs.append({
            "code": code,
            "name": name,
            "manager": s.get("ManagerName", ""),
            "shares": chg,                       # 正=增持 负=减持
            "price": price,
            "amount": abs(chg) * price,          # 变动金额（元）
            "dir": "增持" if chg > 0 else ("减持" if chg < 0 else "—"),
            "declare": ddate,
            "report": str(s.get("ReportDate", "")).strip(),
            "sw1": code2sw1.get(code, ""),
            "sw2": name2sw2.get(name, ""),
            "chgPct": None,                      # 涨跌幅，后续行情补齐
        })

    # ---- 行情合并（可选，幂等）----
    QUOTE_DST = os.path.join(Q, "quotes", f"exec_{DATE}.json")
    qsrc = args.quotes if (args.quotes and os.path.exists(args.quotes)) else (
        QUOTE_DST if os.path.exists(QUOTE_DST) else None)
    if qsrc:
        qraw = load(qsrc)
        qmap = qraw.get("data", {})
        hit = 0
        for r in recs:
            q = qmap.get(r["code"])
            if q:
                r["chgPct"] = q.get("change_percent")
                r["priceNow"] = q.get("price")
                r["turnover"] = q.get("turnover_rate")
                hit += 1
        print(f"行情补齐: {hit}/{len(recs)} 条（源 {os.path.basename(qsrc)}）")
        if qsrc == args.quotes:
            os.makedirs(os.path.dirname(QUOTE_DST), exist_ok=True)
            slim = {c: {k: v.get(k) for k in ("name", "price", "change_percent", "turnover_rate")}
                    for c, v in qmap.items()}
            with open(QUOTE_DST, "w", encoding="utf-8") as f:
                json.dump({"date": DATE, "data": slim}, f, ensure_ascii=False, indent=1)
            print(f"行情留存 -> {QUOTE_DST}")
    else:
        print("未提供行情源，chgPct 留空（可用 --quotes 补齐）")

    # ---- 统计 ----
    buy = [r for r in recs if r["dir"] == "增持"]
    sell = [r for r in recs if r["dir"] == "减持"]
    codes = sorted({r["code"] for r in recs})
    by_date = collections.defaultdict(list)
    for r in recs:
        by_date[r["declare"]].append(r)

    print(f"增持记录 {len(buy)} / 减持记录 {len(sell)}")
    print(f"涉及股票 {len(codes)} 只，披露日 {len(by_date)} 个")
    print(f"最新披露日: {max(by_date.keys()) if by_date else '—'}")
    missing_sw1 = sum(1 for r in recs if not r["sw1"])
    print(f"缺申万一级: {missing_sw1} 条")

    out = {
        "date": DATE,                 # 采集日
        "snapDate": snap_date,        # 接口快照日
        "totalStocks": total,
        "count": len(recs),
        "buyCount": len(buy),
        "sellCount": len(sell),
        "stockCount": len(codes),
        "codes": codes,               # 去重股票（供后续补行情）
        "latestDeclare": max(by_date.keys()) if by_date else None,
        "byDate": {d: by_date[d] for d in sorted(by_date.keys(), reverse=True)},
        "records": sorted(recs, key=lambda r: (r["declare"], -abs(r["amount"])), reverse=True),
    }

    os.makedirs(os.path.join(Q, "exec_chg"), exist_ok=True)
    dst = os.path.join(Q, "exec_chg", f"{DATE}.json")
    with open(dst, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"OK -> {dst}")


if __name__ == "__main__":
    main()
