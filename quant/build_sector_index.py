#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
生成「A股板块强度」首页索引: 汇总所有每日页入口 + 趋势看板。

用法:
  python build_sector_index.py --trend quant/sector_trend.json --output ../web/sector-strength-index.html
"""
import argparse, json, os, glob

ROOT = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.normpath(os.path.join(ROOT, "..", "web"))


def build_html(trend):
    trend_sorted = sorted(trend, key=lambda t: t["date"], reverse=True)
    latest = trend_sorted[0] if trend_sorted else None
    cards = []
    for t in trend_sorted:
        d = t["date"]
        href = f"sector-strength-{d.replace('-','')}.html"
        dark = t["totalDarkY"]
        dcls = "up" if dark >= 0 else "down"
        sign = "+" if dark >= 0 else ""
        beh = t
        cards.append(f"""
        <a class="day" href="{href}">
          <div class="d-date">{d}</div>
          <div class="d-row"><span>板块</span><b>{t['sectorCount']}</b></div>
          <div class="d-row"><span>暗盘净额</span><b class="{dcls}">{sign}{dark:.1f}亿</b></div>
          <div class="d-row"><span>均强</span><b>{t['avgStrength']}</b></div>
          <div class="d-beh"><span class="bq">抢{beh['qiangchou']}</span><span class="bj">建{beh['jiancang']}</span><span class="bx">洗{beh['xipan']}</span><span class="bc">出{beh['chuhuo']}</span></div>
          <div class="d-go">查看明细 →</div>
        </a>""")

    html = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>A股板块强度 · 首页</title>
<style>
:root{--bg:#0b0f17;--panel:#121826;--panel2:#0e1420;--line:#1f2937;--txt:#e6edf3;
  --mut:#8b98a9;--up:#e0483b;--down:#1a9e5a;--gold:#e8b339;--qc:#e0483b;--ch:#1a9e5a;--jc:#e8b339;--xp:#5b8def}
*{box-sizing:border-box}
body{margin:0;background:linear-gradient(180deg,#0b0f17,#0a0d14);color:var(--txt);
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;
  font-size:13px;padding:26px 30px 60px}
h1{font-size:23px;margin:0 0 2px;letter-spacing:.5px}
.sub{color:var(--mut);font-size:12px;margin-bottom:22px}
.up{color:var(--up)}.down{color:var(--down)}
.hero{display:grid;grid-template-columns:1.3fr 1fr;gap:16px;margin-bottom:22px}
.big{background:linear-gradient(135deg,#161d2b,#10161f);border:1px solid var(--line);border-radius:14px;padding:20px;position:relative;overflow:hidden;text-decoration:none;color:var(--txt)}
.big:before{content:"";position:absolute;right:-30px;top:-30px;width:160px;height:160px;border-radius:50%;background:radial-gradient(circle,rgba(232,179,57,.22),transparent 70%)}
.big .tag{color:var(--gold);font-size:12px;letter-spacing:1px}
.big h2{margin:8px 0 4px;font-size:19px}
.big p{color:var(--mut);font-size:12px;margin:6px 0 0;line-height:1.6}
.big .go{display:inline-block;margin-top:14px;background:var(--gold);color:#1a1300;font-weight:700;padding:8px 16px;border-radius:8px;font-size:13px}
.latest .lv{font-size:30px;font-weight:800;margin-top:6px}
.latest .ls{color:var(--mut);font-size:12px;margin-top:2px}
.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}
.day{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:13px 14px;text-decoration:none;color:var(--txt);transition:.15s;display:flex;flex-direction:column}
.day:hover{border-color:var(--gold);transform:translateY(-2px)}
.d-date{font-size:14px;font-weight:700;color:var(--gold);margin-bottom:8px}
.d-row{display:flex;justify-content:space-between;font-size:12px;color:var(--mut);padding:3px 0}
.d-row b{color:var(--txt);font-variant-numeric:tabular-nums}
.d-beh{display:flex;gap:5px;margin:8px 0 4px;font-size:10.5px}
.d-beh span{padding:2px 6px;border-radius:5px}
.bq{background:rgba(224,72,59,.16);color:var(--qc)}.bj{background:rgba(232,179,57,.16);color:var(--jc)}
.bx{background:rgba(91,141,239,.16);color:var(--xp)}.bc{background:rgba(26,158,90,.16);color:var(--ch)}
.d-go{margin-top:auto;color:var(--mut);font-size:11px;padding-top:8px}
.sectit{color:var(--gold);font-size:13px;margin:24px 0 12px;font-weight:600;letter-spacing:.5px}
.note{color:var(--mut);font-size:11px;margin-top:22px;line-height:1.7}
@media(max-width:1100px){.hero{grid-template-columns:1fr}.grid{grid-template-columns:repeat(2,1fr)}}
</style>
</head>
<body>
<h1>A股板块强度 <span style="color:var(--gold)">看板中心</span></h1>
<div class="sub">暗盘资金 = 主力 − 散户 ｜ 板块强度 = 暗盘 ÷ 总成交额 × 100 ｜ 每日盘后真实快照累积</div>
<div class="hero">
  <a class="big" href="sector-strength-trend.html">
    <div class="tag">趋势</div>
    <h2>趋势看板（日 / 周 / 月）</h2>
    <p>全市场暗盘资金净额、平均强度、上涨占比、抢筹/出货板块数随交易日演变；叠加主力行为分布堆叠图。数据自动累积、曲线随交易日延长。</p>
    <span class="go">打开趋势看板 →</span>
  </a>
  """ + (f"""
  <a class="big latest" href="sector-strength-{latest['date'].replace('-','')}.html">
    <div class="tag">最新 · {latest['date']}</div>
    <h2>最新一日板块强度</h2>
    <div class="lv {'up' if latest['totalDarkY']>=0 else 'down'}">{('+' if latest['totalDarkY']>=0 else '')}{latest['totalDarkY']:.1f}<span style="font-size:14px;color:var(--mut)">亿</span></div>
    <div class="ls">全市场暗盘资金净额 ｜ 均强 {latest['avgStrength']} ｜ 涨 {latest['upRatio']}%</div>
    <span class="go">查看 {latest['date']} 明细 →</span>
  </a>""" if latest else "") + """
</div>
<div class="sectit">每日板块强度页（点击查看当日完整明细）</div>
<div class="grid">""" + "\n".join(cards) + """</div>
<div class="note">说明: 因 westock 板块接口 <code>date</code> 参数被忽略、仅返回最新快照，历史某日真实数据无法回溯；本看板按"每日拉取日期"真实累积，
未来每个交易日运行自动化后将自动新增一页并在此列出。当前共 """ + str(len(trend_sorted)) + """ 个数据点。</div>
</body>
</html>"""
    return html


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trend", required=True)
    ap.add_argument("--output", default=None)
    args = ap.parse_args()
    trend = json.load(open(args.trend, encoding="utf-8"))
    out = args.output or os.path.join(WEB, "sector-strength-index.html")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    open(out, "w", encoding="utf-8").write(build_html(trend))
    print(f"[ok] 首页索引 -> {out} ({len(trend)} 个每日入口)")


if __name__ == "__main__":
    main()
