# -*- coding: utf-8 -*-
"""移动止盈 · 单一退出模拟口径（quant/_exit_sim.py）

背景（2026-10-04 实测发现）
---------------------------
主升精选 / 反转池 / 做T池 的退出回测原本各自实现 `_sim_trail`，共同存在**两个系统性高估**：

  ① **日内路径假设**：同根 K 线里「先更新最高价 → 上移止盈线 → 再判是否跌破」，
     等价于假设当日**先冲高后回落**。但当日最低价是否先于最高价出现是未知的，
     这个假设对跟踪止盈**系统性乐观**（实测可把收益抬到「1.2 天赚 0.77%」这种不可能量级）。
  ② **跳空未处理**：开盘已跌破止损线时，仍以「止损线价」成交。真实的限价单在跳空低开时
     只能以**开盘价**成交（更差）。不处理会把大阴线/跳空的亏损系统性低估。

同一组参数、只改这两条假设，A 档净均值跨度可达 **2.4pp**（与收益本身同量级）。
⇒ 任何基于旧口径的选参/胜率都是拟合噪声。

本模块提供统一实现，`cons` / `gap` 两个开关对应四种假设组合：

| cons | gap | 含义                                  |
|------|-----|---------------------------------------|
| False| False| **旧口径**（乐观日内 + 忽略跳空，生产原值）|
| True | False| 保守日内 + 忽略跳空                    |
| False| True | 乐观日内 + 跳空成交                    |
| True | True | **可实现口径**（推荐作为新生产默认）      |

用法
----
    from _exit_sim import sim_exit                      # 数组模式（前向 C/H/L/O 全程）
    pnl, hold, mae = sim_exit(fC, fH, fL, px, 0.12, 0.06, 0.03, 20, cons=True, fO=fO)
    # 标量模式：主升生产面板 fc 是 T+20 收盘标量，hold 须等于 len(fL)
    pnl, hold, mae = sim_exit(fc_scalar, fH, fL, px, 0.12, 0.06, 0.03, 20, cons=True, fO=fO)
"""
from __future__ import annotations

# 生产现行参数（与 build_selected 一致；改动须同步）
STOP = 0.12
ACT = 0.06
TRAIL = 0.03
MAXFWD = 20


def sim_exit(fC, fH, fL, px, stop=STOP, act=ACT, trail=TRAIL, hold=MAXFWD,
             cons=True, fO=None):
    """信号日收盘 px 买入 → 移动止盈退出的单笔收益（百分点）。

    参数
    ----
    fC : 前向收盘序列（array/list，T+1..T+hold）**或** T+hold 的收盘**标量**
         （标量模式仅在 hold == len(fL) 时有效，即「到期平仓价就是最后一根」）。
    fH, fL : 前向 high / low 序列（T+1..T+hold）。
    px  : 入场价（信号日收盘）。
    stop/act/trail/hold : 硬止损 / 激活点（act<=0 视为买入即激活）/ 回撤 / 最长持有日。
    cons : True=保守日内路径（先用截至前一日的止盈线判断当日是否跌破，再用当日高点上移）；
           False=旧乐观口径（同根 K 线先冲高后回落）。
    fO  : 前向开盘价序列（T+1..T+hold）；给定时启用跳空修正。

    返回
    ----
    (pnl%, hold_days, mae%)  —— mae 为持有期最大不利偏移（%）。
    """
    hi = px
    cur = px * (1 - stop)
    activated = (act <= 0)
    m = min(hold, len(fL))
    lo = fL[0]
    for j in range(m):
        # 跳空优先：开盘已在止损线之下 → 以开盘价成交（两版都适用）
        if fO is not None and fO[j] > 0 and fO[j] <= cur:
            return (fO[j] / px - 1) * 100, j + 1, (lo / px - 1) * 100
        if cons:
            # 保守：先用前一日的止盈线判当日是否跌破，再上移
            if fL[j] <= cur:
                return (cur / px - 1) * 100, j + 1, (lo / px - 1) * 100
            if fH[j] > hi:
                hi = fH[j]
            if fL[j] < lo:
                lo = fL[j]
            if not activated and hi >= px * (1 + act):
                activated = True
            if activated:
                ts = hi * (1 - trail)
                if ts > cur:
                    cur = ts
            continue
        # 乐观：同根 K 线先冲高后回落
        if fH[j] > hi:
            hi = fH[j]
        if fL[j] < lo:
            lo = fL[j]
        if not activated and hi >= px * (1 + act):
            activated = True
        if activated:
            ts = hi * (1 - trail)
            if ts > cur:
                cur = ts
        if fL[j] <= cur:
            return (cur / px - 1) * 100, j + 1, (lo / px - 1) * 100
    last = fC[m - 1] if hasattr(fC, "__len__") else fC
    return (last / px - 1) * 100, m, (lo / px - 1) * 100


