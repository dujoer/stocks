# -*- coding: utf-8 -*-
"""
强势行业回调买点 · 前提检验（_pullback_probe.py）
==============================================
用户 2026-08-03 决定做方向一：检验「**强势行业回调买点**」这个独立假设。

为什么它是独立假设
------------------
已被证伪的两个方向都是**个股层面横截面**：
  · 资金流（cum5）→ 领先但无增量（+0.53pp vs 涨幅对照 +0.52pp）
  · 位置（距 250 日高）→ 单调有效应但无超额（+0.3pp/5日，增量 <0.5pp）
本假设完全不同：先看**行业层面**（31 个行业，两年日K）谁是强势，
再在强势行业里等**回调**买点。是「行业动量 + 回撤时机」，与个股维度不重叠。

★「回调」的定义必须先验固定，否则必然调出好看的数字 ★
------------------------------------------------------
本模块用**三个可回溯、无自由参数**的定义，一次性全测，不做「挑最好的那个」：

  D1 回撤幅度       从 T 前 60 日高点回撤 ≥X%（X ∈ 3/5/8/12 四个**先验档位**）
  D2 回撤日数       处于「自 60 日高点回落」的 N 日内（N ∈ 5/10/20）
  D3 缩量回调       回调期间成交量萎缩（量能萎缩是洗盘的关键特征）

  每个定义单独检验，**不交叉组合** —— 组合会引入参数搜索。

判定链（每一步都必须过，任一步不过就停）
------------------------------------
① **前提检验**：强势行业（近 N 日有主升）整体是否真的优于弱势行业？
   —— 这是 2026-10-03 已测过的：热门 59.7% > 冷门 55.4%（**已证前提成立**）
② **回调买点检验**：在强势行业里，「回调到定义位置」买入 vs「同行业随机时点」买入
   —— 用全站一致退出口径（止损 −12% / +6% 激活 / 回撤 3% 跟踪 / 满 20 日强平）
③ **随机对照**：同 n、同入场日独立抽样，看该策略在随机分布里的分位

纪律
----
- 入场日间隔 ≥ FWD_WIN（结果窗口不重叠），否则有效样本数被高估。
- 样本不足一律判「不可判」，**不降判据凑通过**。
- 任何策略想上线，必须再过 `_accum_oos.py` 的四道闸门。

用法
----
    python _pullback_probe.py --date 2026-09-30
"""
from __future__ import annotations
import os, sys, json, argparse, collections, statistics, random

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import _cold_sector as CS

# ---- 退出口径（与全站一致：主升/反转/增仓/三连阴全都用这套）----
STOP, ACT, TRAIL, MAXFWD = 0.12, 0.06, 0.03, 20
MIN_N = 40
FWD_STEP = 5          # 入场日间隔（结果窗口不重叠）
DRAWDOWN_LOOKBACK = 60   # 判定「高点」的回看窗口（先验固定）


def simulate(bars, code, i):
    """移动止盈回测。bars 含 _code 供 vol_unit 用。返回 dict 或 None。"""
    if i + 1 >= len(bars):
        return None
    entry = bars[i]["last"]
    if entry <= 0:
        return None
    fwd = min(MAXFWD, len(bars) - 1 - i)
    if fwd < 5:
        return None                      # 前瞻太短 → 不算成熟样本
    peak = entry
    for k in range(1, fwd + 1):
        hi, lo, cl = bars[i + k]["high"], bars[i + k]["low"], bars[i + k]["last"]
        peak = max(peak, hi)
        if lo <= entry * (1 - STOP):
            return {"ret": -STOP, "win": False, "fwd": k, "exit": "硬止损"}
        if peak >= entry * (1 + ACT) and cl <= peak * (1 - TRAIL):
            ret = cl / entry - 1.0
            return {"ret": ret, "win": ret > 0, "fwd": k, "exit": "跟踪止盈"}
        if k == fwd:
            ret = cl / entry - 1.0
            return {"ret": ret, "win": ret > 0, "fwd": k, "exit": "满期"}
    return None


