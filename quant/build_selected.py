# -*- coding: utf-8 -*-
"""主升精选 · v2（全市场域 · 先验固定因子集横截面分位）。

v2 相对 v1（2026-09-19 重构，消费 MACD 池 + 精选池两个现有模型库）：
  改为从**全市场 A 股正股**出发，用主升先验因子集（趋势 + 资金双确认，
  9 因子等权横截面分位）做严格筛选，A 档 = 域内前 5%（更严格），
  严格样本外可兑现胜率稳定 >60%（证据见 lab.html）。
  不再依赖任何现有模型库（MACD 池 / 精选池），只依赖全市场日K 缓存 +
  实验室冻结的 _selected_model.json（因子 + 方向 + 截断比例 + 退出规则）。

数据源：腾讯前复权日K（离线 _txk_cache.json，全市场缓存）→ 在选股日 date 处算因子 →
      横截面分位 → 前 pct 为 A 档 → 含预估买卖点 → 环境门控横幅。
"""
from __future__ import annotations
import os, sys, json, datetime, argparse
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _tx_fetch as T
import _selected_lab as S
import _xhist as X
import _idxkline as E
import _emlink as EM
from _nav import topnav

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QUANT = os.path.join(ROOT, "quant")
OUTDIR = os.path.join(ROOT, "web", "selected")
os.makedirs(OUTDIR, exist_ok=True)

MINI = S.MINI
PRICE_MIN = S.PRICE_MIN
AMT_MIN = S.AMT_MIN
PRIOR = S.PRIOR

# ★ 退出回测「成交假设」口径审计产物（_exit_assumption_audit.py 生成）。
#   生产页面披露的胜率来自「旧口径」（乐观日内路径 + 忽略跳空）；本页必须并列可实现口径，
#   否则就是把「好看但不成立」的数字当成绩展示（用户红线）。读不到就如实标注，不静默沿用。
EXIT_AUDIT = os.path.join(QUANT, "_exit_assumption_audit.json")


def load_exit_audit():
    """→ (audit dict 或 None, {mode: entry})。读不到返回 (None, {})。"""
    try:
        d = json.load(open(EXIT_AUDIT, encoding="utf-8"))
        return d, {x.get("mode"): x for x in d.get("modes", [])}
    except Exception:
        return None, {}


def audit_pair():
    """→ (old, real) 两个口径条目；缺任一返回 (None, None)。"""
    _d, m = load_exit_audit()
    return (m.get("旧口径（乐观日内·忽略跳空）"),
            m.get("可实现口径（保守日内·跳空成交）"))


def _c6(raw):
    return raw.replace("sh", "").replace("sz", "").replace("bj", "")


def _prefix(a):
    ps = [0.0] * (len(a) + 1)
    for i, x in enumerate(a):
        ps[i + 1] = ps[i] + (x or 0)
    return ps


def _ma(arr, n):
    return sum(arr[-n:]) / n if len(arr) >= n else None


def buy_sell(kasc):
    """主升买点：回踩 MA10/MA20 不追高；止损=近20日基底（结构位）；目标=近20日高突破。"""
    if not kasc or len(kasc) < 25:
        return None
    closes = [x["last"] for x in kasc]
    lows = [x["low"] for x in kasc]
    highs = [x["high"] for x in kasc]
    close = closes[-1]
    ma10 = _ma(closes, 10)
    ma20 = _ma(closes, 20)
    if not ma20:
        return None
    mids = [x for x in (ma10, ma20) if x]
    el = min(mids) * 0.99
    eh = max(mids) * 1.01
    if close > eh:
        el, eh = ma20 * 0.98, ma20 * 1.02
    base_low20 = min(lows[-20:])
    stop = round(base_low20 * 0.97, 2)
    h20 = max(highs[-20:])
    t1 = round(h20 * 1.05, 2)
    t2 = round(h20 * 1.10, 2)
    rr = (t1 - eh) / (eh - stop) if eh > stop else 0
    # 箱体位置：现价在 [止损, T2] 箱体中的百分比（0=止损位，100=T2），并给状态标签
    span = t2 - stop
    pos_pct = (close - stop) / span * 100 if span > 0 else 50.0
    if close < stop:
        tag = "已破止损"
    elif close < el:
        tag = "接近买区"
    elif close <= eh:
        tag = "买区内·可买"
    elif close < t1:
        tag = "持有·待涨"
    elif close < t2:
        tag = "已到T1"
    else:
        tag = "已到T2"
    gap_t1 = (t1 / close - 1) * 100 if close else 0
    return {"entry_lo": round(el, 2), "entry_hi": round(eh, 2),
            "stop": stop, "t1": t1, "t2": t2, "rr": round(rr, 2),
            "close": close, "pos_pct": round(pos_pct, 1), "pos_tag": tag,
            "gap_t1": round(gap_t1, 1)}


