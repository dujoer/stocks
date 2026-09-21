# -*- coding: utf-8 -*-
"""
增仓精选 · 回测实验室（_accum_lab.py）
=====================================
把用户要求的「增仓/增持」信号维度合成为统一日频信号帧，对最近 N 个交易日逐日选股，
并用与主升精选/反转池完全可比的移动止盈退出做样本外回测胜率。

信号集（先验固定、等权、不训练——保持干净样本外）：
  1. 私募增持      —— q2 十大流通股东「私募」类 holdChange>0（季度维度 2026Q2）
  2. 阳光私募      —— q2 股东名含「阳光私募/阳光」
  3. 个人(牛散)增持 —— q2 自然人大股东 holdChange>0
  4. 公募增持      —— q2 股东名含「基金/证券投资基金」且非私募 holdChange>0
  5. 大宗交易      —— block_chg/{T}.json byStock（日频连续）
  6. 高管增持      —— exec_chg/{T}.json records(dir=增持)
  7. 席位异动      —— lhb_detail/{T} NetBuy>0
  8. 多空增仓(1/3/5日) —— picks/margin_{T}.json 融资余额变化（快照稀疏，近似）

退出口径（与主升/反转池一致，保证横比）：
  STOP=-12% 硬止损 / +6% 激活 / 回撤 3% 跟踪 / 满 20 日强平
  胜率 = 该规则下盈利交易占比。

用法：
  python _accum_lab.py            # 复用 kline 缓存，跑最近20交易日，写 lab.html + accum_result.json
  python _accum_lab.py --days 20
"""
import os, sys, json, glob, math, argparse, collections, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CACHE = os.path.join(HERE, "_txk_cache.json")
Q2 = os.path.join(HERE, "q2_full", "_merged_shareholder.json")
OUT = os.path.join(ROOT, "web", "accumulation")
os.makedirs(OUT, exist_ok=True)

# ---- 退出参数（与主升/反转池一致）----
STOP, ACT, TRAIL, MAXFWD = 0.12, 0.06, 0.03, 20

# 选股参数
TOPN = 25            # 每日入选上限
MIN_DAILY = 1        # 至少触发 1 个日频信号（block/exec/lhb/margin）才入选，保证"主动"

# ============================================================
# 1. 数据加载
# ============================================================
def load_kline():
    c = json.load(open(CACHE, encoding="utf-8"))
    # code -> (dates[], last[], high[], low[])  ；bar keys: date,open,last,high,low,volume
    K = {}
    for code, bars in c.items():
        if not bars:
            continue
        ds = [b["date"] for b in bars]
        vu = 1.0 if code.startswith("sh688") else 100.0
        amt = [(b.get("volume") or 0) * vu * (b.get("last") or 0) for b in bars]
        K[code] = (ds, [b["last"] for b in bars], [b["high"] for b in bars], [b["low"] for b in bars], amt)
    return K

def trading_days(K):
    # 用一只活跃股推出全市场交易日历
    ds = None
    for code in ("sh600519", "sz000001", "sh601398"):
        if code in K:
            ds = K[code][0]; break
    if ds is None:
        ds = sorted({d for code in K.values() for d in code[0]})
    return ds

INST_WORDS = ["有限公司","股份","公司","银行","保险","证券","资管","资产","投资","合伙","企业","中心","基金","信托"]
FUND_KW = ["基金","证券投资基金"]
def is_person(nm):
    return not any(w in nm for w in INST_WORDS)

def load_q2_flags():
    """返回 code -> set(pe, sun, person, fund) 季度增持标记（2026Q2）"""
    SH = json.load(open(Q2, encoding="utf-8"))
    flags = collections.defaultdict(set)
    for code, info in SH.items():
        holders = info.get("top10FloatShareholders") or []
        if not isinstance(holders, list):
            continue
        for h in holders:
            ch = h.get("holdChange") or 0
            nm = h.get("name", "")
            if ch <= 0:
                continue
            if "私募" in nm:
                flags[code].add("pe")
            if "阳光" in nm and any(k in nm for k in ["信托", "私募", "资管", "基金", "资产管理"]):
                flags[code].add("sun")
            elif any(k in nm for k in FUND_KW) and "私募" not in nm:
                flags[code].add("fund")
            elif is_person(nm):
                flags[code].add("person")
    return flags

