# -*- coding: utf-8 -*-
"""底部反转池 v6 · 分档出票合法性核验（_rev_tier_gate.py）

为什么要有这一页
----------------
`web/reversal` 页面每日实算的「走前验证」表长这样（2026-09-30 实测）：

    ① 深跌域全体（v5 旧口径）        n=13801  胜率 59.9%  均值 −0.68%
    ② ① + 阶段底部区                n=4046   胜率 62.7%  均值 −0.24%
    ③ ① + 启动证据≥2（不看位置）     n=5958   胜率 61.4%  均值 −0.30%
    ④ 本页实际采用（位置+证据）      n=2159   胜率 65.0%  均值 +0.12%

三个问题（都是「好看但不成立」的形状）：
  1. **口径错位**：④ 是 ① 的**子集**（先过旧硬门槛，再叠闸门）。子集 vs 母集比绝对胜率，
     子集天然会被「 Survivorship by filter」抬高——这不是 edge。
  2. **不满足 R1 等量对照**：13801 : 2159 = 6.4:1，门禁要求对照 n 与策略 n 比值 ≥0.5。
  3. **无显著性检验**：只有点估计，没有 bootstrap 置信区间、没有留一法、没有随机分位。
     65.0% 是不是噪声？本页不回答这个点估计，只回答它**稳健不稳健**。

而且更致命的一处：**页面 ④ 的样本 ≠ 真正出票的样本**。
生产实际出票 = `hard` ∩ `bot_ok`（阶段底部+启动证据）∩ `qs` 属域内前 10%（A 档），
2026-09-30 只出了 52 只；④ 有 2159 条。也就是说——**页面给的那张表，测的不是你买的票**。

本脚本做什么
------------
按 `_accum_tier_gate.py` 完全同口径重建面板：
  * 数据只用 `quant/_txk_cache.json`（全市场真实日K，离线），**逐日逐票复刻生产逻辑**：
     域（正股 / 非 ST·退 / 20 日均额≥3000 万 / 现价≥2）→ 旧硬门槛 hard
     → `_rbot.detect`（阶段底部）→ `_rbot.fail_cat` + `lift_signals≥2`（bot_ok）
     → 9 因子横截面分位 qs → A 档（域内前 10%，同 A_PCT）
  * 收益统一用**移动止盈**（−12% 硬止损 / +6% 激活 / 回撤 3% / 满 20 日强平），
    与 `_selected_lab`、`_rbot._sim_trail` 同口径。
  * **逐日平衡 edge** = 该档逐日均值 − 同日对照域逐日均值（不是把大池子摊平后比绝对值）。
  * 显著性：**按日 block bootstrap**（BOOT=800，L=1，按日整块重抽，避开前向窗口重叠导致的
    朴素正态低估误差）+ **留一法**（逐日剔除后重算）。

出票许可
--------
`edge>0` 且 R3（bootstrap 中 edge>0 的比例 ≥95%）= 可出票；否则空仓（宁可不选）。
`build_rev.py` / `rev_pool.py` 只读本脚本产出的 JSON，**读不到一律不出票**（fail-safe）。

用法：python quant/_rev_tier_gate.py [--limit N] [--step N]
"""
from __future__ import annotations
import os, sys, json, math, random, statistics, argparse
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _gate_common as GC
import _selected_lab as S
import _rbot as RB
import _exit_sim as EXIT          # 成交假设审计（四口径单笔收益）

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QUANT = os.path.join(ROOT, "quant")
CACHE = os.path.join(QUANT, "_txk_cache.json")
OUT_JSON = os.path.join(QUANT, "_rev_tier_gate.json")
OUT_HTML = os.path.join(ROOT, "web", "reversal", "tier_gate.html")

STEP = 5            # 采样步长（交易日）
MINI = 60           # 最少 K 线
AMT_MIN = 3.0e7     # 20 日均额下限（元）
PRICE_MIN = 2.0     # 最低价
A_PCT, B_PCT = 0.10, 0.25     # 复刻 rev_pool.A_PCT / B_PCT
LIFT_MIN = 2                  # 复刻 rev_pool.LIFT_MIN
BOOT = 800
SEED = 20261004


# ---------------- 工具（与 _selected_lab 同口径的复刻） ----------------
def _prefix(a):
    ps = [0.0] * (len(a) + 1)
    for i, x in enumerate(a):
        ps[i + 1] = ps[i] + (x or 0)
    return ps


def _rollma(ps, i, n):
    if i - n + 1 < 0:
        return None
    return (ps[i + 1] - ps[i - n + 1]) / n