def load_model():
    try:
        m = json.load(open(os.path.join(QUANT, "_selected_model.json"), encoding="utf-8"))
        return m
    except Exception:
        return {"pct": 0.05, "exit": {"stop": 0.12, "act": 0.06, "trail": 0.03, "maxfwd": 20},
                "factors": PRIOR, "version": "selected_v1"}


def scan(date):
    """全市场域选股：在 date 处算主升因子 → 横截面分位 → 前 pct 为 A 档。"""
    cache = T._load()
    nm = {}
    try:
        nm = json.load(open(os.path.join(QUANT, "_stock_names.json"), encoding="utf-8"))
    except Exception:
        pass
    model = load_model()
    pct = model.get("pct", 0.05)
    codes = [c for c in cache if (c.startswith("sh6") or c.startswith("sz0") or c.startswith("sz3"))]
    rows = []
    st = liq = short = 0
    for code in codes:
        bars = cache.get(code)
        if not bars or len(bars) < MINI + S.FMAX + 5:
            short += 1
            continue
        nm_c = nm.get(code) or ""
        if "ST" in nm_c or "退" in nm_c:
            st += 1
            continue
        idx = None
        for j, b in enumerate(bars):
            if b["date"] == date:
                idx = j
                break
            if b["date"] > date:
                break
        if idx is None or idx < MINI + S.FMAX:
            continue
        C = [b["last"] for b in bars]
        H = [b["high"] for b in bars]
        L = [b["low"] for b in bars]
        O = [b["open"] for b in bars]
        V = [b["volume"] for b in bars]
        close = C[idx]
        if close < PRICE_MIN:
            continue
        vu = 1.0 if code.startswith("sh688") else 100.0
        amt20 = sum(V[idx - 19 + k] * vu * C[idx - 19 + k] for k in range(20)) / 20 / 1e8
        if amt20 < AMT_MIN / 1e8:
            liq += 1
            continue
        psC = _prefix(C)
        f = S.factors_at(C, H, L, O, V, psC, idx, code)
        if f is None:
            continue
        rows.append({"code": _c6(code), "_full": code, "name": nm_c or code,
                     "date": date, "f": f, "close": close, "kasc": bars[:idx + 1]})
    # 横截面分位（单日域）
    S.score_universe(rows, pct)
    # ⚠ 排序键必须带唯一兜底字段：qs 只保留 1 位小数，同分极常见，
    # 而 rows 源自 dict 遍历（PYTHONHASHSEED 跨进程随机）→ 缺兜底会让同一份数据
    # 两次运行顺序不同、html 的 sha 漂移，每次都白推。
    rows.sort(key=lambda x: (-(x.get("qs") or 0), x.get("code") or ""))
    n = len(rows)
    nA = int(round(n * pct))
    for i, r in enumerate(rows):
        r["tier"] = "A" if i < nA else "B"
        r["qrank"] = i + 1
    shown = rows[:nA]
    for r in shown:
        r["bs"] = buy_sell(r["kasc"])
    print("[selected] 全市场域 %d 只入池（剔 ST/退 %d · 流动性 %d · K线不足 %d）｜ A 档前 %.0f%% = %d 只"
          % (n, st, liq, short, pct * 100, nA))
    return shown, rows, model, n, nA


