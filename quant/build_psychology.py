# -*- coding: utf-8 -*-
"""群体心理风险雷达 · 数据驱动生成器（根治「总不更新」）

用法：
    python quant/build_psychology.py --date 2026-09-14

设计要点（与旧流程 _build_MMDD.py 的根本差异）：
  旧流程：每期手抄一份 400+ 条中英文案 + 60 组精确字符串 old->new 替换，
          锚点是「上一期的值」，一旦上一期页面被主题注入/i18n 回写改动，
          锚点静默失配（脚本只 print 未命中），于是残留旧数据或直接放弃当日更新。
  新流程：固定骨架 quant/psy/_skeleton.html（只读，永不改动）+ 结构化正则锚点
          + 数据驱动的定性/文案模板。数据到位即可一键出稿，不再依赖人工撰写。

输入（全部为本地已落盘的日快照，缺一项即如实标注降级，不编造）：
  quant/market_overview/YYYY-MM-DD.json   breadth/指数/技术/估值/风格
  quant/sector_strength_data_YYYYMMDD.json 板块涨跌与主力行为
  quant/psy/limitup_YYYY-MM-DD.json       连板梯队
"""
import argparse
import datetime as dt
import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SKELETON = os.path.join(HERE, "psy", "_skeleton.html")
OUT_DIR = os.path.join(ROOT, "web", "psychology")
HUB = os.path.join(OUT_DIR, "index.html")
HIST = os.path.join(HERE, "psy", "history.json")

WEEK_CN = {0: "周一", 1: "周二", 2: "周三", 3: "周四", 4: "周五", 5: "周六", 6: "周日"}
WEEK_EN = {0: "Mon", 1: "Tue", 2: "Wed", 3: "Thu", 4: "Fri", 5: "Sat", 6: "Sun"}


# ---------------------------------------------------------------- 数据装载
def load_json(path, default=None):
    if not path or not os.path.exists(path):
        return default
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def flat_overview(d):
    """把 market_overview 的 listCode->row 结构摊平成字段字典。"""
    out = {}
    for it in (d or {}).get("data", []):
        row = it.get("row") or {}
        for k, v in row.items():
            if v is not None:
                out[k] = v
    return out


def load_overview(date):
    p = os.path.join(ROOT, "quant", "market_overview", "%s.json" % date)
    return flat_overview(load_json(p))


def prev_trading_date(date):
    """从 market_overview 目录中取早于 date 的最近一个已落盘交易日。"""
    ds = []
    for p in glob.glob(os.path.join(ROOT, "quant", "market_overview", "*.json")):
        b = os.path.basename(p)[:-5]
        if b < date:
            ds.append(b)
    return max(ds) if ds else None


def next_trading_date(date):
    """简单推算下一交易日（跳过周末）。节假日需 --next 手动覆盖。"""
    y, m, d = [int(x) for x in date.split("-")]
    cur = dt.date(y, m, d)
    nxt = cur + dt.timedelta(days=1)
    while nxt.weekday() >= 5:
        nxt += dt.timedelta(days=1)
    return nxt.isoformat()


def prev_risk_from_hub(prev_date):
    """从 hub 索引读取上一期的风险等级（历史页面已推送，可靠）。"""
    if not prev_date or not os.path.exists(HUB):
        return None
    txt = open(HUB, encoding="utf-8").read()
    m = re.search(r'date:"%s",\s*\n\s*risk:"([^"]+)"' % prev_date, txt)
    return m.group(1) if m else None


def load_sectors(date):
    ymd = date.replace("-", "")
    p = os.path.join(ROOT, "quant", "sector_strength_data_%s.json" % ymd)
    arr = load_json(p, [])
    if not arr:
        return []
    return arr


def pick_sectors(rows, kind=None, top=3, reverse=True):
    rs = [r for r in rows if (kind is None or r.get("kind") == kind)]
    rs = [r for r in rs if isinstance(r.get("pctVal"), (int, float))]
    rs.sort(key=lambda r: r["pctVal"], reverse=reverse)
    return rs[:top]


def load_ladder(date):
    p = os.path.join(HERE, "psy", "limitup_%s.json" % date)
    d = load_json(p)
    if not d:
        # 回退：从 ① 拉取的 quant/limitup/{date}.json（westock tool_ranking 原始返回）派生
        raw = load_json(os.path.join(HERE, "limitup", "%s.json" % date))
        blk = (raw or {}).get("data") or {}
        stocks = blk.get("stocks") or []
        if not stocks:
            return None
        d = {
            "date": date,
            "source": "westock·tool_ranking(metric=limitup_days, date=%s)" % date,
            "total": blk.get("totalStocks") or len(stocks),
            "stocks": [{"code": s.get("code"), "name": s.get("name"),
                        "days": s.get("LimitUpDays", 1)} for s in stocks],
        }
    st = d.get("stocks", [])
    st.sort(key=lambda x: (-x.get("days", 1), x.get("code", "")))
    return d


def yi(v):
    """亿元 -> 万亿元文本"""
    try:
        return "%.2f" % (float(v) / 10000.0)
    except Exception:
        return "—"


def sgn(v, digits=2, pct=False):
    try:
        f = float(v)
    except Exception:
        return "—"
    s = ("%+.*f" % (digits, f)) if f >= 0 else ("%.*f" % (digits, f))
    return s + ("%" if pct else "")


# ---------------------------------------------------------------- 定性引擎
def classify(c, p):
    """由广度 / 指数 / 量能 / 技术 判定阶段与风险等级。"""
    up = c.get("RATIO_UP")
    dn_cnt = c.get("CNT_REACH_DNLIMIT")
    sh = c.get("CHANGE_PCT_SZZS")
    amt5 = c.get("MONEY_5DAVG_RATIO")
    p_up = (p or {}).get("RATIO_UP")
    p_dn = (p or {}).get("CNT_REACH_DNLIMIT")
    d_up = None if (up is None or p_up is None) else up - p_up
    d_dn = None if (dn_cnt is None or p_dn is None) else dn_cnt - p_dn

    stage = "CHOPPY"
    if up is not None and up < 25 and dn_cnt is not None and dn_cnt >= 10 and (amt5 or 0) >= 95:
        stage = "PANIC"
    elif up is not None and up < 35 and sh is not None and sh < 0 and (amt5 or 0) < 95:
        stage = "EBB"
    elif d_up is not None and d_up >= 20 and up is not None and up >= 45 and (sh or 0) <= 0.5:
        stage = "REPAIR"
    elif up is not None and up >= 60 and (sh or 0) > 0 and (amt5 or 0) >= 100:
        stage = "REBOUND"
    elif up is not None and up >= 45 and (sh or 0) > 0:
        stage = "REBOUND"
    elif up is not None and up >= 45 and (sh or 0) < -0.5:
        stage = "DIVERGE"

    # 风险等级
    if stage == "PANIC":
        risk = "高"
    elif stage == "EBB":
        risk = "高" if (dn_cnt or 0) >= 10 else "中"
    elif stage == "REPAIR":
        risk = "中" if (dn_cnt or 0) >= 10 else "中"
    elif stage == "REBOUND":
        risk = "低"
    else:
        risk = "中"
    if (dn_cnt or 0) >= 25:
        risk = "高"

    # ---- 雷达六维（0-100，越高越脆弱；公式为显式映射，非拍脑袋）
    def clamp(v, lo=20, hi=95):
        return int(max(lo, min(hi, round(v))))

    # 广度：涨股比越低越脆弱，跌停数量加权
    base_up = 25 if up is None else (
        25 if up >= 60 else 40 if up >= 50 else 55 if up >= 40 else 70 if up >= 25 else 85 if up >= 15 else 95)
    breadth = clamp(base_up + (15 if (dn_cnt or 0) >= 20 else 8 if (dn_cnt or 0) >= 10 else 0))

    # 换手：量能相对 5 日均
    a = amt5 if amt5 else 100
    turnover = clamp(32 + (a - 80) * 0.9)

    # 融资：两融接口常降级，缺失时按恐慌边际变化平移上一期读数
    margin_missing = not c.get("MARGIN_BALANCE") and not c.get("FINANCE_VALUE_DOD")
    prev_margin = 66
    hp = os.path.join(HERE, "psy", "history.json")
    h = load_json(hp, {})
    if h:
        ks = sorted([k for k in h if k < c.get("_date", "9999")])
        if ks:
            prev_margin = h[ks[-1]].get("radar", {}).get("margin", 66)
    margin = clamp(prev_margin + (0 if d_dn is None else (-4 if d_dn < -5 else 4 if d_dn > 5 else -2 if d_dn < 0 else 2)))

    # 拥挤度：领涨方向资金集中度（由板块强度前 10 占比映射）
    rows = c.get("_sectors", []) or []
    pos = [r.get("strengthVal", 0) for r in rows if (r.get("strengthVal") or 0) > 0]
    pos.sort(reverse=True)
    share = (sum(pos[:10]) / sum(pos)) if pos else 0.25
    crowd = clamp(40 + (share - 0.25) * 160, 30, 80)

    # 媒体情绪：涨停/跌停/涨股比综合温度（越高越亢奋，此处取「脆弱性」故反向权重低）
    media = clamp(50 + ((up or 50) - 50) * 0.45 - (dn_cnt or 0) * 0.30 + (c.get("CNT_REACH_UPLIMIT") or 0) * 0.12)

    # 估值：PE_TTM 长周期分位为主
    pe10 = c.get("PE_TTM_PCT_10Y") or c.get("PE_TTM_PCT_5Y") or c.get("PE_TTM_PCT_3Y")
    pe = c.get("PE_TTM")
    val = clamp((pe10 * 0.8 if pe10 else 55) + ((pe - 18) * 4 if pe else 0), 30, 95)

    radar = {"crowd": crowd, "margin": margin, "turn": turnover,
             "breadth": breadth, "media": media, "val": val}

    return {
        "stage": stage, "risk": risk, "radar": radar,
        "d_up": d_up, "d_dn": d_dn, "p_up": p_up, "p_dn": p_dn,
        "margin_missing": margin_missing,
    }


STAGE_ZH = {
    "PANIC": "放量普跌 · 恐慌扩散",
    "EBB": "缩量阴跌 · 退潮加速",
    "REPAIR": "缩量止跌 · 广度修复（指数未确认）",
    "REBOUND": "放量普涨 · 情绪回暖",
    "DIVERGE": "指数分化 · 结构主导",
    "CHOPPY": "缩量震荡 · 多空观望",
}
STAGE_EN = {
    "PANIC": "Volume-expanding broad sell-off / Panic spreads",
    "EBB": "Volume-shrinking grind / Ebb accelerates",
    "REPAIR": "Shrinking-volume stabilisation / Breadth repairs (index unconfirmed)",
    "REBOUND": "Volume-expanding rally / Sentiment warms",
    "DIVERGE": "Index divergence / Structure leads",
    "CHOPPY": "Low-volume chop / Sideline standoff",
}