def _bad_name(nm):
    return ("ST" in (nm or "")) or ("退" in (nm or ""))


def hard_flag(C, H, i):
    """复刻 rev_pool.evaluate 的 hard：dist52 ≤ −18% 且 close ≥ MA60×0.75。

    ★ h52 必须取**全段最高**（生产 `rev_pool.evaluate` 用 `max(highs)` 遍历 k[:i+1] 全部历史），
      不是近 N 日窗口 —— 取 60 日窗口会让 deep-drop 域定义**偏松**（掺进"最近 60 天才跌 18%，
      但离 250 天前的高点只跌 5%"的票），把闸门的效果稀释掉（实测 gate vs 深跌域从 +5pp 掉到
      +0.2pp）。这一步不忠于生产，整个复核就白做。
    """
    if i < 60:
        return False
    h52 = max(H[:i + 1])
    ma60 = _rollma(_prefix(C), i, 60)
    close = C[i]
    if not h52:
        return False
    if (close - h52) / h52 * 100 > -18:
        return False
    if ma60 and close < ma60 * 0.75:
        return False
    return True


# ---------------- 面板 ----------------
def build_panel(limit=0, step=STEP, verbose=True):
    cache = json.load(open(CACHE, encoding="utf-8"))
    nm_path = os.path.join(QUANT, "_stock_names.json")
    NM = {}
    if os.path.exists(nm_path):
        try:
            NM = json.load(open(nm_path, encoding="utf-8"))
        except Exception:
            NM = {}
    codes = sorted([c for c in cache
                    if (c.startswith("sh6") or c.startswith("sz0") or c.startswith("sz3"))
                    and len(cache[c]) >= MINI + S.MAXFWD + 5])
    if verbose:
        print("[rev] 日K %d 只，入面板候选 %d 只" % (len(cache), len(codes)))
    if limit:
        codes = codes[:limit]

    rows = []
    skipped = defaultdict(int)
    for c in codes:
        if _bad_name(NM.get(c) or ""):
            skipped["bad"] += 1
            continue
        bars = cache[c]
        C = [b["last"] for b in bars]
        H = [b["high"] for b in bars]
        L = [b["low"] for b in bars]
        O = [b["open"] for b in bars]
        V = [b["volume"] for b in bars]
        psC = _prefix(C)
        n = len(bars)
        vu = 1.0 if c.startswith("sh688") else 100.0
        for i in range(MINI, n - S.MAXFWD - 1, step):
            close = C[i]
            if not close:
                continue
            amt20 = sum(V[k] * vu * C[k] for k in range(i - 19, i + 1)) / 20
            if amt20 < AMT_MIN:
                skipped["amt"] += 1
                continue
            if close < PRICE_MIN:
                skipped["price"] += 1
                continue
            ma20 = _rollma(psC, i, 20)
            ma60 = _rollma(psC, i, 60)
            if not (ma20 and ma60):
                continue
            f = S.factors_at(C, H, L, O, V, psC, i, c)
            if f is None:
                continue
            hf = hard_flag(C, H, i)
            bot_ok, lift, why = False, 0, ""
            if hf:
                b = RB.detect(bars[:i + 1])
                if b is None:
                    why = "未识别底部结构"
                else:
                    fcat = RB.fail_cat(b)
                    nl, _ = RB.lift_signals(bars[:i + 1], b)
                    lift = nl
                    if fcat:
                        why = fcat
                    elif nl < LIFT_MIN:
                        why = "启动证据仅%d条" % nl
                    else:
                        bot_ok = True
            fl = L[i + 1:i + 1 + S.MAXFWD]
            fh = H[i + 1:i + 1 + S.MAXFWD]
            fO = O[i + 1:i + 1 + S.MAXFWD]
            fc = C[i + S.MAXFWD] if i + S.MAXFWD < n else None
            if len(fl) < S.MAXFWD or not fc:
                continue
            if any((o is None or o <= 0) for o in fO):
                continue                      # 跳空修正必需，缺则整行剔除（不静默补 0）
            sim = S._sim_trail(fl, fh, fc, close)
            p4 = EXIT.four_pnl(fl, fh, fc, close, fO=fO)
            # 自检：四口径第 0 档必须等于旧口径 pnl（否则说明口径模块被改坏）
            assert abs(p4[0] - sim["pnl"]) < 1e-6, "四口径自检失败 %s %s" % (c, bars[i]["date"])
            rows.append({"code": c, "date": bars[i]["date"], "f": f,
                         "hard": bool(hf), "bot_ok": bot_ok, "lift": lift,
                         "why": why, "pnl": sim["pnl"], "win": bool(sim["win"]),
                         "mae": sim["mae"], "p4": [round(x, 4) for x in p4]})
    if verbose:
        print("[rev] 面板 %d 行（剔 ST/退 %d · 流动性 %d · 低价 %d）"
              % (len(rows), skipped["bad"], skipped["amt"], skipped["price"]))
    return rows


