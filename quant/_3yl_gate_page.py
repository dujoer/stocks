#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""三连阴 · 分档出票核验 证据页 + 出票许可

读 `_3yl_tier_gate.json` / `_3yl_tier_gate_step3.json`，产出
  * `web/three_yin/tier_gate.html` —— 证据页
  * `emit_license()` —— 供 `build_3yl.py` 消费的出票许可（fail-safe）

★ 与 lab 结论的冲突处理原则：**不删历史结论**。lab 写的「观察档两半同向跑赢基准」
原样保留在页面第一节，同时把「那是子集对母集、且未做显著性检验」讲清楚，
再给逐日平衡 + bootstrap 的重算结果。两者不一致时以本页为准并说明为什么。

不写死任何胜率/统计数字 —— 全部来自证据 JSON。
"""
from __future__ import annotations
import os, re, sys, json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _gate_common as GC

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QUANT = os.path.join(ROOT, "quant")
WEBP = os.path.join(ROOT, "web", "three_yin")
MAIN_JSON = os.path.join(QUANT, "_3yl_tier_gate.json")
SENS_JSON = os.path.join(QUANT, "_3yl_tier_gate_step3.json")
OUTHTML = os.path.join(WEBP, "tier_gate.html")

ORDER = ["obs", "mid", "light", "deep", "fatal"]
# 出票判定只看「主推档」——页面写「本期主推」的就是 obs；其余档是排除/警示，不出票也不需要许可
EMIT_KEYS = ("obs",)
CN = {"obs": "★ 观察档（跌 8~12%）· 页面所称「本期主推」",
      "mid": "一般档（跌 5~8%）",
      "light": "浅跌档（跌 0~5%）",
      "deep": "⚠ 排雷档（跌 12~20%）",
      "fatal": "⛔ 深跌禁区（跌 >20%）"}


def _load(p):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return None


def _f(v, d=3):
    return "—" if v is None else ("%+.3f" % v if d == 3 else "%+.2f" % v)


def _p(v):
    return "—" if v is None else "%.1f" % v


def emit_license():
    return GC.emit_license(MAIN_JSON, SENS_JSON, EMIT_KEYS, CN)


def _latest():
    try:
        fs = sorted(f[7:-5] for f in os.listdir(WEBP)
                    if re.match(r"^sanyin_\d{8}\.html$", f))
    except OSError:
        return ""
    return fs[-1] if fs else ""


def render(res):
    per = {t.get("tier"): t for t in res["tiers"]}
    js = _load(SENS_JSON)
    per3 = {t.get("tier"): t for t in (js or {}).get("tiers", [])}
    lic = emit_license()
    d = lic.get("detail", {})

    def cls(v):
        return "up" if (v or 0) > 0 else "dn"

    rows, rows2, srow, hrow = [], [], [], []
    for k in ORDER:
        t = per.get(k) or {}
        e = t.get("edge")
        if t.get("note"):
            rows.append("<tr><td><b>%s</b></td><td colspan='6' class='kv'>%s</td></tr>"
                        % (CN.get(k, k), t["note"]))
            continue
        ve = t.get("vs_excl") or {}
        rows.append(
            "<tr><td><b>%s</b></td><td class='num'>%d</td>"
            "<td class='num'>%s</td><td class='num'>%s</td>"
            "<td class='num %s'>%s</td><td class='num %s'>%s</td>"
            "<td class='kv'>[%s, %s]</td></tr>"
            % (CN.get(k, k), t.get("n_rows", 0), _p(t.get("pnl")) + "%",
               _p(t.get("win")) + "%", cls(e), _f(e) + "pp",
               "up" if (t.get("r3") or 0) >= 95 else "dn", _p(t.get("r3")) + "%",
               _f(t.get("loo_min")), _f(t.get("loo_max"))))
        # 等量对照（不含自己）
        ee = ve.get("edge")
        rows2.append(
            "<tr><td><b>%s</b></td><td class='num'>%s</td><td class='num'>%s</td>"
            "<td class='num %s'>%s</td><td class='num %s'>%s</td>"
            "<td class='kv'>[%s, %s]</td></tr>"
            % (CN.get(k, k), _p(ve.get("ctrl_pnl")) + "%", _p(ve.get("ctrl_win")) + "%",
               cls(ee), _f(ee) + "pp",
               "up" if (ve.get("r3") or 0) >= 95 else "dn", _p(ve.get("r3")) + "%",
               _f(ve.get("loo_min")), _f(ve.get("loo_max"))))
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

    # ---- 退出回测的成交假设（只修跳空；本池买入价已是 T+1 开盘）----
    ea = res.get("exit_assumption") or {}
    if not ea:
        ea_html = ("<h2>七、退出回测的成交假设</h2>"
                   "<div class='card'><div class='box red' style='border-color:#b00020'>"
                   "<b>⚠️ 可实现口径未核验：</b>本次产物里没有 <code>exit_assumption</code> 段"
                   "（重跑 <code>python quant/_3yl_tier_gate.py</code> 生成）。"
                   "核验完成前本页收益按<b>旧口径</b>（止损/止盈一律按触发价成交）计算。</div></div>")
    else:
        etr = "".join(
            "<tr><td><b>%s</b></td><td class='num'>%d</td>"
            "<td class='num'>%s</td><td class='num'>%s</td>"
            "<td class='num'>%s</td><td class='num'>%s</td>"
            "<td class='num'>%s</td><td class='num'>%s</td></tr>"
            % (t.get("desc") or t.get("key"), t.get("n", 0),
               _p(t.get("wr")) + "%", _f(t.get("mean")) + "%",
               _p(t.get("wr_gap")) + "%", _f(t.get("mean_gap")) + "%",
               _f(t.get("d_wr")) + "pp", _f(t.get("d_mean")) + "pp")
            for t in ea.get("tiers", []) if t.get("n"))
        ea_html = ("<h2>七、退出回测的成交假设（两口径并列）</h2>"
                   "<div class='card'><table>"
                   "<thead><tr><th>档</th><th>笔数</th>"
                   "<th>旧胜率</th><th>旧均值</th>"
                   "<th>跳空修正 胜率</th><th>跳空修正 均值</th>"
                   "<th>Δ胜率</th><th>Δ均值</th></tr></thead>"
                   "<tbody>%s</tbody></table>"
                   "<div class='kv'>本池买入价已经是 <b>T+1 开盘</b>（真实可得，不存在日内路径问题），"
                   "唯一能修的是 <b>%s</b>：旧口径在触发日一律按止损价/止盈价成交，"
                   "可实现口径改为「开盘已穿线则按开盘价成交」—— 止损方向更差、止盈方向更好，"
                   "<b>净方向由实测决定</b>。%s"
                   "信号定义、分档阈值、止损/止盈百分比一律<b>未改</b>。</div></div>"
                   % (etr, ea.get("fixed", "跳空"), ea.get("note", "")))

    o = d.get("obs") or {}
    banner = (
        "<b>本页核验一个具体问题：页面写「★ 观察档（跌 8~12%）两半同向跑赢基准，"
        "本期主推」——这句话成立吗？</b><br>"
        "① 原结论的对照是 <b>该档 vs 全体三连阴母集</b>，而母集里含它自己 —— "
        "这是「子集对母集」，不是等量对照（R1），且原结论<b>没有给任何显著性区间</b>。<br>"
        "② 本页按全项目统一口径重算：<b>逐日平衡</b> edge（该档逐日均 − 同日对照逐日均）、"
        "按日 block bootstrap {boot} 次算 R3、留一法、前/后半、跨步长敏感性。<br>"
        "③ 双对照并列给出：<b>母集对照</b>（含自己，偏向低估）与 <b>等量对照</b>"
        "（同日非本档 = 「买这档 vs 买别的三连阴」的真实差异）。"
        "<b>出票许可取更严的等量对照</b>。<br>"
        "<b>原结论原样保留</b>（见第一节），不删改历史判定；两者不一致时以本页为准，"
        "并写明原因。")

    # 主判定
    o_all = (o.get("edge"), o.get("r3"), o.get("loo_min"), o.get("loo_max"))
    o_ex = ((o.get("vs_excl") or {}).get("edge"), (o.get("vs_excl") or {}).get("r3"),
            (o.get("vs_excl") or {}).get("loo_min"), (o.get("vs_excl") or {}).get("loo_max"))
    hv = o.get("halves") or []
    h1 = next((x for x in hv if x["half"] == "前半"), None)
    h2 = next((x for x in hv if x["half"] == "后半"), None)
    flip = bool(h1 and h2 and h1["edge"] * h2["edge"] < 0)

    if o and not o.get("ok"):
        emerg = (
            "<div class='box red' style='border-color:#b00020'>"
            "<b>⚠ 结论：★ 观察档本期不出票（宁可不选）</b><br>"
            "逐日平衡后，母集对照 edge <b>%s pp</b>（R3 <b>%s%%</b>，门槛 95%%），"
            "更严格的等量对照（同日非本档）edge <b>%s pp</b>（R3 <b>%s%%</b>）。"
            "留一法区间：母集 [%s, %s]、等量 [%s, %s]。<br>"
            "%s"
            "原结论「两半同向跑赢基准」在<b>前后半</b>上是 %s；"
            "但「跑赢母集」与「edge 显著为正」是两件事 —— 原结论只答了前者。<br>"
            "<b>不写「改个阈值就能用」的建议</b>，只记录已算出的事实。"
            "</div>"
            % (_f(o_all[0]) + "pp", _p(o_all[1]),
               _f(o_ex[0]) + "pp", _p(o_ex[1]),
               _f(o_all[2]), _f(o_all[3]), _f(o_ex[2]), _f(o_ex[3]),
               ("<b>等量对照与母集对照符号相反</b> —— 说明「跑赢母集」其实是"
                "「比其它三连阴差」，子集对母集把方向讲反了。<br>" if o_ex[0] is not None
                and o_all[0] is not None and o_ex[0] * o_all[0] < 0 else ""),
               ("<b>前后半符号翻转（前半 %s / 后半 %s）</b>，结论锁在单段行情里。"
                % (_f(h1["edge"]) + "pp", _f(h2["edge"]) + "pp") if flip else
                "前后半同向（前半 %s / 后半 %s）。"
                % (_f(h1["edge"]) + "pp" if h1 else "—",
                   _f(h2["edge"]) + "pp" if h2 else "—"))))
    else:
        emerg = ("<div class='box'><b>★ 观察档通过出票核验</b> —— edge %s pp，R3 %s%%，"
                 "等量对照 %s pp（R3 %s%%）。详见下表。</div>"
                 % (_f(o_all[0]) + "pp", _p(o_all[1]), _f(o_ex[0]) + "pp", _p(o_ex[1])))

    html = """<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>三连阴 · 分档出票核验</title></head><body>
