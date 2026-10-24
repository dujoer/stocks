#!/usr/bin/env python3
"""研报分析模块生成器（独立模块 web/research/）。

用户需求（2026-10-24）：「增加研报分析模块，记录研报时间，通过上传的和过去的信息，
将相关股票的情况进行分析，将胜率排序，以及是否可建仓，及相关的买卖点」。

实现：
  · 研报注册表 quant/research/reports.json（人工校读上传 PDF 入库，观点引用原文）；
  · 每份研报渲染独立分析页 report_{id}.html + 模块索引页 index.html（记录研报时间）；
  · 逐股分析全部用本地真实行情数据现算（不写死、不编造，样本不足如实标注）：
      - 近一年该股 N字形信号的「首次触及胜率」（+6%/-8%/10日，与回测 DEF 档同口径）；
      - 当前价格状态（MA20/MA60/52周分位/距60日高/20日均额；52周区间自 K 线缓存自算）；
      - 是否可建仓（大盘环境门控 + 趋势 + 位置 + 健康回撤）；
      - 参考买卖点（买点=回踩MA20，止损=-8%，目标1=+6%，目标2=60日局部高，取自真实K线）。
  · 观察池·非出票，不构成投资建议。
"""
from __future__ import annotations
import os, sys, json, argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _txk
import _mkt_emo as M
import build_n_shape as NS
import build_n_shape_backtest as BT

QUANT = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(QUANT)
REG_PATH = os.path.join(QUANT, "research", "reports.json")
OUT_DIR = os.path.join(ROOT, "web", "research_report")   # 独立目录：勿与 web/research/（个股调研）混用

TP, SL = 0.06, 0.08                 # 首次触及法配置：+6% / -8%（与回测 DEF 档一致）
FWD = getattr(BT, "FWD", 10)        # 前向窗口 10 日
MIN_HIST = 6                        # 逐股历史胜率最少样本数，不足标注「样本不足」

ENV_ADVICE = {"强势": "开仓", "震荡": "开仓", "弱势": "谨慎", "破位": "暂停", "未知": "数据不足"}


# ------------------------------------------------------------------ 名称→代码
def _core_name(name):
    """去掉快照名称的临时修饰：XD/XR/DR 除权前缀、-U/-W/-C 未盈利/特殊投票权后缀。"""
    text = (name or "").strip()
    for pre in ("XD", "XR", "DR"):
        if text.startswith(pre) and len(text) > 3:
            text = text[len(pre):]
            break
    for suf in ("-U", "-W", "-C", "-P", "-R"):
        if text.endswith(suf):
            text = text[:-len(suf)]
            break
    return text


def resolve_codes(report_name, name_map, cache):
    """研报提及名称 → A股代码列表（精确 → 去修饰精确 → 前缀包含）。
    匹配不上返回空列表（不猜代码）。"""
    exact = [c for c, n in name_map.items() if n == report_name]
    if exact:
        return exact
    core = _core_name(report_name)
    same = [c for c, n in name_map.items() if _core_name(n) == core]
    if same:
        return same
    if len(core) >= 3:
        pref = []
        for c, n in name_map.items():
            cn = _core_name(n)
            if len(cn) >= 3 and (cn.startswith(core) or core.startswith(cn)):
                pref.append(c)
        if pref:
            return pref
    return []


# ------------------------------------------------------------------ 逐股分析
def stock_history(cache, code, bars, name):
    """该股全部已结算 as-of 日的 N字形信号 + 首次触及结果（与主池同一 eval 口径）。"""
    total = len(bars)
    sigs = []
    lo = max(getattr(NS, "MIN_BARS", 60) - 1, NS.WINDOW)
    for aidx in range(lo, total - FWD):   # 只用前向 FWD 根齐全的已结算信号（无未来函数）
        sig = NS.eval_stock_signal(code, bars, aidx, name)
        if not sig:
            continue
        ft = BT.fwd_first_touch(cache, sig, TP, SL, FWD)
        if ft:
            sig["ft"] = ft
        sigs.append(sig)
    return sigs


def hist_stats(sigs):
    fts = [s["ft"] for s in sigs if s.get("ft")]
    n = len(fts)
    if not n:
        return {"n": 0, "wr": None, "avg": None, "pr": None, "day": None}
    wins = [f for f in fts if f["win"]]
    losses = [f for f in fts if not f["win"]]
    pr = None
    if wins and losses:
        pr = (sum(f["ret"] for f in wins) / len(wins)) / abs(sum(f["ret"] for f in losses) / len(losses))
    days = [f["day"] for f in wins]
    return {"n": n, "wr": len(wins) / n,
            "avg": sum(f["ret"] for f in fts) / n, "pr": pr,
            "day": (sum(days) / len(days)) if days else None}


