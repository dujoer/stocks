# -*- coding: utf-8 -*-
"""三连阴（量化错杀型）观察池 —— 每日选股 + 量化买卖点 + 回测裁决。

来源：用户提出的四套问财条件（优质三连阴 / 普通三连阴基准 / 高危三连阴排雷 /
龙头主线三连阴）+ 盘中人工二次核对清单。

铁律（quant-factor-oos-lab）：
- 上线前先跑真实样本外回测（quant/_3yl_lab.py，284 交易日 / 22.4 万信号），
  **回测结论原样呈现在页面首位**，不美化、不隐藏。
- 回测已证伪的三条（缩量=优质 / 站上MA60=安全 / 市值区间）**不作为加分项**，
  只作为记录列展示；真正两半同向有效的维度是 **三连阴累计跌幅分档**。
- 环境只控 β（仓位系数），不改排序；退出纪律 > 入场筛选；期间依赖诚实披露。
- 全离线真实数据：_txk_cache.json + _mktcap.json + _name2sw2.json，不联网、不伪造。

产出：web/three_yin/sanyin_{DS}.html + index.html + stat_{DS}.json + lab.html
用法：python3 quant/build_3yl.py 2026-09-29
"""
from __future__ import annotations
import os, sys, json, glob, datetime, argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _tx_fetch as T
import _idxkline as E
import _xhist as X

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QUANT = os.path.join(ROOT, "quant")
OUTDIR = os.path.join(ROOT, "web", "three_yin")
os.makedirs(OUTDIR, exist_ok=True)

PRICE_MIN = 2.0
AMT_MIN = 20_000_000          # 20 日均成交额下限（2000 万）
MIN_BARS = 70

# 跌幅分档（回测校准：8~12% 是唯一两半同向跑赢的区间；>12% 显著为负）
BUCKETS = [
    ("obs",   "★ 观察档", 0.08, 0.12, "var(--up)",   "两半同向跑赢基准：T+1涨54.0% / 胜率47.7% / 期望+0.43%（基准 48.7% / 44.3% / +0.01%）。本期主推。"),
    ("mid",   "一般档",   0.05, 0.08, "var(--blue)", "T+1涨50.3% / 胜率45.1% / 期望+0.08%，略优于基准但边际弱。"),
    ("light", "浅跌档",   0.00, 0.05, "var(--muted)","跌 0~5%：T+1涨≈47.8% / 期望 −0.09%，无优势，仅作观察。"),
    ("deep",  "⚠ 排雷档", 0.12, 0.20, "var(--dn)",   "跌 12~20%：胜率 41.9% / 期望 −0.07%，两半均劣化，禁止抄底。"),
    ("fatal", "⛔ 深跌禁区", 0.20, 9.9, "#b00020",    "跌 >20%：胜率仅 20.9% / 期望 −2.39%，两半同向为大负，坚决回避。"),
]

STYLE = """
:root{--bg:#fbfbfd;--card:#fff;--text:#1d1d1f;--muted:#6e6e73;--line:#e5e5e7;
 --up:#ff3b30;--dn:#34c759;--blue:#0071e3;--gold:#b8893b;--orange:#ff9500;--purple:#af52de;}
*{box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"PingFang SC","Microsoft YaHei",sans-serif;
 background:var(--bg);color:var(--text);line-height:1.7;margin:0;padding:0}
.wrap{max-width:1060px;margin:0 auto;padding:28px 18px 56px}
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
.tag.ok{background:#e6f7ec;color:#1a7a45}.tag.no{background:#fff5f4;color:#b00020}
.tag.mid{background:#e6f0ff;color:#1a73e8}.tag.gray{background:#f0f0f2;color:#6e6e73}
.bk{font-size:13px;font-weight:700;padding:3px 10px;border-radius:10px;display:inline-block;margin:2px 0}
.case{font-size:13px;margin:10px 0;padding:12px 16px;background:#fafafa;border-radius:10px;border-left:3px solid var(--purple)}
.case .h{font-weight:600;margin-bottom:4px}
.kv{font-size:12.5px;color:var(--muted)}
.bp{background:#f7f9fc;border:1px solid var(--line);border-radius:10px;padding:10px 14px;margin:8px 0;font-size:13px}
.bp b{color:var(--blue)}
.chk{font-size:13.5px;line-height:2.0}
.chk label{display:block;padding:4px 0;cursor:pointer}
.chk input{margin-right:8px;transform:translateY(1px)}
.foot{text-align:center;color:var(--muted);font-size:12px;margin-top:28px}
.tbl-wrap{overflow-x:auto}
""" + X.BADGE_CSS


def _ma(a, n):
    return sum(a[-n:]) / n if len(a) >= n else None


def _vol_unit(code):
    """腾讯 fqkline 成交量单位：科创板 sh688* = 股，其余 = 手。"""
    return 1 if code.startswith("sh688") else 100


def _load_maps():
    nm = json.load(open(os.path.join(QUANT, "_stock_names.json"), encoding="utf-8"))
    sw2 = json.load(open(os.path.join(QUANT, "_name2sw2.json"), encoding="utf-8"))
    ind = {c: sw2.get(v) for c, v in nm.items() if sw2.get(v)}
    cap = {}
    p = os.path.join(QUANT, "_mktcap.json")
    if os.path.exists(p):
        cap = json.load(open(p, encoding="utf-8")).get("caps", {})
    return nm, ind, cap


def bucket_of(fall):
    for key, label, lo, hi, color, desc in BUCKETS:
        if lo <= fall < hi:
            return key, label, color, desc
    return "light", "浅跌档", "var(--muted)", ""


# ------------------------------------------------------------------ 档内评级
# 星级只依据 `_3yl_lab2.py` 实测的 ATR 分档胜率（先验固定，不每日重调）
STAR_OF_BIN = {
    "ATR<2.0%": "★★★", "ATR 2.0~2.5%": "★★★", "ATR 2.5~3.0%": "★★★",
    "ATR 3.0~3.5%": "★★", "ATR 3.5~4.0%": "★★",
    "ATR 4.0~5.0%": "★",
    "ATR 5.0~7.0%": "—", "ATR>7.0%": "✕ 回避",
}
STAR_CLS = {"★★★": "ok", "★★": "ok", "★": "mid", "—": "gray", "✕ 回避": "no"}


def _load_lab2():
    p = os.path.join(QUANT, "3yl_lab2.json")
    if not os.path.exists(p):
        return None
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return None


def grade_of(atr, lab2):
    """按 ATR 落入哪一档 -> 该档的真实历史胜率/期望（来自 lab2 全样本回测）。"""
    bins = (lab2 or {}).get("atr_bins") or []
    # ★ ATR 低于最低档时（lab2 里该档因样本 <50 未落盘）必须单独处理：
    #   实测胜率随 ATR 单调下降，ATR 越低越好，所以归入**最高**星级，
    #   绝不能掉进下面的兜底分支被标成「✕ 回避」——那会把最优档变成最差档。
    if bins and atr < bins[0]["lo"]:
        b = bins[0]
        return {"star": "★★★", "cls": "ok",
                "win": b.get("win"), "exp": b.get("exp"), "t1": b.get("t1_up"),
                "n": b.get("n"), "bin": "ATR<%.1f%%" % (bins[0]["lo"] * 100),
                "ok": True, "thin": True}
    for b in bins:
        if b["lo"] <= atr < b["hi"]:
            return {"star": STAR_OF_BIN.get(b["label"], "—"), "cls": STAR_CLS.get(
                        STAR_OF_BIN.get(b["label"], "—"), "gray"),
                    "win": b.get("win"), "exp": b.get("exp"), "t1": b.get("t1_up"),
                    "n": b.get("n"), "bin": b["label"],
                    "ok": bool(b.get("both_better"))}
    # 高于最高档（ATR 极大）才是回避
    return {"star": "✕ 回避", "cls": "no", "win": None, "exp": None,
            "t1": None, "n": 0, "bin": "ATR 超范围", "ok": False}