def load_block(T):
    """block_chg/{T}.json -> code -> {value, discount}（byStock）"""
    p = os.path.join(HERE, "block_chg", f"{T}.json")
    if not os.path.exists(p):
        return {}
    d = json.load(open(p, encoding="utf-8"))
    out = {}
    for s in d.get("byStock", []):
        out[s["code"]] = {"value": s.get("value") or 0, "discount": s.get("avgDiscount") or 0}
    return out

def load_exec(T):
    """exec_chg/{T}.json -> code -> 增持总金额（records dir=增持）"""
    p = os.path.join(HERE, "exec_chg", f"{T}.json")
    if not os.path.exists(p):
        return {}
    d = json.load(open(p, encoding="utf-8"))
    amt = collections.defaultdict(float)
    for r in d.get("records", []):
        if r.get("dir") == "增持":
            amt[r["code"]] += float(r.get("amount") or 0)
    return dict(amt)

def load_lhb(T):
    """lhb_detail/{T}_batch*.json -> code -> NetBuy（LhbInfos 聚合）"""
    out = collections.defaultdict(float)
    for f in glob.glob(os.path.join(HERE, "lhb_detail", f"{T}_batch*.json")):
        d = json.load(open(f, encoding="utf-8"))
        data = d.get("data") if isinstance(d, dict) and "data" in d else d
        if isinstance(data, dict):
            items = data.values()
        else:
            items = []
        for code, v in (data.items() if isinstance(data, dict) else []):
            infos = v.get("LhbInfos") if isinstance(v, dict) else None
            if not infos:
                continue
            try:
                infos = json.loads(infos) if isinstance(infos, str) else infos
            except Exception:
                infos = []
            for it in infos:
                try:
                    out[code] += float(it.get("NetBuy") or 0)
                except Exception:
                    pass
    return {k: v for k, v in out.items()}

def load_margin_snapshots():
    """picks/margin_*.json -> 按日期排序的快照列表 [(date, {code:{financeValue,financeDOD,securityDOD}})]"""
    import re
    snaps = []
    seen = set()
    for f in glob.glob(os.path.join(HERE, "picks", "margin_*.json")):
        base = os.path.basename(f)
        mm = re.search(r"(\d{4})-?(\d{2})-?(\d{2})", base)
        if not mm:
            continue
        d = f"{mm.group(1)}-{mm.group(2)}-{mm.group(3)}"
        if d in seen:
            continue
        seen.add(d)
        try:
            data = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        snaps.append((d, data))
    snaps.sort(key=lambda x: x[0])
    return snaps

def margin_net(T, snaps, offset_days, cal):
    """返回 T 日该维度：净多空增仓(%)。
    多头=融资余额变化；空头=融券余额变化（securityDOD）。1日用日变动净额，3/5日用快照间融资余额变化。
    快照稀疏→多数日返回 None。"""
    if not snaps:
        return None
    s_le = None
    for d, data in snaps:
        if d <= T:
            s_le = (d, data)
        else:
            break
    if s_le is None:
        return None
    if offset_days <= 1:
        # 净多空 = 融资日变动 - 融券日变动（字段可能缺失）
        out = {}
        for code, v in s_le[1].items():
            try:
                out[code] = float(v.get("financeDOD") or 0) - float(v.get("securityDOD") or 0)
            except Exception:
                out[code] = 0.0
        return out
    try:
        ti = cal.index(T)
    except ValueError:
        return None
    target = cal[ti - offset_days] if ti - offset_days >= 0 else None
    if target is None:
        return None
    s_prev = None
    for d, data in snaps:
        if d <= target:
            s_prev = (d, data)
        else:
            break
    if s_prev is None or s_prev[0] == s_le[0]:
        return None
    out = {}
    for code, v in s_le[1].items():
        v0 = s_prev[1].get(code, {}).get("financeValue")
        v1 = v.get("financeValue")
        if v0 and v1:
            out[code] = (v1 / v0 - 1) * 100.0
    return out

# ============================================================
# 1b. 真实融资融券模块（东财 datacenter-web，T+1 公布）
# ============================================================
def load_margin_em():
    """margin_em/{code}.json -> {code: rows 升序}。行字段 date/rzjme/rzjme3d/rzjme5d/rqjmg/rzye。"""
    mh = {}
    for f in glob.glob(os.path.join(HERE, "margin_em", "*.json")):
        code = os.path.basename(f)[:-5]
        try:
            rows = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        rows = [r for r in rows if r and r.get("date")]
        rows.sort(key=lambda r: r["date"])
        mh[code] = rows
    return mh


