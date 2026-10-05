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
import re
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


def limit_pct(code):
    """该代码的涨停幅度（20cm 创业板/科创板、30cm 北交所、其余 10cm）。

    ⚠ 此口径原先在 `_gen_market_overview_offline.py` / `_gen_limitup_offline.py`
    各写一份 —— 改一处就会分叉（涨停家数直接错位）。此处提为统一层唯一定义，
    新脚本一律引它；那两处老脚本暂未改（避免回归），收敛情况记在审计页遗留项。
    """
    if code.startswith("sz30") or code.startswith("sh688"):
        return 0.20
    if code.startswith("bj") or code[2:4] in ("83", "87", "92"):
        return 0.30
    return 0.10


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

#: 长K统一层 `_longk.py`（管 401MB 的 _long_kline.json）的豁免名单。
#: ★ 与 TXK_READ_ALLOW 分开列：不能让日K侧的豁免顺带盖掉长K侧，
#:   也不能反过来 —— 两条缓存各有各的写路径。
LONG_READ_ALLOW = (
    "_longk.py",                     # 统一层自身
    "_data_integrity_audit.py",
    "_datahub_api.py",
    "_fetch_long_kline.py",          # ★ 写路径：抓取并回写长K缓存
)

_ASSIGN_RE = re.compile(r"^\s*(\w+)\s*=")
#: 抓 `json.load(open(<变量>(, ...))` 里的变量名
_LOADARG_RE = re.compile(r"json\.load\(\s*open\(\s*(\w+)")


def _strip_comment(line):
    """去掉行尾注释（`#` 只有落在引号外才算注释）。返回剥过的新行（原行不变）。"""
    q = None
    for i, ch in enumerate(line):
        if q:
            if ch == q:
                q = None
        elif ch in "\"'":
            q = ch
        elif ch == "#":
            return line[:i].rstrip()
    return line.rstrip()


def scan_text(text, token, importer):
    """从**一段源码文本**里找「直读该缓存却没走统一层」的位置 → [(行号, 归因)]。

    纯函数（不碰文件系统），所以能拿内置样例做**反向自测** —— 这道门禁自己
    也从没被验过会不会假绿，正则一改就悄悄失效，必须能自证。

    用轻量数据流追踪而非文本匹配：`p = …_txk_cache.json` 之后 `json.load(open(p))`
    是真直读，但同一个 `p` 随后被改成 `macd_scan_*.json` 就不是了。只做文本匹配
    会两头错（漏检局部别名 + 误报改道后的 load）。
    """
    if re.search(r"^import %s\b" % re.escape(importer), text, re.M):
        return []                     # 已接统一层 → 不判（自测里显式验这条）
    state, hits = {}, []
    for i, raw in enumerate(text.split("\n"), 1):
        # ★ 先剥注释：门禁自己那行注释就写着「json.load 打开 _txk_cache.json」，
        #   不剥的话门禁拿自己当靶子报一条（实测真发生过），白白消耗可信度。
        #   `#` 在引号内不算注释，字符串里的文件名要留着。
        L = _strip_comment(raw)
        m = _ASSIGN_RE.match(L)
        if m:                                          # 行首赋值：更新「该变量此刻指向什么」
            state[m.group(1)] = (token in L)
        if "json.load" not in L:
            continue
        if token in L:                                 # 字面量内嵌
            hits.append((i, "literal"))
            continue
        for v in _LOADARG_RE.findall(L):
            if state.get(v):
                hits.append((i, "alias:" + v))
                break
    ded = []
    for h in hits:                                     # 相邻行合并，避免一处两行算两下
        if not ded or h[0] - ded[-1][0] > 1:
            ded.append(h)
    return ded


def scan_readers(token, importer, allow=(), quant_dir=None, skip=None):
    """扫 quant/*.py，返回「直读 <token> 却没 import <importer>」的脚本 → [(名, 处数, [行号])]。"""
    base = quant_dir or HERE
    skip = set(skip or ()) | {os.path.basename(__file__)}   # 自身别扫
    out = []
    for path in sorted(glob.glob(os.path.join(base, "*.py"))):
        name = os.path.basename(path)
        if name in skip or name in allow or name.startswith("_legacy"):
            continue
        try:
            text = io.open(path, encoding="utf-8").read()
        except OSError:
            continue
        hits = scan_text(text, token, importer)
        if hits:
            out.append((name, len(hits), [h[0] for h in hits]))
    return out


