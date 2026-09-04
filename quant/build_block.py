# -*- coding: utf-8 -*-
"""大宗交易 · 看板生成
--------------------------------
读取 quant/block_chg/{DATE}.json，生成自包含 HTML：
  - web/block.html        （最新一期）
  - web/block_{DATE}.html （每日归档，长期保留）

版块内容：
  1) 概览卡：成交笔数 / 涉及股票 / 合计成交额 / 平均折溢价 / 折价·溢价 / 机构买方
  2) 个股聚合榜：按成交额排序（笔数 / 成交额 / 平均折溢价 / 当日涨跌幅）
  3) 明细表（JS 筛选：全部 / 机构买入 / 溢价成交）：买卖营业部、成交价、成交额、折溢价

用法：
    python quant/build_block.py --date 2026-09-04

硬规矩：只展示公开披露的大宗交易，不输出任何个人持仓、组合、选股内容。
"""
import os, argparse, json, re, datetime

from _nav import topnav

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
Q = os.path.join(ROOT, "quant")
WEB = os.path.join(ROOT, "web")
OUT_DIR = os.path.join(Q, "block_chg")

CSS = """* { box-sizing: border-box; }
body { margin:0; font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;
  background:#f5f6f8; color:#23262b; min-height:100vh; }
.wrap { max-width:1180px; margin:0 auto; padding:40px 20px 60px; }
.topnav { display:flex; flex-wrap:wrap; gap:8px; margin-bottom:22px; padding-bottom:14px;
  border-bottom:1px solid rgba(0,0,0,.08); }
.topnav a { color:#b8893b; text-decoration:none; font-size:13px; padding:4px 12px; border-radius:20px;
  border:1px solid rgba(184,137,59,.35); transition:.2s; }
.topnav a:hover { background:rgba(184,137,59,.10); }
header h1 { font-size:30px; margin:0 0 6px; background:linear-gradient(90deg,#b8893b,#b8332a,#6b5b95);
  -webkit-background-clip:text; background-clip:text; color:transparent; font-weight:800; }
header p { margin:4px 0; color:#8a929c; font-size:13px; line-height:1.6; }
.meta { margin:14px 0 24px; font-size:12px; color:#6b7280; line-height:1.7; }
.meta b { color:#b8893b; }
.section { background:#ffffff; border:1px solid rgba(0,0,0,.08); border-radius:20px;
  padding:18px 20px; margin:0 0 22px; }
.section h2 { font-size:19px; margin:0 0 14px; padding-left:12px; border-left:5px solid #b8893b; }
.idxrow { display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:14px; }
.idx { background:#fafbfc; border:1px solid #eef1f4; border-radius:14px; padding:14px 16px; }
.idx .k { font-size:12px; color:#7b8794; }
.idx .v { font-size:24px; font-weight:800; margin-top:4px; color:#23262b; }
.idx .v.buy { color:#b8332a; } .idx .v.sell { color:#1a9e5a; } .idx .v.gold { color:#b8893b; }
table { width:100%; border-collapse:collapse; font-size:13px; }
th { text-align:left; padding:9px 10px; background:#f7f8fa; color:#5a6573; font-weight:700;
  border-bottom:2px solid #e3e7ec; white-space:nowrap; }
td { padding:9px 10px; border-bottom:1px solid #f0f2f5; }
tr:hover td { background:#fcfbf8; }
.num { text-align:right; font-variant-numeric:tabular-nums; white-space:nowrap; }
.up { color:#b8332a; font-weight:700; } .down { color:#1a9e5a; font-weight:700; } .flat { color:#8a929c; }
.disc { color:#b8893b; font-weight:600; } .prem { color:#6b5b95; font-weight:600; }
.seat { font-size:12px; color:#6b7280; }
.inst { display:inline-block; font-size:11px; padding:1px 7px; border-radius:10px;
  background:#eef4fa; color:#1f4e79; margin-left:6px; white-space:nowrap; }
.tabs { margin-bottom:12px; }
.tab { display:inline-block; padding:5px 14px; margin-right:8px; border-radius:18px; cursor:pointer;
  font-size:13px; border:1px solid rgba(184,137,59,.35); color:#b8893b; background:#fff; }
.tab.on { background:#b8893b; color:#fff; }
.empty { padding:26px; text-align:center; color:#8a929c; font-size:13px; }
.datenav { display:flex; flex-wrap:wrap; gap:8px; margin:0 0 18px; font-size:13px; }
.datenav a { color:#1f4e79; text-decoration:none; padding:5px 13px; border-radius:18px;
  background:#eef4fa; border:1px solid #dbe6f2; }
.datenav a:hover { background:#dbe6f2; }
footer { margin-top:40px; padding-top:18px; border-top:1px solid #e3e7ec;
  font-size:12px; color:#7b8794; line-height:1.8; }
"""

