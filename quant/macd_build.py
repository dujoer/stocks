# -*- coding: utf-8 -*-
"""MACD 水上金叉 + 20 日主力净流入 · 扫描落盘器。

数据来源（agent 经 westock 实拉）：
  1) tool_filter preset=main_inflow, min_inflow=0.3, market=hs, limit=200  → 主力流入初筛池
  2) data_technical(批量 25/次)                                              → MACD / DIF / DEA
  3) data_fund_flow(批量)                                                   → MainNetFlow20D（20 日主力净流入，元）

筛选口径（与用户约定一致）：
  A. 主力流入池：MainNetFlow（tool_filter 口径）> 0.3 亿  → 初筛 1488 只，取前 200
  B. 水上金叉：DIF > 0 且 DEA > 0 且 MACD(柱) > 0
  C. 20 日主力净流入为正：MainNetFlow20D > 0（严格口径，剔除"当日热、20 日撤"的伪强势）

用法：
  python quant/macd_build.py                 # 自动取最新原始 JSON 计算；缺失则用内嵌的本批实测结果
  python quant/macd_build.py 20260911        # 指定数据日期（compact）
  python quant/macd_build.py --raw           # 强制从 quant/macd_raw_*.json 计算（日常重扫模式）

输出：
  quant/macd_scan_{DATE}.json   → gen_macd.py 消费渲染
"""
from __future__ import annotations
import os, re, json, glob, argparse, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QUANT = os.path.join(ROOT, "quant")
# ★ 这里曾硬编码 DATE = "20260911" + 内嵌一份 09-11 的 FINAL 快照，
#   缺原始数据时静默回退却顶着新日期写文件 → macd_scan_20260924/28/29/30 四期逐字节冻结。
#   现在日期一律由命令行/原始文件名推导，回退必须显式 --allow-embedded（见 main）。
EMBEDDED_SNAPSHOT_DATE = "20260911"   # 仅标识内嵌快照属于哪一天

