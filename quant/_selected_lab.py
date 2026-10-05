# -*- coding: utf-8 -*-
"""主升精选观察池 · 全市场域 · 先验固定因子集横截面分位 + 样本外验证。

与底部反转池(v5)/做T池(v6) 同一范式：全市场域（剔 ST/退/低流动）+ 先验固定因子集
（方向由经济逻辑给定、等权、不筛不调权）+ 域内横截面分位定档 + 环境门控（仓位系数）
+ 移动止盈退出口径验证「可兑现胜率」。

主升精选 = 趋势已转多（动量 / 均线多头 / 站上长期均线）与 资金确认（上涨放量 /
量价齐升）双确认。因子全部为「比率 / 价格比」，规避跨板块成交量单位差
（科创板按股、其余按手，差 100 倍——绝对量口径会系统性压分，见 quant 数据笔记）。

胜率口径（与 web/reversal 完全可比，便于横向对照）：信号日收盘买入 → 未盈利前
−stop 硬止损；浮盈 ≥ +act 后止损上移为「持仓最高价 ×(1−trail)」跟踪；满 FMAX 日强平。
「可兑现胜率」= 该退出规则下盈利交易占比。目标：A 档（域内前 X%）严格样本外 >60%。
"""
from __future__ import annotations
import os, sys, json, math, datetime, argparse, statistics
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _idxkline as E
import _exit_sim as _EXITSIM        # 移动止盈单一口径（本文件不再自持实现）

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QUANT = os.path.join(ROOT, "quant")
CACHE = os.path.join(QUANT, "_txk_cache.json")
PANEL = os.path.join(QUANT, "_selected_lab_panel.json")
MODEL = os.path.join(QUANT, "_selected_model.json")
OUT = os.path.join(ROOT, "web", "selected", "lab.html")
# ★ 退出回测「成交假设」口径审计（_exit_assumption_audit.py 生成）。
#   本页所有「可兑现胜率」都是移动止盈退出口径 → 必须并列乐观/可实现两种口径，
#   否则就是把「好看但不成立」的数字当成绩展示。读不到则如实标注未核验。
EXIT_AUDIT = os.path.join(QUANT, "_exit_assumption_audit.json")
os.makedirs(os.path.dirname(OUT), exist_ok=True)


def audit_pair():
    """→ (old, real)：旧口径（乐观日内·忽略跳空）/ 可实现口径（保守日内·跳空成交）；缺则 None。"""
    try:
        d = json.load(open(EXIT_AUDIT, encoding="utf-8"))
        m = {x.get("mode"): x for x in d.get("modes", [])}
        return (m.get("旧口径（乐观日内·忽略跳空）"),
                m.get("可实现口径（保守日内·跳空成交）"))
    except Exception:
        return None, None

STEP = 5            # 采样步长（交易日）
MINI = 60           # 最少 K 线
FMAX = 20           # 前推窗口上限（持有期最大 20 日，与反转池一致）
AMT_MIN = 3.0e7     # 20 日均成交额下限（元）—— 可交易性下限，剔僵尸票
PRICE_MIN = 2.0     # 最低价（剔仙股/退市边缘）

# ---------------- 工具 ----------------
def _prefix(a):
    ps = [0.0] * (len(a) + 1)
    for i, x in enumerate(a):
        ps[i + 1] = ps[i] + (x or 0)
    return ps

def _rollma(ps, i, n):
    if i - n + 1 < 0:
        return None
    return (ps[i + 1] - ps[i - n + 1]) / n

def _bad_name(nm):
    return ("ST" in (nm or "")) or ("退" in (nm or ""))

# ---------------- 先验因子集（方向由经济逻辑给定，等权、不筛不调权） ----------------
# dir: +1 越大越好（趋势/资金越强）；-1 越小越好
PRIOR = {
    "rel20": 1,        # 近 20 日动量（趋势强度）
    "rel60": 1,        # 近 60 日动量（中期趋势）
    "above_ma60": 1,   # 站上长期均线（趋势确认，非下跌中继）
    "slope20": 1,      # MA20 斜率向上（短中期加速）
    "ma_strength": 1,  # 均线多头强度（MA5/MA60，多头排列）
    "dist_h20": 1,     # 接近近 20 日高（强势延续，非深跌反弹）
    "up_vol": 1,       # 上涨放量占比（资金进场代理）
    "rvol": 1,         # 量能放大（温和放量，量价齐升）
    "vol_dry": -1,     # 回调缩量（健康换手，越小越好）
}
PRIOR_CN = {
    "rel20": "近20日动量", "rel60": "近60日动量", "above_ma60": "站上MA60",
    "slope20": "MA20斜率", "ma_strength": "均线多头强度", "dist_h20": "接近近20日高",
    "up_vol": "上涨放量占比", "rvol": "量能放大", "vol_dry": "回调缩量",
}

# 退出规则（移动止盈，与反转池 lab/backtest 同口径）
STOP = 0.12         # 硬止损 -12%
ACT = 0.06          # 浮盈 +6% 激活移动止盈
TRAIL = 0.03        # 回撤 3% 跟踪
MAXFWD = FMAX       # 满 20 日强平


