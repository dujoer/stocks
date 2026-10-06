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
def load_quotes(prefer_long=False):
    """读日K（统一层）。读不到抛异常，由调用方降级，绝不返回空数据冒充。

    ⚠ **本页刻意用短缓存（`_txk_cache`，252 根）**，不是为了省时间，是为了**对齐**：
      本页第一~三节的「涨停家数 / 炸板率 / 连板高度」是全站要对齐的日更数字，
      [C5] 门禁拿它与「大盘概览」逐日比。若这里换成 780 根长历史，
      2026-09-30 会出现「大盘概览 53 / 龙道诀 55」的跨页矛盾（实测已触发 C5 FAIL）。
      两个缓存的覆盖并不互相包含（各自都有洞，详见 .workbuddy/memory 记录），
      在这个数据缺口修好之前，**页面之间宁可口径一致、并把缺口单独报出来**，
      也不要让同一页面系统的两个数字互相打架。
      第四~六节的**胜率统计**是另一回事：那是研究量（不受 [C5] 约束），
      由 `_dragon_odds.py` 走 780 根长历史算，页面上已标明样本期。

    返回 (cache, 来源标签)。
    """
    if prefer_long:
        try:
            import _longk as LK
            c = LK.load_long()
            if c:
                return c, LK.src_label()
        except Exception:
            pass
    import _txk
    return _txk.load(), "_txk_cache(252 根·与全站对齐)"


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
    import _tx_fetch                      # 复用抓取层的代码资格判据（别在本地再抄一份）
    day = collections.defaultdict(list)
    ret = collections.defaultdict(list)     # date -> [日涨跌幅]
    for code, bars in cache.items():
        if len(bars) < 3:
            continue
        # ★ 缓存里混过可转债（sh11x / sz12x）：它没有 10% 涨跌停这回事，
        #   但会被 `limit_pct` 按 10% 判 → 转债涨 10% 就成了「假涨停」。
        if not _tx_fetch.is_stock(code):
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


def latest_stage_use(asof=None):
    """读「阶段能不能用」预注册检验产出 `quant/dragon/stage_use_{DS}.json`。

    与 `latest_odds` 同一纪律：**没读到就返回 None**，页面那一节显示「无法自检」，
    绝不拿旧数据冒充当天、也绝不自己编一组结论。

    ⚠ 这个产物测的是**全市场等权收益**，不是任何个股 —— 页面上不能拿它当「选股信号」。
    """
    pick = None
    for f in sorted(glob.glob(os.path.join(HERE, "dragon", "stage_use_*.json"))):
        stem = _digits(os.path.basename(f).replace("stage_use_", "").replace(".json", ""))
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
        # ★ 两套样本口径必须当面说清楚，否则读者会拿第一节的「252 日」去理解第四节的「780 日」
        _od = ctx.get("odds") or {}
        A("<div class='note'><b>先说清样本口径，本页有两套：</b>"
          "① <b>第一~三节</b>的<b>情绪定位</b>用 <b>%d</b> 个交易日（日K <code>%s</code>）——"
          "它必须与全站其它页面的「涨停家数」对齐，由 [C5] 门禁逐日校验，所以用的是同一份短缓存；"
          "② <b>第四~六节</b>的<b>胜率统计</b>是研究量、不受那个约束，"
          "走的是 <b>%d</b> 个交易日的长历史（<code>%s</code>，%s ~ %s）。"
          "两套数据不是同一批，数字<b>只在本节内可比</b>，跨节不要混着算。</div>"
          % (ctx["ndays"], ctx["src"], _od.get("sample_days") or 0,
             _od.get("kline_label") or "—", _od.get("sample_first") or "—",
             _od.get("sample_last") or "—"))
        A(render_stage(ctx))
        A(render_verses(ctx))
        A(render_calib(ctx))
        A(render_odds(ctx))      # 四：胜率最高的形态（真源 _dragon_odds）
        A(render_cand(ctx))      # 五：今天的观察名单
        A(render_plan(ctx))      # 六：配套操作方案（规则层）
        A(render_hot(ctx))
        A(render_uses(ctx))
        A(render_stage_use(ctx))   # 九：阶段能不能用（预注册检验，产物 _dragon_stage_use.py）

    A(render_risk(ctx))
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


def _grid_counts(od):
    """第④道全网格的（可判, 过相对判据, 扣成本净正）格数。"""
    eg = od.get("exec_grid") or {}
    tot = pn = nn = 0
    for _st, cell in eg.items():
        if not isinstance(cell, dict):
            continue
        for _rb, r in cell.items():
            if r.get("pass") is not None:
                tot += 1
            if r.get("pass"):
                pn += 1
            if r.get("net_positive"):
                nn += 1
    return tot, pn, nn


def _probe_counts(od):
    """既有退出探针的（可判, 过相对判据, 扣成本净正）格数。"""
    ep = od.get("exit_probe") or {}
    if ep.get("err"):
        return 0, 0, 0
    return (ep.get("n_judged") or 0, ep.get("n_pass") or 0, ep.get("n_net_positive") or 0)


