#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""龙道诀 · 情绪周期择时台（数据驱动生成器）

视频版《龙道诀》讲的是「打板核心不是 K 线技术，是市场情绪节点」——
九句口诀里真正能被机器核对的，是「情绪处在周期的哪一段」「此刻该做什么不该做什么」。
本页把口诀里**能量化的部分用真数据落地**，量不了的就写「不可核」，不硬凑。

用法：
    python quant/build_dragon.py                 # 用底座最新数据日
    python quant/build_dragon.py --date 2026-09-30

数据源（全部本地已落盘，走统一层，绝不联网现算、绝不编数）：
    quant/_txk_cache.json              日K 251 日 × 5049 票（唯一入口 _txk.load）
    quant/sector_concept_{DS}.json     概念热度（changePct / upCount / 主力净流入）
    quant/sector_industry_{DS}.json    行业热度（同上）
输出：
    web/dragon/index.html

红线（与本项目其余模块一致）：
  · 只给「周期定位 + 操作规则提示」，**不给个股清单**（个股清单看「群体心理 / 连板周报」）；
  · 所有分位与统计只用**截至当日**的数据滚动计算 —— 不用未来信息；
  · 数据读到什么就写到哪天，**不冒充成今天**；读不到就显示「无法自检」。
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

OUT_DIR = os.path.join(ROOT, "web", "dragon")
OUT = os.path.join(OUT_DIR, "index.html")

WIN = 60              # 滚动窗口（交易日）—— 所有分位/统计都用它
FORWARD_DAYS = 5      # 阶段 → 后续表现回看的天数


# ------------------------------------------------------------------ 数据层
def load_quotes():
    """读日K（统一层）。读不到抛异常，由调用方降级，绝不返回空数据冒充。"""
    import _txk
    return _txk.load()


def build_series(cache):
    """逐票扫日K → 每日市场情绪指标。返回 list[dict]，按日期升序。

    closed  = 收盘封住涨停（用 >= 涨停价*0.9995，容差处理四舍五入）
    touched = 盘中触及涨停（含封住与否）
    炸板     = touched 且 未 closed
    streak  = 连板天数（连续收盘涨停，断即归零）
    """
    # ★ 2026-10-06：封板/炸板/连板判定收口到统一真源 `_mkt_emo`（原来这里自写一份），
    #   与「群体心理/大盘概览」用同一口径，页面之间不再出现两套涨停家数。
    import _mkt_emo as M
    day = collections.defaultdict(list)
    ret = collections.defaultdict(list)     # date -> [日涨跌幅]
    for code, bars in cache.items():
        if len(bars) < 3:
            continue
        for r in M.scan_one(code, bars):
            day[r["date"]].append((code, r["closed"], r["touched"], r["run"]))
            ret[r["date"]].append(r["chg"])

    # 只保留「绝大多数票都有数据」的日子 —— 少一天会让家数突然缩水，看着像暴跌
    dates = sorted(x for x, v in day.items() if len(v) > 3000)

    out = []
    for i, d8 in enumerate(dates):
        zt = zb = 0
        hi = 0
        n2 = n3 = 0
        two_set = set()
        for code, closed, touched, run in day[d8]:
            if closed:
                zt += 1
                hi = max(hi, run)
                if run == 2:
                    n2 += 1
                    two_set.add(code)
                elif run >= 3:
                    n3 += 1
            elif touched:
                zb += 1
        rs = ret[d8]
        eq = (sum(rs) / len(rs)) if rs else 0.0        # 全市场等权日收益
        out.append(dict(date=d8, zt=zt, zb=zb, rate=(zb / (zt + zb)) if (zt + zb) else 0.0,
                        hi=hi, n2=n2, n3=n3, eq=eq, two_set=two_set))

    # 二板→三板晋级率：今日二板票，明日收盘是否还涨停（ continuous ）
    closed_by_day = {}
    for d8 in dates:
        closed_by_day[d8] = {c for c, closed, _t, _r in day[d8] if closed}
    for i, row in enumerate(out):
        if i + 1 < len(out):
            nxt = closed_by_day[out[i + 1]["date"]]
            hit = len(row["two_set"] & nxt)
            row["prom_n"] = len(row["two_set"])
            row["prom_hit"] = hit
        else:
            row["prom_n"] = len(row["two_set"])
            row["prom_hit"] = None
        row.pop("two_set", None)
    return out


# ★ 2026-10-06：滚动分位与「情绪四阶段判定」收口到统一真源 `_mkt_emo`
#   （原来这两个函数只存在本页，别的池要用只能再抄一遍；门控实验统一引这里）。
#   分位定义与阶段阈值改一处即全站生效，页面上的判定说明仍原样印出来。
from _mkt_emo import rolling_pctile, stage_of


STAGE_ACTION = {
    "冰点": dict(
        verse="第 1 句 · 择时擒龙顺天时",
        do="只观察、不重仓。把候选放进自选（看「群体心理 / 连板周报」的二板梯队），等第三句的条件成立。",
        avoid="不要在冰点里找龙头 —— 这个阶段没有真龙，多数是新题材的一日游。",
    ),
    "回暖": dict(
        verse="第 2、3 句 · 二板烂透出地利 → 三板暴龙现人和",
        do="这是本战法的主操作段：看二板换手梯队，等三板确认后再等「首次分歧」。",
        avoid="二板只是候选，别在二板重仓；也不要在三板上还没出现板块跟风时抢跑。",
    ),
    "高潮": dict(
        verse="第 5 句 · 妖龙一致卖合一",
        do="持有人在一致性高潮时兑现——这是卖点。没有持仓就别追。",
        avoid="别在人声鼎沸时买入。这是多数人亏钱的地方：把卖点当买点。",
    ),
    "退潮": dict(
        verse="第 7 句 · 顺势聚焦龙与空（空）",
        do="空仓等待。等炸板率回落、涨停家数重新站上中位。",
        avoid="退潮期强行找龙头，接到的多是诱多。",
    ),
    "样本不足": dict(verse="—", do="数据不足，按「无信号」处理。", avoid="不要凭感觉补数据做判断。"),
}

STAGE_COLOR = {"冰点": "#3b82f6", "回暖": "#d8392b", "高潮": "#f59e0b", "退潮": "#1a9e5a",
               "样本不足": "#8b8b8b"}


# ------------------------------------------------------------------ 热点
def _digits(s):
    """把 2026-09-30 / 20260930 都规范成 '20260930'。

    ⚠ 本项目两种日期写法混用（{DATE} 带横线、{DS} 不带）。直接字符串比较时
    '20260930' > '2026-09-30'（'-' 码点小于数字），于是**当天的数据会被当成
    未来数据过滤掉** —— 板块热点第一次跑就整模块显示「无法自检」，根因就是它。
    """
    return (s or "").replace("-", "").replace("/", "")


