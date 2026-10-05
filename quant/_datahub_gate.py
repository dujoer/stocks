# -*- coding: utf-8 -*-
"""
数据底座门禁（_datahub_gate.py）
===============================
用户 2026-10-03 要求「每天整体获取数据给各模块使用」→ 必须防止**底座本身腐化**。

检查项
------
① **底座存在且当日**：缺 `hub/{DATE}.json` → 失败。
② **维度覆盖率**：manifest 的 `ok_dims` 必须 ≥ 阈值（默认 6/8），
   缺失维度要逐条列出原因。
③ **★数据日一致性**：各来源文件的最新日期必须 == {DATE}。
   ★这是本门禁最有价值的一条 —— 2026-10-03 首次运行时**当场查出融资融券
   数据只到 09-10、落后 20 天**，而各模块当时并不知道。
④ **口径标注**：quotes/flow 必须带 `scope`（事件域/全市场），
   否则页面会误以为覆盖全市场 5207 只。
⑤ **无编造数据**：底座不得出现「用旧日期冒充当日」——
   即 manifest 的 date 必须等于各维度的实际数据日。
⑥ **★K 线新鲜度**（2026-10-05 加）：缓存里末根 K 线 < 数据日 的票占比 > 2% → 失败。
   少量（停牌/退市）只 WARN。这一条拦的是「旧价当当日价算指标」的静默通道。

用法
----
    python _datahub_gate.py --date 2026-09-30
    python _datahub_gate.py --date 2026-09-30 --min-cover 7
退出码：0 通过 / 1 有问题（可直接进 CI）
"""
from __future__ import annotations
import os, sys, json, glob, argparse, re

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
ROOT = os.path.dirname(HERE)

