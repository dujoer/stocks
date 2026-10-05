# -*- coding: utf-8 -*-
"""MACD 池「增强诊断列」数据构建器（自动化版）。

取代 legacy 手抄版 `_build_macd_extra_*.py`：经本地 westock MCP 代理实拉当日数据，
输出 quant/macd_extra_{YYYYMMDD}.json 供 macd_build.py 合并进 macd_scan_*.json。

字段（仅记录与显示，不参与筛选）：
  pos52    52 周分位 = (现价 − 52周低) / (52周高 − 52周低) × 100
  turnover 换手%        vr      量比
  chg1/20/60/Ytd        chg_5d/chg_10d 一并记录
  circMktCapYi 流通市值(亿)   pe/pb
  mf5/mf10/mf20Yi 5/10/20 日主力净额(亿)   mainYi 当日主力(亿)   jumboYi 超大单(亿)
  norm20   20 日主力净额 ÷ 流通市值 × 100
  profitRate 获利盘%    conc90 90%筹码集中度    avgCost 平均成本

用法：
  python3 quant/build_macd_extra.py --date 2026-09-16
  python3 quant/build_macd_extra.py --date 2026-09-16 --codes sh600183,sz002436
"""
from __future__ import annotations
import os, sys, json, time, argparse, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QUANT = os.path.join(ROOT, "quant")
sys.path.insert(0, QUANT)          # 使 import _wsboot / _wsmcp 稳定可用


# ---------- 本地 MCP 代理 JSON-RPC ----------
def _proxy():
    cfg = json.loads(os.environ.get("CODEBUDDY_MCP_CONFIG") or "{}")
    info = (cfg.get("mcpServers") or {}).get("westock-mcp") or {}
    if not info.get("url"):
        # 回退：本机未挂载 westock-mcp 时，读取 _wsmcp_local.json（由 _wsboot 约定）
        local = os.path.join(QUANT, "_wsmcp_local.json")
        if os.path.exists(local):
            info = json.load(open(local, encoding="utf-8"))
    if not info.get("url"):
        raise SystemExit("未找到 westock-mcp 代理配置（CODEBUDDY_MCP_CONFIG / _wsmcp_local.json）")
    return info["url"], dict(info.get("headers", {}))


