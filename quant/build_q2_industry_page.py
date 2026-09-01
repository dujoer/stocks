# -*- coding: utf-8 -*-
"""
2026 中报 · 全市场行业「最强个人/私募/公募」榜
输入：quant/q2_full/_industry_ranking.json  _ind_valuation.json
输出：web/2026-q2-industry-elite.html（自包含单页，数据内嵌）
"""
import json, os, statistics as st

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE)
Q2 = os.path.join(BASE, "q2_full")

R = json.load(open(os.path.join(Q2, "_industry_ranking.json"), encoding="utf-8"))
V = json.load(open(os.path.join(Q2, "_ind_valuation.json"), encoding="utf-8"))
VAL_BY_IND = {r["ind"]: r for r in V["rows"]}
GROUPS = ("个人", "私募", "公募")

# ============================================================
# 行业四象限：聪明钱净增持 × 估值分位
# ============================================================
nets = [r["smart_net"] for r in R["ind_summary"]]
NET_MID = st.median(nets)
VAL_MID = 50

QUAD = {
    "A": ("资金进 · 估值低", "最优组合：机构与牛散同步加仓，且行业估值仍在全市场偏低区间", "qa"),
    "B": ("资金进 · 估值高", "资金追高：加仓明确但估值已偏贵，需靠业绩兑现消化", "qb"),
    "C": ("资金退 · 估值低", "冷门低估：便宜但缺乏增量资金，等催化剂", "qc"),
    "D": ("资金退 · 估值高", "高估失血：估值贵且聪明钱在撤，优先回避", "qd"),
}

def quad_of(net, vr):
    hi_net = net >= NET_MID
    lo_val = (vr is not None and vr < VAL_MID)
    if hi_net and lo_val: return "A"
    if hi_net: return "B"
    if lo_val: return "C"
    return "D"

ind_rows = []
for r in R["ind_summary"]:
    v = VAL_BY_IND.get(r["ind"], {})
    q = quad_of(r["smart_net"], v.get("val_rank"))
    ind_rows.append({
        "ind": r["ind"], "net": r["smart_net"],
        "p_net": r["个人"]["net"], "s_net": r["私募"]["net"], "f_net": r["公募"]["net"],
        "p_h": r["个人"]["holders"], "s_h": r["私募"]["holders"], "f_h": r["公募"]["holders"],
        "pe": v.get("pe_med"), "pb": v.get("pb_med"), "div": v.get("div_med"),
        "loss": v.get("loss_ratio"), "vr": v.get("val_rank"), "n": v.get("n"),
        "quad": q,
    })

# 榜单精简（去掉页面用不到的字段，压缩体积）
def slim(x):
    return {"nm": x["short"][:26], "mgr": x.get("mgr", ""), "n": x["n"],
            "inc": x["inc"], "dec": x["dec"], "flat": x["flat"],
            "pct": x["pct_sum"], "sc": x["score"],
            "b": x["s_breadth"], "p": x["s_power"], "d": x["s_depth"],
            "ind": x["ind"],
            "win": x.get("win"), "avg": x.get("avg"), "n_valid": x.get("n_valid"),
            "st": [{"n": s["name"], "c": s["code"], "d": s["d"], "p": s["pct"]}
                   for s in x["stocks"][:6]]}

DATA = {
    "date": R["date"],
    "val_date": V["date"],
    "universe": R["universe"],
    "records": sum(R["type_count"].values()),
    "type_count": R["type_count"],
    "summary": R["summary"],
    "net_mid": NET_MID,
    "ind_rows": ind_rows,
    "by_ind": {ind: {g: [slim(x) for x in R["by_ind"][ind][g][:20]] for g in GROUPS}
               for ind in R["by_ind"]},
    "all_top": {g: [slim(x) for x in R["all_top"][g][:20]] for g in GROUPS},
    "all_dec": {g: [slim(x) for x in R["all_dec"][g][:12]] for g in GROUPS},
}

TC = R["type_count"]
S = R["summary"]

# ============================================================
# 结论：A 象限行业 + 三类主体共振
# ============================================================
A_inds = [r for r in ind_rows if r["quad"] == "A"]
A_inds.sort(key=lambda r: -r["net"])
B_inds = sorted([r for r in ind_rows if r["quad"] == "B"], key=lambda r: -r["net"])[:5]
D_inds = sorted([r for r in ind_rows if r["quad"] == "D"], key=lambda r: r["net"])[:5]
# 三类主体同步净增持的行业（最强共振）
reso = [r for r in ind_rows if r["p_net"] > 0 and r["s_net"] > 0 and r["f_net"] > 0]
reso.sort(key=lambda r: -(r["p_net"] + r["s_net"] * 3 + r["f_net"] * 3))

NAV = """<div class='topnav'>
<a href='../index.html'>总门户</a><a href='index.html'>看板首页</a>
<a href='daily_overview.html'>每日总览</a><a href='lhb.html'>龙虎榜分析</a>
<a href='sector-strength-index.html'>板块强度</a>
<a href='2026-q2-shareholder-moves.html'>中报股东动向</a>
</div>"""