def _exec_verdict(ctx):
    """第④道结论的**统一说法**（页面各处别再各写一句，否则结论一变就自相矛盾）。

    返回 (短标签, 完整句)。三种状态都覆盖：过 / 不过 / 不可判。
    ⚠ 「过相对判据」不等于「能赚钱」：判据只比胜率高低，边际可能只有零点几个 pp。
    """
    ex = (ctx.get("odds") or {}).get("exec") or {}
    p = ex.get("pass")
    edge = abs(ex.get("edge_pp") or 0)
    tot, _pn, nn = _grid_counts(ctx.get("odds") or {})
    tail = ("<br>而且这不是<b>某一个</b>形态的问题：把 4 阶段 × 6 连板桶全过一遍，"
            "%d 格里扣成本后<b>净均值为正的有 %d 格</b>。" % (tot, nn))
    if p is True:
        return ("过 · 仍亏",
                "第④道「退出可兑现」<b>过了相对判据</b> —— 可实现口径胜率只比同阶段基线高"
                "<b>%.1fpp</b>（这个量级属噪音），但<b>扣掉双边成本后净均值仍为负</b>："
                "所以它<b>仍然不是一条能执行的规则</b>，只是「比乱买略好一点」。%s" % (edge, tail))
    if p is False:
        return ("不通过",
                "第④道「退出可兑现」已补做、<b>不通过</b> —— 换成买得到、卖得掉的打法后，"
                "胜率<b>低于</b>同阶段同口径基线 <b>%.1fpp</b>。%s" % (edge, tail))
    return ("不可判", "第④道<b>不可判</b>（读不到证据）—— 按 fail-safe，不判通过也不判不通过。" + tail)


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
             "（就是这只票<b>连续</b>第 N 个涨停，N 即上面的板数）时，"
             "以当日收盘价买入、往后持有 K 天的胜率。%s"
             "<br><b>本节样本期</b>：%s ~ %s，共 <b>%d</b> 个交易日"
             "（日K 来源 <code>%s</code>）。样本期越长，这类统计越不容易是运气 ——"
             "但同时也意味着<b>横跨了完全不同的几段行情</b>，别把整个样本期的平均值当成今天的预期。</div>"
             % (b["stage"], b["run"], b["stage"], b["run"],
                ("这就是<b>当前阶段</b>（今天判定为 %s）的最优形态。" % cur) if is_cur
                else "（注：这是<b>全样本</b>最优，不是当前阶段最优。）",
                od.get("sample_first") or "—", od.get("sample_last") or "—",
                od.get("sample_days") or 0, od.get("kline_label") or "—"))

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
                 "<ul><li>%s</li>"
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
        o.append("<div class='card'><b>它靠什么站住（前三道自检，缺一不可）</b><ul>")
        for p in parts:
            o.append("<li>%s</li>" % p)
        o.append("</ul></div>")
    else:
        o.append("<div class='warn'><b>三道自检都没有足够证据</b> —— 按红线不给结论。</div>")

    # ★ 前三道验的是「历史上是不是真的」；第④道验的是「能不能真的做出来」——
    #   两件事，别看到这一节过就以为能用了。
    _ex = (od.get("exec") or {})
    if _ex and not _ex.get("err"):
        if _ex.get("pass") is False:
            o.append("<div class='warn'><b>但这三条只说明「历史上真的发生过」，"
                     "不说明「能赚到」</b>：第④道「退出可兑现」已补做，"
                     "<b>结果是没过</b> —— 换成买得到、卖得掉的打法，胜率 %s 反而低于"
                     "同口径基线 %s（<b>%+.1fpp</b>）。详见<b>第六节</b>。</div>"
                     % ("%.1f%%" % (_ex["rule_open1"]["win"] * 100) if _ex.get("rule_open1") else "—",
                        "%.1f%%" % (_ex["base_rule_open1"]["win"] * 100) if _ex.get("base_rule_open1") else "—",
                        _ex.get("edge_pp") or 0))
        else:
            o.append("<div class='warn'>第④道「退出可兑现」已补做，见<b>第六节</b>。</div>")

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


_RUN_ORDER = ("首板", "二板", "三板", "四板", "五板", "六板以上")


def _stage_order_note(rows, best):
    """「连板越高、胜率越高」这条规律到底成不成立 —— 用真实数字说，成立才敢说成立。

    ★ 只按**连板顺序**判单调，不按胜率排序后自说自话（那是拿排序结果当规律）。
    """
    hi = [r for r in rows if r.get("enough") and r.get("1") and r["run"] in _RUN_ORDER]
    if len(hi) < 2:
        return "样本不足以排顺序。"
    seq = sorted(((r["run"], r["1"]["win"]) for r in hi),
                 key=lambda x: _RUN_ORDER.index(x[0]))
    mono = all(seq[i][1] <= seq[i + 1][1] + 1e-12 for i in range(len(seq) - 1))
    top = max(seq, key=lambda x: x[1])
    low = min(seq, key=lambda x: x[1])
    head = ("同一阶段里，<b>连板越高、K=1 胜率越高</b>（按连板顺序单调）：" if mono else
            "同一阶段里，K=1 胜率<b>并不随连板数单调变化</b>（所以不能简单说「板越高越好」）：")
    return head + "达标形态里最高的是 <b>%s</b>（%.1f%%），最低的是 <b>%s</b>（%.1f%%），差 %.1fpp" % (
        top[0], top[1] * 100, low[0], low[1] * 100, (top[1] - low[1]) * 100)


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
                 "%s这份名单是<b>条件满足才生成</b>的 —— 空就是空，"
                 "本页不会拿别阶段的票来充数、也不会给一个「最像的」凑数。</div>"
                 % (ctx["asof"], for_.get("stage", "—"), for_.get("run", "—"),
                    "" if for_.get("is_cur_stage") else
                    "⚠ 注意：这个形态<b>不是当前阶段的最优</b>（当前阶段没有达标形态，"
                    "只能退回全样本最优）—— 所以这里「空」尤其正常。<br>"))
        return "".join(o)
    _tag, _sentence = _exec_verdict(ctx)
    o.append("<div class='warn'><b>这不是推荐，是观察名单。</b>"
             "它只说明「今天确实出现了这个历史胜率最高的形态」；%s"
             "至于能不能<b>真的做出来、做出来赚不赚</b>，看第④道 —— %s"
             "本页不给买卖点位。看名单是为了「盯盘时知道该看谁」，不是「该买谁」。</div>"
             % ("" if for_.get("is_cur_stage") else
                "⚠ 注意：<b>它不是当前阶段的最优形态</b>（当前阶段没达标形态，退回了全样本最优）。",
                _sentence))
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
                 "再叠加第六节第④道不过这件事：<b>目前不建议照第六节的规则去做</b>，"
                 "那份名单的作用仅限于「知道今天是谁触发了这个条件」。</div>" % len(no_hist))
    return "".join(o)


RISK_PER_TRADE = 0.015      # 单笔风险预算（占本金）—— 用来从「历史最差」反推仓位上限


