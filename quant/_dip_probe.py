# -*- coding: utf-8 -*-
"""实测：「找上涨率高的信号 → 低吸买入」这条路到底通不通（_dip_probe.py）

用户的假说（2026-10-04 提出）
----------------------------
「不需要涨停，尽量看上涨率高的，这个可以通过低吸来盈利，这个方法是否可行？」

拆成两个可证伪的子命题：
  H1 **上涨率可筛**：存在 T 日收盘可知的信号，使 T→T+1 的上涨率显著高于全市场。
  H2 **低吸能兑现**：把 H1 选出的票改用「T+1 挂低价限价单」买入，收益不劣于直接买入。

为什么 H2 很可能不成立（本脚本要证伪的核心）
------------------------------------------
低吸有**逆向选择**：T+1 只有当天走弱的票才会跌到你的挂单价。
而「上涨率高的信号」的票，恰恰是当天最容易直接冲高、**不给你低吸机会**的那批。
⇒ 能低吸到的成交样本，可能是信号失效的那部分。
⇒ 成交率与成交后收益必须**同时报告**，不能只看「成交了的那批赚多少」。

★ 三个必须分开的口径（混在一起必然得出好看的假结论）
----------------------------------------------------
  P0_追高   T+1 开盘价买入            —— 所有票都能买到，含「成交率=100%」
  P1_低吸x  T+1 挂 T日收盘×(1−x%) 限价 —— 有成交率，成交量 <100%
  chg1      T 日收盘买入 → T+1 收盘卖  —— 这才是「次日上涨率」，但**配不了低吸**
                                          （A股 T+1：T+1 买的当天不能卖）

★ 判定低吸有效，必须同时满足三条（缺一即证伪）
----------------------------------------------
  ① 成交后均值 > 0，且 ② 成交后均值 > 同一样本按 P0 追高的均值（买点确实改善），
  ③ 池化净期望（成交率 × 成交后均值）> 0 —— 不成交 = 资金闲置，也是结果。

反例先例：做T池 A 档逐日 edge +0.537pp/R3 95%，但池化「触买后」−0.28%
（`_tplus_tier_gate.py`）—— 同一类陷阱，已用 `_gate_common.emit_license(pool_key=...)` 拦下。

数据
----
`quant/_long_kline.json`（腾讯前复权长历史日K，含 open/high/low/last/volume）
→ 全市场 ≈5000 只 × ≈780 根，足够算 MA/ATR 并做 T+1 限价成交判定。

用法
----
    python _dip_probe.py --date 2026-09-30
    python _dip_probe.py --date 2026-09-30 --step 3     # 步长敏感性
"""
from __future__ import annotations
import os, sys, json, argparse, collections, statistics

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _gate_common as G

LONG = os.path.join(HERE, "_long_kline.json")

# ---- 先验固定参数（经济逻辑给定，**不做参数搜索**）----
DIP_LEVELS = [0.5, 1.0, 2.0, 3.0]      # 低吸挂单折扣档（%），四档全测，不挑最好的
HOLDS = [2, 5]                          # 持有到 T+N 收盘（N≥2，满足 T+1 制度）
SIGS = ["S1_趋势多头", "S2_强势回踩", "S3_超跌首阳", "S4_窄幅缩量"]
SIG_CN = {
    "S1_趋势多头": "收盘>MA20>MA60 且 MA20 上行（动量）",
    "S2_强势回踩": "站上MA60 + 当日跌0.5~3% + 缩量（典型低吸形态）",
    "S3_超跌首阳": "近5日累计跌≥6% 且 当日收阳（抢反弹）",
    "S4_窄幅缩量": "20日ATR<2% + 量<20日均量×0.8（横盘蓄势）",
}
MIN_BARS = 70                           # 至少 70 根才参与（MA60 + 余量）
MIN_AMT20 = 3.0e7                       # 20日均额 ≥3000万（可交易域，僵尸股买不到也卖不掉）


def load_long():
    if not os.path.exists(LONG):
        return {}
    with open(LONG, encoding="utf-8") as f:
        return json.load(f)