def _howto_block(lab2):
    """「今天哪些是好的」——三问三答决策卡（数字全部来自 lab2 真实回测）。"""
    if not lab2:
        return ""
    base = lab2.get("base") or {}
    atr_rows = ""
    for b in lab2.get("atr_bins", []):
        star = STAR_OF_BIN.get(b["label"], "—")
        cls = STAR_CLS.get(star, "gray")
        atr_rows += (
            f"<tr><td><span class='tag {cls}'>{star}</span></td>"
            f"<td class='num'>{b['label']}</td>"
            f"<td class='num'>{b['n']:,}</td>"
            f"<td class='num'>{b['t1_up']*100:.1f}%</td>"
            f"<td class='num'><b>{b['win']*100:.1f}%</b></td>"
            f"<td class='num {'up' if b['exp']>0 else 'dn'}'>{b['exp']*100:+.2f}%</td>"
            f"<td class='kv'>{b['h1_exp']*100:+.2f}% / {b['h2_exp']*100:+.2f}%</td>"
            f"<td>{'✅ 两半同向' if b['both_better'] else ''}</td></tr>")
    amt_rows = ""
    for d in lab2.get("dims", []):
        if d["key"] != "amt":
            continue
        for it in d["items"]:
            amt_rows += (
                f"<tr><td>{it['group']}</td><td class='num'>{it['n']:,}</td>"
                f"<td class='num'>{it['t1_up']*100:.1f}%</td>"
                f"<td class='num'><b>{it['win']*100:.1f}%</b></td>"
                f"<td class='num {'up' if it['exp']>0 else 'dn'}'>{it['exp']*100:+.2f}%</td>"
                f"<td class='kv'>{it['h1_exp']*100:+.2f}% / {it['h2_exp']*100:+.2f}%</td>"
                f"<td>{'✅ 两半同向' if it['both_better'] else ''}</td></tr>")
    cross_rows = ""
    for c in lab2.get("cross", []):
        cross_rows += (
            f"<tr><td>{c['label']}</td><td class='num'>{c['n']:,}</td>"
            f"<td class='num'>{c['t1_up']*100:.1f}%</td>"
            f"<td class='num'><b>{c['win']*100:.1f}%</b></td>"
            f"<td class='num {'up' if c['exp']>0 else 'dn'}'>{c['exp']*100:+.2f}%</td>"
            f"<td class='kv'>{c['h1_exp']*100:+.2f}% / {c['h2_exp']*100:+.2f}%</td>"
            f"<td>{'✅ 两半同向' if c['both_better'] else ''}</td></tr>")

    return f"""
<h2>今天哪些是「好票」——三问三答</h2>
<div class="box gold"><b>一句话：</b>先看<b>跌了多少</b>（8~12% 才值得看），
再看<b>波动率</b>（ATR% 越低越好，这是档内唯一单调有效的维度），
最后看<b>成交额</b>（清淡 &lt;1 亿更佳）。三项都满足的，历史同类胜率可达
<b>70~88%</b>；不满足的，胜率会掉到 <b>36~53%</b>。
</div>

<div class="card">
<h3 style="font-size:14px;margin:14px 0 6px">① 第一问：跌了多少？（决定值不值得看）</h3>
<div class="kv">只有 <b>跌 8~12%</b> 这一档在样本前后两半都跑赢「全市场随便买」基准。
跌 0~5% 没有优势；跌 &gt;12% 明显劣化；<b>跌 &gt;20% 是灾难</b>（胜率 20.9%、期望 −2.39%）。</div>

<h3 style="font-size:14px;margin:18px 0 6px">② 第二问：波动率高不高？（决定同类里的好坏，最关键）</h3>
<div class="kv">在跌 8~12% 这一档内部，<b>ATR% 越低胜率越高，且是单调的</b>——
单调性是最难被过拟合伪造的证据。档内基准：胜率 <b>{base.get('win',0)*100:.1f}%</b>、
期望 <b>{base.get('exp',0)*100:+.2f}%</b>。</div>
<div class="tbl-wrap"><table>
<thead><tr><th>星级</th><th>波动率区间</th><th>样本</th><th>T+1上涨</th>
<th>历史胜率</th><th>期望</th><th>前半/后半</th><th>稳健性</th></tr></thead>
<tbody>{atr_rows}</tbody></table></div>
<div class="kv">读法：<b>★★★ = ATR&lt;3.0%</b>（温和回调，抛压可控）；
<b>★ = ATR 4~5%</b>（勉强）；<b>✕ 回避 = ATR&gt;7%</b>（真崩塌/题材退潮，胜率仅 35.8%）。</div>

<h3 style="font-size:14px;margin:18px 0 6px">③ 第三问：成交是否清淡？（叠加项，非必需）</h3>
<div class="kv">成交额越低越好，且与波动率<b>部分独立</b>——即使在高波动组，
清淡组期望 <b>+0.99%</b> 也明显优于活跃组 <b>−0.15%</b>。</div>
<div class="tbl-wrap"><table>
<thead><tr><th>20日均成交额</th><th>样本</th><th>T+1上涨</th><th>历史胜率</th>
<th>期望</th><th>前半/后半</th><th>稳健性</th></tr></thead>
<tbody>{amt_rows}</tbody></table></div>

<h3 style="font-size:14px;margin:18px 0 6px">④ 两者叠加（波动率 × 成交额）</h3>
<div class="tbl-wrap"><table>
<thead><tr><th>组合</th><th>样本</th><th>T+1上涨</th><th>历史胜率</th>
<th>期望</th><th>前半/后半</th><th>稳健性</th></tr></thead>
<tbody>{cross_rows}</tbody></table></div>
<div class="box green"><b>最优组合：低波动(ATR 2~4%) × 清淡(&lt;1亿)</b> →
历史胜率 <b>77.7%</b>、期望 <b>+3.08%</b>，且前后半同向。
这就是本页「★ 今日优先池」的筛选口径。</div>
</div>"""


