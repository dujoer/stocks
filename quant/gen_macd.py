# -*- coding: utf-8 -*-
"""MACD 水上金叉 + 20 日主力净流入 · 板块生成器。

消费 quant/macd_scan_{DATE}.json（macd_build.py 实拉筛选后落盘），渲染：
  web/macd/watchlist_{DATE}.html   每日候选明细（dated）
  web/macd/index.html               板块入口（方法论 + 最新候选 + 归档）
  web/macd/method.html              方法论常驻页

用法：
  python quant/gen_macd.py                 # 自动取最新 macd_scan_*.json
  python quant/gen_macd.py 20260911        # 指定数据日期（compact）

约定：配色/骨架统一由 quant/_theme.css 注入（Google Material 风，涨红绿跌）；
本页不内嵌导航，_apply_theme.py 按 web/macd/ 统一注入。不输出任何买卖建议。
"""
from __future__ import annotations
import os, re, json, glob, datetime, argparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QUANT = os.path.join(ROOT, "quant")
WEB = os.path.join(ROOT, "web")
OUTDIR = os.path.join(WEB, "macd")
os.makedirs(OUTDIR, exist_ok=True)

# 2026-09-19 起：本板块不再作为独立「选股」入口主推。
# 其两层条件（水上金叉 / 20 日主力净流入为正）已并入精选池（web/picks）作为技术确认门槛，
# 同时本扫描仍是「高胜率候选池」的基底（macd_scan_{DATE}.json），故继续日更、不停止扫描。
MERGE_NOTE = (
    "<div class='box' style='border-left:4px solid var(--accent)'>"
    "<b>本板块已并入「精选池」，此处仅作技术面观察归档</b><br>"
    "「水上金叉 + 20 日主力净流入为正」已并入 "
    "<a href='../picks/index.html'><b>精选池</b></a>：最高档直接出池，"
    "次高档须通过「20 日主力净流入为正」才出池；未通过者一律折叠为仅跟踪。<br>"
    "本页继续每日扫描（同时作为高胜率候选池的基底），但<b>不再单独给出建仓建议</b>，"
    "请以精选池的当日出池名单为准。</div>")

# 仅保留本板块特有组件；配色/字体/底卡全部继承 _theme.css 的设计变量
CSS = """.wrap{max-width:1180px}
h1{font-size:23px;font-weight:700;margin:0 0 6px;letter-spacing:-.02em}
h2{font-size:18px;font-weight:600;margin:28px 0 12px;padding-bottom:8px;border-bottom:2px solid var(--accent)}
h3{font-size:15px;font-weight:600;margin:18px 0 8px}
.sub{color:var(--muted);font-size:13px;margin-bottom:8px}
.card{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:16px 20px;margin:12px 0;
  box-shadow:0 1px 2px rgba(60,64,67,.10)}
.box{border-left:4px solid var(--accent);background:var(--accent-soft);padding:14px 18px;border-radius:0 10px 10px 0;margin:14px 0}
.box.gold{border-color:var(--accent);background:var(--accent-soft)}
.box.red{border-color:var(--green);background:#e6f4ea}
.box.amber{border-color:#e37400;background:#fef7e0}
table{width:100%;border-collapse:collapse;font-size:12.5px;margin:10px 0}
th,td{padding:8px 6px;border-bottom:1px solid var(--line-2);text-align:left;vertical-align:top}
th{color:var(--muted);font-weight:600;font-size:11.5px;background:var(--hover)}
tbody tr:hover{background:var(--hover)}
.num{font-variant-numeric:tabular-nums}
.up{color:var(--red)}.dn{color:var(--green)}.am{color:var(--accent)}
.warn{color:#a8071a;font-weight:600}.amber-t{color:#b06000;font-weight:600}
.tag{display:inline-block;font-size:11px;padding:2px 8px;border-radius:10px;margin:1px 2px;white-space:nowrap}
.tag.r{background:#fce8e6;color:#a8071a}
.tag.y{background:#fef7e0;color:#8a6d00}
.tag.g{background:#e6f4ea;color:#137333}
.note{font-size:12px;color:var(--muted);margin-top:8px;padding-top:8px;border-top:1px dashed var(--line-2)}
.arch{font-size:13px;margin:4px 0}
.arch a{color:var(--accent);text-decoration:none}
.arch a:hover{text-decoration:underline}
.foot{text-align:center;color:var(--muted);font-size:12px;margin-top:28px}
ul{margin:8px 0;padding-left:20px}li{margin:4px 0}
.kpi{display:flex;gap:10px;flex-wrap:wrap;margin:10px 0}
.kpi div{flex:1;min-width:120px;background:var(--hover);border-radius:10px;padding:10px 14px}
.kpi b{display:block;font-size:20px;color:var(--accent)}
.kpi span{font-size:12px;color:var(--muted)}
.scroll{overflow-x:auto;-webkit-overflow-scrolling:touch;max-height:78vh;overflow-y:auto}
.scroll table{min-width:1180px}
thead th{position:sticky;top:0;z-index:2}
th[data-k]{cursor:pointer;user-select:none}
th[data-k]:hover{color:var(--accent)}
th.sorted-asc:after{content:" \u25b4";color:var(--accent)}
th.sorted-desc:after{content:" \25be";color:var(--accent)}
.num{text-align:right}
.hist{display:inline-block;font-size:10.5px;font-weight:700;color:#137333;background:#e6f4ea;border:1px solid #b7e1c3;border-radius:8px;padding:1px 6px;margin-left:4px;cursor:help}
.newb{display:inline-block;font-size:10.5px;font-weight:700;color:#1a73e8;background:#e8f0fe;border:1px solid #c6dafc;border-radius:8px;padding:1px 6px;margin-left:4px;cursor:help}
.streakb{display:inline-block;font-size:10.5px;font-weight:700;color:#76360c;background:#fdf0e3;border:1px solid #f3cf9f;border-radius:8px;padding:1px 6px;margin-left:4px;cursor:help}
.hotb{display:inline-block;font-size:10.5px;font-weight:700;color:#a8071a;background:#fce8e6;border:1px solid #f3b1ab;border-radius:8px;padding:1px 6px;margin-left:4px;cursor:help}
.resb{display:inline-block;font-size:10.5px;font-weight:700;color:#0b6b3a;background:#e6f4ea;border:1px solid #a8ddbe;border-radius:8px;padding:1px 6px;margin-left:4px;cursor:help}
.histcol{white-space:normal;min-width:158px;max-width:215px}
.note-inline{color:var(--muted)}
.cmp{display:flex;gap:10px;flex-wrap:wrap;margin:10px 0}
.cmp div{flex:1;min-width:130px;border-radius:10px;padding:10px 14px;background:var(--hover)}
.cmp b{display:block;font-size:19px}
.cmp span{font-size:12px;color:var(--muted)}
.cmp .cnew b{color:#1a73e8}.cmp .ccont b{color:#137333}.cmp .cout b{color:#a8071a}
"""

