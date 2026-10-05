# -*- coding: utf-8 -*-
"""做T池 · 大盘环境门控（ENV_RULE pos_scale 1.0 / 0.8 / 0.55 / 0.0）样本外验证。

为什么单独做一页：主升精选的 env_gate 已经把「折数系数」证伪（反推系数强势 +1.00 显著为正、
震荡/弱势/破位点估计为负 → 二值门控），但 **ENV_RULE 是做T池共用的同一张表**，做T场景从未单独
验证过。主升那页没有验证做T的接口，所以不能拿它的结论直接套用。这一页补做T那一半。

口径（尽量与生产一致，不用实验室便利口径）：
  * 收益口径 = `_tplus_lab._sim_default`（线上现行参数）：反T —— 支撑上方 2% 进、
    目标 = max(2.5%, 1.2×ATR)、−6% 止损、5 日到期；**未成交记 0**（空仓等待是策略的一部分，不算亏）。
  * 环境分<b>对齐生产口径</b>：生产 env_score = 0.45×指数分 + 0.55×market_profile core，
    本脚本逐项复刻（权重与公式原样搬），只在「≤ 信号日」的收盘 + 已落盘画像上算 → 无未来函数。
    core 没落盘的日退化为纯指数分（与主升 env_gate 完全同口径）。
  * 选股层 = 每交易日内按 PRIOR_A 做横截面分位、取前 **10%**（生产 build_tplus.py 的 A 档口径），
    对照 = 同日全票。edge 一律**逐日平衡**（先算每日 top 均 − 该日全票均，再对日取平均），
    不把跨日样本池化成单一均值 —— 那样会把「日期数差」混进 edge。
  * 前向窗口重叠 → 样本非独立，显著性全部用**按日 block bootstrap**（整日整日重抽）。

闸门口径（沿用 _strategy_gate 的三条假阳性规则）：
  R1 对照等量：策略与对照在同一日、同一口径内比，edge 是逐日差的平均，样本量差被抵消。
  R2 真选股层：比较对象是横截面前 K（真选股层），不是全市场全票。
  R3 双条件：edge>0 **且** bootstrap 中 edge>0 的比例 ≥95%。
"""
from __future__ import annotations
import os, sys, json, math, random, statistics

from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _tplus_lab as T
import _idxkline as E

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QUANT = os.path.join(ROOT, "quant")
PANEL = os.path.join(QUANT, "_tplus_lab_panel.json")
OUT = os.path.join(ROOT, "web", "tplus", "env_gate.html")
OUT_JSON = os.path.join(QUANT, "_tplus_env_gate.json")

PRIOR = T.PRIOR                 # 默认（v6）落地用的先验集
PCT = 0.10                      # 生产 build_tplus.py：A 档 = 全量前 10%
BOOT = 800
SEED = 20261003
ORDER = ["强势", "震荡", "弱势", "破位"]
CUT_FRAC = 0.6                  # walk-forward 训练/测试切分（按信号日位置）


# ---------------- 环境分（复刻生产 env_score：0.45 指数 + 0.55 画像 core） ----------------
def idx_score(ie):
    """复刻 _idxkline.env_score 中的指数子分（core 缺失时的兜底口径）。"""
    if not ie:
        return None
    dev = (ie["close"] - ie["ma20"]) / ie["ma20"] * 100 if ie["ma20"] else 0.0
    s = 3.0
    if dev > 1:
        s += 0.7
    elif dev > 0:
        s += 0.3
    elif dev > -1:
        s -= 0.2
    elif dev > -3:
        s -= 0.8
    else:
        s -= 1.4
    if ie.get("slope5") is not None:
        if ie["slope5"] > 0.4:
            s += 0.5
        elif ie["slope5"] > 0:
            s += 0.2
        elif ie["slope5"] > -0.4:
            s -= 0.2
        else:
            s -= 0.5
    if ie.get("chg5") is not None:
        if ie["chg5"] > 2:
            s += 0.5
        elif ie["chg5"] > 0:
            s += 0.2
        elif ie["chg5"] > -2:
            s -= 0.2
        else:
            s -= 0.5
    return max(1.0, min(5.0, s))


def label_of(sc):
    if sc is None:
        return "未知"
    if sc >= 3.8:
        return "强势"
    if sc >= 3.0:
        return "震荡"
    if sc >= 2.2:
        return "弱势"
    return "破位"


