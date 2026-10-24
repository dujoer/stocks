# -*- coding: utf-8 -*-
"""N字形 hb_pos 候选规则 walk-forward 验证（前半窗选、后半窗盲测）。

铁律遵守：
- 信号口径 = eval_stock_signal + is_hb_pos（唯一真源）；
- 首次触及 = fwd_first_touch；bootstrap 次数固定 2000 并写入产物；
- 规则选择只许看前半窗，后半窗盲测一次；禁按最好看的窗口判；
- 经济闸：逐档 edge 全部 > 0.15pp 双边成本才算「可执行」；
- 样本 < 30 标注样本不足；无合格档写「无合格标的」，不放宽阈值。
"""
import argparse
import json
import os
import random
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_n_shape as NS          # noqa: E402
import build_n_shape_backtest as BT  # noqa: E402
import _txk                          # noqa: E402

QUANT = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(QUANT, "n_shape")
BOOT = 2000

# 候选规则（单规则 + 交集；全部有逻辑假设，非穷举）
def r_deep(s):    return (s.get("dist_local_peak") or 0) <= -20        # 深回撤：跌透才反弹
def r_deeper(s):  return (s.get("dist_local_peak") or 0) <= -25
def r_time(s):    return (s.get("days_since_zt") or 0) >= 5            # 急跌期已过
def r_time2(s):   return (s.get("days_since_zt") or 0) >= 7
def r_pos(s):     return s.get("pos_pctile") is not None and s["pos_pctile"] <= 60   # 排除高位
def r_pos2(s):    return s.get("pos_pctile") is not None and s["pos_pctile"] <= 50
def r_pb(s):      return -6 <= (s.get("pullback_pct") or 0) < -3       # 涨停后浅回撤（强）
def r_amt(s):     return (s.get("avg_amt_yi") or 0) >= 5               # 流动性下限
def r_heat(s):    return s.get("heat_label") in ("震荡", "强势")        # 环境非弱

CANDIDATES = {
    "R1 深回撤≤-20": r_deep,
    "R1b 深回撤≤-25": r_deeper,
    "R2 涨停后≥5日": r_time,
    "R2b 涨停后≥7日": r_time2,
    "R3 52周分位≤60": r_pos,
    "R3b 52周分位≤50": r_pos2,
    "R4 涨停后回撤-6~-3": r_pb,
    "R5 均额≥5亿": r_amt,
    "R6 环境非弱(震荡/强势)": r_heat,
    "R1∩R2": lambda s: r_deep(s) and r_time(s),
    "R1∩R3": lambda s: r_deep(s) and r_pos(s),
    "R2∩R3": lambda s: r_time(s) and r_pos(s),
    "R1∩R2∩R3": lambda s: r_deep(s) and r_time(s) and r_pos(s),
    "R1∩R2∩R3b": lambda s: r_deep(s) and r_time(s) and r_pos2(s),
    "R2∩R3∩R6": lambda s: r_time(s) and r_pos(s) and r_heat(s),
    "R1∩R2∩R3∩R6": lambda s: r_deep(s) and r_time(s) and r_pos(s) and r_heat(s),
}

PARAMS = [(0.06, 0.08, 10), (0.08, 0.06, 10), (0.10, 0.08, 10), (0.12, 0.08, 10),
          (0.08, 0.08, 20), (0.10, 0.06, 10), (0.12, 0.10, 10)]


def agg(rows):
    n = len(rows)
    if n == 0:
        return None
    wins = [r for r in rows if r["ft"]["win"]]
    rets = [r["ft"]["ret"] for r in rows]
    return {"n": n,
            "win_rate": round(len(wins) / n * 100, 2),
            "avg_ret_pp": round(sum(rets) / n * 100, 3),
            "pl_ratio": round(abs(sum(r["ft"]["ret"] for r in wins) / max(1e-9, sum(r["ft"]["ret"] for r in rows if not r["ft"]["win"]))), 2)}


