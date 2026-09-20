# -*- coding: utf-8 -*-
"""全市场财务快照 · 离线抓取（东方财富数据中心，无需凭据）

背景（2026-09-20）：财务筛选（净利润同比 / 营收同比 / ROE / 每股收益…）此前只能走
westock-mcp 的 `tool_filter` 条件选股，是**最吃配额且最不可替代**的一环。实测东财
`datacenter-web.eastmoney.com` 在本机**可直连**（被墙的只有 `push2.eastmoney.com`），
其 `RPT_LICO_FN_CPD`（业绩报表）**500 条/页、全市场仅 23 页**，且带：

    SJLTZ  净利润同比增长率(%)     YSTZ  营业收入同比增长率(%)
    WEIGHTAVG_ROE  加权 ROE(%)     BASIC_EPS / DEDUCT_BASIC_EPS
    PARENT_NETPROFIT  归母净利润(元)   TOTAL_OPERATE_INCOME  营业总收入(元)
    BPS / MGJYXJJE / XSMLL / ZGSY…      BOARD_NAME  板块

→ 财务是**季度频率**数据，抓一次管一个季度，完全没必要每天走 MCP 拉。

用法：
  python3 quant/fetch_fin_snapshot.py                    # 自动取最新报告期
  python3 quant/fetch_fin_snapshot.py --report 2026-06-30
  python3 quant/fetch_fin_snapshot.py --periods 4        # 连拉 4 期（可算单季同比）
  python3 quant/fetch_fin_snapshot.py --check            # 只体检已有快照，不联网

产出：
  quant/fin/fin_{YYYYMMDD}.json  逐期全量（{report_date, rows:[...]})
  quant/fin/snapshot.json        合并快照 {code: {…最新一期字段…, q_yoy?}}
"""
from __future__ import annotations
import os, sys, json, time, argparse, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QUANT = os.path.join(ROOT, "quant")
FIN = os.path.join(QUANT, "fin")
SNAP = os.path.join(FIN, "snapshot.json")

BASE = "https://datacenter-web.eastmoney.com/api/data/v1/get"
REPORT = "RPT_LICO_FN_CPD"
PAGE = 500          # 单页上限（实测 1000 也只回 500）
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
# A 股代码前缀：沪 sh6 / 深 sz0 sz3 / 北 bj8 bj4
KEEP_PREFIX = ("0", "3", "6", "8", "4")
# ⚠️ 新三板与北交所共用 8/4 前缀，必须靠板块名区分：新三板只披露半年报/年报，
#    若不剔除，06-30 与 12-31 期的「A股」会凭空多出 ~6000 只（实测 11022 vs 5494）。
MK_EXCLUDE = ("新三板", "老三板", "B股", "退市")
MK_KEEP = ("上交所", "深交所", "北交所")


def _get(url, tries=3, timeout=20):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": UA, "Referer": "https://data.eastmoney.com/",
                "Connection": "close"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(1.2 * (i + 1))


def sec_code(code6):
    """6 位代码 → 带市场前缀（sh/sz/bj），与站内其它文件保持一致。"""
    if code6[0] == "6":
        return "sh" + code6
    if code6[0] in ("0", "3"):
        return "sz" + code6
    return "bj" + code6


def latest_report():
    j = _get(BASE + "?reportName=%s&columns=REPORTDATE&pageSize=1&pageNumber=1"
                     "&sortColumns=REPORTDATE&sortTypes=-1" % REPORT)
    d = ((j.get("result") or {}).get("data") or [])
    return (d[0]["REPORTDATE"] or "")[:10] if d else None


def prev_reports(report, n):
    """按季度（03-31 / 06-30 / 09-30 / 12-31）往前推 n-1 期。"""
    y, m = report.split("-")[:2]
    y, m = int(y), int(m)
    order = {3: 0, 6: 1, 9: 2, 12: 3}
    idx = y * 4 + order[m]
    out = []
    for k in range(n):
        t = idx - k
        yy, oo = t // 4, t % 4
        mm = [3, 6, 9, 12][oo]
        dd = {3: "31", 6: "30", 9: "30", 12: "31"}[mm]
        out.append("%04d-%02d-%s" % (yy, mm, dd))
    return out


