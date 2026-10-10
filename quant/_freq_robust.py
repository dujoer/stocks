#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""跨采样频率稳健性（第五道闸）——把「跨步长」从 2 点扩成多点扫描

为什么新增这道闸
----------------
出票核验原本的「跨步长」只比 **step5（主口径）vs step3（派生）** 两个点，
三连阴池当年就是在这个薄弱处翻了车：step5 下 ★观察档 edge +0.245pp（R3 85.6%）看着能用，
但换个采样频率结论就变 —— 实测七个频率的结果：

    step    1      2      3      5      8      10     20
    edge  -0.094 -0.067 +0.061 +0.245 -0.391 +0.350 +0.884   （单位 pp，★观察档）

符号在正负之间来回跳 —— 这种 edge 不是「弱」，是**不存在**。两点对比看不出这一点，
必须扫频谱。

判据（比现有闸更严，不许放宽凑数）
--------------------------------
对每个档位，取**等量对照**（同日非本档；出票取更严口径）：

    ① 符号一致：所有扫描频率的 edge 同号（sign flip = 0）
    ② R3 一致：所有频率的 R3 都 ≥ 95%
    ③ 逐频率 edge > 0

三条同时满足 → 该档「频率稳健」；否则一律不可出票，并在产物里写明翻转位置，
**证伪结论保留不删**（项目红线）。

★ bootstrap 次数固定（BOOT）并写入产物 `boot` 键：否则同数据两次跑会得到不同 R3。

用法：
    python3 _freq_robust.py --pool 3yl --steps 1,2,3,5,8,10,20