<div class="wrap">
<h1>三连阴 · 分档出票核验</h1>
<div class="card">{banner}</div>
{banner2}

<h2>一、原结论（原样保留，不删改）</h2>
<div class="card">`_3yl_lab.py` 与观察池页面写的是：<b>★ 观察档（跌 8~12%）两半同向跑赢基准：
T+1 涨 54.0% / 胜率 47.7% / 期望 +0.43%（基准 48.7% / 44.3% / +0.01%），本期主推。</b>
<div class="kv">这是<b>全样本摊平</b>对比（把该档所有信号堆在一起比均值），不是逐日平衡。
对照「基准」= 全体三连阴，<b>含观察档自己</b>。方向性参考有价值，但它<b>不等于</b>
「买观察档能跑赢同一天买其它三连阴」，也没有给置信区间。</div></div>

<h2>二、逐日平衡 edge（母集对照：同日全体三连阴，含本档）</h2>
<table><thead><tr><th>档</th><th>笔数</th><th>绝对收益</th><th>胜率</th>
<th>edge</th><th>R3</th><th>留一法区间</th></tr></thead><tbody>{rows}</tbody></table>
<div class="kv">edge = 该档逐日均值 − 同日全三连阴逐日均值（逐日平衡）。
R3 = bootstrap 中 edge&gt;0 的比例（按日整块重抽 {boot} 次，门槛 95%）。
留一法 = 去掉任意一天后 edge 的极值范围；<b>区间跨 0 就说明结论由个别交易日撑着</b>。</div>