def _today_zt(code, bars):
    """当日是否已封涨停（_mkt_emo 唯一真端口径）。"""
    try:
        recs = list(M.scan_one(code, bars[-(NS.WINDOW + 5):]))
        return bool(recs and recs[-1].get("closed"))
    except Exception:
        return False


def stock_state(bars, code, name, w52, name2sw2, ind_map, hot_leaders):
    """当前状态（数据日收盘）：价格/均线/位置/量能 + 当日N字形信号体检。"""
    close = bars[-1].get("last")
    prev = bars[-2].get("last") if len(bars) >= 2 else None
    chg = (close / prev - 1) * 100 if (close and prev) else None
    cl20 = [b["last"] for b in bars[-20:] if b.get("last")]
    cl60 = [b["last"] for b in bars[-60:] if b.get("last")]
    ma20 = sum(cl20) / len(cl20) if len(cl20) >= 20 else None
    ma60 = sum(cl60) / len(cl60) if len(cl60) >= 60 else None
    hi60 = max((b.get("high") or 0) for b in bars[-60:]) if len(bars) >= 20 else None
    # 成交额口径与信号引擎一致：_mkt_emo.amount_of（volume×手数×收盘价，元）；
    # ⚠ K线缓存无 amount 字段，直接读 b["amount"] 会整列静默变 0（fail-unsafe），禁之。
    amt20 = sum(M.amount_of(code, b.get("last"), b.get("volume", 0))
                for b in bars[-20:]) / max(1, min(20, len(bars))) / 1e8
    h52, l52 = w52.get(code, (None, None))
    pos = None
    if close and h52 and l52 and h52 > l52:
        pos = (close - l52) / (h52 - l52) * 100
    dist_hi60 = (close / hi60 - 1) * 100 if (close and hi60) else None
    st = {"close": close, "chg": chg, "ma20": ma20, "ma60": ma60, "hi60": hi60,
          "amt20": amt20, "pos": pos, "dist_hi60": dist_hi60,
          "above_ma60": (close > ma60) if (close and ma60) else None,
          "has_signal": False, "healthy_loose": False, "healthy_strict": False,
          "hot": False, "pos_ok": False, "today_zt": False,
          "days_since_zt": None, "dist_local_peak": None}
    if not st["has_signal"]:
        st["today_zt"] = _today_zt(code, bars)
    sig = NS.eval_stock_signal(code, bars, len(bars) - 1, name)
    if sig:
        NS.attach_attr([sig], name2sw2, ind_map, hot_leaders, w52)
        st["has_signal"] = True
        st["healthy_loose"] = NS.is_healthy_pullback(sig, False)
        st["healthy_strict"] = NS.is_healthy_pullback(sig, True)
        st["hot"] = bool(sig.get("hot"))
        st["pos_ok"] = bool(sig.get("pos_ok"))
        st["days_since_zt"] = sig.get("days_since_zt")
        st["dist_local_peak"] = sig.get("dist_local_peak")
    return st


def verdict_of(st, env_label):
    """是否可建仓（观察池口径）：环境门控 + 趋势 + 位置 + 健康回撤。"""
    if env_label == "破位":
        return "禁入", "环境破位（大盘门控暂停）"
    if not st["has_signal"]:
        return "观察", "当日封涨停" if st["today_zt"] else "无当前N字形信号"
    if st["above_ma60"] is False:
        return "观察", "未站上MA60（趋势未确认）"
    if not st["pos_ok"]:
        if st["pos"] is None:
            return "观察", "52周分位数据不足"
        return "观察", "52周分位不合理（%.0f%%）" % st["pos"]
    if st["healthy_strict"]:
        return "可关注", "健康回撤∩热点∩位置合理（站上MA60）"
    if st["healthy_loose"]:
        return "可关注", "健康回撤∩热点∩位置合理"
    return "观察", "有信号但非健康回撤形态"


