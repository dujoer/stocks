#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""东财 datacenter-web 批量抓取个股融资融券历史（离线通道，替代 westock data_fund_margin）。

用途：增仓精选的 1/3/5 日多空增仓模块需要连续日频序列（此前 picks/margin_* 只有 5 个稀疏快照）。
产物：margin_em/{code}.json = [{date, rzye, rzjme, rzjme3d, rzjme5d, rqjmg, rqye, ...}]
口径：融资融券 T+1 公布 —— T 日决策只能用 DATE < T 的最近一期（防未来函数）。

用法：
  python3 _fetch_margin_em.py                 # 默认 = 20 日事件域（block/exec/lhb 唯一代码）
  python3 _fetch_margin_em.py sh600519 sz000001
  python3 _fetch_margin_em.py --workers 6
"""
import os
import re
import sys
import json
import glob
import time
import urllib.request
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "margin_em")

UA = {"User-Agent": "Mozilla/5.0", "Referer": "https://data.eastmoney.com/"}


def event_codes(days=20):
    """近 N 个交易日内触发过日频事件的唯一代码（与 _accum_lab 同源）。"""
    import datetime
    codes = set()
    cut = (datetime.date.today() - datetime.timedelta(days=40)).isoformat()
    # 注意：block/exec 落盘的 code 已带 sh/sz 前缀（如 sh600519）；lhb_detail 顶层 {ok, data:{code:...}}
    for f in glob.glob(os.path.join(HERE, "block_chg", "2026-*.json")) + \
             glob.glob(os.path.join(HERE, "block_chg", "2025-*.json")):
        base = os.path.basename(f)
        if not re.match(r"^\d{4}-\d{2}-\d{2}\.json$", base) or base[:10] < cut:
            continue
        try:
            d = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        rows = d.get("rows") if isinstance(d, dict) else d
        if isinstance(rows, list):
            for r in rows:
                c = str((r or {}).get("code") or "")
                if re.match(r"^s[hz]\d{6}$", c):
                    codes.add(c)
    for f in glob.glob(os.path.join(HERE, "exec_chg", "2026-*.json")) + \
             glob.glob(os.path.join(HERE, "exec_chg", "2025-*.json")):
        base = os.path.basename(f)
        if base[:10] < cut:
            continue
        try:
            d = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        for r in (d.get("records") or []):
            c = str((r or {}).get("code") or "")
            if re.match(r"^s[hz]\d{6}$", c):
                codes.add(c)
    for f in glob.glob(os.path.join(HERE, "lhb_detail", "2026-*.json")) + \
             glob.glob(os.path.join(HERE, "lhb_detail", "2025-*.json")):
        base = os.path.basename(f)
        if base[:10] < cut:
            continue
        try:
            d = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        if isinstance(d, dict) and isinstance(d.get("data"), dict):
            codes |= {c for c in d["data"] if re.match(r"^s[hz]\d{6}$", c)}
    return sorted(codes)


def fetch_one(code, pagesize=30, retries=2):
    scode = code[2:]
    url = ("https://datacenter-web.eastmoney.com/api/data/v1/get?"
           + urllib.parse.urlencode({
               "reportName": "RPTA_WEB_RZRQ_GGMX", "columns": "ALL",
               "source": "WEB", "client": "WEB",
               "filter": f'(scode="{scode}")',
               "sortColumns": "DATE", "sortTypes": "-1",
               "pageSize": pagesize, "pageNumber": 1}))
    for k in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=UA)
            d = json.load(urllib.request.urlopen(req, timeout=15))
            rows = (d.get("result") or {}).get("data") or []
            out = []
            for r in rows:
                out.append({
                    "date": str(r.get("DATE") or "")[:10],
                    "rzye": r.get("RZYE"),            # 融资余额
                    "rzjme": r.get("RZJME"),          # 当日融资净买入（元）
                    "rzjme3d": r.get("RZJME3D"),      # 3日融资净买入
                    "rzjme5d": r.get("RZJME5D"),      # 5日融资净买入
                    "rqjmg": r.get("RQJMG"),          # 融券净卖出（股）
                    "rqye": r.get("RQYE"),            # 融券余额
                    "rzrqye": r.get("RZRQYE"),        # 融资融券余额
                })
            return code, out
        except Exception:
            if k < retries:
                time.sleep(1.0 + k)
            else:
                return code, None


def main():
    argv = sys.argv[1:]
    codes_in = []
    workers = 6
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--workers":
            workers = int(argv[i + 1])
            i += 2
        elif a.startswith("--workers="):
            workers = int(a.split("=", 1)[1])
            i += 1
        elif a.startswith("--"):
            i += 1
        else:
            codes_in.append(a)
            i += 1
    codes = codes_in if codes_in else event_codes()
    os.makedirs(OUT, exist_ok=True)
    print(f"[margin_em] 待抓取 {len(codes)} 只，workers={workers}")
    ok = fail = 0
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(fetch_one, c): c for c in codes}
        for i, fu in enumerate(as_completed(futs), 1):
            code, rows = fu.result()
            if rows is None:
                fail += 1
            else:
                json.dump(rows, open(os.path.join(OUT, code + ".json"), "w", encoding="utf-8"),
                          ensure_ascii=False)
                ok += 1
            if i % 100 == 0:
                print(f"  进度 {i}/{len(codes)} ok={ok} fail={fail} 耗时 {time.time()-t0:.0f}s")
    print(f"[margin_em] 完成 ok={ok} fail={fail} 耗时 {time.time()-t0:.0f}s → {OUT}")


if __name__ == "__main__":
    main()
