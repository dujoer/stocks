# -*- coding: utf-8 -*-
"""westock CLI 取数 → 站点原始 JSON（离线降级通道）。

为什么需要它
------------
`daily_all.py` 的 ③④⑤⑩ 步是 MANUAL：依赖 westock MCP 实时取数。MCP 握手失败
（initialize 502）时，第 ⑤ 步「板块强度」和第 ② 步的龙虎榜原始数据会永久停在旧数据日。
而 `westock` CLI 与 MCP **同源同口径**，只是输出 markdown 表格 —— 本脚本负责
「表格 → 站点既有 JSON schema」的转换，不动任何字段口径、不做任何推算。

产出（与 MCP 路径完全同构，下游脚本无需改动）：
  · sector:  quant/sector_{industry|concept}_{DS}.json
  · lhb:     quant/lhb/{YYYY-MM-DD}.json   （all/jg/yyb/gslmr/gslxw/yzb）

用法：
  python quant/_westock_cli_fetch.py sector --date 2026-10-09
  python quant/_westock_cli_fetch.py lhb    --date 2026-10-09
  python quant/_westock_cli_fetch.py all    --date 2026-10-09

⚠ 取值受限时（CLI 未返回该榜）**如实置空**，不编造；`data.src` 标注真实来源。
"""
from __future__ import annotations
import argparse, json, os, re, shutil, subprocess, sys

Q = os.path.dirname(os.path.abspath(__file__))
NAMES = os.path.join(Q, "_stock_names.json")


def cli_path():
    return shutil.which("westock") or os.path.expanduser("~/.local/bin/westock")


def run_cli(args, timeout=90):
    """跑一条 westock 命令，取 stdout。失败抛 SystemExit（不静默）。"""
    exe = cli_path()
    r = subprocess.run([exe] + args, capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise SystemExit("[fail] westock %s 退出码 %d：%s"
                         % (" ".join(args), r.returncode, (r.stderr or r.stdout)[:200]))
    return r.stdout


def parse_table(text, title_kw=None):
    """markdown 表格 → [dict]。只认以 | 开头的行，跳过分隔行。"""
    lines = [l.strip() for l in text.splitlines() if l.strip().startswith("|")]
    if len(lines) < 2:
        return []
    head = [c.strip() for c in lines[0].strip("|").split("|")]
    rows = []
    for l in lines[1:]:
        cells = [c.strip() for c in l.strip("|").split("|")]
        if len(cells) != len(head):
            continue
        if all(set(c) <= set("-: ") for c in cells):     # 分隔行
            continue
        rows.append(dict(zip(head, cells)))
    return rows


#: 必须保持字符串的列（其余一律尝试转数值，失败则保留原文）
STR_KEYS = {"code", "name", "upCount", "stockName", "id"}
#: 嵌套 JSON 文本列
JSON_KEYS = {"branchList", "stockList"}


def conv_row(r):
    out = {}
    for k, v in r.items():
        if k in JSON_KEYS:
            try:
                out[k] = json.loads(v)
            except Exception:
                out[k] = []
        elif k in STR_KEYS:
            out[k] = v
        else:
            try:
                out[k] = float(v)
            except Exception:
                out[k] = v
    return out


# ── sector ──────────────────────────────────────────────────────────
_LEADER_RE = re.compile(r"^(.*?)[（(]\s*([-+]?\d+(?:\.\d+)?)\s*[)）]\s*$")


def _name2code():
    try:
        d = json.load(open(NAMES, encoding="utf-8"))
    except Exception:
        return {}
    if isinstance(d, dict) and d and str(next(iter(d)))[:2] in ("sh", "sz", "bj"):
        rev = {}
        for c, n in d.items():
            rev.setdefault(n if isinstance(n, str) else (n.get("name") if isinstance(n, dict) else ""), c)
        return rev
    return {}


def fetch_sector(date):
    ds = date.replace("-", "")
    rev = _name2code()
    for kind in ("industry", "concept"):
        txt = run_cli(["sector", "ranking", "--kind", kind])
        rows = [conv_row(r) for r in parse_table(txt)]
        for r in rows:
            ld = r.pop("leader", "") or ""
            m = _LEADER_RE.match(ld)
            if m:
                nm, pct = m.group(1).strip(), float(m.group(2))
                r["leader"] = {"code": rev.get(nm, ""), "name": nm, "changePct": pct}
            else:
                r["leader"] = {"code": "", "name": ld, "changePct": None} if ld else {}
            r.pop("changePct ", None)
        out = {"ok": True, "data": {"kind": kind, "type": "changepct", "order": "desc",
                                    "rows": rows, "src": "westock CLI sector ranking"}}
        p = os.path.join(Q, "sector_%s_%s.json" % (kind, ds))
        json.dump(out, open(p, "w", encoding="utf-8"), ensure_ascii=False)
        miss = sum(1 for r in rows if not (r.get("leader") or {}).get("code"))
        print("  sector %-8s -> %s  %d 行（leader 未匹配 code %d）"
              % (kind, os.path.basename(p), len(rows), miss))
    return True


# ── lhb ─────────────────────────────────────────────────────────────
LHB_TYPES = [("institution", "jg"), ("activeseat", "yyb"),
             ("winbuy", "gslmr"), ("winseat", "gslxw")]


def fetch_lhb(date):
    data = {"date": date, "all": [], "jg": [], "yyb": [], "gslmr": [], "gslxw": [], "yzb": []}
    data["all"] = [conv_row(r) for r in parse_table(run_cli(["lhb", "--date", date]))]
    for t, key in LHB_TYPES:
        try:
            data[key] = [conv_row(r) for r in
                         parse_table(run_cli(["lhb", "--date", date, "--type", t]))]
        except SystemExit as ex:
            print("  ⚠ %s 取数失败，如实置空：%s" % (t, str(ex)[:110]))
            data[key] = []
        print("  lhb %-12s %d 条" % (key, len(data[key])))
    out = {"ok": True, "data": data,
           "src": "westock CLI lhb（主榜 + 机构/活跃席位/高胜率买入/高胜率席位）"}
    p = os.path.join(Q, "lhb", "%s.json" % date)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    json.dump(out, open(p, "w", encoding="utf-8"), ensure_ascii=False)
    print("  lhb -> %s  all=%d" % (os.path.basename(p), len(data["all"])))
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=["sector", "lhb", "all"])
    ap.add_argument("--date", required=True, help="交易日 YYYY-MM-DD")
    a = ap.parse_args()
    print("=== westock CLI 取数 %s（%s）===" % (a.what, a.date))
    if a.what in ("sector", "all"):
        fetch_sector(a.date)
    if a.what in ("lhb", "all"):
        fetch_lhb(a.date)
    print("完成。")


if __name__ == "__main__":
    main()
