# -*- coding: utf-8 -*-
"""高胜率候选池 · 分档出票合法性核验（_hw_tier_gate.py）

为什么要有这一页
----------------
`web/picks/highwin_*.html` 每天给出「核心候选（总分≥68 且无风险否决）」，
并在交易规则里写「<b>优先核心候选</b>」——这就是事实上的出票指引。
但它从未做过显著性检验：页面原话是「本池是多因子共振筛选，不是收益承诺……需累积
20–30 个交易日的前向表现再分组回测，方可把阈值逐步硬化」。

本脚本用**按日 block bootstrap + 留一法 + 前/后半 + 跨步长**回答：
在历史上，这个打分的高分档到底有没有 edge？还敢不敢让它出票？

两个绕不开的口径问题（都如实写进页面）
--------------------------------------
1. **可前推维度只有 40%。**
   生产满分 100 = 技术 25 + 位置 15 + 资金 20 + 筹码 15 + 板块 12 + 龙虎榜 8 + 高管大宗 5。
   其中资金/筹码/板块行为/龙虎榜/高管大宗都来自**当日盘后快照与事件源**（主力净流入、筹码分布、
   板块当日主力行为、龙虎榜、高管增减持、大宗交易）——**回测时不可得**，历史上根本不存在这个文件。
   按项目铁律「缺的维度记 0 并降级」，本页只复刻可得部分：**技术 25 + 位置 15 = 40 分**。
   ⇒ 本页的 CORE 档 = 「可得子分前 10%」，是**降级口径下的近似核心档位置**，
     **不等于**生产「全维 ≥68」的核心档；生产核心档是否真有 alpha，本页判「不可判」。

2. **生产底池本身在缩水，且有一期口径异常。**
   2026-09-23 那期 base=983 只（tech_scanned 4971，与其他期 100 相差 50 倍），
   09-24 那期 base=0 只（build_highwin 跑在 macd_scan 就绪之前），
   09-21 之后每期只剩 35~66 只。本页会逐期把这些事实记下来，不做美化。

做法
----
  * 数据只用 `quant/_txk_cache.json`（全市场真实日K，离线），逐日逐票复刻
    MACD 水上红柱底池 + 可得子打分（macd_ratio / 均线多头排列 / RSI12 / 52 周分位）+ 可得 veto。
  * 收益统一用**移动止盈**（−12% 硬止损 / +6% 激活 / 回撤 3% / 满 20 日强平），
    与 `_selected_lab`、`_rbot` 同口径。
  * **逐日平衡 edge** = 该档逐日均值 − 同日对照域逐日均值。
  * 显著性用 `_gate_common` 的按日 block bootstrap（R3）+ 留一法 + 前/后半。

出票许可
--------
`gen_highwin.py` 只读本脚本产出的 JSON；`_gate_common.emit_license` 要求
edge>0 且 R3≥95% 且跨步长同号且 step3 R3≥95%，**读不到一律不出票**（fail-safe）。

用法：python quant/_hw_tier_gate.py [--limit N] [--step N] [--no-html] [--sens]
"""
from __future__ import annotations
import os, sys, json, math, argparse
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _gate_common as GC
import _selected_lab as S
import _exit_sim as EXIT          # 成交假设审计（四口径单笔收益）

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QUANT = os.path.join(ROOT, "quant")
CACHE = os.path.join(QUANT, "_txk_cache.json")
OUT_JSON = os.path.join(QUANT, "_hw_tier_gate.json")
OUT_HTML = os.path.join(ROOT, "web", "picks", "highwin_tier_gate.html")

STEP = 5            # 采样步长（交易日）
MINI = 130          # 最少 K 线（要 MA120）
A_PCT, M_PCT = 0.10, 0.30   # CORE = 可得子分前 10%，MID = 10~30%
BOOT = GC.BOOT
SEED = 20261004


# ---------------- 指标（从日K复刻） ----------------
def _ema(prev, x, n):
    k = 2.0 / (n + 1)
    return x * k + prev * (1 - k)


def _rsi(C, i, n=12):
    if i <= 0:
        return 0.0
    g = l = 0.0
    for k in range(i - n + 1, i + 1):
        d = C[k] - C[k - 1]
        if d > 0:
            g += d
        else:
            l -= d
    if g + l <= 0:
        return 0.0
    return g / (g + l) * 100.0


def _ma(vals, i, n):
    if i - n + 1 < 0:
        return None
    s = 0.0
    for k in range(i - n + 1, i + 1):
        s += vals[k]
    return s / n


