# -*- coding: utf-8 -*-
import json, os
BASE = os.path.dirname(os.path.abspath(__file__))
S = json.load(open(os.path.join(BASE, "_winrate_codes.json"), encoding="utf-8"))["S"]
B = 400
batches = [",".join(S[i:i+B]) for i in range(0, len(S), B)]
json.dump(batches, open(os.path.join(BASE, "_codes_batches.json"), "w"), ensure_ascii=False)
for i, b in enumerate(batches):
    print("=== BATCH {} | {} codes ===".format(i, b.count(",") + 1))
    print(b)
