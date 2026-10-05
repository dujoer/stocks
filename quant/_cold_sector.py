# -*- coding: utf-8 -*-
"""
三年未主升板块 · 引擎（_cold_sector.py）
=====================================
用户需求（2026-10-02）
---------------------
「增加一个板块：三年内没有主升过的板块，并且有很大胜率将要主升的股票」

核心思路
--------
主升浪是有迹可循的：**一段持续上涨 + 显著跑赢大盘**。反过来，
「长期没主升过的板块」= 该板块指数在长周期里**从未出现过像样的主升**。
这类板块的特点是：跌无可跌（估值/涨幅双低）、筹码充分换手、
一旦行业出现**资金点火 + 龙头启动**，爆发力往往最强 —— 这就是「将要主升」的机会来源。

⚠ 口径：2026-10-02 用户确认「**2 年**没主升过也行」→ 默认 LOOKBACK=500 根（约 2 年），
   请求抓 780 根留作备用与后续扩到 3 年。

四步走
------
① **重建行业指数**：板块指数没有现成历史源（腾讯对 `pt*` 只返 1 根）。
   本模块用 `q2_full/_code2industry.json`（5543 票 → 31 行业）按**流通市值加权**，
   每日重算行业指数 → 得到可回溯 2 年的净值序列。
   ⚠ 成分是**当前**分类（分类源不提供历史），存在成分漂移偏差，页面须如实标注。
② **主升识别**：给定一段序列，判定是否发生过「主升」。
   先验固定判据（方向由经济逻辑给定，不筛不调权）：
     - 区间最大涨幅 ≥ 60%（行业两年 60% 已算强势）
     - 涨幅持续 ≥ 60 个交易日（不是一根脉冲）
     - 期间跑赢全市场 ≥ 25pp（真主升 = 有超额，不是随大盘涨）
③ **冷门榜**：对每个行业算「N 年内主升次数 / 最强主升幅度 / 距今多久」，
   按 (主升次数 asc, 最强主升幅度 asc) 排序 → 最冷的排前面。
④ **将要主升打分**：在冷门行业里选股。先验固定 5 因子（等权、方向给定）：
     - 低位：距 500 日高越低越好（透支最少）
     - 企稳：MA20 斜率由负转正（启动证据，不是已启动）
     - 放量：当日量比 > 1.5（资金点火）
     - 强度：20 日相对行业指数走强（个股领先行业 → 龙头先动）
     - 波动收敛：ATR% 越低越好（三连阴已证：低波动档胜率高 88.3%）

防未来函数
----------
- 全部指标只用到 T 日及之前（`i` 及更早切片）。
- 行业指数按 T 日**当日收盘成分**算，不用未来成分（成分漂移是已知偏差，非未来函数）。

用法
----
    python _cold_sector.py --date 2026-09-30            # 出结论 + 落 JSON
    python _cold_sector.py --date 2026-09-30 --backtest  # 附回测（需长历史）
"""
from __future__ import annotations
import os, sys, json, math, argparse, collections, statistics, time, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import _tx_fetch as _TX
import _longk

T_TX = _TX.TX_KLINE
UA_TX = _TX.UA

LONG = os.path.join(HERE, "_long_kline.json")
CODE2IND = os.path.join(HERE, "q2_full", "_code2industry.json")
OUTDIR = os.path.join(HERE, "cold_sector")

# ---- 先验固定参数（经济逻辑给定，不自动筛） ----
LOOKBACK = 500          # 判定「N 年没主升」用多少根（500≈2年）
MIN_BARS = 400          # 指数至少要有这么多根才参与判定
RISE_TH = 0.60          # 主升幅度门槛：区间最大涨幅 ≥ 60%
HOLD_TH = 60            # 主升持续：涨幅需持续 ≥ 60 个交易日
EXCESS_TH = 0.25        # 跑赢大盘 ≥ 25pp 才算「有超额的主升」
TOPN = 20               # 输出股票上限

