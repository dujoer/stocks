# -*- coding: utf-8 -*-
"""底部反转观察池 · v6（阶段底部锚定 ＋ 回升启动确认 ＋ 本轮回撤目标）。

v6 相对 v5 的三处结构性改动（依据见走前消融 quant/_rbot_ablate.py，页面每日实算）：

  1. **从「跌得多」改为「确认在阶段底部区域」**。v5 的域只看「距 52 周高回撤 ≥18%」，
     那只是跌得多，可以是下跌中继（仍在创新低），也可以已经反弹一大截（追高）。
     v6 先识别**本轮下跌段**（最近一个显著高点 → 谷底），再要求：
        · 已止跌（谷底形成 ≥4 个交易日，且期间不再创新低）；
        · 位置仍在底部区（现价距谷底 ≤15%）；
        · 本轮跌幅 ≥30%（跌得够透才有回补空间）。
     并且谷底 / 平台上沿**锚定**写盘（quant/rev/bottom_state.json）：数值一旦确立就锁死，
     只有「破底 / 远离 / 超期」才重算并升版本号 —— 上下沿不随行情天天漂。
  2. **要求「回升启动证据」≥2 条**（即将回升）：站上 MA10 / MA10 上翘 / MACD 金叉或底背离 /
     量能放大 / 突破平台上沿 / 20 日主力净流入。这是本次唯一在**两半样本外都稳定为正**
     的条件（相对各自半区基线 前半 +2.3pp / 后半 +8.3pp）。
  3. **目标位改按本轮下跌段回撤**，不再用「52 周高回撤 0.382/0.618」——那是自半年高点算起的
     天价目标，几乎不可兑现。新目标：T1 = 谷底 + 本轮跌幅×0.382，T2 = 谷底 + 本轮跌幅×0.618，
     并给出最近的真实阻力「平台上沿」。

⚠️ 消融中被证伪、因此**没有采用**的两条先验（如实记录，避免以后又捡回来）：
  · 「谷底触碰次数 ≥2 天」：前后半 −0.7pp / −1.0pp（**负贡献**），已降级为展示信息，不作门槛；
  · 「必须限定在距谷底 ≤15%」单独用也是负的（−2.5pp / −0.8pp），
    只有在叠加「启动证据≥2 ＋ 跌幅≥30%」之后，整套组合才翻正（+2.3pp / +8.3pp）。
    换句话说：**位置约束本身不产生胜率，它必须与「已经要回升」的证据同时出现才有意义**。

排序仍用 v5 的先验固定因子集横向分位（qs），档位仍按域内分位；
最终展示只保留「通过全部新闸门 且 qs 属域内前 {A_PCT:.0%}」的交集 —— 参考票不再列表。

同时明确两件**不做**的事：
  · 不用环境状态预判 alpha。实测六类日级状态量在训练半/测试半方向全部相反，
    `env_coefficient` 只用来给**总暴露（β）**一个仓位系数，不改变选股排序；
  · 不给「确认类」信号加分（收复 MA20 / 短均线多头排列等在相对胜率上是负向）。

A 档 = 域内组合分前 10%（绝对名次会随域大小漂移，仅作参考列）；B = 10~25%；C 不出。
每票给买区（MA10/MA20 回踩）、止损（跌破近 20 日基底）、目标（52 周高回撤 0.382/0.618）。

数据源：腾讯前复权日K（离线 _tx_fetch 缓存，全市场缓存见 quant/fetch_full_kline.py）。
基本面/流通市值用 _rev_enrich 快照（仅选股日生效）；资金流走腾讯+新浪离线。
"""
from __future__ import annotations
import os, sys, json, math, datetime, argparse, statistics
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _tx_fetch as T
import _xhist as X
import _exit_sim as _EXITSIM      # 移动止盈单一口径（本文件不再自持实现）
import _idxkline as E
import _emlink as EM
import _rbot as RB          # 阶段底部锚定引擎（谷底/平台上沿/本轮回撤目标）
from _nav import topnav

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QUANT = os.path.join(ROOT, "quant")
OUTDIR = os.path.join(ROOT, "web", "reversal")
os.makedirs(OUTDIR, exist_ok=True)

SEED_DATE = "2026-09-18"
SEED_FILE = os.path.join(QUANT, f"_rev_seed_raw_{SEED_DATE.replace('-','')}.json")
QUOTE_FILE = os.path.join(QUANT, f"_rev_quote_{SEED_DATE.replace('-','')}.json")


# ---------------- 指标 ----------------
def ema(a, n):
    if not a:
        return []
    k = 2.0 / (n + 1)
    out = [a[0]]
    for x in a[1:]:
        out.append(x * k + out[-1] * (1 - k))
    return out


def macd_series(closes):
    ef, es = ema(closes, 12), ema(closes, 26)
    dif = [a - b for a, b in zip(ef, es)]
    dea = ema(dif, 9)
    return dif, dea


def rsi_series(closes, n=14):
    out = [50.0] * len(closes)
    for i in range(1, len(closes)):
        g = l = 0.0
        for j in range(max(1, i - n + 1), i + 1):
            d = closes[j] - closes[j - 1]
            if d >= 0:
                g += d
            else:
                l -= d
        out[i] = 100.0 if l == 0 else (100 - 100 / (1 + g / l))
    return out


def _ma(arr, n):
    return sum(arr[-n:]) / n if len(arr) >= n else None


def _valleys(closes, lo, hi):
    v = []
    for i in range(max(1, lo + 1), min(hi, len(closes) - 1)):
        if closes[i] <= closes[i - 1] and closes[i] <= closes[i + 1]:
            v.append(i)
    return v


def bullish_divergence(closes, dif, window=60):
    """价格创新低而 MACD(DIF)未创新低 → 底背离。返回 (bool, detail)。"""
    if len(closes) < window:
        return False, "窗口不足"
    seg = closes[-window:]
    lv = _valleys(closes, len(closes) - window, len(closes) - 1)
    if len(lv) < 2:
        # 退一步：取窗口内最低价位置与次低
        idx_min = len(closes) - window + seg.index(min(seg))
        # 找更早一个明显低点
        earlier = min(closes[:idx_min]) if idx_min > 5 else None
        if earlier is None:
            return False, "无双底"
        return (False, "单底")
    v1, v2 = lv[-2], lv[-1]  # 早 / 晚
    p1, p2 = closes[v1], closes[v2]
    d1, d2 = dif[v1], dif[v2]
    if p2 <= p1 * 1.02 and d2 > d1:
        return True, "价格新低·DIF 抬高"
    if p2 <= p1 * 1.02 and d2 > d1 - abs(d1) * 0.1:
        return "weak", "价格新低·DIF 走平"
    return False, "无背离(价格新低·DIF 同步新低)"