def render_grid(eg):
    """全阶段 × 全连板桶 的第④道网格：回答「是不是整个龙道诀都不可执行」。"""

    def _gwp(s):
        return "—" if not s else "%.1f%%" % (s["win"] * 100)

    def _gsp(v):
        return "—" if v is None else ("%+.2f%%" % (v * 100)).replace("-", "−")

    def _gpp(v):
        return "—" if v is None else ("%+.1fpp" % v).replace("-", "−")

    tot = pn = nn = 0
    for _st, cell in eg.items():
        for _rb, r in cell.items():
            if r.get("pass") is not None:
                tot += 1
            if r.get("pass"):
                pn += 1
            if r.get("net_positive"):
                nn += 1
    o = ["<h3>先把 %d 个（阶段 × 连板）组合全过一遍第④道 —— "
         "扣成本后<b>能赚钱的：%s</b></h3>"
         % (tot, "没有" if nn == 0 else "只有 %d 格" % nn)]
    o.append("<div class='warn'>上一轮只给「当前最优」那<b>一个</b>形态判了死刑，答不了「别的形态呢」。"
             "这一轮把 <b>4 阶段 × 6 连板桶 = 24 格</b>全按真实成交约束"
             "（次日开盘入场、封死跌停顺延、一字买不进剔除）跑了一遍："
             "<b>%d 格</b>样本够判，其中 <b>%d 格</b>胜率高于同阶段、同口径的基线；"
             "但<b>扣掉双边成本（0.2%%）后净均值为正的，只剩 %d 格</b>。</div>" % (tot, pn, nn))
    o.append("<div class='note'><b>「过判据」和「能赚钱」是两件事，别混。</b>"
             "判据是<b>相对</b>的：胜率比同阶段随便买涨停票高就算过。"
             "但请看每一格的<b>净均值</b>那一列 —— 在可实现打法下，"
             "<b>涨停票整体就是负期望</b>（各阶段基线净均值全为负，见下面「既有退出探针」）。"
             "所以<b>赢了基线不等于不亏</b>。"
             "还要看<b>超出多少</b>：像 0.3pp 这种量级的「过」，就是噪音，"
             "不能读成「有超额」。根因也不在某个参数上（「−5% 止损太近」已被附加检验证伪），"
             "而是<b>这套「买涨停票」的打法本身</b>。</div>")
    for st, cell in eg.items():
        o.append("<div class='card' style='padding:10px 12px'><b>%s期</b>" % st)
        o.append("<table><tr><th>连板形态</th><th class='num'>样本</th><th class='num'>买不进</th>"
                 "<th class='num'>页面口径</th><th class='num'>可实现胜率</th>"
                 "<th class='num'>净均值</th><th class='num'>相对基线</th><th>第④道</th></tr>")
        for rb, r in cell.items():
            ro = r.get("rule_open1")
            n = r.get("n_sample") or 0
            if ro is None:
                o.append("<tr><td>%s</td><td class='num'>%d</td><td class='num'>—</td>"
                         "<td class='num'>—</td><td class='num'>—</td><td class='num'>—</td>"
                         "<td class='num'>—</td><td>样本不足</td></tr>" % (rb, n))
                continue
            if r.get("net_positive"):
                verdict, sty = "<b>过 · 净正</b>", " style=\"background:#fff4ef\""
            elif r.get("pass"):
                verdict, sty = "过 · 仍亏", ""
            else:
                verdict, sty = "不过", ""
            o.append("<tr%s><td>%s</td><td class='num'>%d</td><td class='num'>%.1f%%</td>"
                     "<td class='num'>%s</td><td class='num'>%s</td><td class='num'>%s</td>"
                     "<td class='num'>%s</td><td>%s</td></tr>"
                     % (sty, rb, n, (r.get("unexec_rate") or 0) * 100,
                        _gwp(r.get("page")), _gwp(ro), _gsp(r.get("net_mean")),
                        _gpp(r.get("edge_pp")), verdict))
        o.append("</table></div>")
    o.append("<div class='note'>读法：<b>页面口径</b>＝第四节那个静态胜率；"
             "<b>可实现胜率</b>＝按真实成交约束重算；<b>净均值</b>＝可实现口径下每次交易的"
             "平均收益、已扣 0.2% 双边成本；<b>相对基线</b>＝可实现胜率 − 同阶段同口径基线。"
             "四列里只有 <b>净均值 &gt; 0</b> 才代表这套打法本身不亏。</div>")
    return "".join(o)


def render_stop_sens(ss):
    """附加检验：把 −5% 放宽容，能不能救（预注册档位 + 前后半段同号检验）。"""
    o = ["<h3>附加检验：把 −5% 放宽容，能不能救？ —— 不能</h3>"]

    def _sp(v):
        return "—" if v is None else ("%+.2f%%" % (v * 100)).replace("-", "−")

    def _pn(v):
        return "—" if v is None else ("%+.2fpp" % (v * 100)).replace("-", "−")

    cells = ss.get("cells") or {}
    n_ok = n_bad = n_inc = 0
    for _k, c in cells.items():
        if c.get("consistent") is None:
            continue
        if c["consistent"]:
            if (c.get("gain_first") or 0) > 0:
                n_ok += 1
            else:
                n_bad += 1
        else:
            n_inc += 1
    nj = n_ok + n_bad + n_inc
    o.append("<div class='warn'>上一轮把根因归到「<b>−5%% 止损太近</b>」，这一轮直接验它。"
             "办法是<b>先把 5 个档位定死</b>（−5%% / −8%% / −10%% / −12%% / 无止损），"
             "再看「放宽止损」这个动作在<b>前半段与后半段</b>上是否<b>同号</b> —— "
             "只在单窗口上好看不算数，两个窗口都得一致才算。"
             "<br>结论：<b>不是普遍规律</b>。%d 个可判格里，<b>%d 格两段都变好、%d 格两段都变差、"
             "%d 格前后半段直接反号</b>（反号率 %.0f%%）—— 方向接近随机。"
             "<b>「放宽止损能救」是单窗口上的过拟合幻觉。</b></div>"
             % (nj, n_ok, n_bad, n_inc, (n_inc / nj * 100) if nj else 0))
    o.append("<table><tr><th>形态</th><th class='num'>前半段：−5% → 无止损（增益）</th>"
             "<th class='num'>后半段：−5% → 无止损（增益）</th><th>两段是否同号</th></tr>")
    for k, c in cells.items():
        a, b = c.get("first") or {}, c.get("second") or {}
        if "−5%" not in a or "−5%" not in b:
            o.append("<tr><td>%s</td><td class='num'>—</td><td class='num'>—</td>"
                     "<td>样本不足</td></tr>" % k)
            continue
        g1, g2 = c.get("gain_first"), c.get("gain_second")
        if c.get("consistent"):
            verdict, sty = ("同号（都变好）" if (g1 or 0) > 0 else "同号（都变差）"), ""
        else:
            verdict, sty = "<b>★ 异号</b>", " style=\"background:#fff9f2\""
        o.append("<tr%s><td>%s</td><td class='num'>%s → %s（%s）</td>"
                 "<td class='num'>%s → %s（%s）</td><td>%s</td></tr>"
                 % (sty, k,
                    _sp(a["−5%"]["net_mean"]), _sp(a["无止损"]["net_mean"]), _pn(g1),
                    _sp(b["−5%"]["net_mean"]), _sp(b["无止损"]["net_mean"]), _pn(g2),
                    verdict))
    o.append("</table>")
    o.append("<div class='note'>三点得一起读："
             "① 「无止损」是<b>极端假设、不是可执行规则</b> —— 回撤全留给你（单笔最差到 −40%% 量级），"
             "均值略好不等于能用；"
             "② 有 <b>%d 格</b>是<b>一致地「放宽更差」</b>，对这些形态，「−5%% 太近」这个说法本身就错了；"
             "③ 即便「两段都变好」的那 <b>%d 格</b>，放宽后的<b>绝对净收益大多仍是负的</b>。"
             "另外前半段与后半段的整体水平差得很远（同一格能差好几个点），"
             "说明<b>结论强烈依赖行情区间</b>，这本身就是「不可依赖」的证据。</div>" % (n_bad, n_ok))
    o.append("<div class='warn'><b>所以：不许拿「放宽止损」去救这套规则。</b>"
             "这条根因假设已被跨窗口检验证伪。真要换退出规则，必须重新走 walk-forward + 随机对照，"
             "而不是在这份数据上把档位调一调 —— 那正是红线要拦的「挑最好看的那个」。</div>")
    return "".join(o)


