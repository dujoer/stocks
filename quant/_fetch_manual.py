# -*- coding: utf-8 -*-
"""取当日「manual」原始数据（龙虎榜 / 大宗 / 高管 / 板块强度），不依赖 westock MCP。

为什么需要它：daily_all 的 ①②③④⑤ 步（lhb/exec/block/sector）原本标为 MANUAL，
只检「原始文件在不在盘上」、不在就跳过，等 agent 经 westock MCP 实拉。
但 westock MCP 长期 502（mcp.json 未配置），导致每天要靠手动降级补齐。

本脚本把 proven 的降级路径固化为主路径，让 daily_all 一条命令跑完：
  · 板块强度 sector ： westock CLI（与 MCP 同源同口径，一条命令落盘）
  · 龙虎榜 lhb 主榜 ： westock CLI
  · 龙虎榜席位明细   ： 东财 _fetch_lhb_detail_em.py（东财无游资标签 → 页内诚实标「不可判」）
  · 大宗 block       ： 东财 _fetch_block_exec_em.py --only block
  · 高管 exec        ： 东财 _fetch_block_exec_em.py --only exec

幂等：目标文件已存在则跳过（不重复拉、不覆盖）。
逐源报告成败；任一源失败 → 退出码非 0（让 daily_all 该步失败、不拿旧数据凑）。

注意：本脚本需联网（沙箱外执行），调用方应在 dangerouslyDisableSandbox 下运行。
"""
from __future__ import annotations
import os, sys, argparse, subprocess

Q = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable


def _run(cmd: str) -> bool:
    print("  $ %s" % cmd)
    r = subprocess.run([PY] + cmd.split(), cwd=Q)
    return r.returncode == 0


def _present(path: str) -> bool:
    return os.path.exists(os.path.join(Q, path))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True, help="数据日期 YYYY-MM-DD")
    a = ap.parse_args()
    D = a.date
    DS = D.replace("-", "")
    print("=== 补齐 manual 原始数据（不依赖 westock MCP）：%s ===" % D)

    results = []  # (name, ok)

    # ① 板块强度：westock CLI（industry + concept）
    ind = "sector_industry_%s.json" % DS
    con = "sector_concept_%s.json" % DS
    if _present(ind) and _present(con):
        print("[sector] 已存在，跳过")
        results.append(("sector", True))
    else:
        ok = _run("_westock_cli_fetch.py sector --date %s" % D)
        results.append(("sector", ok))

    # ② 龙虎榜主榜：westock CLI
    lhb_main = os.path.join("lhb", "%s.json" % D)
    if _present(lhb_main):
        print("[lhb] 主榜已存在，跳过")
        results.append(("lhb", True))
    else:
        ok = _run("_westock_cli_fetch.py lhb --date %s" % D)
        results.append(("lhb", ok))

    # ③ 龙虎榜席位明细：东财（无游资标签，页内诚实标「不可判」）
    lhb_detail = os.path.join("lhb_detail", "%s_batch1.json" % D)
    if _present(lhb_detail):
        print("[lhb_detail] 已存在，跳过")
        results.append(("lhb_detail", True))
    else:
        ok = _run("_fetch_lhb_detail_em.py --date %s" % D)
        results.append(("lhb_detail", ok))

    # ④ 大宗交易：东财
    block_raw = os.path.join("block_chg", "_raw_em_%s.json" % D)
    if _present(block_raw):
        print("[block] 已存在，跳过")
        results.append(("block", True))
    else:
        ok = _run("_fetch_block_exec_em.py --date %s --only block" % D)
        results.append(("block", ok))

    # ⑤ 高管增减持：东财
    exec_raw = os.path.join("exec_chg", "_raw_em_%s.json" % D)
    if _present(exec_raw):
        print("[exec] 已存在，跳过")
        results.append(("exec", True))
    else:
        ok = _run("_fetch_block_exec_em.py --date %s --only exec" % D)
        results.append(("exec", ok))

    print("\n=== 取数结果 ===")
    all_ok = True
    for name, ok in results:
        print("  %-12s %s" % (name, "OK" if ok else "✗ FAIL"))
        all_ok = all_ok and ok
    if not all_ok:
        print("部分源失败 → 退出码 1（daily_all 该步会失败，不拿旧数据凑）")
        sys.exit(1)
    print("全部成功")


if __name__ == "__main__":
    main()
