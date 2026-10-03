# -*- coding: utf-8 -*-
"""
全市场横截面 · 数据底座能力展示（build_cross_section.py）
==========================================================
用户 2026-10-03 指出：「**不是全市场那无法分析最有价值的标的**」。

背景
----
原 `_datahub.py` 落地时，quotes/flow 两个维度只覆盖「事件域」
（524 / 356 只），理由是「避免重复联网」。**这个取舍是错的**：
事件域覆盖不到全市场，就**无法做横截面分位**，也就无法回答
「全市场里哪只最值得买」—— 而这正是分析的最终目的。

实测纠正（2026-10-03）
---------------------
- 腾讯 qt 快照**全市场 5207 只仅 21~24 秒**（65 批 × 80 只，节流 0.05s）
- 新浪资金流**全市场 5207 只约 59 秒**（12 并发）
→ 两者都不是瓶颈，事件域口径纯属自缚手脚。现已全部改为全市场。

本页面做什么
------------
**只验证「底座数据能力」，不构成任何推荐。** 展示在全市场 4971 只可分析域上
能做哪些横截面分析，并给出**各维度的覆盖统计**（让人知道数据有多全），
以及一个**先验固定、等权**的示例打分（明确标注：未过样本外检验，**不是选股结论**）。

⚠ 与其他池子的纪律一致：任何「最有价值标的」的说法必须先过 `_accum_oos.py`
   那套四道闸门（无未来函数 / 样本外 walk-forward / 随机对照 / 退出可兑现）。
   本页的示例打分**没有**过闸门，因此**只作为数据能力演示**，不作为买入依据。

数据源：全部来自 `quant/hub/{DATE}.json`（统一数据底座），本脚本**不联网**。
"""
from __future__ import annotations
import os, sys, json, argparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import _datahub as DH
import _nav

ROOT = os.path.dirname(HERE)
OUT_WEB = os.path.join(ROOT, "web", "cross_section")

CSS = """* { box-sizing: border-box; }
body { margin:0; font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;
  background:#f5f6f8; color:#23262b; }
.wrap { max-width:1240px; margin:0 auto; padding:26px 20px 60px; }
h1 { font-size:26px; margin:0 0 6px; }
h2 { font-size:18px; margin:0 0 10px; }
.sub { color:#6b7280; font-size:13px; line-height:1.8; margin-bottom:14px; }
.section { background:#fff; border:1px solid rgba(0,0,0,.08); border-radius:12px;
  padding:16px 18px; margin:14px 0; }
table { width:100%; border-collapse:collapse; font-size:13px; }
th,td { padding:7px 9px; border-bottom:1px solid rgba(0,0,0,.07); text-align:right; }
th:first-child,td:first-child,th.l,td.l { text-align:left; }
th { background:#fafbfc; font-weight:600; color:#5b6168; font-size:12px; white-space:nowrap; }
tbody tr:hover { background:#fafbfc; }
.warn { background:#fff4e5; border:1px solid #f0c896; border-radius:12px;
  padding:14px 16px; color:#7a4a12; font-size:13px; line-height:1.85; margin:14px 0; }
.ok { background:#eef6ff; border:1px solid #c9def5; border-radius:12px;
  padding:14px 16px; color:#1c4e80; font-size:13px; line-height:1.85; margin:14px 0; }
.muted { color:#8b9199; }
.pos { color:#a32d2d; }
.neg { color:#1a73e8; }
a { color:#1a73e8; }
.bar { display:inline-block; height:8px; background:#85b7eb; border-radius:4px; }
.arch { display:flex; flex-wrap:wrap; gap:8px; }
.arch a { background:#f5f6f8; border:1px solid rgba(0,0,0,.08); border-radius:8px;
  padding:5px 10px; font-size:12px; text-decoration:none; color:#1c4e80; }
footer { margin-top:24px; color:#9aa0a6; font-size:12px; line-height:1.8; }
"""


def _pct_rank(vals, higher=True):
    """转 0~1 横截面分位。ties 取平均位次，避免同值顺序影响结果。"""
    n = len(vals)
    if n == 0:
        return []
    order = sorted(range(n), key=lambda i: vals[i])
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and vals[order[j + 1]] == vals[order[i]]:
            j += 1
        avg = (i + j) / 2.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg / max(1, n - 1)
        i = j + 1
    return [r if higher else 1.0 - r for r in ranks]


