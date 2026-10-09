# -*- coding: utf-8 -*-
"""
三年未主升板块 · 数据底座（_fetch_long_kline.py）
=================================================
为什么需要它
------------
用户要「三年内没有主升过的板块」→ 必须有 **≥3 年（750 根）日K** 才能判定"三年内有没有主升"。
而 `quant/_txk_cache.json` 只有 252 根（2025-09-16 起，约 1 年），
本地缓存**根本无法支撑三年回溯**。腾讯 `fqkline` 实测能取到 760 根（2023-08-14 起）。

板块指数历史同样没有现成源：
- 腾讯对板块代码（`pt02GNxxxx`）只返回 1 根当日，不能用。
- → 只能**自建板块指数**：用「全市场每票日收益按流通市值加权」按日重建。

口径与做法
----------
1. 三年日K：逐票从腾讯补到 780 根，存到独立缓存 `quant/_long_kline.json`（不动 `_txk_cache`，
   避免污染其它池子已收敛的缓存与 sha）。
2. 板块成分：以 `sector_concept_{DATE}.json` 的 rows 取板块清单（概念 + 行业两套），
   成分股用 **每日全市场票池**（`_stock_names.json` 名单 ∩ 有日K 的票）按板块归属归集。
   ⚠ 板块成分历史不可得（接口只给当期），因此板块指数是**当前成分**的事后重建，
   存在成分漂移偏差（生存偏差方向已知：退市/被剔除的票不在池内）。
   页面必须如实标注这一点，不宣称是官方板块指数。
3. 断点续抓：已存在 `code` 且根数达标则跳过；失败票记 `_long_failed.json` 下次重试。

用法
----
    python _fetch_long_kline.py --n 780              # 全市场
    python _fetch_long_kline.py --n 780 --limit 800   # 只补前 800 只（试跑）
    python _fetch_long_kline.py --check                # 只查覆盖，不抓
"""
from __future__ import annotations
import os, sys, json, time, argparse, random, datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _tx_fetch as T
import _longk

LONG_CACHE = os.path.join(HERE, "_long_kline.json")
FAILED = os.path.join(HERE, "_long_failed.json")
NAMES = os.path.join(HERE, "_stock_names.json")

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")


def load_long():
    # 本文件是长K的生产者（写入方），但**读取**统一走 _longk，
    # 与 6 个消费脚本共用同一份 mtime 缓存，避免同一进程重复解析 401MB
    return _longk.load_long()


def save_long(d):
    tmp = LONG_CACHE + ".tmp"
    json.dump(d, open(tmp, "w", encoding="utf-8"), ensure_ascii=False)
    os.replace(tmp, LONG_CACHE)


def load_short():
    return json.load(open(T.CACHE, encoding="utf-8"))


def supported(code):
    """腾讯 fqkline 支持的代码段。

    ⚠ 实测：`bj920xxx`（北交所 920 段）**腾讯完全不返回**（连续 100 只全部 0 根，
      不是限流）。若不跳过，票池按代码排序时 bj 段排在最前，会把抓取时间全耗在
      永远失败的票上。sh/sz 全段正常（含 sh688 科创板）。
    """
    if not code or len(code) < 6:
        return False
    if code.startswith("bj"):
        # 北交所：只有 bj43x / bj83x / bj87x 老段在腾讯有；920 段没有
        return not code.startswith("bj92")
    return code[:2] in ("sh", "sz")


def code_list():
    """全部票池：_stock_names.json 的名单（它就是每日全市场扫描用的票池）。"""
    if os.path.exists(NAMES):
        try:
            d = json.load(open(NAMES, encoding="utf-8"))
            if isinstance(d, dict):
                ks = list(d.keys())
                if ks and isinstance(ks[0], str) and ks[0][:2] in ("sh", "sz", "bj"):
                    return sorted(k for k in ks if supported(k))
            if isinstance(d, list):
                return sorted(x for x in d if supported(x))
        except Exception:
            pass
    return sorted(k for k in load_short().keys() if supported(k))


def fetch_one(code, n, tries=3):
    """直接打腾讯 fqkline（不复用 _tx_fetch 的 250 根缓存判断）。

    ⚠ 批量抓取必须节流：60 连发实测会被服务端限流，只返回 1 根当日数据
    （**返回 200 + 合法 JSON，不是错误码**，不节流就会静默抓出一堆 1 根的假数据）。
    因此这里固定 sleep + 失败指数退避；上层还会按根数校验再丢弃。
    """
    url = "%s?param=%s,day,,,%d,qfq" % (T.TX_KLINE, code, n)
    for i in range(tries):
        try:
            import urllib.request
            req = urllib.request.Request(url, headers={
                "User-Agent": UA, "Referer": "https://gu.qq.com/", "Connection": "close"})
            with urllib.request.urlopen(req, timeout=25) as r:
                j = json.loads(r.read().decode("utf-8"))
            d = ((j.get("data") or {}).get(code) or {})
            ks = d.get("qfqday") or d.get("day") or []
            out = []
            for it in ks:
                try:
                    out.append({"date": it[0], "open": float(it[1]), "last": float(it[2]),
                                "high": float(it[3]), "low": float(it[4]),
                                "volume": float(it[5])})
                except Exception:
                    continue
            # 根数不足 = 被限流（真实新股也不会有 480 根），不当成功
            if len(out) >= MIN_ACCEPT:
                return out
            time.sleep(1.2 * (i + 1))
        except Exception:
            time.sleep(1.2 * (i + 1))
    return []