def prep(bars, unit=100.0):
    """一次性算好滚动指标（O(n)），返回与 bars 等长的列表。
    全部只用 i 及之前的数据 —— 无未来函数。

    `unit`：成交额换算系数。腾讯 fqkline 的 volume 单位不统一
    （sh688* 已是「股」，其余是「手」→ ×100），不修正则科创板成交额被低估 100 倍、
    流动性门槛会误杀全部科创板票。
    """
    n = len(bars)
    cl = [b.get("last") or 0.0 for b in bars]
    op = [b.get("open") or 0.0 for b in bars]
    hi = [b.get("high") or 0.0 for b in bars]
    lo = [b.get("low") or 0.0 for b in bars]
    vo = [b.get("volume") or 0.0 for b in bars]

    ma20 = [None] * n
    ma60 = [None] * n
    v20 = [None] * n
    atr20 = [None] * n
    amt20 = [None] * n

    s20 = s60 = 0.0
    sv = 0.0
    sa = 0.0
    samt = 0.0
    for i in range(n):
        s20 += cl[i]
        s60 += cl[i]
        sv += vo[i]
        sa += ((hi[i] - lo[i]) / cl[i]) if cl[i] > 0 else 0.0
        samt += vo[i] * cl[i] * unit
        if i >= 20:
            s20 -= cl[i - 20]
            sv -= vo[i - 20]
            sa -= ((hi[i - 20] - lo[i - 20]) / cl[i - 20]) if cl[i - 20] > 0 else 0.0
            samt -= vo[i - 20] * cl[i - 20] * unit
        # ★ 60 日窗口必须滑出 —— 曾有版本只加不减，MA60 随天数单调膨胀，
        #   导致「收盘 > MA60」几乎永不成立（全市场 48 万样本里只剩 9 个）。
        if i >= 60:
            s60 -= cl[i - 60]
        if i >= 19:
            ma20[i] = s20 / 20.0
            v20[i] = sv / 20.0
            atr20[i] = sa / 20.0
            amt20[i] = samt / 20.0
        if i >= 59:
            ma60[i] = s60 / 60.0
    return {"cl": cl, "op": op, "hi": hi, "lo": lo, "vo": vo,
            "ma20": ma20, "ma60": ma60, "v20": v20, "atr20": atr20, "amt20": amt20}


