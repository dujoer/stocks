# -*- coding: utf-8 -*-
"""全站个股名称 → 东方财富外链（后处理）。

为什么用后处理而不是逐个改生成器：
  站点有 30+ 个生成器 + 200 多张历史归档页。逐处改生成器只能覆盖「以后新生成的页」，
  历史归档页永远漏，且容易漏掉某个新加的板块。这里统一在 `_apply_theme.py` 之后跑一遍，
  **新页老页一起覆盖**（与 `quant-static-site-integrity` 技能里「注入型脚本」同思路）。

处理范围（只碰「结构化容器」，绝不碰正文散文）：
  1. <td ...>…</td>                                （表格单元格，含单元格内的多个名称）
  2. <span class="cname|nm|sname|stk">…</span>      （卡片标题）
  3. <a class="slk" href="stocks.html#sz000049">名称</a>  → 换成东财外链

安全阀：
  - 只匹配 `quant/_stock_names.json` 里 1:1 可反查的名称（同名不同码的直接放弃）。
  - 名称前一个字符必须是「非中日韩字符」（行首 / 空格 / 标点 / 数字），
    避免把长词里的一截当股票名（如「龙头中际旭创」不链，「（中际旭创）」链）。
  - 名称后 16 字内若出现「有限责任/证券营业部/营业部/分公司/有限公司/开户/席位/专户/资管计划」
    则跳过 —— 否则会误伤「中信证券(山东)有限责任公司…营业部」这类券商营业部名。
  - 已在 <a> 内的一律跳过（幂等；也保护站内既有链接）。

用法：
  python quant/linkify.py            # 全站处理（幂等，随 _apply_theme 一起跑）
  python quant/linkify.py --dry      # 只报告会改多少处
  python quant/linkify.py --file web/tplus/index.html
"""
import os
import re
import sys
import glob
import argparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _emlink as L

ROOT = os.path.dirname(HERE)

# ---------- 容器 ----------
CELL_RE = re.compile(r"(<td\b[^>]*>)(.*?)(</td>)", re.S)
SPAN_RE = re.compile(
    r"(<span\b[^>]*class=['\"](?:cname|nm|sname|stk)['\"][^>]*>)(.*?)(</span>)", re.S)
# 站内旧链接（web/block 用 stocks.html#code）→ 换成东财外链
SLK_RE = re.compile(
    r"<a\b[^>]*href=['\"]stocks\.html#(sh|sz|bj)(\d{6})['\"][^>]*>([^<]*)</a>", re.I)

# 已生成但显示成光秃秃代码的外链 → 回填真实名称（自愈历史产物 / 上游名称为空的页）
EMLK_CODE_RE = re.compile(
    r'(<a class="emlk" href="https://quote\.eastmoney\.com/)(\w{2})(\d{6})'
    r'(\.html"[^>]*>)((?:sh|sz|bj)?\d{6})(</a>)')

CODE_ONLY_RE = re.compile(r"^\s*(?:sh|sz|bj)?\d{6}\s*$")

TAG_RE = re.compile(r"<[^>]*>")

# 名称后若紧跟这些词 → 说的是机构/营业部，不是个股
BAD_RE = re.compile(r"有限责任|证券营业部|营业部|分公司|有限公司|开户|席位|专户|资管计划")
BAD_WIN = 16
MAXLEN = 7          # 名称最长 7 字
MINLEN = 3          # 名称最短 3 字

_CJK = re.compile(r"[\u3400-\u9fff\uff00-\uffef]")


def _is_cjk(ch):
    return bool(_CJK.match(ch)) if ch else False


def _find_names(text, n2c, minlen=MINLEN, maxlen=MAXLEN):
    """贪婪最长匹配，返回 [(start, end, code)]。"""
    n = len(text)
    out = []
    i = 0
    while i < n:
        step = 0
        for Ln in range(min(maxlen, n - i), minlen - 1, -1):
            code = n2c.get(text[i:i + Ln])
            if not code:
                continue
            # 前一个字符是汉字 → 说明是某个长词的一截，同起点更短的名字同样不可信
            if i > 0 and _is_cjk(text[i - 1]):
                break
            if BAD_RE.search(text[i + Ln:i + Ln + BAD_WIN]):
                break
            out.append((i, i + Ln, code))
            step = Ln
            break
        i += step if step else 1
    return out


