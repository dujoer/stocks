#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""做T池 · 分档出票核验 证据页 + 出票许可

读 `_tplus_tier_gate.json` / `__step3.json`，产出
  * `web/tplus/tier_gate.html` —— 证据页
  * `emit_license()` —— 供 `build_tplus.py` 消费（fail-safe，含池化闸）

★ 本池的核心发现（与其它池不同，必须两个口径并排看）：
  做T是**区间操作**，且「不成交」也是一种结果。实测 A 档：
    逐日平衡 edge **+0.54pp**（R3 95.0%、留一全正、前后半同向）← 看着像能出票
    池化「触买后」期望 **−0.28%**、往返率仅 5.15%（对照 12.65%）  ← 实际做一笔是亏的
  两个口径**方向相反**：逐日平衡衡量「每天都重选 A 档是否更优」，池化衡量「实际成交能赚多少」。
  差额来自不成交的空值（`kind=none/expire`）—— A 档 55.6% 的信号根本没进过买卖区。
  ⇒ **只报逐日平衡就放行 = 拿一个不反映真实执行的数字出票**，本池不写这条规则。

不写死任何数字 —— 全部来自证据 JSON。
"""
from __future__ import annotations
import os, re, sys, json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _gate_common as GC

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QUANT = os.path.join(ROOT, "quant")
WEBP = os.path.join(ROOT, "web", "tplus")
MAIN_JSON = os.path.join(QUANT, "_tplus_tier_gate.json")
SENS_JSON = os.path.join(QUANT, "_tplus_tier_gate_step3.json")
OUTHTML = os.path.join(WEBP, "tier_gate.html")

ORDER = ["A", "B", "C"]
# 做T只有 A 档进主榜/操作手册（build_tplus: anchors = release ∧ grade=="A"）
EMIT_KEYS = ("A",)
CN = {"A": "A 档（域内前 10%·可重点做T·主榜唯一出票档）",
      "B": "B 档（前 10~25%·适合做T）",
      "C": "C 档（其余·仅跟踪）"}


def _load(p):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return None


def _f(v, d=4):
    return "—" if v is None else ("%+.4f" % v if d == 4 else "%+.3f" % v)


def _p(v):
    return "—" if v is None else "%.1f" % v


def emit_license():
    return GC.emit_license(MAIN_JSON, SENS_JSON, EMIT_KEYS, CN,
                           pool_key=("A", "pooled_hitbuy"))


def _latest():
    try:
        fs = sorted(f[6:-5] for f in os.listdir(WEBP)
                    if re.match(r"^tplus-\d{4}-\d{2}-\d{2}\.html$", f))
    except OSError:
        return ""
    return fs[-1] if fs else ""


def render(res):
    per = {t.get("tier"): t for t in res["tiers"]}
    js = _load(SENS_JSON)
    per3 = {t.get("tier"): t for t in (js or {}).get("tiers", [])}
    lic = emit_license()
    d = lic.get("detail", {})
    pg = lic.get("pooled_gate")

    def cls(v):
        return "up" if (v or 0) > 0 else "dn"

    rows, prows, srow, hrow = [], [], [], []
    for k in ORDER:
        t = per.get(k) or {}
        e = t.get("edge")
        if t.get("note"):
            rows.append("<tr><td><b>%s</b></td><td colspan='6' class='kv'>%s</td></tr>"
                        % (CN.get(k, k), t["note"]))
            continue
        rows.append(
            "<tr><td><b>%s</b></td><td class='num'>%d</td>"
            "<td class='num %s'>%s</td><td class='num %s'>%s</td>"
            "<td class='kv'>[%s, %s]</td></tr>"
            % (CN.get(k, k), t.get("n_rows", 0), cls(e), _f(e) + "pp",
               "up" if (t.get("r3") or 0) >= 95 else "dn", _p(t.get("r3")) + "%",
               _f(t.get("loo_min")), _f(t.get("loo_max"))))
        # ★ 池化口径行
        prows.append(
            "<tr><td><b>%s</b></td>"
            "<td class='num %s'>%s</td><td class='num'>%s</td><td class='num'>%s</td>"
            "<td class='num'>%s</td><td class='num'>%s</td></tr>"
            % (CN.get(k, k), cls(t.get("pooled_hitbuy")), _f(t.get("pooled_hitbuy")) + "%",
               _f(t.get("pooled_all")) + "%", _p(t.get("hit_buy_abs")) + "%",
               _p(t.get("round_abs")) + "%", _p(t.get("stop_abs")) + "%"))
        t3 = per3.get(k) or {}
        e3 = t3.get("edge")
        srow.append(
            "<tr><td><b>%s</b></td><td class='num %s'>%s</td><td class='num %s'>%s</td>"
            "<td class='kv'>%s</td></tr>"
            % (CN.get(k, k), cls(e3), _f(e3) + "pp",
               "up" if (t3.get("r3") or 0) >= 95 else "dn", _p(t3.get("r3")) + "%",
               ("同号" if (e3 is not None and e is not None and e3 * e > 0)
                else ("翻号" if e3 is not None else "—"))))
        hv = t.get("halves") or []
        htxt = " ｜ ".join("%s %s（%d 日中 %d 日为正）"
                          % (h["half"], _f(h["edge"]) + "pp", h["n_days"],
                             h["edge_pos_days"]) for h in hv)
        hrow.append("<tr><td><b>%s</b></td><td class='kv'>%s</td></tr>"
                    % (CN.get(k, k), htxt or "—"))

    lic_rows = "".join(
        "<tr><td>%s</td><td class='%s'>%s</td><td class='kv'>%s</td></tr>"
        % (CN.get(k, k), "up" if v["ok"] else "dn",
           "可出票" if v["ok"] else "不出票", v["why"])
        for k, v in sorted(d.items(), key=lambda kv: ORDER.index(kv[0])))

    # ---- 退出回测的成交假设：反T「先买后卖」受 A 股 T+1 约束 ----
    ea = res.get("exit_assumption") or {}
    if not ea:
        ea_html = ("<h2>六、退出回测的成交假设</h2>"
                   "<div class='card'><div class='box red' style='border-color:#b00020'>"
                   "<b>⚠️ 可实现口径未核验：</b>本次产物里没有 <code>exit_assumption</code> 段"
                   "（重跑 <code>python quant/_tplus_tier_gate.py</code> 生成）。"
                   "核验完成前本页收益按<b>旧口径</b>计算：同根 K 线既摸买区又摸卖区即记"
                   "「完成一轮」。</div></div>")
    else:
        etr = "".join(
            "<tr><td><b>%s</b></td><td class='num'>%d</td>"
            "<td class='num'>%s</td><td class='num'>%s</td><td class='num'>%s</td>"
            "<td class='num'>%s</td><td class='num'>%s</td><td class='num'>%s</td>"
            "<td class='num'>%s</td><td class='num'>%s</td><td class='num'>%s</td></tr>"
            % (CN.get(t.get("grade"), t.get("grade")), t.get("n", 0),
               _p(t.get("round_abs")) + "%", _p(t.get("round_abs_cons")) + "%",
               _f(t.get("d_round")) + "pp",
               _f(t.get("pooled")) + "%", _f(t.get("pooled_cons")) + "%",
               _f(t.get("d_pooled")) + "pp",
               _f(t.get("edge")) + "pp", _f(t.get("edge_cons")) + "pp",
               _p(t.get("r3")) + "% → " + _p(t.get("r3_cons")) + "%")
            for t in ea.get("tiers", []) if t.get("n"))
        ea_html = ("<h2>六、退出回测的成交假设（两口径并列）</h2>"
                   "<div class='card'><table>"
                   "<thead><tr><th>档</th><th>笔数</th>"
                   "<th>往返率 旧</th><th>往返率 可实现</th><th>Δ</th>"
                   "<th>池化每次 旧</th><th>池化每次 可实现</th><th>Δ</th>"
                   "<th>逐日edge 旧</th><th>逐日edge 可实现</th><th>R3</th></tr></thead>"
                   "<tbody>%s</tbody></table>"
                   "<div class='box red' style='border-color:#b00020'>"
                   "<b>⚠️ 旧口径里有一处实盘做不到的假设：</b>%s。"
                   "旧模拟在同一根 K 线既摸到买区又摸到卖区时<b>无条件记「完成一轮」</b>，"
                   "等于假设日内必定先跌后涨 —— 而 A 股 <b>T+1</b>，当日买入的股份当日不能卖出。"
                   "可实现口径把卖出推迟到<b>次日及以后</b>：%s</div>"
                   "<div class='kv'>%s 打分、买区/卖区/止损阈值<b>一律未改</b>，只改成交可实现性。"
                   "⚠️ A 档逐日 edge 在新口径下<b>反而更高</b>，这再次说明：换口径后的涨跌"
                   "<b>不能</b>当作「该不该改规则」的依据，它只证明旧数字不能拿去挑参数。</div></div>"
                   % (etr, ea.get("why", ""), ea.get("new", ""), ea.get("note", "")))

    a = per.get("A") or {}
    banner = (
        "<b>本页核验：做T池「A 档 = 可重点做T」这条规则，两个口径给出<b>相反</b>的答案</b><br>"
        "① <b>逐日平衡 edge</b>（每天该档均 − 同日非本档均）：A 档 <b>{ae} pp</b>，"
        "R3 <b>{ar}%</b>、留一法 [{al}, {ah}] 全正、前后半同向 —— 单看这一项像<b>可以出票</b>。<br>"
        "② <b>池化口径</b>（实际做一笔的期望）：A 档<b>触买后 {ph}%</b>（全体 {pa}%）—— "
        "做T 是区间操作，<b>「没成交」也是一种结果</b>，不成交的空值会把池化均值拉平，"
        "而逐日平衡几乎看不出这部分。<br>"
        "③ 两者的差额来自成交率：A 档只有 <b>{hb}%</b> 的信号进过买卖区，"
        "<b>往返率仅 {ro}%（同域非 A 档 {rc}%）</b> —— 分数越高成交越少，"
        "「适合做T」这个说法本身与数据相反。<br>"
        "④ 本池额外设一道<b>池化闸</b>：逐日平衡为正但触买后期望 ≤0 → 一律不出票。"
        "只报逐日平衡就放行，等于拿一个不反映真实执行的数字出票。")

    if a and not (d.get("A") or {}).get("ok", False):
        emerg = (
            "<div class='box red' style='border-color:#b00020'>"
            "<b>⚠ 结论：做T池 A 档本期不出票（宁可不选）</b><br>"
            "逐日平衡 edge {ae} pp（R3 {ar}%，门槛 95%）本身是达标的，但<b>池化口径为负</b>："
            "实际触买后做一笔的期望 <b>{ph}%</b>，往返率只有 <b>{ro}%</b>、"
            "而同域非 A 档有 {rc}%。<br>"
            "也就是说这条规则选出的是<b>「看起来安静但很难成交」</b>的票 —— "
            "分数越高成交越少。<b>宁可不选</b>：不能拿「每天都重选更优」的数字，"
            "去支撑「实际做一笔能赚」的结论。</div>")
    else:
        emerg = ("<div class='box'><b>A 档通过出票核验</b> —— 逐日平衡 {ae} pp（R3 {ar}%），"
                 "且触买后池化期望为正。</div>")

    html = """<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>做T池 · 分档出票核验</title></head><body>