def evaluate(kasc, idx=None, info=None, gate_fund=False, code=None, bot=None):
    """在 kasc[:idx+1] 处评估反转信号。返回 dict。

    gate_fund=False（v5 默认）：不施加「0<PE<50 & 市值<100亿」的基本面地板 —— 全市场域下
    估值与市值改由横截面因子承担（见 `_rev_lab.py` PRIOR_SET 的 mv_log）。
    """
    n = len(kasc)
    if idx is None:
        idx = n - 1
    if idx < 60:
        return {"ok": False, "reason": "K线不足60"}
    closes = [x["last"] for x in kasc[:idx + 1]]
    highs = [x["high"] for x in kasc[:idx + 1]]
    lows = [x["low"] for x in kasc[:idx + 1]]
    vols = [x["volume"] for x in kasc[:idx + 1]]
    opens = [x["open"] for x in kasc[:idx + 1]]
    L = len(closes)
    close = closes[-1]

    h52 = max(highs)
    l52 = min(lows)
    dist52 = (close - h52) / h52 * 100 if h52 else 0
    ytd = (close - closes[0]) / closes[0] * 100 if closes[0] else 0

    ma5, ma10, ma20, ma60 = _ma(closes, 5), _ma(closes, 10), _ma(closes, 20), _ma(closes, 60)
    ma20_prev = _ma(closes[:L - 5], 20) if L > 25 else None
    slope = (ma20 - ma20_prev) / ma20_prev * 100 if (ma20 and ma20_prev) else 0.0

    # 量能
    v20 = sum(vols[-20:]) / 20
    v60 = sum(vols[-60:]) / 60 if L >= 60 else v20
    vol_dry = v20 / v60 if v60 else 1.0
    accum = sum(1 for i in range(L - 20, L)
                if closes[i] > opens[i] and vols[i] > v60 * 1.2)
    v5 = sum(vols[-5:]) / 5
    v15 = sum(vols[-20:-5]) / 15 if L >= 20 else v20
    vol_expand = v5 / v15 if v15 else 1.0

    # 背离
    dif, dea = macd_series(closes)
    div, div_txt = bullish_divergence(closes, dif, window=60)
    golden = dif[-1] > dea[-1]

    reclaim = ma20 is not None and close > ma20
    short_align = (ma5 and ma10 and ma20) and (ma5 > ma10 > ma20)
    base_low20 = min(lows[-20:]) if L >= 20 else min(lows)
    # 筑底确认：近10日最低未跌破近20日基底（不再创新低）
    bottom_confirm = min(lows[-10:]) >= base_low20 * 0.985 if L >= 10 else False

    # ---- v4 新增特征（均由 _rev_lab.py 样本外实证入选，见 lab.html） ----
    lo60 = min(lows[-60:]) if L >= 60 else min(lows)
    dist_lo20 = (close / base_low20 - 1) * 100 if base_low20 else 0.0
    dist_lo60 = (close / lo60 - 1) * 100 if lo60 else 0.0
    gap_lo52 = (close - l52) / l52 * 100 if l52 else 0.0
    trs = []
    for t in range(max(1, L - 20), L):
        trs.append(max(highs[t] - lows[t], abs(highs[t] - closes[t - 1]), abs(lows[t] - closes[t - 1])))
    atr20 = sum(trs) / len(trs) if trs else 0.0
    atr_pct = atr20 / close * 100 if close else 0.0
    range20 = (max(highs[-20:]) - min(lows[-20:])) / close * 100 if close else 0.0
    ma60_dev = (close - ma60) / ma60 * 100 if ma60 else 0.0

    # 跌幅成熟度：自52周高至今的交易日数
    hi_idx = highs.index(h52)
    decline_dur = L - 1 - hi_idx

    # ---- 评分 ----
    def band_val(x, a, b, lo, hi, mx):
        if x is None:
            return 0.0
        if a <= x <= b:
            return float(mx)
        if x < a:
            return float(mx) * (x - lo) / (a - lo) if a > lo else 0.0
        return float(mx) * (hi - x) / (hi - b) if hi > b else 0.0

    s_depth = band_val(dist52, -45, -25, -10, -5, 22)
    s_mat = 12.0 if decline_dur >= 60 else (9.0 if decline_dur >= 40 else (5.0 if decline_dur >= 25 else 2.0))
    s_dry = band_val(vol_dry, 0.55, 0.8, 0.95, 1.15, 14)
    s_acc = 14.0 if accum >= 6 else (9.0 if accum >= 4 else (4.0 if accum >= 2 else 0.0))
    s_div = 18.0 if div is True else (10.0 if div == "weak" else 0.0)
    s_ma = 0.0
    if reclaim and slope > 0 and short_align:
        s_ma = 20.0
    elif reclaim and slope > 0:
        s_ma = 15.0
    elif reclaim:
        s_ma = 10.0
    elif slope > 0:
        s_ma = 6.0
    total = round(s_depth + s_mat + s_dry + s_acc + s_div + s_ma, 1)

    # 基本面地板（旧 v4 种子口径：只在 gate_fund=True 且 info 提供时生效）
    # v5 全市场版**不启用**：PE / 市值 从硬门槛改为横截面因子（见 _rev_lab.py PRIOR_SET）。
    fund_ok = True
    fund_note = ""
    if gate_fund and info:
        pe = info.get("pe")
        cmv = info.get("circ_mv")
        nm = info.get("name") or ""
        if "ST" in nm or "退" in nm:
            fund_ok = False
            fund_note = "ST/退市"
        elif pe is None or not (0 < pe < 50):
            fund_ok = False
            fund_note = "PE 越界"
        elif cmv is None or cmv > 100:
            fund_ok = False
            fund_note = "市值越界"

    # 硬门槛（加 MA60 护栏：仍在深度长期下行 = 飞刀风险，剔除）
    hard = (dist52 <= -18 and (not gate_fund or not info or fund_ok)
            and (ma60 is None or close >= ma60 * 0.75))

    # 档位（按回测实证校准，v3 walk-forward 952 信号）：
    #  ⚠️ 过度确认陷阱：要求「底背离+收复+放量+筑底」同时成立 → 选中已反弹充分的票，
    #     A 档 +20日胜率仅 36.8%（差于基线 48.3%）。故该组合不设为买点档。
    #  ✅ 高胜率组合（回测 58.8% vs 基线 48.3%，+10.5pp，样本 933）：
    #     底背离/弱背离/收复其一 ＋ 量能枯竭(≤0.95) ＋ 吸筹(≥2日)或金叉
    #  → 设为 A 档（主买点）；B 档为更松的次级确认。
    if not hard:
        tier = "C"
    elif (total >= 50 and (div is True or div == "weak" or reclaim)
          and vol_dry <= 0.95 and (accum >= 2 or golden)):
        tier = "A"
    elif (total >= 45 and (div is True or div == "weak" or reclaim)
          and vol_dry <= 1.05):
        tier = "B"
    else:
        tier = "C"

    # 买卖点
    mids = [x for x in (ma5, ma10, ma20) if x]
    if mids:
        entry_lo = min(mids) * 0.99
        entry_hi = max(mids) * 1.01
    else:
        entry_lo, entry_hi = close * 0.96, close * 1.0
    if close > entry_hi:  # 已远离，等回踩
        entry_lo, entry_hi = (ma20 * 0.98 if ma20 else close * 0.97), (ma20 * 1.02 if ma20 else close * 1.0)
    # v6：有了锚定的谷底，止损就用**结构位**（跌破谷底 3% = 底部结构失效），
    # 而不是近 20 日基底 —— 后者在深度回踩后会把止损抬得太高，被日常波动扫出去。
    stop = base_low20 * 0.97
    if bot and bot.get("trough"):
        stop = bot["trough"] * 0.97
    stop_pct = (stop - close) / close * 100 if close else 0
    if bot and bot.get("leg_high"):
        tg = RB.targets(bot) or {}
        t1, t2 = tg.get("t1") or close, tg.get("t2") or close
    else:
        t1 = entry_hi + (h52 - entry_hi) * 0.382
        t2 = entry_hi + (h52 - entry_hi) * 0.618
    risk = (entry_hi - stop) / entry_hi * 100 if entry_hi else 0
    reward = (t1 - entry_hi) / entry_hi * 100 if entry_hi else 0
    rr = (reward / abs(risk)) if risk else 0

    factors = {
        "dist52": round(dist52, 1), "ytd": round(ytd, 1), "decline_dur": decline_dur,
        "vol_dry": round(vol_dry, 2), "accum": accum, "vol_expand": round(vol_expand, 2),
        "div": div, "div_txt": div_txt, "golden": golden,
        "reclaim": reclaim, "short_align": short_align, "slope": round(slope, 2),
        "bottom_confirm": bottom_confirm, "ma20": round(ma20, 2) if ma20 else None,
        "ma60": round(ma60, 2) if ma60 else None,
        "dist_lo20": round(dist_lo20, 1), "dist_lo60": round(dist_lo60, 1),
        "gap_lo52": round(gap_lo52, 1), "atr_pct": round(atr_pct, 2),
        "range20": round(range20, 1), "ma60_dev": round(ma60_dev, 1),
    }
    # v5 规模因子：总市值（腾讯快照优先；缺失时用「股本反推 × 收盘」兜底）
    tmv = (info or {}).get("total_mv")
    if not tmv and code:
        _sh = _shares_cached().get(code)
        tmv = (close * _sh / 1e8) if _sh else None
    factors["mv_log"] = (round(math.log(tmv * 1e8), 4) if (tmv and tmv > 0) else None)
    score_detail = {"结构深度": s_depth, "跌幅成熟": s_mat, "量能枯竭": s_dry,
                    "吸筹": s_acc, "背离": s_div, "均线排列": s_ma}

    return {"ok": True, "hard": hard, "tier": tier, "score": total, "close": close,
            "factors": factors, "score_detail": score_detail,
            "entry_lo": round(entry_lo, 2), "entry_hi": round(entry_hi, 2),
            "stop": round(stop, 2), "stop_pct": round(stop_pct, 1),
        "t1": round(t1, 2), "t2": round(t2, 2),
        "risk": round(risk, 1), "reward": round(reward, 1), "rr": round(rr, 2),
        "h52": round(h52, 2), "l52": round(l52, 2),
        "bot": bot, "fund_ok": fund_ok, "fund_note": fund_note, "ma5": ma5, "ma10": ma10}


# ---------------- v5 全市场域（2026-09-21 起反转池改全市场） ----------------
NAME_FILE = os.path.join(QUANT, "_stock_names.json")
FIN_SNAP = os.path.join(QUANT, "fin", "snapshot.json")
AMT_MIN = 3.0e7        # 20 日均成交额下限（元）—— 与 _rev_lab.py 保持一致
# 档位 = 域内组合分分位（不是绝对名次）：实验室截断曲线显示前 5%~10% 见顶
# （前5% +16.3pp / 前10% +16.4pp / 前15% +15.0pp / 前20% +14.0pp），故 A 取前 10%。
# 绝对名次在域扩张到 4000+ 只后会严重失真，已弃用。
A_PCT = 0.10           # A 档 = 域内组合分前 10%
B_PCT = 0.25           # B 档 = 10% ~ 25%
TOP_SHOW = 220         # 页面表格展示上限（全市场域下总表可达上千行）

# ---- v6：阶段底部闸门参数（先验固定，由 _rbot_ablate.py 走前消融给出，勿手调）----
MIN_LEG_FALL = 30.0    # 本轮下跌段最小跌幅 %（两半 +1.3 / +2.4pp）
LIFT_MIN     = 2       # 回升启动证据最少条数（两半 +2.0 / +6.4pp，单条最强）
MAX_RISE     = RB.MAX_RISE   # 距谷底上限 %（叠加上面两条后，整套组合 +2.3 / +8.3pp）
WF_SAMPLE    = 700     # 页面「走前验证」每日实算的抽样股票数（算力/稳定性折中）



def _name_map():
    try:
        return json.load(open(NAME_FILE, encoding="utf-8"))
    except Exception:
        return {}


def _shares_map():
    """股本反推（netprofit ÷ eps）—— 腾讯快照缺总市值时的兜底。"""
    try:
        snap = json.load(open(FIN_SNAP, encoding="utf-8")).get("stocks", {})
    except Exception:
        return {}
    out = {}
    for c, v in snap.items():
        npf, eps = v.get("netprofit"), v.get("eps")
        if npf and eps and eps > 0:
            out[c] = npf / eps
    return out


_SH_CACHE = None


def _shares_cached():
    global _SH_CACHE
    if _SH_CACHE is None:
        _SH_CACHE = _shares_map()
    return _SH_CACHE


def _amt20(bars, code, win=20):
    """20 日均成交额（元，统一口径）。"""
    u = T.vol_unit(code)
    seg = bars[-win:] if len(bars) >= win else bars
    if not seg:
        return 0.0
    return sum(b["volume"] * u * b["last"] for b in seg) / len(seg)


def load_universe_full(date=None):
    """v5 全市场域：腾讯日K缓存里的全部 A 股正股，剔除 ST/退 与流动性不足。

    旧机制只覆盖 westock 条件选股（净利同比>50 & 0<PE<50 & 市值<100亿）的约 220 只，
    横截面排序的域太窄；v5 改为全市场，市值/估值改作**因子**而非硬门槛。

    返回 (codes, names, 统计 dict)。
    """
    cache = T._load()
    nm = _name_map()
    codes, names = [], {}
    st = liq = short = 0
    for c in cache:
        if not (c.startswith("sh6") or c.startswith("sz0") or c.startswith("sz3")):
            continue                       # 仅 A 股正股（排转债/ETF/指数/北交所）
        bars = cache[c]
        if len(bars) < 70:
            short += 1
            continue
        n = nm.get(c) or ""
        if "ST" in n or "退" in n:
            st += 1
            continue
        if _amt20(bars, c) < AMT_MIN:
            liq += 1
            continue
        codes.append(c)
        names[c] = n or c
    codes.sort()
    stat = {"st": st, "illiquid": liq, "short": short, "total": len(codes)}
    print("[rev_pool] v5 全市场域 %d 只（剔 ST/退 %d · 流动性不足 %d · K线不足 %d）"
          % (len(codes), st, liq, short))
    return codes, names, stat


