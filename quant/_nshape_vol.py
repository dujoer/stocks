#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""N字形 · 成交量特征预测力诊断（2026-10-24 用户方向：量能是预测参数，不是闸门）

对 60 个 as-of 日的 hb_pos 信号全集，提取**纯量能特征**（仅用 ≤as-of 根数据，
无未来函数），逐特征做五分位桶分析：检验前向首触（+10/-8/10 与 +6/-8/10）
收益/胜率是否随特征单调变化——单调才有预测力，不单调只是噪声。

特征全部来自 _txk 缓存 bar 的 volume 字段（ shares ）：
  contr_pb   缩量回调度 = 回撤段均量 / 涨停潮均量（越低=抛压衰竭越彻底）
  contr_pre  回撤段均量 / 涨停前5日均量
  vr5_20     5日均量 / 20日均量（量比 regime）
  vr_now     当日量 / 20日均量（转折日放量程度）
  vmin_ratio 回撤段最低量 / 20日均量（地量度）
  vseq       回撤尾3日均量 / 回撤初3日均量（量能递减）
  vdu        回撤段下跌日均量 / 上涨日均量（量价配合，低=健康）
  vtrend     近10日均量 / 前10日均量（量能趋势）
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
import _txk
import build_n_shape as NS
import build_n_shape_backtest as BT

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "n_shape")

TP_A, SL_A, H_A = 0.10, 0.08, 10   # 主口径（与闸门一致）
TP_B, SL_B, H_B = 0.06, 0.08, 10   # 敏感口径（低目标 → 高胜率需求）


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return (sum(xs) / len(xs)) if xs else None


def vol_features(code, bars, aidx, row):
    """从缓存 bar 提取量能特征。只用 bars[0:aidx+1]，无未来函数。"""
    zt_idx = aidx - (row.get("days_since_zt") or 0)
    if zt_idx < 2 or zt_idx >= aidx:
        return None
    vols = [b.get("volume") for b in bars[:aidx + 1]]
    if any(v is None for v in vols):
        return None
    highs = [b.get("high") for b in bars[:aidx + 1]]
    # 局部峰（涨停后区间最高价所在根）
    peak_idx = zt_idx
    for i in range(zt_idx, aidx + 1):
        if highs[i] is not None and highs[i] >= highs[peak_idx]:
            peak_idx = i
    pb = vols[peak_idx:aidx + 1]          # 峰后回撤段（含当日）
    if len(pb) < 2:
        return None
    surge = vols[max(0, zt_idx - 1):zt_idx + 1]     # 涨停潮（前一日+涨停日）
    pre = vols[max(0, zt_idx - 5):zt_idx]           # 涨停前 5 日
    v20 = _mean(vols[-20:])
    v10n = _mean(vols[-10:])
    v10p = _mean(vols[-20:-10])
    if not v20 or not surge or v20 <= 0:
        return None
    # 回撤段量价配合：下跌日均量 / 上涨日均量
    ups, downs = [], []
    for i in range(peak_idx, aidx + 1):
        if i == 0:
            continue
        c, p = bars[i].get("last"), bars[i - 1].get("last")
        if c is None or p is None:
            continue
        (ups if c >= p else downs).append(vols[i])
    f = {
        "contr_pb": _mean(pb) / _mean(surge),
        "vr5_20": _mean(vols[-5:]) / v20,
        "vr_now": vols[-1] / v20,
        "vmin_ratio": (min(pb) / v20) if pb else None,
        "vseq": (_mean(pb[-3:]) / _mean(pb[:3])) if len(pb) >= 6 else None,
        "vdu": (_mean(downs) / _mean(ups)) if ups and downs else None,
        "vtrend": (v10n / v10p) if v10p else None,
        "pb_days": len(pb),
    }
    if pre:
        f["contr_pre"] = _mean(pb) / _mean(pre)
    return f


def agg_ft(rows, ftkey):
    n = len(rows)
    if n == 0:
        return None
    wins = [r for r in rows if r[ftkey]["win"]]
    rets = [r[ftkey]["ret"] for r in rows]
    wp = sum(r[ftkey]["ret"] for r in wins) / len(wins) if wins else 0.0
    lp = sum(r[ftkey]["ret"] for r in rows if not r[ftkey]["win"]) / max(1, n - len(wins))
    return {"n": n, "win": round(len(wins) / n * 100, 2),
            "avg": round(sum(rets) / n, 3), "aw": round(wp, 3), "al": round(lp, 3),
            "pl": round(abs(wp / lp), 2) if lp else None}


