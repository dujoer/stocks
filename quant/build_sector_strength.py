#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
生成「A股板块强度」每日交互式 HTML（增强展示版）。

用法:
  python build_sector_strength.py --daily quant/sector_daily/2026-08-28.json \
         --output web/sector-strength-20260828.html

特性:
  - 顶部 KPI 概览卡(板块数/暗盘净额/均强/抢筹/出货/涨跌比)
  - 强势板块 Top10 + 暗盘流入 Top10 迷你条
  - 表头点击排序、全局搜索、类型/行为/涨跌/强度区间筛选、导出 CSV、实时计数
  - 数据内联(JSON),完全离线可用
"""
import argparse, json, os

ROOT = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.normpath(os.path.join(ROOT, "..", "web"))


def fmt_yi(v):
    # v 单位: 元 -> 亿元, 带正负
    y = v / 1e8
    return ("+" if y > 0 else "") + format(y, ".2f")


def build_html(daily):
    date = daily["date"]
    s = daily["summary"]
    records = daily["records"]
    beh = s["behavior"]

    # KPI
    dark_cls = "up" if s["totalDarkY"] >= 0 else "down"
    kpi = f"""
    <div class="kpis">
      <div class="kpi"><div class="kpi-v">{s['sectorCount']}</div><div class="kpi-l">板块总数</div><div class="kpi-s">行业 {s['industryCount']} · 概念 {s['conceptCount']}</div></div>
      <div class="kpi"><div class="kpi-v {dark_cls}">{fmt_yi(s['totalDarkY']*1e8)}<span class="unit">亿</span></div><div class="kpi-l">全市场暗盘资金净额</div><div class="kpi-s">主力−散户 合计</div></div>
      <div class="kpi"><div class="kpi-v">{s['avgStrength']}</div><div class="kpi-l">平均板块强度</div><div class="kpi-s">暗盘/成交额×100</div></div>
      <div class="kpi"><div class="kpi-v c-qc">{beh['抢筹']}</div><div class="kpi-l">抢筹板块</div><div class="kpi-s">强度≥3</div></div>
      <div class="kpi"><div class="kpi-v c-ch">{beh['出货']}</div><div class="kpi-l">出货板块</div><div class="kpi-s">强度≤−1</div></div>
      <div class="kpi"><div class="kpi-v">{s['upRatio']}%<span class="unit">涨</span></div><div class="kpi-l">上涨占比</div><div class="kpi-s">涨 {s['upCount']} · 跌 {s['downCount']}</div></div>
    </div>"""

    # Top strips
    def top_strip(items, valkey, unit, valfmt):
        cells = []
        maxv = max((abs(it[valkey]) for it in items), default=1) or 1
        for it in items:
            v = it[valkey]
            w = abs(v) / maxv * 100 if maxv else 0
            cls = "up" if v >= 0 else "down"
            bar = f'<div class="tbar {cls}" style="width:{w:.1f}%"></div>'
            cells.append(
                f'<div class="trow"><span class="tname">{it["name"]}<i class="tkind">{it["kind"]}</i></span>'
                f'<span class="tval {cls}">{valfmt(v)}<span class="unit">{unit}</span></span></div>'
                f'<div class="ttrack">{bar}</div>')
        return "\n".join(cells)

    top_str = top_strip(s["topByStrength"], "strength", "", lambda v: f"{v:.2f}")
    top_dark = top_strip(s["topDarkMoney"], "darkY", "亿", lambda v: f"{v:+.2f}")

    data_json = json.dumps(records, ensure_ascii=False)

    html = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>A股板块强度 """ + date + """</title>
<style>
:root{
  --bg:#0b0f17; --panel:#121826; --panel2:#0e1420; --line:#1f2937; --txt:#e6edf3;
  --mut:#8b98a9; --up:#e0483b; --down:#1a9e5a; --gold:#e8b339; --qc:#e0483b; --ch:#1a9e5a;
  --jc:#e8b339; --xp:#5b8def;
}
*{box-sizing:border-box}
body{margin:0;background:linear-gradient(180deg,#0b0f17,#0a0d14);color:var(--txt);
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;
  font-size:13px;padding:22px 26px 60px}
h1{font-size:21px;margin:0 0 2px;letter-spacing:.5px}
.sub{color:var(--mut);font-size:12px;margin-bottom:16px}
.sub b{color:var(--gold)}
.up{color:var(--up)} .down{color:var(--down)} .c-qc{color:var(--qc)} .c-ch{color:var(--ch)} .c-jc{color:var(--jc)} .c-xp{color:var(--xp)}
.unit{font-size:10px;color:var(--mut);margin-left:2px}
.kpis{display:grid;grid-template-columns:repeat(6,1fr);gap:12px;margin-bottom:20px}
.kpi{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px 14px 12px;position:relative;overflow:hidden}
.kpi:before{content:"";position:absolute;left:0;top:0;bottom:0;width:3px;background:var(--gold);opacity:.55}
.kpi-v{font-size:23px;font-weight:700;line-height:1.1}
.kpi-l{color:var(--mut);font-size:11.5px;margin-top:6px}
.kpi-s{color:#5f6b7a;font-size:10.5px;margin-top:2px}
.strips{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:20px}
.strip{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px 16px}
.strip h3{margin:0 0 10px;font-size:13px;color:var(--gold);font-weight:600;letter-spacing:.5px}
.trow{display:flex;justify-content:space-between;align-items:baseline;margin-top:9px;font-size:12px}
.tname{color:var(--txt)} .tkind{font-style:normal;font-size:9.5px;color:var(--mut);border:1px solid var(--line);border-radius:4px;padding:0 4px;margin-left:5px}
.tval{font-weight:600;font-variant-numeric:tabular-nums}
.ttrack{height:5px;background:#0a0e16;border-radius:3px;overflow:hidden;margin:3px 0 2px}
.tbar{border-radius:3px}
.tbar.up{background:linear-gradient(90deg,#7a1d16,var(--up))}
.tbar.down{background:linear-gradient(90deg,#0d4d2c,var(--down))}
.controls{display:flex;flex-wrap:wrap;gap:10px;align-items:center;background:var(--panel2);
  border:1px solid var(--line);border-radius:12px;padding:12px 14px;margin-bottom:14px}
.controls input[type=text]{background:#0a0e16;border:1px solid var(--line);color:var(--txt);
  border-radius:8px;padding:7px 10px;width:200px;outline:none}
.controls input[type=text]:focus{border-color:var(--gold)}
.controls select{background:#0a0e16;border:1px solid var(--line);color:var(--txt);border-radius:8px;padding:7px 8px;outline:none}
.controls button{background:#1b2433;border:1px solid var(--line);color:var(--txt);border-radius:8px;padding:7px 12px;cursor:pointer}
.controls button:hover{border-color:var(--gold)}
.count{margin-left:auto;color:var(--mut);font-size:12px}
.count b{color:var(--gold)}
.tablewrap{background:var(--panel);border:1px solid var(--line);border-radius:12px;overflow:hidden}
table{width:100%;border-collapse:collapse}
th,td{padding:9px 12px;text-align:right;border-bottom:1px solid #161d2b;white-space:nowrap;font-variant-numeric:tabular-nums}
th{background:#0f1622;color:var(--mut);font-weight:600;cursor:pointer;user-select:none;position:sticky;top:0;font-size:12px}
th:hover{color:var(--gold)}
th.sorted:after{content:" " attr(data-arrow);color:var(--gold)}
td:first-child,th:first-child,td:nth-child(2),th:nth-child(2){text-align:left}
tbody tr:hover{background:#0f1622}
.rank{color:#5f6b7a;width:42px}
.sname{font-weight:600}
.skind{font-size:9.5px;color:var(--mut);border:1px solid var(--line);border-radius:4px;padding:0 4px;margin-left:5px}
.beh{padding:2px 8px;border-radius:20px;font-size:11px;font-weight:600}
.beh.q{background:rgba(224,72,59,.15);color:var(--qc)}
.beh.j{background:rgba(232,179,57,.15);color:var(--jc)}
.beh.x{background:rgba(91,141,239,.15);color:var(--xp)}
.beh.c{background:rgba(26,158,90,.15);color:var(--ch)}
.sbar{display:inline-block;height:6px;border-radius:3px;vertical-align:middle;margin-left:8px}
.note{color:var(--mut);font-size:11px;margin-top:14px;line-height:1.7}
.note code{background:#0a0e16;padding:1px 5px;border-radius:4px;color:var(--gold)}
@media(max-width:1100px){.kpis{grid-template-columns:repeat(3,1fr)}.strips{grid-template-columns:1fr}
  .hide-narrow{display:none}}
</style>
</head>
<body>
<h1>A股板块强度 <span style="color:var(--gold)">""" + date + """</span></h1>
<div class="sub">暗盘资金 = 主力资金 − 散户资金 ｜ 板块强度 = 暗盘资金 ÷ 总成交额 × 100 ｜ 主力行为:
  <b>抢筹</b>(≥3) <b>建仓</b>(1~3) <b>洗盘</b>(−1~1) <b>出货</b>(≤−1) ｜ 数据: westock 实时板块(最新快照)</div>
""" + kpi + """
<div class="strips">
  <div class="strip"><h3>★ 强势板块 Top 10（按强度）</h3>""" + top_str + """</div>
  <div class="strip"><h3>★ 暗盘资金流入 Top 10（亿元）</h3>""" + top_dark + """</div>
</div>
<div class="controls">
  <input type="text" id="search" placeholder="搜索板块 / 领涨股…">
  <select id="f-kind"><option value="">类型:全部</option><option value="行业">行业</option><option value="概念">概念</option></select>
  <select id="f-behavior"><option value="">行为:全部</option><option value="抢筹">抢筹</option><option value="建仓">建仓</option><option value="洗盘">洗盘</option><option value="出货">出货</option></select>
  <select id="f-dir"><option value="">涨跌:全部</option><option value="up">上涨</option><option value="down">下跌</option></select>
  <select id="f-strength"><option value="">强度:全部</option><option value="g10">≥10</option><option value="g5">≥5</option><option value="g3">≥3(抢筹级)</option><option value="l-1">≤−1(出货级)</option></select>
  <button id="reset">重置</button>
  <button id="csv">导出CSV</button>
  <span class="count">当前显示 <b id="cnt">0</b> / """ + str(len(records)) + """</span>
</div>
<div class="tablewrap">
<table id="t">
<thead><tr>
<th class="rank" data-k="idx">#</th>
<th data-k="name">板块 ⇅</th>
<th data-k="pctVal" title="涨幅%">涨幅 ⇅</th>
<th class="hide-narrow" data-k="totalVal" title="总成交额(元)">总成交额 ⇅</th>
<th data-k="mainVal" title="主力资金(元)">主力资金 ⇅</th>
<th data-k="retailVal" title="散户资金(元)">散户资金 ⇅</th>
<th data-k="darkVal" title="暗盘资金=主力−散户(元)">暗盘资金 ⇅</th>
<th data-k="strengthVal" title="板块强度=暗盘/总成交额×100">板块强度 ⇅</th>
<th data-k="behaviorRank">主力行为 ⇅</th>
<th class="hide-narrow" data-k="leader">领涨股</th>
</tr></thead>
<tbody id="tb"></tbody>
</table>
</div>
<div class="note">计算口径: 主力资金=<code>mainInflow</code> ｜ 散户资金=<code>mainOutflow</code> ｜ 暗盘资金=<code>mainNetInflow</code> ｜
强度=<code>暗盘资金 ÷ 总成交额 × 100</code>。金额由元换算为亿元展示。本页为当日真实板块快照，仅供研究参考，不构成投资建议。</div>
<script>
const DATA = """ + data_json + """;
const fmtYi = v => (v>=0?'+':'') + (v/1e8).toFixed(2);
const fmtPct = v => (v>0?'+':'') + v.toFixed(2) + '%';
const behClass = {'抢筹':'q','建仓':'j','洗盘':'x','出货':'c'};
const maxAbsStrength = Math.max.apply(null, DATA.map(r=>Math.abs(r.strengthVal||0))) || 1;
let sortKey='strengthVal', sortDir=-1;
function behRank(b){return {'抢筹':4,'建仓':3,'洗盘':2,'出货':1}[b]||0;}
function applyFilters(){
  const q=(document.getElementById('search').value||'').trim().toLowerCase();
  const k=document.getElementById('f-kind').value;
  const b=document.getElementById('f-behavior').value;
  const d=document.getElementById('f-dir').value;
  const st=document.getElementById('f-strength').value;
  let rows=DATA.filter(r=>{
    if(q && !(r.name.toLowerCase().includes(q) || (r.leader||'').toLowerCase().includes(q))) return false;
    if(k && r.kind!==k) return false;
    if(b && r.behavior!==b) return false;
    if(d==='up' && (r.pctVal||0)<=0) return false;
    if(d==='down' && (r.pctVal||0)>=0) return false;
    const sv=r.strengthVal||0;
    if(st==='g10' && sv<10) return false;
    if(st==='g5' && sv<5) return false;
    if(st==='g3' && sv<3) return false;
    if(st==='l-1' && sv>-1) return false;
    return true;
  });
  rows.sort((a,b)=>{
    let av=a[sortKey], bv=b[sortKey];
    if(sortKey==='name'){av=(av||'');bv=(bv||'');return av<bv?-sortDir:av>bv?sortDir:0;}
    if(sortKey==='behaviorRank'){av=behRank(a.behavior);bv=behRank(b.behavior);}
    if(sortKey==='idx'){av=DATA.indexOf(a);bv=DATA.indexOf(b);}
    av=av||0;bv=bv||0;return (av-bv)*sortDir;
  });
  render(rows);
}
function render(rows){
  const tb=document.getElementById('tb');tb.innerHTML='';
  rows.forEach((r,i)=>{
    const sv=r.strengthVal||0;
    const w=Math.abs(sv)/maxAbsStrength*60;
    const bc=sv>=0?'var(--up)':'var(--down)';
    const tr=document.createElement('tr');
    tr.innerHTML=
      '<td class="rank">'+(i+1)+'</td>'+
      '<td class="sname">'+r.name+'<i class="skind">'+r.kind+'</i></td>'+
      '<td class="'+(r.pctVal>0?'up':r.pctVal<0?'down':'')+'">'+fmtPct(r.pctVal||0)+'</td>'+
      '<td class="hide-narrow">'+(r.totalText||'')+'</td>'+
      '<td class="'+(r.mainVal>=0?'up':'down')+'">'+(r.mainText||'')+'</td>'+
      '<td class="'+(r.retailVal>=0?'up':'down')+'">'+(r.retailText||'')+'</td>'+
      '<td class="'+(r.darkVal>=0?'up':'down')+'">'+(r.darkText||'')+'</td>'+
      '<td><span class="'+(sv>=0?'up':'down')+'">'+(r.strengthText||'')+'</span>'+
        '<span class="sbar" style="width:'+w.toFixed(1)+'px;background:'+bc+'"></span></td>'+
      '<td><span class="beh '+behClass[r.behavior]+'">'+r.behavior+'</span></td>'+
      '<td class="hide-narrow">'+(r.leader||'')+'</td>';
    tb.appendChild(tr);
  });
  document.getElementById('cnt').textContent=rows.length;
}
document.querySelectorAll('th[data-k]').forEach(th=>{
  th.addEventListener('click',()=>{
    const k=th.getAttribute('data-k');
    if(sortKey===k){sortDir*=-1;}else{sortKey=k;sortDir=(k==='name'||k==='idx')?1:-1;}
    document.querySelectorAll('th').forEach(x=>x.classList.remove('sorted'));
    th.classList.add('sorted');
    th.setAttribute('data-arrow', sortDir>0?'▲':'▼');
    applyFilters();
  });
});
['search','f-kind','f-behavior','f-dir','f-strength'].forEach(id=>{
  document.getElementById(id).addEventListener('input',applyFilters);
  document.getElementById(id).addEventListener('change',applyFilters);
});
document.getElementById('reset').addEventListener('click',()=>{
  document.getElementById('search').value='';
  ['f-kind','f-behavior','f-dir','f-strength'].forEach(id=>document.getElementById(id).value='');
  sortKey='strengthVal';sortDir=-1;
  document.querySelectorAll('th').forEach(x=>x.classList.remove('sorted'));
  applyFilters();
});
document.getElementById('csv').addEventListener('click',()=>{
  const q=(document.getElementById('search').value||'').trim().toLowerCase();
  const k=document.getElementById('f-kind').value,b=document.getElementById('f-behavior').value,
        d=document.getElementById('f-dir').value,st=document.getElementById('f-strength').value;
  const rows=DATA.filter(r=>{
    if(q && !(r.name.toLowerCase().includes(q)||(r.leader||'').toLowerCase().includes(q)))return false;
    if(k&&r.kind!==k)return false; if(b&&r.behavior!==b)return false;
    if(d==='up'&&(r.pctVal||0)<=0)return false; if(d==='down'&&(r.pctVal||0)>=0)return false;
    const sv=r.strengthVal||0; if(st==='g10'&&sv<10)return false; if(st==='g5'&&sv<5)return false;
    if(st==='g3'&&sv<3)return false; if(st==='l-1'&&sv>-1)return false; return true;
  });
  const head=['板块','类型','涨幅%','总成交额(亿)','主力资金(亿)','散户资金(亿)','暗盘资金(亿)','板块强度','主力行为','领涨股'];
  const lines=[head.join(',')];
  rows.forEach(r=>lines.push([r.name,r.kind,(r.pctVal||0).toFixed(2),
    (r.totalVal/1e8).toFixed(2),(r.mainVal/1e8).toFixed(2),(r.retailVal/1e8).toFixed(2),
    (r.darkVal/1e8).toFixed(2),(r.strengthVal||0).toFixed(2),r.behavior,r.leader||''].join(',')));
  const blob=new Blob(['\uFEFF'+lines.join('\\n')],{type:'text/csv;charset=utf-8'});
  const a=document.createElement('a');a.href=URL.createObjectURL(blob);
  a.download='sector-strength-""" + date.replace('-','') + """.csv';a.click();
});
applyFilters();
</script>
</body>
</html>"""
    return html


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--daily", required=True)
    ap.add_argument("--output", default=None)
    args = ap.parse_args()
    daily = json.load(open(args.daily, encoding="utf-8"))
    date = daily["date"]
    out = args.output or os.path.join(WEB, "sector-strength-" + date.replace("-", "") + ".html")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    open(out, "w", encoding="utf-8").write(build_html(daily))
    print(f"[ok] 每日页 -> {out} ({len(daily['records'])} 板块)")


if __name__ == "__main__":
    main()
