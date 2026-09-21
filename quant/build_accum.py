# -*- coding: utf-8 -*-
"""
增仓精选 · 每日选股页（build_accum.py v3）
=====================================
基于 _accum_lab 的信号帧（机构/私募季度增持 I × 融资融券 1/3/5 日净增仓 M × 日频事件）做当日选股。
定稿规则（20 交易日回测，移动止盈口径，证据见 lab.html）：
  S 档 = 5日融资净买入占成交额 ≥4%（M强）+ 机构/私募季度增持（I）     → 胜率 80.9%（n=110）
  A 档 = ≥3 信号共振 且 （融资增仓 M 或 机构/私募 I）                 → 胜率 68~69%（n≈424）
  B 档 = 2 个信号触发（观察仓）
  不入选 = 仅 1 个信号（≈基线，无超额）
阈值敏感性（5日占比，单调）：≥0% 68.4 → ≥2% 70.6 → ≥4% 80.9 → ≥6% 91.2%。

每日持久化（与其它板块一致）：
  web/accumulation/combined_{DS}.html   当期页（历史留档）
  web/accumulation/stat_{DS}.json       当期统计快照（供门户读取）
  web/accumulation/index.html           最新一期（等于最新 combined）
  web/accumulation/history.html          每日归档 + 事后兑现跟踪（自包含）
  quant/accum/history.json              本地历史累积（逐期逐票，T+1/T+5 + 移动止盈结算）
每次运行会先对历史各期做兑现回填（数据够即结算），再入当期 —— 累积的可兑现胜率与其它池同口径。

用法： python build_accum.py 2026-09-21
      python build_accum.py --all        # 重生成全部已归档期页面
"""
import os, sys, json, collections

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import _accum_lab as L

OUT = os.path.join(ROOT, "web", "accumulation")
DATA = os.path.join(HERE, "accum")
HIST = os.path.join(DATA, "history.json")
os.makedirs(OUT, exist_ok=True)
os.makedirs(DATA, exist_ok=True)

RED, GRN, BLUE, GOLD = "#ea4335", "#34a853", "#1a73e8", "#b8893b"
SIG_CN = L.SIG_CN
SIG_ORDER = ["pe", "sun", "person", "fund", "block", "exec", "lhb", "m1", "m3", "m5"]
I_KEYS = ("pe", "sun", "person", "fund")
M_KEYS = ("m1", "m3", "m5")
TIER_CN = {"S": "S 强共振", "A": "A 共振", "B": "B 观察"}


def load_result():
    p = os.path.join(OUT, "accum_result.json")
    if os.path.exists(p):
        return json.load(open(p, encoding="utf-8"))
    return {}


# ---------------------------------------------------------------
# 历史累积
# ---------------------------------------------------------------
def load_hist():
    if os.path.exists(HIST):
        try:
            h = json.load(open(HIST, encoding="utf-8"))
            if isinstance(h, list):
                return h
        except Exception:
            pass
    return []


def save_hist(hist):
    hist.sort(key=lambda h: h.get("date", ""))
    with open(HIST, "w", encoding="utf-8") as f:
        json.dump(hist, f, ensure_ascii=False, indent=1)


def entry_price(K, code, T):
    try:
        ds, last = K[code][0], K[code][1]
        return last[ds.index(T)]
    except Exception:
        return None


def upsert(hist, date, rows, universe_n, K):
    """写入/覆盖当期条目（S+A 档逐票入库，B 档只留计数）。"""
    nS = sum(1 for r in rows if r["tier"] == "S")
    nA = sum(1 for r in rows if r["tier"] == "A")
    nB = sum(1 for r in rows if r["tier"] == "B")
    picks = []
    for r in rows:
        if r["tier"] not in ("S", "A"):
            continue
        picks.append({
            "code": r["code"], "name": r["name"], "tier": r["tier"],
            "score": r["score"], "n_sig": r["n_sig"], "m5r": r.get("m5r", 0.0),
            "entry": entry_price(K, r["code"], date),
        })
    row = {"date": date, "universe": universe_n, "nS": nS, "nA": nA, "nB": nB,
           "picks": picks}
    for i, h in enumerate(hist):
        if h.get("date") == date:
            hist[i] = row
            break
    else:
        hist.append(row)
    return hist