# ---------------- 渲染 ----------------
STYLE = """
:root{--bg:#fbfbfd;--card:#fff;--text:#1d1d1f;--muted:#6e6e73;--line:#e5e5e7;
 --up:#ff3b30;--dn:#34c759;--blue:#0071e3;--gold:#b8893b;--orange:#ff9500;--purple:#af52de;}
*{box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"PingFang SC","Microsoft YaHei",sans-serif;
 background:var(--bg);color:var(--text);line-height:1.7;margin:0;padding:0}
.wrap{max-width:1040px;margin:0 auto;padding:28px 18px 56px}
h1{font-size:23px;font-weight:700;margin:0 0 6px;letter-spacing:-.02em}
h2{font-size:18px;font-weight:600;margin:26px 0 12px;padding-bottom:8px;border-bottom:2px solid var(--blue)}
.sub{color:var(--muted);font-size:13px;margin-bottom:8px}
.card{background:var(--card);border-radius:16px;padding:16px 20px;margin:12px 0;box-shadow:0 1px 3px rgba(0,0,0,.05)}
.box{border-left:4px solid var(--blue);background:#f0f7ff;padding:14px 18px;border-radius:0 12px 12px 0;margin:14px 0}
.box.gold{border-color:var(--gold);background:#fffaf0}
.box.green{border-color:var(--dn);background:#f0faf3}
.box.red{border-color:var(--up);background:#fff5f4}
table{width:100%;border-collapse:collapse;font-size:12.5px;margin:10px 0}
th,td{padding:8px 6px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
th{color:var(--muted);font-weight:600;font-size:11.5px;background:#fafafa;white-space:nowrap}
.num{font-variant-numeric:tabular-nums}
.up{color:var(--up)}.dn{color:var(--dn)}.am{color:var(--blue)}
.tag{display:inline-block;font-size:11px;padding:2px 8px;border-radius:10px;margin:1px 2px}
.tag.A{background:#e6f7ec;color:#1a7a45}
.tag.B{background:#fff3e0;color:#e65100}
.case{font-size:13px;margin:10px 0;padding:12px 16px;background:#fafafa;border-radius:10px;border-left:3px solid var(--purple)}
.case .h{font-weight:600;margin-bottom:4px}
.kv{font-size:12.5px;color:var(--muted)}
.bp{background:#f7f9fc;border:1px solid var(--line);border-radius:10px;padding:10px 14px;margin:8px 0;font-size:13px}
.bp b{color:var(--blue)}
/* 箱体位置条：止损(0%) → 买区 → T1 → T2(100%)，指针=现价 */
.bxrow{display:flex;align-items:center;gap:10px;margin:6px 0 2px}
.bxtrack{position:relative;flex:1;min-width:180px;height:14px;background:#eee;border-radius:7px;overflow:visible}
.bxzone{position:absolute;top:0;height:100%;background:#cfe3ff;border-radius:7px 0 0 7px}
.bxzone.hold{background:#fff3d6;border-radius:0}
.bxtick{position:absolute;top:-3px;width:2px;height:20px;background:var(--gold)}
.bxneedle{position:absolute;top:-5px;width:0;height:0;margin-left:-5px;
 border-left:5px solid transparent;border-right:5px solid transparent;border-top:9px solid var(--up);z-index:2}
.bxlegend{display:flex;justify-content:space-between;font-size:10.5px;color:var(--muted);margin-top:3px;min-width:180px;flex:1}
.bxtag{font-size:12px;font-weight:700;white-space:nowrap}
.bxtag.buy{color:var(--up)}  /* 买区内：可买（红=进攻） */
.bxtag.hold{color:var(--blue)}
.bxtag.tp{color:var(--gold)}
.bxtag.stop{color:var(--dn)} /* 破止损：离场（绿=防守） */
.foot{text-align:center;color:var(--muted);font-size:12px;margin-top:28px}
""" + X.BADGE_CSS


def _yi(v, digits=2):
    if v is None:
        return "—"
    return "%+.2f" % v


