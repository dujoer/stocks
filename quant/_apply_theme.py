# -*- coding: utf-8 -*-
"""统一设计系统后处理器：把 quant/_theme.css 与 quant/_app.js 注入所有页面，
并为符合条件的列表表开启「点表头排序 + 搜索筛选」。幂等、可重复运行。

用法：
  python quant/_apply_theme.py            # 处理 web/ 下全部 html + index.html
  python quant/_apply_theme.py --dry      # 仅统计将改动的文件，不写盘
"""
from __future__ import annotations
import os, re, sys, glob, argparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # G:/ai/股票
WEB = os.path.join(ROOT, "web")
THEME = open(os.path.join(ROOT, "quant", "_theme.css"), encoding="utf-8").read()
APP = open(os.path.join(ROOT, "quant", "_app.js"), encoding="utf-8").read()
from _nav import topnav as _nav_topnav

# 旧 selfcontained_nav 内联金色药丸块的匹配（顺序无关，更鲁棒）
_SELF_NAV_RE = re.compile(
    r"<div style='(?=[^']*rgba\(184,137,59,\.3\))(?=[^']*font-size:13px)[^']*'[^>]*>.*?</div>",
    re.S)

THEME_BLOCK = "<!--WB_THEME--><style id='wb-theme'>\n" + THEME + "\n</style><!--/WB_THEME-->"
APP_BLOCK = "<!--WB_APP--><script id='wb-app'>\n" + APP + "\n</script><!--/WB_APP-->"

POLLUT = re.compile(r"\s*data-page-node-id=\"[^\"]*\"")
# 排除卡片式/排名卡式细节表（class 可能带引号），避免给个股卡片表加搜索框
SKIP_CLASS = re.compile(r"class\s*=\s*['\"][^'\"]*\b(?:card|gtable)\b", re.I)
ENDHEAD_RE = re.compile(r"</head>", re.I)
ENDBODY_RE = re.compile(r"</body>", re.I)
TOPNAV_OPEN_RE = re.compile(r"<div class=['\"]topnav['\"]>")
NAVGRP_OPEN_RE = re.compile(r"<div class=['\"]navgrp['\"]>")
HOME_A_RE = re.compile(r"<a\s+href=['\"][^'\"]*['\"]\s+class=['\"]home['\"]>首页</a>")


def _strip_balanced_div(s: str, open_re) -> str:
    """移除所有 open_re 匹配的 <div …>…</div> 块（按 <div>/</div> 计数配对）。"""
    out = s
    while True:
        m = open_re.search(out)
        if not m:
            return out
        i, depth = m.end(), 1
        while i < len(out) and depth > 0:
            nxt = out.find("<div", i)
            end = out.find("</div>", i)
            if nxt != -1 and (end == -1 or nxt < end):
                depth += 1
                i = nxt + 4
            elif end != -1:
                depth -= 1
                i = end + 6
            else:
                break
        out = out[:m.start()] + out[i:]


def strip_topnav(s: str) -> str:
    """完整移除所有 <div class='topnav'>…</div>（含嵌套的 .navgrp 子块）。

    注意：不能用 `.*?</div>` 非贪婪匹配——分组导航内含多个 </div>，
    非贪婪会在第一个 </div> 处截断，留下半截导航残片（会与注入的新导航
    重叠成"多套导航"，且高亮/对齐失效）。这里按 <div>/</div> 计数找配对闭合。
    """
    return _strip_balanced_div(s, TOPNAV_OPEN_RE)


def strip_nav_fragments(s: str) -> str:
    """清理历史遗留的半截导航：孤立的 .navgrp 块、脱离 topnav 的「首页」链接。"""
    s = _strip_balanced_div(s, NAVGRP_OPEN_RE)
    s = HOME_A_RE.sub("", s)
    return s


def strip_pollution(s: str) -> str:
    return POLLUT.sub("", s)


_GOLD_MAP = [
    (re.compile(r"#b8893b", re.I), "#1a73e8"),
    (re.compile(r"#caa15a", re.I), "#5b8def"),
    (re.compile(r"#a9792f", re.I), "#1967d2"),
    (re.compile(r"#d8b46a", re.I), "#8ab4f8"),
    (re.compile(r"#fbf6ee", re.I), "#e8f0fe"),
    (re.compile(r"#efe2c9", re.I), "#c5d8fb"),
    (re.compile(r"#f6f4ef", re.I), "#f1f3f4"),
    (re.compile(r"rgba\s*\(\s*184\s*,\s*137\s*,\s*59", re.I), "rgba(26,115,232"),
    (re.compile(r"rgb\s*\(\s*184\s*,\s*137\s*,\s*59\s*\)", re.I), "rgb(26,115,232)"),
]


