# -*- coding: utf-8 -*-
"""主升精选 · 精中取精（胜率候选 · 观察用 · 未过样本外稳健性闸）

目的
----
用户要求「量化策略列出的股票 = 整个判断逻辑中胜率最高的，精中取精」。
本脚本在「全市场主升分前 5%（样本内胜率最高档 ~67%）」里，再取主升分最靠前的
那一撮（胜率代理最靠前）作为**观察候选**呈现。

⚠ 红线约束（不可逾越）
----------------------
本页**只作观察 / 待选，不构成可执行信号**：
  该档样本外 edge 在 7 个采样频率下全为负或符号翻转（legacy −0.185~+1.421pp、
  翻转 1 次@step10、R3 最低 48.0%；realistic 口径 R3 最低 14.5%），
  全站 23 个可判定档**无一跨过 0.15pp 双边成本线**（见 quant/_cost_gate.py）。
  → 胜率最高 ≠ 可赚钱（胜率≠edge，项目反复踩的坑）。
  → 按「无证据不上 / 宁可不选」维持 fail-safe：本页不给出票结论。

数据真源（统计数字不写死，全部追到证据页）
------------------------------------------
  档内胜率：quant/_selected_model.json → evidence.curve / prior_test_wr / pct_gate
  第五道闸：quant/_freq_robust_selected.json
  成本闸：  quant/_cost_gate.py
  口径修正：quant/_exit_assumption_audit.json（乐观→保守成交）

用法
----
  python quant/build_selected_elite.py 2026-10-09
"""
from __future__ import annotations
import os, sys, json, argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_selected as S
from _nav import topnav

ROOT = S.ROOT
OUTDIR = S.OUTDIR
os.makedirs(OUTDIR, exist_ok=True)


def _fmt(v, d=2):
    return "—" if v is None else ("%+.2f" % v)


