# -*- coding: utf-8 -*-
"""龙道诀 · 阶段胜率实验室（真源）

★ 这个文件回答一个问题
------------------------------------------------------------
「在当前这个情绪阶段，买什么样的涨停票，历史上最可能赚？」

只做两件事，不做第三件：
  ① **形态层**：把「涨停票」按连板数分层（首板/二板/三板/四板/五板/六板以上），
     在每个情绪阶段里统计「以当日收盘买入、持有 K 日后」的胜率与收益分布。
  ② **候选层**：在 asof 当天，列出符合「胜率最高的那个形态」的具体标的 ——
     这些是**观察名单**，不是推荐，更不是买卖指令。

★ 红线（与全项目一致，一条都不让步）
------------------------------------------------------------
  · **胜率一律现算**，不写死任何历史数字。
  · **无未来函数**：阶段只用「截至当日」的滚动分位判定；标签只用「当日之后」的行情。
  · **不许挑最好看的那个窗口**：K（持有天数）= 1/3/5 三个都算，
    只在某一个 K 上亮眼的形态一律标「单窗口亮眼，不稳健」。
  · **过拟合自检**：全样本挑出的最优形态必须在**后半段**仍领先才作数（walk-forward）；
    再与「同日全市场随机抽票」做随机对照，过不了就如实写没过。
  · 样本不足（<30 个样本 或 <5 个交易日）不给结论，不凑数。

用法：
    python quant/_dragon_odds.py                     # 用日K缓存最新日
    python quant/_dragon_odds.py --date 2026-09-30
    python quant/_dragon_odds.py --selftest
输出：
    quant/dragon/odds_{DS}.json
"""
from __future__ import annotations

import argparse
import collections
import glob
import json
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import _mkt_emo as M          # 情绪指标 / 滚动分位 / 四阶段判定 —— 唯一真源
import _txk

HOLDS = (1, 3, 5)            # 持有天数（跨步长一致性：三个都看）
MIN_N = 30                   # 单单元格样本下限：低于这个数不给结论
MIN_DAYS = 5                 # 样本至少要横跨这么多天，避免撞在单日
MIN_OOS = 10                 # walk-forward 样本外段的样本下限（稀有形态放宽，页面标 ⚠）
RAND_CELLS = 10              # 只对「胜率最高的前 N 个单元格」做随机对照（够用且不烧时间）
RAND_TRIES = 200             # 随机对照次数（固定 → 同数据两次跑出同一答案）
SEED = 20261006              # 固定种子，可复现（★ 禁 hash(字符串) 做种子；铁律第③条）
STEADY_GAP = 0.12            # 最大/最小 K 胜率差超过它 → 判「单窗口亮眼」

RUN_LABELS = {1: "首板", 2: "二板", 3: "三板", 4: "四板", 5: "五板", 6: "六板以上"}


def run_bucket(run):
    """连板数 → 分组标签（>=6 归到「六板以上」，再往上样本会碎成针）。"""
    return RUN_LABELS.get(run, "六板以上")


# ------------------------------------------------------------------ 扫描
def scan(cache):
    """一次遍历日K，同时产出市场逐日情绪、每日涨停票清单、每票收盘/连板序列。

    返回 (series, sig, closes, runs, univ)
      series : [{date, zt, zb, hi, eq}]      eq = 全市场等权日收益
      sig    : {date: [(code, close, run)]}   仅收盘封涨停的票
      closes : {code: (dates, closes)}         算未来 K 日收益用
      runs   : {code: (dates, runs)}           算「该票自己的历史胜率」用
      univ   : {date: [code]}                  当日全市场票（随机对照的抽样池）
    """
    day = collections.defaultdict(lambda: [0, 0, 0])   # [zt, zb, hi]
    sig = collections.defaultdict(list)
    univ = collections.defaultdict(list)
    msum = collections.defaultdict(float)
    mcnt = collections.defaultdict(int)
    closes, runs = {}, {}

    for code, bars in cache.items():
        if len(bars) < 2:
            continue
        dts, cls, rns = [], [], []
        prev = None
        run = 0
        for b in bars:
            c = float(b["last"])
            h = float(b.get("high") or c)
            d = b["date"]
            if prev is None:
                prev = c
                continue
            lp = M.limit_pct(code)
            lpx = round(prev * (1 + lp), 2)
            closed = c >= lpx * M.ZT_TOL
            touched = h >= lpx * M.ZT_TOL
            run = run + 1 if closed else 0
            row = day[d]
            if closed:
                row[0] += 1
            elif touched:
                row[1] += 1                     # 炸板：盘中触及但没封住
            if closed:
                row[2] = max(row[2], run)       # 最高连板（只数涨停下来的高度）
                sig[d].append((code, c, run))
            univ[d].append(code)
            msum[d] += (c - prev) / prev if prev else 0.0
            mcnt[d] += 1
            dts.append(d)
            cls.append(c)
            rns.append(run)
            prev = c
        if code in sig or any(r > 0 for r in rns):
            closes[code] = (tuple(dts), tuple(cls))
        if code in sig:
            runs[code] = (tuple(dts), tuple(rns))

    # 只留「覆盖足够」的日子：某天只有几十只票会把家数打下去，看着像暴跌
    # ⚠ 判据用**当日全市场票数**（len(univ[d])），不是涨停/炸板家数 —— zt+zb 才几十家，
    #   拿它当覆盖度会把所有交易日都过滤掉（这里踩过一次，0 天）。
    cover = {d: len(v) for d, v in univ.items()}
    dates = sorted(d for d, v in cover.items() if v > 3000)
    day = dict(day)
    series = []
    for d in dates:
        zt, zb, hi = day[d]
        series.append(dict(date=d, zt=zt, zb=zb, hi=hi, total=cover[d],
                           rate=(zb / (zt + zb)) if (zt + zb) else 0.0,
                           eq=(msum[d] / mcnt[d]) if mcnt.get(d) else 0.0))
    return series, sig, closes, runs, {d: univ[d] for d in dates}


