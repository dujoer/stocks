# -*- coding: utf-8 -*-
"""
个股信号池 · 双池打分与页面构建（第二步）

模型（v2，机构轨 / 游资轨 分轨）：
  Gate 0 板块闸门：所属板块主力行为 = 出货 → 直接剔除
  Gate 1 风险否决：获利盘 >90% / 远离成本 >30% / 跌破下行 MA60 / RSI>80 → 剔除

  机构轨（波段 5~15 日）100 分：
    机构方向 30（龙虎榜机构净买入 20 + 一致预期目标价空间 10）
    + 主力资金 10（5日/20日主力净流入）
    + 中报背景 10 + 高管 10（按金额/市值归一化） + 大宗 8
    + 量价 22 + 筹码 10 − 风险 10

  游资轨（短线 1~3 日）100 分：
    游资方向 32（知名席位 20 + 买入额 8 + 席位家数 4）
    + 主力资金 8（当日主力净流入）
    + 中报 6 + 高管 6 + 大宗 6
    + 量价 30 + 筹码 12 − 风险 10

输入：
  quant/picks/candidates_{D}.json   候选池（gen_picks.py）
  quant/picks/quotes_{D}.json       行情
  quant/picks/technical_{D}.json    技术指标
  quant/picks/consensus_{D}.json    一致预期目标价
  quant/picks/fundflow_{D}.json     主力资金流
  quant/picks/chip_{D}.json         筹码分布
  quant/sector_daily/{D}.json       板块主力行为（闸门）
  quant/picks/history.json          历史累积

输出：
  web/picks/pick_{D}.html · web/picks/index.html · quant/picks/history.json

用法：python quant/build_picks.py --date 2026-09-10
"""
import os
import re
import json
import glob
import argparse
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(ROOT, "web")
PICKS_WEB = os.path.join(WEB, "picks")
PICKS_DATA = os.path.join(ROOT, "quant", "picks")
SECTOR_DAILY = os.path.join(ROOT, "quant", "sector_daily")
HIST = os.path.join(PICKS_DATA, "history.json")
ARCHIVE = os.path.join(PICKS_DATA, "price_archive.json")  # 逐码×逐日 OHLC（回填源）


def load_json(p, default=None):
    if not os.path.exists(p):
        return default
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def fnum(v, nd=2, dash="—"):
    if v is None:
        return dash
    try:
        return f"{float(v):,.{nd}f}"
    except Exception:
        return dash


def pct(v, nd=2, dash="—"):
    if v is None:
        return dash
    try:
        return f"{float(v):+.{nd}f}%"
    except Exception:
        return dash


