# -*- coding: utf-8 -*-
"""顾比倒数线 · 历史回测（描述性证据，非出票判定）。

三条口径，全部输出到 JSON 供页面引用（页面不得写死数字）：
  A 绝对收益  信号股（收盘首次站上倒数入场线）前向表现，首触法 +tp/-sl/fwd 收盘判定
  B 相对 edge  canonical 逐日平衡 edge，对照域 = 当日全部可评估个股（_gate_common）
  C 原生规则   顾比倒数止损线动态跟踪出场（每日收盘重算，跌破次日开盘离场）

用法：python3 quant/build_guppy_backtest.py --date YYYY-MM-DD [--asof 60] [--cb 3]
"""
from __future__ import annotations
import argparse
import json
import os
import sys

QUANT = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(QUANT)
sys.path.insert(0, QUANT)

os.chdir(ROOT)

import _txk                       # noqa: E402
import _gate_common as GC         # noqa: E402
import _guppy_core as GU          # noqa: E402
import build_n_shape as NS        # noqa: E402
import build_n_shape_backtest as BT  # noqa: E402

OUT_DIR = os.path.join(QUANT, "guppy")


def build_idx_map(cache):
    return {c: {b.get("date"): i for i, b in enumerate(bs)}
            for c, bs in cache.items() if isinstance(bs, list) and bs}


def scan_day(cache, idx_map, d, cb_n):
    """扫描单个 as-of 日的全市场，返回所有「可评估」的行。"""
    rows = []
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
        if st is not None:
            rows.append(st)
    return rows


def agg(rows):
    """绝对口径：胜率/均值/盈亏比（pp）。"""
    if not rows:
        return None
    n = len(rows)
    w = sum(1 for r in rows if r.get("pnl", 0) > 0)
    avg = sum(r.get("pnl", 0) for r in rows) / n
    wins = [r["pnl"] for r in rows if r.get("pnl", 0) > 0]
    loss = [r["pnl"] for r in rows if r.get("pnl", 0) <= 0]
    aw = sum(wins) / len(wins) if wins else 0.0
    al = sum(loss) / len(loss) if loss else 0.0
    return {"n": n, "win": round(w / n * 100, 2), "avg": round(avg, 3),
            "avg_win": round(aw, 3), "avg_loss": round(al, 3),
            "pl": round(abs(aw / al), 3) if al else None}


def trail_exit(cache, code, aidx, max_hold, cb_n):
    """顾比原生规则出场：持仓期内每日收盘重算倒数止损线，跌破则次日开盘离场。

    无未来函数：第 k 日只用 bars[:k+1]（eval_stock 内部以 end=k 为界）。
    返回 (ret, hold_days, reason)。
    """
    bars = cache.get(code)
    if not bars or aidx is None or aidx + 1 >= len(bars):
        return None
    entry = bars[aidx]["last"]
    if not entry:
        return None
    upper = min(aidx + max_hold + 1, len(bars))
    for k in range(aidx + 1, upper):
        st = GU.eval_stock(code, bars, k, cb_n=cb_n)
        if st is None:
            continue
        sl_line = st.get("stop_line")
        if sl_line is not None and st["close"] < sl_line:
            if k + 1 < len(bars):
                exit_px = bars[k + 1].get("open") or bars[k + 1].get("last")
                hold = k + 1 - aidx
            else:
                exit_px = bars[k]["last"]
                hold = k - aidx
            return (exit_px / entry - 1, hold, "倒数止损线跌破(次日开盘离场)")
    last = upper - 1
    return (bars[last]["last"] / entry - 1, last - aidx, "持有到期(末日收盘)")


