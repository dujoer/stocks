# -*- coding: utf-8 -*-
"""大宗交易 · 个股档案生成
--------------------------------
读取 quant/block_chg/ 全部交易日 JSON，按股票聚合，生成单个静态页：
  - web/block/stocks.html  （个股大宗档案：搜索 + 点击展开该股全部逐笔记录）

设计要点（为什么不是"动态页面"）：
  GitHub Pages 纯静态托管、无服务端；全量数据本地已有，生成器一次聚合内嵌进
  单个 HTML（2270 笔 / 380 只 ≈ 1MB），前端 JS 完成搜索 / 展开 / 排序 / 锚点定位，
  免部署、免后端、离线可用。

用法：
    python quant/build_block_stocks.py

硬规矩：只展示公开披露的大宗交易，不输出任何个人持仓、组合、选股内容。
"""
import os, json, glob, collections

from build_block import CSS, fmt_pct, wan, yi, seat_html, cls
from _nav import topnav

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
Q = os.path.join(ROOT, "quant")
OUT = os.path.join(ROOT, "web", "block", "stocks.html")

STOCK_CSS = """
#q { width:100%; max-width:460px; padding:9px 14px; border:1px solid #d8dce3; border-radius:8px;
  font-size:14px; margin:0 0 6px; background:#fff; outline:none; }
#q:focus { border-color:#b8893b; }
.qhint { font-size:12px; color:#9aa2ad; margin-bottom:14px; }
.qhint b { color:#b8893b; }
tr.srow { cursor:pointer; }
tr.srow:hover td { background:#faf6ee; }
tr.openrow td { background:#f6efe2; }
tr.sdet > td { padding:0 !important; background:#fbfbfc; }
.sdet table { width:100%; border-collapse:collapse; font-size:12.5px; margin:0; }
.sdet th { text-align:left; padding:7px 10px; color:#8a929c; font-weight:600;
  border-bottom:1px solid #e6e9ee; white-space:nowrap; background:#f3f4f6; }
.sdet td { padding:6px 10px; border-bottom:1px solid #f0f2f5; }
.sdet tr:last-child td { border-bottom:none; }
.flash td { animation:fl 1.6s ease-out 1; }
@keyframes fl { 0% { background:#fdeec9; } 100% { background:transparent; } }
"""

STOCK_JS = """
function sortPairs(th){
  var tbody=document.getElementById('st').tBodies[0];
  var pairs=[], rows=tbody.rows, i;
  for(i=0;i<rows.length;i++){
    if(rows[i].classList.contains('srow')){
      var d=rows[i].nextElementSibling;
      pairs.push([rows[i], (d&&d.classList.contains('sdet'))?d:null]);
    }
  }
  var idx=parseInt(th.getAttribute('data-c'),10);
  var asc=th.getAttribute('data-asc')!=='1';
  pairs.sort(function(a,b){
    var x=a[0].cells[idx].getAttribute('data-val');
    var y=b[0].cells[idx].getAttribute('data-val');
    var nx=parseFloat(x), ny=parseFloat(y);
    if(!isNaN(nx)&&!isNaN(ny)){ return asc?nx-ny:ny-nx; }
    x=(x==null?'':x); y=(y==null?'':y);
    return asc?(x<y?-1:(x>y?1:0)):(x<y?1:(x>y?-1:0));
  });
  for(i=0;i<pairs.length;i++){
    tbody.appendChild(pairs[i][0]);
    if(pairs[i][1]) tbody.appendChild(pairs[i][1]);
  }
  var ths=document.querySelectorAll('#st th.sort');
  for(i=0;i<ths.length;i++){ ths[i].removeAttribute('data-asc'); ths[i].classList.remove('sorted'); }
  th.setAttribute('data-asc', asc?'1':'0');
  th.classList.add('sorted');
}
function toggleRow(r){
  var d=r.nextElementSibling;
  if(!d||!d.classList.contains('sdet')) return;
  var open=d.style.display!=='none';
  d.style.display=open?'none':'';
  r.classList.toggle('openrow', !open);
}
document.querySelectorAll('#st tbody tr.srow').forEach(function(r){
  r.addEventListener('click', function(){ toggleRow(r); });
});
document.querySelectorAll('#st th.sort').forEach(function(t){
  t.addEventListener('click', function(ev){
    ev.stopPropagation();
    sortPairs(t);
  });
});
document.getElementById('q').addEventListener('input', function(){
  var v=this.value.trim().toLowerCase(), n=0;
  document.querySelectorAll('#st tbody tr.srow').forEach(function(r){
    var hit=!v || r.getAttribute('data-key').indexOf(v)>=0;
    r.style.display=hit?'':'none';
    var d=r.nextElementSibling;
    if(d&&d.classList.contains('sdet')){
      d.style.display=(hit && d.style.display==='')?'':'none';
    }
    if(hit) n++;
  });
  document.getElementById('cnt').textContent=n;
});
window.addEventListener('load', function(){
  var h=decodeURIComponent(location.hash.slice(1));
  if(!h) return;
  var r=document.getElementById(h);
  if(r&&r.classList.contains('srow')){
    var d=r.nextElementSibling;
    if(d&&d.classList.contains('sdet')){ d.style.display=''; r.classList.add('openrow','flash'); }
    setTimeout(function(){ r.scrollIntoView({behavior:'smooth', block:'center'}); }, 60);
  }
});
"""