def _link_text(text, n2c):
    """对一段纯文本加链接，返回 (新文本, 命中数)。"""
    hits = _find_names(text, n2c)
    if not hits:
        return text, 0
    buf = []
    last = 0
    for a, b, code in hits:
        buf.append(text[last:a])
        buf.append(L.link(code, text[a:b], raw=True))
        last = b
    buf.append(text[last:])
    return "".join(buf), len(hits)


def _process_container(inner, n2c):
    """处理容器内部 HTML：逐文本节点加链接，<a> 内跳过。返回 (新 HTML, 命中数)。"""
    if not inner:
        return inner, 0
    out = []
    last = 0
    depth = 0
    hits = 0
    for m in TAG_RE.finditer(inner):
        seg = inner[last:m.start()]
        tag = m.group(0)
        if seg:
            if depth == 0:
                seg, nh = _link_text(seg, n2c)
                hits += nh
            out.append(seg)
        out.append(tag)
        tl = tag.lower()
        if tl.startswith("<a ") or tl.startswith("<a>"):
            depth += 1
        elif tl.startswith("</a"):
            depth = max(0, depth - 1)
        last = m.end()
    seg = inner[last:]
    if seg:
        if depth == 0:
            seg, nh = _link_text(seg, n2c)
            hits += nh
        out.append(seg)
    return "".join(out), hits


def scan_html(s, n2c, c2n=None):
    """返回 (new_html, 命中数)。"""
    total = 0
    c2n = c2n or {}

    def slk(m):
        nonlocal total
        code = (m.group(1) + m.group(2)).lower()
        txt = m.group(3).strip()
        # 站内链接文字为空或只是代码时，换成真实名称
        # （web/block 历史产物里有一批 `<a class='slk' …></a>` 名称是空的）
        if not txt or CODE_ONLY_RE.match(txt):
            txt = c2n.get(code) or txt or code
        a = L.link(code, txt, raw=True)
        if not a or "<a" not in a:
            return m.group(0)
        total += 1
        return a

    s = SLK_RE.sub(slk, s)

    def fixcode(m):
        """把显示成纯代码的东财外链回填为真实名称（幂等：回填后不再匹配）。"""
        nonlocal total
        code = (m.group(2) + m.group(3)).lower()
        nm = c2n.get(code)
        if not nm:
            return m.group(0)
        total += 1
        return m.group(1) + m.group(2) + m.group(3) + m.group(4) + nm + m.group(6)

    s = EMLK_CODE_RE.sub(fixcode, s)

    def run(rx, m):
        nonlocal total
        got, nh = _process_container(m.group(2), n2c)
        if not nh:
            return m.group(0)
        total += nh
        return m.group(1) + got + m.group(3)

    s = CELL_RE.sub(lambda m: run(CELL_RE, m), s)
    s = SPAN_RE.sub(lambda m: run(SPAN_RE, m), s)
    return s, total


def files_of(args):
    if args.file:
        return [os.path.abspath(f) for f in args.file]
    fs = glob.glob(os.path.join(ROOT, "web", "**", "*.html"), recursive=True)
    fs.append(os.path.join(ROOT, "index.html"))
    return sorted(fs)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true", help="只统计不改写")
    ap.add_argument("--file", action="append", help="只处理指定文件（可重复）")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()

    n2c, c2n = L.name_map()
    if not n2c:
        print("[linkify] ⚠ 名称表为空（quant/_stock_names.json 缺失），跳过")
        return 0

    tot_files, tot_hits = 0, 0
    for f in files_of(a):
        try:
            s = open(f, encoding="utf-8", errors="ignore").read()
        except Exception:
            continue
        new, hits = scan_html(s, n2c, c2n)
        if hits and not a.dry:
            open(f, "w", encoding="utf-8").write(new)
        if hits:
            tot_files += 1
            tot_hits += hits
            if not a.quiet:
                print("  %-58s +%d" % (os.path.relpath(f, ROOT), hits))
    print("[linkify] %s %d 个文件 / %d 处个股名称%s"
          % ("将处理" if a.dry else "已处理", tot_files, tot_hits,
             "（dry-run，未写盘）" if a.dry else ""))
    return tot_hits


if __name__ == "__main__":
    main()
