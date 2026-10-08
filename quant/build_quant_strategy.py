# -*- coding: utf-8 -*-
"""量化策略板（综合选股 + 买卖点操作建议，分短 / 中 / 长持有周期）。

设计铁律（见 quant-factor-oos-lab 方法论）：
- 先验固定因子集（方向由经济逻辑给定、等权、不筛因子、不按回测调权重）→ 全市场域横截面分位。
- 本板是「综合视图」：把各池已在样本外证实的因子族（趋势 / 资金 / 反转 / 做T / 增仓）重新组织成
  短 / 中 / 长 三种持有周期视角，并给出量化买卖点；不是新 alpha 源，不宣称叠加胜率。
- 环境只控 β（仓位系数），不改变排序；退出纪律 > 入场筛选；期间依赖诚实披露。
- 全部用真实离线数据：_txk_cache.json（全市场日K）+ rev/bottom_state.json（底部锚定）。
"""
from __future__ import annotations
import os, sys, json, datetime, argparse, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import _tx_fetch as T
import _idxkline as E
import _emlink as EM
import _xhist as X

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QUANT = os.path.join(ROOT, "quant")
OUTDIR = os.path.join(ROOT, "web", "quant_strategy")
os.makedirs(OUTDIR, exist_ok=True)

MIN_BARS = 250          # 长线需 250 日低/高（缓存单只约 250 根，取满窗口）
PRICE_MIN = 2.0         # 现价下限（元）
AMT_MIN = 30_000_000    # 20 日均成交额下限（3000 万，元）

BUCKET_LABEL = {"short": "短线", "mid": "中线", "long": "长线"}
BUCKET_DESC = {
    "short": "≈5–20 交易日：捕捉箱体波动 / 动量加速，偏做T与波段，波动容忍度高。",
    "mid":   "≈1–3 个月：趋势已转多、资金进场，回踩均线低吸，吃主升段。",
    "long":  "≈3–12 个月：低位 + 低波动 + 底部锚定 / 机构增仓，逢低布局价值修复。",
}

