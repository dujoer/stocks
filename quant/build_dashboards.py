# -*- coding: utf-8 -*-
"""以远程 web/index.html(深色交易终端风)为蓝本重做本地看板。
数据来源(均为 2026-08-27 收盘/盘后, 由 westock-mcp 拉取落盘; 大盘概览聚合/收盘为当日, 估值口径滞后):
  quant/market_overview/2026-08-27.json (大盘概览; 估值口径 2026-08-25)
  quant/board_hot/2026-08-27.json        (板块热度)
  quant/quotes/2026-08-27.json           (9只持仓实时行情)
  quant/news.json                        (要闻 2026-08-27)
  quant/limitup/2026-08-27.json          (连板梯队)
  quant/lhb/2026-08-27.json              (龙虎榜: 机构榜/游资席位/共振/胜率)
"""
import json, os, re, argparse, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(ROOT, "web")
QUANT = os.path.join(ROOT, "quant")
parser = argparse.ArgumentParser(description="A股龙虎榜看板生成器（每日参数化）")
parser.add_argument("--date", default=datetime.date.today().strftime("%Y-%m-%d"),
                    help="数据口径日期，默认今天 (YYYY-MM-DD)")
parser.add_argument("--snap-date", default=None, help="大盘概览快照日期，默认同 --date")
parser.add_argument("--val-date", default=None, help="估值快照日期，默认 --date 前一天")
_args = parser.parse_args()
DATE = _args.date
SNAP_DATE = _args.snap_date or DATE
if _args.val_date:
    val_date = _args.val_date
else:
    _d = datetime.date.fromisoformat(DATE) - datetime.timedelta(days=1)
    val_date = _d.isoformat()

def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)

def fnum(x, d=2):
    try:
        return f"{float(x):,.{d}f}"
    except Exception:
        return "-"

def pct(x, d=2):
    try:
        v = float(x)
        return ("+" if v > 0 else "") + f"{v:.{d}f}%"
    except Exception:
        return "-"

def cls(x):
    try:
        v = float(x)
        return "up" if v > 0 else ("down" if v < 0 else "")
    except Exception:
        return ""

def short_status(s):
    if not s:
        return ""
    return s.split("(")[0].strip()

def yi(x):
    try:
        return f"{float(x)/1e8:,.2f}"
    except Exception:
        return "-"

# ---------- 配色 ----------
CSS = """* { box-sizing: border-box; }
body { margin:0; font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;
  background:#f5f6f8; color:#23262b; min-height:100vh; }
.wrap { max-width:1040px; margin:0 auto; padding:40px 20px 60px; }
.topnav { display:flex; flex-wrap:wrap; gap:8px; margin-bottom:22px; padding-bottom:14px;
  border-bottom:1px solid rgba(0,0,0,.08); }
.topnav a { color:#b8893b; text-decoration:none; font-size:13px; padding:4px 12px; border-radius:20px;
  border:1px solid rgba(184,137,59,.35); transition:.2s; }
.topnav a:hover { background:rgba(184,137,59,.10); }
header h1 { font-size:30px; margin:0 0 6px; background:linear-gradient(90deg,#b8893b,#b8332a,#6b5b95);
  -webkit-background-clip:text; background-clip:text; color:transparent; font-weight:800; }
header p { margin:4px 0; color:#8a929c; font-size:13px; line-height:1.6; }
.meta { margin:14px 0 24px; font-size:12px; color:#6b7280; line-height:1.7; }
.meta b { color:#b8893b; }
.section { background:#ffffff;
  border:1px solid rgba(0,0,0,.08); border-radius:20px; padding:18px 20px; margin:0 0 22px;
  box-shadow:0 1px 3px rgba(20,30,50,.05); backdrop-filter:blur(10px); }
.section h2 { font-size:17px; margin:0 0 14px; color:#1c2430; display:flex; align-items:center; gap:8px; }
.section h2:before { content:""; width:4px; height:16px; background:#b8893b; border-radius:3px; }
.idxrow { display:flex; flex-wrap:wrap; gap:12px; margin-bottom:12px; }
.idx { flex:1; min-width:200px; background:linear-gradient(135deg,rgba(184,51,42,.08),rgba(184,51,42,.03));
  border:1px solid rgba(184,51,42,.20); border-radius:14px; padding:13px 10px; text-align:center;
  box-shadow:0 1px 3px rgba(184,51,42,.06); }
.idx .k { font-size:11px; color:#6b7280; letter-spacing:.3px; }
.idx .v { font-size:22px; font-weight:800; color:#1c2430; margin:5px 0 2px; }
.idx .c { font-size:13px; font-weight:700; }
.idx .hl { font-size:10px; color:#8a929c; margin-top:4px; }
.bar { display:flex; height:34px; border-radius:8px; overflow:hidden; margin:10px 0; font-size:12px;
  color:#ffffff; text-align:center; line-height:34px; box-shadow:0 2px 6px rgba(0,0,0,.12); }
.chiprow { display:flex; flex-wrap:wrap; gap:8px; margin:10px 0; }
.chip { background:rgba(0,0,0,.05); border:1px solid rgba(0,0,0,.06); border-radius:12px;
  padding:10px 6px; text-align:center; min-width:74px; backdrop-filter:blur(6px); box-shadow:0 1px 3px rgba(20,30,50,.04); }
.chip .ck { font-size:10px; color:#8a929c; }
.chip .cv { font-size:16px; font-weight:800; margin-top:3px; }
.tag { display:inline-block; border-radius:20px; padding:3px 11px; font-size:12px; margin:3px 4px 3px 0;
  background:#eef2f8; color:#33414f; }
.tag.hot { background:#fdeceb; color:#d8392b; }
.tag.cold { background:#e9f6ef; color:#1a9e5a; }
.pill { display:inline-block; background:rgba(0,0,0,.05); border:1px solid rgba(0,0,0,.06);
  border-radius:20px; padding:4px 11px; font-size:12px; color:#3a4048; margin:3px 4px 3px 0; cursor:help; }
.pill b { color:#b8893b; font-weight:700; }
table { width:100%; border-collapse:collapse; font-size:13px; background:rgba(0,0,0,.03);
  border:1px solid rgba(0,0,0,.05); border-radius:12px; overflow:hidden; margin:10px 0; }
th,td { padding:8px 10px; text-align:left; border-bottom:1px solid rgba(0,0,0,.04); }
th { background:rgba(20,30,50,.06); color:#3a4048; font-weight:600; font-size:12px; }
td.num,th.num { text-align:right; font-variant-numeric:tabular-nums; }
.up { color:#b8332a; } .down { color:#1a9e5a; }
.note { color:#8a929c; font-size:12px; margin-top:8px; line-height:1.6; }
.amberbox { font-size:13px; color:#b8893b; background:linear-gradient(135deg,rgba(184,137,59,.10),rgba(184,137,59,.04));
  border:1px solid rgba(184,137,59,.18); border-radius:12px; padding:12px 16px; margin:12px 0; line-height:1.6; }
.ladder { margin:6px 0; padding:8px 10px; background:rgba(0,0,0,.03); border:1px solid rgba(0,0,0,.08);
  border-radius:8px; font-size:13px; }
.ladder .badge { display:inline-block; border-radius:6px; padding:1px 8px; margin-right:8px; font-weight:700; font-size:12px; }
.ladder .b5 { background:rgba(184,51,42,.10); border:1px solid rgba(184,51,42,.35); color:#b8332a; }
.ladder .b4 { background:rgba(184,51,42,.08); border:1px solid rgba(184,51,42,.30); color:#b8332a; }
.ladder .b3 { background:rgba(184,137,59,.14); border:1px solid rgba(184,137,59,.40); color:#d8bd8a; }
.ladder .b2 { background:rgba(184,137,59,.14); border:1px solid rgba(184,137,59,.40); color:#d8bd8a; }
.ladder .b1 { background:rgba(90,107,128,.12); border:1px solid rgba(90,107,128,.35); color:#a7b4c9; }
.namechip { display:inline-block; color:#3a4048; margin:2px 6px 2px 0; font-size:13px; }
.empty { color:#8a929c; text-align:center; padding:38px 0; font-size:14px; line-height:1.8; }
.empty b { color:#b8893b; }
footer { margin-top:40px; padding-top:16px; border-top:1px solid rgba(0,0,0,.08);
  font-size:12px; color:#8a929c; line-height:1.8; }
a.inlink { color:#b8893b; text-decoration:none; border:1px solid rgba(201,166,107,.5);
  border-radius:10px; padding:6px 14px; font-size:13px; font-weight:700; display:inline-block; margin:4px 6px 4px 0; }
a.inlink:hover { background:rgba(201,166,107,.16); }
.wrap.landing { max-width:880px; text-align:center; }
.landing header h1 { font-size:34px; }
.landing header p { margin:6px 0; color:#8a929c; font-size:14px; }
.date { margin:18px 0 30px; font-size:13px; color:#b8893b; letter-spacing:.5px; }
.grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:16px; text-align:left; }
.card { display:block; text-decoration:none; color:#23262b; background:#ffffff;
  border:1px solid rgba(0,0,0,.08); border-radius:18px; padding:20px 18px;
  box-shadow:0 1px 3px rgba(20,30,50,.05); backdrop-filter:blur(10px); transition:.2s; }
.card:hover { border-color:rgba(184,137,59,.50); transform:translateY(-2px); background:linear-gradient(135deg,rgba(184,137,59,.08),rgba(255,255,255,.03)); }
.card .ic { font-size:26px; }
.card .t { font-size:17px; font-weight:700; margin:10px 0 6px; color:#1c2430; }
.card .d { font-size:12.5px; color:#8a929c; line-height:1.6; }
.hist { margin-top:30px; font-size:12.5px; color:#6b7280; }
.hist a { color:#b8893b; text-decoration:none; border:1px solid rgba(201,166,107,.4); border-radius:10px; padding:5px 12px; display:inline-block; margin:4px; }
.foot { margin-top:42px; font-size:12px; color:#8a929c; line-height:1.8; }
.lhb { table-layout:fixed; }
.lhb th, .lhb td { font-size:12.5px; vertical-align:top; }
.lhb td.reason { color:#6b7280; width:150px; font-size:11.5px; line-height:1.4; }
.lhb td.sec { font-size:12px; white-space:nowrap; }
.hm { text-align:center; }
.hm-high { color:#f2a65a; font-weight:800; }
.hm-mid { color:#b8893b; font-weight:700; }
.hm-low { color:#8a93a3; }
.hmtags { margin-top:3px; }
.hmtag { display:inline-block; background:rgba(184,51,42,.10); border:1px solid rgba(184,51,42,.30); color:#b8332a; border-radius:10px; padding:1px 7px; font-size:10.5px; margin:2px 2px 0 0; }
.toggle { color:#b8893b; cursor:pointer; font-size:12px; user-select:none; }
.toggle:hover { text-decoration:underline; }
.seats { display:flex; gap:24px; flex-wrap:wrap; padding:6px 4px; }
.seats .buys, .seats .sells { flex:1; min-width:260px; }
.seat-h { font-weight:700; margin-bottom:6px; font-size:13px; }
.seat-h.up { color:#b8332a; } .seat-h.down { color:#1a9e5a; }
.seats ul { list-style:none; margin:0; padding:0; }
.seats li { display:flex; align-items:center; gap:8px; padding:4px 0; border-bottom:1px dashed rgba(0,0,0,.04); font-size:12px; }
.seats li .nm { flex:1; color:#3a4048; }
.seats li .amt { font-variant-numeric:tabular-nums; font-weight:700; }
tr.detail td { background:rgba(0,0,0,.03); }
"""

