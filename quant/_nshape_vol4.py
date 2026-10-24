#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""N字形 · 量能模型决胜验证 v2（2026-10-24）—— 修正 sel/ctrl 口径

v1 三处 bug（edge_stats 的 sel 误传全集 → edge 恒 0）：训练选参 / OOS 合并 /
随机对照。本版统一 canonical 模式：rows=当日全集（对照域），sel_fn=id 集合标记子集。

流程：
  1) 每折：训练段中位数插补 → 逻辑回归（vol_rich 9 特征）
  2) 折内选参：对每个 (TP,SL,H)，全训练行算 ft，top20% 标记 → edge_stats(训练全集, sel, ALL)
  3) 测试段：冻结模型+参数，top20% 标记 → edge_stats(测试全集, sel, ALL)
  4) OOS 合并：两折测试行并集 → edge/R3/loo/前后半
  5) 随机对照：每日从全集抽同条数 → edge_stats(全集, 抽样id, ALL) 40 次
"""
import argparse
import json
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _txk
import build_n_shape as NS
import build_n_shape_backtest as BT
import _gate_common as GC
from _nshape_vol import agg_ft
from _nshape_vol3 import rich_vol_features, logistic_fit, logistic_pred

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "n_shape")
BOOT = 800
COST_PP = 0.15
PARAM_GRID = [(tp, sl, h) for tp in (0.04, 0.06, 0.08, 0.10, 0.12)
              for sl in (0.06, 0.08, 0.10) for h in (5, 10)]
LOGF = ["v_turn", "v_surge", "v_peak", "obv_slope", "v_ud3", "v_reb",
        "vseq", "vr_now", "vtrend"]


def xvec(r, feats, med):
    out = []
    for f in feats:
        v = r["vf"].get(f)
        if v is None:
            v = med[f]
        if f in ("v_turn", "v_surge", "v_peak", "v_ud3", "v_reb",
                 "vseq", "vr_now", "vtrend"):
            out.append(math.log(max(1e-6, float(v))))
        else:
            out.append(float(v))
    return out


def edge_sel(all_rows, chosen):
    """canonical：全集为对照域，chosen=id 集合。"""
    return GC.edge_stats(all_rows, lambda r: id(r) in chosen, lambda r: True, name="sel")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None)
    ap.add_argument("--asof", type=int, default=60)
    ap.add_argument("--step", type=int, default=10, help="滚动步长（交易日）；5=更多折")
    a = ap.parse_args()
    D = a.date or NS.latest_date()
    print("=== N字形 · 量能决胜 v2 · 数据日 %s · as-of %d ===" % (D, a.asof))

    try:
        _txk.set_asof(D)
    except Exception:
        pass
    cache = _txk.load()
    name_map = NS.load_name_map(D)
    name2sw2 = NS.load_name2sw2()
    ind_map, cl = NS.load_hot_maps()
    w52 = NS.load_52w_cache(cache)
    dates = BT.pick_asof_dates(cache, n=a.asof, fwd=BT.FWD)

    rows = []
    for d in dates:
        day = NS.gen_signals_asof(cache, d, name_map)
        NS.attach_attr(day, name2sw2, ind_map, cl, w52)
        for r in day:
            if not BT.is_hb_pos(r):
                continue
            raw = {k: v for k, v in r.items() if k != "ft"}
            fa = BT.fwd_first_touch(cache, raw, 0.10, 0.08, 10)
            fb = BT.fwd_first_touch(cache, raw, 0.06, 0.08, 10)
            if not fa or not fb:
                continue
            vf = rich_vol_features(r["code"], cache[r["code"]], r["asof_idx"], r)
            if not vf:
                continue
            r.update({"date": d, "ftA": fa, "ftB": fb, "vf": vf,
                      "winA": bool(fa["win"]), "retA": fa["ret"],
                      "pnl": fa["ret"] * 100.0, "win": bool(fa["win"])})
            rows.append(r)
    ba = agg_ft(rows, "ftA")
    bb = agg_ft(rows, "ftB")
    print("全量样本 %d 条｜%s ~ %s" % (len(rows), rows[0]["date"], rows[-1]["date"]))
    print("基准 A：n=%d 胜率=%.2f%% 均=%+.3f%%｜B：n=%d 胜率=%.2f%% 均=%+.3f%%"
          % (ba["n"], ba["win"], ba["avg"], bb["n"], bb["win"], bb["avg"]))

    step = a.step
    folds = []
    i = 0
    while i + 50 <= len(dates):
        folds.append((dates[i:i + 40], dates[i + 40:i + 50]))
        i += step

    out = {"date": D, "asof": a.asof, "n": len(rows), "boot": BOOT,
           "base": {"A": ba, "B": bb}, "folds": [], "oos": {}, "random_control": {}}
    te_all = []          # 全部测试行（跨折，带 _top 标记）
    for fi, (tr, te) in enumerate(folds, 1):
        trs = set(tr)
        tr_rows = [r for r in rows if r["date"] in trs]
        te_rows = [r for r in rows if r["date"] not in trs and te[0] <= r["date"] <= te[-1]]
        med = {}
        for f in LOGF:
            vs = sorted(r["vf"][f] for r in tr_rows if r["vf"].get(f) is not None)
            med[f] = vs[len(vs) // 2] if vs else 1.0
        model = logistic_fit([xvec(r, LOGF, med) for r in tr_rows],
                             [1 if r["winA"] else 0 for r in tr_rows])
        tr_scored = sorted(tr_rows, key=lambda r: logistic_pred(model, xvec(r, LOGF, med)),
                           reverse=True)
        ktr = max(1, len(tr_rows) // 5)
        top_tr_ids = set(id(r) for r in tr_scored[:ktr])
        # ---- 折内选参（canonical：训练全集为对照域）----
        best = None
        for tp, sl, h in PARAM_GRID:
            for r in tr_rows:
                raw = {kk: vv for kk, vv in r.items() if kk not in ("ft", "ftA", "ftB", "_ft_p")}
                r["_ft_p"] = BT.fwd_first_touch(cache, raw, tp, sl, h)
            tr_ok = [r for r in tr_rows if r.get("_ft_p")]
            for r in tr_ok:
                r["pnl"] = r["_ft_p"]["ret"] * 100.0
                r["win"] = bool(r["_ft_p"]["win"])
            st = edge_sel(tr_ok, top_tr_ids)
            e = st.get("edge")
            if e is None:
                continue
            if best is None or e > best[0]:
                best = (e, tp, sl, h, st.get("r3"), len(top_tr_ids))
        _e, tp, sl, h, _r3, _kn = best
        # 还原 A 口径 pnl/win（后续统计用）
        for r in rows:
            if "_ft_p" in r:
                r["pnl"] = r["ftA"]["ret"] * 100.0
                r["win"] = bool(r["ftA"]["win"])
                del r["_ft_p"]
        # ---- 测试段：冻结 ----
        te_scored = sorted(te_rows, key=lambda r: logistic_pred(model, xvec(r, LOGF, med)),
                           reverse=True)
        kte = max(1, len(te_rows) // 5)
        top_te = te_scored[:kte]
        top_te_ids = set(id(r) for r in top_te)
        for r in top_te:
            r["_top"] = True
        subA, subB = [], []
        for r in top_te:
            raw = {kk: vv for kk, vv in r.items() if kk not in ("ft", "ftA", "ftB", "_top")}
            fta = BT.fwd_first_touch(cache, raw, tp, sl, h)
            ftb = BT.fwd_first_touch(cache, raw, 0.06, 0.08, 10)
            if fta:
                subA.append({"ft": fta})
            if ftb:
                subB.append({"ft": ftb})
        aA = agg_ft(subA, "ft")
        aB = agg_ft(subB, "ft")
        st = edge_sel(te_rows, top_te_ids)
        hv = GC.halves(st.get("days", []))
        rec = {"fold": fi, "train": [tr[0], tr[-1]], "test": [te[0], te[-1]],
               "param": "+%g/-%g/%d" % (tp * 100, sl * 100, h),
               "train_edge": round(_e, 3), "train_n": _kn,
               "test_n": aA["n"] if aA else 0,
               "test_winA": aA["win"] if aA else None, "test_avgA": aA["avg"] if aA else None,
               "test_plA": aA["pl"] if aA else None,
               "test_winB": aB["win"] if aB else None, "test_avgB": aB["avg"] if aB else None,
               "test_edge": st.get("edge"), "test_r3": st.get("r3"),
               "test_loo_min": st.get("loo_min"),
               "test_half1": hv[0]["edge"] if len(hv) > 0 else None,
               "test_half2": hv[1]["edge"] if len(hv) > 1 else None}
        out["folds"].append(rec)
        te_all.extend(te_rows)
        print("fold%d 选 +%g/-%g/%d（train edge %+.3f, n=%d）→ 测试 n=%d 胜率A=%s 均A=%+.3f 盈亏比A=%s 胜率B=%s｜edge=%s R3=%s loo=%s 半1=%s 半2=%s"
              % (fi, tp * 100, sl * 100, h, _e, _kn, rec["test_n"],
                 ("%.2f%%" % rec["test_winA"]) if rec["test_winA"] else "NA",
                 rec["test_avgA"] or 0, rec["test_plA"] or "NA",
                 ("%.2f%%" % rec["test_winB"]) if rec["test_winB"] else "NA",
                 ("%+.3f" % rec["test_edge"]) if rec["test_edge"] is not None else "NA",
                 ("%.1f" % rec["test_r3"]) if rec["test_r3"] is not None else "NA",
                 ("%+.3f" % rec["test_loo_min"]) if rec["test_loo_min"] is not None else "NA",
                 ("%+.3f" % rec["test_half1"]) if rec["test_half1"] is not None else "NA",
                 ("%+.3f" % rec["test_half2"]) if rec["test_half2"] is not None else "NA"))

    # ---- OOS 合并（canonical；步长<10 时折间测试窗重叠 → 按 id 去重）----
    print("\n---- OOS 合并（两折测试行并集，canonical）----")
    uniq = {}
    for r in te_all:
        uniq[id(r)] = r
    te_all = list(uniq.values())
    top_ids = set(id(r) for r in te_all if r.get("_top"))
    n_top = len(top_ids)
    st = edge_sel(te_all, top_ids)
    hv = GC.halves(st.get("days", []))
    h1 = hv[0]["edge"] if len(hv) > 0 else None
    h2 = hv[1]["edge"] if len(hv) > 1 else None
    tops = [r for r in te_all if r.get("_top")]
    wA = sum(1 for r in tops if r["winA"]) / max(1, n_top) * 100
    wB = sum(1 for r in tops if r["ftB"]["win"]) / max(1, n_top) * 100
    print("OOS top n=%d｜池化胜率A=%.2f%%（基准%.2f）胜率B=%.2f%%（基准%.2f）"
          % (n_top, wA, ba["win"], wB, bb["win"]))
    print("canonical：edge=%spp R3=%s loo_min=%s loo_max=%s 前半=%s 后半=%s"
          % (("%+.3f" % st["edge"]) if st.get("edge") is not None else "NA",
             ("%.1f" % st["r3"]) if st.get("r3") is not None else "NA",
             ("%+.3f" % st["loo_min"]) if st.get("loo_min") is not None else "NA",
             ("%+.3f" % st["loo_max"]) if st.get("loo_max") is not None else "NA",
             ("%+.3f" % h1) if h1 is not None else "NA",
             ("%+.3f" % h2) if h2 is not None else "NA"))
    out["oos"] = {"n_top": n_top, "winA": round(wA, 2), "winB": round(wB, 2),
                  "edge": st.get("edge"), "r3": st.get("r3"),
                  "loo_min": st.get("loo_min"), "loo_max": st.get("loo_max"),
                  "half1": h1, "half2": h2}

    # ---- 随机对照（canonical：全集为对照域）----
    rng = random.Random(20261024)
    print("\n---- 随机对照：每日从当日全集抽同条数，40 次 ----")
    by_day = {}
    for r in te_all:
        by_day.setdefault(r["date"], []).append(r)
    hit = 0
    N_RAND = 40
    for _ in range(N_RAND):
        chosen = set()
        for d, dayrows in by_day.items():
            k = sum(1 for r in dayrows if r.get("_top"))
            if k <= 0:
                continue
            if len(dayrows) <= k:
                chosen.update(id(r) for r in dayrows)
            else:
                chosen.update(id(r) for r in rng.sample(dayrows, k))
        st_ = edge_sel(te_all, chosen)
        if (st_.get("edge") or 0) > COST_PP and (st_.get("r3") or 0) >= 95:
            hit += 1
    rate = hit / N_RAND * 100
    print("随机达标 %d/%d = %.1f%%" % (hit, N_RAND, rate))
    out["random_control"] = {"rand_n": N_RAND, "hit": hit, "hit_rate_pct": round(rate, 2)}

    # ---- 判定 ----
    ok = (st.get("edge") or 0) > COST_PP and (st.get("r3") or 0) >= 95 \
        and (st.get("loo_min") or -9) > 0 and (h1 or -9) > 0 and (h2 or -9) > 0
    print("\n主判据（OOS）：%s" % ("PASS" if ok else "FAIL"))
    if ok and rate <= 5.0:
        print("随机对照 %.1f%% ≤ 5%% → 特异性通过" % rate)
        out["licensed"] = True
    elif ok:
        print("随机对照 %.1f%% > 5%% → 疑多重比较噪声，不出票" % rate)
        out["licensed"] = False
    else:
        print("按铁律不出票、不放宽阈值。")
        out["licensed"] = False

    os.makedirs(OUT_DIR, exist_ok=True)
    outp = os.path.join(OUT_DIR, "vol_final2_%s_step%d.json" % (D.replace("-", ""), a.step))
    json.dump(out, open(outp, "w", encoding="utf-8"), ensure_ascii=False, indent=1, sort_keys=True)
    print("\n存档：%s" % outp)


if __name__ == "__main__":
    main()