def load_all():
    """读全部 block_chg，按股票聚合。返回 (stocks dict, dates list, totals)。"""
    files = sorted(glob.glob(os.path.join(Q, "block_chg", "2026-*.json")))
    stocks = collections.defaultdict(list)
    dates = []
    tot_val = 0
    tot_rows = 0
    for f in files:
        d = json.load(open(f, encoding="utf-8"))
        dt = d.get("date") or os.path.basename(f)[10:-5]
        dates.append(dt)
        for r in d.get("rows", []):
            r = dict(r)
            r["date"] = dt
            stocks[r["code"]].append(r)
            tot_val += r.get("value") or 0
            tot_rows += 1
    dates = sorted(set(dates))
    return stocks, dates, tot_rows, tot_val


def detail_table(rows):
    """单只股票的逐笔明细表（按日期倒序、同日按成交额倒序）。"""
    rows = sorted(rows, key=lambda x: (x["date"], -(x.get("value") or 0)), reverse=False)
    rows = sorted(rows, key=lambda x: x["date"], reverse=True)
    trs = []
    for r in rows:
        disc = r.get("discount")
        dcls = "disc" if (disc or 0) > 0 else ("prem" if (disc or 0) < 0 else "")
        chg = r.get("changePercent")
        ccls = cls(chg)
        trs.append(
            f"<tr>"
            f"<td><a class='slk' href='block_{r['date']}.html'>{r['date']}</a></td>"
            f"<td class='num'>{r.get('tradePrice', '—')}</td>"
            f"<td class='num {dcls}'>{fmt_pct(disc)}</td>"
            f"<td class='num'>{wan(r.get('value'))}</td>"
            f"<td class='num' data-val='{r.get('ratio', '')}'>{r.get('ratio', '—')}</td>"
            f"<td class='num {ccls}'>{fmt_pct(chg)}</td>"
            f"<td>{seat_html(r.get('buyer'))}</td>"
            f"<td>{seat_html(r.get('seller'))}</td>"
            f"<td>{r.get('type', '')}</td>"
            f"</tr>")
    return ("<table><thead><tr>"
            "<th>交易日</th><th>成交价</th><th>折溢价</th><th>成交额(万元)</th>"
            "<th>占比(%)</th><th>当日涨跌</th><th>买方营业部</th><th>卖方营业部</th><th>类型</th>"
            "</tr></thead><tbody>" + "".join(trs) + "</tbody></table>")