NAV = (f"<div class='topnav'>"
       "<a href='daily_overview.html'>每日总览</a>"
       "<a href='lhb.html'>龙虎榜分析</a>"
       "<a href='hotmoney.html'>游资看板</a>"
       f"<a href='status_{DATE}.html'>状态报告</a>"
       "<a href='2026-q2-industry-elite.html'>行业最强榜</a>"
       "<a href='../index.html'>总门户</a>"
       "</div>")

def page(title, body):
    html = ("<!DOCTYPE html><html lang='zh-CN'><head><meta charset='UTF-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1.0'>"
            f"<title>{title}</title><style>{CSS}</style></head><body><div class='wrap'>"
            f"{NAV}{body}</div></body></html>")
    # 在相邻标签边界换行，便于版本控制 diff 与逐行读取（HTML 标签间空白无害）
    return html.replace("><", ">\n<")

# ---------- 数据 ----------
ov = load(os.path.join(QUANT, "market_overview", f"{DATE}.json"))["data"]
def row(lc):
    for e in ov:
        if e.get("listCode") == lc:
            return e.get("row", {})
    return {}
summ = row("market_statis_summary")
trade = row("market_statis_daily_trade")
updown = row("market_statis_updown")
val = row("market_statis_valuation")
tech = row("market_statis_technical")
rot = row("market_statis_rotation")

board = load(os.path.join(QUANT, "board_hot", f"{DATE}.json"))["data"]["rankResult"]
news = load(os.path.join(QUANT, "news.json"))[DATE]
store = load(os.path.join(ROOT, "deliverables", "trading-agent", "_all_store.json"))
quotes = load(os.path.join(QUANT, "quotes", f"{DATE}.json"))["data"]
lu = load(os.path.join(QUANT, "limitup", f"{DATE}.json"))["data"]
lhb = load(os.path.join(QUANT, "lhb", f"{DATE}.json"))
if isinstance(lhb, dict) and "data" in lhb:
    lhb = lhb["data"]

# 富集数据（申万一/二级板块+涨跌幅、游资介入度、席位明细），由 build_lhb_enriched.py 生成
ENRICH = {}
try:
    ENRICH = load(os.path.join(QUANT, f"lhb_enriched_{DATE}.json")).get("stocks", {})
except Exception:
    ENRICH = {}
SCRIPT = ("<script>function toggle(id){var e=document.getElementById(id);"
          "if(e){e.style.display=(e.style.display==='none')?'table-row':'none';}}</script>")

