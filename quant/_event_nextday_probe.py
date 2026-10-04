# -*- coding: utf-8 -*-
"""实测：「T 日可观测事件 → T+1 收益」到底有没有胜率。

动机（用户问「提前一天拿新闻、第二天大概率涨」）：
  严格「提前确知」= 内幕信息。可测的合法代理是「T 日盘后已公开、且市场已强烈反应」
  的最强信号 —— **涨停**。若连涨停都不能保证次日上涨，更弱的新闻（媒体滞后、
  无个股映射）更不可能。

口径：
  T 日涨停名单 = quant/limitup/{D}.json 的 data.stocks（含 LimitUpDays 连板数）
  T+1 收益     = quant/tplus/quotes_{T+1}.json[code].change_percent（相对前收盘）
  覆盖限制：tplus 报价只有 1100~1600 只（做T域有流动性门槛），
            不在域内的涨停股查不到 → 样本有「流动性偏好」偏差，如实标注。

输出：quant/_event_nextday_probe.json
"""
from __future__ import annotations
import json, os, glob, re, statistics
from collections import defaultdict

QUANT = os.path.dirname(os.path.abspath(__file__))


def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


TRADING_CAL_SRC = ("market_overview/2026-*.json", "limitup/2026-*.json",
                   "tplus/quotes_2026-*.json")


def trading_days():
    """交易日历：取多源文件名日期并集（单源都有缺失，并集最接近真实日历）。"""
    ds = set()
    for pat in TRADING_CAL_SRC:
        for f in glob.glob(os.path.join(QUANT, pat)):
            m = re.search(r"(\d{4}-\d{2}-\d{2})", os.path.basename(f))
            if m:
                ds.add(m.group(1))
    return sorted(ds)


TCAL = trading_days()


def next_quote_date(d):
    """D 的真实下一交易日，且该日有 tplus 报价；否则 None（避免拿 3 周后的价格冒充次日）。"""
    later = [x for x in TCAL if x > d]
    if not later:
        return None
    nd = later[0]
    have_q = os.path.exists(os.path.join(QUANT, "tplus", "quotes_%s.json" % nd))
    return nd if have_q else None


