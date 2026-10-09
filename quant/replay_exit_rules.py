#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
退出规则回放：用**真实交割单**回答「如果当时执行了硬止损 / 移动止盈，结果会怎样」。

这是对复盘页建议②（硬止损 -7% + 移动止盈 + 限时）的**可证伪检验**，不是参数搜索。

为什么必须做、而不是拍脑袋给建议
--------------------------------
复盘结论是「亏损高度集中在少数失控单」（最差 5 笔占 -62,935）。但要证明
「加止损就能改善」必须回放：拿每一笔真实买入批次，在它真实的持有窗口内
重放规则，与实际结果对照。若回放后反而更差，说明建议②不成立 —— 结论必须接受被证伪。

口径（全部可复核，不估算、不编造）
--------------------------------
1. **批次**：FIFO 配对。买入建批次；卖出按 FIFO 消耗批次，并**按 exit 段拆分**
   （一笔买入被分两次卖 → 拆成两个子批次，各自持有到自己的实际卖出日）。
2. **窗口前持仓（成本不可考）**：起始日前就持有、交割单无建仓成本的卖出
   → **排除回放**（买入价未知，无法判定止损），单独计数并标注。
3. **价格路径锚定**：日K是**前复权**，绝对价与真实成交价有复权因子差 →
   用收益率链式锚定：P_t = 真实买入价 × (C_t / C_buy)，high/low 同比缩放。
   这样除权不影响止损触发判定（否则会凭空触发 / 漏触发）。
4. **T+1**：从买入日**下一个交易日**起才可卖出（A股规则）。
5. **成交假设（两档并列，绝不只报好看的那档）**：
   - 保守（跳空）：若当日开盘价已低于触发价 → 按开盘价成交（跳空无法按触发价成交）
   - 乐观（触发价）：按触发价成交
6. **费用**：卖出费率 = 佣金率(实测) + 印花税率(实测)，**按真实费率**、不写死；
   规则卖出会产生额外费用，计入回放结果。
7. **不调参**：主口径 = 建议②原值（止损 -7% / 峰值回撤 6% / 持有上限 20 日）。
   敏感性只做 -5% / -7% / -10% 三档并列展示，**标注为稳健性参考、不是选参依据**
   （项目红线：自动筛参数是主要噪声源）。