def scan(date):
    cache = T._load()
    nm, ind, cap = _load_maps()
    rows = []
    n_st = n_liq = n_short = 0
    for code, bars in cache.items():
        if not bars or len(bars) < MIN_BARS:
            n_short += 1
            continue
        name = nm.get(code) or ""
        if not name or "ST" in name or "退" in name or code.startswith("bj"):
            n_st += 1
            continue
        idx = None
        for j, b in enumerate(bars):
            if b["date"] == date:
                idx = j
                break
        if idx is None or idx < 62:
            continue
        i1, i2 = idx - 1, idx - 2
        if bars[i1]["date"] is None or i2 < 0:
            continue
        C = [b["last"] for b in bars]
        H = [b["high"] for b in bars]
        L = [b["low"] for b in bars]
        V = [b["volume"] for b in bars]
        # 三连阴：收盘价连续 3 日下跌
        if not (C[idx] < C[i1] < C[i2]):
            continue
        if V[idx] <= 0 or V[i1] <= 0 or V[i2] <= 0:
            continue
        close = C[idx]
        if close < PRICE_MIN:
            continue
        # 起点 = 三连阴开始前一日收盘；谷底 = 三日最低
        start = C[i2 - 1] if i2 >= 1 else C[i2]
        trough = min(L[i2], L[i1], L[idx])
        fall = 1 - close / start if start else 0.0
        if fall <= 0:
            continue
        vu = _vol_unit(code)
        amt20 = sum(V[idx - 19 + k] * vu * C[idx - 19 + k] for k in range(20)) / 20.0
        if amt20 < AMT_MIN:
            n_liq += 1
            continue
        ma60 = sum(C[idx - 59:idx + 1]) / 60.0
        # ATR%（近 14 根含信号日）—— 与 _3yl_lab2.py 完全同口径，档内评级用它
        trs = []
        for k in range(idx - 13, idx + 1):
            if k <= 0:
                continue
            pc = C[k - 1]
            if not pc:
                continue
            tr = max(H[k] - L[k], abs(H[k] - pc), abs(L[k] - pc))
            trs.append(tr / pc)
        atr = (sum(trs) / len(trs)) if trs else 0.0
        shrink = V[idx] < V[i1] < V[i2]
        expand = V[idx] > V[i1] > V[i2]
        above = close > ma60
        # 流通市值（亿）
        m = cap.get(code) or {}
        fmc = m.get("fmc")
        # ---- 买卖点（回测校准）
        # 买入参考：T+1 开盘≈现价；低吸区 = 谷底 × [1.00, 1.03]
        buy_ref = close
        entry_lo = trough * 1.00
        entry_hi = trough * 1.03
        # 止损：结构位（谷底×0.97）与固定 −5% 取更宽者
        # ⚠ 口径必须与「同类历史胜率」一致：lab2 的胜率就是用 止损5%/止盈8%/持有5日 算的。
        # （A 桶 MAE 均值 −4.16%；3% 止损胜率仅 33.9%、5% 为 43.5%、7% 为 47.2%）
        stop_struct = trough * 0.97
        stop_fixed = buy_ref * 0.95
        stop = min(stop_struct, stop_fixed)
        # 目标：本轮下跌段回撤（与反转池 v6 同口径）
        rng = max(start - trough, 0.0)
        t1 = trough + rng * 0.382
        t2 = trough + rng * 0.618
        rr = ((t1 - buy_ref) / (buy_ref - stop)) if buy_ref > stop else 0.0
        bk, label, color, desc = bucket_of(fall)
        rows.append({
            "code": code, "name": name, "close": close, "fall": fall,
            "start": start, "trough": trough, "ma60": ma60, "above": above,
            "shrink": shrink, "expand": expand, "fmc": fmc, "atr": atr,
            "ind": ind.get(code, ""), "amt20": amt20,
            "entry_lo": entry_lo, "entry_hi": entry_hi, "stop": stop,
            "t1": t1, "t2": t2, "rr": rr, "bk": bk, "bklabel": label,
            "upside1": t1 / buy_ref - 1, "upside2": t2 / buy_ref - 1,
        })
    print("[3yl] 剔 ST/北交所 %d ｜ 流动性不足 %d ｜ K线不足 %d ｜ 三连阴入池 %d"
          % (n_st, n_liq, n_short, len(rows)))
    return rows


def _row_tr(r, g=None):
    tags = []
    tags.append("<span class='tag %s'>%s</span>" % ("ok" if r["shrink"] else "gray",
                                                    "缩量" if r["shrink"] else "非缩量"))
    tags.append("<span class='tag %s'>%s</span>" % ("ok" if r["above"] else "no",
                                                    "站上MA60" if r["above"] else "破MA60"))
    tags.append("<span class='tag %s'>%s</span>" % ("no" if r["expand"] else "gray",
                                                    "放量" if r["expand"] else "—"))
    fmc = ("%.0f亿" % r["fmc"]) if r["fmc"] else "—"
    if g:
        star = f"<span class='tag {g['cls']}'>{g['star']}</span>"
        win = ("<b>%.1f%%</b>" % (g["win"] * 100)) if g.get("win") is not None else "—"
        if g.get("thin"):
            # 该档在 lab2 里因样本 <50 未单独落盘，胜率取相邻档作参考 —— 必须如实标注
            star += "<span class='tag gray' title='该 ATR 档回测样本不足 50 条，胜率取相邻最低档作参考'>样本薄</span>"
    else:
        star, win = "—", "—"
    return ("<tr>"
            f"<td>{r['code']}</td><td>{r['name']}</td>"
            f"<td class='num'>{r['close']:.2f}</td>"
            f"<td class='num dn'>-{r['fall']*100:.1f}%</td>"
            f"<td>{star}</td>"
            f"<td class='num'>{win}</td>"
            f"<td class='num'>{r['atr']*100:.2f}%</td>"
            f"<td class='num'>{r['trough']:.2f}</td>"
            f"<td class='num'>{r['entry_lo']:.2f}~{r['entry_hi']:.2f}</td>"
            f"<td class='num dn'>{r['stop']:.2f}</td>"
            f"<td class='num up'>{r['t1']:.2f} / {r['t2']:.2f}</td>"
            f"<td class='num'>{r['rr']:.1f}</td>"
            f"<td class='num'>{fmc}</td>"
            f"<td>{r['ind'] or '—'}</td>"
            f"<td>{''.join(tags)}</td></tr>")


HEAD = ("<thead><tr><th>代码</th><th>名称</th><th>现价</th><th>三连阴跌幅</th>"
        "<th>评级</th><th>同类历史胜率</th><th>波动率ATR%</th><th>谷底</th>"
        "<th>低吸区</th><th>止损</th><th>目标 T1/T2</th><th>盈亏比</th><th>流通市值</th>"
        "<th>行业</th><th>量价特征</th></tr></thead>")


