# -*- coding: utf-8 -*-
"""渲染 今日高胜率候选池 页面（所有表格列可点击排序）

输入：quant/picks/highwin_{DATE}.json
输出：web/picks/highwin_{YYYYMMDD}.html

用法：
    python quant/gen_highwin.py --date 2026-09-14
    python quant/gen_highwin.py               # 自动取 quant/picks 下最新一期
"""
import os, json, argparse, glob as _glob

_WBROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
R = _WBROOT   # 原写死：G:/ai/股票
Q = os.path.join(R, "quant")
WEB = os.path.join(R, "web")

# ---------- 日期参数 ----------
_AP = argparse.ArgumentParser(description="渲染高胜率候选池页面")
_AP.add_argument("--date", dest="date", help="数据日期 YYYY-MM-DD，缺省取 picks 下最新一期")
_A = _AP.parse_args()
_PICKS = os.path.join(Q, "picks")
if not _A.date:
    _cand = sorted(_glob.glob(os.path.join(_PICKS, "highwin_*.json")))
    if not _cand:
        raise SystemExit("quant/picks 下没有 highwin_*.json，先跑 build_highwin.py --date ...")
    D = os.path.basename(_cand[-1])[len("highwin_"):-len(".json")]
else:
    D = _A.date
DS = D.replace("-", "")
OUT = os.path.join(WEB, "picks", "highwin_%s.html" % DS)

d = json.load(open(os.path.join(_PICKS, "highwin_%s.json" % D), encoding="utf-8"))
print("[args] date=%s" % D)
rows = d["rows"]
cnt = d["counts"]

def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")

def num(v, nd=2, dash="—"):
    if v is None:
        return dash
    try:
        return ("{:,." + str(nd) + "f}").format(float(v))
    except Exception:
        return dash

def pct(v, nd=1, dash="—"):
    if v is None:
        return dash
    try:
        return ("{:." + str(nd) + "f}%" ).format(float(v))
    except Exception:
        return dash

def chg_cls(v):
    try:
        return "up" if float(v) > 0 else ("dn" if float(v) < 0 else "")
    except Exception:
        return ""

def tier_tag(t):
    m = {"核心": "g", "观察": "y", "备选": "y", "回避": "r"}
    return '<span class="tag %s">%s</span>' % (m.get(t, "y"), t)

def beh_tag(b):
    m = {"抢筹": "g", "建仓": "g", "洗盘": "y", "出货": "r", "未知": "y"}
    return '<span class="tag %s">%s</span>' % (m.get(b, "y"), b)

def hist_badge(r):
    ds = r.get("histDates") or []
    if not ds:
        return ""
    last = ds[-1]
    tip = "入选记录：" + "；".join("%s %s" % (h["date"], h["pool"]) for h in r.get("hist") or [])
    return ' <span class="hist" title="%s">%s</span>' % (esc(tip), last[5:])

def hist_cell(r):
    hs = r.get("hist") or []
    if not hs:
        return '<span class="note-inline">—</span>'
    out = []
    for h in hs:
        out.append('<span class="tag %s">%s %s</span>' % (
            "g" if "MACD" in h["pool"] else "y", h["date"][5:], h["pool"].replace("观察池", "").replace("信号池·", "")))
    return " ".join(out)

def flags_html(fl):
    if not fl:
        return '<span class="note-inline">—</span>'
    out = []
    for f in fl:
        cls = "r" if f in ("板块出货", "超买RSI≥90", "高位≥92%") else "y"
        out.append('<span class="tag %s">%s</span>' % (cls, esc(f)))
    return " ".join(out)

