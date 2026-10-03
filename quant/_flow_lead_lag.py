# -*- coding: utf-8 -*-
"""
资金流「领先 vs 滞后」判定（_flow_lead_lag.py）
==============================================
用户 2026-10-03：「继续」。

问题
----
`_selected_flow_probe.py` 发现「1 日主力强度分档与**当日**涨幅单调」，
但这**无法区分因果方向**：

    A. 资金流入 → 未来涨   （资金流是**领先**指标，可用于选股）
    B. 当天涨 → 资金流入   （资金流是**滞后**结果，只是涨幅的影子）

截面数据（同一时刻比 4971 只）两种情况会长得**一模一样**。
要区分，必须用**时间序列**：拿 T 日之前的资金流去预测 T+1 之后的涨跌。

做法（先验固定，不调参）
------------------------
对每个交易日 T（用序列里可得的最后 6 个交易日，避免样本重叠）：

  ① 取「T 日及之前 5 日累计净流入」= `cum5(T)`（**只用 T 之前的数据，防未来函数**）
  ② 按 `cum5(T)` 把全市场分 5 档
  ③ 算各档在 **T+1 ~ T+5** 的平均收益（来自 `_long_kline.json` 的日K）
  ④ 关键判据：看「**高资金流档**的次日收益是否 > **低资金流档**」

  - 若高 > 低 → 资金流**领先**，有预测力
  - 若高 ≈ 低 或反向 → 资金流只是涨幅的**滞后影子**，**不能进选股因子**

★ 同时算对照组：把 `cum5(T)` 换成「T 日之前的涨幅」，看涨幅本身的预测力。
  若资金流的预测力 ≈ 涨幅的预测力，说明前者没有**增量**信息。

方法论铁律（项目已栽三次的地方）
--------------------------------
- 只用 T 及之前的信息算因子，T+1 之后只用来算结果 —— 标准 walk-forward。
- **不扫参数**：`cum5` 的窗口 5 日、档位数 5、结果窗口 5 日，全部先验固定。
- 结果门槛：至少 6 个入场日、每档 n≥30，否则**判「不可判」而非「通过」**。
- 即便通过，也**只是「有增量信息」的必要条件**，还必须过 `_accum_oos.py`
  那套四道闸门（含移动止盈回测 + 随机对照）才允许进规则。

用法
----
    python _flow_lead_lag.py --date 2026-09-30
"""
from __future__ import annotations
import os, sys, json, argparse, collections, statistics

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import _datahub as DH

CUM_WIN = 5       # 累计窗口（交易日）— 先验固定
N_BUCKET = 5      # 分档数 — 先验固定
FWD_WIN = 5       # 结果窗口（交易日）— 先验固定
MIN_N = 30        # 每档最少样本
MIN_DAYS = 6      # 最少入场日数


def load_seq(date):
    """读资金流序列 → ({code: {date: val}}, span)。

    兼容两种布局：
      · col（2026-10-03 起）：`row_dates` 共用日期表 + `values[code] = [v...]`（省体积）
      · data（旧）：`data[code] = [[date, val], ...]`
    """
    p = os.path.join(DH.HUB, "flowseq_%s.json" % DH.DS(date))
    if not os.path.exists(p):
        return None, ""
    j = json.load(open(p, encoding="utf-8"))
    span = j.get("span", "")
    if j.get("layout") == "col":
        rd = j.get("row_dates") or []
        out = {}
        for c, arr in (j.get("values") or {}).items():
            m = {}
            for i, d in enumerate(rd):
                if i < len(arr) and arr[i] is not None:
                    m[d] = arr[i]
            if m:
                out[c] = m
        return out, span
    out = {}
    for c, v in (j.get("data") or {}).items():
        out[c] = {d: x for d, x in v}
    return out, span


