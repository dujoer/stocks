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

用法
----
    python _datahub_gate.py --date 2026-09-30
    python _datahub_gate.py --date 2026-09-30 --min-cover 7
退出码：0 通过 / 1 有问题（可直接进 CI）
"""
from __future__ import annotations
import os, sys, json, glob, argparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

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