def neutralize_gold(s: str) -> str:
    """把页面自身样式里的金色系统一映射为蓝色系，确保全站无金。"""
    # 保护已注入的主题/脚本块（虽然主题内已无金色）
    theme_blocks = list(re.finditer(r"<!--WB_THEME-->.*?<!--/WB_THEME-->", s, re.S))
    app_blocks = list(re.finditer(r"<!--WB_APP-->.*?<!--/WB_APP-->", s, re.S))
    placeholders = []
    def shield(seg):
        placeholders.append(seg)
        return f"\x00{len(placeholders)-1}\x00"
    s = re.sub(r"<!--WB_THEME-->.*?<!--/WB_THEME-->", lambda m: shield(m.group(0)), s, flags=re.S)
    s = re.sub(r"<!--WB_APP-->.*?<!--/WB_APP-->", lambda m: shield(m.group(0)), s, flags=re.S)
    for pat, repl in _GOLD_MAP:
        s = pat.sub(repl, s)
    for i, seg in enumerate(placeholders):
        s = s.replace(f"\x00{i}\x00", seg)
    return s


def inject_theme(s: str) -> str:
    # 强制替换已有主题块，确保 _theme.css 修改后全站同步刷新
    s = re.sub(r"<!--WB_THEME-->.*?<!--/WB_THEME-->", "", s, flags=re.S)
    s = re.sub(r"<style\s+id=['\"]wb-theme['\"][^>]*>.*?</style>", "", s, flags=re.S)
    if ENDHEAD_RE.search(s):
        return ENDHEAD_RE.sub(lambda m: THEME_BLOCK + "</head>", s, count=1)
    return THEME_BLOCK + s


def inject_app(s: str) -> str:
    # 强制替换已有通用脚本块，确保 _app.js 修改后全站同步刷新
    s = re.sub(r"<!--WB_APP-->.*?<!--/WB_APP-->", "", s, flags=re.S)
    s = re.sub(r"<script\s+id=['\"]wb-app['\"][^>]*>.*?</script>", "", s, flags=re.S)
    if ENDBODY_RE.search(s):
        return ENDBODY_RE.sub(lambda m: APP_BLOCK + "</body>", s, count=1)
    return s + APP_BLOCK


def add_sort_filter(s: str) -> str:
    """给符合条件的列表表加 data-wb（通用 JS 据此开启排序+筛选）。
    判定：有 <thead> 且 th>=2、tbody 行>=3、无已有 th.sort、表自身 class 非 card/gtable。"""
    opens = list(re.finditer(r"<table\b[^>]*>", s, flags=re.I))
    pairs = []
    for m in opens:
        depth, i, end = 0, m.end(), None
        while i < len(s):
            if s[i:i + 6].lower() == "<table":
                depth += 1
            elif s[i:i + 7].lower() == "</table":
                if depth == 0:
                    end = i
                    break
                depth -= 1
            i += 1
        if end is not None:
            pairs.append((m, end))

    for m, end in reversed(pairs):  # 从后往前，避免偏移
        tag = m.group(0)
        seg = s[m.start(): end]
        # 自愈：卡片式细节表若误带 data-wb，先剥离
        if SKIP_CLASS.search(tag) and "data-wb" in tag:
            s = s[: m.start()] + tag.replace(" data-wb", "") + s[m.end():]
            continue
        if "data-wb" in tag:
            continue
        if "th.sort" in seg or "class='sort'" in seg or 'class="sort"' in seg:
            continue  # 已有自备排序
        ths = len(re.findall(r"<th\b", seg, flags=re.I))
        tb = re.search(r"<tbody\b[^>]*>(.*?)</tbody>", seg, flags=re.S | re.I)
        rowseg = tb.group(1) if tb else seg
        rows = len(re.findall(r"<tr\b", rowseg, flags=re.I))
        if ths < 2 or rows < 3:
            continue
        if SKIP_CLASS.search(tag):
            continue
        newtag = tag.rstrip()[:-1].rstrip() + " data-wb>"
        s = s[: m.start()] + newtag + s[m.end():]
    return s


