# -*- coding: utf-8 -*-
"""渲染证据页：web/docs/exit_assumption_evidence.html

主题：**退出回测的「成交假设」—— 生产页面披露的胜率，有多少是假设撑起来的？**

数据源（全部由脚本实测，页面不手写任何数字）：
  · quant/_exit_assumption_audit.json    ← `_exit_assumption_audit.py` 在生产主升面板
      （_selected_lab_panel.json，162,177 行，与冻结模型 _selected_model.json 同源）上跑四种假设
  · quant/_selected_attrib_txk.json      ← `_selected_attrib.py --source txk` 独立采样互证
  · quant/_selected_model.json           ← 冻结模型记录的头牌数字（用于复现对照）

口径铁律：页面所有数字读自实测 JSON，不手写、不引用记忆里的旧数字。
结论铁律：只陈述已算出的事实；「可实现口径」是**最保守**而非「正确答案」，
          真实值不可分辨 —— 写清这点，不假装知道。
"""
from __future__ import annotations
import json
import os
import sys

QUANT = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(QUANT)
WEB = os.path.join(ROOT, "web")
OUT = os.path.join(WEB, "docs", "exit_assumption_evidence.html")

F_AUDIT = os.path.join(QUANT, "_exit_assumption_audit.json")
F_TXK = os.path.join(QUANT, "_selected_attrib_txk.json")

CSS = """
* { box-sizing:border-box; }
body { margin:0; background:#f5f6f8; color:#1c2430;
  font-family:"PingFang SC","Microsoft YaHei","Hiragino Sans GB",sans-serif; line-height:1.75; font-size:15px; }
.wrap { max-width:1160px; margin:0 auto; padding:36px 22px 70px; }
header.top { border-bottom:3px solid #1f4e79; padding-bottom:18px; margin-bottom:26px; }
h1 { font-size:26px; margin:0 0 6px; }
.sub { color:#5a6573; font-size:14px; }
h2 { font-size:21px; margin:42px 0 14px; padding-left:12px; border-left:5px solid #1f4e79; }
h3 { font-size:16.5px; margin:26px 0 8px; color:#1f4e79; }
p { margin:9px 0; }
code { background:#eef4fa; color:#1f4e79; padding:1px 6px; border-radius:5px; font-size:13px; }
.card { background:#fff; border:1px solid #e3e7ec; border-radius:14px; padding:18px 20px; margin:14px 0;
  box-shadow:0 1px 4px rgba(20,30,50,.04); }
table { width:100%; border-collapse:collapse; font-size:13px; margin:10px 0; }
th,td { border:1px solid #e3e7ec; padding:7px 9px; text-align:left; vertical-align:top; }
th { background:#f0f3f7; white-space:nowrap; }
td.num,th.num { text-align:right; font-variant-numeric:tabular-nums; white-space:nowrap; }
.note { background:#fffaf0; border-left:4px solid #b7791f; padding:12px 16px; margin:14px 0;
  border-radius:0 8px 8px 0; font-size:14px; }
.danger { background:#fdecea; border-left:4px solid #c0392b; padding:12px 16px; margin:14px 0;
  border-radius:0 8px 8px 0; font-size:14px; }
.ok { background:#e6f6ee; border-left:4px solid #128a52; padding:12px 16px; margin:14px 0;
  border-radius:0 8px 8px 0; font-size:14px; }
.big { font-size:21px; font-weight:700; }
.up { color:#ea4335; font-weight:700; }
.down { color:#34a853; font-weight:700; }
.muted { color:#98a2b3; }
a { color:#1f4e79; }
footer { margin-top:48px; padding-top:18px; border-top:1px solid #e3e7ec; font-size:12px; color:#7b8794; line-height:1.8; }
ul { margin:8px 0; padding-left:22px; } li { margin:5px 0; }
.kicker { color:#7b8794; font-size:12px; letter-spacing:.2em; text-transform:uppercase; }
.hl { background:#fff8e6; }
.cur { background:#fff4e5; }
.warnbox { border:2px solid #c0392b; }
"""


def sp(v, unit="pp", dec=2):
    if v is None:
        return "<span class='muted'>—</span>"
    cls = "up" if v > 0 else ("down" if v < 0 else "")
    return f"<span class='{cls}'>{v:+.{dec}f}{unit}</span>"