def cls(v):
    return "up" if v > 0 else ("down" if v < 0 else "flat")


def sign(v):
    return f"+{v}" if v > 0 else str(v)


# ---------- 行业四象限表 ----------
rows_html = []
for r in sorted(ind_rows, key=lambda x: -x["net"]):
    q = QUAD[r["quad"]]
    rows_html.append(
        f"<tr><td><b>{r['ind']}</b><span class='tiny'> {r['n']}只</span></td>"
        f"<td class='num {cls(r['net'])}'>{sign(r['net'])}</td>"
        f"<td class='num {cls(r['p_net'])}'>{sign(r['p_net'])}</td>"
        f"<td class='num {cls(r['s_net'])}'>{sign(r['s_net'])}</td>"
        f"<td class='num {cls(r['f_net'])}'>{sign(r['f_net'])}</td>"
        f"<td class='num'>{r['pe'] if r['pe'] else '—'}</td>"
        f"<td class='num'>{r['pb'] if r['pb'] else '—'}</td>"
        f"<td class='num'>{r['loss']}%</td>"
        f"<td class='num'><span class='vrbar'><i style='width:{r['vr'] or 0}%'></i></span>"
        f"<span class='tiny'>{r['vr']}</span></td>"
        f"<td><span class='qtag {q[2]}'>{q[0]}</span></td></tr>")
IND_TABLE = "".join(rows_html)


def _fmt_win(x):
    return "—" if x.get("win") is None else f"{x['win']:.0f}%"


def _fmt_avg(x):
    return "—" if x.get("avg") is None else f"{'+' if x['avg'] > 0 else ''}{x['avg']:.1f}%"


def top_table(lst, g):
    """全市场榜表格"""
    out = []
    for i, x in enumerate(lst, 1):
        if x["mgr"]:
            nm_cell = f"<b>{x['nm']}</b><br><span class='tiny'>· {x['mgr']}</span>"
        else:
            nm_cell = f"<b>{x['nm']}</b>"
        out.append(
            f"<tr><td class='num rk'>{i}</td>"
            f"<td class='nm'>{nm_cell}<br><span class='tiny'>{x['ind']}</span></td>"
            f"<td class='num'>{x['n']}</td>"
            f"<td class='num up'>{x['inc']}</td>"
            f"<td class='num down'>{x['dec']}</td>"
            f"<td class='num'>{x['pct']:.2f}%</td>"
            f"<td class='num sc'>{x['sc']:.2f}</td>"
            f"<td class='num win'>{_fmt_win(x)}</td>"
            f"<td class='num avg'>{_fmt_avg(x)}</td></tr>")
    head = ("<tr><th class='num'>#</th><th>"
            + ("自然人" if g == "个人" else "产品 · 管理人")
            + "</th><th class='num'>家数</th><th class='num'>增</th>"
              "<th class='num'>减</th><th class='num'>合计持股</th><th class='num'>强度</th>"
              "<th class='num'>胜率*</th><th class='num'>均涨*</th></tr>")
    return f"<table class='rk3'>{head}{''.join(out)}</table>"


TOP_BLOCKS = "".join(
    f"<div class='tabpane' data-g='{g}'>{top_table(DATA['all_top'][g], g)}</div>"
    for g in GROUPS)
DEC_BLOCKS = "".join(
    f"<div class='tabpane2' data-g='{g}'>{top_table(DATA['all_dec'][g], g)}</div>"
    for g in GROUPS)

PILLS = "".join(
    f"<button class='pill' data-ind='{r['ind']}'>{r['ind']}"
    f"<span class='pn {cls(r['net'])}'>{sign(r['net'])}</span></button>"
    for r in sorted(ind_rows, key=lambda x: -x["net"]))

A_LIST = "、".join(f"<b>{r['ind']}</b>（净{sign(r['net'])}／估值分位{r['vr']}）" for r in A_inds[:8]) or "无"
B_LIST = "、".join(f"{r['ind']}（净{sign(r['net'])}／分位{r['vr']}）" for r in B_inds) or "无"
D_LIST = "、".join(f"{r['ind']}（净{sign(r['net'])}／分位{r['vr']}）" for r in D_inds) or "无"
RESO_LIST = "、".join(
    f"<b>{r['ind']}</b>（个人{sign(r['p_net'])}／私募{sign(r['s_net'])}／公募{sign(r['f_net'])}）"
    for r in reso[:6]) or "无"

