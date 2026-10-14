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
from collections import defaultdict

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

import _gate_common as GC

BOOT = GC.BOOT
SEED = 20261010

#: 对照基准档：**不参与出票判定**。
#: ALL（全市场域）/ HARD（深跌域母集）/ BASE（生产基底）本身是「拿来比」的尺子，
#: 它们相对任何对照都恒为正或恒为 0 —— 判成「稳健」等于自己造出一个假 alpha。
SKIP_TIERS = ("ALL", "HARD", "BASE", "REST")

# 池注册表：分两族
#   A 族（三连阴）：BUCKETS=(label,key,lo,hi) + pick(key)->闭包 + ctrl_all/ctrl_same
#   B 族（反转/高胜率）：TIERS=(key,desc) + pick(r,key) 或 _sel(key) + 各池自带对照
POOLS = {
    "3yl": {"mod": "_3yl_tier_gate", "cn": "三连阴", "steps": [1, 2, 3, 5, 8, 10, 20]},
    "rev": {"mod": "_rev_tier_gate", "cn": "底部反转", "steps": [1, 3, 5, 10, 20]},
    "hw":  {"mod": "_hw_tier_gate",  "cn": "高胜率", "steps": [1, 2, 3, 5, 8, 10, 20]},
    # ★ 做T 族：面板（_tplus_lab_panel.json）已稀疏，不能二次抽稀；family=tplus 让它走
    #   自定义 build —— 真正从全量日K 重建（_tplus_lab.build_panel(step)）再打分分档，
    #   才是项目铁律下的「跨采样频率稳健性」检验（详见 adapt 的 tplus 分支）。
    "tplus": {"mod": "_tplus_tier_gate", "cn": "做T", "steps": [1, 2, 3, 5, 8, 10, 20],
              "family": "tplus"},
    # ★ 增仓池：无现成 build_panel(step)；复用 _accum_tier_gate.build(days=全量) 一次产全行，
    #   再按入场日 step 子集（等价于跨采样频率稳健性检验）。tier 选自 RULES（S/A/B/C + M且I 候选）。
    "accum": {"mod": "_accum_tier_gate", "cn": "增仓", "steps": [1, 2, 3, 5, 8, 10, 20],
              "family": "accum"},
    # ★ 主升精选：复用生产口径（_selected_lab.factors_at + _selected_attrib 打分 + V1 质量闸）。
    #   逐交易日建「入场日」：全市场域算 9 因子等权横截面分位 → 前 5% 为 A 档候选
    #   → V1 质量闸（dist_h20≤-1%）把候选切成「A 档(V1 通过)」与「B_notV1(V1 未过)」两档。
    #   只建一次（_CACHE），7 步扫描按入场日重采样（与 accum 同构，非二次抽稀）。
    #   legacy 与 realistic(跳空成交) 两种退出口径都算 pnl；第五道闸判 legacy、页面并列 realistic。
    "selected": {"mod": "_selected_lab", "cn": "主升精选", "steps": [1, 2, 3, 5, 8, 10, 20],
                 "family": "selected"},
}


def load_pool(name):
    key = POOLS.get(name)
    if not key:
        raise SystemExit("未知池 %r，可选：%s" % (name, list(POOLS)))
    mod = __import__(key["mod"])
    return key, mod, adapt(mod, name)