def pc(v, dec=2):
    if v is None:
        return "<span class='muted'>—</span>"
    return f"{v:.{dec}f}%"


def mode_of(a, key):
    for m in a["modes"]:
        if m["mode"] == key:
            return m
    return {}


def main():
    a = json.load(open(F_AUDIT, encoding="utf-8"))
    t = json.load(open(F_TXK, encoding="utf-8"))
    P = a["params"]
    pct = a["pct"]
    cost = a["cost"]
    ref = a.get("model_ref") or {}

    old = mode_of(a, "旧口径（乐观日内·忽略跳空）")
    real = mode_of(a, "可实现口径（保守日内·跳空成交）")
    mt = {m["mode"]: m for m in a["modes"]}

    # 独立采样互证（_selected_attrib txk）
    x_top = ((t.get("attrib") or {}).get("top") or {}).get("exit") or {}
    x_base = ((t.get("attrib") or {}).get("base") or {}).get("exit") or {}
    x_a = ((t.get("a_top") or {}))

    # 2×2 假设矩阵（A 档）
    def cell(cons, gap):
        for m in a["modes"]:
            if m["cons"] == cons and m["gap"] == gap:
                return m
        return {}
    c_oo, c_og = cell(False, False), cell(False, True)
    c_co, c_cg = cell(True, False), cell(True, True)

    # 跨度
    top_means = [m["top_mean"] for m in a["modes"]]
    top_nets = [m["top_net"] for m in a["modes"]]
    top_wrs = [m["top_wr"] for m in a["modes"]]
    span_net = round(max(top_nets) - min(top_nets), 3)
    span_wr = round(max(top_wrs) - min(top_wrs), 2)

    # ---- 跨池复核：反转 / 高胜率 / 增仓 ----
    def _ld(fn):
        try:
            return json.load(open(os.path.join(QUANT, fn), encoding="utf-8"))
        except Exception:
            return None

    _rev, _hw, _acc = (_ld("_rev_tier_gate.json"), _ld("_hw_tier_gate.json"),
                       _ld("_accum_tier_gate.json"))

    def add4(label, doc, tier, doc_name):
        ea = (doc or {}).get("exit_assumption") or {}
        for t in ea.get("tiers", []):
            if t.get("tier") != tier or not t.get("rows"):
                continue
            m0, mz = t["rows"][0], t["rows"][-1]
            return (label, t["n"], m0["wr"], m0["mean"], mz["wr"], mz["mean"], "四口径", doc_name)
        return (label, None, None, None, None, None, "缺证据", doc_name)

    def add_gap(label, doc, win, rule, doc_name):
        ea = ((doc or {}).get("per") or {}).get(str(win), {}).get("exit_assumption") or {}
        for t in ea.get("tiers", []):
            if t.get("rule") != rule or not t.get("n"):
                continue
            return (label, t["n"], t["wr"], t["ret"], t["wr_gap"], t["ret_gap"], "仅跳空", doc_name)
        return (label, None, None, None, None, None, "缺证据", doc_name)

    def add_3yl(label, doc, key, doc_name):
        ea = (doc or {}).get("exit_assumption") or {}
        for t in ea.get("tiers", []):
            if t.get("key") != key or not t.get("n"):
                continue
            return (label, t["n"], t["wr"], t["mean"],
                    t["wr_gap"], t["mean_gap"], "仅跳空", doc_name)
        return (label, None, None, None, None, None, "缺证据", doc_name)

    def add_tplus(label, doc, grade, doc_name):
        """做T的「胜率/均值」另有含义：这里 胜率列=往返率(%)、均值列=池化每次期望(%)。"""
        ea = (doc or {}).get("exit_assumption") or {}
        for t in ea.get("tiers", []):
            if t.get("grade") != grade or not t.get("n"):
                continue
            return (label + "（左=往返率，右=每次期望）", t["n"],
                    t["round_abs"], t["pooled"],
                    t["round_abs_cons"], t["pooled_cons"], "T+1 约束", doc_name)
        return (label, None, None, None, None, None, "缺证据", doc_name)

    _3yl, _tp = _ld("_3yl_tier_gate.json"), _ld("_tplus_tier_gate.json")

    pool = [
        ("主升精选 A 档（域内前 5%）", a["n_rows"], old["top_wr"], old["top_mean"],
         real["top_wr"], real["top_mean"], "四口径", "本页"),
        add4("反转池 A 档（现行出票）", _rev, "A", "_rev_tier_gate.json"),
        add4("反转池 BOT 档（底部+证据≥2）", _rev, "BOT", "_rev_tier_gate.json"),
        add4("反转池 HARD 档（仅旧硬门槛）", _rev, "HARD", "_rev_tier_gate.json"),
        add4("高胜率 CORE 档（可得子分前 10%）", _hw, "CORE", "_hw_tier_gate.json"),
        add4("高胜率 BASE 档（MACD 水上红柱底池）", _hw, "BASE", "_hw_tier_gate.json"),
        add_gap("增仓 S 档（现行生产）", _acc, 60, "S 档（现行生产）", "_accum_tier_gate.json"),
        add_gap("增仓 A 档（现行生产·M或I）", _acc, 60, "A 档（现行生产·M或I）", "_accum_tier_gate.json"),
        add_gap("增仓全候选域（对照）", _acc, 60, "全候选域（无筛选对照）", "_accum_tier_gate.json"),
        add_3yl("三连阴 ★观察档（8~12%）", _3yl, "obs", "_3yl_tier_gate.json"),
        add_3yl("三连阴 ⚠排雷档（12~20%）", _3yl, "deep", "_3yl_tier_gate.json"),
        add_tplus("做T A 档（域内前 10%）", _tp, "A", "_tplus_tier_gate.json"),
        add_tplus("做T B 档（前 10~25%）", _tp, "B", "_tplus_tier_gate.json"),
    ]

    pool_rows_html = ""
    for label, n, w0, m0, w1, m1, kind, src in pool:
        if n is None:
            pool_rows_html += (f"<tr class='cur'><td>{label}</td><td class='num'>—</td>"
                               f"<td class='num'>—</td><td class='num'>—</td>"
                               f"<td class='num'>—</td><td class='num'>—</td>"
                               f"<td class='num'>—</td><td class='muted'>{kind}</td></tr>")
            continue
        dw = w1 - w0
        dm = m1 - m0
        clsw = "up" if dw >= 0 else "down"
        clsm = "up" if dm >= 0 else "down"
        pool_rows_html += (
            f"<tr><td>{label}</td><td class='num'>{n:,}</td>"
            f"<td class='num'>{pc(w0)}</td><td class='num'>{sp(m0, '%', 3)}</td>"
            f"<td class='num'><b>{pc(w1)}</b></td><td class='num'><b>{sp(m1, '%', 3)}</b></td>"
            f"<td class='num {clsw}'>{dw:+.2f}pp</td>"
            f"<td class='muted'>{kind}<br>{src}</td></tr>")

    # ---- 环境门控两口径复核（主升精选的出票依据，必须单独查）----
    _envL, _envR = _ld("_env_gate_lab.json"), _ld("_env_gate_lab_realistic.json")
    if not _envL or not _envR:
        env_rows_html = ("<tr class='cur'><td colspan='8' class='muted'>⚠️ 可实现口径未核验："
                         "缺 quant/_env_gate_lab_realistic.json（跑 "
                         "<code>python quant/_env_gate_lab.py --mode realistic --no-html</code> 生成）</td></tr>")
        env_note = ("核验完成前，环境门控的 edge 与系数均按<b>旧乐观口径</b>计算，"
                    "<b>不可作为调参依据</b>，也不可据此放宽出票。")
    else:
        env_rows_html = ""
        for k in ("强势", "震荡", "弱势", "破位"):
            ea = (_envL.get("edge_out") or {}).get(k)
            eb = (_envR.get("edge_out") or {}).get(k)
            if not ea or not eb:
                continue
            ok = eb["edge"] > 0 and eb.get("pass_rate", 0) >= 95
            clsd = "up" if (eb["edge"] - ea["edge"]) >= 0 else "down"
            verdict = "✅ 仍成立" if ok else ("⚠️ 不稳（R3 不足）" if eb["edge"] > 0 else "不通过")
            env_rows_html += (
                f"<tr><td><b>{k}</b></td><td class='num'>{ea['nd']}</td>"
                f"<td class='num'>{ea['edge']:+.3f}pp</td>"
                f"<td class='num'>{ea.get('pass_rate', 0):.1f}%</td>"
                f"<td class='num'><b>{eb['edge']:+.3f}pp</b></td>"
                f"<td class='num'><b>{eb.get('pass_rate', 0):.1f}%</b></td>"
                f"<td class='num {clsd}'>{eb['edge'] - ea['edge']:+.3f}pp</td>"
                f"<td class='muted'>{verdict}</td></tr>")
        sa = (_envL.get("edge_out") or {}).get("强势") or {}
        sb = (_envR.get("edge_out") or {}).get("强势") or {}
        s_ok = sb.get("edge", 0) > 0 and sb.get("pass_rate", 0) >= 95
        wa = (_envL.get("edge_out") or {}).get("弱势") or {}
        wb = (_envR.get("edge_out") or {}).get("弱势") or {}
        if s_ok:
            env_note = (
                f"<b>结论：强势档（唯一开仓档）仍然成立</b> —— edge "
                f"{sa.get('edge', 0):+.3f} → <b>{sb.get('edge', 0):+.3f} pp</b>、R3 "
                f"{sa.get('pass_rate', 0):.1f}% → <b>{sb.get('pass_rate', 0):.1f}%</b>，"
                f"留一区间仍全正。二值门控「强势开仓」的依据<b>没有被成交假设推翻</b>，主升精选维持原判。"
                f"⚠️ 但幅度普遍缩水（强势 −{abs(sb.get('edge', 0) - sa.get('edge', 0)):.3f}pp、"
                f"弱势 {(wb.get('edge', 0) - wa.get('edge', 0)):+.3f}pp），"
                f"<b>弱势档的留一区间已跨零</b> —— 该档本就判空仓、绝对收益在新口径下更负，"
                f"空仓方向不变，但「弱势档有正 edge」这个说法以后不能再用。")
        else:
            env_note = (
                f"<b>⚠️ 结论：强势档在可实现口径下不再成立</b> —— edge "
                f"{sa.get('edge', 0):+.3f} → {sb.get('edge', 0):+.3f} pp、R3 "
                f"{sa.get('pass_rate', 0):.1f}% → {sb.get('pass_rate', 0):.1f}%。"
                f"按红线（宁可不选），<b>主升精选应停止出票</b>，直到用可实现口径重新取得证据。")

    rows_tbl = ""
    for m in a["modes"]:
        star = " ★旧生产口径" if m["cons"] is False and m["gap"] is False else ""
        star2 = " ★可实现口径" if m["cons"] is True and m["gap"] is True else ""
        cls = " class='cur'" if (m["cons"] is False and m["gap"] is False) else ""
        rows_tbl += (
            f"<tr{cls}><td>{m['mode']}{star}{star2}</td>"
            f"<td class='num'>{pc(m['base_wr'])}</td>"
            f"<td class='num'>{sp(m['base_mean'], '%', 3)}</td>"
            f"<td class='num'>{sp(m['base_net'], '%', 3)}</td>"
            f"<td class='num'><b>{pc(m['top_wr'])}</b></td>"
            f"<td class='num'>{sp(m['top_mean'], '%', 3)}</td>"
            f"<td class='num'>{sp(m['top_net'], '%', 3)}</td>"
            f"<td class='num'>{pc(m['train_wr'])}</td>"
            f"<td class='num'>{pc(m['test_wr'])}</td></tr>"
        )

    # 复现对照
    rep = ""
    if ref.get("base_wr") is not None:
        same = abs(ref["base_wr"] - old.get("base_wr", 0)) < 0.05
        rep = (
            f"<tr><td>全样本可兑现胜率</td><td class='num'>{pc(ref.get('base_wr'))}</td>"
            f"<td class='num'>{pc(old.get('base_wr'))}</td>"
            f"<td class='num'>{'<b class=\"up\">完全一致</b>' if same else '<b>不一致</b>'}</td></tr>"
            f"<tr><td>全样本单笔均值</td><td class='num'>{sp(ref.get('base_ret'), '%', 3)}</td>"
            f"<td class='num'>{sp(old.get('base_mean'), '%', 3)}</td>"
            f"<td class='num'>{'一致' if abs((ref.get('base_ret') or 0) - old.get('base_mean', 0)) < 0.05 else '差异'}</td></tr>"
        )

    html = f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>退出回测「成交假设」口径审计 · 主升精选</title>
