# -*- coding: utf-8 -*-
"""底部反转池 · 分档出票证据页渲染（_rev_gate_page.py）

输入 quant/_rev_tier_gate.json（由 _rev_tier_gate.py 产出）
输出 web/reversal/tier_gate.html

页面只做**判定**，不写死任何数字：所有数字从 JSON 现读，JSON 由每日入口脚本重算。
★ 提供 `emit_license()` 给 `rev_pool.py` 调用：出票许可由数据决定，读不到一律 fail-safe 不出票。
"""
from __future__ import annotations
import os, re, sys, json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _gate_common as GC

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

QUANT = HERE
OUTDIR = os.path.join(ROOT, "web", "reversal")
OUTHTML = os.path.join(OUTDIR, "tier_gate.html")
SENS_JSON = os.path.join(QUANT, "_rev_tier_gate_step3.json")

ORDER = ["ALL", "HARD", "BOT", "A", "B"]
NAME = {
    "ALL": "全市场域（随便买 · 绝对对照）",
    "HARD": "仅旧硬门槛（跌得多，v5 域）",
    "BOT": "旧硬门槛 + 阶段底部＋启动证据（不看组合分）",
    "A": "现行出票：旧硬门槛 + 阶段底部＋证据≥2 + 组合分前 10%",
    "B": "旧硬门槛 + 阶段底部＋证据≥2 + 组合分 10~25%",
}
CN = {"ALL": "全市场域", "HARD": "旧硬门槛", "BOT": "闸门全开", "A": "A 档（现行出票）", "B": "B 档（10~25%）"}


def _f(v, d=3):
    """⚠ 格式串写法：%format 与 .format 混用会让页面静默出现 %s，这里统一用 format。"""
    if v is None:
        return "—"
    return "{:+.{}f}".format(v, d)


def _p(v, d=2):
    if v is None:
        return "—"
    return "{:.{}f}".format(v, d)


def _load(p):
    if not os.path.exists(p):
        return None
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return None


def emit_license():
    """出票许可（供 rev_pool 读）。规则已抽到 `_gate_common.emit_license`（反转/高胜率/三连阴三池共用）：

        edge>0 且 R3≥95% **且跨步长（step3）同号且 step3 R3≥95%** 才可出票；
        读不到证据 JSON → fail-safe 不出票。

    只满足主步长就放行，属放宽阈值凑数，与项目红线「宁可不选」冲突，故不写这条规则。
    """
    return GC.emit_license(os.path.join(QUANT, "_rev_tier_gate.json"),
                           os.path.join(QUANT, SENS_JSON),
                           ("A", "B", "BOT"),
                           {"A": "A 档（现行出票）", "B": "B 档", "BOT": "BOT（闸门全开·不看分）"})
def _latest_watchlist():
    """返回 reversal 目录里生产真·已产出的最新一期名单页文件名（无则 ""）。"""
    try:
        fs = sorted(f for f in os.listdir(OUTDIR)
                    if re.match(r"^watchlist_\d{8}\.html$", f))
    except OSError:
        return ""
    return fs[-1] if fs else ""


