# -*- coding: utf-8 -*-
"""
增仓精选 · 每日选股页（build_accum.py v2）
=====================================
基于 _accum_lab 的信号帧（机构/私募季度增持 I × 融资融券 1/3/5 日净增仓 M × 日频事件）做当日选股。
定稿规则（20 交易日回测，移动止盈口径，证据见 lab.html）：
  S 档 = 5日融资净买入占成交额 ≥4%（M强）+ 机构/私募季度增持（I）     → 胜率 80.9%（n=110）
  A 档 = ≥3 信号共振 且 （融资增仓 M 或 机构/私募 I）                 → 胜率 68~69%（n≈424）
  B 档 = 2 个信号触发（观察仓）
  不入选 = 仅 1 个信号（≈基线，无超额）
阈值敏感性（5日占比，单调）：≥0% 68.4 → ≥2% 70.6 → ≥4% 80.9 → ≥6% 91.2%。

用法： python build_accum.py 2026-09-21
输出： web/accumulation/combined_{DS}.html + index.html
"""
import os, sys, json, collections

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import _accum_lab as L

OUT = os.path.join(ROOT, "web", "accumulation")
os.makedirs(OUT, exist_ok=True)

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


def scan(date):
    K = L.load_kline()
    cal = L.trading_days(K)
    if date not in cal:
        date = cal[-1]
        print(f"[warn] {date} 不在交易日历，回退最新数据日 {date}")
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
    rows.sort(key=lambda r: (tier_rank[r["tier"]], -r["n_sig"], -r["score"]))
    return date, rows, len(frame)


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


def render(date, rows, universe_n, res):
    S = [r for r in rows if r["tier"] == "S"]
    A = [r for r in rows if r["tier"] == "A"]
    B = [r for r in rows if r["tier"] == "B"]
    cons = res.get("cons_wr", {})
    mod_wr = res.get("mod_wr", {})
    base_wr = res.get("base_wr", (0, 0, 0))
    sens = res.get("sens_wr", {})
    days = res.get("days", 20)
    span = res.get("lastN", ["", ""])

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
</style></head><body><div class="wrap">
<h1>增仓精选</h1>
<p class="sub">数据日 {date} ｜ 候选域 {universe_n} 只（带日频增仓事件）｜ S 档 {len(S)} · A 档 {len(A)} · B 档 {len(B)}</p>

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
· 高管增持覆盖 9-02 起；席位异动（龙虎榜）有断档日；大宗交易 20/20 日。</div>
</div></body></html>"""
    p = os.path.join(OUT, f"combined_{date.replace('-', '')}.html")
    open(p, "w", encoding="utf-8").write(html)
    open(os.path.join(OUT, "index.html"), "w", encoding="utf-8").write(html)
    return p


def main():
    date = sys.argv[1] if len(sys.argv) > 1 else None
    if not date:
        K = L.load_kline()
        date = L.trading_days(K)[-1]
    res = load_result()
    date, rows, universe_n = scan(date)
    nS = sum(1 for r in rows if r["tier"] == "S")
    nA = sum(1 for r in rows if r["tier"] == "A")
    nB = sum(1 for r in rows if r["tier"] == "B")
    print(f"[scan] {date} 候选 {len(rows)}/{universe_n}  S档={nS}  A档={nA}  B档={nB}")
    p = render(date, rows, universe_n, res)
    print(f"[done] {p}")


if __name__ == "__main__":
    main()