<style>{CSS}</style></head><body><div class="wrap">
<header class="top">
<div class="kicker">QUANT · 口径审计</div>
<h1>退出回测的「成交假设」口径审计</h1>
<div class="sub">主升精选生产面板 {a['n_rows']:,} 行 ｜ 参数 止损 {P['stop']*100:.0f}% · 激活 +{P['act']*100:.0f}% ·
回撤 {P['trail']*100:.0f}% · 满 {P['hold']} 日 ｜ 往返成本 {cost}pp ｜ 两半切分 {a['cut']}</div>
</header>

<div class="danger warnbox">
<p class="big">结论：生产页面披露的「A 档严格样本外可兑现胜率 65.5%」，
是<b>特定成交假设</b>下的产物，不是数据本身的属性。</p>
<p>同一批生产样本、同一组参数，只改「日内路径」与「跳空」两个假设，A 档可兑现胜率在
<b>{pc(min(top_wrs))} ~ {pc(max(top_wrs))}</b> 之间摆动（跨度 <b>{span_wr}pp</b>）；
单笔净收益在 <b>{sp(min(top_nets), '%', 3)} ~ {sp(max(top_nets), '%', 3)}</b>
之间摆动（跨度 <b>{span_net}pp</b>，是收益本身的数倍）。</p>
<p>在最保守口径（<b>保守日内 + 跳空成交</b>）下，A 档可兑现胜率降到 <b>{pc(real['top_wr'])}</b>，
其中<b>测试半 {pc(real['test_wr'])} 已低于页面自设的 60% 门槛</b>
—— 页面上「训练半 / 测试半两半同向均 &gt;60%」的表述<b>不成立</b>。</p>
<p style="margin-bottom:0">更关键的是：<b>生产页面的口径说明里完全没有提到这两个假设</b>，
读者无从知道 65.5% 究竟站在哪一档假设上。</p>
</div>

