# -*- coding: utf-8 -*-
"""
个股信号池 · 候选聚合（第一步）
三路信号合流 → 候选池 → 输出待拉行情的股票代码

信号源：
  1. 中报增减持（季频）  quant/q2_full/_merged_shareholder.json 的 holdChange（Q2↔Q1 环比）
  2. 高管增减持（日频）  quant/exec_chg/*.json  近 N 日 records（dir=增持/减持）
  3. 大宗交易（日频）    quant/block_chg/*.json 近 N 日 rows（discount/buyer/seller）

输出：
  quant/picks/candidates_{D}.json   候选池（含三路信号明细与信号分）
  quant/picks/_codes_{D}.txt        待拉行情的代码清单（逗号分批，每批 25）

用法：
  python quant/gen_picks.py --date 2026-09-10 [--window 20] [--top 40]
"""
import os
import re
import json
import glob
import argparse
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
Q2 = os.path.join(ROOT, "quant", "q2_full", "_merged_shareholder.json")
C2I = os.path.join(ROOT, "quant", "q2_full", "_code2industry.json")
EXEC_DIR = os.path.join(ROOT, "quant", "exec_chg")
BLOCK_DIR = os.path.join(ROOT, "quant", "block_chg")
OUT_DIR = os.path.join(ROOT, "quant", "picks")


