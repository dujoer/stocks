#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""龙道诀四阶段 →「**仓位开关**」能不能跑赢恒满仓（预注册检验）

   为什么这一节
   ----------
   上一道检验（_dragon_stage_use.py）只证到「高潮 → 后续全市场等权收益 +0.8~1.7pp」。
   那是**条件收益**，不等于「拿它去开关仓位能多赚」。从条件收益到可执行规则之间
   还差三件事：① 换仓成本 ② T+1 落地（无未来函数）③ 对照基准该是谁（恒满仓）。

   预注册判据（**跑前写死，不许事后挑好看的窗口/参数**）
   ----------------------------------------------------
   P1 绝对  —— 扣换仓成本后，策略日均收益 − 恒满仓日均收益 > 0
   P2 稳健  —— 样本期**前半段与后半段**的超额**同为正**
   P3 概率  —— 按日 block bootstrap（block=21 天，整日整日抽）抽 2000 次，
               「日均可超额 > 0」的比例 R3 ≥ 0.95
   ⇒ P1 且 P2 且 P3 全过，才叫「可用（仓位开关）」。

   P4 风控  —— ★ 单列，不属于上面三条（它回答的不是「能不能赚」）。
       「把仓位压低」本身就会让最大回撤变小 —— 不比对照就是循环论证。
       只有做到「**同等回撤水平（±2pp）下**日均收益不低于最优恒仓线」，
       才说明回撤的下降是四阶段带来的，而不只是「少下注」。
       固定仓位基准族：w ∈ {1.0, 0.75, 0.5, 0.25, 0.0}，不做任何判断。

   证伪面（**必须一起报，只报好看的一侧就是选择性呈现**）
   ----------------------------------------------------
   F1 反向规则：把仓位映射反过来（高潮空仓 / 其余满仓）。若反向也通过 P1，
               说明所谓超额只是**市场 beta**，不是阶段择时 → 判「不可用」。
   F2 成本敏感：SWITCH_COST 从 0.2% 抬到 0.5% / 1.0%，看结论是否翻。
   F3 换手代价：报换手次数、平均持仓天数 —— 超额若全靠高频切换，不叫稳健。

   落地口径（无未来函数）
   --------------------
   阶段在 **T 日收盘后**由当日涨停/炸板/连板定出，仓位 **T+1 日**才生效：
       w[i] = rule[ stage(dates[i-1]) ]
   首日（i=0）没有前置信息 → 计为 None 并**剔除**，不猜、不补。
   阶段缺失（停牌/缺数据）→ 预注册为 **0 仓位（空仓）**，fail-safe 保守。

   标的：全市场等权日收益（`_dragon_odds.scan()` 同源，不走个股，不出票）。
   ⚠ 本节测的是**指数口径的仓位择时**。拿它去加/减某个选股池的仓位属**跨口径外推**，
     真要接进实盘须对那个池重走四道验证。

   用法
   ----
       python3 _dragon_pos_rule.py --date 2026-09-30 --src long
       python3 _dragon_pos_rule.py --selftest
