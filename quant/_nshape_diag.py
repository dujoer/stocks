# -*- coding: utf-8 -*-
"""N字形 hb_pos 信号全维度切片诊断（描述性，非选参）。

铁律遵守：
- 信号口径 = eval_stock_signal + is_hb_pos（与主池/回测/模拟器同一真源），杜绝口径分叉；
- 首次触及 = fwd_first_touch（与回测 DEF 档同实现）；
- 本脚本只做「描述性切片」找负期望来源，任何参数/规则优势必须另走 walk-forward + bootstrap R3 + 经济闸；
- 样本不足的桶标注「样本不足」，缺失不当结论。
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_n_shape as NS          # noqa: E402
import build_n_shape_backtest as BT  # noqa: E402
import _txk                          # noqa: E402

QUANT = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(QUANT, "n_shape")

DEF_TP, DEF_SL, DEF_FWD = 0.06, 0.08, 10  # fwd_first_touch 收小数（0.06=+6%），勿传百分数

BUCKETS = {
    # 维度 -> [(标签, 判定函数)]
    "市场热度": lambda s: s.get("heat_label") or "未知",
    "距涨停天数": [
        ("0-2日", lambda s: (s.get("days_since_zt") or 0) <= 2),
        ("3-4日", lambda s: 3 <= (s.get("days_since_zt") or 0) <= 4),
        ("5日以上", lambda s: (s.get("days_since_zt") or 0) >= 5),
    ],
    "涨停后回撤": [
        ("≥-3%", lambda s: (s.get("pullback_pct") or 0) >= -3),
        ("-3~-6%", lambda s: -6 <= (s.get("pullback_pct") or 0) < -3),
        ("-6~-10%", lambda s: -10 <= (s.get("pullback_pct") or 0) < -6),
        ("<-10%", lambda s: (s.get("pullback_pct") or 0) < -10),
    ],
    "距局部峰": [
        ("-5~-10%", lambda s: -10 <= (s.get("dist_local_peak") or 0) <= -5),
        ("-10~-20%", lambda s: -20 <= (s.get("dist_local_peak") or 0) < -10),
        ("-20~-30%", lambda s: -30 <= (s.get("dist_local_peak") or 0) < -20),
    ],
    "52周分位": [
        ("30-50", lambda s: s.get("pos_pctile") is not None and 30 <= s["pos_pctile"] < 50),
        ("50-70", lambda s: s.get("pos_pctile") is not None and 50 <= s["pos_pctile"] < 70),
        ("70-85", lambda s: s.get("pos_pctile") is not None and 70 <= s["pos_pctile"] <= 85),
    ],
    "20日均额(亿)": [
        ("<5", lambda s: (s.get("avg_amt_yi") or 0) < 5),
        ("5-15", lambda s: 5 <= (s.get("avg_amt_yi") or 0) < 15),
        ("≥15", lambda s: (s.get("avg_amt_yi") or 0) >= 15),
    ],
    "当日涨幅": [
        ("<0", lambda s: (s.get("chg_pct") or 0) < 0),
        ("0~3", lambda s: 0 <= (s.get("chg_pct") or 0) < 3),
        ("≥3", lambda s: (s.get("chg_pct") or 0) >= 3),
    ],
    "距MA5": [
        ("0-3%", lambda s: 0 <= (s.get("dist_ma5") or 0) <= 3),
        ("3-6%", lambda s: 3 < (s.get("dist_ma5") or 0) <= 6),
        (">6%", lambda s: (s.get("dist_ma5") or 0) > 6),
    ],
    "热点": [
        ("热点", lambda s: bool(s.get("hot"))),
        ("非热点", lambda s: not s.get("hot")),
    ],
}

TP_GRID = [0.04, 0.06, 0.08, 0.10, 0.12, 0.15]
SL_GRID = [0.06, 0.08, 0.10, 0.12]
H_GRID = [10, 20]


def agg(rows):
    """聚合一组已带 ft 结果的信号。返回描述统计（非门禁）。"""
    n = len(rows)
    if n == 0:
        return None
    wins = [r for r in rows if r["ft"]["win"]]
    rets = [r["ft"]["ret"] for r in rows]
    wp = sum(r["ft"]["ret"] for r in wins) / len(wins) if wins else 0.0
    lp = sum(r["ft"]["ret"] for r in rows if not r["ft"]["win"]) / max(1, n - len(wins)) if n - len(wins) else 0.0
    return {
        "n": n,
        "win_rate": round(len(wins) / n * 100, 2),
        "avg_ret": round(sum(rets) / n, 3),
        "avg_win": round(wp, 3),
        "avg_loss": round(lp, 3),
        "pl_ratio": round(abs(wp / lp), 2) if lp else None,
        "edge_pp": round(sum(rets) / n, 3),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None)
    ap.add_argument("--asof", type=int, default=None,
                    help="回测 as-of 日数量（默认用回测配置 N_DATES；扩大窗口=扩大样本与市场状态覆盖）")
    a = ap.parse_args()
    D = a.date or NS.latest_date()
    n_asof = a.asof or BT.N_DATES
    print("=== N字形 hb_pos 全维度切片诊断 · 数据日 %s · as-of %d 日 ===" % (D, n_asof))

    try:
        _txk.set_asof(D)
    except Exception:
        pass
    cache = _txk.load()
    name_map = NS.load_name_map(D)
    name2sw2 = NS.load_name2sw2()
    ind_map, concept_leaders = NS.load_hot_maps()
    w52 = NS.load_52w_cache(cache)

    asof_dates = BT.pick_asof_dates(cache, n=n_asof, fwd=BT.FWD)
    print("回测日 %d 个：%s ~ %s" % (len(asof_dates), asof_dates[0], asof_dates[-1]))

    # 大盘热度（≤信号日，无未来函数）
    heat_map = {}
    for d in asof_dates:
        try:
            heat_map[d] = (NS.load_market_heat(d) or {}).get("label") or "未知"
        except Exception:
            heat_map[d] = "未知"

    all_sigs = []
    for d in asof_dates:
        rows = NS.gen_signals_asof(cache, d, name_map)
        NS.attach_attr(rows, name2sw2, ind_map, concept_leaders, w52)
        for r in rows:
            r["asof"] = d
            r["heat_label"] = heat_map.get(d, "未知")
            ft = BT.fwd_first_touch(cache, r, DEF_TP, DEF_SL, DEF_FWD)
            if ft:
                r["ft"] = ft
                all_sigs.append(r)

    print("全量信号 %d 条（含 ft）" % len(all_sigs))
    hb = [s for s in all_sigs if BT.is_hb_pos(s)]
    base = agg(hb)
    print("hb_pos 基准（DEF +%g%%/-%g%%/%d日）：n=%s 胜率=%s%% 均=%s%% 盈亏比=%s"
          % (DEF_TP * 100, DEF_SL * 100, DEF_FWD, base["n"], base["win_rate"],
             round(base["avg_ret"] * 100, 2), base["pl_ratio"]))

    # as-of 日的市场热度构成（样本集中度披露——10 个回测日若几乎全是弱市，结论只覆盖弱市）
    from collections import Counter
    hc = Counter(heat_map.get(d, "未知") for d in asof_dates)
    print("as-of 日热度构成：%s" % dict(hc))

    # ---- 分桶诊断 ----
    report = {"date": D, "asof_range": [asof_dates[0], asof_dates[-1]],
              "n_asof": len(asof_dates), "base": base, "buckets": {}, "grid": {}}
    for dim, spec in BUCKETS.items():
        if callable(spec):
            keys = sorted({spec(s) or "未知" for s in hb})
            entries = [(lambda s, _f=spec, _k=k: (_f(s) or "未知") == _k, k) for k in keys]
        else:
            entries = [(fn, lab) for lab, fn in spec]
        report["buckets"][dim] = {}
        print("\n---- %s ----" % dim)
        for fn, key in entries:
            rows = [s for s in hb if fn(s)]
            a_ = agg(rows)
            if a_ is None:
                print("  %-8s 无样本" % key)
                continue
            flag = "" if a_["n"] >= 30 else "  ⚠样本不足"
            print("  %-8s n=%-4d 胜率=%6.2f%% 均=%+6.2f%% 盈=%+.2f 亏=%+.2f 比=%s%s"
                  % (key, a_["n"], a_["win_rate"], a_["avg_ret"] * 100, a_["avg_win"] * 100,
                     a_["avg_loss"] * 100, a_["pl_ratio"], flag))
            report["buckets"][dim][key] = a_

    # ---- 参数网格（描述性扫描，非选参） ----
    print("\n---- TP×SL×H 网格（hb_pos 全量，描述性；单位%）----")
    print("  %5s %5s %4s %5s %8s %8s %7s" % ("TP", "SL", "H", "n", "胜率%", "均收益%", "盈亏比"))
    for tp in TP_GRID:
        for sl in SL_GRID:
            for h in H_GRID:
                rows = []
                for s in hb:
                    raw = {k: v for k, v in s.items() if k != "ft"}
                    ft = BT.fwd_first_touch(cache, raw, tp, sl, h)
                    if ft:
                        rows.append({"ft": ft})
                a_ = agg(rows)
                if a_ is None:
                    continue
                mark = ""
                if a_["avg_ret"] > 0.15 and a_["n"] >= 30:
                    mark = "  ← edge>0.15pp"
                print("  %5g %5g %4d %5d %8.2f %8.2f %7s%s"
                      % (tp * 100, sl * 100, h, a_["n"], a_["win_rate"], a_["avg_ret"] * 100, a_["pl_ratio"], mark))
                report["grid"]["+%g/-%g/%d" % (tp * 100, sl * 100, h)] = a_

    os.makedirs(OUT_DIR, exist_ok=True)
    out = os.path.join(OUT_DIR, "diag_%s_asof%d.json" % (D.replace("-", ""), n_asof))
    json.dump(report, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1, sort_keys=True)
    print("\n存档：%s" % out)
    print("注：以上均为描述性统计；任何优势档位必须 walk-forward 选参 + bootstrap R3 + 经济闸复核。")


if __name__ == "__main__":
    main()