def row_html(r):
    lhb = num(r["inst_net"], 2) if r["inst_net"] else "—"
    hm = r["hotmoney"] or ""
    eb = []
    if r["exec_buy"] > 0 and r["exec_buy"] >= r["exec_sell"]:
        eb.append("高管增持")
    if r["block_inst"] > 0:
        eb.append("大宗机构买")
    eb_s = " ".join(eb) if eb else "—"
    def dv(v6):
        return ' data-v="%s"' % ("" if v6 is None else v6)
    return (
        '<tr>'
        '<td class="num">%s</td>'
        '<td><b>%s</b>%s</td>'
        '<td class="histcol">%s</td>'
        '<td class="num"%s><b>%s</b></td>'
        '<td class="num"%s>%s</td>'
        '<td class="num %s"%s>%s</td>'
        '<td class="num"%s>%s</td>'
        '<td class="num"%s>%s</td>'
        '<td class="num"%s>%s</td>'
        '<td class="num"%s>%s</td>'
        '<td class="num"%s>%s</td>'
        '<td class="num"%s>%s</td>'
        '<td class="num"%s>%s</td>'
        '<td class="num"%s>%s</td>'
        '<td class="num"%s>%s</td>'
        '<td>%s</td>'
        '<td>%s</td>'
        '<td class="num"%s>%s</td>'
        '<td>%s</td>'
        '<td>%s</td>'
        '</tr>'
    ) % (
        esc(r["code"]), esc(r["name"]), hist_badge(r),
        hist_cell(r),
        dv(r["total"]), num(r["total"], 1),
        dv(r["price"]), num(r["price"], 2),
        chg_cls(r["changePct"]), dv(r["changePct"]), pct(r["changePct"], 2),
        dv(r["macd_ratio"]), num(r["macd_ratio"], 3),
        dv(r["flow20d_yi"]), num(r["flow20d_yi"], 2),
        dv(r["dailyFlow_yi"]), num(r["dailyFlow_yi"], 3),
        dv(r["pos52"]), (pct(r["pos52"], 1) if r["pos52"] is not None else "—"),
        dv(r["turn"]), pct(r["turn"], 2),
        dv(r["volr"]), num(r["volr"], 2),
        dv(r["rsi12"]), num(r["rsi12"], 1),
        dv(r["profit"]), pct(r["profit"], 1),
        dv(r["conc90"]), num(r["conc90"], 1),
        beh_tag(r["behavior"]), esc(r["sw2"] or "—"),
        dv(r["inst_net"]), lhb + (("·" + hm + "游资") if hm and hm != "低" else ""),
        esc(eb_s), flags_html(r["flags"]),
    )

HEAD = (
    '<thead><tr>'
    '<th data-k="code" data-t="s">代码</th>'
    '<th data-k="name" data-t="s">名称</th>'
    '<th data-k="hist" data-t="s">历史入选</th>'
    '<th data-k="total" data-t="n" class="sorted-desc">总分 ▾</th>'
    '<th data-k="price" data-t="n">收盘</th>'
    '<th data-k="changePct" data-t="n">涨跌%</th>'
    '<th data-k="macd_ratio" data-t="n">MACD柱/价%</th>'
    '<th data-k="flow20d_yi" data-t="n">20D主力(亿)</th>'
    '<th data-k="dailyFlow_yi" data-t="n">当日主力(亿)</th>'
    '<th data-k="pos52" data-t="n">52周位%</th>'
    '<th data-k="turn" data-t="n">换手%</th>'
    '<th data-k="volr" data-t="n">量比</th>'
    '<th data-k="rsi12" data-t="n">RSI12</th>'
    '<th data-k="profit" data-t="n">获利盘%</th>'
    '<th data-k="conc90" data-t="n">集中90</th>'
    '<th data-k="behavior" data-t="s">板块行为</th>'
    '<th data-k="sw2" data-t="s">板块</th>'
    '<th data-k="inst_net" data-t="n">龙虎榜(亿)</th>'
    '<th data-k="eb" data-t="s">高管/大宗</th>'
    '<th data-k="flags" data-t="s">风险标记</th>'
    '</tr></thead>'
)

def table(rs):
    return ('<div class="scroll"><table class="sortable">' + HEAD + "<tbody>"
            + "".join(row_html(r) for r in rs) + "</tbody></table></div>")

core = [r for r in rows if r["tier"] == "核心"]
watch = [r for r in rows if r["tier"] == "观察"]
alt = [r for r in rows if r["tier"] == "备选"]
avoid = [r for r in rows if r["tier"] == "回避"]

# 板块热点聚合
from collections import Counter
beh_c = Counter(r["behavior"] for r in core + watch)

fn_build = lambda rs: table(rs) if rs else '<div class="box">无</div>'

