# -*- coding: utf-8 -*-
"""退出模拟「假设口径」审计 —— 在生产主升面板上复核生产头牌数字（_exit_assumption_audit.py）

用户问（2026-10-04）：「那怎么优化，我想筛选赚钱的」→ 归因发现**成交假设支配结论**。
本脚本把这条发现落到**生产数字本身**：

  ① 用**生产主升面板**（_selected_lab_panel.json，162,177 行，与 _selected_model.json 同源）
     复现生产头牌数字（base_wr / A档 训练半·测试半可兑现胜率）；
  ② 只改「成交假设」（日内路径 × 跳空），重算同一批数字；
  ③ 报出差异 —— 差异即「虚高幅度」。

⚠ 面板只存 fh/fl 与 T+20 收盘标量，**无前向开盘价** → 从 _txk_cache.json 按 (code, date)
   重建 fO（跳空修正必需）。重建失败的样本**剔除并计数**，不静默补 0。

用法
----
    python _exit_assumption_audit.py --panel _selected_lab_panel.json --pct 0.05
"""
from __future__ import annotations
import os, sys, json, argparse, statistics, collections

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _selected_lab as S
import _selected_attrib as A
import _exit_sim as X

QUANT = HERE
PANEL = os.path.join(QUANT, "_selected_lab_panel.json")
CACHE = os.path.join(QUANT, "_txk_cache.json")
MODEL = os.path.join(QUANT, "_selected_model.json")
OUT = os.path.join(QUANT, "_exit_assumption_audit.json")

FMAX = S.FMAX


def attach_fwd_open(rows, cache_path):
    """按 (code, date) 重建前向开盘价 fO；返回 (保留行, 剔除计数)。"""
    cache = json.load(open(cache_path, encoding="utf-8"))
    idx = {}
    for c, bars in cache.items():
        idx[c] = {b["date"]: k for k, b in enumerate(bars)}
    kept, drop = [], 0
    for r in rows:
        c, T = r["code"], r["date"]
        k = idx.get(c, {}).get(T)
        if k is None:
            drop += 1
            continue
        bars = cache[c]
        if k + FMAX >= len(bars):
            drop += 1
            continue
        fO = [bars[k + 1 + j]["open"] for j in range(FMAX)]
        if any(o is None or o <= 0 for o in fO):
            drop += 1
            continue
        r["fO"] = fO
        kept.append(r)
    del cache
    return kept, drop


def _wr(pnls):
    return 100.0 * sum(1 for x in pnls if x > 0) / len(pnls) if pnls else 0.0


def _mean(pnls):
    return sum(pnls) / len(pnls) if pnls else 0.0


def build(panel_path, pct, cost):
    rows = json.load(open(panel_path, encoding="utf-8"))
    n_raw = len(rows)
    pst = os.stat(panel_path)
    panel_stamp = {"file": os.path.basename(panel_path), "bytes": pst.st_size,
                   "mtime": int(pst.st_mtime)}
    rows, drop = attach_fwd_open(rows, CACHE)
    print("[panel] 原始 %d 行 → 重建 fO 后 %d 行（剔除 %d，均因缺开盘价/越界）"
          % (n_raw, len(rows), drop))

    # 打分（与生产等权口径一致，直接复用 _selected_attrib.score_by_date）
    A.score_by_date(rows)
    tops = A.top_of_day(rows, pct)
    dates = sorted(set(r["date"] for r in rows))
    cut = dates[len(dates) // 2]
    tr = [r for r in tops if r["date"] < cut]
    te = [r for r in tops if r["date"] >= cut]
    print("[split] 两半切分 cut=%s  A档 %d 行（前 %d / 后 %d）"
          % (cut, len(tops), len(tr), len(te)))

    res = {"panel": os.path.basename(panel_path), "n_rows": len(rows),
           "n_drop": drop, "pct": pct, "cost": cost, "cut": cut,
           "panel_stamp": panel_stamp,
           "params": {"stop": X.STOP, "act": X.ACT, "trail": X.TRAIL, "hold": X.MAXFWD},
           "modes": [], "model_ref": None}

    for name, cons, gap in X.MODES:
        def run(ss):
            ps = []
            for r in ss:
                v, _, _ = X.sim_exit(r.get("fc"), r["fh"], r["fl"], r["_close"],
                                     X.STOP, X.ACT, X.TRAIL, X.MAXFWD, cons,
                                     r.get("fO") if gap else None)
                ps.append(v)
            return ps

        b = run(rows)
        t = run(tops)
        t1, t2 = run(tr), run(te)
        net_t = [x - cost for x in t]
        net_b = [x - cost for x in b]
        ent = {
            "mode": name, "cons": cons, "gap": gap,
            "base_wr": round(_wr(b), 2), "base_mean": round(_mean(b), 3),
            "top_wr": round(_wr(t), 2), "top_mean": round(_mean(t), 3),
            "top_net": round(_mean(net_t), 3),
            "train_wr": round(_wr(t1), 2), "train_mean": round(_mean(t1), 3),
            "test_wr": round(_wr(t2), 2), "test_mean": round(_mean(t2), 3),
            "base_net": round(_mean(net_b), 3),
            "same_sign": (_mean(t1) > 0) == (_mean(t2) > 0),
        }
        res["modes"].append(ent)
        print("\n[%s]  cons=%s gap=%s" % (name, cons, gap))
        print("   全样本  可兑现胜率 %5.2f%%  单笔 %+.3f%%  净 %+.3f%%"
              % (ent["base_wr"], ent["base_mean"], ent["base_net"]))
        print("   A档(前%.0f%%) 可兑现胜率 %5.2f%%  单笔 %+.3f%%  净 %+.3f%%"
              % (pct * 100, ent["top_wr"], ent["top_mean"], ent["top_net"]))
        print("   A档两半  前半 %5.2f%%(%+.3f%%)  后半 %5.2f%%(%+.3f%%)  %s"
              % (ent["train_wr"], ent["train_mean"], ent["test_wr"], ent["test_mean"],
                 "同向" if ent["same_sign"] else "★反向"))

    # 与冻结模型记录的证据对照
    try:
        m = json.load(open(MODEL, encoding="utf-8"))
        ev = m.get("evidence", {})
        res["model_ref"] = {
            "built_at": m.get("built_at"),
            "base_wr": round(ev.get("base_wr"), 2) if ev.get("base_wr") is not None else None,
            "base_ret": round(ev.get("base_ret"), 3) if ev.get("base_ret") is not None else None,
            "prior_test_wr": round(ev.get("prior_test_wr"), 2) if ev.get("prior_test_wr") is not None else None,
            "train_wr": round(ev.get("train_wr"), 2) if ev.get("train_wr") is not None else None,
            "test_wr": round(ev.get("test_wr"), 2) if ev.get("test_wr") is not None else None,
        }
        print("\n[对照] 冻结模型 _selected_model.json（built_at %s）" % res["model_ref"]["built_at"])
        print("   base_wr %s / prior_test_wr %s / train_wr %s / test_wr %s"
              % (res["model_ref"]["base_wr"], res["model_ref"]["prior_test_wr"],
                 res["model_ref"]["train_wr"], res["model_ref"]["test_wr"]))
    except Exception as e:
        print("[warn] 读模型失败：%s" % e)

    json.dump(res, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n[out] %s" % OUT)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--panel", default=PANEL)
    ap.add_argument("--pct", type=float, default=0.05)
    ap.add_argument("--cost", type=float, default=0.15)
    a = ap.parse_args()
    build(a.panel, a.pct, a.cost)


if __name__ == "__main__":
    main()