def wr(lst):
    if not lst:
        return (0, 0.0, 0.0)
    n = len(lst)
    return (n, 100.0 * sum(1 for x in lst if x["win"]) / n,
            100.0 * sum(x["ret"] for x in lst) / n)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--per-industry", type=int, default=20, help="对照组每行业抽样数")
    ap.add_argument("--top", type=int, default=20,
                    help="★策略每行业按流动性取前 K 只（与对照等量，edge 才可比）")
    ap.add_argument("--nrand", type=int, default=120)
    a = ap.parse_args()

    bars_by_code = CS.load_long()
    members, _ = CS.load_industry_map()
    if not bars_by_code:
        print("！无长历史，先跑 _fetch_long_kline.py")
        return
    bc, bn = None, -1
    for c, b in bars_by_code.items():
        if len(b) > bn:
            bc, bn = c, len(b)
    cal = [b["date"] for b in bars_by_code[bc]]
    print("[load] 票=%d 日历=%s~%s（%d 根）| 行业=%d"
          % (len(bars_by_code), cal[0], cal[-1], len(cal), len(members)))

    bench = CS.fetch_bench(780)
    mkt = CS.build_market_index(cal, bars_by_code, bench)
    ind_nav = CS.build_industry_index(cal, bars_by_code, members)

    # 逐票索引
    idx = {}
    for c, b in bars_by_code.items():
        idx[c] = {x["date"]: i for i, x in enumerate(b)}

    # ---------- 识别强势行业（近 60 日出现主升）----------
    stats = {}
    for ind, nav in ind_nav.items():
        st = CS.sector_stats(nav, cal, mkt, 500)
        if st:
            st["n_members"] = len(members.get(ind, []))
            stats[ind] = st
    ok_ind = [k for k, v in stats.items()
              if v["n_members"] >= 8 and v["n_bars"] >= 400]
    ranked = sorted(ok_ind, key=lambda k: (stats[k]["n_runs"], stats[k]["best_run"]))
    hot = [k for k in ranked if stats[k]["n_runs"] >= 1]     # 近两年有主升 = 强势
    print("[行业] 可用 %d，其中强势（近两年≥1 次主升）%d 个" % (len(ok_ind), len(hot)))
    if not hot:
        print("无强势行业 → 退出")
        return

    # ---------- 入场日窗口 ----------
    hi = max(0, len(cal) - MAXFWD)
    lo = 260                                   # 需足够历史算 60 日高点
    days = cal[lo:hi:FWD_STEP]
    print("[入场日] %d 个（间隔 %d 日）%s ~ %s" % (len(days), FWD_STEP, days[0], days[-1]))
    if len(days) < 8:
        print("入场日不足 → 不可判")
        return

    def ind_pullback_state(ind, T, ti):
        """行业在 T 的回调状态。全部只用 T 及之前。
        返回 (距60日高%, 已回落天数, 缩量比) 或 None"""
        nav = ind_nav[ind]
        if ti < 5:
            return None
        seg = nav[max(0, ti - DRAWDOWN_LOOKBACK + 1):ti + 1]
        if len(seg) < 20:
            return None
        cur = seg[-1]
        hi_ = max(seg)
        if hi_ <= 0:
            return None
        dd = (cur / hi_ - 1.0) * 100.0            # 负值
        # 回落天数：从高点到今天过了几根
        hi_i = max(range(len(seg)), key=lambda k: seg[k])
        gap = len(seg) - 1 - hi_i
        return dd, gap, hi_

    def ind_vol_ratio(ind, T, ti, gap):
        """回调期间量能萎缩比：回调段均量 / 前段均量。"""
        members_ind = [c for c in members.get(ind, [])
                       if c in idx and T in idx[c] and len(bars_by_code[c]) > ti + 1]
        if len(members_ind) < 5:
            return None
        v_now = []
        v_pre = []
        for c in members_ind:
            b = bars_by_code[c]
            i = idx[c][T]          # ★ 键是日期字符串
            w = max(1, min(gap + 1, 5))
            seg_now = b[max(0, i - w + 1):i + 1]
            v_now.append(sum(x.get("volume") or 0 for x in seg_now) / len(seg_now))
            # 前段窗口与回调段**不重叠**（避免共享样本抬高相关性）
            j1 = max(0, i - w)                  # 前段右界（不含）
            j0 = max(0, j1 - 10)               # 前段左界
            seg_pre = b[j0:j1]
            if not seg_pre:
                continue
            v_pre.append(sum(x.get("volume") or 0 for x in seg_pre) / len(seg_pre))
        if not v_now or not v_pre:
            return None
        mn = sum(v_now) / len(v_now)
        mp = sum(v_pre) / len(v_pre)
        if mp <= 0:
            return None
        return mn / mp

    # ---------- 逐日选股 + 回测 ----------
    # 定义 D1：回撤幅度档位（先验固定四个）
    DD_LEVELS = [3, 5, 8, 12]
    GAP_LEVELS = [5, 10, 20]
    VOL_RATIO = 0.8                                # 缩量：回调量 ≤ 前段 80%

    recs = collections.defaultdict(list)          # 策略名 -> [rec]
    base_pool = {}                                # 行业 -> 当日可分析票（做对照）
    for T in days:
        try:
            ti = cal.index(T)
        except ValueError:
            continue
        day_all = []
        day_hot = []
        for ind in hot:
            st = ind_pullback_state(ind, T, ti)
            if st is None:
                continue
            dd, gap, hi_ = st
            # ★ 键是**日期字符串**，不能用 cal 的下标 ti 去查（曾恒为空）
            mem = [c for c in members.get(ind, [])
                   if c in idx and T in idx[c] and len(bars_by_code[c]) > ti + 1]
            base_pool[ind] = mem
            # ★★ 关键设计修正：原写法把**该行业所有成分股**都当样本
            #   （n 高达 24 万）→ 那测的是「能不能整体加仓」这个 beta，
            #   不是选股能力。edge 会因样本量虚高而看起来很好。
            #   现在改为：**行业内按流动性横截面取前 K 只**（K 由 --top 控制），
            #   并让对照组同样取 K 只 → edge 才是「同一行业内选股」的净效果。
            mem_liq = []
            for c in mem:
                b = bars_by_code[c]
                i = idx[c][T]
                if i < 20:
                    continue
                vu = 1.0 if c.startswith("sh688") else 100.0
                amt = sum((x.get("volume") or 0) * vu * (x.get("last") or 0)
                          for x in b[i - 19:i + 1]) / 20.0
                if amt <= 0:
                    continue
                r = simulate(b, c, i)
                if not r:
                    continue
                mem_liq.append((amt, c, r))
            mem_liq.sort(key=lambda t: -t[0])
            for amt, c, r in mem_liq[:a.top]:
                rec = {"T": T, "code": c, "ind": ind,
                       "ret": r["ret"], "win": r["win"], "exit": r["exit"]}
                day_all.append(rec)
                # D1：回撤达到档位，且仍处强势（未破 60 日高太多）
                for lv in DD_LEVELS:
                    if dd <= -lv and gap >= 1:
                        recs["D1_回撤%d%%" % lv].append(rec)
                # D2：回落天数在档位内
                for lv in GAP_LEVELS:
                    if 1 <= gap <= lv and dd < 0:
                        recs["D2_回落%d日内" % lv].append(rec)
                # D3：缩量回调
                vr = ind_vol_ratio(ind, T, ti, gap)
                if vr is not None and dd <= -5 and 1 <= gap <= 20 and vr <= VOL_RATIO:
                    recs["D3_缩量回调"].append(rec)
                # 组合（先验固定，不扫参数）：回撤≥5% + 缩量 + 20日内
                if vr is not None and dd <= -5 and 1 <= gap <= 20 and vr <= VOL_RATIO:
                    recs["D4_回撤5%+缩量"].append(rec)
                day_hot.append(rec)
        # ★ 对照必须与策略**同入场日、同行业、且抽样规模可配平**，否则 edge 不可比。
        #   旧写法每行业固定抽 5 只，而策略取了全行业所有票 → 对照 n 远小于策略 n，
        #   edge 里混进了「样本量差异」而非「选股能力」。改为按行业等比例抽样。
        for ind in hot:
            mem = base_pool.get(ind) or []
            if len(mem) < 5:
                continue
            rr = random.Random(abs(hash((T, ind))) % (2 ** 31))
            for c in rr.sample(mem, min(a.per_industry, len(mem))):
                i = idx[c].get(T)
                if i is None:
                    continue
                r = simulate(bars_by_code[c], c, i)
                if r:
                    recs["_对照_同行业随机"].append(
                        {"T": T, "code": c, "ind": ind,
                         "ret": r["ret"], "win": r["win"], "exit": r["exit"]})

    # ---------- 汇总 ----------
    bname = "_对照_同行业随机"
    if not recs.get(bname):
        print("对照样本为空 → 不可判")
        return
    bn_, bw_, ba_ = wr(recs[bname])
    print("\n=== 对照：强势行业内随机时点买入 ===")
    print("   n=%d  胜率=%.1f%%  均值=%+.2f%%" % (bn_, bw_, ba_))

    print("\n=== 各回调定义（先验固定，不挑最好的）===")
    print("   %-16s %7s %8s %9s %10s" % ("定义", "n", "胜率", "均值", "vs对照"))
    out = {}
    for name in sorted(recs):
        if name == bname:
            continue
        n, w, rt = wr(recs[name])
        if n < MIN_N:
            print("   %-16s %7d %8s %9s  样本不足(≥%d)" % (name, n, "—", "—", MIN_N))
            out[name] = {"n": n, "wr": None, "verdict": "样本不足"}
            continue
        edge = w - bw_
        print("   %-16s %7d %7.1f%% %+8.2f%% %+9.1fpp" % (name, n, w, rt, edge))
        out[name] = {"n": n, "wr": w, "avg": rt, "edge": edge}

    # ---------- 随机对照分位（对最优的一个，只为看是否显著）----------
    print("\n=== 随机对照分位（判断是否显著，非选最优）===")
    pctile = {}
    for name, v in out.items():
        if v.get("wr") is None:
            continue
        pick = recs[name]
        rr = random.Random(20260803)
        byday = collections.defaultdict(int)
        for r in pick:
            byday[r["T"]] += 1
        wins = 0
        for _ in range(a.nrand):
            smp = []
            for T, k in byday.items():
                mem = []
                for ind in hot:
                    mm = base_pool.get(ind) or []
                    if mm:
                        mem.extend(rr.sample(mm, min(a.per_industry, len(mm))))
                for c in mem[:k]:
                    i = idx[c].get(T)
                    if i is None:
                        continue
                    r = simulate(bars_by_code[c], c, i)
                    if r:
                        smp.append({"win": r["win"], "ret": r["ret"]})
            if smp:
                _mn, mw, _ = wr(smp)
                if mw >= v["wr"]:
                    wins += 1
        p = 100.0 * wins / a.nrand
        pctile[name] = p
        print("   %-16s 胜率%.1f%%  随机分位=%.1f%% %s"
              % (name, v["wr"], p, "★显著" if p >= 95 else ""))
        out[name]["pctile"] = p

    # ---------- 结论 ----------
    print("\n=== 结论 ===")
    # ★ 判定必须**同时**满足：edge>0（跑赢对照）且 随机分位≤5（随机几乎达不到）。
    #   旧版只卡了分位没卡 edge → 把「随机分位 100% 且 edge −4.5pp」的
    #   D3_缩量回调误判成「最优且显著」（它其实明显更差）。
    sig = [k for k, v in out.items()
           if v.get("wr") is not None and v.get("pctile") is not None
           and v["edge"] > 0 and v["pctile"] <= 5 and v["n"] >= MIN_N]
    pos = [k for k, v in out.items()
           if v.get("wr") is not None and v["edge"] > 0 and v["n"] >= MIN_N]
    worse = [k for k, v in out.items()
             if v.get("wr") is not None and v["edge"] <= 0 and v["n"] >= MIN_N]
    print("   跑赢对照（edge>0）：%s" % ("、".join(pos) or "无"))
    print("   显著更优（edge>0 且随机分位≤5%%）：%s" % ("、".join(sig) or "无"))
    if worse:
        print("   ★反而更差（edge≤0）：%s" % "、".join(worse))
    if sig:
        best = max(sig, key=lambda k: out[k]["edge"])
        print("   → 最优且显著：%s（n=%d 胜率%.1f%% edge%+.1fpp 随机分位%.1f%%）"
              % (best, out[best]["n"], out[best]["wr"], out[best]["edge"],
                 out[best]["pctile"]))
        print("   ★ 还需过 `_accum_oos.py` 的样本外 walk-forward（移动止盈已在本脚本用，"
              "但样本外切分与两半同向尚未做）")
    else:
        print("   → **无「显著且更优」者** → 不出票（宁可不选）")

    p = os.path.join(CS.OUTDIR, "pullback_%s.json" % a.date.replace("-", ""))
    json.dump({"date": a.date, "n_hot_ind": len(hot), "hot": hot,
               "entry_days": days, "per_industry": a.per_industry,
               "exit": {"stop": STOP, "act": ACT, "trail": TRAIL, "maxfwd": MAXFWD},
               "baseline": {"n": bn_, "wr": bw_, "avg": ba_},
               "strats": out},
              open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n[out] %s" % p)


if __name__ == "__main__":
    main()