HTML = '''<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>今日高胜率候选池 · 2026-09-14</title><style>
.wrap{max-width:1320px}
h1{font-size:23px;font-weight:700;margin:0 0 6px;letter-spacing:-.02em}
h2{font-size:18px;font-weight:600;margin:28px 0 12px;padding-bottom:8px;border-bottom:2px solid var(--accent)}
h3{font-size:15px;font-weight:600;margin:18px 0 8px}
.sub{color:var(--muted);font-size:13px;margin-bottom:8px}
.card{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:16px 20px;margin:12px 0;box-shadow:0 1px 2px rgba(60,64,67,.10)}
.box{border-left:4px solid var(--accent);background:var(--accent-soft);padding:14px 18px;border-radius:0 10px 10px 0;margin:14px 0}
.box.red{border-color:var(--green);background:#e6f4ea}
.box.amber{border-color:#e37400;background:#fef7e0}
table{width:100%;border-collapse:collapse;font-size:12.5px;margin:10px 0}
th,td{padding:8px 6px;border-bottom:1px solid var(--line-2);text-align:left;vertical-align:middle;white-space:nowrap}
th{color:var(--muted);font-weight:600;font-size:11.5px;background:var(--hover);position:sticky;top:0}
th[data-k]{cursor:pointer;user-select:none}
th[data-k]:hover{color:var(--accent)}
th.sorted-asc:after{content:" ▴";color:var(--accent)}
th.sorted-desc:after{content:" ▾";color:var(--accent)}
tbody tr:hover{background:var(--hover)}
.num{font-variant-numeric:tabular-nums;text-align:right}
.up{color:var(--red)}.dn{color:var(--green)}.am{color:var(--accent)}
.note-inline{color:var(--muted)}
.tag{display:inline-block;font-size:11px;padding:2px 8px;border-radius:10px;margin:1px 2px;white-space:nowrap}
.tag.r{background:#fce8e6;color:#a8071a}.tag.y{background:#fef7e0;color:#8a6d00}.tag.g{background:#e6f4ea;color:#137333}
.hist{display:inline-block;font-size:10.5px;font-weight:700;color:#137333;background:#e6f4ea;border:1px solid #b7e1c3;border-radius:8px;padding:1px 6px;margin-left:4px;cursor:help}
.histcol{white-space:normal;min-width:150px;max-width:200px}
.note{font-size:12px;color:var(--muted);margin-top:8px;padding-top:8px;border-top:1px dashed var(--line-2)}
.foot{text-align:center;color:var(--muted);font-size:12px;margin-top:28px}
ul{margin:8px 0;padding-left:20px}li{margin:4px 0}
.kpi{display:flex;gap:10px;flex-wrap:wrap;margin:10px 0}
.kpi div{flex:1;min-width:110px;background:var(--hover);border-radius:10px;padding:10px 14px}
.kpi b{display:block;font-size:20px;color:var(--accent)}
.kpi span{font-size:12px;color:var(--muted)}
.scroll{overflow-x:auto;-webkit-overflow-scrolling:touch;max-height:78vh;overflow-y:auto}
.scroll table{min-width:1380px}
</style></head><body>
<div class="wrap">
<h1>今日高胜率候选池 · 2026-09-14</h1>
__EMIT__
<div class="sub">基底：MACD 水上金叉（DIF&gt;0 且 DEA&gt;0 且 柱&gt;0）+ 20 日主力净流入&gt;0 的 <b>__N__ 只</b>（全市场扫描 __POOL__ 只）。增强：行情 / 技术(MA·RSI) / 筹码 / 板块行为 / 龙虎榜 / 高管·大宗，全部为 <b>2026-09-14 收盘</b>数据。表格所有列均可点击排序。</div>

<div class="kpi">
<div><b>__N__</b><span>候选池（MACD 水上金叉）</span></div>
<div><b>__C1__</b><span>核心候选</span></div>
<div><b>__C2__</b><span>观察候选</span></div>
<div><b>__C3__</b><span>备选</span></div>
<div><b>__C4__</b><span>回避（含风险标记）</span></div>
</div>

<div class="box"><b>打分模型（100 分 · 8 维）</b>
<ul>
<li><b>趋势/技术 25</b>：MACD 柱动能(柱/价·10) + 均线多头排列(8) + RSI12 健康区(7)</li>
<li><b>位置 15</b>：52 周分位——偏好相对中低位（25–65% 满分），过高(≥88%)降分</li>
<li><b>资金 20</b>：20 日主力净流入(12) + 当日主力净流入(4) + 流入占流通比(4)</li>
<li><b>筹码 15</b>：获利盘健康区(45–80%·8) + 90 集中度适中(12–32·7)</li>
<li><b>板块 12</b>：所属申万二级板块主力行为——抢筹12 / 建仓9 / 洗盘5 / 出货0</li>
<li><b>龙虎榜 8</b>：机构席位净买入 + 游资热度（高/中/低）</li>
<li><b>高管/大宗 5</b>：高管净增持 + 大宗机构买入</li>
</ul>
<b>硬性降级（回避）</b>：所属板块「出货」/ RSI12≥90 超买 / 52 周位≥92% 高位。
<div class="note">名称后的<span class="hist">09-11</span>绿色徽标 = 该标的<b>此前（不含今日）</b>曾被选入观察/信号池；<b>鼠标悬停</b>可看全部入选记录；对应「历史入选」列（可排序）列出全部日期与池别。</div></div>

<h2>一、核心候选（__C1__ 只 · 总分≥68 且无风险否决）</h2>
__CORE__

<h2>二、观察候选（__C2__ 只 · 55≤总分&lt;68）</h2>
__WATCH__

<h2>三、备选（__C3__ 只）</h2>
__ALT__

<h2>四、回避 / 风险名单（__C4__ 只 · 触发板块出货 / 超买 / 高位 等硬降级）</h2>
<div class="box amber">以下标的不建议追入，触发硬性降级条件；若已持有，按退出纪律执行（见下）。</div>
__AVOID__

<h2>五、使用说明与退出纪律</h2>
<div class="card">
<b>胜率的正确理解：</b>本池是「多因子共振」筛选，<b>不是</b>收益承诺。单期样本不能证明胜率——按项目纪律，需<b>累积 20–30 个交易日</b>的前向表现，再分组回测各维度胜率，方可把阈值逐步硬化。当前所有阈值仅为「观察档」，不构成趋势的充分/必要条件。
<div class="note">
<b>建议执行规则：</b>
<ul>
<li><b>入场</b>：优先核心候选，且需满足「次日不破 5 日线」或「放量突破前高」之一；不追涨停、不打板。</li>
<li><b>仓位</b>：单票 ≤ 组合 15%；核心候选合计 ≤ 60%。</li>
<li><b>退出（优先于入场）</b>：跌破 MA20 或 MACD 死叉 → 离场；单票 −8% 无条件止损；达 +15~20% 分批止盈。</li>
<li><b>板块</b>：若所属板块主力行为由「抢筹/建仓」转为「洗盘/出货」，同步降仓。</li>
</ul>
</div>
<div class="note">数据口径：行情/技术/筹码 = westock data_quote/data_technical/data_chip（2026-09-14）；板块行为 = westock data_sector（2026-09-14）；龙虎榜 = westock data_lhb 机构席位（2026-09-14）；高管增减持 = 东财 RPT_EXECUTIVE_HOLD_DETAILS（变动日 2026-09-14）；大宗 = 东财 RPT_DATA_BLOCKTRADE（2026-09-14）。</div>
</div>

<div class="foot">
<b>免责声明</b>：以上内容基于公开数据和量化分析，仅供参考，不构成投资建议。市场有风险，投资需谨慎。<br>
任何投资决策应结合个人风险承受能力、资金状况和投资目标独立判断，必要时咨询持牌专业机构。过往表现不预示未来收益。
</div>
</div>
<script>
(function(){
  function cellVal(tr, idx, type){
    var td = tr.cells[idx];
    if(!td) return type==='n' ? -Infinity : '';
    var raw = td.getAttribute('data-v');
    var txt = (raw!==null? raw : td.textContent).trim();
    if(type==='n'){
      var v = parseFloat(txt.replace(/[,%·万亿+]/g,''));
      return isNaN(v) ? -Infinity : v;
    }
    return txt;
  }
  document.querySelectorAll('table.sortable').forEach(function(tb){
    var ths = tb.querySelectorAll('thead th[data-k]');
    ths.forEach(function(th, ci){
      th.addEventListener('click', function(){
        var tbody = tb.tBodies[0];
        var arr = Array.prototype.slice.call(tbody.rows);
        var type = th.getAttribute('data-t') || 'n';
        var cur = th.getAttribute('data-dir');
        var dir = (cur === 'asc') ? 'desc' : 'asc';
        ths.forEach(function(o){ o.removeAttribute('data-dir'); o.classList.remove('sorted-asc','sorted-desc'); });
        th.setAttribute('data-dir', dir);
        th.classList.add(dir==='asc' ? 'sorted-asc' : 'sorted-desc');
        arr.sort(function(a,b){
          var va = cellVal(a, ci, type), vb = cellVal(b, ci, type);
          if(va < vb) return dir==='asc' ? -1 : 1;
          if(va > vb) return dir==='asc' ? 1 : -1;
          return 0;
        });
        arr.forEach(function(tr){ tbody.appendChild(tr); });
      });
    });
  });
})();
</script>
</body></html>'''

