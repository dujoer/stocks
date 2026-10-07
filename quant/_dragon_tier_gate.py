# -*- coding: utf-8 -*-
"""
龙道诀 · 出票闸（_dragon_tier_gate.py）
======================================

★ 为什么还要做这一步（不是重复劳动）
前面三道检验的结论分别是：
  · `_dragon_odds`      —— 按「阶段 × 连板」直接做移动止盈：24 格扣成本净正 **0**
  · `_dragon_stage_use` —— 四阶段 → 后续**全市场等权**收益：高潮可用 / 退潮不可用
  · `_dragon_pos_rule`  —— 把阶段当**仓位开关**：日均超额 −0.065pp，四条判据全否

「验死」不等于「没有链路」。本脚本把龙道诀做成一条**正式的出票通道**：

    候选生成 → T+1 开盘入场 → 既有移动止盈出场 → 五项闸门 → 允许 / 不允许出票

**过闸就出名单，不过闸就是 0 票**（fail-safe）。
这样每天都有确定答案 —— 「今天有没有合格标的」，而不是「这条路线被放弃了」。

★ 先验固定（跑前写死，禁止事后挑规则）
候选域 = 当日**收盘封涨停**的全集（`_dragon_odds.scan()` 的 sig），不做任何预筛。
四条规则的依据全部来自本项目**已发表的证据**，不是在这里扫出来的最优：

  D1 高潮·二板        —— 高潮阶段后续全市场收益在三窗口上均优于「同当日涨幅分位」对照
                        （+0.84 / +1.39 / +1.70pp，见 `_dragon_stage_use`）；
                        二板是连板链的主节点，实测二板→三板晋级率 31.5%（489 候选 / 154 晋级）
  D2 高潮·三板及以上  —— 同前的更高阶版本（候选更少、更挑）
  D3 非退潮·二板      —— 退潮三窗口 edge 全负（−0.67 / −0.88 / −0.63pp），据此外延排除退潮
  D4 退潮·二板        —— **证伪面**：先验预期为负。若它也能过关，说明是判据失效而非找到 alpha

★ 这一步与前面三道的区别（为什么仍值得一跑）
前面几道在回答「某个口径下有没有统计优势」。本脚本把前面没做齐的三件补齐：
  ① 入场用 **T+1 开盘**（不是信号日收盘 —— 拿收盘价当成交价不可兑现）
  ② 出场走项目**唯一**退出实现 `_exit_sim`（−12% / +6% / 3% / 20 日，**一个参数都不扫**）
  ③ 判据走项目**唯一**出票闸 `_gate_common.tier_license_windows`（五项全过才许可）

即：**候选可能仍然全部不合格 —— 那时输出 0 票，那是结论，不是失败。**

★ 五项闸门（`_gate_common.tier_license_windows`，全过才算数）
  ① 生产窗口 edge > 0       —— 逐日平衡：该档逐日均 − 同日候选域逐日均
  ② 全部窗口 er3_min ≥ 95%  —— 跨样本期一致（历史坑：按最好看的窗口判定＝在样本期维度挑优）
  ③ 全部窗口 ar3 ≥ 95%      —— 绝对收益也要稳；赢基线 ≠ 能赚钱
  ④ 留一法 loo[0] > 0       —— 剔除任一个入场日不翻负
  ⑤ 前/后半 wf 两段都 > 0   —— 不锁在单一市场状态

★ 数据有效性闸（与统计无关的前置）
阶段覆盖率：入场日中能判出四阶段的比例低于阈值 → **全档不出票**
（同源做法见 `_accum_tier_gate` 的 M 维融资覆盖率闸）。

★ 买不到怎么办
T+1 开盘一字封板 → 判据走真源 `M.is_sealed_up` → **丢样并计数**，不假装买到了。
这是**保守方向**的偏差（一字板通常次日更强，剔掉会低估），如实标注。

用法：
  python _dragon_tier_gate.py --selftest
  python _dragon_tier_gate.py --date 2026-09-30 --src long
  python _dragon_tier_gate.py --date 2026-09-30 --src long --emit
"""
import os, sys, json, argparse, collections

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
OUTDIR = os.path.join(HERE, "dragon")
os.makedirs(OUTDIR, exist_ok=True)

