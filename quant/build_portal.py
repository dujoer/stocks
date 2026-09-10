# -*- coding: utf-8 -*-
"""生成 A股分析中心 · 总门户（G:\\ai\\股票\\index.html）。

扫描 3 个子系统的「最新一期」文件，自动写出统一入口，并标注每个子系统的
数据新鲜度（相对今天的天数差），避免主看板/板块/雷达各自为政。

子系统（全站 web/ 分层后）：
  1) 龙虎榜主看板   web/lhb/lhb.html            最新 = max(web/lhb/lhb_YYYY-MM-DD.html)
  2) 板块强度       web/sector/index.html       最新 = max(web/sector/sector-strength-YYYYMMDD.html)
  3) 群体心理风险雷达 web/psychology/index.html  最新 = max(web/psychology/crowd-psychology-risk-radar-YYYYMMDD.html)
  4) 个股调研        web/research/index.html     列出全部调研报告
"""
import os, re, datetime, json
from _nav import selfcontained_nav

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(ROOT, "web")
MT = os.path.join(ROOT, "market-trend")
QUANT = os.path.join(ROOT, "quant")
OUT = os.path.join(ROOT, "index.html")
TODAY = datetime.date.today()

# 根门户置于仓库根目录，统一导航的链接需带 web/ 前缀，主页指向自身
PORTAL_NAV = selfcontained_nav(current_web_dir="", home="index.html", prefix="web/")