def build(date):
    hub = DH.load_hub(date)
    if not hub:
        print("！底座缺失，请先跑 _datahub.py --date %s" % date)
        return None
    qd = (hub.get("dims") or {}).get("quotes") or {}
    fd = (hub.get("dims") or {}).get("flow") or {}
    q = qd.get("data") or {}
    f = fd.get("data") or {}
    if not q:
        print("！底座无 quotes 维度")
        return None

    # ---- 分析域：剔 ST/退市/低价/停牌（全市场口径，不做任何主观取舍）----
    def bad(v):
        nm = (v.get("name") or "").upper()
        return ("ST" in nm) or ("退" in nm)

    dom = [c for c, v in q.items()
           if not bad(v)
           and (v.get("last") or 0) >= 2.0              # 低价股噪声大
           and (v.get("turnover_rate") or 0) > 0]        # 换手 0 = 停牌
    rows = []
    for c in dom:
        vq, vf = q[c], (f.get(c) or {})
        rows.append({
            "code": c, "name": vq.get("name") or c,
            "last": vq.get("last") or 0.0,
            "chg": vq.get("change_percent") or 0.0,
            "turn": vq.get("turnover_rate") or 0.0,
            "vr": vq.get("volume_ratio") or 0.0,
            "cap": vq.get("circulating_market_cap") or 0.0,
            "pe": vq.get("pe_ratio") or 0.0,
            "pb": vq.get("pb_ratio") or 0.0,
            "h52": vq.get("high_52week") or 0.0,
            "l52": vq.get("low_52week") or 0.0,
            "mf1": vf.get("mf1") or 0.0,
            "mf5": vf.get("mf5") or 0.0,
            "mf20": vf.get("mf20") or 0.0,
        })

    # ---- 字段覆盖统计（证明数据有多全）----
    # ⚠ 上一版用「中文名 → 键名」手工映射，**算错了**（现价 44.7%、52周高低 0%）。
    #   正确做法：直接用腾讯快照的**原始键名**统计。
    #   键名：last / change_percent / circulating_market_cap / turnover_rate /
    #        volume_ratio / high_52week / low_52week / pe_ratio / pb_ratio
    cover = [
        ("现价 / 涨跌幅", ["last", "change_percent"]),
        ("流通市值", ["circulating_market_cap"]),
        ("换手率 / 量比", ["turnover_rate", "volume_ratio"]),
        ("52 周高 / 52 周低", ["high_52week", "low_52week"]),
        ("PE / PB", ["pe_ratio", "pb_ratio"]),
        ("主力资金 1 日", ["mf1"]),
        ("主力资金 5 日", ["mf5"]),
        ("主力资金 20 日", ["mf20"]),
    ]
    n_all_dom = max(1, len(rows))
    cov_rows = []
    for cn, keys in cover:
        n_ok = 0
        for c in dom:
            vq = q[c]
            if keys[0].startswith("mf"):          # 资金流在 flow 维度
                vf = f.get(c) or {}
                if all((vf.get(k) or 0) > 0 for k in keys):
                    n_ok += 1
            else:
                # 涨跌幅可为 0（平盘），算「有值」；其余要求 > 0
                if all((vq.get(k) is not None) and
                       ((vq.get(k) > 0) if k != "change_percent" else (vq.get(k) is not None))
                       for k in keys):
                    n_ok += 1
        cov_rows.append((cn, n_ok, 100.0 * n_ok / n_all_dom))

    # ---- 先验固定等权示例打分（明确非选股结论）----
    for fld, hb in (("mf20", True), ("mf5", True), ("mf1", True),
                    ("turn", True), ("vr", True), ("chg", True)):
        for r, p in zip(rows, _pct_rank([r[fld] for r in rows], hb)):
            r["r_" + fld] = p
    for r in rows:
        # 位置：距 52 周高越近越好（动量确认），但这是先验设定，不保证成立
        r["r_pos"] = (r["last"] / r["h52"]) if r["h52"] else 0.5
    for r, p in zip(rows, _pct_rank([r["r_pos"] for r in rows], True)):
        r["r_pos"] = p
    W = {"mf20": 0.25, "mf5": 0.20, "mf1": 0.10, "turn": 0.10,
         "vr": 0.10, "chg": 0.10, "pos": 0.15}
    for r in rows:
        r["rs"] = sum(W[k] * r["r_" + k] for k in W)
    rows.sort(key=lambda x: (-x["rs"], x["code"]))

    return {
        "date": date, "hub": hub, "rows": rows, "dom": dom,
        "n_all": len(q), "cov_rows": cov_rows, "W": W,
        "q_scope": qd.get("scope", ""), "f_scope": fd.get("scope", ""),
        "q_check": qd.get("date_check", ""),
    }


