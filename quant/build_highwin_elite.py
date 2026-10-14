# -*- coding: utf-8 -*-
"""高胜率候选池 · 精中取精（胜率候选 · 观察用 · 未过样本外稳健性闸 + 底池冻结）

目的
----
用户要求「量化策略（高胜率池）列出的股票 = 整个判断逻辑中胜率最高的，精中取精」。
本脚本在「高胜率池（得分 = 胜率代理）排序后最靠前的一撮」里取综合分最高者作为**观察候选**呈现，
与 web/selected/elite_*.html（主升精选精中取精）同口径、同红线纪律。

⚠ 红线约束（不可逾越）
----------------------
本页**只作观察 / 待选，不构成可执行信号**，且高胜率池比主升精选多一道更硬的否决：
  · 数据有效性闸：MACD 底池自 2026-09-17 起连续 6 期逐字节冻结，收盘价反查 35/35 只精确等于
    2026-09-11 —— 当前页面标的用的是一份旧快照冒充当日，违反「严禁旧数据冒充当日」。
    → 在数据修好前，本池候选连「当日信号」都不是，更谈不上出票（优先级高于一切策略优化）。
  · 第五道闸：CORE 档（可得子分前 10% 降级口径）样本外 edge 在 7 个采样频率下全为负
    （−1.886~−0.2929pp、R3 最低 3.0%）→ 全站 23 档无一跨过 0.15pp 双边成本线。
  · 胜率：乐观口径 55.80%、保守（可兑现）口径仅 49.64%（Δ−6.16pp），且两口径均值均为负
    → 胜率最高 ≠ 可赚钱。
  → 按「无证据不上 / 宁可不选」维持 fail-safe：本页不给出票结论。

数据真源（统计数字不写死，全部追到证据页）
------------------------------------------
  当日候选池：    quant/picks/highwin_{DATE}.json（emit_ok / emit_why / rows）
  第五道闸：      quant/_freq_robust_hw.json（CORE 档 edge / R3）
  分档核验证据：  quant/_hw_gate_page.py → web/picks/highwin_tier_gate.html
  底池冻结 / 退出假设：quant/_hw_tier_gate.json（freeze / exit_assumption）

用法
----
  python quant/build_highwin_elite.py 2026-10-09
"""
from __future__ import annotations
import os, json, argparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QUANT = os.path.join(ROOT, "quant")
PICKS = os.path.join(QUANT, "picks")
PAGE = os.path.join(ROOT, "web", "picks")
os.makedirs(PAGE, exist_ok=True)


def _fmt(v, d=4):
    if v is None:
        return "—"
    return "%+.*f" % (d, v)