def kline_map():
    p = os.path.join(HERE, "_long_kline.json")
    if not os.path.exists(p):
        p = os.path.join(HERE, "_txk_cache.json")
    return json.load(open(p, encoding="utf-8"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    a = ap.parse_args()

    seq, span = load_seq(a.date)
    if not seq:
        print("！无资金流序列，先跑 _datahub.py --date %s（会生成 flowseq_*.json）" % a.date)
        return
    kl = kline_map()
    print("[load] 资金流序列 %d 只，覆盖 %s | 日K %d 只" % (len(seq), span, len(kl)))

    # 交易日历（取出现最多次的日期序列）
    cal = collections.Counter()
    for m in seq.values():
        for d in m:          # m 是 {date: val}
            cal[d] += 1
    dates = sorted(d for d, c in cal.items() if c >= len(seq) * 0.3)
    print("[日历] 可用 %d 个交易日 %s ~ %s" % (len(dates), dates[0], dates[-1]))
    if len(dates) < CUM_WIN + FWD_WIN + MIN_DAYS:
        print("序列太短（%d 日），需 ≥%d 日" % (len(dates), CUM_WIN + FWD_WIN + MIN_DAYS))
        return

    # 入场日：留出 FWD_WIN 的结果窗口
    lo, hi = CUM_WIN, len(dates) - FWD_WIN
    entry = dates[lo:hi]
    # ★ 样本独立：入场日间隔 ≥ FWD_WIN，避免结果窗口重叠导致的有效样本数被高估
    step = FWD_WIN
    entry = entry[::step]
    print("[入场日] %d 个（间隔 %d 日避免重叠）: %s ~ %s"
          % (len(entry), step, entry[0], entry[-1]))
    if len(entry) < MIN_DAYS:
        print("入场日不足 %d → 判「不可判」" % MIN_DAYS)
        return

    # 预构建：每票的 date -> 净流入
    smap = seq        # load_seq 已返回 {code: {date: val}}

    def cum_before(c, T, win):
        """T 日**及之前** win 日累计净流入（严格不含 T 之后）。"""
        m = smap.get(c) or {}
        ds = [d for d in m if d <= T]
        ds.sort()
        sel = ds[-win:] if len(ds) >= win else ds
        if len(sel) < max(2, win // 2):
            return None
        return sum(m[d] for d in sel)

    def fwd_ret(c, T, win):
        """T 之后 win 日累计收益（用日K）。"""
        bars = kl.get(c)
        if not bars:
            return None
        idx = None
        for i, b in enumerate(bars):
            if b["date"] == T:
                idx = i
                break
        if idx is None:
            return None
        j = idx + win
        if j >= len(bars):
            return None
        p0, p1 = bars[idx]["last"], bars[j]["last"]
        if not p0 or p0 <= 0:
            return None
        return (p1 / p0 - 1.0) * 100.0

    def mom_before(c, T, win):
        """对照组：T 之前 win 日涨幅。"""
        bars = kl.get(c)
        if not bars:
            return None
        idx = None
        for i, b in enumerate(bars):
            if b["date"] == T:
                idx = i
                break
        if idx is None or idx - win < 0:
            return None
        p0, p1 = bars[idx - win]["last"], bars[idx]["last"]
        if not p0 or p0 <= 0:
            return None
        return (p1 / p0 - 1.0) * 100.0

    def run(factor, label, higher_better=True):
        """factor(c,T) -> 值 | None。返回 (逐档结果, 高档-低档差, 是否单调)。"""
        per_bucket = collections.defaultdict(list)
        used = 0
        for T in entry:
            vals = []
            for c in seq:
                v = factor(c, T)
                if v is None:
                    continue
                r = fwd_ret(c, T, FWD_WIN)
                if r is None:
                    continue
                vals.append((v, r))
            if len(vals) < N_BUCKET * MIN_N:
                continue
            used += 1
            xs = sorted(x for x, _ in vals)
            ths = [xs[int(len(xs) * i / N_BUCKET)] for i in range(1, N_BUCKET)]
            for v, r in vals:
                b = 0
                for i, t in enumerate(ths):
                    if v <= t:
                        b = i
                        break
                else:
                    b = N_BUCKET - 1
                per_bucket[b].append(r)
        rows = []
        for b in sorted(per_bucket):
            v = per_bucket[b]
            rows.append((b, len(v), statistics.mean(v)))
        if not rows:
            return rows, 0.0, None, 0
        spread = rows[-1][2] - rows[0][2]
        ws = [r[2] for r in rows if r[1] >= MIN_N]
        mono = None
        if len(ws) >= 3:
            ups = sum(1 for i in range(len(ws) - 1) if ws[i + 1] > ws[i])
            downs = sum(1 for i in range(len(ws) - 1) if ws[i + 1] < ws[i])
            mono = "升" if ups > downs else ("降" if downs > ups else "平")
        return rows, spread, mono, used

    print("\n=== 检验 1：资金流 cum%d 是否领先？ ===" % CUM_WIN)
    rows, spread, mono, used = run(
        lambda c, T: cum_before(c, T, CUM_WIN), "cum%d" % CUM_WIN)
    if not rows:
        print("样本不足 → 不可判")
    else:
        for b, n, m in rows:
            print("   档%d  n=%5d  T+%d 日均收益 = %+6.2f%%"
                  % (b, n, FWD_WIN, m))
        print("   档间差（高档−低档）= %+.2fpp ｜ 趋势=%s ｜ 有效入场日=%d"
              % (spread, mono, used))

    print("\n=== 检验 2（对照组）：T 之前涨幅的领先性 ===")
    rows2, spread2, mono2, used2 = run(
        lambda c, T: mom_before(c, T, CUM_WIN), "mom%d" % CUM_WIN)
    if rows2:
        for b, n, m in rows2:
            print("   档%d  n=%5d  T+%d 日均收益 = %+6.2f%%"
                  % (b, n, FWD_WIN, m))
        print("   档间差（高档−低档）= %+.2fpp ｜ 趋势=%s ｜ 有效入场日=%d"
              % (spread2, mono2, used2))

    # ---- 结论 ----
    print("\n=== 结论 ===")
    judge_rows = [r for r in rows if r[1] >= MIN_N]
    if len(judge_rows) < 2 or used < 2:
        print("样本不足 → **不可判**（不通过也不否决，等更多序列）")
        verdict = "不可判"
    else:
        lead = spread > 0.5
        has_inc = (abs(spread) - abs(spread2)) > 0.5     # 相对涨幅的增量
        print("   资金流 cum%d 档间差 = %+.2fpp" % (CUM_WIN, spread))
        print("   涨幅对照 档间差 = %+.2fpp" % (spread2,))
        if not lead:
            print("   → 资金流**不领先**（高档未来收益不高于低档）")
            print("     解释：主力净流入是**当日涨幅的滞后影子**，不是独立预测信号。")
            print("     **不得**把它当选股因子（加了只会放大 beta，不是 alpha）。")
            verdict = "不领先"
        elif not has_inc:
            print("   → 资金流领先，但**相对涨幅没有增量**（%+.2f vs %+.2f）" % (spread, spread2))
            print("     即：资金流 ≈ 涨幅的信息，增量微弱。暂不进规则。")
            verdict = "无增量"
        else:
            print("   → 资金流领先且有增量（%+.2f vs 涨幅 %+.2f）" % (spread, spread2))
            print("     ★ 可进入 `_accum_oos.py` 四道闸门检验（移动止盈回测 + 随机对照）。")
            verdict = "有增量·待闸门"

    out = {"date": a.date, "seq_span": span, "n_seq": len(seq),
           "cum_win": CUM_WIN, "fwd_win": FWD_WIN, "n_bucket": N_BUCKET,
           "entry_days": entry,
           "flow_rows": rows, "flow_spread": spread, "flow_mono": mono,
           "mom_rows": rows2, "mom_spread": spread2, "mom_mono": mono2,
           "n_entry_used": used, "n_entry_used_mom": used2,
           "verdict": verdict}
    p = os.path.join(DH.HUB, "flow_lead_lag_%s.json" % DH.DS(a.date))
    json.dump(out, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n[out] %s" % p)
    print("【纪律】本脚本只判定「领先/滞后」这一件事，**不产出选股结论**。")


if __name__ == "__main__":
    main()