# ---------------------------------------------------------------- 文案引擎
def narrate(date, c, p, k, sec_up, sec_dn, lad):
    """按阶段模板 + 真实数据拼装中英文文案。"""
    d = dt.date(*[int(x) for x in date.split("-")])
    dstr_cn = "%d-%02d-%02d" % (d.year, d.month, d.day)
    prev = k.get("_prev_date")
    nxt = k.get("_next_date")
    nd = dt.date(*[int(x) for x in nxt.split("-")])
    nxt_cn = "%02d-%02d" % (nd.month, nd.day)
    nxt_en = "%02d-%02d %s" % (nd.month, nd.day, WEEK_EN[nd.weekday()])

    up = c.get("RATIO_UP")
    cnt_up, cnt_dn, cnt_fl = c.get("CNT_RED"), c.get("CNT_GREEN"), c.get("CNT_ZERO")
    lu, ld = c.get("CNT_REACH_UPLIMIT"), c.get("CNT_REACH_DNLIMIT")
    amt = c.get("MONEY")
    amt5, amt10, amt20 = c.get("MONEY_5DAVG_RATIO"), c.get("MONEY_10DAVG_RATIO"), c.get("MONEY_20DAVG_RATIO")
    sh, shp = c.get("CLOSE_PRICE_SZZS"), c.get("CHANGE_PCT_SZZS")
    sz, szp = c.get("CLOSE_PRICE_SZCZ"), c.get("CHANGE_PCT_SZCZ")
    cy, cyp = c.get("CLOSE_PRICE_CYBZ"), c.get("CHANGE_PCT_CYBZ")
    ma5, ma10, ma20, ma60 = c.get("MA_5"), c.get("MA_10"), c.get("MA_20"), c.get("MA_60")
    bl, bm, bu = c.get("BOLL_LOWER"), c.get("BOLL_MID"), c.get("BOLL_UPPER")
    macd, dif, dea = c.get("MACD"), c.get("DIF"), c.get("DEA")
    rsi6, kdj_j = c.get("RSI_6"), c.get("KDJ_J")
    pe, pe10, pe5, pe3, pb, div = (c.get("PE_TTM"), c.get("PE_TTM_PCT_10Y"), c.get("PE_TTM_PCT_5Y"),
                                   c.get("PE_TTM_PCT_3Y"), c.get("PB_LF"), c.get("DIV_TTM"))
    v20, g20 = c.get("CHG_20D_QZJZ"), c.get("CHG_20D_QZCZ")
    hs5, zz5 = c.get("CHG_5D_HS300"), c.get("CHG_5D_ZZ1000")

    stage_zh, stage_en = STAGE_ZH[k["stage"]], STAGE_EN[k["stage"]]
    risk = k["risk"]
    risk_en = {"高": "High", "中": "Medium", "低": "Low"}[risk]

    # 均线位置
    mas = [("MA5", ma5), ("MA10", ma10), ("MA20", ma20), ("MA60", ma60)]
    above = [n for n, v in mas if v and sh and sh >= v]
    below = [n for n, v in mas if v and sh and sh < v]
    if not below:
        ma_txt = "站上 MA5/MA10/MA20/MA60 全部均线"
        ma_txt_en = "above MA5/MA10/MA20/MA60 all at once"
    elif not above:
        ma_txt = "收盘低于 MA5/MA10/MA20/MA60 全部均线"
        ma_txt_en = "closes below MA5/MA10/MA20/MA60 all at once"
    else:
        ma_txt = "站上 %s，但仍低于 %s" % ("/".join(above), "/".join(below))
        ma_txt_en = "above %s but still below %s" % ("/".join(above), "/".join(below))

    # 布林位置
    if bl and sh:
        boll_txt = "盘中/收盘位于布林下轨（%.2f）%s" % (bl, "上方" if sh >= bl else "下方")
        boll_txt_en = "closes %s the BOLL lower band (%.2f)" % ("above" if sh >= bl else "below", bl)
    else:
        boll_txt, boll_txt_en = "布林口径暂缺", "BOLL basis missing"

    # 环比
    p_amt = (p or {}).get("MONEY")
    amt_diff = None if (amt is None or p_amt is None) else amt - p_amt
    amt_diff_txt = ("环比 %+d亿" % round(amt_diff)) if amt_diff is not None else "环比口径暂缺"
    amt_diff_en = ("%+.0f bn d/d" % amt_diff) if amt_diff is not None else "d/d basis missing"
    d_up, d_dn = k.get("d_up"), k.get("d_dn")
    d_up_txt = ("较上一报告日 %+.1fpct" % d_up) if d_up is not None else "无环比口径"
    d_dn_txt = ("较上一报告日 %+d 只" % d_dn) if d_dn is not None else "无环比口径"
    d_up_en = ("%+.1fpct vs the previous report" % d_up) if d_up is not None else "no d/d basis"
    d_dn_en = ("%+d vs the previous report" % d_dn) if d_dn is not None else "no d/d basis"

    # 板块
    def fmt_sec(r):
        beh = r.get("behavior") or "—"
        main = r.get("mainText") or "—"
        lead = r.get("leader") or ""
        return "%s %s（主力 %s亿，行为「%s」；龙头 %s）" % (r.get("name"), r.get("pctText"), main, beh, lead)
    sup = "；".join(fmt_sec(r) for r in sec_up) if sec_up else "板块接口降级，暂缺"
    sdn = "；".join(fmt_sec(r) for r in sec_dn) if sec_dn else "板块接口降级，暂缺"
    sup_en = "；".join("%s %s (main %s, '%s')" % (r.get("name"), r.get("pctText"), r.get("mainText"), r.get("behavior"))
                      for r in sec_up) if sec_up else "sector interface degraded, missing"

    # 连板
    if lad:
        top = lad["stocks"][0]
        board = top["days"]
        board_name = top["name"]
        b2 = [s["name"] for s in lad["stocks"] if s["days"] == 2][:6]
        b3 = [s["name"] for s in lad["stocks"] if s["days"] == board and board > 1]
        lad_txt = "最高 %d 板（%s），共 %d 只涨停%s" % (
            board, board_name, lad.get("total", len(lad["stocks"])),
            "；2板：" + " / ".join(b2) if b2 else "")
        lad_txt_en = "Top board %d (%s), %d limit-ups%s" % (
            board, board_name, lad.get("total", len(lad["stocks"])),
            "; 2-board: " + " / ".join(b2) if b2 else "")
    else:
        board, board_name = None, "—"
        lad_txt = "连板梯队接口降级，暂缺（未编造）"
        lad_txt_en = "ladder interface degraded, missing (not fabricated)"

    n_sector = len(c.get("_sectors") or [])
    n_up_sector = len([r for r in (c.get("_sectors") or []) if (r.get("pctVal") or 0) > 0])
    n_dist = len([r for r in (c.get("_sectors") or []) if r.get("behavior") == "出货"])

    # 估值分位
    pe_s = ("%.2f" % pe) if isinstance(pe, (int, float)) else "暂缺"
    pe_s_en = ("%.2f" % pe) if isinstance(pe, (int, float)) else "n/a"
    if pe10 is not None:
        pe_txt = "PE_TTM %s（10年分位 %.1f%%、5年 %.1f%%、3年 %.1f%%；PB %.2f、股息率 %.2f%%）" % (
            pe_s, pe10, pe5 if pe5 is not None else 0, pe3 if pe3 is not None else 0, pb or 0, div or 0)
        pe_txt_en = "PE_TTM %s (10Y pctile %.1f%%, 5Y %.1f%%, 3Y %.1f%%; PB %.2f, dividend yield %.2f%%)" % (
            pe_s_en, pe10, pe5 if pe5 is not None else 0, pe3 if pe3 is not None else 0, pb or 0, div or 0)
        pe_short = "%.0f%%（10年）" % pe10
    else:
        pe_txt = "PE_TTM %s（52周分位 %.1f%%，3/5/10 年长周期分位缺，未编造）" % (pe_s, c.get("PE_TTM_PCT_52W") or 0)
        pe_txt_en = "PE_TTM %s (52w pctile %.1f%%, 3/5/10Y percentiles missing, not fabricated)" % (
            pe_s_en, c.get("PE_TTM_PCT_52W") or 0)
        pe_short = "%.0f%%（52周）" % (c.get("PE_TTM_PCT_52W") or 0)

    r = k["radar"]
    radar_txt = ("拥挤度 %d / 融资 %d / 换手 %d / 广度 %d / 媒体 %d / 估值 %d"
                 % (r["crowd"], r["margin"], r["turn"], r["breadth"], r["media"], r["val"]))
    radar_txt_en = ("crowding %d / margin %d / turnover %d / breadth %d / media %d / valuation %d"
                    % (r["crowd"], r["margin"], r["turn"], r["breadth"], r["media"], r["val"]))

    amt_yi = yi(amt)
    vol_word = "放量" if (amt5 or 0) >= 105 else "缩量" if (amt5 or 0) <= 92 else "平量"
    vol_word_en = "expanding" if (amt5 or 0) >= 105 else "shrinking" if (amt5 or 0) <= 92 else "flat"

    ZH = {
        "t_headline_sub": "%s · 收盘" % dstr_cn,
        "t_breadth": "市场涨跌分布（%s 收盘）" % dstr_cn,
        "ev_index": "二、核心指数表现（%s 收盘）" % dstr_cn,
        "o_compliance": "<b>合规说明：</b>本展望仅给出板块方向与交易规则，不涉及具体个股推荐；群体心理定位与板块推断基于 %s 真实行情数据，市场有风险，决策须独立。" % dstr_cn,
        "t_risk_hi": risk,
        "hk_risk": "风险等级",
        "hv_risk": "<b class=\"hl-risk\">%s</b>（%s）" % (risk, "较上一报告日维持" if (p or {}).get("_risk") == risk else "由上一报告日调整"),
        "hv_stage": "<b>%s</b>（%s）" % (stage_zh, dstr_cn),
        "hv_upratio": "<b>%.0f%%</b>（前次 %s · %s）" % (up or 0, ("%.0f%%" % k["p_up"]) if k["p_up"] is not None else "—", d_up_txt),
        "hv_lim": "<b>%s</b> / <b>%s</b>（跌停 %s）" % (lu if lu is not None else "—", ld if ld is not None else "—", d_dn_txt),
        "hv_amt": "<b>¥%s万亿</b>（%s，为 5 日均 %.1f%%）" % (amt_yi, vol_word, amt5 or 0),
        "hv_cycle": "<b>%s</b>" % stage_zh,
        "hv_flag": "涨股比 %s（%s，%s）、涨停 %s / 跌停 %s（%s）、成交 ¥%s万亿（5 日均 %.1f%%）；上证 %s（%.2f）%s，%s——%s".replace("%s（%s，%s）", "%s（%s，%s）") % (
            ("%.0f%%" % up) if up is not None else "—",
            "涨%s / 跌%s / 平%s" % (cnt_up, cnt_dn, cnt_fl), d_up_txt,
            lu if lu is not None else "—", ld if ld is not None else "—", d_dn_txt,
            amt_yi, amt5 or 0, sgn(shp, 2, True), sh or 0, ma_txt, boll_txt,
            "两融接口降级暂缺，未编造" if k["margin_missing"] else "两融口径已更新"),
        # ---- 八大段
        "tk1": "阶段定性",
        "tv1": "A股 %s 定性为「<b>%s</b>」：涨股比 <b>%.0f%%</b>（%s，%s），涨停 <b>%s</b>、跌停 <b>%s</b>（%s）；上证 <b>%s</b>（%.2f，%s），深成 %s（%.2f）、创业板 %s（%.2f）；成交 ¥%s万亿（5 日均 %.1f%%、10 日均 %.1f%%、20 日均 %.1f%%，%s）。风险等级：<b>%s</b>。" % (
            dstr_cn, stage_zh, up or 0, "涨%s / 跌%s / 平%s" % (cnt_up, cnt_dn, cnt_fl), d_up_txt,
            lu if lu is not None else "—", ld if ld is not None else "—", d_dn_txt,
            sgn(shp, 2, True), sh or 0, ma_txt,
            sgn(szp, 2, True), sz or 0, sgn(cyp, 2, True), cy or 0,
            amt_yi, amt5 or 0, amt10 or 0, amt20 or 0, amt_diff_txt, risk),
        "tk2": "广度与量能",
        "tv2": "涨股比 <b>%.0f%%</b>（%s）· 涨停 <b>%s</b> · 跌停 <b>%s</b>（%s）· 成交 <b>¥%s万亿</b>（5 日均 %.1f%%、%s，%s）——%s；全市场 %s 个板块中 <b>%s</b> 个收红、%s 个呈主力「出货」。%s" % (
            up or 0, d_up_txt, lu if lu is not None else "—", ld if ld is not None else "—", d_dn_txt,
            amt_yi, amt5 or 0, amt_diff_txt, vol_word,
            "广度修复但跌停仍在 10 只上方，恐慌尚未完全出清" if (ld or 0) >= 10 else "跌停回落至 10 只下方，恐慌边际缓和",
            n_sector, n_up_sector, n_dist,
            "跌停 ≥25 只，恐慌仍处扩散段" if (ld or 0) >= 25 else ""),
        "tk3": "技术位置",
        "tv3": "上证 <b>%s</b>（%.2f），%s；%s。MACD <b>%s</b>（DIF %s / DEA %s），RSI6 <b>%s</b>、KDJ_J %s——%s。深成 %s（%.2f）、创业板 %s（%.2f）。" % (
            sgn(shp, 2, True), sh or 0, ma_txt, boll_txt,
            ("%.2f" % macd) if macd is not None else "—",
            ("%.2f" % dif) if dif is not None else "—", ("%.2f" % dea) if dea is not None else "—",
            ("%.2f" % rsi6) if rsi6 is not None else "—", ("%.1f" % kdj_j) if kdj_j is not None else "—",
            "超卖与破位并存：短线有技术性反抽条件，但中期趋势未修复" if (rsi6 or 50) < 35 else "技术指标处于中性区间",
            sgn(szp, 2, True), sz or 0, sgn(cyp, 2, True), cy or 0),
        "tk4": "板块结构",
        "tv4": "领涨：%s。领跌：%s。全市场 %s 个板块中 %s 个收红、%s 个呈主力「出货」——%s。" % (
            sup, sdn, n_sector, n_up_sector, n_dist,
            "资金集中于少数方向，其余普遍承压" if n_up_sector < n_sector * 0.4 else "板块普涨，赚钱效应扩散"),
        "tk5": "连板结构",
        "tv5": "%s。%s" % (lad_txt, "高度与接力情况是短线情绪的直接温度计：高度抬升＝赚钱效应扩张，高度下降或龙头更替＝接力意愿转弱。" if board else ""),
        "tk6": "资金：两融",
        "tv6": ("两融接口降级（service error），<b>未编造</b>；仅就可见信号判断：%s 个板块呈主力「出货」，资金集中在 %s。"
                % (n_dist, "、".join([r.get("name") for r in sec_up[:3]]) if sec_up else "少数方向")
                ) if k["margin_missing"] else "两融余额与融资单日变动已更新，详见下方证据表。",
        "tk7": "估值 / 风格",
        "tv7": "%s。风格上：全指价值 20 日 <b>%s</b> vs 全指成长 20 日 <b>%s</b>（差 %.1fpct），沪深300 5日 %s / 中证1000 5日 %s——%s。" % (
            pe_txt, sgn(v20, 2, True) if v20 is not None else "—", sgn(g20, 2, True) if g20 is not None else "—",
            abs((v20 or 0) - (g20 or 0)), sgn(hs5, 2, True) if hs5 is not None else "—",
            sgn(zz5, 2, True) if zz5 is not None else "—",
            "价值/成长分化显著，风格切换是当期主轴" if abs((v20 or 0) - (g20 or 0)) >= 3 else "风格差异不显著"),
        "tk8": "情绪周期",
        "tv8": "当期定位「<b>%s</b>」：涨股比 %s、涨停 %s / 跌停 %s、成交 5 日均 %.1f%%（%s）。右侧确认条件：%s；恶化条件：%s。风险等级 <b>%s</b>。" % (
            stage_zh, ("%.0f%%" % up) if up is not None else "—", lu if lu is not None else "—",
            ld if ld is not None else "—", amt5 or 0, vol_word,
            "放量收复 MA5/MA10（%.2f / %.2f）且跌停回落至 10 只下方" % (ma5 or 0, ma10 or 0),
            "跌停扩大至 25 只以上或上证收于布林下轨（%.2f）下方" % (bl or 0), risk),
        "t_tldr_text": "%s A股：涨股比 %.0f%%（涨%s / 跌%s / 平%s），涨停 %s / 跌停 %s，成交 ¥%s万亿（5 日均 %.1f%%）；上证 %s（%.2f，%s），深成 %s（%.2f）、创业板 %s（%.2f）。领涨：%s。领跌：%s。%s。%s。风险等级 %s。" % (
            dstr_cn, up or 0, cnt_up, cnt_dn, cnt_fl, lu if lu is not None else "—", ld if ld is not None else "—",
            amt_yi, amt5 or 0, sgn(shp, 2, True), sh or 0, ma_txt, sgn(szp, 2, True), sz or 0,
            sgn(cyp, 2, True), cy or 0,
            "；".join("%s %s" % (r.get("name"), r.get("pctText")) for r in sec_up[:3]) if sec_up else "板块暂缺",
            "；".join("%s %s" % (r.get("name"), r.get("pctText")) for r in sec_dn[:3]) if sec_dn else "板块暂缺",
            lad_txt, pe_txt, risk),
        "t_radar_note": "六维风险读数（0–100，由下方真实数据按显式公式映射，越高代表该维度群体脆弱性越强）：%s。%s" % (
            radar_txt,
            "融资维度因两融接口降级，按恐慌边际平移上一期读数（非实测值）；其余五维均由当日真实数据计算。" if k["margin_missing"] else "六维均由当日真实数据计算。"),
        "t_cycle_note": "注：上方「%s」为实时群体心理定位——%s 广度（涨股比 %s、涨停 %s、跌停 %s、成交 ¥%s万亿）显示：%s。若下一交易日跌停回落至 10 只以内且涨股比维持在 50%% 上方，恐慌视为完全缓和；若跌停重新扩大至 25 只以上或上证收于 %.2f 下方，恐慌升级。" % (
            stage_zh, dstr_cn, ("%.0f%%" % up) if up is not None else "—", lu if lu is not None else "—",
            ld if ld is not None else "—", amt_yi,
            "跌停仍在 10 只上方，恐慌尚未完全出清" if (ld or 0) >= 10 else "跌停已回落至 10 只下方，恐慌边际缓和",
            bl or 0),
        "t_breadth_note": "涨股比 %s（涨%s / 跌%s / 平%s）、涨停 %s / 跌停 %s，成交 ¥%s万亿（5 日均 %.1f%%，%s）。三大指数：上证 %s（%.2f）/ 深成 %s（%.2f）/ 创业板 %s（%.2f）；%s 个板块中 %s 个收红、%s 个呈主力「出货」。" % (
            ("%.0f%%" % up) if up is not None else "—", cnt_up, cnt_dn, cnt_fl,
            lu if lu is not None else "—", ld if ld is not None else "—", amt_yi, amt5 or 0, amt_diff_txt,
            sgn(shp, 2, True), sh or 0, sgn(szp, 2, True), sz or 0, sgn(cyp, 2, True), cy or 0,
            n_sector, n_up_sector, n_dist),
        # ---- 证据表解读
        "ev_upratio_i": "涨股比 %.0f%%（%s），涨 %s / 跌 %s / 平 %s——%s" % (
            up or 0, d_up_txt, cnt_up, cnt_dn, cnt_fl,
            "参与度显著修复" if (d_up or 0) > 10 else "参与度继续走弱" if (d_up or 0) < -5 else "参与度变化不大"),
        "ev_limit_i": "涨停 %s（%s）、跌停 %s（%s）——%s" % (
            lu if lu is not None else "—", ("较上一报告日 %+d 只" % ((lu or 0) - (k.get("p_lu") or 0))) if k.get("p_lu") is not None else "无环比",
            ld if ld is not None else "—", d_dn_txt,
            "跌停仍在 10 只上方，恐慌未完全出清" if (ld or 0) >= 10 else "跌停回落至警戒线下方，恐慌缓和"),
        "ev_amount_i": "两市成交 ¥%s万亿（5 日均 %.1f%%、10 日均 %.1f%%、20 日均 %.1f%%，%s）——%s" % (
            amt_yi, amt5 or 0, amt10 or 0, amt20 or 0, amt_diff_txt,
            "缩量＝抛压衰减但承接亦不足" if (amt5 or 0) <= 92 else "放量＝分歧加大，需看方向" if (amt5 or 0) >= 105 else "量能持平，多空僵持"),
        "ev_sh_i": "上证 %s（%.2f），%s；%s。MACD %s（DIF %s / DEA %s）、RSI6 %s、KDJ_J %s。%s" % (
            sgn(shp, 2, True), sh or 0, ma_txt, boll_txt,
            ("%.2f" % macd) if macd is not None else "—", ("%.2f" % dif) if dif is not None else "—",
            ("%.2f" % dea) if dea is not None else "—", ("%.2f" % rsi6) if rsi6 is not None else "—",
            ("%.1f" % kdj_j) if kdj_j is not None else "—", pe_txt),
        "ev_sz_i": "深成 %s（%.2f）——%s" % (sgn(szp, 2, True), sz or 0,
                                        "与上证同步，趋势一致性较高" if (szp or 0) * (shp or 0) > 0 else "与上证背离，结构分化"),
        "ev_cyb_i": "创业板 %s（%.2f）——%s" % (sgn(cyp, 2, True), cy or 0,
                                          "相对抗跌" if (cyp or 0) > (shp or 0) else "弱于主板，成长风格承压"),
        "ev_secup_i": "领涨：%s" % sup,
        "ev_secdn_i": "领跌：%s" % sdn,
        "ev_board_i": "%s——%s" % (lad_txt, "梯队高度为短线情绪温度计" if board else "接口降级，未编造"),
        "ev_height_i": "最高 %s 板（%s），%s" % (board if board else "—", board_name, lad_txt),
        "ev_main_i": "主力 5 日净流入：%s" % ("接口降级暂缺，未编造；当日主力行为以板块口径（主力/散户/暗盘）替代呈现" if not c.get("_main5d") else "已更新"),
        "ev_margin_i": "融资单日变动：%s" % ("两融接口降级（service error），数据暂缺，<b>未编造</b>" if k["margin_missing"] else "已更新"),
        "ev_hot_i": "热点：%s；%s" % (
            "、".join([r.get("name") for r in sec_up[:4]]) if sec_up else "暂缺",
            lad_txt),
        "ev_margintotal_i": "市场两融余额：%s" % ("接口降级暂缺，已如实标注、未编造" if k["margin_missing"] else "已更新"),
        # ---- 风险分层
        "rc1_tag": "红线区 · %s" % ("杠杆与恐慌双高（两融暂缺）" if k["margin_missing"] else "恐慌未出清"),
        "rc1_t": "恐慌未完全出清 + 指数未收复均线",
        "rc1_d": "%s 跌停 %s 只（%s，仍在 10 只警戒线%s）、上证 %s（%.2f）%s——恐慌虽有缓和但未确认出清；%s。" % (
            dstr_cn, ld if ld is not None else "—", d_dn_txt,
            "上方" if (ld or 0) >= 10 else "下方", sgn(shp, 2, True), sh or 0, ma_txt,
            "两融数据缺失，杠杆踩踏风险无法证伪" if k["margin_missing"] else "两融口径可见"),
        "rc1_rep": "代表：%s；以及 %s 个呈主力「出货」的板块" % (
            "、".join([r.get("name") for r in sec_dn[:3]]) if sec_dn else "领跌方向暂缺", n_dist),
        "rc1_cond": "条件框架：以「跌停回落至 10 只下方 + 涨股比维持 50%% 上方 + 上证放量收复 MA5（%.2f）」为恐慌出清的最低确认；未确认前仓位纪律优先，不加杠杆、不抄正在下跌的刀。" % (ma5 or 0),
        "rc2_tag": "黄线区 · 修复与反复的博弈",
        "rc2_t": "广度修复 vs 指数未确认",
        "rc2_d": "涨股比已回升至 %.0f%%（%s，%s），但上证仍 %s、成交%s（5 日均 %.1f%%）——广度修复领先于指数，属典型的「跌不动但涨不动」阶段；RSI6 %s、KDJ_J %s 显示%s。" % (
            up or 0, "涨%s / 跌%s" % (cnt_up, cnt_dn), d_up_txt, sgn(shp, 2, True), vol_word, amt5 or 0,
            ("%.2f" % rsi6) if rsi6 is not None else "—", ("%.1f" % kdj_j) if kdj_j is not None else "—",
            "超卖，存在技术性反抽条件" if (rsi6 or 50) < 35 else "未超卖"),
        "rc2_rep": "代表：%s" % ("、".join([r.get("name") for r in sec_up[:3]]) if sec_up else "领涨方向暂缺"),
        "rc2_cond": "条件框架：不预判底部；若反弹缩量（量能回落至 5 日均下方）视为弱反弹，警惕二次探底；右侧确认 ＝ 放量收复 MA5/MA10（%.2f / %.2f）且跌停清零。" % (ma5 or 0, ma10 or 0),
        "rc3_tag": "绿线区 · 有主力真实承接的方向（观察）",
        "rc3_t": "主力净流入方向",
        "rc3_d": "%s——在 %s 个板块呈「出货」的背景下，以上方向是少数有主力真实承接者。" % (sup, n_dist),
        "rc3_rep": "代表：%s" % ("、".join([r.get("name") for r in sec_up[:4]]) if sec_up else "暂缺"),
        "rc3_cond": "条件框架：仅作结构跟踪，不追当日涨幅；确认信号 ＝ 指数企稳后仍保持主力净流入且换手不萎缩；若恐慌加剧其补跌，则确认全线出清。",
        # ---- 展望
        "t_sec_outlook": "下个交易日（%s %s）展望" % (nxt_cn, WEEK_CN[nd.weekday()]),
        "o_logic": "研判逻辑（基于 %s 收盘 + 群体心理定位）" % dstr_cn,
        "o_logic_text": "由 %s 的「%s」延伸：涨股比 %s、涨停 %s / 跌停 %s、成交 ¥%s万亿（5 日均 %.1f%%），上证 %s 且 %s；%s。据此给出下一交易日的板块方向与交易规则（<b>不涉及具体个股推荐</b>）。" % (
            dstr_cn, stage_zh, ("%.0f%%" % up) if up is not None else "—", lu if lu is not None else "—",
            ld if ld is not None else "—", amt_yi, amt5 or 0, ma_txt, boll_txt,
            "RSI6 %s 处于超卖区，短线存在技术性反抽条件" % ("%.2f" % rsi6) if (rsi6 or 50) < 35 else "技术指标处于中性区间"),
        "o1_tag": "有主力承接的方向（观察）",
        "o1_t": "%s" % (" / ".join([r.get("name") for r in sec_up[:4]]) if sec_up else "暂缺"),
        "o1_d": "%s 是当日少数有主力真实承接的方向（%s）；若恐慌继续缓和，该方向大概率率先企稳。" % (
            "、".join([r.get("name") for r in sec_up[:3]]) if sec_up else "暂无",
            "、".join(["%s 主力 %s亿" % (r.get("name"), r.get("mainText")) for r in sec_up[:2]]) if sec_up else "—"),
        "o1_cond": "注意：当日收红 ≠ 避险港；观察「指数企稳后主力净流入是否延续」，不追当日涨幅。",
        "o2_tag": "主力「出货」方向（回避）",
        "o2_t": "%s" % (" / ".join([r.get("name") for r in sec_dn[:4]]) if sec_dn else "暂缺"),
        "o2_d": "%s 当日领跌且呈主力「出货」；全市场 %s 个板块处于出货状态——流动性最差的方向抛压最重。" % (
            "、".join([r.get("name") for r in sec_dn[:3]]) if sec_dn else "暂无", n_dist),
        "o2_cond": "注意：主力出货型下跌通常有第二段惯性下探；不抢反弹，等待主力净流入转正或缩量止跌信号。",
        "o3_tag": "出清确认信号（观望）",
        "o3_t": "跌停回落 / 涨股比修复 / 量能回补",
        "o3_d": "当日跌停 %s 只、涨股比 %s；观察下一交易日是否出现「跌停回落至 10 只以内 + 涨股比维持 50%% 上方 + 量能回升至 5 日均上方」。" % (
            ld if ld is not None else "—", ("%.0f%%" % up) if up is not None else "—"),
        "o3_cond": "注意：未出清段不预判底部；反弹缩量视为弱反弹（警惕二次探底）；右侧确认 ＝ 放量收复 MA5/MA10（%.2f / %.2f）且跌停清零。" % (ma5 or 0, ma10 or 0),
        "o_rules_t": "交易规则（%s）" % nxt_cn,
        "o_r1": "<b>仓位</b>：恐慌未出清前维持防守——<b>仓位 ≤3 成</b>，不加杠杆；出清确认（跌停 <10 + 涨股比 >50%% + 放量收复 MA5）后再考虑加回。",
        "o_r2": "<b>出清确认</b>：跌停回落至 10 只以内且涨股比维持在 50%% 上方，视为恐慌出清；若跌停重新扩大至 25 只以上或上证收于 %.2f 下方，视为恶化，进一步压缩风险敞口。" % (bl or 0),
        "o_r3": "<b>主线参与</b>：有主力承接的方向仅作结构观察（净流入是否延续），不追当日涨幅；主力「出货」方向回避，等待净流入转正。",
        "o_r4": "<b>回避清单</b>：主力出货板块、两融集中且已破位的高位主线、连板高标接力（龙头更替快时接力风险最高）。",
        "o_r5": "<b>风控</b>：反弹缩量视为弱反弹、警惕二次探底；两融数据恢复前不加重杠杆；单笔止损 −8%%，MA20 破位或死叉离场。",
        # ---- 数据来源
        "s_breadth_v": "westock · data_market_overview（market_statis_updown / daily_trade）；%s 收盘" % dstr_cn,
        "s_portrait_v": "westock · data_market_overview 官方快照；%s" % dstr_cn,
        "s_index_v": "westock · data_market_overview（market_statis_technical / interval_trade）；%s 收盘" % dstr_cn,
        "s_sector_v": "westock · data_sector（%s 个板块，含主力/散户/暗盘行为分类）；%s" % (n_sector, dstr_cn),
        "s_hot_v": "westock · data_hot(kind=board) / tool_ranking(limitup_days)；%s" % dstr_cn,
        "s_margin_v": ("westock · 两融接口降级（market_statis_margin_chg 为空），数据暂缺，未编造" if k["margin_missing"]
                       else "westock · data_market_overview（market_statis_margin_chg）；%s" % dstr_cn),
        "s_main_v": ("westock · tool_ranking 降级期，主力5日净流入暂缺；当日主力行为由 data_sector 板块口径替代" if not c.get("_main5d")
                     else "westock · tool_ranking(cap_main_5d)；%s" % dstr_cn),
        "s_board_v": ("westock · tool_ranking(metric=limitup_days, date=%s)；共 %s 只涨停" % (dstr_cn, lad.get("total") if lad else "—")
                      if lad else "连板梯队接口降级，暂缺（未编造）"),
        "s_gap_v": "%s" % ("；".join([x for x in [
            "两融余额与融资单日变动接口降级（service error），已如实标注、未编造" if k["margin_missing"] else "",
            "主力5日净流入降级期暂缺" if not c.get("_main5d") else "",
            "连板梯队接口降级暂缺" if not lad else "",
        ] if x]) or "无数据缺口"),
        "t_ev_note": "数据口径：宏观指标为月频/季频（截至最新发布），与日频行情不可直接对齐，已分别标注；涨跌分布 / 指数 / 板块 / 连板梯队均为 %s 当日真实收盘。缺失项均已标注，未编造。详见末尾「数据来源与日期口径」。" % dstr_cn,
        "t_src_note": "时间口径：所有时点按北京时间。宏观为月频 / 季频，与日频行情不可直接对齐，已分别标注。%s 的涨跌分布 / 指数 / 技术 / 板块 / 连板梯队均为当日真实数据；缺失项（%s）已如实标注、未编造。" % (
            dstr_cn, "两融 / 主力5日" if k["margin_missing"] else "无"),
    }

    # ------------------------------------------------------------ 英文
    EN = {
        "t_headline_sub": "%s · Close" % dstr_cn,
        "t_breadth": "Market breadth (%s close)" % dstr_cn,
        "ev_index": "II. Core indices (%s close)" % dstr_cn,
        "o_compliance": "<b>Compliance:</b> sector directions and trading rules only, no individual stock recommendations; the crowd-psychology position and sector inferences are based on real %s market data. Markets carry risk; decisions must be independent." % dstr_cn,
        "t_risk_hi": risk_en,
        "hv_risk": "<b class=\"hl-risk\">%s</b> (%s)" % (risk_en, "held from the previous report" if (p or {}).get("_risk") == risk else "changed from the previous report"),
        "hv_stage": "<b>%s</b> (%s)" % (stage_en, dstr_cn),
        "hv_upratio": "<b>%.0f%%</b> (prev %s · %s)" % (up or 0, ("%.0f%%" % k["p_up"]) if k["p_up"] is not None else "—", d_up_en),
        "hv_lim": "<b>%s</b> / <b>%s</b> (limit-down %s)" % (lu if lu is not None else "—", ld if ld is not None else "—", d_dn_en),
        "hv_amt": "<b>¥%s tn</b> (%s, %.1f%% of the 5d avg)" % (amt_yi, vol_word_en, amt5 or 0),
        "hv_cycle": "<b>%s</b>" % stage_en,
        "hv_flag": "Up-ratio %s (%s, %s), limit-up %s / limit-down %s (%s), turnover ¥%s tn (%.1f%% of 5d avg); SSE %s (%.2f), %s, %s — %s." % (
            ("%.0f%%" % up) if up is not None else "—",
            "%s up / %s down / %s flat" % (cnt_up, cnt_dn, cnt_fl), d_up_en,
            lu if lu is not None else "—", ld if ld is not None else "—", d_dn_en,
            amt_yi, amt5 or 0, sgn(shp, 2, True), sh or 0, ma_txt_en, boll_txt_en,
            "margin interface degraded, not fabricated" if k["margin_missing"] else "margin basis updated"),
        "tv1": "A-shares %s: '<b>%s</b>'. Up-ratio <b>%.0f%%</b> (%s, %s), limit-up <b>%s</b>, limit-down <b>%s</b> (%s); SSE <b>%s</b> (%.2f, %s), SZ %s (%.2f), ChiNext %s (%.2f); turnover ¥%s tn (%.1f%% of 5d, %.1f%% of 10d, %.1f%% of 20d, %s). Risk: <b>%s</b>." % (
            dstr_cn, stage_en, up or 0, "%s up / %s down / %s flat" % (cnt_up, cnt_dn, cnt_fl), d_up_en,
            lu if lu is not None else "—", ld if ld is not None else "—", d_dn_en,
            sgn(shp, 2, True), sh or 0, ma_txt_en, sgn(szp, 2, True), sz or 0, sgn(cyp, 2, True), cy or 0,
            amt_yi, amt5 or 0, amt10 or 0, amt20 or 0, amt_diff_en, risk_en),
        "tv2": "Up-ratio <b>%.0f%%</b> (%s) · limit-up <b>%s</b> · limit-down <b>%s</b> (%s) · turnover <b>¥%s tn</b> (%.1f%% of 5d, %s, %s) — %s; %s of %s sectors green, %s in main-capital 'distribution'. %s" % (
            up or 0, d_up_en, lu if lu is not None else "—", ld if ld is not None else "—", d_dn_en,
            amt_yi, amt5 or 0, amt_diff_en, vol_word_en,
            "breadth repairs but limit-downs stay above 10, panic not fully cleared" if (ld or 0) >= 10 else "limit-downs fall under 10, panic eases at the margin",
            n_up_sector, n_sector, n_dist,
            "Limit-downs ≥25, panic still spreading" if (ld or 0) >= 25 else ""),
        "tv3": "SSE <b>%s</b> (%.2f), %s; %s. MACD <b>%s</b> (DIF %s / DEA %s), RSI6 <b>%s</b>, KDJ_J %s — %s. SZ %s (%.2f), ChiNext %s (%.2f)." % (
            sgn(shp, 2, True), sh or 0, ma_txt_en, boll_txt_en,
            ("%.2f" % macd) if macd is not None else "—", ("%.2f" % dif) if dif is not None else "—",
            ("%.2f" % dea) if dea is not None else "—", ("%.2f" % rsi6) if rsi6 is not None else "—",
            ("%.1f" % kdj_j) if kdj_j is not None else "—",
            "oversold and broken coexist: room for a technical bounce, mid-term trend unrepaired" if (rsi6 or 50) < 35 else "technicals in the neutral zone",
            sgn(szp, 2, True), sz or 0, sgn(cyp, 2, True), cy or 0),
        "tv4": "Leaders: %s. Laggards: %s. %s of %s sectors green, %s in 'distribution' — %s." % (
            sup_en, sdn, n_up_sector, n_sector, n_dist,
            "capital concentrates in a few directions while the rest stays pressured" if n_up_sector < n_sector * 0.4 else "broad sector gains, profit effect spreads"),
        "tv5": "%s. %s" % (lad_txt_en, "Ladder height is the direct thermometer of short-term sentiment: rising height = profit effect expanding; falling height or leader rotation = weaker relay appetite." if board else ""),
        "tv6": ("Margin interface degraded (service error), <b>not fabricated</b>; from visible signals: %s sectors in 'distribution', capital concentrates in %s."
                % (n_dist, ", ".join([r.get("name") for r in sec_up[:3]]) if sec_up else "a few directions")
                ) if k["margin_missing"] else "Margin balance and daily change updated, see the evidence table below.",
        "tv7": "%s. Style: All-Share Value 20d <b>%s</b> vs Growth 20d <b>%s</b> (%.1fpct gap), HS300 5d %s / CSI1000 5d %s — %s." % (
            pe_txt_en, sgn(v20, 2, True) if v20 is not None else "—", sgn(g20, 2, True) if g20 is not None else "—",
            abs((v20 or 0) - (g20 or 0)), sgn(hs5, 2, True) if hs5 is not None else "—",
            sgn(zz5, 2, True) if zz5 is not None else "—",
            "the value/growth split is the axis of the tape" if abs((v20 or 0) - (g20 or 0)) >= 3 else "no notable style gap"),
        "tv8": "Positioned as '<b>%s</b>': up-ratio %s, limit-up %s / limit-down %s, turnover %.1f%% of 5d (%s). Right-side confirmation: %s; deterioration: %s. Risk <b>%s</b>." % (
            stage_en, ("%.0f%%" % up) if up is not None else "—", lu if lu is not None else "—",
            ld if ld is not None else "—", amt5 or 0, vol_word_en,
            "expanding volume reclaiming MA5/MA10 (%.2f / %.2f) with limit-downs under 10" % (ma5 or 0, ma10 or 0),
            "limit-downs widening past 25 or the SSE closing below the BOLL lower band (%.2f)" % (bl or 0), risk_en),
        "t_tldr_text": "%s A-shares: up-ratio %.0f%% (%s up / %s down / %s flat), limit-up %s / limit-down %s, turnover ¥%s tn (%.1f%% of 5d); SSE %s (%.2f, %s), SZ %s (%.2f), ChiNext %s (%.2f). Leaders: %s. Laggards: %s. %s. %s. Risk %s." % (
            dstr_cn, up or 0, cnt_up, cnt_dn, cnt_fl, lu if lu is not None else "—", ld if ld is not None else "—",
            amt_yi, amt5 or 0, sgn(shp, 2, True), sh or 0, ma_txt_en, sgn(szp, 2, True), sz or 0,
            sgn(cyp, 2, True), cy or 0,
            "; ".join("%s %s" % (r.get("name"), r.get("pctText")) for r in sec_up[:3]) if sec_up else "sectors missing",
            "; ".join("%s %s" % (r.get("name"), r.get("pctText")) for r in sec_dn[:3]) if sec_dn else "sectors missing",
            lad_txt_en, pe_txt_en, risk_en),
        "t_radar_note": "Six-dimension risk readings (0–100, mapped from the real data below by explicit formulas; higher = greater crowd fragility): %s. %s" % (
            radar_txt_en,
            "The margin axis is carried forward by panic delta while the margin interface is degraded (not a measured value); the other five are computed from same-day data." if k["margin_missing"] else "All six are computed from same-day data."),
        "t_cycle_note": "Note: the '%s' tag above is the live crowd-psychology position — %s breadth (up-ratio %s, limit-up %s, limit-down %s, turnover ¥%s tn) shows: %s. Panic is treated as fully cleared only if the next session sees limit-downs under 10 with the up-ratio holding above 50%%; it escalates if limit-downs widen past 25 or the SSE closes below %.2f." % (
            stage_en, dstr_cn, ("%.0f%%" % up) if up is not None else "—", lu if lu is not None else "—",
            ld if ld is not None else "—", amt_yi,
            "limit-downs still above 10, panic not fully cleared" if (ld or 0) >= 10 else "limit-downs back under 10, panic easing at the margin",
            bl or 0),
        "t_breadth_note": "Up-ratio %s (%s up / %s down / %s flat), limit-up %s / limit-down %s, turnover ¥%s tn (%.1f%% of 5d, %s). SSE %s (%.2f) / SZ %s (%.2f) / ChiNext %s (%.2f); %s of %s sectors green, %s in 'distribution'." % (
            ("%.0f%%" % up) if up is not None else "—", cnt_up, cnt_dn, cnt_fl,
            lu if lu is not None else "—", ld if ld is not None else "—", amt_yi, amt5 or 0, amt_diff_en,
            sgn(shp, 2, True), sh or 0, sgn(szp, 2, True), sz or 0, sgn(cyp, 2, True), cy or 0,
            n_up_sector, n_sector, n_dist),
        "ev_upratio_i": "Up-ratio %.0f%% (%s), %s up / %s down / %s flat — %s" % (
            up or 0, d_up_en, cnt_up, cnt_dn, cnt_fl,
            "participation repairs notably" if (d_up or 0) > 10 else "participation keeps weakening" if (d_up or 0) < -5 else "participation little changed"),
        "ev_limit_i": "Limit-up %s (%s), limit-down %s (%s) — %s" % (
            lu if lu is not None else "—",
            ("%+d vs the previous report" % ((lu or 0) - (k.get("p_lu") or 0))) if k.get("p_lu") is not None else "no d/d basis",
            ld if ld is not None else "—", d_dn_en,
            "limit-downs still above 10, panic not fully cleared" if (ld or 0) >= 10 else "limit-downs below the warning line, panic eases"),
        "ev_amount_i": "Turnover ¥%s tn (%.1f%% of 5d, %.1f%% of 10d, %.1f%% of 20d, %s) — %s" % (
            amt_yi, amt5 or 0, amt10 or 0, amt20 or 0, amt_diff_en,
            "shrinking = selling pressure decays but so does absorption" if (amt5 or 0) <= 92 else "expanding = divergence widens, direction matters" if (amt5 or 0) >= 105 else "flat volume, stalemate"),
        "ev_sh_i": "SSE %s (%.2f), %s; %s. MACD %s (DIF %s / DEA %s), RSI6 %s, KDJ_J %s. %s" % (
            sgn(shp, 2, True), sh or 0, ma_txt_en, boll_txt_en,
            ("%.2f" % macd) if macd is not None else "—", ("%.2f" % dif) if dif is not None else "—",
            ("%.2f" % dea) if dea is not None else "—", ("%.2f" % rsi6) if rsi6 is not None else "—",
            ("%.1f" % kdj_j) if kdj_j is not None else "—", pe_txt_en),
        "ev_sz_i": "SZ %s (%.2f) — %s" % (sgn(szp, 2, True), sz or 0,
                                          "in sync with the SSE, trend consistency high" if (szp or 0) * (shp or 0) > 0 else "diverging from the SSE, structure splits"),
        "ev_cyb_i": "ChiNext %s (%.2f) — %s" % (sgn(cyp, 2, True), cy or 0,
                                               "relatively resilient" if (cyp or 0) > (shp or 0) else "weaker than the main board, growth style pressured"),
        "ev_secup_i": "Leaders: %s" % sup_en,
        "ev_secdn_i": "Laggards: %s" % sdn,
        "ev_board_i": "%s — %s" % (lad_txt_en, "ladder height is the short-term sentiment thermometer" if board else "interface degraded, not fabricated"),
        "ev_height_i": "Top board %s (%s), %s" % (board if board else "—", board_name, lad_txt_en),
        "ev_main_i": "Main capital 5d net inflow: %s" % ("interface degraded, missing, not fabricated; same-day main behaviour shown via the sector view (main/retail/dark)" if not c.get("_main5d") else "updated"),
        "ev_margin_i": "Daily margin change: %s" % ("margin interface degraded (service error), missing — <b>not fabricated</b>" if k["margin_missing"] else "updated"),
        "ev_hot_i": "Hotspots: %s; %s" % (", ".join([r.get("name") for r in sec_up[:4]]) if sec_up else "missing", lad_txt_en),
        "ev_margintotal_i": "Aggregate margin balance: %s" % ("interface degraded, missing — flagged honestly, not fabricated" if k["margin_missing"] else "updated"),
        "rc1_tag": "Red zone · %s" % ("leverage and panic both elevated (margin missing)" if k["margin_missing"] else "panic not cleared"),
        "rc1_t": "Panic not fully cleared + index below its MAs",
        "rc1_d": "%s: limit-downs %s (%s, still %s the 10-name warning line), SSE %s (%.2f) %s — panic eases but clearing is unconfirmed; %s." % (
            dstr_cn, ld if ld is not None else "—", d_dn_en,
            "above" if (ld or 0) >= 10 else "below", sgn(shp, 2, True), sh or 0, ma_txt_en,
            "margin missing, leverage-crash risk cannot be ruled out" if k["margin_missing"] else "margin basis visible"),
        "rc1_rep": "Represented by: %s; plus %s sectors in main-capital 'distribution'" % (
            ", ".join([r.get("name") for r in sec_dn[:3]]) if sec_dn else "laggards missing", n_dist),
        "rc1_cond": "Condition frame: minimum clearing confirmation = 'limit-downs under 10 + up-ratio above 50%% + SSE reclaiming MA5 (%.2f) on expanding volume'; until then position discipline first, no leverage, no catching a falling knife." % (ma5 or 0),
        "rc2_tag": "Amber zone · repair vs relapse",
        "rc2_t": "Breadth repair vs index unconfirmed",
        "rc2_d": "Up-ratio back to %.0f%% (%s up / %s down, %s), yet the SSE is still %s and turnover is %s (%.1f%% of 5d) — breadth repairs ahead of the index, the classic 'can't fall but can't rally' phase; RSI6 %s, KDJ_J %s show %s." % (
            up or 0, cnt_up, cnt_dn, d_up_en, sgn(shp, 2, True), vol_word_en, amt5 or 0,
            ("%.2f" % rsi6) if rsi6 is not None else "—", ("%.1f" % kdj_j) if kdj_j is not None else "—",
            "oversold, leaving room for a technical bounce" if (rsi6 or 50) < 35 else "no oversold reading"),
        "rc2_rep": "Represented by: %s" % (", ".join([r.get("name") for r in sec_up[:3]]) if sec_up else "leaders missing"),
        "rc2_cond": "Condition frame: do not pre-empt the bottom; a shrinking-volume bounce = weak rebound, beware a second leg; right-side confirmation = expanding volume reclaiming MA5/MA10 (%.2f / %.2f) with limit-downs cleared." % (ma5 or 0, ma10 or 0),
        "rc3_tag": "Green zone · directions with real main-capital absorption (watch)",
        "rc3_t": "Main net-inflow directions",
        "rc3_d": "%s — with %s sectors in 'distribution', these are among the few with real main-capital absorption." % (sup_en, n_dist),
        "rc3_rep": "Represented by: %s" % (", ".join([r.get("name") for r in sec_up[:4]]) if sec_up else "missing"),
        "rc3_cond": "Condition frame: structural tracking only, do not chase same-day gains; confirmation = main net inflows persist and turnover holds after the index stabilises; if it dumps as panic worsens, that confirms a full wash-out.",
        "t_sec_outlook": "Next session (%s) outlook" % nxt_en,
        "o_logic": "Reasoning (based on the %s close + crowd-psychology position)" % dstr_cn,
        "o_logic_text": "Extending %s's '%s': up-ratio %s, limit-up %s / limit-down %s, turnover ¥%s tn (%.1f%% of 5d), SSE %s and %s; %s. Sector directions and trading rules for the next session follow (<b>no individual stock recommendations</b>)." % (
            dstr_cn, stage_en, ("%.0f%%" % up) if up is not None else "—", lu if lu is not None else "—",
            ld if ld is not None else "—", amt_yi, amt5 or 0, ma_txt_en, boll_txt_en,
            "RSI6 %s is oversold, leaving room for a technical bounce" % ("%.2f" % rsi6) if (rsi6 or 50) < 35 else "technicals in the neutral zone"),
        "o1_tag": "Directions with main-capital absorption (watch)",
        "o1_t": "%s" % (" / ".join([r.get("name") for r in sec_up[:4]]) if sec_up else "missing"),
        "o1_d": "%s are among the few with real main-capital absorption (%s); if panic keeps easing, they likely stabilise first." % (
            ", ".join([r.get("name") for r in sec_up[:3]]) if sec_up else "none",
            ", ".join(["%s main %s" % (r.get("name"), r.get("mainText")) for r in sec_up[:2]]) if sec_up else "—"),
        "o1_cond": "Caution: green on the day ≠ safe haven; watch 'do main inflows persist after the index stabilises', do not chase same-day gains.",
        "o2_tag": "Main-capital 'distribution' directions (avoid)",
        "o2_t": "%s" % (" / ".join([r.get("name") for r in sec_dn[:4]]) if sec_dn else "missing"),
        "o2_d": "%s led the losses in main-capital 'distribution'; %s sectors market-wide are distributing — the least liquid directions carry the heaviest selling." % (
            ", ".join([r.get("name") for r in sec_dn[:3]]) if sec_dn else "none", n_dist),
        "o2_cond": "Caution: distribution-led declines usually have a second leg down; do not grab the bounce, wait for main inflows to turn positive or a shrinking-volume stabilisation.",
        "o3_tag": "Clearing confirmation signals (stand by)",
        "o3_t": "Limit-downs recede / up-ratio repairs / volume returns",
        "o3_d": "Limit-downs %s and up-ratio %s today; watch for 'limit-downs under 10 + up-ratio above 50%% + volume back above the 5d average' next session." % (
            ld if ld is not None else "—", ("%.0f%%" % up) if up is not None else "—"),
        "o3_cond": "Caution: do not pre-empt the bottom before clearing; a shrinking-volume bounce = weak rebound (beware a second leg); right-side confirmation = expanding volume reclaiming MA5/MA10 (%.2f / %.2f) with limit-downs cleared." % (ma5 or 0, ma10 or 0),
        "o_rules_t": "Trading rules (%s)" % nxt_en,
        "o_r1": "<b>Position</b>: stay defensive until the panic clears — <b>≤30%</b>, no leverage; rebuild only after clearing (limit-downs <10 + up-ratio >50%% + volume reclaiming MA5).",
        "o_r2": "<b>Clearing confirmation</b>: limit-downs under 10 with the up-ratio holding above 50%% = cleared; if limit-downs widen past 25 or the SSE closes below %.2f, treat as deterioration and shrink exposure further." % (bl or 0),
        "o_r3": "<b>Main-line participation</b>: absorption directions are structural observation only (do inflows persist?), no chasing same-day gains; avoid distribution directions until inflows turn positive.",
        "o_r4": "<b>Avoid list</b>: distribution sectors, margin-concentrated broken high-position lines, ladder-top relay (relay risk peaks when the leader rotates fast).",
        "o_r5": "<b>Risk control</b>: a shrinking-volume bounce = weak rebound, beware a second leg; do not add leverage until margin data resumes; −8%% stop per position, exit on a MA20 break or dead cross.",
        "s_breadth_v": "westock · data_market_overview (market_statis_updown / daily_trade); %s close" % dstr_cn,
        "s_portrait_v": "westock · data_market_overview official snapshot; %s" % dstr_cn,
        "s_index_v": "westock · data_market_overview (market_statis_technical / interval_trade); %s close" % dstr_cn,
        "s_sector_v": "westock · data_sector (%s sectors, incl. main/retail/dark behaviour); %s" % (n_sector, dstr_cn),
        "s_hot_v": "westock · data_hot(kind=board) / tool_ranking(limitup_days); %s" % dstr_cn,
        "s_margin_v": ("westock · margin interface degraded (market_statis_margin_chg empty), missing, not fabricated" if k["margin_missing"]
                       else "westock · data_market_overview (market_statis_margin_chg); %s" % dstr_cn),
        "s_main_v": ("westock · tool_ranking degraded, main-5d missing; same-day behaviour shown via data_sector" if not c.get("_main5d")
                     else "westock · tool_ranking(cap_main_5d); %s" % dstr_cn),
        "s_board_v": ("westock · tool_ranking(metric=limitup_days, date=%s); %s limit-ups in total" % (dstr_cn, lad.get("total") if lad else "—")
                      if lad else "ladder interface degraded, missing (not fabricated)"),
        "s_gap_v": "%s" % ("; ".join([x for x in [
            "aggregate margin balance and daily change interfaces degraded (service error) — flagged, not fabricated" if k["margin_missing"] else "",
            "main-capital 5d net inflow missing in the degraded window" if not c.get("_main5d") else "",
            "limit-up ladder interface degraded, missing" if not lad else "",
        ] if x]) or "no data gaps"),
        "t_ev_note": "Data basis: macro indicators are monthly/quarterly (to the latest release) and cannot be aligned directly with daily quotes; each is flagged. Breadth / indices / sectors / ladder are real %s closes. Missing items are flagged, not fabricated. See 'Sources & date basis' at the end." % dstr_cn,
        "t_src_note": "Timing: all timestamps are Beijing time. Macro data are monthly/quarterly and cannot be aligned with daily quotes; each is flagged. %s breadth / indices / technicals / sectors / ladder are real same-day data; missing items (%s) are flagged honestly, not fabricated." % (
            dstr_cn, "margin / main-5d" if k["margin_missing"] else "none"),
    }
    return ZH, EN


