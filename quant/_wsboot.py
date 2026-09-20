# -*- coding: utf-8 -*-
"""westock MCP 引导：注入本地保存的 westock-mcp 入口后导入 _wsmcp。

用法：import _wsboot as W; W.call(tool, args)
（本机 CODEBUDDY_MCP_CONFIG 未挂载 westock-mcp 时，从 _wsmcp_local.json 补齐）

⚠️ 2026-09-20 修复：`_wsmcp_local.json` 里存的是**当时的** 127.0.0.1:<port>，
   Electron 每次启动端口都会变，旧实现无条件覆盖 live 配置 →
   所有 MCP 拉取脚本都会 502（init failed: {'code': 502}），且看起来像「服务端挂了」。
   现在只在①live 配置没有 westock-mcp，或②live 的 host:port 连不上时才用本地文件兜底。
"""
import os, json, sys, socket
from urllib.parse import urlparse

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

_LOCAL = os.path.join(_HERE, "_wsmcp_local.json")


def _live_entry():
    """从环境变量取 live 的 westock-mcp 配置；不存在返回 None。"""
    try:
        cfg = json.loads(os.environ.get("CODEBUDDY_MCP_CONFIG") or "{}")
        return (cfg.get("mcpServers") or {}).get("westock-mcp")
    except Exception:
        return None


def _alive(entry, timeout=1.5):
    """host:port 是否可连（只判端口，不发请求）。"""
    try:
        u = urlparse((entry or {}).get("url") or "")
        if not u.hostname:
            return False
        s = socket.socket()
        s.settimeout(timeout)
        try:
            return s.connect_ex((u.hostname, u.port or 80)) == 0
        finally:
            s.close()
    except Exception:
        return False


def _use_local(live):
    """是否需要本地兜底：无 live，或 live 端口已失效（应用重启换了端口）。"""
    if not live:
        return True
    if _alive(live):
        return False
    return os.path.exists(_LOCAL)


_live = _live_entry()
if os.path.exists(_LOCAL) and _use_local(_live):
    cfg = json.loads(os.environ.get("CODEBUDDY_MCP_CONFIG") or "{}")
    cfg.setdefault("mcpServers", {})["westock-mcp"] = json.load(open(_LOCAL, encoding="utf-8"))
    os.environ["CODEBUDDY_MCP_CONFIG"] = json.dumps(cfg, ensure_ascii=False)
    print("[_wsboot] live MCP 入口不可用，回退 _wsmcp_local.json（可能已过期）", file=sys.stderr)

import _wsmcp as W  # noqa: E402

_ready = False


def ensure():
    global _ready
    if not _ready:
        W.init()
        _ready = True
    return W


def call(tool, args=None, retry=2, sleep=2):
    """薄封装：限频预算与熔断都在 _wsmcp 层实现，这里不再叠加长睡眠。

    旧实现自身 retry=3 × sleep=20，与 _wsmcp、fetch 脚本的退避三层嵌套，
    导致单个被限频批次可空等 1000s+（09-18 实测 4368s）。现只保留极短兜底重试。
    """
    ensure()
    import time
    last = None
    for i in range(max(1, retry)):
        r = W.call(tool, args or {})
        if "error" not in r:
            return r
        last = r["error"]
        if getattr(W, "BREAK_HINT", "circuit-open") in str(last):
            break                      # 已熔断 → 立刻停，绝不空等
        if i < retry - 1:
            time.sleep(sleep)
    return {"error": last}


def fetch(tool, args, retry=2):
    """拉取并解析；失败（含限频/熔断）返回 None，供批量脚本优雅降级。

    取代各 fetch 脚本里手写的 fetch()+退避循环。
    """
    d = unwrap(call(tool, args, retry=retry))
    if isinstance(d, dict) and d.get("error"):
        return None
    return d


def reset_breaker():
    """跨日/换会话时清空熔断状态。"""
    ensure()
    if hasattr(W, "reset_breaker"):
        W.reset_breaker()


def unwrap(r):
    return W.unwrap(r) if hasattr(W, "unwrap") else r
