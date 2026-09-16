import os, re
MT = "market-trend"
_WBROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

# 1) Per-date _build_*.py: OUT = os.path.join(HERE, "crowd-psychology-risk-radar-YYYYMMDD.html") -> web/psychology/
pat_out = re.compile(r'OUT = os\.path\.join\(HERE, "crowd-psychology-risk-radar-(\d{8})\.html"\)')
rep_out = r'OUT = os.path.join(HERE, "..", "web", "psychology", "crowd-psychology-risk-radar-\1.html")'

# 2) _update_hub_0902.py PATH
pat_path = re.compile(r'PATH = os\.path\.join\(HERE, "index\.html"\)')
rep_path = r'PATH = os.path.join(HERE, "..", "web", "psychology", "index.html")'

# 3) legacy absolute paths in _build_index_0825.py
changed = []
for fn in sorted(os.listdir(MT)):
    if not fn.endswith(".py"):
        continue
    p = os.path.join(MT, fn)
    s = open(p, encoding="utf-8").read()
    orig = s
    s = pat_out.sub(rep_out, s)
    s = pat_path.sub(rep_path, s)
    # legacy 写死绝对路径：G:/ai/股票/market-trend/... -> _WBROOT/market-trend/...
    for name in ("index.html", "_check_idx.js"):
        s = s.replace("G:/ai/股票/market-trend/" + name,
                      os.path.join(_WBROOT, "market-trend", name))
        s = s.replace("G:/ai/股票/web/psychology/" + name,
                      os.path.join(_WBROOT, "web", "psychology", name))
    if s != orig:
        open(p, "w", encoding="utf-8").write(s)
        changed.append(fn)

print("Updated files:")
for c in changed:
    print("  ", c)
if not changed:
    print("  (none)")
