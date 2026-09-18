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
reversal_d, reversal_f = latest(r"^watchlist_(\d{8})\.html$", os.path.join(WEB, "reversal"))
macd_d, macd_f = latest(r"^watchlist_(\d{8})\.html$", os.path.join(WEB, "macd"))
exec_d, exec_f = latest(r"^(\d{4}-\d{2}-\d{2})\.json$", os.path.join(ROOT, "quant", "exec_chg"))
blk_d, blk_f = latest(r"^(\d{4}-\d{2}-\d{2})\.json$", os.path.join(ROOT, "quant", "block_chg"))
# 每日总览（大盘看板）：取 market_overview 最新快照日期
mkt_d, mkt_f = latest(r"^(\d{4}-\d{2}-\d{2})\.json$", os.path.join(QUANT, "market_overview"))

# 个股信号池：读 history.json 取最新一期日期与档位分布
pick_d = None
pick_stat = ""
try:
    _hp = os.path.join(ROOT, "quant", "picks", "history.json")
    if os.path.exists(_hp):
        _h = json.load(open(_hp, encoding="utf-8"))
        if _h:
            pick_d = datetime.date.fromisoformat(_h[-1]["date"])
            _ni = _h[-1].get("nInst")
            _ny = _h[-1].get("nYouzi")
            if _ni is None and _ny is None:
                _n = _h[-1].get("n", 0)
                pick_stat = f"候选 {_n} 只 ｜ 每日交易计划"
            else:
                pick_stat = f"机构轨 {_ni or 0} 只 ｜ 游资轨 {_ny or 0} 只 ｜ 每日交易计划"
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


def stat_market():
    """每日总览：上证收盘涨跌 / 涨跌家数 / 涨停数（从 quant/market_overview 最新快照）。

    注意：market_overview 的部分分段在数据源降级期可能为空（如 market_statis_summary），
    这里逐段取值、缺则跳过，保证不因单段缺失而整体失败。
    """
    if not mkt_f:
        return ""
    d = _load_json(os.path.join(QUANT, "market_overview", mkt_f))
    if not d:
        return ""
    segs = {}
    for s in (d.get("data") or []):
        segs[s.get("listCode")] = (s.get("row") or {})
    dt = segs.get("market_statis_daily_trade") or {}
    ud = segs.get("market_statis_updown") or {}
    parts = []
    close, chg = dt.get("CLOSE_PRICE_SZZS"), dt.get("CHANGE_PCT_SZZS")
    if close is not None and chg is not None:
        arrow = "▲" if chg >= 0 else "▼"
        parts.append(f"上证 <b>{close:.0f}</b> {arrow}{abs(chg):.2f}%")
    red, green = ud.get("CNT_RED"), ud.get("CNT_GREEN")
    if red is not None and green is not None:
        parts.append(f"涨 <b>{red}</b> / 跌 <b>{green}</b>")
    up = ud.get("CNT_REACH_UPLIMIT")
    if up is not None:
        parts.append(f"涨停 <b>{up}</b> 只")
    return " ｜ ".join(parts)


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


def stat_reversal():
    """底部反转观察池：已累积期数 + 最新一期日期"""
    d = os.path.join(WEB, "reversal")
    if not os.path.isdir(d):
        return ""
    fs = [f for f in os.listdir(d) if re.match(r"^watchlist_\d{8}\.html$", f)]
    if not fs:
        return ""
    latest_dt = reversal_d.strftime("%Y-%m-%d") if reversal_d else "—"
    return f"已累积 <b>{len(fs)}</b> 期观察池 ｜ 最新 {latest_dt}"


def stat_macd():
    """MACD 水上金叉观察池：入选数 / 水上金叉数 / 初筛数"""
    if not macd_d or not macd_f:
        return ""
    p = os.path.join(QUANT, "macd_scan_%s.json" % macd_d.strftime("%Y%m%d"))
    d = _load_json(p)
    if not d:
        return ""
    return (f"入选 <b>{d.get('final_count', '—')}</b> 只 ｜ "
            f"水上金叉 <b>{d.get('above_water', '—')}</b> ｜ "
            f"初筛 <b>{d.get('pool_total', '—')}</b> 只")


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


STAT = {
    "market": stat_market(),
    "lhb": stat_lhb(),
    "exec": stat_exec(),
    "block": stat_block(),
    "sec": stat_sector(),
    "psy": stat_psy(),
    "elite": stat_industry_elite(),
    "accum": stat_stock_accumulation(),
    "khealth": stat_known_health(),
    "research": stat_research(),
    "reversal": stat_reversal(),
    "macd": stat_macd(),
}

lhb_txt, lhb_cls = freshness(lhb_d)
mkt_txt, mkt_cls = freshness(mkt_d)
sec_txt, sec_cls = freshness(sec_d)
psy_txt, psy_cls = freshness(psy_d)
research_txt, research_cls = freshness(research_d)
reversal_txt, reversal_cls = freshness(reversal_d)
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

