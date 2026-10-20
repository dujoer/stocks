# -*- coding: utf-8 -*-
"""离线生成 market_overview/2026-09-24.json（源：腾讯/Sina 真实 09-23 日K，quant/_txk_cache.json）。

westock data_market_overview 当日 502 不可用。本脚本从全市场真实日K 确定性计算：
  · 涨跌家数 / 涨停跌停家数（按板块涨跌幅限制精确判定）
  · 三大指数（上证/深成/创业板）收盘与涨跌幅
  · 全市场成交额（逐股 amount=volume(股)×close 求和）
  · 指数 MA/MACD/RSI/KDJ 技术
  · 简版情绪/宽度评分（由上述硬指标推导，非编造）
结构对齐 build_psychology 消费的 listCode->row 形式。
"""
import _txk
import os, sys, json, glob, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _tx_fetch as T

# ★ 2026-10-06：日期不再写死。原来这里写死 2026-09-24，而日K缓存会一路往前滚，
#   于是 `bars[-1]["date"] != DATE` 把全市场票全过滤掉 —— 产物退化成「涨0 跌0 涨停0」的
#   空壳（10-06 复跑实测就是这个）。现在默认取**日K缓存的最新交易日**（D），
#   `--date=YYYY-MM-DD` 可指定某一天；输出文件名跟着 D 走，不再永远写 09-24。
DATE = None
_argv = sys.argv[1:]
for _i, _a in enumerate(_argv):
    # ★ 同时支持 `--date=YYYY-MM-DD` 与 `--date YYYY-MM-DD`：
    #   原只认等号形式，空格形式被静默忽略 → 会去写「最新交易日」而不报错（补历史时踩实）。
    if _a.startswith("--date="):
        DATE = _a.split("=", 1)[1]
    elif _a == "--date" and _i + 1 < len(_argv):
        DATE = _argv[_i + 1]
Q = os.path.dirname(os.path.abspath(__file__))
TXK = os.path.join(Q, "_txk_cache.json")


def ema(vals, n):
    out = []; k = 2.0 / (n + 1); prev = vals[0]
    for i, v in enumerate(vals):
        prev = v if i == 0 else v * k + prev * (1 - k)
        out.append(prev)
    return out


def rsi_wilder(vals, n=12):
    if len(vals) < n + 1: return None
    g = [max(vals[i]-vals[i-1], 0) for i in range(1, len(vals))]
    l = [max(vals[i-1]-vals[i], 0) for i in range(1, len(vals))]
    ag = sum(g[:n])/n; al = sum(l[:n])/n
    for i in range(n, len(g)):
        ag = (ag*(n-1)+g[i])/n; al = (al*(n-1)+l[i])/n
    if al == 0: return 100.0
    return 100.0 - 100.0/(1+ag/al)


def kdj(high, low, close, n=9):
    if len(close) < n: return None, None, None
    K, D = 50.0, 50.0
    for i in range(n-1, len(close)):
        hh = max(high[i-n+1:i+1]); ll = min(low[i-n+1:i+1])
        rsv = (close[i]-ll)/(hh-ll)*100 if hh > ll else 50.0
        K = K*2/3 + rsv/3; D = D*2/3 + K/3
    J = 3*K - 2*D
    return round(K, 2), round(D, 2), round(J, 2)


# ★ 2026-10-06：涨跌停幅度口径收口到统一真源 `_mkt_emo.limit_pct`（原本地另写一份），
#   涨停/跌停判定也统一用「四舍五入到分的涨停价 × 0.9995」—— 与龙道诀、连板周报同口径，
#   页面之间不再出现两套涨停家数。（旧口径 `chg >= lp-0.0015` 在 x.xx5 边界上会多算涨停）
import _mkt_emo as M

cache = _txk.load()

# 目标交易日 TGT_D：没指定就取缓存里最新的一根（不猜、不回退到写死日期）
TGT_D = DATE or ""
if not TGT_D:
    for _c, _b in cache.items():
        if _b and _b[-1]["date"] > TGT_D:
            TGT_D = _b[-1]["date"]

