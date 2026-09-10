# -*- coding: utf-8 -*-
"""
个股信号池 · 每日回测
----------------------
读取 quant/picks/history.json（build_picks.py 每日累积 + 多周期回填），
按「档位 × 周期」统计胜率与收益，产出 web/picks/backtest.html。

用法：python quant/backtest_picks.py
（无需参数；每日在 build_picks.py 之后运行即可，无样本时会输出"待累积"状态页）
"""
import os
import json
import glob
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(ROOT, "web")
OUT_DIR = os.path.join(WEB, "picks")
HIST = os.path.join(ROOT, "quant", "picks", "history.json")
PICKS_DATA = os.path.join(ROOT, "quant", "picks")

HOR = [("1", "次日 (T+1)"), ("3", "3 日 (T+3)"), ("5", "5 日 (T+5)")]
TRACKS = [("inst", "机构轨", "i"), ("youzi", "游资轨", "y")]
GRADES = ["A", "B", "C", "D"]


def load_json(p, default=None):
    if not os.path.exists(p):
        return default
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def esc(s):
    return (str(s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


# ---------------- 字段口径说明（悬浮提示） ----------------
TIPS = {
    "轨": "机构轨＝波段模型（持有 5~15 日，看 5/20 日资金与机构评级）；游资轨＝短线模型（持有 1~3 日，看当日资金与龙虎榜营业部）。",
    "档位": "按信号池当日总分分档：A ≥70 · B 60~70 · C 50~60 · D <50。回测用来检验高档位是否真的优于低档位。",
    "T+1": "以页面给出的进场参考价买入，第 1 个交易日收盘价计算的平均收益（(收盘 − 进场价) / 进场价）。",
    "T+3": "以进场参考价买入，第 3 个交易日收盘价计算的平均收益。机构轨理论上应优于 T+1。",
    "T+5": "以进场参考价买入，第 5 个交易日收盘价计算的平均收益。",
    "胜率": "该组内收益为正的样本数 ÷ 有效样本数。",
    "触T1": "该组内区间最高价触及目标一的样本数（同一只票在一个周期内只计一次）。",
    "触T2": "该组内区间最高价触及目标二的样本数。",
    "止损": "该组内区间最低价跌破止损位的样本数。",
    "候选数": "该期该轨输出的候选只数（已通过一票否决后剩余）。",
    "有效样本": "已回填出该周期收益的候选只数；持仓周期未满时尚未结算。",
    "结算状态": "是否已有足够的后续交易日完成回填，以及用于结算的数据日期。",
    "均涨": "该组内全部样本的平均收益（算术平均，未做等权再平衡）。",
    "总览卡": "该轨在该持有周期下的整体表现：均涨 / 样本数 / 胜率 / 触及目标与止损次数。样本极小时仅供参考。",
    "进场参考价": "信号池当日给出的进场区间中值，回测与次日回填全部以它为买入基准价。",
}


def tip_t(key):
    t = TIPS.get(key)
    return f" title='{esc(t)}'" if t else ""


def nav(cur="backtest"):
    items = [
        ("总门户", "../../index.html"), ("龙虎榜", "../lhb/lhb.html"),
        ("板块强度", "../sector/index.html"), ("高管增减持", "../exec/index.html"),
        ("大宗交易", "../block/index.html"), ("群体心理", "../psychology/index.html"),
        ("牛人追踪", "../shareholder/tracker.html"), ("数据中心", "../db/index.html"),
        ("信号池", "index.html"), ("回测", "backtest.html"),
        ("做T池", "../tplus/index.html"), ("版块总览", "../sections/index.html"),
    ]
    out = []
    for n, h in items:
        cls = " class='cur'" if n == "回测" else ""
        out.append(f"<a href='{h}'{cls}>{n}</a>")
    return "<div class='topnav'>" + "".join(out) + "</div>"


def aggregate(history):
    """返回 {track: {grade: {k: {n, ret, win, t1, t2, st}}}} 与全局合计"""
    agg = {tk: {g: {k: {"n": 0, "ret": 0.0, "win": 0, "t1": 0, "t2": 0, "st": 0}
                    for k, _ in HOR} for g in GRADES} for tk, _, _ in TRACKS}
    for h in history:
        for tk, _, _ in TRACKS:
            for p in (h.get(tk) or []):
                g = p.get("grade") or "D"
                if g not in GRADES:
                    g = "D"
                r1 = p.get("ret1")
                if r1 is None:
                    continue
                for k, _ in HOR:
                    r = p.get(f"ret{k}")
                    if r is None:
                        continue
                    a = agg[tk][g][k]
                    a["n"] += 1
                    a["ret"] += r
                    if r > 0:
                        a["win"] += 1
                    if p.get(f"hitT1_{k}"):
                        a["t1"] += 1
                    if p.get(f"hitT2_{k}"):
                        a["t2"] += 1
                    if p.get(f"hitStop_{k}"):
                        a["st"] += 1
    return agg


def aggregate_v2(history):
    """按 (track, grade, horizon) 聚合；返回 (agg, grand)"""
    agg = {}
    grand = {}
    for h in history:
        for tk, _, _ in TRACKS:
            for p in (h.get(tk) or []):
                g = p.get("grade") or "D"
                if g not in GRADES:
                    g = "D"
                for k, _ in HOR:
                    r = p.get(f"ret{k}")
                    if r is None:
                        continue
                    key = (tk, g, k)
                    a = agg.setdefault(key, {"n": 0, "ret": 0.0, "win": 0, "t1": 0, "t2": 0, "st": 0})
                    a["n"] += 1
                    a["ret"] += float(r)
                    if float(r) > 0:
                        a["win"] += 1
                    if p.get(f"hitT1_{k}"):
                        a["t1"] += 1
                    if p.get(f"hitT2_{k}"):
                        a["t2"] += 1
                    if p.get(f"hitStop_{k}"):
                        a["st"] += 1
                    gk = (tk, k)
                    gd = grand.setdefault(gk, {"n": 0, "ret": 0.0, "win": 0, "t1": 0, "t2": 0, "st": 0})
                    gd["n"] += 1
                    gd["ret"] += float(r)
                    if float(r) > 0:
                        gd["win"] += 1
                    if p.get(f"hitT1_{k}"):
                        gd["t1"] += 1
                    if p.get(f"hitT2_{k}"):
                        gd["t2"] += 1
                    if p.get(f"hitStop_{k}"):
                        gd["st"] += 1
    return agg, grand


def main():
    history = load_json(HIST, []) or []
    settled = [h for h in history if h.get("settled")]
    agg, grand = aggregate_v2(history)

    total_picks = sum(len(h.get(tk) or []) for h in history for tk, _, _ in TRACKS)
    scored = sum(grand[(tk, k)]["n"] for tk, _, _ in TRACKS for k, _ in HOR if (tk, k) in grand)

    # ---- 汇总卡 ----
    cards = []
    for tk, tname, _ in TRACKS:
        for k, kname in HOR:
            d = grand.get((tk, k))
            if not d or not d["n"]:
                cards.append(f"<div class='kbox'><div class='kt'>{tname} · {kname}</div>"
                             f"<div class='kv dim'>—</div><div class='kd'>暂无已结算样本</div></div>")
                continue
            avg = d["ret"] / d["n"]
            win = d["win"] / d["n"] * 100
            cls = "up" if avg > 0 else ("down" if avg < 0 else "")
            cards.append(
                f"<div class='kbox'{tip_t('总览卡')}><div class='kt'>{tname} · {kname}</div>"
                f"<div class='kv {cls}'{tip_t('均涨')}>{avg:+.2f}%</div>"
                f"<div class='kd'>样本 {d['n']} · <span class='tip'{tip_t('胜率')}>胜率 {win:.0f}%</span>"
                f" · <span class='tip'{tip_t('触T1')}>触T1 {d['t1']}</span>"
                f" · <span class='tip'{tip_t('止损')}>止损 {d['st']}</span></div></div>")

    # ---- 分档表 ----
    rows = []
    for tk, tname, _ in TRACKS:
        for g in GRADES:
            cells = []
            any_n = False
            for k, _ in HOR:
                a = agg.get((tk, g, k))
                if not a or not a["n"]:
                    cells.append("<td class='dim'>—</td>")
                    continue
                any_n = True
                avg = a["ret"] / a["n"]
                win = a["win"] / a["n"] * 100
                cls = "up" if avg > 0 else ("down" if avg < 0 else "")
                cells.append(
                    f"<td><b class='{cls}'>{avg:+.2f}%</b><br>"
                    f"<span class='dim tip'{tip_t('胜率')}>胜率 {win:.0f}% · n={a['n']}</span><br>"
                    f"<span class='dim tip'{tip_t('触T1')}>T1 {a['t1']}</span> / "
                    f"<span class='dim tip'{tip_t('触T2')}>T2 {a['t2']}</span> / "
                    f"<span class='dim tip'{tip_t('止损')}>止损 {a['st']}</span></td>")
            if any_n:
                rows.append(f"<tr><td><b>{tname}</b></td><td><b>{g}</b></td>" + "".join(cells) + "</tr>")

    if not rows:
        rows.append("<tr><td colspan='5' class='dim' style='text-align:center;padding:20px'>"
                    "尚无已结算样本。信号池自首期起累积，每个交易日盘后自动回填 T+1/T+3/T+5 表现，"
                    "积累 3 期后开始显示统计。</td></tr>")

    # ---- 逐期明细 ----
    det = []
    for h in reversed(history):
        for tk, tname, _ in TRACKS:
            n1 = h.get(f"{tk}_n1") or 0
            r1 = h.get(f"{tk}_ret1")
            r3 = h.get(f"{tk}_ret3")
            r5 = h.get(f"{tk}_ret5")
            st = "已结算" if h.get("settled") else "待结算"
            sd = h.get("settleDate") or "—"
            def cc(v):
                if v is None:
                    return "<td class='dim'>—</td>"
                cls = "up" if v > 0 else ("down" if v < 0 else "")
                return f"<td class='{cls}'>{v:+.2f}%</td>"
            det.append(f"<tr><td>{h.get('date')}</td><td>{tname}</td><td>{len(h.get(tk) or [])}</td>"
                       f"{cc(r1)}{cc(r3)}{cc(r5)}<td>{n1}</td><td>{st}（{sd}）</td></tr>")

    det_html = "".join(det) if det else "<tr><td colspan='8' class='dim'>暂无</td></tr>"
    t_tk = tip_t("轨")
    t_g = tip_t("档位")
    t_1 = tip_t("T+1")
    t_3 = tip_t("T+3")
    t_5 = tip_t("T+5")
    t_cnt = tip_t("候选数")
    t_s = tip_t("有效样本")
    t_st = tip_t("结算状态")

    os.makedirs(OUT_DIR, exist_ok=True)
    html = f"""<!DOCTYPE html>
<html lang='zh-CN'><head><meta charset='UTF-8'>
<meta name='viewport' content='width=device-width,initial-scale=1.0'>
<title>信号池回测 · 档位胜率与多周期表现</title>
<style>
* {{ box-sizing:border-box; }}
body {{ margin:0; background:#f5f6f8; color:#23262b;
  font-family:"PingFang SC","Microsoft YaHei","Hiragino Sans GB",sans-serif; line-height:1.7; }}
.wrap {{ max-width:1180px; margin:0 auto; padding:28px 20px 60px; }}
.topnav {{ display:flex; flex-wrap:wrap; gap:8px; margin-bottom:22px; padding-bottom:14px;
  border-bottom:1px solid #e6e9ee; }}
.topnav a {{ color:#b8893b; text-decoration:none; font-size:13px; padding:4px 12px; border-radius:20px;
  border:1px solid rgba(184,137,59,.35); }}
.topnav a.cur {{ background:#b8893b; color:#fff; border-color:#b8893b; }}
header h1 {{ font-size:26px; margin:0 0 6px; }}
header h1 span {{ background:linear-gradient(90deg,#b8893b,#8a6428); -webkit-background-clip:text;
  -webkit-text-fill-color:transparent; }}
.sub {{ color:#6b7480; font-size:13.5px; }}
.section {{ margin-top:28px; }}
.section h2 {{ font-size:19px; margin:0 0 14px; padding-left:12px; border-left:4px solid #b8893b; }}
.kgrid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:12px; }}
.kbox {{ background:#fff; border:1px solid #e6e9ee; border-radius:12px; padding:14px 16px; }}
.kt {{ font-size:12.5px; color:#6b7480; }}
.kv {{ font-size:24px; font-weight:700; margin:4px 0; }}
.kd {{ font-size:12px; color:#8a929c; }}
table {{ width:100%; border-collapse:collapse; background:#fff; font-size:13px;
  border:1px solid #e6e9ee; border-radius:10px; overflow:hidden; margin-top:10px; }}
th,td {{ padding:8px 9px; text-align:left; border-bottom:1px solid #eef1f4; }}
th {{ background:#fafbfc; color:#5a6573; font-weight:600; font-size:12.5px; }}
.up {{ color:#b8332a; }} .down {{ color:#1a9e5a; }} .dim {{ color:#9aa3ad; }}
.tip {{ cursor:help; border-bottom:1px dotted #c3cad3; }}
.note {{ background:#fffaf0; border-left:4px solid #b7791f; padding:12px 16px; border-radius:0 8px 8px 0;
  font-size:13.5px; color:#6b4f2a; margin:14px 0; }}
footer {{ margin-top:38px; padding-top:16px; border-top:1px solid #e6e9ee; font-size:12px; color:#8a929c; }}
</style></head><body><div class='wrap'>
{nav()}
<header><h1><span>信号池回测</span></h1>
<div class='sub'>按档位与持有周期统计候选股的实际表现：T+1 / T+3 / T+5 平均收益、胜率、触及目标与止损次数。</div></header>

<div class='section'><h2>总览</h2>
<div class='kgrid'>{"".join(cards)}</div>
<div class='note'><b>口径：</b>收益以页面给出的<span class='tip'{tip_t('进场参考价')}>进场参考价</span>为基准（(第 N 日收盘 − 进场价) / 进场价）；
胜率 = 收益为正的比例；「触T1 / 触T2 / 止损」统计区间内最高价触及目标一/目标二、最低价触及止损位的家数（同一只票在周期内只计一次）。
<b>样本极小，仅作模型自检，不构成任何收益承诺。</b></div></div>

<div class='section'><h2>分档表现</h2>
<table><thead><tr><th{t_tk}>轨</th><th{t_g}>档位</th><th{t_1}>次日 T+1</th><th{t_3}>3 日 T+3</th><th{t_5}>5 日 T+5</th></tr></thead>
<tbody>{"".join(rows)}</tbody></table></div>

<div class='section'><h2>逐期明细</h2>
<table><thead><tr><th>日期</th><th{t_tk}>轨</th><th{t_cnt}>候选数</th><th{t_1}>T+1</th><th{t_3}>T+3</th><th{t_5}>T+5</th><th{t_s}>有效样本</th><th{t_st}>结算状态</th></tr></thead>
<tbody>{det_html}</tbody></table></div>

<div class='note'><b>为什么必须回测：</b>信号池是规则化模型，改权重、加维度后如果不看实际结果，很容易陷入"看着合理但持续亏钱"的循环。
建议累计 <b>20 个交易日</b> 后，按本页分档胜率重新校准权重——尤其关注：A 档是否显著优于 C 档（若否，说明档位阈值失效）、
机构轨 T+5 是否优于 T+1（若否，说明"波段"定位站不住）。</div>

<footer>累计 {len(history)} 期 · 候选 {total_picks} 只 · 已结算样本 {scored // max(1, len(HOR))} 只次<br>
数据源：westock-mcp · 本页由 <code>quant/backtest_picks.py</code> 每日自动生成 · 仅供参考，不构成投资建议。</footer>
</div></body></html>"""

    out = os.path.join(OUT_DIR, "backtest.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[backtest_picks] → {out}（{len(history)} 期，已结算 {len(settled)} 期）")


if __name__ == "__main__":
    main()