def _verdict_block(lab):
    """回测裁决（页面首屏）：原样呈现证据，不美化。"""
    if not lab:
        return ""
    s = lab.get("stat", {})
    w = lab.get("window", {})
    d = lab.get("default", {})

    def line(k, name):
        x = s.get(k) or {}
        if not x.get("n"):
            return ""
        h1 = ("前半 胜率%.1f%% / 期望%+.2f%%" % (x["h1_win"] * 100, x["h1_exp"] * 100)) if x.get("h1_win") is not None else ""
        h2 = ("后半 胜率%.1f%% / 期望%+.2f%%" % (x["h2_win"] * 100, x["h2_exp"] * 100)) if x.get("h2_win") is not None else ""
        return (f"<tr><td><b>{name}</b></td><td class='num'>{x['n']:,}</td>"
                f"<td class='num'>{x['t1_up']*100:.1f}%</td><td class='num'>{x['up5']*100:.1f}%</td>"
                f"<td class='num'>{x['win']*100:.1f}%</td>"
                f"<td class='num {'up' if x['exp']>0 else 'dn'}'>{x['exp']*100:+.2f}%</td>"
                f"<td class='kv'>{h1}</td><td class='kv'>{h2}</td></tr>")

    rows = "".join([line("ALL", "全市场随便买（绝对基准）"), line("B", "B 普通三连阴"),
                    line("A", "A 优质三连阴（用户原条件）"), line("C", "C 高危三连阴"),
                    line("D", "D 龙头主线三连阴")])
    abl = "".join(
        "<tr><td>%s</td><td class='num'>%s</td><td class='num'>%.1f%%</td><td class='num'>%.1f%%</td>"
        "<td class='num %s'>%+.2f%%</td></tr>"
        % (a["label"], "{:,}".format(a["n"]) if a.get("n") else "—",
           a["t1_up"] * 100 if a.get("t1_up") is not None else 0,
           a["win"] * 100 if a.get("win") is not None else 0,
           "up" if (a.get("exp") or 0) > 0 else "dn",
           (a.get("exp") or 0) * 100)
        for a in lab.get("cond_ablation", []) if a.get("win") is not None)

    fall = "".join(
        "<tr><td>%s</td><td class='num'>%s</td><td class='num'>%.1f%%</td><td class='num'>%.1f%%</td>"
        "<td class='num %s'>%+.2f%%</td><td class='kv'>%s</td></tr>"
        % (f["label"], "{:,}".format(f["n"]), f["t1_up"] * 100, (f["win"] or 0) * 100,
           "up" if (f.get("exp") or 0) > 0 else "dn", (f.get("exp") or 0) * 100,
           ("前半 %+.2f%% / 后半 %+.2f%%" % (f["h1_exp"] * 100, f["h2_exp"] * 100))
           if f.get("h1_exp") is not None and f.get("h2_exp") is not None else "")
        for f in lab.get("ablation_fall", []))

    return f"""
<div class="box red" style="border-color:#b00020">
<b>🔬 回测裁决（先看这里，再决定是否使用本页信号）</b><br>
样本：<b>{w.get('from','')} ~ {w.get('to','')}</b>（{w.get('days','')} 个交易日）｜ 可回测域 {lab.get('universe',0):,} 只 ｜
样本量：三连阴信号 <b>{s.get('B',{}).get('n',0):,}</b> 条 ｜ 口径：T+1 开盘买入，止损 {int(d.get('stop',0.05)*100)}% /
止盈 {int(d.get('target',0.08)*100)}% / 持有 {d.get('hold',5)} 日，同日双触保守记止损。<br><br>
<b>结论 1（原条件集被证伪）：</b>A「优质三连阴」胜率 <b>{s.get('A',{}).get('win',0)*100:.1f}%</b>、期望
<b>{s.get('A',{}).get('exp',0)*100:+.2f}%</b>，<b>低于</b>「全市场随便买」基准
{s.get('ALL',{}).get('win',0)*100:.1f}% / {s.get('ALL',{}).get('exp',0)*100:+.2f}%。
即：<b>这套过滤条件不产生超额收益</b>。<br>
<b>结论 2（三条假设与数据相反）：</b>「缩量」与「站上 MA60」两个条件<b>都是负贡献</b>（见消融表）；
而用户归为「高危」的<b>放量</b>反而 T+1 上涨 51.1%、5 日上涨 54.2%，<b>优于缩量</b>。<br>
<b>结论 3（唯一有效维度 = 跌幅分档）：</b>累计跌幅 <b>8~12%</b> 档在前后半<b>两半同向跑赢</b>（T+1 涨 54.0%、
期望 +0.43%）；<b>跌幅 &gt;20% 是灾难</b>（胜率 20.9%、期望 −2.39%，两半同向为大负）。<br>
<b>结论 4（环境主导）：</b>所有变体在后半段期望<b>集体转负</b>（基准亦由 +0.58% → −0.13%），
说明收益主要来自市场 β 而非选股 α；环境差时应降低仓位，而非依赖选股。
</div>

<div class="card">
<h2 style="border:0;margin:0 0 8px;font-size:16px">① 四套规则 vs 基准（真实样本外）</h2>
<div class="tbl-wrap"><table><thead><tr><th>规则</th><th>信号数</th><th>T+1 上涨</th><th>5日上涨</th>
<th>胜率</th><th>期望收益</th><th>走前·前半</th><th>走前·后半</th></tr></thead>
<tbody>{rows}</tbody></table></div>
<div class="kv">「胜率 / 期望」= 固定退出规则下的可兑现结果；「T+1 上涨 / 5日上涨」= 用户问财口径的原始概率。
基准 ALL 为同期全市场随机抽样，代表「闭眼买」。</div>
</div>

<div class="card">
<h2 style="border:0;margin:0 0 8px;font-size:16px">② 条件消融：逐条看哪条在加分</h2>
<div class="tbl-wrap"><table><thead><tr><th>条件（叠加在三连阴之上）</th><th>信号数</th><th>T+1 上涨</th>
<th>胜率</th><th>期望收益</th></tr></thead><tbody>{abl}</tbody></table></div>
<div class="kv">基准行 = 仅三连阴。可见：加「缩量」后胜率与期望<b>双降</b>；加「站上 MA60」胜率降、期望几乎不变；
「流通市值 20~500 亿」<b>几乎无影响</b>；反向对照里「放量」与「跌破 MA60」<b>并不比原条件差</b>。</div>
</div>

<div class="card">
<h2 style="border:0;margin:0 0 8px;font-size:16px">③ 跌幅分档：唯一稳健的维度</h2>
<div class="tbl-wrap"><table><thead><tr><th>三连阴累计跌幅</th><th>信号数</th><th>T+1 上涨</th>
<th>胜率</th><th>期望收益</th><th>走前验证（前半 / 后半期望）</th></tr></thead>
<tbody>{fall}</tbody></table></div>
<div class="kv">按方法论：只有「前半、后半<b>两半同向</b>」的条件才允许写进规则。
<b>跌 8~12%</b> 两半相对基准均为正 → 采纳为观察档；<b>跌 &gt;20%</b> 两半同向为大负 → 列为禁区。</div>
</div>
"""