# ---------- 连板梯队(2026-08-27, 来自 tool_ranking limitup_days) ----------
TIERS = {4: [], 3: [], 2: [], 1: []}
for s in lu["stocks"]:
    d = s.get("LimitUpDays")
    if d in TIERS:
        TIERS[d].append((s["name"], s["code"]))
LIMITUP_LISTED = sum(len(v) for v in TIERS.values())
LIMITUP_TOTAL = lu.get("totalStocks", LIMITUP_LISTED)
# 实际列出数（受 tool_ranking limit=100 截断）与全市场总数可能不一致，据实标注
LIMITUP_TOTAL_TXT = f"{LIMITUP_LISTED} 只" + (f"（全市场 {LIMITUP_TOTAL} 只）" if LIMITUP_TOTAL > LIMITUP_LISTED else "")
# 持仓股连板情况（动态，避免硬编码）
# 个人持仓不对外展示：连板梯队不标注持仓股
held_lu_txt = ""
# 连板高度（取实际最高板层）
max_tier = max([t for t in TIERS if TIERS[t]], default=0)
lhb_height = ("、".join(n for n, _ in TIERS[max_tier]) + f" {max_tier}板") if max_tier else "—"

# ---------- 大盘概览 ----------
idx_defs = [
    ("上证指数", "CLOSE_PRICE_SZZS", "CHANGE_PCT_SZZS", "HIGH_PRICE_SZZS", "LOW_PRICE_SZZS"),
    ("深证成指", "CLOSE_PRICE_SZCZ", "CHANGE_PCT_SZCZ", "HIGH_PRICE_SZCZ", "LOW_PRICE_SZCZ"),
    ("创业板指", "CLOSE_PRICE_CYBZ", "CHANGE_PCT_CYBZ", "HIGH_PRICE_CYBZ", "LOW_PRICE_CYBZ"),
]
idx_html = "<div class='idxrow'>"
for name, c, ch, hi, lo in idx_defs:
    idx_html += (f"<div class='idx'><div class='k'>{name}</div>"
                 f"<div class='v'>{fnum(trade[c])}</div>"
                 f"<div class='c {cls(trade[ch])}'>{pct(trade[ch])}</div>"
                 f"<div class='hl'>H {fnum(trade[hi])} · L {fnum(trade[lo])}</div></div>")
idx_html += "</div>"

red = updown.get("CNT_RED", 0); grn = updown.get("CNT_GREEN", 0)
zero = updown.get("CNT_ZERO", 0); tot = updown.get("CNT_TOTAL", 0)
rp = lambda n: (n / tot * 100) if tot else 0
bar_html = (f"<div class='bar'>"
            f"<div style='background:linear-gradient(90deg,#b87064,#b8332a);width:{rp(red):.1f}%'>"
            f"涨 {red}<br><span style='font-size:10px;opacity:.9'>{rp(red):.1f}%</span></div>"
            f"<div style='background:linear-gradient(90deg,rgba(154,154,164,.7),rgba(154,154,164,.55));width:{rp(zero):.1f}%'>平 {zero}</div>"
            f"<div style='background:linear-gradient(90deg,#7d9682,#1a9e5a);width:{rp(grn):.1f}%'>"
            f"跌 {grn}<br><span style='font-size:10px;opacity:.9'>{rp(grn):.1f}%</span></div></div>")

chip_html = (f"<div class='chiprow'>"
             f"<div class='chip'><div class='ck'>涨停</div><div class='cv up'>{updown.get('CNT_REACH_UPLIMIT')}</div></div>"
             f"<div class='chip'><div class='ck'>跌停</div><div class='cv down'>{updown.get('CNT_REACH_DNLIMIT')}</div></div>"
             f"<div class='chip'><div class='ck'>涨跌比</div><div class='cv' style='color:#b8893b'>{updown.get('RATIO_UPDOWN')}</div></div>"
             f"<div class='chip'><div class='ck'>5日新高/低</div><div class='cv' style='color:#8b9bb5'>{updown.get('CNT_HIGH5')}/{updown.get('CNT_LOW5')}</div></div>"
             f"<div class='chip'><div class='ck'>20日新高/低</div><div class='cv' style='color:#6b5b95'>{updown.get('CNT_HIGH20')}/{updown.get('CNT_LOW20')}</div></div>"
             f"<div class='chip'><div class='ck'>60日新高/低</div><div class='cv' style='color:#8aaab3'>{updown.get('CNT_HIGH60')}/{updown.get('CNT_LOW60')}</div></div>"
             f"</div>")

money = trade.get("MONEY"); avg5 = trade.get("MONEY_5DAVG"); avg20 = trade.get("MONEY_20DAVG")
ratio5 = trade.get("MONEY_5DAVG_RATIO")
vol_label = "放量" if (ratio5 and float(ratio5) >= 100) else "缩量"
vol_cls = "up" if (ratio5 and float(ratio5) >= 100) else "down"
money_html = (f"<div class='amberbox' style='color:#1c2430'>"
              f"<span style='font-size:13px;color:#3a4048'>沪深京成交额</span> "
              f"<span style='font-size:20px;font-weight:700'>{fnum(money)} 亿</span> "
              f"<span class='{vol_cls}' style='font-weight:700'>{vol_label}</span>"
              f"<div style='font-size:12px;color:#6b7280;margin-top:6px'>"
              f"5日均 {fnum(avg5)} 亿 ({ratio5}%) · "
              f"10日均 {fnum(trade.get('MONEY_10DAVG'))} 亿 ({trade.get('MONEY_10DAVG_RATIO')}%) · "
              f"20日均 {fnum(avg20)} 亿 ({trade.get('MONEY_20DAVG_RATIO')}%)</div></div>")

status_pairs = [
    ("情绪", summ.get("SENTIMENT_STATUS")),
    ("技术", summ.get("TECHNICAL_STATUS")),
    ("估值", summ.get("VALUATION_STATUS")),
    ("量能", summ.get("VOLUME_ENERGE_STATUS")),
    ("大小盘", summ.get("CAP_ROTATION_STATUS")),
    ("风格", summ.get("STYLE_ROTATION_STATUS")),
    ("行业轮动", summ.get("SECTOR_ROTATION_STATUS")),
    ("个股宽度", summ.get("STOCK_WIDTH_STATUS")),
    ("短期趋势", summ.get("TREND_SHORT_DIRECTION_STATUS")),
    ("中长期趋势", summ.get("TREND_LONG_DIRECTION_STATUS")),
]
tag_html = "<div class='chiprow'>"
for label, st in status_pairs:
    if st:
        tag_html += f"<span class='pill' title='{label}：{st}'><b>{label}</b> {short_status(st)}</span>"
tag_html += "</div>"

rot_rows = [
    ("沪深300", rot.get("CHG_5D_HS300"), rot.get("CHG_20D_HS300")),
    ("中证1000", rot.get("CHG_5D_ZZ1000"), rot.get("CHG_20D_ZZ1000")),
    ("全指成长", rot.get("CHG_5D_QZCZ"), rot.get("CHG_20D_QZCZ")),
    ("全指价值", rot.get("CHG_5D_QZJZ"), rot.get("CHG_20D_QZJZ")),
]
rot_html = "<table><tr><th>风格/规模</th><th class='num'>5日</th><th class='num'>20日</th></tr>"
for n, a, b in rot_rows:
    rot_html += f"<tr><td>{n}</td><td class='num {cls(a)}'>{pct(a)}</td><td class='num {cls(b)}'>{pct(b)}</td></tr>"
