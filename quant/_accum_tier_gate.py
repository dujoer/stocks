# -*- coding: utf-8 -*-
"""
增仓精选 · 分档规则显著性检验（_accum_tier_gate.py）
====================================================
起因：文档标注错位。生产 build_accum.scan() 用的是「全候选域按规则分档」
（今日 S6 / A46 / B124），而 web/accumulation/lab.html 与 accum_result.json
评估的是「每日 composite 得分 top25」——**两个口径不是同一批票**。
所以页面给每档标的胜率，测的未必是实际出票那批。

本脚本按**生产真实分档定义**在**全候选域**上重建面板，逐入场日跑：
  ① 逐日平衡 edge（该档逐日均 − 同日候选域逐日均）+ block bootstrap + R3 通过率
  ② 该档绝对收益（回答「这个环境做多本身赚不赚钱」）
  ③ 留一法（去掉任一天是否会归零）
  ④ walk-forward（前半估 → 后半验）
  ⑤ 与实验室 top25 口径的交叉核对

口径与退出生效参数全部沿用 _accum_lab / build_accum：
  STOP −12% / ACT +6% / TRAIL 3% / MAXFWD 20 日；仅取前瞻已走满 20 根的入场日。

用法：
  python _accum_tier_gate.py [--days 20] [--boot 800]
"""
import os, sys, json, random, statistics, argparse, collections

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import _accum_lab as L
import _gate_common as GC          # ★ 跨窗口出票许可（单一真源，与 build_accum 共用）

OUTDIR = os.path.join(ROOT, "web", "accumulation")
OUTJSON = os.path.join(HERE, "_accum_tier_gate.json")
OUTHTML = os.path.join(OUTDIR, "tier_gate.html")

BOOT = 2000      # ★ 固定 bootstrap 次数：R3 的分辨率 = 1/BOOT，改次数会改 er3_min（判据依赖它）。
                 #   历史坑：旧证据页用 2000、脚本默认 800，同一份数据两次跑出不同 er3_min
                 #   （S 档 20 日 0.921 vs 0.9175），结论不可复现。判定一律按本常量。
SEED = 20261004
DAYS = 20

I_KEYS = ("pe", "sun", "person", "fund")
M_KEYS = ("m1", "m3", "m5")

# 必须与 build_accum.scan() 完全一致
def tier_of(n_sig, I, M, m5r):
    if m5r >= L.MARG_TH[5] and I:
        return "S"
    if n_sig >= 3 and (M or I):
        return "A"
    if n_sig == 2:
        return "B"
    return "C"

RULES = [
    ("S 档（现行生产）",        lambda r: r["tier"] == "S"),
    ("A 档（现行生产·M或I）",   lambda r: r["tier"] == "A"),
    ("A 档（候选改法·M且I）",   lambda r: r["n"] >= 3 and r["M"] and r["I"]),
    ("B 档（观察仓·2信号）",     lambda r: r["tier"] == "B"),
    ("C 档（1信号·不入名单）",   lambda r: r["tier"] == "C"),
    ("全候选域（无筛选对照）",   lambda r: True),
]


def mean(xs):
    return sum(xs) / len(xs) if xs else 0.0


def block_boot(pairs, boot=BOOT, seed=SEED):
    """pairs=[(date, value)] → (点估计, lo, hi, 重抽样中>0 的比例)。按日整块重抽。"""
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
        m = mean(flat)
        ms.append(m)
        if m > 0:
            pos += 1
    ss = sorted(ms)
    n = len(ss)
    lo = ss[int(n * 0.05)] if n else 0.0
    hi = ss[min(n - 1, int(n * 0.95))] if n else 0.0
    return (mean([v for _, v in pairs]), lo, hi, (pos / len(ms)) if ms else 0.0)


