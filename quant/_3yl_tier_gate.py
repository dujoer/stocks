#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""三连阴 · 分档出票核验（逐日平衡 edge + 按日 block bootstrap + 留一法 + 跨步长）

为什么必须做（项目红线：不能有好看但不成立的情况）：
  `_3yl_lab.py` 报出「★ 观察档（跌 8~12%）两半同向跑赢基准：胜率 47.7% / 期望 +0.43%
  （基准 44.3% / +0.01%）」，页面据此写「本期主推」。但那个对照是
  **该档 vs 全体三连阴母集** —— 母集里含它自己，属于「子集对母集」，
  不是等量对照，也没有显著性区间。本脚本按与反转池/高胜率池同一套口径重算：

    ① 逐日平衡 edge（该档逐日均 − 同日对照逐日均），不是把两堆样本摊平比绝对值；
    ② 按日 block bootstrap 算 R3（edge>0 的比例，门槛 95%）；
    ③ 留一法（去掉任意一天后 edge 的极值）；
    ④ 前/后半同向性；
    ⑤ 跨步长敏感性（step5 主口径 / step3 派生）——防「结论锁在采样格点上」。

★ **双对照**，这是本页与 lab 的关键差别：
    母集对照 = 同日全体三连阴（**含本档自己** → 稀释，偏向低估 edge）
    等量对照 = 同日**非本档**三连阴（**不含自己** → 这才是「买这档 vs 买别的三连阴」的真实差异）
  两者都报；出票许可取**更严的那个**（等量对照），不靠放宽口径凑数。

口径完全复刻生产：
  信号 = 收盘连续 3 日下跌（`C[i]<C[i-1]<C[i-2]`）+ 近 3 日无停牌跳空 + 量 > 0
  fall（累计跌幅）= 1 − close / C[i-3]，与 `build_3yl.scan()` / `_3yl_lab` 一字不差
  退出 = T+1 开盘买入 / 止损 5% / 止盈 8% / 持有 5 日（同日双触保守记止损）
  分档 = build_3yl.BUCKETS 的五档（obs/mid/light/deep/fatal）