<div class="wrap">
<h1>做T池 · 分档出票核验</h1>
<div class="card">{banner}</div>
{banner2}

<h2>一、逐日平衡 edge（对照 = 同日非本档，不含自己）</h2>
<table><thead><tr><th>档</th><th>笔数</th><th>edge</th><th>R3</th>
<th>留一法区间</th></tr></thead><tbody>{rows}</tbody></table>
<div class="kv">edge = 该档逐日均值 − 同日非本档逐日均值（逐日平衡，不是把两堆样本摊平比）。
R3 = bootstrap 中 edge&gt;0 的比例（按日整块重抽 {boot} 次，门槛 95%）。
留一法 = 去掉任意一天后 edge 的极值；<b>区间跨 0 说明结论由个别交易日撑着</b>。</div>

<h2>二、★ 池化口径（做T的真实执行口径，本页结论的关键）</h2>
<table><thead><tr><th>档</th><th>触买后期望（实际做一笔）</th><th>全体期望</th>
<th>触买率</th><th>往返率</th><th>止损率</th></tr></thead><tbody>{prows}</tbody></table>
<div class="kv"><b>触买后期望</b> = 只统计真的进过买区的信号，模拟到卖出/止损/到期的真实收益 ——
这是「我做一笔能不能赚」。<b>全体期望</b>把没成交的也算进来（记 0 或极小值），
会被 <code>kind=none</code>（当日既没触买区也没触卖区）稀释。
<br>做T 的关键不是「每天都重选更优」（那是逐日平衡在问的），而是
<b>「进去之后能不能走出来」</b>。A 档触买后为负、往返率又最低 → 两个口径都在说同一件事：
<b>这档票难成交</b>。</div>

