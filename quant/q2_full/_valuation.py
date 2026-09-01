# -*- coding: utf-8 -*-
"""
全市场估值解析 + 行业估值分位聚合
输入：tool_ranking(metric=fin_valuation) 落盘结果
输出：quant/q2_full/_valuation.json      code -> {PE,PB,PS,DIV}
      quant/q2_full/_ind_valuation.json  行业 -> 中位数与全市场分位
"""
import json, os, re, glob, statistics as st

TR = r"C:\Users\nonoy\.workbuddy\projects\g-ai-股票\e3ab6e4e-351f-47a8-a451-53f648954b46\tool-results"
BASE = os.path.dirname(os.path.abspath(__file__))

files = sorted(glob.glob(os.path.join(TR, "mcp-westock-mcp-tool_ranking-*.txt")),
               key=os.path.getmtime, reverse=True)
VAL, date = {}, None
for fn in files:
    raw = open(fn, encoding="utf-8", errors="replace").read()
    m = re.search(r'\{"ok"\s*:\s*true', raw)
    if not m:
        continue
    try:
        d = json.loads(raw[m.start():])
    except Exception:
        continue
    dat = d.get("data") or {}
    if dat.get("metric") != "fin_valuation":
        continue
    date = date or dat.get("date")
    for s in dat.get("stocks", []) or []:
        VAL[s["code"]] = {"PE": s.get("PE_TTM"), "PB": s.get("PB_LF"),
                          "PS": s.get("PS_TTM"), "DIV": s.get("DIV_TTM")}
    print("解析", os.path.basename(fn), "累计", len(VAL))

json.dump({"date": date, "data": VAL},
          open(os.path.join(BASE, "_valuation.json"), "w", encoding="utf-8"),
          ensure_ascii=False)
print("估值日期:", date, " 覆盖股票数:", len(VAL))

# ---------- 行业估值聚合 ----------
C2I = json.load(open(os.path.join(BASE, "_code2industry.json"), encoding="utf-8"))
buckets = {}
for code, v in VAL.items():
    ind = C2I.get(code)
    if not ind:
        continue
    buckets.setdefault(ind, []).append(v)

rows = []
for ind, lst in buckets.items():
    # PE 只取正值（亏损股 PE 无意义），PB 取正值
    pe = sorted(x["PE"] for x in lst if x["PE"] and x["PE"] > 0)
    pb = sorted(x["PB"] for x in lst if x["PB"] and x["PB"] > 0)
    div = [x["DIV"] for x in lst if x["DIV"] is not None]
    loss = sum(1 for x in lst if not x["PE"] or x["PE"] <= 0)
    rows.append({
        "ind": ind, "n": len(lst),
        "pe_med": round(st.median(pe), 1) if pe else None,
        "pb_med": round(st.median(pb), 2) if pb else None,
        "div_med": round(st.median(div), 2) if div else None,
        "loss_ratio": round(loss / len(lst) * 100, 1),
    })

# 全市场分位：PE/PB 中位数在 31 个行业里的排名百分位（越低越便宜）
def add_rank(key, out):
    ok = [r for r in rows if r[key] is not None]
    ok.sort(key=lambda r: r[key])
    for i, r in enumerate(ok):
        r[out] = round(i / max(1, len(ok) - 1) * 100)
    for r in rows:
        r.setdefault(out, None)

add_rank("pe_med", "pe_rank")
add_rank("pb_med", "pb_rank")
for r in rows:
    vs = [r[k] for k in ("pe_rank", "pb_rank") if r[k] is not None]
    r["val_rank"] = round(sum(vs) / len(vs)) if vs else None   # 综合估值分位

rows.sort(key=lambda r: (r["val_rank"] if r["val_rank"] is not None else 999))
json.dump({"date": date, "rows": rows},
          open(os.path.join(BASE, "_ind_valuation.json"), "w", encoding="utf-8"),
          ensure_ascii=False)

print("\n行业估值（由低到高，分位越低越便宜）:")
for r in rows:
    print(f"  {r['ind']:8s} n={r['n']:4d} PE中位{str(r['pe_med']):>7s} "
          f"PB中位{str(r['pb_med']):>6s} 股息{str(r['div_med']):>5s}% "
          f"亏损占比{r['loss_ratio']:5.1f}% 估值分位{r['val_rank']}")