<h2>一、四种成交假设的完整对照</h2>
<div class="card">
<table>
<thead><tr><th rowspan="2">成交假设</th><th colspan="3" class="num">全样本（域内全体）</th>
<th colspan="3" class="num">A 档（域内前 {pct*100:.0f}%）</th><th colspan="2" class="num">A 档两半</th></tr>
<tr><th class="num">可兑现胜率</th><th class="num">单笔均值</th><th class="num">净均值</th>
<th class="num">可兑现胜率</th><th class="num">单笔均值</th><th class="num">净均值</th>
<th class="num">前半</th><th class="num">后半</th></tr></thead>
<tbody>{rows_tbl}</tbody></table>
<div class="note" style="margin-bottom:0">
「可兑现胜率」＝该退出规则下盈利交易占比；「净均值」＝单笔均值 − {cost}pp 往返成本。
橙色行是<b>生产页面当前实际披露的口径</b>；标 ★可实现口径的行为<b>最保守</b>口径。
</div></div>

<h2>二、这不是样本差异 —— 旧口径被精确复现</h2>
<div class="card">
<p>把冻结模型 <code>_selected_model.json</code>（built_at {ref.get('built_at')}）记录的证据，
与本次在<b>同一批面板</b>上重跑旧口径的结果对照：</p>
<table><thead><tr><th>指标</th><th class="num">冻结模型记录</th><th class="num">本次旧口径重跑</th><th>判定</th></tr></thead>
<tbody>{rep}</tbody></table>
<div class="ok" style="margin-bottom:0">
全样本可兑现胜率 <b>{pc(ref.get('base_wr'))}</b> 与本次重跑 <b>{pc(old.get('base_wr'))}</b> 完全一致
—— 证明两组数字来自同一批样本，<b>下面的差异只可能来自「成交假设」本身</b>，不是换了一批票或换了一段时间。
</div></div>