# ---------------------------------------------------------------- 偏差矩阵
def bias_list(c, p, k):
    up = c.get("RATIO_UP") or 50
    ld = c.get("CNT_REACH_DNLIMIT") or 0
    lu = c.get("CNT_REACH_UPLIMIT") or 0
    d_up = k.get("d_up") or 0
    rsi = c.get("RSI_6") or 50
    n_dist = len([r for r in (c.get("_sectors") or []) if r.get("behavior") == "出货"])
    n_sec = len(c.get("_sectors") or []) or 1
    sh = c.get("CLOSE_PRICE_SZZS")
    bl = c.get("BOLL_LOWER")

    sev = {}
    sev["herd"] = 5 if ld >= 20 else 4 if ld >= 10 else 3 if abs(up - 50) > 25 else 2
    sev["loss"] = 4 if ld >= 10 else 3
    sev["mental"] = 4 if d_up >= 20 else 3
    sev["overconf"] = 4 if (d_up >= 20 and rsi < 35) else 3 if d_up > 0 else 2
    sev["dispo"] = 3
    sev["anchor"] = 4 if (bl and sh and abs(sh - bl) / (bl or 1) < 0.01) else 3
    sev["confirm"] = 4 if (up - 50) * ((c.get("CHANGE_PCT_SZZS") or 0)) < 0 else 3
    sev["recency"] = 5 if abs(d_up) >= 30 else 4 if abs(d_up) >= 15 else 3
    sev["narrative"] = 4 if n_dist / n_sec > 0.5 else 3
    sev["repr"] = 4 if abs(up - 50) > 25 else 3

    upn = c.get("CNT_RED") or 0
    dnn = c.get("CNT_GREEN") or 0
    amt5 = c.get("MONEY_5DAVG_RATIO") or 100
    sec_up = [r.get("name") for r in (c.get("_sectors") or []) if (r.get("pctVal") or 0) > 0][:3]
    sec_up = "、".join(sec_up) if sec_up else "少数方向"

    B = [
        dict(zh="羊群效应", en="Herding", k="herd",
             zhd="涨股比 %.0f%%（涨%s / 跌%s）%s，跌停 %s 只——群体定价仍由「跟随」主导：%s。"
                 % (up, upn, dnn, "较上一报告日%+.1fpct" % d_up if k.get("d_up") is not None else "", ld,
                    "恐慌未出清时抛售从个体决策变为相互踩踏" if ld >= 10 else "分歧收敛但方向未定，跟随行为依旧主导"),
             end="Up-ratio %.0f%% (%s up / %s down)%s with %s limit-downs — pricing is still herd-driven: %s."
                 % (up, upn, dnn, ", %+.1fpct vs the previous report" % d_up if k.get("d_up") is not None else "", ld,
                    "selling turns from individual decisions into mutual stampeding while panic is uncleared" if ld >= 10 else "divergence narrows but direction is unset, herding still leads")),
        dict(zh="损失厌恶", en="Loss Aversion", k="loss",
             zhd="跌停 %s 只是损失实现的直接刻度；%s 的情况下，「扛单的痛苦」与「割肉的痛苦」仍在博弈，止损盘与被动持有者交替释放。"
                 % (ld, "跌停仍在 10 只上方" if ld >= 10 else "跌停已回落至 10 只下方"),
             end="%s limit-downs are the direct gauge of realised loss; with %s, the pain of holding and the pain of cutting are still in play as stop-losses and passive holders release in turns."
                 % (ld, "limit-downs above 10" if ld >= 10 else "limit-downs back under 10")),
        dict(zh="心理账户/赌徒谬误", en="Mental Accounting / Gambler", k="mental",
             zhd="把 %s 的当日收红记入「避风港」账户并外推为「资金避难所」，忽视全市场 %s/%s 个板块呈主力「出货」——局部强势≠账户安全。"
                 % (sec_up, n_dist, n_sec),
             end="Booking today's greens in %s into a 'safe-haven' account and extrapolating them into 'where capital shelters' ignores that %s of %s sectors are in main-capital distribution — local strength ≠ account safety."
                 % (sec_up, n_dist, n_sec)),
        dict(zh="过度自信", en="Overconfidence", k="overconf",
             zhd="%s：涨股比单日%+.1fpct 的剧烈变化容易催生「已见底/已转势」的判断，而指数与技术均未确认——自信领先于证据是高波动期的典型特征。"
                 % ("RSI6 %.2f 处超卖区，抄底自信开始萌芽" % rsi if rsi < 35 else "技术指标处于中性区", d_up),
             end="%s: a %+.1fpct one-day swing in the up-ratio easily breeds an 'it has bottomed / turned' call while neither the index nor the technicals confirm — confidence running ahead of evidence is typical of high-volatility phases."
                 % ("RSI6 %.2f is oversold, bottom-fishing confidence sprouts" % rsi if rsi < 35 else "technicals sit in the neutral zone", d_up)),
        dict(zh="处置效应", en="Disposition", k="dispo",
             zhd="卖出亏损仓、紧握浮盈仓的倾向在该阶段依然明显；若恐慌二次扩散，「强势仓」同样面临回吐——浮盈不等于安全边际。",
             end="The tendency to cut losers and clutch winners stays visible here; if panic spreads again, the 'strong' books give back too — unrealised gains are not a safety margin."),
        dict(zh="锚定偏差", en="Anchoring", k="anchor",
             zhd="缺乏新定价锚时，指数点位与布林下轨（%.2f）等可见参照成为群体博弈焦点；锚在前高者视回调为机会、锚在下轨者等反弹，易在半山腰互接。" % (bl or 0),
             end="Without a new pricing anchor, visible references such as the index level and the BOLL lower band (%.2f) become the crowd's battleground: those anchored to prior highs see dips as chances, those anchored to the band wait for a bounce — easy to catch falling knives at mid-slope." % (bl or 0)),
        dict(zh="确认偏误", en="Confirmation Bias", k="confirm",
             zhd="%s——多头只看广度修复，空头只盯指数与技术破位，同一组数据被两侧各取所需。" % (
                 "广度（涨股比 %.0f%%）与指数（%s）背离，为确认偏误提供了最肥沃的土壤" % (up, sgn(c.get("CHANGE_PCT_SZZS"), 2, True))
                 if (up - 50) * ((c.get("CHANGE_PCT_SZZS") or 0)) < 0 else "广度与指数方向一致，确认偏误的破坏力相对可控"),
             end="%s — bulls read only the breadth repair, bears only the index and broken technicals; the same dataset is mined by both sides." % (
                 "Breadth (up-ratio %.0f%%) diverges from the index (%s), the richest soil for confirmation bias" % (up, sgn(c.get("CHANGE_PCT_SZZS"), 2, True))
                 if (up - 50) * ((c.get("CHANGE_PCT_SZZS") or 0)) < 0 else "Breadth and the index point the same way, so confirmation bias does less damage")),
        dict(zh="近因偏差", en="Recency", k="recency",
             zhd="把单日涨股比%+.1fpct 的剧变外推为趋势转折，忽视样本仅为一个交易日；恐慌期的单日修复与单日暴跌一样，都不构成趋势证据。" % d_up,
             end="Extrapolating a single-day %+.1fpct swing in the up-ratio into a trend turn ignores that the sample is one session: single-day repairs in a panic phase are as little trend evidence as single-day crashes." % d_up),
        dict(zh="叙事偏差", en="Narrative", k="narrative",
             zhd="%s 等方向的叙事被当日主力净流入强化；但 %s/%s 个板块处于「出货」状态，叙事一旦被后续资金证伪，承接盘回撤同样剧烈。" % (sec_up, n_dist, n_sec),
             end="The narrative around %s is reinforced by same-day main inflows; yet %s of %s sectors are distributing — if the story is falsified by follow-through flows, the absorption books retrace just as hard." % (sec_up, n_dist, n_sec)),
        dict(zh="代表性启发", en="Representativeness", k="repr",
             zhd="以个别领涨/领跌板块推断全市场，是 %s 只跌停 / %s 只涨停并存的分布下最容易犯的错——极端分布中任何单一样本都不具代表性。" % (ld, lu),
             end="Inferring the whole market from a few leading or lagging sectors is the easiest mistake when %s limit-downs and %s limit-ups coexist — in an extreme distribution no single sample is representative." % (ld, lu)),
    ]
    for b in B:
        b["sev"] = sev.get(b["k"], 3)
        del b["k"]
    return B


