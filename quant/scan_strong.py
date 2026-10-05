# -*- coding: utf-8 -*-
"""全市场强势扫描（离线，腾讯公开接口，无 MCP 限额）。

两段式：
  ① qt 快照全市场（80 只/请求）→ 基础门槛粗筛（价格/市值/换手/52周分位/涨跌幅）
  ② 对粗筛存活者拉日K（复用 _tx_fetch 缓存）→ 计算相对强度与技术结构

输出：quant/tplus/_strong_scan_{D}.json
  {date, benchmark:{code,chg20,chg60}, scanned, passed, rows:[{code,name,industry,
   price,chg,chg20,chg60,rs20,rs60,ma5,ma10,ma20,ma60,multi,slope,amp20,atr_pct,
   box_h,pos,pos52,turn,amt_yi,cmc_yi,pe,vol_ratio,hi52,lo52,newhigh20,newhigh60}]}

用法：python scan_strong.py --date 2026-09-18 [--workers 24] [--no-cache-refresh]
"""
from __future__ import annotations
import os, sys, json, argparse, datetime, time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _tx_fetch as T

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
C2I = os.path.join(ROOT, "quant", "q2_full", "_code2industry.json")
OUT_DIR = os.path.join(ROOT, "quant", "tplus")
BENCH = "sh000001"

BAD_NAME = ("ST", "退", "*ST")


def bench_chg(date, n):
    """上证指数最近 n 个交易日涨幅（%）。用 _idxkline 的缓存序列。"""
    ser = {}
    p = os.path.join(ROOT, "quant", "_idx_kline.json")
    if os.path.exists(p):
        try:
            ser = (json.load(open(p, encoding="utf-8")) or {}).get(BENCH) or {}
        except Exception:
            ser = {}
    ds = sorted(d for d in ser if d <= date)
    if len(ds) < n + 1:
        return None, None
    c0 = ser[ds[-1]]
    cn = ser[ds[-(n + 1)]]
    return ((c0 - cn) / cn * 100 if cn else None), ds[-1]


def to_nodes(kasc, code=None):
    """升序日K -> build_tplus 口径的倒序 node（amount 按板块统一口径估算，单位：元）。

    ⚠️ 腾讯 volume 单位不统一（688=股，其余=手）—— 原实现一律 `*100` 会让
    科创板成交额虚高 100 倍、并被强势门槛误放行。必须传 code 走 `T.vol_unit`。
    """
    u = T.vol_unit(code) if code else 100.0
    nodes = []
    for it in kasc:
        avg = (it["high"] + it["low"] + it["last"]) / 3.0
        nodes.append({"date": it["date"], "open": it["open"], "last": it["last"],
                      "high": it["high"], "low": it["low"], "volume": it["volume"],
                      "amount": round(it["volume"] * u * avg, 0), "exchange": ""})
    nodes.reverse()
    return nodes


