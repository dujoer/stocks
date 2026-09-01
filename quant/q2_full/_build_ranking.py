# -*- coding: utf-8 -*-
"""
全市场 2026 中报 · 行业最强「个人 / 私募 / 公募」榜单生成
数据：5544 家 A 股 2026-06-30 十大股东/十大流通股东
输出：quant/q2_full/_industry_ranking.json
"""
import json, os, re, collections, unicodedata

BASE = os.path.dirname(os.path.abspath(__file__))
SH = json.load(open(os.path.join(BASE, "_merged_shareholder.json"), encoding="utf-8"))
C2I = json.load(open(os.path.join(BASE, "_code2industry.json"), encoding="utf-8"))

# ============================================================
# 1. 股东分类
# ============================================================
src = open(os.path.join(BASE, "..", "build_q2_dashboard.py"), encoding="utf-8").read()
m = re.search(r"KNOWN_CATTLE = \{(.*?)\}", src, re.S)
KNOWN_CATTLE = set(re.findall(r'"([^"]+)"', m.group(1)))

NATIONAL = ["国新", "社保", "养老金", "基本养老", "中央汇金", "国调", "国务院国资委",
            "国家集成电路", "国有企业结构", "证金", "证券金融", "社会保障基金"]
FOREIGN = ["HONG KONG", "香港中央结算", "HKSCC", "UBS", "MORGAN", "BARCLAYS", "J.P.Morgan",
           "JPMorgan", "Goldman", "高盛", "BLACKROCK", "Nominee", "Nominees", "GREENWOODS",
           "CICC", "阿布达比", "科威特", "新加坡政府", "GIC", "加拿大年金", "安大略",
           "魁北克", "挪威", "SCHRODER", "MACQUARIE", "CITIBANK", "MLFE", "BNP"]
TRUST = ["信托"]
PASSIVE_KW = ["交易型开放式", "ETF", "指数型", "指数基金", "联接"]
PRIVATE_KW = ["私募"]
FUND_KW = ["基金", "证券投资基金"]
# 一级市场/产业资本关键词：持股多来自 Pre-IPO 入股或定增锁定，
# 变动不代表二级市场主动判断，与被动 ETF 同理需剔除
PE_KW = ["股权投资", "创业投资", "创投", "产业投资基金", "产业基金", "并购基金",
         "股权基金", "创新投资基金", "产业升级基金", "股权合伙"]
INST_WORDS = ["有限公司", "股份", "公司", "银行", "保险", "证券", "资管", "资产", "投资",
              "合伙", "企业", "中心", "基金", "信托", "局", "部", "委", "大学", "学院",
              "研究院", "集团", "厂", "店", "行", "社"]
BIG_HOLDER_PCT = 10.0        # ≥10% 视为实控人/大股东记录，不计入牛散
STRIP_SUFFIX = ["型证券投资基金", "证券投资基金", "私募证券投资基金", "证券投资",
                "型发起式", "发起式"]

def is_passive(name):
    if "增强" in name:
        return False
    return any(k in name for k in PASSIVE_KW) or "指数" in name

def is_pe(name):
    """一级市场/产业资本判定。产品段明确写「证券投资基金」的先行豁免。"""
    prod = name.split("-")[-1] if "-" in name else name
    if "证券投资基金" in prod:
        return False
    if any(k in name for k in PE_KW):
        return True
    return prod.endswith("(有限合伙)") or prod.endswith("（有限合伙）")

def is_cn(n):
    return all('\u4e00' <= c <= '\u9fff' for c in n)

def holder_type(name, pct=0.0):
    if name in KNOWN_CATTLE: return "个人"
    for k in NATIONAL:
        if k in name: return "国家队"
    for k in FOREIGN:
        if k in name: return "外资"
    for k in TRUST:
        if k in name: return "信托"
    if is_pe(name): return "产业资本"          # 须先于私募/公募判定，避免产业基金混入
    for k in PRIVATE_KW:
        if k in name: return "私募"
    if is_passive(name): return "被动"
    for k in FUND_KW:
        if k in name: return "公募"
    if any(w in name for w in INST_WORDS): return "机构"
    if 2 <= len(name) <= 4 and is_cn(name):
        return "大股东" if pct >= BIG_HOLDER_PCT else "个人"
    return "其他"

