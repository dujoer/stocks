# -*- coding: utf-8 -*-
"""今日高胜率候选池（通用版 · 按 --date 参数化）

基底：当日 MACD 水上金叉 + 20日主力净流入>0 的候选（每日重扫）
增强：data_quote(行情) + data_technical(MA/RSI) + data_chip(筹码) + 板块行为 + 龙虎榜 + 高管/大宗
输出：quant/picks/highwin_{DATE}.json
用法： python quant/build_highwin.py --date 2026-09-14
      随后 python quant/gen_highwin.py --date 2026-09-14  渲染 HTML

输入依赖（均按日期自动定位）：
  quant/macd_scan_{YYYYMMDD}.json      MACD 三层漏斗结果（必需）
  quant/_raw_extract/{quote,tech,chip}_{YYYYMMDD}.json  增强数据（缺失则该维度记 0）
  quant/sector_daily/{DATE}.json       板块行为
  quant/lhb/{DATE}.json + lhb_enriched_{DATE}.json
  quant/exec_chg/{DATE}.json + block_chg/{DATE}.json
"""
import os, json, argparse

_WBROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
R = _WBROOT   # 原写死：G:/ai/股票
Q = os.path.join(R, "quant")
EXTRACT = os.path.join(Q, "_raw_extract")

# ---------- 日期参数 ----------
_AP = argparse.ArgumentParser(description="高胜率候选池打分")
_AP.add_argument("--date", dest="date", help="数据日期 YYYY-MM-DD，缺省取今天")
_A = _AP.parse_args()
import datetime as _dt
D = _A.date or _dt.date.today().strftime("%Y-%m-%d")
DS = D.replace("-", "")
print("[args] date=%s" % D)

def load(p, d=None):
    if not os.path.exists(p):
        return d
    return json.load(open(p, encoding="utf-8"))

def clamp(x, lo, hi):
    return max(lo, min(hi, x))

# ---------- 1) 基底：MACD 水上金叉 55 只 ----------
scan = load(os.path.join(Q, "macd_scan_%s.json" % DS), {})
stocks = scan.get("stocks", [])
print("[base] MACD 水上金叉:", len(stocks), "pool_total:", scan.get("pool_total"))

# ---------- 2) 增强数据 ----------
quote = (load(os.path.join(EXTRACT, "quote_%s.json" % DS), {}) or {}).get("data", {})
tech = (load(os.path.join(EXTRACT, "tech_%s.json" % DS), {}) or {}).get("data", {})
chip = (load(os.path.join(EXTRACT, "chip_%s.json" % DS), {}) or {}).get("data", {})
print("[enh] quote=%d tech=%d chip=%d" % (len(quote), len(tech), len(chip)))

# 板块行为
sd = load(os.path.join(Q, "sector_daily", "%s.json" % D), {})
beh_ind = {}
for r in sd.get("records", []):
    if r.get("kind") == "行业":
        beh_ind[r["name"]] = r
print("[sector] 行业记录:", len(beh_ind))
name2sw2 = load(os.path.join(Q, "_name2sw2.json"), {})

# 龙虎榜：机构席位
rawlhb = load(os.path.join(Q, "lhb", "%s.json" % D), {})
jg = ((rawlhb.get("data") or {}).get("jg") or [])
inst = {}
for r in jg:
    c = r.get("code")
    if c:
        inst[c] = inst.get(c, 0.0) + float(r.get("netBuyAmt") or 0)
lhb_en = load(os.path.join(Q, "lhb_enriched_%s.json" % D), {})
lhb_stocks = lhb_en.get("stocks", {})

# 高管增减持
ex = load(os.path.join(Q, "exec_chg", "%s.json" % D), {})
exec_map = {}
for r in ex.get("records", []):
    c = r.get("code")
    if not c:
        continue
    e = exec_map.setdefault(c, {"buy": 0.0, "sell": 0.0, "nBuy": 0, "nSell": 0})
    sh = float(r.get("shares") or 0)
    if r.get("dir") == "增持":
        e["buy"] += sh; e["nBuy"] += 1
    else:
        e["sell"] += sh; e["nSell"] += 1

# 大宗交易
bl = load(os.path.join(Q, "block_chg", "%s.json" % D), {})
bl_map = {}
for r in (bl.get("byStock") or []):
    c = r.get("code")
    if c:
        bl_map[c] = r
bl_rows = bl.get("rows") or []
bl_inst_buy = {}
for r in bl_rows:
    c = r.get("code")
    if not c:
        continue
    if "机构" in str(r.get("buyer") or ""):
        bl_inst_buy[c] = bl_inst_buy.get(c, 0.0) + float(r.get("value") or 0)

