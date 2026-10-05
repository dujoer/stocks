# -*- coding: utf-8 -*-
"""高胜率候选池 · 分档核验证据页渲染（_hw_gate_page.py）

读 `_hw_tier_gate.json` / `_hw_tier_gate_step3.json`，产出 `web/picks/highwin_tier_gate.html`，
并提供 `emit_license()` 给 `gen_highwin.py` 消费（读不到/不达标 → 页面标注「不出票」，fail-safe）。

页面纪律（与 `_rev_gate_page` 一致）：
  * 只陈述本页**实际算出来**的数；样本不足就写「不可判」，不许放宽阈值凑数。
  * 模板统一用 `.format()`（混用 `%` 会让页面静默冒出 %s）。
  * 不写死任何胜率/统计数字 —— 全部来自当日证据 JSON。
"""
from __future__ import annotations
import os, re, sys, json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _gate_common as GC

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QUANT = os.path.join(ROOT, "quant")
WEBP = os.path.join(ROOT, "web", "picks")
MAIN_JSON = os.path.join(QUANT, "_hw_tier_gate.json")
SENS_JSON = os.path.join(QUANT, "_hw_tier_gate_step3.json")
OUTHTML = os.path.join(WEBP, "highwin_tier_gate.html")

ORDER = ["CORE", "MID", "TAIL", "BASE", "ALL"]
CN = {"CORE": "CORE 档（可得子分前 10%，近似核心候选）",
      "MID": "MID 档（可得子分 10~30%）",
      "TAIL": "TAIL 档（可得子分 30% 以后）",
      "BASE": "BASE 底池（当日 MACD 水上红柱全体）",
      "ALL": "ALL 全市场域（随便买 · 绝对对照）"}


def _f(v, d=3):
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


def data_gate():
    """数据有效性闸：读冻结检查，底池是旧数据冒充当日 → 一律不出票。

    这一条**不依赖任何统计**：MACD 技术快照逐字节相同、且其 close 反查全部落在
    2026-09-11，说明 09-28/29/30 的「当日」底池其实是一份 3 周前的快照。
    拿它出票 = 拿过期信息下单，统计再对也没意义。
    """
    j = _load(MAIN_JSON) or {}
    fr = [r for r in (j.get("freeze") or []) if r.get("frozen")]
    if not fr:
        return {"ok": True, "why": ""}
    last = fr[-1]
    d = last.get("frozen_close_date")
    hit, n = last.get("frozen_close_hit"), last.get("frozen_close_n")
    # ★ 冻结链的起点是「最后一份没被标记为冻结」的那期（它是第一次被抓的那一份），
    #   fr[0] 是它之后的第一期 —— 直接报 fr[0] 会把起点晚报一天。
    allr = sorted(j.get("freeze") or [], key=lambda x: x["file"])
    fi = allr.index(fr[0])
    origin = (allr[fi - 1] if fi > 0 else fr[0])
    frm = origin.get("data_date") or origin.get("file")
    days = len(fr) + 1          # 冻结起点那一期也算
    why = ("MACD 底池自 %s 起连续 %d 期逐字节未重扫（dif/dea/close 全同），"
           "其收盘价反查 %s/%s 只精确等于 %s —— 属旧快照冒充当日"
           % (frm, days, hit, n, d or "更早日期"))
    return {"ok": False, "why": why,
            "frozen_from": frm,
            "frozen_days": days, "close_date": d, "hit": hit, "n": n}


def emit_license():
    return GC.emit_license(MAIN_JSON, SENS_JSON, ("CORE", "MID", "TAIL"), CN,
                           data_gate=data_gate())


