# -*- coding: utf-8 -*-
"""N字形战法 · 首次触及法 实盘模拟器（可调参数 · 交互页）。

定位（用户 2026-10-23 建议落地）：
  把「健康回撤·完整（hb_pos = 健康回撤严格 ∩ 52周分位30~85）」的真实信号分布
  原样嵌入页面，用户拖动 目标价%/止损价%/持有天数/市场热度，即刻在浏览器端重算：
    首次触及胜率 / 平均已实现收益 / 盈亏比 / 平均触达天数 / 收益分布 / TP×SL 胜率热力图。
  「首次触及法」= 入场后先触 +目标 还是先触 −止损（真实交易判据，替代第10天终端价）。

铁律：
  · 信号口径与主池 / 回测完全一致（复用 gen_signals_asof + attach_attr + is_healthy_pullback
    + is_pos_ok），as-of 回测日集合复用 build_n_shape_backtest.pick_asof_dates → 防分叉。
  · 页面数字全部来自真实历史样本（前向价格逐 bar 嵌入），JS 端现算，**不写死、不编**。
  · 观察池·非出票；仅历史验证，不代表未来收益。
"""
from __future__ import annotations
import os, sys, json

QUANT = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(QUANT)
WEB = os.path.join(ROOT, "web")
sys.path.insert(0, QUANT)

import _txk
import build_n_shape as NS
import build_n_shape_backtest as BT

FWD_SIM = 20            # 每条信号最多嵌入的前向收盘价根数（供更长持有天数探索）
HEAT_ORDER = ["强势", "震荡", "弱势", "破位", "未知"]
OUTDIR = os.path.join(WEB, "n_shape", "sim")
os.makedirs(OUTDIR, exist_ok=True)


def _first_touch_py(fwd, entry, tp, sl, horizon):
    """与页面 JS firstTouch 完全同口径的 Python 复刻（仅用于生成『参考基准』文本）。"""
    up, dn = entry * (1 + tp), entry * (1 - sl)
    n = min(horizon, len(fwd))
    for i in range(n):
        p = fwd[i]
        if p >= up:
            return True, tp, i + 1
        if p <= dn:
            return False, -sl, i + 1
    last = fwd[n - 1]
    ret = (last / entry - 1) if entry else 0.0
    return (ret >= 0), ret, n


def collect_signals():
    latest = NS.latest_date()
    if not latest:
        raise SystemExit("无法确定数据日")
    try:
        _txk.set_asof(latest)
    except Exception:
        pass
    cache = _txk.load()
    name_map = NS.load_name_map(latest)
    name2sw2 = NS.load_name2sw2()
    ind_map, concept_leaders = NS.load_hot_maps()
    w52 = NS.load_52w_cache(cache)   # 52周区间改从K线缓存自算（快照字段已被证伪）

    asof_dates = BT.pick_asof_dates(cache, BT.N_DATES, BT.FWD)
    if not asof_dates:
        raise SystemExit("无足够后续数据的回测日")

    signals = []
    for D in asof_dates:
        sigs = NS.gen_signals_asof(cache, D, name_map)
        NS.attach_attr(sigs, name2sw2, ind_map, concept_leaders, w52)
        heat = NS.load_market_heat(D)
        hlabel = heat.get("label") or "未知"
        for s in sigs:
            # hb_pos：健康回撤·完整 = 健康回撤严格 ∩ 52周分位位置合理（与回测 is_hb_pos 同口径）
            if not (NS.is_healthy_pullback(s, True) and NS.is_pos_ok(s)):
                continue
            bars = cache.get(s["code"])
            aidx = s.get("asof_idx")
            if not bars or aidx is None:
                continue
            entry = bars[aidx].get("last")
            if not entry:
                continue
            entry = float(entry)
            fwd = []
            for b in bars[aidx + 1: aidx + 1 + FWD_SIM]:
                lv = b.get("last")
                if lv is None:
                    break
                fwd.append(float(lv))
            if len(fwd) < NS.FWD:      # 至少 10 根前向收盘价，保证与回测口径一致
                continue
            signals.append({
                "c": s["code"],
                "n": s.get("name") or "—",
                "sw": s.get("sw2") or "—",
                "h": hlabel,
                "e": round(entry, 4),
                "d": round(s.get("dist_local_peak"), 2) if s.get("dist_local_peak") is not None else None,
                "f": [round(x, 4) for x in fwd],
                "_d": D,
            })

    # 参考基准：默认参数 6%/8%/10日/全部热度 的首次触及胜率（应与回测汇总 hb_pos 一致）
    wins = 0
    sret = 0.0
    sw = 0.0
    sl = 0.0
    nw = nl = 0
    for s in signals:
        win, ret, _day = _first_touch_py(s["f"], s["e"], 0.06, 0.08, NS.FWD)
        sret += ret
        if win:
            wins += 1; sw += ret; nw += 1
        else:
            sl += ret; nl += 1
    n = len(signals)
    ref = {
        "tp": 6, "sl": 8, "horizon": NS.FWD, "heat": "全部", "n": n,
        "wr": (wins / n) if n else None,
        "avg": (sret / n) if n else None,
        "pr": ((sw / nw) / abs(sl / nl)) if (nw and nl) else None,
    }
    return latest, asof_dates, signals, ref