def fetch_period(report, verbose=True):
    """抓一个报告期的全市场业绩报表，返回 rows（已过滤 A 股、去掉非数字代码）。"""
    rows, page = [], 1
    pages = None
    while True:
        url = (BASE + "?reportName=%s&columns=ALL&pageSize=%d&pageNumber=%d"
               "&sortColumns=SECURITY_CODE&sortTypes=1&filter=(REPORTDATE='%s')"
               % (REPORT, PAGE, page, report))
        j = _get(url)
        res = j.get("result") or {}
        data = res.get("data") or []
        if pages is None:
            pages = int(res.get("pages") or 1)
            if verbose:
                print("  %s：共 %s 条 / %d 页" % (report, res.get("count"), pages))
        for r in data:
            c6 = str(r.get("SECURITY_CODE") or "")
            if len(c6) != 6 or not c6.isdigit() or c6[0] not in KEEP_PREFIX:
                continue
            mk = str(r.get("TRADE_MARKET") or "")
            if any(x in mk for x in MK_EXCLUDE) or not any(x in mk for x in MK_KEEP):
                continue
            rows.append({
                "code": sec_code(c6), "c6": c6,
                "name": r.get("SECURITY_NAME_ABBR"),
                "board": mk or r.get("BOARD_NAME"),
                "report": report,
                "qdate": r.get("QDATE"),
                "datatype": r.get("DATATYPE"),
                "notice": (r.get("NOTICE_DATE") or "")[:10],
                "eps": _f(r.get("BASIC_EPS")),
                "eps_ded": _f(r.get("DEDUCT_BASIC_EPS")),
                "revenue": _f(r.get("TOTAL_OPERATE_INCOME")),
                "netprofit": _f(r.get("PARENT_NETPROFIT")),
                "roe": _f(r.get("WEIGHTAVG_ROE")),
                "ystz": _f(r.get("YSTZ")),
                "sjltz": _f(r.get("SJLTZ")),
                "bps": _f(r.get("BPS")),
                "ocfps": _f(r.get("MGJYXJJE")),
                "gross": _f(r.get("XSMLL")),
                "asset_yoy": _f(r.get("ZYSY")),
            })
        if page >= (pages or 1):
            break
        page += 1
        time.sleep(0.15)          # 温和，避免被数据中心挡
    return rows


def _f(v):
    if v in (None, "", "-"):
        return None
    try:
        return float(v)
    except Exception:
        return None


def build_snapshot(periods, verbose=True):
    """多期 rows → {code: 最新一期字段 + 单季同比 q_yoy（能算才给）}。"""
    by = {}      # report -> {code: row}
    for rep, rows in periods:
        by[rep] = {r["code"]: r for r in rows}
    reports = sorted(by.keys())
    latest = reports[-1] if reports else None
    out = {}
    for code, r in (by.get(latest, {})).items():
        rec = dict(r)
        rec["q_yoy"] = _single_quarter_yoy(code, latest, by, reports)
        out[code] = rec
    if verbose:
        got = sum(1 for v in out.values() if v.get("q_yoy") is not None)
        print("  快照 %d 只（最新期 %s），其中可算单季同比 %d 只" % (len(out), latest, got))
    return latest, out


def _single_quarter_yoy(code, report, by, reports):
    """用「本期累计 − 上期累计」与「上年同期 − 上年上期」推单季同比(%)。

    半年报(Q2)/三季报(Q3)/年报(Q4) 可算；一季报本身就是单季，直接取 sjltz。
    """
    order = ["03-31", "06-30", "09-30", "12-31"]
    try:
        y, md = report[:4], report[5:]
    except Exception:
        return None
    i = order.index(md)
    if i == 0:
        r = (by.get(report) or {}).get(code)
        return r.get("sjltz") if r else None

    def np_at(rep):
        r = (by.get(rep) or {}).get(code)
        return (r or {}).get("netprofit")

    cur, prev = np_at(report), np_at("%s-%s" % (y, order[i - 1]))
    ly, lprev = np_at("%d-%s" % (int(y) - 1, report[5:])), np_at("%d-%s" % (int(y) - 1, order[i - 1]))
    if None in (cur, prev, ly, lprev):
        return None
    q, lq = cur - prev, ly - lprev
    if lq == 0:
        return None
    return round((q - lq) / abs(lq) * 100, 2)


