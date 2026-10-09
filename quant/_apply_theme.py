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
#: 纯跳转桩（meta refresh 重定向页）—— 无正文，不注入主题
REDIRECT_RX = re.compile(r"""<meta[^>]+http-equiv\s*=\s*['"]?refresh""", re.I)
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


# ---------- 数据时间戳条（真实数据更新时间的唯一呈现处） ----------
# 设计取舍：**不显示「渲染时间」**。渲染时间=每次跑 _apply_theme 的当下，
# 全站 385 页会因此每轮都变字节 → 每次推送白传几十 MB（历史上踩过）。
# 只显示「页面自己写在正文里的数据日」，它由生成器写出、稳定、可核对；
# 页面没写数据日的就如实显示「未标注」，不替它编一个。
_HUB_DATES = None


def hub_dates():
    """可用交易日集合（取自统一底座 hub/ 的日切片文件名），升序。"""
    global _HUB_DATES
    if _HUB_DATES is None:
        ds = []
        for p in glob.glob(os.path.join(ROOT, "quant", "hub", "2*")):
            m = re.match(r"^(20\d{2})(\d{2})(\d{2})\.json$", os.path.basename(p))
            if m:
                ds.append("%s-%s-%s" % m.groups())
        _HUB_DATES = sorted(set(ds))
    return _HUB_DATES


# 关键词必须紧跟日期，避免把正文里无关的日期（如「上一期 2026-09-30」）当数据日。
_STAMP_KW = (r"(?:数据基准|数据日期|数据口径|行情口径|数据截至|数据更新|数据日|统计截至|"
             r"最近更新|更新日期|最新交易日|最新一期|最新数据日|最新一日|当前|统计日|快照日|"
             r"截至|口径)")
_STAMP_DATE_RE = re.compile(
    _STAMP_KW + r"\s*[:：]?\s*<?[^0-9]{0,24}?(20\d{2})[-/年.](\d{1,2})[-/月.](\d{1,2})")
_FNAME_DATE_RE = re.compile(r"(20\d{2})[-_]?(\d{2})[-_]?(\d{2})")
# 方法与证据页：这些页面没有「每日数据基准」的概念，别跟日更页一个待遇
_METHOD_PAGE_RE = re.compile(
    r"(?:^|/)[^/]*(?:lab|method|backtest|trend|gate|sens|history|audit|evidence)\.html$", re.I)


def page_data_date(s: str):
    """从页面正文（<body> 后前 24000 字符）提取它自己声明的数据日。找不到返回 None。"""
    i = s.find("<body")
    if i < 0:
        return None
    seg = s[i:i + 24000]
    # 先剥标签：生成器大量写成「数据日期 <b>2026-10-08</b>」，不剥会漏匹配
    txt = re.sub(r"<script\b.*?</script>", " ", seg, flags=re.S | re.I)
    txt = re.sub(r"<[^>]+>", " ", txt)
    txt = re.sub(r"\s+", " ", txt)
    m = _STAMP_DATE_RE.search(txt)
    if not m:
        return None
    y, mo, d = m.groups()
    try:
        return "%04d-%02d-%02d" % (int(y), int(mo), int(d))
    except Exception:
        return None


_FREQ_MAP = None


def page_freq(rel_web: str):
    """该页面所属页面族的更新频率（_page_registry 是唯一权威来源）。
    只有 daily 族的页面「没跟上最新数据日」才值得红字报警；
    研究/证据/方法页（on_demand / ad_hoc）的数据基准天然停在生成那天。"""
    global _FREQ_MAP
    if _FREQ_MAP is None:
        import fnmatch as _fn
        m = []
        try:
            sys.path.insert(0, os.path.join(ROOT, "quant"))
            import _page_registry as R
            for f in R.FAMILIES:
                for p in (f.get("patterns") or []):
                    m.append((p, f.get("freq") or "ad_hoc"))
        except Exception:
            m = []
        _FREQ_MAP = m
    import fnmatch as _fn
    for pat, fq in _FREQ_MAP:
        if _fn.fnmatch(rel_web, pat):
            return fq
    return None