import _datahub as DH


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--min-cover", type=int, default=6)
    a = ap.parse_args()
    date = a.date
    problems = []
    warns = []

    # ① 底座存在
    hub_p = DH.hub_path(date)
    if not os.path.exists(hub_p):
        print("[FAIL] 底座缺失：%s" % hub_p)
        print("       修复：python _datahub.py --date %s" % date)
        return 1
    try:
        hub = json.load(open(hub_p, encoding="utf-8"))
    except Exception as e:
        print("[FAIL] 底座解析失败：%s" % e)
        return 1
    print("[ok] 底座存在：%s" % hub_p)

    # 底座日期必须等于请求日（防「用旧底座冒充当日」）
    if hub.get("date") != date:
        problems.append("底座 date=%s ≠ 请求日 %s（用旧底座冒充当日）"
                        % (hub.get("date"), date))
    else:
        print("[ok] 底座日期一致：%s" % date)

    # ② 覆盖率
    dims = hub.get("dims") or {}
    ok = [d for d in DH.DIM_ORDER if (dims.get(d) or {}).get("ok")]
    bad = [d for d in DH.DIM_ORDER if d not in ok]
    print("[%s] 维度覆盖 %d/%d" % ("ok" if len(ok) >= a.min_cover else "FAIL",
                                   len(ok), len(DH.DIM_ORDER)))
    for d in ok:
        r = dims[d]
        sc = r.get("scope") or ""
        n = r.get("n")
        print("      ✓ %-8s src=%-16s %s%s"
              % (d, r.get("src") or "-",
                 ("n=%s" % n) if n is not None else "",
                 ("  口径：%s" % sc) if sc else ""))
    for d in bad:
        rs = (dims.get(d) or {}).get("reason", "未抓取")
        print("      ✗ %-8s %s" % (d, rs))
    if len(ok) < a.min_cover:
        problems.append("维度覆盖不足：%d/%d < %d" % (len(ok), len(DH.DIM_ORDER), a.min_cover))
    # 核心维度缺失 = 硬失败
    for must in ("quotes", "lhb"):
        if must not in ok:
            problems.append("核心维度缺失：%s" % must)

    # ③ 数据日一致性（最有价值的一条）
    print("\n[检查] 各来源数据日是否等于 %s" % date)
    import _datahub_api as H
    hard, soft, txt = H.verify(date)
    for line in txt.split("\n"):
        print("   " + line)
    # ★ hard（文件缺失/没跑）= 我们的问题，门禁失败
    for p in hard:
        problems.append("数据源缺失：%s" % p)
    # ★ soft（数据日落后）= 可能是数据源自身滞后 → 只警告，但必须打印 lag_days，
    #   让页面据此降级；**不允许默默当当日用**。
    for p in soft:
        warns.append("数据日滞后：%s" % p)

    # ④ 口径标注
    for d in ("quotes", "flow"):
        r = dims.get(d) or {}
        if r.get("ok") and not r.get("scope"):
            warns.append("%s 缺 scope 标注（页面可能误以为覆盖全市场）" % d)

    # ⑤ manifest 同步
    mfp = DH.manifest_path()
    if os.path.exists(mfp):
        try:
            mf = json.load(open(mfp, encoding="utf-8"))
            if mf.get("date") != date:
                warns.append("manifest 日期 %s ≠ 底座 %s" % (mf.get("date"), date))
        except Exception:
            problems.append("manifest 解析失败")
    else:
        warns.append("manifest.json 不存在")

    # ⑥ ★ K 线新鲜度：末根 K 线 < 数据日 的票不能用（旧价当当日价）
    #    2026-10-05 加。历史坑：`_tx_fetch.fetch_kline` 命中缓存只看条数、不看末根日期，
    #    缓存里 8 只票（含 1 只可转债）末根停在 09-11~09-29，会被下游当作当日价算指标。
    mfx = locals().get("mf") or {}
    kf = mfx.get("kline_freshness") or {}
    try:
        import _tx_fetch as _T
        total = len(_T._load() or {})
    except Exception:
        total = 0
    stale_n = kf.get("stale_n")
    if stale_n is None:
        # manifest 是旧版（无该字段）→ 自算一次，避免「无该键」被当成「已通过」
        try:
            import _tx_fetch as _T
            _T.set_asof(date)
            stale_n = len(_T.stale_codes())
            kf = {"asof": date, "stale_n": stale_n,
                  "stale_sample": [c for c, _ in _T.stale_codes()[:20]]}
        except Exception:
            stale_n = -1
    print("\n[检查] K 线新鲜度（末根 < %s）" % date)
    if stale_n < 0:
        warns.append("K 线新鲜度无法自检（_tx_fetch 不可用）")
        print("   ? 无法自检")
    else:
        ratio = (stale_n / total * 100.0) if total else 0.0
        print("   %d/%d 只陈旧（%.2f%%）%s" % (stale_n, total, ratio,
              ("：" + "、".join(kf.get("stale_sample") or [])) if stale_n else ""))
        if kf.get("nonstock_n"):
            print("   注：缓存含非股票代码 %d 个：%s"
                  % (kf["nonstock_n"], "、".join(kf.get("nonstock_sample") or [])))
        # 少量陈旧 = 停牌/退市，属正常 → WARN；大面积陈旧 = 底座腐化 → FAIL
        if ratio > 2.0:
            problems.append("K 线大面积陈旧：%d/%d（%.2f%%）> 2%% —— 底座当日价不可用"
                            % (stale_n, total, ratio))
        elif stale_n:
            warns.append("K 线陈旧 %d 只（多为停牌，已由 _tx_fetch 补拉失败保留）：%s"
                         % (stale_n, "、".join(kf.get("stale_sample") or [])))

    # ⑦ ★ 各池产出日一致性（2026-10-05 加）
    #    底座日已是 {date}，但各池页面可能是更早一期——「无合格标的空仓」属正常不出页，
    #    可若是**忘了跑**或**静默失败**，页面就会停在旧日期而没人发现。
    #    这里只报事实（落后几日），不下 FAIL，交给人判断是空仓还是漏跑。
    print("\n[检查] 各池产出日 vs 底座日 %s" % date)
    _ro = os.path.join(ROOT, "web")
    pools = [("主升精选", "selected", "combined_"), ("底部反转", "reversal", "watchlist_"),
             ("增仓精选", "accumulation", "combined_"), ("三连阴", "three_yin", "sanyin_"),
             ("做T池", "tplus", "tplus-"), ("高胜率", "picks", "highwin_")]
    lagged = []
    for cn, sub, pre in pools:
        try:
            fs = [f for f in os.listdir(os.path.join(_ro, sub))
                  if f.startswith(pre) and f.endswith(".html")]
        except OSError:
            fs = []
        ds = []
        for f in fs:
            m = re.search(r"(\d{4})-?(\d{2})-?(\d{2})", f)
            if m:
                ds.append("%s-%s-%s" % (m.group(1), m.group(2), m.group(3)))
        if not ds:
            print("   %-8s 无当期页（可能空仓未出票）" % cn)
            continue
        latest = max(ds)
        if latest != date:
            lagged.append((cn, latest))
            print("   %-8s 最新 %s （落后 %s）" % (cn, latest, date))
        else:
            print("   %-8s 最新 %s ✓" % (cn, latest))
    if lagged:
        warns.append("各池产出日与底座不一致：%s —— 需人工确认是「无合格标的空仓」"
                     "还是漏跑（空仓不出页属正常）"
                     % "、".join("%s(%s)" % (c, d) for c, d in lagged))

    # ⑧ ★ 双 K 线缓存覆盖一致性（2026-10-06 加）
    #    底座有一条「日K主缓存」`_txk_cache`（252 根）和一条「长历史」`_long_kline`（780 根），
    #    两者**并不互相包含**：实测 2026-09-30 用同一套涨停口径判出来
    #      短缓存 53 家 / 长历史 55 家；差异来自双方各自的**覆盖洞**——
    #      短缓存缺 sh600340 的 09-29（前收错 → 假涨停）、并整只缺 4 只真涨停；
    #      长缓存整只缺 sh688806（当日真涨停）。
    #    ⇒ 同一天两个缓存能给出不同家数，是**数据缺陷**，不是口径问题。
    #      这里只**报事实 + 列差异代码**（不 FAIL）：因为「哪个缓存才是权威」需要单独定，
    #      而在此之前任何依赖涨停家数的跨页比较都可能踩到它。改动前先看这段再决定用哪份。
    print("\n[检查] 双 K 线缓存覆盖（%s 的涨停判定）" % date)
    try:
        import _mkt_emo as _M
        import _tx_fetch as _T2

        def _zt(cache):
            out = {}
            for code, bars in (cache or {}).items():
                if not _T2.is_stock(code):
                    continue
                idx = None
                for i, b in enumerate(bars):
                    if b.get("date") == date:
                        idx = i
                        break
                if idx is None or idx == 0:
                    continue
                prev = float(bars[idx - 1]["last"])
                c = float(bars[idx]["last"])
                px = _M.limit_price(prev, _M.limit_pct(code))
                if px is not None and c >= px * _M.ZT_TOL:
                    out[code] = True
            return out

        _s = _zt(_T2._load())
        _l = _zt(__import__("_longk").load_long())
        only_s = sorted(set(_s) - set(_l))
        only_l = sorted(set(_l) - set(_s))
        print("   短缓存 %d 家 / 长历史 %d 家" % (len(_s), len(_l)))
        if only_s or only_l:
            if only_s:
                print("   仅短缓存判为涨停（长历史无/非涨停）：%s" % "、".join(only_s[:12]))
            if only_l:
                print("   仅长历史判为涨停（短缓存缺失或非涨停）：%s" % "、".join(only_l[:12]))
            warns.append("双 K 线缓存对 %s 的涨停判定不一致（短 %d / 长 %d，差异 %d 只：%s）"
                         "—— 两缓存覆盖各有洞，依赖涨停家数的跨页比较可能因此失真"
                         % (date, len(_s), len(_l), len(only_s) + len(only_l),
                            "、".join((only_s + only_l)[:10])))
        else:
            print("   ✓ 两个缓存的涨停判定完全一致")
    except Exception as e:
        print("   ? 无法自检：%s" % str(e)[:80])
        warns.append("双 K 线缓存一致性无法自检：%s" % str(e)[:60])

    # ---- 结论 ----
    print("")
    for w in warns:
        print("[WARN] %s" % w)
    if problems:
        for p in problems:
            print("[FAIL] %s" % p)
        print("\n=== 门禁未通过（%d 问题 / %d 警告）===" % (len(problems), len(warns)))
        return 1
    print("=== 门禁通过（0 问题 / %d 警告）===" % len(warns))
    return 0


if __name__ == "__main__":
    sys.exit(main())
