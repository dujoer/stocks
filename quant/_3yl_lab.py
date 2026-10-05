#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
三连阴（量化错杀型）样本外回测实验室
=====================================

目的：回答「用户给的四套三连阴选股条件，到底能不能选出高胜率股票」。

数据源（全离线、真实）：
  quant/_txk_cache.json   全市场日K（5049 只 × ~251 根）
  quant/_stock_names.json code -> 名称（ST / 退 / 板块判定）
  quant/_name2sw2.json    名称 -> 申万二级行业（主线板块条件，124 行业）
  quant/_mktcap.json      流通市值快照（腾讯 qt，历史按价格缩放近似）

规则（严格按用户问财语句实现，未自行增删）：
  A 优质三连阴 : 非ST + 近3日收盘连续下跌 + 今日量<昨日<前日 + 流通市值20~500亿
                 + 收盘>MA60 + 剔北交所 + 剔名称含"退"
  B 普通三连阴 : 非ST + 近3日收盘连续下跌 + 剔北交所          （基准对照）
  C 高危三连阴 : 非ST + 近3日收盘连续下跌 + (近3日量持续放大 或 收盘<MA60)
  D 龙头主线   : A 条件 + 市值30~800亿 + 所属行业近20日等权涨幅排名全市场前5
                 + 行业内近20日涨幅>15% 的个股 ≥10 只
  ALL 全市场   : 非ST + 剔北交所（"随便买"绝对基准）

执行口径（可兑现，非偷看未来）：
  信号在收盘后产生 -> T+1 开盘买入；止损/止盈/持有N日 固定退出规则。
  同日既触止损又触止盈 -> 保守记止损。

诚实降级（页面必须标注）：
  * 利空过滤（近20日减持 / 监管问询 / 业绩预减）：本地仅 18 天历史，
    **不参与回测**（会让历史样本失真）；该条并入人工二次核对清单。
  * 流通市值为当前快照按价格缩放的历史近似（假设股本不变）。
  * 行业分类为当前申万二级静态映射（近似历史归属）。