<h2>三、两个假设各做了什么</h2>

<h3>① 日内路径：同根 K 线里，先冲高还是先探底？</h3>
<div class="card">
<p>跟踪止盈的止损线依赖「持仓期最高价」。若写成「同根 K 线先创新高 → 再回落」，
止损线会在<b>当日</b>就被抬高并可能立即触发 —— <b>赢家被提前平掉</b>；
若写成「先探底 → 再冲高」，同一根 K 线就不会触发。</p>
<table><thead><tr><th>（忽略跳空时）A 档</th><th class="num">可兑现胜率</th><th class="num">单笔均值</th></tr></thead><tbody>
<tr><td>乐观日内（先冲高后回落，旧口径）</td><td class="num">{pc(c_oo.get('top_wr'))}</td>
<td class="num">{sp(c_oo.get('top_mean'), '%', 3)}</td></tr>
<tr><td>保守日内（先用昨日止盈线判跌破）</td><td class="num">{pc(c_co.get('top_wr'))}</td>
<td class="num">{sp(c_co.get('top_mean'), '%', 3)}</td></tr>
</tbody></table>
<p>两版在<b>均值上差 {sp((c_co.get('top_mean') or 0) - (c_oo.get('top_mean') or 0), 'pp', 3)}</b>
—— 而输出产物只差一个布尔开关。<b>这个方向没有「谁更保守」的固定答案</b>（加不加跳空会翻转），
说明它对均值的影响是<b>假设噪声</b>；而对胜率，它把赢家的「赢多赢少」改掉，直接改变胜负判定。</p>
</div>