FACTORS = [
    ("low", "低位", "距 500 日高越低越没透支"),
    ("turn", "企稳", "MA20 斜率由负转正 = 启动前兆"),
    ("vol", "放量", "当日量比 > 1.5 = 资金点火"),
    ("lead", "领涨", "20 日跑赢行业指数 = 龙头先动"),
    ("calm", "波动收敛", "ATR% 低 = 兑现概率高"),
]


# ============================================================
# 1. 数据
# ============================================================
def load_long():
    # 统一走 _longk（单一加载层：mtime 缓存 + 缺文件显式报，不静默回退短缓存）
    # _pullback_probe / _cold_oos / build_cold_sector 都 import 本函数，一并受益
    return _longk.load_long()


def load_industry_map():
    d = json.load(open(CODE2IND, encoding="utf-8"))
    # code -> industry
    m = collections.defaultdict(list)
    for code, ind in d.items():
        if ind:
            m[ind].append(code)
    return dict(m), d


# ============================================================
# 2. 重建行业指数（等权 / 市值不可得时用等权 + 成交额加权折中）
# ============================================================
def build_industry_index(cal, bars_by_code, members):
    """返回 industry -> [收盘序列]，与 cal 对齐。

    做法：每日 = 该行业成分股当日收益的**等权平均**，首日基点 1.0。

    ⚠ 两个必须做的修正（否则指数完全失真）：
      1. **固定票池**：只取在 cal[0] 就有数据的票。新股在涨得最高时才被纳入权重，
         会系统性抬高行业指数（生存偏差）。
      2. **等权，不用成交额加权**：成交额加权让高换手/热门票主导指数，
         实测电子行业 2 年累乘到 +3529%（同期成分股中位仅 +17%）—— 纯权重偏误。
    ⚠ 新股/次新股历史起点晚于全局起点时，用**宽松对齐**（该日该行业有 ≥5 只有数据即算有效），
      否则所有行业都会被判 0 根。
    """
    min_valid = 5
    idx = {}
    # 按行业组织，逐行业只遍历自己的成分票（避免全市场重复扫描）
    for ind in members:
        codes = [c for c in members[ind] if c in bars_by_code]
        codes = [c for c in codes if bars_by_code[c] and len(bars_by_code[c]) >= 30]
        if len(codes) < 5:
            continue
        # ★ 固定票池：只取在窗口起点就有数据的票。否则新股在涨得最高时才被纳入权重，
        #   会系统性抬高该行业指数（生存偏差的一种表现，方向已知）。
        fixed = [c for c in codes if bars_by_code[c][0]["date"] == cal[0]]
        if len(fixed) < 5:
            fixed = codes[:max(5, int(len(codes) * 0.5))]
        tab = {}
        for c in fixed:
            bars = bars_by_code[c]
            r = {}
            for i in range(1, len(bars)):
                p0, p1 = bars[i - 1]["last"], bars[i]["last"]
                if p0 and p0 > 0:
                    r[bars[i]["date"]] = p1 / p0 - 1.0
            if r:
                # ★ 成交额必须修正单位（vol_unit），否则科创板权重放大 100 倍
                tab[c] = (r, _amount(bars, c))
        if len(tab) < 5:
            continue
        nav = [1.0]
        for d in cal[1:]:
            # ★ 等权平均（不用成交额加权）。
            #   成交额加权会让热门/高换手票主导指数 → 系统性偏向热门股，
            #   实测电子行业指数 2 年累乘到 +3529%（同期个股中位仅 +17%），
            #   完全是权重偏误造成的假象。等权无偏，行业内部谁涨谁跌一目了然。
            vals = [r[d] for r, _ in tab.values() if d in r]
            if len(vals) >= 3:
                nav.append(nav[-1] * (1.0 + sum(vals) / len(vals)))
            else:
                nav.append(nav[-1])
        idx[ind] = nav
    return idx


