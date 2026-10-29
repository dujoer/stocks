# -*- coding: utf-8 -*-
"""顾比倒数线 · 入场口径变体扫描（canonical 逐日平衡 edge + 随机对照）。

目的：判断「收盘站上倒数入场线」这条原生规则本身有没有超额，以及哪些可选过滤
能把有超额的子集挑出来。**这不是把负结果调成正结果的工具**——随机对照用于回答
「这个 edge 是不是随手抽同等数量也能抽出来」。

用法：python3 quant/_guppy_variants.py --asof 60 --tp 0.06 --sl 0.08 --fwd 10
"""
from __future__ import annotations
import argparse
import json
import os
import random
import sys

QUANT = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(QUANT)
sys.path.insert(0, QUANT)
os.chdir(ROOT)

import _txk                            # noqa: E402
import _gate_common as GC              # noqa: E402
import _guppy_core as GU               # noqa: E402
import build_n_shape as NS             # noqa: E402
import build_n_shape_backtest as BT    # noqa: E402

OUT_DIR = os.path.join(QUANT, "guppy")
BOOT = 800
RAND_N = 200          # ★ 随机对照次数必须固定，否则同一份数据两次跑出两个数
RAND_SEED = 20261029
BJ_PREFIX = ("bj", "8", "4")   # 北交所代码前缀粗筛（同 NS.EXCLUDE_BJ 口径）
AMT_MIN = 30_000_000


def _is_bj(code):
    c = (code or "").lower()
    return c.startswith("bj") or c.startswith("8") or c.startswith("4")


def _amt20(code, bars, end):
    """end 处近 20 根的日均成交额（元）。K 线缓存无 amount 字段，必须换算。"""
    try:
        from _mkt_emo import amount_of
    except Exception:
        return None
    seg = bars[max(0, end - 19):end + 1]
    vals = [amount_of(code, b.get("last"), b.get("volume")) for b in seg]
    vals = [v for v in vals if v]
    return sum(vals) / len(vals) if vals else None


def pick_dates(cache, n, fwd, offset=0):
    """最近 n 个（再往前让出 offset 个）具备 >= fwd 个后续交易日的回测日。

    offset 用于**跨窗口复核**：同一结论必须在相邻的不同时间段都成立，
    否则只是锁在一段行情里。
    """
    rep = next((v for v in cache.values() if isinstance(v, list) and v), None)
    if not rep:
        return []
    ds = sorted(b["date"] for b in rep)
    cand = [d for i, d in enumerate(ds) if (len(ds) - 1 - i) >= fwd]
    end = max(0, len(cand) - offset)
    return cand[max(0, end - n):end]


def build_idx_map(cache):
    return {c: {b.get("date"): i for i, b in enumerate(bs)}
            for c, bs in cache.items() if isinstance(bs, list) and bs}


def scan_all(cache, idx_map, dates, cb_n):
    """扫全部 as-of 日，返回「可评估 + 有前向结果」的行（对照域）。"""
    rows = []
    for d in dates:
        for code, bs in cache.items():
            if not isinstance(bs, list) or len(bs) < GU.MIN_BARS:
                continue
            im = idx_map.get(code)
            if not im:
                continue
            i = im.get(d)
            if i is None:
                continue
            st = GU.eval_stock(code, bs, i, cb_n=cb_n)
            if st is None:
                continue
            ft = BT.fwd_first_touch(cache, st, TP, SL, FWD)
            if ft is None:
                continue
            st["date"] = d
            st["pnl"] = ft["ret"] * 100.0
            st["win"] = bool(ft["win"])
            rows.append(st)
    return rows


def _tradable(r):
    if _is_bj(r["code"]):
        return False
    a = r.get("amt20")
    return a is not None and a >= AMT_MIN


