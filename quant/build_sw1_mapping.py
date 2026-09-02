import json, re, os

Q = r"G:/ai/股票/quant"
F = r"C:/Users/nonoy/.workbuddy/projects/g-ai-股票/e3ab6e4e-351f-47a8-a451-53f648954b46/tool-results/mcp-westock-mcp-data_sector-1788282121297-f5af83.txt"

# 1) sw1 constituents (name -> member stock names)
raw = json.load(open(F, encoding="utf-8"))["data"]
sw1_members = {}   # clean sw1 name -> list of stock names
sw1_code = {}      # clean sw1 name -> code
for k, v in raw.items():
    sec = v.get("sectorName", "")
    name = re.sub(r"^申万一级行业成分股-", "", sec)
    code = (v.get("listCode") or k).replace("comp_", "")
    names = [s.get("name") for s in v.get("stocks", []) if s.get("name")]
    sw1_members[name] = names
    sw1_code[name] = code
print("sw1 count:", len(sw1_members))

# 2) name -> sw2
name2sw2 = json.load(open(os.path.join(Q, "_name2sw2.json"), encoding="utf-8"))

# 3) sw2 clean name -> pctVal (LIVE 2026-09-01 from data_sector ranking)
sw2_chg = json.load(open(os.path.join(Q, "sw2_chg_live.json"), encoding="utf-8"))
print("sw2 chg map count:", len(sw2_chg))

# 4) sw1 -> member sw2 + derived changePct
sw1_detail = {}
for sw1, members in sw1_members.items():
    sw2set = []
    for nm in members:
        s2 = name2sw2.get(nm)
        if s2 and s2 not in sw2set:
            sw2set.append(s2)
    chgs = [sw2_chg[s] for s in sw2set if s in sw2_chg and sw2_chg[s] is not None]
    chg = round(sum(chgs) / len(chgs), 3) if chgs else None
    sw1_detail[sw1] = {
        "code": sw1_code.get(sw1, ""),
        "member_sw2": sw2set,
        "member_count": len(sw2set),
        "n_with_chg": len(chgs),
        "changePct": chg,
    }

json.dump(sw1_detail, open(os.path.join(Q, "sw1_detail.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
json.dump(sw2_chg, open(os.path.join(Q, "sw2_chg.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)

# report
print("\n=== sw1 derived changePct (member sw2 avg) ===")
for sw1, d in sorted(sw1_detail.items(), key=lambda kv: (kv[1]["changePct"] is None, -(kv[1]["changePct"] or 0))):
    print(f"{sw1:8s} chg={d['changePct']}  members={d['member_count']} w/chg={d['n_with_chg']}")
# sanity: which sw1 have no chg
noc = [s for s,d in sw1_detail.items() if d["changePct"] is None]
print("\nsw1 with NO derived chg:", noc)