def vol_unit(code):
    """腾讯 fqkline 的 volume 单位：sh688* 已是「股」，其余是「手」（×100）。
    ⚠ 实测成交额中位数：688 = 1.23 亿 vs 其余 = 0.01 亿，**差 114 倍**。
      不乘这个系数 → 基准指数被科创板独票绑架（实测基准虚增到 +1087%）。
    """
    return 1.0 if code.startswith("sh688") else 100.0


def _amount(bars, code):
    """一票的成交额序列（已修正单位）。"""
    vu = vol_unit(code)
    return {b["date"]: (b.get("volume") or 0) * vu * b["last"] for b in bars}


# 真实指数（腾讯可回溯 760 根）——★ 优于自建基准，见 build_market_index 的说明
BENCH = [("sh000300", "沪深300"), ("sh000001", "上证指数"), ("sz399006", "创业板指")]


def fetch_bench(n=780):
    """取真实宽基指数日K。返回 {code: {date: last}}。失败返回 {}。"""
    out = {}
    for code, _nm in BENCH:
        url = "%s?param=%s,day,,,%d,qfq" % (T_TX, code, n)
        for i in range(3):
            try:
                import urllib.request
                req = urllib.request.Request(url, headers={
                    "User-Agent": UA_TX, "Referer": "https://gu.qq.com/", "Connection": "close"})
                with urllib.request.urlopen(req, timeout=25) as r:
                    j = json.loads(r.read().decode("utf-8"))
                d = ((j.get("data") or {}).get(code) or {})
                ks = d.get("qfqday") or d.get("day") or []
                m = {it[0]: float(it[2]) for it in ks}
                if len(m) > 100:
                    out[code] = m
                    break
            except Exception:
                time.sleep(0.8 * (i + 1))
    return out


def build_market_index(cal, bars_by_code, bench_raw=None):
    """全市场基准序列（与 cal 对齐，归一化到 1.0）。

    ★ 优先用**真实宽基指数**（沪深300/上证/创业板，腾讯可回溯 760 根）。
      为什么不自建：自建必须给每票定权重，而任何权重口径都会失真 ——
      实测三种错法都踩过：① 用全部票（退市/次新股缺席 → 基准虚增到 +1087%）；
      ② 加 ≥90% 覆盖门槛（只剩 29 只超级大牛 → 仍是 +1039%）；
      ③ 成交额不修 vol_unit（科创板权重放大 114 倍）。
      真指数无权重争议、可回溯 3 年，是唯一可靠基准。

    兜底：取不到真指数时用**全市场日收益等权平均**（不成交额加权，至少不含权重偏误）。
    """
    if bench_raw:
        # 用沪深300 为主基准（覆盖最广、代表大盘）；缺失则退上证，再退创业板
        pick = None
        for code, _nm in BENCH:
            if code in bench_raw and cal[0] in bench_raw[code]:
                pick = bench_raw[code]
                break
        if pick:
            nav, last = [1.0], pick.get(cal[0])
            if last:
                for d in cal[1:]:
                    c = pick.get(d)
                    nav.append(nav[-1] * (c / last) if c and last > 0 else nav[-1])
                    if c and c > 0:
                        last = c
                return nav
    # 兜底：等权平均
    rets = {}
    for code, bars in bars_by_code.items():
        if not bars or len(bars) < 60:
            continue
        r = {}
        for i in range(1, len(bars)):
            p0, p1 = bars[i - 1]["last"], bars[i]["last"]
            if p0 and p0 > 0:
                r[bars[i]["date"]] = p1 / p0 - 1.0
        rets[code] = r
    nav = [1.0]
    for d in cal[1:]:
        vals = [r[d] for r in rets.values() if d in r]
        nav.append(nav[-1] * (1.0 + (sum(vals) / len(vals) if vals else 0.0)))
    return nav


