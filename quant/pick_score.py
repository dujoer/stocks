# -*- coding: utf-8 -*-
"""精选池 · 稳健分（pick_score v1）

由 `quant/_pick_lab.py` 的样本外结论驱动，**不是又一套拍脑袋的权重表**。

结论回顾（详见 quant/_pick_lab_result.json 与 web/picks/lab.html）
------------------------------------------------------------------
1. 现有 `build_picks.py` 的 11 维思路，其可离线近似版（`STYLE_BASE`）在样本外是
   **负的**：训练 −7.3pp / 测试 −5.6pp（相对胜率）。即「按近 5 期归因调权重」这条路的
   方向本身就与实证相反。
2. **自动「筛因子」这个动作就是主要噪声源**：用前 60% 数据筛出 7 个因子再测后 40%，
   相对胜率只剩 **+0.5pp**；而同一批数据下「用全量筛因子」能报出 +8.2pp —— 7.7pp 的差额
   就是过拟合的量。所以本模块**不做筛选、不按回测调权重**。
3. **因子集固定 + 等权横截面分位**（方向由经济逻辑给定，不来自数据）在留出段是正的：
   价量组 相对胜率 +3.8pp / 绝对胜率 +2.6pp；价量+基本面 相对胜率 +4.3pp；
   6 段滚动全部为正。
4. 因此：因子固定为下面 12 个，方向固定，**等权**，在当日候选内做横截面分位。

因子口径（全部取自腾讯前复权日K + 东财业绩报表，无未来信息）
------------------------------------------------------------
价量 5 项：
  vol_day      当日量比 = 今量 ÷ 60 日均量         方向 −1（不过度拥挤）
  pullback_dry 回调缩量 = 近3日下跌日量能 ÷ 前10日量能  方向 −1（缩量回调=惜售）
  dist_hi20    距 20 日高（%，负值）                方向 +1（贴近 20 日高=趋势在）
  ovn20        近 20 日隔夜跳空累计贡献（%）        方向 +1（隔夜有资金承接）
  atr_comp     波动收敛 = ATR20 ÷ ATR60            方向 −1（波动收敛=蓄势）
基本面 7 项（东财业绩报表，最新报告期）：
  grow_rev  营收同比      +1     grow_q   单季净利同比  +1
  roe       加权 ROE      +1     mv_log   总市值(对数)  −1（小市值）
  ep        盈利收益率    +1     bp       账面市值比    +1
  amt20_log 20日均额(对数) −1（成交额小=小盘）
"""
from __future__ import annotations
import os, sys, json, math

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rev_pool as R

QUANT = os.path.dirname(os.path.abspath(__file__))
CACHE_F = os.path.join(QUANT, "_txk_cache.json")
FIN_F = os.path.join(QUANT, "fin", "snapshot.json")
MODEL_F = os.path.join(QUANT, "_pick_model.json")

# (键, 方向, 中文名)  —— 方向 −1 表示「数值越小越好」，分位按方向翻转
PRICE_FEATS = [
    ("vol_day",      -1, "量比(不拥挤)"),
    ("pullback_dry", -1, "缩量回调"),
    ("dist_hi20",     1, "贴近20日高"),
    ("ovn20",         1, "隔夜承接"),
    ("atr_comp",     -1, "波动收敛"),
]
FUND_FEATS = [
    ("grow_rev",  1, "营收同比"),
    ("grow_q",    1, "单季净利同比"),
    ("roe",       1, "ROE"),
    ("mv_log",   -1, "小市值"),
    ("ep",        1, "盈利收益率"),
    ("bp",        1, "账面市值比"),
    ("amt20_log", -1, "小成交额"),
]
ALL_FEATS = PRICE_FEATS + FUND_FEATS

_cache = None
_fin = None


def _load():
    global _cache, _fin
    if _cache is None:
        try:
            with open(CACHE_F, encoding="utf-8") as f:
                _cache = json.load(f)
        except Exception:
            _cache = {}
    if _fin is None:
        try:
            with open(FIN_F, encoding="utf-8") as f:
                _fin = json.load(f).get("stocks") or {}
        except Exception:
            _fin = {}
    return _cache, _fin