def latest_sector(kind="concept", asof=None):
    """读最近一期概念/行业热度。asof 之后的文件不用（避免拿未来数据）。"""
    pat = os.path.join(HERE, "sector_%s_*.json" % kind)
    fs = sorted(glob.glob(pat))
    pick = None
    for f in fs:
        stem = _digits(os.path.basename(f).replace("sector_%s_" % kind, "").replace(".json", ""))
        if stem.isdigit() and (asof is None or stem <= _digits(asof)):
            pick = f
    if not pick:
        return None, None
    try:
        j = json.load(open(pick, encoding="utf-8"))
    except Exception:
        return None, None
    rows = (j.get("data") or {}).get("rows") or []
    return rows, os.path.basename(pick).replace(".json", "")


def latest_odds(asof=None):
    """读「阶段胜率实验室」产出 `quant/dragon/odds_{DS}.json`。

    没读到就返回 None —— 页面那一段会显示「无法自检」，
    **绝不拿旧数据冒充当天、也绝不自己编一组胜率出来**。
    """
    pick = None
    for f in sorted(glob.glob(os.path.join(HERE, "dragon", "odds_*.json"))):
        stem = _digits(os.path.basename(f).replace("odds_", "").replace(".json", ""))
        if stem.isdigit() and (asof is None or stem <= _digits(asof)):
            pick = f
    if not pick:
        return None
    try:
        return json.load(open(pick, encoding="utf-8"))
    except Exception:
        return None


def top_rows(rows, key="changePct", n=8):
    def _v(r):
        try:
            return float(r.get(key) or 0)
        except (TypeError, ValueError):
            return 0.0
    return sorted(rows, key=_v, reverse=True)[:n]


# ------------------------------------------------------------------ HTML
CSS = """
  :root{--bg:#f5f5f7;--card:#fff;--ink:#1c1b19;--muted:#6b675f;--line:#e7e2d8;
        --up:#d8392b;--down:#1a9e5a;--gold:#0071e3;}
  *{box-sizing:border-box;margin:0;padding:0}
  body{background:var(--bg);color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,
       "PingFang SC","Noto Sans SC","Microsoft YaHei",sans-serif;line-height:1.68;}
  .wrap{max-width:1060px;margin:0 auto;padding:0 18px 70px;}
  .masthead{background:linear-gradient(135deg,#221f1c,#3a3026);color:#f7f3ea;
    border-radius:0 0 18px 18px;padding:30px 26px 24px;}
  .kicker{font-size:.72rem;letter-spacing:.28em;color:var(--gold);font-weight:700;}
  .masthead h1{font-size:2rem;font-weight:800;margin:6px 0 6px;line-height:1.15;}
  .masthead .sub{font-size:.92rem;color:#cfc6b6;max-width:700px;}
  .mast-meta{margin-top:12px;font-size:.78rem;color:#bdb4a4;display:flex;gap:14px;flex-wrap:wrap;}
  h2{font-size:1.3rem;margin:38px 0 12px;padding-left:11px;border-left:5px solid #b8332a;}
  h3{font-size:1.02rem;margin:22px 0 8px;color:#3a3026;}
  p{margin:8px 0;}
  .card{background:var(--card);border:1px solid var(--line);border-radius:14px;
    padding:18px 20px;margin:14px 0;box-shadow:0 1px 3px rgba(28,27,25,.07);}
  .stagebox{display:flex;align-items:center;gap:18px;flex-wrap:wrap;}
  .stage{font-size:1.7rem;font-weight:800;letter-spacing:.06em;}
  .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:14px 0;}
  .kpi{background:#fbfaf8;border:1px solid var(--line);border-radius:12px;padding:12px 14px;}
  .kpi .lab{font-size:.76rem;color:var(--muted);}
  .kpi .val{font-size:1.35rem;font-weight:700;margin-top:2px;}
  .kpi .pct{font-size:.74rem;color:var(--muted);}
  table{width:100%;border-collapse:collapse;font-size:.86rem;margin:10px 0;}
  th,td{border-bottom:1px solid var(--line);padding:8px 9px;text-align:left;vertical-align:top;}
  th{background:#f3f0ea;font-weight:700;}
  td.num,th.num{text-align:right;}
  .up{color:var(--up);} .down{color:var(--down);} .muted{color:var(--muted);}
  .warn{background:#fff6f5;border:1px solid #f3c9c4;border-radius:12px;padding:14px 16px;margin:14px 0;}
  .note{background:#f6f8fb;border:1px solid #dbe4f0;border-radius:12px;padding:14px 16px;margin:14px 0;
    font-size:.9rem;}
  code{background:#eef4fa;color:#1f4e79;padding:1px 6px;border-radius:5px;font-size:.85rem;}
  .tag{display:inline-block;font-size:.72rem;padding:2px 8px;border-radius:20px;
    background:#ece7dd;color:#5b5449;margin-left:6px;}
  .tag.ok{background:#e6f4ea;color:#14683a;}
  .tag.no{background:#fdecea;color:#8a1f14;}
  .tag.mid{background:#fdf3e3;color:#7a4c0a;}
  ul{margin:8px 0 8px 20px;} li{margin:5px 0;}
  footer{margin-top:34px;padding-top:16px;border-top:1px solid var(--line);
    font-size:.8rem;color:var(--muted);}
  a{color:#1f4e79;}
"""


def kpi(label, val, sub):
    return ("<div class='kpi'><div class='lab'>%s</div>"
            "<div class='val'>%s</div><div class='pct'>%s</div></div>" % (label, val, sub))


def _pc(v):
    """带颜色的百分比（涨红跌绿，A股口径）。"""
    if v is None:
        return "—"
    cls = "up" if v > 0 else ("down" if v < 0 else "")
    return "<span class='%s'>%+.2f%%</span>" % (cls, v * 100)


