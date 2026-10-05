# -*- coding: utf-8 -*-
"""MACD 原始数据离线补数（MCP data_technical / data_fund_flow 限频时的降级通道）。

产出与 westock 原始落盘同构：
  macd_raw_tech_{DS}.json  —— MACD 从 _txk_cache 本地 EMA12/26 + DEA9 计算（已对 09-18
                              westock 实测 25 只逐点核对，误差 <0.02；bar=2*(DIF-DEA)）。
  macd_raw_flow_{DS}.json  —— 资金流走新浪 MoneyFlow（主力净流入 25 日）；
                              MainNetFlow20D=mf20、MainNetFlow=mf1、
                              MainInflowCircRate=mf1/流通市值、MainInflowRank=池内当日排名。

⚠️ 口径注记：新浪「主力」与 westock Jumbo+Block 存在阈值口径差（同 rev_pool 页面标注惯例）。

用法：python3 quant/_macd_offline.py --date 2026-09-21
"""
import os, sys, json, argparse
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _tx_fetch as T
from fetch_rev_flow import sina_batch

Q = HERE


def macd_at(code, date_str):
    bars = T._load().get(code)
    if not bars:
        return None
    idx = None
    for i, b in enumerate(bars):
        if b["date"] <= date_str:
            idx = i
        else:
            break
    if idx is None or idx < 40:
        return None
    cl = [b["last"] for b in bars[:idx + 1]]
    k12, k26, kd = 2 / 13, 2 / 27, 2 / 10
    x12 = x26 = cl[0]
    difs = []
    for v in cl:
        x12 = v * k12 + x12 * (1 - k12)
        x26 = v * k26 + x26 * (1 - k26)
        difs.append(x12 - x26)
    dif = difs[-1]
    dea = difs[0]
    for d_ in difs[1:]:
        dea = d_ * kd + dea * (1 - kd)

    def ma(n):
        if len(cl) < n:
            return None
        return round(sum(cl[-n:]) / n, 3)

    close = cl[-1]
    return {
        "code": code, "date": date_str, "closePrice": close,
        "ma": {k: ma(n) for k, n in (("MA_5", 5), ("MA_10", 10), ("MA_20", 20),
                                     ("MA_30", 30), ("MA_60", 60), ("MA_120", 120),
                                     ("MA_250", 250))},
        "macd": {"DIF": round(dif, 4), "DEA": round(dea, 4),
                 "MACD": round(2 * (dif - dea), 4)},
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    a = ap.parse_args()
    ds = a.date.replace("-", "")
    pool = json.load(open(os.path.join(Q, f"macd_raw_pool_{ds}.json"), encoding="utf-8"))
    stocks = pool["data"]["stocks"]
    codes = [s["code"] for s in stocks]
    print("[1/3] pool %d 只（已有）" % len(codes))

    # ---- pool 补行情：ClosePrice/ChangePCT（腾讯 qt 收盘口径，同 data_quote）----
    qt_all = T.fetch_qt(codes)
    for s in stocks:
        q = qt_all.get(s["code"], {})
        if q.get("last"):
            s["ClosePrice"] = q["last"]
            s["ChangePCT"] = q.get("change_percent", 0)
    json.dump(pool, open(os.path.join(Q, f"macd_raw_pool_{ds}.json"), "w",
                         encoding="utf-8"), ensure_ascii=False)
    filled = sum(1 for s in stocks if s.get("ClosePrice"))
    print("[1/3] pool %d 只，行情补齐 %d（ClosePrice/ChangePCT ← 腾讯 qt）"
          % (len(codes), filled))

    # ---- tech：本地 MACD ----
    tech = {}
    for code in codes:
        m = macd_at(code, a.date)
        if m:
            nm = next((s["name"] for s in stocks if s["code"] == code), "")
            m["name"] = nm
            tech[code] = m
    json.dump({"ok": True, "data": tech},
              open(os.path.join(Q, f"macd_raw_tech_{ds}.json"), "w", encoding="utf-8"),
              ensure_ascii=False)
    print("[2/3] tech 本地 MACD：覆盖 %d/%d" % (len(tech), len(codes)))

    # ---- flow：新浪 ----
    fb = sina_batch(codes, workers=10)
    # 流通市值（亿）→ 元，算 MainInflowCircRate
    qt = qt_all
    flow = {}
    for code, v in fb.items():
        mf1 = v.get("mf1") or 0.0
        circ = (qt.get(code, {}).get("circulating_market_cap") or 0) * 1e8
        flow[code] = {"data": [{
            "MainNetFlow20D": v.get("mf20") or 0,
            "MainNetFlow": mf1,
            "MainInflowCircRate": round(mf1 / circ * 100, 2) if circ else 0,
            "MainInflowRank": 0,
        }]}
    rank = sorted(fb.items(), key=lambda x: -(x[1].get("mf1") or 0))
    for i, (code, _) in enumerate(rank, 1):
        flow[code]["data"][0]["MainInflowRank"] = i
    json.dump({"ok": True, "data": flow},
              open(os.path.join(Q, f"macd_raw_flow_{ds}.json"), "w", encoding="utf-8"),
              ensure_ascii=False)
    print("[3/3] flow 新浪：覆盖 %d/%d（口径 sina，注意与 westock 主力阈值口径差）"
          % (len(flow), len(codes)))


if __name__ == "__main__":
    main()
