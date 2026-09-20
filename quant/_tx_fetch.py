# -*- coding: utf-8 -*-
"""离线行情获取（腾讯公开接口，无需凭据）。

- fetch_kline(code, n): 腾讯前复权日K，返回升序 [{date,open,last,high,low,volume}]
- fetch_qt(codes):      腾讯实时快照（周末返回最近交易日 09-18 收盘）
                        -> {code: name/last/change_percent/turnover_rate/volume_ratio/
                                pe_ratio/pb_ratio/circulating_market_cap(亿)/high_52week/low_52week}
- 全量缓存到 quant/_txk_cache.json，避免重复联网。

单位说明：
  fqkline 的 volume 单位为「手」(100 股)；本模块原样返回，amount 需调用方按
  volume*100*均价 估算（前复权价）。
"""
from __future__ import annotations
import os, json, time, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "quant", "_txk_cache.json")
TX_KLINE = "https://proxy.finance.qq.com/ifzqgtimg/appstock/app/fqkline/get"
TX_QT = "https://qt.gtimg.cn/q="
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

_cache = None


def _load():
    global _cache
    if _cache is None:
        if os.path.exists(CACHE):
            try:
                _cache = json.load(open(CACHE, encoding="utf-8"))
            except Exception:
                _cache = {}
        else:
            _cache = {}
    return _cache


def save_cache():
    try:
        json.dump(_load(), open(CACHE, "w", encoding="utf-8"), ensure_ascii=False)
    except Exception:
        pass


def _num(x):
    try:
        return float(x)
    except Exception:
        return None


def fetch_kline(code, n=250, retries=3):
    """腾讯前复权日K，升序 [{date,open,last,high,low,volume}]。失败返回 []。"""
    c = _load()
    if code in c and len(c[code]) >= max(30, n - 8):
        return c[code]
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
            out = []
            for it in ks:
                out.append({"date": it[0], "open": float(it[1]),
                            "last": float(it[2]), "high": float(it[3]),
                            "low": float(it[4]), "volume": float(it[5])})
            if out:
                c[code] = out
                return out
        except Exception:
            time.sleep(0.5 * (i + 1))
    return []


def fetch_qt(codes, batch=80):
    """腾讯实时快照。返回 {code(带前缀): {...}}。"""
    out = {}
    for i in range(0, len(codes), batch):
        grp = codes[i:i + batch]
        url = TX_QT + ",".join(grp)
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": UA, "Referer": "https://gu.qq.com/"})
            raw = urllib.request.urlopen(req, timeout=20).read().decode("gbk")
        except Exception:
            time.sleep(0.6)
            continue
        for line in raw.strip().split("\n"):
            if not line.strip() or "=" not in line or '"' not in line:
                continue
            s = line.split('"')[1]
            if not s:
                continue
            f = s.split("~")
            if len(f) <= 49:
                continue
            pref = line.split("=")[0].replace("v_", "").strip()
            out[pref] = {
                "name": f[1],
                "last": _num(f[3]),
                "change_percent": _num(f[32]),
                "turnover_rate": _num(f[38]),
                "volume_ratio": _num(f[49]),
                "pe_ratio": _num(f[39]),
                "pb_ratio": _num(f[46]),
                "circulating_market_cap": _num(f[44]),
                "total_market_cap": _num(f[45]),        # 总市值(亿)，2026-09-20 补
                "high_52week": _num(f[47]),
                "low_52week": _num(f[48]),
            }
    return out


def chg_n(kasc, n):
    """最近 n 个交易日累计涨跌幅(%)；不足返回 None。"""
    if not kasc or len(kasc) < n + 1:
        return None
    c0 = kasc[-1]["last"]
    cn = kasc[-(n + 1)]["last"]
    return (c0 - cn) / cn * 100 if cn else None


if __name__ == "__main__":
    import sys
    cs = sys.argv[1:] or ["sh600519"]
    for c in cs:
        k = fetch_kline(c, 30)
        print(c, "kline", len(k), k[-1] if k else None)
    print(fetch_qt(cs))
