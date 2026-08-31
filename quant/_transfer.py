import json, glob, os, sys

BASE = "G:/ai/股票/quant"
TR_DIR = "C:/Users/nonoy/.workbuddy/projects/g-ai-股票/4405b549-d4c3-4941-a66e-f648de00540e/subagents/agent-cdab452f/tool-results"

# load batch lines
batches = {}
with open(os.path.join(BASE, "_batchlines_2026-08-21.txt"), encoding="utf-8") as f:
    for line in f:
        line = line.rstrip("\n")
        if not line.strip():
            continue
        i_s, codes = line.split("\t", 1)
        batches[int(i_s)] = set(codes.split(","))

# map tool-results file -> json
files = [
    "chatcmpl-tool-ac24921e9735f893.txt",
    "chatcmpl-tool-a6dbae0b0e57cbe9.txt",
    "chatcmpl-tool-a760fdcc0519977f.txt",
    "chatcmpl-tool-9903368c4addd790.txt",
    "chatcmpl-tool-af542a145ab4112e.txt",
]

for fn in files:
    p = os.path.join(TR_DIR, fn)
    with open(p, encoding="utf-8") as f:
        raw = f.read()
    obj = json.loads(raw)
    keys = set(obj["data"].keys())
    # find matching batch
    match = None
    for i, codset in batches.items():
        if keys == codset:
            match = i
            break
    if match is None:
        # try subset
        for i, codset in batches.items():
            if keys <= codset:
                match = i
                break
    if match is None:
        print(f"NO MATCH for {fn} (keys sample: {list(keys)[:3]})")
        continue
    out = os.path.join(BASE, f"raw_2026-08-21_{match:03d}.json")
    with open(out, "w", encoding="utf-8") as f:
        f.write(raw)
    print(f"WROTE {os.path.basename(out)} batch={match} codes={len(keys)}")