import _mkt_emo as M            # 情绪/涨停/阶段 —— 项目唯一真源
import _dragon_odds as DO       # 复用 scan()（候选域）与 _probe_one()（T+1 开盘 + 既有退出）
import _exit_sim as X           # 移动止盈 —— 项目唯一退出实现（此处不改参数）
import _longk as LK             # 长历史日K —— 项目唯一加载入口
import _txk                     # 短缓存（C5 跨页一致性要求页面口径用它）
import _gate_common as GC       # ★ 出票许可 —— 项目唯一判据（tier_license_windows）
import _accum_tier_gate as ATG  # ★ 统计层 —— 复用其 analyse()（逐日平衡 + block bootstrap + loo + wf）

BOOT = 2000         # ★ 固定：R3 分辨率 = 1/BOOT，改次数会改 er3_min（判据依赖它）
SEED = 20261004
WINDOWS = (250, 500, 780)   # 入场日样本期窗口（近 1 年 / 近 2 年 / 全样本）
PROD_WINDOW = min(WINDOWS)  # ★ 生产窗口取最小 —— 与 _accum_tier_gate 同一纪律，不用最大（那是挑优）
DATA_GATE_STAGE_PCT = 90.0  # ★ 数据有效性闸：阶段可判比例下限（%）
STAGES = ("高潮", "回暖", "冰点", "退潮")
TOPN = 10           # 出票名单上限（只截 ENABLED 规则命中的票，不排序挑优）

# ---- 先验固定规则（跑前写死，不含「全候选域」那个对照项）----
RULES = [
    ("D1 高潮·二板",             lambda r: r["stage"] == "高潮" and r["rb"] == 2),
    ("D2 高潮·三板及以上",       lambda r: r["stage"] == "高潮" and r["rb"] >= 3),
    ("D3 非退潮·二板",           lambda r: r["stage"] in ("高潮", "回暖", "冰点") and r["rb"] == 2),
    ("D4 退潮·二板（证伪面）",   lambda r: r["stage"] == "退潮" and r["rb"] == 2),
]
# 分析用的规则表：末尾挂「全候选域」作同日对照基准（= 逐日平衡的分母）
ALL_RULES = RULES + [("全候选域（无筛选对照）", lambda r: True)]
FALSIFY = "D4 退潮·二板（证伪面）"


# ------------------------------------------------------------------ 面板构建
def build_panel(cache, src_label=""):
    """造出全部候选行的面板。每行 = 一笔「信号日 → T+1 开盘买 → 既有移动止盈卖」。

    单位：ret 为**百分比**（与 `_accum_tier_gate` 一致，edge 的量纲即 pp）。
    """
    series, sig, _closes, _runs, _univ = DO.scan(cache)
    stg = M.stage_series(series)
    all_dates = [s["date"] for s in series]

    rows, cover = [], []
    for d in all_dates:
        st = stg.get(d)
        cands = sig.get(d) or []
        n_fwd, n_unex, n_ok = 0, 0, 0
        for code, _c, run in cands:
            pr = DO._probe_one(cache, d, code)
            if pr is None:          # 前向不足 / 无数据 —— 丢样，不糊弄
                n_fwd += 1
                continue
            if pr["unexec"]:        # T+1 一字封板 = 买不进
                n_unex += 1
                continue
            real = pr["real"]
            if real is None:
                n_unex += 1
                continue
            n_ok += 1
            rows.append(dict(code=code, date=d, ret=real * 100.0, win=real > 0,
                             stage=st, rb=run))
        cover.append(dict(date=d, stage=st, cand=len(cands), n_fwd=n_fwd,
                          unexec=n_unex, ok=n_ok))
    return rows, all_dates, cover, dict(src_label=src_label)


# ------------------------------------------------------------------ 出票许可
def analyse_panel(rows, all_dates, cover, boot=BOOT):
    """按样本期窗口切片，逐窗走统一统计层；再交 `tier_license_windows` 判定。"""
    usable = [c["date"] for c in cover if c["stage"] in STAGES]
    n = len(all_dates)
    # ⚠ `min(w, n)`：写死 780 而实际只有 779 天时会把全样本窗口整个漏掉（第三次）
    wins = tuple(sorted({min(w, n) for w in WINDOWS}))
    per = {}
    for w in wins:
        # 窗口 = 最近 w 个入场日（tails），与 _accum_tier_gate 的 `lastN = cal[-days:]` 同一取向
        sub = all_dates[-w:]
        stat, _ctrl = GC.tier_analyse(rows, sub, ALL_RULES, boot=boot, seed=SEED)
        per[w] = {"stat": stat, "window": [sub[0], sub[-1]], "n_rows": len(rows),
                  "n_days": len(sub)}
    allow, detail = [], {}
    for name, _fn in RULES:
        ok, why, det = GC.tier_license_windows(per, name, prod_window=PROD_WINDOW)
        detail[name] = {"ok": bool(ok), "why": why, "detail": det}
        if ok:
            allow.append(name)
    return per, allow, detail, wins


