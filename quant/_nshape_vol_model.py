#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""N字形 · 量能评分模型（2026-10-24）——训练/冻结/加载/打分/档位标记

定位（务必与铁律一致）：
  - 量能特征是**预测参数**（用户方向），本模型把 9 个量能构造合成连续预测分
    （逻辑回归预测「首触 +10%/-8%/10日」胜率，×100 显示）。
  - 验证结论（quant/n_shape/vol_final2_*_step*.json）：
      step10：OOS edge +3.147pp / R3 99.9 / loo +2.657 / 前后半 +3.0/+3.3 / 随机对照 2.5%
      step5 ：OOS edge +2.431pp / R3 99.4 / loo +1.839 / 前后半 +2.0/+2.9 / 随机对照 7.5%
    → **跨步长随机对照不一致（2.5% vs 7.5%）+ 绝对收益≈0 → 不出票**，
      仅作「量能优选观察档」：透明评分 + 当日 hb_pos 前 20% 标记，需配合环境门控。
  - 模型只在验证脚本中重训（如每周）；日更仅加载冻结权重打分（无未来函数：
      训练样本 as-of 日均有完整 10 日前向窗，即 as-of ≤ 数据日-10 日）。

用法：
  python3 quant/_nshape_vol_model.py --train [--date D] [--asof 60]  # 训练并冻结
  引擎侧：import _nshape_vol_model as VM; VM.attach_vol(rows, cache); VM.mark_vol_top(rows)