# ★ 出票许可横幅：只读 build_highwin 写进 JSON 的 emit_ok/emit_why，页面不自己算统计。
#   ★ 三态，缺一不可：
#     有 emit_ok=False → 不出票，附原因
#     有 emit_ok=True  → 通过
#     **没有 emit_ok 键**（本页生成时尚未做核验）→ 只能写「无核验证据，仅作历史记录」。
#       绝不能默认当成「通过」—— 那是把没验过的东西说成验过了（项目红线：宁可不选）。
EMIT_HAS = "emit_ok" in d
EMIT_OK = bool(d.get("emit_ok"))
EMIT_WHY = str(d.get("emit_why", "") or "")

# ★ 底池冻结窗口：本页日期若落在「MACD 快照逐字节未重扫」的那几期里，
#   不管 JSON 里有没有 emit_ok，都必须写明这批候选不是当日数据。
FRZ = []
try:
    _fz = json.load(open(os.path.join(Q, "_hw_tier_gate.json"), encoding="utf-8"))
    _all = sorted(_fz.get("freeze") or [], key=lambda x: x["file"])
    _fi = [i for i, r in enumerate(_all) if r.get("frozen")]
    if _fi:
        _org = _all[_fi[0] - 1] if _fi[0] > 0 else _all[_fi[0]]
        FRZ = {"from": _org["file"], "to": _all[-1]["file"],
               "close_date": (_all[_fi[-1]].get("frozen_close_date") or ""),
               "hit": _all[_fi[-1]].get("frozen_close_hit"),
               "n": _all[_fi[-1]].get("frozen_close_n")}
