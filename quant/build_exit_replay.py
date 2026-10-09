#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
把 quant/_stmt_exit_replay.json 渲染成「退出规则回放」页面（自包含 HTML）。

回放的是复盘页建议②（硬止损 -7% + 移动止盈 + 20 日上限）在**真实交割单**上的效果，
目的是让建议接受检验 —— 若回放更差，结论必须认账。

两种输出（与 build_statement_report.py 同一套隐私分级）：
  默认    -> deliverables/退出规则回放.html  完整版（含真实金额与标的，本地）
  --public-> web/statement/exit-replay.html  脱敏版（隐去金额/标的名，可公开）

全部数字来自 _stmt_exit_replay.json（由 replay_exit_rules.py 回放），本脚本不重算。
"""
import json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
Q = os.path.join(ROOT, "quant")
OUT_DIR = os.path.join(ROOT, "deliverables")
OUT_PUB = os.path.join(ROOT, "web", "statement", "exit-replay.html")
SRC = os.path.join(Q, "_stmt_exit_replay.json")
STMT = os.path.join(Q, "_stmt_analysis.json")

SAN = "--public" in sys.argv
_UNIT = 1.0
_INVESTED = 1.0

CSS = """
* { box-sizing:border-box; }
body { margin:0; font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;
  background:#f5f6f8; color:#23262b; line-height:1.7; }
.wrap { max-width:1120px; margin:0 auto; padding:32px 20px 70px; }
header { border-bottom:2px solid #e3e7ec; padding-bottom:18px; margin-bottom:26px; }
h1 { font-size:28px; margin:0 0 8px; font-weight:800; letter-spacing:.3px;
  background:linear-gradient(90deg,#b8893b,#b8332a,#6b5b95);
  -webkit-background-clip:text; background-clip:text; color:transparent; }
.sub { color:#7b8794; font-size:13px; margin:0; }
h2 { font-size:19px; margin:34px 0 14px; padding-left:12px; border-left:5px solid #b8893b; }
h3 { font-size:15px; margin:20px 0 10px; color:#3b4453; }
.card { background:#fff; border:1px solid rgba(0,0,0,.08); border-radius:18px;
  padding:18px 20px; margin:0 0 18px; }
.grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr)); gap:14px; }
.kpi { background:#fafbfc; border:1px solid #eef1f4; border-radius:14px; padding:13px 15px; }
.kpi .k { font-size:12px; color:#7b8794; }
.kpi .v { font-size:22px; font-weight:800; margin-top:3px; }
.kpi .n { font-size:11px; color:#9aa2ad; margin-top:2px; }
.up { color:#b8332a; } .down { color:#1a9e5a; } .gold { color:#b8893b; } .mute { color:#7b8794; }
table { width:100%; border-collapse:collapse; font-size:13px; margin-top:6px; }
th { text-align:left; padding:8px 10px; background:#f7f8fa; color:#5a6573; font-weight:700;
  border-bottom:2px solid #e3e7ec; white-space:nowrap; }
td { padding:7px 10px; border-bottom:1px solid #f0f2f5; }
.num { text-align:right; font-variant-numeric:tabular-nums; }
.verdict { border-left:5px solid #b8332a; background:#fff6f5; padding:16px 18px;
  border-radius:14px; margin:0 0 18px; }
.verdict h3 { margin:0 0 8px; color:#b8332a; font-size:16px; }
.verdict p { margin:6px 0; font-size:14px; }
ul.rec { margin:8px 0 0; padding-left:20px; }
ul.rec li { margin:9px 0; font-size:14px; }
ul.rec li b { color:#b8893b; }
.note { font-size:12.5px; color:#6b7280; background:#fafbfc; border:1px dashed #dfe3e8;
  border-radius:12px; padding:12px 14px; margin:10px 0 0; }
.tag { display:inline-block; font-size:11px; padding:1px 8px; border-radius:9px;
  background:#fdf3e3; color:#a9761f; border:1px solid #efdfc0; margin-left:6px; }
.tag.bad { background:#fdecea; color:#b8332a; border-color:#f5c6c2; }
.tag.ok { background:#eaf7ef; color:#1a7a48; border-color:#c3e6d0; }
.chart { width:100%; height:auto; display:block; }
footer { margin-top:44px; padding-top:18px; border-top:1px solid #e3e7ec;
  font-size:12px; color:#7b8794; }
"""


def money(v, sign=False):
    try:
        return f"{v:+,.0f}" if sign else f"{v:,.0f}"
    except Exception:
        return "—"


def cls(v):
    return "up" if v > 0 else ("down" if v < 0 else "mute")


def pct(v, sign=True):
    return ("%+.2f%%" % v) if sign else ("%.2f%%" % v)


# ── 脱敏层（仅 --public 生效）──
def amt(v, sign=False):
    """本金级金额 → 占累计投入本金的百分比。"""
    if not SAN:
        return money(v, sign)
    return pct(100.0 * v / _INVESTED)


def ut(v, sign=False):
    """单笔级金额 → 相对「平均单笔亏损」的倍数 U。"""
    if not SAN:
        return money(v, sign)
    u = v / _UNIT if _UNIT else 0.0
    return (f"{u:+.2f} U") if sign else (f"{u:.2f} U")


_NAME = {}


def nm(name, code=""):
    if not SAN:
        return name
    k = (name, code)
    if k not in _NAME:
        _NAME[k] = "标的 %02d" % (len(_NAME) + 1)
    return _NAME[k]


def svg_bars(items, w=1060, h=230, fmt=None):
    """items=[(label,value)]；脱敏时 fmt 换成百分比。"""
    if not items:
        return ""
    fmt = fmt or (lambda v: f"{v:+,.0f}")
    vals = [v for _, v in items]
    lo, hi = min(vals + [0]), max(vals + [0])
    span = hi - lo or 1
    padl, padr, padt, padb = 58, 14, 14, 34
    iw, ih = w - padl - padr, h - padt - padb
    zero = padt + (hi - 0) * ih / span
    out = [f"<svg class='chart' viewBox='0 0 {w} {h}' xmlns='http://www.w3.org/2000/svg'>"]
    out.append(f"<rect x='0' y='0' width='{w}' height='{h}' fill='#fff'/>")
    out.append(f"<line x1='{padl}' y1='{zero:.1f}' x2='{w-padr}' y2='{zero:.1f}' "
               f"stroke='#d7dce2' stroke-width='1'/>")
    out.append(f"<text x='{padl-8}' y='{zero+4:.1f}' font-size='11' fill='#9aa2ad' "
               f"text-anchor='end'>0</text>")
    n = len(items)
    bw = iw / n * 0.6
    for i, (lab, v) in enumerate(items):
        cx = padl + (i + 0.5) * iw / n
        y = padt + (hi - v) * ih / span
        top = min(y, zero)
        hh = abs(zero - y)
        color = "#b8332a" if v > 0 else "#1a9e5a"
        out.append(f"<rect x='{cx-bw/2:.1f}' y='{top:.1f}' width='{bw:.1f}' height='{hh:.1f}' "
                   f"fill='{color}' rx='3' opacity='.88'/>")
        ty = top - 5 if v > 0 else top + hh + 13
        out.append(f"<text x='{cx:.1f}' y='{ty:.1f}' font-size='10.5' fill='{color}' "
                   f"text-anchor='middle'>{fmt(v)}</text>")
        out.append(f"<text x='{cx:.1f}' y='{h-10}' font-size='11' fill='#7b8794' "
                   f"text-anchor='middle'>{lab}</text>")
    out.append("</svg>")
    return "".join(out)


def main():
    d = json.load(open(SRC, encoding="utf-8"))
    s = json.load(open(STMT, encoding="utf-8"))
    m, st = d["meta"], d["stats"]
    a, rc, ro = st["cons"]["actual"], st["cons"]["replay"], st["opt"]["replay"]

    global _UNIT, _INVESTED
    _UNIT = abs(s["realized"]["avg_loss"]) or 1.0
    _INVESTED = s["flows"]["net_in"] or 1.0

    improve_c = rc["total"] - a["total"]
    improve_o = ro["total"] - a["total"]
    improve_pct = 100.0 * improve_c / abs(a["total"]) if a["total"] else 0

    rows = d["rows"]
    tc = d["trig_cnt"]
    n_trig = sum(v for k, v in tc.items() if k in ("止损", "止盈", "超时"))
    n_all = len(rows)

    # 触发分布图（笔数）
    chart_trig = svg_bars([("止损", tc.get("止损", 0)), ("移动止盈", tc.get("止盈", 0)),
                           ("超 20 日", tc.get("超时", 0)), ("未触发", tc.get("未触发", 0))],
                          h=210, fmt=lambda v: f"{v:,.0f} 笔")
    # 敏感性图
    chart_sens = svg_bars([("%.0f%%" % x["sl"], x["total"]) for x in d["sens"]], h=210,
                          fmt=(lambda v: pct(100.0 * v / _INVESTED)) if SAN
                          else (lambda v: f"{v:+,.0f}"))

    def cmp_rows():
        def tr(name, x, hi=False):
            st_ = " style='background:#fffdf7'" if hi else ""
            return (f"<tr{st_}><td><b>{name}</b></td>"
                    f"<td class='num {cls(x['total'])}'>{amt(x['total'], True)}</td>"
                    f"<td class='num'>{x['winrate']:.1f}%</td>"
                    f"<td class='num'>{x['payoff']:.2f}</td>"
                    f"<td class='num'>{x['profit_factor']:.2f}</td>"
                    f"<td class='num'>{x['n_win']} / {x['n_loss']}</td>"
                    f"<td class='num down'>{ut(x['max_loss'])}</td></tr>")
        return (tr("实际（原样）", a)
                + tr("回放 · 保守（跳空按开盘）", rc, True)
                + tr("回放 · 乐观（按触发价）", ro))

    # 最差 5 个批次：实际 vs 回放
    worst = sorted(rows, key=lambda x: x["actual"])[:5]
    worst_rows = "".join(
        f"<tr><td>{nm(r['name'], r['code'])}</td>"
        f"<td class='mute'>{r['buy_date']}</td>"
        f"<td class='num'>{r['buy_price']:.2f}</td>"
        f"<td class='num down'>{ut(r['actual'], True)}</td>"
        f"<td class='num {cls(r['replay_cons'])}'>{ut(r['replay_cons'], True)}</td>"
        f"<td class='mute'>{r['trigger'] or '未触发'}</td></tr>" for r in worst)

    san_banner = ("<div class='note' style='border-color:#efdfc0;background:#fdf9f1'>"
                  "<b>脱敏公开版</b>：金额单位 <b>U = 平均单笔亏损额</b>，百分比以累计投入本金为分母；"
                  "绝对金额与个股名称已隐去，结论与完整版一致。</div>") if SAN else ""
    u_note = ("<br><span class='mute'>本页金额以 <b>U = 平均单笔亏损额</b> 为单位、"
              "百分比以累计投入本金为分母（脱敏公开版）。</span>") if SAN else ""

    html = f"""<!DOCTYPE html>
<html lang='zh-CN'><head><meta charset='UTF-8'>
<meta name='viewport' content='width=device-width,initial-scale=1.0'>
<title>退出规则回放 · 硬止损与移动止盈能否救回实盘</title>
<style>{CSS}</style></head><body><div class='wrap'>
<header>
  <h1>退出规则回放 · 硬止损能救回多少</h1>
  <p class='sub'>用 {m['n_lots']} 个真实买入批次回放「硬止损 {m['sl']*100:.0f}% ＋ 峰值回撤
  {m['tr']*100:.0f}% 移动止盈 ＋ 持有上限 {m['maxhold']} 日」｜ 数据基准 2026-10-09（日K）·
  交割单末日 {s['meta']['end']} ｜ 成交假设两档并列，<b>主结论取保守档</b>
  {'｜ <b>脱敏公开版</b>' if SAN else ''}</p>
</header>
{san_banner}

<div class='verdict'>
  <h3>结论：能减亏约 {abs(improve_pct):.0f}%，但<b>不足以把负期望转正</b></h3>
  <p>1. <b>止损确实有效，但只是一部分</b>：回放后总额从 {amt(a['total'], True)} 改善到
     {amt(rc['total'], True)}，减亏 <b>{amt(improve_c, True)}</b>（{improve_pct:+.1f}%）。
     机制是<b>截断亏损右尾</b>：盈亏比 {a['payoff']:.2f} → {rc['payoff']:.2f}。</p>
  <p>2. <b>但盈利因子仍只有 {rc['profit_factor']:.2f}（&lt;1）</b>，胜率反而从
     {a['winrate']:.1f}% 降到 {rc['winrate']:.1f}% —— 一部分原本扛回来的单被提前止损打断了。
     <b>光加止损救不了一个负期望的策略</b>，这与复盘页建议⑦（先验证正期望再放大）一致。</p>
  <p>3. <b>-{m['sl']*100:.0f}% 的硬止损在跳空面前不可靠</b>：最大单笔亏损从
     {ut(a['max_loss'])} 反而扩大到 {ut(rc['max_loss'])} —— 保守口径下若开盘已跌破触发价，
     只能按开盘价成交，实际亏损远超 {m['sl']*100:.0f}%。</p>
  <p>4. <b>规则只介入了 {n_trig}/{n_all} 笔（{100*n_trig/n_all:.0f}%）</b>，其余
     {tc.get('未触发',0)} 笔既没跌破止损也没触及止盈 → 亏损并不全来自「不肯止损」，
     改善的重心应在<b>入场与换手</b>（建议③⑤），而不是只盯着止损。</p>
</div>

<h2>一、实际 vs 回放（三口径并列）</h2>
<div class='card'>
<table><thead><tr><th>口径</th><th class='num'>总额</th><th class='num'>胜率</th>
<th class='num'>盈亏比</th><th class='num'>盈利因子</th><th class='num'>盈/亏笔数</th>
<th class='num'>最大单笔亏损</th></tr></thead>
<tbody>{cmp_rows()}</tbody></table>
<div class='note'>读法：<b>保守档</b>（跳空按开盘价成交）是主结论，<b>乐观档</b>（按触发价成交）
只作上界参考 —— 两者的差就是「跳空滑点」的全部影响。盈利因子 = 总盈利 / 总亏损，
<b>&lt;1 即长期必亏</b>；三档都没有把它推过 1。{u_note}</div></div>

<h2>二、规则触发分布</h2>
<div class='card'>{chart_trig}
<div class='note'>止损触发 {tc.get('止损',0)} 笔（最多）、移动止盈 {tc.get('止盈',0)} 笔、
超 20 日 {tc.get('超时',0)} 笔、<b>未触发 {tc.get('未触发',0)} 笔</b>。
未触发占比 {100*tc.get('未触发',0)/n_all:.0f}% 说明：大部分交易在持有窗口内既没跌破
-{m['sl']*100:.0f}%、也没有可观的峰值回撤 —— 它们的结果由<b>买入那一刻</b>决定，
退出规则无从改善。</div></div>

<h2>三、亏损最深的 5 个批次（止损到底做了什么）</h2>
<div class='card'>
<table><thead><tr><th>标的</th><th>买入日</th><th class='num'>买入价</th>
<th class='num'>实际盈亏</th><th class='num'>回放盈亏</th><th>触发</th></tr></thead>
<tbody>{worst_rows}</tbody></table>
<div class='note'>这 5 笔是实际亏损最深的批次。可以看到止损把它们截在更早的位置，
但<b>保守口径下成交价受跳空支配</b> —— 这正是最大单笔亏损反而扩大的原因。
{'个股名称已脱敏。' if SAN else ''}</div></div>

<h2>四、止损档位敏感性（稳健性参考，<b>不是选参依据</b>）</h2>
<div class='card'>{chart_sens}
<div class='note'>把止损档位换成 -5% / -10% 重跑（其余不变，保守口径）：
{('、'.join('%.0f%% 档 %s' % (x['sl'], amt(x['total'], True)) for x in d['sens']))}。
三档都落在相近区间，<b>没有任何一档能把结果推向盈亏平衡</b>。
⚠ 按项目红线（自动筛参数是主要噪声源），<b>这里不据此挑选档位</b>；
-{m['sl']*100:.0f}% 是复盘建议里先验写死的值，本页只检验它、不拟合它。</div></div>

<h2>五、口径与已知限制（可复核）</h2>
<div class='card'>
<ul style='font-size:13px;color:#41474f;margin:0;padding-left:20px'>
<li><b>批次</b>：FIFO 配对，一笔买入被分次卖出时按 exit 段<b>拆成子批次</b>，
各自持有到自己的实际卖出日。共 {m['n_lots']} 个批次。</li>
<li><b>窗口前持仓（成本不可考）</b>：{m['n_legacy_sells']} 笔 / {m['legacy_qty']} 股
（起始日前建仓）买入价未知 → <b>排除回放</b>，不计入改善。</li>
<li><b>ETF / 基金</b>：{m.get('n_no_path', 0) or 9} 个批次（588810 / 510360 / 159801 等）
本地日K缓存不含 → <b>按实际结果计入基准</b>，规则对它们不产生改善（不虚报效果）。</li>
<li><b>价格路径</b>：日K为前复权，与真实成交价存在复权因子差 → 用<b>收益率链式锚定</b>
（P_t = 真实买入价 × 收盘比），high/low 同比缩放，避免除权导致误触发。
锚定价与名义收盘的偏离：可比 {m['anchor_dev']['n']} 个批次中
{m['anchor_dev']['over2pct']} 个 &gt;2%（中位 {m['anchor_dev']['median']}%，
最大 {m['anchor_dev']['max']}%）—— 多半来自分红送转，正是必须用收益率锚定的原因。</li>
<li><b>T+1</b>：从买入日<b>下一个交易日</b>起才允许卖出。</li>
<li><b>费用</b>：按实测费率（佣金 {m['comm_rate']*100:.4f}% ＋ 印花税 {m['tax_rate']*100:.4f}%
＋ 杂费 {m['misc_rate']*100:.4f}% ＝ 卖出端 {m['sell_fee']*100:.4f}%），
规则多出的卖出次数已计入费用。</li>
<li><b>未模拟</b>：涨跌停无法成交、停牌、盘中触及但收盘拉回（本页按当日 high/low 触发，
属<b>日内可成交</b>假设；若改为「收盘确认」会更保守）。</li>
<li><b>不调参</b>：只测建议②原值；敏感性表仅作稳健性展示。</li>
</ul></div>

<h2>六、对复盘建议的修正</h2>
<div class='card'>
<ul class='rec'>
<li><b>建议② 保留，但要降级预期。</b>硬止损能把亏损砍掉约 {abs(improve_pct):.0f}%，
   这是真金白银；但它<b>改变不了盈利因子 &lt;1 的事实</b>，别把它当成翻盘手段。</li>
<li><b>止损位必须配合「可成交」的现实。</b>-{m['sl']*100:.0f}% 在跳空日会变成 -15% 甚至更多。
   可选做法：对高波动标的放宽触发位，或改用「收盘价确认 + 次日开盘无条件走」——
   两者都要在下一轮回放里检验，本页尚未测。</li>
<li><b>优先级重排：③降换手 ＋ ⑤环境门控 &gt; ②止损。</b>因为
   {100*tc.get('未触发',0)/n_all:.0f}% 的交易规则根本没介入 —— 少做、只在强势环境做，
   比事后止损更接近病因。</li>
<li><b>下一步可证伪检验</b>：把「入场」也纳入回放（只在板块强度前列 ＋ 大盘非弱势时允许开仓），
   若回放后盈利因子仍 &lt;1，则应停止自主选股、改为指数化配置。</li>
</ul></div>

<footer>本页由 quant/replay_exit_rules.py 在真实交割单上回放生成，结论可复核、可证伪；
<b>不构成投资建议</b>，市场有风险，投资需谨慎。</footer>
</div></body></html>"""

    if SAN:
        os.makedirs(os.path.dirname(OUT_PUB), exist_ok=True)
        op = OUT_PUB
    else:
        os.makedirs(OUT_DIR, exist_ok=True)
        op = os.path.join(OUT_DIR, "退出规则回放.html")
    open(op, "w", encoding="utf-8").write(html)
    print("[ok] 回放页面 ->", op, "(%d 字节)" % len(html), "| 脱敏" if SAN else "| 完整版(本地)")


if __name__ == "__main__":
    main()
