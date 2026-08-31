import json, os

SRC_DIR = r"C:/Users/nonoy/.workbuddy/projects/g-ai-股票/4405b549-d4c3-4941-a66e-f648de00540e/subagents/agent-19a7abd3/tool-results"
DST_DIR = r"G:/ai/股票/quant"
DAY = "2026-08-18"

mapping = {
    "b813425d59152e42": 0,
    "9480ec5d8ba65df2": 500,
    "a0b1d616655617d2": 1000,
    "8fdfb65fcfeb1fcf": 1500,
    "91f3aa78e9a5ba77": 2000,
    "8bf0120afddecc58": 2500,
    "b21f1100fddcc2fc": 3000,
    "93c2adad4dc5a03e": 3500,
    "ba77ab40d48e774d": 4000,
    "b7f124af2c952469": 4500,
    "9f82adf926754903": 5000,
}

for fname, off in mapping.items():
    path = os.path.join(SRC_DIR, f"chatcmpl-tool-{fname}.txt")
    with open(path, "r", encoding="utf-8") as f:
        raw = f.read()
    obj = json.loads(raw)  # validate full JSON parses
    assert obj.get("ok") is True, f"{fname} not ok"
    n = len(obj["data"]["stocks"])
    dst = os.path.join(DST_DIR, f"enum_{DAY}_{off}.json")
    with open(dst, "w", encoding="utf-8") as f:
        f.write(raw)
    print(f"offset={off:5d} stocks={n:4d} -> enum_{DAY}_{off}.json")

print("CONV_DONE")