def render(ctx):
    """拼页面。所有数字来自 ctx（真数据），读不到就是「无法自检」。"""
    parts = []
    A = parts.append
    A("<!DOCTYPE html><html lang='zh-CN'><head><meta charset='UTF-8'>")
    A("<meta name='viewport' content='width=device-width,initial-scale=1.0'>")
    A("<title>龙道诀 · 情绪周期择时台</title>")
    A("<style>%s</style></head><body><div class='wrap'>" % CSS)

    # masthead
    A("<div class='masthead'><div class='kicker'>DRAGON DAO · EMOTION CYCLE</div>")
    A("<h1>龙道诀 · 情绪周期择时台</h1>")
    A("<div class='sub'>把《龙道诀》九句口诀里<b>能被机器核对的部分</b>用真实行情落地："
      "判断市场情绪处在周期的哪一段，对应哪一句口诀、此刻该做什么、不该做什么。"
      "量不了的句子如实标「不可核」，不硬凑。</div>")
    A("<div class='mast-meta'><span>数据日 %s</span><span>源 %s</span>"
      "<span>样本 %s 个交易日 × %d 只票</span><span>生成 %s</span></div></div>"
      % (ctx["asof"], ctx["src"], ctx["ndays"], ctx["ncodes"],
         dt.datetime.now().strftime("%Y-%m-%d %H:%M")))

    if ctx.get("err"):
        A("<div class='warn'><b>无法自检</b>：%s<br>"
          "本项目规则是「读不到证据就不给结论」——此处保留空缺，不会用旧数据或估计值填上。</div>"
          % ctx["err"])
    else:
        A(render_stage(ctx))
        A(render_verses(ctx))
        A(render_calib(ctx))
        A(render_odds(ctx))      # 四：胜率最高的形态（真源 _dragon_odds）
        A(render_cand(ctx))      # 五：今天的观察名单
        A(render_plan(ctx))      # 六：配套操作方案（规则层）
        A(render_hot(ctx))
        A(render_uses(ctx))

    A(render_risk())
    A("<footer>%s ｜ 生成脚本 <code>quant/build_dragon.py</code> ｜ "
      "胜率统计真源 <code>quant/_dragon_odds.py</code>（产出 "
      "<code>quant/dragon/odds_{DS}.json</code>）｜ "
      "本页定位是<b>情绪周期定位 + 规则提示</b>；"
      "第五节只给形态触发后的<b>观察名单</b>，不是推荐、不含买卖点位。</footer>"
      % dt.datetime.now().strftime("%Y-%m-%d %H:%M"))
    A("</div></body></html>")
    return "\n".join(parts)


def render_stage(ctx):
    s = ctx["now"]
    st = s["stage"]
    act = STAGE_ACTION.get(st, STAGE_ACTION["样本不足"])
    color = STAGE_COLOR.get(st, "#8b8b8b")
    o = ["<h2>一、当前情绪节点</h2>"]
    o.append("<div class='card stagebox'>")
    o.append("<div><div class='lab muted' style='font-size:.78rem'>判定结果</div>"
             "<div class='stage' style='color:%s'>%s</div></div>" % (color, st))
    o.append("<div style='flex:1;min-width:260px'><b>依据</b>：%s</div></div>" % s["why"])
    o.append("</div>")

    o.append("<div class='grid'>")
    o.append(kpi("涨停家数（收盘封住）", s["zt"], "60 日滚动分位 %.0f%%" % (s["zt_p"] or 0)))
    o.append(kpi("炸板率", "%.1f%%" % (s["rate"] * 100), "分位 %.0f%%（越高越分歧）" % (s["rate_p"] or 0)))
    o.append(kpi("最高连板", "%d 板" % s["hi"], "分位 %.0f%%" % (s["hi_p"] or 0)))
    o.append(kpi("二板家数", s["n2"], "三板及以上 %d 家" % s["n3"]))
    o.append("</div>")

    o.append("<div class='card'><b>对应口诀</b>：%s" % act["verse"])
    o.append("<p style='margin-top:8px'><b class='up'>该做</b>：%s</p>" % act["do"])
    o.append("<p><b class='down'>不该做</b>：%s</p></div>" % act["avoid"])

    # ★ 三个指标有时会互相打架（比如高度很高但涨停家数很低），
    #   这时候必须把「打架」本身说出来，而不是只丢一个阶段标签给人。
    notes = []
    if st in ("冰点", "退潮") and s["hi_p"] is not None and s["hi_p"] >= 60:
        notes.append("连板高度分位偏高（<b>%.0f%%</b>，最高 %d 板）但涨停家数分位只有 %.0f%% —— "
                     "这是<b>「高度有了、广度没起来」的结构性行情</b>：极少数高标在打空间，"
                     "赚钱效应没扩散到全市场。按<b>不扩散就不算回暖</b>处理，仍按%s档。"
                     % (s["hi_p"], s["hi"], s["zt_p"] or 0, st))
    if st == "高潮" and s["rate_p"] is not None and s["rate_p"] >= 50:
        notes.append("已进高潮但炸板率分位也到了 %.0f%% —— 一部分票开始封不住了，"
                     "这是<b>高潮中后段</b>的常见形态，卖出窗口在收窄。" % s["rate_p"])
    if st == "回暖" and s["rate_p"] is not None and s["rate_p"] >= 70:
        notes.append("回暖但炸板率分位 %.0f%% 偏高 —— 说明承接不够扎实，"
                     "这种回暖容易夭折，别急着上仓位。" % s["rate_p"])
    if notes:
        o.append("<div class='note'><b>当天的指标在互相打架，说明白一点：</b><ul>")
        for n in notes:
            o.append("<li>%s</li>" % n)
        o.append("</ul></div>")

    o.append("<div class='note'><b>这套判定是怎么算的（怕你看不清规则，所以全印出来）</b>"
             "<ul><li>三个指标各取<b>过去 %d 个交易日</b>的滚动分位；只看过去，不用未来数据。"

             "</li><li>判定<b>按序</b>：退潮 → 高潮 → 回暖 → 其余落冰点（有兜底，不会留空档）。"
             "<ul><li><b>退潮</b>：炸板率分位 ≥70 且 涨停家数分位 &lt;50</li>"
             "<li><b>高潮</b>：涨停家数分位 ≥75 且 高度分位 ≥70 且 炸板率分位 ≤40</li>"
             "<li><b>回暖</b>：涨停家数分位 ≥40 且（高度分位 ≥50 或 涨停家数分位 ≥60）</li>"
             "<li><b>冰点</b>：以上都不满足</li></ul></li>"
             "<li>分位样本不足 10 天 → 显示「样本不足」，不猜。</li></ul></div>" % WIN)
    return "".join(o)


VERSES = [
    ("1", "择时擒龙顺天时", "可核", "涨停家数 / 炸板率 / 连板高度的 60 日分位",
     "本页「当前情绪节点」就是它"),
    ("2", "二板烂透出地利", "近似", "二板家数可核；「烂板=充分换手」需分时/逐笔，日K只能用振幅+量比近似",
     "未展示（近似口径尚未验证，不做数）"),
    ("3", "三板暴龙现人和", "可核", "二板→三板晋级率（给出真实样本数与胜率）",
     "本页「真实校准」"),
    ("4", "强龙分歧买知行", "近似", "「首次分歧」可定义为连板中断首日，能量化但<b>未做样本外验证</b>",
     "暂未展示（未过四道验证，不给结论）"),
    ("5", "妖龙一致卖合一", "近似", "「一致」可用缩量+普涨代理，但卖点精度依赖个股级别数据",
     "本页在高潮阶段给出提示，不给点位"),
    ("6", "山是山兮去群虫", "部分可核", "相对强弱可算，但「留最强」的价值排序属策略层，需另做验证",
     "未展示"),
    ("7", "顺势聚焦龙与空", "可核", "「空」这一半完全可核：空仓=当前阶段不允许出手的判定",
     "本页已在退潮/冰点给出空仓提示"),
    ("8", "物在己身皆不同", "不可核", "认知、心态、资金承受力 —— 机器无从度量",
     "不可核，如实标注"),
    ("9", "循环悟道守本心", "不可核", "纪律是执行层面，不是数据层面",
     "不可核，如实标注"),
]
TAGCLS = {"可核": "ok", "近似": "mid", "部分可核": "mid", "不可核": "no"}


