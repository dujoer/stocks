# -*- coding: utf-8 -*-
"""N字形战法筛选板（观察池 · 非出票）。

筛选条件（用户给定示例）：
  1) 近 20 个交易日（含当日）内，至少 1 根日K 收盘封涨停（统一口径 _mkt_emo.is_limit_up）。
  2) 最新收盘价 > 5 日均线（MA5）。
「可建仓」附加：剔除当日已封涨停（一字/封死涨停盘中买不进）的标的。

N字形形态语义：涨停启动（强势信号）→ 回调 → 再上穿均线（动量延续），属短线动量延续观察池。
本板仅按机械条件筛选，未过任何样本外稳健性检验，不构成买卖建议。

数据：_txk_cache.json（全市场日K）+ quotes/{D}.json（名称/现价/涨跌幅）。
输出：web/n_shape/n_shape_{DS}.html（每日归档）+ web/n_shape/index.html（滚动视图）。
"""
from __future__ import annotations
import os, sys, json, datetime, argparse

QUANT = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(QUANT)
WEB = os.path.join(ROOT, "web")
sys.path.insert(0, QUANT)

import _txk
import _mkt_emo as M

OUTDIR = os.path.join(WEB, "n_shape")
os.makedirs(OUTDIR, exist_ok=True)

WINDOW = 20            # 近 N 个交易日查涨停
MIN_BARS = 30          # 最少历史根数
AMT_MIN = 30_000_000   # 20 日均成交额下限（元），剔除流动性差的
EXCLUDE_BJ = True      # 剔除北交所（30cm，口径不同）


def latest_date():
    try:
        return _txk.last_date(_txk.load())
    except Exception:
        return None


