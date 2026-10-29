# -*- coding: utf-8 -*-
"""顾比倒数线（Guppy Countback Line）核心算法 —— 全站单一真源。

规则出处：MBA智库百科 / 百度百科「顾比倒数线」条目，二者描述一致。

入场线（下跌趋势 → 上升趋势的确认线）
  1) 取「重要低点」所在 K 线为第 1 条重要 K 线（本实现用左右各 2 根的 pivot low）；
  2) 自该条向左，找到第一条「最高价高于当前条最高价」的 K 线 = 第 2 条重要 K 线；
  3) 自第 2 条向左，找到第一条「最高价高于第 2 条最高价」的 K 线 = 第 3 条重要 K 线；
  4) 沿第 3 条的最高价画水平线 = 顾比倒数入场线；收盘站上 → 趋势转折确认。

止损/止盈线（上升趋势中的离场线）
  起点换为「重要高点」（pivot high），向左倒数 3 条「最低价低于其后一条最低价」的
  重要 K 线，取第 3 条的最低价画水平线；收盘跌破 → 离场。

纪律（原文明确要求，本实现严格遵守）
  - 一律以**收盘价**判定，盘中穿越无效；
  - 只要价格创出新的低点，入场线必须重算（本实现恒用最近的 pivot low，天然重算）；
  - 倒数条数默认 3（顾比标准），2 为激进变体，皆可配。

依赖的 K 线 bar 字段：date / open / high / low / last(收盘) / volume。
"""
from __future__ import annotations

CB_N = 3            # 倒数重要 K 线条数（顾比标准 = 3；2 为激进变体）
PIVOT_L = 2         # pivot 左侧确认根数
PIVOT_R = 2         # pivot 右侧确认根数（→ pivot 需滞后 2 根才能确认）
MIN_BARS = 120      # 参与扫描所需的最少历史根数
MAX_PIVOT_AGE = 45  # 重要低/高点距当日的最大交易日数，超出认为趋势太老


def is_pivot_low(bars, i, l=PIVOT_L, r=PIVOT_R, end=None):
    """bar i 是否为「重要低点」：low 不高于左右各 l/r 根。

    end：可用数据的最后下标（回测重算时必传）。右侧确认一律不越过 end，
    否则历史某日重算会用到当日之后的数据 = 未来函数。
    """
    if end is None:
        end = len(bars) - 1
    hi_end = min(end, len(bars) - 1)
    if i - l < 0 or i + r > hi_end:
        return False
    lo = bars[i].get("low")
    if lo is None:
        return False
    for k in range(i - l, min(i + r, hi_end) + 1):
        if k == i:
            continue
        v = bars[k].get("low")
        if v is not None and v < lo:
            return False
    return True


def is_pivot_high(bars, i, l=PIVOT_L, r=PIVOT_R, end=None):
    """bar i 是否为「重要高点」：high 不低于左右各 l/r 根（右侧不越过 end）。"""
    if end is None:
        end = len(bars) - 1
    hi_end = min(end, len(bars) - 1)
    if i - l < 0 or i + r > hi_end:
        return False
    hi = bars[i].get("high")
    if hi is None:
        return False
    for k in range(i - l, min(i + r, hi_end) + 1):
        if k == i:
            continue
        v = bars[k].get("high")
        if v is not None and v > hi:
            return False
    return True


def last_pivot(bars, end, kind, max_age=MAX_PIVOT_AGE, l=PIVOT_L, r=PIVOT_R):
    """返回 end 之前最近的 pivot 下标（右侧需确认，故上限 end-r）。kind='low'|'high'。"""
    fn = is_pivot_low if kind == "low" else is_pivot_high
    limit = end - r
    if limit < l:
        return None
    for i in range(limit, l - 1, -1):
        if end - i > max_age:
            return None
        if fn(bars, i, l, r, end):
            return i
    return None


def countback(bars, start, kind, n=CB_N):
    """自第 1 条重要 K 线 start 向左倒数第 n 条重要 K 线，返回 (价格, 下标)。

    kind='entry'：逐条要求 high 高于当前参考 high（取第 n 条的 high 画线）
    kind='stop' ：逐条要求 low  低于当前参考 low （取第 n 条的 low  画线）
    """
    if start is None or start <= 0:
        return None, None
    pk = "high" if kind == "entry" else "low"
    cur = bars[start].get(pk)
    if cur is None:
        return None, None
    cnt = 1
    for k in range(start - 1, -1, -1):
        v = bars[k].get(pk)
        if v is None:
            continue
        hit = (v > cur) if kind == "entry" else (v < cur)
        if hit:
            cnt += 1
            cur = v
            if cnt >= n:
                return v, k
    return None, None


def _ma_at(bars, idx, key, n):
    """下标 idx 处（含）往前 n 根的均值；数据不足返回 None。"""
    if idx is None or idx + 1 < n or idx >= len(bars):
        return None
    seg = [bars[idx - k].get(key) for k in range(n)]
    if any(v is None for v in seg):
        return None
    return sum(seg) / n


def days_above(bars, end, line, cap=60):
    """自 end 起向前统计「收盘站上 line」的连续天数（上限 cap）。"""
    if line is None:
        return 0
    n = 0
    for k in range(end, max(-1, end - cap), -1):
        c = bars[k].get("last")
        if c is None or c <= line:
            break
        n += 1
    return n