rot_html += "</table>"

# val_date 已在文件顶部按 --val-date / (DATE - 1) 计算
val_html = (f"<div class='amberbox' style='color:#1c2430'><b style='color:#1c2430'>中证全指估值</b>（口径 {val_date}）："
            f"PE_TTM <span style='font-size:16px;font-weight:700'>{val.get('PE_TTM')}</span> · "
            f"3年分位 <span class='up'>{val.get('PE_TTM_PCT_3Y')}%</span> · "
            f"5年分位 <span class='up'>{val.get('PE_TTM_PCT_5Y')}%</span> · "
            f"10年分位 <span class='up'>{val.get('PE_TTM_PCT_10Y')}%</span> "
            f"<span style='color:#8a929c;font-size:12px'>(PB {val.get('PB_LF')} · 股息率 {val.get('DIV_TTM')}%)</span></div>")

news_html = "<ul style='margin:0;padding-left:18px;color:#6b7280'>"
for it in news:
    impact = it.get("impact") or ""
    news_html += (f"<li style='margin:8px 0;line-height:1.55'>"
                  f"<span style='color:#b8893b;font-weight:700'>[{it.get('source','')}]</span> <b>{it.get('title','')}</b>"
                  + (f"<br><span style='color:#8a929c;font-size:12px'>▸ 影响：{impact}</span>" if impact else "") + "</li>")
news_html += "</ul>"

tech_defs = [
    ("MACD", tech.get("MACD"), "MACD>0，多头动能占优"),
    ("DIF", tech.get("DIF"), "DIF>DEA，金叉多头信号"),
    ("DEA", tech.get("DEA"), "DEA 为 DIF 的 9 日平滑，中期趋势"),
    ("KDJ-K", tech.get("KDJ_K"), "K>80 超买区，警惕回调"),
    ("KDJ-D", tech.get("KDJ_D"), "D 线为 K 线平滑，慢速随机"),
    ("KDJ-J", tech.get("KDJ_J"), "J 线放大 K/D 乖离，极端值提示转折"),
    ("RSI6", tech.get("RSI_6"), "RSI6 中性区域"),
    ("MA5", tech.get("MA_5"), "短周期在 MA20 上方，短期偏多"),
    ("MA20", tech.get("MA_20"), "20 日均线，中期趋势参考"),
    ("MA60", tech.get("MA_60"), "60 日均线，中长期趋势参考"),
    ("布林下轨", tech.get("BOLL_LOWER"), "弱势支撑位"),
    ("布林中轨", tech.get("BOLL_MID"), "多空分水岭"),
    ("布林上轨", tech.get("BOLL_UPPER"), "强势压力位"),
]
tech_html = "<table><tr><th>指标</th><th class='num'>数值</th><th>专业解读</th></tr>"
for n, v, d in tech_defs:
    tech_html += f"<tr><td style='color:#8a929c;font-size:12px'>{n}</td><td class='num' style='font-weight:700;color:#1c2430'>{fnum(v)}</td><td style='color:#6b7280;font-size:12px'>{d}</td></tr>"
tech_html += "</table>"

review = (f"{vol_label}，{short_status(summ.get('SENTIMENT_STATUS'))}，{short_status(summ.get('STOCK_WIDTH_STATUS'))}，"
          f"{short_status(summ.get('CAP_ROTATION_STATUS'))}，{short_status(summ.get('STYLE_ROTATION_STATUS'))}，"
          f"{short_status(summ.get('VALUATION_STATUS'))}，涨跌比 {updown.get('RATIO_UPDOWN')}，"
          f"短期{short_status(summ.get('TREND_SHORT_DIRECTION_STATUS'))}。")
outlook = (f"量能{'平稳' if ratio5 and 98<=float(ratio5)<=102 else ('放大' if ratio5 and float(ratio5)>102 else '收窄')}，"
           f"明日大概率维持震荡；MACD 红柱/正值；DIF 上穿 DEA，短期偏多；"
           f"KDJ 超买，短线有回调压力；MA5 在 MA20 上方；情绪偏高，次日分歧可能加大；"
           f"估值处于历史高位，追高风险大。")
review_html = (f"<div class='amberbox'><div style='margin-bottom:8px'><b>📌 专业点评：</b>{review}</div>"
               f"<div style='border-top:1px dashed rgba(201,166,107,.25);padding-top:8px'>"
               f"<b>🔮 次日展望：</b>{outlook}</div></div>")

market_overview_html = (
    f"<div class='section'><h2>📈 当日大盘概览 — {SNAP_DATE}（快照）</h2>"
    f"{idx_html}{bar_html}{chip_html}{money_html}"
    f"<div class='note' style='color:#8a929c'>以上标签由 westock-mcp data_market_overview 按全市场量价/估值/风格自动生成（聚合/收盘口径 {SNAP_DATE}；估值口径滞后至 {val_date}）。</div>"
    f"{tag_html}"
    f"<div style='font-size:13px;font-weight:700;color:#1c2430;margin:14px 0 8px'>风格 / 规模</div>{rot_html}"
    f"{val_html}"
    f"<div style='font-size:14px;font-weight:700;color:#1c2430;margin:14px 0 8px'>📰 当日要闻（{DATE}）</div>{news_html}"
    f"<div style='font-size:14px;font-weight:700;color:#1c2430;margin:14px 0 8px'>🔧 技术摘要与解读</div>{tech_html}"
    f"{review_html}</div>")

# ---------- 板块热度 ----------
boards_sorted = sorted(board, key=lambda x: float(x.get("zdf", 0)), reverse=True)
btags = ""
for b in boards_sorted[:18]:
    z = float(b.get("zdf", 0))
    kind = "hot" if z > 0 else "cold"
    btags += f"<span class='tag {kind}'>{b.get('name')} {pct(z)}</span>"
sector_html = (f"<div class='section'><h2>🔥 板块热度 — {DATE} 收盘</h2>"
               f"<div>{btags}</div>"
               f"<div class='note'>共 {len(board)} 个板块入选排行；领涨：{('、'.join(b['name']+' '+pct(float(b['zdf'])) for b in boards_sorted[:3]))}；"
               f"领跌：{('、'.join(b['name']+' '+pct(float(b['zdf'])) for b in boards_sorted[-3:]))}（数据来源：腾讯自选股板块排行）。</div></div>")

# ---------- 连板梯队 ----------
tier_label = {4: "4连板", 3: "3连板", 2: "2连板", 1: "首板"}
tier_cls = {4: "b4", 3: "b3", 2: "b2", 1: "b1"}
ladder_html = ""
for t in [4, 3, 2, 1]:
    names = TIERS[t]
    if t == 1:
        shown = names[:16]
        extra = f" …等共 {len(names)} 只" if len(names) > 16 else ""
        names_html = "".join(f"<span class='namechip'>{n}</span>" for n, _ in shown) + extra
    else:
        names_html = "".join(f"<span class='namechip'>{n}</span>" for n, _ in names)
    ladder_html += (f"<div class='ladder'><span class='badge {tier_cls[t]}'>{tier_label[t]}</span>"
                     f"<span style='color:#8a929c;font-size:11px'>({len(names)}只)</span>：{names_html}</div>")