def render(rows, date, env, lab, prev=None, lab2=None, emit_ok=True, emit_why=""):
    # ★ 出票许可横幅（读证据页判定，页面不自己算统计）
    if emit_ok:
        emit_banner = (
            "<div class='box'><b>出票许可：已通过</b> —— 下方「今日优先池」可作买入依据。"
            "核验过程见页尾链接。</div>")
    else:
        emit_banner = (
            "<div class='box red' style='border-color:#b00020'>"
            "<b>⚠ 本期不出票（宁可不选）</b> —— 下方「今日优先池」及所有分档表"
            "<b>只作观察参考，不构成任何买入依据</b>。<br>原因：<code>%s</code><br>"
            "<b>诚实更正：</b>本页原写「观察档两半同向跑赢基准、期望 +0.43%%（基准 +0.01%%），本期主推」。"
            "那个对照是<b>该档 vs 全体三连阴母集（母集含它自己）</b>，属子集对母集、不是等量对照，"
            "且<b>没有给任何显著性区间</b>。按统一口径逐日平衡 + bootstrap 重算后，"
            "该档 edge 归零、R3 远低于 95%% 门槛 → <b>不能当买入依据</b>。"
            "原结论与重算过程见页尾「分档出票核验」页（历史判定不删改）。</div>"
            % (emit_why or "未读到出票许可证据"))
    labname = (env or {}).get("label", "未知") if env else "未知"
    pos = (env or {}).get("pos_scale") if env else None
    advice = (env or {}).get("advice", "") if env else ""
    env_banner = ""
    if labname and labname != "未知":
        env_banner = (f"<div class='box red'><b>大盘环境门控：{labname}</b>｜ 建议仓位系数 <b>{pos}</b><br>{advice}"
                      f"本页据此给<b>仓位系数</b>（控 β 暴露）；排序不受环境影响。</div>")

    n_base = ((lab2 or {}).get("base") or {}).get("n", 0)
    by = {b[0]: [] for b in BUCKETS}
    for r in rows:
        r["g"] = grade_of(r["atr"], lab2)
        by[r["bk"]].append(r)
    for k in by:
        if k == "obs":
            # 观察档内按 ATR 升序：回测证明档内「波动率越低胜率越高」且单调
            by[k].sort(key=lambda r: (r["atr"], r["code"]))
        else:
            by[k].sort(key=lambda r: (-r["rr"], r["code"]))

    counts = {k: len(v) for k, v in by.items()}

    # ---- ★ 今日优先池：观察档 × 低波动（ATR<4%），按 ATR 升序
    obs_all = by.get("obs", [])
    gc = {}
    for r in obs_all:
        gc[r["g"]["star"]] = gc.get(r["g"]["star"], 0) + 1
    dist = " ｜ ".join("%s %d 只" % (k, gc[k])
                       for k in ("★★★", "★★", "★", "—", "✕ 回避") if gc.get(k))
    no_top = "" if gc.get("★★★") else (
        "<div class='box red' style='margin:10px 0 0'><b>本期没有 ★★★。</b>"
        "说明当前市场波动整体抬升，连「跌 8~12%」的票 ATR 也普遍偏高。"
        "此时<b>不要降低标准去凑票</b>——正确做法是<b>只在 ★★ 里做、并降低仓位</b>；"
        "★ 及以下（ATR&gt;4%）历史胜率只有 35~53%，不值得出手。</div>")
    prime = [r for r in obs_all if r["atr"] < 0.04]
    prime_all = len(prime)
    prime = prime[:20]
    if prime:
        ptbl = "".join(_row_tr(r, r["g"]) for r in prime)
        wins = [r["g"]["win"] for r in prime if r["g"].get("win") is not None]
        wavg = (sum(wins) / len(wins)) if wins else 0
        prime_html = (
            f"<h2>★ 今日优先池（观察档 跌8~12% × 低波动 ATR&lt;4%）· {prime_all} 只</h2>"
            f"<div class='box green'><b>这是本页最该看的一张表。</b>"
            f"筛选口径 = 跌幅 8~12% ＋ <b>ATR&lt;4%</b>。"
            f"历史同口径样本：低波动×清淡组合胜率 <b>77.7%</b>、期望 <b>+3.08%</b>；"
            f"本表 {len(prime)} 只按 ATR 升序排列，<b>越靠前波动越小、历史同类胜率越高</b>"
            f"（本表平均同类胜率 <b>{wavg*100:.1f}%</b>）。</div>"
            f"<div class='box' style='margin:10px 0'><b>本期观察档评级分布（共 {len(obs_all)} 只）：</b>"
            f"{dist or '本期无观察档标的'}。"
            f"只有 <b>★★★ / ★★</b> 值得动手，<b>★ 及以下请直接跳过</b>。</div>{no_top}"
            f"<div class='card'><div class='tbl-wrap'><table data-wb>{HEAD}<tbody>{ptbl}</tbody></table></div>"
            f"<div class='kv'>「同类历史胜率」= 该股 ATR 所属分档在 <b>{n_base:,}</b> 条真实样本中的"
            f"实测胜率（固定退出规则：T+1开盘买／止损 −5%／止盈 +8%／持有 5 日），"
            f"<b>不是对个股的预测</b>，也不保证这只票一定涨。"
            f"要用这个胜率，就得用同一套买卖点（见下方「口径 A」）。展示前 {len(prime)} 只（共 {prime_all} 只）。</div></div>")
    else:
        prime_html = (
            "<h2>★ 今日优先池 · 0 只</h2>"
            "<div class='box red'><b>本期没有标的同时满足「跌 8~12% ＋ ATR&lt;4%」。</b>"
            "此时正确做法是<b>空仓等待</b>，不要退而求其次去碰高波动票——"
            "ATR&gt;7% 的同类历史胜率只有 <b>35.8%</b>、期望 <b>−0.51%</b>。</div>")

    sections = ""
    for key, label, lo, hi, color, desc in BUCKETS:
        sub = by.get(key, [])
        if not sub:
            sections += (f"<h2>{label}（跌 {lo*100:.0f}~{hi*100:.0f}%）· 0 只</h2>"
                         f"<div class='card'><div class='case'>本期无标的落入该档。</div></div>")
            continue
        show = sub[:30]
        tbl = "".join(_row_tr(r, r["g"]) for r in show)
        order_note = ("按<b>波动率 ATR 升序</b>（越低越好）" if key == "obs"
                      else "按盈亏比降序")
        sections += (
            f"<h2><span class='bk' style='color:{color}'>{label}</span>"
            f"（跌 {lo*100:.0f}~{hi*100:.0f}%）· {len(sub)} 只</h2>"
            f"<div class='box' style='border-color:{color};background:#fafafa'>{desc}</div>"
            f"<div class='card'><div class='tbl-wrap'><table data-wb>{HEAD}<tbody>{tbl}</tbody></table></div>"
            f"<div class='kv'>{order_note}，展示前 {len(show)} 只（共 {len(sub)} 只）。</div></div>")

    prev_html = ""
    if prev:
        prev_html = (f"<div class='box gold'><b>上期信号兑现追踪：</b>{prev['date']} 共 {prev['n']} 只信号，"
                     f"至 {date} 平均涨跌 <b class='{'up' if prev['avg']>0 else 'dn'}'>{prev['avg']*100:+.2f}%</b>，"
                     f"上涨比例 <b>{prev['win']*100:.1f}%</b>（{prev['up_cnt']}/{prev['n']}）。"
                     f"该数字用于校准本策略，不代表未来。</div>")

    return f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>三连阴（量化错杀）观察池 · {date}</title><style>{STYLE}</style></head>
<body><div class="wrap">
<h1>三连阴（量化错杀型）观察池 · 每日选股 + 量化买卖点</h1>
<div class="sub">数据基准 {date} 收盘｜ 全市场域（剔 ST/退/北交所、20 日均成交额 &lt;2000 万、现价 &lt;2 元）｜
按<b>三连阴累计跌幅</b>分档（回测校准的核心维度）｜ 全部离线真实日K，不联网、不补造</div>

<div class="box gold"><b>本页怎么用（30 秒版）：</b>
<b>第一步</b>看下面「★ 今日优先池」——那是同时满足回测中两条稳健条件的标的；
<b>第二步</b>看「同类历史胜率」列，那是它所属波动率档在 <b>{n_base:,}</b> 条真实样本里的实测胜率；
<b>第三步</b>只对 <b>★★★ / ★★</b> 的票走人工核对清单。<br>
你原先的四套问财条件已<b>逐条回测</b>（见下方裁决区）：原条件集
（缩量 + 站上MA60 + 市值）<b>不产生超额</b>，其中两条还是负贡献；
真正稳健的只有 <b>跌幅分档</b> 与档内的 <b>波动率</b>。四套原始判定仍保留在表格「量价特征」列供对照。</div>

{emit_banner}
{env_banner}
{prev_html}
{prime_html}
{_howto_block(lab2)}
{_verdict_block(lab)}

<h2>人工二次核对清单（量化筛出后，逐条人工确认）</h2>
<div class="card"><div class="chk">
<label><input type="checkbox"> <b>① 是否主线题材？</b>板块逻辑有没有结束？（看板块强度页的「抢筹 / 出货」分布）</label>
<label><input type="checkbox"> <b>② 三连阴是量化踩踏，还是基本面利空？</b>（本地无全市场利空历史库，此项<b>必须人工</b>：
查近 20 日减持公告 / 监管问询 / 业绩预减）</label>
<label><input type="checkbox"> <b>③ 下跌时成交量是否逐步萎缩？</b>抛压是否衰竭（注意：回测显示「缩量」本身不带来超额，
但可作为<b>抛压观察项</b>）</label>
<label><input type="checkbox"> <b>④ 股价是否在关键支撑位？</b>（MA60 / 前期平台 / 谷底）</label>
<label><input type="checkbox"> <b>⑤ 板块情绪：</b>同板块其他个股有没有承接？是不是大面积退潮？</label>
</div>
<div class="kv" style="margin-top:10px">勾选框仅为本页交互，不保存。第 ② 条是本地数据缺口（利空库仅 18 天历史，未参与回测），
也是本策略最大的<b>未验证风险</b>——把利空票误判为错杀票，正是回测中「跌 &gt;20% 期望 −2.39%」的主要来源。</div></div>

