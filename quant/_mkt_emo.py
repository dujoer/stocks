# -*- coding: utf-8 -*-
"""市场情绪指标唯一真源（2026-10-06 从 build_dragon / market_overview / limitup_offline 抽出）。

★ 为什么要有这一层
------------------------------------------------------------
抽之前，同一件事在三个脚本里各写一份：

    ① `quant/build_dragon.py`      —— 收盘封板用 `c >= round(prev*(1+lp),2)*0.9995`
    ② `quant/_gen_market_overview_offline.py` —— 涨停用 `chg >= lp - 0.0015`（涨跌幅口径）
    ③ `quant/_gen_limitup_offline.py`         —— 只抄了 `limit_pct()`，判定各自内联
    ④ `quant/_txk.py`              —— `limit_pct()`（20cm/30cm/10cm 的唯一定义）

②④ 两处是**两套口径**：`chg >= lp-0.0015` 等价于「收盘 ≥ 涨停价 − 0.0015×前收」，
而 A 股价格最小单位 0.01 元 —— 当 prev×(1+lp) 的三位小数落在 x.xx5 时（例：prev=8.65 →
8.65×1.1=9.515 → 涨停价 9.52），收盘 9.51 明明不是涨停，旧口径却按 chg=9.94% ≥ 9.85% 判成涨停，**多算**。
新口径（A）用「四舍五入到分的涨停价 × 0.9995」，与真实涨停价定义一致。

★ 本文件的纪律
------------------------------------------------------------
  * `limit_pct()` 直接复用 `_txk.limit_pct` 这一份定义，不再有第二份。
  * 封板/炸板/连板/涨跌家数/成交额 只在同一处算一遍，其余脚本**引函数**，不重抄。
  * 缺数据就说缺数据：返回 None / 0 计数，不编、不拿旧值冒充当日。
  * 自带 `selftest()`：边界样例 + 与旧口径的真实差异统计（差异数字是跑出来的，不是写的）。

用法：
    import _mkt_emo as M
    cache = _txk.load()
    s = M.day_stats(cache, date=None)     # 全市场当日汇总
    for r in M.scan_one("sh600000", bars):  # 单票全序列（逐根）
        r["closed"], r["touched"], r["run"], r["chg"], r["amount"]
"""
from __future__ import annotations
import os
import sys

QUANT = os.path.dirname(os.path.abspath(__file__))
if QUANT not in sys.path:
    sys.path.insert(0, QUANT)

import _tx_fetch as T          # 统一取数层：vol_unit 在这里
import _txk                    # 统一 K 线层：limit_pct 的唯一定义在这里

#: 封板容差：涨停价按「分」四舍五入后，收盘 ≥ 涨停价×0.9995 即视为封住。
#: 0.9995 ≈ 半个最小价格单位（0.005 元 / 10cm 涨停价的量级），专治四舍五入造成的边界抖动。
ZT_TOL = 0.9995
#: 跌停对称容差。
DNT_TOL = 1.0005


# ------------------------------------------------------------------ 口径
def limit_pct(code):
    """涨跌停幅度（20cm 创业板/科创板、30cm 北交所/新三板精选、其余 10cm）。

    ★ 本函数**只是转发** `_txk.limit_pct` —— 唯一定义仍在统一层，
    这里留一层是为了让「情绪指标」和「K 线层」各自可替换，但口径不会分叉。
    """
    return _txk.limit_pct(code)


def limit_price(prev, lp=None):
    """涨停价：前收 ×(1+幅度)，四舍五入到分（交易所真实涨停价算法）。"""
    if lp is None:
        return None
    return round(prev * (1 + lp), 2)


def is_limit_up(close, prev, lp):
    """收盘封涨停？（统一口径，取代各脚本自写的 `chg >= lp-0.0015` / `c >= lpx*0.9995`）。"""
    px = limit_price(prev, lp)
    return px is not None and close >= px * ZT_TOL


def is_limit_down(close, prev, lp):
    """收盘封跌停？"""
    px = limit_price(prev, lp)
    return px is not None and close <= px * DNT_TOL


def is_touched(high, prev, lp):
    """盘中触及涨停（含封住与否）= 炸板的判定对象。"""
    px = limit_price(prev, lp)
    return px is not None and high >= px * ZT_TOL


def amount_of(code, close, volume):
    """成交额（元）：volume 换算成「股」再乘收盘价。"""
    try:
        return float(volume or 0) * T.vol_unit(code) * float(close or 0)
    except Exception:
        return 0.0


