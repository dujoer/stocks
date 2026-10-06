# -*- coding: utf-8 -*-
"""龙道诀四阶段「能不能拿来做仓位/开仓规则」的预注册检验（2026-10-06）。

★ 为什么还要再测一次
------------------------------------------------------------
`_dragon_odds` 已测过一件事：**打板持仓收益**在四阶段里全负（24 格扣成本净正 0）。
但那只说明「这个打法在这些阶段里都亏」，**推不出**「阶段有没有择时价值」。
阶段唯一可能有用的路径：它能不能**提前告诉你接下来市场会怎样**。本脚本就测这一条。

标的口径：全市场等权日收益 —— **不是任何个股**（本项目红线：不推个股、不出票）。

★ 预注册判据（跑之前写死，不再挑好看的）
------------------------------------------------------------
    P1 相对：阶段均 − 全样本均 > 0            （赢基线）
    P2 绝对：阶段均 − 单次往返成本 COST > 0    （真能赚）
    P3 稳健：前半段与后半段**同号**            （防单窗口挑优）
★ 三条**全过** → 该阶段才可用于「仓位/开仓」；
  任一条不过 → 该阶段**只当状态描述（温度计）**，不许写进任何开仓/加仓/减仓规则，
  也不许在页面上暗示它能提高收益。

★ 复用纪律（不许另抄一份）
    * 情绪逐日序列直接 `import _dragon_odds` 调 `scan()` —— zt/zb/hi/eq 与页面同源。
    * 阶段判定走 `_mkt_emo.stage_series()` 唯一实现。
    * 日K 走 `_longk.load_long()` 唯一入口（不回退短缓存）。

用法：
    python3 quant/_dragon_stage_use.py                  # 长历史（默认）
    python3 quant/_dragon_stage_use.py --src short      # 短缓存（仅对拍）
    python3 quant/_dragon_stage_use.py --selftest       # 判据自测
"""
from __future__ import annotations

import os
import sys
import json
import random
import argparse

QUANT = os.path.dirname(os.path.abspath(__file__))
if QUANT not in sys.path:
    sys.path.insert(0, QUANT)

import _longk as LK          # 长历史日K 唯一入口
import _dragon_odds as DO    # 逐日情绪 + 全市场等权日收益（同源，不重抄）
import _mkt_emo as M         # 四阶段判定唯一实现

COST = 0.002          # 单次往返成本（0.2%），与 _dragon_odds 的 EXEC_COST 同口径
BOOT = 2000           # ★ bootstrap 次数固定，不随跑次变（改一次＝另一次实验）
BLOCK = 21            # 按日 block 长度（≈1 个月），整日整日抽
SEED = 20261006
HOLDS = (5, 10, 20)
STAGES = ("退潮", "高潮", "回暖", "冰点")
MIN_N = 5             # 某阶段样本少于这个数 → 判「样本不足」，不编数


# --------------------------------------------------------------- 阶段与前向收益
def stage_map(series):
    """[{date,zt,zb,hi,eq}] → {date: 阶段名}。判定走唯一实现，与页面同源。"""
    thin = [
        dict(date=row["date"], zt=row["zt"],
             hi=row["hi"], rate=row.get("rate") or 0.0)
        for row in series
    ]
    return M.stage_series(thin)


def fwd_from_eq(eqs, i, hold):
    """从 i 之后 hold 个交易日复利。缺日（停牌/无数据）→ None —— **丢样，不糊弄**。"""
    if i + hold >= len(eqs):
        return None
    for j in range(i + 1, i + hold + 1):
        if eqs[j] is None:
            return None
    acc = 1.0
    for j in range(i + 1, i + hold + 1):
        acc *= (1.0 + eqs[j])
    return acc - 1.0