def normalize_nav(s: str, rel_dir: str, prefix: str = "", home: str | None = None) -> str:
    """把页面导航统一替换为当前 _nav.topnav()（14 项全清单 + 首页，单一来源）。
    rel_dir: 相对 web/ 的子目录（"." 表示 web 根扁平页）。
    prefix:  给规范路径加前缀（仓库根 index.html 用 web/）。
    home:    首页链接，默认按深度自动计算。
    """
    if home is None:
        if rel_dir in (".", ""):
            cur, home = "", "../index.html"
        else:
            cur, home = rel_dir, "../../index.html"
    else:
        cur = "" if rel_dir in (".", "") else rel_dir
    new_nav = _nav_topnav(current_web_dir=cur, home=home, prefix=prefix)

    # 1) 清掉旧的内联金色药丸导航
    s = _SELF_NAV_RE.sub("", s)
    # 2) 清掉已有的 UNIFIED_NAV 哨兵（避免空行堆积）
    s = re.sub(r"<!--\s*UNIFIED_NAV\s*-->\n?", "", s)
    # 3) 清掉已有 topnav（含嵌套分组）+ 历史遗留的半截 navgrp / 首页残片
    s = strip_topnav(s)
    s = strip_nav_fragments(s)
    body_m = re.search(r"<body\b[^>]*>", s, re.I)
    if body_m:
        pos = body_m.end()
        # 幂等关键：先把 <body> 之后的历史空行收敛成恰好一个 \n，再插入导航。
        # 旧写法 s[:pos] + "\n" + nav + s[pos:] 会让 strip_topnav 残留的空行逐次累积，
        # 每次 _apply_theme 都让页面长 1 字节 → 238 页全部进差集 → 每次推送白传 ~32MB。
        rest = re.sub(r"^\s*\n", "\n", s[pos:], count=1)
        # 幂等关键（补）：若 <body> 之后紧跟的是同行内容（不少生成器写 <body><div class="wrap">），
        # 导航会与它粘在同一行；下一遍 strip_topnav 删掉导航后又会补一个换行，
        # 导致「生成器新页 → _apply_theme 要跑两遍才收敛」，每遍全站进差集、白推一份。
        # 这里主动保证 nav 之后恰好一个 \n，首遍即终态。
        if not rest.startswith("\n"):
            rest = "\n" + rest
        s = s[:pos] + "\n" + new_nav + rest
    else:
        s = new_nav + s
    return s


# ---------- 个股外链（东方财富） ----------
# 站点有 30+ 个生成器 + 200 多张历史归档页，逐个改生成器只能覆盖「以后新生成的页」。
# 这里挂在主题注入之后统一跑一遍，新页老页一起覆盖；详见 quant/linkify.py。
_LK = {"fn": None, "n2c": None, "c2n": None}


def linkify_stocks(s: str):
    """给页面里的个股名称加东财外链。返回 (新HTML, 命中数)。"""
    if _LK["fn"] is None:
        try:
            sys.path.insert(0, os.path.join(ROOT, "quant"))
            import linkify as _LKmod
            n2c, c2n = _LKmod.L.name_map()
            _LK.update(fn=_LKmod.scan_html, n2c=n2c, c2n=c2n)
        except Exception as e:                                   # 名称表缺失等
            print("[_apply_theme] 个股外链模块不可用，本轮跳过：%s" % e)
            _LK["fn"] = False
    if _LK["fn"] is False or not _LK["n2c"]:
        return s, 0
    return _LK["fn"](s, _LK["n2c"], _LK["c2n"])


def process(path: str) -> bool:
    s = open(path, encoding="utf-8", errors="ignore").read()
    orig = s
    s = strip_pollution(s)
    s = inject_theme(s)
    s = inject_app(s)
    s = add_sort_filter(s)
    s = neutralize_gold(s)

    rel = os.path.relpath(path, ROOT).replace(os.sep, "/")
    if rel == "index.html":
        # 仓库根门户：导航路径需加 web/ 前缀，首页指向自身
        s = normalize_nav(s, "", prefix="web/", home="index.html")
    elif rel.startswith("web/"):
        rel_dir = os.path.relpath(os.path.dirname(path), WEB).replace(os.sep, "/")
        if rel_dir == ".":
            rel_dir = ""
        s = normalize_nav(s, rel_dir)

    s = linkify_stocks(s)[0]

    if s != orig:
        open(path, "w", encoding="utf-8").write(s)
        return True
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    files = glob.glob(os.path.join(ROOT, "web", "**", "*.html"), recursive=True)
    files.append(os.path.join(ROOT, "index.html"))
    done = 0
    for f in files:
        s = open(f, encoding="utf-8", errors="ignore").read()
        has = ("id='wb-theme'" in s) or ('id="wb-theme"' in s)
        missing = (not has) or ("data-page-node-id" in s)
        if a.dry:
            if missing:
                done += 1
            continue
        if process(f):
            done += 1
    print(("将改动" if a.dry else "已处理") + " %d 个文件" % done)


if __name__ == "__main__":
    main()
