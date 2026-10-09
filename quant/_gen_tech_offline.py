# -*- coding: utf-8 -*-
"""离线技术指标准备（绕开 westock data_technical / data_chip 服务端限频）。

数据源：quant/_txk_cache.json（腾讯前复权日K，与 MCP data_kline 口径一致，5045 只）。
计算：MACD(12,26,9) · MA5/10/20/60/120 · RSI(12, Wilder) —— 全部为收盘价的确定性函数。

产出（三种消费格式，结构对齐原 westock 返回，便于各 build 脚本无改动复用）：
  1) macd_raw_tech_{DS}.json        = {"ok":true,"data":{code:{"macd":{"DIF":, "DEA":, "MACD":}}}}
                                       供 macd_build.build_from_raw 消费（MACD 池）
  2) technical_{DATE}.json          = {code:{"ma5":,"ma10":,"ma20":,"ma60":,"rsi12":}}
                                       供 build_picks 消费（Gate + 量价打分）
  3) _raw_extract/tech_{DS}.json    = {"ok":true,"data":{code:{"ma":{"MA_5".."MA_120"},
                                                                  "rsi":{"RSI_12":}}}}
                                       供 build_highwin 消费（趋势/位置维度）

同时把 macd_raw_pool_{DS}.json 的候选补全 ClosePrice/ChangePCT（09-22 池抓取时丢失，
        westock 返回结构缺字段），从 txk 末根对齐，macd_build 才能读到显示的收盘价/涨跌幅。

用法：python3 quant/_gen_tech_offline.py --date 2026-09-22
"""
import _txk
import os, sys, json, argparse

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
Q = HERE
TXK = os.path.join(Q, "_txk_cache.json")


def sma(vals, n):
    if len(vals) < n:
        return None
    return sum(vals[-n:]) / n


def ema_series(vals, n):
    """返回与 vals 等长的 EMA 序列（seed = 首值）。"""
    out = []
    k = 2.0 / (n + 1)
    prev = vals[0]
    for i, v in enumerate(vals):
        if i == 0:
            prev = v
        else:
            prev = v * k + prev * (1 - k)
        out.append(prev)
    return out


def rsi_wilder(vals, n=12):
    if len(vals) < n + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(vals)):
        d = vals[i] - vals[i - 1]
        gains.append(max(d, 0.0))
        losses.append(max(-d, 0.0))
    ag = sum(gains[:n]) / n
    al = sum(losses[:n]) / n
    for i in range(n, len(gains)):
        ag = (ag * (n - 1) + gains[i]) / n
        al = (al * (n - 1) + losses[i]) / n
    if al == 0:
        return 100.0
    rs = ag / al
    return 100.0 - 100.0 / (1.0 + rs)


def macd_pair(close):
    if len(close) < 26:
        return None, None, None
    e12 = ema_series(close, 12)
    e26 = ema_series(close, 26)
    dif = [e12[i] - e26[i] for i in range(len(close))]
    dea = ema_series(dif, 9)
    bar = [2.0 * (dif[i] - dea[i]) for i in range(len(close))]
    return dif[-1], dea[-1], bar[-1]


def load_cache():
    return _txk.load()