CSS = """
* { box-sizing:border-box; }
body { margin:0; font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;
  background:linear-gradient(135deg,#1a1f2e 0%,#232838 45%,#1a1f2e 100%); color:#f0e6dd; min-height:100vh; }
.wrap { max-width:1180px; margin:0 auto; padding:40px 20px 70px; }
.topnav { display:flex; flex-wrap:wrap; gap:8px; margin-bottom:18px; padding-bottom:14px;
  border-bottom:1px solid rgba(255,255,255,.10); }
.topnav a { color:#c9a66b; text-decoration:none; font-size:13px; padding:4px 12px; border-radius:20px;
  border:1px solid rgba(201,166,107,.30); transition:.2s; }
.topnav a:hover { background:rgba(201,166,107,.14); }
header h1 { font-size:29px; margin:0 0 6px; background:linear-gradient(90deg,#c9a66b,#c98b7d,#a899b3);
  -webkit-background-clip:text; background-clip:text; color:transparent; font-weight:800; }
header p { margin:4px 0; color:#9a9aa4; font-size:13px; line-height:1.6; }
.meta { margin:12px 0 22px; font-size:12px; color:#c9c3b8; line-height:1.7; }
.meta b { color:#c9a66b; }
.section { background:linear-gradient(135deg,rgba(255,255,255,.07),rgba(255,255,255,.03));
  border:1px solid rgba(255,255,255,.10); border-radius:20px; padding:18px 20px; margin:0 0 22px;
  box-shadow:0 4px 20px rgba(0,0,0,.15), inset 0 1px 0 rgba(255,255,255,.05); }
.section h2 { font-size:17px; margin:0 0 8px; color:#f7f1ec; display:flex; align-items:center; gap:8px; }
.section h2:before { content:""; width:4px; height:16px; background:#c9a66b; border-radius:3px; }
.sub2 { font-size:13px; color:#c9c3b8; margin:2px 0 10px; line-height:1.7; }
.chiprow { display:flex; flex-wrap:wrap; gap:10px; margin:10px 0; }
.chip { flex:1; min-width:112px; background:linear-gradient(135deg,rgba(185,116,104,.18),rgba(220,38,38,.06));
  border:1px solid rgba(201,139,125,.36); border-radius:14px; padding:12px 10px; text-align:center; }
.chip.g { background:linear-gradient(135deg,rgba(141,168,148,.18),rgba(16,122,87,.06));
  border-color:rgba(141,168,148,.36); }
.chip.n { background:linear-gradient(135deg,rgba(201,166,107,.16),rgba(201,166,107,.04));
  border-color:rgba(201,166,107,.34); }
.chip .k { font-size:11px; color:#c9c3b8; }
.chip .v { font-size:21px; font-weight:800; color:#f7f1ec; margin:3px 0 1px; }
.chip .hl { font-size:10px; color:#9a9aa4; }
table { width:100%; border-collapse:collapse; font-size:13px; background:rgba(26,31,46,.55);
  border:1px solid rgba(255,255,255,.08); border-radius:12px; overflow:hidden; margin:8px 0; }
th,td { padding:7px 10px; text-align:left; border-bottom:1px solid rgba(255,255,255,.07); }
th { background:rgba(30,41,59,.8); color:#e6ded6; font-weight:600; font-size:12px; }
tr:last-child td { border-bottom:none; }
td.num,th.num { text-align:right; font-variant-numeric:tabular-nums; }
.up { color:#e39a8c; font-weight:700; } .down { color:#8fc4a3; font-weight:700; }
.flat { color:#9a9aa4; }
.tiny { font-size:11px; color:#9a9aa4; font-weight:400; }
.rk { color:#c9a66b; font-weight:800; }
.sc { color:#e9d8b8; font-weight:800; }
.note { color:#9a9aa4; font-size:12px; margin-top:8px; line-height:1.7; }
.amberbox { font-size:13px; color:#e9d8b8; background:linear-gradient(135deg,rgba(201,166,107,.13),rgba(201,166,107,.05));
  border:1px solid rgba(201,166,107,.22); border-radius:12px; padding:12px 16px; margin:12px 0; line-height:1.8; }
.amberbox b { color:#c9a66b; }
.upbox { border-left:4px solid #c98b7d; } .downbox { border-left:4px solid #8da894; }
.vrbar { display:inline-block; width:52px; height:7px; background:rgba(255,255,255,.10);
  border-radius:4px; overflow:hidden; vertical-align:middle; margin-right:5px; }
.vrbar i { display:block; height:100%; background:linear-gradient(90deg,#8fc4a3,#c9a66b,#e39a8c); }
.qtag { font-size:11px; padding:3px 8px; border-radius:10px; white-space:nowrap; font-weight:700; }
.qa { background:rgba(185,116,104,.26); color:#f0b8a8; border:1px solid rgba(227,154,140,.45); }
.qb { background:rgba(201,166,107,.20); color:#e0c48d; border:1px solid rgba(201,166,107,.40); }
.qc { background:rgba(168,153,179,.20); color:#c9bcd6; border:1px solid rgba(168,153,179,.40); }
.qd { background:rgba(141,168,148,.20); color:#a8ccb5; border:1px solid rgba(141,168,148,.40); }
.tabs { display:flex; gap:8px; margin:10px 0 4px; flex-wrap:wrap; }
.tab { background:rgba(255,255,255,.06); border:1px solid rgba(255,255,255,.14); color:#c9c3b8;
  font-size:13px; padding:6px 16px; border-radius:18px; cursor:pointer; transition:.2s; font-family:inherit; }
.tab:hover { background:rgba(201,166,107,.14); }
.tab.on { background:rgba(201,166,107,.24); border-color:rgba(201,166,107,.55); color:#f7f1ec; font-weight:700; }
.tabpane,.tabpane2 { display:none; } .tabpane.on,.tabpane2.on { display:block; }
.pills { display:flex; flex-wrap:wrap; gap:6px; margin:10px 0 14px; }
.pill { background:rgba(255,255,255,.05); border:1px solid rgba(255,255,255,.12); color:#c9c3b8;
  font-size:12px; padding:5px 11px; border-radius:16px; cursor:pointer; transition:.18s;
  font-family:inherit; display:flex; align-items:center; gap:5px; }
.pill:hover { background:rgba(201,166,107,.12); border-color:rgba(201,166,107,.35); }
.pill.on { background:rgba(201,166,107,.26); border-color:rgba(201,166,107,.6); color:#f7f1ec; font-weight:700; }
.pn { font-size:10px; }
.grid3 { display:grid; grid-template-columns:repeat(auto-fit,minmax(470px,1fr)); gap:14px; margin-top:6px; }
.gcard { background:rgba(26,31,46,.5); border:1px solid rgba(255,255,255,.09); border-radius:14px; padding:12px 13px; }
.gcard h3 { margin:0 0 3px; font-size:14px; color:#f7f1ec; display:flex; align-items:center; gap:7px; }
.gcard h3 em { font-style:normal; font-size:11px; color:#9a9aa4; font-weight:400; }
.dot { width:8px; height:8px; border-radius:50%; display:inline-block; }
.d1 { background:#e39a8c; } .d2 { background:#c9a66b; } .d3 { background:#a899b3; }
.rk3 { font-size:12px; }
.rk3 th,.rk3 td { padding:5px 7px; }
.rk3 tbody tr { cursor:pointer; }
.rk3 td.nm { min-width:140px; white-space:normal; word-break:break-word; line-height:1.35; }
.rk3 td.nm b { display:inline-block; }
.win { color:#e9d8b8; font-weight:800; } .avg { color:#e9d8b8; font-weight:800; }
.sortbar { display:flex; gap:6px; margin:7px 0 6px; }
.sbtn { background:rgba(255,255,255,.06); border:1px solid rgba(255,255,255,.14); color:#c9c3b8;
  font-size:11px; padding:3px 11px; border-radius:14px; cursor:pointer; font-family:inherit; transition:.2s; }
.sbtn:hover { background:rgba(201,166,107,.14); }
.sbtn.on { background:rgba(201,166,107,.26); border-color:rgba(201,166,107,.55); color:#f7f1ec; font-weight:700; }
.rowdet { background:rgba(201,166,107,.06); font-size:11px; color:#c9c3b8; }
.rowdet td { padding:7px 10px; }
.sbadge { display:inline-block; margin:2px 4px 2px 0; padding:2px 7px; border-radius:8px;
  background:rgba(255,255,255,.07); border:1px solid rgba(255,255,255,.12); font-size:11px; }
.empty { color:#9a9aa4; font-size:12px; padding:14px 4px; }
.legend { display:flex; flex-wrap:wrap; gap:12px; font-size:11px; color:#9a9aa4; margin-top:8px; }
@media(max-width:700px){ .wrap{padding:24px 12px 50px;} header h1{font-size:22px;}
  table{font-size:11.5px;} th,td{padding:5px 6px;} .grid3{grid-template-columns:1fr;} }
"""

