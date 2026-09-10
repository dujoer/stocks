# -*- coding: utf-8 -*-
"""做T池 · 引擎（Stage 2）：筛选 → 做T适合度评分 → 操作参数 → 出页。

方法论（顶级机构规则）：
  - 网格交易法(Grid)：震荡市机械高抛低吸，赚波动不猜方向
  - 均值回归(Mean Reversion)：价格围绕箱体中枢往复
  - 底仓+卫星仓(Core-Satellite)：底仓不动，卫星仓反复做T摊低成本
  - 波动率套利：日振幅/ATR 足够大，做T才有空间
  - 风险预算：破箱体下沿无条件离场，单次做T亏损 ≤ 总资金 0.5%

输入：quant/tplus/universe_{D}.json / quotes_{D}.json / kline_{D}.json
输出：web/tplus/index.html、web/tplus/tplus-{D}.html、quant/tplus/history.json

用法：python build_tplus.py --date YYYY-MM-DD
"""
import os, sys, json, math, argparse, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "quant", "tplus")
WEB = os.path.join(ROOT, "web", "tplus")
PICKS = os.path.join(ROOT, "quant", "picks")
HIST = os.path.join(DATA, "history.json")


def esc(s):
    return (str(s if s is not None else "")
            .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("'", "&#39;"))


def fnum(x, n=2):
    if x is None:
        return "—"
    return f"{x:.{n}f}"


def pct(x):
    if x is None:
        return "—"
    return f"{x:+.2f}%"


def yi(x):
    if not x:
        return "—"
    return f"{x/1e8:.2f} 亿"


def clamp(x, a, b):
    return max(a, min(b, x))


def band(x, a, b, c, d, mx):
    """x 落在 [a,b] 得满分 mx，落在 [c,d] 外得 0，之间线性过渡。"""
    if x is None:
        return 0.0
    if a <= x <= b:
        return float(mx)
    if x < a:
        return float(mx) * (x - c) / (a - c) if a > c else 0.0
    return float(mx) * (d - x) / (d - b) if d > b else 0.0


# ---------------- 字段口径说明（悬浮提示） ----------------
TIPS = {
    "现价": "数据日期（T 日）收盘价，括号内为当日涨跌幅（红涨绿跌）。所有网格/波段价位均以该日收盘后的数据推算。",
    "做T分": "做T适合度总分（0~100）：波动性 30 + 流动性 20 + 区间结构 25 + 机构底仓 15 + 波动稳定性 10 − 风险扣分。分数越高越适合反复做T。",
    "档位": "A ≥80（可重点做T）· B 70~80（适合做T）· C 60~70（可小仓试）· D <60（不适合，仅列出）。",
    "日内振幅": "近 20 个交易日 (最高−最低)/前收 的平均值（%）。做T的『空间』来自振幅：低于 3% 基本没有做T价值，3%~9% 最佳。",
    "ATR%": "近 14 日平均真实波幅占现价比例（%），衡量单日波动幅度。3%~8% 最适合做T；过高(>10%)易单边、风险大。",
    "换手": "当日换手率（成交量/流通股本）。2%~18% 为活跃且可持续；过高(>20%)多为游资情绪票，做T易被闷杀。",
    "箱体": "近 20 日形成的震荡区间 [下沿 L, 上沿 U]。反复做T即在此区间内高抛低吸。箱体高度=(U−L)/L，15%~45% 最佳。",
    "箱内位置": "现价在箱体中的百分位：0=贴下沿(低吸区)，100=贴上沿(高抛区)，50=中枢。理想做T在 20%~80% 区间。",
    "均线斜率": "MA20 近 5 日的变化率（%）。越接近 0 说明越横盘、越适合网格；绝对值大说明在走趋势，做T易做反。",
    "机构底仓": "公募基金持有十大流通股比例（季度数据）。底仓越重，箱体下沿支撑越强，做T越安全。",
    "顶级机构": "社保 / 养老 / 年金 / 险资 / 汇金 / 证金 / QFII 是否出现在十大流通股东。出现即视为强底仓信号。",
    "类型": "网格型 = 箱体清晰、均线粘合，适合机械网格高抛低吸；波段型 = 有一定趋势/箱体较宽，适合按支撑压力几日一循环。",
    "网格档": "把箱体 [L,U] 均分为 5 档，给出每档的价格与建议动作。下跌触及买入档分批接、上涨触及卖出档分批抛，机械执行。",
    "底仓/滚动": "机构常用『底仓+卫星仓』：底仓不动吃趋势/分红，用卫星(滚动)仓反复做T摊低成本。A股 T+1，做T必须先有底仓。",
    "波段买区": "回落至支撑位附近的吸纳区间（支撑取箱体下沿与 MA20 的较高者）。",
    "波段卖区": "反弹至箱体上沿附近的减持区间。",
    "止损": "做T的纪律线：收盘跌破箱体下沿一定比例（通常 4%~6%）即无条件清仓，避免『越补越亏』。",
    "失效条件": "出现以下任一即停止做T：放量破箱体下沿、MA20 拐头向下走成空头排列、出现解禁/减持公告。",
    "成交额": "当日成交金额。做T需足够流动性，日成交额建议 ≥3 亿，否则买卖冲击成本高。",
    "风险": "风险扣分：跌破 MA60、RSI 超买、接近一年高位、成交额不足、命中解禁/减持名单等。",
    "评级": "做T池评分模型各维度的权重与口径说明。",
    "方法论": "本页采用顶级机构常用的四类方法：网格交易、均值回归、底仓+卫星仓、波动率套利，均服务于『在震荡区间反复降低持仓成本』。",
    "RSI": "14 日相对强弱指标。做T标的宜处于 35~70 的健康区间；<30 超卖(可低吸)、>75 超买(宜高抛)。",
    "波动稳定": "近 20 日振幅的变异系数（标准差/均值）。越低说明波动越规律、越可预期，做T节奏越好把握。",
}


