#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""N字形 · 量能评分合成 + walk-forward + 随机对照（2026-10-24）

承接 _nshape_vol.py 的单特征诊断结论（无单特征全线单调，但尾部信号强）：
  vseq 尾/初段量能比↓（极差18.2pp）· vr_now 当日量比↓（均收益单调）·
  vtrend 近10日/前10日量比↓（+6口径全单调）—— 三者同向：缩量=好。

本脚本：
  1) 合成 vol_score = 三特征秩分位（反向）等权 0-100（连续评分，非闸门）
  2) vol_score 五分位 / 头尾20% 描述统计（双前向口径）
  3) 头20%档 canonical 逐日平衡 edge + R3（_gate_common.edge_stats，boot=800）
  4) 滚动 walk-forward：4 折，训练段选阈值（逐日平衡 edge），测试段冻结应用
  5) 逻辑回归（L2）walk-forward OOS：AUC/log-loss/Brier —— 纯预测力描述
  6) 随机对照：每日从全集抽同条数随机子集，统计过「edge>0.15pp 且 R3≥95%」比例

铁律：boot 固定 800；选池结论只用逐日平衡 edge；不过闸=不出票。
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
SCORE_FEATS = ["vseq", "vr_now", "vtrend"]   # 三同向特征（诊断结论，事前冻结）


def build_rows(D, n_asof):
    try:
        _txk.set_asof(D)
    except Exception:
        pass
    cache = _txk.load()
    name_map = NS.load_name_map(D)
    name2sw2 = NS.load_name2sw2()
    ind_map, cl = NS.load_hot_maps()
    w52 = NS.load_52w_cache(cache)
    dates = BT.pick_asof_dates(cache, n=n_asof, fwd=BT.FWD)
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
            vf = vol_features(r["code"], cache[r["code"]], r["asof_idx"], r)
            if not vf:
                continue
            r.update({"date": d, "ftA": fa, "ftB": fb, "vf": vf,
                      "winA": bool(fa["win"]), "retA": fa["ret"],
                      "winB": bool(fb["win"]), "retB": fb["ret"],
                      # canonical edge_stats 需要 pnl(pp)/win 键（主口径 A）
                      "pnl": fa["ret"] * 100.0, "win": bool(fa["win"])})
            rows.append(r)
    return rows


def add_score(rows):
    """vol_score = Σ 秩分位(反向) / 3 ×100。秩分位在全集上计算（描述性）；
    walk-forward 内改用训练段秩（防污染）。"""
    for f in SCORE_FEATS:
        vals = sorted(r["vf"][f] for r in rows if r["vf"].get(f) is not None)
        if not vals:
            continue
        n = len(vals)

        def prank(x, _v=vals, _n=n):
            # 小于 x 的比例（0~1），反向 = 1-p
            lo, hi = 0, _n
            while lo < hi:
                mid = (lo + hi) // 2
                if _v[mid] < x:
                    lo = mid + 1
                else:
                    hi = mid
            return lo / _n
        for r in rows:
            v = r["vf"].get(f)
            if v is None:
                r["s_" + f] = None
            else:
                r["s_" + f] = 1.0 - prank(v)
    for r in rows:
        ss = [r["s_" + f] for f in SCORE_FEATS if r.get("s_" + f) is not None]
        # 可用特征≥2 即计分（vseq 需回撤段≥6根，短回撤样本缺失）
        r["vol_score"] = (sum(ss) / len(ss) * 100) if len(ss) >= 2 else None
        r["score_cov"] = len(ss)
    return rows


def edge_of(rows, sel, ctrl=None, name="sel"):
    """canonical 逐日平衡 edge + R3。sel/ctrl 为行判定函数。"""
    st = GC.edge_stats(rows, sel, ctrl or (lambda r: True), name=name)
    return st