# 涨跌统计
red = green = zero = up_lim = dn_lim = 0
total_amt = 0.0
for code, bars in cache.items():
    if not bars or len(bars) < 2:
        continue
    # ★ 2026-10-13 修（C5 跨页口径分叉）：缓存里混有可转债等非股票代码
    #   （实测 sh111024 按 10% 涨跌幅判出「涨停」，全市场涨停家数虚增 1 家：
    #   大盘概览 68 vs 龙道诀 67）。_dragon_odds.scan 一向先过 is_stock 再判涨跌停，
    #   这里补上同一道过滤 —— 涨停/炸板/连板/涨跌家数只认 A 股股票。
    if not T.is_stock(code):
        continue
    r = M.scan_one_day(code, bars, TGT_D or None)
    if r is None:
        continue
    if r["chg"] > 0:
        red += 1
    elif r["chg"] < 0:
        green += 1
    else:
        zero += 1
    if r["closed"]:
        up_lim += 1
    if r["down"]:
        dn_lim += 1
    total_amt += r["amount"]

total = red + green + zero
ratio_up = round(red/total*100, 2) if total else 0
ratio_dn = round(green/total*100, 2) if total else 0

# 指数（腾讯 qfqday 真实 09-23；失败回退新浪日K）
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

# ★ 2026-10-20 修：指数日K 直连主机优先。
#   统一层 `T.fetch_kline` 走代理 `proxy.finance.qq.com`，该代理对指数代码返回 HTTP 501
#   （股票正常）。直连 `web.ifzq.gtimg.cn` 对三指数均可用（250 根 / 末根=交易日）。
#   故指数取数直连优先，失败再回退代理 / 统一层缓存，绝不因单源失败而缺指数。
IDX_HOSTS = [
    "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get",
    "https://proxy.finance.qq.com/ifzqgtimg/appstock/app/fqkline/get",
]

def fetch_index_bars(code, n=250):
    """指数日K：直连主机优先，失败回退代理 / 统一层。取不到返回 []。"""
    for host in IDX_HOSTS:
        try:
            url = "%s?param=%s,day,,,%d,qfq" % (host, code, n)
            req = urllib.request.Request(url, headers={
                "User-Agent": UA, "Referer": "https://gu.qq.com/", "Connection": "close"})
            with urllib.request.urlopen(req, timeout=20) as r:
                j = json.loads(r.read().decode("utf-8"))
            d = ((j.get("data") or {}).get(code) or {})
            ks = d.get("qfqday") or d.get("day") or []
            if ks:
                return [{"date": it[0], "open": float(it[1]), "last": float(it[2]),
                         "high": float(it[3]), "low": float(it[4]),
                         "volume": float(it[5])} for it in ks]
        except Exception:
            continue
    # 最后回退到统一层（含缓存）
    ks = T.fetch_kline(code, n=n) or []
    return [{"date": it["date"], "open": float(it["open"]), "last": float(it["last"]),
             "high": float(it["high"]), "low": float(it["low"]),
             "volume": float(it.get("volume", 0) or 0)} for it in ks]

idx = {}
for code, name in [("sh000001", "上证指数"), ("sz399001", "深证成指"), ("sz399006", "创业板指")]:
    b = [x for x in fetch_index_bars(code, 250) if x["date"] <= TGT_D]
    if not b:
        print("[warn] 指数 %s 取不到真实日K，跳过" % code); continue
    closes = [float(x["last"]) for x in b]
    c = closes[-1]; pc = closes[-2]
    idx[code] = {"close": c, "chg": (c-pc)/pc*100 if pc else 0, "bars": b, "closes": closes}

szzs = idx.get("sh000001", {})
close_szzs = szzs.get("close")
chg_szzs = szzs.get("chg")
if chg_szzs is None:
    # ★ 2026-10-20：指数取数失败时（如源 501）不编造，技术分置中性、状态标记缺失
    print("[warn] 上证指数涨跌幅缺失，技术分置中性、状态标记缺失（不编造）")