def warm_macd(C, upto, e12, e26, dea):
    """预热 EMA：从不早于 upto-260 根开始推进，把起点误差磨掉。返回 (e12, e26, dea)。"""
    for j in range(max(1, upto - 260), upto + 1):
        c = C[j]
        if not c:
            continue
        e12 = _ema(e12, c, 12)
        e26 = _ema(e26, c, 26)
        dea = _ema(dea, e12 - e26, 9)
    return e12, e26, dea


def macd_state(C, i, e12, e26, dea):
    """推进到 i，返回 (DIF, DEA, 柱)。★ EMA 状态必须由调用方在循环里连续推进，

    每根 K 线都从 0 重算会让 DIF/DEA 退化成「当前价的函数」，底池直接空掉（实测 0 行）。
    """
    c = C[i]
    e12 = _ema(e12, c, 12)
    e26 = _ema(e26, c, 26)
    dif = e12 - e26
    dea = _ema(dea, dif, 9)
    return dif, dea, 2 * (dif - dea), e12, e26, dea


def avail_score(C, H, i, dif, dea, bar):
    """可得子打分：技术 25（macd_ratio / 均线多头 / RSI12）+ 位置 15（52 周分位）。

    ★ 与 `build_highwin.score_one` 完全同式的 clamp/分档，只是输入换成日K复刻值。
    ★ 资金/筹码/板块/龙虎榜/高管大宗 = 不可前推 → 记 0（降级），页面必须写清楚。
    """
    close = C[i]
    if not close:
        return None
    macd_ratio = bar / close * 100
    s_macd = max(0.0, min(macd_ratio / 0.9 * 10, 10))
    ma5, ma10 = _ma(C, i, 5), _ma(C, i, 10)
    ma20, ma60, ma120 = _ma(C, i, 20), _ma(C, i, 60), _ma(C, i, 120)
    align = 0
    if close > ma5 and ma5:
        align += 2
    if ma5 >= ma10 and ma10:
        align += 1
    if ma10 >= ma20 and ma20:
        align += 1
    if ma20 >= ma60 and ma60:
        align += 2
    if ma60 >= ma120 and ma120:
        align += 2
    s_align = max(0, min(align, 8))
    r = _rsi(C, i, 12)
    if 55 <= r <= 75:
        s_rsi = 7
    elif 48 <= r < 55 or 75 < r <= 82:
        s_rsi = 4
    elif r > 0:
        s_rsi = 2
    else:
        s_rsi = 3
    s_tech = s_macd + s_align + s_rsi
    # 位置 15（与 score_one.pos 同分档）
    hi52, lo52 = max(H[:i + 1]), min(H[:i + 1])
    pos52 = (close - lo52) / (hi52 - lo52) * 100 if hi52 > lo52 > 0 else None
    if pos52 is None:
        s_pos = 7
    elif 25 <= pos52 <= 65:
        s_pos = 15
    elif 15 <= pos52 < 25 or 65 < pos52 <= 78:
        s_pos = 10
    elif 78 < pos52 <= 88:
        s_pos = 5
    elif pos52 > 88:
        s_pos = 1
    else:
        s_pos = 6
    veto = (r >= 90) or (pos52 is not None and pos52 >= 92)
    return {"s": s_tech + s_pos, "s_tech": round(s_tech, 2), "s_pos": s_pos,
            "rsi": round(r, 2), "pos52": (round(pos52, 1) if pos52 is not None else None),
            "veto": veto, "macd_ratio": round(macd_ratio, 3)}


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
        print("[hw] 日K %d 只，入面板候选 %d 只" % (len(cache), len(codes)))
    if limit:
        codes = codes[:limit]

    rows = []
    skipped = defaultdict(int)
    for c in codes:
        nm = NM.get(c) or ""
        if "ST" in nm or "退" in nm:
            skipped["bad"] += 1
            continue
        bars = cache[c]
        C = [b["last"] for b in bars]
        H = [b["high"] for b in bars]
        L = [b["low"] for b in bars]
        O = [b["open"] for b in bars]
        n = len(bars)
        e12 = e26 = dea = 0.0
        e12, e26, dea = warm_macd(C, MINI - 1, e12, e26, dea)
        for i in range(MINI, n - S.MAXFWD - 1, step):
            close = C[i]
            if not close:
                continue
            dif, d2, bar, e12, e26, dea = macd_state(C, i, e12, e26, dea)
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
            p4 = [round(x, 4) for x in p4]
            # ★ 复刻生产 criteria：DIF>0 且 DEA>0 且 MACD 红柱>0（生产叫「水上金叉」）
            is_base = bool(dif > 0 and d2 > 0 and bar > 0)
            if not is_base:
                # 非底池行只留统计必需字段（对照域要算收益），控制面板内存
                rows.append({"code": c, "date": bars[i]["date"], "base": False,
                             "pnl": sim["pnl"], "win": bool(sim["win"]), "p4": p4})
                continue
            sc = avail_score(C, H, i, dif, d2, bar)
            if sc is None:
                continue
            rows.append({"code": c, "date": bars[i]["date"], "base": True,
                         "s": sc["s"], "s_tech": sc["s_tech"], "s_pos": sc["s_pos"],
                         "rsi": sc["rsi"], "pos52": sc["pos52"], "veto": sc["veto"],
                         "macd_ratio": sc["macd_ratio"],
                         "pnl": sim["pnl"], "win": bool(sim["win"]), "mae": sim["mae"],
                         "p4": p4})
    if verbose:
        print("[hw] 底池（MACD 水上红柱）面板 %d 行 / %d 日期（剔 ST·退 %d）"
              % (len(rows), len(set(r["date"] for r in rows)), skipped["bad"]))
    return rows