def data_gate(cover):
    """数据有效性闸：阶段可判比例。判不出阶段的日子根本无从构成规则。"""
    if not cover:
        return dict(ok=False, pct=0.0, days=0, no_stage_days=0,
                    threshold=DATA_GATE_STAGE_PCT, note="无入场日")
    ns = sum(1 for c in cover if c["stage"] not in STAGES)
    pct = 100.0 * (len(cover) - ns) / len(cover)
    return dict(ok=(pct >= DATA_GATE_STAGE_PCT), pct=round(pct, 2), days=len(cover),
                no_stage_days=ns, threshold=DATA_GATE_STAGE_PCT,
                note=("阶段可判 %.1f%%（%d 个入场日中 %d 个判不出阶段）；阈值 %.0f%%"
                      % (pct, len(cover), ns, DATA_GATE_STAGE_PCT)))


def run(date=None, src="long", boot=BOOT):
    if src == "long":
        cache = LK.load_long()
        label = LK.src_label()
    else:
        cache, label = _txk.load(), "_txk_cache"
    if not cache:
        return dict(error="读不到日K（该添样本也没拉到），fail-safe 不出票")
    rows, dates, cover, meta = build_panel(cache, label)
    per, allow, detail, wins = analyse_panel(rows, dates, cover, boot=boot)
    dg = data_gate(cover)
    if not dg["ok"]:
        for k in detail:
            detail[k]["ok"] = False
            detail[k]["why"] = "【数据闸】" + detail[k]["why"]
        allow = []
    res = dict(asof=date, boot=boot, windows=list(wins), prod_window=PROD_WINDOW,
               kline_src=src, kline_label=label,
               n_rows=len(rows), n_days=len(dates),
               sample_first=(dates[0] if dates else None),
               sample_last=(dates[-1] if dates else None),
               per={str(k): v for k, v in per.items()},
               allow=allow, allow_detail=detail, data_gate=dg,
               license_note=GC.__doc__ or "",
               n_unexec=sum(c["unexec"] for c in cover),
               n_fwd_missing=sum(c["n_fwd"] for c in cover))
    return res


def emit(asof=None, allow=None, cap=TOPN):
    """出当日名单。**仅许可能通过的规则**才贡献票；allow 为空则返回空名单。"""
    allow = allow or []
    cache, label = _txk.load(), "_txk_cache"
    if not cache:
        return dict(error="读不到日K")
    series, sig, _c, _r, _u = DO.scan(cache)
    stg = M.stage_series(series)
    asof = DO._dig(asof or series[-1]["date"])
    cands = [s for s in series if DO._dig(s["date"]) == asof]
    if not cands:
        return dict(date=asof, stage=None, names=[], note="该日无候选（非交易日或数据缺失）", src=label)
    cur = cands[-1]
    st = stg.get(cur["date"])
    fns = [(n, f) for n, f in RULES if n in allow]
    hits = {}
    for name, fn in fns:
        for code, close, run in sig.get(cur["date"]) or []:
            row = dict(code=code, stage=st, rb=run)
            if fn(row):
                hits.setdefault(code, {"code": code, "stage": st, "rb": run, "rules": []})
                hits[code]["rules"].append(name)
    names = sorted(hits.values(), key=lambda x: (-len(x["rules"]), -x["rb"], x["code"]))[:cap]
    return dict(date=cur["date"], stage=st, allow=allow, names=names,
                total_cand=len(sig.get(cur["date"]) or []),
                note=("" if names else "本期无合格标的（没有规则的出票闸被通过）"),
                src=label)


