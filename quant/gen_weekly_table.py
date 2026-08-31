# -*- coding: utf-8 -*-
"""生成本周涨停复盘周表：HTML(查看) + CSV(补数)。
数据来源：腾讯自选股 westock-mcp
  - data_market_overview(type=all) 回拉 2026-08-17~08-21 每日
  - tool_ranking(limitup_days) 回拉每日连板梯队
缺失指标(标"待补")：腾讯自选股 westock-mcp 标准输出未提供，需另源。
"""
import csv, os

OUT_HTML = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "web", "limitup_weekly_2026-08-17_21.html")
OUT_CSV  = os.path.join(os.path.dirname(os.path.abspath(__file__)), "limitup_weekly_2026-08-17_21.csv")

# 有效涨停 = 非ST涨停(含20%板/北交所板)；20%涨停 = 创业板(300/301)+科创板(688)
# 涨跌停比例 = 有效涨停 / 跌停家数
# 连板数 = limitup_days 中 LimitUpDays>=2；连板率 = 连板数 / 涨停总数(含ST)
# 跌停/到过跌停：westock 仅给 CNT_REACH_DNLIMIT(无法区分收盘跌停与盘中触及)，两列同值
D = {
 "2026-08-17": dict(wd="周一", eff=106, l20=14, ld=0,  rld=0,  up=4335, down=1064, ratio="—",   lbc=15, lbr=13.6, top="金螳螂、澳洋健康、天洋新材（4板）",
                    sh=(3982.65,1.41), sz=(14704.27,2.44), cyb=(3740.16,3.14), money=23874.57, pe=21.99),
 "2026-08-18": dict(wd="周二", eff=80,  l20=6,  ld=0,  rld=0,  up=2121, down=3292, ratio="—",   lbc=18, lbr=22.2, top="神奇制药（4板）",
                    sh=(3990.30,0.19), sz=(14622.50,-0.56), cyb=(3705.56,-0.93), money=24007.75, pe=21.97),
 "2026-08-19": dict(wd="周三", eff=37,  l20=2,  ld=6,  rld=6,  up=449,  down=5069, ratio=6.17, lbc=8,  lbr=21.1, top="京粮控股、红四方、金健米业（3板）",
                    sh=(3894.42,-2.40), sz=(13890.15,-5.01), cyb=(3473.49,-6.26), money=25110.43, pe=21.24),
 "2026-08-20": dict(wd="周四", eff=78,  l20=22, ld=0,  rld=0,  up=4096, down=1347, ratio="—",   lbc=5,  lbr=6.0,  top="金健米业（4板）",
                    sh=(3903.72,0.24), sz=(13972.78,0.59), cyb=(3495.59,0.64), money=20793.63, pe=21.26),
 "2026-08-21": dict(wd="周五", eff=55,  l20=9,  ld=1,  rld=1,  up=2505, down=2862, ratio=55.0, lbc=13, lbr=22.4, top="*ST威领、汉森制药（3板）",
                    sh=(3905.20,0.04), sz=(14094.17,0.87), cyb=(3545.58,1.43), money=18792.64, pe=21.26),
}
ORDER = list(D.keys())

def pct(x):
    return ("+" if x >= 0 else "") + f"{x:.2f}%"

def idx_cell(v):
    price, chg = v
    cls = "up" if chg >= 0 else "down"
    return f"{price:,.2f}<br><span class='{cls}'>{pct(chg)}</span>"

NA = "<span class='na'>待补</span>"

# ---------------- HTML ----------------
groups = [
    ("日期", 2, [("日期", "date")]),
    ("涨停家数", 6, [("有效涨停", "eff"), ("20%涨停", "l20"), ("跌停", "ld"),
                     ("到过跌停", "rld"), ("炸板", "na"), ("中位数涨跌幅<br>(去ST)", "na")]),
    ("涨跌家数", 3, [("上涨家数", "up"), ("下跌家数", "down"), ("涨跌停比例", "ratio")]),
    ("连板", 3, [("连板数", "lbc"), ("连板率", "lbr"), ("最高板代表", "top")]),
    ("市值(亿)", 2, [("总市值", "na"), ("流通市值", "na")]),
    ("两融余额(亿)", 4, [("上海", "na"), ("深圳", "na"), ("北京", "na"), ("合计", "na")]),
    ("指数", 4, [("上海", "sh"), ("深圳", "sz"), ("创业板", "cyb"), ("北证", "na")]),
    ("成交量", 5, [("上海", "na"), ("深圳", "na"), ("创业板", "na"), ("北证", "na"), ("合计", "na")]),
    ("中午", 1, [("中午成交量", "na")]),
    ("PE", 3, [("上海", "na"), ("深圳", "na"), ("创业板", "na")]),
    ("平均", 1, [("平均股价(元)", "na")]),
]

