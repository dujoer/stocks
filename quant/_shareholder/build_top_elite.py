#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成「行业内知名 Top20 私募 / Top20 牛散 · 玩家图谱 + 机会扫描器」。
基于行业知名度与历史业绩的策划清单（非短期收益胜率）；叠加 2026-Q2 中报十大流通股东
真实持仓变动（增持/减持/不变）、参考价与参考市值，并按"增持信号"做聚合排序，便于快速发现机会。
输出: web/shareholder/top-elite.html
"""
import json, os, datetime

OUT = os.path.join(os.path.dirname(__file__), "..", "..", "web", "shareholder", "top-elite.html")
OUT = os.path.abspath(OUT)

# 全市场 Q2 中报真实现身统计（scan_elite_coverage.py 产出）
COV_PATH = os.path.join(os.path.dirname(__file__), "elite_coverage.json")
# 参考价（data_quote 最新价，_quotes_elite.json）
QUOTE_PATH = os.path.join(os.path.dirname(__file__), "_quotes_elite.json")
# 中报后高管增减持共现（exec_elite_xref.json）
XREF_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "quant", "exec_elite_xref.json")

try:
    COVERAGE = json.load(open(COV_PATH, encoding="utf-8"))
except Exception:
    COVERAGE = {"meta": {}, "entities": {}}
try:
    QUOTES = json.load(open(QUOTE_PATH, encoding="utf-8"))
except Exception:
    QUOTES = {}

def load_xref():
    try:
        d = json.load(open(XREF_PATH, encoding="utf-8"))
        # 反查：股票名 -> [主体]
        m = {}
        for it in d.get("items", []):
            for st in it.get("stocks", []):
                m.setdefault(st, []).append(it["name"])
        return m
    except Exception:
        return {}

XREF = load_xref()
_META = COVERAGE.get("meta") or {}
SAMPLE = _META.get("sample", "全市场")
RDATE = _META.get("date", "2026-06-30")

def build_evidence(name):
    cov = (COVERAGE.get("entities") or {}).get(name)
    meta = COVERAGE.get("meta") or {}
    sample = meta.get("sample")
    date = meta.get("date")
    if not cov:
        return ("", False)
    n = cov.get("count", 0)
    if n == 0:
        return (f"全市场（{sample} 只 · {date} Q2 中报）前十大均未现身", True)
    names = [s["name"] for s in cov.get("stocks", [])[:4]]
    shown = "、".join(names)
    more = f" 等 {n} 只" if n > len(names) else f"（共 {n} 只）"
    return (f"{date} Q2 中报现身 {n} 只：{shown}{more}", False)

def price_of(code):
    q = QUOTES.get(code)
    return q.get("price") if isinstance(q, dict) else None

def entity_positions(name):
    """返回该主体的全部 Q2 十大流通股东持仓行（含变动与市值）。"""
    cov = (COVERAGE.get("entities") or {}).get(name) or {}
    rows = []
    for s in cov.get("stocks", []):
        code = s.get("code", "")
        hs = s.get("holdShares") or 0
        hc = s.get("holdChange") or 0
        pct = s.get("holdPct") or 0
        px = price_of(code)
        mv = (hs * px / 1e8) if px else None  # 亿元
        if hc > 0:
            typ = "增持"
        elif hc < 0:
            typ = "减持"
        else:
            typ = "不变"
        rows.append({
            "name": s.get("name", ""), "code": code, "holder": s.get("holder", ""),
            "hold_w": round(hs / 1e4, 1), "pct": round(pct, 2),
            "chg_w": round(hc / 1e4, 1), "typ": typ,
            "price": px, "mv": round(mv, 2) if mv is not None else None,
            "chg_pct": (QUOTES.get(code) or {}).get("chg"),
        })
    rows.sort(key=lambda r: -(r["hold_w"] or 0))
    return rows

def entity_table(name):
    rows = entity_positions(name)
    if not rows:
        return ""
    trs = []
    for r in rows:
        mv = f'{r["mv"]:.2f}' if r["mv"] is not None else "—"
        px = f'{r["price"]:.2f}' if r["price"] else "—"
        chg = f'+{r["chg_w"]}' if r["chg_w"] > 0 else (str(r["chg_w"]) if r["chg_w"] < 0 else "0")
        tcls = {"增持": "up", "减持": "down", "不变": "flat"}[r["typ"]]
        trs.append(
            f'<tr><td class="stk">{esc(r["name"])}</td>'
            f'<td class="num">{r["hold_w"]}</td>'
            f'<td class="num">{r["pct"]}</td>'
            f'<td class="num {tcls}">{chg}</td>'
            f'<td class="num {tcls}">{r["typ"]}</td>'
            f'<td class="num">{px}</td>'
            f'<td class="num">{mv}</td></tr>')
    return f'''<div class="posbox">
      <div class="poscap">中报十大流通股东持仓（{len(rows)} 只 · 按持股排序）</div>
      <table class="ptbl">
        <thead><tr><th>股票</th><th>持股(万)</th><th>占比%</th><th>季度变动(万)</th><th>类型</th><th>参考价</th><th>市值(亿)</th></tr></thead>
        <tbody>{"".join(trs)}</tbody>
      </table></div>'''

# ============ 私募 Top20 ============
PRIVATE = [
    {"name":"高毅资产","people":"邱国鹭(创始人) / 邓晓峰 / 冯柳 / 卓利伟 / 孙庆瑞","type":"平台型·主观多头","scale":"千亿级（国内最大主观多头平台之一）",
     "sectors":["消费","医药","先进制造","周期","金融"],"style":"基金经理制、价值成长、长期持股，冯柳逆向+邓晓峰制造业深耕为标签。",
     "tag":"A股最具代表性的平台型头部私募"},
    {"name":"景林资产","people":"蒋锦志(创始人)","type":"主观多头","scale":"数百亿（含美元基金）",
     "sectors":["消费","互联网","港股中概","医药"],"style":"价值投资、长期持有优质龙头，跨 AH/中概配置。",
     "tag":"长线价值标杆，海外中国资产配置经验深厚"},
    {"name":"淡水泉投资","people":"赵军(创始人)","type":"主观多头","scale":"数百亿",
     "sectors":["成长股","TMT","消费","高端制造"],"style":"基本面逆向，“越跌越买”的逆周期布局。",
     "tag":"“逆向投资”风格的旗号"},
    {"name":"重阳投资","people":"裘国根(创始人)","type":"主观多头","scale":"数百亿",
     "sectors":["蓝筹","金融","消费","周期"],"style":"价值优先、注重安全边际与长期复利。",
     "tag":"老牌价值派，稳健低波"},
    {"name":"千合资本","people":"王亚伟(创始人，原华夏大盘)","type":"主观多头","scale":"百亿级",
     "sectors":["重组预期","成长","消费"],"style":"精选个股、挖掘重组与拐点机会。",
     "tag":"“公募一哥”转型私募的代表"},
    {"name":"星石投资","people":"江晖(创始人)","type":"宏观+成长","scale":"百亿级",
     "sectors":["成长","宏观策略","消费"],"style":"宏观驱动下的成长价值轮动。",
     "tag":"国内最早一批阳光私募"},
    {"name":"朱雀投资","people":"李华轮(创始人)","type":"主观多头","scale":"百亿级",
     "sectors":["高端制造","新能源","消费","医药"],"style":"产业深耕、自上而下选赛道。",
     "tag":"制造业/新能源赛道认知突出"},
    {"name":"混沌投资","people":"葛卫东(创始人)","type":"宏观+趋势","scale":"百亿级",
     "sectors":["商品","有色","科技","消费"],"style":"宏观+趋势、全球配置，股期联动。",
     "tag":"牛散与私募双栖的宏观玩家"},
    {"name":"林园投资","people":"林园","type":"主观多头","scale":"百亿级",
     "sectors":["消费","医药(中药)"],"style":"极致价值、长期持有成瘾性消费与医疗。",
     "tag":"“茅台/片仔癀”长期主义旗手"},
    {"name":"东方港湾","people":"但斌","type":"主观多头","scale":"百亿级",
     "sectors":["白酒","互联网","美股龙头"],"style":"长期价值、“时间的玫瑰”。",
     "tag":"白酒+中概长线代表"},
    {"name":"高瓴资本","people":"张磊","type":"一二级联动","scale":"数千亿（含一级）",
     "sectors":["消费","医药","科技","新能源"],"style":"长期主义、重仓中国、产业赋能。",
     "tag":"横跨一二级的顶级资本"},
    {"name":"宁泉资产","people":"杨东(原兴全总经理)","type":"主观多头","scale":"数百亿",
     "sectors":["低估值","港股","折价资产"],"style":"稳健价值、风控优先。",
     "tag":"“看空提示”出圈的稳健派"},
    {"name":"半夏投资","people":"李蓓(创始人)","type":"宏观对冲","scale":"百亿级",
     "sectors":["商品","利率","权益"],"style":"自上而下宏观策略，股债商灵活配置。",
     "tag":"宏观策略知名女将"},
    {"name":"聚鸣投资","people":"刘晓龙(创始人)","type":"多策略","scale":"数百亿",
     "sectors":["制造","消费","科技"],"style":"成长+逆向多策略并行。",
     "tag":"逆向成长多策略头部"},
    {"name":"盘京投资","people":"庄涛(创始人)","type":"主观多头","scale":"百亿级",
     "sectors":["成长","消费","制造"],"style":"成长价值、精选个股。",
     "tag":"成长价值标杆"},
    {"name":"石锋资产","people":"崔红建(创始人)","type":"主观多头","scale":"百亿级",
     "sectors":["成长价值","消费","制造"],"style":"产业趋势+公司质量双因子。",
     "tag":"质量成长派"},
    {"name":"正心谷","people":"林利军(原汇添富创始人)","type":"产业投资","scale":"数百亿",
     "sectors":["消费","科技","医药"],"style":"长期产业投资、深度研究。",
     "tag":"公募大佬转型产业投资"},
    {"name":"幻方量化","people":"九章/幻方团队","type":"量化","scale":"曾超600亿(后主动收缩)",
     "sectors":["全市场量化"],"style":"AI+量化、高频/中性多策略。",
     "tag":"量化巨头，技术驱动"},
    {"name":"九坤投资","people":"王琛团队","type":"量化","scale":"数百亿",
     "sectors":["量化对冲","指数增强"],"style":"多频段量化多头/中性。",
     "tag":"头部量化中性/指增"},
    {"name":"明汯投资","people":"裘慧明(创始人)","type":"量化","scale":"数百亿",
     "sectors":["量化"],"style":"多策略量化、指增与中性并行。",
     "tag":"老牌量化头部"},
]

# ============ 牛散 Top20 ============
RETAIL = [
    {"name":"葛卫东","type":"牛散+私募双栖","sectors":["科技","有色","消费","医美"],
     "style":"期货起家，股期联动、长期持有+顺势，单票格局大。","tag":"牛散天花板，混沌投资创始人"},
    {"name":"章建平","type":"牛散(章盟主)","sectors":["科技","券商","题材","大市值"],
     "style":"激进重仓、偏好大成交额题材龙头。","tag":"“章盟主”，浙江游资转型牛散代表"},
    {"name":"赵建平","type":"牛散","sectors":["医药","科技","成长"],
     "style":"专注成长股、长线持有，押注细分龙头。","tag":"医药科技成长高手"},
    {"name":"张素芬","type":"牛散","sectors":["低价股","重组","消费","公用事业"],
     "style":"多只分散潜伏、偏好低价与重组预期。","tag":"“低价重组”分散型大户"},
    {"name":"何雪萍","type":"牛散","sectors":["小盘","重组","次新"],
     "style":"长期潜伏、押注重组与小盘拐点。","tag":"重组潜伏型"},
    {"name":"周信钢","type":"牛散(夫妻档)","sectors":["次新","小盘","创业板"],
     "style":"与李欣协同、多账户布局次新小盘。","tag":"次新小盘专业户"},
    {"name":"陈发树","type":"产业资本型牛散","sectors":["紫金矿业","云南白药","隆基","中国中免"],
     "style":"长期价值+定增，产业资本视角。","tag":"“中国巴菲特”式长期持有"},
    {"name":"蒋仕波","type":"牛散","sectors":["医药(中药)"],
     "style":"专注中药与医药赛道。","tag":"中药医药专精"},
    {"name":"夏重阳","type":"牛散","sectors":["低价股","重组","ST"],
     "style":"分散布局低价与重组标的。","tag":"低价重组分散户"},
    {"name":"魏巍","type":"牛散","sectors":["次新","小盘","打新"],
     "style":"网下打新+持股，次新偏好。","tag":"打新+持股型"},
    {"name":"吕强","type":"牛散","sectors":["多板块","低价蓝筹","传媒"],
     "style":"跨板块分散、低价蓝筹与题材兼具。","tag":"多面手分散户"},
    {"name":"邹瀚枢","type":"牛散","sectors":["资源","有色金属","材料"],
     "style":"聚焦资源与金属周期。","tag":"资源周期专精"},
    {"name":"赵吉","type":"牛散","sectors":["医药","消费"],
     "style":"医药消费成长布局。","tag":"医药消费型"},
    {"name":"李欣","type":"牛散(周信钢配偶)","sectors":["次新","小盘"],
     "style":"与周信钢协同操作。","tag":"协同账户"},
    {"name":"刘芳","type":"牛散","sectors":["重组","ST","题材"],
     "style":"精准押注重组与困境反转。","tag":"“最牛散户”重组王"},
    {"name":"王萍","type":"牛散","sectors":["与葛卫东关联标的"],
     "style":"与葛卫东协同布局。","tag":"协同账户"},
    {"name":"屠文斌","type":"牛散(宁波系)","sectors":["题材博弈"],
     "style":"激进短线、题材博弈。","tag":"宁波系活跃户"},
    {"name":"沈付兴","type":"牛散","sectors":["多板块"],
     "style":"历史活跃、跨板块操作。","tag":"老牌活跃户"},
    {"name":"邱宝裕","type":"牛散/游资(Asking)","sectors":["龙头","打板"],
     "style":"淘股吧精神领袖，龙头战法。","tag":"游资鼻祖(偏游资)"},
    {"name":"舒逸民","type":"牛散","sectors":["多板块","题材"],
     "style":"跨板块活跃、题材敏感。","tag":"活跃题材户"},
]

def esc(s):
    return (s.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;"))

def card(idx, d, kind):
    etext, ezero = build_evidence(d["name"])
    if etext:
        cls = "dt zero" if ezero else "dt"
        dt_html = f'<div class="{cls}">📌 {esc(etext)}</div>'
    else:
        dt_html = ''
    xref_stocks = [st for st, names in XREF.items() if d["name"] in names]
    xref_html = ''
    if xref_stocks:
        xref_html = f'<div class="xref">🔗 中报后关联（高管增减持）：{"、".join(esc(s) for s in xref_stocks)}</div>'
    sectors = " · ".join(esc(s) for s in d["sectors"])
    if kind == "private":
        meta = f'<div class="meta"><span class="chip">{esc(d["type"])}</span><span class="chip gold">{esc(d["scale"])}</span></div>'
        people = f'<div class="people">核心：{esc(d["people"])}</div>'
    else:
        meta = f'<div class="meta"><span class="chip">{esc(d["type"])}</span></div>'
        people = ""
    return f'''
    <div class="card">
      <div class="rank">{idx}</div>
      <div class="body">
        <div class="nm">{esc(d["name"])}</div>
        {people}
        {meta}
        <div class="sec">主投：{sectors}</div>
        <div class="style">{esc(d["style"])}</div>
        <div class="tagline">★ {esc(d["tag"])}</div>
        {dt_html}
        {xref_html}
        {entity_table(d["name"])}
      </div>
    </div>'''

def grid(title, subtitle, items, kind):
    cards = "".join(card(i+1, d, kind) for i, d in enumerate(items))
    return f'''
    <div class="block">
      <h2>{esc(title)}</h2>
      <div class="sub">{esc(subtitle)}</div>
      <div class="grid">{cards}</div>
    </div>'''

def opportunity_scan():
    """聚合 40 家主体的全部 Q2 持仓，按'增持信号'排序，便于快速发现机会。"""
    rows = []
    all_entities = [(p["name"], "私募") for p in PRIVATE] + [(r["name"], "牛散") for r in RETAIL]
    for name, kind in all_entities:
        for r in entity_positions(name):
            rows.append({
                "entity": name, "kind": kind, "name": r["name"], "code": r["code"],
                "hold_w": r["hold_w"], "pct": r["pct"], "chg_w": r["chg_w"], "typ": r["typ"],
                "price": r["price"], "mv": r["mv"], "chg_pct": r["chg_pct"],
            })
    # 默认按 参考市值 降序
    rows.sort(key=lambda x: -(x["mv"] if x["mv"] is not None else -1))
    trs = []
    for i, r in enumerate(rows, 1):
        mv = f'{r["mv"]:.2f}' if r["mv"] is not None else "—"
        px = f'{r["price"]:.2f}' if r["price"] else "—"
        chg = f'+{r["chg_w"]}' if r["chg_w"] > 0 else (str(r["chg_w"]) if r["chg_w"] < 0 else "0")
        tcls = {"增持": "up", "减持": "down", "不变": "flat"}[r["typ"]]
        kcls = "k-p" if r["kind"] == "私募" else "k-r"
        # 加 data-* 便于排序
        trs.append(
            f'<tr data-mv="{r["mv"] if r["mv"] is not None else -1}" data-chg="{r["chg_w"]}" '
            f'data-pct="{r["pct"]}" data-hold="{r["hold_w"]}" '
            f'data-px="{r["price"] if r["price"] is not None else -1}">'
            f'<td class="num">{i}</td>'
            f'<td><span class="ent {kcls}">{esc(r["entity"])}</span></td>'
            f'<td class="num">{esc(r["kind"])}</td>'
            f'<td class="stk">{esc(r["name"])}</td>'
            f'<td class="num">{esc(r["code"])}</td>'
            f'<td class="num">{r["hold_w"]}</td>'
            f'<td class="num">{r["pct"]}</td>'
            f'<td class="num {tcls}">{chg}</td>'
            f'<td class="num {tcls}">{r["typ"]}</td>'
            f'<td class="num">{px}</td>'
            f'<td class="num">{mv}</td></tr>')
    return f'''<div class="block scan">
      <h2>机会扫描 · 增持/减持信号总榜</h2>
      <div class="sub">40 家主体全部 Q2 中报十大流通股东持仓聚合（{len(rows)} 条）· 默认按「参考市值」降序 · 点击表头可重排 · 红色=增持/买入信号，绿色=减持</div>
      <div class="scanhint">用法：先看「增持」行（红），按市值或季度增持量排序，圈出有实力主体重仓且本季加仓的票，再回看下方主体卡片的详细持仓与中报后关联。</div>
      <table class="ptbl scan-tbl" id="scantbl">
        <thead><tr>
          <th onclick="sortScan(0)">#</th>
          <th onclick="sortScan(1)">主体</th>
          <th onclick="sortScan(2)">类别</th>
          <th onclick="sortScan(3)">股票</th>
          <th onclick="sortScan(4)">代码</th>
          <th onclick="sortScan(5)">持股(万)</th>
          <th onclick="sortScan(6)">占比%</th>
          <th onclick="sortScan(7)">季度变动(万)</th>
          <th onclick="sortScan(8)">类型</th>
          <th onclick="sortScan(9)">参考价</th>
          <th onclick="sortScan(10)">市值(亿)</th>
        </tr></thead>
        <tbody>{"".join(trs)}</tbody>
      </table></div>'''

def build():
    today = datetime.date.today().isoformat()
    html = f'''<!DOCTYPE html>
<html lang="zh-CN"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>行业知名 Top20 私募 / 牛散 · 玩家图谱 + 机会扫描</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:#f5f6f8;color:#23262b;font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;line-height:1.6}}
.topnav{{background:#fff;border-bottom:1px solid #e7e9ee;padding:10px 18px;display:flex;gap:14px;flex-wrap:wrap;font-size:13px}}
.topnav a{{color:#5a6270;text-decoration:none}}
.topnav a:hover{{color:#b8893b}}
.wrap{{max-width:1180px;margin:0 auto;padding:22px 18px 60px}}
header h1{{font-size:24px;margin-bottom:6px}}
.note{{background:#fff;border-left:4px solid #b8893b;border-radius:8px;padding:12px 16px;font-size:13px;color:#5a6270;margin:14px 0 6px}}
.note b{{color:#23262b}}
.block{{margin-top:30px}}
.block h2{{font-size:19px;display:flex;align-items:center;gap:8px}}
.block h2:before{{content:"";width:4px;height:18px;background:#b8893b;border-radius:3px}}
.sub{{color:#8a929c;font-size:13px;margin:4px 0 16px}}
.scanhint{{background:#fbf6ea;border:1px dashed #d9c79a;border-radius:8px;padding:8px 12px;font-size:12px;color:#8a6a2e;margin-bottom:12px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(360px,1fr));gap:14px}}
.card{{background:#fff;border:1px solid #ecedf1;border-radius:12px;padding:14px 16px;display:flex;gap:12px;transition:.15s}}
.card:hover{{box-shadow:0 4px 18px rgba(0,0,0,.06);border-color:#d9c79a}}
.rank{{flex:0 0 30px;height:30px;border-radius:50%;background:#b8893b;color:#fff;font-weight:700;display:flex;align-items:center;justify-content:center;font-size:14px}}
.body{{flex:1;min-width:0}}
.nm{{font-size:16px;font-weight:700;color:#1c2430}}
.people{{font-size:12px;color:#6b7280;margin-top:2px}}
.meta{{margin:6px 0;display:flex;gap:6px;flex-wrap:wrap}}
.chip{{font-size:11px;background:#f1f2f5;color:#5a6270;padding:2px 8px;border-radius:20px}}
.chip.gold{{background:#f6efe2;color:#9a6f2b}}
.sec{{font-size:13px;margin-top:4px}}
.style{{font-size:12.5px;color:#4a515c;margin-top:4px}}
.tagline{{font-size:12px;color:#b8893b;margin-top:6px;font-weight:600}}
.dt{{font-size:11.5px;color:#1a9e5a;margin-top:6px;background:#eef8f1;padding:3px 8px;border-radius:6px;display:inline-block}}
.dt.zero{{color:#9aa1ab;background:#f1f2f5}}
.xref{{font-size:11.5px;color:#b8332a;margin-top:6px;background:#fdeeee;padding:3px 8px;border-radius:6px;display:inline-block}}
.posbox{{margin-top:8px}}
.poscap{{font-size:11px;color:#8a929c;margin:4px 0 4px}}
.ptbl{{width:100%;border-collapse:collapse;font-size:11.5px}}
.ptbl th{{background:#f3f4f7;color:#5a6270;text-align:right;padding:4px 6px;font-weight:600;cursor:pointer;white-space:nowrap}}
.ptbl th:hover{{color:#b8893b}}
.ptbl td{{padding:3px 6px;border-top:1px solid #f0f1f4;text-align:right;white-space:nowrap}}
.ptbl td.stk{{text-align:left;color:#23262b;font-weight:600}}
.ptbl td.num{{color:#4a515c}}
.up{{color:#b8332a;font-weight:600}}
.down{{color:#1a9e5a;font-weight:600}}
.flat{{color:#8a929c}}
.scan-tbl td.num{{text-align:right}}
.scan-tbl td.stk{{text-align:left}}
.scan-tbl td .ent{{font-weight:700}}
.k-p{{color:#b8893b}}
.k-r{{color:#5a6270}}
footer{{text-align:center;color:#9aa1ab;font-size:12px;padding:24px}}
.disc{{background:#fff;border:1px dashed #d9c79a;border-radius:10px;padding:12px 16px;font-size:12px;color:#6b7280;margin-top:26px}}
</style></head>
<body>
<div class='topnav'>
  <a href="../market/index.html">每日总览</a>
  <a href="../lhb/lhb.html">龙虎榜分析</a>
  <a href="../market/hotmoney.html">游资看板</a>
  <a href="../sector/index.html">板块强度</a>
  <a href="2026-q2-industry-elite.html">股东动向</a>
  <a href="stock-accumulation.html">增持扫描</a>
  <a href="../exec/index.html">高管增减持</a>
  <a href="../block/index.html">大宗交易</a>
  <a href="../sections/index.html">版块总览</a>
  <a href="../../index.html">返回主页</a>
</div>
<div class="wrap">
  <header>
    <h1>行业知名 Top20 私募 / Top20 牛散 · 玩家图谱 + 机会扫描</h1>
    <div style="color:#8a929c;font-size:13px">A股市场上被广泛讨论、行业地位突出的私募与牛散清单（按行业知名度与历史业绩策划，非短期收益胜率）；叠加 2026-Q2 中报十大流通股东真实持仓变动，辅助快速发现机会。</div>
  </header>
  <div class="note">
    <b>口径说明：</b>应需求调整 —— 短期的“区间收益胜率”样本太短、噪声太大，不足以排名；本页改为<b>行业内知名度与历史业绩</b>视角的策划清单。
    名称旁“📌”为<b>真实持仓佐证</b>：基于已合并的 <b>{SAMPLE} 只全市场个股 {RDATE} Q2 中报十大股东</b>数据扫描。每张卡片下方为<b>中报十大流通股东持仓明细</b>（持股/占比/季度变动/参考价/市值），顶部“机会扫描”为 40 家主体的<b>增持/减持信号聚合总榜</b>。
    <b>新进说明：</b>单季快照的 <code>holdChange</code> 仅区分增持/减持/不变，<b>未单列“新进”标志</b>（新进主体被并入“不变”项），故本页以“增持”作为可检测的买入信号；若需严格新进，需对比 Q1 十大股东（当前数据源仅返回最新一期）。
    <b>中报后变化：</b>Q3 十大股东尚未披露（约 10–11 月），中报后增量信息以“高管增减持”共现呈现（见卡片🔗标记，来自 exec 页交叉验证的 9 例）。
    本页<b>不构成任何投资建议</b>。
  </div>
  {opportunity_scan()}
  {grid("私募 Top20（行业头部）", "平台型、主观多头、量化、宏观对冲中具有代表性的头部机构", PRIVATE, "private")}
  {grid("牛散 Top20（知名大户）", "长期现身前十大流通股东、市场关注度高的个人/家族账户", RETAIL, "retail")}
  <div class="disc">
    ⚠️ 免责声明：本页为<b>行业玩家格局</b>的公开信息整理，所有名称、规模、风格均来自公开报道与历史持仓，存在时效与认知偏差；
    所列主体仅为市场讨论中的知名代表，<b>不代表其当前业绩或未来表现</b>，更不构成买卖任何证券的建议。持仓/市值基于中报披露股数 × 最新参考价估算，仅供参考。
  </div>
  <footer>生成日期 {today} · 数据维度：公开信息整理 + 全市场 {SAMPLE} 只 {RDATE} Q2 中报十大股东真实现身统计 + 最新参考价</footer>
</div>
<script>
function sortScan(col) {{
  var tbl=document.getElementById('scantbl');
  var tb=tbl.tBodies[0];
  var rows=Array.from(tb.rows);
  var asc=tbl.getAttribute('data-asc')!=='1';
  var numCols={{5:'hold',6:'pct',7:'chg',9:'px',10:'mv'}};
  var keyf=function(r){{
    if(numCols[col]){{ return parseFloat(r.getAttribute('data-'+numCols[col]))||0; }}
    return r.children[col].textContent;
  }};
  rows.sort(function(a,b){{
    var x=keyf(a), y=keyf(b);
    if(typeof x==='number'){{ return asc? x-y : y-x; }}
    x=String(x); y=String(y);
    return asc? (x<y?-1:x>y?1:0) : (x<y?1:x>y?-1:0);
  }});
  rows.forEach(function(r){{tb.appendChild(r);}});
  tbl.setAttribute('data-asc', asc?'1':'0');
}}
</script>
</body></html>'''
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(html)
    print("written:", OUT, "bytes:", len(html))

if __name__ == "__main__":
    build()
