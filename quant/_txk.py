#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""全市场日K缓存（quant/_txk_cache.json）的**唯一加载入口**。

为什么要抽这一层
----------------
原先 **39 个脚本各自 `json.load` 同一个 128MB 文件**：

    _rev_lab.py / _gen_flow_all.py  → `json.load(open(os.path.join(Q, "_txk_cache.json"), ...))`
    _tplus_lab.py / _selected_lab.py / _rev_tier_gate.py / _hw_tier_gate.py
                                    → 各自 `CACHE = ...` + 自己 open
    _tx_fetch.py / _fetch_long_kline.py / ...

同一份 128MB 数据在**同一次日更**里被反复解析几十次，每次 ~0.56s，
而且各家行为不一致：有的缺文件静默返回 `{}`，有的抛异常，有的顺手改键名。

统一口径
--------
* **mtime 感知的模块级缓存**：同一进程内多次调用只 load 一次
  （实测 128MB 首次 0.57s、命中 ~0s）。缓存文件被写回后（mtime 变）
  自动失效重新读，**不会出现「读到旧版本」**。
* **只读共享**。仓库内已确认没有脚本 `json.dump` 回 `_txk_cache.json`；
  万一日后有，mtime 变化会把缓存顶掉，行为不会悄悄错。
* **新鲜度校验（可选但强烈建议）**：`set_asof('2026-09-30')` 之后，
  命中缓存时会检查「末根日期 ≥ 数据日」。txk 是**主缓存**——
  很多脚本直接拿它当「当日价」，旧数据冒充当日价的后果比长K更直接。
  不达标时 `_txk.py` 返回 `{}`，由调用方已有分支显式报出来，
  **绝不静默拿旧价算结论**。
* 每次加载记进 `STATS`，`_daily_profile.json` 会用「有效率」口径汇总。

用法
----
    import _txk
    bars = _txk.load()                  # 缺文件 / 陈旧 → {}
    _txk.set_asof('2026-09-30')         # 推荐：先钉数据日再取数
    print(_txk.load_stats())