def settle(hist, K):
    """对历史每期每票回填事后收益（移动止盈口径，与回测同规则）。
    K 不变则结果不变，幂等；新交易日入库后旧期会自动重算。
    """
    for h in hist:
        T = h.get("date", "")
        tot = 0
        win = 0
        sret = 0.0
        for p in h.get("picks", []):
            code = p.get("code")
            sim = L.simulate(K, code, T) if code in K else None
            if sim:
                ret, w, fwd, rs = sim
                p["sim"] = {"ret": round(ret * 100, 2), "win": bool(w),
                            "fwd": fwd, "reason": rs}
                tot += 1
                win += 1 if w else 0
                sret += ret
            else:
                p.pop("sim", None)
            # T+1 / T+5 裸收益（不走退出规则，仅供观察短期反应）
            f1 = f5 = None
            try:
                ds, last = K[code][0], K[code][1]
                i = ds.index(T)
                ep = last[i]
                if ep:
                    if i + 1 < len(ds):
                        f1 = round((last[i + 1] / ep - 1) * 100, 2)
                    if i + 5 < len(ds):
                        f5 = round((last[i + 5] / ep - 1) * 100, 2)
            except Exception:
                pass
            p["f1"], p["f5"] = f1, f5
        h["nSettle"] = tot
        h["wins"] = win
        h["wr"] = round(win / tot * 100, 1) if tot else None
        h["avg"] = round(sret / tot * 100, 2) if tot else None
    return hist


def hist_summary(hist):
    tot = sum(h.get("nSettle", 0) for h in hist)
    win = sum(h.get("wins", 0) for h in hist)
    return {
        "periods": len(hist),
        "n": tot,
        "wr": round(win / tot * 100, 1) if tot else None,
    }


# ---------------------------------------------------------------
# 选股
# ---------------------------------------------------------------
def scan(date):
    K = L.load_kline()
    cal = L.trading_days(K)
    if date not in cal:
        date = cal[-1]
        print(f"[warn] 指定日不在交易日历，回退最新数据日 {date}")
    q2 = L.load_q2_flags()
    snaps = L.load_margin_snapshots()
    mh = L.load_margin_em()
    frame = L.signal_frame(date, K, q2, snaps, cal, mh=mh)

    nm = {}
    try:
        nm = json.load(open(os.path.join(HERE, "_stock_names.json"), encoding="utf-8"))
    except Exception:
        pass
    c = json.load(open(L.CACHE, encoding="utf-8"))
    names = {code: (nm.get(code) or (bars[-1].get("name") if bars else None) or code)
             for code, bars in c.items()}

    rows = []
    for code, sig in frame.items():
        has_daily = any(k in sig and sig[k] > 0 for k in L.DAILY)
        if not has_daily:
            continue
        sc = L.composite(sig)
        if sc <= 0:
            continue
        n_sig = sum(1 for k in L.ALLSIG if k in sig and sig[k] > 0)
        I = any(k in sig and sig[k] > 0 for k in I_KEYS)
        M = any(k in sig and sig[k] > 0 for k in M_KEYS)
        m5r = sig.get("_mr5") or 0.0
        if m5r >= L.MARG_TH[5] and I:
            tier = "S"
        elif n_sig >= 3 and (M or I):
            tier = "A"
        elif n_sig == 2:
            tier = "B"
        else:
            tier = "C"
        rows.append({
            "code": code, "name": names.get(code, code), "score": round(sc, 3),
            "n_sig": n_sig, "sig": sig, "tier": tier,
            "m5r": round(m5r * 100, 1),
        })
    tier_rank = {"S": 0, "A": 1, "B": 2, "C": 3}
    # 末位以 code 兜底：dict/set 迭代顺序跨进程不稳定，否则同参数的页面 sha 会漂
    rows.sort(key=lambda r: (tier_rank[r["tier"]], -r["n_sig"], -r["score"], r["code"]))
    return date, rows, len(frame), K