def trade_points(st):
    """参考买卖点（全部取自真实K线）：买点=MA20回踩；止损=-8%；目标1=+6%；目标2=60日局部高。"""
    buy = st["ma20"]
    if not buy:
        return None
    return {"buy": round(buy, 2), "stop": round(buy * (1 - SL), 2),
            "tp1": round(buy * (1 + TP), 2), "tp2": round(st["hi60"], 2) if st["hi60"] else None,
            "room": (st["hi60"] / buy - 1) * 100 if st["hi60"] else None}


def analyze_report(reg, cache, name_map, w52, name2sw2, ind_map, hot_leaders, D, env_label):
    """对一份研报做全部分析，返回结构化结果（供渲染）。"""
    rows = []
    unmatched = []
    rpt_date = reg.get("date") or D
    for sec in reg.get("sectors", []):
        sec_rows = []
        for item in sec.get("stocks", []):
            nm = item["name"]
            if item.get("market") and item["market"] != "A股":
                unmatched.append({"name": nm, "role": item.get("role", ""),
                                  "note": item.get("note", ""), "market": item.get("market")})
                continue
            codes = [c for c in resolve_codes(nm, name_map, cache) if c in cache]
            if not codes:
                unmatched.append({"name": nm, "role": item.get("role", ""),
                                  "note": item.get("note", ""), "market": "未匹配A股代码"})
                continue
            code = sorted(codes)[0]
            bars = cache[code]
            name = name_map.get(code, nm)
            sigs = stock_history(cache, code, bars, name)
            hs = hist_stats(sigs)
            st = stock_state(bars, code, name, w52, name2sw2, ind_map, hot_leaders)
            tp_pts = trade_points(st)
            # 研报发布以来涨跌（仅当研报日早于数据日时可得）
            since = None
            ridx = None
            for i, b in enumerate(bars):
                if b["date"] == rpt_date:
                    ridx = i
                    break
                if b["date"] > rpt_date:
                    break
            if ridx is not None and ridx < len(bars) - 1 and st["close"]:
                base = bars[ridx].get("last")
                if base:
                    since = (st["close"] / base - 1) * 100
            vlabel, vwhy = verdict_of(st, env_label)
            sec_rows.append({
                "name": name, "code": code, "role": item.get("role", ""), "note": item.get("note", ""),
                "st": st, "hist": hs, "tp": tp_pts, "verdict": vlabel, "why": vwhy,
                "since_report": since, "report_date": rpt_date, "amb": len(codes) > 1,
            })
        sec_rows.sort(key=lambda r: (1 if r["hist"]["n"] >= MIN_HIST else 0,
                                     r["hist"]["wr"] if r["hist"]["wr"] is not None else -1,
                                     r["hist"]["avg"] if r["hist"]["avg"] is not None else -1,
                                     r["name"]), reverse=True)
        rows.append({"sector": sec, "rows": sec_rows})
    return {"report": reg, "sectors": rows, "unmatched": unmatched}


# ------------------------------------------------------------------ 渲染
PAGE_CSS = """
.rpt-note{background:var(--accent-soft);border:1px solid #cfe0fb;border-left:4px solid var(--accent);
  border-radius:8px;padding:12px 14px;font-size:13px;color:var(--ink);margin:0 0 16px;line-height:1.75;}
.rpt-note b{color:var(--accent-ink);}
.rpt-meta{display:flex;flex-wrap:wrap;gap:8px 26px;font-size:13px;color:var(--muted);margin:0 0 14px;}
.rpt-meta b{color:var(--ink);font-weight:600;}
.rpt-box{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:14px 16px;margin:0 0 16px;}
.rpt-box h3{margin:0 0 8px;font-size:15px;color:var(--ink);}
.rpt-box p{margin:0 0 8px;font-size:13px;line-height:1.8;color:var(--ink);}
.rpt-box ul{margin:6px 0 0;padding-left:20px;font-size:13px;line-height:1.8;color:var(--ink);}
.rpt-tbl{width:100%;border-collapse:collapse;font-size:12.5px;margin:0 0 18px;}
.rpt-tbl th{background:var(--surface);color:var(--muted);font-weight:600;text-align:right;
  padding:7px 8px;border-bottom:1px solid var(--line);white-space:nowrap;}
.rpt-tbl td{padding:7px 8px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap;color:var(--ink);}
.rpt-tbl th:nth-child(-n+3),.rpt-tbl td:nth-child(-n+3){text-align:left;}
.rpt-tbl tr:hover td{background:var(--hover);}
.rpt-tbl .nm{font-weight:600;}
.rpt-tbl .code{color:var(--muted);font-size:11.5px;}
.rpt-tbl .role{color:var(--muted);font-size:11.5px;white-space:normal;min-width:120px;}
.rpt-tbl .why{color:var(--muted);font-size:11.5px;white-space:normal;min-width:110px;text-align:left;}
.v-ok{background:var(--accent-soft);color:var(--accent-ink);border-radius:5px;padding:2px 8px;font-weight:600;}
.v-mid{background:var(--surface);color:var(--muted);border:1px solid var(--line);border-radius:5px;padding:2px 8px;}
.v-no{color:var(--red);border:1px solid var(--red);border-radius:5px;padding:2px 8px;font-weight:600;}
.rpt-h2{font-size:17px;margin:22px 0 10px;color:var(--ink);border-left:4px solid var(--accent);padding-left:10px;}
.rpt-foot{font-size:12px;color:var(--muted);line-height:1.8;margin:18px 0 0;}
.muted{color:var(--muted);}
"""


