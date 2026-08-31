# -*- coding: utf-8 -*-
"""聚合某日的逐股 raw 快照，计算周表所需的全市场指标。
读取 quant/raw_{DAY}_*.json（每个文件是 data_quote 的完整返回 {ok,data:{code:{...}}}），
输出 quant/scan_{DAY}.json 并打印摘要。

计算口径：
- 中位数涨跌幅(去ST) = 所有非ST股的 change_percent 中位数
- 平均股价(去ST)     = 所有非ST股的 price 均值
- 总市值/流通市值    = 所有股 total_market_cap / circulating_market_cap 求和(元→亿元)
- 成交量分市场(亿手) = volume(单位:手) 按代码前缀分组求和: sh→上海, sz300/301→创业板, sz其他→深圳, bj→北证
- 炸板数量  = high >= price_ceiling-eps 且 close(price) < price_ceiling-eps 的股数(含ST)
- 回头波数  = (high/price - 1) > 0.10 的股数(含ST)
- limitup_closed = 收盘封板(price>=ceil-eps)股数; st_limitup = 其中ST
ST判定: name 以 ST 或 *ST 开头
"""
import json, glob, os, sys, statistics

DAY = sys.argv[1] if len(sys.argv) > 1 else "2026-08-21"
HERE = os.path.dirname(os.path.abspath(__file__))
files = sorted(glob.glob(os.path.join(HERE, f"raw_{DAY}_*.json")))

def market_of(code):
    if code.startswith("sh"):
        return "sh"
    if code.startswith("bj"):
        return "bj"
    if code.startswith("sz"):
        num = code[2:5]
        return "cyb" if num in ("300", "301") else "sz"
    return "other"

changes, prices = [], []
tot_mc = circ_mc = 0.0
vol = {"sh": 0.0, "sz": 0.0, "cyb": 0.0, "bj": 0.0, "other": 0.0}
vol_total = 0.0
zhaban = huitoubo = limitup = st_limitup = st_count = n = n_fields = n_traded = 0

for f in files:
    with open(f, encoding="utf-8") as fh:
        obj = json.load(fh)
    if isinstance(obj, dict):
        data = obj.get("data") or obj.get("stocks") or obj
    else:
        data = obj
    items = data.values() if isinstance(data, dict) else data
    for s in items:
        if not isinstance(s, dict):
            continue
        n += 1
        name = s.get("name") or ""
        is_st = name.startswith("ST") or name.startswith("*ST")
        code = s.get("code") or s.get("symbol") or ""
        price = s.get("price")          # 收盘价
        chg = s.get("change_percent")
        tmc = s.get("total_market_cap")
        cmc = s.get("circulating_market_cap")
        v = s.get("volume")
        high = s.get("high")
        ceil = s.get("price_ceiling")
        if price is None or chg is None:
            continue
        n_fields += 1
        traded = (v is not None and v > 0)
        if traded:
            n_traded += 1
        if is_st:
            st_count += 1
        else:
            # 中位数/平均股价仅统计当日有成交(非停牌)的非ST股
            if traded:
                changes.append(chg)
                prices.append(price)
        if tmc:
            tot_mc += tmc
        if cmc:
            circ_mc += cmc
        if v:
            m = market_of(code)
            vol[m] += v
            vol_total += v
        if ceil is not None and high is not None and price is not None:
            if high >= ceil - 0.01 and price < ceil - 0.01:
                zhaban += 1
            if price > 0 and (high / price - 1) > 0.10:
                huitoubo += 1
            if price >= ceil - 0.01:
                limitup += 1
                if is_st:
                    st_limitup += 1

out = {
    "date": DAY,
    "median_change_nonst": round(statistics.median(changes), 3) if changes else None,
    "avg_price_nonst": round(sum(prices) / len(prices), 3) if prices else None,
    "total_market_cap_yi": round(tot_mc / 1e8, 1),
    "circ_market_cap_yi": round(circ_mc / 1e8, 1),
    "volume_yi_hand": {
        "sh": round(vol["sh"] / 1e8, 1),
        "sz": round(vol["sz"] / 1e8, 1),
        "cyb": round(vol["cyb"] / 1e8, 1),
        "bj": round(vol["bj"] / 1e8, 1),
        "other": round(vol["other"] / 1e8, 1),
        "total": round(vol_total / 1e8, 1),
    },
    "zhaban": zhaban,
    "huitoubo": huitoubo,
    "limitup_closed": limitup,
    "st_limitup_closed": st_limitup,
    "st_count": st_count,
    "n_stocks_scanned": n,
    "n_traded": n_traded,
    "n_with_fields": n_fields,
    "raw_files": len(files),
}
outpath = os.path.join(HERE, f"scan_{DAY}.json")
with open(outpath, "w", encoding="utf-8") as fh:
    json.dump(out, fh, ensure_ascii=False, indent=2)
print(json.dumps(out, ensure_ascii=False, indent=2))