CRITERIA = [
    ("初筛 · 主力流入池", "westock tool_filter：preset=main_inflow，min_inflow=0.3 亿，market=hs。全市场约 {N} 只满足，取前 200 进入技术验证。"),
    ("技术 · 水上金叉", "data_technical 取 MACD：要求 DIF &gt; 0 且 DEA &gt; 0 且 MACD 红柱 &gt; 0。三者同时在零轴上方 = 多头趋势已确立的真金叉，区别于零轴下方的「水下金叉」（仅是下跌中继反弹）。"),
    ("资金 · 20 日净流入为正", "data_fund_flow 取 MainNetFlow20D：要求 20 日主力净流入 &gt; 0。剔除「当日拉升热、近 20 日却在撤」的伪强势（如亨通光电 20 日净流出 −41 亿、风语筑 −1.6 亿，均被剔除）。"),
]

EXTRA_SOURCE = "data_quote + data_chip + data_fund_flow（同一交易日收盘）"

# ── 增强诊断列：判定规则（阈值后的括号为「警示」触发条件）──
DIAG_RULES = [
    ("52 周分位", "pos52 = (现价 − 52周低) ÷ (52周高 − 52周低)", "≥ 80% 标红（高位追涨）；≥ 70% 标橙"),
    ("量比", "volume_ratio", "&lt; 1 标红：缩量金叉，无量突破易假"),
    ("换手率", "turnover_rate", "&gt; 15% 标橙：换手过热，筹码剧烈易手"),
    ("5 日主力净额", "MainNetFlow5D", "≤ 0 且 20 日仍为正 → 标红：资金减速 / 疑似派发"),
    ("归一化强度", "MainNetFlow20D ÷ 流通市值 × 100", "横向可比口径，绝对值不可比"),
    ("60 日涨幅", "chg_60d", "20 日为正而 60 日仍为负 → 标红：疑似反弹非趋势"),
    ("获利盘", "chipProfitRate", "≥ 95% 标橙：全员获利，兑现压力集中"),
    ("筹码集中度 90", "chipConcentration90", "越小越集中（辅助观察，不设阈值）"),
]


def freeze_banner(scan, dc):
    """冻结横幅：本期 MACD 快照与上一期**逐字节相同** → 旧数据冒充当日，必须红框标出。

    2026-09-24/28/29/30 四期就是这样冻结的（根因：`macd_build.py` 缺原始数据时
    静默回退到内嵌的 2026-09-11 快照，却顶着新日期写文件）。已修脚本 + 加落盘前自检，
    这里负责把既有的冻结期如实标注出来。
    """
    cur = scan.get("sig") or "|".join(
        "%s:%.4f:%.4f:%.4f" % (s["code"], s["dif"], s["dea"], s["close"])
        for s in sorted(scan.get("stocks") or [], key=lambda x: x["code"]))
    if not cur:
        return ""
    prevs = [f for f in sorted(glob.glob(os.path.join(QUANT, "macd_scan_*.json")))
             if f < os.path.join(QUANT, "macd_scan_%s.json" % dc)]
    if not prevs:
        return ""
    # ★ 与链上**任意更早**一期指纹相同都要标（不只上一期）：冻结链的起点那期
    #   （2026-09-24）跟上一期本来就不一样，只比上一期会漏掉它。
    pdc = None
    for pf in reversed(prevs):
        prev = json.load(open(pf, encoding="utf-8"))
        psig = prev.get("sig") or "|".join(
            "%s:%.4f:%.4f:%.4f" % (s["code"], s["dif"], s["dea"], s["close"])
            for s in sorted(prev.get("stocks") or [], key=lambda x: x["code"]))
        if psig and psig == cur:
            pdc = re.search(r"(\d{8})", os.path.basename(pf)).group(1)
            break
    if not pdc:
        return ""
    return ("<div class='box red' style='border-color:#b00020'>"
            "<b>⚠ 本页不是当日数据：底池未重扫</b><br>"
            "本期 %s 的 MACD 快照与 %s 期 <b>整批逐字节完全相同</b>（候选集、"
            "dif / dea / close 全部一字不差）—— 说明底池没有真正重扫，"
            "这是<b>旧快照冒充当日</b>。<br>"
            "本页仅作历史归档，<b>不构成任何当日选股依据</b>；"
            "「高胜率候选池」同期页面亦已标红。根因已修（`macd_build.py` 不再静默回退内嵌快照，"
            "并加落盘前冻结自检）。</div>" % (dc, pdc))


def load_scan(date_arg=None):
    if date_arg:
        p = os.path.join(QUANT, f"macd_scan_{date_arg}.json")
        if not os.path.exists(p):
            raise SystemExit(f"未找到扫描数据：{p}")
        return p, date_arg
    files = sorted(glob.glob(os.path.join(QUANT, "macd_scan_*.json")))
    if not files:
        raise SystemExit("quant/ 下无 macd_scan_*.json，请先运行 macd_build.py。")
    p = files[-1]
    m = re.search(r"macd_scan_(\d{8})\.json$", p)
    return p, (m.group(1) if m else None)


def compact_date(s):
    return s.replace("-", "")


# ─────────────────────────────────────────────────────────────
#  跨期入选历史（与「高胜率候选池」同一口径）：
#    · MACD 观察池  → 全部 quant/macd_scan_*.json
#    · 个股信号池  → quant/picks/history.json（机构轨 / 游资轨）
#  返回 {code: [(date, pool), ...]}，按日期升序。
# ─────────────────────────────────────────────────────────────
def load_history():
    hist = {}

    def _add(code, date, pool):
        if code:
            hist.setdefault(code, []).append((date, pool))

    for p in sorted(glob.glob(os.path.join(QUANT, "macd_scan_*.json"))):
        m = re.search(r"macd_scan_(\d{8})\.json", os.path.basename(p))
        if not m:
            continue
        ds = m.group(1)
        date = "%s-%s-%s" % (ds[:4], ds[4:6], ds[6:8])
        try:
            jj = json.load(open(p, encoding="utf-8"))
        except Exception:
            continue
        for s in jj.get("stocks", []):
            _add(s.get("code"), date, "MACD观察池")

    hp = os.path.join(QUANT, "picks", "history.json")
    if os.path.exists(hp):
        try:
            entries = json.load(open(hp, encoding="utf-8")) or []
        except Exception:
            entries = []
        if isinstance(entries, dict):
            entries = entries.get("entries") or []
        for entry in entries:
            date = entry.get("date")
            if not date:
                continue
            for track, label in [("inst", "信号池·机构轨"), ("youzi", "信号池·游资轨")]:
                for x in (entry.get(track) or []):
                    _add(x.get("code"), date, label)

    for k in hist:
        hist[k].sort()
    return hist


def prior_hits(s, hist, today):
    """该标的在「今日之前」的入选记录 [(date, pool), ...]。"""
    return [(d, p) for d, p in hist.get(s.get("code"), []) if d < today]


def hist_badge(s, hist, today, is_new=False, streak=0):
    out = []
    if is_new:
        out.append("<span class='newb' title='本期首次入选（上一期不在池内）'>新</span>")
    if streak >= 2:
        out.append("<span class='streakb' title='连续 %d 期同时满足三层漏斗，趋势与资金的持续性已被反复验证'>连%d期</span>"
                   % (streak, streak))
    pr = prior_hits(s, hist, today)
    if pr:
        tip = "入选记录：" + "；".join("%s %s" % (d, p) for d, p in pr)
        out.append("<span class='hist' title='%s'>%s</span>" % (tip, pr[-1][0][5:]))
    return "".join(out)


