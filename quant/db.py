# -*- coding: utf-8 -*-
"""
A股分析中心 · 本地 SQLite 主库
------------------------------------------------
唯一数据源：所有模块的明细数据按日增量写入 quant/db/stocks.db，
再由 db_export.py 导出轻量 JSON 供静态页面查询。

用法：
    python quant/db.py init            建表
    python quant/db.py import          全量导入（幂等，INSERT OR REPLACE）
    python quant/db.py import --date 2026-09-07   只导入某天
    python quant/db.py stats           查看各表行数与日期覆盖
"""
import os
import re
import sys
import glob
import json
import sqlite3

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(ROOT, "quant", "db", "stocks.db")
Q = lambda *p: os.path.join(ROOT, "quant", *p)

SCHEMA = """
PRAGMA journal_mode=WAL;

-- 高管增减持（逐笔）
CREATE TABLE IF NOT EXISTS exec_change (
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  date      TEXT NOT NULL,
  declare   TEXT,
  report    TEXT,
  code      TEXT NOT NULL,
  name      TEXT,
  manager   TEXT,
  shares    REAL,
  price     REAL,
  amount    REAL,
  dir       TEXT,
  sw1       TEXT,
  sw2       TEXT,
  chgPct    REAL,
  priceNow  REAL,
  turnover  REAL,
  UNIQUE(date, code, manager, shares, declare)
);
CREATE INDEX IF NOT EXISTS ix_exec_date ON exec_change(date);
CREATE INDEX IF NOT EXISTS ix_exec_code ON exec_change(code);

-- 大宗交易（逐笔）
CREATE TABLE IF NOT EXISTS block_trade (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  date          TEXT NOT NULL,
  code          TEXT NOT NULL,
  name          TEXT,
  tradePrice    REAL,
  value         REAL,
  ratio         REAL,
  discount      REAL,
  type          TEXT,
  buyer         TEXT,
  seller        TEXT,
  price         REAL,
  changePercent REAL,
  UNIQUE(date, code, tradePrice, value, buyer, seller)
);
CREATE INDEX IF NOT EXISTS ix_block_date ON block_trade(date);
CREATE INDEX IF NOT EXISTS ix_block_code ON block_trade(code);

-- 龙虎榜（每日每股一行，行业/原因来自富集数据）
CREATE TABLE IF NOT EXISTS lhb (
  date      TEXT NOT NULL,
  code      TEXT NOT NULL,
  name      TEXT,
  changePct REAL,
  netBuy    REAL,
  buy       REAL,
  sell      REAL,
  reason    TEXT,
  sw1       TEXT,
  sw1Chg    REAL,
  sw2       TEXT,
  sw2Chg    REAL,
  ipo       INTEGER,
  tags      TEXT,
  PRIMARY KEY(date, code)
);
CREATE INDEX IF NOT EXISTS ix_lhb_code ON lhb(code);

-- 龙虎榜席位明细
CREATE TABLE IF NOT EXISTS lhb_seat (
  id    INTEGER PRIMARY KEY AUTOINCREMENT,
  date  TEXT NOT NULL,
  code  TEXT NOT NULL,
  side  TEXT,
  idx   INTEGER,
  seat  TEXT,
  buy   REAL,
  sell  REAL,
  tag   TEXT,
  UNIQUE(date, code, side, idx)
);

-- 板块强度（行业 + 概念）
CREATE TABLE IF NOT EXISTS sector (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  date         TEXT NOT NULL,
  name         TEXT NOT NULL,
  kind         TEXT,
  pctVal       REAL,
  totalVal     REAL,
  mainVal      REAL,
  retailVal    REAL,
  darkVal      REAL,
  darkUp       INTEGER,
  strengthVal  REAL,
  behavior     TEXT,
  behaviorRank INTEGER,
  leader       TEXT,
  UNIQUE(date, name, kind)
);
CREATE INDEX IF NOT EXISTS ix_sector_name ON sector(name);

-- 大盘概览（纵表：一行一指标，字段增删无需改表）
CREATE TABLE IF NOT EXISTS market_metric (
  date     TEXT NOT NULL,
  listCode TEXT NOT NULL,
  field    TEXT NOT NULL,
  value    TEXT,
  PRIMARY KEY(date, listCode, field)
);

-- 连板梯队
CREATE TABLE IF NOT EXISTS limitup (
  date TEXT NOT NULL,
  code TEXT NOT NULL,
  name TEXT,
  days INTEGER,
  PRIMARY KEY(date, code)
);
CREATE INDEX IF NOT EXISTS ix_limitup_days ON limitup(days);

-- 热门板块榜
CREATE TABLE IF NOT EXISTS board_hot (
  date      TEXT NOT NULL,
  symbol    TEXT NOT NULL,
  rank      INTEGER,
  rankdelta INTEGER,
  name      TEXT,
  zdf       REAL,
  zxj       REAL,
  PRIMARY KEY(date, symbol)
);

-- 市场快讯
CREATE TABLE IF NOT EXISTS news (
  id     INTEGER PRIMARY KEY AUTOINCREMENT,
  date   TEXT NOT NULL,
  source TEXT,
  title  TEXT,
  impact TEXT,
  UNIQUE(date, title)
);
"""


