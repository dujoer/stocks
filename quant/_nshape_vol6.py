# -*- coding: utf-8 -*-
"""N字形 · 退出工程测试（2026-10-25）：量能优选子集上 移动止盈 vs 固定首触。

背景：选股维度（价格/位置/量能）已多轮验证——量能优选有相对 edge 但绝对≈0。
退出工程是唯一未测试的维度。本项目唯一规范退出实现 = _exit_sim.sim_exit
（保守日内路径 + 跳空成交，口径见该模块 docstring；旧乐观口径已证伪）。

本脚本在同一入场集合上对比：
  A. 固定首触（TP/SL/H，fwd_first_touch 口径）
  B. 移动止盈（stop/act/trail/hold 网格，sim_exit 可实现口径 cons=True+gap）
入场集合：hb_pos 全集 / vol_top20% / 强震荡×vol_top（描述性分组）
指标：池化均收益/胜率/盈亏比 + 逐日平衡 edge（对照=当日全集）。

诚实标注：入场子集由冻结模型在全窗口上打分（样本内），
退出对比只回答「同一批入场，哪种退出更优」，元层选择偏差由后续 WF 处理。
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _txk
import build_n_shape as NS
import build_n_shape_backtest as BT
import _nshape_vol_model as VM
from _exit_sim import sim_exit

QUANT = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(QUANT, "n_shape")
TP_A, SL_A, FWD = 0.10, 0.08, 10


def fwd_bars(cache, code, aidx, hold):
    """前向 C/H/L/O 序列（T+1..T+hold），不足返回 None。"""
    bars = cache.get(code) or []
    seg = bars[aidx + 1: aidx + 1 + hold]
    if len(seg) < hold:
        return None
    return ([b["last"] for b in seg], [b["high"] for b in seg],
            [b["low"] for b in seg], [b["open"] for b in seg])


def stats(rows):
    if not rows:
        return None
    n = len(rows)
    w = sum(1 for r in rows if r["pnl"] > 0) / n * 100
    m = sum(r["pnl"] for r in rows) / n
    wins = [r["pnl"] for r in rows if r["pnl"] > 0]
    loss = [r["pnl"] for r in rows if r["pnl"] <= 0]
    aw = sum(wins) / len(wins) if wins else 0.0
    al = sum(loss) / len(loss) if loss else 0.0
    return {"n": n, "win": round(w, 2), "avg": round(m, 3),
            "avg_win": round(aw, 2), "avg_loss": round(al, 2),
            "pl": round(abs(aw / al), 2) if al else None,
            "hold": round(sum(r["hold"] for r in rows) / n, 1)}


def daily_edge(rows, sel_fn):
    by_day = {}
    for r in rows:
        by_day.setdefault(r["date"], []).append(r)
    diffs = []
    for _d, rs in by_day.items():
        sub = [r for r in rs if sel_fn(r)]
        if not sub:
            continue
        m_all = sum(r["pnl"] for r in rs) / len(rs)
        m_sub = sum(r["pnl"] for r in sub) / len(sub)
        diffs.append(m_sub - m_all)
    return round(sum(diffs) / len(diffs), 3) if diffs else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None)
    ap.add_argument("--asof", type=int, default=60)
    a = ap.parse_args()
    D = a.date or NS.latest_date()
    DS = D.replace("-", "")
    print("=== N字形 退出工程测试（量能子集 × 移动止盈）· 数据日 %s ===" % D)

    _txk.set_asof(D)
    cache = _txk.load()
    name_map = NS.load_name_map(D)
    name2sw2 = NS.load_name2sw2()
    ind_map, cl = NS.load_hot_maps()
    w52 = NS.load_52w_cache(cache)
    dates = BT.pick_asof_dates(cache, n=a.asof, fwd=FWD)
    print("as-of 窗口：%s → %s（%d 日）" % (dates[0], dates[-1], len(dates)))

    # ---- 建行（hb_pos 全集 = 对照域）----
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
    model = VM.load_model()
    VM.attach_vol(rows, cache, model)
    VM.mark_vol_top(rows)
    print("hb_pos 行：%d（可打分 %d，vol_top %d）"
          % (len(rows), sum(1 for r in rows if r.get("vol_score") is not None),
             sum(1 for r in rows if r.get("vol_top"))))

    report = {"date": D, "asof": a.asof, "groups": {}}

    groups = {
        "hb_pos全集": lambda r: True,
        "vol_top20": lambda r: bool(r.get("vol_top")),
        "强震荡×vol_top": lambda r: bool(r.get("vol_top")) and r["heat"] in ("强势", "震荡"),
    }

    for gname, gsel in groups.items():
        sub = [r for r in rows if gsel(r)]
        print("\n---- %s（n=%d，n日=%d）----" % (gname, len(sub), len({r["date"] for r in sub})))
        rep = {}

        # A. 固定首触基准
        fa = []
        for r in sub:
            raw = {k: v for k, v in r.items() if k != "ft"}
            ft = BT.fwd_first_touch(cache, raw, TP_A, SL_A, FWD)
            if ft:
                rr = dict(r)
                rr["pnl"] = ft["ret"] * 100
                rr["hold"] = ft.get("bars") or FWD
                fa.append(rr)
        sa = stats(fa)
        print("  [固定首触 +10/-8/10] n=%s 胜率=%s%% 均=%s%% 盈亏比=%s 均持=%s天"
              % (sa["n"], sa["win"], sa["avg"], sa["pl"], sa["hold"]))
        rep["fixed_10_8"] = sa

        # 固定首触参数网格（描述性）
        print("  固定首触网格（描述性）:")
        for tp in (0.06, 0.08, 0.10, 0.12):
            line = []
            for sl in (0.06, 0.08, 0.10):
                fr = []
                for r in sub:
                    raw = {k: v for k, v in r.items() if k != "ft"}
                    ft = BT.fwd_first_touch(cache, raw, tp, sl, FWD)
                    if ft:
                        rr = dict(r)
                        rr["pnl"] = ft["ret"] * 100
                        rr["hold"] = ft.get("bars") or FWD
                        fr.append(rr)
                s_ = stats(fr)
                line.append("+%d/-%d: %s%%/%s%%" % (tp * 100, sl * 100, s_["win"], s_["avg"]))
                rep["fixed_+%d_-%d" % (tp * 100, sl * 100)] = s_
            print("    " + " ｜ ".join(line))

        # B. 移动止盈网格（可实现口径）
        print("  移动止盈网格（保守日内+跳空成交；缺前向bar的行按格跳过并披露）:")
        print("    %6s %6s %6s %5s %8s %8s %7s %6s %6s" % ("止损%", "激活%", "回撤%", "持有", "n", "胜率%", "均%", "盈亏比", "均持"))
        best = None
        for stop in (0.08, 0.10, 0.12):
            for act in (0.04, 0.06):
                for trail in (0.03, 0.05):
                    for hold in (10, 20):
                        fr = []
                        dropped = 0
                        for r in sub:
                            fb = fwd_bars(cache, r["code"], r["asof_idx"], hold)
                            if not fb:
                                dropped += 1
                                continue
                            fC, fH, fL, fO = fb
                            px = cache[r["code"]][r["asof_idx"]]["last"]
                            pnl, hd, _mae = sim_exit(fC, fH, fL, px,
                                                     stop=stop, act=act, trail=trail,
                                                     hold=hold, cons=True, fO=fO)
                            rr = dict(r)
                            rr["pnl"] = pnl
                            rr["hold"] = hd
                            fr.append(rr)
                        if not fr:
                            continue
                        s_ = stats(fr)
                        mark = ""
                        if s_["avg"] > 0.15:
                            mark = "  ← >成本线"
                        print("    %6g %6g %6g %5d %5d %8.2f %+8.3f %7s %6.1f%s%s"
                              % (stop * 100, act * 100, trail * 100, hold, s_["n"],
                                 s_["win"], s_["avg"], s_["pl"], s_["hold"], mark,
                                 ("  [缺bar丢%d]" % dropped) if dropped else ""))
                        key = "trail_%d_%d_%d_%d" % (stop * 100, act * 100, trail * 100, hold)
                        rep[key] = s_
                        rep[key]["dropped"] = dropped
                        if best is None or s_["avg"] > best[1]["avg"]:
                            best = (key, s_)
        if best:
            print("  最优移动止盈：%s → 均 %+.3f%%（固定首触基准 %+.3f%%，注：行集可能不同）"
                  % (best[0], best[1]["avg"], sa["avg"]))
            rep["best_trail"] = {"key": best[0], **best[1]}

        # 同子集固定首触基准（仅对有满 20 根前向bar的行，保证与 trail_*_20 可比）
        fr20 = []
        for r in sub:
            if not fwd_bars(cache, r["code"], r["asof_idx"], 20):
                continue
            raw = {k: v for k, v in r.items() if k != "ft"}
            ft = BT.fwd_first_touch(cache, raw, TP_A, SL_A, FWD)
            if ft:
                rr = dict(r)
                rr["pnl"] = ft["ret"] * 100
                rr["hold"] = ft.get("bars") or FWD
                fr20.append(rr)
        s20 = stats(fr20)
        if s20:
            print("  同子集固定首触基准（满20根bar行，n=%d）：胜率=%.2f%% 均=%+.3f%%"
                  % (s20["n"], s20["win"], s20["avg"]))
            rep["fixed_10_8_full20"] = s20

        # 逐日平衡 edge（各退出 vs 当日全集同退出）
        print("  逐日平衡 edge（子集−当日全集，同退出口径）:")
        for key in ("fixed_10_8",):
            if key not in rep:
                continue
            # 全集同退出
            fullr = []
            for r in rows:
                raw = {k: v for k, v in r.items() if k != "ft"}
                ft = BT.fwd_first_touch(cache, raw, TP_A, SL_A, FWD)
                if ft:
                    rr = dict(r)
                    rr["pnl"] = ft["ret"] * 100
                    rr["hold"] = ft.get("bars") or FWD
                    fullr.append(rr)
            allrows = fullr + [x for x in fa]
            e = daily_edge(allrows, lambda r: id(r) in {id(x) for x in fa})
            print("    %s: edge=%s" % (key, e))
            rep[key]["daily_edge"] = e

        report["groups"][gname] = rep

    os.makedirs(OUT_DIR, exist_ok=True)
    outp = os.path.join(OUT_DIR, "vol6_exit_%s.json" % DS)
    json.dump(report, open(outp, "w", encoding="utf-8"), ensure_ascii=False, indent=1, sort_keys=True)
    print("\n存档：%s" % outp)


if __name__ == "__main__":
    main()
