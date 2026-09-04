# -*- coding: utf-8 -*-
"""
高管（董监高）增减持 · 看板生成
--------------------------------
读取 quant/exec_chg/{DATE}.json，生成自包含 HTML：web/exec.html
风格与 web/lhb.html 保持一致（深色 + 金色点缀，涨红跌绿）。

版块内容：
  1) 概览卡：增持/减持 记录数与金额、净变动、涉及股票数、最新披露日
  2) 行业分布：按申万一级聚合增减持金额（chip）
  3) 五张表（JS 切换）：最新披露日 / 增持榜 / 减持榜 / 个股聚合 / 全部明细
  4) 方向筛选（全部 / 仅增持 / 仅减持）

用法：
    python quant/build_exec.py --date 2026-09-02

硬规矩：只展示公开披露的高管增减持，不输出任何个人持仓、组合、选股内容。
"""
import os, sys, json, argparse, collections, datetime
from _nav import topnav

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
Q = os.path.join(ROOT, "quant")
WEB = os.path.join(ROOT, "web")

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
.section { background:#ffffff;
  border:1px solid rgba(0,0,0,.08); border-radius:20px; padding:18px 20px; margin:0 0 22px;
  box-shadow:0 1px 3px rgba(20,30,50,.05); backdrop-filter:blur(10px); }