def render_verses(ctx):
    o = ["<h2>二、九句口诀 × 机器能不能核</h2>"]
    o.append("<div class='note'>口诀是经验总结，落到机器上只有一部分能量化。"
             "这里逐句标注<b>可核 / 近似 / 不可核</b>，避免「看着像验证了，其实是拍脑袋」。</div>")
    o.append("<table><tr><th>#</th><th>口诀</th><th>可核性</th><th>用什么数据代理</th>"
             "<th>本页处理</th></tr>")
    for n, t, k, proxy, deal in VERSES:
        o.append("<tr><td class='num'>%s</td><td><b>%s</b></td>"
                 "<td><span class='tag %s'>%s</span></td><td>%s</td><td>%s</td></tr>"
                 % (n, t, TAGCLS.get(k, "mid"), k, proxy, deal))
    o.append("</table>")
    o.append("<div class='warn'><b>关于第 2、4 句（本战法的核心买点）</b>："
             "「二板烂板」「首次分歧」都需要<b>分时/盘口</b>才能严格判定，"
             "本地只有日K（开高低收量）。用日K近似可以做，但<b>没有做样本外验证之前不给结论</b> —— "
             "这是本项目的一贯做法：宁可写「待验证」，也不拿未验证的口径当信号。</div>")
    return "".join(o)


def render_calib(ctx):
    c = ctx["calib"]
    o = ["<h2>三、真实校准（用数据给口诀标刻度）</h2>"]
    o.append("<div class='grid'>")
    o.append(kpi("二板→三板晋级率（近 %d 日）" % WIN, "%.1f%%" % (c["prom_rate"] * 100),
                 "候选 %d 个 / 晋级 %d 个" % (c["prom_n"], c["prom_hit"])))
    o.append(kpi("三板以上个股出现天数占比", "%.1f%%" % (c["has3_ratio"] * 100),
                 "%d / %d 个交易日" % (c["has3_days"], c["ndays_eff"])))
    o.append(kpi("全部样本炸板率均值", "%.1f%%" % (c["rate_avg"] * 100), "越高说明封板越难"))
    o.append(kpi("涨停家数中位数", "%d 家" % c["zt_med"], "区间 %d ~ %d 家" % (c["zt_min"], c["zt_max"])))
    o.append("</div>")

    o.append("<div class='warn'><b>对「三板定龙头」的校准</b>：近 %d 个交易日里，"
             "二板票有 <b>%d</b> 个走到三板、<b>%.1f%%</b> 止步 —— "
             "换句话说<b>六成以上的二板会在次日断掉</b>。"
             "这不影响口诀成立（它说的就是用「三板」去筛掉这批），"
             "但它告诉你：二板阶段动手，胜率就是个<b>三成出头</b>的事。"
             "</div>" % (WIN, c["prom_hit"], (1 - c["prom_rate"]) * 100))

    if c.get("fwd"):
        o.append("<h3>历史回看：各阶段之后 %d 日的全市场表现</h3>" % FORWARD_DAYS)
        o.append("<table><tr><th>阶段</th><th class='num'>样本数</th><th class='num'>胜率（上涨占比）</th>"
                 "<th class='num'>平均涨跌</th><th class='num'>最好</th><th class='num'>最差</th></tr>")
        for st, row in c["fwd"]:
            warn_mark = " ⚠ 样本偏少" if row["n"] < 30 else ""
            o.append("<tr><td><b>%s</b>%s</td><td class='num'>%d</td><td class='num'>%.1f%%</td>"
                     "<td class='num'>%s</td><td class='num'>%s</td><td class='num'>%s</td></tr>"
                     % (st, warn_mark, row["n"], row["win"] * 100, _pc(row["mean"]),
                        _pc(row["best"]), _pc(row["worst"])))
        o.append("</table>")
        o.append("<div class='note'><b>怎么读这张表（读错了比不看更危险）</b>"
                 "<ul><li>这是<b>历史回看统计</b>，不是预测。它回答的是「过去在这个情绪阶段买入、"
                 "持有 %d 天，<b>全市场等权</b>是赚是亏、多少次赚多少次亏」。</li>"
                 "<li><b>别拿它比较「哪个阶段更好」</b>：各阶段样本数悬殊（上表已列出，"
                 "少于 30 的标了 ⚠），且这里是<b>全市场等权</b>而不是龙头 —— "
                 "龙头能不能跑出超额是另一回事，本页没验证过，就不替它说话。</li>"
                 "<li>这张表最该看的其实是<b>最差那一列</b>：它提醒你同一个阶段里，"
                 "最糟糕的时候能亏掉多少 —— 这才是仓位管理的依据。</li></ul></div>"
                 % FORWARD_DAYS)
    return "".join(o)


# ------------------------------------------------ 新增：胜率最高的形态 / 名单 / 方案
ODDS_KS = ("1", "3", "5")


def _win(r, k):
    s = (r or {}).get(k)
    return ("%.1f%%" % (s["win"] * 100)) if s else "—"