def f2(v, dash="—"):
    return dash if v is None else ("%.2f" % v)


def fpc(v, signed=True, dash="—"):
    if v is None:
        return dash
    return ("%+.2f%%" % v) if signed else ("%.2f%%" % v)


def chg_span(v):
    if v is None:
        return "<span class='muted'>—</span>"
    cls = "up" if v > 0 else ("dn" if v < 0 else "muted")
    return "<span class='%s'>%s</span>" % (cls, fpc(v))


def wr_span(wr, n):
    if wr is None:
        return "<span class='muted'>样本不足</span>" if n < MIN_HIST else "<span class='muted'>—</span>"
    cls = "up" if wr >= 0.5 else ("dn" if wr < 0.4 else "muted")
    return "<span class='%s'>%.1f%%</span>" % (cls, wr * 100)


VERDICT_CLS = {"可关注": "v-ok", "观察": "v-mid", "禁入": "v-no"}


def page_head(title):
    return ("<!DOCTYPE html>\n<html lang=\"zh-CN\"><head><meta charset=\"utf-8\">\n"
            "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">\n"
            "<title>%s</title>\n<style>%s</style>\n</head>\n<body>\n<div class=\"wrap\">\n"
            % (title, PAGE_CSS))


def env_banner(env):
    label = env.get("label") or "未知"
    advice = ENV_ADVICE.get(label, "数据不足")
    score = env.get("score")
    return ("<div class='rpt-note'><b>大盘环境门控：%s%s</b>（数据基准 %s）—— %s。"
            "破位日全市场禁入；本模块所有个股判定均受此门控约束。</div>"
            % (label, ("（评分 %s）" % score) if score is not None else "",
               env.get("date") or "—", advice))


