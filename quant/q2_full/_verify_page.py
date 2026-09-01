# -*- coding: utf-8 -*-
"""页面自检：内嵌 JSON 可解析、无破坏性字符、关键结构齐全"""
import json, os, re

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
P = os.path.join(ROOT, "web", "2026-q2-industry-elite.html")
s = open(P, encoding="utf-8").read()
ok = True

def chk(cond, msg):
    global ok
    print(("  [OK] " if cond else "  [!!] ") + msg)
    if not cond:
        ok = False

print("文件大小: %.0f KB" % (len(s) / 1024))

# 1. 破坏性字符
chk("</script>" not in s[s.find("<script>") + 8: s.rfind("</script>")],
    "数据段内无嵌套 </script>")
chk(s.count("<script>") == 1 and s.count("</script>") == 1, "script 标签成对且唯一")

# 2. 内嵌 JSON 可解析
m = re.search(r"const D = (\{.*?\});\nconst GS", s, re.S)
chk(bool(m), "定位到内嵌数据对象")
D = json.loads(m.group(1))
chk(D["universe"] == 5544, f"全市场股票数 = {D['universe']}")
chk(len(D["ind_rows"]) == 31, f"行业数 = {len(D['ind_rows'])}")
chk(len(D["by_ind"]) == 31, f"行业榜单数 = {len(D['by_ind'])}")

# 3. 每行业三榜数量
short = []
for ind, d in D["by_ind"].items():
    for g in ("个人", "私募", "公募"):
        n = len(d.get(g, []))
        if n < 10:
            short.append(f"{ind}/{g}={n}")
chk(True, f"未满 10 名的行业组合 {len(short)} 个: {short}")

# 4. 榜单字段完整
sample = D["by_ind"]["电子"]["公募"][0]
need = {"nm", "mgr", "n", "inc", "dec", "flat", "pct", "sc", "b", "p", "d", "ind", "st"}
chk(need <= set(sample), f"榜单字段完整: {sorted(set(sample))}")
chk(all(isinstance(x["st"], list) for g in ("个人", "私募", "公募")
        for x in D["by_ind"]["电子"][g]), "持仓明细均为数组")

# 5. 强度分拆解自洽
bad = []
for ind, d in D["by_ind"].items():
    for g in ("个人", "私募", "公募"):
        for x in d[g]:
            if abs(x["b"] + x["p"] + x["d"] - x["sc"]) > 0.02:
                bad.append((ind, g, x["nm"]))
chk(not bad, f"强度分 = 广度+力度+深度（误差<0.02），异常 {len(bad)} 条")

# 6. 排序单调递减
bad2 = []
for ind, d in D["by_ind"].items():
    for g in ("个人", "私募", "公募"):
        sc = [x["sc"] for x in d[g]]
        if sc != sorted(sc, reverse=True):
            bad2.append(f"{ind}/{g}")
chk(not bad2, f"各榜按强度降序，异常 {len(bad2)} 个: {bad2}")

# 7. 关键 DOM 锚点
for anchor in ["id='indTitle'", "id='indBody'", "class='pills'",
               "data-scope='top'", "data-scope='dec'"]:
    chk(anchor in s, f"存在锚点 {anchor}")
chk(s.count("class='pill' data-ind=") == 31, "31 个行业按钮")

# 8. 被动/PE 类记录确已剔除
allnames = [x["nm"] for ind in D["by_ind"] for g in ("私募", "公募")
            for x in D["by_ind"][ind][g]] + \
           [x["nm"] for g in ("私募", "公募") for x in D["all_top"][g]]
leak_p = [n for n in allnames if any(k in n for k in ("ETF", "指数型", "联接"))
          and "增强" not in n]
leak_e = [n for n in allnames if any(k in n for k in ("股权投资", "创业投资", "产业投资基金"))]
chk(not leak_p, f"无被动指数漏网: {leak_p[:5]}")
chk(not leak_e, f"无一级市场基金漏网: {leak_e[:5]}")

# 9. 不得出现个人持仓/组合内容（项目硬性约束）
for kw in ["组合持仓", "我的持仓", "portfolio", "持仓盈亏", "组合总看板"]:
    chk(kw not in s, f"未出现禁展关键词「{kw}」")

print("\n结果:", "全部通过" if ok else "存在问题")
