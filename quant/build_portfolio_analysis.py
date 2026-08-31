#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""基于 _all_store.json(新持仓) + quotes 生成 web/portfolio_analysis.html（组合分析页）。
风格复用 build_dashboards.py 的 CSS（正则提取，保持统一深色交易终端风）。"""
import json, os, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(ROOT, "web")
QUANT = os.path.join(ROOT, "quant")
DATE = "2026-08-27"          # 行情/涨跌口径（最新交易日）
SNAP_DATE = "2026-08-22"     # 券商导出日

store = json.load(open(os.path.join(ROOT, "deliverables", "trading-agent", "_all_store.json"), encoding="utf-8"))
quotes = json.load(open(os.path.join(QUANT, "quotes", DATE + ".json"), encoding="utf-8"))["data"]

# 复用 build_dashboards.py 的 CSS
src = open(os.path.join(QUANT, "build_dashboards.py"), encoding="utf-8").read()
CSS = re.search(r'^CSS = """(.*?)"""', src, re.S | re.M).group(1)

# 板块归类
COARSE = {
    "003031": "半导体链", "301005": "汽车", "300623": "半导体链", "301308": "半导体链",
    "300458": "半导体链", "600584": "半导体链", "002428": "半导体链", "600737": "农业/食糖",
    "688382": "创新药",
}
FINE = {
    "003031": "半导体材料(电子陶瓷)", "301005": "汽车零部件(紧固件)", "300623": "功率半导体",
    "301308": "存储芯片", "300458": "SoC芯片", "600584": "半导体封测", "002428": "半导体材料(锗)",
    "600737": "农业/食糖", "688382": "创新药",
}

held = [s for s in store["stocks"] if s["held"]]
rows = []
tot_mv = 0.0
tot_pnl = 0.0
tot_day = 0.0
for s in held:
    q = quotes.get(s["market"].lower() + s["code"])
    chg = q["change_percent"] if q else None
    price = q["price"] if q else s["price"]
    mv = s["qty"] * price
    pnl = (price - s["cost"]) * s["qty"]
    pnl_pct = (price - s["cost"]) / s["cost"] * 100
    day_pnl = s["qty"] * price * (chg / 100.0) if chg is not None else 0.0
    tot_mv += mv
    tot_pnl += pnl
    tot_day += day_pnl
    rows.append({
        "name": s["name"], "code": s["code"], "market": s["market"], "qty": s["qty"],
        "cost": s["cost"], "price": price, "chg": chg, "mv": mv, "pnl": pnl,
        "pnl_pct": pnl_pct, "w": 0.0, "day_pnl": day_pnl,
        "hold": int(s.get("hold_days") or 0),
        "coarse": COARSE.get(s["code"], "其他"), "fine": FINE.get(s["code"], ""),
    })
rows.sort(key=lambda x: -x["mv"])
for r in rows:
    r["w"] = r["mv"] / tot_mv * 100 if tot_mv else 0
tot_pnl_pct = tot_pnl / tot_mv * 100 if tot_mv else 0

# 板块集中度
sector_w = {}
for r in rows:
    sector_w[r["coarse"]] = sector_w.get(r["coarse"], 0) + r["w"]
semi_w = sector_w.get("半导体链", 0)
top3 = sorted(rows, key=lambda x: -x["w"])[:3]
top3_w = sum(r["w"] for r in top3)
red_n = sum(1 for r in rows if r["pnl"] < 0)
worst = min(rows, key=lambda x: x["pnl_pct"])

# 估值极端（来自 quotes PE）
pe_map = {k: v.get("pe_ratio") for k, v in quotes.items()}
extreme = [(r["name"], pe_map.get(r["market"].lower() + r["code"])) for r in rows
           if (pe_map.get(r["market"].lower() + r["code"]) or 0) > 100
           or (pe_map.get(r["market"].lower() + r["code"]) or 0) < 0]

PALETTE = ["#c98b7d", "#c9a66b", "#8da894", "#a899b3", "#7fa8c9", "#d6a89d",
           "#9bbf8a", "#c9b07a", "#b08fc9"]

def fnum(x, d=2):
    return f"{x:,.{d}f}"

def pct(x, d=2):
    if x is None:
        return "—"
    return f"{x:+.{d}f}%"

def cls(x):
    if x is None:
        return ""
    return "up" if x >= 0 else "down"

# 持仓明细表
trows = ""
for i, r in enumerate(rows):
    trows += (f"<tr><td><b>{r['name']}</b> <span class='note'>{r['code']}·{r['market']}</span>"
              f"<div class='note'>{r['fine']}</div></td>"
              f"<td class='num'>{fnum(r['qty'],0)}</td>"
              f"<td class='num'>{fnum(r['cost'])}</td>"
              f"<td class='num'>{fnum(r['price'])}</td>"
              f"<td class='num {cls(r['pnl'])}'>{fnum(r['pnl'])}</td>"
              f"<td class='num {cls(r['pnl_pct'])}'>{pct(r['pnl_pct'])}</td>"
              f"<td class='num {cls(r['chg'])}'>{pct(r['chg'])}</td>"
              f"<td class='num'>{fnum(r['w'])}%</td>"
              f"<td class='num'>{r['hold']}</td></tr>")

# 仓位条
bar_seg = ""
for i, r in enumerate(rows):
    c = PALETTE[i % len(PALETTE)]
    bar_seg += f"<div style='width:{r['w']:.2f}%;background:{c}' title='{r['name']} {r['w']:.1f}%'>{r['w']:.1f}%</div>"

# 板块 chips
sec_chips = ""
for k, v in sorted(sector_w.items(), key=lambda x: -x[1]):
    sec_chips += f"<div class='chip'><div class='ck'>{k}</div><div class='cv'>{v:.1f}%</div></div>"

# 风险标记
flags = []
flags.append(f"半导体链单产业链暴露 <b>{semi_w:.1f}%</b>（9 只中 6 只），行业集中度偏高。")
flags.append(f"前三大仓位合计 <b>{top3_w:.1f}%</b>：{ '、'.join(r['name'] for r in top3) }。")
flags.append(f"当前 <b>{red_n}/9</b> 只持仓处于浮动亏损；最大亏损 <b class='down'>{worst['name']} {pct(worst['pnl_pct'])}</b>。")
if extreme:
    ex = "、".join(f"{n}(PE={('亏损' if p<0 else fnum(p,0))})" for n, p in extreme)
    flags.append(f"估值极端标的：{ex} —— 需以「机构主导+量价健康+业绩可验证」规则严格卡控。")
flags_html = "".join(f"<div class='ladder'>⚠️ {f}</div>" for f in flags)

# 换仓对比
compare = ("<div class='amberbox'>"
           "<b>相对上一组合（8.21 旧组合 5 只）：</b>持仓数 5 → 9；清仓 华懋科技、经纬辉开、恒瑞医药；"
           "仅 <b>长电科技、云南锗业</b> 延续；新开 中瓷电子、超捷股份、捷捷微电、江波龙、全志科技、中粮糖业、益方生物（7 只）。"
           "组合市值（持仓股）约 <b>323,432 元</b>，浮动盈亏 <b class='down'>−11.74%</b>，较旧组合 −4.01% 进一步走弱，且换仓后整体未盈利，半导体链普跌是主因。</div>")

# 可执行观察（规则/板块，非直接买卖建议）
obs = [
    "板块节奏：8.20 医药爆发、8.21 医药全线退潮，资金切向贵金属/通信/铜与半导体分化；本组合重仓半导体链（~64%）与当前「科技分化」市况一致，但单一产业链暴露过大，建议单产业链上限 ≤35%。",
    "最强标的：中瓷电子 8.21 涨停 +10%（电子陶瓷/半导体封装材料），属板块内最强，可纳入「强趋势+相对低位+机构主导」观察池。",
    "风险源：超捷股份 −21%（PE≈945，估值极高、疑似追高），建议按「止损/减仓规则」审视；益方生物（创新药、亏损）、云南锗业（PE≈3457）估值极端，不满足「业绩可验证」筛选。",
    "防御回撤：中粮糖业 8.21 −8.14%，与 8.20 粮食防御（金健米业 4 板）逻辑相悖，说明防御板块亦会快速回撤，需配合量价与机构席位验证。",
    "回撤纪律：当前 −11.74% 仍在 15% 容忍度内，但换仓后多数持仓仅 3–5 天（仅长电 10 天），与「中长线」定位有张力；建议对每笔明确「波段/中线」属性并匹配止损。",
]
obs_html = "".join(f"<div class='ladder'>• {o}</div>" for o in obs)

NAV = ("<div class='topnav'>"
       "<a href='index.html'>首页</a>"
       "<a href='daily_overview.html'>每日总览</a>"
       "<a href='portfolio.html'>组合总看板</a>"
       "<a href='portfolio_analysis.html'>组合分析</a>"
       "<a href='lhb.html'>龙虎榜分析</a>"
       "<a href='hotmoney.html'>游资看板</a>"
       f"<a href='status_{DATE}.html'>状态报告</a></div>")

body = (
    f"<header><h1>💼 组合分析 — 换仓后快照</h1>"
    f"<p>数据口径：持仓来自券商导出（{SNAP_DATE}），行情涨跌为 {DATE}（最新交易日）。共 {len(rows)} 只持仓股。</p></header>"
    f"<div class='meta'>数据源：券商导出持仓（table.xls）→ _all_store.json + 腾讯自选股实时行情。本页仅做组合层面的客观分析，不构成买卖建议。</div>"

    f"<div class='section'><h2>📊 组合快照</h2>"
    f"<div class='idxrow'>"
    f"<div class='idx'><div class='k'>持仓股市值</div><div class='v'>{fnum(tot_mv,0)}</div><div class='c'>元</div></div>"
    f"<div class='idx'><div class='k'>浮动盈亏</div><div class='v {cls(tot_pnl)}'>{fnum(tot_pnl,0)}</div><div class='c {cls(tot_pnl)}'>{pct(tot_pnl_pct)}</div></div>"
    f"<div class='idx'><div class='k'>8.27 当日盈亏</div><div class='v {cls(tot_day)}'>{fnum(tot_day,0)}</div><div class='c'>元</div></div>"
    f"<div class='idx'><div class='k'>持仓数 / 亏损数</div><div class='v'>{len(rows)}</div><div class='c'>{red_n} 只浮亏</div></div>"
    f"</div></div>"

    f"<div class='section'><h2>🧩 仓位结构</h2>"
    f"<div class='bar'>{bar_seg}</div>"
    f"<div class='note'>各持仓占比（按 8.27 现价市值计算，总持仓股市值 {fnum(tot_mv,0)} 元）。</div></div>"

    f"<div class='section'><h2>🏭 板块集中度</h2>"
    f"<div class='chiprow'>{sec_chips}</div>"
    f"<div class='note'>半导体链（材料/功率/存储/SoC/封测）合计 <b class='down'>{semi_w:.1f}%</b>，为组合核心暴露。</div></div>"

    f"<div class='section'><h2>📋 持仓明细</h2>"
    f"<table><tr><th>名称</th><th class='num'>持仓</th><th class='num'>成本</th><th class='num'>现价</th>"
    f"<th class='num'>浮动盈亏</th><th class='num'>盈亏%</th><th class='num'>8.27</th><th class='num'>仓位%</th>"
    f"<th class='num'>天数</th></tr>{trows}</table></div>"

    f"<div class='section'><h2>⚠️ 风险标记</h2>{flags_html}</div>"

    f"<div class='section'><h2>🔄 换仓对比</h2>{compare}</div>"

    f"<div class='section'><h2>🧭 可执行观察（规则/板块）</h2>{obs_html}</div>"
)

TEMPLATE = ("<!DOCTYPE html><html lang='zh-CN'><head><meta charset='UTF-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1.0'>"
            "<title>组合分析</title><style>{css}</style></head>"
            "<body><div class='wrap'>{nav}{body}</div></body></html>")

html = TEMPLATE.replace("{css}", CSS).replace("{nav}", NAV).replace("{body}", body)
html = html.replace("><", ">\n<")
open(os.path.join(WEB, "portfolio_analysis.html"), "w", encoding="utf-8").write(html)
print("wrote web/portfolio_analysis.html  rows=%d tot_mv=%.0f tot_pnl=%.0f(%.2f%%) semi_w=%.1f%%" %
      (len(rows), tot_mv, tot_pnl, tot_pnl_pct, semi_w))