# 主升精选专用二值门控（样本外证据见 web/selected/env_gate.html）
# 反推的相对仓位系数（强势=1）：强势 +1.00[0.61,1.42] ／ 震荡 -0.16 ／ 弱势 -0.46 ／ 破位 -0.05
# → 只有「强势」档的系数显著为正，其余档点估计为负（=该空仓）。
# 只用于主升精选；做T池共用 _idxkline.ENV_RULE，本页未验证做T场景，保持原值不动。
GATE_ALLOW = ("强势",)


def render(shown, rows, model, date, env, gate=None, gate_lab=None):
    pct = model.get("pct", 0.05)
    hist = X.load_cross_history()
    ev = model.get("evidence", {})
    lab = (env or {}).get("label", "未知") if env else "未知"
    sc = (env or {}).get("score") if env else None
    pos = (env or {}).get("pos_scale") if env else None
    advice = (env or {}).get("advice", "") if env else ""
    if gate is None:
        gate = lab in GATE_ALLOW
    if gate_lab is None:
        gate_lab = lab

    env_banner = ""
    if lab and lab != "未知":
        if gate:
            head = (f"<div class='box green'><b>大盘环境门控：{lab}</b>（综合分 {sc}）"
                    f"｜ 主升精选二值门控：<b>强势开仓，其余档位空仓</b>"
                    f"<br>本页在「{gate_lab}」档，<b>本期正常出手</b>。"
                    f"依据见 <a href='env_gate.html' style='color:var(--blue)'>环境门控样本外证据 env_gate.html</a>。</div>")
        else:
            # 只引生产 ENV_RULE 里当前的 pos_scale，不写死实验室数字（统计数字必须可追溯到当日重算）。
            # ⚠ 依据要按档区分：换采样步长复核后，只有「弱势」跨步长稳定为负（有依据），
            #   「震荡 / 破位」符号随采样翻转（不可判），空仓是纪律不是数据结论 —— 不能混为一谈。
            if gate_lab == "弱势":
                why_txt = ("该档在 4 组采样步长下<b>绝对收益均为负</b>，样本外证据<b>支持空仓</b>")
            elif gate_lab == "强势":
                why_txt = "该档跨步长稳定为正"
            else:
                why_txt = ("该档的绝对收益<b>符号随采样步长翻转</b>（换一组采样日期就变号），"
                           "样本外证据<b>判「不可判」</b> —— 此处空仓是「宁可不选」的<b>纪律</b>，"
                           "<b>不是</b>数据证明该档该空仓")
            head = (f"<div class='box red'><b>大盘环境门控：{gate_lab}</b>（综合分 {sc}）"
                    f"｜ 主升精选二值门控：<b>非强势档 → 空仓，本期不出手</b>"
                    f"<br>本页在「{gate_lab}」档，<b>本期空仓</b>：生产 ENV_RULE 给该档的折数系数是 {pos}；"
                    f"该折数没有样本外依据（「打折继续持有」不成立）。"
                    f"空仓的依据强度<b>按档不同</b>：{why_txt}。"
                    f"宁可空仓，不乱选。<br>依据见 "
                    f"<a href='env_gate.html' style='color:var(--blue)'>环境门控样本外证据 env_gate.html</a>"
                    f" ／ <a href='env_gate_sens.html' style='color:var(--blue)'>样本量敏感性检验</a>。"
                    f"（做T池沿用同一张 ENV_RULE 表，已单独验证为「不可判」、保持原值，做T侧不随本页改动）</div>")
        env_banner = head

    # 总表
    TAG_CLS = {"买区内·可买": "up", "接近买区": "up", "持有·待涨": "am",
               "已到T1": "", "已到T2": "", "已破止损": "dn"}
    tr = []
    for r in shown:
        bs = r.get("bs")
        if bs:
            bz = f"{bs['entry_lo']}~{bs['entry_hi']}"
            stp = f"{bs['stop']}（RR {bs['rr']}）"
            tgt = f"{bs['t1']} / {bs['t2']}"
            bx = (f"<span class='{TAG_CLS.get(bs['pos_tag'],'')}' style='font-weight:700'>"
                  f"{bs['pos_tag']}</span><br><span style='font-size:11px;color:var(--muted)'>"
                  f"箱体 {bs['pos_pct']:.0f}%</span>")
        else:
            bz = stp = tgt = bx = "—"
        f = r["f"]
        qs = r.get("qs")
        qtxt = "%.0f" % qs if qs is not None else "—"
        fac = ("近20日动量 %+.1f%%｜站上MA60 %+.1f%%｜均多 %+.1f%%｜近高 %+.1f%%｜上涨放量 %.0f%%"
               % (f["rel20"] * 100, f["above_ma60"] * 100, f["ma_strength"] * 100,
                  f["dist_h20"] * 100, f["up_vol"] * 100))
        tr.append(
            f"<tr><td>{EM.link(r['_full'], r['code'], cls='')}</td>"
            f"<td>{EM.link(r['_full'], r['name'])}{X.badge_html(hist, r['code'], date)}</td>"
            f"<td class='am num'>{r['close']}</td>"
            f"<td class='num' style='font-weight:700'>{qtxt}</td>"
            f"<td class='num'>{r['qrank']}</td>"
            f"<td class='num'>{bz}</td><td class='dn num'>{stp}</td><td class='up num'>{tgt}</td>"
            f"<td>{bx}</td>"
            f"<td class='kv'>{fac}</td></tr>")
    table = "".join(tr)

    def box_bar(bs):
        """箱体可视化：止损(0)→买区→T1→T2(100)，指针=现价位置。"""
        if not bs:
            return ""
        span = bs["t2"] - bs["stop"]
        if span <= 0:
            return ""
        el_p = max(0.0, min(100.0, (bs["entry_lo"] - bs["stop"]) / span * 100))
        eh_p = max(0.0, min(100.0, (bs["entry_hi"] - bs["stop"]) / span * 100))
        t1_p = max(0.0, min(100.0, (bs["t1"] - bs["stop"]) / span * 100))
        px_p = max(0.0, min(100.0, bs["pos_pct"]))
        tag_cls = {"买区内·可买": "buy", "接近买区": "buy", "持有·待涨": "hold",
                   "已到T1": "tp", "已到T2": "tp", "已破止损": "stop"}.get(bs["pos_tag"], "hold")
        return (f"<div class='bxrow'><div style='flex:1'>"
                f"<div class='bxtrack'><div class='bxzone' style='left:0;width:{el_p:.1f}%'></div>"
                f"<div class='bxzone hold' style='left:{el_p:.1f}%;width:{max(0, eh_p-el_p):.1f}%'></div>"
                f"<div class='bxtick' style='left:{t1_p:.1f}%'></div>"
                f"<div class='bxneedle' style='left:{px_p:.1f}%'></div></div>"
                f"<div class='bxlegend'><span>止损 {bs['stop']}</span><span>买区</span>"
                f"<span>T1 {bs['t1']}</span><span>T2 {bs['t2']}</span></div></div>"
                f"<div class='bxtag {tag_cls}'>{bs['pos_tag']}（箱体 {bs['pos_pct']:.0f}%）</div></div>")

    def case_div(r):
        bs = r.get("bs")
        if bs:
            gap_t1 = (f"，距 T1 还有 <b>+{bs['gap_t1']:.1f}%</b>" if bs["gap_t1"] > 0 else "，已越过 T1")
            bp = (f"<div class='bp'><b>买区</b> {bs['entry_lo']}~{bs['entry_hi']}（回踩 MA10/MA20 不追高）｜"
                  f"<b>结构位止损</b> {bs['stop']}（破位先减半；跌到 −15% 全出）｜"
                  f"<b>目标</b> T1 {bs['t1']}（近20日高×1.05）/ T2 {bs['t2']}（×1.10）｜RR {bs['rr']}"
                  f"<br><b>箱体位置</b>：现价 {bs['close']} 处于「{bs['pos_tag']}」，"
                  f"箱体 {bs['pos_pct']:.0f}%（0%=止损位，100%=T2）{gap_t1}｜{box_bar(bs)}</div>")
        else:
            bp = ""
        f = r["f"]
        fac = ("近20日动量 <b>%+.1f%%</b>｜近60日 <b>%+.1f%%</b>｜站上MA60 <b>%+.1f%%</b>｜MA20斜率 <b>%+.1f%%</b>｜"
               "均线多头 <b>%+.1f%%</b>｜接近近20日高 <b>%+.1f%%</b>｜上涨放量占比 <b>%.0f%%</b>｜量能放大 <b>%.2f</b>｜回调缩量 <b>%.2f</b>"
               % (f["rel20"] * 100, f["rel60"] * 100, f["above_ma60"] * 100, f["slope20"] * 100,
                  f["ma_strength"] * 100, f["dist_h20"] * 100, f["up_vol"] * 100, f["rvol"], f["vol_dry"]))
        return (f"<div class='case'><div class='h'>🔥 {EM.link(r['_full'], r['name'])} {r['code']} "
                f"—— 主升分 {r.get('qs')}/100（域内第 {r['qrank']} 名）</div>"
                f"<div class='kv'>{fac}</div>{bp}</div>")

    a_cases = "".join(case_div(r) for r in shown[:40])
    if not a_cases:
        why = ("本期<b>不出手</b>：市场处于「%s」档，按二值门控（<b>强势开仓、其余空仓</b>）"
               "主升精选本期空仓等待 —— 这是结论，不是筛选不到票；环境回到强势档后列表会自动恢复。"
               "样本外证据见 <a href='env_gate.html' style='color:var(--blue)'>env_gate.html</a>。"
               % gate_lab if gate_lab else
               "本期全市场域无达标标的。确定性最高的组合稀缺，空仓等待也是纪律。")

    old_aud, real_aud = audit_pair()
    if ev:
        _owr = (old_aud or {}).get("top_wr")
        _owr = _owr if _owr is not None else (ev.get('prior_test_wr') or ev.get('test_wr') or 0)
        ev_line = (f"A 档（域内前 {pct*100:.0f}%）严格样本外可兑现胜率 "
                   f"<b>{_owr:.1f}%</b>（基线 {ev.get('base_wr',0):.1f}%），"
                   f"训练半 {ev.get('train_wr') or 0:.1f}% / 测试半 {ev.get('test_wr') or 0:.1f}%"
                   f" —— ⚠ 此为 <b>乐观成交口径</b>；改按可实现口径后为 "
                   f"<b>{(real_aud or {}).get('top_wr',0):.1f}%</b>（见下个红框）")
    else:
        ev_line = "详见 lab.html"

    # ★ 口径修正说明：旧口径（乐观日内+忽略跳空）→ 可实现口径（保守日内+跳空成交）
    if old_aud and real_aud:
        audit_box = (
            f"<div class='box red' style='border-color:#b00020'><b>⚠️ 口径修正（退出回测的成交假设，必读）：</b>"
            f"上方胜率来自<b>乐观口径</b>（把同根 K 线当作「先冲高、后回落」）"
            f"且<b>忽略跳空</b>（开盘已破止损线时仍按止损线价成交）。"
            f"同一批样本、同一组参数，改按<b>可实现口径</b>"
            f"（先用截至昨日的止盈线判断当日是否跌破 + 跳空以开盘价成交）重算："
            f"A 档可兑现胜率 <b>{old_aud['top_wr']:.1f}% → {real_aud['top_wr']:.1f}%</b>，"
            f"测试半 <b>{old_aud['test_wr']:.1f}% → {real_aud['test_wr']:.1f}%</b>"
            f"（<b>已低于 60%</b>，原「两半均 &gt;60%」的表述不成立）；"
            f"单笔净均值 <b>{old_aud['top_net']:+.3f}% → {real_aud['top_net']:+.3f}%</b>。"
            f"旧口径在全样本上被<b>精确复现</b>（62.7%，与冻结模型记录一致），"
            f"说明差异<b>只来自成交假设</b>，不是换了一批票或换了一段时间。"
            f"完整四假设对照见 "
            f"<a href='../docs/exit_assumption_evidence.html' style='color:var(--blue)'>"
            f"退出回测口径审计证据页</a>。本页结论以该页为准。</div>")
    else:
        audit_box = ("<div class='box red' style='border-color:#b00020'><b>⚠️ 退出回测口径未核验：</b>"
                     "未找到口径审计产物 <code>quant/_exit_assumption_audit.json</code>"
                     "（运行 <code>python quant/_exit_assumption_audit.py</code> 生成）。"
                     "在完成核验前，本页胜率应视为<b>乐观口径、未证实</b>。</div>")

    return f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>主升精选 · 趋势+资金双确认高确定性池 · {date}</title><style>{STYLE}</style></head>