def short_name(name):
    """产品名简化：取 '-' 后段并剥离基金后缀"""
    s = name.split("-")[-1] if "-" in name else name
    for suf in STRIP_SUFFIX:
        if s.endswith(suf) and len(s) > len(suf):
            s = s[: -len(suf)]
            break
    return s.strip() or name

def norm_stock(n):
    """股票名规范化：去排版空格、全角转半角、去 XD/XR/DR 前缀与 -U/-W 后缀"""
    if not n:
        return ""
    n = n.replace(" ", "").replace("\u3000", "")
    n = unicodedata.normalize("NFKC", n)
    for p in ("XD", "XR", "DR"):
        if n.startswith(p):
            n = n[2:]
    for suf in ("-UW", "-U", "-W"):
        if n.endswith(suf):
            n = n[: -len(suf)]
    return n

def collect(entry):
    """合并十大股东与十大流通股东，按名称去重（新进按原始记录判定）"""
    by = {}
    for s_ in ("top10Shareholders", "top10FloatShareholders"):
        for s in entry.get(s_, []) or []:
            n = s["name"]
            d = s.get("holdChange", 0) or 0
            sh = s.get("holdShares", 0) or 0
            pct = s.get("holdPct", 0) or 0
            # 新进：本期变动量 == 当前持股量（即上期为 0）
            is_new = 1 if (d > 0 and sh > 0 and abs(d - sh) <= max(1, sh * 0.001)) else 0
            if n not in by:
                by[n] = {"holdChange": d, "holdPct": pct, "holdShares": sh, "new": is_new,
                         "float": s_ == "top10FloatShareholders"}
            else:
                b = by[n]
                if d != 0 and b["holdChange"] == 0:
                    b["holdChange"] = d
                if sh > b["holdShares"]:
                    b["holdShares"] = sh
                    b["holdPct"] = pct
                b["new"] = b["new"] or is_new
                b["float"] = b["float"] or (s_ == "top10FloatShareholders")
    return by

# ============================================================
# 2. 聚合：(行业, 类型, 股东名) -> 统计
# ============================================================
AGG = collections.defaultdict(lambda: {
    "n": 0, "inc": 0, "dec": 0, "flat": 0, "new": 0,
    "pct_sum": 0.0, "delta": 0, "stocks": []})
TYPE_CNT = collections.Counter()
IND_STAT = collections.defaultdict(lambda: collections.Counter())   # 行业 -> 类型 -> 记录数

for code, e in SH.items():
    ind = C2I.get(code)
    if not ind:
        continue
    sname = e.get("name") or code
    for nm, h in collect(e).items():
        t = holder_type(nm, h["holdPct"] or 0)
        TYPE_CNT[t] += 1
        if t not in ("个人", "私募", "公募"):
            continue
        a = AGG[(ind, t, nm)]
        a["n"] += 1
        a["pct_sum"] += h["holdPct"] or 0
        d = h["holdChange"] or 0
        a["delta"] += d
        a["new"] += h["new"]
        if d > 0:
            a["inc"] += 1
        elif d < 0:
            a["dec"] += 1
        else:
            a["flat"] += 1
        a["stocks"].append({"code": code, "name": norm_stock(sname), "d": d,
                            "pct": round(h["holdPct"] or 0, 3)})
        IND_STAT[ind][t] += 1

# ============================================================
# 3. 评分：广度(0-3) + 加仓力度(0-4) + 介入深度(0-3)
# ============================================================
def score_of(v):
    """强度评分 10 分制 = 参与广度(0-4) + 加仓力度(0-4) + 介入深度(0-2)

    · 广度：进入几家公司前十大股东，6 家封顶。只押 1 只股不算「行业最强」。
    · 力度：(增持家数 − 减持家数) / 持股家数，贯彻「增比减好」首要判据；持平会稀释。
    · 深度：合计持股比例，15% 封顶，防止单一重仓股垒高分。
    注：数据源不含「新进」标记（上期在榜外时变动量记为 0），故只统计增持/减持/持平。"""
    breadth = min(v["n"], 6) / 6.0 * 4.0
    ratio = (v["inc"] - v["dec"]) / v["n"] if v["n"] else 0
    ratio = max(-1.0, min(1.0, ratio))
    power = (ratio + 1) / 2.0 * 4.0
    depth = min(v["pct_sum"], 15.0) / 15.0 * 2.0
    return breadth, power, depth

