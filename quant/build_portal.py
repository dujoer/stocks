# -*- coding: utf-8 -*-
"""生成 A股分析中心 · 总门户（G:\\ai\\股票\\index.html）。

扫描 3 个子系统的「最新一期」文件，自动写出统一入口，并标注每个子系统的
数据新鲜度（相对今天的天数差），避免主看板/板块/雷达各自为政。

子系统：
  1) 龙虎榜主看板   web/index.html         最新 = max(web/lhb_YYYY-MM-DD.html)
  2) 板块强度       web/sector-strength-index.html  最新 = max(web/sector-strength-YYYYMMDD.html)
  3) 群体心理风险雷达 market-trend/index.html        最新 = max(market-trend/crowd-psychology-risk-radar-YYYYMMDD.html)
"""
import os, re, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(ROOT, "web")
MT = os.path.join(ROOT, "market-trend")
OUT = os.path.join(ROOT, "index.html")
TODAY = datetime.date.today()

def parse_date(s):
    s = s.strip()
    for fmt in ("%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.datetime.strptime(s, fmt).date()
        except Exception:
            pass
    return None

def latest(pattern, directory):
    """返回 (date_obj, filename) 或 (None, None)"""
    best_d, best_f = None, None
    if not os.path.isdir(directory):
        return best_d, best_f
    for fn in os.listdir(directory):
        m = re.match(pattern, fn)
        if not m:
            continue
        d = parse_date(m.group(1))
        if d is None:
            continue
        if best_d is None or d > best_d:
            best_d, best_f = d, fn
    return best_d, best_f

def freshness(d):
    if d is None:
        return "无数据", "stale"
    diff = (TODAY - d).days
    if diff <= 0:
        return "今日", "fresh"
    if diff == 1:
        return "昨日", "fresh"
    if diff <= 3:
        return f"{diff} 天前", "warn"
    return f"{diff} 天前", "stale"

# ---- 扫描各子系统最新日期 ----
lhb_d, lhb_f = latest(r"^lhb_(\d{4}-\d{2}-\d{2})\.html$", WEB)
sec_d, sec_f = latest(r"^sector-strength-(\d{8})\.html$", WEB)
psy_d, psy_f = latest(r"^crowd-psychology-risk-radar-(\d{8})\.html$", MT)

lhb_txt, lhb_cls = freshness(lhb_d)
sec_txt, sec_cls = freshness(sec_d)
psy_txt, psy_cls = freshness(psy_d)

def fmt(d):
    return d.strftime("%Y-%m-%d") if d else "—"

def badge(cls, txt):
    return f"<span class='badge {cls}'>{txt}</span>"

# ---- 卡片定义 ----
cards = [
    {
        "ic": "🐉", "t": "龙虎榜主看板", "href": "web/index.html",
        "d": "大盘概览 / 板块热度 / 连板梯队 / 龙虎榜机构榜·共振·席位胜率",
        "date": fmt(lhb_d), "fresh": badge(lhb_cls, lhb_txt),
    },
    {
        "ic": "🔥", "t": "板块强度", "href": "web/sector-strength-index.html",
        "d": "行业/概念板块主力资金、强度与主力行为（抢筹/建仓/洗盘/出货）日更与趋势",
        "date": fmt(sec_d), "fresh": badge(sec_cls, sec_txt),
    },
    {
        "ic": "🧠", "t": "群体心理风险雷达", "href": "market-trend/index.html",
        "d": "情绪周期 / 认知偏差热力 / 风险分层，每日单篇 + 跨日趋势索引",
        "date": fmt(psy_d), "fresh": badge(psy_cls, psy_txt),
    },
    {
        "ic": "🏆", "t": "行业最强榜（全市场）", "href": "web/2026-q2-industry-elite.html",
        "d": "全市场 5544 只 A 股中报股东全量解析：申万 31 个行业各自最强的自然人 / 私募 / 公募各 20 名 + 资金估值四象限 + 胜率/均涨",
        "date": "2026-06-30", "fresh": badge("warn", "全市场"),
    },
]

cards_html = "\n".join(
    f"<a class='card' href='{c['href']}'>"
    f"<div class='cardtop'><span class='ic'>{c['ic']}</span>{c['fresh']}</div>"
    f"<div class='t'>{c['t']}</div>"
    f"<div class='d'>{c['d']}</div>"
    f"<div class='meta'>数据截至 {c['date']}</div>"
    f"</a>" for c in cards
)

# ---- 每日更新清单 ----
update_steps = [
    ("① 拉取当日数据", "用 westock-mcp 拉取 market_overview / board_hot / quotes / limitup / lhb / news，分别落盘到 quant 对应子目录的 <b>{DATE}.json</b>。"),
    ("② 生成龙虎榜主看板", "<code>python quant\\build_dashboards.py --date {DATE}</code> → 重写 web/ 下 7 个页面（含导航 index.html）。"),
    ("③ 板块强度（可选）", "若当日行业/概念快照已落盘：<code>python quant\\run_daily_sector.py --date {DATE} --industry &lt;file&gt; --concept &lt;file&gt;</code> → 刷新 web/sector-strength-* 与索引。"),
    ("④ 心理风险雷达（可选）", "按 market-trend 既有 _build 范式，用当日 westock 真实数据生成 crowd-psychology-risk-radar-{DATE}.html 并入 market-trend/index.html。"),
    ("⑤ 刷新总门户", "<code>python quant\\build_portal.py</code> → 重建本页，自动带出各子系统最新日期与新鲜度。"),
    ("⑥ 校验与推送", "检查无外链/死链、JS 语法；经 GitHub 连接器推送 web/ 与 market-trend/ 至仓库。"),
]

steps_html = "\n".join(
    f"<div class='step'><div class='no'>{i+1}</div><div><b>{t}</b><br><span class='sd'>{d}</span></div></div>"
    for i, (t, d) in enumerate(update_steps)
)

html = f"""<!DOCTYPE html>
<html lang='zh-CN'>
<head>
<meta charset='UTF-8'>
<meta name='viewport' content='width=device-width,initial-scale=1.0'>
<title>A股分析中心 · 总门户</title>
<style>
* {{ box-sizing:border-box; }}
body {{ margin:0; background:#f5f6f8; color:#1c2430;
  font-family:"PingFang SC","Microsoft YaHei","Hiragino Sans GB",sans-serif; line-height:1.7; }}
.wrap {{ max-width:1040px; margin:0 auto; padding:40px 22px 70px; }}
header.top {{ border-bottom:3px solid #1f4e79; padding-bottom:18px; margin-bottom:10px; }}
h1 {{ font-size:30px; margin:0 0 6px; letter-spacing:.5px; }}
.sub {{ color:#5a6573; font-size:14px; }}
.updated {{ color:#7b8794; font-size:12.5px; margin:6px 0 26px; }}
.grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(230px,1fr)); gap:18px; }}
.card {{ display:block; text-decoration:none; color:inherit; background:#fff; border:1px solid #e3e7ec;
  border-radius:16px; padding:22px 20px; box-shadow:0 2px 10px rgba(20,30,50,.05); transition:.18s; }}
.card:hover {{ border-color:#2b6cb0; transform:translateY(-3px); box-shadow:0 8px 22px rgba(31,78,121,.12); }}
.cardtop {{ display:flex; align-items:center; justify-content:space-between; }}
.ic {{ font-size:30px; }}
.t {{ font-size:18px; font-weight:700; margin:12px 0 8px; color:#1c2430; }}
.d {{ font-size:13px; color:#5a6573; line-height:1.65; min-height:62px; }}
.meta {{ font-size:12px; color:#7b8794; margin-top:12px; padding-top:10px; border-top:1px dashed #e3e7ec; }}
.badge {{ font-size:11px; padding:3px 10px; border-radius:20px; font-weight:700; }}
.badge.fresh {{ background:#e6f6ee; color:#128a52; }}
.badge.warn {{ background:#fdf3e0; color:#b7791f; }}
.badge.stale {{ background:#fdecea; color:#c0392b; }}
h2 {{ font-size:21px; margin:44px 0 16px; padding-left:12px; border-left:5px solid #1f4e79; }}
.sop {{ background:#fff; border:1px solid #e3e7ec; border-radius:14px; padding:8px 22px; margin:14px 0;
  box-shadow:0 1px 4px rgba(20,30,50,.04); }}
.step {{ display:flex; gap:14px; padding:14px 4px; border-bottom:1px solid #eef1f4; }}
.step:last-child {{ border-bottom:none; }}
.no {{ flex:none; width:26px; height:26px; line-height:26px; text-align:center; border-radius:50%;
  background:#1f4e79; color:#fff; font-size:13px; font-weight:700; }}
.sd {{ font-size:13px; color:#5a6573; }}
code {{ background:#eef4fa; color:#1f4e79; padding:1px 6px; border-radius:5px; font-size:12.5px; }}
.note {{ background:#fffaf0; border-left:4px solid #b7791f; padding:12px 16px; border-radius:0 8px 8px 0;
  font-size:13.5px; color:#6b4f2a; margin:14px 0; }}
footer {{ margin-top:48px; padding-top:18px; border-top:1px solid #e3e7ec;
  font-size:12px; color:#7b8794; line-height:1.8; }}
</style>
</head>
<body>
<div class='wrap'>
<header class='top'>
  <h1>A股分析中心 · 总门户</h1>
  <div class='sub'>龙虎榜主看板 · 板块强度 · 群体心理风险雷达 · 行业最强榜</div>
  <div class='updated'>门户重建于 {TODAY.strftime('%Y-%m-%d')} · 各卡片标注对应子系统的数据最新日期与新鲜度</div>
</header>

<div class='grid'>
{cards_html}
</div>

<div class='note'>提示：板块强度 / 心理雷达 两个子系统需先各自完成当日数据拉取与构建，再运行本门户生成器即可自动带出最新日期。龙虎榜主看板由 <code>build_dashboards.py</code> 统一生成。</div>

<h2>📅 每日更新清单（SOP）</h2>
<div class='note'>完整操作手册（数据口径、已知坑、校验清单）见 <a href='DAILY_UPDATE_SOP.html'>DAILY_UPDATE_SOP.html</a>。下表为精简步骤，各子系统最新日期以本门户卡片为准。</div>
<div class='sop'>
{steps_html}
</div>

<footer>
数据来源：腾讯自选股 <b>westock-mcp</b>（盘后公开数据，滞后且非未来收益承诺）。<br>
全部页面由 A股量化助理自动化生成 · 仅供参考，<b>不构成投资建议</b> · 市场有风险，投资需谨慎。
</footer>
</div>
</body>
</html>
"""

with open(OUT, "w", encoding="utf-8") as f:
    f.write(html)
print(f"OK: 总门户已生成 -> {OUT}")
print(f"    龙虎榜={fmt(lhb_d)} | 板块强度={fmt(sec_d)} | 心理雷达={fmt(psy_d)}")