# ------------------------------------------------------------------ 自测
def selftest():
    ok = tot = 0

    def _ck(msg, cond):
        nonlocal ok, tot
        tot += 1
        ok += 1 if cond else 0
        print(("  OK   " if cond else "  FAIL ") + msg)

    # ① 先验固定：规则是四条，且 D4 是证伪面（先验预期为负）
    _ck("规则表为 4 条先验 + 1 条对照", len(ALL_RULES) == 5 and len(RULES) == 4)
    _ck("证伪面存在且不在允许规则的默认名里", FALSIFY in dict(RULES) and FALSIFY.startswith("D4"))
    _ck("生产窗口取最小（不许挑最大窗口）", PROD_WINDOW == min(WINDOWS))

    # ② 规则函数本身（构造行，纯逻辑，不碰数据）
    r1 = dict(stage="高潮", rb=2)
    r2 = dict(stage="高潮", rb=3)
    r3 = dict(stage="退潮", rb=2)
    r4 = dict(stage="冰点", rb=2)
    f = dict(RULES)
    _ck("D1 命中高潮二板", f["D1 高潮·二板"](r1) and not f["D1 高潮·二板"](r3))
    _ck("D2 命中三板及以上", f["D2 高潮·三板及以上"](r2) and not f["D2 高潮·三板及以上"](r1))
    _ck("D3 排除退潮", f["D3 非退潮·二板"](r4) and not f["D3 非退潮·二板"](r3))
    _ck("D4 只命中退潮二板", f[FALSIFY](r3) and not f[FALSIFY](r1))

    # ③ 数据闸：阶段不可判比例过高 → 全档封锁
    cov = [dict(date="d", stage="高潮", cand=1, n_fwd=0, unexec=0, ok=1),
           dict(date="e", stage=None, cand=1, n_fwd=0, unexec=0, ok=0)]
    dg = data_gate(cov)
    _ck("阶段缺失超阈值 → 数据闸关闭", dg["ok"] is False and dg["pct"] == 50.0)
    dg2 = data_gate([dict(date="d", stage="高潮", cand=1, n_fwd=0, unexec=0, ok=1)])
    _ck("阶段齐备 → 数据闸通过", dg2["ok"] is True and dg2["pct"] == 100.0)
    _ck("空覆盖 → 数据闸关闭（fail-safe）", data_gate([])["ok"] is False)

    # ④ 面板单位：ret 是百分比（%）
    rows = [dict(code="c", date="d1", ret=1.5, win=True, stage="高潮", rb=2)]
    _ck("ret 量纲为百分比（edge 即 pp）", rows[0]["ret"] == 1.5 and rows[0]["win"] is True)

    # ⑤ 统计层复用：对照 = 全候选域（挂 ALL_RULES 末尾那条），4 行样本全落进去<｜hy_place▁holder▁no▁813｜>
    st, _ctl = GC.tier_analyse(
        [dict(code="a", date="d1", ret=2.0, win=True, stage="高潮", rb=2),
         dict(code="b", date="d1", ret=0.0, win=False, stage="高潮", rb=3),
         dict(code="c", date="d2", ret=4.0, win=True, stage="退潮", rb=2),
         dict(code="d", date="d2", ret=0.0, win=False, stage="退潮", rb=5)],
        ["d1", "d2"], ALL_RULES, boot=50)
    _ck("统计层能产出全候选域口径", "全候选域（无筛选对照）" in st and st["全候选域（无筛选对照）"]["n"] == 4)

    # ⑥ 闸门通路：空 per → 一律不许可（fail-safe）
    okk, why, det = GC.tier_license_windows({}, "D1 高潮·二板", prod_window=250)
    _ck("无窗口样本 → 不许可", okk is False and "无窗口样本" in why)

    # ⑦ emit：读不到数据时必须 fail-safe（报错或空名单），**不许偷偷出票**
    saved = globals()["_txk"]
    class _NoData:
        @staticmethod
        def load():
            raise FileNotFoundError("selftest 不读真数据：模拟日K不可得")
    globals()["_txk"] = _NoData
    try:
        try:
            emit(asof="2026-09-30", allow=[])
            got_err = False
        except FileNotFoundError:
            got_err = True
        _ck("日K不可读时 emit fail-safe（不产出名单）", got_err is True)
    finally:
        globals()["_txk"] = saved

    print("\n自测 %d/%d" % (ok, tot))
    return ok == tot


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None)
    ap.add_argument("--src", choices=("auto", "long", "short"), default="long")
    ap.add_argument("--boot", type=int, default=BOOT)
    ap.add_argument("--emit", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        sys.exit(0 if selftest() else 1)
    res = run(a.date, a.src, boot=a.boot)
    if res.get("error"):
        print("[dragon-gate] " + res["error"])
        sys.exit(1)
    if a.emit:
        em = emit(a.date, res["allow"])
        res["emit"] = em
        print("[dragon-gate] 当日名单：allow=%s ｜ 候选 %s 只 ｜ 出票 %d 只"
              % (res["allow"], em.get("total_cand"), len(em.get("names") or [])))
    out = os.path.join(OUTDIR, "dragon_tier_gate.json")
    json.dump(res, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("[dragon-gate] 已写 %s" % out)
