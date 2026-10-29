# -*- coding: utf-8 -*-
"""顾比倒数线 ·「止损线作为动态离场规则」配对回测。

实验设计（不是问「哪批票能涨」，而是问「同一个开仓，用什么规则离场更好」）
    每个样本 = (个股, 开仓日)，开仓统一按当日收盘价买入 —— 有意不用任何入场信号，
    这样两条腿唯一的差别就是**离场规则**，差异干净可归因。
    A 腿：固定持有 hold 个交易日后收盘了结
    B 腿：逐日重算倒数止损线，收盘跌破 → 次日开盘离场；未跌破则持有到期
    逐日配对 Δ = mean(B) − mean(A)，再按日 block bootstrap 求 R3 = P(Δ>0)。

跨步长：默认跑 step5 / step10 两个采样频率，**必须同号**才算结论成立。

用法：python3 quant/_guppy_exit.py --hold 20 --step 5
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

import _txk                       # noqa: E402
import _guppy_core as GU          # noqa: E402
import build_n_shape as NS        # noqa: E402

OUT_DIR = os.path.join(QUANT, "guppy")
BOOT = 2000
SEED = 20261029


def all_dates(cache, fwd):
    rep = next((v for v in cache.values() if isinstance(v, list) and v), None)
    if not rep:
        return []
    ds = sorted(b["date"] for b in rep)
    return [d for i, d in enumerate(ds) if (len(ds) - 1 - i) >= fwd]


def _leg_A(bars, i, hold):
    """固定持有 hold 日，末日收盘了结；不足则用最后一根收盘。"""
    entry = bars[i].get("last")
    j = min(i + hold, len(bars) - 1)
    if j <= i or not entry:
        return None
    return bars[j]["last"] / entry - 1


def _leg_B(cache_code_bars, i, hold):
    """倒数止损线动态离场（每日收盘重算，跌破次日开盘走）。"""
    bars = cache_code_bars
    entry = bars[i].get("last")
    if not entry:
        return None
    upper = min(i + hold + 1, len(bars))
    for k in range(i + 1, upper):
        c = bars[k].get("last")
        sl = GU.stop_line_at(bars, k)
        if c is not None and sl is not None and c < sl:
            if k + 1 < len(bars):
                px = bars[k + 1].get("open") or bars[k + 1].get("last")
            else:
                px = bars[k]["last"]
            if not px:
                return None
            return px / entry - 1
    last = upper - 1
    if last <= i:
        return None
    return bars[last]["last"] / entry - 1


def run(cache, idx_map, dates, hold, step):
    """返回 {date: (mean_A, mean_B, n)}。"""
    out = {}
    for di in range(0, len(dates), step):
        d = dates[di]
        a_vals, b_vals = [], []
        for code, bs in cache.items():
            if not isinstance(bs, list) or len(bs) < GU.MIN_BARS:
                continue
            im = idx_map.get(code)
            if not im:
                continue
            i = im.get(d)
            if i is None or i + hold >= len(bs):
                continue
            va = _leg_A(bs, i, hold)
            vb = _leg_B(bs, i, hold)
            if va is None or vb is None:
                continue
            a_vals.append(va * 100.0)
            b_vals.append(vb * 100.0)
        if len(a_vals) >= 30:
            out[d] = (sum(a_vals) / len(a_vals), sum(b_vals) / len(b_vals),
                      len(a_vals))
    return out


def boot_r3(diffs, boot=BOOT, seed=SEED):
    rnd = random.Random(seed)
    if not diffs:
        return None
    pos = 0
    for _ in range(boot):
        s = sum(diffs[rnd.randrange(len(diffs))] for _ in range(len(diffs)))
        if s > 0:
            pos += 1
    return round(pos / boot * 100.0, 1)


def report(tag, per_day, boot=BOOT):
    ds = sorted(per_day)
    if len(ds) < 5:
        print("  %s 样本日不足（%d）" % (tag, len(ds)))
        return None
    diffs = [per_day[d][1] - per_day[d][0] for d in ds]
    obs = sum(diffs) / len(diffs)
    ma = sum(per_day[d][0] for d in ds) / len(ds)
    mb = sum(per_day[d][1] for d in ds) / len(ds)
    pos_days = sum(1 for x in diffs if x > 0)
    loo = []
    for k in range(len(diffs)):
        rest = [diffs[j] for j in range(len(diffs)) if j != k]
        loo.append(sum(rest) / len(rest))
    h = len(diffs) // 2
    fh = sum(diffs[:h]) / max(1, h)
    sh = sum(diffs[h:]) / max(1, len(diffs) - h)
    r3 = boot_r3(diffs, boot=boot)
    print("  %-8s 样本日=%2d  固定持有=%+7.3f%%  倒数止损离场=%+7.3f%%  Δ=%+6.3fpp  "
          "R3=%5.1f%%  正 Δ 日=%d/%d  前半=%+.3f 后半=%+.3f  留一=[%+.3f,%+.3f]"
          % (tag, len(ds), ma, mb, obs, r3, pos_days, len(ds), fh, sh,
             min(loo), max(loo)))
    return {"tag": tag, "n_days": len(ds), "hold_A": round(ma, 3),
            "stop_B": round(mb, 3), "delta": round(obs, 3), "r3": r3,
            "pos_days": pos_days, "half_first": round(fh, 3),
            "half_second": round(sh, 3), "loo_min": round(min(loo), 3),
            "loo_max": round(max(loo), 3),
            "days": [{"date": d, "A": round(per_day[d][0], 3),
                      "B": round(per_day[d][1], 3), "n": per_day[d][2]}
                     for d in ds]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None)
    ap.add_argument("--hold", type=int, default=20)
    ap.add_argument("--steps", default="5,10")
    ap.add_argument("--ndates", type=int, default=120)
    ap.add_argument("--boot", type=int, default=BOOT)
    a = ap.parse_args()

    D = a.date or NS.latest_date()
    DS = D.replace("-", "")
    print("=== 顾比倒数止损线 · 离场规则配对回测 · 持有上限 %d 日 ===" % a.hold)
    _txk.set_asof(D)
    cache = _txk.load()
    idx_map = {c: {b.get("date"): i for i, b in enumerate(bs)}
               for c, bs in cache.items() if isinstance(bs, list) and bs}
    dates = all_dates(cache, a.hold + 2)[-a.ndates:]
    print("可用开仓日 %d 个：%s → %s" % (len(dates), dates[0], dates[-1]))

    out = {"date": D, "hold": a.hold, "boot": a.boot, "seed": SEED, "res": {}}
    for s in [int(x) for x in a.steps.split(",") if x.strip()]:
        per = run(cache, idx_map, dates, a.hold, s)
        r = report("step%-3d" % s, per, boot=a.boot)
        out["res"]["step%d" % s] = r

    res = {k: v for k, v in out["res"].items() if v}
    if len(res) >= 2:
        same = len({(v["delta"] > 0) for v in res.values()}) == 1
        print("\n跨步长同号：%s（%s）"
              % ("是" if same else "否",
                 "，".join("%s Δ=%+.3fpp" % (k, v["delta"]) for k, v in res.items())))
        out["cross_step_same_sign"] = bool(same)
        min_r3 = min(v["r3"] for v in res.values())
        out["min_r3"] = min_r3
        print("最差步长 R3 = %.1f%%  → %s"
              % (min_r3, "两步长同号且 R3 均高，离场规则可采信"
                 if (same and min_r3 >= 95) else "尚不构成可靠结论，按观察处理"))

    os.makedirs(OUT_DIR, exist_ok=True)
    p = os.path.join(OUT_DIR, "exit_pair_%s.json" % DS)
    json.dump(out, open(p, "w", encoding="utf-8"), ensure_ascii=False,
              indent=1, sort_keys=True)
    print("\n存档：%s" % p)


if __name__ == "__main__":
    main()