def hold_exit(cache, code, aidx, days):
    """对照：固定持有 days 交易日，按末日收盘了结。"""
    bars = cache.get(code)
    if not bars or aidx is None:
        return None
    entry = bars[aidx]["last"]
    if not entry:
        return None
    j = min(aidx + days, len(bars) - 1)
    if j <= aidx:
        return None
    return (bars[j]["last"] / entry - 1, j - aidx, "固定持有")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None)
    ap.add_argument("--asof", type=int, default=60)
    ap.add_argument("--cb", type=int, default=GU.CB_N)
    ap.add_argument("--tp", type=float, default=0.10)
    ap.add_argument("--sl", type=float, default=0.08)
    ap.add_argument("--fwd", type=int, default=10)
    ap.add_argument("--hold", type=int, default=20)
    a = ap.parse_args()

    D = a.date or NS.latest_date()
    DS = D.replace("-", "")
    print("=== 顾比倒数线 回测 · 数据日 %s · as-of %d 日 · 倒数 %d 条 ==="
          % (D, a.asof, a.cb))

    _txk.set_asof(D)
    cache = _txk.load()
    print("缓存个股 %d 只" % len(cache))
    idx_map = build_idx_map(cache)

    dates = BT.pick_asof_dates(cache, n=a.asof, fwd=max(a.fwd, a.hold))
    print("as-of 交易日 %d 个：%s → %s" % (len(dates), dates[0], dates[-1]))

    rows = []
    per_day = {}
    for d in dates:
        day = scan_day(cache, idx_map, d, a.cb)
        try:
            heat = NS.load_market_heat(d)
            lab = heat.get("label") if isinstance(heat, dict) else None
        except Exception:
            lab = None
        kept = []
        for r in day:
            ft = BT.fwd_first_touch(cache, r, a.tp, a.sl, a.fwd)
            if ft is None:
                continue
            r["date"] = d
            r["heat"] = lab
            r["pnl"] = ft["ret"] * 100.0
            r["win"] = bool(ft["win"])
            kept.append(r)
        rows.extend(kept)
        per_day[d] = {"n": len(kept),
                      "n_sig": sum(1 for r in kept if r["cross_up"]),
                      "heat": lab}
        print("  %s 可评估 %4d 只｜信号 %3d 只｜热度 %s"
              % (d, len(kept), per_day[d]["n_sig"], lab))

    sig_rows = [r for r in rows if r["cross_up"]]
    out = {
        "date": D, "asof_dates": len(dates), "window": [dates[0], dates[-1]],
        "cb_n": a.cb, "params": {"tp": a.tp, "sl": a.sl, "fwd": a.fwd, "hold": a.hold},
        "n_rows": len(rows), "n_signal": len(sig_rows),
        "per_day": per_day,
    }
    print("\n---- A 绝对口径（首触法 +%g%%/-%g%%/%d日，收盘判定）----"
          % (a.tp * 100, a.sl * 100, a.fwd))
    base = agg(rows)
    sa = agg(sig_rows)
    print("  全市场对照组 n=%d 胜率=%.2f%% 均=%+.3f%% 盈亏比=%s"
          % (base["n"], base["win"], base["avg"], base["pl"]))
    print("  信号组      n=%d 胜率=%.2f%% 均=%+.3f%% 盈亏比=%s"
          % (sa["n"], sa["win"], sa["avg"], sa["pl"]))
    out["abs_all"], out["abs_signal"] = base, sa

    print("\n---- B 相对口径（canonical 逐日平衡 edge，对照域=当日全部可评估）----")
    try:
        st = GC.edge_stats(rows, lambda r: r["cross_up"], lambda r: True,
                           name="cross_up")
        for k in ("n_rows", "edge", "r3", "loo_min", "win", "pnl", "ctrl_pnl"):
            print("  %-9s %s" % (k, st.get(k)))
        out["edge_signal"] = {k: st.get(k) for k in
                              ("n_rows", "edge", "r3", "loo_min", "win",
                               "pnl", "ctrl_pnl", "days")}
    except Exception as e:
        print("  [跳过] %s" % e)
        out["edge_signal"] = None

    print("\n---- C 顾比原生规则（倒数止损线动态跟踪，跌破次日开盘离场）----")
    tr, hd = [], []
    for r in sig_rows:
        t = trail_exit(cache, r["code"], r["asof_idx"], a.hold, a.cb)
        if t:
            tr.append({"code": r["code"], "date": r["date"], "ret": t[0] * 100,
                       "hold": t[1], "reason": t[2]})
        h = hold_exit(cache, r["code"], r["asof_idx"], a.hold)
        if h:
            hd.append({"code": r["code"], "date": r["date"], "ret": h[0] * 100,
                       "hold": h[1], "reason": h[2]})
    def _a2(rs, tag):
        if not rs:
            print("  %s 无样本" % tag)
            return None
        n = len(rs)
        w = sum(1 for x in rs if x["ret"] > 0)
        avg = sum(x["ret"] for x in rs) / n
        holds = sum(x["hold"] for x in rs) / n
        print("  %-10s n=%-4d 胜率=%6.2f%% 均=%+7.3f%% 均持有=%.1f日"
              % (tag, n, w / n * 100, avg, holds))
        return {"n": n, "win": round(w / n * 100, 2), "avg": round(avg, 3),
                "hold": round(holds, 1)}
    out["native_exit"] = _a2(tr, "止损线出场")
    out["hold_exit"] = _a2(hd, "固定持有")
    if tr and hd:
        diff = out["native_exit"]["avg"] - out["hold_exit"]["avg"]
        print("  配对差异（止损线出场 − 固定持有）= %+.3fpp" % diff)
        out["exit_pair_diff"] = round(diff, 3)
    reasons = {}
    for x in tr:
        reasons[x["reason"]] = reasons.get(x["reason"], 0) + 1
    out["exit_reasons"] = reasons
    print("  出场原因分布：%s" % reasons)

    print("\n---- 热度分桶（信号组绝对口径）----")
    buckets = {}
    for r in sig_rows:
        k = r.get("heat") or "未知"
        buckets.setdefault(k, []).append(r)
    out["heat_buckets"] = {}
    for k in sorted(buckets):
        ag = agg(buckets[k])
        out["heat_buckets"][k] = ag
        print("  %-6s n=%-4d 胜率=%6.2f%% 均=%+7.3f%% 盈亏比=%s"
              % (k, ag["n"], ag["win"], ag["avg"], ag["pl"]))

    os.makedirs(OUT_DIR, exist_ok=True)
    p = os.path.join(OUT_DIR, "backtest_%s.json" % DS)
    json.dump(out, open(p, "w", encoding="utf-8"), ensure_ascii=False,
              indent=1, sort_keys=True)
    print("\n存档：%s" % p)
    return out


if __name__ == "__main__":
    main()
