# -*- coding: utf-8 -*-
"""生成「版块总览」页面 web/sections.html。

用途：
  1) 一次性说清 A股分析中心所有版块各自提供什么内容、数据从哪来、多久更新一次。
  2) 作为每日手动更新后的**自检页** —— 一眼看出哪个版块的数据日期落后。

设计要点：
  - 所有统计数字（记录数、板块数、主力行为分布…）均从 quant/ 下的数据文件实时读取，
    不用硬编码，因此每天重跑本页即自动同步最新口径。
  - 读取失败时降级显示 "—"，不影响页面生成。
  - 幂等注入 web/index.html 导航锚点（build_dashboards 重建索引后重跑本脚本即可补回）。
"""
import os
import re
import json
import datetime
from _nav import topnav

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(ROOT, "web")
MT = os.path.join(ROOT, "market-trend")
QUANT = os.path.join(ROOT, "quant")
OUT = os.path.join(WEB, "sections", "index.html")
TODAY = datetime.date.today()


# ---------------- 通用工具 ----------------
def parse_date(s):
    s = (s or "").strip()
    for fmt in ("%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.datetime.strptime(s, fmt).date()
        except Exception:
            pass
    return None


def latest(pattern, directory):
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


def fmt(d):
    return d.strftime("%Y-%m-%d") if d else "—"


def load_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def yi(x):
    """元 -> 亿元字符串"""
    try:
        return f"{float(x) / 1e8:,.2f}"
    except Exception:
        return "—"


# ---------------- 扫描各版块最新日期 ----------------
lhb_d, _ = latest(r"^lhb_(\d{4}-\d{2}-\d{2})\.html$", os.path.join(WEB, "lhb"))
sec_d, _ = latest(r"^sector-strength-(\d{8})\.html$", os.path.join(WEB, "sector"))
psy_d, _ = latest(r"^crowd-psychology-risk-radar-(\d{8})\.html$", os.path.join(WEB, "psychology"))
exec_d, _ = latest(r"^(\d{4}-\d{2}-\d{2})\.json$", os.path.join(QUANT, "exec_chg"))
blk_d, _ = latest(r"^(\d{4}-\d{2}-\d{2})\.json$", os.path.join(QUANT, "block_chg"))


# ---------------- 各版块实时统计 ----------------
def stat_lhb():
    """龙虎榜：股票数、游资介入度分布"""
    if not lhb_d:
        return {}
    d = load_json(os.path.join(QUANT, f"lhb_enriched_{lhb_d}.json"))
    if not d:
        return {}
    stocks = d.get("stocks", {})
    lv = {"高": 0, "中": 0, "低": 0}
    has_seat = 0
    for v in stocks.values():
        l = v.get("hotmoneyLevel") or "低"
        lv[l] = lv.get(l, 0) + 1
        if v.get("buySeats") or v.get("sellSeats"):
            has_seat += 1
    return {
        "count": len(stocks),
        "lv": lv,
        "hasSeat": has_seat,
        "sw1": sum(1 for v in stocks.values() if v.get("sw1")),
    }


def stat_exec():
    """高管增减持：记录数、股票数、增/减笔数、净额"""
    if not exec_d:
        return {}
    d = load_json(os.path.join(QUANT, "exec_chg", f"{exec_d}.json"))
    if not d:
        return {}
    recs = d.get("records", [])
    buy = sum(1 for r in recs if r.get("dir") == "增持")
    sell = sum(1 for r in recs if r.get("dir") == "减持")
    net = sum(float(r.get("amount", 0)) * (1 if r.get("dir") == "增持" else -1) for r in recs)
    return {
        "recs": len(recs),
        "stocks": d.get("stockCount") or len(set(r.get("code") for r in recs)),
        "buy": buy,
        "sell": sell,
        "net": net,
        "days": len(d.get("byDate", {})) if isinstance(d.get("byDate"), dict) else None,
    }


def stat_block():
    """大宗交易：笔数、股票数、成交额、平均折溢价、折价/溢价、机构买方"""
    if not blk_d:
        return {}
    d = load_json(os.path.join(QUANT, "block_chg", f"{blk_d}.json"))
    if not d:
        return {}
    return {
        "recs": d.get("count"),
        "stocks": d.get("stockCount"),
        "total": d.get("totalValue"),
        "avg": d.get("avgDiscount"),
        "disc": d.get("discCount"),
        "prem": d.get("premCount"),
        "inst": d.get("instBuyCount"),
    }


def stat_sector():
    """板块强度：优先读 summary（管道已算好的统计），缺失时再从 records 现算"""
    if not sec_d:
        return {}
    d = load_json(os.path.join(QUANT, "sector_daily", f"{sec_d}.json"))
    if not d:
        return {}
    sm = d.get("summary") or {}
    if sm.get("sectorCount"):
        return {
            "count": sm.get("sectorCount"),
            "ind": sm.get("industryCount"),
            "cpt": sm.get("conceptCount"),
            "up": sm.get("upCount"),
            "down": sm.get("downCount"),
            "act": sm.get("behavior") or {},
            "avg": sm.get("avgStrength"),
        }
    # ---- fallback：从 records 现算 ----
    rows = d.get("records") or []
    up = down = 0
    act = {"抢筹": 0, "建仓": 0, "洗盘": 0, "出货": 0}
    strengths = []
    for r in rows:
        try:
            cp = float(r.get("pctVal"))
            if cp > 0:
                up += 1
            elif cp < 0:
                down += 1
        except Exception:
            pass
        a = r.get("behavior")
        if a in act:
            act[a] += 1
        try:
            strengths.append(float(r.get("strengthVal")))
        except Exception:
            pass
    return {
        "count": len(rows),
        "ind": sum(1 for r in rows if r.get("kind") == "行业"),
        "cpt": sum(1 for r in rows if r.get("kind") == "概念"),
        "up": up,
        "down": down,
        "act": act,
        "avg": (sum(strengths) / len(strengths)) if strengths else None,
    }


s_lhb = stat_lhb()
s_exec = stat_exec()
s_blk = stat_block()
s_sec = stat_sector()


# ---------------- 版块定义 ----------------
def chips(items, cls="chip"):
    return "".join(f"<span class='{cls}'>{i}</span>" for i in items)


def stat_line(pairs):
    """pairs: [(label, value), ...] -> 指标条"""
    out = []
    for k, v in pairs:
        if v in (None, "", "—"):
            continue
        out.append(f"<div class='kv'><span class='k'>{k}</span><span class='v'>{v}</span></div>")
    return "<div class='kvs'>" + "".join(out) + "</div>" if out else ""


lhb_lv = s_lhb.get("lv", {})
lhb_stats = stat_line([
    ("龙虎榜个股", f"{s_lhb.get('count', '—')} 只"),
    ("游资介入度", f"高 {lhb_lv.get('高', 0)} / 中 {lhb_lv.get('中', 0)} / 低 {lhb_lv.get('低', 0)}"),
    ("含席位明细", f"{s_lhb.get('hasSeat', '—')} 只"),
    ("申万行业覆盖", f"{s_lhb.get('sw1', '—')} 只"),
])

exec_stats = stat_line([
    ("变动记录", f"{s_exec.get('recs', '—')} 条"),
    ("涉及股票", f"{s_exec.get('stocks', '—')} 只"),
    ("增持 / 减持", f"{s_exec.get('buy', '—')} / {s_exec.get('sell', '—')} 笔"),
    ("合计净额", (f"{yi(s_exec['net'])} 亿元" if s_exec.get("net") is not None else "—")),
    ("披露日跨度", f"{s_exec.get('days', '—')} 个" if s_exec.get("days") else "—"),
])

blk_stats = stat_line([
    ("成交笔数", f"{s_blk.get('recs', '—')} 笔"),
    ("涉及股票", f"{s_blk.get('stocks', '—')} 只"),
    ("合计成交额", (f"{yi(s_blk['total'])} 亿元" if s_blk.get("total") else "—")),
    ("平均折溢价", (f"{s_blk['avg']}%" if s_blk.get("avg") is not None else "—")),
    ("折价 / 溢价", f"{s_blk.get('disc', '—')} / {s_blk.get('prem', '—')} 笔"),
    ("机构买入", f"{s_blk.get('inst', '—')} 笔"),
])

sec_act = s_sec.get("act", {})
sec_stats = stat_line([
    ("板块总数", f"{s_sec.get('count', '—')} 个"
        + (f"（行业 {s_sec['ind']} + 概念 {s_sec['cpt']}）" if s_sec.get("ind") else "")),
    ("涨 / 跌", f"{s_sec.get('up', '—')} / {s_sec.get('down', '—')}"),
    ("主力行为", f"抢筹 {sec_act.get('抢筹', 0)} · 建仓 {sec_act.get('建仓', 0)} · "
                f"洗盘 {sec_act.get('洗盘', 0)} · 出货 {sec_act.get('出货', 0)}"),
    ("平均强度", f"{s_sec['avg']:.3f}" if s_sec.get("avg") is not None else "—"),
])

SECTIONS = [
    {
        "ic": "🗺️", "name": "每日总览", "href": "../market/index.html",
        "date": fmt(lhb_d), "badge": freshness(lhb_d),
        "desc": "交易日盘后第一眼：大盘看板（指数 / 涨跌家数 / 涨停梯队 / 资金流向 / 板块热度）一屏总览。",
        "modules": chips([
            "指数面板", "涨跌家数与成交额", "涨停梯队（含连板）",
            "资金流向（板块 / 个股）", "板块热度 Top", "当日要闻",
        ]),
        "sources": chips(["data_market_overview", "data_hot(board_hot)", "data_quote", "limitup"]),
        "cadence": "每个交易日必跑",
        "cadence_cls": "must",
        "notes": "build_dashboards.py 一并产出，与龙虎榜主看板同源。",
        "files": ["web/market/index.html", "web/market/hotmoney.html"],
        "stats": "",
    },
    {
        "ic": "🐉", "name": "龙虎榜主看板", "href": "../lhb/lhb.html",
        "date": fmt(lhb_d), "badge": freshness(lhb_d),
        "desc": "当日盘后龙虎榜全景：从大盘环境一路下钻到每只上榜个股的席位与游资标签。",
        "modules": chips([
            "大盘概览（指数/成交/涨跌分布）", "板块热度", "连板梯队（多口径）",
            "龙虎榜全榜（按净买入排序）", "游资介入度 + 买卖方席位明细",
            "申万一级 + 二级行业与涨跌幅", "窗口收益 alpha（vs 大盘）", "当日要闻",
        ]),
        "sources": chips([
            "data_market_overview", "data_sector(board_hot)", "data_quote",
            "data_lhb(全市场)", "data_lhb(codes=明细)", "data_hot(news)", "data_changedist",
        ]),
        "cadence": "每个交易日必跑",
        "cadence_cls": "must",
        "notes": "支持 date 参数回溯，漏跑可补建。估值口径天然滞后 1 个交易日（接口特性）。",
        "files": ["web/market/index.html", "web/lhb/lhb.html", "web/market/hotmoney.html",
                  f"web/lhb/lhb_{fmt(lhb_d)}.html", f"web/market/status_{fmt(lhb_d)}.html"],
        "stats": lhb_stats,
    },
    {
        "ic": "💼", "name": "高管增减持（董监高）", "href": "../exec/index.html",
        "date": fmt(exec_d), "badge": freshness(exec_d),
        "desc": "全市场董监高持股变动的窗口扫描（近 1 个月），按金额排序看谁在真金白银买、谁在跑。",
        "modules": chips([
            "概览（增/减笔数、净额、涉及股票数）", "行业分布（申万一级，按金额）",
            "最新披露日", "增持榜 Top60", "减持榜 Top60", "个股聚合 Top80（按净额）", "全部明细",
        ]),
        "sources": chips(["tool_event(manager_sharechg)", "data_quote(补涨跌幅)",
                          "_code2industry", "_name2sw2"]),
        "cadence": "每个交易日必跑",
        "cadence_cls": "must",
        "notes": "T+1 口径：接口快照日为前一交易日，公司晚间公告次日才纳入。按 DeclareDate 可切严格每日口径。",
        "files": ["web/exec/index.html", f"quant/exec_chg/{fmt(exec_d)}.json"],
        "stats": exec_stats,
    },
    {
        "ic": "🧾", "name": "大宗交易", "href": "../block/archive.html",
        "date": fmt(blk_d), "badge": freshness(blk_d),
        "desc": "全市场大宗交易逐笔扫描（T 日口径）：看谁在折价出货、谁在溢价接盘、机构席位在买还是在卖。",
        "modules": chips([
            "概览（笔数/股票数/成交额/平均折溢价/折价·溢价/机构买入）",
            "个股聚合（按成交额）", "逐笔明细（按成交额）",
            "筛选：全部 / 机构买入 / 溢价成交", "每日归档 + 日期导航",
        ]),
        "sources": chips(["tool_event(block_past_30)", "data_quote(补涨跌幅)"]),
        "cadence": "每个交易日必跑",
        "cadence_cls": "must",
        "notes": "⚠ <code>limit</code> 必须给足：默认 500 会截断当日数据（实测 09-04 当日 500 档仅 32 条、3000 档 158 条）。"
                 "折溢价相对当日收盘价，正=折价、负=溢价。",
        "files": ["web/block/archive.html", "web/block/index.html", f"web/block/block_{fmt(blk_d)}.html",
                  f"quant/block_chg/{fmt(blk_d)}.json"],
        "stats": blk_stats,
    },
    {
        "ic": "🔥", "name": "板块强度", "href": "../sector/index.html",
        "date": fmt(sec_d), "badge": freshness(sec_d),
        "desc": "行业 + 概念全板块的主力资金画像，用「强度」和「主力行为」判断资金在抢筹还是在出货。",
        "modules": chips([
            "每日全板块榜（强度排序）", "强势板块 Top10", "暗盘资金流入 Top10",
            "主力行为四档（抢筹/建仓/洗盘/出货）", "趋势看板（跨交易日累积）", "日期索引",
        ]),
        "sources": chips(["data_sector(kind=industry)", "data_sector(kind=concept)"]),
        "cadence": "每个交易日必跑 · 不可回溯",
        "cadence_cls": "danger",
        "notes": "⚠ date 参数被接口忽略，只返回最新快照。次日开盘即被覆盖，漏跑一天永久断档，趋势看板会留真空。",
        "files": ["web/sector/index.html", "web/sector/trend.html",
                  f"web/sector/sector-strength-{sec_d.strftime('%Y%m%d') if sec_d else ''}.html"],
        "stats": sec_stats,
    },
    {
        "ic": "🧠", "name": "群体心理风险雷达", "href": "../psychology/index.html",
        "date": fmt(psy_d), "badge": freshness(psy_d),
        "desc": "从群体行为角度给市场做「心理体检」：情绪处在周期哪一段、哪些认知偏差正在发酵、风险怎么分层。",
        "modules": chips([
            "情绪周期定位", "行为偏差热力图", "风险雷达",
            "关键证据表", "风险分层", "下个交易日展望", "跨日趋势索引",
        ]),
        "sources": chips(["westock 当日快照", "人工结构化研判（_build_MMDD.py 内嵌数据）"]),
        "cadence": "按需更新（独立子系统）",
        "cadence_cls": "opt",
        "notes": "每个交易日一份单篇 HTML，数据内嵌在 market-trend/_build_MMDD.py 脚本里，非从落盘 JSON 读取，故需逐日新建脚本。",
        "files": ["web/psychology/index.html", f"web/psychology/crowd-psychology-risk-radar-{psy_d.strftime('%Y%m%d') if psy_d else ''}.html"],
        "stats": "",
    },
    {
        "ic": "🏆", "name": "行业最强榜（全市场）", "href": "../shareholder/2026-q2-industry-elite.html",
        "date": "2026-06-30", "badge": ("定期", "warn"),
        "desc": "全市场 5500+ 只 A 股定期报告股东全量解析，按申万行业找出各自最强的自然人 / 私募 / 公募。",
        "modules": chips([
            "31 个申万行业榜单", "自然人（牛散）Top20 / 行业",
            "私募 Top20 / 行业", "公募 Top20 / 行业",
            "资金-估值四象限", "胜率 / 均涨统计",
        ]),
        "sources": chips(["定期报告十大股东（季报/中报/年报）", "申万行业分类"]),
        "cadence": "定期报告发布后重跑（非每日）",
        "cadence_cls": "opt",
        "notes": "当前为中报口径（截至 2026-06-30）。季报/年报披露季需全量重跑，日常更新不涉及。",
        "files": ["web/shareholder/2026-q2-industry-elite.html"],
        "stats": "",
    },
    {
        "ic": "🌟", "name": "行业知名 Top20 私募 / 牛散", "href": "../shareholder/top-elite.html",
        "date": "2026-09-04", "badge": ("策划", "warn"),
        "desc": "按行业知名度与历史业绩策划的私募 / 牛散 Top20 玩家图谱（非短期收益胜率），并交叉标注与高管增减持共现的知名主体。",
        "modules": chips([
            "私募 Top20（头部机构）", "牛散 Top20（知名大户）",
            "行业聚焦 / 投资风格", "高管增减持共现重点标注",
        ]),
        "sources": chips(["公开信息整理", "Q2 十大股东 + 高管增减持交叉核对"]),
        "cadence": "按需更新",
        "cadence_cls": "opt",
        "notes": "口径为行业知名度与公开业绩，非收益胜率；不构成投资建议。",
        "files": ["web/shareholder/top-elite.html"],
        "stats": "",
    },
    {
        "ic": "📈", "name": "股票增持信号扫描", "href": "../shareholder/stock-accumulation.html",
        "date": "2026-06-30", "badge": ("定期", "warn"),
        "desc": "全市场 5544 只中报十大流通股东变动逐只扫描：统计增持 / 减持家数与股数，筛出「增持多于减持」并高亮知名私募 / 牛散加仓标的。",
        "modules": chips([
            "全市场 5544 只逐只扫描", "增持 / 减持家数与股数统计",
            "知名私募 / 牛散加仓高亮", "净增持额排序",
        ]),
        "sources": chips(["2026 中报十大流通股东", "知名主体名单匹配"]),
        "cadence": "定期报告发布后重跑（非每日）",
        "cadence_cls": "opt",
        "notes": "单季股东数据无法单列「新进」，只能看增持 / 减持方向；不构成投资建议。",
        "files": ["web/shareholder/stock-accumulation.html"],
        "stats": "",
    },
    {
        "ic": "🩺", "name": "知名加仓 · 量价健康度过滤", "href": "../shareholder/known-accumulation-health.html",
        "date": "2026-09-04", "badge": ("定期", "warn"),
        "desc": "在上游 50 只知名私募 / 牛散加仓股上叠加技术面二次过滤：趋势结构 30 + 动量健康 25 + 量价配合 20 + 相对位置 25，纯量价口径打分。",
        "modules": chips([
            "趋势结构 30（MA20/60/120）", "动量健康 25（RSI_12 + 60 日涨幅）",
            "量价配合 20（换手率 + 量比）", "相对位置 25（52 周位越低越高分）",
            "机构信号仅作排序加成", "✓ 矩阵 + 表头排序",
        ]),
        "sources": chips(["westock data_technical（MA / RSI）", "westock data_quote（换手 / 量比 / 52 周位）", "2026 中报十大流通股东"]),
        "cadence": "定期报告发布后重跑；量价快照随扫描日更新",
        "cadence_cls": "opt",
        "notes": "规则打分、不荐个股；「行业订单 / 业绩可验证」「瓶颈环节」未纳入评分，需自行核验。技术面为单一时点快照。",
        "files": ["web/shareholder/known-accumulation-health.html"],
        "stats": "",
    },
    {
        "ic": "🎯", "name": "牛人追踪（索引入口）", "href": "../shareholder/tracker.html",
        "date": "2026-Q2", "badge": ("季频", "warn"),
        "desc": "把「厉害的人」做成可索引、可跟随的清单：全市场 5500+ 只中报十大股东 → 牛散/私募/公募 索引；龙虎榜营业部 → 游资席位。",
        "modules": chips([
            "牛散 2640 / 私募 939 / 公募 867", "游资席位 833（龙虎榜聚合）",
            "姓名 + 行业筛选", "按持仓家数 / 增仓力度 / 持股数排序",
            "个股持仓明细 + 动向·加仓/减仓", "关注★ + 代号映射 localStorage",
            "纯本机不上传",
        ]),
        "sources": chips(["2026 中报十大股东 + 十大流通股东", "Q2↔Q1 环比（holdChange）", "龙虎榜营业部（08-17~09-09 活跃度）"]),
        "cadence": "季频更新（中报 / 季报披露季重跑）",
        "cadence_cls": "opt",
        "notes": "「跟随」核心信号来自 holdChange 环比：正=加仓↑ 负=减仓↓。localStorage 关注与代号映射纯本机。",
        "files": ["web/shareholder/tracker.html", "web/shareholder/data/person_index.json"],
        "stats": "",
    },
    {
        "ic": "🔍", "name": "个股调研（三周期）", "href": "../research/index.html",
        "date": "2026-09-04", "badge": ("季频", "warn"),
        "desc": "单只 A 股「短线 / 中线 / 长线」三周期调研：单季拆分、内部人行为对照、板块资金确认、七条标准打分（不荐个股）。",
        "modules": chips([
            "短线：单季拆分 + 主力意图", "中线：基本面周期 + 内部人对照",
            "长线：行业订单 / 业绩可验证", "板块资金确认",
            "七条标准逐条打分 + 验证指标",
        ]),
        "sources": chips(["westock data_finance", "data_quote", "data_technical", "中报十大股东", "板块强度"]),
        "cadence": "按需更新（深度调研，单只一篇 HTML）",
        "cadence_cls": "opt",
        "notes": "上游筛选：板块强度 / 牛人追踪 / 健康度过滤。调研结论只输出板块与交易规则，不给个股推荐。",
        "files": ["web/research/index.html", "web/research/research-*.html"],
        "stats": "",
    },
    {
        "ic": "🎯", "name": "个股信号池（次日建仓候选）", "href": "../picks/index.html",
        "date": (json.load(open(os.path.join(ROOT, "quant", "picks", "history.json"), encoding="utf-8"))[-1]["date"]
                 if os.path.exists(os.path.join(ROOT, "quant", "picks", "history.json")) else "—"),
        "badge": ("每日", "must"),
        "desc": "把「中报增减持 + 高管增减持 + 大宗交易」三路信号合流打分，叠加当日量价确认，输出次日建仓候选池与逐只交易计划（进场区间 / 止损 / 目标位 / 盈亏比 / 建议仓位），每日归档并自动回填次日表现统计胜率。",
        "modules": chips([
            "三路信号聚合（中报 25 + 高管 20 + 大宗 20）",
            "量价健康 25（趋势 10 / 量能 5 / 动量 5 / 位置 5）",
            "风险扣分 10（净减持 / 机构卖出 / 高折价 / 高位 / 超买）",
            "档位 A~D 与仓位（A≥70 八到十成·B 60~70 五到七成·C 50~60 三成·D 不建仓）",
            "逐只交易计划（进场 / 止损 / 目标一·二 / 盈亏比）",
            "历史归档 + 次日表现自动回填（触目标 / 触止损统计）",
        ]),
        "sources": chips([
            "westock data_quote（现价 / 换手 / 量比 / 52 周位 / PE / PB）",
            "westock data_technical（MA5/10/20/60、MACD、RSI12、KDJ、BOLL）",
            "quant/exec_chg/*.json（近 20 日高管增减持）",
            "quant/block_chg/*.json（近 20 日大宗交易）",
            "quant/q2_full/_merged_shareholder.json（2026-Q2 十大流通股东环比）",
        ]),
        "cadence": "每个交易日盘后（20:00 后），与每日更新 SOP 同步；两步：gen_picks.py → 拉行情 → build_picks.py",
        "cadence_cls": "must",
        "notes": "中报数据截至 2026-06-30 存在滞后；大宗与高管为当日披露快照。买卖点由固定公式产出，不含基本面判断，务必自行核验并严格执行止损（单票亏损不超过总资金 2%）。本页为规则化输出，不构成投资建议。",
        "files": ["web/picks/index.html", "web/picks/pick_*.html", "quant/picks/*.json", "quant/gen_picks.py", "quant/build_picks.py"],
        "stats": "",
    },
    {
        "ic": "🔁", "name": "做T池（可反复做T候选）", "href": "../tplus/index.html",
        "date": (json.load(open(os.path.join(ROOT, "quant", "tplus", "history.json"), encoding="utf-8"))[-1]["date"]
                 if os.path.exists(os.path.join(ROOT, "quant", "tplus", "history.json")) else "—"),
        "badge": ("每日", "must"),
        "desc": "从「机构底仓池」（公募持股≥5% 或 社保/养老/险资≥2家）中筛出高波动 + 高流动性 + 区间震荡的标的，"
                "按顶级机构常用的网格交易 / 均值回归 / 底仓+卫星仓方法，给出网格 5 档价位、波段买卖区、止损与仓位建议。",
        "modules": chips([
            "机构底仓池 848 只候选（公募重仓 + 顶级机构）",
            "硬门槛：非ST · 流通市值 20~1200亿 · 换手 2%~18% · 日振幅 ≥3%",
            "做T适合度 5 维评分（波动 30 / 流动性 20 / 区间结构 25 / 机构 15 / 稳定 10 − 风险）",
            "网格 5 档价位 + 波段买卖区 + 止损（逐只操作手册）",
            "档位 A≥80 / B 70~80 / C 60~70（网格型 / 波段型分类）",
            "历史归档（每日入选数与类型分布）",
        ]),
        "sources": chips([
            "westock data_quote（振幅 / 换手 / 量比 / 市值 / 52周位）",
            "westock data_kline（60 日前复权，算箱体 / ATR / MA / BOLL / RSI）",
            "quant/q2_full/_merged_shareholder.json（公募 / 社保 / 险资 持仓）",
            "quant/picks/events_unlock|reduce_*.json（解禁 / 减持排雷）",
        ]),
        "cadence": "每个交易日盘后，与每日更新 SOP 同步；两步：gen_tplus.py → 拉行情/K线 → build_tplus.py",
        "cadence_cls": "must",
        "notes": "做T依托底仓（A股 T+1），无底仓不适用；网格/波段价位为规则化输出，务必自行核验。纪律：破箱体下沿无条件清仓，单次做T亏损 ≤ 总资金 0.5%。本页不构成投资建议。",
        "files": ["web/tplus/index.html", "web/tplus/tplus-*.html", "quant/tplus/*.json", "quant/gen_tplus.py", "quant/build_tplus.py"],
        "stats": "",
    },
    {
        "ic": "🗄️", "name": "数据中心", "href": "../db/index.html",
        "date": TODAY.strftime("%Y-%m-%d"), "badge": ("实时", "fresh"),
        "desc": "全模块历史数据查询页：龙虎榜 / 高管增减持 / 大宗 / 板块强度 / 涨停梯队 / 热搜 / 新闻 / 大盘指标 9 个表，支持模块切换、日期区间、搜索、专项筛选、排序、分页。",
        "modules": chips([
            "9 个数据模块（exec / block / lhb / lhb_seat / sector / limitup / board_hot / news / market_metric）",
            "列式压缩 JSON + 按月分片",
            "模块切换 + 日期区间 + 全文搜索",
            "专项筛选 + 排序 + 分页",
        ]),
        "sources": chips(["quant/db/stocks.db（SQLite 9 表）", "quant/db_export.py → web/data/{module}_YYYY-MM.json"]),
        "cadence": "实时（每次手动更新后由 db_update.py 同步）",
        "cadence_cls": "must",
        "notes": "历史长期留存，INSERT OR REPLACE 幂等。所有上方页面的历史数据源。",
        "files": ["web/db/index.html", "web/data/*.json", "quant/db/stocks.db"],
        "stats": "",
    },
]

sec_html = ""
for s in SECTIONS:
    btxt, bcls = s["badge"]
    files_html = "".join(f"<code>{f}</code>" for f in s["files"] if f)
    sec_html += f"""
<div class='sec'>
  <div class='sechead'>
    <span class='sic'>{s['ic']}</span>
    <div class='stitle'>
      <a href='{s['href']}'>{s['name']}</a>
    </div>
    <span class='badge {bcls}'>{btxt}</span>
    <span class='bdate'>数据截至 {s['date']}</span>
  </div>
  <div class='sdesc'>{s['desc']}</div>
  {s['stats']}
  <div class='row'><div class='lab'>内容模块</div><div class='val'>{s['modules']}</div></div>
  <div class='row'><div class='lab'>数据来源</div><div class='val'>{s['sources']}</div></div>
  <div class='row'><div class='lab'>更新节奏</div><div class='val'>
    <span class='cad {s['cadence_cls']}'>{s['cadence']}</span></div></div>
  <div class='row'><div class='lab'>口径要点</div><div class='val note2'>{s['notes']}</div></div>
  <div class='row'><div class='lab'>产出文件</div><div class='val files'>{files_html}</div></div>
</div>"""

# ---------------- 全站页面索引（按功能分组 + 关系图） ----------------
INDEX_ZONES = [
    {
        "ic": "📊", "t": "每日总览（今天该看什么）",
        "pages": [
            ("🗺️ 每日总览", "../market/index.html", "大盘看板一屏总览"),
            ("🐉 龙虎榜主看板", "../lhb/lhb.html", "异动 / 机构榜 / 游资胜率 / 共振"),
            ("🔥 板块强度", "../sector/index.html", "板块资金 + 主力行为 + 估值分位"),
        ],
    },
    {
        "ic": "💰", "t": "资金动向（谁在买 / 卖）",
        "pages": [
            ("💼 高管增减持", "../exec/index.html", "内部人董监高持股变动"),
            ("🧾 大宗交易", "../block/archive.html", "大资金折价 / 溢价调仓"),
        ],
    },
    {
        "ic": "🧠", "t": "市场情绪",
        "pages": [
            ("🧠 群体心理风险雷达", "../psychology/index.html", "情绪周期 + 偏差 + 风险分层"),
        ],
    },
    {
        "ic": "👑", "t": "牛人与股东（谁在持仓）",
        "pages": [
            ("🎯 牛人追踪（索引）", "../shareholder/tracker.html", "牛散 / 私募 / 公募 / 游资 索引 + 增减持"),
            ("🏆 行业最强榜", "../shareholder/2026-q2-industry-elite.html", "31 行业 × 牛散 / 私募 / 公募 Top20"),
            ("🌟 玩家图谱", "../shareholder/top-elite.html", "按知名度策划的 Top20 + 高管共现"),
            ("📈 增持信号扫描", "../shareholder/stock-accumulation.html", "全市场 5544 只增持 / 减持扫描"),
            ("🩺 健康度过滤", "../shareholder/known-accumulation-health.html", "上游 50 只加技术面四维打分"),
        ],
    },
    {
        "ic": "🎯", "t": "个股信号池（次日建仓候选）",
        "pages": [
            ("🎯 个股信号池", "../picks/index.html", "三路信号合流 → 候选 + 买卖点 + 胜率归档"),
            ("📉 信号池回测", "../picks/backtest.html", "档位 × T+1/T+3/T+5 胜率与收益统计"),
        ],
    },
    {
        "ic": "🔍", "t": "单只深挖",
        "pages": [
            ("🔍 个股调研", "../research/index.html", "短线 / 中线 / 长线 三周期"),
        ],
    },
    {
        "ic": "🗄️", "t": "数据与工具",
        "pages": [
            ("🗄️ 数据中心", "../db/index.html", "9 模块历史查询"),
            ("📦 版块总览（本页）", "index.html", "自检 + 全站索引"),
        ],
    },
]

def _index_zones_html():
    out = []
    for z in INDEX_ZONES:
        page_html = "".join(
            f"<a class='pg' href='{h}'><span class='pgn'>{n}</span>"
            f"<span class='pgd'>{d}</span></a>"
            for n, h, d in z["pages"]
        )
        out.append(
            f"<div class='izone'>"
            f"<div class='izh'><span class='izi'>{z['ic']}</span>"
            f"<span class='izt'>{z['t']}</span></div>"
            f"<div class='ipages'>{page_html}</div>"
            f"</div>"
        )
    return "".join(out)

RELATIONSHIPS = [
    ("📊 每日总览", "汇总：龙虎榜 + 板块强度 + 高管增减持 + 大宗", "→ 资金动向 / 市场情绪"),
    ("🐉 龙虎榜主看板", "席位明细 → 牛人追踪·游资席位", "← 数据中心（查历史席位）"),
    ("🔥 板块强度", "行业过滤 → 行业最强榜 / 牛人追踪", "← 数据中心（查历史板块）"),
    ("💼 高管增减持", "共现主体 → 玩家图谱", "← 数据中心（查历史增减持）"),
    ("🧾 大宗交易", "与高管增减持互补（折价+内部人）", "← 数据中心"),
    ("🧠 群体心理雷达", "情绪外化 → 龙虎榜 / 板块强度", "← 数据中心（趋势跨日）"),
    ("🎯 个股信号池", "← 中报 / 高管增减持 / 大宗交易（三路信号）+ 量价确认", "→ 个股调研（选中后深挖）· → 归档回看胜率"),
    ("🎯 牛人追踪（索引）", "← 板块强度（按行业筛） / 高管（按主体筛）", "→ 数据中心（查历年）"),
    ("🏆 行业最强榜", "→ 牛人追踪（按行业版入口） / 玩家图谱", "← 数据中心"),
    ("🌟 玩家图谱", "→ 高管共现 / 牛人追踪", "← 数据中心"),
    ("📈 增持信号扫描", "→ 健康度过滤（技术面）", "← 数据中心"),
    ("🩺 健康度过滤", "← 增持信号扫描（上游 50 只）", "→ 个股调研（最终单只）"),
    ("🔍 个股调研", "← 板块强度 / 牛人追踪 / 健康度（筛选上游）", "→ 数据中心（查历年）"),
    ("🗄️ 数据中心", "← 所有上方页面的历史数据源", ""),
    ("📦 版块总览", "本门户卡片的数据来源说明页", ""),
]
rel_html = "".join(
    f"<div class='relrow'><div class='reln'>{n}</div>"
    f"<div class='relflow'>{f}</div><div class='relflow out'>{o}</div></div>"
    for n, f, o in RELATIONSHIPS
)

# ---------------- 更新时间建议 ----------------
TIMELINE = [
    ("15:00", "收盘", "行情、涨跌停、板块资金定格", "ok"),
    ("15:30", "盘后数据可拉", "此时可开始跑，但龙虎榜未公布、大盘统计未聚合", "wait"),
    ("18:00 前后", "龙虎榜陆续公布", "沪深交易所盘后披露，个别标的可能延后", "wait"),
    ("19:30", "最早可靠窗口", "实测：龙虎榜 19:xx 与 20:56 复拉均为 62 只，已定稿", "ok"),
    ("20:00–21:00", "★ 推荐时段", "大盘统计聚合定稿（实测 20:00 与 20:56 涨跌分布完全一致）", "best"),
    ("次日 08:00–09:15", "补救窗口", "板块强度最后机会；高管增减持可纳入前夜公告", "warn"),
    ("次日 09:30", "✕ 死线", "开盘后板块快照被覆盖，T 日板块强度永久不可补", "dead"),
]
tl_html = "".join(
    f"<div class='tl {c}'><div class='tt'>{t}</div><div class='tn'>{n}</div><div class='td'>{d}</div></div>"
    for t, n, d, c in TIMELINE
)

CHECKS = [
    "龙虎榜：market_overview / board_hot / quotes / limitup / lhb + news 全部落盘",
    "龙虎榜明细 3 批 + lhb_enriched_{DATE}.json + 申万涨跌幅映射刷新",
    "<b>板块强度</b>（不可跳过）：industry + concept 快照 → gen_sector_raw.py → run_daily_sector.py",
    "高管增减持：tool_event + data_quote → gen_exec.py → build_exec.py",
    "心理雷达（按需）",
    "build_portal.py → build_sections.py（本页）→ _push_lhb.py 推送",
    "合规扫描：产物内不得出现个人持有信息、账户盈亏、自下而上选股等敏感内容（关键词清单见项目约定）",
]
ck_html = "".join(
    f"<div class='ck'><span class='box'></span>{c}</div>" for c in CHECKS
)

html = f"""<!DOCTYPE html>
<html lang='zh-CN'>
<head>
<meta charset='UTF-8'>
<meta name='viewport' content='width=device-width,initial-scale=1.0'>
<title>版块总览 · A股分析中心</title>
<style>
* {{ box-sizing:border-box; }}
body {{ margin:0; background:#f5f6f8; color:#1c2430;
  font-family:"PingFang SC","Microsoft YaHei","Hiragino Sans GB",sans-serif; line-height:1.7; }}
.wrap {{ max-width:1080px; margin:0 auto; padding:36px 22px 70px; }}
header.top {{ border-bottom:3px solid #1f4e79; padding-bottom:16px; margin-bottom:8px; }}
h1 {{ font-size:27px; margin:0 0 6px; letter-spacing:.5px; }}
.sub {{ color:#5a6573; font-size:14px; }}
.updated {{ color:#7b8794; font-size:12.5px; margin:8px 0 24px; }}
h2 {{ font-size:20px; margin:38px 0 14px; padding-left:12px; border-left:5px solid #1f4e79; }}
.sec {{ background:#fff; border:1px solid #e3e7ec; border-radius:14px; padding:20px 22px;
  margin-bottom:16px; box-shadow:0 1px 4px rgba(20,30,50,.04); }}
.sechead {{ display:flex; align-items:center; gap:12px; flex-wrap:wrap;
  padding-bottom:12px; border-bottom:1px solid #eef1f4; }}
.sic {{ font-size:26px; }}
.stitle a {{ font-size:18px; font-weight:700; color:#1f4e79; text-decoration:none; }}
.stitle a:hover {{ text-decoration:underline; }}
.bdate {{ margin-left:auto; font-size:12.5px; color:#7b8794; }}
.badge {{ font-size:11px; padding:3px 10px; border-radius:20px; font-weight:700; }}
.badge.fresh {{ background:#e6f6ee; color:#128a52; }}
.badge.warn {{ background:#fdf3e0; color:#b7791f; }}
.badge.stale {{ background:#fdecea; color:#c0392b; }}
.sdesc {{ font-size:13.5px; color:#4a5563; margin:12px 0 4px; }}
.kvs {{ display:flex; flex-wrap:wrap; gap:10px; margin:12px 0 4px; }}
.kv {{ background:#f7f9fc; border:1px solid #e6ecf3; border-radius:8px; padding:6px 12px; font-size:12.5px; }}
.kv .k {{ color:#7b8794; margin-right:8px; }}
.kv .v {{ font-weight:700; color:#1f4e79; }}
.row {{ display:flex; gap:14px; padding:9px 0; border-bottom:1px dashed #eef1f4; font-size:13px; }}
.row:last-child {{ border-bottom:none; }}
.lab {{ flex:none; width:82px; color:#7b8794; font-size:12.5px; padding-top:2px; }}
.val {{ flex:1; }}
.chip {{ display:inline-block; background:#eef4fa; color:#2c5282; border-radius:6px;
  padding:3px 9px; margin:3px 5px 3px 0; font-size:12px; }}
.note2 {{ color:#6b4f2a; font-size:12.5px; background:#fffaf0; padding:8px 12px;
  border-left:3px solid #b7791f; border-radius:0 6px 6px 0; }}
.cad {{ display:inline-block; font-size:12px; font-weight:700; padding:3px 10px; border-radius:6px; }}
.cad.must {{ background:#e6f6ee; color:#128a52; }}
.cad.danger {{ background:#fdecea; color:#c0392b; }}
.cad.opt {{ background:#eef1f4; color:#5a6573; }}
.files code {{ display:inline-block; background:#eef4fa; color:#1f4e79; padding:2px 7px;
  border-radius:5px; font-size:11.5px; margin:3px 5px 3px 0; }}
.tlwrap {{ background:#fff; border:1px solid #e3e7ec; border-radius:14px; overflow:hidden; }}
.tl {{ display:flex; align-items:center; gap:14px; padding:12px 18px; border-bottom:1px solid #eef1f4; font-size:13px; }}
.tl:last-child {{ border-bottom:none; }}
.tt {{ flex:none; width:112px; font-weight:700; color:#1f4e79; font-variant-numeric:tabular-nums; }}
.tn {{ flex:none; width:120px; color:#1c2430; font-weight:600; }}
.td {{ flex:1; color:#5a6573; }}
.tl.ok {{ background:#f7fcf9; }}
.tl.best {{ background:#eaf6ef; border-left:4px solid #128a52; }}
.tl.wait {{ background:#fcfcfd; }}
.tl.warn {{ background:#fffaf0; border-left:4px solid #b7791f; }}
.tl.dead {{ background:#fdecea; border-left:4px solid #c0392b; }}
.ck {{ padding:8px 0 8px 4px; font-size:13px; border-bottom:1px dashed #eef1f4; }}
.ck:last-child {{ border-bottom:none; }}
.box {{ display:inline-block; width:14px; height:14px; border:2px solid #b9c3cf; border-radius:4px;
  margin-right:10px; vertical-align:-2px; }}
.note {{ background:#fffaf0; border-left:4px solid #b7791f; padding:12px 16px;
  border-radius:0 8px 8px 0; font-size:13.5px; color:#6b4f2a; margin:14px 0; }}
/* 全站索引（按功能分组） */
.idxwrap {{ background:#fff; border:1px solid #e3e7ec; border-radius:14px;
  padding:18px 22px; margin-bottom:18px; box-shadow:0 1px 4px rgba(20,30,50,.04); }}
.izone {{ margin:10px 0 14px; padding-bottom:10px; border-bottom:1px dashed #eef1f4; }}
.izone:last-child {{ border-bottom:none; }}
.izh {{ display:flex; align-items:center; gap:10px; margin-bottom:8px; }}
.izi {{ font-size:20px; }}
.izt {{ font-size:15px; font-weight:700; color:#1f4e79; }}
.ipages {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:8px; }}
.pg {{ display:flex; flex-direction:column; gap:2px; background:#f7f9fc; border:1px solid #e6ecf3;
  border-radius:8px; padding:8px 12px; text-decoration:none; color:inherit; transition:.15s; }}
.pg:hover {{ border-color:#2b6cb0; background:#eef4fa; }}
.pgn {{ font-size:13px; font-weight:700; color:#1f4e79; }}
.pgd {{ font-size:11.5px; color:#5a6573; line-height:1.4; }}
/* 关系图 */
.relwrap {{ background:#fff; border:1px solid #e3e7ec; border-radius:14px;
  padding:14px 18px; margin-bottom:18px; box-shadow:0 1px 4px rgba(20,30,50,.04); }}
.relhd {{ display:grid; grid-template-columns:1.4fr 2fr 2fr; gap:10px; padding:6px 10px;
  font-size:12px; color:#7b8794; border-bottom:1px solid #eef1f4; }}
.relrow {{ display:grid; grid-template-columns:1.4fr 2fr 2fr; gap:10px; padding:8px 10px;
  font-size:12.5px; border-bottom:1px dashed #eef1f4; align-items:start; }}
.relrow:last-child {{ border-bottom:none; }}
.reln {{ font-weight:700; color:#1f4e79; }}
.relflow {{ color:#5a6573; }}
.relflow.out {{ color:#8a5a1e; }}
footer {{ margin-top:46px; padding-top:18px; border-top:1px solid #e3e7ec;
  font-size:12px; color:#7b8794; }}
.topnav {{ font-size:13px; margin-bottom:14px; }}
.topnav a {{ color:#b8893b; text-decoration:none; margin-right:14px; padding:4px 12px; border:1px solid rgba(184,137,59,.35); border-radius:20px; }}
.topnav a:hover {{ background:rgba(184,137,59,.10); }}
</style>
</head>
<body>
<div class='wrap'>
{topnav("sections")}

<header class='top'>
  <h1>📦 版块总览</h1>
  <div class='sub'>A股分析中心全部版块：内容清单 / 数据来源 / 更新节奏 / 当前数据日期</div>
  <div class='updated'>生成于 {TODAY.strftime('%Y-%m-%d')} · 统计数字实时读取自 quant/ 下的数据文件</div>
</header>

<h2>🧭 全站页面索引（按功能分组）</h2>
<div class='idxwrap'>
{_index_zones_html()}
</div>

<h2>🔗 页面关系（数据流 / 上下游）</h2>
<div class='relwrap'>
  <div class='relhd'><div>页面</div><div>← 输入 / 依赖</div><div>输出 / 走向 →</div></div>
  {rel_html}
</div>
<div class='note'><b>阅读建议：</b>从「每日总览」开始扫一眼全局 → 「资金动向 / 市场情绪」看定性 → 「牛人与股东」按行业筛 → 「单只深挖」拿到具体票 → 全程所有数据都能在「数据中心」查历史。</div>

<h2>⏰ 每日更新时间建议</h2>
<div class='tlwrap'>{tl_html}</div>
<div class='note'>
<b>推荐：交易日当晚 20:00–21:00 手动触发一次全量更新。</b>
此时龙虎榜已公布完毕、大盘统计聚合定稿、板块资金与行情早已定格，全部版块可一次性跑齐。<br>
<b>硬约束：</b>板块强度的快照次日开盘即被覆盖且不可回溯，若当晚漏跑，务必在
<b>次日 09:15 之前</b>补跑（开盘前接口仍返回前一交易日收盘快照）。
</div>

<h2>🗂 全部版块详情</h2>
{sec_html}

<h2>✅ 每日手动更新自检清单</h2>
<div class='sec'>{ck_html}</div>

<footer>
数据来源：腾讯自选股 <b>westock-mcp</b>（盘后公开数据）。<br>
本页由 <code>quant/build_sections.py</code> 自动生成，可随时重跑以同步最新口径 ·
仅供参考，<b>不构成投资建议</b> · 市场有风险，投资需谨慎。
</footer>
</div>
</body>
</html>
"""

os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, "w", encoding="utf-8") as f:
    f.write(html)
print(f"OK -> {OUT}")
print(f"    龙虎榜={fmt(lhb_d)} | 高管增减持={fmt(exec_d)} | 大宗交易={fmt(blk_d)} | 板块强度={fmt(sec_d)} | 心理雷达={fmt(psy_d)}")
