# -*- coding: utf-8 -*-
"""高胜率池 quote 增强提取（离线：腾讯 qt + txk 缓存）。

data_quote 服务端返回空（限频），改用离线腾讯 qt（fetch_qt）覆盖 price/change_percent/
turnover_rate/volume_ratio/high_52week/low_52week，chg_20d/chg_60d 由 txk 末根对齐计算。

结构对齐 build_highwin：_raw_extract/quote_{DS}.json = {"ok":true,"data":{code:{
    "price","change_percent","turnover_rate","volume_ratio","high_52week","low_52week",
    "chg_20d","chg_60d"}}}

用法：python3 quant/_gen_hw_quote_offline.py --date 2026-09-22
"""
import _txk
import sys, os, json, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _tx_fetch as T

HERE = os.path.dirname(os.path.abspath(__file__))
TXK = os.path.join(HERE, "_txk_cache.json")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    a = ap.parse_args()
    D = a.date
    DS = D.replace("-", "")

    pool = json.load(open(os.path.join(HERE, f"macd_raw_pool_{DS}.json"), encoding="utf-8"))
    codes = [s["code"] for s in pool["data"]["stocks"]]
    print("[pool] %d 只，腾讯 qt 离线拉取" % len(codes))

    qt = T.fetch_qt(codes)
    cache = _txk.load()

    def chg_n(code, n):
        bars = cache.get(code)
        if not bars or len(bars) <= n:
            return 0.0
        c0 = float(bars[-1]["last"])
        cn = float(bars[-(n + 1)]["last"])
        return (c0 - cn) / cn * 100 if cn else 0.0

    data = {}
    for c in codes:
        q = qt.get(c) or {}
        last = q.get("last")
        if last is None:
            # 退回 txk 末根
            bars = cache.get(c)
            if bars:
                last = float(bars[-1]["last"])
                chg = chg_n(c, 1)
            else:
                continue
        else:
            chg = q.get("change_percent") or chg_n(c, 1)
        data[c] = {
            "price": float(last),
            "change_percent": float(chg),
            "turnover_rate": float(q.get("turnover_rate") or 0),
            "volume_ratio": float(q.get("volume_ratio") or 0),
            "high_52week": float(q.get("high_52week") or 0),
            "low_52week": float(q.get("low_52week") or 0),
            "chg_20d": round(chg_n(c, 20), 2),
            "chg_60d": round(chg_n(c, 60), 2),
        }
    json.dump({"ok": True, "data": data},
              open(os.path.join(HERE, "_raw_extract", f"quote_{DS}.json"), "w", encoding="utf-8"),
              ensure_ascii=False)
    print(f"[save] _raw_extract/quote_{DS}.json 覆盖 {len(data)}/{len(codes)}")


if __name__ == "__main__":
    main()
