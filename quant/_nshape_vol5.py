# -*- coding: utf-8 -*-
"""N字形 · 组合规则诊断（2026-10-25）：量能优选 × 市场热度门控 × 退出工程。

背景：单族量能规则跨步长随机对照不一致（step5 7.5%>5%）+ 绝对收益≈0。
本项目已验证环境门控能规避弱市（弱势绝对 alpha 强负）——本脚本检验
「量能优选 × 环境门控」组合是否把相对 edge 转成绝对 edge。

口径（全部为 as-of 无未来函数）：
- 行域：60 个 as-of 日的全部 hb_pos（当日全集=对照域，与 canonical 一致）
- 量能分：冻结模型 vol_model.json 打分，当日 hb_pos 前 20% 标记 vol_top
- 逐日平衡 edge：mean(当日 vol_top pnl) − mean(当日全集 pnl)，按日聚合
- 环境门控：load_market_heat 的 label（强势/震荡/弱势/破位）
- 退出工程：固定 TP/SL 之外，加移动止盈（回撤阈值 trail）对照

输出：诊断打印 + quant/n_shape/vol5_diag_{DS}.json（描述性，非选参）。
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
import _nshape_vol_model as VM

TP_A, SL_A, FWD = 0.10, 0.08, 10
TP_B = 0.06
QUANT = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(QUANT, "n_shape")


def agg(rows, key):
    """池化统计（仅描述）。rows 已含 pnlA/pnlB/winA/winB。"""
    if not rows:
        return None
    n = len(rows)
    wA = sum(1 for r in rows if r["winA"]) / n * 100
    wB = sum(1 for r in rows if r["winB"]) / n * 100
    mA = sum(r["pnlA"] for r in rows) / n
    mB = sum(r["pnlB"] for r in rows) / n
    wins = [r["pnlA"] for r in rows if r["winA"]]
    loss = [r["pnlA"] for r in rows if not r["winA"]]
    aw = sum(wins) / len(wins) if wins else 0.0
    al = sum(loss) / len(loss) if loss else 0.0
    return {"n": n, "winA": round(wA, 2), "winB": round(wB, 2),
            "avgA": round(mA, 3), "avgB": round(mB, 3),
            "avg_win": round(aw, 2), "avg_loss": round(al, 2),
            "pl": round(abs(aw / al), 2) if al else None}


def daily_balanced_edge(rows, sel_fn):
    """canonical 逐日平衡 edge（复刻 edge_stats 核心：按日均值差）。"""
    by_day = {}
    for r in rows:
        by_day.setdefault(r["date"], []).append(r)
    diffs = []
    for d, rs in by_day.items():
        sub = [r for r in rs if sel_fn(r)]
        if not sub:
            continue
        m_all = sum(r["pnlA"] for r in rs) / len(rs)
        m_sub = sum(r["pnlA"] for r in sub) / len(sub)
        diffs.append(m_sub - m_all)
    if not diffs:
        return None
    return sum(diffs) / len(diffs)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None)
    ap.add_argument("--asof", type=int, default=60)
    a = ap.parse_args()
    D = a.date or NS.latest_date()
    DS = D.replace("-", "")
    print("=== N字形 组合规则诊断（量能×环境×退出）· 数据日 %s ===" % D)

    _txk.set_asof(D)
    cache = _txk.load()
    name_map = NS.load_name_map(D)
    name2sw2 = NS.load_name2sw2()
    ind_map, cl = NS.load_hot_maps()
    w52 = NS.load_52w_cache(cache)
    dates = BT.pick_asof_dates(cache, n=a.asof, fwd=FWD)
    print("as-of 窗口：%s → %s（%d 日）" % (dates[0], dates[-1], len(dates)))

    # ---- 建行：全部 hb_pos（对照域=当日全集）----
    rows = []
    for d in dates:
        day = NS.gen_signals_asof(cache, d, name_map)
        NS.attach_attr(day, name2sw2, ind_map, cl, w52)
        heat = NS.load_market_heat(d)
        for r in day:
            if not BT.is_hb_pos(r):
                continue
            raw = {k: v for k, v in r.items() if k != "ft"}
            fa = BT.fwd_first_touch(cache, raw, TP_A, SL_A, FWD)
            if not fa:
                continue
            fb = BT.fwd_first_touch(cache, raw, TP_B, SL_A, FWD)
            r.update({"date": d, "ftA": fa, "ftB": fb,
                      "heat": heat["label"], "heat_score": heat["score"],
                      "winA": bool(fa["win"]), "pnlA": fa["ret"] * 100.0,
                      "winB": bool(fb["win"]) if fb else False,
                      "pnlB": (fb["ret"] * 100.0) if fb else 0.0})
            rows.append(r)
    print("hb_pos 行：%d" % len(rows))

    # ---- 冻结模型打分 + 当日 top20% ----
    model = VM.load_model()
    if not model:
        print("无冻结模型，退出")
        return
    VM.attach_vol(rows, cache, model)
    VM.mark_vol_top(rows)
    n_top = sum(1 for r in rows if r.get("vol_top"))
    print("可打分 %d 行，当日 top20%% 标记 %d 行" %
          (sum(1 for r in rows if r.get("vol_score") is not None), n_top))

    base = agg(rows, "A")
    print("\n基准（hb_pos 全集）：n=%d 胜率A=%.2f%% 均A=%+.3f%%｜胜率B=%.2f%% 均B=%+.3f%%"
          % (base["n"], base["winA"], base["avgA"], base["winB"], base["avgB"]))

    report = {"date": D, "asof": a.asof, "n_rows": len(rows), "base": base,
              "heat": {}, "combo": {}, "exit": {}}

    # ---- ① 量能优选按热度分桶（核心诊断）----
    print("\n---- ① vol_top20%% 按市场热度分桶（池化）----")
    print("  %-6s %5s %5s %8s %8s %8s %8s" % ("热度", "n行", "n日", "胜率A%", "均A%", "胜率B%", "均B%"))
    for lab in ("强势", "震荡", "弱势", "破位"):
        sub = [r for r in rows if r["heat"] == lab and r.get("vol_top")]
        s_ = agg(sub, "A")
        nd = len({r["date"] for r in sub})
        if not s_:
            print("  %-6s 无样本" % lab)
            continue
        print("  %-6s %5d %5d %8.2f %+8.3f %8.2f %+8.3f"
              % (lab, s_["n"], nd, s_["winA"], s_["avgA"], s_["winB"], s_["avgB"]))
        report["heat"][lab] = s_
        report["heat"][lab]["n_days"] = nd

    # 同桶的全集对照（看相对 edge 是否也集中在强市）
    print("\n  同热度桶的全集对照（相对 edge 来源）:")
    for lab in ("强势", "震荡", "弱势", "破位"):
        sub = [r for r in rows if r["heat"] == lab]
        s_ = agg(sub, "A")
        if not s_:
            continue
        print("  %-6s 全集 n=%d 胜率A=%.2f%% 均A=%+.3f%%" % (lab, s_["n"], s_["winA"], s_["avgA"]))

    # ---- ② 逐日平衡 edge 按热度分解 ----
    print("\n---- ② 逐日平衡 edge（vol_top − 当日全集）按热度分解 ----")
    for lab in ("强势", "震荡", "弱势", "破位"):
        e = daily_balanced_edge([r for r in rows if r["heat"] == lab],
                                lambda r: bool(r.get("vol_top")))
        print("  %-6s 逐日平衡 edge = %s" % (lab, ("%+.3fpp" % e) if e is not None else "无样本"))
        report["heat"].setdefault(lab, {})["daily_edge"] = round(e, 3) if e is not None else None

    # ---- ③ 组合规则：强市门控 × 量能优选 ----
    print("\n---- ③ 组合规则（门控×量能）池化 + 逐日平衡 ----")
    combos = {
        "vol_top20(全市场)": lambda r: bool(r.get("vol_top")),
        "强/震荡 × vol_top20": lambda r: bool(r.get("vol_top")) and r["heat"] in ("强势", "震荡"),
        "强 × vol_top20": lambda r: bool(r.get("vol_top")) and r["heat"] == "强势",
        "强/震荡(不限量能)": lambda r: r["heat"] in ("强势", "震荡"),
        "强(不限量能)": lambda r: r["heat"] == "强势",
    }
    for name, fn in combos.items():
        sub = [r for r in rows if fn(r)]
        s_ = agg(sub, "A")
        e = daily_balanced_edge(rows, fn)
        nd = len({r["date"] for r in sub})
        if not s_:
            print("  %-22s 无样本" % name)
            continue
        print("  %-22s n=%-4d n日=%-3d 胜率A=%6.2f%% 均A=%+6.3f%% 盈亏比=%s｜逐日平衡edge=%s"
              % (name, s_["n"], nd, s_["winA"], s_["avgA"], s_["pl"],
                 ("%+.3fpp" % e) if e is not None else "—"))
        report["combo"][name] = {"n": s_["n"], "n_days": nd, **s_,
                                 "daily_edge": round(e, 3) if e is not None else None}

    # ---- ④ 退出工程：组合子集上的移动止盈 vs 固定 TP ----
    # 说明：fwd_first_touch 只支持固定 TP/SL；移动止盈用逐 bar 路径模拟（仅诊断）。
    print("\n---- ④ 退出工程诊断（强市×vol_top20 子集，路径级模拟）----")
    target = [r for r in rows if r.get("vol_top") and r["heat"] in ("强势", "震荡")]
    print("  子集 n=%d（强市+震荡 × vol_top20）" % len(target))
    # 固定参数网格（描述性）
    print("  %5s %5s %5s %6s %8s %8s %7s" % ("TP%", "SL%", "H", "n", "胜率%", "均%", "盈亏比"))
    for tp in (0.04, 0.06, 0.08, 0.10, 0.12):
        for sl in (0.06, 0.08):
            sub = []
            for r in target:
                raw = {k: v for k, v in r.items() if k not in ("ft", "ftA", "ftB")}
                ft = BT.fwd_first_touch(cache, raw, tp, sl, FWD)
                if ft:
                    sub.append({"ft": ft})
            s_ = agg([{"winA": bool(x["ft"]["win"]), "pnlA": x["ft"]["ret"] * 100,
                       "winB": False, "pnlB": 0} for x in sub], "A")
            if not s_:
                continue
            mark = "  ← edge>成本线" if s_["avgA"] > 0.15 else ""
            print("  %5g %5g %5d %6d %8.2f %+8.3f %7s%s"
                  % (tp * 100, sl * 100, FWD, s_["n"], s_["winA"], s_["avgA"], s_["pl"], mark))
            report["exit"]["+%g/-%g/%d" % (tp * 100, sl * 100, FWD)] = s_

    os.makedirs(OUT_DIR, exist_ok=True)
    outp = os.path.join(OUT_DIR, "vol5_diag_%s.json" % DS)
    json.dump(report, open(outp, "w", encoding="utf-8"), ensure_ascii=False, indent=1, sort_keys=True)
    print("\n存档：%s" % outp)


if __name__ == "__main__":
    main()
