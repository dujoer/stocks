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


def grade(score):
    if score >= 70:
        return "A", "重点建仓", "8%~10%", 10.0
    if score >= 60:
        return "B", "可建仓", "5%~7%", 7.0
    if score >= 50:
        return "C", "轻仓观察", "≤3%", 3.0
    return "D", "仅跟踪", "不建仓", 0.0


# ---------------- 历史回填 ----------------
def backfill(history):
    """回填次日/3日/5日表现。机构轨持有 5~15 日，必须看多周期，不能只看 T+1。"""
    qs = {}
    for p in glob.glob(os.path.join(PICKS_DATA, "quotes_*.json")):
        m = re.search(r"quotes_(\d{4}-\d{2}-\d{2})\.json", os.path.basename(p))
        if m:
            qs[m.group(1)] = p
    dates = sorted(qs)
    cache = {}

    def qmap_of(d):
        if d not in cache:
            cache[d] = load_json(qs[d], {}) or {}
        return cache[d]

    for h in history:
        if h.get("settled"):
            continue
        later = [d for d in dates if d > h["date"]]
        if not later:
            continue
        nxt = later[0]
        HOR = (("1", 1), ("3", 3), ("5", 5))
        for tk in ("inst", "youzi"):
            pk_list = h.get(tk, []) or []
            if not pk_list:
                continue
            stats = {k: {"tot": 0.0, "n": 0, "t1": 0, "t2": 0, "st": 0} for k, _ in HOR}
            for pk in pk_list:
                code = pk["code"]
                entry = pk.get("entry")
                for k, hh in HOR:
                    if len(later) < hh:
                        continue
                    qd = qmap_of(later[hh - 1]).get(code)
                    if not qd:
                        continue
                    close = qd.get("price")
                    if close is None:
                        continue
                    if entry:
                        ret = (close - entry) / entry * 100
                    else:
                        ret = qd.get("changePercent")
                    if ret is None:
                        continue
                    pk[f"ret{k}"] = round(float(ret), 2)
                    stats[k]["tot"] += float(ret)
                    stats[k]["n"] += 1
                    # 区间内是否触及目标/止损
                    for dd in later[:hh]:
                        qx = qmap_of(dd).get(code) or {}
                        hi = qx.get("high")
                        if pk.get("t1") and hi is not None and hi >= pk["t1"]:
                            pk[f"hitT1_{k}"] = True
                            break
                    for dd in later[:hh]:
                        qx = qmap_of(dd).get(code) or {}
                        hi = qx.get("high")
                        if pk.get("t2") and hi is not None and hi >= pk["t2"]:
                            pk[f"hitT2_{k}"] = True
                            break
                    for dd in later[:hh]:
                        qx = qmap_of(dd).get(code) or {}
                        lo = qx.get("low")
                        if pk.get("stop") and lo is not None and lo <= pk["stop"]:
                            pk[f"hitStop_{k}"] = True
                            break
                qd1 = qmap_of(nxt).get(code)
                if qd1 and qd1.get("changePercent") is not None:
                    pk["nextChg"] = round(float(qd1["changePercent"]), 2)
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
            # 兼容旧字段
            h[f"{tk}_avg"] = h.get(f"{tk}_ret1")
            h[f"{tk}_n"] = h.get(f"{tk}_n1", 0)
        h["settled"] = True
        h["settleDate"] = nxt
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
"""


# ---------------- 字段口径说明（悬浮提示） ----------------
TIPS = {
    # 卡片交易计划字段
    "现价": "数据日期的收盘价，括号内为当日涨跌幅（红涨绿跌）。全部买卖点均以该日收盘后的数据计算。",
    "进场区间": "建议分批建仓的价格带。机构轨：乖离 MA20 超过 10% 时改挂 MA10±1%（不追高），否则取「现价~MA5」上下各 0.5%~1.5%；游资轨：min(现价,MA5)×0.99 ~ 现价×1.02。后续目标位与止损均以该区间中值 mid 为基准。",
    "止损": "机构轨：在 MA20×0.97、平均成本×0.97、mid×0.93 三个候选里取「低于 mid 且最接近 mid」的一个，并夹在 mid 的 90%~97% 之间；游资轨：min(MA5×0.97, mid×0.95)。括号内为止损位相对 mid 的百分比。收盘跌破即无条件离场。",
    "目标一": "目标一 = mid×1.10（机构轨）/ mid×1.05（游资轨）；目标二 = mid×1.15 / mid×1.08。为固定比例，不含个股基本面与阻力位判断，实际操作中建议结合前高压力位修正。",
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
    items = [
        ("总门户", "../../index.html"), ("龙虎榜", "../lhb/lhb.html"),
        ("板块强度", "../sector/index.html"), ("高管增减持", "../exec/index.html"),
        ("大宗交易", "../block/index.html"), ("群体心理", "../psychology/index.html"),
        ("牛人追踪", "../shareholder/tracker.html"), ("数据中心", "../db/index.html"),
        ("信号池", "index.html"), ("回测", "backtest.html"),
        ("做T池", "../tplus/index.html"), ("版块总览", "../sections/index.html"),
    ]
    out = ["<div class='topnav'>"]
    for n, h in items:
        if n == cur:
            out.append(f"<a href='{h}' class='cur'>{n}</a>")
        else:
            out.append(f"<a href='{h}'>{n}</a>")
    out.append("</div>")
    return "".join(out)


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
    for c in cands["candidates"]:
        code = c["code"]
        q = qmap.get(code) or {}
        t = tmap.get(code) or {}
        if not q.get("price"):
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
            vetoed.append({"name": c.get("name"), "code": code, "why": veto})
            continue

        s = c["sig"]
        price = q.get("price")
        exs, exd = exec_norm(c.get("exec"), q)
        chs_inst, chn_i = chip_score(ch, price, 6.0)
        chs_yz, chn_y = chip_score(ch, price, 9.0)
        rts, rtd = rating_score(rt, 8.0)
        mgs, mgd = margin_score(mg, 6.0)
        mgs_y, mgd_y = margin_score(mg, 8.0)

        # 中报背景（滞后项，仅作底仓确认）
        q2 = c.get("q2") or {}
        q2_add = q2.get("addCnt") or 0
        q2s_inst = 8.0 if q2_add >= 2 else (5.0 if q2_add == 1 else 0.0)
        q2s_yz = q2s_inst * 0.6

        # 大宗
        bl = c.get("block") or {}
        bls = 6.0 if (bl.get("instBuyValue") or 0) > 0 else (3.0 if bl.get("cnt") else 0.0)
        bls_yz = 5.0 if (bl.get("instBuyValue") or 0) > 0 else (2.5 if bl.get("cnt") else 0.0)

        # 量价
        ts, tn = tech_score(q, t, 20.0)
        tsz, tnz = tech_score(q, t, 28.0)

        # 机构方向 28 = 龙虎榜机构净买 18 + 目标价空间 10
        inb = 0.0
        inst = c.get("inst") or {}
        net = float(inst.get("netBuy") or 0)
        if net > 0:
            raw_b = net / 1e8 * 11.0 + (inst.get("branchMax") or 0) * 2.0
            inb = min(18.0, raw_b)
        tp = con.get("targetPrice")
        tps = 0.0
        tpspace = None
        if tp and price and tp > 0:
            tpspace = (tp - price) / price * 100
            tps = 10.0 if tpspace >= 30 else (7.0 if tpspace >= 15 else (4.0 if tpspace > 0 else 0.0))

        # 主力资金
        mnf5 = ff.get("mainNetFlow5D")
        mnf20 = ff.get("mainNetFlow20D")
        mnf = ff.get("mainNetFlow")
        fs_inst = 0.0
        if mnf5 is not None:
            fs_inst += 5.0 if mnf5 > 0 else (2.0 if mnf5 > -1e8 else 0.0)
        if mnf20 is not None:
            fs_inst += 5.0 if mnf20 > 0 else (2.0 if mnf20 > -2e8 else 0.0)
        fs_yz = 8.0 if (mnf or 0) > 0 else (3.0 if (mnf or 0) > -5e7 else 0.0)

        # 游资方向 32 = 知名席位 20 + 买入额 8 + 席位家数 4
        yz = c.get("youzi") or {}
        yzs = 0.0
        if yz:
            yzs = (min(20.0, (yz.get("starCnt") or 0) * 10.0)
                   + min(8.0, float(yz.get("buy") or 0) / 1e8 * 6.0)
                   + min(4.0, (yz.get("seatCnt") or 0) * 0.8))

        exs_i = exs * 0.8
        total_inst = max(0.0, min(100.0, (inb + tps) + rts + mgs + fs_inst + q2s_inst
                                  + exs_i + bls + ts + chs_inst - pen - hpen))
        total_yz = max(0.0, min(100.0, yzs + fs_yz + q2s_yz + exs * 0.5 + bls_yz
                                + tsz + chs_yz + mgs_y - pen - hpen))

        base = {
            "code": code, "name": c.get("name"), "sw1": c.get("sw1"), "sw2": c.get("sw2"),
            "price": price, "chg": q.get("changePercent"), "turn": q.get("turnoverRate"),
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
            g, gn, ps, pn = grade(total_inst)
            inst_rows.append({**base, "score": round(total_inst, 1), "grade": g, "gname": gn,
                              "posStr": ps, "posNum": pn,
                              "detail": {"机构方向": round(inb + tps, 1), "机构评级": round(rts, 1),
                                         "两融": round(mgs, 1), "主力资金": round(fs_inst, 1),
                                         "中报背景": round(q2s_inst, 1), "高管": round(exs_i, 1),
                                         "大宗": round(bls, 1), "量价": round(ts, 1),
                                         "筹码": round(chs_inst, 1)},
                              "plan": plan_inst(q, t, ch),
                              "notes": tn + chn_i + extra_i + ([exd] if exd else [])})
        if s["youzi"] > 0 or c.get("track") == "youzi":
            g2, gn2, ps2, pn2 = grade(total_yz)
            youzi_rows.append({**base, "score": round(total_yz, 1), "grade": g2, "gname": gn2,
                               "posStr": ps2, "posNum": pn2,
                               "detail": {"游资方向": round(yzs, 1), "主力资金": round(fs_yz, 1),
                                          "中报背景": round(q2s_yz, 1), "高管": round(exs * 0.5, 1),
                                          "大宗": round(bls_yz, 1), "量价": round(tsz, 1),
                                          "筹码": round(chs_yz, 1), "两融": round(mgs_y, 1)},
                               "plan": plan_youzi(q, t, ch), "notes": tnz + chn_y + extra_y})

    inst_rows.sort(key=lambda x: -x["score"])
    youzi_rows.sort(key=lambda x: -x["score"])

    # ---- 历史 ----
    history = load_json(HIST, []) or []
    history = backfill(history)
    entry = {
        "date": D,
        "inst": [{"code": r["code"], "name": r["name"], "score": r["score"], "grade": r["grade"],
                  "entry": r["plan"]["mid"], "stop": r["plan"]["stop"],
                  "t1": r["plan"]["t1"], "t2": r["plan"]["t2"]} for r in inst_rows[:10]],
        "youzi": [{"code": r["code"], "name": r["name"], "score": r["score"], "grade": r["grade"],
                   "entry": r["plan"]["mid"], "stop": r["plan"]["stop"],
                   "t1": r["plan"]["t1"], "t2": r["plan"]["t2"]} for r in youzi_rows[:10]],
    }
    history = [h for h in history if h["date"] != D] + [entry]
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
            out.append(f"""
  <div class='card hi'>
    <div class='chead'>
      <span class='cname'>{esc(r['name'])}</span>
      <span class='ccode'>{esc(r['code'])} · {esc(r.get('sw1') or '—')}</span>
      <span class='badge b{r['grade']}'{tip_t('档位')}>{r['grade']} {esc(r['gname'])}</span>
      <span style='margin-left:auto' class='score'{tip_t('总分')}>{r['score']}</span>
    </div>
    <div class='grid'>
      <div class='kv tipbox'{tip_t('现价')}><div class='k tipk'>现价</div><div class='v'>{fnum(r['price'])} <span class='{"up" if (r["chg"] or 0) >= 0 else "down"}' style='font-size:12px'>{pct(r['chg'])}</span></div></div>
      <div class='kv tipbox'{tip_t('进场区间')}><div class='k tipk'>进场区间</div><div class='v sm'>{fnum(p['lo'])} ~ {fnum(p['hi'])}</div></div>
      <div class='kv tipbox'{tip_t('止损')}><div class='k tipk'>止损</div><div class='v sm down'>{fnum(p['stop'])}（{p['stopPct']}%）</div></div>
      <div class='kv tipbox'{tip_t('目标一')}><div class='k tipk'>目标一 / 二</div><div class='v sm up'>{fnum(p['t1'])} / {fnum(p['t2'])}</div></div>
      <div class='kv tipbox'{tip_t('盈亏比')}><div class='k tipk'>盈亏比</div><div class='v sm'>{p['rr']}</div></div>
      <div class='kv tipbox'{tip_t('仓位')}><div class='k tipk'>仓位 / 周期</div><div class='v sm'>{esc(r['posStr'])} · {esc(p['hold'])}</div></div>
    </div>
    <div class='sig'><b>信号：</b>{sigs_html}</div>
    <div class='sig'><b>打分：</b>{det} · <span{tip('风险')}>风险 {r['pen']}</span></div>
    <div class='sig'><b>介入：</b>{esc(p['note'])}；<b>失效：</b>跌破 {fnum(p['stop'])} 无条件离场。</div>
    {risk}
  </div>""")
        return "".join(out)

    def table_html(rows):
        return "".join(
            f"<tr><td>{esc(r['name'])}</td><td class='muted'>{esc(r['code'])}</td>"
            f"<td>{esc(r.get('sw1') or '—')}</td><td>{esc(r.get('behavior') or '—')}</td>"
            f"<td><b>{r['score']}</b></td>"
            f"<td class='{"up" if (r["chg"] or 0) >= 0 else "down"}'>{pct(r['chg'])}</td>"
            f"<td>{fnum(r['turn'])}</td><td>{fnum(r['pos52'], 0)}</td>"
            f"<td>{fnum((r['chip'] or {}).get('profitRate'), 0)}</td>"
            f"<td>{esc(r['plan']['stop'])}</td><td>{esc(r['plan']['t1'])}</td>"
            f"<td><span class='badge b{r['grade']}'{tip_t('档位')}>{r['grade']}</span></td></tr>"
            for r in rows)

    def th(key, label):
        return f"<th{tip(key)}>{label}</th>"

    THEAD = ("<thead><tr>" + th("名称", "名称") + th("代码", "代码") + th("行业", "行业")
             + th("板块", "板块") + th("总分", "总分") + th("当日", "当日")
             + th("换手", "换手%") + th("52周位", "52周位") + th("获利盘", "获利盘%")
             + th("止损", "止损") + th("目标一", "目标一") + th("档位", "档")
             + "</tr></thead>")

    na = sum(1 for r in inst_rows if r["grade"] == "A")
    nb = sum(1 for r in inst_rows if r["grade"] == "B")
    nya = sum(1 for r in youzi_rows if r["grade"] == "A")
    nyb = sum(1 for r in youzi_rows if r["grade"] == "B")

    veto_html = ""
    if vetoed:
        veto_html = ("<div class='veto'><b>已剔除 " + str(len(vetoed)) + " 只（触发一票否决）：</b>"
                     + "、".join(f"{esc(v['name'])}（{esc(v['why'])}）" for v in vetoed[:12])
                     + ("…" if len(vetoed) > 12 else "") + "</div>")

    html = f"""<!DOCTYPE html>