def tip_t(key):
    t = TIPS.get(key)
    return f" title='{esc(t)}'" if t else ""


def tip(key, cls="tip"):
    t = TIPS.get(key)
    if not t:
        return ""
    return f" class='{cls}' title='{esc(t)}'"


STYLE = """
:root{--bg:#f5f6f8;--card:#fff;--tx:#23262b;--sub:#6b7280;--gold:#b8893b;--red:#b8332a;--green:#1a9e5a;--line:#e6e8eb;}
*{box-sizing:border-box;}
body{margin:0;background:var(--bg);color:var(--tx);font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;font-size:14px;line-height:1.6;}
.wrap{max-width:1180px;margin:0 auto;padding:26px 20px 60px;}
.topnav{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:18px;}
.topnav a{font-size:12.5px;color:#7a5a1f;background:#fff;border:1px solid #e7dcc4;border-radius:20px;padding:5px 12px;text-decoration:none;}
.topnav a:hover{background:#faf3e4;}
.topnav a.cur{background:linear-gradient(135deg,#c79a44,#a97b2e);color:#fff;border-color:transparent;}
header{background:linear-gradient(135deg,#fdf8ef,#f7efe0);border:1px solid #ecdfc6;border-radius:16px;padding:22px 24px;margin-bottom:18px;}
header h1{margin:0 0 6px;font-size:26px;background:linear-gradient(135deg,#c79a44,#8f6420);-webkit-background-clip:text;background-clip:text;color:transparent;}
header .sub{color:var(--sub);font-size:13px;}
.section{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:18px 20px;margin-bottom:16px;}
.section h2{margin:0 0 12px;font-size:17px;padding-left:10px;border-left:4px solid var(--gold);}
.note{background:#fbf9f4;border:1px solid #efe6d4;border-radius:10px;padding:12px 14px;color:#5c5648;font-size:13px;margin-bottom:14px;}
table{width:100%;border-collapse:collapse;font-size:13px;}
th,td{padding:8px 8px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap;}
th:first-child,td:first-child,th:nth-child(2),td:nth-child(2){text-align:left;}
thead th{background:#faf7f0;color:#7a5a1f;font-weight:600;position:sticky;top:0;}
tbody tr:hover{background:#fdfaf3;}
.up{color:var(--red);} .down{color:var(--green);} .muted{color:var(--sub);} .dim{color:#9aa3ad;}
.badge{display:inline-block;min-width:20px;text-align:center;border-radius:6px;padding:1px 7px;font-size:12px;font-weight:700;color:#fff;}
.bA{background:#b8332a;} .bB{background:#d98a26;} .bC{background:#7a8aa0;} .bD{background:#c2c7cd;}
.tag{display:inline-block;font-size:11.5px;border-radius:6px;padding:1px 7px;margin-right:4px;}
.tgrid{background:#eef4ec;color:#2f6b46;border:1px solid #d6e6da;}
.tswing{background:#eef1f8;color:#3b4f86;border:1px solid #d9e0f0;}
.tinst{background:#fbf3e3;color:#8a5d16;border:1px solid #efe0bf;}
.cards{display:grid;grid-template-columns:1fr 1fr;gap:14px;}
.card{border:1px solid var(--line);border-radius:12px;padding:14px 16px;background:#fff;}
.card .hd{display:flex;align-items:center;gap:8px;margin-bottom:8px;}
.card .nm{font-size:16px;font-weight:700;}
.card .cd{color:var(--sub);font-size:12px;}
.grid2{display:grid;grid-template-columns:repeat(3,1fr);gap:8px 12px;margin:8px 0;}
.kv{background:#fafbfc;border:1px solid #eef0f2;border-radius:8px;padding:6px 9px;}
.kv .k{color:var(--sub);font-size:11.5px;}
.kv .v{font-size:14px;font-weight:600;}
.kv .k.tipk::after{content:"?";display:inline-block;margin-left:3px;font-size:9px;color:var(--gold);border:1px solid rgba(184,137,59,.5);border-radius:50%;width:11px;height:11px;line-height:10px;text-align:center;}
.gtable{width:100%;font-size:12.5px;border-collapse:collapse;margin-top:6px;}
.gtable th,.gtable td{padding:4px 6px;text-align:center;border-bottom:1px dashed #eceef0;}
.gbuy{color:var(--green);font-weight:600;} .gsell{color:var(--red);font-weight:600;}
.sig{font-size:12.5px;color:#4b5563;margin-top:6px;}
.tip{cursor:help;border-bottom:1px dotted #c3cad3;}
.kv.tipbox:hover{background:#fdf8ef;}
footer{text-align:center;color:#9aa3ad;font-size:12px;margin-top:24px;}
@media(max-width:760px){.cards{grid-template-columns:1fr;}.wrap{padding:18px 12px 44px;}table{font-size:12px;}}
"""


