# -*- coding: utf-8 -*-
"""全市场稳健分选股（横截面排序版）

为什么需要它
------------
`quant/pick_score.py` 的先验 12 因子模型，原先只给精选池的**候选票**打分（候选约 40 只，
来自龙虎榜 / 增减持 / 大宗的事件驱动异动票）。但该模型本质是**横截面排序器**：
候选集越小分位分辨率越低，而事件驱动异动票与「缩量回调 + 高成长 + 小市值」这个先验方向
**天然冲突** —— 实测精选池内最高稳健分仅 66.6，而全市场可达 79+。

本脚本把它用回正确用法：**在可交易域内做全市场横截面排序**。

证据（`quant/_pick_lab.py`，13,630 个样本点 / 13 个月，口径修复后重跑）
--------------------------------------------------------------------
- 「自动筛因子」严格样本外（前 60% 筛 → 后 40% 测）只有 **+0.5pp**；留一段交叉 **0/4** 段胜出
  → 筛因子这个动作不产生 alpha。
- 先验因子集（价量 5 + 基本面 7，方向由经济逻辑给定、等权、不筛不调权）：
  测试段 **+4.9pp 相对 / +1.4pp 绝对**，**6 段滚动全部为正**。
- 环境门控比选股更值钱：弱势期「随便买」绝对胜率 40.9% vs 强势期 51.1%（**差 10.1pp**）。

⚠️ 2026-09-21 修复 —— 腾讯 fqkline 的 volume **单位不统一**（科创板 sh688=股，其余=手）。
   旧口径把主板成交额低估 100 倍，导致流动性过滤几乎把主板全部误杀
   （可交易域只剩 331 只、Top 25 全是 688）。现统一走 `_tx_fetch.vol_unit`。

用法
----
    python quant/scan_stable.py --date 2026-09-18 [--top 30] [--min-amt 5000] [--no-render]

产物
----
    quant/picks/stable_{DATE}.json     完整结果（含全部域内标的）
    web/picks/stable_{DATE}.html       页面（自包含，主题/导航由 _apply_theme.py 注入）
"""
from __future__ import annotations
import os, sys, json, math, html, argparse, datetime, statistics

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pick_score as PS
import _tx_fetch as T

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QUANT = os.path.join(ROOT, "quant")
OUTDIR = os.path.join(ROOT, "web", "picks")
PICKS = os.path.join(QUANT, "picks")

MIN_BARS = 45          # 特征所需最少历史根数
DEF_MIN_AMT = 5000.0   # 20 日均额下限（万元）
DEF_MIN_PRICE = 2.0    # 低价股下限（元）
DEF_TOP = 30

FEAT_CN = {
    "vol_day": "量比不拥挤", "pullback_dry": "缩量回调", "dist_hi20": "贴近20日高",
    "ovn20": "隔夜承接", "atr_comp": "波动收敛", "grow_rev": "营收同比",
    "grow_q": "单季净利同比", "roe": "ROE", "mv_log": "小市值", "ep": "盈利收益率",
    "bp": "账面市值比", "amt20_log": "小成交额",
}
BAND_CN = {"sh688": "科创板", "sh60": "沪主板", "sz30": "创业板",
           "sz00": "深主板", "bj": "北交所"}


def _band(code):
    for k, v in BAND_CN.items():
        if code.startswith(k):
            return v
    return "其他"