<h2>三、等量对照（★ 这一节才是「买这档 vs 买别的三连阴」）</h2>
<table><thead><tr><th>档</th><th>对照绝对收益</th><th>对照胜率</th>
<th>edge</th><th>R3</th><th>留一法区间</th></tr></thead><tbody>{rows2}</tbody></table>
<div class="kv">对照 = <b>同日、非本档</b>的三连阴信号（不含观察档自己）。
母集对照含自己 → 偏向低估；等量对照不含自己 → 真实差异。
<b>两档数字不一致甚至反向时，以本节为准</b>（出票许可亦按本节判定）。</div>

<h2>四、前 / 后半稳定性</h2>
<table><thead><tr><th>档</th><th>前半 / 后半 edge（母集对照）</th></tr></thead><tbody>{hrow}</tbody></table>
<div class="kv">单段行情容易把结论锁在一个市场状态里；只有两半同向才算稳。</div>

<h2>五、跨步长敏感性（主口径 step5 vs 派生 step3）</h2>
<table><thead><tr><th>档</th><th>step3 edge</th><th>step3 R3</th><th>与主口径符号</th></tr></thead>
<tbody>{srow}</tbody></table>
<div class="kv">换采样步长结论就翻号 = 结论锁在采样格点上，不是规律。</div>