# ---------- 3) 打分 ----------
def score_one(s):
    code = s["code"]; name = s["name"]
    price = float(s.get("close") or 0)
    dif = float(s.get("dif") or 0); dea = float(s.get("dea") or 0); macd = float(s.get("macd") or 0)
    flow20d_yi = float(s.get("flow20d_yi") or 0)
    dailyFlow = float(s.get("dailyFlow") or 0)
    circRate = float(s.get("circRate") or 0)

    q = quote.get(code, {})
    t = tech.get(code, {})
    ch = chip.get(code, {})
    ma = (t.get("ma") or {})
    rsi = (t.get("rsi") or {})
    price_q = float(q.get("price") or price or 0)
    hi52 = float(q.get("high_52week") or 0); lo52 = float(q.get("low_52week") or 0)
    turn = float(q.get("turnover_rate") or 0)
    volr = float(q.get("volume_ratio") or 0)
    chg20 = float(q.get("chg_20d") or 0); chg60 = float(q.get("chg_60d") or 0)
    rsi12 = float(rsi.get("RSI_12") or 0)
    profit = float(ch.get("chipProfitRate") or 0)
    conc90 = float(ch.get("chipConcentration90") or 0)

    # 52周分位
    pos52 = None
    if hi52 > lo52 > 0:
        pos52 = (price_q - lo52) / (hi52 - lo52) * 100

    # --- 趋势/技术 25 ---
    macd_ratio = (macd / price * 100) if price else 0
    s_macd = clamp(macd_ratio / 0.9 * 10, 0, 10)
    ma5 = float(ma.get("MA_5") or 0); ma10 = float(ma.get("MA_10") or 0)
    ma20 = float(ma.get("MA_20") or 0); ma60 = float(ma.get("MA_60") or 0); ma120 = float(ma.get("MA_120") or 0)
    align = 0
    if price_q > ma5 and ma5: align += 2
    if ma5 >= ma10 and ma10: align += 1
    if ma10 >= ma20 and ma20: align += 1
    if ma20 >= ma60 and ma60: align += 2
    if ma60 >= ma120 and ma120: align += 2
    s_align = clamp(align, 0, 8)
    if 55 <= rsi12 <= 75: s_rsi = 7
    elif 48 <= rsi12 < 55 or 75 < rsi12 <= 82: s_rsi = 4
    elif rsi12 > 0: s_rsi = 2
    else: s_rsi = 3
    s_tech = s_macd + s_align + s_rsi

    # --- 位置 15 ---
    if pos52 is None: s_pos = 7
    elif 25 <= pos52 <= 65: s_pos = 15
    elif 15 <= pos52 < 25 or 65 < pos52 <= 78: s_pos = 10
    elif 78 < pos52 <= 88: s_pos = 5
    elif pos52 > 88: s_pos = 1
    else: s_pos = 6

    # --- 资金 20 ---
    s_flow20 = clamp(flow20d_yi / 6.0 * 12, 0, 12) if flow20d_yi > 0 else 0
    s_daily = 4 if dailyFlow > 0 else 0
    s_circ = clamp(circRate / 4.0 * 4, 0, 4)
    s_fund = s_flow20 + s_daily + s_circ

    # --- 筹码 15 ---
    if 45 <= profit <= 80: s_prof = 8
    elif 35 <= profit < 45 or 80 < profit <= 88: s_prof = 5
    elif profit > 0: s_prof = 2
    else: s_prof = 4
    if 12 <= conc90 <= 32: s_conc = 7
    elif 8 <= conc90 < 12 or 32 < conc90 <= 40: s_conc = 4
    else: s_conc = 2
    s_chip = s_prof + s_conc

    # --- 板块 12 ---
    sw2 = name2sw2.get(name, "")
    rec = beh_ind.get(sw2)
    behavior = rec.get("behavior") if rec else "未知"
    s_sec = {"抢筹": 12, "建仓": 9, "洗盘": 5, "出货": 0}.get(behavior, 5)

    # --- 龙虎榜 8 ---
    s_lhb = 0
    inb = inst.get(code, 0.0)
    if inb > 0: s_lhb += clamp(inb / 1e8 * 5, 0, 5)
    le = lhb_stocks.get(code)
    if le:
        hm = {"高": 3, "中": 2, "低": 0}.get(le.get("hotmoneyLevel") or "低", 0)
        if float(le.get("netBuy") or 0) > 0: s_lhb += hm
    s_lhb = clamp(s_lhb, 0, 8)

    # --- 高管/大宗 5 ---
    s_eb = 0.0
    em = exec_map.get(code)
    if em and em["nBuy"] > em["nSell"]: s_eb += 2.5
    if bl_inst_buy.get(code, 0) > 0: s_eb += 2.5
    s_eb = clamp(s_eb, 0, 5)

    total = s_tech + s_pos + s_fund + s_chip + s_sec + s_lhb + s_eb

    # veto / 风险
    flags = []
    if behavior == "出货": flags.append("板块出货")
    if rsi12 >= 90: flags.append("超买RSI≥90")
    if pos52 is not None and pos52 >= 92: flags.append("高位≥92%")
    if turn >= 30: flags.append("换手过热")
    if profit >= 92: flags.append("获利盘≥92%")
    veto = len([f for f in flags if f in ("板块出货", "超买RSI≥90", "高位≥92%")]) > 0

    if veto: tier = "回避"
    elif total >= 68: tier = "核心"
    elif total >= 55: tier = "观察"
    else: tier = "备选"

    return {
        "code": code, "name": name, "price": round(price_q, 2),
        "changePct": float(q.get("change_percent") or s.get("change") or 0),
        "sw2": sw2, "behavior": behavior, "leader": (rec or {}).get("leader", ""),
        "total": round(total, 1),
        "c_tech": round(s_tech, 1), "c_pos": s_pos, "c_fund": round(s_fund, 1),
        "c_chip": round(s_chip, 1), "c_sec": s_sec, "c_lhb": round(s_lhb, 1), "c_eb": s_eb,
        "macd_ratio": round(macd_ratio, 3), "flow20d_yi": round(flow20d_yi, 2),
        "dailyFlow_yi": round(dailyFlow / 1e8, 3), "circRate": circRate,
        "pos52": (round(pos52, 1) if pos52 is not None else None),
        "turn": turn, "volr": volr, "rsi12": rsi12, "chg20": chg20, "chg60": chg60,
        "profit": profit, "conc90": conc90, "avgCost": float(ch.get("chipAvgCost") or 0),
        "inst_net": round(inb / 1e8, 3), "hotmoney": (le or {}).get("hotmoneyLevel", ""),
        "exec_buy": em["buy"] if em else 0, "exec_sell": em["sell"] if em else 0,
        "block_inst": round(bl_inst_buy.get(code, 0) / 1e8, 3),
        "flags": flags, "veto": veto, "tier": tier,
    }