.section h2 { font-size:17px; margin:0 0 14px; color:#1c2430; display:flex; align-items:center; gap:8px; }
.section h2:before { content:""; width:4px; height:16px; background:#b8893b; border-radius:3px; }
.idxrow { display:flex; flex-wrap:wrap; gap:12px; margin-bottom:12px; }
.idx { flex:1; min-width:168px; background:linear-gradient(135deg,rgba(184,51,42,.08),rgba(184,51,42,.03));
  border:1px solid rgba(184,51,42,.20); border-radius:14px; padding:13px 10px; text-align:center;
  box-shadow:0 1px 3px rgba(184,51,42,.06); }
.idx .k { font-size:11px; color:#6b7280; letter-spacing:.3px; }
.idx .v { font-size:22px; font-weight:800; color:#1c2430; margin:5px 0 2px; }
.idx .hl { font-size:10px; color:#8a929c; margin-top:4px; }
.chiprow { display:flex; flex-wrap:wrap; gap:8px; margin:10px 0; }
.chip { background:rgba(0,0,0,.05); border:1px solid rgba(0,0,0,.06); border-radius:12px;
  padding:10px 8px; text-align:center; min-width:96px; backdrop-filter:blur(6px); box-shadow:0 1px 3px rgba(20,30,50,.04); }
.chip-ind { cursor:pointer; transition:.18s; }
.chip-ind:hover { background:rgba(184,137,59,.10); transform:translateY(-1px); }
.chip-ind.on { background:rgba(184,137,59,.18); border-color:rgba(184,137,59,.50); box-shadow:0 2px 6px rgba(184,137,59,.18); }
.chip-all { background:rgba(184,137,59,.10); border-color:rgba(184,137,59,.30); }
.chip-all:hover { background:rgba(184,137,59,.18); }
.chip .ck { font-size:10px; color:#8a929c; }
.chip .cv { font-size:15px; font-weight:800; margin-top:3px; }
.chip .cs { font-size:10px; margin-top:2px; }
table { width:100%; border-collapse:collapse; font-size:13px; background:rgba(0,0,0,.03);
  border:1px solid rgba(0,0,0,.05); border-radius:12px; overflow:hidden; margin:10px 0; }
th,td { padding:8px 10px; text-align:left; border-bottom:1px solid rgba(0,0,0,.04); }
th { background:rgba(20,30,50,.06); color:#3a4048; font-weight:600; font-size:12px; }
td.num,th.num { text-align:right; font-variant-numeric:tabular-nums; }
tr:last-child td { border-bottom:none; }
.up { color:#d8392b; } .down { color:#1a9e5a; }
.buy { color:#d8392b; font-weight:700; } .sell { color:#1a9e5a; font-weight:700; }
.badge-b { display:inline-block; background:rgba(224,112,95,.16); border:1px solid rgba(224,112,95,.4);
  color:#d8392b; border-radius:20px; padding:2px 9px; font-size:11px; font-weight:700; }
.badge-s { display:inline-block; background:rgba(127,184,148,.16); border:1px solid rgba(127,184,148,.4);
  color:#1a9e5a; border-radius:20px; padding:2px 9px; font-size:11px; font-weight:700; }
.tabs { display:flex; flex-wrap:wrap; gap:8px; margin:6px 0 14px; }
.tab { cursor:pointer; background:rgba(0,0,0,.04); border:1px solid rgba(0,0,0,.06);
  color:#6b7280; border-radius:20px; padding:6px 14px; font-size:12.5px; transition:.18s; user-select:none; }
.tab:hover { background:rgba(184,137,59,.10); color:#23262b; }
.tab.on { background:rgba(184,137,59,.18); border-color:rgba(184,137,59,.50); color:#1c2430; font-weight:700; }
.filters { display:flex; flex-wrap:wrap; gap:8px; margin:0 0 10px; align-items:center; }
.filters .lb { font-size:12px; color:#8a929c; margin-right:2px; }
.note { color:#8a929c; font-size:12px; margin-top:8px; line-height:1.65; }
.scroll { max-height:620px; overflow:auto; border-radius:12px; }
.scroll table { margin:0; }
.scroll thead th { position:sticky; top:0; z-index:2; }
.hide { display:none; }
footer { margin-top:34px; padding-top:16px; border-top:1px solid rgba(0,0,0,.08);
  font-size:12px; color:#7b8794; line-height:1.8; }"""

JS = """
function switchTab(id){
  document.querySelectorAll('.tab[data-tab]').forEach(function(t){ t.classList.toggle('on', t.dataset.tab===id); });
  document.querySelectorAll('.pane').forEach(function(p){ p.classList.toggle('hide', p.id!==id); });
}
function setDir(v){
  window.__dir = v;
  document.querySelectorAll('.fbtn').forEach(function(b){ b.classList.toggle('on', b.dataset.dir===v); });
  document.querySelectorAll('tr[data-dir]').forEach(function(tr){
    tr.classList.toggle('hide', !(v==='all' || tr.dataset.dir===v));
  });
  // 方向变化时也要尊重行业筛选（已选行业时，非该行业行继续隐藏）
  if (window.__ind) applyIndustry();
}
function filterIndustry(name){
  window.__ind = (window.__ind===name ? null : name);
  applyIndustry();
}
function clearIndustry(){
  window.__ind = null;
  document.querySelectorAll('.chip-ind').forEach(function(c){ c.classList.toggle('on', false); });
  document.querySelectorAll('tr[data-sw1]').forEach(function(tr){ tr.classList.remove('hide'); });
  // 行业重置后仍尊重方向筛选
  if (window.__dir && window.__dir!=='all') setDir(window.__dir);
}
function applyIndustry(){
  var ind = window.__ind;
  document.querySelectorAll('.chip-ind').forEach(function(c){ c.classList.toggle('on', c.dataset.industry===ind); });
  document.querySelectorAll('tr[data-sw1]').forEach(function(tr){
    var sw = tr.dataset.sw1;
    var dirMatch = (!window.__dir || window.__dir==='all' || tr.dataset.dir===window.__dir);
    var indMatch = (!ind || sw===ind);
    tr.classList.toggle('hide', !(dirMatch && indMatch));
  });
}
document.addEventListener('DOMContentLoaded', function(){
  var t0 = document.querySelector('.tab[data-tab]'); if(t0) switchTab(t0.dataset.tab);
  var f0 = document.querySelector('.fbtn'); if(f0) setDir('all');
});
"""


def fmt_date(s):
    s = str(s).strip()
    if len(s) == 8 and s.isdigit():
        return f"{s[:4]}-{s[4:6]}-{s[6:]}"
    return s or "—"


def wan(v):
    """元 -> 万元 字符串"""
    return f"{v/10000:,.1f}"


def shares_wan(v):
    """股 -> 万股 字符串（带符号）"""
    return f"{v/10000:+,.2f}"


def pct_cls(v):
    if v is None:
        return ""
    return "up" if v > 0 else ("down" if v < 0 else "")


def pct_txt(v):
    if v is None:
        return "—"
    return f"{v:+.2f}%"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    args = ap.parse_args()
    DATE = args.date

    src = os.path.join(Q, "exec_chg", f"{DATE}.json")
    if not os.path.exists(src):
        print(f"缺少数据文件 {src}，请先运行 gen_exec.py --date {DATE}")
        sys.exit(2)
    d = json.load(open(src, encoding="utf-8"))
    recs = d["records"]

    buy = [r for r in recs if r["dir"] == "增持"]
    sell = [r for r in recs if r["dir"] == "减持"]
    buy_amt = sum(r["amount"] for r in buy)
    sell_amt = sum(r["amount"] for r in sell)
    net = buy_amt - sell_amt
    latest = d.get("latestDeclare")

    # ---- 行业聚合（申万一级）----
    by_sw1 = collections.defaultdict(lambda: {"b": 0.0, "s": 0.0, "n": 0})
    for r in recs:
        k = r.get("sw1") or "其他"
        by_sw1[k]["n"] += 1
        if r["dir"] == "增持":
            by_sw1[k]["b"] += r["amount"]
        else:
            by_sw1[k]["s"] += r["amount"]
    sw1_sorted = sorted(by_sw1.items(), key=lambda kv: -(kv[1]["b"] + kv[1]["s"]))[:18]

    chips = "\n".join(
        f"<div class='chip chip-ind' data-industry='{k}' onclick='filterIndustry(this.dataset.industry)' title='点击仅看「{k}」行业'>"
        f"<div class='ck'>{k}</div>"
        f"<div class='cv'>{wan(v['b']+v['s'])}<span style='font-size:10px;color:#8a929c'> 万</span></div>"
        f"<div class='cs'><span class='buy'>+{wan(v['b'])}</span> / <span class='sell'>-{wan(v['s'])}</span></div></div>"
        for k, v in sw1_sorted
    )

    # ---- 个股聚合 ----
    by_code = collections.defaultdict(lambda: {"net": 0.0, "n": 0, "b": 0, "s": 0, "recs": []})
    for r in recs:
        g = by_code[r["code"]]
        g["net"] += r["shares"] * r["price"]   # 带符号净额（元）
        g["n"] += 1
        g["b" if r["dir"] == "增持" else "s"] += 1
        g["recs"].append(r)
    agg = []
    for code, g in by_code.items():
        r0 = g["recs"][0]
        agg.append({
            "code": code, "name": r0["name"], "sw1": r0["sw1"], "sw2": r0["sw2"],
            "net": g["net"], "n": g["n"], "b": g["b"], "s": g["s"],
            "chgPct": r0.get("chgPct"),
            "last": max((x["declare"] for x in g["recs"])),
        })
    agg.sort(key=lambda x: -x["net"])

    # ---- 表格渲染 ----
    def rows(items, show_manager=True):
        out = []
        for r in items:
            dirb = ("<span class='badge-b'>增持</span>" if r["dir"] == "增持"
                    else "<span class='badge-s'>减持</span>")
            mgr = f"<td>{r['manager']}</td>" if show_manager else ""
            out.append(
                f"<tr data-dir='{'b' if r['dir']=='增持' else 's'}' data-sw1='{r.get('sw1') or '其他'}'>"
                f"<td><b>{r['name']}</b></td><td style='color:#8a929c;font-size:12px'>{r['code']}</td>"
                f"<td>{r.get('sw1') or '—'}</td>"
                f"<td style='color:#6b7280;font-size:12px'>{r.get('sw2') or '—'}</td>"
                f"{mgr}"
                f"<td style='text-align:center'>{dirb}</td>"
                f"<td class='num {('buy' if r['dir']=='增持' else 'sell')}'>{shares_wan(r['shares'])}</td>"
                f"<td class='num'>{r['price']:.2f}</td>"
                f"<td class='num {('buy' if r['dir']=='增持' else 'sell')}'>{wan(r['amount'])}</td>"
                f"<td style='color:#6b7280;font-size:12px'>{fmt_date(r['declare'])}</td>"
                f"<td class='num {pct_cls(r.get('chgPct'))}'>{pct_txt(r.get('chgPct'))}</td></tr>")
        return "\n".join(out)

    mgr_th = "<th>高管</th>"
    base_th = ("<th>股票</th><th>代码</th><th>申万一级</th><th>申万二级</th>"
               f"{mgr_th}<th style='text-align:center'>方向</th>"
               "<th class='num'>变动股数(万股)</th><th class='num'>均价(元)</th>"
               "<th class='num'>变动金额(万元)</th><th>披露日</th><th class='num'>当日涨跌</th>")

    # 披露日范围（辅助 meta 显示；2026-08-01/08-02 为周末无变动）
    decl_dates = sorted(set(r["declare"] for r in recs))
    date_range_txt = (f"{fmt_date(decl_dates[0])} → {fmt_date(decl_dates[-1])}"
                      if decl_dates else "—")
    date_window_days = len(decl_dates)

    # 最新披露日
    latest_recs = [r for r in recs if r["declare"] == latest]
    latest_recs.sort(key=lambda r: -r["amount"])
    t_latest = rows(latest_recs)

    # 增持/减持榜
    t_buy = rows(sorted(buy, key=lambda r: -r["amount"])[:60])
    t_sell = rows(sorted(sell, key=lambda r: -r["amount"])[:60])

    # 个股聚合表
    agg_rows = []
    for a in agg[:80]:
        net_cls = "buy" if a["net"] > 0 else ("sell" if a["net"] < 0 else "")
        agg_rows.append(
            f"<tr data-dir='{'b' if a['net']>0 else 's'}' data-sw1='{a['sw1'] or '其他'}'>"
            f"<td><b>{a['name']}</b></td><td style='color:#8a929c;font-size:12px'>{a['code']}</td>"
            f"<td>{a['sw1'] or '—'}</td>"
            f"<td style='color:#6b7280;font-size:12px'>{a['sw2'] or '—'}</td>"
            f"<td class='num'>{a['n']}</td>"
            f"<td class='num buy'>{a['b']}</td><td class='num sell'>{a['s']}</td>"
            f"<td class='num {net_cls}'>{wan(a['net'])}</td>"
            f"<td style='color:#6b7280;font-size:12px'>{fmt_date(a['last'])}</td>"
            f"<td class='num {pct_cls(a['chgPct'])}'>{pct_txt(a['chgPct'])}</td></tr>")
    t_agg = "\n".join(agg_rows)

    # 全部明细
    t_all = rows(sorted(recs, key=lambda r: (r["declare"], -r["amount"]), reverse=True))

    net_cls = "buy" if net > 0 else "sell"
    net_txt = ("净增持" if net > 0 else "净减持")

    html = f"""<!DOCTYPE html>
<html lang='zh-CN'>
<head>
<meta charset='UTF-8'>
<meta name='viewport' content='width=device-width,initial-scale=1.0'>
<title>高管增减持 · {DATE}</title>
<style>{CSS}</style>
</head>
<body>
<div class='wrap'>

{topnav()}

<header>
  <h1>高管增减持（董监高）</h1>
  <p>全市场董监高持股变动披露追踪：谁在买、谁在卖、买多少、什么行业。</p>
</header>

<div class='meta'>
采集日 <b>{DATE}</b> ｜ 接口快照日 <b>{d.get('snapDate')}</b> ｜ 最新披露日 <b>{fmt_date(latest)}</b><br>
数据口径：westock 事件 <b>董监高增减持（近 1 个月窗口）</b>，共 <b>{d['count']}</b> 条变动记录，
覆盖 <b>{d['stockCount']}</b> 只股票、<b>{date_window_days}</b> 个披露交易日（<b>{date_range_txt}</b>）；行业取自申万一/二级分类。
「当日涨跌」为采集日行情快照，非变动当日涨跌。<br>
<b>8.1 起的增减持已完整收录</b>（08-01/08-02 为周末无变动披露，最早一笔自 08-03 起）；如需查询更早，需补一次更早的快照。
</div>

<div class='section'>
  <h2>概览</h2>
  <div class='idxrow'>
    <div class='idx'><div class='k'>增持记录</div><div class='v buy'>{len(buy)}</div>
      <div class='hl'>合计 {wan(buy_amt)} 万元</div></div>
    <div class='idx'><div class='k'>减持记录</div><div class='v sell'>{len(sell)}</div>
      <div class='hl'>合计 {wan(sell_amt)} 万元</div></div>
    <div class='idx'><div class='k'>净变动金额</div><div class='v {net_cls}'>{wan(net)}</div>
      <div class='hl'>{net_txt}（万元）</div></div>
    <div class='idx'><div class='k'>涉及股票</div><div class='v'>{d['stockCount']}</div>
      <div class='hl'>只</div></div>
    <div class='idx'><div class='k'>变动金额合计</div><div class='v'>{wan(buy_amt+sell_amt)}</div>
      <div class='hl'>万元（增减持绝对值之和）</div></div>
  </div>
  <div class='note'>减持笔数占比 <b>{len(sell)/max(1,len(recs))*100:.1f}%</b>、
减持金额占比 <b>{sell_amt/max(1e-9,(buy_amt+sell_amt))*100:.1f}%</b>。
净额为负表示近一月董监高整体呈净卖出。</div>
</div>

<div class='section'>
  <h2>行业分布（申万一级 · 按增减持金额合计）</h2>
  <div class='chiprow'>
    <div class='chip chip-ind chip-all' data-industry='__all__' onclick='clearIndustry()' title='清除行业筛选'>
      <div class='ck'>全部行业</div>
      <div class='cv' style='font-size:13px'>{len(set(r.get('sw1') or '其他' for r in recs))} 个</div>
      <div class='cs'><span style='color:#8a929c'>点击重置</span></div>
    </div>
    {chips}
  </div>
  <div class='note'>每格：行业 ｜ 增减持金额合计（万元）｜ <span class='buy'>增持</span> / <span class='sell'>减持</span> 分项（万元）。
  <b>点击任一行业卡片</b>可仅看该行业记录；点「全部行业」或再次点击同一卡片可重置。仅列金额合计最高的 18 个行业。</div>
</div>

<div class='section'>
  <h2>明细</h2>
  <div class='tabs'>
    <div class='tab' data-tab='p_latest' onclick='switchTab("p_latest")'>最新披露日（{fmt_date(latest)} · {len(latest_recs)} 条）</div>
    <div class='tab' data-tab='p_buy' onclick='switchTab("p_buy")'>增持榜 Top60</div>
    <div class='tab' data-tab='p_sell' onclick='switchTab("p_sell")'>减持榜 Top60</div>
    <div class='tab' data-tab='p_agg' onclick='switchTab("p_agg")'>个股聚合 Top80</div>
    <div class='tab' data-tab='p_all' onclick='switchTab("p_all")'>全部明细（{len(recs)} 条）</div>
  </div>
  <div class='filters'>
    <span class='lb'>方向筛选：</span>
    <div class='tab fbtn' data-dir='all' onclick='setDir("all")'>全部</div>
    <div class='tab fbtn' data-dir='b' onclick='setDir("b")'>仅增持</div>
    <div class='tab fbtn' data-dir='s' onclick='setDir("s")'>仅减持</div>
  </div>

  <div class='pane' id='p_latest'><div class='scroll'><table>
    <thead><tr>{base_th}</tr></thead><tbody>{t_latest}</tbody></table></div></div>

  <div class='pane hide' id='p_buy'><div class='scroll'><table>
    <thead><tr>{base_th}</tr></thead><tbody>{t_buy}</tbody></table></div></div>

  <div class='pane hide' id='p_sell'><div class='scroll'><table>
    <thead><tr>{base_th}</tr></thead><tbody>{t_sell}</tbody></table></div></div>

  <div class='pane hide' id='p_agg'><div class='scroll'><table>
    <thead><tr><th>股票</th><th>代码</th><th>申万一级</th><th>申万二级</th>
    <th class='num'>变动笔数</th><th class='num'>增持</th><th class='num'>减持</th>
    <th class='num'>净变动金额(万元)</th><th>最近披露日</th><th class='num'>当日涨跌</th></tr></thead>
    <tbody>{t_agg}</tbody></table></div>
    <div class='note'>净变动金额 = Σ(变动股数 × 成交均价)，正=净增持、负=净减持；按净额从高到低排序。</div></div>

  <div class='pane hide' id='p_all'><div class='scroll'><table>
    <thead><tr>{base_th}</tr></thead><tbody>{t_all}</tbody></table></div></div>
</div>

<footer>
数据来源：腾讯自选股 <b>westock-mcp</b>（上市公司公开披露的董监高持股变动，盘后数据、存在披露滞后）。<br>
本页面由 A股量化助理自动生成 · 仅供参考，<b>不构成投资建议</b> · 市场有风险，投资需谨慎。
</footer>
</div>
<script>{JS}</script>
</body>
</html>
"""

    os.makedirs(WEB, exist_ok=True)
    dst = os.path.join(WEB, "exec.html")
    with open(dst, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"OK -> {dst}")
    print(f"    记录 {len(recs)}（增持 {len(buy)} / 减持 {len(sell)}）｜股票 {d['stockCount']} 只｜净额 {wan(net)} 万元")

    # ---- 幂等注入导航：龙虎榜索引页加入口（build_dashboards 重建后重跑本脚本即可补回）----
    idx = os.path.join(WEB, "index.html")
    if os.path.exists(idx):
        s = open(idx, encoding="utf-8").read()
        if "exec.html" not in s:
            anchor = "← 返回 A股分析中心总门户</a>"
            if anchor in s:
                s = s.replace(anchor, anchor + "\n<a href='exec.html'>高管增减持</a>", 1)
                with open(idx, "w", encoding="utf-8") as f:
                    f.write(s)
                print("    导航注入 -> web/index.html（高管增减持）")
            else:
                print("    ⚠ web/index.html 未找到导航锚点，跳过注入")
        else:
            print("    导航已存在，跳过注入")


if __name__ == "__main__":
    main()