def esc(s):
    return (str(s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace("'", "&#39;").replace('"', "&quot;"))


def yi(v):
    """元 → 亿元字符串"""
    if v is None:
        return "—"
    try:
        return f"{float(v) / 1e8:.2f}亿"
    except Exception:
        return "—"


# ---------------- Gate 0：板块闸门 ----------------
def sector_behavior_map(D):
    """返回 {板块名: behavior}，优先取 <= D 的最新一天"""
    files = sorted(glob.glob(os.path.join(SECTOR_DAILY, "*.json")))
    files = [f for f in files if os.path.basename(f)[:10] <= D]
    if not files:
        return {}
    j = load_json(files[-1], {}) or {}
    out = {}
    for r in j.get("records", []) or []:
        nm = r.get("name")
        if nm and r.get("behavior"):
            out[nm] = r.get("behavior")
    return out


def match_sector(cand, smap):
    """用 sw2 / sw1 匹配板块行为，匹配不到返回 None"""
    for key in (cand.get("sw2"), cand.get("sw1")):
        if key and key in smap:
            return key, smap[key]
    return None, None


# ---------------- 高管增减持归一化 ----------------
def exec_norm(ex, q):
    """按 变动金额/总市值 归一化，返回 (0~10 分, 描述)"""
    if not ex:
        return 0.0, ""
    price = q.get("price") or 0
    mc = q.get("totalMarketCap") or 0
    shares = (ex.get("buyShares") or 0) - (ex.get("sellShares") or 0)
    if shares <= 0 or not price or not mc:
        return 0.0, ""
    ratio = shares * price / mc * 100  # 占总市值百分比
    if ratio >= 0.5:
        s, d = 10.0, f"净增持占市值 {ratio:.2f}%（大额）"
    elif ratio >= 0.1:
        s, d = 8.0, f"净增持占市值 {ratio:.2f}%（显著）"
    elif ratio >= 0.02:
        s, d = 5.0, f"净增持占市值 {ratio:.3f}%（中等）"
    elif ratio > 0:
        s, d = 2.5, f"净增持占市值 {ratio:.4f}%（小额）"
    else:
        s, d = 0.0, ""
    return s, d


# ---------------- 筹码评分 ----------------
def chip_score(ch, price, maxs=10.0):
    """返回 (分数, 要点列表)"""
    if not ch:
        return 0.0, []
    notes = []
    s = 0.0
    pr = ch.get("profitRate")
    cost = ch.get("avgCost")
    conc = ch.get("conc90")

    if pr is not None:
        if 25 <= pr <= 70:
            s += maxs * 0.45
            notes.append(f"获利盘{pr:.0f}%（健康）")
        elif 10 <= pr < 25 or 70 < pr <= 85:
            s += maxs * 0.3
            notes.append(f"获利盘{pr:.0f}%")
        elif pr < 10:
            s += maxs * 0.15
            notes.append(f"获利盘{pr:.0f}%（普遍套牢）")
        else:
            s += maxs * 0.05
            notes.append(f"获利盘{pr:.0f}%（抛压重）")

    if cost and price:
        dev = (price - cost) / cost * 100
        if -5 <= dev <= 12:
            s += maxs * 0.3
            notes.append(f"现价贴近成本{dev:+.1f}%")
        elif 12 < dev <= 30:
            s += maxs * 0.18
            notes.append(f"高于成本{dev:+.1f}%")
        elif dev < -5:
            s += maxs * 0.12
            notes.append(f"低于成本{dev:+.1f}%（套牢）")
        else:
            s += maxs * 0.05
            notes.append(f"远离成本{dev:+.1f}%")

    if conc is not None:
        if conc <= 8:
            s += maxs * 0.25
            notes.append(f"筹码集中{conc:.1f}")
        elif conc <= 15:
            s += maxs * 0.15
            notes.append(f"筹码较集中{conc:.1f}")
        else:
            s += maxs * 0.05
            notes.append(f"筹码分散{conc:.1f}")
    return round(s, 2), notes


# ---------------- 机构评级评分 ----------------
def rating_score(rt, maxs=8.0):
    """返回 (分数, 描述)。无评级=0 分（不奖不罚）"""
    if not rt:
        return 0.0, ""
    cnt = rt.get("ratingCnt")
    buy = rt.get("ratingBuyCnt")
    if not cnt:
        return 0.0, ""
    s = 0.0
    if cnt >= 10:
        s = maxs * 0.75
    elif cnt >= 5:
        s = maxs * 0.55
    elif cnt >= 3:
        s = maxs * 0.38
    else:
        s = maxs * 0.2
    ratio = (buy / cnt) if (buy is not None and cnt) else 0
    if ratio >= 0.9:
        s += maxs * 0.25
    elif ratio >= 0.7:
        s += maxs * 0.12
    s = min(maxs, s)
    return s, f"机构评级 {cnt} 家（买入 {buy or 0} 家，占比 {ratio*100:.0f}%）"


# ---------------- 两融评分 ----------------
def margin_score(mg, maxs=6.0):
    """融资余额环比增=杠杆资金进场（正面）；融券大增=看空（负面）"""
    if not mg:
        return 0.0, ""
    d = mg.get("financeDOD")
    sd = mg.get("securityDOD")
    s = 0.0
    desc = ""
    if d is None:
        return 0.0, ""
    if d >= 5:
        s = maxs
        desc = f"融资余额环比 +{d:.1f}%（杠杆积极）"
    elif d >= 2:
        s = maxs * 0.7
        desc = f"融资余额环比 +{d:.1f}%"
    elif d > 0:
        s = maxs * 0.4
        desc = f"融资余额环比 +{d:.1f}%"
    elif d > -3:
        s = maxs * 0.15
        desc = f"融资余额环比 {d:.1f}%"
    else:
        s = 0.0
        desc = f"融资余额环比 {d:.1f}%（杠杆撤离）"
    if sd is not None and sd >= 20:
        s = max(0.0, s - maxs * 0.4)
        desc += f"；融券 +{sd:.1f}%（看空增）"
    return min(maxs, s), desc


# ---------------- 热度反向惩罚 ----------------
def hot_penalty(rank, maxpen=4.0):
    """散户热度为反向指标：热搜越靠前、当日涨幅越大，越接近短期情绪高点"""
    if not rank:
        return 0.0, ""
    pos, zdf = rank
    pen = 0.0
    desc = ""
    if pos <= 10 and zdf >= 5:
        pen = maxpen
        desc = f"热搜第 {pos} 位且涨 {zdf:.1f}%（散户过热）"
    elif pos <= 10:
        pen = maxpen * 0.6
        desc = f"热搜第 {pos} 位（热度过高）"
    elif pos <= 30 and zdf >= 5:
        pen = maxpen * 0.5
        desc = f"热搜第 {pos} 位、涨 {zdf:.1f}%（情绪偏热）"
    elif pos <= 30:
        pen = maxpen * 0.25
        desc = f"热搜第 {pos} 位（有散户关注）"
    return pen, desc


# ---------------- 排雷：解禁 / 计划减持 / 质押 / 诉讼 ----------------
def event_check(code, evu, evr, rk, q, D):
    """返回 (否决原因 or None, 扣分, 说明列表)"""
    notes = []
    pen = 0.0
    veto = None
    price = q.get("price") or 0
    mc = q.get("totalMarketCap") or 0

    u = evu.get(code)
    if u and price and mc:
        shares = float(u.get("shares") or 0)
        ratio = shares * price / mc * 100
        dt = u.get("unlockDate")
        if ratio >= 1.0:
            veto = veto or f"解禁窗口内，解禁市值约占 {ratio:.2f}%"
        elif ratio >= 0.3:
            pen += 3
            notes.append(f"近期解禁约占市值 {ratio:.2f}%")
        elif ratio > 0:
            pen += 1
            notes.append(f"近期小额解禁（{dt or '—'}）")

    r = evr.get(code)
    if r:
        endv = r.get("endDate") or 0
        try:
            dint = int(D.replace("-", ""))
        except Exception:
            dint = 0
        if not endv or endv >= dint:
            veto = veto or f"处于计划减持窗口（{r.get('subject') or '股东'}，至 {endv or '—'}）"

    if rk:
        pr = rk.get("pledgeRatio")
        if pr is not None:
            if pr > 30:
                veto = veto or f"质押比例 {pr:.1f}% 过高"
            elif pr > 15:
                pen += 3
                notes.append(f"质押比例 {pr:.1f}% 偏高")
            elif pr > 8:
                pen += 1.5
                notes.append(f"质押比例 {pr:.1f}%")
        lc = rk.get("lawsuitCnt") or 0
        if lc > 0:
            pen += 2
            notes.append(f"存在诉讼 {lc} 起")
        es = rk.get("execSellRecent") or 0
        if es >= 3:
            pen += 2
            notes.append(f"高管历史转让 {es} 笔")
    return veto, min(8.0, pen), notes


# ---------------- 风险与否决 ----------------
def risk_and_veto(cand, q, t, ch, ff, behavior):
    """返回 (扣分0~10, 风险说明, 否决原因或 None)"""
    pen = 0.0
    notes = []
    veto = None
    price = q.get("price")
    ma60 = t.get("ma60")
    rsi = t.get("rsi12")
    ex = cand.get("exec") or {}
    bl = cand.get("block") or {}
    q2 = cand.get("q2") or {}
    pos = q.get("week52Pos")

    if behavior == "出货":
        veto = f"所属板块主力出货（{cand.get('sw1') or '—'}）"

    if ch:
        pr = ch.get("profitRate")
        if pr is not None and pr > 90:
            veto = veto or f"获利盘{pr:.0f}%，抛压极大"
        # 弱势区否决（2026-09-18 归因：获利盘<20% 段 T+1 -2.76% / 胜率 24%，
        # 叠加 52 周位<50 段 -1.14% / 胜率 37%，属实测最差组合）
        if pr is not None and pr < 20:
            if pos is None or pos < 50:
                veto = veto or (f"获利盘{pr:.0f}%（普遍套牢）"
                                + (f"且 52 周分位 {pos:.0f}" if pos is not None else "")
                                + "，弱势区暂不纳入")
            else:
                pen += 2
                notes.append(f"获利盘{pr:.0f}%（普遍套牢）")
        cost = ch.get("avgCost")
        if cost and price and price > cost * 1.30:
            veto = veto or "现价高于平均成本30%，追高风险"
        if pr is not None and pr > 85:
            pen += 3
            notes.append(f"获利盘{pr:.0f}%偏高")

    if ma60 and price and price < ma60:
        pen += 3
        notes.append("跌破MA60")
        if t.get("ma5") and t.get("ma20") and t["ma5"] < t["ma20"] < ma60:
            veto = veto or "均线空头排列且跌破MA60"

    if rsi is not None and rsi > 80:
        veto = veto or f"RSI{rsi:.0f}超买"
    elif rsi is not None and rsi > 75:
        pen += 2
        notes.append(f"RSI{rsi:.0f}偏高")

    if ex and (ex.get("buyCnt") or 0) < (ex.get("sellCnt") or 0):
        pen += 4
        notes.append("高管净减持")
    if bl and (bl.get("instSellValue") or 0) > (bl.get("instBuyValue") or 0):
        pen += 3
        notes.append("大宗机构净卖出")
    if q2 and (q2.get("cutCnt") or 0) > (q2.get("addCnt") or 0):
        pen += 2
        notes.append("中报减仓多于加仓")
    if pos is not None and pos > 92:
        pen += 3
        notes.append("接近一年高位")
    return min(10.0, pen), notes, veto


# ---------------- 交易计划 ----------------
def plan_inst(q, t, ch):
    """机构轨：波段 5~15 日，止损参考 MA20 与平均成本"""
    price = q.get("price") or 0
    ma5, ma10, ma20 = t.get("ma5"), t.get("ma10"), t.get("ma20")
    cost = (ch or {}).get("avgCost")
    bias = ((price - ma20) / ma20 * 100) if (ma20 and price) else 0

    if ma10 and bias > 10:
        lo, hi = ma10 * 0.99, ma10 * 1.01
        note = f"乖离MA20 {bias:.1f}%，回踩MA10（{fnum(ma10)}）介入，不追高"
    else:
        base = min([x for x in (price, ma5) if x] or [price])
        top = max([x for x in (price, ma5) if x] or [price])
        lo, hi = base * 0.995, top * 1.015
        note = "现价至MA5区间分批建仓"
    mid = (lo + hi) / 2

    cands = []
    if ma20:
        cands.append(ma20 * 0.97)
    if cost:
        cands.append(cost * 0.97)
    cands.append(mid * 0.93)
    below = [c for c in cands if c < mid * 0.995]
    stop = max(below) if below else mid * 0.92
    stop = max(stop, mid * 0.90)
    if stop >= mid * 0.97:
        stop = mid * 0.93

    return {
        "lo": round(lo, 2), "hi": round(hi, 2), "mid": round(mid, 2),
        "stop": round(stop, 2), "t1": round(mid * 1.10, 2), "t2": round(mid * 1.15, 2),
        "stopPct": round((stop - mid) / mid * 100, 2),
        "rr": round((mid * 1.10 - mid) / (mid - stop), 2) if mid > stop else 0,
        "note": note, "hold": "5~15 个交易日",
    }


def plan_youzi(q, t, ch):
    """游资轨：短线 1~3 日，紧止损、快进快出"""
    price = q.get("price") or 0
    ma5 = t.get("ma5")
    base = min([x for x in (price, ma5) if x] or [price])
    lo, hi = base * 0.99, price * 1.02
    mid = (lo + hi) / 2
    stop = min([x for x in ((ma5 or price) * 0.97, mid * 0.95) if x])
    return {
        "lo": round(lo, 2), "hi": round(hi, 2), "mid": round(mid, 2),
        "stop": round(stop, 2), "t1": round(mid * 1.05, 2), "t2": round(mid * 1.08, 2),
        "stopPct": round((stop - mid) / mid * 100, 2),
        "rr": round((mid * 1.05 - mid) / (mid - stop), 2) if mid > stop else 0,
        "note": "次日开盘不追高（高开>3%放弃），分时回踩介入；不封板即走",
        "hold": "1~3 个交易日",
    }


def grade(score, close=None, t1=None, pct=None, tk=None):
    """总分 -> 档位。

    2026-09-18 改：档位以**轨道内相对分位**为主（pct，0=最高分），
    因为机构轨与游资轨的满分量级不同（机构约 83、游资约 95），
    用同一套绝对阈值会让机构轨永远无 A/B；故两轨各设绝对底线：
      机构轨 A≥54 / B≥49 / 弱<40；游资轨 A≥60 / B≥54 / 弱<45。
    整体偏弱日或数据降级日该轨可能全数不入 A/B → 空仓等待，不硬凑。
    close>=t1（已达目标一）时强制转「仅跟踪」，不在高位追仓。
    """
    if tk == "inst":
        fa, fb, fd = 54.0, 49.0, 40.0
    else:
        fa, fb, fd = 60.0, 54.0, 45.0
    if score < fd:
        g, gn, ps, pn = "D", "弱势·仅跟踪", "不建仓", 0.0
    elif pct is not None:
        if pct <= 0.15 and score >= fa:
            g, gn, ps, pn = "A", "重点建仓", "8%~10%", 10.0
        elif pct <= 0.40 and score >= fb:
            g, gn, ps, pn = "B", "可建仓", "5%~7%", 7.0
        else:
            g, gn, ps, pn = "C", "轻仓观察", "≤3%", 3.0
    elif score >= 70:
        g, gn, ps, pn = "A", "重点建仓", "8%~10%", 10.0
    elif score >= 60:
        g, gn, ps, pn = "B", "可建仓", "5%~7%", 7.0
    elif score >= 50:
        g, gn, ps, pn = "C", "轻仓观察", "≤3%", 3.0
    else:
        g, gn, ps, pn = "D", "仅跟踪", "不建仓", 0.0
    if close is not None and t1 and close >= t1:
        return "D", "已达目标·仅跟踪", "不建仓", 0.0
    return g, gn, ps, pn


# ---------------- 历史回填 ----------------
def backfill(history):
    """回填次日/3日/5日表现。机构轨持有 5~15 日，必须看多周期，不能只看 T+1。

    价格源优先级：
      1) quant/picks/price_archive.json —— 逐码×逐日 OHLC（fetch_pick_klines.py 建），
         覆盖任意选股码在任意交易日的真实收盘价，使每只票次日即回填（核心修复）。
      2) quotes_*.json（当日候选价）—— 仅作兜底，覆盖 archive 未含的码。
    按真实交易日历取 T+1/3/5（下一/三/五个交易日），而非"候选日"。
    """
    arch = load_json(ARCHIVE, {}) or {}

    # 全局交易日历 = archive 全部日期 ∪ quotes 候选日
    dates_set = set()
    for rec in arch.values():
        dates_set.update(rec.keys())
    qfiles = {}
    qcache = {}
    for p in glob.glob(os.path.join(PICKS_DATA, "quotes_*.json")):
        m = re.search(r"quotes_(\d{4}-\d{2}-\d{2})\.json", os.path.basename(p))
        if m:
            qfiles[m.group(1)] = p
            dates_set.add(m.group(1))
    trading = sorted(dates_set)

    def qmap_of(d):
        if d not in qcache:
            qcache[d] = load_json(qfiles[d], {}) or {}
        return qcache[d]

    def bar_of(code, d):
        """返回 {open,high,low,close} 或 None（优先 archive，兜底 quotes）"""
        rec = arch.get(code)
        if rec and d in rec:
            b = rec[d]
            return {"open": b.get("o"), "high": b.get("h"),
                    "low": b.get("l"), "close": b.get("c")}
        qf = qfiles.get(d)
        if qf:
            qd = qmap_of(d).get(code)
            if qd:
                return {"open": qd.get("open"), "high": qd.get("high"),
                        "low": qd.get("low"), "close": qd.get("price")}
        return None

    def recalc_plan(pk, code, d):
        """用 archive 真实同日收盘 + MA5 重算入场/止损/目标一/二。

        历史期的 plan 曾用陈旧 MA5 计算（如 09-16 期部分票入场价比真实收盘低 9~14%），
        直接配真实后市价会算出虚高收益。此处统一按当日真实价结构重算，
        使回填收益口径一致、可比。archive 无该日数据则保持原值不动。
        """
        rec = arch.get(code)
        if not rec or d not in rec:
            return
        ds = sorted(x for x in rec if x <= d)[-5:]
        cs = [rec[x]["c"] for x in ds if rec[x].get("c") is not None]
        if not cs:
            return
        c = rec[d]["c"]
        if c is None:
            return
        ma5 = sum(cs) / len(cs)
        lo = min(c, ma5) * 0.97
        hi = max(c, ma5) * 1.02
        pk["entry"] = round((lo + hi) / 2, 2)
        pk["t1"] = round(max(c, ma5) * 1.08, 2)
        pk["t2"] = round(max(c, ma5) * 1.15, 2)
        pk["stop"] = round(min(c, ma5) * 0.93, 2)

    HOR = (("1", 1), ("3", 3), ("5", 5))
    for h in history:
        D = h.get("date")
        if D not in trading:
            continue
        base_idx = trading.index(D)
        later = trading[base_idx + 1:]
        if not later:
            h["settled"] = False
            continue
        any_cov = False
        for tk in ("inst", "youzi"):
            pk_list = h.get(tk, []) or []
            if not pk_list:
                continue
            for pk in pk_list:
                code = pk["code"]
                recalc_plan(pk, code, D)  # 用真实同日价结构校正入场/止损/目标
                entry = pk.get("entry")
                for k, hh in HOR:
                    if len(later) < hh:
                        continue
                    td = later[hh - 1]
                    b = bar_of(code, td)
                    if not b or b["close"] is None:
                        continue
                    close = b["close"]
                    if entry:
                        ret = (close - entry) / entry * 100
                    else:
                        ret = None
                    if ret is None:
                        continue
                    pk[f"ret{k}"] = round(float(ret), 2)
                    # 区间内是否触及目标一/二、止损
                    for dd in later[:hh]:
                        bb = bar_of(code, dd)
                        if not bb:
                            continue
                        if pk.get("t1") and bb["high"] is not None and bb["high"] >= pk["t1"]:
                            pk[f"hitT1_{k}"] = True
                        if pk.get("t2") and bb["high"] is not None and bb["high"] >= pk["t2"]:
                            pk[f"hitT2_{k}"] = True
                        if pk.get("stop") and bb["low"] is not None and bb["low"] <= pk["stop"]:
                            pk[f"hitStop_{k}"] = True
                # 次日实际涨跌（用于卡片"当日"列）
                b0 = bar_of(code, D)
                b1 = bar_of(code, later[0])
                if b0 and b1 and b0["close"] and b1["close"]:
                    pk["nextChg"] = round((b1["close"] - b0["close"]) / b0["close"] * 100, 2)
            for k, _ in HOR:
                sub = [p for p in pk_list if p.get(f"ret{k}") is not None]
                if sub:
                    h[f"{tk}_ret{k}"] = round(sum(p[f"ret{k}"] for p in sub) / len(sub), 2)
                    h[f"{tk}_win{k}"] = round(
                        sum(1 for p in sub if p[f"ret{k}"] > 0) / len(sub) * 100, 1)
                    h[f"{tk}_t1_{k}"] = sum(1 for p in sub if p.get(f"hitT1_{k}"))
                    h[f"{tk}_t2_{k}"] = sum(1 for p in sub if p.get(f"hitT2_{k}"))
                    h[f"{tk}_st_{k}"] = sum(1 for p in sub if p.get(f"hitStop_{k}"))
                h[f"{tk}_n{k}"] = len(sub)
                any_cov = any_cov or bool(sub)
            # 兼容旧字段
            h[f"{tk}_avg"] = h.get(f"{tk}_ret1")
            h[f"{tk}_n"] = h.get(f"{tk}_n1", 0)
        # 只要任一票有 T+1 价即可结算；否则保持待回填（等次日数据）
        if any_cov:
            h["settled"] = True
            h["settleDate"] = later[0]
        else:
            h["settled"] = False
    return history


# ---------------- 页面样式与导航 ----------------
CSS = """
* { box-sizing:border-box; }
body { margin:0; background:#f5f6f8; color:#23262b;
  font-family:"PingFang SC","Microsoft YaHei","Hiragino Sans GB",sans-serif; line-height:1.7; }
.wrap { max-width:1180px; margin:0 auto; padding:28px 20px 60px; }
.topnav { display:flex; flex-wrap:wrap; gap:8px; margin-bottom:22px; padding-bottom:14px;
  border-bottom:1px solid #e6e9ee; }
.topnav a { color:#b8893b; text-decoration:none; font-size:13px; padding:4px 12px; border-radius:20px;
  border:1px solid rgba(184,137,59,.35); }
.topnav a.cur { background:#b8893b; color:#fff; border-color:#b8893b; }
.topnav a:hover { background:rgba(184,137,59,.10); }
header h1 { font-size:26px; margin:0 0 6px; }
header h1 span { background:linear-gradient(90deg,#b8893b,#8a6428); -webkit-background-clip:text;
  -webkit-text-fill-color:transparent; }
.sub { color:#6b7480; font-size:13.5px; }
.section { margin-top:30px; }
.section h2 { font-size:19px; margin:0 0 14px; padding-left:12px; border-left:4px solid #b8893b; }
.trk { display:inline-block; font-size:12px; padding:2px 10px; border-radius:20px; margin-left:8px; }
.trk.i { background:#e6f1fb; color:#185fa5; } .trk.y { background:#fcebeb; color:#a32d2d; }
table { width:100%; border-collapse:collapse; background:#fff; font-size:13px;
  border:1px solid #e6e9ee; border-radius:10px; overflow:hidden; }
th,td { padding:8px 9px; text-align:left; border-bottom:1px solid #eef1f4; }
th { background:#fafbfc; color:#5a6573; font-weight:600; font-size:12.5px; }
tr:last-child td { border-bottom:none; }
.up { color:#b8332a; } .down { color:#1a9e5a; }
.card { background:#fff; border:1px solid #e6e9ee; border-radius:12px; padding:16px 18px; margin-bottom:12px; }
.card.hi { border-left:4px solid #b8893b; }
.chead { display:flex; align-items:baseline; gap:10px; flex-wrap:wrap; }
.cname { font-size:17px; font-weight:700; }
.ccode { color:#8a929c; font-size:13px; }
.badge { font-size:11.5px; padding:2px 9px; border-radius:20px; font-weight:700; }
.bA { background:#fdecea; color:#b8332a; } .bB { background:#fdf3e0; color:#b7791f; }
.bC { background:#eef4fa; color:#2b6cb0; } .bD { background:#eef0f2; color:#6b7480; }
.score { font-size:22px; font-weight:800; color:#b8893b; }
.grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(140px,1fr)); gap:9px; margin-top:11px; }
.kv { background:#fafbfc; border:1px solid #eef1f4; border-radius:8px; padding:7px 10px; }
.kv .k { font-size:11.5px; color:#8a929c; }
.kv .v { font-size:14px; font-weight:700; margin-top:2px; }
.kv .v.sm { font-size:12.5px; font-weight:600; }
.sig { margin-top:10px; font-size:12.5px; color:#5a6573; }
.sig b { color:#23262b; }
.chip { display:inline-block; background:#f4f6f8; border:1px solid #e6e9ee; border-radius:14px;
  padding:1px 9px; font-size:11.5px; margin:2px 4px 2px 0; color:#5a6573; }
.note { background:#fffaf0; border-left:4px solid #b8893b; padding:12px 16px; border-radius:0 8px 8px 0;
  font-size:13px; color:#6b4f2a; margin:14px 0; }
.warn { background:#fdecea; border-left-color:#b8332a; color:#8c2b22; }
.veto { background:#f4f6f8; border:1px dashed #c8ced6; border-radius:10px; padding:12px 16px;
  font-size:12.5px; color:#6b7480; margin:12px 0; }
footer { margin-top:36px; padding-top:16px; border-top:1px solid #e6e9ee; font-size:12px; color:#8a929c; }
.muted { color:#8a929c; font-size:12px; }
@media(max-width:700px){ .wrap{padding:20px 12px 44px;} header h1{font-size:20px;} table{font-size:12px;} }
/* 字段悬浮说明：带虚线下划线的字段均可悬浮查看口径 */
.tip { cursor:help; border-bottom:1px dotted #c3cad3; }
.kv.tipbox:hover { background:#fdf8ef; border-color:#e6d3ae; }
.kv .k.tipk::after { content:"?"; display:inline-block; margin-left:3px; font-size:10px;
  color:#b8893b; border:1px solid rgba(184,137,59,.45); border-radius:50%;
  width:12px; height:12px; line-height:11px; text-align:center; }
.chip[title], .badge[title], .score[title] { cursor:help; }
/* 观察池进出标记 */
.obs { display:inline-block; font-size:11px; padding:1px 7px; border-radius:10px; margin-left:6px;
  font-weight:600; vertical-align:middle; }
.obs.new { background:#e8f3ec; color:#1a7f43; border:1px solid #bfe0cb; }
.obs.keep { background:#f1f3f5; color:#6b7480; border:1px solid #e0e4e9; }
.dropsec table { font-size:12.5px; }
.dropsum { background:#fdecea; border-left:4px solid #b8332a; padding:12px 16px; border-radius:0 8px 8px 0;
  font-size:13px; color:#8c2b2b; margin:14px 0; }
.why { color:#8a929c; font-size:12px; }
"""


# ---------------- 字段口径说明（悬浮提示） ----------------
TIPS = {
    # 卡片交易计划字段
    "现价": "数据日期的收盘价，括号内为当日涨跌幅（红涨绿跌）。全部买卖点均以该日收盘后的数据计算。",
    "进场区间": "建议分批建仓的价格带。机构轨：乖离 MA20 超过 10% 时改挂 MA10±1%（不追高），否则取「现价~MA5」上下各 0.5%~1.5%；游资轨：min(现价,MA5)×0.99 ~ 现价×1.02。后续目标位与止损均以该区间中值 mid 为基准。",
    "止损": "机构轨：在 MA20×0.97、平均成本×0.97、mid×0.93 三个候选里取「低于 mid 且最接近 mid」的一个，并夹在 mid 的 90%~97% 之间；游资轨：min(MA5×0.97, mid×0.95)。括号内为止损位相对 mid 的百分比。收盘跌破即无条件离场。",
    "目标一": "目标一 = mid×1.10（机构轨）/ mid×1.05（游资轨）；目标二 = mid×1.15 / mid×1.08。为固定比例，不含个股基本面与阻力位判断，实际操作中建议结合前高压力位修正。",
    "今开": "当日开盘价（westock data_quote 的 open 字段）。与收盘价并列用于判断当日走势强弱：收盘高于开盘＝日内收阳、承接较好；收盘低于开盘＝日内冲高回落或抛压占优。",
    "收盘": "当日收盘价，即「现价」。本页新增的两项盈亏比例（距止损 / 距目标一）均以该价格为基准重算，与卡片中以进场区间中值 mid 为基准的「盈亏比」口径不同。",
    "距止损": "以<b>当日收盘价</b>为基准，跌到止损位还需下跌的幅度 =（止损价 − 收盘价）÷ 收盘价。负值表示尚有缓冲空间（数值越接近 0，离止损越近、安全垫越薄）；若显示为正并标注「已破」，说明收盘已跌破止损位，按纪律应无条件离场。注：与卡片「盈亏比」不同——后者以进场区间中值 mid 为基准，本项以当日实际收盘价为基准，用于盘中/盘后复核持仓的安全边际。",
    "距目标一": "以<b>当日收盘价</b>为基准，涨到目标一还可获得的幅度 =（目标一 − 收盘价）÷ 收盘价。数值越大代表剩余上行空间越足；若已接近 0 或为负，说明目标一已达成或已被超越，应转为跟踪目标二或按纪律分批止盈。",
    "盈亏比": "（目标一 − 进场中值）÷（进场中值 − 止损），即潜在盈利空间 ÷ 潜在亏损空间。分子固定 10%（机构轨）/ 5%（游资轨），所以数值完全由止损幅度决定：止损越近，比值越高。经验阈值 ≥2 值得做，<1 应当放弃。",
    "仓位": "按总分档位给出的建议最大仓位：A ≥70 分 8%~10%，B 60~70 分 5%~7%，C 50~60 分 3% 以内，D <50 分不建仓。分母为总资金，单票最大亏损应控制在总资金 2% 以内。",
    # 列表表头
    "名称": "个股名称。候选来自三路信号（中报十大股东增减持 / 高管增减持 / 大宗交易）与龙虎榜机构、游资方向合流。",
    "代码": "带市场前缀的代码：sh 沪市、sz 深市、bj 北交所。",
    "行业": "申万一级行业，来自中报股东库的代码-行业映射。",
    "板块": "该股所属板块当日的「主力行为」（抢筹 / 建仓 / 洗盘 / 出货）。行为为「出货」时触发 Gate0 板块闸门，直接剔除。",
    "总分": "该轨 11 维加权总分（0~100），已扣除风险扣分与热度反向分。机构轨与游资轨分开打分，同一只票在两轨分数不同。",
    "当日": "数据日期的当日涨跌幅。",
    "换手": "当日换手率（成交量 / 流通股本）。过高（>20%）视为情绪过热，量价分打折。",
    "52周位": "现价在近 52 周最高最低区间中的百分位，0 为最低、100 为最高。>92 视为接近一年高位并扣分。",
    "获利盘": "筹码分布中处于盈利状态的持仓占比。>90% 视为抛压极大并一票否决，>85% 扣分。",
    "档位": "A ≥70 分（8%~10% 仓位）· B 60~70（5%~7%）· C 50~60（≤3%）· D <50 不建仓。",
    # —— 稳健分（来自 picks/lab.html 的样本外实验室） ——
    "稳健分": "来自样本外实验室（picks/lab.html）的独立排序分（0~100）。因子固定为价量 5 项 + 基本面 7 项，"
              "方向由经济逻辑给定、等权、在<b>全市场可交易域</b>做横截面分位（候选只作展示过滤）—— <b>不按回测调权重</b>。"
              "分位基准从「异动票子集」改为「全市场」，修复了同因子在异动票域被压扁（最高分仅66.6 vs 全市场79+）的域错。"
              "原因：实测「自动筛因子」在严格样本外只剩 +0.5pp，筛选动作本身就是噪声源；"
              "而先验固定因子集在留出段相对胜率 +4.9pp、绝对胜率 +1.4pp，6 段滚动全部为正。"
              "它与「总分」的差别在于：总分是现有 11 维加权（含龙虎榜/评级/大宗等事件维度），"
              "稳健分只用可跨期稳定复现的价量与基本面维度，两者交叉可减少单一口径的误判。",
    "稳健分用法": "稳健分与总分<b>同高</b>＝两个独立口径都认可，优先看；"
                  "<b>总分高但稳健分低</b>＝可能只是事件驱动的一次性脉冲（龙虎榜/大宗），需要更严格的买点纪律；"
                  "<b>稳健分高但总分低</b>＝基本面与量价结构扎实、但暂无事件催化，适合放观察位。",
    # 打分明细维度
    "机构方向": "机构轨方向分，满分 28：龙虎榜机构席位净买入金额（最高 18）+ 一致预期目标价相对现价的空间（最高 10，空间 ≥30% 满分）。",
    "游资方向": "游资轨方向分，满分 30：知名游资席位现身次数（最高 18）+ 龙虎榜营业部买入额（最高 8）+ 席位家数（最高 4）。机构轨权重表里记为 30。",
    "机构评级": "最近 6 个月券商评级的覆盖家数与买入/增持占比，满分 8（data_rating）。小票常无覆盖，得分 0 属正常，不因此加分也不扣分。",
    "两融": "融资余额环比变化（杠杆资金进场为正），融券大幅增加为负，满分 6（机构轨）/ 8（游资轨）。",
    "主力资金": "主力净流入。机构轨看 5 日与 20 日（各 5 分，共 10 分，判断中期资金）；游资轨只看当日（10 分）。主力资金 = 主力净流入 − 散户净流入。",
    "中报背景": "2026 年中报十大流通股东加仓家数（≥2 家满分）。数据截至 2026-06-30 已滞后，仅作底仓确认，权重已下调。",
    "高管": "近 20 个交易日高管增减持，按「变动金额 / 总市值」归一化，满分 8（机构轨）/ 5（游资轨）。净减持转为风险扣分而非本项负分。",
    "大宗": "近 20 个交易日大宗交易：机构专用席位买入、溢价成交为正面，满分 6（机构轨）/ 5（游资轨）；机构净卖出转为风险扣分。",
    "量价": "量价健康度，机构轨满分 20、游资轨满分 28。由趋势结构（多头排列/中期上行/站上MA20…）42% + 量能换手 22% + RSI 动量 18% + 52 周相对位置 18% 加权。",
    "筹码": "获利盘比例、现价与平均成本偏离、筹码集中度，满分 6（机构轨）/ 9（游资轨）。",
    "风险": "风险扣分合计（最多 −12）：高管净减持 −4、大宗机构净卖出 −3、中报减仓多于加仓 −2、破 MA60 −3、RSI 偏高 −2、接近一年高位 −3、质押 >15% 等。",
    # 信号标签
    "机构净买": "近 20 个交易日龙虎榜机构专用席位的净买入金额合计（买入 − 卖出）。",
    "机构席位": "单日龙虎榜上机构专用席位出现的最大家数，家数越多说明机构分歧小、共识强。",
    "目标价空间": "券商一致预期目标价相对现价的空间：≥30% 满分 10 分，15%~30% 得 7 分，0~15% 得 4 分，低于现价 0 分。",
    "知名席位": "龙虎榜营业部中命中「知名游资席位库」（web/shareholder/data/person_index.json 中标记 star 的席位）的次数。",
    "游资买入": "近 20 个交易日龙虎榜营业部买入金额合计；同一条记录涉及多只股票时按只数均摊，避免重复计入。",
    "主力当日": "当日主力净流入金额（主力净流入 − 散户净流入）。",
    "板块行为": "该股所属板块当日的主力行为：抢筹（主力净流入 / 换手率 × 100 ≥3）、建仓（1~3）、洗盘（−1~1）、出货（<−1）。",
    # 归档首页
    "历史表现": "每一期的候选只数与次日回填表现：均涨 = 该期全部候选次日相对进场参考价的平均收益；触T1 / 触止损 = 区间内最高价触及目标一、最低价触及止损位的只数。",
    "维度": "评分模型的组成维度，机构轨与游资轨权重不同。",
    "机构轨权重": "该维度在机构轨总分中的满分值（机构轨满分 100）。",
    "游资轨权重": "该维度在游资轨总分中的满分值（游资轨满分 100）。",
    "口径": "该维度的具体计算方式与数据来源。",
    # 回测
    "回测T+1": "以进场参考价买入、第 1 个交易日收盘价计算的平均收益。",
    "回测T+3": "以进场参考价买入、第 3 个交易日收盘价计算的平均收益。",
    "回测T+5": "以进场参考价买入、第 5 个交易日收盘价计算的平均收益。",
    "胜率": "该组内收益为正的样本数 ÷ 有效样本数。",
    "触T1": "该组内区间最高价触及目标一的样本数（同一只票在一个周期内只计一次）。",
    "触T2": "该组内区间最高价触及目标二的样本数。",
    "触止损": "该组内区间最低价跌破止损位的样本数。",
    "有效样本": "已回填出该周期收益的候选只数；不足周期长度时尚未结算。",
    "候选数": "该期该轨输出的候选只数（已通过 Gate 一票否决后剩余的数量）。",
    "次日表现": "次日（T+1）回填：均涨 = 全部候选相对进场参考价的平均收益；触T1 = 区间最高价触及目标一的只数；触止损 = 区间最低价跌破止损位的只数。",
    "取消观察": "上一期在池、本期出局的个股数量，点击可跳到当日明细。取消只代表规则口径下不再跟踪（一票否决 / 无行情停牌 / 信号消失 / 评分未达阈值），不等于看空或立即卖出信号；已持仓者仍按原交易计划的止损与目标执行。",
    "热度反向": "热搜榜名次 + 当日涨幅：已上榜且涨幅巨大视为散户过热、短期见顶信号，最多扣 4 分（反向指标）。",
    "进场参考价": "页面给出的进场区间中值 mid，回测与次日回填全部以它为买入基准价。",
    "Gate": "一票否决闸门：所属板块主力出货 · 获利盘 >90% · 现价高于平均成本 30% · 均线空头排列且跌破 MA60 · RSI>80 · 解禁市值占比 ≥1% · 处于计划减持窗口 · 质押比例 >30%，命中任意一条即剔除，不参与打分。",
}


def tip(key, cls="tip"):
    """生成 title 属性；无说明时返回空串"""
    t = TIPS.get(key)
    if not t:
        return ""
    return f" class='{cls}' title='{esc(t)}'"


def tip_t(key):
    """只返回 title='...'"""
    t = TIPS.get(key)
    if not t:
        return ""
    return f" title='{esc(t)}'"


def nav(cur="picks"):
    from _nav import topnav
    return topnav(current_web_dir="picks", home="../../index.html")


# ---------------- 主流程 ----------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    args = ap.parse_args()
    D = args.date

    cands = load_json(os.path.join(PICKS_DATA, f"candidates_{D}.json"))
    qmap = load_json(os.path.join(PICKS_DATA, f"quotes_{D}.json"), {}) or {}
    tmap = load_json(os.path.join(PICKS_DATA, f"technical_{D}.json"), {}) or {}
    cmap = load_json(os.path.join(PICKS_DATA, f"consensus_{D}.json"), {}) or {}
    fmap = load_json(os.path.join(PICKS_DATA, f"fundflow_{D}.json"), {}) or {}
    hmap = load_json(os.path.join(PICKS_DATA, f"chip_{D}.json"), {}) or {}
    rkmap = load_json(os.path.join(PICKS_DATA, f"risk_{D}.json"), {}) or {}
    mgmap = load_json(os.path.join(PICKS_DATA, f"margin_{D}.json"), {}) or {}
    rtmap = load_json(os.path.join(PICKS_DATA, f"rating_{D}.json"), {}) or {}
    hotj = load_json(os.path.join(PICKS_DATA, f"hot_{D}.json"), {}) or {}
    evu = (load_json(os.path.join(PICKS_DATA, f"events_unlock_{D}.json"), {}) or {}).get("codes", {}) or {}
    evr = (load_json(os.path.join(PICKS_DATA, f"events_reduce_{D}.json"), {}) or {}).get("codes", {}) or {}
    # 热度排名：{code: (名次, 当日涨幅)}
    hotrank = {}
    for i, it in enumerate(hotj.get("list", []) or []):
        try:
            hotrank[it.get("code")] = (i + 1, float(it.get("zdf") or 0))
        except Exception:
            pass
    if not cands:
        print(f"[build_picks] 缺少候选池 {D}")
        return

    smap = sector_behavior_map(D)
    os.makedirs(PICKS_WEB, exist_ok=True)

    inst_rows, youzi_rows, vetoed = [], [], []
    cand_codes = {c.get("code") for c in cands["candidates"]}
    no_quote = set()
    for c in cands["candidates"]:
        code = c["code"]
        q = qmap.get(code) or {}
        t = tmap.get(code) or {}
        if not q.get("price"):
            no_quote.add(code)
            continue
        con = cmap.get(code) or {}
        ff = fmap.get(code) or {}
        ch = hmap.get(code) or {}
        sname, behavior = match_sector(c, smap)

        rk = rkmap.get(code) or {}
        mg = mgmap.get(code) or {}
        rt = rtmap.get(code) or {}
        hk = hotrank.get(code)

        pen, rnotes, veto = risk_and_veto(c, q, t, ch, ff, behavior)
        ev_veto, ev_pen, ev_notes = event_check(code, evu, evr, rk, q, D)
        veto = veto or ev_veto
        pen = min(12.0, pen + ev_pen)
        rnotes = rnotes + ev_notes
        hpen, hnote = hot_penalty(hk)
        if hnote:
            rnotes = rnotes + [hnote]

        if veto:
            _s = c.get("sig") or {}
            _tl = ([x for x in ("机构轨" if _s.get("inst") else "",
                                "游资轨" if _s.get("youzi") else "") if x])
            vetoed.append({"name": c.get("name"), "code": code, "why": veto,
                           "track": " / ".join(_tl) if _tl else "—"})
            continue

        s = c["sig"]
        price = q.get("price")
        exs, exd = exec_norm(c.get("exec"), q)
        # 2026-09-18 归因：筹码 r=+0.20（最强正向）、机构评级 r=-0.15（反向）
        chs_inst, chn_i = chip_score(ch, price, 10.0)
        chs_yz, chn_y = chip_score(ch, price, 12.0)
        rts, rtd = rating_score(rt, 4.0)
        mgs, mgd = margin_score(mg, 6.0)
        mgs_y, mgd_y = margin_score(mg, 8.0)

        # 中报背景（滞后项）—— 2026-09-18 归因显示与 T+1 负相关（r=-0.15），由 8 分降至 3 分
        q2 = c.get("q2") or {}
        q2_add = q2.get("addCnt") or 0
        q2s_inst = 1.5 if q2_add >= 2 else (0.8 if q2_add == 1 else 0.0)
        q2s_yz = 1.0 if q2_add >= 2 else (0.5 if q2_add == 1 else 0.0)

        # 大宗
        bl = c.get("block") or {}
        bls = 6.0 if (bl.get("instBuyValue") or 0) > 0 else (3.0 if bl.get("cnt") else 0.0)
        bls_yz = 5.0 if (bl.get("instBuyValue") or 0) > 0 else (2.5 if bl.get("cnt") else 0.0)

        # 量价
        # 2026-09-18 归因：量价 r=+0.17（第二强正向），上限 20→24 / 28→30
        ts, tn = tech_score(q, t, 24.0)
        tsz, tnz = tech_score(q, t, 30.0)

        # 机构方向 16（原 28）= 龙虎榜机构净买 10 + 目标价空间 6
        # 2026-09-18 归因：龙虎榜机构净买入与 T+1 负相关（r=-0.09，高分组 -0.19% vs 低分组 +0.73%）
        inb = 0.0
        inst = c.get("inst") or {}
        net = float(inst.get("netBuy") or 0)
        if net > 0:
            raw_b = net / 1e8 * 6.0 + (inst.get("branchMax") or 0) * 1.2
            inb = min(10.0, raw_b)
        tp = con.get("targetPrice")
        tps = 0.0
        tpspace = None
        if tp and price and tp > 0:
            tpspace = (tp - price) / price * 100
            tps = 6.0 if tpspace >= 30 else (4.0 if tpspace >= 15 else (2.0 if tpspace > 0 else 0.0))

        # 主力资金：只保留 5 日（20 日与 T+1 负相关，已剔除）
        # 资金流字段偶发为字符串（westock 上游口径不稳），统一安全转 float
        def _fnum(v):
            try:
                return float(v)
            except (TypeError, ValueError):
                return None

        mnf5 = _fnum(ff.get("mainNetFlow5D"))
        mnf20 = _fnum(ff.get("mainNetFlow20D"))
        mnf = _fnum(ff.get("mainNetFlow"))
        fs_inst = 0.0
        if mnf5 is not None:
            fs_inst += 6.0 if mnf5 > 0 else (2.0 if mnf5 > -1e8 else 0.0)
        fs_yz = 6.0 if (mnf or 0) > 0 else (2.5 if (mnf or 0) > -5e7 else 0.0)

        # ── 量价动量加分（归因：当日涨幅 0~3% 段 +0.92%/胜率 50%，>6% 段 +4.77%/胜率 83%）──
        mom_inst = mom_yz = 0.0
        mom_note = ""
        _cg = q.get("changePercent")
        if _cg is not None:
            try:
                _cg = float(_cg)
                if 0 <= _cg <= 3:
                    mom_inst, mom_yz, mom_note = 2.0, 2.5, f"当日温和上涨{_cg:+.1f}%（动量健康）"
                elif 3 < _cg <= 6:
                    mom_inst, mom_yz, mom_note = 1.0, 1.5, f"当日上涨{_cg:+.1f}%（动量偏强）"
                elif _cg > 6:
                    mom_inst, mom_yz, mom_note = 0.0, 1.0, f"当日大涨{_cg:+.1f}%（短线强但追高风险）"
                elif _cg < -3:
                    mom_inst, mom_yz, mom_note = 0.0, -1.5, f"当日大跌{_cg:+.1f}%（弱势）"
            except Exception:
                pass

        # ── 主力资金多周期共振（1/3/5日）── 弱辅助信号，与用户方法论一致
        mf1 = _fnum(ff.get("mainNetFlow1D")); mf3 = _fnum(ff.get("mainNetFlow3D")); mf5 = _fnum(ff.get("mainNetFlow5D"))
        if None not in (mf1, mf3, mf5):
            if mf1 <= 0 and mf3 <= 0 and mf5 <= 0:
                pen = min(12.0, pen + 8.0)   # 三周期主力均撤离 → 减分（弱辅助否决）
                rnotes.append(("主力资金", "近1/3/5日主力净流入全为负，资金持续撤离"))
            elif mf1 > 0 and mf3 > 0 and mf5 >= 0:
                fs_inst = min(12.0, fs_inst + 2.0)  # 共振确认 → 小幅加成
                fs_yz = min(10.0, fs_yz + 2.0)

        # ── ROE 质量门（需财务数据；缺则中性不罚）──
        roe = c.get("roe")
        if roe is None:
            roe = q.get("roe")
        if roe is not None:
            try:
                rv = float(roe)
                if rv < 5.0:
                    pen = min(12.0, pen + 4.0)
                    rnotes.append(("ROE", "ROE(TTM) %.1f%% < 5%%，质量偏弱" % rv))
            except Exception:
                pass

        # 游资方向 32 = 知名席位 20 + 买入额 8 + 席位家数 4
        yz = c.get("youzi") or {}
        yzs = 0.0
        if yz:
            yzs = (min(20.0, (yz.get("starCnt") or 0) * 10.0)
                   + min(8.0, float(yz.get("buy") or 0) / 1e8 * 6.0)
                   + min(4.0, (yz.get("seatCnt") or 0) * 0.8))

        exs_i = exs * 0.8
        total_inst = max(0.0, min(100.0, (inb + tps) + rts + mgs + fs_inst + q2s_inst
                                  + exs_i + bls + ts + chs_inst + mom_inst - pen - hpen))
        total_yz = max(0.0, min(100.0, yzs + fs_yz + q2s_yz + exs * 0.5 + bls_yz
                                + tsz + chs_yz + mgs_y + mom_yz - pen - hpen))

        base = {
            "code": code, "name": c.get("name"), "sw1": c.get("sw1"), "sw2": c.get("sw2"),
            "price": price, "chg": q.get("changePercent"), "turn": q.get("turnoverRate"),
            "open": q.get("open"), "close": q.get("price"),
            "pos52": q.get("week52Pos"), "behavior": behavior, "sector": sname,
            "inst": inst, "youzi": yz, "q2": q2, "exec": c.get("exec"), "block": bl,
            "chip": ch, "ff": ff, "consensus": con, "tpspace": tpspace,
            "rating": rt, "margin": mg, "risk": rk, "hotRank": (hk[0] if hk else None),
            "pen": round(-(pen + hpen), 1), "riskNotes": rnotes, "hits": c.get("hits", []),
        }
        extra_i = []
        extra_y = []
        if rtd:
            extra_i.append(rtd)
        if mgd:
            extra_i.append(mgd)
        if mgd_y and mgd_y != mgd:
            extra_y.append(mgd_y)
        if s["inst"] > 0 or c.get("track") == "inst":
            plan_i = plan_inst(q, t, ch)
            g, gn, ps, pn = grade(total_inst, close=price, t1=plan_i["t1"])
            inst_rows.append({**base, "score": round(total_inst, 1), "grade": g, "gname": gn,
                              "posStr": ps, "posNum": pn,
                              "detail": {"机构方向": round(inb + tps, 1), "机构评级": round(rts, 1),
                                         "两融": round(mgs, 1), "主力资金": round(fs_inst, 1),
                                         "中报背景": round(q2s_inst, 1), "高管": round(exs_i, 1),
                                         "大宗": round(bls, 1), "量价": round(ts, 1),
                                         "筹码": round(chs_inst, 1), "动量": round(mom_inst, 1)},
                              "plan": plan_i,
                              "notes": tn + chn_i + extra_i + ([exd] if exd else [])
                                      + ([mom_note] if mom_note else [])})
        if s["youzi"] > 0 or c.get("track") == "youzi":
            plan_y = plan_youzi(q, t, ch)
            g2, gn2, ps2, pn2 = grade(total_yz, close=price, t1=plan_y["t1"])
            youzi_rows.append({**base, "score": round(total_yz, 1), "grade": g2, "gname": gn2,
                               "posStr": ps2, "posNum": pn2,
                               "detail": {"游资方向": round(yzs, 1), "主力资金": round(fs_yz, 1),
                                          "中报背景": round(q2s_yz, 1), "高管": round(exs * 0.5, 1),
                                          "大宗": round(bls_yz, 1), "量价": round(tsz, 1),
                                          "筹码": round(chs_yz, 1), "两融": round(mgs_y, 1),
                                          "动量": round(mom_yz, 1)},
                               "plan": plan_y,
                               "notes": tnz + chn_y + extra_y + ([mom_note] if mom_note else [])})

    inst_rows.sort(key=lambda x: -x["score"])
    youzi_rows.sort(key=lambda x: -x["score"])
    # 档位按「轨道内相对分位」重定：双轨满分量级不同（机构约 83 / 游资约 95），
    # 共用一个绝对阈值会让机构轨永远无 A/B；两轨各设底线，弱市则该轨为空 → 空仓等待
    for _tk, _rows in (("inst", inst_rows), ("youzi", youzi_rows)):
        _n = len(_rows)
        for _i, _r in enumerate(_rows):
            _g, _gn, _ps, _pn = grade(_r["score"], close=_r.get("price"),
                                      t1=(_r.get("plan") or {}).get("t1"),
                                      pct=((_i + 1) / _n) if _n else 1.0, tk=_tk)
            _r["grade"], _r["gname"], _r["posStr"], _r["posNum"] = _g, _gn, _ps, _pn

    # ---- 出池门槛（2026-09-19 起，合并 MACD 三层漏斗的「20 日主力净流入为正」作技术确认）----
    # 实测（7 期 278 样本，134 个有 T+3）：A 档 T+3 均值 +2.96% / 胜率 83% / 3日触T1 58%；
    # B 档 -0.22% / 47%，反而不如"不建仓"的 D 档（+3.96% / 70%）→ B 及以下无区分度。
    # 故：A 档直接出池；B 档须通过技术确认（20 日主力净流入 > 0）才出池；C/D 一律不出。
    # 当日无任何出池标的 → 页面明示「今日无合格标的 · 空仓等待」，不硬凑。
    for _tk, _rows in (("inst", inst_rows), ("youzi", youzi_rows)):
        for _r in _rows:
            _mnf20 = (_r.get("ff") or {}).get("mainNetFlow20D")
            _ok20 = _mnf20 is not None and float(_mnf20) > 0
            _g = _r.get("grade")
            if _g == "A":
                _r["release"], _r["relNote"] = True, "最高档·直接出池"
            elif _g == "B" and _ok20:
                _r["release"], _r["relNote"] = True, "次高档·20日主力净流入为正，技术确认通过"
            elif _g == "B":
                _r["release"], _r["relNote"] = False, "次高档·20日主力净流出，未获技术确认"
            else:
                _r["release"], _r["relNote"] = False, "未达出池门槛"

    # ---- 历史 ----
    history = load_json(HIST, []) or []
    history = backfill(history)

    # ---- 观察池进出标记：新进 / 持续 / 取消观察 ----
    _arch = load_json(ARCHIVE, {}) or {}

    def day_quote(code, day):
        """取该票该日收盘与当日涨跌（来自日K档案，不依赖当日候选池）。"""
        a = _arch.get(code) or {}
        ds = [d for d in sorted(a) if d <= day]
        if not ds or ds[-1] != day:
            return None, None
        c = a[day].get("c")
        if c is None:
            return None, None
        if len(ds) >= 2:
            p0 = a[ds[-2]].get("c")
            if p0:
                return round((c - p0) / p0 * 100, 2), c
        return None, c

    prev_period = None
    for _h in sorted(history, key=lambda x: x["date"]):
        if _h["date"] < D:
            prev_period = _h

    def obs_streak(code):
        """截至上一期，连续入选观察池的期数。"""
        n = 0
        for _h in sorted(history, key=lambda x: x["date"], reverse=True):
            if _h["date"] >= D:
                continue
            codes = {p.get("code") for p in (_h.get("inst") or []) + (_h.get("youzi") or [])}
            if code in codes:
                n += 1
            else:
                break
        return n

    prev_pick = {}
    if prev_period:
        for _tk, _lab in (("inst", "机构轨"), ("youzi", "游资轨")):
            for _p in (prev_period.get(_tk) or []):
                _c0 = _p.get("code")
                if not _c0:
                    continue
                rec = prev_pick.get(_c0) or {"code": _c0, "name": _p.get("name"),
                                             "tracks": [], "score": _p.get("score"),
                                             "grade": _p.get("grade")}
                rec["tracks"].append(_lab)
                prev_pick[_c0] = rec

    today_codes = {r["code"] for r in inst_rows} | {r["code"] for r in youzi_rows}
    veto_map = {v["code"]: v for v in vetoed}

    for _r in inst_rows + youzi_rows:
        _n = obs_streak(_r["code"])
        _r["obsNew"] = _n == 0
        _r["obsTag"] = "新进" if _n == 0 else f"持续 {_n + 1} 期"

    dropped = []
    if prev_period:
        for _code, _rec in prev_pick.items():
            if _code in today_codes:
                continue
            _st = obs_streak(_code)
            _chg, _px = day_quote(_code, D)
            if _code in veto_map:
                kind, why, grp = "一票否决", "一票否决：" + (veto_map[_code].get("why") or ""), "out"
            elif _code in no_quote:
                # 区分「真停牌」与「上游限频没拉到行情」：日K档案有当日收盘 → 属后者
                if _px is not None:
                    kind, grp = "数据缺失", "pause"
                    why = ("当日行情未取到（上游限频降级，非停牌），本期无法评分 · 顺延跟踪")
                else:
                    kind, grp = "停牌", "pause"
                    why = "疑似停牌或当日无成交，暂停跟踪"
            elif _code not in cand_codes:
                kind, why, grp = "信号消失", "今日未进入候选池（三路信号均不再触发）", "out"
            else:
                kind, why, grp = "未达阈值", "仍在候选池，但今日双轨评分未达入选条件", "out"
            dropped.append({"code": _code, "name": _rec.get("name"),
                            "track": " / ".join(_rec.get("tracks") or ["—"]),
                            "score": _rec.get("score"), "grade": _rec.get("grade"),
                            "streak": _st, "kind": kind, "why": why, "group": grp,
                            "chg": _chg, "price": _px,
                            "from": prev_period.get("date")})
    dropped.sort(key=lambda x: -(x.get("score") or 0))
    # 本期此前已生成且已结算 → 取出逐只回填实测，合并进当前行（重渲染历史页时显示）
    prev_entry = next((h for h in history if h.get("date") == D), None)
    wbmap = {}
    if prev_entry and prev_entry.get("settled"):
        for _tk in ("inst", "youzi"):
            for _pk in (prev_entry.get(_tk) or []):
                if _pk.get("code"):
                    wbmap[_pk["code"]] = _pk
    for _r in inst_rows + youzi_rows:
        _pk = wbmap.get(_r["code"])
        if _pk:
            _r["wb"] = _pk

    def wb_cell(r):
        """表格里的回填列。"""
        w = r.get("wb") or {}
        if w.get("ret1") is None:
            return "<td class='muted'>待结算</td>"
        v = float(w["ret1"])
        cls = "up" if v >= 0 else "down"
        bits = [f"<b class='{cls}'>{v:+.2f}%</b>"]
        if w.get("ret5") is not None:
            v5 = float(w["ret5"])
            bits.append(f"<span class='muted'>5日</span> <b class='{'up' if v5 >= 0 else 'down'}'>{v5:+.2f}%</b>")
        elif w.get("nextChg") is not None:
            bits.append(f"<span class='muted'>次日 {float(w['nextChg']):+.2f}%</span>")
        if w.get("hitT1_1"):
            bits.append("<span class='chip'>触T1</span>")
        if w.get("hitStop_1"):
            bits.append("<span class='chip'>触止损</span>")
        return "<td>" + " ".join(bits) + "</td>"

    wb_summary = ""
    if prev_entry and prev_entry.get("settled"):
        def _wsum(tk):
            a = prev_entry.get(f"{tk}_ret1")
            if a is None:
                return "—"
            cls = "up" if a >= 0 else "down"
            n1 = prev_entry.get(f"{tk}_n1", 0)
            seg = (f"次日均涨 <b class='{cls}'>{a:+.2f}%</b>（{n1} 只）"
                   f"· 触T1 {prev_entry.get(f'{tk}_t1_1', 0)}"
                   f" · 触止损 {prev_entry.get(f'{tk}_st_1', 0)}")
            r5 = prev_entry.get(f"{tk}_ret5")
            if r5 is not None:
                seg += f" · 5日均涨 <b class=\"{'up' if r5 >= 0 else 'down'}\">{r5:+.2f}%</b>"
            return seg
        _sd = prev_entry.get("settleDate", "")
        wb_summary = (f"<div class='note'{tip_t('次日表现')}><b>回填实测（结算于 {_sd}）：</b>"
                      f"机构轨 {_wsum('inst')}｜游资轨 {_wsum('youzi')}。"
                      "收益以当期<b>进场参考价（区间中值）</b>为基准；当前样本仅数期，"
                      "只作机制运行证明，<b>不构成统计意义的胜率结论</b>。</div>")

    def fx_of(r):
        """落盘因子明细（供 quant/analyze_picks.py 做胜率归因）。"""
        ch = r.get("chip") or {}
        ff = r.get("ff") or {}
        return {"chg": r.get("chg"), "turn": r.get("turn"), "pos52": r.get("pos52"),
                "pr": ch.get("profitRate"), "conc": ch.get("conc90"), "cost": ch.get("avgCost"),
                "beh": r.get("behavior"), "hot": r.get("hotRank"),
                "mf": ff.get("mainNetFlow"), "mf1": ff.get("mainNetFlow1D"),
                "mf3": ff.get("mainNetFlow3D"), "mf5": ff.get("mainNetFlow5D"),
                "mf20": ff.get("mainNetFlow20D"),
                "tp": r.get("tpspace"), "inb": (r.get("inst") or {}).get("netBuy"),
                "yz": (r.get("youzi") or {}).get("starCnt"),
                "q2": (r.get("q2") or {}).get("addCnt"), "pen": r.get("pen")}

    entry = {
        "date": D,
        "nInst": len(inst_rows), "nYouzi": len(youzi_rows),
        # 存全部候选（非仅前 10），保证每只选股都能次日回填
        "inst": [{"code": r["code"], "name": r["name"], "score": r["score"], "grade": r["grade"],
                  "entry": r["plan"]["mid"], "stop": r["plan"]["stop"],
                  "t1": r["plan"]["t1"], "t2": r["plan"]["t2"],
                  "release": r.get("release"), "relNote": r.get("relNote"),
                  "detail": r["detail"], "fx": fx_of(r)} for r in inst_rows],
        "youzi": [{"code": r["code"], "name": r["name"], "score": r["score"], "grade": r["grade"],
                   "entry": r["plan"]["mid"], "stop": r["plan"]["stop"],
                   "t1": r["plan"]["t1"], "t2": r["plan"]["t2"],
                   "release": r.get("release"), "relNote": r.get("relNote"),
                   "detail": r["detail"], "fx": fx_of(r)} for r in youzi_rows],
        # 当日取消观察：上期在池、本期出局，含出局原因（供每日跟踪与复盘）
        "dropped": [{"code": d["code"], "name": d["name"], "track": d["track"],
                     "score": d["score"], "grade": d["grade"], "streak": d["streak"],
                     "kind": d["kind"], "why": d["why"], "chg": d["chg"],
                     "group": d["group"]} for d in dropped],
        "vetoed": [{"code": v["code"], "name": v["name"], "track": v["track"], "why": v["why"]}
                   for v in vetoed],
    }
    history = [h for h in history if h["date"] != D] + [entry]
    # 重渲染历史期时，保留旧 entry 已结算的回填数据（否则会被未结算的新 entry 抹掉）
    if prev_entry and prev_entry.get("settled"):
        entry["settled"] = True
        entry["settleDate"] = prev_entry.get("settleDate")
        for _tk in ("inst", "youzi"):
            for _k in ("ret1", "ret3", "ret5", "win1", "win3", "win5", "avg",
                       "t1_1", "t2_1", "st_1", "t1_3", "t2_3", "st_3",
                       "t1_5", "t2_5", "st_5", "n1", "n3", "n5", "n"):
                if prev_entry.get(f"{_tk}_{_k}") is not None:
                    entry[f"{_tk}_{_k}"] = prev_entry[f"{_tk}_{_k}"]
            _old = {p.get("code"): p for p in (prev_entry.get(_tk) or [])}
            for _np in entry.get(_tk) or []:
                _op = _old.get(_np.get("code"))
                if not _op:
                    continue
                # 历史记录以首算为准：分数/档位/进场价不随重渲染漂移
                for _k in ("score", "grade", "entry", "stop", "t1", "t2"):
                    if _op.get(_k) is not None:
                        _np[_k] = _op[_k]
                for _k in ("ret1", "ret3", "ret5", "nextChg",
                           "hitT1_1", "hitT2_1", "hitStop_1",
                           "hitT1_3", "hitT2_3", "hitStop_3",
                           "hitT1_5", "hitT2_5", "hitStop_5"):
                    if _op.get(_k) is not None:
                        _np[_k] = _op[_k]
    history.sort(key=lambda h: h["date"])
    with open(HIST, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=1)

    def cards_html(rows, kind):
        out = []
        for r in rows[:10]:
            p = r["plan"]
            sigs = []  # (说明键, 展示文本)
            if r["inst"].get("netBuy"):
                sigs.append(("机构净买", f"机构净买 {yi(r['inst']['netBuy'])}"))
            if r["inst"].get("branchMax"):
                sigs.append(("机构席位", f"机构席位 {r['inst']['branchMax']} 家"))
            if r["tpspace"]:
                sigs.append(("目标价空间", f"目标价空间 {r['tpspace']:+.0f}%"))
            if r["youzi"].get("starCnt"):
                sigs.append(("知名席位", f"知名席位 {r['youzi']['starCnt']} 次"))
            if r["youzi"].get("buy"):
                sigs.append(("游资买入", f"游资买入 {yi(r['youzi']['buy'])}"))
            if r["ff"].get("mainNetFlow"):
                sigs.append(("主力当日", f"主力当日 {yi(r['ff']['mainNetFlow'])}"))
            if r["chip"].get("profitRate") is not None:
                sigs.append(("获利盘", f"获利盘 {r['chip']['profitRate']:.0f}%"))
            if r["behavior"]:
                sigs.append(("板块行为", f"板块{r['behavior']}"))
            sigs_html = "".join(
                f"<span class='chip'{tip_t(key)}>{esc(txt)}</span>" for key, txt in sigs)
            det = " · ".join(
                f"<span{tip(k2)}>{esc(k2)} {v}</span>" for k2, v in r["detail"].items())
            risk = ("<div class='sig'>⚠ " + esc("、".join(r["riskNotes"])) + "</div>"
                    if r["riskNotes"] else "")
            wbk = r.get("wb") or {}
            if wbk.get("ret1") is not None:
                v1 = float(wbk["ret1"])
                c1 = "up" if v1 >= 0 else "down"
                seg = f"相对进场价 <b class='{c1}'>{v1:+.2f}%</b>"
                if wbk.get("nextChg") is not None:
                    seg += f"（当日 {float(wbk['nextChg']):+.2f}%）"
                if wbk.get("hitT1_1"):
                    seg += " · <b class='up'>已触目标一</b>"
                if wbk.get("hitStop_1"):
                    seg += " · <b class='down'>已触止损</b>"
                wb_line = f"<div class='sig'{tip_t('次日表现')}><b>回填实测（T+1）：</b>{seg}</div>"
            else:
                wb_line = ""
            out.append(f"""
  <div class='card hi'>
    <div class='chead'>
      <span class='cname'>{esc(r['name'])}</span>
      <span class='ccode'>{esc(r['code'])} · {esc(r.get('sw1') or '—')}</span>
      <span class='badge b{r['grade']}'{tip_t('档位')}>{r['grade']} {esc(r['gname'])}</span>
      <span class='obs {'new' if r.get('obsNew') else 'keep'}'>{esc(r.get('obsTag') or '')}</span>
      <span style='margin-left:auto' class='score'{tip_t('总分')}>{r['score']}</span>
    </div>
    <div class='grid'>
      <div class='kv tipbox'{tip_t('现价')}><div class='k tipk'>现价</div><div class='v'>{fnum(r['price'])} <span class='{"up" if (r["chg"] or 0) >= 0 else "down"}' style='font-size:12px'>{pct(r['chg'])}</span></div></div>
      {oc_kv(r)}
      {gap_kv(r)}
      <div class='kv tipbox'{tip_t('进场区间')}><div class='k tipk'>进场区间</div><div class='v sm'>{fnum(p['lo'])} ~ {fnum(p['hi'])}</div></div>
      <div class='kv tipbox'{tip_t('止损')}><div class='k tipk'>止损</div><div class='v sm down'>{fnum(p['stop'])}（{p['stopPct']}%）</div></div>
      <div class='kv tipbox'{tip_t('目标一')}><div class='k tipk'>目标一 / 二</div><div class='v sm up'>{fnum(p['t1'])} / {fnum(p['t2'])}</div></div>
      <div class='kv tipbox'{tip_t('盈亏比')}><div class='k tipk'>盈亏比</div><div class='v sm'>{p['rr']}</div></div>
      <div class='kv tipbox'{tip_t('仓位')}><div class='k tipk'>仓位 / 周期</div><div class='v sm'>{esc(r['posStr'])} · {esc(p['hold'])}</div></div>
    </div>
    <div class='sig'><b>信号：</b>{sigs_html}</div>
    <div class='sig'><b>打分：</b>{det} · <span{tip('风险')}>风险 {r['pen']}</span></div>
    <div class='sig'><b>介入：</b>{esc(p['note'])}；<b>失效：</b>跌破 {fnum(p['stop'])} 无条件离场。</div>
    {wb_line}
    {risk}
  </div>""")
        return "".join(out)

    def gap_cells(r):
        """以当日收盘价为基准，到止损位 / 目标一的盈亏比例。"""
        px = r.get("close") or r.get("price") or 0
        st = r["plan"].get("stop")
        t1 = r["plan"].get("t1")
        if not px:
            return "<td>—</td><td>—</td>"
        if st:
            gs = (st - px) / px * 100
            broke = gs >= 0
            a = "<td class='%s'>%+.1f%%%s</td>" % ("up" if broke else "down", gs,
                                                   " 已破" if broke else "")
        else:
            a = "<td>—</td>"
        b = "<td class='up'>%+.1f%%</td>" % ((t1 - px) / px * 100) if t1 else "<td>—</td>"
        return a + b

    def oc_kv(r):
        return ("<div class='kv tipbox'%s><div class='k tipk'>今开 / 收盘</div>"
                "<div class='v sm'>%s / %s</div></div>"
                % (tip_t("今开"), fnum(r.get("open")), fnum(r.get("close") or r.get("price"))))

    def gap_kv(r):
        """以当日收盘价为基准，到止损位 / 目标一的盈亏比例。"""
        px = r.get("close") or r.get("price") or 0
        st = r["plan"].get("stop")
        t1 = r["plan"].get("t1")
        if not px:
            return ""
        gs = (st - px) / px * 100 if st else None
        gt = (t1 - px) / px * 100 if t1 else None
        a = "—" if gs is None else ("%+.1f%%%s" % (gs, " 已破" if gs >= 0 else ""))
        b = "—" if gt is None else ("%+.1f%%" % gt)
        cls = "up" if (gs is not None and gs >= 0) else "down"
        return ("<div class='kv tipbox'%s><div class='k tipk'>距止损 / 距目标一</div>"
                "<div class='v sm'><span class='%s'>%s</span> / <span class='up'>%s</span></div></div>"
                % (tip_t("距止损"), cls, a, b))

    FEAT_CN = {"vol_day": "量比低", "pullback_dry": "缩量回调", "dist_hi20": "贴近20日高",
               "ovn20": "隔夜承接", "atr_comp": "波动收敛", "grow_rev": "营收同比",
               "grow_q": "单季净利", "roe": "ROE", "mv_log": "小市值",
               "ep": "盈利收益率", "bp": "账面市值比", "amt20_log": "小成交额"}

    def stable_cell(r):
        v = r.get("stableScore")
        if v is None:
            return "<td class='muted'>—</td>"
        cls = "up" if v >= 60 else ("down" if v < 40 else "")
        rk = r.get("stableRank") or {}
        top = sorted(rk.items(), key=lambda kv: -kv[1])[:2]
        sub = "、".join(FEAT_CN.get(k, k) for k, _ in top) if top else ""
        return ("<td class='%s'><b>%.0f</b><br>"
                "<span class='muted' style='font-size:10.5px'>%s</span></td>"
                % (cls, v, esc(sub)))

    def table_html(rows):
        return "".join(
            f"<tr><td>{esc(r['name'])}<span class='obs {'new' if r.get('obsNew') else 'keep'}'>"
            f"{esc(r.get('obsTag') or '')}</span></td><td class='muted'>{esc(r['code'])}</td>"
            f"<td>{esc(r.get('sw1') or '—')}</td><td>{esc(r.get('behavior') or '—')}</td>"
            f"<td><b>{r['score']}</b></td>"
            f"{stable_cell(r)}"
            f"<td class='{"up" if (r["chg"] or 0) >= 0 else "down"}'>{pct(r['chg'])}</td>"
            f"<td>{fnum(r.get('open'))}</td><td>{fnum(r.get('close'))}</td>"
            f"<td>{fnum(r['turn'])}</td><td>{fnum(r['pos52'], 0)}</td>"
            f"<td>{fnum((r['chip'] or {}).get('profitRate'), 0)}</td>"
            f"<td>{esc(r['plan']['stop'])}</td><td>{esc(r['plan']['t1'])}</td>"
            f"{gap_cells(r)}"
            f"<td><span class='badge b{r['grade']}'{tip_t('档位')}>{r['grade']}</span></td>"
            f"{wb_cell(r)}</tr>"
            for r in rows)

    def cd_block(rows, label):
        """C/D 档折叠为「仅跟踪」：用户要求不再选 C/D，但保留可追溯。"""
        if not rows:
            return ""
        rr = []
        for r in rows:
            rr.append(
                f"<tr><td>{esc(r['name'])}</td><td class='muted'>{esc(r['code'])}</td>"
                f"<td>{r['score']}</td>"
                f"<td><span class='badge b{r['grade']}'>{r['grade']}</span> {esc(r['gname'])}</td>"
                f"<td class='{'up' if (r['chg'] or 0) >= 0 else 'down'}'>{pct(r['chg'])}</td>"
                f"<td>{fnum(r.get('close'))}</td>"
                f"<td>{fnum(r['plan']['stop'])}</td><td>{fnum(r['plan']['t1'])}</td>"
                f"{wb_cell(r)}</tr>")
        return (f"<details class='veto' style='margin-top:12px'><summary style='cursor:pointer'>"
                f"<b>仅跟踪 · {label} C/D 档 {len(rows)} 只</b>"
                "<span class='muted'>（不建议建仓 · 点击展开）</span></summary>"
                "<table style='margin-top:8px'><thead><tr><th>名称</th><th>代码</th><th>总分</th>"
                "<th>档位</th><th>当日</th><th>收盘</th><th>止损</th><th>目标一</th>"
                "<th>次日表现</th></tr></thead><tbody>" + "".join(rr) + "</tbody></table></details>")

    def th(key, label):
        return f"<th{tip(key)}>{label}</th>"

    # —— 稳健分（pick_score.py）：先验固定因子集 · 等权 · 横截面分位 ——
    try:
        import pick_score as _PS
        _codes_all = [r["code"] for r in (inst_rows + youzi_rows)]
        # 原则9：分位基准改为「全市场可交易域」，候选只作展示过滤。
        # 旧口径在异动票子集内算分位 → 分数被压扁（同因子池内最高分仅66.6 vs 全市场79+），
        # 且出现「分档反向」的过拟合信号。改用全市场域后，稳健分反映「相对全市场的位置」。
        _univ = list(_PS.all_codes())
        _SS = _PS.score_codes(_codes_all, D, universe=_univ)
        _ENV = _PS.env_state(D)
    except Exception as _e:
        _SS = {}
        _ENV = {"breadth": None, "coef": 1.0, "label": "环境数据不可用"}
        print("[build_picks] 稳健分不可用：%s" % _e)
    for _r in (inst_rows + youzi_rows):
        _v = _SS.get(_r["code"])
        _r["stableScore"] = _v["score"] if _v else None
        _r["stableRank"] = _v["rank"] if _v else {}
        _r["stableRaw"] = _v["raw"] if _v else {}

    THEAD = ("<thead><tr>" + th("名称", "名称") + th("代码", "代码") + th("行业", "行业")
             + th("板块", "板块")              + th("总分", "总分") + th("稳健分", "稳健分")
             + th("当日", "当日")
             + th("今开", "今开") + th("收盘", "收盘")
             + th("换手", "换手%") + th("52周位", "52周位") + th("获利盘", "获利盘%")
             + th("止损", "止损") + th("目标一", "目标一")
             + th("距止损", "距止损%") + th("距目标一", "距目标一%") + th("档位", "档")
             + th("次日表现", "回填") + "</tr></thead>")

    na = sum(1 for r in inst_rows if r["grade"] == "A")
    nb = sum(1 for r in inst_rows if r["grade"] == "B")
    nya = sum(1 for r in youzi_rows if r["grade"] == "A")
    nyb = sum(1 for r in youzi_rows if r["grade"] == "B")
    # 只主推 A/B（用户要求：C/D 不再作为可选项），C/D 折叠为「仅跟踪」
    # 2026-09-19 起：主区只放「已出池」标的（A 档 + 通过技术确认的 B 档）
    inst_ab = [r for r in inst_rows if r.get("release")]
    inst_cd = [r for r in inst_rows if not r.get("release")]
    youzi_ab = [r for r in youzi_rows if r.get("release")]
    youzi_cd = [r for r in youzi_rows if not r.get("release")]
    empty_ab = ("<div class='muted' style='padding:10px 0'>本期该轨<b>无合格出池标的</b>"
                " —— 当日整体偏弱或分数未达门槛，按纪律空仓等待，不硬凑低胜率标的。</div>")
    # 顶部结论卡：今日到底有没有可买的
    _rel_all = len(inst_ab) + len(youzi_ab)
    if _rel_all:
        release_banner = (
            "<div class='note' style='border-left:4px solid #b8893b'>"
            "<b>今日结论：出池 " + str(_rel_all) + " 只</b>"
            "（机构轨 " + str(len(inst_ab)) + " · 游资轨 " + str(len(youzi_ab)) + "）——"
            " 均为 A 档或通过「20 日主力净流入为正」技术确认的 B 档。"
            "其余 " + str(len(inst_cd) + len(youzi_cd)) + " 只已折叠为「仅跟踪」，<b>不作为建仓选项</b>。</div>")
    else:
        release_banner = (
            "<div class='note warn' style='border-left:4px solid #d93025'>"
            "<b>今日结论：无合格标的 · 建议空仓等待</b><br>"
            "全部候选均未达出池门槛（A 档空缺，且 B 档未通过 20 日主力净流入为正的技术确认）。"
            "按「宁可没有，也不要低胜率标的」的纪律，<b>本期不出任何建仓建议</b>。</div>")

    # —— 环境门控 + 稳健分说明（来自 picks/lab.html 的样本外实验室） ——
    _ec = _ENV.get("coef", 1.0)
    _ec_col = "#1a7a45" if _ec >= 1.0 else ("#b7791f" if _ec >= 0.7 else "#c0392b")
    _ec_txt = "可正常配置" if _ec >= 1.0 else ("建议降至七成" if _ec >= 0.7 else "建议降至四成或空仓")
    _sb = ""
    if _SS:
        _name = {r["code"]: r["name"] for r in (inst_rows + youzi_rows)}
        _top = sorted(_SS.items(), key=lambda kv: -kv[1]["score"])[:3]
        _sb = ("<b>稳健分最高的 3 只：</b>"
               + "、".join("%s %.0f" % (esc(_name.get(c) or c), v["score"]) for c, v in _top)
               + "（满分 100，仅表排序强弱，不构成推荐）。<br>")
    env_banner = (
        "<div class='note' style='border-left:4px solid " + _ec_col + "'>"
        "<b>环境门控：" + esc(_ENV.get("label") or "未知")
        + " · 建议仓位系数 %.1f（%s）</b><br>" % (_ec, _ec_txt)
        + "实测在同一批异动票里「随便买」的绝对胜率：<b>弱势环境 40.9%</b> vs <b>强势环境 51.1%</b> —— "
        "差 10.1pp，<b>比选股本身能带来的 1~3pp 大得多</b>。所以弱势期该做的是降低暴露，"
        "而不是继续在弱势里精挑细选。<br>" + _sb
        + "<b>稳健分</b>（表内新列）＝独立于「总分」的第二个口径：固定价量 5 项 + 基本面 7 项、等权、"
        "在<b>全市场可交易域</b>做横截面分位（候选只作展示过滤），<b>不按回测调权重</b>。原因：实测「自动筛因子」在严格样本外只剩 +0.5pp，"
        "筛选动作本身就是噪声源；而先验固定因子集在留出段 相对胜率 +4.9pp / 绝对胜率 +1.4pp，6 段滚动全部为正。"
        "<a href='lab.html' style='color:#b8893b;text-decoration:none;font-weight:600'>"
        "查看完整证据与局限 →</a></div>"
    )

    veto_html = ""
    if vetoed:
        _vl = "".join(
            f"<li><b>{esc(v['name'])}</b> <span class='muted'>{esc(v['code'])} · {esc(v['track'])}</span>"
            f" —— {esc(v['why'])}</li>" for v in vetoed)
        veto_html = ("<details class='veto'><summary style='cursor:pointer'><b>已剔除 "
                     + str(len(vetoed)) + " 只（触发一票否决 · 点击展开名单）</b></summary>"
                     + "<ul style='margin:8px 0 0 20px;padding:0'>" + _vl + "</ul></details>")

    # ---- 当日取消观察：上期在池、本期出局 ----
    drop_html = ""
    drop_summary = ""
    if dropped:
        _out = [d for d in dropped if d.get("group") == "out"]
        _pause = [d for d in dropped if d.get("group") == "pause"]

        def _dtable(items):
            _rr = []
            for _d in items:
                _c = "up" if (_d.get("chg") or 0) >= 0 else "down"
                _g = _d.get("grade") or "D"
                _rr.append(
                    f"<tr><td>{esc(_d.get('name') or '—')}</td><td class='muted'>{esc(_d['code'])}</td>"
                    f"<td>{esc(_d.get('track') or '—')}</td>"
                    f"<td><span class='badge b{_g}'>{esc(_g)}</span> {fnum(_d.get('score'))}</td>"
                    f"<td class='{_c}'>{pct(_d.get('chg'))}</td>"
                    f"<td>{_d.get('streak') or 0} 期</td>"
                    f"<td class='why'>{esc(_d.get('why') or '')}</td></tr>")
            return ("<table><thead><tr><th>名称</th><th>代码</th><th>原轨道</th>"
                    "<th>上期档位 · 评分</th><th>当日涨跌</th><th>连续观察</th>"
                    "<th>取消原因</th></tr></thead><tbody>" + "".join(_rr) + "</tbody></table>")

        drop_html = (
            f"<div class='section dropsec'><h2 id='dropped'>当日取消观察 · {len(_out)} 只</h2>"
            f"<div class='muted' style='margin-bottom:8px'>相对上一期（{esc(prev_period.get('date'))}）"
            "在池、本期出局的个股。取消只代表<b>规则口径下不再跟踪</b>，"
            "不等于看空；原因分四类：一票否决 / 信号消失 / 未达阈值 / 数据缺失或停牌（见下方「暂停跟踪」）。</div>"
            + (_dtable(_out) if _out else "<div class='muted'>本期无规则口径出局个股。</div>"))
        if _pause:
            drop_html += (
                f"<h3 style='font-size:15px;margin:22px 0 10px'>暂停跟踪 · {len(_pause)} 只"
                "<span class='muted' style='font-weight:400;font-size:12px'>"
                "（数据缺失或停牌，非规则出局，恢复后自动回归）</span></h3>" + _dtable(_pause))
        drop_html += "</div>"
        drop_summary = ("<div class='dropsum'><b>当日取消观察 " + str(len(_out)) + " 只</b>"
                        + (f" · 暂停跟踪 {len(_pause)} 只" if _pause else "")
                        + f"（相对 {esc(prev_period.get('date'))}）："
                        + "、".join(f"{esc(_d.get('name') or '—')}（{esc(_d.get('kind') or '')}）"
                                    for _d in (_out or dropped)[:10])
                        + ("…" if len(_out or dropped) > 10 else "")
                        + " · <a href='#dropped' style='color:#8c2b2b'>查看明细</a></div>")

    # 高管增减持数据源口径标注（东财回补期：变动日口径、覆盖约 76%）
    exec_src_note = ""
    _ej = load_json(os.path.join(ROOT, "quant", "exec_chg", f"{D}.json"), {}) or {}
    if "eastmoney" in str(_ej.get("source") or "").lower():
        exec_src_note = ("<div class='note warn' style='margin-top:8px'><b>数据源口径：</b>"
                         f"{D} 高管增减持源为<b>东财数据中心</b>（westock 事件接口降级期回补），"
                         "日期口径为<b>变动日</b>（非披露日）、全市场覆盖约 <b>76%</b>"
                         "（缺科创板 688 与股权激励类），高管维度得分可能偏低；westock 恢复后自动回归原口径。</div>")

    html = f"""<!DOCTYPE html>
<html lang='zh-CN'><head><meta charset='UTF-8'>
<meta name='viewport' content='width=device-width,initial-scale=1.0'>
<title>个股信号池 · {D}</title><style>{CSS}</style></head><body>
<div class='wrap'>
{nav()}
<header><h1><span>个股信号池</span> · {D}</h1>
<div class='sub'>机构轨（波段 5~15 日）与 游资轨（短线 1~3 日）双池分轨打分，含板块闸门与筹码/资金流确认，每日盘后更新并回填次日表现。
<div class='muted' style='margin-top:6px'>字段旁带 <span class='tip' style='border:none'>?</span> 或虚线下划线的均可悬浮查看计算口径。</div></div></header>

<div class='note'><b>今日结论：</b>机构轨 {len(inst_rows)} 只（A {na} / B {nb}）· 游资轨 {len(youzi_rows)} 只（A {nya} / B {nyb}）。<br>
<span class='muted'>档位口径 = 当日<b>该轨道内相对分位</b>（前 15% 为 A、前 40% 为 B），并设绝对底线 45 分——整体偏弱或数据降级时该轨可能无 A/B，此时建议空仓等待。</span><br>
<span class='muted'><b>实测（7 期 278 样本）：A 档 T+3 均值 +2.96% / 胜率 83% / 3 日触 T1 58%；B 档 −0.22% / 47%，反而不如「不建仓」的 D 档（+3.96% / 70%）——故 B 档须再过技术确认才出池。</b></span><br>
<span{tip('Gate')}>闸门</span>：所属板块主力出货、获利盘 &gt;90%、<b>获利盘 &lt;20% 且位置偏弱</b>、现价高于成本 30%、空头排列破 MA60、RSI&gt;80、解禁 ≥1%、减持窗口、质押 &gt;30% 一律剔除。</div>
{release_banner}
{env_banner}
{veto_html}
{drop_summary}
{exec_src_note}
{wb_summary}

<div class='section'><h2>机构轨 · 波段<span class='trk i'>5~15 日</span></h2>
<div class='muted' style='margin-bottom:8px'>机构方向 16（龙虎榜机构净买入 10 + 目标价空间 6）+ 机构评级 4 + 两融 6 + 主力资金 8（5日 6 + 1/3/5 共振 2）+ 中报背景 1.5 + 高管 6.4 + 大宗 6 + 量价 24 + 筹码 10 + 动量 ≤2 − 风险 ≤12 − 热度反向 ≤4<br>
<span class='muted'>2026-09-18 按近 5 期实测归因重调权重：筹码 / 量价 / 动量 / 主力资金（5日）为正向因子已提权；中报背景、机构评级、龙虎榜机构净买入与 T+1 负相关已降权；主力 20 日净流入确认为反向已剔除。</span></div>
{table_html(inst_ab) and "<table>" + THEAD + "<tbody>" + table_html(inst_ab) + "</tbody></table>" or empty_ab}
{cards_html(inst_ab, 'inst')}
{cd_block(inst_cd, '机构轨')}</div>

<div class='section'><h2>游资轨 · 短线<span class='trk y'>1~3 日</span></h2>
<div class='muted' style='margin-bottom:8px'>游资方向 30（知名席位 18 + 买入额 8 + 席位家数 4）+ 量价 30 + 筹码 12 + 两融 8 + 主力资金 6（当日）+ 动量 ≤2.5 + 中报 1 + 高管 5 + 大宗 5 − 风险 ≤12 − 热度反向 ≤4</div>
{table_html(youzi_ab) and "<table>" + THEAD + "<tbody>" + table_html(youzi_ab) + "</tbody></table>" or empty_ab}
{cards_html(youzi_ab, 'youzi')}
{cd_block(youzi_cd, '游资轨')}</div>

{drop_html}

<div class='note warn'><b>风险提示：</b>本页为量化规则输出，<b>不构成投资建议</b>。中报数据截至 2026-06-30 已滞后，仅作背景参考；
游资轨波动剧烈、须严格执行紧止损。所有买卖点来自公开数据与固定公式，不含基本面判断，务必自行核验并控制单票亏损不超过总资金 2%。</div>

<footer>数据源：westock-mcp（行情 / 技术指标 / 资金流 / 筹码 / 一致预期 / 龙虎榜 / 高管变动 / 大宗）· 中报十大流通股东（2026-06-30）<br>
生成脚本 <code>quant/gen_picks.py</code> + <code>quant/build_picks.py</code> · 仅供参考，不构成投资建议。</footer>
</div></body></html>"""

    p1 = os.path.join(PICKS_WEB, f"pick_{D}.html")
    with open(p1, "w", encoding="utf-8") as f:
        f.write(html)

    # ---- 归档首页 ----
    def hist_row(h):
        def cell(tk):
            # 回填写入的是 h["settled"] 与 {tk}_t1_1 / {tk}_n1 / {tk}_st_1（多周期后缀）
            if not h.get("settled"):
                return "<span class='muted'>待回填</span>"
            avg = h.get(f"{tk}_ret1", h.get(f"{tk}_avg"))
            if avg is None:
                return "<span class='muted'>待回填</span>"
            cls = "up" if avg >= 0 else "down"
            n1 = h.get(f"{tk}_n1", 0)
            parts = [f"<b class='{cls}'>{pct(avg)}</b>",
                     f"触T1 {h.get(f'{tk}_t1_1', 0)}/{n1}",
                     f"触止损 {h.get(f'{tk}_st_1', 0)}"]
            r5 = h.get(f"{tk}_ret5")
            if r5 is not None:
                cls5 = "up" if r5 >= 0 else "down"
                parts.append(f"5日 <b class='{cls5}'>{pct(r5)}</b>")
            return " · ".join(parts)
        ni = len(h.get("inst", []) or [])
        ny = len(h.get("youzi", []) or [])
        nd = len([x for x in (h.get("dropped") or []) if x.get("group") != "pause"])
        dcell = (f"<a href='pick_{h['date']}.html#dropped'>{nd}</a>" if nd
                 else "<span class='muted'>—</span>")
        return (f"<tr><td><a href='pick_{h['date']}.html'>{h['date']}</a></td>"
                f"<td>{ni}</td><td>{cell('inst')}</td><td>{ny}</td><td>{cell('youzi')}</td>"
                f"<td>{dcell}</td></tr>")

    ti = sum(h.get("inst_n1", 0) for h in history if h.get("settled"))
    ty = sum(h.get("youzi_n1", 0) for h in history if h.get("settled"))

    def wr(tk, tot):
        if not tot:
            return "<span class='muted'>首期尚无回填</span>"
        h1 = sum(h.get(f"{tk}_t1_1", 0) for h in history if h.get("settled"))
        hs = sum(h.get(f"{tk}_st_1", 0) for h in history if h.get("settled"))
        avgs = [h.get(f"{tk}_ret1", h.get(f"{tk}_avg")) for h in history
                if h.get("settled") and h.get(f"{tk}_ret1", h.get(f"{tk}_avg")) is not None]
        a = sum(avgs) / len(avgs) if avgs else 0
        return f"触T1 {h1}/{tot}（{h1 / tot * 100:.0f}%）· 触止损 {hs} · 次日均涨 {pct(a)}"

    t_cnt = tip_t("候选数")
    t_nx = tip_t("次日表现")
    t_dim = tip("维度")
    t_wi = tip("机构轨权重")
    t_wy = tip("游资轨权重")
    t_cal = tip("口径")
    t_drop = tip_t("取消观察")

    # 高胜率候选池入口（多因子扫描产物，链接最新一期，避免孤儿页）
    hw_files = sorted(glob.glob(os.path.join(PICKS_WEB, "highwin_*.html")))
    hw_block = ""
    if hw_files:
        _hw = os.path.basename(hw_files[-1])
        _hwd = re.search(r"highwin_(\d{8})\.html", _hw)
        _hwd = ("%s-%s-%s" % (_hwd.group(1)[:4], _hwd.group(1)[4:6], _hwd.group(1)[6:8])) if _hwd else "最新"
        hw_block = (f"<div class='note'><b>高胜率候选池（多因子扫描）：</b>"
                    f"<a href='{esc(_hw)}'>{_hwd}</a> —— 以 MACD 水上金叉池为基底，"
                    f"叠加趋势/位置/量价/资金/筹码/板块/龙虎榜/高管大宗八维打分与分层"
                    f"（核心 / 观察 / 备选 / 回避），另附「历史入选」标记。</div>")

    # 全市场稳健分选股入口（scan_stable.py 产物，链接最新一期，避免孤儿页）
    # ★ 历史各期也必须在本页静态入链：_fix_orphans 插的归档块会被本生成器整页重写抹掉，
    #   只链最新一期 → 其余 stable_*.html 全部变孤儿（_page_registry 的 picks_stable 族可见）。
    stable_block = ""
    stable_arch = ""
    _stf = os.path.join(PICKS_WEB, "stable_%s.html" % D)
    _stj = os.path.join(PICKS_DATA, "stable_%s.json" % D)
    if os.path.exists(_stf) and os.path.exists(_stj):
        try:
            _sj = load_json(_stj, {}) or {}
            _su = _sj.get("universe") or {}
            _se = _sj.get("env") or {}
            _sm = (_sj.get("stats") or {}).get("median")
            stable_block = (
                f"<div class='note' style='border-left:4px solid #b8893b'>"
                f"<b>全市场稳健分选股：</b><a href='stable_{D}.html'>{D}</a> —— "
                f"把「稳健分」用回它的正确用法：在<b>可交易域 {_su.get('kept', '—')} 只</b>内做全市场横截面排序"
                f"（剔除 ST/退市、停牌、低流动、低价），而不是只在几十只事件驱动候选里排队。"
                f"环境门控：<b>{esc(str(_se.get('label') or '—'))}</b>，建议仓位系数 <b>{esc(str(_se.get('coef')))}</b>；"
                f"域内分数中位 {esc(str(_sm))}。</div>")
        except Exception:
            stable_block = ""

    try:
        import glob as _glob
        _grp = []
        for _pfx, _lbl in (("stable_", "稳健分选股"), ("highwin_", "高胜率候选池")):
            _ds = []
            for p in _glob.glob(os.path.join(PICKS_WEB, _pfx + "*.html")):
                _b = os.path.basename(p)
                _d = _b[len(_pfx):-5]
                _d = ("%s-%s-%s" % (_d[:4], _d[4:6], _d[6:8])) if re.fullmatch(r"\d{8}", _d) else _d
                if _d != D:
                    _ds.append((_d, "%s%s.html" % (_pfx, _d.replace("-", "")) if _pfx == "highwin_" else "%s%s.html" % (_pfx, _d)))
            if _ds:
                _ln = "".join("<a href='%s'>%s</a>" % (h, d) for d, h in _ds)
                _grp.append("<div class='section'><h2>%s历史归档</h2><div class='arch'>%s</div></div>" % (_lbl, _ln))
        stable_arch = "".join(_grp)
    except Exception:
        stable_arch = ""

    idx = f"""<!DOCTYPE html>
<html lang='zh-CN'><head><meta charset='UTF-8'>
<meta name='viewport' content='width=device-width,initial-scale=1.0'>
<title>个股信号池 · 每日归档</title><style>{CSS}</style></head><body>
<div class='wrap'>
{nav()}
<header><h1><span>个股信号池</span> · 每日归档</h1>
<div class='sub'>机构轨（波段）+ 游资轨（短线）双池输出建仓候选与买卖点，次日自动回填表现并统计胜率。</div></header>

<div class='note'><b>最新一期：</b><a href='pick_{D}.html'>{D}</a> —— 机构轨 {len(inst_rows)} 只（A {na} / B {nb}）· 游资轨 {len(youzi_rows)} 只（A {nya} / B {nyb}）· 实际出池 {len(inst_ab) + len(youzi_ab)} 只（其余折叠为仅跟踪）· 取消观察 {len([d for d in dropped if d.get('group') != 'pause'])} 只（<a href='pick_{D}.html#dropped'>明细</a>）。</div>
{hw_block}
{stable_block}
{stable_arch}

<div class='section'{tip_t('历史表现')}><h2>历史表现（多周期回填）</h2>
<div class='note'>机构轨累计 {wr('inst', ti)}<br>游资轨累计 {wr('youzi', ty)}</div>
<table><thead><tr><th>日期</th><th{t_cnt}>机构轨</th><th{t_nx}>机构轨次日</th><th{t_cnt}>游资轨</th><th{t_nx}>游资轨次日</th><th{t_drop}>取消观察</th></tr></thead>
<tbody>{"".join(hist_row(h) for h in reversed(history))}</tbody></table></div>

<div class='section'><h2>双池评分模型</h2>
<table><thead><tr><th{t_dim}>维度</th><th{t_wi}>机构轨</th><th{t_wy}>游资轨</th><th{t_cal}>口径</th></tr></thead><tbody>
<tr><td{tip('机构方向')}>方向分</td><td>28</td><td>30</td><td>机构：龙虎榜机构净买入 18 + 一致预期目标价空间 10 / 游资：知名席位现身 18 + 买入额 8 + 席位家数 4</td></tr>
<tr><td{tip('机构评级')}>机构评级</td><td>8</td><td>—</td><td>覆盖机构家数 + 买入占比（data_rating）</td></tr>
<tr><td{tip('两融')}>两融</td><td>6</td><td>8</td><td>融资余额环比（杠杆进场为正）；融券大增为负（data_fund_margin）</td></tr>
<tr><td{tip('主力资金')}>主力资金</td><td>10</td><td>10</td><td>机构看 5日/20日主力净流入（中期）；游资看当日主力净流入</td></tr>
<tr><td{tip('中报背景')}>中报背景</td><td>8</td><td>5</td><td>Q2 十大流通股东加仓家数（已降权为背景项，滞后 72 天）</td></tr>
<tr><td{tip('高管')}>高管增减持</td><td>8</td><td>5</td><td>按 变动金额 / 总市值 归一化，过滤象征性小额增持</td></tr>
<tr><td{tip('大宗')}>大宗交易</td><td>6</td><td>5</td><td>机构专用买入、溢价 / 折价</td></tr>
<tr><td{tip('量价')}>量价</td><td>20</td><td>28</td><td>趋势结构 + 量能 + 动量 + 相对位置</td></tr>
<tr><td{tip('筹码')}>筹码</td><td>6</td><td>9</td><td>获利盘比例、现价与平均成本偏离、筹码集中度</td></tr>
<tr><td{tip('风险')}>风险扣分</td><td>−≤12</td><td>−≤12</td><td>高管净减持 / 大宗机构净卖出 / 高位 / 超买 / 破 MA60 / 质押 / 诉讼 / 解禁</td></tr>
<tr><td{tip('热度反向')}>热度反向</td><td>−≤4</td><td>−≤4</td><td>热搜榜名次 + 当日涨幅，散户过热视为短期见顶信号</td></tr>
</tbody></table>
<div class='note'><b>一票否决（Gate）：</b>所属板块主力出货 · 获利盘 &gt;90% · 现价高于平均成本 30% · 均线空头排列且跌破 MA60 · RSI&gt;80 · <b>解禁市值占比 ≥1%</b> · <b>处于计划减持窗口</b> · <b>质押比例 &gt;30%</b>。
<b>档位：</b>A ≥70（8%~10%）· B 60~70（5%~7%）· C 50~60（≤3%）· D &lt;50 不建仓。
<b>买卖点：</b>机构轨止损取 MA20×0.97 / 平均成本×0.97 / 进场×0.93 中最接近者，目标 +10%/+15%；游资轨止损 −3~5%，目标 +5%/+8%，不封板即走。</div></div>

<div class='note' style='border-left:4px solid #b8893b'><b>因子功效样本外实验室：</b>
本页打分体系的权重此前是按「近 5 期实测归因」调的 —— 5 期约 100 个样本且全在同一波行情里，属于样本内过拟合
（回测页自己也露出破绽：机构轨 B 档 T+1 胜率仅 36%，最低的 D 档 T+5 反而 +5.74%）。
我们把 13 个月、13,630 个样本点做了<b>五道独立检验</b>（两段切分 / 严格样本外 / 留一段交叉 / 扩窗 walk-forward / 先验因子集），
结论与可用改进见 <a href='lab.html' style='color:#b8893b;font-weight:600'>picks/lab.html →</a>（含完整局限声明）。
表内新增的「<b>稳健分</b>」列即由该实验室的口径给出：固定 12 因子、等权、横截面分位，不按回测调权重。</div>

<div class='note warn'><b>风险提示：</b>规则化输出，<b>不构成投资建议</b>。中报滞后、游资轨波动剧烈，务必自行核验基本面并严格执行止损。</div>

<footer>数据源：westock-mcp · 中报十大流通股东（2026-06-30）· 仅供参考，不构成投资建议。</footer>
</div></body></html>"""

    p2 = os.path.join(PICKS_WEB, "index.html")
    with open(p2, "w", encoding="utf-8") as f:
        f.write(idx)

    print(f"[build_picks] {D}: 机构轨 {len(inst_rows)}（A {na}/B {nb}）| 游资轨 {len(youzi_rows)}（A {nya}/B {nyb}）| 否决 {len(vetoed)} | 取消观察 {len([d for d in dropped if d.get('group') != 'pause'])}"
          f"（暂停 {len([d for d in dropped if d.get('group') == 'pause'])}）"
          f" | 新进 {sum(1 for r in inst_rows + youzi_rows if r.get('obsNew'))}")
    print(f"  → {p1}\n  → {p2}\n  → {HIST}（累计 {len(history)} 期）")
    if dropped:
        _bk = {}
        for _d in dropped:
            _bk.setdefault(_d.get("kind"), []).append(_d.get("name"))
        for _k, _v in _bk.items():
            print(f"     取消[{_k}] {len(_v)}: " + "、".join(str(x) for x in _v[:8])
                  + ("…" if len(_v) > 8 else ""))


def tech_score(q, t, maxs):
    """量价健康，满分 maxs（机构 22 / 游资 30）"""
    s = 0.0
    notes = []
    price = q.get("price")
    ma5, ma20, ma60 = t.get("ma5"), t.get("ma20"), t.get("ma60")
    rsi = t.get("rsi12")
    vr = q.get("volumeRatio")
    turn = q.get("turnoverRate")
    pos = q.get("week52Pos")
    w_trend, w_vol, w_mom, w_pos = 0.42, 0.22, 0.18, 0.18

    if all(x is not None for x in (price, ma5, ma20, ma60)):
        if ma5 > ma20 > ma60 and price > ma5:
            s += maxs * w_trend
            notes.append("多头排列")
        elif price > ma20 and ma20 > ma60:
            s += maxs * w_trend * 0.8
            notes.append("中期上行")
        elif price > ma20:
            s += maxs * w_trend * 0.6
            notes.append("站上MA20")
        elif price > ma5:
            s += maxs * w_trend * 0.35
            notes.append("短线转强")
        else:
            s += maxs * w_trend * 0.1
            notes.append("均线下方")
    else:
        s += maxs * w_trend * 0.3

    if turn is not None:
        if turn > 20:
            s += maxs * w_vol * 0.3
            notes.append(f"换手{turn:.1f}%过热")
        elif turn >= 1:
            s += maxs * w_vol if (vr is None or 0.8 <= vr <= 2.5) else maxs * w_vol * 0.6
            notes.append(f"换手{turn:.1f}%")
        else:
            s += maxs * w_vol * 0.5
            notes.append(f"换手{turn:.1f}%偏冷")

    if rsi is not None:
        if rsi > 75:
            s += maxs * w_mom * 0.2
            notes.append(f"RSI{rsi:.0f}超买")
        elif rsi >= 55:
            s += maxs * w_mom
            notes.append(f"RSI{rsi:.0f}强势")
        elif rsi >= 45:
            s += maxs * w_mom * 0.75
            notes.append(f"RSI{rsi:.0f}中性")
        else:
            s += maxs * w_mom * 0.5
            notes.append(f"RSI{rsi:.0f}偏弱")

    if pos is not None:
        if pos > 90:
            s += maxs * w_pos * 0.2
            notes.append(f"52周位{pos:.0f}%高位")
        elif pos >= 70:
            s += maxs * w_pos * 0.6
        elif pos >= 20:
            s += maxs * w_pos
        else:
            s += maxs * w_pos * 0.8
    return round(min(float(maxs), s), 2), notes


if __name__ == "__main__":
    main()