except Exception:
    FRZ = []

_FOOT = ('<div class="note" style="margin-top:26px;padding-top:12px;'
         'border-top:1px dashed var(--line-2);font-size:12px;color:var(--muted)">'
         '出票依据：<a href="highwin_tier_gate.html">分档出票核验（逐日平衡 edge + bootstrap + 留一法 + 跨步长）</a>'
         ' ｜ <a href="index.html">← 返回信号池首页</a></div>')
if FRZ and FRZ["from"] <= DS <= FRZ["to"]:
    EMIT_HTML = ('<div class="box red" style="border-color:#b00020">'
                 '<b>⚠ 本期不出票（宁可不选）—— 底池不是当日数据</b><br>'
                 'MACD 技术底池在 <b>%s ~ %s</b> 期间<b>逐字节没有重扫</b>（dif / dea / close 全同）；'
                 '把快照里的收盘价拿去日K 反查，<b>%s / %s 只精确等于 %s</b>。<br>'
                 '也就是说这期页面标的「当日候选」用的是一份 <b>%s 的旧快照</b>冒充当日数据，'
                 '直接违反「严禁用旧数据冒充当日」。下面表格<b>只作历史记录，不构成任何买入依据</b>。%s</div>'
                 % (FRZ["from"], FRZ["to"], FRZ["hit"], FRZ["n"],
                    FRZ["close_date"], FRZ["close_date"], _FOOT))
elif not EMIT_HAS:
    EMIT_HTML = ('<div class="box amber"><b>⚠ 本页未做出票核验（无证据）</b> —— '
                 '这期页面生成时还没有「出票许可」这道闸，<b>未经样本外验证</b>，'
                 '只作历史记录，<b>不构成任何买入依据</b>。'
                 '现行候选是否还能出票，请看页脚链接的核验页（结论：不出票）。%s</div>' % _FOOT)
elif EMIT_OK:
    EMIT_HTML = ('<div class="box"><b>出票许可：已通过</b> —— 本页候选可作买入依据。'
                 '核验过程见页脚链接。%s</div>' % _FOOT)
else:
    EMIT_HTML = ('<div class="box red" style="border-color:#b00020">'
                 '<b>⚠ 本期不出票（宁可不选）</b> —— 下面这张表只作<b>观察参考</b>，'
                 '<b>不构成任何买入依据</b>。<br>原因：%s<br>'
                 '（本页不写任何「改个阈值就能用」的建议；先把依据修好再说。）%s</div>'
                 % (esc(EMIT_WHY) or "未读到出票许可证据", _FOOT))

HTML = (HTML
        .replace("2026-09-14", D)
        .replace("__EMIT__", EMIT_HTML)
        .replace("__POOL__", num(d.get("pool_total"), 0))
        .replace("__N__", str(len(rows)))
        .replace("__C1__", str(cnt.get("核心", 0)))
        .replace("__C2__", str(cnt.get("观察", 0)))
        .replace("__C3__", str(cnt.get("备选", 0)))
        .replace("__C4__", str(cnt.get("回避", 0)))
        .replace("__CORE__", fn_build(core))
        .replace("__WATCH__", fn_build(watch))
        .replace("__ALT__", fn_build(alt))
        .replace("__AVOID__", fn_build(avoid)))

os.makedirs(os.path.join(WEB, "picks"), exist_ok=True)
with open(OUT, "w", encoding="utf-8") as f:
    f.write(HTML)
print("[ok] wrote", OUT, len(HTML), "bytes")
print("核心%d 观察%d 备选%d 回避%d" % (len(core), len(watch), len(alt), len(avoid)))