def adapt(mod, pool):
    """把各池统一成 (tiers, sel, ctrl_all, ctrl_same[, build]) 接口。"""
    # ★ 做T 族：面板（_tplus_lab_panel.json）已稀疏采样，二次抽稀会自欺；
    #   改用全量日K 按 step 重建（_tplus_lab.build_panel(step)）→ 打分分档 → 两版做T期望。
    if POOLS.get(pool, {}).get("family") == "tplus":
        import _tplus_lab as L
        # ★ 环境门控（2026-10-12）：做T 内核是「反T」——弱市低吸高抛。修复 score_day 方向后
        #   实测 A 档只在弱市有正池化期望（edge 随阈值单调），故新增 AW 档 = A档∩弱市 参与判定。
        _GATE = getattr(mod, "ENV_GATE", -3.0)
        _TIERS = [("A", "A 档（域内前 10%·可重点做T）"),
                  ("B", "B 档（前 10~25%·适合做T）"),
                  ("C", "C 档（其余·仅跟踪）"),
                  ("AW", "A 档 ∩ 弱市（上证20日<%+.0f%%·反T 只在此态成立）" % _GATE)]

        def _build_tplus(st):
            raw = L.build_panel(step=st)
            byd = defaultdict(list)
            for r in raw:
                byd[r["date"]].append(r)
            rows = []
            dates = []
            _ENV = mod.env20_map()          # 只用 ≤ 当日 数据，无未来函数
            for d in sorted(byd):
                rs = mod.score_day(byd[d])
                order = sorted(rs, key=lambda r: (-r["score"], r["code"]))
                n = len(order)
                na = max(1, int(round(n * mod.A_PCT)))
                nb = max(na + 1, int(round(n * mod.B_PCT)))
                ev = _ENV.get(d)
                for i, r in enumerate(order):
                    g = "A" if i < na else ("B" if i < nb else "C")
                    s = L._sim_default(r)
                    sr = L._sim_realistic(r)
                    rows.append({"code": r["code"], "date": d, "grade": g,
                                 "env20": ev,
                                 "pnl": float(s["ret"]), "win": bool(s["ret"] > 0),
                                 "round_ok": bool(s["round_ok"]),
                                 "pnl_cons": float(sr["ret"]),
                                 "round_cons": bool(sr["round_ok"])})
                dates.append(d)
            return (rows, (dates[0] if dates else ""),
                    (dates[-1] if dates else ""), len(dates))

        def _in_aw(r, gate=None):
            g = _GATE if gate is None else gate
            return (r.get("grade") == "A") and (r.get("env20") is not None) \
                and (r["env20"] < g)

        tiers = _TIERS

        def _sel(k):
            if k == "AW":
                return (lambda r, kk=_GATE: _in_aw(r, kk))
            return (lambda r, kk=k: r["grade"] == kk)

        sel = _sel
        ctrl_all = lambda r: True
        # 等量对照：同日非本档（与 _tplus_tier_gate.main 的 ctl 一致；
        # ★ 不放宽成母集，否则 BASE/ALL 式恒正会造假 alpha）
        # AW 档对照 = 同日「非（A∩弱市）」，即含 A∩强/中 + 全部非A，口径一致。
        def _ctrl_same(r, k=None):
            if k == "AW":
                return not _in_aw(r)
            return r["grade"] != k

        ctrl_same = _ctrl_same
        return tiers, sel, ctrl_all, ctrl_same, _build_tplus

    if POOLS.get(pool, {}).get("family") == "accum":
        # 复用 _accum_tier_gate.build 一次产全量行（全 matured 入场日），再按 step 子集。
        # build() 内部对每日 signal_frame + simulate(default/gap)，与主线 _accum_tier_gate 一致，
        # 故本分支只是「频率重采样」封装，不引入新逻辑（避免未来函数 / 口径分叉）。
        RULE_MAP = {nm: fn for nm, fn in mod.RULES}
        # 只扫候选档：排除「全候选域」对照基准——其 ctrl_same=not(all) 会让 edge_stats 崩溃。
        SCAN_TIERS = [nm for nm, _ in mod.RULES if nm != "全候选域（无筛选对照）"]
        _CACHE = {}

        def _load_all():
            if "_rows" not in _CACHE:
                rows, lastN, _cover = mod.build(days=10 ** 9)
                norm = []
                for r in rows:
                    norm.append({
                        "code": r["code"], "date": r["date"],
                        "pnl": float(r["ret"]), "win": bool(r["win"]),
                        "pnl_cons": float(r.get("ret_gap", r["ret"])),
                        "win_cons": bool(r.get("win_gap", r["win"])),
                        "tier": r["tier"], "n": r["n"],
                        "I": r["I"], "M": r["M"], "m5r": r["m5r"],
                    })
                _CACHE["_rows"] = norm
                _CACHE["_days"] = list(lastN)
            return _CACHE["_rows"], _CACHE["_days"]

        def _build_accum(st):
            rows, days = _load_all()
            sub_idx = days[::st] if st and st > 0 else days
            chosen = set(sub_idx)
            sub = [r for r in rows if r["date"] in chosen]
            d0 = sub_idx[0] if sub_idx else ""
            d1 = sub_idx[-1] if sub_idx else ""
            return (sub, d0, d1, len(sub_idx))

        tiers = [(nm, nm) for nm in SCAN_TIERS]
        sel = lambda k: (lambda r, kk=k: RULE_MAP[kk](r))
        ctrl_all = lambda r: True
        # 等量对照：同日非本档（与主线「vs 同日全候选域」一致；不放宽成母集以免造假 alpha）
        ctrl_same = lambda r, k=None: not RULE_MAP[k](r)
        return tiers, sel, ctrl_all, ctrl_same, _build_accum

    if POOLS.get(pool, {}).get("family") == "selected":
        # ★ 主升精选：复用生产口径，逐交易日建入场日，V1 质量闸把候选切 A / B_notV1 两档。
        #   只建一次（PRE/cal 在 adapt 调用时算一次；rows 在 _CACHE 缓存，7 步重采样复用）。
        import collections as _coll
        import _txk as _TXK
        import _selected_lab as SL
        import _selected_attrib as AT
        from _exit_sim import sim_exit as _sim
        MINI = SL.MINI; FMAX = SL.FMAX; AMT_MIN = SL.AMT_MIN; PRICE_MIN = SL.PRICE_MIN
        PCT = 0.05
        # —— 一次性预计算（adapt 调用一次，不在 _load_all 内重算）——
        print("[selected·freq] 加载日K缓存并预计算逐票序列…")
        _cache = _TXK.load()
        try:
            _NM = json.load(open(os.path.join(_HERE, "_stock_names.json"), encoding="utf-8"))
        except Exception:
            _NM = {}
        _codes = [c for c in _cache
                  if (c.startswith("sh6") or c.startswith("sz0") or c.startswith("sz3"))
                  and len(_cache[c]) >= MINI + FMAX + 5]
        _PRE = {}
        for c in _codes:
            bars = _cache[c]
            C = [b["last"] for b in bars]; H = [b["high"] for b in bars]
            L = [b["low"] for b in bars]; O = [b["open"] for b in bars]
            V = [b["volume"] for b in bars]
            psC = SL._prefix(C)
            bidx = {b["date"]: i for i, b in enumerate(bars)}
            dates = [b["date"] for b in bars]
            _PRE[c] = (C, H, L, O, V, psC, bidx, dates)
        del _cache
        _cov = _coll.Counter()
        for c in _codes:
            for dt in _PRE[c][7]:
                _cov[dt] += 1
        _cut = (max(_cov.values()) * 0.25) if _cov else 0
        _cal = sorted(d for d, n in _cov.items() if n >= _cut)
        print("[selected·freq] 候选票 %d 只，交易日历 %d 根（覆盖度门槛 %d）"
              % (len(_codes), len(_cal), _cut))
        _CACHE = {}

        def _load_all():
            if "_rows" in _CACHE:
                return _CACHE["_rows"], _CACHE["_days"]
            rows = []
            for T in _cal:
                universe = []
                for c in _codes:
                    C, H, L, O, V, psC, bidx, dates = _PRE[c]
                    i = bidx.get(T)
                    if i is None or i < MINI or i + FMAX >= len(C):
                        continue
                    close = C[i]
                    if not close or close < PRICE_MIN:
                        continue
                    vu = 1.0 if c.startswith("sh688") else 100.0
                    amt20 = sum(V[k] * vu * C[k] for k in range(i - 19, i + 1)) / 20 / 1e8
                    if amt20 < AMT_MIN / 1e8:
                        continue
                    f = SL.factors_at(C, H, L, O, V, psC, i, c)
                    if not f:
                        continue
                    fl = L[i + 1:i + 1 + FMAX]; fh = H[i + 1:i + 1 + FMAX]; fc = C[i + FMAX]
                    if len(fl) < FMAX or not fc:
                        continue
                    fO = O[i + 1:i + 1 + FMAX]
                    universe.append({"code": c, "date": T, "f": f, "_close": close,
                                     "fl": fl, "fh": fh, "fc": fc, "fO": fO})
                if len(universe) < 12:
                    continue
                AT.score_by_date(universe)
                top = AT.top_of_day(universe, PCT)
                topkey = {(r["code"], T) for r in top}
                # ★ 面板必须装**当日域全部票**（不只前 5%）：
                #   否则对照只是「前5%内部的另一半」，两档 edge 必然互为镜像，
                #   测的是「前5%里谁更好」而非相对市场的 alpha（口径缺陷）。
                #   V1 回退后生产口径 = 前5%整体（TOP5），对照必须是域内其余（REST）。
                for r in universe:
                    code = r["code"]
                    _sim_now = (code, T) in topkey
                    pnl, _, _ = _sim(r["fc"], r["fh"], r["fl"], r["_close"], cons=False)
                    pnl_r, _, _ = _sim(r["fc"], r["fh"], r["fl"], r["_close"],
                                       cons=True, fO=r["fO"])
                    if _sim_now:
                        v1 = r["f"]["dist_h20"] <= -0.01
                        tier = "A" if v1 else "B_notV1"
                    else:
                        tier = "REST"
                    rows.append({"code": code, "date": T, "tier": tier,
                                 "pnl": pnl, "win": (pnl > 0),
                                 "pnl_cons": pnl_r, "win_cons": (pnl_r > 0)})
            _CACHE["_rows"] = rows
            _CACHE["_days"] = sorted(set(r["date"] for r in rows))
            nA = sum(1 for r in rows if r["tier"] == "A")
            nB = sum(1 for r in rows if r["tier"] == "B_notV1")
            nR = len(rows) - nA - nB
            print("[selected·freq] 入场日 %d 个｜ 前5%% %d 行（其中 V1通过 %d / 未过 %d）"
                  "｜ 域内其余 REST %d 行 → 对照口径＝相对市场" % (
                      len(_CACHE["_days"]), nA + nB, nA, nB, nR))
            return _CACHE["_rows"], _CACHE["_days"]

        def _build_selected(st):
            rows, days = _load_all()
            sub_idx = days[::st] if st and st > 0 else days
            chosen = set(sub_idx)
            sub = [r for r in rows if r["date"] in chosen]
            d0 = sub_idx[0] if sub_idx else ""
            d1 = sub_idx[-1] if sub_idx else ""
            return (sub, d0, d1, len(sub_idx))

        # 每档对应的 tier 成员集合；对照 = 域内**不属于本档**的行。
        # ★ REST 是「拿来比」的尺子，本身不给出票判定（见 SKIP_TIERS）。
        _TIER_MEMBERS = {"TOP5": ("A", "B_notV1"),
                         "A": ("A",),
                         "B_notV1": ("B_notV1",),
                         "REST": ("REST",)}
        tiers = [("TOP5", "前 5% 整体（★V1 回退后的现行生产口径）"),
                 ("A", "前 5% 中·V1 质量闸通过（距20日高≥1%，不追最尖）"),
                 ("B_notV1", "前 5% 中·V1 未过（最尖处延伸末端）"),
                 ("REST", "当日域内非前 5%（对照母集·不参与判定）")]
        sel = lambda k: (lambda r, kk=k: (r["tier"] in _TIER_MEMBERS[kk]))
        ctrl_all = lambda r: True
        ctrl_same = lambda r, k=None: (r["tier"] not in _TIER_MEMBERS.get(k, ()))
        return tiers, sel, ctrl_all, ctrl_same, _build_selected, True

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
    """逐频率重建面板 → 各档 edge/R3（母集 + 等量双对照）。

    api 第 6 项（可选，bool）：是否并列计算 realistic(跳空成交) 口径
    （主升精选池用，行须带 pnl_cons/win_cons）。第五道闸判 legacy，realistic 仅并列展示。
    """
    tiers, sel, ctrl_all, ctrl_same = api[0], api[1], api[2], api[3]
    build = api[4] if len(api) > 4 else (lambda st: mod.build_panel(st))
    realistic = (len(api) > 5 and api[5]) or False
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
            rec = dict(
                step=st, tier=key, label=label,
                n_rows=m.get("n_rows"), n_days=m.get("n_days"),
                edge=m.get("edge"), r3=m.get("r3"),
                edge_excl=e.get("edge"), r3_excl=e.get("r3"),
                loo_min=m.get("loo_min"), loo_max=m.get("loo_max"),
                note=m.get("note") or e.get("note") or "")
            if realistic:
                # realistic 口径：用 pnl_cons/win_cons 重算同一组对照
                rows_c = [dict(r, pnl=r.get("pnl_cons", r["pnl"]),
                               win=r.get("win_cons", r["win"])) for r in rows]
                mc = GC.edge_stats(rows_c, sel(key), ctrl_all,
                                   boot=BOOT, seed=SEED, name=key)
                ec = GC.edge_stats(rows_c, sel(key), lambda r, kk=key: ctrl_same(r, kk),
                                   boot=BOOT, seed=SEED, name=key)
                rec["edge_cons"] = mc.get("edge"); rec["r3_cons"] = mc.get("r3")
                rec["edge_excl_cons"] = ec.get("edge"); rec["r3_excl_cons"] = ec.get("r3")
            rows_all.append(rec)
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