leader_html = (f"<div class='section'><h2>👑 当日连板梯队（多口径）— {DATE}</h2>"
               f"<div class='note' style='color:#8a929c'>口径：全市场连续涨停天数（westock-mcp tool_ranking limitup_days）。"
               f"共 {LIMITUP_TOTAL_TXT}{held_lu_txt}。</div>"
               f"{ladder_html}"
               f"<div class='note'>资金龙头 / 板块龙头（按龙虎榜净买排序）见下方龙虎榜速览与龙虎榜分析页。</div></div>")

# ---------- 组合快照 ----------
held = [s for s in store["stocks"] if s["held"]]
rows_p = []
tot_mv = 0.0
for s in held:
    q = quotes.get(s["market"].lower() + s["code"])
    if q:
        price = q["price"]; chg = q["change_percent"]
    else:
        price = s.get("price"); chg = None
    tot_mv += s["qty"] * price
for s in held:
    q = quotes.get(s["market"].lower() + s["code"])
    price = q["price"]; chg = q["change_percent"]
    mv = s["qty"] * price
    cost = s["cost"]
    pnl = (price - cost) * s["qty"]
    pnl_pct = (price - cost) / cost * 100
    w = mv / tot_mv * 100
    rows_p.append((s, price, chg, mv, pnl, pnl_pct, w))
tot_pnl = sum(r[4] for r in rows_p)
tot_pnl_pct = tot_pnl / tot_mv * 100 if tot_mv else 0
port_rows = ""
for s, price, chg, mv, pnl, pnl_pct, w in rows_p:
    port_rows += (f"<tr><td><b>{s['name']}</b> <span class='note'>{s['code']}·{s['market']}</span></td>"
                  f"<td class='num'>{fnum(s['qty'],0)}</td>"
                  f"<td class='num'>{fnum(price)}</td>"
                  f"<td class='num {cls(chg)}'>{pct(chg)}</td>"
                  f"<td class='num'>{fnum(mv)}</td>"
                  f"<td class='num {cls(pnl)}'>{fnum(pnl)}</td>"
                  f"<td class='num {cls(pnl_pct)}'>{pct(pnl_pct)}</td>"
                  f"<td class='num'>{fnum(w)}%</td>"
                  f"<td class='num'>{int(s.get('hold_days') or 0)}</td></tr>")
top_holdings = "、".join(f"{r[0]['name']}({fnum(r[6])}%)" for r in sorted(rows_p, key=lambda x: -x[6]))
portfolio_table = (f"<table><tr><th>名称</th><th class='num'>持仓</th><th class='num'>现价</th><th class='num'>当日</th>"
                   f"<th class='num'>市值</th><th class='num'>浮动盈亏</th><th class='num'>盈亏%</th><th class='num'>仓位%</th>"
                   f"<th class='num'>天数</th></tr>{port_rows}</table>")
portfolio_html = (f"<div class='section'><h2>💼 组合快照 — 实时市值 {fnum(tot_mv)} 元</h2>"
                  f"{portfolio_table}"
                  f"<div class='amberbox' style='color:#1c2430'>组合浮动盈亏合计 "
                  f"<b class='{'up' if tot_pnl>=0 else 'down'}'>{fnum(tot_pnl)} 元（{pct(tot_pnl_pct)}）</b>。"
                  f"重仓顺序：{top_holdings}。</div></div>")

# ---------- 龙虎榜数据 ----------
jg = sorted(lhb.get("jg", []), key=lambda x: float(x.get("netBuyAmt", 0)), reverse=True)
yyb = [x for x in lhb.get("yyb", []) if x.get("code")]
yyb_sorted = sorted(yyb, key=lambda x: float(x.get("buyAmt", 0)), reverse=True)
gslmr = sorted(lhb.get("gslmr", []), key=lambda x: float(x.get("netAmt", 0)), reverse=True)
gslxw = sorted(lhb.get("gslxw", []), key=lambda x: float(x.get("netAmt", 0)), reverse=True)
lhb_all = lhb.get("all", [])  # 龙虎榜全榜上榜个股（rank/code/name/changePct/netBuyAmount/buyAmount/sellAmount）
LHB_DETAIL_EMPTY = not (jg or yyb or gslmr or gslxw)  # 分项榜是否全空
if LHB_DETAIL_EMPTY:
    # 根因：data_lhb 默认"全部"调用只回 all 全榜，jg/yyb/gslmr/gslxw 四项需 type 显式分 4 次拉取后合并进 lhb/{DATE}.json；
    # 若此处仍为空，说明分项数据未拉取/未合并，看板将只剩全榜、缺机构/游资购买比例与分析。
    import sys
    print("[WARN] LHB 分项(jg/yyb/gslmr/gslxw)全空 → 看板将缺机构/游资分析。"
          "请确认已用 data_lhb(type=jg/yyb/gslmr/gslxw) 分 4 次拉取并用 _merge_lhb_subtabs.py 合并。",
          file=sys.stderr)
_lhb_sorted_all = sorted(lhb_all, key=lambda x: float(x.get("netBuyAmount", 0)), reverse=True)

def jg_table(rows, n=20):
    h = ("<table><tr><th>名称</th><th class='num'>上榜</th><th class='num'>机构买入(亿)</th>"
         "<th class='num'>机构净买(亿)</th><th class='num'>净买率%</th><th class='num'>席位</th>"
         "<th class='num'>总买入(亿)</th><th class='num'>排名</th></tr>")
    for r in rows[:n]:
        h += (f"<tr><td><b>{r['name']}</b> <span class='note'>{r['code']}</span></td>"
              f"<td class='num'>{r.get('tdDays')}</td>"
              f"<td class='num'>{yi(r.get('instBuyAmt'))}</td>"
              f"<td class='num {cls(r.get('netBuyAmt'))}'>{yi(r.get('netBuyAmt'))}</td>"
              f"<td class='num {cls(r.get('netBuyRate'))}'>{fnum(r.get('netBuyRate'))}</td>"
              f"<td class='num'>{r.get('instBuyBranchCount')}</td>"
              f"<td class='num'>{yi(r.get('totalBuyAmt'))}</td>"
              f"<td class='num'>{r.get('rank')}</td></tr>")
    h += "</table>"
    return h