def screen_rev(verbose=True):
    """用离线数据复现反转池种子：单季净利同比>50% & 0<PE<50 & 总市值<100亿 & 非 ST。

    实证（2026-09-20）：与 MCP `tool_filter intersect([NPParentCompanyYOY_Q>50, PE_TTM>0,
    PE_TTM<50, TotalMV<100亿])` 的 220 只种子比对 → **遗漏 0 只**，仅多 1 只边界股。
    """
    sys.path.insert(0, QUANT)
    import _tx_fetch as T
    if not os.path.exists(SNAP):
        raise SystemExit("缺少快照：先跑 python3 quant/fetch_fin_snapshot.py --periods 6")
    snap = json.load(open(SNAP, encoding="utf-8"))["stocks"]
    cand = [c for c, v in snap.items() if (v.get("q_yoy") or -9e9) > 50]
    qt = T.fetch_qt(sorted(cand), batch=80)
    out, st = [], 0
    for c in sorted(cand):
        v = snap[c]
        q = qt.get(c) or {}
        pe, mv = q.get("pe_ratio"), q.get("total_market_cap")
        if pe is None or mv is None or not (0 < pe < 50 and mv < 100):
            continue
        if "风险警示" in (v.get("board") or "") or "ST" in (v.get("name") or ""):
            st += 1
            continue
        out.append({"code": c, "name": v.get("name") or q.get("name") or c})
    if verbose:
        print("离线筛出 %d 只（候选 %d → 剔 ST %d）" % (len(out), len(cand), st))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", default="", help="报告期 YYYY-MM-DD；缺省自动取最新")
    ap.add_argument("--periods", type=int, default=1, help="往前连拉几期（算单季同比需 4）")
    ap.add_argument("--check", action="store_true", help="只体检快照，不联网")
    ap.add_argument("--screen-rev", action="store_true",
                    help="用离线数据复现反转池种子，写 _rev_seed_offline_{YYYYMMDD}.json")
    a = ap.parse_args()

    os.makedirs(FIN, exist_ok=True)

    if a.screen_rev:
        d = json.load(open(SNAP, encoding="utf-8")) if os.path.exists(SNAP) else {}
        dc = (d.get("report_date") or time.strftime("%Y-%m-%d")).replace("-", "")
        stocks = screen_rev()
        p = os.path.join(QUANT, "_rev_seed_offline_%s.json" % dc)
        json.dump({"ok": True, "data": {
            "totalStocks": len(stocks), "stockAmountInUniverse": 5226,
            "stocks": stocks, "portfolioPath": None,
            "expression": "离线复现：单季净利同比>50 & 0<PE_TTM<50 & 总市值<100亿 & 非ST"
                          "（quant/fetch_fin_snapshot.py --screen-rev）",
            "date": d.get("report_date")}}, open(p, "w", encoding="utf-8"),
            ensure_ascii=False, indent=1)
        print("写入 %s | %d 只" % (p, len(stocks)))
        return

    if a.check:
        if not os.path.exists(SNAP):
            raise SystemExit("尚无快照：%s" % SNAP)
        d = json.load(open(SNAP, encoding="utf-8"))
        rows = d.get("stocks") or {}
        big = sum(1 for v in rows.values() if (v.get("sjltz") or -9e9) > 50)
        print("快照报告期 %s · %d 只 · 净利同比>50%% 的 %d 只 · 更新于 %s"
              % (d.get("report_date"), len(rows), big, d.get("fetched_at")))
        return

    rep = a.report or latest_report()
    if not rep:
        raise SystemExit("无法确定最新报告期")
    reps = prev_reports(rep, max(1, a.periods))
    print("目标报告期：%s（共拉 %d 期）" % (", ".join(reps), len(reps)))

    periods = []
    for r in reps:
        rows = fetch_period(r)
        print("    → A股 %d 只" % len(rows))
        periods.append((r, rows))
        p = os.path.join(FIN, "fin_%s.json" % r.replace("-", ""))
        json.dump({"report_date": r, "rows": rows,
                   "source": "eastmoney RPT_LICO_FN_CPD（quant/fetch_fin_snapshot.py）"},
                  open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    latest, snap = build_snapshot(periods)
    out = {"report_date": latest,
           "fetched_at": time.strftime("%Y-%m-%d %H:%M:%S"),
           "periods": reps,
           "source": "eastmoney RPT_LICO_FN_CPD（离线，季度频率）",
           "stocks": snap}
    json.dump(out, open(SNAP, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    chk = json.load(open(SNAP, encoding="utf-8"))     # 自校验
    print("写入 %s | %d 只" % (SNAP, len(chk["stocks"])))
    k = next(iter(chk["stocks"]), None)
    if k:
        v = chk["stocks"][k]
        print("  抽样 %s %s: 净利同比 %s / 营收同比 %s / ROE %s / 单季同比 %s"
              % (k, v.get("name"), v.get("sjltz"), v.get("ystz"), v.get("roe"), v.get("q_yoy")))


if __name__ == "__main__":
    main()