def hist_cell(s, hist, today):
    pr = prior_hits(s, hist, today)
    if not pr:
        return "<span class='note-inline'>—</span>"
    out = []
    for d, p in pr:
        cls = "g" if "MACD" in p else "y"
        out.append("<span class='tag %s'>%s %s</span>" % (
            cls, d[5:], p.replace("观察池", "").replace("信号池·", "")))
    return " ".join(out)


def compare_prev(scan, prev):
    """与上一期 MACD 观察池对比。返回 dict 或 None。"""
    if not prev:
        return None
    pc = {s["code"]: s for s in prev.get("stocks", [])}
    cc = {s["code"]: s for s in scan.get("stocks", [])}
    return {
        "pdate": prev.get("data_date"),
        "n_prev": len(pc),
        "n_cur": len(cc),
        "new": [c for c in cc if c not in pc],
        "cont": [c for c in cc if c in pc],
        "out": [pc[c] for c in pc if c not in cc],
    }


def streak_map(cur_dc):
    """回溯全部 macd_scan_*.json，返回 {code: 截至当前期的连续在榜期数}。

    连续 = 从当前期往前，每期都在池内，直到出现缺口为止（中间断一期即中断）。
    用于区分「长期强势共振」与「偶发一日入选」——连榜越久，趋势与资金的持续性越被验证。
    """
    files = []
    for p in sorted(glob.glob(os.path.join(QUANT, "macd_scan_*.json"))):
        m = re.search(r"macd_scan_(\d{8})\.json", os.path.basename(p))
        if m and m.group(1) <= cur_dc:
            files.append((m.group(1), p))
    pools = []
    for dc, p in files:
        try:
            pools.append({s["code"] for s in json.load(open(p, encoding="utf-8")).get("stocks", [])})
        except Exception:
            pools.append(set())
    if not pools:
        return {}
    out = {}
    for code in pools[-1]:
        n = 0
        for pl in reversed(pools):
            if code in pl:
                n += 1
            else:
                break
        out[code] = n
    return out


def prev_scan(cur_dc):
    """取严格早于 cur_dc(YYYYMMDD) 的最近一期 macd_scan_*.json 内容。"""
    best = None
    for p in sorted(glob.glob(os.path.join(QUANT, "macd_scan_*.json"))):
        m = re.search(r"macd_scan_(\d{8})\.json", os.path.basename(p))
        if not m or m.group(1) >= cur_dc:
            continue
        best = p
    if not best:
        return None
    try:
        return json.load(open(best, encoding="utf-8"))
    except Exception:
        return None


SORT_JS = """<script>
(function(){
  function cellVal(tr, idx, type){
    var td = tr.cells[idx];
    if(!td) return type==='n' ? -Infinity : '';
    var raw = td.getAttribute('data-v');
    var txt = (raw!==null? raw : td.textContent).trim();
    if(type==='n'){
      var v = parseFloat(txt.replace(/[,%\\u00b7\\u4e07\\u4ebf+]/g,''));
      return isNaN(v) ? -Infinity : v;
    }
    return txt;
  }
  document.querySelectorAll('table.sortable').forEach(function(tb){
    var ths = tb.querySelectorAll('thead th[data-k]');
    ths.forEach(function(th, ci){
      th.addEventListener('click', function(){
        var tbody = tb.tBodies[0];
        if(!tbody) return;
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
"""


def diag(s):
    """返回该股的解读标签 [(level, text)]；level ∈ r/y/g。无增强数据则返回 []。"""
    e = s.get("extra")
    if not e:
        return []
    out = []
    p = e.get("pos52")
    if p is not None:
        if p >= 80:
            out.append(("r", f"位置高 {p:.0f}%"))
        elif p >= 70:
            out.append(("y", f"位置偏高 {p:.0f}%"))
    vr = e.get("vr")
    if vr is not None and vr < 1:
        out.append(("y", f"缩量金叉 ×{vr:.2f}"))
    to = e.get("turnover")
    if to is not None and to > 15:
        out.append(("y", f"换手过热 {to:.0f}%"))
    c20, c60 = e.get("chg20"), e.get("chg60")
    if c20 is not None and c60 is not None and c20 > 0 and c60 < 0:
        out.append(("r", "疑似反弹 60日仍负"))
    pr = e.get("profitRate")
    if pr is not None and pr >= 95:
        out.append(("y", f"获利盘 {pr:.0f}%"))
    mf5, mf20 = e.get("mf5Yi"), e.get("mf20Yi")
    if mf5 is not None and mf20 is not None and mf5 <= 0 < mf20:
        out.append(("r", "近5日净流出"))

    # ── 综合结论（把散标签收敛成可执行的一句话）──
    # 高位过热回避：52 周分位 ≥80 且（换手过热 或 获利盘 ≥95）→ 追高风险显著大于趋势收益
    if (p is not None and p >= 80
            and ((to is not None and to > 15) or (pr is not None and pr >= 95))):
        out.append(("r", "高位过热·回避"))
    # 资金量价共振（重点关注）：主力 5/20 日同为正 + 量比不缩 + 位置未过热
    # + 获利盘未极端 + 非「20日正/60日负」的反弹结构 → 多重验证同时成立
    if (mf5 is not None and mf20 is not None and mf5 > 0 and mf20 > 0
            and (vr is None or vr >= 1) and (p is None or p < 70)
            and (to is None or to <= 15) and (pr is None or pr < 95)
            and not (c20 is not None and c60 is not None and c20 > 0 and c60 < 0)):
        out.append(("g", "资金量价共振"))
    # 资金加速：近 5 日日均流入 > 20 日日均（mf5/5 > mf20/20 等价于 mf5*4 > mf20）
    if mf5 is not None and mf20 is not None and mf5 > 0 and mf20 > 0 and mf5 * 4 > mf20 * 1.5:
        out.append(("g", "资金加速"))
    return out


def tag_html(fl):
    if not fl:
        return "<span class='note' style='border:none;padding:0;margin:0'>—</span>"
    return "".join(f"<span class='tag {lv}'>{tx}</span>" for lv, tx in fl)


def _f(v, fmt="{:+.2f}"):
    return "—" if v is None else fmt.format(v)