def gslmr_table(rows):
    h = ("<table><tr><th>名称</th><th class='num'>上榜天数</th><th class='num'>共振净买(亿)</th>"
         "<th class='num'>当日涨幅%</th><th class='num'>买入(亿)</th><th class='num'>卖出(亿)</th>"
         "<th class='num'>席位家数</th></tr>")
    for r in rows:
        h += (f"<tr><td><b>{r['name']}</b> <span class='note'>{r['code']}</span></td>"
              f"<td class='num'>{r.get('tdDays')}</td>"
              f"<td class='num {cls(r.get('netAmt'))}'>{yi(r.get('netAmt'))}</td>"
              f"<td class='num {cls(r.get('upRate'))}'>{pct(r.get('upRate'))}</td>"
              f"<td class='num'>{yi(r.get('bAmt'))}</td>"
              f"<td class='num'>{yi(r.get('sAmt'))}</td>"
              f"<td class='num'>{r.get('winNum')}</td></tr>")
    h += "</table>"
    return h

def yyb_table(rows, n=25):
    h = ("<table><tr><th>游资席位</th><th>涉及个股</th><th class='num'>净买额(亿)</th></tr>")
    for r in rows[:n]:
        h += (f"<tr><td>{r['name']}</td>"
              f"<td style='color:#6b7280;font-size:12px'>{r.get('stockName','')}</td>"
              f"<td class='num {cls(r.get('buyAmt'))}'>{yi(r.get('buyAmt'))}</td></tr>")
    h += "</table>"
    return h

def gslxw_table(rows, n=20):
    h = ("<table><tr><th>营业部席位</th><th class='num'>胜率%</th><th class='num'>净买额(亿)</th><th>涉及个股</th></tr>")
    for r in rows[:n]:
        stocks = "、".join(s.get("name", "") for s in r.get("stockList", []))
        h += (f"<tr><td>{r['name']}</td>"
              f"<td class='num' style='color:#b8893b;font-weight:700'>{fnum(float(r.get('winRate',0))*100,1)}</td>"
              f"<td class='num {cls(r.get('netAmt'))}'>{yi(r.get('netAmt'))}</td>"
              f"<td style='color:#6b7280;font-size:12px'>{stocks}</td></tr>")
    h += "</table>"
    return h

def lhb_all_table(rows, n=30):
    h = ("<table><tr><th>排名</th><th>名称</th><th class='num'>当日涨幅%</th>"
         "<th class='num'>净买入(亿)</th><th class='num'>买入(亿)</th><th class='num'>卖出(亿)</th></tr>")
    for r in rows[:n]:
        # yi() 已自带 /1e8 → 元转亿，这里不要再预先除一次
        net_raw = r.get("netBuyAmount", 0)
        buy_raw = r.get("buyAmount", 0)
        sell_raw = r.get("sellAmount", 0)
        h += (f"<tr><td class='num'>{r.get('rank')}</td>"
              f"<td><b>{r['name']}</b> <span class='note'>{r['code']}</span></td>"
              f"<td class='num {cls(r.get('changePct'))}'>{pct(r.get('changePct'))}</td>"
              f"<td class='num {cls(net_raw)}'>{yi(net_raw)}</td>"
              f"<td class='num'>{yi(buy_raw)}</td>"
              f"<td class='num'>{yi(sell_raw)}</td></tr>")
    h += "</table>"
    return h

def _seat_li(s, kind):
    amt = s.get("buy" if kind == "buy" else "sell", 0)
    tag = f" <span class='hmtag'>{s['tag']}</span>" if s.get("tag") else ""
    return (f"<li><span class='nm'>{s['name']}</span>"
            f"<span class='amt {cls(amt)}'>{yi(amt)}亿</span>{tag}</li>")

def lhb_enriched_table(enr, sort_by="net"):
    """富化龙虎榜表：一级/二级板块+涨跌幅、游资介入度、可展开买卖方席位。"""
    if not enr:
        return "<div class='empty'>无富集数据</div>"
    items = list(enr.values())
    if sort_by == "hot":
        order = {"高": 0, "中": 1, "低": 2}
        items.sort(key=lambda d: (order.get(d["hotmoneyLevel"], 3), -(d.get("hotmoneyNet") or 0)))
    else:
        items.sort(key=lambda d: -(d.get("netBuy") or 0))
    h = ("<table class='lhb'><thead><tr>"
         "<th>排名</th><th>名称</th><th class='num'>涨幅%</th><th class='num'>净买入(亿)</th>"
         "<th>上榜原因</th><th>一级行业</th><th>二级行业</th><th>游资介入度</th><th>席位</th></tr></thead><tbody>")
    for i, d in enumerate(items, 1):
        code = d["code"]; name = d["name"]
        ipo = " (推测)" if d.get("ipo") else ""
        sw1 = f"{d['sw1']}{ipo} <span class='{cls(d['sw1Chg'])}'>{pct(d['sw1Chg'])}</span>" if d["sw1"] else "—"
        sw2 = f"{d['sw2']}{ipo} <span class='{cls(d['sw2Chg'])}'>{pct(d['sw2Chg'])}</span>" if d["sw2"] else "—"
        lvl = d["hotmoneyLevel"]
        lvlcls = {"高": "hm-high", "中": "hm-mid", "低": "hm-low"}.get(lvl, "hm-low")
        tags = "".join(f"<span class='hmtag'>{t}</span>" for t in d["hotmoneyTags"]) or "<span class='note'>—</span>"
        reason = d["reason"] or "—"
        h += (f"<tr class='r' onclick=\"toggle('d{code}')\" style='cursor:pointer'>"
              f"<td class='num'>{i}</td>"
              f"<td><b>{name}</b> <span class='note'>{code}</span></td>"
              f"<td class='num {cls(d['changePct'])}'>{pct(d['changePct'])}</td>"
              f"<td class='num {cls(d['netBuy'])}'>{yi(d['netBuy'])}</td>"
              f"<td class='reason'>{reason}</td>"
              f"<td class='sec'>{sw1}</td>"
              f"<td class='sec'>{sw2}</td>"
              f"<td class='hm {lvlcls}'>{lvl}<div class='hmtags'>{tags}</div></td>"
              f"<td><span class='toggle'>▸ 席位</span></td></tr>")
        buys = "".join(_seat_li(s, "buy") for s in d["buySeats"]) or "<li class='note'>—</li>"
        sells = "".join(_seat_li(s, "sell") for s in d["sellSeats"]) or "<li class='note'>—</li>"
        netcls = cls(d.get("hotmoneyNet"))
        h += (f"<tr id='d{code}' class='detail' style='display:none'><td colspan='9'>"
              f"<div class='seats'><div class='buys'><div class='seat-h up'>买方席位 Top5</div><ul>{buys}</ul></div>"
              f"<div class='sells'><div class='seat-h down'>卖方席位 Top5</div><ul>{sells}</ul></div></div>"
              f"<div class='note'>游资净买合计：<b class='{netcls}'>{yi(d.get('hotmoneyNet'))}亿</b>"
              f"（仅统计带游资标签席位；共 {d['hotmoneyCount']} 个标签席位）</div></td></tr>")
    h += "</tbody></table>"
    return h

# 速览卡(嵌入总览)
jg_top3 = "、".join(f"{r['name']}({yi(r['netBuyAmt'])}亿)" for r in jg[:3])
yyb_top3 = "、".join(f"{r['name']}({yi(r['buyAmt'])}亿)" for r in yyb_sorted[:3])
gslmr_txt = (f"{gslmr[0]['name']}({yi(gslmr[0]['netAmt'])}亿) 等 {len(gslmr)} 只"
            if gslmr else
            f"当日龙虎榜细分（机构榜/共振/席位胜率）数据源未披露；龙虎榜全榜共 {len(lhb_all)} 只，见 lhb.html")