def series_for(cache, code):
    bars = cache.get(code)
    if not bars:
        return None
    out = []
    for b in bars:
        c = b.get("last")
        if c is None:
            continue
        out.append(float(c))
    return out if out else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    a = ap.parse_args()
    D = a.date
    DS = D.replace("-", "")

    cache = load_cache()
    print("[txk] 缓存 %d 只" % len(cache))

    def close_at(code):
        """返回 (close, changePCT) 对齐到目标日期末根。"""
        bars = cache.get(code)
        if not bars:
            return None, None
        # 取目标日期当根；缺失则用末根（缓存已截至 09-22）
        target = None
        for b in bars:
            if b.get("date") == D:
                target = b
                break
        if target is None:
            target = bars[-1]
        idx = bars.index(target)
        close = float(target["last"])
        if idx > 0:
            prev = float(bars[idx - 1]["last"])
            chg = (close - prev) / prev * 100 if prev else 0.0
        else:
            chg = 0.0
        return close, chg

    # ---- 收集需要计算的目标码 ----
    want = set()
    pool_codes = []
    pool_p = os.path.join(Q, f"macd_raw_pool_{DS}.json")
    if os.path.exists(pool_p):
        pool = json.load(open(pool_p, encoding="utf-8"))
        for s in pool["data"]["stocks"]:
            pool_codes.append(s["code"])
            want.add(s["code"])
    cand_codes = []
    cand_p = os.path.join(Q, "picks", f"candidates_{D}.json")
    if os.path.exists(cand_p):
        cand = json.load(open(cand_p, encoding="utf-8"))
        rows = cand.get("candidates") if isinstance(cand, dict) else cand
        for r in rows:
            c = r.get("code")
            if c:
                cand_codes.append(c)
                want.add(c)
    print("[want] pool=%d cand=%d union=%d" % (len(pool_codes), len(cand_codes), len(want)))

    # ---- 计算 ----
    tech_macd = {}     # code -> {DIF,DEA,MACD}
    tech_picks = {}    # code -> {ma5,ma10,ma20,ma60,rsi12}
    tech_hw = {}       # code -> {ma:{...}, rsi:{RSI_12}}
    miss = 0
    for code in want:
        close = series_for(cache, code)
        if not close or len(close) < 120:
            miss += 1
            continue
        dif, dea, bar = macd_pair(close)
        if dif is not None:
            tech_macd[code] = {"macd": {"DIF": round(dif, 4), "DEA": round(dea, 4), "MACD": round(bar, 4)}}
        ma = {n: sma(close, n) for n in (5, 10, 20, 60, 120)}
        rsi = rsi_wilder(close, 12)
        tech_picks[code] = {
            "ma5": round(ma[5], 3) if ma[5] else None,
            "ma10": round(ma[10], 3) if ma[10] else None,
            "ma20": round(ma[20], 3) if ma[20] else None,
            "ma60": round(ma[60], 3) if ma[60] else None,
            "rsi12": round(rsi, 2) if rsi is not None else None,
        }
        tech_hw[code] = {
            "ma": {f"MA_{n}": round(ma[n], 3) for n in (5, 10, 20, 60, 120) if ma[n]},
            "rsi": {"RSI_12": round(rsi, 2)} if rsi is not None else {},
        }
    print("[calc] 覆盖 %d / 缺 %d" % (len(tech_macd), miss))

    # ---- 1) macd_raw_tech ----
    if pool_codes:
        json.dump({"ok": True, "data": tech_macd},
                  open(os.path.join(Q, f"macd_raw_tech_{DS}.json"), "w", encoding="utf-8"),
                  ensure_ascii=False)
        print("[write] macd_raw_tech_%s.json (%d 只)" % (DS, len(tech_macd)))

    # ---- 2) technical_{DATE}.json（精选池） ----
    json.dump({c: tech_picks[c] for c in cand_codes if c in tech_picks},
              open(os.path.join(Q, "picks", f"technical_{D}.json"), "w", encoding="utf-8"),
              ensure_ascii=False)
    print("[write] picks/technical_%s.json (%d 只)" % (D, sum(1 for c in cand_codes if c in tech_picks)))

    # ---- 3) _raw_extract/tech_{DS}.json（高胜率） ----
    os.makedirs(os.path.join(Q, "_raw_extract"), exist_ok=True)
    json.dump({"ok": True, "data": tech_hw},
              open(os.path.join(Q, "_raw_extract", f"tech_{DS}.json"), "w", encoding="utf-8"),
              ensure_ascii=False)
    print("[write] _raw_extract/tech_%s.json (%d 只)" % (DS, len(tech_hw)))

    # ---- 补全 pool ClosePrice/ChangePCT ----
    if pool_codes:
        pool = json.load(open(pool_p, encoding="utf-8"))
        filled = 0
        for s in pool["data"]["stocks"]:
            if "ClosePrice" not in s or "ChangePCT" not in s:
                c, chg = close_at(s["code"])
                if c is not None:
                    s["ClosePrice"] = round(c, 3)
                    s["ChangePCT"] = round(chg, 3)
                    filled += 1
        json.dump(pool, open(pool_p, "w", encoding="utf-8"), ensure_ascii=False)
        print("[patch] macd_raw_pool_%s.json 补全 %d 只收盘价/涨跌幅" % (DS, filled))


if __name__ == "__main__":
    main()