def signals_at(M, i):
    """T=i 日收盘时的信号掩码（bit 对应 SIGS 下标）。只用 ≤i 的数据。"""
    cl, op = M["cl"], M["op"]
    ma20, ma60 = M["ma20"], M["ma60"]
    v20, atr20 = M["v20"], M["atr20"]
    if i < 61 or cl[i] <= 0 or cl[i - 1] <= 0:
        return 0
    mask = 0
    c, c1, o = cl[i], cl[i - 1], op[i]
    chg = c / c1 - 1.0
    a20, a60, vv = ma20[i], ma60[i], v20[i]
    # S1 趋势多头
    if a20 and a60 and c > a20 > a60 and ma20[i - 5] is not None and a20 > ma20[i - 5]:
        mask |= 1
    # S2 强势回踩（缩量回调）
    if a60 and c > a60 and vv and -0.03 <= chg <= -0.005 and M["vo"][i] < vv:
        mask |= 2
    # S3 超跌首阳
    if i >= 5 and cl[i - 5] > 0 and (c / cl[i - 5] - 1.0) <= -0.06 and c > o:
        mask |= 4
    # S4 窄幅缩量
    if atr20[i] is not None and vv and (atr20[i] < 0.02) and M["vo"][i] < 0.8 * vv:
        mask |= 8
    return mask


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--step", type=int, default=5, help="入场日间隔（窗口不重叠）")
    ap.add_argument("--lookback", type=int, default=250, help="入场日起始回看")
    ap.add_argument("--boot", type=int, default=400)
    a = ap.parse_args()
    DS = a.date.replace("-", "")

    bars_by_code = load_long()
    if not bars_by_code:
        print("！无长历史，先跑 _fetch_long_kline.py")
        return

    # 交易日历：全票日期并集 + 覆盖度过滤（早期稀疏日剔除）
    cover = collections.Counter()
    for b in bars_by_code.values():
        for x in b:
            cover[x["date"]] += 1
    cutoff = max(cover.values()) * 0.25
    cal = sorted(d for d, c in cover.items() if c >= cutoff and d <= a.date)
    print(f"[load] 票={len(bars_by_code)}  日历={cal[0]}~{cal[-1]}（{len(cal)} 根）")

    # 每票预计算
    M_by_code = {}
    for c, b in bars_by_code.items():
        if len(b) < MIN_BARS:
            continue
        M_by_code[c] = prep(b, 1.0 if c.startswith("sh688") else 100.0)
    # 真实交易日历索引（用于剔停牌样本，避免「下一根」其实是数周后）
    CI = {d: j for j, d in enumerate(cal)}

    # 入场日：留足 60 根算指标 + HOLDS 前瞻
    maxN = max(HOLDS)
    hi_i = len(cal) - maxN - 1
    lo_i = min(a.lookback, max(0, hi_i - 1))
    entry_days = cal[lo_i:hi_i:a.step]
    if len(entry_days) < 8:
        print("！入场日不足 → 不可判")
        return
    print(f"[entry] {len(entry_days)} 个入场日（间隔{a.step}）{entry_days[0]} ~ {entry_days[-1]}")

    ESET = set(entry_days)
    recs = []
    for c, b in bars_by_code.items():
        M = M_by_code.get(c)
        if M is None:
            continue
        cl = M["cl"]
        for i, x in enumerate(b):
            T = x["date"]
            if T not in ESET:
                continue
            if i + maxN >= len(b) or i < 61:
                continue
            # ★ 必须与真实交易日历**连续**——停牌票的下一根可能在三周后，
            #   直接拿 b[i+1] 当「T+1」会算出数周后的收益，污染结论。
            cj = CI.get(T)
            if cj is None or cj + maxN >= len(cal):
                continue
            if any(b[i + k]["date"] != cal[cj + k] for k in range(1, maxN + 1)):
                continue
            amt = M["amt20"][i]
            if not amt or amt < MIN_AMT20:
                continue                       # 可交易域
            mask = signals_at(M, i)
            close_T = cl[i]
            if close_T <= 0:
                continue
            op1 = M["op"][i + 1] or 0.0
            lo1 = M["lo"][i + 1] or 0.0
            cl1 = cl[i + 1]
            rec = {"date": T, "code": c, "mask": mask, "amt": amt,
                   "chg1": (cl1 / close_T - 1.0) * 100.0}
            # P0 追高：T+1 开盘买
            for N in HOLDS:
                rec[f"ret0_{N}"] = (cl[i + N] / op1 - 1.0) * 100.0 if op1 > 0 else None
            # P1 低吸各档
            fills = {}
            for x in DIP_LEVELS:
                limit = close_T * (1.0 - x / 100.0)
                if op1 > 0 and op1 <= limit:
                    fill_px = op1                 # 跳空低开，以开盘成交
                    ok = True
                elif lo1 > 0 and lo1 <= limit:
                    fill_px = limit               # 盘中触及限价
                    ok = True
                else:
                    fill_px, ok = None, False
                d = {"ok": ok}
                if ok:
                    for N in HOLDS:
                        d[f"ret1_{N}"] = (cl[i + N] / fill_px - 1.0) * 100.0
                fills[f"{x}"] = d
            rec["fills"] = fills
            recs.append(rec)

    if not recs:
        print("！无样本")
        return
    print(f"[面板] 样本 {len(recs)} 行（可交易域：20日均额≥{MIN_AMT20/1e8:.1f}亿）")

    # ---------------- 统计 ----------------
    def mean_wr(rs):
        if not rs:
            return None, None, 0
        return (sum(x["pnl"] for x in rs) / len(rs),
                100.0 * sum(1 for x in rs if x["win"]) / len(rs), len(rs))

    res = {"date": a.date, "step": a.step, "n_recs": len(recs),
           "n_days": len(entry_days), "entry_days": entry_days, "boot": a.boot,
           "dip_levels": DIP_LEVELS, "holds": HOLDS, "min_amt20": MIN_AMT20}

    # ---- 口径一：次日上涨率（T 收盘买 → T+1 收盘卖）----
    print("\n=== 口径一：T→T+1 上涨率（这才是「次日涨不涨」，但配不了低吸）===")
    base_mean, base_wr, base_n = mean_wr([{"pnl": r["chg1"], "win": r["chg1"] > 0} for r in recs])
    print(f"   全市场母集   n={base_n:6d}  上涨率 {base_wr:5.1f}%  均值 {base_mean:+.2f}%")
    s1out = {"all": {"n": base_n, "wr": round(base_wr, 1), "mean": round(base_mean, 3)}}
    for k, name in enumerate(SIGS):
        sub = [r for r in recs if r["mask"] & (1 << k)]
        m, w, n = mean_wr([{"pnl": r["chg1"], "win": r["chg1"] > 0} for r in sub])
        if n < 100:
            continue
        print(f"   {name:<12} n={n:6d}  上涨率 {w:5.1f}%  均值 {m:+.2f}%  vs母集 {w-base_wr:+.1f}pp")
        s1out[name] = {"n": n, "wr": round(w, 1), "mean": round(m, 3),
                       "edge_pp": round(w - base_wr, 1)}
    res["nextday"] = s1out

    # ---- 口径二/三：追高 vs 低吸 ----
    print("\n=== 口径二/三：追高(P0: T+1开盘买) vs 低吸(P1: 挂低价限价) ===")
    print("   ★ 判定低吸值不值得做，只看一条：低吸的**池化净期望**能否超过「直接追高」")
    print("     （池化 = 不成交记 0；资金角度：没成交的那份钱闲置，不能算赚）")
    import random as _rnd
    out_sig = {}
    for k, name in enumerate(SIGS):
        bit = 1 << k
        sub_all = [r for r in recs if r["mask"] & bit]
        if len(sub_all) < 100:
            out_sig[name] = {"n_all": len(sub_all), "verdict": "样本不足"}
            print(f"\n   [{name}] 样本不足（n={len(sub_all)}）")
            continue
        ctrl_pool = collections.defaultdict(list)
        for r in recs:
            if not (r["mask"] & bit):
                ctrl_pool[r["date"]].append(r)
        by_day_n = collections.Counter(r["date"] for r in sub_all)
        entry = {"n_all": len(sub_all), "sig_cn": SIG_CN[name], "holds": {}}
        print(f"\n   [{name}] n={len(sub_all)}  {SIG_CN[name]}")
        for N in HOLDS:
            r_all = [{"date": r["date"], "pnl": r[f"ret0_{N}"], "win": r[f"ret0_{N}"] > 0}
                     for r in sub_all if r[f"ret0_{N}"] is not None]
            m0, w0, n0 = mean_wr(r_all)
            rr = _rnd.Random(20261004 + N)
            crows = []
            for Td, lst in ctrl_pool.items():
                kk = by_day_n.get(Td, 0)
                if kk <= 0 or not lst:
                    continue
                for r in rr.sample(lst, min(kk, len(lst))):
                    v = r[f"ret0_{N}"]
                    if v is not None:
                        crows.append({"date": Td, "pnl": v, "win": v > 0})
            cm, cw, cn = mean_wr(crows)
            # 逐日：信号 P0 vs 同日等量对照（回答「这个信号本身有没有超额，稳不稳」）
            sig_d, ctl_d = collections.defaultdict(list), collections.defaultdict(list)
            for r in sub_all:
                v = r[f"ret0_{N}"]
                if v is not None:
                    sig_d[r["date"]].append(v)
            for r in crows:
                ctl_d[r["date"]].append(r["pnl"])
            eg_sig = [sum(sig_d[d]) / len(sig_d[d]) - sum(ctl_d[d]) / len(ctl_d[d])
                      for d in sorted(sig_d) if ctl_d.get(d)]
            r3_sig = G._boot_pos(eg_sig, boot=a.boot) if len(eg_sig) >= 3 else 0.0
            edg = (m0 - cm) if (m0 is not None and cm is not None) else None
            print(f"      P0追高(全样本)：n={n0:6d} 上涨率 {w0:5.1f}% 均值 {m0:+.3f}%")
            if cm is not None:
                print(f"      等量对照(同日非本档)：n={cn:6d} 上涨率 {cw:5.1f}% 均值 {cm:+.3f}%"
                      f"  → 超额 {edg:+.3f}pp  R3={r3_sig:.1f}%")
            ent = {"p0": {"n": n0, "wr": round(w0, 1), "mean": round(m0, 3)},
                   "ctrl": {"n": cn, "wr": round(cw, 1) if cw is not None else None,
                            "mean": round(cm, 3) if cm is not None else None,
                            "edge_pp": round(edg, 3) if edg is not None else None,
                            "r3": round(r3_sig, 1)},
                   "levels": {}}
            byd_all = collections.defaultdict(list)
            for r in sub_all:
                v = r[f"ret0_{N}"]
                if v is not None:
                    byd_all[r["date"]].append(v)
            for x in DIP_LEVELS:
                fk = f"{x}"
                filled = [r for r in sub_all
                          if r["fills"][fk]["ok"]
                          and r["fills"][fk].get(f"ret1_{N}") is not None
                          and r[f"ret0_{N}"] is not None]
                n_fill = len(filled)
                fill_rate = 100.0 * n_fill / max(1, len(sub_all))
                m1 = w1 = mp0 = mmiss = None
                if n_fill:
                    m1 = sum(r["fills"][fk][f"ret1_{N}"] for r in filled) / n_fill
                    w1 = 100.0 * sum(1 for r in filled if r["fills"][fk][f"ret1_{N}"] > 0) / n_fill
                    mp0 = sum(r[f"ret0_{N}"] for r in filled) / n_fill
                miss = [r for r in sub_all
                        if not r["fills"][fk]["ok"] and r[f"ret0_{N}"] is not None]
                if miss:
                    mmiss = sum(r[f"ret0_{N}"] for r in miss) / len(miss)
                # 逐日池化：未成交记 0（资金闲置），与「直接追高」逐日对比
                byd_fill = collections.defaultdict(list)
                for r in filled:
                    byd_fill[r["date"]].append(r["fills"][fk][f"ret1_{N}"])
                egs = []
                for d in sorted(byd_all):
                    if not byd_fill.get(d):
                        continue
                    pool_d = sum(byd_fill[d]) / len(byd_all[d])
                    p0_d = sum(byd_all[d]) / len(byd_all[d])
                    egs.append(pool_d - p0_d)
                delta = sum(egs) / len(egs) if egs else None
                r3d = G._boot_pos(egs, boot=a.boot) if len(egs) >= 3 else 0.0
                net_pool = (fill_rate / 100.0) * m1 if m1 is not None else None
                print(f"      低吸{x}%：成交率 {fill_rate:5.1f}%  成交后均值 "
                      + (f"{m1:+.3f}%" if m1 is not None else "—")
                      + (f"（同样本追高 {mp0:+.3f}% → 买点改善 {m1-mp0:+.3f}pp）"
                         if (m1 is not None and mp0 is not None) else "")
                      + (f" | 未成交组追高 {mmiss:+.3f}%" if mmiss is not None else ""))
                if delta is not None:
                    print(f"               池化净期望 {net_pool:+.3f}% vs 直接追高 {m0:+.3f}%"
                          f"  → **{delta:+.3f}pp**  R3={r3d:.1f}%")
                ent["levels"][fk] = {
                    "fill_rate": round(fill_rate, 1), "n_fill": n_fill,
                    "wr1": round(w1, 1) if w1 is not None else None,
                    "mean1": round(m1, 3) if m1 is not None else None,
                    "p0_on_fill": round(mp0, 3) if mp0 is not None else None,
                    "improve_pp": round(m1 - mp0, 3) if (m1 is not None and mp0 is not None) else None,
                    "miss_p0": round(mmiss, 3) if mmiss is not None else None,
                    "net_pool": round(net_pool, 3) if net_pool is not None else None,
                    "net_p0": round(m0, 3),
                    "delta_pp": round(delta, 3) if delta is not None else None,
                    "r3": round(r3d, 1),
                }
            entry["holds"][f"N{N}"] = ent
        out_sig[name] = entry
    res["signals"] = out_sig

    # ---------------- 结论 ----------------
    print("\n=== 结论 ===")
    ok_any = []
    for name, e in out_sig.items():
        if not e.get("holds"):
            continue
        for N, ent in e["holds"].items():
            for x, lv in ent["levels"].items():
                if lv.get("delta_pp") is None:
                    continue
                # 判定低吸值得做，需同时满足：
                #   ① 池化净期望为正  ② 严格优于「直接追高」  ③ 逐日 R3 ≥ 95%
                if lv["net_pool"] is not None and lv["net_pool"] > 0 \
                        and lv["delta_pp"] > 0 and lv["r3"] >= 95.0:
                    ok_any.append((name, N, x, lv))
    if ok_any:
        print("   同时满足 ①池化净期望>0 ②优于追高 ③R3≥95% 的低吸组合：")
        for name, N, x, lv in ok_any:
            print(f"     {name} {N} 低吸{x}%  成交率{lv['fill_rate']}% "
                  f"池化净{lv['net_pool']:+.3f}% 比追高{lv['delta_pp']:+.3f}pp R3={lv['r3']}%")
    else:
        print("   → **无任何「信号 × 低吸档 × 持有期」组合能同时满足三条**")
        print("   → 判定：低吸不产生增量收益 —— 上涨率越高的票，越不会跌到你的挂单价上；")
        print("     能低吸到的，正是信号已经失效的那部分（逆向选择），错过的收益大于买价的改善")
    res["ok_combos"] = [{"sig": s, "hold": N, "dip": x, **lv} for s, N, x, lv in ok_any]

    outp = os.path.join(HERE, f"_dip_probe_{DS}.json")
    with open(outp, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    print(f"\n[out] {outp}")


if __name__ == "__main__":
    main()