# ---- 功能区定义（与导航的 5 大模块一一对应）----
# 模块顺序与 _nav.py 的 MODULES 完全一致：
#   大盘与情绪 → 板块与资金 → 牛人与股东 → 选股与策略 → 数据与工具
# 每个模块内的卡片由统一的固定 3 列等宽网格渲染（.grid），
# 保证全站卡片同宽同高、每行左对齐，版面左右对称、不再「忽宽忽窄」。
ZONES = [
    {
        "ic": "🌡️", "t": "大盘与情绪",
        "desc": "每天先看大势：指数位置与量能、涨跌家数、涨停梯队、板块热度，以及市场群体情绪处在周期的什么位置。",
        "rel": "每日总览看「广度 + 量能」（定量），群体心理看「情绪 + 认知偏差」（定性），一量一性互相印证。",
        "cards": [
            {
                "ic": "🗺️", "t": "每日总览", "href": "web/market/index.html",
                "func": "大盘看板：指数与量能 / 涨跌家数 / 涨停梯队 / 资金流向 / 板块热度，一屏看清当日市场全貌。",
                "rel": "📌 汇总龙虎榜与板块强度的上游数据。",
                "stat": STAT["market"], "date": fmt(mkt_d), "fresh": badge(mkt_cls, mkt_txt),
            },
            {
                "ic": "🧠", "t": "群体心理风险雷达", "href": "web/psychology/index.html",
                "func": "情绪周期 / 认知偏差热力 / 风险分层，每日单篇 + 跨日趋势索引 + 六维雷达图。",
                "rel": "→ 龙虎榜（情绪外化为异动） → 板块强度（情绪外化为资金方向）。",
                "stat": STAT["psy"], "date": fmt(psy_d), "fresh": badge(psy_cls, psy_txt),
            },
        ],
    },
    {
        "ic": "💰", "t": "板块与资金",
        "desc": "钱往哪里去：板块资金强度与主力行为、龙虎榜异动与席位、一线游资活跃方向，以及董监高与大宗这两类「内部人动作」。",
        "rel": "板块强度 + 龙虎榜 + 游资看板 = 资金的「方向」；高管增减持 + 大宗交易 = 内部人的「动作」。",
        "cards": [
            {
                "ic": "🔥", "t": "板块强度", "href": "web/sector/index.html",
                "func": "行业 / 概念板块的当日资金强度 + 主力行为（抢筹 / 建仓 / 洗盘 / 出货）+ 多日趋势 + 估值分位。",
                "rel": "→ 行业最强榜（按行业筛最强股东） → 牛人追踪（按板块筛持仓）。",
                "stat": STAT["sec"], "date": fmt(sec_d), "fresh": badge(sec_cls, sec_txt),
            },
            {
                "ic": "🐉", "t": "龙虎榜主看板", "href": "web/lhb/lhb.html",
                "func": "异动个股 / 机构榜 / 游资席位胜率 / 机构 + 游资共振 信号。",
                "rel": "→ 游资看板（席位活跃度） → 牛人追踪·游资席位。",
                "stat": STAT["lhb"], "date": fmt(lhb_d), "fresh": badge(lhb_cls, lhb_txt),
            },
            {
                "ic": "🌊", "t": "游资看板", "href": "web/market/hotmoney.html",
                "func": "龙虎榜营业部 / 游资席位活跃度与胜率，看一线游资在猛攻哪些方向。",
                "rel": "→ 龙虎榜主看板（席位明细） → 牛人追踪·游资席位。",
                "stat": "", "date": fmt(lhb_d), "fresh": badge(lhb_cls, lhb_txt),
            },
            {
                "ic": "💼", "t": "高管增减持（董监高）", "href": "web/exec/index.html",
                "func": "全市场董监高持股变动：增持 / 减持明细与金额、申万行业分布、个股聚合净额。",
                "rel": "→ 玩家图谱（共现主体交叉标注） → 数据中心（翻历史）。",
                "stat": STAT["exec"], "date": fmt(exec_d), "fresh": badge(exec_cls, exec_txt),
            },
            {
                "ic": "🧾", "t": "大宗交易", "href": "web/block/archive.html",
                "func": "全市场大宗交易逐笔：折溢价、成交额、买卖营业部、机构席位动向；每日归档。",
                "rel": "→ 高管增减持（大宗折价可能配合内部人出货） → 数据中心。",
                "stat": STAT["block"], "date": fmt(blk_d), "fresh": badge(blk_cls, blk_txt),
            },
            {
                "ic": "📉", "t": "板块强度 · 多日趋势", "href": "web/sector/sector-strength-trend.html",
                "func": "把每日板块强度连成时间序列：全市场暗盘资金净额、主力行为分布（抢筹 / 建仓 / 洗盘 / 出货）逐日趋势、板块逐日明细与领涨股、多板块对比。",
                "rel": "← 板块强度（每日快照累积而成） → 行业最强榜（挑出持续走强的行业）。",
                "stat": "逐日累积 ｜ 暗盘资金 + 主力行为分布",
                "date": fmt(sec_d), "fresh": badge(sec_cls, sec_txt),
            },
        ],
    },
    {
        "ic": "👑", "t": "牛人与股东",
        "desc": "谁在持仓：全市场 5500+ 只中报十大股东逐只解析出的牛散 / 私募 / 公募持仓，以及龙虎榜营业部对应的游资席位。",
        "rel": "牛人追踪是索引入口；行业最强榜 / 玩家图谱 / 增持扫描 / 健康度过滤 是四个专题视角（季频刷新）。",
        "cards": [
            {
                "ic": "🎯", "t": "牛人追踪（索引）", "href": "web/shareholder/tracker.html",
                "func": "全市场 5500+ 只中报十大股东 → 牛散 / 私募 / 公募 索引 + 龙虎榜营业部 → 游资席位；含 Q2↔Q1 增减持信号，可关注代号、可按行业筛选。",
                "rel": "← 行业最强榜（行业版） ← 玩家图谱（精选版） ← 增持扫描（信号版） ← 健康度过滤（技术版）。",
                "stat": "牛散 2640 ｜ 私募 939 ｜ 公募 867 ｜ 游资 833",
                "date": "2026-Q2", "fresh": badge("warn", "季频"),
            },
            {
                "ic": "🏆", "t": "行业最强榜（全市场）", "href": "web/shareholder/2026-q2-industry-elite.html",
                "func": "申万 31 个行业各自最强的 自然人 / 私募 / 公募 各 20 名 + 资金估值四象限 + 胜率 / 均涨。",
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
        "ic": "🎯", "t": "选股与策略",
        "desc": "自下而上：把筛选方法沉淀成每日可重扫的观察池，再汇流成带买卖点的交易计划，最后对选中的单只票做三周期深挖。",
        "rel": "底部反转 / MACD 金叉 → 输出候选；个股信号池 → 给进场 / 止损 / 仓位；个股调研 → 选中后深挖。",
        "cards": [
            {
                "ic": "📈", "t": "底部反转观察池", "href": "web/reversal/index.html",
                "func": "六步法（turnaround / main_inflow / low_pb 交叉 → 流通 < 100 亿 → 低位 → 扣非 PE → 20 日主力净流入 → 技术金叉）每日重扫，输出 A/B/C 分级观察池与方法论常驻页。",
                "rel": "← 全市场初筛（tool_filter） → 逐只验证（quote / fund_flow / technical）",
                "stat": STAT["reversal"], "date": fmt(reversal_d), "fresh": badge(reversal_cls, reversal_txt),
            },
            {
                "ic": "📊", "t": "MACD 金叉池（已并入精选池）", "href": "web/macd/index.html",
                "func": "三层漏斗（主力流入初筛 → MACD 零轴上方金叉 → 20 日主力净流入为正）每日重扫，输出趋势转多 × 资金进场共振的强势候选。2026-09-19 起不再单独荐股：其两层条件已并入精选池作技术确认门槛，本页保留为技术面观察归档 + 高胜率池基底。",
                "rel": "← 全市场初筛（tool_filter）→ data_technical（水上金叉）→ data_fund_flow（20 日净流入）→ 并入精选池",
                "stat": STAT["macd"], "date": fmt(macd_d) if macd_d else "—", "fresh": badge("fresh", "每日" if macd_d else "—"),
            },
            {
                "ic": "🎯", "t": "精选池 · 每日出池", "href": "web/picks/index.html",
                "func": "每日盘后输出【实际出池】标的与逐只交易计划：进场区间 / 止损 / 目标位 / 盈亏比 / 建议仓位。出池门槛：最高档直接出，次高档须通过「20 日主力净流入为正」技术确认；当日无合格标的则明示空仓等待。含评分模型说明与历史胜率归档。",
                "rel": "← 高管增减持 + 大宗交易 + 中报（三路上游）+ MACD 技术确认 → 个股调研（选中后深挖）。",
                "stat": STAT["pick"], "date": fmt(pick_d), "fresh": badge(pick_cls, pick_txt),
            },
            {
                "ic": "📉", "t": "信号池回测", "href": "web/picks/backtest.html",
                "func": "按档位 × 周期（T+1 / T+3 / T+5）统计候选股实际表现：平均收益、胜率、触及目标与止损次数，用于校准模型权重。",
                "rel": "← 个股信号池（每日累积 history.json） → 权重调优。",
                "stat": STAT["pick"], "date": fmt(pick_d), "fresh": badge(pick_cls, pick_txt),
            },
            {
                "ic": "🔁", "t": "做T池 · 每日候选", "href": "web/tplus/index.html",
                "func": "从 848 只机构底仓池中筛出可反复做 T 的标的：箱体区间 / 网格 5 档价位 / 波段买卖区 / 止损 / 仓位建议。<b>大盘环境门控</b>：强势放行 A/B/C、震荡放行 A/B、弱势只放行 A 档并附加「非高位 · MA20 未明显下行 · 箱体不过宽」，仓位按环境打 0.55~1.0 折，破位不放行新开仓；卖区按 1.2×ATR 设定（不再死等箱体上沿）。",
                "rel": "← 机构底仓池（公募 / 社保 / 险资） → 数据中心（积累历史）。",
                "stat": STAT["tplus"], "date": fmt(tplus_d), "fresh": badge(tplus_cls, tplus_txt),
            },
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
        "desc": "底层数据查询与更新纪律：所有模块的历史数据、完整操作手册，以及更新节奏与自检清单。",
        "rel": "数据中心 = 所有模块的历史数据源；另两份文档管住「怎么更、什么时候更」。",
        "cards": [
            {
                "ic": "🗄️", "t": "数据中心", "href": "web/db/index.html",
                "func": "全模块历史数据查询：龙虎榜 / 高管增减持 / 大宗 / 板块强度 / 涨停梯队 / 热搜 / 新闻 / 大盘指标，支持模块切换、日期区间、搜索、专项筛选。",
                "rel": "← 所有上方模块页面的历史数据源。",
                "stat": "8 模块 ｜ 列式分片 ｜ 按月归档",
                "date": TODAY.strftime("%Y-%m-%d"), "fresh": badge("fresh", "实时"),
            },
            {
                "ic": "📘", "t": "每日更新 SOP（完整手册）", "href": "web/docs/DAILY_UPDATE_SOP.html",
                "func": "数据口径、执行顺序、已知坑、校验清单的完整操作手册，按顺序执行不易漏项。",
                "rel": "← 本文档「每日更新清单」的完整版（含脚本命令与坑位说明）。",
                "stat": "12 步流水线 ｜ 含数据口径与已知坑",
                "date": TODAY.strftime("%Y-%m-%d"), "fresh": badge("fresh", "文档"),
            },
            {
                "ic": "⏱️", "t": "更新节奏与自检清单", "href": "web/docs/update-cadence.html",
                "func": "把全站 15 个数据维度按「每日 / 季频 / 按需 / 门禁」四档归类，附可勾选并本地保存的每日必做清单与关键时间红线。",
                "rel": "← 本文档「每日更新时间建议」的完整版。",
                "stat": "22 个维度 ｜ 四档节奏 ｜ 可勾选清单",
                "date": TODAY.strftime("%Y-%m-%d"), "fresh": badge("fresh", "文档"),
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
    n = len(z["cards"])
    return (
        f"<section class='zone'>"
        f"<div class='zone-h'>"
        f"<div class='zone-ht'><span class='zone-ic'>{z['ic']}</span>"
        f"<h2 class='zone-t'>{z['t']}</h2></div>"
        f"<span class='zone-cnt'>{n} 个入口</span>"
        f"</div>"
        f"<div class='zone-desc'>{z['desc']}</div>"
        f"<div class='zone-rel'><b>关联：</b>{z['rel']}</div>"
        f"<div class='grid'>{cards_in_zone}</div>"
        f"</section>"
    )

zones_html = "\n".join(_zone_section(z) for z in ZONES)
_n_cards = sum(len(z["cards"]) for z in ZONES)

# ---- 每日更新清单 ----
update_steps = [
    ("① 拉取当日快照", "经 westock-mcp 拉取 market_overview / board_hot / quotes / limitup / lhb / news，分别落盘到 <code>quant/</code> 对应子目录的 <b>{DATE}.json</b>；再补 <code>lhb</code> 个股明细（分 3 批）与分项 4 次 <code>type</code>。<b>降级期</b> market_overview / limitup / board_hot 可能返回 error_type=2，缺失即诚实标注降级，<b>不得用旧数据冒充当日</b>。"),
    ("② 龙虎榜主看板", "<code>python quant/build_lhb_enriched.py</code> → <code>python quant/build_dashboards.py --date {DATE}</code>，重写 web/ 下各页面（<b>会重建 web/lhb/index.html</b>）。席位明细最易漏，漏跑则全榜表从 9 列退化 6 列。"),
    ("③ 高管增减持", "<code>tool_event(manager_sharechg, limit=700)</code>；<b>降级期</b>经东财 <code>RPT_EXECUTIVE_HOLD_DETAILS</code> 回补（变动日口径、覆盖约 76%）→ 落 <code>quant/exec_chg/{DATE}.json</code> → <code>python quant/gen_exec.py --date {DATE}</code> → <code>python quant/build_exec.py --date {DATE}</code>。"),
    ("④ 大宗交易", "<code>block_past_30(limit=3000)</code>；<b>降级期</b>经东财 <code>RPT_DATA_BLOCKTRADE</code>（pageSize=5000；折扣 <code>discount=-PREMIUM_RATIO*100</code>，正=折价）→ 落 <code>quant/block_chg/{DATE}.json</code> → <code>python quant/gen_block.py --date {DATE}</code> → <code>python quant/build_block.py --date {DATE}</code>。"),
    ("⑤ 板块强度（必做 · 不可回溯）", "拉 industry(ranking, limit=300) + concept(limit=1000) 快照 → <code>python quant/gen_sector_raw.py</code> → <code>python quant/run_daily_sector.py --date {DATE} --industry &lt;绝对路径&gt; --concept &lt;绝对路径&gt;</code>。<b>漏跑一天该交易日永久断档</b>，次日开盘后无法回补。"),
    ("⑥ 群体心理风险雷达（每日必做 · 已全自动化）", "<code>python quant/build_psychology.py --date {DATE}</code>（节假日用 <code>--next {NEXT}</code>）。读①②③④⑤ 的产物自动出页 + 写入索引 + 累积 <code>quant/psy/history.json</code>；<b>旧的手抄文案法 <code>_build_*_{MMDD}.py</code> 已废弃</b>。"),
    ("⑦ 精选池（原信号池 · 每日 · 双轨 + 技术确认出池）", "<code>python quant/gen_picks.py --date {DATE} --window 20 --top 40</code>（纯本地三路信号）→ agent 经 MCP 按 <code>_codes_{DATE}.txt</code> 以 25 只/批补拉 quote/technical/chip/fund_flow/margin/hot → <b><code>python quant/fetch_pick_klines.py --end {DATE}</code>（沙箱外；为全部选股码建 <code>quant/picks/price_archive.json</code> 日K价格档案，漏跑则次日无法回填昨日选股）</b> → <code>python quant/build_picks.py --date {DATE}</code>（backfill 读该档案按真实交易日历回填每只票 T+1/T+3/T+5，昨日选股今日结算；并用真实同日收盘+MA5 校正入场/止损/目标基准）→ <code>python quant/backtest_picks.py</code>（累积胜率）。<b><code>quotes_{DATE}.json</code> 缺失会导致 0 行输出</b>。<b>2026-09-19 起出池门槛：</b>最高档直接出池；次高档须通过「20 日主力净流入为正」（MACD 三层漏斗第 C 层，读 <code>fundflow_{DATE}.json</code> 的 <code>mainNetFlow20D</code>）才出池；其余一律折叠为仅跟踪。当日无出池标的时页面明示<b>空仓等待</b>——实测最高档 T+3 胜率 83%，次高档仅 47%，故不硬凑。"),
    ("⑧ 做T池（每日 · 底仓网格）", "<code>python quant/gen_tplus.py --date {DATE}</code>（本地 q2_full 机构底仓池，约 848 只）→ 补拉 <code>data_quote</code> + <code>data_kline</code>（约 848×60 根，<b>数据量最大，建议单独跑一轮</b>）→ <code>python quant/build_tplus.py --date {DATE}</code>。<b>2026-09-19 起加大盘环境门控（<code>quant/_idxkline.py</code>）</b>：市场画像评分 × 55% + 上证指数均线状态 × 45%，强势 ≥3.8 / 震荡 3.0~3.8 / 弱势 2.2~3.0 / 破位 &lt;2.2；强势放行 A/B/C、震荡放行 A/B、<b>弱势只放行 A 档</b>并附加「一年分位 ≤70% · MA20 斜率 ≥−1% · 箱体高度 ≤40%」，仓位按环境打 0.55~1.0 折，<b>破位不放行新开仓</b>；卖区改为 1.2×ATR 驱动（不再死等箱体上沿）。"),
    ("⑨ 反转 / MACD / 高胜率（每日扫描）", "三者均以当日 <code>tool_filter</code> 实拉落盘后再渲染：<code>python quant/gen_watchlist.py {DATE}</code> / <code>python quant/macd_build.py {DS} --raw</code> + <code>python quant/build_macd_extra.py --date {DATE}</code> + <code>python quant/macd_build.py {DS} --raw</code> + <code>python quant/gen_macd.py {DS}</code> / <code>python quant/build_highwin.py --date {DATE}</code> + <code>python quant/gen_highwin.py --date {DATE}</code>。<b>增强诊断列（52周分位 / 量比 / 换手 / 5日主力 / 归一化强度 / 获利盘 / 集中度）由 <code>build_macd_extra.py</code> 经 MCP 实拉 data_quote + data_chip + data_fund_flow 生成</b>，必须在 <code>macd_build.py</code> 之前跑，否则该表整列显示「无增强数据」；<b>高胜率须早于 <code>build_picks.py</code></b>，否则 picks/index 入链停在上期。"),
    ("⑩ 当日要闻", "<code>data_hot(kind=news)</code> 榜单落 <code>quant/_news_seed/{DATE}.json</code> → <code>python quant/add_news.py --date {DATE}</code>（可加 <code>--expect 50</code> 校验条数）。<b>不再每天新建一个脚本</b>。"),
    ("⑪ 数据库与门户重建", "<code>python quant/db_update.py {DATE}</code> → <code>python quant/db_export.py</code> → <code>python quant/build_portal.py</code> → <code>python quant/build_sections.py</code> → <code>python quant/_apply_theme.py</code>。门户卡片自动带出最新日期与新鲜度；<b>凡显示「非当日」的卡片即为漏跑项，须当天补齐或诚实标注降级</b>。"),
    ("⑫ 校验与推送", "合规扫描（产物内不得出现个人持有信息、账户盈亏等敏感内容）；<code>python quant/_link_check.py</code> 须 0 断链、<code>python quant/_coverage_check.py --until {DATE}</code> 无新增缺口、<code>python quant/_js_check.py --all</code> 通过；推送须<b>关闭沙箱</b>执行 <code>python quant/_push_lhb.py</code> → <code>python quant/_sync_all.py</code> 收敛 → <code>python quant/_curl_gate.py</code> 抽检核心页 200。"),
]

_LATEST = TODAY.strftime("%Y-%m-%d")
steps_html = "\n".join(
    f"<div class='step'><div class='no'>{i+1}</div><div><b>{t}</b><br><span class='sd'>{d}</span></div></div>"
    for i, (t, d) in enumerate(update_steps)
)
# 之前 {DATE} / {DS} / {NEXT} 占位符从未被替换，会原样输出到门户页面 —— 这里统一落地
steps_html = (steps_html
              .replace("{DATE}", _LATEST)
              .replace("{DS}", TODAY.strftime("%Y%m%d"))
              .replace("{NEXT}", (TODAY + __import__("datetime").timedelta(days=1)).strftime("%Y-%m-%d")))

# ---- 合并自原 build_sections.py 的参考信息 ----
RELATIONSHIPS = [
    ("📊 每日总览", "汇总：龙虎榜 + 板块强度 + 高管增减持 + 大宗", "→ 资金动向 / 市场情绪"),
    ("🐉 龙虎榜主看板", "席位明细 → 牛人追踪·游资席位", "← 数据中心（查历史席位）"),
    ("🌊 游资看板", "游资席位 → 龙虎榜主看板 / 牛人追踪·游资", "← 数据中心（查历史营业部）"),
    ("🔥 板块强度", "行业过滤 → 行业最强榜 / 牛人追踪", "← 数据中心（查历史板块）"),
    ("💼 高管增减持", "共现主体 → 玩家图谱", "← 数据中心（查历史增减持）"),
    ("🧾 大宗交易", "与高管增减持互补（折价+内部人）", "← 数据中心"),
    ("🧠 群体心理雷达", "情绪外化 → 龙虎榜 / 板块强度", "← 数据中心（趋势跨日）"),
    ("📈 底部反转观察池", "← 全市场初筛（tool_filter）→ 逐只验证（quote/fund_flow/technical）", "→ 数据中心（查历史观察池）"),
    ("📊 MACD 水上金叉", "← 主力流入初筛 → data_technical（水上金叉）→ data_fund_flow（20日净流入）", "→ 个股调研 / 信号池（共振候选深挖）"),
    ("🎯 个股信号池", "← 中报 / 高管增减持 / 大宗交易（三路信号）+ 量价确认", "→ 个股调研（选中后深挖）· → 归档回看胜率"),
    ("🎯 牛人追踪（索引）", "← 板块强度（按行业筛） / 高管（按主体筛）", "→ 数据中心（查历年）"),
    ("🏆 行业最强榜", "→ 牛人追踪（按行业版入口） / 玩家图谱", "← 数据中心"),
    ("🌟 玩家图谱", "→ 高管共现 / 牛人追踪", "← 数据中心"),
    ("📈 增持信号扫描", "→ 健康度过滤（技术面）", "← 数据中心"),
    ("🩺 健康度过滤", "← 增持信号扫描（上游 50 只）", "→ 个股调研（最终单只）"),
    ("🔍 个股调研", "← 板块强度 / 牛人追踪 / 健康度（筛选上游）", "→ 数据中心（查历年）"),
    ("🗄️ 数据中心", "← 所有上方页面的历史数据源", ""),
]

TIMELINE = [
    ("15:00", "收盘", "行情、涨跌停、板块资金定格", "ok"),
    ("15:30", "盘后数据可拉", "此时可开始跑，但龙虎榜未公布、大盘统计未聚合", "wait"),
    ("18:00 前后", "龙虎榜陆续公布", "沪深交易所盘后披露，个别标的可能延后", "wait"),
    ("19:30", "最早可靠窗口", "实测：龙虎榜 19:xx 与 20:56 复拉均为 62 只，已定稿", "ok"),
    ("20:00–21:00", "★ 推荐时段", "大盘统计聚合定稿（实测 20:00 与 20:56 涨跌分布完全一致）", "best"),
    ("次日 08:00–09:15", "补救窗口", "板块强度最后机会；高管增减持可纳入前夜公告", "warn"),
    ("次日 09:30", "✕ 死线", "开盘后板块快照被覆盖，T 日板块强度永久不可补", "dead"),
]

CHECKS = [
    "龙虎榜：market_overview / board_hot / quotes / limitup / lhb / news 全部落盘",
    "龙虎榜明细 3 批 + lhb_enriched_{DATE}.json + 申万涨跌幅映射刷新",
    "<b>板块强度</b>（不可跳过）：industry + concept 快照 → gen_sector_raw.py → run_daily_sector.py",
    "高管增减持：tool_event + data_quote → gen_exec.py → build_exec.py",
    "心理雷达（按需）",
    "build_portal.py → build_sections.py（重定向页）→ _apply_theme.py（统一导航自愈）",
    "合规扫描：产物内不得出现个人持有信息、账户盈亏、自下而上选股等敏感内容",
]


_rel_html = "".join(
    f"<div class='relrow'><div class='reln'>{n}</div>"
    f"<div class='relflow'>{f}</div><div class='relflow out'>{o}</div></div>"
    for n, f, o in RELATIONSHIPS
)
_tl_html = "".join(
    f"<div class='tl {c}'><div class='tt'>{t}</div><div class='tn'>{n}</div><div class='td'>{d}</div></div>"
    for t, n, d, c in TIMELINE
)

ref_html = f"""
<section class='zone'>
  <div class='zone-h'>
    <div class='zone-ht'><span class='zone-ic'>🔗</span><h2 class='zone-t'>页面关系（数据流 / 上下游）</h2></div>
    <span class='zone-cnt'>{len(RELATIONSHIPS)} 条链路</span>
  </div>
  <div class='zone-desc'>各模块之间如何相互喂养：大盘情绪 → 资金动向 → 选股信号 → 单只深挖 → 数据中心归档。</div>
  <div class='relwrap'>
    <div class='relhd'><div>页面</div><div>← 输入 / 依赖</div><div>输出 / 走向 →</div></div>
    {_rel_html}
  </div>
</section>

<section class='zone'>
  <div class='zone-h'>
    <div class='zone-ht'><span class='zone-ic'>⏰</span><h2 class='zone-t'>每日更新时间建议</h2></div>
    <span class='zone-cnt'>{len(TIMELINE)} 个时点</span>
  </div>
  <div class='zone-desc'>各接口可拉时间的实测边界，以及板块强度不可回溯的硬红线。</div>
  <div class='tlwrap'>{_tl_html}</div>
  <div class='pnote'><b>推荐：交易日当晚 20:00–21:00 手动触发一次全量更新。</b>此时龙虎榜已公布完毕、大盘统计聚合定稿、板块资金与行情早已定格。<b>硬约束：</b>板块强度的快照次日开盘即被覆盖且不可回溯，若当晚漏跑，务必在 <b>次日 09:15 之前</b> 补跑。完整操作手册（数据口径、已知坑、校验清单）见 <a href='web/docs/DAILY_UPDATE_SOP.html'>每日更新 SOP</a>；四档节奏与可勾选清单见 <a href='web/docs/update-cadence.html'>更新节奏与自检清单</a>。</div>
</section>
"""

html = f"""<!DOCTYPE html>
<html lang='zh-CN'>
<head>
<meta charset='UTF-8'>
<meta name='viewport' content='width=device-width,initial-scale=1.0'>
<title>A股分析中心 · 总门户</title>
<style>
header.top {{ margin:0 0 22px; }}
header.top h1 {{ font-size:28px; margin:0 0 6px; letter-spacing:-.2px; font-weight:500; }}
.sub {{ color:var(--muted); font-size:13px; }}
.updated {{ color:var(--muted); font-size:12px; margin:6px 0 0; }}
/* 模块区：不打外框，卡片直接浮于灰底（避免「卡片套卡片」），模块头以细线分隔 */
section.zone {{ margin:0 0 26px; }}
.zone-h {{ display:flex; align-items:center; justify-content:space-between; gap:12px; padding-bottom:7px; border-bottom:1px solid var(--line-2); }}
.zone-ht {{ display:flex; align-items:center; gap:9px; min-width:0; }}
.zone-ic {{ font-size:17px; line-height:1; }}
.zone-t {{ font-size:16px; margin:0; color:var(--ink); font-weight:600; letter-spacing:.01em; }}
.zone-cnt {{ font-size:11.5px; color:var(--muted); background:var(--hover); border:1px solid var(--line-2); border-radius:12px; padding:2px 10px; white-space:nowrap; }}
.zone-desc {{ color:var(--muted); font-size:12.5px; margin:8px 0 0; line-height:1.65; }}
.zone-rel {{ color:var(--muted); font-size:12px; margin:3px 0 12px; line-height:1.6; }}
.zone-rel b {{ color:var(--accent-ink); font-weight:600; }}
/* 统一卡片网格：固定 3 列 + 卡片等高 → 所有模块、所有卡片同宽同高，行行对齐 */
.grid {{ display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:12px; align-items:stretch; }}
.card {{ display:flex; flex-direction:column; min-height:264px; text-decoration:none; color:inherit;
  background:var(--surface); border:1px solid var(--line); border-radius:8px; padding:15px 16px 13px;
  box-shadow:0 1px 2px rgba(60,64,67,.08); transition:border-color .15s, box-shadow .15s, transform .15s; }}
.card:hover {{ border-color:var(--accent); box-shadow:0 2px 10px rgba(60,64,67,.18); transform:translateY(-1px); text-decoration:none; }}
.cardtop {{ display:flex; align-items:flex-start; justify-content:space-between; gap:8px; }}
.ic {{ font-size:19px; line-height:1; }}
.t {{ font-size:14.5px; font-weight:600; margin:8px 0 5px; color:var(--ink); line-height:1.4; }}
.func {{ flex:1 1 auto; font-size:12.5px; color:var(--muted); line-height:1.62; }}
.rel {{ font-size:11.5px; color:var(--accent-ink); background:var(--accent-soft); padding:5px 8px; border-radius:6px; margin-top:8px; line-height:1.5; }}
.stat {{ font-size:11.5px; color:var(--ink); margin-top:8px; padding:6px 9px; background:var(--hover); border-radius:6px; line-height:1.6; }}
.stat b {{ color:var(--ink); font-weight:600; }}
.meta {{ margin-top:auto; padding-top:9px; font-size:11.5px; color:var(--muted); border-top:1px solid var(--line-2); }}
.badge {{ font-size:11px; padding:3px 10px; border-radius:20px; font-weight:600; }}
.badge.fresh {{ background:#e6f4ea; color:#137333; }}
.badge.warn {{ background:#fce8cf; color:#b45f06; }}
.badge.stale {{ background:#fce8e6; color:#9e2a2a; }}
.sop {{ background:var(--surface); border:1px solid var(--line); border-radius:8px; padding:8px 18px; margin:14px 0; }}
.step {{ display:flex; gap:14px; padding:14px 4px; border-bottom:1px solid var(--line-2); }}
.step:last-child {{ border-bottom:none; }}
.no {{ flex:none; width:26px; height:26px; line-height:26px; text-align:center; border-radius:50%; background:var(--accent); color:#fff; font-size:13px; font-weight:600; }}
.sd {{ font-size:13px; color:var(--muted); }}
.pnote {{ background:var(--accent-soft); border-left:4px solid var(--accent); padding:12px 14px; border-radius:0 8px 8px 0; font-size:13px; color:var(--ink); margin:12px 0; line-height:1.7; }}
code {{ background:var(--hover); color:var(--ink); padding:1px 6px; border-radius:5px; font-size:12.5px; }}
h2.sec {{ font-size:18px; margin:28px 0 12px; color:var(--ink); font-weight:500; }}
/* 数据流/更新时间/自检（从原 build_sections.py 合并） */
.relwrap {{ background:var(--surface); border:1px solid var(--line); border-radius:8px; padding:14px 18px; margin:12px 0 0; }}
.relhd {{ display:grid; grid-template-columns:1.4fr 2fr 2fr; gap:10px; padding:6px 10px; font-size:12px; color:var(--muted); border-bottom:1px solid var(--line-2); }}
.relrow {{ display:grid; grid-template-columns:1.4fr 2fr 2fr; gap:10px; padding:8px 10px; font-size:12.5px; border-bottom:1px dashed var(--line-2); align-items:start; }}
.relrow:last-child {{ border-bottom:none; }}
.reln {{ font-weight:600; color:var(--ink); }}
.relflow {{ color:var(--muted); }}
.relflow.out {{ color:#b45f06; }}
.tlwrap {{ background:var(--surface); border:1px solid var(--line); border-radius:8px; overflow:hidden; margin:12px 0 0; }}
.tl {{ display:flex; align-items:center; gap:14px; padding:12px 18px; border-bottom:1px solid var(--line-2); font-size:13px; }}
.tl:last-child {{ border-bottom:none; }}
.tt {{ flex:none; width:112px; font-weight:600; color:var(--accent); font-variant-numeric:tabular-nums; }}
.tn {{ flex:none; width:120px; color:var(--ink); font-weight:600; }}
.td {{ flex:1; color:var(--muted); }}
.tl.ok {{ background:var(--hover); }}
.tl.best {{ background:#e6f4ea; border-left:4px solid var(--green); }}
.tl.wait {{ background:var(--surface); }}
.tl.warn {{ background:#fce8cf; border-left:4px solid #f9ab00; }}
.tl.dead {{ background:#fce8e6; border-left:4px solid var(--red); }}
.ck {{ padding:8px 0 8px 4px; font-size:13px; color:var(--ink); border-bottom:1px dashed var(--line-2); }}
.ck:last-child {{ border-bottom:none; }}
footer {{ margin-top:40px; color:var(--muted); font-size:12px; text-align:center; }}
@media(max-width:1020px){{ .grid{{grid-template-columns:repeat(2,minmax(0,1fr));}} .card{{min-height:0;}} }}
@media(max-width:700px){{ .grid{{grid-template-columns:1fr;}} .card{{min-height:0;}} h1{{font-size:22px;}} .zone-t{{font-size:15px;}} .relhd,.relrow{{grid-template-columns:1fr;}} .tl{{flex-direction:column;align-items:flex-start;gap:4px;}} }}
</style>
</head>
<body>
<div class='wrap'>
{PORTAL_NAV}
<header class='top'>
  <h1>A股分析中心 · 总门户</h1>
  <div class='sub'>按功能区分五大模块：大盘与情绪 → 板块与资金 → 牛人与股东 → 选股与策略 → 数据与工具<br>共 {len(ZONES)} 个模块 · {_n_cards} 个页面入口，模块内卡片等宽排布、逐张标注数据新鲜度</div>
  <div class='updated'>门户重建于 {TODAY.strftime('%Y-%m-%d')} · 每张卡片标注功能、关联页面、数据截至日期</div>
</header>

{zones_html}

{ref_html}

<h2 class='sec'>📅 每日更新清单（精简 SOP）</h2>
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
print("    下一步：python quant/build_sections.py（重定向页）→ python quant/_apply_theme.py")