def sig_badges(sig):
    out = []
    for k in SIG_ORDER:
        if k in sig and sig[k] > 0:
            tip = ""
            if k == "block":
                tip = f"（额 {sig.get('_block_val',0)/1e4:.0f}万 折价 {sig.get('_block_disc',0):.1f}%）"
            elif k == "exec":
                tip = f"（增持 {sig.get('_exec_amt',0)/1e4:.0f}万元）"
            elif k == "lhb":
                tip = f"（净买 {sig.get('_lhb_net',0)/1e4:.0f}万）"
            elif k in ("m1", "m3", "m5"):
                w = {"m1": "1日", "m3": "3日", "m5": "5日"}[k]
                r = sig.get("_mr" + k[1])
                tip = f"（{w}融资净买入占成交额 {r*100:.1f}%）" if r is not None else ""
            out.append(f"<span class='bdg' title='{tip}'>{SIG_CN[k]}</span>")
    return "".join(out)


def _ret_color(v):
    if v is None:
        return "#8a929c"
    return RED if v > 0 else (GRN if v < 0 else "#8a929c")


def archive_rows(hist, cur_date):
    """历史归档表（只显示 ≤ 当期 的期次，保证当期页不含未来信息）。"""
    rows = [h for h in hist if h.get("date", "") <= cur_date]
    out = []
    for h in sorted(rows, key=lambda x: x["date"], reverse=True):
        d = h["date"]
        ds = d.replace("-", "")
        cur = " style='font-weight:700'" if d == cur_date else ""
        wr = h.get("wr")
        wrs = f"{wr:.1f}%" if wr is not None else "待结算"
        if wr is None:
            wrc = "#8a929c"
        else:
            wrc = RED if wr >= 70 else (GOLD if wr >= 60 else "#8a929c")
        settle_txt = f"{h.get('nSettle',0)}/{h.get('nS',0)+h.get('nA',0)}"
        out.append(
            f"<tr><td{cur}><a href='combined_{ds}.html'>{d}</a></td>"
            f"<td>{h.get('universe','—')}</td><td>{h.get('nS',0)}</td><td>{h.get('nA',0)}</td>"
            f"<td>{h.get('nB',0)}</td><td>{settle_txt}</td>"
            f"<td style='color:{wrc};font-weight:700'>{wrs}</td></tr>")
    return "".join(out)