def quintile_report(rows, feat, ftkey, label):
    """单特征五分位：Q1=特征值最低组。返回各组统计 + 单调性判断。"""
    vals = [(r["vf"][feat], r) for r in rows if r["vf"].get(feat) is not None]
    if len(vals) < 50:
        return None
    vals.sort(key=lambda x: x[0])
    k = len(vals) // 5
    groups = []
    for qi in range(5):
        seg = vals[qi * k:(qi + 1) * k] if qi < 4 else vals[4 * k:]
        a = agg_ft([r for _v, r in seg], ftkey)
        if a:
            a["q"] = qi + 1
            groups.append(a)
    if len(groups) < 5:
        return None
    wins = [g["win"] for g in groups]
    avgs = [g["avg"] for g in groups]
    mono_w = all(wins[i] <= wins[i + 1] for i in range(4)) or all(wins[i] >= wins[i + 1] for i in range(4))
    mono_a = all(avgs[i] <= avgs[i + 1] for i in range(4)) or all(avgs[i] >= avgs[i + 1] for i in range(4))
    return {"label": label, "groups": groups,
            "mono_win": bool(mono_w), "mono_avg": bool(mono_a),
            "spread_win": round(max(wins) - min(wins), 2),
            "spread_avg": round(max(avgs) - min(avgs), 3)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None)
    ap.add_argument("--asof", type=int, default=60)
    a = ap.parse_args()
    D = a.date or NS.latest_date()
    print("=== N字形 · 量能特征预测力诊断 · 数据日 %s · as-of %d 日 ===" % (D, a.asof))

    try:
        _txk.set_asof(D)
    except Exception:
        pass
    cache = _txk.load()
    name_map = NS.load_name_map(D)
    name2sw2 = NS.load_name2sw2()
    ind_map, cl = NS.load_hot_maps()
    w52 = NS.load_52w_cache(cache)
    asof_dates = BT.pick_asof_dates(cache, n=a.asof, fwd=BT.FWD)
    print("回测日 %d 个：%s ~ %s" % (len(asof_dates), asof_dates[0], asof_dates[-1]))

    rows = []
    for d in asof_dates:
        day = NS.gen_signals_asof(cache, d, name_map)
        NS.attach_attr(day, name2sw2, ind_map, cl, w52)
        for r in day:
            if not BT.is_hb_pos(r):
                continue
            raw = {k: v for k, v in r.items() if k != "ft"}
            fa = BT.fwd_first_touch(cache, raw, TP_A, SL_A, H_A)
            fb = BT.fwd_first_touch(cache, raw, TP_B, SL_B, H_B)
            if not fa or not fb:
                continue
            vf = vol_features(r["code"], cache[r["code"]], r["asof_idx"], r)
            if not vf:
                continue
            r.update({"date": d, "ftA": fa, "ftB": fb, "vf": vf})
            rows.append(r)
    print("hb_pos 带量能特征样本：%d 条" % len(rows))
    ba, bb = agg_ft(rows, "ftA"), agg_ft(rows, "ftB")
    print("基准 +10/-8/10：n=%d 胜率=%.2f%% 均=%+.3f%% 盈亏比=%s" % (ba["n"], ba["win"], ba["avg"], ba["pl"]))
    print("基准 +6/-8/10 ：n=%d 胜率=%.2f%% 均=%+.3f%% 盈亏比=%s" % (bb["n"], bb["win"], bb["avg"], bb["pl"]))

    feats = [("contr_pb", "缩量回调度↓"), ("contr_pre", "回撤/涨停前量比↓"),
             ("vr5_20", "5日/20日量比"), ("vr_now", "当日量比"),
             ("vmin_ratio", "地量度↓"), ("vseq", "尾/初段量能比↓"),
             ("vdu", "跌日/涨日量比↓"), ("vtrend", "近10日/前10日量比")]
    report = {"date": D, "asof_range": [asof_dates[0], asof_dates[-1]],
              "n": len(rows), "base": {"+10/-8/10": ba, "+6/-8/10": bb},
              "quintiles": {}}
    for ftkey, tag in (("ftA", "+10/-8/10"), ("ftB", "+6/-8/10")):
        print("\n########## 前向口径 %s ##########" % tag)
        for feat, lab in feats:
            rep = quintile_report(rows, feat, ftkey, lab)
            if not rep:
                print("  %-14s 样本不足" % lab)
                continue
            gs = rep["groups"]
            print("  %-14s Q1→Q5 胜率 %s｜均收益 %s｜单调(胜率)%s 单调(收益)%s 极差=%.1fpp"
                  % (lab, "/".join("%.1f" % g["win"] for g in gs),
                     "/".join("%+.2f" % g["avg"] for g in gs),
                     "✓" if rep["mono_win"] else "✗",
                     "✓" if rep["mono_avg"] else "✗", rep["spread_win"]))
            report["quintiles"]["%s|%s" % (tag, feat)] = rep

    os.makedirs(OUT_DIR, exist_ok=True)
    out = os.path.join(OUT_DIR, "vol_diag_%s.json" % D.replace("-", ""))
    json.dump(report, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1, sort_keys=True)
    print("\n存档：%s" % out)
    print("注：五分位为描述性统计；预测力需 Q1→Q5 单调且极差显著，再进 walk-forward 与 canonical 闸门。")


if __name__ == "__main__":
    main()
