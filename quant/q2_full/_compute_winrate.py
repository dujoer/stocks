# -*- coding: utf-8 -*-
"""
逐主体计算：胜率 = 上涨股数 / 有效持股数（两端价齐全）；平均涨幅 = 各股区间收益均值。
区间：2026-06-30 -> 2026-09-01。结果写回 _industry_ranking.json 的每个 actor，
并另存 _winrate.json 备查。
"""
import json, os
from collections import defaultdict

BASE = os.path.dirname(os.path.abspath(__file__))
wc = json.load(open(os.path.join(BASE, "_winrate_codes.json"), encoding="utf-8"))
prices = json.load(open(os.path.join(BASE, "_prices_raw.json"), encoding="utf-8"))
R = json.load(open(os.path.join(BASE, "_industry_ranking.json"), encoding="utf-8"))

D0, D1 = "2026-06-30", "2026-09-01"

# actor_codes: "scope|ind|type|name" -> [codes]
stats = {}
for key, codes in wc["actor_codes"].items():
    scope, ind, g, name = key.split("|", 3)
    ups = dns = flt = 0
    rets = []
    n_valid = 0
    for c in codes:
        p0 = prices.get("{}|{}".format(c, D0))
        p1 = prices.get("{}|{}".format(c, D1))
        if p0 is None or p1 is None or not p0:
            continue
        n_valid += 1
        r = (p1 - p0) / p0
        rets.append(r)
        if r > 0:
            ups += 1
        elif r < 0:
            dns += 1
        else:
            flt += 1
    if n_valid == 0:
        win_pct = None
        avg_pct = None
    else:
        win_pct = round(ups / n_valid * 100, 1)
        avg_pct = round(sum(rets) / n_valid * 100, 2)
    stats[key] = {
        "n_valid": n_valid, "up": ups, "down": dns, "flat": flt,
        "win_pct": win_pct, "avg_pct": avg_pct,
    }

# 写回 ranking JSON
def enrich(lst, scope, ind, g):
    for a in lst:
        k = "{}|{}|{}|{}".format(scope, ind, g, a["name"])
        s = stats.get(k)
        if s:
            a["win"] = s["win_pct"]
            a["avg"] = s["avg_pct"]
            a["n_valid"] = s["n_valid"]
            a["up"] = s["up"]
            a["down"] = s["down"]
        else:
            a["win"] = None
            a["avg"] = None
            a["n_valid"] = 0

for ind, d in R["by_ind"].items():
    for g in ("个人", "私募", "公募"):
        enrich(d[g], "ind", ind, g)
for g in ("个人", "私募", "公募"):
    enrich(R["all_top"][g], "top", g, g)
    enrich(R["all_dec"][g], "dec", g, g)

json.dump(R, open(os.path.join(BASE, "_industry_ranking.json"), "w", encoding="utf-8"),
          ensure_ascii=False)
json.dump(stats, open(os.path.join(BASE, "_winrate.json"), "w", encoding="utf-8"),
          ensure_ascii=False)

# 统计覆盖
total = len(wc["actor_codes"])
filled = sum(1 for s in stats.values() if s["n_valid"] > 0)
print("actor 条目:", total, " 有有效胜率:", filled)
# 抽样：公募 by_ind 第一个行业
sample_ind = next(iter(R["by_ind"]))
print("抽样行业:", sample_ind, "公募Top3:")
for a in R["by_ind"][sample_ind]["公募"][:3]:
    print("  ", a["short"][:16], "胜率", a.get("win"), "均涨", a.get("avg"), "n_valid", a.get("n_valid"))