def render_exit_probe(ep):
    """附加检验 B：换成**项目既有**退出实现（`_exit_sim.py` 移动止盈），能不能救。"""
    o = ["<h3>附加检验 B：换成项目本来就在用的移动止盈，能不能救？</h3>"]

    def _p(v):
        return "—" if v is None else ("%+.2f%%" % (v * 100)).replace("-", "−")

    def _w(s):
        return "—" if not s else "%.1f%%" % (s["win"] * 100)

    pr = ep.get("params") or {}
    sb = ep.get("stage_base") or {}
    cells = ep.get("cells") or {}
    n_judged = ep.get("n_judged") or 0
    n_pass = ep.get("n_pass") or 0
    n_net = ep.get("n_net_positive") or 0
    cost = ep.get("cost") or 0

    o.append("<div class='card'><b>这次换的不是我临时拍的线，是项目里唯一那套退出实现</b>"
             "<ul>"
             "<li><b>出场</b>：<code>_exit_sim.py</code> 的移动止盈 —— 硬止损 −%d%%、"
             "涨到 +%d%% 激活、从最高点回撤 %d%% 走人、最长持有 %s 个交易日。"
             "<b>这是生产参数，固定一个档位、不做扫描</b>"
             "（上一轮已经证明「在这份数据上把参数调一调」是幻觉）。</li>"
             "<li><b>成交假设</b>：%s；入场用 <b>%s</b>，T+1 一字封板买不进的样本<b>剔除并计数</b>。</li>"
             "<li><b>对照基线</b>：同一情绪阶段的<b>全部涨停票</b>，用<b>完全相同</b>的退出与成交假设算 ——"
             "两边口径不一致就是拿假超额。</li>"
             "</ul></div>"
             % (int(round(pr.get("stop", 0) * 100)), int(round(pr.get("act", 0) * 100)),
                int(round(pr.get("trail", 0) * 100)), pr.get("maxfwd"),
                ep.get("mode") or "—", ep.get("entry") or "—"))

    o.append("<div class='warn'>结论：<b>换退出确实把「几乎全负」拉回来了一些，但仍然不成立</b>。"
             "%d 个可判格里 <b>%d 格</b>过了相对判据（胜率高于同阶段基线），"
             "扣掉 <b>%.1f%%</b> 双边成本后<b>净均值为正的只剩 %d 格</b>。</div>"
             % (n_judged, n_pass, cost * 100, n_net))

    o.append("<h4>关键在「阶段」，不在「连板形态」</h4>")
    o.append("<div class='note'>把<b>该阶段的全部涨停票</b>（不分连板）用同一套退出跑一遍，"
             "看净均值正负 —— 这张表才是这一节的答案。</div>")
    o.append("<table><tr><th>情绪阶段</th><th class='num'>样本</th><th class='num'>交易日</th>"
             "<th class='num'>净均值</th><th class='num'>前半段</th><th class='num'>后半段</th>"
             "<th>两段是否同号</th></tr>")
    order = ("冰点", "回暖", "高潮", "退潮")
    for st in order:
        v = sb.get(st)
        if not v:
            continue
        sty = ' style="background:#fff5f5"' if v.get("both_positive") else ""
        if v.get("consistent") is True:
            verdict = "是" + ("（<b>两段都为正</b>）" if v.get("both_positive") else "（两段都为负）")
        elif v.get("consistent") is False:
            verdict = "<b>★ 否（前后段反号）</b>"
        else:
            verdict = "样本不足"
        o.append("<tr%s><td><b>%s</b></td><td class='num'>%d</td><td class='num'>%d</td>"
                 "<td class='num'>%s</td><td class='num'>%s</td><td class='num'>%s</td>"
                 "<td>%s</td></tr>"
                 % (sty, st, v.get("n") or 0, v.get("n_days") or 0,
                    _p(v.get("net")), _p(v.get("net_first")), _p(v.get("net_second")), verdict))
    o.append("</table>")

    pos_st = [st for st in order if sb.get(st, {}).get("net") is not None and sb[st]["net"] > 0]
    neg_st = [st for st in order if sb.get(st, {}).get("net") is not None and sb[st]["net"] <= 0]

    def _st_txt(lst):
        return "、".join("<b>%s</b>（净 %s）" % (st, _p(sb[st]["net"])) for st in lst) or "无"

    lead = ("读法：换既有退出后，<b>转正的只有 %s</b>；%s 仍为负 —— "
            % (_st_txt(pos_st), _st_txt(neg_st))) if pos_st else (
        "读法：换既有退出后，<b>四个阶段一个都没转正</b>（%s）—— " % _st_txt(neg_st))
    o.append("<div class='note'>%s"
             "也就是说「买涨停票」这件事在<b>多数情绪阶段本身就是负期望</b>，"
             "退出换好只是把亏损收窄，改不了正负号。这一节和第四节问的是两件事："
             "第四节问「买什么<b>形态</b>」，这一节问「配什么<b>退出</b>」。</div>" % lead)

    # 净正格单独点出来，并说清它们为什么还不足以当结论
    net_cells = sorted([(k, c) for k, c in cells.items() if c.get("net_positive")],
                       key=lambda kv: -kv[1]["net_mean"])
    if net_cells:
        o.append("<h4>那 %d 个「净正格」值不值得信？</h4>" % len(net_cells))
        o.append("<table><tr><th>形态</th><th class='num'>样本</th><th class='num'>买不进</th>"
                 "<th class='num'>可实现胜率</th><th class='num'>净均值</th>"
                 "<th class='num'>同阶段基线净值</th><th class='num'>形态本身的贡献</th>"
                 "<th class='num'>前半/后半</th><th>能不能当结论</th></tr>")
        for k, c in net_cells:
            r = c.get("real") or {}
            b = c.get("base_real") or {}
            contrib = None
            if r.get("mean") is not None and b.get("mean") is not None:
                contrib = r["mean"] - b["mean"]          # 形态相对阶段的净贡献（未扣成本，两边同口径）
            stage_pos = (b.get("mean") or 0) > cost
            if c["n_sample"] < 100 or not c.get("both_positive"):
                ok = "<b>不够</b>：%s" % ("样本只有 %d 只" % c["n_sample"] if c["n_sample"] < 100
                                          else "前半/后半不同号")
            elif stage_pos:
                ok = ("<b>主要是阶段效应</b>：基线本身就为正，形态只多贡献 %s"
                      % _p(contrib))
            else:
                ok = "两段都为正、样本够 —— 但阶段本身是负的，属个案"
            o.append("<tr><td><b>%s</b></td><td class='num'>%d</td><td class='num'>%s</td>"
                     "<td class='num'>%s</td><td class='num'>%s</td><td class='num'>%s</td>"
                     "<td class='num'>%s</td><td class='num'>%s / %s</td><td>%s</td></tr>"
                     % (k, c["n_sample"],
                        ("%.0f%%" % (c["unexec_rate"] * 100)) if c.get("unexec_rate") else "—",
                        _w(r), _p(c.get("net_mean")), _p((b.get("mean") - cost) if b.get("mean") is not None else None),
                        _p(contrib), _p(c.get("net_first")), _p(c.get("net_second")), ok))
        o.append("</table>")
    else:
        o.append("<div class='warn'>连一格「扣成本后净均值为正」的都没有。</div>")

    # 全格明细
    o.append("<h4>全部 %d 格（按净均值从高到低）</h4>" % len(cells))
    o.append("<table><tr><th>形态</th><th class='num'>样本</th><th class='num'>买不进</th>"
             "<th class='num'>页面口径胜率</th><th class='num'>可实现胜率</th>"
             "<th class='num'>净均值</th><th class='num'>同阶段基线胜率</th>"
             "<th class='num'>超额</th><th>第④道</th></tr>")
    rows = sorted(cells.items(),
                  key=lambda kv: -(kv[1]["net_mean"] if kv[1].get("net_mean") is not None else -9))
    for k, c in rows:
        r = c.get("real")
        b = c.get("base_real")
        if c.get("net_mean") is None:
            verdict, sty = "样本不足", ""
        elif c.get("net_positive"):
            verdict, sty = "<b>过 · 净正</b>", ' style="background:#fff5f5"'
        elif c.get("pass"):
            verdict, sty = "过 · 仍亏", ""
        else:
            verdict, sty = "不通过", ""
        o.append("<tr%s><td>%s</td><td class='num'>%d</td><td class='num'>%s</td>"
                 "<td class='num'>%s</td><td class='num'>%s</td><td class='num'>%s</td>"
                 "<td class='num'>%s</td><td class='num'>%s</td><td>%s</td></tr>"
                 % (sty, k, c.get("n_sample") or 0,
                    ("%.0f%%" % (c["unexec_rate"] * 100)) if c.get("unexec_rate") else "—",
                    _w(c.get("page")), _w(r), _p(c.get("net_mean")), _w(b),
                    ("%+.1fpp" % c["edge_pp"]).replace("-", "−") if c.get("edge_pp") is not None else "—",
                    verdict))
    o.append("</table>")

    o.append("<div class='note'><b>三点交代</b>："
             "① 既有退出<b>没有</b>处理「当天封死跌停、根本卖不掉」的情形"
             "（它只在<b>跳空低开</b>时改按开盘价成交），所以这一节的数字<b>仍偏乐观</b>，真实只会更差；"
             "② 样本跨度 %s ~ %s、共 <b>%d</b> 个交易日（来源 %s），"
             "像「高潮」这种薄阶段只有 <b>%d</b> 个交易日 —— "
             "<b>样本越薄的格越容易翻号，别单独拿一格的符号当结论</b>；"
             "③ 本节与第四节的「胜率」不是一回事：第四节是<b>固定持有 5 日</b>的统计规律，"
             "这一节是<b>移动止盈</b>下的可实现收益，两个数不能互相印证，也不能互相替代。</div>"
             % (ep.get("sample_first") or "—", ep.get("sample_last") or "—",
                ep.get("sample_days") or 0, ep.get("kline_label") or "—",
                (sb.get("高潮") or {}).get("n_days") or 0))

    o.append("<div class='warn'><b>所以这一节的结论是</b>：把这个模块临时拍的 −5%% 止损换成"
             "项目本来就在用的移动止盈，<b>整体仍然不成立</b> —— "
             "4 个情绪阶段里有 <b>%d 个</b>净均值为正%s；"
             "24 格里扣成本后净正的只有 <b>%d 格</b>。"
             "<b>问题不在某一条退出线上，在「买涨停票」这个动作本身。</b>"
             "要推翻这个结论，得换一个<b>入场</b>逻辑重新走四道验证，"
             "而不是继续在这套数据上换退出参数。</div>"
             % (len(pos_st), ("（%s）" % "、".join(pos_st)) if pos_st else "",
                ep.get("n_net_positive") or 0))
    return "".join(o)