def variants():
    """变体名 -> 谓词。全部基于当日已知信息，无未来函数。"""
    def above_line(r):
        return bool(r.get("above"))
    return {
        "raw_cross_up":        lambda r: bool(r.get("cross_up")),
        "cu_ma20":             lambda r: bool(r.get("cross_up")) and bool(r.get("above_ma20")),
        "cu_ma60":             lambda r: bool(r.get("cross_up")) and bool(r.get("above_ma60")),
        "cu_ma20_up":          lambda r: bool(r.get("cross_up")) and bool(r.get("ma20_up")),
        "cu_vol15":            lambda r: bool(r.get("cross_up")) and (r.get("vol_ratio") or 0) >= 1.5,
        "cu_fresh_pivot10":    lambda r: bool(r.get("cross_up")) and (r.get("pivot_age") or 99) <= 10,
        "cu_cb_age_le20":      lambda r: bool(r.get("cross_up")) and (r.get("cb_age") or 999) <= 20,
        "cu_cb_age_gt40":      lambda r: bool(r.get("cross_up")) and (r.get("cb_age") or 0) > 40,
        "cu_ret20_le10":       lambda r: bool(r.get("cross_up")) and (r.get("ret20") is not None) and r["ret20"] <= 10,
        "cu_novol_surge":      lambda r: bool(r.get("cross_up")) and (r.get("vol_ratio") or 0) <= 1.5,
        "confirm2":            lambda r: r.get("days_above") == 2,
        "confirm3":            lambda r: r.get("days_above") == 3,
        "held_gt3":            lambda r: above_line(r) and (r.get("days_above") or 0) > 3,
        "combo_core":          lambda r: bool(r.get("cross_up")) and bool(r.get("above_ma20"))
                                         and (r.get("vol_ratio") or 0) >= 1.2,
        "combo_full":          lambda r: bool(r.get("cross_up")) and bool(r.get("above_ma20"))
                                         and (r.get("vol_ratio") or 0) >= 1.2
                                         and (r.get("ret20") is not None) and r["ret20"] <= 15,
        "stop_break":          lambda r: bool(r.get("stop_break")),
    }


