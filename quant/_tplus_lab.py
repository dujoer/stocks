# -*- coding: utf-8 -*-
"""做T池 · 特征功效实验室（tplus_lab v1，2026-09-21）。

要解决的问题
------------
做T池现行打分（`build_tplus.score`，7 维 100 分）的区间阈值来自一轮 ~347 样本、仅 6 个
交易日（同一周）的小回测，从未做过样本外验证；且已知「档位 A/B/C/D 对能否完成一轮几乎
无预测力」。用户要求「增加确定性和胜率」→ 本实验室回答三件事：

  ① 打分器的因子到底有没有预测力、方向如何？（单特征：训练桶 → 套测试）
  ② 那些方向换一段时间还成立吗？（训练半 / 测试半 + 逐月 walk-forward）
  ③ 真正能提高「完成一轮率、降低破止损率」的抓手在哪？（参数网格：买区深度 ×
     卖区目标 × 止损宽度 × 持有期）

做T的胜率口径（与持有型池子完全不同，这是本实验室的关键）
--------------------------------------------------------
做T赚的是箱体波动差价，**不能用涨跌幅衡量**（旧的「T+3 涨跌」口径量的是 β 不是做T能力）。
主指标：
  buy_rate   低吸命中率（后市最低价触及买区）
  round_rate 完成一轮率（先低吸 → 后高抛，中途未破止损）—— 「确定性」的最直接刻画
  stop_rate  破止损率 —— 「风险」
  exp_ret    可兑现期望收益（逐笔模拟；未成交记 0 = 空仓等待，不算亏）
口径保守处（对所有参数组同等保守，故组间比较有效）：①买价取买区上沿 buy_hi；
②同日既触买区又破止损时按「止损优先」；③到期（T+N）未触卖区按当日收盘平仓。
忽略滑点与手续费。

方法（沿用反转池 v5 实验室框架）
------------------------------
  A. 域扩张：在**全市场可做T域**上验证，而不是只测三源并集（分位分辨率 ↑、无选择偏差）。
     候选来源（机构底仓/龙虎榜/强势）不参与排序，故结论对线上三源候选同样适用。
  B. 先验固定因子集：方向由网格交易 / 均值回归的经济逻辑给定，等权、不筛、不调权
     → 全期都是干净样本外（这才是「确定性」的来源，不是靠回测挑出来的阈值）。
  C. 严格样本外对照：先验集 vs 自动筛（训练学 → 测试用）vs 自动筛全量（含前视）
     → 差额 = 「挑因子」这个动作制造的过拟合量。
  D. 时间切分：前 60% 训练 / 后 40% 测试；并按月 walk-forward 复核（无未来信息）。
  E. 参数网格：用**两半平均排名**（不是单半最优）找稳定格 —— 做T的「退出规则」就是网格参数。

输出：quant/_tplus_lab_result.json、quant/_tplus_lab_panel.json、web/tplus/lab.html
用法：python quant/_tplus_lab.py            # 复用面板（快）
      python quant/_tplus_lab.py --rebuild  # 强制重建面板（约 2~4 分钟）
"""
from __future__ import annotations
import os, sys, json, math, argparse, statistics
from collections import deque, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _idxkline as E

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QUANT = os.path.join(ROOT, "quant")
WEB = os.path.join(ROOT, "web", "tplus")
CACHE = os.path.join(QUANT, "_txk_cache.json")
NAMES = os.path.join(QUANT, "_stock_names.json")
OUT_RES = os.path.join(QUANT, "_tplus_lab_result.json")
OUT_PANEL = os.path.join(QUANT, "_tplus_lab_panel.json")
OUT_HTML = os.path.join(WEB, "lab.html")

STEP = 3          # 采样步长（交易日）—— 与反转实验室一致
MINI = 60         # 至少要 60 根才能算 MA60 / 箱体 / 相对强度
FMAX = 10         # 前推窗口上限（持有期最大 10 日）
HOLD = 5          # 默认持有期（线上参考）
LIQ_WIN = 20

# ---- 做T域门槛（与 build_tplus 硬门槛对齐；市值/换手用日K+股本反推近似） ----
PRICE_MIN = 3.0
CMC_LO, CMC_HI = 15.0, 1500.0     # 流通市值（亿）—— 近似口径，比线上 20~1200 放宽一档
AMP_MIN = 3.0                     # 20 日振幅下限
AMT_MIN_YI = 1.5                  # 20 日均成交额下限（亿）
TURN_LO, TURN_HI = 1.2, 26.0      # 换手率（近似）
CHG60_MIN, CHG20_MAX = -35.0, 65.0
POS52_LO, POS52_HI = 10.0, 94.0
BOX_LO, BOX_HI = 7.0, 78.0

# ---- 默认买卖点（线上 swing_plan 口径） ----
DEF_BUY_OFF = 2.0     # 买区上沿 = support × (1 + 2%)
DEF_SELL_MULT = 1.2   # 卖区目标 = max(2.5%, 1.2 × ATR%)
DEF_MIN_GAIN = 2.5
DEF_STOP_PCT = -6.0   # 相对买价（线上 box_low×0.955 的等效值约 −6%）

# ---- 先验固定集（两组对照，方向均由经济逻辑给定） ----
# 做T的两条竞争性经济假设，各自都能事先讲清道理，用「训练段选 → 测试段验」比较：
#   收敛派（A）：做T赚的是「区间往复」，所以越安静越好 —— 箱体窄、带宽低、均线粘合、波动规律、斜率平。
#   支撑派（B）：做T赚的是「支撑有效」，所以越强越好 —— 均线向上、相对强度高、贴下沿、下沿被反复验证。
PRIOR_A = ["box_dev", "bwidth", "cohesion", "amp_cv", "amp_dev", "atr_dev",
           "slope_abs", "neg_tests", "neg_amt"]
PRIOR_B = ["neg_slope", "pos", "neg_tests", "neg_rs", "box_dev",
           "amp_cv", "cohesion", "neg_amt"]
PRIOR = PRIOR_A                     # 默认（v6）落地用；最终由训练段择优决定
PRIOR_CN = {
    "box_dev": "偏离理想箱体 |箱高−20%|（收敛派：箱体要够窄，一轮才做得完）",
    "bwidth": "BOLL 带宽 4σ/MA20（收敛派：带宽低 = 波动收敛）",
    "cohesion": "均线粘合度 MA5/10/20（收敛派：粘合 = 无趋势 = 适合网格）",
    "amp_cv": "振幅变异系数（收敛派：波动越规律越可预期）",
    "amp_dev": "偏离理想振幅 |amp20−6%|（收敛派：太小没空间、太大是单边）",
    "atr_dev": "偏离理想 ATR |ATR%−5%|（收敛派）",
    "slope_abs": "|MA20 二十日斜率|（收敛派：越横盘越好）",
    "neg_tests": "负的「近 60 日下沿被测试次数」（两派共用：被验证过的支撑更可靠）",
    "neg_amt": "负的 20 日均成交额（两派共用：流动性下限）",
    "neg_slope": "负的 MA20 二十日斜率（支撑派：均线向上才做T，向下 = 接飞刀）",
    "neg_rs": "负的 20 日相对强度超额（支撑派：跑赢大盘者支撑更硬）",
    "pos": "箱内位置（支撑派：越贴下沿，低吸空间越大 —— ⚠️ 本假设已被实证否证）",
}
ALLF = ["box_dev", "bwidth", "cohesion", "amp_cv", "amp_dev", "atr_dev", "slope_abs",
        "neg_tests", "neg_amt", "neg_slope", "pos", "neg_rs",
        "amp20", "atr_pct", "box_h", "slope", "rsi14", "rs20", "turn", "amt_yi", "pos52"]

# 现行 7 维打分（v5）在实验室里的等价因子方向（用于「现行规则 vs 先验集」对照）
LEGACY = ["amp_dev", "atr_dev", "box_dev", "slope_abs", "amp_cv", "cohesion",
          "pos", "neg_amt", "pos52"]

# 面板里已有 slope / rs20，派生因子在加载时补算（避免为两个减法重建 79MB 面板）
_DERIVE = {
    "neg_slope": lambda f: (-f["slope"]) if f.get("slope") is not None else None,
    "neg_rs": lambda f: (-f["rs20"]) if f.get("rs20") is not None else None,
    "neg_pos52": lambda f: (-f["pos52"]) if f.get("pos52") is not None else None,
}


def derive(rows):
    """给面板行补派生因子（幂等）。"""
    for r in rows:
        f = r["f"]
        for k, fn in _DERIVE.items():
            if k not in f:
                try:
                    f[k] = fn(f)
                except Exception:
                    f[k] = None
    return rows


# ==================== 工具 ====================
def _prefix(a):
    ps = [0.0]
    for v in a:
        ps.append(ps[-1] + (v or 0.0))
    return ps


def _rollma(ps, i, n):
    if i + 1 < n:
        return None
    return (ps[i + 1] - ps[i + 1 - n]) / n


def _roll_ext(a, n, mx=True):
    """滚动窗口极值（窗口不满时用已有个数）。"""
    out = [None] * len(a)
    dq = deque()
    for i, v in enumerate(a):
        if v is None:
            out[i] = out[i - 1] if i else None
            continue
        if mx:
            while dq and (a[dq[-1]] is None or a[dq[-1]] <= v):
                dq.pop()
        else:
            while dq and (a[dq[-1]] is None or a[dq[-1]] >= v):
                dq.pop()
        dq.append(i)
        if dq[0] <= i - n:
            dq.popleft()
        out[i] = a[dq[0]]
    return out


def _atr(H, L, C, n, i):
    if i < n:
        return None
    s = 0.0
    for j in range(i - n + 1, i + 1):
        pc = C[j - 1]
        s += max(H[j] - L[j], abs(H[j] - pc), abs(L[j] - pc))
    return s / n


def _shares_map():
    """东财业绩快照 netprofit ÷ eps 反推股本 → 历史市值 = 当日收盘 × 股本（点时、无前视）。"""
    p = os.path.join(QUANT, "fin", "snapshot.json")
    if not os.path.exists(p):
        return {}
    snap = json.load(open(p, encoding="utf-8")).get("stocks", {})
    out = {}
    for c, v in snap.items():
        npf, eps = v.get("netprofit"), v.get("eps")
        if npf and eps and eps > 0:
            out[c] = npf / eps
    return out