def assign(rows, verbose=False):
    """在**当日底池**内按可得子分切 CORE / MID（生产的分位是在全维 total 上切，这里只能切可得子分）。"""
    byd = defaultdict(list)
    for r in rows:
        if r.get("base"):
            byd[r["date"]].append(r)
    for d, rs in sorted(byd.items()):
        rs.sort(key=lambda r: (-r["s"], r["code"]))
        n = len(rs)
        ia = int(round(n * A_PCT))
        im = int(round(n * M_PCT))
        for i, r in enumerate(rs):
            if r["veto"]:
                r["tier"] = "VETO"
            elif i < ia:
                r["tier"] = "CORE"
            elif i < im:
                r["tier"] = "MID"
            else:
                r["tier"] = "TAIL"
            r["rank"] = i + 1
    if verbose:
        print("[hw] 分档完成，日期 %d 个" % len(byd))
    return rows


TIERS = [
    ("CORE", "可得子分前 10%（降级口径下的近似核心档）"),
    ("MID", "可得子分 10~30%"),
    ("TAIL", "可得子分 30% 以后"),
    ("BASE", "当日 MACD 水上红柱底池全体（生产基底）"),
    ("ALL", "全市场域（随便买 · 绝对对照）"),
]


def pick(r, key):
    if key == "ALL":
        return True
    if key == "BASE":
        return bool(r.get("base"))
    return r.get("tier") == key


# ---------------- 成交假设审计（退出回测的口径依赖） ----------------
EXIT_TIERS = ["CORE", "MID", "BASE", "ALL"]