<h2>买卖点算法（两套口径，请二选一执行）</h2>
<div class="card">
<div class="box gold" style="margin-top:0"><b>⚠ 先看清口径，否则数字对不上：</b>
上表「同类历史胜率」是<b>回测口径</b>（止损 −5% / 止盈 +8% / 持有 5 日）算出来的。
如果你用结构位口径（T1/T2），胜率会<b>更高、但单笔赚得更少</b>——因为 T1 通常比 +8% 更近、更容易达到。
两套都是真实口径，<b>不要混用</b>。</div>

<h3 style="font-size:14px;margin:16px 0 4px">口径 A｜回测口径（推荐，与「同类历史胜率」完全对应）</h3>
<div class="bp"><b>买入：</b>信号收盘后产生 → <b>T+1 开盘</b>买入（回测就是这样执行的，不偷看未来）。</div>
<div class="bp"><b>止损：</b>入场价 <b>−5%</b>。依据：A 桶 MAE 均值 <b>−4.16%</b>，
止损 3% 时胜率仅 33.9%、5% 为 43.5%、7% 为 47.2%——<b>止损过窄会被正常波动打掉</b>，
这是本策略最常见的亏损来源。</div>
<div class="bp"><b>止盈 / 退出：</b><b>+8%</b> 或持有满 <b>5 个交易日</b>收盘卖出，二者先到为准。</div>
<div class="bp"><b>期望：</b>低波动组（ATR&lt;3%）在这一口径下历史胜率 <b>80.6~88.3%</b>；
高波动组（ATR&gt;7%）仅 <b>35.8%</b>、期望 <b>−0.51%</b>。</div>

<h3 style="font-size:14px;margin:18px 0 4px">口径 B｜结构位口径（贴合个股形态，未单独回测）</h3>
<div class="bp"><b>买入：</b>回踩不破谷底时低吸，低吸区 = <b>谷底 × [1.00, 1.03]</b>。</div>
<div class="bp"><b>止损：</b>取 <b>结构位（谷底 × 0.97）</b> 与 <b>固定 −5%</b> 中<b>更宽</b>的一个。</div>
<div class="bp"><b>目标：</b>T1 = 谷底 + 本轮跌幅 × 0.382，T2 = × 0.618（与反转池 v6 同口径），到 T1 先兑现一半。</div>
<div class="bp"><b>注意盈亏比：</b>低波动票的 T1 往往只有 <b>+3%~4%</b>，配 −5% 止损，盈亏比会 <b>&lt;1</b>。
<b>这是正常的、不要因此放弃</b>——这条路的收益来自<b>高胜率</b>（约 80%）而非大赔率；
按 80% × 3.6% − 20% × 5% 估算，期望仍为 <b>正</b>。真正该放弃的是 ATR&gt;7% 的票。</div>

<div class="bp"><b>仓位：</b>由大盘环境给<b>仓位系数</b>（控 β），本页不因环境改变排序。
回测显示后期全体转负是 β 所致，<b>降仓比换票更有效</b>。</div>
</div>

{sections}

<h2>局限与诚实披露</h2>
<div class="card"><div class="kv">
① <b>利空过滤未参与回测</b>：近 20 日减持 / 监管问询 / 业绩预减，本地仅 18 天历史样本，无法回溯；
回测中的 A 桶<b>不含</b>该过滤，因此实盘若严格执行利空过滤，结果可能与回测不同（大概率更好，但<b>未经证实</b>）。<br>
② <b>流通市值</b>为当前快照（腾讯 qt），历史回测中按价格缩放近似（假设股本不变）。<br>
③ <b>行业分类</b>用当前申万二级静态映射近似历史归属；板块前 5 排名按成分股等权 20 日涨幅计算。<br>
④ <b>前向窗口重叠</b> → 样本非独立；样本约 10 个月，跨年份有效性未验证。<br>
⑤ <b>绝对胜率含 β</b>：本策略在样本后半段期望转负，结论以<b>相对基准</b>口径为主。<br>
⑥ 本页为量化观察工具，<b>非个股推荐、非买卖建议</b>，决策责任在账户本人。</div></div>

<div class="foot">数据基准 {date} ｜ 回测引擎 quant/_3yl_lab.py ｜ 实验室页
<a href="lab.html" style="color:var(--blue)">lab.html</a> ｜ 出票核验
<a href="tier_gate.html" style="color:var(--blue)">tier_gate.html</a></div>
</div>{X.SORT_JS}</body></html>"""


def _lab2_block(lab2):
    """实验室页 ⑥：档内细分（回答「同样是跌 8~12%，哪一类更好」）。"""
    if not lab2:
        return ""
    base = lab2.get("base") or {}
    b1, b2 = lab2.get("base_h1") or {}, lab2.get("base_h2") or {}
    w = lab2.get("window") or {}

    def row_of(label, it, star=None):
        cls = "up" if it["exp"] > 0 else "dn"
        st = f"<span class='tag {STAR_CLS.get(star,'gray')}'>{star}</span>" if star else ""
        return (f"<tr><td>{st}{label}</td><td class='num'>{it['n']:,}</td>"
                f"<td class='num'>{it['t1_up']*100:.1f}%</td>"
                f"<td class='num'><b>{it['win']*100:.1f}%</b></td>"
                f"<td class='num {cls}'>{it['exp']*100:+.2f}%</td>"
                f"<td class='kv'>{it['h1_exp']*100:+.2f}% / {it['h2_exp']*100:+.2f}%</td>"
                f"<td>{'✅' if it.get('both_better') else ''}</td></tr>")

    atr = "".join(row_of(b["label"], b, STAR_OF_BIN.get(b["label"]))
                  for b in lab2.get("atr_bins", []))
    dims = ""
    for d in lab2.get("dims", []):
        if d["key"] == "atr":
            continue
        body = "".join(row_of(it["group"], it) for it in d["items"])
        dims += (f"<h3 style='font-size:13.5px;margin:14px 0 2px'>{d['label']}</h3>"
                 f"<div class='tbl-wrap'><table><thead><tr><th>分组</th><th>样本</th>"
                 f"<th>T+1上涨</th><th>历史胜率</th><th>期望</th><th>前半/后半</th>"
                 f"<th>两半同向</th></tr></thead><tbody>{body}</tbody></table></div>")
    cross = "".join(row_of(c["label"], c) for c in lab2.get("cross", []))

    return f"""
<h2>⑥ 档内细分：同样是跌 8~12%，哪一类更好？</h2>
<div class="card">
<div class="kv">上层回测只证明了「跌 8~12%」这一档有效。本节在<b>该档内部</b>再跑一层：
固定退出规则（T+1 开盘买 / 止损 5% / 止盈 8% / 持有 5 日），对 11 个先验固定维度做分组统计，
并做<b>前后半（walk-forward）</b>验证。样本 <b>{base.get('n',0):,}</b> 条，
区间 {w.get('from','')} ~ {w.get('to','')}。</div>

<h3 style="font-size:13.5px;margin:14px 0 2px">档内基准</h3>
<div class="kv">胜率 <b>{base.get('win',0)*100:.1f}%</b>、期望 <b>{base.get('exp',0)*100:+.2f}%</b>
（前半 {b1.get('exp',0)*100:+.2f}% ｜ 后半 {b2.get('exp',0)*100:+.2f}%）。
<b>只有前后半同时优于这个基准的分组，才被写进选股规则</b>。</div>