# ──────────────────────────────────────────────────────────────
# 本批实测最终入选（35 只）：经 A/B/C 三步筛选后的结果。
# 字段：(code, name, close, change%, dif, dea, macd, flow20d(元), circRate%, dailyFlow(元), mainInflowRank)
# flow20d = data_fund_flow.MainNetFlow20D；dailyFlow = 当日主力净流入；circRate = 主力净流入流通占比%
# ──────────────────────────────────────────────────────────────
FINAL = [
    ("sh603186", "华正新材", 227.74, 1.37, 14.4825, 9.8629, 9.2392, 2111092931, 0.45, 159866466, 53),
    ("sh601869", "长飞光纤", 473.99, 8.78, 20.4644, 13.5124, 13.9039, 1692084536, 0.25, 490095318, 12),
    ("sz002297", "博云新材", 23.53, 7.44, 0.9524, 0.4041, 1.0966, 782809702, 4.56, 614338446, 9),
    ("sh603936", "博敏电子", 20.88, 10.01, 0.6233, 0.3381, 0.5705, 755144792, 3.23, 424871482, 17),
    ("sh601872", "招商轮船", 20.00, 4.18, 0.7202, 0.6098, 0.2207, 748671991, 0.19, 308283463, 24),
    ("sz000823", "超声电子", 20.57, 10.00, 0.7754, 0.2218, 1.1072, 676677975, 2.15, 262727974, 29),
    ("sh603228", "景旺电子", 111.75, 1.58, 6.239, 4.772, 2.9341, 649650450, 0.29, 313914371, 23),
    ("sz002602", "世纪华通", 15.56, 0.00, 0.508, 0.3586, 0.2987, 517950976, 0.08, 80890828, 99),
    ("sh600104", "上汽集团", 11.72, 5.11, 0.2161, 0.0829, 0.2663, 516808117, 0.35, 475851594, 13),
    ("sh603989", "艾华集团", 33.03, 4.01, 0.7523, 0.2307, 1.0432, 476360837, 0.71, 93796958, 85),
    ("sz002916", "深南电路", 396.68, 1.11, 5.7556, 0.5425, 10.4262, 465832794, 0.10, 262379005, 30),
    ("sh603533", "掌阅科技", 25.04, 4.57, 0.8649, 0.6714, 0.3869, 394428265, 1.22, 133846978, 64),
    ("sh688143", "长盈通", 195.00, 15.49, 13.4409, 12.4347, 2.0124, 376515449, 0.69, 165444402, 51),
    ("sz002815", "崇达技术", 20.08, 10.03, 1.2596, 0.6592, 1.2009, 335161557, 1.45, 225652357, 37),
    ("sz002902", "铭普光磁", 30.86, 10.02, 0.9432, 0.5146, 0.8573, 301380297, 5.81, 334133932, 21),
    ("sh603920", "世运电路", 41.45, 1.54, 0.5366, 0.084, 0.905, 318205872, 0.29, 85400827, 94),
    ("sz002201", "九鼎新材", 11.09, 10.02, 0.4384, 0.2001, 0.4765, 288253277, 1.68, 112208809, 70),
    ("sz002181", "粤传媒", 9.73, 5.42, 0.207, 0.1099, 0.1941, 237094766, 0.97, 107626293, 73),
    ("sz301176", "逸豪新材", 60.60, 7.28, 1.6367, 0.167, 2.9394, 165129753, 1.11, 110216014, 72),
    ("sz300852", "四会富仕", 65.59, 3.10, 3.9199, 1.7833, 4.2732, 174425811, 0.88, 89619203, 90),
    ("sh600255", "鑫科材料", 3.88, 4.43, 0.1203, 0.0657, 0.1093, 184174341, 1.48, 103754556, 75),
    ("sh688519", "南亚新材", 327.07, 5.65, 5.9518, 3.3182, 5.2672, 196501724, 0.31, 235763280, 36),
    ("sz000070", "特发信息", 17.16, 6.06, 0.4009, 0.2564, 0.2889, 127068528, 1.99, 291955312, 26),
    ("sz301183", "东田微", 246.99, 4.93, 10.1958, 9.4683, 1.455, 132977199, 1.67, 241896048, 35),
    ("sh600967", "内蒙一机", 14.98, 9.99, 0.7986, 0.5054, 0.5864, 123958877, 3.17, 808847105, 6),
    ("sz002517", "恺英网络", 17.71, 0.06, 0.1589, 0.0879, 0.142, 143524438, 0.30, 98676378, 77),
    ("sz002194", "武汉凡谷", 11.46, 5.52, 0.2982, 0.1978, 0.2008, 109182909, 7.92, 466924049, 15),
    ("sz003035", "南网能源", 5.98, 2.02, 0.0641, 0.0316, 0.0648, 103843415, 0.41, 93484076, 86),
    ("sh600706", "曲江文旅", 9.41, 2.62, 0.4164, 0.3352, 0.1623, 34578563, 6.03, 144089999, 58),
    ("sh603136", "天目湖", 10.58, 9.98, 0.2662, 0.1773, 0.1779, 11288256, 3.01, 86158806, 93),
    ("sz000930", "中粮科技", 5.88, -1.48, 0.3328, 0.2062, 0.253, 14975224, 0.78, 85111728, 95),
    ("sh600887", "伊利股份", 26.66, 0.45, 0.1652, 0.1354, 0.0596, 8743901, 0.09, 146730776, 55),
    ("sz000980", "众泰汽车", 2.12, 9.84, 0.0587, 0.0105, 0.0963, 19675881, 1.74, 186304866, 45),
    ("sh600371", "万向德农", 14.78, 4.02, 2.0058, 1.7591, 0.4934, 59652507, 5.82, 251646033, 32),
    ("sz002519", "银河电子", 6.31, 9.93, 0.1206, 0.0637, 0.1138, 2408928, 2.86, 202785737, 40),
]


def build_from_raw(date_str):
    """日常重扫模式：从 quant/macd_raw_{pool,tech,flow}_{DATE}.json 计算。
    返回 (stocks, meta_count)。原始 JSON 结构即 westock 直接返回的 data 字段。
    """
    pool_p = os.path.join(QUANT, f"macd_raw_pool_{date_str}.json")
    tech_p = os.path.join(QUANT, f"macd_raw_tech_{date_str}.json")
    flow_p = os.path.join(QUANT, f"macd_raw_flow_{date_str}.json")
    if not (os.path.exists(pool_p) and os.path.exists(tech_p) and os.path.exists(flow_p)):
        return None, None
    pool = json.load(open(pool_p, encoding="utf-8"))
    tech = json.load(open(tech_p, encoding="utf-8"))
    flow = json.load(open(flow_p, encoding="utf-8"))

    tech_d = tech["data"]
    flow_d = flow["data"]

    # pool 提供 change/close/dailyFlow/name
    cand = []
    above_water = 0
    for s in pool["data"]["stocks"]:
        code = s["code"]
        t = tech_d.get(code)
        if not t:
            continue
        macd = t["macd"]
        dif, dea, bar = macd["DIF"], macd["DEA"], macd["MACD"]
        if not (dif > 0 and dea > 0 and bar > 0):
            continue
        above_water += 1
        f = flow_d.get(code, {}).get("data", [{}])[0]
        flow20d = f.get("MainNetFlow20D")
        if not flow20d or float(flow20d) <= 0:
            continue
        cand.append({
            "code": code, "name": s["name"], "close": float(s["ClosePrice"]),
            "change": float(s["ChangePCT"]), "dif": round(dif, 4), "dea": round(dea, 4),
            "macd": round(bar, 4), "flow20d": int(float(flow20d)),
            "flow20d_yi": round(float(flow20d) / 1e8, 2),
            "circRate": float(f.get("MainInflowCircRate", 0)),
            "dailyFlow": int(float(f.get("MainNetFlow", 0))),
            "rank": int(f.get("MainInflowRank", 0)),
        })
    cand.sort(key=lambda x: x["flow20d"], reverse=True)
    return cand, {"pool_total": pool["data"]["totalStocks"], "tech_scanned": len(tech_d),
                  "above_water": above_water, "pool_src": pool.get("src") or "westock_filter"}