# ============================================================
# 3. 主升识别（先验固定）
# ============================================================
def find_runs(nav, cal, mkt_nav, start_idx):
    """在 [start_idx, len) 区间里找主升段。返回 [(涨幅, 起止, 跑赢pp, 持续根数)]。

    判据（全部同时满足才算一次主升）：
      1. 从段内某点起，向上累计涨幅 ≥ RISE_TH
      2. 这段涨幅持续 ≥ HOLD_TH 根（不是一根脉冲）
      3. 同期跑赢全市场 ≥ EXCESS_TH
    实现：用「最大回撤内的涨幅」近似 —— 找所有 i，使 nav[j]/nav[i]-1 ≥ RISE_TH 且
    后续 HOLD_TH 根内不破前低（保证持续）。
    """
    n = len(nav)
    runs = []
    i = start_idx
    while i < n - 5:
        # 往后找最大涨幅点
        best = None
        for j in range(i + 1, min(n, i + 250)):
            r = nav[j] / nav[i] - 1.0
            if best is None or r > best[0]:
                best = (r, j)
        if best and best[0] >= RISE_TH:
            r, j = best
            # 持续性：j 之后 HOLD_TH 根内最低点不能跌破起点太多（允许 8% 容忍）
            tail = nav[j:j + HOLD_TH]
            if tail:
                hold_ok = min(tail) >= nav[i] * 0.92
            else:
                hold_ok = False
            if hold_ok:
                m0 = mkt_nav[i]
                m1 = mkt_nav[j]
                excess = (nav[j] / nav[i]) - (m1 / m0) if m0 > 0 and m1 > 0 else 0.0
                if excess >= EXCESS_TH:
                    runs.append({"gain": r, "i0": i, "i1": j,
                                 "d0": cal[i], "d1": cal[j],
                                 "excess": excess, "hold": HOLD_TH})
                    i = j + HOLD_TH
                    continue
        i += 5
    return runs


def sector_stats(nav, cal, mkt_nav, lookback):
    """单个行业：统计 lookback 窗口内的主升情况。"""
    n = len(nav)
    if n < MIN_BARS:
        return None
    start = max(0, n - lookback)
    seg = nav[start:]
    segm = mkt_nav[start:]
    segd = cal[start:]
    # 窗口内累计涨幅
    total = seg[-1] / seg[0] - 1.0
    mtotal = segm[-1] / segm[0] - 1.0 if segm[0] > 0 else 0.0
    runs = find_runs(seg, segd, segm, 0)
    best = max((r["gain"] for r in runs), default=0.0)
    # 距今最近一次主升已过去多少根
    last_gap = None
    if runs:
        last_gap = len(seg) - 1 - runs[-1]["i1"]
    hi = max(seg)
    return {
        "n_bars": n,
        "start": segd[0], "end": segd[-1],
        "total": total, "mkt_total": mtotal, "excess_total": total - mtotal,
        "n_runs": len(runs),
        "best_run": best,
        "last_gap": last_gap,
        "dist_hi": seg[-1] / hi - 1.0,
        "cur": seg[-1],
        "runs": runs,
    }


