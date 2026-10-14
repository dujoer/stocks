# -*- coding: utf-8 -*-
"""主升精选 · 环境门控「跨采样频率稳健性」严扫（对齐 _freq_robust.py 第五道闸标准）。

为什么单独再扫一遍（_env_gate_sens.py 已经有了）：
  sens.py 只扫 step 3/5/6/9 四组，且判据是「符号是否同号」这种宽松口径。
  而各选股池在 _freq_robust.py 里被要求通过**更严的三判据**：
    edge>0 ＋ R3≥95%（block bootstrap 中为正的比例）＋ 跨频率符号翻转 0 次。
  主升精选的环境门控（全站唯一有样本外正 alpha 的来源）必须接受**同一套考验**，
  否则它就是「宽于它对别人设的线」—— 红线不允许双标。

方法（与 _env_gate_sens.py 一致、可派生）：
  * 横截面分位是**日内**计算的，所以从一次 step=1 密扫描里按 ds[::m] 抽子集，
    与直接按 step=m 扫描结果严格相同（同一天域/因子/分位/退出模拟完全一致）。
    → 一次密扫描派生 7 组步长，避免重复加载几百 MB 缓存。
  * 口径对齐 _env_gate_lab.py（生产 composite = 0.45*指数分 + 0.55*画像 core，无未来函数）。
  * 退出模拟走 AUDIT_MODE="legacy"（与 _env_gate_lab 头条 +2.443pp 同口径）；
    可实现口径已在 env_gate.html 第七节单独验证（强势仍成立）。
  * 显著性 = 按日移动块 bootstrap（块长 = 覆盖前推窗口 FMAX 个信号日，处理相邻信号日窗口重叠）。

判据（仅对「强势」开仓档；其余档本就空仓，不要求它们有 alpha）：
  cr1 符号一致：7 步绝对均收益全 > 0（翻转 0 次）
  cr2 R3：7 步绝对收益的 block-bootstrap R3 全 ≥ 95%
  cr3 选股 alpha：7 步相对同日全票的 edge 全 > 0（强势档下选股层确有 alpha）
  PASS = 三判据全满足。

不改动生产：只做检验，写 ENV_RULE / build_selected.py 一律不动。
"""
from __future__ import annotations
import _txk
import os, sys, json, math, random, statistics
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env_gate_lab as G
import _env_gate_sens as SENS

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QUANT = os.path.join(ROOT, "quant")
OUT = os.path.join(ROOT, "web", "selected", "env_gate_freq.html")
OUT_JSON = os.path.join(QUANT, "_env_gate_freq.json")

BASE_STEP = 1                              # 一次密扫描，派生多组
STEPS = [1, 2, 3, 5, 8, 10, 20]            # 对齐 _freq_robust.py 第五道闸的 7 步网格
ORDER = ["强势", "震荡", "弱势", "破位"]
BOOT = 2000                               # 与 _freq_robust 固定 2000 一致
SEED = 20261010                           # 固定种子（与 _freq_robust 一致，幂等）
R3_MIN = 95.0                             # 百分数阈值（_freq_robust 的 min_r3>=95.0）


def _mean(v):
    return sum(v) / len(v) if v else 0.0


def one_group(rows, tops, elab, ds_used, step):
    """给定一组信号日，算四档：绝对均收益 + 其 R3 + 相对同日全票的 edge + 其 R3。

    口径与 _env_gate_lab.py 完全对齐：
      * 绝对口径（决定开仓/空仓）：该档所有 top 笔 pnl 池化均值 —— 绝对亏钱即该空仓。
      * 相对口径（决定选股有无 alpha）：策略前5% − 同日全票，逐日平衡。
    两个口径的 R3 都用**按日移动块 bootstrap**（块长覆盖前推窗口，处理窗口重叠）。
    """
    byd = defaultdict(list)
    for r in rows:
        byd[r["date"]].append(r)
    edge_pairs, abs_pairs = [], []
    for d in sorted(set(ds_used) & set(tops)):
        a = [r["pnl"] for r in tops[d]]
        b = [r["pnl"] for r in byd[d]]
        if a and b:
            edge_pairs.append((d, _mean(a) - _mean(b)))
            abs_pairs.append((d, _mean(a)))
    L = SENS.blk_len(step)
    out = {}
    for lab in ORDER:
        ep = [(d, v) for d, v in edge_pairs if elab[d] == lab]
        ap = [(d, v) for d, v in abs_pairs if elab[d] == lab]
        if not ap:
            continue
        # 绝对口径
        am = _mean([v for _, v in ap])
        _, alo, ahi, ar3 = SENS.block_boot(ap, L=L, boot=BOOT, seed=SEED)
        # 相对口径
        em = _mean([v for _, v in ep]) if ep else 0.0
        _, elo, ehi, er3 = SENS.block_boot(ep, L=L, boot=BOOT, seed=SEED) if ep else (0, 0, 0, 0)
        # 留一法（绝对口径）：剔掉任一信号日后均值摆到哪
        lv = []
        for i in range(len(ap)):
            sub = ap[:i] + ap[i + 1:]
            lv.append(_mean([v for _, v in sub]))
        out[lab] = {"n": len(ap), "abs_mean": am, "abs_ci": (alo, ahi), "abs_r3": ar3 * 100,
                    "rel_edge": em, "rel_ci": (elo, ehi), "rel_r3": er3 * 100,
                    "loo": (min(lv), max(lv)) if lv else (0.0, 0.0),
                    "n_bet": sum(len(tops[d]) for d in {dd for dd, _ in ap})}
    return out, len(edge_pairs)