def load_extra(date_str):
    """增强记录列（可选）：quant/macd_extra_{DATE}.json，由 _build_macd_extra_*.py 生成。
    仅用于诊断显示，**不参与筛选**（避免单期样本过拟合）。缺失时返回 {}，页面优雅降级。"""
    p = os.path.join(QUANT, f"macd_extra_{date_str}.json")
    if not os.path.exists(p):
        return {}
    try:
        return json.load(open(p, encoding="utf-8")).get("extra", {}) or {}
    except Exception as ex:
        print(f"[warn] 增强列读取失败（忽略）：{ex}")
        return {}


def attach_extra(stocks, date_str):
    """把增强列并入各股；同时用 data_quote 收盘涨跌幅校正 change（原 tool_filter 为盘中口径）。"""
    extra = load_extra(date_str)
    hit = 0
    for s in stocks:
        e = extra.get(s["code"])
        if not e:
            continue
        s["extra"] = e
        if e.get("chg1") is not None:
            s["change"] = e["chg1"]
        hit += 1
    return hit, len(extra)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("date", nargs="?", default=None,
                    help="数据日期 YYYYMMDD；缺省时取 quant/ 下最新的 macd_raw_pool_*.json")
    ap.add_argument("--raw", action="store_true", help="从原始 JSON 计算（日常重扫模式）")
    ap.add_argument("--allow-embedded", action="store_true",
                    help="仅当原始数据缺失时才允许回退到内嵌 2026-09-11 实测快照（默认禁止）")
    a = ap.parse_args()

    if a.date is None:
        cands = sorted(glob.glob(os.path.join(QUANT, "macd_raw_pool_*.json")))
        if not cands:
            raise SystemExit(
                "quant/ 下没有 macd_raw_pool_*.json —— 当日重扫数据未落盘。\n"
                "★ 禁止回退到内嵌的 2026-09-11 快照冒充当日：那是旧数据冒充当日，"
                "曾导致 macd_scan_20260924/28/29/30 四期逐字节相同。\n"
                "请先跑当日重扫（westock tool_filter → data_technical → data_fund_flow 落 "
                "macd_raw_{pool,tech,flow}_%s.json），再执行 macd_build.py %s --raw"
                % ("{DATE}", "{DATE}"))
        a.date = os.path.basename(cands[-1])[len("macd_raw_pool_"):-len(".json")]
        print("[macd] 未指定日期，取最新原始数据 macd_raw_pool_%s.json" % a.date)

    stocks = None
    counts = None
    if a.raw or True:  # 始终走原始数据；内嵌快照需显式 --allow-embedded
        stocks, counts = build_from_raw(a.date)
        if stocks is None and a.allow_embedded:
            print("[macd] ⚠ 原始数据缺失，按 --allow-embedded 回退到内嵌 2026-09-11 快照"
                  "（该结果**不是 %s 的数据**，页面必须如实标注）" % a.date)
    if stocks is None:
        if not a.allow_embedded:
            missing = [n for n in ("pool", "tech", "flow")
                       if not os.path.exists(os.path.join(QUANT, f"macd_raw_{n}_{a.date}.json"))]
            raise SystemExit(
                "✗ 拒绝出票：%s 的原始重扫数据不完整（缺 %s）\n"
                "  macd_raw_pool_%s.json / macd_raw_tech_%s.json / macd_raw_flow_%s.json\n"
                "★ 本脚本不会回退到内嵌的 2026-09-11 快照 —— 那会让 macd_scan_{date}.json "
                "顶着新日期写旧数据（2026-09-24/28/29/30 四期就是这样冻结的）。\n"
                "  正确做法：先把当日 westock 三段原始数据落盘，再 --raw 重跑；\n"
                "  若确认要用旧快照，必须显式加 --allow-embedded。"
                % (a.date, "、".join(missing) or "（无）", a.date, a.date, a.date))
        # 内嵌本批实测（仅在显式允许时）
        stocks = []
        for (code, name, close, change, dif, dea, bar, flow20d, circ, daily, rank) in FINAL:
            stocks.append({
                "code": code, "name": name, "close": close, "change": change,
                "dif": dif, "dea": dea, "macd": bar, "flow20d": flow20d,
                "flow20d_yi": round(flow20d / 1e8, 2), "circRate": circ,
                "dailyFlow": daily, "rank": rank,
            })
        counts = {"pool_total": 1488, "tech_scanned": 100, "above_water": 51}
        a.date = "20260911"          # 内嵌快照就是 09-11 的，日期必须改回来，不许顶着新日期

    hit, extra_total = attach_extra(stocks, a.date)

    off = (counts.get("pool_src") == "offline_txk_full")
    out = {
        # ★ data_date 必须由实际使用的数据日推导，绝不写死 —— 写死就是「旧数据冒充当日」
        "data_date": "%s-%s-%s" % (a.date[:4], a.date[4:6], a.date[6:8]),
        "generated": datetime.date.today().isoformat(),
        "src": "offline_txk_full" if off else "westock",
        "method": "MACD 水上金叉 (DIF>0, DEA>0, MACD柱>0) + 20日主力净流入 > 0",
        "criteria": [
            ("初筛域：全市场正股 %d 只（★离线降级：本地腾讯日K，非 westock 主力净流入 top200；"
             "与历史 top200 口径不可直接对比）" % counts["pool_total"]) if off
            else "tool_filter preset=main_inflow, min_inflow=0.3亿, market=hs, limit=200（全市场初筛 1488 只）",
            "MACD 水上金叉（DIF>0 且 DEA>0 且 MACD红柱>0）" + ("（本地日K 自算，口径同 data_technical）" if off else ""),
            "20 日主力净流入 > 0（剔除当日热、20日撤的伪强势）" + ("（新浪 MoneyFlow 离线源）" if off else ""),
        ],
        "pipeline_note": ("每日离线重扫：_gen_macd_pool_offline（本地日K初筛域）→ _gen_tech_offline（本地日K算 MACD）"
                          "→ _gen_macd_flow_sina（新浪 20 日主力净流入）→ macd_build --raw。"
                          if off else
                          "每日重扫：westock tool_filter→data_technical→data_fund_flow，落 macd_raw_*.json，再 macd_build.py --raw。"),
        "extra_note": f"增强诊断列 {hit}/{len(stocks)} 只（源 macd_extra_{a.date}.json）：pos52/量比/换手/5D主力/归一化强度/60日涨幅/获利盘/集中度。**仅记录与显示，不参与筛选**；change 已按 data_quote 收盘口径校正。",
        "extra_covered": hit,
        "extra_available": extra_total,
        "pool_total": counts["pool_total"],
        "tech_scanned": counts["tech_scanned"],
        "above_water": counts["above_water"],
        "final_count": len(stocks),
        "stocks": stocks,
    }
    # ★ 落盘前冻结自检：与上一期的整批 (code,dif,dea,close) 指纹逐字节比对。
    #   逐字节相同 = 这一期根本没重扫（2026-09-24/28/29/30 就是这样冻结的）。
    #   命中就**拒绝写盘**并报错，不让旧快照顶着新日期落盘。
    sig_now = "|".join("%s:%.4f:%.4f:%.4f" % (s["code"], s["dif"], s["dea"], s["close"])
                       for s in sorted(stocks, key=lambda x: x["code"]))
    prev_files = sorted(f for f in os.listdir(QUANT)
                        if re.match(r"^macd_scan_\d{8}\.json$", f) and f < f"macd_scan_{a.date}.json")
    if prev_files:
        prev = json.load(open(os.path.join(QUANT, prev_files[-1]), encoding="utf-8"))
        sig_prev = "|".join("%s:%.4f:%.4f:%.4f" % (s["code"], s["dif"], s["dea"], s["close"])
                            for s in sorted(prev.get("stocks") or [], key=lambda x: x["code"]))
        if sig_prev and sig_prev == sig_now:
            raise SystemExit(
                "✗ 拒绝写盘：本次结果与上一期 %s **逐字节完全相同**。\n"
                "  这说明底池没有真正重扫，继续写下去就是拿旧数据冒充当日。\n"
                "  请检查 %s 的 macd_raw_{{pool,tech,flow}}_%s.json 是否真的换了新数据。"
                % (prev_files[-1][len("macd_scan_"):-len(".json")], a.date, a.date))
        print("[macd] 冻结自检通过（与 %s 指纹不同）" % prev_files[-1])

    out["sig"] = sig_now

    path = os.path.join(QUANT, f"macd_scan_{a.date}.json")
    json.dump(out, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"写入 {path}｜入选 {len(stocks)} 只（水上金叉 {counts['above_water']} / 初筛 {counts['pool_total']}）｜增强列 {hit} 只")


if __name__ == "__main__":
    main()
