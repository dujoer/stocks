# -*- coding: utf-8 -*-
"""推送后第三道门禁：抽检线上关键页 HTTP 状态码（须全 200）。
Pages 构建有约 1 分钟延迟，首次 404 属正常，脚本内置重试。
"""
import time, urllib.request, urllib.error, sys

BASE = "https://dujoer.github.io/stocks"
PAGES = [
    "/",
    "/index.html",
    "/web/market/index.html",
    "/web/lhb/lhb.html",
    "/web/lhb/lhb_2026-09-10.html",
    "/web/lhb/lhb_2026-09-11.html",
    "/web/lhb/index.html",
    "/web/exec/index.html",
    "/web/block/index.html",
    "/web/block/block_2026-09-11.html",
    "/web/sector/index.html",
    "/web/sector/sector-strength-20260911.html",
    "/web/sector/sector-strength-trend.html",
    "/web/tplus/index.html",
    "/web/tplus/tplus-2026-09-11.html",
    "/web/psychology/index.html",
    "/web/picks/index.html",
    "/web/db/index.html",
    "/web/sections/index.html",
    "/web/data/manifest.json",
]

def probe(url, tries=4):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=25) as r:
                return r.status, len(r.read())
        except urllib.error.HTTPError as e:
            last = e.code
        except Exception as e:
            last = str(e)
        time.sleep(3 + i * 4)
    return last, 0

bad = []
for p in PAGES:
    code, n = probe(BASE + p)
    ok = "OK " if code == 200 else "!! "
    if code != 200:
        bad.append(p)
    print("%s %-4s %8s  %s" % (ok, code, n, p), flush=True)

print("GATE_DONE bad=%d / total=%d" % (len(bad), len(PAGES)), flush=True)
if bad:
    print("BAD_LIST: " + ", ".join(bad), flush=True)