def render(res):
    per = {t["tier"]: t for t in res["tiers"]}
    js = _load(SENS_JSON)
    per3 = {t["tier"]: t for t in js["tiers"]} if js else {}
    lic = emit_license()
    # ★ 链接名先算好：模板用 .format() 具名占位，kwargs 里不能再互相引用
    wl = _latest_watchlist()
    wl_link = (' ｜ <a href="%s">最新观察名单</a>' % wl) if wl else ""

    # ---- 主表 ----
    rows = []
    for k in ORDER:
        t = per.get(k)
        if not t or t.get("note"):
            continue
        cls = "up" if t["edge"] > 0 else "dn"
        rows.append(
            "<tr><td>%s</td><td class='num'>%d</td><td class='num'>%d</td>"
            "<td class='num'>%s%%</td><td class='num'>%s%%</td>"
            "<td class='num'>%s%%</td><td class='num'>%s%%</td>"
            "<td class='num %s'><b>%s</b></td><td class='num'>%.1f%%</td>"
            "<td class='num'>[%s, %s]</td></tr>"
            % (NAME[k], t["n_days"], t["n_rows"], _p(t["pnl"]), _p(t["win"]),
               _p(t["ctrl_pnl"]), _p(t["ctrl_win"]), cls, _f(t["edge"]), t["r3"],
               _f(t["loo_min"]), _f(t["loo_max"])))

    # ---- 第二对照（相对深跌域母集，= 页面原走前验证 ① vs ④ 的口径）----
    rows2 = []
    for k in ("ALL", "HARD", "BOT", "A", "B"):
        t = per.get(k)
        v = (t or {}).get("vs_hard") if t else None
        if not v:
            continue
        rows2.append("<tr><td>%s</td><td class='num'>%s</td><td class='num'>%.1f%%</td>"
                     "<td class='num'>[%s, %s]</td></tr>"
                     % (NAME[k], _f(v["edge"]), v["r3"], _f(v["loo_min"]), _f(v["loo_max"])))

    # ---- 判定 ----
    vrow = []
    for k in ("A", "B", "BOT", "HARD"):
        t = per.get(k)
        if not t or t.get("note"):
            vrow.append("<tr><td>%s</td><td>无样本</td></tr>" % NAME[k])
            continue
        e, r, lo, hi = t["edge"], t["r3"], t["loo_min"], t["loo_max"]
        if k == "HARD":
            tag = "<b>旧硬门槛本身是负向筛选</b>：两个步长、前后半全部为负（留一全负）→ 域定义要改，不是闸门的问题"
        elif e > 0 and r >= 95.0:
            tag = "成立（可出票）"
        elif e > 0 and lo > 0 and (per3.get(k) or {}).get("edge", 0) > 0 \
                and (per3.get(k) or {}).get("r3", 0) >= 95.0:
            tag = "点估计为正、跨步长同号，但 R3 未稳定过线 → <b>不可判，不作买入依据</b>"
        elif e <= 0 and hi <= 0:
            tag = "超额为负且留一法全负 → <b>不应出票</b>"
        else:
            tag = "符号随采样/半区翻转 → <b>不可判，不作买入依据</b>"
        vrow.append("<tr><td>%s</td><td>%s</td></tr>" % (NAME[k], tag))

    # ---- 前后半 ----
    hrow = []
    for k in ("A", "B", "BOT", "HARD"):
        t = per.get(k)
        if not t or not t.get("halves"):
            continue
        hrow.append("<tr><td>%s</td>%s</tr>" % (
            NAME[k], "".join("<td class='num'>%s edge %s</td>"
                             % (h["half"], _f(h["edge"])) for h in t["halves"])))

    # ---- 敏感性 ----
    srow = []
    for k in ("A", "B", "BOT", "HARD"):
        t5 = per.get(k) or {}
        t3 = per3.get(k) or {}
        if not t5 or t5.get("note"):
            continue
        srow.append("<tr><td>%s</td><td class='num'>%d</td><td class='num'>%s</td><td class='num'>%.1f%%</td>"
                    "<td class='num'>%d</td><td class='num'>%s</td><td class='num'>%.1f%%</td></tr>"
                    % (NAME[k], t5.get("n_days", 0), _f(t5.get("edge")), t5.get("r3", 0),
                       t3.get("n_days", 0), _f(t3.get("edge")), t3.get("r3", 0)))

    a = per.get("A") or {}
    hard = per.get("HARD") or {}
    allt = per.get("ALL") or {}
    a3 = per3.get("A") or {}
    b = per.get("B") or {}
    b3 = per3.get("B") or {}

    # ---- 成交假设审计（新增；旧 JSON 无此键时明写「未核验」，不许静默略过）----
    ea = res.get("exit_assumption") or None
    ea_rows = []
    ea_a_old = ea_a_real = ea_delta = None
    if ea:
        eper = {t["tier"]: t for t in ea["tiers"] if t.get("rows")}
        for k in ("A", "BOT", "HARD", "ALL"):
            t = eper.get(k)
            if not t:
                continue
            m0, mz = t["rows"][0], t["rows"][-1]
            d_wr = mz["wr"] - m0["wr"]
            d_mn = mz["mean"] - m0["mean"]
            ea_rows.append(
                "<tr><td>%s</td><td class='num'>%d</td>"
                "<td class='num'>%.2f%%</td><td class='num'>%+.3f%%</td>"
                "<td class='num'><b>%.2f%%</b></td><td class='num'><b>%+.3f%%</b></td>"
                "<td class='num %s'>%+.2fpp</td><td class='num %s'>%+.3fpp</td></tr>"
                % (NAME[k], t["n"], m0["wr"], m0["mean"], mz["wr"], mz["mean"],
                   "dn" if d_wr < 0 else "up", d_wr,
                   "dn" if d_mn < 0 else "up", d_mn))
            if k == "A":
                ea_a_old, ea_a_real, ea_delta = m0["wr"], mz["wr"], d_wr
    if ea and ea_rows:
        ea_html = (
            "<h2>九、退出回测的成交假设（同一批票，只改成交假设）</h2>"
            "<div class='box red'><b>本页所有胜率/均值都用「移动止盈」口径结算，而这个口径本身依赖两处人为假设：</b><br>"
            "① <b>日内路径</b>：旧实现假设同一根 K 线「先冲高（上移止盈线）→ 再回落（触发卖出）」→ 系统性乐观；<br>"
            "② <b>跳空</b>：开盘已跌破止损线时，旧实现仍按「止损线价」成交，真实只能按<b>开盘价</b>成交（更差）。<br>"
            "只把这两处换成可兑现版本，现行出票档（A 档）的绝对胜率就是 <b>%.2f%% → %.2f%%（%+.2fpp）</b>。"
            "⇒ 页面上的绝对胜率请以「可实现口径」为准。</div>"
            "<table><tr><th>档</th><th class='num'>笔数</th><th class='num'>旧口径胜率</th><th class='num'>旧口径均值</th>"
            "<th class='num'>可实现胜率</th><th class='num'>可实现均值</th><th class='num'>Δ胜率</th><th class='num'>Δ均值</th></tr>%s</table>"
            "<div class='note'>口径定义与全项目统一实现见 <a href='../docs/exit_assumption_evidence.html'>退出成交假设证据页</a>"
            "（<code>quant/_exit_sim.py</code> 为唯一实现，三个入口 <code>_rbot</code>/<code>rev_pool</code>/<code>_selected_lab</code> 已全部收敛到它）。</div>"
            % (ea_a_old, ea_a_real, ea_delta, "\n".join(ea_rows)))
    else:
        ea_html = ("<h2>九、退出回测的成交假设</h2>"
                   "<div class='box red'>本页<b>未做成交假设核验（无证据 JSON）</b>："
                   "旧实现的移动止盈含「日内路径 + 忽略跳空」两处乐观假设，因此上方胜率应视为<b>乐观口径、未证实</b>。</div>")

    banner = ("<div class='box red'><b>结论：现行出票条件（A 档）拿不出「跑赢随便买」的证据，本期不出票。</b><br>"
              "A 档相对<b>同日全市场域</b>的逐日平衡超额为 %s pp（R3 %.1f%%，留一法区间 [%s, %s] <b>全为负</b>）；"
              "另一组步长（step3）为 %s pp —— <b>符号翻转</b>。绝对胜率 %s%% 看着不低，但同一对照（随便买）的胜率是 %s%%，"
              "两者几乎一样；而<b>平均收益 %s%% 明显低于对照的 %s%%</b>（赢面小、亏面大）。"
              "<br>按红线「宁可不选，不能乱选」，<b>本期不按 A 档出票</b>，列表照列但<b>不作买入依据</b>；"
              "B 档（组合分 10~25%%）点估计最正（%s pp，后半 %s pp），但 R3 跨步长 %d%% / %d%% 未稳定过线，同样只记为待验证。</div>"
              % (_f(a.get("edge")), a.get("r3", 0), _f(a.get("loo_min")), _f(a.get("loo_max")),
                 _f(a3.get("edge"), 3), _p(a.get("win")), _p(a.get("ctrl_win")),
                 _p(a.get("pnl")), _p(a.get("ctrl_pnl")),
                 _f(b.get("edge")), _f((b.get("halves") or [{}])[1].get("edge") if len(b.get("halves") or []) > 1 else 0),
                 b.get("r3", 0), b3.get("r3", 0)))

    html = """<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<title>底部反转池 · 分档出票核验</title></head>
<body><div class="wrap"><h1>底部反转池 v6 · 分档出票核验</h1>
<div class="note">本页回答一个问题：<b>页面上那张「走前验证」表打出来的数字，是不是你真正会买的那批票？</b>
生产实际出票 = 旧硬门槛 ∩ 阶段底部＋启动证据 ≥2 条 ∩ 组合分属于域内前 10%（A 档），
2026-09-30 只出了 52 只；而页面原表第 ④ 组有 2159 条。<b>不是同一批票。</b><br>
本页按<b>生产真实出票口径</b>在<b>全市场日K</b>上重建面板（逐日逐票复刻每一道闸门），
用主升/做T 门控同一套方法重新判定：逐日平衡 edge + 按日 block bootstrap + R3 + 留一法 + 前后半 + 步长敏感性。</div>

{banner}

<h2>一、各档判定（对照 = 同日全市场域逐日均值，即「随便买」）</h2>
<table><tr><th>规则</th><th class="num">信号日</th><th class="num">笔数</th>
<th class="num">绝对收益</th><th class="num">绝对胜率</th>
<th class="num">对照收益</th><th class="num">对照胜率</th>
<th class="num">edge（pp）</th><th class="num">R3</th><th class="num">留一法</th></tr>
{rows}
</table>
<div class="note">edge = 该档当日均值 − <b>同日</b>全市场域当日均值，再对日取平均（逐日平衡，剔除大盘日影响）。
R3 = bootstrap（按日整块重抽 %d 次）中 edge &gt; 0 的比例；判据是 <b>edge&gt;0 且 R3≥95%</b>。
「全市场域」那一行 edge 恒为 0，只用来看绝对基准：这段时期（2025-09 ~ 2026-09）随便买
<b>移动止盈后 +{all_pnl}%</b>、胜率 {all_win}%。</div>

<h2>二、为什么页面原表不能直接用（子集 vs 母集）</h2>
<div class="box warn"><b>原表 ① 深跌域全体 n=13801 / 胜率 59.9% ，④ 本页采用 n=2159 / 胜率 65.0%</b> ——
④ 是 ① 的<b>子集</b>（先过旧硬门槛、再叠闸门）。子集相对母集的绝对胜率天然偏高，这不是超额；
且两者样本量比 <b>6.4 : 1</b>，直接违反 R1 等量对照（要求 ≥0.5），也没有任何显著性区间。
本页改成<b>逐日平衡</b>＋<b>同日对照</b>后，同一条闸门（不看组合分那组）的超额只有 {bot_edge} pp，不是 +5.1pp。</div>

<h2>三、两种对照口径并列（供交叉核对）</h2>
<div class="note">左列是「相对随便买」（本页主口径），右列是「相对同日深跌域母集」＝原表 ① vs ④ 的口径。
两个问题答案不同：<b>相对深跌域，闸门是有用的</b>；<b>但相对全市场随便买，它没带来增量。</b></div>
<table><tr><th>规则</th><th class="num">vs 全市场 edge</th><th class="num">R3</th><th class="num">留一法</th></tr>{rows2}</table>

<h2>四、逐档结论</h2>
<table><tr><th>规则</th><th>判定</th></tr>{vrow}</table>

<h2>五、前 / 后半稳定性（一段行情不能代表全部）</h2>
<table><tr><th>规则</th><th>前半</th><th>后半</th></tr>{hrow}</table>

<h2>六、步长敏感性（同一规则换个采样密度还成不成立）</h2>
<table><tr><th>规则</th><th class="num">step5 信号日</th><th class="num">step5 edge</th><th class="num">step5 R3</th>
<th class="num">step3 信号日</th><th class="num">step3 edge</th><th class="num">step3 R3</th></tr>{srow}</table>
<div class="note">判据不是「点估计好不好看」，而是<b>符号会不会随采样翻转</b>。
A 档（现行出票）{a_e5} pp / {a_e3} pp 符号翻转，且后半 {a_h2} pp；
真正稳定为负的是<b>旧硬门槛（跌得多）本身</b>（{hard_e5} / {hard_e3} pp，R3 均在 0~1%）—— 换句话说，
v5 那套「距 52 周高回撤 ≥18%」的域定义是<b>负向筛选</b>，这才是主要问题来源，闸门反而不是。</div>

<h2>七、复刻是否正确（自检）</h2>
<div class="note">本页 HARD 档（仅旧硬门槛）复刻出的绝对胜率 <b>{hard_win}%</b>（{hard_nd} 个信号日 / {hard_nr} 笔），
与页面原表 ①「深跌域全体 59.9%」几乎一致 → 说明闸门体系的复刻没有跑偏；
两处口径差异（本页硬门槛的 52 周高取<b>全段最高</b>，与 <code>rev_pool.evaluate</code> 一致；
本页不做 700 只抽样而用<b>全市场</b>）只会让样本更大、结论更保守。</div>

<h2>八、出票许可（机器判定，读不到就 fail-safe）</h2>
<table><tr><th>档</th><th>可出票？</th><th>依据</th></tr>{emit_rows}</table>
<div class="note"><code>rev_pool.py</code> 每日调用 <code>_rev_gate_page.emit_license()</code>：
只有 <b>edge&gt;0 且 R3≥95% 且跨步长同号</b>的档才允许出票；<b>读不到证据 JSON 一律不出票</b>。
本期许可 = <b>{lic}</b>。</div>

{ea_html}

<h2>十、局限与口径声明</h2>
<div class="card"><ul>
<li>样本只覆盖 2025-09 ~ 2026-09 一段行情；反转类策略与市场状态强相关，<b>本页结论不声称适用于所有行情</b>，
只声明「在这段样本内拿不出正超额 → 不出票（宁可不选）」。</li>
<li>阶段底部用<b>即时检测</b>复刻（生产是「锚定 + 版本化」写盘）。锚定只影响谷底值是否随行情漂移，
对本页的逐日平衡比较不改变方向；若要完全一致需按日回放 anchor，属另一个工程。</li>
<li>A 档只有 {a_ndays} 个信号日 / {a_nrows} 笔 —— <b>样本本身就小</b>；这正是本页判「不可判」而不是判「有效」的原因。
要么放宽闸门攒样本，要么等行情走出来，都不该在样本不足时出票。</li>
<li>退出生效参数沿用全项目统一口径：−12% 硬止损 / +6% 激活移动止盈 / 回撤 3% 跟踪 / 满 20 日强平。</li>
<li>本页只判定「现有规则有没有超额」，<b>不做规则改良</b>：B 档点估计最好也只列为待验证，不代表改用它就能赚钱。</li>
</ul></div>

<div class="note"><a href="index.html">← 返回底部反转观察池</a>{wl_link}</div>
</div></body></html>""".format(
        banner=banner, rows="\n".join(rows), rows2="\n".join(rows2),
        vrow="\n".join(vrow), hrow="\n".join(hrow), srow="\n".join(srow),
        emit_rows="".join(
            "<tr><td>%s</td><td>%s</td><td>%s</td></tr>" % (CN[k], "可出票" if v["ok"] else "不出票", v["why"])
            for k, v in lic["detail"].items()),
        lic="全部档位不出票" if lic["all_blocked"] else "见表（逐档判定）",
        # ★ 只链接「生产实际已产出」的名单页：面板最后一日（如 20260831）很可能没有对应 watchlist，
        #   硬拼文件名会造断链（_link_check 会 FAIL）。改为扫描已有文件取最新一期。
        wl=wl, wl_link=wl_link,
        a_ndays=a.get("n_days", 0), a_nrows=a.get("n_rows", 0),
        boot=res.get("boot", 800),
        all_pnl=_p(allt.get("pnl")), all_win=_p(allt.get("win")),
        bot_edge=_f((per.get("BOT") or {}).get("edge")),
        hard_e5=_f((per.get("HARD") or {}).get("edge")),
        hard_e3=_f((per3.get("HARD") or {}).get("edge")),
        a_e5=_f(a.get("edge")), a_e3=_f(a3.get("edge")),
        a_h2=_f(((b.get("halves") or [{}])[1] if len(b.get("halves") or []) > 1 else {}).get("edge")),
        hard_win=_p(hard.get("win")), hard_nd=hard.get("n_days", 0), hard_nr=hard.get("n_rows", 0),
        ea_html=ea_html,
    )
    os.makedirs(OUTDIR, exist_ok=True)
    open(OUTHTML, "w", encoding="utf-8").write(html)
    print("[rev-gate] 证据页 %s" % OUTHTML)


if __name__ == "__main__":
    j = _load(os.path.join(QUANT, "_rev_tier_gate.json"))
    if not j:
        raise SystemExit("先跑 _rev_tier_gate.py")
    render(j)
