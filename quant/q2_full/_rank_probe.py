# -*- coding: utf-8 -*-
"""探查：按行业 × 股东类型聚合，验证「最强」榜单的数据合理性。"""
import json, os, re, collections

BASE = os.path.dirname(os.path.abspath(__file__))
SH = json.load(open(os.path.join(BASE, "_merged_shareholder.json"), encoding="utf-8"))
C2I = json.load(open(os.path.join(BASE, "_code2industry.json"), encoding="utf-8"))

# ---------- 分类 ----------
NATIONAL = ["国新", "社保", "养老金", "基本养老", "中央汇金", "国调", "国务院国资委",
            "国家集成电路", "国有企业结构", "证金", "证券金融", "社会保障基金"]
FOREIGN = ["HONG KONG", "香港中央结算", "HKSCC", "UBS", "MORGAN", "BARCLAYS", "J.P.Morgan",
           "JPMorgan", "Goldman", "高盛", "BLACKROCK", "摩根", "Nominee", "Nominees",
           "GREENWOODS", "CICC", "阿布达比", "科威特", "新加坡政府", "GIC",
           "加拿大年金", "安大略", "魁北克", "挪威", "SCHRODER", "MACQUARIE", "CITIBANK"]
TRUST = ["信托"]
PASSIVE = ["交易型开放式", "ETF", "指数型", "指数基金", "联接"]
PRIVATE = ["私募"]
FUNDSTRONG = ["基金", "证券投资基金"]
BIG_HOLDER_PCT = 10.0    # 持股比例 ≥ 此值视为实控人/大股东记录，不计入牛散

def is_passive(name):
    if "增强" in name:            # 指数增强属主动管理
        return False
    return any(k in name for k in PASSIVE) or "指数" in name
INST_WORDS = ["有限公司", "股份", "公司", "银行", "保险", "证券", "资管", "资产", "投资",
              "合伙", "企业", "中心", "基金", "信托", "社", "会", "局", "部", "委",
              "大学", "学院", "研究院", "集团", "厂", "店", "行", "社"]

def is_chinese_name(n):
    return all('\u4e00' <= c <= '\u9fff' for c in n)

def holder_type(name, pct=0.0):
    """返回: 个人 / 私募 / 公募 / 被动 / 国家队 / 外资 / 信托 / 机构 / 大股东 / 其他"""
    if name in KNOWN_CATTLE: return "个人"
    for k in NATIONAL:
        if k in name: return "国家队"
    for k in FOREIGN:
        if k in name: return "外资"
    for k in TRUST:
        if k in name: return "信托"
    for k in PRIVATE:
        if k in name: return "私募"
    if is_passive(name): return "被动"
    for k in FUNDSTRONG:
        if k in name: return "公募"
    if any(w in name for w in INST_WORDS): return "机构"
    # 自然人：2~4 个纯汉字；持股过高视为实控人/大股东
    if 2 <= len(name) <= 4 and is_chinese_name(name):
        return "大股东" if pct >= BIG_HOLDER_PCT else "个人"
    return "其他"

# 载入已知牛散名单
src = open(os.path.join(BASE, "..", "build_q2_dashboard.py"), encoding="utf-8").read()
m = re.search(r"KNOWN_CATTLE = \{(.*?)\}", src, re.S)
KNOWN_CATTLE = set(re.findall(r'"([^"]+)"', m.group(1)))

def collect(entry):
    by = {}
    for s_ in ("top10Shareholders", "top10FloatShareholders"):
        for s in entry.get(s_, []) or []:
            n = s["name"]
            if n not in by:
                by[n] = {"holdChange": s.get("holdChange", 0),
                         "holdPct": s.get("holdPct", 0), "holdShares": s.get("holdShares", 0)}
            else:
                if s.get("holdChange", 0) != 0 and by[n]["holdChange"] == 0:
                    by[n]["holdChange"] = s["holdChange"]
                if s.get("holdShares", 0) > by[n]["holdShares"]:
                    by[n]["holdShares"] = s["holdShares"]; by[n]["holdPct"] = s.get("holdPct", 0)
    return by

# ---------- 聚合：(行业, 类型, 股东名) -> 统计 ----------
AGG = collections.defaultdict(lambda: {"n":0,"inc":0,"dec":0,"flat":0,"pct_sum":0.0,"delta":0})
typ_cnt = collections.Counter()
for code, e in SH.items():
    ind = C2I.get(code)
    if not ind: continue
    for nm, h in collect(e).items():
        t = holder_type(nm, h["holdPct"] or 0)
        typ_cnt[t] += 1
        if t not in ("个人", "私募", "公募"): continue
        a = AGG[(ind, t, nm)]
        a["n"] += 1
        a["pct_sum"] += h["holdPct"] or 0
        a["delta"] += h["holdChange"] or 0
        d = h["holdChange"] or 0
        if d > 0: a["inc"] += 1
        elif d < 0: a["dec"] += 1
        else: a["flat"] += 1

print("股东类型分布:", dict(typ_cnt.most_common()))
print("参与排名的组合数:", len(AGG))

# ---------- 探查：每个类型在行业内的持股家数分布 ----------
for t in ("个人", "私募", "公募"):
    items = [(k, v) for k, v in AGG.items() if k[1] == t]
    multi = [1 for _, v in items if v["n"] >= 2]
    print(f"\n[{t}] 组合数 {len(items)}  其中行业内持股>=2家的 {len(multi)}")

# ---------- 预览：几个行业的 Top10（按持股家数 + 净增持） ----------
def score(v):
    breadth = min(v["n"], 6)                       # 广度 0-6
    tot = v["inc"] + v["dec"]
    direc = ((v["inc"] - v["dec"]) / tot * 3) if tot else 0   # 方向 -3 ~ +3
    depth = min(v["pct_sum"], 20) / 20 * 3         # 深度 0-3
    return breadth + direc + depth

for ind in ("电子", "医药生物", "银行", "机械设备"):
    print("\n" + "="*70)
    print("行业:", ind)
    for t in ("个人", "私募", "公募"):
        items = [(k[2], v) for k, v in AGG.items() if k[0] == ind and k[1] == t]
        items.sort(key=lambda x: -score(x[1]))
        print(f"  -- {t} Top8 --")
        for nm, v in items[:8]:
            print(f"     {nm[:26]:28s} 家数{v['n']:3d} 增{v['inc']:3d} 减{v['dec']:3d} "
                  f"比例和{v['pct_sum']:7.2f}%  分{score(v):5.2f}")