# 判定「这次拿到的是完整历史」的最低根数。低于它一律视为限流/异常，丢弃重试。
MIN_ACCEPT = 480


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=780, help="请求根数（780≈3.2年，多抓备用）")
    ap.add_argument("--limit", type=int, default=0, help="只处理前 N 只（0=全部）")
    ap.add_argument("--minbars", type=int, default=480,
                    help="达标根数。★默认 480≈2 年（用户 2026-10-02 确认「2 年没主升过也行」）")
    ap.add_argument("--check", action="store_true", help="只查覆盖不抓")
    ap.add_argument("--merge", action="store_true", help="同时把已有 252 根短缓存并入")
    ap.add_argument("--asof", default=None,
                    help="★只补「末根日期 < ASOF」的标的（默认今日）。"
                         "解决旧判据「根数达标就跳过」→ 永远补不进最新交易日")
    ap.add_argument("--workers", type=int, default=12, help="并发数（原串行版在「全票需补」时不可用）")
    a = ap.parse_args()

    codes = code_list()
    if a.limit:
        codes = codes[:a.limit]
    print("[票池] %d 只" % len(codes))

    if a.check:
        d = load_long()
        if a.merge:
            d2 = load_short()
            for c, bars in d2.items():
                if c not in d or len(d[c]) < len(bars):
                    d[c] = bars
            save_long(d)
        ok = [c for c in codes if len(d.get(c, [])) >= a.minbars]
        bars = [len(d[c]) for c in ok]
        print("[覆盖] 达标 %d/%d（根数≥%d）" % (len(ok), len(codes), a.minbars))
        if bars:
            print("        根数 min/中位/max = %d/%d/%d" % (min(bars), sorted(bars)[len(bars) // 2], max(bars)))
        if d:
            anyb = next(iter(d.values()))
            print("        覆盖区间示例：%s ~ %s" % (anyb[0]["date"], anyb[-1]["date"]))
        return

    long_d = load_long()
    if a.merge:
        short = load_short()
        n_merge = 0
        for c, bars in short.items():
            if c not in long_d or len(long_d[c]) < len(bars):
                long_d[c] = bars
                n_merge += 1
        print("[merge] 并入短缓存 %d 只" % n_merge)

    failed = {}
    if os.path.exists(FAILED):
        try:
            failed = json.load(open(FAILED, encoding="utf-8"))
        except Exception:
            failed = {}

    ASOF = a.asof or datetime.date.today().strftime("%Y-%m-%d")

    def _needs(c):
        """需补 = 根数不足 或 **末根日期 < ASOF**。

        ★ 不能只看根数：达标票（≥480 根）的末根会一直停在补数那一天，
          永远不进 todo → 「补齐脚本补不动最新交易日」。
        """
        b = long_d.get(c, [])
        if len(b) < a.minbars:
            return True
        return str(b[-1].get("date", "")) < ASOF

    todo = [c for c in codes if _needs(c)]
    n_stale = sum(1 for c in codes
                  if len(long_d.get(c, [])) >= a.minbars and _needs(c))
    print("[待抓] %d 只（其中已达标但末根< %s 的 %d 只）" % (len(todo), ASOF, n_stale))

    ok = 0
    fail = 0
    done = 0
    t0 = time.time()
    # ★ 2026-10-09 改并发：原串行「每只 sleep 0.35 + 请求」在**全部票都需补**
    #   的场景下要跑 40 分钟以上（旧判据只补极少数缺根票，才显得够快）。
    #   fetch_one 内已含失败退避与根数校验，这里按并发调度。
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        futs = {ex.submit(fetch_one, c, a.n): c for c in todo}
        for f in as_completed(futs):
            c = futs[f]
            try:
                bars = f.result()
            except Exception:
                bars = []
            if len(bars) >= a.minbars:
                long_d[c] = bars
                failed.pop(c, None)
                ok += 1
            else:
                # 抓到的根数不足（限流 / 新股 / 长期停牌）：不写入当历史，避免污染底座
                failed[c] = len(bars)
                fail += 1
            done += 1
            if done % 400 == 0:      # 401MB 落盘 ~1-2s，太密会拖慢
                save_long(long_d)
                json.dump(failed, open(FAILED, "w", encoding="utf-8"), ensure_ascii=False)
                el = time.time() - t0
                rate = done / el if el else 0
                left = (len(todo) - done) / rate if rate else 0
                print("  %d/%d  成功 %d  失败 %d  %.0f票/分  剩余约 %.1f 分"
                      % (done, len(todo), ok, fail, rate * 60, left / 60), flush=True)
    save_long(long_d)
    json.dump(failed, open(FAILED, "w", encoding="utf-8"), ensure_ascii=False)

    print("[完成] 成功 %d / 失败 %d" % (ok, fail))
    bars = [len(v) for v in long_d.values()]
    if bars:
        print("[缓存] 票数 %d  根数 min/中位/max = %d/%d/%d"
              % (len(long_d), min(bars), sorted(bars)[len(bars) // 2], max(bars)))
        anyb = next(iter(long_d.values()))
        print("[区间] %s ~ %s" % (anyb[0]["date"], anyb[-1]["date"]))


if __name__ == "__main__":
    main()