def _stamp_html(path: str, s: str, home: str) -> str:
    """生成数据时间戳条 + 返回入口。"""
    dates = hub_dates()
    newest = dates[-1] if dates else None
    rel = os.path.relpath(path, ROOT).replace(os.sep, "/")
    is_portal = rel == "index.html"
    rel_web = "../index.html" if is_portal else rel[len("web/"):]
    fq = page_freq(rel_web)

    if is_portal:
        # 门户是总览页，自身的「数据日」没有意义 → 直接报全站最新
        cur, note = newest, "<span class='s-l'>全站最新数据日</span>"
        unknown = False
    else:
        cur = page_data_date(s)
        note = "<span class='s-l'>本页数据基准</span>"
        unknown = cur is None

    fn = _FNAME_DATE_RE.search(os.path.basename(path))
    fn_date = None
    if fn and not is_portal:
        try:
            fn_date = "%04d-%02d-%02d" % (int(fn.group(1)), int(fn.group(2)), int(fn.group(3)))
        except Exception:
            fn_date = None

    if fn_date and not is_portal:
        # ★ 归档判定只认「文件名里的日期」：归档页命名就是 `xxx_YYYYMMDD.html`，
        #   而正文里第一个日期常是别的口径（如 block_2026-08-06 页里写着 09-04 的区间），
        #   早前拿「正文日 == 文件名日」做判据 → 一大批归档页被误报成「落后」。
        mid = ("<b class='s-d'>%s</b>"
               "<span class='s-hist'>· 历史归档页（内容即该日快照，不随最新数据日更新）</span>"
               % fn_date)
    elif unknown:
        # 方法与证据页（lab / method / backtest / *_gate / trend / history 等）
        # 本来就没有「每日数据口径」，标红会变成噪声；其余页面没写数据日是真缺口。
        if _METHOD_PAGE_RE.search(rel_web or ""):
            mid = ("<b class='s-d unknown'>方法与证据页</b>"
                   "<span class='s-src'>（样本外检验/方法说明，无每日数据口径；"
                   "口径日期见正文）</span>")
        elif fq and fq != "daily":
            mid = ("<b class='s-d unknown'>未标注</b>"
                   "<span class='s-src'>（该族为 %s 更新，非每日口径）</span>" % fq)
        else:
            mid = ("<b class='s-d unknown'>未标注</b>"
                   "<span class='s-warn'>⚠ 该页正文没写数据日 —— 无法核对是否已更新</span>")
    else:
        mid = "<b class='s-d'>%s</b>" % cur
        if is_portal:
            mid += "<span class='s-src'>（仅代表全站最新；各板块新鲜度见下方卡片）</span>"
        elif newest and cur == newest:
            mid += "<span class='s-ok'>· 当日</span>"
        elif newest and cur < newest:
            # 不报「落后 N 个交易日」：hub 只沉淀近期切片，用它数交易日本身不准，
            # 报一个错的天数比不报更糟。只陈述「落后于全站最新」这个可核对的事实。
            if fq == "daily" and not _METHOD_PAGE_RE.search(rel_web or ""):
                mid += ("<span class='s-warn'>⚠ 落后全站最新 %s（该页属每日更新族，"
                        "未随最新数据日刷新）</span>" % newest)
            else:
                mid += ("<span class='s-src'>· 该族非每日更新（研究/证据/方法页），"
                        "基准为该页最近一次生成日；全站最新 %s</span>" % newest)
        elif newest and cur > newest:
            mid += "<span class='s-src'>· 晚于底座最新（%s）</span>" % newest

    # href 用真链接兜底：从哪来回哪，无历史时跳门户
    return ("<!--WB_STAMP--><div class='wb-stamp'>%s%s"
            "<a class='wb-back' href='%s'>← 返回</a></div><!--/WB_STAMP-->"
            % (note, mid, home))


def inject_fab(s: str, home: str) -> str:
    """右下角浮动：回门户 + 回顶部（回顶部按滚动位置显隐，见 _app.js）。"""
    s = re.sub(r"<!--WB_FAB-->.*?<!--/WB_FAB-->", "", s, flags=re.S)
    fab = ("<!--WB_FAB--><div class='wb-fab'>"
           "<a class='wb-top' href='#' title='回到顶部' aria-label='回到顶部'>↑</a>"
           "<a class='wb-home' href='%s' title='返回门户首页' aria-label='返回门户首页'>⌂</a>"
           "</div><!--/WB_FAB-->" % home)
    if ENDBODY_RE.search(s):
        return ENDBODY_RE.sub(lambda m: fab + "</body>", s, count=1)
    return s + fab


def normalize_nav(s: str, rel_dir: str, prefix: str = "", home: str | None = None,
                  path: str | None = None) -> str:
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
    # 2) 清掉已有的 UNIFIED_NAV 哨兵（避免空行堆积）+ 旧时间戳条
    s = re.sub(r"<!--\s*UNIFIED_NAV\s*-->\n?", "", s)
    s = re.sub(r"<!--WB_STAMP-->.*?<!--/WB_STAMP-->", "", s, flags=re.S)
    # 3) 清掉已有 topnav（含嵌套分组）+ 历史遗留的半截 navgrp / 首页残片
    s = strip_topnav(s)
    s = strip_nav_fragments(s)
    # 3b) 时间戳条紧随导航：数据日取自**替换导航之前**的页面正文（导航本身无日期）
    if path:
        stamp = _stamp_html(path, s, home)
        new_nav = new_nav + "\n" + stamp
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
        s = normalize_nav(s, "", prefix="web/", home="index.html", path=path)
        s = inject_fab(s, "index.html")
    elif rel.startswith("web/"):
        rel_dir = os.path.relpath(os.path.dirname(path), WEB).replace(os.sep, "/")
        if rel_dir == ".":
            rel_dir = ""
        # 返回/回门户的路径按页面深度算（web/a/b.html 与 web/a/index.html 都是 2 层）
        home = "../" * rel.count("/") + "index.html"
        s = normalize_nav(s, rel_dir, home=home, path=path)
        s = inject_fab(s, home)

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
        # ★ 纯跳转桩（<meta http-equiv="refresh">）不注入主题：它没有正文可主题化，
        #   注入一次就白白把 ~23KB 主题塞进去（且每次跳转都要多下载一次）。
        if REDIRECT_RX.search(s):
            continue
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