rows = [score_one(s) for s in stocks]
order = {"核心": 0, "观察": 1, "备选": 2, "回避": 3}
rows.sort(key=lambda x: (order[x["tier"]], -x["total"]))

# ---------- 3b) 跨池入选历史（MACD观察池 + 信号池） ----------
import glob as _glob, re as _re
hist = {}
def _add(code, date, pool):
    if code:
        hist.setdefault(code, []).append((date, pool))

for p in _glob.glob(os.path.join(Q, "macd_scan_*.json")):
    m = _re.search(r"macd_scan_(\d{8})\.json", os.path.basename(p))
    if not m:
        continue
    ds = m.group(1)
    date = "%s-%s-%s" % (ds[:4], ds[4:6], ds[6:8])
    try:
        jj = json.load(open(p, encoding="utf-8"))
    except Exception:
        continue
    for s in jj.get("stocks", []):
        _add(s.get("code"), date, "MACD观察池")

hp = load(os.path.join(Q, "picks", "history.json"), []) or []
for entry in hp:
    date = entry.get("date")
    if not date:
        continue
    for track, label in [("inst", "信号池·机构轨"), ("youzi", "信号池·游资轨")]:
        for x in (entry.get(track) or []):
            _add(x.get("code"), date, label)

TODAY = D
for r in rows:
    prior = [(d, pool) for d, pool in hist.get(r["code"], []) if d < TODAY]
    prior.sort()
    r["hist"] = [{"date": d, "pool": pool} for d, pool in prior]
    r["histDates"] = sorted(set(d for d, _ in prior))

n_hist = sum(1 for r in rows if r["histDates"])
print("[hist] 本轮池内出现过往期入选的标的:", n_hist, "/", len(rows))

from collections import Counter
tc = Counter(r["tier"] for r in rows)
print("[tier]", dict(tc))

out = {
    "date": D,
    "base": "MACD水上金叉+20日主力净流入>0（%d只）" % len(stocks),
    "pool_total": scan.get("pool_total"),
    "counts": dict(tc),
    "model": "8维：趋势25/位置15/资金20/筹码15/板块12/龙虎榜8/高管大宗5",
    "rows": rows,
}

# ★ 出票许可：只读证据页 `_hw_gate_page.emit_license()`，读不到即 fail-safe 不出票。
#   底池是旧数据（MACD 快照冻结）时，edge 再漂亮也不能出票 —— 那是拿过期信息下单。
emit_ok, emit_why = True, ""
try:
    import _hw_gate_page as _GP
    _lic = _GP.emit_license()
    _core = (_lic.get("detail", {}) or {}).get("CORE", {}) or {}
    emit_ok = bool(_core.get("ok"))
    emit_why = _core.get("why", "")
except Exception as ex:
    emit_ok, emit_why = False, "证据不可用：%s" % ex
out["emit_ok"] = bool(emit_ok)
out["emit_why"] = emit_why
if not emit_ok:
    print("[emit] 出票许可未通过 → 本期不出票（宁可不选）")
    print("[emit] 原因：%s" % emit_why)
else:
    print("[emit] 出票许可通过")
os.makedirs(os.path.join(Q, "picks"), exist_ok=True)
with open(os.path.join(Q, "picks", "highwin_%s.json" % D), "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False)
print("[out] quant/picks/highwin_%s.json" % D)
for r in rows[:12]:
    print("  %-6s %-6s %5.1f  %s  板块=%s(%s) 20D=%.2f亿 pos=%s RSI=%.0f 获利=%.0f" % (
        r["tier"], r["name"], r["total"], r["code"], r["behavior"], r["sw2"],
        r["flow20d_yi"], r["pos52"], r["rsi12"], r["profit"]))