# ============================================================
# 4. 个股打分（先验固定 5 因子，等权）
# ============================================================
def stock_score(bars, ind_nav, cal, ind_name, i, code=None, name=None):
    """对某票在第 i 根（= 最新根）算因子。返回 None 表示数据不足。"""
    if len(bars) < 60 or i >= len(bars):
        return None
    c = bars[i]["last"]
    if c <= 0:
        return None
    seg = bars[:i + 1]
    n = len(seg)

    # ① 低位：距 500 日高
    w = min(500, n)
    hi = max(b["high"] for b in seg[-w:])
    low_pos = c / hi - 1.0 if hi > 0 else 0.0

    # ② 企稳：MA20 斜率（近 20 日线性拟合日均 %）
    p20 = [b["last"] for b in seg[-20:]]
    if len(p20) >= 10:
        xs = list(range(len(p20)))
        mx, my = sum(xs) / len(p20), sum(p20) / len(p20)
        num = sum((xs[k] - mx) * (p20[k] - my) for k in range(len(p20)))
        den = sum((x - mx) ** 2 for x in xs) or 1.0
        slope = (num / den) / my * 100.0
    else:
        slope = 0.0

    # ③ 放量：当日量比（当日量 / 前 20 日均量，同单位比值不受 vol_unit 影响）
    v = (bars[i].get("volume") or 0)
    vols = [(b.get("volume") or 0) for b in seg[-21:-1]]
    vavg = (sum(vols) / len(vols)) if vols else 0.0
    vr = (v / vavg) if vavg > 0 else 1.0

    # ④ 领涨：20 日涨幅 − 行业指数 20 日涨幅
    m20 = c / seg[-21]["last"] - 1.0 if n >= 21 and seg[-21]["last"] > 0 else 0.0
    if ind_nav and len(ind_nav) >= 21 and ind_nav[-21] > 0:
        ind20 = ind_nav[-1] / ind_nav[-21] - 1.0
    else:
        ind20 = 0.0
    lead = m20 - ind20

    # ⑤ 波动收敛：ATR%
    trs = []
    for k in range(max(1, n - 20), n):
        h, l, pc = seg[k]["high"], seg[k]["low"], seg[k - 1]["last"]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    atr = (sum(trs) / len(trs) / c) if trs and c > 0 else 0.5

    return {
        "code": code, "name": name,
        "low": low_pos, "turn": slope, "vol": vr, "lead": lead, "calm": atr,
        "price": c, "mom20": m20, "atr": atr, "volratio": vr,
        "ind": ind_name,
    }


