# -*- coding: utf-8 -*-
"""N字形候选档出票闸门（照 _gate_common canonical 判据，fail-safe）。

判据（与增仓/反转/高胜率三池同一统计层，禁自造口径）：
  ① 逐日平衡 edge = 档逐日均值 − 同日对照域（当日全部 hb_pos）逐日均值；
  ② 经济闸：edge > 0.15pp（双边成本：佣金.05+印花.05+过户.002+滑点.05）；
  ③ R3（按日 block bootstrap，GC.BOOT=800 固定，写入产物）≥ 95%；
  ④ 留一全正（loo_min > 0）；
  ⑤ 前后半 edge 同号；
  ⑥ 跨窗口（asof=30 派生步长）同号且 R3≥95%；
  ⑦ 随机对照：同每日条数的随机子集达到 ②③ 的比例（防多重比较噪声）。
全部满足 → 可出票；任一不满足或读不到证据 → 「无合格标的」，不放宽阈值。
"""
import argparse
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_n_shape as NS          # noqa: E402
import build_n_shape_backtest as BT  # noqa: E402
import _gate_common as GC           # noqa: E402
import _txk                          # noqa: E402

QUANT = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(QUANT, "n_shape")
COST_PP = 0.15          # 双边成本门槛（pp）
RAND_CTRL = 200         # 随机对照次数（固定，写入产物）


def r_deep(s):    return (s.get("dist_local_peak") or 0) <= -20
def r_time(s):    return (s.get("days_since_zt") or 0) >= 5
def r_pos(s):     return s.get("pos_pctile") is not None and s["pos_pctile"] <= 60
def r_pos2(s):    return s.get("pos_pctile") is not None and s["pos_pctile"] <= 50
def r_amt(s):     return (s.get("avg_amt_yi") or 0) >= 5

CANDIDATES = {
    "R1∩R2∩R3": lambda s: r_deep(s) and r_time(s) and r_pos(s),
    "R1∩R2∩R3b": lambda s: r_deep(s) and r_time(s) and r_pos2(s),
    "R1∩R3": lambda s: r_deep(s) and r_pos(s),
    "R2∩R3": lambda s: r_time(s) and r_pos(s),
    "R1∩R2∩R3∩R5": lambda s: r_deep(s) and r_time(s) and r_pos(s) and r_amt(s),
}
PARAMS = [(0.06, 0.08, 10), (0.08, 0.06, 10), (0.10, 0.08, 10), (0.12, 0.08, 10),
          (0.10, 0.06, 10), (0.08, 0.08, 20), (0.12, 0.10, 10)]


def build_rows(cache, name_map, name2sw2, ind_map, cl, w52, asof_dates, heat_map, tp, sl, h):
    """重建 hb_pos 信号行（date/pnl/win + 规则字段）。ctrl 域 = 当日全部 hb_pos。"""
    rows = []
    for d in asof_dates:
        day = NS.gen_signals_asof(cache, d, name_map)
        NS.attach_attr(day, name2sw2, ind_map, cl, w52)
        for r in day:
            if not BT.is_hb_pos(r):
                continue
            raw = {k: v for k, v in r.items() if k != "ft"}
            ft = BT.fwd_first_touch(cache, raw, tp, sl, h)
            if not ft:
                continue
            r.update({"date": d, "pnl": ft["ret"] * 100.0, "win": bool(ft["win"]),
                      "heat_label": heat_map.get(d, "未知")})
            rows.append(r)
    return rows


def gate_one(rows, sel_fn, name):
    st = GC.edge_stats(rows, sel_fn, lambda r: True, name=name)
    hv = GC.halves(st.get("days", []))
    return st, hv


