# -*- coding: utf-8 -*-
"""分档出票核验 · 公共统计层（_gate_common.py）

背景
----
增仓精选 / 底部反转 / 高胜率池 三个池子都要回答同一个问题：

    「页面打的那个数字，是不是你真正会买的那批票？还有没有超额？稳不稳？」

三个池子的面板构建各不相同（那天价量因子、这个 MACD 基底打分），
但**统计层完全一样**：逐日平衡 edge → 按日 block bootstrap → 留一法 → 前/后半 → 跨步长。
这一层抽出来共用，避免每个池子各写一版、各错一处。

统一口径（与 `_selected_lab` / `_rbot` 一致）
--------------------------------------------
  * **逐日平衡 edge** = 该档逐日均值 − 同日对照域逐日均值（不是把大池子摊平后比绝对值）。
  * **按日 block bootstrap**（L=1，整日重抽）：前向窗口重叠会让朴素正态低估误差，
    必须按日整块重抽才敢用 R3 这个数。
  * **R3** = bootstrap 中 edge>0 的比例，要求 ≥95% 才叫「可出票」。
  * **留一法**看稳健下限（逐日剔除后是否仍同号），**前/后半**看是否锁在某个市场状态里，
    **跨步长**看结论是不是只为某一个采样频率成立。

出票许可（机器化，fail-safe）
----------------------------
`emit_license()` 要求：主步长 `edge>0` 且 `R3≥95%`，
且**跨步长（step3 派生口径）必须同号且 step3 R3≥95%**。
读不到证据 JSON → 一律不出票（「宁可不选」，不许放宽阈值凑数）。

被谁用：`_rev_tier_gate.py`、`_hw_tier_gate.py`、`_3yl_tier_gate.py`。
"""
from __future__ import annotations
import os, sys, json, random, collections

QUANT = os.path.dirname(os.path.abspath(__file__))
BOOT = 800


# ---------------- 基础 ----------------
def daily_mean(rs):
    n = len(rs) or 1
    return sum(x["pnl"] for x in rs) / n, sum(1 for x in rs if x["win"]) / n * 100.0


def series(rows, sel_fn, ctrl_fn):
    """逐日聚合：sel_fn/ctrl_fn 都是 (row)->bool。

    返回 ({date:(mean_pnl, win_rate, n)}, {date:(mean_pnl, win_rate)})
    对照逐日与策略逐日**必须同日**：只在「对照与策略同时存在」的日子上算 edge，
    否则 edge 会掺进两边的日期分布差（比如拿全集当策略、子集当对照时，
    把只有对照没策略的日期也算进均值）。
    """
    byd, ctl = {}, {}
    for r in rows:
        if ctrl_fn(r):
            ctl.setdefault(r["date"], []).append(r)
        if sel_fn(r):
            byd.setdefault(r["date"], []).append(r)
    common = sorted(set(ctl) & set(byd))
    out, ctrl = {}, {}
    for d in common:
        mp, mw = daily_mean(ctl[d])
        ctrl[d] = (mp, mw)
        sp, sw, n = daily_mean(byd[d]) + (len(byd[d]),)
        out[d] = (sp, sw, n)
    return out, ctrl


def _boot_pos(evs, boot=BOOT, seed=20261004):
    """按日整块重抽，返回 edge>0 的比例（%）—— 即 R3。"""
    rnd = random.Random(seed)
    pos = 0
    L = len(evs)
    if L == 0:
        return 0.0
    for _ in range(boot):
        s = 0.0
        for _j in range(L):
            s += evs[rnd.randrange(L)]
        if s / L > 0:
            pos += 1
    return pos / boot * 100.0