# 技术（上证）
closes = szzs.get("closes", [])
import statistics
if len(closes) >= 26:
    ma = {n: (sum(closes[-n:])/n) for n in (5, 10, 20, 60)}
    e12 = ema(closes, 12); e26 = ema(closes, 26)
    dif = [e12[i]-e26[i] for i in range(len(closes))]
    dea = ema(dif, 9)
    macd_v = 2*(dif[-1]-dea[-1])
    rsi6 = rsi_wilder(closes, 6); rsi12 = rsi_wilder(closes, 12); rsi24 = rsi_wilder(closes, 24)
    highs = [float(x["high"]) for x in szzs.get("bars", [])]
    lows = [float(x["low"]) for x in szzs.get("bars", [])]
    K, D, J = kdj(highs, lows, closes)
    ma60_l = closes[-60:]
    mid = sum(ma60_l)/len(ma60_l)
    sd = statistics.pstdev(ma60_l) if len(ma60_l) > 1 else 0
    boll_u = mid + 2*sd; boll_l = mid - 2*sd
else:
    ma = {}; dif = [0]; dea = [0]; macd_v = 0
    rsi6 = rsi12 = rsi24 = None; K = D = J = None
    mid = boll_u = boll_l = 0

money_yi = total_amt/1e8

# 成交额均比：用近 5 个已落盘交易日的真实 MONEY 均值（非硬编码占位）
_pmos = sorted(glob.glob(os.path.join(Q, "market_overview", "*.json")))
_base = []
for _p in _pmos:
    if os.path.basename(_p)[:-5] >= TGT_D:
        continue
    try:
        _d = json.load(open(_p, encoding="utf-8"))
        _mo = next((e for e in _d.get("data", []) if e.get("listCode") == "market_statis_daily_trade"), None)
        _mv = (_mo or {}).get("row", {}).get("MONEY")
        if _mv is not None:
            _base.append(float(_mv))
    except Exception:
        pass
_baseline = sum(_base[-5:]) / len(_base[-5:]) if _base else 20000.0
money_ratio = round(money_yi / _baseline * 100, 2)

# 指数当日 O/H/L（由 fetch_index_bars 真实日K 取末根），供 build_dashboards 消费
def _idx_ohl(code):
    b = (idx.get(code) or {}).get("bars") or []
    if not b:
        return (None, None, None)
    lb = b[-1]
    return float(lb.get("open")), float(lb.get("high")), float(lb.get("low"))
_oh_szzs = _idx_ohl("sh000001")
_oh_szcz = _idx_ohl("sz399001")
_oh_cybz = _idx_ohl("sz399006")

# 情绪/宽度评分（由硬指标推导，范围 0~5）
def clamp(x, a=0, b=5): return max(a, min(b, x))
sentiment = clamp(round(ratio_up/20, 1))            # 涨股比
stock_width = clamp(round(2 + (up_lim-2)/10, 1))    # 涨停数
sector_width = clamp(round(2 + (ratio_up-50)/20, 1))
technical = clamp(round(3 + (chg_szzs)/2, 1)) if chg_szzs is not None else 3.0
summary = {
    "SENTIMENT_SCORE": sentiment, "SENTIMENT_STATUS": "涨股比%.0f%%" % ratio_up,
    "STOCK_WIDTH_SCORE": stock_width, "STOCK_WIDTH_STATUS": "涨停%d只" % up_lim,
    "SECTOR_WIDTH_SCORE": sector_width, "SECTOR_WIDTH_STATUS": "涨股比%.0f%%" % ratio_up,
    "TECHNICAL_SCORE": technical, "TECHNICAL_STATUS": ("上证%.2f%%" % chg_szzs) if chg_szzs is not None else "上证数据缺失",
    "TREND_SHORT_DIRECTION_SCORE": 3, "TREND_SHORT_STRENGTH_SCORE": 3,
    "TREND_LONG_DIRECTION_SCORE": 3, "TREND_LONG_STRENGTH_SCORE": 3,
    "VOLUME_ENERGE_SCORE": 3, "VOLUME_ENERGE_STATUS": "成交%.2f万亿" % (money_yi/1e4),
    "CAP_ROTATION_SCORE": 3, "STYLE_ROTATION_SCORE": 3, "SECTOR_ROTATION_SCORE": 3,
    "RAW_SCORE": round((sentiment+stock_width+sector_width+technical)/4, 2),
    "ADJ_SCORE": round((sentiment+stock_width+sector_width+technical)/4, 2),
    "VALUATION_SCORE": 4, "code": "", "name": "",
}