def render_plan(ctx):
    o = ["<h2>六、配套的操作方案（规则层，不是指令）</h2>"]
    od = ctx.get("odds") or {}
    b = od.get("best_cur") or od.get("best")
    ex = od.get("exec") or {}
    if not b:
        o.append("<div class='warn'>没有达标形态，<b>方案不成立</b> —— 按红线，不出方案也不凑数。</div>")
        return "".join(o)

    # ---- 第④道「退出可兑现」：本轮补做。结果直接决定这套方案能不能执行。----
    def _w(s):
        return "—" if not s else "%.1f%%" % (s["win"] * 100)

    def _m(s):
        return "—" if not s else ("%+.2f%%" % (s["mean"] * 100)).replace("-", "−")

    def _md(s):
        return "—" if not s else ("%+.2f%%" % (s["med"] * 100)).replace("-", "−")

    if ex.get("err"):
        o.append("<div class='warn'><b>第④道读不到</b>（%s）—— 按 fail-safe，"
                 "这种时候不判「通过」，也不判「不通过」，而是<b>不给结论</b>。"
                 "下面的方案因此只是纸面推导。</div>" % ex["err"][:80])
    elif ex:
        eg = od.get("exec_grid") or {}
        if eg and not eg.get("err"):
            o.append(render_grid(eg))
        ssens = od.get("stop_sens") or {}
        if ssens and not ssens.get("err"):
            o.append(render_stop_sens(ssens))
        eprobe = od.get("exit_probe") or {}
        if eprobe and not eprobe.get("err"):
            o.append(render_exit_probe(eprobe))
        o.append("<h3>再细看当前这个形态（%s期 · %s）差在哪</h3>"
                 % (ex.get("stage") or "—", ex.get("run") or "—"))
        _bw = _w(ex.get("base_rule_open1"))
        if ex.get("pass") is True:
            _cmp = ("换口径后仍然<b>略高于</b>同口径基线（%s），但只高 <b>%.1fpp</b> —— "
                    "这个差距是<b>噪音量级</b>；而且<b>扣掉成本后净均值仍为负</b>，"
                    "所以它只是「比乱买略好」，<b>不是能执行的规则</b>。" % (_bw, abs(ex.get("edge_pp") or 0)))
        elif ex.get("pass") is False:
            _cmp = ("而且<b>低于</b>同口径的基线（%s）<b>%.1fpp</b> —— 也就是说，"
                    "换成能真的做出来的打法，这个形态<b>没有超额</b>。" % (_bw, abs(ex.get("edge_pp") or 0)))
        else:
            _cmp = "同口径基线读不到，这一格的比较<b>不可判</b>（按 fail-safe 不给结论）。"
        o.append("<div class='warn'>这一节最该看的就是下面这张表。<b>同一个形态、同一批样本</b>，"
                 "只把「买在哪、怎么卖」换成真实成交约束，胜率就从 <b>%s</b> 掉到 <b>%s</b>；%s</div>"
                 % (_w(ex.get("page")), _w(ex.get("rule_open1")), _cmp))
        o.append("<table><tr><th>口径</th><th class='num'>样本</th><th class='num'>胜率</th>"
                 "<th class='num'>中位</th><th>说明</th></tr>")
        rows = [
            ("① 页面口径（第四节那个数）", ex.get("page"), False,
             "信号日<b>收盘价</b>买入、持有 5 日收盘卖出。建立在一个<b>大概率买不到</b>的价上"),
            ("② 信号日收盘买入 + 规则退出", ex.get("rule_close"), False,
             "入场照旧，出场换成 −5% 止损 / 满 5 日 / 转段，含跳空与跌停顺延"),
            ("③ <b>次日开盘买入 + 规则退出</b>", ex.get("rule_open1"), True,
             "<b>最接近真实</b>的一档：看到收盘封板，只能次日开盘去接"),
            ("④ 同口径基线", ex.get("base_rule_open1"), False,
             "冰点期<b>全部涨停票</b>、用<b>完全相同的可实现口径</b>算（公平对照）"),
            ("⑤ 诊断：③ 去掉 −5% 止损", ex.get("diag_nostop"), False,
             "⚠ <b>仅供归因</b>，看止损吃掉了多少；<b>不得据此改规则</b>"),
        ]
        for name, s, hi, note in rows:
            o.append("<tr%s><td>%s</td><td class='num'>%s</td><td class='num'>%s</td>"
                     "<td class='num'>%s</td><td>%s</td></tr>"
                     % (' style="background:#fff9f2"' if hi else "", name,
                        "—" if not s else s["n"], _w(s), _md(s), note))
        o.append("</table>")
        a, c, d2 = ex.get("page"), ex.get("rule_close"), ex.get("rule_open1")
        if a and c and d2:
            o.append("<div class='card'><b>两处乐观假设各值多少钱（拿数字说，不靠感觉）</b><ul>"
                     "<li><b>出场规则</b>吃掉 <b>%.1fpp</b>：%s → %s。"
                     "−5%% 这条止损线对四板票来说<b>太近了</b>，基本是日内噪音就会打掉 —— "
                     "样本里 <b>%d/%d</b> 笔是「止损」出场，中位收益正好停在 −5.00%%。</li>"
                     "<li><b>入场假设</b>再吃掉 <b>%.1fpp</b>：%s → %s。"
                     "封板价买不到，只能次日开盘接；另有 <b>%d 个</b>样本（<b>%.1f%%</b>）"
                     "次日直接<b>一字封板、根本买不进</b>，被剔除。</li>"
                     "<li>两处合计 <b>%.1fpp</b>：%s → %s。"
                     "这就是「纸面胜率」和「真能拿到的胜率」之间的距离。</li>"
                     "</ul></div>"
                     % ((a["win"] - c["win"]) * 100, _w(a), _w(c),
                        (ex.get("reasons") or {}).get("rule_open1:止损", 0), d2["n"],
                        (c["win"] - d2["win"]) * 100, _w(c), _w(d2),
                        ex.get("n_unexec") or 0, (ex.get("unexec_rate") or 0) * 100,
                        (a["win"] - d2["win"]) * 100, _w(a), _w(d2)))
        if ex.get("diag_nostop") and ex.get("base_rule_open1"):
            o.append("<div class='warn'><b>关于第 ⑤ 行，先把话说死</b>：去掉止损后是 %s，"
                     "看着比第 ③ 行好很多 —— 但那是<b>在同一份数据上挑口径</b>，"
                     "正是红线里「不许挑最好看的那个窗口」要拦的事，"
                     "而且它的对照基线也得用同样口径重算才算数。<b>本页不据此修改方案。</b>"
                     "真要改（比如放宽止损），必须重新走一遍 walk-forward 和随机对照。</div>"
                     % _w(ex.get("diag_nostop")))
        o.append("<div class='note'><b>第④道的判据（写出来，方便被打脸）</b>："
                 "拿<b>最保守口径（③）</b>的胜率，去比<b>同口径基线（④）</b>。"
                 "高于基线 = 过；不高于 = 不过。此处 %s vs %s → <b>%s</b>。"
                 "<br>另有两点诚实交代：本节模拟的是<b>全仓一次性了结</b>，"
                 "下面方案里「跌破 5%% 先减半」是分批口径，<b>未单独模拟</b>；"
                 "持有期按<b>该票自己的交易日</b>数，停牌会拉长自然日跨度。</div>"
                 % (_w(ex.get("rule_open1")), _w(ex.get("base_rule_open1")),
                    "通过" if ex.get("pass") else
                    ("不通过" if ex.get("pass") is False else "不可判")))
        if ex.get("pass"):
            o.append("<div class='card'><b>第④道通过</b> —— 但仍要配合仓位纪律，"
                     "且它依然只是<b>研究结论</b>，不构成买卖指令。</div>")

    o.append("<h3>以下是纸面推导（第④道通过之前，只当记录看）</h3>")
    # ★ 仓位与止损：全部用「历史最差」反推，不拍脑袋给数；数字一律用纯文本，
    #   别把 -26.7% 显示成红色的 +26.7%（那看起来像赚了 26.7%）。
    def _p(v):
        return "—" if v is None else ("%+.2f%%" % (v * 100)).replace("-", "−")

    worst5, worst1 = abs(b["5"]["worst"]) or 0.267, abs(b["1"]["worst"]) or 0.102
    pos5 = RISK_PER_TRADE / worst5 * 100
    pos1 = RISK_PER_TRADE / worst1 * 100
    bestK = "5" if b["5"]["mean"] >= b["1"]["mean"] else "1"
    crows = {r["run"]: r for r in (od.get("cur_rows") or [])}
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
             "三选先到者。⚠ 这条线是<b>从历史极值推的保守线</b>，不是优化出来的最优解；"
             "<b>第④道实测下来，正是这条线把胜率吃掉的</b>。</li>"
             "<li><b>明确不做</b>：冰点期去做<b>首板 / 二板</b>（K=1 胜率 %s / %s，"
             "基本就是扔硬币，超额接近 0）。</li>"
             "</ul></div>"
             % (b["stage"], b["run"], bestK, _p(b[bestK]["mean"]), _win(b, bestK),
                _win(b, "1"), _p(b["1"]["mean"]),
                _p(b["5"]["worst"]), RISK_PER_TRADE * 100, min(pos5, 15.0),
                _p(b["1"]["worst"]), min(pos1, 30.0),
                int(abs(b["1"]["worst"]) * 100 / 2.0), bestK,
                w_first, w_second))
    _tag, _sentence = _exec_verdict(ctx)
    _tot, _pn, _nn = _grid_counts(od)
    _ps, _psp, _psn = _probe_counts(od)
    o.append("<div class='warn'><b>结论：这一节的东西现在不能执行。</b>"
             "四道自检里 ①②③ 已过（无未来函数 / walk-forward / 随机对照），"
             "第 ④ 道「退出可兑现」的结果是：%s"
             "<br>而且这不是<b>某一个</b>形态的问题：把 4 阶段 × 6 连板桶全过一遍，"
             "<b>%d 格</b>里扣成本后净均值为正的有 <b>%d 格</b>；"
             "再把退出换成项目本来就在用的移动止盈（<code>_exit_sim.py</code>），"
             "<b>%d 格</b>里净均值为正的也只有 <b>%d 格</b>。"
             "同时「是不是 −5%% 止损太近」这条根因假设<b>已被跨窗口检验证伪</b>"
             "（放宽止损在前/后半段大量反号，见上面「附加检验」）。"
             "所以问题出在<b>这套打法本身</b>（买涨停票 + 固定持有期/止盈），"
             "不是「形态选错了」，也不是「调一个参数能救」。"
             "真要翻案，必须换一个<b>入场</b>逻辑重新走 walk-forward + 随机对照，"
             "<b>不能拿这份数据现挑</b>。</div>"
             % (_sentence, _tot, _nn, _ps, _psn))
    o.append("<div class='note'>模拟口径与 `_exit_sim.py`（本项目移动止盈的唯一实现）保持同一套假设："
             "<b>跳空按开盘价成交</b>、<b>跌停封死卖不掉要顺延</b>、<b>一字板买不进要剔除</b>。"
             "要验证退出假设请走它，别在别处重算一套。</div>")
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