def edge_stats(rows, sel_fn, ctrl_fn, boot=BOOT, seed=20261004, name=None):
    """返回该档统计字典（结构与 _rev_tier_gate 产物兼容）。"""
    ser, ctl = series(rows, sel_fn, ctrl_fn)
    ds = sorted(ser)
    if len(ds) < 3:
        return {"tier": name, "n_days": len(ds), "note": "样本不足（<3 个信号日）"}
    eg = [ser[d][0] - ctl[d][0] for d in ds]
    wr = [ser[d][1] for d in ds]
    obs = sum(eg) / len(ds)
    own_pnl = sum(ser[d][0] for d in ds) / len(ds)
    own_win = sum(wr) / len(wr)
    ctrl_days = [d for d in ds if d in ctl]
    ctrl_pnl = sum(ctl[d][0] for d in ctrl_days) / max(1, len(ctrl_days))
    ctrl_win = sum(ctl[d][1] for d in ctrl_days) / max(1, len(ctrl_days))
    r3 = _boot_pos(eg, boot=boot, seed=seed)
    loo = []
    for k in range(len(eg)):
        rest = [eg[j] for j in range(len(eg)) if j != k]
        loo.append(sum(rest) / len(rest))
    days = [{"date": d, "edge": round(e, 4), "win": round(w, 2), "n": ser[d][2]}
            for d, e, w in zip(ds, eg, wr)]
    own_rows = [r for r in rows if r["date"] in ser]
    return {
        "tier": name,
        "n_days": len(ds),
        "n_rows": sum(ser[d][2] for d in ds),
        "edge": round(obs, 4),
        "pnl": round(own_pnl, 4),
        "win": round(own_win, 2),
        "ctrl_pnl": round(ctrl_pnl, 4),
        "ctrl_win": round(ctrl_win, 2),
        "win_pool": round(sum(1 for r in own_rows if r["win"]) / max(1, len(own_rows)) * 100.0, 2),
        "r3": round(r3, 1),
        "loo_min": round(min(loo), 4),
        "loo_max": round(max(loo), 4),
        "days": days,
    }


def halves(days):
    """前/后半 edge 同向性（单段行情容易把结论锁在一个市场状态里，必须查）。"""
    if len(days) < 6:
        return []
    h = len(days) // 2
    out = []
    for tag, seg in (("前半", days[:h]), ("后半", days[h:])):
        e = [x["edge"] for x in seg]
        if not e:
            continue
        out.append({"half": tag, "n_days": len(seg),
                    "edge": round(sum(e) / len(e), 4),
                    "edge_pos_days": sum(1 for x in e if x > 0),
                    "win": round(sum(x["win"] for x in seg) / len(seg), 2)})
    return out