<html lang='zh-CN'><head><meta charset='UTF-8'>
<meta name='viewport' content='width=device-width,initial-scale=1.0'>
<title>个股信号池 · {D}</title><style>{CSS}</style></head><body>
<div class='wrap'>
{nav()}
<header><h1><span>个股信号池</span> · {D}</h1>
<div class='sub'>机构轨（波段 5~15 日）与 游资轨（短线 1~3 日）双池分轨打分，含板块闸门与筹码/资金流确认，每日盘后更新并回填次日表现。
<div class='muted' style='margin-top:6px'>字段旁带 <span class='tip' style='border:none'>?</span> 或虚线下划线的均可悬浮查看计算口径。</div></div></header>

<div class='note'><b>今日结论：</b>机构轨 {len(inst_rows)} 只（A {na} / B {nb}）· 游资轨 {len(youzi_rows)} 只（A {nya} / B {nyb}）。
<span{tip('Gate')}>闸门</span>：所属板块主力出货、获利盘 &gt;90%、现价高于成本 30%、空头排列破 MA60、RSI&gt;80、解禁 ≥1%、减持窗口、质押 &gt;30% 一律剔除。</div>
{veto_html}

<div class='section'><h2>机构轨 · 波段<span class='trk i'>5~15 日</span></h2>
<div class='muted' style='margin-bottom:8px'>机构方向 28（龙虎榜机构净买入 18 + 目标价空间 10）+ 机构评级 8 + 两融 6 + 主力资金 10 + 中报背景 8 + 高管 8 + 大宗 6 + 量价 20 + 筹码 6 − 风险 ≤12 − 热度反向 ≤4</div>
<table>{THEAD}
<tbody>{table_html(inst_rows)}</tbody></table>
{cards_html(inst_rows, 'inst')}</div>