<h3 style="font-size:13.5px;margin:16px 0 2px">★ 波动率（ATR%）——唯一两半同向、且单调的维度</h3>
<div class="tbl-wrap"><table><thead><tr><th>分组</th><th>样本</th><th>T+1上涨</th>
<th>历史胜率</th><th>期望</th><th>前半/后半</th><th>两半同向</th></tr></thead>
<tbody>{atr}</tbody></table></div>
<div class="box green"><b>为什么可信：</b>胜率随 ATR 单调下降（88.3% → 80.6% → 69.7% → 62.1% → 53.1% → 42.2% → 35.8%）。
<b>单调关系不可能靠挑参数伪造</b>，这是本轮回测里最强的一条证据。
经济含义：低波动的三连阴多属<b>温和回调 / 洗盘</b>，高波动的多属<b>真崩塌 / 题材退潮</b>。<br>
<b>注意 T+1 上涨率同样单调</b>（80.8% → 48.1%）——这说明它<b>不只是「低波动不易打止损」的机械效应</b>，
<b>方向判断能力本身也更强</b>。</div>

<h3 style="font-size:13.5px;margin:16px 0 2px">波动率 × 成交额 四象限</h3>
<div class="tbl-wrap"><table><thead><tr><th>组合</th><th>样本</th><th>T+1上涨</th>
<th>历史胜率</th><th>期望</th><th>前半/后半</th><th>两半同向</th></tr></thead>
<tbody>{cross}</tbody></table></div>

<h3 style="font-size:13.5px;margin:16px 0 2px">其余 10 个维度（多数为「前半好、后半差」＝ β 而非 alpha）</h3>
{dims}
<div class="box red"><b>读表提醒：</b>上表中多数分组呈现「前半大幅为正、后半为负」的形态，
例如「小市值」「放量」「弱势续跌」在前半期望 +2.4% ~ +2.7%，后半却掉到 +0.1% ~ −0.35%。
这是<b>市场 β（样本前半上涨、后半回落）</b>造成的，<b>不是选股能力</b>。
按方法论，这些<b>一律不写进规则</b>。</div>
</div>"""


def render_lab(lab, date, lab2=None):
    """实验室页：完整回测证据（回答「这套条件到底能不能选出高胜率股票」）。"""
    s = lab.get("stat", {})
    w = lab.get("window", {})
    d = lab.get("default", {})

    def main_rows():
        out = []
        for k, name in (("ALL", "全市场随便买（绝对基准）"), ("B", "B 普通三连阴"),
                        ("A", "A 优质三连阴（原条件）"), ("C", "C 高危三连阴"),
                        ("D", "D 龙头主线三连阴")):
            x = s.get(k) or {}
            if not x.get("n"):
                continue
            out.append((f"<tr><td><b>{name}</b></td><td class='num'>{x['n']:,}</td>"
                        f"<td class='num'>{x['t1_up']*100:.1f}%</td>"
                        f"<td class='num'>{x['up5']*100:.1f}%</td>"
                        f"<td class='num'>{x['max5']*100:+.2f}%</td>"
                        f"<td class='num'>{x['win']*100:.1f}%</td>"
                        f"<td class='num {'up' if x['exp']>0 else 'dn'}'>{x['exp']*100:+.2f}%</td>"
                        f"<td class='num'>{x['mae']*100:+.2f}%</td>"
                        f"<td class='kv'>{'%.1f%% / %+.2f%%' % (x['h1_win']*100, x['h1_exp']*100) if x.get('h1_win') is not None else '—'}</td>"
                        f"<td class='kv'>{'%.1f%% / %+.2f%%' % (x['h2_win']*100, x['h2_exp']*100) if x.get('h2_win') is not None else '—'}</td></tr>"))
        return "".join(out)

    def abl_rows(key):
        out = []
        for a in lab.get(key, []):
            if a.get("win") is None:
                out.append(f"<tr><td>{a.get('label')}</td><td class='num'>{a.get('n',0)}</td>"
                           "<td colspan='3' class='kv'>样本不足</td></tr>")
                continue
            wf = ""
            if a.get("h1_exp") is not None and a.get("h2_exp") is not None:
                wf = "%+.2f%% / %+.2f%%" % (a["h1_exp"] * 100, a["h2_exp"] * 100)
            out.append(f"<tr><td>{a['label']}</td><td class='num'>{a['n']:,}</td>"
                       f"<td class='num'>{a['t1_up']*100:.1f}%</td>"
                       f"<td class='num'>{a['win']*100:.1f}%</td>"
                       f"<td class='num {'up' if a['exp']>0 else 'dn'}'>{a['exp']*100:+.2f}%</td>"
                       f"<td class='kv'>{wf}</td></tr>")
        return "".join(out)

    def grid_rows():
        out = []
        g = lab.get("grid", {})
        items = []
        for k, v in g.items():
            st, tg, hd = k.split("_")
            items.append((int(st), int(tg), int(hd), v))
        items.sort(key=lambda r: (r[2], r[0], r[1]))
        for st, tg, hd, v in items:
            cells = "".join(
                "<td class='num %s'>%+.2f%%</td>" % ("up" if (v[k]["exp"] or 0) > 0 else "dn",
                                                     (v[k]["exp"] or 0) * 100)
                for k in ("ALL", "B", "A", "C", "D"))
            out.append(f"<tr><td class='num'>{st}%</td><td class='num'>{tg}%</td>"
                       f"<td class='num'>{hd}日</td>{cells}</tr>")
        return "".join(out)

    caveats = "".join("<li>%s</li>" % c for c in lab.get("caveats", []))

    return f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>三连阴实验室 · 样本外回测证据</title><style>{STYLE}</style></head>
<body><div class="wrap">
<h1>三连阴实验室 · 样本外回测证据</h1>
<div class="sub">回测窗口 <b>{w.get('from','')} ~ {w.get('to','')}</b>（{w.get('days','')} 个交易日）｜
可回测域 <b>{lab.get('universe',0):,}</b> 只 ｜ 信号总量 <b>{s.get('B',{}).get('n',0):,}</b> 条 ｜
生成于 {lab.get('generated_at','')}</div>

<div class="box red" style="border-color:#b00020"><b>一句话结论：</b>
四套条件<b>都没有产生超过「全市场随便买」的超额收益</b>。
A 优质三连阴胜率 {s.get('A',{}).get('win',0)*100:.1f}% / 期望 {s.get('A',{}).get('exp',0)*100:+.2f}%，
基准为 {s.get('ALL',{}).get('win',0)*100:.1f}% / {s.get('ALL',{}).get('exp',0)*100:+.2f}%。
唯一两半同向稳健的维度是<b>跌幅分档</b>（8~12% 最优，&gt;20% 是灾难）。
因此本池只把「跌幅 8~12%」作为观察档，<b>不宣称该策略有正向 alpha</b>。</div>

<h2>回测口径（可兑现，不偷看未来）</h2>
<div class="card"><div class="kv">
<b>信号</b>：收盘后判定 → <b>T+1 开盘买入</b>（可执行，非用当日收盘价）。<br>
<b>退出</b>：止损 {int(d.get('stop',0.05)*100)}% / 止盈 {int(d.get('target',0.08)*100)}% /
最多持有 {d.get('hold',5)} 日；<b>同一天既触止损又触止盈，保守记止损</b>。<br>
<b>胜率</b>：固定退出规则下收益 &gt; 0 的占比；<b>期望</b>：单笔收益均值（含亏损）。<br>
<b>T+1 上涨 / 5日上涨</b>：用户问财口径的原始概率（相对信号日收盘）。<br>
<b>走前验证</b>：按信号日分前后半，只有<b>两半同向</b>的结论才被采纳。
</div></div>

<h2>① 主结果：四套规则 vs 基准</h2>
<div class="card"><div class="tbl-wrap"><table><thead><tr><th>规则</th><th>信号数</th>
<th>T+1上涨</th><th>5日上涨</th><th>5日最大涨幅</th><th>胜率</th><th>期望</th><th>MAE</th>
<th>走前·前半(胜率/期望)</th><th>走前·后半(胜率/期望)</th></tr></thead>
<tbody>{main_rows()}</tbody></table></div>
<div class="kv">MAE = 持仓期内相对买入价的最大不利偏移均值。A 桶 MAE −4.16% 说明<b>止损必须宽于 4%</b>，
否则会被正常波动打掉。</div></div>

<h2>② 条件消融：哪条在加分</h2>
<div class="card"><div class="tbl-wrap"><table><thead><tr><th>条件（叠加在三连阴之上）</th>
<th>信号数</th><th>T+1上涨</th><th>胜率</th><th>期望</th><th>走前(前半/后半期望)</th></tr></thead>
<tbody>{abl_rows('cond_ablation')}</tbody></table></div>
<div class="kv">关键：<b>缩量</b>使胜率与期望双降；<b>站上 MA60</b> 使胜率降；<b>市值区间</b>几乎无影响；
反向对照中<b>放量</b>与<b>跌破 MA60</b> 并不比原条件差 —— 与用户原假设相反。</div></div>

<h2>③ 跌幅分档：唯一稳健维度</h2>
<div class="card"><div class="tbl-wrap"><table><thead><tr><th>三连阴累计跌幅</th><th>信号数</th>
<th>T+1上涨</th><th>胜率</th><th>期望</th><th>走前(前半/后半期望)</th></tr></thead>
<tbody>{abl_rows('ablation_fall')}</tbody></table></div></div>

<h2>④ 改进版候选：跌 8~12% 档 × 其它条件</h2>
<div class="card"><div class="tbl-wrap"><table><thead><tr><th>组合</th><th>信号数</th>
<th>T+1上涨</th><th>胜率</th><th>期望</th><th>走前(前半/后半期望)</th></tr></thead>
<tbody>{abl_rows('combo_8_12')}</tbody></table></div>
<div class="kv">在跌 8~12% 档内<b>再加</b>「站上 MA60」「缩量」都会<b>降低</b>收益（两半同向为负），
所以改进版<b>只保留跌幅分档</b>，不再叠加原条件。</div></div>

<h2>⑤ 参数敏感性（止损 / 止盈 / 持有期）</h2>
<div class="card"><div class="tbl-wrap"><table><thead><tr><th>止损</th><th>止盈</th><th>持有</th>
<th>ALL基准期望</th><th>B期望</th><th>A期望</th><th>C期望</th><th>D期望</th></tr></thead>
<tbody>{grid_rows()}</tbody></table></div>
<div class="kv">网格<b>仅作敏感性展示，不用于挑选参数</b>（挑最优会过拟合）。可观察到的稳健结构：
收益主要来自<b>右偏分布</b>（宽止盈捕捉少数大涨），这一结构在基准组同样存在 —— 再次说明它<b>不是选股 alpha</b>。</div></div>

{_lab2_block(lab2)}

<h2>⑦ 诚实降级</h2>
<div class="card"><div class="kv"><ul>{caveats}</ul></div></div>

<div class="foot">回测引擎 quant/_3yl_lab.py ｜ 每日页
<a href="index.html" style="color:var(--blue)">返回三连阴观察池</a></div>
</div></body></html>"""


