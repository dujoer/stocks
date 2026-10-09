#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
生成「A股板块强度 · 看板中心」首页 (web/sector/index.html):

  - 顶部统一导航 (topnav)
  - header + datebadge + meta
  - 概览区 (idxrow: 全市场暗盘净额累计 / 总数据点 / 主力抢筹板块数累计 /
                       主力出货板块数累计 / 最新一日均强 / 最新一日上涨占比 / 趋势看板入口)
  - 每日板块强度归档表格 (可点表头排序: 日期/板块数/暗盘净额/均强/涨占比/抢/建/洗/出)
  - footer 免责

设计语言与全站统一 (block/archive.html、market/exec/block/exec index 等共用同一套
.wrap + .topnav + .section + .idxrow + table 模板)。

用法:
  python build_sector_index.py --trend quant/sector_trend.json
                              [--output web/sector/index.html]
"""
import argparse, json, os
from _nav import topnav

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
Q = os.path.join(ROOT, "quant")
WEB = os.path.join(ROOT, "web")
WEB_SECTOR = os.path.join(WEB, "sector")

# 全站统一 CSS: 与 build_block.py / market / exec / block 一致
CSS = """* { box-sizing: border-box; }
body { margin:0; font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;
  background:#f5f6f8; color:#23262b; min-height:100vh; }
.wrap { max-width:1180px; margin:0 auto; padding:40px 20px 60px; }
.topnav { display:flex; flex-wrap:wrap; gap:8px; margin-bottom:22px; padding-bottom:14px;
  border-bottom:1px solid rgba(0,0,0,.08); }
.topnav a { color:#b8893b; text-decoration:none; font-size:13px; padding:4px 12px; border-radius:20px;
  border:1px solid rgba(184,137,59,.35); transition:.2s; }
.topnav a:hover { background:rgba(184,137,59,.10); }
.topnav a.cur { background:#b8893b; color:#fff; border-color:#b8893b; }
header { display:flex; align-items:flex-end; justify-content:space-between; flex-wrap:wrap; gap:12px; }
header h1 { font-size:30px; margin:0 0 6px; background:linear-gradient(90deg,#b8893b,#b8332a,#6b5b95);
  -webkit-background-clip:text; background-clip:text; color:transparent; font-weight:800; }
header p { margin:4px 0; color:#8a929c; font-size:13px; line-height:1.6; }
.datebadge { display:inline-block; font-size:22px; font-weight:800; color:#fff;
  background:linear-gradient(135deg,#b8893b,#b8332a); padding:10px 20px; border-radius:14px;
  letter-spacing:.5px; box-shadow:0 6px 18px rgba(184,137,59,.25); white-space:nowrap; }
.datebadge small { display:block; font-size:11px; font-weight:600; opacity:.85; letter-spacing:1px; }
.meta { margin:14px 0 24px; font-size:12px; color:#6b7280; line-height:1.7; }
.meta b { color:#b8893b; }
.section { background:#ffffff; border:1px solid rgba(0,0,0,.08); border-radius:20px;
  padding:18px 20px; margin:0 0 22px; }
.section h2 { font-size:19px; margin:0 0 14px; padding-left:12px; border-left:5px solid #b8893b; }
.idxrow { display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:14px; }
.idx { background:#fafbfc; border:1px solid #eef1f4; border-radius:14px; padding:14px 16px; }
.idx .k { font-size:12px; color:#7b8794; }
.idx .v { font-size:24px; font-weight:800; margin-top:4px; color:#23262b; }
.idx .v.up { color:#b8332a; } .idx .v.down { color:#1a9e5a; } .idx .v.gold { color:#b8893b; }
.idx a { color:#23262b; text-decoration:none; display:block; }
.idx a:hover .v { color:#b8893b; }
table { width:100%; border-collapse:collapse; font-size:13px; }
th { text-align:left; padding:9px 10px; background:#f7f8fa; color:#5a6573; font-weight:700;
  border-bottom:2px solid #e3e7ec; white-space:nowrap; }
td { padding:9px 10px; border-bottom:1px solid #f0f2f5; }
tr:hover td { background:#fcfbf8; }
.num { text-align:right; font-variant-numeric:tabular-nums; white-space:nowrap; }
.up { color:#b8332a; font-weight:700; } .down { color:#1a9e5a; font-weight:700; } .flat { color:#8a929c; }
.beh-qiang { color:#b8332a; font-weight:700; }
.beh-jian  { color:#b8893b; font-weight:700; }
.beh-xi    { color:#3b6fd1; font-weight:700; }
.beh-chu   { color:#1a9e5a; font-weight:700; }
.empty { padding:8px; color:#9aa2ad; font-size:12px; }
footer { margin-top:40px; padding-top:18px; border-top:1px solid #e3e7ec;
  font-size:12px; color:#7b8794; line-height:1.8; }
th.sort { cursor:pointer; user-select:none; position:relative; }
th.sort:hover { background:#eef0f3; color:#3b4453; }
th.sort.sorted { color:#b8893b; }
th.sort.sorted[data-asc="1"]::after { content:" \\25B2"; font-size:10px; }
th.sort.sorted[data-asc="0"]::after { content:" \\25BC"; font-size:10px; }
th.sort:not(.sorted)::after { content:" \\2195"; font-size:10px; color:#c2c9d1; }
.gapbox { border-left-color:#d9a441; }
.gapbox h2 { border-left-color:#d9a441; }
.gapbox p { font-size:13px; color:#41474f; line-height:1.9; margin:0; }
.gapbox ul { margin:8px 0 6px; padding-left:20px; font-size:13px; color:#41474f; line-height:1.95; }
.gapbox li b { color:#b8332a; }
.gapbox .muted { color:#8a929c; font-size:12px; margin-top:8px; }
.tag-src { display:inline-block; font-size:10.5px; padding:1px 6px; border-radius:9px;
  background:#fdf3e3; color:#a9761f; border:1px solid #efdfc0; margin-left:5px; white-space:nowrap; }
"""

SORT_JS = """function sortTable(id, th){
  var table=document.getElementById(id);
  var tbody=table.tBodies[0];
  var rows=Array.prototype.slice.call(tbody.rows);
  var idx=parseInt(th.getAttribute('data-c'),10);
  var asc=th.getAttribute('data-asc')!=='1';
  rows.sort(function(a,b){
    var x=a.cells[idx].getAttribute('data-val');
    var y=b.cells[idx].getAttribute('data-val');
    var nx=parseFloat(x), ny=parseFloat(y);
    if(!isNaN(nx)&&!isNaN(ny)){ return asc?nx-ny:ny-nx; }
    x=(x==null?'':x); y=(y==null?'':y);
    return asc?(x<y?-1:(x>y?1:0)):(x<y?1:(x>y?-1:0));
  });
  for(var i=0;i<rows.length;i++) tbody.appendChild(rows[i]);
  var ths=table.querySelectorAll('th.sort');
  for(var k=0;k<ths.length;k++){ ths[k].removeAttribute('data-asc'); ths[k].classList.remove('sorted'); }
  th.setAttribute('data-asc', asc?'1':'0');
  th.classList.add('sorted');
}
document.querySelectorAll('th.sort').forEach(function(t){
  t.addEventListener('click',function(){ sortTable(t.parentNode.parentNode.parentNode.id, t); });
});
"""


def fmt_dark(v):
    sign = "+" if v >= 0 else ""
    cls = "up" if v >= 0 else "down"
    return f"<span class='{cls}'>{sign}{v:.1f}亿</span>"


def build_html(trend):
    trend_sorted = sorted(trend, key=lambda t: t["date"], reverse=True)
    total = len(trend_sorted)
    latest = trend_sorted[0] if trend_sorted else None

    # 累计统计
    dark_sum = sum(t["totalDarkY"] for t in trend_sorted)
    qiang_sum = sum(t["qiangchou"] for t in trend_sorted)
    chu_sum = sum(t["chuhuo"] for t in trend_sorted)
    sector_avg = round(sum(t["sectorCount"] for t in trend_sorted) / max(total, 1))

    NAV = topnav("sector")
    # 当前页面高亮: 板块强度 → sector/index.html
    NAV = NAV.replace(
        "<a href='index.html'>板块强度</a>",
        "<a href='index.html' class='cur'>板块强度</a>",
        1,
    )

    if latest:
        last_date = latest["date"]
        last_dark_sign = "+" if latest["totalDarkY"] >= 0 else ""
        last_dark_cls = "up" if latest["totalDarkY"] >= 0 else "down"
        latest_strength = latest["avgStrength"]
        latest_upratio = latest["upRatio"]
    else:
        last_date = last_dark_sign = last_dark_cls = ""
        latest_strength = latest_upratio = 0
        latest = {"date": "—", "totalDarkY": 0}

    # ── 数据完整性说明：把「静默缺口」显式化（同源不可回补，一律如实列出）──────
    # 交易日历取单一真源 _coverage_check.trade_days_from_data（同一份 web/data 日K 日期列），
    # 读不到就退化为「不显示」—— 宁可不显示，也不用另一套口径编一个缺口数出来。
    all_dates = sorted({t["date"] for t in trend_sorted})
    missing_days = []
    if all_dates:
        try:
            import _coverage_check as _cv
            # ★ 传参必须是无横线 DS：trade_days_from_data 内部用 norm_date 后的 8 位串比较，
            #   传带横线的日期会被静默过滤成空集（踩过一次）
            _lo = all_dates[0].replace("-", "")
            _hi = all_dates[-1].replace("-", "")
            _have = {d.replace("-", "") for d in all_dates}
            _td = _cv.trade_days_from_data(_lo, _hi)
            missing_days = sorted("%s-%s-%s" % (d[:4], d[4:6], d[6:8])
                                  for d in _td if d not in _have)
        except Exception as e:
            print("[warn] 交易日历不可用，完整性说明跳过: %s" % str(e)[:70])
    src_days = [t for t in trend_sorted if (t.get("src") or "westock") != "westock"]
    gap_html = ""
    if missing_days or src_days:
        items = []
        for d in missing_days:
            items.append(
                f"<li><b>{d}</b>：当日未落快照（该交易日漏拉）。westock 快照接口 date 参数无效 → "
                f"<b>同源不可回溯</b>；改用其它源补期会引入不同板块划分与资金口径，须<b>单独标注</b>后方可用于衔接。</li>")
        for t in src_days:
            items.append(
                f"<li><b>{t['date']}</b><span class='tag-src'>东财口径补期</span>：该期强度口径与其余期不同"
                f"（东财「主力净流入 ÷ 成交额」 vs 本族「(主力净流入 − 散户净流入) ÷ 成交额」），"
                f"仅供衔接参考，<b>不并入趋势线统计</b>。</li>")
        gap_html = (
            "<div class='section gapbox'>\n"
            "  <h2>数据完整性说明</h2>\n"
            "  <p>本族为 <b>前瞻累积</b>：westock 板块快照接口的 date 参数无效，只能按「当日盘后实拉」逐日固化，"
            "<b>漏跑一天即永久断档</b>。与其它数据源混用会引入不同的板块划分与不同的资金口径，"
            "因此不给缺口静默补数 —— 一律在下方如实列出。</p>\n"
            "  <ul>" + "".join(items) + "</ul>\n"
            f"  <p class='muted'>交易日区间 {all_dates[0]} ~ {all_dates[-1]}：实到 <b>{len(all_dates)}</b> 期 / "
            f"应有 <b>{len(all_dates) + len(missing_days)}</b> 期"
            + (f"，<b>缺 {len(missing_days)} 期</b>" if missing_days else "，无缺口") + "。</p>\n"
            "</div>\n")

    # 表格行: 日期 / 板块数 / 暗盘净额 / 均强 / 涨占比 / 抢 / 建 / 洗 / 出
    rows_html = []
    for t in trend_sorted:
        compact = t["date"].replace("-", "")
        d = t["date"]
        dark = t["totalDarkY"]
        dark_sign = "+" if dark >= 0 else ""
        dark_cls = "up" if dark >= 0 else "down"
        bsrc = ("<span class='tag-src'>东财口径</span>"
                if (t.get("src") or "westock") != "westock" else "")
        rows_html.append(
            "<tr>"
            f"<td data-val='{d}'><a href='sector-strength-{compact}.html' "
            f"style='color:#1f4e79;text-decoration:none;font-weight:700'>{d}</a>{bsrc}</td>"
            f"<td class='num' data-val='{t['sectorCount']}'>{t['sectorCount']}</td>"
            f"<td class='num' data-val='{dark:.2f}'>{dark_sign}{dark:.1f}亿</td>"
            f"<td class='num' data-val='{t['avgStrength']:.3f}'>{t['avgStrength']:.3f}</td>"
            f"<td class='num' data-val='{t['upRatio']:.2f}'>{t['upRatio']:.1f}%</td>"
            f"<td class='num beh-qiang' data-val='{t['qiangchou']}'>{t['qiangchou']}</td>"
            f"<td class='num beh-jian'  data-val='{t['jiancang']}'>{t['jiancang']}</td>"
            f"<td class='num beh-xi'    data-val='{t['xipan']}'>{t['xipan']}</td>"
            f"<td class='num beh-chu'   data-val='{t['chuhuo']}'>{t['chuhuo']}</td>"
            "</tr>"
        )

    html = (
        "<!DOCTYPE html>\n"
        "<html lang='zh-CN'>\n"
        "<head>\n"
        "<meta charset='UTF-8'>\n"
        "<meta name='viewport' content='width=device-width,initial-scale=1.0'>\n"
        f"<title>A股板块强度 · 看板中心</title>\n"
        f"<style>{CSS}</style>\n"
        "</head>\n"
        "<body>\n"
        "<div class='wrap'>\n"
        f"{NAV}\n"
        "<header>\n"
        "  <div>\n"
        "    <h1>📊 板块强度 · 看板中心</h1>\n"
        "    <p>暗盘资金 = 主力净流入 − 散户净流入 ｜ 板块强度 = 暗盘 ÷ 板块总成交额 × 100 ｜ 每日盘后真实快照累积（因 westock 接口 date 无效，按拉取日固化、不回溯不编造）。</p>\n"
        "  </div>\n"
        f"  <div class='datebadge'><small>最新交易日</small>{last_date}</div>\n"
        "</header>\n"
        "<div class='meta'>\n"
        f"最新一日 <b>{last_date}</b> ｜ 全市场暗盘净额 <b>{last_dark_sign}{latest['totalDarkY']:.1f}亿</b> ｜ 均强 <b>{latest_strength:.3f}</b> ｜ 上涨占比 <b>{latest_upratio:.1f}%</b><br>\n"
        f"区间累计：暗盘净额 <b>{('+' if dark_sum>=0 else '')}{dark_sum:.1f}亿</b> ｜ 主力抢筹板块 <b>{qiang_sum}</b> / 出货板块 <b>{chu_sum}</b> ｜ 共 <b>{total}</b> 个数据点。\n"
        "</div>\n"
        "<div class='section'>\n"
        "  <h2>概览</h2>\n"
        "  <div class='idxrow'>\n"
        f"    <div class='idx'><div class='k'>区间累计暗盘净额</div><div class='v {('up' if dark_sum>=0 else 'down')}'>{('+' if dark_sum>=0 else '')}{dark_sum:.1f}<span style='font-size:13px;color:#7b8794'>亿</span></div></div>\n"
        f"    <div class='idx'><div class='k'>数据点（交易日）</div><div class='v gold'>{total}</div></div>\n"
        f"    <div class='idx'><div class='k'>日均板块数</div><div class='v'>{sector_avg}</div></div>\n"
        f"    <div class='idx'><div class='k'>主力抢筹板块（累计）</div><div class='v up'>{qiang_sum}</div></div>\n"
        f"    <div class='idx'><div class='k'>主力出货板块（累计）</div><div class='v down'>{chu_sum}</div></div>\n"
        f"    <div class='idx'><div class='k'>最新一日均强</div><div class='v'>{latest_strength:.3f}</div></div>\n"
        f"    <div class='idx'><div class='k'>最新一日上涨占比</div><div class='v'>{latest_upratio:.1f}%</div></div>\n"
        f"    <div class='idx'><a href='sector-strength-trend.html'><div class='k'>趋势看板（日/周/月）</div><div class='v gold'>{'查看 →'}</div></a></div>\n"
        f"    <div class='idx'><a href='heatmap.html'><div class='k'>板块强度热力图（交互）</div><div class='v gold'>{'🔥 查看 →'}</div></a></div>\n"
        # 冷门行业榜：两年未主升的「已发生事实」，仅陈述不作买卖依据（2026-10-03 新增）
        f"    <div class='idx'><a href='../cold_sector/index.html'><div class='k'>冷门行业榜（两年未主升）</div><div class='v gold'>{'仅事实 →'}</div></a></div>\n"
        "  </div>\n"
        "</div>\n"
        + gap_html +
        "<div class='section'>\n"
        "  <h2>每日板块强度归档（按日期倒序）</h2>\n"
        "  <table id='arch'>\n"
        "    <thead><tr>\n"
        "      <th class='sort' data-c='0'>交易日</th>\n"
        "      <th class='num sort' data-c='1'>板块数</th>\n"
        "      <th class='num sort' data-c='2'>暗盘净额</th>\n"
        "      <th class='num sort' data-c='3'>均强</th>\n"
        "      <th class='num sort' data-c='4'>上涨占比</th>\n"
        "      <th class='num sort' data-c='5'>主力抢筹</th>\n"
        "      <th class='num sort' data-c='6'>主力建仓</th>\n"
        "      <th class='num sort' data-c='7'>主力洗盘</th>\n"
        "      <th class='num sort' data-c='8'>主力出货</th>\n"
        "    </tr></thead>\n"
        f"    <tbody>{''.join(rows_html)}</tbody>\n"
        "  </table>\n"
        "  <div class='empty'>提示：点击表头可排序；点击交易日可进入当日完整明细。</div>\n"
        "</div>\n"
        "<footer>\n"
        "数据来源：腾讯自选股 <b>westock-mcp</b>（盘后公开数据）。<br>\n"
        "本页面由 A股量化助理自动生成 · 仅供参考，<b>不构成投资建议</b> · 市场有风险，投资需谨慎。\n"
        "</footer>\n"
        "</div>\n"
        f"<script>{SORT_JS}</script>\n"
        "</body>\n"
        "</html>"
    )
    return html


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trend", required=True)
    ap.add_argument(
        "--output",
        default=os.path.join(WEB_SECTOR, "index.html"),
        help="首页输出路径（默认 web/sector/index.html）",
    )
    args = ap.parse_args()
    trend = json.load(open(args.trend, encoding="utf-8"))
    out = args.output
    os.makedirs(os.path.dirname(out), exist_ok=True)
    open(out, "w", encoding="utf-8").write(build_html(trend))
    print(f"[ok] 看板中心 -> {out} ({len(trend)} 个每日入口)")


if __name__ == "__main__":
    main()