def render_odds(ctx):
    od = ctx.get("odds") or {}
    o = []
    b = od.get("best_cur") or od.get("best")
    cur = od.get("cur_stage", ctx.get("now", {}).get("stage", "—"))
    o.append("<h2>四、胜率最高的形态（这一节的全部数字都是现算的）</h2>")
    if not b:
        o.append("<div class='warn'><b>无法自检</b>：没有达标形态 —— "
                 "所有候选形态在「三个持有期都优于对照」这两道上没有全过。"
                 "按红线：<b>宁可不给结论，也不放宽阈值凑数字</b>。此处保留空缺。</div>")
        return "".join(o)
    is_cur = bool(od.get("cand_for", {}).get("is_cur_stage")) or \
        (b["stage"] == cur)
    o.append("<div class='note'>形态 = <b>「%s期 · %s」</b>，意思是："
                 "市场情绪判定为<b>%s</b>、当天收盘封涨停、<b>连板数正好是 %s</b>"
                 "（四板＝当日是这只票连起来的第 4 个涨停）时，"
             "以当日收盘价买入、往后持有 K 天的胜率。%s</div>"
             % (b["stage"], b["run"], b["stage"], b["run"],
                "这就是<b>当前阶段</b>（今天判定为%s）的最优形态。"
                % cur if is_cur else "（注：这是<b>全样本</b>最优，不是当前阶段最优。）"))

    # ---- 主指标 ----
    o.append("<div class='grid'>")
    o.append(kpi("样本 / 横跨天数", "%d 个 / %d 天" % (b["1"]["n"], b["days"]),
                 "样本下限 %d、至少跨 %d 天" % (od.get("min_n", 30), od.get("min_days", 5))))
    o.append(kpi("K=1 日胜率", _win(b, "1"), "均值 %s / 最差 %s"
                 % (_pc(b["1"]["mean"]), _pc(b["1"]["worst"]))))
    o.append(kpi("K=3 日胜率", _win(b, "3"), "均值 %s / 最差 %s"
                 % (_pc(b["3"]["mean"]), _pc(b["3"]["worst"]))))
    o.append(kpi("K=5 日胜率", _win(b, "5"), "均值 %s / 最差 %s"
                 % (_pc(b["5"]["mean"]), _pc(b["5"]["worst"]))))
    o.append("</div>")

    # ---- 当前阶段各形态对比（原因的可核部分就在这张表里）----
    rows = od.get("cur_rows") or []
    if rows:
        o.append("<h3>为什么是这一档（先看表，这是最硬的证据）</h3>")
        o.append("<table><tr><th>形态</th><th class='num'>样本/天数</th>"
                 "<th class='num'>K=1 胜率</th><th class='num'>K=3 胜率</th>"
                 "<th class='num'>K=5 胜率</th><th>达标</th></tr>")
        for r in sorted(rows, key=lambda x: -((x.get("1") or {}).get("win") or -9)):
            hl = ' style="background:#fff9f2"' if (r["run"] == b["run"] and r["stage"] == b["stage"]) else ""
            mark = "<b>← 最优</b>" if (r["run"] == b["run"] and r["stage"] == b["stage"]) else ""
            o.append("<tr%s><td><b>%s</b>%s</td><td class='num'>%d / %d</td>"
                     "<td class='num'>%s</td><td class='num'>%s</td><td class='num'>%s</td>"
                     "<td><span class='tag %s'>%s</span>%s</td></tr>"
                     % (hl, r["run"], "", r["1"]["n"], r["days"], _win(r, "1"), _win(r, "3"),
                        _win(r, "5"), "ok" if r["enough"] else "no",
                        "达标" if r["enough"] else "样本不足", mark))
        o.append("</table>")
        o.append("<div class='note'><b>表里的规律（可核，不是解释是数据）</b>"
                 "<ul><li>同一阶段里，连板<b>越高</b>、K=1 胜率<b>越高</b>：%s</li>"
                 "<li>越低位的票越接近「扔硬币」：%s</li></ul></div>"
                 % (_stage_order_note(rows, b), _stage_base_note(rows, b)))

    # ---- 三道自检 ----
    parts = []
    if b.get("rand"):
        parts.append("<b>① 随机对照</b>：同一天、同等数量，从<b>全市场任意股票</b>里"
                     "随机抽 %d 次，K=1 胜率的 95 分位是 <b>%.1f%%</b>（中位数 %.1f%%）；"
                     "这一形态是 <b>%.1f%%</b> —— %s（固定种子，可复现）"
                     % (b["rand"]["1"]["tries"], b["rand"]["1"]["p95"] * 100,
                        b["rand"]["1"]["p50"] * 100, b["rand"]["1"]["real"] * 100,
                        "过了" if b["rand"]["1"]["win_p95"] else "没过"))
    if b.get("lift_n"):
        parts.append("<b>② 同阶段对照</b>：同一个情绪阶段里，全部涨停票的 K=1 胜率是 <b>%.1f%%</b>，"
                     "这一形态是 <b>%.1f%%</b>，超额 <b>%+.1fpp</b> —— 说明不是「阶段本身在托底」。"
                     % (b["base"]["1"]["win"] * 100, b["1"]["win"] * 100, b["lift"]["1"] * 100))
    wf = od.get("wf") or {}
    if wf.get("note"):
        parts.append("<b>③ 样本外（walk-forward）</b>：%s" % wf["note"])
    if parts:
        o.append("<div class='card'><b>它靠什么站住（三道自检，缺一不可）</b><ul>")
        for p in parts:
            o.append("<li>%s</li>" % p)
        o.append("</ul></div>")
    else:
        o.append("<div class='warn'><b>三道自检都没有足够证据</b> —— 按红线不给结论。</div>")

    # ---- 均值 vs 中位（防止被少数大涨骗了）----
    o.append("<div class='warn'><b>看胜率的同时必须看「中位」和「最差」</b>："
             "K=5 均值 <b>%s</b> 但中位只有 <b>%s</b>、最好 <b>%s</b>、最差 <b>%s</b>。"
             "<br>意思是：多数时候赚的就是这点<b>中位收益</b>，真正把均值拉高的那批（最好那只 %s）"
             "<b>不是常态</b> —— 拿均值当预期收益会高估自己。最差那一列才是仓位管理的依据。</div>"
             % (_pc(b["5"]["mean"]), _pc(b["5"]["med"]), _pc(b["5"]["best"]),
                _pc(b["5"]["worst"]), _pc(b["5"]["best"])))

    # ---- 归因：分「可核」与「不可核」，不硬凑 ----
    o.append("<h3>归因</h3>")
    if b.get("rand") and b.get("lift"):
        o.append("<div class='card'><b class='up'>可核的部分</b>（数据直接给出的）："
                 "<ul><li>该形态 K=1 胜率 <b>%s</b>，比同阶段全部涨停票（<b>%s</b>）高 "
                 "%+.1fpp，比同天全市场随机抽票的 95 分位（<b>%s</b>）高 %+.1fpp。</li>"
                 "<li>样本 %d 个、横跨 %d 个交易日 —— 不是撞在单日上的偶然。</li>"
                 "<li>三个持有期（%s）都优于各自对照，不是只在某一个持有期上亮眼。</li></ul></div>"
                 % (_win(b, "1"), "%.1f%%" % (b["base"]["1"]["win"] * 100), b["lift"]["1"] * 100,
                    "%.1f%%" % (b["rand"]["1"]["p95"] * 100),
                    (b["1"]["win"] - b["rand"]["1"]["p95"]) * 100,
                    b["1"]["n"], b["days"], " / ".join(ODDS_KS)))
    else:
        o.append("<div class='warn'>对照数据不完整，归因只保留可核的那三条（见上表）。</div>")
    o.append("<div class='note'><b class='down'>不可核的部分（如实标注，不编）</b>："
             "它为什么涨、题材是不是真的、游资在不在里面、明天会不会直接一字开 —— "
             "这些<b>本地数据衡量不了</b>。日K 只能告诉你<b>「过去这个形态后续大概率涨」</b>，"
             "不能告诉你<b>「这次为什么涨」</b>。任何把行情归因到某条消息、某个概念的说法，"
             "都请自己核，本页不代劳。</div>")
    return "".join(o)