def passes(st, hv):
    """机器判定：经济闸+R3+留一+前后半同号。"""
    if st.get("edge") is None:
        return False, "无证据"
    why = []
    if st["edge"] <= COST_PP:
        why.append("edge=%.2fpp≤%.2fpp" % (st["edge"], COST_PP))
    if (st.get("r3") or 0) < 95:
        why.append("R3=%.1f<95" % (st.get("r3") or 0))
    if (st.get("loo_min") or -9) <= 0:
        why.append("loo_min=%.3f≤0" % (st.get("loo_min") or 0))
    if len(hv) == 2 and not (hv[0]["edge"] > 0 and hv[1]["edge"] > 0):
        why.append("前后半不同正(%s/%s)" % (hv[0]["edge"], hv[1]["edge"]))
    return (not why), (";".join(why) if why else "全过")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None)
    ap.add_argument("--asof", type=int, default=60)
    ap.add_argument("--sens-asof", type=int, default=30)
    a = ap.parse_args()
    D = a.date or NS.latest_date()
    print("=== N字形候选档出票闸门 · 数据日 %s · asof %d（派生 %d）===" % (D, a.asof, a.sens_asof))

    try:
        _txk.set_asof(D)
    except Exception:
        pass
    cache = _txk.load()
    name_map = NS.load_name_map(D)
    name2sw2 = NS.load_name2sw2()
    ind_map, cl = NS.load_hot_maps()
    w52 = NS.load_52w_cache(cache)
    dates60 = BT.pick_asof_dates(cache, n=a.asof, fwd=BT.FWD)
    dates_s = BT.pick_asof_dates(cache, n=a.sens_asof, fwd=BT.FWD)
    heat_map = {}
    for d in dates60:
        try:
            heat_map[d] = (NS.load_market_heat(d) or {}).get("label") or "未知"
        except Exception:
            heat_map[d] = "未知"

    out = {"date": D, "boot": GC.BOOT, "cost_pp": COST_PP, "rand_ctrl": RAND_CTRL,
           "asof_main": a.asof, "asof_sens": a.sens_asof, "tiers": [], "random_control": {}}
    survivors = []
    for name, fn in CANDIDATES.items():
        for tp, sl, h in PARAMS:
            pkey = "+%g/-%g/%d" % (tp * 100, sl * 100, h)
            rows = build_rows(cache, name_map, name2sw2, ind_map, cl, w52, dates60, heat_map, tp, sl, h)
            if len(rows) < 30:
                continue
            sel = lambda r, _fn=fn: _fn(r)
            st, hv = gate_one(rows, sel, "%s|%s" % (name, pkey))
            ok, why = passes(st, hv)
            # 跨窗口（派生步长）
            rows_s = build_rows(cache, name_map, name2sw2, ind_map, cl, w52, dates_s, heat_map, tp, sl, h)
            st_s, hv_s = gate_one(rows_s, sel, "%s|%s|sens" % (name, pkey))
            sens_ok = (st_s.get("edge") or 0) > COST_PP and (st_s.get("r3") or 0) >= 95
            rec = {"tier": "%s|%s" % (name, pkey), "n_rows": st.get("n_rows"),
                   "n_days": st.get("n_days"), "edge": st.get("edge"), "r3": st.get("r3"),
                   "win": st.get("win"), "loo_min": st.get("loo_min"),
                   "halves": hv, "ok_main": ok, "why_main": why,
                   "sens": {"edge": st_s.get("edge"), "r3": st_s.get("r3"),
                            "n_days": st_s.get("n_days"), "ok": sens_ok}}
            out["tiers"].append(rec)
            tag = "PASS" if (ok and sens_ok) else "fail"
            print("[%s] %-22s %-12s n=%-4d edge=%+6.2fpp R3=%5.1f loo=%+.3f 前半%+.2f/后半%+.2f | sens edge=%+.2f R3=%.1f | %s"
                  % (tag, name, pkey, st.get("n_rows") or 0, st.get("edge") or 0,
                     st.get("r3") or 0, st.get("loo_min") or 0,
                     hv[0]["edge"] if len(hv) == 2 else 0, hv[1]["edge"] if len(hv) == 2 else 0,
                     st_s.get("edge") or 0, st_s.get("r3") or 0, why))
            if ok and sens_ok:
                survivors.append((rec, rows, sel))

    # ---- 随机对照（防多重比较噪声）：每日从「当日全集」抽与候选同条数的随机子集 ----
    # 若随机子集也频繁达标 → edge 来自「少选」的结构而非规则特异性 → 不出票。
    rng = random.Random(20261024)
    print("\n---- 随机对照：同每日条数的随机子集（从当日全集抽取），统计「edge>0.15pp 且 R3≥95%%」比例 ----")
    # 每规则族取代表档（+10/-8/10），避免对 31 个幸存档重复同一检验
    reps = {}
    for rec, rows, sel in survivors:
        fam = rec["tier"].split("|")[0]
        if fam not in reps:
            reps[fam] = (rec, rows, sel)
    for fam, (rec, rows, sel) in reps.items():
        cand_by_day = {}
        all_by_day = {}
        for r in rows:
            all_by_day.setdefault(r["date"], []).append(r)
            if sel(r):
                cand_by_day.setdefault(r["date"], []).append(r)
        days = sorted(cand_by_day)
        hit = 0
        for _ in range(RAND_CTRL):
            chosen = set()
            for d in days:
                pool = all_by_day[d]
                k = len(cand_by_day[d])
                if k >= len(pool):
                    chosen.update(id(r) for r in pool)
                else:
                    chosen.update(id(r) for r in rng.sample(pool, k))
            st, _hv = gate_one(rows, lambda r, _c=chosen: id(r) in _c, "rand")
            if (st.get("edge") or 0) > COST_PP and (st.get("r3") or 0) >= 95:
                hit += 1
        rate = hit / RAND_CTRL * 100
        out["random_control"][rec["tier"]] = {"rand_n": RAND_CTRL, "hit": hit, "hit_rate_pct": round(rate, 2)}
        print("  %-30s 随机达标 %d/%d = %.1f%%" % (rec["tier"], hit, RAND_CTRL, rate))

    print("\n---- 出票结论（主判据 + 跨窗口 + 随机对照，机器判定）----")
    # 随机对照按族记录（每族一个代表档）；结论按族匹配实际记录的键
    fam_rc = {}
    for k, v in out["random_control"].items():
        fam_rc[k.split("|")[0]] = v
    licensed = []
    for rec, _rows, _sel in survivors:
        fam = rec["tier"].split("|")[0]
        rc = fam_rc.get(fam)
        if rc is None:
            print("  候选 %s：无随机对照证据 → fail-safe 不出票" % rec["tier"])
            continue
        if rc["hit_rate_pct"] > 5.0:
            print("  候选 %s：随机达标率 %.1f%% > 5%% → 特异性不足，不出票" % (rec["tier"], rc["hit_rate_pct"]))
            continue
        licensed.append(rec)
        print("  候选 %s：主判据+跨窗口全过，随机达标率 %.1f%% ≤ 5%%" % (rec["tier"], rc["hit_rate_pct"]))
    if not licensed:
        print("\n最终结论：无合格标的（特异性/稳健性不足）。按铁律不出票、不放宽阈值。")
    else:
        out["licensed"] = [r["tier"] for r in licensed]

    os.makedirs(OUT_DIR, exist_ok=True)
    outp = os.path.join(OUT_DIR, "gate_wf_%s.json" % D.replace("-", ""))
    json.dump(out, open(outp, "w", encoding="utf-8"), ensure_ascii=False, indent=1, sort_keys=True)
    print("\n存档：%s" % outp)


if __name__ == "__main__":
    main()