def cell(d, key):
    if key == "date":
        return f"<b>{d['wd']}</b><br><span class='sub'>{ORDER.index(d['wd']) if False else ''}</span>"  # placeholder
    if key == "na":
        return NA
    if key == "sh":
        return idx_cell(d["sh"])
    if key == "sz":
        return idx_cell(d["sz"])
    if key == "cyb":
        return idx_cell(d["cyb"])
    v = d[key]
    if key == "top":
        return f"<span class='top'>{v}</span>"
    if key == "lbr":
        return f"{v:.1f}%"
    if key == "ratio":
        return v if v == "—" else f"{v:.2f}"
    return f"{v:,}" if isinstance(v, int) else str(v)

# date cells
def date_cell(k):
    return f"<b>{k[5:]}</b><br><span class='sub'>{D[k]['wd']}</span>"

thead = "<thead><tr>"
for gname, span, cols in groups:
    thead += f"<th class='grp' colspan='{span}'>{gname}</th>"
thead += "</tr><tr>"
for gname, span, cols in groups:
    for cname, _ in cols:
        thead += f"<th class='subh'>{cname}</th>"
thead += "</tr></thead>"

tbody = "<tbody>"
for k in ORDER:
    d = D[k]
    tbody += "<tr>"
    tbody += f"<td class='date'>{date_cell(k)}</td>"
    for gname, span, cols in groups[1:]:
        for cname, ckey in cols:
            if ckey == "date":
                continue
            tbody += f"<td>{cell(d, ckey)}</td>"
    tbody += "</tr>"
tbody += "</tbody>"

html = f"""<!DOCTYPE html>
<html lang='zh-CN'><head><meta charset='UTF-8'>
<meta name='viewport' content='width=device-width,initial-scale=1.0'>
<title>A股涨停复盘周表 2026-08-17~08-21</title>
<style>
* {{ box-sizing:border-box; }}
body {{ margin:0; font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;
  background:#f5f6f8; color:#1f2733; padding:24px; }}
.wrap {{ max-width:1500px; margin:0 auto; }}
h1 {{ font-size:22px; margin:0 0 4px; color:#1f2733; }}
.meta {{ font-size:13px; color:#6b7280; margin:0 0 16px; line-height:1.7; }}
.legend {{ font-size:12px; color:#6b7280; margin:0 0 14px; }}
.legend b {{ color:#d8392b; }} .legend i {{ color:#1a9e5a; font-style:normal; }}
.legend .na {{ color:#9aa0a6; background:#eceef1; padding:1px 6px; border-radius:4px; }}
table {{ border-collapse:collapse; width:100%; font-size:12.5px; background:#fff;
  border:1px solid #e2e5ea; border-radius:10px; overflow:hidden; box-shadow:0 2px 10px rgba(0,0,0,.05); }}
th.grp {{ background:#2f3a4a; color:#fff; font-size:12px; padding:8px 6px; text-align:center; border-right:1px solid #43505f; }}
th.subh {{ background:#eef1f5; color:#3a4452; font-weight:600; padding:6px 6px; text-align:center; border-bottom:1px solid #dfe3e9; border-right:1px solid #eef1f5; white-space:nowrap; }}
td {{ padding:7px 8px; text-align:center; border-bottom:1px solid #eef1f5; border-right:1px solid #f1f3f6; vertical-align:middle; }}
td.date {{ background:#fafbfc; font-weight:700; white-space:nowrap; }}
td.date .sub {{ font-weight:400; color:#8a9099; font-size:11px; }}
tr:hover td {{ background:#f8fafc; }}
.up {{ color:#d8392b; font-weight:600; }} .down {{ color:#1a9e5a; font-weight:600; }}
.na {{ color:#9aa0a6; background:#eceef1; border-radius:4px; padding:1px 6px; font-size:11px; }}
.top {{ color:#b8860b; font-weight:600; }}
.foot {{ font-size:12px; color:#6b7280; line-height:1.8; margin-top:16px; background:#fff;
  border:1px solid #e2e5ea; border-radius:10px; padding:14px 16px; }}
.foot b {{ color:#d8392b; }} .foot code {{ background:#f0f2f5; padding:1px 5px; border-radius:4px; color:#33414f; }}
</style></head><body><div class='wrap'>
<h1>A股涨停复盘周表 · 2026-08-17 ~ 2026-08-21（本周）</h1>
<p class='meta'>数据来源：腾讯自选股 <code>westock-mcp</code>（data_market_overview / tool_ranking limitup_days），按交易日逐日回拉。
红色=涨、绿色=跌（A股惯例）。<b>"待补"</b> = 该指标在 westock-mcp 标准输出中未提供，需另找数据源。</p>
<div class='legend'>图例：<b>涨(红)</b> / <i>跌(绿)</i> / <span class='na'>待补</span>（数据源缺失）</div>
<table>{thead}{tbody}</table>
<div class='foot'>
<b>口径说明：</b><br>
1. <b>有效涨停</b>=非ST涨停（含创业板/科创板20%板、北交所30%板）；本表未剔除新股(N日)，如需剔除请告知。<br>
2. <b>20%涨停</b>=创业板(300/301)+科创板(688)涨停只数；北交所30%板已计入"有效涨停"但未单列。<br>
3. <b>跌停 / 到过跌停</b>：westock 仅提供 <code>CNT_REACH_DNLIMIT</code>（无法区分收盘跌停与盘中触及跌停），两列同值；炸板数量未提供。<br>
4. <b>涨跌停比例</b>=有效涨停 ÷ 跌停家数；跌停为0的交易日记为"—"。<br>
5. <b>连板数</b>=limitup_days 中连续涨停≥2板；<b>连板率</b>=连板数 ÷ 当日涨停总数(含ST)。<b>最高板代表</b>含ST股（如 08-21 的 *ST威领）。<br>
6. <b>指数</b>仅含 上证 / 深证 / 创业板（收盘+涨跌幅），北证未提供。<br>
7. <b>可得但未单列的指标</b>（可补入）：① 沪深成交额(亿) 合计——08-17 {D['2026-08-17']['money']:.0f}、08-18 {D['2026-08-18']['money']:.0f}、08-19 {D['2026-08-19']['money']:.0f}、08-20 {D['2026-08-20']['money']:.0f}、08-21 {D['2026-08-21']['money']:.0f}（注意：这是<b>成交额</b>非<b>成交量</b>，且为沪+深不含北证）；② 中证全指 PE_TTM——21.99 / 21.97 / 21.24 / 21.26 / 21.26（非分市场PE）。<br>
8. <b>完全缺失（需另源）</b>：炸板数量、中位数涨跌幅(去ST)、回头波数、总市值、流通市值、两融余额(沪/深/京/合计)、北证指数、成交量(沪/深/创业/京/合计)、中午成交量、分市场PE(沪/深/创业)、平均股价。
</div>
</div></body></html>"""