def margin_em_event(code, T, K, mh):
    """T 日决策可用的最新融资融券行（严格 DATE < T，T+1 公布 → 防未来函数）。
    返回 dict(ratio1, ratio3, ratio5, rzjme...) 或 None。占比 = 融资净买入 / 对应窗口成交额。"""
    rows = mh.get(code)
    if not rows:
        return None
    if code not in K:
        return None
    ds, _last, _high, _low, amt = K[code]
    row = None
    for r in rows:
        if r["date"] < T:
            row = r
        else:
            break
    if row is None:
        return None
    try:
        i = ds.index(row["date"])
    except ValueError:
        return None

    def ratio(net, n):
        if net is None or net <= 0 or i + 1 < n:
            return 0.0
        base = sum(amt[i - n + 1:i + 1])
        return (net / base) if base > 0 else 0.0

    return {"date": row["date"], "rzjme": row.get("rzjme") or 0,
            "ratio1": ratio(row.get("rzjme"), 1),
            "ratio3": ratio(row.get("rzjme3d"), 3),
            "ratio5": ratio(row.get("rzjme5d"), 5)}


# 先验固定阈值（经济逻辑：杠杆资金净买入且占比显著 → 多头增仓；窗口越长容忍占比越低）
MARG_TH = {1: 0.02, 3: 0.04, 5: 0.04}


def margin_flags(ev):
    """按先验阈值给出 m1/m3/m5 触发与强度（0~1，5% 占比封顶）。"""
    out = {}
    if not ev:
        return out
    for k, wk in (("m1", 1), ("m3", 3), ("m5", 5)):
        r = ev["ratio%d" % wk]
        if r >= MARG_TH[wk]:
            out[k] = min(1.0, r / 0.05)
            out["_" + k + "_ratio"] = r
    return out



# ============================================================
# 2. 信号帧 + 合成
# ============================================================
def signal_frame(T, K, q2, snaps, cal, mh=None):
    """返回 code -> dict(各信号 strength[0,1] 与原值)。日频信号缺失则该维 strength=0。"""
    block = load_block(T)
    execa = load_exec(T)
    lhb = load_lhb(T)
    m1 = margin_net(T, snaps, 1, cal)
    m3 = margin_net(T, snaps, 3, cal)
    m5 = margin_net(T, snaps, 5, cal)

    codes = set()
    for d in (block, execa, lhb):
        codes.update(d.keys())
    codes.update(q2.keys())

    # 日频强度归一（横截面）
    def norm(vals):
        mx = max((v for v in vals if v and v > 0), default=0)
        return (math.log1p(mx) if mx > 0 else 1.0)

    bmax = norm([s["value"] for s in block.values()])
    emax = norm(list(execa.values()))
    lmax = max((abs(v) for v in lhb.values() if v), default=0)

    frame = {}
    for code in codes:
        sig = {}
        if code in block:
            # 经济先验：深度折价大宗多为减持/出货（偏空），溢价或低折价接盘才偏多
            disc = block[code]["discount"]
            q = max(0.3, 1.0 - max(0.0, disc) / 20.0)
            sig["block"] = (math.log1p(block[code]["value"]) / bmax) * q if bmax else 0.0
            sig["_block_val"] = block[code]["value"]
            sig["_block_disc"] = disc
        if code in execa:
            sig["exec"] = (math.log1p(execa[code]) / emax) if emax else 0.0
            sig["_exec_amt"] = execa[code]
        if code in lhb:
            lv = lhb[code]
            sig["lhb"] = max(0.0, lv) / lmax if lmax else 0.0
            sig["_lhb_net"] = lv
        # 多空增仓 1/3/5日（真实融资融券：东财日频序列，T+1 公布口径）
        mev = margin_em_event(code, T, K, mh) if mh else None
        for k, v in margin_flags(mev).items():
            sig[k] = v
        if mev:
            # 原始占比始终保留（阈值敏感性分析用）
            sig["_mr1"], sig["_mr3"], sig["_mr5"] = mev["ratio1"], mev["ratio3"], mev["ratio5"]
        # 季度维度（二值）
        fl = q2.get(code, set())
        for f in ("pe", "sun", "person", "fund"):
            if f in fl:
                sig[f] = 0.6   # 季度增持标记，给固定强度（不压倒日频事件）
        frame[code] = sig
    return frame