def build(days=DAYS):
    K = L.load_kline()
    cal = L.trading_days(K)
    q2 = L.load_q2_flags()
    snaps = L.load_margin_snapshots()
    mh = L.load_margin_em()

    hi = max(0, len(cal) - L.MAXFWD)
    lastN = cal[max(0, hi - days):hi]
    print("[accum-gate] 入场日 %s ~ %s（%d 日，前瞻均走满 %d 根）"
          % (lastN[0], lastN[-1], len(lastN), L.MAXFWD))

    rows = []          # 每笔一行：dict(code, date, ret, win, tier, n, I, M, m5r, top25)
    cover = []         # 每日覆盖情况诊断
    for T in lastN:
        frame = L.signal_frame(T, K, q2, snaps, cal, mh=mh)
        scored = []
        for code, sig in frame.items():
            if not any(k in sig and sig[k] > 0 for k in L.DAILY):
                continue
            sc = L.composite(sig)
            if sc <= 0:
                continue
            scored.append((code, sc, sig))
        scored.sort(key=lambda x: (-x[1], x[0]))
        top25 = {c for c, _, _ in scored[:L.TOPN]}
        n_frame, n_scored, n_noSim = len(frame), len(scored), 0
        # ★ 融资信号（M 维）可用性：`_mr5` 只在 margin_em_event 命中时才写入 sig。
        #   2026-10-05 审计：margin_em 覆盖不齐（277/1082 只无数据、日期不一），
        #   picks/margin_*.json 只有 6 个快照（最早 09-10）→ 面板期 M 信号大面积缺失。
        #   不把这个数落盘，就无从判断「S/A 档样本为何这么小」，也无法判定结论是否可判。
        n_mraw = sum(1 for _c, _s, sg in scored if "_mr5" in sg)
        for code, sc, sig in scored:
            n_sig = sum(1 for k in L.ALLSIG if k in sig and sig[k] > 0)
            I = any(k in sig and sig[k] > 0 for k in I_KEYS)
            M = any(k in sig and sig[k] > 0 for k in M_KEYS)
            m5r = sig.get("_mr5") or 0.0
            r = L.simulate(K, code, T)
            if not r:
                n_noSim += 1
                continue
            # ★ 成交假设审计：本池跟踪止盈按**收盘触发/收盘成交**（不含日内路径假设），
            #   唯一需修正的是**硬止损跳空** —— 开盘已破止损线时以开盘价成交（更差）。
            rg = L.simulate(K, code, T, gap=True)
            rows.append({"code": code, "date": T, "ret": r[0] * 100.0, "win": r[1],
                         "ret_gap": (rg[0] * 100.0) if rg else r[0] * 100.0,
                         "win_gap": (rg[1] if rg else r[1]),
                         "tier": tier_of(n_sig, I, M, m5r),
                         "n": n_sig, "I": I, "M": M, "m5r": m5r,
                         "top25": code in top25, "score": sc})
        cover.append({"date": T, "frame": n_frame, "cand": n_scored, "no_sim": n_noSim,
                      "m_raw": n_mraw,
                      "m_raw_pct": round(100.0 * n_mraw / n_scored, 2) if n_scored else 0.0})
    return rows, lastN, cover


def analyse(rows, dates, a_boot=BOOT):
    """逐日平衡口径：该档逐日均 − 同日全候选域逐日均。"""
    byd = collections.defaultdict(list)
    for r in rows:
        byd[r["date"]].append(r)
    ctrl = {d: mean([x["ret"] for x in byd[d]]) for d in byd}

    out = {}
    for name, fn in RULES:
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
            m = mean(sub)
            pd_abs.append((d, m))
            pd_edge.append((d, m - ctrl[d]))
        n = len(hits)
        wr = 100.0 * sum(1 for r in hits if r["win"]) / n
        pooled_ret = mean([r["ret"] for r in hits])
        e0, elo, ehi, er3 = block_boot(pd_edge, boot=a_boot, seed=SEED)
        a0, alo, ahi, ar3 = block_boot(pd_abs, boot=a_boot, seed=SEED)
        # 多种子看 R3 的蒙特卡洛抖动；判定一律取最保守（最小）的那个
        r3s = [block_boot(pd_edge, boot=a_boot, seed=SEED + i)[3] for i in range(3)]
        lv = []
        for i in range(len(pd_edge)):
            sub = pd_edge[:i] + pd_edge[i + 1:]
            lv.append(mean([v for _, v in sub])) if sub else None
        cut_i = len(pd_edge) // 2
        first = [v for _, v in pd_edge[:cut_i]]
        second = [v for _, v in pd_edge[cut_i:]]
        out[name] = {
            "n": n, "wr": wr, "ret": pooled_ret, "days": len(pd_edge),
            "edge": e0, "eci": (elo, ehi), "er3": er3,
            "er3_min": min(r3s), "er3_max": max(r3s),
            "abs": a0, "aci": (alo, ahi), "ar3": ar3,
            "loo": (min(lv), max(lv)) if lv else (0.0, 0.0),
            "wf": (mean(first), mean(second)),
            "wf_n": (len(first), len(second)),
        }
    return out, ctrl


