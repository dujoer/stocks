# -*- coding: utf-8 -*-
"""
把历史归档页（早期生成的 lhb_/status_/q2 页）中**不完整的旧导航**替换成当前统一导航。
判定标准：若页面导航已含 block.html（即 7 模块齐全）则跳过；否则用统一 topnav 替换其首个
<div class='topnav'>。页面若自带 .topnav CSS 则用 class 版 topnav()；否则用内联版 selfcontained_nav()。
用法：python quant/_fix_archive_nav.py
"""
import os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _nav import topnav, selfcontained_nav

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIRS = [".", "web", "market-trend"]

def rel_home(d):
    if d == ".":
        return "web/", "index.html"
    if d == "web":
        return "", "../index.html"
    if d == "market-trend":
        return "../web/", "../index.html"
    return "", "../index.html"

def has_topnav_css(s):
    return ".topnav" in s and ("<style" in s.lower())

def main():
    changed = []
    for d in DIRS:
        base = os.path.join(ROOT, d)
        if not os.path.isdir(base):
            continue
        rel, home = rel_home(d)
        for fn in sorted(os.listdir(base)):
            if not fn.endswith(".html"):
                continue
            p = os.path.join(base, fn)
            s = open(p, encoding="utf-8", errors="replace").read()
            # 已含 block.html 视为最新导航，跳过
            if "block.html" in s:
                continue
            has_css = has_topnav_css(s)
            new_nav = topnav(rel=rel, home=home) if has_css else selfcontained_nav(rel=rel, home=home)
            # 找到首个 <div class='topnav' ...>...</div>
            pat = re.compile(r"<div class=['\"]topnav['\"]>.*?</div>", re.S | re.I)
            m = pat.search(s)
            if m:
                s2 = pat.sub(new_nav, s, count=1)
                if s2 != s:
                    open(p, "w", encoding="utf-8").write(s2)
                    changed.append((os.path.relpath(p, ROOT).replace("\\", "/"), "topnav" if has_css else "selfcontained"))
            else:
                # 完全没有 topnav 的页面：在 </body> 前注入
                if "</body>" in s:
                    s2 = s.replace("</body>", new_nav + "\n</body>", 1)
                    open(p, "w", encoding="utf-8").write(s2)
                    changed.append((os.path.relpath(p, ROOT).replace("\\", "/"), "injected"))
    print(f"[fix] 已修复 {len(changed)} 个历史页导航：")
    for f, k in changed:
        print(f"  - {f}  ({k})")

if __name__ == "__main__":
    main()