def rand_control(rows, sel_fn, obs_edge, boots=RAND_N):
    """随机对照：每日抽同等数量的行，重复 boots 次，看有多少次 edge ≥ 实际 edge。

    返回 (p_ge, rand_edges_mean)。p_ge 越小说明信号越不像「随手一抽」。
    """
    byd = {}
    for r in rows:
        byd.setdefault(r["date"], []).append(r)
    cnt = {d: sum(1 for r in rs if sel_fn(r)) for d, rs in byd.items()}
    rnd = random.Random(RAND_SEED)
    ges = 0
    edges = []
    tot = 0
    for _ in range(boots):
        chosen = set()
        for d, c in cnt.items():
            if c <= 0:
                continue
            rs = byd[d]
            for x in rnd.sample(rs, min(c, len(rs))):
                chosen.add(id(x))
        tot += 1
        st = GC.edge_stats(rows, lambda r, ch=chosen: id(r) in ch,
                           lambda r: True, boot=200, seed=RAND_SEED, name="rand")
        ed = st.get("edge")
        if ed is None:
            continue
        edges.append(ed)
        if ed >= obs_edge:
            ges += 1
    if not edges:
        return None, None
    return round(ges / tot, 4), round(sum(edges) / len(edges), 4)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None)
    ap.add_argument("--asof", type=int, default=60)
    ap.add_argument("--cb", type=int, default=GU.CB_N)
    ap.add_argument("--tp", type=float, default=0.06)
    ap.add_argument("--sl", type=float, default=0.08)
    ap.add_argument("--fwd", type=int, default=10)
    ap.add_argument("--tradable-only", action="store_true")
    ap.add_argument("--offset", type=int, default=0,
                    help="往前让出 N 个回测日，用于跨窗口复核")
    ap.add_argument("--rand", action="store_true", help="对全部变体跑随机对照（慢）")
    a = ap.parse_args()

    global TP, SL, FWD
    TP, SL, FWD = a.tp, a.sl, a.fwd

    D = a.date or NS.latest_date()
    DS = D.replace("-", "")
    print("=== 顾比口径变体扫描 · 数据日 %s · %d 个 as-of 日 · 首触 +%g%%/-%g%%/%d日 ==="
          % (D, a.asof, a.tp * 100, a.sl * 100, a.fwd))

    _txk.set_asof(D)
    cache = _txk.load()
    idx_map = build_idx_map(cache)
    dates = pick_dates(cache, n=a.asof, fwd=a.fwd, offset=a.offset)
    print("窗口 %s → %s（%d 日，offset=%d）"
          % (dates[0], dates[-1], len(dates), a.offset))

    rows = scan_all(cache, idx_map, dates, a.cb)
    for r in rows:
        r["amt20"] = _amt20(r["code"], cache.get(r["code"]) or [], r["asof_idx"])
        r["_tradable"] = _tradable(r)
    domain = [r for r in rows if r["_tradable"]] if a.tradable_only else rows
    print("对照域行数：全市场 %d｜可交易口径 %d｜本次使用 %d"
          % (len(rows), sum(1 for r in rows if r["_tradable"]), len(domain)))

    out = {"date": D, "asof_dates": len(dates), "window": [dates[0], dates[-1]],
           "cb_n": a.cb, "tp": a.tp, "sl": a.sl, "fwd": a.fwd,
           "boot": BOOT, "rand_n": RAND_N,
           "n_domain": len(domain), "variants": {}}
    print("\n%-20s %6s %8s %7s %9s %8s" % ("变体", "n_rows", "edge(pp)", "R3%", "留一下限", "胜率%"))
    for name, fn in variants().items():
        st = GC.edge_stats(domain, fn, lambda r: True, boot=BOOT, name=name)
        if st.get("edge") is None:
            print("%-20s %6s  %s" % (name, st.get("n_rows"), st.get("note", "样本不足")))
            out["variants"][name] = {"n_rows": st.get("n_rows"), "note": st.get("note")}
            continue
        rec = {"n_rows": st["n_rows"], "n_days": st["n_days"], "edge": st["edge"],
               "r3": st["r3"], "loo_min": st["loo_min"], "win": st["win"],
               "pnl": st["pnl"], "ctrl_pnl": st["ctrl_pnl"]}
        print("%-20s %6d %8.3f %7.1f %9.3f %8.2f"
              % (name, st["n_rows"], st["edge"], st["r3"], st["loo_min"], st["win"]))
        out["variants"][name] = rec

    if a.rand:
        print("\n---- 随机对照（每日等额随机抽样 × %d 次，固定种子 %d）----" % (RAND_N, RAND_SEED))
        print("  p = 随机抽样 edge ≥ 该变体实际 edge 的比例；p 越小越不像噪声")
        for name, fn in variants().items():
            st = GC.edge_stats(domain, fn, lambda r: True, boot=BOOT, name=name)
            if st.get("edge") is None:
                continue
            p, mean_e = rand_control(domain, fn, st["edge"])
            print("  %-20s edge=%+.3fpp  随机均值=%+.3fpp  p=%.3f"
                  % (name, st["edge"], mean_e if mean_e is not None else float("nan"), p))
            out["variants"][name]["rand_p"] = p
            out["variants"][name]["rand_edge_mean"] = mean_e

    os.makedirs(OUT_DIR, exist_ok=True)
    tail = "_tradable" if a.tradable_only else ""
    if a.offset:
        tail += "_off%d" % a.offset
    p = os.path.join(OUT_DIR, "variants_%s%s.json" % (DS, tail))
    json.dump(out, open(p, "w", encoding="utf-8"), ensure_ascii=False,
              indent=1, sort_keys=True)
    print("\n存档：%s" % p)


if __name__ == "__main__":
    main()
