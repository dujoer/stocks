#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
生成「A股板块强度 · 趋势看板」HTML。

结构:
  (A) 全市场聚合趋势: 日/周/月 + 主指标折线 + 主力行为折线 (读 sector_trend.json)
      最多展示最近 20 个交易日。
  (B) 单板块趋势下钻: 搜索板块 -> 该板块逐日 涨跌幅/暗盘资金/板块强度 折线,
      并在数据点标记当日领涨股, 下方给出逐日明细表。
  (C) 多板块对比: 多选板块 -> 同一指标的多线折线对比,
      实现"每个版块自己跟自己比、多个版块互相比"。

板块级序列由 sector_daily/*.json 真实累积而成 (前瞻累积, 不编造历史)。

用法:
  python build_sector_trend.py --trend quant/sector_trend.json --output ../web/sector-strength-trend.html
"""
import argparse, json, os, glob

ROOT = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.normpath(os.path.join(ROOT, "..", "web"))


def load_sectors(daily_dir):
    """扫描 sector_daily/*.json, 构建 板块名 -> {k:类型, p:[[date,pct,darkY,strength,behavior,leader],...]}"""
    sec = {}
    files = sorted(glob.glob(os.path.join(daily_dir, "*.json")))
    for f in files:
        try:
            d = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        date = d.get("date")
        if not date:
            continue
        for r in d.get("records", []):
            n = r.get("name")
            if not n:
                continue
            if n not in sec:
                sec[n] = {"k": r.get("kind", ""), "p": []}
            sec[n]["p"].append([
                date,
                round(r.get("pctVal") or 0, 2),
                round((r.get("darkVal") or 0) / 1e8, 2),   # 元 -> 亿
                round(r.get("strengthVal") or 0, 2),
                r.get("behavior") or "",
                r.get("leader") or "",
            ])
    for n in sec:
        sec[n]["p"].sort(key=lambda x: x[0])
    return sec


BH_COLOR = {"抢筹": "var(--qc)", "建仓": "var(--jc)", "洗盘": "var(--xp)", "出货": "var(--ch)"}


def existing_day_pages():
    """扫描 web/ 下已生成的每日页, 返回存在的日期列表 (YYYY-MM-DD), 用于日期链接点亮"""
    import re as _re
    days = []
    for f in glob.glob(os.path.join(WEB, "sector-strength-*.html")):
        m = _re.search(r"sector-strength-(\d{8})\.html$", f)
        if m:
            d = m.group(1)
            days.append(f"{d[:4]}-{d[4:6]}-{d[6:8]}")
    return days


def build_html(trend, sectors):
    trend_json = json.dumps(trend, ensure_ascii=False)
    sectors_json = json.dumps(sectors, ensure_ascii=False)
    existing_json = json.dumps(existing_day_pages(), ensure_ascii=False)
    html = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>A股板块强度 · 趋势看板</title>
<style>
:root{--bg:#f5f6f8;--panel:#ffffff;--panel2:#f0f2f5;--line:#e3e6ea;--txt:#23262b;
  --mut:#6b7280;--up:#b8332a;--down:#1a9e5a;--gold:#b8893b;--qc:#b8332a;--ch:#1a9e5a;
  --jc:#b8893b;--xp:#3b6fd1}
*{box-sizing:border-box}
body{margin:0;background:linear-gradient(180deg,#f5f6f8,#eef0f3);color:var(--txt);
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;
  font-size:13px;padding:22px 26px 80px}
h1{font-size:21px;margin:0 0 4px;letter-spacing:.5px;line-height:1.3}
.sub{color:var(--mut);font-size:12px;margin-bottom:18px;line-height:1.5}
.bar{display:flex;flex-wrap:wrap;gap:10px;align-items:center;background:var(--panel2);
  border:1px solid var(--line);border-radius:12px;padding:12px 14px;margin-bottom:16px}
.bar label{color:var(--mut);font-size:12px;margin-right:4px}
.bar select{background:#f0f2f5;border:1px solid var(--line);color:var(--txt);border-radius:8px;padding:7px 10px;outline:none}
.seg{display:inline-flex;border:1px solid var(--line);border-radius:8px;overflow:hidden}
.seg button{background:transparent;border:none;color:var(--mut);padding:7px 14px;cursor:pointer;font-size:12px}
.seg button.on{background:var(--gold);color:#1a1300;font-weight:700}
.cards{display:grid;grid-template-columns:repeat(5,1fr);gap:12px;margin-bottom:16px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:12px 14px}
.card .cl{color:var(--mut);font-size:11.5px}.card .cv{font-size:20px;font-weight:700;margin-top:5px}
.card .cs{color:#5f6b7a;font-size:10.5px;margin-top:2px}
.chartbox{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:18px 14px 14px;margin-bottom:18px;position:relative;overflow:visible}
.chartbox h3{margin:0 0 14px;font-size:13.5px;color:var(--gold);font-weight:600;line-height:1.45;word-break:break-all}
svg{display:block;width:100%;height:auto;overflow:visible}
.daylink{fill:#6b7280;cursor:default}
.daylink.live{cursor:pointer}
.daylink.live:hover{fill:var(--gold);text-decoration:underline}
.tip{position:absolute;pointer-events:none;background:#f0f2f5;border:1px solid var(--gold);
  border-radius:8px;padding:8px 12px;font-size:12px;color:var(--txt);opacity:0;transition:opacity .1s;z-index:10;white-space:nowrap;box-shadow:0 6px 20px rgba(0,0,0,.35)}
.tip b{color:var(--gold)}
.legend{display:flex;gap:16px;flex-wrap:wrap;color:var(--mut);font-size:11.5px;padding:6px 2px 4px}
.legend i{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:5px;vertical-align:middle}
.note{color:var(--mut);font-size:11px;margin-top:8px;line-height:1.8}
.secbar{display:flex;flex-wrap:wrap;gap:10px;align-items:center;background:var(--panel2);
  border:1px solid var(--line);border-radius:12px;padding:12px 14px;margin:8px 0 16px}
.secbar label{color:var(--mut);font-size:12px;margin-right:2px}
.secbar input{background:#f0f2f5;border:1px solid var(--line);color:var(--txt);border-radius:8px;padding:7px 12px;outline:none;min-width:240px}
.secbar select{background:#f0f2f5;border:1px solid var(--line);color:var(--txt);border-radius:8px;padding:7px 10px;outline:none}
.secbar .now{color:var(--gold);font-size:12px;margin-left:auto}
table{width:100%;border-collapse:collapse;font-size:12px;margin-top:4px}
table th,table td{padding:8px 10px;border-bottom:1px solid var(--line);text-align:right}
table th:first-child,table td:first-child{text-align:left}
table th{color:var(--mut);font-weight:600;font-size:11.5px}
table tr:hover td{background:#f0f2f5}
.bh{font-weight:700}
.ld{font-weight:600}
.divider{height:1px;background:var(--line);margin:24px 0 6px}

/* 多板块选择器 - 新布局 */
.cbar{background:var(--panel2);border:1px solid var(--line);border-radius:12px;padding:14px;margin:8px 0 18px}
.csel-wrap{display:flex;gap:14px;align-items:stretch;min-height:220px}
.csel-left{flex:1 1 55%;display:flex;flex-direction:column;min-width:0}
.csel-right{flex:1 1 45%;display:flex;flex-direction:column;min-width:0;background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:12px}
.csel-head{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin-bottom:12px}
.csel-head label{color:var(--mut);font-size:12px}
.csel-head select{background:#f0f2f5;border:1px solid var(--line);color:var(--txt);border-radius:8px;padding:7px 10px;outline:none}
.csel-head button{background:var(--panel2);border:1px solid var(--line);color:var(--mut);border-radius:8px;padding:6px 12px;cursor:pointer;font-size:12px}
.csel-head button:hover{border-color:var(--gold);color:var(--gold)}
.csel-head .hint{color:var(--mut);font-size:11.5px;margin-left:auto}
#csearch{width:100%;background:#f0f2f5;border:1px solid var(--line);color:var(--txt);border-radius:8px;padding:8px 12px;outline:none;margin-bottom:8px}
#csearch:focus{border-color:var(--gold)}
.candidates{flex:1;overflow-y:auto;background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:6px;max-height:260px}
.candidate{display:flex;align-items:center;justify-content:space-between;padding:6px 8px;border-radius:6px;cursor:pointer;font-size:12px;color:var(--txt)}
.candidate:hover{background:#1a2332}
.candidate .cname{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-right:8px}
.candidate .ckind{font-size:10.5px;color:var(--mut);flex-shrink:0}
.candidate .cadd{color:var(--gold);font-size:15px;margin-left:6px;flex-shrink:0}
.candidate.disabled{opacity:.45;cursor:not-allowed}
.selected-chips{display:flex;flex-wrap:wrap;gap:8px;align-content:flex-start;overflow-y:auto;max-height:180px}
.chip{display:inline-flex;align-items:center;gap:6px;background:#1a2332;border:1px solid var(--line);border-radius:16px;padding:5px 10px;font-size:12px;color:var(--txt)}
.chip .dot{width:8px;height:8px;border-radius:50%}
.chip .x{cursor:pointer;color:var(--mut);font-size:14px;line-height:1}
.chip .x:hover{color:var(--gold)}
.empty{display:flex;align-items:center;justify-content:center;height:160px;color:var(--mut);font-size:13px}

@media(max-width:1100px){
  .cards{grid-template-columns:repeat(2,1fr)}
  .csel-wrap{flex-direction:column;min-height:auto}
  .csel-left,.csel-right{width:100%}
  .candidates{max-height:200px}
}
@media(max-width:640px){
  body{padding:16px 14px 60px}
  .cards{grid-template-columns:1fr}
  .secbar .now{width:100%;margin-left:0;margin-top:6px}
}
</style>
</head>
<body>
<h1>A股板块强度 · <span style="color:var(--gold)">趋势看板</span></h1>
<div class="sub">每日盘后真实板块快照累积而成 ｜ 全市场聚合 + 单板块下钻 + 多板块对比 ｜ 数据随交易日自动变长（westock 最新快照）</div>

<!-- (A) 全市场聚合 -->
<div class="bar">
  <div class="seg" id="seg-period">
    <button data-p="day" class="on">日</button>
    <button data-p="week">周</button>
    <button data-p="month">月</button>
  </div>
  <label>主指标</label>
  <select id="metric">
    <option value="totalDarkY">全市场暗盘资金净额(亿)</option>
    <option value="avgStrength">平均板块强度</option>
    <option value="upRatio">上涨占比(%)</option>
    <option value="qiangchou">抢筹板块数</option>
    <option value="chuhuo">出货板块数</option>
  </select>
  <span id="ptext" style="color:var(--mut);font-size:12px;margin-left:auto"></span>
</div>
<div class="cards" id="cards"></div>
<div class="chartbox">
  <h3 id="mtitle">全市场暗盘资金净额(亿) · 日</h3>
  <div id="chart"></div>
  <div class="tip" id="tip"></div>
</div>
<div class="chartbox">
  <h3>主力行为分布趋势（抢筹 / 建仓 / 洗盘 / 出货 板块数）</h3>
  <div id="bhchart"></div>
  <div class="legend">
    <span><i style="background:var(--qc)"></i>抢筹</span>
    <span><i style="background:var(--jc)"></i>建仓</span>
    <span><i style="background:var(--xp)"></i>洗盘</span>
    <span><i style="background:var(--ch)"></i>出货</span>
  </div>
</div>

<div class="divider"></div>

<!-- (B) 单板块趋势下钻 -->
<div class="secbar">
  <label>板块</label>
  <input id="ssearch" list="slist" placeholder="输入或选择板块名…" autocomplete="off">
  <datalist id="slist"></datalist>
  <label>指标</label>
  <select id="smetric">
    <option value="pct">涨跌幅(%)</option>
    <option value="dark">暗盘资金(亿)</option>
    <option value="strength">板块强度</option>
  </select>
  <span class="now" id="snow"></span>
</div>
<div class="chartbox">
  <h3 id="stitle">板块逐日趋势</h3>
  <div id="schart"></div>
  <div class="tip" id="stip"></div>
</div>
<div class="chartbox">
  <h3>板块逐日明细 · 每日领涨股</h3>
  <div id="stable"></div>
</div>

<div class="divider"></div>

<!-- (C) 多板块对比 -->
<div class="cbar">
  <div class="csel-wrap">
    <div class="csel-left">
      <input type="text" id="csearch" placeholder="搜索板块名称…" autocomplete="off">
      <div id="ccandidates" class="candidates"></div>
    </div>
    <div class="csel-right">
      <div class="csel-head">
        <label>对比指标</label>
        <select id="cmetric">
          <option value="pct">涨跌幅(%)</option>
          <option value="dark">暗盘资金(亿)</option>
          <option value="strength">板块强度</option>
        </select>
        <button id="cclear">清空选择</button>
        <span class="hint">最多 8 个板块</span>
      </div>
      <div id="cselected" class="selected-chips"></div>
    </div>
  </div>
</div>
<div class="chartbox">
  <h3 id="ctitle">多板块对比 · 涨跌幅</h3>
  <div id="cchart"></div>
  <div class="tip" id="ctip"></div>
</div>

<div class="note">说明: 因 westock 板块接口 <code>date</code> 参数被忽略、只返回最新快照，历史某日数据无法回溯；本看板按"每日拉取日期"真实累积。
全市场聚合最多展示最近 20 个交易日；单板块/多板块对比最多展示最近 20 个数据点。超过 20 时自动截断为最新 20。
强度=暗盘资金÷总成交额×100。板块级数据来自各交易日 <code>sector_daily/*.json</code>，领涨股为当日该板块领涨个股。</div>
<script>
const TREND = """ + trend_json + """;
const SECTORS = """ + sectors_json + """;
const EXISTING_DAYS = """ + existing_json + """;
const W=960,H=380,PL=70,PR=40,PT=28,PB=58;
const MAX_DAYS=20;
// 固定间距: 每个交易日占一格, 20 个铺满图宽; 点从左侧挨着排, 后续交易日往右续
const PITCH=(W-PL-PR)/MAX_DAYS;
const METRIC_LABEL={totalDarkY:'全市场暗盘资金净额(亿)',avgStrength:'平均板块强度',
  upRatio:'上涨占比(%)',qiangchou:'抢筹板块数',chuhuo:'出货板块数'};
const SMETRIC_LABEL={pct:'涨跌幅(%)',dark:'暗盘资金(亿)',strength:'板块强度'};
const BH_NAME={'qiangchou':'抢筹','jiancang':'建仓','xipan':'洗盘','chuhuo':'出货'};
const BH_COLOR={'抢筹':'var(--qc)','建仓':'var(--jc)','洗盘':'var(--xp)','出货':'var(--ch)'};
const COMPARE_COLORS=['#b8332a','#1a9e5a','#b8893b','#3b6fd1','#a855f7','#22d3ee','#f97316','#ec4899'];
function goDay(date){ if(EXISTING_DAYS.indexOf(date)<0) return; const f='sector-strength-'+date.replace(/-/g,'')+'.html'; window.open(f,'_blank'); }
let period='day', metric='totalDarkY';
let sname=Object.keys(SECTORS).sort()[0], smetric='pct';
let cmetric='pct', cselected=[];

/* ---------- (A) 聚合 ---------- */
function monday(d){const x=new Date(d);const day=(x.getDay()+6)%7;x.setDate(x.getDate()-day);return x.toISOString().slice(0,10);}
function group(){
  if(period==='day') return TREND.map(t=>({label:t.date.slice(5),date:t.date,
    totalDarkY:t.totalDarkY,avgStrength:t.avgStrength,upRatio:t.upRatio,
    qiangchou:t.qiangchou,jiancang:t.jiancang,xipan:t.xipan,chuhuo:t.chuhuo,
    sectorCount:t.sectorCount,upCount:t.upCount,downCount:t.downCount}));
  const map={};
  TREND.forEach(t=>{
    let key = period==='week'? monday(t.date) : t.date.slice(0,7)+'-01';
    if(!map[key]) map[key]={label:key.slice(5),date:key,n:0,_dark:0,_str:0,_up:0,_qc:0,_jc:0,_xp:0,_ch:0,_sc:0,_uc:0,_dc:0};
    const m=map[key];m.n++;m._dark+=t.totalDarkY;m._str+=t.avgStrength;m._up+=t.upRatio;
    m._qc+=t.qiangchou;m._jc+=t.jiancang;m._xp+=t.xipan;m._ch+=t.chuhuo;m._sc+=t.sectorCount;
    m._uc+=t.upCount;m._dc+=t.downCount;
  });
  return Object.values(map).map(m=>({label:m.label,date:m.date,
    totalDarkY:m._dark, avgStrength:m._str/m.n, upRatio:m._up/m.n,
    qiangchou:m._qc, jiancang:m._jc, xipan:m._xp, chuhuo:m._ch,
    sectorCount:Math.round(m._sc/m.n), upCount:Math.round(m._uc/m.n), downCount:Math.round(m._dc/m.n)}))
    .sort((a,b)=>a.date<b.date?-1:1);
}
function stats(series){
  const vals=series.map(s=>s[metric]);
  const last=vals[vals.length-1], max=Math.max.apply(null,vals), min=Math.min.apply(null,vals);
  const avg=vals.reduce((a,b)=>a+b,0)/vals.length;
  return {last,max,min,avg};
}
function drawCards(series){
  const st=stats(series);
  const cards=document.getElementById('cards');
  const fmt=v=> (metric==='upRatio')? v.toFixed(1)+'%' : (metric==='avgStrength'||metric==='totalDarkY')? (v>=0?'+':'')+v.toFixed(2) : Math.round(v);
  const items=[
    ['最新',fmt(st.last)],['区间最高',fmt(st.max)],['区间最低',fmt(st.min)],
    ['区间均值',fmt(st.avg)],['数据点',series.length+(period==='day'?' 日':period==='week'?' 周':' 月')]
  ];
  cards.innerHTML=items.map(([l,v])=>`<div class="card"><div class="cl">${l}</div><div class="cv">${v}</div><div class="cs">${METRIC_LABEL[metric]}</div></div>`).join('');
}

// 通用单指标折线
function drawLine(series, containerId, tipId, {label, color='var(--gold)', zeroBaseline=true, fmt=null, dash=false}={}){
  const el=document.getElementById(containerId);
  const n=series.length;
  if(n===0){el.innerHTML='<div class="empty">暂无数据</div>';return;}
  const vals=series.map(s=>s.value);
  let lo=Math.min.apply(null,vals), hi=Math.max.apply(null,vals);
  if(zeroBaseline){ lo=Math.min(lo,0); hi=Math.max(hi,0); }
  if(lo===hi){lo-=1;hi+=1;}
  const pad=(hi-lo)*0.12; lo-=pad; hi+=pad;
  const x=i=> PL + PITCH*i;
  const y=v=> PT + (1-(v-lo)/(hi-lo))*(H-PT-PB);
  let g='';
  for(let k=0;k<=4;k++){const yy=PT+k*(H-PT-PB)/4;const vv=hi-(k/4)*(hi-lo);
    g+=`<line x1="${PL}" y1="${yy.toFixed(1)}" x2="${W-PR}" y2="${yy.toFixed(1)}" stroke="#161d2b"/>`;
    g+=`<text x="${PL-10}" y="${(yy+4).toFixed(1)}" fill="#5f6b7a" font-size="10" text-anchor="end">${fmt?fmt(vv):vv.toFixed(1)}</text>`;}
  let path='',area='';
  series.forEach((s,i)=>{const px=x(i),py=y(s.value);path+=(i?'L':'M')+px.toFixed(1)+' '+py.toFixed(1)+' ';});
  area=path+`L${x(n-1).toFixed(1)} ${(H-PB)} L${x(0).toFixed(1)} ${(H-PB)} Z`;
  let dots='',labels='';
  series.forEach((s,i)=>{const px=x(i),py=y(s.value);
    const col=s.value>=0?'var(--up)':'var(--down)'; dots+=`<circle cx="${px.toFixed(1)}" cy="${py.toFixed(1)}" r="3.5" fill="${col}" data-i="${i}"/>`;
    const dl=EXISTING_DAYS.indexOf(s.date)>=0;
    labels+=`<text class="daylink${dl?' live':''}" x="${px.toFixed(1)}" y="${H-PB+20}" font-size="10" text-anchor="middle" ${dl?`onclick="goDay('${s.date}')"`:''}>${s.label}</text>`;
  });
  const gid='g'+Math.random().toString(36).slice(2,7);
  el.innerHTML=`<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid meet">
    <defs><linearGradient id="${gid}" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="${color}" stop-opacity="0.28"/><stop offset="1" stop-color="${color}" stop-opacity="0"/>
    </linearGradient></defs>
    ${g}<path d="${area}" fill="url(#${gid})"/><path d="${path}" fill="none" stroke="${color}" stroke-width="2" stroke-dasharray="${dash?'4 3':'0'}"/>${dots}${labels}
    <line class="vline" x1="0" y1="${PT}" x2="0" y2="${H-PB}" stroke="var(--gold)" stroke-dasharray="3 3" opacity="0"/>
  </svg>`;
  const svg=el.querySelector('svg');const tip=document.getElementById(tipId);const vline=svg.querySelector('.vline');
  const rect=svg.getBoundingClientRect();
  const box=el.closest('.chartbox').getBoundingClientRect();
  svg.addEventListener('mousemove',e=>{
    const sx=(e.clientX-rect.left)/rect.width*W;
    let i=0,best=1e9;series.forEach((s,k)=>{const d=Math.abs(x(k)-sx);if(d<best){best=d;i=k;}});
    const s=series[i];const px=x(i),py=y(s.value);
    vline.setAttribute('x1',px);vline.setAttribute('x2',px);vline.setAttribute('opacity','0.6');
    tip.innerHTML=`<b>${s.date}</b><br>${label}: ${fmt?fmt(s.value):(s.value>=0?'+':'')+s.value.toFixed(2)}`;
    tip.style.opacity=1;
    tip.style.left=(e.clientX-box.left+12)+'px';tip.style.top=(e.clientY-box.top-10)+'px';
  });
  svg.addEventListener('mouseleave',()=>{tip.style.opacity=0;vline.setAttribute('opacity','0');});
}
function drawMain(series){
  const data=series.map(s=>({label:s.label,date:s.date,value:s[metric]}));
  const fmt=(v)=> metric==='upRatio'? v.toFixed(1)+'%' : (metric==='avgStrength'||metric==='totalDarkY')? (v>=0?'+':'')+v.toFixed(2): Math.round(v);
  drawLine(data,'chart','tip',{label:METRIC_LABEL[metric], color:'var(--gold)', fmt:fmt});
}

// 主力行为多线折线
function drawBehavior(series){
  const el=document.getElementById('bhchart');
  const n=series.length;
  if(n===0){el.innerHTML='<div class="empty">暂无数据</div>';return;}
  const keys=['qiangchou','jiancang','xipan','chuhuo'];
  const allv=[];series.forEach(s=>keys.forEach(k=>allv.push(s[k])));
  let lo=0, hi=Math.max.apply(null,allv);
  if(hi===0)hi=1;
  const pad=hi*0.12; hi+=pad;
  const x=i=> PL + PITCH*i;
  const y=v=> PT + (1-v/hi)*(H-PT-PB);
  let g='';
  for(let k=0;k<=4;k++){const yy=PT+k*(H-PT-PB)/4;const vv=hi-(k/4)*hi;
    g+=`<line x1="${PL}" y1="${yy.toFixed(1)}" x2="${W-PR}" y2="${yy.toFixed(1)}" stroke="#161d2b"/>`;
    g+=`<text x="${PL-10}" y="${(yy+4).toFixed(1)}" fill="#5f6b7a" font-size="10" text-anchor="end">${Math.round(vv)}</text>`;}
  let paths='',dots='',labels='';
  keys.forEach(k=>{
    const col=BH_COLOR[BH_NAME[k]];
    let d='';series.forEach((s,i)=>{d+=(i?'L':'M')+x(i).toFixed(1)+' '+y(s[k]).toFixed(1)+' ';});
    paths+=`<path d="${d}" fill="none" stroke="${col}" stroke-width="2.5"/>`;
    series.forEach((s,i)=>{dots+=`<circle cx="${x(i).toFixed(1)}" cy="${y(s[k]).toFixed(1)}" r="3" fill="${col}" data-k="${k}" data-i="${i}"/>`; });
  });
  series.forEach((s,i)=>{const dl=EXISTING_DAYS.indexOf(s.date)>=0;labels+=`<text class="daylink${dl?' live':''}" x="${x(i).toFixed(1)}" y="${H-PB+20}" font-size="10" text-anchor="middle" ${dl?`onclick="goDay('${s.date}')"`:''}>${s.label}</text>`; });
  el.innerHTML=`<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid meet">${g}${paths}${dots}${labels}
    <line class="vline" x1="0" y1="${PT}" x2="0" y2="${H-PB}" stroke="var(--gold)" stroke-dasharray="3 3" opacity="0"/>
  </svg>`;
  const tip=document.getElementById('tip');const box=el.closest('.chartbox').getBoundingClientRect();
  const svg=el.querySelector('svg');const vline=svg.querySelector('.vline');
  const rect=svg.getBoundingClientRect();
  svg.addEventListener('mousemove',e=>{
    const sx=(e.clientX-rect.left)/rect.width*W;
    let i=0,best=1e9;series.forEach((s,k)=>{const d=Math.abs(x(k)-sx);if(d<best){best=d;i=k;}});
    const s=series[i];const px=x(i);
    vline.setAttribute('x1',px);vline.setAttribute('x2',px);vline.setAttribute('opacity','0.6');
    let html=`<b>${s.date}</b>`;
    keys.forEach(k=>{html+=`<br><span style="color:${BH_COLOR[BH_NAME[k]]}">${BH_NAME[k]}</span>: ${s[k]} 个`; });
    tip.innerHTML=html;tip.style.opacity=1;
    tip.style.left=(e.clientX-box.left+12)+'px';tip.style.top=(e.clientY-box.top-10)+'px';
  });
  svg.addEventListener('mouseleave',()=>{tip.style.opacity=0;vline.setAttribute('opacity','0');});
}
function renderAgg(){
  const all=group();
  const series=all.slice(-MAX_DAYS);
  document.getElementById('mtitle').textContent=METRIC_LABEL[metric]+' · '+(period==='day'?'日':period==='week'?'周':'月');
  document.getElementById('ptext').textContent='共 '+all.length+' 个'+(period==='day'?'交易日':period==='week'?'自然周':'月')+' · 最近展示 '+series.length+' 个';
  drawCards(series);drawMain(series);drawBehavior(series);
}

/* ---------- (B) 单板块下钻 ---------- */
function sval(s){ return smetric==='pct'? s[1] : smetric==='dark'? s[2] : s[3]; }
function initSectorUI(){
  const dl=document.getElementById('slist');
  dl.innerHTML=Object.keys(SECTORS).sort().map(n=>`<option value="${n}">`).join('');
  const inp=document.getElementById('ssearch');
  inp.value=sname;
  inp.addEventListener('input',()=>{ const v=inp.value.trim(); if(SECTORS[v]){sname=v;renderSector();} });
  inp.addEventListener('change',()=>{ const v=inp.value.trim(); if(SECTORS[v]){sname=v;renderSector();} else {inp.value=sname;} });
  document.getElementById('smetric').addEventListener('change',e=>{smetric=e.target.value;renderSector();});
}
function renderSector(){
  const s=SECTORS[sname];
  const pts=s.p.slice(-MAX_DAYS);
  document.getElementById('snow').textContent=`${sname}（${s.k}）· ${s.p.length} 个交易日`+(s.p.length>MAX_DAYS?`（最近 ${MAX_DAYS} 天）`:'');
  document.getElementById('stitle').textContent=`${sname} · ${SMETRIC_LABEL[smetric]} 逐日趋势`;
  const n=pts.length;
  const vals=pts.map(sval);
  let lo=Math.min.apply(null,vals), hi=Math.max.apply(null,vals);
  if(smetric!=='strength'){ lo=Math.min(lo,0); hi=Math.max(hi,0); }
  if(lo===hi){lo-=1;hi+=1;}
  const pad=(hi-lo)*0.18; lo-=pad; hi+=pad;
  const x=i=> PL + PITCH*i;
  const y=v=> PT + (1-(v-lo)/(hi-lo))*(H-PT-PB);
  let g='';for(let k=0;k<=4;k++){const yy=PT+k*(H-PT-PB)/4;const vv=hi-(k/4)*(hi-lo);
    g+=`<line x1="${PL}" y1="${yy.toFixed(1)}" x2="${W-PR}" y2="${yy.toFixed(1)}" stroke="#161d2b"/>`;
    g+=`<text x="${PL-10}" y="${(yy+4).toFixed(1)}" fill="#5f6b7a" font-size="10" text-anchor="end">${vv.toFixed(2)}</text>`;}
  let path='',area='';
  pts.forEach((pt,i)=>{path+=(i?'L':'M')+x(i).toFixed(1)+' '+y(vals[i]).toFixed(1)+' ';});
  area=path+`L${x(n-1).toFixed(1)} ${(H-PB)} L${x(0).toFixed(1)} ${(H-PB)} Z`;
  let dots='',labels='',leads='';
  pts.forEach((pt,i)=>{const px=x(i),py=y(vals[i]);
    const col=vals[i]>=0?'var(--up)':'var(--down)';
    dots+=`<circle cx="${px.toFixed(1)}" cy="${py.toFixed(1)}" r="4" fill="${col}" data-i="${i}"/>`;
    const dl=EXISTING_DAYS.indexOf(pt[0])>=0;
    labels+=`<text class="daylink${dl?' live':''}" x="${px.toFixed(1)}" y="${H-PB+20}" font-size="10" text-anchor="middle" ${dl?`onclick="goDay('${pt[0]}')"`:''}>${pt[0].slice(5)}</text>`;
    if(pt[5] && n<=12){ const up=pt[5].indexOf('+')>=0; const lcol=up?'var(--up)':'var(--down)';
      leads+=`<text x="${px.toFixed(1)}" y="${(py-14).toFixed(1)}" fill="${lcol}" font-size="9.5" text-anchor="middle">${pt[5]}</text>`; }
  });
  const gid='sg'+Math.random().toString(36).slice(2,7);
  const el=document.getElementById('schart');
  el.innerHTML=`<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid meet">
    <defs><linearGradient id="${gid}" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#3b6fd1" stop-opacity="0.30"/><stop offset="1" stop-color="#3b6fd1" stop-opacity="0"/>
    </linearGradient></defs>
    ${g}<path d="${area}" fill="url(#${gid})"/><path d="${path}" fill="none" stroke="var(--xp)" stroke-width="2"/>${dots}${leads}${labels}
    <line class="vline" x1="0" y1="${PT}" x2="0" y2="${H-PB}" stroke="var(--xp)" stroke-dasharray="3 3" opacity="0"/>
  </svg>`;
  const svg=el.querySelector('svg');const tip=document.getElementById('stip');const vline=svg.querySelector('.vline');
  const rect=svg.getBoundingClientRect();
  svg.addEventListener('mousemove',e=>{
    const sx=(e.clientX-rect.left)/rect.width*W;
    let i=0,best=1e9;pts.forEach((pt,k)=>{const d=Math.abs(x(k)-sx);if(d<best){best=d;i=k;}});
    const pt=pts[i];const px=x(i),py=y(vals[i]);
    vline.setAttribute('x1',px);vline.setAttribute('x2',px);vline.setAttribute('opacity','0.6');
    const fv=(smetric==='pct'? vals[i].toFixed(2)+'%' : (vals[i]>=0?'+':'')+vals[i].toFixed(2));
    tip.innerHTML=`<b>${pt[0]}</b><br>${SMETRIC_LABEL[smetric]}: ${fv}<br>主力行为: <span style="color:${BH_COLOR[pt[4]]||'#fff'}">${pt[4]}</span><br>领涨股: <b style="color:${pt[5].indexOf('+')>=0?'var(--up)':'var(--down)'}">${pt[5]}</b>`;
    tip.style.opacity=1;const box=document.getElementById('schart').closest('.chartbox').getBoundingClientRect();
    tip.style.left=(e.clientX-box.left+12)+'px';tip.style.top=(e.clientY-box.top-10)+'px';
  });
  svg.addEventListener('mouseleave',()=>{tip.style.opacity=0;vline.setAttribute('opacity','0');});
  const rows=pts.map(pt=>{
    const up=pt[5].indexOf('+')>=0; const lcol=up?'var(--up)':'var(--down)';
    const bcol=BH_COLOR[pt[4]]||'#fff';
    const tdl=EXISTING_DAYS.indexOf(pt[0])>=0;
    return `<tr><td><span class="daylink${tdl?' live':''}" ${tdl?`onclick="goDay('${pt[0]}')"`:''}>${pt[0]}</span></td><td>${pt[1].toFixed(2)}%</td><td>${pt[2].toFixed(2)}</td><td>${pt[3].toFixed(2)}</td><td class="bh" style="color:${bcol}">${pt[4]}</td><td class="ld" style="color:${lcol}">${pt[5]}</td></tr>`;
  }).join('');
  document.getElementById('stable').innerHTML=`<table><tr><th>日期</th><th>涨跌幅</th><th>暗盘(亿)</th><th>强度</th><th>主力行为</th><th>领涨股</th></tr>${rows}</table>`;
}

/* ---------- (C) 多板块对比 ---------- */
function getLastStrength(n){
  const pts=SECTORS[n].p;
  if(!pts.length) return -Infinity;
  return pts[pts.length-1][3];
}
function getLastDate(){
  return Object.keys(SECTORS).reduce((d,n)=>{const pts=SECTORS[n].p;return pts.length?Math.max(d,pts[pts.length-1][0]):d;},'');
}
let allNamesSorted=[], rankedNames=[];
function initCompareUI(){
  allNamesSorted=Object.keys(SECTORS).sort();
  rankedNames=allNamesSorted.slice().sort((a,b)=>getLastStrength(b)-getLastStrength(a));
  document.getElementById('cmetric').addEventListener('change',e=>{cmetric=e.target.value;renderCompare();});
  document.getElementById('cclear').addEventListener('click',()=>{cselected=[];renderSelected();renderCompare();});
  document.getElementById('csearch').addEventListener('input',()=>renderCandidates());
  // 默认选中最近一个交易日强度最高的 5 个板块
  cselected=rankedNames.slice(0,5).filter(n=>getLastStrength(n)>-Infinity);
  renderSelected();renderCandidates();renderCompare();
}
function renderCandidates(){
  const box=document.getElementById('ccandidates');
  const q=document.getElementById('csearch').value.trim().toLowerCase();
  let list=q? allNamesSorted.filter(n=>n.toLowerCase().includes(q)) : rankedNames.slice(0,80);
  if(list.length===0){ box.innerHTML='<div class="empty" style="height:80px">无匹配板块</div>'; return; }
  const html=list.map(n=>{
    const sel=cselected.includes(n);
    const disabled=sel || cselected.length>=8;
    return `<div class="candidate ${disabled?'disabled':''}" data-name="${n}" title="${n}">
      <span class="cname">${n}</span>
      <span class="ckind">${SECTORS[n].k}</span>
      ${sel?'<span class="cadd">✓</span>':'<span class="cadd">+</span>'}
    </div>`;
  }).join('');
  box.innerHTML=html;
  box.querySelectorAll('.candidate:not(.disabled)').forEach(el=>{
    el.addEventListener('click',()=>{addCompare(el.getAttribute('data-name'));});
  });
}
function renderSelected(){
  const box=document.getElementById('cselected');
  if(cselected.length===0){ box.innerHTML='<div class="empty" style="height:80px">尚未选择板块，点击左侧添加</div>'; return; }
  box.innerHTML=cselected.map((n,i)=>{
    const color=COMPARE_COLORS[i % COMPARE_COLORS.length];
    return `<div class="chip" title="${n}">
      <span class="dot" style="background:${color}"></span>
      <span class="cname" style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:160px">${n}</span>
      <span class="x" data-name="${n}">×</span>
    </div>`;
  }).join('');
  box.querySelectorAll('.x').forEach(el=>{
    el.addEventListener('click',()=>removeCompare(el.getAttribute('data-name')));
  });
}
function addCompare(n){
  if(cselected.includes(n)) return;
  if(cselected.length>=8){ alert('最多选择 8 个板块进行对比'); return; }
  cselected.push(n);renderSelected();renderCandidates();renderCompare();
}
function removeCompare(n){
  cselected=cselected.filter(x=>x!==n);renderSelected();renderCandidates();renderCompare();
}
function cval(pt){ return cmetric==='pct'? pt[1] : cmetric==='dark'? pt[2] : pt[3]; }
function renderCompare(){
  document.getElementById('ctitle').textContent='多板块对比 · '+SMETRIC_LABEL[cmetric];
  const el=document.getElementById('cchart');
  if(cselected.length===0){el.innerHTML='<div class="empty">请在上方选择板块进行对比</div>';return;}
  const tip=document.getElementById('ctip');
  // 取所有选中板块在最近 MAX_DAYS 内的数据, 统一日期
  const dateSet={}; const lineData=[];
  cselected.forEach((n,idx)=>{
    const pts=SECTORS[n].p.slice(-MAX_DAYS);
    const color=COMPARE_COLORS[idx % COMPARE_COLORS.length];
    pts.forEach(pt=>{dateSet[pt[0]]=pt[0].slice(5);});
    lineData.push({name:n,color,pts});
  });
  const dates=Object.keys(dateSet).sort();
  const n=dates.length;
  // 为每条线生成按日期对齐的 value 数组
  lineData.forEach(line=>{
    const map={};line.pts.forEach(pt=>map[pt[0]]=cval(pt));
    line.values=dates.map(d=>map[d]!==undefined?map[d]:null);
  });
  // 计算Y轴范围 (忽略 null)
  const allv=[];lineData.forEach(line=>line.values.forEach(v=>{if(v!==null)allv.push(v);}));
  let lo=Math.min.apply(null,allv), hi=Math.max.apply(null,allv);
  if(cmetric!=='strength'){ lo=Math.min(lo,0); hi=Math.max(hi,0); }
  if(lo===hi){lo-=1;hi+=1;}
  const pad=(hi-lo)*0.15; lo-=pad; hi+=pad;
  const x=i=> PL + PITCH*i;
  const y=v=> PT + (1-(v-lo)/(hi-lo))*(H-PT-PB);
  let g='';
  for(let k=0;k<=4;k++){const yy=PT+k*(H-PT-PB)/4;const vv=hi-(k/4)*(hi-lo);
    g+=`<line x1="${PL}" y1="${yy.toFixed(1)}" x2="${W-PR}" y2="${yy.toFixed(1)}" stroke="#161d2b"/>`;
    g+=`<text x="${PL-10}" y="${(yy+4).toFixed(1)}" fill="#5f6b7a" font-size="10" text-anchor="end">${vv.toFixed(cmetric==='strength'?2:1)}</text>`;}
  let paths='',dots='',labels='',legend='';
  lineData.forEach((line,idx)=>{
    let d='';let hasStart=false;
    line.values.forEach((v,i)=>{if(v===null)return;if(!hasStart){d='M'+x(i).toFixed(1)+' '+y(v).toFixed(1);hasStart=true;}else{d+=' L'+x(i).toFixed(1)+' '+y(v).toFixed(1);}});
    if(d) paths+=`<path d="${d}" fill="none" stroke="${line.color}" stroke-width="2.5"/>`;
    line.values.forEach((v,i)=>{if(v!==null)dots+=`<circle cx="${x(i).toFixed(1)}" cy="${y(v).toFixed(1)}" r="3" fill="${line.color}" data-name="${line.name}" data-i="${i}"/>`; });
    legend+=`<span style="color:${line.color};margin-right:12px;font-size:11.5px">● ${line.name}</span>`;
  });
  dates.forEach((d,i)=>{const dl=EXISTING_DAYS.indexOf(d)>=0;labels+=`<text class="daylink${dl?' live':''}" x="${x(i).toFixed(1)}" y="${H-PB+20}" font-size="10" text-anchor="middle" ${dl?`onclick="goDay('${d}')"`:''}>${dateSet[d]}</text>`; });
  el.innerHTML=`<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid meet">${g}${paths}${dots}${labels}
    <line class="vline" x1="0" y1="${PT}" x2="0" y2="${H-PB}" stroke="var(--gold)" stroke-dasharray="3 3" opacity="0"/>
  </svg>`;
  const box=el.closest('.chartbox');
  box.querySelector('h3').innerHTML='多板块对比 · '+SMETRIC_LABEL[cmetric]+'<div style="margin-top:8px;line-height:1.6">'+legend+'</div>';
  const svg=el.querySelector('svg');const vline=svg.querySelector('.vline');
  const rect=svg.getBoundingClientRect();
  svg.addEventListener('mousemove',e=>{
    const sx=(e.clientX-rect.left)/rect.width*W;
    let i=0,best=1e9;dates.forEach((d,k)=>{const dx=Math.abs(x(k)-sx);if(dx<best){best=dx;i=k;}});
    const date=dates[i];const px=x(i);
    vline.setAttribute('x1',px);vline.setAttribute('x2',px);vline.setAttribute('opacity','0.6');
    let html=`<b>${date}</b>`;
    lineData.forEach(line=>{
      const v=line.values[i];
      if(v!==null){
        const fv=cmetric==='pct'? v.toFixed(2)+'%' : (v>=0?'+':'')+v.toFixed(2);
        html+=`<br><span style="color:${line.color}">●</span> ${line.name}: ${fv}`;
      }
    });
    tip.innerHTML=html;tip.style.opacity=1;
    tip.style.left=(e.clientX-box.getBoundingClientRect().left+12)+'px';
    tip.style.top=(e.clientY-box.getBoundingClientRect().top-10)+'px';
  });
  svg.addEventListener('mouseleave',()=>{tip.style.opacity=0;vline.setAttribute('opacity','0');});
}

/* ---------- 事件 ---------- */
document.querySelectorAll('#seg-period button').forEach(b=>b.addEventListener('click',()=>{
  document.querySelectorAll('#seg-period button').forEach(x=>x.classList.remove('on'));
  b.classList.add('on');period=b.getAttribute('data-p');renderAgg();
}));
document.getElementById('metric').addEventListener('change',e=>{metric=e.target.value;renderAgg();});

initSectorUI();
initCompareUI();
renderAgg();
renderSector();
</script>
</body>
</html>"""
    return html


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trend", required=True)
    ap.add_argument("--output", default=None)
    args = ap.parse_args()
    trend = json.load(open(args.trend, encoding="utf-8"))
    daily_dir = os.path.join(os.path.dirname(os.path.abspath(args.trend)), "sector_daily")
    sectors = load_sectors(daily_dir)
    out = args.output or os.path.join(WEB, "sector-strength-trend.html")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    open(out, "w", encoding="utf-8").write(build_html(trend, sectors))
    print(f"[ok] 趋势看板 -> {out} ({len(trend)} 交易日 | {len(sectors)} 板块可下钻)")


if __name__ == "__main__":
    main()