def nav(cur="tplus"):
    from _nav import topnav
    return topnav(current_web_dir="tplus", home="../../index.html")


# ---------------- 指标计算 ----------------
def calc_metrics(code, u, q, nodes):
    # nodes: 日期倒序，nodes[0] 最新
    if not nodes or len(nodes) < 30:
        return None
    closes = [n.get("last") for n in nodes]
    highs = [n.get("high") for n in nodes]
    lows = [n.get("low") for n in nodes]
    amts = [n.get("amount") or 0 for n in nodes]
    if any(c is None for c in closes[:25]) or any(h is None for h in highs[:25]):
        return None
    price = closes[0]

    def ma(arr, n):
        return sum(arr[:n]) / n if len(arr) >= n else None

    ma5, ma10, ma20, ma60 = ma(closes, 5), ma(closes, 10), ma(closes, 20), ma(closes, 60)
    ma20_prev = sum(closes[5:25]) / 20 if len(closes) >= 25 else None
    slope = (ma20 - ma20_prev) / ma20_prev * 100 if (ma20 and ma20_prev) else 0.0

    # 箱体（近20日）
    box_high = max(highs[:20]); box_low = min(lows[:20])
    box_h = (box_high - box_low) / box_low * 100 if box_low else 0
    pos = (price - box_low) / (box_high - box_low) * 100 if box_high > box_low else 50

    # ATR14
    trs = []
    for i in range(min(14, len(nodes) - 1)):
        h, l, pc = highs[i], lows[i], closes[i + 1]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    atr = sum(trs) / len(trs) if trs else 0
    atr_pct = atr / price * 100 if price else 0

    # 近20日平均振幅
    amps = []
    for i in range(min(20, len(nodes) - 1)):
        pc = closes[i + 1]
        if pc:
            amps.append((highs[i] - lows[i]) / pc * 100)
    amp20 = sum(amps) / len(amps) if amps else 0
    amp_cv = 0.0
    if len(amps) > 2:
        m = amp20
        sd = (sum((x - m) ** 2 for x in amps) / len(amps)) ** 0.5
        amp_cv = sd / m if m else 0

    # BOLL 带宽
    bstd = 0.0
    if ma20:
        bstd = (sum((c - ma20) ** 2 for c in closes[:20]) / 20) ** 0.5
    bwidth = 4 * bstd / ma20 * 100 if ma20 else 0

    # 均线粘合度
    ma_list = [x for x in (ma5, ma10, ma20) if x]
    cohesion = (max(ma_list) - min(ma_list)) / ma20 * 100 if ma20 and ma_list else 0

    # RSI14
    gains = losses = 0.0
    for i in range(14):
        d = closes[i] - closes[i + 1]
        if d >= 0:
            gains += d
        else:
            losses -= d
    rsi = 100 - 100 / (1 + (gains / losses)) if losses > 0 else (100 if gains > 0 else 50)

    amt_yi = (sum(amts[:20]) / 20) / 1e8

    h52 = q.get("high_52week") or box_high
    l52 = q.get("low_52week") or box_low
    pos52 = (price - l52) / (h52 - l52) * 100 if h52 > l52 else 50

    return {
        "code": code, "name": q.get("name") or u.get("name"), "industry": u.get("industry"),
        "price": price, "chg": q.get("change_percent"),
        "turn": q.get("turnover_rate"), "vratio": q.get("volume_ratio"),
        "amount": q.get("amount"), "amt_yi": amt_yi,
        "cmc_yi": (q.get("circulating_market_cap") or 0) / 1e8,
        "pe": q.get("pe_ratio"), "pb": q.get("pb_ratio"),
        "ma5": ma5, "ma10": ma10, "ma20": ma20, "ma60": ma60, "slope": slope,
        "box_high": box_high, "box_low": box_low, "box_h": box_h, "pos": pos,
        "atr_pct": atr_pct, "amp20": amp20, "amp_cv": amp_cv, "bwidth": bwidth,
        "cohesion": cohesion, "rsi": rsi, "pos52": pos52,
        "fund_ratio": u.get("fund_ratio"), "top_inst": u.get("top_inst"),
        "chg20": q.get("chg_20d"), "chg60": q.get("chg_60d"),
    }