def render_watchlist(scan, hist=None, prev=None):
    d = scan
    hist = hist or {}
    date = d["data_date"]
    today = date
    dc = compact_date(date)
    cmp_ = compare_prev(scan, prev)
    new_set = set(cmp_["new"]) if cmp_ else set()
    smap = streak_map(dc)
    stocks = sorted(d["stocks"], key=lambda x: x["flow20d"], reverse=True)
    n_extra = sum(1 for s in stocks if s.get("extra"))
    freeze_banner_html = freeze_banner(d, dc)

    kpis = (f"<div class='kpi'>"
            f"<div><b class='num'>{d['pool_total']}</b><span>全市场主力流入初筛（&gt;0.3亿）</span></div>"
            f"<div><b class='num'>{d['above_water']}</b><span>技术验证·水上金叉</span></div>"
            f"<div><b class='num'>{d['final_count']}</b><span>20日净流入为正·最终入选</span></div>"
            f"<div><b class='num'>{date}</b><span>数据基准（收盘）</span></div>"
            f"</div>")

    rows = []
    for s in stocks:
        chg = s["change"]
        ccls = "up" if chg >= 0 else "dn"
        fcls = "up" if s["flow20d"] >= 0 else "dn"
        dcls = "up" if s["dailyFlow"] >= 0 else "dn"
        pr = prior_hits(s, hist, today)
        hv = pr[-1][0] if pr else ""
        stk = smap.get(s["code"], 0)
        rows.append(
            f"<tr><td class='am num' data-v='{s['code']}'>{s['code']}</td>"
            f"<td>{s['name']}{hist_badge(s, hist, today, s['code'] in new_set, stk)}</td>"
            f"<td class='histcol' data-v='{hv}'>{hist_cell(s, hist, today)}</td>"
            f"<td class='num' data-v='{stk}'>{stk} 期</td>"
            f"<td class='num' data-v='{s['close']}'>{s['close']}</td>"
            f"<td class='num {ccls}' data-v='{chg}'>{chg:+.2f}%</td>"
            f"<td class='num' data-v='{s['dif']}'>{s['dif']:.3f}</td>"
            f"<td class='num' data-v='{s['dea']}'>{s['dea']:.3f}</td>"
            f"<td class='num up' data-v='{s['macd']}'>{s['macd']:.3f}</td>"
            f"<td class='num {fcls}' data-v='{s['flow20d_yi']}'>{s['flow20d_yi']:+.2f}</td>"
            f"<td class='num {dcls}' data-v='{s['dailyFlow']/1e8:+.4f}'>{s['dailyFlow']/1e8:+.2f}</td>"
            f"<td class='num' data-v='{s['circRate']}'>{s['circRate']:.2f}</td>"
            f"<td class='num am' data-v='{s['rank']}'>{s['rank']}</td></tr>"
        )
    table = "".join(rows)

    # ── 增强诊断表 ──
    erows = []
    for s in stocks:
        stk = smap.get(s["code"], 0)
        e = s.get("extra")
        if not e:
            erows.append(f"<tr><td class='am num' data-v='{s['code']}'>{s['code']}</td>"
                         f"<td>{s['name']}{hist_badge(s, hist, today, s['code'] in new_set, stk)}</td>"
                         + "<td class='num'>—</td>" * 8 + "<td class='note' style='border:none;padding:0'>无增强数据</td></tr>")
            continue
        p = e.get("pos52")
        pcls = "warn" if (p is not None and p >= 80) else ("amber-t" if (p is not None and p >= 70) else "")
        vr = e.get("vr")
        vcls = "warn" if (vr is not None and vr < 1) else ""
        to = e.get("turnover")
        tcls = "amber-t" if (to is not None and to > 15) else ""
        mf5 = e.get("mf5Yi")
        m5cls = "up" if (mf5 is not None and mf5 >= 0) else "dn"
        c60 = e.get("chg60")
        c6cls = "up" if (c60 is not None and c60 >= 0) else "dn"
        # 反弹背离：20 日正而 60 日负
        c20 = e.get("chg20")
        if c20 is not None and c60 is not None and c20 > 0 and c60 < 0:
            c6cls = "warn"
        pr_ = e.get("profitRate")
        prcls = "amber-t" if (pr_ is not None and pr_ >= 95) else ""
        n20 = e.get("norm20")
        cn = e.get("conc90")
        # data-v 排序值：None 一律转空串，避免 NaN 污染排序
        pv = "" if p is None else p
        vv = "" if vr is None else vr
        tv = "" if to is None else to
        mv = "" if mf5 is None else mf5
        cv = "" if c60 is None else c60
        prv = "" if pr_ is None else pr_
        nv = "" if n20 is None else n20
        cnv = "" if cn is None else cn
        erows.append(
            f"<tr><td class='am num' data-v='{s['code']}'>{s['code']}</td>"
            f"<td>{s['name']}{hist_badge(s, hist, today, s['code'] in new_set, stk)}</td>"
            f"<td class='num {pcls}' data-v='{pv}'>{_f(p, '{:.1f}%')}</td>"
            f"<td class='num {vcls}' data-v='{vv}'>{_f(vr, '{:.2f}')}</td>"
            f"<td class='num {tcls}' data-v='{tv}'>{_f(to, '{:.2f}')}</td>"
            f"<td class='num {m5cls}' data-v='{mv}'>{_f(mf5, '{:+.2f}')}</td>"
            f"<td class='num' data-v='{nv}'>{_f(n20, '{:.2f}%')}</td>"
            f"<td class='num {c6cls}' data-v='{cv}'>{_f(c60, '{:+.2f}%')}</td>"
            f"<td class='num {prcls}' data-v='{prv}'>{_f(pr_, '{:.1f}%')}</td>"
            f"<td class='num' data-v='{cnv}'>{_f(cn, '{:.1f}')}</td>"
            f"<td>{tag_html(diag(s))}</td></tr>"
        )
    etable = "".join(erows)

    # 警示统计
    cnt = {}
    for s in stocks:
        for lv, tx in diag(s):
            key = tx.split(" ")[0]
            cnt[key] = cnt.get(key, 0) + 1
    cnt_html = " ｜ ".join(f"{k} <b>{v}</b> 只" for k, v in sorted(cnt.items(), key=lambda x: -x[1])) or "无"

    crit_html = "".join(
        f"<div class='box' style='border-color:var(--accent);background:var(--accent-soft)'><b>{t}</b><br>{b_.format(N=d['pool_total'])}</div>"
        for t, b_ in CRITERIA)

    diag_rules_html = "".join(
        f"<tr><td>{a}</td><td>{b}</td><td>{c}</td></tr>" for a, b, c in DIAG_RULES)

    # ── 重点关注 / 回避 两个综合名单（把散标签收敛成可执行结论）──
    def _has(s_, pre):
        return any(t.startswith(pre) for _, t in diag(s_))

    focus = [s for s in stocks if _has(s, "资金量价共振")]
    avoid = [s for s in stocks if _has(s, "高位过热")]
    long_run = [s for s in focus if smap.get(s["code"], 0) >= 2]

    def _names(lst, n=14):
        return "、".join(f"{x['name']}({x['code'][2:]})" for x in lst[:n]) or "—"

    focus_html = (
        "<h2>三、重点关注 / 回避（综合结论）</h2>"
        "<div class='cmp'>"
        f"<div class='cnew'><b>{len(focus)}</b><span>资金量价共振（可重点跟踪）</span></div>"
        f"<div class='ccont'><b>{len(long_run)}</b><span>共振且连榜 ≥2 期（持续性已验证）</span></div>"
        f"<div class='cout'><b>{len(avoid)}</b><span>高位过热·建议回避</span></div>"
        "</div>"
        "<div class='card'><table><tr><th style='width:96px'>名单</th><th>标的</th><th style='width:340px'>判定口径</th></tr>"
        f"<tr><td><b>重点关注</b></td><td class='note-inline'>{_names(focus)}</td>"
        "<td>主力 5/20 日净流入同为正 + 量比 ≥1（不缩量）+ 52 周分位 &lt;70 + 换手 ≤15% + 获利盘 &lt;95%"
        " + 非「20 日正 / 60 日负」反弹结构</td></tr>"
        f"<tr><td><b>回避</b></td><td class='note-inline'>{_names(avoid)}</td>"
        "<td>52 周分位 ≥80 且（换手 &gt;15% 或 获利盘 ≥95%）—— 趋势虽在，但追高的赔率已明显劣化</td></tr>"
        "</table>"
        "<div class='note'>这两张名单是对「增强诊断列」散标签的<b>收敛</b>：单条标签只是提示，综合结论才对应操作。"
        "重点关注 ≠ 买入信号，仍须叠加退出纪律（跌破 MA20 / MACD 柱转负 / −8% 止损）。</div></div>")

    # ── 与上一期对比块 ──
    if cmp_:
        nd, nc, no = len(cmp_["new"]), len(cmp_["cont"]), len(cmp_["out"])
        orows = []
        for s in sorted(cmp_["out"], key=lambda x: (x.get("flow20d_yi") or 0), reverse=True):
            fy = s.get("flow20d_yi") or 0
            cg = s.get("change") or 0
            orows.append(
                f"<tr><td class='am num' data-v='{s['code']}'>{s['code']}</td>"
                f"<td>{s['name']}</td>"
                f"<td class='num' data-v='{fy}'>{fy:+.2f}</td>"
                f"<td class='num' data-v='{cg}'>{cg:+.2f}%</td>"
                f"<td class='num' data-v='{s.get('rank') or 0}'>{s.get('rank', '—')}</td></tr>")
        otable = "".join(orows)
        out_block = ""
        if no:
            out_block = (
                "<h3>上期已退出（" + str(no) + " 只 · " + str(cmp_["pdate"]) + " 在池、本期不再满足）</h3>"
                "<div class='card'><div class='scroll' style='max-height:44vh'><table class='sortable'>"
                "<thead><tr>"
                "<th data-k='code' data-t='s'>代码</th><th data-k='name' data-t='s'>名称</th>"
                "<th data-k='f20' data-t='n'>上期20日主力(亿)</th>"
                "<th data-k='chg' data-t='n'>上期涨跌幅</th>"
                "<th data-k='rank' data-t='n'>上期主力排名</th>"
                "</tr></thead><tbody>" + otable + "</tbody></table></div>"
                "<div class='note'>退出 = 本期不再同时满足三层漏斗（<b>MACD 水上金叉破位</b>：DIF/DEA/柱 任一转负；或 <b>20 日主力净流入转负</b>）。"
                "对持仓者而言，这是比「新进」更该优先看的名单 —— 它对应 <b>趋势或资金已经转向</b> 的标的。</div></div>")
        cmp_html = (
            "<h2>二、与上一期对比（" + str(cmp_["pdate"]) + " → " + date + "）</h2>"
            "<div class='cmp'>"
            "<div class='cnew'><b>" + str(nd) + "</b><span>本期新进（上期不在池内）</span></div>"
            "<div class='ccont'><b>" + str(nc) + "</b><span>连续在榜（两期同时入选）</span></div>"
            "<div class='cout'><b>" + str(no) + "</b><span>上期已退出（本期不再满足）</span></div>"
            "<div><b>" + str(cmp_["n_prev"]) + " → " + str(cmp_["n_cur"]) + "</b><span>入选数变化</span></div>"
            "</div>"
            "<div class='note'>名称后的 <span class='newb'>新</span> 蓝徽标 = 本期<b>首次入选</b>；"
            "<span class='hist'>09-11</span> 绿徽标 = 该标的<b>此前（不含今日）</b>曾入选，悬停可看全部记录；"
            "对应「历史入选」列（可排序）列出全部日期与池别（MACD 观察池 / 信号池双轨）。</div>"
            + out_block)
    else:
        cmp_html = ("<h2>二、与上一期对比</h2><div class='card'><div class='note'>"
                    "当前仅有单期 macd_scan 数据，无上一期可比；明日起本板块会自动输出「新进 / 连续 / 退出」三类名单。</div></div>")

    html = f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>MACD 水上金叉 + 20日主力净流入 · {date}</title><style>{CSS}</style></head>