# 四种假设组合（名字 → cons/gap），便于审计与页面统一引用
MODES = [
    ("旧口径（乐观日内·忽略跳空）", False, False),
    ("保守日内·忽略跳空", True, False),
    ("乐观日内·跳空成交", False, True),
    ("可实现口径（保守日内·跳空成交）", True, True),
]

MODE_OLD = "旧口径（乐观日内·忽略跳空）"
MODE_REAL = "可实现口径（保守日内·跳空成交）"


def sim_trail_lists(fl, fh, fc, px, stop=STOP, act=ACT, trail=TRAIL, maxfwd=MAXFWD,
                    cons=False, fO=None):
    """**list 模式**：与 `_selected_lab._sim_trail` 完全同形（默认 cons=False 逐位一致）。

    fl/fh = T+1..T+hold 的 low/high；fc = T+hold 收盘标量；fO = 前向开盘序列（给定时启用跳空修正）。
    返回 dict(win, pnl, hold, hit_tp, hit_stop, mae)，与 `_selected_lab._sim_trail` 同键。
    """
    hi = px
    lo = fl[0] if fl else px
    cur = px * (1 - stop)
    activated = (act <= 0)
    m = min(len(fl), len(fh))
    for j in range(m):
        # 跳空优先（两版都适用）：开盘已在止损线之下 → 以开盘价成交
        if fO is not None and fO[j] and fO[j] <= cur:
            return {"win": fO[j] > px, "pnl": (fO[j] / px - 1) * 100, "hold": j + 1,
                    "hit_tp": activated, "hit_stop": not activated,
                    "mae": (lo / px - 1) * 100}
        if cons:
            # 保守：先用「截至昨日」的止盈线判当日是否跌破，再上移
            if fl[j] <= cur:
                pnl = (cur / px - 1) * 100
                return {"win": pnl > 0, "pnl": pnl, "hold": j + 1, "hit_tp": activated,
                        "hit_stop": not activated, "mae": (lo / px - 1) * 100}
            if fh[j] > hi:
                hi = fh[j]
            if fl[j] < lo:
                lo = fl[j]
            if not activated and hi >= px * (1 + act):
                activated = True
            if activated:
                ts = hi * (1 - trail)
                if ts > cur:
                    cur = ts
            continue
        if fh[j] > hi:
            hi = fh[j]
        if fl[j] < lo:
            lo = fl[j]
        if not activated and hi >= px * (1 + act):
            activated = True
        if activated:
            ts = hi * (1 - trail)
            if ts > cur:
                cur = ts
        if fl[j] <= cur:
            pnl = (cur / px - 1) * 100
            return {"win": pnl > 0, "pnl": pnl, "hold": j + 1, "hit_tp": activated,
                    "hit_stop": not activated, "mae": (lo / px - 1) * 100}
    last = fc if fc is not None else (fl[-1] if fl else px)
    return {"win": last > px, "pnl": (last / px - 1) * 100, "hold": m,
            "hit_tp": activated, "hit_stop": False, "mae": (lo / px - 1) * 100}