def render_report_page(res, D, env):
    reg = res["report"]
    parts = [page_head("研报分析 · %s" % reg["title"])]
    parts.append("<h1>%s</h1>" % reg["title"])
    parts.append("<div class='rpt-meta'>"
                 "<span>报告日期 <b>%s</b></span>"
                 "<span>来源 <b>%s</b></span>"
                 "<span>执笔 <b>%s</b></span>"
                 "<span>篇幅 <b>%s 页</b></span>"
                 "<span>原文 <b>%s</b></span>"
                 "<span>数据基准 <b>%s</b></span></div>"
                 % (reg.get("date", "—"), reg.get("source", "—"), reg.get("advisors", "—"),
                    reg.get("pages", "—"), os.path.basename(reg.get("file", "")), D))
    parts.append(env_banner(env))
    parts.append("<div class='rpt-box'><h3>研报市场观点（原文引用）</h3><p>%s</p></div>"
                 % reg.get("market_view", "—"))

    n_ok = n_mid = n_no = n_matched = 0
    for blk in res["sectors"]:
        sec = blk["sector"]
        rows = blk["rows"]
        n_matched += len(rows)
        parts.append("<div class='rpt-h2'>%s</div>" % sec["name"])
        parts.append("<div class='rpt-box'><h3>板块观点（原文引用）</h3><p>%s</p><ul>%s</ul></div>"
                     % (sec.get("view", "—"),
                        "".join("<li>%s</li>" % k for k in sec.get("key_data", []))))
        parts.append("<table class='rpt-tbl'><thead><tr>"
                     "<th>#</th><th>个股</th><th>研报定位</th>"
                     "<th>现价</th><th>当日%</th><th>研报以来%</th>"
                     "<th>MA20</th><th>MA60</th><th>52周分位</th><th>距60日高</th><th>20日均额(亿)</th>"
                     "<th>近一年信号</th><th>首次触及胜率</th><th>平均收益</th><th>盈亏比</th>"
                     "<th>是否可建仓</th><th>参考买点</th><th>止损</th><th>目标1</th><th>目标2</th>"
                     "</tr></thead><tbody>")
        for i, r in enumerate(rows, 1):
            st, hs, tp = r["st"], r["hist"], r["tp"]
            if r["verdict"] == "可关注":
                n_ok += 1
            elif r["verdict"] == "禁入":
                n_no += 1
            else:
                n_mid += 1
            pos_txt = ("%.0f%%" % st["pos"]) if st["pos"] is not None else "—"
            badge = "<span class='%s' title='%s'>%s</span>" % (
                VERDICT_CLS[r["verdict"]], r["why"], r["verdict"])
            amb_mark = " <span class='muted' title='快照存在多个同名代码，取排序首个'>△</span>" if r["amb"] else ""
            dist_hi = st["dist_hi60"]
            dist_cell = ("<span class='%s'>%s</span>"
                         % (("up" if dist_hi > -5 else "dn"), fpc(dist_hi))) if dist_hi is not None else "—"
            cells = [
                str(i),
                "<span class='nm'>%s</span>%s<br><span class='code'>%s</span>" % (r["name"], amb_mark, r["code"]),
                "<span class='role'>%s</span>" % (r["role"] or "—"),
                f2(st["close"]),
                chg_span(st["chg"]),
                chg_span(r["since_report"]),
                f2(st["ma20"]), f2(st["ma60"]),
                pos_txt,
                dist_cell,
                f2(st["amt20"]),
                str(hs["n"]),
                wr_span(hs["wr"], hs["n"]),
                chg_span(hs["avg"] * 100) if hs["avg"] is not None else "—",
                f2(hs["pr"]),
                badge,
                f2(tp["buy"]) if tp else "—",
                f2(tp["stop"]) if tp else "—",
                f2(tp["tp1"]) if tp else "—",
                f2(tp["tp2"]) if tp else "—",
            ]
            parts.append("<tr>" + "".join("<td>%s</td>" % c for c in cells) + "</tr>")
        parts.append("</tbody></table>")
        parts.append("<div class='rpt-foot'>买卖点口径：参考买点=回踩MA20；止损=买点-8%%；"
                     "目标1=买点+6%%；目标2=60日局部高点（全部取自真实K线，非投资建议）。"
                     "首次触及胜率口径：近一年该股N字形信号入场后先触+6%%还是先触-8%%"
                     "（与N字形回测DEF档一致），样本&lt;%d只标注样本不足。</div>" % MIN_HIST)

    if res["unmatched"]:
        items = []
        for u in res["unmatched"]:
            tag = u.get("market") or "未匹配A股代码"
            items.append("<li><b>%s</b>（%s）——%s%s</li>" % (
                u["name"], tag, u.get("role", ""),
                ("；" + u["note"]) if u.get("note") else ""))
        parts.append("<div class='rpt-box'><h3>未纳入逐股分析的提及标的（%d）</h3><ul>%s</ul>"
                     "<p class='muted'>原因：非A股上市或本地行情快照未匹配到代码——按「宁可不选」铁律不猜代码、不出数。</p></div>"
                     % (len(res["unmatched"]), "".join(items)))

    parts.append("<div class='rpt-note'><b>汇总</b>：提及标的 %d 个，A股匹配 %d 只（可关注 %d / 观察 %d / 禁入 %d），"
                 "未匹配 %d 个。全模块为<b>观察池·非出票</b>：以上为数据研判，不构成投资建议；"
                 "逐股统计随数据日推进每日重算。</div>"
                 % (n_matched + len(res["unmatched"]), n_matched, n_ok, n_mid, n_no, len(res["unmatched"])))
    parts.append("<div class='rpt-foot'>免责声明：本页为研报信息的结构化整理与本地数据交叉验证，"
                 "研报观点版权归原发布方所有；所涉个股仅作研究记录。股市有风险，投资需谨慎。</div>")
    parts.append("</div></body></html>")
    return "".join(parts)