def _boot_edge_ratio(vals, stgs, hit_stage, block=BLOCK, n_boot=BOOT, seed=SEED):
    """按日 block bootstrap：整日整日地重抽，重算「阶段均 − 全样本均」，返回 edge>0 比例。

    前向窗口重叠 → 样本非独立，不能用朴素正态近似（会严重低估误差）。
    """
    n = len(vals)
    if n < 2 * block:
        return None
    rng = random.Random(seed)
    hit = 0
    for _ in range(n_boot):
        picked = []
        while len(picked) < n:
            start = rng.randrange(0, n)
            picked.extend(range(start, min(start + block, n)))
        picked = picked[:n]
        tot = 0.0
        cnt = 0
        sub = 0.0
        subn = 0
        for pos in picked:
            val = vals[pos]
            if val is None:
                continue
            tot += val
            cnt += 1
            if stgs[pos] == hit_stage:
                sub += val
                subn += 1
        if cnt == 0 or subn == 0:
            continue
        if (sub / subn) > (tot / cnt):
            hit += 1
    return hit / float(n_boot)


def _half_split(pairs):
    """按**信号日顺序**切前后半（不是按收益值），返回 (前半均值, 后半均值)。"""
    half = len(pairs) // 2
    def _mean(block_pairs):
        vals = [v for _, v in block_pairs]
        return (sum(vals) / len(vals)) if vals else None
    return _mean(pairs[:half]), _mean(pairs[half:])