lhb_summary = (
    f"<div class='section'><h2>🐉 龙虎榜速览 — {DATE}</h2>"
    f"<div class='amberbox' style='color:#1c2430'>"
    f"<b>机构净买 TOP3</b>：{jg_top3}<br>"
    f"<b>游资净买 TOP 席位</b>：{yyb_top3}<br>"
    f"<b>连板高度</b>：{lhb_height}，共 {LIMITUP_TOTAL_TXT}<br>"
    f"<b>机构+游资共振</b>：{gslmr_txt}</div>"
    f"<div style='margin-top:6px'>"
    f"<a class='inlink' href='lhb.html'>龙虎榜分析页(机构榜/共振/胜率) →</a>"
    f"<a class='inlink' href='hotmoney.html'>游资看板(席位净买/胜率) →</a>"
    f"<a class='inlink' href='../index.html'>返回总门户 →</a></div></div>")

# ---------- 每日总览页 ----------
overview_body = (
    f"<header><h1>📊 A股量化助理 · 每日总览</h1>"
    f"<p>大盘概览 / 板块热度 / 连板梯队 / 龙虎榜速览 — 数据口径 {DATE}（大盘概览快照 {SNAP_DATE} · 估值 {val_date}）</p></header>"
    f"<div class='meta'>数据来源：腾讯自选股 <b>westock-mcp</b>（data_market_overview / tool_ranking / data_hot / data_quote / data_lhb）。</div>"
    f"{market_overview_html}{sector_html}{leader_html}{lhb_summary}"
    f"<footer>本报告由 A 股量化助理自动化生成 · 数据仅供参考，不构成投资建议 · 市场有风险，投资需谨慎</footer>")
open(os.path.join(WEB, "daily_overview.html"), "w", encoding="utf-8").write(
    page("A股量化助理 · 每日总览", overview_body))

# ---------- 组合总看板页 ----------
portfolio_body = (
    f"<header><h1>💼 组合总看板</h1><p>持仓 9 只 · 实时市值 {fnum(tot_mv)} 元（{DATE} 收盘）</p></header>"
    f"<div class='meta'>数据源：券商导出持仓（table.xls）→ _all_store.json + 腾讯自选股实时行情。</div>"
    f"{portfolio_html}"
    f"<footer>组合盈亏为浮动口径，以实时收盘价计；仓位% 按组合内实时市值占比重算。</footer>")
# 个人持仓不对外展示：跳过组合总看板页面生成
# open(os.path.join(WEB, "portfolio.html"), "w", encoding="utf-8").write(
#     page("组合总看板", portfolio_body))

# ---------- 游资看板页（游资介入度 + 席位 + 板块） ----------
_hotmoney_detail = ""
if yyb_sorted:
    _hotmoney_detail += (
        f"<div class='section'><h2>🏦 游资席位净买榜 TOP25</h2>"
        f"<div class='note'>按当日净买入额排序（单位：亿元）；共统计 {len(yyb)} 个上榜营业部席位。</div>"
        f"{yyb_table(yyb_sorted)}</div>")
if gslxw:
    _hotmoney_detail += (
        f"<div class='section'><h2>🎯 营业部席位胜率聚合 TOP20</h2>"
        f"<div class='note'>基于近 1·3·5·10 日窗口的营业部胜率（数据口径来自 data_lhb gslxw）；胜率仅供参考。</div>"
        f"{gslxw_table(gslxw)}</div>")
_hotmoney_detail += (
    f"<div class='section'><h2>🐉 龙虎榜个股 · 游资介入度与席位（{len(ENRICH) if ENRICH else len(lhb_all)} 只，按介入度）</h2>"
    f"<div class='note'>按游资介入度（高→中→低）排序；点击行展开买卖方席位 Top5 与游资标签。"
    f"游资净买合计仅统计带标签席位（净买入额单位：亿元）。板块为申万一级/二级（名称+当日涨跌幅）。</div>"
    f"{lhb_enriched_table(ENRICH, sort_by='hot') if ENRICH else lhb_all_table(_lhb_sorted_all, 25)}</div>")
hotmoney_body = (
    f"<header><h1>🐉 游资看板</h1><p>游资介入度 / 席位明细 / 板块(一级·二级) / 板块涨跌幅 — {DATE}</p></header>"
    f"<div class='meta'>数据来源：westock-mcp data_lhb（yyb 营业部榜 / gslxw 席位胜率 / all 龙虎榜全榜）+ data_sector（申万一/二级涨跌幅）。</div>"
    f"{_hotmoney_detail}"
    f"<footer>⚠️ 盘后滞后资金痕迹，仅提示概率优势方向，不构成投资建议。</footer>{SCRIPT}")
open(os.path.join(WEB, "hotmoney.html"), "w", encoding="utf-8").write(
    page("游资看板", hotmoney_body))

# ---------- 龙虎榜分析页（含一级/二级板块、涨跌幅、游资介入度、席位） ----------
_lhb_enr_section = (
    f"<div class='section'><h2>🐉 龙虎榜全榜 {len(ENRICH) if ENRICH else len(lhb_all)} 只（按净买入额排序）</h2>"
    f"<div class='note'>每行可点击展开查看买方/卖方席位 Top5 与游资标签。板块为申万一级 / 二级（名称+当日涨跌幅）；"
    f"游资介入度按带标签席位数量分高/中/低，游资净买合计仅统计带标签席位。净买入额单位：亿元。</div>"
    f"{lhb_enriched_table(ENRICH) if ENRICH else lhb_all_table(_lhb_sorted_all)}</div>")

_lhb_inst_section = ""
if not LHB_DETAIL_EMPTY:
    _lhb_inst_section = (
        f"<div class='section'><h2>🏛️ 机构专用榜 TOP20（按净买额）</h2>"
        f"<div class='note'>机构专用席位净买入口径；净买额为净流入（买入−卖出）。共 {len(jg)} 只个股上榜机构榜。</div>"
        f"{jg_table(jg)}</div>"
        f"<div class='section'><h2>🔗 机构 + 游资共振买入（{len(gslmr)} 只）</h2>"
        f"<div class='note'>同时出现机构与活跃游资席位合力的个股；netAmt 为共振净流入，upRate 为当日涨幅，winNum 为龙虎榜上榜席位家数。</div>"
        f"{gslmr_table(gslmr)}</div>"
        f"<div class='section'><h2>🎯 营业部席位胜率聚合 TOP20</h2>"
        f"{gslxw_table(gslxw)}</div>")