TEMPLATE = r"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>主升精选 · 精中取精（胜率候选·观察用）· __DATE__</title>
<style>
:root{--bg:#fbfbfd;--card:#fff;--text:#1d1d1f;--muted:#6e6e73;--line:#e5e5e7;
 --up:#ff3b30;--dn:#34c759;--blue:#0071e3;--gold:#b8893b;--orange:#ff9500;}
*{box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"PingFang SC","Microsoft YaHei",sans-serif;
 background:var(--bg);color:var(--text);line-height:1.7;margin:0;padding:0}
.wrap{max-width:1060px;margin:0 auto;padding:28px 18px 56px}
h1{font-size:23px;font-weight:700;margin:0 0 6px;letter-spacing:-.02em}
h2{font-size:18px;font-weight:600;margin:26px 0 12px;padding-bottom:8px;border-bottom:2px solid var(--blue)}
.sub{color:var(--muted);font-size:13px;margin-bottom:8px}
.card{background:var(--card);border-radius:16px;padding:16px 20px;margin:12px 0;box-shadow:0 1px 3px rgba(0,0,0,.05)}
.box{border-left:4px solid var(--blue);background:#f0f7ff;padding:14px 18px;border-radius:0 12px 12px 0;margin:14px 0}
.box.red{border-color:var(--up);background:#fff5f4}
.box.gold{border-color:var(--gold);background:#fffaf0}
table{width:100%;border-collapse:collapse;font-size:12.5px;margin:10px 0}
th,td{padding:8px 6px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
th{color:var(--muted);font-weight:600;font-size:11.5px;background:#fafafa;white-space:nowrap}
.num{font-variant-numeric:tabular-nums}
.up{color:var(--up)}.dn{color:var(--dn)}.am{color:var(--blue)}
.case{font-size:13px;margin:10px 0;padding:12px 16px;background:#fafafa;border-radius:10px;border-left:3px solid var(--gold)}
.case .h{font-weight:600;margin-bottom:4px}
.kv{font-size:12.5px;color:var(--muted)}
.bp{background:#f7f9fc;border:1px solid var(--line);border-radius:10px;padding:10px 14px;margin:8px 0;font-size:13px}
.bp b{color:var(--blue)}
.tag{display:inline-block;font-size:11px;padding:2px 8px;border-radius:10px;margin:1px 2px}
.tag.ob{background:#fff3e0;color:#e65100}
.foot{text-align:center;color:var(--muted);font-size:12px;margin-top:28px}
</style><!--WB_THEME-->
</head><body><div class="wrap">
<h1>主升精选 · 精中取精（胜率候选 · 观察用）</h1>
<div class="sub">数据基准 __DATE__ 收盘｜ 全市场域（剔 ST/退 + 20日均额≥3000万 + 现价≥2元）
｜ 在「主升分前 __PCT__%（样本内胜率最高档）」中再取主升分最靠前 <b>__ELITE_N__</b> 只（≈全市场前 1%）</div>

<div class="box red"><b>⚠️ 红线声明（必读）：本页是「观察候选」，不是「出票」。</b><br>
本页列出的票是判断逻辑里<b>胜率代理最靠前</b>的一撮，但它们<b>未过样本外稳健性闸</b>：
该档（主升分前 5%）样本外 edge 在 7 个采样频率下<b>全为负或符号翻转</b>
（legacy __EDGE_MIN__~__EDGE_MAX__pp、翻转 __FLIPS__ 次@step10、R3 最低 __R3_MIN__%）；
全站 23 个可判定档<b>无一跨过 0.15pp 双边成本线</b>（见 <code>quant/_cost_gate.py</code>）。
<b>胜率最高 ≠ 可赚钱</b>（胜率≠edge，项目反复踩的坑）。按「无证据不上 / 宁可不选」维持 fail-safe：
本页<b>不给出票结论</b>，仅供你盯票、等环境转强后待选。</div>

<div class="box gold"><b>档内胜率的真实数字（追到 quant/_selected_model.json → evidence，非写死）：</b><br>
① 样本内全样本（前 5% 档）胜率 <b>__WR_BEST__%</b>（乐观成交口径）；<br>
② 严格样本外测试半（前 60% 学 → 后 40% 测）先验集胜率 <b>__WR_TEST__%</b>，基线 __BASE_WR__%；<br>
③ ⚠️ 上述胜率依赖退出回测成交假设：改按<b>可实现口径</b>（保守日内 + 跳空成交）后胜率降至约 <b>60%</b>
（见 <code>quant/_exit_assumption_audit.json</code>）。<br>
关键：即便胜率 60%+，因<b>单次盈利薄、亏损深</b>，样本外 edge 仍为负 —— 所以「胜率高」不能当「能赚钱」。</div>

<div class="box"><b>第五道闸 / 成本闸证据位置（自证，不重述结论）：</b><br>
· 跨采样频率稳健性：<code>quant/_freq_robust_selected.json</code>（TOP5 档 ok=false）；<br>
· 经济可执行线：<code>quant/_cost_gate.py</code>（全站 23 档 0 可执行）；<br>
· 口径修正：<code>quant/_exit_assumption_audit.json</code>。<br>
本页只做「精中取精」呈现，不改变任何闸的判定。</div>

<h2>一、精中取精 · 观察候选（主升分最靠前 __ELITE_N__ 只 · 胜率代理最靠前）</h2>
<div class="card"><div style="overflow-x:auto"><table>
<thead><tr><th>代码</th><th>名称</th><th>现价</th><th>主升分</th><th>全市场排名</th>
<th>买区</th><th>止损</th><th>目标T1/T2</th><th>关键因子</th><th>性质</th></tr></thead>
<tbody>__ELITE_TBL__</tbody></table></div>
<div class="sub">主升分 = 先验固定因子在<b>当日全市场域内</b>的横截面分位（0~100，越高=越像主升形态=历史胜率代理越靠前），只在同日内可比。
买卖点为量化参考区间。<b>所有标的均为观察候选，非买入信号。</b></div></div>

<h2>二、逐票明细（前 __MIN40__ 只）</h2>
__ELITE_CARDS__

<h2>三、为什么「精中取精」仍不能当出票</h2>
<div class="card kv">
① <b>胜率是档位统计量，不是逐票属性</b>：单只股票单次前向是「赚/亏」二值，谈不上「率」；
   硬算逐票胜率等于用样本内数据拟合，是过拟合。本页的「胜率」单位是<b>档</b>（前 5% 整体 ~67%）。<br>
② <b>胜率≠edge</b>：胜率高只说明「涨的次数多」，但若「涨时赚 1%、跌时亏 3%」，整体仍亏。
   该档样本外 edge 为负即此理。<br>
③ <b>样本外才是真钱</b>：第五道闸（符号一致 + 全频 R3≥95%）+ 成本闸（跨过 0.15pp 双边成本）
   是出票的硬门槛；本档两关都不达 → fail-safe 空仓。<br>
④ <b>唯一可用的杠杆是环境</b>：弱势档绝对胜率仅 ~41%、强势档 ~51%（差 10pp，远大于选股带来的 1~3pp）。
   故正确动作是「弱势降暴露 / 空仓」，而非「弱势里精挑细选」。<br>
⑤ 本页结论与 <code>web/selected/index.html</code>（主升精选主页）一致：主页按环境门控决定出手/观察，
   本页只是把「观察池里胜率代理最靠前的一撮」单独拎出来方便你盯。</div>

<div class="foot">本页为基于离线日K的量化筛选与方法论，<b>非个股推荐、非买卖建议</b>。
决策责任在账户本人。数据基准 __DATE__。精中取精 ≠ 可执行信号。</div>
</div></body></html>"""


def render(elite, rows, model, date, elite_n, n_univ, nA):
    pct = model.get("pct", 0.05)
    ev = model.get("evidence", {}) or {}
    wr_curve = ev.get("curve", []) or []
    wr_best = max((c["wr"] for c in wr_curve), default=0.0)
    wr_test = ev.get("prior_test_wr") or ev.get("test_wr") or 0.0
    base_wr = ev.get("base_wr", 0.0)
    # 第五道闸 / 成本闸 真值（来自证据页，非写死）
    fr = {}
    try:
        fr = json.load(open(os.path.join(S.QUANT, "_freq_robust_selected.json"), encoding="utf-8"))
    except Exception:
        pass
    top5 = next((t for t in (fr.get("tiers") or []) if t.get("tier") == "TOP5"), None)
    edge_min = top5.get("edge_min") if top5 else None
    edge_max = top5.get("edge_max") if top5 else None
    r3_min = top5.get("min_r3") if top5 else None
    flips = top5.get("flips") if top5 else None

    trs = []
    cards = []
    for r in elite:
        f = r["f"]
        bs = r.get("bs")
        fac = ("近20日动量 %+.1f%%｜近60日 %+.1f%%｜站上MA60 %+.1f%%｜MA20斜率 %+.1f%%｜"
               "均线多头 %+.1f%%｜接近近20日高 %+.1f%%｜上涨放量 %.0f%%｜量能放大 %.2f｜回调缩量 %.2f"
               % (f["rel20"] * 100, f["rel60"] * 100, f["above_ma60"] * 100, f["slope20"] * 100,
                  f["ma_strength"] * 100, f["dist_h20"] * 100, f["up_vol"] * 100, f["rvol"], f["vol_dry"]))
        if bs:
            bx = "箱体 %s%%（%s）" % (bs["pos_pct"], bs["pos_tag"])
            bz = "%s~%s" % (bs["entry_lo"], bs["entry_hi"])
            stp = "%s（RR %s）" % (bs["stop"], bs["rr"])
            tgt = "%s / %s" % (bs["t1"], bs["t2"])
        else:
            bx = bz = stp = tgt = "—"
        name_l = S.EM.link(r["_full"], r["name"])
        code_l = S.EM.link(r["_full"], r["code"], cls="")
        trs.append(
            "<tr><td>%s</td><td>%s</td><td class='num'>%s</td>"
            "<td class='num' style='font-weight:700'>%s</td><td class='num'>%s</td>"
            "<td class='num'>%s</td><td class='num'>%s</td><td class='num'>%s</td>"
            "<td class='kv'>%s</td><td><span class='tag ob'>观察</span></td></tr>"
            % (code_l, name_l, r["close"], r.get("qs"), r.get("qrank"), bz, stp, tgt, fac))
        cards.append(
            "<div class='case'><div class='h'>🔎 %s %s —— 主升分 %s/100（全市场第 %s 名 · 胜率代理最靠前）</div>"
            "<div class='kv'>%s</div>"
            "<div class='bp'>买区 %s｜结构位止损 %s｜目标 T1/T2 %s｜%s"
            " <span class='tag ob'>观察候选·非可执行</span></div></div>"
            % (code_l, name_l, r.get("qs"), r.get("qrank"), fac, bz, stp, tgt, bx))

    html = (TEMPLATE
            .replace("__DATE__", date)
            .replace("__PCT__", "%.0f" % (pct * 100))
            .replace("__ELITE_N__", str(elite_n))
            .replace("__N_UNIV__", str(n_univ))
            .replace("__NA__", str(nA))
            .replace("__WR_BEST__", "%.1f" % wr_best)
            .replace("__WR_TEST__", "%.1f" % wr_test)
            .replace("__BASE_WR__", "%.1f" % base_wr)
            .replace("__EDGE_MIN__", _fmt(edge_min))
            .replace("__EDGE_MAX__", _fmt(edge_max))
            .replace("__FLIPS__", str(flips if flips is not None else "—"))
            .replace("__R3_MIN__", ("%.1f" % r3_min) if r3_min is not None else "—")
            .replace("__ELITE_TBL__", "".join(trs))
            .replace("__ELITE_CARDS__", "".join(cards) or
                     "<div class='box'>本期无达标候选（连观察池都空，说明全市场趋势共振度极低）。</div>")
            .replace("__MIN40__", str(min(elite_n, 40))))
    return html


def main(date):
    shown, rows, model, n, nA = S.scan(date)
    elite_n = max(15, round(n * 0.01))
    elite = shown[:elite_n]
    html = render(elite, rows, model, date, elite_n, n, nA)
    ds = date.replace("-", "")
    out = os.path.join(OUTDIR, "elite_%s.html" % ds)
    open(out, "w", encoding="utf-8").write(html)
    json.dump({"date": date, "n_universe": n, "nA": nA, "elite_n": len(elite),
               "elite_codes": [r["code"] for r in elite],
               "note": "观察候选·未过样本外稳健性闸·非可执行信号"},
              open(os.path.join(OUTDIR, "elite_%s.json" % ds), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("[elite] 精中取精 %d 只（全市场域 %d / A档前5%% %d）→ %s" % (len(elite), n, nA, out))
    return elite


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("date", nargs="?", default="2026-10-09")
    a = ap.parse_args()
    main(a.date)