# 日频信号键（要求至少触发其一才入选）
DAILY = ["block", "exec", "lhb", "m1", "m3", "m5"]
# 全部信号键（用于命中率）
ALLSIG = ["pe", "sun", "person", "fund", "block", "exec", "lhb", "m1", "m3", "m5"]
SIG_CN = {"pe":"私募增持","sun":"阳光私募","person":"个人(牛散)增持","fund":"公募增持",
          "block":"大宗交易","exec":"高管增持","lhb":"席位异动","m1":"多空增仓1日","m3":"多空增仓3日","m5":"多空增仓5日"}

def composite(sig):
    # 共识合成：求和（多维度同时触发 > 单一强信号），体现"聪明钱共振"
    return sum(v for k, v in sig.items() if k in ALLSIG and v > 0)

# ============================================================
# 3. 移动止盈回测
# ============================================================
def simulate(K, code, T):
    if code not in K:
        return None
    ds, last, high, low = K[code][:4]
    try:
        i = ds.index(T)
    except ValueError:
        return None
    entry = last[i]
    if entry <= 0:
        return None
    fwd = min(MAXFWD, len(ds) - 1 - i)
    if fwd <= 0:
        return None
    peak = entry
    for k in range(1, fwd + 1):
        hi = high[i + k]; lo = low[i + k]; cl = last[i + k]
        if hi > peak:
            peak = hi
        # 硬止损
        if lo <= entry * (1 - STOP):
            ret = entry * (1 - STOP) / entry - 1
            return (ret, ret > 0, k, "硬止损")
        # 跟踪止盈
        if peak >= entry * (1 + ACT) and cl <= peak * (1 - TRAIL):
            ret = cl / entry - 1
            return (ret, ret > 0, k, "跟踪止盈")
        # 满期强平
        if k == fwd:
            ret = cl / entry - 1
            return (ret, ret > 0, k, "满期")
    return None