# 公募管理人识别（长名优先匹配）
_m = re.search(r"MUTUAL_FUND_KEYWORDS_PAT = \[(.*?)\]", src, re.S)
MUTUAL_COS = re.findall(r'"([^"]+)"', _m.group(1)) if _m else []
EXTRA_COS = ["前海开源", "银河", "华宝", "创金合信", "财通", "安信", "中庚", "泓德", "国联",
             "中信保诚", "光大保德信", "中信建投", "中泰", "浙商", "华福", "东吴", "德邦",
             "恒越", "淳厚", "中加", "国寿安保", "人保", "太平", "融通", "宝盈", "诺德",
             "金信", "信达澳亚", "西部利得", "兴银", "圆信永丰", "中邮创业", "红土创新",
             "同泰", "博道", "东方", "富安达", "东兴", "湘财", "英大", "九泰", "浦银安盛",
             "平安基金", "华泰保兴", "朱雀", "睿远", "兴证全球", "恒生前海", "鹏扬", "华商"]
MUTUAL_COS = sorted(set(MUTUAL_COS + EXTRA_COS), key=len, reverse=True)
PRIV_SUFFIX = ["私募基金管理有限公司", "私募基金管理", "基金管理有限公司", "资产管理有限公司",
               "管理有限公司", "有限公司", "公司", "合伙企业", "（有限合伙）", "(有限合伙)",
               "资产管理", "投资管理", "资本管理"]

def extract_mgr(t, name, short):
    if t == "私募":
        mgr = name.split("-")[0] if "-" in name else name
        changed = True
        while changed:                       # 循环剥离所有可识别后缀
            changed = False
            for suf in PRIV_SUFFIX:
                if mgr.endswith(suf) and len(mgr) > len(suf):
                    mgr = mgr[: -len(suf)]
                    changed = True
                    break
        mgr = re.sub(r"[（(][^）)]*[）)]\s*$", "", mgr).strip("-· ")
        return mgr or short[:4]
    if t == "公募":
        for co in MUTUAL_COS:
            if short.startswith(co):
                return co
        return short[:2]
    return ""

def pack(ind, t, nm, v):
    b, p, d = score_of(v)
    v["stocks"].sort(key=lambda x: -x["d"])
    return {
        "ind": ind, "type": t, "name": nm, "short": short_name(nm),
        "mgr": extract_mgr(t, nm, short_name(nm)),
        "n": v["n"], "inc": v["inc"], "dec": v["dec"], "flat": v["flat"],
        "pct_sum": round(v["pct_sum"], 2), "delta": v["delta"],
        "s_breadth": round(b, 2), "s_power": round(p, 2), "s_depth": round(d, 2),
        "score": round(b + p + d, 2),
        "stocks": v["stocks"][:8],
    }

GROUPS = ("个人", "私募", "公募")
by_ind = collections.defaultdict(lambda: {g: [] for g in GROUPS})
for (ind, t, nm), v in AGG.items():
    by_ind[ind][t].append(pack(ind, t, nm, v))
for ind in by_ind:
    for g in GROUPS:
        by_ind[ind][g].sort(key=lambda x: (-x["score"], -x["n"], -x["pct_sum"]))

# 行业层面汇总
ind_summary = []
for ind, d in by_ind.items():
    row = {"ind": ind}
    for g in GROUPS:
        lst = d[g]
        inc = sum(x["inc"] for x in lst); dec = sum(x["dec"] for x in lst)
        row[g] = {"holders": len(lst), "inc": inc, "dec": dec, "net": inc - dec,
                  "pct": round(sum(x["pct_sum"] for x in lst), 2)}
    tot = sum(row[g]["holders"] for g in GROUPS)
    row["smart_inc"] = sum(row[g]["inc"] for g in GROUPS)
    row["smart_dec"] = sum(row[g]["dec"] for g in GROUPS)
    row["smart_net"] = row["smart_inc"] - row["smart_dec"]
    row["total"] = tot
    ind_summary.append(row)