def parse_date(s):
    s = s.strip()
    for fmt in ("%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.datetime.strptime(s, fmt).date()
        except Exception:
            pass
    return None

def latest(pattern, directory):
    """返回 (date_obj, filename) 或 (None, None)"""
    best_d, best_f = None, None
    if not os.path.isdir(directory):
        return best_d, best_f
    for fn in os.listdir(directory):
        m = re.match(pattern, fn)
        if not m:
            continue
        d = parse_date(m.group(1))
        if d is None:
            continue
        if best_d is None or d > best_d:
            best_d, best_f = d, fn
    return best_d, best_f

def freshness(d):
    if d is None:
        return "无数据", "stale"
    diff = (TODAY - d).days
    if diff <= 0:
        return "今日", "fresh"
    if diff == 1:
        return "昨日", "fresh"
    if diff <= 3:
        return f"{diff} 天前", "warn"
    return f"{diff} 天前", "stale"

# ---- 扫描各子系统最新日期 ----
lhb_d, lhb_f = latest(r"^lhb_(\d{4}-\d{2}-\d{2})\.html$", os.path.join(WEB, "lhb"))
sec_d, sec_f = latest(r"^sector-strength-(\d{8})\.html$", os.path.join(WEB, "sector"))
psy_d, psy_f = latest(r"^crowd-psychology-risk-radar-(\d{8})\.html$", os.path.join(WEB, "psychology"))
research_d, research_f = latest(r"^research-.*?-(\d{8})\.html$", os.path.join(WEB, "research"))
exec_d, exec_f = latest(r"^(\d{4}-\d{2}-\d{2})\.json$", os.path.join(ROOT, "quant", "exec_chg"))
blk_d, blk_f = latest(r"^(\d{4}-\d{2}-\d{2})\.json$", os.path.join(ROOT, "quant", "block_chg"))

# 个股信号池：读 history.json 取最新一期日期与档位分布
pick_d = None
pick_stat = ""
try:
    _hp = os.path.join(ROOT, "quant", "picks", "history.json")
    if os.path.exists(_hp):
        _h = json.load(open(_hp, encoding="utf-8"))
        if _h:
            pick_d = datetime.date.fromisoformat(_h[-1]["date"])
            _n = _h[-1].get("n", 0)
            pick_stat = f"候选 {_n} 只 ｜ 每日交易计划"
except Exception:
    pick_d = None

# 做T池：读 history.json 取最新一期日期与档位分布
tplus_d = None
tplus_stat = ""
try:
    _tp = os.path.join(ROOT, "quant", "tplus", "history.json")
    if os.path.exists(_tp):
        _th = json.load(open(_tp, encoding="utf-8"))
        if _th:
            tplus_d = datetime.date.fromisoformat(_th[-1]["date"])
            _t = _th[-1]
            tplus_stat = f"A {_t.get('A',0)} ｜ B {_t.get('B',0)} ｜ C {_t.get('C',0)} ｜ 网格 {_t.get('grid',0)}"
except Exception:
    tplus_d = None


# ---- 各模块内联数据快照（让总门户一眼看全所有版块的核心数据，不只是链接列表）----
def _load_json(path):
    try:
        return json.load(open(path, encoding="utf-8"))
    except Exception:
        return None


def stat_lhb():
    """龙虎榜：机构上榜 / 共振 / 胜率（从 web/lhb_YYYY-MM-DD.html 标题与 HTML 抓取）"""
    if not lhb_d or not lhb_f:
        return ""
    p = os.path.join(WEB, lhb_f)
    try:
        h = open(p, encoding="utf-8").read()
    except Exception:
        return ""
    import re as _re
    inst = _re.search(r"共\s*(\d+)\s*只个股上榜机构榜", h)
    res = _re.search(r"共振买入（(\d+)\s*只）", h)
    return (f"机构上榜 <b>{inst.group(1) if inst else '—'}</b> 只 ｜ "
            f"机构+游资共振 <b>{res.group(1) if res else '—'}</b> 只 ｜ "
            f"席位胜率 Top20")


def stat_exec():
    """高管增减持：笔数 / 增持 : 减持 / 覆盖股票"""
    if not exec_d:
        return ""
    p = os.path.join(QUANT, "exec_chg", exec_f)
    d = _load_json(p)
    if not d:
        return ""
    return (f"近 1 月共 <b>{d.get('count', '—')}</b> 条 ｜ "
            f"<span style='color:#b8332a'>增持 {d.get('buyCount', '—')}</span> : "
            f"<span style='color:#1a9e5a'>减持 {d.get('sellCount', '—')}</span> ｜ "
            f"覆盖 <b>{d.get('stockCount', '—')}</b> 只股票")


def stat_block():
    """大宗交易：当日笔数 / 成交额 / 折溢价均值"""
    if not blk_d:
        return ""
    p = os.path.join(QUANT, "block_chg", blk_f)
    d = _load_json(p)
    if not d:
        return ""
    n = d.get('count', 0)
    amt = d.get('totalValue', 0) / 1e8  # 元 → 亿元
    disc = d.get('avgDiscount', 0)
    inst = d.get('instBuyCount', 0)
    return (f"当日 <b>{n}</b> 笔 ｜ 成交额 <b>{amt:.2f}</b> 亿 ｜ "
            f"折溢价均值 <b>{disc:+.2f}%</b> ｜ 机构买入 <b>{inst}</b> 笔")


def stat_sector():
    """板块强度：当日抢筹 / 建仓 / 洗盘 / 出货（从 sector_daily/JSON 的 summary.behavior 拿）"""
    if not sec_d:
        return ""
    snap = sec_d.strftime("%Y-%m-%d")
    p = os.path.join(QUANT, "sector_daily", f"{snap}.json")
    d = _load_json(p)
    if not d:
        return ""
    s = d.get('summary') or {}
    bh = s.get('behavior') or {}
    return (f"板块 <b>{s.get('sectorCount', '—')}</b> 个 ｜ "
            f"抢筹 <b>{bh.get('抢筹', 0)}</b> ｜ 建仓 <b>{bh.get('建仓', 0)}</b> ｜ "
            f"洗盘 <b>{bh.get('洗盘', 0)}</b> ｜ 出货 <b>{bh.get('出货', 0)}</b>")


def stat_psy():
    """群体心理雷达：从最近一期 HTML 抓「标题 + 关键定性词」"""
    if not psy_f:
        return ""
    p = os.path.join(WEB, "psychology", psy_f)
    try:
        h = open(p, encoding="utf-8").read()
    except Exception:
        return ""
    import re as _re
    # 情绪定性（找一个风险/情绪相关词）
    m = _re.search(r"id=\"grade[^\"]*\"[^>]*>([^<]{2,12})<", h) \
        or _re.search(r"<span[^>]*class=\"grade[^\"]*\"[^>]*>([^<]{2,12})<", h)
    title_m = _re.search(r"<title>([^<]+)</title>", h)
    if m:
        return f"情绪定性 <b>{m.group(1).strip()}</b>"
    if title_m:
        return f"近期：<b>{title_m.group(1).strip()[:24]}</b>"
    return ""


def stat_research():
    """个股调研：列出 web/research/ 下所有调研报告数量"""
    d = os.path.join(WEB, "research")
    if not os.path.isdir(d):
        return ""
    n = len([f for f in os.listdir(d) if f.endswith(".html") and f != "index.html"])
    if n == 0:
        return ""
    return f"已生成 <b>{n}</b> 篇个股调研报告（青木科技 / 上海九百等）"


def stat_industry_elite():
    """行业最强榜：行业数 / 标的数"""
    p = os.path.join(WEB, "shareholder", "2026-q2-industry-elite.html")
    if not os.path.exists(p):
        return ""
    import re as _re
    try:
        h = open(p, encoding="utf-8").read()
    except Exception:
        return ""
    sw = _re.search(r"申万\s*<[^>]*>\s*(\d+)\s*<[^>]*>\s*个行业", h)
    if sw:
        return f"申万 <b>{sw.group(1)}</b> 个行业 ｜ 全市场 <b>5544</b> 只全量解析"
    return "全市场 <b>5544</b> 只中报股东解析"


def _box_val(h, label_prefix):
    """从生成页的 stat 卡片抓数值（结构固定为「值在前、标签在后」）：
    <div class="v">N</div><div class="l">标签..."""
    import re as _re
    m = _re.search(r'<div class="v">(\d+)</div><div class="l">' + _re.escape(label_prefix), h)
    return m.group(1) if m else None


def stat_stock_accumulation():
    """股票增持信号扫描：全市场样本 / 有增持信号 / 知名主体加仓"""
    p = os.path.join(WEB, "shareholder", "stock-accumulation.html")
    if not os.path.exists(p):
        return ""
    try:
        h = open(p, encoding="utf-8").read()
    except Exception:
        return ""
    tot = _box_val(h, "全市场样本")
    sig = _box_val(h, "有增持信号")
    kn = _box_val(h, "知名主体加仓")
    if not (tot and sig):
        return ""
    parts = [f"全市场 <b>{tot}</b> 只中报 ｜ 有增持信号 <b>{sig}</b> 只"]
    if kn:
        parts.append(f"其中知名私募 / 牛散加仓 <b>{kn}</b> 只")
    return " ｜ ".join(parts)


def stat_known_health():
    """知名加仓股量价健康度：样本数 + 强/中/弱分布"""
    p = os.path.join(WEB, "shareholder", "known-accumulation-health.html")
    if not os.path.exists(p):
        return ""
    try:
        h = open(p, encoding="utf-8").read()
    except Exception:
        return ""
    n = _box_val(h, "知名加仓样本")
    s = _box_val(h, "健康度·强")
    m = _box_val(h, "健康度·中")
    w = _box_val(h, "健康度·弱")
    if not (n and s):
        return ""
    return (f"知名加仓 <b>{n}</b> 只 ｜ 健康度 "
            f"<span style='color:#1a9e5a'>强 <b>{s}</b></span> ｜ "
            f"中 <b>{m or '—'}</b> ｜ 弱 <b>{w or '—'}</b>")


def stat_sections():
    """版块总览：所有子系统最新日期一览"""
    parts = []
    if lhb_d: parts.append(f"龙虎榜 {lhb_d.strftime('%m-%d')}")
    if sec_d: parts.append(f"板块 {sec_d.strftime('%m-%d')}")
    if exec_d: parts.append(f"增减持 {exec_d.strftime('%m-%d')}")
    if blk_d: parts.append(f"大宗 {blk_d.strftime('%m-%d')}")
    if psy_d: parts.append(f"心理 {psy_d.strftime('%m-%d')}")
    return " ｜ ".join(parts) if parts else ""


STAT = {
    "lhb": stat_lhb(),
    "exec": stat_exec(),
    "block": stat_block(),
    "sec": stat_sector(),
    "psy": stat_psy(),
    "elite": stat_industry_elite(),
    "accum": stat_stock_accumulation(),
    "khealth": stat_known_health(),
    "research": stat_research(),
    "sec2": stat_sections(),
}

lhb_txt, lhb_cls = freshness(lhb_d)
sec_txt, sec_cls = freshness(sec_d)
psy_txt, psy_cls = freshness(psy_d)
research_txt, research_cls = freshness(research_d)
exec_txt, exec_cls = freshness(exec_d)
blk_txt, blk_cls = freshness(blk_d)
pick_txt, pick_cls = freshness(pick_d) if pick_d else ("—", "stale")
STAT["pick"] = pick_stat
tplus_txt, tplus_cls = freshness(tplus_d) if tplus_d else ("—", "stale")
STAT["tplus"] = tplus_stat

def fmt(d):
    return d.strftime("%Y-%m-%d") if d else "—"

def badge(cls, txt):
    return f"<span class='badge {cls}'>{txt}</span>"

# ---- 功能区定义（替代旧的扁平卡片列表）----
# 每个 zone 是「一类功能」，cards 是该功能下的具体页面入口。
# 目的：让总门户一眼看清「每天要看哪几个版块、各版块之间是什么关系」。
ZONES = [
    {
        "ic": "📊", "t": "每日总览（今天该看什么）",
        "desc": "交易日盘后第一眼必看的几个面板：大盘整体 / 异动机构 / 板块资金行为。",
        "rel": "见下方各卡片。",
        "cards": [
            {
                "ic": "🗺️", "t": "每日总览", "href": "web/market/index.html",
                "func": "大盘看板：指数 / 涨跌家数 / 涨停梯队 / 资金流向 / 板块热度 一屏总览。",
                "rel": "📌 龙虎榜主看板 + 板块强度（数据源）。",
                "stat": STAT["lhb"], "date": fmt(lhb_d), "fresh": badge(lhb_cls, lhb_txt),
            },
            {
                "ic": "🐉", "t": "龙虎榜主看板", "href": "web/lhb/lhb.html",
                "func": "异动个股 / 机构榜 / 游资席位胜率 / 机构+游资共振 信号。",
                "rel": "→ 游资席位（web/lhb/lhb.html #yyb） → 牛人追踪·游资（web/shareholder/tracker.html）。",
                "stat": STAT["lhb"], "date": fmt(lhb_d), "fresh": badge(lhb_cls, lhb_txt),
            },
            {
                "ic": "🔥", "t": "板块强度", "href": "web/sector/index.html",
                "func": "行业 / 概念板块的当日资金强度 + 主力行为（抢筹/建仓/洗盘/出货）+ 多日趋势 + 估值分位。",
                "rel": "→ 行业最强榜（按行业筛最强股东） → 牛人追踪（按板块筛持仓）。",
                "stat": STAT["sec"], "date": fmt(sec_d), "fresh": badge(sec_cls, sec_txt),
            },
        ],
    },
    {
        "ic": "💰", "t": "资金动向（谁在买 / 卖）",
        "desc": "看大资金与内部人的调仓动作——董监高自买自卖、大宗交易折溢价。",
        "rel": "高管增减持 + 大宗交易 互补看：内部人异动 + 大额协议转让。",
        "cards": [
            {
                "ic": "💼", "t": "高管增减持（董监高）", "href": "web/exec/index.html",
                "func": "全市场董监高持股变动：增持/减持明细与金额、申万行业分布、个股聚合净额。",
                "rel": "→ 玩家图谱（共现主体交叉标注） → 数据中心（翻历史）。",
                "stat": STAT["exec"], "date": fmt(exec_d), "fresh": badge(exec_cls, exec_txt),
            },
            {
                "ic": "🧾", "t": "大宗交易", "href": "web/block/archive.html",
                "func": "全市场大宗交易逐笔：折溢价、成交额、买卖营业部、机构席位动向；每日归档。",
                "rel": "→ 高管增减持（大宗折价可能配合内部人出货） → 数据中心。",
                "stat": STAT["block"], "date": fmt(blk_d), "fresh": badge(blk_cls, blk_txt),
            },
        ],
    },
    {
        "ic": "🧠", "t": "市场情绪",
        "desc": "市场在想什么——情绪周期、认知偏差、风险分层。",
        "rel": "与板块强度互补：情绪是定性、强度是定量。",
        "cards": [
            {
                "ic": "🧠", "t": "群体心理风险雷达", "href": "web/psychology/index.html",
                "func": "情绪周期 / 认知偏差热力 / 风险分层，每日单篇 + 跨日趋势索引 + 六维雷达图。",
                "rel": "→ 龙虎榜（情绪外化为异动） → 板块强度（情绪外化为资金方向）。",
                "stat": STAT["psy"], "date": fmt(psy_d), "fresh": badge(psy_cls, psy_txt),
            },
        ],
    },
    {
        "ic": "👑", "t": "牛人与股东（谁在持仓）",
        "desc": "看全市场牛散 / 私募 / 公募 / 游资席位的当前持仓与增减持动向。",
        "rel": "牛人追踪 是索引入口；下方四张表是中报专题（定期刷新）。",
        "cards": [
            {
                "ic": "🎯", "t": "牛人追踪（索引）", "href": "web/shareholder/tracker.html",
                "func": "全市场 5500+ 只中报十大股东 → 牛散/私募/公募 索引 + 龙虎榜营业部 → 游资席位；含 Q2↔Q1 增减持信号，可关注代号、可按行业筛选。",
                "rel": "← 行业最强榜（行业版） ← 玩家图谱（精选版） ← 增持扫描（信号版） ← 健康度过滤（技术版）。",
                "stat": "牛散 2640 ｜ 私募 939 ｜ 公募 867 ｜ 游资 833",
                "date": "2026-Q2", "fresh": badge("warn", "季频"),
            },
            {
                "ic": "🏆", "t": "行业最强榜（全市场）", "href": "web/shareholder/2026-q2-industry-elite.html",
                "func": "申万 31 个行业各自最强的 自然人 / 私募 / 公募 各 20 名 + 资金估值四象限 + 胜率/均涨。",
                "rel": "→ 牛人追踪（行业版入口） → 玩家图谱（按知名度重排）。",
                "stat": STAT["elite"], "date": "2026-06-30", "fresh": badge("warn", "定期"),
            },
            {
                "ic": "🌟", "t": "行业知名 Top20 玩家图谱", "href": "web/shareholder/top-elite.html",
                "func": "按行业知名度与历史业绩策划的 私募 / 牛散 Top20（非短期收益胜率），并交叉标注与高管增减持共现的知名主体。",
                "rel": "→ 高管增减持（查看共现） → 牛人追踪（任意查持仓）。",
                "stat": "", "date": "2026-09-04", "fresh": badge("warn", "策划"),
            },
            {
                "ic": "📈", "t": "股票增持信号扫描", "href": "web/shareholder/stock-accumulation.html",
                "func": "全市场 5544 只中报十大流通股东变动逐只扫描：增持 / 减持家数与股数，筛出「增持多于减持」并高亮知名私募 / 牛散加仓标的。",
                "rel": "→ 健康度过滤（在上游 50 只上叠技术面）。",
                "stat": STAT["accum"], "date": "2026-06-30", "fresh": badge("warn", "定期"),
            },
            {
                "ic": "🩺", "t": "知名加仓 · 量价健康度过滤", "href": "web/shareholder/known-accumulation-health.html",
                "func": "在上游 50 只知名私募 / 牛散加仓股上叠加技术面二次过滤：趋势结构 + 动量健康 + 量价配合 + 相对位置，纯量价口径打分。",
                "rel": "← 增持扫描（上游） → 个股调研（最终单只深挖）。",
                "stat": STAT["khealth"], "date": "2026-09-04", "fresh": badge("warn", "定期"),
            },
        ],
    },
    {
        "ic": "🎯", "t": "个股信号池（次日建仓候选）",
        "desc": "把上游三路信号合流打分，直接输出「明天可关注哪些票、什么价进、什么价止损」的交易计划，并每日归档回看胜率。",
        "rel": "中报增减持 + 高管增减持 + 大宗交易（三路信号）→ 叠加当日量价确认 → 输出候选与买卖点 → 次日自动回填表现。",
        "cards": [
            {
                "ic": "🎯", "t": "个股信号池 · 每日候选", "href": "web/picks/index.html",
                "func": "每日盘后输出建仓候选池与逐只交易计划：进场区间 / 止损 / 目标位 / 盈亏比 / 建议仓位，含评分模型说明与历史胜率归档。",
                "rel": "← 高管增减持 + 大宗交易 + 中报（三路上游） → 个股调研（选中后深挖）。",
                "stat": STAT["pick"], "date": fmt(pick_d), "fresh": badge(pick_cls, pick_txt),
            },
            {
                "ic": "📉", "t": "信号池回测", "href": "web/picks/backtest.html",
                "func": "按档位 × 周期（T+1 / T+3 / T+5）统计候选股实际表现：平均收益、胜率、触及目标与止损次数，用于校准模型权重。",
                "rel": "← 个股信号池（每日累积 history.json） → 权重调优。",
                "stat": STAT["pick"], "date": fmt(pick_d), "fresh": badge(pick_cls, pick_txt),
            },
        ],
    },
    {
        "ic": "🔁", "t": "做T池（区间反复做T）",
        "desc": "筛出高波动 + 高流动性 + 区间震荡且机构底仓扎实的标的，用网格/波段方法反复做T摊低成本。",
        "rel": "机构底仓（公募/社保/险资）→ 技术面筛震荡箱体 → 网格档位 + 波段买卖点。",
        "cards": [
            {
                "ic": "🔁", "t": "做T池 · 每日候选", "href": "web/tplus/index.html",
                "func": "从 848 只机构底仓池中筛出可反复做T的标的：箱体区间 / 网格 5 档价位 / 波段买卖区 / 止损 / 仓位建议，含机构方法论说明与历史归档。",
                "rel": "← 机构底仓池（公募/社保/险资） → 数据中心（积累历史）。",
                "stat": STAT["tplus"], "date": fmt(tplus_d), "fresh": badge(tplus_cls, tplus_txt),
            },
        ],
    },
    {
        "ic": "🔍", "t": "单只深挖",
        "desc": "从池子筛到具体一只票后的完整调研。",
        "rel": "上游：板块强度 + 牛人追踪 + 健康度过滤 + 个股信号池 → 下游：个股调研 → 数据中心。",
        "cards": [
            {
                "ic": "🔍", "t": "个股调研（三周期）", "href": "web/research/index.html",
                "func": "单只 A 股「短线 / 中线 / 长线」三周期调研：单季拆分、内部人行为对照、板块资金确认、七条标准打分。",
                "rel": "← 板块强度 / 牛人追踪 / 健康度（筛选上游） → 数据中心（查历年）。",
                "stat": STAT["research"], "date": fmt(research_d), "fresh": badge(research_cls, research_txt),
            },
        ],
    },
    {
        "ic": "🗄️", "t": "数据与工具",
        "desc": "底层数据查询 + 每日自检。",
        "rel": "数据中心 = 所有模块的历史；版块总览 = 每日落后检查。",
        "cards": [
            {
                "ic": "🗄️", "t": "数据中心", "href": "web/db/index.html",
                "func": "全模块历史数据查询：龙虎榜 / 高管增减持 / 大宗 / 板块强度 / 涨停梯队 / 热搜 / 新闻 / 大盘指标，支持模块切换、日期区间、搜索、专项筛选。",
                "rel": "← 所有上方页面的历史数据源。",
                "stat": "8 模块 ｜ 列式分片 ｜ 按月归档",
                "date": TODAY.strftime("%Y-%m-%d"), "fresh": badge("fresh", "实时"),
            },
            {
                "ic": "📦", "t": "版块总览（自检）", "href": "web/sections/index.html",
                "func": "所有版块的内容清单 / 数据来源 / 更新节奏 / 更新时间建议；每日更新后一眼看出哪个版块落后。",
                "rel": "本门户卡片的数据来源说明页。",
                "stat": STAT["sec2"],
                "date": fmt(max([d for d in [lhb_d, exec_d, sec_d, psy_d] if d], default=None)),
                "fresh": badge("fresh", "自检页"),
            },
        ],
    },
]

# ---- 渲染各功能区 ----
def _zone_section(z):
    cards_in_zone = "\n".join(
        f"<a class='card' href='{c['href']}'>"
        f"<div class='cardtop'><span class='ic'>{c['ic']}</span>{c['fresh']}</div>"
        f"<div class='t'>{c['t']}</div>"
        f"<div class='func'>{c.get('func', c.get('d', ''))}</div>"
        f"<div class='rel'>{c.get('rel', '')}</div>"
        + (f"<div class='stat'>{c['stat']}</div>" if c.get('stat') else "")
        + f"<div class='meta'>数据截至 {c['date']}</div>"
        f"</a>" for c in z["cards"]
    )
    return (
        f"<section class='zone'>"
        f"<div class='zone-h'>"
        f"<span class='zone-ic'>{z['ic']}</span>"
        f"<h2 class='zone-t'>{z['t']}</h2>"
        f"</div>"
        f"<div class='zone-desc'>{z['desc']}</div>"
        f"<div class='zone-rel'><b>关联：</b>{z['rel']}</div>"
        f"<div class='grid'>{cards_in_zone}</div>"
        f"</section>"
    )

zones_html = "\n".join(_zone_section(z) for z in ZONES)

# ---- 每日更新清单 ----
update_steps = [
    ("① 拉取当日快照", "用 westock-mcp 拉取 market_overview / board_hot / quotes / limitup / lhb / news，分别落盘到 quant 对应子目录的 <b>{DATE}.json</b>；再补 lhb 个股明细（分 3 批）。"),
    ("② 高管增减持", "<code>tool_event(manager_sharechg)</code> + <code>data_quote</code> → <code>python quant\\gen_exec.py --date {DATE}</code> → <code>python quant\\build_exec.py --date {DATE}</code>。T+1 口径，接口快照日为前一交易日。"),
    ("③ 大宗交易", "<code>tool_event(names=block_past_30, limit=3000)</code>（<b>limit 必须给足</b>，默认 500 会截断当日数据）→ <code>data_quote</code> 补涨跌幅 → <code>python quant\\gen_block.py --date {DATE} --src &lt;事件落盘&gt; --quotes &lt;行情落盘&gt;</code> → <code>python quant\\build_block.py --date {DATE}</code>。"),
    ("④ 生成龙虎榜主看板", "<code>python quant\\build_dashboards.py --date {DATE}</code> → 重写 web/ 下各页面（<b>会重建 web/lhb/index.html</b>）。"),
    ("⑤ 板块强度（必做 · 不可回溯）", "拉 industry + concept 快照 → <code>python quant\\gen_sector_raw.py</code> → <code>python quant\\run_daily_sector.py --date {DATE} --industry &lt;绝对路径&gt; --concept &lt;绝对路径&gt;</code>。<b>漏跑一天该交易日永久断档</b>。"),
    ("⑥ 心理风险雷达（按需）", "按 web/psychology 既有 _build 范式生成 crowd-psychology-risk-radar-{DATE}.html 并入 web/psychology/index.html。数据内嵌在 _build 脚本内。"),
    ("⑦ 刷新门户与总览", "<code>python quant\\build_portal.py</code> → <code>python quant\\build_sections.py</code> → <code>python quant\\_apply_nav.py</code>（统一导航自愈）→ 各卡片自动带出最新日期与新鲜度。"),
    ("⑧ 校验与推送", "合规扫描（产物内不得出现个人持有信息、账户盈亏、自下而上选股等敏感内容，关键词清单见项目约定）；<code>python quant\\_link_check.py</code> 须 0 断链；经 GitHub Contents API 推送（<code>python quant\\_push_lhb.py</code>）。"),
]

steps_html = "\n".join(
    f"<div class='step'><div class='no'>{i+1}</div><div><b>{t}</b><br><span class='sd'>{d}</span></div></div>"
    for i, (t, d) in enumerate(update_steps)
)

html = f"""<!DOCTYPE html>
<html lang='zh-CN'>
<head>
<meta charset='UTF-8'>
<meta name='viewport' content='width=device-width,initial-scale=1.0'>
<title>A股分析中心 · 总门户</title>
<style>
* {{ box-sizing:border-box; }}
body {{ margin:0; background:#f5f6f8; color:#1c2430;
  font-family:"PingFang SC","Microsoft YaHei","Hiragino Sans GB",sans-serif; line-height:1.7; }}
.wrap {{ max-width:1080px; margin:0 auto; padding:40px 22px 70px; }}
header.top {{ border-bottom:3px solid #1f4e79; padding-bottom:18px; margin-bottom:18px; }}
h1 {{ font-size:30px; margin:0 0 6px; letter-spacing:.5px; }}
.sub {{ color:#5a6573; font-size:14px; }}
.updated {{ color:#7b8794; font-size:12.5px; margin:6px 0 0; }}
/* 功能区 */
section.zone {{ margin:30px 0 0; padding:18px 0 0; border-top:1px dashed #d8dde5; }}
section.zone:first-of-type {{ border-top:none; padding-top:6px; }}
.zone-h {{ display:flex; align-items:center; gap:10px; margin-bottom:4px; }}
.zone-ic {{ font-size:24px; }}
.zone-t {{ font-size:20px; margin:0; color:#1f4e79; padding-left:10px; border-left:5px solid #1f4e79; }}
.zone-desc {{ color:#5a6573; font-size:13.5px; margin:6px 0 2px; }}
.zone-rel {{ background:#eef4fa; border-left:3px solid #2b6cb0; padding:6px 12px; border-radius:0 6px 6px 0; font-size:12.5px; color:#1f4e79; margin:0 0 14px; }}
.zone-rel b {{ color:#1f4e79; }}
/* 卡片网格 */
.grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(240px,1fr)); gap:14px; }}
.card {{ display:flex; flex-direction:column; text-decoration:none; color:inherit; background:#fff; border:1px solid #e3e7ec;
  border-radius:14px; padding:18px 18px 14px; box-shadow:0 2px 8px rgba(20,30,50,.05); transition:.18s; }}
.card:hover {{ border-color:#2b6cb0; transform:translateY(-3px); box-shadow:0 8px 22px rgba(31,78,121,.12); }}
.cardtop {{ display:flex; align-items:center; justify-content:space-between; }}
.ic {{ font-size:24px; }}
.t {{ font-size:16px; font-weight:700; margin:8px 0 6px; color:#1c2430; }}
.func {{ font-size:12.5px; color:#3a4048; line-height:1.6; min-height:54px; }}
.rel {{ font-size:11.5px; color:#2b6cb0; background:#f5faff; padding:4px 8px; border-radius:6px; margin-top:6px; line-height:1.5; }}
.meta {{ font-size:11.5px; color:#7b8794; margin-top:8px; padding-top:8px; border-top:1px dashed #e3e7ec; }}
.stat {{ font-size:12px; color:#3a4048; margin-top:8px; padding:6px 10px; background:rgba(184,137,59,.06);
  border-radius:6px; line-height:1.7; }}
.stat b {{ color:#1c2430; font-weight:700; }}
.badge {{ font-size:11px; padding:3px 10px; border-radius:20px; font-weight:700; }}
.badge.fresh {{ background:#e6f6ee; color:#128a52; }}
.badge.warn {{ background:#fdf3e0; color:#b7791f; }}
.badge.stale {{ background:#fdecea; color:#c0392b; }}
.sop {{ background:#fff; border:1px solid #e3e7ec; border-radius:14px; padding:8px 22px; margin:14px 0;
  box-shadow:0 1px 4px rgba(20,30,50,.04); }}
.step {{ display:flex; gap:14px; padding:14px 4px; border-bottom:1px solid #eef1f4; }}
.step:last-child {{ border-bottom:none; }}
.no {{ flex:none; width:26px; height:26px; line-height:26px; text-align:center; border-radius:50%;
  background:#1f4e79; color:#fff; font-size:13px; font-weight:700; }}
.sd {{ font-size:13px; color:#5a6573; }}
code {{ background:#eef4fa; color:#1f4e79; padding:1px 6px; border-radius:5px; font-size:12.5px; }}
.note {{ background:#fffaf0; border-left:4px solid #b7791f; padding:12px 16px; border-radius:0 8px 8px 0;
  font-size:13.5px; color:#6b4f2a; margin:14px 0; }}
h2.sec {{ font-size:21px; margin:44px 0 16px; padding-left:12px; border-left:5px solid #1f4e79; }}
footer {{ margin-top:48px; padding-top:18px; border-top:1px solid #e3e7ec;
  font-size:12px; color:#7b8794; line-height:1.8; }}
@media(max-width:700px){{ .wrap{{padding:24px 12px 50px;}} h1{{font-size:22px;}} .grid{{grid-template-columns:1fr;}} .zone-t{{font-size:16px;}} }}
</style>
</head>
<body>
<div class='wrap'>
{PORTAL_NAV}
<header class='top'>
  <h1>A股分析中心 · 总门户</h1>
  <div class='sub'>按功能区分组：每日总览 → 资金动向 → 市场情绪 → 牛人与股东 → 单只深挖 → 数据与工具</div>
  <div class='updated'>门户重建于 {TODAY.strftime('%Y-%m-%d')} · 每张卡片标注功能、关联页面、数据新鲜度</div>
</header>

{zones_html}

<div class='note'><b>⏰ 建议更新时间：交易日当晚 20:00–21:00</b>（龙虎榜已公布、大盘统计已聚合）。<b>板块强度必须在次日 09:15 前跑完</b>——接口只返回最新快照，开盘后即被覆盖且不可回溯。完整版块说明与自检清单见 <a href='web/sections/index.html'>版块总览</a>。</div>

<h2 class='sec'>📅 每日更新清单（SOP）</h2>
<div class='note'>完整操作手册（数据口径、已知坑、校验清单）见 <a href='web/docs/DAILY_UPDATE_SOP.html'>DAILY_UPDATE_SOP.html</a>。下表为精简步骤，各子系统最新日期以本门户卡片为准。</div>
<div class='sop'>
{steps_html}
</div>

<footer>
数据来源：腾讯自选股 <b>westock-mcp</b>（盘后公开数据，滞后且非未来收益承诺）。<br>
全部页面由 A股量化助理自动化生成 · 仅供参考，<b>不构成投资建议</b> · 市场有风险，投资需谨慎。
</footer>
</div>
</body>
</html>
"""

with open(OUT, "w", encoding="utf-8") as f:
    f.write(html)
print(f"OK: 总门户已生成 -> {OUT}")
print(f"    龙虎榜={fmt(lhb_d)} | 高管增减持={fmt(exec_d)} | 大宗交易={fmt(blk_d)} | 板块强度={fmt(sec_d)} | 心理雷达={fmt(psy_d)}")
print("    下一步：python quant\\build_sections.py（版块总览 / 自检页）")