"""
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

COST = 0.002          # 换仓成本口径，与 _dragon_odds 的 EXEC_COST 同（0.2% 往返）
BOOT = 2000           # ★ bootstrap 次数固定，不随跑次变（改一次＝另一次实验）
BLOCK = 21            # 按日 block 长度（≈1 个月），整日整日抽
SEED = 20261006
STAGES = ("退潮", "高潮", "回暖", "冰点")
MIN_N = 5

# 主规则：只用已被上一道检验证出方向的两阶段；回暖/冰点跨窗口不一致 → 预注册为「不参与择时」
RULE_MAIN = {"高潮": 1.0, "退潮": 0.0, "回暖": 0.0, "冰点": 0.0}
# 证伪面 F1：反向映射
RULE_REV = {"高潮": 0.0, "退潮": 1.0, "回暖": 1.0, "冰点": 1.0}
# F1b：只有「退潮」空仓、其余满仓
#   ★ 这条**有先验依据**，不是事后扫描：上一道检验证明「退潮」是唯一 edge 三窗口全负的阶段，
#     所以「退潮离场」是本命题里最有理由成立的**单条件**规则。若它也不行，就别再扫别的形了。
RULE_NEG = {"高潮": 1.0, "退潮": 0.0, "回暖": 1.0, "冰点": 1.0}
# 成本敏感 F2
COST_GRID = (0.002, 0.005, 0.010)
# 固定仓位基准族（P4 用）：只压仓位、不做任何判断的对照线
FIXED = (1.0, 0.75, 0.5, 0.25, 0.0)


def stage_map(series):
    """[{date,zt,zb,hi,eq}] → {date: 阶段名}。判定走唯一实现，与页面同源。"""
    thin = [dict(date=row["date"], zt=row["zt"],
                 hi=row["hi"], rate=row.get("rate") or 0.0)
            for row in series]
    return M.stage_series(thin)


def weights(dates, stg, rule):
    """w[i] = rule[stage(dates[i-1])] —— T 日收盘定阶段、T+1 日落地（无未来函数）。

    首日（i=0）无前置信息 → None（剔除，不猜）；阶段缺失 → 0（空仓，fail-safe 保守）。
    """
    ws = [None]
    for i in range(1, len(dates)):
        st = stg.get(dates[i - 1])
        ws.append(rule.get(st) if st is not None else 0.0)
    return ws


def _stats(daily):
    """净日收益序列 → (日均, 累计, 最大回撤, 正收益占比)"""
    clean = [d for d in daily if d is not None]
    if not clean:
        return None
    mean = sum(clean) / len(clean)
    cum = 1.0
    peak = 1.0
    mdd = 0.0
    pos = 0
    for d in clean:
        cum *= (1.0 + d)
        peak = max(peak, cum)
        mdd = max(mdd, peak - cum if cum > 0 else (1.0 - cum))
        if d > 0:
            pos += 1
    return dict(mean=mean, cum=cum - 1.0, mdd=mdd,
                pos_ratio=pos / len(clean), n=len(clean))


def _boot_exceed_ratio(exceed, block=BLOCK, n_boot=BOOT, seed=SEED):
    """按日 block bootstrap：抽到「日均可超额 > 0」的比例（R3）。"""
    vals = [v for v in exceed if v is not None]
    n = len(vals)
    if n < 2 * block:
        return None
    rng = random.Random(seed)
    nblk = int(n // block)
    hit = 0
    for _b in range(n_boot):
        tot = 0.0
        for _k in range(nblk):
            st0 = rng.randrange(0, max(1, n - block))
            for j in range(block):
                tot += vals[st0 + j]
        if tot / (nblk * block) > 0:
            hit += 1
    return hit / n_boot


def backtest_ws(eqs, ws, switch_cost=COST):
    """回测核：给定逐日权重序列，出净日收益 / 基准 / 换手次数。建仓成本不计，只计**换仓**成本。"""
    net, base, swi = [], [], []
    for i in range(len(eqs)):
        e = eqs[i]
        if e is None or ws[i] is None:
            net.append(None)
            base.append(None)
            swi.append(None)
            continue
        w = ws[i]
        turn = 0.0
        if i > 0 and ws[i - 1] is not None:
            turn = abs(w - ws[i - 1])
        net.append(e * w - turn * switch_cost)
        base.append(e)
        swi.append(turn)
    return dict(net=net, base=base, ws=ws, swi=swi,
                turns=sum(1 for t in swi if t is not None and t > 0))


def flat_ws(n, w):
    """恒定仓位权重序列（首日无前置信息 → None，与主规则口径一致）。"""
    return [None] + [w] * (n - 1)


def backtest(eqs, dates, stg, rule, switch_cost=COST):
    """逐日回测：权重由 stage(dates[i-1]) 经 rule 映射（T+1 落地）。"""
    return backtest_ws(eqs, weights(dates, stg, rule), switch_cost)


def analyze(eqs, dates, stg, holds=None):
    """主规则 + 证伪面 F1/F2/F3 全套统计。"""
    eqs = [e if e is not None else None for e in eqs]

    # ---- 主规则 ----
    bt = backtest(eqs, dates, stg, RULE_MAIN)
    st_net, st_base = _stats(bt["net"]), _stats(bt["base"])
    if not st_net or not st_base or st_net["n"] < 30:
        return dict(note="样本不足，不可判（fail-safe：不出结论）")

    days = st_net["n"]
    ex_mean = st_net["mean"] - st_base["mean"]
    ex_cum = (st_net["cum"] - st_base["cum"])

    # 前半段 / 后半段（按索引平分，各算一次日均超额）
    def _half_exceed(lo, hi):
        dn = [bt["net"][i] for i in range(lo, hi) if bt["net"][i] is not None]
        db = [bt["base"][i] for i in range(lo, hi) if bt["base"][i] is not None]
        if not dn or len(dn) != len(db):
            return None
        return sum(dn) / len(dn) - sum(db) / len(db)

    half = days // 2
    h1, h2 = _half_exceed(0, half), _half_exceed(half, days)

    exceed = [bt["net"][i] - bt["base"][i] if bt["net"][i] is not None else None
              for i in range(days)]
    r3 = _boot_exceed_ratio(exceed)

    p1 = ex_mean > 0
    p2 = (h1 is not None and h2 is not None and h1 > 0 and h2 > 0)
    p3 = (r3 is not None and r3 >= 0.95)
    passed = bool(p1 and p2 and p3)

    # ---- 证伪面 F1：反向规则 ----
    bt_r = backtest(eqs, dates, stg, RULE_REV)
    sr = _stats(bt_r["net"])
    ex_rev = (sr["mean"] - st_base["mean"]) if sr else None

    # ---- 证伪面 F1b：退潮离场（有先验依据的单条件规则）----
    bt_n = backtest(eqs, dates, stg, RULE_NEG)
    sn = _stats(bt_n["net"])
    ex_neg = (sn["mean"] - st_base["mean"]) if sn else None

    # ---- 证伪面 F2：成本敏感 ----
    cost_sens = {}
    for c in COST_GRID:
        b2 = backtest(eqs, dates, stg, RULE_MAIN, switch_cost=c)
        s2 = _stats(b2["net"])
        cost_sens[str(c)] = None if not s2 else dict(
            ex=(s2["mean"] - st_base["mean"]), turns=b2["turns"])

    # ---- 固定仓位基准族：回答「降回撤到底算不算四阶段的功劳」----
    #   ⚠ 不比这个就是循环论证 —— 任何把仓位压低的规则回撤都会变小。
    #   只有做到「**同等回撤水平**下收益不低于恒仓线」，才能说风控价值是四阶段带来的。
    fixed = {}
    for w in FIXED:
        fb = _stats(backtest_ws(eqs, flat_ws(len(eqs), w))["net"])
        fixed[str(w)] = (None if not fb else
                         dict(mean=fb["mean"], cum=fb["cum"], mdd=fb["mdd"]))
    # 主规则在「回撤相近（±0.02）」的恒仓线里，日均收益是否不低于最优那条
    # 没有 ±2pp 的精确邻域时，退而取**回撤最接近**的那条恒仓线做配对（仍如实标注）
    cand = [v for v in fixed.values() if v]
    near = [(w, v) for w, v in fixed.items() if v and v["mdd"] is not None
            and abs(v["mdd"] - st_net["mdd"]) <= 0.02]
    p4 = False
    if near:
        best_w, best_v = max(near, key=lambda kv: kv[1]["mean"])
    else:
        best_w, best_v = min(
            [(w, v) for w, v in fixed.items() if v],
            key=lambda kv: abs(kv[1]["mdd"] - st_net["mdd"]))
    if st_net["mdd"] <= best_v["mdd"] + 1e-9 and st_net["mean"] >= best_v["mean"]:
        p4 = True
    # ⚠ 文案一律出「百分比纯文本」，百分比格式化交给页面 —— 否则与表格里的数字对不上，
    #   也不许在真源里写 markdown 星号（会原样漏到 HTML 页面上）。
    p4_note = ("对照恒仓 w=%s（回撤 %.2f%%，日均 %+.4f%%）｜本策略（回撤 %.2f%%，日均 %+.4f%%）"
               "→ 风控价值%s"
               % (best_w, best_v["mdd"] * 100, best_v["mean"] * 100,
                  st_net["mdd"] * 100, st_net["mean"] * 100,
                  "成立" if p4 else "不成立"))

    # F1b 的等风险对照线（必须在 fixed 定义之后）
    nb = min([(w, v) for w, v in fixed.items() if v],
             key=lambda kv: abs(kv[1]["mdd"] - (sn["mdd"] if sn else 0.0)))

    # ---- 换手 / 持仓 ----
    w_live = [w for w in bt["ws"] if w is not None]
    held = sum(1 for w in w_live if w > 0)
    span = {}
    for i, d in enumerate(dates):
        st = stg.get(d)
        if st not in STAGES:
            continue
        cur = span.get(st)
        span[st] = ([cur[0], d] if cur else [d, d])

    return dict(
        days=days,
        base_mean=st_base["mean"], base_cum=st_base["cum"], base_mdd=st_base["mdd"],
        net_mean=st_net["mean"], net_cum=st_net["cum"], net_mdd=st_net["mdd"],
        excess_mean=ex_mean, excess_cum=ex_cum,
        half1=h1, half2=h2, r3=r3,
        turns=bt["turns"],
        hold_days=held, hold_ratio=(held / len(w_live) if w_live else None),
        # ★ 阶段天数按 stg 数，不能拿扁平仓位列表数（那样四个阶段会算出同一个数）
        rule_days={st: sum(1 for d in dates if stg.get(d) == st) for st in STAGES},
        p1=p1, p2=p2, p3=p3, p4=p4,
        passed=bool(p1 and p2 and p3),          # P4 单列：是风控价值，不是 alpha
        p4_note=p4_note,
        risk_adj=("收益判据看 P1/P2/P3；风控价值看 P4（同等回撤下不劣于恒仓线）"),
        fixed=fixed,
        neg=dict(excess_mean=ex_neg, mdd=(sn["mdd"] if sn else None),
                 # 等风险配对：与**回撤最接近**的恒仓线比
                 near_w=nb[0], near_mean=nb[1]["mean"], near_mdd=nb[1]["mdd"],
                 pass_risk=(sn is not None and sn["mdd"] <= nb[1]["mdd"] + 1e-9
                            and sn["mean"] >= nb[1]["mean"])),
        rev=dict(excess_mean=ex_rev, mdd=(sr["mdd"] if sr else None)),
        cost_sens=cost_sens,
        spans={st: span.get(st) for st in STAGES},
    )


# --------------------------------------------------------------- 自测
def selftest():
    tot = ok = 0

    def _ck(name, cond):
        nonlocal tot, ok
        tot += 1
        if cond:
            ok += 1
        print("  %s %s" % ("OK  " if cond else "FAIL", name))

    # ① T+1 落地：w[i] 只看 dates[i-1] 的阶段 ——  future 改不动当天仓位
    stg = {"d1": "高潮", "d2": "退潮", "d3": "高潮"}
    rule = {"高潮": 1.0, "退潮": 0.0}
    w = weights(["d1", "d2", "d3", "d4"], stg, rule)
    _ck("weights 首日为 None（无前置信息，剔除不猜）", w[0] is None)
    _ck("weights = T+1 生效（d2 用 d1 的阶段）", w[1] == 1.0)
    _ck("weights = d3 用 d2 的退潮→0", w[2] == 0.0)

    # ② 阶段缺失 → 0（空仓 fail-safe），不猜
    #    ⚠ 测这个必须让 stg 覆盖到每个“前一日”，否则缺失的是日期而非阶段，测的不是同一件事
    w3 = weights(["d1", "d2", "d3"], {}, rule)
    _ck("阶段全部缺失 → 全 0 仓位（fail-safe 保守）", w3[1] == 0.0 and w3[2] == 0.0)
    w4 = weights(["d1", "d2", "d3"], {"d1": "高潮", "d2": "退潮"}, rule)
    _ck("前一日有阶段 → 正常映射（不被缺失分支吃掉）",
        w4[1] == 1.0 and w4[2] == 0.0)

    # ③ 换仓才扣成本；不动仓不扣
    eqs = [0.01, 0.01, 0.01, 0.01]
    dates = ["a", "b", "c", "d"]
    stg_all = dict(zip(dates, ["高潮"] * 4))          # 阶段全覆盖，排除缺失干扰
    b1 = backtest(eqs, dates, stg_all, {"高潮": 1.0}, switch_cost=0.01)
    _ck("满仓不换手 → 换手次数 0（成本不空扣）", b1["turns"] == 0)
    b2 = backtest(eqs, dates, {"a": "高潮", "b": "退潮", "c": "退潮", "d": "退潮"},
                  {"高潮": 1.0, "退潮": 0.0}, switch_cost=0.01)
    _ck("满仓→空仓 → 记 1 次换手", b2["turns"] == 1)

    # ④ 恒满仓规则的超额恰为 0（基准不产生伪超额）
    b3 = backtest(eqs, dates, stg_all, {"高潮": 1.0, "退潮": 1.0})
    s3, b3b = _stats(b3["net"]), _stats(b3["base"])
    _ck("恒满仓 → 超额 0", abs((s3["mean"] - b3b["mean"])) < 1e-12)

    # ⑤ bootstrap 恒正样本 → 1.0；恒负 → 0.0
    _ck("bootstrap 恒正 → R3=1.0", _boot_exceed_ratio([0.01] * 2000) == 1.0)
    _ck("bootstrap 恒负 → R3=0.0", _boot_exceed_ratio([-0.01] * 2000) == 0.0)

    # ⑥ 样本过短 → bootstrap 返回 None（不编 R3）
    _ck("样本 < 2 个 block → R3=None", _boot_exceed_ratio([0.01] * 5) is None)

    # ⑦ 大回撤能被测出（mdd 单调累加 → 回撤 0；先涨后暴跌 → 回撤>0）
    s_up = _stats([0.05] * 10)
    _ck("单边上涨 → 最大回撤 0", s_up["mdd"] == 0.0)
    s_dn = _stats([0.10] * 5 + [-0.5] * 5)
    _ck("先涨后暴跌 → 最大回撤 > 0", s_dn["mdd"] > 0.0)

    # ⑧ 阶段映射：主规则只有高潮持仓
    _ck("主规则：只有高潮日给正仓位",
        RULE_MAIN["高潮"] == 1.0 and all(RULE_MAIN[s] == 0.0
                                         for s in ("退潮", "回暖", "冰点")))

    # ⑨ 固定仓位基准族：恒空仓 → 日均 0、回撤 0（空仓当然没风险，这条只钉口径）
    s0 = _stats(backtest_ws(eqs, flat_ws(4, 0.0))["net"])
    _ck("恒空仓 → 日均 0 且回撤 0", s0["mean"] == 0.0 and s0["mdd"] == 0.0)
    _ck("flat_ws 首日 None（与择时口径一致，不偷跑建仓）",
        flat_ws(4, 0.5)[0] is None and flat_ws(4, 0.5)[1] == 0.5)
    # ⑩ 恒满仓基准线 == 基准序列本身（超额必须能算成 0，否则 P1 是空转）
    f1 = backtest_ws(eqs, flat_ws(4, 1.0))
    sf, sf0 = _stats(f1["net"]), _stats(f1["base"])
    _ck("恒满仓基准线 → 超额 0", abs((sf["mean"] - sf0["mean"])) < 1e-12)

    print("\n自测 %d/%d" % (ok, tot))
    return 0 if ok == tot else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="", help="数据截止日 YYYY-MM-DD（默认取数据最新日）")
    ap.add_argument("--src", default="long", choices=("long", "short"))
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

    series, _sig, _closes, _runs, _univ = DO.scan(cache)
    if not series:
        print("[FAIL] scan 返回空序列，fail-safe：不出任何结论")
        return 2

    stg = stage_map(series)
    dates = [r["date"] for r in series]
    eqs = [r.get("eq") for r in series]
    asof = a.date or dates[-1]
    if a.date:
        keep = [i for i, d in enumerate(dates) if d <= a.date]
        series = [series[i] for i in keep]
        dates = [dates[i] for i in keep]
        eqs = [eqs[i] for i in keep]
        stg = stage_map(series)

    res = analyze(eqs, dates, stg)

    payload = dict(
        asof=asof, kline_src=src_label, kline_label=src_label,
        sample_first=series[0]["date"] if series else None,
        sample_last=series[-1]["date"] if series else None,
        sample_days=len(series), cost=COST, boot=BOOT, block=BLOCK,
        pre_register=("P1 扣成本日均超额>0 / P2 前后半段同正 / P3 block bootstrap R3>=0.95；"
                      "三条全过才叫「可用（仓位开关）」。"),
        falsify=("F1 反向规则若也 P1 通过 → 只是 beta，判不可用；"
                 "F2 换仓成本敏感性；F3 换手次数与持仓天数。"),
        rule_main=RULE_MAIN, rule_neg=RULE_NEG,
        result=res,
    )
    out = os.path.join(os.path.dirname(QUANT), "quant", "dragon",
                       "pos_rule_%s.json" % asof.replace("-", ""))
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, sort_keys=True, indent=1)
    print("→ 写出 %s" % out)
    print(json.dumps(res, ensure_ascii=False, indent=1, default=str)[:3000])
    return 0


if __name__ == "__main__":
    sys.exit(main())