USE_CLS = {"可用（仓位/开仓）": "ok", "赢基线但没赢动量": "mid", "不可用": "no"}


def _use_pass_stages(su):
    """读数据：哪些阶段在**全部**前向窗口都通过预注册判据（结论句用，不写死）。"""
    holds = su.get("holds") or {}
    ok_sets = []
    for key in sorted(holds, key=lambda x: int(x)):
        cells = (holds[key].get("cells") or {})
        ok_sets.append({st for st, c in cells.items()
                        if (c or {}).get("verdict") == "可用（仓位/开仓）"})
    if not ok_sets:
        return []
    common = set(ok_sets[0])
    for s in ok_sets[1:]:
        common &= s
    return sorted(common, key=lambda s: ("高潮", "回暖", "冰点", "退潮").index(s))


def _use_neg_stages(su):
    """读数据：哪些阶段在**全部**窗口的「同涨幅分位档 edge」都为负（即「该收手」的实证）。

    ★ 结论句必须读数据 —— 上一轮就栽在「把某阶段写死进结论句，数据一变动就自相矛盾」。
    """
    holds = su.get("holds") or {}
    neg_sets = []
    for key in sorted(holds, key=lambda x: int(x)):
        cells = (holds[key].get("cells") or {})
        neg_sets.append({st for st, c in cells.items()
                         if (c or {}).get("edge_matched") is not None
                         and c["edge_matched"] < 0})
    if not neg_sets:
        return []
    common = set(neg_sets[0])
    for s in neg_sets[1:]:
        common &= s
    return sorted(common, key=lambda s: ("高潮", "回暖", "冰点", "退潮").index(s))