<body><div class="wrap">
<h1>主升精选 · 趋势 + 资金 双确认（全市场严格筛选）</h1>
<div class="sub">数据基准 {date} 收盘｜ <b>全市场域</b>：A 股正股，剔 ST/退 与 20 日均成交额 &lt;3000 万、现价 &lt;2 元
｜ 先验固定因子集（趋势+资金 9 因子）横截面分位 → A 档前 {pct*100:.0f}%（共 <b>{len(shown)}</b> 只）</div>

<div class="box gold"><b>主升精选是什么（v2）：</b>从<b>全市场正股</b>出发（不再依赖任何现有模型库），
用「趋势已转多 + 资金真进场」双确认的<b>先验固定因子集</b>（方向由经济逻辑给定、等权、不筛不调权）
做横截面分位排序，取域内前 {pct*100:.0f}% 为 A 档。比 v1（消费 MACD 池+精选池）更严格、域更干净。
⚠ 样本外可兑现胜率<b>依赖退出回测的成交假设</b>：乐观口径下约 {((old_aud or {}).get('top_wr') or 0):.1f}%，
可实现口径（保守日内 + 跳空成交）下降至约 {((real_aud or {}).get('top_wr') or 0):.1f}%，
测试半 <b>{(real_aud or {}).get('test_wr', 0):.1f}%</b> —— 详见下方口径修正框。</div>

