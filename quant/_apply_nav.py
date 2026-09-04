# -*- coding: utf-8 -*-
"""为缺少统一导航的看板页面注入 selfcontained_nav（自带样式、金色主题、幂等且自愈）。

覆盖范围（全站 web/ 分层后）：
  - web/<板块>/*.html（递归扫描整个 web/ 子目录树）
  - 仓库根目录 index.html 由 build_portal 写入 PORTAL_NAV，跳过。
  - web/index.html（旧龙虎榜入口）本就不应存在，跳过。

相对路径按【页面所在子目录】计算：
  - web/<section>/page.html  → current_web_dir="<section>", home="../../index.html"
  - web/ 根扁平页（应已删除）  → current_web_dir="",          home="../index.html"

幂等 + 自愈（关键）：无论页面里现有的统一导航是「旧版（无哨兵）」还是「新版（带哨兵）」，
先把已有的 selfcontained 导航块剥离，再重新注入当前版本的导航，避免出现双导航条。
生成器自带 <div class='topnav'> 的页面跳过，由生成器自行维护。
"""
import os, re
from _nav import selfcontained_nav, NAV_SENTINEL

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(ROOT, "web")
SENTINEL = NAV_SENTINEL

# 匹配 selfcontained 导航块（无论是否带哨兵）：<div style='...border-bottom:...font-size:13px;' ...>...</div>
_NAV_DIV_RE = re.compile(
    r"<div style='[^']*border-bottom:1px solid rgba\(184,137,59,\.3\);font-size:13px;'[^>]*>.*?</div>",
    re.S)
# 旧版导航可能带「哨兵注释 + 导航块」整体，须一并剥离
_SENTINEL_BLOCK_RE = re.compile(
    re.escape(SENTINEL) + r"\n" + _NAV_DIV_RE.pattern, re.S)


def _strip_existing_nav(s: str) -> str:
    # 优先尝试「哨兵 + 导航块」整体剥离
    s2 = _SENTINEL_BLOCK_RE.sub("", s, count=1)
    if s2 != s:
        return s2
    # 否则尝试仅剥离导航块（旧版无哨兵）
    return _NAV_DIV_RE.sub("", s, count=1)


targets = []  # (abs_path, current_web_dir, home, prefix)
for dirpath, _, filenames in os.walk(WEB):
    for fn in sorted(filenames):
        if not fn.endswith(".html"):
            continue
        ap = os.path.join(dirpath, fn)
        rel_dir = os.path.relpath(dirpath, WEB).replace(os.sep, "/")
        if rel_dir == ".":
            # web/ 根扁平页（应已删除）；web/index.html 旧入口也跳过
            if fn == "index.html" and os.path.abspath(dirpath) == WEB:
                continue
            cur, home, prefix = "", "../index.html", ""
        else:
            cur, home, prefix = rel_dir, "../../index.html", ""
        targets.append((ap, cur, home, prefix))

done = skipped = healed = 0
for path, cur, home, prefix in targets:
    s = open(path, encoding="utf-8").read()
    rel_path = os.path.relpath(path, ROOT).replace(os.sep, "/")

    if "<div class='topnav'>" in s:
        skipped += 1  # 生成器自己的导航，交由生成器维护
        continue

    had = (SENTINEL in s) or bool(_NAV_DIV_RE.search(s))
    if had:
        s = _strip_existing_nav(s)
        healed += 1

    m = re.search(r"<body[^>]*>", s)
    if not m:
        print(f"    ⚠ 无 <body> 跳过: {rel_path}")
        skipped += 1
        continue
    nav = selfcontained_nav(current_web_dir=cur, home=home, prefix=prefix)
    s = s[:m.end()] + "\n" + nav + "\n" + s[m.end():]
    open(path, "w", encoding="utf-8").write(s)
    done += 1
print(f"OK: 写入 {done} 个（其中自愈重注入 {healed} 个），跳过 {skipped} 个（生成器自带导航/无 body）")