def main():
    stocks, dates, tot_rows, tot_val = load_all()
    first_d, last_d = dates[0], dates[-1]

    items = []
    for code, rows in stocks.items():
        vals = [r.get("value") or 0 for r in rows]
        discs = [r.get("discount") for r in rows if r.get("discount") is not None]
        avg_disc = sum(discs) / len(discs) if discs else None
        days = sorted(set(r["date"] for r in rows))
        items.append({
            "code": code,
            "name": rows[0].get("name", code),
            "days": len(days),
            "count": len(rows),
            "value": sum(vals),
            "avg_disc": avg_disc,
            "first": days[0],
            "last": days[-1],
            "rows": rows,
        })
    items.sort(key=lambda x: (-x["value"], x["code"]))

    cards = (
        f"<div class='idx'><div class='k'>覆盖交易日</div><div class='v'>{len(dates)}</div></div>"
        f"<div class='idx'><div class='k'>个股数量</div><div class='v gold'>{len(items)}</div></div>"
        f"<div class='idx'><div class='k'>累计成交笔数</div><div class='v'>{tot_rows}</div></div>"
        f"<div class='idx'><div class='k'>累计成交额（亿元）</div><div class='v gold'>{yi(tot_val)}</div></div>"
    )

    body_rows = []
    for e in items:
        ad = e["avg_disc"]
        adcls = "disc" if (ad or 0) > 0 else ("prem" if (ad or 0) < 0 else "")
        key = f"{e['name']} {e['code']}".lower()
        body_rows.append(
            f"<tr class='srow' id='{e['code']}' data-key='{key}'>"
            f"<td data-val='{e['name']}'><a class='slk' href='stocks.html#{e['code']}' "
            f"onclick=\"event.stopPropagation()\">{e['name']}</a></td>"
            f"<td class='num' data-val='{e['code']}'>{e['code']}</td>"
            f"<td class='num' data-val='{e['days']}'>{e['days']}</td>"
            f"<td class='num' data-val='{e['count']}'>{e['count']}</td>"
            f"<td class='num' data-val='{e['value']}'>{wan(e['value'])}</td>"
            f"<td class='num {adcls}' data-val='{ad}'>{fmt_pct(ad)}</td>"
            f"<td data-val='{e['first']}'>{e['first']}</td>"
            f"<td data-val='{e['last']}'>{e['last']}</td>"
            f"</tr>")
        body_rows.append(
            f"<tr class='sdet' style='display:none'><td colspan='8'>{detail_table(e['rows'])}</td></tr>")

    head_cells = (
        "<th class='sort' data-c='0'>股票</th>"
        "<th class='sort' data-c='1'>代码</th>"
        "<th class='num sort' data-c='2'>交易天数</th>"
        "<th class='num sort' data-c='3'>笔数</th>"
        "<th class='num sort' data-c='4'>累计成交额(万元)</th>"
        "<th class='num sort' data-c='5'>平均折溢价</th>"
        "<th class='sort' data-c='6'>首次日期</th>"
        "<th class='sort' data-c='7'>最近日期</th>")

    html = f"""<!DOCTYPE html>
<html lang='zh-CN'>
<head>
<meta charset='UTF-8'>
<meta name='viewport' content='width=device-width,initial-scale=1.0'>
<title>大宗交易 · 个股档案</title>
<style>{CSS}</style>
<style>{STOCK_CSS}</style>
</head>
<body>
<div class='wrap'>
{topnav("block")}
<div class='datenav'>
  <a class='arch' href='archive.html'>归档总览</a>
  <a class='cur' href='stocks.html'>个股档案</a>
  <a href='index.html'>最新一期（{last_d}）</a>
  <a href='../../index.html'>返回总门户</a>
</div>
<header>
  <div>
    <h1>大宗交易 · 个股档案</h1>
    <p>统计期内全部大宗交易按个股归档：输入名称/代码过滤，点击任意行展开该股逐笔记录；<br>
    从其它页面点击股票名也会跳转到对应档案。覆盖 <b>{first_d}</b> ~ <b>{last_d}</b>。</p>
  </div>
  <div class='datebadge'>{last_d}</div>
</header>
<div class='idxrow'>{cards}</div>
<div class='section'>
  <h2>个股一览（按累计成交额排序）</h2>
  <input id='q' placeholder='🔍 输入股票名称或代码过滤，如：巨人 / 002558'>
  <div class='qhint'>匹配 <b id='cnt'>{len(items)}</b> 只 ｜ 点击行展开逐笔明细，点击表头排序</div>
  <table id='st'><thead><tr>{head_cells}</tr></thead><tbody>{''.join(body_rows)}</tbody></table>
</div>
<footer>
数据来源：腾讯自选股 <b>westock-mcp</b>（盘后公开数据）。折溢价为相对当日收盘价：<b>正=折价成交</b>，<b>负=溢价成交</b>。<br>
本页面由 A股量化助理自动生成 · 仅供参考，<b>不构成投资建议</b> · 市场有风险，投资需谨慎。
</footer>
</div>
<script>{STOCK_JS}</script>
</body>
</html>
"""
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"OK -> {OUT}（{len(items)} 只 / {tot_rows} 笔 / {len(dates)} 个交易日，{os.path.getsize(OUT)//1024} KB）")


if __name__ == "__main__":
    main()
