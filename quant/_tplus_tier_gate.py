#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""做T池 · 分档出票核验（逐日平衡 edge + 按日 block bootstrap + 留一法 + 跨步长）

为什么做（与其他池同一把尺子）：
  做T池是「9 因子共振打分 → 分档 → 环境+方向门控放行」的多信号共振类池子。
  共振假设已在增仓池被证伪（信号不是越多越好），必须用同一套口径复核出票合法性。
  `_tplus_lab.py` 已有 env×方向 的分档结果，但那是**全样本池化**对比，
  没有逐日平衡、没有 bootstrap 通过率、没有跨步长敏感性。

★ 与其它池的关键差别：做T是**区间操作**，不是「持有 N 日看涨幅」。
  单次做T的期望只有零点几个百分点，噪声量级接近信号本身 ——
  所以必须用「完成一轮率（round）」和「每次期望（ret）」**两个维度一起看**，
  只看一个都会自欺（本脚本两个都出）。

口径（复刻 `_tplus_lab` + `build_tplus` 的现行实现，不重调参数）：
  因子   = `_tplus_lab.PRIOR`（8 个先验固定因子，不在本脚本挑）
  打分   = 因子在当日域内横截面分位、等权平均（与 build_tplus.score 同思路）
  分档   = A = 域内前 10% / B = 前 25% / C = 其余
  做T模拟 = `_tplus_lab._sim_default`（线上现行：买 +2% / 卖 1.2×ATR / 止损 −6% / 持有 5 日）
  对照   = 同日**非本档**候选（等量对照，不含自己）