# ---------------------------------------------------------------- 页面（HTML/JS/CSS 原文，勿用 % 格式化）
_HEAD = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>N字形 · 首次触及法 实盘模拟器</title>
<style>
.sim-head{margin:2px 0 4px;}
.sim-sub{color:var(--muted);font-size:13px;margin:0 0 14px;}
.sim-note{background:var(--accent-soft);border:1px solid #cfe0fb;border-left:4px solid var(--accent);
  border-radius:8px;padding:12px 14px;font-size:13px;color:var(--ink);margin:0 0 16px;line-height:1.7;}
.sim-note b{color:var(--accent-ink);}
.sim-ctrl{display:flex;flex-wrap:wrap;gap:18px 26px;align-items:flex-end;
  background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:16px 18px;margin:0 0 16px;}
.sim-field{display:flex;flex-direction:column;gap:6px;min-width:150px;}
.sim-field label{font-size:12px;color:var(--muted);font-weight:600;}
.sim-field .val{font-size:20px;font-weight:700;color:var(--ink);}
.sim-field input[type=range]{width:170px;accent-color:var(--accent);}
.sim-field select{font-size:14px;padding:6px 8px;border:1px solid var(--line);border-radius:6px;background:var(--surface);color:var(--ink);}
.sim-presets{display:flex;gap:8px;flex-wrap:wrap;}
.sim-presets button{font-size:12px;padding:7px 11px;border:1px solid var(--line-2);border-radius:999px;
  background:var(--bg);color:var(--ink);cursor:pointer;}