def eval_stock(code, bars, end=None, cb_n=CB_N, max_age=MAX_PIVOT_AGE,
               l=PIVOT_L, r=PIVOT_R):
    """评估单只个股在 end（下标）处的顾比倒数状态。返回 dict 或 None（不可判）。

    None = 数据不足/无有效 pivot/无第 n 条重要 K 线 —— 一律「不可判」，不猜、不兜底。
    """
    if not bars or len(bars) < MIN_BARS:
        return None
    if end is None:
        end = len(bars) - 1
    if end < MIN_BARS - 1 or end >= len(bars):
        return None
    b = bars[end]
    close = b.get("last")
    if not close or close <= 0:
        return None

    pidx = last_pivot(bars, end, "low", max_age, l, r)
    if pidx is None:
        return None
    line, cbidx = countback(bars, pidx, "entry", cb_n)
    if line is None:
        return None

    prev_close = bars[end - 1].get("last") if end >= 1 else None
    above = close > line
    prev_above = bool(prev_close is not None and prev_close > line)

    hidx = last_pivot(bars, end, "high", max_age, l, r)
    stop, sbidx = (None, None)
    if hidx is not None:
        stop, sbidx = countback(bars, hidx, "stop", cb_n)
    stop_prev = bars[end - 1].get("last") if end >= 1 else None
    below_stop = bool(stop is not None and close < stop)
    prev_below_stop = bool(stop is not None and stop_prev is not None
                           and stop_prev < stop)

    def _ma(key, n):
        if end + 1 < n:
            return None
        seg = [x.get(key) for x in bars[end + 1 - n:end + 1]]
        if any(v is None for v in seg):
            return None
        return sum(seg) / n

    ma20, ma60 = _ma("last", 20), _ma("last", 60)
    ma20_prev = _ma_at(bars, end - 5, "last", 20)
    vol20, vol5 = _ma("volume", 20), _ma("volume", 5)
    vol = b.get("volume")
    close60ago = bars[end - 60].get("last") if end >= 60 else None
    vol_ratio = None
    if vol20 and vol:
        vol_ratio = round(vol / vol20, 3)

    win = bars[max(0, end - 59):end + 1]
    hs = [x.get("high") for x in win if x.get("high") is not None]

    win20 = win[-20:] if len(win) >= 20 else win
    hs20 = [x.get("high") for x in win20 if x.get("high") is not None]

    return {
        "code": code,
        "asof_idx": end,
        "date": b.get("date"),
        "close": close,
        "prev_close": prev_close,
        "entry_line": round(line, 3),
        "cb_date": bars[cbidx].get("date") if cbidx is not None else None,
        "cb_age": (end - cbidx) if cbidx is not None else None,
        "pivot_idx": pidx,
        "pivot_date": bars[pidx].get("date"),
        "pivot_low": bars[pidx].get("low"),
        "pivot_age": end - pidx,
        "stop_line": round(stop, 3) if stop is not None else None,
        "stop_date": bars[sbidx].get("date") if sbidx is not None else None,
        "high_pivot_idx": hidx,
        "high_pivot_date": bars[hidx].get("date") if hidx is not None else None,
        "high_pivot_age": (end - hidx) if hidx is not None else None,
        "high_pivot_date": bars[hidx].get("date") if hidx is not None else None,
        "above": above,
        "days_above": days_above(bars, end, line) if above else 0,
        "cross_up": bool(above and not prev_above),            # 当日收盘首次站上入场线
        "stop_break": bool(below_stop and not prev_below_stop),  # 当日收盘首次跌破止损线
        "below_stop": below_stop,
        "line_dist_pct": round((close / line - 1) * 100, 2),
        "prev_peak_high": max(hs) if hs else None,
        "prev_peak20_high": max(hs20) if hs20 else None,
        # ---- 预测用特征（全部只用 bars[:end+1]，无未来函数）----
        "ma20": round(ma20, 3) if ma20 else None,
        "ma60": round(ma60, 3) if ma60 else None,
        "above_ma20": bool(ma20 and close > ma20),
        "above_ma60": bool(ma60 and close > ma60),
        "ma20_up": bool(ma20 and ma20_prev and ma20 > ma20_prev),
        "ret20": round((close / bars[end - 20].get("last") - 1) * 100, 2)
                 if end >= 20 and bars[end - 20].get("last") else None,
        "ret60": round((close / close60ago - 1) * 100, 2) if close60ago else None,
        "vol_ratio": vol_ratio,
        "vol5_20": round(vol5 / vol20, 3) if (vol5 and vol20) else None,
    }


def stop_line_at(bars, end, cb_n=CB_N, max_age=MAX_PIVOT_AGE,
                 l=PIVOT_L, r=PIVOT_R):
    """只算 end 处的倒数**止损**线（源自重要高点），用于逐日重算的离场规则。

    比 eval_stock 轻（不算入场线/均线），持仓模拟要每天调用，必须省。
    """
    hidx = last_pivot(bars, end, "high", max_age, l, r)
    if hidx is None:
        return None
    line, _ = countback(bars, hidx, "stop", cb_n)
    return line


def entry_plan(row, pct_fallback=0.08):
    """机械买点/止损/阻力参考位（全部取自真实 K 线，非预测）。

    买点 = 当日收盘（顾比纪律：收盘确认站上后，下一交易日可介入）
    止损 = 顾比倒数止损线；无有效止损线时用 -pct_fallback 兜底
    阻力 = 近 60 日最高价
    """
    if not row:
        return None
    c = row["close"]
    stop = row.get("stop_line")
    stop_src = "顾比倒数止损线"
    if stop is None or stop >= c:
        stop = round(c * (1 - pct_fallback), 2)
        stop_src = "兜底 -%.0f%%（无有效倒数止损线）" % (pct_fallback * 100)
    ph = row.get("prev_peak_high")
    return {
        "buy": round(c, 2),
        "stop": round(stop, 2),
        "stop_pct": round((stop / c - 1) * 100, 2),
        "stop_src": stop_src,
        "resist": round(ph, 2) if ph else None,
        "resist_pct": round((ph / c - 1) * 100, 2) if ph else None,
    }
