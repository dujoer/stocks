#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
生成「板块强度热力图」(web/sector/heatmap.html):

  - 读 quant/sector_daily/*.json（最近 N 个交易日，默认 25）
  - 行 = 板块（最新一日全量 928，按最新强度排序 / 可筛选 行业·概念·全部）
  - 列 = 交易日（左旧右新）
  - 单元格底色 = 板块强度（红=强 / 绿=弱，按 |强度| 分级；缺失=灰）
  - 悬停浮窗：强度 / 主力净流入 / 散户净流入 / 暗盘净额 / 主力行为 / 领涨
  - 顶部控制：时间范围 · 类型 · 排序 · 数量(TOP60/全部)；色阶图例
  - 顶部概览：最新交易日 / 均强 / 上涨占比 / 四档行为计数 / 全市场暗盘净额

数据全部来自 sector_daily（westock 盘后真实快照，前瞻累积、不回溯不编造），
本脚本不生成任何统计数字，只做「可视化编排」。

用法:
  python build_sector_heatmap.py [--days 25] [--output web/sector/heatmap.html]
"""
import argparse, json, os, glob
from _nav import topnav

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
Q = os.path.join(ROOT, "quant")
WEB = os.path.join(ROOT, "web")
WEB_SECTOR = os.path.join(WEB, "sector")

BEH_RANK2TXT = {4: "抢筹", 3: "建仓", 2: "洗盘", 1: "出货"}
BEH_RANK2CLS = {4: "beh-qiang", 3: "beh-jian", 2: "beh-xi", 1: "beh-chu"}

CSS = """* { box-sizing: border-box; }
body { margin:0; font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;
  background:var(--bg,#f8f9fa); color:var(--ink,#202124); min-height:100vh; }
.wrap { max-width:1440px; margin:0 auto; padding:24px 22px 56px; }
header { display:flex; align-items:flex-end; justify-content:space-between; flex-wrap:wrap; gap:12px; }
header h1 { font-size:28px; margin:0 0 6px; background:linear-gradient(90deg,#b8893b,#b8332a,#6b5b95);
  -webkit-background-clip:text; background-clip:text; color:transparent; font-weight:800; }
header p { margin:4px 0; color:#8a929c; font-size:13px; line-height:1.6; }
.datebadge { display:inline-block; font-size:20px; font-weight:800; color:#fff;
  background:linear-gradient(135deg,#b8893b,#b8332a); padding:9px 18px; border-radius:14px;
  letter-spacing:.5px; box-shadow:0 6px 18px rgba(184,137,59,.25); white-space:nowrap; }
.datebadge small { display:block; font-size:11px; font-weight:600; opacity:.85; letter-spacing:1px; }
.meta { margin:14px 0 18px; font-size:12px; color:#6b7280; line-height:1.7; }
.meta b { color:#b8893b; }
.section { background:var(--surface,#fff); border:1px solid var(--line,#dadce0); border-radius:20px;
  padding:18px 20px; margin:0 0 22px; }
.section h2 { font-size:18px; margin:0 0 14px; padding-left:12px; border-left:5px solid #b8893b; }
/* 概览卡片 */
.idxrow { display:grid; grid-template-columns:repeat(auto-fit,minmax(140px,1fr)); gap:14px; }
.idx { background:#fafbfc; border:1px solid #eef1f4; border-radius:14px; padding:13px 15px; }
.idx .k { font-size:12px; color:#7b8794; }
.idx .v { font-size:22px; font-weight:800; margin-top:4px; color:#23262b; }
.idx .v.up { color:#b8332a; } .idx .v.down { color:#1a9e5a; } .idx .v.gold { color:#b8893b; }
/* 控制条 */
.controls { display:flex; flex-wrap:wrap; gap:14px 22px; align-items:center; margin:2px 0 14px; }
.ctl { display:flex; align-items:center; gap:8px; font-size:13px; color:#41474f; }
.ctl label { font-weight:700; color:#5a6573; }
.ctl select { font-size:13px; padding:5px 10px; border-radius:10px; border:1px solid #d7dce2;
  background:#fff; color:#23262b; }
.legend { display:flex; align-items:center; gap:8px; font-size:12px; color:#7b8794; }
.legend .bar { width:160px; height:12px; border-radius:6px;
  background:linear-gradient(90deg, rgba(52,168,83,.85), rgba(52,168,83,.18) 38%, #eceff1 50%,
    rgba(234,67,53,.18) 62%, rgba(234,67,53,.85)); }
/* 热力图 */
.hm-scroll { overflow-x:auto; -webkit-overflow-scrolling:touch; padding-bottom:6px; }
table.hm { border-collapse:separate; border-spacing:2px; font-size:11px; }
table.hm th { text-align:center; padding:5px 4px; color:#5a6573; font-weight:700;
  background:#f7f8fa; border-bottom:2px solid #e3e7ec; white-space:nowrap; position:sticky; top:0; }
table.hm th.hdate { min-width:38px; }
table.hm td.name { text-align:left; white-space:nowrap; padding:4px 8px 4px 4px;
  background:#fafbfc; position:sticky; left:0; z-index:2; min-width:150px;
  border-right:1px solid #eceff1; }
table.hm td.name .nm { font-weight:700; color:#23262b; }
table.hm td.name .bd { font-size:9.5px; padding:0 5px; border-radius:8px; margin-left:5px; }
.bd.beh-qiang { color:#b8332a; background:rgba(184,51,42,.10); }
.bd.beh-jian  { color:#b8893b; background:rgba(184,137,59,.12); }
.bd.beh-xi    { color:#3b6fd1; background:rgba(59,111,209,.10); }
.bd.beh-chu   { color:#1a9e5a; background:rgba(26,158,90,.10); }
table.hm td.cell { text-align:center; padding:0; min-width:38px; height:26px; border-radius:5px;
  cursor:default; }
table.hm td.cell span { display:block; padding:5px 2px; border-radius:5px; font-variant-numeric:tabular-nums;
  font-size:10px; line-height:1; }
table.hm tr:hover td.name { background:#f1f3f4; }
.empty { padding:8px; color:#9aa2ad; font-size:12px; }
footer { margin-top:40px; padding-top:18px; border-top:1px solid #e3e7ec;
  font-size:12px; color:#7b8794; line-height:1.8; }
/* 悬停浮窗 */
#tip { position:fixed; pointer-events:none; z-index:50; display:none; max-width:280px;
  background:#202124; color:#fff; border-radius:12px; padding:11px 13px; font-size:12px;
  line-height:1.7; box-shadow:0 10px 30px rgba(0,0,0,.28); }
#tip b { color:#ffd479; } #tip .t-up { color:#ff8a7a; } #tip .t-down { color:#7ee0a3; }
#tip .hd { font-weight:800; font-size:13px; margin-bottom:5px; color:#fff; }
"""

JS = """var DATA = __DATA__;
var CAP = 6; // 色阶饱和阈值（|强度|）
function colorOf(v){
  if(v===null||v===undefined) return '#eceff1';
  var t = Math.min(Math.abs(v)/CAP, 1); t = 0.12 + t*0.80;
  return v>0 ? 'rgba(234,67,53,'+t.toFixed(3)+')' : 'rgba(52,168,83,'+t.toFixed(3)+')';
}
function txtCls(v){ if(v===null) return ''; var t=Math.min(Math.abs(v)/CAP,1); return t>0.55?'w':''; }
var BEH = {4:'抢筹',3:'建仓',2:'洗盘',1:'出货'};
var tip = document.getElementById('tip');

function render(){
  var days = DATA.dates;
  var range = parseInt(document.getElementById('c-range').value,10);
  var kind = document.getElementById('c-kind').value;
  var sort = document.getElementById('c-sort').value;
  var topn = document.getElementById('c-top').value;
  var dslice = days.slice(-range);
  var rows = DATA.rows.filter(function(r){ return kind==='all' ? true : r.k===kind; });
  rows.forEach(function(r){
    r._last = (function(){ for(var i=dslice.length-1;i>=0;i--){ var s=r.ser[DATA.dates.indexOf(dslice[i])]; if(s&&s[0]!==null) return s[0]; } return null; })();
  });
  if(sort==='strength') rows.sort(function(a,b){ return (b._last==null?-1e9:b._last)-(a._last==null?-1e9:a._last); });
  else rows.sort(function(a,b){ return a.n<b.n?-1:(a.n>b.n?1:0); });
  if(topn!=='all') rows = rows.slice(0, parseInt(topn,10));

  var h = "<thead><tr><th class='name'>板块</th>";
  dslice.forEach(function(d){ h += "<th class='hdate'>"+d.slice(5)+"</th>"; });
  h += "</tr></thead><tbody>";
  if(!rows.length){ h += "<tr><td class='empty' colspan='"+(dslice.length+1)+"'>无符合条件板块</td></tr>"; }
  rows.forEach(function(r){
    h += "<tr><td class='name'><span class='nm'>"+r.n+"</span>";
    if(r.b){ h += "<span class='bd "+DATA.behcls[r.b]+"'>"+BEH[r.b]+"</span>"; }
    h += "</td>";
    dslice.forEach(function(d){
      var idx = DATA.dates.indexOf(d); var s = r.ser[idx];
      if(!s || s[0]===null){ h += "<td class='cell'><span style='background:#eceff1;color:#b8c0c8'>&middot;</span></td>"; }
      else {
        var bg = colorOf(s[0]); var w = txtCls(s[0])==='w' ? "color:#fff" : "";
        h += "<td class='cell' data-n='"+r.n+"' data-d='"+d+"' data-s='"+s[0].toFixed(2)+"'"
           + " data-m='"+s[1].toFixed(1)+"' data-r='"+s[2].toFixed(1)+"' data-dk='"+s[3].toFixed(1)+"'"
           + " data-b='"+BEH[s[4]]+"' data-l='"+r.l+"'>"
           + "<span style='background:"+bg+";"+w+"'>"+s[0].toFixed(1)+"</span></td>";
      }
    });
    h += "</tr>";
  });
  h += "</tbody>";
  document.getElementById('hmtab').innerHTML = h;
}
function showTip(e){
  var t = e.target.closest('td.cell'); if(!t) return;
  var m = parseFloat(t.getAttribute('data-m')), r = parseFloat(t.getAttribute('data-r')),
      dk = parseFloat(t.getAttribute('data-dk'));
  var mc = m>=0?'t-up':'t-down', rc = r>=0?'t-up':'t-down', dc = dk>=0?'t-up':'t-down';
  tip.innerHTML = "<div class='hd'>"+t.getAttribute('data-n')+"</div>"
    + "交易日 <b>"+t.getAttribute('data-d')+"</b><br>"
    + "板块强度 <b>"+t.getAttribute('data-s')+"</b><br>"
    + "主力净流入 <span class='"+mc+"'>"+(m>=0?'+':'')+m+"亿</span><br>"
    + "散户净流入 <span class='"+rc+"'>"+(r>=0?'+':'')+r+"亿</span><br>"
    + "暗盘净额 <span class='"+dc+"'>"+(dk>=0?'+':'')+dk+"亿</span><br>"
    + "主力行为 <b>"+t.getAttribute('data-b')+"</b><br>"
    + "领涨 <b>"+t.getAttribute('data-l')+"</b>";
  tip.style.display='block';
  var x=e.clientX+14, y=e.clientY+14;
  if(x+290>window.innerWidth) x=e.clientX-290;
  if(y+150>window.innerHeight) y=e.clientY-150;
  tip.style.left=x+'px'; tip.style.top=y+'px';
}
document.getElementById('hmtab').addEventListener('mouseover', showTip);
document.addEventListener('mousemove', function(e){ if(tip.style.display==='block'){ var x=e.clientX+14,y=e.clientY+14; if(x+290>window.innerWidth)x=e.clientX-290; if(y+150>window.innerHeight)y=e.clientY-150; tip.style.left=x+'px'; tip.style.top=y+'px'; } });
document.getElementById('hmtab').addEventListener('mouseout', function(e){ if(!e.relatedTarget||!e.relatedTarget.closest||!e.relatedTarget.closest('td.cell')) tip.style.display='none'; });
['c-range','c-kind','c-sort','c-top'].forEach(function(id){ document.getElementById(id).addEventListener('change', render); });
render();
"""


def load_recent(days):
    fs = sorted(glob.glob(os.path.join(Q, "sector_daily", "*.json")))[-days:]
    out = []
    for f in fs:
        try:
            out.append(json.load(open(f, encoding="utf-8")))
        except Exception as e:
            print("[warn] 跳过损坏文件 %s: %s" % (os.path.basename(f), str(e)[:50]))
    return out


def build_html(dailies, days):
    # dates 升序（左旧右新）
    dates = sorted({d["date"] for d in dailies})
    # 行宇宙：以最新一日全量为基准（板块集合稳定）
    latest = max(dailies, key=lambda d: d["date"])
    latest_map = {r["name"]: r for r in latest["records"]}
    # 各日期 map
    date_maps = {d["date"]: {r["name"]: r for r in d["records"]} for d in dailies}

    rows = []
    for name, rec in latest_map.items():
        ser = []
        for d in dates:
            r = date_maps.get(d, {}).get(name)
            if r and isinstance(r.get("strengthVal"), (int, float)):
                ser.append([
                    round(float(r["strengthVal"]), 2),
                    round((r.get("mainVal") or 0) / 1e8, 1),   # 主力净流入 亿
                    round((r.get("retailVal") or 0) / 1e8, 1),  # 散户净流入 亿
                    round((r.get("darkVal") or 0) / 1e8, 1),    # 暗盘净额 亿
                    int(r.get("behaviorRank") or 0),
                ])
            else:
                ser.append(None)
        rows.append({
            "n": name,
            "k": rec.get("kind", ""),
            "b": int(rec.get("behaviorRank") or 0),
            "l": rec.get("leader", "") or "",
            "ser": ser,
        })

    sm = latest.get("summary", {})
    beh = sm.get("behavior", {})
    last_date = latest["date"]
    total_dark = sm.get("totalDarkY", 0)
    pay = {
        "dates": dates,
        "rows": rows,
        "behcls": {str(k): v for k, v in BEH_RANK2CLS.items()},
    }
    nav = topnav("sector", extra=(("趋势看板", "sector/sector-strength-trend.html"),))
    nav = nav.replace("<a href='sector/heatmap.html'>板块热力图</a>",
                      "<a href='sector/heatmap.html' class='cur'>板块热力图</a>", 1)

    html = (
        "<!DOCTYPE html>\n<html lang='zh-CN'>\n<head>\n<meta charset='UTF-8'>\n"
        "<meta name='viewport' content='width=device-width,initial-scale=1.0'>\n"
        "<title>A股板块强度 · 热力图</title>\n"
        "<style>" + CSS + "</style>\n</head>\n<body>\n<div class='wrap'>\n"
        + nav +
        "<header>\n<div>\n<h1>🔥 板块强度热力图</h1>\n"
        "<p>单元格底色 = 板块强度（红=强 / 绿=弱，按 |强度| 分级）｜ 悬停查看主力净流入 / 散户净流入 / 暗盘 / 行为 / 领涨。<br>"
        "强度 = (主力净流入 − 散户净流入) ÷ 板块总成交额 × 100 ｜ 数据来自 westock 盘后真实快照，前瞻累积、不回溯不编造。</p>\n"
        "</div>\n<div class='datebadge'><small>最新交易日</small>" + last_date + "</div>\n</header>\n"
        "<div class='meta'>数据基准 <b>" + last_date + "</b> ｜ 区间 " + dates[0] + " ~ " + dates[-1]
        + "（" + str(len(dates)) + " 个交易日）｜ 板块数 <b>" + str(len(rows))
        + "</b> ｜ 均强 <b>" + ("%.3f" % sm.get("avgStrength", 0)) + "</b> ｜ 上涨占比 <b>"
        + ("%.1f" % sm.get("upRatio", 0)) + "%</b></div>\n"
        "<div class='section'>\n<h2>概览（最新一日）</h2>\n<div class='idxrow'>\n"
        + "<div class='idx'><div class='k'>全市场暗盘净额</div><div class='v "
        + ("up" if total_dark >= 0 else "down") + "'>" + ("+" if total_dark >= 0 else "")
        + ("%.1f" % total_dark) + "<span style='font-size:12px;color:#7b8794'>亿</span></div></div>\n"
        + "<div class='idx'><div class='k'>均强</div><div class='v'>"
        + ("%.3f" % sm.get("avgStrength", 0)) + "</div></div>\n"
        + "<div class='idx'><div class='k'>上涨占比</div><div class='v'>"
        + ("%.1f" % sm.get("upRatio", 0)) + "%</div></div>\n"
        + "<div class='idx'><div class='k'>主力抢筹板块</div><div class='v up'>" + str(beh.get("抢筹", 0)) + "</div></div>\n"
        + "<div class='idx'><div class='k'>主力建仓板块</div><div class='v gold'>" + str(beh.get("建仓", 0)) + "</div></div>\n"
        + "<div class='idx'><div class='k'>主力洗盘板块</div><div class='v' style='color:#3b6fd1'>" + str(beh.get("洗盘", 0)) + "</div></div>\n"
        + "<div class='idx'><div class='k'>主力出货板块</div><div class='v down'>" + str(beh.get("出货", 0)) + "</div></div>\n"
        + "</div>\n</div>\n"
        "<div class='section'>\n<h2>强度热力图</h2>\n"
        "<div class='controls'>\n"
        + "<div class='ctl'><label>时间范围</label><select id='c-range'>"
        + "<option value='15'>近15日</option><option value='25' selected>近25日</option>"
        + "<option value='" + str(len(dates)) + "'>全部(" + str(len(dates)) + ")</option></select></div>\n"
        + "<div class='ctl'><label>类型</label><select id='c-kind'>"
        + "<option value='all'>全部</option><option value='行业'>行业</option><option value='概念'>概念</option></select></div>\n"
        + "<div class='ctl'><label>排序</label><select id='c-sort'>"
        + "<option value='strength' selected>最新强度↓</option><option value='name'>名称</option></select></div>\n"
        + "<div class='ctl'><label>数量</label><select id='c-top'>"
        + "<option value='60' selected>TOP60</option><option value='all'>全部(" + str(len(rows)) + ")</option></select></div>\n"
        + "<div class='legend'><span>弱</span><span class='bar'></span><span>强</span>"
        + "<span style='margin-left:6px'>（绿=跌 红=涨，按中国习惯）</span></div>\n"
        + "</div>\n<div class='hm-scroll'><table class='hm' id='hmtab'></table></div>\n"
        "<div class='empty'>提示：列排序为左旧右新；点击表头外的下拉框可切换范围/类型/排序/数量。底色越红越强、越绿越弱；灰点=当日无该板块快照。</div>\n"
        "</div>\n"
        "<footer>数据来源：腾讯自选股 westock-mcp（盘后公开数据）。<br>"
        "本页面由 A股量化助理自动生成 · 仅供参考，<b>不构成投资建议</b> · 市场有风险，投资需谨慎。</footer>\n"
        "</div>\n<div id='tip'></div>\n"
        "<script>var DATA = " + json.dumps(pay, ensure_ascii=False) + ";\n" + JS + "</script>\n"
        "</body>\n</html>"
    )
    return html


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=25)
    ap.add_argument("--output", default=os.path.join(WEB_SECTOR, "heatmap.html"))
    args = ap.parse_args()
    dailies = load_recent(args.days)
    if not dailies:
        raise SystemExit("sector_daily 下没有可用快照")
    out = args.output
    os.makedirs(os.path.dirname(out), exist_ok=True)
    open(out, "w", encoding="utf-8").write(build_html(dailies, args.days))
    print("[ok] 板块强度热力图 -> %s (%d 交易日 / %d 板块)"
          % (out, len(dailies), len(dailies and max(dailies, key=lambda d: d['date'])['records'] or [])))


if __name__ == "__main__":
    main()
