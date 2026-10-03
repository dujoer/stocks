# -*- coding: utf-8 -*-
"""
统一数据底座 · 历史沉淀（_datahub_archive.py）
==============================================
用户 2026-10-03：「继续」。

背景
----
`_selected_flow_probe.py` 的探查结论（2026-09-30 全市场 4971 只）：
- **1 日主力强度**分档与当日涨幅**单调**（档0 −2.55% → 档4 +2.52%，跨度 5pp），
  且与换手率相关系数仅 **+0.013** → 是真实信息，不是「换手率」的影子。
- **20 日强度不单调**（趋势平）→ 中期资金流没有区分度。

★ 但这里有个**因果倒置**风险，截面数据分不出来：
    「当日涨得多 → 资金自然流入」（同向）≠ 「资金流入 → 未来涨」。
  要区分二者，**必须有连续多日的时间序列**做样本外检验。

所以本脚本解决的是**基础设施问题**：把每天的底座**自动沉淀**下来，
积累 3~6 周后就能做真正的时间序列检验（而不是只能做截面快照）。

沉淀内容（按日切片，体积小、可长期累积）
----------------------------------------
- `hub/hist/{YYYYMMDD}.json`：当日 quotes + flow 的**精简投影**
  （只保留后续因子需要的字段，不存 52 周高低等冗余）
- 每份带 `asof` / `built_at` / `n_domain` / `src`，可追源

为什么要「精简投影」而不是整份拷贝
--------------------------------
整份 `hub/{DATE}.json` 约 1.5MB（含 5207×13 字段），一年 250 天 ≈ 375MB。
精简后只保留 **代码 / 名称 / 收盘 / 涨跌幅 / 换手 / 流通市值 / mf1/mf5/mf20**
约 10 字段，单日约 250KB，一年 ≈ 60MB，可接受。

用法
----
    python _datahub_archive.py --date 2026-09-30     # 沉淀一日
    python _datahub_archive.py --date 2026-09-30 --all-hub   # 沉淀底座里所有日期
    python _datahub_archive.py --list               # 看已沉淀
"""
from __future__ import annotations
import os, sys, json, glob, argparse, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import _datahub as DH

HIST = os.path.join(DH.HUB, "hist")

# 后续因子需要的字段（精简投影）
KEEP_Q = ["name", "last", "change_percent", "turnover_rate", "volume_ratio",
          "circulating_market_cap", "pe_ratio", "pb_ratio", "high_52week"]
KEEP_F = ["mf1", "mf5", "mf10", "mf20"]


def archive(date):
    os.makedirs(HIST, exist_ok=True)
    hub = DH.load_hub(date)
    if not hub:
        print("  ✗ %s 底座缺失，跳过" % date)
        return False
    q = ((hub["dims"].get("quotes") or {}).get("data")) or {}
    f = ((hub["dims"].get("flow") or {}).get("data")) or {}
    if not q:
        print("  ✗ %s 底座无 quotes，跳过" % date)
        return False

    def bad(v):
        nm = (v.get("name") or "").upper()
        return ("ST" in nm) or ("退" in nm)

    out = {}
    for c, v in q.items():
        if bad(v):
            continue
        last = v.get("last") or 0
        turn = v.get("turnover_rate") or 0
        if last < 2.0 or turn <= 0:
            continue
        rec = {k: v.get(k) for k in KEEP_Q}
        rec.update({k: (f.get(c) or {}).get(k) for k in KEEP_F})
        out[c] = rec

    # ★ 逐日资金流序列（2026-10-03）：新浪返回 25 天逐日明细，
    #   底座聚合视图里没有，必须单独落盘，否则跨日无法做「领先/滞后」检验。
    seq_file = (hub["dims"].get("flow") or {}).get("seq_file") or ""
    seq_span = ""
    if seq_file:
        sp = os.path.join(DH.HUB, seq_file)
        if os.path.exists(sp):
            try:
                sj = json.load(open(sp, encoding="utf-8"))
                seq_span = sj.get("span", "")
                # 只保留可分析域的票，控制体积
                sj["data"] = {c: v for c, v in (sj.get("data") or {}).items() if c in out}
                json.dump(sj, open(os.path.join(HIST, "flowseq_%s.json" % DH.DS(date)),
                                   "w", encoding="utf-8"), ensure_ascii=False)
            except Exception:
                seq_span = ""

    p = os.path.join(HIST, "%s.json" % DH.DS(date))
    payload = {
        "asof": date, "built_at": hub.get("built_at"),
        "n_domain": len(out), "n_all": len(q),
        "q_src": (hub["dims"].get("quotes") or {}).get("src", ""),
        "f_src": (hub["dims"].get("flow") or {}).get("src", ""),
        "q_date_check": (hub["dims"].get("quotes") or {}).get("date_check", ""),
        "flow_seq_span": seq_span,
        "data": out,
    }
    json.dump(payload, open(p, "w", encoding="utf-8"), ensure_ascii=False)
    sz = os.path.getsize(p) / 1024.0
    extra = ("｜资金流序列 %s" % seq_span) if seq_span else "｜无序列"
    print("  ✓ %s  域=%d  %.0fKB%s" % (date, len(out), sz, extra))
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="")
    ap.add_argument("--all-hub", action="store_true", help="沉淀底座里所有日期")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()

    if a.list:
        fs = sorted(glob.glob(os.path.join(HIST, "*.json")))
        if not fs:
            print("尚未沉淀任何日期。用 --date {D} 或 --all-hub")
            return
        print("已沉淀 %d 天：" % len(fs))
        dates = []
        for f in fs:
            try:
                j = json.load(open(f, encoding="utf-8"))
                dates.append((j.get("asof"), j.get("n_domain"),
                              os.path.getsize(f) / 1024.0))
            except Exception:
                continue
        for d, n, sz in dates:
            print("  %s  域=%5d  %.0fKB" % (d, n, sz))
        if len(dates) >= 2:
            ds = sorted(x[0] for x in dates if x[0])
            days = (datetime.date(*map(int, ds[-1].split("-")))
                    - datetime.date(*map(int, ds[0].split("-")))).days
            print("  跨度 %d 天（%d 个交易日样本）" % (days, len(ds)))
            if len(ds) < 20:
                print("  ⚠ 样本不足 20 个交易日，时间序列检验需要 ≥40 日才可靠")
        return

    print("== 沉淀历史切片 ==")
    if a.all_hub:
        for p in sorted(glob.glob(os.path.join(DH.HUB, "2*.json"))):
            d = "%s-%s-%s" % (p[-12:-9], p[-9:-7], p[-7:-5])
            archive(d)
    elif a.date:
        archive(a.date)
    else:
        print("用 --date {D} 或 --all-hub")
        return
    print("\n[产物目录] %s" % HIST)


if __name__ == "__main__":
    main()