<h2>三、前 / 后半稳定性</h2>
<table><thead><tr><th>档</th><th>前半 / 后半 edge</th></tr></thead><tbody>{hrow}</tbody></table>
<div class="kv">单段行情容易把结论锁在一个市场状态里；只有两半同向才算稳。</div>

<h2>四、跨步长敏感性</h2>
<table><thead><tr><th>档</th><th>step3 edge</th><th>step3 R3</th><th>与主口径符号</th></tr></thead>
<tbody>{srow}</tbody></table>
<div class="kv">⚠ 本池面板由 <code>_tplus_lab</code> 离线重建时<b>已稀疏采样</b>
（{ndays} 个信号日跨 10 个月，非逐日全量），所以此处 step3 与主口径<b>共用同一份面板</b>，
只作符号一致性参考，<b>不是独立的采样步长验证</b>。</div>

<h2>五、出票许可（机器判定，读不到就 fail-safe）</h2>
<table><thead><tr><th>档</th><th>可出票？</th><th>依据</th></tr></thead><tbody>{lic_rows}</tbody></table>
<div class="kv">做T只有 A 档进主榜与操作手册（<code>build_tplus</code>：anchors = release ∧ grade==A），
故许可只判 A 档。闸门顺序：<b>数据闸 → 统计闸（edge/R3/跨步长）→ 池化闸</b>，任一不过即不出票。</div>