def render(d):
    rows = d["rows"]
    cov = d["cov_rows"]

    def cov_tr(cn, n, pct):
        w = int(round(pct))
        return ("<tr><td class='l'>" + cn + "</td><td>" + str(n) + " / "
                + str(len(d["dom"])) + "</td><td class='l'>"
                + "<span class='bar' style='width:" + str(w) + "px'></span> "
                + ("%.1f%%" % pct) + "</td></tr>")

    def top_tr(i, r):
        cls = "pos" if r["chg"] > 0 else ("neg" if r["chg"] < 0 else "")
        return ("<tr><td>{i}</td><td class='l'>{code}</td>"
                "<td class='l'><a href='https://quote.eastmoney.com/{code}.html' "
                "target='_blank'>{name}</a></td>"
                "<td>{last:.2f}</td><td class='{cls}'>{chg:+.2f}%</td>"
                "<td>{turn:.2f}</td><td>{vr:.2f}</td>"
                "<td>{mf1:.1f}亿</td><td>{mf5:.1f}亿</td><td>{mf20:.1f}亿</td>"
                "<td>{cap:.0f}亿</td><td>{rs:.3f}</td></tr>".format(
                    i=i, code=r["code"], name=r["name"], cls=cls,
                    last=r["last"], chg=r["chg"], turn=r["turn"], vr=r["vr"],
                    mf1=r["mf1"] / 1e8, mf5=r["mf5"] / 1e8, mf20=r["mf20"] / 1e8,
                    cap=r["cap"], rs=r["rs"]))

    top = "".join(top_tr(i, r) for i, r in enumerate(rows[:30], 1))
    cov_t = "".join(cov_tr(*c) for c in cov)

    # 归档入链**做进生成器**（含当期自己），否则 cross_YYYYMMDD.html 会成孤儿
    import glob as _glob
    snaps = sorted(os.path.basename(p)[6:-5]
                   for p in _glob.glob(os.path.join(OUT_WEB, "cross_2*.html")))
    arch = ("<div class='section'><h2>历史快照</h2><div class='arch'>%s</div></div>"
            % "".join("<a href='cross_%s.html'>%s</a>" % (s, s) for s in snaps)) if snaps else ""

    return """<!DOCTYPE html>
<html lang='zh-CN'><head><meta charset='UTF-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'>
<title>全市场横截面 · 数据能力</title><style>{css}</style></head><body>
<div class="wrap">
{nav}
<header><h1>全市场横截面 <span style="font-size:14px;color:#6b7280;font-weight:400">数据能力展示</span></h1>
<div class="sub">数据日 <b>{date}</b>｜全市场 <b>{n_all}</b> 只 → 可分析域 <b>{ndom}</b> 只
（剔除 ST/退市 · 股价&lt;2 元 · 停牌）｜<b>全市场抓取，非事件域抽样</b></div></header>

<div class="warn">
<b>⚠ 本页只演示「数据能力」，不构成任何买入建议。</b><br>
下面那张 Top30 表是<b>先验固定、等权</b>的示例打分，<b>没有通过样本外检验</b>，
因此<b>不是选股结论</b>。要得到可用的选股结论，必须先过四道闸门
（无未来函数 / 样本外 walk-forward / 随机对照 / 退出可兑现）。
<br>本页面<b>不联网</b>，全部数据来自统一数据底座 <code>hub/{ds}.json</code>。
</div>

<div class="ok">
<b>为什么现在能做全市场横截面（2026-10-03 修正）</b><br>
原方案 quotes/flow 只覆盖事件域（524 / 356 只），理由是「避免重复联网」——
<b>这个取舍是错的</b>：事件域覆盖不到全市场，就<b>无法做横截面分位</b>，
也就无法回答「全市场里哪只最值得买」，而这正是分析的最终目的。<br>
实测纠正：腾讯快照<b>全市场 5207 只 21 秒</b>（65 批 × 80 只）；新浪资金流
<b>全市场 5207 只 59 秒</b>（12 并发）。两者都<b>不是瓶颈</b>，事件域口径纯属自缚手脚。
<br><b>★ 日期真实性校验</b>：腾讯快照<b>不带任何日期字段</b>，隔天重跑无法自证是当日数据。
底座已用日K交叉验证 —— {check}。
</div>

<div class="section">
{related}
<h2>字段覆盖统计（可分析域 {ndom} 只）</h2>
<div class="sub" style="margin:0 0 10px">覆盖率高才谈得上「横截面分析」。</div>
<table><thead><tr><th class="l">字段</th><th>有值只数</th><th class="l">覆盖率</th></tr></thead>
<tbody>{cov}</tbody></table>
<div class="sub" style="margin:10px 0 0">
行情口径：<b>{qscope}</b>｜资金流口径：<b>{fscope}</b>
</div>
</div>

<div class="section">
<h2>示例打分 · Top30（<b style="color:#a8500a">未过样本外检验，不是选股结论</b>）</h2>
<div class="sub" style="margin:0 0 10px">
先验固定 7 因子等权（方向由经济逻辑给定，不筛不调权）：
主力资金 20 日 25% · 5 日 20% · 1 日 10% · 换手 10% · 量比 10% · 当日涨幅 10% · 距 52 周高 15%。
<b>权重未经检验，仅用于展示分位计算能力。</b>
</div>
<table><thead><tr>
<th>#</th><th class="l">代码</th><th class="l">名称</th><th>现价</th><th>涨跌</th>
<th>换手%</th><th>量比</th><th>主力1日</th><th>主力5日</th><th>主力20日</th>
<th>流通市值</th><th>评分</th>
</tr></thead><tbody>{top}</tbody></table>
</div>

{arch}
<footer>
本页由 <code>build_cross_section.py</code> 生成，数据源 <code>_datahub.py</code>（统一数据底座），
门禁 <code>_datahub_gate.py</code>。<br>
纪律：<b>宁可不选，不能乱选</b>；<b>不许编数据</b> —— 快照无日期字段，
已强制与日K交叉校验，未通过则拒绝当当日使用。
<br>数据日 {date}｜全市场口径，非抽样。
</footer>
</div></body></html>
""".format(
        css=CSS, nav=_nav.topnav(current_web_dir="cross_section", home="../../index.html"),
        date=d["date"], ds=d["date"].replace("-", ""),
        n_all=d["n_all"], ndom=len(rows),
        check=d["q_check"] or "（未执行）",
        qscope=d["q_scope"] or "—", fscope=d["f_scope"] or "—",
        cov=cov_t, top=top, arch=arch,
        related=("<div class='ok' style='margin-top:12px'><b>相关页面</b>："
                 "<a href='../cold_sector/index.html'>冷门行业榜（两年未主升）</a>"
                 " —— 用两年日K 重建行业指数识别「哪些行业两年零主升」，"
                 "仅陈述事实、不作买卖依据（策略已证伪：冷门 55.4% &lt; 热门 59.7%）。</div>"),
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    a = ap.parse_args()
    d = build(a.date)
    if not d:
        return
    os.makedirs(OUT_WEB, exist_ok=True)
    html = render(d)
    for fn in ("index.html", "cross_%s.html" % d["date"].replace("-", "")):
        p = os.path.join(OUT_WEB, fn)
        open(p, "w", encoding="utf-8").write(html)
        print("  → %s" % p)
    # 落 JSON 供审计
    jp = os.path.join(OUT_WEB, "cross_%s.json" % d["date"].replace("-", ""))
    json.dump({
        "asof": d["date"], "n_all": d["n_all"], "n_domain": len(d["rows"]),
        "q_scope": d["q_scope"], "f_scope": d["f_scope"],
        "q_date_check": d["q_check"],
        "weights": d["W"],
        "cover": [{"field": a, "n": b, "pct": c} for a, b, c in d["cov_rows"]],
        "top30": [{k: r[k] for k in ("code", "name", "last", "chg", "turn",
                                       "vr", "mf1", "mf5", "mf20", "cap", "rs")}
                  for r in d["rows"][:30]],
    }, open(jp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("  → %s" % jp)


if __name__ == "__main__":
    main()
