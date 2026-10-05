# -*- coding: utf-8 -*-
"""MACD 原始数据抓取（pool / tech / flow 三段）—— 可复用于任意数据日。

背景（2026-10-04）：`macd_build.py` 在原始数据缺失时会静默回退到内嵌的
2026-09-11 快照却顶着新日期写文件，导致 macd_scan_20260918/24/28/29/30
五期逐字节冻结（收盘价反查 35/35 = 09-11）= 旧数据冒充当日。
现已在 `macd_build.py` 改为「缺数据直接报错 + 落盘前冻结自检」，
本脚本负责**把当日的三段原始数据真实抓下来**，让重扫能真正跑通。

本脚本由 `_fetch_macd_2026092X.py` 系列**合并而来**（原来每期新建一个脚本，
正是漏步的温床 —— 现统一成带 `--date` 的一个脚本）。

用法：
  python quant/_fetch_macd_raw.py --date 2026-09-30
  python quant/_fetch_macd_raw.py --date 2026-09-30 --batch-tech 25 --batch-flow 35
  python quant/_fetch_macd_raw.py --date 2026-09-30 --only pool|tech|flow

★ 断点续抓：已存在的 code 会从 tech/flow 里剔除，重跑只补缺的部分。
★ 限频：批间 sleep 由 --gap 控制（默认 12s），限频由共享层 _wsboot 熔断兜底。
"""
import sys, os, json, time, argparse, random

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _wsboot as W

QUANT = os.path.dirname(os.path.abspath(__file__))


def throttled(d):
    if not isinstance(d, dict):
        return False
    t = d.get("_text") or ""
    return ("限频" in t) or ("服务限" in t) or ("rate" in t.lower())


def fetch(tool, args, retries=2):
    """委托共享层 W.fetch：总等待预算封顶 + 同工具连续限频即熔断。"""
    d = W.fetch(tool, args, retry=retries)
    if d is None:
        print("  [skip] %s 失败/限频（共享层预算已兜底）" % tool, flush=True)
    return d


def load_json(name, default=None):
    p = os.path.join(QUANT, name)
    if os.path.exists(p):
        try:
            return json.load(open(p, encoding="utf-8"))
        except Exception:
            return default
    return default


def save(name, d):
    p = os.path.join(QUANT, name)
    json.dump(d, open(p, "w", encoding="utf-8"), ensure_ascii=False)
    print("[save] %s (%d bytes)" % (name, os.path.getsize(p)), flush=True)
    return p