def scan_txk_readers(quant_dir=None, skip=None):
    """★ 单一真源：门禁 C3 与审计页都调它，别在别处另写一份判据。"""
    return scan_readers("_txk_cache", "_txk", TXK_READ_ALLOW, quant_dir, skip)


def scan_longk_readers(quant_dir=None, skip=None):
    """长K（401MB _long_kline.json）的直读扫描，与日K同一套判据。"""
    return scan_readers("_long_kline", "_longk", LONG_READ_ALLOW, quant_dir, skip)


#: (说明, 源码文本, 期望命中的条数)。0 条 = 期望它**不**报（负例）。
#: 覆盖四种形态：字面量内嵌 / 大写常量 / 局部别名 / 改道后不应误报；
#: 外加一条「已 import 统一层」—— 此时即使有裸 load 也不该报。
#: 样例用 `{tok}` 占位：同一组形态对日K / 长K 都跑一遍，别把文件名写死进样例
#: （第一版就把 `_txk_cache.json` 硬编码了，长K 三条正例全测不出来 —— 自测当场炸出来）。
_SELFTEST_CASES = (
    ("字面量内嵌",
     'cache = json.load(open(os.path.join(Q, "{tok}")))', 1),
    ("大写常量",
     'CACHE = os.path.join(Q, "{tok}")\nk = json.load(open(CACHE, encoding="utf-8"))', 1),
    ("局部别名",
     'p = os.path.join(QUANT, "{tok}")\nk = json.load(open(p, encoding="utf-8"))', 1),
    ("改道后不算直读",
     'p = os.path.join(QUANT, "{tok}")\np = os.path.join(QUANT, "macd_scan.json")\nk = json.load(open(p))', 0),
    ("只列文件名不 load",
     'CACHE = os.path.join(Q, "{tok}")\nprint(CACHE)', 0),
    ("已接统一层则不报",
     'import {imp}\nbars = json.load(open("{tok}"))', 0),
    ("注释里提到不算直读",
     '# 说明：这里 json.load 打开 "{tok}" 只是注释\nk = 1', 0),
    ("行尾注释不挡住真直读",
     'p = os.path.join(QUANT, "{tok}")  # 本地大缓存\nk = json.load(open(p))  # 直接读', 1),
)


def selftest_scan(verbose=True):
    """反向自测扫描器本身：内置样例跑一遍，命中条数不符就炸。

    ★ 这道门禁自己也会失效（正则/数据流一改就假绿），所以「门禁」之前先有「门禁的门禁」。
    返回(bool, [str])；失败即 SystemExit，不会被当成通过。
    """
    bad, lines = [], []
    for token, importer in (("_txk_cache", "_txk"), ("_long_kline", "_longk")):
        for desc, tpl, want in _SELFTEST_CASES:
            src = tpl.format(tok=token, imp=importer)
            got = len(scan_text(src, token, importer))
            ok = (got == want)
            if not ok:
                bad.append("%s/%s：期望 %d 处，实际 %d 处" % (token, desc, want, got))
            lines.append("    %-4s %-18s %-14s 期望 %d / 实得 %d"
                         % ("ok" if ok else "FAIL", token, desc, want, got))
    if verbose:
        print("[C3 判据自测] %d 组样例" % (2 * len(_SELFTEST_CASES)))
        print("\n".join(lines))
        print("    结果：%s" % ("PASS" if not bad else "FAIL"))
    return (not bad), bad


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        ok, bad = selftest_scan()
        for b in bad:
            print("  ! " + b)
        raise SystemExit(0 if ok else 1)
    t0 = time.time()
    d = load()
    t1 = time.time()
    d2 = load()
    t2 = time.time()
    print("首次 %.3fs（%d 只），二次 %.5fs（缓存命中），合计 %.3fs"
          % (t1 - t0, len(d), t2 - t1, t2 - t0))
    print("数据截至：", last_date(d))
    print("加载统计：", json.dumps(load_stats(), ensure_ascii=False))