def logistic_fit(X, y, l2=1.0, iters=300, lr=0.5):
    """极简 L2 逻辑回归（无外部依赖）。X 已标准化。返回 (w, b, mu, sd)。"""
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
    """pairs: [(score, label01)] → AUC（Mann-Whitney）。"""
    pos = [s for s, y in pairs if y == 1]
    neg = [s for s, y in pairs if y == 0]
    if not pos or not neg:
        return None
    # 秩次法
    allv = sorted(pairs, key=lambda t: t[0])
    # 平均秩处理并列
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None)
    ap.add_argument("--asof", type=int, default=60)
    a = ap.parse_args()
    D = a.date or NS.latest_date()
    print("=== N字形 · 量能评分合成 + WF + 随机对照 · 数据日 %s · as-of %d 日 ===" % (D, a.asof))

    rows = build_rows(D, a.asof)
    rows = add_score(rows)
    ok = [r for r in rows if r.get("vol_score") is not None]
    print("样本 %d 条（vol_score 完整 %d）｜ as-of %s ~ %s"
          % (len(rows), len(ok), min(r["date"] for r in ok), max(r["date"] for r in ok)))
    ba = agg_ft(ok, "ftA")
    bb = agg_ft(ok, "ftB")
    print("基准 +10/-8/10：n=%d 胜率=%.2f%% 均=%+.3f%%｜ +6/-8/10：n=%d 胜率=%.2f%% 均=%+.3f%%"
          % (ba["n"], ba["win"], ba["avg"], bb["n"], bb["win"], bb["avg"]))

    out = {"date": D, "asof": a.asof, "n": len(ok), "boot": BOOT,
           "base": {"A": ba, "B": bb}, "score_quintiles": {},
           "wf": {}, "logit": {}, "random_control": {}}

    # ---- 1) vol_score 五分位 + 头尾20% ----
    for tag, ftkey in (("A(+10/-8/10)", "ftA"), ("B(+6/-8/10)", "ftB")):
        sv = sorted(ok, key=lambda r: r["vol_score"])
        k = len(sv) // 5
        qs = []
        for qi in range(5):
            seg = sv[qi * k:(qi + 1) * k] if qi < 4 else sv[4 * k:]
            a_ = agg_ft(seg, ftkey)
            a_["q"] = qi + 1
            qs.append(a_)
        low20 = sv[:len(sv) // 5]
        high20 = sv[-len(sv) // 5:]
        la, ha = agg_ft(low20, ftkey), agg_ft(high20, ftkey)
        print("\n[%s] vol_score 五分位 Q1(最缩量)→Q5：胜率 %s｜均 %s"
              % (tag, "/".join("%.1f" % q["win"] for q in qs),
                 "/".join("%+.2f" % q["avg"] for q in qs)))
        print("     头20%%(最缩量)：n=%d 胜率=%.2f%% 均=%+.3f 盈亏比=%s｜尾20%%：n=%d 胜率=%.2f%% 均=%+.3f"
              % (la["n"], la["win"], la["avg"], la["pl"], ha["n"], ha["win"], ha["avg"]))
        out["score_quintiles"][tag] = {"quintiles": qs, "low20": la, "high20": ha}

    # ---- 2) 头20% canonical edge（全样本描述）----
    sel_top = lambda r: r.get("vol_score") is not None and r["vol_score"] >= 80
    st = edge_of(ok, sel_top, name="top20")
    print("\n[canonical] 头20%%(vol_score≥80)：n=%s edge=%+.3fpp R3=%s win=%s"
          % (st["n_rows"], st["edge"], st["r3"], st["win"]))
    out["top20_full"] = {k: st[k] for k in ("n_rows", "edge", "r3", "win") if k in st}

    # ---- 3) 滚动 walk-forward（4折：训练40日→测试20日）----
    dates = sorted(set(r["date"] for r in ok))
    step = 10
    folds = []
    i = 0
    while i + 50 <= len(dates):
        tr = dates[i:i + 40]
        te = dates[i + 40:i + 50]
        if len(te) < 10:
            break
        folds.append((tr, te))
        i += step
    print("\n---- 滚动 walk-forward：训练段选阈值（逐日平衡 edge 最大），测试段冻结 ----")
    wf_rows = []
    for fi, (tr, te) in enumerate(folds, 1):
        trs = set(tr)
        tr_rows = [r for r in ok if r["date"] in trs]
        te_rows = [r for r in ok if r["date"] not in trs and te[0] <= r["date"] <= te[-1]]
        best = None
        for t in [50, 60, 65, 70, 75, 80, 85]:
            sel = lambda r, _t=t: r["vol_score"] >= _t
            s_ = GC.edge_stats(tr_rows, sel, lambda r: True, name="tr")
            if best is None or (s_.get("edge") or -9) > best[0]:
                best = ((s_.get("edge") or -9), t, s_.get("r3"))
        _e, t, _r3 = best
        sel = lambda r, _t=t: r["vol_score"] >= _t
        stt = GC.edge_stats(te_rows, sel, lambda r: True, name="te")
        base_st = GC.edge_stats(te_rows, lambda r: True, lambda r: True, name="base")
        aA = agg_ft([r for r in te_rows if r["vol_score"] >= t], "ftA")
        aB = agg_ft([r for r in te_rows if r["vol_score"] >= t], "ftB")
        rec = {"fold": fi, "train": [tr[0], tr[-1]], "test": [te[0], te[-1]],
               "thresh": t, "train_edge": round(_e, 3),
               "test_n": stt.get("n_rows") or 0,
               "test_edge": stt.get("edge"), "test_r3": stt.get("r3"),
               "test_win": aA["win"] if aA else None,
               "test_avg": aA["avg"] if aA else None,
               "testB_win": aB["win"] if aB else None,
               "base_edge": base_st.get("edge")}
        wf_rows.append(rec)
        print("  fold%d 训练[%s~%s] 选阈值≥%d(train edge %+.2f) → 测试[%s~%s] n=%d edge=%s R3=%s 胜率=%s"
              % (fi, tr[0], tr[-1], t, _e, te[0], te[-1], rec["test_n"],
                 ("%+.3f" % rec["test_edge"]) if rec["test_edge"] is not None else "NA",
                 ("%.1f" % rec["test_r3"]) if rec["test_r3"] is not None else "NA",
                 ("%.2f%%" % rec["test_win"]) if rec["test_win"] else "NA"))
        out["wf"]["fold%d" % fi] = rec
    oos = [r for rec in wf_rows for r in ok
           if rec["test"][0] <= r["date"] <= rec["test"][1] and r["vol_score"] >= rec["thresh"]]
    aA = agg_ft(oos, "ftA")
    aB = agg_ft(oos, "ftB")
    print("  OOS 合并：n=%d｜A 胜率=%.2f%% 均=%+.3f｜B 胜率=%.2f%% 均=%+.3f"
          % (len(oos), aA["win"], aA["avg"], aB["win"], aB["avg"]) if aA else "  OOS 无样本")
    out["wf"]["oos"] = {"n": len(oos), "A": aA, "B": aB}

    # ---- 4) 逻辑回归 walk-forward（纯预测力：OOS AUC/log-loss）----
    print("\n---- 逻辑回归（L2）walk-forward OOS 预测力 ----")
    logit_feats = ["vseq", "vr_now", "vtrend", "vr5_20", "vmin_ratio", "contr_pb"]
    def xvec(r):
        return [math.log(max(1e-6, r["vf"][f])) for f in logit_feats]
    def complete(r):
        return all(r["vf"].get(f) is not None for f in logit_feats)
    lg_oos = []
    for fi, (tr, te) in enumerate(folds, 1):
        trs = set(tr)
        tr_rows = [r for r in ok if r["date"] in trs and complete(r)]
        te_rows = [r for r in ok if r["date"] not in trs and te[0] <= r["date"] <= te[-1] and complete(r)]
        if len(tr_rows) < 60 or len(te_rows) < 30:
            continue
        model = logistic_fit([xvec(r) for r in tr_rows], [1 if r["winA"] else 0 for r in tr_rows])
        pairs = []
        ll, npos = 0.0, 0
        for r in te_rows:
            p = logistic_pred(model, xvec(r))
            pairs.append((p, 1 if r["winA"] else 0))
            y = 1 if r["winA"] else 0
            ll += -(y * math.log(max(1e-9, p)) + (1 - y) * math.log(max(1e-9, 1 - p)))
        a_ = auc(pairs)
        rec = {"fold": fi, "n_test": len(te_rows), "auc": round(a_, 4) if a_ else None,
               "logloss": round(ll / len(te_rows), 4)}
        lg_oos.append(rec)
        print("  fold%d 测试 n=%d AUC=%s logloss=%s"
              % (fi, rec["n_test"], rec["auc"], rec["logloss"]))
    out["logit"] = {"feats": logit_feats, "folds": lg_oos}

    # ---- 5) 随机对照 ----
    import random
    rng = random.Random(20261024)
    print("\n---- 随机对照：每日抽同等条数随机子集，达标（edge>0.15pp 且 R3≥95%%）比例 ----")
    hit = 0
    N_RAND = 40
    for _ in range(N_RAND):
        chosen = set()
        by_day = {}
        for r in ok:
            if r["vol_score"] >= 80:
                by_day.setdefault(r["date"], []).append(id(r))
        for d, ids in by_day.items():
            day_all = [r for r in ok if r["date"] == d]
            for r in rng.sample(day_all, min(len(ids), len(day_all))):
                chosen.add(id(r))
        st_ = GC.edge_stats(ok, lambda r: id(r) in chosen, lambda r: True, name="rand")
        if (st_.get("edge") or 0) > COST_PP and (st_.get("r3") or 0) >= 95:
            hit += 1
    rate = hit / N_RAND * 100
    print("  随机达标 %d/%d = %.1f%%" % (hit, N_RAND, rate))
    out["random_control"] = {"rand_n": N_RAND, "hit": hit, "hit_rate_pct": round(rate, 2)}

    os.makedirs(OUT_DIR, exist_ok=True)
    outp = os.path.join(OUT_DIR, "vol_score_%s.json" % D.replace("-", ""))
    json.dump(out, open(outp, "w", encoding="utf-8"), ensure_ascii=False, indent=1, sort_keys=True)
    print("\n存档：%s" % outp)


if __name__ == "__main__":
    main()