<body><div class="wrap">
<h1>MACD 水上金叉 + 20 日主力净流入 · 候选池</h1>
<div class="sub">数据基准：{date} 收盘｜ 方法：主力流入初筛 → 水上金叉 → 20 日净流入为正 ｜ 全市场 {d['pool_total']} → 最终 {d['final_count']} 只</div>
{MERGE_NOTE}
{freeze_banner_html}

<div class="box gold"><b>一句话：</b>本批经三层漏斗，全市场约 {d['pool_total']} 只主力流入股中，仅 <b>{d['final_count']} 只</b>同时满足
<b>MACD 零轴上方金叉</b> 与 <b>20 日主力净流入为正</b>。这两个条件同时成立，意味着「趋势已转多 + 资金持续进场」，是相对稀缺的强势共振组合。</div>

{kpis}

<h2>一、筛选口径（三层漏斗）</h2>
{crit_html}

{cmp_html}

{focus_html}

<h2>四、候选总表（{d['final_count']} 只 · 默认按 20 日主力净流入排序 · <span style="color:var(--accent)">点击任意列头切换排序</span>）</h2>
<div class="card"><div class="scroll"><table class="sortable">
<thead><tr><th data-k="code" data-t="s">代码</th><th data-k="name" data-t="s">名称</th><th data-k="hist" data-t="s">历史入选</th><th data-k="streak" data-t="n">连榜</th><th data-k="close" data-t="n">现价</th><th data-k="chg" data-t="n">涨跌幅</th><th data-k="dif" data-t="n">DIF</th><th data-k="dea" data-t="n">DEA</th><th data-k="macd" data-t="n">MACD柱</th><th data-k="f20" data-t="n">20日主力(亿)</th><th data-k="fd" data-t="n">当日主力(亿)</th><th data-k="circ" data-t="n">流通占比%</th><th data-k="rank" data-t="n">主力排名</th></tr></thead>
<tbody>{table}</tbody></table></div>
<div class="note">读法：DIF/DEA/MACD柱 均为正 = 水上金叉；20日主力(亿) 与 当日主力(亿) 为正 = 资金净流入；流通占比% 越高说明主力介入越深；主力排名 = 全市场 20 日主力净流入名次（越小越强）。<b>涨跌幅以 data_quote 收盘口径为准</b>（初筛接口为盘中口径，已统一）。<br>
<b>排序：</b>所有列均可点击表头排序（数值列按真实数值比较，不受 %、单位、文本干扰）；<b>历史入选</b>列按最近一次入选日期排序。</div></div>

<h2>五、增强诊断列（{n_extra} 只，记录项 · 不参与筛选）</h2>
<div class="box amber"><b>为什么是「记录」而不是「筛选条件」：</b>目前仅有 1 期样本（{d['final_count']} 只），若直接把阈值变成硬条件，等于用一次观测去拟合规则（过拟合）。
因此本批先把这些字段<b>如实记录并标红</b>，累积 20~30 个交易日后回测各阈值的分组表现，再决定哪几条升级为硬条件。
本表顺序与总表一致，便于对照。<b>本表同样支持点击表头排序。</b></div>
<div class="card"><div class="scroll"><table class="sortable">
<thead><tr><th data-k="code" data-t="s">代码</th><th data-k="name" data-t="s">名称</th><th data-k="pos52" data-t="n">52周分位</th><th data-k="vr" data-t="n">量比</th><th data-k="turn" data-t="n">换手%</th><th data-k="mf5" data-t="n">5日主力(亿)</th><th data-k="norm" data-t="n">20日÷流通市值%</th><th data-k="chg60" data-t="n">60日涨幅</th><th data-k="profit" data-t="n">获利盘%</th><th data-k="conc" data-t="n">集中度90</th><th data-k="tag" data-t="s">解读</th></tr></thead>
<tbody>{etable}</tbody></table></div>
<div class="note"><b>阈值口径：</b>粗体/彩色为越界警示 —— <span class="warn">红</span>=高风险特征（高位追涨 / 缩量金叉 / 60日背离 / 近5日净流出），<span class="amber-t">橙</span>=需留意（位置偏高 / 换手过热 / 获利盘过高）。<br>
<b>本批警示分布：</b>{cnt_html}。</div>
<div class="note">字段来源：{EXTRA_SOURCE}。归一化强度 = 20 日主力净额 ÷ 流通市值 × 100，用于横向可比（绝对净额会被大盘股系统性放大）。</div></div>