# ---------------- 面板 ----------------
def build_panel(step=STEP):
    """全市场可交易域面板：逐 (标的, 交易日) 算主升因子 + 前向标签。

    域 = `_txk_cache.json` 全部 A 股正股（排北交所/转债/ETF），剔除 ST/退、K线不足、
    20 日均额 < AMT_MIN、现价 < PRICE_MIN。不做趋势/深跌等前置剪枝（那是排序器的事）。
    """
    cache = json.load(open(CACHE, encoding="utf-8"))
    NM = {}
    try:
        NM = json.load(open(os.path.join(QUANT, "_stock_names.json"), encoding="utf-8"))
    except Exception:
        pass
    codes = [c for c in cache if (c.startswith("sh6") or c.startswith("sz0") or c.startswith("sz3"))
             and len(cache[c]) >= MINI + FMAX + 5]
    print("[lab] 日K缓存 %d 只，入面板候选 %d 只" % (len(cache), len(codes)))

    rows = []
    skipped = defaultdict(int)
    for ci, c in enumerate(codes):
        nm = NM.get(c) or ""
        if _bad_name(nm):
            skipped["bad"] += 1
            continue
        bars = cache[c]
        C = [b["last"] for b in bars]
        H = [b["high"] for b in bars]
        L = [b["low"] for b in bars]
        O = [b["open"] for b in bars]
        V = [b["volume"] for b in bars]
        psC = _prefix(C)
        n = len(bars)
        for i in range(MINI, n - FMAX - 1, step):
            close = C[i]
            if not close:
                continue
            # 流动性 / 价格门槛
            amt20 = (psC[i + 1] - psC[i + 1 - 20]) / 20 * 0   # 占位（成交额需单位校正，改用价量比因子）
            # 用收盘价 × 成交量 近似成交额（仅用于流动性门槛，单位一致比较）
            vu = 1.0 if c.startswith("sh688") else 100.0
            amt20_yi = sum(V[k] * vu * C[k] for k in range(i - 19, i + 1)) / 20 / 1e8
            if amt20_yi < AMT_MIN / 1e8:
                skipped["amt"] += 1
                continue
            if close < PRICE_MIN:
                skipped["price"] += 1
                continue
            ma5 = _rollma(psC, i, 5)
            ma10 = _rollma(psC, i, 10)
            ma20 = _rollma(psC, i, 20)
            ma60 = _rollma(psC, i, 60)
            if not (ma20 and ma60):
                continue
            rel20 = (C[i] / C[i - 20] - 1) if i >= 20 and C[i - 20] else 0.0
            rel60 = (C[i] / C[i - 60] - 1) if i >= 60 and C[i - 60] else 0.0
            above_ma60 = C[i] / ma60 - 1
            ma20p = _rollma(psC, i - 20, 20)
            slope20 = (ma20 / ma20p - 1) if ma20p else 0.0
            ma_strength = (ma5 / ma60 - 1) if ma5 else 0.0
            h20 = max(H[i - 19:i + 1]) if i >= 19 else H[i]
            dist_h20 = C[i] / h20 - 1 if h20 else 0.0
            # 量
            v60 = sum(V[i - 59:i + 1]) / 60 if i >= 60 else sum(V[i - 19:i + 1]) / 20
            up_vol = (sum(1 for k in range(i - 19, i + 1)
                          if C[k] > O[k] and V[k] > v60) / 20.0) if v60 else 0.0
            rvol = V[i] / v60 if v60 else 1.0
            vol_dry = (sum(V[k] for k in range(i - 19, i + 1)) / 20.0 / v60) if v60 else 1.0
            f = {
                "rel20": rel20, "rel60": rel60, "above_ma60": above_ma60,
                "slope20": slope20, "ma_strength": ma_strength, "dist_h20": dist_h20,
                "up_vol": up_vol, "rvol": rvol, "vol_dry": vol_dry,
            }
            # 前推
            fl = [L[i + 1 + k] for k in range(FMAX) if i + 1 + k < n]
            fh = [H[i + 1 + k] for k in range(FMAX) if i + 1 + k < n]
            fc = C[i + FMAX] if i + FMAX < n else None
            if len(fl) < FMAX or not fc:
                continue
            ret20 = fc / C[i] - 1
            ret10 = (C[i + 10] / C[i] - 1) if i + 10 < n else None
            ret5 = (C[i + 5] / C[i] - 1) if i + 5 < n else None
            mae = min(fl) / C[i] - 1
            mfe = max(fh) / C[i] - 1
            rows.append({
                "code": c, "date": bars[i]["date"], "f": f, "_close": C[i],
                "fl": fl, "fh": fh, "fc": fc,
                "ret5": ret5, "ret10": ret10, "ret20": ret20,
                "mae": mae, "mfe": mfe,
            })
    print("[lab] 面板 %d 行（剔 ST/退 %d · 流动性 %d · 低价 %d）" %
          (len(rows), skipped["bad"], skipped["amt"], skipped["price"]))
    return rows


# ---------------- 选股日因子计算（与 build_panel 同口径，单一来源） ----------------
def factors_at(C, H, L, O, V, psC, i, c):
    """在 kasc[:i+1] 处算主升先验因子（全为比率/价格比，规避成交量单位差）。

    供 build_selected.py 选股日调用：给定某票截至 date 的全量序列与前缀和，返回因子 dict。
    与 build_panel 内联逻辑完全一致（单一来源，避免口径分叉）。
    """
    close = C[i]
    ma5 = _rollma(psC, i, 5)
    ma10 = _rollma(psC, i, 10)
    ma20 = _rollma(psC, i, 20)
    ma60 = _rollma(psC, i, 60)
    if not (ma20 and ma60):
        return None
    rel20 = (C[i] / C[i - 20] - 1) if i >= 20 and C[i - 20] else 0.0
    rel60 = (C[i] / C[i - 60] - 1) if i >= 60 and C[i - 60] else 0.0
    above_ma60 = C[i] / ma60 - 1
    ma20p = _rollma(psC, i - 20, 20)
    slope20 = (ma20 / ma20p - 1) if ma20p else 0.0
    ma_strength = (ma5 / ma60 - 1) if ma5 else 0.0
    h20 = max(H[i - 19:i + 1]) if i >= 19 else H[i]
    dist_h20 = C[i] / h20 - 1 if h20 else 0.0
    v60 = sum(V[i - 59:i + 1]) / 60 if i >= 60 else sum(V[i - 19:i + 1]) / 20
    up_vol = (sum(1 for k in range(i - 19, i + 1)
                  if C[k] > O[k] and V[k] > v60) / 20.0) if v60 else 0.0
    rvol = V[i] / v60 if v60 else 1.0
    vol_dry = (sum(V[k] for k in range(i - 19, i + 1)) / 20.0 / v60) if v60 else 1.0
    return {"rel20": rel20, "rel60": rel60, "above_ma60": above_ma60,
            "slope20": slope20, "ma_strength": ma_strength, "dist_h20": dist_h20,
            "up_vol": up_vol, "rvol": rvol, "vol_dry": vol_dry}


