# -*- coding: utf-8 -*-
"""底部反转观察池 · 数据补全（名称 / 流通市值 / PE / 20 日主力净流入）。

背景（v5）：观察池的候选来自**全市场深跌域**（rev_pool.py 先验固定因子集横截面分位），
候选清单只带 code / 名称 / 组合分，不含流通市值与资金流；页面会出现
「名称显示成代码 / 流通与 20 日主力一片空白」。本脚本负责把这些补全并回写。
（旧版候选来自「净利同比>50 & 0<PE<50 & 总市值<100亿」的条件选股种子，该路径已废。）

数据源分工（都不占 MCP 额度 → 可以每天跑）：
  · 名称 / 流通市值 / PE / PB / 换手  → 腾讯离线快照（qt.gtimg.cn，80 只/请求）
  · 20 日主力净流入                    → 新浪离线 MoneyFlow（由 fetch_rev_flow.py 落盘为
                                        quant/_rev_flow_raw_{dc}.json，本脚本负责合并）

用法：
  python quant/fetch_rev_enrich.py --date 2026-09-18
  python quant/fetch_rev_enrich.py --date 2026-09-18 --no-quote      # 只合并已落盘的 flow
  python quant/fetch_rev_enrich.py --date 2026-09-18 --render        # 合并后顺带重渲染页面
  python quant/fetch_rev_enrich.py --date 2026-09-18 --flow /tmp/f.json

产出：quant/rev_enrich_{dc}.json
  {"data_date": "...", "quote": {code: {...}}, "flow": {code: {...}}, "n": ...}
"""
import os
import sys
import json
import argparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _tx_fetch as T

ROOT = os.path.dirname(HERE)
QUANT = HERE


def dc_of(date):
    return str(date).replace("-", "")


def _fnum(v):
    try:
        if v is None or v == "":
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def candidate_codes(date):
    """从当日的反转扫描里取候选代码（带前缀）。"""
    p = os.path.join(QUANT, "watchlist_scan_%s.json" % dc_of(date))
    if not os.path.exists(p):
        return []
    try:
        j = json.load(open(p, encoding="utf-8"))
    except Exception:
        return []
    out = []
    for c in j.get("candidates") or []:
        code = c.get("_full") or c.get("code")
        if code:
            out.append(code if code[:2] in ("sh", "sz", "bj") else "sz" + code)
    return out


def load_flow_raw(date, path=None):
    """读取 agent 落盘的 MCP data_fund_flow 原始结果，归一化为 {code: {...}}。"""
    cands = [path,
             os.path.join(QUANT, "_rev_flow_raw_%s.json" % dc_of(date)),
             os.path.join(QUANT, "rev_flow_%s.json" % date),
             os.path.join(QUANT, "_rev_flow_all_%s.json" % dc_of(date))]
    raw = None
    used = None
    for p in cands:
        if p and os.path.exists(p):
            try:
                raw = json.load(open(p, encoding="utf-8"))
                used = p
                break
            except Exception:
                continue
    if raw is None:
        return {}, None

    data = raw.get("data") if isinstance(raw, dict) and "data" in raw else raw
    src = raw.get("src") if isinstance(raw, dict) else None
    out = {}
    if isinstance(data, dict):
        for k, v in data.items():
            # ① 已归一化（fetch_rev_flow.py 产物：直接带 mf1/mf5/mf10/mf20）
            if isinstance(v, dict) and ("mf20" in v or "mf1" in v):
                code = str(v.get("code") or k).lower()
                if code[:2] not in ("sh", "sz", "bj"):
                    continue
                rec = dict(v)
                rec.setdefault("src", src)
                out[code] = rec
                continue
            # ② 原始 MCP data_fund_flow（data 为 list）
            rec = None
            if isinstance(v, dict):
                rec = (v.get("data") or [None])[0] if isinstance(v.get("data"), list) else v
            elif isinstance(v, list):
                rec = v[0] if v else None
            if not isinstance(rec, dict):
                continue
            code = rec.get("code") or rec.get("SecuCode") or k
            code = str(code).lower()
            if code[:2] not in ("sh", "sz", "bj"):
                continue
            out[code] = {
                "date": rec.get("EndDate"),
                "name": rec.get("name"),
                "mf1": _fnum(rec.get("MainNetFlow")),
                "mf5": _fnum(rec.get("MainNetFlow5D")),
                "mf10": _fnum(rec.get("MainNetFlow10D")),
                "mf20": _fnum(rec.get("MainNetFlow20D")),
                "rank": _fnum(rec.get("MainInflowRank")),
                "circ_rate": _fnum(rec.get("MainInflowCircRate")),
                "src": src,
            }
    return out, used


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="2026-09-18")
    ap.add_argument("--flow", help="外部 flow 文件（默认自动找 _rev_flow_raw_{dc}.json）")
    ap.add_argument("--no-quote", action="store_true", help="跳过腾讯快照（只用已有 flow）")
    ap.add_argument("--render", action="store_true",
                    help="补数后顺带重渲染反转页（等价于再跑 rev_pool.py render）")
    a = ap.parse_args()

    dc = dc_of(a.date)
    codes = candidate_codes(a.date)
    print("[rev_enrich] %s 候选 %d 只" % (a.date, len(codes)))

    out = {"data_date": a.date, "quote": {}, "flow": {}, "n": len(codes)}

    if not a.no_quote and codes:
        q = T.fetch_qt(codes, batch=80)
        for c in codes:
            v = q.get(c)
            if not v:
                continue
            out["quote"][c] = {
                "name": v.get("name"),
                "circ_mv": v.get("circulating_market_cap"),     # 亿元
                "pe": v.get("pe_ratio"),
                "pb": v.get("pb_ratio"),
                "turn": v.get("turnover_rate"),
                "last": v.get("last"),
                "h52": v.get("high_52week"),
            }
        print("[rev_enrich] 腾讯快照命中 %d / %d" % (len(out["quote"]), len(codes)))

    flow, used = load_flow_raw(a.date, a.flow)
    if flow:
        miss = [c for c in codes if c not in flow]
        out["flow"] = flow
        out["flow_file"] = os.path.basename(used) if used else "?"
        srcs = sorted({v.get("src") for v in flow.values() if v.get("src")})
        out["flow_src"] = ("mixed" if len(srcs) > 1 else (srcs[0] if srcs else "unknown"))
        print("[rev_enrich] 资金流命中 %d（口径 %s，源文件 %s）；候选内缺 %d"
              % (len(flow), out["flow_src"], out["flow_file"], len(miss)))
    else:
        print("[rev_enrich] ⚠ 未找到资金流原始文件，20 日主力将显示为空")

    p = os.path.join(QUANT, "rev_enrich_%s.json" % dc)
    json.dump(out, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("[rev_enrich] → %s" % p)

    if a.render:
        import rev_pool
        rev_pool.render_only(a.date)


if __name__ == "__main__":
    main()