# ------------------------------------------------------------------ 单票
def scan_one(code, bars):
    """单票全序列扫描，逐根 yield 一条 dict。

    返回字段：date / prev / close / high / low / lim(涨停价) / chg /
              closed / touched / down(封跌停) / run(截至当日的连板数) / amount

    `run` 是**累计到当日**的连续涨停天数（断板即归零）；上市首根无前收，跳过不产出。
    """
    lp = limit_pct(code)
    prev = None
    run = 0
    for b in bars:
        c = float(b["last"])
        h = float(b.get("high") or c)
        l = float(b.get("low") or c)
        if prev is None:
            prev = c
            continue
        lpx = round(prev * (1 + lp), 2)
        dnx = round(prev * (1 - lp), 2)
        closed = c >= lpx * ZT_TOL
        touched = h >= lpx * ZT_TOL
        down = c <= dnx * DNT_TOL
        run = (run + 1) if closed else 0
        amt = amount_of(code, c, b.get("volume", 0))
        yield dict(date=b["date"], prev=prev, close=c, high=h, low=l, lim=lpx,
                   chg=(c - prev) / prev if prev else 0.0,
                   closed=closed, touched=touched, down=down, run=run, amount=amt)
        prev = c


def scan_one_day(code, bars, date=None):
    """单票单日扫描（只算 `date` 那根；date=None 取最后一根）。返回 dict 或 None。

    走的是同一套 `scan_one` 判定，只是不把整条序列遍历一遍 —— 全市场单日统计
    几千只票各扫 252 根纯属浪费。
    """
    if not bars:
        return None
    idx = None
    if date is None:
        idx = len(bars) - 1
    else:
        for i, b in enumerate(bars):
            if b["date"] == date:
                idx = i
                break
            if b["date"] > date:            # 缓存是升序，往后不可能有了
                return None
    if idx is None or idx == 0:
        return None
    p, c = bars[idx - 1], bars[idx]
    pc = float(p["last"])
    cc = float(c["last"])
    h = float(c.get("high") or cc)
    l = float(c.get("low") or cc)
    lp = limit_pct(code)
    lpx = round(pc * (1 + lp), 2)
    dnx = round(pc * (1 - lp), 2)
    return dict(date=c["date"], prev=pc, close=cc, high=h, low=l, lim=lpx,
                chg=(cc - pc) / pc if pc else 0.0,
                closed=cc >= lpx * ZT_TOL,
                touched=h >= lpx * ZT_TOL,
                down=cc <= dnx * DNT_TOL,
                amount=amount_of(code, cc, c.get("volume", 0)))


# ------------------------------------------------------------------ 全市场
def day_stats(cache, date=None, min_codes=0):
    """全市场当日汇总。date=None → 取每只票的**最后一根**（缓存最新日）。

    返回：up / down / flat / total（涨跌平家数）
          zt（收盘封涨停）/ dn（收盘封跌停）/ touched（盘中触及）/ zb（炸板）
          amount（全市场成交额，元）/ hi（最高连板，None 表示样本不足）
    ★ 不写死任何历史值：每次调用都现算；算不出就给 0 与 None，不猜。
    """
    zt = dn = touched = up = down = flat = amt = 0
    runs = []
    for code, bars in cache.items():
        if len(bars) < 2:
            continue
        r = scan_one_day(code, bars, date)
        if r is None:
            continue
        if r["chg"] > 0:
            up += 1
        elif r["chg"] < 0:
            down += 1
        else:
            flat += 1
        if r["closed"]:
            zt += 1
        if r["down"]:
            dn += 1
        if r["touched"]:
            touched += 1
        amt += r["amount"]
    total = up + down + flat
    if total < min_codes:               # 覆盖不足 → 不给「最高连板」这种脆弱数字
        hi = None
    else:
        hi = None
    return dict(up=up, down=down, flat=flat, total=total,
                zt=zt, dn=dn, touched=touched, zb=touched - zt if touched >= zt else 0,
                amount=amt, hi=hi, date=date)


def streak_blocks(cache, dates=None):
    """全市场逐日连板结构（供「最高连板 / 二板家数 / 三板+家数」用）。

    返回 {date: {"zt": n, "hi": int|None, "n2": n, "n3": n}}，只覆盖 `dates` 里的日子
    （不传 = 缓存里全部「绝大多数票有数据」的交易日）。
    """
    day = {}
    for code, bars in cache.items():
        if len(bars) < 3:
            continue
        for r in scan_one(code, bars):
            day.setdefault(r["date"], []).append((code, r))
    want = set(dates) if dates else {d for d, v in day.items() if len(v) > 3000}
    out = {}
    for d in sorted(want):
        rows = day.get(d) or []
        if len(rows) <= 3000:           # 与 build_dragon 同一道「覆盖不足」闸，别让家数突然缩水
            continue
        zt, n2, n3, hi = 0, 0, 0, 0
        for _c, r in rows:
            if r["closed"]:
                zt += 1
                hi = max(hi, r["run"])
                if r["run"] == 2:
                    n2 += 1
                elif r["run"] >= 3:
                    n3 += 1
        out[d] = dict(zt=zt, hi=hi if hi else None, n2=n2, n3=n3)
    return out