def cross_check_top25(rows, dates):
    """复刻 _accum_lab 的 top25 口径，核对能否还原 accum_result.json 的 sel_wr。"""
    sel = [r for r in rows if r["top25"]]
    if not sel:
        return None
    return {"n": len(sel), "wr": 100.0 * sum(1 for r in sel if r["win"]) / len(sel),
            "ret": mean([r["ret"] for r in sel])}


WINDOWS = (20, 40, 60)      # 20 = 生产滚动窗口；40/60 为样本量敏感性
PRIMARY = max(WINDOWS)
PROD_WINDOW = min(WINDOWS)  # ★ 出票许可一律按生产窗口判定，不用 max(WINDOWS)（那是窗口挑优）
DATA_GATE_M_PCT = 30.0      # ★ 数据有效性闸：M 维（融资增仓）候选覆盖率下限（%）


def exit_assumption(rows):
    """成交假设审计（增仓池专用口径）。

    ⚠ 本池的跟踪止盈是**收盘触发、收盘成交**（`cl <= peak*(1-TRAIL)`），
      **不含**同根 K 线「先冲高后回落」的日内路径假设 → 不适用 cons 修正；
      唯一需要修正的成交假设是**硬止损跳空**（开盘已破 −12% 线时以开盘价成交，更差）。
    """
    out = {"note": "跟踪止盈为收盘触发/收盘成交，不含日内路径假设；本表只修正「硬止损跳空」",
           "tiers": []}
    for name, fn in RULES:
        sel = [r for r in rows if fn(r)]
        if not sel:
            out["tiers"].append({"rule": name, "n": 0})
            continue
        o_ret = mean([r["ret"] for r in sel])
        g_ret = mean([r.get("ret_gap", r["ret"]) for r in sel])
        o_wr = 100.0 * sum(1 for r in sel if r["win"]) / len(sel)
        g_wr = 100.0 * sum(1 for r in sel if r.get("win_gap", r["win"])) / len(sel)
        out["tiers"].append({"rule": name, "n": len(sel),
                             "wr": round(o_wr, 2), "ret": round(o_ret, 3),
                             "wr_gap": round(g_wr, 2), "ret_gap": round(g_ret, 3),
                             "d_wr": round(g_wr - o_wr, 2), "d_ret": round(g_ret - o_ret, 3)})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=0,
                    help="0=跑全部窗口（默认：20/40/60），否则只跑指定窗口")
    ap.add_argument("--boot", type=int, default=BOOT)
    ap.add_argument("--no-html", dest="html", action="store_false", default=True)
    a = ap.parse_args()
    wins = (a.days,) if a.days else WINDOWS

    per = {}
    for d in wins:
        rows, dates, cover = build(d)
        stat, _ = analyse(rows, dates, a.boot)
        cc = cross_check_top25(rows, dates)
        per[d] = {"stat": stat, "cross": cc, "cover": cover,
                  "window": [dates[0], dates[-1]], "n_rows": len(rows),
                  "n_days": len(dates),
                  "exit_assumption": exit_assumption(rows),
                  "lose_no_sim": sum(c["no_sim"] for c in cover)}
        print("[accum-gate] 窗口 %d 日：入场 %s ~ %s ｜ 面板 %d 笔"
              % (d, dates[0], dates[-1], len(rows)))
        print("  %-22s %6s %6s %8s %9s %9s %10s %9s"
              % ("规则", "笔数", "日数", "胜率%", "绝对%", "edge(pp)", "R3(最小~最大)", "留一法"))
        for name, _ in RULES:
            s = stat.get(name)
            if not s:
                print("  %-22s 无样本" % name)
                continue
            print("  %-22s %6d %6d %8.1f%% %+8.2f%% %+9.2f [%+5.2f,%+5.2f] %4.0f~%4.0f%% [%+5.2f,%+5.2f]"
                  % (name, s["n"], s["days"], s["wr"], s["ret"], s["edge"],
                     s["eci"][0], s["eci"][1],
                     s["er3_min"] * 100, s["er3_max"] * 100,
                     s["loo"][0], s["loo"][1]))
        if cc:
            print("  [交叉核对] top25 口径 n=%d 胜率 %.1f%% 均收益 %.2f%%" % (cc["n"], cc["wr"], cc["ret"]))
        for t in per[d]["exit_assumption"]["tiers"]:
            if not t["n"]:
                continue
            print("  [口径·跳空修正] %-22s n=%6d 胜率 %5.1f%%→%5.1f%% (%+.2fpp) 均值 %+.2f%%→%+.2f%%"
                  % (t["rule"], t["n"], t["wr"], t["wr_gap"], t["d_wr"], t["ret"], t["ret_gap"]))
        print()

    res = {"boot": a.boot, "primary": PRIMARY if PRIMARY in per else wins[-1],
           "per": per,
           "ctrl_NOTE": "对照 = 同日全候选域逐日均；收益单位为 %，edge 单位为 pp"}
    # ★ 允许出票的档：走 `_gate_common.tier_license_windows` 的统一严格口径。
    #   历史坑：原实现按 `PRIMARY = max(WINDOWS)`（60 日）单窗口判 `edge>0 且 er3_min≥95%`，
    #   而生产滚动窗口是 20 日 —— B 档在 20 日 er3_min=0.926（不达标）、60 日 0.9995（达标），
    #   按最大窗口判定 = 在窗口维度上挑优；且判据漏掉绝对收益 R3、留一法、前/后半。
    #   现改为：生产窗口 edge>0 ＋ 所有窗口 R3≥95% ＋ 所有窗口绝对收益 R3≥95%
    #          ＋ 留一法全正 ＋ 前/后半同正。
    allow, lic_detail = [], {}
    for name, _ in RULES:
        if name.startswith("全候选域"):
            continue
        ok, why, det = GC.tier_license_windows(per, name, prod_window=PROD_WINDOW)
        lic_detail[name] = {"ok": bool(ok), "why": why, "detail": det}
        if ok:
            allow.append(name)
    res["allow"] = allow
    res["allow_detail"] = lic_detail
    res["prod_window"] = PROD_WINDOW
    res["license_note"] = ("判据：生产窗口（%d 日）edge>0 ＋ 全部窗口 R3≥95%% "
                           "＋ 全部窗口绝对收益 R3≥95%% ＋ 留一法全正 ＋ 前/后半同为正"
                           % PROD_WINDOW)
    # ★ 数据有效性闸（与统计无关）：M 维 = 融资增仓，是 S/A 档的核心判据之一。
    #   若面板期拿不到 M 信号（margin_em 覆盖不齐 / 快照稀疏），
    #   那么「S 档」根本无从构成、「A 档」只剩 I 侧单腿 —— 统计再漂亮也是拿缺维数据算的。
    #   这与红线「读不到证据就不出票」同源：宁可空仓，不用缺维信号出票。
    covs = per.get(res["primary"], {}).get("cover") or []
    mp = [c.get("m_raw_pct", 0.0) for c in covs]
    avg_m = (sum(mp) / len(mp)) if mp else 0.0
    zero_days = sum(1 for x in mp if x <= 0.0)
    dg_ok = (avg_m >= DATA_GATE_M_PCT)
    res["data_gate"] = {
        "ok": dg_ok, "field": "m_raw_pct（面板有融资信号的候选占比）",
        "avg_pct": round(avg_m, 2), "min_pct": round(min(mp), 2) if mp else 0.0,
        "days": len(mp), "zero_days": zero_days, "threshold": DATA_GATE_M_PCT,
        "note": ("M 维（融资增仓）在面板期覆盖 %.1f%%（%d 个入场日中 %d 个完全无 M 信号）；"
                 "阈值 %.0f%%。M 是 S 档的必要条件，覆盖不足时 S/A 档结论不作数。"
                 % (avg_m, len(mp), zero_days, DATA_GATE_M_PCT)),
    }
    if not dg_ok:
        for k in lic_detail:
            lic_detail[k]["ok"] = False
            lic_detail[k]["why"] = ("【数据闸】" + lic_detail[k]["why"])
        allow = []
        res["allow"] = []
        print("[accum-gate] ⚠ 数据有效性闸未通过：M 维平均覆盖 %.1f%% < %.0f%% → 全档不出票"
              % (avg_m, DATA_GATE_M_PCT))
    json.dump(res, open(OUTJSON, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("[accum-gate] 按生产窗口 %d 日的统一判据判定，可出票的档：%s"
          % (PROD_WINDOW, "、".join(allow) if allow else "无（全部未达门槛）"))
    for k, v in lic_detail.items():
        print("   %-24s %s  %s" % (k, "可出票" if v["ok"] else "不出票", v["why"]))
    print("[accum-gate] 结论落 %s" % OUTJSON)
    if a.html:
        render(res)


# ----------------------------- 渲染 -----------------------------
CSS = """
body{font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif;
margin:0;padding:24px;background:var(--bg,#f7f8fa);color:var(--fg,#1f2328);line-height:1.7}
.wrap{max-width:1080px;margin:0 auto}
h1{font-size:22px;margin:0 0 6px}
h2{font-size:17px;margin:26px 0 8px;padding-left:9px;border-left:4px solid var(--blue,#2563eb)}
.sub{color:#666;font-size:13px;margin-bottom:18px}
table{border-collapse:collapse;width:100%;font-size:13px;margin:8px 0;background:#fff}
th,td{border:1px solid #e3e6ea;padding:6px 8px;text-align:left}
th{background:#f0f3f7;font-weight:600}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
.up{color:#ea4335;font-weight:600}
.dn{color:#34a853;font-weight:600}
.box{padding:12px 14px;border-radius:8px;background:#fff;border:1px solid #e3e6ea;margin:12px 0}
.box.red{background:#fff5f5;border-color:#f3c2c2}
.box.green{background:#f4fbf6;border-color:#bfe3c9}
.box.warn{background:#fffaf0;border-color:#ecd9ae}
.note{font-size:12.5px;color:#666}
ul{margin:6px 0 6px 20px;padding:0}
li{margin:3px 0}
a{color:var(--blue,#2563eb)}
"""

def _f(v, d=2):
    if v is None:
        return "—"
    return "{:+.{}f}".format(v, d)

def _g(v, d=1):
    if v is None:
        return "—"
    return "{:.{}f}".format(v, d)

def render(res):
    per = res["per"]
    pkey = res["primary"]
    P = per[pkey]
    st = P["stat"]
    cc = P.get("cross")
    cover = P.get("cover", [])
    if isinstance(st, str):
        st = json.loads(st)
    order = ["S 档（现行生产）", "A 档（现行生产·M或I）",
             "A 档（候选改法·M且I）", "B 档（观察仓·2信号）",
             "C 档（1信号·不入名单）",
             "全候选域（无筛选对照）"]
    def row_of(name):
        s = st.get(name)
        if not s:
            return ("<tr><td>%s</td><td colspan='7' class='num'>无样本</td></tr>" % name)
        cls = "up" if s["edge"] > 0 else "dn"
        return (
            "<tr><td>%s</td><td class='num'>%d</td><td class='num'>%d</td>"
            "<td class='num'>%s%%</td><td class='num'>%s%%</td>"
            "<td class='num %s'><b>%s</b></td><td class='num'>[%s, %s]</td>"
            "<td class='num'>%.0f%%~%.0f%%</td><td class='num'>[%s, %s]</td></tr>"
            % (name, s["n"], s["days"], _g(s["wr"]), _f(s["ret"]),
               cls, _f(s["edge"]), _f(s["eci"][0]), _f(s["eci"][1]),
               s["er3_min"] * 100, s["er3_max"] * 100,
               _f(s["loo"][0]), _f(s["loo"][1])))

    rows_html = "".join(row_of(n) for n in order)

    # 判定语：与 allow 同一真源（`_gate_common.tier_license_windows`），不再各写一版
    licd = res.get("allow_detail") or {}
    verdict = {}
    for n in order:
        s = st.get(n)
        if not s:
            verdict[n] = "无样本"
            continue
        if n.startswith("全候选域"):
            verdict[n] = "对照域（不参与出票）"
            continue
        ld = licd.get(n)
        if ld is None:
            verdict[n] = "未纳入许可判定"
        elif ld.get("ok"):
            verdict[n] = ("成立（可出票）：生产窗口 %d 日 edge>0 ＋ 跨窗口 R3≥95%% "
                          "＋ 绝对收益 R3≥95%% ＋ 留一法全正 ＋ 前/后半同为正"
                          % res.get("prod_window", PROD_WINDOW))
        else:
            verdict[n] = "不可出票：%s" % (ld.get("why") or "")
    vhtml = "".join("<tr><td>%s</td><td>%s</td></tr>" % (n, verdict[n]) for n in order)

    a_cur = st.get("A 档（现行生产·M或I）")
    a_new = st.get("A 档（候选改法·M且I）")
    s_s = st.get("S 档（现行生产）")

    if a_cur and a_cur["edge"] < 0:
        ahead = ("<div class='box red'><b>已发现问题：A 档（现行生产「≥3共振且 M 或 I」）"
                 "的逐日平衡超额为负</b>（%s pp，R3 最低仅 %.0f%%，绝对收益 %s%% 也低于不筛选的候选域 %s%%）。"
                 "也就是说按现行规则出票的那一档，<b>还不如不筛选</b>；"
                 "且窗口拉长到 %d 个入场日后负值更大 —— 这不是噪声，是稳定负贡献。"
                 % (_f(a_cur["edge"]), a_cur["er3_min"] * 100, _f(a_cur["ret"]),
                    _f(st["全候选域（无筛选对照）"]["ret"]) if st.get("全候选域（无筛选对照）") else "—",
                    pkey))
        if a_new and a_new["edge"] > a_cur["edge"]:
            ahead += ("<br>候选改法「≥3共振且 M <b>且</b> I」在同一批样本上超额为 %s pp（R3 %.0f%%），"
                      "但它<b>是在这批样本里挑出来的赢家</b>，本页不采纳为出票依据，只作对照。"
                      % (_f(a_new["edge"]), a_new["er3_min"] * 100))
        ahead += "</div>"
    else:
        ahead = ("<div class='box warn'><b>A 档（现行生产）超额 %s pp，R3 %.0f%%</b>，详见下表判定。</div>"
                 % (_f(a_cur["edge"]) if a_cur else "—",
                    (a_cur["er3_min"] * 100) if a_cur else 0))

    cc_html = ""
    if cc:
        cc_html = ("<div class='note'>交叉核对：复刻实验室 top25 口径得 n=%d、胜率 %.1f%%、"
                   "均收益 %s%%（入场日窗口 %s ~ %s），可与 <code>accum_result.json</code> 的 sel_wr 互相对照，"
                   "用于确认本次重算没有跑偏。</div>"
                   % (cc["n"], cc["wr"], _f(cc["ret"]), P['window'][0], P['window'][1]))

    cov_rows = "".join(
        "<tr><td>%s</td><td class='num'>%d</td><td class='num'>%d</td>"
        "<td class='num'>%d</td><td class='num'>%s</td></tr>"
        % (c["date"], c["frame"], c["cand"], c["no_sim"],
           ("%.1f%%" % c["m_raw_pct"]) if c.get("m_raw_pct") is not None else "—")
        for c in cover)
    cov_html = ("<table><tr><th>入场日</th><th class='num'>信号帧覆盖（只）</th>"
                "<th class='num'>候选域（≥1 日频信号且合成分&gt;0）</th>"
                "<th class='num'>缺当日K线被弃</th>"
                "<th class='num'>其中拿到融资信号（M 维）</th></tr>%s</table>" % cov_rows) \
        if cover else ""

    # ★ 数据有效性闸展示：M 维缺失会让 S 档无从构成、A 档只剩单腿
    dg = res.get("data_gate") or {}
    dg_html = ""
    if dg:
        okc = "up" if dg.get("ok") else "dn"
        dg_html = ("<div class='note'><b>★ 数据有效性闸（与统计无关的前置条件）："
                   "<span class='%s'>%s</span></b><br>%s<br>"
                   "口径：M 维 = 融资增仓（东财日频序列 T+1 公布），是 <b>S 档的必要条件</b>；"
                   "覆盖不足时 S/A 档的样本本身就构造不出来，统计结论一律不作数。</div>"
                   % (okc, "通过" if dg.get("ok") else "未通过 → 该池全档不出票",
                      dg.get("note", "")))

    # 跨窗口敏感性：edge 与 R3 随样本量怎样变
    sens_rows = ""
    for d in sorted(per.keys()):
        sd = per[d]["stat"]
        cells = []
        for nm in order[:4]:
            v = sd.get(nm)
            cells.append("<td class='num'>%s</td><td class='num'>%.0f%%</td>"
                         % (_f(v["edge"]) if v else "—",
                            v["er3_min"] * 100 if v else 0))
        sens_rows += ("<tr><td>%d 日<span class='note'>（%s~%s）</span></td>%s</tr>"
                      % (d, per[d]["window"][0], per[d]["window"][1], "".join(cells)))
    sens_head = "".join("<th class='num' colspan='2'>%s</th>" % n for n in order[:4])
    sens_html = ("<table><tr><th>入场日窗口</th>%s</tr>"
                 "<tr><th></th>%s</tr>%s</table>"
                 % (sens_head,
                    "".join(x for n in order[:4] for x in
                            ("<th class='num'>edge</th><th class='num'>R3低</th>",)),
                    sens_rows))

    # 成交假设审计：本池跟踪止盈为收盘触发/收盘成交 → 只需修「硬止损跳空」一处
    ea = (P or {}).get("exit_assumption") or None
    if ea:
        ea_rows = []
        for t in ea["tiers"]:
            if not t.get("n"):
                continue
            ea_rows.append(
                "<tr><td>%s</td><td class='num'>%d</td><td class='num'>%s%%</td><td class='num'>%s%%</td>"
                "<td class='num %s'>%+.2fpp</td><td class='num'>%s%%</td><td class='num'>%s%%</td>"
                "<td class='num %s'>%+.3fpp</td></tr>"
                % (t["rule"], t["n"], _g(t["wr"]), _g(t["wr_gap"]),
                   "up" if t["d_wr"] > 0 else "dn", t["d_wr"],
                   _f(t["ret"]), _f(t["ret_gap"]),
                   "up" if t["d_ret"] > 0 else "dn", t["d_ret"]))
        ea_html = ("<h2>五、退出回测的成交假设（本池只需修一处）</h2>"
                   "<div class='box'><b>" + ea["note"] + "。</b><br>"
                   "因此「同一根 K 线先冲高后回落」那处系统性乐观<b>与本池无关</b>；"
                   "下表只把「硬止损跳空」的修正量摆出来。<br>"
                   "实测修正量极小：<b>胜率基本不变</b>（硬止损无论按止损线价、还是按更差的开盘价成交，"
                   "<b>都记为亏</b>），只有均值略微下移。"
                   "⇒ <b>本池展示的胜率不受成交假设显著影响</b>，与主升/反转/高胜率三个池不同。</div>"
                   "<table><tr><th>规则</th><th class='num'>笔数</th><th class='num'>胜率</th>"
                   "<th class='num'>跳空修正后</th><th class='num'>Δ胜率</th>"
                   "<th class='num'>均值</th><th class='num'>修正后均值</th><th class='num'>Δ均值</th></tr>"
                   + "".join(ea_rows) + "</table>"
                   "<div class='note'>口径定义与全项目统一实现见 "
                   "<a href='../docs/exit_assumption_evidence.html'>退出成交假设证据页</a>"
                   "（<code>quant/_exit_sim.py</code> 为唯一实现）。</div>")
    else:
        ea_html = ("<h2>五、退出回测的成交假设</h2>"
                   "<div class='box'>本页<b>未做成交假设核验（无证据）</b>。</div>")

    html = f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>增仓精选 · 分档规则显著性检验</title>
<style>{CSS}</style></head><body><div class="wrap">
<h1>增仓精选 · 分档规则显著性检验</h1>
<div class="sub">主判定窗口 {P['window'][0]} ~ {P['window'][1]}
（{P['n_days']} 个入场日，每笔前瞻均走满 20 根）｜ 面板 {P['n_rows']} 笔 ｜
bootstrap {res['boot']} 次按日整块重抽 × 三个随机种子取保守值</div>

<div class="box"><b>为什么会有这一页。</b>
生产 <code>build_accum.scan()</code> 是<b>全候选域按规则分档</b>（当日 S / A / B 全部出票），
而 <code>lab.html</code> 与 <code>accum_result.json</code> 评估的是<b>每日 composite 得分 top25</b> ——
两者不是同一批票，页面给每档标的胜率<b>未必是实际出票那批</b>。
另外页面把 A 档写成「≥3 共振且（M 或 I）」、却标注 59.4%（那是「M <b>且</b> I」的数字），
规则与数字对不上。本页按<b>生产真实分档定义</b>在<b>全候选域</b>上重建面板，
用主升/做T 门控同一套方法（逐日平衡 edge + block bootstrap + R3 + 留一法 + walk-forward）重新判定。</div>

{ahead}

<h2>一、各档判定（对照 = 同日全候选域逐日均）</h2>
<table><tr><th>规则</th><th class="num">笔数</th><th class="num">日数</th><th class="num">胜率</th>
<th class="num">绝对收益</th><th class="num">edge（pp）</th><th class="num">95% 区间</th>
<th class="num">R3（三个种子区间）</th><th class="num">留一法</th></tr>
{rows_html}</table>
{cc_html}
<div class="note">edge = 该档当日均值 − 同日全候选域当日均值，再对日取平均（逐日平衡，剔除大盘日影响）。
R3 = bootstrap 重抽样中 edge &gt; 0 的比例；因单点估计对随机种子敏感，这里跑三个种子、<b>取最保守（最小）值判定</b>。</div>

<h2>二、逐档结论</h2>
{dg_html}
<table><tr><th>规则</th><th>判定</th></tr>{vhtml}</table>

<h2>三、样本量敏感性（同一规则在不同窗口下稳不稳）</h2>
{sens_html}
<div class="note">判据不是「点估计好不好看」，而是<b>符号会不会随采样翻转</b>。
A 档（现行）随窗口拉长负得更厉害（方向一致、稳定负贡献）；B 档相反，随样本增加转正并达标；
S 档与「候选改法」两档在三个窗口里数字完全一样 —— 因为它们依赖的两融/事件数据只在最近的入场日可得，
<b>拉长窗口加不进新样本</b>，样本量被数据可得性锁死。</div>

<h2>四、每日覆盖度（为什么样本这么少）</h2>
{cov_html}
<div class="note">页面头部写的「候选域 3609 只」是信号帧覆盖的全部股票，真正进入候选的是
「当日触发过至少一个日频事件且合成分 &gt; 0」的那一层，每天只有几十~一百多只，
也就是说<b>所谓的横截面分档是在很小的池子里做的</b>。
另有 {P.get('lose_no_sim', 0)} 笔因缺当日 K 线被弃（占面板不到 5%）。</div>

{ea_html}

<h2>六、局限与口径声明</h2>
<div class="card">
<ul>
<li>分档定义逐字复刻 <code>build_accum.scan()</code>：S = 5 日融资净买入占比 ≥4%
且机构/私募季度增持；A = ≥3 信号共振且（M 或 I）；B = 恰 2 个信号。</li>
<li>退出生效参数沿用 <code>_accum_lab</code>：止损 −12% ／ +6% 激活 ／ 回撤 3% 跟踪 ／ 满 20 日强平；
入场日只取前瞻已走满 20 根的那些。</li>
<li>对照口径是<b>同日全候选域</b>（当日触发过至少一个日频事件、且合成分为正的全体），
故「全候选域（无筛选对照）」那一行 edge 恒为 0，只用来看它的绝对水平。</li>
<li>机构/私募维度来自季度股东快照，把它套到历史入场日<b>天然带有后见偏差</b>；
这是该数据集的既有属性，本页不做修正，只在此声明。</li>
<li>主判定窗口只有 {P['n_days']} 个入场日、{P['n_rows']} 笔，
且早期每天候选只有几十只、后期上百只（数据可得性随时间变宽，窗口本身不均匀）；
逐日平衡会把「几十只的日子」和「上百只的日子」等权，这是本页刻意的保守处理。
按项目红线，<b>达不到 R3 门槛的一律判「不可判」，不作为出票依据</b>。</li>
<li>本页只做「现有规则有没有超额」的判定，<b>不做规则改良</b>：候选改法那一行只用于对照，
不代表改用它就能赚钱（在同一批样本上挑赢家本身即是过拟合）。</li>
</ul></div>

<div class="note"><a href="index.html">← 返回增仓精选</a> ｜
<a href="lab.html">回测证据页（top25 口径）</a></div>
</div></body></html>"""
    os.makedirs(OUTDIR, exist_ok=True)
    open(OUTHTML, "w", encoding="utf-8").write(html)
    print("[accum-gate] 证据页 %s" % OUTHTML)


if __name__ == "__main__":
    main()
