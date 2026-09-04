# -*- coding: utf-8 -*-
"""安全清理：删除 web/ 根扁平 HTML、旧的 web/index.html 龙虎榜入口、market-trend/*.html。
仅当「分层等价文件」存在时才删除，否则跳过并打印警告（fail-safe）。
删除前先打印将要删除的清单，确认无误后执行。
"""
import os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(ROOT, "web")
MT = os.path.join(ROOT, "market-trend")

# web/ 根扁平文件 -> 分层等价文件（相对 web/ 根）
# 重命名的扁平入口：扁平名 -> 分层新名
NAME_MAP = {
    "block.html": os.path.join(WEB, "block", "index.html"),
    "block_archive.html": os.path.join(WEB, "block", "archive.html"),
    "daily_overview.html": os.path.join(WEB, "market", "index.html"),
    "exec.html": os.path.join(WEB, "exec", "index.html"),
    "sections.html": os.path.join(WEB, "sections", "index.html"),
    "sector-strength-index.html": os.path.join(WEB, "sector", "index.html"),
    "sector-strength-trend.html": os.path.join(WEB, "sector", "trend.html"),
}
FLAT_TO_LAYERED = {}
for fn in os.listdir(WEB):
    full = os.path.join(WEB, fn)
    if os.path.isfile(full) and fn.endswith(".html"):
        if fn in NAME_MAP:
            FLAT_TO_LAYERED[fn] = NAME_MAP[fn]
        elif fn == "index.html":
            # 旧龙虎榜入口 -> web/lhb/index.html
            FLAT_TO_LAYERED[fn] = os.path.join(WEB, "lhb", "index.html")
        else:
            # 形如 daily_overview_2026-09-04.html / lhb_2026-09-04.html / block_2026-09-04.html ...
            # 在 web/<section>/ 下寻找同名文件
            found = None
            for dirpath, _, files in os.walk(WEB):
                if os.path.abspath(dirpath) == os.path.abspath(WEB):
                    continue
                if fn in files:
                    found = os.path.join(dirpath, fn)
                    break
            FLAT_TO_LAYERED[fn] = found  # 可能 None


# market-trend/*.html -> web/psychology/<同名>
MT_TO_PSY = {}
if os.path.isdir(MT):
    for fn in os.listdir(MT):
        full = os.path.join(MT, fn)
        if os.path.isfile(full) and fn.endswith(".html"):
            MT_TO_PSY[fn] = os.path.join(WEB, "psychology", fn)

to_delete = []
warn = []
for fn, layered in FLAT_TO_LAYERED.items():
    if layered and os.path.exists(layered):
        to_delete.append(os.path.join(WEB, fn))
    else:
        warn.append((os.path.join(WEB, fn), layered))
for fn, psy in MT_TO_PSY.items():
    if psy and os.path.exists(psy):
        to_delete.append(os.path.join(MT, fn))
    else:
        warn.append((os.path.join(MT, fn), psy))

print(f"=== 将删除 {len(to_delete)} 个文件 ===")
for p in sorted(to_delete):
    print("  DEL", os.path.relpath(p, ROOT))
if warn:
    print(f"\n=== ⚠ 跳过 {len(warn)} 个（找不到分层等价文件，未删除）===")
    for p, tgt in warn:
        print("  SKIP", os.path.relpath(p, ROOT), "->", (os.path.relpath(tgt, ROOT) if tgt else "NONE"))

if "--go" not in sys.argv:
    print("\n[dry-run] 加参数 --go 才真正删除。")
    sys.exit(0)

for p in to_delete:
    try:
        os.remove(p)
        print("已删除", os.path.relpath(p, ROOT))
    except Exception as e:
        print("删除失败", os.path.relpath(p, ROOT), e)
print(f"\n完成：删除 {len(to_delete)} 个冗余扁平文件。")