def analyze(series, stg, holds=HOLDS):
    """逐 hold 出四阶段的前向收益统计 + 三态结论。"""
    dates = [row["date"] for row in series]
    eqs = [row.get("eq") for row in series]

    out = {}
    for hold in holds:
        pairs = []          # [(stage, fwd)]
        span = {}           # stage -> [首日, 末日]（看样本是不是集中在某段行情）
        for i, d in enumerate(dates):
            eq_now = eqs[i]
            st = stg.get(d)
            if eq_now is None or st not in STAGES:
                continue
            fv = fwd_from_eq(eqs, i, hold)
            if fv is None:
                continue
            pairs.append((st, fv))
            # ⚠ 顺序别写反：首日是**最早**那次见到的 d
            cur = span.get(st)
            span[st] = ([cur[0], d] if cur else [d, d])

        n_all = len(pairs)
        if n_all < 30:
            out[str(hold)] = dict(n=n_all, note="样本不足（<30），本窗口不可判")
            continue

        vals = [v for _, v in pairs]
        mu_all = sum(vals) / n_all
        h1, h2 = _half_split(pairs)

        # ---- 第二道控制：按「当日全市场涨幅分位」配对（剥离短期动量）----
        #  替代解释：高潮＝涨停家数高位≈市场本来就在涨，「后续涨」可能只是当日涨幅的
        #  动量延续。若一个阶段只落在高档分位，那么拿**同分位档**的 fwd 当对照才公平。
        #  分位用 _mkt_emo.rolling_pctile（唯一实现，只看过去 60 日）。
        #  ⚠ 该控制是看到主结果（P1/P2/P3）之后才加的，只会让结论更保守，不会更好看。
        buckets = {}
        for i, d in enumerate(dates):
            eq_now = eqs[i]
            st = stg.get(d)
            if eq_now is None or st not in STAGES:
                continue
            fv = fwd_from_eq(eqs, i, hold)
            if fv is None:
                continue
            pct = M.rolling_pctile(eqs, i)          # 当日等权涨幅的 60 日分位
            if pct is None:
                continue
            bk = min(4, int(pct // 20))             # 0~4 五档：0-20/20-40/40-60/60-80/80-100
            buckets.setdefault(bk, []).append((st, fv))

        cells = {}
        for st in STAGES:
            sub = [v for s, v in pairs if s == st]
            if len(sub) < MIN_N:
                cells[st] = dict(n=len(sub), verdict="样本不足")
                continue
            mean = sum(sub) / len(sub)
            edge = mean - mu_all
            net = mean - COST
            r3 = _boot_edge_ratio(vals, [s for s, _ in pairs], st)

            # 同分位档对照：对该阶段**实际占用的每个档位**，取「同档位的全部日子」的 fwd 均值
            # （不只是该阶段的日子），再按该阶段在各档位的样本数加权平均。
            # ⚠ 不能把所有档位先混成一个池再平均 —— 那就绕回了 stage_mean，edge 恒 0。
            num = 0.0
            den = 0
            bucket_span = []
            per_bucket = {}
            for bk, lst in buckets.items():
                mine = [v2 for (s2, v2) in lst if s2 == st]
                if not mine:
                    continue
                all_in_bucket = [v2 for (_s2, v2) in lst]
                bm = sum(all_in_bucket) / len(all_in_bucket)
                per_bucket[str(bk)] = dict(n_stage=len(mine),
                                           n_all=len(all_in_bucket),
                                           bucket_mean=bm)
                bucket_span.append(bk)
                num += len(mine) * bm
                den += len(mine)
            matched = (num / den) if den else None
            edge_matched = (mean - matched) if matched is not None else None
            bucket_span = sorted(bucket_span)

            p1 = edge > 0
            p2 = net > 0

            # P3 前后半：按**该阶段信号日出现的先后顺序**切（不是按收益值切）
            idxs = [k for k in range(n_all) if pairs[k][0] == st]
            half = len(idxs) // 2

            def _m(ks):
                vs = [pairs[k][1] for k in ks]
                return (sum(vs) / len(vs)) if vs else None

            ph1, ph2 = _m(idxs[:half]), _m(idxs[half:])
            p3 = (ph1 is not None and ph2 is not None
                  and ((ph1 > 0 and ph2 > 0) or (ph1 < 0 and ph2 < 0)))
            sp = span.get(st) or [None, None]
            cells[st] = dict(n=len(sub), mean=mean, edge=edge, net=net,
                             r3=r3, half1=ph1, half2=ph2,
                             first_date=sp[0], last_date=sp[1],
                             matched=matched, edge_matched=edge_matched,
                             bucket_span=bucket_span, per_bucket=per_bucket,
                             p1_rel=p1, p2_abs=p2, p3_same=p3,
                             verdict=("可用（仓位/开仓）" if (p1 and p2 and p3 and
                                      edge_matched is not None and edge_matched > 0)
                                      else ("不可用" if not (p1 and p2 and p3)
                                            else "赢基线但没赢动量")))
        out[str(hold)] = dict(n=n_all, baseline=mu_all, cost=COST, cells=cells)
    return out


# ------------------------------------------------------------------ 自测
def selftest():
    checks = []

    def _ok(name, cond):
        checks.append((name, bool(cond)))

    # ① 复利前向算得对（无成本、无缺日）
    # 索引 0~10 全 0.01；11 是 None；12~16 是 0.0
    eqs = [0.01] * 11 + [None] + [0.0] * 5
    _ok("fwd 复合正确（10 日 +1% = 10.46%）",
        abs(fwd_from_eq(eqs, 0, 10) - (1.01 ** 10 - 1)) < 1e-9)
    _ok("缺日返回 None（丢样不糊弄）", fwd_from_eq(eqs, 0, 11) is None)

    # ② 越界返回 None
    _ok("越界返回 None", fwd_from_eq(eqs, 9, 20) is None)

    # ③ 阶段序列：给一条全 0 的平淡序列，必须落到「冰点」兜底而不是崩
    flat = [dict(date="d%03d" % k, zt=5, hi=2, zb=5, rate=0.5,
                 eq=0.0, total=4000) for k in range(80)]
    sm = stage_map(flat)
    _ok("平淡序列不崩且给出阶段", all(v in STAGES or "样本" in v for v in sm.values()))

    # ④ bootstrap：回暖段恒高于全样本 → 必 1.0；退潮段恒低 → 必 0.0
    #    ⚠ 别拿「全样本同值」当样例：那时 edge 恰好 =0，不满足 >0，结果必是 0.0
    vals = [0.02] * 50 + [0.00] * 50
    sts = ["回暖"] * 50 + ["退潮"] * 50
    r_hi = _boot_edge_ratio(vals, sts, "回暖", n_boot=50, block=10)
    _ok("bootstrap 恒胜基线 → 1.0", r_hi == 1.0)
    r_lo = _boot_edge_ratio(vals, sts, "退潮", n_boot=50, block=10)
    _ok("bootstrap 恒输基线 → 0.0", r_lo == 0.0)
    r_none = _boot_edge_ratio([], [], "回暖")
    _ok("样本过少 → None（不编）", r_none is None)

    # ⑤ 前后半按信号日顺序切（前半、后半样本数接近）
    pairs = [("回暖", 0.01)] * 10 + [("回暖", -0.01)] * 10
    h1, h2 = _half_split(pairs)
    _ok("前后半切分给值", h1 is not None and h2 is not None)

    bad = [n for n, c in checks if not c]
    print("自测：%d/%d 通过" % (len(checks) - len(bad), len(checks)))
    for n in bad:
        print("  ✗", n)
    return 0 if not bad else 1


# ------------------------------------------------------------------ 主流程
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="", help="数据截止日 YYYY-MM-DD（默认取数据最新日）")
    ap.add_argument("--src", default="long", choices=("long", "short"),
                    help="日K来源：long=长历史（默认）/ short=短缓存")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()

    if a.selftest:
        return selftest()

    if a.src == "long":
        cache = LK.load_long()
        src_label = LK.src_label()
    else:
        import _txk
        cache = _txk.load()
        src_label = "_txk_cache"
    if not cache:
        print("[FAIL] 读不到 K 线缓存（src=%s），fail-safe：不出任何结论" % src_label)
        return 2

    # 逐日情绪 + 全市场等权日收益，全部来自 _dragon_odds（同源）
    series, _sig, _closes, _runs, _univ = DO.scan(cache)
    if not series:
        print("[FAIL] scan 返回空序列，fail-safe：不出任何结论")
        return 2

    stg = stage_map(series)
    dates = [r["date"] for r in series]
    asof = a.date or dates[-1]
    if a.date:
        dates = [d for d in dates if d <= a.date]
        series = [r for r in series if r["date"] <= a.date]
        stg = stage_map(series)

    res = analyze(series, stg)

    payload = dict(
        asof=asof, kline_src=src_label, kline_label=src_label,
        sample_first=series[0]["date"] if series else None,
        sample_last=series[-1]["date"] if series else None,
        sample_days=len(series), cost=COST, boot=BOOT, block=BLOCK,
        holds=res, stages=list(STAGES),
        scope="全市场等权日收益（不含个股，不出票）",
        pre_register=("P1 相对 edge>0 / P2 绝对 net>0 / P3 前后半同号；三条全过才可用"),
    )

    out = os.path.join(os.path.dirname(QUANT), "quant", "dragon",
                       "stage_use_%s.json" % asof.replace("-", ""))
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, sort_keys=True, indent=1)
    print("→ 写出 %s" % out)

    print("\n=== 四阶段 → 后续全市场等权收益（预注册三判据）===")
    for hold in HOLDS:
        blk = res.get(str(hold)) or {}
        if "note" in blk:
            print("  N=%-3d %s" % (hold, blk["note"]))
            continue
        print("  N=%-3d 样本 %d　全样本均值 %+.4f%%" %
              (hold, blk["n"], (blk["baseline"] or 0) * 100))
        for st in STAGES:
            c = (blk.get("cells") or {}).get(st) or {}
            if "verdict" not in c:
                print("      %-4s 样本不足" % st)
                continue
            em = c.get("edge_matched")
            print("      %-4s n=%-4d 均值 %+7.4f%%  edge(全样本) %+7.4f%%  净 %+7.4f%%  R3=%s"
                  % (st, c["n"], c["mean"] * 100, c["edge"] * 100, c["net"] * 100,
                     ("%.3f" % c["r3"]) if c.get("r3") is not None else "n/a"))
            print("          前半 %+7.4f%%/后半 %+7.4f%%　同涨幅分位档 edge %s　档位 %s → %s"
                  % ((c["half1"] or 0) * 100, (c["half2"] or 0) * 100,
                     ("%+7.4f%%" % (em * 100)) if em is not None else "n/a",
                     c.get("bucket_span"), c["verdict"]))
            print("          样本期 %s ~ %s" % (c.get("first_date"), c.get("last_date")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