def excluded_name(name):
    if not name:
        return True
    for k in ("ST", "*ST", "退", "ETF", "基金", "债", "B股"):
        if k in name:
            return True
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("date", nargs="?", default=None)
    ap.add_argument("--date", dest="date", default=None)
    a = ap.parse_args()
    _d = latest_date()
    D = a.date or (_d if _d else None)
    if not D:
        print("无法确定数据日"); return
    DS = D.replace("-", "")
    print("=== N字形筛选 · 数据日 %s ===" % D)

    try:
        _txk.set_asof(D)
    except Exception:
        pass
    cache = _txk.load()

    # 名称 / 现价 / 涨跌幅
    qname = {}
    qpath = os.path.join(QUANT, "quotes", "%s.json" % D)
    try:
        qj = json.load(open(qpath, encoding="utf-8")).get("data", {})
        for code, v in qj.items():
            if isinstance(v, dict):
                qname[code] = (v.get("name"), v.get("last"), v.get("change_percent"))
    except Exception as e:
        print("  [warn] quotes 读取失败：%s" % e)

    rows = []
    excluded_today_zt = 0
    for code, bars in cache.items():
        if not isinstance(bars, list) or len(bars) < MIN_BARS:
            continue
        if EXCLUDE_BJ and str(code).startswith("bj"):
            continue
        name = (qname.get(code) or (None,))[0]
        if excluded_name(name):
            continue

        # 末 26 根（多留 6 根给 scan_one 算 prev）
        win = bars[-(WINDOW + 6):]
        recs = list(M.scan_one(code, win))
        if len(recs) < WINDOW:
            continue
        last20 = recs[-WINDOW:]

        today_zt = bool(last20[-1].get("closed"))
        has_zt = any(r.get("closed") for r in last20)
        if not has_zt:
            continue

        closes5 = [r["close"] for r in recs[-5:]]
        if not closes5 or any(c is None for c in closes5):
            continue
        ma5 = sum(closes5) / len(closes5)
        cur = last20[-1]["close"]
        if cur is None or ma5 is None:
            continue
        if not (cur > ma5):
            continue

        amts = [r.get("amount") or 0 for r in last20]
        avg_amt = sum(amts) / len(amts) if amts else 0
        if avg_amt < AMT_MIN:
            continue

        # 可建仓：剔除当日已封涨停（买不进）
        if today_zt:
            excluded_today_zt += 1
            continue

        last_zt_idx = None
        for i in range(len(last20) - 1, -1, -1):
            if last20[i].get("closed"):
                last_zt_idx = i
                break
        last_zt_date = last20[last_zt_idx]["date"] if last_zt_idx is not None else None
        days_since = (len(last20) - 1 - last_zt_idx) if last_zt_idx is not None else None

        nm = qname.get(code) or (None, None, None)
        rows.append({
            "code": code,
            "name": nm[0],
            "close": cur,
            "ma5": round(ma5, 2),
            "dist_ma5": round((cur / ma5 - 1) * 100, 2),
            "chg_pct": nm[2],
            "last_zt_date": last_zt_date,
            "days_since_zt": days_since,
            "avg_amt_yi": round(avg_amt / 1e8, 2),
        })

    # 排序：距上次涨停天数升序（越近越强）→ 20日均额降序
    rows.sort(key=lambda r: (r["days_since_zt"] if r["days_since_zt"] is not None else 999,
                             -(r["avg_amt_yi"] or 0)))

    print("  命中 %d 只（剔除当日涨停 %d 只）" % (len(rows), excluded_today_zt))

    jout = {"date": D, "count": len(rows), "excluded_today_zt": excluded_today_zt,
            "window": WINDOW, "rows": rows}
    jdir = os.path.join(QUANT, "n_shape")
    os.makedirs(jdir, exist_ok=True)
    json.dump(jout, open(os.path.join(jdir, "n_shape_%s.json" % DS), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    html = render_html(D, rows, excluded_today_zt, "n_shape_%s.html" % DS)
    open(os.path.join(OUTDIR, "n_shape_%s.html" % DS), "w", encoding="utf-8").write(html)
    open(os.path.join(OUTDIR, "index.html"), "w", encoding="utf-8").write(html)
    print("  写出 n_shape_%s.html 与 index.html，共 %d 只" % (DS, len(rows)))


def render_html(D, rows, excluded, archive_href):
    head = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>N字形战法筛选 · 近20日涨停+站上5日线</title>
</head><body>
<div class="wrap">
<h1>N字形战法筛选 · 可建仓观察池</h1>
<div class="sub">数据基准 %s · 条件：近20交易日有收盘涨停 且 收盘价&gt;MA5（已剔除当日封涨停）</div>
<div class="box">本页为<b>观察池·非出票</b>：仅按机械条件筛选，未过样本外稳健性检验，不构成买卖建议。
N字形=涨停启动 → 回调 → 再上穿均线，属短线动量延续形态。距上次涨停天数越短，动能延续概率越高。</div>
""" % D
    if archive_href:
        head += "<div class='sub'><a href='%s'>📅 历史归档页（%s）</a></div>\n" % (archive_href, D)
    th = ("<table><thead><tr>"
          "<th>#</th><th>代码</th><th>名称</th><th>现价</th><th>MA5</th>"
          "<th>距MA5</th><th>当日%</th><th>最近涨停</th><th>距涨停</th><th>20日均额(亿)</th>"
          "</tr></thead><tbody>")
    trs = []
    for i, r in enumerate(rows, 1):
        chg = r["chg_pct"] or 0
        cls = "up" if chg >= 0 else "dn"
        sign = "+" if chg >= 0 else ""
        d_zt = r["days_since_zt"]
        d_zt_s = ("%d日" % d_zt) if d_zt is not None else "—"
        trs.append(
            "<tr><td>%d</td><td>%s</td><td>%s</td><td>%.2f</td><td>%.2f</td>"
            "<td class='%s'>%+.2f%%</td><td class='%s'>%s%.2f%%</td>"
            "<td>%s</td><td>%s</td><td>%.2f</td></tr>" % (
                i, r["code"], r["name"] or "—", r["close"], r["ma5"],
                "up" if r["dist_ma5"] >= 0 else "dn", r["dist_ma5"],
                cls, sign, chg,
                r["last_zt_date"] or "—", d_zt_s, r["avg_amt_yi"] or 0))
    tail = ("</tbody></table>"
            "<div class='sub'>共 %d 只命中 · 已剔除当日封涨停 %d 只 · 数据基准 %s</div>"
            "</div></body></html>" % (len(rows), excluded, D))
    return head + th + "".join(trs) + tail


if __name__ == "__main__":
    main()