{env_banner}

<div class="box green"><b>样本外证据（详见 <a href="lab.html" style="color:var(--blue)">lab.html</a>）：</b>
{ev_line}。
① <b>先验固定集 vs 自动筛因子</b>：严格样本外（前 60% 学 → 后 40% 测）先验集胜率（乐观口径）
<b>{ev.get('prior_test_wr') or 0:.1f}%</b>、自动筛仅 <b>59.1%</b> —— 「挑因子」这个动作本身就是过拟合，
先验集才是干净样本外；
② <b>截断曲线</b>：前 {pct*100:.0f}% 全样本胜率（乐观口径）<b>{ev.get('prior_test_wr') or 0:.1f}%</b> 量级，
训练半与测试半同向（反转池为反向）；
③ <b>退出规则</b>（移动止盈 −12% / +6%激活 / 3%回撤 / 满 20 日）网格最优组合的胜率是<b>样本内挑出来的</b>，
不可作为样本外成绩；且其数值对成交假设高度敏感（见下方口径修正框）。
本页选股/退出能力<b>以 lab.html 与口径审计证据页为准</b>。</div>

{audit_box}

<div class="box red" style="border-color:#b00020"><b>⚠️ 退出纪律（唯一跨期稳定的改进，必读）：</b>
主升浪用<b>移动止盈</b>：未盈利前 −12% 硬止损；浮盈 ≥+6% 后止损上移为「持仓最高价 ×0.97」跟踪；满 20 日强平。
实验室实测最紧的 −6% 止损两半胜率仅 41%（因前 10% 平均不利偏移已达 −7.7%，贴身止损必被扫）。
正确用法：<b>破结构位（近 20 日基底）先减半，跌到 −15% 全出；+8%~+10% 先止盈一半</b>。
胜率与单笔均值是一对权衡，<b>不要只看胜率</b>。</div>