def load_json(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def recent_dates(dirpath, pattern, window, end_date):
    """取目录里 <= end_date 的最近 window 个日期文件"""
    files = glob.glob(os.path.join(dirpath, pattern))
    ds = set()
    for f in files:
        m = re.search(r"(\d{4}-\d{2}-\d{2})", os.path.basename(f))
        if m:
            ds.add(m.group(1))
    ds = sorted(d for d in ds if d <= end_date)
    return ds[-window:]


# ---------------- 1) 中报（Q2）增减持 ----------------
def load_q2():
    """返回 code -> {addCnt, cutCnt, addShares, cutShares, topAdd:[names]}"""
    if not os.path.exists(Q2):
        return {}
    m = load_json(Q2)
    out = {}
    for code, v in m.items():
        holders = v.get("top10FloatShareholders") or v.get("top10Shareholders") or []
        add_cnt = cut_cnt = 0
        add_sh = cut_sh = 0
        names = []
        for h in holders:
            chg = h.get("holdChange") or 0
            sh = h.get("holdShares") or 0
            if chg > 0:
                add_cnt += 1
                add_sh += chg
                names.append((h.get("name", ""), chg))
            elif chg < 0:
                cut_cnt += 1
                cut_sh += abs(chg)
        if add_cnt or cut_cnt:
            names.sort(key=lambda x: -x[1])
            out[code] = {
                "addCnt": add_cnt, "cutCnt": cut_cnt,
                "addShares": add_sh, "cutShares": cut_sh,
                "topAdd": [n for n, _ in names[:5]],
                "name": v.get("name", ""),
            }
    return out


# ---------------- 2) 高管增减持（近 N 日） ----------------
def load_exec(dates):
    """返回 code -> {buyCnt, sellCnt, buyShares, sellShares, lastDir, lastDate, sw1, sw2, name}"""
    out = {}
    for d in dates:
        p = os.path.join(EXEC_DIR, f"{d}.json")
        if not os.path.exists(p):
            continue
        try:
            j = load_json(p)
        except Exception:
            continue
        for r in j.get("records", []):
            code = r.get("code")
            if not code:
                continue
            e = out.setdefault(code, {
                "name": r.get("name", ""), "sw1": r.get("sw1", ""), "sw2": r.get("sw2", ""),
                "buyCnt": 0, "sellCnt": 0, "buyShares": 0.0, "sellShares": 0.0,
                "lastDir": "", "lastDate": "", "managers": [],
            })
            e["name"] = e["name"] or r.get("name", "")
            e["sw1"] = e["sw1"] or r.get("sw1", "")
            e["sw2"] = e["sw2"] or r.get("sw2", "")
            sh = float(r.get("shares") or 0)
            if r.get("dir") == "增持":
                e["buyCnt"] += 1
                e["buyShares"] += sh
            else:
                e["sellCnt"] += 1
                e["sellShares"] += sh
            dec = str(r.get("declare") or "")
            if dec > e["lastDate"]:
                e["lastDate"] = dec
                e["lastDir"] = r.get("dir", "")
            if r.get("manager") and r["manager"] not in e["managers"]:
                e["managers"].append(r["manager"])
    return out


# ---------------- 3) 大宗交易（近 N 日） ----------------
def load_block(dates):
    """返回 code -> {cnt, value, instBuyCnt, instBuyValue, instSellCnt, avgDiscount, premCnt, lastDate, name}"""
    out = {}
    for d in dates:
        p = os.path.join(BLOCK_DIR, f"{d}.json")
        if not os.path.exists(p):
            continue
        try:
            j = load_json(p)
        except Exception:
            continue
        for r in j.get("rows", []):
            code = r.get("code")
            if not code:
                continue
            b = out.setdefault(code, {
                "name": r.get("name", ""), "cnt": 0, "value": 0.0,
                "instBuyCnt": 0, "instBuyValue": 0.0, "instSellCnt": 0, "instSellValue": 0.0,
                "discSum": 0.0, "premCnt": 0, "lastDate": "", "price": 0.0, "chgPct": None,
            })
            b["name"] = b["name"] or r.get("name", "")
            val = float(r.get("value") or 0)
            b["cnt"] += 1
            b["value"] += val
            disc = float(r.get("discount") or 0)
            b["discSum"] += disc
            if disc < 0:
                b["premCnt"] += 1
            buyer = str(r.get("buyer") or "")
            seller = str(r.get("seller") or "")
            if "机构" in buyer:
                b["instBuyCnt"] += 1
                b["instBuyValue"] += val
            if "机构" in seller:
                b["instSellCnt"] += 1
                b["instSellValue"] += val
            if d > b["lastDate"]:
                b["lastDate"] = d
                b["price"] = float(r.get("price") or 0)
                b["chgPct"] = r.get("changePercent")
    for v in out.values():
        v["avgDiscount"] = round(v["discSum"] / v["cnt"], 3) if v["cnt"] else 0.0
        del v["discSum"]
    return out


# ---------------- 4) 龙虎榜机构方向（近 N 日） ----------------
def load_lhb_inst(dates):
    """近 N 日龙虎榜机构席位（jg）→ code -> {instBuy, netBuy, days, branchMax, lastDate}"""
    out = {}
    for d in dates:
        p = os.path.join(ROOT, "quant", "lhb", f"{d}.json")
        if not os.path.exists(p):
            continue
        try:
            j = load_json(p)
        except Exception:
            continue
        for r in (j.get("data", {}) or {}).get("jg", []) or []:
            code = r.get("code")
            if not code:
                continue
            e = out.setdefault(code, {
                "name": r.get("name", ""), "instBuy": 0.0, "netBuy": 0.0,
                "days": 0, "branchMax": 0, "lastDate": "",
            })
            e["name"] = e["name"] or r.get("name", "")
            e["instBuy"] += float(r.get("instBuyAmt") or 0)
            e["netBuy"] += float(r.get("netBuyAmt") or 0)
            e["days"] += 1
            e["branchMax"] = max(e["branchMax"], int(r.get("instBuyBranchCount") or 0))
            if d > e["lastDate"]:
                e["lastDate"] = d
    return out


# ---------------- 5) 龙虎榜游资方向（近 N 日） ----------------
def load_youzi(dates):
    """近 N 日龙虎榜营业部（yyb）→ code -> {seatCnt, starCnt, buy, seats:[], lastDate}

    yyb 一条记录里 code 可能是多只股票（分号分隔），buyAmt 为该营业部当日买入合计，
    这里按股票数均摊，避免同一笔钱在多只股票上重复计入。
    同时用 web/shareholder/data/person_index.json 的游资席位库标记「知名席位」。
    """
    stars = {}
    pi = os.path.join(ROOT, "web", "shareholder", "data", "person_index.json")
    if os.path.exists(pi):
        try:
            for y in (load_json(pi) or {}).get("youzi", []) or []:
                stars[y.get("name", "")] = {
                    "freq": y.get("freq", 0), "totalBuy": y.get("totalBuy", 0.0),
                    "star": bool(y.get("star")),
                }
        except Exception:
            stars = {}

    out = {}
    for d in dates:
        p = os.path.join(ROOT, "quant", "lhb", f"{d}.json")
        if not os.path.exists(p):
            continue
        try:
            j = load_json(p)
        except Exception:
            continue
        for r in (j.get("data", {}) or {}).get("yyb", []) or []:
            raw = r.get("code") or ""
            codes = [c for c in raw.split(";") if c]
            if not codes:
                continue
            amt = float(r.get("buyAmt") or 0) / len(codes)
            seat = r.get("name", "")
            is_star = seat in stars and stars[seat]["star"]
            for c in codes:
                e = out.setdefault(c, {
                    "seatCnt": 0, "starCnt": 0, "buy": 0.0, "seats": [], "lastDate": "",
                })
                e["seatCnt"] += 1
                e["buy"] += amt
                if is_star:
                    e["starCnt"] += 1
                if seat and seat not in e["seats"]:
                    e["seats"].append(seat)
                if d > e["lastDate"]:
                    e["lastDate"] = d
    for v in out.values():
        v["seats"] = v["seats"][:5]
    return out, stars
def sig_scores(q2, ex, bl, inst, yz):
    """五路信号各自 0~100 的归一化强度 + 命中标记"""
    s = {"q2": 0.0, "exec": 0.0, "block": 0.0, "inst": 0.0, "youzi": 0.0}
    hits = []

    # 中报：加仓家数为主，减仓扣分
    if q2:
        add = q2["addCnt"]
        cut = q2["cutCnt"]
        if add > 0:
            s["q2"] = min(100.0, add * 25.0) - min(25.0, cut * 8.0)
            s["q2"] = max(0.0, s["q2"])
            if add >= 2 or (add == 1 and cut == 0):
                hits.append("中报加仓")
        elif cut >= 3:
            s["q2"] = 0.0

    # 高管：净增持笔数/股数
    if ex:
        net_cnt = ex["buyCnt"] - ex["sellCnt"]
        net_sh = ex["buyShares"] - ex["sellShares"]
        if net_cnt > 0:
            s["exec"] = max(0.0, min(100.0, net_cnt * 20.0 + (20.0 if net_sh > 0 else 0.0)))
            hits.append("高管增持")
        elif net_cnt == 0 and net_sh > 0:
            s["exec"] = 20.0      # 笔数持平但股数净增，弱正面
            hits.append("高管净增持")
        else:
            s["exec"] = 0.0       # 净减持笔数更多 → 无正面分（风险扣分在 build 阶段处理）

    # 大宗：机构买入 + 低折价/溢价为正面；机构卖出 + 高折价为负面
    if bl:
        v = bl["value"]
        ib = bl["instBuyValue"]
        isl = bl["instSellValue"]
        disc = bl["avgDiscount"]
        pos = 0.0
        if ib > 0:
            pos += min(60.0, ib / 5e7 * 40.0)   # 机构买入 5000万 → 40 分
        if disc < 0:
            pos += 25.0                          # 溢价成交
        elif disc < 3:
            pos += 12.0                          # 低折价
        elif disc > 8:
            pos -= 20.0                          # 高折价
        if isl > ib:
            pos -= min(30.0, (isl - ib) / 5e7 * 20.0)
        s["block"] = max(0.0, min(100.0, 30.0 + pos))
        if ib > 0 or disc < 0:
            hits.append("大宗机构买入" if ib > 0 else "大宗溢价")

    # 机构方向（龙虎榜机构席位）：净买入金额 + 机构席位数 + 上榜天数
    if inst:
        net = float(inst.get("netBuy") or 0)
        if net > 0:
            v = 0.0
            v += min(45.0, net / 1e8 * 30.0)                       # 净买 1 亿 → 30 分
            v += min(30.0, (inst.get("branchMax") or 0) * 10.0)     # 每个机构席位 10 分
            v += min(25.0, (inst.get("days") or 0) * 12.0)          # 每次上榜 12 分
            s["inst"] = max(0.0, min(100.0, v))
            hits.append("机构净买入")

    # 游资方向（龙虎榜营业部）：知名席位现身 + 买入额 + 席位家数
    if yz:
        v = 0.0
        v += min(50.0, (yz.get("starCnt") or 0) * 25.0)             # 知名席位每次 25 分
        v += min(30.0, float(yz.get("buy") or 0) / 1e8 * 20.0)      # 买入 1 亿 → 20 分
        v += min(20.0, (yz.get("seatCnt") or 0) * 4.0)              # 每个席位 4 分
        if v > 0:
            s["youzi"] = max(0.0, min(100.0, v))
            if yz.get("starCnt"):
                hits.append("知名游资席位")
    return s, hits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True, help="数据日期 YYYY-MM-DD")
    ap.add_argument("--window", type=int, default=20, help="日频信号回溯交易日数")
    ap.add_argument("--top", type=int, default=40, help="输出候选数量（拉行情规模）")
    args = ap.parse_args()
    D, W, TOP = args.date, args.window, args.top

    os.makedirs(OUT_DIR, exist_ok=True)

    c2i = load_json(C2I) if os.path.exists(C2I) else {}
    q2map = load_q2()
    ex_dates = recent_dates(EXEC_DIR, "*.json", W, D)
    bl_dates = recent_dates(BLOCK_DIR, "*.json", W, D)
    lhb_dates = recent_dates(os.path.join(ROOT, "quant", "lhb"), "*.json", W, D)
    exmap = load_exec(ex_dates)
    blmap = load_block(bl_dates)
    instmap = load_lhb_inst(lhb_dates)
    yzmap, yz_stars = load_youzi(lhb_dates)

    codes = set(q2map) | set(exmap) | set(blmap) | set(instmap) | set(yzmap)
    cands = []
    for code in codes:
        q2 = q2map.get(code)
        ex = exmap.get(code)
        bl = blmap.get(code)
        inst = instmap.get(code)
        yz = yzmap.get(code)
        s, hits = sig_scores(q2, ex, bl, inst, yz)
        if not hits:
            continue  # 无任何正面信号，跳过
        name = (ex or bl or inst or q2 or {}).get("name", "") or (q2 or {}).get("name", "")
        sw1 = (ex or {}).get("sw1", "") or ""
        if not sw1:
            ci = c2i.get(code)
            sw1 = ci if isinstance(ci, str) else ((ci or {}).get("sw1", ""))
        sw2 = (ex or {}).get("sw2", "") or ""
        # 主轨归属：机构信号强于游资则用机构轨，反之游资轨，两者都有则记 both
        if s["inst"] >= s["youzi"] and s["inst"] > 0:
            track = "inst"
        elif s["youzi"] > 0:
            track = "youzi"
        else:
            track = "base"
        sig_total = (s["q2"] * 0.20 + s["exec"] * 0.20 + s["block"] * 0.20
                     + s["inst"] * 0.25 + s["youzi"] * 0.15)
        cands.append({
            "code": code, "name": name, "sw1": sw1, "sw2": sw2,
            "q2": q2, "exec": ex, "block": bl, "inst": inst, "youzi": yz,
            "youziSeats": [y for y in (yz or {}).get("seats", [])],
            "sig": s, "hits": hits, "nHits": len(hits), "track": track,
            "sigTotal": round(sig_total, 2),
        })

    # 排序：命中路数优先 → 信号总分
    cands.sort(key=lambda x: (-x["nHits"], -x["sigTotal"]))
    cands = cands[:TOP]

    out = {
        "date": D,
        "window": W,
        "execDates": ex_dates,
        "blockDates": bl_dates,
        "q2Date": "2026-06-30",
        "nCandidates": len(cands),
        "candidates": cands,
    }
    op = os.path.join(OUT_DIR, f"candidates_{D}.json")
    with open(op, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)

    # 代码清单（每批 25）
    cs = [c["code"] for c in cands]
    batches = [",".join(cs[i:i + 25]) for i in range(0, len(cs), 25)]
    cp = os.path.join(OUT_DIR, f"_codes_{D}.txt")
    with open(cp, "w", encoding="utf-8") as f:
        f.write("\n".join(batches))

    print(f"[gen_picks] 日期 {D} 窗口 {W} 日")
    print(f"  高管文件 {len(ex_dates)} 个 / 大宗文件 {len(bl_dates)} 个 / 中报个股 {len(q2map)}")
    print(f"  候选池 {len(cands)} 只 → {op}")
    print(f"  行情批次 {len(batches)} 批 → {cp}")
    for b in batches:
        print("    ", b)


if __name__ == "__main__":
    main()