def full_quote_sweep(codes, date, use_cache=True):
    """全市场腾讯快照（名称/PE/PB/总市值/流通市值/换手/52 周高低）→ _rev_quote_full_{dc}.json。

    离线优先：当日已拉过就直接复用，避免每天重复 63 次请求。
    """
    dc = str(date).replace("-", "")
    p = os.path.join(QUANT, "_rev_quote_full_%s.json" % dc)
    if use_cache and os.path.exists(p):
        try:
            d = json.load(open(p, encoding="utf-8"))
            q = d.get("quote") or {}
            if len(q) >= len(codes) * 0.9:
                print("[rev_pool] 复用全市场快照 %d 只（%s）" % (len(q), os.path.basename(p)))
                return q
        except Exception:
            pass
    raw = T.fetch_qt(codes, batch=80)
    out = {}
    for c in codes:
        v = raw.get(c)
        if not v:
            continue
        out[c] = {"name": v.get("name"), "pe": v.get("pe_ratio"), "pb": v.get("pb_ratio"),
                  "total_mv": v.get("total_market_cap"), "circ_mv": v.get("circulating_market_cap"),
                  "turn": v.get("turnover_rate"), "last": v.get("last"),
                  "h52": v.get("high_52week"), "l52": v.get("low_52week")}
    json.dump({"data_date": date, "n_codes": len(codes), "quote": out},
              open(p, "w", encoding="utf-8"), ensure_ascii=False)
    print("[rev_pool] 全市场快照 %d/%d → %s" % (len(out), len(codes), os.path.basename(p)))
    return out


def load_universe(date=None):
    """种子（条件选股结果）+ 名称表。

    ⚠️ 种子文件里的 `stocks` 每项都带 name（如 {"code":"sz301680","name":"固德电材"}），
    但旧实现只取了 code，导致页面名称列回退成「sz000049」这种代码。这里把名称一并带出。
    """
    dc = (date or SEED_DATE).replace("-", "")
    seed_file = os.path.join(QUANT, "_rev_seed_raw_%s.json" % dc)
    if not os.path.exists(seed_file):
        seed_file = SEED_FILE
    s = json.load(open(seed_file, encoding="utf-8"))["data"]
    stocks = s.get("stocks", [])
    q = {}
    if os.path.exists(QUOTE_FILE):
        q = json.load(open(QUOTE_FILE, encoding="utf-8"))["data"]
    codes = [x["code"] for x in stocks]
    names = {x["code"]: x.get("name") for x in stocks if x.get("name")}
    return codes, q, s.get("totalStocks", len(codes)), names


# ---------------- 名称 / 流通市值 / PE / 主力资金 补全 ----------------
ENRICH_CACHE = {}


def load_enrich(date):
    """读 quant/rev_enrich_{dc}.json（由 fetch_rev_enrich.py 产出）。缺失返回空。"""
    dc = str(date).replace("-", "")
    if dc in ENRICH_CACHE:
        return ENRICH_CACHE[dc]
    p = os.path.join(QUANT, "rev_enrich_%s.json" % dc)
    d = {"quote": {}, "flow": {}, "flow_src": None}
    if os.path.exists(p):
        try:
            d = json.load(open(p, encoding="utf-8"))
        except Exception:
            pass
    ENRICH_CACHE[dc] = d
    return d


def fetch_klines(codes, n=250):
    kl = {}
    with ThreadPoolExecutor(max_workers=8) as ex:
        for c, k in ex.map(lambda c: (c, T.fetch_kline(c, n)), codes):
            if k:
                kl[c] = k
    return kl


# ---------------- v5 组合模型（全市场横截面分位排序 · 先验固定因子集） ----------------
MODEL_FILE = os.path.join(QUANT, "_rev_model.json")
# 兜底：模型文件缺失时用内置先验固定集（来源 quant/_rev_lab.py，方向由经济逻辑给定，勿手改）
MODEL_FALLBACK = {"dist_lo20": -1, "dist_lo60": -1, "gap_lo52": -1, "vol_dry": -1,
                  "atr_pct": -1, "range20": -1, "ma60_dev": -1, "slope": -1, "mv_log": -1}


def load_model():
    """读 _rev_lab.py 冻结的模型（特征 + 方向）。返回 (dict, meta)。"""
    try:
        m = json.load(open(MODEL_FILE, encoding="utf-8"))
        d = {f["name"]: f["dir"] for f in m.get("features", [])}
        if len(d) >= 3:
            return d, m
    except Exception:
        pass
    return dict(MODEL_FALLBACK), {}


def score_pool(items, model):
    """日内横截面分位排序 → 组合分 qs(0~1，越高越好)。qs 只在本批候选内可比。"""
    keys = list(model)
    ranks = [dict() for _ in items]
    for k in keys:
        pairs = sorted([(it["factors"].get(k), i) for i, it in enumerate(items)
                        if it["factors"].get(k) is not None])
        m = len(pairs)
        if m < 5:
            continue
        for pos, (v, i) in enumerate(pairs):
            ranks[i][k] = pos / (m - 1)
    for i, it in enumerate(items):
        rk = ranks[i]
        if not rk:
            it["qs"] = None
            it["qcov"] = 0
            continue
        used = [k for k in keys if k in rk]
        s = sum((rk[k] if model[k] > 0 else 1 - rk[k]) for k in used)
        it["qs"] = round(s / len(used) * 100, 1)      # 0~100 分位分
        it["qcov"] = len(used)
    return items


def assign_tiers(items, a_pct=A_PCT, b_pct=B_PCT):
    """v5 档位 = 域内组合分**分位**（仅硬门槛内参与排序）：

    A = 域内前 a_pct（默认 10%）  B = a_pct ~ b_pct（默认 10~25%）  C = 其余
    为什么用分位而不是绝对名次：实验室截断曲线显示边缘在前 5%~10% 见顶，
    属于「比例」性质；域从 220 只扩到 4000+ 只后，绝对名次（如前 30 名）会变得过窄。
    """
    hard = [it for it in items if it.get("hard") and it.get("qs") is not None]
    hard.sort(key=lambda x: -x["qs"])
    n = len(hard)
    ia = int(round(n * a_pct))
    ib = int(round(n * b_pct))
    for i, it in enumerate(hard):
        it["tier"] = "A" if i < ia else ("B" if i < ib else "C")
        it["qrank"] = i + 1
    for it in items:
        if it not in hard:
            it["tier"] = "C"
            it["qrank"] = None
    return {"A": sum(1 for x in items if x["tier"] == "A"),
            "B": sum(1 for x in items if x["tier"] == "B"),
            "C": sum(1 for x in items if x["tier"] == "C"),
            "hard": n,
            "a_pct": a_pct, "b_pct": b_pct,
            "a_cut": (hard[ia - 1]["qs"] if ia and n else None),
            "b_cut": (hard[ib - 1]["qs"] if ib and n else None)}


def env_coefficient(mstate):
    """环境门控 → 仓位系数（分档阈值来自 quant/_rev_lab.py regime_gate 的样本外分桶）。

    广度 = 全市场站上 MA20 的占比：<35% 防守(0.4) / 35~55% 中性(0.7) / ≥55% 进攻(1.0)。
    """
    br = (mstate or {}).get("breadth")
    if br is None:
        return {"coef": 0.5, "label": "未知", "advice": "环境数据缺失，按半仓对待"}
    if br < 35:
        return {"coef": 0.4, "label": "防守", "advice": "广度低、反转信号易失效：只做 A 档且降至四成仓，或空仓等广度回升"}
    if br < 55:
        return {"coef": 0.7, "label": "中性", "advice": "广度中性：只做 A 档，按买卖点纪律执行，不追高、不摊平"}
    return {"coef": 1.0, "label": "进攻", "advice": "广度高：A 档可满仓执行，B 档可小仓试单"}


def market_state(kl):
    """日级市场状态（只用当日及之前信息）：宇宙中位 20 日收益 + 广度(close>MA20 占比)。"""
    rets, above, tot = [], 0, 0
    for _c, k in kl.items():
        if not k or len(k) < 21:
            continue
        last, prev = k[-1]["last"], k[-21]["last"]
        if not last or not prev:
            continue
        rets.append(last / prev - 1)
        ma20 = sum(x["last"] for x in k[-20:]) / 20
        tot += 1
        if last > ma20:
            above += 1
    if not rets or not tot:
        return {"mkt20": None, "breadth": None, "label": "未知"}
    mkt20 = statistics.median(rets) * 100
    breadth = above / tot * 100
    if breadth >= 55 and mkt20 > 1:
        lab = "偏强"
    elif breadth < 30 or mkt20 < -4:
        lab = "弱势"
    else:
        lab = "中性"
    return {"mkt20": round(mkt20, 1), "breadth": round(breadth, 1), "label": lab}