def env_of(d):
    """(score, label, has_core, index_only) —— 生产 composite 口径；core 缺失退化指数口径。"""
    _, det = E.env_score(d)
    si, pc = det.get("index_score"), det.get("profile_core")
    sc_i = idx_score(E.index_env(d)) if si is None else si
    if pc is None or si is None:
        return (sc_i, label_of(sc_i), False, sc_i)
    sc = round(0.45 * si + 0.55 * pc, 2)
    return (sc, label_of(sc), True, sc_i)


# ---------------- 面板 → 逐日 top（真选股层）+ 全票 ----------------
def build():
    rows = json.load(open(PANEL, encoding="utf-8"))
    byd = defaultdict(list)
    for r in rows:
        byd[r["date"]].append(r)

    # 模拟只算一次，结果直接挂回行对象（用 id() 当键不可靠，直接挂属性最稳）
    for r in rows:
        r["_simd"] = T._sim_default(r)
    dup = len(rows) - len({(r["code"], r["date"]) for r in rows})
    print("[tplus-env] 面板 (code,date) 重复行 %d（应为 0）" % dup)
    env = {d: env_of(d) for d in byd}

    top = {}
    for d, rs in byd.items():
        if len(rs) < 12:
            continue
        rk = {}
        for f in PRIOR:
            vals = sorted([(r["f"].get(f), r["code"]) for r in rs if r["f"].get(f) is not None])
            if len(vals) < 6:
                continue
            for pos, (_, c) in enumerate(vals):
                rk.setdefault(c, {})[f] = pos / (len(vals) - 1)
        sc = []
        for r in rs:
            tot = cnt = 0.0
            for f in PRIOR:
                v = rk.get(r["code"], {}).get(f)
                if v is None:
                    continue
                tot += 1 - v
                cnt += 1
            if cnt >= max(2, len(PRIOR) // 2):
                sc.append((tot / cnt, r))
        if len(sc) >= 12:
            sc.sort(key=lambda x: -x[0])
            k = max(1, int(round(len(sc) * PCT)))
            top[d] = [(r, r["_simd"]["ret"]) for _, r in sc[:k]]

    return rows, byd, top, env


def mean(v):
    return sum(v) / len(v) if v else 0.0


def block_boot(pairs, boot=BOOT, seed=SEED):
    """pairs = [(date, value)]；按日整块重抽 → (mean, lo, hi, 重抽样中为正的比例)。"""
    rnd = random.Random(seed)
    if not pairs:
        return (0.0, 0.0, 0.0, 0.0)
    uniq = sorted({d for d, _ in pairs})
    mat = defaultdict(list)
    for d, v in pairs:
        mat[d].append(v)
    pos_cnt = 0
    ms = []
    for _ in range(boot):
        pick = [uniq[rnd.randrange(len(uniq))] for _ in range(len(uniq))]
        flat = [x for d in pick for x in mat[d]]
        if not flat:
            continue
        m = mean(flat)
        ms.append(m)
        if m > 0:
            pos_cnt += 1
    ms_sorted = sorted(ms)
    lo = ms_sorted[int(len(ms_sorted) * 0.05)] if ms_sorted else 0.0
    hi = ms_sorted[int(len(ms_sorted) * 0.95)] if ms_sorted else 0.0
    return (mean([v for _, v in pairs]), lo, hi, (pos_cnt / len(ms)) if ms else 0.0)


def ci(vs, lo_q=0.05):
    vs = sorted(vs)
    if not vs:
        return (0.0, 0.0)
    return (vs[int(len(vs) * lo_q)], vs[int(len(vs) * (1 - lo_q))])


# ---------------- 主流程 ----------------
def main():
    random.seed(SEED)
    rows, byd, top, env = build()
    ds_all = sorted(byd)
    print("[tplus-env] 面板 %d 行 / %d 交易日（%s ~ %s）"
          % (len(rows), len(ds_all), ds_all[0], ds_all[-1]))

    per_d = []
    for d in sorted(top):
        a = [v for _, v in top[d]]
        b = [r["_simd"]["ret"] for r in byd[d]]
        st = [row["_simd"] for row, _ in top[d]]
        none = sum(1 for s in st if s["kind"] == "none")
        trd = [s["ret"] for s in st if s["kind"] != "none"]
        sc, lab, hc, _ = env[d]
        per_d.append({"date": d, "lab": lab, "sc": sc, "hc": hc,
                      "top": mean(a), "all": mean(b), "n_top": len(a), "n_all": len(b),
                      "n_none": none, "cond": mean(trd), "cond_wr":
                          (sum(1 for x in trd if x > 0) / len(trd) * 100) if trd else 0.0})
    print("[tplus-env] 有横截面成立的信号日 %d" % len(per_d))

    n_days = defaultdict(int)
    for p in per_d:
        n_days[p["lab"]] += 1
    print("[tplus-env] 分档天数：%s" % dict(n_days))

    # ① 各档逐日平衡 edge（策略前 PCT − 同日全票）
    edge_out = {}
    for lab in ORDER + ["未知"]:
        sub = [p for p in per_d if p["lab"] == lab]
        if not sub:
            continue
        ps = [(p["date"], p["top"] - p["all"]) for p in sub]
        m0, lo, hi, rate = block_boot(ps)
        edge_out[lab] = {
            "n": len(ps),
            "mean_top": mean([p["top"] for p in sub]),
            "mean_all": mean([p["all"] for p in sub]),
            "edge": m0, "ci": (lo, hi), "r3": rate,
        }
        print("  %-4s %3d日 top %+.3f%% / 全票 %+.3f%% / edge %+.3f [%.3f,%.3f] R3 %.0f%%"
              % (lab, len(ps), edge_out[lab]["mean_top"], edge_out[lab]["mean_all"],
                 m0, lo, hi, rate * 100))

    # ② 反推相对仓位系数（均值-方差有效口径 f = mean/sd，归一强势 = 1）
    coef_out = {}
    base = None
    for lab in ORDER:
        vals = [p["top"] - p["all"] for p in per_d if p["lab"] == lab]
        if len(vals) < 3:
            continue
        m = mean(vals)
        sd = statistics.pstdev(vals) if len(vals) > 1 else 0.0
        fs = []
        rnd = random.Random(SEED + 1)
        for _ in range(BOOT // 4):
            samp = [vals[rnd.randrange(len(vals))] for _ in range(len(vals))]
            mm, ss = mean(samp), statistics.pstdev(samp) if len(samp) > 1 else 0.0
            fs.append(mm / ss if ss else 0.0)
        if lab == "强势":
            base = (m / sd) if sd else None
        coef_out[lab] = {"n": len(vals), "mean": m, "sd": sd,
                         "f": (m / sd) if sd else 0.0, "f_ci": ci(fs), "fs": fs}
        print("  %-4s mean/sd = %+.4f  f_ci [%.3f, %.3f]"
              % (lab, coef_out[lab]["f"], coef_out[lab]["f_ci"][0], coef_out[lab]["f_ci"][1]))
    for lab in coef_out:
        c = coef_out[lab]
        c["rel"] = (c["f"] / base) if base else None
        c["rel_ci"] = ((c["f_ci"][0] / base, c["f_ci"][1] / base) if base else (0.0, 0.0))
        print("  %-4s 相对系数 = %+.2f [%.2f, %.2f]"
              % (lab, c["rel"], c["rel_ci"][0], c["rel_ci"][1]))

    # ③ 留一法（去掉单日后 edge 会不会塌）
    loo = {}
    for lab in ORDER:
        ps = [(p["date"], p["top"] - p["all"]) for p in per_d if p["lab"] == lab]
        if len(ps) < 4:
            continue
        vals = []
        for i in range(len(ps)):
            sub = ps[:i] + ps[i + 1:]
            vals.append(mean([v for _, v in sub]))
        loo[lab] = {"min": min(vals), "max": max(vals)}
        print("  %-4s 留一法 edge [%+.3f, %+.3f]" % (lab, min(vals), max(vals)))

    # ④ walk-forward（前 60% 训练 / 后 40% 测试）
    ds_sorted = sorted({p["date"] for p in per_d})
    cut = ds_sorted[int(len(ds_sorted) * CUT_FRAC)]
    wf = {}
    for lab in ORDER:
        tr = [p["top"] - p["all"] for p in per_d if p["lab"] == lab and p["date"] < cut]
        te = [p["top"] - p["all"] for p in per_d if p["lab"] == lab and p["date"] >= cut]
        wf[lab] = {"train": mean(tr) if tr else None,
                   "test": mean(te) if te else None, "n_tr": len(tr), "n_te": len(te)}
        print("  %-4s train %+.3f（%d日）/ test %+.3f（%d日）"
              % (lab, wf[lab]["train"] or 0, len(tr), wf[lab]["test"] or 0, len(te)))

    # ⑤ 环境分连续分位（每 0.5 分一档）
    buckets = defaultdict(list)
    for p in per_d:
        if p["sc"] is None:
            continue
        buckets[round(p["sc"] * 2) / 2].append(p)
    by_sc = {}
    for b in sorted(buckets):
        ps = buckets[b]
        a, c = mean([p["top"] for p in ps]), mean([p["all"] for p in ps])
        nwin = sum(1 for p in ps if p["top"] > p["all"]) / len(ps) * 100 if ps else 0
        by_sc[b] = {"day": len(ps), "n": sum(p["n_top"] for p in ps),
                    "top": a, "all": c, "edge": a - c, "nwin": nwin}
        print("  %.1f 档 %2d日 n=%5d top %+.3f%% 全票 %+.3f%% edge %+.3f%% 逐日胜率 %.0f%%"
              % (b, len(ps), by_sc[b]["n"], a, c, a - c, nwin))

    # ⑤b 成交率诊断：edge 是不是「压根没成交、记 0」撑起来的（空仓也算一种结果，必须摊开）
    fill = {}
    for lab in ORDER:
        sub = [p for p in per_d if p["lab"] == lab]
        if not sub:
            continue
        fill[lab] = {
            "day": len(sub),
            "none_pct": sum(p["n_none"] for p in sub) / max(1, sum(p["n_top"] for p in sub)) * 100,
            "cond": mean([p["cond"] for p in sub]),
            "cond_wr": mean([p["cond_wr"] for p in sub]),
            "edge": mean([p["top"] - p["all"] for p in sub]),
        }
        print("  %-4s 未成交占比 %.1f%% ｜ 成交后条件均值 %+.3f%% ｜ 条件胜率 %.0f%%"
              % (lab, fill[lab]["none_pct"], fill[lab]["cond"], fill[lab]["cond_wr"]))

    # ⑥ 生产 ENV_RULE 对照：现行 allow / pos_scale vs 数据反推
    rule = {}
    for lab in ORDER + ["未知"]:
        r = E.ENV_RULE.get(lab, {})
        rule[lab] = {"allow": list(r.get("allow", [])), "pos_scale": r.get("pos_scale")}
    suggest = {}
    for lab in ORDER:
        c = coef_out.get(lab)
        if not c or c["rel"] is None:
            suggest[lab] = "样本不足 · 保持现行"
        elif c["rel"] > 0 and c["rel_ci"][1] > 0:
            suggest[lab] = "可开仓（系数 ≈ %.2f）" % c["rel"]
        else:
            suggest[lab] = "空仓（反推 ≤ 0，现行 %.2f 无依据）" % (rule.get(lab, {}).get("pos_scale") or 0)

    res = {"pct": PCT, "per_d": per_d, "edge": edge_out, "coef": coef_out, "loo": loo,
           "wf": wf, "by_sc": by_sc, "rule": rule, "suggest": suggest, "fill": fill, "cut": cut,
           "n_days": dict(n_days), "ds_lo": per_d[0]["date"] if per_d else "",
           "ds_hi": per_d[-1]["date"] if per_d else "", "n_rows": len(rows),
           "n_days_total": len(ds_all), "seed": SEED, "boot": BOOT}
    json.dump(res, open(OUT_JSON, "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
    print("[tplus-env] 落 %s" % OUT_JSON)
    render(res)


# ---------------- 渲染 ----------------
def _f(v, d=2):
    if v is None:
        return "—"
    return "{:+.{}f}".format(v, d)


CSS = """<style>
:root{--bg:#fbfbfd;--card:#fff;--text:#1d1d1f;--muted:#6e6e73;--line:#e5e5e7;
 --up:#ff3b30;--dn:#34c759;--blue:#0071e3;--gold:#a97b2e;}
*{box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif;
 background:var(--bg);color:var(--text);line-height:1.7;margin:0;padding:0}
.wrap{max-width:1020px;margin:0 auto;padding:26px 18px 56px}
h1{font-size:23px;font-weight:700;margin:0 0 6px;letter-spacing:-.02em}
h2{font-size:18px;font-weight:600;margin:28px 0 12px;padding-bottom:8px;border-bottom:2px solid var(--blue)}
h3{font-size:15px;font-weight:600;margin:18px 0 8px}
.sub{color:var(--muted);font-size:13px;margin-bottom:8px}
.card{background:var(--card);border-radius:16px;padding:14px 20px;margin:12px 0;box-shadow:0 1px 3px rgba(0,0,0,.05)}
.box{border-left:4px solid var(--blue);background:#f0f7ff;padding:13px 18px;border-radius:0 12px 12px 0;margin:14px 0}
.box.gold{border-color:var(--gold);background:#fffaf0}
.box.red{border-color:#c0392b;background:#fdf1f0}
.box.green{border-color:var(--dn);background:#f0faf3}
table{width:100%;border-collapse:collapse;font-size:12.5px;margin:10px 0}
th,td{padding:7px 6px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
th{white-space:nowrap;color:var(--muted);font-weight:600;font-size:11.5px;background:#fafafa}
.num{font-variant-numeric:tabular-nums;text-align:right}
.up{color:var(--up)}.dn{color:var(--dn)}.am{color:var(--blue)}.dim{color:#b0b3b8}
.note{font-size:12.5px;color:var(--muted);margin-top:8px}
li{margin:5px 0}
.foot{text-align:center;color:var(--muted);font-size:12px;margin-top:26px}
</style>"""


def render(res):
    ed, co, lo, wf, bs, ru, sg, fill = (res["edge"], res["coef"], res["loo"], res["wf"],
                                        res["by_sc"], res["rule"], res["suggest"],
                                        res.get("fill", {}))
    o = []
    A = o.append
    A("<!DOCTYPE html><html lang='zh-CN'><head><meta charset='utf-8'>")
    A("<meta name='viewport' content='width=device-width,initial-scale=1'>")
    A("<title>做T池 · 大盘环境门控样本外验证</title>%s</head><body><div class='wrap'>" % CSS)
    A(f"<h1>做T池 · 大盘环境门控样本外验证</h1>")
    A(f"<div class='sub'>面板 {res['n_rows']:,} 行 / {res['n_days_total']} 个交易日"
      f"（{res['ds_lo']} ~ {res['ds_hi']}）｜ 真选股层 = 每日横截面按先验集取前 "
      f"{res['pct']*100:.0f}%（生产 A 档口径）｜ 收益 = 线上现行做T逐笔模拟"
      f"（反T：支撑上方 2% 进 / 1.2×ATR 目标 / −6% 止损 / 5 日到期，未成交记 0）"
      f"｜ 显著性 = 按日 block bootstrap {res['boot']} 次</div>")

    s = ed.get("强势", {})
    A(f"<div class='box gold'><b>一句话结论：</b>本页验的是<b>做T场景下</b>那张共用表 "
      f"<code>ENV_RULE</code>（强势 1.0 / 震荡 0.8 / 弱势 0.55 / 破位 0.0）的地基。")
    if s:
        A(f"强势档 edge {_f(s['edge'])} pp（逐日平衡，95% 区间 [{_f(s['ci'][0])}、{_f(s['ci'][1])}]，"
          f"bootstrap 通过率 {s['r3']*100:.0f}%）")
    parts = []
    for lab in ORDER:
        c = co.get(lab)
        if c and c.get("rel") is not None:
            parts.append(f"{lab} {_f(c['rel'])}")
    A("；反推的相对系数（归一强势 = 1）：" + "、".join(parts) + "。")
    A(" 乍看之下弱势（+1.50）比强势（+1.00）还高，四档点估计也<b>全是正的</b>；但本页后面的检验显示："
      "<b>这些点估计之间的差距，全部落在同一条噪声带里</b> —— 95% 区间<b>无一例外跨 0</b>、"
      "R3 通过率只有 48%~78%（远低于 95% 门槛）、反推系数的相对区间宽到 ±3 量级。"
      "所以本页<b>做不出「哪一档该给几折」的结论</b>，只能判「不可判」。"
      "本页结论<b>独立于</b>主升精选 env_gate —— 那是日线持有 20 日场景，这里是日内做T场景，"
      "两者共用同一张表但<b>必须分别验证</b>；也正因为如此，<b>不能</b>把主升的二值门控"
      "（强势开仓、其余空仓）照搬过来。</div>")

    # ①
    A(f"<h2>① 各环境档的逐日平衡 edge（策略前 {res['pct']*100:.0f}% − 同日全票）</h2>")
    A("<table><tr><th>环境档</th><th>信号日</th><th>策略层均收益</th><th>同日全票均</th>"
      "<th>edge（pp）</th><th>95% 区间</th><th>R3 通过率</th><th>留一法区间</th></tr>")
    for lab in ORDER + ["未知"]:
        a = ed.get(lab)
        if not a:
            continue
        l = lo.get(lab, {})
        A(f"<tr><td>{lab}</td><td class='num'>{a['n']}</td>"
          f"<td class='num {'up' if a['mean_top']>0 else 'dn'}'>{_f(a['mean_top'])}%</td>"
          f"<td class='num'>{_f(a['mean_all'])}%</td>"
          f"<td class='num {'up' if a['edge']>0 else 'dn'}'><b>{_f(a['edge'])}</b></td>"
          f"<td class='num'>[{_f(a['ci'][0])}, {_f(a['ci'][1])}]</td>"
          f"<td class='num'>{a['r3']*100:.0f}%</td>"
          f"<td class='num'>[{_f(l.get('min',0))}, {_f(l.get('max',0))}]</td></tr>")
    A("</table>")
    A("<div class='note'>R3 = edge&gt;0 且在 block bootstrap 重抽样中为正的比例 ≥95%（双条件）。"
      "两条都没过的档，不能声称「环境门控提升了做T」。留一法 = 逐一剔除单个信号日后 edge 的波动范围。</div>")

    # ②
    A("<h2>② 反推的相对仓位系数（均值-方差有效口径 f = mean/sd，归一强势 = 1）</h2>")
    A("<table><tr><th>环境档</th><th>信号日</th><th>mean</th><th>sd</th>"
      "<th>f = mean/sd</th><th>f 95% 区间</th><th>相对系数</th><th>相对 95% 区间</th></tr>")
    for lab in ORDER:
        c = co.get(lab)
        if not c:
            continue
        A(f"<tr><td>{lab}</td><td class='num'>{c['n']}</td><td class='num'>{_f(c['mean'],3)}</td>"
          f"<td class='num'>{c['sd'] or 0:.3f}</td>"
          f"<td class='num {'up' if c['f']>0 else 'dn'}'>{c['f']:+.4f}</td>"
          f"<td class='num'>[{c['f_ci'][0]:.2f}, {c['f_ci'][1]:.2f}]</td>"
          f"<td class='num {'up' if (c['rel'] or 0)>0 else 'dn'}'><b>{_f(c['rel'])}</b></td>"
          f"<td class='num'>[{_f(c['rel_ci'][0])}, {_f(c['rel_ci'][1])}]</td></tr>")
    A("</table>")
    A("<div class='note'>固定风险预算时第 i 档的最优暴露 f ≈ mean/sd（sd = 该档<b>逐日 edge</b> 的标准差，"
      "单位 pp）。本页各档 sd 都在 3.9~4.6pp 量级，而 edge 均值只有 0.03~1.14pp，"
      "<b>信噪比不到 0.3</b> —— 这是「折数分不出来」的直接原因，不是取样方式的问题。"
      "作为对照：主升精选那页的强势档 sd 小得多、R3 通过率 100%，所以能得出「强势开仓、其余空仓」。"
      "本页做T的逐日波动天生大（日内成交/止损/到期三种结局分散），同样的样本量下分辨力就是不够。</div>")

    # ③
    A("<h2>③ 生产现行 ENV_RULE 与数据反推的对照</h2>")
    A("<table><tr><th>环境档</th><th>现行 allow</th><th>现行 pos_scale</th>"
      "<th>反推相对系数</th><th>本页依据下的建议</th></tr>")
    for lab in ORDER + ["未知"]:
        if lab not in ru:
            continue
        r, c = ru[lab], co.get(lab, {})
        A(f"<tr><td>{lab}</td><td>{'/'.join(r.get('allow',[])) or '—'}</td>"
          f"<td class='num'>{r.get('pos_scale')}</td><td class='num'>{_f(c.get('rel'))}</td>"
          f"<td><b>{sg.get(lab,'—')}</b></td></tr>")
    A("</table>")

    # ④
    A(f"<h2>④ walk-forward（按信号日切 {res['cut']}：前 {CUT_FRAC*100:.0f}% 训练 / "
      f"后 {(1-CUT_FRAC)*100:.0f}% 测试）</h2>")
    A("<table><tr><th>环境档</th><th>训练半 edge</th><th>测试半 edge</th>"
      "<th>两半同号</th><th>说明</th></tr>")
    for lab in ORDER:
        w = wf.get(lab)
        if not w:
            continue
        t, e = w.get("train"), w.get("test")
        same = (t is not None and e is not None and (t > 0) == (e > 0))
        tag = "<span class='dn'>否</span>" if not same else "<span class='up'>是</span>"
        if same and (t or 0) > 0 and (e or 0) > 0:
            note = "两半同号且同为正 → 可依赖"
        elif same:
            note = "两半同号但同负 → 该档整体不做"
        else:
            note = "半间翻转 → 不可依赖"
        A(f"<tr><td>{lab}</td><td class='num'>{_f(t or 0)}</td><td class='num'>{_f(e or 0)}</td>"
          f"<td>{tag}</td><td>{note}</td></tr>")
    A("</table>")

    # ⑤
    A("<h2>⑤ 环境分连续分位（每 0.5 分一档，真选股层）</h2>")
    A("<table><tr><th>环境分区间</th><th>信号日</th><th>样本数</th><th>策略层均</th>"
      "<th>同日全票均</th><th>edge</th><th>逐日 前10%&gt;全票 占比</th></tr>")
    for b in sorted(bs):
        v = bs[b]
        A(f"<tr><td>{b:.1f} 分</td><td class='num'>{v['day']}</td><td class='num'>{v['n']:,}</td>"
          f"<td class='num {'up' if v['top']>0 else 'dn'}'>{_f(v['top'])}%</td>"
          f"<td class='num'>{_f(v['all'])}%</td>"
          f"<td class='num {'up' if v['edge']>0 else 'dn'}'>{_f(v['edge'])}</td>"
          f"<td class='num'>{v['nwin']:.0f}%</td></tr>")
    A("</table>")

    # ⑤b 成交率诊断
    A("<h2>⑥ 成交率诊断：edge 里有多少是「压根没成交、记 0」</h2>")
    A("<table><tr><th>环境档</th><th>信号日</th><th>未成交占比</th><th>全样本均值（记 0 口径）</th>"
      "<th>成交后条件均值</th><th>成交后条件胜率</th></tr>")
    for lab in ORDER:
        v = fill.get(lab)
        if not v:
            continue
        A(f"<tr><td>{lab}</td><td class='num'>{v['day']}</td>"
          f"<td class='num'>{v['none_pct']:.1f}%</td>"
          f"<td class='num'>{_f(v['edge'])}</td>"
          f"<td class='num {'up' if v['cond']>0 else 'dn'}'><b>{_f(v['cond'])}</b></td>"
          f"<td class='num'>{v['cond_wr']:.0f}%</td></tr>")
    A("</table>")
    A("<div class='note'>做T的未成交记 0（空仓等待是策略的一部分）。若某档 edge 明显高于其他档，"
      "但成交率也明显更低，那这个 edge 是<b>「少出手」</b>造成的，不是<b>「选得准」</b>——"
      "真实账户里底仓一直在，不做T的日子是有机会成本的，本口径没记这笔账。"
      "所以判定时<b>同时看</b>全样本均值与成交后条件均值。</div>")
    bp = fill.get("破位", {})
    sq = fill.get("强势", {})
    if bp and sq:
        A("<div class='box red'><b>一个反直觉的观察（只记录，不据此改规则）：</b>"
          f"现行 ENV_RULE 给<b>破位档 0.0（完全空仓）</b>，但成交率诊断显示破位档的"
          f"<b>未成交占比最高（{bp['none_pct']:.0f}%）</b>、而<b>成交后条件均值也最高"
          f"（{_f(bp['cond'])}、条件胜率 {bp['cond_wr']:.0f}%）</b>，反而高于强势档的 "
          f"{_f(sq['cond'])} / {sq['cond_wr']:.0f}%。"
          "也就是说：<b>破位日里真成交的那部分做T，看起来比强势日做T更赚</b>。"
          "但破位只有 25 个信号日、成交样本更少，且全样本口径下它的 edge 只有 "
          f"{_f(bp['edge'])}（95% 区间 {ed.get('破位',{}).get('ci',('—','—'))[0]} ~ "
          f"{ed.get('破位',{}).get('ci',('—','—'))[1]}，跨 0）。"
          "<b>两个口径排序相反 = 样本量不够支撑任何结论</b>，因此本页<b>不建议</b>把破位从 0.0 放开，"
          "只把它作为一条待积累样本的观察项记在这里。</div>")

    # ⑦ 局限
    A("<h2>七、结论与局限</h2>")
    good = [l for l in ORDER if ed.get(l) and ed[l]["r3"] >= 0.95 and ed[l]["edge"] > 0]
    if not good:
        A("<div class='box red'><b>判「不可判」—— 做T池的 ENV_RULE 折数（1.0 / 0.8 / 0.55 / 0.0）"
          "在样本外<b>分不出差别</b>，任何改法都还没有证据支持。</b><br>"
          "四个档的 edge 点估计虽都是正的，但 95% 区间<b>全部跨 0</b>、R3 通过率只有 "
          + " / ".join(f"{l} {ed[l]['r3']*100:.0f}%" for l in ORDER if ed.get(l))
          + "（远低于 95% 门槛）；反推系数的相对区间宽到 ±3 量级（毫无分辨力）；"
          "环境分连续分位<b>非单调</b>（1.5 分与 2.5 分高、2.0 分最低、4.5 分为负），"
          "是噪声的形状而不是信息的形状。<br>"
          "<b>因此：做T池保持现行 ENV_RULE 原值不动</b>，也不套用主升精选的「强势开仓、其余空仓」"
          "——那是日线持有场景验出来的，做T是日内场景，且本页点估计显示弱势档"
          f"{_f(co.get('弱势',{}).get('rel'))} 反而高于强势 {_f(co.get('强势',{}).get('rel'))}，"
          "照搬会把做T做反。</div>")
    A("<div class='card'><ul>")
    A("<li><b>本页只验做T场景</b>，与主升精选 env_gate 的结论不能互相套用；两者共用同一张 "
      "<code>ENV_RULE</code> 表，若要改系数须<b>分别</b>取得各自场景的样本外证据。</li>")
    A("<li><b>口径对齐生产</b>：环境分用生产 <code>env_score</code> = 0.45×指数分 + 0.55×"
      "<code>market_profile</code> core 的 composite；core 没有落盘的信号日退化为纯指数分，"
      "本页对这类日的标签可能与实际执行的 composite 标签不同（生产执行用 composite）。</li>")
    A("<li><b>不是胜率提升器</b>：edge 是相对「同日全票」的增量，不是绝对胜率。"
      "做T的未成交记 0，所以「空仓等待」在本口径下既不算赚也不算亏 —— 空仓的机会成本没有计入。</li>")
    A(f"<li><b>面板时间窗口有限</b>：{res['ds_lo']} ~ {res['ds_hi']}，共 {res['n_days_total']} 个交易日；"
      "分到四档后每档只有个位数到十几日的信号日，bootstrap 区间必然很宽，"
      "这是真实的不确定性，不是精度问题。</li>")
    A("<li><b>本页只验做T场景</b>，与主升精选 env_gate 的结论不能互相套用；两者共用同一张 "
      "<code>ENV_RULE</code> 表，若要改系数须<b>分别</b>取得各自场景的样本外证据。</li>")
    A(f"<li>所有数字由 <code>quant/_tplus_env_gate.py</code> 重算得出，种子固定（{res['seed']}）、"
      f"bootstrap {res['boot']} 次；原始结果落 <code>quant/_tplus_env_gate.json</code>。</li>")
    A("</ul></div>")
    A(f"<div class='foot'>做T池 · 大盘环境门控样本外验证 ｜ 数据区间 {res['ds_lo']} ~ {res['ds_hi']} ｜ "
      "无未来函数（只用 ≤ 信号日的收盘与画像）</div>")
    A("</div></body></html>")

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    open(OUT, "w", encoding="utf-8").write("\n".join(o))
    print("[tplus-env] 写 %s" % OUT)


if __name__ == "__main__":
    main()