def load_names():
    try:
        with open(os.path.join(QUANT, "_stock_names.json"), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def name_of(nam, code):
    return nam.get(code) or nam.get(code[2:]) or code


def _idx_of(bars, date):
    for k in range(len(bars) - 1, -1, -1):
        if bars[k]["date"] <= date:
            return k
    return None


def build_universe(cache, nam, date, min_amt=DEF_MIN_AMT, min_price=DEF_MIN_PRICE):
    """可交易域：剔除 ST/退市、停牌、历史不足、20 日均额过低、低价。"""
    drop = {"ST/退市": 0, "停牌": 0, "历史不足": 0, "流动性不足": 0, "低价": 0}
    uni, amts = [], {}
    floor = min_amt * 1e4
    for c, bars in cache.items():
        nm = name_of(nam, c)
        if ("ST" in nm.upper()) or ("退" in nm):
            drop["ST/退市"] += 1
            continue
        i = _idx_of(bars, date)
        if i is None or i < MIN_BARS:
            drop["历史不足"] += 1
            continue
        if not bars[i]["volume"] or not bars[i]["last"]:
            drop["停牌"] += 1
            continue
        a = T.amount(bars, c, i, 20)
        if a is None or a < floor:
            drop["流动性不足"] += 1
            continue
        if bars[i]["last"] < min_price:
            drop["低价"] += 1
            continue
        amts[c] = a
        uni.append(c)
    return uni, amts, drop


def scan(date, top=DEF_TOP, min_amt=DEF_MIN_AMT, min_price=DEF_MIN_PRICE):
    cache, _ = PS._load()
    nam = load_names()
    env = PS.env_state(date)
    uni, amts, drop = build_universe(cache, nam, date, min_amt, min_price)
    sc = PS.score_codes(uni, date)

    rows = []
    for c, v in sc.items():
        rk = v["rank"]
        lead = sorted(rk.items(), key=lambda kv: -kv[1])[:3]
        r = v["raw"]
        i = _idx_of(cache[c], date)
        cl = cache[c][i]["last"]
        rows.append({
            "code": c, "name": name_of(nam, c), "band": _band(c), "close": cl,
            "score": v["score"], "nFeat": v["n_feat"],
            "lead": [FEAT_CN.get(k, k) for k, _ in lead],
            "volDay": r.get("vol_day"), "distHi20": r.get("dist_hi20"),
            "atrComp": r.get("atr_comp"), "ovn20": r.get("ovn20"),
            "pullbackDry": r.get("pullback_dry"), "amt20Yi": round(amts[c] / 1e8, 2),
            "growRev": r.get("grow_rev"), "growQ": r.get("grow_q"),
            "roe": r.get("roe"), "ep": r.get("ep"), "bp": r.get("bp"),
        })
    rows.sort(key=lambda x: -x["score"])
    for n, r in enumerate(rows, 1):
        r["rank"] = n

    band_cnt = {}
    for r in rows:
        band_cnt[r["band"]] = band_cnt.get(r["band"], 0) + 1

    scores = [r["score"] for r in rows]
    deciles = []
    if scores:
        lo, hi = min(scores), max(scores)
        step = (hi - lo) / 10 or 1
        for d in range(9, -1, -1):
            a, b = lo + step * d, lo + step * (d + 1)
            cnt = sum(1 for s in scores if (a <= s < b) or (d == 9 and s >= b))
            deciles.append({"decile": 10 - d, "lo": round(a, 1), "hi": round(b, 1), "n": cnt})

    return {
        "date": date,
        "generated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "env": env,
        "universe": {"total": len(cache), "kept": len(uni), "drop": drop,
                     "band": band_cnt, "minAmtWan": min_amt, "minPrice": min_price},
        "model": {"version": (PS.load_model() or {}).get("version", "unknown"),
                  "feats": [f[0] for f in PS.ALL_FEATS],
                  "nFeat": len(PS.ALL_FEATS)},
        "stats": {"n": len(rows), "max": round(max(scores), 1) if scores else None,
                  "median": round(statistics.median(scores), 1) if scores else None,
                  "min": round(min(scores), 1) if scores else None},
        "deciles": deciles,
        "top": rows[:top],
        "rows": rows,
    }


# ------------------------------- 渲染 -------------------------------
def _fmt(v, n=1, suffix="", plus=False):
    if v is None:
        return "—"
    s = ("%+." + str(n) + "f") % v if plus else ("%." + str(n) + "f") % v
    return s + suffix


def render(res):
    D = res["date"]
    env = res["env"]
    u = res["universe"]
    st = res["stats"]
    coef = env.get("coef", 1.0)
    if coef >= 1.0:
        env_bg, env_txt = "#e7f4ec", "#1a7f4b"
    elif coef >= 0.7:
        env_bg, env_txt = "#fff5e0", "#a86a10"
    else:
        env_bg, env_txt = "#fdeaea", "#b3261e"

    trs = []
    for r in res["top"]:
        trs.append(
            "<tr><td class='rk'>{rank}</td><td class='nm'>{name}<span class='bd'>{band}</span></td>"
            "<td class='sc'>{score}</td><td class='ld'>{lead}</td>"
            "<td>{volDay}</td><td>{distHi20}</td><td>{growRev}</td><td>{growQ}</td>"
            "<td>{roe}</td><td>{amt20Yi}</td></tr>".format(
                rank=r["rank"], name=html.escape(r["name"]), band=r["band"],
                score="%.1f" % r["score"], lead=" · ".join(r["lead"]),
                volDay=_fmt(r["volDay"], 2), distHi20=_fmt(r["distHi20"], 1, "%", True),
                growRev=_fmt(r["growRev"], 1, "%", True), growQ=_fmt(r["growQ"], 1, "%", True),
                roe=_fmt(r["roe"], 1, "%"), amt20Yi=_fmt(r["amt20Yi"], 2, "亿")))

    dec_rows = "".join(
        "<tr><td>第 {d} 档</td><td>{lo} ~ {hi}</td><td>{n} 只</td>"
        "<td>{pct:.1f}%</td></tr>".format(
            d=x["decile"], lo=x["lo"], hi=x["hi"], n=x["n"],
            pct=(x["n"] / st["n"] * 100) if st["n"] else 0)
        for x in res["deciles"])

    drop_txt = " · ".join("%s %d" % (k, v) for k, v in u["drop"].items() if v)
    band_txt = " · ".join("%s %d" % (k, v) for k, v in sorted(u["band"].items(), key=lambda kv: -kv[1]))

    return """<!DOCTYPE html>
<html lang='zh-CN'><head><meta charset='UTF-8'>
<meta name='viewport' content='width=device-width,initial-scale=1.0'>
<title>稳健分选股 · 全市场横截面 · {D}</title>
<style>
*{{box-sizing:border-box}}
body{{margin:0;background:#f5f6f8;color:#23262b;font-family:"PingFang SC","Microsoft YaHei","Hiragino Sans GB",sans-serif;line-height:1.75}}
.wrap{{max-width:1440px;margin:0 auto;padding:28px 20px 60px}}
.topnav{{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:22px;padding-bottom:14px;border-bottom:1px solid #e6e9ee}}
.topnav a{{color:#b8893b;text-decoration:none;font-size:13px;padding:4px 12px;border-radius:20px;border:1px solid rgba(184,137,59,.35)}}
.topnav a.cur{{background:#b8893b;color:#fff;border-color:#b8893b}}
header h1{{font-size:26px;margin:0 0 6px}}
header h1 span{{background:linear-gradient(90deg,#b8893b,#8a6428);-webkit-background-clip:text;-webkit-text-fill-color:transparent}}
.sub{{color:#6b7480;font-size:13.5px}}
.env{{margin-top:18px;padding:14px 18px;border-radius:12px;background:{env_bg};color:{env_txt};font-size:14px;display:flex;flex-wrap:wrap;gap:22px;align-items:center}}
.env b{{font-size:19px}}
.section{{margin-top:30px}}
.section h2{{font-size:19px;margin:0 0 14px;padding-left:12px;border-left:4px solid #b8893b}}
.kb{{background:#fff;border:1px solid #e6e9ee;border-radius:12px;padding:14px 16px}}
.kgrid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px}}
.kt{{font-size:12.5px;color:#6b7480}}
.kv{{font-size:22px;font-weight:700;margin:4px 0}}
.kd{{font-size:12px;color:#8a929c}}
table{{width:100%;border-collapse:collapse;background:#fff;border:1px solid #e6e9ee;border-radius:12px;overflow:hidden;font-size:13.5px}}
th{{background:#faf7f1;color:#6b5a3a;font-weight:600;text-align:left;padding:10px 12px;white-space:nowrap;font-size:12.5px}}
td{{padding:9px 12px;border-top:1px solid #eef1f5;white-space:nowrap}}
tr:hover td{{background:#fcfbf8}}
.rk{{color:#8a929c;font-weight:600}}
.nm{{font-weight:600}}
.bd{{margin-left:8px;font-size:11.5px;color:#8a929c;border:1px solid #e6e9ee;border-radius:10px;padding:1px 7px}}
.sc{{color:#b8893b;font-weight:700;font-size:15px}}
.ld{{color:#6b7480;font-size:12.5px}}
.note{{margin-top:12px;font-size:12.5px;color:#6b7480}}
.warn{{margin-top:12px;padding:12px 16px;border-radius:10px;background:#fdf6e9;border:1px solid #f0e2c4;font-size:13px;color:#8a6a2a}}
.lim li{{margin:6px 0;font-size:13.5px;color:#3d434b}}
</style></head><body><div class='wrap'>
<header>
  <h1>稳健分选股 · <span>全市场横截面</span></h1>
  <div class='sub'>数据日 {D} · 生成 {GEN} · 模型 {VER} · 先验 {NF} 因子等权横截面分位（不筛、不调权）</div>
</header>

<div class='env'>
  <span>环境门控 <b>{ENVLABEL}</b></span>
  <span>建议仓位系数 <b>{COEF}</b></span>
  <span>域内标的 <b>{KEPT}</b> 只</span>
  <span class='kd'>广度 = 全市场站上 MA20 占比（{BREADTH}%）</span>
</div>

<div class='section'>
  <h2>怎么用这一页</h2>
  <div class='kb'>
    ① <b>先看环境</b>：门控系数决定总仓位 —— 弱势期降暴露甚至停手，比换标的更有效
    （实测弱势「随便买」绝对胜率 40.9% vs 强势 51.1%）。<br>
    ② <b>再看名单</b>：稳健分是**域内横截面分位**（0~100，50 = 中位），不是预测涨跌幅；
    分数高只代表「在这 12 个先验维度上更占优」。<br>
    ③ <b>入场仍需技术确认</b>：本页只做候选排序，不替代均线 / 量价结构 / 止损纪律。
  </div>
  <div class='warn'>为什么不再「按回测胜率调权重」：样本内过拟合。把全量筛因子（+12.4pp）
  与严格样本外（+0.5pp）并排看，<b>差额就是过拟合量</b>；而先验固定因子集在留出段
  仍有 <b>+4.9pp 相对胜率、6 段滚动全部为正</b>。证据见 <b>lab.html</b>。</div>
</div>

<div class='section'>
  <h2>可交易域</h2>
  <div class='kgrid'>
    <div class='kb'><div class='kt'>缓存标的</div><div class='kv'>{TOTAL}</div><div class='kd'>全部有日K的标的</div></div>
    <div class='kb'><div class='kt'>域内标的</div><div class='kv'>{KEPT}</div><div class='kd'>剔除后剩余（{KEEPPCT}%）</div></div>
    <div class='kb'><div class='kt'>分数中位</div><div class='kv'>{MED}</div><div class='kd'>最高 {MAX} / 最低 {MIN}</div></div>
    <div class='kb'><div class='kt'>流动性下限</div><div class='kv'>{MINAMT}万</div><div class='kd'>20 日均额</div></div>
  </div>
  <div class='note'>剔除规则：{DROP}。域内板块分布：{BAND}。</div>
  <div class='note'>⚠️ 成交额口径：腾讯日K的 volume 单位**不统一**（科创板为股、其余为手），
  本页已按板块统一换算；此前未换算导致主板成交额被低估 100 倍、流动性过滤把主板几乎全部误杀。</div>
</div>

<div class='section'>
  <h2>稳健分 Top {TOPN}</h2>
  <table>
    <thead><tr><th>#</th><th>名称</th><th>稳健分</th><th>因子亮点（分位最高 3 项）</th>
    <th>量比</th><th>距20日高</th><th>营收同比</th><th>单季净利同比</th><th>ROE</th><th>20日均额</th></tr></thead>
    <tbody>{TRS}</tbody>
  </table>
  <div class='note'>「因子亮点」= 该股在域内分位最高的 3 个因子（分位越高越占优）；
  量比 &lt; 1 表示缩量（先验偏好不过度拥挤），距 20 日高为负表示仍在回调中。</div>
</div>

<div class='section'>
  <h2>分数分布（十分位）</h2>
  <table><thead><tr><th>档位</th><th>分数区间</th><th>样本数</th><th>占比</th></tr></thead>
  <tbody>{DEC}</tbody></table>
</div>

<div class='section'>
  <h2>局限（必须一起看）</h2>
  <ul class='lim'>
    <li><b>前视偏差</b>：基本面因子取自最新报告期（东财业绩报表），套用到更早价格上；
    偏差对全部标的同等作用，故相对 lift 仍有效，但<b>绝对胜率被高估</b>。</li>
    <li><b>窗口重叠</b>：实验室前向 5 日窗口互相重叠，样本非独立，pp 差应按<b>日期聚类</b>理解。</li>
    <li><b>样本跨度</b>：覆盖 2025-07 ~ 2026-08，不足一个完整牛熊周期，<b>换年份是否成立无法验证</b>。</li>
    <li><b>分数是相对量</b>：域内横截面分位会随当日域构成漂移，<b>不可跨日直接比较绝对分数</b>。</li>
    <li><b>非投资建议</b>：本页是筛选与排序工具，不构成任何买卖推荐；入场、仓位、止损须自行判断。</li>
  </ul>
</div>

</div></body></html>
""".format(
        D=D, GEN=res["generated"], VER=res["model"]["version"], NF=res["model"]["nFeat"],
        env_bg=env_bg, env_txt=env_txt,
        ENVLABEL=env.get("label") or "未知", COEF=env.get("coef"),
        BREADTH=env.get("breadth"), KEPT=u["kept"], TOTAL=u["total"],
        KEEPPCT=("%.1f" % (u["kept"] / u["total"] * 100)) if u["total"] else "0",
        MED=st["median"], MAX=st["max"], MIN=st["min"], MINAMT=u["minAmtWan"],
        DROP=drop_txt or "无", BAND=band_txt, TOPN=len(res["top"]),
        TRS="\n".join(trs), DEC=dec_rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--top", type=int, default=DEF_TOP)
    ap.add_argument("--min-amt", type=float, default=DEF_MIN_AMT, help="20 日均额下限（万元）")
    ap.add_argument("--min-price", type=float, default=DEF_MIN_PRICE)
    ap.add_argument("--no-render", action="store_true")
    a = ap.parse_args()

    res = scan(a.date, a.top, a.min_amt, a.min_price)
    os.makedirs(PICKS, exist_ok=True)
    jf = os.path.join(PICKS, "stable_%s.json" % a.date)
    with open(jf, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False)
    print("[scan_stable] %s 域内 %d / %d 只，中位分 %s，环境 %s" % (
        a.date, res["universe"]["kept"], res["universe"]["total"],
        res["stats"]["median"], res["env"].get("label")))
    if not a.no_render:
        os.makedirs(OUTDIR, exist_ok=True)
        hf = os.path.join(OUTDIR, "stable_%s.html" % a.date)
        with open(hf, "w", encoding="utf-8") as f:
            f.write(render(res))
        print("  → %s" % hf)
    print("  → %s" % jf)
    for r in res["top"][:10]:
        print("   %2d %-10s %-8s %5.1f  %s" % (
            r["rank"], r["code"], r["name"], r["score"], " · ".join(r["lead"])))


if __name__ == "__main__":
    main()
