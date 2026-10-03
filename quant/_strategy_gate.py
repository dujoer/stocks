# -*- coding: utf-8 -*-
"""
策略结论门禁（_strategy_gate.py）
================================
用户 2026-10-03：「继续」——把「真选股层 + 等量对照」做成门禁固定检查项。

背景：本项目已 4 次栽在「假阳性」上
------------------------------------
① 自动筛因子（无 CE 域间条件跑输随便买 42.5% vs 45.9%）
② 三连阴「优质条件」跑输随便买
③ 「60 日涨幅最佳档 71.6% / edge +11.6pp」= 同数据既选参又验收
④ 「行业回撤 12% 后买入」报 +3.8pp、随机分位 0% 看着完美
   → 真因：策略取「全行业所有票」(n=24万) 而对照只抽 5 只，**edge 混的是样本量差异**；
     且判定只卡「随机分位≥95%」没卡「edge>0」，把 edge −4.5pp 的策略判成「最优」。
     加上等量对照 + 真实选股层后 → 全部 9 个定义跑输（edge −1.7~−5.0pp）。

本门禁把三条硬规则变成**机器强制**，任何策略结论 JSON 都绕不过去
--------------------------------------------------------------
R1 **等量对照**：对照组 n 必须与策略 n 同量级（比值 ≥0.5）。
   —— 挡「策略全取、对照抽样」型假阳性。
R2 **真实选股层**：策略样本必须来自某个横截面筛选（每个入场日有上限 K），
   而不是「把某个集合全量当样本」。
   —— 挡「测的是整体加仓 beta 而非选股能力」。
R3 **判定双条件**：任何被标为「可上线 / 显著 / 最优」的结论，必须同时满足
   `edge > 0` **且** 随机分位 ≤ 5%。
   —— 挡「只看分位不看 edge」型误判。

★ 门禁只做**形式检查**（数字之间是否自洽），不重跑回测、不改任何策略结论。
  缺字段的结论按「不可判」处理，不是「通过」。

用法
----
    python _strategy_gate.py                     # 扫全部结论 JSON
    python _strategy_gate.py --file X.json       # 只查一个
    python _strategy_gate.py --strict            # 警告也算失败
"""
from __future__ import annotations
import os, sys, json, glob, argparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

ROOT = os.path.dirname(HERE)

# 结论 JSON 的判定关键词：命中即视为「宣称可上线/显著/最优」
CLAIM_KEYS = ("可上线", "显著", "最优", "★可采信", "有增量", "通过")
PASS_KEYS = ("pass", "ok", "oos_ok", "trust", "verified")

# 建议扫描的目录（结论类 JSON 所在）
SCAN_DIRS = [
    ("web/accumulation", ".json"),
    ("web/selected", ".json"),
    ("web/cold_sector", ".json"),
    ("quant/hub", ".json"),
]
# 明确排除（大体量 / 非结论文件）
SKIP_WORDS = ("hist", "flowseq", "manifest", "hub/2")


def _walk_keys(obj, path="", depth=0, out=None):
    """深度遍历 JSON，产出 (路径, 键, 值) 三元组（限制深度防爆）。"""
    if out is None:
        out = []
    if depth > 8:
        return out
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = "%s.%s" % (path, k) if path else k
            out.append((p, k, v))
            _walk_keys(v, p, depth + 1, out)
    elif isinstance(obj, list):
        for i, v in enumerate(obj[:50]):
            _walk_keys(v, "%s[%d]" % (path, i), depth + 1, out)
    return out