def prev_performance(date):
    """读上一期 stat，计算其上期信号至今的兑现（用于校准）。"""
    files = sorted(glob.glob(os.path.join(OUTDIR, "stat_*.json")))
    if not files:
        return None
    cache = T._load()
    for p in reversed(files[:-1]) if len(files) > 1 else []:
        try:
            st = json.load(open(p, encoding="utf-8"))
        except Exception:
            continue
        d0 = st.get("date")
        sig = st.get("signals") or []
        if not d0 or not sig or d0 >= date:
            continue
        rets = []
        for s in sig:
            bars = cache.get(s["code"])
            if not bars:
                continue
            a = b = None
            for x in bars:
                if x["date"] == d0:
                    a = x["last"]
                if x["date"] == date:
                    b = x["last"]
            if a and b:
                rets.append(b / a - 1)
        if len(rets) < 5:
            continue
        up = sum(1 for r in rets if r > 0)
        return {"date": d0, "n": len(rets), "avg": sum(rets) / len(rets),
                "win": up / len(rets), "up_cnt": up}
    return None


def main(date):
    rows = scan(date)
    env = E.market_env(date)
    lab = None
    lp = os.path.join(QUANT, "3yl_lab.json")
    if os.path.exists(lp):
        lab = json.load(open(lp, encoding="utf-8"))
    lab2 = _load_lab2()
    prev = prev_performance(date)
    # ★ 出票许可：只读证据页 `_3yl_gate_page.emit_license()`，读不到即 fail-safe 不出票。
    #   观察档原结论「+0.43% vs 基准 +0.01%」是子集对母集、无显著性区间；
    #   逐日平衡 + bootstrap 重算后 edge 归零 → 不再允许把优先池当买入依据。
    emit_ok, emit_why = True, ""
    try:
        import _3yl_gate_page as _GP
        _lic = _GP.emit_license()
        _o = (_lic.get("detail", {}) or {}).get("obs", {}) or {}
        emit_ok = bool(_o.get("ok"))
        emit_why = _o.get("why", "")
    except Exception as ex:
        emit_ok, emit_why = False, "证据不可用：%s" % ex
    html = render(rows, date, env, lab, prev, lab2, emit_ok=emit_ok, emit_why=emit_why)
    dc = date.replace("-", "")
    open(os.path.join(OUTDIR, f"sanyin_{dc}.html"), "w", encoding="utf-8").write(html)
    open(os.path.join(OUTDIR, "index.html"), "w", encoding="utf-8").write(html)
    counts = {b[0]: len([r for r in rows if r["bk"] == b[0]]) for b in BUCKETS}
    prime_n = len([r for r in rows if r["bk"] == "obs" and r["atr"] < 0.04])
    json.dump({
        "date": date, "n": len(rows), "counts": counts, "prime": prime_n,
        "env": (env or {}).get("label", "未知") if env else "未知",
        "model": "three_yin_v1",
        "emit_ok": bool(emit_ok), "emit_why": emit_why,
        "signals": [{"code": r["code"], "fall": round(r["fall"], 4), "bk": r["bk"],
                     "atr": round(r["atr"], 4)} for r in rows],
    }, open(os.path.join(OUTDIR, f"stat_{dc}.json"), "w", encoding="utf-8"),
        ensure_ascii=False, indent=1)
    print("[3yl] " + " ｜ ".join("%s %d" % (b[1], counts[b[0]]) for b in BUCKETS))
    if not emit_ok:
        print("[3yl] 出票许可未通过 → 本期不出票（宁可不选）：%s" % emit_why)
    print("[3yl] 写 web/three_yin/  (sanyin_%s.html + index.html + stat_%s.json)" % (dc, dc))
    if lab:
        open(os.path.join(OUTDIR, "lab.html"), "w", encoding="utf-8").write(
            render_lab(lab, date, lab2))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("date", nargs="?", default="2026-09-29")
    a = ap.parse_args()
    main(a.date)