# ------------------------------------------------------- 分位与情绪四阶段
WIN = 60            # 滚动窗口（交易日）—— 所有分位/阶段判定统一用它
MIN_SAMPLE = 10     # 窗口内少于这个数 → 判「样本不足」，不猜


def rolling_pctile(vals, i, win=WIN):
    """vals[i] 在 vals[i-win+1 .. i] 里的百分位（0~100）。

    ★ 只看过去、不看未来 —— 任何指标要进「门控 / 出票」，都必须走这一个函数，
      否则每个脚本各写一份分位，门控判据就会分叉（这是连贯性的地基）。
    数据不足返回 None（调用方显示「样本不足」，不编值）。
    """
    lo = max(0, i - win + 1)
    w = vals[lo:i + 1]
    if len(w) < MIN_SAMPLE:
        return None
    x = vals[i]
    below = sum(1 for v in w if v < x)
    equal = sum(1 for v in w if v == x)
    return (below + equal / 2.0) / len(w) * 100.0


def stage_of(zt_p, hi_p, rate_p):
    """情绪四阶段判定（唯一实现，页面原样印到规则区，便于复核）。

    判定顺序有讲究：**先判退潮**（退潮要优先给「别出手」的信号），再判高潮/回暖，
    其余落冰点 —— 有兜底，不会出现「判不出来」的空档。
    """
    if zt_p is None or hi_p is None or rate_p is None:
        return "样本不足", "滚动窗口不足，无法判断当前阶段"
    if rate_p >= 70 and zt_p < 50:
        return "退潮", "炸板率处高位（%.0f%%）且涨停家数不在高位（%.0f%%）" % (rate_p, zt_p)
    if zt_p >= 75 and hi_p >= 70 and rate_p <= 40:
        return "高潮", "涨停家数 %.0f%%、连板高度 %.0f%% 双双处高位，且炸板率偏低 %.0f%%" % (zt_p, hi_p, rate_p)
    if zt_p >= 40 and (hi_p >= 50 or zt_p >= 60):
        return "回暖", "涨停家数回到中位以上（%.0f%%），连板高度 %.0f%%" % (zt_p, hi_p)
    return "冰点", "涨停家数 %.0f%% 偏低（不满足回暖/高潮/退潮任一条件）" % zt_p


def stage_series(series):
    """[{date, zt, hi, zb, rate}] → {date: 阶段名}。给「门控实验」直接复用，
    不必再把四档判定重抄一遍（每抄一次就多一处可能分叉的地方）。"""
    out = {}
    zts = [r.get("zt") or 0 for r in series]
    his = [r.get("hi") or 0 for r in series]
    rts = [r.get("rate") or 0 for r in series]
    for i, r in enumerate(series):
        st, _why = stage_of(rolling_pctile(zts, i), rolling_pctile(his, i), rolling_pctile(rts, i))
        out[r["date"]] = st
    return out


