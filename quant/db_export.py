# -*- coding: utf-8 -*-
"""
把 SQLite 主库导出成静态页面可直接加载的轻量 JSON。
------------------------------------------------
列式存储（fields + rows 二维数组）+ 高重复列字典编码，体积约为行式 JSON 的 1/4。
明细表按「年-月」分片，页面按所选日期范围只加载需要的分片。

用法：python quant/db_export.py
"""
import os
import sys
import json
import sqlite3
from collections import defaultdict, OrderedDict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db

ROOT = db.ROOT
OUT = os.path.join(ROOT, "web", "data")
os.makedirs(OUT, exist_ok=True)

# key -> (label, table, [(col, 中文标签, type)], 主排序列)
MODULES = OrderedDict([
    ("exec", ("高管增减持", "exec_change", [
        ("date", "日期", "date"), ("declare", "公告日", "str"), ("code", "代码", "str"),
        ("name", "名称", "str"), ("manager", "高管", "str"), ("dir", "方向", "str"),
        ("shares", "变动股数", "num"), ("price", "均价", "num"), ("amount", "变动金额", "num"),
        ("sw1", "一级行业", "str"), ("sw2", "二级行业", "str"),
        ("chgPct", "当日涨跌%", "num"), ("priceNow", "现价", "num"),
        ("turnover", "换手率%", "num"), ("report", "报告期", "str"),
    ], "date DESC, amount DESC")),
    ("block", ("大宗交易", "block_trade", [
        ("date", "日期", "date"), ("code", "代码", "str"), ("name", "名称", "str"),
        ("tradePrice", "成交价", "num"), ("price", "当日收盘", "num"),
        ("changePercent", "涨跌幅%", "num"), ("value", "成交额", "num"),
        ("ratio", "占比%", "num"), ("discount", "折溢价%", "num"),
        ("type", "类型", "str"), ("buyer", "买方营业部", "str"), ("seller", "卖方营业部", "str"),
    ], "date DESC, value DESC")),
    ("lhb", ("龙虎榜", "lhb", [
        ("date", "日期", "date"), ("code", "代码", "str"), ("name", "名称", "str"),
        ("changePct", "涨跌幅%", "num"), ("netBuy", "净买入", "num"),
        ("buy", "买入额", "num"), ("sell", "卖出额", "num"),
        ("reason", "上榜原因", "str"), ("sw1", "一级行业", "str"), ("sw2", "二级行业", "str"),
        ("ipo", "次新股", "num"), ("tags", "游资标签", "str"),
    ], "date DESC, netBuy DESC")),
    ("seat", ("龙虎榜席位", "lhb_seat", [
        ("date", "日期", "date"), ("code", "代码", "str"), ("side", "方向", "str"),
        ("idx", "序号", "num"), ("seat", "席位", "str"),
        ("buy", "买入额", "num"), ("sell", "卖出额", "num"), ("tag", "标签", "str"),
    ], "date DESC, code, side, idx")),
    ("sector", ("板块强度", "sector", [
        ("date", "日期", "date"), ("name", "板块", "str"), ("kind", "类型", "str"),
        ("pctVal", "涨跌幅%", "num"), ("totalVal", "总成交额", "num"),
        ("mainVal", "主力净流入", "num"), ("retailVal", "散户净流入", "num"),
        ("darkVal", "暗盘资金", "num"), ("strengthVal", "板块强度", "num"),
        ("behavior", "主力行为", "str"), ("leader", "领涨股", "str"),
    ], "date DESC, strengthVal DESC")),
    ("limitup", ("连板梯队", "limitup", [
        ("date", "日期", "date"), ("code", "代码", "str"), ("name", "名称", "str"),
        ("days", "连板数", "num"),
    ], "date DESC, days DESC")),
    ("hot", ("热门板块", "board_hot", [
        ("date", "日期", "date"), ("rank", "排名", "num"), ("name", "板块", "str"),
        ("zdf", "涨跌幅%", "num"), ("zxj", "最新价", "num"), ("rankdelta", "排名变动", "num"),
    ], "date DESC, rank")),
    ("news", ("市场快讯", "news", [
        ("date", "日期", "date"), ("source", "来源", "str"),
        ("title", "标题", "str"), ("impact", "影响", "str"),
    ], "date DESC, id")),
])

