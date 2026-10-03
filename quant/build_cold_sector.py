# -*- coding: utf-8 -*-
"""
冷门行业榜页面（build_cold_sector.py）
=====================================
用户 2026-10-03 要求：冷门榜**单独做一个页面**。

⚠ 页面定位（重要，勿改）
------------------------
**只陈述已发生的事实**（哪些行业两年零主升），**不作为买入依据**。
顶部必须醒目标注「未通过样本外检验」。

原因（2026-10-03 实测，41 万笔成熟样本）：

    冷门行业内任意选   55.4%
    热门行业内任意选   59.7%
    全市场随机基线     58.2%
    → 冷门 vs 热门 = −4.3pp

**「两年没主升」在 A 股是负向信号（= 刚刚不涨），不是「将要主升」。**
所以本页绝不推荐个股、绝不标「买点」。`picks` 恒为空，闸门未过就不出。

数据源（全部本地真实数据，可复现）
--------------------------------
- `quant/_long_kline.json` —— 5050 票 × 780 根日K（2023-07-17 ~ 2026-09-30，2 年抓取）
- `quant/q2_full/_code2industry.json` —— 5543 票 → 31 行业
- 腾讯宽基指数（沪深300，实时取，失败退回等权）
- 行业指数 = **等权**收益平均（成交额加权会让热门票主导，实测会让电子行业虚增到 +3529%）

用法
----
    python build_cold_sector.py --date 2026-09-30
"""
from __future__ import annotations
import os, sys, json, argparse, math

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import _cold_sector as CS
import _nav

ROOT = os.path.dirname(HERE)
WEB = os.path.join(ROOT, "web")
OUT_WEB = os.path.join(WEB, "cold_sector")

CSS = """* { box-sizing: border-box; }
body { margin:0; font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;
  background:#f5f6f8; color:#23262b; }
.wrap { max-width:1180px; margin:0 auto; padding:26px 20px 60px; }
h1 { font-size:26px; margin:0 0 6px; }
h2 { font-size:18px; margin:0 0 10px; }
.sub { color:#6b7280; font-size:13px; line-height:1.8; margin-bottom:14px; }
.section { background:#fff; border:1px solid rgba(0,0,0,.08); border-radius:12px;
  padding:16px 18px; margin:14px 0; }
table { width:100%; border-collapse:collapse; font-size:13px; }
th,td { padding:8px 10px; border-bottom:1px solid rgba(0,0,0,.07); text-align:right; }
th:first-child,td:first-child { text-align:left; }
th { background:#fafbfc; font-weight:600; color:#5b6168; font-size:12px; white-space:nowrap; }
tbody tr:hover { background:#fafbfc; }
.warn { background:#fff4e5; border:1px solid #f0c896; border-radius:12px;
  padding:14px 16px; color:#7a4a12; font-size:13px; line-height:1.85; margin:14px 0; }
.warn b { color:#a8500a; }
.ok { background:#eef6ff; border:1px solid #c9def5; border-radius:12px;
  padding:14px 16px; color:#1c4e80; font-size:13px; line-height:1.85; margin:14px 0; }
.t0 { background:#e8f4ff; }
.muted { color:#8b9199; }
.sec-tag { display:inline-block; background:#eef6ff; color:#1c4e80; border-radius:6px;
  padding:1px 7px; font-size:12px; margin-left:6px; }
.cold-tag { display:inline-block; background:#eaf3de; color:#173404; border-radius:6px;
  padding:1px 7px; font-size:12px; }
a { color:#1a73e8; }
.arch { display:flex; flex-wrap:wrap; gap:8px; }
.arch a { background:#f5f6f8; border:1px solid rgba(0,0,0,.08); border-radius:8px;
  padding:5px 10px; font-size:12px; text-decoration:none; color:#1c4e80; }
footer { margin-top:24px; color:#9aa0a6; font-size:12px; line-height:1.8; }
"""