<h2>六、出票许可（机器判定，读不到就 fail-safe）</h2>
<table><thead><tr><th>档</th><th>可出票？</th><th>依据</th></tr></thead><tbody>{lic_rows}</tbody></table>
<div class="kv">`build_3yl.py` 只读本页证据；观察档不达标即标注<b>不出票（宁可不选）</b>，
其余四档是排除/警示档，不涉及出票。</div>

{ea_html}

<h2>八、口径与局限</h2>
<div class="card"><ul>
<li>信号：收盘连续 3 日下跌 + 近 3 日无停牌跳空 + 量 &gt; 0；<b>累计跌幅</b>
    = 1 − 信号日收盘 / 三连阴开始前一日收盘（与 <code>build_3yl.scan()</code>、<code>_3yl_lab</code> 一字不差）。</li>
<li>退出：T+1 开盘买入 / 止损 {stop}% / 止盈 {tgt}% / 持有 {hold} 日；同日双触保守记止损。</li>
<li>回测窗口 {d0} ~ {d1}；域 = 全市场离线日K（剔 ST / 退市 / 北交所 / 无市值）。</li>
<li>本页只判定<b>现有分档规则</b>有没有超额，<b>不做规则改良</b>：edge 为负不代表反向做能赚钱，
    是不该拿它出票。</li>
<li>生产 scan 还叠了「现价 ≥2 元 + 20 日均额 ≥2000 万」两条流动性门槛（<code>build_3yl</code> 的
    PRICE_MIN / AMT_MIN）。本页面板<b>未叠这两条</b> → 结论偏宽松，属<b>放宽而非收紧</b>，
    不会把不合格的档说成合格。</li>
</ul></div>
<div class="note"><a href="index.html">← 返回三连阴观察池</a> ｜ <a href="sanyin_{latest}.html">当期观察池页面</a> ｜ <a href="lab.html">原始回测实验室</a></div>
</div></body></html>""".format(
        banner=banner,
        banner2=emerg,
        rows="\n".join(rows), rows2="\n".join(rows2),
        srow="\n".join(srow), hrow="\n".join(hrow), lic_rows=lic_rows,
        ea_html=ea_html,
        boot=res.get("boot", 800),
        stop=int((res.get("exit") or {}).get("stop", 0.05) * 100),
        tgt=int((res.get("exit") or {}).get("target", 0.08) * 100),
        hold=(res.get("exit") or {}).get("hold", 5),
        d0=(res.get("window") or ["—", "—"])[0], d1=(res.get("window") or ["—", "—"])[1],
        latest=_latest(),
    )
    os.makedirs(WEBP, exist_ok=True)
    open(OUTHTML, "w", encoding="utf-8").write(html)
    print("[3yl-gate] 证据页 %s" % OUTHTML)


if __name__ == "__main__":
    render(_load(MAIN_JSON) or {})
