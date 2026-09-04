# -*- coding: utf-8 -*-
"""为缺少统一导航的看板页面注入 selfcontained_nav（自带样式、金色主题、幂等且自愈）。

覆盖范围：
  - web/*.html（排除 web/index.html，它已由 build_dashboards 写入 .topnav）
  - market-trend/*.html（雷达报告 + 索引）
  - 根目录 *.html（排除 index.html；根门户由 build_portal 写入 PORTAL_NAV）

相对路径按目录计算，切勿写死：
  - web/            → rel="",        home="../index.html"
  - market-trend/   → rel="../web/", home="../index.html"
  - 仓库根目录       → rel="web/",    home="index.html"（写死 ../ 会指向仓库之外）

幂等 + 自愈：
  - 已含 <div class='topnav'> 的页面由生成器负责，跳过；
  - 已含 UNIFIED_NAV 哨兵的页面先剥离旧导航再重新注入，保证路径规则变更时自动同步。
"""
import os, re
from _nav import selfcontained_nav

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(ROOT, "web")
MT = os.path.join(ROOT, "market-trend")
SENTINEL = "<!-- UNIFIED_NAV -->"

# (目录, rel, home, 排除的文件名)
DIRS = [
    (WEB, "", "../index.html", {"index.html"}),
    (MT, "../web/", "../index.html", set()),
    (ROOT, "web/", "index.html", {"index.html"}),
]

# 已注入的导航块（含哨兵），用于重新注入前剥离
NAV_BLOCK_RE = re.compile(
    r"\n" + re.escape(SENTINEL) + r"\n<div style='[^']*'>.*?</div>\n", re.S)

targets = []  # (abs_path, rel, home)
for base, rel, home, exclude in DIRS:
    if not os.path.isdir(base):
        continue
    for fn in sorted(os.listdir(base)):
        if fn.endswith(".html") and fn not in exclude:
            targets.append((os.path.join(base, fn), rel, home))

done = skipped = healed = 0
for path, rel, home in targets:
    s = open(path, encoding="utf-8").read()
    rel_path = os.path.relpath(path, ROOT).replace(os.sep, "/")

    if "<div class='topnav'>" in s:
        skipped += 1  # 生成器自己的导航，交由生成器维护
        continue

    # 自愈：剥离旧导航块（路径规则变更时自动同步）
    if SENTINEL in s:
        s2 = NAV_BLOCK_RE.sub("\n", s, count=1)
        if s2 != s:
            healed += 1
            s = s2
        else:
            # 哨兵存在但块未匹配上，去掉孤立哨兵避免重复注入
            s = s.replace(SENTINEL, "", 1)

    m = re.search(r"<body[^>]*>", s)
    if not m:
        print(f"    ⚠ 无 <body> 跳过: {rel_path}")
        skipped += 1
        continue
    nav = selfcontained_nav(rel=rel, home=home)
    s = s[:m.end()] + f"\n{SENTINEL}\n{nav}\n" + s[m.end():]
    open(path, "w", encoding="utf-8").write(s)
    done += 1
print(f"OK: 写入 {done} 个（其中自愈重注入 {healed} 个），跳过 {skipped} 个（生成器自带导航/无 body）")