def to_pct_rank(vals, higher_better):
    """转成 0~1 百分位（先验固定方向，不筛因子权重）。"""
    xs = sorted(vals)
    n = len(xs)
    out = []
    for v in vals:
        r = xs.index(v) / max(1, n - 1) if n > 1 else 0.5
        out.append(r if higher_better else 1.0 - r)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--lookback", type=int, default=LOOKBACK)
    ap.add_argument("--top", type=int, default=TOPN)
    ap.add_argument("--min-members", type=int, default=8)
    a = ap.parse_args()

    bars_by_code = load_long()
    print("[load] 长历史票数 = %d" % len(bars_by_code))
    if not bars_by_code:
        print("！无长历史数据，请先跑 _fetch_long_kline.py（需联网）")
        return

    members, code2ind = load_industry_map()
    print("[行业] %d 个（来自 q2_full/_code2industry.json，5543 票）" % len(members))

    # 对齐交易日历：取所有票的日期并集里、出现次数最多的那只票作基准
    # 更稳：用覆盖度最高的票序列
    best_code, best_n = None, -1
    for c, b in bars_by_code.items():
        if len(b) > best_n:
            best_code, best_n = c, len(b)
    cal = [b["date"] for b in bars_by_code[best_code]]
    print("[日历] %s ~ %s（%d 根，基准 %s）" % (cal[0], cal[-1], len(cal), best_code))
    if cal[-1] != a.date:
        print("[注意] 请求日 %s 与数据末日 %s 不同，按数据末日 %s 计算" % (a.date, cal[-1], cal[-1]))

    # 建「票 → 序列（按 cal 索引的 dict date→bar）」
    pos = {d: i for i, d in enumerate(cal)}
    print("[建指数] 重建 %d 个行业指数（等权收益平均）+ 真实宽基基准 …" % len(members))
    bench_raw = fetch_bench(780)
    mkt_nav = build_market_index(cal, bars_by_code, bench_raw)
    if bench_raw:
        m0 = None
        m1 = mkt_nav[-1]
        # 报告基准实际涨幅，便于人工核对合理性
        print("        基准源 = %s，区间涨幅 %.1f%%"
              % ("真实指数 " + BENCH[0][1] if cal[0] in bench_raw.get(BENCH[0][0], {}) else "等权兜底",
                 (m1 - 1.0) * 100))
    ind_nav = build_industry_index(cal, bars_by_code, members)

    # ---- 冷门榜 ----
    print("\n=== 冷门行业榜（%d 个交易日内无主升）===" % a.lookback)
    stats = {}
    for ind, nav in ind_nav.items():
        st = sector_stats(nav, cal, mkt_nav, a.lookback)
        if st:
            st["n_members"] = len(members.get(ind, []))
            stats[ind] = st
    cold = [k for k, v in stats.items()
            if v["n_members"] >= a.min_members and v["n_bars"] >= a.lookback * 0.8]
    cold.sort(key=lambda k: (stats[k]["n_runs"], stats[k]["best_run"]))
    print("%-12s %6s %6s %8s %10s %10s %8s" %
          ("行业", "成分", "主升数", "最强主升", "窗口涨幅", "跑赢大盘", "距高"))
    for ind in cold:
        v = stats[ind]
        print("%-12s %6d %6d %7.1f%% %9.1f%% %9.1f%% %7.1f%%" %
              (ind, v["n_members"], v["n_runs"], v["best_run"] * 100,
               v["total"] * 100, v["excess_total"] * 100, v["dist_hi"] * 100))

    # ---- 个股打分（只在冷门行业里） ----
    picks = []
    for ind in cold:
        nav = ind_nav[ind]
        for code in members.get(ind, []):
            bars = bars_by_code.get(code)
            if not bars or len(bars) < 60:
                continue
            s = stock_score(bars, nav, cal, ind, len(bars) - 1)
            if not s:
                continue
            s["code"] = code
            # 名称表
            try:
                names = json.load(open(os.path.join(HERE, "_stock_names.json"), encoding="utf-8"))
                s["name"] = names.get(code, code)
            except Exception:
                s["name"] = code
            # 提前过滤：太低位的（跌无可跌但无启动迹象）不入选；要求低位 + 企稳不冲突
            picks.append(s)

    if not picks:
        print("\n[选股] 无满足条件的标的")
        return

    # 因子 → 百分位（等权）
    for fld, _cn, _why in FACTORS:
        hb = fld in ("turn", "vol", "lead")   # 这三个越大越好
        vals = [p[fld] for p in picks]
        pr = to_pct_rank(vals, hb)
        for p, r in zip(picks, pr):
            p["r_" + fld] = r
    for p in picks:
        p["rs"] = sum(p["r_" + f] for f, _c, _w in FACTORS) / len(FACTORS)

    picks.sort(key=lambda x: (-x["rs"], x["code"] or ""))
    top = picks[:a.top]

    print("\n=== 将要主升候选（冷门行业 × 5 因子等权）===")
    print("%-4s %-9s %-12s %6s %7s %7s %7s %7s %6s" %
          ("#", "代码", "行业", "评分", "距500高", "MA20斜率", "量比", "领涨", "ATR%"))
    for i, p in enumerate(top, 1):
        print("%-4d %-9s %-12s %6.3f %6.1f%% %+7.2f %7.2f %+6.1f%% %5.1f%%" %
              (i, p["code"], p["ind"], p["rs"], p["low"] * 100, p["turn"],
               p["vol"], p["lead"] * 100, p["calm"] * 100))

    # ---- 落盘 ----
    os.makedirs(OUTDIR, exist_ok=True)
    out = {
        "asof": cal[-1], "lookback": a.lookback,
        "n_industries": len(ind_nav), "n_cold": len(cold),
        "params": {"RISE_TH": RISE_TH, "HOLD_TH": HOLD_TH, "EXCESS_TH": EXCESS_TH,
                   "MIN_BARS": MIN_BARS, "min_members": a.min_members},
        "caveat": ("板块指数为按当前行业分类事后重建（成分源不含历史），"
                   "存在成分漂移偏差；非官方板块指数。主升判据为先验固定，非拟合。"),
        "cold": [{"ind": k, **{kk: stats[k][kk] for kk in
                    ("n_members", "n_runs", "best_run", "last_gap",
                     "total", "excess_total", "dist_hi", "start")}}
                 for k in cold],
        "picks": [{k: v for k, v in p.items() if k != "sig"} for p in top],
    }
    path = os.path.join(OUTDIR, "cold_%s.json" % cal[-1].replace("-", ""))
    json.dump(out, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n[out] %s" % path)


if __name__ == "__main__":
    main()
