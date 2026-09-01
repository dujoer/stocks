# -*- coding: utf-8 -*-
"""解析落盘的申万一级行业成分股，构建 code -> 行业 映射。"""
import json, os, re, glob, collections, unicodedata

TR = r"C:\Users\nonoy\.workbuddy\projects\g-ai-股票\e3ab6e4e-351f-47a8-a451-53f648954b46\tool-results"
BASE = os.path.dirname(os.path.abspath(__file__))

def norm(n: str) -> str:
    """名称规范化：去空白、全角转半角、去 XD/XR/DR 前缀、去 -U/-W/-UW 后缀。"""
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

files = sorted(glob.glob(os.path.join(TR, "mcp-westock-mcp-data_sector-*.txt")))
print("成分股落盘文件数:", len(files))

# 1. 解析：板块 -> 行业名 + 成分股名称集合
ind_names = {}   # 行业名 -> set(股票名)
for fn in files:
    raw = open(fn, encoding="utf-8", errors="replace").read()
    m = re.search(r'\{"ok"\s*:\s*true', raw)
    if not m:
        print("  跳过(非ok):", os.path.basename(fn)); continue
    d = json.loads(raw[m.start():])
    for key, blk in d.get("data", {}).items():
        if not key.startswith("comp_sw1_"):
            continue
        sname = blk.get("sectorName", "")
        ind = sname.split("-")[-1] if "-" in sname else sname
        names = {s["name"] for s in blk.get("stocks", [])}
        ind_names.setdefault(ind, set()).update(names)
        print(f"  {ind:8s} {len(names):5d} 只  (原始 {blk.get('totalStocks')} 条)")

print("\n行业数:", len(ind_names), " 覆盖股票名总数:", sum(len(v) for v in ind_names.values()))

# 2. 名称 -> code（来自全市场股东数据），按规范化名称索引
SH = json.load(open(os.path.join(BASE, "_merged_shareholder.json"), encoding="utf-8"))
name2code = collections.defaultdict(list)
for code, e in SH.items():
    nm = norm(e.get("name") or "")
    if nm:
        name2code[nm].append(code)

dup = {n: c for n, c in name2code.items() if len(c) > 1}
print("全市场股票数:", len(SH), " 规范化后重名数:", len(dup))
if dup:
    print("  重名样例:", list(dup.items())[:10])

# 3. 构建 code -> 行业（三级匹配：精确 -> 前缀唯一 -> 失败）
code2ind = {}
conflict = []
unmatched = collections.defaultdict(list)
fuzzy_hits = []
for ind, names in ind_names.items():
    for nm in names:
        key = norm(nm)
        codes = name2code.get(key, [])
        if not codes and len(key) >= 2:
            # 前缀匹配（应对 XD 截断造成的不完整名称，如 '亚宝药' vs '亚宝药业'）
            cand = [x for n2, cs in name2code.items()
                    if len(n2) >= 2 and abs(len(n2) - len(key)) <= 3
                    and (n2.startswith(key) or key.startswith(n2))
                    for x in cs]
            if len(cand) == 1:
                codes = cand
                fuzzy_hits.append((nm, cand[0], ind))
        if not codes:
            unmatched[ind].append(nm)
            continue
        if len(codes) > 1:
            conflict.append((nm, codes, ind))
        for c in codes:
            if c in code2ind and code2ind[c] != ind:
                conflict.append((nm, [c], f"{code2ind[c]}→{ind}"))
            code2ind[c] = ind

print("前缀模糊匹配成功:", len(fuzzy_hits), fuzzy_hits[:10])

print("\n已映射代码数:", len(code2ind), "/", len(SH),
      f"  覆盖率 {len(code2ind)*100.0/len(SH):.1f}%")
miss = [c for c in SH if c not in code2ind]
print("未映射代码数:", len(miss))
if miss:
    print("  未映射样例:", [(c, SH[c].get("name")) for c in miss[:20]])

if unmatched:
    print("\n成分股中未能匹配到代码的名称（按行业）:")
    for ind, ns in sorted(unmatched.items(), key=lambda x: -len(x[1]))[:15]:
        print(f"  {ind:8s} {len(ns):3d}  {ns[:8]}")
if conflict:
    print("\n冲突:", len(conflict), conflict[:10])

# 手工补充：sz002731 中报名称为空（实为 *ST萃华 / 萃华珠宝，属纺织服饰）
code2ind.setdefault("sz002731", "纺织服饰")

out = os.path.join(BASE, "_code2industry.json")
json.dump(code2ind, open(out, "w", encoding="utf-8"), ensure_ascii=False)
print("补录 sz002731 ->", code2ind["sz002731"])
print("已保存", out, len(code2ind), "条")
