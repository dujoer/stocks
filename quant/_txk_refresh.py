# -*- coding: utf-8 -*-
"""强制刷新 _txk_cache.json 到最新交易日（腾讯前复权日K）。

fetch_full_kline.py 只补缺失标的、跳过已缓存；本脚本对**全部已缓存标的**重新拉取，
把最新交易日追加进去（前复权口径可能与历史略有出入，故整段替换）。

用法：
  python3 quant/_txk_refresh.py --check          # 统计缓存最新日分布
  python3 quant/_txk_refresh.py [--end 2026-09-21] [--workers 14]

★ 2026-10-13 修（根因）：刷新域原为「已缓存代码」，建库时漏抓的代码永远不会被补进来
  （实测 186 只老票整只不在短缓存，却全在长K缓存里有完整数据，且无任何报错）。
  后果：读短缓存的 market_overview / 龙道诀第一~三节，10-13 涨停家数少算 3 家
  （67 vs 长K口径 70；差异股 sh600370/sz002667/sz301030 均整只缺失）。
  现刷新域 = 已缓存 ∪ 最新行情快照中的股票（is_stock 过滤），漏网码自动补拉。
"""
import os, sys, json, time, argparse, glob, re
from concurrent.futures import ThreadPoolExecutor, as_completed
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _tx_fetch as T

TX_KLINE = T.TX_KLINE
UA = getattr(T, "UA", "Mozilla/5.0")


def _universe(c):
    """短缓存应有的代码全集 = 已缓存 ∪ 最新行情快照中的股票。"""
    us = set(c.keys())
    try:
        qdir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "quotes")
        fs = [f for f in glob.glob(os.path.join(qdir, "*.json"))
              if re.match(r"^\d{4}-\d{2}-\d{2}\.json$", os.path.basename(f))]
        if fs:
            qd = json.load(open(max(fs), encoding="utf-8")).get("data") or {}
            us |= set(k for k in qd if T.is_stock(k))
    except Exception:
        pass
    return sorted(us)


def fetch_fresh(code, n=250, retries=3):
    url = "%s?param=%s,day,,,%d,qfq" % (TX_KLINE, code, n)
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": UA, "Referer": "https://gu.qq.com/",
                "Connection": "close"})
            with urllib.request.urlopen(req, timeout=20) as r:
                j = json.loads(r.read().decode("utf-8"))
            d = ((j.get("data") or {}).get(code) or {})
            ks = d.get("qfqday") or d.get("day") or []
            if ks:
                return [{"date": it[0], "open": float(it[1]),
                         "last": float(it[2]), "high": float(it[3]),
                         "low": float(it[4]), "volume": float(it[5])} for it in ks]
            return None
        except Exception:
            time.sleep(0.5 * (i + 1))
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--end", default=None, help="目标最新交易日，如 2026-09-21")
    ap.add_argument("--workers", type=int, default=14)
    a = ap.parse_args()

    c = T._load()
    codes = list(c.keys())
    dist = {}
    for code in codes:
        b = c[code]
        d = b[-1]["date"] if b else "EMPTY"
        dist[d] = dist.get(d, 0) + 1
    top = sorted(dist.items(), key=lambda x: -x[1])[:5]
    print("缓存 %d 只｜最新日分布 Top5: %s" % (len(codes), top))
    if a.check:
        return

    # 刷新域 = 全集（含从未入缓存的漏网码），不只是已缓存代码
    codes = _universe(c)
    if a.end:
        stale = [k for k in codes
                 if k not in c or not c[k] or c[k][-1]["date"] < a.end]
    else:
        mx = max(d for d in dist if d != "EMPTY")
        stale = [k for k in codes if k not in c or not c[k] or c[k][-1]["date"] < mx]
    print("待刷新（落后于目标日）：%d 只" % len(stale))
    if not stale:
        print("全部已到目标日，无需刷新。")
        return

    done = ok = fail = 0
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        futs = {ex.submit(fetch_fresh, k): k for k in stale}
        for f in as_completed(futs):
            code = futs[f]
            bars = f.result()
            done += 1
            if bars:
                c[code] = bars
                ok += 1
            else:
                fail += 1
            if done % 400 == 0:
                T.save_cache()
                print("  进度 %d/%d（成功 %d 失败 %d）…" % (done, len(stale), ok, fail))
    T.save_cache()
    c2 = T._load()
    hit = sum(1 for k in stale if c2.get(k) and (not a.end or c2[k][-1]["date"] >= a.end))
    print("完成：刷新成功 %d / 失败 %d｜达到目标日 %d/%d" % (ok, fail, hit, len(stale)))


if __name__ == "__main__":
    main()
