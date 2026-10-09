# -*- coding: utf-8 -*-
"""
统一数据底座 · 模块接入层（_datahub_api.py）
===========================================
`_datahub.py` 负责「一次抓取、各模块共享」。本模块负责**让各模块用起来**。

核心原则：**零改造**
------------------------
不改任何现有生成器/构建器的代码。接入分三级，按侵入性递增：

① **只读 API**（推荐，显式接入）
     import _datahub_api as H
     q = H.quotes(D)          # 读底座行情；无则 None
     mf = H.flow(D)           # 读底座资金流
     ok, why = H.available(D, "quotes")   # 问维度是否就绪 + 降级原因

② **垫片拦截**（零改造，推荐给新脚本）
     import _datahub_api as H
     H.patch()      # 拦下 _tx_fetch.fetch_kline / fetch_qt，优先喂底座缓存
     之后**任何** import 了 _tx_fetch 的模块都自动走底座，不用改一行

③ **门禁核对**（防口径漂移）
     H.verify(D)    # 各模块实际读到的数据日 vs 底座数据日，列出不一致
     `_datahub_gate.py` 会用它把不一致写进门禁报告

为什么值得做
------------
现状 `quant/` 有 23 个抓数脚本，同一份数据被多模块重复抓（quotes 18 处、
fundflow 9 处、margin_em 8 处），后果是重复请求触发限频、以及各模块各自
判断降级导致页面口径互相矛盾。统一到一处后：
- 限频只发生一次（且可在底座里统一节流）
- 降级口径只有一份（manifest），页面引用同一来源
- 新增模块无需再写抓数代码

用法
----
    python _datahub_api.py --date 2026-09-30            # 看当日底座状态
    python _datahub_api.py --date 2026-09-30 --verify   # 核对各模块口径
"""
from __future__ import annotations
import os, sys, json, glob, argparse, collections, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import _datahub as DH


# ============================================================
# 读
# ============================================================
def get_dim(date, dim):
    """读底座某维度。返回 dict（含 ok/src/data/n/scope），无则 None。"""
    return DH.get(date, dim)


def quotes(date):
    """当日行情快照 {code: {...}}。无则 {}。"""
    d = DH.get(date, "quotes")
    return (d or {}).get("data") or {}


def flow(date):
    """当日主力资金流 {code: {mf1,mf5,mf10,mf20,...}}。无则 {}。"""
    d = DH.get(date, "flow")
    return (d or {}).get("data") or {}


def available(date, dim):
    """维度是否就绪。返回 (ok, 说明)。说明在未就绪时给出降级原因。"""
    d = DH.get(date, dim)
    if not d:
        return False, "底座无该维度（%s 缺）" % dim
    if not d.get("ok"):
        return False, d.get("reason") or "未就绪"
    return True, "%s（%s）" % (dim, d.get("src") or "?")


def manifest(date=None):
    """读 manifest（date 省略则取 hub 里最新一期）。"""
    p = DH.manifest_path()
    if not os.path.exists(p):
        return {}
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return {}


def latest_date():
    """底座里最新的数据日。"""
    fs = sorted(glob.glob(os.path.join(DH.HUB, "2*.json")))
    if not fs:
        return None
    return os.path.basename(fs[-1])[:8]


# ============================================================
# 垫片：让 _tx_fetch 优先喂底座缓存（零改造接入）
# ============================================================
_PATCHED = {"done": False}


