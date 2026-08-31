#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
把某一天的板块强度记录固化为每日数据文件，并更新趋势汇总 JSON。

用法:
  python build_sector_daily.py --records sector_strength_data.json --date 2026-08-28

输出:
  quant/sector_daily/<date>.json      当日全量记录 + 摘要(保留,不覆盖)
  quant/sector_trend.json             所有交易日的轻量摘要数组(用于趋势图)

说明:
  westock data_sector 的 date 参数被忽略,只返回最新快照。本脚本按"拉取日期"固化,
  不做任何历史回测/编造。未来每日自动化拉取后调用本脚本即可让趋势自然累积。
"""
import argparse, json, os, datetime

ROOT = os.path.dirname(os.path.abspath(__file__))
DAILY_DIR = os.path.join(ROOT, "sector_daily")
TREND_PATH = os.path.join(ROOT, "sector_trend.json")


def behavior_of(s):
    if s >= 3:
        return "抢筹"
    if s >= 1:
        return "建仓"
    if s >= -1:
        return "洗盘"
    return "出货"


def rank_of(b):
    return {"抢筹": 4, "建仓": 3, "洗盘": 2, "出货": 1}.get(b, 0)


def build(records, date_str):
    total_dark = 0.0          # 元
    total_turnover = 0.0     # 元
    up = down = flat = 0
    beh = {"抢筹": 0, "建仓": 0, "洗盘": 0, "出货": 0}
    strengths = []
    for r in records:
        s = float(r.get("strengthVal", 0) or 0)
        dark = float(r.get("darkVal", 0) or 0)
        turn = float(r.get("totalVal", 0) or 0)
        pct = float(r.get("pctVal", 0) or 0)
        total_dark += dark
        total_turnover += turn
        strengths.append(s)
        b = behavior_of(s)
        beh[b] += 1
        if pct > 0:
            up += 1
        elif pct < 0:
            down += 1
        else:
            flat += 1
    avg_strength = sum(strengths) / len(strengths) if strengths else 0
    n = len(records)
    industry_n = sum(1 for r in records if r.get("kind") == "行业")
    concept_n = n - industry_n

    # 排序辅助
    by_strength = sorted(records, key=lambda r: float(r.get("strengthVal", 0) or 0), reverse=True)
    by_dark = sorted(records, key=lambda r: float(r.get("darkVal", 0) or 0), reverse=True)

    def slim(rows, key, k=12):
        out = []
        for r in rows[:k]:
            out.append({
                "name": r.get("name"),
                "kind": r.get("kind"),
                "strength": round(float(r.get("strengthVal", 0) or 0), 2),
                "darkY": round(float(r.get("darkVal", 0) or 0) / 1e8, 2),  # 亿元
                "pct": round(float(r.get("pctVal", 0) or 0), 2),
                "behavior": behavior_of(float(r.get("strengthVal", 0) or 0)),
            })
        return out

    summary = {
        "sectorCount": n,
        "industryCount": industry_n,
        "conceptCount": concept_n,
        "totalDarkY": round(total_dark / 1e8, 1),       # 全市场暗盘资金净额(亿元)
        "totalTurnoverY": round(total_turnover / 1e8, 1),
        "avgStrength": round(avg_strength, 3),
        "upCount": up,
        "downCount": down,
        "flatCount": flat,
        "upRatio": round(up / n * 100, 1) if n else 0,
        "behavior": beh,
        "topByStrength": slim(by_strength, "strengthVal"),
        "topDarkMoney": slim(by_dark, "darkVal"),
    }

    daily = {
        "date": date_str,
        "pulledAt": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "source": "westock data_sector (latest snapshot; date param ignored)",
        "summary": summary,
        "records": records,
    }
    return daily, summary


def update_trend(date_str, summary):
    os.makedirs(DAILY_DIR, exist_ok=True)
    trend = []
    if os.path.exists(TREND_PATH):
        try:
            trend = json.load(open(TREND_PATH, encoding="utf-8"))
        except Exception:
            trend = []
    trend = [t for t in trend if t.get("date") != date_str]
    trend.append({
        "date": date_str,
        "totalDarkY": summary["totalDarkY"],
        "avgStrength": summary["avgStrength"],
        "upCount": summary["upCount"],
        "downCount": summary["downCount"],
        "upRatio": summary["upRatio"],
        "qiangchou": summary["behavior"]["抢筹"],
        "jiancang": summary["behavior"]["建仓"],
        "xipan": summary["behavior"]["洗盘"],
        "chuhuo": summary["behavior"]["出货"],
        "sectorCount": summary["sectorCount"],
    })
    trend.sort(key=lambda t: t["date"])
    json.dump(trend, open(TREND_PATH, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    return trend


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--records", required=True, help="板块强度全量记录 JSON")
    ap.add_argument("--date", required=True, help="拉取日期 YYYY-MM-DD")
    ap.add_argument("--out", default=None, help="每日数据文件输出路径(默认 sector_daily/<date>.json)")
    args = ap.parse_args()

    records = json.load(open(args.records, encoding="utf-8"))
    daily, summary = build(records, args.date)
    os.makedirs(DAILY_DIR, exist_ok=True)
    out_path = args.out or os.path.join(DAILY_DIR, args.date + ".json")
    json.dump(daily, open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    trend = update_trend(args.date, summary)
    print(f"[ok] 每日数据 -> {out_path}")
    print(f"[ok] 趋势汇总 -> {TREND_PATH} (共 {len(trend)} 个交易日)")
    print(f"     板块 {summary['sectorCount']} | 暗盘净额 {summary['totalDarkY']}亿 | "
          f"均强 {summary['avgStrength']} | 抢筹 {summary['behavior']['抢筹']} / 出货 {summary['behavior']['出货']} | 涨 {summary['upCount']} 跌 {summary['downCount']}")


if __name__ == "__main__":
    main()