def connect():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    return sqlite3.connect(DB_PATH)


def init():
    con = connect()
    con.executescript(SCHEMA)
    con.commit()
    con.close()
    print("[db] init ok ->", DB_PATH)


def _f(v):
    """统一数值转换：None/空串 -> None"""
    if v is None or v == "" or v == "-":
        return None
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, (int, float)):
        return v
    try:
        return float(v)
    except Exception:
        return None


def _s(v):
    return None if v is None else str(v)


def _dates(folder, pattern="*.json"):
    """从目录里列出所有日期（文件名去扩展）"""
    out = []
    for f in sorted(glob.glob(os.path.join(folder, pattern))):
        out.append(os.path.splitext(os.path.basename(f))[0])
    return out


# ---------------------------------------------------------------- importers
def imp_exec(con, only=None):
    n = 0
    for f in sorted(glob.glob(Q("exec_chg", "*.json"))):
        D = os.path.splitext(os.path.basename(f))[0]
        if only and D != only:
            continue
        d = json.load(open(f, encoding="utf-8"))
        for r in d.get("records", []):
            con.execute(
                "INSERT OR REPLACE INTO exec_change "
                "(date,declare,report,code,name,manager,shares,price,amount,dir,sw1,sw2,chgPct,priceNow,turnover) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (D, _s(r.get("declare")), _s(r.get("report")), r.get("code"),
                 r.get("name"), r.get("manager"), _f(r.get("shares")),
                 _f(r.get("price")), _f(r.get("amount")), r.get("dir"),
                 r.get("sw1"), r.get("sw2"), _f(r.get("chgPct")),
                 _f(r.get("priceNow")), _f(r.get("turnover"))))
            n += 1
    return n


def imp_block(con, only=None):
    n = 0
    for f in sorted(glob.glob(Q("block_chg", "*.json"))):
        d = json.load(open(f, encoding="utf-8"))
        D = d.get("date") or os.path.splitext(os.path.basename(f))[0]
        if only and D != only:
            continue
        for r in d.get("rows", []):
            con.execute(
                "INSERT OR REPLACE INTO block_trade "
                "(date,code,name,tradePrice,value,ratio,discount,type,buyer,seller,price,changePercent) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (D, r.get("code"), r.get("name"), _f(r.get("tradePrice")),
                 _f(r.get("value")), _f(r.get("ratio")), _f(r.get("discount")),
                 r.get("type"), r.get("buyer"), r.get("seller"),
                 _f(r.get("price")), _f(r.get("changePercent"))))
            n += 1
    return n


def imp_lhb(con, only=None):
    """主榜 + 富集的行业/原因/游资标签；同时落席位明细"""
    n = nseat = 0
    for f in sorted(glob.glob(Q("lhb", "*.json"))):
        D = os.path.splitext(os.path.basename(f))[0]
        if only and D != only:
            continue
        d = json.load(open(f, encoding="utf-8"))
        rows = (d.get("data") or {}).get("all") or []
        # 富集补充
        en = {}
        ep = Q("lhb_enriched_%s.json" % D)
        if os.path.exists(ep):
            en = json.load(open(ep, encoding="utf-8")).get("stocks") or {}
        for r in rows:
            c = r.get("code")
            e = en.get(c) or {}
            con.execute(
                "INSERT OR REPLACE INTO lhb "
                "(date,code,name,changePct,netBuy,buy,sell,reason,sw1,sw1Chg,sw2,sw2Chg,ipo,tags) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (D, c, r.get("name"), _f(r.get("changePct")),
                 _f(r.get("netBuyAmount")), _f(r.get("buyAmount")),
                 _f(r.get("sellAmount")), e.get("reason"), e.get("sw1"),
                 _f(e.get("sw1Chg")), e.get("sw2"), _f(e.get("sw2Chg")),
                 1 if e.get("ipo") else 0, e.get("tags") or ""))
            n += 1
            for side, key in (("buy", "buySeats"), ("sell", "sellSeats")):
                for i, s in enumerate(e.get(key) or []):
                    con.execute(
                        "INSERT OR REPLACE INTO lhb_seat (date,code,side,idx,seat,buy,sell,tag) "
                        "VALUES (?,?,?,?,?,?,?,?)",
                        (D, c, side, i, s.get("name"), _f(s.get("buy")),
                         _f(s.get("sell")), s.get("tag") or ""))
                    nseat += 1
    return n, nseat