def load_risk_sets(date):
    def rd(name):
        p = os.path.join(PICKS, name)
        if not os.path.exists(p):
            return set()
        try:
            j = json.load(open(p, encoding="utf-8"))
        except Exception:
            return set()
        out = set()
        if isinstance(j, list):
            for it in j:
                if isinstance(it, dict):
                    c = it.get("code") or it.get("symbol")
                    if c:
                        out.add(c)
        elif isinstance(j, dict):
            for k, v in j.items():
                if k.startswith(("sh", "sz", "bj")):
                    out.add(k)
        return out
    return rd(f"events_unlock_{date}.json"), rd(f"events_reduce_{date}.json")


def score(m, unlock, reduce):
    detail = {}
    comp = 0.0

    # 波动性 30（取 ATR% 与 20日振幅的较大者；满分区间 5%~7% 最理想）
    wave = max(m["atr_pct"], m["amp20"])
    s_wave = band(wave, 5.0, 7.0, 3.0, 10.5, 30)
    detail["波动"] = round(s_wave, 1); comp += s_wave

    # 流动性 20
    s_turn = band(m["turn"], 4.5, 12.0, 2.0, 19.0, 10)
    s_amt = band(m["amt_yi"], 4.0, 70.0, 2.0, 300.0, 10)
    detail["流动性"] = round(s_turn + s_amt, 1); comp += s_turn + s_amt

    # 区间结构 25
    s_box = band(m["box_h"], 18.0, 36.0, 9.0, 65.0, 10)
    s_pos = band(abs(m["pos"] - 50), 0.0, 18.0, 0.0, 46.0, 10)
    s_ma = band(abs(m["slope"]), 0.0, 1.5, 0.0, 6.0, 5)
    detail["区间结构"] = round(s_box + s_pos + s_ma, 1); comp += s_box + s_pos + s_ma

    # 机构底仓 15
    s_fund = band(m["fund_ratio"] or 0, 8.0, 25.0, 3.0, 40.0, 10)
    s_top = 5 if (m["top_inst"] or 0) >= 2 else (3 if (m["top_inst"] or 0) == 1 else 0)
    detail["机构底仓"] = round(s_fund + s_top, 1); comp += s_fund + s_top

    # 波动稳定性 10
    s_stab = band(m["amp_cv"], 0.0, 0.32, 0.0, 0.85, 10)
    detail["稳定性"] = round(s_stab, 1); comp += s_stab

    # 风险扣分
    pen = 0.0
    notes = []
    if m["ma60"] and m["price"] < m["ma60"]:
        pen += 6; notes.append("跌破 MA60")
    if m["pos52"] > 90:
        pen += 4; notes.append("接近一年高位")
    if m["rsi"] > 76:
        pen += 4; notes.append("RSI 超买")
    if m["box_h"] > 70:
        pen += 3; notes.append("箱体过宽近趋势")
    if m["amt_yi"] < 2:
        pen += 3; notes.append("成交额不足")
    if m["code"] in unlock:
        pen += 8; notes.append("近期解禁")
    if m["code"] in reduce:
        pen += 6; notes.append("计划减持窗口")
    detail["风险"] = -round(pen, 1)

    total = clamp(comp - pen, 0, 100)
    if total >= 80:
        g, gname = "A", "可重点做T"
    elif total >= 70:
        g, gname = "B", "适合做T"
    elif total >= 60:
        g, gname = "C", "可小仓试"
    else:
        g, gname = "D", "不适合"
    return round(total, 1), g, gname, detail, notes