"""
import argparse
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _txk
import build_n_shape as NS
import build_n_shape_backtest as BT
from _nshape_vol3 import rich_vol_features, logistic_fit, logistic_pred

MODEL_PATH = os.path.join(HERE, "n_shape", "vol_model.json")
FEATS = ["v_turn", "v_surge", "v_peak", "obv_slope", "v_ud3", "v_reb",
         "vseq", "vr_now", "vtrend"]
TOP_FRAC = 0.2          # 当日 hb_pos 前 20%（与 walk-forward 选择口径一致）


def _xvec(r, med):
    out = []
    for f in FEATS:
        v = r["vf"].get(f)
        if v is None:
            v = med[f]
        if f in ("v_turn", "v_surge", "v_peak", "v_ud3", "v_reb",
                 "vseq", "vr_now", "vtrend"):
            out.append(math.log(max(1e-6, float(v))))
        else:
            out.append(float(v))
    return out


def train(D=None, asof=60, out=MODEL_PATH):
    """在 as-of 窗上训练并冻结模型。样本 = hb_pos ∩ 有完整 10 日前向窗。"""
    D = D or NS.latest_date()
    try:
        _txk.set_asof(D)
    except Exception:
        pass
    cache = _txk.load()
    name_map = NS.load_name_map(D)
    name2sw2 = NS.load_name2sw2()
    ind_map, cl = NS.load_hot_maps()
    w52 = NS.load_52w_cache(cache)
    dates = BT.pick_asof_dates(cache, n=asof, fwd=BT.FWD)
    rows = []
    for d in dates:
        day = NS.gen_signals_asof(cache, d, name_map)
        NS.attach_attr(day, name2sw2, ind_map, cl, w52)
        for r in day:
            if not BT.is_hb_pos(r):
                continue
            raw = {k: v for k, v in r.items() if k != "ft"}
            fa = BT.fwd_first_touch(cache, raw, 0.10, 0.08, 10)
            if not fa:
                continue
            vf = rich_vol_features(r["code"], cache[r["code"]], r["asof_idx"], r)
            if not vf:
                continue
            r.update({"date": d, "ftA": fa, "vf": vf, "winA": bool(fa["win"])})
            rows.append(r)
    if len(rows) < 100:
        print("训练样本不足（%d），不冻结" % len(rows))
        return None
    med = {}
    for f in FEATS:
        vs = sorted(r["vf"][f] for r in rows if r["vf"].get(f) is not None)
        med[f] = vs[len(vs) // 2] if vs else 1.0
    X = [_xvec(r, med) for r in rows]
    y = [1 if r["winA"] else 0 for r in rows]
    w, b, mu, sd = logistic_fit(X, y)
    # 训练窗内 AUC（描述）
    pairs = [(logistic_pred((w, b, mu, sd), x), yy) for x, yy in zip(X, y)]
    pos = [p for p, yy in pairs if yy == 1]
    neg = [p for p, yy in pairs if yy == 0]
    n1, n0 = len(pos), len(neg)
    gt = sum(1 for p in pos for q in neg if p > q) + 0.5 * sum(1 for p in pos for q in neg if p == q)
    auc_tr = gt / (n1 * n0) if n1 and n0 else None

    # 嵌入 WF 验证证据（只读存档，不写死）
    val = {}
    for step in (5, 10):
        p = os.path.join(HERE, "n_shape", "vol_final2_%s_step%d.json" % (D.replace("-", ""), step))
        if os.path.exists(p):
            j = json.load(open(p, encoding="utf-8"))
            o = j.get("oos", {})
            val["step%d" % step] = {
                "n_top": o.get("n_top"), "winA": o.get("winA"), "winB": o.get("winB"),
                "edge": o.get("edge"), "r3": o.get("r3"),
                "loo_min": o.get("loo_min"), "half1": o.get("half1"), "half2": o.get("half2"),
                "rand_hit_pct": (j.get("random_control") or {}).get("hit_rate_pct"),
                "licensed": j.get("licensed")}
    model = {"feats": FEATS, "w": w, "b": b, "mu": mu, "sd": sd, "med": med,
             "top_frac": TOP_FRAC,
             "trained_on": {"date": D, "asof": asof, "n_rows": len(rows),
                            "window": [dates[0], dates[-1]],
                            "train_auc": round(auc_tr, 4) if auc_tr else None,
                            "base_winA": round(sum(y) / len(y) * 100, 2)},
             "validation": val,
             "note": "量能优选观察档·非出票：跨步长随机对照不一致(step5 7.5%>5%)+绝对收益≈0，"
                     "需配合环境门控；WF OOS edge 见 validation。",
             "target": "首触+10%/-8%/10日 胜率"}
    os.makedirs(os.path.dirname(out), exist_ok=True)
    json.dump(model, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1, sort_keys=True)
    print("模型已冻结：%s（训练 %d 行，窗 %s~%s，train AUC=%s）"
          % (out, len(rows), dates[0], dates[-1],
             round(auc_tr, 4) if auc_tr else "NA"))
    return model


def load_model(path=MODEL_PATH):
    if not os.path.exists(path):
        return None
    try:
        return json.load(open(path, encoding="utf-8"))
    except Exception:
        return None


def score(r, model):
    """0-100 预测分（首触+10%胜率概率×100）。缺模型返回 None。"""
    if not model or not r.get("vf"):
        return None
    x = _xvec(r, model["med"])
    p = logistic_pred((model["w"], model["b"], model["mu"], model["sd"]), x)
    return round(p * 100, 1)


def attach_vol(rows, cache, model=None):
    """给信号行附加 vf 特征 + vol_score。返回成功打分条数。"""
    if model is None:
        model = load_model()
    if not model:
        for r in rows:
            r["vol_score"] = None
        return 0
    n = 0
    for r in rows:
        vf = rich_vol_features(r["code"], cache.get(r["code"]) or [], r["asof_idx"], r)
        if not vf:
            r["vol_score"] = None
            continue
        r["vf"] = vf
        r["vol_score"] = score(r, model)
        if r["vol_score"] is not None:
            n += 1
    return n


def mark_vol_top(rows, frac=None):
    """按「当日 hb_pos 前 frac」标记 vol_top（与 WF 选择口径一致）。"""
    frac = frac or TOP_FRAC
    by_day = {}
    for r in rows:
        by_day.setdefault(r.get("date") or "_", []).append(r)
    n_mark = 0
    for _d, rs in by_day.items():
        scored = [r for r in rs if r.get("vol_score") is not None]
        scored.sort(key=lambda r: -r["vol_score"])
        k = max(1, int(len(scored) * frac)) if scored else 0
        for r in scored[:k]:
            r["vol_top"] = True
            n_mark += 1
    return n_mark


def is_hb_vol(s):
    """量能优选观察档（2026-10-24，非出票）：hb_pos ∩ 当日 vol_score 前 20%。"""
    return bool(s.get("vol_top"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--train", action="store_true")
    ap.add_argument("--date", default=None)
    ap.add_argument("--asof", type=int, default=60)
    a = ap.parse_args()
    if a.train:
        train(a.date, a.asof)
    else:
        m = load_model()
        print(json.dumps({k: m.get(k) for k in ("feats", "top_frac", "trained_on", "note")},
                         ensure_ascii=False, indent=1) if m else "无模型文件")


if __name__ == "__main__":
    main()
