# -*- coding: utf-8 -*-
"""做T池 · 候选池生成（Stage 1）· 多源版。

三源并集（任一中即入池，逐只标注来源）：
  A 机构底仓（inst）  —— 公募基金持有十大流通股比例合计 ≥ min-fund（默认 3%）
                         或 社保/养老/年金/险资/汇金/证金/QFII ≥ 2 家
  B 龙虎榜活跃（lhb）  —— 近 LOOKBACK 个交易日上过龙虎榜，且累计净买 > 0 或 ≥2 次上榜
                         （游资/机构席位活跃 → 波动与流动性天然充足，适合做T）
  C 强势股（strong）   —— 全市场离线扫描（scan_strong.py）：20 日超额收益 ≥5pp 且站上 MA20，
                         再过做T结构门槛（振幅/箱体/位置），取 RS 前 STRONG_TOP 只

数据源：
  quant/q2_full/_merged_shareholder.json   （2026-Q2 全市场十大流通股东）
  quant/q2_full/_code2industry.json        （代码 → 申万一级）
  quant/lhb_enriched_{YYYY-MM-DD}.json     （龙虎榜增强，近 10 交易日）
  quant/tplus/_strong_scan_{D}.json        （scan_strong.py 产物）

输出：
  quant/tplus/codes_{D}.txt         逗号分隔代码（供批量拉行情）
  quant/tplus/universe_{D}.json     [{code,name,industry,fund_ratio,top_inst,inst_names,sources,lhb,strong}]

用法：
  python gen_tplus.py [--date YYYY-MM-DD] [--min-fund 3.0] [--sources inst,lhb,strong]
                      [--lhb-days 10] [--strong-top 400] [--inst-only] [--all]
"""
import os, sys, json, argparse, datetime, glob, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
Q2 = os.path.join(ROOT, "quant", "q2_full")
MERGED = os.path.join(Q2, "_merged_shareholder.json")
C2I = os.path.join(Q2, "_code2industry.json")
OUT_DIR = os.path.join(ROOT, "quant", "tplus")

FUND_KW = ["证券投资基金", "混合型", "股票型", "灵活配置", "指数型", "交易型开放式"]
TOP_KW = ["社保", "养老", "年金", "保险", "汇金", "证金", "中国证券金融", "QFII", "北向",
          "国新", "国调", "中央汇金"]


def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=datetime.date.today().strftime("%Y-%m-%d"))
    ap.add_argument("--min-fund", type=float, default=3.0, help="公募持股比例门槛（%）")
    ap.add_argument("--sources", default="inst,lhb,strong", help="启用来源，逗号分隔")
    ap.add_argument("--lhb-days", type=int, default=10, help="龙虎榜回看交易日数")
    ap.add_argument("--strong-top", type=int, default=400, help="强势源取 RS20 前 N 只")
    ap.add_argument("--inst-only", action="store_true", help="仅用机构底仓源（旧行为）")
    ap.add_argument("--all", action="store_true", help="机构源忽略门槛，全市场")
    return ap.parse_args()


def _lhb_dates(date, days):
    out = []
    for p in glob.glob(os.path.join(ROOT, "quant", "lhb_enriched_*.json")):
        m = re.search(r"lhb_enriched_(\d{4}-\d{2}-\d{2})\.json$", p)
        if m and m.group(1) <= date:
            out.append(m.group(1))
    return sorted(out)[-days:]


def load_lhb_codes(date, days):
    """-> {code: {n, net, last, last_net, hot, tags, name, sw1}}"""
    agg = {}
    for d in _lhb_dates(date, days):
        try:
            j = json.load(open(os.path.join(ROOT, "quant", f"lhb_enriched_{d}.json"), encoding="utf-8"))
        except Exception:
            continue
        for code, v in (j.get("stocks") or {}).items():
            a = agg.setdefault(code, {"n": 0, "net": 0.0, "last": d, "last_net": 0.0,
                                      "hot": "", "hot_net": 0.0, "tags": [], "name": "", "sw1": ""})
            net = v.get("netBuy") or 0
            a["n"] += 1
            a["net"] += net
            if d >= a["last"]:
                a["last"] = d
                a["last_net"] = net
                a["hot"] = v.get("hotmoneyLevel") or ""
                a["hot_net"] = v.get("hotmoneyNet") or 0
                a["name"] = v.get("name") or a["name"]
                a["sw1"] = v.get("sw1") or a["sw1"]
                a["tags"] = [t for t in (v.get("hotmoneyTags") or [])][:3]
    return agg


def load_strong(date, top, c2i):
    """强势源：优先 scan_strong 产物；缺失则跳过。"""
    p = os.path.join(OUT_DIR, f"_strong_scan_{date}.json")
    if not os.path.exists(p):
        print(f"[gen_tplus] ⚠ 缺 {os.path.basename(p)}，强势源跳过（先跑 scan_strong.py）")
        return {}
    try:
        j = json.load(open(p, encoding="utf-8"))
    except Exception:
        return {}
    out = {}
    for r in (j.get("rows") or []):
        if (r.get("rs20") or -99) < 5.0:
            continue
        # 做T结构门槛（与 build_tplus 硬门槛同口径，仅留余量）
        if not (3.0 <= (r.get("amp20") or 0) <= 14.0):
            continue
        if not (8 <= (r.get("box_h") or 0) <= 75):
            continue
        if not (12 <= (r.get("pos52") or 0) <= 92):
            continue
        if (r.get("chg60") or 0) < -30 or (r.get("chg20") or 0) > 60:
            continue
        out[r["code"]] = r
    keep = sorted(out.values(), key=lambda r: (r.get("rs20") or 0), reverse=True)[:top]
    return {r["code"]: r for r in keep}