<div class='section'><h2>游资轨 · 短线<span class='trk y'>1~3 日</span></h2>
<div class='muted' style='margin-bottom:8px'>游资方向 30（知名席位 18 + 买入额 8 + 席位家数 4）+ 主力资金 10 + 量价 28 + 筹码 9 + 两融 8 + 中报 5 + 高管 5 + 大宗 5 − 风险 ≤12 − 热度反向 ≤4</div>
<table>{THEAD}
<tbody>{table_html(youzi_rows)}</tbody></table>
{cards_html(youzi_rows, 'youzi')}</div>

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
            if not h.get(f"{tk}_settled"):
                return "<span class='muted'>待回填</span>"
            avg = h.get(f"{tk}_avg")
            cls = "up" if (avg or 0) >= 0 else "down"
            return (f"<b class='{cls}'>{pct(avg)}</b> · 触T1 {h.get(f'{tk}_t1')}/{h.get(f'{tk}_n')}"
                    f" · 触止损 {h.get(f'{tk}_stop')}")
        ni = len(h.get("inst", []) or [])
        ny = len(h.get("youzi", []) or [])
        return (f"<tr><td><a href='pick_{h['date']}.html'>{h['date']}</a></td>"
                f"<td>{ni}</td><td>{cell('inst')}</td><td>{ny}</td><td>{cell('youzi')}</td></tr>")

    ti = sum(h.get("inst_n", 0) for h in history if h.get("inst_settled"))
    ty = sum(h.get("youzi_n", 0) for h in history if h.get("youzi_settled"))

    def wr(tk, tot):
        if not tot:
            return "<span class='muted'>首期尚无回填</span>"
        h1 = sum(h.get(f"{tk}_t1", 0) for h in history if h.get(f"{tk}_settled"))
        hs = sum(h.get(f"{tk}_stop", 0) for h in history if h.get(f"{tk}_settled"))
        avgs = [h.get(f"{tk}_avg") for h in history if h.get(f"{tk}_settled") and h.get(f"{tk}_avg") is not None]
        a = sum(avgs) / len(avgs) if avgs else 0
        return f"触T1 {h1}/{tot}（{h1 / tot * 100:.0f}%）· 触止损 {hs} · 次日均涨 {pct(a)}"

    t_cnt = tip_t("候选数")
    t_nx = tip_t("次日表现")
    t_dim = tip("维度")
    t_wi = tip("机构轨权重")
    t_wy = tip("游资轨权重")
    t_cal = tip("口径")

    idx = f"""<!DOCTYPE html>
<html lang='zh-CN'><head><meta charset='UTF-8'>
<meta name='viewport' content='width=device-width,initial-scale=1.0'>
<title>个股信号池 · 每日归档</title><style>{CSS}</style></head><body>
<div class='wrap'>
{nav()}
<header><h1><span>个股信号池</span> · 每日归档</h1>
<div class='sub'>机构轨（波段）+ 游资轨（短线）双池输出建仓候选与买卖点，次日自动回填表现并统计胜率。</div></header>

<div class='note'><b>最新一期：</b><a href='pick_{D}.html'>{D}</a> —— 机构轨 {len(inst_rows)} 只（A {na} / B {nb}）· 游资轨 {len(youzi_rows)} 只（A {nya} / B {nyb}）。</div>

<div class='section'{tip_t('历史表现')}><h2>历史表现（多周期回填）</h2>
<div class='note'>机构轨累计 {wr('inst', ti)}<br>游资轨累计 {wr('youzi', ty)}</div>
<table><thead><tr><th>日期</th><th{t_cnt}>机构轨</th><th{t_nx}>机构轨次日</th><th{t_cnt}>游资轨</th><th{t_nx}>游资轨次日</th></tr></thead>
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

<div class='note warn'><b>风险提示：</b>规则化输出，<b>不构成投资建议</b>。中报滞后、游资轨波动剧烈，务必自行核验基本面并严格执行止损。</div>

<footer>数据源：westock-mcp · 中报十大流通股东（2026-06-30）· 仅供参考，不构成投资建议。</footer>
</div></body></html>"""

    p2 = os.path.join(PICKS_WEB, "index.html")
    with open(p2, "w", encoding="utf-8") as f:
        f.write(idx)

    print(f"[build_picks] {D}: 机构轨 {len(inst_rows)}（A {na}/B {nb}）| 游资轨 {len(youzi_rows)}（A {nya}/B {nyb}）| 否决 {len(vetoed)}")
    print(f"  → {p1}\n  → {p2}\n  → {HIST}（累计 {len(history)} 期）")


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
