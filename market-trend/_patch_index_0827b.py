# -*- coding: utf-8 -*-
"""Second pass: insert 08-27 REPORTS entry (Q) and add 08-27 to traj notes (FK).
Uses robust anchors independent of arrow/tilde glyphs."""
import re

P = "G:/ai/股票/web/psychology/index.html"
s = open(P, encoding="utf-8").read()
fails = []

# ---- Q. REPORTS insert: anchor on end of REPORTS array ----
NEW_TAIL = (
    '    },\n'
    '    {\n'
    '      file:"crowd-psychology-risk-radar-20260827.html", date:"2026-08-27",\n'
    '      risk:"\u9ad8", riskEn:"High",\n'
    '      cycleZh:"\u4fee\u590d\u786e\u8ba4 / \u653e\u91cf\u5171\u632f", cycleEn:"Repair confirmed / volume resonance",\n'
    '      cycleNoteZh:"\u653e\u91cf\u53cd\u5305 / \u91cf\u4ef7\u8fdd\u79bb\u4fee\u590d", cycleNoteEn:"Volume-expanded rebound / divergence repaired",\n'
    '      up:"61%", limitup:"78", board:"5\u677f", turn:"\u00a52.1259\u4e07\u4ebf",\n'
    '      summaryZh:"\u6da8\u80a1\u6bd4\u7531 53% \u56de\u5347\u81f3 61%\u3001\u6da8\u505c 78\u3001\u8dcc\u505c 4\u3001\u6210\u4ea4\u653e\u91cf\u81f3 \u00a52.1259\u4e07\u4ebf\uff08+3172\u4ebf\uff09\uff1b\u6280\u672f\u9762\u6781\u5f3a\uff08MACD\u91d1\u53c9\uff09\u3001\u4e09\u6307\u9f50\u6da8\u8dcc\u5e45\u6269\u5927\uff08\u521b\u4e1a\u677f+1.71%\uff09\u3001\u8fde\u677f\u7ef4\u6301 5 \u677f\uff0c\u91cf\u4ef7\u8fdd\u79bb\u4fee\u590d = \u653e\u91cf\u53cd\u5305 / \u91cf\u4ef7\u5171\u632f\u3002\u4f46\u8d8b\u52bf\u4ecd\u5f31\u3001\u4f30\u503c\u504f\u9ad8\uff08PE\u5206\u4f4d 70-90% \u4e14\u6307\u6570\u53c8\u6da8\uff09\u3001\u7ed3\u6784\u5206\u5316\uff08\u94f6\u884c/\u5149\u4f0f/\u767d\u7535\u9886\u8dcc\uff09\uff0c\u5b98\u65b9\u300c\u72c2\u70ed\u300d\u6807\u7b7e\u4ec5\u56e0\u6da8\u505c>50\u89e6\u53d1\uff08\u771f\u5b9e 61%<70% \u9608\u503c\uff09= \u6807\u7b7e\u7565\u8d85\u524d\u5e7f\u5ea6\u3002",\n'
    '      summaryEn:"Up-ratio recovers 53%\u219261%, 78 limit-up, 4 limit-down, turnover expands to \u00a52.1259tn (+317.2bn); technics extremely-strong (MACD golden cross), all three indices up with widening gains (ChiNext +1.71%), streak holds 5 boards, price-volume divergence repaired = volume-expanded rebound / volume resonance. Yet trend still weak, valuation elevated (PE 70-90% pct while indices rise again), structure diverged (banks/PV/white-goods lead down), and official \'Euphoria\' tag triggered only by limit-up>50 (real 61%<70%) = tag slightly ahead of breadth."\n'
    '    }\n'
    '  ];'
)
m = re.search(r'    \}\n  \];', s)
if not m:
    fails.append("WARN Q: REPORTS closing not found")
else:
    s = s[:m.start()] + NEW_TAIL + s[m.end():]

# ---- FK. traj notes (HTML default + I18N zh) share the tail prefix ----
EXT = '官方「狂热」标签虚高），08-27 转入「修复确认 / 放量共振」（放量反包、成交放量至¥2.1259万亿、涨股比回升至61%、涨停扩至78、三指齐涨涨幅扩大、MACD金叉、量价背离修复，但趋势仍弱、估值偏高、结构分化）'
# HTML traj note
pat_html = r'官方「狂热」标签虚高）。08-22([~～])08-23 周末休市。</p>'
if not re.search(pat_html, s):
    fails.append("WARN FK html: anchor not found")
else:
    s = re.sub(pat_html, EXT + r'。08-22\1-08-23 周末休市。</p>', s, count=1)
# I18N zh t_traj_note
pat_zh = r'官方「狂热」标签虚高）。08-22([~～])08-23 周末休市。",'
if not re.search(pat_zh, s):
    fails.append("WARN FK zh: anchor not found")
else:
    s = re.sub(pat_zh, EXT + r'。08-22\1-08-23 周末休市。",', s, count=1)

open(P, "w", encoding="utf-8").write(s)
print("PATCH2 DONE")
print("\n".join(fails) if fails else "ALL OK")
