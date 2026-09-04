#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""扫描已合并的 1375 只 Q2 中报十大股东数据，统计 40 家知名私募/牛散的真实现身情况。
输出: quant/_shareholder/elite_coverage.json
数据口径: 2026-06-30 Q2 中报（_merged_shareholder.json），低噪声、真实、非收益胜率。
"""
import json, os

BASE = os.path.dirname(__file__)
# 优先用全市场股东数据（a-share-full-market-shareholder-elite 技能产出，5544 只 / 2026-06-30），
# 回退到本项目合并的 1375 只样本。两者结构一致（code/date/name/top10FloatShareholders...）。
_FULL = os.path.join(BASE, "..", "q2_full", "_merged_shareholder.json")
_PARTIAL = os.path.join(BASE, "_merged_shareholder.json")
SRC = _FULL if os.path.exists(_FULL) else _PARTIAL
OUT = os.path.join(BASE, "elite_coverage.json")

# 40 家主体 → 匹配关键词（私募用产品/公司名前缀；牛散用自然人姓名）
# type: private=私募(产品名含关键词, 不剔除机构后缀); retail=牛散(自然人姓名, 剔除机构后缀防误匹配)
MATCH = {
    # ---- 私募 Top20 ----
    "高毅资产": ("private", ["高毅"]),
    "景林资产": ("private", ["景林"]),
    "淡水泉投资": ("private", ["淡水泉"]),
    "重阳投资": ("private", ["重阳"]),
    "千合资本": ("private", ["千合"]),
    "星石投资": ("private", ["星石"]),
    "朱雀投资": ("private", ["朱雀"]),
    "混沌投资": ("private", ["混沌"]),
    "林园投资": ("private", ["林园"]),
    "东方港湾": ("private", ["东方港湾"]),
    "高瓴资本": ("private", ["高瓴"]),
    "宁泉资产": ("private", ["宁泉"]),
    "半夏投资": ("private", ["半夏"]),
    "聚鸣投资": ("private", ["聚鸣"]),
    "盘京投资": ("private", ["盘京"]),
    "石锋资产": ("private", ["石锋"]),
    "正心谷": ("private", ["正心谷"]),
    "幻方量化": ("private", ["幻方"]),
    "九坤投资": ("private", ["九坤"]),
    "明汯投资": ("private", ["明汯"]),
    # ---- 牛散 Top20 ----
    "葛卫东": ("retail", ["葛卫东"]),
    "章建平": ("retail", ["章建平"]),
    "赵建平": ("retail", ["赵建平"]),
    "张素芬": ("retail", ["张素芬"]),
    "何雪萍": ("retail", ["何雪萍"]),
    "周信钢": ("retail", ["周信钢"]),
    "陈发树": ("retail", ["陈发树"]),
    "蒋仕波": ("retail", ["蒋仕波"]),
    "夏重阳": ("retail", ["夏重阳"]),
    "魏巍": ("retail", ["魏巍"]),
    "吕强": ("retail", ["吕强"]),
    "邹瀚枢": ("retail", ["邹瀚枢"]),
    "赵吉": ("retail", ["赵吉"]),
    "李欣": ("retail", ["李欣"]),
    "刘芳": ("retail", ["刘芳"]),
    "王萍": ("retail", ["王萍"]),
    "屠文斌": ("retail", ["屠文斌"]),
    "沈付兴": ("retail", ["沈付兴"]),
    "邱宝裕": ("retail", ["邱宝裕"]),
    "舒逸民": ("retail", ["舒逸民"]),
}

INST_SUFFIX = ["基金", "公司", "合伙", "资管", "信托", "银行", "证券", "投资",
               "理财", "保险", "有限", "集团", "控股", "资产管理", "财富"]

def is_institution(name):
    return any(k in name for k in INST_SUFFIX)

def main():
    raw = json.load(open(SRC, encoding="utf-8"))
    data = raw.get("data", raw)
    date = None
    # 统计容器
    res = {name: {"type": t, "kw": kw, "count": 0, "stocks": [], "confidence": "high"}
           for name, (t, kw) in MATCH.items()}

    seen = {name: set() for name in MATCH}  # 去重 (code,holder)
    n_rec = 0
    for code, rec in data.items():
        n_rec += 1
        if date is None:
            date = rec.get("date")
        name = rec.get("name", "")
        for lst in ("top10FloatShareholders", "top10Shareholders"):
            for h in rec.get(lst) or []:
                hn = (h.get("name") or "").strip()
                if not hn:
                    continue
                for ename, (t, kwlist) in MATCH.items():
                    for kw in kwlist:
                        if kw not in hn:
                            continue
                        # 牛散: 自然人姓名匹配但持有人是机构 → 剔除(疑似误匹配)
                        if t == "retail" and is_institution(hn):
                            continue
                        # 同一持有人在「流通」与「总」名单中重复出现 → 去重为同一仓位只算一次
                        key = (code, hn)
                        if key in seen[ename]:
                            continue
                        seen[ename].add(key)
                        r = res[ename]
                        r["count"] += 1
                        r["stocks"].append({
                            "code": code, "name": name, "holder": hn,
                            "holdPct": h.get("holdPct"),
                            "holdChange": h.get("holdChange"),
                            "list": "float" if lst.startswith("top10Float") else "total",
                        })

    # 牛散若出现但部分匹配被机构后缀剔除，置信度保持 high(已剔除噪声)
    out = {
        "meta": {"source": os.path.basename(SRC), "date": date, "sample": n_rec},
        "entities": res,
    }
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    # 打印摘要
    print(f"样本: {n_rec} 只, 数据日期: {date}")
    print(f"{'主体':<10}{'类型':<6}{'现身数':<8}示例")
    for ename, (t, _) in MATCH.items():
        r = res[ename]
        ex = "、".join(s["name"] for s in r["stocks"][:3])
        print(f"{ename:<10}{t:<6}{r['count']:<8}{ex}")

if __name__ == "__main__":
    main()
