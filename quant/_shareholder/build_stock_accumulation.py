#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""股票维度 · 中报增持信号扫描器。
直接复用已落盘的 5544 只全市场 2026-Q2 中报十大流通股东数据，对每只股票统计：
  增持股东数 / 减持股东数 / 净增持(万股) / 增持额(万股) / 是否有知名私募·牛散加仓。
按「知名主体加仓优先 + 净增持量」排序，辅助快速发现具增持潜力的股票。
输出: web/shareholder/stock-accumulation.html

说明：单季快照无法区分「新进」(新进主体被并入 holdChange=0 的不变项)，故本页以「增持」作为可检测的买入信号；
若需严格「新进」，需对比 Q1 十大股东（当前数据源仅返回最新一期，不支持历史日期）。
"""
import json, os, datetime

BASE = os.path.dirname(__file__)
SRC = os.path.join(BASE, "..", "q2_full", "_merged_shareholder.json")
OUT = os.path.join(BASE, "..", "..", "web", "shareholder", "stock-accumulation.html")
OUT = os.path.abspath(OUT)

# 知名主体匹配（与 scan_elite_coverage.py 一致）：私募=产品/公司名前缀；牛散=自然人姓名(剔除机构后缀防误匹配)
MATCH = {
    "高毅资产": ("private", ["高毅"]), "景林资产": ("private", ["景林"]), "淡水泉投资": ("private", ["淡水泉"]),
    "重阳投资": ("private", ["重阳"]), "千合资本": ("private", ["千合"]), "星石投资": ("private", ["星石"]),
    "朱雀投资": ("private", ["朱雀"]), "混沌投资": ("private", ["混沌"]), "林园投资": ("private", ["林园"]),
    "东方港湾": ("private", ["东方港湾"]), "高瓴资本": ("private", ["高瓴"]), "宁泉资产": ("private", ["宁泉"]),
    "半夏投资": ("private", ["半夏"]), "聚鸣投资": ("private", ["聚鸣"]), "盘京投资": ("private", ["盘京"]),
    "石锋资产": ("private", ["石锋"]), "正心谷": ("private", ["正心谷"]), "幻方量化": ("private", ["幻方"]),
    "九坤投资": ("private", ["九坤"]), "明汯投资": ("private", ["明汯"]),
    "葛卫东": ("retail", ["葛卫东"]), "章建平": ("retail", ["章建平"]), "赵建平": ("retail", ["赵建平"]),
    "张素芬": ("retail", ["张素芬"]), "何雪萍": ("retail", ["何雪萍"]), "周信钢": ("retail", ["周信钢"]),
    "陈发树": ("retail", ["陈发树"]), "蒋仕波": ("retail", ["蒋仕波"]), "夏重阳": ("retail", ["夏重阳"]),
    "魏巍": ("retail", ["魏巍"]), "吕强": ("retail", ["吕强"]), "邹瀚枢": ("retail", ["邹瀚枢"]),
    "赵吉": ("retail", ["赵吉"]), "李欣": ("retail", ["李欣"]), "刘芳": ("retail", ["刘芳"]),
    "王萍": ("retail", ["王萍"]), "屠文斌": ("retail", ["屠文斌"]), "沈付兴": ("retail", ["沈付兴"]),
    "邱宝裕": ("retail", ["邱宝裕"]), "舒逸民": ("retail", ["舒逸民"]),
}
INST_SUFFIX = ["基金", "公司", "合伙", "资管", "信托", "银行", "证券", "投资", "理财", "保险", "有限", "集团", "控股", "资产管理", "财富"]

def is_institution(name):
    return any(k in name for k in INST_SUFFIX)

def scan_stock(rec):
    holders = rec.get("top10FloatShareholders") or []
    inc = dec = 0
    inc_shares = dec_shares = 0
    known = []  # (entity, type, action)
    for h in holders:
        hc = h.get("holdChange") or 0
        hn = (h.get("name") or "").strip()
        if hc > 0:
            inc += 1; inc_shares += hc
        elif hc < 0:
            dec += 1; dec_shares += -hc
        for ename, (t, kws) in MATCH.items():
            for kw in kws:
                if kw not in hn:
                    continue
                if t == "retail" and is_institution(hn):
                    continue
                action = "增持" if hc > 0 else ("减持" if hc < 0 else "持有")
                known.append((ename, t, action))
    net_w = (inc_shares - dec_shares) / 1e4
    inc_w = inc_shares / 1e4
    known_inc = sum(1 for _, _, a in known if a == "增持")
    known_dec = sum(1 for _, _, a in known if a == "减持")
    return {
        "code": rec.get("code"), "name": rec.get("name"),
        "inc": inc, "dec": dec, "net_w": round(net_w, 1), "inc_w": round(inc_w, 1),
        "known": known, "known_inc": known_inc, "known_dec": known_dec,
    }

def main():
    raw = json.load(open(SRC, encoding="utf-8"))
    data = raw.get("data", raw)
    rows = []
    for code, rec in data.items():
        r = scan_stock(rec)
        # 聚焦「净增持」股票：增持股东数 > 减持股东数（十大流通股东净买入主导），或知名主体在加仓
        if (r["inc"] > r["dec"]) or r["known_inc"] > 0:
            rows.append(r)
    # 排序：知名主体加仓数降序 → 净增持量降序
    rows.sort(key=lambda x: (-x["known_inc"], -x["net_w"]))
    n_total = len(data)
    n_show = len(rows)
    n_known = sum(1 for r in rows if r["known_inc"] > 0)

    def known_str(r):
        if not r["known"]:
            return ""
        # 去重展示 主体:动作
        seen = {}
        for e, t, a in r["known"]:
            seen.setdefault(e, a)
        return "、".join(f"{e}{a}" for e, a in seen.items())

    trs = []
    for i, r in enumerate(rows, 1):
        ks = known_str(r)
        kcls = "k-inc" if r["known_inc"] > 0 else ""
        trs.append(
            f'<tr class="{kcls}">'
            f'<td class="num">{i}</td>'
            f'<td class="stk">{esc(r["name"])}</td>'
            f'<td class="num">{esc(r["code"])}</td>'
            f'<td class="num up">{r["inc"]}</td>'
            f'<td class="num down">{r["dec"]}</td>'
            f'<td class="num" data-net="{r["net_w"]}">{r["net_w"]}</td>'
            f'<td class="num" data-inc="{r["inc_w"]}">{r["inc_w"]}</td>'
            f'<td class="kn">{"<span class=\"up\">"+ks+"</span>" if r["known_inc"]>0 else esc(ks)}</td>'
            f'</tr>')

    today = datetime.date.today().isoformat()
    html = f'''<!DOCTYPE html>
<html lang="zh-CN"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>股票增持信号扫描 · 中报十大股东</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:#f5f6f8;color:#23262b;font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;line-height:1.6}}
.topnav{{background:#fff;border-bottom:1px solid #e7e9ee;padding:10px 18px;display:flex;gap:14px;flex-wrap:wrap;font-size:13px}}
.topnav a{{color:#5a6270;text-decoration:none}}
.topnav a:hover{{color:#b8893b}}
.wrap{{max-width:1180px;margin:0 auto;padding:22px 18px 60px}}
header h1{{font-size:22px;margin-bottom:6px}}
.note{{background:#fff;border-left:4px solid #b8893b;border-radius:8px;padding:12px 16px;font-size:13px;color:#5a6270;margin:14px 0 6px}}
.note b{{color:#23262b}}
.sub{{color:#8a929c;font-size:13px;margin:8px 0 12px}}
.stat{{display:flex;gap:14px;flex-wrap:wrap;margin:10px 0}}
.stat .box{{background:#fff;border:1px solid #ecedf1;border-radius:10px;padding:10px 16px;min-width:120px}}
.stat .box .v{{font-size:20px;font-weight:700;color:#b8893b}}
.stat .box .l{{font-size:12px;color:#8a929c}}
.ptbl{{width:100%;border-collapse:collapse;font-size:12.5px;background:#fff;border:1px solid #ecedf1;border-radius:10px;overflow:hidden}}
.ptbl th{{background:#f3f4f7;color:#5a6270;text-align:right;padding:7px 10px;font-weight:600;cursor:pointer;white-space:nowrap;position:sticky;top:0}}
.ptbl th:hover{{color:#b8893b}}
.ptbl td{{padding:5px 10px;border-top:1px solid #f0f1f4;text-align:right;white-space:nowrap}}
.ptbl td.stk{{text-align:left;font-weight:600}}
.ptbl td.kn{{text-align:left;color:#5a6270}}
.ptbl td.num{{color:#4a515c}}
.up{{color:#b8332a;font-weight:600}}
.down{{color:#1a9e5a;font-weight:600}}
tr.k-inc{{background:#fff7f2}}
tr.k-inc td.stk{{color:#b8332a}}
footer{{text-align:center;color:#9aa1ab;font-size:12px;padding:24px}}
.disc{{background:#fff;border:1px dashed #d9c79a;border-radius:10px;padding:12px 16px;font-size:12px;color:#6b7280;margin-top:20px}}
</style></head>
<body>
<div class='topnav'>
  <a href="../market/index.html">每日总览</a>
  <a href="../lhb/lhb.html">龙虎榜分析</a>
  <a href="../market/hotmoney.html">游资看板</a>
  <a href="../sector/index.html">板块强度</a>
  <a href="2026-q2-industry-elite.html">股东动向</a>
  <a href="top-elite.html">玩家图谱</a>
  <a href="known-accumulation-health.html">健康度过滤</a>
  <a href="../exec/index.html">高管增减持</a>
  <a href="../block/index.html">大宗交易</a>
  <a href="../sections/index.html">版块总览</a>
  <a href="../../index.html">返回主页</a>
</div>
<div class="wrap">
  <header><h1>股票增持信号扫描 · 中报十大流通股东</h1>
    <div style="color:#8a929c;font-size:13px">直接复用全市场 {n_total} 只个股 2026-Q2 中报十大流通股东，统计每只股票的增持/减持力量，按「知名主体加仓优先 + 净增持量」排序，辅助快速发现具增持潜力的标的。</div>
  </header>
  <div class="note">
    <b>口径：</b>本页基于单季（2026-06-30 中报）十大流通股东数据，以「<b>增持</b>」作为可检测的买入信号。
    <b>关于「新进」：</b>单季快照的 <code>holdChange</code> 仅区分增持/减持/不变，<b>未单列「新进」标志</b>（新进主体被并入「不变」项），故无法在本页直接给出「大量新进」；若需严格新进，需对比 Q1 十大股东（当前数据源仅返回最新一期，不支持历史日期）。
    排序逻辑：先按「知名私募/牛散加仓数」降序（紫红高亮行 = 有知名主体加仓），再按「净增持(万股)」降序。
    <b>免责：</b>本页为股东行为的中性统计，<b>不构成任何投资建议</b>。
  </div>
  <div class="stat">
    <div class="box"><div class="v">{n_total}</div><div class="l">全市场样本(只)</div></div>
    <div class="box"><div class="v">{n_show}</div><div class="l">有增持信号(只)</div></div>
    <div class="box"><div class="v">{n_known}</div><div class="l">知名主体加仓(只)</div></div>
  </div>
  <div class="sub">点击表头可重排；红=增持/加仓，绿=减持。优先看紫色高亮行（知名资金在买）。</div>
  <table class="ptbl" id="stbl">
    <thead><tr>
      <th onclick="sortTbl(0)">#</th>
      <th onclick="sortTbl(1)">股票</th>
      <th onclick="sortTbl(2)">代码</th>
      <th onclick="sortTbl(3)">增持股东</th>
      <th onclick="sortTbl(4)">减持股东</th>
      <th onclick="sortTbl(5)">净增持(万)</th>
      <th onclick="sortTbl(6)">增持额(万)</th>
      <th onclick="sortTbl(7)">知名主体动作</th>
    </tr></thead>
    <tbody>{"".join(trs)}</tbody>
  </table>
  <div class="disc">⚠️ 免责声明：股东增减持仅反映中报时点的持仓变化，存在滞后与认知偏差；知名主体动作来自公开十大股东名称的关键词匹配，可能有遗漏或误匹配（已对自然人姓名剔除机构后缀）。本页仅作研究线索，<b>不构成买卖任何证券的建议</b>。</div>
  <footer>生成日期 {today} · 数据：全市场 {n_total} 只 2026-Q2 中报十大流通股东（直接复用，无新增行情调用）</footer>
</div>
<script>
function sortTbl(col){{
  var tbl=document.getElementById('stbl');
  var tb=tbl.tBodies[0];
  var rows=Array.from(tb.rows);
  var asc=tbl.getAttribute('data-asc')!=='1';
  var numCols={{3:'',4:'',5:'net',6:'inc'}};
  var keyf=function(r){{
    if(col===5)return parseFloat(r.children[5].getAttribute('data-net'))||0;
    if(col===6)return parseFloat(r.children[6].getAttribute('data-inc'))||0;
    if(col===3)return parseInt(r.children[3].textContent)||0;
    if(col===4)return parseInt(r.children[4].textContent)||0;
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
    print("written:", OUT, "bytes:", len(html), "| total:", n_total, "show:", n_show, "known-inc:", n_known)

def esc(s):
    return (s.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;"))

if __name__ == "__main__":
    main()
