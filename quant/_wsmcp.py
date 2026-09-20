# -*- coding: utf-8 -*-
"""westock MCP 直连客户端（本地代理，与被授权的 MCP 工具同一服务端）。

用途：把批量拉取结果直接落盘，避免在会话里搬运巨大 payload。
严格尊重限频：批间 sleep 由调用方控制。
"""
import json, os, time, hashlib, datetime, urllib.request, urllib.error

_cfg = json.loads(os.environ["CODEBUDDY_MCP_CONFIG"])["mcpServers"]["westock-mcp"]
URL = _cfg["url"]
_HDR = _cfg["headers"]
TOKEN = _HDR["Authorization"].split(" ", 1)[-1]
CTX = _HDR["X-WorkBuddy-MCP-Context"]

_sid = None


def _post(body, is_init=False):
    global _sid
    hdr = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "Authorization": "Bearer " + TOKEN,
        "X-WorkBuddy-MCP-Context": CTX,
    }
    if _sid:
        hdr["Mcp-Session-Id"] = _sid
    req = urllib.request.Request(URL, data=json.dumps(body).encode(), headers=hdr, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            raw = r.read().decode("utf-8")
            got = r.headers.get("Mcp-Session-Id")
            if got:
                _sid = got
            ct = (r.headers.get("Content-Type") or "")
            if "text/event-stream" in ct or raw.startswith("event:"):
                for line in raw.split("\n"):
                    if line.startswith("data:"):
                        raw = line[5:].strip()
                        break
            if not raw.strip():
                return {"ok": True, "_empty": True}
            return json.loads(raw)
    except urllib.error.HTTPError as e:
        return {"error": {"code": e.code, "message": e.read().decode("utf-8", "ignore")[:400]}}


def init():
    r = _post({
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2025-06-18",
                   "capabilities": {},
                   "clientInfo": {"name": "quant-agent", "version": "1.0"}},
    }, True)
    if "error" in r:
        raise SystemExit("init failed: %s" % r["error"])
    _post({"jsonrpc": "2.0", "method": "notifications/initialized"})
    return r


_RATE_KEYS = ("服务限频", "限频", "error_type=2", "过于频繁", "请求太快",
             "rate limit", "429", "too many requests")

# ---------------- 限频预算 + 熔断（2026-09-19 新增，解决「空等 17 分钟仍失败」）----------------
# 旧行为：每层各自重试并长睡（_wsmcp 25+att*5、_wsboot 20、fetch 脚本 30+i*10），
# 三层嵌套叠加 → 单个被限频的批次可空等 1000s+ 才放弃（09-18 burst 日志实测 4368s）。
# 新行为：策略只在本层实现一次——指数退避 + **单次调用总等待预算** + **按工具熔断**。
BUDGET = 90.0        # 单次 call 累计等待上限（秒），超预算立即失败（下游降级落盘）
BACKOFF0 = 3.0       # 首次退避
BACKOFF_CAP = 45.0   # 单次退避上限
BREAK_N = 3          # 同一工具连续限频 N 次 → 熔断
BREAK_S = 240.0      # 熔断静默期（秒）

_streak = {}         # tool -> 连续限频计数
_tripped = {}        # tool -> 最近一次熔断时刻
BREAK_HINT = "circuit-open"      # 熔断标记；上层据此立刻停止重试


def _breaker_open(name):
    return (_streak.get(name, 0) >= BREAK_N
            and (time.time() - _tripped.get(name, 0)) < BREAK_S)


def reset_breaker():
    """手动清空熔断状态（跨日/换会话时调用）。"""
    _streak.clear()
    _tripped.clear()


def _result_error_text(res):
    """从 tools/call 的 result 里取错误文本；无错返回 None。

    关键：MCP 工具级错误用 result["isError"]=True + content[].text 表达，
    而不是 JSON-RPC 顶层的 "error"。历史 bug 正是漏检这个字段，
    导致「服务限频」被当成成功返回（表现为「成功但 0 条数据」），重试永不触发。
    """
    if not isinstance(res, dict):
        return None
    if res.get("isError") is True:
        c = res.get("content")
        if isinstance(c, list):
            for it in c:
                if isinstance(it, dict):
                    t = it.get("text")
                    if t:
                        return t
        return "unknown tool error"
    return None


def _is_rate_limited(msg):
    low = (msg or "").lower()
    return any(k.lower() in low for k in _RATE_KEYS)