<h2>六、诊断列判定规则</h2>
<div class="card"><table>
<tr><th>字段</th><th>定义 / 来源字段</th><th>警示触发条件</th></tr>
{diag_rules_html}
</table>
<div class="note">深入读法与常见误读见 <a href="method.html" style="color:var(--accent);text-decoration:none;font-weight:600">方法论页</a>。</div></div>

<h2>七、关键概念说明</h2>
<div class="card">
<b>① 什么是 MACD 水上金叉？</b><br>
MACD 由 DIF（快线）、DEA（慢线）、MACD 柱（红绿柱）组成。当 DIF 与 DEA 都位于 <b>零轴（0）上方</b> 且 DIF 上穿 DEA（金叉），称为「水上金叉」。它代表股价已站上中期成本、多头趋势确立后的回踩再进攻，成功率远高于零轴下方的「水下金叉」（后者多是下跌途中的技术反弹）。<br><br>
<b>② 20 日主力净流入怎么看？</b><br>
主力净流入 = 大单/机构主动买入额 − 主动卖出额。<b>注意它是「净额」不是「净值」，是流量不是存量</b>；口径为按单笔委托金额分档的大单净额，机构拆单会低估、对倒会高估，且累计值会掩盖时序（20 日为正可能是「前 15 日灌、近 5 日撤」）。因此它只能作<b>弱辅助信号</b>：转负可提示警惕，为正不能确认趋势 —— 这正是「5 日主力」列存在的意义。<br><br>
<b>③ 两个条件为何要叠加？</b><br>
单看水上金叉，可能已涨高、追涨风险大；单看主力流入，可能是短线游资一日游。两者共振 = 趋势与资金同向，才构成可跟踪的强势候选。<br><br>
<b>④ 为什么加「位置」和「量能」？</b><br>
水上金叉本质是趋势中继，但若发生在 52 周分位 80% 以上的极端位置，回撤风险显著抬升；若金叉当天量比不足 1（缩量），突破缺乏成交确认、更易假突破。这两条与「60 日涨幅仍为负」（疑似反弹）共同构成三道最常见的伪强势过滤网。
</div>

<h2>八、风险提示</h2>
<div class="box red"><ul style="margin:8px 0 0;padding-left:20px;font-size:13.5px">
<li>本页为<b>量化筛选结果</b>，非个股推荐、非买卖建议。入选仅代表同时满足筛选条件，不等于一定上涨。</li>
<li><b>入选 ≠ 可买入</b>：增强列的告警若集中出现（如高位 + 缩量 + 60 日背离同时命中），应视为风险叠加，而非利好。</li>
<li>退出规则比入场筛选更决定最终盈亏：建议跌破 MA20 或 MACD 死叉离场、单笔止损 −8%、盈利分批止盈。</li>
<li>强势股波动大，介入须自设止损与仓位上限（本账户纪律：单票 ≤ 总资金 5%–8%，整体回撤 ≤ 15%）。</li>
<li>数据每日变化，须按上述口径动态重扫复核。决策责任在账户本人。</li>
</ul></div>

<div class="foot">数据基准 {date} 收盘；页面生成 {d.get('generated', datetime.date.today().isoformat())}。本候选池为量化筛选，非投资建议。</div>
</div>{SORT_JS}</body></html>"""
    return html, f"watchlist_{dc}.html"


def render_index(scan, archive, hist=None, prev=None):
    d = scan
    hist = hist or {}
    date = d["data_date"]
    today = date
    dc = compact_date(date)
    cmp_ = compare_prev(scan, prev)
    new_set = set(cmp_["new"]) if cmp_ else set()
    smap = streak_map(dc)
    stocks = sorted(d["stocks"], key=lambda x: x["flow20d"], reverse=True)

    rows = []
    for s in stocks:
        chg = s["change"]
        ccls = "up" if chg >= 0 else "dn"
        fcls = "up" if s["flow20d"] >= 0 else "dn"
        e = s.get("extra")
        if e:
            p = e.get("pos52")
            pcls = "warn" if (p is not None and p >= 80) else ("amber-t" if (p is not None and p >= 70) else "")
            pv = "" if p is None else p
            pos_td = f"<td class='num {pcls}' data-v='{pv}'>{_f(p, '{:.0f}%')}</td>"
            vr = e.get("vr")
            vrcls = "warn" if (vr is not None and vr < 1) else ""
            vv = "" if vr is None else vr
            vr_td = f"<td class='num {vrcls}' data-v='{vv}'>{_f(vr, '{:.2f}')}</td>"
        else:
            pos_td = "<td class='num'>—</td>"
            vr_td = "<td class='num'>—</td>"
        pr = prior_hits(s, hist, today)
        hv = pr[-1][0] if pr else ""
        stk = smap.get(s["code"], 0)
        rows.append(
            f"<tr><td class='am num' data-v='{s['code']}'>{s['code']}</td>"
            f"<td>{s['name']}{hist_badge(s, hist, today, s['code'] in new_set, stk)}</td>"
            f"<td class='histcol' data-v='{hv}'>{hist_cell(s, hist, today)}</td>"
            f"<td class='num' data-v='{stk}'>{stk} 期</td>"
            f"<td class='num' data-v='{s['close']}'>{s['close']}</td>"
            f"<td class='num {ccls}' data-v='{chg}'>{chg:+.2f}%</td>"
            f"<td class='num up' data-v='{s['macd']}'>{s['macd']:.3f}</td>"
            f"<td class='num {fcls}' data-v='{s['flow20d_yi']}'>{s['flow20d_yi']:+.2f}</td>"
            f"{pos_td}{vr_td}"
            f"<td>{tag_html(diag(s))}</td></tr>"
        )
    ab_table = "".join(rows)

    if cmp_:
        cmp_line = (
            "<div class='cmp'>"
            "<div class='cnew'><b>" + str(len(cmp_["new"])) + "</b><span>本期新进</span></div>"
            "<div class='ccont'><b>" + str(len(cmp_["cont"])) + "</b><span>连续在榜</span></div>"
            "<div class='cout'><b>" + str(len(cmp_["out"])) + "</b><span>上期已退出</span></div>"
            "<div><b>" + str(cmp_["n_prev"]) + " → " + str(cmp_["n_cur"]) + "</b><span>" + str(cmp_["pdate"]) + " → " + date + "</span></div>"
            "</div>")
    else:
        cmp_line = ""

    crit_html = "".join(
        f"<div class='box'><b>{t}</b><br>{b_.format(N=d['pool_total'])}</div>" for t, b_ in CRITERIA)

    arch_html = "\n".join(
        f"<div class='arch'>· <a href='{fn}'>{dt} 候选池</a></div>"
        for dt, fn in archive)

    html = f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>MACD 水上金叉 + 20日主力净流入 · 板块</title><style>{CSS}</style></head>
<body><div class="wrap">
<h1>MACD 水上金叉 + 20 日主力净流入</h1>
<div class="sub">数据基准：{date} 收盘｜ 每日随数据更新重扫 ｜ 强势共振：趋势转多 × 资金进场 ｜ 增强诊断列：仅记录不筛选</div>
{MERGE_NOTE}

<div class="box gold"><b>核心：</b>真强势 = <b>技术面（MACD 零轴上方金叉）</b> × <b>资金面（20 日主力净流入为正）</b> 两者共振。
当前市场同时满足仅 <b>{d['final_count']} 只</b>。本板块每日自动重扫，长期跟踪强势候选。<br>
<b>本批增强：</b>新增「52 周分位 / 量比 / 换手 / 5日主力 / 归一化强度 / 60日涨幅 / 获利盘 / 集中度」诊断列并自动标红警示（<b>记录项，未参与筛选</b>）。</div>

<h2>方法论（三层漏斗）</h2>
<div class="card">{crit_html}
<div class="note"><a href="method.html" style="color:var(--accent);text-decoration:none;font-weight:600">→ 完整方法论（概念详解 / 增强列读法 / 常见误区 / 介入纪律）</a></div>
</div>

<h2>与上一期对比</h2>
<div class="card">{cmp_line or "<div class='note'>当前仅有单期数据，明日起自动输出「新进 / 连续 / 退出」三类名单。</div>"}</div>

<h2>最新候选（{date} · 默认按 20 日主力净流入排序 · <span style="color:var(--accent)">点击列头切换排序</span>）</h2>
<div class="card"><div class="scroll"><table class="sortable">
<thead><tr><th data-k="code" data-t="s">代码</th><th data-k="name" data-t="s">名称</th><th data-k="hist" data-t="s">历史入选</th><th data-k="streak" data-t="n">连榜</th><th data-k="close" data-t="n">现价</th><th data-k="chg" data-t="n">涨跌幅</th><th data-k="macd" data-t="n">MACD柱</th><th data-k="f20" data-t="n">20日主力(亿)</th><th data-k="pos52" data-t="n">52周分位</th><th data-k="vr" data-t="n">量比</th><th data-k="tag" data-t="s">解读</th></tr></thead>
<tbody>{ab_table}</tbody></table></div>
<div class="note"><a href="watchlist_{dc}.html" style="color:var(--accent);text-decoration:none;font-weight:600">→ 查看完整 {date} 候选池（{d['final_count']} 只 / 三层漏斗口径 / 增强诊断列 / 概念说明 / 风险提示）</a></div>
</div>

<h2>历史候选归档</h2>
<div class="card">{arch_html or '<div class="note">暂无历史归档。</div>'}</div>

<div class="foot">本版块为基于 westock 实拉数据的量化筛选，非个股推荐、非买卖建议。决策责任在账户本人。</div>
</div>{SORT_JS}</body></html>"""
    return html