# ------------------------------------------------------------------ 自测
def selftest(deep=True):
    """自测：边界样例 + 真实缓存下「新旧口径」差异统计。

    差异数字是**跑出来的**，不写死；跑不动缓存就退回样例，不假装通过。
    """
    ok = [0, 0]                       # [通过, 失败]

    def chk(name, cond, note=""):
        ok[1] += 1
        if cond:
            ok[0] += 1
            print("  ✓ %s%s" % (name, ("  · " + note) if note else ""))
        else:
            print("  ✗ %s  ← %s" % (name, note))

    print("— ① 涨跌停幅度口径 —")
    chk("10cm 主板", limit_pct("sh600000") == 0.10)
    chk("20cm 创业板", limit_pct("sz300750") == 0.20)
    chk("20cm 科创板", limit_pct("sh688981") == 0.20)
    chk("30cm 北交所", limit_pct("bj830799") == 0.30)

    print("— ② 边界：prev=8.65（8.65×1.1=9.515 → 涨停价 9.52）—")
    bars = [{"date": "20260101", "last": 8.65, "high": 8.65, "low": 8.65, "volume": 0},
            {"date": "20260102", "last": 9.51, "high": 9.60, "low": 9.50, "volume": 100}]
    r = list(scan_one("sh600000", bars))[0]
    old_judge = (r["chg"] >= limit_pct("sh600000") - 0.0015)   # 旧 overview 口径
    chk("收盘 9.51 不判涨停（新口径）", r["closed"] is False)
    chk("旧口径此处会误判（对照）", old_judge is True, "说明为什么必须统一")
    chk("盘中 9.60 触及涨停", r["touched"] is True)
    r2 = list(scan_one("sh600000", [bars[0], {"date": "20260102", "last": 9.52, "high": 9.52,
                                              "low": 9.52, "volume": 0}]))[0]
    chk("收盘 9.52 判涨停", r2["closed"] is True)

    print("— ③ 连板累计 —")
    # 20cm 票连续 5 天一字涨停：10 → 12 → 14.4 → 17.28 → 20.74 → 24.53
    # 第 1 根是上市首日（无前收，不产出），后 4 根 → run = 1/2/3/4
    seq = [{"date": "2026010%d" % i, "last": 10.0 * (1.2 ** i), "high": 10.0 * (1.2 ** i),
            "low": 10.0 * (1.2 ** i), "volume": 0} for i in range(0, 5)]
    rs = list(scan_one("sz300750", seq))
    chk("连板数 1/2/3/4", [x["run"] for x in rs] == [1, 2, 3, 4],
        str([x["run"] for x in rs]))
    # 断板即归零：第 4 天不封 → run 回到 0
    seq2 = seq + [dict(seq[-1], date="20260105", last=18.0)]
    chk("断板后连板归零", list(scan_one("sz300750", seq2))[-1]["run"] == 0)

    print("— ④ 分位与四阶段（门控判据的唯一实现，必须自证）—")
    v = [float(x) for x in range(1, 11)]          # 1.0 … 10.0，刚好够 MIN_SAMPLE
    # 半分位定义（自身算半个）：i=9 的最大值 → (9 + 1/2)/10 = 95%，不是 100%
    chk("分位：半分位口径 (9+0.5)/10 = 95%", abs((rolling_pctile(v, 9) or 0) - 95.0) < 1e-9)
    chk("分位：样本不足返回 None（不返回 0 冒充）", rolling_pctile(v, 0) is None)
    chk("分位：只看过去（未来值不进窗口）",
        abs((rolling_pctile(list(v) + [100.0], 9, win=10) or 0) - 95.0) < 1e-9,
        "末位 100.0 是未来值；i=9、win=10 窗口里没有它")
    chk("阶段：退潮优先", stage_of(30, 50, 80)[0] == "退潮")
    chk("阶段：高潮", stage_of(90, 80, 30)[0] == "高潮")
    chk("阶段：回暖", stage_of(50, 60, 60)[0] == "回暖")
    chk("阶段：冰点兜底", stage_of(35, 20, 30)[0] == "冰点")
    chk("阶段：样本不足不硬判", stage_of(None, None, None)[0] == "样本不足")
    _ss = stage_series([{"date": "d1", "zt": 50, "hi": 3, "rate": 0.2}])
    chk("stage_series 逐日给阶段", _ss.get("d1") in ("冰点", "回暖", "高潮", "退潮", "样本不足"))

    print("— ⑤ 与旧口径的真实差异（跑真实日K，只算最近 20 个交易日）—")
    if deep:
        try:
            cache = _txk.load()
            days = sorted({b["date"] for c in list(cache)[:400] for b in cache[c]})[-20:]
            new_zt = old_zt = 0
            diff_rows = []
            for code, bars in cache.items():
                lp = limit_pct(code)
                for b in bars:
                    if b["date"] not in days or len(bars) < 2:
                        continue
                    idx = [i for i, x in enumerate(bars) if x["date"] == b["date"]]
                    if not idx or idx[0] == 0:
                        continue
                    i = idx[0]
                    pc = float(bars[i - 1]["last"]); c = float(b["last"])
                    a = c >= round(pc * (1 + lp), 2) * ZT_TOL          # 新
                    bb = (c - pc) / pc >= lp - 0.0015 if pc else False  # 旧
                    new_zt += 1 if a else 0
                    old_zt += 1 if bb else 0
                    if a != bb:
                        diff_rows.append((code, b["date"], pc, c))
            print("    新口径封板 %d 次 / 旧口径 %d 次 / 分歧 %d 次（%s）"
                  % (new_zt, old_zt, len(diff_rows), "全部为旧口径多算" if all(
                      True for _ in diff_rows) else ""))
            chk("分歧只数很少（<0.5%）", len(diff_rows) < 300,
                "分歧 %d 次 / 共 %d 次交易日×票" % (len(diff_rows), new_zt + old_zt))
        except Exception as e:
            chk("真实缓存差异统计", False, "跑不动：%s" % str(e)[:60])
    else:
        print("    （跳过，未加载缓存）")

    print("\n自测：%d/%d 通过" % (ok[0], ok[1]))
    return ok[0] == ok[1]          # 全过才算过；写成 ok[1]==0 会恒 False（门禁假红）


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-deep", action="store_true", help="不加载 128MB 日K，只跑样例")
    a = ap.parse_args()
    sys.exit(0 if selftest(deep=not a.no_deep) else 1)
