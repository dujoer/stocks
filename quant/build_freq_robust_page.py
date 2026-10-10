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
    # 频率全景（edge 符号轨迹）
    html.append("<div class='note'><b>edge 符号轨迹</b>（同一档在不同采样频率下的方向）：<br>")
    for t in d["tiers"]:
        tr = " → ".join(
            ("%+0.3f" % by_tier.get(t["tier"], {}).get(st, {}).get("edge", 0.0))
            for st in steps)
        html.append("　%s：%s pp<br>" % (t["tier"], tr))
    html.append("</div></div>")
    return "".join(html)


def main():
    blocks = [b for b in (pool_block("_freq_robust_3yl.json"),
                          pool_block("_freq_robust_rev.json")) if b]
    # 汇总
    n_ok = 0
    all_tiers = 0
    data = {}
    for fn in ("_freq_robust_3yl.json", "_freq_robust_rev.json"):
        p = os.path.join(Q, fn)
        if os.path.exists(p):
            d = json.load(open(p, encoding="utf-8"))
            data[fn] = d
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

    d3 = data.get("_freq_robust_3yl.json")
    dr = data.get("_freq_robust_rev.json")
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
    if obs:
        verdict.append(
            "<p>· <b>三连阴「%s」</b>（生产主推）：edge 在 %+.3f ~ %+.3fpp 之间来回跳，"
            "符号翻转 <b>%d 次</b>（step %s）—— 这种 edge 不是「弱」，是<b>不存在</b>。</p>"
            % (obs["label"].split("（")[0], obs["edge_min"], obs["edge_max"],
               obs["flips"], " / ".join(map(str, obs["flip_at"]))))
    if rB:
        extra = ""
        if b5 and b5.get("edge") is not None:
            extra = ("　（生产主口径 step5 曾报 edge %+.3fpp、R3 %.1f%% 看着能用）"
                     % (b5["edge"], b5.get("r3") or 0))
        verdict.append(
            "<p>· <b>底部反转 B 档</b>：符号翻转 <b>%d 次</b>（step %s），"
            "edge 区间 %+.3f ~ %+.3fpp%s。</p>"
            % (rB["flips"], " / ".join(map(str, rB["flip_at"])),
               rB["edge_min"], rB["edge_max"], extra))
    if rA and rA["flips"] == 0 and rA["edge_max"] <= 0:
        verdict.append(
            "<p>· 唯一「符号一致」的是<b>反转 A 档 —— 但它在所有频率下都为负</b>"
            "（%+.3f ~ %+.3fpp）：这是<b>稳定的负贡献</b>，比不稳定更值得警惕"
            "（每开一单都在漏钱）。</p>" % (rA["edge_min"], rA["edge_max"]))
    verdict_html = "".join(verdict) or "<p>（证据不足，未生成结论）</p>"
    obs_traj = traj(d3, "obs") if d3 else "—"

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

<footer>本页由 quant/_freq_robust.py 重算生成（证据 JSON：_freq_robust_3yl.json / _freq_robust_rev.json）；
结论可复核、可证伪；<b>不构成投资建议</b>。</footer>
</div></body></html>"""

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    open(OUT, "w", encoding="utf-8").write(html)
    print("[ok] 频率稳健性页面 ->", OUT, "(%d 字节)" % len(html),
          "| 可判定档 %d / 通过 %d" % (all_tiers, n_ok))


if __name__ == "__main__":
    main()