.sim-presets button:hover{border-color:var(--accent);color:var(--accent);}
.sim-summary{display:flex;flex-wrap:wrap;gap:14px;margin:0 0 18px;}
.sim-kpi{flex:1;min-width:132px;background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:14px 16px;}
.sim-kpi .k{font-size:12px;color:var(--muted);font-weight:600;margin-bottom:4px;}
.sim-kpi .v{font-size:24px;font-weight:800;color:var(--ink);}
.sim-kpi .v small{font-size:13px;font-weight:600;color:var(--muted);}
.sim-h2{font-size:16px;font-weight:700;color:var(--ink);margin:22px 0 10px;padding-left:10px;border-left:4px solid var(--accent);}
.sim-heatwrap{overflow-x:auto;}
table.sim-heat{border-collapse:collapse;font-size:13px;}
table.sim-heat th,table.sim-heat td{border:1px solid var(--line-2);padding:7px 9px;text-align:center;min-width:42px;}
table.sim-heat th{background:var(--bg);color:var(--muted);font-weight:600;}
table.sim-heat td{cursor:pointer;font-weight:700;}
table.sim-heat td.cur{outline:2px solid var(--accent);outline-offset:-2px;}
table.sim-heat td.slcol{background:var(--bg);color:var(--muted);font-weight:700;cursor:default;}
.sim-legend{font-size:12px;color:var(--muted);margin:8px 0 0;}
.sim-hist{display:flex;align-items:flex-end;gap:3px;height:150px;padding:6px 2px 0;border-bottom:1px solid var(--line);}
.sim-bar{flex:1;position:relative;min-width:8px;}
.sim-bar .b{width:100%;border-radius:3px 3px 0 0;}
.sim-histaxis{display:flex;justify-content:space-between;font-size:11px;color:var(--muted);margin-top:4px;}
.sim-tablewrap{overflow-x:auto;}
table.sim-tbl{border-collapse:collapse;width:100%;font-size:13px;}
table.sim-tbl th,table.sim-tbl td{border-bottom:1px solid var(--line-2);padding:7px 9px;text-align:right;white-space:nowrap;}
table.sim-tbl th{background:var(--bg);color:var(--muted);font-weight:600;position:sticky;top:0;}
table.sim-tbl td.l,table.sim-tbl th.l{text-align:left;}
.sim-pill{display:inline-block;font-size:11px;padding:1px 7px;border-radius:999px;font-weight:600;}
.sim-pill.win{background:#fdecea;color:#c5221f;}
.sim-pill.lose{background:#e6f4ea;color:#137333;}
.sim-pill.to{background:#f1f3f4;color:#5f6368;}
.sim-foot{color:var(--muted);font-size:12px;margin:22px 0 0;line-height:1.7;}
</style></head>
<body>
<div class="wrap">
"""


def render(signals, ref, latest, asof_dates):
    meta = {
        "gen": latest, "n_dates": len(asof_dates), "asof": asof_dates,
        "heats": HEAT_ORDER, "ref": ref,
    }
    # 数据日与回测口径提示（现算，不写死）
    n = len(signals)
    ref_txt = "—"
    if ref["wr"] is not None:
        pr = "—" if ref["pr"] is None else ("%.2f" % ref["pr"])
        ref_txt = "胜率 <b>%.1f%%</b> ｜ 平均已实现收益 <b>%+.2f%%</b> ｜ 盈亏比 <b>%s</b>" % (
            ref["wr"] * 100, ref["avg"] * 100, pr)
    body = []
    body.append("<h1 class='sim-head'>N字形战法 · 首次触及法 实盘模拟器</h1>")
    body.append("<p class='sim-sub'>样本 = 健康回撤·完整（健康回撤严格 ∩ 52周分位30~85）真实信号，"
                "跨 <b>%d</b> 个可回测日共 <b>%d</b> 条 · 数据基准 <b>%s</b> · 观察池·非出票</p>" % (
                    len(asof_dates), n, latest))
    body.append("<div class='sim-note'>"
                "拖动下方 <b>目标价 / 止损价 / 持有天数</b>、切换<b>市场热度</b>，本页即刻用真实前向价格重算「首次触及」结果。"
                "<br>· <b>首次触及法</b>：入场后先触 +目标 记赢（实现 +目标）、先触 −止损 记亏（实现 −止损）；持有期内均未触按末日收盘判定。"
                "<br>· 默认参数（目标 <b>6%</b> / 止损 <b>8%</b> / 持有 <b>10</b> 日 / 全部热度）：" + ref_txt +
                " —— 与「<a href='../backtest/index.html'>N字形回测汇总</a>」首次触及胜率同源同口径，可交叉验证。"
                "<br>· 该形态仅在市场偏暖（强势/震荡）时有效，破位环境由主池页顶部「大盘热度」横幅门控暂停开仓。"
                "</div>")

    # 控件
    body.append("<div class='sim-ctrl'>")
    body.append("<div class='sim-field'><label>目标价 +TP</label>"
                "<input type='range' id='cTp' min='2' max='14' step='0.5' value='6'>"
                "<span class='val' id='vTp'>+6.0%</span></div>")
    body.append("<div class='sim-field'><label>止损价 −SL</label>"
                "<input type='range' id='cSl' min='2' max='14' step='0.5' value='8'>"
                "<span class='val' id='vSl'>−8.0%</span></div>")
    body.append("<div class='sim-field'><label>持有天数（首次触及窗口）</label>"
                "<select id='cH'><option>5</option><option selected>10</option><option>15</option></select></div>")
    heat_opts = "".join("<option%s>%s</option>" % (" selected" if h == "全部" else "", h)
                        for h in (["全部"] + HEAT_ORDER))
    body.append("<div class='sim-field'><label>市场热度（信号日环境）</label>"
                "<select id='cHeat'>%s</select></div>" % heat_opts)
    body.append("<div class='sim-field'><label>快捷档位</label><div class='sim-presets'>"
                "<button data-tp='6' data-sl='8' data-h='10'>平衡 6/8/10</button>"
                "<button data-tp='4' data-sl='8' data-h='10'>高胜率 4/8/10</button>"
                "<button data-tp='8' data-sl='6' data-h='10'>宽目标紧止损 8/6/10</button>"
                "</div></div>")
    body.append("</div>")

    # KPI 汇总
    body.append("<div class='sim-summary' id='sum'></div>")

    # 热力图
    body.append("<div class='sim-h2'>目标 × 止损 胜率热力图（按当前持有天数/热度）</div>")
    body.append("<div class='sim-heatwrap' id='heat'></div>")
    body.append("<p class='sim-legend'>单元格 = 该 (目标, 止损) 组合的首次触及胜率（%），颜色越深越有利；"
                "点击单元格即可套用该组合。· = 该组合样本不足。</p>")

    # 直方图
    body.append("<div class='sim-h2'>已实现收益分布（当前参数）</div>")
    body.append("<div class='sim-hist' id='hist'></div>")
    body.append("<div class='sim-histaxis'><span>−14%</span><span>−7%</span><span>0</span><span>+7%</span><span>+14%</span></div>")

    # 逐票明细
    body.append("<div class='sim-h2'>逐票首次触及结果（当前参数）</div>")
    body.append("<div class='sim-tablewrap'><table class='sim-tbl'>"
                "<thead><tr><th class='l'>代码</th><th class='l'>名称</th><th class='l'>板块</th><th class='l'>热度</th>"
                "<th>入场价</th><th>距局部高</th><th>结果</th><th>第几日</th><th>已实现收益</th></tr></thead>"
                "<tbody id='tbody'></tbody></table></div>")

    body.append("<p class='sim-foot'>"
                "口径说明：以信号日收盘价买入（未计滑点/次日跳空），前向最多 %d 个交易日逐 bar 判定先触目标还是先触止损；"
                "持有天数超过某信号可用前向根数时，该信号在该档位被剔除（样本数会随之变化）。"
                "<br>本页为历史回测·观察池，<b>非出票、不构成买卖建议、不代表未来收益</b>。信号与「健康回撤·完整」同口径，"
                "由 <b>build_n_shape_sim.py</b> 每日重算，数字全部来自真实历史样本、不写死。</p>" % FWD_SIM)
    body.append("</div>")  # /wrap

    data_script = "<script>var DATA=" + json.dumps(meta, ensure_ascii=False) + \
                  ";var SIG=" + json.dumps(signals, ensure_ascii=False) + ";</script>"
    html = _HEAD + "".join(body) + data_script + _LOGIC + "</body></html>"
    return html


# 交互逻辑（浏览器端现算；原文，勿用 % 格式化）
_LOGIC = """
<script>
(function(){
  var TP_LIST=[3,4,5,6,7,8,9,10,11,12];
  var SL_LIST=[3,4,5,6,7,8,9,10,11,12];
  function firstTouch(sig,tp,sl,H){
    var e=sig.e, up=e*(1+tp/100), dn=e*(1-sl/100), f=sig.f, n=Math.min(H,f.length);
    for(var i=0;i<n;i++){var p=f[i];
      if(p>=up) return {win:true,ret:tp/100,day:i+1};
      if(p<=dn) return {win:false,ret:-sl/100,day:i+1};}
    var last=f[n-1], ret=e>0?(last/e-1):0;
    return {win:ret>=0,ret:ret,day:n};
  }
  function runAll(tp,sl,H,heat){
    var rows=[];
    for(var k=0;k<SIG.length;k++){var s=SIG[k];
      if(heat!=='\\u5168\\u90e8' && s.h!==heat) continue;
      if(s.f.length<H) continue;
      var r=firstTouch(s,tp,sl,H); r.sig=s; rows.push(r);}
    return rows;
  }
  function agg(rows){
    var n=rows.length; if(!n) return {n:0};
    var w=0,sr=0,sw=0,sl=0,days=[];
    for(var i=0;i<n;i++){var r=rows[i]; sr+=r.ret;
      if(r.win){w++;sw+=r.ret;days.push(r.day);} else {sl+=r.ret;}}
    return {n:n,win:w,wr:w/n,avg:sr/n,
      pr:(w>0&&(n-w)>0)?(sw/w)/Math.abs(sl/(n-w)):null,
      ad:days.length?days.reduce(function(a,b){return a+b;},0)/days.length:null};
  }
  function pct(x,d){ if(x==null) return '\\u2014'; var v=(x*100); return (v>=0?'+':'')+v.toFixed(d==null?2:d)+'%'; }
  function col(x){ return x==null?'var(--muted)':(x>=0?'var(--red)':'var(--green)'); }
  function heatColor(wr){
    if(wr==null) return 'background:#f1f3f4;color:#9aa0a6;';
    var t=Math.max(0,Math.min(1,(wr-0.34)/0.28));
    var a=0.06+0.74*t, txt=t>0.5?'#fff':'#202124';
    return 'background:rgba(234,67,53,'+a.toFixed(3)+');color:'+txt+';';
  }
  function $ (id){return document.getElementById(id);}
  function cur(){ return {tp:parseFloat($('cTp').value), sl:parseFloat($('cSl').value),
    H:parseInt($('cH').value,10), heat:$('cHeat').value}; }

  function renderSum(){
    var c=cur(), rows=runAll(c.tp,c.sl,c.H,c.heat), a=agg(rows);
    $('vTp').textContent='+'+c.tp.toFixed(1)+'%';
    $('vSl').textContent='\\u2212'+c.sl.toFixed(1)+'%';
    var verdict = a.n===0?'样本不足':(a.avg>0?'正期望':'负期望');
    var vcol = a.n===0?'var(--muted)':(a.avg>0?'var(--red)':'var(--green)');
    var html=''
      +kpi('首次触及胜率', a.n?(a.wr*100).toFixed(1)+'<small>%</small>':'\\u2014', a.n?(a.wr>=0.5?'var(--red)':'var(--green)'):'var(--muted)')
      +kpi('平均已实现收益', pct(a.avg), col(a.avg))
      +kpi('盈亏比', a.pr==null?'\\u2014':a.pr.toFixed(2), a.n&&a.pr!=null?(a.pr>=1?'var(--red)':'var(--green)'):'var(--muted)')
      +kpi('样本数', a.n, 'var(--ink)')
      +kpi('平均触达天数', a.ad==null?'\\u2014':a.ad.toFixed(1), 'var(--ink)')
      +kpi('期望判定', verdict, vcol);
    $('sum').innerHTML=html;
    renderHist(rows);
    renderTable(rows);
    highlight();
  }
  function kpi(k,v,c){ return "<div class='sim-kpi'><div class='k'>"+k+"</div><div class='v' style='color:"+c+"'>"+v+"</div></div>"; }

  function renderHist(rows){
    var bins=new Array(29).fill(0); // -14..+14 step 1
    for(var i=0;i<rows.length;i++){var r=rows[i].ret*100; var b=Math.floor(r)+14; if(b<0)b=0; if(b>28)b=28; bins[b]++;}
    var mx=Math.max.apply(null,bins); if(mx<1)mx=1;
    var h='';
    for(var j=0;j<29;j++){var cnt=bins[j]; var hp=cnt/mx*100; var cc=(j-14)>=0?'var(--red)':'var(--green)';
      h+="<div class='sim-bar' title='"+(j-14)+"% ~ "+(j-13)+"% : "+cnt+" 笔'><div class='b' style='height:"+hp.toFixed(1)+"%;background:"+cc+";opacity:"+(cnt?0.85:0)+"'></div></div>";}
    $('hist').innerHTML=h;
  }
  function renderTable(rows){
    rows=rows.slice().sort(function(a,b){return b.ret-a.ret;});
    var h='';
    for(var i=0;i<rows.length;i++){var r=rows[i], s=r.sig;
      var pill = r.ret=== (cur().tp/100) ? "<span class='sim-pill win'>触利 ↗</span>"
              : (r.ret=== -(cur().sl/100) ? "<span class='sim-pill lose'>触损 ↘</span>" : "<span class='sim-pill to'>超时</span>");
      h+="<tr><td class='l'>"+s.c+"</td><td class='l'>"+esc(s.n)+"</td><td class='l'>"+esc(s.sw)+"</td>"
        +"<td class='l'>"+esc(s.h)+"</td><td>"+s.e.toFixed(2)+"</td>"
        +"<td style='color:"+(s.d==null?'var(--muted)':(s.d>=0?'var(--red)':'var(--green)'))+"'>"+(s.d==null?'\\u2014':s.d.toFixed(1)+'%')+"</td>"
        +"<td class='l'>"+pill+"</td><td>第"+r.day+"日</td>"
        +"<td style='color:"+col(r.ret)+";font-weight:700'>"+pct(r.ret)+"</td></tr>";}
    $('tbody').innerHTML=h||"<tr><td colspan='9' class='l' style='color:var(--muted)'>当前参数无足够样本。</td></tr>";
  }
  function esc(x){ return String(x).replace(/[&<>]/g,function(m){return {'&':'&amp;','<':'&lt;','>':'&gt;'}[m];}); }

  var heatBuilt=false;
  function buildHeat(){
    var c=cur(), h='<table class=\\'sim-heat\\'><thead><tr><th>SL\\\\TP</th>';
    for(var t=0;t<TP_LIST.length;t++) h+='<th>+'+TP_LIST[t]+'%</th>';
    h+='</tr></thead><tbody>';
    for(var si=0;si<SL_LIST.length;si++){
      h+='<tr><td class=\\'slcol\\'>\\u2212'+SL_LIST[si]+'%</td>';
      for(var ti=0;ti<TP_LIST.length;ti++){
        var rows=runAll(TP_LIST[ti],SL_LIST[si],c.H,c.heat), a=agg(rows);
        var wr=a.n?a.wr:null;
        h+="<td style='"+heatColor(wr)+"' data-tp='"+TP_LIST[ti]+"' data-sl='"+SL_LIST[si]+"' "
          +"title='目标+"+TP_LIST[ti]+"% / 止损"+SL_LIST[si]+"% : 胜率 "+(wr==null?'样本不足':(wr*100).toFixed(1)+'%')+" (n="+a.n+")'>"
          +(wr==null?'\\u00b7':Math.round(wr*100))+"</td>";
      }
      h+='</tr>';
    }
    h+='</tbody></table>';
    $('heat').innerHTML=h;
    var cells=$('heat').querySelectorAll('td[data-tp]');
    for(var k=0;k<cells.length;k++){
      cells[k].onclick=function(){ $('cTp').value=this.getAttribute('data-tp'); $('cSl').value=this.getAttribute('data-sl'); renderSum(); };
    }
    heatBuilt=true; highlight();
  }
  function highlight(){
    if(!heatBuilt) return;
    var c=cur(), cells=$('heat').querySelectorAll('td[data-tp]');
    for(var k=0;k<cells.length;k++){
      var on = parseFloat(cells[k].getAttribute('data-tp'))===c.tp && parseFloat(cells[k].getAttribute('data-sl'))===c.sl;
      cells[k].classList.toggle('cur',on);
    }
  }

  ['cTp','cSl'].forEach(function(id){ $(id).addEventListener('input', renderSum); });
  ['cH','cHeat'].forEach(function(id){ $(id).addEventListener('change', function(){ buildHeat(); renderSum(); }); });
  var btns=document.querySelectorAll('.sim-presets button');
  for(var i=0;i<btns.length;i++){ btns[i].onclick=function(){
    $('cTp').value=this.getAttribute('data-tp'); $('cSl').value=this.getAttribute('data-sl');
    $('cH').value=this.getAttribute('data-h'); buildHeat(); renderSum(); }; }

  buildHeat(); renderSum();
})();
</script>
"""


def main():
    latest, asof_dates, signals, ref = collect_signals()
    html = render(signals, ref, latest, asof_dates)
    out = os.path.join(OUTDIR, "index.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    rt = "—"
    if ref["wr"] is not None:
        pr = "—" if ref["pr"] is None else ("%.2f" % ref["pr"])
        rt = "胜率 %.1f%% / 均 %+.2f%% / 比 %s" % (ref["wr"] * 100, ref["avg"] * 100, pr)
    print("=== N字形 实盘模拟器 · 数据日 %s · 回测日 %d · hb_pos 样本 %d ===" % (
        latest, len(asof_dates), len(signals)))
    print("  参考基准 6/8/10/全部：%s" % rt)
    print("  写出 %s" % out)


if __name__ == "__main__":
    main()
