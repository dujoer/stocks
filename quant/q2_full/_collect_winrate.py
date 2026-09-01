# -*- coding: utf-8 -*-
"""
收集「行业最强榜」所有 top10 主体 + 全市场榜主体的【全部持仓】股票代码集合 S。
- by_ind 的 actor：取其在该行业内的全部持仓（按行业反查，不用展示的 8 只）。
- all_top/all_dec 的 actor：取其跨行业全部持仓（全局反查）。
输出：_winrate_codes.json = {S:[...], actor_codes:{ "scope|ind|type|name":[codes] }}
"""
import json, os, collections

BASE = os.path.dirname(os.path.abspath(__file__))
SH = json.load(open(os.path.join(BASE, "_merged_shareholder.json"), encoding="utf-8"))
C2I = json.load(open(os.path.join(BASE, "_code2industry.json"), encoding="utf-8"))
R = json.load(open(os.path.join(BASE, "_industry_ranking.json"), encoding="utf-8"))

# ---- 反查索引：行业 -> 股东名 -> 代码集；全局 股东名 -> 代码集 ----
ind_name_codes = collections.defaultdict(lambda: collections.defaultdict(set))
name_codes = collections.defaultdict(set)
for code, e in SH.items():
    ind = C2I.get(code)
    if not ind:
        continue
    names = set()
    for s in (e.get("top10Shareholders", []) or []) + (e.get("top10FloatShareholders", []) or []):
        names.add(s["name"])
    for nm in names:
        ind_name_codes[ind][nm].add(code)
        name_codes[nm].add(code)

GROUPS = ("个人", "私募", "公募")
actor_codes = {}
S = set()
empty = 0

def take(scope, ind, g, name, codeset):
    global empty
    key = (scope, ind, g, name)
    if key in actor_codes:
        return
    cs = sorted(codeset)
    actor_codes[key] = cs
    if not cs:
        empty += 1
    S.update(cs)

# by_ind：行业内持仓
for ind, d in R["by_ind"].items():
    for g in GROUPS:
        for a in d[g]:
            take("ind", ind, g, a["name"], ind_name_codes[ind].get(a["name"], set()))

# all_top / all_dec：全局持仓
for g in GROUPS:
    for a in R["all_top"][g]:
        take("top", g, g, a["name"], name_codes.get(a["name"], set()))
    for a in R["all_dec"][g]:
        take("dec", g, g, a["name"], name_codes.get(a["name"], set()))

out = {
    "S": sorted(S),
    "actor_codes": {"{}|{}|{}|{}".format(*k): v for k, v in actor_codes.items()},
}
json.dump(out, open(os.path.join(BASE, "_winrate_codes.json"), "w", encoding="utf-8"),
          ensure_ascii=False)

from collections import Counter
c = Counter(k[0] for k in actor_codes)
print("S 总数(去重代码):", len(S))
print("actor 条目数:", len(actor_codes), " 空匹配:", empty)
print("按 scope 分布:", dict(c))
print("S 前 20:", sorted(S)[:20])