def render_index_page(reports, D, env):
    parts = [page_head("研报分析")]
    parts.append("<h1>研报分析</h1>")
    parts.append("<div class='rpt-note'><b>模块口径</b>：上传研报（PDF）经人工校读入库，"
                 "记录报告时间与原文观点；逐股分析全部使用本地真实行情数据现算"
                 "（全市场日K缓存、52周区间自算、N字形信号史首次触及胜率、大盘环境门控），"
                 "数字不写死、不编造，样本不足如实标注。<b>观察池·非出票</b>，不构成投资建议。</div>")
    parts.append(env_banner(env))
    if not reports:
        parts.append("<div class='rpt-box'><p>暂无研报记录。</p></div>")
    else:
        parts.append("<table class='rpt-tbl'><thead><tr>"
                     "<th>报告日期</th><th>研报标题</th><th>来源</th><th>覆盖板块</th>"
                     "<th>提及标的</th><th>核心结论（原文摘要）</th><th>分析</th>"
                     "</tr></thead><tbody>")
        for reg in sorted(reports, key=lambda r: r.get("date", ""), reverse=True):
            n_stocks = sum(len(s.get("stocks", [])) for s in reg.get("sectors", []))
            secs = "、".join(s["name"] for s in reg.get("sectors", []))
            view = reg.get("market_view", "")
            brief = view[:110] + ("……" if len(view) > 110 else "")
            parts.append("<tr><td><b>%s</b></td><td class='nm'>%s</td><td>%s</td><td>%s</td>"
                         "<td>%d 个</td><td class='role'>%s</td>"
                         "<td><a href='report_%s.html'>逐股分析 →</a></td></tr>"
                         % (reg.get("date", "—"), reg.get("title", "—"), reg.get("source", "—"),
                            secs, n_stocks, brief, reg.get("id", "")))
        parts.append("</tbody></table>")
    parts.append("<div class='rpt-foot'>入库方式：研报 PDF 上传后人工校读，将报告日期/来源/观点/"
                 "提及标的登记至 quant/research/reports.json（原文留存 quant/research/）；"
                 "逐股胜率与买卖点由 build_research.py 每日用本地行情数据重算。"
                 "股市有风险，投资需谨慎。</div>")
    parts.append("</div></body></html>")
    return "".join(parts)


# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("date", nargs="?", default=None)
    ap.add_argument("--date", dest="date_flag", default=None)
    args = ap.parse_args()
    latest = NS.latest_date()
    D = args.date_flag or args.date or (latest if latest else None)
    if not D:
        print("无法确定数据日")
        return
    print("=== 研报分析 · 数据日 %s ===" % D)

    if not os.path.exists(REG_PATH):
        print("注册表不存在：%s" % REG_PATH)
        return
    registry = json.load(open(REG_PATH, encoding="utf-8"))
    reports = registry.get("reports", [])

    _txk.set_asof(D)
    cache = _txk.load()
    name_map = NS.load_name_map(D)
    name2sw2 = NS.load_name2sw2()
    ind_map, hot_leaders = NS.load_hot_maps()
    w52 = NS.load_52w_cache(cache)     # 52周区间自 K 线缓存自算（quotes 快照字段已证伪）
    env = NS.load_market_heat(D)
    print("环境门控：%s（评分 %s）｜缓存 %d 只｜名称映射 %d 条"
          % (env.get("label"), env.get("score"), len(cache), len(name_map)))

    os.makedirs(OUT_DIR, exist_ok=True)
    index_html = render_index_page(reports, D, env)
    with open(os.path.join(OUT_DIR, "index.html"), "w", encoding="utf-8") as fh:
        fh.write(index_html)

    total_matched = total_unmatched = 0
    for reg in reports:
        res = analyze_report(reg, cache, name_map, w52, name2sw2, ind_map, hot_leaders, D,
                             env.get("label") or "未知")
        html = render_report_page(res, D, env)
        out = os.path.join(OUT_DIR, "report_%s.html" % reg.get("id", "unknown"))
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(html)
        n_match = sum(len(b["rows"]) for b in res["sectors"])
        total_matched += n_match
        total_unmatched += len(res["unmatched"])
        print("研报《%s》：匹配 %d 只 / 未匹配 %d -> %s"
              % (reg.get("title", "?"), n_match, len(res["unmatched"]), os.path.basename(out)))
    print("完成：索引页 + %d 份研报分析页（合计匹配 %d 只、未匹配 %d 个）"
          % (len(reports), total_matched, total_unmatched))


if __name__ == "__main__":
    main()