def main():
    a = parse_args()
    os.makedirs(OUT_DIR, exist_ok=True)
    merged = json.load(open(MERGED, encoding="utf-8"))
    c2i = json.load(open(C2I, encoding="utf-8"))

    want = {"inst"} if a.inst_only else {s.strip() for s in a.sources.split(",") if s.strip()}

    # ---------- 源 A：机构底仓 ----------
    inst = {}
    if "inst" in want:
        for code, rec in merged.items():
            hs = rec.get("top10FloatShareholders") or []
            fund_ratio = 0.0
            top_inst, inst_names = 0, []
            for h in hs:
                nm = (h.get("name") or "").strip()
                pct = h.get("holdPct") or 0
                if any(k in nm for k in FUND_KW):
                    fund_ratio += pct
                if any(k in nm for k in TOP_KW):
                    top_inst += 1
                    inst_names.append(nm)
            keep = a.all or (fund_ratio >= a.min_fund) or (top_inst >= 2)
            if not keep:
                continue
            inst[code] = {"code": code, "name": rec.get("name") or code,
                          "industry": c2i.get(code) or "—",
                          "fund_ratio": round(fund_ratio, 2), "top_inst": top_inst,
                          "inst_names": inst_names[:4]}
        print(f"[gen_tplus] 源A 机构底仓（公募≥{a.min_fund}% 或 顶级机构≥2家）：{len(inst)} 只")

    # ---------- 源 B：龙虎榜活跃 ----------
    lhb_agg, lhb_keep = {}, {}
    if "lhb" in want:
        lhb_agg = load_lhb_codes(a.date, a.lhb_days)
        for code, v in lhb_agg.items():
            if code[:2] not in ("sh", "sz"):
                continue
            nm = v.get("name") or ""
            if "ST" in nm or "退" in nm:
                continue
            if v["n"] >= 2 or v["net"] > 0:
                lhb_keep[code] = v
        print(f"[gen_tplus] 源B 龙虎榜活跃（近{a.lhb_days}日，净买>0 或 ≥2 次）：{len(lhb_keep)} 只 / 候选池 {len(lhb_agg)} 只")

    # ---------- 源 C：强势股 ----------
    strong = load_strong(a.date, a.strong_top, c2i)
    if "strong" in want:
        print(f"[gen_tplus] 源C 强势股（20日超额≥5pp · 站上MA20 · 做T结构门槛）：{len(strong)} 只")

    # ---------- 合并 ----------
    universe = []
    for code in set(inst) | set(lhb_keep) | set(strong):
        base = inst.get(code) or {}
        lh = lhb_agg.get(code) or {}
        st = strong.get(code) or {}
        src = []
        if code in inst:
            src.append("机构底仓")
        if code in lhb_keep:
            src.append("龙虎榜")
        if code in strong:
            src.append("强势")
        name = base.get("name") or lh.get("name") or st.get("name") or code
        if ("ST" in name or "退" in name) and code not in inst:
            continue
        universe.append({
            "code": code,
            "name": name,
            "industry": base.get("industry") or st.get("industry") or c2i.get(code) or "—",
            "fund_ratio": base.get("fund_ratio"),
            "top_inst": base.get("top_inst"),
            "inst_names": base.get("inst_names") or [],
            "sources": src,
            "lhb": ({"n": lh.get("n"), "net": round(lh.get("net") or 0, 0),
                     "last": lh.get("last"), "last_net": round(lh.get("last_net") or 0, 0),
                     "hot": lh.get("hot") or "", "hot_net": round(lh.get("hot_net") or 0, 0),
                     "tags": lh.get("tags") or []} if lh else None),
            "strong": ({"rs20": st.get("rs20"), "rs60": st.get("rs60"),
                        "chg20": st.get("chg20"), "chg60": st.get("chg60"),
                        "multi": st.get("multi"), "pos52": st.get("pos52"),
                        "to_hi52": st.get("to_hi52"), "new60": st.get("new60")} if st else None),
        })

    def rank(u):
        s = u["sources"]
        return (len(s), "机构底仓" in s, u.get("fund_ratio") or 0, u["code"])
    universe.sort(key=rank, reverse=True)

    codes = [u["code"] for u in universe]
    cpath = os.path.join(OUT_DIR, f"codes_{a.date}.txt")
    upath = os.path.join(OUT_DIR, f"universe_{a.date}.json")
    with open(cpath, "w", encoding="utf-8") as f:
        f.write(",".join(codes))
    with open(upath, "w", encoding="utf-8") as f:
        json.dump(universe, f, ensure_ascii=False)

    n3 = sum(1 for u in universe if len(u["sources"]) >= 2)
    print(f"[gen_tplus] {a.date}: 三源并集 {len(codes)} 只（多源共振 {n3} 只）"
          f"｜来源分布 " + " / ".join(f"{k} {sum(1 for u in universe if k in u['sources'])}"
                                      for k in ("机构底仓", "龙虎榜", "强势")))
    print(f"  → {cpath}")
    print(f"  → {upath}")


if __name__ == "__main__":
    main()
