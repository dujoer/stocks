#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""知名主体加仓股 · 量价健康度二次过滤。
输入: known_inc_50.json(股东维度, 知名加仓) + _tech_b{1,2}.json + _quote_b{1,2}.json(技术面/行情快照)
对 50 只「知名私募/牛散加仓」股做一套透明的量价健康度评分，叠加机构信号，输出可排序的二次过滤页。
评分口径(0-100):
  趋势结构 30 = 收盘>MA20(10) + MA20>MA60(10) + MA60>MA120(10)
  动量健康 25 = RSI_12∈[45,70](15) + 近60日涨跌幅温和正(10)
  量价配合 20 = 换手率适中(12) + 量比健康(8)
  相对位置 25 = 52周位置越低越高分(低位=未透支)
机构信号(不参与健康度分, 单独标注): 知名加仓主体数 + 中报净增持额
输出: web/shareholder/known-accumulation-health.html
"""
import json, os, datetime

BASE = os.path.dirname(__file__)
KNOWN = os.path.join(BASE, "known_inc_50.json")
TECH_FILES = [os.path.join(BASE, f"_tech_b{i}.json") for i in (1, 2)]
QUOTE_FILES = [os.path.join(BASE, f"_quote_b{i}.json") for i in (1, 2)]
OUT = os.path.abspath(os.path.join(BASE, "..", "..", "web", "shareholder", "known-accumulation-health.html"))

def load_json(path):
    return json.load(open(path, encoding="utf-8"))

def merge(files):
    d = {}
    for f in files:
        d.update(load_json(f).get("data", {}))
    return d

def clamp(x, lo=0, hi=100):
    return max(lo, min(hi, x))

def score_trend(close, ma):
    t = 0
    if close > ma.get("MA_20", 0): t += 10
    if ma.get("MA_20", 0) > ma.get("MA_60", 0): t += 10
    if ma.get("MA_60", 0) > ma.get("MA_120", 0): t += 10
    return t  # 0-30

def score_momentum(rsi, chg60):
    # RSI_12
    r = rsi.get("RSI_12", 50)
    if 45 <= r <= 70: rs = 15
    elif (40 <= r < 45) or (70 < r <= 78): rs = 9
    elif r > 78: rs = 0
    else: rs = 5
    # 近60日
    c = chg60 or 0
    if 0 <= c <= 30: cs = 10
    elif 30 < c <= 50: cs = 6
    elif c > 50: cs = 2
    elif -10 <= c < 0: cs = 6
    else: cs = 3
    return clamp(rs + cs, 0, 25)

def score_volprice(to, vr):
    to = to or 0; vr = vr or 0
    if 1 <= to <= 8: ts = 12
    elif 0.5 <= to < 1: ts = 6
    elif 8 < to <= 15: ts = 6
    else: ts = 0
    if 1 <= vr <= 2.5: vs = 8
    elif (0.7 <= vr < 1) or (2.5 < vr <= 3.5): vs = 4
    else: vs = 0
    return clamp(ts + vs, 0, 20)

def score_position(pos_pct):
    p = pos_pct if pos_pct is not None else 50
    if p <= 35: return 25
    if p <= 50: return 18
    if p <= 65: return 12
    if p <= 80: return 6
    return 0

def main():
    known = load_json(KNOWN)["rows"]
    tech = merge(TECH_FILES)
    quote = merge(QUOTE_FILES)

    rows = []
    for r0 in known:
        code = r0["code"]; name = r0["name"]
        t = tech.get(code, {}); q = quote.get(code, {})
        close = t.get("closePrice") or q.get("price")
        ma = t.get("ma", {}); rsi = t.get("rsi", {})
        to = q.get("turnover_rate"); vr = q.get("volume_ratio")
        chg = q.get("change_percent"); chg60 = q.get("chg_60d")
        h52 = q.get("high_52week"); l52 = q.get("low_52week")
        pos_pct = None
        if close and h52 and l52 and h52 > l52:
            pos_pct = (close - l52) / (h52 - l52) * 100
        st = score_trend(close, ma)
        sm = score_momentum(rsi, chg60)
        sv = score_volprice(to, vr)
        sp = score_position(pos_pct)
        health = st + sm + sv + sp
        # 机构信号加成(不参与健康度分, 仅用于综合排序): 知名加仓数(封顶3)*5
        inst_bonus = min(r0["known_inc"], 3) * 5
        composite = health + inst_bonus
        rows.append({
            "code": code, "name": name,
            "entities": r0["entities"], "known_inc": r0["known_inc"],
            "net_w": r0["net_w"],
            "price": close, "chg": chg, "to": to, "vr": vr,
            "chg60": chg60, "pos_pct": pos_pct,
            "st": st, "sm": sm, "sv": sv, "sp": sp,
            "health": health, "composite": composite,
        })
    # 默认按综合分降序
    rows.sort(key=lambda x: -x["composite"])

    def hlabel(h):
        if h >= 75: return ("强", "h-strong")
        if h >= 60: return ("中", "h-mid")
        return ("弱", "h-weak")

    trs = []
    for i, r in enumerate(rows, 1):
        lab, cls = hlabel(r["health"])
        strong_trend = (r["st"] >= 20)
        rel_low = (r["pos_pct"] is not None and r["pos_pct"] <= 60)
        vol_ok = (r["sv"] >= 12)
        to_ok = (r["to"] is not None and 1 <= r["to"] <= 8)
        inst = (r["known_inc"] >= 1)
        def mark(b): return '<span class="ok">✓</span>' if b else '<span class="no">—</span>'
        ent = "、".join(r["entities"])
        pos = f'{r["pos_pct"]:.0f}%' if r["pos_pct"] is not None else "—"
        chg = f'{r["chg"]:+.2f}%' if r["chg"] is not None else "—"
        chg_cls = "up" if (r["chg"] or 0) > 0 else ("down" if (r["chg"] or 0) < 0 else "")
        to = f'{r["to"]:.2f}%' if r["to"] is not None else "—"
        trs.append(
            f'<tr class="{cls}">'
            f'<td class="num">{i}</td>'
            f'<td class="stk">{esc(r["name"])}<span class="sub">{esc(r["code"])}</span></td>'
            f'<td class="ent" title="{esc(ent)}">{esc(ent)}</td>'
            f'<td class="num" data-net="{r["net_w"]}">{r["net_w"]:+.0f}</td>'
            f'<td class="num" data-px="{r["price"] or 0}">{r["price"]}</td>'
            f'<td class="num {chg_cls}">{chg}</td>'
            f'<td class="num">{pos}</td>'
            f'<td class="num">{to}</td>'
            f'<td class="num" data-st="{r["st"]}">{r["st"]}</td>'
            f'<td class="num" data-sm="{r["sm"]}">{r["sm"]}</td>'
            f'<td class="num" data-sv="{r["sv"]}">{r["sv"]}</td>'
            f'<td class="num" data-sp="{r["sp"]}">{r["sp"]}</td>'
            f'<td class="num health" data-h="{r["health"]}"><b>{r["health"]}</b><span class="lab {cls}">{lab}</span></td>'
            f'<td class="matrix">{mark(strong_trend)}{mark(rel_low)}{mark(vol_ok)}{mark(to_ok)}{mark(inst)}</td>'
            f'</tr>')

    today = datetime.date.today().isoformat()
    html = f'''<!DOCTYPE html>
<html lang="zh-CN"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>知名加仓股 · 量价健康度二次过滤</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:#f5f6f8;color:#23262b;font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;line-height:1.6}}
.topnav{{background:#fff;border-bottom:1px solid #e7e9ee;padding:10px 18px;display:flex;gap:14px;flex-wrap:wrap;font-size:13px}}
.topnav a{{color:#5a6270;text-decoration:none}}
.topnav a:hover{{color:#b8893b}}
.wrap{{max-width:1240px;margin:0 auto;padding:22px 18px 60px}}
header h1{{font-size:22px;margin-bottom:6px}}
.note{{background:#fff;border-left:4px solid #b8893b;border-radius:8px;padding:12px 16px;font-size:13px;color:#5a6270;margin:14px 0 6px}}
.note b{{color:#23262b}}
.sub{{color:#8a929c;font-size:13px;margin:8px 0 12px}}
.stat{{display:flex;gap:14px;flex-wrap:wrap;margin:10px 0}}
.stat .box{{background:#fff;border:1px solid #ecedf1;border-radius:10px;padding:10px 16px;min-width:120px}}
.stat .box .v{{font-size:20px;font-weight:700;color:#b8893b}}
.stat .box .l{{font-size:12px;color:#8a929c}}
.ptbl{{width:100%;border-collapse:collapse;font-size:12.5px;background:#fff;border:1px solid #ecedf1;border-radius:10px;overflow:hidden}}
.ptbl th{{background:#f3f4f7;color:#5a6270;text-align:right;padding:7px 8px;font-weight:600;cursor:pointer;white-space:nowrap;position:sticky;top:0}}
.ptbl th:hover{{color:#b8893b}}
.ptbl td{{padding:5px 8px;border-top:1px solid #f0f1f4;text-align:right;white-space:nowrap}}
.ptbl td.stk{{text-align:left;font-weight:600}}
.ptbl td.stk .sub{{display:block;font-weight:400;color:#9aa1ab;font-size:11px}}
.ptbl td.ent{{text-align:left;color:#7a5a2a;max-width:200px;overflow:hidden;text-overflow:ellipsis}}
.ptbl td.num{{color:#4a515c}}
.ptbl td.health{{background:#faf7f2}}
.ptbl td.health b{{font-size:14px}}
.ptbl td.health .lab{{display:inline-block;margin-left:5px;font-size:11px;padding:1px 6px;border-radius:8px;color:#fff}}
.lab.h-strong{{background:#1a9e5a}} .lab.h-mid{{background:#b8893b}} .lab.h-weak{{background:#9aa1ab}}
tr.h-strong td.health{{background:#f1f9f4}} tr.h-mid td.health{{background:#fbf6ec}} tr.h-weak td.health{{background:#f6f7f9}}
.up{{color:#b8332a;font-weight:600}} .down{{color:#1a9e5a;font-weight:600}}
.matrix{{letter-spacing:2px;font-size:13px}}
.ok{{color:#1a9e5a;font-weight:700}} .no{{color:#c9ced6}}
footer{{text-align:center;color:#9aa1ab;font-size:12px;padding:24px}}
.disc{{background:#fff;border:1px dashed #d9c79a;border-radius:10px;padding:12px 16px;font-size:12px;color:#6b7280;margin-top:20px}}
.legend{{font-size:12px;color:#6b7280;margin:6px 0 0}}
.legend b{{color:#23262b}}
</style></head>
<body>
<div class='topnav'>
  <a href="../market/index.html">每日总览</a>
  <a href="../lhb/lhb.html">龙虎榜分析</a>
  <a href="../market/hotmoney.html">游资看板</a>
  <a href="../sector/index.html">板块强度</a>
  <a href="2026-q2-industry-elite.html">股东动向</a>
  <a href="top-elite.html">玩家图谱</a>
  <a href="stock-accumulation.html">增持信号扫描</a>
  <a href="../exec/index.html">高管增减持</a>
  <a href="../sections/index.html">版块总览</a>
  <a href="../../index.html">返回主页</a>
</div>
<div class="wrap">
  <header><h1>知名加仓股 · 量价健康度二次过滤</h1>
    <div style="color:#8a929c;font-size:13px">在「股票增持信号扫描」筛出的 50 只<b>知名私募/牛散加仓</b>股基础上，叠加技术面/量价二次过滤，按「健康度 + 机构信号」综合排序，辅助聚焦最有交易素质的标的。</div>
  </header>
  <div class="note">
    <b>评分口径（0-100，透明可复核）：</b>
    ① <b>趋势结构</b> 30 = 收盘&gt;MA20(+10) + MA20&gt;MA60(+10) + MA60&gt;MA120(+10)；
    ② <b>动量健康</b> 25 = RSI_12∈[45,70](+15) + 近60日涨跌幅温和正(+10)；
    ③ <b>量价配合</b> 20 = 换手率适中1%-8%(+12) + 量比健康1-2.5(+8)；
    ④ <b>相对位置</b> 25 = 52周位置越低分越高（低位=未被透支）。
    <b>机构信号</b>（不参与健康度分，仅综合排序加成）：知名加仓主体数（封顶3）×5。
    数据为 2026-09-04 收盘快照，单季股东数据无法单列「新进」（见增持扫描页说明）。
  </div>
  <div class="stat">
    <div class="box"><div class="v">{len(rows)}</div><div class="l">知名加仓样本(只)</div></div>
    <div class="box"><div class="v">{sum(1 for r in rows if r['health']>=75)}</div><div class="l">健康度·强(≥75)</div></div>
    <div class="box"><div class="v">{sum(1 for r in rows if 60<=r['health']<75)}</div><div class="l">健康度·中(60-74)</div></div>
    <div class="box"><div class="v">{sum(1 for r in rows if r['health']<60)}</div><div class="l">健康度·弱(&lt;60)</div></div>
    <div class="box"><div class="v">{sum(1 for r in rows if r['st']>=20 and (r['pos_pct'] or 999)<=60 and r['sv']>=12)}</div><div class="l">强趋势+低位+量价健康</div></div>
  </div>
  <div class="sub">点击表头可重排。✓ 矩阵顺序：强趋势 / 相对低位 / 量价健康 / 换手适中 / 机构主导。优先看健康度「强」且 ✓ 全绿者。</div>
  <table class="ptbl" id="htbl">
    <thead><tr>
      <th onclick="sortH(0)">#</th>
      <th onclick="sortH(1)">股票</th>
      <th onclick="sortH(2)">知名加仓主体</th>
      <th onclick="sortH(3)">净增持(万)</th>
      <th onclick="sortH(4)">现价</th>
      <th onclick="sortH(5)">涨跌幅</th>
      <th onclick="sortH(6)">52周位</th>
      <th onclick="sortH(7)">换手率</th>
      <th onclick="sortH(8)">趋势</th>
      <th onclick="sortH(9)">动量</th>
      <th onclick="sortH(10)">量价</th>
      <th onclick="sortH(11)">位置</th>
      <th onclick="sortH(12)">健康度</th>
      <th onclick="sortH(13)">✓矩阵</th>
    </tr></thead>
    <tbody>{"".join(trs)}</tbody>
  </table>
  <div class="disc">⚠️ 免责声明：本页为「知名资金加仓 + 量价健康度」的中性量化筛选，评分基于公开技术指标与单季股东数据，<b>不构成任何投资建议</b>。用户七条标准中的「行业订单/业绩可验证」「瓶颈环节」需自行核验；技术面为某一时点的快照，会随行情变化。请结合基本面与风险预算独立决策。</div>
  <footer>生成日期 {today} · 数据快照 2026-09-04 · 样本 50 只知名主体加仓股</footer>
</div>
<script>
function sortH(col){{
  var tbl=document.getElementById('htbl');
  var tb=tbl.tBodies[0], rows=Array.from(tb.rows);
  var asc=tbl.getAttribute('data-asc')!=='1';
  var numCols={{3:'net',4:'px',5:'',6:'',7:'',8:'st',9:'sm',10:'sv',11:'sp',12:'h'}};
  var keyf=function(r){{
    if(col===3)return parseFloat(r.children[3].getAttribute('data-net'))||0;
    if(col===4)return parseFloat(r.children[4].getAttribute('data-px'))||0;
    if(col===8)return parseFloat(r.children[8].getAttribute('data-st'))||0;
    if(col===9)return parseFloat(r.children[9].getAttribute('data-sm'))||0;
    if(col===10)return parseFloat(r.children[10].getAttribute('data-sv'))||0;
    if(col===11)return parseFloat(r.children[11].getAttribute('data-sp'))||0;
    if(col===12)return parseInt(r.children[12].getAttribute('data-h'))||0;
    return r.children[col].textContent;
  }};
  rows.sort(function(a,b){{
    var x=keyf(a),y=keyf(b);
    if(typeof x==='number')return asc?x-y:y-x;
    x=String(x);y=String(y);
    return asc?(x<y?-1:x>y?1:0):(x<y?1:x>y?-1:0);
  }});
  rows.forEach(function(r){{tb.appendChild(r);}});
  tbl.setAttribute('data-asc',asc?'1':'0');
}}
</script>
</body></html>'''
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(html)
    print("written:", OUT, "bytes:", len(html), "| rows:", len(rows))

def esc(s):
    return (str(s).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;"))

if __name__ == "__main__":
    main()