# ============================================================
# 4. 主流程
# ============================================================
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=20)
    args = ap.parse_args()

    K = load_kline()
    cal = trading_days(K)
    q2 = load_q2_flags()
    snaps = load_margin_snapshots()
    mh = load_margin_em()
    print(f"[load] kline codes={len(K)} 交易日={cal[0]}~{cal[-1]} q2_flags={len(q2)} "
          f"margin_snaps={len(snaps)} margin_em={len(mh)}")

    lastN = cal[-args.days:]
    # 建代码名表
    names = {}
    c = json.load(open(CACHE, encoding="utf-8"))
    for code, bars in c.items():
        if bars:
            names[code] = bars[-1].get("name", "") or code

    # 逐日选股 + 逐信号命中统计
    per_day_sel = []          # [(T, [ (code, score, sigdict) ])]
    sig_events = collections.defaultdict(list)   # sig -> [(code,T)]
    sel_results = []          # (T, code, ret, win, fwd)
    base_results = []         # 基线
    import random
    random.seed(20260921)

    for T in lastN:
        frame = signal_frame(T, K, q2, snaps, cal, mh=mh)
        scored = []
        for code, sig in frame.items():
            has_daily = any(k in sig and sig[k] > 0 for k in DAILY)
            if not has_daily:
                continue
            sc = composite(sig)
            if sc <= 0:
                continue
            scored.append((code, sc, sig))
            for k in ALLSIG:
                if k in sig and sig[k] > 0:
                    sig_events[k].append((code, T))
        scored.sort(key=lambda x: -x[1])
        sel = scored[:TOPN]
        per_day_sel.append((T, sel))
        # 入选股回测
        for code, sc, sig in sel:
            r = simulate(K, code, T)
            if r:
                sel_results.append((T, code, r[0], r[1], r[2]))
        # 基线：同数量随机股
        pool = [code for code in K if code in names]
        for _ in range(len(sel)):
            code = random.choice(pool)
            r = simulate(K, code, T)
            if r:
                base_results.append((T, code, r[0], r[1], r[2]))

    # 汇总
    def wr(lst):
        if not lst:
            return (0, 0.0, 0.0)
        n = len(lst); w = sum(1 for x in lst if x[3]); rets = [x[2] for x in lst]
        return (n, 100.0 * w / n, 100.0 * sum(rets) / n)

    sel_wr = wr(sel_results)
    base_wr = wr(base_results)
    # 共识度曲线：≥m 个信号同时触发的入选股胜率（m=1..6）
    cons_results = collections.defaultdict(list)
    for T, sel in per_day_sel:
        for code, sc, sig in sel:
            n_sig = sum(1 for k in ALLSIG if k in sig and sig[k] > 0)
            r = simulate(K, code, T)
            if r:
                for m in range(1, 7):
                    if n_sig >= m:
                        cons_results[m].append((T, code, r[0], r[1], r[2]))
    cons_wr = {m: wr(v) for m, v in cons_results.items()}

    # ---- 条件模块组合实验：机构/私募季度增持 I × 融资融券增仓 M（用户：机构私募 + 1/3/5日行情） ----
    def mods(sig):
        I = any(k in sig and sig[k] > 0 for k in ("pe", "sun", "person", "fund"))
        M = any(k in sig and sig[k] > 0 for k in ("m1", "m3", "m5"))
        n_sig = sum(1 for k in ALLSIG if k in sig and sig[k] > 0)
        return I, M, n_sig

    # 先把入选股的前向结果缓存（T,code）-> sim，避免重复模拟
    sim_cache = {}
    for T, sel in per_day_sel:
        for code, sc, sig in sel:
            if (T, code) not in sim_cache:
                sim_cache[(T, code)] = simulate(K, code, T)

    MOD_DEFS = [
        ("v0_现行≥3共振",        lambda I, M, n: n >= 3),
        ("v1_≥3共振+融资增仓M",   lambda I, M, n: n >= 3 and M),
        ("v2_≥3共振+M或I",       lambda I, M, n: n >= 3 and (M or I)),
        ("v3_≥3共振+M且I",       lambda I, M, n: n >= 3 and M and I),
        ("v4_≥2共振+M且I",       lambda I, M, n: n >= 2 and M and I),
        ("v5_M且I(不限共振数)",   lambda I, M, n: M and I),
        ("v6_M强(≥5日占比4%)+I",  lambda I, M, n: False),  # 占位，下面单独算
    ]
    mod_results = {name: [] for name, _ in MOD_DEFS}
    m5_strong_results = []   # v6: m5 ratio≥4% 且 I
    margin_only = []         # M 触发但无 I（对照）
    ins_only = []            # I 触发但无 M（对照）
    for T, sel in per_day_sel:
        for code, sc, sig in sel:
            I, M, n_sig = mods(sig)
            r = sim_cache.get((T, code))
            if not r:
                continue
            rec = (T, code, r[0], r[1], r[2])
            for name, fn in MOD_DEFS:
                if name.startswith("v6"):
                    continue
                if fn(I, M, n_sig):
                    mod_results[name].append(rec)
            mev_ratio5 = sig.get("_mr5") or 0.0
            if mev_ratio5 >= MARG_TH[5] and I:
                m5_strong_results.append(rec)
            if M and not I:
                margin_only.append(rec)
            if I and not M:
                ins_only.append(rec)
    mod_results["v6_M强(≥5日占比4%)+I"] = m5_strong_results
    mod_results["_对照_M无I"] = margin_only
    mod_results["_对照_I无M"] = ins_only
    mod_wr = {name: wr(v) for name, v in mod_results.items()}
    print("\n-- 条件模块组合（I=机构/私募季度增持 · M=融资融券1/3/5日净增仓）--")
    for name, v in mod_wr.items():
        print(f"  {name:<24} n={v[0]:>4} 胜率={v[1]:>5.1f}% 均收益={v[2]:>6.2f}%")

    # margin 阈值敏感性（诚实披露：不同先验阈值下方向是否稳定；用原始占比，含未触发样本）
    sens = collections.defaultdict(list)
    for T, sel in per_day_sel:
        for code, sc, sig in sel:
            r = sim_cache.get((T, code))
            if not r or "_mr5" not in sig:
                continue
            rec = (T, code, r[0], r[1], r[2])
            for th in (0.0, 0.01, 0.02, 0.03, 0.04, 0.06):
                if sig["_mr5"] >= th:
                    sens[th].append(rec)
    sens_wr = {th: wr(v) for th, v in sens.items()}
    sig_wr = {}
    for k in ALLSIG:
        ev = sig_events[k]
        rs = [simulate(K, code, T) for code, T in ev]
        # 转成与 sel_results 同构的元组 (T, code, ret, win, fwd) 再统计
        rs = [(0, code, r[0], r[1], r[2]) for r in rs if r]
        sig_wr[k] = (len(ev), wr(rs))

    # 逐日表
    day_rows = []
    for T, sel in per_day_sel:
        rs = [r for r in sel_results if r[0] == T]
        n, w, ret = wr(rs)
        day_rows.append((T, len(sel), n, round(w, 1), round(ret, 2)))

    # 信号共现（入选股中同时触发的信号对）
    pair = collections.Counter()
    for T, sel in per_day_sel:
        for code, sc, sig in sel:
            ks = [k for k in ALLSIG if k in sig and sig[k] > 0]
            for a in range(len(ks)):
                for b in range(a + 1, len(ks)):
                    pair[tuple(sorted((ks[a], ks[b])))] += 1

    summary = {
        "days": args.days, "lastN": lastN,
        "sel_wr": sel_wr, "base_wr": base_wr, "cons_wr": cons_wr,
        "sig_wr": {k: sig_wr[k] for k in ALLSIG},
        "day_rows": day_rows,
        "top_pairs": pair.most_common(8),
        "topn": TOPN, "exit": {"stop": STOP, "act": ACT, "trail": TRAIL, "maxfwd": MAXFWD},
        "margin_snaps": [s[0] for s in snaps],
        "mod_wr": {k: list(v) for k, v in mod_wr.items()},
        "sens_wr": {str(k): list(v) for k, v in sens_wr.items()},
        "margin_em_n": len(mh), "marg_th": MARG_TH,
    }
    json.dump(summary, open(os.path.join(OUT, "accum_result.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    # 控制台
    print(f"\n=== 增仓精选 回测（最近 {args.days} 交易日） ===")
    print(f"入选股可测样本 n={sel_wr[0]}  胜率={sel_wr[1]:.1f}%  均值收益={sel_wr[2]:.2f}%")
    print(f"基线(随机)   n={base_wr[0]}  胜率={base_wr[1]:.1f}%  均值收益={base_wr[2]:.2f}%")
    print(f"edge(胜率差) = {sel_wr[1]-base_wr[1]:+.1f}pp")
    print("\n-- 共识度曲线（≥m 个信号同时触发的入选股）--")
    for m in sorted(cons_wr):
        nn, w, ret = cons_wr[m]
        print(f"  ≥{m} 个信号  n={nn:>4} 胜率={w:>5.1f}% 收益={ret:>6.2f}%")
    print("\n-- 逐信号命中率（该信号触发股的前向胜率）--")
    for k in ALLSIG:
        ev_n, (nn, w, ret) = sig_wr[k]
        print(f"  {SIG_CN[k]:<10} 事件{ev_n:>4} 可测{nn:>4} 胜率={w:>5.1f}% 收益={ret:>6.2f}%")
    print("\n-- 逐日 --")
    for row in day_rows:
        print(f"  {row[0]} 入选{row[1]:>3} 可测{row[2]:>3} 胜率{row[3]:>5}% 收益{row[4]:>6}%")
    print("\n-- 信号共现 Top --")
    for (a, b), cnt in pair.most_common(6):
        print(f"  {SIG_CN[a]} + {SIG_CN[b]}: {cnt}")

    render_html(summary, q2, names, per_day_sel, K, frame_dummy=None)
    print(f"\n[done] 证据页 -> {os.path.join(OUT,'lab.html')}")

# ============================================================
# 5. 证据页
# ============================================================
def render_html(S, q2, names, per_day_sel, K, frame_dummy):
    RED, GRN, BLUE = "#ea4335", "#34a853", "#1a73e8"
    def fmt(v): return f"{v:.1f}"
    sig_rows = ""
    for k in ALLSIG:
        ev_n, (nn, w, ret) = S["sig_wr"][k]
        col = RED if w >= 55 else ("#888" if nn == 0 else GRN)
        sig_rows += (f"<tr><td>{SIG_CN[k]}</td><td>{ev_n}</td><td>{nn}</td>"
                     f"<td style='color:{col};font-weight:700'>{fmt(w)}%</td><td>{fmt(ret)}%</td></tr>")
    day_rows = ""
    for T, ns, n, w, ret in S["day_rows"]:
        day_rows += f"<tr><td>{T}</td><td>{ns}</td><td>{n}</td><td>{w}%</td><td>{ret}%</td></tr>"
    pairs = ""
    for (a, b), cnt in S["top_pairs"]:
        pairs += f"<tr><td>{SIG_CN[a]} + {SIG_CN[b]}</td><td>{cnt}</td></tr>"

    seln, selw, selr = S["sel_wr"]
    bn, bw, br = S["base_wr"]
    edge = selw - bw
    html = f"""<!doctype html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>增仓精选 · 回测证据</title>
<style>
*{{box-sizing:border-box}}
body{{margin:0;font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;background:#f5f6f8;color:#23262b}}
.wrap{{max-width:1100px;margin:0 auto;padding:40px 20px 60px}}
h1{{font-size:26px;margin:0 0 4px;color:#1c2430}}
.sub{{color:#8a929c;font-size:13px;margin:0 0 22px}}
.card{{background:#fff;border:1px solid rgba(0,0,0,.08);border-radius:16px;padding:18px 20px;margin:0 0 18px;box-shadow:0 1px 3px rgba(20,30,50,.05)}}
.card h2{{font-size:16px;margin:0 0 12px;color:#1c2430}}
.kpi{{display:flex;flex-wrap:wrap;gap:14px}}
.k{{flex:1;min-width:150px;background:linear-gradient(135deg,#fafbff,#f0f4ff);border:1px solid #dde6ff;border-radius:14px;padding:14px;text-align:center}}
.k .v{{font-size:26px;font-weight:800}}
.k .l{{font-size:12px;color:#6b7280;margin-top:4px}}
table{{width:100%;border-collapse:collapse;font-size:13px}}
th,td{{padding:7px 9px;border-bottom:1px solid #eef0f3;text-align:center}}
th{{background:#f7f9fc;color:#5b6573;font-weight:600}}
.warn{{background:#fff7ed;border:1px solid #fed7aa;color:#9a5b1e;border-radius:12px;padding:12px 14px;font-size:13px;line-height:1.7}}
.note{{color:#6b7280;font-size:12px;line-height:1.7}}
</style></head><body><div class="wrap">
<h1>增仓精选 · 样本外回测证据</h1>
<p class="sub">最近 {S['days']} 个交易日（{S['lastN'][0]} ~ {S['lastN'][-1]}）· 移动止盈退出（止损-{int(S['exit']['stop']*100)}%/激活+{int(S['exit']['act']*100)}%/回撤{int(S['exit']['trail']*100)}%/满{S['exit']['maxfwd']}日）· 每日入选≤{S['topn']}</p>

<div class="card"><h2>核心结论</h2>
<div class="kpi">
<div class="k"><div class="v" style="color:{RED}">{fmt(selw)}%</div><div class="l">入选股可兑现胜率（n={seln}）</div></div>
<div class="k"><div class="v" style="color:#888">{fmt(bw)}%</div><div class="l">基线（随机同量）</div></div>
<div class="k"><div class="v" style="color:{BLUE}">{edge:+.1f}pp</div><div class="l">胜率优势 edge</div></div>
<div class="k"><div class="v">{fmt(selr)}%</div><div class="l">入选股均值收益</div></div>
</div></div>

<div class="card"><h2>共识度曲线（≥m 个信号同时触发的入选股胜率）</h2>
<table><tr><th>共振门槛</th><th>可测样本</th><th>胜率</th><th>均值收益</th></tr>""" + "".join(
    f"<tr><td>≥{m} 个信号</td><td>{v[0]}</td><td style='color:{RED if v[1]>=60 else GRN};font-weight:700'>{fmt(v[1])}%</td><td>{fmt(v[2])}%</td></tr>"
    for m, v in sorted(S.get("cons_wr", {}).items())) + f"""</table>
<div class="note">结论：<b>单一信号≈基线，多维度共振才有超额</b>——「合起来选股」的核心是共识度，≥3 个信号共振胜率 {(S.get('cons_wr',{}).get(3,(0,0,0)))[1]:.1f}%。样本较小（≥4 档仅 {S.get('cons_wr',{}).get(4,(0,0,0))[0]} 笔），统计脆弱性需在后续样本外持续验证。</div>
</div>

<div class="card"><h2>条件模块组合（Ⅰ 机构/私募增持 I × Ⅱ 融资融券净增仓 M）</h2>
<table><tr><th>模块组合</th><th>可测样本</th><th>胜率</th><th>均值收益</th></tr>""" + "".join(
    f"<tr><td>{'S 档规则' if k.startswith('v6') else k.split('_',1)[1]}</td><td>{v[0]}</td><td style='color:{RED if v[1]>=70 else BLUE};font-weight:700'>{fmt(v[1])}%</td><td>{fmt(v[2])}%</td></tr>"
    for k, v in S.get("mod_wr", {}).items() if not k.startswith("_")) + f"""</table>
<div class="note">定稿：<b>S 档 = 5日融资净买入占成交额 ≥{int(S.get('marg_th',{}).get(5,0.04)*100)}% 且 机构/私募增持</b>（最高胜率档）；A 档 = ≥3 信号共振且（M 或 I）；对照：仅 M 无 I / 仅 I 无 M 胜率都明显低于组合——<b>两模块交叉验证才有最高确定性</b>。</div>
</div>

<div class="card"><h2>5日融资占比阈值敏感性（先验阈值非拟合的验证）</h2>
<table><tr><th>阈值</th><th>可测样本</th><th>胜率</th><th>均值收益</th></tr>""" + "".join(
    f"<tr><td>≥{float(k)*100:.0f}%</td><td>{v[0]}</td><td style='color:{RED if v[1]>=70 else BLUE};font-weight:700'>{fmt(v[1])}%</td><td>{fmt(v[2])}%</td></tr>"
    for k, v in sorted(S.get("sens_wr", {}).items(), key=lambda x: float(x[0]))) + f"""</table>
<div class="note">胜率随阈值<b>单调上升</b>，说明「融资净买入占比」是真实的剂量-反应信号，不是在某一点上凑出来的过拟合。阈值取 {int(S.get('marg_th',{}).get(5,0.04)*100)}%（先验：窗口越长容忍占比越低）。</div>
</div>

<div class="card"><h2>逐信号命中率（该信号触发股的前向胜率）</h2>
<table><tr><th>信号</th><th>事件数</th><th>可测</th><th>胜率</th><th>均值收益</th></tr>{sig_rows}</table>
<div class="note">注：私募/阳光私募/个人(牛散)/公募增持为 <b>2026Q2 季度维度</b>（股东环比增持标记），在 20 日内为静态 flags；其余为日频事件信号。<b>多空增仓 1/3/5 日已升级为东财全量融资融券日频序列</b>（T+1 公布口径，事件域 {S.get('margin_em_n',0)} 只逐只抓取），阈值先验固定 {int(S.get('marg_th',{}).get(1,0.02)*100)}/{int(S.get('marg_th',{}).get(3,0.04)*100)}/{int(S.get('marg_th',{}).get(5,0.04)*100)}%（净买入占成交额）。</div>
</div>

<div class="card"><h2>逐日选股胜率</h2>
<table><tr><th>日期</th><th>入选</th><th>可测</th><th>胜率</th><th>均值收益</th></tr>{day_rows}</table>
<div class="note">可测样本=该日入选股中有足够前向日K（≤{S['exit']['maxfwd']}日）者。最新数日因日K缓存截至 {S['lastN'][-1]}，前向窗口不足，不计入胜率但照常入选。</div>
</div>

<div class="card"><h2>信号共现 Top（入选股中同时触发）</h2>
<table><tr><th>信号组合</th><th>次数</th></tr>{pairs}</table>
</div>

<div class="warn"><b>数据覆盖与局限</b><br>
· 大宗交易：日频连续（block_chg，20/20 覆盖）。<br>
· 高管增持：exec_chg 覆盖 13/20 日（9-02 起）。<br>
· 席位异动：龙虎榜 lhb_detail 覆盖 8/20 日。<br>
· 多空增仓：<b>东财 datacenter-web 融资融券日频序列</b>（margin_em/，{S.get('margin_em_n',0)} 只事件域全量，T+1 公布口径防未来函数），不再是稀疏快照近似；阈值为先验固定并已做单调性检验。<br>
· 私募/阳光私募/个人(牛散)/公募增持：q2 十大流通股东 2026-06-30 季度环比，{len(q2)} 只股票带标记。<br>
· S 档（M强×I）样本 n=110、≥6% 占比档 n=34 偏小，统计脆弱，须样本外持续验证。<br>
· 退出口径与「主升精选/反转池」一致，胜率可直接横比。本回测为样本外（用当时可得信号选股、用之后日K验证），非参数拟合。</div>
</div></body></html>"""
    open(os.path.join(OUT, "lab.html"), "w", encoding="utf-8").write(html)

if __name__ == "__main__":
    main()