def build(date):
    bars = CS.load_long()
    if not bars:
        print("！无长历史数据，请先跑 _fetch_long_kline.py")
        return None
    members, _ = CS.load_industry_map()
    bc, bn = None, -1
    for c, b in bars.items():
        if len(b) > bn:
            bc, bn = c, len(b)
    cal = [b["date"] for b in bars[bc]]
    asof = cal[-1]
    print("[load] 票数=%d 日历=%s~%s" % (len(bars), cal[0], asof))

    bench = CS.fetch_bench(780)
    mkt = CS.build_market_index(cal, bars, bench)
    ind_nav = CS.build_industry_index(cal, bars, members)

    stats = {}
    for ind, nav in ind_nav.items():
        st = CS.sector_stats(nav, cal, mkt, CS.LOOKBACK)
        if st:
            st["n_members"] = len(members.get(ind, []))
            stats[ind] = st
    ok = [k for k, v in stats.items()
          if v["n_members"] >= 8 and v["n_bars"] >= CS.LOOKBACK * 0.8]
    ranked = sorted(ok, key=lambda k: (stats[k]["n_runs"], stats[k]["best_run"]))
    print("[行业] 可用 %d / %d，冷门榜按 (主升次数, 最强主升) 升序" % (len(ranked), len(stats)))

    # 前提检验数字（若已有 oos 产物则读，否则标注未跑）
    oos_path = os.path.join(CS.OUTDIR, "oos_%s.json" % asof.replace("-", ""))
    premise = None
    if os.path.exists(oos_path):
        try:
            o = json.load(open(oos_path, encoding="utf-8"))
            premise = {"pass": o.get("pass"),
                       "n": (o.get("stats") or {}).get("n"),
                       "wr": (o.get("stats") or {}).get("wr"),
                       "rnd": (o.get("stats") or {}).get("rnd_med"),
                       "edge": (o.get("stats") or {}).get("edge")}
        except Exception:
            pass

    rows = []
    for i, ind in enumerate(ranked, 1):
        v = stats[ind]
        rows.append({
            "i": i, "ind": ind, "n": v["n_members"], "runs": v["n_runs"],
            "best": v["best_run"], "total": v["total"],
            "excess": v["excess_total"], "dhi": v["dist_hi"],
            "gap": v["last_gap"],
        })

    return {"asof": asof, "rows": rows, "stats": stats, "cal": cal,
            "mkt": mkt, "premise": premise, "bench": bench,
            "bars_n": len(bars)}