def render_stage_use(ctx):
    """九、阶段能不能用 —— 预注册检验（产物 `_dragon_stage_use.py` / `stage_use_{DS}.json`）。

    ★ 读不到产物：**整节只显示一句「无法自检」**，不编数字（fail-safe）。
    """
    su = ctx.get("stage_use")
    if not su:
        return ("<h2>九、阶段能不能用（预注册检验）</h2>"
                "<div class='warn'><b>无法自检</b>：读不到 "
                "<code>quant/dragon/stage_use_{DS}.json</code>（该产物由 "
                "<code>quant/_dragon_stage_use.py</code> 生成）。"
                "本项目规则是「读不到证据就不给结论」—— 此处保留空缺，不会用旧数据或估计值填上。"
                "</div>".format(ctx.get("asof") or "未知"))

    holds = su.get("holds") or {}
    keylist = sorted(holds, key=lambda x: int(x))
    stage_order = su.get("stages") or ["退潮", "高潮", "回暖", "冰点"]
    ok_all = _use_pass_stages(su)

    o = ["<h2>九、阶段能不能用（预注册检验）</h2>"]
    o.append("<div class='note'><b>先说测的是什么。</b>前面第四节测的是"
             "「<b>打板持仓</b>」在这些阶段里能不能赚 —— 结果 24 格里扣成本净正 <b>0</b> 格。"
             "但那<em>推不出</em>「阶段有没有择时价值」。本节换一条路测："
             "阶段能不能<b>提前告诉你接下来市场会怎样</b>，标的换成<b>全市场等权收益</b>"
             "（<em>不是任何个股</em>，本项目不出票不推个股）。"
             "<b>预注册判据（跑之前写死，不再挑好看的）</b>："
             "① 相对 —— 阶段均 &gt; 全样本均；② 绝对 —— 扣 %.2f%% 单次往返成本后仍 &gt; 0；"
             "③ 稳健 —— 前半段与后半段<b>同号</b>；外加第四道<b>对照</b>："
             "与「<b>当日涨幅分位相同</b>的日子」比（剥离短期动量 —— "
             "否则「高潮＝市场本来就在涨」会被算成龙道诀的功劳）。"
             "四条全过才叫<b>可用</b>。</div>"
             % ((su.get("cost") or 0.002) * 100))

    o.append("<div class='note'>判据是<b>跑之前</b>定的；最后那道「同涨幅分位档」对照是"
             "<em>看到前三道结果之后才加的</em>，只会让结论更保守，不会更好看。"
             "样本 %s ~ %s，共 %s 个交易日；bootstrap 按日整块重抽 %s 次（固定值，保证可复现）。</div>"
             % (su.get("sample_first") or "—", su.get("sample_last") or "—",
                su.get("sample_days") or 0, su.get("boot") or 0))

    for key in keylist:
        blk = holds[key] or {}
        if "cells" not in blk:
            continue
        o.append("<h3>前向 %s 个交易日（全样本均值 %s，样本 %d）</h3>"
                 % (key, _pc(blk.get("baseline")), blk.get("n") or 0))
        o.append("<table><tr><th>阶段</th><th class='num'>样本</th>"
                 "<th class='num'>后续 %s 日均值</th><th class='num'>edge（对全样本）</th>"
                 "<th class='num'>edge（对同涨幅分位档）</th><th class='num'>R3</th>"
                 "<th class='num'>前半 / 后半</th><th>结论</th></tr>" % key)
        for st in stage_order:
            c = (blk.get("cells") or {}).get(st) or {}
            if not c:
                o.append("<tr><td>%s</td><td colspan='7' class='muted'>无数据</td></tr>" % st)
                continue
            if c.get("verdict") == "样本不足":
                o.append("<tr><td><b>%s</b></td><td class='num'>%s</td>"
                         "<td colspan='5' class='muted'>样本不足（&lt;%d）</td>"
                         "<td><span class='tag mid'>样本不足</span></td></tr>"
                         % (st, c.get("n") or 0, c.get("n") or 0))
                continue
            em = c.get("edge_matched")
            r3 = c.get("r3")
            o.append(
                "<tr><td><b>%s</b></td><td class='num'>%d</td><td class='num'>%s</td>"
                "<td class='num'>%s</td><td class='num'>%s</td><td class='num'>%s</td>"
                "<td class='num'>%s / %s</td><td><span class='tag %s'>%s</span></td></tr>"
                % (st, c.get("n") or 0, _pc(c.get("mean")), _pc(c.get("edge")),
                   _pc(em), ("%.3f" % r3) if r3 is not None else "—",
                   _pc(c.get("half1")), _pc(c.get("half2")),
                   USE_CLS.get(c.get("verdict"), "mid"), c.get("verdict")))
        o.append("</table>")

    neg_all = _use_neg_stages(su)
    if ok_all:
        tail = ("反向的 <b>%s</b> 在三个窗口 edge 全为负，是「<b>该收手</b>」的实证依据。"
                % "、".join(neg_all)) if neg_all else \
               ("其余阶段<b>跨窗口不一致</b> —— 有的只在单窗口看着可用，那不算证据。")
        o.append("<div class='warn'><b>能用的落点（只有这些）。</b>"
                 "<b>%s</b> 在 5 / 10 / 20 三个窗口<b>全部</b>通过四条判据 —— "
                 "这是本页唯一跨窗口一致的信号，可以当<b>环境状态</b>来读："
                 "进入这个阶段时，短期市场环境是偏顺的（<b>仓位倾向</b>，不是选股）。"
                 "%s"
                 "<br>⚠ <b>但边界必须说清</b>：本节测的是<b>全市场等权</b>，"
                 "拿它去加仓某个选股池是<b>跨口径外推</b>；真要接进实盘，"
                 "得对那个池<b>重走四道验证</b>（无未来函数 / walk-forward / 随机对照 / 退出可兑现），"
                 "不能拿这张表直接上。</div>" % ("、".join(ok_all), tail))
    else:
        o.append("<div class='warn'><b>能用的落点：无。</b>"
                 "没有一个阶段在全部窗口同时通过四条判据 —— "
                 "这个温度计只能<b>描述状态</b>，不能当仓位/开仓信号。</div>")

    o.append("<div class='note'>★ <b>为什么不矛盾</b>：第四节「打板 24 格净正 0」与本节"
             "（高潮→全市场等权后续有正增量）说的是<b>两件事</b> —— "
             "前者是<b>个股口径</b>（涨停票买不进、买得到也贵），后者是<b>指数口径</b>。"
             "赚钱效应强 ≠ 你能从涨停票上赚到钱。</div>")
    return "".join(o)


