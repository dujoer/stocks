# -*- coding: utf-8 -*-
"""补齐各池子每日所需的「行情 / K线」中间文件（腾讯离线源，MCP 不可用时的替代通道）。

为什么需要它
------------
`daily_all` 的第 ③④⑧⑩ 步在 SOP 里都要求「经 MCP 实拉 data_quote / data_kline」：
  · ③④ 大宗 / 高管增减持 → `quotes/{block,exec}_{DATE}.json`（补涨跌幅）
  · ⑧ 做T池            → `tplus/quotes_{DATE}.json` + `tplus/kline_{DATE}.json`
  · ⑦ 精选池            → `picks/quotes_{DATE}.json`
  · ① 底座口径校验        → `quotes/{DATE}.json`（全市场快照）
MCP 握手失败时这些文件缺失 → 对应步骤直接退出 1（做T池）/ 门禁报「数据源缺失」。
本脚本用腾讯 qt 快照 + 本地日K（`_txk`）补齐，**字段口径与历史 MCP 落盘完全一致**，
不改变任何字段语义、不做任何推算（chg_20d 走 `_tx_fetch.chg_n`；成交额走 `_tx_fetch.vol_unit`）。

用法：
    python quant/_gen_pool_quotes.py --date 2026-10-09              # 默认 all
    python quant/_gen_pool_quotes.py --date 2026-10-09 --what tplus
"""
from __future__ import annotations
import argparse, json, os, re, sys

Q = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, Q)
import _tx_fetch as T


def load(p, default=None):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return {} if default is None else default


def dump(obj, p):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    json.dump(obj, open(p, "w", encoding="utf-8"), ensure_ascii=False)


def codes_of(stocks, day_field, day=None):
    out = set()
    for s in stocks:
        c = s.get("code")
        if not c:
            continue
        if day and str(s.get(day_field) or "") != day:
            continue
        out.add(c)
    return sorted(out)


def codes_from_txt(p):
    if not os.path.exists(p):
        return []
    s = open(p, encoding="utf-8").read().strip()
    return sorted({c.strip() for c in re.split(r"[,\s]+", s) if c.strip()})


def fetch_map(codes):
    got, B = {}, 80
    for i in range(0, len(codes), B):
        try:
            got.update(T.fetch_qt(codes[i:i + B]) or {})
        except Exception as ex:
            print("  ⚠ 批次失败：%s" % str(ex)[:70])
    return got


# ── ③④ 大宗 / 高管增减持 ────────────────────────────────────────────
def gen_block_exec(date):
    DS = date.replace("-", "")
    bp = os.path.join(Q, "block_chg", "_raw_em_%s.json" % date)
    if not os.path.exists(bp):
        bp = os.path.join(Q, "block_chg", "_raw_tool_%s.json" % date)
    bst = (load(bp).get("data") or {}).get("evt_block_past_30", {}).get("stocks") or []
    bcodes = codes_of(bst, "TradeDay", DS)
    print("  block 源 %s 当日 %d 只" % (os.path.basename(bp) if os.path.exists(bp) else "-", len(bcodes)))
    if bcodes:
        got = fetch_map(bcodes)
        slim = {c: {"name": v.get("name"), "change_percent": v.get("change_percent"),
                    "turnover_rate": v.get("turnover_rate"), "price": v.get("last")}
                for c, v in got.items()}
        dump({"date": date, "data": slim}, os.path.join(Q, "quotes", "block_%s.json" % date))
        print("  block -> quotes/block_%s.json  %d/%d 只" % (date, len(slim), len(bcodes)))

    ep = os.path.join(Q, "exec_chg", "_raw_em_%s.json" % date)
    if not os.path.exists(ep):
        ep = os.path.join(Q, "exec_chg", "_raw_tool_%s.json" % date)
    est = (load(ep).get("data") or {}).get("evt_manager_sharechg_past_30", {}).get("stocks") or []
    # 页面按披露日分组渲染，但**全部记录都要涨跌幅** → 取全部 code（不按当日筛）
    ecodes = codes_of(est, "DeclareDate", None)
    print("  exec  源 %s %d 只" % (os.path.basename(ep) if os.path.exists(ep) else "-", len(ecodes)))
    if ecodes:
        got = fetch_map(ecodes)
        slim = {c: {"name": v.get("name"), "change_percent": v.get("change_percent"),
                    "turnover_rate": v.get("turnover_rate"), "price": v.get("last")}
                for c, v in got.items()}
        dump({"date": date, "data": slim}, os.path.join(Q, "quotes", "exec_%s.json" % date))
        print("  exec  -> quotes/exec_%s.json   %d/%d 只" % (date, len(slim), len(ecodes)))


