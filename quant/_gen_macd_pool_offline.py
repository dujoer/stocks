# -*- coding: utf-8 -*-
"""离线生成 MACD 初筛池 macd_raw_pool_{DS}.json（源：腾讯真实日K，本地缓存）。

westock tool_filter 不可用时（502/限频/MCP 断），把全市场正股（剔除 ST/退/基金）作为初筛域，
写入 westock 同构的 pool JSON（data.stocks: code/name/ClosePrice/ChangePCT），
交给 macd_build 按「水上金叉」原逻辑筛选（不在此处重复实现筛选，保证与线上口径一致）。

★ 日期参数化（原写死 2026-09-23 → 每日可跑）。
用法：python3 quant/_gen_macd_pool_offline.py --date 2026-10-09
"""
import os, sys, json, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _tx_fetch as T

_AP = argparse.ArgumentParser(description="离线生成 MACD 初筛池")
_AP.add_argument("--date", required=True, help="数据日 YYYY-MM-DD")
_A = _AP.parse_args()
DATE = _A.date
DS = DATE.replace("-", "")
Q = os.path.dirname(os.path.abspath(__file__))   # quant/ 目录
NAMES = json.load(open(os.path.join(Q, "_stock_names.json"), encoding="utf-8"))


def main():
    c = T._load()
    stocks = []
    for code, bars in c.items():
        if not bars or bars[-1]["date"] != DATE:
            continue
        if code.startswith(("bj", "sh")) and code[2:4] in ("51", "56", "58", "11", "11"):
            pass  # 放行，下面按名称剔 ST/退
        name = NAMES.get(code, "")
        if "ST" in name or "退" in name or "ETF" in name or "基金" in name:
            continue
        last = bars[-1]
        prev = bars[-2]["last"] if len(bars) > 1 else last["last"]
        chg = (last["last"] - prev) / prev * 100 if prev else 0
        stocks.append({
            "code": code,
            "name": name or code,
            "ClosePrice": round(last["last"], 2),
            "ChangePCT": round(chg, 2),
        })
    out = {"src": "offline_txk_full",
           "universe": "全市场正股（离线降级：非 westock 主力净流入 top200 初筛域）",
           "data": {"stocks": stocks, "totalStocks": len(stocks)}}
    dst = os.path.join(Q, f"macd_raw_pool_{DS}.json")
    json.dump(out, open(dst, "w", encoding="utf-8"), ensure_ascii=False)
    print("写完 %s：%d 只正股初筛域" % (dst, len(stocks)))


if __name__ == "__main__":
    main()
