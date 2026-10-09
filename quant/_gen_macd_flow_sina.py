# -*- coding: utf-8 -*-
"""MACD 池 20日主力净流入（离线源：新浪 MoneyFlow）。

westock data_fund_flow 服务端间歇限频（首批量 OK、余量熔断），且用户要求"真更新、不降级"。
改用离线新浪主力资金流 mf20（20日主力净流入，元）作 MainNetFlow20D 口径，覆盖全 200 只，
与 picks 离线富集同源，保证 09-22 MACD 池为真实数据而非空页。

结构对齐 macd_build.build_from_raw：{code:{"data":[{"MainNetFlow20D","MainNetFlow",
                                                "MainInflowCircRate","MainInflowRank"}]}}
circRate/rank 新浪无对应字段，置 0（仅展示用，不参与筛选）。

用法：python3 quant/_gen_macd_flow_sina.py --date 2026-10-09
"""
import sys, os, json, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fetch_rev_flow import sina_batch

_AP = argparse.ArgumentParser(description="MACD 池 20 日主力净流入（新浪离线源）")
_AP.add_argument("--date", required=True, help="数据日 YYYY-MM-DD")
_A = _AP.parse_args()
DATE = _A.date
DS = DATE.replace("-", "")
QUANT = os.path.dirname(os.path.abspath(__file__))


def cross_codes(pool_codes):
    """★ 只对「MACD 水上金叉」的候选拉资金流（origin 全市场池 5000+ 只 → 约百余只）。
    依据 macd_build 的判定顺序：先金叉后 flow，故非金叉票的 flow 无意义。
    读不到 tech 时退回全池（保证不静默空转）。"""
    tp = os.path.join(QUANT, f"macd_raw_tech_{DS}.json")
    if not os.path.exists(tp):
        print("[flow] 无 macd_raw_tech_%s.json，退回全池" % DS)
        return pool_codes
    tech = (json.load(open(tp, encoding="utf-8")).get("data") or {})
    out = []
    for c in pool_codes:
        m = ((tech.get(c) or {}).get("macd") or {})
        try:
            if float(m.get("DIF", 0)) > 0 and float(m.get("DEA", 0)) > 0 and float(m.get("MACD", 0)) > 0:
                out.append(c)
        except Exception:
            pass
    print("[flow] 水上金叉 %d / 全池 %d，仅对这些拉资金流" % (len(out), len(pool_codes)))
    return out or pool_codes


def main():
    pool = json.load(open(os.path.join(QUANT, f"macd_raw_pool_{DS}.json"), encoding="utf-8"))
    codes = cross_codes([s["code"] for s in pool["data"]["stocks"]])
    print("[pool] %d 只，走新浪 MoneyFlow" % len(codes))

    fb = sina_batch(codes, workers=10)
    data = {}
    hit = 0
    for c in codes:
        v = fb.get(c) or {}
        mf20 = v.get("mf20")
        mf1 = v.get("mf1")
        if mf20 is None and mf1 is None:
            continue
        data[c] = {"data": [{
            "MainNetFlow20D": int(mf20) if mf20 is not None else 0,
            "MainNetFlow": int(mf1) if mf1 is not None else 0,
            "MainInflowCircRate": 0,
            "MainInflowRank": 0,
        }]}
        hit += 1
    json.dump({"ok": True, "data": data},
              open(os.path.join(QUANT, f"macd_raw_flow_{DS}.json"), "w", encoding="utf-8"),
              ensure_ascii=False)
    print(f"[save] macd_raw_flow_{DS}.json 覆盖 {hit}/{len(codes)}（新浪口径）")


if __name__ == "__main__":
    main()