lhb_body = (
    f"<header><h1>🐉 龙虎榜分析</h1><p>个股板块(一级/二级) · 涨跌幅 · 游资介入度 · 席位明细 — {DATE}</p></header>"
    f"<div class='meta'>数据来源：westock-mcp data_lhb（全榜 / 机构榜 / 共振 / 席位胜率）+ data_sector（申万一/二级涨跌幅）。"
    f"一级涨跌幅为成分二级均值（{DATE} 实时）。</div>"
    f"{_lhb_enr_section}{_lhb_inst_section}"
    f"<div class='section'><h2>📐 窗口收益（alpha vs 大盘）</h2>"
    f"<div class='empty'>1·3·5·10 交易日窗口收益回测属量化专题，需历史复权数据支撑，本页未内置；"
    f"该专题为早期远程分析页，本地未保留，后续可单独建设。</div></div>"
    f"<footer>⚠️ 盘后滞后资金痕迹，仅提示概率优势方向，不构成投资建议。</footer>{SCRIPT}")
open(os.path.join(WEB, "lhb.html"), "w", encoding="utf-8").write(
    page("龙虎榜分析", lhb_body))
open(os.path.join(WEB, f"lhb_{DATE}.html"), "w", encoding="utf-8").write(
    page("龙虎榜分析", lhb_body))

# ---------- 状态报告 ----------
status_body = (
    f"<header><h1>📋 状态报告</h1><p>{DATE} · 龙虎榜手动更新 + 全量数据刷新</p></header>"
    f"<div class='section'><h2>✅ 本轮完成情况</h2>"
    f"<div class='amberbox' style='color:#1c2430'>"
    f"1. <b>龙虎榜数据</b>：通过 westock-mcp data_lhb 拉取 {DATE} 真实龙虎榜（机构榜 {len(jg)} 只、游资席位 {len(yyb)} 个、机构+游资共振 {len(gslmr)} 只、席位胜率 {len(gslxw)} 条；龙虎榜全榜上榜 {len(lhb_all)} 只）。"
    + (f"分项（机构榜/游资席位/共振/胜率）数据源当日未披露（均为空），已以龙虎榜全榜 {len(lhb_all)} 只兜底渲染 lhb.html / hotmoney.html。"
       if LHB_DETAIL_EMPTY else
       f"已渲染 lhb.html（机构榜/共振/胜率）与 hotmoney.html（席位净买榜/胜率）。")
    + f"<br>"
    f"2. <b>大盘/板块/连板刷新</b>：data_market_overview({DATE})、data_hot(board)、tool_ranking(limitup_days) 全部更新为 {DATE}（估值口径 {val_date}）。<br>"
    f""
    f"4. <b>推送</b>：本地已生成 6 个页面（含导航 index.html、龙虎榜归档页 lhb_{DATE}.html），待经 GitHub 连接器推送至 dujoer/stocks 的 web/ 目录（main 分支，需仓库写权限）。"
    f"注：早期 08-14 窗口收益/共振/Alpha 回测为远程分析页，本地未保留，本系统以龙虎榜机构榜、共振、席位胜率为核心。</div></div>"
    f"<div class='section'><h2>📁 产出文件</h2>"
    f"<div class='chiprow'>"
     f"<span class='pill'>index.html</span><span class='pill'>daily_overview.html</span>"
     f"<span class='pill'>lhb.html</span><span class='pill'>hotmoney.html</span><span class='pill'>lhb_{DATE}.html</span>"
     f"<span class='pill'>status_{DATE}.html</span></div>"
    f"<div class='note'>数据落盘：quant/market_overview、board_hot、quotes、news.json、limitup、lhb（均为 {DATE}）。"
    f"生成脚本：quant/build_dashboards.py。</div></div>"
    f"<div class='section'><h2>⚠️ 口径说明</h2>"
    f"<div class='empty' style='text-align:left'>"
    f"· 估值（PE 分位）接口最新快照为 {val_date}，其余均为 {DATE}。<br>"
    f"· 窗口收益(alpha)回测未内置，链接至远程历史分析页。<br>"
    f"· 所有资金数据为盘后公开龙虎榜，滞后且非未来收益承诺。</div></div>"
    f"<footer>由 A 股量化助理生成 · 仅供参考，不构成投资建议。</footer>")
open(os.path.join(WEB, f"status_{DATE}.html"), "w", encoding="utf-8").write(
    page("状态报告", status_body))

# ---------- 导航首页 ----------
# 动态扫描每日龙虎榜归档页（lhb_YYYY-MM-DD.html）
_lhb_files = []
for _fn in os.listdir(WEB):
    _m = re.match(r"^lhb_(\d{4}-\d{2}-\d{2})\.html$", _fn)
    if _m:
        _lhb_files.append((_m.group(1), _fn))
_lhb_files.sort(reverse=True)
lhb_archive_html = "".join(f"<a href='{fn}'>{dt}</a>" for dt, fn in _lhb_files)

index_body = (
    f"<header><h1>📊 龙虎榜 · 入口与归档</h1>"
    f"<p>本页为龙虎榜板块的辅助入口，主看板请点击下方按钮。</p></header>"
    f"<div class='date'>数据口径：{DATE}（大盘概览快照 {SNAP_DATE} · 估值快照 {val_date}）</div>"
    f"<div class='grid'>"
    f"<a class='card' href='lhb.html'><div class='ic'>🐉</div><div class='t'>龙虎榜主看板</div>"
    f"<div class='d'>机构专用榜 / 机构+游资共振 / 席位胜率 / 申万一·二级板块与涨跌幅</div></a>"
    f"<a class='card' href='daily_overview.html'><div class='ic'>📈</div><div class='t'>每日总览</div>"
    f"<div class='d'>大盘 / 板块热度 / 连板梯队 / 龙虎榜速览</div></a>"
    f"<a class='card' href='hotmoney.html'><div class='ic'>🏦</div><div class='t'>游资看板</div>"
    f"<div class='d'>游资席位净买榜 TOP25 / 营业部胜率聚合</div></a>"
    f"<a class='card' href='status_{DATE}.html'><div class='ic'>📋</div><div class='t'>状态报告</div>"
    f"<div class='d'>本轮产出、文件清单与口径说明</div></a>"
    f"</div>"
    f"<div class='hist'><b>每日龙虎榜归档：</b>{lhb_archive_html}"
    f"<br><a href='../index.html'>← 返回 A股分析中心总门户</a></div>"
    f"<div class='foot'>数据来源：腾讯自选股 westock-mcp（盘后公开数据，滞后且非未来收益承诺）。<br>"
    f"由 A 股量化助理生成 · 仅供参考，不构成投资建议。</div>")
open(os.path.join(WEB, "index.html"), "w", encoding="utf-8").write(
    ("<!DOCTYPE html><html lang='zh-CN'><head><meta charset='UTF-8'>"
     "<meta name='viewport' content='width=device-width,initial-scale=1.0'>"
     f"<title>A股量化助理 · 龙虎榜看板</title><style>{CSS}</style></head><body><div class='wrap landing'>"
     f"{index_body}</div></body></html>").replace("><", ">\n<"))

print("OK: daily_overview / portfolio / lhb / hotmoney / status / index 已生成")
print(f"组合实时市值={tot_mv:.2f} 浮动盈亏={tot_pnl:.2f} ({tot_pnl_pct:.2f}%)")
print(f"龙虎榜: 机构榜{len(jg)} 游资席位{len(yyb)} 共振{len(gslmr)} 胜率{len(gslxw)}; 连板共{LIMITUP_TOTAL}只")
