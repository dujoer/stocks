#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""长历史日K（quant/_long_kline.json）的**唯一加载入口**。

为什么要抽这一层
----------------
原先 6+ 个脚本各自 `json.load` 同一个 401MB 文件，且行为互相分叉：

    _dip_probe.py / _cold_sector.py  → 缺文件返回 {}（调用方自己打印提示）
    _flow_lead_lag.py / _nonprice_lead.py → 缺文件**静默回退** _txk_cache（250 根短缓存）
    _datahub.py:322                  → 缺文件返回 None + 原因串
    _selected_attrib.py:283          → 按 a.source 二选一，走的是拼接路径

「缺文件时用 250 根短缓存冒充 780 根长历史」是最危险的一支：
研究结论会悄悄从「三年」变成「一年」却不报错。

统一口径
--------
* **默认不回退**。缺 `_long_kline.json` 一律返回 `{}`，由调用方已有的
  `if not bars: print("！无长历史，先跑 _fetch_long_kline.py")` 分支显式报出来。
  只有调用方显式 `allow_short=True` 才回退 `_txk_cache`，且必须在产物里标注来源。
* **mtime 感知的模块级缓存**：同一进程内多次调用只 load 一次
  （实测 401MB 首次 1.9s，之后 ~0s）。日更链路一次跑十几个脚本，这一项实打实省时间。
* 任何一次加载都记进 `STATS`，可用 `load_stats()` 取回用于效率自检。

用法
----
    import _longk
    bars = _longk.load_long()                       # 严格：缺文件返回 {}
    bars = _longk.load_long(allow_short=True)       # 显式允许回退（产物须标 src）
    print(_longk.load_stats())                      # {"load": n, "bytes": n, "secs": x}
"""

from __future__ import annotations
import os
import json
import time

HERE = os.path.dirname(os.path.abspath(__file__))
LONG = os.path.join(HERE, "_long_kline.json")
SHORT = os.path.join(HERE, "_txk_cache.json")

STATS = {"loads": 0, "bytes": 0, "secs": 0.0, "paths": []}

_cache = None      # (mtime, data)
_cache_sig = None

#: 允许回退的脚本，写在这里是为了「谁用了变通」可在页面上一眼查到
SHORT_FALLBACK_BY = ("_flow_lead_lag.py", "_nonprice_lead.py",
                     "_datahub.py", "_selected_attrib.py")


def _read(path, label):
    t0 = time.time()
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    dt = time.time() - t0
    try:
        n = os.path.getsize(path)
    except OSError:
        n = 0
    STATS["loads"] += 1
    STATS["bytes"] += n
    STATS["secs"] += dt
    STATS["paths"].append({"path": os.path.basename(path),
                           "label": label, "secs": round(dt, 3),
                           "mb": round(n / 1e6, 1),
                           "codes": len(data) if isinstance(data, dict) else None})
    return data, dt


def load_long(here=None, allow_short=False):
    """读长历史日K。

    `here` 便于测试时指向别的目录；正常调用不要传。
    `allow_short` 仅在调用方确认「用 250 根短缓存也可接受」时置 True，
    此时返回的数据来自 `_txk_cache`，**条数远少于长历史**，产物须标注来源。
    """
    global _cache, _cache_sig
    base = here or HERE
    path = os.path.join(base, "_long_kline.json")
    if not os.path.exists(path):
        if allow_short:
            return _load_with_short(path, base)
        if _cache is not None:           # 同一进程内已失败过，直接复用结论
            return _cache
        try:
            m = os.path.getmtime(SHORT) if os.path.exists(SHORT) else -1
            _cache, _cache_sig = {}, m
        except OSError:
            _cache, _cache_sig = {}, None
        return _cache

    try:
        mt = os.path.getmtime(path)
    except OSError:
        return {} if _cache is not None else {}
    if _cache is not None and _cache_sig == mt:
        return _cache

    data, _ = _read(path, "long")
    _cache, _cache_sig = data, mt
    return data


def _load_with_short(long_path, base):
    """显式允许时的回退：读 250 根短缓存。调用方必须自己标注来源。"""
    short = os.path.join(base, "_txk_cache.json")
    if not os.path.exists(short):
        return {}
    data, _ = _read(short, "short(回退)")
    return data


def load_stats():
    """返回本进程累计的加载开销，供「有效率」自检落盘。"""
    return {"loads": STATS["loads"],
            "bytes_mb": round(STATS["bytes"] / 1e6, 1),
            "secs": round(STATS["secs"], 3),
            "paths": STATS["paths"]}


def src_label(allow_short=False):
    """产物里标注 K 线来源用。缺长K 时不要写成「长历史」。"""
    if os.path.exists(LONG):
        return "_long_kline"
    if allow_short:
        return "_txk_cache(回退·仅250根)"
    return "_long_kline(缺失)"


if __name__ == "__main__":
    t0 = time.time()
    d = load_long()
    t1 = time.time()
    d2 = load_long()
    t2 = time.time()
    print("首次 %.2fs（%d 只），二次 %.4fs（缓存命中），合计 %.2fs"
          % (t1 - t0, len(d), t2 - t1, t2 - t0))
    print("加载统计：", json.dumps(load_stats(), ensure_ascii=False))