def sim_trail_bars(k, i, px, stop=STOP, act=ACT, trail=TRAIL, maxfwd=MAXFWD,
                   cons=False, gap=False):
    """**bars 模式**：与 `_rbot` / `rev_pool._sim_trail` 同形（默认逐位一致）。

    ★ 与 list 模式的两处固有限制（必须保留才能复刻旧值，勿「顺手修正」）：
      · `lo` 从**信号日**的 low 起算（list 模式从 T+1 起算）→ 只影响 mae，不影响退出判定；
      · 越界时以 `k[-1].last` 兜底。
    cons/gap 语义同 `sim_trail_lists`。返回 dict(win, pnl, hold, hit_tp, hit_stop, mae)。
    """
    n = len(k)
    hi = px
    _l0 = k[i].get("low")
    lo = _l0 if _l0 else px
    cur = px * (1 - stop)
    activated = (act <= 0)
    j = 1
    while j <= maxfwd:
        if i + j >= n:
            last = k[-1]["last"]
            return {"win": last > px, "pnl": (last / px - 1) * 100, "hold": j - 1,
                    "hit_tp": activated, "hit_stop": False, "mae": (lo / px - 1) * 100}
        b = k[i + j]
        o = b.get("open")
        if gap and o and o <= cur:
            return {"win": o > px, "pnl": (o / px - 1) * 100, "hold": j,
                    "hit_tp": activated, "hit_stop": not activated,
                    "mae": (lo / px - 1) * 100}
        if cons:
            if b["low"] <= cur:
                pnl = (cur / px - 1) * 100
                return {"win": pnl > 0, "pnl": pnl, "hold": j, "hit_tp": activated,
                        "hit_stop": not activated, "mae": (lo / px - 1) * 100}
            if b["high"] > hi:
                hi = b["high"]
            if b["low"] < lo:
                lo = b["low"]
            if not activated and hi >= px * (1 + act):
                activated = True
            if activated:
                ts = hi * (1 - trail)
                if ts > cur:
                    cur = ts
            j += 1
            continue
        if b["high"] > hi:
            hi = b["high"]
        if b["low"] < lo:
            lo = b["low"]
        if not activated and hi >= px * (1 + act):
            activated = True
        if activated:
            ts = hi * (1 - trail)
            if ts > cur:
                cur = ts
        if b["low"] <= cur:
            pnl = (cur / px - 1) * 100
            return {"win": pnl > 0, "pnl": pnl, "hold": j, "hit_tp": activated,
                    "hit_stop": not activated, "mae": (lo / px - 1) * 100}
        j += 1
    last = k[i + maxfwd]["last"]
    return {"win": last > px, "pnl": (last / px - 1) * 100, "hold": maxfwd,
            "hit_tp": activated, "hit_stop": False, "mae": (lo / px - 1) * 100}


def four_pnl(fl, fh, fc, px, stop=STOP, act=ACT, trail=TRAIL, maxfwd=MAXFWD, fO=None):
    """一次给出四种假设下的单笔收益（%），顺序同 `MODES`。

    fO 为 None（或含 None）时，跳空两档退化为「忽略跳空」——调用方须自行保证 fO 完整，
    否则会在页面上把两档写成「相同」而掩盖问题；审计脚本已对 fO 缺失的样本整行剔除。
    """
    out = []
    for _name, cons, gap in MODES:
        r = sim_trail_lists(fl, fh, fc, px, stop, act, trail, maxfwd,
                            cons=cons, fO=(fO if gap else None))
        out.append(r["pnl"])
    return out


def run_mode(rows, mode, px_key="_close", stop=STOP, act=ACT, trail=TRAIL,
             hold=MAXFWD):
    """在一批面板行上跑某个假设组合，返回 (pnls, wr, mean)。

    `rows` 每行需含：fH/fL（前向 high/low）、fC 或 fc（到期收盘）、px_key（入场价）、fO（可选）。
    """
    _, cons, gap = mode
    pnls = []
    for r in rows:
        fC = r.get("fC", r.get("fc"))
        fO = r.get("fO") if gap else None
        v, _, _ = sim_exit(fC, r["fH"] if "fH" in r else r["fh"],
                           r["fL"] if "fL" in r else r["fl"],
                           r[px_key], stop, act, trail, hold, cons, fO)
        pnls.append(v)
    if not pnls:
        return [], 0.0, 0.0
    wr = 100.0 * sum(1 for x in pnls if x > 0) / len(pnls)
    return pnls, wr, sum(pnls) / len(pnls)