def render_history(hist):
    """每日归档 + 事后兑现跟踪页（自包含）。"""
    summ = hist_summary(hist)
    rows = []
    for h in sorted(hist, key=lambda x: x["date"], reverse=True):
        d = h["date"]
        ds = d.replace("-", "")
        wr = h.get("wr")
        wrc = _ret_color(wr - 50) if wr is not None else "#8a929c"
        rows.append(
            f"<tr><td><a href='combined_{ds}.html'>{d}</a></td>"
            f"<td>{h.get('universe','—')}</td><td>{h.get('nS',0)}</td><td>{h.get('nA',0)}</td>"
            f"<td>{h.get('nB',0)}</td><td>{h.get('nSettle',0)}</td>"
            f"<td style='color:{wrc};font-weight:700'>{wr if wr is not None else '—'}"
            f"{'%' if wr is not None else ''}</td>"
            f"<td style='color:{_ret_color(h.get('avg'))}'>{h.get('avg') if h.get('avg') is not None else '—'}</td></tr>")

    # 逐期明细（近 10 期）
    detail = []
    for h in sorted(hist, key=lambda x: x["date"], reverse=True)[:10]:
        d = h["date"]
        ds = d.replace("-", "")
        ps = h.get("picks", [])
        if not ps:
            detail.append(f"<div class='hrow'><div class='hd'><a href='combined_{ds}.html'>{d}</a>"
                          f"<span class='hsub'>候选 {h.get('universe','—')} · 无 S/A 档入选</span></div></div>")
            continue
        trs = []
        for p in ps:
            sim = p.get("sim")
            if sim:
                rc = _ret_color(sim["ret"])
                rt = f"<span style='color:{rc};font-weight:700'>{sim['ret']:+.2f}%</span>" \
                     f"<span class='why'>{sim['reason']}·{sim['fwd']}日</span>"
            else:
                rt = "<span class='why'>未到期</span>"
            f1 = p.get("f1")
            f5 = p.get("f5")
            tc = GOLD if p["tier"] == "S" else RED
            trs.append(
                f"<tr><td><a href='https://quote.eastmoney.com/{p['code']}.html' target='_blank'>{p['name']}</a></td>"
                f"<td style='color:{tc};font-weight:700'>{p['tier']}</td><td>{p.get('n_sig','—')}</td>"
                f"<td>{p.get('m5r',0):.1f}%</td>"
                f"<td style='color:{_ret_color(f1)}'>{f1 if f1 is not None else '—'}</td>"
                f"<td style='color:{_ret_color(f5)}'>{f5 if f5 is not None else '—'}</td>"
                f"<td>{rt}</td></tr>")
        wr = h.get("wr")
        detail.append(
            f"<div class='hrow'><div class='hd'><a href='combined_{ds}.html'>{d}</a>"
            f"<span class='hsub'>候选 {h.get('universe','—')} 只 · S {h.get('nS',0)} / A {h.get('nA',0)}"
            f" · 已结算 {h.get('nSettle',0)}"
            f" · 胜率 <b style='color:{_ret_color((wr or 0)-50)}'>{wr if wr is not None else '—'}"
            f"{'%' if wr is not None else ''}</b></span></div>"
            f"<table><tr><th>名称</th><th>档</th><th>共振</th><th>5日融资占比</th>"
            f"<th>T+1</th><th>T+5</th><th>结算（移动止盈）</th></tr>{''.join(trs)}</table></div>")

    html = CSS_HEAD + f"""<title>增仓精选 · 每日归档与兑现跟踪</title>{CSS_COMMON}<style>
.hrow{{margin:0 0 16px}}
.hd{{font-size:14px;font-weight:700;margin:0 0 6px}}
.hsub{{font-weight:400;color:#6b7280;font-size:12px;margin-left:8px}}
.why{{display:block;font-size:11px;color:#8a929c}}
</style></head><body><div class="wrap">
<h1>每日归档 · 兑现跟踪</h1>
<p class="sub">共 {summ['periods']} 期 ｜ 已结算样本 {summ['n']} 个 ｜
累计可兑现胜率 <b style="color:{_ret_color((summ['wr'] or 0)-50)}">{summ['wr'] if summ['wr'] is not None else '—'}{'%' if summ['wr'] is not None else ''}</b>
（与回测口径一致：止损 −12% ／ 浮盈 +6% 激活、回撤 3% 跟踪 ／ 满 20 日强平）｜
<a href='index.html'>最新一期</a> · <a href='lab.html'>回测证据</a></p>

<div class="card"><h2>各期概览</h2>
<table><tr><th>数据日</th><th>候选域</th><th>S 档</th><th>A 档</th><th>B 档</th><th>已结算</th><th>胜率</th><th>均值收益</th></tr>
{''.join(rows) if rows else "<tr><td colspan='8'>暂无归档</td></tr>"}</table>
<div class="note">T+1 / T+5 为裸涨跌幅（不走退出规则），结算列按移动止盈规则兑现；两者口径不同，别混用。</div></div>

<div class="card"><h2>近 10 期逐票明细</h2>
{''.join(detail) if detail else "<div class='note'>暂无明细。</div>"}</div>

<div class="rule"><b>说明</b><br>
· 归档按<b>交易日逐期</b>留档：每期生成 <code>combined_&#123;YYYYMMDD&#125;.html</code> 与 <code>stat_&#123;YYYYMMDD&#125;.json</code>，门户按最新一期更新。<br>
· S / A 档逐票入库（含当日收盘价，作入场价），每次运行都会重算历史各期的事后兑现 —— <b>这是真实留痕，不是回测拟合</b>。<br>
· 样本会随交易日累积，短期数字统计脆弱；<b>退出纪律 &gt; 入场筛选</b>。</div>
</div></body></html>"""
    p = os.path.join(OUT, "history.html")
    open(p, "w", encoding="utf-8").write(html)
    return p


CSS_HEAD = """<!doctype html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
"""