产出：quant/_freq_robust_{pool}.json
"""
from __future__ import annotations
import os, sys, json, argparse

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

import _gate_common as GC

BOOT = GC.BOOT
SEED = 20261010

#: 对照基准档：**不参与出票判定**。
#: ALL（全市场域）/ HARD（深跌域母集）/ BASE（生产基底）本身是「拿来比」的尺子，
#: 它们相对任何对照都恒为正或恒为 0 —— 判成「稳健」等于自己造出一个假 alpha。
SKIP_TIERS = ("ALL", "HARD", "BASE")

# 池注册表：分两族
#   A 族（三连阴）：BUCKETS=(label,key,lo,hi) + pick(key)->闭包 + ctrl_all/ctrl_same
#   B 族（反转/高胜率）：TIERS=(key,desc) + pick(r,key) 或 _sel(key) + 各池自带对照
POOLS = {
    "3yl": {"mod": "_3yl_tier_gate", "cn": "三连阴", "steps": [1, 2, 3, 5, 8, 10, 20]},
    "rev": {"mod": "_rev_tier_gate", "cn": "底部反转", "steps": [1, 3, 5, 10, 20]},
}


def load_pool(name):
    key = POOLS.get(name)
    if not key:
        raise SystemExit("未知池 %r，可选：%s" % (name, list(POOLS)))
    mod = __import__(key["mod"])
    return key, mod, adapt(mod, name)


def adapt(mod, pool):
    """把两族池统一成 (tiers, sel, ctrl_all, ctrl_same[, build]) 接口。"""
    if hasattr(mod, "BUCKETS"):                      # A 族（三连阴）
        for fn in ("build_panel", "pick", "ctrl_all", "ctrl_same"):
            if not hasattr(mod, fn):
                raise SystemExit("池 %s 缺接口 %s" % (pool, fn))
        return ([(b[1], b[0]) for b in mod.BUCKETS],
                lambda k: mod.pick(k), mod.ctrl_all, mod.ctrl_same)
    if not hasattr(mod, "TIERS"):                    # B 族
        raise SystemExit("池 %s 既无 BUCKETS 也无 TIERS" % pool)
    tiers = [(k, d) for k, d in mod.TIERS]

    def _build(st):
        """重建面板 + **补分档**。
        ★ 反转/高胜率的 A/B/CORE 档由独立 `assign(rows)` 切出，漏调它会让所有分档恒空、
          报成「样本不足」—— 实测反转 A/B 档就是这样整档消失的。"""
        rows = mod.build_panel(limit=0, step=st, verbose=False)
        if hasattr(mod, "assign"):
            mod.assign(rows)
        return rows

    if hasattr(mod, "_sel"):                         # 反转：_sel 闭包 + deep 域字段
        sel = lambda k: mod._sel(k)
        ctrl_all = lambda r: True
        # ★ 对照口径：主 gate 的主口径是「vs 全市场域」（vs='HARD' 只在辅助表里用）。
        #   若这里改用深跌域做对照，HARD 档差恒为 0、ALL 档必然为正 —— 那是定义使然，
        #   不是 alpha。判定必须与生产主口径一致，否则等于自己造出「稳健档」。
        ctrl_same = lambda r, k=None: True
        build = _build
    else:                                            # 高胜率：pick(r,key) + _ctrl_fn
        sel = lambda k: (lambda r, kk=k: mod.pick(r, kk))
        ctrl_all = lambda r: True
        ctrl_same = lambda r, k=None: mod._ctrl_fn(None)(r)
        build = _build
    return tiers, sel, ctrl_all, ctrl_same, build


def scan(mod, steps, api):
    """逐频率重建面板 → 各档 edge/R3（母集 + 等量双对照）。"""
    tiers, sel, ctrl_all, ctrl_same = api[0], api[1], api[2], api[3]
    build = api[4] if len(api) > 4 else (lambda st: mod.build_panel(st))
    rows_all = []
    for st in steps:
        built = build(st)
        # 各池 build_panel 返回形态不一：(rows,d0,d1) / (rows,) / rows —— 统一拆包
        if isinstance(built, tuple):
            rows = built[0]
            d0, d1 = (list(built[1:3]) + ["", ""])[:2]
        else:
            rows, d0, d1 = built, "", ""
        for key, label in tiers:
            m = GC.edge_stats(rows, sel(key), ctrl_all,
                              boot=BOOT, seed=SEED, name=key)
            e = GC.edge_stats(rows, sel(key), lambda r, kk=key: ctrl_same(r, kk),
                              boot=BOOT, seed=SEED, name=key)
            rows_all.append(dict(
                step=st, tier=key, label=label,
                n_rows=m.get("n_rows"), n_days=m.get("n_days"),
                edge=m.get("edge"), r3=m.get("r3"),
                edge_excl=e.get("edge"), r3_excl=e.get("r3"),
                loo_min=m.get("loo_min"), loo_max=m.get("loo_max"),
                note=m.get("note") or e.get("note") or ""))
        print("  step=%-3d 面板 %d 行（%s ~ %s）" % (st, len(rows), d0, d1), flush=True)
    return rows_all


def judge(rows_all):
    """按档位聚合：符号一致 + 全频率 R3≥95% + edge>0。"""
    tiers = []
    keys = []
    for r in rows_all:
        if r["tier"] not in keys:
            keys.append(r["tier"])
    for k in keys:
        rs = sorted([r for r in rows_all if r["tier"] == k], key=lambda x: x["step"])
        edges = [r["edge_excl"] for r in rs if r["edge_excl"] is not None]
        r3s = [r["r3_excl"] for r in rs if r["r3_excl"] is not None]
        if not edges:
            continue
        signs = [1 if e > 0 else (-1 if e < 0 else 0) for e in edges]
        flips = sum(1 for i in range(1, len(signs)) if signs[i] != signs[i - 1])
        all_pos = all(e > 0 for e in edges)
        # ★ GC.edge_stats 的 r3 是**百分数**（0~100），不是比例 —— 按 0-1 比会永远判通过
        min_r3 = min(r3s) if r3s else 0.0
        baseline = k in SKIP_TIERS
        ok = (not baseline) and (flips == 0) and all_pos and (min_r3 >= 95.0)
        # 翻转位置（写进产物，证伪可追溯）
        flip_at = [rs[i]["step"] for i in range(1, len(signs)) if signs[i] != signs[i - 1]]
        tiers.append(dict(
            tier=k, label=rs[0]["label"], ok=ok, baseline=baseline,
            flips=flips, flip_at=flip_at,
            min_r3=round(min_r3, 4),
            edge_min=round(min(edges), 4), edge_max=round(max(edges), 4),
            steps=[r["step"] for r in rs],
            n_days=[r["n_days"] for r in rs],
            n_rows=[r["n_rows"] for r in rs],
            edges=edges, r3s=r3s,
        ))
    return tiers


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pool", default="3yl")
    ap.add_argument("--steps", default="")
    a = ap.parse_args()
    key, mod, api = load_pool(a.pool)
    steps = [int(x) for x in a.steps.split(",")] if a.steps else key["steps"]
    print("[freq] 池=%s 频率=%s" % (key["cn"], steps), flush=True)
    rows_all = scan(mod, steps, api)
    tiers = judge(rows_all)
    out = dict(_doc="跨采样频率稳健性（第五道闸：符号一致 + 全频率 R3≥95%）",
               pool=a.pool, pool_cn=key["cn"], steps=steps,
               seed=SEED, boot=BOOT,
               n_ok=sum(1 for t in tiers if t["ok"]),
               tiers=tiers, detail=rows_all)
    op = os.path.join(_HERE, "_freq_robust_%s.json" % a.pool)
    json.dump(out, open(op, "w", encoding="utf-8"), ensure_ascii=False)

    print("\n=== 频率稳健性判定（等量对照，更严口径）===")
    for t in tiers:
        tag = "（对照基准档·不判定）" if t["baseline"] else ""
        print("  %-6s %s  符号翻转 %d 次%s｜全频率 R3 最低 %.1f%%｜edge 区间 [%+.3f, %+.3f]pp%s"
              % (t["tier"], "✅稳健" if t["ok"] else "❌不可出票",
                 t["flips"], ("@" + ",".join(map(str, t["flip_at"]))) if t["flip_at"] else "",
                 t["min_r3"], t["edge_min"], t["edge_max"], tag))
    print("  → 可出票档位：%d 个" % out["n_ok"])
    print("\n[out]", op)


if __name__ == "__main__":
    main()