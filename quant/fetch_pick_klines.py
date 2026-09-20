# -*- coding: utf-8 -*-
"""
个股信号池 · 选股码日K价格档案构建（回填数据源）

问题：build_picks.backfill 只读 quant/picks/quotes_*.json（仅当日候选），
导致只有"连续两日都入选"的票才有 T+1/3/5 回填。本脚本为每只选股码单独拉
日K，建一份逐码×逐日的 OHLC 档案（price_archive.json），使每只票在
被选中后的任意交易日都能用真实后市价结算。

★ 2026-09-20 改造：数据源由 westock-mcp `data_kline` 改为**腾讯离线优先**
   （`_tx_fetch.fetch_kline`，前复权），把这条链彻底移出 MCP 配额；
   腾讯失败/为空时才回退 MCP，回退仍可用 `--src mcp` 强制全走 MCP。
   口径已实证一致：抽样 sh600371 / sh600479 与档案旧值 **101/101 个交易日
   开收盘完全吻合**（前复权锚定最新价），故新旧数据可混存。
   离线通道 8 并发，几十只票秒级完成；不再需要 sleep 限频。

用法：
  python quant/fetch_pick_klines.py --end 2026-09-18
  python quant/fetch_pick_klines.py --end 2026-09-18 --extra sh600519,sz000001
  python quant/fetch_pick_klines.py --end 2026-09-18 --src mcp     # 强制 MCP

产出：
  quant/picks/price_archive.json  = {code: {date: {o,h,l,c}}}

腾讯通道无需沙箱外权限；仅 `--src mcp` 时需要 dangerouslyDisableSandbox。
"""
import os, sys, json, argparse, time
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PICKS = os.path.join(ROOT, "quant", "picks")
HIST = os.path.join(PICKS, "history.json")
ARCHIVE = os.path.join(PICKS, "price_archive.json")
COUNT = 60      # 默认需要的日K根数
KEEP = 120      # 档案统一保留「最近 N 个交易日」窗口（全局对齐，防无界膨胀且各码一致）
WORKERS = 8     # 腾讯离线并发


def load_json(p, default=None):
    if not os.path.exists(p):
        return default
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def collect_codes(end, extra=""):
    codes = set()
    for h in (load_json(HIST, []) or []):
        for tk in ("inst", "youzi"):
            for pk in (h.get(tk) or []):
                if pk.get("code"):
                    codes.add(pk["code"])
    if extra:
        codes.update(c.strip() for c in extra.split(",") if c.strip())
    # 只处理 6 位前缀码（sh/sz/bj + 6 位）
    return sorted(c for c in codes if len(c) >= 8 and c[:2] in ("sh", "sz", "bj"))


def tx_bars(code, count, end):
    """腾讯前复权日K → [{date,o,h,l,c}]，只取 <= end。失败返回 []。"""
    try:
        import _tx_fetch as T
    except Exception:
        return []
    ks = T.fetch_kline(code, max(count, 120))
    return [{"date": k["date"], "o": k["open"], "h": k["high"],
             "l": k["low"], "c": k["last"]}
            for k in ks if k["date"] <= end]


def mcp_bars(code, count, end, W):
    """MCP data_kline → [{date,o,h,l,c}]，只取 <= end。失败返回 []。"""
    r = W.call("data_kline", {"code": code, "end": end, "count": count})
    d = W.unwrap(r)
    nodes = (d or {}).get("data", {}).get("nodes") or []
    out = []
    for n in nodes:
        if n.get("date") and n["date"] <= end:
            out.append({"date": n["date"], "o": n.get("open"), "h": n.get("high"),
                        "l": n.get("low"), "c": n.get("last")})
    return out


def merge(rec, bars):
    """把新 bars 并入 rec（旧值保留；同日期以新值为准）。"""
    for b in bars:
        rec[b["date"]] = {"o": b["o"], "h": b["h"], "l": b["l"], "c": b["c"]}
    return rec


def align_window(archive, keep):
    """全局对齐：所有码统一裁到「最近 keep 个交易日」，保持各码窗口一致。"""
    alld = sorted({d for rec in archive.values() for d in rec.keys()})
    if len(alld) <= keep:
        return 0
    cut = alld[-keep]
    dropped = 0
    for code, rec in list(archive.items()):
        for d in [x for x in rec.keys() if x < cut]:
            rec.pop(d, None)
            dropped += 1
        if not rec:
            archive.pop(code, None)
    return dropped


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--end", required=True, help="日K截止日期 YYYY-MM-DD（最近一个交易日）")
    ap.add_argument("--extra", default="", help="额外码（逗号分隔），如尚未入选也想建档")
    ap.add_argument("--count", type=int, default=COUNT)
    ap.add_argument("--src", choices=["auto", "tx", "mcp"], default="auto",
                    help="auto=腾讯优先·MCP兜底（默认）；tx=只用腾讯；mcp=只用MCP")
    ap.add_argument("--workers", type=int, default=WORKERS)
    ap.add_argument("--keep", type=int, default=KEEP, help="档案统一保留的最近交易日数")
    args = ap.parse_args()

    codes = collect_codes(args.end, args.extra)
    print(f"[fetch_pick_klines] 需建档选股码 {len(codes)} 个，截止 {args.end}，源={args.src}")

    archive = load_json(ARCHIVE, {}) or {}
    todo = [c for c in codes if args.end not in (archive.get(c) or {})]
    print(f"[fetch_pick_klines] 已含截止日 {len(codes) - len(todo)} 个，待补 {len(todo)} 个")

    tx_ok, mcp_ok, fail = [], [], []

    if args.src in ("auto", "tx") and todo:
        t0 = time.time()
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            res = list(ex.map(lambda c: (c, tx_bars(c, args.count, args.end)), todo))
        for c, bars in res:
            if bars:
                merge(archive.setdefault(c, {}), bars)
                tx_ok.append(c)
        print(f"[fetch_pick_klines] 腾讯离线：成功 {len(tx_ok)}/{len(todo)}"
              f"（{time.time() - t0:.1f}s）")

    rest = [c for c in todo if c not in set(tx_ok)]
    if args.src == "tx":
        fail = rest
        rest = []
    if rest:
        try:
            import _wsboot as W
        except Exception as e:
            print("[fetch_pick_klines] 无法加载 _wsmcp，跳过 MCP 兜底：", e)
            fail = rest
            rest = []
        for i, code in enumerate(rest):
            try:
                bars = mcp_bars(code, args.count, args.end, W)
                if bars:
                    merge(archive.setdefault(code, {}), bars)
                    mcp_ok.append(code)
                else:
                    fail.append(code)
            except Exception as e:
                fail.append(code)
                print(f"  ! {code} 失败: {e}")

    dropped = align_window(archive, args.keep)

    with open(ARCHIVE, "w", encoding="utf-8") as f:
        json.dump(archive, f, ensure_ascii=False, indent=1)

    # 覆盖统计
    total_dates = set()
    for rec in archive.values():
        total_dates.update(rec.keys())
    cov = sum(1 for c in codes if c in archive and args.end in archive[c])
    print(f"[fetch_pick_klines] 完成：腾讯 {len(tx_ok)} · MCP兜底 {len(mcp_ok)} ；"
          f"截止日 {args.end} 覆盖 {cov}/{len(codes)}；"
          f"档案含 {len(archive)} 码 / {len(total_dates)} 交易日"
          f"（对齐裁剪 {dropped} 条旧记录）")
    if fail:
        print(f"  失败 {len(fail)}：{fail[:15]}")


if __name__ == "__main__":
    main()