# 大盘指标中文标签（未列出的用原名）
MLAB = {
    "updown.RATIO_UP": "涨股比%", "updown.RATIO_DOWN": "跌股比%",
    "updown.CNT_RED": "上涨家数", "updown.CNT_GREEN": "下跌家数",
    "updown.CNT_ZERO": "平盘家数", "updown.CNT_TOTAL": "总数",
    "updown.CNT_REACH_UPLIMIT": "涨停数", "updown.CNT_REACH_DNLIMIT": "跌停数",
    "updown.CNT_HIGH20": "创20日新高", "updown.CNT_LOW20": "创20日新低",
    "updown.CNT_HIGH60": "创60日新高", "updown.CNT_LOW60": "创60日新低",
    "daily_trade.MONEY": "成交额(亿)", "daily_trade.MONEY_10DAVG": "10日均额",
    "daily_trade.MONEY_10DAVG_RATIO": "额/10日均%",
    "daily_trade.MONEY_20DAVG_RATIO": "额/20日均%",
    "daily_trade.CHANGE_PCT_SZZS": "上证涨跌%", "daily_trade.CHANGE_PCT_SZCZ": "深成涨跌%",
    "daily_trade.CHANGE_PCT_CYBZ": "创业板涨跌%",
    "daily_trade.CLOSE_PRICE_SZZS": "上证收盘", "daily_trade.CLOSE_PRICE_SZCZ": "深成收盘",
    "daily_trade.CLOSE_PRICE_CYBZ": "创业板收盘",
    "technical.MA_5": "MA5", "technical.MA_10": "MA10", "technical.MA_20": "MA20",
    "technical.MA_60": "MA60", "technical.MA_120": "MA120", "technical.MA_250": "MA250",
    "technical.DIF": "DIF", "technical.DEA": "DEA", "technical.MACD": "MACD",
    "technical.KDJ_K": "KDJ-K", "technical.KDJ_D": "KDJ-D", "technical.KDJ_J": "KDJ-J",
    "technical.RSI_6": "RSI6", "technical.RSI_12": "RSI12", "technical.RSI_24": "RSI24",
    "technical.BOLL_UPPER": "BOLL上轨", "technical.BOLL_MID": "BOLL中轨",
    "technical.BOLL_LOWER": "BOLL下轨",
    "valuation.PE_TTM": "PE(TTM)", "valuation.PE_TTM_PCT_10Y": "PE十年分位%",
    "valuation.PE_TTM_PCT_5Y": "PE五年分位%", "valuation.PE_TTM_PCT_3Y": "PE三年分位%",
    "valuation.PB_LF": "PB(LF)", "valuation.DIV_TTM": "股息率%",
    "valuation.PS_TTM": "PS(TTM)", "valuation.PCF_TTM": "PCF(TTM)",
    "summary.SENTIMENT_SCORE": "情绪分", "summary.STOCK_WIDTH_SCORE": "个股广度分",
    "summary.SECTOR_WIDTH_SCORE": "板块广度分", "summary.TECHNICAL_SCORE": "技术分",
    "summary.VALUATION_SCORE": "估值分", "summary.VOLUME_ENERGE_SCORE": "量能分",
    "summary.TREND_SHORT_DIRECTION_SCORE": "短趋势方向分",
    "summary.TREND_LONG_DIRECTION_SCORE": "长趋势方向分",
    "summary.TREND_SHORT_STRENGTH_SCORE": "短趋势强度分",
    "summary.TREND_LONG_STRENGTH_SCORE": "长趋势强度分",
    "summary.STYLE_ROTATION_SCORE": "风格轮动分", "summary.CAP_ROTATION_SCORE": "市值轮动分",
    "summary.SECTOR_ROTATION_SCORE": "板块轮动分",
    "summary.ADJ_SCORE": "综合分(修正)", "summary.RAW_SCORE": "综合分(原始)",
}
# 大盘概览默认展示列（其余可在页面勾选）
MARKET_DEFAULT = [
    "updown.RATIO_UP", "updown.CNT_REACH_UPLIMIT", "updown.CNT_REACH_DNLIMIT",
    "daily_trade.MONEY", "daily_trade.MONEY_10DAVG_RATIO",
    "daily_trade.CHANGE_PCT_SZZS", "daily_trade.CHANGE_PCT_SZCZ",
    "daily_trade.CHANGE_PCT_CYBZ", "technical.MA_20", "technical.MA_60",
    "valuation.PE_TTM", "valuation.PE_TTM_PCT_10Y",
    "summary.SENTIMENT_SCORE", "summary.ADJ_SCORE",
]


# 字典编码阈值：唯一值 / 总行数 低于此值才编码，否则反而变大
DICT_RATIO = 0.5