数据：`_txk_cache.json` + `_stock_names.json` + `_mktcap.json`（全离线真实，不联网）
产出：`_3yl_tier_gate.json` / `_3yl_tier_gate_step3.json` / `web/three_yin/tier_gate.html`
用法：python3 _3yl_tier_gate.py [--sens --step 3] [--no-html] [--limit N]
"""
from __future__ import annotations
import os, sys, json, argparse, random
from collections import defaultdict

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

import _gate_common as GC
import _3yl_lab as L

BOOT = GC.BOOT
SEED = 20261005

# 生产 BUCKETS（label, key, lo, hi）—— 与 build_3yl.py 完全一致，不在此处调参
BUCKETS = [
    ("★ 观察档（8~12%）", "obs", 0.08, 0.12),
    ("一般档（5~8%）", "mid", 0.05, 0.08),
    ("浅跌档（0~5%）", "light", 0.00, 0.05),
    ("⚠ 排雷档（12~20%）", "deep", 0.12, 0.20),
    ("⛔ 深跌禁区（>20%）", "fatal", 0.20, 99.0),
]


# ------------------------------------------------------------------ 面板重建
def build_panel(step, limit=None):
    """逐票逐日重建三连阴信号 + 退出口径，产出 rows。

    row: code/date/fall/bucket/pnl/win
    """
    data, didx, dates, names, ind, mkt = L.load_data()
    codes = sorted(data.keys())
    if limit:
        codes = codes[:limit]
    psum = {}
    for c in codes:
        s, acc = [0.0], 0.0
        for x in data[c]["c"]:
            acc += x
            s.append(acc)
        psum[c] = s

    N = len(dates)
    lo_i, hi_i = 60, N - 7
    rows = []
    for di in range(lo_i, hi_i + 1, step):
        d = dates[di]
        dm1, dm2 = dates[di - 1], dates[di - 2]
        dp1 = dates[di + 1] if di + 1 < N else None
        if not dp1:
            continue
        for c in codes:
            ix = didx[c].get(d)
            if ix is None or ix < 60:
                continue
            ix1, ix2 = didx[c].get(dm1), didx[c].get(dm2)
            # 近 3 日必须连续（有停牌跳空就不算三连阴）
            if ix1 is None or ix2 is None or ix1 != ix - 1 or ix2 != ix - 2:
                continue
            arr = data[c]
            C, V = arr["c"], arr["v"]
            if not (C[ix] < C[ix1] < C[ix2]):
                continue
            if V[ix] <= 0 or V[ix1] <= 0 or V[ix2] <= 0:
                continue
            if ix2 < 1 or not C[ix2 - 1]:
                continue
            fall = 1 - C[ix] / C[ix2 - 1]
            if fall <= 0:
                continue
            o = L.outcome(arr, ix, L.DEF_STOP, L.DEF_TARGET, L.DEF_HOLD)
            if not o:
                continue
            og = L.outcome_gap(arr, ix, L.DEF_STOP, L.DEF_TARGET, L.DEF_HOLD)
            bk = "obs"
            for _, k, lo, hi in BUCKETS:
                if lo <= fall < hi:
                    bk = k
                    break
            gp = (og["ret"] * 100.0) if og else (o["ret"] * 100.0)
            rows.append({"code": c, "date": d, "fall": round(fall, 6),
                         "bucket": bk, "pnl": o["ret"] * 100.0,
                         "win": bool(o["win"]), "pnl_gap": gp})
    return rows, dates[lo_i], dates[min(hi_i, N - 1)]


def pick(key):
    def f(r):
        return r["bucket"] == key
    return f


def ctrl_same(r, key):
    """等量对照：同日**非本档**三连阴（不含自己 → 真实差异）。"""
    return r["bucket"] != key


def ctrl_all(r, key=None):
    """母集对照：同日全体三连阴（含本档 → 稀释）。"""
    _ = key
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--step", type=int, default=5)
    ap.add_argument("--sens", action="store_true")
    ap.add_argument("--no-html", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()

    print("[3yl] 重建面板 step=%d …" % a.step)
    rows, d0, d1 = build_panel(a.step, a.limit or None)
    print("[3yl] 面板 %d 行（%s ~ %s）" % (len(rows), d0, d1))

    res = {"_doc": "三连阴 分档出票核验（逐日平衡 edge + 按日 block bootstrap + 留一法）",
           "seed": SEED, "boot": BOOT, "step": a.step,
           "window": [d0, d1],
           "exit": {"stop": L.DEF_STOP, "target": L.DEF_TARGET, "hold": L.DEF_HOLD,
                    "buy": "T+1 开盘"},
           "fall_def": "1 − 信号日收盘 / 三连阴开始前一日收盘（与 build_3yl.scan 同口径）",
           "tiers": []}

    for label, key, lo, hi in BUCKETS:
        st = GC.edge_stats(rows, pick(key), ctrl_all, boot=BOOT, seed=SEED, name=key)
        if st.get("note"):
            print("[3yl] %-5s %s" % (key, st["note"]))
            st["desc"] = label
            res["tiers"].append(st)
            continue
        st["desc"] = label
        # 等量对照（同日非本档）——这才是「买这档 vs 买别的三连阴」
        ve = GC.edge_stats(rows, pick(key), lambda r, k=key: ctrl_same(r, k),
                           boot=BOOT, seed=SEED, name=key)
        st["vs_excl"] = {k: ve.get(k) for k in
                         ("n_days", "n_rows", "edge", "r3", "loo_min", "loo_max",
                          "pnl", "win", "ctrl_pnl", "ctrl_win")}
        st["halves"] = GC.halves(st["days"])
        res["tiers"].append(st)
        print("[3yl] %-5s n=%6d 母集edge=%+.3fpp(R3 %5.1f%%)  等量edge=%+.3fpp(R3 %5.1f%%)  "
              "留一[%+.3f,%+.3f]"
              % (key, st["n_rows"], st["edge"], st["r3"],
                 ve.get("edge", 0), ve.get("r3", 0),
                 st["loo_min"], st["loo_max"]))

    # ---- 成交假设审计：本池买入价已是 T+1 开盘（真实可得），唯一可修的是**跳空** ----
    #   旧 outcome：止损/止盈一律按触发价成交；可实现口径：触发日开盘已穿线则按开盘价成交
    #   （止损方向更差、止盈方向更好 → 净影响必须实测，不许猜）。
    if not a.sens and not a.limit:
        rows_gap = [dict(r, pnl=r.get("pnl_gap", r["pnl"]),
                         win=(r.get("pnl_gap", r["pnl"]) > 0)) for r in rows]
        ea_t = []
        for st, (label, key, _lo, _hi) in zip(res["tiers"], BUCKETS):
            if st.get("note"):
                ea_t.append({"key": key, "desc": label, "n": 0, "note": st["note"]})
                continue
            g1 = GC.edge_stats(rows_gap, pick(key), ctrl_all, boot=BOOT, seed=SEED, name=key)
            ea_t.append({"key": key, "desc": label, "n": st["n_rows"],
                         "wr": st["win"], "mean": st["pnl"], "edge": st["edge"], "r3": st["r3"],
                         "wr_gap": g1["win"], "mean_gap": g1["pnl"],
                         "edge_gap": g1["edge"], "r3_gap": g1["r3"],
                         "d_wr": round(g1["win"] - st["win"], 2),
                         "d_mean": round(g1["pnl"] - st["pnl"], 3)})
            print("[3yl·口径] %-5s n=%6d 旧 %5.2f%%(%+.3f%%) → 跳空修正 %5.2f%%(%+.3f%%)"
                  "  Δ胜率 %+.2fpp  Δ均值 %+.3fpp"
                  % (key, st["n_rows"], st["win"], st["pnl"],
                     g1["win"], g1["pnl"], g1["win"] - st["win"], g1["pnl"] - st["pnl"]))
        res["exit_assumption"] = {
            "buy": "T+1 开盘（真实可得，无日内路径问题）",
            "fixed": "仅跳空：触发日开盘已穿止损/止盈线 → 按开盘价成交",
            "note": "止损跳空更差、止盈跳空更好，净方向由实测决定；选股规则与阈值一律未改。",
            "tiers": ea_t}

    out = os.path.join(_HERE, "_3yl_tier_gate_step%s.json" % a.step) if a.sens \
        else os.path.join(_HERE, "_3yl_tier_gate.json")
    json.dump(res, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("[3yl] 写 %s" % out)
    if not a.no_html and not a.sens and not a.limit:
        import _3yl_gate_page as P
        P.render(res)


if __name__ == "__main__":
    main()
