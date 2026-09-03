# -*- coding: utf-8 -*-
"""为缺少统一导航的看板页面注入 selfcontained_nav（自带样式、金色主题、幂等）。

覆盖范围：
  - web/*.html（排除 web/index.html，它已由 build_dashboards 写入 .topnav）
  - market-trend/*.html（雷达报告 + 索引）
根门户 index.html 由 build_portal.py 直接写入 PORTAL_NAV，此处跳过。

链接相对路径：
  - web/ 内：rel=""（lhb.html 等同目录）
  - market-trend/ 内：rel="../web/"（回指 web/ 子目录）
主页均指向 ../index.html（web 内）或 index.html 由生成器负责（根门户）。

幂等：已含 UNIFIED_NAV 哨兵或 .topnav 的页面跳过。
"""
import os, re
from _nav import selfcontained_nav

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(ROOT, "web")
MT = os.path.join(ROOT, "market-trend")
SENTINEL = "<!-- UNIFIED_NAV -->"

targets = []  # (abs_path, rel)
for fn in sorted(os.listdir(WEB)):
    if fn.endswith(".html") and fn != "index.html":
        targets.append((os.path.join(WEB, fn), ""))
for fn in sorted(os.listdir(MT)):
    if fn.endswith(".html"):
        targets.append((os.path.join(MT, fn), "../web/"))
for fn in sorted(os.listdir(ROOT)):
    if fn.endswith(".html") and fn != "index.html":
        targets.append((os.path.join(ROOT, fn), "web/"))

done = skipped = 0
for path, rel in targets:
    s = open(path, encoding="utf-8").read()
    if SENTINEL in s or "<div class='topnav'>" in s:
        skipped += 1
        continue
    m = re.search(r"<body[^>]*>", s)
    if not m:
        print(f"    ⚠ 无 <body> 跳过: {os.path.relpath(path, ROOT)}")
        skipped += 1
        continue
    nav = selfcontained_nav(rel=rel, home="../index.html")
    s = s[:m.end()] + f"\n{SENTINEL}\n{nav}\n" + s[m.end():]
    open(path, "w", encoding="utf-8").write(s)
    done += 1
    print(f"    + 注入导航: {os.path.relpath(path, ROOT)} (rel='{rel}')")
print(f"OK: 注入 {done} 个，跳过 {skipped} 个（已含导航/无 body/根门户）")