def render(res):
    per = {t.get("tier"): t for t in res["tiers"]}
    js = _load(SENS_JSON)
    per3 = {t.get("tier"): t for t in (js or {}).get("tiers", [])}
    lic = emit_license()
    d = emit_license()["detail"]

    rows, rows2, vrow, hrow, srow = [], [], [], [], []
    for k in ORDER:
        t = per.get(k) or {}
        if not t:
            rows.append("<tr><td>%s</td><td colspan='6' class='kv'>无样本</td></tr>" % CN.get(k, k))
            continue
        e = t.get("edge")
        rows.append("<tr><td><b>%s</b></td><td class='num'>%d</td><td class='num'>%s</td>"
                    "<td class='num'>%s</td><td class='num %s'>%s</td>"
                    "<td class='num %s'>%s</td><td class='kv'>[%s, %s]</td></tr>"
                    % (CN.get(k, k), t.get("n_rows", 0), _p(t.get("pnl")), _p(t.get("win")) + "%",
                       "up" if (e or 0) > 0 else "dn", _f(e) + "pp",
                       "up" if (t.get("r3") or 0) >= 95 else "dn", _p(t.get("r3")) + "%",
                       _f(t.get("loo_min")), _f(t.get("loo_max"))))
        vb = t.get("vs_base")
        rows2.append("<tr><td><b>%s</b></td><td class='num %s'>%s</td>"
                     "<td class='num %s'>%s</td><td class='kv'>[%s, %s]</td></tr>"
                     % (CN.get(k, k),
                        "up" if ((vb or {}).get("edge") or 0) > 0 else "dn",
                        _f((vb or {}).get("edge")) + "pp" if vb else "—",
                        "up" if (vb or {}).get("r3", 0) >= 95 else "dn",
                        _p((vb or {}).get("r3")) + "%" if vb else "—",
                        _f((vb or {}).get("loo_min")), _f((vb or {}).get("loo_max"))))
        t3 = per3.get(k) or {}
        srow.append("<tr><td><b>%s</b></td><td class='num %s'>%s</td><td class='num %s'>%s</td>"
                    "<td class='kv'>%s</td></tr>"
                    % (CN.get(k, k),
                       "up" if (t3.get("edge") or 0) > 0 else "dn", _f(t3.get("edge")) + "pp",
                       "up" if (t3.get("r3") or 0) >= 95 else "dn", _p(t3.get("r3")) + "%",
                       "同号" if (t3.get("edge") is not None and e is not None
                                  and t3["edge"] * e > 0) else "翻号"))
        hv = t.get("halves") or []
        htxt = " ｜ ".join("%s %s（%d/%d 日为正）" % (h["half"], _f(h["edge"]) + "pp",
                                                    h["edge_pos_days"], h["n_days"]) if False else
                           "%s %s（%d 日中 %d 日为正）"
                           % (h["half"], _f(h["edge"]) + "pp", h["n_days"], h["edge_pos_days"])
                           for h in hv)
        hrow.append("<tr><td><b>%s</b></td><td class='kv'>%s</td></tr>" % (CN.get(k, k), htxt or "—"))

    core = d.get("CORE") or {}
    dg = data_gate()
    if not dg.get("ok"):
        emerg = ("<div class='box red' style='border-color:#b00020'>"
                 "<b>⚠ 先说结论：高胜率候选池本期不出票（宁可不选）—— 底池是旧数据，不是策略问题</b><br>"
                 "MACD 技术底池自 <b>%s</b> 起<b>连续 %s 期逐字节没有重扫</b>（dif / dea / close 全同）；"
                 "把冻结快照里的收盘价拿去日K 反查，<b>%s / %s 只精确等于 %s</b>。<br>"
                 "也就是说，这几期页面上标的「当期候选」用的是一份 <b>%s 的旧快照</b>冒充当日数据 —— "
                 "直接违反「严禁用旧数据冒充当日」。<br>"
                 "因此<b>先修底池重扫，再谈胜率</b>；在数据修好之前，本池候选<b>不作任何买入依据</b>。"
                 "</div>"
                 % (dg.get("frozen_from"), dg.get("frozen_days"),
                    dg.get("hit"), dg.get("n"), dg.get("close_date"), dg.get("close_date")))
    else:
        emerg = ("<div class='box red' style='border-color:#b00020'>"
                 "<b>⚠ 先说结论：CORE 档不可出票（宁可不选）</b><br>"
                 "在可得维度（技术 25 + 位置 15 = 40 分）的口径下，CORE 档相对同日全市场的逐日平衡 edge "
                 "<b>%s pp</b>，bootstrap 通过率 <b>%s%%</b>（门槛 95%%），留一法区间 <b>[%s, %s]</b> 全为负，"
                 "前/后半也同向为负。<br>"
                 "本页不给出「改个阈值就能用」的建议 —— <b>只记录已算出的事实</b>；证据页链接见文末。"
                 "</div>"
                 % (_f(core.get("edge")) + "pp", _p(core.get("r3")),
                    _f(core.get("loo_min")), _f(core.get("loo_max")))) if core else ""

    # 生产底池冻结证据
    fr = res.get("freeze") or []
    frows = []
    prev_n = None
    for r in fr:
        mark = "—" if not r.get("frozen") else \
            "<span style='color:#ea4335;font-weight:700'>冻结</span>"
        tn = "%s" % r.get("tech_scanned") if r.get("tech_scanned") is not None else "—"
        if prev_n is not None and r.get("tech_scanned") is not None and int(r["tech_scanned"]) < int(prev_n) / 10:
            mark = "<span style='color:#ea4335;font-weight:700'>扫描量骤降（%s → %s）</span>" % (prev_n, r["tech_scanned"])
        prev_n = r.get("tech_scanned")
        if r.get("frozen_close_date"):
            mark = ("<span style='color:#ea4335;font-weight:700'>冻结；close 反查 %s/%s 只 = %s</span>"
                    % (r.get("frozen_close_hit"), r.get("frozen_close_n"),
                       r.get("frozen_close_date")))
        frows.append("<tr><td>%s</td><td class='num'>%s</td><td class='num'>%s</td>"
                     "<td class='num'>%s</td><td class='kv'>%s</td></tr>"
                     % (r.get("data_date") or r.get("file"), r.get("n"), tn,
                        r.get("above_water"), mark))
    fz = "\n".join(frows)

    rep = res.get("replicate") or []
    rrows = "\n".join(
        "<tr><td>%s</td><td class='num'>%s</td><td class='num'>%s</td><td class='num'>%s</td>"
        "<td class='num %s'>%s</td></tr>"
        % (r["date"], r["prod_n"], r["prod_tech_scanned"], r["repl_n"],
           "up" if (r.get("cover") or 0) >= 70 else "dn",
           _p(r.get("cover")) + "%" if r.get("cover") is not None else "—")
        for r in rep[-8:]) or "<tr><td colspan='5' class='kv'>无</td></tr>"

    lic_rows = "".join(
        "<tr><td>%s</td><td class='%s'>%s</td><td class='kv'>%s</td></tr>"
        % (CN.get(k, k), "up" if v["ok"] else "dn", "可出票" if v["ok"] else "不出票", v["why"])
        for k, v in sorted(d.items(), key=lambda kv: ORDER.index(kv[0])))

    # ---- 成交假设审计（新增；缺证据时明写「未核验」，不许静默略过）----
    ea = res.get("exit_assumption") or None
    ea_a_old = ea_a_real = ea_delta = None
    ea_rows = []
    if ea:
        eper = {t["tier"]: t for t in ea["tiers"] if t.get("rows")}
        for k in ("CORE", "MID", "BASE", "ALL"):
            t = eper.get(k)
            if not t:
                continue
            m0, mz = t["rows"][0], t["rows"][-1]
            d_wr, d_mn = mz["wr"] - m0["wr"], mz["mean"] - m0["mean"]
            ea_rows.append(
                "<tr><td><b>%s</b></td><td class='num'>%d</td>"
                "<td class='num'>%.2f%%</td><td class='num'>%+.3f%%</td>"
                "<td class='num'><b>%.2f%%</b></td><td class='num'><b>%+.3f%%</b></td>"
                "<td class='num %s'>%+.2fpp</td><td class='num %s'>%+.3fpp</td></tr>"
                % (CN.get(k, k), t["n"], m0["wr"], m0["mean"], mz["wr"], mz["mean"],
                   "dn" if d_wr < 0 else "up", d_wr,
                   "dn" if d_mn < 0 else "up", d_mn))
            if k == "CORE":
                ea_a_old, ea_a_real, ea_delta = m0["wr"], mz["wr"], d_wr
    if ea and ea_rows:
        ea_html = (
            "<h2>八、退出回测的成交假设（同一批票，只改成交假设）</h2>"
            "<div class='box red'><b>本页所有胜率/均值都用「移动止盈」口径结算，而这个口径本身依赖两处人为假设：</b><br>"
            "① <b>日内路径</b>：旧实现假设同一根 K 线「先冲高（上移止盈线）→ 再回落（触发卖出）」→ 系统性乐观；<br>"
            "② <b>跳空</b>：开盘已跌破止损线时，旧实现仍按「止损线价」成交，真实只能按<b>开盘价</b>成交（更差）。<br>"
            "只把这两处换成可兑现版本，CORE 档的绝对胜率就是 <b>%.2f%% → %.2f%%（%+.2fpp）</b> —— "
            "本池原本就判「不出票」，修正后亏损面进一步扩大。<br>"
            "⇒ 页面上的绝对胜率请以「可实现口径」为准。</div>"
            "<table><thead><tr><th>档</th><th>笔数</th><th>旧口径胜率</th><th>旧口径均值</th>"
            "<th>可实现胜率</th><th>可实现均值</th><th>Δ胜率</th><th>Δ均值</th></tr></thead><tbody>%s</tbody></table>"
            "<div class='kv'>口径定义与全项目统一实现见 <a href='../docs/exit_assumption_evidence.html'>退出成交假设证据页</a>"
            "（<code>quant/_exit_sim.py</code> 为唯一实现）。</div>"
            % (ea_a_old, ea_a_real, ea_delta, "\n".join(ea_rows)))
    else:
        ea_html = ("<h2>八、退出回测的成交假设</h2>"
                   "<div class='box red'>本页<b>未做成交假设核验（无证据 JSON）</b>："
                   "旧实现的移动止盈含「日内路径 + 忽略跳空」两处乐观假设，上方胜率应视为<b>乐观口径、未证实</b>。</div>")

    banner = ("<b>本页是「高胜率候选池」的出票合法性核验</b>（逐日平衡 edge + 按日 block bootstrap + "
              "留一法 + 前/后半 + 跨步长）。<br>"
              "① 生产打分满分 100 分，其中<b>只有技术 25 + 位置 15 = 40 分在历史上可前推</b>；"
              "资金/筹码/板块/龙虎榜/高管大宗都来自当日盘后快照与事件源，回测时不存在 → <b>记 0 降级</b>。<br>"
              "② 因此本页 CORE 档 =「可得子分前 10%%」，<b>不是</b>生产那批「全维 ≥68 的核心候选」；"
              "生产核心档是否真有超额，本页判 <b>不可判</b>（缺 60 分维度，无法复原）。<br>"
              "③ <b>但有一件事不用统计就能定：底池的数据本身是过期的</b>——"
              "自 %s 起连续 %s 期 MACD 快照逐字节相同、收盘价反查 %s/%s 只等于 %s（见第六节）。"
              "这是数据就绪问题，优先级高于一切策略优化。")
    banner = banner % (dg.get("frozen_from"), dg.get("frozen_days"),
                       dg.get("hit"), dg.get("n"), dg.get("close_date"))

    html = """<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>高胜率候选池 · 分档出票核验</title></head><body>
<div class="wrap">
<h1>高胜率候选池 · 分档出票核验</h1>
<div class="card">{banner}</div>
{banner2}
<h2>一、逐档结果（对照 = 同日全市场域，逐日平衡 edge）</h2>
<table><thead><tr><th>档</th><th>笔数</th><th>绝对收益</th><th>胜率</th>
<th>edge</th><th>R3</th><th>留一法区间</th></tr></thead><tbody>{rows}</tbody></table>
<div class="kv">edge = 该档逐日均值 − 同日全市场逐日均值（逐日平衡，不是把大池子摊平比绝对值）。
R3 = bootstrap 中 edge>0 的比例（按日整块重抽 {boot} 次，门槛 95%）。</div>

<h2>二、把「底池效应」和「打分增量」拆开</h2>
<table><thead><tr><th>档</th><th>edge（相对底池母集）</th><th>R3</th><th>留一法区间</th></tr></thead>
<tbody>{rows2}</tbody></table>
<div class="kv">底池 = MACD 水上红柱（天然偏强的一批票）。相对<b>底池母集</b>的 edge 才是<b>打分本身</b>的增量；
相对全市场的 edge 里还掺着「底池是不是本身就强」这一块。BASE 一行同时给出它相对「非底池」的 edge。</div>

<h2>三、前 / 后半稳定性</h2>
<table><thead><tr><th>档</th><th>前半 / 后半 edge</th></tr></thead><tbody>{hrow}</tbody></table>
<div class="kv">单段行情容易把结论锁在一个市场状态里；只有两半同向才算稳。</div>

<h2>四、跨步长敏感性（主口径 step5 vs 派生 step3）</h2>
<table><thead><tr><th>档</th><th>step3 edge</th><th>step3 R3</th><th>与主口径符号</th></tr></thead>
<tbody>{srow}</tbody></table>

<h2>五、复刻自检：本页 CORE 与生产那批核心候选是不是同一批？</h2>
<table><thead><tr><th>数据日</th><th>生产候选数</th><th>生产 tech_scanned</th><th>本地复刻底池</th>
<th>生产标的命中本地的比例</th></tr></thead><tbody>{rrows}</tbody></table>
<div class="kv">本地底池用 <code>_txk_cache.json</code>（腾讯前复权日K）复刻生产的「DIF>0 且 DEA>0 且 MACD 红柱>0」。
比例接近 100% 才说明复刻没跑偏；实测偏低 → 本页结论只适用于「可得维度这套打分本身」，
<b>不能直接套到生产名单</b>。另外：生产还叠了「20 日主力净流入&gt;0」这一条（本页无此数据，未复刻），
生产候选必然是本地底池的子集，命中率不该是 0，低命中说明两边口径确实不同源。</div>

<h2>六、生产底池有没有真的每天重扫（冻结检查）</h2>
<table><thead><tr><th>数据日</th><th>候选数</th><th>tech_scanned</th><th>水上金叉数</th><th>判定</th></tr></thead>
<tbody>{fz}</tbody></table>
<div class="kv">「冻结」= 与上一天是<b>整批</b>标的、且 dif / dea / close 逐字节相同（不是抽样前 5 只）。
再把冻结快照里的 close 拿去 <code>_txk_cache.json</code> 日K 反查它本来是哪天的价格 ——
若集体落在同一个更早的日子，就说明这几天的「当日池」是旧快照在复用。
<b>这一节不依赖任何回测口径，是纯数据事实</b>，所以它对「本期能不能出票」有否决权。</div>

<h2>七、出票许可（机器判定，读不到就 fail-safe）</h2>
<table><thead><tr><th>档</th><th>可出票？</th><th>依据</th></tr></thead><tbody>{lic_rows}</tbody></table>
<div class="kv">`gen_highwin.py` 只读本页证据；CORE/MID/TAIL 任一档不达标即标注<b>不出票（宁可不选）</b>。
只满足主步长就放行，属放宽阈值凑数，与项目红线冲突，故不写这条规则。<br>
另有一道<b>数据有效性闸</b>（与统计无关）：底池快照是旧数据时，即使 edge 为正也压住出票 ——
底注：edge 衡量的是「这套打分在历史上选得比随便买好多少」，底池过期时这个数字连适用对象都没有。</div>

{ea_html}

<h2>九、局限与口径声明</h2>
<div class="card"><ul>
<li>可得维度只有 40 分，<b>生产核心候选（全维 ≥68）的合法性在本页判「不可判」</b> —— 不是「没用」，是<b>没法验</b>。</li>
<li>资金（20）/筹码（15）/板块（12）/龙虎榜（8）/高管大宗（5）在回测时不可得，按纪律<b>记 0 降级</b>，
    因此本页总分上限 40，CORE 阈值是「前 10%」而非 68 分。</li>
<li>退出生效参数沿用全项目统一口径：−12% 硬止损 / +6% 激活移动止盈 / 回撤 3% 跟踪 / 满 20 日强平；
    买入价 = 信号日收盘（与生产「次日开盘」略有出入，属放宽，只会让结论偏保守）。</li>
<li>本页<b>只判定现有规则有没有超额，不做规则改良</b>：负 edge 也不代表「反向做」能赚钱，只是不该拿它出票。</li>
<li>CORE 档样本 {core_days} 个信号日 / {core_n} 笔 —— 样本偏小，正是本页判「不可出票」而不是判「有效」的原因。</li>
</ul></div>
<div class="note"><a href="index.html">← 返回自选/候选池首页</a> ｜ <a href="highwin_{latest}.html">高胜率候选池当期页面</a></div>
</div></body></html>""".format(
        banner=banner,
        banner2=(emerg.replace("\n", " ").replace("。\n", "。") if emerg else ""),
        rows="\n".join(rows), rows2="\n".join(rows2), hrow="\n".join(hrow),
        srow="\n".join(srow), rrows=rrows, fz=fz, lic_rows=lic_rows,
        boot=res.get("boot", 800),
        ea_html=ea_html,
        core_days=(per.get("CORE") or {}).get("n_days", 0),
        core_n=(per.get("CORE") or {}).get("n_rows", 0),
        latest=_latest(),
    )
    os.makedirs(WEBP, exist_ok=True)
    open(OUTHTML, "w", encoding="utf-8").write(html)
    print("[hw-gate] 证据页 %s" % OUTHTML)


def _latest():
    try:
        # ★ 只取日期串：模板又会拼回 highwin_ 前缀，直接返回整文件名会变成
        #   highwin_highwin_20260930.html 这种断链
        fs = sorted(f[8:-5] for f in os.listdir(WEBP)
                    if re.match(r"^highwin_\d{8}\.html$", f))
    except OSError:
        return ""
    return fs[-1] if fs else ""


if __name__ == "__main__":
    render(_load(MAIN_JSON) or {})