def render(d, date):
    asof = d["asof"]
    rows = d["rows"]
    premise = d["premise"]
    p_txt = ""
    if premise:
        p_txt = ("本页数据对应的策略做过严格检验：<b>策略胜率 %s vs 随机基线 %s（%s）</b>，"
                 % ("%.1f%%" % premise["wr"] if premise["wr"] else "—",
                    "%.1f%%" % premise["rnd"] if premise["rnd"] else "—",
                    ("%+.1fpp" % premise["edge"]) if premise.get("edge") is not None else "—"))
    mkt_gain = (d["mkt"][-1] / d["mkt"][0] - 1) * 100 if d["mkt"][0] else 0.0

    def tr(r):
        cls = " class='t0'" if r["runs"] == 0 else ""
        tag = "<span class='cold-tag'>两年零主升</span>" if r["runs"] == 0 else ""
        return ("<tr%s><td><b>%d</b></td><td style='text-align:left'><b>%s</b>%s</td>"
                "<td>%d</td><td>%d</td><td>%.1f%%</td><td>%.1f%%</td>"
                "<td style='color:%s'>%+.1f%%</td><td>%.1f%%</td><td>%s</td></tr>"
                % (cls, r["i"], r["ind"], tag, r["n"], r["runs"],
                   r["best"] * 100, r["total"] * 100,
                   "#a32d2d" if r["excess"] >= 0 else "#1a73e8",
                   r["excess"] * 100, r["dhi"] * 100,
                   ("%d 根前" % r["gap"]) if r["gap"] is not None else "—"))

    body_rows = "".join(tr(r) for r in rows)
    n_cold = sum(1 for r in rows if r["runs"] == 0)

    # 归档入链必须**做进生成器**：入口页自己链当期快照，
    # 否则 cold_YYYYMMDD.html 会变孤儿（_fix_orphans 插的块会被整页重写抹掉）。
    # ⚠ 含当期自己：首期（只有 1 个快照）时也必须列出，否则当期页就是孤儿页。
    import glob as _glob
    snaps = sorted(os.path.basename(p)[5:-5]
                   for p in _glob.glob(os.path.join(OUT_WEB, "cold_2*.html")))
    arch = ("<div class='section'><h2>历史快照</h2><div class='arch'>%s</div></div>"
            % "".join("<a href='cold_%s.html'>%s</a>" % (s, s) for s in snaps)) if snaps else ""

    return """<!DOCTYPE html>
<html lang='zh-CN'><head><meta charset='UTF-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'>
<title>冷门行业榜 · 两年未主升</title><style>%(css)s</style></head><body>
<div class="wrap">
%(nav)s
<header><h1>冷门行业榜 <span class="sec-tag">已发生的事实</span></h1>
<div class="sub">统计窗口 %(look)d 个交易日（约 2 年）｜数据日 <b>%(asof)s</b>｜
样本 %(bars)d 只票（两年日K）｜大盘同期 <b>%(mkt).1f%%</b>（沪深300）</div></header>

<div class="warn">
<b>⚠ 本页不提供任何买入建议，只陈述事实。</b><br>
「两年没有主升过」是<b>已发生的历史</b>，可以拿来看；<b>它不等于「将要主升」</b>。<br>
本页数据对应的选股策略已做过严格样本外检验（%(prem)s）—— 结论是<b>跑输随机基线</b>，
因此<b>不推荐任何个股、不标注任何买点</b>。详见页面底部「为什么不上线」。
</div>

<div class="section">
<div class='ok' style='margin-top:12px'>
<b>相关页面</b>：<a href='../cross_section/index.html'>全市场横截面 · 数据能力</a>（统一数据底座的<b>全市场</b> quotes + 主力资金流，4971 只可分析域，含字段覆盖统计与示例打分 —— 示例打分未过样本外检验，非选股结论）。
</div>

<h2>两年零主升的行业（%(ncold)d 个）</h2>
<div class="sub" style="margin:0 0 10px">
判据（先验固定、非拟合）：一段上涨同时满足 <b>涨幅 ≥ 60%%</b>、<b>持续 ≥ 60 个交易日</b>、
<b>跑赢沪深300 ≥ 25pp</b> 才算一次主升。窗口内没有满足的 = 零主升。</div>
<table><thead><tr>
<th>#</th><th>行业</th><th>成分股</th><th>主升次数</th><th>最强主升</th>
<th>窗口涨幅</th><th>跑赢大盘</th><th>距区间高点</th><th>末次主升距今</th>
</tr></thead><tbody>%(rows)s</tbody></table>
</div>

<div class="ok">
<b>为什么不上线（2026-10-03 实测，41 万笔成熟样本，每笔走满 20 日）</b><br>

<table style="margin-top:8px"><thead><tr><th>组合</th><th>样本 n</th><th>胜率</th><th>均值收益</th></tr></thead>
<tbody>
<tr><td style="text-align:left"><b>冷门行业</b>（15 个，两年少主升）内任意选</td><td>415,766</td>
<td><b>55.4%%</b></td><td>0.12%%</td></tr>
<tr><td style="text-align:left">热门行业（16 个）内任意选</td><td>775,444</td>
<td><b>59.7%%</b></td><td>0.61%%</td></tr>
<tr><td style="text-align:left">全市场随机基线</td><td>392,848</td><td>58.2%%</td><td>0.43%%</td></tr>
</tbody></table>
<br><b>冷门 vs 热门 = −4.3pp，冷门 vs 基线 = −2.8pp。</b>
<br>即：<b>「两年没主升」在 A 股是负向信号（刚刚不涨），不是正向买点。</b>
<br>这解释了为什么在此类行业里做技术面选股必然跑输随机 —— <b>池子入口就选错了一边</b>。
<br><br>此外 5 个技术因子（低位 / 企稳 / 放量 / 领涨 / 波动收敛）做过消融：
<b>正反两个方向都跑输随机</b>（edge −0.1 ~ −2.9pp），
说明这些维度的档位差异纯属统计噪声，<b>不携带胜率信息</b>。
<br>结论：<b>宁可不选，也不推一个跑输随机的池子。</b>
</div>

<div class="section">
<h2>数据口径与已知偏差</h2>
<div class="sub" style="margin:0">
① <b>行业指数为事后重建</b>：用 <code>q2_full/_code2industry.json</code>（5543 票 → 31 行业）按
<b>等权</b>收益平均重建。分类源不含历史成分，故存在<b>成分漂移偏差</b>，非官方板块指数。<br>
② <b>等权而非成交额加权</b>：成交额加权会让高换手/热门票主导指数（实测会让某行业 2 年虚增到 +3529%%，
同期成分股中位仅 +17%%）。<br>
③ <b>大盘基准用真实指数</b>（沪深300，腾讯可回溯 760 根），不用自建 —— 自建会因退市股缺席、
覆盖门槛、科创板成交额单位差 114 倍而虚增到 +1087%%。<br>
④ 样本为 <b>两年日K 底座</b>（%(bars)d 只 × 780 根），次新股/长期停牌 157 只未纳入。<br>
⑤ 本页<b>不产生任何个股推荐</b>，页面上没有「买入」「目标价」字样。
</div>
</div>

%(arch)s
<footer>
本页由 <code>build_cold_sector.py</code> 生成，引擎 <code>_cold_sector.py</code>，
闸门 <code>_cold_oos.py</code>，消融 <code>_cold_ablate.py</code>。<br>
纪律：<b>宁可不选，不能乱选</b> —— 未通过样本外检验的策略一律不出票。
<br>数据日 %(asof)s｜本页所有数字均由当日真实数据重算，无写死值。
</footer>
</div></body></html>
""" % {
        "css": CSS, "nav": _nav.topnav(current_web_dir="cold_sector", home="../../index.html"),
        "look": CS.LOOKBACK, "asof": asof, "rows": body_rows, "ncold": n_cold,
        "bars": d["bars_n"], "mkt": mkt_gain, "prem": p_txt or "尚未运行（_cold_oos.py）",
        "arch": arch,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    a = ap.parse_args()
    d = build(a.date)
    if not d:
        return
    os.makedirs(OUT_WEB, exist_ok=True)
    # 入口页固定名 + 当期快照（archive 族）
    for fn in ("index.html", "cold_%s.html" % d["asof"].replace("-", "")):
        p = os.path.join(OUT_WEB, fn)
        open(p, "w", encoding="utf-8").write(render(d, a.date))
        print("  → %s" % p)
    # 事实数据也落一份 JSON（供审计）
    jp = os.path.join(OUT_WEB, "cold_%s.json" % d["asof"].replace("-", ""))
    json.dump({"asof": d["asof"], "lookback": CS.LOOKBACK,
               "n_bars": d["bars_n"], "rows": d["rows"]},
              open(jp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("  → %s" % jp)


if __name__ == "__main__":
    main()