# ---------------- 出票许可 ----------------
def emit_license(main_json, sens_json, keys, tier_cn, data_gate=None, pool_key=None):
    """读两份证据 JSON（主步长 + step3 派生），机器判定各档能否出票。

    规则（与 `_rev_tier_gate` 结论一致，三池共用）：
      主步长 edge>0 且 R3≥95% 且 step3 同号且 step3 R3≥95% → 可出票
      读不到证据 → 该档 fail-safe 不出票

    ★ `data_gate`（可选，dict 含 ok/why）：**数据有效性闸**，与统计无关。
      底池本身是旧数据冒充当日时，edge 再漂亮也不能出票 —— 那是拿过期信息下单，
      统计核验根本无从谈起。反转/三连阴不需要这道闸（不传即可），高胜率传。

    ★ `pool_key`（可选，**tuple**(档位, 字段名)）：**池化闸**。做T这类「不成交也是一种结果」
      的场景必须传 —— 逐日平衡 edge>0 只说明「每天都重选更优」，**不等于实际成交能赚**。
      该档该字段 ≤0 → 该档一律不出票。例：`("A", "pooled_hitbuy")`。
    """
    def _load(p):
        try:
            j = json.load(open(p, encoding="utf-8"))
        except Exception:
            return None
        return j

    j5 = _load(main_json)
    jn = _load(sens_json)
    per5 = {t.get("tier"): t for t in (j5 or {}).get("tiers", [])}
    pern = {t.get("tier"): t for t in (jn or {}).get("tiers", [])}
    if not per5:
        return {"ok": False,
                "why": "未读到主证据（%s）→ fail-safe 不出票" % os.path.basename(main_json),
                "detail": {k: {"ok": False, "why": "无证据", "edge": None, "r3": None,
                               "edge_step3": None}
                           for k in keys}}
    out = {}
    for k in keys:
        t = per5.get(k) or {}
        e5, r5 = t.get("edge"), t.get("r3")
        n3 = pern.get(k) or {}
        e3, r3 = n3.get("edge"), n3.get("r3")
        ok = True
        why = []
        if e5 is None:
            ok = False
            why.append("主证据缺 edge")
        else:
            if e5 <= 0:
                ok = False
                why.append("主步长 edge %+.3fpp ≤ 0" % e5)
            if r5 is None or r5 < 95.0:
                ok = False
                why.append("R3 %s < 95%% 门槛" % ("—" if r5 is None else "%.1f%%" % r5))
        if e3 is not None:
            if e3 * e5 < 0:
                ok = False
                why.append("步长敏感性翻转（step3 %+.3fpp）" % e3)
            elif e3 <= 0:
                ok = False
                why.append("step3 edge %+.3fpp ≤ 0" % e3)
            elif r3 is not None and r3 < 95.0:
                ok = False
                why.append("step3 R3 %.1f%% < 95%%" % r3)
        out[k] = {"ok": bool(ok), "why": "；".join(why) or "达标",
                  "edge": e5, "r3": r5, "edge_step3": e3}
    # ★ 数据有效性闸：底池不是当日数据 → 统计结论一律不作数，压住全部档位
    if data_gate is not None and not data_gate.get("ok", True):
        dw = data_gate.get("why") or "数据有效性未通过"
        for k in out:
            out[k]["ok"] = False
            out[k]["why"] = (out[k]["why"] + "；" if out[k]["why"] != "达标" else "") + \
                           "【数据闸】" + dw
    # ★ 池化闸：逐日平衡 edge 为正、但**池化口径为负**时不得出票。
    #   做T这类「不成交也是结果」的场景会出现：没成交的空值把池化均值拉平，
    #   逐日平衡看不出来 —— 实测做T A 档逐日 +0.54pp 但触买后池化 −0.28%。
    #   edge>0 只说明「每天都重选更优」，不代表「实际做一笔能赚」。
    #   pool_key = (档位, 字段名)：字段值取自主证据该档的 <字段>。
    pooled_gate = None
    if pool_key:
        pk_k, pk_f = (pool_key if isinstance(pool_key, (tuple, list)) else (None, pool_key))
        if pk_k is not None and pk_k in out:
            pv = (per5.get(pk_k) or {}).get(pk_f)
            if pv is not None and pv <= 0:
                pooled_gate = {"tier": pk_k, "field": pk_f, "value": pv}
                out[pk_k]["ok"] = False
                out[pk_k]["why"] = (out[pk_k]["why"] + "；" if out[pk_k]["why"] != "达标" else "") + \
                    ("【池化闸】%s 档「%s」%+.4f%% ≤ 0 —— 逐日平衡为正只是"
                     "「每天都重选更优」，不等于实际成交能赚" % (pk_k, pk_f, pv))
    # ★ 顶层键名一律语义正向：`any_ok` = 至少有一档可出票。
    #   历史坑：曾用 `"ok": not any(...)`（名字叫 ok、意思却是「全部不出票」），
    #   与 detail 内同名字段反义，`_rev_gate_page` 直接拿它显示 → 恒显示「见表」。
    return {"any_ok": any(v["ok"] for v in out.values()),
            "all_blocked": not any(v["ok"] for v in out.values()),
            "why": "", "detail": out, "tier_cn": tier_cn,
            "data_gate": data_gate, "pooled_gate": pooled_gate}