def load_model():
    """读取冻结模型（含 lab 的样本外证据摘要）；缺失返回 None。"""
    try:
        with open(MODEL_F, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _pct(a, b):
    return (a / b - 1) * 100 if b else 0.0


def features_for(code, date):
    """算出截至 date 的因子值（收盘后可用，无未来信息）。取不到返回 {}。"""
    cache, fin = _load()
    bars = cache.get(code)
    if not bars:
        return {}
    dmap = {}
    for k, b in enumerate(bars):
        dmap.setdefault(b["date"], k)
    i = dmap.get(date)
    if i is None:
        # 用不晚于 date 的最后一根
        cand = [k for k, b in enumerate(bars) if b["date"] <= date]
        if not cand:
            return {}
        i = cand[-1]
    if i < 45:
        return {}
    C = [b["last"] for b in bars]; H = [b["high"] for b in bars]
    L = [b["low"] for b in bars]; O = [b["open"] for b in bars]
    V = [b["volume"] for b in bars]
    if not C[i] or not V[i]:
        return {}
    close = C[i]
    v60 = sum(V[i - 59:i + 1]) / 60 if i >= 59 else sum(V[:i + 1]) / (i + 1)
    vol_day = V[i] / v60 if v60 else 1.0
    hi20 = max(H[i - 19:i + 1])
    dist_hi20 = _pct(close, hi20)
    # 隔夜累计
    ovn = 0.0
    for k in range(i - 19, i + 1):
        if C[k - 1] > 0:
            ovn += math.log(O[k] / C[k - 1])
    ovn20 = ovn * 100
    # 回调缩量
    dvol = sum(V[k] for k in range(i - 2, i + 1) if C[k] < O[k])
    pvol = sum(V[i - 12:i - 2]) / 2 if i > 12 else 0
    pullback_dry = (dvol / 3) / pvol if (dvol and pvol) else 1.0
    # ATR20 / ATR60
    def atr(w):
        s = 0.0
        for k in range(i - w + 1, i + 1):
            pc = C[k - 1] if k > 0 else C[k]
            s += max(H[k] - L[k], abs(H[k] - pc), abs(L[k] - pc))
        return s / w
    a20, a60 = atr(20), atr(60)
    atr_comp = (a20 / a60) if a60 else 1.0
    amt20 = sum(V[k] * C[k] for k in range(i - 19, i + 1)) / 20
    f = {"vol_day": vol_day, "pullback_dry": pullback_dry, "dist_hi20": dist_hi20,
         "ovn20": ovn20, "atr_comp": atr_comp,
         "amt20_log": math.log(amt20) if amt20 > 0 else None}
    fi = fin.get(code) or {}
    _eps = fi.get("eps"); _bps = fi.get("bps"); _npf = fi.get("netprofit")
    shares = (_npf / _eps) if (_npf and _eps and _eps > 0) else None
    mv = (close * shares) if shares else None
    f["mv_log"] = math.log(mv) if (mv and mv > 0) else None
    f["ep"] = (_eps / close * 100) if (_eps and close and _eps > 0) else None
    f["bp"] = (_bps / close * 100) if (_bps and close and _bps > 0) else None
    f["roe"] = fi.get("roe")
    f["grow_q"] = fi.get("q_yoy")
    f["grow_rev"] = fi.get("ystz")
    return f


def score_codes(codes, date, feats=None):
    """在给定候选集合内做**横截面分位等权**打分。

    返回 {code: {"score": 0~100, "rank": {因子: 0~1 分位}, "raw": {...}, "n_feat": n}}
    不使用任何绝对阈值 —— 分位天然自适应市场中枢漂移（lab 已验证的口径）。
    """
    use = feats or ALL_FEATS
    rows = {}
    for c in codes:
        f = features_for(c, date)
        if f:
            rows[c] = f
    if not rows:
        return {}
    # 逐因子算分位（在候选内部）
    rank = {c: {} for c in rows}
    valid = {}
    for name, d, _cn in use:
        vals = sorted([(rows[c].get(name), c) for c in rows if rows[c].get(name) is not None])
        n = len(vals)
        if n < 5:
            continue
        spread = vals[-1][0] - vals[0][0]
        if spread == 0:
            continue
        valid[name] = True
        for pos, (v, c) in enumerate(vals):
            r = pos / (n - 1) if n > 1 else 0.5
            rank[c][name] = r if d > 0 else 1 - r
    out = {}
    for c in rows:
        rk = rank[c]
        if len(rk) < max(3, len(valid) // 2):
            continue
        out[c] = {"score": round(sum(rk.values()) / len(rk) * 100, 1),
                  "rank": {k: round(v, 3) for k, v in rk.items()},
                  "raw": {k: rows[c].get(k) for k in rk},
                  "n_feat": len(rk)}
    return out


def env_state(date):
    """当日市场环境（全市场广度 = 站上 MA20 占比）→ 建议仓位系数。

    lab 实测：广度低（弱势）时基线绝对胜率仅 40.9%，广度高（强势）时 51.1% ——
    **环境对绝对胜率的影响（≈10pp）大于选股本身（≈1~3pp）**，故必须门控。
    """
    cache, _ = _load()
    up = tot = 0
    for c, bars in cache.items():
        idx = None
        for k in range(len(bars) - 1, -1, -1):
            if bars[k]["date"] <= date:
                idx = k; break
        if idx is None or idx < 20:
            continue
        C = [b["last"] for b in bars[max(0, idx - 19):idx + 1]]
        if not C[-1]:
            continue
        ma20 = sum(C) / len(C)
        up += 1 if C[-1] > ma20 else 0
        tot += 1
    if tot < 200:
        return {"breadth": None, "coef": 1.0, "label": "未知"}
    b = up / tot * 100
    if b >= 55:
        return {"breadth": round(b, 1), "coef": 1.0, "label": "强势（广度 %.1f%%）" % b}
    if b >= 35:
        return {"breadth": round(b, 1), "coef": 0.7, "label": "中性（广度 %.1f%%）" % b}
    return {"breadth": round(b, 1), "coef": 0.4, "label": "弱势（广度 %.1f%%，建议降暴露）" % b}


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--codes", default="", help="逗号分隔；缺省读 picks/candidates_{date}.json")
    a = ap.parse_args()
    cs = [x for x in a.codes.split(",") if x]
    if not cs:
        p = os.path.join(QUANT, "picks", "candidates_%s.json" % a.date)
        if os.path.exists(p):
            cs = [x["code"] for x in json.load(open(p, encoding="utf-8"))["candidates"]]
    r = score_codes(cs, a.date)
    print("环境：", env_state(a.date))
    print("打分 %d / %d 只" % (len(r), len(cs)))
    for c, v in sorted(r.items(), key=lambda kv: -kv[1]["score"])[:15]:
        print("  %-10s %.1f" % (c, v["score"]))