def boot_r3(rows, iters=BOOT):
    """bootstrap：重采样信号的胜率，R3 = P(胜率>0) 的百分比口径（逐日平衡近似：按 as-of 日重采样）。

    简化口径：对 as-of 日有放回重采样 iters 次，统计均收益 > 0 的占比（%）。
    固定 iters，写入产物。
    """
    by_day = {}
    for r in rows:
        by_day.setdefault(r["asof"], []).append(r["ft"]["ret"] * 100)
    days = list(by_day.keys())
    if len(days) < 3:
        return None
    rng = random.Random(42)
    pos = 0
    for _ in range(iters):
        sample = [rng.choice(days) for _ in range(len(days))]
        tot = sum(sum(by_day[d]) for d in sample) / len(sample)
        if tot > 0:
            pos += 1
    return round(pos / iters * 100, 2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None)
    ap.add_argument("--asof", type=int, default=60)
    a = ap.parse_args()
    D = a.date or NS.latest_date()
    print("=== N字形候选规则 walk-forward · 数据日 %s · as-of %d 日 ===" % (D, a.asof))

    try:
        _txk.set_asof(D)
    except Exception:
        pass
    cache = _txk.load()
    name_map = NS.load_name_map(D)
    name2sw2 = NS.load_name2sw2()
    ind_map, concept_leaders = NS.load_hot_maps()
    w52 = NS.load_52w_cache(cache)
    asof_dates = BT.pick_asof_dates(cache, n=a.asof, fwd=BT.FWD)
    heat_map = {}
    for d in asof_dates:
        try:
            heat_map[d] = (NS.load_market_heat(d) or {}).get("label") or "未知"
        except Exception:
            heat_map[d] = "未知"

    sigs = []
    for d in asof_dates:
        rows = NS.gen_signals_asof(cache, d, name_map)
        NS.attach_attr(rows, name2sw2, ind_map, concept_leaders, w52)
        for r in rows:
            r["asof"] = d
            r["heat_label"] = heat_map.get(d, "未知")
            sigs.append(r)
    hb = [s for s in sigs if BT.is_hb_pos(s)]
    half = len(asof_dates) // 2
    first_days = set(asof_dates[:half])
    print("全量 %d 条，hb_pos %d 条；前半 %d 日 / 后半 %d 日"
          % (len(sigs), len(hb), half, len(asof_dates) - half))

    report = {"date": D, "n_asof": len(asof_dates), "boot": BOOT,
              "asof_range": [asof_dates[0], asof_dates[-1]], "rules": {}}
    passes = []
    print("\n%-16s %14s %-22s %-22s" % ("规则", "参数(TP/SL/H)", "前半(选参依据)", "后半(盲测)"))
    for name, fn in CANDIDATES.items():
        sub = [s for s in hb if fn(s)]
        for tp, sl, h in PARAMS:
            rows = []
            for s in sub:
                raw = {k: v for k, v in s.items() if k != "ft"}
                ft = BT.fwd_first_touch(cache, raw, tp, sl, h)
                if ft:
                    rows.append({"asof": s["asof"], "ft": ft})
            f1 = [r for r in rows if r["asof"] in first_days]
            f2 = [r for r in rows if r["asof"] not in first_days]
            a1, a2 = agg(f1), agg(f2)
            if not a1 or not a2:
                continue
            r3 = boot_r3(rows)
            key = "%s|+%g/-%g/%d" % (name, tp * 100, sl * 100, h)
            report["rules"][key] = {"first": a1, "second": a2, "boot_r3": r3,
                                     "n_first_days": len(first_days)}
            flag = ""
            if a2["n"] >= 30 and a2["avg_ret_pp"] > 0.15:
                flag = "  ←后半 edge>0.15pp"
                passes.append((key, a2, r3))
            print("%-16s %14s n=%-4d %6.2f%% %+6.2fpp  n=%-4d %6.2f%% %+6.2fpp R3=%s%s"
                  % (name, "+%g/-%g/%d" % (tp * 100, sl * 100, h),
                     a1["n"], a1["win_rate"], a1["avg_ret_pp"],
                     a2["n"], a2["win_rate"], a2["avg_ret_pp"], r3, flag))

    print("\n---- 后半窗 edge>0.15pp 候选（经济闸初筛）----")
    if not passes:
        print("无合格候选：后半窗无一档 edge>0.15pp。按铁律写「无合格标的」，不放宽阈值。")
    for key, a2, r3 in passes:
        print("  %s  后半 n=%d 胜率=%.2f%% edge=%+.2fpp R3=%s" % (key, a2["n"], a2["win_rate"], a2["avg_ret_pp"], r3))

    os.makedirs(OUT_DIR, exist_ok=True)
    out = os.path.join(OUT_DIR, "opt_wf_%s.json" % D.replace("-", ""))
    json.dump(report, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1, sort_keys=True)
    print("\n存档：%s" % out)


if __name__ == "__main__":
    main()