# ---------------- 多窗口出票许可（增仓这类「同一批样本、多个持有窗口」的池专用） ----------------
# ---------------- 通用分档统计（2026-10-08 从 _accum_tier_gate 抽上来）----------------
def block_boot(pairs, boot=BOOT, seed=20261004):
    """pairs=[(date, value)] → (点估计, lo, hi, 重抽样中>0 的比例)。按日整块重抽。

    ★ 原本是 `_accum_tier_gate` 的私货，但逻辑与本模块「按日 block bootstrap」
      是同一段 —— 抽到这里后两处共用一份，避免改一处漏一处。
      数值实现逐字符照搬，重构前后 `_accum_tier_gate.json` 指纹必须一致。
    """
    if not pairs:
        return (0.0, 0.0, 0.0, 0.0)
    uniq = sorted({d for d, _ in pairs})
    mat = collections.defaultdict(list)
    for d, v in pairs:
        mat[d].append(v)
    rnd = random.Random(seed)
    ms, pos = [], 0
    for _ in range(boot):
        pick = [uniq[rnd.randrange(len(uniq))] for _ in range(len(uniq))]
        flat = [x for d in pick for x in mat[d]]
        if not flat:
            continue
        m = sum(flat) / len(flat)
        ms.append(m)
        if m > 0:
            pos += 1
    ss = sorted(ms)
    n = len(ss)
    lo = ss[int(n * 0.05)] if n else 0.0
    hi = ss[min(n - 1, int(n * 0.95))] if n else 0.0
    return (sum(v for _, v in pairs) / len(pairs), lo, hi, (pos / len(ms)) if ms else 0.0)


def tier_analyse(rows, dates, rules, boot=BOOT, seed=20261004):
    """**通用**逐日平衡分档统计 —— `_accum_tier_gate.analyse` 的原实现，参数化 rules。

    `rules = [(name, fn)]`，`fn(row) -> bool`。
    返回 `( {name: stat}, ctrl )`，stat 结构与 `_accum_tier_gate` 产物**逐键一致**
    （n/wr/ret/days/edge/eci/er3/er3_min/er3_max/abs/aci/ar3/loo/wf/wf_n），
    这样 `tier_license_windows` 认得它。

    为什么要抽这一刀（2026-10-08）：龙道诀出票闸要复用同一套统计，
    但原 `analyse` 内部写死了增仓自己的 RULES（依赖 `r["tier"]`），
    别的池子一调就 `KeyError` —— 是「私货」不是「公共层」。
    """
    byd = collections.defaultdict(list)
    for r in rows:
        byd[r["date"]].append(r)
    ctrl = {d: sum(x["ret"] for x in byd[d]) / len(byd[d]) for d in byd}

    out = {}
    for name, fn in rules:
        hits = [r for r in rows if fn(r)]
        if not hits:
            out[name] = None
            continue
        pd_edge, pd_abs = [], []
        for d in dates:
            if d not in byd:
                continue
            sub = [r["ret"] for r in byd[d] if fn(r)]
            if not sub:
                continue
            m = sum(sub) / len(sub)
            pd_abs.append((d, m))
            pd_edge.append((d, m - ctrl[d]))
        n = len(hits)
        wr = 100.0 * sum(1 for r in hits if r["win"]) / n
        pooled_ret = sum(r["ret"] for r in hits) / n
        e0, elo, ehi, er3 = block_boot(pd_edge, boot=boot, seed=seed)
        a0, alo, ahi, ar3 = block_boot(pd_abs, boot=boot, seed=seed)
        # 多种子看 R3 的蒙特卡洛抖动；判定一律取最保守（最小）的那个
        r3s = [block_boot(pd_edge, boot=boot, seed=seed + i)[3] for i in range(3)]
        lv = []
        for i in range(len(pd_edge)):
            sub = pd_edge[:i] + pd_edge[i + 1:]
            if sub:
                lv.append(sum(v for _, v in sub) / len(sub))
        cut_i = len(pd_edge) // 2
        first = [v for _, v in pd_edge[:cut_i]]
        second = [v for _, v in pd_edge[cut_i:]]
        out[name] = {
            "n": n, "wr": wr, "ret": pooled_ret, "days": len(pd_edge),
            "edge": e0, "eci": (elo, ehi), "er3": er3,
            "er3_min": min(r3s), "er3_max": max(r3s),
            "abs": a0, "aci": (alo, ahi), "ar3": ar3,
            "loo": (min(lv), max(lv)) if lv else (0.0, 0.0),
            "wf": ((sum(first) / len(first)) if first else 0.0,
                   (sum(second) / len(second)) if second else 0.0),
            "wf_n": (len(first), len(second)),
        }
    return out, ctrl