# 与其它板块页面保持一致的公共样式块（历史/归档页与当期页共用）
CSS_COMMON = """<style>
*{box-sizing:border-box}
body{margin:0;font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;background:#f5f6f8;color:#23262b}
.wrap{max-width:1440px;margin:0 auto;padding:36px 20px 60px}
h1{font-size:26px;margin:0 0 4px;color:#1c2430}
.sub{color:#8a929c;font-size:13px;margin:0 0 20px}
.card{background:#fff;border:1px solid rgba(0,0,0,.08);border-radius:16px;padding:18px 20px;margin:0 0 18px;box-shadow:0 1px 3px rgba(20,30,50,.05)}
.card h2{font-size:16px;margin:0 0 12px;color:#1c2430;display:flex;align-items:center;gap:8px}
.card h2:before{content:"";width:4px;height:16px;background:#b8893b;border-radius:3px}
.kpi{display:flex;flex-wrap:wrap;gap:12px}
.k{flex:1;min-width:150px;background:linear-gradient(135deg,#fafbff,#f0f4ff);border:1px solid #dde6ff;border-radius:14px;padding:13px;text-align:center}
.k .v{font-size:24px;font-weight:800}
.k .l{font-size:12px;color:#6b7280;margin-top:4px}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{padding:7px 9px;border-bottom:1px solid #eef0f3;text-align:center}
th{background:#f7f9fc;color:#5b6573;font-weight:600}
td a{color:#1c2430;text-decoration:none} td a:hover{color:#1a73e8}
.rule{background:#fff7ed;border:1px solid #fed7aa;color:#9a5b1e;border-radius:12px;padding:12px 14px;font-size:13px;line-height:1.8}
.note{color:#6b7280;font-size:12px;line-height:1.7}
code{background:#f1f3f4;padding:1px 5px;border-radius:5px;font-size:12px}
</style>"""