def render_method(scan=None):
    """MACD 水上金叉方法论常驻页（概念详解 / 增强列读法 / 常见误区 / 介入纪律）。"""
    pool_total = (scan or {}).get("pool_total", "2000")
    diag_rules_html = "".join(
        f"<tr><td>{a}</td><td>{b}</td><td>{c}</td></tr>" for a, b, c in DIAG_RULES)
    html = f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>MACD 水上金叉 + 20日主力净流入 · 方法论</title><style>{CSS}</style></head>
<body><div class="wrap">
<h1>MACD 水上金叉 + 20 日主力净流入 · 方法论</h1>
<div class="sub">常驻 Playbook：筛选口径 / 概念详解 / 增强列读法 / 常见误区 / 介入纪律（每日随数据重扫，方法不变）</div>
{MERGE_NOTE}

<div class="box gold"><b>核心结论：</b>真强势 = <b>技术面（MACD 零轴上方金叉）</b> × <b>资金面（20 日主力净流入为正）</b> 两者共振。本页只讲方法，不荐个股。</div>

<h2>一、筛选口径（三层漏斗）</h2>
<div class="card">{''.join(f"<div class='box' style='border-color:var(--accent);background:var(--accent-soft)'><b>{t}</b><br>{b_.format(N=pool_total)}</div>" for t, b_ in CRITERIA)}</div>

<h2>二、关键概念详解</h2>
<div class="card">
<b>① 什么是 MACD 水上金叉？</b><br>
MACD 由 DIF（快线）、DEA（慢线）、MACD 柱（红绿柱）组成。当 DIF 与 DEA 都位于 <b>零轴（0）上方</b> 且 DIF 上穿 DEA（金叉），称为「水上金叉」。它代表股价已站上中期成本、多头趋势确立后的回踩再进攻，成功率远高于零轴下方的「水下金叉」（后者多是下跌途中的技术反弹）。<br><br>
<b>② 20 日主力净流入：是「净额」不是「净值」</b><br>
主力净流入 = 大单/机构主动买入额 − 主动卖出额，是<b>流量</b>而非存量。它有三层先天噪声：<br>
&nbsp;&nbsp;1) <b>口径噪声</b>：「主力」按单笔委托金额分档推断，机构用冰山单/VWAP 拆成中小单会被低估，游资用大单对倒会被高估；<br>
&nbsp;&nbsp;2) <b>被动资金</b>：大宗交易、ETF 申赎、指数调仓带来的流入与「看好」无关；一字板无成交时净额严重失真；<br>
&nbsp;&nbsp;3) <b>累计掩盖时序</b>：20 日为正可能是「前 15 日猛灌 + 近 5 日连续撤」，趋势其实已在转弱。<br>
&nbsp;&nbsp;→ 因此它只能作<b>弱辅助信号（不否决级）</b>：<b>转负可以提示警惕，为正不能确认趋势</b>。既是趋势向好的非充分条件（高位对倒诱多即是反例），也是非必要条件（缩量筑底期净额≈0 但趋势转好）。<br><br>
<b>③ 两个条件为何要叠加？</b><br>
单看水上金叉，可能已涨高、追涨风险大；单看主力流入，可能是短线游资一日游。两者共振 = 趋势与资金同向，才构成可跟踪的强势候选。
</div>