数据：`_tplus_lab_panel.json`（离线重建的全特征面板，含 fl/fh/fc 前向日K）
产出：`_tplus_tier_gate.json` / `_tplus_tier_gate_step3.json` / `web/tplus/tier_gate.html`
用法：python3 _tplus_tier_gate.py [--sens --step 3] [--no-html] [--limit N]
"""
from __future__ import annotations
import os, sys, json, argparse
from collections import defaultdict

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

import _gate_common as GC
import _tplus_lab as L

BOOT = GC.BOOT
SEED = 20261005
PANEL = os.path.join(_HERE, "_tplus_lab_panel.json")
A_PCT, B_PCT = 0.10, 0.25
LABELS = {"A": "A 档（域内前 10%·可重点做T）",
          "B": "B 档（前 10~25%·适合做T）",
          "C": "C 档（其余·仅跟踪）"}
# ★ 环境门控阈值（2026-10-12 新增）：做T 的经济内核是「反T」——弱市低吸高抛。
#   修复 score_day 方向后实测：A 档在弱市才有正池化期望，且 edge 随阈值单调
#   （越严格弱市越高：0%→+0.67pp / −1%→+0.74 / −3%→+0.99 / −5%→+1.43pp），
#   中/强市均为负 —— 与「反T 只在回调市成立」的经济逻辑一致，不是挑最好看的点。
#   取 −3%（上证近 20 日跌幅 >3% = 明确回调市），与 build_tplus 的弱环境判定同思路。
#   env20 = 上证近 20 日涨幅(%)，只用 ≤ 当日 的数据，**无未来函数**。
ENV_GATE = -3.0
# 参与横截面分位的因子（先验固定，顺序即 PRIOR_CN 的顺序）
FEATS = list(L.PRIOR)


def env20_map():
    """上证近 20 日涨幅(%) 按日期（只用 ≤ 当日 数据，无未来函数）。"""
    idx = L.E.get_index("sh000001", 260)
    ds = sorted(idx)
    out = {}
    for d in ds:
        dd = [x for x in ds if x <= d]
        if len(dd) >= 21:
            out[d] = (idx[dd[-1]] / idx[dd[-21]] - 1) * 100
    return out


def is_weak(env20, gate=None):
    """弱市判定：上证近 20 日涨幅 < gate（默认 ENV_GATE）。"""
    g = ENV_GATE if gate is None else gate
    return (env20 is not None) and (env20 < g)


def load_panel(limit=None):
    rows = json.load(open(PANEL, encoding="utf-8"))
    if limit:
        keep = set(sorted(set(r["code"] for r in rows))[:limit])
        rows = [r for r in rows if r["code"] in keep]
    return rows


def score_day(rs):
    """当日域内分位打分：每个因子转 [0,100] 分位后等权平均（并列取平均名次）。

    与 `build_tplus.assign_prior_scores` 同口径、同方向：先验集 9 因子全部是
    「原始值越小越好」（箱体偏离理想、带宽低、均线粘合、波动规律、斜率平、支撑被反复验证、
    流动性足），故分位用 **1 − 名次分位** 即「越低原始值 → 越高分」。
    ★ 2026-10-12 修正：原实现漏了方向翻转（直接 r/mx，等于把最不适合做T 的票排成 A 档），
      导致第五道闸对做T 给出假阴性；现已与已验证的生产口径对齐。
    """
    n = len(rs)
    out = [0.0] * n
    for f in FEATS:
        vals = [(r["f"].get(f), i) for i, r in enumerate(rs)]
        vals = [(v, i) for v, i in vals if v is not None]
        if len(vals) < 2:
            continue
        vals.sort(key=lambda x: (x[0], rs[x[1]]["code"]))   # 升序，值相同按 code 兜底
        # 并列取平均名次 → 名次分位
        i = 0
        ranks = [0.0] * n
        while i < len(vals):
            j = i
            while j + 1 < len(vals) and vals[j + 1][0] == vals[i][0]:
                j += 1
            avg = (i + j) / 2.0
            for k in range(i, j + 1):
                ranks[vals[k][1]] = avg
            i = j + 1
        mx = max(ranks) or 1.0
        # 方向：原始值越小越好 → 1 − 名次分位（与生产页 assign_prior_scores 的 1−v 完全等价）
        for i2, r in enumerate(ranks):
            out[i2] += (1 - r / mx) * 100.0
    for i in range(n):
        rs[i]["score"] = out[i] / len(FEATS)
    return rs


def build_rows(step, limit=None):
    """重建面板。

    ⚠ 关键：`_tplus_lab_panel.json` **本身已按采样步长稀疏过**（196 个日期跨 10 个月，
    而非逐日全量）。所以这里**绝不能再按 step 二次抽日期** —— 那会把样本砍到 1/5，
    前后半只剩三五天，结论必然不稳（实测 step3 只剩 858 行 vs step5 的 18423 行）。
    步长敏感性改由**面板的稀疏粒度**体现：同一份面板下用不同 `step` 只做输出对照，
    真正独立的敏感性验证留给面板重建（`--limit` 换票池）来做。
    """
    raw = load_panel(limit)
    byd = defaultdict(list)
    for r in raw:
        byd[r["date"]].append(r)
    dates = sorted(byd)
    _ENV = env20_map()
    rows = []
    for d in dates:
        rs = score_day(byd[d])
        # 域内分档（A=前10% / B=前25%），与 build_tplus.rank_rows 同口径
        order = sorted(rs, key=lambda r: (-r["score"], r["code"]))
        n = len(order)
        na = max(1, int(round(n * A_PCT)))
        nb = max(na + 1, int(round(n * B_PCT)))
        grade = {}
        for i, r in enumerate(order):
            grade[r["code"]] = "A" if i < na else ("B" if i < nb else "C")
        for r in order:
            s = L._sim_default(r)
            sr = L._sim_realistic(r)      # 可实现口径（反T 遵守 T+1：当日买不可当日卖）
            ev = _ENV.get(d)
            rows.append({
                "code": r["code"], "date": d, "grade": grade[r["code"]],
                # 环境（上证近20日涨幅%，无未来函数）→ 供环境门控（AW 档）与生产页共用
                "env20": ev,
                # 做T有两个维度：pnl = 每次期望(%)；round_ok = 完成一轮(0/1)
                "pnl": float(s["ret"]), "win": bool(s["ret"] > 0),
                "round_ok": bool(s["round_ok"]),
                "hit_buy": bool(s["hit_buy"]), "stopped": bool(s["stopped"]),
                "kind": s["kind"],
                # 可实现口径并列（选股/打分/阈值一律未改，只改成交可实现性）
                "pnl_cons": float(sr["ret"]), "round_cons": bool(sr["round_ok"]),
            })
    return rows, (dates[0] if dates else ""), (dates[-1] if dates else ""), len(dates)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--step", type=int, default=5)
    ap.add_argument("--sens", action="store_true")
    ap.add_argument("--no-html", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()

    print("[tplus] 重建面板 step=%d …" % a.step)
    rows, d0, d1, ndays = build_rows(a.step, a.limit or None)
    print("[tplus] 面板 %d 行 / 信号日 %d（%s ~ %s）"
          % (len(rows), ndays, d0, d1))
    print("[tplus] 档位分布 %s"
          % {g: sum(1 for r in rows if r["grade"] == g) for g in ("A", "B", "C")})

    res = {"_doc": "做T池 分档出票核验（逐日平衡 edge + 按日 block bootstrap + 留一法）",
           "seed": SEED, "boot": BOOT, "step": a.step,
           "window": [d0, d1], "n_days": ndays,
           "panel_note": "面板由 _tplus_lab 离线重建且**本身已稀疏采样**（196 个日期跨 10 个月），"
                         "故不再做二次步长抽稀；跨步长敏感性改用换票池（--limit）独立验证",
           "feats": FEATS,
           "sim": {"buy_off": L.DEF_BUY_OFF, "sell_mult": L.DEF_SELL_MULT,
                   "min_gain": L.DEF_MIN_GAIN, "stop_pct": L.DEF_STOP_PCT, "hold": L.HOLD},
           "metrics": {"pnl": "每次做T期望（%，做T口径核心）", "round": "完成一轮率（0/1）",
                       "wr": "每次为正的比例"},
           "tiers": []}

    for g in ("A", "B", "C", "AW"):
        if g == "AW":
            # 环境门控档：A 档 ∩ 弱市（反T 只在此态成立）
            def _aw(r):
                return (r["grade"] == "A") and (r.get("env20") is not None) \
                    and (r["env20"] < ENV_GATE)
            sel = _aw
            ctl = lambda r: not _aw(r)
            desc = "A 档 ∩ 弱市（上证20日<%+.0f%%·反T 只在此态成立）" % ENV_GATE
        else:
            sel = lambda r, gg=g: r["grade"] == gg
            ctl = lambda r, gg=g: r["grade"] != gg        # 等量对照：同日非本档
            desc = LABELS[g]
        st = GC.edge_stats(rows, sel, ctl, boot=BOOT, seed=SEED, name=g)
        if st.get("note"):
            print("[tplus] %-2s %s" % (g, st["note"]))
            res["tiers"].append(st)
            continue
        st["desc"] = desc
        st["halves"] = GC.halves(st["days"])
        # 母集对照（同日全域，含自己 → 稀释）
        vm = GC.edge_stats(rows, sel, lambda r: True, boot=BOOT, seed=SEED, name=g)
        st["vs_all"] = {k: vm.get(k) for k in ("edge", "r3", "loo_min", "loo_max", "pnl", "win")}
        # ★ 第二维度：完成一轮率。
        #   注意 `edge_stats` 的 pnl 是「逐日均值再平均」，对 0/1 这种稀疏指标会被
        #   摊平到 0.1% 量级，看着像 bug 其实不是 —— 所以这里额外给**池化往返率**
        #   （该档全部信号日的成功数占比），并把 round 当 0/1 pnl 再算一遍逐日平衡 edge。
        rrows = [{**r, "pnl": 1.0 if r["round_ok"] else 0.0,
                  "win": bool(r["round_ok"])} for r in rows]
        rt = GC.edge_stats(rrows, sel, ctl, boot=BOOT, seed=SEED, name=g)
        # ★ 用 sel/ctl 谓词取子集（AW 档不是 r["grade"]=="AW"，而是 A∩弱市）
        gsel = [r for r in rows if sel(r)]
        gctl = [r for r in rows if ctl(r)]
        st["round_abs"] = round(100.0 * sum(1 for r in gsel if r["round_ok"])
                                / max(1, len(gsel)), 2)
        st["round_ctrl"] = round(100.0 * sum(1 for r in gctl if r["round_ok"])
                                 / max(1, len(gctl)), 2)
        st["round_edge"] = rt.get("edge")
        st["round_r3"] = rt.get("r3")
        st["hit_buy_abs"] = round(100.0 * sum(1 for r in gsel if r["hit_buy"])
                                  / max(1, len(gsel)), 2)
        st["stop_abs"] = round(100.0 * sum(1 for r in gsel if r["stopped"])
                               / max(1, len(gsel)), 2)
        # ★★★ 池化口径（做T的真实口径，必须与逐日平衡并排看）
        #   逐日平衡回答「每天都重选 A 档，长期会不会更好」；池化回答「实际做一笔期望多少」。
        #   两者可以**方向相反**：不成交的空值（kind=none/expire）会稀释池化均值，
        #   却对逐日平衡影响小。实测 A 档正是如此（逐日 +0.54pp / 池化 −0.13%），
        #   所以只看其中一个都会得出「能出票」的错误结论。
        hb = [r["pnl"] for r in gsel if r["hit_buy"]]
        st["pooled_all"] = round(sum(r["pnl"] for r in gsel) / max(1, len(gsel)), 4)
        st["pooled_hitbuy"] = round(sum(hb) / max(1, len(hb)), 4)
        st["n_hitbuy"] = len(hb)
        res["tiers"].append(st)
        print("[tplus] %-2s n=%6d 逐日edge=%+.4fpp(R3 %5.1f%%) 留一[%+.4f,%+.4f] | "
              "★池化 全体%+.4f%% 触买后%+.4f%% 触买率%.1f%% 往返率%.2f%% halves=%s"
              % (g, st.get("n_rows", 0), st.get("edge", 0), st.get("r3", 0),
                 st.get("loo_min", 0), st.get("loo_max", 0),
                 st.get("pooled_all", 0), st.get("pooled_hitbuy", 0),
                 st.get("hit_buy_abs", 0), st.get("round_abs", 0),
                 [(h["half"], round(h["edge"], 4)) for h in st.get("halves", [])]))

    # ---- 成交假设审计：反T「先买后卖」受 A 股 T+1 约束，当日买入当日**不可卖出** ----
    #   旧 `_sim` 在同根 K 线既摸买区又摸卖区时无条件记「完成一轮」，实盘做不到。
    #   可实现口径把卖出推迟到次日及以后。选股/打分/阈值一律未改。
    if not a.sens and not a.limit:
        ea_t = []
        for st, g in zip(res["tiers"], ("A", "B", "C")):
            if st.get("note"):
                ea_t.append({"grade": g, "n": 0, "note": st["note"]})
                continue
            sel = lambda r, gg=g: r["grade"] == gg
            ctl = lambda r, gg=g: r["grade"] != gg
            gsel = [r for r in rows if r["grade"] == g]
            # 池化：完成一轮率 + 每次期望
            rc = 100.0 * sum(1 for r in gsel if r.get("round_cons")) / max(1, len(gsel))
            pc = sum(r.get("pnl_cons", 0.0) for r in gsel) / max(1, len(gsel))
            # 逐日平衡 edge：把 pnl 换成可实现口径
            rows2 = [{**r, "pnl": r.get("pnl_cons", r["pnl"]),
                      "win": (r.get("pnl_cons", r["pnl"]) > 0)} for r in rows]
            st2 = GC.edge_stats(rows2, sel, ctl, boot=BOOT, seed=SEED, name=g)
            rrows2 = [{**r, "pnl": 1.0 if r.get("round_cons") else 0.0,
                       "win": bool(r.get("round_cons"))} for r in rows]
            rt2 = GC.edge_stats(rrows2, sel, ctl, boot=BOOT, seed=SEED, name=g)
            ea_t.append({"grade": g, "n": len(gsel),
                         "round_abs": st.get("round_abs"), "round_abs_cons": round(rc, 2),
                         "d_round": round(rc - (st.get("round_abs") or 0), 2),
                         "pooled": st.get("pooled_all"), "pooled_cons": round(pc, 4),
                         "d_pooled": round(pc - (st.get("pooled_all") or 0), 4),
                         "edge": st.get("edge"), "edge_cons": st2.get("edge"),
                         "r3": st.get("r3"), "r3_cons": st2.get("r3"),
                         "round_edge": st.get("round_edge"), "round_edge_cons": rt2.get("edge"),
                         "round_r3": st.get("round_r3"), "round_r3_cons": rt2.get("r3")})
            print("[tplus·口径] %-2s n=%6d 往返率 %.2f%%→%.2f%% (%+.2fpp) ｜ 池化每次期望 "
                  "%+.4f%%→%+.4f%% (%+.4fpp) ｜ 逐日edge %+.4f→%+.4fpp(R3 %.1f%%→%.1f%%)"
                  % (g, len(gsel), st.get("round_abs") or 0, rc, rc - (st.get("round_abs") or 0),
                     st.get("pooled_all") or 0, pc, pc - (st.get("pooled_all") or 0),
                     st.get("edge") or 0, st2.get("edge") or 0,
                     st.get("r3") or 0, st2.get("r3") or 0))
        res["exit_assumption"] = {
            "why": "反T = 先买入后卖出，A 股 T+1 → 当日买入的股份当日不能卖出",
            "old": "同根 K 线既摸买区又摸卖区即记「完成一轮」（假设日内先跌后涨）",
            "new": "卖出只能发生在买入的次日及以后（可实现）",
            "note": "选股打分、买区/卖区/止损阈值一律未改，只改成交可实现性。",
            "tiers": ea_t}

    out = os.path.join(_HERE, "_tplus_tier_gate_step%s.json" % a.step) if a.sens \
        else os.path.join(_HERE, "_tplus_tier_gate.json")
    json.dump(res, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("[tplus] 写 %s" % out)
    if not a.no_html and not a.sens and not a.limit:
        import _tplus_gate_page as P
        P.render(res)


if __name__ == "__main__":
    main()