def render(date, rows, universe_n, res, hist):
    S = [r for r in rows if r["tier"] == "S"]
    A = [r for r in rows if r["tier"] == "A"]
    B = [r for r in rows if r["tier"] == "B"]
    cons = res.get("cons_wr", {})
    mod_wr = res.get("mod_wr", {})
    base_wr = res.get("base_wr", (0, 0, 0))
    sens = res.get("sens_wr", {})
    days = res.get("days", 20)

    def wr3(k):
        v = mod_wr.get(k) or (0, 0.0, 0.0)
        return v

    s_v6 = wr3("v6_M强(≥5日占比4%)+I")
    v3 = wr3("v3_≥3共振+M且I")
    cons_rows = "".join(
        f"<tr><td>≥{m} 个信号</td><td>{v[0]}</td>"
        f"<td style='color:{RED if v[1]>=60 else GRN};font-weight:700'>{v[1]:.1f}%</td><td>{v[2]:.2f}%</td></tr>"
        for m, v in sorted(cons.items(), key=lambda x: int(x[0].replace('≥','').replace(' 个信号','')) if isinstance(x[0], str) else 0))
    mod_rows = "".join(
        f"<tr><td>{'S 档规则' if k.startswith('v6') else k.split('_',1)[1]}</td><td>{v[0]}</td>"
        f"<td style='color:{RED if v[1]>=70 else BLUE};font-weight:700'>{v[1]:.1f}%</td><td>{v[2]:.2f}%</td></tr>"
        for k, v in mod_wr.items() if not k.startswith("_"))
    sens_rows = "".join(
        f"<tr><td>5日净买入占比 ≥{float(k)*100:.0f}%</td><td>{v[0]}</td>"
        f"<td style='color:{RED if v[1]>=70 else BLUE};font-weight:700'>{v[1]:.1f}%</td><td>{v[2]:.2f}%</td></tr>"
        for k, v in sorted(sens.items(), key=lambda x: float(x[0])))

    def card(r):
        tc = {"S": "#b8893b", "A": RED, "B": BLUE}.get(r["tier"], "#888")
        return f"""<div class='stk{'' if r["tier"]!="S" else " stkS"}'>
<div class='h'><a class='nm' href='https://quote.eastmoney.com/{r["code"]}.html' target='_blank'>{r["name"]}</a>
<span class='cd'>{r["code"].upper()}</span><span class='tier' style='background:{tc}1a;color:{tc}'>{TIER_CN.get(r["tier"], r["tier"])}</span>
<span class='sc'>增仓分 {r["score"]:.2f}</span></div>
<div class='sg'>{sig_badges(r["sig"])}</div></div>"""

    cards = "".join(card(r) for r in (S + A)[:40])

    def trow(r, i):
        return (f"<tr><td>{i}</td><td><a href='https://quote.eastmoney.com/{r['code']}.html' "
                f"target='_blank'>{r['name']}</a></td><td>{r['code'].upper()}</td><td>{TIER_CN.get(r['tier'], r['tier'])}</td>"
                f"<td>{r['n_sig']}</td><td>{r.get('m5r', 0):.1f}%</td><td>{r['score']:.2f}</td><td class='sgtd'>{sig_badges(r['sig'])}</td></tr>")
    tbl = "".join(trow(r, i + 1) for i, r in enumerate(S + A + B))

    summ = hist_summary(hist)
    arc_rows = archive_rows(hist, date)

    html = f"""<!doctype html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>增仓精选 · {date}</title>
<style>
*{{box-sizing:border-box}}
body{{margin:0;font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;background:#f5f6f8;color:#23262b}}
.wrap{{max-width:1440px;margin:0 auto;padding:36px 20px 60px}}
h1{{font-size:26px;margin:0 0 4px;color:#1c2430}}
.sub{{color:#8a929c;font-size:13px;margin:0 0 20px}}
.card{{background:#fff;border:1px solid rgba(0,0,0,.08);border-radius:16px;padding:18px 20px;margin:0 0 18px;box-shadow:0 1px 3px rgba(20,30,50,.05)}}
.card h2{{font-size:16px;margin:0 0 12px;color:#1c2430;display:flex;align-items:center;gap:8px}}
.card h2:before{{content:"";width:4px;height:16px;background:{GOLD};border-radius:3px}}
.kpi{{display:flex;flex-wrap:wrap;gap:12px}}
.k{{flex:1;min-width:150px;background:linear-gradient(135deg,#fafbff,#f0f4ff);border:1px solid #dde6ff;border-radius:14px;padding:13px;text-align:center}}
.k .v{{font-size:24px;font-weight:800}}
.k .l{{font-size:12px;color:#6b7280;margin-top:4px}}
.stkgrid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:12px}}
.stk{{background:#fbfcfe;border:1px solid #e8ecf3;border-radius:12px;padding:12px 14px}}
.stkS{{background:linear-gradient(135deg,#fffaf0,#fdf3e0);border-color:#ecd9ae}}
.nm{{font-weight:700;font-size:15px;color:#1c2430;text-decoration:none}}
.nm:hover{{color:{BLUE}}}
.cd{{font-size:11px;color:#8a929c}}
.tier{{font-size:11px;padding:2px 8px;border-radius:10px;font-weight:700}}
.sc{{margin-left:auto;font-size:12px;color:#6b7280}}
.sg{{margin-top:8px;display:flex;flex-wrap:wrap;gap:6px}}
.bdg{{font-size:11px;background:#eef3fb;color:#3c5a83;border:1px solid #d8e2f2;border-radius:9px;padding:2px 8px}}
table{{width:100%;border-collapse:collapse;font-size:13px}}
th,td{{padding:7px 9px;border-bottom:1px solid #eef0f3;text-align:center}}
th{{background:#f7f9fc;color:#5b6573;font-weight:600}}
td a{{color:#1c2430;text-decoration:none}} td a:hover{{color:{BLUE}}}
.sgtd{{text-align:left;white-space:normal}}
.rule{{background:#fff7ed;border:1px solid #fed7aa;color:#9a5b1e;border-radius:12px;padding:12px 14px;font-size:13px;line-height:1.8}}
.evi{{background:#f0f7ff;border:1px solid #cfe3ff;border-radius:12px;padding:12px 14px;font-size:13px;line-height:1.8}}
.note{{color:#6b7280;font-size:12px;line-height:1.7}}
.hrow{{margin:0 0 16px}}
.hd{{font-size:14px;font-weight:700;margin:0 0 6px}}
.hsub{{font-weight:400;color:#6b7280;font-size:12px;margin-left:8px}}
.why{{display:block;font-size:11px;color:#8a929c}}
</style></head><body><div class="wrap">
<h1>增仓精选</h1>
<p class="sub">数据日 {date} ｜ 候选域 {universe_n} 只（带日频增仓事件）｜ S 档 {len(S)} · A 档 {len(A)} · B 档 {len(B)}
｜ <a href='history.html'>每日归档 · 兑现跟踪</a>（已 {summ['periods']} 期 / 累计结算 {summ['n']} 个，胜率
<b style="color:{_ret_color((summ['wr'] or 0)-50)}">{summ['wr'] if summ['wr'] is not None else '—'}{'%' if summ['wr'] is not None else ''}</b>）</p>

<div class="card"><h2>选股逻辑：机构/私募 × 融资增仓 双模块</h2>
<div class="kpi">
<div class="k" style="background:linear-gradient(135deg,#fffaf0,#fdf3e0);border-color:#ecd9ae"><div class="v" style="color:{GOLD}">{s_v6[1]:.1f}%</div><div class="l">S 档胜率（M强×机构私募，n={s_v6[0]}）</div></div>
<div class="k"><div class="v" style="color:{RED}">{v3[1]:.1f}%</div><div class="l">A 档胜率（≥3共振且M/I，n={v3[0]}）</div></div>
<div class="k"><div class="v" style="color:#888">{base_wr[1]:.1f}%</div><div class="l">随机基线（{days}日回测）</div></div>
<div class="k"><div class="v">{len(S)}</div><div class="l">今日 S 档（融资强增仓×机构私募）</div></div>
</div>
<div class="evi" style="margin-top:12px"><b>条件模块（先验固定）</b>：<br>
<b>Ⅰ 机构/私募增持（季度维度 Q2）</b>：私募 · 阳光私募 · 个人(牛散) · 公募 十大流通股东增持；<br>
<b>Ⅱ 融资融券 1/3/5 日净增仓（日频，东财全量序列 · T+1 公布口径）</b>：融资净买入占成交额 ≥2%/4%/4% 触发，
其中 <b>5 日占比是全信号最强单项</b>（79.8%，n=124）；<br>
<b>Ⅲ 日频事件</b>：大宗交易（折价加权）· 高管增持 · 席位异动。<br>
档位规则：<b>S 档</b> = 5日融资净买入占比≥4% 且 机构/私募增持（胜率 {s_v6[1]:.1f}%）；<b>A 档</b> = ≥3 信号共振且（M 或 I）（{v3[1]:.1f}%）；<b>B 档</b> = 2 信号观察仓。
退出纪律与主升/反转池一致：止损 −12% ／ 浮盈 +6% 激活、回撤 3% 跟踪 ／ 满 20 日强平。证据见 <a href='lab.html'>回测证据页</a>。</div></div>

<div class="card"><h2>S 档 · 强增仓 × 机构私募（最高确定性）</h2>
{''.join([f"<div class='stkgrid'>{cards}</div>"] if (S or A) else ["<div class='note'>今日无 S/A 档标的 —— 按纪律<b>空仓等待</b>，不降低门槛凑数。</div>"])}
</div>

<div class="card"><h2>完整名单（S + A + B 档）</h2>
<table><tr><th>#</th><th>名称</th><th>代码</th><th>档</th><th>共振数</th><th>5日融资占比</th><th>增仓分</th><th>触发信号</th></tr>{tbl}</table>
<div class="note">B 档（2 信号）仅作观察仓；1 信号 ≈基线，不入选。</div></div>

<div class="card"><h2>历史归档（每日留档 · 事后结算）</h2>
<table><tr><th>数据日</th><th>候选域</th><th>S</th><th>A</th><th>B</th><th>已结算</th><th>胜率</th></tr>{arc_rows}</table>
<div class="note">逐期留档 <code>combined_&#123;YYYYMMDD&#125;.html</code> ＋ 统计快照 <code>stat_&#123;YYYYMMDD&#125;.json</code>；
完整逐票明细见 <a href='history.html'>每日归档页</a>。结算口径与回测一致（移动止盈）。</div></div>

<div class="card"><h2>条件模块回测（最近 {days} 个交易日）</h2>
<table><tr><th>模块组合</th><th>可测样本</th><th>胜率</th><th>均值收益</th></tr>{mod_rows}</table>
<div class="note" style="margin-top:8px">对照：仅 M 无 I（n=15, 66.7%）／ 仅 I 无 M（n=46, 63.0%）—— 两模块组合才有最高胜率。</div></div>

<div class="card"><h2>5日融资占比阈值敏感性（单调 = 先验阈值非拟合）</h2>
<table><tr><th>阈值</th><th>可测样本</th><th>胜率</th><th>均值收益</th></tr>{sens_rows}</table></div>

<div class="card"><h2>共识度曲线</h2>
<table><tr><th>共振门槛</th><th>可测样本</th><th>胜率</th><th>均值收益</th></tr>{cons_rows}</table></div>

<div class="rule"><b>⚠️ 数据覆盖与局限（务必阅读）</b><br>
· 多空增仓维度已升级为<b>东财全量融资融券日频序列</b>（T+1 公布口径，事件域 945 只逐只抓取），不再是稀疏快照近似；但 5 日占比阈值 {L.MARG_TH[5]*100:.0f}% 为先验设定，敏感性已验证方向稳定（单调）。<br>
· 私募/阳光私募/个人(牛散)/公募增持为 <b>2026Q2 季度维度</b>；阳光私募与一般私募/保险在股东名中难严格区分，事件可为 0。<br>
· S 档 20 日样本 n={s_v6[0]}，≥6% 占比档 n=34 更小；统计脆弱，须样本外持续验证，<b>退出纪律 &gt; 入场筛选</b>。<br>
· 高管增持覆盖 9-02 起；席位异动（龙虎榜）有断档日；大宗交易 20/20 日。<br>
· 归档页的「累计胜率」是<b>逐交易日入选后真实走出来的结果</b>，样本随日累积，短期不代表稳态。</div>
</div></body></html>"""
    p = os.path.join(OUT, f"combined_{date.replace('-', '')}.html")
    open(p, "w", encoding="utf-8").write(html)
    # 入口页只跟随「最新一期」：补跑/回填历史旧期时不把 index 倒退
    latest = max([h.get("date", "") for h in hist]) if hist else date
    if date >= latest:
        open(os.path.join(OUT, "index.html"), "w", encoding="utf-8").write(html)
    # 统计快照（供门户读取，与其它板块 stat_*.json 同构）
    snap_name = _stat_name(date)
    stat = {
        "date": date,
        "n_universe": universe_n,
        "nS": len(S), "nA": len(A), "nB": len(B),
        "model": "accum_v3",
        "hist_periods": summ["periods"],
        "hist_n": summ["n"],
        "hist_wr": summ["wr"],
        "lab_S_wr": round(s_v6[1], 1), "lab_S_n": s_v6[0],
        "lab_A_wr": round(v3[1], 1), "lab_A_n": v3[0],
    }
    json.dump(stat, open(snap_name, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    return p


def _stat_name(date):
    return os.path.join(OUT, "stat_%s.json" % date.replace("-", ""))


def run(date, K=None, hist=None):
    """跑一期：入库 → 回填 → 出页（含 index/history）。返回 (date, rows, hist)。"""
    res = load_result()
    date, rows, universe_n, K = scan(date)
    hist = load_hist() if hist is None else hist
    hist = upsert(hist, date, rows, universe_n, K)
    hist = settle(hist, K)
    save_hist(hist)
    nS = sum(1 for r in rows if r["tier"] == "S")
    nA = sum(1 for r in rows if r["tier"] == "A")
    nB = sum(1 for r in rows if r["tier"] == "B")
    print(f"[scan] {date} 候选 {len(rows)}/{universe_n}  S档={nS}  A档={nA}  B档={nB}")
    p = render(date, rows, universe_n, res, hist)
    hp = render_history(hist)
    print(f"[done] {p}  {hp}")
    return date, rows, K, hist


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = {a for a in sys.argv[1:] if a.startswith("--")}
    hist = load_hist()
    if "--all" in flags:
        K = None
        for h in sorted(hist, key=lambda x: x["date"]):
            _, _, K, hist = run(h["date"], K=K, hist=hist)
        print(f"[all] 重生成 {len(hist)} 期")
        return
    if args:
        date = args[0]
    else:
        K0 = L.load_kline()
        date = L.trading_days(K0)[-1]
    run(date, hist=hist)


if __name__ == "__main__":
    main()