def flips(vals):
    """符号翻转次数（相邻异号计数）。"""
    c = 0
    for a, b in zip(vals, vals[1:]):
        if a * b < 0:
            c += 1
    return c


def main(argv=None):
    import argparse as _ap
    _p = _ap.ArgumentParser(add_help=False)
    _p.add_argument("--mode", default="legacy", choices=("legacy", "realistic"))
    _cli, _unk = _p.parse_known_args(argv if argv is not None else sys.argv[1:])
    mode = getattr(_cli, "mode", "legacy") if hasattr(_cli, "mode") else "legacy"
    global OUT, OUT_JSON
    if mode == "realistic":
        OUT = os.path.join(ROOT, "web", "selected", "env_gate_freq_realistic.html")
        OUT_JSON = os.path.join(QUANT, "_env_gate_freq_realistic.json")
    G.AUDIT_MODE = mode
    random.seed(SEED)
    print("[egf] 成交假设口径 = %s" % ("可实现（保守日内 + 跳空按开盘价成交）" if mode == "realistic"
                                   else "旧乐观（同根K先冲高后回落 + 忽略跳空）"))
    print("[egf] 加载 _txk_cache.json（一次，派生 7 组步长共用）…")
    cache = _txk.load()
    try:
        nm = json.load(open(os.path.join(QUANT, "_stock_names.json"), encoding="utf-8"))
    except Exception:
        nm = {}
    rows, ds, esc, elab, ehas_core, tops, top_rows, _, _ = G.build(
        step_dates=BASE_STEP, cache=cache, nm=nm)
    print("[egf] 密扫描 step=%d：%d 行 / %d 个信号日 / 真选股层 %d 行"
          % (BASE_STEP, len(rows), len(ds), len(top_rows)))

    groups = {}
    for s in STEPS:
        ds_used = ds[::s]
        st, nper = one_group(rows, tops, elab, ds_used, s)
        key = "step%d" % s
        groups[key] = {"step": s, "n_signal": len(ds_used), "n_used": nper,
                       "days": {l: st[l]["n"] for l in ORDER if l in st}, "stat": st}
        print("[egf] %-7s 信号日 %3d / 有效 %3d ｜ %s"
              % (key, len(ds_used), nper,
                 " ".join("%s%d日 绝对%+.2f%% R3%.0f%%" % (l, st[l]["n"], st[l]["abs_mean"],
                                                          st[l]["abs_r3"])
                          for l in ORDER if l in st)))

    # ---- 三判据（仅对强势开仓档）----
    sg = {s: groups["step%d" % s]["stat"].get("强势") for s in STEPS if "强势" in groups["step%d" % s]["stat"]}
    steps_have = sorted(sg)
    abs_means = [sg[s]["abs_mean"] for s in steps_have]
    abs_r3s = [sg[s]["abs_r3"] for s in steps_have]
    rel_edges = [sg[s]["rel_edge"] for s in steps_have]
    cr1 = all(v > 0 for v in abs_means)           # 7 步绝对收益全 > 0
    cr2 = all(v >= R3_MIN for v in abs_r3s)        # 7 步 R3 全 ≥ 95%
    cr3 = all(v > 0 for v in rel_edges)            # 7 步相对 edge 全 > 0
    n_flip = flips(abs_means)
    cr1 = cr1 and (n_flip == 0)
    verdict_pass = cr1 and cr2 and cr3

    judge = {
        "steps_have": steps_have,
        "abs_means": {str(s): sg[s]["abs_mean"] for s in steps_have},
        "abs_r3": {str(s): round(sg[s]["abs_r3"], 1) for s in steps_have},
        "rel_edges": {str(s): round(sg[s]["rel_edge"], 4) for s in steps_have},
        "flips": n_flip,
        "cr1_sign": bool(all(v > 0 for v in abs_means)),
        "cr1_flips0": bool(n_flip == 0),
        "cr2_r3": bool(all(v >= R3_MIN for v in abs_r3s)),
        "cr3_rel_edge": bool(all(v > 0 for v in rel_edges)),
        "pass": bool(verdict_pass),
        "r3_min": R3_MIN,
    }

    res = {"base_step": BASE_STEP, "steps": STEPS, "groups": groups,
           "n_rows": len(rows), "n_signal": len(ds), "boot": BOOT, "seed": SEED,
           "mode": mode, "judge": judge}
    json.dump(res, open(OUT_JSON, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1, sort_keys=True, default=str)
    print("[egf] 落 %s ｜ 三判据 cr1=%s cr2=%s cr3=%s → PASS=%s"
          % (OUT_JSON, judge["cr1_sign"] and judge["cr1_flips0"], judge["cr2_r3"],
             judge["cr3_rel_edge"], verdict_pass))
    render(res)
    return res


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
.wrap{max-width:1040px;margin:0 auto;padding:26px 18px 56px}
h1{font-size:23px;font-weight:700;margin:0 0 6px;letter-spacing:-.02em}
h2{font-size:18px;font-weight:600;margin:28px 0 12px;padding-bottom:8px;border-bottom:2px solid var(--blue)}
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
.up{color:var(--up)}.dn{color:var(--dn)}
.note{font-size:12.5px;color:var(--muted);margin-top:8px}
.foot{text-align:center;color:var(--muted);font-size:12px;margin-top:26px}
</style>"""


def render(res):
    gs = res["groups"]
    j = res["judge"]
    o = []
    A = o.append
    A("<!DOCTYPE html><html lang='zh-CN'><head><meta charset='utf-8'>")
    A("<meta name='viewport' content='width=device-width,initial-scale=1'>")
    A("<title>主升精选 · 环境门控跨采样频率稳健性（严判据）</title>%s</head><body><div class='wrap'>" % CSS)
    A("<h1>主升精选 · 环境门控「跨采样频率稳健性」严扫</h1>")
    A("<div class='sub'>一次密扫描 step=%d（%d 行 / %d 信号日）→ 派生 %d 组步长 %s。"
      "横截面分位日内计算，抽子集与直接扫严格同结果。显著性 = 按日移动块 bootstrap %d 次（种子 %d 固定）。"
      "口径对齐 env_gate.html（composite = 0.45×指数分 + 0.55×画像 core，无未来函数）。"
      "成交假设口径：<b>%s</b>。本页只检验、不改生产。</div>"
      % (res["base_step"], res["n_rows"], res["n_signal"], len(res["steps"]),
         "／".join("step%d" % s for s in res["steps"]), res["boot"], res["seed"],
         "可实现（保守日内 + 跳空按开盘价成交）" if res.get("mode") == "realistic"
         else "旧乐观（同根K先冲高后回落 + 忽略跳空）"))

    # 主结论
    if j["pass"]:
        A("<div class='box green'><b>结论：PASS —— 环境门控（强势开仓、其余空仓）在 %d 组采样频率下稳健。</b><br>"
          "三判据全满足：① 强势档绝对均收益 7 步全 &gt; 0 且符号翻转 %d 次；"
          "② 7 步绝对收益 R3 全 ≥ %.0f%%；③ 7 步相对同日全票 edge 全 &gt; 0（选股层确有 alpha）。"
          "门控的 +2.443pp alpha 不是某个采样步长的巧合，可保留。</div>"
          % (len(j["steps_have"]), j["flips"], j["r3_min"]))
    else:
        A("<div class='box red'><b>结论：不通过 —— 环境门控在部分采样频率下未达严判据。</b><br>"
          "cr1 符号一致(全&gt;0且翻转0)：%s ｜ cr2 R3≥%.0f%%：%s ｜ cr3 相对edge全&gt;0：%s。"
          "按「判据必须跨窗口/跨步长一致、禁按最好看的窗口判」的红线，门控须降级为「不可判」或收紧，"
          "不得只挑 step=5 那一格当作证据。</div>"
          % (j["cr1_sign"] and j["cr1_flips0"], j["r3_min"], j["cr2_r3"], j["cr3_rel_edge"]))

    # 三判据明细
    A("<h2>三判据明细（仅对强势开仓档）</h2>")
    A("<table><tr><th>判据</th><th>要求</th><th>实测</th><th>结果</th></tr>")
    A("<tr><td>cr1 符号一致</td><td>7 步绝对均收益全 &gt; 0 且翻转 0 次</td>"
      "<td>翻转 %d 次；轨迹 %s</td><td><b>%s</b></td></tr>"
      % (j["flips"], " → ".join("%+.2f%%" % j["abs_means"][str(s)] for s in j["steps_have"]),
         "通过" if (j["cr1_sign"] and j["cr1_flips0"]) else "不通过"))
    A("<tr><td>cr2 绝对收益 R3</td><td>7 步全 ≥ %.0f%%</td><td>%s</td><td><b>%s</b></td></tr>"
      % (j["r3_min"], " ／ ".join("step%d %.0f%%" % (s, j["abs_r3"][str(s)]) for s in j["steps_have"]),
         "通过" if j["cr2_r3"] else "不通过"))
    A("<tr><td>cr3 选股 alpha</td><td>7 步相对同日全票 edge 全 &gt; 0</td>"
      "<td>%s</td><td><b>%s</b></td></tr>"
      % (" ／ ".join("step%d %+.3f" % (s, j["rel_edges"][str(s)]) for s in j["steps_have"]),
         "通过" if j["cr3_rel_edge"] else "不通过"))
    A("</table>")

    # 主表：每步每档
    A("<h2>逐步长 · 逐档明细</h2>")
    for s in res["steps"]:
        key = "step%d" % s
        g = gs.get(key)
        if not g:
            continue
        A("<h2 style='font-size:16px'>步长 %d 日（%d 信号日 / 有效 %d 日）</h2>" % (s, g["n_signal"], g["n_used"]))
        A("<table><tr><th>环境档</th><th>信号日</th><th>笔数</th>"
          "<th>绝对均收益</th><th>绝对 R3</th><th>相对 edge</th><th>相对 R3</th>"
          "<th>留一法(绝对)</th><th>判定</th></tr>")
        for lab in ORDER:
            st = g["stat"].get(lab)
            if not st:
                continue
            if lab == "强势":
                okabs = st["abs_mean"] > 0 and st["abs_r3"] >= j["r3_min"]
                okrel = st["rel_edge"] > 0
                tag = ("✅开仓" if (okabs and okrel) else
                       "⚠️不稳" if st["abs_mean"] > 0 else "❌空仓")
            else:
                tag = ("空仓" if st["abs_mean"] <= 0 else "开仓?")
            A("<tr><td>%s</td><td class='num'>%d</td><td class='num'>%d</td>"
              "<td class='num %s'><b>%+.2f%%</b></td><td class='num'>%.0f%%</td>"
              "<td class='num'>%+.3f</td><td class='num'>%.0f%%</td>"
              "<td class='num'>[%+.2f, %+.2f]</td><td>%s</td></tr>"
              % (lab, st["n"], st["n_bet"],
                 "up" if st["abs_mean"] > 0 else "dn", st["abs_mean"], st["abs_r3"],
                 st["rel_edge"], st["rel_r3"], st["loo"][0], st["loo"][1], tag))
        A("</table>")
        A("<div class='note'>绝对均收益 &gt; 0 且 R3 ≥ %.0f%% = 该档可开仓；"
          "否则数据指向空仓。相对 edge = 策略前5%% − 同日全票（选股层 alpha，只说明选股有无用、不定出手）。</div>"
          % j["r3_min"])

    # 与 sens 页交叉
    A("<h2>与样本量敏感性页（env_gate_sens.html）的关系</h2>")
    A("<div class='card'><div class='kv'>env_gate_sens.html 是宽松版（只判符号是否同号，扫 step 3/5/6/9）；"
      "本页是严版（edge&gt;0 + R3≥95%% + 0 翻转，扫 %s）。两页结论应一致："
      "sens 页判「强势开仓跨步长稳定为正、弱势空仓稳定为负、震荡/破位翻转不可判」，"
      "本页用更严的 R3 门槛再验一次。若本页也 PASS，门控的证据强度高于 sens 页的「稳定为正」。</div></div>"
      % "／".join("step%d" % s for s in res["steps"]))

    A("<h2>局限</h2><div class='card'><ul>")
    A("<li>派生子集与直接扫描同结果，前提是横截面分位只在该信号日内计算（本项目满足）。</li>")
    A("<li>step=20 的强势档样本仅个位数信号日，其 R3 由极少块构成，可信度低——若 step=20 一项不达标，"
      "应判为「长步长样本不足、不可判」，而非「门控失效」。短中步长（1~10）全过即可视为稳健。</li>")
    A("<li>退出模拟走 legacy 乐观口径（与生产头条 +2.443pp 同口径）；可实现口径已在 env_gate.html 第七节验证强势仍成立。</li>")
    A("<li>本页只检验、不改生产；门控是否保留由 env_gate.html 证据决定。结果落 <code>quant/_env_gate_freq.json</code>。</li>")
    A("</ul></div>")
    A("<div class='foot'>主升精选 · 环境门控跨采样频率稳健性（严判据）｜ 无未来函数</div>")
    A("</div></body></html>")

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    open(OUT, "w", encoding="utf-8").write("\n".join(o))
    print("[egf] 写 %s" % OUT)


if __name__ == "__main__":
    main()
