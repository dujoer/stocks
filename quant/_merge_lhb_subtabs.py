#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 data_lhb 分项(4 次 type 调用)的原始响应合并进 quant/lhb/{DATE}.json。

数据源（westock-mcp data_lhb，必须显式 type，默认"全部"只给 all 全榜）：
    data_lhb(date=DATE, type="jg")     # 机构榜
    data_lhb(date=DATE, type="yyb")    # 游资席位
    data_lhb(date=DATE, type="gslmr")  # 机构净买入
    data_lhb(date=DATE, type="gslxw")  # 机构净卖出

每次响应形如 {ok,data:{date, jg/yzb/yyb/gslmr/gslxw:[...]}}，保存成独立 JSON，
用本脚本合并（保留已有 all 全榜，去重合并四项），再跑 build_dashboards 即可出机构/游资分析。

用法:
    python quant/_merge_lhb_subtabs.py --date 2026-09-03 \
        --jg _lhb_jg.json --yyb _lhb_yyb.json \
        --gslmr _lhb_gslmr.json --gslxw _lhb_gslxw.json
    # 或：python quant/_merge_lhb_subtabs.py --date 2026-09-03 --dir <目录>
    #      （目录下需含 _lhb_{jg,yyb,gslmr,gslxw}.json）

可选 --out 指定输出路径(默认 quant/lhb/{DATE}.json)；测试时指向临时文件避免覆盖。
"""
import argparse, json, os, sys

TABS = ["jg", "yyb", "gslmr", "gslxw"]
# build_dashboards.py 对每个分项期望的必需键（用于告警，不阻断）
EXPECT_KEYS = {
    "jg": {"code", "name", "netBuyAmt", "instBuyAmt", "netBuyRate", "instBuyBranchCount"},
    "yyb": {"id", "name", "code", "stockName", "buyAmt"},
    "gslmr": {"code", "name", "netAmt", "upRate", "bAmt", "sAmt", "winNum"},
    "gslxw": {"id", "name", "netAmt", "winRate", "stockList"},
}


def load_tab(path, tab):
    d = json.load(open(path, encoding="utf-8"))
    return d.get("data", {}).get(tab, [])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--dir", help="目录，内含 _lhb_{jg,yyb,gslmr,gslxw}.json")
    ap.add_argument("--jg")
    ap.add_argument("--yyb")
    ap.add_argument("--gslmr")
    ap.add_argument("--gslxw")
    ap.add_argument("--out", help="输出路径(默认 quant/lhb/{DATE}.json)")
    args = ap.parse_args()

    paths = {}
    if args.dir:
        for t in TABS:
            p = os.path.join(args.dir, f"_lhb_{t}.json")
            if os.path.exists(p):
                paths[t] = p
    else:
        for t in TABS:
            p = getattr(args, t)
            if p:
                paths[t] = p

    if not paths:
        print("ERROR: 未提供任何分项输入 (--dir 或 --jg/--yyb/--gslmr/--gslxw)")
        sys.exit(1)

    out = args.out or os.path.join("quant", "lhb", f"{args.date}.json")
    if not os.path.exists(out):
        print(f"ERROR: 目标文件不存在 {out}（请先确保 lhb/{args.date}.json 已含 all 全榜）")
        sys.exit(1)

    main_f = json.load(open(out, encoding="utf-8"))
    data = main_f["data"]

    for t in TABS:
        if t not in paths:
            print(f"  [跳过] {t} 未提供")
            continue
        arr = load_tab(paths[t], t)
        # 宽松键校验：只告警不阻断
        present = set().union(*[set(r.keys()) for r in arr]) if arr else set()
        missing = EXPECT_KEYS[t] - present
        if missing:
            print(f"  [WARN] {t}: 期望键缺失 {sorted(missing)}（数据可能不完整）")
        existing = data.get(t, [])
        seen, merged = set(), []
        for r in existing + arr:
            k = json.dumps(r, sort_keys=True, ensure_ascii=False)
            if k not in seen:
                seen.add(k)
                merged.append(r)
        data[t] = merged
        print(f"  [OK] {t}: +{len(arr)} from pull, merged total={len(merged)}")

    json.dump(main_f, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    empty = not any(data.get(t) for t in TABS)
    print(f"写入 {out} | LHB_DETAIL_EMPTY 将为: {empty}")


if __name__ == "__main__":
    main()
