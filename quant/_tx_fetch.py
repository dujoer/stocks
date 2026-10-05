# -*- coding: utf-8 -*-
"""离线行情获取（腾讯公开接口，无需凭据）。

- fetch_kline(code, n): 腾讯前复权日K，返回升序 [{date,open,last,high,low,volume}]
- fetch_qt(codes):      腾讯实时快照（周末返回最近交易日 09-18 收盘）
                        -> {code: name/last/change_percent/turnover_rate/volume_ratio/
                                pe_ratio/pb_ratio/circulating_market_cap(亿)/high_52week/low_52week}
- 全量缓存到 quant/_txk_cache.json，避免重复联网。

单位说明（2026-09-21 修正 —— 原文档「一律为手」是错的）：
  腾讯 fqkline 的 volume **单位不统一**，用 qt 快照的成交额字段交叉标定（240 只抽样、
  各板块 unit 中位数 1.0 / 99.9 / 100.0，零异常样本）实测：
    - 科创板 sh688*            → 已是「股」，换算系数 1
    - 沪主板 sh60* / 深主板 sz00* / 创业板 sz30* / 北交所 bj*  → 单位「手」，系数 100
  **算成交额必须用 volume * vol_unit(code) * 均价**，否则科创板与其余板块会差 100 倍。
  ⚠️ 历史上 `pick_score.py` / `_pick_lab.py` / `scan_strong.py` / `fetch_tplus_offline.py`
  曾直接 `volume * 100` 或 `volume * 均价`，导致：① 主板成交额被低估 100 倍（流动性过滤误杀）；
  ② 科创板成交额被高估 100 倍（强势扫描虚高）。已统一改为调 `vol_unit()`。
  本模块仍**原样返回** volume（不改缓存），由调用方按板块换算（前复权价）。
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
# ★ 当期数据日（可选）。设置后 `fetch_kline` 会对缓存做**新鲜度校验**：
#   缓存里末根 K 线日期 < ASOF 时视为陈旧 → 自动重新联网补拉，而不是把旧价当当日价用。
#   历史坑（2026-10-05 审计发现）：原逻辑命中条件只有 `len(c[code]) >= need`，
#   完全不看末根日期 —— 缓存里 8 只（三峡新材/信达证券/建兴院/0028 等）末根停在
#   09-11~09-29，却会被下游当成 09-30 的价算指标，属「旧数据冒充当日」的静默通道。
_ASOF = None


def set_asof(date):
    """设置当期数据日（'YYYY-MM-DD' 或 'YYYYMMDD'）。日更第一步 `_datahub.py` 会调用，
    使整条链共享同一个新鲜度基准。不设置 = 关闭新鲜度校验（保持旧行为）。"""
    global _ASOF
    if not date:
        _ASOF = None
        return
    s = str(date).replace("-", "")
    _ASOF = "%s-%s-%s" % (s[:4], s[4:6], s[6:8]) if len(s) == 8 else str(date)


def get_asof():
    return _ASOF


def _norm_date(d):
    s = str(d or "").replace("-", "")
    return "%s-%s-%s" % (s[:4], s[4:6], s[6:8]) if len(s) == 8 else str(d)


def last_date(code):
    """缓存里该代码的末根 K 线日期（无则 None）。"""
    bars = _load().get(code) or []
    return bars[-1]["date"] if bars else None


def stale_codes(asof=None, only_prefixes=None):
    """末根 K 线日期 < asof 的代码（诊断用，不改数据）。

    only_prefixes：只统计这些前缀（默认全部）。返回 [(code, last_date), ...]。
    """
    a = _norm_date(asof or _ASOF)
    if not a:
        return []
    out = []
    for code, bars in _load().items():
        if not bars:
            continue
        if only_prefixes and not code.startswith(tuple(only_prefixes)):
            continue
        d = bars[-1].get("date")
        if d and _norm_date(d) < a:
            out.append((code, d))
    return sorted(out)


# A 股股票代码：沪 sh60/sh688、深 sz00/sz30、北 bj。排除可转债(sh11x/sz12x)、基金(sh51x/sz15x)等。
_STOCK_RE = None


def is_stock(code):
    """是否 A 股股票代码（用于把缓存里混入的可转债/基金剔出去）。"""
    global _STOCK_RE
    if _STOCK_RE is None:
        import re as _re
        _STOCK_RE = _re.compile(r"^(sh6\d{5}|sz[03]\d{5}|bj[489]\d{5})$")
    return bool(_STOCK_RE.match(code or ""))


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


def vol_unit(code):
    """腾讯 fqkline 的 volume 单位换算系数 —— 把各板块统一成「股」。

    实测（2026-09-21，qt 成交额交叉标定，240 只抽样零异常）：
      科创板 sh688* 原样为「股」(系数 1)；其余（sh60/sz00/sz30/bj）为「手」(系数 100)。
    成交额 = volume * vol_unit(code) * 均价。
    """
    return 1.0 if code.startswith("sh688") else 100.0


def amount(bars, code, i=None, win=None):
    """按统一口径估算成交额（元）。i 为末根下标（默认最后一根）；win 给定时取窗口均值。"""
    if not bars:
        return None
    if i is None:
        i = len(bars) - 1
    u = vol_unit(code)
    rng = range(i - win + 1, i + 1) if win else [i]
    vals = [bars[k]["volume"] * u * bars[k]["last"] for k in rng if 0 <= k < len(bars)]
    if not vals:
        return None
    return sum(vals) / len(vals) if win else sum(vals)


def fetch_kline(code, n=250, retries=3, asof=None):
    """腾讯前复权日K，升序 [{date,open,last,high,low,volume}]。失败返回 []。

    ★ 新鲜度（2026-10-05 加）：命中缓存的条件除「条数够」外，还要求末根 K 线日期
      ≥ asof（默认取全局 `set_asof` 的值）。陈旧 → 视为未命中，重新联网补拉。
      拉回来仍陈旧（真停牌/退市）则**照样返回**（与旧行为一致，避免下游突然拿不到数据），
      由 `stale_codes()` 暴露给门禁。未设 asof = 关闭校验，保持旧行为。
    """
    c = _load()
    a = _norm_date(asof or _ASOF)
    need = max(30, n - 8)
    if code in c and len(c[code]) >= need:
        if not a or _norm_date(c[code][-1].get("date")) >= a:
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
    # 拉取失败：若缓存里有（陈旧）数据，仍返回 —— 但调用方可用 stale_codes() 识别
    return c.get(code, [])


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