def exit_assumption(rows):
    """同一批票、只改「日内路径 / 跳空」，看现行胜率虚高多少。

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


def _ctrl_fn(vs):
    """对照口径：
      vs='ALL'     → 同日全市场域（含底池）→ 问「相对随便买」
      vs='BASE'    → 同日底池母集 → 问「**打分本身**的增量」（把底池效应扣掉）
      vs='OFFBASE' → 同日**不在底池**的正股 → 问底池本身相对其他票
    """
    if vs == "BASE":
        return lambda r: bool(r.get("base"))
    if vs == "OFFBASE":
        return lambda r: not r.get("base")
    return lambda r: True


def edge_stats(rows, key, boot=BOOT, seed=SEED, vs="ALL"):
    return GC.edge_stats(rows, lambda r: pick(r, key), _ctrl_fn(vs),
                         boot=boot, seed=seed, name=key)


# ---------------- 复刻自检 ----------------
def replicate_check():
    """拿最近几期生产 macd_scan_* 与本地复刻的底池比对，看复刻有没有跑偏。

    只比对「生产 produced 的那批票有多少落在复刻底池里」——生产还叠了 20 日主力净流入>0，
    所以覆盖率不会是 100%，但**至少 70%** 才说明 MACD 口径没算错。
    """
    out = []
    for fn in sorted(os.listdir(QUANT)):
        if not fn.startswith("macd_sc" + "an_") or not fn.endswith(".json"):
            continue
        p = os.path.join(QUANT, fn)
        try:
            j = json.load(open(p, encoding="utf-8"))
        except Exception:
            continue
        ds = j.get("data_date")
        if not ds:
            continue
        out.append((ds, j.get("final_count") or 0, j.get("above_water") or 0,
                    j.get("tech_scanned"), [s["code"] for s in (j.get("stocks") or [])]))
    return out


def freeze_check():
    """逐期列出生产 macd_scan 的技术扫描覆盖与首只标的指纹，看底池是不是**冻结**的。

    2026-09-24 起 tech_scanned 从 4971 掉到 100，且各期 stocks 完全相同（dif/dea/macd/close 一字不差）
    —— 也就是说这几天的「MACD 水上红柱底池」根本没重扫，是旧快照在复用。
    这一点比任何统计都重要：底池若冻结，「核心候选」就是拿 5 天前的信息在当天出票。
    """
    out = []
    for fn in sorted(os.listdir(QUANT)):
        if not fn.startswith("macd_sc" + "an_") or not fn.endswith(".json"):
            continue
        try:
            j = json.load(open(os.path.join(QUANT, fn), encoding="utf-8"))
        except Exception:
            continue
        st = j.get("stocks") or []
        # ★ 全集合指纹（不是前 5 只）：只有覆盖到全体才能证明「整批没重扫」
        sig = "|".join("%s:%.4f:%.4f:%.4f" % (s["code"], s["dif"], s["dea"], s["close"])
                       for s in sorted(st, key=lambda x: x["code"]))
        out.append({"file": fn[len("macd_scan_"):-len(".json")],
                    "data_date": j.get("data_date"),
                    "tech_scanned": j.get("tech_scanned"),
                    "above_water": j.get("above_water"),
                    "final": j.get("final_count"),
                    "sig": sig, "n": len(st)})
    # 与前一日指纹相同 = 冻结
    prev = None
    for r in sorted(out, key=lambda x: x["file"]):
        r["frozen"] = bool(prev is not None and r["sig"] == prev and r["n"] > 0)
        r["same_as_prev"] = (prev == r["sig"]) if prev is not None else False
        prev = r["sig"]
    # ★ 与链上**任意更早**一期相同也要标：冻结链的起点那期（2026-09-24）跟上一期
    #   本来就不一样，只比上一期会漏掉它（实测 2026-09-18 同样是 09-11 的快照）。
    allr = sorted(out, key=lambda x: x["file"])
    for i, r in enumerate(allr):
        if r["frozen"] or not r["n"]:
            continue
        for pf in reversed(allr[:i]):
            if pf["sig"] and pf["sig"] == r["sig"]:
                r["frozen"] = True
                r["frozen_vs"] = pf["file"]
                break
    # ★ 冻结期证伪「当日数据」：把每只标的的 close 拿去 _txk_cache 反查落在哪一天。
    #   若某期的 close 集体落在很久以前的那天，就坐实「旧快照冒充当日」。
    cache = _load_cache()
    if cache:
        byd = defaultdict(lambda: defaultdict(list))   # date -> close -> [code...]
        for code, bars in cache.items():
            for b in bars:
                byd[b["date"]][round(b["last"], 2)].append(code)
        # close → 出现过的日期集合（一次建表，后面 O(1) 查）
        c2d = defaultdict(set)
        for d, m in byd.items():
            for close in m:
                c2d[close].add(d)
        for r in out:
            if not r["frozen"]:
                continue
            j = _load_macd(r["file"])
            if not j:
                continue
            hits = defaultdict(int)
            for s in j.get("stocks") or []:
                for d in c2d.get(round(s["close"], 2), ()):
                    hits[d] += 1
            if hits:
                top = sorted(hits, key=lambda d: (-hits[d], d))[0]
                r["frozen_close_date"] = top
                r["frozen_close_hit"] = hits[top]
                r["frozen_close_n"] = len(j.get("stocks") or [])
    return out


_CACHE = None


def _load_cache():
    """_txk_cache.json 体积大，按需加载一次并缓存。"""
    global _CACHE
    if _CACHE is None:
        p = os.path.join(QUANT, "_txk_cache.json")
        try:
            _CACHE = json.load(open(p, encoding="utf-8")) or {}
        except Exception:
            _CACHE = {}
    return _CACHE


def _load_macd(stem):
    p = os.path.join(QUANT, "macd_scan_%s.json" % stem)
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return None


def build_replicate_map(rows):
    """本地复刻当日底池：{date: set(code)}。"""
    m = defaultdict(set)
    for r in rows:
        if r.get("base"):
            m[r["date"]].add(r["code"])
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--step", type=int, default=STEP)
    ap.add_argument("--no-html", action="store_true")
    ap.add_argument("--sens", action="store_true",
                    help="敏感性模式：结果另存 _hw_tier_gate_stepN.json，不覆盖主证据、不渲染页面")
    a = ap.parse_args()

    rows = build_panel(limit=a.limit, step=a.step)
    assign(rows, verbose=True)
    out_json = OUT_JSON
    if a.sens:
        out_json = os.path.join(QUANT, "_hw_tier_gate_step%s.json" % a.step)
    res = {"_doc": "高胜率候选池 分档出票核验（逐日平衡 edge + 按日 block bootstrap + 留一法）",
           "seed": SEED, "boot": BOOT, "step": a.step,
           "scope": "可得维度仅 技术25+位置15=40 分（资金/筹码/板块/龙虎榜/高管大宗 不可前推，记 0 降级）",
           "tiers": []}
    for k, desc in TIERS:
        st = edge_stats(rows, k)
        st["desc"] = desc
        res["tiers"].append(st)
        print("[hw] %-5s 天数=%3d n=%7d edge=%+.3fpp R3=%5.1f%% 留一[%.3f,%.3f]"
              % (k, st.get("n_days", 0), st.get("n_rows", 0), st.get("edge", 0),
                 st.get("r3", 0), st.get("loo_min", 0), st.get("loo_max", 0)))
    for st in res["tiers"]:
        if st.get("note"):
            continue
        st["halves"] = GC.halves(st["days"])
        # 第二对照：相对「同日底池母集」——只有这个 edge 才是**打分本身的增量**，
        # 相对全市场的 edge 里还掺着「底池本身是不是强势票」这一块（底池 = MACD 水上红柱，天然偏强）。
        if st["tier"] not in ("BASE", "ALL"):
            vb = edge_stats(rows, st["tier"], vs="BASE")
            st["vs_base"] = {k: vb.get(k) for k in
                             ("n_days", "n_rows", "edge", "r3", "loo_min", "loo_max", "pnl", "win")}
            print("[hw] %-5s vs底池母集 edge=%+.3fpp R3=%5.1f%%" %
                  (st["tier"], vb.get("edge", 0), vb.get("r3", 0)))
        if st["tier"] == "BASE":
            vo = edge_stats(rows, "BASE", vs="OFFBASE")
            st["vs_off"] = {k: vo.get(k) for k in ("edge", "r3", "loo_min", "loo_max")}
            print("[hw] BASE vs非底池 edge=%+.3fpp R3=%5.1f%%"
                  % (vo.get("edge", 0), vo.get("r3", 0)))
    # 复刻自检：与生产 macd_scan 的对账
    rmap = build_replicate_map(rows)
    rep = []
    for ds, fc, aw, tsc, codes in replicate_check():
        # 面板按 step 采样，生产日期未必被采到 → 回退到它之前最近的一个采样日再比对
        pds = [d for d in sorted(rmap) if d <= ds]
        ls = rmap.get(pds[-1]) if pds else set()
        hit = len(set(codes) & ls) if (ls and codes) else 0
        rep.append({"date": ds,
                    "prod_n": fc, "prod_above_water": aw, "prod_tech_scanned": tsc,
                    "panel_date": (pds[-1] if pds else None),
                    "repl_n": len(ls),
                    "prod_hit": hit,
                    "cover": round(hit / len(codes) * 100.0, 1) if (codes and ls) else None})
    res["replicate"] = rep
    res["freeze"] = freeze_check()
    # 成交假设审计：同一批票、只改「日内路径 / 跳空」
    res["exit_assumption"] = exit_assumption(rows)
    for t in res["exit_assumption"]["tiers"]:
        if not t["rows"]:
            continue
        m0 = t["rows"][0]; mz = t["rows"][-1]
        print("[hw·口径] %-5s n=%6d 旧 %5.2f%%(%+.3f%%) → 可实现 %5.2f%%(%+.3f%%)  Δ胜率 %+.2fpp"
              % (t["tier"], t["n"], m0["wr"], m0["mean"], mz["wr"], mz["mean"], mz["wr"] - m0["wr"]))
    if rep:
        print("[hw] 复刻自检（最近 3 期）：")
        for x in rep[-3:]:
            print("     %s 生产 %d 只 → 复刻命中 %d（%.0f%%）；复刻底池 %d 只（技术扫描 %s）"
                  % (x["date"], x["prod_n"], x["prod_hit"], x["cover"] or 0,
                     x["repl_n"], x["prod_tech_scanned"]))
    json.dump(res, open(out_json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("[hw] 写 %s" % out_json)
    if not a.no_html and not a.limit and not a.sens:
        import _hw_gate_page as P
        P.render(res)


if __name__ == "__main__":
    main()