def plan_types(m):
    """判定主导做T类型"""
    grid = (15 <= m["box_h"] <= 48) and (abs(m["slope"]) <= 3.2) and (20 <= m["pos"] <= 80)
    return "网格型" if grid else "波段型"


def grid_levels(m):
    L, U = m["box_low"], m["box_high"]
    step = (U - L) / 4.0
    levels = []
    for i in range(5):
        p = L + step * i
        if i <= 1:
            act, cls = "分批买入", "gbuy"
        elif i == 2:
            act, cls = "中枢观望", "dim"
        else:
            act, cls = "分批卖出", "gsell"
        levels.append({"p": round(p, 2), "act": act, "cls": cls})
    return levels


def swing_plan(m):
    L, U = m["box_low"], m["box_high"]
    support = max(L, m["ma20"] if (m["ma20"] and m["ma20"] < m["price"]) else L)
    buy_lo, buy_hi = support, support * 1.02
    sell_lo, sell_hi = U * 0.98, U
    stop = L * 0.955
    return {"support": round(support, 2), "sell": round(U, 2),
            "buy_lo": round(buy_lo, 2), "buy_hi": round(buy_hi, 2),
            "sell_lo": round(sell_lo, 2), "sell_hi": round(sell_hi, 2),
            "stop": round(stop, 2)}


GRADE_POS = {"A": "底仓 40% + 滚动 30%", "B": "底仓 30% + 滚动 20%",
             "C": "底仓 20% + 滚动 10%", "D": "不建议建仓"}