def imp_sector(con, only=None):
    n = 0
    for f in sorted(glob.glob(Q("sector_daily", "*.json"))):
        d = json.load(open(f, encoding="utf-8"))
        D = d.get("date") or os.path.splitext(os.path.basename(f))[0]
        if only and D != only:
            continue
        for r in d.get("records", []):
            con.execute(
                "INSERT OR REPLACE INTO sector "
                "(date,name,kind,pctVal,totalVal,mainVal,retailVal,darkVal,darkUp,strengthVal,behavior,behaviorRank,leader) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (D, r.get("name"), r.get("kind"), _f(r.get("pctVal")),
                 _f(r.get("totalVal")), _f(r.get("mainVal")),
                 _f(r.get("retailVal")), _f(r.get("darkVal")),
                 1 if r.get("darkUp") else 0, _f(r.get("strengthVal")),
                 r.get("behavior"), _f(r.get("behaviorRank")), r.get("leader")))
            n += 1
    return n


def imp_market(con, only=None):
    n = 0
    for f in sorted(glob.glob(Q("market_overview", "*.json"))):
        d = json.load(open(f, encoding="utf-8"))
        for e in d.get("data", []):
            D = e.get("date") or os.path.splitext(os.path.basename(f))[0]
            if only and D != only:
                continue
            lc = e.get("listCode")
            for k, v in (e.get("row") or {}).items():
                con.execute(
                    "INSERT OR REPLACE INTO market_metric (date,listCode,field,value) VALUES (?,?,?,?)",
                    (D, lc, k, _s(v)))
                n += 1
    return n


def imp_limitup(con, only=None):
    n = 0
    for f in sorted(glob.glob(Q("limitup", "*.json"))):
        d = json.load(open(f, encoding="utf-8"))
        D = (d.get("data") or {}).get("date") or os.path.splitext(os.path.basename(f))[0]
        if only and D != only:
            continue
        for s in (d.get("data") or {}).get("stocks", []):
            con.execute(
                "INSERT OR REPLACE INTO limitup (date,code,name,days) VALUES (?,?,?,?)",
                (D, s.get("code"), s.get("name"), _f(s.get("LimitUpDays"))))
            n += 1
    return n


def imp_hot(con, only=None):
    n = 0
    for f in sorted(glob.glob(Q("board_hot", "*.json"))):
        d = json.load(open(f, encoding="utf-8"))
        dt = ((d.get("data") or {}).get("rankTime") or "")[:10]
        D = dt or os.path.splitext(os.path.basename(f))[0]
        if only and D != only:
            continue
        for r in (d.get("data") or {}).get("rankResult", []):
            con.execute(
                "INSERT OR REPLACE INTO board_hot (date,symbol,rank,rankdelta,name,zdf,zxj) "
                "VALUES (?,?,?,?,?,?,?)",
                (D, r.get("symbol"), _f(r.get("rank")), _f(r.get("rankdelta")),
                 r.get("name"), _f(r.get("zdf")), _f(r.get("zxj"))))
            n += 1
    return n


def imp_news(con, only=None):
    n = 0
    p = Q("news.json")
    if not os.path.exists(p):
        return 0
    d = json.load(open(p, encoding="utf-8"))
    for D, items in d.items():
        if only and D != only:
            continue
        for it in items:
            con.execute(
                "INSERT OR REPLACE INTO news (date,source,title,impact) VALUES (?,?,?,?)",
                (D, it.get("source"), it.get("title"), it.get("impact") or ""))
            n += 1
    return n


IMPORTERS = [
    ("exec_change", imp_exec),
    ("block_trade", imp_block),
    ("lhb", imp_lhb),
    ("sector", imp_sector),
    ("market_metric", imp_market),
    ("limitup", imp_limitup),
    ("board_hot", imp_hot),
    ("news", imp_news),
]


def do_import(only=None):
    init()
    con = connect()
    for name, fn in IMPORTERS:
        r = fn(con, only)
        con.commit()
        if isinstance(r, tuple):
            print("[import] %-14s +%s" % (name, " / +".join(str(x) for x in r)))
        else:
            print("[import] %-14s +%d" % (name, r))
    con.close()
    print("[db] import done", "(only %s)" % only if only else "")


def stats():
    con = connect()
    print("%-16s %10s  %s" % ("TABLE", "ROWS", "DATE RANGE"))
    print("-" * 60)
    for (t,) in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"):
        n = con.execute("SELECT COUNT(*) FROM %s" % t).fetchone()[0]
        try:
            a, b = con.execute("SELECT MIN(date),MAX(date) FROM %s" % t).fetchone()
            days = con.execute("SELECT COUNT(DISTINCT date) FROM %s" % t).fetchone()[0]
            rng = "%s ~ %s (%d 天)" % (a, b, days) if a else "-"
        except Exception:
            rng = "-"
        print("%-16s %10d  %s" % (t, n, rng))
    con.close()


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "stats"
    if cmd == "init":
        init()
    elif cmd == "import":
        d = None
        if "--date" in sys.argv:
            d = sys.argv[sys.argv.index("--date") + 1]
        do_import(d)
    else:
        stats()