def preflight():
    """取数前体检：westock MCP 通道是否可用。

    2026-10-04 实测：MCP 端点端口可连但 `initialize` 握手稳定返回
    `500 internal_error`（连 initialize 都不通，不是调用姿势问题）→
    此时任何取数都会失败。**必须在开跑前判定并明确报出**，
    否则会表现为「跑了一堆 [skip] 然后什么都没有」，
    或者更糟：下游误以为数据已就绪。
    """
    try:
        import _wsboot as W
    except Exception as ex:
        return False, "_wsboot 不可导入：%s" % ex
    try:
        W.ensure()
        return True, "westock MCP 通道正常"
    except SystemExit as ex:
        return False, ("westock MCP 握手失败：%s\n"
                       "     端点端口可连但 initialize 返回 500 → 后端会话不可用"
                       "（重启 WorkBuddy 应用通常可恢复；或检查 westock-mcp 连接器状态）。\n"
                       "     ★ 不会用旧数据凑数 —— 本脚本直接退出。" % ex)
    except Exception as ex:
        return False, "westock MCP 握手异常：%s" % ex


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True, help="数据日期 YYYY-MM-DD")
    ap.add_argument("--batch-tech", type=int, default=25)
    ap.add_argument("--batch-flow", type=int, default=35)
    ap.add_argument("--gap", type=int, default=12, help="批间基础 sleep 秒")
    ap.add_argument("--limit", type=int, default=200, help="tool_filter limit")
    ap.add_argument("--only", default="", help="只跑某段：pool / tech / flow")
    ap.add_argument("--no-preflight", action="store_true", help="跳过取数前体检")
    a = ap.parse_args()
    DATE = a.date
    DS = DATE.replace("-", "")
    only = set(x for x in a.only.split(",") if x.strip())

    if not a.no_preflight:
        ok, why = preflight()
        print("=== 取数前体检：%s ===" % why.split("\n")[0])
        if not ok:
            raise SystemExit("✗ 拒绝取数：%s" % why)

    # 1) pool —— 全市场主力流入初筛
    f_pool = "macd_raw_pool_%s.json" % DS
    pool = load_json(f_pool)
    if not (only & {"tech", "flow"}) and pool and pool.get("data", {}).get("stocks"):
        print("[1/3] pool: 命中已有文件 %d 只" % len(pool["data"]["stocks"]))
    else:
        print("[1/3] pool: tool_filter main_inflow（min_inflow=0.3亿 market=hs limit=%d）" % a.limit,
              flush=True)
        r = fetch("tool_filter", {"preset": "main_inflow", "min_inflow": 0.3,
                                  "market": "hs", "limit": a.limit})
        if not (r and isinstance(r.get("data"), dict) and r["data"].get("stocks")):
            raise SystemExit("pool fetch failed: %s" % str(r)[:300])
        pool = r
        save(f_pool, pool)
    codes = [s["code"] for s in pool["data"]["stocks"]]
    print("    pool stocks: %d" % len(codes))

    # 2) tech —— MACD/DEA/柱（分批）
    f_tech = "macd_raw_tech_%s.json" % DS
    tech = load_json(f_tech, {}).get("data", {})
    tech = {k: v for k, v in tech.items() if isinstance(v, dict) and "macd" in v}
    if "tech" in only:
        print("[2/3] tech: --only 模式，清空缓存重抓")
        tech = {}
    pending = [c for c in codes if c not in tech]
    print("[2/3] tech: 待抓 %d/%d（已有 %d）" % (len(pending), len(codes), len(tech)), flush=True)
    for i in range(0, len(pending), a.batch_tech):
        b = pending[i:i + a.batch_tech]
        d = fetch("data_technical", {"codes": ",".join(b), "date": DATE, "group": "macd,ma"})
        if d and isinstance(d.get("data"), dict) and not throttled(d):
            for c, v in d["data"].items():
                if isinstance(v, dict) and "macd" in v:
                    tech[c] = v
            print("    tech %d/%d → 累计 %d" % (i // a.batch_tech + 1,
                  (len(pending) + a.batch_tech - 1) // a.batch_tech, len(tech)), flush=True)
        elif d is None:
            print("    [warn] tech 批次 %d 全失败" % (i // a.batch_tech + 1), flush=True)
        else:
            print("    [warn] tech 批次 %d: %s" % (i // a.batch_tech + 1, str(d)[:120]), flush=True)
        time.sleep(a.gap + random.uniform(0, 6))
    save(f_tech, {"ok": True, "date": DATE, "data": tech})
    print("    tech covered: %d / %d" % (len(tech), len(codes)))

    # 3) flow —— MainNetFlow20D（分批）
    f_flow = "macd_raw_flow_%s.json" % DS
    flow = load_json(f_flow, {}).get("data", {})
    flow = {k: v for k, v in flow.items()
            if isinstance(v, dict) and isinstance(v.get("data"), list) and v["data"]}
    if "flow" in only:
        print("[3/3] flow: --only 模式，清空缓存重抓")
        flow = {}
    pending = [c for c in codes if c not in flow]
    print("[3/3] flow: 待抓 %d/%d（已有 %d）" % (len(pending), len(codes), len(flow)), flush=True)
    for i in range(0, len(pending), a.batch_flow):
        b = pending[i:i + a.batch_flow]
        d = fetch("data_fund_flow", {"codes": ",".join(b), "date": DATE})
        if d and isinstance(d.get("data"), dict) and not throttled(d):
            for c, v in d["data"].items():
                if isinstance(v, dict) and isinstance(v.get("data"), list) and v["data"]:
                    flow[c] = v
            print("    flow %d/%d → 累计 %d" % (i // a.batch_flow + 1,
                  (len(pending) + a.batch_flow - 1) // a.batch_flow, len(flow)), flush=True)
        elif d is None:
            print("    [warn] flow 批次 %d 全失败" % (i // a.batch_flow + 1), flush=True)
        else:
            print("    [warn] flow 批次 %d: %s" % (i // a.batch_flow + 1, str(d)[:120]), flush=True)
        time.sleep(a.gap + random.uniform(8, 18))
    save(f_flow, {"ok": True, "date": DATE, "data": flow})
    print("    flow covered: %d / %d" % (len(flow), len(codes)))

    cov_t = len(tech)
    cov_f = len(flow)
    print("""\n=== 取数完成（%s）===
  pool %d 只 ｜ tech %d/%d ｜ flow %d/%d
%s
下一步：python quant/macd_build.py %s --raw""" % (
        DATE, len(codes), cov_t, len(codes), cov_f, len(codes),
        "★ tech/flow 覆盖不足，macd_build.py 会因水上金叉样本太少而出候选很少 —— "
        "这是诚实结果，不补数。" if (cov_t < len(codes) * 0.9 or cov_f < len(codes) * 0.9)
        else "覆盖充分。",
        DS))


if __name__ == "__main__":
    main()