JS = """
const D = __DATA__;
const GS = ['个人','私募','公募'];
let sortKey='sc';
let currentInd=null;
function sortList(list){
  const a=(list||[]).slice();
  if(sortKey==='win')
    a.sort((x,y)=> ((y.win==null?-1:y.win)-(x.win==null?-1:x.win)) || (y.sc-x.sc));
  else
    a.sort((x,y)=> (y.sc-x.sc) || ((y.win==null?-1:y.win)-(x.win==null?-1:x.win)));
  return a;
}

/* --- 全市场榜 / 减持榜 tab --- */
function bindTabs(tabSel, paneSel){
  document.querySelectorAll(tabSel).forEach(t=>{
    t.onclick=()=>{
      document.querySelectorAll(tabSel).forEach(x=>x.classList.remove('on'));
      t.classList.add('on');
      document.querySelectorAll(paneSel).forEach(p=>
        p.classList.toggle('on', p.dataset.g===t.dataset.g));
    };
  });
}
bindTabs('.tab[data-scope=top]','.tabpane');
bindTabs('.tab[data-scope=dec]','.tabpane2');

/* --- 行业三榜 --- */
const DOT={'个人':'d1','私募':'d2','公募':'d3'};
const CAP={'个人':'自然人（牛散）','私募':'私募证券基金','公募':'公募主动基金'};

function fmtD(v){
  if(!v) return "<span class='flat'>持平</span>";
  const s=(v>0?'+':'')+(Math.abs(v)>=1e8?(v/1e8).toFixed(2)+'亿股'
        :Math.abs(v)>=1e4?(v/1e4).toFixed(1)+'万股':v+'股');
  return "<span class='"+(v>0?'up':'down')+"'>"+s+"</span>";
}
function fmtWin(x){
  if(x.win==null) return "<span class='flat'>—</span>";
  return Math.round(x.win)+"%";
}
function fmtAvg(x){
  if(x.avg==null) return "<span class='flat'>—</span>";
  const cls = x.avg>0?'up':x.avg<0?'down':'flat';
  return "<span class='"+cls+"'>"+(x.avg>0?'+':'')+x.avg.toFixed(1)+"%</span>";
}

function rowsOf(list, g){
  if(!list||!list.length) return "<div class='empty'>本行业该类型无符合口径的股东记录</div>";
  let h="<table class='rk3'><tr><th class='num'>#</th><th>"
      +(g==='个人'?'自然人':'产品 · 管理人')
      +"</th><th class='num'>家数</th><th class='num'>增</th><th class='num'>减</th>"
      +"<th class='num'>持股</th><th class='num'>强度</th>"
      +"<th class='num'>胜率*</th><th class='num'>均涨*</th></tr>";
  list.forEach((x,i)=>{
    const nm = x.mgr
      ? "<b>"+x.nm+"</b><br><span class='tiny'>· "+x.mgr+"</span>"
      : "<b>"+x.nm+"</b>";
    h+="<tr data-k='"+g+i+"'><td class='num rk'>"+(i+1)+"</td><td class='nm'>"+nm+"</td>"
      +"<td class='num'>"+x.n+"</td><td class='num up'>"+x.inc+"</td>"
      +"<td class='num down'>"+x.dec+"</td><td class='num'>"+x.pct.toFixed(2)+"%</td>"
      +"<td class='num sc'>"+x.sc.toFixed(2)+"</td>"
      +"<td class='num win'>"+fmtWin(x)+"</td>"
      +"<td class='num avg'>"+fmtAvg(x)+"</td></tr>";
    const det = x.st.map(s=>"<span class='sbadge'>"+s.n+" "+s.p+"% "+fmtD(s.d)+"</span>").join('');
    h+="<tr class='rowdet' data-p='"+g+i+"' style='display:none'><td></td><td colspan='8'>"
      +"持仓：" + det
      + "<br><span class='tiny'>强度拆解 → 广度 "+x.b.toFixed(2)+" ／ 加仓力度 "+x.p.toFixed(2)
      + " ／ 介入深度 "+x.d.toFixed(2)+"（持平 "+x.flat+" 家）</span></td></tr>";
  });
  return h+"</table>";
}

function renderInd(ind){
  currentInd = ind;
  const d=D.by_ind[ind]||{};
  const r=D.ind_rows.find(x=>x.ind===ind)||{};
  document.getElementById('indTitle').innerHTML =
    "<b>"+ind+"</b> · 聪明钱净增持 <span class='"+(r.net>0?'up':r.net<0?'down':'flat')+"'>"
    +(r.net>0?'+':'')+r.net+"</span> 家次 · PE中位 "+(r.pe||'—')
    +" · 估值分位 "+(r.vr!=null?r.vr:'—')+" · 成分股 "+(r.n||'—')+" 只";
  document.getElementById('indBody').innerHTML = GS.map(g=>
    "<div class='gcard'><h3><span class='dot "+DOT[g]+"'></span>"+g+" Top20<em>"+CAP[g]+"</em></h3>"
    + "<div class='sortbar'>"
    + "<button class='sbtn"+(sortKey==='sc'?' on':'')+"' data-sk='sc'>按强度</button>"
    + "<button class='sbtn"+(sortKey==='win'?' on':'')+"' data-sk='win'>按胜率*</button>"
    + "</div>"
    + rowsOf(sortList(d[g]||[]), g) + "</div>").join('');
  document.querySelectorAll('#indBody tr[data-k]').forEach(tr=>{
    tr.onclick=()=>{
      const p=document.querySelector("#indBody tr[data-p='"+tr.dataset.k+"']");
      if(p) p.style.display = p.style.display==='none'? '' : 'none';
    };
  });
  document.querySelectorAll('#indBody .sbtn').forEach(b=>{
    b.onclick=()=>{ sortKey=b.dataset.sk; renderInd(currentInd); };
  });
}

document.querySelectorAll('.pill').forEach(b=>{
  b.onclick=()=>{
    document.querySelectorAll('.pill').forEach(x=>x.classList.remove('on'));
    b.classList.add('on');
    renderInd(b.dataset.ind);
  };
});
const first=document.querySelector('.pill');
if(first){ first.classList.add('on'); renderInd(first.dataset.ind); }
"""