def tier_license_windows(per, name, prod_window=None, keys=("stat",),
                         min_r3=95.0, require_abs=True, require_loo=True,
                         require_halves=True):
    """跨窗口统一判据 —— 单一真源，`_accum_tier_gate` 的 allow 与渲染判定都调它。

    为什么不能只看一个窗口
    ----------------------
    同一档在不同持有窗口上的 bootstrap 通过率会**单调变好**（样本越长越平滑），
    若按「最好看的那个窗口」判定，等于在窗口维度上挑优 —— 与统一口径
    「跨步长必须同号且各自达标」直接冲突。实测增仓 B 档：
        er3_min  窗口20 = 0.9260 ｜ 窗口40 = 0.9975 ｜ 窗口60 = 0.9995
    按 max(WINDOWS)=60 判定会放行，而生产滚动窗口是 20 —— 不达标。

    判据（全过才算成立）
    --------------------
      * **生产窗口** `prod_window`（默认取最小窗口）：`edge > 0`
      * **所有窗口**：`er3_min ≥ min_r3`（跨窗口一致，取最保守）
      * `require_abs`：所有窗口 `ar3 ≥ min_r3` —— 绝对收益也要稳，
        否则会出现「超额为正但本身亏钱」的档（实测增仓 A 候选 ar3=0.65）
      * `require_loo`：生产窗口 `loo[0] > 0`（留一法全正）
      * `require_halves`：生产窗口 `wf` 两段同为正（不锁在单一市场状态里）

    返回 (ok:bool, why:str, detail:dict)。
    """
    def _stat(w):
        node = per.get(w)
        if node is None:
            return None
        for k in keys:
            if isinstance(node, dict) and isinstance(node.get(k), dict):
                node = node[k]
            else:
                return None
        return (node or {}).get(name)

    wins = sorted(per.keys(), key=lambda x: int(x))
    if not wins:
        return False, "无窗口样本", {}
    pw = str(prod_window if prod_window is not None else wins[0])
    if pw not in per:
        pw = wins[0]
    why = []
    detail = {"prod_window": pw, "windows": wins}
    # ① 生产窗口方向
    sp = _stat(pw)
    if not sp:
        return False, "生产窗口（%s 日）无样本" % pw, detail
    if not (sp.get("edge", 0) > 0):
        why.append("生产窗口 %s 日 edge %+.3fpp ≤ 0" % (pw, sp.get("edge", 0)))
    # ② 所有窗口的 bootstrap 通过率
    r3s = {}
    for w in wins:
        s = _stat(w)
        if not s:
            why.append("窗口 %s 日无样本" % w)
            continue
        r3s[w] = round(s.get("er3_min", 0.0), 4)
        if s.get("er3_min", 0.0) < min_r3 / 100.0:
            why.append("窗口 %s 日 R3 %.1f%% < %.0f%%" % (w, s["er3_min"] * 100, min_r3))
    detail["er3_min_by_window"] = r3s
    # ③ 绝对收益也要稳
    if require_abs:
        a3s = {}
        for w in wins:
            s = _stat(w)
            if not s:
                continue
            a3s[w] = round(s.get("ar3", 0.0), 4)
            if s.get("ar3", 0.0) < min_r3 / 100.0:
                why.append("窗口 %s 日绝对收益 R3 %.1f%% < %.0f%%" % (w, s["ar3"] * 100, min_r3))
        detail["ar3_by_window"] = a3s
    # ④ 留一法
    if require_loo:
        lo = (sp.get("loo") or [0.0, 0.0])[0]
        detail["loo_min"] = lo
        if not (lo > 0):
            why.append("留一法下限 %+.3fpp ≤ 0（剔除任一日就翻负）" % lo)
    # ⑤ 前/后半
    if require_halves:
        wf = sp.get("wf") or (0.0, 0.0)
        detail["wf"] = list(wf)
        if not (wf[0] > 0 and wf[1] > 0):
            why.append("前/后半 [%+.3f, %+.3f]pp 未同为正" % (wf[0], wf[1]))
    ok = not why
    return ok, ("达标（生产窗口 %s 日；跨 %s 窗口一致）" % (pw, "/".join(wins)) if ok else "；".join(why)), detail