def main():
    obs = []                      # (date, code, limit_up_days, next_chg)
    for f in sorted(glob.glob(os.path.join(QUANT, "limitup", "2026-*.json"))):
        m = re.search(r"(\d{4}-\d{2}-\d{2})", os.path.basename(f))
        if not m:
            continue
        d = m.group(1)
        nd = next_quote_date(d)
        if not nd:
            continue
        q = load(os.path.join(QUANT, "tplus", "quotes_%s.json" % nd))
        j = load(f)
        for s in (j.get("data") or {}).get("stocks") or []:
            code = s.get("code")
            if code not in q:
                continue
            cp = (q[code] or {}).get("change_percent")
            if cp is None:
                continue
            obs.append({"date": d, "next_date": nd, "code": code,
                        "lud": int(s.get("LimitUpDays") or 1),
                        "next_chg": float(cp)})

    if not obs:
        print("[probe] 无可用观测")
        return

    rets = [o["next_chg"] for o in obs]
    win = sum(1 for r in rets if r > 0)

    # ★ 口径修正一：剔除「次日封板」样本 —— 那部分 T+1 开盘买不进，收益不可得
    SEAL = 9.5
    tradable = [o for o in obs if o["next_chg"] < SEAL]
    t_rets = [o["next_chg"] for o in tradable]

    # ★ 口径修正二：等量对照 —— 同日**非涨停**股在 T+1 的收益（同一批对照股票池）
    ctrl_ret = []
    per_day = {}
    for d, nd in sorted({(o["date"], o["next_date"]) for o in obs}):
        qn = load(os.path.join(QUANT, "tplus", "quotes_%s.json" % nd))
        lu = {o["code"] for o in obs if o["date"] == d}
        vals = [float((qn[c] or {}).get("change_percent"))
                for c in qn if c not in lu and (qn.get(c) or {}).get("change_percent") is not None]
        vals_t = [v for v in vals if v < SEAL]        # 对照也剔封板，口径对齐
        per_day[d] = {"ctrl_n": len(vals_t),
                      "ctrl_mean": round(statistics.mean(vals_t), 3) if vals_t else None}
        ctrl_ret.extend(vals_t)

    # 分布桶
    buckets = [(-99, -5, "<-5%"), (-5, 0, "-5~0%"), (0, 3, "0~+3%"),
               (3, 5.5, "+3~+5.5%"), (5.5, 9.5, "+5.5~+9.5%"), (9.5, 99, "≥+9.5%（≈封板）")]
    dist = []
    for lo, hi, lab in buckets:
        c = sum(1 for r in rets if lo <= r < hi)
        dist.append({"label": lab, "n": c, "pct": round(100.0 * c / len(rets), 1)})

    # 按连板数分层
    by_lud = defaultdict(list)
    for o in obs:
        k = "首板" if o["lud"] <= 1 else ("%d连板" % o["lud"] if o["lud"] <= 3 else "4板及以上")
        by_lud[k].append(o["next_chg"])
    tiers = []
    for k in ("首板", "2连板", "3连板", "4板及以上"):
        v = by_lud.get(k) or []
        if not v:
            continue
        tiers.append({"tier": k, "n": len(v),
                      "win_rate": round(100.0 * sum(1 for x in v if x > 0) / len(v), 1),
                      "mean": round(statistics.mean(v), 2),
                      "median": round(statistics.median(v), 2)})

    # 按日
    by_day = defaultdict(list)
    for o in obs:
        by_day[o["date"]].append(o["next_chg"])
    days = []
    for d in sorted(by_day):
        v = by_day[d]
        nd = next(o["next_date"] for o in obs if o["date"] == d)
        days.append({"date": d, "next_date": nd, "n": len(v),
                     "win_rate": round(100.0 * sum(1 for x in v if x > 0) / len(v), 1),
                     "mean": round(statistics.mean(v), 2),
                     "median": round(statistics.median(v), 2)})

    res = {
        "_doc": "涨停（T 日最强公开事件）→ T+1 收益实测",
        "n_obs": len(obs), "n_days": len(by_day),
        "win_rate": round(100.0 * win / len(obs), 1),
        "mean": round(statistics.mean(rets), 2),
        "median": round(statistics.median(rets), 2),
        "best": round(max(rets), 2), "worst": round(min(rets), 2),
        "dist": dist, "tiers": tiers, "days": days,
        "tradable": {
            "note": "剔除次日 ≥+9.5%%（≈封板，T+1 开盘买不进）后的口径",
            "n": len(t_rets),
            "win_rate": round(100.0 * sum(1 for x in t_rets if x > 0) / max(1, len(t_rets)), 1),
            "mean": round(statistics.mean(t_rets), 2) if t_rets else None,
            "median": round(statistics.median(t_rets), 2) if t_rets else None,
        },
        "ctrl_nonlimit": {
            "note": "等量对照：同日非涨停股在 T+1 的收益（同样剔除 ≥+9.5%%）",
            "n": len(ctrl_ret),
            "win_rate": round(100.0 * sum(1 for x in ctrl_ret if x > 0) / max(1, len(ctrl_ret)), 1),
            "mean": round(statistics.mean(ctrl_ret), 2) if ctrl_ret else None,
        },
        "edge_vs_ctrl_pp": round(statistics.mean(t_rets) - statistics.mean(ctrl_ret), 2)
        if t_rets and ctrl_ret else None,
        "caveat": "样本仅 %d 个交易日（按日 block 不足，不做 bootstrap）；tplus 报价域"
                  "1100~1600 只（有流动性门槛），不在域内的涨停股查不到，样本偏流动性好的票；"
                  "limitup 部分期次被截断到前 20 名（按连板数降序）→ 偏向高连板，会**高估**表现。"
                  % len(by_day),
    }
    with open(os.path.join(QUANT, "_event_nextday_probe.json"), "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)

    print("[probe] 观测 %d 个（%d 个交易日）" % (res["n_obs"], res["n_days"]))
    print("[probe] ① 全样本（含买不进的）：上涨率 %.1f%%  均值 %+.2f%%  中位数 %+.2f%%"
          % (res["win_rate"], res["mean"], res["median"]))
    t = res["tradable"]
    print("[probe] ② 剔封板（T+1 开盘能买）：n=%d  上涨率 %.1f%%  均值 %+.2f%%  中位数 %+.2f%%"
          % (t["n"], t["win_rate"], t["mean"], t["median"]))
    c = res["ctrl_nonlimit"]
    print("[probe] ③ 等量对照（同日非涨停）：n=%d  上涨率 %.1f%%  均值 %+.2f%%"
          % (c["n"], c["win_rate"], c["mean"]))
    print("[probe] ★ 涨停 vs 对照 超额 = %+.2fpp" % (res["edge_vs_ctrl_pp"] or 0))
    print("[probe] 次日收益分布：")
    for d in dist:
        print("        %-16s %5d  %5.1f%%" % (d["label"], d["n"], d["pct"]))
    print("[probe] 按连板数：")
    for t2 in tiers:
        print("        %-8s n=%4d  上涨率 %5.1f%%  均值 %+6.2f%%  中位数 %+6.2f%%"
              % (t2["tier"], t2["n"], t2["win_rate"], t2["mean"], t2["median"]))
    print("[probe] 按日（涨停组 vs 同日非涨停对照）：")
    for d in days:
        pd = per_day.get(d["date"], {})
        print("        %s → %s  涨停 n=%3d 上涨率 %5.1f%% 均值 %+6.2f%% | 对照 n=%4d 均值 %s"
              % (d["date"], d["next_date"], d["n"], d["win_rate"], d["mean"],
                 pd.get("ctrl_n", 0),
                 ("%+.2f%%" % pd["ctrl_mean"]) if pd.get("ctrl_mean") is not None else "—"))


if __name__ == "__main__":
    main()