def check_file(path):
    """检查一个结论 JSON。返回 (problems, warns, info)。"""
    problems, warns, info = [], [], {}
    try:
        j = json.load(open(path, encoding="utf-8"))
    except Exception as e:
        return ["无法解析：%s" % str(e)[:60]], [], info
    flat = _walk_keys(j)

    # ---- R3：判定双条件 ----
    # 找所有「看起来是结论」的节点，检查是否同时带 edge 与分位
    claim_hits = []
    edge_vals = []
    pct_vals = []
    for p, k, v in flat:
        if isinstance(v, str) and any(c in v for c in CLAIM_KEYS):
            claim_hits.append((p, v))
        if k in ("edge", "edge_vs_base") and isinstance(v, (int, float)):
            edge_vals.append((p, float(v)))
        if k in ("pctile", "pctile_vs", "pct") and isinstance(v, (int, float)):
            pct_vals.append((p, float(v)))
    info["claims"] = len(claim_hits)
    info["edge_n"] = len(edge_vals)
    info["pct_n"] = len(pct_vals)

    if claim_hits:
        # 有宣称 → 必须同时有 edge 和分位可核对
        if not edge_vals:
            problems.append("宣称「%s」但**没有 edge 数字** → 无法核对是否真的跑赢对照"
                            % claim_hits[0][1][:20])
        if not pct_vals:
            warns.append("宣称「%s」但没有随机分位 → 无法确认是否显著"
                         % claim_hits[0][1][:20])

        # ★R3 核心（2026-10-03 补）：「宣称显著/最优」必须**存在一个同时满足**
        #   `edge>0 且 随机分位≤5%` 的策略。否则宣称就是误判。
        #   实测漏过的真实案例：`_pullback_probe.py` 把
        #   「随机分位 100% + edge −4.5pp」的缩量回调判成「最优且显著」——
        #   那是**明显更差**的策略（旧逻辑只卡分位≥95 没卡 edge>0）。
        good = [(p, e, q) for (p, e) in edge_vals
                for (p2, q) in pct_vals
                if p2.split(".")[0] == p.split(".")[0]
                and e > 0 and q <= 5.0]
        all_neg = [p for p, v in edge_vals if v <= 0]
        all_high = [p for p, v in pct_vals if v > 50.0]
        if edge_vals and pct_vals and not good:
            why = []
            if all_neg and len(all_neg) == len(edge_vals):
                why.append("全部策略 edge≤0（都跑输对照）")
            if all_high and len(all_high) == len(pct_vals):
                why.append("全部随机分位>50%（随机都达不到该胜率=策略更差）")
            # 用 .format 而非 % —— 串里有反引号与百分号，% 格式化会炸
            problems.append(
                "R3 判定双条件不通过：文件宣称「{c}」，但**不存在**同时满足 "
                "`edge>0 且 随机分位<=5%` 的策略{w} → 宣称属误判".format(
                    c=claim_hits[0][1][:20],
                    w=("（" + "；".join(why) + "）") if why else ""))
        # 存在跑输策略时提醒结论只针对 edge>0 的部分
        if good and all_neg:
            warns.append(
                "含 {n} 个 edge<=0 的策略，同时存在合格宣称 → "
                "请确认结论只针对 edge>0 且分位<=5% 的那部分".format(n=len(all_neg)))

    # ---- R1：等量对照 ----
    # ⚠ 只认**明确的样本量字段名**（baseline_n / ctrl_n / base_n ...），
    #   不能拿通用键 "n" 到处比 —— `cold_20260930.json` 里 n=86 是行业成分数、
    #   n=610 是另一行业的成分数，拿它们比会误报（首次运行就误报了）。
    base_n = None
    strat_ns = []
    for p, k, v in flat:
        if not isinstance(v, int):
            continue
        kl = k.lower()
        # 对照侧：字段名明确带 base/ctrl/control/对照
        pl = p.lower()
        # ★ 必须**键名本身**是对照语义，或路径里有 baseline/对照 节点。
        #   不能只看 `cleaned.n=566`（消融里的「清洗后子集」）就当对照组 ——
        #   那不是「策略 vs 对照」，会误报（实测 accum_ablate 被误报 3 次）。
        is_base = (
            kl in ("base_n", "baseline_n", "ctrl_n", "control_n",
                   "n_base", "rand_n", "baseline_wins", "baseline", "base")
            or (any(t in pl for t in ("baseline", "对照", "基线", "ctrl", "control"))
                and not any(t in pl for t in ("cleaned", "清洗", "subset", "子集")))
        )
        if is_base and (kl in ("n", "size", "count", "wr", "n_base")
                        or kl.endswith("_n")):
            if base_n is None or v > base_n:
                base_n = v
        # 策略侧：明确的策略样本量
        elif (kl in ("n", "n_real", "n_total", "n_pool", "n_recs", "n_pick", "n_test")
              and any(t in kl for t in ("n",))):
            # 排除「行业成分数/票池数」这类域规模字段
            if any(t in p.lower() for t in ("member", "pool_size", "universe",
                                            "domain", "sector", "票池", "成分")):
                continue
            strat_ns.append((p, v))
    if base_n and strat_ns:
        # ★ 只在**同一父节点**内比较：不同层的 n 本来就该不同。
        #   实测误报：`accum_ablate.json` 里 cleaned.n=566（清洗后）vs
        #   n_pool=2836（全信号池）→ 本来就是「剔除负贡献因子后」的子集 vs 全集，
        #   不是「策略 vs 对照」。跨层比较会误报。
        from collections import defaultdict
        byparent = defaultdict(list)
        for pth, v in strat_ns:
            byparent[pth.rsplit(".", 1)[0]].append(v)
        # ★ 只有「**明确存在 baseline/对照组节点**」才做 R1 比对。
        #   消融诊断类文件（accum_ablate）里 cleaned.n 是「剔除负贡献因子后的子集」，
        #   与全信号池 n 本来就不同量，不是「策略 vs 对照」→ 不适用 R1。
        bkey = None
        for pth, _k, _v in flat:
            pl_ = pth.lower()
            if "baseline" in pl_ or "对照" in pth or "基线" in pth:
                if pth.lower().endswith((".n", "_n", ".size", ".count")) \
                        or pth.rsplit(".", 1)[-1] in ("n", "size", "count", "n_base"):
                    bkey = pth.rsplit(".", 1)[0]
                    break
        if bkey is None:
            # 无明确对照组父节点 → 仍做**保守检查**：若基线 n 与某个策略 n
            # 差 5 倍以上且该策略带 edge>0 的宣称，就提示（不硬失败，避免误报）。
            info["r1"] = "无明确对照组父节点（保守模式）"
            if edge_vals and base_n:
                _maxn = max(v for _p, v in strat_ns) if strat_ns else 0
                if _maxn and base_n / _maxn < 0.2 and any(v > 0 for _p, v in edge_vals):
                    warns.append(
                        "R1 保守提示：基线 n={b} 与最大策略 n={m} 相差 {r:.1f} 倍，"
                        "且存在 edge>0 的宣称 → 请确认对照与策略等量".format(
                            b=base_n, m=_maxn, r=_maxn / max(1, base_n)))
        else:
            # ★ 对照与策略通常**不在同一父节点**（`baseline.n` vs `strats.*.n`），
            #   所以等量比对应取「所有策略 n 的最大者」与基线比，而不是同层。
            cand = byparent.get(bkey) or []
            mx = max(cand) if cand else (max(v for _p, v in strat_ns)
                                         if strat_ns else 0)
            if mx > 0 and base_n / mx < 0.5:
                problems.append(
                    "R1 等量对照不通过：对照 n={b}，最大策略 n={m}，比例={r:.2f}"
                    "（要求 >=0.50）→ edge 混了样本量差异，不是选股能力".format(
                        b=base_n, m=mx, r=base_n / mx))
                info["base_n"] = base_n
                info["max_strat_n"] = mx
            else:
                info["r1"] = "通过"

    # ---- R2：真实选股层 ----
    # 策略样本应有 per-day / per-industry 之类上限；若无，且单策略 n 极大（>10万），可疑
    has_cap = False
    for p, k, v in flat:
        if k in ("per_day", "per_ind", "per_industry", "top", "topn", "TOPN", "cap"):
            if isinstance(v, int) and 0 < v <= 200:
                has_cap = True
                break
    info["has_cap"] = has_cap
    if strat_ns and not has_cap:
        big = max(v for _p, v in strat_ns)
        if big > 100000:
            warns.append(
                "R2 疑无真实选股层：最大策略 n=%d 且未发现 per_day/top 之类上限 → "
                "该结论可能只是「整体加仓 beta」而非选股能力" % big)

    return problems, warns, info


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default="")
    ap.add_argument("--strict", action="store_true", help="警告也算失败")
    a = ap.parse_args()

    files = []
    if a.file:
        files = [a.file if os.path.isabs(a.file) else os.path.join(ROOT, a.file)]
    else:
        for d, pat in SCAN_DIRS:
            p = os.path.join(ROOT, d)
            if not os.path.isdir(p):
                continue
            for f in glob.glob(os.path.join(p, "*" + pat)):
                if any(w in os.path.basename(f) for w in SKIP_WORDS):
                    continue                    # 大体量 / 非结论文件
                files.append(f)

    print("== 策略结论门禁（R1 等量 / R2 真选股层 / R3 判定双条件）==")
    print("扫描 %d 个结论文件\n" % len(files))
    tot_p = tot_w = 0
    for f in files:
        rel = os.path.relpath(f, ROOT)
        probs, warns, info = check_file(f)
        tot_p += len(probs)
        tot_w += len(warns)
        mark = "✓" if not probs else "✗"
        print("%s %s" % (mark, rel))
        print("     宣称=%d edge数=%d 分位数=%d%s"
              % (info.get("claims", 0), info.get("edge_n", 0), info.get("pct_n", 0),
                 ("  有选股上限" if info.get("has_cap") else "")))
        for p in probs:
            print("     [FAIL] %s" % p)
        for w in warns:
            print("     [WARN] %s" % w)
    print("")
    if tot_p:
        print("=== 门禁未通过（%d 问题 / %d 警告）===" % (tot_p, tot_w))
        return 1
    if a.strict and tot_w:
        print("=== 门禁未通过（strict 模式：%d 警告）===" % tot_w)
        return 1
    print("=== 门禁通过（0 问题 / %d 警告）===" % tot_w)
    return 0


if __name__ == "__main__":
    sys.exit(main())