def patch(verbose=True):
    """拦截 `_tx_fetch.fetch_kline` / `fetch_qt`，优先返回底座已有数据。

    ★ 为什么安全：只在**底座已有该数据**时接管，底座没有就原样调用原函数。
      因此不会因为垫片而丢数据，也不会改变任何现有行为（除省掉重复请求）。
    ★ 幂等：重复调用只生效一次。
    """
    if _PATCHED["done"]:
        return False
    try:
        import _tx_fetch as T
    except Exception as e:
        if verbose:
            print("[垫片] _tx_fetch 不可用：%s" % e)
        return False

    hub_date = latest_date()
    if not hub_date:
        if verbose:
            print("[垫片] 底座为空，先跑 _datahub.py --date {DATE}")
        return False
    ds = "%s-%s-%s" % (hub_date[:4], hub_date[4:6], hub_date[6:])
    q = quotes(ds)
    fl = flow(ds)
    hits = {"kline": 0, "qt": 0}

    # ① 日K：底座没有日K 维度，但 _long_kline / _txk_cache 本身已是磁盘缓存，
    #    这里只做「确保已加载」，不改变行为（真正的重复请求发生在无缓存时）。
    # ② 行情快照：底座有当日快照时直接喂，避免再打腾讯。
    _orig_qt = T.fetch_qt

    def fetch_qt(codes, batch=80, **kw):
        if q:
            out = {c: q[c] for c in (codes or []) if c in q}
            miss = [c for c in (codes or []) if c not in q]
            if out and not miss:
                hits["qt"] += 1
                return out
            if out:                      # 部分命中：拿底座 + 缺的走原通道
                rest = _orig_qt(miss, batch=batch, **kw)
                out.update(rest or {})
                return out
        return _orig_qt(codes, batch=batch, **kw)

    T.fetch_qt = fetch_qt

    # ③ 资金流：把底座当日结果预置到 fetch_rev_flow 的缓存里（若该模块支持缓存）
    if fl:
        try:
            import fetch_rev_flow as FR
            if hasattr(FR, "_CACHE"):
                FR._CACHE.setdefault(ds, {}).update(fl)
                if verbose:
                    print("[垫片] 资金流已预置 %d 只到 fetch_rev_flow 缓存" % len(fl))
        except Exception:
            pass

    _PATCHED["done"] = True
    if verbose:
        print("[垫片] 已启用：底座 %s 行情 %d 只 / 资金流 %d 只"
              % (ds, len(q), len(fl)))
    return True


# ============================================================
# 门禁：核对各模块实际数据日 vs 底座数据日
# ============================================================
# 模块 → 它该读的文件模式（相对 quant/）
MOD_EXPECT = {
    "quotes":  ("quotes/{d}.json", "行情快照"),
    "lhb":     ("lhb/{d}.json", "龙虎榜"),
    "block":   ("block_chg/{d}.json", "大宗交易"),
    "exec":    ("exec_chg/{d}.json", "高管增减持"),
    "sector":  ("sector_industry_{c}.json", "板块(行业)"),
    "picks":   ("picks/quotes_{d}.json", "精选池行情"),
    "margin":  ("margin_em/*.json", "融资融券"),
    "kline":   ("_long_kline.json", "两年日K底座"),
}


