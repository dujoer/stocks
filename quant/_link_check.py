#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A股看板项目 · 网页端链接自检工具（量化项目通用）

扫描项目内所有 HTML 文件的本地 href 链接，检测断链（指向不存在的文件）。
默认仅扫描报告、不修改任何文件；加 --clean 时把所有 dead href 改为 href="#"
（按钮文字保留、仅阻止跳转到 404）。

用法：
    cd G:\\ai\\股票
    python quant/_link_check.py                   # 默认递归扫描 web/**/*.html + 根 index.html
    python quant/_link_check.py --clean           # 同上，发现 dead href 时直接改成 #
    python quant/_link_check.py --files "web/lhb/lhb_2026-08-*.html"   # 只扫描某个 glob
    python quant/_link_check.py --files "web/**/*.html" --clean        # 递归 + 清理

退出码：
    0 = 无断链（含已 --clean 后再跑一次）
    1 = 仍有断链（脚本默认不自动清，需手动 --clean 或人工处理）

适用：
    任何一次手动更新后、推送前必跑，作为最后一道闸口。
"""
from __future__ import annotations
import argparse
import glob as _glob
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(ROOT, "web")

EXCLUDE_PREFIX = (
    "#", "http://", "https://", "mailto:", "javascript:", "data:", "//",
)
HREF_RE = re.compile(r'href\s*=\s*["\']([^"\']+)["\']', re.I)


def collect_html_files() -> list[str]:
    out = [os.path.join(ROOT, "index.html")]
    for dirpath, _, filenames in os.walk(WEB):
        for fn in filenames:
            if fn.endswith(".html"):
                out.append(os.path.join(dirpath, fn))
    return [f for f in out if os.path.exists(f)]


def scan(html_files: list[str], clean: bool = False) -> tuple[int, int]:
    files_with_broken = 0
    broken_total = 0
    for hf in html_files:
        base = os.path.dirname(hf)
        with open(hf, encoding="utf-8", errors="ignore") as f:
            txt = f.read()
        file_broken: list[tuple[str, str]] = []
        for m in HREF_RE.findall(txt):
            t = m.strip()
            if not t or t.startswith(EXCLUDE_PREFIX):
                continue
            cleaned = t.split("#")[0].split("?")[0]
            if not cleaned:
                continue
            target = os.path.normpath(os.path.join(base, cleaned))
            if not os.path.exists(target):
                file_broken.append((t, os.path.relpath(target, ROOT)))
        if file_broken:
            files_with_broken += 1
            broken_total += len(file_broken)
            rel = os.path.relpath(hf, ROOT)
            print(f"\n[{rel}] 断链 {len(file_broken)} 条")
            for link, tgt in file_broken:
                print(f"    {link}  →  缺失: {tgt}")
        if clean and file_broken:
            new_txt = txt
            changed = 0
            for link, _ in file_broken:
                pat = r'href\s*=\s*["\']' + re.escape(link) + r'["\']'
                new_txt2 = re.sub(pat, 'href="#"', new_txt)
                if new_txt2 != new_txt:
                    new_txt = new_txt2
                    changed += 1
            if changed:
                with open(hf, "w", encoding="utf-8") as f:
                    f.write(new_txt)
                print(f"    → 已改 {changed} 处 dead href 为 href=\"#\"")
    return files_with_broken, broken_total


def main() -> int:
    ap = argparse.ArgumentParser(description="A股看板项目 网页端链接自检")
    ap.add_argument("--clean", action="store_true", help="把 dead href 改为 href=\"#\"")
    ap.add_argument("--files", help="glob 模式，仅扫描匹配文件（如 web/lhb_2026-08-*.html）")
    args = ap.parse_args()

    if args.files:
        # 允许相对项目根或当前 cwd
        pattern = args.files
        if not os.path.isabs(pattern):
            pattern_candidates = [os.path.join(ROOT, pattern), pattern]
        else:
            pattern_candidates = [pattern]
        html_files: list[str] = []
        for cand in pattern_candidates:
            html_files = sorted(_glob.glob(cand, recursive=True))
            if html_files:
                break
    else:
        html_files = collect_html_files()

    print(f"扫描 {len(html_files)} 个 HTML 文件 ...")
    files_with_broken, broken_total = scan(html_files, clean=args.clean)
    print()
    print(f"=== 总计 === 断链文件 {files_with_broken} 个 / 断链链接 {broken_total} 条")
    if files_with_broken > 0:
        if args.clean:
            print("CLEAN 模式已执行，请重新跑一次确认归零。")
        print("HAS_BROKEN_LINKS")
        return 1
    if args.clean:
        print("CLEAN 模式：本次无需修改。")
    print("ALL_CLEAN")
    return 0


if __name__ == "__main__":
    sys.exit(main())