HTML = f"""<!DOCTYPE html>
<html lang='zh-CN'>
<head>
<meta charset='UTF-8'>
<meta name='viewport' content='width=device-width,initial-scale=1.0'>
<title>2026中报 · 全市场行业最强个人/私募/公募榜</title>
<style>{CSS}</style>
</head>
<body>
<div class='wrap'>
{NAV}
<header>
<h1>2026 中报 · 全市场行业最强「个人 / 私募 / 公募」榜</h1>
<p>覆盖 <b>沪深北全部 {DATA['universe']} 只 A 股</b>的 2026-06-30 十大股东与十大流通股东，
逐一分类后按申万一级行业聚合，输出 31 个行业各自的最强自然人、私募、公募各 20 名。</p>
</header>

<div class='meta'>
股东数据基准日 <b>{DATA['date']}</b>（2026 年中报）　估值数据基准日 <b>{DATA['val_date']}</b>　
样本口径 <b>{DATA['universe']} 只 / {DATA['records']:,} 条股东记录</b>　
行业分类 <b>申万一级 31 个行业</b>　行业映射覆盖 <b>{R['mapped']}/{DATA['universe']}</b>
</div>

<div class='section'>
<h2>口径说明：这一版是全市场，不是抽样</h2>
<div class='sub2'>上一版页面只覆盖 121 只样本股（涨停股 + 蓝筹），会漏掉大量中小市值里的牛散重仓股，
结论容易失真。本版把范围换成<b>沪深北交易所全部 {DATA['universe']} 只 A 股</b>，逐只抓取中报前十大股东与前十大流通股东，
共 <b>{DATA['records']:,} 条</b>股东记录，无抽样、无行业遗漏。</div>
<div class='chiprow'>
<div class='chip n'><div class='k'>全市场股票</div><div class='v'>{DATA['universe']}</div><div class='hl'>沪 + 深 + 北</div></div>
<div class='chip n'><div class='k'>股东记录</div><div class='v'>{DATA['records']:,}</div><div class='hl'>十大 + 十大流通去重</div></div>
<div class='chip'><div class='k'>自然人（牛散）</div><div class='v'>{TC.get('个人',0):,}</div><div class='hl'>{S['个人']['holders']:,} 位</div></div>
<div class='chip'><div class='k'>私募证券基金</div><div class='v'>{TC.get('私募',0):,}</div><div class='hl'>{S['私募']['holders']:,} 只产品</div></div>
<div class='chip'><div class='k'>公募主动基金</div><div class='v'>{TC.get('公募',0):,}</div><div class='hl'>{S['公募']['holders']:,} 只产品</div></div>
</div>
<div class='note'>被剔除的记录：产业资本／一级市场 {TC.get('产业资本',0):,} 条、被动指数与 ETF {TC.get('被动',0):,} 条、
外资通道 {TC.get('外资',0):,} 条、国家队 {TC.get('国家队',0):,} 条、持股≥10% 的实控人 {TC.get('大股东',0):,} 条、
一般法人 {TC.get('机构',0):,} 条、信托 {TC.get('信托',0):,} 条。
剔除逻辑：这些主体的持股变动来自申赎、Pre-IPO 锁定、通道过户或控制权安排，不代表二级市场的主动选股判断。</div>
</div>

<div class='section'>
<h2>评分口径：怎么定义「最强」</h2>
<div class='sub2'>沿用三条判据 —— <b>① 增比减好　② 低比高好　③ 牛比不牛好</b>。
落到股东个体上，强度 = 参与广度 + 加仓力度 + 介入深度，满分 10 分。</div>
<table>
<tr><th style='width:120px'>维度</th><th class='num' style='width:70px'>满分</th><th>算法</th></tr>
<tr><td><b>参与广度</b></td><td class='num'>4.0</td><td>进入几家公司的前十大股东，6 家封顶。只押 1 只股不算「行业最强」，避免单票赌徒冲榜。</td></tr>
<tr><td><b>加仓力度</b></td><td class='num'>4.0</td><td>（增持家数 − 减持家数）÷ 持股家数，对应判据①；持平会稀释得分，只有真金白银加仓才拿满分。</td></tr>
<tr><td><b>介入深度</b></td><td class='num'>2.0</td><td>在这些公司的合计持股比例，15% 封顶，防止单一重仓股垒高分。</td></tr>
</table>
<div class='note'>判据②「低比高好」在股东榜里无法落到个人，因此提升到<b>行业估值分位</b>层面处理（见下一节的四象限）；
判据③「牛比不牛好」体现为只保留自然人／私募／公募三类主动资金，剔除被动与产业资本。<br>
局限：数据源不提供「新进」标记 —— 上期不在前十大、本期新进的股东，其变动量被记为 0，会落入「持平」。
因此本页的增持家数是<b>偏保守</b>的下限值。</div>
</div>

<div class='section'>
<h2>行业四象限：聪明钱流向 × 估值高低</h2>
<div class='sub2'>净增持 = 三类主动资金的增持家次 − 减持家次（正数代表加仓面更广）。
估值分位 = 该行业 PE / PB 中位数在 31 个行业中的排位，<b>数字越小越便宜</b>。
分界线取全行业净增持中位数 <b>{NET_MID:.0f}</b> 与估值分位 <b>50</b>。</div>
<table>
<tr><th>行业</th><th class='num'>净增持</th><th class='num'>个人</th><th class='num'>私募</th><th class='num'>公募</th>
<th class='num'>PE中位</th><th class='num'>PB中位</th><th class='num'>亏损占比</th><th class='num'>估值分位</th><th>象限</th></tr>
{IND_TABLE}
</table>
<div class='legend'>
<span><span class='qtag qa'>资金进·估值低</span> 最优</span>
<span><span class='qtag qb'>资金进·估值高</span> 追高</span>
<span><span class='qtag qc'>资金退·估值低</span> 待催化</span>
<span><span class='qtag qd'>资金退·估值高</span> 回避</span>
</div>
<div class='note'>注意「亏损占比」一列：钢铁 37%、煤炭 42%、房地产 63% 的公司 PE 为负，
这类行业的 PE 中位数只由盈利公司算出，会系统性低估真实估值水平，须配合 PB 一起看。</div>
</div>

<div class='section'>
<h2>行业最强榜 · 各行业个人 / 私募 / 公募 Top20</h2>
<div class='sub2'>点击行业标签切换。标签后的数字是该行业聪明钱净增持家次。
表格里点任意一行可展开该股东的具体持仓与强度拆解。每卡可<b>按强度 / 按胜率*</b>切换排序，胜率* 为该股东中报全部持股在 2026-06-30 → 2026-09-01 窗口的上涨比例与平均涨幅（仅作历史参考）。</div>
<div class='pills'>{PILLS}</div>
<div class='amberbox' id='indTitle'></div>
<div class='grid3' id='indBody'></div>
</div>

<div class='section'>
<h2>全市场强度榜 Top20</h2>
<div class='sub2'>不分行业的横向对比。个人榜按行业分别统计
（同名自然人无法区分，跨行业合并会把不同的人叠成一个）；私募与公募名称唯一，做跨行业合并。</div>
<div class='tabs'>
<button class='tab on' data-scope='top' data-g='个人'>自然人</button>
<button class='tab' data-scope='top' data-g='私募'>私募</button>
<button class='tab' data-scope='top' data-g='公募'>公募</button>
</div>
{TOP_BLOCKS.replace("class='tabpane' data-g='个人'", "class='tabpane on' data-g='个人'")}
</div>

<div class='section'>
<h2>减持警示榜</h2>
<div class='sub2'>净减持家数最多的股东。判据①反向使用：连续减持的主体，其重仓方向要降级看待。</div>
<div class='tabs'>
<button class='tab on' data-scope='dec' data-g='个人'>自然人</button>
<button class='tab' data-scope='dec' data-g='私募'>私募</button>
<button class='tab' data-scope='dec' data-g='公募'>公募</button>
</div>
{DEC_BLOCKS.replace("class='tabpane2' data-g='个人'", "class='tabpane2 on' data-g='个人'")}
</div>

<div class='section'>
<h2>结论与操作建议</h2>
<div class='amberbox upbox'>
<b>① 三类资金共振的行业（最强信号）</b><br>
{RESO_LIST}<br>
<span class='tiny'>自然人、私募、公募三类主体同时净增持。私募与公募的权重更高——它们有投研团队和风控约束，
判断错误的成本远高于个人，因此机构侧的净增持比个人侧更有指示意义。</span>
</div>
<div class='amberbox'>
<b>② 资金进 + 估值低（A 象限，优先配置）</b><br>
{A_LIST}<br>
<span class='tiny'>加仓面广且行业估值仍在全市场偏低区间，同时满足判据①和②，是风险收益比最好的一档。</span>
</div>
<div class='amberbox'>
<b>③ 资金进 + 估值高（B 象限，需要业绩兑现）</b><br>
{B_LIST}<br>
<span class='tiny'>聪明钱在买，但估值已到全市场偏贵区间，只能靠盈利增长消化。适合波段而非底仓，
必须设止损；一旦季报增速不达预期，估值和资金会同时反向。</span>
</div>
<div class='amberbox downbox'>
<b>④ 资金退 + 估值高（D 象限，优先回避）</b><br>
{D_LIST}<br>
<span class='tiny'>估值贵、聪明钱在撤，判据①②同时不利。</span>
</div>
<div class='amberbox'>
<b>⑤ 怎么用这三张榜</b><br>
· <b>行业层面先做取舍</b>：只在 A 象限和三类资金共振的行业里找标的，直接排除 D 象限，可以砍掉一大半无效工作量。<br>
· <b>用私募／公募榜找方向，用个人榜做交叉验证</b>：机构榜给出的是有研究支撑的方向；如果同一个行业里牛散也在加仓，
说明产业侧和资金侧的认知一致，信号更硬。<br>
· <b>看强度拆解而不只看总分</b>：广度高但力度低 = 分散布局、缺乏信心；力度满分但广度低 = 单票重仓、赔率高但风险集中。
点开表格行可以看到每个股东的三项拆分。<br>
· <b>把减持榜当负面清单</b>：某只股票同时出现在多个主体的减持记录里，无论技术形态多好都要降级。<br>
· <b>季度数据有天然滞后</b>：中报反映的是 6 月 30 日的持仓，公告日到现在已有时间差，
筹码可能已经变化。这套榜单适合做<b>方向筛选和交叉验证</b>，不能当买卖信号直接用。
</div>
</div>

<div class='section'>
<h2>方法论与已知局限</h2>
<table>
<tr><th style='width:150px'>环节</th><th>处理方式与局限</th></tr>
<tr><td><b>样本范围</b></td><td>沪深北全部 {DATA['universe']} 只 A 股，无抽样。行业映射成功 {R['mapped']} 只，
未映射的极少数为暂无申万分类的新股或退市整理股。</td></tr>
<tr><td><b>股东分类</b></td><td>基于名称的规则引擎。已处理的易错点：基金公司名含「银行／保险」（如某银行-兴全合润基金）
须先判基金再判银保；证金公司归国家队；「XX增强」不算被动指数。
残留风险：极少数不含任何机构关键词的合伙企业可能被误判为自然人。</td></tr>
<tr><td><b>自然人识别</b></td><td>2~4 个纯汉字且持股 &lt; 10%。持股≥10% 视为实控人／创始人（共 {TC.get('大股东',0):,} 条），
不计入牛散——否则寒武纪创始人这类持股 30%+ 的产业股东会占满榜首。</td></tr>
<tr><td><b>同名问题</b></td><td>自然人只有姓名没有身份标识，无法区分同名不同人。因此个人榜按行业分别统计，
不做跨行业合并。跨行业出现的同名股东会被视为不同人。</td></tr>
<tr><td><b>私募筛选</b></td><td>剔除私募股权／创业投资／产业投资基金／股权合伙企业（共 {TC.get('产业资本',0):,} 条）。
这类持股来自 Pre-IPO 入股或定增锁定，减持是退出安排而非看空，与二级市场判断无关。</td></tr>
<tr><td><b>公募筛选</b></td><td>剔除 ETF、指数型、联接基金（共 {TC.get('被动',0):,} 条）。
被动产品的持仓变动来自申赎和成分股调整，不含主动判断。「指数增强」保留，因其有主动敞口。</td></tr>
<tr><td><b>新进未标记</b></td><td>数据源中上期不在前十大的新进股东，变动量记为 0，落入「持平」。
经全量校验：110,781 条记录中「变动量 = 持股量」的为 0 条，确认无法识别新进。本页增持家数为保守下限。</td></tr>
<tr><td><b>估值口径</b></td><td>PE_TTM / PB_LF，基准日 {DATA['val_date']}，晚于中报基准日。
行业中位数只用盈利公司计算 PE，亏损占比高的行业须结合 PB 与亏损占比列判断。</td></tr>
<tr><td><b>胜率 / 均涨*</b></td><td>胜率 = 区间上涨家数 ÷ 该股东全部持股家数；均涨 = 全部持股区间涨跌幅的均值。
区间取 <b>2026-06-30 收盘 → 2026-09-01 收盘</b>，价格来自腾讯自选股 data_quote 历史快照（共 1813 只成分股、1041 个股东主体的全持仓，缺失价格的记为「—」）。
* 表示该指标仅反映其<b>中报时点历史持仓</b>在窗口内的表现，不等于其当前持仓，亦不构成收益承诺；用于辅助判断「这批资金过去选股准不准」，而非买卖信号。</td></tr>
</table>
<div class='note'>数据来源：腾讯自选股（股东数据 data_shareholder、行业成分 data_sector、估值 fin_valuation 排行）。
本页仅为数据整理与统计，不构成投资建议。</div>
</div>

</div>
<script>{JS.replace('__DATA__', json.dumps(DATA, ensure_ascii=False))}</script>
</body>
</html>"""

out = os.path.join(ROOT, "web", "2026-q2-industry-elite.html")
open(out, "w", encoding="utf-8").write(HTML)
print("已生成", out, f"{len(HTML)/1024:.0f} KB")
print("A象限行业:", [r["ind"] for r in A_inds])
print("三类共振:", [r["ind"] for r in reso[:6]])
print("净增持中位数:", NET_MID)