# ---------------- 按日横截面分位 + 档位 ----------------
def assign(rows, verbose=False):
    """按日给 9 因子打横截面分位，再切 A/B/C。

    ★ 口径必须对齐生产 `rev_pool.assign_tiers`：生产的 items 只含 **hard 通过**的票
    （`run()` 里 `r["ok"] and r["hard"]` 才 append），所以横截面分位是**在 hard 集合内**切前 10%，
    不是在全市场域内切。给非 hard 行算分位会让 A 档人数虚高（实测差一个量级）。
    """
    byd = defaultdict(list)
    for r in rows:
        byd[r["date"]].append(r)
    for d, rs in sorted(byd.items()):
        # hard 集合（生产：只有硬门槛通过的才进入打分与分档）
        cand = [r for r in rs if r["hard"]]
        rs = cand
        if len(rs) < 12:
            for r in byd[d]:
                r["qs"], r["tier"], r["qrank"] = None, "C", None
            continue
        rk = {}
        for fac in S.PRIOR:
            vals = sorted([(r["f"].get(fac), r["code"]) for r in rs
                           if r["f"].get(fac) is not None])
            if len(vals) < 6:
                continue
            for pos, (v, c) in enumerate(vals):
                rk.setdefault(c, {})[fac] = pos / (len(vals) - 1)
        scored = []
        for r in rs:
            tot = cnt = 0.0
            for fac in S.PRIOR:
                v = rk.get(r["code"], {}).get(fac)
                if v is None:
                    continue
                tot += (v if S.PRIOR[fac] > 0 else 1 - v)
                cnt += 1
            if cnt >= max(2, len(S.PRIOR) // 2):
                scored.append((tot / cnt, r))
        scored.sort(key=lambda x: (-x[0], x[1]["code"]))
        n = len(scored)
        ia = int(round(n * A_PCT))
        ib = int(round(n * B_PCT))
        for i, (sc, r) in enumerate(scored):
            r["qs"] = round(sc * 100, 1)
            r["tier"] = "A" if i < ia else ("B" if i < ib else "C")
            r["qrank"] = i + 1
        for r in rs:
            if "qs" not in r:
                r["qs"] = None
                r["tier"] = "C"
                r["qrank"] = None
    if verbose:
        print("[rev] 分档完成，日期 %d 个" % len(byd))
    return rows


# ---------------- 分档与统计 ----------------
TIERS = [
    ("A",  "现行出票：旧硬门槛 + 阶段底部+证据≥2 + 组合分前 10%"),
    ("B",  "旧硬门槛 + 阶段底部+证据≥2 + 组合分 10~25%"),
    ("BOT", "旧硬门槛 + 阶段底部+证据≥2（不看组合分）"),
    ("HARD", "仅旧硬门槛（v5 旧口径：跌得多）"),
    ("ALL", "全市场域（随便买 · 绝对对照）"),
]


def pick(r, key):
    if key == "ALL":
        return True
    if key == "HARD":
        return r["hard"]
    if key == "BOT":
        return r["hard"] and r["bot_ok"]
    if key == "A":
        return r["hard"] and r["bot_ok"] and r.get("tier") == "A"
    if key == "B":
        return r["hard"] and r["bot_ok"] and r.get("tier") == "B"
    return False


def _sel(key):
    """档位 → (row)->bool。统计层已抽到 `_gate_common`（三池共用），这里只留选票口径。"""
    def f(r):
        return pick(r, key)
    return f


# ---------------- 成交假设审计（退出回测的口径依赖） ----------------
EXIT_TIERS = ["A", "BOT", "HARD", "ALL"]


def exit_assumption(rows):
    """对现行出票档与相邻档，给出四种成交假设下的胜率/均值。

    目的：把「**同一批票**、只改成交假设」的差异摆出来 —— 差异即旧口径的虚高幅度。
    第 0 档 = 旧口径（= 页面现行数字），第 3 档 = 可实现口径。
    """
    out = {"modes": [{"mode": n, "cons": c, "gap": g} for n, c, g in EXIT.MODES],
           "tiers": []}
    for key in EXIT_TIERS:
        sel = [r for r in rows if pick(r, key)]
        if not sel:
            out["tiers"].append({"tier": key, "n": 0, "rows": []})
            continue
        rr = []
        for mi, (n, c, g) in enumerate(EXIT.MODES):
            ps = [r["p4"][mi] for r in sel]
            wr = 100.0 * sum(1 for x in ps if x > 0) / len(ps)
            rr.append({"mode": n, "n": len(ps), "wr": round(wr, 2),
                       "mean": round(sum(ps) / len(ps), 3)})
        out["tiers"].append({"tier": key, "n": len(sel), "rows": rr})
    return out


def series(rows, key, ctrl_key="ALL"):
    """返回 ({date: (mean_pnl, win_rate, n)}, {date: (mean_pnl, win_rate)})。

    ctrl_key='ALL' → 对照 = 同日全市场域（问「能不能跑赢随便买」）
    ctrl_key='HARD' → 对照 = 同日**只过旧硬门槛**的深跌域母集（页面原表 ① 的口径）
    """
    return GC.series(rows, _sel(key), lambda r: r["hard"] if ctrl_key == "HARD" else True)


def edge_stats(rows, key, boot=BOOT, seed=SEED, vs="ALL"):
    """vs='ALL' 对照同日全市场域（问「能不能跑赢随便买」）；vs='HARD' 对照同日深跌域母集。"""
    return GC.edge_stats(rows, _sel(key),
                         lambda r: r["hard"] if vs == "HARD" else True,
                         boot=boot, seed=seed, name=key)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="只处理前 N 只（试跑）")
    ap.add_argument("--step", type=int, default=STEP)
    ap.add_argument("--no-html", action="store_true")
    ap.add_argument("--sens", action="store_true",
                    help="敏感性模式：结果另存 _rev_tier_gate_stepN.json，不覆盖主证据、不渲染页面")
    a = ap.parse_args()

    rows = build_panel(limit=a.limit, step=a.step)
    assign(rows, verbose=True)
    out_json = OUT_JSON
    if a.sens:
        out_json = os.path.join(QUANT, "_rev_tier_gate_step%s.json" % a.step)
    res = {"_doc": "底部反转池 v6 分档出票核验（逐日平衡 edge + 按日 block bootstrap + 留一法）",
           "seed": SEED, "boot": BOOT, "step": a.step, "tiers": []}
    for k, desc in TIERS:
        st = edge_stats(rows, k)
        st["desc"] = desc
        res["tiers"].append(st)
        print("[rev] %-5s 天数=%3d n=%7d edge=%+.3fpp R3=%5.1f%% 留一[%.3f,%.3f]"
              % (k, st.get("n_days", 0), st.get("n_rows", 0),
                 st.get("edge", 0), st.get("r3", 0),
                 st.get("loo_min", 0), st.get("loo_max", 0)))
    # 第二对照：相对同日「深跌域母集」（= 页面原表 ① 的口径，用来交叉核对旧结论）
    for st in res["tiers"]:
        if st.get("note"):
            continue
        vs_hard = edge_stats(rows, st["tier"], vs="HARD")
        st["vs_hard"] = {kk: vs_hard.get(kk) for kk in
                         ("edge", "r3", "loo_min", "loo_max", "n_days", "n_rows", "win")}
        print("[rev] %-5s vs深跌域 edge=%+.3fpp R3=%5.1f%%"
              % (st["tier"], vs_hard.get("edge", 0), vs_hard.get("r3", 0)))
    # 前/后半稳定性（单段行情容易把结论锁在某一个市场状态里，必须查同向性）
    for st in res["tiers"]:
        if st.get("note"):
            continue
        st["halves"] = GC.halves(st["days"])
    # 成交假设审计：同一批票、只改「日内路径 / 跳空」，看现行数字虚高多少
    res["exit_assumption"] = exit_assumption(rows)
    for t in res["exit_assumption"]["tiers"]:
        if not t["rows"]:
            continue
        m0 = t["rows"][0]; mz = t["rows"][-1]
        print("[rev·口径] %-5s n=%6d 旧 %5.2f%%(%+.3f%%) → 可实现 %5.2f%%(%+.3f%%)  Δ胜率 %+.2fpp"
              % (t["tier"], t["n"], m0["wr"], m0["mean"], mz["wr"], mz["mean"], mz["wr"] - m0["wr"]))
    json.dump(res, open(out_json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("[rev] 写 %s" % out_json)
    if not a.no_html and not a.limit and not a.sens:
        import _rev_gate_page as P
        P.render(res)


if __name__ == "__main__":
    main()