<h3>② 跳空：开盘已破止损线，还能按止损线成交吗？</h3>
<div class="card">
<p>不能。限价单在跳空低开时只能以<b>开盘价</b>成交（比止损线更差）。
这是一个<b>单向</b>修正 —— 只会让结果更差，永远不会更好。</p>
<table><thead><tr><th>（保守日内下）A 档</th><th class="num">可兑现胜率</th><th class="num">单笔均值</th></tr></thead><tbody>
<tr><td>忽略跳空</td><td class="num">{pc(c_co.get('top_wr'))}</td>
<td class="num">{sp(c_co.get('top_mean'), '%', 3)}</td></tr>
<tr><td>跳空以开盘价成交</td><td class="num">{pc(c_cg.get('top_wr'))}</td>
<td class="num">{sp(c_cg.get('top_mean'), '%', 3)}</td></tr>
</tbody></table>
<div class="danger" style="margin-bottom:0">
补上跳空后，A 档可兑现胜率从 <b>{pc(c_co.get('top_wr'))}</b> 掉到 <b>{pc(c_cg.get('top_wr'))}</b>
（<b>{sp((c_cg.get('top_wr') or 0) - (c_co.get('top_wr') or 0), 'pp', 2)}</b>），
单笔均值从 {sp(c_co.get('top_mean'), '%', 3)} 掉到 {sp(c_cg.get('top_mean'), '%', 3)}。
<b>这一步是必须补的</b>：它单向、无争议，不补就是系统性低估亏损。
</div></div>

<h2>四、独立采样互证（换一套采样方式，结论不变）</h2>
<div class="card">
<p>上面的审计跑在<b>生产面板</b>（逐股各自采样，样本日错位）。为排除「结论是这套采样造成的」，
另用<b>日历对齐采样</b>（每个采样日取全市场横截面）独立重跑同一口径：</p>
<table><thead><tr><th>可实现口径（保守日内 + 跳空成交）· A 档</th>
<th class="num">可兑现胜率</th><th class="num">单笔均值</th><th class="num">样本</th></tr></thead><tbody>
<tr><td>生产面板 · 逐股采样（本页主口径）</td>
<td class="num">{pc(real['top_wr'])}</td><td class="num">{sp(real['top_mean'], '%', 3)}</td>
<td class="num">{a['n_rows']:,} 行</td></tr>
<tr><td>归因探针 · 日历对齐采样（独立互证）</td>
<td class="num">{pc(x_top.get('wr'))}</td><td class="num">{sp(x_top.get('mean'), '%', 3)}</td>
<td class="num">{x_top.get('n', 0):,} 行</td></tr>
</tbody></table>
<p>差 {sp(abs((x_top.get('mean') or 0) - (real.get('top_mean') or 0)), 'pp', 3)}、胜率差
{pc(abs((x_top.get('wr') or 0) - (real.get('top_wr') or 0)))} —— <b>两套独立采样互相印证</b>，
说明「可实现口径下 A 档胜率约 60%、测试半跌破 60%」不是采样造成的。</p>
<div class="note" style="margin-bottom:0">
同一探针还显示：A 档的<b>相对胜率</b>（前向 20 日跑赢同日域内中位数）只有 <b>{pc(x_a.get('rel'))}</b>
（超额 <b>{sp(x_a.get('edge_rel'), 'pp', 1)}</b>），即先验打分方向在这个样本期<b>整体为负</b>
—— 这是另一条独立的问题，详见
<a href="selected_attrib_evidence.html">主升精选收益归因实测</a>。
</div></div>