def build_module(con, key, label, table, cols, order):
    names = [c[0] for c in cols]
    sql = "SELECT %s FROM %s ORDER BY %s" % (",".join(names), table, order)
    rows = con.execute(sql).fetchall()
    if not rows:
        return None

    # 按年月分片
    buckets = defaultdict(list)
    for r in rows:
        ym = (r[0] or "")[:7]
        buckets[ym].append(r)

    shards = []
    total_bytes = 0
    for ym in sorted(buckets):
        sub = buckets[ym]
        encoded, fields = _encode(cols, sub)
        payload = {"ym": ym, "rows": sub.__len__(), "fields": fields, "data": encoded}
        fp = os.path.join(OUT, "%s_%s.json" % (key, ym))
        with open(fp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
        sz = os.path.getsize(fp)
        total_bytes += sz
        shards.append({
            "ym": ym, "file": "data/%s_%s.json" % (key, ym),
            "rows": len(sub), "size": sz,
            "dates": [min(x[0] for x in sub), max(x[0] for x in sub)],
        })
    return {"key": key, "label": label, "shards": shards, "rows": len(rows),
            "size": total_bytes, "dates": _range(con, table)}


def _encode(cols, rows):
    """列式 + 字典编码"""
    n = len(rows)
    fields = []
    data = []
    for i, (col, label, typ) in enumerate(cols):
        vals = [r[i] for r in rows]
        entry = {"n": col, "l": label, "t": typ}
        if typ == "str":
            uniq = sorted({v for v in vals if v is not None}, key=str)
            if uniq and len(uniq) / n < DICT_RATIO:
                idx = {v: k for k, v in enumerate(uniq)}
                entry["d"] = uniq
                data.append([None if v is None else idx[v] for v in vals])
                fields.append(entry)
                continue
        data.append([None if v is None else v for v in vals])
        fields.append(entry)
    return data, fields


def _range(con, table):
    try:
        a, b = con.execute("SELECT MIN(date),MAX(date) FROM %s" % table).fetchone()
        d = con.execute("SELECT COUNT(DISTINCT date) FROM %s" % table).fetchone()[0]
        return [a, b, d]
    except Exception:
        return None


def build_market(con):
    """大盘概览：纵表 pivot 成宽表，按天输出"""
    rows = con.execute(
        "SELECT date, listCode, field, value FROM market_metric ORDER BY date").fetchall()
    if not rows:
        return None
    by_date = defaultdict(dict)
    for d, lc, fld, v in rows:
        key = lc.replace("market_statis_", "")
        by_date[d]["%s.%s" % (key, fld)] = v
    dates = sorted(by_date)
    allf = []
    seen = set()
    for d in dates:
        for k in by_date[d]:
            if k not in seen:
                seen.add(k)
                allf.append(k)
    allf.sort()
    # 列式：每个字段一列，列内按 dates 顺序
    data = [list(dates)] + [[by_date[d].get(k) for d in dates] for k in allf]
    payload = {
        "ym": "all", "rows": len(dates),
        "fields": [{"n": "date", "l": "日期", "t": "date"}] +
                  [{"n": k, "l": MLAB.get(k, k), "t": "num"} for k in allf],
        "data": data,
    }
    fp = os.path.join(OUT, "market_all.json")
    with open(fp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
    groups = OrderedDict()
    for k in allf:
        g = k.split(".")[0]
        groups.setdefault(g, []).append({"n": k, "l": MLAB.get(k, k)})
    GN = {"updown": "涨跌分布", "daily_trade": "成交与指数", "technical": "技术指标",
          "valuation": "估值", "summary": "综合评分", "rotation": "轮动",
          "interval_trade": "区间涨跌", "margin_chg": "两融"}
    return {"key": "market", "label": "大盘概览", "rows": len(dates),
            "default": MARKET_DEFAULT,
            "groups": [{"n": g, "l": GN.get(g, g), "fields": v} for g, v in groups.items()],
            "size": os.path.getsize(fp), "dates": [dates[0], dates[-1], len(dates)],
            "shards": [{"ym": "all", "file": "data/market_all.json", "rows": len(dates),
                        "size": os.path.getsize(fp), "dates": [dates[0], dates[-1]]}]}


def main():
    con = db.connect()
    manifest = {"generated": "", "modules": []}
    import datetime
    manifest["generated"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    total = 0
    for key, (label, table, cols, order) in MODULES.items():
        m = build_module(con, key, label, table, cols, order)
        if m:
            manifest["modules"].append(m)
            total += m["size"]
            print("[export] %-6s %6d 行  %6.1f KB  %s 分片" %
                  (key, m["rows"], m["size"] / 1024, len(m["shards"])))
    mm = build_market(con)
    if mm:
        manifest["modules"].append(mm)
        total += mm["size"]
        print("[export] %-6s %6d 行  %6.1f KB" % ("market", mm["rows"], mm["size"] / 1024))
    mfp = os.path.join(OUT, "manifest.json")
    with open(mfp, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, separators=(",", ":"))
    print("[export] manifest -> %s | 合计 %.1f KB" % (mfp, total / 1024))
    con.close()


if __name__ == "__main__":
    main()