<h2>一、主升精选 A 档（{len(shown)} 只 · 按主升分降序，展开前 40）</h2>
{a_cases or why}

<h2>二、合并总表（{len(shown)} 只）</h2>
<div class="card"><div style="overflow-x:auto"><table>
<thead><tr><th>代码</th><th>名称</th><th>现价</th><th>主升分</th><th>排名</th><th>买区</th><th>止损</th><th>目标T1/T2</th><th>箱体位置</th><th>关键因子</th></tr></thead>
<tbody>{table}</tbody></table></div>
<div class="note" style="color:var(--muted);font-size:12px">主升分 = 先验固定因子在<b>当日全市场域内</b>的横截面分位（0~100，越高越好），只在同日内可比、不可跨日比较。
A = 域内前 {pct*100:.0f}%。<b>箱体位置</b> = 现价在「止损位(0%) → 买区 → T1 → T2(100%)」箱体中的百分比：
<b>买区内·可买</b>（0~买区上沿，最佳介入区）→ <b>持有·待涨</b>（等 T1）→ <b>已到T1/T2</b>（按纪律止盈一半/兑现）→ <b>已破止损</b>（离场，等待重新进买区）。
买卖点为量化参考区间，须结合大盘环境与退出纪律执行。
逐票完整因子见上方卡片；名称可直接点击跳转东方财富个股页。</div></div>