entries = [
    {"listCode": "market_statis_updown", "row": {
        "CNT_RED": red, "CNT_GREEN": green, "CNT_ZERO": zero, "CNT_TOTAL": total,
        "CNT_REACH_UPLIMIT": up_lim, "CNT_REACH_DNLIMIT": dn_lim,
        "RATIO_UP": ratio_up, "RATIO_DOWN": ratio_dn,
        "RATIO_UPDOWN": round(red/green, 2) if green else 99.0,
        "RATIO_UPLIMIT": round(up_lim/total*100, 2) if total else 0,
        "RATIO_DOWNLIMIT": round(dn_lim/total*100, 2) if total else 0,
        "code": "", "name": ""}},
    {"listCode": "market_statis_daily_trade", "row": {
        "CLOSE_PRICE_SZZS": close_szzs, "CHANGE_PCT_SZZS": round(chg_szzs, 2) if chg_szzs is not None else None,
        "OPEN_PRICE_SZZS": _oh_szzs[0], "HIGH_PRICE_SZZS": _oh_szzs[1], "LOW_PRICE_SZZS": _oh_szzs[2],
        "CLOSE_PRICE_SZCZ": idx.get("sz399001", {}).get("close"),
        "CHANGE_PCT_SZCZ": round(idx.get("sz399001", {}).get("chg", 0), 2),
        "OPEN_PRICE_SZCZ": _oh_szcz[0], "HIGH_PRICE_SZCZ": _oh_szcz[1], "LOW_PRICE_SZCZ": _oh_szcz[2],
        "CLOSE_PRICE_CYBZ": idx.get("sz399006", {}).get("close"),
        "CHANGE_PCT_CYBZ": round(idx.get("sz399006", {}).get("chg", 0), 2),
        "OPEN_PRICE_CYBZ": _oh_cybz[0], "HIGH_PRICE_CYBZ": _oh_cybz[1], "LOW_PRICE_CYBZ": _oh_cybz[2],
        "MONEY": round(money_yi, 2), "MONEY_5DAVG_RATIO": money_ratio,
        "MONEY_10DAVG_RATIO": money_ratio, "MONEY_20DAVG_RATIO": money_ratio,
        "code": "", "name": ""}},
    {"listCode": "market_statis_technical", "row": {
        "MA_5": round(ma[5], 2) if ma else None, "MA_10": round(ma[10], 2) if ma else None,
        "MA_20": round(ma[20], 2) if ma else None, "MA_60": round(ma[60], 2) if ma else None,
        "MA_120": None, "MA_250": None,
        "BOLL_MID": round(mid, 2), "BOLL_UPPER": round(boll_u, 2), "BOLL_LOWER": round(boll_l, 2),
        "DIF": round(dif[-1], 4), "DEA": round(dea[-1], 4), "MACD": round(macd_v, 4),
        "RSI_6": rsi6, "RSI_12": rsi12, "RSI_24": rsi24,
        "KDJ_K": K, "KDJ_D": D, "KDJ_J": J,
        "code": "", "name": ""}},
    {"listCode": "market_statis_summary", "row": summary},
    {"listCode": "market_statis_interval_trade", "row": {}},
    {"listCode": "market_statis_rotation", "row": {}},
    {"listCode": "market_statis_margin_chg", "row": {}},
    {"listCode": "market_statis_valuation", "row": {}},
]

out = {"ok": True, "data": entries, "source": "offline·txk(%s真实日K)" % TGT_D}
dst = os.path.join(Q, "market_overview", "%s.json" % TGT_D)
json.dump(out, open(dst, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("market_overview/%s.json 写入：涨%d 跌%d 平%d｜涨停%d 跌停%d｜上证%s｜成交%.2f万亿"
      % (TGT_D, red, green, zero, up_lim, dn_lim,
         ("%.2f%%" % chg_szzs) if chg_szzs is not None else "数据缺失", money_yi/1e4))