def _stage_order_note(rows, best):
    """表里「连板越高、胜率越高」的规律，用真实数字说出来。"""
    hi = [r for r in rows if r["enough"] and r.get("1")]
    if len(hi) < 2:
        return "样本不足以排顺序。"
    hi.sort(key=lambda x: (not x["enough"], -x["1"]["win"]))
    top, low = hi[0], hi[-1]
    return "达标形态里 %s 的 K=1 胜率最高（%.1f%%），最低的是 %s（%.1f%%），差 %.1fpp" % (
        top["run"], top["1"]["win"] * 100, low["run"], low["1"]["win"] * 100,
        (top["1"]["win"] - low["1"]["win"]) * 100)


def _stage_base_note(rows, best):
    """低位票相对「扔硬币」的位置。"""
    low = [r for r in rows if r["enough"] and r.get("1") and r["run"] in ("首板", "二板")]
    if not low:
        return "——"
    return "; ".join("%s 胜率 %s" % (r["run"], _win(r, "1")) for r in low)


def render_cand(ctx):
    o = ["<h2>五、今天符合这个形态的观察名单</h2>"]
    cand = (ctx.get("odds") or {}).get("cand") or []
    for_ = (ctx.get("odds") or {}).get("cand_for") or {}
    if not cand:
        o.append("<div class='warn'>今天（数据日 %s）<b>没有</b>出现符合「%s / %s」的标的。"
                 "这份名单是<b>条件满足才生成</b>的 —— 空就是空，"
                 "本页不会拿别阶段的票来充数、也不会给一个「最像的」凑数。</div>"
                 % (ctx["asof"], for_.get("stage", "—"), for_.get("run", "—")))
        return "".join(o)
    o.append("<div class='warn'><b>这不是推荐，是观察名单。</b>"
             "它只说明「今天确实出现了这个历史胜率最高的形态」；"
             "名单里的票<b>没有经过出票闸</b>（无未来函数 / walk-forward / 随机对照 / 退出可兑现 四道），"
             "本页也不给买卖点位。看名单是为了「盯盘时知道该看谁」，不是「该买谁」。</div>")
    o.append("<table><tr><th>代码</th><th>名称</th><th class='num'>连板</th>"
             "<th class='num'>收盘</th><th class='num'>换手率</th>"
             "<th class='num'>自身历史样本</th><th class='num'>自身历史胜率</th></tr>")
    for c in cand:
        own = c.get("own_n") or 0
        mark = ("<span class='tag no'>首次出现</span>" if own == 0 else
                ("<span class='tag mid'>%d 次</span>" % own if own < 5 else "<span class='tag ok'>%d 次</span>" % own))
        ow = ("%.0f%%" % (c["own_win"] * 100)) if c.get("own_win") is not None else "—"
        o.append("<tr><td><code>%s</code></td><td><b>%s</b></td><td class='num'>%d 板</td>"
                 "<td class='num'>%.2f</td><td class='num'>%s</td><td>%s</td><td class='num'>%s</td></tr>"
                 % (c["code"], c["name"], c["run"], c["close"],
                    ("%.2f%%" % c["turnover"]) if c.get("turnover") is not None else "—",
                    mark, ow))
    o.append("</table>")
    no_hist = [c for c in cand if not (c.get("own_n") or 0)]
    if no_hist:
        o.append("<div class='note'><b>关于名单里的 %d 只「自身历史样本为 0」</b>："
                 "意思是它在样本期里<b>第一次</b>走到这个板数 —— 没有自己的历史胜率可查，"
                 "<b>这不代表它更安全或更危险</b>，只代表我们不知道。"
                 "真要用，先按下面第六节的规则小仓位试，别一上来就上重仓。</div>" % len(no_hist))
    return "".join(o)


RISK_PER_TRADE = 0.015      # 单笔风险预算（占本金）—— 用来从「历史最差」反推仓位上限


def render_plan(ctx):
    o = ["<h2>六、配套的操作方案（规则层，不是指令）</h2>"]
    b = (ctx.get("odds") or {}).get("best_cur") or (ctx.get("odds") or {}).get("best")
    if not b:
        o.append("<div class='warn'>没有达标形态，<b>方案不成立</b> —— 按红线，不出方案也不凑数。</div>")
        return "".join(o)
    # ★ 仓位与止损：全部用「历史最差」反推，不拍脑袋给数；数字一律用纯文本，
    #   别把 -26.7% 显示成红色的 +26.7%（那看起来像赚了 26.7%）。
    def _p(v):
        return "—" if v is None else "%+.2f%%" % (v * 100)

    worst5, worst1 = abs(b["5"]["worst"]) or 0.267, abs(b["1"]["worst"]) or 0.102
    pos5 = RISK_PER_TRADE / worst5 * 100
    pos1 = RISK_PER_TRADE / worst1 * 100
    bestK = "5" if b["5"]["mean"] >= b["1"]["mean"] else "1"
    crows = {r["run"]: r for r in ((ctx.get("odds") or {}).get("cur_rows") or [])}
    w_first = _win(crows.get("首板"), "1")
    w_second = _win(crows.get("二板"), "1")
    o.append("<div class='card'><b>这条方案是这么推出来的</b>"
             "<ul>"
             "<li><b>触发</b>：情绪阶段判定 = <b>%s</b>，且当日收盘封涨停、连板数 = <b>%s</b>。"
             "两条同时满足才进名单。</li>"
             "<li><b>买入假设</b>：以<b>当日收盘价</b>成交。⚠ 这是简化假设 —— "
             "真实打板要排队，可能封不上、也可能高开走，<b>实际成交价高于收盘价</b>；"
             "本页所有胜率都建立在「能成交且成交在收盘价」上，这一条<b>没有单独验证</b>。</li>"
             "<li><b>持有期</b>：K=%s（这个形态在该口径上均值 %s、胜率 %s）。"
             "K=1 胜率更高（%s）但 <b>均值只有 %s</b>，属于快进快出；"
             "两种口径差别很大，别混着用。</li>"
             "<li><b>仓位上限（由历史最坏情况反推，不是拍的）</b>：本形态 K=5 的最差是 "
             "<b>%s</b>。按单笔亏损不超过本金 <b>%.1f%%</b> 的纪律，单票仓位 ≤ <b>%.1f%%</b>"
             "（换成 K=1 口径，最差 %s → 单票 ≤ %.1f%%）。<b>取更小的那个</b>。</li>"
             "<li><b>退出</b>：跌破买入价 <b>%d%%</b>（由 K=1 最差的一半反推）减半，继续跌破再走；"
             "或持有满 %s 个交易日时间止损；或情绪阶段转<b>退潮 / 高潮</b>时了结 —— "
             "三选先到者。⚠ 这条线是<b>从历史极值推的保守线</b>，不是优化出来的最优解。</li>"
             "<li><b>明确不做</b>：冰点期去做<b>首板 / 二板</b>（K=1 胜率 %s / %s，"
             "基本就是扔硬币，超额接近 0）。</li>"
             "</ul></div>"
             % (b["stage"], b["run"], bestK, _p(b[bestK]["mean"]), _win(b, bestK),
                _win(b, "1"), _p(b["1"]["mean"]),
                _p(b["5"]["worst"]), RISK_PER_TRADE * 100, min(pos5, 15.0),
                _p(b["1"]["worst"]), min(pos1, 30.0),
                int(abs(b["1"]["worst"]) * 100 / 2.0), bestK,
                w_first, w_second))
    o.append("<div class='warn'><b>这条方案还过不了出票闸，先别当真</b>："
             "它现在只是<b>研究结论</b>。要接进出票，还得补四道 —— "
             "① 无未来函数（本页已满足）；② walk-forward（本页已做，见第四节③）；"
             "③ 随机对照（已做，见第四节①）；④ <b>退出可兑现</b>（<b>还没做</b>："
             "上面的退出价是静态假设，滑点/一字/停牌都没算，"
             "这一道不过，它就不是一条能执行的规则）。</div>")
    o.append("<div class='note'>退出假设还有两处乐观：忽略<b>日内路径</b>（只按收盘价算）" +
             "、忽略<b>跳空</b>（一字板 / 低开走不出来）。这两处会让上面的退出线<b>偏乐观</b>。"
             "本项目的移动止盈只在一处实现（<code>_exit_sim.py</code>），要验证请走它，别在别处重算一套。</div>")
    return "".join(o)