"""

from __future__ import annotations
import os
import io
import glob
import json
import time
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "_txk_cache.json")
#: 打开方式：`WB_TXK_LOG=1 python _rev_lab.py`。默认关闭，零开销；
#: 日更链路打开它，就能统计「这一轮到底把 128MB 解析了多少次、花了多少秒」。
LOG_ENV = "WB_TXK_LOG"
LOG_PATH = os.path.join(HERE, "_txk_loadlog.jsonl")

STATS = {"loads": 0, "bytes": 0, "secs": 0.0, "paths": [], "stale_blocks": 0}

_cache = None          # (mtime, data)
_cache_sig = None
_asof = None           # 钉住的数据日，形如 '2026-09-30'
_last_seen = None      # 已缓存数据的「全局最晚交易日」，只在读盘时算一次
                       # ★ 关键：命中缓存路径上不能再扫 5049 票，否则缓存白做


def set_asof(date):
    """钉住本轮的数据日（YYYY-MM-DD）。

    必须在第一次 `load()` **之前**调用才生效。设过之后，若缓存末根日期
    早于该日，`load()` 返回 `{}`（fail-safe：宁可不出数，也不拿旧价冒充当日）。
    传 None 表示不做新鲜度校验。
    """
    global _asof
    _asof = date
    return _asof


def last_date(data):
    """取缓存里**全局最晚**的交易日（扫描所有票的末根）。

    5049 票全扫约 0.6s；只在 `check_fresh()` 里调一次，不要放进热路径。
    """
    best = None
    if isinstance(data, dict):
        items = data.items()
    else:
        items = []
    for _, bars in items:
        if isinstance(bars, list) and bars:
            d = bars[-1].get("date") if isinstance(bars[-1], dict) else None
            if d and (best is None or d > best):
                best = d
    return best


def _read():
    t0 = time.time()
    with open(CACHE, encoding="utf-8") as f:
        data = json.load(f)
    dt = time.time() - t0
    try:
        n = os.path.getsize(CACHE)
    except OSError:
        n = 0
    try:
        mt = os.path.getmtime(CACHE)
    except OSError:
        mt = None
    STATS["loads"] += 1
    STATS["bytes"] += n
    STATS["secs"] += dt
    STATS["paths"].append({"path": "_txk_cache.json", "secs": round(dt, 3),
                           "mb": round(n / 1e6, 1),
                           "codes": len(data) if isinstance(data, dict) else None,
                           "last_date": last_date(data)})
    _maybe_log(os.path.basename(sys.argv[0]) if sys.argv else "?", dt, n)
    return data, mt


def _maybe_log(script, dt, nbytes):
    """记一行加载日志（仅当 WB_TXK_LOG=1）。默认关闭 → 不影响日更耗时。

    日更链路靠它统计「这一轮到底把 128MB 解析了多少次、一共花了多少秒」，
    把「不重复取数」从口头话变成可查证的数字。
    """
    if not os.environ.get(LOG_ENV):
        return
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps({"t": round(time.time(), 3), "script": script,
                                "secs": round(dt, 3), "mb": round(nbytes / 1e6, 1)},
                               ensure_ascii=False) + "\n")
    except OSError:
        pass


def load(here=None, allow_stale=False):
    """读全市场日K主缓存。

    `here` 便于测试时指向别的目录；正常调用不要传。
    `allow_stale=True` = 我知道缓存可能没更新到数据日，仍然要算
    （此时请用 `src_label()` 在产物里把「数据截至 X」标出来）。
    """
    global _cache, _cache_sig, _last_seen, _asof
    base = here or HERE
    path = os.path.join(base, "_txk_cache.json")
    if not os.path.exists(path):
        # ★ 缺文件 = 读不到数据 —— 抛出去，别在库层悄悄变成空数据。
        # 原来各调用点裸 `json.load(open(...))` 缺文件就是 FileNotFoundError
        # （脚本当场崩，问题一眼可见）；若这里返回 {}，下游会拿「空缓存」算出一份
        # 看似正常的空结论 —— 是 fail-open，比崩溃危险得多。
        # 需要降级的调用点（如 _datahub 取名兜底）自己 try/except 即可。
        raise FileNotFoundError(path)

    try:
        mt = os.path.getmtime(path)
    except OSError:
        return {} if _cache is not None else {}

    # ★ 陈旧拦截必须在「返回」之前，不能只计数不拦（fail-open 反例）：
    #   钉了数据日却仍把旧数据交出去 = 旧价冒充当日，比不缓存危险得多。
    # 判据走 _stale_hit() 单一真源，不在 load 里再写一遍比较（防两处口径分叉）
    if _asof and not allow_stale and _stale_hit():
        # 不返回脏数据；但 _cache 保留着，等数据抓齐（钉对日期）自动恢复
        STATS["stale_blocks"] += 1
        return {}

    if _cache is not None and _cache_sig == mt:
        # 命中缓存：零读盘返回（这就是统一层省下的时间）
        STATS["loads"] += 0
        return _cache

    data, mt2 = _read()
    _last_seen = last_date(data)          # 顺手记下，后续命中路径直接复用
    _cache, _cache_sig = data, mt2
    return _cache


def _stale_hit():
    """钉过数据日且已缓存数据过旧 → True（只做标记，不读盘、不重扫）。"""
    if _cache is None or _asof is None:
        return False
    ld = _last_seen or ""
    return bool(ld) and ld < _asof


def _cache_last():
    """已缓存数据的全局最晚交易日（有缓存就 O(1)，没缓存才扫盘）。"""
    if _last_seen:
        return _last_seen
    return last_date(_cache if _cache is not None else {})


def load_stats():
    """本进程累计的 txk 加载开销，供「有效率」自检落盘。"""
    return {"loads": STATS["loads"],
            "bytes_mb": round(STATS["bytes"] / 1e6, 1),
            "secs": round(STATS["secs"], 3),
            "stale_blocks": STATS["stale_blocks"],
            "paths": STATS["paths"]}


def src_label(allow_stale=False):
    """产物里标注 K 线来源用：把「数据截至哪天」写清楚，别让人误当日数。"""
    if not os.path.exists(CACHE):
        return "_txk_cache(缺失)"
    ld = _cache_last()
    if _asof and not allow_stale and ld and ld < _asof:
        return "_txk_cache(陈旧·截至 %s)" % ld
    return "_txk_cache(截至 %s)" % (ld or "未知")


def bar_of(code, date):
    """取某票某日的 bar；没有就 None。绝大多数脚本真正用到的只是这一条。"""
    data = _cache if _cache is not None else load()
    if not isinstance(data, dict):
        return None
    bars = data.get(code)
    if not isinstance(bars, list):
        return None
    for b in bars:
        if isinstance(b, dict) and b.get("date") == date:
            return b
    return None


#: 允许直读大缓存的脚本。语义分两类：
#:  - 写路径（抓取/回写缓存本身，它必须独占文件句柄）
#:  - 纯统计/清单文件（只是把文件名当字符串列出来，并不 json.load 内容）
#: ★ 门禁 _coverage_check 的 [C3] 与审计页都调 scan_txk_readers()，判据只有这一处。
TXK_READ_ALLOW = (
    "_txk.py",                       # 统一层自身
    "_data_integrity_audit.py",      # 审计页统计「谁读了它」，读的是文件名不是内容
    "_page_registry.py",             # need 文案里出现文件名
    "_push_lhb.py",                  # FILES 白名单里的字符串
    "_push_incremental.py",
    "_tx_fetch.py",                  # ★ 写路径：抓取并回写缓存
    "_txk_refresh.py",               # ★ 写路径：重建缓存
    "_append_txk_day.py",            # ★ 写路径：追加单日
    "_append_txk_0923.py",           # ★ 写路径：历史补写
    "_datahub_api.py",               # 在线服务口，自己管连接与新鲜度校验
)


def scan_txk_readers(quant_dir=None, skip=None):
    """扫出「直读 _txk_cache.json 却没走统一层」的脚本 → [(name, 处数, [行号])]。

    用轻量数据流追踪而非文本匹配：`p = …_txk_cache.json` 之后 `json.load(open(p))`
    是真直读，但同一个 `p` 随后被改成 `macd_scan_*.json` 就不是了。只做文本匹配
    会两头错（漏检局部别名 + 误报改道后的 load）。
    """
    import re
    base = quant_dir or HERE
    skip = set(skip or ()) | {os.path.basename(__file__)}   # 自身别扫
    out = []
    for path in sorted(glob.glob(os.path.join(base, "*.py"))):
        name = os.path.basename(path)
        if name in skip or name in TXK_READ_ALLOW or name.startswith("_legacy"):
            continue
        try:
            lines = io.open(path, encoding="utf-8").read().split("\n")
        except OSError:
            continue
        if re.search(r"^import _txk\b", "\n".join(lines), re.M):
            continue                                   # 已接统一层
        state, hits, _ASSIGN = {}, [], re.compile(r"^\s*(\w+)\s*=")
        for i, L in enumerate(lines, 1):
            m = _ASSIGN.match(L)
            if not m:
                continue
            if "_txk_cache" in L:
                state[m.group(1)] = True               # 此刻该变量指向大缓存
            else:
                state[m.group(1)] = False              # 被别的赋值覆盖
            if "json.load" not in L:
                continue
            if "_txk_cache" in L:                      # 字面量内嵌
                hits.append(i)
                continue
            for v in re.findall(r"json\.load\(\s*open\(\s*(\w+)", L):
                if state.get(v):
                    hits.append(i)
                    break
        hits = [h for j, h in enumerate(hits) if j == 0 or h - hits[j - 1] > 1]
        if hits:
            out.append((name, len(hits), hits))
    return out


if __name__ == "__main__":
    t0 = time.time()
    d = load()
    t1 = time.time()
    d2 = load()
    t2 = time.time()
    print("首次 %.3fs（%d 只），二次 %.5fs（缓存命中），合计 %.3fs"
          % (t1 - t0, len(d), t2 - t1, t2 - t0))
    print("数据截至：", last_date(d))
    print("加载统计：", json.dumps(load_stats(), ensure_ascii=False))