JS = """
function filterBlock(mode){
  var rows=document.querySelectorAll('#bt tbody tr');
  for(var i=0;i<rows.length;i++){
    var r=rows[i], show=true;
    if(mode==='inst') show=r.getAttribute('data-inst')==='1';
    else if(mode==='prem') show=r.getAttribute('data-prem')==='1';
    r.style.display=show?'':'none';
  }
  var tabs=document.querySelectorAll('.tab');
  for(var j=0;j<tabs.length;j++) tabs[j].className='tab'+(tabs[j].getAttribute('data-m')===mode?' on':'');
}
document.querySelectorAll('.tab').forEach(function(t){
  t.addEventListener('click',function(){ filterBlock(t.getAttribute('data-m')); });
});
"""


def cls(v):
    try:
        v = float(v)
    except Exception:
        return "flat"
    return "up" if v > 0 else ("down" if v < 0 else "flat")


def fmt_pct(v, digits=2):
    if v is None:
        return "—"
    return f"{v:+.{digits}f}%"


def wan(v):
    """元 → 万元"""
    try:
        return f"{float(v)/1e4:,.1f}"
    except Exception:
        return "—"


def yi(v):
    try:
        return f"{float(v)/1e8:,.4f}"
    except Exception:
        return "—"


def seat_html(s):
    s = s or "—"
    if "机构专用" in s:
        return f"{s}<span class='inst'>机构</span>"
    return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    a = ap.parse_args()
    DATE = a.date

    src = os.path.join(OUT_DIR, f"{DATE}.json")
    if not os.path.exists(src):
        print(f"✗ 缺数据文件: {src}（请先跑 quant/gen_block.py --date {DATE}）")
        return
    d = json.load(open(src, encoding="utf-8"))
    rows = d.get("rows", [])
    by_stock = d.get("byStock", [])

    # ---- 日期归档导航 ----
    dates = []
    if os.path.isdir(WEB):
        for fn in os.listdir(WEB):
            m = re.match(r"^block_(\d{4}-\d{2}-\d{2})\.html$", fn)
            if m:
                dates.append(m.group(1))
    dates = sorted(set(dates + [DATE]), reverse=True)
    prev_d = next((x for x in dates if x < DATE), None)
    next_d = next((x for x in reversed(dates) if x > DATE), None)
    datenav = "<div class='datenav'>"
    if prev_d:
        datenav += f"<a href='block_{prev_d}.html'>← {prev_d}</a>"
    datenav += f"<a href='#' style='background:#b8893b;color:#fff;border-color:#b8893b'>{DATE}</a>"
    if next_d:
        datenav += f"<a href='block_{next_d}.html'>{next_d} →</a>"
    datenav += f"<a href='../index.html'>返回总门户</a>"
    if len(dates) > 1:
        datenav += f"<span style='align-self:center;color:#8a929c'>归档 {len(dates)} 期</span>"
    datenav += "</div>"

    # ---- 概览 ----
    cards = (
        f"<div class='idx'><div class='k'>成交笔数</div><div class='v gold'>{d['count']}</div></div>"
        f"<div class='idx'><div class='k'>涉及股票</div><div class='v'>{d['stockCount']}</div></div>"
        f"<div class='idx'><div class='k'>合计成交额（亿元）</div><div class='v gold'>{yi(d['totalValue'])}</div></div>"
        f"<div class='idx'><div class='k'>平均折溢价</div><div class='v'>{fmt_pct(d['avgDiscount'])}</div></div>"
        f"<div class='idx'><div class='k'>折价 / 溢价</div>"
        f"<div class='v'><span class='down'>{d['discCount']}</span> / <span class='up'>{d['premCount']}</span></div></div>"
        f"<div class='idx'><div class='k'>机构买入笔数</div><div class='v buy'>{d['instBuyCount']}</div></div>"
    )

    # ---- 个股聚合 ----
    if by_stock:
        st_rows = "".join(
            f"<tr><td>{e['name']}</td><td class='num'>{e['code']}</td>"
            f"<td class='num'>{e['count']}</td>"
            f"<td class='num'>{wan(e['value'])}</td>"
            f"<td class='num {'disc' if (e['avgDiscount'] or 0)>0 else ('prem' if (e['avgDiscount'] or 0)<0 else '')}'>"
            f"{fmt_pct(e['avgDiscount'])}</td>"
            f"<td class='num {cls(e.get('changePercent'))}'>{fmt_pct(e.get('changePercent'))}</td></tr>"
            for e in by_stock)
        stock_html = (f"<table id='bs'><thead><tr><th>股票</th><th>代码</th><th class='num'>笔数</th>"
                      f"<th class='num'>成交额(万元)</th><th class='num'>平均折溢价</th>"
                      f"<th class='num'>当日涨跌</th></tr></thead><tbody>{st_rows}</tbody></table>")
    else:
        stock_html = "<div class='empty'>当日无大宗交易记录</div>"

    # ---- 明细 ----
    if rows:
        det = []
        for r in rows:
            disc = r.get("discount")
            dcls = "disc" if (disc or 0) > 0 else ("prem" if (disc or 0) < 0 else "")
            is_inst = "1" if "机构专用" in (r.get("buyer") or "") else "0"
            is_prem = "1" if (disc is not None and disc < 0) else "0"
            det.append(
                f"<tr data-inst='{is_inst}' data-prem='{is_prem}'>"
                f"<td>{r.get('name','')}</td><td class='num'>{r.get('code','')}</td>"
                f"<td class='num'>{r.get('tradePrice','—')}</td>"
                f"<td class='num {cls(r.get('changePercent'))}'>{fmt_pct(r.get('changePercent'))}</td>"
                f"<td class='num'>{wan(r.get('value'))}</td>"
                f"<td class='num {dcls}'>{fmt_pct(disc)}</td>"
                f"<td class='num'>{r.get('ratio','—')}</td>"
                f"<td class='seat'>{seat_html(r.get('buyer'))}</td>"
                f"<td class='seat'>{seat_html(r.get('seller'))}</td>"
                f"<td>{r.get('type','')}</td></tr>")
        detail_html = (
            f"<div class='tabs'>"
            f"<span class='tab on' data-m='all'>全部 {len(rows)}</span>"
            f"<span class='tab' data-m='inst'>机构买入 {d['instBuyCount']}</span>"
            f"<span class='tab' data-m='prem'>溢价成交 {d['premCount']}</span></div>"
            f"<table id='bt'><thead><tr><th>股票</th><th>代码</th><th class='num'>成交价</th>"
            f"<th class='num'>当日涨跌</th><th class='num'>成交额(万元)</th><th class='num'>折溢价</th>"
            f"<th class='num'>占比(%)</th><th>买方营业部</th><th>卖方营业部</th><th>类型</th>"
            f"</tr></thead><tbody>{''.join(det)}</tbody></table>")
    else:
        detail_html = "<div class='empty'>当日无大宗交易记录</div>"

    html = f"""<!DOCTYPE html>
<html lang='zh-CN'>
<head>
<meta charset='UTF-8'>
<meta name='viewport' content='width=device-width,initial-scale=1.0'>
<title>大宗交易 · {DATE}</title>
<style>{CSS}</style>
</head>
<body>
<div class='wrap'>
{topnav()}
{datenav}
<header>
  <h1>大宗交易</h1>
  <p>全市场大宗交易逐笔追踪：谁在折价出货、谁在溢价接盘、机构席位动向。</p>
</header>

<div class='meta'>
交易日 <b>{DATE}</b> ｜ 接口快照日 <b>{d.get('snapDate') or DATE}</b><br>
数据口径：westock 事件 <b>大宗交易一月内（block_past_30）</b>中按 <b>TradeDay={DATE.replace('-','')}</b> 筛选，
共 <b>{d['count']}</b> 笔、覆盖 <b>{d['stockCount']}</b> 只股票、合计 <b>{yi(d['totalValue'])}</b> 亿元；
「当日涨跌」为交易日行情快照（已补齐 <b>{d.get('quoteMatched',0)}/{d['count']}</b> 笔）。
折溢价为相对当日收盘价：<b>正=折价成交</b>，<b>负=溢价成交</b>。
</div>

<div class='section'>
  <h2>概览</h2>
  <div class='idxrow'>{cards}</div>
</div>

<div class='section'>
  <h2>个股聚合（按成交额）</h2>
  {stock_html}
</div>

<div class='section'>
  <h2>逐笔明细（按成交额）</h2>
  {detail_html}
</div>

<footer>
数据来源：腾讯自选股 <b>westock-mcp</b>（盘后公开数据）。<br>
本页面由 A股量化助理自动生成 · 仅供参考，<b>不构成投资建议</b> · 市场有风险，投资需谨慎。
</footer>
</div>
<script>{JS}</script>
</body>
</html>
"""

    os.makedirs(WEB, exist_ok=True)
    page_bytes = html.encode("utf-8")
    dst_dated = os.path.join(WEB, f"block_{DATE}.html")
    with open(dst_dated, "w", encoding="utf-8") as f:
        f.write(html)
    latest = max(dates)
    if DATE >= latest:
        with open(os.path.join(WEB, "block.html"), "w", encoding="utf-8") as f:
            f.write(html)
        print(f"OK -> {dst_dated}（并更新最新版 web/block.html）")
    else:
        print(f"OK -> {dst_dated}（历史归档，未覆盖 web/block.html 最新={latest}）")
    print(f"    笔数 {d['count']}｜股票 {d['stockCount']}｜成交额 {yi(d['totalValue'])} 亿元")


if __name__ == "__main__":
    main()