def render_card(r):
    m = r["m"]; g = r["grade"]
    p = r["swing"]; levels = r["levels"]
    pos_txt = ("贴下沿·低吸区" if m["pos"] < 33 else ("贴中枢" if m["pos"] <= 66 else "贴上沿·高抛区"))
    inst_tags = ""
    if m["top_inst"]:
        inst_tags += f"<span class='tag tinst'>顶级机构×{m['top_inst']}</span>"
    inst_tags += f"<span class='tag tinst'>基金持股 {fnum(m['fund_ratio'],1)}%</span>"
    typ = r["ptype"]
    tcls = "tgrid" if typ == "网格型" else "tswing"
    gl = "".join(
        f"<tr><td>{i+1}</td><td>{fnum(l['p'])}</td><td class='{l['cls']}'>{l['act']}</td></tr>"
        for i, l in enumerate(levels))
    notes = ("<div class='sig'>⚠ " + esc("、".join(r["notes"])) + "</div>") if r["notes"] else ""
    sigs = r["sigs"]
    sigs_html = "".join(f"<span class='tag tinst'>{esc(s)}</span>" for s in sigs)
    det = " · ".join(f"{k} {v}" for k, v in r["detail"].items())
    return f"""
  <div class='card'>
    <div class='hd'>
      <span class='nm'>{esc(m['name'])}</span>
      <span class='cd'>{esc(m['code'])} · {esc(m['industry'])}</span>
      <span class='badge b{g}'{tip_t('档位')}>{g}</span>
      <span style='margin-left:auto' class='cd'{tip_t('做T分')}>做T分 <b style='color:#b8892b'>{r['score']}</b></span>
    </div>
    <div>{inst_tags}<span class='tag {tcls}'{tip_t('类型')}>{typ}</span>{sigs_html}</div>
    <div class='grid2'>
      <div class='kv tipbox'{tip_t('现价')}><div class='k tipk'>现价</div><div class='v'>{fnum(m['price'])} <span class='{"up" if (m["chg"] or 0)>=0 else "down"}' style='font-size:11px'>{pct(m['chg'])}</span></div></div>
      <div class='kv tipbox'{tip_t('日内振幅')}><div class='k tipk'>振幅/ATR</div><div class='v sm'>{fnum(m['amp20'],1)}% / {fnum(m['atr_pct'],1)}%</div></div>
      <div class='kv tipbox'{tip_t('换手')}><div class='k tipk'>换手/量比</div><div class='v sm'>{fnum(m['turn'],1)}% / {fnum(m['vratio'],2)}</div></div>
      <div class='kv tipbox'{tip_t('箱体')}><div class='k tipk'>箱体 [下沿~上沿]</div><div class='v sm'>{fnum(m['box_low'])} ~ {fnum(m['box_high'])} <span class='dim'>({fnum(m['box_h'],0)}%)</span></div></div>
      <div class='kv tipbox'{tip_t('箱内位置')}><div class='k tipk'>箱内位置</div><div class='v sm'>{fnum(m['pos'],0)}% · {pos_txt}</div></div>
      <div class='kv tipbox'{tip_t('均线斜率')}><div class='k tipk'>MA20 斜率</div><div class='v sm'>{pct(m['slope'])}</div></div>
    </div>
    <div class='sig'><b class='tip' title='{esc(TIPS.get('底仓/滚动',''))}'>仓位建议：</b>{esc(GRADE_POS[g])}</div>
    <table class='gtable'>
      <thead><tr><th{tip_t('网格档')}>网格档</th><th>价格</th><th>动作</th></tr></thead>
      <tbody>{gl}</tbody>
    </table>
    <div class='sig'><b{tip_t('波段买区')}>波段做T：</b>买区 {fnum(p['buy_lo'])}~{fnum(p['buy_hi'])}｜卖区 {fnum(p['sell_lo'])}~{fnum(p['sell_hi'])}｜<span class='down'><b{tip_t('止损')}>止损 {fnum(p['stop'])}</b></span>（持有 3~7 日）</div>
    <div class='sig'><b>打分：</b>{esc(det)} · <span{tip('风险')}>风险 {r['pen']}</span></div>
    {notes}
    <div class='sig dim'><b{tip_t('失效条件')}>失效：</b>放量跌破 {fnum(p['stop'])} 或 MA20 拐头向下 → 停做T。</div>
  </div>"""