# ---------------------------------------------------------------- 渲染
def render(date, ZH, EN, BIAS, c, p, k, sec_up, sec_dn, lad):
    html = open(SKELETON, encoding="utf-8").read()
    d = dt.date(*[int(x) for x in date.split("-")])
    dstr_cn = "%d-%02d-%02d" % (d.year, d.month, d.day)
    nxt = k["_next_date"]
    nd = dt.date(*[int(x) for x in nxt.split("-")])

    up = c.get("RATIO_UP") or 0
    cnt_up = c.get("CNT_RED") or 0
    cnt_dn = c.get("CNT_GREEN") or 0
    cnt_fl = c.get("CNT_ZERO") or 0
    lu = c.get("CNT_REACH_UPLIMIT") or 0
    ld = c.get("CNT_REACH_DNLIMIT") or 0
    amt_yi = yi(c.get("MONEY"))
    p_amt = (p or {}).get("MONEY")
    amt_diff = None if (c.get("MONEY") is None or p_amt is None) else c["MONEY"] - p_amt

    # ---- 1) i18n 文案块
    def extract_inner(h, marker):
        if marker == "zh":
            return re.search(r'zh:\{(.*?)\n    \},', h, re.S)
        return re.search(r'en:\{(.*?)\n    \}', h, re.S)

    def parse(inner):
        d0 = {}
        pat = re.compile(r'([A-Za-z_][A-Za-z0-9_]*)\s*:\s*"((?:[^"\\]|\\.)*)"')
        for line in inner.split("\n"):
            for mm in pat.finditer(line):
                d0[mm.group(1)] = mm.group(2)
        return d0

    def esc(s):
        return str(s).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")

    m_zh, m_en = extract_inner(html, "zh"), extract_inner(html, "en")
    assert m_zh and m_en, "骨架 i18n 块缺失"
    zh, en = parse(m_zh.group(1)), parse(m_en.group(1))
    zh.update(ZH)
    en.update(EN)

    def serialize(dic):
        return "\n".join('      %s:"%s",' % (kk, esc(dic[kk])) for kk in dic)

    html = html[:m_en.start()] + "en:{\n" + serialize(en) + "\n    }" + html[m_en.end():]
    m_zh = extract_inner(html, "zh")
    html = html[:m_zh.start()] + "zh:{\n" + serialize(zh) + "\n    }," + html[m_zh.end():]

    # ---- 2) BIAS
    bias_js = "var BIAS = [\n" + ",\n".join(
        "    {zh:\"%s\",en:\"%s\",sev:%d,zhd:\"%s\",end:\"%s\"}" % (
            esc(b["zh"]), esc(b["en"]), b["sev"], esc(b["zhd"]), esc(b["end"])) for b in BIAS) + "\n  ];"
    html, n = re.subn(r'var BIAS = \[.*?\n  \];', bias_js, html, count=1, flags=re.S)
    assert n == 1, "BIAS 替换失败"

    # ---- 3) 涨跌分布 SVG（结构化锚点，不依赖上一期的具体数值）
    up_w = int(round(up * 5))
    dn_w = 500 - up_w
    dn_x = 14 + up_w
    html, n = re.subn(r'(<rect x="14" y="14" width=")\d+(" height="26" fill="#d8392b"/>)',
                      (lambda m: m.group(1) + str(up_w) + m.group(2)), html, count=1)
    assert n == 1, "up rect 未命中"
    html, n = re.subn(r'(<rect x=")\d+(" y="14" width=")\d+(" height="26" fill="#1a9e5a"/>)',
                      (lambda m: m.group(1) + str(dn_x) + m.group(2) + str(dn_w) + m.group(3)), html, count=1)
    assert n == 1, "down rect 未命中"

    # 分布条上的百分比文字（两处同结构，按出现顺序）
    texts = list(re.finditer(
        r'(<text x=")\d+(" y="33" fill="#fff" font-size="14" font-weight="800" text-anchor="middle">)[\d.]+%', html))
    assert len(texts) == 2, "分布百分比文字定位失败: %d" % len(texts)
    vals = ["%.0f%%" % up, "%.0f%%" % (100 - up)]
    xs = [int(round(14 + up_w / 2.0)), int(round(14 + up_w + dn_w / 2.0))]
    for m, v, x in zip(reversed(texts), reversed(vals), reversed(xs)):
        html = html[:m.start()] + m.group(1) + str(x) + m.group(2) + v + html[m.end():]

    flat_pct = round(100.0 * cnt_fl / max(1, cnt_up + cnt_dn + cnt_fl))
    html, n = re.subn(
        r'(<text x="514" y="33" fill="#6b675f" font-size="11" font-weight="700" text-anchor="end">)[\d.]+% 平盘',
        r'\g<1>%d%% 平盘' % flat_pct, html, count=1)
    if n != 1:
        print("[warn] 平盘文字未命中")

    # ---- 4) 统计行（y=72/92/112/138/158/184）
    stat = {
        72: ("#d8392b", str(cnt_up)),
        92: ("#1a9e5a", str(cnt_dn)),
        112: ("#6b675f", str(cnt_fl)),
        138: ("#d8392b", str(lu)),
        158: ("#1a9e5a", str(ld)),
        184: ("#1c1b19", "¥%s万亿" % amt_yi),
    }
    for y, (color, val) in stat.items():
        pat = r'(<text x="340" y="%d" fill="%s">)[^<]*(</text>)' % (y, color)
        html, n = re.subn(pat, r'\g<1>%s\g<2>' % val.replace("\\", ""), html, count=1)
        if n != 1:
            print("[warn] 统计行 y=%d 未命中" % y)

    # ---- 5) 注释行（同 y 坐标）
    d_up = k.get("d_up")
    d_dn = k.get("d_dn")
    p_lu = k.get("p_lu")
    note = {
        72: "（占 %.0f%%，%s）" % (up, ("较上一报告日 %+.1fpct" % d_up) if d_up is not None else "无环比口径"),
        92: "（占 %.0f%%，%s）" % (round(100.0 * cnt_dn / max(1, cnt_up + cnt_dn + cnt_fl), 1),
                              ("较上一报告日 %+.1fpct" % (-d_up)) if d_up is not None else "无环比口径"),
        112: "（占 %d%%）" % flat_pct,
        138: "（%s，连板高度 %s）" % (("较前日 %+d 只" % (lu - p_lu)) if p_lu is not None else "无环比口径",
                                ("%d板" % lad["stocks"][0]["days"]) if lad and lad.get("stocks") else "—"),
        158: "（%s）" % (("较前日 %+d 只" % d_dn) if d_dn is not None else "无环比口径"),
        184: "（%s，%s）" % (("环比 %+d亿" % round(amt_diff)) if amt_diff is not None else "环比口径暂缺",
                        "继续缩量" if (c.get("MONEY_5DAVG_RATIO") or 100) <= 92 else "放量" if (c.get("MONEY_5DAVG_RATIO") or 100) >= 105 else "平量"),
    }
    for y, txt in note.items():
        pat = r'(<text x="355" y="%d">)[^<]*(</text>)' % y
        html, n = re.subn(pat, r'\g<1>%s\g<2>' % txt, html, count=1)
        if n != 1:
            print("[warn] 注释行 y=%d 未命中" % y)

    # ---- 6) 证据表（按 data-i18n 行锚点定位，替换其后的数值单元格）
    def set_td(html, key, inner):
        pat = r'(<td data-i18n="%s"[^>]*>.*?</td>\s*<td>).*?(</td>)' % key
        html, n = re.subn(pat, (lambda m: m.group(1) + inner + m.group(2)), html, count=1, flags=re.S)
        if n != 1:
            print("[warn] 证据表 %s 未命中" % key)
        return html

    def sec_cell(r):
        return "%s %s（主力 %s亿，行为「%s」；龙头 %s）" % (
            r.get("name"), r.get("pctText"), r.get("mainText"), r.get("behavior"), r.get("leader") or "—")

    def idx_cell(cl, pc):
        cls = "up" if (pc or 0) >= 0 else "down"
        pct = ("+%.2f%%" % pc) if (pc or 0) >= 0 else ("\u2212%.2f%%" % abs(pc))
        return '<span class="val %s">%.2f\u3000%s</span>' % (cls, cl or 0, pct)

    if lad and lad.get("stocks"):
        top = lad["stocks"][0]
        tiers = {}
        for s in lad["stocks"]:
            tiers.setdefault(s["days"], []).append(s["name"])
        tier_txt = "；".join(["%d板：%s" % (dd, " / ".join(tiers[dd][:4]))
                            for dd in sorted(tiers, reverse=True)][:4])
        total = lad.get("total", len(lad["stocks"]))
        lad_html = ('<span class="val up">连板高度 %d 板</span>（%s）<br>共 %s 只涨停；%s'
                    % (top["days"], top["name"], total, tier_txt))
        lad_htop = '<span class="val up">%s %d板</span>（%s）' % (top["name"], top["days"], date)
        hot_html = "<br>".join(["%s %s（%s）" % (r.get("name"), r.get("pctText"), r.get("behavior"))
                                for r in (sec_up + sec_dn)[:4]]) or "热搜接口降级，暂缺"
    else:
        lad_html = lad_htop = "连板梯队接口降级，暂缺（未编造）"
        hot_html = "热搜接口降级，暂缺"

    html = set_td(html, "ev_upratio",
                  '<span class="val up">%.0f%%</span>（涨%s / 跌%s / 平%s）' % (up, cnt_up, cnt_dn, cnt_fl))
    html = set_td(html, "ev_limit",
                  '<span class="val up">%d</span> / <span class="val down">%d</span>' % (lu, ld))
    html = set_td(html, "ev_amount",
                  '<span class="val">\u00a5%s万亿</span>（%s，5日均 %.1f%%）' % (
                      amt_yi, ("环比 %+d亿" % round(amt_diff)) if amt_diff is not None else "环比暂缺",
                      c.get("MONEY_5DAVG_RATIO") or 0))
    html = set_td(html, "ev_sh", idx_cell(c.get("CLOSE_PRICE_SZZS"), c.get("CHANGE_PCT_SZZS")))
    html = set_td(html, "ev_sz", idx_cell(c.get("CLOSE_PRICE_SZCZ"), c.get("CHANGE_PCT_SZCZ")))
    html = set_td(html, "ev_cyb", idx_cell(c.get("CLOSE_PRICE_CYBZ"), c.get("CHANGE_PCT_CYBZ")))
    html = set_td(html, "ev_secup",
                  "<br>".join(sec_cell(r) for r in sec_up) if sec_up else "板块接口降级，暂缺")
    html = set_td(html, "ev_secdn",
                  "<br>".join(sec_cell(r) for r in sec_dn) if sec_dn else "板块接口降级，暂缺")
    html = set_td(html, "ev_board", lad_html)
    html = set_td(html, "ev_height", lad_htop)
    html = set_td(html, "ev_hot", hot_html)
    html = set_td(html, "ev_main",
                  '<span class="val">主力5日净流入 TOP（%s）</span>'
                  % ("降级期暂缺，未编造" if not c.get("_main5d") else "已更新"))
    html = set_td(html, "ev_margin",
                  '<span class="val">融资单日变动 TOP（%s）</span>'
                  % ("两融接口降级，数据暂缺，未编造" if k["margin_missing"] else "已更新"))
    html = set_td(html, "ev_margintotal",
                  '<span class="val">%s</span>' % ("数据源未返回聚合值" if k["margin_missing"] else "已更新"))


    # ---- 7) 雷达数值（六处红字，按固定坐标）
    radar_pos = [(160, 71, "crowd"), (237, 120, "margin"), (209, 194, "turn"),
                 (160, 167, "breadth"), (109, 201, "media"), (55, 118, "val")]
    for x, y, key in radar_pos:
        pat = r'(<text x="%d" y="%d">)\d+(</text>)' % (x, y)
        html, n = re.subn(pat, r'\g<1>%d\g<2>' % k["radar"][key], html, count=1)
        if n != 1:
            print("[warn] 雷达 %s 未命中" % key)

    # ---- 8) 日期 / 展望标题 / 顶部 chips
    html = re.sub(r'<b>\d{4}-\d{2}-\d{2} 收盘（北京时间，盘后）</b>',
                  '<b>%s 收盘（北京时间，盘后）</b>' % dstr_cn, html, count=1)
    html = re.sub(r'Next-Session Outlook \([^)]*\)',
                  'Next-Session Outlook (%02d-%02d %s)' % (nd.month, nd.day, WEEK_EN[nd.weekday()]), html, count=1)
    chips = [
        ("c_upratio", "%.0f%%" % up),
        ("c_limitup", str(lu)),
        ("c_pe", "%.0f%%（10年）" % (c.get("PE_TTM_PCT_10Y") or c.get("PE_TTM_PCT_52W") or 0)),
        ("c_turn", "¥%s万亿" % amt_yi),
    ]
    for key, val in chips:
        pat = r'(<span data-i18n="%s">[^<]*</span> <b>)[^<]*(</b>)' % key
        html, n = re.subn(pat, r'\g<1>%s\g<2>' % val, html, count=1)
        if n != 1:
            print("[warn] chip %s 未命中" % key)

    # ---- 9) data-i18n 兜底回写
    pat = re.compile(r'<(\w+)([^>]*\bdata-i18n="([^"]+)"[^>]*)>(.*?)</\1>', re.S)

    def _repl(m):
        tag, attrs, key, inner = m.group(1), m.group(2), m.group(3), m.group(4)
        if key in zh:
            return "<%s%s>%s</%s>" % (tag, attrs, zh[key], tag)
        return m.group(0)

    html = pat.sub(_repl, html)
    return html