class MCP:
    """优先走 `_wsboot`（统一入口：**磁盘缓存 + 90s 预算 + 工具级熔断**）。

    2026-09-20 改造：本文件原来自带一套 JSON-RPC 客户端 + 退避循环（retry=4 × sleep=25
    → 单个被限频批次可空等 250s），既享受不到缓存、又和其它脚本的退避叠加。
    现在只要能 import `_wsboot` 就一律委托给它（返回口径完全一致：`data.get("data", data)`），
    仅在 import 失败时退回自带的直连实现。
    """

    def __init__(self):
        self._w = None
        try:
            import _wsboot as _W          # noqa: F401
            self._w = _W
            return
        except Exception:
            pass
        self.url, self.headers = _proxy()

    def _post(self, payload, timeout=180):
        req = urllib.request.Request(
            self.url, data=json.dumps(payload).encode(),
            headers={**self.headers, "Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())

    def init(self):
        if self._w is not None:
            return
        try:
            self._post({"jsonrpc": "2.0", "id": 0, "method": "initialize",
                        "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                                   "clientInfo": {"name": "build_macd_extra", "version": "1"}}}, timeout=60)
            self._post({"jsonrpc": "2.0", "method": "notifications/initialized"}, timeout=30)
        except Exception:
            pass

    def call(self, name, args, timeout=180, retry=4, sleep=25):
        """返回与旧实现同口径的 dict；失败抛 RuntimeError。"""
        if self._w is not None:
            d = self._w.fetch(name, args)
            if d is None:
                raise RuntimeError("%s 失败（限频/熔断，_wsboot）" % name)
            if isinstance(d, dict) and d.get("error"):
                raise RuntimeError("%s 接口报错：%s"
                                   % (name, json.dumps(d["error"], ensure_ascii=False)[:200]))
            return d.get("data", d) if isinstance(d, dict) else d
        last = None
        for i in range(retry):
            try:
                res = self._post({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                  "params": {"name": name, "arguments": args}}, timeout)
            except Exception as e:
                last = "HTTP %s" % e
                time.sleep(sleep)
                continue
            content = res.get("result", {}).get("content") or []
            text = (content[0].get("text", "") or "") if content else ""
            if not text.strip():
                last = "空返回：%s" % json.dumps(res, ensure_ascii=False)[:200]
                time.sleep(sleep)
                continue
            try:
                data = json.loads(text)
            except Exception:
                if "限频" in text or "429" in text:
                    last = "限频：%s" % text[:120]
                    time.sleep(sleep * (i + 1))
                    continue
                last = "非 JSON：%s" % text[:120]
                time.sleep(sleep)
                continue
            if isinstance(data, dict) and data.get("ok") is False:
                last = "接口报错：%s" % json.dumps(data, ensure_ascii=False)[:200]
                time.sleep(sleep)
                continue
            return data.get("data", data)
        raise RuntimeError(f"{name} 连续失败：{last}")


# ---------- 工具 ----------
def _f(v):
    """转 float；字符串/None 容错。"""
    if v is None or v == "":
        return None
    try:
        return float(v)
    except Exception:
        return None


def _yi(v):
    x = _f(v)
    return None if x is None else round(x / 1e8, 4)


def chunks(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


def load_default_codes(date_str):
    p = os.path.join(QUANT, f"macd_scan_{date_str.replace('-', '')}.json")
    if not os.path.exists(p):
        raise SystemExit(f"未找到 macd_scan：{p}")
    d = json.load(open(p, encoding="utf-8"))
    return [s["code"] for s in d.get("stocks", [])]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True, help="交易日 YYYY-MM-DD")
    ap.add_argument("--codes", default="", help="逗号分隔；缺省从 macd_scan_{D}.json 读")
    ap.add_argument("--sleep", type=float, default=8.0)
    # 批大小可调（2026-09-20）：额度宽松时调大可直接减半调用次数；被限频时调小。
    # 注意 _wsmcp 已内置磁盘缓存，同一交易日重复跑不会重复打请求。
    ap.add_argument("--batch-quote", type=int, default=30)
    ap.add_argument("--batch-chip", type=int, default=30)
    ap.add_argument("--batch-flow", type=int, default=20)
    a = ap.parse_args()

    codes = [c.strip() for c in a.codes.split(",") if c.strip()] or load_default_codes(a.date)
    print(f"目标 {len(codes)} 只 @ {a.date}")

    m = MCP()
    m.init()

    quotes, chips, flows = {}, {}, {}
    for batch in chunks(codes, a.batch_quote):
        b = ",".join(batch)
        q = m.call("data_quote", {"codes": b, "date": a.date})
        quotes.update(q if isinstance(q, dict) else {})
        time.sleep(a.sleep)
    for batch in chunks(codes, a.batch_chip):
        c = m.call("data_chip", {"codes": ",".join(batch), "date": a.date})
        chips.update(c if isinstance(c, dict) else {})
        time.sleep(a.sleep)
    for batch in chunks(codes, a.batch_flow):
        f = m.call("data_fund_flow", {"codes": ",".join(batch), "date": a.date})
        flows.update(f if isinstance(f, dict) else {})
        time.sleep(a.sleep)
    print(f"拉取完成 quote={len(quotes)} chip={len(chips)} flow={len(flows)}")

    extra = {}
    missing = []
    for code in codes:
        q = quotes.get(code) or {}
        c = chips.get(code) or {}
        fr = flows.get(code) or {}
        if isinstance(fr, dict) and isinstance(fr.get("data"), list) and fr["data"]:
            fr0 = fr["data"][0]
        else:
            fr0 = fr if isinstance(fr, dict) else {}
        if not q:
            missing.append(code)
            continue
        close = _f(q.get("price"))
        hi, lo = _f(q.get("high_52week")), _f(q.get("low_52week"))
        if close is None or hi is None or lo is None:
            missing.append(code)
            continue
        span = (hi - lo) or 1.0
        cap_yi = _yi(q.get("circulating_market_cap"))
        mf20 = _yi(fr0.get("MainNetFlow20D"))
        d = {
            "code": code, "name": q.get("name") or c.get("name") or fr0.get("name"),
            "close": close,
            "turnover": _f(q.get("turnover_rate")),
            "vr": _f(q.get("volume_ratio")),
            "high52": hi, "low52": lo,
            "chg1": _f(q.get("change_percent")),
            "chg5": _f(q.get("chg_5d")),
            "chg10": _f(q.get("chg_10d")),
            "chg20": _f(q.get("chg_20d")),
            "chg60": _f(q.get("chg_60d")),
            "chgYtd": _f(q.get("chg_ytd")),
            "circMktCapYi": cap_yi,
            "totalMktCapYi": _yi(q.get("total_market_cap")),
            "pe": _f(q.get("pe_ratio")),
            "pb": _f(q.get("pb_ratio")),
            "mf5Yi": _yi(fr0.get("MainNetFlow5D")),
            "mf10Yi": _yi(fr0.get("MainNetFlow10D")),
            "mf20Yi": mf20,
            "mainYi": _yi(fr0.get("MainNetFlow")),
            "jumboYi": _yi(fr0.get("JumboNetFlow")),
            "profitRate": _f(c.get("chipProfitRate")),
            "conc90": _f(c.get("chipConcentration90")),
            "conc70": _f(c.get("chipConcentration70")),
            "avgCost": _f(c.get("chipAvgCost")),
        }
        d["pos52"] = round((close - lo) / span * 100, 1)
        d["norm20"] = round(mf20 / cap_yi * 100, 2) if (mf20 is not None and cap_yi) else None
        extra[code] = d

    out = {
        "data_date": a.date,
        "source": f"westock data_quote + data_chip + data_fund_flow @{a.date} 收盘（quant/build_macd_extra.py 自动拉取）",
        "note": ("增强记录列：**仅用于诊断与显示，不参与筛选、不改变入选结果**。"
                 "pos52=(现价−52周低)/(52周高−52周低)；norm20=20日主力净额÷流通市值×100；"
                 "mf5/10/20Yi=5/10/20日主力净额(亿)；mainYi=当日主力净额(亿)；jumboYi=超大单净额(亿)。"
                 "换手/量比/涨跌幅取自 data_quote 收盘口径（权威）。"),
        "codes": len(extra),
        "extra": extra,
    }
    p = os.path.join(QUANT, f"macd_extra_{a.date.replace('-', '')}.json")
    json.dump(out, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    chk = json.load(open(p, encoding="utf-8"))          # 自校验
    k0 = next(iter(chk["extra"]), None)
    sample = chk["extra"][k0] if k0 else {}
    print(f"写入 {p} | codes {len(chk['extra'])} / {len(codes)}")
    if k0:
        print(f"  抽样 {k0}: pos52={sample.get('pos52')} vr={sample.get('vr')} "
              f"turnover={sample.get('turnover')} norm20={sample.get('norm20')} "
              f"profit={sample.get('profitRate')} conc90={sample.get('conc90')}")
    if missing:
        print(f"  ⚠️ 缺增强数据 {len(missing)} 只：{','.join(missing[:8])}{'…' if len(missing) > 8 else ''}")


if __name__ == "__main__":
    main()
