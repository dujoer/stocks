# -*- coding: utf-8 -*-
"""底部反转观察池 · 主力资金流（1/5/10/20 日净流入）。

两条通道，互为兜底：
  · MCP  westock `data_fund_flow` —— 与站内其它池（精选池出池门槛）**同口径**，优先。
  · 离线 新浪 `MoneyFlow.ssl_qsfx_zjlrqs`（每股一次请求，25 个交易日）—— 不受 MCP 限频影响。
    口径说明：新浪「主力」= 自家大单+超大单阈值，与 westock 的 Jumbo+Block 存在**位数相同的
    口径差**（阈值不同，非错误）。页面会标注当日实际使用的来源，避免跨日误读。

产出：quant/_rev_flow_raw_{dc}.json
  {"data_date": "...", "src": "mcp|sina|mixed", "data": {code: {mf1,mf5,mf10,mf20,rank,circ_rate,src}}}

用法：
  python quant/fetch_rev_flow.py --date 2026-09-18                # auto：先 MCP 再新浪补缺
  python quant/fetch_rev_flow.py --date 2026-09-18 --src sina     # 纯离线
  python quant/fetch_rev_flow.py --date 2026-09-18 --limit 30
"""
import os
import sys
import json
import time
import argparse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

ROOT = os.path.dirname(HERE)
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
SINA = ("https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/"
        "MoneyFlow.ssl_qsfx_zjlrqs")


def dc_of(d):
    return str(d).replace("-", "")


def cand_codes(date, limit=0):
    p = os.path.join(HERE, "watchlist_scan_%s.json" % dc_of(date))
    if not os.path.exists(p):
        raise SystemExit("缺少 %s（先跑 rev_pool.py run）" % p)
    j = json.load(open(p, encoding="utf-8"))
    out = []
    for c in j.get("candidates") or []:
        code = c.get("_full") or c.get("code")
        if not code:
            continue
        out.append(code if code[:2] in ("sh", "sz", "bj") else "sz" + code)
    return (out[:limit] if limit else out)


# ---------------- 新浪离线 ----------------
def _sina_rows(code, num=25, retries=2):
    """拉某只的日级资金流（新→旧）。失败返回 None。"""
    u = "%s?page=1&num=%d&sort=opendate&asc=0&daima=%s" % (SINA, num, code)
    for i in range(retries):
        try:
            req = urllib.request.Request(u, headers={
                "User-Agent": UA, "Referer": "https://finance.sina.com.cn/"})
            raw = urllib.request.urlopen(req, timeout=15).read().decode("utf-8", "ignore")
            d = json.loads(raw)
            return d if isinstance(d, list) else None
        except Exception:
            time.sleep(0.4 * (i + 1))
    return None


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def sina_flow(code, num=25):
    """新浪 → {date, mf1,mf5,mf10,mf20, rank=None, circ_rate=None, src:'sina'}。"""
    rows = _sina_rows(code, num)
    if not rows:
        return None
    vals = [_f(r.get("netamount")) for r in rows]      # 新浪「主力净流入」日值
    if not vals:
        return None

    def s(n):
        return sum(vals[:n]) if len(vals) >= n else None

    return {"date": rows[0].get("opendate"), "src": "sina",
            "mf1": (vals[0] if vals else None), "mf5": s(5), "mf10": s(10), "mf20": s(20),
            "rank": None, "circ_rate": None,
            "close": _f(rows[0].get("trade")) or None}


def sina_batch(codes, workers=12):
    out = {}
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for c, v in zip(codes, ex.map(sina_flow, codes)):
            if v:
                out[c] = v
    return out


# ---------------- MCP ----------------
def mcp_flow(codes, date, batch=50, gap=6.0, quiet=False):
    try:
        import _wsboot as W
        W.ensure()
    except Exception as e:
        if not quiet:
            print("  [mcp] 不可用：%s" % e)
        return {}
    out = {}
    nb = (len(codes) + batch - 1) // batch
    for i in range(0, len(codes), batch):
        grp = codes[i:i + batch]
        r = W.call("data_fund_flow", {"codes": ",".join(grp), "date": date})
        d = W.unwrap(r) if hasattr(W, "unwrap") else r
        data = (d or {}).get("data") if isinstance(d, dict) else None
        if not data:
            if not quiet:
                print("  [mcp] 批 %d/%d 失败：%s"
                      % (i // batch + 1, nb,
                         str((r.get("error") if isinstance(r, dict) else r))[:80]))
        else:
            for k, v in data.items():
                rec = (v.get("data") or [None])[0] if isinstance(v, dict) else None
                if not isinstance(rec, dict):
                    continue
                out[k] = {"date": rec.get("EndDate"), "src": "mcp",
                          "mf1": _num(rec.get("MainNetFlow")),
                          "mf5": _num(rec.get("MainNetFlow5D")),
                          "mf10": _num(rec.get("MainNetFlow10D")),
                          "mf20": _num(rec.get("MainNetFlow20D")),
                          "rank": _num(rec.get("MainInflowRank")),
                          "circ_rate": _num(rec.get("MainInflowCircRate"))}
            if not quiet:
                print("  [mcp] 批 %d/%d 成功 +%d（累计 %d）"
                      % (i // batch + 1, nb, len(data), len(out)))
        if i + batch < len(codes):
            time.sleep(gap)
    return out


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="2026-09-18")
    ap.add_argument("--src", choices=("auto", "mcp", "sina"), default="auto")
    ap.add_argument("--batch", type=int, default=50)
    ap.add_argument("--gap", type=float, default=6.0)
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--no-reuse", action="store_true", help="忽略已有结果，整批重拉")
    a = ap.parse_args()

    codes = cand_codes(a.date, a.limit)
    out_path = os.path.join(HERE, "_rev_flow_raw_%s.json" % dc_of(a.date))

    got = {}
    if not a.no_reuse and os.path.exists(out_path):
        try:
            got = json.load(open(out_path, encoding="utf-8")).get("data") or {}
            print("[rev_flow] 复用已有 %d 只" % len(got))
        except Exception:
            got = {}

    todo = [c for c in codes if c not in got]
    print("[rev_flow] %s 目标 %d 只，待拉 %d 只（模式 %s）" % (a.date, len(codes), len(todo), a.src))

    if todo and a.src in ("auto", "mcp"):
        m = mcp_flow(todo, a.date, batch=a.batch, gap=a.gap)
        got.update(m)
        todo = [c for c in todo if c not in got]

    if todo and a.src in ("auto", "sina"):
        print("  改用新浪离线补 %d 只…" % len(todo))
        s = sina_batch(todo, workers=a.workers)
        got.update(s)
        print("  新浪命中 %d / %d" % (len(s), len(todo)))

    srcs = {v.get("src") for v in got.values()}
    json.dump({"data_date": a.date, "src": ("mixed" if len(srcs) > 1 else (srcs or {"?"}).pop()),
               "data": got, "codes": codes},
              open(out_path, "w", encoding="utf-8"), ensure_ascii=False)
    miss = [c for c in codes if c not in got]
    print("[rev_flow] → %s｜有数据 %d/%d（源 %s）｜缺 %d"
          % (out_path, len(got), len(codes), ",".join(sorted(srcs)) or "—", len(miss)))


if __name__ == "__main__":
    main()
