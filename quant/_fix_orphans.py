# -*- coding: utf-8 -*-
"""把孤儿页（无任何入链的归档页）接回所属索引页。

做法：在宿主索引页 body 末尾（`<!--WB_APP-->` 之前）插入一个「历史归档」链接块，
使用 _theme.css 的 .section / .arch 样式；块带哨兵注释，重复运行幂等。

用法：python quant/_fix_orphans.py [--dry]
"""
from __future__ import annotations
import os, re, sys, io, argparse, datetime as dt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _page_registry as R
from _coverage_check import all_html, build_inbound, match_family

ROOT = R.repo_root()
WEB = R.web_root()
BEGIN = '<!--ARCHIVE_LINKS-->'
END = '<!--/ARCHIVE_LINKS-->'

# 目录 -> 宿主索引页（相对 web/）；缺省用同目录 index.html
HOST = {
    'market': 'market/index.html',
    'lhb': 'lhb/lhb.html',
    'block': 'block/index.html',
    'sector': 'sector/index.html',
    'tplus': 'tplus/index.html',
    'psychology': 'psychology/index.html',
    'picks': 'picks/index.html',
    'research': 'research/index.html',
    '.': '../index.html',
}

# 文件名 -> 中文类型名
KIND = [
    (r'status_', '状态报告'),
    (r'daily_overview_', '每日总览'),
    (r'limitup_weekly_', '连板周报'),
    (r'lhb_', '龙虎榜'),
    (r'block_', '大宗交易'),
    (r'sector-strength-', '板块强度'),
    (r'tplus-', '做T池'),
    (r'pick_', '信号池'),
    (r'crowd-psychology-risk-radar-', '心理雷达'),
    (r'research-', '个股调研'),
]


def label_of(rel: str) -> str:
    fn = rel.split('/')[-1]
    d = re.search(r'(\d{4})-?(\d{2})-?(\d{2})', fn)
    date = ('%s-%s' % (d.group(2), d.group(3))) if d else ''
    kind = ''
    for rx, k in KIND:
        if re.search(rx, fn):
            kind = k
            break
    if not kind:
        kind = fn.replace('.html', '')
    return ('%s %s' % (date, kind)).strip()


def block_html(items, title='历史归档'):
    links = '\n'.join('  <a href="%s">%s</a>' % (href, txt) for href, txt in items)
    return (BEGIN + '\n<div class="section">\n<h2>%s</h2>\n<div class="arch">\n%s\n</div>\n</div>\n' % (title, links) + END)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry', action='store_true')
    a = ap.parse_args()

    pages = all_html()
    inbound = build_inbound(pages)
    orphans = sorted(r for r, c in inbound.items()
                     if c == 0 and not any(s in r for s in R.ORPHAN_WHITELIST_SUBSTR))
    if not orphans:
        print('无孤儿页，退出')
        return 0

    groups = {}
    for r in orphans:
        d = os.path.dirname(r) or '.'
        groups.setdefault(d, []).append(r)

    n_edit = 0
    for d, items in sorted(groups.items()):
        host = HOST.get(d, '%s/index.html' % d if d != '.' else '../index.html')
        if host not in pages:
            print('[skip] %-10s 宿主缺失 %s（%d 页）' % (d, host, len(items)))
            continue
        hp = pages[host]
        t = io.open(hp, encoding='utf-8').read()
        # 链接相对宿主所在目录
        hdir = os.path.dirname(host)
        prefix = 'web/' if host.startswith('../') else ''
        links = []
        for r in sorted(items, reverse=True):
            if prefix:
                href = prefix + r
            else:
                href = os.path.relpath(r, hdir).replace('\\', '/') if hdir else r
            links.append((href, label_of(r)))
        all_dated = all(re.search(r'\d{4}-?\d{2}-?\d{2}', r) for r in items)
        title = '历史归档' if all_dated else '相关页面'
        blk = block_html(links, title)
        # 幂等：先删旧块
        if BEGIN in t:
            t = re.sub(re.escape(BEGIN) + r'.*?' + re.escape(END), '', t, flags=re.S)
        anchor = '<!--WB_APP-->'
        if anchor in t:
            t = t.replace(anchor, blk + '\n' + anchor, 1)
        else:
            i = t.rfind('</body>')
            if i < 0:
                print('[skip] %s 无锚点' % host); continue
            t = t[:i] + blk + '\n' + t[i:]
        if not a.dry:
            io.open(hp, 'w', encoding='utf-8').write(t)
        n_edit += 1
        print('[ok] %-28s <- %d 个归档页链接' % (host, len(items)))

    print('修改宿主页数 =', n_edit)
    return 0


if __name__ == '__main__':
    sys.exit(main())