def score_universe(rows, pct):
    """给候选集（已带 f 因子）做日内横截面分位打分，返回 (sorted_rows, n_top)。"""
    from collections import defaultdict as _dd
    byd = _dd(list)
    for r in rows:
        byd[r["date"]].append(r)
    out = []
    for d, rs in sorted(byd.items()):
        if len(rs) < 12:
            continue
        rk = {}
        for fac in PRIOR:
            vals = sorted([(r["f"].get(fac), r["code"]) for r in rs if r["f"].get(fac) is not None])
            if len(vals) < 6:
                continue
            for pos, (v, c) in enumerate(vals):
                rk.setdefault(c, {})[fac] = pos / (len(vals) - 1)
        scored = []
        for r in rs:
            tot = cnt = 0.0
            for fac in PRIOR:
                v = rk.get(r["code"], {}).get(fac)
                if v is None:
                    continue
                tot += (v if PRIOR[fac] > 0 else 1 - v)
                cnt += 1
            if cnt >= max(2, len(PRIOR) // 2):
                scored.append((tot / cnt, r))
        scored.sort(key=lambda x: -x[0])
        for sc, r in scored:
            r["qs"] = round(sc * 100, 1)
            out.append(r)
    return out


# ---------------- 退出模拟（移动止盈，与反转池同口径） ----------------
def _sim_trail(fl, fh, fc, px, stop=STOP, act=ACT, trail=TRAIL, maxfwd=MAXFWD,
               cons=False, fO=None):
    """信号日收盘 px 买入；未盈利前 -stop 硬止损；浮盈≥act 后止损上移为最高价×(1-trail)；
    满 maxfwd 强平。fl/fh/fc 为 T+1..T+FMAX 的 low/high/close。

    ★ 已收敛到 `_exit_sim.sim_trail_lists` 单一口径（默认 cons=False/fO=None = 旧口径，逐位一致）。
      新增 cons/fO 供「成交假设」审计调用；**不要在本文件里再写第二份实现**。
    """
    return _EXITSIM.sim_trail_lists(fl, fh, fc, px, stop, act, trail, maxfwd, cons, fO)


def _agg(rs):
    if not rs:
        return None
    n = len(rs)
    pnls = [x["pnl"] for x in rs]
    return (n, sum(1 for x in rs if x["win"]) / n * 100, sum(pnls) / n,
            sum(1 for x in rs if x["hit_tp"]) / n * 100,
            sum(1 for x in rs if x["hit_stop"]) / n * 100,
            min(x["mae"] for x in rs))


# ---------------- 成交假设口径开关（默认 = 旧口径，逐位不变） ----------------
# AUDIT_MODE = "legacy"    → 与历史完全一致（生产默认）
# AUDIT_MODE = "realistic" → 保守日内路径 + 跳空按开盘价成交（需先装 FO_IDX）
AUDIT_MODE = "legacy"
FO_IDX = None        # {(code, date): [open_{T+1}, ..., open_{T+hold}]}


def _sim_row(r):
    """按当前口径算一行的退出结果。legacy 走 `_sim_trail`（逐位复刻旧值）；
    realistic 走 `_exit_sim.sim_trail_lists(cons=True, fO=前向开盘序列)`。"""
    if AUDIT_MODE == "realistic":
        fo = FO_IDX.get((r["code"], r["date"])) if FO_IDX else None
        return _EXITSIM.sim_trail_lists(r["fl"], r["fh"], r["fc"], _px(r),
                                        cons=True, fO=fo)
    return _sim_trail(r["fl"], r["fh"], r["fc"], _px(r))


def build_fo_index(rows, hold=MAXFWD):
    """为 realistic 口径建前向开盘索引：{(code, date): [open_{T+1..T+hold}]}。

    只给面板里实际出现的 (code, date) 建，避免为全市场铺开占内存。
    读不到（停牌/缓存缺）→ 该行 fO=None，等价于「该日只修日内路径、不修跳空」。
    """
    need = defaultdict(set)
    for r in rows:
        need[r["code"]].add(r["date"])
    cache = json.load(open(CACHE, encoding="utf-8"))
    idx = {}
    miss = 0
    for code, ds in need.items():
        bars = cache.get(code)
        if not bars:
            miss += len(ds)
            continue
        d2i = {}
        for i, b in enumerate(bars):
            d2i[b["date"]] = i
        for d in ds:
            i = d2i.get(d)
            if i is None:
                miss += 1
                continue
            seq = []
            for j in range(1, hold + 1):
                if i + j < len(bars):
                    o = bars[i + j].get("open")
                    seq.append(o if o else None)
                else:
                    seq.append(None)
            idx[(code, d)] = seq
    print("[lab·fO] 索引 %d 条，缺失 %d 条（缺则只修日内路径）" % (len(idx), miss))
    return idx


# ---------------- 横截面分位打分 ----------------
def _as_dir(d):
    return {k: (1 if v > 0 else -1) for k, v in d.items()}

def _rank_top(sample, use, dirs, pct=0.10, stop=STOP, act=ACT, trail=TRAIL):
    """日内横截面分位排序 → 每日前 pct 组成组合，与全体对照（主升口径：移动止盈）。"""
    dirs = _as_dir(dirs)
    byd = defaultdict(list)
    for r in sample:
        byd[r["date"]].append(r)
    top, allc = [], []
    for d, rs in sorted(byd.items()):
        if len(rs) < 12:
            continue
        rk = {}
        for fac in use:
            vals = sorted([(r["f"].get(fac), r["code"]) for r in rs if r["f"].get(fac) is not None])
            if len(vals) < 6:
                continue
            for pos, (v, c) in enumerate(vals):
                rk.setdefault(c, {})[fac] = pos / (len(vals) - 1)
        scored = []
        for r in rs:
            tot = cnt = 0.0
            for fac in use:
                v = rk.get(r["code"], {}).get(fac)
                if v is None:
                    continue
                tot += (v if dirs[fac] > 0 else 1 - v)
                cnt += 1
            if cnt >= max(2, len(use) // 2):
                scored.append((tot / cnt, r))
        if len(scored) < 12:
            continue
        scored.sort(key=lambda x: -x[0])
        k = max(1, int(round(len(scored) * pct)))
        top += [r for _, r in scored[:k]]
        allc += [r for _, r in scored]
    if len(top) < 40:
        return None
    a = _agg([_sim_row(r) for r in top])
    b = _agg([_sim_row(r) for r in allc])
    return {"n_top": len(top), "n_all": len(allc),
            "wr_top": a[1], "wr_all": b[1], "edge_wr": a[1] - b[1],
            "ret_top": a[2], "ret_all": b[2], "edge_ret": a[2] - b[2],
            "mae_top": a[5], "mae_all": b[5], "tp_top": a[3], "stop_top": a[4]}


def _px(r):
    """信号日入场价 = T 日 close（用 ret20 反推需 fc，这里直接存原 close 不便；
    用 fc/(1+ret20) 还原 T 日 close）。"""
    if r.get("_close"):
        return r["_close"]
    return r["fc"] / (1 + r["ret20"]) if (r.get("ret20") is not None and r["fc"]) else r["fc"]


# ---------------- 基线与相对胜率 ----------------
def rel_median(rows):
    """按 date 算域内 ret20 中位数，给每行加 beat20（相对胜率标签）。"""
    byd = defaultdict(list)
    for r in rows:
        byd[r["date"]].append(r)
    for d, rs in byd.items():
        med = statistics.median([x["ret20"] for x in rs if x.get("ret20") is not None])
        for r in rs:
            r["beat20"] = (r["ret20"] > med) if r.get("ret20") is not None else None


def base_rate(rows, stop=STOP, act=ACT, trail=TRAIL):
    """基线：全样本套同一移动止盈规则的可兑现胜率（= 随机持有对照）。"""
    return _agg([_sim_trail(r["fl"], r["fh"], r["fc"], _px(r)) for r in rows])


# ---------------- 单特征功效 ----------------
def feature_table(rows, cut, min_n=300):
    """连续特征按训练段分位切 5 桶，报训练/测试相对胜率单调。"""
    tr = [r for r in rows if r["date"] < cut]
    te = [r for r in rows if r["date"] >= cut]
    out = []
    for fac, d in PRIOR.items():
        trv = [r["f"][fac] for r in tr if r["f"].get(fac) is not None]
        if len(trv) < min_n:
            continue
        qs = statistics.quantiles(trv, n=4)
        def bucket(sample, q):
            bs = [[] for _ in range(5)]
            for r in sample:
                v = r["f"].get(fac)
                if v is None:
                    continue
                idx = 0
                for kk in range(4):
                    if v <= q[kk]:
                        idx = kk
                        break
                else:
                    idx = 4
                bs[idx].append(r["beat20"])
            return [statistics.mean(x) * 100 if x else None for x in bs]
        bt = bucket(tr, qs)
        be = bucket(te, qs)
        out.append((fac, bt, be))
    return out


# ---------------- 严格样本外（先验 vs 自动筛） ----------------
def strict_oos(rows, pct=0.10):
    """先验固定集 vs 自动筛（训练段学方向 → 测试段用）vs 全量前视。"""
    cut = sorted(set(r["date"] for r in rows))[len(set(r["date"] for r in rows)) // 2]
    tr = [r for r in rows if r["date"] < cut]
    te = [r for r in rows if r["date"] >= cut]
    # 先验集（方向固定）
    prior = _rank_top(te, list(PRIOR.keys()), PRIOR, pct)
    # 自动筛：训练段按极差挑因子并定方向
    learn = {}
    for fac, d in PRIOR.items():
        trv = [r["f"][fac] for r in tr if r["f"].get(fac) is not None]
        if len(trv) < 300:
            continue
        qs = statistics.quantiles(trv, n=2)
        top = [r["beat20"] for r in tr if r["f"].get(fac) is not None and r["f"][fac] >= qs[0]]
        bot = [r["beat20"] for r in tr if r["f"].get(fac) is not None and r["f"][fac] < qs[0]]
        if top and bot:
            edge = statistics.mean(top) - statistics.mean(bot)
            if abs(edge) >= 0.02:
                learn[fac] = 1 if edge > 0 else -1
    auto = None
    if len(learn) >= 3:
        auto = _rank_top(te, list(learn.keys()), learn, pct)
    return {"cut": cut, "prior": prior, "auto": auto, "auto_feats": learn}


# ---------------- 训练半 vs 测试半（最重要的表） ----------------
def half_oos(rows, pct=0.10):
    dates = sorted(set(r["date"] for r in rows))
    cut = dates[len(dates) // 2]
    tr = [r for r in rows if r["date"] < cut]
    te = [r for r in rows if r["date"] >= cut]
    a = _rank_top(tr, list(PRIOR.keys()), PRIOR, pct)
    b = _rank_top(te, list(PRIOR.keys()), PRIOR, pct)
    return {"cut": cut, "train": a, "test": b}


# ---------------- 截断比例曲线（找 >60% 的 pct，含训练/测试半） ----------------
def topn_curve(rows, pcts=(0.01, 0.02, 0.03, 0.05, 0.10, 0.20, 0.30)):
    dates = sorted(set(r["date"] for r in rows))
    cut = dates[len(dates) // 2]
    tr = [r for r in rows if r["date"] < cut]
    te = [r for r in rows if r["date"] >= cut]
    out = []
    for p in pcts:
        rf = _rank_top(rows, list(PRIOR.keys()), PRIOR, p)
        rt = _rank_top(tr, list(PRIOR.keys()), PRIOR, p)
        re = _rank_top(te, list(PRIOR.keys()), PRIOR, p)
        if rf:
            out.append((p, rf, rt, re))
    return out


# ---------------- 逐月 walk-forward ----------------
def monthly(rows, pct=0.10):
    ds = sorted(set(r["date"] for r in rows))
    out = []
    for m in range(0, len(ds), max(1, len(ds) // 8)):
        sub = [r for r in rows if r["date"] <= ds[m]]
        if len(sub) < 200:
            continue
        r = _rank_top(sub, list(PRIOR.keys()), PRIOR, pct)
        if r:
            out.append((ds[m], r["wr_top"], r["ret_top"], r["n_top"]))
    return out


# ---------------- 环境门控 ----------------
def regime_gate(rows, pct=0.10):
    """按日级广度（站上 MA60 占比）分桶，看各桶 edge。结论通常是两半反向 → 只控 β。"""
    byd = defaultdict(list)
    for r in rows:
        byd[r["date"]].append(r)
    buckets = defaultdict(list)
    for d, rs in byd.items():
        above = sum(1 for r in rs if r["f"]["above_ma60"] > 0.0)
        br = above / len(rs) * 100 if rs else 50
        key = "防守(<35)" if br < 35 else ("中性(35~55)" if br < 55 else "进攻(>=55)")
        buckets[key].append(r)
    out = {}
    for k, rs in buckets.items():
        r = _rank_top(rs, list(PRIOR.keys()), PRIOR, pct)
        if r:
            out[k] = r
    return out


# ---------------- 退出规则网格 ----------------
def exit_lab(rows, pct=0.10):
    """移动止盈网格：不同 激活点/回撤 下的 A 档可兑现胜率与均收益。"""
    tops = _tops(rows, pct)
    if not tops:
        return []
    grid = []
    for act in (0.04, 0.06, 0.08):
        for trail in (0.02, 0.03):
            rs = [_sim_trail(r["fl"], r["fh"], r["fc"], _px(r), STOP, act, trail) for r in tops]
            a = _agg(rs)
            grid.append((act, trail, a[1], a[2], a[3], a[4], a[5]))
    return grid


def _tops(rows, pct):
    """取全样本每日前 pct 的并集（用于退出网格单独跑模拟）。"""
    byd = defaultdict(list)
    for r in rows:
        byd[r["date"]].append(r)
    tops = []
    for d, rs in sorted(byd.items()):
        if len(rs) < 12:
            continue
        rk = {}
        for fac in PRIOR:
            vals = sorted([(r["f"].get(fac), r["code"]) for r in rs if r["f"].get(fac) is not None])
            if len(vals) < 6:
                continue
            for pos, (v, c) in enumerate(vals):
                rk.setdefault(c, {})[fac] = pos / (len(vals) - 1)
        scored = []
        for r in rs:
            tot = cnt = 0.0
            for fac in PRIOR:
                v = rk.get(r["code"], {}).get(fac)
                if v is None:
                    continue
                tot += (v if PRIOR[fac] > 0 else 1 - v)
                cnt += 1
            if cnt >= max(2, len(PRIOR) // 2):
                scored.append((tot / cnt, r))
        if len(scored) < 12:
            continue
        scored.sort(key=lambda x: -x[0])
        k = max(1, int(round(len(scored) * pct)))
        tops += [r for _, r in scored[:k]]
    return tops


# ---------------- 主流程 ----------------
def main(rebuild=False, mode="legacy", no_html=False):
    """mode: legacy（生产默认，逐位复刻旧值） / realistic（保守日内 + 跳空按开盘成交）。

    realistic 只做审计：结论落 `_selected_model_realistic.json`，**不覆盖生产模型**，
    且默认不渲染 lab.html（避免用非生产口径改写生产页）。
    """
    global AUDIT_MODE, FO_IDX
    AUDIT_MODE = mode
    if mode == "realistic":
        no_html = True
    print("[lab] 成交假设口径 = %s" % ("可实现（保守日内 + 跳空按开盘成交）" if mode == "realistic"
                                   else "旧乐观（同根K先冲高后回落 + 忽略跳空）"))
    if rebuild or not os.path.exists(PANEL):
        rows = build_panel()
        json.dump(rows, open(PANEL, "w", encoding="utf-8"))
        print("[lab] 面板落盘 %s" % PANEL)
    else:
        rows = json.load(open(PANEL, encoding="utf-8"))
        print("[lab] 复用面板 %d 行" % len(rows))
    if mode == "realistic":
        FO_IDX = build_fo_index(rows)
    rel_median(rows)

    dates = sorted(set(r["date"] for r in rows))
    cut = dates[len(dates) // 2]
    print("[lab] 样本区间 %s ~ %s（%d 交易日，cut=%s）" % (dates[0], dates[-1], len(dates), cut))

    base = base_rate(rows)
    print("\n=== 基线（全样本随机持有，移动止盈口径）===")
    print("可兑现胜率 %.1f%% ｜ 均收益 %+.2f%% ｜ 最坏MAE %.1f%%" % (base[1], base[2], base[5]))

    print("\n=== 截断比例曲线（先验集 · 全/训练半/测试半）===")
    curve = topn_curve(rows)
    for p, rf, rt, re in curve:
        print("前 %.0f%%：全 %.1f%% / 训练半 %.1f%% / 测试半 %.1f%%（edge %+.1fpp）｜ 均收益 %+.2f%% ｜ n=%d"
              % (p * 100, rf["wr_top"], rt["wr_top"], re["wr_top"], rf["edge_wr"], rf["ret_top"], rf["n_top"]))

    print("\n=== 严格样本外（先验 vs 自动筛）===")
    so = strict_oos(rows)
    if so["prior"]:
        print("先验集(测试半)：胜率 %.1f%% ｜ edge %+.1fpp ｜ 均收益 %+.2f%%"
              % (so["prior"]["wr_top"], so["prior"]["edge_wr"], so["prior"]["ret_top"]))
    if so["auto"]:
        print("自动筛(测试半)：胜率 %.1f%% ｜ edge %+.1fpp ｜ 均收益 %+.2f%%"
              % (so["auto"]["wr_top"], so["auto"]["edge_wr"], so["auto"]["ret_top"]))
        print("自动筛选中因子：%s" % so["auto_feats"])

    print("\n=== 训练半 vs 测试半（最重要）===")
    ho = half_oos(rows)
    if ho["train"] and ho["test"]:
        print("训练半：胜率 %.1f%% ｜ 均收益 %+.2f%%" % (ho["train"]["wr_top"], ho["train"]["ret_top"]))
        print("测试半：胜率 %.1f%% ｜ 均收益 %+.2f%%" % (ho["test"]["wr_top"], ho["test"]["ret_top"]))

    print("\n=== 退出规则网格（A 档前10%）===")
    grid = exit_lab(rows)
    for act, trail, wr, ret, tp, st, mae in grid:
        print("激活+%.0f%%/回撤%.0f%%：胜率 %.1f%% ｜ 均收益 %+.2f%% ｜ 触止盈 %.1f%%/触止损 %.1f%%"
              % (act * 100, trail * 100, wr, ret, tp, st))

    # 环境门控
    rg = regime_gate(rows)
    print("\n=== 环境门控（按广度分桶）===")
    for k, r in rg.items():
        print("%s：胜率 %.1f%% ｜ edge %+.1fpp" % (k, r["wr_top"], r["edge_wr"]))

    # 冻结模型：A 档 = 更严格（前 5%），且严格样本外(测试半)胜率稳定 ≥60% 的最严截断。
    # ★ 判据必须显式记录「通过 / 未通过」——旧代码在无人满足时静默兜底 0.05，
    #   等于把「没有证据」伪装成「证据支持前 5%」，属 fail-open，禁止。
    cand = [(p, rf, rt, re) for p, rf, rt, re in curve
            if re and re["wr_top"] >= 60.0 and re["edge_wr"] >= 0 and p >= 0.05]
    if cand:
        best_pct = cand[0][0]
        pct_gate = ("pass", "判据通过：满足「测试半胜率 ≥60%% 且 edge≥0」的最严截断 = 前 %.0f%%"
                    % (best_pct * 100))
    else:
        best_pct = 0.05
        worst = min((re["wr_top"] for _p, _rf, _rt, re in curve
                     if re and _p >= 0.05), default=None)
        pct_gate = ("fail",
                    "★ 判据未通过（%s 口径）：<b>没有任何</b>截断比例同时满足「测试半胜率 ≥60%% 且 edge≥0」"
                    "（前 5%% 及以上的最高测试半胜率 = %s）→ 此处仍写 0.05 仅为保持生产脚本可读，"
                    "<b>不得据此认定 A 档选股存在正 edge</b>"
                    % (AUDIT_MODE, ("%.1f%%" % worst) if worst is not None else "无样本"))
    print("\n[lab·判据] %s" % pct_gate[1].replace("<b>", "").replace("</b>", ""))
    model = {
        "version": "selected_v1",
        "built_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "domain": "全市场 A 股正股（剔 ST/退 + 20日均额≥3000万 + 现价≥2元）",
        "factors": {k: PRIOR[k] for k in PRIOR},
        "factor_cn": PRIOR_CN,
        "pct": best_pct,
        "exit": {"stop": STOP, "act": ACT, "trail": TRAIL, "maxfwd": MAXFWD},
        "panel_min": dates[0], "panel_max": dates[-1],
        "n_rows": len(rows),
        "evidence": {
            "base_wr": base[1], "base_ret": base[2],
            "prior_test_wr": so["prior"]["wr_top"] if so["prior"] else None,
            "train_wr": ho["train"]["wr_top"] if ho["train"] else None,
            "test_wr": ho["test"]["wr_top"] if ho["test"] else None,
        "curve": [{"pct": p, "n": rf["n_top"], "wr": rf["wr_top"], "edge": rf["edge_wr"],
                   "ret": rf["ret_top"]} for p, rf, rt, re in curve],
        "pct_gate": {"verdict": pct_gate[0], "note": pct_gate[1],
                     "test_wr_by_pct": {str(p): (re["wr_top"] if re else None)
                                        for p, rf, rt, re in curve}},
    },
    "audit_mode": AUDIT_MODE,
    }
    out_model = os.path.join(QUANT, "_selected_model_realistic.json") if mode == "realistic" else MODEL
    json.dump(model, open(out_model, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n[lab] 冻结模型 %s（A 档 = 域内前 %.0f%%）" % (out_model, best_pct * 100))

    if no_html:
        print("[lab] --no-html：跳过页面渲染（lab.html 保持生产口径）")
        return model
    render_lab(rows, model, base, curve, so, ho, grid, rg)
    return model


# ---------------- 渲染 ----------------
STYLE = """
:root{--bg:#fbfbfd;--card:#fff;--text:#1d1d1f;--muted:#6e6e73;--line:#e5e5e7;
 --up:#ff3b30;--dn:#34c759;--blue:#0071e3;--gold:#b8893b;--orange:#ff9500;--purple:#af52de;}
*{box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"PingFang SC","Microsoft YaHei",sans-serif;
 background:var(--bg);color:var(--text);line-height:1.7;margin:0;padding:0}
.wrap{max-width:1040px;margin:0 auto;padding:28px 18px 56px}
h1{font-size:23px;font-weight:700;margin:0 0 6px;letter-spacing:-.02em}
h2{font-size:18px;font-weight:600;margin:26px 0 12px;padding-bottom:8px;border-bottom:2px solid var(--blue)}
.sub{color:var(--muted);font-size:13px;margin-bottom:8px}
.card{background:var(--card);border-radius:16px;padding:16px 20px;margin:12px 0;box-shadow:0 1px 3px rgba(0,0,0,.05)}
.box{border-left:4px solid var(--blue);background:#f0f7ff;padding:14px 18px;border-radius:0 12px 12px 0;margin:14px 0}
.box.gold{border-color:var(--gold);background:#fffaf0}
.box.green{border-color:var(--dn);background:#f0faf3}
.box.red{border-color:var(--up);background:#fff5f4}
table{width:100%;border-collapse:collapse;font-size:12.5px;margin:10px 0}
th,td{padding:8px 6px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
th{color:var(--muted);font-weight:600;font-size:11.5px;background:#fafafa}
.num{font-variant-numeric:tabular-nums}
.up{color:var(--up)}.dn{color:var(--dn)}.am{color:var(--blue)}
.foot{text-align:center;color:var(--muted);font-size:12px;margin-top:28px}
"""


def _load_realistic():
    """读可实现口径审计产物。读不到 → None（调用方必须明写「未核验」，禁止静默沿用旧口径）。"""
    p = os.path.join(QUANT, "_selected_model_realistic.json")
    if not os.path.exists(p):
        return None
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return None


def _load_env_realistic():
    """读环境门控的可实现口径结论（强势档 edge）。读不到 → None，明写未核验。"""
    p = os.path.join(QUANT, "_env_gate_lab_realistic.json")
    if not os.path.exists(p):
        return None
    try:
        r = json.load(open(p, encoding="utf-8"))
    except Exception:
        return None
    return (r.get("edge_out") or {}).get("强势")


def render_lab(rows, model, base, curve, so, ho, grid, rg):
    ds = (model.get("panel_min"), model.get("panel_max"))
    ev = model.get("evidence", {})
    # 可实现口径对照（_selected_lab.py --mode realistic 的产物；本页主体仍是生产口径）
    _rz = _load_realistic()
    _rzc = {}
    _rzt = {}
    if _rz:
        for c in (_rz.get("evidence") or {}).get("curve", []):
            _rzc[round(float(c["pct"]), 4)] = c
        for k, v in ((_rz.get("evidence") or {}).get("pct_gate", {})
                     or {}).get("test_wr_by_pct", {}).items():
            _rzt[round(float(k), 4)] = v
    curve_rows = "".join(
        "<tr><td>前 %.0f%%</td><td class='num'>%d</td>"
        "<td class='num %s'>%.1f%%</td><td class='num'>%.1f%%</td><td class='num'>%.1f%%</td>"
        "<td class='num %s'>%+.1fpp</td><td class='num %s'>%+.2f%%</td>"
        "<td class='num %s'>%s</td><td class='num %s'>%s</td></tr>" %
        (p * 100, rf["n_top"],
         "up" if rf["wr_top"] >= 60 else ("dn" if rf["wr_top"] < 50 else ""),
         rf["wr_top"], rt["wr_top"], re["wr_top"],
         "up" if rf["edge_wr"] >= 0 else "dn", rf["edge_wr"],
         "up" if rf["ret_top"] >= 0 else "dn", rf["ret_top"],
         "up" if (_rzc.get(round(p, 4), {}).get("wr", 0) or 0) >= 60 else "dn",
         ("%.1f%%" % _rzc[round(p, 4)]["wr"]) if round(p, 4) in _rzc else "—",
         "up" if (_rzc.get(round(p, 4), {}).get("edge", 0) or 0) >= 0 else "dn",
         ("%+.2fpp" % _rzc[round(p, 4)]["edge"]) if round(p, 4) in _rzc else "—")
        for p, rf, rt, re in curve)
    if _rz:
        curve_head = ("<th>截断</th><th>样本</th><th>全样本胜率</th><th>训练半</th><th>测试半</th>"
                      "<th>vs 全体 edge</th><th>均收益</th>"
                      "<th>可实现胜率</th><th>可实现 edge</th>")
        _rz_pct = _rz.get("pct")
        _env = _load_env_realistic()
        _env_txt = ("%+.3fpp" % _env["edge"]) if _env else "（未核验）"
        curve_note = (
            "右两列为<b>可实现口径</b>（保守日内路径 + 跳空按开盘成交）下的同一批票：<br>"
            "① 可实现口径下 edge 随截断<b>单调上升</b>（前 1%% %+.2fpp → 前 5%% %+.2fpp → 前 20%% %+.2fpp），"
            "即<b>越精选越差</b>；② 现行判据「测试半胜率 ≥60%% 且 edge≥0」在可实现口径下指向<b>前 %.0f%%</b>，"
            "但该判据是<b>绝对胜率门槛</b>，pct 越宽组合越接近域内平均（基线 %.1f%%），"
            "所以「满足 60%%」主要是<b>稀释效应</b>，不构成选股 alpha 的证据。<br>"
            "<b>处置：生产 A 档维持前 5%% 不变</b>。理由：① 用换口径的涨跌去调 pct 属拟合噪声；"
            "② 环境门控证据（强势档可实现 edge %s）是按<b>前 5%%</b> 口径算出的，改 pct 会让该证据失去对应；"
            "③ 前 20%% 的 edge 提升不可解释为选股能力（它与「前 1%% 为负」自相矛盾）。<br>"
            "⚠ 因此本页表格里「前 5%%」的<b>可实现 edge = %+.2fpp（不显著为正）</b>，"
            "选股部分<b>不提供独立 alpha</b>——主升精选的依据是<b>环境门控</b>，不是选股。"
            % (_rzc.get(0.01, {}).get("edge", float("nan")),
               _rzc.get(0.05, {}).get("edge", float("nan")),
               _rzc.get(0.20, {}).get("edge", float("nan")),
               (_rz_pct or 0) * 100, base[1], _env_txt,
               _rzc.get(0.05, {}).get("edge", float("nan"))))
    else:
        curve_head = ("<th>截断</th><th>样本</th><th>全样本胜率</th><th>训练半</th><th>测试半</th>"
                      "<th>vs 全体 edge</th><th>均收益</th>"
                      "<th>可实现胜率</th><th>可实现 edge</th>")
        curve_note = (
            "<div class='red'>★ 可实现口径<b>未核验</b>：未找到 <code>quant/_selected_model_realistic.json</code>"
            "（跑 <code>python quant/_selected_lab.py --mode realistic</code> 生成）。"
            "右两列显示「—」，<b>不代表可实现口径与左列相同</b>，只表示没有证据。</div>")
    # 核心结论框：选股是否有独立 alpha，必须以可实现口径为准（三态，不可静默）
    _e5 = _rzc.get(0.05, {}).get("edge") if _rz else None
    _t5 = _rzt.get(0.05) if _rz else None
    if _rz and _e5 is not None:
        sel_alpha_line = (
            "⚠ 但按<b>可实现口径</b>复核：A 档（前 5%%）可实现 edge = <b>%+.2fpp</b>、测试半胜率 <b>%.1f%%</b>"
            "（未达 60%% 门槛）→ <b>选股不提供独立 alpha</b>。"
            "主升精选的成立依据是<b>环境门控（强势开仓）</b>，不是选股本身。"
            % (_e5, _t5 if _t5 is not None else float("nan")))
    else:
        sel_alpha_line = (
            "⚠ 可实现口径<b>未核验</b>（缺 <code>_selected_model_realistic.json</code>）→ "
            "选股是否提供独立 alpha <b>不可判</b>，不得引用本页胜率作为选股能力的证据。")
    so_rows = ""
    if so.get("prior"):
        so_rows += ("<tr><td>先验固定集</td><td class='num'>%d</td>"
                    "<td class='num'>%.1f%%</td><td class='num'>%+.1fpp</td><td class='num'>%+.2f%%</td></tr>" %
                    (so["prior"]["n_top"], so["prior"]["wr_top"], so["prior"]["edge_wr"], so["prior"]["ret_top"]))
    if so.get("auto"):
        so_rows += ("<tr><td>自动筛因子</td><td class='num'>%d</td>"
                    "<td class='num'>%.1f%%</td><td class='num'>%+.1fpp</td><td class='num'>%+.2f%%</td></tr>" %
                    (so["auto"]["n_top"], so["auto"]["wr_top"], so["auto"]["edge_wr"], so["auto"]["ret_top"]))
    ho_rows = ""
    if ho.get("train") and ho.get("test"):
        ho_rows = ("<tr><td>训练半</td><td class='num'>%d</td><td class='num'>%.1f%%</td>"
                   "<td class='num'>%+.2f%%</td></tr><tr><td>测试半</td><td class='num'>%d</td>"
                   "<td class='num'>%.1f%%</td><td class='num'>%+.2f%%</td></tr>" %
                   (ho["train"]["n_top"], ho["train"]["wr_top"], ho["train"]["ret_top"],
                    ho["test"]["n_top"], ho["test"]["wr_top"], ho["test"]["ret_top"]))
    grid_rows = "".join(
        "<tr><td>激活 +%.0f%% / 回撤 %.0f%%</td><td class='num'>%.1f%%</td>"
        "<td class='num'>%+.2f%%</td><td class='num'>%.1f%%</td><td class='num'>%.1f%%</td>"
        "<td class='num dn'>%.1f%%</td></tr>" %
        (act * 100, trail * 100, wr, ret, tp, st, mae)
        for act, trail, wr, ret, tp, st, mae in grid)
    rg_rows = "".join("<tr><td>%s</td><td class='num'>%.1f%%</td><td class='num'>%+.1fpp</td></tr>"
                      % (k, r["wr_top"], r["edge_wr"]) for k, r in rg.items())
    pct = model.get("pct", 0.10)
    # ★ 成交假设口径对照（读 _exit_assumption_audit.json；读不到则如实标注未核验）
    _old, _real = audit_pair()
    if _old and _real:
        audit_line = (f"同一批样本、同一组参数，改按<b>可实现口径</b>"
                      f"（保守日内 + 跳空以开盘价成交）重算，A 档胜率为 <b>{_real['top_wr']:.1f}%</b>"
                      f"（测试半 {_real['test_wr']:.1f}%）。")
        audit_box = (
            f"<div class='box red' style='border-color:#b00020'>"
            f"<b>⚠️ 成交假设口径审计（本页所有胜率的解释前提）：</b><br>"
            f"本页数字用的是<b>乐观口径</b>：同根 K 线视作「先冲高、后回落」（止盈线当日即被抬高并可能触发），"
            f"且<b>忽略跳空</b>（开盘已跌破止盈线时仍按止盈线价成交）。<br>"
            f"同一批样本（{model.get('n_rows')} 行）、同一组参数，改按<b>可实现口径</b>"
            f"（先用截至昨日的止盈线判断当日是否跌破 + 跳空以开盘价成交）重算："
            f"A 档可兑现胜率 <b>{_old['top_wr']:.1f}% → {_real['top_wr']:.1f}%</b>，"
            f"测试半 <b>{_old['test_wr']:.1f}% → {_real['test_wr']:.1f}%</b>"
            f"（<b>低于本页自设的 60% 门槛</b>）；单笔净均值 "
            f"<b>{_old['top_net']:+.3f}% → {_real['top_net']:+.3f}%</b>。<br>"
            f"旧口径在全样本上被<b>精确复现</b>（62.7%，与冻结模型记录一致），"
            f"证明差异<b>只来自成交假设</b>，不是换了一批样本。<b>跳空修正是单向的（只会更差），必须补。</b><br>"
            f"完整四假设对照与机制说明见 "
            f"<a href='../docs/exit_assumption_evidence.html' style='color:var(--blue)'>"
            f"退出回测口径审计证据页</a>。</div>")
    else:
        audit_line = "⚠ <b>本页尚未做成交假设核验</b>（缺 <code>_exit_assumption_audit.json</code>）。"
        audit_box = ("<div class='box red' style='border-color:#b00020'><b>⚠️ 成交假设未核验：</b>"
                     "未找到 <code>quant/_exit_assumption_audit.json</code>"
                     "（运行 <code>python quant/_exit_assumption_audit.py</code> 生成）。"
                     "在完成核验前，本页全部胜率应视为<b>乐观口径、未证实</b>。</div>")
    html = f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>主升精选 · 因子样本外功效实验室 · {ds[0]}~{ds[1]}</title><style>{STYLE}</style></head>
<body><div class="wrap">
<h1>主升精选 · 因子样本外功效实验室</h1>
<div class="sub">样本区间 {ds[0]} ~ {ds[1]}（{model.get('n_rows')} 行 · 面板由 _txk_cache.json 全市场日K 实时算）｜ 版本 {model.get('version')}</div>

<div class="box gold"><b>核心结论（v1 · 全市场域）：</b>先验固定因子集（趋势+资金双确认，9 因子等权横截面分位）
A 档（域内前 <b>{pct*100:.0f}%</b>）严格样本外可兑现胜率
<b>{ev.get('test_wr') if ev.get('test_wr') is not None else '—'}</b>（基线 {ev.get('base_wr'):.1f}%），
训练半 {ev.get('train_wr') if ev.get('train_wr') is not None else '—'} / 测试半 {ev.get('test_wr') if ev.get('test_wr') is not None else '—'}。<br>
{sel_alpha_line}</div>

<div class="box red"><b>⚠️ 口径先说清（与 web/reversal 完全可比）：</b>胜率 = 信号日收盘买入 → 移动止盈
（−12% 硬止损 / 浮盈 +6% 激活 / 回撤 3% / 满 20 日强平）退出规则下<b>盈利交易占比</b>。
绝对胜率 = alpha + beta（普涨里随便买都赢）；本页同时报<b>相对胜率</b>（beat20 = 个股 20 日收益 &gt; 同日域内中位数）作 alpha 证据。<br>
★ <b>成交假设必须先声明</b>：本页数字默认<b>乐观口径</b>（同根 K 线「先冲高、后回落」+ 忽略跳空）。{audit_line}</div>

{audit_box}

<h2>一、截断比例曲线（先验集 · 全样本）</h2>
<div class="card"><table>
<thead><tr>{curve_head}</tr></thead>
<tbody>{curve_rows}</tbody></table>
<div class="note">{curve_note}</div></div>

<h2>二、严格样本外（先验 vs 自动筛）</h2>
<div class="card"><table>
<thead><tr><th>方法</th><th>样本</th><th>测试半胜率</th><th>edge</th><th>均收益</th></tr></thead>
<tbody>{so_rows}</tbody></table>
<div class="note">「自动筛因子」= 训练段按极差挑方向、测试段用；若其 edge 接近先验集，说明筛因子动作不产生 alpha（过拟合量）。</div></div>

<h2>三、训练半 vs 测试半（最重要：优势是否依赖期间）</h2>
<div class="card"><table>
<thead><tr><th>半区</th><th>样本</th><th>可兑现胜率</th><th>均收益</th></tr></thead>
<tbody>{ho_rows}</tbody></table></div>

<h2>四、退出规则网格（A 档前10% · 移动止盈）</h2>
<div class="card"><table>
<thead><tr><th>规则</th><th>胜率</th><th>均收益</th><th>触止盈率</th><th>触止损率</th><th>最坏MAE</th></tr></thead>
<tbody>{grid_rows}</tbody></table>
<div class="note">胜率与单笔均收益是一对权衡：激活点越低（越早锁利）胜率越高、单笔越薄。主口径取 激活+6%/回撤3%。</div></div>

<h2>五、环境门控（按广度分桶 · 仅控 β）</h2>
<div class="card"><table>
<thead><tr><th>环境</th><th>胜率</th><th>edge</th></tr></thead>
<tbody>{rg_rows}</tbody></table>
<div class="note">若各桶 edge 在训练半/测试半方向不一致，则环境门控<b>只给仓位系数</b>、不预判 alpha。</div></div>

<h2>六、因子集（方向由经济逻辑给定，等权、不筛不调权）</h2>
<div class="card"><div class="kv">
{("、".join("%s(%s)" % (PRIOR_CN[k], "↑越大越好" if PRIOR[k] > 0 else "↓越小越好") for k in PRIOR))}
<br>全部为比率/价格比因子（rel20/above_ma60/up_vol 等），规避跨板块成交量单位差
（科创板按股、其余按手，差 100 倍）。</div></div>

<h2>七、局限</h2>
<div class="card"><div class="kv">
① 前向 20 日窗口重叠 → 样本非独立；② 样本约 10 个月，换年份是否成立无法验证；
③ 主力资金用「上涨放量占比」价量代理（离线源只给最新日真实主力净流入，历史序列不可得）；
选股日叠加真实主力净流入（新浪/mcp）作加分；④ 绝对胜率含 beta，结论以相对口径为主。</div></div>

<div class="foot">本页为基于离线日K的量化筛选与方法论，非个股推荐、非买卖建议。决策责任在账户本人。</div>
</div></body></html>"""
    open(OUT, "w", encoding="utf-8").write(html)
    print("[lab] 写 %s" % OUT)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--rebuild", action="store_true", help="重建面板（默认复用）")
    ap.add_argument("--mode", choices=("legacy", "realistic"), default="legacy",
                    help="成交假设口径：legacy=生产默认；realistic=审计用（不覆盖生产模型与页面）")
    ap.add_argument("--no-html", action="store_true", help="跳过页面渲染")
    _ns = ap.parse_args()
    main(rebuild=_ns.rebuild, mode=_ns.mode, no_html=_ns.no_html)