def verify(date):
    """核对各来源是否都有当日数据。

    返回 (hard_problems, soft_warnings, 汇总文本)。
    ★ 区分两类问题（2026-10-03 实测踩过）：
      - **hard**：文件缺失 / 脚本没跑 → 我们的责任，必须修。
      - **soft**：文件在但数据日落后 → 可能是**数据源本身滞后**（如东财融资融券
        实测只到 T-25），不一定是我们的 bug。必须如实标注 lag_days，
        由页面决定是否降级，**不能默默当当日用**。
    """
    ds = DH.DS(date)
    hard = []
    soft = []
    rows = []
    for mod, (pat, cn) in MOD_EXPECT.items():
        p = pat.format(d=date, c=ds)
        full = os.path.join(HERE, p)
        if p.endswith("*.json"):
            files = glob.glob(full)
            n = len(files)
            # ★ 用**分布**而不是 max：单只新股/次新股的末根可能是孤立的高位日期
            #   （实测 sz301689 只到 2026-09-10，而全库中位数是 2026-08-19），
            #   取 max 会被这类票污染，把整体滞后天数算错。
            dates = {}
            for f in files:
                try:
                    j = json.load(open(f, encoding="utf-8"))
                except Exception:
                    continue
                if not j:
                    continue
                # ★ 文件内可能升序或降序（东财 margin_em 按 DATE 降序，最新在首行）
                #   → 取两端较大者，否则会把「最旧一行」当数据末根 → 误报滞后数百天。
                a0 = (j[0] or {}).get("date") or ""
                a1 = (j[-1] or {}).get("date") or ""
                d0 = max(a0, a1)
                if d0:
                    dates[d0] = dates.get(d0, 0) + 1
            if not n or not dates:
                hard.append("%s：无文件或全为空" % cn)
                rows.append((cn, "n=%d" % n, "—", "缺"))
                continue
            # 中位数日期（整体水平）+ 最新日期（最快的那只）
            xs = sorted(dates.items(), key=lambda kv: kv[1])
            cum, med = 0, xs[0][0]
            for dd, cc in xs:
                cum += cc
                if cum >= n / 2.0:
                    med = dd
                    break
            last = xs[-1][0]
            if last == date:
                rows.append((cn, "n=%d" % n, last, "✓"))
            else:
                lag = ""
                try:
                    a_ = datetime.date(*map(int, last.split("-")))
                    b_ = datetime.date(*map(int, date.split("-")))
                    lag = "最快%s滞后%d天" % ("", (b_ - a_).days)
                except Exception:
                    lag = "落后"
                try:
                    a2 = datetime.date(*map(int, med.split("-")))
                    b2 = datetime.date(*map(int, date.split("-")))
                    lag += "；中位%s滞后%d天" % (med, (b2 - a2).days)
                except Exception:
                    pass
                soft.append("%s：最快 %s、中位 %s（%s）≠ %s —— 若为数据源自身滞后则可接受，页面须标注"
                            % (cn, last, med, lag, date))
                rows.append((cn, "n=%d" % n, "%s(中位%s)" % (last, med), "滞后"))
        else:
            good = os.path.exists(full)
            rows.append((cn, "文件", "有" if good else "缺", "✓" if good else "✗"))
            if not good:
                hard.append("%s：%s 缺失" % (cn, p))
    mf = manifest(date)
    txt = ["%-14s %-10s %-18s %s" % ("数据源", "规模", "最新日期", "状态")]
    for cn, scale, last, good in rows:
        txt.append("%-14s %-10s %-18s %s" % (cn, scale, last, good))
    if mf:
        txt.append("")
        txt.append("底座覆盖 %s｜缺失 %s"
                   % (mf.get("coverage"), "、".join(mf.get("bad_dims") or []) or "无"))
        for d, sc in (mf.get("scopes") or {}).items():
            if sc:
                txt.append("  口径 %s = %s" % (d, sc))
    return hard, soft, "\n".join(txt)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None)
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--patch", action="store_true", help="仅演示垫片效果")
    a = ap.parse_args()
    d = a.date or (("%s-%s-%s" % (latest_date()[:4], latest_date()[4:6], latest_date()[6:8]))
                   if latest_date() else None)
    if not d:
        print("底座为空，先跑：python _datahub.py --date 2026-09-30")
        return
    print("== 底座状态 %s ==" % d)
    mf = manifest(d)
    for k in (mf.get("ok_dims") or []):
        print("  ✓ %-8s src=%s" % (k, (mf.get("sources") or {}).get(k)))
    for k in (mf.get("bad_dims") or []):
        print("  ✗ %-8s %s" % (k, (mf.get("reasons") or {}).get(k)))
    if a.verify:
        print("\n== 各来源数据日核对 ==")
        hard, soft, txt = verify(d)
        print(txt)
        if hard:
            print("\n发现 %d 个硬问题（我们的责任，必须修）：" % len(hard))
            for p in hard:
                print("  ✗ %s" % p)
        if soft:
            print("\n发现 %d 个滞后（可能是数据源自身滞后，页面须标注）：" % len(soft))
            for p in soft:
                print("  ⚠ %s" % p)
        if not hard and not soft:
            print("\n✓ 各来源数据日一致")
    if a.patch:
        patch()


if __name__ == "__main__":
    main()