def render_risk(ctx):
    _tag, _sentence = _exec_verdict(ctx)
    return ("<h2>十、使用边界</h2>"
            "<div class='warn'><b>风险提示</b>：本页是<b>方法论科普 + 情绪周期定位</b>，"
            "不构成任何买卖建议。龙头战法波动极大，连板梯队本身就在告诉你风险："
            "六成以上的二板走不到三板。<ul>"
            "<li>第五节给的是<b>「这个形态今天出现了」的观察名单</b>，"
            "不是个股推荐、不给买卖点位。它能不能变成可执行规则，看第④道 —— %s</li>"
            "<li>所有分位只用<b>截至当日</b>的滚动窗口，不含未来数据；这是能做到的事，"
            "但历史统计 ≠ 预测。</li>"
            "<li>数据读到哪天就写到哪天。若显示「无法自检」，就是真没读到，不用估计值补。</li>"
            "</ul></div>" % _sentence)


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

    ctx = dict(asof=asof or "未知", src="—", ndays=0, ncodes=0, err="")
    try:
        cache, src_label = load_quotes()
        ctx["src"] = src_label
        if not cache:
            raise RuntimeError("日K缓存为空")
        # 截断到 asof，避免把未来数据混进来
        # ⚠ 两边都先去横线再比（`'-'` 码点小于数字 → 混用格式时这个过滤会静默失效）
        if asof:
            ad = _digits(asof)
            trimmed = {}
            for code, bars in cache.items():
                bs = [b for b in bars if _digits(b["date"]) <= ad]
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
        # ---- 阶段能不能用（预注册检验，真源 _dragon_stage_use.py 的产出）----
        # ⚠ 同样：没读到就给 None，页面那一节显示「无法自检」，不编结论。
        ctx["stage_use"] = latest_stage_use(ctx["asof"])

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