{ea_html}

<h2>七、口径与局限</h2>
<div class="card"><ul>
<li>打分因子 = <code>_tplus_lab.PRIOR</code> 的 {nf} 个先验固定因子（不在本页挑、不网格搜），
    逐日在<b>域内</b>转横截面分位后等权平均；分档 A=前10% / B=前25% / C=其余
    （与 <code>build_tplus.rank_rows</code> 同口径）。</li>
<li>做T模拟 = <code>_tplus_lab._sim_default</code>（线上现行：买区 +2% / 卖区 max(2.5%, 1.2×ATR%) /
    止损 −6% / 持有 5 日；同日既触买又触卖保守记完成一轮）。<b>参数一律不在本页调</b>。</li>
<li>面板窗口 {d0} ~ {d1}（{ndays} 个信号日），数据全离线真实日K，不联网、不补造。</li>
<li>本池<b>不重复已证伪的结论</b>：环境门控（<code>_tplus_env_gate</code>）已独立判「不可判」，
    主升精选的二值门控<b>严禁</b>套用到做T（点估计上弱势档还高于强势档）。</li>
<li>本页判定的是<b>「A 档这条规则有没有超额」</b>，<b>不做规则改良</b>：负 edge 不代表反向做能赚，
    是不该拿它出票。</li>
</ul></div>
<div class="note"><a href="index.html">← 返回做T池</a> ｜ <a href="tplus-{latest}.html">当期做T池页面</a> ｜ <a href="lab.html">原始回测实验室</a> ｜ <a href="env_gate.html">环境门控核验</a></div>
</div></body></html>""".format(
        banner=banner.format(
            ae=_f(a.get("edge")) + "pp", ar=_p(a.get("r3")),
            al=_f(a.get("loo_min")), ah=_f(a.get("loo_max")),
            ph=_f(a.get("pooled_hitbuy")) + "%", pa=_f(a.get("pooled_all")) + "%",
            hb=_p(a.get("hit_buy_abs")), ro=_p(a.get("round_abs")),
            rc=_p(a.get("round_ctrl"))),
        banner2=emerg.format(
            ae=_f(a.get("edge")) + "pp", ar=_p(a.get("r3")),
            ph=_f(a.get("pooled_hitbuy")) + "%",
            ro=_p(a.get("round_abs")), rc=_p(a.get("round_ctrl"))),
        rows="\n".join(rows), prows="\n".join(prows),
        srow="\n".join(srow), hrow="\n".join(hrow), lic_rows=lic_rows, ea_html=ea_html,
        boot=res.get("boot", 800),
        ndays=res.get("n_days", "—"), nf=len(res.get("feats") or []),
        d0=(res.get("window") or ["—", "—"])[0], d1=(res.get("window") or ["—", "—"])[1],
        latest=_latest(),
    )
    os.makedirs(WEBP, exist_ok=True)
    open(OUTHTML, "w", encoding="utf-8").write(html)
    print("[tplus-gate] 证据页 %s" % OUTHTML)


if __name__ == "__main__":
    render(_load(MAIN_JSON) or {})