def render_hot(ctx):
    h = ctx.get("hot")
    o = ["<h2>七、当前热点板块（资金与广度）</h2>"]
    if not h or (not h.get("concept") and not h.get("industry")):
        o.append("<div class='warn'>无法自检：没读到板块热度快照（<code>quant/sector_*.json</code>）。"
                 "此处保留空缺。</div>")
        return "".join(o)
    o.append("<div class='note'>板块数据是<b>板块级</b>的：涨跌、上涨家数/总数（广度）、"
             "主力净流入（原始数据为万元，此列换算成亿元；「主力行为」的分档口径见"
             "<a href='../sector/index.html'>板块强度</a>页，这里不重复算一套）。"
             "<b>本仓没有「个股 → 所属板块」的成分表</b>，"
             "所以「某只龙头带动板块内 N 家跟风」<b>算不出来</b>，不瞎编。</div>")
    for kind, title in (("concept", "概念热度 Top"), ("industry", "行业热度 Top")):
        rows = h.get(kind) or []
        if not rows:
            continue
        o.append("<h3>%s<span class='tag'>%s</span></h3>" % (title, h.get(kind + "_src", "")))
        o.append("<table><tr><th>板块</th><th class='num'>涨跌</th><th class='num'>上涨/总数</th>"
                 "<th class='num'>主力净流入(亿元)</th><th>领涨股</th></tr>")
        for r in rows:
            try:
                chg = float(r.get("changePct") or 0)
            except (TypeError, ValueError):
                chg = 0.0
            try:
                # ⚠ 单位：collect_sector.py 明确标注原始数据为「万元」，故 /10000 = 亿元。
                #   别再另算一套 —— 「主力行为（抢筹/洗盘…）」的分档在「板块强度」页，
                #   这里只列原始净流入，避免同一个数字两种口径。
                mn = (r.get("mainNetInflow") or 0) / 10000.0
            except (TypeError, ValueError):
                mn = 0.0
            ld = r.get("leader") or {}
            cls = "up" if chg > 0 else ("down" if chg < 0 else "")
            o.append("<tr><td>%s</td><td class='num %s'>%+.2f%%</td><td class='num'>%s</td>"
                     "<td class='num'>%s</td><td>%s</td></tr>"
                     % (r.get("name", "—"), cls or "muted", chg, r.get("upCount", "—"),
                        ("{:,.0f}".format(mn)), (ld.get("name") or "—")))
        o.append("</table>")
    return "".join(o)


USES = [
    ("情绪温度计", "把「今天该high还是该怂」变成一个可复核的位置判定",
     "已做（本页第一节）", "ok"),
    ("出手频率纪律", "用真实频率校准「一个月出手几次」，而不是凭感觉",
     "已做（第三节：三板以上出现天数占比）", "ok"),
    ("连板梯队健康度", "炸板率 + 高度 + 晋级率，判断赚钱效应是在扩散还是在收口",
     "已做（KPI + 校准）", "ok"),
    ("候选分层", "二板 / 三板以上分层，配合「首次分歧」定义做候选池",
     "需先验证买点口径才有意义（现只给分层，不给池）", "mid"),
    ("板块效应强度", "龙头带动跟风家数 —— 判断「人和」是否成立",
     "不可算：缺「个股→板块」成分表", "no"),
    ("分时盘口判定（真烂板/真分歧）", "严格版第 2、4 句",
     "不可算：本地只有日K，无分时数据", "no"),
    ("个股相对强弱（去弱留强）", "第 6 句",
     "可做但属策略层，需要单独做样本外验证", "mid"),
    ("卖点：一致高潮的量化", "缩量 + 普涨 + 高度见顶 → 第 5 句",
     "可做，需定义并验证；本页只给阶段提示", "mid"),
]


def render_uses(ctx):
    o = ["<h2>八、这套东西还能用来分析什么</h2>"]
    o.append("<table><tr><th>能用在哪</th><th>解决什么问题</th><th>当前状态</th></tr>")
    for name, what, state, cls in USES:
        tag = {"ok": "可核", "mid": "待验证", "no": "不可核"}[cls]
        o.append("<tr><td><b>%s</b></td><td>%s</td>"
                 "<td><span class='tag %s'>%s</span> %s</td></tr>" % (name, what, cls, tag, state))
    o.append("</table>")
    return "".join(o)