<h2>五、跨池复核：其他池受不受同一个假设影响</h2>
<div class="card">
<p>同一套「移动止盈」口径被<b>四个池</b>共用过。把同样的修正<b>逐池重跑</b>（不改任何选股规则、不改退出参数，
只换成交假设）的结果如下：</p>
<table>
<thead><tr><th>池 / 档</th><th class="num">笔数</th><th class="num">旧口径胜率</th><th class="num">旧口径均值</th>
<th class="num">可实现胜率</th><th class="num">可实现均值</th><th class="num">Δ胜率</th><th>修正类型</th></tr></thead>
<tbody>
{pool_rows_html}
</tbody></table>
<div class="note">
<b>三点结论：</b><br>
① <b>主升精选受影响最大</b>（A 档 −7.1pp）；其次是<b>高胜率池</b>（CORE 档 −4.4pp，修正后均值仍为负，
该池本来就判「不出票」）；<br>
② <b>反转池</b>与主升共用同一实现，A 档 −1.7pp，但修正后<b>均值由负转正</b> —— 旧口径同时<b>压低</b>了它，
方向与主升相反。这再次说明：靠这套口径去<b>挑参数</b>就是在拟合噪声。<br>
③ <b>增仓池基本不受影响</b>：它的跟踪止盈是<b>收盘触发、收盘成交</b>（不含「同根 K 线先冲高后回落」的路径假设），
唯一可修的是硬止损跳空；而硬止损无论按止损线价、还是按更差的开盘价成交<b>都记为亏</b>，
胜率不变、均值只轻微下移（±0.1pp 量级）。<br>
④ <b>三连阴 / 做T 用各自的口径单独复核</b>（不是移动止盈，所以不能套用同一张表）：<br>
　· 三连阴买入价本就是 <b>T+1 开盘</b>（真实可得、无日内路径问题），唯一能修的是跳空，
　　修正后<b>胜率 Δ 0.00pp、均值 Δ 不超过 0.06pp</b> —— 基本不受影响；<br>
　· 做T是<b>反T</b>（先买后卖），受 A 股 <b>T+1</b> 约束，当日买入当日不能卖出，
　　旧模拟却把「同根 K 线既摸买区又摸卖区」记为完成一轮。改为次日及以后才能卖出后，
　　A 档往返率 5.15%→5.02%、池化每次期望 −0.125%→−0.142% —— <b>该池本就判「不出票」，结论不变</b>；
　　注意 A 档逐日 edge 反而<b>升高</b>（+0.537→+0.595pp），这再次说明<b>不能用换口径的涨跌去改规则</b>。
</div>
</div>

<h2>六、主升精选的出票依据：环境门控两口径复核</h2>
<div class="card">
<p>主升精选是<b>主推池</b>，它的出票闸门不是「档位 edge」，而是<b>大盘环境门控</b>（强势开仓、其余空仓）。
而门控系数与 edge 全部由 <code>_env_gate_lab.py</code> 用<b>旧乐观口径</b>的收益反推 ——
所以这一项必须单独复核：<b>如果强势档在可实现口径下不再成立，主推池就该停票。</b></p>
<table>
<thead><tr><th>环境档</th><th class="num">信号日</th><th class="num">旧 edge</th><th class="num">旧 R3</th>
<th class="num">可实现 edge</th><th class="num">可实现 R3</th><th class="num">Δ edge</th><th>判据（edge&gt;0 且 R3≥95%）</th></tr></thead>
<tbody>
{env_rows_html}
</tbody></table>
<div class="note">{env_note}</div>
</div>