# ---------------- 选股日运行 ----------------
def run(date, full=True):
    """选股日运行。

    v5（默认，full=True）：**全市场域** —— 宇宙 = 腾讯日K缓存全部 A 股正股，
    剔除 ST/退 与 20 日均额 <3000 万；在域内用**先验固定因子集**做横截面分位排序，
    A 档取前 A_N 名；并按日级广度给仓位系数（环境门控）。
    """
    ustat = {}
    if full:
        codes, names, ustat = load_universe_full(date)
        qm = full_quote_sweep(codes, date)
        seed_n = len(codes)
    else:
        codes, qm, seed_n, names = load_universe(date)
    enrich = load_enrich(date)
    eq, ef = enrich.get("quote") or {}, enrich.get("flow") or {}
    cache = T._load()
    kl = {c: cache[c] for c in codes if c in cache}
    print("[rev_pool] 日K命中 %d/%d｜补全数据：名称/行情 %d 只、主力资金 %d 只"
          % (len(kl), len(codes), len(eq), len(ef)))

    # ---- v6：阶段底部锚定（state 每日写一次，避免逐只落盘） ----
    boxes = RB.load_state()
    bot_drop, n_hard = {}, 0
    out = []
    for code in codes:
        k = kl.get(code)
        if not k or len(k) < 60:
            continue
        info = qm.get(code) or {}
        e = eq.get(code) or {}
        f = ef.get(code) or {}
        nm = info.get("name") or names.get(code) or e.get("name") or code
        pe = e.get("pe") if e.get("pe") is not None else info.get("pe")
        cmv = e.get("circ_mv") if e.get("circ_mv") is not None else info.get("circ_mv")
        inf = {"pe": pe, "circ_mv": cmv, "name": nm, "total_mv": info.get("total_mv")}
        # —— 新第一道闸：阶段底部区 + 启动证据（位置必须先站住，且已经在回升）——
        # 谷底/平台上沿取自锚定状态（一旦确立就锁死，只有破底/远离/超期才重算）
        b = RB.anchor(code, k, date, boxes, save=False)
        why = ""
        if b is None:
            why = "未识别出可靠的本轮下跌结构"
        elif b["stage"] == "下跌中":
            why = "仍在创新低（未止跌）"
        elif b["stage"] == "已脱离":
            why = "已距谷底反弹 >%.0f%%（属追高）" % MAX_RISE
        elif b["fall"] > -MIN_LEG_FALL:
            why = "本轮跌幅不足 %.0f%%" % MIN_LEG_FALL
        nl, hits = 0, []
        if not why:
            nl, hits = RB.lift_signals(k, b)
            if nl < LIFT_MIN:
                why = "回升启动证据仅 %d 条（需 ≥%d 条）" % (nl, LIFT_MIN)
        _key = why.split("%")[0].split("（")[0] if why else ""
        if why:
            bot_drop[_key] = bot_drop.get(_key, 0) + 1
        r = evaluate(k, None, inf, code=code, bot=(dict(b) if b else None))
        if not r["ok"] or not r["hard"]:
            continue
        n_hard += 1
        out.append({
            "code": code.replace("sh", "").replace("sz", "").replace("bj", ""),
            "_full": code, "name": nm,
            "pe": pe, "pb": info.get("pb"), "float_mv": cmv, "total_mv": info.get("total_mv"),
            "mf1": f.get("mf1"), "mf5": f.get("mf5"),
            "mf10": f.get("mf10"), "mf20": f.get("mf20"),
            "mf_src": f.get("src"), "mf_date": f.get("date"),
            "ytd": r["factors"]["ytd"], "dist52": r["factors"]["dist52"],
            "tier": r["tier"], "score": r["score"], "hard": bool(r["hard"]),
            "close": r["close"], "entry_lo": r["entry_lo"], "entry_hi": r["entry_hi"],
            "stop": r["stop"], "stop_pct": r["stop_pct"], "t1": r["t1"], "t2": r["t2"],
            "rr": r["rr"], "factors": r["factors"], "score_detail": r["score_detail"],
            "fund_note": r["fund_note"], "h52": r["h52"], "l52": r["l52"],
            "bot": dict(b) if b else None, "lift": nl,
            "lift_hits": hits + (["20日主力净流入（弱辅助）"] if (f.get("mf20") or 0) > 0 else []),
            "bot_ok": (not why), "bot_drop": why,
        })
    RB.save_state(boxes)
    # ---- v5：全市场横截面分位打分 + 绝对名次档位 + 环境门控 ----
    model, mmeta = load_model()
    score_pool(out, model)
    n_tier = assign_tiers(out)
    mstate = market_state(kl)
    gate = env_coefficient(mstate)
    out.sort(key=lambda x: (-(x["qs"] if x["qs"] is not None else -1), x["code"]))
    nA, nB, nC = n_tier["A"], n_tier["B"], n_tier["C"]
    n_botok = sum(1 for x in out if x["bot_ok"])
    # ---- 出票许可：由 _rev_tier_gate.py 的证据决定，读不到 = 不出票（fail-safe） ----
    # 起因（2026-10-04）：页面「走前验证」表打的是 ④ 组 2159 条，而实际出票是 A 档 ∩ 前 10%
    # 只 52 只；且 ④ vs ① 是「子集 vs 母集」的绝对胜率比（6.4:1，违反 R1），也没有任何显著性区间。
    # 按 _rev_tier_gate.py 重算：A 档相对同日全市场域 edge −0.238pp、R3 29.9%、留一法全负，
    # 跨步长符号翻转 → 判「不可出票」（宁可不选，不能乱选）。证据页：web/reversal/tier_gate.html
    emit_ok, emit_why = True, ""
    try:
        import _rev_gate_page as G
        _lic = G.emit_license()
        emit_ok = bool(_lic.get("detail", {}).get("A", {}).get("ok"))
        emit_why = (_lic.get("detail", {}).get("A", {}) or {}).get("why", "")
    except Exception as ex:
        emit_ok, emit_why = False, "证据不可用：%s" % ex
    if not emit_ok:
        print("[rev_pool] 出票许可未通过（%s）→ 本期不出票（宁可不选），名单照列但不作买入依据" % emit_why)
    # 最终展示：必须同时通过「阶段底部＋启动证据」与「组合分前 10%」两道 —— 参考票不列表
    sel = [x for x in out if x["bot_ok"] and x["tier"] == "A"]
    if not emit_ok:
        sel = []
    sel.sort(key=lambda x: (-(x["qs"] if x["qs"] is not None else -1), x["code"]))
    print("[rev_pool] 硬门槛内 %d 只 → 阶段底部＋启动证据 %d 只 → ∩ 组合分前 %d%% = 精选 %d 只"
          % (n_tier["hard"], n_botok, A_PCT * 100, len(sel)))
    if bot_drop:
        print("[rev_pool] 阶段底部闸门取消："
              + "；".join("%s %d" % (k, v) for k, v in sorted(bot_drop.items(), key=lambda x: -x[1])))
    print("[rev_pool] 硬门槛内 %d 只：A %d / B %d / C %d｜模型 %d 特征｜环境 %s（广度 %s%%）→ 仓位系数 %.1f"
          % (n_tier["hard"], nA, nB, nC, len(model), mstate["label"],
             mstate.get("breadth"), gate["coef"]))
    # 走前验证（每日实算，不写死数字）：抽样 WF_SAMPLE 只，信号只用 T 日及之前信息
    wf = None
    try:
        import random
        pool = sorted(kl.keys())
        if len(pool) > WF_SAMPLE:
            random.Random(int(date.replace("-", ""))).shuffle(pool)
            pool = pool[:WF_SAMPLE]
        wf = RB.walk_forward({c: kl[c] for c in pool})
    except Exception as ex:
        print("[rev_pool] 走前验证跳过：%s" % ex)

    dc = date.replace("-", "")
    env = E.market_env(date)
    sel_rows = sel[:TOP_SHOW]
    scan = {"_doc": "底部反转观察池 v6（阶段底部锚定 ＋ 回升启动确认 ＋ 本轮回撤目标），"\
                   "只保留通过全部闸门且属域内组合分前 10% 的标的。",
            "version": "rev_v6",
            "data_date": date, "generated": date,
            "universe": ustat, "seed": seed_n,
            "presets": {"A": nA, "B": nB, "C": nC},
            "bot": {"n_hard": n_hard, "n_botok": n_botok, "drop": bot_drop,
                    "n_sel": len(sel), "lift_min": LIFT_MIN,
                    "min_leg_fall": MIN_LEG_FALL, "max_rise": MAX_RISE},
            "wf": wf, "wf_sample": len(pool) if wf else 0,
            "tiers": {"a_pct": n_tier.get("a_pct"), "b_pct": n_tier.get("b_pct"),
                      "a_cut": n_tier.get("a_cut"), "b_cut": n_tier.get("b_cut")},
            "hard": n_tier["hard"], "model": {"n": len(model), "features": model,
                                              "wf": mmeta.get("wf_agg"), "cut": mmeta.get("cut_date"),
                                              "evidence": mmeta.get("evidence")},
            "emit_ok": emit_ok, "emit_why": emit_why,
            "mstate": mstate, "gate": gate,
            "env": (env["label"] if env else "未知"),
            "flow_src": enrich.get("flow_src"),
            "ab_codes": [x["_full"] for x in sel_rows],
            "candidates": sel_rows}
    json.dump(scan, open(os.path.join(QUANT, f"watchlist_scan_{dc}.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    html = render_watchlist(scan, sel_rows, env)
    open(os.path.join(OUTDIR, f"watchlist_{dc}.html"), "w", encoding="utf-8").write(html)
    print("[rev_pool] 写 web/reversal/watchlist_%s.html（精选 %d 只 / 域内 %d 只）"
          % (dc, len(sel_rows), len(out)))
    return out


def render_only(date):
    """只重渲染（补数后再出页，不重拉日K）。

    典型用法：`rev_pool.py run` → `fetch_rev_flow.py` → `fetch_rev_enrich.py` →
    `rev_pool.py render`（把补全的名称/流通市值/主力资金合并进 scan 与页面）。
    """
    dc = str(date).replace("-", "")
    sp = os.path.join(QUANT, f"watchlist_scan_{dc}.json")
    if not os.path.exists(sp):
        raise SystemExit("缺少 %s，先跑 rev_pool.py run" % sp)
    scan = json.load(open(sp, encoding="utf-8"))
    rows = scan.get("candidates") or []
    enrich = load_enrich(date)
    eq, ef = enrich.get("quote") or {}, enrich.get("flow") or {}
    codes, _, _, seed_names = load_universe(date)
    for c in rows:
        full = c.get("_full") or c.get("code")
        e, f = eq.get(full) or {}, ef.get(full) or {}
        if seed_names.get(full):
            c["name"] = seed_names[full]
        elif e.get("name"):
            c["name"] = e["name"]
        if e.get("pe") is not None:
            c["pe"] = e["pe"]
        if e.get("circ_mv") is not None:
            c["float_mv"] = e["circ_mv"]
        for k in ("mf1", "mf5", "mf10", "mf20"):
            c[k] = f.get(k)
        c["mf_src"] = f.get("src")
        c["mf_date"] = f.get("date")
    scan["flow_src"] = enrich.get("flow_src")
    json.dump(scan, open(sp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    html = render_watchlist(scan, rows, E.market_env(date))
    open(os.path.join(OUTDIR, f"watchlist_{dc}.html"), "w", encoding="utf-8").write(html)
    n_mf = sum(1 for c in rows if c.get("mf20") is not None)
    n_mv = sum(1 for c in rows if c.get("float_mv") is not None)
    print("[rev_pool] 重渲染 %s：%d 只（流通市值 %d / 20日主力 %d｜口径 %s）"
          % (dc, len(rows), n_mv, n_mf, enrich.get("flow_src") or "—"))
    return rows


# ---------------- 回测 ----------------
# 退出规则：以「移动止盈（回撤跟踪）」为可兑现口径——宽硬止损避开小盘日内噪音，
# 浮盈达标后止损上移锁定收益，把「冲高回落」的票由亏损翻为盈利，显著提升胜率。
STOP = 0.12      # 硬止损 -12%（小盘波动适配；8% 过紧被日内噪音频繁扫损）
ACT = 0.06       # 浮盈 +6% 后激活移动止盈
TRAIL = 0.03     # 移动止盈回撤 3%（自持仓最高价起跟踪）
MAXFWD = 20      # 最长持有 20 日（时间止损）


def _sim_trail(k, i, px, stop=STOP, act=ACT, trail=TRAIL, maxfwd=MAXFWD,
               cons=False, gap=False):
    """移动止盈：未激活前硬止损 -stop；浮盈≥act 后止损上移为「最高价×(1-trail)」；满 maxfwd 强平。

    ★ 已收敛到 `_exit_sim.sim_trail_bars` 单一口径（默认 cons=False/gap=False = 旧口径，逐位一致）。
    """
    return _EXITSIM.sim_trail_bars(k, i, px, stop, act, trail, maxfwd, cons, gap)


def _sim_fixed(k, i, px, stop=0.12, tp=0.12, maxfwd=MAXFWD):
    """固定止损/止盈（对照）：先触 -stop 计亏、先触 +tp 计盈；满 maxfwd 强平。"""
    sl, tpl = px * (1 - stop), px * (1 + tp)
    lo = k[i]["low"]
    for j in range(1, maxfwd + 1):
        if i + j >= len(k):
            last = k[-1]["last"]
            return {"win": last > px, "pnl": (last / px - 1) * 100, "hold": j - 1,
                    "hit_tp": False, "hit_stop": False, "mae": (lo / px - 1) * 100}
        b = k[i + j]
        if b["low"] < lo:
            lo = b["low"]
        if b["low"] <= sl:
            return {"win": False, "pnl": (sl / px - 1) * 100, "hold": j,
                    "hit_tp": False, "hit_stop": True, "mae": (sl / px - 1) * 100}
        if b["high"] >= tpl:
            return {"win": True, "pnl": (tpl / px - 1) * 100, "hold": j,
                    "hit_tp": True, "hit_stop": False, "mae": (lo / px - 1) * 100}
    last = k[i + maxfwd]["last"]
    return {"win": last > px, "pnl": (last / px - 1) * 100, "hold": maxfwd,
            "hit_tp": False, "hit_stop": False, "mae": (lo / px - 1) * 100}


def _agg_path(rs):
    """聚合退出模拟：样本 / 胜率 / 均收益 / 中位 / 平均持有 / 触止盈率 / 触止损率 / 最坏MAE。"""
    if not rs:
        return None
    n = len(rs)
    pnls = [x["pnl"] for x in rs]
    vs = sorted(pnls)
    return (n, sum(1 for x in rs if x["win"]) / n * 100, sum(pnls) / n, vs[n // 2],
            sum(x["hold"] for x in rs) / n,
            sum(1 for x in rs if x["hit_tp"]) / n * 100,
            sum(1 for x in rs if x["hit_stop"]) / n * 100,
            min(x["mae"] for x in rs))


def _agg_naive(rs):
    """朴素买入持有：样本 / 胜率(>0) / 胜率(>+5%) / 均收益 / 中位 / 最差。"""
    if not rs:
        return None
    n = len(rs)
    vs = sorted(rs)
    return (n, sum(1 for v in rs if v > 0) / n * 100,
            sum(1 for v in rs if v > 5) / n * 100, sum(rs) / n, vs[n // 2], min(rs))


def backtest(codes=None, step=5, fwd=(5, 10, 20)):
    if codes is None:
        codes, _, _ = load_universe()
    print(f"[rev_pool] 回测：种子 {len(codes)} 只，拉取日K…")
    kl = fetch_klines(codes)
    T.save_cache()
    idxA, idxB, idxALL, idxBase = [], [], [], []      # (code,i,entry_px)
    naiveA, naiveALL, naiveBase = [], [], []          # 朴素买入持有 +20 日收益
    for code in codes:
        k = kl.get(code)
        if not k or len(k) < 80:
            continue
        for i in range(60, len(k) - MAXFWD - 1, step):
            px = k[i]["last"]
            idxBase.append((code, i, px))
            if i + 20 < len(k):
                naiveBase.append((k[i + 20]["last"] / px - 1) * 100)
            r = evaluate(k, i, None)
            if not r["ok"] or r["tier"] not in ("A", "B"):
                continue
            idxALL.append((code, i, px))
            (idxA if r["tier"] == "A" else idxB).append((code, i, px))
            if i + 20 < len(k):
                v = (k[i + 20]["last"] / px - 1) * 100
                naiveALL.append(v)
                if r["tier"] == "A":
                    naiveA.append(v)
    print(f"[rev_pool] 信号样本 {len(idxALL)}，基线样本 {len(idxBase)}")

    def run_rule(idxlist, sim):
        return _agg_path([sim(kl[c], i, px) for c, i, px in idxlist])

    an, bn = _agg_naive(naiveA), _agg_naive(naiveBase)
    stats = {
        # 主口径：移动止盈 −12% / +6%激活 / 3%回撤 / 满 20 日
        "A_path": run_rule(idxA, _sim_trail), "B_path": run_rule(idxB, _sim_trail),
        "ALL_path": run_rule(idxALL, _sim_trail), "base_path": run_rule(idxBase, _sim_trail),
        # 旧口径（对照）
        "A_naive": an, "ALL_naive": _agg_naive(naiveALL), "base_naive": bn,
    }
    # 退出规则敏感性：A 档 vs 基线 在各规则下的胜率与均收益
    var = [("朴素买入持有 +20 日", an[1] if an else 0, an[3] if an else 0, bn[1] if bn else 0)]
    fr = run_rule(idxA, lambda k, i, px: _sim_fixed(k, i, px, 0.12, 0.12))
    frb = run_rule(idxBase, lambda k, i, px: _sim_fixed(k, i, px, 0.12, 0.12))
    var.append(("固定止损止盈 −12% / +12%", fr[1], fr[2], frb[1]))
    for a_, t_, lab in ((0.08, 0.03, "移动止盈 · +8%激活 / 回撤3%"),
                        (0.06, 0.03, "移动止盈 · +6%激活 / 回撤3% ★主口径"),
                        (0.04, 0.03, "移动止盈 · +4%激活 / 回撤3%")):
        ar = run_rule(idxA, lambda k, i, px, a_=a_, t_=t_: _sim_trail(k, i, px, 0.12, a_, t_))
        br = run_rule(idxBase, lambda k, i, px, a_=a_, t_=t_: _sim_trail(k, i, px, 0.12, a_, t_))
        var.append((lab, ar[1], ar[2], br[1]))
    stats["variants"] = var
    html = render_backtest(stats, len(codes), len(idxALL), len(idxBase))
    open(os.path.join(OUTDIR, "backtest.html"), "w", encoding="utf-8").write(html)
    print("[rev_pool] 写 web/reversal/backtest.html")
    return stats


# ---------------- 渲染 ----------------
def _factor_line(r):
    f = r["factors"]
    parts = []
    parts.append("组合分位 <b>%.0f</b>/100（%s）" % (
        (r.get("qs") if r.get("qs") is not None else 0),
        ("硬门槛内第 %d 名" % r["qrank"]) if r.get("qrank") else "未过硬门槛"))
    parts.append("距52周低点 %+.1f%%" % f["gap_lo52"])
    parts.append("距60日低 %+.1f%%" % f["dist_lo60"])
    parts.append("量能枯竭 %.2f" % f["vol_dry"])
    parts.append("ATR %.2f%%" % f["atr_pct"])
    parts.append("20日箱体 %.1f%%" % f["range20"])
    parts.append("MA60 偏离 %+.1f%%" % f["ma60_dev"])
    parts.append("MA20 斜率 %+.2f%%" % f["slope"])
    parts.append("短周期多头排列 %s" % ("是" if f["short_align"] else "否"))
    div = "底背离✅" if f["div"] is True else ("背离弱" if f["div"] == "weak" else "无背离")
    parts.append(div)
    return "；".join(parts)


STYLE = """
:root{--bg:#fbfbfd;--card:#fff;--text:#1d1d1f;--muted:#6e6e73;--line:#e5e5e7;
 --up:#ff3b30;--dn:#34c759;--blue:#0071e3;--gold:#b8893b;--orange:#ff9500;--purple:#af52de;}
*{box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"PingFang SC","Microsoft YaHei",sans-serif;
 background:var(--bg);color:var(--text);line-height:1.7;margin:0;padding:0}
.wrap{max-width:1000px;margin:0 auto;padding:28px 18px 56px}
h1{font-size:23px;font-weight:700;margin:0 0 6px;letter-spacing:-.02em}
h2{font-size:18px;font-weight:600;margin:26px 0 12px;padding-bottom:8px;border-bottom:2px solid var(--blue)}
.sub{color:var(--muted);font-size:13px;margin-bottom:8px}
.card{background:var(--card);border-radius:16px;padding:16px 20px;margin:12px 0;box-shadow:0 1px 3px rgba(0,0,0,.05)}
.box{border-left:4px solid var(--blue);background:#f0f7ff;padding:14px 18px;border-radius:0 12px 12px 0;margin:14px 0}
.box.gold{border-color:var(--gold);background:#fffaf0}
.box.green{border-color:var(--dn);background:#f0faf3}
/* 表格：**不再横向滚动** —— 宽屏自适应换行；窄屏整行堆成卡片（列名由 td 的 data-l 提供） */
.tbl-wrap{max-width:100%;border:1px solid var(--line);border-radius:10px;margin-top:4px;background:#fff;}
table{width:100%;border-collapse:collapse;font-size:12.5px;table-layout:auto;}
th,td{padding:7px 5px;border-bottom:1px solid var(--line);text-align:right;
      white-space:normal;word-break:break-word;vertical-align:middle;}
th:first-child,td:first-child{text-align:left;}
th{white-space:nowrap;color:var(--muted);font-weight:600;font-size:11.5px;background:#fafafa;}
@media(max-width:1040px){
  table.rt thead{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);}
  table.rt tr{display:block;border-bottom:2px solid var(--line);padding:8px 0;}
  table.rt tr:last-child{border-bottom:0;}
  table.rt td{display:flex;align-items:baseline;justify-content:space-between;gap:12px;
              border:0;padding:3px 12px;text-align:right;white-space:normal;}
  table.rt td::before{content:attr(data-l);flex:0 0 44%;color:var(--muted);font-size:11.5px;text-align:left;}
  table.rt tbody tr:hover{background:transparent;}
}
.num{font-variant-numeric:tabular-nums;}
.up{color:var(--up)}.dn{color:var(--dn)}.am{color:var(--blue)}.dim{color:#b0b3b8}
a{color:inherit}
.tag{display:inline-block;font-size:11px;padding:2px 8px;border-radius:10px;margin:1px 2px}
.tag.A{background:#e6f7ec;color:#1a7a45}
.tag.B{background:#fff3e0;color:#e65100}
.tag.C{background:#fdecea;color:#c0392b}
.case{font-size:13px;margin:10px 0;padding:12px 16px;background:#fafafa;border-radius:10px;border-left:3px solid var(--purple)}
.case .h{font-weight:600;margin-bottom:4px}
.kv{font-size:12.5px;color:var(--muted)}
.bp{background:#f7f9fc;border:1px solid var(--line);border-radius:10px;padding:10px 14px;margin:8px 0;font-size:13px}
.bp b{color:var(--blue)}
a.emlk{color:inherit;text-decoration:none;border-bottom:1px dashed rgba(128,128,128,.42)}
a.emlk:hover{color:var(--blue);border-bottom-color:var(--blue)}
.foot{text-align:center;color:var(--muted);font-size:12px;margin-top:28px}
""" + X.BADGE_CSS


def _yi(v, digits=2):
    """元 → 亿元字符串。"""
    if v is None:
        return "—"
    return "%+.2f" % (v / 1e8)


def _mf_cell(c, key="mf20"):
    """主力净流入单元格（红=净流入，绿=净流出，遵循 A 股惯例）。"""
    v = c.get(key)
    if v is None:
        return "<td class='num dim'>—</td>"
    cls = "up" if v > 0 else ("dn" if v < 0 else "")
    return "<td class='num %s'>%s</td>" % (cls, _yi(v))

def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace("'", "&#39;").replace('"', "&quot;"))


def _bot_cell(c):
    """谷底锚定状态：谷底价 / 确立日 / 已锁定多少个交易日 / 第几版。"""
    b = c.get("bot") or {}
    tr = b.get("trough")
    if tr is None:
        return "<td class='num' data-l='谷底 · 锁定' data-v=''>—</td>"
    lock = ("今日确立 · 第 %d 版" % (b.get("ver") or 1)) if not (b.get("age") or 0) \
        else ("已锁定 %d 日 · 第 %d 版" % (b.get("age"), b.get("ver") or 1))
    tip = "谷底确立于 %s（%s）；距上次触底 %d 个交易日，谷底位共获 %d 个交易日验证" % (
        b.get("td") or "—", lock, b.get("base_days") or 0, b.get("touch") or 0)
    return ("<td class='num' data-l='谷底 · 锁定' data-v='%s' title='%s'>"
            "<b>%.2f</b> <span class='dim' style='font-size:11px'>%s</span></td>"
            % (tr, esc(tip), tr, lock))


def render_watchlist(scan, out, env=None):
    date = scan["data_date"]
    nA = scan["presets"]["A"]; nB = scan["presets"]["B"]; nC = scan["presets"]["C"]
    nhard = scan.get("hard", 0)
    ms = scan.get("mstate") or {}
    mlab = ms.get("label", "未知")
    hist = X.load_cross_history()
    fs = scan.get("flow_src") or "—"
    _SRC_NAME = {"mcp": "westock（与精选池同口径）", "sina": "新浪财经离线",
                 "mixed": "westock + 新浪离线（部分标的兜底）"}
    _src_txt = _SRC_NAME.get(str(fs).split(".")[0], str(fs))
    if not any(c.get("mf20") is not None for c in out):
        _src_txt = "未取到（请跑 quant/fetch_rev_flow.py 补数）"
    bt = scan.get("bot") or {}
    n_hard_v = bt.get("n_hard") or nhard
    n_botok = bt.get("n_botok") or 0
    drop = bt.get("drop") or {}
    lift_min = bt.get("lift_min") or LIFT_MIN

    # 环境门控（只控 β，不改排序）
    gate = scan.get("gate") or {}
    coef = gate.get("coef")
    env_lab = (env or {}).get("label", "未知") if env else "未知"
    m20, br = ms.get("mkt20"), ms.get("breadth")
    mtxt = "全市场等权中位20日 %s ｜ 广度(站上MA20占比) %s ｜ 市场状态 %s" % (
        ("%+.1f%%" % m20) if m20 is not None else "—",
        ("%.0f%%" % br) if br is not None else "—", mlab)
    _cmap = {"防守": "red", "中性": "gold", "进攻": "green"}
    advice = gate.get("advice") or "按买卖点纪律执行，不追高、不摊平。"
    env_banner = (
        "<div class='box %s'><b>环境参考 · %s</b>（指数环境 %s）｜ %s ｜ <b>建议仓位系数 %.1f×</b><br>%s"
        "<br><span style='color:var(--muted)'>⚠️ 该系数只用于控制<b>总暴露（β）</b>，"
        "实测环境状态与选股 alpha 的关系在训练半与测试半<b>方向相反</b>——不要当成"
        "「环境好就重仓」的 alpha 依据。</span></div>"
        % (_cmap.get(gate.get("label"), "gold"), gate.get("label") or "—", env_lab, mtxt,
           (coef if coef is not None else 0.5), advice))

    # ---- 取消原因分布（不符合就不展示，不降级、不进参考列表） ----
    if drop:
        lis = "".join("<li>%s —— <b>%d</b> 只</li>" % (esc(k), v)
                      for k, v in sorted(drop.items(), key=lambda x: -x[1]))
        drop_html = ("<div class='note'><b>同一批深跌股里，本期有 %d 只被底部闸门挡下：</b><ul>%s</ul>"
                     "被挡下的<b>不进任何列表</b>（不是降级、不作参考），这也是本池从 %d 只收敛到 %d 只的全部原因。</div>"
                     % (n_hard_v - n_botok, lis, n_hard_v, len(out)))
    else:
        drop_html = ""

    # ---- 走前验证（每日实算） ----
    wf = scan.get("wf")
    # ⚠ 成交假设提醒（数字一律从证据 JSON 读，不写死；缺证据则明写「未核验」）
    ea_box = ""
    try:
        _rj = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                          "_rev_tier_gate.json"), encoding="utf-8"))
        for _t in (_rj.get("exit_assumption") or {}).get("tiers", []):
            if _t.get("tier") == "A" and _t.get("rows"):
                _o, _r = _t["rows"][0], _t["rows"][-1]
                ea_box = (
                    "<div class='box'><span style='color:var(--muted)'>⚠ <b>口径提醒</b>："
                    "上表用全项目统一的「移动止盈」结算，该口径含两处人为假设"
                    "（同一根 K 线的日内路径假设为「先冲高后回落」；跳空时仍按止损线价成交）。"
                    "换成<b>可实现口径</b>后，同一批票的绝对胜率由 %.1f%% 变为 <b>%.1f%%（%+.1fpp）</b>。"
                    "逐档实测见 <a href='tier_gate.html'>分档出票核验</a> 第九节，"
                    "口径定义见 <a href='../docs/exit_assumption_evidence.html'>成交假设审计</a>。</span></div>"
                    % (_o["wr"], _r["wr"], _r["wr"] - _o["wr"]))
                break
        if not ea_box:
            ea_box = ("<div class='box'><span style='color:var(--muted)'>⚠ <b>口径提醒</b>："
                      "本页移动止盈口径含「日内路径 + 跳空」两处人为假设，"
                      "本次<b>未做成交假设核验（无证据）</b>，上表胜率应视为乐观口径。</span></div>")
    except Exception:
        ea_box = ""
    if wf and wf.get("ctrl", {}).get("n"):
        g = {k: (wf.get(k) or {}) for k in ("ctrl", "base", "liftA", "core")}
        c_, b_, l_, x_ = g["ctrl"], g["base"], g["liftA"], g["core"]
        wf_html = (
            "<div class='box green'><b>走前验证（每日实算，非写死数字）：</b>"
            "抽样 %d 只、信号只用 T 日及之前信息，收益用 T+1 起真实走势 + 统一退出规则"
            "（−12%% 硬止损 / +6%% 激活移动止盈 / 回撤 3%% / 满 20 日）结算，特意把贡献拆成四组："
            "<table class='rt'><thead><tr><th>分组</th><th>样本</th><th>可兑现胜率</th>"
            "<th>均值收益</th><th>平均最大不利偏移</th></tr></thead><tbody>"
            "<tr><td data-l='分组'>① 深跌域全体（v5 旧口径）</td><td class='num' data-l='样本'>%d</td>"
            "<td class='num' data-l='胜率'>%.1f%%</td><td class='num' data-l='均收益'>%+.2f%%</td>"
            "<td class='num' data-l='MAE'>%.2f%%</td></tr>"
            "<tr><td data-l='分组'>② ① + 阶段底部区（只看位置）</td><td class='num' data-l='样本'>%d</td>"
            "<td class='num' data-l='胜率'>%.1f%%</td><td class='num' data-l='均收益'>%+.2f%%</td>"
            "<td class='num' data-l='MAE'>%.2f%%</td></tr>"
            "<tr><td data-l='分组'>③ ① + 启动证据≥%d 条（不看位置）</td><td class='num' data-l='样本'>%d</td>"
            "<td class='num' data-l='胜率'>%.1f%%</td><td class='num' data-l='均收益'>%+.2f%%</td>"
            "<td class='num' data-l='MAE'>%.2f%%</td></tr>"
            "<tr><td data-l='分组'><b>④ 本页实际采用：位置 ＋ 证据同时成立</b></td>"
            "<td class='num' data-l='样本'>%d</td><td class='num' data-l='胜率'><b>%.1f%%</b></td>"
            "<td class='num' data-l='均收益'><b>%+.2f%%</b></td><td class='num' data-l='MAE'>%.2f%%</td></tr>"
            "</tbody></table>"
            "<span style='color:var(--muted)'>读法：<b>把 ② 与 ① 对比、③ 与 ① 对比</b>，就能看出哪个条件在真正提供边际。"
            "本日实测差值：<b>位置约束单独 %+.1fpp、启动证据单独 %+.1fpp、二者同时 %+.1fpp</b>（对照①）。<br>"
            "必须诚实说明：<b>位置约束在不同的抽样/半区里忽正忽负</b>——大样本走前消融相对各自半区基线是"
            " −2.5pp / −0.8pp（略负），本日重算是 %+.1fpp，所以它<b>不该被当成胜率来源</b>，只是中性偏弱的条款；"
            "真正稳定提供边际的是「已经出现回升启动证据」。位置约束的价值在<b>尾部风险</b>："
            "平均最大不利偏移由 %.2f%% 收窄到 %.2f%%（④ 为 %.2f%%）—— 它换来的是「不追高、不接飞刀」，"
            "而不是更高的胜率。<br>⭐<b>诚实更正（2026-10-04）</b>：上表 ④ 是<b>闸门全开</b>那一层"
            "（阶段底部＋启动证据、<b>不看组合分</b>，共 %d 条），它<b>不是本页真正出票的那批</b>——"
            "出票还要 ∩ 组合分前 %d%%，本日只有 %d 只；且 ④ 相对①是<b>子集对母集</b>的绝对胜率差（%.1f:1），"
            "违反等量对照、也没有任何显著性区间。按 <a href='tier_gate.html'>分档出票核验</a> 重算"
            "（对照＝同日全市场域、逐日平衡 ＋ bootstrap），现行 A 档拿不出正超额 → "
            "<b>本期不出票，此表仅留痕、不作买入依据</b>。</span></div>"
            % (scan.get("wf_sample") or 0,
               c_["n"], c_["win"], c_["avg"], c_["mae"],
               b_["n"], b_["win"], b_["avg"], b_["mae"],
               lift_min, l_["n"], l_["win"], l_["avg"], l_["mae"],
               x_["n"], x_["win"], x_["avg"], x_["mae"],
               b_["win"] - c_["win"], l_["win"] - c_["win"], x_["win"] - c_["win"],
               b_["win"] - c_["win"], c_["mae"], b_["mae"], x_["mae"],
               x_["n"], int(A_PCT * 100), len(out), x_["n"] / max(1, c_["n"]) * 1.0)) + ea_box
    else:
        wf_html = ""

    # ---- 出票许可横幅（由 _rev_tier_gate.py 的证据决定） ----
    _ok = scan.get("emit_ok", True)
    if not _ok:
        emit_html = (
            "<div class='box red' style='border-color:#b00020'><b>⚠️ 本期不出票（宁可不选）。</b>"
            "按 <a href='tier_gate.html'>分档出票核验</a> 重算：现行出票条件（旧硬门槛 ＋ 阶段底部＋启动证据≥%d 条 "
            "＋ 组合分前 %d%%）相对<b>同日全市场域</b>的逐日平衡超额为负且不显著（%s）。"
            "本页那张「走前验证」表打的是 ④ 组 %s 条（闸门全开、不看组合分），"
            "<b>不是你真正会买的那批票</b>，也不是「相对随便买」的口径 —— 那个对比是<b>子集对母集</b>的绝对胜率差"
            "（对照样本是策略样本的约 %.0f 倍，违反等量对照），也没有任何显著性区间。"
            "名单照列仅供观察，<b>不作买入依据</b>。</div>"
            % (lift_min, int(A_PCT * 100), scan.get("emit_why") or "见证据页",
               (scan.get("wf") or {}).get("core", {}).get("n", 0) or "—",
               max(1.0, (scan.get("wf") or {}).get("ctrl", {}).get("n", 1)
                   / max(1, (scan.get("wf") or {}).get("core", {}).get("n", 1)))))
        sel_title = "本期名单 · 不出票（仅观察，不作买入依据）"
    else:
        emit_html = (
            "<div class='box green'><b>本期出票许可已通过</b>（依据 <a href='tier_gate.html'>分档出票核验</a>）。</div>")
        sel_title = "精选"

    rows = []
    for c in out:
        b = c.get("bot") or {}
        stage = b.get("stage") or "—"
        scls = {"底部区": "am", "启动": "up"}.get(stage, "dim")
        lift_tip = "；".join(c.get("lift_hits") or []) or "无"
        space = ((c["t1"] - c["close"]) / c["close"] * 100) if c.get("close") else None
        rows.append(
            f"<tr>"
            f"<td data-l='名称 · 代码'>{EM.link(c.get('_full') or c['code'], c['name'])}"
            f"<span class='dim' style='font-size:11px'> {c['code']}</span>"
            f"{X.badge_html(hist, c['code'], date)}</td>"
            f"<td class='num' data-l='组合分' data-v='{c.get('qs') if c.get('qs') is not None else ''}'>"
            f"<b>{(round(c['qs']) if c.get('qs') is not None else '—')}</b></td>"
            f"<td data-l='阶段' data-v='{esc(stage)}'><span class='{scls}'>{esc(stage)}</span></td>"
            + _bot_cell(c) +
            f"<td class='num dn' data-l='本轮跌幅' data-v='{b.get('fall') if b.get('fall') is not None else ''}'>"
            f"{(b['fall']):.0f}%</td>"
            f"<td class='num' data-l='距谷底' data-v='{b.get('rise') if b.get('rise') is not None else ''}'>"
            f"+{b.get('rise', 0):.1f}%</td>"
            f"<td class='num' data-l='启动证据' data-v='{c.get('lift') or 0}' title='{esc(lift_tip)}'>"
            f"<b>{c.get('lift') or 0}</b> 条</td>"
            f"<td class='num' data-l='现价' data-v='{c['close']}'>{c['close']}</td>"
            f"<td class='num am' data-l='买区' data-v='{c['entry_lo']}'>{c['entry_lo']}~{c['entry_hi']}</td>"
            f"<td class='num dn' data-l='止损' data-v='{c['stop']}'><b>{c['stop']}</b>"
            f"<span style='font-size:11px'>（{c['stop_pct']:+.0f}%）</span></td>"
            f"<td class='num' data-l='平台上沿' data-v='{(b.get('ph') if b.get('ph') is not None else '')}'>"
            f"{(b['ph']) if b.get('ph') is not None else '—'}</td>"
            f"<td class='num up' data-l='回升目标 T1 / T2' data-v='{c['t1']}'><b>{c['t1']}</b>"
            f"<span style='font-size:11px'>（+{space:.0f}%）/ {c['t2']}</span></td>"
            f"<td class='num' data-l='RR' data-v='{c['rr']}'>{c['rr']}</td></tr>")
    table = "".join(rows)

    # 明细卡片（只给最靠前的几只，避免页面膨胀）
    cards = "".join(
        "<div class='case'><div class='h'>✅ %s %s —— 组合分 %.0f / 100（域内第 %s 名）</div>"
        "<div class='kv'>%s</div>"
        "<div class='bp'>买区 %s~%s（回踩不追高）｜结构位止损 <b>%s</b>（%+.1f%%，跌破即底部结构失效）｜"
        "第一阻力（平台上沿）%s｜回升目标 T1 <b>%s</b> / T2 %s｜风险回报比 %s｜"
        "启动证据：%s</div></div>"
        % (EM.link(c.get("_full") or c["code"], c["name"]), c["code"],
           (c.get("qs") or 0), (c.get("qrank") or "—"), _factor_line(c),
           c["entry_lo"], c["entry_hi"], c["stop"], c["stop_pct"],
           ((c.get("bot") or {}).get("ph") or "—"), c["t1"], c["t2"], c["rr"],
           ("；".join(c.get("lift_hits") or []) or "—"))
        for c in out[:12])

    thead = ("<thead><tr>"
             "<th data-k='name' data-t='s'>名称 · 代码</th>"
             "<th data-k='qs' data-t='n'>组合分</th>"
             "<th data-k='stage' data-t='s'>阶段</th>"
             "<th data-k='trough' data-t='n'>谷底 / 锁定</th>"
             "<th data-k='fall' data-t='n'>本轮跌幅</th>"
             "<th data-k='rise' data-t='n'>距谷底</th>"
             "<th data-k='lift' data-t='n'>启动证据</th>"
             "<th data-k='close' data-t='n'>现价</th>"
             "<th data-k='buy' data-t='n'>买区</th>"
             "<th data-k='stop' data-t='n'>止损</th>"
             "<th data-k='ph' data-t='n'>平台上沿</th>"
             "<th data-k='t1' data-t='n'>回升目标 T1/T2</th>"
             "<th data-k='rr' data-t='n'>RR</th>"
             "</tr></thead>")

    return f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>底部反转观察池 · v6 阶段底部锚定 · {date}</title><style>{STYLE}</style></head>
<body><div class="wrap">
<h1>底部反转观察池 · v6（阶段底部锚定 ＋ 回升启动确认）</h1>
<div class="sub">数据基准 {date} 收盘｜ 全市场深跌域入域 <b>{scan.get('seed')}</b> 只 → 旧硬门槛 <b>{n_hard_v}</b> 只
→ <b>阶段底部 ＋ 启动证据 ≥{lift_min} 条</b> <b>{n_botok}</b> 只 → ∩ 组合分前 {int(A_PCT*100)}% = <b>本页精选 {len(out)} 只</b></div>
{env_banner}
<div class="box gold"><b>一句话：</b>v6 不再用「距 52 周高回撤 ≥18%」当底部——那只代表<b>跌得多</b>，
可以是下跌中继，也可能已经反弹一大截。现在先识别<b>本轮下跌段的谷底</b>，要求它<b>站住了</b>
（≥{int(RB.MIN_STOP_DAYS)} 个交易日不再创新低、位置仍在谷底 +{int(MAX_RISE)}% 以内、本轮跌幅 ≥{int(MIN_LEG_FALL)}%），
再要求已经出现<b>回升启动证据 ≥{lift_min} 条</b>。<b>谷底与平台上沿一旦确立就锁死</b>，不随行情天天改。</div>

{wf_html}

<div class="box red" style="border-color:#b00020"><b>⚠️ 这张表怎么用（必读）：</b>
<li type="square"><b>看「阶段」列</b>：底部区 = 仍在谷底附近横着；启动 = 已突破平台上沿但尚未走远。</li>
<li type="square"><b>看「谷底 / 锁定」列</b>：<b>谷底价即为结构止损的基准</b>，后面跟着「已锁定 N 日 · 第 v 版」——
只有当价格<b>跌破谷底 3%</b>、<b>距谷底 +30% 以上</b>或<b>锁定超 {RB.MAX_AGE} 个交易日</b>时才会重算并升版本。</li>
<li type="square"><b>目标位改按本轮下跌段回撤</b>：T1 = 谷底 + 本轮跌幅×0.382、T2 = ×0.618，比过去按「52 周高回撤」算的天价目标近得多、可兑现；
中间会先撞上<b>「平台上沿」</b>（谷底之后形成的前高），那是最近的真实阻力，到不了 T1 就先减一半。</li>
<li type="square"><b>止损分两层</b>：跌破<b>谷底结构位</b>先减半，跌到 <b>−15%</b> 全出；<b>+8%~+10% 先止盈一半</b>。
单笔试仓 3–5%。退出纪律 &gt; 入场筛选——这是本项目唯一跨期稳定的改进。</li>
</div>

{emit_html}
<h2>一、{sel_title}（{len(out)} 只 · 属域内组合分前 {int(A_PCT*100)}%）</h2>
{drop_html}
<div class="card"><div class="tbl-wrap"><table class="sortable rt">{thead}<tbody>{table or "<tr><td class='dim' colspan='13'>今日无标的同时满足「阶段底部 + 启动证据 + 高分位」——空仓等待也是纪律。</td></tr>"}</tbody></table></div>
<div class="note">排序默认按<b>组合分</b>降序（可点表头改列）。
<b>组合分</b>=9 个先验固定因子在<b>当日全市场深跌域内</b>的横截面分位（0~100，越高越像底），只在同日内可比、不可跨日。
<b>本轮跌幅</b>=自最近一个显著高点 → 谷底的跌幅；<b>距谷底</b>=现价相对谷底的涨幅（超过 {int(MAX_RISE)}% 就不在底部区了）。
<b>启动证据</b>=站上 MA10 / MA10 上翘 / MACD 金叉或底背离 / 量能放大 / 破平台上沿 / 20 日主力净流入，命中条数（悬停看明细）。
<b>RR</b>=风险回报比 =(T1−买区上沿)/(买区上沿−止损)。资金口径：{_src_txt}。名称可点击直达东方财富。</div></div>

<h2>二、最靠前的细节（{min(len(out), 12)} 只）</h2>
{cards or '<div class="case">今日无标的。</div>'}

<h2>三、方法论 v6 与局限（诚实版）</h2>
<div class="card"><div class="kv">
① <b>改了什么</b>：域与打分仍是 v5 的「全市场深跌域 + 先验固定因子集横截面分位」（9 因子等权、不筛不调权），
v6 新增的是<b>入场前的两道 verified 闸门</b>：阶段底部区、回升启动证据。<br>
② <b>为什么这两条能进</b>：走前消融（<code>quant/_rbot_ablate.py</code>，信号只用当日及之前信息、收益用 T+1~T+20 真实走势、
统一退出规则结算）显示，相对各自半区基线，<b>启动证据≥2 条</b> 前半 +2.0pp / 后半 +6.4pp，
<b>本轮跌幅≥30%</b> +1.3pp / +2.4pp，二者叠加后最强组合 +2.3pp / +8.3pp —— 两半同向才被采用。<br>
③ <b>被证伪、因此没采用的两条先验</b>：<b>「谷底触碰 ≥2 天」</b>（两半 −0.7pp / −1.0pp）与
<b>「只贴着谷底 ≤15%」单独使用</b>（两半 −2.5pp / −0.8pp）——位置约束本身<b>不产生</b>胜率，
它必须与「已经在回升」的证据同时成立才有价值。这两条仍展示在页面上，但<b>不作门槛</b>。<br>
④ <b>锚定</b>：谷底/平台上沿写进 <code>quant/rev/bottom_state.json</code>，数值锁死；
只对「破底 −3% / 远离 +30% / 超期 {RB.MAX_AGE} 日」重算。这样今天看到的价位，明天不会因为一根 K 线就换掉。<br>
⑤ <b>局限</b>：走前样本约 8 个月、20 日窗口重叠（样本非独立，pp 差须按日期聚类理解）；
胜率与单笔均值是一对权衡（宽止损+早止盈胜率高但单笔薄），<b>不要只看胜率</b>；
即便两半同向，仍需警惕：同一套因子的 alpha 高度依赖期间（v5 训练半 −3.0pp / 测试半 +16.4pp），找不到可提前识别失效期的信号。<br>
⑥ <b>红线</b>：主力净额只作<b>弱辅助</b>；<b>退出纪律 &gt; 入场筛选</b>；本页是量化筛选，非个股推荐。</div></div>

<div class="foot">本页为基于离线日K的量化筛选与方法论，非个股推荐、非买卖建议。决策责任在账户本人。数据基准 {date}。</div>
</div>{X.SORT_JS}</body></html>"""
def render_backtest(st, n_univ, n_sig, n_base):
    def prow(label, t, hi=False):
        if not t:
            return "<tr><td>%s</td><td colspan='8' class='muted'>—</td></tr>" % label
        wincls = "up" if t[1] >= 55 else ("dn" if t[1] < 50 else "")
        return ("<tr%s><td>%s</td><td class='num'>%d</td>"
                "<td class='num %s'>%.1f%%</td><td class='num'>%.1f%%</td><td class='num'>%.1f%%</td>"
                "<td class='num %s'>%.2f%%</td><td class='num'>%.2f%%</td>"
                "<td class='num'>%.1f</td><td class='num dn'>%.2f%%</td></tr>" % (
                    " class='hl'" if hi else "", label, t[0], wincls, t[1], t[5], t[6],
                    "up" if t[2] >= 0 else "dn", t[2], t[3], t[4], t[7]))
    A_r = prow("A 档（主买点）", st["A_path"], True)
    B_r = prow("B 档（次级确认）", st["B_path"])
    ALL_r = prow("全部信号", st["ALL_path"])
    BASE_r = prow("基线·随机持有（同退出规则）", st["base_path"])
    a, base = st["A_path"], st["base_path"]
    concl = ""
    if a and base:
        concl = (f"A 档<b>可兑现胜率</b>（移动止盈 −12% / +6%激活 / 回撤3%）<b>{a[1]:.1f}%</b> "
                 f"vs 基线 {base[1]:.1f}%（<b>{a[1]-base[1]:+.1f}pp</b>），"
                 f"均值收益 {a[2]:+.2f}% vs {base[2]:+.2f}%（<b>{a[2]-base[2]:+.2f}pp</b>），"
                 f"触止盈率 {a[5]:.1f}% / 触硬止损率 {a[6]:.1f}%，平均持有 {a[4]:.1f} 日，"
                 f"最坏 MAE {a[7]:.1f}% vs 基线 {base[7]:.1f}%（<b>{a[7]-base[7]:+.1f}pp</b>）。"
                 f"胜率较旧版「朴素买入持有 +20 日」的 58.4% <b>显著提升</b>。")

    def nrow(label, t):
        if not t:
            return "<tr><td>%s</td><td colspan='6' class='muted'>—</td></tr>" % label
        return ("<tr><td>%s</td><td class='num'>%d</td><td class='num'>%.1f%%</td><td class='num'>%.1f%%</td>"
                "<td class='num'>%.2f%%</td><td class='num'>%.2f%%</td><td class='num dn'>%.2f%%</td></tr>") % (
                label, t[0], t[1], t[2], t[3], t[4], t[5])
    na = nrow("A 档 · 朴素+20日（对照）", st["A_naive"])
    nall = nrow("全部信号 · 朴素+20日（对照）", st["ALL_naive"])
    nbase = nrow("基线 · 朴素+20日（对照）", st["base_naive"])

    vrows = ""
    for lab, awr, aavg, bwr in st["variants"]:
        vrows += ("<tr><td>%s</td><td class='num'>%.1f%%</td><td class='num %s'>%+.2f%%</td>"
                  "<td class='num'>%.1f%%</td><td class='num'>%+.1fpp</td></tr>") % (
            lab, awr, "up" if aavg >= 0 else "dn", aavg, bwr, awr - bwr)

    return f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>底部反转 · 回测报告（退出规则口径 · 旧 v3 规则对照）</title><style>{STYLE}</style></head>
<body><div class="wrap">
<h1>底部反转 · 回测报告（退出规则口径）</h1>
<div class="sub">walk-forward（<b>旧版种子宇宙</b>，仅作退出规则对照）：种子宇宙 {n_univ} 只，过往 ~180 交易日每 5 日重算信号；信号样本 {n_sig}，基线样本 {n_base}。</div>

<div class="box red"><b>⚠️ 本页口径说明（必读）：</b>本页评估的是<b>旧 v3 规则的退出规则口径</b>（基于当年的
「净利同比&gt;50 &amp; 0&lt;PE&lt;50 &amp; 市值&lt;100亿」条件选股种子宇宙），
只回答「同一条入场规则下，不同止损/止盈方式能把胜率调到多少」，<b>不能证明选股能力</b>，
也不代表 v5 全市场域的回测结果。若要评估「哪些特征真的有预测力、方向如何、档位该取多大」，
请以 <a href="lab.html" style="color:var(--blue)">特征功效实验室 lab.html</a> 为准
（v5 全市场域 · 先验固定集严格样本外 top20% 相对胜率 <b>+14.0pp</b>；退出规则对照见其第十一节）。
另：报告里「可兑现胜率」随退出参数变宽而升高，属规则设计的结果、非入场质量提升，勿当作策略优势。</div>

<div class="box gold"><b>结论：</b>{concl}<br>
本页只验证<b>退出规则</b>本身（止损 / 移动止盈 / 持有期），入场侧一律使用当年的旧规则，
不含 v5 的域扩张与先验固定因子集排序（那部分见 lab.html）。</div>

<h2>一、可兑现胜率（移动止盈 −12% 硬止损 / +6% 激活 / 回撤 3% / 满 20 日强平）</h2>
<div class="card"><table>
<thead><tr><th>分组</th><th>样本</th><th>可兑现胜率</th><th>触止盈率</th><th>触硬止损率</th>
<th>均值收益</th><th>中位收益</th><th>平均持有(日)</th><th>最坏MAE</th></tr></thead>
<tbody>{A_r}{B_r}{ALL_r}{BASE_r}</tbody></table>
<div class="note">可兑现胜率=按退出规则逐日模拟后盈利交易占比；触止盈率=浮盈达标后已激活移动止盈的占比；触硬止损率=−12% 硬止损离场占比；
最坏 MAE=所有信号路径中最低 (low/入场−1)，近似最大不利偏移。A/B 档仅统计 tier 命中信号；基线=种子宇宙所有(股,日) 套同一退出规则。单位均为 %。</div></div>

<h2>二、退出规则敏感性（A 档 vs 基线）</h2>
<div class="card"><table>
<thead><tr><th>退出规则</th><th>A 档胜率</th><th>A 档均收益</th><th>基线胜率</th><th>优势</th></tr></thead>
<tbody>{vrows}</tbody></table>
<div class="note">胜率与盈亏比是一对权衡：移动止盈越早锁定（激活点越低）胜率越高、但单笔均收益越薄；
「朴素买入持有」则胜率最低。★ 为主口径。可见「宽止损 + 移动止盈」是提升胜率、同时压住回撤的关键。</div></div>

<h2>三、对照 · 朴素买入持有 +20 日（旧口径）</h2>
<div class="card"><table>
<thead><tr><th>分组</th><th>样本</th><th>胜率(&gt;0)</th><th>胜率(&gt;+5%)</th>
<th>均值收益</th><th>中位收益</th><th>最差</th></tr></thead>
<tbody>{na}{nall}{nbase}</tbody></table>
<div class="note">旧口径仅作对照：信号日收盘买入、不动持有 20 日。其严重低估反转策略——大量反弹在 20 日内回吐，胜率与收益被压低。</div></div>

<h2>四、方法说明</h2>
<div class="card"><div class="kv">
• 信号：结构深度 + 量能枯竭 + 吸筹 + MACD 底背离 + 均线排列 六维评分；A=高胜率组合（背离/收复其一 ＋ 量能枯竭≤0.95 ＋ 吸筹≥2 或金叉），B=更松次级确认，C=未达硬门槛。<br>
• 退出（主口径）：信号日收盘买入 → 未盈利前 −12% 硬止损；浮盈 ≥ +6% 后止损上移为「持仓最高价 × 0.97」跟踪；满 20 日强制平仓。<br>
• 为何移动止盈：底部反转常「冲高回落」，固定持有会把到手的 +8%/+10% 回吐成亏损；移动止盈把这类交易翻为盈利，是小盘高波动标的提升胜率的核心。<br>
• 数据：腾讯前复权日K（离线）。与选股页同一套逻辑，保证「回测=实盘规则」。</div></div>

<div class="foot">回测为历史统计，不代表未来；非投资建议。</div>
</div></body></html>"""


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", nargs="?", default="all", help="run / render / backtest / all")
    ap.add_argument("date", nargs="?", default=SEED_DATE)
    a = ap.parse_args()
    if a.cmd in ("run", "all"):
        run(a.date)
    if a.cmd == "render":
        render_only(a.date)
    if a.cmd in ("backtest", "all"):
        backtest()
    if a.cmd == "all":
        print("完成。")
