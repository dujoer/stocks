#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""N字形 · 量能特征扩充 + 分组 walk-forward 预测力对比（2026-10-24）

承接 _nshape_vol2.py：基础量能 OOS AUC 0.56~0.59（真实但温和），且合成评分方向
翻转提示「缩量」与「放量拐头」被混同。本脚本：

  1) 扩充量能构造（放量拐头度/涨停潮强度/峰位量/OBV 斜率/近3日涨跌量比）
  2) 四组特征 walk-forward 逻辑回归对比 OOS AUC：
       price  /  vol_basic  /  vol_rich  /  all
  3) 每组在测试段按预测概率取前 20%，报 OOS 胜率/均收益/逐日平衡 edge/R3
  4) 参数网格（对最优组的前 20% 子集）—— 看有没有参数组合把胜率推过盈亏平衡

铁律：折划分事前冻结（同 vol2）；boot 固定 800；随机对照兜底。
"""
import argparse
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _txk
import build_n_shape as NS
import build_n_shape_backtest as BT
import _gate_common as GC
from _nshape_vol import vol_features, agg_ft

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "n_shape")
TP_A, SL_A, H_A = 0.10, 0.08, 10
TP_B, SL_B, H_B = 0.06, 0.08, 10
BOOT = 800
COST_PP = 0.15


def rich_vol_features(code, bars, aidx, row):
    """扩充量能特征。只用 bars[0:aidx+1]。"""
    vf = vol_features(code, bars, aidx, row)
    if not vf:
        return None
    zt_idx = aidx - (row.get("days_since_zt") or 0)
    if zt_idx < 6:
        return None
    vols = [b.get("volume") for b in bars[:aidx + 1]]
    closes = [b.get("last") for b in bars[:aidx + 1]]
    highs = [b.get("high") for b in bars[:aidx + 1]]
    if any(v is None for v in vols) or any(c is None for c in closes):
        return None
    peak_idx = zt_idx
    for i in range(zt_idx, aidx + 1):
        if highs[i] is not None and highs[i] >= highs[peak_idx]:
            peak_idx = i
    v20 = sum(vols[-20:]) / 20.0
    if v20 <= 0:
        return None
    pb = vols[peak_idx:aidx + 1]
    pb_avg = sum(pb) / len(pb)
    # 放量拐头度：近3日最大量 / 回撤段均量（转折是否放量）
    v_turn = max(vols[-3:]) / pb_avg if pb_avg > 0 else None
    # 涨停潮强度：涨停日量 / 20日均量
    v_surge = vols[zt_idx] / v20
    # 峰位量比：局部峰根量 / 20日均量（峰位放量=派发风险）
    v_peak = vols[peak_idx] / v20
    # OBV 斜率（回撤段）：净流入量 / 回撤段总量
    obv = 0.0
    tot = 0.0
    for i in range(peak_idx + 1, aidx + 1):
        if closes[i] is None or closes[i - 1] is None:
            continue
        d = 1 if closes[i] >= closes[i - 1] else -1
        obv += d * vols[i]
        tot += vols[i]
    obv_slope = obv / tot if tot > 0 else None
    # 近3日涨日量 / 跌日量
    up3, dn3 = [], []
    for i in range(max(1, aidx - 2), aidx + 1):
        if closes[i] is None or closes[i - 1] is None:
            continue
        (up3 if closes[i] >= closes[i - 1] else dn3).append(vols[i])
    v_ud3 = (sum(up3) / len(up3)) / (sum(dn3) / len(dn3)) if up3 and dn3 else None
    # 地量后再放量：回撤段最低量位置之后 3 日均量 / 之前 3 日均量
    if len(pb) >= 8:
        imin = pb.index(min(pb))
        if imin >= 3 and len(pb) - imin >= 3:
            v_reb = (sum(pb[imin + 1:imin + 4]) / 3.0) / (sum(pb[imin - 3:imin]) / 3.0)
        else:
            v_reb = None
    else:
        v_reb = None
    vf.update({"v_turn": v_turn, "v_surge": v_surge, "v_peak": v_peak,
               "obv_slope": obv_slope, "v_ud3": v_ud3, "v_reb": v_reb})
    return vf


def logistic_fit(X, y, l2=1.0, iters=300, lr=0.5):
    n, p = len(X), len(X[0])
    mu = [sum(row[j] for row in X) / n for j in range(p)]
    sd = []
    for j in range(p):
        v = sum((row[j] - mu[j]) ** 2 for row in X) / n
        sd.append(math.sqrt(v) if v > 1e-12 else 1.0)
    Xs = [[(row[j] - mu[j]) / sd[j] for j in range(p)] for row in X]
    w = [0.0] * p
    b = 0.0
    for _ in range(iters):
        gw = [0.0] * p
        gb = 0.0
        for i in range(n):
            z = b + sum(w[j] * Xs[i][j] for j in range(p))
            pr = 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, z))))
            e = pr - y[i]
            for j in range(p):
                gw[j] += e * Xs[i][j]
            gb += e
        for j in range(p):
            w[j] -= lr * (gw[j] / n + l2 * w[j] / n)
        b -= lr * gb / n
    return w, b, mu, sd


def logistic_pred(model, x):
    w, b, mu, sd = model
    z = b + sum(w[j] * (x[j] - mu[j]) / sd[j] for j in range(len(w)))
    return 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, z))))


def auc(pairs):
    pos = [s for s, y in pairs if y == 1]
    neg = [s for s, y in pairs if y == 0]
    if not pos or not neg:
        return None
    allv = sorted(pairs, key=lambda t: t[0])
    ranks = {}
    i = 0
    while i < len(allv):
        j = i
        while j < len(allv) and allv[j][0] == allv[i][0]:
            j += 1
        r = (i + j - 1) / 2.0 + 1
        for k in range(i, j):
            ranks[k] = r
        i = j
    rsum = sum(ranks[k] for k, (s, y) in enumerate(allv) if y == 1)
    n1, n0 = len(pos), len(neg)
    return (rsum - n1 * (n1 + 1) / 2.0) / (n1 * n0)


GROUPS = {
    "price": ["dist_local_peak", "days_since_zt", "pos_pctile", "pullback_pct", "chg_pct"],
    "vol_basic": ["vseq", "vr_now", "vtrend", "vr5_20", "vmin_ratio", "contr_pb"],
    "vol_rich": ["v_turn", "v_surge", "v_peak", "obv_slope", "v_ud3", "v_reb",
                 "vseq", "vr_now", "vtrend"],
    "all": ["dist_local_peak", "days_since_zt", "pos_pctile", "pullback_pct", "chg_pct",
            "v_turn", "v_surge", "v_peak", "obv_slope", "v_ud3", "v_reb",
            "vseq", "vr_now", "vtrend", "vr5_20", "vmin_ratio", "contr_pb"],
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None)
    ap.add_argument("--asof", type=int, default=60)
    a = ap.parse_args()
    D = a.date or NS.latest_date()
    print("=== N字形 · 量能扩充 + 分组 WF 预测力 · 数据日 %s · as-of %d ===" % (D, a.asof))

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
            fa = BT.fwd_first_touch(cache, raw, TP_A, SL_A, H_A)
            fb = BT.fwd_first_touch(cache, raw, TP_B, SL_B, H_B)
            if not fa or not fb:
                continue
            vf = rich_vol_features(r["code"], cache[r["code"]], r["asof_idx"], r)
            if not vf:
                continue
            r.update({"date": d, "ftA": fa, "ftB": fb, "vf": vf,
                      "winA": bool(fa["win"]), "retA": fa["ret"],
                      "pnl": fa["ret"] * 100.0, "win": bool(fa["win"])})
            rows.append(r)
    print("样本 %d 条｜%s ~ %s" % (len(rows), rows[0]["date"], rows[-1]["date"]))
    ba = agg_ft(rows, "ftA")
    print("基准 +10/-8/10：n=%d 胜率=%.2f%% 均=%+.3f%%" % (ba["n"], ba["win"], ba["avg"]))

    def xvec(r, feats):
        out = []
        for f in feats:
            v = r["vf"].get(f, r.get(f))
            if v is None:
                return None
            if f in ("days_since_zt",):
                out.append(float(v))
            elif f in ("contr_pb", "v_turn", "v_surge", "v_peak", "v_ud3", "v_reb",
                       "vseq", "vr_now", "vtrend", "vr5_20", "vmin_ratio"):
                out.append(math.log(max(1e-6, float(v))))
            else:
                out.append(float(v) / 100.0 if abs(float(v)) > 1.5 else float(v))
        return out

    def complete(r, feats):
        return all((r["vf"].get(f) if f in r["vf"] else r.get(f)) is not None for f in feats)

    # 折划分（同 vol2：冻结）
    step = 10
    folds = []
    i = 0
    while i + 50 <= len(dates):
        folds.append((dates[i:i + 40], dates[i + 40:i + 50]))
        i += step

    out = {"date": D, "asof": a.asof, "n": len(rows), "boot": BOOT,
           "base": ba, "groups": {}}

    for gname, feats in GROUPS.items():
        print("\n########## 特征组 [%s]（%d 特征）##########" % (gname, len(feats)))
        grp = {"feats": feats, "folds": []}
        oos_rows = []
        for fi, (tr, te) in enumerate(folds, 1):
            trs = set(tr)
            tr_rows = [r for r in rows if r["date"] in trs and complete(r, feats)]
            te_rows = [r for r in rows if r["date"] not in trs
                       and te[0] <= r["date"] <= te[-1] and complete(r, feats)]
            if len(tr_rows) < 60 or len(te_rows) < 30:
                print("  fold%d 样本不足（tr=%d te=%d）" % (fi, len(tr_rows), len(te_rows)))
                continue
            model = logistic_fit([xvec(r, feats) for r in tr_rows],
                                 [1 if r["winA"] else 0 for r in tr_rows])
            pairs = []
            for r in te_rows:
                p = logistic_pred(model, xvec(r, feats))
                r2 = dict(r)
                r2["_p"] = p
                oos_rows.append(r2)
                pairs.append((p, 1 if r["winA"] else 0))
            a_ = auc(pairs)
            # 测试段内按预测概率前 20%（打 _top 标记，edge_stats 用全集+选择器）
            k = max(1, len(te_rows) // 5)
            top = sorted(te_rows, key=lambda r: logistic_pred(model, xvec(r, feats)),
                         reverse=True)[:k]
            for r in top:
                r["_top"] = True
            st = GC.edge_stats(te_rows, lambda r: r.get("_top"), lambda r: True, name="top20")
            at = agg_ft(top, "ftA")
            bt = agg_ft(top, "ftB")
            rec = {"fold": fi, "n_test": len(te_rows), "auc": round(a_, 4) if a_ else None,
                   "top_n": at["n"], "top_win": at["win"], "top_avg": at["avg"],
                   "topB_win": bt["win"],
                   "top_edge": st.get("edge"), "top_r3": st.get("r3")}
            grp["folds"].append(rec)
            print("  fold%d 测试n=%d AUC=%s｜前20%%: n=%d 胜率A=%.2f%% 均=%+.3f 胜率B=%.2f%% edge=%s R3=%s"
                  % (fi, rec["n_test"], rec["auc"], rec["top_n"], rec["top_win"],
                     rec["top_avg"], rec["topB_win"],
                     ("%+.3f" % rec["top_edge"]) if rec["top_edge"] is not None else "NA",
                     ("%.1f" % rec["top_r3"]) if rec["top_r3"] is not None else "NA"))
        # OOS 合并：各折 top20 汇总 + 全体按概率前20%（逐日平衡，全集为对照域）
        if oos_rows:
            pairs_all = [(r["_p"], 1 if r["winA"] else 0) for r in oos_rows]
            auc_all = auc(pairs_all)
            k = max(1, len(oos_rows) // 5)
            top_all = sorted(oos_rows, key=lambda r: r["_p"], reverse=True)[:k]
            for r in top_all:
                r["_top"] = True
            at = agg_ft(top_all, "ftA")
            bt = agg_ft(top_all, "ftB")
            st = GC.edge_stats(oos_rows, lambda r: r.get("_top"), lambda r: True, name="oos_top")
            grp["oos"] = {"n_oos": len(oos_rows), "auc": round(auc_all, 4) if auc_all else None,
                          "top_n": at["n"], "top_winA": at["win"], "top_avgA": at["avg"],
                          "top_plA": at["pl"], "top_winB": bt["win"], "top_avgB": bt["avg"],
                          "top_edge": st.get("edge"), "top_r3": st.get("r3")}
            print("  OOS 合并：n=%d AUC=%s｜前20%%: n=%d 胜率A=%.2f%%(基准%.2f) 均=%+.3f 盈亏比=%s 胜率B=%.2f%% edge=%s R3=%s"
                  % (grp["oos"]["n_oos"], grp["oos"]["auc"], grp["oos"]["top_n"],
                     grp["oos"]["top_winA"], ba["win"], grp["oos"]["top_avgA"],
                     grp["oos"]["top_plA"], grp["oos"]["top_winB"],
                     ("%+.3f" % grp["oos"]["top_edge"]) if grp["oos"]["top_edge"] is not None else "NA",
                     ("%.1f" % grp["oos"]["top_r3"]) if grp["oos"]["top_r3"] is not None else "NA"))
        out["groups"][gname] = grp

    # ---- 参数网格：vol_rich 组（OOS AUC 最优）前20% 子集 ----
    GRID_GROUP = "vol_rich"
    if GRID_GROUP in out["groups"] and out["groups"][GRID_GROUP].get("oos"):
        print("\n---- 参数网格（%s 组 OOS 前20%% 子集，描述性）----" % GRID_GROUP)
        # 重建该组 OOS 前20%（同一折划分与模型，复现概率）
        oos_rows = []
        feats = GROUPS[GRID_GROUP]
        for fi, (tr, te) in enumerate(folds, 1):
            trs = set(tr)
            tr_rows = [r for r in rows if r["date"] in trs and complete(r, feats)]
            te_rows = [r for r in rows if r["date"] not in trs
                       and te[0] <= r["date"] <= te[-1] and complete(r, feats)]
            if len(tr_rows) < 60 or len(te_rows) < 30:
                continue
            model = logistic_fit([xvec(r, feats) for r in tr_rows],
                                 [1 if r["winA"] else 0 for r in tr_rows])
            for r in te_rows:
                r2 = dict(r)
                r2["_p"] = logistic_pred(model, xvec(r, feats))
                oos_rows.append(r2)
        oos_rows.sort(key=lambda r: r["_p"], reverse=True)
        k = max(1, len(oos_rows) // 5)
        top_rows = oos_rows[:k]
        print("  %5s %5s %4s %5s %8s %8s %7s" % ("TP", "SL", "H", "n", "胜率%", "均收益%", "盈亏比"))
        for tp in (0.04, 0.06, 0.08, 0.10, 0.12):
            for sl in (0.06, 0.08, 0.10):
                for h in (5, 10):
                    sub = []
                    for r in top_rows:
                        raw = {kk: vv for kk, vv in r.items() if kk not in ("ft", "ftA", "ftB", "_p", "_top")}
                        ft = BT.fwd_first_touch(cache, raw, tp, sl, h)
                        if ft:
                            sub.append({"ft": ft})
                    a_ = agg_ft(sub, "ft")
                    if not a_:
                        continue
                    mark = ""
                    if a_["avg"] > 0.15 and a_["n"] >= 30:
                        mark = "  ← edge>0.15pp"
                    print("  %5g %5g %4d %5d %8.2f %8.2f %7s%s"
                          % (tp * 100, sl * 100, h, a_["n"], a_["win"], a_["avg"] * 100, a_["pl"], mark))
                    out["groups"][GRID_GROUP].setdefault("grid", {})["+%g/-%g/%d" % (tp * 100, sl * 100, h)] = a_

    os.makedirs(OUT_DIR, exist_ok=True)
    outp = os.path.join(OUT_DIR, "vol_groups_%s.json" % D.replace("-", ""))
    json.dump(out, open(outp, "w", encoding="utf-8"), ensure_ascii=False, indent=1, sort_keys=True)
    print("\n存档：%s" % outp)


if __name__ == "__main__":
    main()
