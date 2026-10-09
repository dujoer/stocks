#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
板块强度 · 换源补期（东财口径）—— 仅用于 westock 快照不可回溯的历史缺口。

背景（必须读懂再跑）:
  westock data_sector 只返回「最新快照」，date 参数被忽略 → 漏跑一天即永久断档。
  2026-09-01 就是这个缺口。
  本脚本用东财板块历史（日K成交额 + 资金流主力净流入）倒推当天板块强度，**仅作换源补期**。

★ 口径差异（红线，必须在页面明标，不得掩盖）:
  westock : 强度 = (主力净流入 − 散户净流入) / 成交额 × 100
  东财     : 强度 =  主力净流入           / 成交额 × 100     ← 本脚本产出的就是这一口径
  两者不是同一指标，**不可直接与其余期比较**；主力流入/流出拆项、领涨股 东财此接口不提供，
  如实留「—」，绝不编造。

用法:
  python quant/_fetch_sector_em.py --date 2026-09-01
  python quant/_fetch_sector_em.py --date 2026-09-01 --rebuild-boards   # 强制重拉板块清单
"""
from __future__ import annotations
import os, sys, json, time, socket, subprocess, argparse, urllib.request, urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = os.path.dirname(os.path.abspath(__file__))
DAILY_DIR = os.path.join(ROOT, "sector_daily")
TREND_PATH = os.path.join(ROOT, "sector_trend.json")
BOARDS_CACHE = os.path.join(ROOT, "_em_boards_cache.json")

H_CLIST = "80.push2.eastmoney.com"
H_HIS = "80.push2his.eastmoney.com"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
# 本机 DNS 对 *.push2*.eastmoney.com 解析不稳 → 用公网 DNS 解析后按 IP 池轮询
_FALLBACK_IP = {
    H_CLIST: ["61.129.129.196", "117.184.33.102", "101.226.30.206"],
    H_HIS:   ["103.220.167.80", "14.103.188.89", "101.226.30.221"],
}
_IP_POOL: dict[str, list[str]] = {}


def _dig(name) -> list[str]:
    try:
        out = subprocess.run(["dig", "+short", "@8.8.8.8", name],
                             capture_output=True, text=True, timeout=15).stdout
    except Exception:
        return []
    return [l.strip() for l in out.splitlines() if l.strip() and l.strip()[0].isdigit()]


def patch_dns():
    """把两个东财域名的解析固定到可用的公网 IP 上（本机解析不到）。"""
    real = socket.getaddrinfo
    for h in (H_CLIST, H_HIS):
        ips = _dig(h) or _FALLBACK_IP[h]
        _IP_POOL[h] = ips or _FALLBACK_IP[h]
    _c = {h: 0 for h in _IP_POOL}

    def _pick(h):
        pool = _IP_POOL[h]
        ip = pool[_c[h] % len(pool)]
        _c[h] += 1
        return ip

    def ga(host, port, family=0, type=0, proto=0, flags=0):
        if host in _IP_POOL:
            return real(_pick(host), port, family, type, proto, flags)
        return real(host, port, family, type, proto, flags)
    socket.getaddrinfo = ga
    print("[dns] " + " | ".join("%s -> %s" % (h, ",".join(v)) for h, v in _IP_POOL.items()))


def get_json(url, host, retries=5):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA, "Referer": "https://quote.eastmoney.com/",
        "Host": host, "Accept": "*/*"})
    last = None
    for i in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=25) as r:
                return json.loads(r.read().decode("utf-8", "replace"))
        except Exception as e:
            last = e
            time.sleep(0.6 + 0.5 * i)
    return None


# ── ① 板块清单 ──────────────────────────────────────────────────────────
def list_boards(t, force=False):
    key = "t%d" % t
    if not force and os.path.exists(BOARDS_CACHE):
        try:
            c = json.load(open(BOARDS_CACHE, encoding="utf-8"))
            if c.get("_ver") == 2 and c.get(key):
                print("[boards] %s 用缓存 %d 个" % (key, len(c[key])))
                return [(x[0], x[1]) for x in c[key]]
        except Exception:
            pass
    out, pn = [], 1
    while pn <= 12:
        u = ("https://%s/api/qt/clist/get?pn=%d&pz=100&po=1&np=1&fltt=2&invt=2&fid=f3"
             "&fs=%s&fields=f12,f14" % (H_CLIST, pn, urllib.parse.quote("m:90+t:%d" % t)))
        d = get_json(u, H_CLIST)
        if not d:
            break
        diff = (d.get("data") or {}).get("diff") or []
        if isinstance(diff, dict):
            diff = list(diff.values())
        for x in diff:
            if x.get("f12") and x.get("f14"):
                out.append((x["f12"], x["f14"]))
        if len(diff) < 100:
            break
        pn += 1
        time.sleep(0.25)
    print("[boards] %s 拉到 %d 个" % (key, len(out)))
    return out


def load_boards(force=False):
    ind = list_boards(2, force)
    con = list_boards(3, force)
    if not force:
        try:
            c = json.load(open(BOARDS_CACHE, encoding="utf-8"))
            c.setdefault("t2", [[a, b] for a, b in ind])
            c.setdefault("t3", [[a, b] for a, b in con])
            c["_ver"] = 2
            json.dump(c, open(BOARDS_CACHE, "w", encoding="utf-8"), ensure_ascii=False)
        except Exception:
            pass
    return ind, con


# ── ② 单板块：成交额 + 主力净流入 ────────────────────────────────────────
def board_day(code, date):
    beg = date.replace("-", "")
    u1 = ("https://%s/api/qt/stock/kline/get?secid=90.%s&klt=101&fqt=1&beg=%s&end=%s"
          "&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"
          % (H_HIS, code, beg, beg))
    d1 = get_json(u1, H_HIS, retries=4)
    amt = pct = None
    if d1 and d1.get("data"):
        for k in d1["data"].get("klines") or []:
            p = k.split(",")
            if p[0] == date and len(p) > 8:
                amt = float(p[6]); pct = float(p[8])
                break
    u2 = ("https://%s/api/qt/stock/fflow/daykline/get?secid=90.%s&lmt=0&klt=101"
          "&fields1=f1,f2,f3,f7&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65"
          % (H_HIS, code))
    d2 = get_json(u2, H_HIS, retries=4)
    main = None
    if d2 and d2.get("data"):
        for k in d2["data"].get("klines") or []:
            p = k.split(",")
            if p[0] == date and len(p) > 1:
                main = float(p[1])
                break
    return amt, pct, main


def behavior_of(s):
    if s >= 3:
        return "抢筹"
    if s >= 1:
        return "建仓"
    if s >= -1:
        return "洗盘"
    return "出货"


def _yi(v, plus=True):
    y = v / 1e8
    return (("+" if (plus and y > 0) else "") + format(y, ".2f"))


# ── ③ 主流程 ────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True, help="补期交易日 YYYY-MM-DD（仅用于东财历史回溯）")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--rebuild-boards", action="store_true")
    ap.add_argument("--boards-only", action="store_true")
    a = ap.parse_args()
    date = a.date
    patch_dns()
    ind, con = load_boards(a.rebuild_boards)
    if a.boards_only:
        print("[ok] 板块清单：行业 %d / 概念 %d" % (len(ind), len(con)))
        return

    tasks = [(c, n, "行业") for c, n in ind] + [(c, n, "概念") for c, n in con]
    print("[fetch] %d 个板块，回溯 %s" % (len(tasks), date))
    raw: dict[str, tuple] = {}
    t0 = time.time()

    def work(it):
        code, name, kind = it
        r = board_day(code, date)
        time.sleep(0.12)
        return it, r

    done = 0
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        futs = {ex.submit(work, it): it for it in tasks}
        for fu in as_completed(futs):
            it, r = fu.result()
            raw[it[0]] = (it[0], it[1], it[2], r[0], r[1], r[2])
            done += 1
            if done % 100 == 0:
                el = time.time() - t0
                print("  %d/%d  %.0fs  (%.1f 个/分)" % (done, len(tasks), el, done / el * 60 if el else 0))

    # 组装记录
    recs, miss = [], 0
    for code, name, kind, amt, pct, main in raw.values():
        if amt in (None, 0) or main is None:
            miss += 1
            continue
        s = main / amt * 100
        recs.append({
            "name": name, "kind": kind,
            "pctText": ("+" if pct > 0 else "") + format(pct, ".2f") + "%",
            "pctVal": round(pct, 2),
            "totalText": _yi(amt), "totalVal": amt,
            # 东财此接口不给「主力流入 / 散户净流入」拆项 —— 如实留「—」，不编造
            "mainText": "—", "mainVal": None,
            "retailText": "—", "retailVal": None,
            "darkText": _yi(main), "darkVal": main, "darkUp": main >= 0,
            "strengthText": format(s, ".2f"), "strengthVal": round(s, 2),
            "behavior": behavior_of(s),
            "behaviorRank": {"抢筹": 4, "建仓": 3, "洗盘": 2, "出货": 1}[behavior_of(s)],
            "leader": "—",
            "src": "eastmoney",
        })
    if not recs:
        raise SystemExit("[fail] 未取到任何板块数据，不写产物（fail-safe）")
    recs.sort(key=lambda r: r["strengthVal"], reverse=True)

    n = len(recs)
    tot_dark = sum(r["darkVal"] for r in recs)
    tot_turn = sum(r["totalVal"] for r in recs)
    up = sum(1 for r in recs if r["pctVal"] > 0)
    dn = sum(1 for r in recs if r["pctVal"] < 0)
    fl = n - up - dn
    beh = {"抢筹": 0, "建仓": 0, "洗盘": 0, "出货": 0}
    for r in recs:
        beh[r["behavior"]] += 1
    avg = round(sum(r["strengthVal"] for r in recs) / n, 3) if n else 0
    industry_n = sum(1 for r in recs if r["kind"] == "行业")

    def slim(rows, k=12):
        return [{"name": r["name"], "kind": r["kind"], "strength": r["strengthVal"],
                 "darkY": round(r["darkVal"] / 1e8, 2), "pct": r["pctVal"],
                 "behavior": r["behavior"]} for r in rows[:k]]

    by_s = sorted(recs, key=lambda r: r["strengthVal"], reverse=True)
    by_d = sorted(recs, key=lambda r: r["darkVal"], reverse=True)
    summary = {
        "sectorCount": n, "industryCount": industry_n, "conceptCount": n - industry_n,
        "totalDarkY": round(tot_dark / 1e8, 1), "totalTurnoverY": round(tot_turn / 1e8, 1),
        "avgStrength": avg, "upCount": up, "downCount": dn, "flatCount": fl,
        "upRatio": round(up / n * 100, 1) if n else 0, "behavior": beh,
        "topByStrength": slim(by_s), "topDarkMoney": slim(by_d),
    }
    daily = {
        "date": date,
        "pulledAt": time.strftime("%Y-%m-%d %H:%M") + "（补期）",
        "source": "eastmoney 板块历史（换源补期）",
        "src": "eastmoney",
        "metric_note": ("本页为换源补期：原 westock 当日快照不可回溯。"
                        "强度口径 = 东财「主力净流入 / 成交额 × 100」，"
                        "与其余各期 westock 口径「(主力净流入 − 散户净流入) / 成交额 × 100」"
                        "**不是同一指标**，不可直接比较。"
                        "「主力资金 / 散户资金」拆项与领涨股东财此接口不提供，如实留「—」。"),
        "coverage": {"boards": len(tasks), "filled": n, "missing": miss},
        "summary": summary,
        "records": recs,
    }
    os.makedirs(DAILY_DIR, exist_ok=True)
    dst = os.path.join(DAILY_DIR, "%s.json" % date)
    json.dump(daily, open(dst, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    # 趋势汇总：写入 src 标记（不覆盖已存在的 westock 期）
    trend = []
    if os.path.exists(TREND_PATH):
        try:
            trend = json.load(open(TREND_PATH, encoding="utf-8"))
        except Exception:
            trend = []
    trend = [t for t in trend if t.get("date") != date]
    trend.append({
        "date": date, "totalDarkY": summary["totalDarkY"], "avgStrength": summary["avgStrength"],
        "upCount": up, "downCount": dn, "upRatio": summary["upRatio"],
        "qiangchou": beh["抢筹"], "jiancang": beh["建仓"], "xipan": beh["洗盘"], "chuhuo": beh["出货"],
        "sectorCount": n, "src": "eastmoney",
    })
    trend.sort(key=lambda t: t.get("date") or "")
    json.dump(trend, open(TREND_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    print("[ok] %s 记录 %d 条（缺 %d）→ %s" % (date, n, miss, os.path.relpath(dst, ROOT)))
    print("     行业 %d / 概念 %d ｜ avgStrength=%s ｜ 涨 %d 跌 %d ｜ 抢筹 %d 出货 %d"
          % (industry_n, n - industry_n, avg, up, dn, beh["抢筹"], beh["出货"]))
    print("     ★ 东财口径，已写入 sector_trend.json 的 src 标记，**不并入趋势线**")


if __name__ == "__main__":
    main()
