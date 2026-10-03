# -*- coding: utf-8 -*-
"""
统一数据底座（_datahub.py）
==========================
用户 2026-10-03 要求：「优化数据获取和计算，最好可以每天整体获取需要的数据，
然后给各模块使用」。

现状问题（实测统计）
--------------------
- `quant/` 下 **23 个** `*_fetch_*.py / fetch_*.py` 抓数脚本，各模块各抓各的。
- 同一份数据被多个脚本重复抓取：**quotes 18 个脚本引用、fundflow 9 个、
  margin_em 8 个、_raw_extract 12 个、exec_chg 21 个、block_chg 18 个**。
- 后果：① 重复请求 → 触发限频（腾讯连发 60 次即被限流，且**返回 200 + 合法 JSON
  但只有 1 根当日数据**，静默污染缓存）② 同一数据不同源口径可能不一致
  ③ 各模块各自判断降级，页面口径互相矛盾。

设计
----
**一次抓取 → 落 `quant/hub/{DATE}.json` → 各模块只读不抓。**

```
                    ┌─────────────┐
   离线真实源 ─────→│  _datahub   │────→ hub/{DATE}.json（全量 + 来源元数据）
   （腾讯/新浪/东财）│  每日一次   │────→ hub/manifest.json（当日覆盖率与降级说明）
                    └─────────────┘
                              ↓ 只读
        各模块（主升/反转/做T/增仓/精选池/三连阴/冷门/量化策略…）
```

纪律
----
1. **来源可追**：每个维度记录 `src`（mcp / 腾讯 / 新浪 / 东财 / 缓存）与 `ok`。
2. **缺维度诚实降级**：`ok=False` 时写 `reason`，页面据此标注，**绝不用旧数据冒充当日**。
3. **离线优先**：能用离线源的维度绝不联网（见 `--offline`）。
4. **可增量补抓**：单个维度失败可 `--only dim` 重补，不必重跑全部。
5. **各模块兼容**：不改任何模块代码也能用（底座只是新增的数据来源）。

用法
----
    python _datahub.py --date 2026-09-30            # 全维度
    python _datahub.py --date 2026-09-30 --list     # 看有哪些维度
    python _datahub.py --date 2026-09-30 --only quotes,fundflow
    python _datahub.py --date 2026-09-30 --offline  # 只用离线源，不联网
    python _datahub.py --date 2026-09-30 --force   # 忽略当日已有缓存
"""
from __future__ import annotations
import os, sys, json, time, argparse, datetime, traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

ROOT = os.path.dirname(HERE)
HUB = os.path.join(HERE, "hub")
os.makedirs(HUB, exist_ok=True)

DS = lambda d: d.replace("-", "")          # noqa: E731


# ============================================================
# 维度登记表：加新维度只在这里加一条
# ============================================================
DIMS = [
    ("quotes",  "全市场行情快照（现价/涨跌幅/换手/市值）", "腾讯 qt 快照（离线优先，westock 兜底）"),
    ("flow",    "主力资金流 1/5/10/20 日",                 "新浪 MoneyFlow 批量（离线，不限频）"),
    ("margin",  "融资融券日频序列（每股 30 根）",           "东财 datacenter-web（离线通道）"),
    ("lhb",     "龙虎榜全量 + 席位明细",                     "东财 datacenter（离线）/ westock 兜底"),
    ("block",   "大宗交易 30 日窗口",                        "东财 datacenter（离线）"),
    ("exec",    "高管增减持（变动日口径）",                  "东财 datacenter（离线）"),
    ("sector",  "板块快照（行业 ranking + 概念）",            "东财 datacenter（离线）"),
    ("kline",   "日K 增量（长历史底座补最新）",              "腾讯 fqkline（离线优先）"),
]
DIM_CN = {k: cn for k, _d, cn in DIMS}
DIM_ORDER = [k for k, _d, _c in DIMS]


def hub_path(date):
    return os.path.join(HUB, "%s.json" % DS(date))


def manifest_path():
    return os.path.join(HUB, "manifest.json")