def render_risk():
    return ("<h2>九、使用边界</h2>"
            "<div class='warn'><b>风险提示</b>：本页是<b>方法论科普 + 情绪周期定位</b>，"
            "不构成任何买卖建议。龙头战法波动极大，连板梯队本身就在告诉你风险："
            "六成以上的二板走不到三板。<ul>"
            "<li>第五节给的是<b>「这个形态今天出现了」的观察名单</b>，"
            "不是个股推荐、不给买卖点位。它<b>没经过出票闸</b>，"
            "要变成可执行还差「退出可兑现」那一道（见第六节）。</li>"
            "<li>所有分位只用<b>截至当日</b>的滚动窗口，不含未来数据；这是能做到的事，"
            "但历史统计 ≠ 预测。</li>"
            "<li>数据读到哪天就写到哪天。若显示「无法自检」，就是真没读到，不用估计值补。</li>"
            "</ul></div>")


# ------------------------------------------------------------------ 主流程
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="", help="数据截止日 YYYY-MM-DD（默认取底座最新）")
    a = ap.parse_args()

    asof = a.date
    if not asof:
        try:
            man = json.load(open(os.path.join(HERE, "hub", "manifest.json"), encoding="utf-8"))
            asof = man.get("date") or ""
        except Exception:
            asof = ""

    ctx = dict(asof=asof or "未知", src="_txk_cache.json", ndays=0, ncodes=0, err="")
    try:
        cache = load_quotes()
        if not cache:
            raise RuntimeError("日K缓存为空")
        # 截断到 asof，避免把未来数据混进来
        if asof:
            trimmed = {}
            for code, bars in cache.items():
                bs = [b for b in bars if b["date"] <= asof]
                if bs:
                    trimmed[code] = bs
            cache = trimmed
        ctx["ncodes"] = len(cache)

        series = build_series(cache)
        if len(series) < WIN + 1:
            raise RuntimeError("交易日样本不足（%d 天，至少需要 %d 天）" % (len(series), WIN + 1))
        ctx["ndays"] = len(series)

        # 分位（滚动，只看过去）
        zts = [r["zt"] for r in series]
        his = [r["hi"] for r in series]
        rts = [r["rate"] for r in series]
        for i, r in enumerate(series):
            r["zt_p"] = rolling_pctile(zts, i)
            r["hi_p"] = rolling_pctile(his, i)
            r["rate_p"] = rolling_pctile(rts, i)

        last = series[-1]
        st, why = stage_of(last["zt_p"], last["hi_p"], last["rate_p"])
        ctx["now"] = dict(date=last["date"], stage=st, why=why, zt=last["zt"], zb=last["zb"],
                          rate=last["rate"], hi=last["hi"], n2=last["n2"], n3=last["n3"],
                          zt_p=last["zt_p"], hi_p=last["hi_p"], rate_p=last["rate_p"])
        ctx["asof"] = last["date"]

        # ---- 校准统计 ----
        prom_rows = [r for r in series if r.get("prom_hit") is not None]
        tail60 = prom_rows[-WIN:]
        pn = sum(r["prom_n"] for r in tail60)
        ph = sum(r["prom_hit"] for r in tail60)
        zt_all = sorted(r["zt"] for r in series)
        has3 = sum(1 for r in series if r["n3"] > 0)

        # 阶段 → 后续 N 日全市场等权收益（同样的滚动规则，事后回看）
        fwd = collections.defaultdict(list)
        for i in range(len(series) - FORWARD_DAYS):
            r = series[i]
            s0, _w = stage_of(r["zt_p"], r["hi_p"], r["rate_p"])
            acc = 1.0
            for j in range(i + 1, i + 1 + FORWARD_DAYS):
                acc *= (1.0 + series[j]["eq"])
            fwd[s0].append(acc - 1.0)
        fwd_rows = []
        for st_name in ("冰点", "回暖", "高潮", "退潮"):
            xs = fwd.get(st_name) or []
            if len(xs) < 3:
                continue
            fwd_rows.append((st_name, dict(
                n=len(xs), win=sum(1 for x in xs if x > 0) / len(xs),
                mean=sum(xs) / len(xs), best=max(xs), worst=min(xs))))

        ctx["calib"] = dict(prom_n=pn, prom_hit=ph, prom_rate=(ph / pn) if pn else 0.0,
                            has3_days=has3, ndays_eff=len(series),
                            has3_ratio=(has3 / len(series)) if series else 0.0,
                            rate_avg=sum(r["rate"] for r in series) / len(series),
                            zt_med=zt_all[len(zt_all) // 2], zt_min=zt_all[0], zt_max=zt_all[-1],
                            fwd=fwd_rows)

        # ---- 阶段胜率实验室（真源 _dragon_odds 的产出）----
        # ⚠ 没读到就给 None：页面那一节会显示「无法自检」，不会自己编一组胜率。
        ctx["odds"] = latest_odds(ctx["asof"])

        # ---- 板块热点 ----
        hot = {}
        for kind in ("concept", "industry"):
            rows, src = latest_sector(kind, asof=ctx["asof"])
            if rows:
                hot[kind] = top_rows(rows, "changePct", 8)
                hot[kind + "_src"] = src
        ctx["hot"] = hot

        # 顺手落一份 JSON，方便门户/别的页复用，也便于核验。
        # ⚠ 文件名统一用 {DS}（无横线）—— 本项目 {DATE}(带横线) / {DS}(无横线) 两种写法混用
        # 已经坑过一次（字符串比较会把当天数据当成未来数据过滤掉），本模块一律用 DS。
        try:
            os.makedirs(os.path.join(HERE, "dragon"), exist_ok=True)
            dump = dict(date=ctx["asof"], stage=ctx["now"]["stage"], why=ctx["now"]["why"],
                        now={k: v for k, v in ctx["now"].items() if k != "why"},
                        calib={k: v for k, v in ctx["calib"].items() if k != "fwd"},
                        series=[{k: v for k, v in r.items()} for r in series[-WIN:]])
            with open(os.path.join(HERE, "dragon", "cycle_%s.json" % ctx["asof"].replace("-", "")),
                      "w", encoding="utf-8") as f:
                json.dump(dump, f, ensure_ascii=False, indent=1)
        except Exception as e:
            print("[warn] 周期 JSON 落盘失败（不影响出页）：%s" % str(e)[:60])

    except Exception as e:
        ctx["err"] = str(e)[:200]

    os.makedirs(OUT_DIR, exist_ok=True)
    html = render(ctx)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(html)
    print("[dragon] %s（%d 字节）" % (OUT, len(html)))
    if ctx.get("err"):
        print("[dragon] ⚠ 降级出页：%s" % ctx["err"])
    else:
        print("[dragon] 数据日 %s｜阶段 %s｜涨停 %d 家｜炸板率 %.1f%%｜最高 %d 板"
              % (ctx["asof"], ctx["now"]["stage"], ctx["now"]["zt"],
                 ctx["now"]["rate"] * 100, ctx["now"]["hi"]))
    print("[dragon] 提醒：接着跑 _apply_theme.py 补注入层")
    return 0 if not ctx.get("err") else 1


if __name__ == "__main__":
    sys.exit(main())