产出 quant/_stmt_exit_replay.json（供 build_exit_replay.py 渲染页面）。
"""
from __future__ import annotations
import json, os, sys
from collections import defaultdict

import _txk
import analyze_statement as A

Q = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(Q)
OUT = os.path.join(Q, "_stmt_exit_replay.json")

# 主口径（= 复盘页建议②原值，非拟合）
SL = 0.07      # 硬止损 -7%
TR = 0.06      # 移动止盈：自峰值回撤 6%
MAXHOLD = 20   # 最长持有 20 个交易日


def norm(d):
    return A.norm(d)


def build_lots(trades):
    """FIFO 建批次 + 按 exit 段拆子批次。

    返回 (lots, legacy_sells)：
      lots: [{code,name,buy_date,buy_price,qty,exit_date,exit_price,actual_net}]
      legacy_sells: 窗口前持仓的卖出笔数（成本不可考，排除回放）
    """
    queue = defaultdict(list)    # code -> [lot...]
    lots = []
    legacy_qty = 0
    legacy_sells = []
    for t in trades:
        cat = A.category(t["op"])
        if cat not in ("buy", "sell"):
            continue
        c = t["code"]
        if cat == "buy":
            queue[c].append(dict(code=c, name=t["name"], buy_date=t["date"],
                                 buy_price=t["price"], qty=t["qty"],
                                 buy_net=abs(t["net"]), remain=t["qty"]))
            continue
        # 卖出：FIFO 消耗
        need = abs(t["qty"])
        while need > 0 and queue[c]:
            lot = queue[c][0]
            take = min(need, lot["remain"])
            lots.append(dict(code=lot["code"], name=lot["name"],
                             buy_date=lot["buy_date"], buy_price=lot["buy_price"],
                             qty=take, buy_net=lot["buy_net"] * (take / lot["qty"]),
                             exit_date=t["date"], exit_price=t["price"],
                             exit_net=t["net"] * (take / abs(t["qty"]))))
            lot["remain"] -= take
            need -= take
            if lot["remain"] <= 0:
                queue[c].pop(0)
        if need > 0:
            # 无对应买入 → 窗口前持仓，成本不可考
            legacy_qty += need
            legacy_sells.append(dict(code=c, name=t["name"], date=t["date"],
                                     qty=need, price=t["price"]))
    # 期末仍持有的批次（未平仓）
    for c, lst in queue.items():
        for lot in lst:
            if lot["remain"] > 0:
                lots.append(dict(code=lot["code"], name=lot["name"],
                                 buy_date=lot["buy_date"], buy_price=lot["buy_price"],
                                 qty=lot["remain"],
                                 buy_net=lot["buy_net"] * (lot["remain"] / lot["qty"]),
                                 exit_date=None, exit_price=None, exit_net=None))
    return lots, legacy_sells, legacy_qty


def path_map(cache, code, buy_date, end_date):
    """取该股 [buy_date, end_date] 的日K路径（相对买入日收盘的比值序列）。

    返回 [(date, o_r, h_r, l_r, c_r)]，r = 相对买入日收盘价的比值；
    首日 c_r = 1.0。缺数据返回 []（不可回放）。
    """
    arr = cache.get(A.mkt_prefix(code)) or []
    if not arr:
        return []
    idxs = {}
    for i, b in enumerate(arr):
        idxs[b["date"].replace("-", "")] = i
    bi = idxs.get(buy_date)
    if bi is None:
        return []
    cb = arr[bi].get("last")
    if not cb:
        return []
    out = []
    for b in arr[bi:]:
        d = b["date"].replace("-", "")
        if d > end_date:
            break
        c = b.get("last") or cb
        out.append((d,
                    (b.get("open") or c) / cb,
                    (b.get("high") or c) / cb,
                    (b.get("low") or c) / cb,
                    c / cb))
    return out


def real_close(cache, code, date):
    """该股 <= date 的最后一个真实收盘价（非前复权锚定价，用于未平仓批次估值）。"""
    arr = cache.get(A.mkt_prefix(code)) or []
    last = None
    for b in arr:
        if b["date"].replace("-", "") <= date:
            last = b.get("last")
        else:
            break
    return last


def replay_lot(lot, path, sl=SL, tr=TR, maxhold=MAXHOLD):
    """在真实持有窗口内重放规则。

    返回 dict(trigger, t_date, t_price_opt, t_price_cons, hold_days)
      trigger: '止损' / '止盈' / '超时' / None(未触发 → 用实际退出)
    """
    bp = lot["buy_price"]
    end = lot["exit_date"] or path[-1][0]
    if len(path) < 2:
        return dict(trigger=None, t_date=end, t_price_opt=None, t_price_cons=None,
                    hold_days=0, note="路径不足")
    # 从 T+1 开始（A股 T+1）
    peak = 1.0
    for k, (d, o_r, h_r, l_r, c_r) in enumerate(path[1:], start=1):
        if d > end:
            break
        peak = max(peak, c_r)
        # ① 硬止损（优先：先保命）
        if l_r <= (1.0 - sl):
            trig_px = bp * (1.0 - sl)
            px_opt = trig_px
            open_px = bp * o_r
            px_cons = min(open_px, trig_px)   # 跳空：开盘已更低则按开盘
            return dict(trigger="止损", t_date=d, t_price_opt=px_opt,
                        t_price_cons=px_cons, hold_days=k)
        # ② 移动止盈（仅在有浮盈时启用：peak > 1）
        if peak > 1.0 and c_r <= peak * (1.0 - tr):
            trig_px = bp * peak * (1.0 - tr)
            px_opt = trig_px
            open_px = bp * o_r
            px_cons = min(open_px, trig_px)
            return dict(trigger="止盈", t_date=d, t_price_opt=px_opt,
                        t_price_cons=px_cons, hold_days=k)
        # ③ 超时
        if k >= maxhold:
            px = bp * c_r
            return dict(trigger="超时", t_date=d, t_price_opt=px,
                        t_price_cons=px, hold_days=k)
    return dict(trigger=None, t_date=end, t_price_opt=None, t_price_cons=None,
                hold_days=len(path) - 1)


def summarize(pairs, key):
    """pairs: [(actual_pnl, replay_pnl, qty...)] → 统计。"""
    a = [p[0] for p in pairs]
    r = [p[1] for p in pairs]
    def _st(v):
        w = [x for x in v if x > 0]
        l = [x for x in v if x <= 0]
        gw, gl = sum(w), sum(l)
        return dict(total=sum(v), n=len(v), n_win=len(w), n_loss=len(l),
                    winrate=100.0 * len(w) / len(v) if v else 0,
                    gross_win=gw, gross_loss=gl,
                    profit_factor=gw / abs(gl) if gl else 0,
                    avg_win=gw / len(w) if w else 0,
                    avg_loss=gl / len(l) if l else 0,
                    payoff=(gw / len(w)) / abs(gl / len(l)) if w and l else 0,
                    expectancy=sum(v) / len(v) if v else 0,
                    max_win=max(w) if w else 0,
                    max_loss=min(l) if l else 0)
    return dict(actual=_st(a), replay=_st(r))


def main():
    stmt = sys.argv[1] if len(sys.argv) > 1 else A.DEFAULT_STMT
    print("[1/5] 解析交割单 ...", flush=True)
    trades = A.parse(stmt)
    stock = [t for t in trades if A.category(t["op"]) in ("buy", "sell")]
    buy_amt = sum(t["amt"] for t in trades if A.category(t["op"]) == "buy")
    sell_amt = sum(t["amt"] for t in trades if A.category(t["op"]) == "sell")
    fee_all = sum(t["fee"] for t in trades)
    tax_all = sum(t["tax"] for t in trades)
    misc_all = sum(t["misc"] for t in trades)
    # 实测费率（不写死）
    comm_rate = fee_all / (buy_amt + sell_amt) if (buy_amt + sell_amt) else 0.0
    tax_rate = tax_all / sell_amt if sell_amt else 0.0
    misc_rate = misc_all / sell_amt if sell_amt else 0.0
    sell_fee = comm_rate + tax_rate + misc_rate
    print("    实测费率：佣金 %.5f%% / 印花税 %.5f%% / 杂费 %.5f%% → 卖出端合计 %.5f%%"
          % (100 * comm_rate, 100 * tax_rate, 100 * misc_rate, 100 * sell_fee))

    print("[2/5] FIFO 建批次（按 exit 段拆分）...", flush=True)
    lots, legacy_sells, legacy_qty = build_lots(trades)
    print("    可回放批次 %d 个；窗口前持仓卖出 %d 笔（%d 股，成本不可考 → 排除）"
          % (len(lots), len(legacy_sells), legacy_qty))

    print("[3/5] 载入日K（统一层 _txk.py）...", flush=True)
    asof = trades[-1]["date"]
    ymd = "%s-%s-%s" % (asof[:4], asof[4:6], asof[6:8])
    _txk.set_asof(ymd)
    cache = _txk.load()
    if not cache:
        print("    ⚠ 日K缓存缺失或陈旧 → 无法回放，退出")
        return
    print("    标的 %d 只" % len(cache))

    print("[4/5] 回放规则（止损 %.0f%% / 峰值回撤 %.0f%% / 上限 %d 日）..."
          % (100 * SL, 100 * TR, MAXHOLD), flush=True)
    rows = []
    skipped = 0
    for lot in lots:
        end = lot["exit_date"] or asof
        path = path_map(cache, lot["code"], lot["buy_date"], end)
        if not path:
            # ETF / 基金：本地日K缓存只含个股（实测 9 个批次：588810 / 510360 / 159801 …）。
            # 规则无法回放（无价格路径）→ **按实际结果计入基准**，对两口径都不产生改善，
            # 以免「实际」基准漏算这批交易而虚报规则效果。
            if lot["exit_net"] is None:
                skipped += 1      # 在持且无法定价：不臆造，直接跳过并计数
                continue
            actual = lot["exit_net"] - lot["buy_net"]
            rows.append(dict(
                code=lot["code"], name=lot["name"], qty=lot["qty"],
                buy_date=lot["buy_date"], buy_price=lot["buy_price"],
                exit_date=lot["exit_date"], exit_price=lot["exit_price"],
                trigger=None, t_date=None, t_price_opt=None, t_price_cons=None,
                hold_actual=None, actual=round(actual, 2),
                replay_opt=round(actual, 2), replay_cons=round(actual, 2),
                anchor_last=None, real_last=None, no_path=True))
            continue
        rp = replay_lot(lot, path)
        q = lot["qty"]
        # 实际：卖出净得 - 买入成本（买入成本按批次占比摊）
        if lot["exit_net"] is not None:
            actual = lot["exit_net"] - lot["buy_net"]
            actual_px = lot["exit_price"]
        else:
            # 未平仓：用**真实期末收盘价**（不是前复权锚定价 —— 锚定价含复权因子，
            # 与真实市值口径不一致；锚定价只用于规则触发判定，不用于估值）
            px_end = real_close(cache, lot["code"], asof)
            if px_end is None:
                px_end = lot["buy_price"] * path[-1][4]
            actual = q * px_end - lot["buy_net"]
            actual_px = px_end
        # 回放：若规则未触发 → 与实际相同（含原费用口径）
        if rp["trigger"] is None or rp["t_price_opt"] is None:
            rp_pnl_opt = actual
            rp_pnl_cons = actual
            trig = None
        else:
            trig = rp["trigger"]
            gross_opt = q * rp["t_price_opt"]
            gross_cons = q * rp["t_price_cons"]
            rp_pnl_opt = gross_opt * (1 - sell_fee) - lot["buy_net"]
            rp_pnl_cons = gross_cons * (1 - sell_fee) - lot["buy_net"]
        rows.append(dict(
            code=lot["code"], name=lot["name"], qty=q,
            buy_date=lot["buy_date"], buy_price=lot["buy_price"],
            exit_date=lot["exit_date"], exit_price=actual_px,
            trigger=trig, t_date=rp["t_date"] if trig else None,
            t_price_opt=rp["t_price_opt"], t_price_cons=rp["t_price_cons"],
            hold_actual=rp["hold_days"],
            actual=round(actual, 2),
            replay_opt=round(rp_pnl_opt, 2),
            replay_cons=round(rp_pnl_cons, 2),
            anchor_last=round(lot["buy_price"] * path[-1][4], 4),
            real_last=real_close(cache, lot["code"], path[-1][0]),
        ))
    print("    回放 %d 个批次，跳过 %d 个（无日K路径）" % (len(rows), skipped))

    # ── 汇总（保守口径为主结论，乐观口径并列）──
    pairs_cons = [(r["actual"], r["replay_cons"]) for r in rows]
    pairs_opt = [(r["actual"], r["replay_opt"]) for r in rows]
    st_cons = summarize(pairs_cons, "cons")
    st_opt = summarize(pairs_opt, "opt")

    # 触发分布
    trig_cnt = defaultdict(int)
    for r in rows:
        trig_cnt[r["trigger"] or "未触发"] += 1

    # 敏感性：止损档位 -5 / -7 / -10（止盈与上限固定）—— 稳健性参考，非选参
    sens = []
    for sl in (0.05, 0.07, 0.10):
        tot = 0.0
        for lot in lots:
            end = lot["exit_date"] or asof
            path = path_map(cache, lot["code"], lot["buy_date"], end)
            if not path:
                continue
            rp = replay_lot(lot, path, sl=sl)
            q = lot["qty"]
            if lot["exit_net"] is not None:
                actual = lot["exit_net"] - lot["buy_net"]
            else:
                px = real_close(cache, lot["code"], asof) or lot["buy_price"] * path[-1][4]
                actual = q * px - lot["buy_net"]
            if rp["trigger"] is None or rp["t_price_cons"] is None:
                tot += actual
            else:
                tot += q * rp["t_price_cons"] * (1 - sell_fee) - lot["buy_net"]
        sens.append(dict(sl=round(100 * sl, 1), total=round(tot, 2)))

    # 前复权锚定偏差披露：锚定价 vs 真实收盘（除权/分红会导致偏离 → 诚实标出影响面）
    devs = [abs(r["anchor_last"] / r["real_last"] - 1) for r in rows if r.get("real_last")]
    devs.sort()
    dev_stat = dict(n=len(devs),
                    over2pct=sum(1 for d in devs if d > 0.02),
                    median=round(100 * devs[len(devs) // 2], 3) if devs else 0,
                    p90=round(100 * devs[int(len(devs) * 0.9)], 3) if devs else 0,
                    max=round(100 * devs[-1], 3) if devs else 0)

    out = dict(
        meta=dict(stmt=os.path.basename(stmt), asof=asof,
                  n_lots=len(rows), n_skipped=skipped,
                  n_legacy_sells=len(legacy_sells), legacy_qty=legacy_qty,
                  sl=SL, tr=TR, maxhold=MAXHOLD,
                  comm_rate=comm_rate, tax_rate=tax_rate, misc_rate=misc_rate,
                  sell_fee=sell_fee, anchor_dev=dev_stat),
        stats=dict(cons=st_cons, opt=st_opt),
        trig_cnt=dict(trig_cnt),
        sens=sens,
        rows=rows,
    )
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False)

    print("\n=== 回放结果（保守口径：跳空按开盘价成交）===")
    a, r = st_cons["actual"], st_cons["replay"]
    print("实际已实现   %+.2f（%d 笔，胜率 %.1f%%，盈亏比 %.2f，盈利因子 %.2f）"
          % (a["total"], a["n"], a["winrate"], a["payoff"], a["profit_factor"]))
    print("规则回放     %+.2f（胜率 %.1f%%，盈亏比 %.2f，盈利因子 %.2f）"
          % (r["total"], r["winrate"], r["payoff"], r["profit_factor"]))
    print("改善         %+.2f" % (r["total"] - a["total"]))
    print("最大单笔亏损 %.2f → %.2f" % (a["max_loss"], r["max_loss"]))
    print("触发分布：", dict(trig_cnt))
    print("止损档位敏感性（保守口径总额）：", [(s["sl"], s["total"]) for s in sens])
    print("前复权锚定偏差：可比 %d 个批次，>2%% 的 %d 个，中位 %.3f%% / 90分位 %.3f%% / 最大 %.3f%%"
          % (dev_stat["n"], dev_stat["over2pct"], dev_stat["median"],
             dev_stat["p90"], dev_stat["max"]))
    print("\n[out]", OUT)


if __name__ == "__main__":
    main()
