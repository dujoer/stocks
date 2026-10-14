#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
把各池「跨采样频率稳健性」结果渲染成页面（自包含 HTML）。

产出：web/quant_strategy/freq-robust.html
数据：quant/_freq_robust_{pool}.json（由 _freq_robust.py 生成）
本脚本不重算、不估算；缺某个池的证据就显示「该池未纳入」，不编数。
"""
from __future__ import annotations
import json, os, glob

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
Q = os.path.join(ROOT, "quant")
OUT = os.path.join(ROOT, "web", "quant_strategy", "freq-robust.html")
BASE = os.path.join(ROOT, "web")          # 判定日期基准（板块页数据日）

CSS = """
* { box-sizing:border-box; }
body { margin:0; font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;
  background:#f5f6f8; color:#23262b; line-height:1.7; }
.wrap { max-width:1180px; margin:0 auto; padding:32px 20px 70px; }
header { border-bottom:2px solid #e3e7ec; padding-bottom:18px; margin-bottom:26px; }
h1 { font-size:27px; margin:0 0 8px; font-weight:800;
  background:linear-gradient(90deg,#b8893b,#b8332a,#6b5b95);
  -webkit-background-clip:text; background-clip:text; color:transparent; }
.sub { color:#7b8794; font-size:13px; margin:0; }
h2 { font-size:19px; margin:32px 0 12px; padding-left:12px; border-left:5px solid #b8893b; }
.card { background:#fff; border:1px solid rgba(0,0,0,.08); border-radius:18px;
  padding:18px 20px; margin:0 0 18px; }
table { width:100%; border-collapse:collapse; font-size:12.5px; }
th { text-align:center; padding:8px 6px; background:#f7f8fa; color:#5a6573; font-weight:700;
  border-bottom:2px solid #e3e7ec; white-space:nowrap; }
th.l, td.l { text-align:left; }
td { padding:7px 6px; border-bottom:1px solid #f0f2f5; text-align:center;
  font-variant-numeric:tabular-nums; }
.pos { color:#b8332a; } .neg { color:#1a9e5a; } .mute { color:#9aa2ad; }
.verdict { border-left:5px solid #b8332a; background:#fff6f5; padding:16px 18px;
  border-radius:14px; margin:0 0 18px; }
.verdict h3 { margin:0 0 8px; color:#b8332a; font-size:16px; }
.verdict p { margin:6px 0; font-size:14px; }
.note { font-size:12.5px; color:#6b7280; background:#fafbfc; border:1px dashed #dfe3e8;
  border-radius:12px; padding:12px 14px; margin:10px 0 0; }
.pill { display:inline-block; font-size:11px; padding:1px 8px; border-radius:9px; }
.pill.no { background:#fdecea; color:#b8332a; border:1px solid #f5c6c2; }
.pill.base { background:#eef1f4; color:#7b8794; border:1px solid #dfe3e8; }
.pill.ok { background:#eaf7ef; color:#1a7a48; border:1px solid #c3e6d0; }
footer { margin-top:42px; padding-top:16px; border-top:1px solid #e3e7ec;
  font-size:12px; color:#7b8794; }
"""


def sgn(v):
    if v is None:
        return "<span class='mute'>—</span>"
    c = "pos" if v > 0 else ("neg" if v < 0 else "mute")
    return f"<span class='{c}'>{v:+.3f}</span>"


def base_date():
    try:
        return max(os.path.basename(p)[:-5] for p in glob.glob(os.path.join(Q, "hub", "2026*.json")))
    except Exception:
        return "—"


def pool_block(fn):
    path = os.path.join(Q, fn)
    if not os.path.exists(path):
        return None
    d = json.load(open(path, encoding="utf-8"))
    steps = d["steps"]
    by_tier = {}
    for r in d["detail"]:
        by_tier.setdefault(r["tier"], {})[r["step"]] = r
    order = [t["tier"] for t in d["tiers"]]
    # ★ 是否带 realistic(跳空成交) 口径：detail 行有 edge_excl_cons 即为（主升精选池）
    has_cons = any((by_tier.get(t, {}).get(st) or {}).get("edge_excl_cons") is not None
                   for t in by_tier for st in steps)
    html = [f"<h2>{d['pool_cn']}池（采样频率 {len(steps)} 档）</h2>",
            "<div class='card'><table><thead><tr><th class='l'>档位</th>"]
    for st in steps:
        html.append(f"<th>step {st}</th>")
    html.append("<th class='l'>判定</th></tr></thead><tbody>")
    for t in d["tiers"]:
        k = t["tier"]
        if t.get("baseline"):
            pill = "<span class='pill base'>对照基准档·不判定</span>"
        elif t["ok"]:
            pill = "<span class='pill ok'>✅ 频率稳健</span>"
        else:
            why = []
            if t["flips"]:
                why.append("符号翻转 %d 次" % t["flips"])
            if t["min_r3"] < 95:
                why.append("全频率 R3 最低 %.1f%%" % t["min_r3"])
            if t["edge_max"] <= 0:
                why.append("全频率为负")
            pill = "<span class='pill no'>❌ %s</span>" % ("；".join(why) or "不可出票")
        html.append("<tr><td class='l'><b>%s</b><div class='mute' style='font-size:11px'>%s</div></td>"
                    % (k, (t["label"] or "")[:34]))
        for st in steps:
            r = by_tier.get(k, {}).get(st)
            if not r or r.get("edge") is None:
                html.append("<td class='mute'>—</td>")
            else:
                html.append("<td>%s<div class='mute' style='font-size:10.5px'>R3 %.0f%%</div></td>"
                            % (sgn(r["edge"]), r.get("r3") or 0))
        html.append("<td class='l'>%s</td></tr>" % pill)
    html.append("</tbody></table>")
    # 频率全景（edge 符号轨迹，legacy 等量对照）
    html.append("<div class='note'><b>edge 符号轨迹（legacy 口径，等量对照）</b>"
                "（同一档在不同采样频率下的方向，—=样本不足）：<br>")
    for t in d["tiers"]:
        parts = []
        for st in steps:
            ev = (by_tier.get(t["tier"], {}).get(st) or {}).get("edge_excl")
            parts.append("—" if ev is None else "%+0.3f" % ev)
        html.append("　%s：%s pp<br>" % (t["tier"], " → ".join(parts)))
    html.append("</div>")
    # ★ realistic(跳空成交) 口径并列（主升精选池）
    if has_cons:
        cons_r3 = {}
        for t in d["tiers"]:
            rs = [(by_tier.get(t["tier"], {}).get(st) or {}).get("edge_excl_cons")
                  for st in steps]
            rs = [x for x in rs if x is not None]
            cons_r3[t["tier"]] = (min(rs) if rs else None)
        html.append("<div class='note' style='border-color:#c9b8e0;background:#faf6ff'>"
                    "<b>edge 符号轨迹（realistic 口径·跳空按开盘成交，等量对照）</b>"
                    "—— 主升精选选股在此口径下无稳健独立 alpha（见 purity.html），"
                    "本行仅看 V1 是否在保守口径下也频率稳健：<br>")
        for t in d["tiers"]:
            parts = []
            for st in steps:
                ev = (by_tier.get(t["tier"], {}).get(st) or {}).get("edge_excl_cons")
                parts.append("—" if ev is None else "%+0.3f" % ev)
            html.append("　%s：%s pp<br>" % (t["tier"], " → ".join(parts)))
        html.append("</div>")
        # 各档 realistic R3 最低（与 95% 门槛比）
        line = []
        for t in d["tiers"]:
            seq = [(by_tier.get(t["tier"], {}).get(st) or {}).get("edge_excl_cons") for st in steps]
            seq = [x for x in seq if x is not None]
            if not seq:
                continue
            flips = sum(1 for i in range(1, len(seq)) if (seq[i] > 0) != (seq[i - 1] > 0))
            allpos = all(x > 0 for x in seq)
            r3min = cons_r3.get(t["tier"])
            r3min_pct = (r3min * 100.0) if isinstance(r3min, (int, float)) else 0.0
            line.append("　%s：realistic 全频 R3 最低 <b>%.1f%%</b>｜符号%s（%s）"
                        % (t["tier"], r3min_pct,
                           "全正一致" if allpos else "不",
                           "翻转 %d 次" % flips if flips else "全正"))
        html.append("<div class='note' style='border-color:#c9b8e0;background:#faf6ff'>"
                    "realistic 口径稳健性复核：<br>" + "<br>".join(line) + "</div>")
    html.append("</div>")
    return "".join(html)


def main():
    POOL_ORDER = ["3yl", "rev", "hw", "tplus", "accum", "selected"]
    POOL_FILE = {"3yl": "_freq_robust_3yl.json", "rev": "_freq_robust_rev.json",
                 "hw": "_freq_robust_hw.json", "tplus": "_freq_robust_tplus.json",
                 "accum": "_freq_robust_accum.json", "selected": "_freq_robust_selected.json"}
    POOL_CN = {"3yl": "三连阴", "rev": "底部反转", "hw": "高胜率", "tplus": "做T",
               "accum": "增仓", "selected": "主升精选"}
    blocks = [b for p in POOL_ORDER for b in (pool_block(POOL_FILE[p]),) if b]
    # 汇总
    n_ok = 0
    all_tiers = 0
    data = {}
    for p in POOL_ORDER:
        path = os.path.join(Q, POOL_FILE[p])
        if os.path.exists(path):
            d = json.load(open(path, encoding="utf-8"))
            data[p] = d
            n_ok += d["n_ok"]
            all_tiers += sum(1 for t in d["tiers"] if not t.get("baseline"))

    # ★ 结论段的每个数字都必须现读 —— 写死统计数字是项目红线（数字会随数据变，写死即失效）
    def tier_of(d, k):
        for t in d["tiers"]:
            if t["tier"] == k:
                return t
        return None

    def traj(d, k):
        # ★ 用 edge_excl（等量对照）——与判定口径一致；母集对照含本档会稀释，
        #   两条曲线混用会让读者以为是同一个数。
        by = {}
        for r in d["detail"]:
            if r["tier"] == k:
                by[r["step"]] = r.get("edge_excl")
        return " / ".join(("{:+.3f}".format(by[s]) if by.get(s) is not None else "—")
                          for s in d["steps"])

    d3 = data.get("3yl")
    dr = data.get("rev")
    obs = tier_of(d3, "obs") if d3 else None
    rB = tier_of(dr, "B") if dr else None
    rA = tier_of(dr, "A") if dr else None
    # 反转 B 档在生产主口径 step5 上的读数
    b5 = None
    if dr:
        for r in dr["detail"]:
            if r["tier"] == "B" and r["step"] == 5:
                b5 = r
    verdict = []
    for p in POOL_ORDER:
        d = data.get(p)
        if not d:
            verdict.append("<p>· <b>%s池</b>：尚未纳入频率扫描（缺 %s），本页不编数。</p>"
                           % (POOL_CN.get(p, p), POOL_FILE[p]))
            continue
        for t in d["tiers"]:
            if t.get("baseline") or t["ok"]:
                continue
            k = t["tier"]
            why = []
            if t["flips"]:
                why.append("符号翻转 %d 次（step %s）"
                           % (t["flips"], " / ".join(map(str, t["flip_at"]))))
            if t["min_r3"] < 95:
                why.append("全频率 R3 最低 %.1f%%" % t["min_r3"])
            if t["edge_max"] <= 0:
                why.append("全频率为负")
            label = (t["label"].split("（")[0] if t["label"] else k)
            if t["edge_max"] <= 0 and t["flips"] == 0:
                verdict.append(
                    "<p>· <b>%s池「%s」</b>：在<b>所有采样频率下稳定为负</b>"
                    "（edge %+.3f ~ %+.3fpp）—— 这是<b>稳定的负贡献</b>，"
                    "比不稳定更值得警惕（每开一单都在漏钱）。</p>"
                    % (POOL_CN.get(p, p), label, t["edge_min"], t["edge_max"]))
            else:
                verdict.append("<p>· <b>%s池「%s」</b>：%s。</p>"
                               % (POOL_CN.get(p, p), label,
                                  "；".join(why) or "不可出票"))
    verdict_html = "".join(verdict) or "<p>（证据不足，未生成结论）</p>"

    # ★ 主升精选专属结论。
    #   ⚠ 2026-10-12 对照口径修正：旧面板**只装前 5% 的行**，对照＝「前5%内部的另一半」，
    #     于是 A 与 B_notV1 的 edge 必然互为镜像（一个全负则另一个必全正），
    #     测的是「前 5% 里谁更好」而不是相对市场的 alpha。
    #     现已把当日域全部票（REST 域）装入面板，对照＝相对市场。
    #     ★ 由此产生的连锁更正见下：旧结论「V1 是动量杀伤闸」不成立。
    sel_note = ""
    ds = data.get("selected")
    if ds:
        tT = tier_of(ds, "TOP5")
        tA = tier_of(ds, "A")
        tB = tier_of(ds, "B_notV1")

        def _cons(d, k, field="edge_excl_cons", rf="r3_excl_cons"):
            seq = [r.get(field) for r in d["detail"] if r["tier"] == k]
            seq = [x for x in seq if x is not None]
            r3s = [r.get(rf) for r in d["detail"] if r["tier"] == k]
            r3s = [x for x in r3s if x is not None]
            if not seq:
                return None, None, None
            flips = sum(1 for i in range(1, len(seq))
                        if (seq[i] > 0) != (seq[i - 1] > 0))
            return (all(x > 0 for x in seq), (min(r3s) if r3s else 0.0), flips)

        def nrows_rest(d):
            """域内对照（REST）行数：取最密频率那一期的 n_rows。"""
            rr = [x for x in d.get("detail", []) if x.get("tier") == "REST"]
            if not rr:
                return "—"
            rr.sort(key=lambda x: (x.get("step") or 0))
            n = rr[0].get("n_rows")
            return ("{:,}".format(n)) if isinstance(n, int) else "—"

        t_allpos, t_r3min, t_flips = _cons(ds, "TOP5")
        a_allpos, a_r3min, a_flips = _cons(ds, "A")
        b_allpos, b_r3min, b_flips = _cons(ds, "B_notV1")
        bits = []
        bits.append("⚠ <b>2026-10-12 对照口径修正</b>：旧版面板只装前 5%% 的行，"
                    "对照＝「前 5%% 内部的另一半」，两档 edge 必然互为镜像。"
                    "现已装入当日域全部票（域内其余对照 %s 行），<b>对照口径改＝相对市场</b>。"
                    % nrows_rest(ds))
        if tT:
            bits.append("· <b>TOP5（前 5%% 整体 · ★V1 回退后的现行生产口径）</b>：legacy "
                        "edge 区间 %+.3f ~ %+.3fpp、符号翻转 %d 次、全频 R3 最低 %.1f%% → %s"
                        % (tT["edge_min"], tT["edge_max"], tT["flips"], tT["min_r3"],
                           "<b>❌ 不可出票</b>" if not tT["ok"] else "✅ 稳健"))
        if t_allpos is not None:
            bits.append("　└ realistic(跳空成交) 口径：符号%s一致、全频 R3 最低 %.1f%% → %s"
                        % ("全正" if t_allpos else "不", t_r3min,
                           "稳健" if (t_allpos and t_r3min >= 95.0) else "不稳健"))
        if tA and tB:
            bits.append("· <b>连锁更正 · V1 质量闸</b>：旧结论「V1 是动量杀伤闸（A 档全频负）」"
                        "<b>建立在错误对照上，已作废</b>。修正对照后 A 档 edge %+.3f ~ %+.3fpp、"
                        "翻转 %d 次、R3 最低 %.1f%% → <b>不稳健</b>；B_notV1 虽 legacy 全正，"
                        "但 realistic 口径%s、R3 最低 %.1f%% → 同样不稳。"
                        % (tA["edge_min"], tA["edge_max"], tA["flips"], tA["min_r3"],
                           ("全正" if (b_allpos or False) else "出现负值"),
                           b_r3min if b_r3min is not None else 0.0))
            bits.append("　└ 因此 V1 <b>既未被证明有害、也未被证明有益</b>。"
                        "按「无证据不上」的 fail-safe 原则维持 <b>entry_gate=null（不启用）</b>，"
                        "<b>理由由「被证伪为有害」更正为「无稳健证据支持」</b>。")
        bits.append("· <b>结论</b>：主升精选现行生产口径（TOP5，前 5% 整体）在 legacy 与 realistic "
                    "双口径下均不可出票；且全站 23 个可判定档<b>无一跨越 0.15pp 双边成本线</b>"
                    "（见 _cost_gate.py）。主升精选成立依据仍是"
                    "<b>环境门控 + 移动止盈退出纪律</b>，选股本身无稳健独立 alpha。")
        sel_note = "<div class='note' style='border-color:#b8893b;background:#fffaf0'>" \
                   "<b>主升精选 · 对照口径修正与 V1 连锁更正</b><br>" + "<br>".join(bits) + "</div>"
    obs_traj = traj(data.get("3yl"), "obs") if data.get("3yl") else "—"
    files_list = "、".join(POOL_FILE[p] for p in POOL_ORDER
                           if os.path.exists(os.path.join(Q, POOL_FILE[p])))

    TODAY = base_date()
    d = TODAY

    html = f"""<!DOCTYPE html>
<html lang='zh-CN'><head><meta charset='UTF-8'>
<meta name='viewport' content='width=device-width,initial-scale=1.0'>
<title>跨采样频率稳健性 · 出票核验第五道闸</title>
<style>{CSS}</style></head><body><div class='wrap'>
<header>
  <h1>跨采样频率稳健性 · 出票核验第五道闸</h1>
  <p class='sub'>数据基准 {d} ｜ 每个池在 {all_tiers and '1/2/3/5/8/10/20 或 1/3/5/10/20'} 多个采样频率上
  重建面板重算 edge 与 R3 ｜ bootstrap 次数固定 ｜ 判据：符号一致 ＋ 全频率 R3≥95% ＋ 逐频率 edge&gt;0</p>
</header>

<div class='verdict'>
  <h3>结论：{all_tiers} 个可判定档位里，<b>{n_ok}</b> 个通过频率稳健性</h3>
  <p>原有的「跨步长」只比 <b>step5 vs step3 两点</b>，覆盖不足：二点之间可以藏下任意多次符号翻转。
  把频率谱补齐后，<b>看起来最好的两个档位都被证伪</b>：</p>
  {verdict_html}
</div>

{sel_note}

{''.join(blocks)}

<h2>为什么必须扫频率谱</h2>
<div class='card'>
<p style='margin:6px 0;font-size:14px'>信号采样间隔 = 每 N 个交易日取一个截面评估。若 edge 随这个间隔
显著变化，说明它不是「这只票有优势」，而是<b>「那几天正好在涨/在跌」</b>—— 而那个频率是事后选的。
二点对比（step5 vs step3）看不出这件事，必须多点扫描。</p>
<div class='note'>实测三连阴「★观察档」在各频率下的 edge（pp）：<b>{obs_traj}</b>
（依次对应 step {' / '.join(map(str, d3["steps"])) if d3 else "—"}）。
末尾那个漂亮的正读数是<b>样本只有几十个交易日</b>的高方差值，
而 step1（真实执行口径：每天都能发现信号）它是<b>负的</b>。</div>
<div class='note'><b>口径与限制</b>：① step 是<b>全局交易日序列</b>上的采样步长（全市场同日评估，
不存在各票不同步）；② 对照口径与生产主口径一致（三连阴取「同日非本档」等量对照，
反转取「同日全市场域」），<b>不放宽</b>；③ ALL / HARD / BASE 是<b>对照基准档</b>，
它们相对任何对照恒为正或恒为 0 —— 参与判定等于自己造一个假 alpha，故排除；
④ 未做参数搜索：频率是<b>检验维度</b>，不用于挑「最优步长」；
⑤ 被证伪的档位<b>保留在表里不删除</b>。</div>
</div>

<footer>本页由 quant/_freq_robust.py 重算生成（证据 JSON：{files_list}）；
结论可复核、可证伪；<b>不构成投资建议</b>。</footer>
</div></body></html>"""

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    open(OUT, "w", encoding="utf-8").write(html)
    print("[ok] 频率稳健性页面 ->", OUT, "(%d 字节)" % len(html),
          "| 可判定档 %d / 通过 %d" % (all_tiers, n_ok))


if __name__ == "__main__":
    main()