# 因子方向：+1 = 值越大越好；-1 = 值越小越好（仅 long 的 reversal_depth 用 +1 取深跌）
FACTOR_DIR = {
    # 短线族（动量 / 量能 / 贴近均线 / 箱体窄）
    "mom5": +1, "rvol": +1, "near_ma10": +1, "range_tight": +1, "up_vol5": +1,
    # 中线族（趋势强度）
    "rel20": +1, "rel60": +1, "above_ma60": +1, "slope20": +1, "ma_strength": +1, "dist_h20": +1,
    # 长线族（低波动 / 深跌回撤 / 底部锚定增仓）
    "vol_low": +1, "reversal_depth": +1, "accumev": +1,
}
FAMILIES = {
    "short": ["mom5", "rvol", "near_ma10", "range_tight", "up_vol5"],
    "mid":   ["rel20", "rel60", "above_ma60", "slope20", "ma_strength", "dist_h20"],
    "long":  ["vol_low", "reversal_depth", "accumev"],
}

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
th{color:var(--muted);font-weight:600;font-size:11.5px;background:#fafafa;white-space:nowrap}
.num{font-variant-numeric:tabular-nums}
.up{color:var(--up)}.dn{color:var(--dn)}.am{color:var(--blue)}
.tag{display:inline-block;font-size:11px;padding:2px 8px;border-radius:10px;margin:1px 2px}
.tag.A{background:#e6f7ec;color:#1a7a45}
.tag.B{background:#fff3e0;color:#e65100}
.tag.short{background:#e6f0ff;color:#1a73e8}
.tag.mid{background:#fff3e0;color:#e65100}
.tag.long{background:#e6f7ec;color:#1a7a45}
.case{font-size:13px;margin:10px 0;padding:12px 16px;background:#fafafa;border-radius:10px;border-left:3px solid var(--purple)}
.case .h{font-weight:600;margin-bottom:4px}
.kv{font-size:12.5px;color:var(--muted)}
.bp{background:#f7f9fc;border:1px solid var(--line);border-radius:10px;padding:10px 14px;margin:8px 0;font-size:13px}
.bp b{color:var(--blue)}
.bxrow{display:flex;align-items:center;gap:10px;margin:6px 0 2px}
.bxtrack{position:relative;flex:1;min-width:180px;height:14px;background:#eee;border-radius:7px;overflow:visible}
.bxzone{position:absolute;top:0;height:100%;background:#cfe3ff;border-radius:7px 0 0 7px}
.bxzone.hold{background:#fff3d6;border-radius:0}
.bxtick{position:absolute;top:-3px;width:2px;height:20px;background:var(--gold)}
.bxneedle{position:absolute;top:-5px;width:0;height:0;margin-left:-5px;
 border-left:5px solid transparent;border-right:5px solid transparent;border-top:9px solid var(--up);z-index:2}
.bxlegend{display:flex;justify-content:space-between;font-size:10.5px;color:var(--muted);margin-top:3px;min-width:180px;flex:1}
.bxtag{font-size:12px;font-weight:700;white-space:nowrap}
.bxtag.buy{color:var(--up)}.bxtag.hold{color:var(--blue)}.bxtag.tp{color:var(--gold)}.bxtag.stop{color:var(--dn)}
.foot{text-align:center;color:var(--muted);font-size:12px;margin-top:28px}
.bktab{display:inline-block;font-size:12px;padding:3px 10px;border-radius:10px;margin-right:6px;font-weight:600}
""" + X.BADGE_CSS


# ---------------- 基础工具 ----------------
def _ma(arr, n):
    return sum(arr[-n:]) / n if len(arr) >= n else None


def _std(arr):
    if len(arr) < 2:
        return 0.0
    m = sum(arr) / len(arr)
    return math.sqrt(sum((x - m) ** 2 for x in arr) / len(arr))


def _pct_rank(values):
    """返回每个值的横截面百分位（0~100，平均秩处理并列）。"""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg = (i + j) / 2.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    n = max(1, len(values) - 1)
    return [r / n * 100.0 for r in ranks]


def _vol_unit(code):
    try:
        return T.vol_unit(code)
    except Exception:
        return 1.0 if code.startswith("sh688") else 100.0


def factors_at(C, H, L, O, V, idx, code, bottom):
    """在 date 处（bars[:idx+1]）算原始因子。返回 (raw_dict, ctx)。"""
    close = C[idx]
    ma5, ma10, ma20, ma60 = _ma(C[:idx + 1], 5), _ma(C[:idx + 1], 10), _ma(C[:idx + 1], 20), _ma(C[:idx + 1], 60)
    if not ma20 or not ma60:
        return None
    ma20_5 = _ma(C[:idx - 4], 20) if idx >= 9 else ma20
    # 动量
    mom5 = C[idx] / C[idx - 5] - 1 if idx >= 5 else 0.0
    mom20 = C[idx] / C[idx - 20] - 1 if idx >= 20 else 0.0
    mom60 = C[idx] / C[idx - 60] - 1 if idx >= 60 else 0.0
    rel20 = C[idx] / ma20 - 1
    rel60 = C[idx] / ma60 - 1
    above_ma60 = 1.0 if C[idx] > ma60 else 0.0
    slope20 = (ma20 - ma20_5) / ma20_5 if ma20_5 else 0.0
    # 均线多头
    ma_strength = 0.0
    if ma5 and ma10:
        ma_strength = sum([1 for a, b in [(ma5, ma10), (ma10, ma20), (ma20, ma60)] if a and b and a > b]) / 3.0
    # 接近近20日高
    dist_h20 = C[idx] / max(H[max(0, idx - 19):idx + 1]) - 1
    # 量比（近5日均量 / 近20日均量）
    v5 = sum(V[idx - 4:idx + 1]) / 5.0 if idx >= 4 else V[idx]
    v20 = sum(V[max(0, idx - 19):idx + 1]) / 20.0
    rvol = v5 / v20 if v20 else 1.0
    # 近5日上涨放量占比（量加权）
    up = [k for k in range(max(0, idx - 4), idx + 1) if C[k] > O[k]]
    up_vol5 = (sum(V[k] for k in up) / sum(V[max(0, idx - 4):idx + 1])) if up else 0.0
    # 贴近均线（做T好）
    near_ma10 = 1 - abs(C[idx] / ma10 - 1) if ma10 else 0.5
    # 箱体窄（近10日振幅 std / close，越小越好 → 取 1-）
    rng = [(H[k] - L[k]) / C[k] for k in range(max(0, idx - 9), idx + 1) if C[k]]
    range_tight = max(0.0, 1 - _std(rng) / 0.04) if rng else 0.0
    # 波动（ATR%）
    trs = []
    for k in range(max(1, idx - 19), idx + 1):
        trs.append(max(H[k] - L[k], abs(H[k] - C[k - 1]), abs(L[k] - C[k - 1])))
    atr = sum(trs) / len(trs) if trs else 0.0
    atr_pct = atr / close if close else 0.0
    vol_low = max(0.0, min(1.0, 1 - atr_pct / 0.05))
    # 长线：距52周高回撤（深跌机会）
    dist_h52 = C[idx] / max(H[max(0, idx - 249):idx + 1]) - 1
    reversal_depth = -dist_h52 if dist_h52 < 0 else 0.0
    # 长线：底部锚定 / 增仓（来自 bottom_state）
    stage = (bottom or {}).get("stage", "")
    accumev = 1.0 if ("底" in stage) else 0.0

    raw = dict(mom5=mom5, rvol=rvol, near_ma10=near_ma10, range_tight=range_tight, up_vol5=up_vol5,
               rel20=rel20, rel60=rel60, above_ma60=above_ma60, slope20=slope20,
               ma_strength=ma_strength, dist_h20=dist_h20,
               vol_low=vol_low, reversal_depth=reversal_depth, accumev=accumev)
    ctx = dict(close=close, ma10=ma10, ma20=ma20, ma60=ma60, atr_pct=atr_pct,
               above_ma60=above_ma60, bottom=bottom)
    return raw, ctx


def price_levels(bucket, C, H, L, idx, ctx):
    """按持有周期给量化买卖点（真实K线 + 底部锚定）。"""
    close = C[idx]
    if bucket == "short":
        lo10 = min(L[max(0, idx - 9):idx + 1])
        hi10 = max(H[max(0, idx - 9):idx + 1])
        el, eh = lo10 * 1.00, lo10 * 1.02          # 贴近下沿低吸，不追高
        stop = lo10 * 0.97
        t1, t2 = hi10 * 1.00, hi10 * 1.04
        method = "箱体下沿低吸（近10日高低区间）"
    elif bucket == "mid":
        ma10, ma20 = ctx["ma10"], ctx["ma20"]
        mids = [x for x in (ma10, ma20) if x]
        el = min(mids) * 0.99 if mids else close * 0.98
        eh = max(mids) * 1.01 if mids else close * 1.01
        if close > eh and mids:
            el, eh = ma20 * 0.98, ma20 * 1.02
        base_low20 = min(L[max(0, idx - 19):idx + 1])
        stop = base_low20 * 0.97
        h20 = max(H[max(0, idx - 19):idx + 1])
        t1, t2 = h20 * 1.05, h20 * 1.10
        method = "回踩 MA10/MA20 低吸（结构位止损）"
    else:  # long
        b = ctx.get("bottom")
        if b and b.get("trough"):
            gv = b["trough"]
            fall = b.get("fall") or 0.0
            drop = -fall if fall < 0 else (abs(b.get("leg_high", gv) - gv))
            el, eh = gv * 1.00, gv * 1.03
            stop = gv * 0.97
            t1 = gv + drop * 0.382
            t2 = gv + drop * 0.618
            method = "底部锚定（谷底×1.0~1.03 低吸；本轮下跌段回撤目标）"
        else:
            low60 = min(L[max(0, idx - 59):idx + 1])
            ma60 = ctx["ma60"] or close
            el = low60 * 1.00
            eh = ma60 * 0.99
            stop = low60 * 0.95
            t1 = max(H[max(0, idx - 119):idx + 1]) * 0.90
            t2 = max(H[max(0, idx - 249):idx + 1]) * 0.95
            method = "阶段低位低吸（近60日低为锚；近120/250日高为目标）"
    el, eh, stop, t1, t2 = (round(el, 2), round(eh, 2), round(stop, 2), round(t1, 2), round(t2, 2))
    rr = (t1 - eh) / (eh - stop) if eh > stop else 0.0
    span = t2 - stop
    pos_pct = (close - stop) / span * 100 if span > 0 else 50.0
    pos_pct = max(0.0, min(100.0, pos_pct))
    if close < stop:
        tag = "已破止损"
    elif close < el:
        tag = "接近买区"
    elif close <= eh:
        tag = "买区内·可买"
    elif close < t1:
        tag = "持有·待涨"
    elif close < t2:
        tag = "已到T1"
    else:
        tag = "已到T2"
    return dict(entry_lo=el, entry_hi=eh, stop=stop, t1=t1, t2=t2, rr=round(rr, 2),
                close=close, pos_pct=round(pos_pct, 1), pos_tag=tag, method=method)


def box_bar(bs):
    if not bs:
        return ""
    span = bs["t2"] - bs["stop"]
    if span <= 0:
        return ""
    el_p = max(0.0, min(100.0, (bs["entry_lo"] - bs["stop"]) / span * 100))
    eh_p = max(0.0, min(100.0, (bs["entry_hi"] - bs["stop"]) / span * 100))
    t1_p = max(0.0, min(100.0, (bs["t1"] - bs["stop"]) / span * 100))
    px_p = bs["pos_pct"]
    tag_cls = {"买区内·可买": "buy", "接近买区": "buy", "持有·待涨": "hold",
               "已到T1": "tp", "已到T2": "tp", "已破止损": "stop"}.get(bs["pos_tag"], "hold")
    return (f"<div class='bxrow'><div style='flex:1'>"
            f"<div class='bxtrack'><div class='bxzone' style='left:0;width:{el_p:.1f}%'></div>"
            f"<div class='bxzone hold' style='left:{el_p:.1f}%;width:{max(0, eh_p-el_p):.1f}%'></div>"
            f"<div class='bxtick' style='left:{t1_p:.1f}%'></div>"
            f"<div class='bxneedle' style='left:{px_p:.1f}%'></div></div>"
            f"<div class='bxlegend'><span>止损 {bs['stop']}</span><span>买区</span>"
            f"<span>T1 {bs['t1']}</span><span>T2 {bs['t2']}</span></div></div>"
            f"<div class='bxtag {tag_cls}'>{bs['pos_tag']}（箱体 {bs['pos_pct']:.0f}%）</div></div>")


def scan(date):
    cache = T._load()
    nm = {}
    try:
        nm = json.load(open(os.path.join(QUANT, "_stock_names.json"), encoding="utf-8"))
    except Exception:
        pass
    bottom_state = {}
    try:
        bj = json.load(open(os.path.join(QUANT, "rev", "bottom_state.json"), encoding="utf-8"))
        bottom_state = bj.get("bottoms", {})
    except Exception:
        pass

    codes = [c for c in cache if (c.startswith("sh6") or c.startswith("sz0") or c.startswith("sz3") or c.startswith("bj"))]
    rows = []
    st = liq = short = 0
    for code in codes:
        bars = cache.get(code)
        if not bars or len(bars) < MIN_BARS:
            short += 1
            continue
        nm_c = nm.get(code) or ""
        if "ST" in nm_c or "退" in nm_c:
            st += 1
            continue
        idx = None
        for j, b in enumerate(bars):
            if b["date"] == date:
                idx = j
                break
            if b["date"] > date:
                break
        if idx is None or idx < MIN_BARS:
            continue
        C = [b["last"] for b in bars]
        H = [b["high"] for b in bars]
        L = [b["low"] for b in bars]
        O = [b["open"] for b in bars]
        V = [b["volume"] for b in bars]
        close = C[idx]
        if close < PRICE_MIN:
            continue
        vu = _vol_unit(code)
        amt20 = sum(V[idx - 19 + k] * vu * C[idx - 19 + k] for k in range(20)) / 20.0
        if amt20 < AMT_MIN:
            liq += 1
            continue
        fr = factors_at(C, H, L, O, V, idx, code, bottom_state.get(code))
        if fr is None:
            continue
        raw, ctx = fr
        rows.append({"code": code[2:] if code[:2] in ("sh", "sz", "bj") else code, "_full": code,
                     "name": nm_c or code, "date": date, "close": close,
                     "raw": raw, "ctx": ctx, "amt20": amt20})

    # 横截面分位（单日域，先验固定方向）
    for key in FACTOR_DIR:
        vals = [r["raw"][key] for r in rows]
        pr = _pct_rank(vals)
        for r, p in zip(rows, pr):
            r.setdefault("fpct", {})[key] = p * FACTOR_DIR[key]   # 已乘方向：越大越好
    for r in rows:
        subs = {}
        for bk, fks in FAMILIES.items():
            subs[bk] = sum(r["fpct"][k] for k in fks) / len(fks)
        r["s_short"], r["s_mid"], r["s_long"] = subs["short"], subs["mid"], subs["long"]
        r["composite"] = (subs["short"] + subs["mid"] + subs["long"]) / 3.0
    # 持有周期分类（argmax + 经济门控）
    for r in rows:
        c, m, l = r["s_short"], r["s_mid"], r["s_long"]
        # 中线须趋势 intact（站上 MA60）
        if m >= c and m >= l and r["ctx"]["above_ma60"] < 0.5:
            m = -1
        # 短线须有可交易波动与流动性
        if c >= m and c >= l and (r["ctx"]["atr_pct"] < 0.008):
            c = -1
        best = max([("short", c), ("mid", m), ("long", l)], key=lambda x: x[1])[0]
        r["bucket"] = best
        r["bs"] = price_levels(best, [b["last"] for b in cache[r["_full"]]],
                               [b["high"] for b in cache[r["_full"]]],
                               [b["low"] for b in cache[r["_full"]]],
                               [b["date"] for b in cache[r["_full"]]].index(date),
                               r["ctx"])
    print("[qstrat] 全市场域 %d 只入池（剔 ST/退 %d · 流动性 %d · K线不足 %d）"
          % (len(rows), st, liq, short))
    return rows


def _bucket_table(rows, bk):
    tr = []
    for r in rows:
        bs = r.get("bs")
        bz = f"{bs['entry_lo']}~{bs['entry_hi']}" if bs else "—"
        stp = f"{bs['stop']}（RR {bs['rr']}）" if bs else "—"
        tgt = f"{bs['t1']} / {bs['t2']}" if bs else "—"
        bx = (f"<span class='{ {'买区内·可买':'up','接近买区':'up','持有·待涨':'am','已到T1':'','已到T2':'','已破止损':'dn'}.get(bs['pos_tag'],'')}' style='font-weight:700'>{bs['pos_tag']}</span><br><span style='font-size:11px;color:var(--muted)'>箱体 {bs['pos_pct']:.0f}%</span>") if bs else "—"
        raw = r["raw"]
        fac = ("短 %.0f｜中 %.0f｜长 %.0f" % (r["s_short"], r["s_mid"], r["s_long"]))
        tr.append(
            f"<tr><td>{EM.link(r['_full'], r['code'], cls='')}</td>"
            f"<td>{EM.link(r['_full'], r['name'])}</td>"
            f"<td class='am num'>{r['close']}</td>"
            f"<td class='num' style='font-weight:700'>{r['composite']:.0f}</td>"
            f"<td class='num'>{r['s_short']:.0f}</td><td class='num'>{r['s_mid']:.0f}</td><td class='num'>{r['s_long']:.0f}</td>"
            f"<td class='num'>{bz}</td><td class='dn num'>{stp}</td><td class='up num'>{tgt}</td>"
            f"<td>{bx}</td><td class='kv'>{fac}</td></tr>")
    return "".join(tr)


def _bucket_cases(rows, bk, n=12):
    out = []
    for r in rows[:n]:
        bs = r.get("bs")
        raw = r["raw"]
        fam = "｜".join("%s %.0f" % (BUCKET_LABEL[b], r["s_" + b]) for b in ("short", "mid", "long"))
        if bs:
            bp = (f"<div class='bp'><b>买区</b> {bs['entry_lo']}~{bs['entry_hi']}（{bs['method']}）｜"
                  f"<b>结构位止损</b> {bs['stop']}｜<b>目标</b> T1 {bs['t1']} / T2 {bs['t2']}｜RR {bs['rr']}"
                  f"<br><b>箱体位置</b>：现价 {bs['close']} 处于「{bs['pos_tag']}」，箱体 {bs['pos_pct']:.0f}%（0%=止损位，100%=T2）｜{box_bar(bs)}</div>")
        else:
            bp = ""
        kv = ("短线分 <b>%.0f</b>｜中线分 <b>%.0f</b>｜长线分 <b>%.0f</b>（综合 <b>%.0f</b>）"
              % (r["s_short"], r["s_mid"], r["s_long"], r["composite"]))
        out.append(
            f"<div class='case'><div class='h'>🔥 {EM.link(r['_full'], r['name'])} {r['code']} "
            f"—— 命中<b>{BUCKET_LABEL[bk]}</b>周期</div>"
            f"<div class='kv'>{kv}</div>{bp}</div>")
    return "".join(out)


def render(rows, date, env):
    lab = (env or {}).get("label", "未知") if env else "未知"
    sc = (env or {}).get("score") if env else None
    pos = (env or {}).get("pos_scale") if env else None
    advice = (env or {}).get("advice", "") if env else ""
    env_banner = ""
    if lab and lab != "未知":
        env_banner = (f"<div class='box red'><b>大盘环境门控：{lab}</b>（综合分 {sc}）｜ 建议仓位系数 "
                      f"<b>{pos}</b><br>{advice} "
                      f"本页已据此给<b>仓位系数</b>（控 β 暴露）；排序本身不受环境影响，宁可降低仓位也不降低确定性。</div>")
    by_b = {bk: sorted([r for r in rows if r["bucket"] == bk], key=lambda x: -x["s_" + bk]) for bk in ("short", "mid", "long")}
    counts = {bk: len(by_b[bk]) for bk in ("short", "mid", "long")}

    sections = ""
    for bk in ("short", "mid", "long"):
        br = by_b[bk][:60]
        tbl = _bucket_table(br, bk)
        cases = _bucket_cases(by_b[bk], bk, 12)
        sections += (
            f"<h2>{BUCKET_LABEL[bk]} · {BUCKET_DESC[bk]}（{counts[bk]} 只 · 展开前 12，表列前 60）</h2>"
            f"<div class='card'>{cases or '<div class=\"case\">本期该周期无达标标的，空仓等待也是纪律。</div>'}</div>"
            f"<div class='card'><div style='overflow-x:auto'><table data-wb>"
            f"<thead><tr><th>代码</th><th>名称</th><th>现价</th><th>综合分</th><th>短线分</th><th>中线分</th><th>长线分</th>"
            f"<th>买区</th><th>止损</th><th>目标T1/T2</th><th>箱体位置</th><th>三族分</th></tr></thead>"
            f"<tbody>{tbl}</tbody></table></div>"
            f"<div class='note' style='color:var(--muted);font-size:12px'>按{BUCKET_LABEL[bk]}分降序；"
            f"买卖点为量化参考区间（{ '短线=近10日箱体的下沿低吸/上沿止盈' if bk=='short' else '中线=回踩MA20低吸、结构位止损、近20日高延伸' if bk=='mid' else '长线=底部锚定或阶段低位低吸、本轮下跌段回撤为目标' }），须结合大盘环境与退出纪律执行。</div></div>"
        )

    return f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>量化策略板 · 综合选股 + 买卖点（短/中/长）· {date}</title><style>{STYLE}</style></head>
<body><div class="wrap">
<h1>量化策略板 · 综合选股 + 买卖点操作建议（短 / 中 / 长）</h1>
<div class="sub">数据基准 {date} 收盘｜ <b>全市场域</b>：A 股正股，剔 ST/退 与 20 日均成交额 &lt;3000 万、现价 &lt;2 元、K线&lt;260 日
｜ 先验固定因子集（短 / 中 / 长 三族，等权横截面分位）→ 按持有周期分类并给量化买卖点</div>

<div class="box gold"><b>量化策略板是什么：</b>把已在样本外证实的各池因子族（<b>趋势</b>/<b>资金</b>/<b>反转</b>/<b>做T</b>/<b>增仓</b>）
重新组织成 <b>短线 / 中线 / 长线</b> 三种持有周期视角，各自给 <b>买区 / 止损 / 目标 / 盈亏比</b>。
它是「<b>综合视图</b>」，不是新 alpha 源——不宣称叠加胜率，选股能力以各池实验室页为准
（<a href="../selected/lab.html" style="color:var(--blue)">主升精选</a> · <a href="../reversal/lab.html" style="color:var(--blue)">反转</a> ·
<a href="../tplus/lab.html" style="color:var(--blue)">做T</a> · <a href="../accumulation/lab.html" style="color:var(--blue)">增仓</a>）。</div>

{env_banner}

<div class="box green"><b>方法（先验固定因子集，不筛不调权）：</b>
短线族 = 5日动量 + 量比 + 贴近MA10 + 箱体窄 + 上涨放量占比；中线族 = 近20/60日动量 + 站上MA60 + MA20斜率 + 均线多头 + 接近近20日高；
长线族 = 低波动(ATR%) + 距52周高深跌回撤 + 底部锚定/增仓。三族各自在<b>当日全市场域内</b>做横截面分位（方向由经济逻辑给定、等权），
按最高的一族判定持有周期。环境只给<b>仓位系数</b>（控 β），<b>不改变排序</b>。</div>

<div class="box red" style="border-color:#b00020"><b>⚠️ 退出纪律（唯一跨期稳定的改进，必读）：</b>
① <b>损位两层</b>：结构位（近20日基底 / 箱体下沿 / 谷底×0.97）破位先<b>减半</b>，跌到更宽固定位（约 −15%）再<b>全出</b>；
② <b>止盈移动</b>：浮盈达标后止损上移跟踪，到 T1/T2 先兑现一半；③ <b>胜率与单笔均值是一对权衡</b>，不要只看胜率。
本页买卖点为量化参考区间，实盘须按退出纪律执行，决策责任在账户本人。</div>

{sections}

<h2>方法论与局限</h2>
<div class="card"><div class="kv">
① <b>综合视图，非叠加 alpha</b>：三族分是同一批真实日K的不同切角，<b>不叠加胜率</b>；它解决「这只票该用哪种打法、拿多久」，不解决「一定能涨」。<br>
② <b>期间依赖诚实披露</b>：各池样本外实证均显示 edge 随市场环境摆动（如反转池 half_oos 训练半 −3pp / 测试半 +16pp），
某一期很强不代表下一期也强；本板不掩饰该波动。<br>
③ <b>排序器跑在全市场域</b>：分位在「可交易全市场域」算（非异动票子集），避免域错压扁分数（精选池曾因此最高分仅 66.6 vs 全市场 79+）。<br>
④ <b>局限</b>：前向窗口重叠→样本非独立；样本约 10 个月，换年份是否成立无法验证；主力资金用「上涨放量占比」价量代理（离线源历史主力净流入不可得）；
长线底部锚定依赖 rev/bottom_state.json（本地累积、随日K刷新）。绝对胜率含 beta，结论以相对口径为主。</div></div>

<div class="foot">本页为基于离线日K的量化综合视图与方法论，非个股推荐、非买卖建议。决策责任在账户本人。数据基准 {date}。</div>
</div>{X.SORT_JS}</body></html>"""


def main(date):
    rows = scan(date)
    env = E.market_env(date)
    html = render(rows, date, env)
    dc = date.replace("-", "")
    open(os.path.join(OUTDIR, f"strategy_{dc}.html"), "w", encoding="utf-8").write(html)
    open(os.path.join(OUTDIR, "index.html"), "w", encoding="utf-8").write(html)
    c = {bk: sum(1 for r in rows if r["bucket"] == bk) for bk in ("short", "mid", "long")}
    json.dump({"date": date, "n_universe": len(rows), "counts": c,
               "env": (env or {}).get("label", "未知") if env else "未知",
               "model": "quant_strategy_v1"},
              open(os.path.join(OUTDIR, f"stat_{dc}.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"[qstrat] 量化策略板：短线 {c['short']} ｜ 中线 {c['mid']} ｜ 长线 {c['long']}（域内 {len(rows)}）"
          f"｜ 环境 {(env or {}).get('label','未知') if env else '未知'} 写 web/quant_strategy/")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("date", nargs="?", default="2026-09-28")
    a = ap.parse_args()
    main(a.date)