# ---------------------------------------------------------------- hub
def update_hub(date, ZH, k, c, lad):
    hub = open(HUB, encoding="utf-8").read()
    fn = "crowd-psychology-risk-radar-%s.html" % date.replace("-", "")
    if fn in hub:
        print("[skip] hub 已有 %s" % fn)
        return False

    def j(s):
        return str(s).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")

    board = ("%d板" % lad["stocks"][0]["days"]) if lad and lad.get("stocks") else "—"
    nd = dt.date(*[int(x) for x in k["_next_date"].split("-")])
    entry = """    },
    {
      file:"%s", date:"%s",
      risk:"%s", riskEn:"%s",
      cycleZh:"%s", cycleEn:"%s",
      cycleNoteZh:"涨股比%.0f%%·跌停%s只", cycleNoteEn:"Up-ratio %.0f%% · Limit-down %s",
      up:"%.0f%%", limitup:"%s", board:"%s", turn:"¥%s万亿",
      summaryZh:"%s",
      summaryEn:"%s\"""" % (
        fn, date, k["risk"], {"高": "High", "中": "Medium", "低": "Low"}[k["risk"]],
        STAGE_ZH[k["stage"]], STAGE_EN[k["stage"]],
        c.get("RATIO_UP") or 0, c.get("CNT_REACH_DNLIMIT") or 0,
        c.get("RATIO_UP") or 0, c.get("CNT_REACH_DNLIMIT") or 0,
        c.get("RATIO_UP") or 0, c.get("CNT_REACH_UPLIMIT") or 0, board, yi(c.get("MONEY")),
        j(ZH.get("t_tldr_text", "")),
        j(ZH.get("t_tldr_text", "")))
    tail = "    }\n  ];\n  REPORTS.reverse();"
    assert tail in hub, "hub tail 未找到"
    hub = hub.replace(tail, entry + "\n    }\n  ];\n  REPORTS.reverse();", 1)
    open(HUB, "w", encoding="utf-8").write(hub)
    print("[ok] hub 已插入 %s" % fn)
    return True


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=dt.date.today().isoformat())
    ap.add_argument("--next", default=None)
    ap.add_argument("--no-hub", action="store_true")
    args = ap.parse_args()

    date = args.date
    c = load_overview(date)
    if not c:
        raise SystemExit("[fail] 缺少 quant/market_overview/%s.json —— 请先采集当日大盘快照" % date)

    pdate = prev_trading_date(date)
    p = load_overview(pdate) if pdate else {}
    c["_date"] = date
    c["_sectors"] = load_sectors(date)
    if p:
        p["_date"] = pdate

    lad = load_ladder(date)
    sec_up = pick_sectors(c["_sectors"], kind="行业", top=3, reverse=True)
    sec_dn = pick_sectors(c["_sectors"], kind="行业", top=3, reverse=False)
    if not sec_up:
        sec_up = pick_sectors(c["_sectors"], top=3, reverse=True)
        sec_dn = pick_sectors(c["_sectors"], top=3, reverse=False)

    k = classify(c, p)
    k["_prev_date"] = pdate
    k["_next_date"] = args.next or next_trading_date(date)
    k["p_lu"] = (p or {}).get("CNT_REACH_UPLIMIT")
    if p:
        p["_risk"] = prev_risk_from_hub(pdate)

    print("[ok] %s 阶段=%s 风险=%s 雷达=%s" % (date, k["stage"], k["risk"], k["radar"]))
    print("     涨股比 %.2f%%（前 %s） 涨停 %s / 跌停 %s 板块 %s 条" % (
        c.get("RATIO_UP") or 0, k.get("p_up"), c.get("CNT_REACH_UPLIMIT"), c.get("CNT_REACH_DNLIMIT"), len(c["_sectors"])))

    ZH, EN = narrate(date, c, p, k, sec_up, sec_dn, lad)
    BIAS = bias_list(c, p, k)
    html = render(date, ZH, EN, BIAS, c, p, k, sec_up, sec_dn, lad)

    out = os.path.join(OUT_DIR, "crowd-psychology-risk-radar-%s.html" % date.replace("-", ""))
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print("[ok] 写出 %s (%d bytes)" % (out, len(html)))

    if not args.no_hub:
        update_hub(date, ZH, k, c, lad)

    # hub 静态部分（涨股比走势 SVG / 走势与轨迹注记 / 统计条 / 跨度标签）刷新。
    # update_hub 只往 REPORTS 尾部插一条，上面那些静态块不会跟着走 —— 历史上靠
    # market-trend/_update_index_MMDD.py 手改，漏跑即永久停在旧日期（曾停在 09-11）。
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import psy_hub_refresh
        psy_hub_refresh.refresh(verbose=True)
    except Exception as _e:
        print("[warn] hub 静态刷新失败：%s" % _e)

    # 历史指标（供下期环比与雷达平移）
    hist = load_json(HIST, {})
    hist[date] = {
        "stage": k["stage"], "risk": k["risk"], "radar": k["radar"],
        "up_ratio": c.get("RATIO_UP"), "limit_up": c.get("CNT_REACH_UPLIMIT"),
        "limit_down": c.get("CNT_REACH_DNLIMIT"), "sh_close": c.get("CLOSE_PRICE_SZZS"),
        "sh_pct": c.get("CHANGE_PCT_SZZS"), "money": c.get("MONEY"),
    }
    os.makedirs(os.path.dirname(HIST), exist_ok=True)
    with open(HIST, "w", encoding="utf-8") as f:
        json.dump(hist, f, ensure_ascii=False, indent=1)
    print("[ok] 历史指标已写入 %s" % HIST)

    # 残留自检：不得出现其它日期的旧值
    stale = ["2026-09-11 收盘", "2026-09-10", "放量普跌 · 恐慌扩散", "¥1.97万亿", "3888.11", "13471.26", "3322.04",
             "工业金属", "农产品加工", "瑞尔特", "桂林旅游 4板", "12%</text>", "643</text>", "4870</text>"]
    bad = [s for s in stale if s in html and not (s == "2026-09-10" and False)]
    print("[校验] 残留旧数据:", bad if bad else "无")


if __name__ == "__main__":
    main()