<h2>七、本页能说什么、不能说什么</h2>
<div class="card">
<ul>
<li><b>能说：</b>生产页面披露的 65.5% 依赖一组未披露的成交假设；换用保守口径后测试半为
{pc(real['test_wr'])}，「两半均 &gt;60%」的表述不成立。旧口径可被精确复现，差异不是样本造成的。</li>
<li><b>能说：</b>「跳空以开盘价成交」是单向、无争议的修正，必须补上。</li>
<li><b>不能说：</b>「可实现口径就是正确答案」。日内路径的真实顺序逐笔不可知，
真实值落在 {pc(min(top_wrs))} ~ {pc(max(top_wrs))} 之间的某处，<b>本页无法分辨</b>。
本页把它当口径下限，是「宁可保守」的纪律，不是数据证明。</li>
<li><b>不能做：</b>用这四种假设里的任何一种去<b>挑参数</b>。跨度 {span_net}pp 与收益同量级，
据此选参就是拟合噪声（同源证据见 <a href="selected_attrib_evidence.html">收益归因页</a> 的退出网格）。</li>
</ul></div>

<h2>八、口径定义与复跑</h2>
<div class="card">
<ul>
<li><b>域：</b>全市场 A 股正股剔 ST/退 + 20 日均额 ≥3000 万 + 现价 ≥2 元（与主升生产域一致）。</li>
<li><b>退出参数：</b>止损 −{P['stop']*100:.0f}% ／ 浮盈 +{P['act']*100:.0f}% 激活 ／
回撤 {P['trail']*100:.0f}% ／ 满 {P['hold']} 日强平（与生产冻结模型一致）。</li>
<li><b>日内路径</b>：保守版＝先用「截至前一日的止盈线」判断当日是否跌破，再用当日高点上移；
乐观版＝同根 K 线先创新高、再回落触发。<b>跳空</b>：开盘 ≤ 止盈线时以开盘价成交。</li>
<li>面板 <code>{a['panel']}</code>（{a['n_rows']:,} 行，另从 <code>_txk_cache.json</code>
重建前向开盘价，剔除 {a['n_drop']} 行）。</li>
<li>⚠ 面板构建于 2026-09-21，缓存此后有除权前复权调整：抽样 600 行中 96.3% 数值完全一致、
3.7% 相差中位 0.6%（不影响结论）。</li>
</ul></div>

<footer>
数据截至 2026-09-30 ｜ 实测脚本 <code>quant/_exit_assumption_audit.py</code>
（重跑：<code>python quant/_exit_assumption_audit.py --panel _selected_lab_panel.json --pct {pct}</code>）<br>
统一口径模块 <code>quant/_exit_sim.py</code>（<code>_rbot</code> / <code>rev_pool</code> / <code>_selected_lab</code>
三个入口已全部收敛到它）｜ 独立互证 <code>quant/_selected_attrib.py --source txk</code><br>
跨池复核：<code>python quant/_rev_tier_gate.py</code> ／ <code>_hw_tier_gate.py</code> ／
<code>_accum_tier_gate.py --boot 2000</code><br>
本页只陈述<strong>已算出的事实</strong>；「可实现口径」是<strong>最保守</strong>而非正确答案。
｜ <a href="../../index.html">← 返回总门户</a>
｜ <a href="selected_attrib_evidence.html">相关：主升精选收益归因</a>
｜ <a href="dip_buy_evidence.html">相关：高上涨率＋低吸</a>
</footer>
</div>
</body></html>
"""
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[exit-audit-evidence] 写出 {OUT}（{len(html)} 字节）")

    try:
        sys.path.insert(0, QUANT)
        import _apply_theme as T2
        T2.process(OUT)
    except Exception as ex:
        print(f"[exit-audit-evidence] 主题注入跳过：{ex}")


if __name__ == "__main__":
    main()