def features(code, name, industry, q, nodes, b20, b60):
    """nodes 倒序（[0] 最新）。返回强势特征或 None。"""
    if not nodes or len(nodes) < 65:
        return None
    closes = [n["last"] for n in nodes]
    highs = [n["high"] for n in nodes]
    lows = [n["low"] for n in nodes]
    amts = [n.get("amount") or 0 for n in nodes]
    price = closes[0]
    if not price:
        return None

    def ma(arr, n):
        return sum(arr[:n]) / n if len(arr) >= n else None

    ma5, ma10, ma20, ma60 = ma(closes, 5), ma(closes, 10), ma(closes, 20), ma(closes, 60)
    if not (ma5 and ma20 and ma60):
        return None
    ma20_prev = sum(closes[5:25]) / 20 if len(closes) >= 25 else None
    slope = (ma20 - ma20_prev) / ma20_prev * 100 if ma20_prev else 0.0

    chg20 = (price - closes[20]) / closes[20] * 100 if closes[20] else None
    chg60 = (price - closes[60]) / closes[60] * 100 if closes[60] else None
    rs20 = (chg20 - b20) if (chg20 is not None and b20 is not None) else None
    rs60 = (chg60 - b60) if (chg60 is not None and b60 is not None) else None

    box_high, box_low = max(highs[:20]), min(lows[:20])
    box_h = (box_high - box_low) / box_low * 100 if box_low else 0
    pos = (price - box_low) / (box_high - box_low) * 100 if box_high > box_low else 50

    trs = []
    for i in range(min(14, len(nodes) - 1)):
        h, l, pc = highs[i], lows[i], closes[i + 1]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    atr = sum(trs) / len(trs) if trs else 0
    atr_pct = atr / price * 100 if price else 0

    amps = []
    for i in range(min(20, len(nodes) - 1)):
        pc = closes[i + 1]
        if pc:
            amps.append((highs[i] - lows[i]) / pc * 100)
    amp20 = sum(amps) / len(amps) if amps else 0

    hi52 = q.get("high_52week") or max(highs[:min(250, len(highs))])
    lo52 = q.get("low_52week") or min(lows[:min(250, len(lows))])
    pos52 = (price - lo52) / (hi52 - lo52) * 100 if hi52 > lo52 else 50

    amt_yi = (sum(amts[:20]) / 20) / 1e8

    return {
        "code": code, "name": name, "industry": industry,
        "price": round(price, 2), "chg": q.get("change_percent"),
        "chg20": round(chg20, 2) if chg20 is not None else None,
        "chg60": round(chg60, 2) if chg60 is not None else None,
        "rs20": round(rs20, 2) if rs20 is not None else None,
        "rs60": round(rs60, 2) if rs60 is not None else None,
        "ma5": round(ma5, 2), "ma10": round(ma10, 2) if ma10 else None,
        "ma20": round(ma20, 2), "ma60": round(ma60, 2),
        "multi": bool(ma5 > ma10 > ma20 > ma60) if ma10 else False,
        "slope": round(slope, 2),
        "above20": bool(price > ma20), "above60": bool(price > ma60),
        "amp20": round(amp20, 2), "atr_pct": round(atr_pct, 2),
        "box_h": round(box_h, 2), "pos": round(pos, 1), "pos52": round(pos52, 1),
        "turn": q.get("turnover_rate"), "vol_ratio": q.get("volume_ratio"),
        "amt_yi": round(amt_yi, 2), "cmc_yi": q.get("circulating_market_cap"),
        "pe": q.get("pe_ratio"), "pb": q.get("pb_ratio"),
        "hi52": hi52, "lo52": lo52,
        "new20": bool(price >= box_high * 0.995),
        "new60": bool(price >= max(highs[:60]) * 0.995),
        "to_hi52": round((price - hi52) / hi52 * 100, 2) if hi52 else None,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=datetime.date.today().strftime("%Y-%m-%d"))
    ap.add_argument("--workers", type=int, default=24)
    ap.add_argument("--limit", type=int, default=0, help="调试用：只扫前 N 只")
    ap.add_argument("--rescan", action="store_true", help="忽略已有结果强制重扫")
    a = ap.parse_args()

    op = os.path.join(OUT_DIR, f"_strong_scan_{a.date}.json")
    if os.path.exists(op) and not a.rescan:
        print(f"[scan_strong] 已存在 {op}，跳过（--rescan 强制重跑）")
        return

    c2i = json.load(open(C2I, encoding="utf-8"))
    codes = [c for c in c2i.keys() if c[:2] in ("sh", "sz")]
    if a.limit:
        codes = codes[:a.limit]
    print(f"[scan_strong] 全市场 sh/sz {len(codes)} 只，qt 快照粗筛…", flush=True)

    t0 = time.time()
    qt = T.fetch_qt(codes)
    print(f"[scan_strong] qt 命中 {len(qt)}/{len(codes)}，耗时 {time.time()-t0:.0f}s", flush=True)

    # ---- ① 基础门槛（与 build_tplus 硬门槛对齐，可宽松一点留余量） ----
    keep = []
    for c in codes:
        q = qt.get(c)
        if not q or not q.get("last"):
            continue
        nm = q.get("name") or ""
        if any(k in nm for k in BAD_NAME):
            continue
        p = q["last"]
        if p < 3:
            continue
        cmc = q.get("circulating_market_cap") or 0
        if not (20 <= cmc <= 1200):
            continue
        turn = q.get("turnover_rate") or 0
        if not (2 <= turn <= 20):
            continue
        hi, lo = q.get("high_52week") or 0, q.get("low_52week") or 0
        if hi > lo:
            pos52 = (p - lo) / (hi - lo) * 100
            if not (12 <= pos52 <= 92):
                continue
        keep.append(c)
    print(f"[scan_strong] 粗筛存活 {len(keep)}/{len(codes)}（价格/市值/换手/52周分位）", flush=True)

    # ---- ② 日K 拉取 + 强势特征 ----
    b20, bdate = bench_chg(a.date, 20)
    b60, _ = bench_chg(a.date, 60)
    print(f"[scan_strong] 基准 {BENCH} @ {bdate}：20日 {b20}% / 60日 {b60}%", flush=True)

    rows, miss = [], 0
    t1 = time.time()
    done = [0]

    def work(c):
        return c, T.fetch_kline(c, 250)

    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        for c, k in ex.map(work, keep):
            done[0] += 1
            if done[0] % 300 == 0:
                print(f"  …{done[0]}/{len(keep)}  ({time.time()-t1:.0f}s)", flush=True)
            if not k or len(k) < 65:
                miss += 1
                continue
            f = features(c, (qt.get(c) or {}).get("name"), c2i.get(c), qt.get(c) or {},
                         to_nodes(k, c), b20, b60)
            if f:
                rows.append(f)
    T.save_cache()
    print(f"[scan_strong] 特征完成 {len(rows)} 只（缺K线 {miss}），耗时 {time.time()-t1:.0f}s", flush=True)

    # ---- ③ 只保留「强势」：跑赢指数 + 站上 MA20 ----
    strong = [r for r in rows
              if (r["rs20"] is not None and r["rs20"] >= 5.0)
              and r["above20"] and (r["rs60"] is None or r["rs60"] >= -5.0)]
    strong.sort(key=lambda r: (r["rs20"] or 0), reverse=True)
    print(f"[scan_strong] 强势股（20日超额 ≥5pp 且站上 MA20）{len(strong)} 只")

    os.makedirs(OUT_DIR, exist_ok=True)
    json.dump({"date": a.date, "benchmark": {"code": BENCH, "date": bdate, "chg20": b20, "chg60": b60},
               "scanned": len(codes), "prescreen": len(keep), "passed": len(rows),
               "strong": len(strong), "rows": rows},
              open(op, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"[scan_strong] → {op}")


if __name__ == "__main__":
    main()