def build(date):
    uj = os.path.join(DATA, f"universe_{date}.json")
    qj = os.path.join(DATA, f"quotes_{date}.json")
    kj = os.path.join(DATA, f"kline_{date}.json")
    for p in (uj, qj, kj):
        if not os.path.exists(p):
            print(f"[build_tplus] 缺少 {p}"); sys.exit(1)
    universe = json.load(open(uj, encoding="utf-8"))
    quotes = json.load(open(qj, encoding="utf-8"))
    kline = json.load(open(kj, encoding="utf-8"))
    unlock, reduce = load_risk_sets(date)

    rows = []
    for u in universe:
        code = u["code"]
        nodes = kline.get(code)
        q = quotes.get(code)
        if not nodes or not q:
            continue
        m = calc_metrics(code, u, q, nodes)
        if not m:
            continue
        # 硬门槛（与预筛一致）
        nm = m["name"] or ""
        if "ST" in nm or "退" in nm or m["price"] < 3:
            continue
        if not (20 <= m["cmc_yi"] <= 1200):
            continue
        if not (2 <= (m["turn"] or 0) <= 20):
            continue
        if m["amp20"] < 3.0 or max(m["atr_pct"], m["amp20"]) < 3.0:
            continue
        if (m["chg60"] or 0) < -30 or (m["chg20"] or 0) > 60:
            continue
        if not (12 <= m["pos52"] <= 92):
            continue
        if not (8 <= m["box_h"] <= 75):
            continue

        total, g, gname, detail, notes = score(m, unlock, reduce)
        ptype = plan_types(m)
        sigs = []
        if m["amp20"] >= 4:
            sigs.append(f"高振幅 {m['amp20']:.1f}%")
        if m["top_inst"]:
            sigs.append("顶级机构底仓")
        if m["fund_ratio"] and m["fund_ratio"] >= 10:
            sigs.append(f"公募重仓 {m['fund_ratio']:.0f}%")
        if abs(m["slope"]) <= 1.5:
            sigs.append("MA20 走平")
        if 35 <= m["rsi"] <= 70:
            sigs.append(f"RSI {m['rsi']:.0f}")
        rows.append({
            "code": code, "name": m["name"], "industry": m["industry"],
            "m": m, "score": total, "grade": g, "gname": gname,
            "detail": detail, "pen": detail["风险"], "notes": notes,
            "ptype": ptype, "levels": grid_levels(m), "swing": swing_plan(m), "sigs": sigs,
        })

    rows.sort(key=lambda r: r["score"], reverse=True)
    abc = [r for r in rows if r["grade"] in ("A", "B")][:45]
    top = rows[:60]

    # 历史
    hist = []
    if os.path.exists(HIST):
        try:
            hist = json.load(open(HIST, encoding="utf-8"))
        except Exception:
            hist = []
    hist = [h for h in hist if h.get("date") != date]
    hist.append({"date": date, "total": len(rows),
                 "A": sum(1 for r in rows if r["grade"] == "A"),
                 "B": sum(1 for r in rows if r["grade"] == "B"),
                 "C": sum(1 for r in rows if r["grade"] == "C"),
                 "grid": sum(1 for r in rows if r["ptype"] == "网格型"),
                 "swing": sum(1 for r in rows if r["ptype"] == "波段型")})
    hist.sort(key=lambda h: h["date"])
    json.dump(hist, open(HIST, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    na = sum(1 for r in rows if r["grade"] == "A")
    nb = sum(1 for r in rows if r["grade"] == "B")
    nc = sum(1 for r in rows if r["grade"] == "C")
    ng = sum(1 for r in rows if r["ptype"] == "网格型")

    thead = ("<thead><tr>"
             + f"<th{tip('做T分')}>分</th>"
             + f"<th{tip('名称') if '名称' in TIPS else ''}>名称</th><th>代码</th><th>行业</th>"
             + f"<th{tip('类型')}>类型</th>"
             + f"<th{tip('现价')}>现价</th>"
             + f"<th{tip('日内振幅')}>振幅%</th>"
             + f"<th{tip('ATR%')}>ATR%</th>"
             + f"<th{tip('换手')}>换手%</th>"
             + f"<th{tip('箱体')}>箱体下~上</th>"
             + f"<th{tip('箱内位置')}>箱位%</th>"
             + f"<th{tip('均线斜率')}>MA20斜率</th>"
             + f"<th{tip('机构底仓')}>基金%</th>"
             + f"<th{tip('档位')}>档</th></tr></thead>")

    def row_html(r):
        m = r["m"]
        return (f"<tr><td><b>{r['score']}</b></td><td>{esc(m['name'])}</td>"
                f"<td class='muted'>{esc(m['code'])}</td><td>{esc(m['industry'] or '—')}</td>"
                f"<td>{esc(r['ptype'])}</td>"
                f"<td>{fnum(m['price'])} <span class='{'up' if (m['chg'] or 0)>=0 else 'down'}' style='font-size:11px'>{pct(m['chg'])}</span></td>"
                f"<td>{fnum(m['amp20'],1)}</td><td>{fnum(m['atr_pct'],1)}</td>"
                f"<td>{fnum(m['turn'],1)}</td>"
                f"<td>{fnum(m['box_low'])}~{fnum(m['box_high'])}</td>"
                f"<td>{fnum(m['pos'],0)}</td><td>{pct(m['slope'])}</td>"
                f"<td>{fnum(m['fund_ratio'],1)}</td>"
                f"<td><span class='badge b{r['grade']}'{tip_t('档位')}>{r['grade']}</span></td></tr>")

    table_html = "".join(row_html(r) for r in top)
    cards_html = "".join(render_card(r) for r in abc)

    hist_rows = "".join(
        f"<tr><td>{esc(h['date'])}</td><td>{h['total']}</td><td>{h['A']}</td>"
        f"<td>{h['B']}</td><td>{h['C']}</td><td>{h['grid']}</td><td>{h['swing']}</td></tr>"
        for h in hist[-15:][::-1])

    body = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>做T池 · {date} · A股分析中心</title>
<style>{STYLE}</style></head>
<body><div class='wrap'>
{nav('tplus')}
<header>
  <h1>做T池（可反复做T候选）</h1>
  <div class='sub'>从「机构底仓池」中筛出<b>高波动 + 高流动性 + 区间震荡 + 有机构底仓支撑</b>的标的，
  按顶级机构常用的<b>网格交易 / 均值回归 / 底仓+卫星仓 / 波动率套利</b>方法给出网格档位与波段买卖点。数据日期 <b>{date}</b>。</div>
</header>

<div class='note'><b>今日结论：</b>入选 {len(rows)} 只（A {na} / B {nb} / C {nc}，其中网格型 {ng} 只）。
做T前请先确认已有底仓（A股 T+1）；<b>单次做T亏损控制在总资金 0.5% 以内</b>，破箱体下沿即停。</div>

<div class='section'><h2>做T榜单</h2>
<table>{thead}<tbody>{table_html or "<tr><td colspan='14' class='dim'>今日无符合条件标的</td></tr>"}</tbody></table></div>

<div class='section'><h2>逐只操作手册（A/B 档 · 前 45 只）</h2>
<div class='note'>每只给出网格 5 档价位与动作、波段买卖区与止损、仓位建议。表格中数字均可悬浮查看口径。</div>
<div class='cards'>{cards_html or "<div class='dim'>今日无 A/B/C 档标的</div>"}</div></div>

<div class='section'><h2>方法论：顶级机构如何做T</h2>
<div class='note'><b>1. 网格交易法</b>——在预设价格网格上机械高抛低吸，不预测方向，赚取波动本身。前提是标的处于<b>区间震荡</b>且波动率充足。
<b>2. 均值回归</b>——价格围绕箱体中枢（机构成本区）往复，偏离越远回归动力越强。
<b>3. 底仓 + 卫星仓</b>——底仓不动（吃趋势/分红），仅用卫星仓反复做T摊低成本；A股 T+1，做T必须先有底仓。
<b>4. 波动率套利</b>——日振幅/ATR 越大，单次做T的价差空间越大。<br>
<b>纪律</b>：破箱体下沿无条件清仓；单次做T亏损 ≤ 总资金 0.5%；不追高、不满仓滚动。</div>
<table><thead><tr><th>维度</th><th>满分</th><th>口径</th></tr></thead><tbody>
<tr><td>波动性</td><td>30</td><td>近20日平均振幅 与 ATR%(14) 取大者，3.5%~9% 满分（<3% 无做T价值，>10% 易单边）</td></tr>
<tr><td>流动性</td><td>20</td><td>换手率 3%~15%（10分）+ 日均成交额 ≥3亿（10分）</td></tr>
<tr><td>区间结构</td><td>25</td><td>箱体高度 15%~45%（10分）+ 现价靠中枢（10分）+ MA20 走平（5分）</td></tr>
<tr><td>机构底仓</td><td>15</td><td>公募持股 5%~25%（10分）+ 社保/险资 ≥2 家（5分）</td></tr>
<tr><td>波动稳定性</td><td>10</td><td>近20日振幅变异系数越低越好（波动规律、节奏可把握）</td></tr>
<tr><td>风险扣分</td><td>−≤32</td><td>破MA60 −6、近一年高位 −4、RSI超买 −4、箱体过宽 −3、成交额不足 −3、解禁 −8、减持 −6</td></tr>
</tbody></table></div>

<div class='section'><h2>历史归档</h2>
<table><thead><tr><th>日期</th><th>入选</th><th>A</th><th>B</th><th>C</th><th>网格型</th><th>波段型</th></tr></thead>
<tbody>{hist_rows or "<tr><td colspan='7' class='dim'>暂无</td></tr>"}</tbody></table></div>

<footer>本页为规则化量化输出，不构成投资建议。数据来源：westock（行情/技术/K线）+ 2026-Q2 十大流通股东。
做T有风险，务必先有底仓、严设止损。</footer>
</div></body></html>"""

    os.makedirs(WEB, exist_ok=True)
    p_index = os.path.join(WEB, "index.html")
    p_date = os.path.join(WEB, f"tplus-{date}.html")
    open(p_index, "w", encoding="utf-8").write(body)
    open(p_date, "w", encoding="utf-8").write(body)
    print(f"[build_tplus] {date}: 入选 {len(rows)}（A {na}/B {nb}/C {nc}，网格型 {ng}）")
    print(f"  → {p_index}")
    print(f"  → {p_date}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=datetime.date.today().strftime("%Y-%m-%d"))
    a = ap.parse_args()
    build(a.date)
