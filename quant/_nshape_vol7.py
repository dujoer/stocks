# -*- coding: utf-8 -*-
"""N字形 · 退出工程决胜 v7（2026-10-25）：每折内选退出 + OOS 盲测 + canonical 判据。

动机：选股维度已多轮验证（量能优选有相对 edge、绝对≈0、特异性跨步长不稳）。
vol6 发现移动止盈在样本内把同子集收益从 +0.37% 抬到 +1.79%——但那是
「24 格选最优」的样本内数字，正是杀死价格族的多重比较陷阱。本脚本用
walk-forward 把退出选择也关进训练段：

  每折（40 训练日 + 10 测试日）：
    1) 训练段中位数插补 + 逻辑回归（只用训练段）
    2) 训练段 top20% 上评估退出网格（固定首触组 + 移动止盈组，hold=10），按训练均收益选优
    3) 选中退出应用到测试段全部行（对照域），测试段 top20% 标记
  OOS 合并（按 id 去重）：
    - canonical：edge/R3(bootstrap 800)/留一/前后半/随机对照 40 次
    - 绝对值（pnl/win_pool）+ 与固定首触 +10/-8/10 的配对比较
    - 成本线 0.15pp 判定

诚实披露：hold=20 止盈在样本内更好，但会丢掉窗口末期缺 20 根前向bar的行
（vol6：210→159），本决胜只用 hold=10（全窗口可评，缺 bar 行≤1 披露）。
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
from _nshape_vol3 import rich_vol_features, logistic_fit, logistic_pred
from _exit_sim import sim_exit

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "n_shape")
BOOT = 800
COST_PP = 0.15
HOLD = 10
LOGF = ["v_turn", "v_surge", "v_peak", "obv_slope", "v_ud3", "v_reb",
        "vseq", "vr_now", "vtrend"]
TOP_FRAC = 0.2
MIN_TRAIN_TOP = 15          # 训练段 top 子集最少行数，不足则该退出不参选

# 退出网格（全部 hold=10，保证全窗口可评）
EXIT_GRID = []
for tp in (0.06, 0.10, 0.12):
    EXIT_GRID.append(("fixed", (tp, 0.08, HOLD)))
for stop in (0.08, 0.10, 0.12):
    for act in (0.04, 0.06):
        for trail in (0.03, 0.05):
            EXIT_GRID.append(("trail", (stop, act, trail, HOLD)))


def xvec(r, med):
    out = []
    for f in LOGF:
        v = r["vf"].get(f)
        if v is None:
            v = med[f]
        if f != "obv_slope":
            out.append(math.log(max(1e-6, float(v))))
        else:
            out.append(float(v))
    return out


def fwd_arrays(cache, r, hold=HOLD):
    """前向 C/H/L/O（T+1..T+hold），不足返回 None。"""
    bars = cache.get(r["code"]) or []
    aidx = r.get("asof_idx")
    if aidx is None:
        return None
    seg = bars[aidx + 1: aidx + 1 + hold]
    if len(seg) < hold:
        return None
    px = bars[aidx]["last"]
    if not px:
        return None
    return (px, [b["last"] for b in seg], [b["high"] for b in seg],
            [b["low"] for b in seg], [b["open"] for b in seg])


def pnl_under(cache, r, exit_spec):
    """给定退出规格的收益（pp）。exit_spec = ("fixed",(tp,sl,h)) 或 ("trail",(stop,act,trail,hold))。"""
    kind, p = exit_spec
    if kind == "fixed":
        raw = {k: v for k, v in r.items() if k != "ft"}
        ft = BT.fwd_first_touch(cache, raw, p[0], p[1], p[2])
        if not ft:
            return None
        return ft["ret"] * 100.0
    fb = fwd_arrays(cache, r, p[3])
    if not fb:
        return None
    px, fC, fH, fL, fO = fb
    pnl, _hd, _mae = sim_exit(fC, fH, fL, px, stop=p[0], act=p[1], trail=p[2],
                              hold=p[3], cons=True, fO=fO)
    return pnl


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None)
    ap.add_argument("--asof", type=int, default=60)
    ap.add_argument("--step", type=int, default=10)
    ap.add_argument("--rand", type=int, default=40, help="随机对照次数（40 次 SE≈3.4%%，200 次≈1.5%%）")
    ap.add_argument("--top", type=float, default=TOP_FRAC, help="每日优选比例（默认0.2）")
    ap.add_argument("--heat", default=None, help="热度过滤：strong_range=仅强势+震荡")
    a = ap.parse_args()
    D = a.date or NS.latest_date()
    DS = D.replace("-", "")
    print("=== N字形 · 退出工程决胜 v7 · 数据日 %s · step %d%s ===" % (
        D, a.step, " · 热度门控=%s" % a.heat if a.heat else ""))

    _txk.set_asof(D)
    cache = _txk.load()
    name_map = NS.load_name_map(D)
    name2sw2 = NS.load_name2sw2()
    ind_map, cl = NS.load_hot_maps()
    w52 = NS.load_52w_cache(cache)
    dates = BT.pick_asof_dates(cache, n=a.asof, fwd=HOLD)
    print("as-of 窗口：%s → %s（%d 日）" % (dates[0], dates[-1], len(dates)))

    # ---- 建行：hb_pos 全集 ----
    rows = []
    for d in dates:
        day = NS.gen_signals_asof(cache, d, name_map)
        NS.attach_attr(day, name2sw2, ind_map, cl, w52)
        heat = NS.load_market_heat(d)
        for r in day:
            if not BT.is_hb_pos(r):
                continue
            r["date"] = d
            r["heat"] = heat["label"]
            rows.append(r)
    for r in rows:
        r["vf"] = rich_vol_features(r["code"], cache.get(r["code"]) or [],
                                    r["asof_idx"], r) or {}
    n_vf = sum(1 for r in rows if any(r["vf"].get(f) is not None for f in LOGF))
    print("hb_pos 行：%d（有量能特征 %d）" % (len(rows), n_vf))
    if a.heat == "strong_range":
        rows = [r for r in rows if r["heat"] in ("强势", "震荡")]
        print("热度门控后：%d 行" % len(rows))
    elif a.heat == "no_break":
        rows = [r for r in rows if r["heat"] != "破位"]
        print("排除破位日后：%d 行" % len(rows))

    # ---- 折分 ----
    step = a.step
    folds = []
    i = 0
    while i + 50 <= len(dates):
        folds.append((dates[i:i + 40], dates[i + 40:i + 50]))
        i += step
    print("折数：%d（%s）" % (len(folds),
          " + ".join("%s~%s" % (tr[0], te[-1]) for tr, te in folds)))

    out = {"date": D, "asof": a.asof, "step": a.step, "heat": a.heat,
           "n_rows": len(rows), "boot": BOOT, "cost_pp": COST_PP,
           "folds": [], "oos": {}, "paired": {}, "random_control": {}}
    te_all = []          # 测试行（带 _top / _pnl / _fixed 标记），跨折
    for fi, (tr, te) in enumerate(folds, 1):
        trs, tes = set(tr), set(te)
        tr_rows = [r for r in rows if r["date"] in trs]
        te_rows = [r for r in rows if r["date"] in tes]
        # 训练段中位数
        med = {}
        for f in LOGF:
            vs = sorted(r["vf"][f] for r in tr_rows if r["vf"].get(f) is not None)
            med[f] = vs[len(vs) // 2] if vs else 1.0
        trc = [r for r in tr_rows if any(r["vf"].get(f) is not None for f in LOGF)]
        if len(trc) < 60:
            print("fold%d 训练样本不足，跳过" % fi)
            continue
        model = logistic_fit([xvec(r, med) for r in trc],
                             [1 if BT.fwd_first_touch(
                                 cache, {k: v for k, v in r.items() if k != "ft"},
                                 0.10, 0.08, HOLD) and
                              BT.fwd_first_touch(
                                  cache, {k: v for k, v in r.items() if k != "ft"},
                                  0.10, 0.08, HOLD)["win"] else 0 for r in trc])
        if not model:
            print("fold%d 模型训练失败，跳过" % fi)
            continue
        # 训练段打分 + top20%（按日）
        for r in trc:
            r["_p"] = logistic_pred(model, xvec(r, med))
        by_day = {}
        for r in trc:
            by_day.setdefault(r["date"], []).append(r)
        tr_top = set()
        for _d, rs in by_day.items():
            rs.sort(key=lambda r: -r["_p"])
            k = max(1, int(len(rs) * a.top))
            tr_top.update(id(r) for r in rs[:k])
        # 退出选择：训练段 top 子集上按均收益选优
        best = None
        for spec in EXIT_GRID:
            vals = []
            for r in trc:
                if id(r) not in tr_top:
                    continue
                v = pnl_under(cache, r, spec)
                if v is not None:
                    vals.append(v)
            if len(vals) < MIN_TRAIN_TOP:
                continue
            m = sum(vals) / len(vals)
            if best is None or m > best[1]:
                best = (spec, m, len(vals))
        if best is None:
            print("fold%d 无合格退出参选，跳过" % fi)
            continue
        chosen, tr_avg, tr_n = best
        print("fold%d 选中退出：%s %s（训练段 top n=%d 均=%+.3f%%）"
              % (fi, chosen[0], chosen[1], tr_n, tr_avg))
        # 应用到测试段：全部行算 _pnl（对照域），top 行标记
        te_scored = [r for r in te_rows if any(r["vf"].get(f) is not None for f in LOGF)]
        for r in te_scored:
            r["_p"] = logistic_pred(model, xvec(r, med))
            r["_pnl"] = pnl_under(cache, r, chosen)
            r["_fixed"] = pnl_under(cache, r, ("fixed", (0.10, 0.08, HOLD)))
        te_ok = [r for r in te_scored if r["_pnl"] is not None]
        by_day = {}
        for r in te_ok:
            by_day.setdefault(r["date"], []).append(r)
        n_top = 0
        for _d, rs in by_day.items():
            rs.sort(key=lambda r: -r["_p"])
            k = max(1, int(len(rs) * a.top))
            for r in rs[:k]:
                r["_top"] = True
                n_top += 1
        print("fold%d 测试段：可评 %d 行，top%d 行" % (fi, len(te_ok), n_top))
        te_all.extend(te_ok)
        out["folds"].append({"fold": fi, "train": [tr[0], tr[-1]], "test": [te[0], te[-1]],
                             "chosen_exit": [chosen[0], list(chosen[1])],
                             "train_top_avg": round(tr_avg, 3), "train_top_n": tr_n,
                             "test_rows": len(te_ok), "test_top": n_top})

    if not te_all:
        print("无测试行，退出")
        return

    # ---- OOS 合并（按 id 去重）----
    # 注意：step<10 时折间测试窗重叠，同一行可能被后折以「缺前向bar」重算成 None
    # （换了 trail 退出即需满 hold 根前向bar）——以最后一次可评为准，不可评的剔除并披露。
    seen = {}
    for r in te_all:
        seen[id(r)] = r
    te_uniq = [r for r in seen.values() if r.get("_pnl") is not None]
    n_drop = len(seen) - len(te_uniq)
    if n_drop:
        print("去重时剔除不可评行：%d（折间重叠+退出变更导致缺前向bar）" % n_drop)
    for r in te_uniq:
        r["pnl"] = r["_pnl"]
        r["win"] = r["pnl"] > 0
    n_top = sum(1 for r in te_uniq if r.get("_top"))
    print("\nOOS 合并（去重后）：%d 行，其中 top %d 行" % (len(te_uniq), n_top))
    if n_top < 10:
        print("top 样本不足，不出结论")
        return

    st = GC.edge_stats(te_uniq, lambda r: bool(r.get("_top")), lambda r: True,
                       boot=BOOT, name="OOS_trail_exit")
    days = st.get("days") or []
    h = len(days) // 2
    e1 = sum(d["edge"] for d in days[:h]) / max(1, h)
    e2 = sum(d["edge"] for d in days[h:]) / max(1, len(days) - h)
    print("\n---- OOS canonical（选中退出，逐日平衡）----")
    print("  top 行 n=%d｜绝对均收益 pnl=%+.3fpp｜胜率(池化)=%.2f%%｜edge=%+.3fpp"
          % (st["n_rows"], st["pnl"], st["win_pool"], st["edge"]))
    print("  R3=%s%%｜loo_min=%+.3f｜前半 edge=%+.3f｜后半 edge=%+.3f"
          % (st["r3"], st["loo_min"], e1, e2))
    print("  对照域（全集）绝对均=%+.3fpp" % st["ctrl_pnl"])
    out["oos"] = {"n_top": st["n_rows"], "pnl": st["pnl"], "win_pool": st["win_pool"],
                  "edge": st["edge"], "r3": st["r3"], "loo_min": st["loo_min"],
                  "half1": round(e1, 3), "half2": round(e2, 3),
                  "ctrl_pnl": st["ctrl_pnl"], "n_days": st["n_days"]}

    # 配对：同一批 top 行的固定首触 +10/-8/10
    tops = [r for r in te_uniq if r.get("_top") and r.get("_fixed") is not None]
    if tops:
        fx = sum(r["_fixed"] for r in tops) / len(tops)
        tr_ = sum(r["_pnl"] for r in tops) / len(tops)
        fw = sum(1 for r in tops if r["_fixed"] > 0) / len(tops) * 100
        tw = sum(1 for r in tops if r["_pnl"] > 0) / len(tops) * 100
        print("\n---- 配对比较（同一批 OOS top 行 n=%d）----" % len(tops))
        print("  固定首触+10/-8/10：均 %+.3f%% 胜率 %.2f%%" % (fx, fw))
        print("  选中退出（折内选）：均 %+.3f%% 胜率 %.2f%%" % (tr_, tw))
        print("  差异：%+.3fpp" % (tr_ - fx))
        out["paired"] = {"n": len(tops), "fixed_avg": round(fx, 3), "fixed_win": round(fw, 2),
                         "chosen_avg": round(tr_, 3), "chosen_win": round(tw, 2),
                         "diff": round(tr_ - fx, 3)}

    # ---- 随机对照 ----
    rng = random.Random(20261025)
    by_day = {}
    for r in te_uniq:
        by_day.setdefault(r["date"], []).append(r)
    hit = 0
    N_RAND = a.rand
    for _ in range(N_RAND):
        chosen = set()
        for _d, rs in by_day.items():
            k = sum(1 for r in rs if r.get("_top"))
            if k <= 0:
                continue
            if len(rs) <= k:
                chosen.update(id(r) for r in rs)
            else:
                chosen.update(id(r) for r in rng.sample(rs, k))
        s_ = GC.edge_stats(te_uniq, lambda r: id(r) in chosen, lambda r: True,
                           boot=BOOT, name="rand")
        if (s_.get("edge") or -9) > COST_PP and (s_.get("r3") or 0) >= 95:
            hit += 1
    rate = hit / N_RAND * 100
    print("\n---- 随机对照：%d/%d = %.1f%%（>5%% 疑多重比较噪声）----" % (hit, N_RAND, rate))
    out["random_control"] = {"rand_n": N_RAND, "hit": hit, "hit_rate_pct": round(rate, 2)}

    # ---- 判定 ----
    ok_edge = st["edge"] > COST_PP
    ok_r3 = (st.get("r3") or 0) >= 95
    ok_loo = (st.get("loo_min") or -9) > 0
    ok_half = e1 > 0 and e2 > 0
    ok_rand = rate <= 5.0
    ok_abs = (st["pnl"] or -9) > COST_PP
    print("\n---- 判定（成本线 %.2fpp）----" % COST_PP)
    print("  edge>成本：%s｜R3≥95：%s｜留一全正：%s｜前后半同正：%s｜随机≤5%%：%s｜绝对>成本：%s"
          % (ok_edge, ok_r3, ok_loo, ok_half, ok_rand, ok_abs))
    out["verdict"] = {"edge": ok_edge, "r3": ok_r3, "loo": ok_loo,
                      "halves": ok_half, "random": ok_rand, "absolute": ok_abs}
    if ok_edge and ok_r3 and ok_loo and ok_half and ok_rand and ok_abs:
        print("  结论：全过 —— 可作为候选进入生产评估")
        out["licensed"] = True
    else:
        print("  结论：未全过 —— 按铁律不出票")
        out["licensed"] = False

    os.makedirs(OUT_DIR, exist_ok=True)
    suffix = "_%s" % a.heat if a.heat else ""
    suffix += "_top%g" % a.top
    outp = os.path.join(OUT_DIR, "vol7_exit_wf_%s_step%d%s.json" % (DS, a.step, suffix))
    json.dump(out, open(outp, "w", encoding="utf-8"), ensure_ascii=False, indent=1, sort_keys=True)
    print("\n存档：%s" % outp)


if __name__ == "__main__":
    main()