# ---------------- 磁盘缓存（2026-09-20 新增：削减配额消耗）----------------
# 背景：MCP 层此前**完全没有缓存**。同一交易日里调试重跑、以及多个池共用同一批
# 数据（quote / chip / fund_flow / kline）时，**参数完全相同的请求**会被反复打到
# 服务端 —— 这是配额被吃光的第一大来源（比"间隔太短"更致命）。
# 本层对「成功的」调用结果做磁盘缓存，对上层脚本完全透明（不用改任何 fetch 脚本）。
#
# 有效期策略：
#   - 参数含 date/end 且 < 今天（历史日）→ **永久有效**（收盘数据不再变）；
#   - 当日 date 或无日期参数 → TTL（默认 600s），避免盘中也取到陈旧分时。
#   - 只缓存成功结果；限频/报错**一律不缓存**（否则一次限频会污染后续所有调用）。
# 开关：MCP_CACHE=0 关闭；MCP_CACHE_TTL=秒 改 TTL；MCP_CACHE_DEBUG=1 打印命中。
CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_mcp_cache")
CACHE_ON = os.environ.get("MCP_CACHE", "1").lower() not in ("0", "false", "no", "off")
CACHE_TTL = float(os.environ.get("MCP_CACHE_TTL", "600"))
CACHE_DEBUG = os.environ.get("MCP_CACHE_DEBUG", "") not in ("", "0")
_cache_hit = [0]
_cache_miss = [0]
_cache_save_n = [0]


def _today_str():
    return datetime.date.today().isoformat()


def _norm_date(v):
    """把 20260918 / 2026-09-18 / 2026/09/18 统一成 2026-09-18。"""
    s = str(v).strip().replace("/", "-")
    if len(s) == 8 and s.isdigit():
        return "%s-%s-%s" % (s[:4], s[4:6], s[6:8])
    return s


def _arg_date(arguments):
    if not isinstance(arguments, dict):
        return None
    for k in ("date", "end", "trade_date", "start", "begin"):
        v = arguments.get(k)
        if isinstance(v, (str, int)) and len(str(v)) >= 8:
            d = _norm_date(v)
            if len(d) == 10:
                return d
    return None


def _cache_ttl(arguments):
    d = _arg_date(arguments)
    if d and d < _today_str():
        return 0                 # 历史日：永久
    return CACHE_TTL


def _cache_path(name, arguments):
    raw = json.dumps({"t": name, "a": arguments}, ensure_ascii=False, sort_keys=True)
    h = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
    return os.path.join(CACHE_DIR, "%s__%s.json" % (name, h))


def _cache_load(cpath, ttl):
    if not os.path.exists(cpath):
        return None
    try:
        obj = json.load(open(cpath, encoding="utf-8"))
    except Exception:
        return None
    ts = obj.get("ts") or 0
    if ttl > 0 and (time.time() - ts) > ttl:
        return None
    return obj.get("result")


def _cache_save(cpath, name, arguments, res):
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        tmp = cpath + ".tmp"
        json.dump({"ts": time.time(), "tool": name, "args": arguments, "result": res},
                  open(tmp, "w", encoding="utf-8"), ensure_ascii=False)
        os.replace(tmp, cpath)
        _cache_save_n[0] += 1
    except Exception:
        pass


def cache_stats():
    n = len(os.listdir(CACHE_DIR)) if os.path.isdir(CACHE_DIR) else 0
    return {"on": CACHE_ON, "dir": CACHE_DIR, "files": n,
            "hit": _cache_hit[0], "miss": _cache_miss[0], "saved": _cache_save_n[0]}


def clear_cache(keep_days=None):
    """删缓存；keep_days 给定则只删「最近 N 天内没被读过」之外的旧文件。"""
    if not os.path.isdir(CACHE_DIR):
        return 0
    cut = time.time() - (keep_days or 0) * 86400
    n = 0
    for f in os.listdir(CACHE_DIR):
        p = os.path.join(CACHE_DIR, f)
        try:
            if keep_days is not None and os.path.getmtime(p) >= cut:
                continue
            os.remove(p)
            n += 1
        except Exception:
            pass
    return n