产出：quant/3yl_lab.json（供 build_3yl.py 渲染实验室页面）
用法：python3 quant/_3yl_lab.py [--quick]
"""
from __future__ import annotations
import _txk
import os, sys, json, math, argparse, datetime, statistics
from collections import defaultdict

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, ".."))
sys.path.insert(0, _HERE)

CACHE = os.path.join(_HERE, "_txk_cache.json")
NAMES = os.path.join(_HERE, "_stock_names.json")
SW2 = os.path.join(_HERE, "_name2sw2.json")
MKT = os.path.join(_HERE, "_mktcap.json")
OUT = os.path.join(_HERE, "3yl_lab.json")

# 先验固定的默认退出参数（不通过网格挑选，防过拟合）
DEF_STOP, DEF_TARGET, DEF_HOLD = 0.05, 0.08, 5
GRID_STOP = [0.03, 0.05, 0.07, 0.10]
GRID_TARGET = [0.05, 0.08, 0.12, 0.20]
GRID_HOLD = [3, 5, 10]


# ---------------------------------------------------------------- 数据装载
def load_data():
    raw = _txk.load()
    names = json.load(open(NAMES, encoding="utf-8"))
    sw2 = json.load(open(SW2, encoding="utf-8"))
    mkt = {}
    if os.path.exists(MKT):
        mkt = json.load(open(MKT, encoding="utf-8")).get("caps", {})

    # code -> 行业
    ind = {}
    for c, nm in names.items():
        v = sw2.get(nm)
        if v:
            ind[c] = v

    data = {}       # code -> dict(date=..., o,h,l,c,v 列表)
    didx = {}       # code -> {date: i}
    all_dates = set()
    for c, kl in raw.items():
        if not kl or len(kl) < 30:
            continue
        kl = [k for k in kl if k.get("last") and k.get("volume") is not None]
        if len(kl) < 30:
            continue
        d = kl[0]["date"]
        data[c] = {
            "d": [k["date"] for k in kl],
            "o": [k.get("open") or k["last"] for k in kl],
            "h": [k.get("high") or k["last"] for k in kl],
            "l": [k.get("low") or k["last"] for k in kl],
            "c": [k["last"] for k in kl],
            "v": [k["volume"] for k in kl],
        }
        didx[c] = {k["date"]: i for i, k in enumerate(kl)}
        all_dates.update(data[c]["d"])
    dates = sorted(all_dates)
    return data, didx, dates, names, ind, mkt


def bad_code(code, nm):
    """北交所 / ST / 退市 判定"""
    if code.startswith("bj"):
        return True
    if not nm:
        return True
    if "ST" in nm or "退" in nm:
        return True
    return False


# ---------------------------------------------------------------- 收益计算
def outcome(arr, i, stop, target, hold, buy_i=None):
    """
    信号日 i（0-based，该股自身索引）。T+1 开盘买入。
    返回 dict(win, ret, mfe, mae, ok)
    """
    n = len(arr["c"])
    b = buy_i if buy_i is not None else i + 1
    if b >= n:
        return None
    buy = arr["o"][b]
    if not buy or buy <= 0:
        return None
    stop_px = buy * (1 - stop)
    tgt_px = buy * (1 + target)
    mfe, mae = 0.0, 0.0
    end = min(b + hold - 1, n - 1)
    for k in range(b, end + 1):
        hi, lo = arr["h"][k], arr["l"][k]
        mfe = max(mfe, hi / buy - 1)
        mae = min(mae, lo / buy - 1)
        if lo <= stop_px:                       # 保守：同日双触记止损
            return {"win": False, "ret": -stop, "mfe": mfe, "mae": mae,
                    "exit": "stop", "days": k - b + 1}
        if hi >= tgt_px:
            return {"win": True, "ret": target, "mfe": mfe, "mae": mae,
                    "exit": "target", "days": k - b + 1}
    last = arr["c"][end]
    r = last / buy - 1
    return {"win": r > 0, "ret": r, "mfe": mfe, "mae": mae,
            "exit": "expire", "days": end - b + 1}


def outcome_gap(arr, i, stop, target, hold, buy_i=None):
    """**可实现口径**：与 `outcome` 同规则，只修「跳空」。

    `outcome` 里两处乐观假设（本函数修掉）：
      ① 止损触发一律按 `stop_px` 成交 —— 若当日开盘已跳空跌破 stop_px，
         实际只能以**开盘价**卖出（比止损价更差）；
      ② 止盈触发一律按 `tgt_px` 成交 —— 若当日开盘已跳空高过 tgt_px，
         实际能以**开盘价**卖出（比目标价**更好**）。
    其余逐字不变：T+1 开盘买入、止损/止盈阈值、持有期、同日双触保守记止损。
    买入当日 k==b 时 op==buy，不可能误触发两侧判定（stop_px<buy<tgt_px）。
    """
    n = len(arr["c"])
    b = buy_i if buy_i is not None else i + 1
    if b >= n:
        return None
    buy = arr["o"][b]
    if not buy or buy <= 0:
        return None
    stop_px = buy * (1 - stop)
    tgt_px = buy * (1 + target)
    mfe, mae = 0.0, 0.0
    end = min(b + hold - 1, n - 1)
    for k in range(b, end + 1):
        hi, lo = arr["h"][k], arr["l"][k]
        op = arr["o"][k]
        mfe = max(mfe, hi / buy - 1)
        mae = min(mae, lo / buy - 1)
        if op and op <= stop_px:                # 跳空止损：只能按开盘价卖出
            return {"win": op > buy, "ret": op / buy - 1, "mfe": mfe, "mae": mae,
                    "exit": "stop_gap", "days": k - b + 1}
        if lo <= stop_px:                       # 日内触止损（保守序，与旧口径一致）
            return {"win": False, "ret": -stop, "mfe": mfe, "mae": mae,
                    "exit": "stop", "days": k - b + 1}
        if op and op >= tgt_px:                 # 跳空止盈：能按开盘价卖出（更好）
            return {"win": True, "ret": op / buy - 1, "mfe": mfe, "mae": mae,
                    "exit": "target_gap", "days": k - b + 1}
        if hi >= tgt_px:
            return {"win": True, "ret": target, "mfe": mfe, "mae": mae,
                    "exit": "target", "days": k - b + 1}
    last = arr["c"][end]
    r = last / buy - 1
    return {"win": r > 0, "ret": r, "mfe": mfe, "mae": mae,
            "exit": "expire", "days": end - b + 1}


def fwd_stats(arr, i, nd=5):
    """用户口径：T+1 收盘上涨 / 5日收盘上涨 / 5日内最大涨幅（相对信号日收盘）"""
    n = len(arr["c"])
    if i + nd >= n:
        return None
    c0 = arr["c"][i]
    if not c0:
        return None
    t1 = arr["c"][i + 1] / c0 - 1
    up5 = arr["c"][i + nd] / c0 - 1
    mx = max(arr["h"][k] for k in range(i + 1, i + nd + 1)) / c0 - 1
    mn = min(arr["l"][k] for k in range(i + 1, i + nd + 1)) / c0 - 1
    return {"t1": t1, "up5": up5, "max5": mx, "min5": mn}


# ---------------------------------------------------------------- 主回测
def run(quick=False):
    data, didx, dates, names, ind, mkt = load_data()
    codes = sorted(data.keys())
    print("[lab] 标的 %d  交易日 %d (%s ~ %s)" % (len(codes), len(dates), dates[0], dates[-1]))

    # 预筛（去掉 ST/北交所/无行业/无市值）
    uni = []
    for c in codes:
        nm = names.get(c, "")
        if bad_code(c, nm):
            continue
        if c not in mkt or not mkt[c].get("fmc"):
            continue
        uni.append(c)
    print("[lab] 可回测域 %d 只（剔 ST/北交所/无市值）" % len(uni))

    # 前缀和（MA60）
    psum = {}
    for c in uni:
        s, acc = [0.0], 0.0
        for x in data[c]["c"]:
            acc += x
            s.append(acc)
        psum[c] = s

    # 行业成员
    members = defaultdict(list)
    for c in uni:
        if c in ind:
            members[ind[c]].append(c)
    members = {k: v for k, v in members.items() if len(v) >= 10}
    print("[lab] 行业（成分≥10）%d 个" % len(members))

    dpos = {d: i for i, d in enumerate(dates)}
    N = len(dates)
    lo_i, hi_i = 60, N - 7
    if quick:
        lo_i = max(lo_i, N - 70)

    # ---- 每天的行业强度（近20日等权涨幅 + 涨幅>15%数量）
    ind_rank = {}   # date -> {行业: (r20等权, cnt>15%)}
    for di in range(lo_i - 1, hi_i + 1):
        if di < 20:
            continue
        acc = defaultdict(float)
        cnt = defaultdict(int)
        tot = defaultdict(int)
        for c in uni:
            ix = didx[c].get(dates[di])
            if ix is None or ix < 20:
                continue
            arr = data[c]
            c0 = arr["c"][ix - 20]
            if not c0:
                continue
            r = arr["c"][ix] / c0 - 1
            g = ind.get(c)
            if g in members:
                acc[g] += r
                tot[g] += 1
                if r > 0.15:
                    cnt[g] += 1
        day = {}
        for g, s in acc.items():
            if tot[g] >= 10:
                day[g] = (s / tot[g], cnt[g])
        ind_rank[dates[di]] = day

    # ---- 主循环
    buckets = {k: [] for k in ("A", "B", "C", "D", "ALL")}
    # ALL = "随便买"绝对基准：每天从域内随机抽 BASE_SAMPLE 只（固定种子，可复现）
    BASE_SAMPLE = 200
    abl = []        # 消融：A + 距MA60 阈值
    grid = {}       # (stop,target,hold) -> 各桶统计

    for di in range(lo_i, hi_i + 1):
        d = dates[di]
        dm1, dm2 = dates[di - 1], dates[di - 2]
        dp1 = dates[di + 1] if di + 1 < N else None
        dp5 = dates[di + 5] if di + 5 < N else None
        if not dp1 or not dp5:
            continue
        day_ind = ind_rank.get(d, {})
        # 主线行业：近20日等权涨幅前5 且 行业内>15%的个股≥10
        top5 = set()
        if day_ind:
            ordered = sorted(day_ind.items(), key=lambda kv: -kv[1][0])[:5]
            top5 = {g for g, (r, c15) in ordered if c15 >= 10}

        for c in uni:
            ix = didx[c].get(d)
            if ix is None or ix < 60:
                continue
            ix1 = didx[c].get(dm1)
            ix2 = didx[c].get(dm2)
            if ix1 is None or ix2 is None or ix1 != ix - 1 or ix2 != ix - 2:
                continue                      # 近3日有停牌跳空 -> 不算三连阴
            arr = data[c]
            C, V = arr["c"], arr["v"]
            if not (C[ix] < C[ix1] < C[ix2]):
                continue                      # 非三连阴
            if V[ix] <= 0 or V[ix1] <= 0 or V[ix2] <= 0:
                continue
            ib1 = didx[c].get(dp1)
            ib5 = didx[c].get(dp5)
            if ib1 is None or ib5 is None:
                continue

            ma60 = (psum[c][ix + 1] - psum[c][ix - 59]) / 60
            px = C[ix]
            shrink = V[ix] < V[ix1] < V[ix2]
            expand = V[ix] > V[ix1] > V[ix2]
            above = px > ma60

            # 历史流通市值近似
            mc = mkt[c]
            cap_close = mc.get("close") or px
            fmc = mc["fmc"] * (px / cap_close) if cap_close else mc["fmc"]

            fs = fwd_stats(arr, ix, 5)
            if fs is None:
                continue

            rec = {
                "code": c, "date": d, "px": px, "ma60": ma60,
                "fmc": fmc, "dist": px / ma60 - 1,
                "t1": fs["t1"], "up5": fs["up5"], "max5": fs["max5"], "min5": fs["min5"],
                "ix": ix, "ib1": ib1,
                "shrink": shrink, "above": above, "expand": expand,
                "cap_ok": (20 <= fmc <= 500), "ind": ind.get(c),
                "is_top5": bool(c in ind and ind[c] in top5),
                "fall": (1 - px / C[ix2 - 1]) if ix2 >= 1 and C[ix2 - 1] else 0.0,
            }

            # B 基准：普通三连阴
            buckets["B"].append(rec)
            # C 高危：放量 或 破 MA60
            if expand or (not above):
                buckets["C"].append(rec)
            # A 优质
            if shrink and above and 20 <= fmc <= 500:
                buckets["A"].append(rec)
                if c in ind and ind[c] in top5 and 30 <= fmc <= 800:
                    buckets["D"].append(rec)
                # 消融：距 MA60 阈值
                abl.append({"dist": rec["dist"], "t1": fs["t1"], "up5": fs["up5"],
                            "max5": fs["max5"], "code": c, "date": d})

    # ---- ALL 绝对基准（"随便买"，独立抽样循环，与三连阴无关）
    import random
    rnd = random.Random(20260929)
    for di in range(lo_i, hi_i + 1):
        if di + 5 >= N:
            continue
        d, dp1, dp5 = dates[di], dates[di + 1], dates[di + 5]
        for c in rnd.sample(uni, min(BASE_SAMPLE, len(uni))):
            ix = didx[c].get(d)
            if ix is None or ix < 60:
                continue
            ib1 = didx[c].get(dp1)
            ib5 = didx[c].get(dp5)
            if ib1 is None or ib5 is None:
                continue
            arr = data[c]
            px = arr["c"][ix]
            ma60 = (psum[c][ix + 1] - psum[c][ix - 59]) / 60
            mc = mkt[c]
            cap_close = mc.get("close") or px
            fmc = mc["fmc"] * (px / cap_close) if cap_close else mc["fmc"]
            fs = fwd_stats(arr, ix, 5)
            if fs is None:
                continue
            buckets["ALL"].append({
                "code": c, "date": d, "px": px, "ma60": ma60, "fmc": fmc,
                "dist": px / ma60 - 1, "t1": fs["t1"], "up5": fs["up5"],
                "max5": fs["max5"], "min5": fs["min5"], "ix": ix, "ib1": ib1,
            })

    print("[lab] 信号数  A=%d B=%d C=%d D=%d ALL=%d"
          % tuple(len(buckets[k]) for k in ("A", "B", "C", "D", "ALL")))

    # ---- 统计
    def summarize(rows, arrs, stop=DEF_STOP, target=DEF_TARGET, hold=DEF_HOLD,
                  dates_all=None, sample=None):
        if not rows:
            return {"n": 0}
        if sample and len(rows) > sample:
            import random as _r
            rows = _r.Random(7).sample(rows, sample)
        n = len(rows)
        outs = []
        for r in rows:
            o = outcome(arrs[r["code"]], r["ix"], stop, target, hold, buy_i=r["ib1"])
            if o:
                outs.append(o)
        if not outs:
            return {"n": n, "ok": 0}
        wins = sum(1 for o in outs if o["win"])
        rets = [o["ret"] for o in outs]
        res = {
            "n": n, "ok": len(outs),
            "t1_up": sum(1 for r in rows if r["t1"] > 0) / n,
            "up5": sum(1 for r in rows if r["up5"] > 0) / n,
            "max5": sum(r["max5"] for r in rows) / n,
            "min5": sum(r["min5"] for r in rows) / n,
            "win": wins / len(outs),
            "exp": sum(rets) / len(rets),
            "mfe": sum(o["mfe"] for o in outs) / len(outs),
            "mae": sum(o["mae"] for o in outs) / len(outs),
            "hold_d": sum(o["days"] for o in outs) / len(outs),
        }
        # 前后半（走前验证）
        if dates_all and n > 20:
            ds = sorted({r["date"] for r in rows})
            mid = ds[len(ds) // 2]
            h1 = [r for r in rows if r["date"] < mid]
            h2 = [r for r in rows if r["date"] >= mid]
            for tag, sub in (("h1", h1), ("h2", h2)):
                if len(sub) < 10:
                    continue
                oo = [outcome(arrs[r["code"]], r["ix"], stop, target, hold, buy_i=r["ib1"])
                      for r in sub]
                oo = [x for x in oo if x]
                if oo:
                    res[tag + "_win"] = sum(1 for x in oo if x["win"]) / len(oo)
                    res[tag + "_exp"] = sum(x["ret"] for x in oo) / len(oo)
                    res[tag + "_n"] = len(sub)
                res[tag + "_t1"] = sum(1 for r in sub if r["t1"] > 0) / len(sub)
                res[tag + "_up5"] = sum(1 for r in sub if r["up5"] > 0) / len(sub)
        return res

    arrs = data
    stat = {k: summarize(v, arrs, dates_all=dates) for k, v in buckets.items()}

    # ---- 网格敏感性（只展示，默认参数不挑选）
    grid = {}
    for st in GRID_STOP:
        for tg in GRID_TARGET:
            for hd in GRID_HOLD:
                key = "%d_%d_%d" % (int(st * 100), int(tg * 100), hd)
                row = {}
                for k in ("A", "B", "C", "D", "ALL"):
                    s = summarize(buckets[k], arrs, st, tg, hd, sample=6000)
                    row[k] = {"win": s.get("win"), "exp": s.get("exp"),
                              "n": s.get("n"), "sampled": 6000}
                grid[key] = row

    # ---- 条件消融：逐条定位哪条在加分 / 扣分
    B = buckets["B"]
    variants = [
        ("① 仅三连阴（基准）", lambda r: True),
        ("② +缩量（今日<昨日<前日）", lambda r: r["shrink"]),
        ("③ +站上MA60", lambda r: r["above"]),
        ("④ +流通市值20~500亿", lambda r: r["cap_ok"]),
        ("⑤ +缩量 & 站上MA60", lambda r: r["shrink"] and r["above"]),
        ("⑥ A全套（②+③+④）", lambda r: r["shrink"] and r["above"] and r["cap_ok"]),
        ("⑦ +放量（反向对照）", lambda r: r["expand"]),
        ("⑧ +跌破MA60（反向对照）", lambda r: not r["above"]),
        ("⑨ D主线（⑥+板块前5）", lambda r: r["shrink"] and r["above"] and r["is_top5"]),
    ]
    cond_abl = []
    for label, fn in variants:
        sub = [r for r in B if fn(r)]
        if len(sub) < 50:
            cond_abl.append({"label": label, "n": len(sub)})
            continue
        n = len(sub)
        oo = [outcome(arrs[r["code"]], r["ix"], DEF_STOP, DEF_TARGET, DEF_HOLD,
                      buy_i=r["ib1"]) for r in sub]
        oo = [x for x in oo if x]
        cond_abl.append({
            "label": label, "n": n,
            "t1_up": sum(1 for r in sub if r["t1"] > 0) / n,
            "up5": sum(1 for r in sub if r["up5"] > 0) / n,
            "max5": sum(r["max5"] for r in sub) / n,
            "win": (sum(1 for x in oo if x["win"]) / len(oo)) if oo else None,
            "exp": (sum(x["ret"] for x in oo) / len(oo)) if oo else None,
        })

    # ---- 消融：三连阴累计跌幅分档（检验"超跌反弹"是否成立）
    fall_abl = []
    for lo_f, hi_f, lab in ((0.0, 0.03, "跌 0~3%"), (0.03, 0.05, "跌 3~5%"),
                            (0.05, 0.08, "跌 5~8%"), (0.08, 0.12, "跌 8~12%"),
                            (0.12, 0.20, "跌 12~20%"), (0.20, 9.9, "跌 >20%")):
        sub = [r for r in B if lo_f <= r["fall"] < hi_f]
        if len(sub) < 50:
            continue
        n = len(sub)
        oo = [outcome(arrs[r["code"]], r["ix"], DEF_STOP, DEF_TARGET, DEF_HOLD,
                      buy_i=r["ib1"]) for r in sub]
        oo = [x for x in oo if x]
        rec_ab = {
            "label": lab, "n": n,
            "t1_up": sum(1 for r in sub if r["t1"] > 0) / n,
            "up5": sum(1 for r in sub if r["up5"] > 0) / n,
            "max5": sum(r["max5"] for r in sub) / n,
            "win": (sum(1 for x in oo if x["win"]) / len(oo)) if oo else None,
            "exp": (sum(x["ret"] for x in oo) / len(oo)) if oo else None,
        }
        # 前后半（走前验证：两半同向才允许写进规则）
        ds = sorted({r["date"] for r in sub})
        if len(ds) > 30:
            mid = ds[len(ds) // 2]
            for tag, part in (("h1", [r for r in sub if r["date"] < mid]),
                              ("h2", [r for r in sub if r["date"] >= mid])):
                if len(part) < 30:
                    continue
                pp = [outcome(arrs[r["code"]], r["ix"], DEF_STOP, DEF_TARGET,
                              DEF_HOLD, buy_i=r["ib1"]) for r in part]
                pp = [x for x in pp if x]
                rec_ab[tag + "_n"] = len(part)
                rec_ab[tag + "_t1"] = sum(1 for r in part if r["t1"] > 0) / len(part)
                rec_ab[tag + "_win"] = (sum(1 for x in pp if x["win"]) / len(pp)) if pp else None
                rec_ab[tag + "_exp"] = (sum(x["ret"] for x in pp) / len(pp)) if pp else None
        fall_abl.append(rec_ab)

    # ---- 改进版候选：跌幅 8~12% 档 × 其它条件（走前验证）
    def bucket_stats(sub, label):
        if len(sub) < 50:
            return {"label": label, "n": len(sub)}
        n = len(sub)
        oo = [outcome(arrs[r["code"]], r["ix"], DEF_STOP, DEF_TARGET, DEF_HOLD,
                      buy_i=r["ib1"]) for r in sub]
        oo = [x for x in oo if x]
        r0 = {
            "label": label, "n": n,
            "t1_up": sum(1 for r in sub if r["t1"] > 0) / n,
            "up5": sum(1 for r in sub if r["up5"] > 0) / n,
            "max5": sum(r["max5"] for r in sub) / n,
            "win": (sum(1 for x in oo if x["win"]) / len(oo)) if oo else None,
            "exp": (sum(x["ret"] for x in oo) / len(oo)) if oo else None,
        }
        ds = sorted({r["date"] for r in sub})
        if len(ds) > 30:
            mid = ds[len(ds) // 2]
            for tag, part in (("h1", [r for r in sub if r["date"] < mid]),
                              ("h2", [r for r in sub if r["date"] >= mid])):
                if len(part) < 30:
                    continue
                pp = [outcome(arrs[r["code"]], r["ix"], DEF_STOP, DEF_TARGET,
                              DEF_HOLD, buy_i=r["ib1"]) for r in part]
                pp = [x for x in pp if x]
                r0[tag + "_n"] = len(part)
                r0[tag + "_t1"] = sum(1 for r in part if r["t1"] > 0) / len(part)
                r0[tag + "_win"] = (sum(1 for x in pp if x["win"]) / len(pp)) if pp else None
                r0[tag + "_exp"] = (sum(x["ret"] for x in pp) / len(pp)) if pp else None
        return r0

    core = [r for r in B if 0.08 <= r["fall"] < 0.12]
    combo = [
        bucket_stats(core, "跌幅8~12%（单独）"),
        bucket_stats([r for r in core if r["above"]], "+站上MA60"),
        bucket_stats([r for r in core if r["shrink"]], "+缩量"),
        bucket_stats([r for r in core if r["cap_ok"]], "+市值20~500亿"),
        bucket_stats([r for r in core if r["above"] and r["shrink"]], "+站上MA60&缩量"),
        bucket_stats([r for r in core if r["above"] and r["cap_ok"]], "+站上MA60&市值"),
        bucket_stats([r for r in core if r["above"] and r["cap_ok"] and r["shrink"]],
                     "全条件（改进版A+）"),
    ]

    # ---- 消融：距 MA60 阈值
    abl_out = []
    for lim in (0.03, 0.05, 0.10, 0.20, 9.9):
        sub = [r for r in abl if r["dist"] <= lim]
        if len(sub) < 30:
            continue
        abl_out.append({
            "dist_max": lim if lim < 9 else None,
            "n": len(sub),
            "t1_up": sum(1 for r in sub if r["t1"] > 0) / len(sub),
            "up5": sum(1 for r in sub if r["up5"] > 0) / len(sub),
            "max5": sum(r["max5"] for r in sub) / len(sub),
        })

    out = {
        "generated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "window": {"from": dates[lo_i], "to": dates[hi_i], "days": hi_i - lo_i + 1},
        "universe": len(uni),
        "default": {"stop": DEF_STOP, "target": DEF_TARGET, "hold": DEF_HOLD},
        "stat": stat,
        "grid": grid,
        "cond_ablation": cond_abl,
        "ablation_fall": fall_abl,
        "combo_8_12": combo,
        "ablation_dist_ma60": abl_out,
        "signals": {k: len(v) for k, v in buckets.items()},
        "caveats": [
            "利空过滤（近20日减持/监管问询/业绩预减）本地仅18天历史，未参与回测，并入人工核对清单",
            "流通市值=当前快照×价格缩放的历史近似（假设股本不变）",
            "行业分类为当前申万二级静态映射（近似历史归属）",
            "T+1开盘买入；同日双触止损/止盈保守记止损",
        ],
    }
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("[lab] ->", OUT)
    for k in ("ALL", "B", "A", "C", "D"):
        s = stat[k]
        if s.get("n"):
            print("  %-3s n=%-6d T+1涨=%s  5日涨=%s  5日最大=%s  胜率=%s  期望=%s"
                  % (k, s["n"],
                     "%.1f%%" % (s["t1_up"] * 100), "%.1f%%" % (s["up5"] * 100),
                     "%+.2f%%" % (s["max5"] * 100), "%.1f%%" % (s["win"] * 100),
                     "%+.2f%%" % (s["exp"] * 100)))
            if s.get("h1_win") is not None:
                print("      走前验证 前半 胜率%.1f%% 期望%+.2f%% (n=%d) | 后半 胜率%.1f%% 期望%+.2f%% (n=%d)"
                      % (s["h1_win"] * 100, s["h1_exp"] * 100, s.get("h1_n", 0),
                         s["h2_win"] * 100, s["h2_exp"] * 100, s.get("h2_n", 0)))
    print("--- 跌幅分档（三连阴累计跌幅，检验超跌反弹）---")
    for r in fall_abl:
        line = ("  %-10s n=%-7d T+1涨=%5.1f%%  5日涨=%5.1f%%  5日最大=%+.2f%%  胜率=%5.1f%%  期望=%+.2f%%"
                % (r["label"], r["n"], r["t1_up"] * 100, r["up5"] * 100,
                   r["max5"] * 100, (r["win"] or 0) * 100, (r["exp"] or 0) * 100))
        if r.get("h1_win") is not None:
            line += ("\n              走前: 前半 T+1=%.1f%% 胜率%.1f%% 期望%+.2f%% | 后半 T+1=%.1f%% 胜率%.1f%% 期望%+.2f%%"
                     % (r["h1_t1"] * 100, r["h1_win"] * 100, r["h1_exp"] * 100,
                        r["h2_t1"] * 100, r["h2_win"] * 100, r["h2_exp"] * 100))
        print(line)
    print("--- 改进版候选（跌幅 8~12% 档 × 条件组合）---")
    for r in combo:
        if r.get("win") is None:
            print("  %-24s n=%d (样本不足)" % (r["label"], r.get("n", 0)))
            continue
        line = ("  %-24s n=%-6d T+1涨=%5.1f%%  胜率=%5.1f%%  期望=%+.2f%%"
                % (r["label"], r["n"], r["t1_up"] * 100, r["win"] * 100, r["exp"] * 100))
        if r.get("h1_win") is not None:
            line += ("\n                          走前: 前半 T+1=%.1f%% 期望%+.2f%% | 后半 T+1=%.1f%% 期望%+.2f%%"
                     % (r["h1_t1"] * 100, r["h1_exp"] * 100,
                        r["h2_t1"] * 100, r["h2_exp"] * 100))
        print(line)
    print("--- 条件消融（默认退出 止损5%/止盈8%/持有5日）---")
    for r in cond_abl:
        if r.get("win") is None:
            print("  %-26s n=%d (样本不足)" % (r["label"], r["n"]))
            continue
        print("  %-26s n=%-6d T+1涨=%5.1f%%  5日涨=%5.1f%%  胜率=%5.1f%%  期望=%+.2f%%"
              % (r["label"], r["n"], r["t1_up"] * 100, r["up5"] * 100,
                 r["win"] * 100, r["exp"] * 100))
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    a = ap.parse_args()
    run(a.quick)