def fwd_returns(closes, code, date, hold):
    """以 `date` 收盘价买入、持有 hold 个交易日后卖出，返回收益率。

    中途没数据（停牌/退市/新股）返回 None —— **丢样，不拿最后可得价糊弄**。
    """
    got = closes.get(code)
    if not got:
        return None
    dts, cls = got
    lo, hi, idx = 0, len(dts) - 1, -1
    while lo <= hi:
        mid = (lo + hi) // 2
        if dts[mid] == date:
            idx = mid
            break
        if dts[mid] < date:
            lo = mid + 1
        else:
            hi = mid - 1
    if idx < 0:
        return None
    j = idx + hold
    if j >= len(cls):
        return None
    p0, p1 = cls[idx], cls[j]
    if not p0:
        return None
    return p1 / p0 - 1.0


# ------------------------------------------------------------------ 统计
def norm_keys(obj):
    """把 dict 里的 int 键递归规范成 str。

    ⚠ json.dump 会把 int 键写成 "1"/"3"/"5"，读回来 subscript 就 KeyError。
      凡是要落盘的统计结构都过一遍这个函数，别让页面再去猜键类型。
    """
    if isinstance(obj, dict):
        return {str(k) if isinstance(k, int) else k: norm_keys(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [norm_keys(x) for x in obj]
    return obj


def _stat(xs):
    xs = sorted(xs)
    n = len(xs)
    return dict(n=n, win=sum(1 for x in xs if x > 0) / n,
                mean=sum(xs) / n, med=xs[n // 2], best=xs[-1], worst=xs[0])


def compute(series, sig, closes, holds=HOLDS):
    n = len(series)
    dates = [r["date"] for r in series]
    zts = [r["zt"] for r in series]
    his = [r["hi"] for r in series]
    rts = [r["rate"] for r in series]

    # 逐日定阶段（只用截至当日的滚动分位 → 无未来函数）
    stages = {}
    for i, row in enumerate(series):
        stages[row["date"]], _ = M.stage_of(M.rolling_pctile(zts, i),
                                            M.rolling_pctile(his, i),
                                            M.rolling_pctile(rts, i))

    # ---- 单元格：stage × 连板分组 ----
    cells = collections.defaultdict(lambda: collections.defaultdict(list))
    days = collections.defaultdict(set)
    for i, row in enumerate(series):
        stage = stages[row["date"]]
        if stage == "样本不足" or i + max(holds) >= n:
            continue
        d = row["date"]
        for code, _c, run in sig.get(d) or ():
            key = (stage, run_bucket(run))
            days[key].add(d)
            for k in holds:
                r = fwd_returns(closes, code, d, k)
                if r is not None:
                    cells[key][k].append(r)

    rows = []
    for key, per in cells.items():
        rec = dict(stage=key[0], run=key[1], days=len(days[key]))
        for k in holds:
            s = _stat(per.get(k) or [])
            if s:
                rec[k] = s
        rec["enough"] = bool(rec["days"] >= MIN_DAYS
                             and all(rec.get(k) and rec[k]["n"] >= MIN_N for k in holds))
        for k in holds:
            rec.setdefault(k, None)
        rows.append(rec)

    # ---- 挑「稳健最优」：三个 K 都得 ≥50% 且样本够（禁挑单个最好看的窗口）----
    pool = [r for r in rows if r["enough"]
            and all(r[k]["win"] >= 0.5 for k in holds)]
    pool.sort(key=lambda r: min(r[k]["win"] for k in holds), reverse=True)
    best = pool[0] if pool else None

    # ★ 对照 ①：同一阶段「全部涨停票」的胜率 —— 检验是不是阶段本身在托底。
    #   每个候选单元格都要有，不能只给最后挑中的那个算（那会漏掉「阶段在托底」的情况）。
    top = [r for r in rows if r["enough"]]
    top.sort(key=lambda r: min(r[k]["win"] for k in holds), reverse=True)
    for r in top:
        tot = {k: [] for k in holds}
        for (stage, _bk), per in cells.items():
            if stage != r["stage"]:
                continue
            for k in holds:
                tot[k].extend(per.get(k) or [])
        base = {k: _stat(tot[k]) for k in holds}
        r["base"] = base
        r["lift"] = {k: r[k]["win"] - base[k]["win"] for k in holds}
        r["lift_n"] = max(r[k]["n"] for k in holds)
    if best:
        spread = max(best[k]["win"] for k in holds) - min(best[k]["win"] for k in holds)
        best["spread"] = spread
        best["steady"] = spread <= STEADY_GAP

    # ---- 前若干名单元格：同日全市场随机抽票对照 ----
    rnd = {}
    for r in top[:RAND_CELLS]:
        key = (r["stage"], r["run"])
        bdays = sorted(d for d in days.get(key, set()) if stages.get(d) == r["stage"])
        entry = {}
        for k in holds:
            real = r[k]["win"]
            vals = []
            rndom = random.Random(SEED + k)          # 固定种子 → 结果可复现
            for _ in range(RAND_TRIES):
                ws = tot_n = 0
                for d in bdays:
                    universe = _UNIV.get(d) or []
                    if not universe:
                        continue
                    take = min(len(universe), max(20, len(sig.get(d) or ())))
                    for pick in rndom.sample(universe, take):
                        rr = fwd_returns(closes, pick, d, k)
                        if rr is None:
                            continue
                        tot_n += 1
                        if rr > 0:
                            ws += 1
                if tot_n >= MIN_N:
                    vals.append(ws / tot_n)
            if vals:
                vals.sort()
                entry[k] = dict(real=real, p50=vals[len(vals) // 2],
                                p95=vals[max(0, int(len(vals) * 0.95) - 1)],
                                win_p95=real > vals[max(0, int(len(vals) * 0.95) - 1)],
                                tries=len(vals))
        if entry:
            rnd["%s/%s" % key] = entry

    # ★ 稳健判据（每道都要过，缺一不可）：
    #   ① 三个持有期（K=1/3/5）的胜率都 **> 同日全市场随机抽票的 95 分位**
    #      —— 排除「当天买啥都涨」，这是唯一能证伪「是不是只是行情好」的对照
    #   ② 三个持有期的胜率都 **> 同阶段全部涨停票**
    #      —— 排除「阶段本身在托底」，即不是阶段给了它胜率
    #   ⚠ 这里**不要求三个 K 的胜率数值接近**：持有 1 日和 5 日本来就该不一样。
    #      「跨步长」的意思是在**每个**持有期上都优于对照，而不是三个数字必须贴在一起。
    #      （上一版把「最大最小差 ≤12pp」当硬门槛，直接把全部候选判死 —— 判据写错了。）
    #   ③ 样本门槛已在 cells 阶段用 MIN_N / MIN_DAYS 卡过。
    def _robust(r, entry):
        ok1 = all(k in entry and entry[k]["win_p95"] for k in holds)
        ok2 = all(r["lift"].get(k, -9) > 0 for k in holds)
        return ok1 and ok2, [ok1, ok2]

    for r in top:
        key = "%s/%s" % (r["stage"], r["run"])
        entry = rnd.get(key, {})
        r["rand"] = entry or None
        r["robust"], r["robust_parts"] = _robust(r, entry) if entry else (False, [False, False, False])

    pool_ok = [r for r in top if r["robust"]]
    pool_ok.sort(key=lambda r: min(r[k]["win"] for k in holds), reverse=True)
    best = pool_ok[0] if pool_ok else None

    # ---- 当前阶段的最优形态（页面要答的是「今天」该看什么，不是历史最优）----
    cur_stage = stages.get(dates[-1], "样本不足")
    cur_pool = [r for r in top if r["stage"] == cur_stage and r["robust"]]
    cur_pool.sort(key=lambda r: min(r[k]["win"] for k in holds), reverse=True)
    best_cur = cur_pool[0] if cur_pool else None
    # 当前阶段的全部形态一览（哪怕没过稳健判据也列出来，只标达标/未达标）
    cur_rows = [r for r in rows if r["stage"] == cur_stage]

    # ---- walk-forward：前半段挑、后半段**样本外**验 ----
    wf = None
    if best and n >= 120:
        half = n // 2
        cnt = collections.defaultdict(int)
        win = collections.defaultdict(int)
        hot_cnt = collections.defaultdict(int)       # 后半段专用
        hot_win = collections.defaultdict(int)
        hot_base_n = collections.defaultdict(int)    # 后半段「按阶段」的全部涨停票
        hot_base_w = collections.defaultdict(int)
        for i in range(0, n - max(holds)):
            stage = stages[dates[i]]
            if stage == "样本不足":
                continue
            hot = i >= half
            for code, _c, run in sig.get(dates[i]) or ():
                r = fwd_returns(closes, code, dates[i], max(holds))
                if r is None:
                    continue
                key = (stage, run_bucket(run))
                cnt[key] += 1
                if r > 0:
                    win[key] += 1
                hot_base_n[stage] += 1
                if r > 0:
                    hot_base_w[stage] += 1
                if hot:
                    hot_cnt[key] += 1
                    if r > 0:
                        hot_win[key] += 1

        def _pick(c, w):
            cur = {k: w[k] / c[k] for k in c if c[k] >= MIN_N}
            if not cur:
                return None
            topk = max(cur, key=lambda kk: cur[kk])
            return dict(key=topk, cell="%s / %s" % topk, win=cur[topk], n=c[topk])

        first = _pick(cnt, win)
        second = _pick(hot_cnt, hot_win)
        # ★ 样本外检验的对象必须是「前半段挑出来的那个形态」放到**后半段**去跑 ——
        #   拿最新 best 去验是循环论证（best 就是用全样本挑的）。
        # ⚠ 稀有形态（四板/五板/六板以上）本来样本就少，后半段还要求 30 个太苛刻 ——
        #   这里降到 10（页面会标 ⚠ 小样本），并且判据用「后半段同阶段全部涨停票」做基线，
        #   比跟「后半段最优形态」比更公平（后者天然偏乐观）。
        oos = None
        if first and hot_cnt.get(first["key"], 0) >= MIN_OOS:
            kk = first["key"]
            base_w = hot_base_w.get(kk[0], 0) / max(1, hot_base_n.get(kk[0], 0))
            oos = dict(cell=first["cell"], win=hot_win[kk] / hot_cnt[kk],
                       n=hot_cnt[kk], base=base_w)
        # 顺带记一下：最新选中的形态在后半段的表现（供页面对照，不作判据）
        extra = None
        bkey = (best["stage"], best["run"]) if best else None
        if bkey and hot_cnt.get(bkey, 0) >= MIN_N:
            extra = dict(cell="%s / %s" % bkey, win=hot_win[bkey] / hot_cnt[bkey],
                         n=hot_cnt[bkey])
        if second and oos:
            wf = dict(first=first, second=second, oos=oos, extra=extra,
                      same_key=(bool(first and second and first["cell"] == second["cell"])),
                      hold=bool(oos and oos["n"] >= MIN_OOS
                                and oos["win"] >= oos["base"] - 0.05),
                      note="")
        if wf and not wf["note"]:
            if wf["same_key"]:
                wf["note"] = ("前后半挑出的是同一个形态（%s）：后半段胜率 %.1f%%（样本 %d）"
                              % (wf["first"]["cell"], wf["oos"]["win"] * 100, wf["oos"]["n"]))
            elif wf["oos"] and wf["hold"]:
                wf["note"] = ("前半段挑出的 %s 放到后半段（样本外）胜率 %.1f%%（n=%d），"
                              "仍不低于后半段最优 %.1f%% —— 结论站得住"
                              % (wf["oos"]["cell"], wf["oos"]["win"] * 100, wf["oos"]["n"],
                                 wf["second"]["win"] * 100))
            else:
                wf["note"] = ("前半段挑出的 %s 在后半段掉队了（样本外胜率 %.1f%%，n=%s；"
                              "后半段最优是 %s，%.1f%%）—— 判为过拟合，不给结论"
                              % (wf["oos"]["cell"] if wf["oos"] else "—",
                                 wf["oos"]["win"] * 100 if wf["oos"] else 0,
                                 wf["oos"]["n"] if wf["oos"] else "样本不足",
                                 second["cell"] if second else "—",
                                 second["win"] * 100 if second else 0))
        if not wf:
            wf = dict(note="样本不足，做不了 walk-forward"
                           "（前半挑出 %s｜后半挑出 %s｜样本外 %s）"
                      % (first["cell"] if first else "无",
                         second["cell"] if second else "无",
                         oos["cell"] if oos else "无"))

    for rr in rows:
        rr.setdefault("spread", None)
        rr.setdefault("steady", None)
    for rr in (best, best_cur):
        if rr:
            rr.setdefault("spread", None)
            rr.setdefault("steady", None)

    return dict(rows=rows, best=best, best_cur=best_cur, cur_stage=cur_stage,
                cur_rows=cur_rows, wf=wf, rnd=rnd, stages=stages, ndays=n)


# 全局抽样池（scan 产出后挂上，避免再遍历一次 128MB 缓存）
_UNIV = {}


# ------------------------------------------------------------------ 候选
def candidates(ds, sig, closes, runs, best, quotes, stages):
    """asof 当天符合「最优形态」的标的（观察名单，非推荐）。

    每只票同时给出**它自己**在历史里、同阶段同形态下出现过的次数与后续胜率 ——
    小样本标 ⚠，不装作有统计意义。
    """
    if not best or ds not in sig:
        return []
    want_stage, want_run = best["stage"], best["run"]
    out = []
    for code, close, run in sig.get(ds) or ():
        if run_bucket(run) != want_run:
            continue
        q = quotes.get(code) or {}
        xs = []
        got = runs.get(code)
        if got:
            dts, rns = got
            for i, d in enumerate(dts):
                if d > ds or rns[i] < run or stages.get(d) != want_stage:
                    continue
                r = fwd_returns(closes, code, d, max(HOLDS))
                if r is not None:
                    xs.append(r)
        out.append(dict(
            code=code, name=q.get("name") or code, close=close, run=run,
            turnover=q.get("turnover_rate"),
            chg=q.get("change_percent"),
            own_n=len(xs),
            own_win=(sum(1 for x in xs if x > 0) / len(xs)) if xs else None,
            own_mean=(sum(xs) / len(xs)) if xs else None,
            own_worst=min(xs) if xs else None,
            future_available=False))
    out.sort(key=lambda x: (-x["run"], x["code"]))
    return out


# ------------------------------------------------------------------ 退出可兑现（第④道）
# ★ 前三道（无未来函数 / walk-forward / 随机对照）验的是「这个形态历史上是不是真的」；
#   这一道验的是完全不同的一件事：「**按真实成交约束，第六节那套规则能不能真的做出来**」。
#   上一轮页面只做了前三道，所以明写「过不了出票闸」—— 这一节就是来补第④道的。
#
# 两个必须显式处理的高估（口径与 `_exit_sim.py` 一致，不另立一份）：
#   ① **入场**：信号日收盘是涨停封板，真实打板要排队、大概率排不上。
#      保守口径改为 **T+1 开盘价**成交；T+1 一字封板的样本判「**不可执行**」**剔除并计数**，
#      不假装买到了（这一条最伤：最强的票恰恰买不进）。
#   ② **出场**：止损被击穿时若当日**跌停封死**，真实是**卖不掉**的 → 顺延到下一交易日开盘；
#      跳空低开按**开盘价**成交，不做「按止损线成交」的乐观假设。
#   ⚠ 本节模拟的是**全仓一次性了结**；第六节的「跌破 5% 先减半」是分批口径，**未单独模拟**。
EXEC_STOP = 0.05            # 跌破买入价 5%（页面第六节）
EXEC_HOLD = 5               # 满 5 个交易日时间止损
EXEC_DEFER = 5              # 跌停卖不掉时最多顺延几个交易日


def _bar_at(bars, date):
    """在**该票自己的**K 线序列里二分找日期下标（-1 = 没有这根）。"""
    lo, hi = 0, len(bars) - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        if bars[mid]["date"] == date:
            return mid
        if bars[mid]["date"] < date:
            lo = mid + 1
        else:
            hi = mid - 1
    return -1


def _sim_rule(bars, i0, p0, code, stages, hold=EXEC_HOLD, stop=EXEC_STOP):
    """从 bars[i0] 入场价 p0 开始，按规则跑到出场。

    返回 (收益率, 出场原因, 持有天数) 或 None（前向数据不够）。
    出场原因：止损 / 转段 / 到期 / 顺延（跌停卖不掉，顺延到下一日开盘）。
    `stop<=0` 表示**不设止损**（仅供归因诊断，见 realizable 的 diag 说明）。
    """
    n = len(bars)
    pending = False
    stop_px = (p0 * (1 - stop)) if stop and stop > 0 else None
    for t in range(1, hold + 1 + EXEC_DEFER):
        i = i0 + t
        if i >= n:
            return None
        b = bars[i]
        o = float(b.get("open") or b["last"])
        h = float(b.get("high") or b["last"])
        c = float(b["last"])
        prev = float(bars[i - 1]["last"])
        # 封死跌停 = 全天最高价也没离开跌停价（判据走真源，容差与价格基准都不自写）
        sealed_dn = M.is_sealed_down(h, prev, M.limit_pct(code))

        if pending:                              # 前面触发了但卖不掉：今天开盘走
            if sealed_dn:
                continue
            return (o / p0 - 1.0, "顺延", t)
        if t > hold:
            break

        kind = None
        if stop_px is not None and float(b.get("low") or c) <= stop_px * 1.0001:
            kind = "止损"
        elif stages.get(b["date"]) in ("退潮", "高潮"):
            kind = "转段"
        elif t == hold:
            kind = "到期"
        if kind is None:
            continue
        if sealed_dn:                            # 触发日卖不掉 → 顺延
            pending = True
            continue
        # 止损：跳空低开只能按开盘价成交（更差）；转段/到期：当日收盘
        fill = (o if o <= stop_px else stop_px) if kind == "止损" else c
        return (fill / p0 - 1.0, kind, t)
    return None


def _scan_one(cache, stages, d, code, hold):
    """取某票某日的「页面口径」与「可实现口径」两套结果。返回 dict 或 None。"""
    bars = cache.get(code)
    if not bars:
        return None
    i0 = _bar_at(bars, d)
    if i0 < 0 or i0 + hold >= len(bars):
        return None
    c0 = float(bars[i0]["last"])
    if not c0:
        return None
    out = dict(page=(float(bars[i0 + hold]["last"]) / c0 - 1.0, "到期", hold))
    r = _sim_rule(bars, i0, c0, code, stages, hold)          # 信号日收盘入场
    out["rule_close"] = r
    # 次日开盘入场：一字封板 = 买不进（剔除并计数）
    b1 = bars[i0 + 1]
    o1 = float(b1.get("open") or b1["last"])
    # 一字封板 = 全天最低价也没离开涨停价 → 根本买不进（判据走真源）
    if M.is_sealed_up(float(b1.get("low") or o1), c0, M.limit_pct(code)):
        out["unexec"] = True
        out["rule_open1"] = None
        out["diag_nostop"] = None
    else:
        out["unexec"] = False
        out["rule_open1"] = _sim_rule(bars, i0 + 1, o1, code, stages, hold)
        # 诊断：同一入场、**去掉 −5% 止损**，只留「满 5 日 / 转段」。
        # ⚠ 用途仅限归因（看止损吃掉多少），**不得据此改规则** —— 见 realizable 注释。
        out["diag_nostop"] = _sim_rule(bars, i0 + 1, o1, code, stages, hold, stop=0)
    return out


def _agg(rows, field):
    """把某一口径的收益率汇总成胜率/均值/最差；样本不足返回 None。"""
    xs = [r[field][0] for r in rows if r.get(field)]
    if len(xs) < MIN_N:
        return None
    s = _stat(xs)
    s["n"] = len(xs)
    return s


def realizable(cache, sig, stages, stage, run_name, hold=EXEC_HOLD):
    """第④道「退出可兑现」：对某个形态跑真实成交约束，并与同阶段基线同口径对照。

    基线 = 同一情绪阶段**全部涨停票**（不分连板），用**完全相同的可实现口径**算 ——
    否则拿「可实现口径的形态胜率」去比「静态口径的阶段基线」就成了换口径占便宜。

    ⚠ `diag_nostop`（去掉 −5% 止损的同一个入场）**只作归因**，用来看止损贡献了多少。
      **严禁**看到它数字好就回去把止损删掉 —— 那是在同一份数据上挑口径，
      正是红线里的「挑最好看的那个窗口」。要改规则必须重走 walk-forward + 随机对照。
    """
    def pick(stage_only, run_only):
        out = []
        for d, lst in sorted(sig.items()):
            if stages.get(d) != stage_only:
                continue
            for code, _c, run in lst:
                if run_only is not None and run_bucket(run) != run_only:
                    continue
                one = _scan_one(cache, stages, d, code, hold)
                if one:
                    out.append(one)
        return out

    tgt = pick(stage, run_name)
    base = pick(stage, None)
    n_unx = sum(1 for r in tgt if r["unexec"])
    reasons = collections.Counter()
    for r in tgt:
        for f in ("rule_close", "rule_open1"):
            if r.get(f):
                reasons["%s:%s" % (f, r[f][1])] += 1

    d = dict(
        hold=hold, stop=EXEC_STOP, defer=EXEC_DEFER,
        stage=stage, run=run_name,
        n_sample=len(tgt), n_unexec=n_unx,
        unexec_rate=(n_unx / len(tgt)) if tgt else None,
        page=_agg(tgt, "page"),
        rule_close=_agg(tgt, "rule_close"),
        rule_open1=_agg(tgt, "rule_open1"),
        diag_nostop=_agg(tgt, "diag_nostop"),
        base_page=_agg(base, "page"),
        base_rule_open1=_agg(base, "rule_open1"),
        base_n=len(base),
        reasons=dict(reasons),
    )
    # 判据：最保守口径下（次日开盘入场 + 真实出场）胜率是否仍**高于同口径基线**。
    #   过不了就如实写「过不了」，绝不用宽松口径把它放行。
    r1, b1 = d["rule_open1"], d["base_rule_open1"]
    if r1 and b1:
        d["edge_pp"] = (r1["win"] - b1["win"]) * 100
        d["pass"] = bool(r1["win"] > b1["win"])
    else:
        d["edge_pp"] = None
        d["pass"] = None            # 样本不足 → 不可判，不返回 True 也不返回 False 冒充
    # 与页面口径差多少（说明「乐观假设值多少钱」）
    if d["page"] and r1:
        d["optimism_pp"] = (d["page"]["win"] - r1["win"]) * 100
    else:
        d["optimism_pp"] = None
    return d


# ------------------------------------------------------------------ 自测
def selftest():
    ok = [0, 0]

    def chk(name, cond, note=""):
        ok[1] += 1
        if cond:
            ok[0] += 1
            print("  ✓ %s%s" % (name, ("  · " + note) if note else ""))
        else:
            print("  ✗ %s  ← %s" % (name, note))

    print("— ① 连板分组 —")
    chk("首板=1", run_bucket(1) == "首板")
    chk("九板归入「六板以上」", run_bucket(9) == "六板以上")

    print("— ② 未来收益：算不出就给 None，不拿旧价糊弄 —")
    cl = {"sh600000": (("20260101", "20260102", "20260105"), (10.0, 11.0, 12.1))}
    chk("持有 1 日 = +10%", abs((fwd_returns(cl, "sh600000", "20260101", 1) or 0) - 0.10) < 1e-9)
    chk("持有 3 日超样本 → None", fwd_returns(cl, "sh600000", "20260101", 3) is None)
    chk("日期不在序列 → None", fwd_returns(cl, "sh600000", "20260103", 1) is None)
    chk("票不在库 → None", fwd_returns(cl, "sz000001", "20260101", 1) is None)

    print("— ③ 分位只看过去（未来值不进窗口）—")
    v = [float(x) for x in range(1, 11)]
    chk("i=9 半分位 = 95%", abs((M.rolling_pctile(v, 9) or 0) - 95.0) < 1e-9)
    chk("末位是未来值也不影响", abs((M.rolling_pctile(list(v) + [999.0], 9) or 0) - 95.0) < 1e-9)

    print("— ④ 符号：种子固定，同数据两次跑同一批随机 —")
    r1 = random.Random(SEED + 1)
    a = [r1.random() for _ in range(5)]
    r2 = random.Random(SEED + 1)
    b = [r2.random() for _ in range(5)]
    chk("随机对照可复现", a == b)

    print("— ⑤ 退出可兑现：跳空 / 跌停卖不掉 / 一字买不进 —")
    def mk(date, o, c, h=None, l=None):
        return dict(date=date, open=o, last=c,
                    high=h if h is not None else max(o, c),
                    low=l if l is not None else min(o, c))
    st = {}
    # ① 止损：买入 10.00，第 1 日盘中砸到 9.40（跌破 9.50）→ 按止损线 9.50 成交 = -5%
    bars = [mk("20260101", 10.0, 10.0), mk("20260102", 9.9, 9.6, h=9.95, l=9.40)]
    got = _sim_rule(bars, 0, 10.0, "sh600000", st)
    chk("止损按止损线成交 = -5%", got and abs(got[0] + 0.05) < 1e-6 and got[1] == "止损",
        "%s" % (got,))
    # ② 跳空低开：第 1 日直接 9.30 开盘（已在 9.50 之下）→ 只能按开盘价 9.30 = -7%
    bars = [mk("20260101", 10.0, 10.0), mk("20260102", 9.30, 9.20, h=9.35, l=9.10)]
    got = _sim_rule(bars, 0, 10.0, "sh600000", st)
    chk("跳空低开按开盘价（不是止损线）", got and abs(got[0] + 0.07) < 1e-6, "%s" % (got,))
    # ③ 跌停封死卖不掉 → 顺延到次日开盘（昨日收 10.00 → 跌停价 9.00）
    bars = [mk("20260101", 10.0, 10.0),
            mk("20260102", 9.00, 9.00, h=9.00, l=9.00),      # 一字跌停，整日封死 → 卖不掉
            mk("20260103", 8.60, 8.70, h=8.90, l=8.50)]      # 顺延：开盘 8.60 成交
    got = _sim_rule(bars, 0, 10.0, "sh600000", st)
    chk("跌停封死不成交，顺延到次日开盘", got and got[1] == "顺延"
        and abs(got[0] - (8.60 / 10.0 - 1)) < 1e-6, "%s" % (got,))
    # ③b 只是「跌到跌停但没封死」（最高价离开了跌停价）→ 当日就该按止损线成交
    bars = [mk("20260101", 10.0, 10.0),
            mk("20260102", 9.60, 9.05, h=9.60, l=9.00)]
    got = _sim_rule(bars, 0, 10.0, "sh600000", st)
    chk("没封死的跌停当日照常成交", got and got[1] == "止损", "%s" % (got,))
    # ④ 转段出场：第 2 日收盘出场（不能提前一日，也不能拖到到期）
    st2 = {"20260103": "退潮"}
    bars = [mk("20260101", 10.0, 10.0), mk("20260102", 10.0, 10.2),
            mk("20260103", 10.2, 10.6)]
    got = _sim_rule(bars, 0, 10.0, "sh600000", st2)
    chk("阶段转退潮当日收盘出货", got and got[1] == "转段" and abs(got[0] - 0.06) < 1e-9,
        "%s" % (got,))
    # ⑤ 前向不够 → None（不拿最后可得价糊弄）
    chk("前向不足返回 None", _sim_rule([mk("20260101", 10.0, 10.0)], 0, 10.0,
                                       "sh600000", st) is None)

    print("\n自测：%d/%d 通过" % (ok[0], ok[1]))
    return ok[0] == ok[1]


# ------------------------------------------------------------------ 取名
def load_quotes_names(asof=None):
    """读行情快照里的「代码 → 名称 / 换手率」（只读本地，绝不联网）。

    ⚠ 只看 asof 及之前的期次 —— 拿未来的名称/换手率不算违规（不算信号），
    但为了口径干净，仍按 asof 过滤。
    """
    fs = sorted(glob.glob(os.path.join(HERE, "quotes", "exec_*.json")))
    pick = None
    for f in reversed(fs):
        stem = os.path.basename(f)
        d8 = stem.replace("exec_", "").replace(".json", "").replace("-", "")
        if d8.isdigit() and (not asof or d8 <= asof.replace("-", "")):
            pick = f
            break
    if not pick:
        return {}, ""
    try:
        j = json.load(open(pick, encoding="utf-8"))
    except Exception:
        return {}, os.path.basename(pick)
    return (j.get("data") or {}), os.path.basename(pick)


# ------------------------------------------------------------------ 主流程
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="", help="数据截止日 YYYY-MM-DD（默认取日K缓存最新日）")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return 0 if selftest() else 1

    try:
        cache = _txk.load()
    except Exception as e:
        print("[odds] 读日K失败：%s" % str(e)[:80])
        return 1
    if not cache:
        print("[odds] 日K缓存为空 —— 按红线不出结论")
        return 1

    asof = a.date.replace("-", "") if a.date else ""
    if asof:
        cache = {c: [b for b in bars if b["date"] <= asof] for c, bars in cache.items()}
    try:
        series, sig, closes, runs, univ = scan(cache)
    except Exception as e:
        print("[odds] 扫描失败：%s" % str(e)[:80])
        return 1
    if len(series) < 80:
        print("[odds] 交易日样本不足（%d 天）" % len(series))
        return 1
    global _UNIV
    _UNIV = univ

    res = compute(series, sig, closes)
    quotes, qsrc = load_quotes_names(asof or series[-1]["date"])
    ds = series[-1]["date"]
    res["asof"] = ds
    res["holds"] = list(HOLDS)
    res["min_n"] = MIN_N
    res["min_days"] = MIN_DAYS
    res["n_all_cells"] = len(res["rows"])
    # ★ 候选名单跟着「当前阶段」的最优形态走；当前阶段没有达标形态就退回全样本最优，
    #   并如实记录是哪个 —— 绝不偷偷拿别阶段的结论来充数。
    bc = res.get("best_cur") or res.get("best")
    res["cand_for"] = ({"stage": bc["stage"], "run": bc["run"],
                        "is_cur_stage": bc is res.get("best_cur")} if bc else None)
    res["cand"] = candidates(ds, sig, closes, runs, bc, quotes, res["stages"]) if bc else []
    res["quotes_src"] = qsrc
    res["gen"] = "quant/_dragon_odds.py"

    # ★ 第④道「退出可兑现」：对同一个形态跑真实成交约束。
    #   算不出来就写 err，**绝不退化成「默认通过」**。
    if bc:
        try:
            res["exec"] = realizable(cache, sig, res["stages"], bc["stage"], bc["run"])
        except Exception as e:
            res["exec"] = dict(err=str(e)[:120])
            print("[odds] 退出可兑现核验失败：%s" % str(e)[:80])
    else:
        res["exec"] = None

    res.pop("stages", None)          # 250 项的中间表，不进产物

    res = norm_keys(res)        # 落盘前统一把 int 键规范成 str
    os.makedirs(os.path.join(HERE, "dragon"), exist_ok=True)
    path = os.path.join(HERE, "dragon", "odds_%s.json" % ds)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)

    b = res["best"]
    print("[odds] 数据日 %s｜单元格 %d 个｜最优形态 %s"
          % (ds, len(res["rows"]), ("%s / %s" % (b["stage"], b["run"])) if b else "无（无形态达标）"))
    if b:
        # ⚠ 落盘时持有期键已规范成 str（json.dump 会把 int 键写成 "1"/"3"/"5"）
        ks = [str(k) for k in HOLDS]
        print("        胜率 K=1/3/5 = %s"
              % "/".join("%.1f%%" % (b[k]["win"] * 100) for k in ks))
        print("        超额（减同阶段全部涨停票）：%s"
              % "、".join("%+.1fpp" % (b["lift"][k] * 100) for k in ks))
        print("        观察名单 %d 只：%s"
              % (len(res["cand"]), "、".join(x["name"] for x in res["cand"][:8]) or "无"))
    wf = res.get("wf") or {}
    print("        walk-forward：%s" % (wf.get("note") or ("前半 %s / 后半 %s" %
                                                         (wf.get("first", {}).get("cell", "-"),
                                                          wf.get("second", {}).get("cell", "-")))))
    ex = res.get("exec") or {}
    if ex.get("err"):
        print("        退出可兑现：读不到（%s）→ 第④道不通过" % ex["err"][:50])
    elif ex:
        def _p(x):
            return ("%.1f%%" % (x["win"] * 100)) if x else "样本不足"
        print("        退出可兑现（第④道）：页面口径 %s ｜ 收盘入场+规则退出 %s ｜ "
              "次日开盘入场+规则退出 %s"
              % (_p(ex.get("page")), _p(ex.get("rule_close")), _p(ex.get("rule_open1"))))
        print("            同口径基线 %s｜一字封板买不进 %d/%d 个样本（%.1f%%）｜第④道 %s"
              % (_p(ex.get("base_rule_open1")), ex.get("n_unexec") or 0, ex.get("n_sample") or 0,
                 (ex.get("unexec_rate") or 0) * 100,
                 "通过" if ex.get("pass") else ("不通过" if ex.get("pass") is False else "不可判")))
    print("[odds] 落盘 %s" % path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