<h2>三、增强诊断列怎么读（去伪存真）</h2>
<div class="card"><table>
<tr><th>字段</th><th>定义 / 来源字段</th><th>警示触发条件</th></tr>
{diag_rules_html}
</table>
<h3>三道最有效的伪强势过滤网</h3>
<ul>
<li><b>位置过滤</b>：52 周分位 &gt; 80% 时，水上金叉多为「趋势末端的中继」，与本账户 ≤15% 最大回撤的风险预算直接冲突。低位净流入（建仓）远比高位净流入可信。</li>
<li><b>量能过滤</b>：量比 &lt; 1 的「缩量金叉」缺乏成交确认，假突破概率显著更高；反之放量突破且换手适中（约 2%–15%）质量更好。</li>
<li><b>时序过滤</b>：5 日净额与 20 日净额必须同号且同为正。20 日为正而 5 日转负 = 资金减速/疑似派发；20 日为正而 60 日涨幅仍为负 = 疑似反弹而非趋势。</li>
</ul>
<h3>为什么这些列「只记录、不筛选」</h3>
<div class="box amber"><b>避免过拟合。</b>样本仅有单期（约 35 只）。若立刻把这些阈值写成硬条件，本质是用一次观测拟合规则，无法验证其真实增益。
正确顺序是：<b>先如实记录 → 累积 20~30 个交易日 → 回测各阈值的分组胜率 → 再把验证有效的升级为硬条件</b>。这是唯一能稳定修正胜率的路径，而非堆指标。</div>
<h3>比加指标更重要的一件事</h3>
<div class="box red"><ul style="margin:8px 0 0;padding-left:20px;font-size:13px">
<li><b>退出纪律 &gt; 入场筛选。</b>入场筛选决定「看不看」，退出规则决定「赚不赚」。再好的筛选也无法替代止损。</li>
<li>建议规则：跌破 MA20 或 MACD 死叉离场；单笔止损 −8%；盈利分批止盈，不追求卖在最高点。</li>
</ul></div>
</div>

<h2>四、跨期对比怎么用（新进 / 连续 / 退出）</h2>
<div class="card">
候选池每天重扫，<b>逐期名单的差异比单期名单更有信息量</b>。候选池页「与上一期对比」给出三个名单，对应三种完全不同的读法：
<table>
<tr><th>名单</th><th>含义</th><th>怎么用</th></tr>
<tr><td><b>新进</b>（蓝徽标「新」）</td><td>本期首次同时满足三层漏斗（上期不在池内）</td><td>信号最"新"，但需辨别是「趋势刚启动」还是「破位后反抽重新满足」——查增强列的 52 周分位与 60 日涨幅，高位 + 60 日为负 = 伪新进。</td></tr>
<tr><td><b>连续在榜</b>（绿徽标 + 历史入选列）</td><td>两期同时入选，趋势与资金连续同向</td><td>信号稳定性最好的正面证据，但<b>不等于可以放松止损</b>；连榜期数越多、位置越高的标的，反而越要警惕趋势末端。</td></tr>
<tr><td><b>上期已退出</b></td><td>上期在池、本期不再同时满足漏斗</td><td><b>对持仓者而言这是最该优先看的名单</b>：退出意味着 MACD 水上金叉破位（DIF/DEA/柱任一转负）或 20 日主力净流入转负，对应退出纪律中的「跌破 MA20 / MACD 死叉离场」。</td></tr>
</table>
<div class="box red"><b>纪律：</b>退出名单的优先级高于新进名单。不要因为一只票「连榜多期」就把它当作低风险，也不要因为「新进」就急于介入——先看它为什么新进、位置在哪。<br>
<b>徽标读法：</b>名称后 <span class="newb">新</span> = 本期首次入选；<span class="hist">09-11</span> = 此前（不含今日）曾入选，鼠标悬停显示<b>全部</b>入选日期与池别（MACD 观察池 / 信号池·机构轨 / 信号池·游资轨）；「历史入选」列列出同一信息并支持排序。</div>
</div>

<h2>五、常见误区</h2>
<div class="card">
<table>
<tr><th>误区</th><th>真相</th></tr>
<tr><td>金叉 = 必涨</td><td>零轴下方金叉多是下跌中继反弹；只有在零轴上方、且量能与大盘配合才有效。</td></tr>
<tr><td>主力净流入为正 = 机构看好</td><td>它是按单笔金额分档的大单净额，可被拆单低估、被对倒高估；且累计值掩盖时序。只能作弱辅助。</td></tr>
<tr><td>净额越大越强</td><td>绝对净额不可横向比较：20 亿对 300 亿流通盘是 6.7%，对 3000 亿盘只有 0.67%。须看归一化强度。</td></tr>
<tr><td>入选 = 可买入</td><td>入选仅代表满足筛选条件，不等于一定上涨；增强列告警集中出现时应视为风险叠加。</td></tr>
<tr><td>信号越多越准</td><td>本筛选刻意「稀缺化」（全市场约 1500–2000 只初筛 → 最终约 30–55 只），追求共振质量而非数量。</td></tr>
</table>
</div>

<h2>六、介入纪律（账户级）</h2>
<div class="box red"><ul style="margin:8px 0 0;padding-left:20px;font-size:13.5px">
<li>本页为<b>量化筛选结果</b>，非个股推荐、非买卖建议；决策责任在账户本人。</li>
<li>水上金叉后若量能不济或大盘转弱，仍可能假突破；须结合板块与大盘情绪综合判断。</li>
<li>强势股波动大，介入须自设止损与仓位上限（本账户纪律：单票 ≤ 总资金 5%–8%，整体回撤 ≤ 15%）。</li>
<li>数据每日变化，须按上述口径动态重扫复核，不刻舟求剑。</li>
</ul></div>

<div class="foot">方法常驻页；候选池每日重扫见 <a href="index.html" style="color:var(--accent);text-decoration:none;font-weight:600">板块入口</a>。本方法为量化筛选，非投资建议。</div>
</div></body></html>"""
    return html


def scan_archive():
    out = []
    for fn in os.listdir(OUTDIR):
        m = re.match(r"^watchlist_(\d{8})\.html$", fn)
        if not m:
            continue
        s = m.group(1)
        try:
            dt = datetime.datetime.strptime(s, "%Y%m%d").strftime("%Y-%m-%d")
        except Exception:
            dt = s
        out.append((dt, fn))
    out.sort(reverse=True)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("date", nargs="?", default=None, help="数据日期 compact YYYYMMDD")
    a = ap.parse_args()
    path, dc = load_scan(a.date)
    scan = json.load(open(path, encoding="utf-8"))
    hist = load_history()
    prev = prev_scan(dc)
    cmp_ = compare_prev(scan, prev)
    if cmp_:
        print("[对比] %s → %s ｜ 新进 %d ｜ 连续 %d ｜ 退出 %d"
              % (cmp_["pdate"], scan["data_date"], len(cmp_["new"]), len(cmp_["cont"]), len(cmp_["out"])))
    else:
        print("[对比] 无上一期 macd_scan，跳过对比板块")
    print("[历史] 跨期入选库覆盖 %d 个代码（MACD观察池 + 信号池双轨）" % len(hist))

    wl_html, wl_fn = render_watchlist(scan, hist, prev)
    open(os.path.join(OUTDIR, wl_fn), "w", encoding="utf-8").write(wl_html)
    print("生成", os.path.join("web/macd", wl_fn))

    arch = scan_archive()
    idx_html = render_index(scan, arch, hist, prev)
    open(os.path.join(OUTDIR, "index.html"), "w", encoding="utf-8").write(idx_html)
    print("生成 web/macd/index.html（最新数据日期", scan["data_date"], "）")

    method_html = render_method(scan)
    open(os.path.join(OUTDIR, "method.html"), "w", encoding="utf-8").write(method_html)
    print("生成 web/macd/method.html（方法论常驻页）")

    n = sum(1 for s in scan["stocks"] if s.get("extra"))
    print(f"增强诊断列覆盖 {n}/{len(scan['stocks'])} 只")
    print("完成。记得跑：python quant/_apply_theme.py 注入导航与主题，再 _link_check.py 校验。")


if __name__ == "__main__":
    main()