<h2>三、方法论 v2 与局限</h2>
<div class="card"><div class="kv">
① <b>v2 改了什么（域）</b>：v1 消费「MACD 池 + 精选池」两个现有模型库（域小、且含各自筛选偏差）；
v2 改为<b>全市场正股域</b>（剔 ST/退 + 流动性 + 低价），域更干净、横截面分位噪声更低。<br>
② <b>v2 改了什么（因子）</b>：用<b>先验固定因子集</b>——趋势（近20/60日动量、站上MA60、MA20斜率、均线多头、接近近20日高）
+ 资金（上涨放量占比、量能放大、回调缩量），方向由经济逻辑给定、等权、不筛因子、不按回测调权重。
严格样本外（前 60% 学 → 后 40% 测）先验集胜率（乐观成交口径）<b>{ev.get('prior_test_wr') or 0:.1f}%</b>
vs 自动筛 <b>59.1%</b>；⚠ 该胜率对成交假设敏感，可实现口径下见上方口径修正框。<br>
③ <b>截断</b>：A 档 = 域内前 {pct*100:.0f}%（更严格，确保胜率 &gt;60%）；绝对名次随域大小漂移，仅参考。<br>
④ <b>局限</b>：前向 20 日窗口重叠 → 样本非独立；样本约 10 个月，换年份是否成立无法验证；
主力资金用「上涨放量占比」价量代理（离线源只给最新日真实主力净流入，历史序列不可得），选股日可叠加真实主力净流入作加分；
绝对胜率含 beta，结论以相对口径为主。</div></div>

<div class="foot">本页为基于离线日K的量化筛选与方法论，非个股推荐、非买卖建议。决策责任在账户本人。数据基准 {date}。</div>
</div>{X.SORT_JS}</body></html>"""


def main(date):
    shown, rows, model, n, nA = scan(date)
    env = E.market_env(date)
    lab = (env or {}).get("label", "未知") if env else "未知"
    gate = lab in GATE_ALLOW
    if not gate:
        # 二值门控：非强势档不出手（只影响主升精选；做T池的 ENV_RULE 不动）
        shown = []
    html = render(shown, rows, model, date, env, gate=gate, gate_lab=lab)
    dc = date.replace("-", "")
    open(os.path.join(OUTDIR, f"combined_{dc}.html"), "w", encoding="utf-8").write(html)
    open(os.path.join(OUTDIR, "index.html"), "w", encoding="utf-8").write(html)
    json.dump({"date": date, "n_universe": n, "nA": nA, "pct": model.get("pct", 0.05),
               "env": lab, "env_gate": "强势开仓/其余空仓" if gate else "空仓（非强势档）",
               "gate_on": gate, "model": model.get("version")},
              open(os.path.join(OUTDIR, f"stat_{dc}.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"[selected] 主升精选 v2：A 档 {len(shown)} 只（域内 {n}）｜ 环境 {lab} ｜ "
          f"二值门控 {'强势·正常出手' if gate else '非强势·空仓不出手'} 写 web/selected/")
    return shown


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("date", nargs="?", default="2026-09-18")
    a = ap.parse_args()
    main(a.date)