# ============================================================
# 工具
# ============================================================
def load_hub(date):
    p = hub_path(date)
    if not os.path.exists(p):
        return {}
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return {}


def save_hub(date, d):
    tmp = hub_path(date) + ".tmp"
    json.dump(d, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    os.replace(tmp, hub_path(date))


def _stock_pool():
    """全市场票池（代码 → 名称）。优先 _stock_names.json，缺失退回日K 缓存。"""
    names = {}
    p = os.path.join(HERE, "_stock_names.json")
    if os.path.exists(p):
        try:
            names = json.load(open(p, encoding="utf-8"))
        except Exception:
            names = {}
    if not names:
        try:
            k = json.load(open(os.path.join(HERE, "_txk_cache.json"), encoding="utf-8"))
            names = {c: (v[-1].get("name") or c) if v else c for c, v in k.items()}
        except Exception:
            pass
    return {c: n for c, n in names.items() if isinstance(c, str) and c[:2] in ("sh", "sz", "bj")}


def _all_codes():
    """全市场代码（用于行情/资金流批量）。腾讯对 bj92* 不支持，需排除。"""
    def ok(c):
        return c[:2] in ("sh", "sz") or (c.startswith("bj") and not c.startswith("bj92"))
    return sorted(c for c in _stock_pool() if ok(c))


# ============================================================
# 各维度抓取
# ============================================================
def dim_quotes(date, ctx, offline=True):
    """全市场行情快照。

    ⚠ **覆盖口径必须说清**：当日 `quotes/{DATE}.json` 只覆盖「事件域」
    （龙虎榜 + 大宗 + 增减持的并集，典型 400~600 只），**不是全市场 5207 只**。
    名称叫「全市场」会误导 → 页面与 manifest 均如实标注实际条数。
    缺全市场快照时走腾讯批量补齐（限频风险，见 _fetch_long_kline 的教训）。
    """
    out = {"src": "", "ok": False, "reason": "", "data": {}, "scope": "", "n": 0}
    p = os.path.join(HERE, "quotes", "%s.json" % date)
    if os.path.exists(p):
        try:
            j = json.load(open(p, encoding="utf-8"))
            d = (j.get("data") or j)
            if isinstance(d, dict) and d:
                out.update(src="quotes缓存", ok=True, data=d,
                           scope="事件域（龙虎榜+大宗+增减持并集）", n=len(d))
                return out
        except Exception:
            pass
    if offline:
        out["reason"] = "离线模式且当日 quotes 缓存缺失"
        return out
    try:
        import _tx_fetch as T
        codes = _all_codes()
        got = {}
        B, GAP = 80, 0.12
        for i in range(0, len(codes), B):
            grp = codes[i:i + B]
            try:
                got.update(T.fetch_qt(grp) or {})
            except Exception:
                pass
            time.sleep(GAP)
        if got:
            out.update(src="腾讯qt", ok=True, data=got, scope="全市场", n=len(got))
        else:
            out["reason"] = "腾讯快照全失败"
    except Exception as e:
        out["reason"] = "异常：%s" % str(e)[:80]
    return out


def _event_codes(date):
    """当日事件域代码并集（龙虎榜 + 大宗 + 增减持 + 精选池）。

    ★资金流/行情这类「按票请求」的维度**只能按事件域取**，不能按代码序截前 N ——
    那样会系统性偏向小代码段（深市主板），造成选择偏差。
    """
    codes = set()
    # lhb
    p = os.path.join(HERE, "lhb", "%s.json" % date)
    if os.path.exists(p):
        try:
            data = (json.load(open(p, encoding="utf-8")).get("data") or {})
            for t in ("all", "jg", "yyb", "gslmr", "gslxw"):
                for it in (data.get(t) or []):
                    c = it.get("code") or it.get("stock_code")
                    if c:
                        codes.add(c)
        except Exception:
            pass
    # block
    p = os.path.join(HERE, "block_chg", "%s.json" % date)
    if os.path.exists(p):
        try:
            for s in (json.load(open(p, encoding="utf-8")).get("byStock") or []):
                if s.get("code"):
                    codes.add(s["code"])
        except Exception:
            pass
    # exec
    p = os.path.join(HERE, "exec_chg", "%s.json" % date)
    if os.path.exists(p):
        try:
            for r in (json.load(open(p, encoding="utf-8")).get("records") or []):
                if r.get("code"):
                    codes.add(r["code"])
        except Exception:
            pass
    # 精选池当日（信号池覆盖到的票）
    p = os.path.join(HERE, "picks", "quotes_%s.json" % date)
    if os.path.exists(p):
        try:
            d = json.load(open(p, encoding="utf-8"))
            if isinstance(d, dict):
                codes.update(d.keys())
        except Exception:
            pass
    def _ok(c):
        return c and (c[:2] in ("sh", "sz") or (c.startswith("bj") and not c.startswith("bj92")))
    return sorted(c for c in codes if _ok(c))


def dim_flow(date, ctx, offline=True):
    """主力资金流 1/5/10/20 日。走新浪批量（离线通道，不受 MCP 限频）。

    ★ 覆盖 = **当日事件域**（非全市场）。新浪是每股一次请求，全市场 5207 只
    约需 20+ 分钟且极易限流；各池子实际只需要事件域的票。
    """
    out = {"src": "", "ok": False, "reason": "", "data": {}, "scope": "", "n": 0}
    try:
        import fetch_rev_flow as FR
        fn = getattr(FR, "sina_batch", None)
        if fn is None:
            out["reason"] = "fetch_rev_flow 无 sina_batch"
            return out
        codes = _event_codes(date)
        if not codes:
            out["reason"] = "当日事件域为空（lhb/block/exec 均缺）"
            return out
        lim = ctx.get("flow_limit", 0)
        if lim and len(codes) > lim:
            codes = codes[:lim]
        got = fn(codes)
        if got:
            out.update(src="新浪MoneyFlow", ok=True, data=got,
                       scope="当日事件域", n=len(got))
        else:
            out["reason"] = "新浪资金流全失败（%d 只）" % len(codes)
    except Exception as e:
        out["reason"] = "异常：%s" % str(e)[:80]
    return out


def dim_margin(date, ctx, offline=True):
    """融资融券日频序列。复用已有 margin_em/{code}.json（不重复抓）。"""
    out = {"src": "", "ok": False, "reason": "", "n": 0}
    d = os.path.join(HERE, "margin_em")
    if not os.path.isdir(d):
        out["reason"] = "margin_em 目录不存在（需先跑 _fetch_margin_em.py）"
        return out
    import glob
    n = 0
    last = ""
    for f in glob.glob(os.path.join(d, "*.json")):
        try:
            rows = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        if rows:
            n += 1
            last = max(last, rows[-1].get("date") or "")
    if n:
        out.update(src="margin_em缓存", ok=True, n=n, last=last)
    else:
        out["reason"] = "margin_em 为空"
    return out


def dim_lhb(date, ctx, offline=True):
    """龙虎榜：优先当日 lhb/{DATE}.json 缓存。"""
    out = {"src": "", "ok": False, "reason": "", "n": 0}
    d = os.path.join(HERE, "lhb")
    p = os.path.join(d, "%s.json" % date)
    if os.path.exists(p):
        try:
            j = json.load(open(p, encoding="utf-8"))
            data = j.get("data") or {}
            n = 0
            for t in ("all", "jg", "yyb", "gslmr", "gslxw"):
                v = data.get(t)
                if isinstance(v, list):
                    n += len(v)
            out.update(src="lhb缓存", ok=True, n=n)
        except Exception as e:
            out["reason"] = "解析失败：%s" % str(e)[:60]
    else:
        out["reason"] = "当日 lhb/%s.json 缺失" % date
    return out


def dim_block(date, ctx, offline=True):
    out = {"src": "", "ok": False, "reason": "", "n": 0}
    p = os.path.join(HERE, "block_chg", "%s.json" % date)
    if os.path.exists(p):
        try:
            j = json.load(open(p, encoding="utf-8"))
            n = len(j.get("byStock") or [])
            out.update(src="block_chg缓存", ok=True, n=n)
        except Exception as e:
            out["reason"] = "解析失败：%s" % str(e)[:60]
    else:
        out["reason"] = "当日 block_chg 缺失"
    return out


def dim_exec(date, ctx, offline=True):
    out = {"src": "", "ok": False, "reason": "", "n": 0}
    p = os.path.join(HERE, "exec_chg", "%s.json" % date)
    if os.path.exists(p):
        try:
            j = json.load(open(p, encoding="utf-8"))
            n = len(j.get("records") or [])
            out.update(src="exec_chg缓存", ok=True, n=n)
        except Exception as e:
            out["reason"] = "解析失败：%s" % str(e)[:60]
    else:
        out["reason"] = "当日 exec_chg 缺失"
    return out


def dim_sector(date, ctx, offline=True):
    out = {"src": "", "ok": False, "reason": "", "n": 0}
    got = {}
    for kind in ("industry", "concept"):
        p = os.path.join(HERE, "sector_%s_%s.json" % (kind, DS(date)))
        if os.path.exists(p):
            try:
                j = json.load(open(p, encoding="utf-8"))
                got[kind] = len(((j.get("data") or {}).get("rows")) or [])
            except Exception:
                pass
    if got:
        out.update(src="sector缓存", ok=True, n=got)
    else:
        out["reason"] = "当日 sector 快照缺失"
    return out


def dim_kline(date, ctx, offline=True):
    """长历史底座的最新一根是否已到位（不联网，只做一致性检查）。"""
    out = {"src": "", "ok": False, "reason": "", "n": 0, "last": ""}
    p = os.path.join(HERE, "_long_kline.json")
    if not os.path.exists(p):
        p = os.path.join(HERE, "_txk_cache.json")
        out["src"] = "_txk_cache"
    else:
        out["src"] = "_long_kline"
    try:
        k = json.load(open(p, encoding="utf-8"))
        n = len(k)
        last = ""
        for v in k.values():
            if v and (v[-1].get("date") or "") > last:
                last = v[-1]["date"]
        out.update(ok=True, n=n, last=last)
    except Exception as e:
        out["reason"] = "读取失败：%s" % str(e)[:60]
    return out


FETCHERS = {
    "quotes": dim_quotes, "flow": dim_flow, "margin": dim_margin,
    "lhb": dim_lhb, "block": dim_block, "exec": dim_exec,
    "sector": dim_sector, "kline": dim_kline,
}


# ============================================================
# 主流程
# ============================================================
def run(date, only=None, offline=True, force=False, flow_limit=1200):
    prev = load_hub(date)
    # ⚠ 语义严格区分：
    #   --only X  → **增量补抓**（--force 也只重抓 X，其余维度保留）
    #   --force   → 全量重抓（无 --only 时才清空）
    #   否则「补一个维度」会把已好的 7 个维度全弄丢。
    if force and only:
        dims = dict(prev.get("dims", {}))
    elif force:
        dims = {}
    else:
        dims = dict(prev.get("dims", {}))
    hub = {
        "date": date,
        "built_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "dims": dims,
    }
    codes = _all_codes()
    ctx = {"codes": codes, "flow_limit": flow_limit}
    todo = [d for d in DIM_ORDER if (only is None or d in only)]

    print("[底座] %s｜维度 %d/%d｜票池 %d 只｜%s"
          % (date, len(todo), len(DIM_ORDER), len(codes),
             "离线模式" if offline else "允许联网"))
    for d in todo:
        old = hub["dims"].get(d)
        if old and old.get("ok") and not force:
            print("  %-8s ✓ 已有可用数据（src=%s）跳过" % (d, old.get("src")))
            continue
        t0 = time.time()
        try:
            r = FETCHERS[d](date, ctx, offline=offline)
        except Exception as e:
            r = {"src": "", "ok": False, "reason": "未捕获异常：%s" % str(e)[:80]}
        r["elapsed"] = round(time.time() - t0, 2)
        hub["dims"][d] = r
        mark = "✓" if r.get("ok") else "✗"
        extra = ""
        if not r.get("ok"):
            extra = "  ← %s" % r.get("reason", "")
        elif r.get("n") is not None:
            extra = "  n=%s" % (r["n"] if not isinstance(r["n"], dict) else sum(r["n"].values()))
        print("  %-8s %s src=%-14s %5.1fs%s" % (d, mark, r.get("src") or "-",
                                                 r["elapsed"], extra))
    save_hub(date, hub)

    # manifest（当日汇总，供门户/门禁读取）
    # ⚠ 用 .get(d, {})：--only/--force 下部分维度可能本轮没跑，不能 KeyError。
    D = lambda k: hub["dims"].get(k) or {}          # noqa: E731
    ok_dims = [d for d in DIM_ORDER if D(d).get("ok")]
    bad_dims = [d for d in DIM_ORDER if not D(d).get("ok")]
    mf = {
        "date": date, "built_at": hub["built_at"],
        "ok_dims": ok_dims, "bad_dims": bad_dims,
        "coverage": "%d/%d" % (len(ok_dims), len(DIM_ORDER)),
        "reasons": {d: D(d).get("reason", "本轮未抓取") for d in bad_dims},
        "sources": {d: D(d).get("src", "") for d in DIM_ORDER if d in hub["dims"]},
        # ★ 覆盖口径必须落盘：quotes/flow 只是「事件域」不是全市场，
        #   不写清楚会让页面误以为覆盖了 5207 只。
        "scopes": {d: D(d).get("scope", "") for d in DIM_ORDER},
        "counts": {d: D(d).get("n") for d in DIM_ORDER
                   if isinstance(D(d).get("n"), int)},
    }
    json.dump(mf, open(manifest_path(), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("\n[底座] 覆盖 %s｜缺失 %s" % (mf["coverage"],
                                       "、".join(bad_dims) or "无"))
    print("[口径] " + "；".join("%s=%s(%s)" % (d, mf["counts"].get(d) or "-",
                                          mf["scopes"].get(d) or "-")
                               for d in DIM_ORDER if d in hub["dims"]))
    if bad_dims:
        for d in bad_dims:
            print("   ✗ %-8s %s" % (d, D(d).get("reason", "")))
    print("[产物] %s ｜ %s" % (hub_path(date), manifest_path()))
    return hub


def get(date, dim):
    """供各模块调用：读底座某维度。返回 dict（含 ok/src/data），缺失返回 None。

    ⚠ 这是给模块用的**唯一入口**：模块应优先 `hub_get(date,'quotes')`，
      取不到再退回自己的历史路径（保持向后兼容）。
    """
    h = load_hub(date)
    return (h.get("dims") or {}).get(dim)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--only", default="", help="逗号分隔的维度名；空=全部")
    ap.add_argument("--offline", action="store_true", default=False,
                    help="只用离线源，不联网（默认联网，允许重试失败维度）")
    ap.add_argument("--force", action="store_true", help="忽略已有数据，全部重抓")
    ap.add_argument("--list", action="store_true", help="列出维度后退出")
    ap.add_argument("--flow-limit", type=int, default=1200,
                    help="资金流覆盖的票数上限（新浪每股一次请求，全市场太慢）")
    a = ap.parse_args()
    if a.list:
        print("可用维度：")
        for k, d, cn in DIMS:
            print("  %-8s %-34s 源：%s" % (k, d, cn))
        return
    only = [x.strip() for x in a.only.split(",") if x.strip()] or None
    bad = [x for x in (only or []) if x not in FETCHERS]
    if bad:
        print("未知维度：%s（用 --list 看全部）" % bad)
        return
    run(a.date, only=only, offline=a.offline, force=a.force,
        flow_limit=a.flow_limit)


if __name__ == "__main__":
    main()