ind_summary.sort(key=lambda r: -r["smart_net"])

# 全市场榜：跨行业合并同一股东（同名同类型只出现一次）
MKT = collections.defaultdict(lambda: {
    "n": 0, "inc": 0, "dec": 0, "flat": 0, "new": 0,
    "pct_sum": 0.0, "delta": 0, "stocks": [], "inds": collections.Counter()})
for (ind, t, nm), v in AGG.items():
    a = MKT[(t, nm)]
    for k in ("n", "inc", "dec", "flat", "new", "delta"):
        a[k] += v[k]
    a["pct_sum"] += v["pct_sum"]
    a["stocks"] += v["stocks"]
    a["inds"][ind] += v["n"]

def pack_mkt(t, nm, v):
    inds = v["inds"]
    it = pack(inds.most_common(1)[0][0], t, nm, v)
    it["ind_n"] = len(inds)
    it["ind_top"] = [{"ind": k, "n": c} for k, c in inds.most_common(4)]
    return it

all_top, all_dec = {}, {}
for g in GROUPS:
    if g == "个人":
        # 自然人同名无法区分（如多位「陈峰」），跨行业合并会把不同的人叠成一个，
        # 故个人榜按行业分别统计，机构榜（名称唯一）才做跨行业合并。
        pool = [pack(ind, t, nm, v) for (ind, t, nm), v in AGG.items() if t == g]
        for x in pool:
            x["ind_n"], x["ind_top"] = 1, [{"ind": x["ind"], "n": x["n"]}]
    else:
        pool = [pack_mkt(t, nm, v) for (t, nm), v in MKT.items() if t == g]
    inc_pool = sorted(pool, key=lambda x: (-x["score"], -x["n"], -x["pct_sum"]))
    all_top[g] = inc_pool[:30]
    dec_pool = [x for x in pool if x["dec"] > x["inc"]]
    dec_pool.sort(key=lambda x: (-(x["dec"] - x["inc"]), -x["n"]))
    all_dec[g] = dec_pool[:20]

OUT = {
    "date": "2026-06-30",
    "universe": len(SH),
    "mapped": len(C2I),
    "type_count": dict(TYPE_CNT),
    "summary": {
        "个人": {"holders": len({k[2] for k in AGG if k[1] == "个人"})},
        "私募": {"holders": len({k[2] for k in AGG if k[1] == "私募"})},
        "公募": {"holders": len({k[2] for k in AGG if k[1] == "公募"})},
    },
    "ind_summary": ind_summary,
    "by_ind": {ind: {g: by_ind[ind][g] for g in GROUPS} for ind in by_ind},
    "all_top": all_top,
    "all_dec": all_dec,
}
json.dump(OUT, open(os.path.join(BASE, "_industry_ranking.json"), "w", encoding="utf-8"),
          ensure_ascii=False)

# ---- 控制台校验 ----
print("全市场:", len(SH), " 已映射行业:", len(C2I))
print("股东类型分布:", dict(TYPE_CNT.most_common()))
print("\n行业强度 Top10（按聪明钱净增持家次）:")
for r in ind_summary[:10]:
    print(f"  {r['ind']:8s} 净{int(r['smart_net']):+5d}  "
          f"(个人{r['个人']['net']:+4d} 私募{r['私募']['net']:+4d} 公募{r['公募']['net']:+4d})")
print("\n行业强度 后5:")
for r in ind_summary[-5:]:
    print(f"  {r['ind']:8s} 净{int(r['smart_net']):+5d}")
for g in GROUPS:
    print(f"\n== 全市场 {g} Top8 ==")
    for x in all_top[g][:8]:
        print(f"  {x['short'][:24]:26s} [{x['mgr'][:8]:8s}] {x['ind']:6s} 家数{x['n']:3d} "
              f"增{x['inc']:2d}减{x['dec']:2d} 分{x['score']:5.2f}")
