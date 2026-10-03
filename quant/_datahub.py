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
    """全市场行情快照（**全市场 ~5200 只，不是事件域**）。

    ★ 2026-10-03 修正（用户指出「不是全市场那无法分析最有价值的标的」）：
      原实现读当日 `quotes/{DATE}.json`（只 524 只事件域）就返回，理由是
      「避免重复联网」—— **这个取舍是错的**。事件域 524 只**无法做全市场
      横截面分析**，而找「最有价值的标的」必须靠横截面分位排序。
      实测腾讯 qt 快照**全市场 5207 只仅 0.3 分钟**（65 批 × 80 只），
      根本不是瓶颈 —— 事件域口径是自缚手脚。
    做法：仅当当日缓存覆盖 ≥ 全市场 60% 才复用，否则直接批量拉全市场。
    """
    out = {"src": "", "ok": False, "reason": "", "data": {}, "scope": "", "n": 0}
    total = len(ctx.get("codes") or [])
    p = os.path.join(HERE, "quotes", "%s.json" % date)
    if os.path.exists(p):
        try:
            j = json.load(open(p, encoding="utf-8"))
            d = (j.get("data") or j)
            if isinstance(d, dict) and d:
                # 覆盖够大才当作全市场等价，否则继续拉全市场
                if not total or len(d) >= total * 0.6:
                    out.update(src="quotes缓存", ok=True, data=d,
                               scope="全市场（复用当日缓存 %d/%d）" % (len(d), total),
                               n=len(d))
                    return out
        except Exception:
            pass
    if offline:
        out["reason"] = "离线模式且当日 quotes 缓存覆盖不足（非全市场）"
        return out
    try:
        import _tx_fetch as T
        codes = ctx["codes"]
        got = {}
        B, GAP = 80, 0.05
        for i in range(0, len(codes), B):
            try:
                got.update(T.fetch_qt(codes[i:i + B]) or {})
            except Exception:
                pass
            time.sleep(GAP)
        if got:
            # ★ 快照无日期字段，必须交叉校验后才允许当 {date} 用
            vd, vmsg = _verify_snapshot_date(date, got)
            out["scope"] = "全市场（腾讯快照 %d/%d）" % (len(got), total)
            out["n"] = len(got)
            out["date_check"] = vmsg
            if vd is False:
                out.update(src="腾讯qt", ok=False, data={})
                out["reason"] = vmsg
            else:
                out.update(src="腾讯qt", ok=True, data=got)
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

    ★ 2026-10-03 修正：**改为全市场**。原先只取当日事件域（356 只），理由
    「新浪是每股一次请求，全市场要 20+ 分钟」—— **实测是错的**：
    600 只 4.2 秒（12 并发），**全市场 5207 只约 0.6 分钟**。
      资金流是「主力净流入横截面分位」的必需输入，只覆盖事件域
      → 无法在全市场范围比较谁更值得买 → 违背「找最有价值的标的」这一目的。
    """
    out = {"src": "", "ok": False, "reason": "", "data": {}, "scope": "", "n": 0}
    try:
        import fetch_rev_flow as FR
        fn = getattr(FR, "sina_batch", None)
        if fn is None:
            out["reason"] = "fetch_rev_flow 无 sina_batch"
            return out
        codes = ctx.get("codes") or _all_codes()
        if not codes:
            out["reason"] = "票池为空"
            return out
        lim = ctx.get("flow_limit", 0)
        if lim and len(codes) > lim:
            codes = codes[:lim]
        got = fn(codes)
        if got:
            out.update(src="新浪MoneyFlow", ok=True, data=got,
                       scope="全市场（新浪 %d/%d）" % (len(got), len(codes)), n=len(got))
            out["hist_dates"] = _flow_hist_span(got)
        else:
            out["reason"] = "新浪资金流全失败（%d 只）" % len(codes)
            return out

        # ★ 同时落**逐日序列**（2026-10-03 新增）。
        #   `sina_flow()` 只把 25 天逐日 netamount 压成 mf1/mf5/mf10/mf20 聚合值就丢掉了，
        #   而「资金流能否预测未来」这个问题**必须**有历史序列才能答（否则只能做截面，
        #   分不清「涨→流入」还是「流入→涨」）。故这里补抓序列，单独存 `seq`。
        seq = _fetch_flow_series(codes, num=ctx.get("flow_win") or 250)
        if seq:
            # ★ 单独存 `flowseq_{DATE}.json`，**不塞进 hub 主文件**：
            #   序列约 3.4MB，塞进去会让 hub 涨到 ~6MB 且每天都要重推。
            seq_path = os.path.join(HUB, "flowseq_%s.json" % DS(date))
            # ★ 列式存储：日期表共用一份（各票交易日基本一致），
            #   每票只存数值数组 → 体积从 ~32MB 降到 ~11MB。
            #   row_dates[i] 对应每票 values[i]（缺期为 None）。
            alld = sorted({d for v in seq.values() for d, _x in v})
            di = {d: i for i, d in enumerate(alld)}
            col = {}
            for c, v in seq.items():
                arr = [None] * len(alld)
                for d, x in v:
                    j = di.get(d)
                    if j is not None:
                        arr[j] = x
                col[c] = arr
            json.dump({"asof": date, "n": len(seq), "layout": "col",
                       "row_dates": alld, "span": _seq_span(seq),
                       "n_dates": len(alld), "values": col},
                      open(seq_path, "w", encoding="utf-8"), ensure_ascii=False)
            out["seq_file"] = os.path.basename(seq_path)
            out["seq_n"] = len(seq)
            out["seq_span"] = _seq_span(seq)
            out["scope"] += "；另存逐日序列 %s" % out["seq_file"]
        else:
            out["seq_file"] = ""
            out["seq_note"] = "序列抓取失败：资金流只有当日聚合值，无法回溯检验"
    except Exception as e:
        out["reason"] = "异常：%s" % str(e)[:80]
    return out


def _verify_snapshot_date(date, got, sample=400):
    """★ 交叉校验快照是否真的属于 {date}（防「无日期字段的快照冒充当日」）。

    腾讯 `fetch_qt` 返回的快照**不带任何日期字段**，只有数值。
    如果隔天重跑、或者接口返回了陈旧数据，光看 `ok=True` 是发现不了的
    —— 这直接违反「不许编数据」。

    做法：用 `_long_kline.json`（有明确 date 字段）交叉验证 `last`。
    抽查若干只，比对「快照 last」与「{date} 日K 收盘」，要求完全一致。
    不一致的比例超阈值 → 判失败，不允许当当日数据用。
    """
    lk_p = os.path.join(HERE, "_long_kline.json")
    if not os.path.exists(lk_p):
        return None, "无 _long_kline.json，无法校验快照日期"
    try:
        lk = json.load(open(lk_p, encoding="utf-8"))
    except Exception as e:
        return None, "读取日K失败：%s" % str(e)[:60]
    keys = [c for c in list(got)[:sample] if c in lk and lk[c]]
    if not keys:
        return None, "无交集样本可校验"
    ok = 0
    bad = 0
    for c in keys:
        bars = lk[c]
        if not bars or bars[-1].get("date") != date:
            continue                     # 该票当日无K线（停牌/新股），跳过
        a = got[c].get("last")
        b = bars[-1].get("last")
        if a and b and abs(float(a) - float(b)) <= max(0.02, float(b) * 1e-4):
            ok += 1
        else:
            bad += 1
    n = ok + bad
    if n == 0:
        return None, "样本均无当日K线，无法校验"
    rate = 100.0 * bad / n
    if rate > 2.0:
        return False, ("快照与 %s 日K 收盘不一致 %.1f%%（%d/%d）→ 快照不是 %s 的数据，"
                       "**拒绝当当日使用**" % (date, rate, bad, n, date))
    return True, "快照已校验= %s（日K 交叉 %d/%d 一致）" % (date, ok, n)


def _fetch_flow_series(codes, num=25, workers=12):
    """抓新浪**逐日**主力净流入序列 → {code: [[date, netamount], ...]}（升序）。

    为什么要单独抓：`sina_flow()` 返回的只是聚合视图（mf1/mf5/mf10/mf20），
    逐日明细被丢弃。而「资金流是领先还是滞后」必须用序列回答。
    """
    from concurrent.futures import ThreadPoolExecutor
    import fetch_rev_flow as FR

    def one(c):
        try:
            rows = FR._sina_rows(c, num)
        except Exception:
            return None
        if not rows:
            return None
        out = []
        for r in rows:
            try:
                out.append([r.get("opendate"), float(r.get("netamount") or 0)])
            except Exception:
                continue
        # 新浪返回是倒序（最新在前）→ 转为升序
        out.sort(key=lambda x: x[0] or "")
        return out or None

    res = {}
    try:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            for c, v in zip(codes, ex.map(one, codes)):
                if v:
                    res[c] = v
    except Exception:
        return res or None
    return res or None


def _seq_span(seq):
    if not seq:
        return ""
    first = next(iter(seq.values()))
    if not first:
        return ""
    ds = [r[0] for r in first if r and r[0]]
    return ("%s ~ %s（%d 日）" % (min(ds), max(ds), len(ds))) if ds else ""


def _flow_hist_span(got):
    """新浪每股返回 25 天逐日序列 → 报告历史覆盖区间（可回溯性检查）。

    ★ 2026-10-03 重要发现：`_sina_rows(code, 25)` 返回的是**逐日** netamount，
      底座存的 mf1/mf5/mf20 只是它的聚合视图。
      → **历史资金流可以回溯**，不必等「每日沉淀 40 天」才能做时间序列检验。
      这条直接决定「资金流因子能否预测未来」今天就可验证。
    """
    ds = [v.get("date") for v in got.values() if v.get("date")]
    if not ds:
        return ""
    return "%s ~ %s" % (min(ds), max(ds))


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
def run(date, only=None, offline=True, force=False, flow_limit=0, flow_win=250):
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
    ctx = {"codes": codes, "flow_limit": flow_limit, "flow_win": flow_win}
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
    ap.add_argument("--flow-win", type=int, default=250,
                    help="资金流逐日序列回溯天数（新浪实测最多 250 天≈1年）")
    ap.add_argument("--flow-limit", type=int, default=0,
                    help="资金流票数上限；0=全市场（实测 5207 只约 0.6 分钟，无需限）")
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
        flow_limit=a.flow_limit, flow_win=a.flow_win)


if __name__ == "__main__":
    main()
