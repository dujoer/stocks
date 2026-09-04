import os, hashlib
WEB = "web"
MT = "market-trend"

def h(p):
    try:
        with open(p, "rb") as f:
            return hashlib.md5(f.read()).hexdigest()
    except Exception as e:
        return "ERR:"+str(e)

def expected(flat_name):
    b = flat_name
    if b == "index.html": return os.path.join(WEB,"lhb","index.html")
    if b == "lhb.html": return os.path.join(WEB,"lhb","lhb.html")
    if b.startswith("lhb_"): return os.path.join(WEB,"lhb",b)
    if b == "daily_overview.html": return os.path.join(WEB,"market","index.html")
    if b.startswith("daily_overview_"): return os.path.join(WEB,"market",b)
    if b == "hotmoney.html": return os.path.join(WEB,"market","hotmoney.html")
    if b.startswith("status_"): return os.path.join(WEB,"market",b)
    if b.startswith("limitup_weekly_"): return os.path.join(WEB,"market",b)
    if b == "block.html": return os.path.join(WEB,"block","index.html")
    if b.startswith("block_") and b != "block_archive.html": return os.path.join(WEB,"block",b)
    if b == "block_archive.html": return os.path.join(WEB,"block","archive.html")
    if b == "exec.html": return os.path.join(WEB,"exec","index.html")
    if b == "sector-strength-index.html": return os.path.join(WEB,"sector","index.html")
    if b == "sector-strength-trend.html": return os.path.join(WEB,"sector","trend.html")
    if b.startswith("sector-strength-"): return os.path.join(WEB,"sector",b)
    if b == "sections.html": return os.path.join(WEB,"sections","index.html")
    if b.startswith("research-"): return os.path.join(WEB,"research",b)
    if b == "2026-q2-industry-elite.html": return os.path.join(WEB,"shareholder",b)
    return None

print("=== web/ root flat files ===")
for fn in sorted(os.listdir(WEB)):
    fp = os.path.join(WEB, fn)
    if not os.path.isfile(fp) or not fn.endswith(".html"): continue
    exp = expected(fn)
    if exp is None:
        print(f"  [NO-MAP] {fn}"); continue
    if not os.path.exists(exp):
        print(f"  [MISSING SUBDIR] {fn} -> {exp}"); continue
    if h(fp) == h(exp):
        print(f"  [DUP-OK] {fn}")
    else:
        print(f"  [DIFF!] {fn} != {exp}  (keep both)")

print("=== market-trend html ===")
for fn in sorted(os.listdir(MT)):
    fp = os.path.join(MT, fn)
    if not os.path.isfile(fp) or not fn.endswith(".html"): continue
    exp = os.path.join(WEB,"psychology",fn)
    if not os.path.exists(exp):
        print(f"  [MISSING SUBDIR] {fn} -> {exp}"); continue
    if h(fp) == h(exp):
        print(f"  [DUP-OK] {fn}")
    else:
        print(f"  [DIFF!] {fn} != {exp}")
print("DONE")