# ── ⑧ 做T池 ─────────────────────────────────────────────────────────
def gen_tplus(date):
    import _txk
    codes = codes_from_txt(os.path.join(Q, "tplus", "codes_%s.txt" % date))
    if not codes:
        u = load(os.path.join(Q, "tplus", "universe_%s.json" % date), [])
        codes = sorted({x.get("code") for x in u if x.get("code")})
    print("  tplus codes %d 只" % len(codes))
    got = fetch_map(codes)
    txk = _txk.load()
    qout = {}
    for c, v in got.items():
        d = {k: v.get(k) for k in ("name", "last", "change_percent", "turnover_rate",
                                   "volume_ratio", "pe_ratio", "pb_ratio",
                                   "circulating_market_cap", "total_market_cap",
                                   "high_52week", "low_52week")}
        ch = T.chg_n(txk.get(c) or [], 20)
        if ch is not None:
            d["chg_20d"] = ch
        qout[c] = d
    dump(qout, os.path.join(Q, "tplus", "quotes_%s.json" % date))
    print("  tplus -> quotes_%s.json  %d 只" % (date, len(qout)))

    kout = {}
    for c in codes:
        bars = txk.get(c) or []
        if not bars:
            continue
        rows = []
        for b in reversed(bars[-60:]):                      # 与历史一致：倒序（最新在前）
            vol = b.get("volume") or 0
            last = b.get("last")
            rows.append({"date": b.get("date"), "open": b.get("open"), "last": last,
                         "high": b.get("high"), "low": b.get("low"), "volume": vol,
                         "amount": round(vol * T.vol_unit(c) * (last or 0), 2),
                         "exchange": ""})
        if rows:
            kout[c] = rows
    dump(kout, os.path.join(Q, "tplus", "kline_%s.json" % date))
    print("  tplus -> kline_%s.json   %d 只（每只 ≤60 根）" % (date, len(kout)))


# ── ⑦ 精选池 ────────────────────────────────────────────────────────
def gen_picks(date):
    codes = codes_from_txt(os.path.join(Q, "picks", "_codes_%s.txt" % date))
    print("  picks codes %d 只" % len(codes))
    if not codes:
        return
    got = fetch_map(codes)
    out = {c: {"name": v.get("name"), "price": v.get("last"),
               "change_percent": v.get("change_percent")} for c, v in got.items()}
    dump(out, os.path.join(Q, "picks", "quotes_%s.json" % date))
    print("  picks -> quotes_%s.json  %d/%d 只" % (date, len(out), len(codes)))


# ── ① 全市场快照（从统一底座导出） ──────────────────────────────────
def _norm_quote(code, v):
    """★ 口径归一：底座 quotes 走腾讯 qt（字段 last/11 项），历史快照走 MCP data_quote
    （字段 price/36 项）。10-08 起这里只导出腾讯口径 → 读 `q['price']` 的脚本 KeyError。
    统一在此补齐 price/code/symbol/market_name 等同义键，读端无需区分来源。"""
    if not isinstance(v, dict):
        return v
    if "price" not in v and v.get("last") is not None:
        v = dict(v)
        v["price"] = v["last"]
    v.setdefault("code", code)
    v.setdefault("symbol", code)
    pre = code[:2]
    v.setdefault("market_name", {"sh": "上海", "sz": "深圳", "bj": "北交所"}.get(pre, ""))
    return v


def gen_market(date):
    hub = load(os.path.join(Q, "hub", "%s.json" % date.replace("-", "")))
    q = ((hub.get("dims") or {}).get("quotes") or {}).get("data") or {}
    if not q:
        print("  market 跳过：hub 无 quotes（先跑 _datahub.py）")
        return
    q = {c: _norm_quote(c, v) for c, v in q.items()}
    dump({"ok": True, "data": q}, os.path.join(Q, "quotes", "%s.json" % date))
    print("  market -> quotes/%s.json  %d 只（已补 price 同义键）" % (date, len(q)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True, help="交易日 YYYY-MM-DD")
    ap.add_argument("--what", default="all",
                    choices=["all", "block", "tplus", "picks", "market"])
    a = ap.parse_args()
    print("=== 补池行情 %s ===" % a.date)
    if a.what in ("all", "block"):
        gen_block_exec(a.date)
    if a.what in ("all", "market"):
        gen_market(a.date)
    if a.what in ("all", "picks"):
        gen_picks(a.date)
    if a.what in ("all", "tplus"):
        gen_tplus(a.date)
    print("完成。")


if __name__ == "__main__":
    main()