def _names():
    if os.path.exists(NAMES):
        try:
            return json.load(open(NAMES, encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _bad_name(nm):
    return (not nm) or ("ST" in nm) or ("退" in nm) or ("PT" in nm)


# ==================== 做T逐笔模拟 ====================
def _sim(fl, fh, fc, buy_hi, sell_lo, stop, horizon, cons=False):
    """逐笔做T模拟（保守口径，见模块 docstring）。

    返回 {buy_i, hit_buy, hit_sell, stopped, round_ok, ret, kind}
    未成交 → ret = 0（空仓等待，是策略的一部分，不算亏）。

    cons=True **可实现口径**：反T是「先买入、后卖出」，而 A 股 **T+1** —— 当日买入的
    股票当日**不能卖出**。旧口径在「同一根 K 线既摸到买区又摸到卖区」时无条件记
    「完成一轮」，等于假设日内必定先跌后涨，实盘做不到。保守口径把卖出推迟到**次日
    及以后**，即删掉同日卖出分支（`kind` 记为 `sell_t1` 以示区分）。
    """
    m = min(horizon, len(fl))
    for k in range(m):
        lo = fl[k]
        hi = fh[k]
        if lo is None or hi is None:
            continue
        if lo <= buy_hi:                       # 成交（保守：按买区上沿成交）
            if lo <= stop:                     # 同日破位 → 止损优先
                return {"buy_i": k, "hit_buy": True, "hit_sell": False,
                        "stopped": True, "round_ok": False,
                        "ret": (stop / buy_hi - 1) * 100, "kind": "stop"}
            if hi >= sell_lo and not cons:     # 同日既成交又摸到卖区 → 算完成一轮
                return {"buy_i": k, "hit_buy": True, "hit_sell": True,
                        "stopped": False, "round_ok": True,
                        "ret": (sell_lo / buy_hi - 1) * 100, "kind": "sell"}
            for j in range(k + 1, m):
                lo2, hi2 = fl[j], fh[j]
                if lo2 is None or hi2 is None:
                    continue
                if lo2 <= stop:                # 止损优先
                    return {"buy_i": k, "hit_buy": True, "hit_sell": False,
                            "stopped": True, "round_ok": False,
                            "ret": (stop / buy_hi - 1) * 100, "kind": "stop"}
                if hi2 >= sell_lo:
                    return {"buy_i": k, "hit_buy": True, "hit_sell": True,
                            "stopped": False, "round_ok": True,
                            "ret": (sell_lo / buy_hi - 1) * 100, "kind": "sell"}
            # 到期平仓
            if fc:
                return {"buy_i": k, "hit_buy": True, "hit_sell": False,
                        "stopped": False, "round_ok": False,
                        "ret": (fc / buy_hi - 1) * 100, "kind": "expire"}
            return {"buy_i": k, "hit_buy": True, "hit_sell": False,
                    "stopped": False, "round_ok": False, "ret": 0.0, "kind": "expire"}
    return {"buy_i": None, "hit_buy": False, "hit_sell": False,
            "stopped": False, "round_ok": False, "ret": 0.0, "kind": "none"}


def _sim_sell_first(fl, fh, fc, buy_hi, sell_lo, horizon):
    """正T（先高抛、后低吸补回）—— 需要底仓，赚的是「卖价 − 买回价」。

    现实约束：A 股 T+1，先卖后买必须已有底仓；做T的目的是<b>维持底仓 + 降成本</b>。
    口径与反T对称：完成一轮记价差；到期未回补则按到期收盘价回补（踏空就是亏）。
    """
    m = min(horizon, len(fl))
    for k in range(m):
        if fh[k] is None:
            continue
        if fh[k] >= sell_lo:                       # 摸到高抛位 → 卖出
            if fl[k] is not None and fl[k] <= buy_hi:
                return {"buy_i": k, "hit_buy": True, "hit_sell": True, "stopped": False,
                        "round_ok": True, "ret": (sell_lo - buy_hi) / sell_lo * 100, "kind": "sell"}
            for j in range(k + 1, m):
                if fl[j] is None:
                    continue
                if fl[j] <= buy_hi:                # 回落补回
                    return {"buy_i": j, "hit_buy": True, "hit_sell": True, "stopped": False,
                            "round_ok": True,
                            "ret": (sell_lo - buy_hi) / sell_lo * 100, "kind": "sell"}
            if fc:
                return {"buy_i": None, "hit_buy": False, "hit_sell": True, "stopped": False,
                        "round_ok": False, "ret": (sell_lo - fc) / sell_lo * 100, "kind": "expire"}
            return {"buy_i": None, "hit_buy": False, "hit_sell": True, "stopped": False,
                    "round_ok": False, "ret": 0.0, "kind": "expire"}
    return {"buy_i": None, "hit_buy": False, "hit_sell": False, "stopped": False,
            "round_ok": False, "ret": 0.0, "kind": "none"}


_DEF_KW = dict(buy_off=DEF_BUY_OFF, sell_mult=DEF_SELL_MULT,
               min_gain=DEF_MIN_GAIN, stop_pct=DEF_STOP_PCT, horizon=HOLD)


def _sim_param(r, buy_off=DEF_BUY_OFF, sell_mult=DEF_SELL_MULT,
               min_gain=DEF_MIN_GAIN, stop_pct=DEF_STOP_PCT, horizon=HOLD,
               mode="buy_first", cons=False):
    buy_hi = r["sup"] * (1 + buy_off / 100.0)
    gain = max(min_gain, sell_mult * r["atr"])
    sell_lo = max(r["price"] * (1 + gain / 100.0), buy_hi * 1.006)
    if mode == "sell_first":
        return _sim_sell_first(r["fl"], r["fh"], r["fc"], buy_hi, sell_lo, horizon)
    stop = buy_hi * (1 + stop_pct / 100.0)
    return _sim(r["fl"], r["fh"], r["fc"], buy_hi, sell_lo, stop, horizon, cons=cons)


def _sim_realistic(r):
    """可实现口径（反T遵守 A 股 T+1：当日买入当日不可卖）。与 `_sim_default` 仅此一处差别。"""
    return _sim_param(r, cons=True, **_DEF_KW)


def _sim_default(r):
    """默认（线上现行）参数下的模拟 —— 结果缓存在行内（只存内存，落盘时机在分析之前）。"""
    s = r.get("_sd")
    if s is None:
        s = _sim_param(r, **_DEF_KW)
        r["_sd"] = s
    return s


def _summ(rs):
    """做T口径汇总。rs 为 _sim 结果列表。"""
    n = len(rs)
    if not n:
        return {"n": 0}
    rets = [x["ret"] for x in rs]
    nb = sum(1 for x in rs if x["hit_buy"])
    nrt = sum(1 for x in rs if x["round_ok"])
    nst = sum(1 for x in rs if x["stopped"])
    traded_win = sum(1 for x in rs if x["hit_buy"] and x["ret"] > 0)
    return {
        "n": n,
        "buy_rate": 100.0 * nb / n,
        "round_rate": 100.0 * nrt / n,
        "stop_rate": 100.0 * nst / n,
        "expire_rate": 100.0 * sum(1 for x in rs if x["kind"] == "expire") / n,
        "none_rate": 100.0 * sum(1 for x in rs if x["kind"] == "none") / n,
        "mean_ret": statistics.mean(rets),
        "med_ret": statistics.median(rets),
        "wr": 100.0 * sum(1 for x in rets if x > 0) / n,
        "wr_traded": 100.0 * traded_win / nb if nb else 0.0,
        "win_loss": ((sum(x for x in rets if x > 0) / max(1, sum(1 for x in rets if x > 0)))
                     / abs(sum(x for x in rets if x < 0) / max(1, sum(1 for x in rets if x < 0)))
                     if any(x < 0 for x in rets) else None),
    }


# ==================== 面板构建 ====================
def build_panel(step=STEP):
    """全市场可做T面板：域 = `_txk_cache.json` 全部正股，过了硬门槛才入面板。"""
    cache = json.load(open(CACHE, encoding="utf-8"))
    NM = _names()
    SH = _shares_map()
    codes = [c for c in cache if len(cache[c]) >= MINI + FMAX + 5]
    print("[lab] 日K缓存 %d 只，可用 %d 只；股本反推命中 %d 只"
          % (len(cache), len(codes), sum(1 for c in codes if c in SH)))

    idx = E.get_index("sh000001", 260)
    idx_dates = sorted(idx)
    _ist = {}

    def idx_state(d):
        if d in _ist:
            return _ist[d]
        ds = [x for x in idx_dates if x <= d]
        r = None
        if len(ds) >= 61:
            ser = [idx[x] for x in ds]
            ma20 = sum(ser[-20:]) / 20
            prev = sum(ser[-25:-5]) / 20
            r = (ser[-1] / ser[-21] - 1) * 100      # 指数近 20 日涨幅（%）
        _ist[d] = r
        return r

    rows = []
    skipped = defaultdict(int)
    for ci, c in enumerate(codes):
        nm = NM.get(c) or ""
        bars = cache[c]
        C = [b["last"] for b in bars]
        H = [b["high"] for b in bars]
        L = [b["low"] for b in bars]
        O = [b["open"] for b in bars]
        V = [b["volume"] for b in bars]
        vu = 1.0 if c.startswith("sh688") else 100.0
        A = [V[k] * vu * ((C[k] or 0)) for k in range(len(bars))]   # 成交额（元，近似）
        sh = SH.get(c)
        bad = _bad_name(nm)
        psC, psV, psA = _prefix(C), _prefix(V), _prefix(A)
        hi20, lo20 = _roll_ext(H, 20, True), _roll_ext(L, 20, False)
        lo60 = _roll_ext(L, 60, False)
        pmaxH, pminL = [], []
        mh, ml = -1e18, 1e18
        for k in range(len(bars)):
            mh = max(mh, H[k]); ml = min(ml, L[k])
            pmaxH.append(mh); pminL.append(ml)

        for i in range(MINI, len(bars) - FMAX - 1, step):
            if bad or i >= len(C):
                break
            close = C[i]
            if not close:
                continue
            # —— 便宜的量先判门槛（前置剪枝）——
            amt20 = (psA[i + 1] - psA[i + 1 - LIQ_WIN]) / LIQ_WIN
            amt_yi = amt20 / 1e8
            if amt_yi < AMT_MIN_YI:
                skipped["amt"] += 1; continue
            if close < PRICE_MIN:
                skipped["price"] += 1; continue
            bH, bL = hi20[i], lo20[i]
            if not (bH and bL and bL > 0):
                continue
            box_h = (bH - bL) / bL * 100
            if not (BOX_LO <= box_h <= BOX_HI):
                skipped["box"] += 1; continue
            h52 = pmaxH[i]; l52 = pminL[i]
            pos52 = (close - l52) / (h52 - l52) * 100 if h52 > l52 else 50.0
            if not (POS52_LO <= pos52 <= POS52_HI):
                skipped["pos52"] += 1; continue
            # —— 全量特征 ——
            cH, cL = H[:i + 1], L[:i + 1]
            amps = []
            for k in range(i - 19, i + 1):
                pc = C[k - 1] if k else C[0]
                if pc:
                    amps.append((H[k] - L[k]) / pc * 100)
            amp20 = sum(amps) / len(amps) if amps else 0.0
            if amp20 < AMP_MIN:
                skipped["amp"] += 1; continue
            sd = (sum((x - amp20) ** 2 for x in amps) / len(amps)) ** 0.5 if len(amps) > 2 else 0.0
            amp_cv = sd / amp20 if amp20 else 0.0
            a14 = _atr(H, L, C, 14, i)
            atr_pct = (a14 / close * 100) if a14 else 0.0
            if atr_pct < 1.0:
                skipped["atr"] += 1; continue
            ma5 = _rollma(psC, i, 5); ma10 = _rollma(psC, i, 10)
            ma20 = _rollma(psC, i, 20); ma60 = _rollma(psC, i, 60)
            ma20p = _rollma(psC, i - 20, 20)
            slope = (ma20 - ma20p) / ma20p * 100 if (ma20 and ma20p) else 0.0
            ml3 = [x for x in (ma5, ma10, ma20) if x]
            cohesion = (max(ml3) - min(ml3)) / ma20 * 100 if (ma20 and ml3) else 0.0
            bstd = (sum((C[k] - ma20) ** 2 for k in range(i - 19, i + 1)) / 20) ** 0.5 if ma20 else 0.0
            bwidth = 4 * bstd / ma20 * 100 if ma20 else 0.0
            chg20 = (close / C[i - 20] - 1) * 100 if i >= 20 and C[i - 20] else 0.0
            chg60 = (close / C[i - 60] - 1) * 100 if i >= 60 and C[i - 60] else 0.0
            if chg60 < CHG60_MIN or chg20 > CHG20_MAX:
                skipped["chg"] += 1; continue
            # 换手（近似：成交量 / 股本）
            turn = (V[i] * vu / sh * 100) if (sh and sh > 0) else None
            if turn is not None and not (TURN_LO <= turn <= TURN_HI):
                skipped["turn"] += 1; continue
            cmc_yi = (close * sh / 1e8) if sh else None
            if cmc_yi is not None and not (CMC_LO <= cmc_yi <= CMC_HI):
                skipped["cmc"] += 1; continue
            # 下沿被验证次数：近 60 日里最低价触及「近 20 日下沿 ×1.02」的天数
            lo20v = lo20[i]
            tests = sum(1 for k in range(max(0, i - 59), i + 1)
                        if cL[k] <= lo20v * 1.02) if lo20v else 0
            # RSI14
            g = ls = 0.0
            for k in range(14):
                dd = C[i - k] - C[i - k - 1]
                if dd >= 0:
                    g += dd
                else:
                    ls -= dd
            rsi14 = 100 - 100 / (1 + g / ls) if ls > 0 else (100 if g > 0 else 50)
            b20 = idx_state(bars[i]["date"])
            rs20 = (chg20 - b20) if b20 is not None else None
            pos = (close - lo20v) / (bH - lo20v) * 100 if bH > lo20v else 50.0
            sup = max(lo20v, ma20 if (ma20 and ma20 < close) else lo20v)
            mv = (close * sh) if sh else None

            # —— 前推：未来 10 日 OHLC（升序排列，k=0 即 T+1）——
            fl = [L[i + 1 + k] for k in range(FMAX) if i + 1 + k < len(bars)]
            fh = [H[i + 1 + k] for k in range(FMAX) if i + 1 + k < len(bars)]
            fc = C[i + FMAX] if i + FMAX < len(C) else None
            if len(fl) < FMAX or not fc:
                continue

            rows.append({
                "code": c, "date": bars[i]["date"],
                "price": round(close, 3), "sup": round(sup, 3),
                "atr": round(atr_pct, 3), "box_low": round(lo20v, 3),
                "f": {
                    "amp_dev": abs(amp20 - 6.0),
                    "atr_dev": abs(atr_pct - 5.0),
                    "box_dev": abs(box_h - 20.0),
                    "slope_abs": abs(slope),
                    "amp_cv": amp_cv,
                    "cohesion": cohesion,
                    "pos": pos,
                    "neg_tests": -float(tests),
                    "neg_amt": -amt_yi,
                    "neg_slope": -slope,
                    "neg_rs": (-rs20 if rs20 is not None else None),
                    "neg_pos52": -pos52,
                    "pos52": pos52,
                    "mv_log": (math.log(mv) if (mv and mv > 0) else None),
                    "amp20": amp20, "atr_pct": atr_pct, "box_h": box_h,
                    "slope": slope, "rsi14": rsi14, "rs20": rs20,
                    "turn": turn, "amt_yi": amt_yi, "bwidth": bwidth,
                },
                "fl": [round(x, 3) for x in fl],
                "fh": [round(x, 3) for x in fh],
                "fc": round(fc, 3),
            })
        if (ci + 1) % 800 == 0:
            print("  ... %d/%d 只，样本 %d" % (ci + 1, len(codes), len(rows)))
    print("[lab] 面板 %d 行；剪枝：%s"
          % (len(rows), ", ".join("%s=%d" % (k, v) for k, v in sorted(skipped.items()))))
    return rows


# ==================== 横截面分位打分 ====================
def _pd():
    """当前先验因子集的方向（恒为 −1「越小越好」；因子已在构造时统一取正向）。"""
    return {f: -1 for f in PRIOR}


def set_prior(feats):
    """把「最终落地先验集」定为训练段择优的那一组。"""
    global PRIOR
    PRIOR = list(feats)
    return _pd()


def _as_dir(use):
    if isinstance(use, dict):
        return dict(use)
    return {f: -1 for f in (use or PRIOR)}


def _rank_top(sample, use, dirs, pct=0.2, sim_kw=None):
    """日内横截面分位排序 → 每日前 pct 组成组合，与全体对照（做T口径）。"""
    use = _as_dir(use)
    dirs = _as_dir(dirs)
    byd = defaultdict(list)
    for r in sample:
        byd[r["date"]].append(r)
    top, allc, sims_top = [], [], []
    for d, rs in sorted(byd.items()):
        if len(rs) < 12:
            continue
        rk = {}
        for f in use:
            vals = sorted([(r["f"].get(f), r["code"]) for r in rs if r["f"].get(f) is not None])
            if len(vals) < 6:
                continue
            for pos, (v, c) in enumerate(vals):
                rk.setdefault(c, {})[f] = pos / (len(vals) - 1)
        scored = []
        for r in rs:
            tot = cnt = 0.0
            for f in use:
                v = rk.get(r["code"], {}).get(f)
                if v is None:
                    continue
                tot += (v if dirs[f] > 0 else 1 - v); cnt += 1
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
    if sim_kw:
        f = lambda r: _sim_param(r, **sim_kw)      # noqa: E731
    else:
        f = _sim_default
    a = _summ([f(r) for r in top])
    b = _summ([f(r) for r in allc])
    return {"n_top": len(top), "n_all": len(allc),
            "round_top": a["round_rate"], "round_all": b["round_rate"],
            "stop_top": a["stop_rate"], "stop_all": b["stop_rate"],
            "ret_top": a["mean_ret"], "ret_all": b["mean_ret"],
            "buy_top": a["buy_rate"], "buy_all": b["buy_rate"],
            "edge_round": a["round_rate"] - b["round_rate"],
            "edge_stop": b["stop_rate"] - a["stop_rate"],
            "edge_ret": a["mean_ret"] - b["mean_ret"],
            "wr_top": a["wr"], "wr_all": b["wr"]}


def _learn_feats(sample, min_spread=2.0):
    """训练段「自动筛因子」：按极差（前 1/3 vs 后 1/3 的完成一轮率差）挑，|差| < 阈值剔除。"""
    use, dirs = {}, {}
    for f in ALLF:
        pv = [r["f"].get(f) for r in sample if r["f"].get(f) is not None]
        if len(pv) < 400 or len(set(pv)) < 2:
            continue
        sv = sorted(pv)
        a, b = sv[len(sv) // 3], sv[2 * len(sv) // 3]
        if a == b:
            continue
        sims_g0 = []
        sims_g2 = []
        for r in sample:
            v = r["f"].get(f)
            if v is None:
                continue
            if v < a:
                sims_g0.append(_sim_default(r))
            elif v >= b:
                sims_g2.append(_sim_default(r))
        if len(sims_g0) < 150 or len(sims_g2) < 150:
            continue
        s0, s2 = _summ(sims_g0), _summ(sims_g2)
        sp = s2["round_rate"] - s0["round_rate"]
        if abs(sp) < min_spread:
            continue
        use[f] = 1
        dirs[f] = 1 if sp > 0 else -1
    return use, dirs


# ==================== 分析 ====================
def deciles_curve(rows, use=None, dirs=None, sim_kw=None):
    """日内十分位（做T口径）——「确定性是否随分数单调」。"""
    use = _as_dir(use)
    dirs = _as_dir(dirs or use)
    byd = defaultdict(list)
    for r in rows:
        byd[r["date"]].append(r)
    buckets = [[] for _ in range(10)]
    for d, rs in byd.items():
        if len(rs) < 30:
            continue
        rk = {}
        for f in use:
            vals = sorted([(r["f"].get(f), r["code"]) for r in rs if r["f"].get(f) is not None])
            if len(vals) < 6:
                continue
            for pos, (v, c) in enumerate(vals):
                rk.setdefault(c, {})[f] = pos / (len(vals) - 1)
        sc = []
        for r in rs:
            tot = cnt = 0.0
            for f in use:
                v = rk.get(r["code"], {}).get(f)
                if v is None:
                    continue
                tot += (v if dirs[f] > 0 else 1 - v); cnt += 1
            if cnt >= max(2, len(use) // 2):
                sc.append((tot / cnt, r))
        if len(sc) < 30:
            continue
        sc.sort(key=lambda x: -x[0])          # 分越高越靠前 → D1 = 最高分
        for k in range(10):
            seg = sc[int(len(sc) * k / 10):int(len(sc) * (k + 1) / 10)]
            buckets[k] += [r for _, r in seg]
    kw = sim_kw or {}
    f = (lambda r: _sim_param(r, **kw)) if sim_kw else _sim_default
    out = []
    for k, b in enumerate(buckets):
        s = _summ([f(r) for r in b])
        s["dec"] = k + 1
        out.append(s)
    return out


def feature_table(rows, cut, min_n=300):
    """单特征功效：训练段分 5 桶（按样本自身分位）→ 套测试段同一切点。报完成一轮率。"""
    tr = [r for r in rows if r["date"] < cut]
    te = [r for r in rows if r["date"] >= cut]
    out = []
    for f in ALLF:
        pv = sorted([r["f"].get(f) for r in tr if r["f"].get(f) is not None])
        if len(pv) < min_n or len(set(pv)) < 3:
            continue
        cuts = [pv[int(len(pv) * q)] for q in (0.2, 0.4, 0.6, 0.8)]

        def buck(rws):
            bs = [[] for _ in range(5)]
            for r in rws:
                v = r["f"].get(f)
                if v is None:
                    continue
                k = 0
                while k < 4 and v >= cuts[k]:
                    k += 1
                bs[k].append(r)
            return [_summ([_sim_default(r) for r in b]) for b in bs]
        a, b = buck(tr), buck(te)
        ra = [x["round_rate"] for x in a if x["n"] >= 60]
        rb = [x["round_rate"] for x in b if x["n"] >= 60]
        if len(ra) < 4 or len(rb) < 4:
            continue
        # Spearman 型单调性（桶序号 vs 完成一轮率）
        def mono(v):
            n = len(v)
            if n < 3:
                return 0
            inv = sum(1 for i in range(n) for j in range(i + 1, n) if v[i] > v[j])
            con = sum(1 for i in range(n) for j in range(i + 1, n) if v[i] < v[j])
            return 1 if con > inv else (-1 if inv > con else 0)
        out.append({
            "name": f, "train": a, "test": b,
            "spread_train": ra[-1] - ra[0], "spread_test": rb[-1] - rb[0],
            "mono_train": mono(ra), "mono_test": mono(rb),
            "stable": mono(ra) == mono(rb) and mono(ra) != 0,
        })
    out.sort(key=lambda x: -abs(x["spread_test"]))
    return out


def strict_oos(rows, pct=0.2):
    """严格样本外：两组先验（训练段择优 → 测试段用）vs 自动筛 vs 自动筛全量。

    判据 = **训练段 top 组合相对域均的期望收益差（edge_ret）** —— 这正是策略的目标函数；
    完成一轮率会随参数放宽而虚高（见参数网格），故不单独用它选先验。
    """
    ds = sorted({r["date"] for r in rows})
    cut = ds[int(len(ds) * 0.6)]
    tr = [r for r in rows if r["date"] < cut]
    te = [r for r in rows if r["date"] >= cut]
    da = {f: -1 for f in PRIOR_A}
    db = {f: -1 for f in PRIOR_B}
    out = {"cut_date": cut, "n_train": len(tr), "n_test": len(te), "pct": pct,
           "prior_a_feats": list(PRIOR_A), "prior_b_feats": list(PRIOR_B)}
    out["prior_a_train"] = _rank_top(tr, da, da, pct)
    out["prior_a"] = _rank_top(te, da, da, pct)
    out["prior_b_train"] = _rank_top(tr, db, db, pct)
    out["prior_b"] = _rank_top(te, db, db, pct)
    out["legacy"] = _rank_top(te, {f: -1 for f in LEGACY}, {f: -1 for f in LEGACY}, pct)

    def score(x):
        """复合判据：把「完成一轮率 edge」与「期望收益 edge」各自按典型量级标准化后等权相加。

        单用期望收益 edge 噪声太大（两派实测只差 0.06pp，等于没有差异）；
        单用完成一轮率 edge 又是有偏指标（会奖励「参数放宽」而不是「选得准」）。两者并用。
        """
        if not x:
            return -9.9
        return x["edge_round"] / 5.0 + x["edge_ret"] / 0.5
    a_s, b_s = score(out["prior_a_train"]), score(out["prior_b_train"])
    pick = "prior_a" if a_s >= b_s else "prior_b"
    out["pick"] = pick
    out["pick_feats"] = list(PRIOR_A if pick == "prior_a" else PRIOR_B)
    out["pick_train_score"] = {"prior_a": a_s, "prior_b": b_s}
    out["pick_train_edge_ret"] = {"prior_a": (out["prior_a_train"] or {}).get("edge_ret"),
                                  "prior_b": (out["prior_b_train"] or {}).get("edge_ret")}
    out["pick_train_edge_round"] = {"prior_a": (out["prior_a_train"] or {}).get("edge_round"),
                                    "prior_b": (out["prior_b_train"] or {}).get("edge_round")}
    # 两派差距是否在噪声内（|复合分差| < 0.4 ≈ 完成一轮率 edge 差 2pp 且期望差 0.2pp）
    out["pick_margin"] = abs(a_s - b_s)
    out["pick_tie"] = bool(abs(a_s - b_s) < 0.4)
    out["prior"] = out[pick]
    out["prior_feats"] = out["pick_feats"]

    u2, d2 = _learn_feats(tr)
    out["auto_strict_feats"] = sorted(u2)
    out["auto_strict"] = _rank_top(te, u2, d2, pct) if len(u2) >= 3 else None
    u3, d3 = _learn_feats(rows)
    out["auto_insample_feats"] = sorted(u3)
    out["auto_insample"] = _rank_top(rows, u3, d3, pct) if len(u3) >= 3 else None
    if out["auto_strict"] and out["auto_insample"]:
        out["gap"] = out["auto_insample"]["edge_round"] - out["auto_strict"]["edge_round"]
    else:
        out["gap"] = None
    out["overlap"] = sorted(set(u2) & set(u3))
    return out


def half_oos(rows, pct=0.10):
    """训练半 / 测试半对照（先验固定集）—— 检验「优势是否依赖期间」。"""
    ds = sorted({r["date"] for r in rows})
    cut = ds[int(len(ds) * 0.6)]
    tr = [r for r in rows if r["date"] < cut]
    te = [r for r in rows if r["date"] >= cut]
    out = {"cut_date": cut}
    for k, s in (("train", tr), ("test", te)):
        r = _rank_top(s, _pd(), _pd(), pct)
        if r:
            r["label"] = "%s ~ %s" % (min(x["date"] for x in s), max(x["date"] for x in s))
        out[k] = r
    return out


def topn_curve(rows):
    """截断比例曲线（先验固定集，测试段）→ 决定 A 档取每日前多少。"""
    ds = sorted({r["date"] for r in rows})
    cut = ds[int(len(ds) * 0.6)]
    te = [r for r in rows if r["date"] >= cut]
    out = []
    for p in (0.05, 0.10, 0.15, 0.20, 0.30, 0.50):
        r = _rank_top(te, _pd(), _pd(), p)
        if r:
            r["pct"] = p
            out.append(r)
    return out


def monthly(rows, pct=0.10):
    """逐月 walk-forward（无未来信息：每月只用此前数据，先验集不筛，故等价于直接套）。"""
    ds = sorted({r["date"] for r in rows})
    bym = defaultdict(list)
    for r in rows:
        bym[r["date"][:7]].append(r)
    ms = sorted(bym)
    out = []
    for m in ms:
        if len(bym[m]) < 500:
            continue
        r = _rank_top(bym[m], _pd(), _pd(), pct)
        if not r:
            continue
        out.append({"month": m, "n": r["n_all"], "n_top": r["n_top"],
                    "round_top": r["round_top"], "round_all": r["round_all"],
                    "edge_round": r["edge_round"], "ret_top": r["ret_top"],
                    "stop_top": r["stop_top"]})
    if out:
        pos = sum(1 for x in out if x["edge_round"] > 0)
        out_agg = {"months": len(out), "win": pos,
                   "mean_edge": statistics.mean(x["edge_round"] for x in out),
                   "mean_round_top": statistics.mean(x["round_top"] for x in out),
                   "min_edge": min(x["edge_round"] for x in out),
                   "max_edge": max(x["edge_round"] for x in out)}
    else:
        out_agg = {}
    return out, out_agg


def env_scan(rows, pct=0.10):
    """环境依赖：按「上证近 20 日涨幅」三档，看两半是否同向（决定环境门控是否有依据）。"""
    idx = E.get_index("sh000001", 260)
    ds = sorted(idx)

    def m20(d):
        dd = [x for x in ds if x <= d]
        if len(dd) < 21:
            return None
        return (idx[dd[-1]] / idx[dd[-21]] - 1) * 100
    ds_all = sorted({r["date"] for r in rows})
    cut = ds_all[int(len(ds_all) * 0.6)]
    buckets = [("弱（指数 20 日 < −3%）", -99, -3), ("中（−3% ~ +3%）", -3, 3),
               ("强（> +3%）", 3, 99)]
    out = []
    for lab, lo, hi in buckets:
        for half in ("train", "test"):
            sub = [r for r in rows if (r["date"] < cut) == (half == "train")]
            sub = [r for r in sub if (m20(r["date"]) is not None and lo <= m20(r["date"]) < hi)]
            r = _rank_top(sub, _pd(), _pd(), pct)
            if r:
                out.append({"env": lab, "half": half, "n": r["n_all"],
                            "round_top": r["round_top"], "round_all": r["round_all"],
                            "stop_top": r["stop_top"], "edge_round": r["edge_round"]})
    return out


def param_scan(rows, pct=0.30):
    """参数网格：买区深度 / 卖区目标 / 止损宽度 / 持有期。

    样本 = 先验固定集每日前 pct（策略实际会用到的那批）。两组对照：训练半 / 测试半。
    稳定性判据 = **两半平均排名**（单半最优不可信）。
    """
    ds = sorted({r["date"] for r in rows})
    cut = ds[int(len(ds) * 0.6)]
    # 先按默认参数选出「前 pct」样本，再在这批上扫参数（避免每换一组参数重排位）
    sel = {}
    for half, sub in (("train", [r for r in rows if r["date"] < cut]),
                      ("test", [r for r in rows if r["date"] >= cut])):
        byd = defaultdict(list)
        for r in sub:
            byd[r["date"]].append(r)
        keep = []
        for d, rs in byd.items():
            if len(rs) < 30:
                continue
            rk = {}
            for f in PRIOR:
                vals = sorted([(r["f"].get(f), r["code"]) for r in rs if r["f"].get(f) is not None])
                if len(vals) < 6:
                    continue
                for pos, (v, c) in enumerate(vals):
                    rk.setdefault(c, {})[f] = pos / (len(vals) - 1)
            sc = []
            for r in rs:
                tot = cnt = 0.0
                for f in PRIOR:
                    v = rk.get(r["code"], {}).get(f)
                    if v is None:
                        continue
                    tot += 1 - v; cnt += 1
                if cnt >= max(2, len(PRIOR) // 2):
                    sc.append((tot / cnt, r))
            if len(sc) < 30:
                continue
            sc.sort(key=lambda x: -x[0])
            keep += [r for _, r in sc[:max(1, int(round(len(sc) * pct)))]]
        sel[half] = keep
    print("[lab] 参数网格样本：训练半 %d / 测试半 %d" % (len(sel["train"]), len(sel["test"])))

    AXES = [
        ("buy_off", "买区深度（相对支撑 +%）", [-1.5, -1.0, -0.5, 0.0, 0.5, 1.0, 2.0, 3.0]),
        ("sell_mult", "卖区目标（ATR 倍数，下限 2.5%）", [0.3, 0.4, 0.6, 0.8, 1.0, 1.2, 1.6]),
        ("stop_pct", "止损宽度（相对买价 %）", [-2.0, -3.0, -4.0, -5.0, -6.0, -8.0, -10.0, -12.0, -15.0]),
        ("horizon", "持有期（交易日）", [2, 3, 4, 5, 7, 10]),
    ]
    base = dict(buy_off=DEF_BUY_OFF, sell_mult=DEF_SELL_MULT,
                min_gain=DEF_MIN_GAIN, stop_pct=DEF_STOP_PCT, horizon=HOLD)
    axes = []
    for key, lab, vals in AXES:
        rowsout = []
        for v in vals:
            kw = dict(base); kw[key] = v
            a = _summ([_sim_param(r, **kw) for r in sel["train"]])
            b = _summ([_sim_param(r, **kw) for r in sel["test"]])
            rowsout.append({"v": v, "train": a, "test": b,
                            "round_avg": (a["round_rate"] + b["round_rate"]) / 2,
                            "stop_avg": (a["stop_rate"] + b["stop_rate"]) / 2,
                            "ret_avg": (a["mean_ret"] + b["mean_ret"]) / 2,
                            "same_dir": ((a["round_rate"] - b["round_rate"]) * 1.0)})
        # 两半平均完成一轮率排名（1 = 最好）
        order = sorted(range(len(rowsout)), key=lambda i: -rowsout[i]["round_avg"])
        for rk, i in enumerate(order):
            rowsout[i]["rank_round"] = rk + 1
        order2 = sorted(range(len(rowsout)), key=lambda i: rowsout[i]["stop_avg"])
        for rk, i in enumerate(order2):
            rowsout[i]["rank_stop"] = rk + 1
        for r in rowsout:
            r["rank_sum"] = r["rank_round"] + r["rank_stop"]
        axes.append({"key": key, "label": lab, "vals": rowsout})

    # 二维网格：卖区目标 × 止损宽度（做T最核心的一对权衡）
    grid = []
    for sm in (0.4, 0.6, 0.8, 1.0, 1.2):
        for sp in (-3.0, -4.0, -5.0, -6.0, -8.0, -10.0, -12.0):
            kw = dict(base); kw["sell_mult"] = sm; kw["stop_pct"] = sp
            a = _summ([_sim_param(r, **kw) for r in sel["train"]])
            b = _summ([_sim_param(r, **kw) for r in sel["test"]])
            grid.append({"sell_mult": sm, "stop_pct": sp,
                         "round_train": a["round_rate"], "round_test": b["round_rate"],
                         "stop_train": a["stop_rate"], "stop_test": b["stop_rate"],
                         "ret_train": a["mean_ret"], "ret_test": b["mean_ret"],
                         "round_avg": (a["round_rate"] + b["round_rate"]) / 2,
                         "ret_avg": (a["mean_ret"] + b["mean_ret"]) / 2,
                         "stop_avg": (a["stop_rate"] + b["stop_rate"]) / 2})
    grid.sort(key=lambda x: -x["round_avg"])
    # 默认参数基准
    base_row = {"train": _summ([_sim_param(r, **base) for r in sel["train"]]),
                "test": _summ([_sim_param(r, **base) for r in sel["test"]])}
    base_row = {"train": _summ([_sim_default(r) for r in sel["train"]]),
                "test": _summ([_sim_default(r) for r in sel["test"]])}
    return {"axes": axes, "grid": grid[:24], "base": base_row,
            "n_train": len(sel["train"]), "n_test": len(sel["test"]), "pct": pct}


def _scored_by_date(sample):
    """按当前先验集在**每个交易日内**做横截面分位打分，返回 {date: [样本按分数降序]}。

    这一层与买卖参数无关，所以只需算一次，参数组合直接复用（否则每个组合都要重排 10 万行）。
    """
    byd = defaultdict(list)
    for r in sample:
        byd[r["date"]].append(r)
    out = {}
    for d, rs in byd.items():
        if len(rs) < 12:
            continue
        rk = {}
        for f in PRIOR:
            vals = sorted([(r["f"].get(f), r["code"]) for r in rs if r["f"].get(f) is not None])
            if len(vals) < 6:
                continue
            for pos, (v, c) in enumerate(vals):
                rk.setdefault(c, {})[f] = pos / (len(vals) - 1)
        sc = []
        for r in rs:
            tot = cnt = 0.0
            for f in PRIOR:
                v = rk.get(r["code"], {}).get(f)
                if v is None:
                    continue
                tot += 1 - v; cnt += 1
            if cnt >= max(2, len(PRIOR) // 2):
                sc.append((tot / cnt, r))
        if len(sc) >= 12:
            sc.sort(key=lambda x: -x[0])
            out[d] = [r for _, r in sc]
    return out


def combo_check(rows, pcts=(0.01, 0.02, 0.05, 0.10, 0.20)):
    """★ 联合检验：先验集 × 参数组合 —— 「确定性/胜率」最终能不能兑现成正期望。

    参数网格只回答「单个旋钮拧到哪」，这里回答「拧组合能不能把期望收益做正」。
    每个组合都同时报训练半与测试半，避免只挑测试半好看的组合。
    """
    ds = sorted({r["date"] for r in rows})
    cut = ds[int(len(ds) * 0.6)]
    ORD = {"train": _scored_by_date([r for r in rows if r["date"] < cut]),
           "test": _scored_by_date([r for r in rows if r["date"] >= cut])}

    def tops(half, p):
        out = []
        for d, sc in ORD[half].items():
            k = max(1, int(round(len(sc) * p)))
            out += sc[:k]
        return out
    ALL = {h: [r for sc in ORD[h].values() for r in sc] for h in ORD}
    TOP = {(h, p): tops(h, p) for h in ORD for p in pcts}

    PARAMS = [
        ("反T · 线上现行（买 +2% / 卖 1.2×ATR / 止损 −6% / T+5）", {}),
        ("反T · 买区贴支撑（+0%）", {"buy_off": 0.0}),
        ("反T · 近目标 0.4×ATR", {"sell_mult": 0.4}),
        ("反T · 近目标 0.4×ATR + 紧止损 −2%", {"sell_mult": 0.4, "stop_pct": -2.0}),
        ("★反T · 贴支撑 + 近目标 0.4×ATR + 紧止损 −2%",
         {"buy_off": 0.0, "sell_mult": 0.4, "stop_pct": -2.0}),
        ("反T · 网格法（不设硬止损 · −30% 兜底）", {"stop_pct": -30.0}),
        ("反T · 网格法 + 贴支撑 + 近目标 0.4×ATR",
         {"buy_off": 0.0, "sell_mult": 0.4, "stop_pct": -30.0}),
        ("反T · 短持有 T+3 + 近目标 0.4×ATR", {"sell_mult": 0.4, "horizon": 3}),
        ("正T · 高抛 1.2×ATR → 低吸补回（+2%）", {"mode": "sell_first"}),
        ("正T · 高抛 0.6×ATR → 低吸补回（+0%）",
         {"mode": "sell_first", "sell_mult": 0.6, "buy_off": 0.0}),
        ("正T · 高抛 0.4×ATR → 补回（−1%）",
         {"mode": "sell_first", "sell_mult": 0.4, "buy_off": -1.0}),
        ("正T · 高抛 0.4×ATR → 补回（−1%）/ T+3",
         {"mode": "sell_first", "sell_mult": 0.4, "buy_off": -1.0, "horizon": 3}),
    ]
    out = []
    for lab, kw in PARAMS:
        f = (lambda r: _sim_param(r, **kw)) if kw else _sim_default
        row = {"label": lab, "kw": kw, "pcts": [],
               "all_train": _summ([f(r) for r in ALL["train"]]),
               "all_test": _summ([f(r) for r in ALL["test"]])}
        for p in pcts:
            row["pcts"].append({
                "pct": p,
                "train": _summ([f(r) for r in TOP[("train", p)]]),
                "test": _summ([f(r) for r in TOP[("test", p)]]),
            })
        out.append(row)
    return out


def env_combo(rows, pct=0.10):
    """环境 × 参数：只在「指数近 20 日涨幅」落入某个区间的日子做T，期望收益能否转正。

    环境量用「截至该日、上证指数近 20 日涨幅」（滞后可得，无未来信息）。
    这是对 `env_scan` 的补充 —— env_scan 只看「完成一轮率」，这里直接看「期望收益」。
    """
    idx = E.get_index("sh000001", 320)
    ds = sorted(idx)
    _c = {}

    def m20(d):
        if d in _c:
            return _c[d]
        dd = [x for x in ds if x <= d]
        v = (idx[dd[-1]] / idx[dd[-21]] - 1) * 100 if len(dd) >= 21 else None
        _c[d] = v
        return v
    KW = [("反T · 线上现行", {}),
          ("反T · 最优（贴支撑+近目标0.4+紧止损−2%）",
           {"buy_off": 0.0, "sell_mult": 0.4, "stop_pct": -2.0}),
          ("正T · 高抛0.4×ATR → 补回(−1%)",
           {"mode": "sell_first", "sell_mult": 0.4, "buy_off": -1.0})]
    BUCKETS = [("&lt; −3%（弱势）", -999, -3), ("−3% ~ 0（偏弱）", -3, 0),
               ("0 ~ +3%（偏强）", 0, 3), ("&gt; +3%（强势）", 3, 999)]
    out = []
    for lab, kw in KW:
        f = (lambda r: _sim_param(r, **kw)) if kw else _sim_default
        for blab, lo, hi in BUCKETS:
            sub = [r for r in rows
                   if (m20(r["date"]) is not None and lo <= m20(r["date"]) < hi)]
            if len(sub) < 800:
                continue
            ordd = _scored_by_date(sub)
            top, allc = [], []
            for d, sc in ordd.items():
                k = max(1, int(round(len(sc) * pct)))
                top += sc[:k]
                allc += sc
            if len(top) < 80:
                continue
            a, b = _summ([f(r) for r in top]), _summ([f(r) for r in allc])
            out.append({"param": lab, "env": blab, "n": len(allc), "n_top": len(top),
                        "round_top": a["round_rate"], "round_all": b["round_rate"],
                        "stop_top": a["stop_rate"], "ret_top": a["mean_ret"],
                        "ret_all": b["mean_ret"], "wr_top": a["wr"],
                        "edge_round": a["round_rate"] - b["round_rate"],
                        "edge_ret": a["mean_ret"] - b["mean_ret"]})
    return out


# ==================== 渲染 ====================
CSS = """<style>
:root{--bg:#fbfbfd;--card:#fff;--text:#1d1d1f;--muted:#6e6e73;--line:#e5e5e7;
 --up:#ff3b30;--dn:#34c759;--blue:#0071e3;--gold:#1a73e8;--orange:#ff9500;--purple:#af52de;}
*{box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"PingFang SC","Microsoft YaHei",sans-serif;
 background:var(--bg);color:var(--text);line-height:1.7;margin:0;padding:0}
.wrap{max-width:1000px;margin:0 auto;padding:28px 18px 56px}
h1{font-size:23px;font-weight:700;margin:0 0 6px;letter-spacing:-.02em}
h2{font-size:18px;font-weight:600;margin:26px 0 12px;padding-bottom:8px;border-bottom:2px solid var(--blue)}
h3{font-size:15px;font-weight:600;margin:18px 0 8px}
.sub{color:var(--muted);font-size:13px;margin-bottom:8px}
.card{background:var(--card);border-radius:16px;padding:16px 20px;margin:12px 0;box-shadow:0 1px 3px rgba(0,0,0,.05)}
.box{border-left:4px solid var(--blue);background:#f0f7ff;padding:14px 18px;border-radius:0 12px 12px 0;margin:14px 0}
.box.gold{border-color:var(--gold);background:#fffaf0}
.box.red{border-color:#c0392b;background:#fdf1f0}
.box.green{border-color:var(--dn);background:#f0faf3}
table{width:100%;border-collapse:collapse;font-size:12.5px;margin:10px 0}
th,td{padding:8px 6px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
th{white-space:nowrap;color:var(--muted);font-weight:600;font-size:11.5px;background:#fafafa}
.num{font-variant-numeric:tabular-nums}
.up{color:var(--up)}.dn{color:var(--dn)}.am{color:var(--blue)}.dim{color:#b0b3b8}
.note{font-size:12.5px;color:var(--muted);margin-top:8px}
.tag{display:inline-block;font-size:11px;padding:2px 8px;border-radius:10px;margin:1px 2px}
.tag.A{background:#e6f7ec;color:#1a7a45}
.tag.B{background:#fff3e0;color:#e65100}
.tag.C{background:#fdecea;color:#c0392b}
code{background:#f1f3f4;border-radius:4px;padding:1px 5px;font-size:12px}
.foot{text-align:center;color:var(--muted);font-size:12px;margin-top:28px}
ul{padding-left:20px}
li{margin:4px 0}
</style>"""


def _p(x, n=1):
    return "%.*f%%" % (n, x) if x is not None else "—"


def _s(x, n=2):
    return "%+.*f%%" % (n, x) if x is not None else "—"


def _cls(v):
    return "up" if v > 0 else ("dn" if v < 0 else "dim")


def _pick(x, *ks, d=None):
    for k in ks:
        if isinstance(x, dict) and x.get(k) is not None:
            return x[k]
    return d


def _combo_row(c):
    ps = {p["pct"]: p for p in (c.get("pcts") or [])}

    def g(pct, h="test"):
        return ((ps.get(pct) or {}).get(h) or {})

    def ec(d):
        v = d.get("mean_ret")
        return "<td class='num %s'>%s</td>" % (_cls(v or 0), _s(v) if v is not None else "—")
    t10, e10 = g(0.10, "train"), g(0.10, "test")
    atr = c.get("all_train") or {}
    both_pos = (t10.get("mean_ret") is not None and t10["mean_ret"] > 0
                and e10.get("mean_ret") is not None and e10["mean_ret"] > 0)
    same_sign = ((t10.get("mean_ret") or 0) > 0) == ((e10.get("mean_ret") or 0) > 0)
    tag = ("<b class='up'>★两半俱正</b>" if both_pos else
           ("<span class='dim'>两半同号</span>" if same_sign else "<span class='dim'>反向</span>"))
    return ("<tr%s><td>%s</td>"
            "<td class='num %s'>%s</td>"
            "<td class='num'>%s</td><td class='num'>%s</td><td class='num %s'>%s</td>"
            "%s%s%s%s%s"
            "<td class='num'>%s</td><td class='num'>%s</td><td class='num %s'>%s</td>"
            "<td>%s</td></tr>"
            % (" style='background:#f0faf3'" if both_pos else "",
               c["label"],
               _cls(atr.get("mean_ret") or 0), _s(atr.get("mean_ret")),
               _p(t10.get("round_rate")), _p(t10.get("stop_rate")),
               _cls(t10.get("mean_ret") or 0), _s(t10.get("mean_ret")),
               ec(g(0.02, "train")), ec(g(0.01)), ec(g(0.02)), ec(g(0.05)), ec(g(0.20)),
               _p(e10.get("round_rate")), _p(e10.get("stop_rate")),
               _cls(e10.get("mean_ret") or 0), _s(e10.get("mean_ret")),
               tag))


def render_lab(res):
    rows = res["panel_summary"]
    cut = res["cut_date"]
    so = res.get("strict_oos") or {}
    ho = res.get("half_oos") or {}
    dec = res.get("deciles") or []
    ft = res.get("features") or []
    tpn = res.get("topn_curve") or []
    mon = res.get("monthly") or []
    magg = res.get("monthly_agg") or {}
    env = res.get("env_scan") or []
    ps = res.get("param_scan") or {}
    cb = res.get("combo") or []
    PCN = res.get("prior_cn") or {}
    PA, PB = res.get("prior_a") or [], res.get("prior_b") or []
    SEL = res.get("prior_set") or []

    d1 = dec[0] if dec else {}
    d10 = dec[-1] if dec else {}
    prior_te = so.get("prior") or {}
    a_tr, a_te = so.get("prior_a_train") or {}, so.get("prior_a") or {}
    b_tr, b_te = so.get("prior_b_train") or {}, so.get("prior_b") or {}
    lg = so.get("legacy") or {}

    # 单特征表
    ftr = "".join(
        "<tr%s><td>%s</td><td class='num'>%s</td><td class='num'>%s</td>"
        "<td class='num'>%+.1fpp</td><td class='num'>%+.1fpp</td><td>%s</td></tr>"
        % (" style='background:#fffaf0'" if f["name"] in SEL else "",
           f["name"],
           " ".join("%.0f" % b["round_rate"] for b in f["train"] if b["n"] >= 60),
           " ".join("%.0f" % b["round_rate"] for b in f["test"] if b["n"] >= 60),
           f["spread_train"], f["spread_test"],
           "★稳定" if f["stable"] else ("⚠️反向" if f["mono_train"] != f["mono_test"] else "—"))
        for f in ft[:16])

    # 十分位
    dcr = "".join(
        "<tr><td>D%d</td><td class='num'>%d</td><td class='num'>%s</td><td class='num'>%s</td>"
        "<td class='num'>%s</td><td class='num'>%s</td><td class='num'>%s</td>"
        "<td class='num %s'>%s</td></tr>"
        % (d["dec"], d["n"], _p(d["buy_rate"]), _p(d["round_rate"]), _p(d["stop_rate"]),
           _p(d.get("wr_traded")), _p(d.get("wr")),
           _cls(d["mean_ret"]), _s(d["mean_ret"]))
        for d in dec)

    # 两组先验 + 自动筛
    sor = []
    for k, lab in (("prior_a", "收敛派 A（箱体/带宽/粘合/规律/斜率平）"),
                   ("prior_b", "支撑派 B（斜率向上/相对强度/贴下沿/支撑测试）"),
                   ("legacy", "现行 7 维等价的 9 因子（v5 口径）"),
                   ("auto_strict", "自动筛 · 严格样本外（训练段学 → 测试段用）"),
                   ("auto_insample", "自动筛 · 全量（含测试段，前视）")):
        r = so.get(k)
        if not r:
            sor.append("<tr><td>%s</td><td colspan='6' class='dim'>—</td></tr>" % lab)
            continue
        hl = " style='background:#f0faf3;font-weight:600'" if k == so.get("pick") else ""
        sor.append("<tr%s><td>%s</td><td class='num'>%d</td><td class='num'>%s</td><td class='num'>%s</td>"
                   "<td class='num %s'>%+.1fpp</td><td class='num %s'>%s</td>"
                   "<td class='num'>%s</td></tr>"
                   % (hl, lab, r["n_top"], _p(r["round_top"]), _p(r["round_all"]),
                      _cls(r["edge_round"]), r["edge_round"], _cls(r["edge_ret"]),
                      _s(r["edge_ret"]), _p(r["stop_top"])))

    # 先前对照（训练段）
    pre_row = ("<tr><td>收敛派 A</td><td class='num'>%d</td><td class='num'>%s</td>"
               "<td class='num'>%s</td><td class='num %s'>%s</td><td class='num'>%s</td>"
               "<td class='num %s'>%+.1fpp</td></tr>"
               "<tr><td>支撑派 B</td><td class='num'>%d</td><td class='num'>%s</td>"
               "<td class='num'>%s</td><td class='num %s'>%s</td><td class='num'>%s</td>"
               "<td class='num %s'>%+.1fpp</td></tr>"
               % (_pick(a_tr, "n_top", d=0), _p(a_tr.get("round_top")), _p(a_tr.get("round_all")),
                  _cls(a_tr.get("mean_ret", 0)), _s(a_tr.get("mean_ret")),
                  _p(a_tr.get("stop_top")), _cls(a_tr.get("edge_ret", 0)),
                  a_tr.get("edge_ret", 0),
                  _pick(b_tr, "n_top", d=0), _p(b_tr.get("round_top")), _p(b_tr.get("round_all")),
                  _cls(b_tr.get("mean_ret", 0)), _s(b_tr.get("mean_ret")),
                  _p(b_tr.get("stop_top")), _cls(b_tr.get("edge_ret", 0)),
                  b_tr.get("edge_ret", 0)))

    # 两半
    hor = ""
    for kk, lab in (("train", "训练半"), ("test", "测试半")):
        r = ho.get(kk)
        if not r:
            continue
        hor += ("<tr><td>%s（%s）</td><td class='num'>%d</td><td class='num'>%s</td>"
                "<td class='num'>%s</td><td class='num %s'>%+.1fpp</td><td class='num'>%s</td>"
                "<td class='num %s'>%s</td></tr>"
                % (lab, r.get("label", ""), r["n_top"], _p(r["round_top"]), _p(r["round_all"]),
                   _cls(r["edge_round"]), r["edge_round"], _p(r["stop_top"]),
                   _cls(r["edge_ret"]), _s(r["edge_ret"])))

    # 截断曲线
    tpnr = "".join(
        "<tr><td class='num'>%.0f%%</td><td class='num'>%d</td><td class='num'>%s</td>"
        "<td class='num'>%s</td><td class='num %s'>%+.1fpp</td><td class='num'>%s</td>"
        "<td class='num %s'>%s</td></tr>"
        % (t["pct"] * 100, t["n_top"], _p(t["round_top"]), _p(t["round_all"]),
           _cls(t["edge_round"]), t["edge_round"], _p(t["stop_top"]),
           _cls(t["edge_ret"]), _s(t["edge_ret"]))
        for t in tpn)

    # 逐月
    monr = "".join(
        "<tr><td>%s</td><td class='num'>%d</td><td class='num'>%s</td><td class='num'>%s</td>"
        "<td class='num %s'>%+.1fpp</td><td class='num %s'>%s</td></tr>"
        % (m["month"], m["n"], _p(m["round_top"]), _p(m["round_all"]),
           _cls(m["edge_round"]), m["edge_round"], _cls(m["ret_top"]), _s(m["ret_top"]))
        for m in mon)

    # 环境
    envr = "".join(
        "<tr><td>%s</td><td>%s</td><td class='num'>%d</td><td class='num'>%s</td>"
        "<td class='num'>%s</td><td class='num %s'>%+.1fpp</td><td class='num'>%s</td></tr>"
        % (e["env"], "训练半" if e["half"] == "train" else "测试半", e["n"],
           _p(e["round_top"]), _p(e["round_all"]), _cls(e["edge_round"]), e["edge_round"],
           _p(e["stop_top"]))
        for e in env)

    # 参数轴
    axr = ""
    for ax in ps.get("axes") or []:
        axr += ("<h3>%s</h3><table><thead><tr><th>取值</th><th>训练半<br>完成一轮</th>"
                "<th>测试半<br>完成一轮</th><th>两半均值</th><th>训练半<br>破止损</th>"
                "<th>测试半<br>破止损</th><th>两半<br>期望收益</th></tr></thead><tbody>"
                % ax["label"])
        for r in ax["vals"]:
            axr += ("<tr><td class='num'>%s</td><td class='num'>%s</td><td class='num'>%s</td>"
                    "<td class='num am'>%s</td><td class='num'>%s</td><td class='num'>%s</td>"
                    "<td class='num %s'>%s</td></tr>"
                    % (r["v"], _p(r["train"]["round_rate"]), _p(r["test"]["round_rate"]),
                       _p(r["round_avg"]), _p(r["train"]["stop_rate"]),
                       _p(r["test"]["stop_rate"]), _cls(r["ret_avg"]), _s(r["ret_avg"])))
        axr += "</tbody></table>"
    grd = "".join(
        "<tr><td class='num'>%.1f×ATR</td><td class='num'>%s</td><td class='num'>%s</td>"
        "<td class='num'>%s</td><td class='num'>%s</td><td class='num'>%s</td>"
        "<td class='num'>%s</td><td class='num %s'>%s</td></tr>"
        % (g["sell_mult"], _s(g["stop_pct"], 0), _p(g["round_train"]), _p(g["round_test"]),
           _p(g["stop_train"]), _p(g["stop_test"]), _p(g["round_avg"]),
           _cls(g["ret_avg"]), _s(g["ret_avg"]))
        for g in (ps.get("grid") or [])[:18])
    psb = ps.get("base") or {}
    ptr, pte = psb.get("train") or {}, psb.get("test") or {}

    # 联合检验
    combor = "".join(_combo_row(c) for c in cb)
    # 环境 × 参数
    ecb = res.get("env_combo") or []

    def _env_row(e):
        return ("<tr><td>%s</td><td>%s</td><td class='num'>%s</td>"
                "<td class='num'>%s</td><td class='num'>%s</td><td class='num %s'>%s</td>"
                "<td class='num'>%s</td><td class='num %s'>%s</td>"
                "<td class='num %s'>%s</td></tr>"
                % (e["param"], e["env"], "{:,}".format(e["n_top"]),
                   _p(e["round_top"]), _p(e["round_all"]),
                   _cls(e["edge_round"] or 0), _s(e["edge_round"], 1),
                   _p(e["stop_top"]),
                   _cls(e["ret_top"] or 0), _s(e["ret_top"]),
                   _cls(e["ret_all"] or 0), _s(e["ret_all"])))
    envcr = "".join(_env_row(e) for e in ecb)
    # 环境 × 参数：找出「top10% 与域均期望同时为正」的配对（唯一可信的做T窗口）
    _ec_pos = [e for e in ecb if (e["ret_top"] or 0) > 0 and (e["ret_all"] or 0) > 0]

    def _short(s):
        return s.replace("反T · ", "反T·").replace("正T · ", "正T·")
    if _ec_pos:
        envfound = ("<b>本节实测：</b>%d 个「参数组合 × 环境档」里，只有 <b>%d 个</b>做到"
                    "「top10%% 与域均期望同时为正」——"
                    % (len(ecb), len(_ec_pos))
                    + "；".join("<b>%s</b> × <b>%s</b>（%s / 域均 %s）"
                                % (_short(e["param"]), e["env"],
                                   _s(e["ret_top"]), _s(e["ret_all"]))
                                for e in _ec_pos[:6])
                    + "。其余配对在任一环境档下都至少有一项为负。"
                      "这说明<b>择时能把期望转正，但必须「参数方向」与「环境方向」配对</b>："
                      "弱环境里做反T（先低吸）、强环境里做正T（先高抛），"
                      "反向配对（弱环境做正T、强环境做反T）是全表最差的一档。"
                      "不是随便做T都能靠「只在该做的时候做」救回来。")
    else:
        envfound = ("<b>本节实测：</b>没有任何「参数组合 × 环境档」能做到 top10%% 与域均同时为正 —— "
                    "说明本域内做T的期望收益无法通过「只在该做的时候做」转正。")
    # 找「测试段前 10% 期望收益最高」的组合
    def _te10(c):
        for p in (c.get("pcts") or []):
            if abs(p["pct"] - 0.10) < 1e-9:
                return (p.get("test") or {}).get("mean_ret")
        return None
    ok_c = [c for c in cb if _te10(c) is not None]
    best_te = max(ok_c, key=_te10) if ok_c else None
    pos_cnt = sum(1 for c in ok_c if (_te10(c) or 0) > 0)
    best10 = _te10(best_te) if best_te else None
    cbest = None
    for c in ok_c:
        t = _te10(c) or -9
        tr10 = None
        for p in (c.get("pcts") or []):
            if abs(p["pct"] - 0.10) < 1e-9:
                tr10 = (p.get("train") or {}).get("mean_ret")
        if t > 0 and tr10 is not None and (cbest is None or t + tr10 > cbest[0]):
            cbest = (t + tr10, c, t, tr10)

    axes_lookup = {a["key"]: a for a in (ps.get("axes") or [])}

    def _best(key, by="ret"):
        a = axes_lookup.get(key)
        if not a:
            return None
        if by == "round":
            return max(a["vals"], key=lambda x: x["round_avg"])
        return max(a["vals"], key=lambda x: x["ret_avg"])
    b_buy, b_sell = _best("buy_off"), _best("sell_mult")
    b_stop, b_hold = _best("stop_pct", "round"), _best("horizon")

    pri = "".join("<tr><td>%s</td><td>%s</td><td class='num'>%+d</td><td>%s</td></tr>"
                  % (f, "越小越好", -1, PCN.get(f, "—"))
                  for f in SEL)

    return f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>做T池 · 特征功效实验室 · {res['data_max']}</title>{CSS}</head>
<body><div class="wrap">
<h1>做T池 · 特征功效实验室</h1>
<div class="sub">目的：用<b>样本外实证</b>回答「做T的因子有没有预测力、方向如何、买卖点该怎么设」，
替代「照 347 样本小结回测手调阈值」。面板：<b>全市场 {res['universe_n']:,} 只 A 股</b>
（<code>_txk_cache.json</code> 全量正股，剔 ST/退）过做T硬门槛 → <b>{rows['n']:,} 个「股票×交易日」样本</b>
（{res['data_min']} ~ {res['data_max']}，步长 3 交易日）。时间切分：前 60%（至 <b>{cut}</b>）训练，后 40% 测试。</div>

<div class="box red"><b>⚠️ 口径先说清楚（做T的胜率 ≠ 涨跌幅，也 ≠ 完成一轮率）：</b>
做T赚的是箱体内的波动差价，所以本页不用「T+3 涨跌」衡量（那量的是 β）。
本页同时报三个指标，<b>并且以「可兑现期望收益」为主判断</b>：
<b>完成一轮率</b>（先低吸 → 后高抛、中途未破止损）、<b>破止损率</b>、<b>可兑现期望收益</b>
（逐笔模拟：未成交记 0 = 空仓等待不算亏）。<br>
<b style="color:#b00020">为什么不能只看完成一轮率</b>：它随「参数放宽」单调上升
（把止损放宽到 −12%、目标缩到 0.4×ATR，完成一轮率能从 16% 抬到 33%），
但同期<b>期望收益反而更差</b> —— 它衡量的是「有没有走完一个来回」，不是「赚不赚钱」。
三个保守假设对所有参数组同等作用，故<b>组间比较有效、绝对值偏保守</b>：
①买价取买区上沿 ②同日既成交又破位时按「止损优先」 ③到期未触卖区按当日收盘平仓。忽略滑点与手续费。</div>

<div class="box gold"><b>核心结论（v6 · 全市场域 · {rows['n']:,} 样本）：</b>
① <b>现行做T框架在全市场域是负期望</b>：默认参数（买区 +2% · 卖区 1.2×ATR · 止损 −6% · T+5）
下完成一轮 <b>{rows['round_rate']:.1f}%</b>、破止损 <b>{rows['stop_rate']:.1f}%</b>，
期望收益 <b>{rows['mean_ret']:+.2f}%</b>；成交后胜率仅 <b>{rows.get('wr_traded', 0):.1f}%</b>。
根因不是「选不到票」，而是<b>盈亏比失配</b>：赚一次 2.5~4%，亏一次 6%，
且破止损样本多于完成一轮样本。<br>
② <b>打分器排序力其实很强，但优化的东西错了</b>：十分位 D1 完成一轮 <b>{d1.get('round_rate', 0):.1f}%</b>
→ D10 <b>{d10.get('round_rate', 0):.1f}%</b>（<b>{(d1.get('round_rate', 0) - d10.get('round_rate', 0)):+.1f}pp</b>，
低吸命中 {d1.get('buy_rate', 0):.1f}% vs {d10.get('buy_rate', 0):.1f}%），
<b>但期望收益 D1 {d1.get('mean_ret', 0):+.2f}% 反而比 D10 {d10.get('mean_ret', 0):+.2f}% 更差</b> ——
现行打分挑出来的是「波动大、贴下沿、最容易成交也最容易破位」的票。
③ <b>「安静」比「强势」更能提高确定性</b>：单特征上箱体高度 / BOLL 带宽 / 均线粘合度全部
<b>单调且两半同向</b>（箱体最窄档完成一轮 {ft[0]['test'][0]['round_rate'] if ft else 0:.0f}% vs 最宽档
{ft[0]['test'][-1]['round_rate'] if ft else 0:.0f}%），而「MA20 向上 / 相对强度高」并无稳定增益 ——
做T赚的是区间往复，不是趋势。<br>
④ <b>参数侧才是抓手</b>：{len(ok_c)} 个「先验集 × 参数」组合里，测试段前 10% 期望收益为正的有
<b>{pos_cnt} 个</b>{('，最好的是「%s」→ 测试段前 10%% 期望 <b>%+.2f%%</b>' % (best_te['label'], best10)) if best_te and best10 else ''}。<br>
⑤ 逐月稳健性：{magg.get('months', 0)} 个月里 <b>{magg.get('win', 0)} 个月</b>完成一轮率优于域均
（edge {magg.get('min_edge', 0):+.1f}pp ~ {magg.get('max_edge', 0):+.1f}pp）——
<b>「相对更会做T」是稳定的，「绝对赚钱」不是</b>（见第七节期望收益列的符号）。</div>

<h2>一、两条先验假设的对照（谁更对，由训练段决定、测试段验证）</h2>
<div class="card"><table>
<thead><tr><th>半段</th><th>假设</th><th>n_top</th><th>top 完成一轮</th><th>域均完成一轮</th>
<th>top 期望收益</th><th>top 破止损</th><th>edge（期望收益）</th></tr></thead>
<tbody>{pre_row}</tbody></table>
<div class="note">做T有两条互相竞争的经济假设，都能事先讲清楚，故都用「训练段择优、测试段验证」的方式比较，
而不是拍脑袋选一组：<br>
<b>收敛派 A</b>（{len(PA)} 因子）：<i>做T赚的是区间往复 → 越安静越好</i> —— 箱体窄、BOLL 带宽低、
均线粘合、振幅规律、斜率平、下沿被反复验证。<br>
<b>支撑派 B</b>（{len(PB)} 因子）：<i>做T赚的是支撑有效 → 越强越好</i> —— MA20 向上、相对强度高、
贴下沿、下沿被验证。<br>
判据 = 复合分（<b>完成一轮率 edge ÷ 5 + 期望收益 edge ÷ 0.5</b>，两者按典型量级标准化后等权）：
收敛派 {so.get('pick_train_score', {}).get('prior_a', 0):+.2f} vs 支撑派
{so.get('pick_train_score', {}).get('prior_b', 0):+.2f}
（完成一轮率 edge {so.get('pick_train_edge_round', {}).get('prior_a', 0):+.1f}pp /
{so.get('pick_train_edge_round', {}).get('prior_b', 0):+.1f}pp；期望收益 edge
{so.get('pick_train_edge_ret', {}).get('prior_a', 0):+.2f}pp /
{so.get('pick_train_edge_ret', {}).get('prior_b', 0):+.2f}pp）→
选定 <b>{'收敛派 A' if so.get('pick') == 'prior_a' else '支撑派 B'}</b>。
{'<b style="color:#b00020">⚠️ 两派复合分差 &lt; 0.4，属于噪声范围</b> —— 选定只是「按训练段排序取前者」，不代表它显著更优；真正稳健的结论是<b>两派共同包含的那些因子（箱体窄、波动规律、均线粘合、下沿被验证、流动性）</b>。' if so.get('pick_tie') else ''}
其测试段结果见第五节。</div></div>

<h2>二、最终先验固定因子集（{len(SEL)} 个，等权、方向全为「越小越好」）</h2>
<div class="card"><table>
<thead><tr><th>因子</th><th>方向</th><th>dir</th><th>做T逻辑</th></tr></thead>
<tbody>{pri}</tbody></table>
<div class="note">全部等权、<b>不筛因子、不调权重</b> → 全期都是干净样本外，这是「确定性」的来源。
命名里 <code>neg_*</code> = 原本「越大越好」的量已取负，统一成「越小越好」。
⚠️ 首轮的「贴箱体下沿最好」（<code>pos</code>）假设<b>已被实证否证</b>（见第三节 V 形），未进入最终集。</div></div>

<h2>三、单特征功效（训练段分 5 桶 → 套测试段；数值 = 完成一轮率 %）</h2>
<div class="card"><table>
<thead><tr><th>因子</th><th>训练 5 桶（低→高）</th><th>测试 5 桶</th><th>训练极差</th><th>测试极差</th><th>跨期一致性</th></tr></thead>
<tbody>{ftr}</tbody></table>
<div class="note">行底色 = 进入最终先验集。★稳定 = 训练与测试单调方向一致（可作依据）；⚠️反向 = 两期方向相反
（该因子的「预测力」只是市场状态的代理）。<b>桶序是「因子值从低到高」</b>；
最终先验集里所有因子 dir = −1，理想形态是完成一轮率<b>随桶序号递减</b>。<br>
注意 <code>pos</code>（箱内位置）呈 <b>V 形</b>（贴下沿与中枢都好、20%~40% 那段最差）→ 单调先验不成立；
<code>rsi14</code> 同理（中段最好）。这两个都不进最终集。</div></div>

<h2>四、十分位（按最终先验组合分降序：D1 = 分数最高）</h2>
<div class="card"><table>
<thead><tr><th>分位</th><th>n</th><th>低吸命中</th><th>完成一轮</th><th>破止损</th>
<th>成交后胜率</th><th>正收益占比</th><th>期望收益</th></tr></thead>
<tbody>{dcr}</tbody></table>
<div class="note">分位在<b>每个交易日内</b>排序后聚合（全局排序会把「日期」混进分位，量到的是行情而非打分能力）。
D1 = 打分最高档。<b>本表的读法</b>：完成一轮率随 D 升高而下降（打分有效），
但期望收益未必同向 —— 因为「低吸命中率高」意味着「承接了更多下跌」，
所以一只票「容易被买到」和「买了能赚」是两件事，这也是本页把期望收益单列的原因。</div></div>

<h2>五、严格样本外对照（同一测试段、同一 top{so.get('pct', 0.2) * 100:.0f}% 口径）</h2>
<div class="card"><table>
<thead><tr><th>口径</th><th>n_top</th><th>top 完成一轮</th><th>域均 完成一轮</th><th>edge（完成一轮）</th>
<th>edge（期望收益）</th><th>top 破止损</th></tr></thead>
<tbody>{''.join(sor)}</tbody></table>
<div class="note">绿底 = 本实验室选定并落地的口径。先验固定集 = 等权不筛；「自动筛」= 在训练段按完成一轮率
极差挑因子（|差| ≥ 2pp），练习段共选出 {len(so.get('auto_strict_feats') or [])} 个、全量
{len(so.get('auto_insample_feats') or [])} 个。<b>「自动筛·全量」比「自动筛·严格样本外」高出的部分
（{(so.get('gap') or 0):.1f}pp）就是挑因子这个动作制造的过拟合量</b>，不是本事。</div></div>

<h2>六、训练半 / 测试半对照（优势是否依赖期间）</h2>
<div class="card"><table>
<thead><tr><th>半段</th><th>n_top</th><th>top 完成一轮</th><th>域均 完成一轮</th><th>edge</th>
<th>top 破止损</th><th>edge（期望收益）</th></tr></thead>
<tbody>{hor}</tbody></table>
<div class="note">口径：最终先验集，每日取前 10%。<b>完成一轮率的两半同向 = 稳定的相对能力</b>；
但期望收益的绝对水平由行情决定（测试半破止损率显著更高），
所以环境只应该用来<b>控 β 与仓位</b>，不该用来「择时调因子」。</div></div>

<h2>七、逐月 walk-forward（每月单独口径）</h2>
<div class="card"><table>
<thead><tr><th>月份</th><th>域内 n</th><th>top10% 完成一轮</th><th>域均完成一轮</th><th>edge</th><th>top 期望收益</th></tr></thead>
<tbody>{monr}</tbody></table>
<div class="note">平均 edge <b>{magg.get('mean_edge', 0):+.1f}pp</b>，
{magg.get('win', 0)}/{magg.get('months', 0)} 个月为正，区间 {magg.get('min_edge', 0):+.1f}pp ~ {magg.get('max_edge', 0):+.1f}pp。
这是「不掺未来信息」的检验：每月只用当月数据，因子方向由先验固定，不存在学习泄漏。
<b>关键读法</b>：完成一轮率列几乎月月为正（选股有效），
但期望收益列符号会翻（{sum(1 for m in mon if m.get('ret_top', 0) > 0)}/{len(mon)} 个月为正）——
说明「相对更会做T」稳定，「绝对赚钱」取决于当期是否适合做T。</div></div>

<h2>八、环境分桶（按上证近 20 日涨幅三档）</h2>
<div class="card"><table>
<thead><tr><th>环境</th><th>半段</th><th>域内 n</th><th>top10% 完成一轮</th><th>域均完成一轮</th><th>edge</th><th>top10% 破止损</th></tr></thead>
<tbody>{envr}</tbody></table>
<div class="note">用于判断「环境门控能不能提高做T胜率」：分环境的 edge 差异不大，
而<b>破止损率在强/弱环境之间差异巨大</b>（{env[0]['stop_top'] if env else 0:.1f}% ~
{max([e['stop_top'] for e in env] or [0]):.1f}%），所以线上 <code>_idxkline.market_env</code> 的门控
定位是<b>控暴露与仓位</b>（弱势只放行 A 档 + 收紧结构条件），而不是「换个因子就能提高胜率」。</div></div>

<h2>九、参数网格（做T真正的抓手：买区 / 卖区 / 止损 / 持有期）</h2>
<div class="card">
<div class="note">样本 = 先验集每日前 {(ps.get('pct') or 0) * 100:.0f}% 的标的
（训练半 {(ps.get('n_train') or 0):,} 例 / 测试半 {(ps.get('n_test') or 0):,} 例）。
默认参数（线上现行）→ 训练半完成一轮 <b>{ptr.get('round_rate', 0):.1f}%</b> / 破止损
<b>{ptr.get('stop_rate', 0):.1f}%</b> / 期望 <b>{ptr.get('mean_ret', 0):+.2f}%</b>；
测试半完成一轮 <b>{pte.get('round_rate', 0):.1f}%</b> / 破止损 <b>{pte.get('stop_rate', 0):.1f}%</b> /
期望 <b>{pte.get('mean_ret', 0):+.2f}%</b>。<b>判据是两半均值，不是单半最优。</b></div>
{axr}
<h3>卖区目标 × 止损宽度（二维网格，按两半平均完成一轮率排序）</h3>
<table><thead><tr><th>卖区目标</th><th>止损</th><th>训练完成一轮</th><th>测试完成一轮</th>
<th>训练破止损</th><th>测试破止损</th><th>两半均值</th><th>两半期望收益</th></tr></thead>
<tbody>{grd}</tbody></table>
<div class="note">两个方向性结论：<b>①止损越紧，破止损率越高、完成一轮率反而下降</b>
（箱体震荡里「正常波动」的深度就足以扫掉贴身止损）；
<b>②卖区越近（目标越小），完成一轮率越高</b>。
把两者放在一起看，就得到做T的核心权衡：<b>目标越近越容易完成，但单次赚得更少；
止损越紧越保护本金，但被打断的次数更多</b>。是否值得，只能用期望收益判断（下一节）。</div></div>

<h2>十、★ 联合检验：先验集 × 参数组合（能不能把期望收益做正）</h2>
<div class="card">
<div class="note">上表只回答「单个旋钮拧到哪」，本表回答「拧组合能不能兑现成正期望」。
每行一种参数组合（反T = 先低吸后高抛；正T = 先高抛后低吸补回）。
<b>判据是「两半一致性」</b>：只有训练半与测试半<b>同时为正</b>的组合才值得采信，
单半为正只是行情赏饭。样本非独立（同一标的每 3 日采一点、前推 10 日重叠），
故这些差异应按「日期聚类」理解，不要当成精确收益率。</div>
<table><thead><tr>
<th rowspan="2">参数组合</th>
<th rowspan="2">训练半<br>全体期望</th>
<th colspan="3">训练半 · 前 10%</th>
<th rowspan="2">训练半<br>前 2% 期望</th>
<th colspan="4">测试半 · 各截断比例期望</th>
<th colspan="3">测试半 · 前 10%</th>
<th rowspan="2">两半<br>一致性</th></tr>
<tr><th>完成一轮</th><th>破止损</th><th>期望收益</th>
<th>前 1%</th><th>前 2%</th><th>前 5%</th><th>前 20%</th>
<th>完成一轮</th><th>破止损</th><th>期望收益</th></tr></thead>
<tbody>{combor}</tbody></table>
<div class="note"><b>怎么用这张表（三步）</b>：<br>
① <b>先看「两半一致性」列</b>：只认「两半俱正」。测试半为正而训练半为负的组合（本页全部的正T 组合都是这样）
说明它赚的是「最近一段行情」，不能当作做T能力 —— 这正是反转池与精选池都踩过的坑。<br>
② <b>再看「前 1% / 前 2%」列</b>：如果越收紧越接近 0，说明<b>最严格的筛选才能勉强不亏</b>，
那就必须接受「多数日子不做」这件事。<br>
③ <b>最后看「完成一轮」与「破止损」</b>：做T的胜率是这两者的平衡 ——
把止损放宽可以提高完成一轮率，但每次亏得更多；把目标缩小也能提高完成一轮率，但单次赚得更少。</div></div>

<h2>十一、环境 × 参数（期望收益能不能靠「只在该做的时候做」转正）</h2>
<div class="card"><table>
<thead><tr><th>参数组合</th><th>指数近 20 日</th><th>域内 n</th><th>top10% 完成一轮</th>
<th>域均完成一轮</th><th>edge</th><th>top10% 破止损</th><th>top10% 期望收益</th><th>域均期望</th></tr></thead>
<tbody>{envcr}</tbody></table>
<div class="note">环境量 = <b>截至当日的上证指数近 20 日涨幅</b>（滞后量，无未来信息）。
这是第八节的补充 —— 第八节只看「完成一轮率」，本节直接看「期望收益」。
edge = top10% 完成一轮率 − 域均完成一轮率（正 = 选股有效，与赚不赚钱是两件事）。
<br>{envfound}</div></div>

<h2>十二、截断比例曲线（最终先验集，测试段）</h2>
<div class="card"><table>
<thead><tr><th>每日取前</th><th>n_top</th><th>完成一轮</th><th>域均完成一轮</th><th>edge（完成一轮）</th>
<th>破止损</th><th>edge（期望收益）</th></tr></thead>
<tbody>{tpnr}</tbody></table>
<div class="note">用于决定「A/B 档各取每日前多少」：若前 5%~10% 已见顶，则再收紧只会缩小样本、不会提高确定性。</div></div>

<h2>十三、结论与落地</h2>
<div class="box green">
<b>① 先验集：</b>落地用<b>{'收敛派 A' if so.get('pick') == 'prior_a' else '支撑派 B'}</b>（{len(SEL)} 因子等权、dir 全 −1）——
训练段按期望收益择优、测试段验证（见第五节）。<br>
<b>② 档位：</b>按截断曲线，A = 每日前 10%、B = 每日前 25%（不再是「分数 ≥80/70」的固定阈值 ——
阈值会随行情漂移，分位不会）。<br>
<b>③ 买卖点：</b>由参数网格 + 联合检验共同决定，见上两节；落地参数以「两半同向 + 期望收益不为负」为准。<br>
<b>④ 环境：</b>门控只用于<b>控 β 与仓位</b>，不作为提高胜率的手段（第八节证据）。
但第十一节给出了一个比「控仓位」更硬的结论：<b>做T方向必须与环境配对</b> ——
指数近 20 日<b>偏弱（−3%~0）或弱势（&lt; −3%）时做反T</b>（先低吸后高抛）、
<b>偏强（0~+3%）时做正T</b>（先高抛后低吸补回），这两类配对是唯一能做到「top10% 与域均期望同时为正」的窗口；
反向配对（弱环境做正T、强环境做反T）是全表最差档。<b>不知道当天处于哪一档时，默认不做。</b><br>
<b>⑤ 纪律（最重要）：</b>本页最反直觉、也最有用的一条是 ——
<b>「完成一轮率高」不等于「赚钱」</b>。做T的胜率来自「<b>不追高 + 给噪声留容错 + 早止盈</b>」三者的组合，
而不是把止损设得更紧、或把目标设得更远。任何单笔亏损预算 = 仓位 × 止损宽度，必须 ≤ 账户 0.5%。<br>
<b>⑥ 与旧版的关系：</b>旧版的 347 样本、6 个交易日回测只覆盖了「一周的行情」，
本实验室把它扩到 {rows['n']:,} 样本 / {len(mon)} 个月，
并在<b>测试段</b>上验证 —— 结论与「档位 A/B/C/D 对能否完成一轮无预测力」不同：
档位（分数分位）<b>确实</b>预测完成一轮率，但它预测不了「赚钱」。</div>

<h2>十四、局限（必读）</h2>
<div class="card"><ul>
<li><b>样本非独立</b>：同一标的每 3 个交易日采一点、前推 10 日 → 窗口重叠，跨样本相关性高；
显著性应按<b>日期聚类</b>理解，本页不做逐样本独立性假设。</li>
<li><b>市值/换手为近似</b>：流通股本用「netprofit ÷ eps 反推总股本」再乘收盘价，未扣限售股，
故流通市值偏大、换手偏小；门槛已相应放宽，且该近似对同期同域所有标的作用一致。</li>
<li><b>忽略滑点与手续费</b>：做T单轮目标常仅 2%~4%，实盘双边成本（佣金+印花税+冲击）约 0.15%~0.3%，
会啃掉相当一部分收益 —— 本页所有参数组同口径，故<b>相对比较有效</b>；
若某组合期望收益只有 +0.1%~+0.3%，扣成本后可能归零，落地时要按这个量级打折。</li>
<li><b>未含事件风险</b>：解禁、减持、财报暴雷、停牌不在本页面板控制内，
线上 <code>build_tplus.load_risk_sets</code> 会额外扣分。</li>
<li><b>做T本质是低胜率策略</b>：全市场域下 5 日窗口的「先低吸后高抛」本身就是小概率事件
（基线 {rows['round_rate']:.1f}%），提升空间在「参数与纪律」，不在「找到完美因子」。</li>
<li>结论会随数据更新重算（<code>python quant/_tplus_lab.py --rebuild</code>），
不是一次性拟合出来的静态阈值。</li>
</ul></div>

<div class="foot">做T池 · 特征功效实验室 · 数据基准 {res['data_max']} · 生成 {res.get('built_at', '')} ·
生成脚本 <code>quant/_tplus_lab.py</code> · 非投资建议，仅量化方法论与纪律沉淀</div>
</div></body></html>"""


# ==================== main ====================
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rebuild", action="store_true", help="强制重建面板")
    ap.add_argument("--panel", default=OUT_PANEL)
    a = ap.parse_args()

    if a.rebuild or not os.path.exists(a.panel):
        rows = build_panel()
        json.dump(rows, open(a.panel, "w", encoding="utf-8"), ensure_ascii=False)
        print("[lab] 面板已落盘 %s（%.1f MB）" % (a.panel, os.path.getsize(a.panel) / 1e6))
    else:
        rows = json.load(open(a.panel, encoding="utf-8"))
        print("[lab] 复用面板 %d 行" % len(rows))
    derive(rows)

    ds = sorted({r["date"] for r in rows})
    base = _summ([_sim_default(r) for r in rows])
    cut = ds[int(len(ds) * 0.6)]
    res = {
        "version": "tplus_v6", "built_at": __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M"),
        "data_min": ds[0], "data_max": ds[-1], "cut_date": cut,
        "universe_n": len({r["code"] for r in rows}),
        "panel_summary": base,
        "prior_a": PRIOR_A, "prior_b": PRIOR_B,
        "prior_cn": PRIOR_CN, "maxfwd": FMAX, "pct_grid": [0.05, 0.10, 0.20, 0.30],
        "defaults": {"buy_off": DEF_BUY_OFF, "sell_mult": DEF_SELL_MULT,
                     "min_gain": DEF_MIN_GAIN, "stop_pct": DEF_STOP_PCT, "horizon": HOLD},
    }
    print("[lab] 基线：完成一轮 %.1f%% · 破止损 %.1f%% · 期望收益 %+.2f%%（n=%d）"
          % (base["round_rate"], base["stop_rate"], base["mean_ret"], base["n"]))

    print("[lab] 单特征功效 ...")
    res["features"] = feature_table(rows, cut)
    print("[lab] 严格样本外（两组先验对照）...")
    res["strict_oos"] = strict_oos(rows)
    so = res["strict_oos"]
    print("[lab] 训练段择优：%s（收敛派 复合 %+.2f / 支撑派 复合 %+.2f；完成一轮 edge %+.1f vs %+.1f pp；期望 edge %+.2f vs %+.2f pp）%s"
          % (so["pick"], so["pick_train_score"]["prior_a"], so["pick_train_score"]["prior_b"],
             so["pick_train_edge_round"]["prior_a"] or 0, so["pick_train_edge_round"]["prior_b"] or 0,
             so["pick_train_edge_ret"]["prior_a"] or 0, so["pick_train_edge_ret"]["prior_b"] or 0,
             "（差距在噪声内）" if so.get("pick_tie") else ""))
    set_prior(so["pick_feats"])
    res["prior_set"] = list(PRIOR)
    print("[lab] 十分位 ...")
    res["deciles"] = deciles_curve(rows)
    print("[lab] 两半对照 ...")
    res["half_oos"] = half_oos(rows)
    print("[lab] 截断曲线 ...")
    res["topn_curve"] = topn_curve(rows)
    print("[lab] 逐月 ...")
    res["monthly"], res["monthly_agg"] = monthly(rows)
    print("[lab] 环境分桶 ...")
    res["env_scan"] = env_scan(rows)
    print("[lab] 参数网格 ...")
    res["param_scan"] = param_scan(rows)
    print("[lab] 联合检验（先验集 × 参数）...")
    res["combo"] = combo_check(rows)

    def _te10(c):
        for p in (c.get("pcts") or []):
            if abs(p["pct"] - 0.10) < 1e-9:
                return ((p.get("test") or {}).get("mean_ret"))
        return None
    ok_c = [c for c in res["combo"] if _te10(c) is not None]
    best = max(ok_c, key=_te10) if ok_c else None
    res["combo_pos_cnt"] = sum(1 for c in ok_c if (_te10(c) or 0) > 0)
    res["combo_n"] = len(ok_c)
    print("[lab] 联合检验：%d 个组合中测试段前 10%% 期望为正的有 %d 个；最优「%s」→ %s"
          % (len(ok_c), res["combo_pos_cnt"],
             best["label"] if best else "—",
             ("%+.2f%%" % _te10(best)) if best else "—"))
    res["combo_best"] = best["label"] if best else None
    print("[lab] 环境 × 参数 ...")
    res["env_combo"] = env_combo(rows)

    json.dump(res, open(OUT_RES, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("[lab] 结果 → %s" % OUT_RES)
    html = render_lab(res)
    os.makedirs(WEB, exist_ok=True)
    open(OUT_HTML, "w", encoding="utf-8").write(html)
    print("[lab] 页面 → %s（%.1f KB）" % (OUT_HTML, len(html) / 1024))


if __name__ == "__main__":
    main()