with open(OUT_HTML, "w", encoding="utf-8") as f:
    f.write(html.replace("><", ">\n<"))

# ---------------- CSV ----------------
csv_cols = ["日期","星期","有效涨停数量","20%涨停数量","跌停数量","到过跌停的数量","炸板数量",
            "中位数涨跌幅(去ST)","上涨家数","下跌家数","涨跌停比例","连板数","连板率","最高板代表",
            "总市值(亿)","流通市值(亿)","两融-上海","两融-深圳","两融-北京","两融-合计",
            "指数-上海","指数-深圳","指数-创业板","指数-北证",
            "成交量-上海","成交量-深圳","成交量-创业板","成交量-北证","成交量-合计",
            "中午成交量","PE-上海","PE-深圳","PE-创业板","平均股价(元)","成交额沪深合计(亿·代理)","中证全指PE"]

def csv_row(k):
    d = D[k]
    return [k, d["wd"],
            d["eff"], d["l20"], d["ld"], d["rld"], "待补", "待补",
            d["up"], d["down"], d["ratio"], d["lbc"], f"{d['lbr']:.1f}%", d["top"],
            "待补","待补","待补","待补","待补","待补",
            f"{d['sh'][0]:.2f} ({pct(d['sh'][1])})", f"{d['sz'][0]:.2f} ({pct(d['sz'][1])})",
            f"{d['cyb'][0]:.2f} ({pct(d['cyb'][1])})", "待补",
            "待补","待补","待补","待补","待补","待补","待补","待补","待补","待补",
            f"{d['money']:.0f}", f"{d['pe']:.2f}"]

with open(OUT_CSV, "w", encoding="utf-8-sig", newline="") as f:
    w = csv.writer(f)
    w.writerow(csv_cols)
    for k in ORDER:
        w.writerow(csv_row(k))

print("OK:", OUT_HTML)
print("OK:", OUT_CSV)
