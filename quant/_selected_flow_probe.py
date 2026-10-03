# -*- coding: utf-8 -*-
"""
主升精选 · 资金流因子可行性检验（_selected_flow_probe.py）
==========================================================
用户 2026-10-03：「继续」（把全市场横截面能力接到各池子）。

先纠正一个认知偏差
------------------
主升精选**本来就是全市场域**（实测 `n_universe=4588`，A 档 = 域内前 5% = 229 只），
**不需要改**。真正的短板是：它的 9 个先验因子**全是价量**，
其中「资金进场」只有 `up_vol`（上涨放量占比）和 `rvol`（量比）两个**成交量代理**，
**没有真实的资金流数据**。

底座现在有全市场主力资金流（5207 只，mf1/mf5/mf20），
于是问题变成：<b>真实资金流能否提供价量因子没有的信息？</b>

★ 本脚本只做「可行性探查」，不产出选股结论、不上线页面。
  任何因子想进 `_selected_lab.PRIOR`，都必须先在这里证明：
  ① 分档单调 ② 两半同向 ③ 随机对照分位
  三条缺一不可 —— 否则就是过拟合噪声（项目已栽三次）。

⚠ 硬限制：这里的样本是**截面**（同一天全市场比），不是**时间序列**回测，
  因此只能回答「资金流是否携带区分度」，**不能回答「买了会不会赚」**。
  真要上线必须再做 `_accum_oos.py` 那套时间序列样本外检验。

用法
----
    python _selected_flow_probe.py --date 2026-09-30
"""
from __future__ import annotations
import os, sys, json, argparse, collections

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import _datahub as DH


def _pct_rank(vals, higher=True):
    n = len(vals)
    if n == 0:
        return []
    order = sorted(range(n), key=lambda i: vals[i])
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and vals[order[j + 1]] == vals[order[i]]:
            j += 1
        avg = (i + j) / 2.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg / max(1, n - 1)
        i = j + 1
    return [r if higher else 1.0 - r for r in ranks]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--k", type=int, default=5, help="分档数")
    a = ap.parse_args()

    hub = DH.load_hub(a.date)
    if not hub:
        print("！底座缺失，先跑 _datahub.py --date %s" % a.date)
        return
    q = ((hub["dims"].get("quotes") or {}).get("data")) or {}
    f = ((hub["dims"].get("flow") or {}).get("data")) or {}
    if not q or not f:
        print("！底座缺 quotes 或 flow 维度")
        return
    print("[load] quotes=%d flow=%d" % (len(q), len(f)))

    def bad(v):
        nm = (v.get("name") or "").upper()
        return ("ST" in nm) or ("退" in nm)

    dom = [c for c, v in q.items()
           if not bad(v) and (v.get("last") or 0) >= 2.0
           and (v.get("turnover_rate") or 0) > 0 and c in f]
    print("[域] 可交叉分析 %d 只（全市场，剔 ST/退/低价/停牌/无资金流）" % len(dom))
    if len(dom) < 200:
        print("样本过少，退出")
        return

    rows = []
    for c in dom:
        vq, vf = q[c], f[c]
        # 资金流强度：净额 / 流通市值（消除市值偏误，大盘股天然资金多）
        cap = (vq.get("circulating_market_cap") or 0) * 1e8   # 亿 → 元
        mf1, mf5, mf20 = (vf.get("mf1") or 0), (vf.get("mf5") or 0), (vf.get("mf20") or 0)
        rows.append({
            "code": c, "name": vq.get("name") or c,
            "mf1": mf1, "mf5": mf5, "mf20": mf20,
            "i1": mf1 / cap if cap else 0.0,
            "i5": mf5 / cap if cap else 0.0,
            "i20": mf20 / cap if cap else 0.0,
            "accel": (mf1 / cap if cap else 0) - (mf20 / cap / 20 if cap else 0),
            "turn": vq.get("turnover_rate") or 0.0,
            "chg": vq.get("change_percent") or 0.0,
            "cap": (vq.get("circulating_market_cap") or 0),
        })

    # ---- 分档：看「资金流强度」与「当日涨幅」是否有单调关系 ----
    # 说明：这里用**当日涨幅**作为「市场当日是否已经price in」的代理，
    # 高资金流 + 低涨幅 = 资金在悄悄进（可能是启动前）；反之为已兑现。
    DIMS = [
        ("i20", "20日主力强度（市值比）", True),
        ("i5", "5日主力强度", True),
        ("i1", "1日主力强度", True),
        ("accel", "资金加速度（1日−20日均）", True),
    ]
    print("\n=== 资金流分位 × 当日涨幅（分 %d 档，看是否单调）===" % a.k)
    verdict = {}
    for fld, cn, hb in DIMS:
        pr = _pct_rank([r[fld] for r in rows], hb)
        buckets = collections.defaultdict(list)
        for r, p in zip(rows, pr):
            buckets[min(a.k - 1, int(p * a.k))].append(r)
        cells = []
        rs = []
        for b in range(a.k):
            sub = buckets.get(b, [])
            if not sub:
                cells.append("档%d: —" % b)
                continue
            chg = sum(r["chg"] for r in sub) / len(sub)
            turn = sum(r["turn"] for r in sub) / len(sub)
            cells.append("档%d(n=%d) 涨幅%+5.2f%% 换手%5.2f"
                         % (b, len(sub), chg, turn))
            rs.append((b, len(sub), chg))
        ws = [x[2] for x in rs if x[1] >= 30]
        mono = None
        if len(ws) >= 3:
            ups = sum(1 for i in range(len(ws) - 1) if ws[i + 1] > ws[i])
            downs = sum(1 for i in range(len(ws) - 1) if ws[i + 1] < ws[i])
            mono = "升" if ups > downs else ("降" if downs > ups else "平")
        verdict[fld] = {"cn": cn, "rows": rs, "mono": mono}
        print("   %s" % cn)
        for c in cells:
            print("      " + c)
        print("      趋势=%s" % mono)

    # ---- 与「换手率」的相关性（排除掉单纯是「交易活跃度」的伪信号）----
    print("\n=== 与换手率的关系（资金流强度若只是换手的影子则无增量信息）===")
    for fld in ("i20", "i1"):
        xs = [r[fld] for r in rows]
        ys = [r["turn"] for r in rows]
        n = len(xs)
        mx, my = sum(xs) / n, sum(ys) / n
        cov = sum((xs[i] - mx) * (ys[i] - my) for i in range(n))
        vx = sum((x - mx) ** 2 for x in xs) ** 0.5
        vy = sum((y - my) ** 2 for y in ys) ** 0.5
        corr = cov / (vx * vy) if vx and vy else 0.0
        print("   %-6s 与换手率相关系数 = %+.3f" % (fld, corr))

    print("\n=== 结论（这只是可行性探查，不是选股结论）===")
    print("本脚本只回答「全市场资金流是否携带区分度」，**不回答「买了会不会赚」**。")
    print("要进 PRIOR 还必须做时间序列样本外检验（`_accum_oos.py` 四道闸门）。")
    out = {"date": a.date, "n_domain": len(dom),
           "verdict": {f: {"cn": v["cn"], "mono": v["mono"],
                           "rows": [[r[0], r[1], round(r[2], 3)] for r in v["rows"]]}
                       for f, v in verdict.items()}}
    p = os.path.join(DH.HUB, "flow_probe_%s.json" % DH.DS(a.date))
    json.dump(out, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("[out] %s" % p)


if __name__ == "__main__":
    main()