def call(name, arguments, retries=4, budget=BUDGET, use_cache=True):
    """单次工具调用，带「磁盘缓存 + 总等待预算 + 工具级熔断」的限频处理。

    - **缓存**：命中直接返回，不发请求（历史日永久、当日 TTL）；`use_cache=False` 跳过
    - 限频：指数退避 3→6→12→…→封顶 45s，**累计等待超过 budget 立即返回错误**
    - 同工具连续限频 ≥BREAK_N 次 → 熔断 BREAK_S 秒，期间直接秒回错误（不再空等）
    - 非限频错误：最多 2 次 2s 短退避后即返回（真错误应尽快暴露）
    返回：解析后的 result（成功）或 {"error": {...}}（失败）。
    """
    cpath = None
    if CACHE_ON and use_cache:
        cpath = _cache_path(name, arguments)
        hit = _cache_load(cpath, _cache_ttl(arguments))
        if hit is not None:
            _cache_hit[0] += 1
            if CACHE_DEBUG:
                import sys as _s
                print("[_wsmcp] cache hit %s %s" % (name, json.dumps(arguments, ensure_ascii=False)[:90]),
                      file=_s.stderr)
            return hit
        _cache_miss[0] += 1

    if _sid is None:
        init()
    if _breaker_open(name):
        left = int(BREAK_S - (time.time() - _tripped.get(name, 0)))
        return {"error": {"code": -32002,
                          "message": "%s %s：连续限频已熔断，%ds 后自动恢复"
                                     % (BREAK_HINT, name, left)}}
    last_err = None
    waited = 0.0
    delay = BACKOFF0
    soft = 0                       # 非限频错误的短重试计数
    for att in range(retries):
        r = _post({"jsonrpc": "2.0", "id": 100 + att,
                   "method": "tools/call",
                   "params": {"name": name, "arguments": arguments}})
        # 1) JSON-RPC 层错误
        if "error" in r:
            err = r
        else:
            # 2) 工具层错误（isError）—— 历史遗漏点
            res = r.get("result", r)
            etxt = _result_error_text(res)
            if etxt is None:
                _streak[name] = 0          # 成功 → 清零连续限频
                if cpath:
                    _cache_save(cpath, name, arguments, res)   # 只缓存成功结果
                return res
            err = {"error": {"code": -32000, "message": etxt}}
        last_err = err
        msg = json.dumps(err.get("error"), ensure_ascii=False)
        if not _is_rate_limited(msg):
            soft += 1
            if soft >= 2:
                return err                 # 真错误：快速暴露，不空等
            time.sleep(2.0); waited += 2.0
            continue
        _streak[name] = _streak.get(name, 0) + 1
        if _streak[name] >= BREAK_N:
            _tripped[name] = time.time()
            return err
        if waited + delay > budget or att == retries - 1:
            return err
        time.sleep(delay); waited += delay
        delay = min(delay * 2, BACKOFF_CAP)
    return last_err or {"error": "exhausted"}


def unwrap(r):
    """把 MCP content 解析成 dict。

    工具级错误（isError=True / 错误文本）统一转成 {"error": {"message": ...}}，
    保证下游 `if "error" in r` 能识别；历史版本会把它变成 {"_text": ...}
    导致上层误判为「成功但空数据」。
    """
    if r is None:
        return None
    if "error" in r:
        return r
    etxt = _result_error_text(r)
    if etxt is not None:
        return {"error": {"code": -32000, "message": etxt}}
    c = r.get("content")
    if isinstance(c, list):
        for it in c:
            t = it.get("text")
            if t:
                try:
                    o = json.loads(t)
                except Exception:
                    return {"_text": t}
                # 有些工具把错误塞在 ok=false 的 JSON 里
                if isinstance(o, dict) and o.get("ok") is False:
                    return {"error": {"code": -32001,
                                      "message": str(o.get("msg") or o.get("message") or "ok=false")}}
                return o
    if "structuredContent" in r:
        return r["structuredContent"]
    return r


if __name__ == "__main__":
    import sys
    if "--stats" in sys.argv:
        print(json.dumps(cache_stats(), ensure_ascii=False, indent=1))
    elif "--clear-cache" in sys.argv:
        args = [a for a in sys.argv[1:] if not a.startswith("--clear-cache")]
        keep = int(args[0]) if args and args[0].isdigit() else None
        print("已删除缓存 %d 个（keep_days=%s）" % (clear_cache(keep), keep))
    else:
        init()
        r = call("data_technical", {"codes": "sh600519", "date": "2026-09-16", "group": "macd,ma"})
        print(json.dumps(unwrap(r), ensure_ascii=False)[:800])
        print(json.dumps(cache_stats(), ensure_ascii=False), file=sys.stderr)