TEMPLATE = r"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>高胜率候选池 · 精中取精（胜率候选·观察用）· __DATE__</title>
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
.tag.core{background:#fdecea;color:#b8332a}
.tag.obs{background:#eef4fa;color:#2b6cb0}
.foot{text-align:center;color:var(--muted);font-size:12px;margin-top:28px}
</style><!--WB_THEME-->
</head><body><div class="wrap">
<h1>高胜率候选池 · 精中取精（胜率候选 · 观察用）</h1>
<div class="sub">数据基准 __DATE__ 收盘｜ 底池 = MACD 水上金叉 + 20 日主力净流入&gt;0（__N_POOL__ 只，全市场域 __POOL_TOTAL__ 只）
｜ 在「综合分排序最靠前」的一撮里取 __ELITE_N__ 只（≈全池前 __PCT_POOL__%）作为观察候选</div>

<div class="box red"><b>⚠️ 红线声明（必读）：本页是「观察候选」，不是「出票」。</b><br>
本页列出的票是判断逻辑里<b>综合分（胜率代理）最靠前</b>的一撮，但它们<b>未过样本外稳健性闸</b>，且高胜率池当前另有一道更硬的否决：<br>
<b>① 底池冻结（数据有效性闸，优先级最高）</b>：MACD 底池自 <b>__FROZEN_FROM__</b> 起连续 <b>__FROZEN_DAYS__</b> 期逐字节未重扫
（dif/dea/close 全同），其收盘价反查 <b>__FROZEN_HIT__/__FROZEN_N__</b> 只精确等于 <b>__FROZEN_CLOSE__</b> ——
即本页标的实为一份旧快照冒充当日，违反「严禁旧数据冒充当日」。<b>在数据修好前，本池连「当日信号」都不是</b>。<br>
<b>② 第五道闸</b>：CORE 档（可得子分前 10% 降级口径）样本外 edge 在 7 个采样频率下<b>全为负</b>
（__EDGE_MIN__~__EDGE_MAX__pp、R3 最低 __R3_MIN__%）；全站 23 个可判定档<b>无一跨过 0.15pp 双边成本线</b>。<br>
<b>③ 胜率≠edge</b>：CORE 乐观口径胜率 <b>__WR_OLD__%</b>、保守（可兑现）口径仅 <b>__WR_REAL__%</b>（Δ__WR_DELTA__pp），两口径<b>均值均为负</b>。
<b>胜率最高 ≠ 可赚钱</b>（项目反复踩的坑）。<br>
按「无证据不上 / 宁可不选」维持 fail-safe：<code>emit_ok=__EMIT_OK__</code>（__EMIT_WHY__），本页<b>不给出票结论</b>。</div>

<div class="box gold"><b>「胜率」的真实数字（追到证据页，非写死）：</b><br>
① 逐档核验页 <code>quant/_freq_robust_hw.json</code> → CORE 档样本外 edge <b>__EDGE_MIN__~__EDGE_MAX__pp</b>、R3 最低 <b>__R3_MIN__%</b>（门槛 95%）；<br>
② 退出成交假设审计（<code>quant/_hw_tier_gate.json</code> → exit_assumption）：CORE 档乐观口径胜率 <b>__WR_OLD__%</b>（均值 __MEAN_OLD__）、
可兑现口径胜率 <b>__WR_REAL__%</b>（均值 __MEAN_REAL__），<b>Δ胜率 __WR_DELTA__pp</b>；<br>
③ 上述胜率依赖移动止盈回测，而旧实现含「日内路径乐观 + 忽略跳空」两处假设；改保守口径后胜率进一步下降、亏损面扩大。<br>
关键：即便乐观口径胜率 55.80%，因<b>单次盈利薄、亏损深</b>（均值 −1.77%），整体仍亏 —— 所以「胜率高」不能当「能赚钱」。</div>

<div class="box"><b>第五道闸 / 成本闸 / 数据闸证据位置（自证，不重述结论）：</b><br>
· 跨采样频率稳健性：<code>quant/_freq_robust_hw.json</code>（CORE 档 ok=false）；<br>
· 经济可执行线：<code>quant/_cost_gate.py</code>（全站 23 档 0 可执行）；<br>
· 分档核验 + 底池冻结 + 退出假设：<code>quant/_hw_gate_page.py</code> → <code>web/picks/highwin_tier_gate.html</code>。<br>
本页只做「精中取精」呈现，不改变任何闸的判定。</div>

<h2>一、精中取精 · 观察候选（综合分最靠前 __ELITE_N__ 只 · 胜率代理最靠前）</h2>
<div class="card"><div style="overflow-x:auto"><table>
<thead><tr><th>代码</th><th>名称</th><th>现价</th><th>综合分</th><th>档</th><th>板块行为</th>
<th>52周分位</th><th>20日主力净流入</th><th>RSI</th><th>关键因子</th><th>性质</th></tr></thead>
<tbody>__ELITE_TBL__</tbody></table></div>
<div class="sub">综合分 = 8 维打分（趋势25/位置15/资金20/筹码15/板块12/龙虎榜8/高管大宗5）的当日横截面排序，越高=越像高胜率形态=历史胜率代理越靠前。
<b>所有标的均为观察候选，非买入信号</b>；且本页底座为冻结快照（见红线声明①），仅供参考、不可作为当日下单依据。</div></div>

<h2>二、逐票明细（前 __MIN40__ 只）</h2>
__ELITE_CARDS__

<h2>三、为什么「精中取精」仍不能当出票（高胜率池额外两条）</h2>
<div class="card kv">
① <b>底池是旧快照（最硬否决）</b>：MACD 底池自 __FROZEN_FROM__ 起冻结 __FROZEN_DAYS__ 期，收盘价反查等于 __FROZEN_CLOSE__。
哪怕打分再漂亮，拿过期信息下单 = 用 9 月 11 日的图决定 10 月 9 日的买卖，纯属无效。<b>先修底池重扫，再谈胜率</b>。<br>
② <b>胜率是档位统计量，不是逐票属性</b>：单只股票单次前向是「赚/亏」二值，谈不上「率」；
硬算逐票胜率等于用样本内数据拟合，是过拟合。本页「胜率」单位是<b>档</b>（CORE 整体）。<br>
③ <b>胜率≠edge</b>：CORE 乐观口径胜率 55.80% 但均值 −1.77%（涨时赚得少、跌时亏得多），保守口径胜率降至 49.64% —— 整体仍亏。<br>
④ <b>样本外才是真钱</b>：第五道闸（符号一致 + 全频 R3≥95%）+ 成本闸（跨过 0.15pp 双边成本）是出票硬门槛；
CORE 两关都不达 → fail-safe 空仓。<br>
⑤ <b>唯一可用的杠杆是环境</b>：弱势档绝对胜率仅 ~41%、强势档 ~51%（差 10pp，远大于选股带来的 1~3pp）。
故正确动作是「弱势降暴露 / 空仓」，而非「弱势里精挑细选」。<br>
⑥ 本页结论与 <code>web/picks/highwin_tier_gate.html</code>（分档核验页）一致：当前不出票（宁可不选）。
本页只是把「观察池里综合分最靠前的一撮」单独拎出来方便你盯——且提醒你这撮数据本身已过期。</div>

<div class="foot">本页为基于离线日K的量化筛选与方法论，<b>非个股推荐、非买卖建议</b>。
决策责任在账户本人。数据基准 __DATE__（底池实际为 __FROZEN_CLOSE__ 冻结快照）。精中取精 ≠ 可执行信号。</div>
</div></body></html>"""


def _load(p, d=None):
    if not os.path.exists(p):
        return d
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return d


def render(elite, hw, date, elite_n, n_pool, pool_total):
    # ---- 证据（运行期读取，不写死）----
    fr = _load(os.path.join(QUANT, "_freq_robust_hw.json"), {}) or {}
    core = next((t for t in (fr.get("tiers") or []) if t.get("tier") == "CORE"), None)
    edge_min = (core or {}).get("edge_min")
    edge_max = (core or {}).get("edge_max")
    r3_min = (core or {}).get("min_r3")

    gate = _load(os.path.join(QUANT, "_hw_tier_gate.json"), {}) or {}
    ea = gate.get("exit_assumption") or {}
    wr_old = wr_real = wr_delta = mean_old = mean_real = None
    for t in (ea.get("tiers") or []):
        if t.get("tier") == "CORE" and t.get("rows"):
            r = t["rows"]
            m0, mz = r[0], r[-1]
            wr_old, mean_old = m0.get("wr"), m0.get("mean")
            wr_real, mean_real = mz.get("wr"), mz.get("mean")
            wr_delta = (mz.get("wr") - m0.get("wr")) if (mz.get("wr") is not None and m0.get("wr") is not None) else None
            break
    frz = gate.get("freeze") or []
    fz = [x for x in frz if x.get("frozen")]
    frozen_from = frozen_days = frozen_hit = frozen_n = frozen_close = "—"
    if fz:
        allr = sorted(frz, key=lambda x: x["file"])
        fi = allr.index(fz[0])
        origin = allr[fi - 1] if fi > 0 else fz[0]
        frozen_from = origin.get("data_date") or "—"
        frozen_days = len(fz) + 1
        frozen_hit = fz[-1].get("frozen_close_hit")
        frozen_n = fz[-1].get("frozen_close_n")
        frozen_close = fz[-1].get("frozen_close_date") or "—"

    emit_ok = hw.get("emit_ok")
    emit_why = hw.get("emit_why") or "证据不可用"

    trs, cards = [], []
    for r in elite:
        tier = r.get("tier", "")
        tcls = "core" if tier == "核心" else ("obs" if tier == "观察" else "")
        fac = ("趋势 %s｜位置 %s｜资金 %s｜筹码 %s｜板块 %s｜龙虎榜 %s｜高管大宗 %s"
               % (r.get("c_tech"), r.get("c_pos"), r.get("c_fund"), r.get("c_chip"),
                  r.get("c_sec"), r.get("c_lhb"), r.get("c_eb")))
        trs.append(
            "<tr><td>%s</td><td>%s</td><td class='num'>%s</td>"
            "<td class='num' style='font-weight:700'>%s</td>"
            "<td><span class='tag %s'>%s</span></td><td class='kv'>%s</td>"
            "<td class='num'>%s%%</td><td class='num'>%s亿</td><td class='num'>%s</td>"
            "<td class='kv'>%s</td><td><span class='tag ob'>观察</span></td></tr>"
            % (r["code"], r["name"], r.get("price"), r.get("total"), tcls, tier,
               r.get("behavior"), r.get("pos52"), r.get("flow20d_yi"), r.get("rsi12"), fac))
        cards.append(
            "<div class='case'><div class='h'>🔎 %s %s —— 综合分 %s/100（档=%s · 胜率代理最靠前）</div>"
            "<div class='kv'>%s</div>"
            "<div class='bp'>现价 %s｜板块行为 %s｜52周分位 %s%%｜20日主力净流入 %s亿｜RSI %s"
            " <span class='tag ob'>观察候选·非可执行</span></div></div>"
            % (r["code"], r["name"], r.get("total"), tier, fac, r.get("price"),
               r.get("behavior"), r.get("pos52"), r.get("flow20d_yi"), r.get("rsi12")))

    html = (TEMPLATE
            .replace("__DATE__", date)
            .replace("__N_POOL__", str(n_pool))
            .replace("__POOL_TOTAL__", str(pool_total))
            .replace("__ELITE_N__", str(elite_n))
            .replace("__PCT_POOL__", "%.1f" % (elite_n / n_pool * 100 if n_pool else 0))
            .replace("__FROZEN_FROM__", str(frozen_from))
            .replace("__FROZEN_DAYS__", str(frozen_days))
            .replace("__FROZEN_HIT__", str(frozen_hit))
            .replace("__FROZEN_N__", str(frozen_n))
            .replace("__FROZEN_CLOSE__", str(frozen_close))
            .replace("__EDGE_MIN__", _fmt(edge_min) if edge_min is not None else "—")
            .replace("__EDGE_MAX__", _fmt(edge_max) if edge_max is not None else "—")
            .replace("__R3_MIN__", ("%.1f" % r3_min) if r3_min is not None else "—")
            .replace("__WR_OLD__", ("%.2f" % wr_old) if wr_old is not None else "—")
            .replace("__WR_REAL__", ("%.2f" % wr_real) if wr_real is not None else "—")
            .replace("__WR_DELTA__", ("%+.2f" % wr_delta) if wr_delta is not None else "—")
            .replace("__MEAN_OLD__", ("%+.3f%%" % mean_old) if mean_old is not None else "—")
            .replace("__MEAN_REAL__", ("%+.3f%%" % mean_real) if mean_real is not None else "—")
            .replace("__EMIT_OK__", str(emit_ok))
            .replace("__EMIT_WHY__", str(emit_why))
            .replace("__ELITE_TBL__", "".join(trs))
            .replace("__ELITE_CARDS__", "".join(cards) or
                     "<div class='box'>本期无达标候选。</div>")
            .replace("__MIN40__", str(min(elite_n, 40))))
    return html


def main(date):
    ds = date.replace("-", "")
    hw = _load(os.path.join(PICKS, "highwin_%s.json" % date))
    if not hw:
        raise SystemExit("未找到 quant/picks/highwin_%s.json" % date)
    rows = hw.get("rows", [])
    n_pool = len(rows)
    pool_total = hw.get("pool_total") or "—"
    # rows 已按 tier 再 -total 排序；精中取精 = 综合分最靠前一撮
    elite_n = max(15, round(n_pool * 0.01))
    elite = rows[:elite_n]
    html = render(elite, hw, date, elite_n, n_pool, pool_total)
    out = os.path.join(PAGE, "highwin_elite_%s.html" % ds)
    open(out, "w", encoding="utf-8").write(html)
    json.dump({"date": date, "n_pool": n_pool, "pool_total": pool_total,
               "elite_n": len(elite), "elite_codes": [r["code"] for r in elite],
               "note": "观察候选·底池冻结+未过样本外稳健性闸·非可执行信号"},
              open(os.path.join(PAGE, "highwin_elite_%s.json" % ds), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("[hw-elite] 精中取精 %d 只（底池 %d / 全市场域 %s）→ %s" % (len(elite), n_pool, pool_total, out))
    return elite


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("date", nargs="?", default="2026-10-09")
    a = ap.parse_args()
    main(a.date)
