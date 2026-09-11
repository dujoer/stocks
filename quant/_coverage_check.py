# -*- coding: utf-8 -*-
"""全站页面覆盖度自检。

检查项：
  A. 未登记页面（registry 漏登记）
  B. 每日族的日期缺口（相对交易日集合，自动剔除周末）
  C. 每日族是否更新到目标日（stale）
  D. 孤儿页（无任何页面静态链接指向它）
  E. 导航入口页存在性

用法：
  python quant/_coverage_check.py                     # since=2026-08-17 until=今天
  python quant/_coverage_check.py --until 2026-09-11
  python quant/_coverage_check.py --json              # 额外落 JSON 报告

退出码：0=全部通过；1=存在覆盖缺口(B/C/D)；2=结构性问题(A/E)
"""
from __future__ import annotations
import os, re, sys, json, io, glob, argparse, datetime as dt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _page_registry as R

ROOT = R.repo_root()
WEB = R.web_root()


def norm_date(s: str) -> str:
    s = str(s).replace('-', '').replace('/', '')
    return s if re.fullmatch(r'\d{8}', s) else ''


def is_weekday(d: str) -> bool:
    try:
        return dt.date(int(d[:4]), int(d[4:6]), int(d[6:8])).weekday() < 5
    except Exception:
        return False


def all_html():
    """{相对 web/ 的路径: 绝对路径}，仓库根 index.html 记为 ../index.html"""
    out = {}
    for dirpath, _dn, filenames in os.walk(WEB):
        for fn in filenames:
            if fn.lower().endswith('.html'):
                ap = os.path.join(dirpath, fn)
                out[os.path.relpath(ap, WEB).replace('\\', '/')] = ap
    root_idx = os.path.join(ROOT, 'index.html')
    if os.path.exists(root_idx):
        out['../index.html'] = root_idx
    return out


def match_family(rel: str):
    for f in R.FAMILIES:
        for pat in f['patterns']:
            if glob.fnmatch.fnmatch(rel, pat):
                return f
    return None


def dates_in_family(pages, date_re):
    rx = re.compile(date_re)
    ds = set()
    for rel in pages:
        m = rx.search(rel)
        if m:
            d = norm_date(m.group(1))
            if d:
                ds.add(d)
    return ds


def trade_days_from_data(since: str, until: str):
    """从 web/data/*.json 的列式 data 抽取 date 列，自动剔除周末"""
    D = os.path.join(WEB, 'data')
    days = set()
    if not os.path.isdir(D):
        return days
    for fn in sorted(os.listdir(D)):
        if not fn.endswith('.json') or fn == 'manifest.json':
            continue
        try:
            j = json.load(io.open(os.path.join(D, fn), encoding='utf-8'))
        except Exception:
            continue
        fields, data = j.get('fields') or [], j.get('data')
        if not fields or not isinstance(data, list) or not data:
            continue
        idx = next((i for i, f in enumerate(fields)
                    if isinstance(f, dict) and f.get('n') == 'date'), None)
        if idx is None or idx >= len(data) or not isinstance(data[idx], list):
            continue
        for v in data[idx]:
            d = norm_date(v)
            if d and since <= d <= until and is_weekday(d):
                days.add(d)
    return days


def build_inbound(pages):
    """统计每个页面的入链数。

    同时识别两种引用形式：
      1) 静态属性  href="...html" / src="...html"
      2) JS 数据   file:"...html" / url:'...html'（列表页动态渲染卡片用）
    """
    attr_rx = re.compile(r'(?:href|src)=["\']([^"\']+\.html[^"\']*)["\']')
    js_rx = re.compile(r'(?:file|url|page|link)\s*[:=]\s*["\']([^"\']+\.html)["\']')
    inbound = {k: 0 for k in pages}
    for rel, ap in pages.items():
        try:
            t = io.open(ap, encoding='utf-8', errors='ignore').read()
        except Exception:
            continue
        # 门户在仓库根（记为 ../index.html）：其链接以仓库根为基准，
        # 形如 web/xxx.html，需剥掉 web/ 前缀再按 web/ 根解析。
        if rel.startswith('../'):
            base = '.'
        else:
            base = os.path.dirname(rel)
        seen = set()
        for rx in (attr_rx, js_rx):
            for href in rx.findall(t):
                href = href.split('#')[0].split('?')[0]
                if not href or href.startswith(('http', 'mailto:', 'javascript:')):
                    continue
                if rel.startswith('../'):
                    href = re.sub(r'^(?:\.\./)?web/', '', href)
                target = os.path.normpath(os.path.join(base, href)).replace('\\', '/')
                seen.add(target)
        for target in seen:
            if target in inbound:
                inbound[target] += 1
    return inbound


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--since', default='20260817')
    ap.add_argument('--until', default=dt.date.today().strftime('%Y%m%d'))
    ap.add_argument('--json', action='store_true')
    a = ap.parse_args()
    since, until = norm_date(a.since), norm_date(a.until)

    pages = all_html()
    fam2pages, unregistered = {}, []
    for rel in sorted(pages):
        f = match_family(rel)
        if f is None:
            unregistered.append(rel)
        else:
            fam2pages.setdefault(f['key'], []).append(rel)

    problems, structural = [], []

    print('=' * 74)
    print('全站页面覆盖度自检   since=%s until=%s   页面总数=%d'
          % (since, until, len(pages)))
    print('=' * 74)

    # A
    print('\n[A] 未登记页面：%d' % len(unregistered))
    for r in unregistered[:20]:
        print('    ? ' + r)
    if unregistered:
        structural.append('A: %d 个页面未在 _page_registry 登记' % len(unregistered))

    td = trade_days_from_data(since, until)
    print('\n[交易日] %d 天（已剔周末）：%s ... %s'
          % (len(td), min(td) if td else '-', max(td) if td else '-'))

    # B/C
    print('\n[B/C] 按日归档族覆盖：')
    print('    %-12s %-5s %-9s %-6s %s' % ('族', '页数', '最新', '缺口', '判定'))
    for f in R.FAMILIES:
        key, ps = f['key'], fam2pages.get(f['key'], [])
        if not f['dated']:
            print('    %-12s %-5d %-9s %-6s %s' % (key, len(ps), '-', '-', '单页滚动更新（不判缺口）'))
            if not ps and f['freq'] == 'daily':
                structural.append('%s: 无页面' % key)
            continue
        if not ps:
            print('    %-12s %-5d %-9s %-6s %s' % (key, 0, '-', '-', '无页面'))
            if f['freq'] == 'daily':
                structural.append('%s: 无页面' % key)
            continue

        ds = dates_in_family(ps, f['date_re'])
        lo = max(since, f['start'] or since)
        window = {d for d in td if lo <= d <= until} if td else set()
        missing = sorted(window - ds) if td else []
        latest = max(ds) if ds else '-'
        flag = ''
        if f['freq'] == 'daily' and td:
            if missing:
                flag = '缺 %d 期: %s' % (len(missing),
                                        ','.join(missing[:8]) + ('...' if len(missing) > 8 else ''))
                problems.append('%s: 缺 %d 期 %s' % (key, len(missing), missing[:10]))
            if until in window and latest != until:
                flag += (' | ' if flag else '') + '未更新到 %s' % until
                problems.append('%s: 最新 %s，未到 %s' % (key, latest, until))
        elif not td:
            flag = '无交易日集合'
        else:
            flag = '按需/低频（不判缺口）'
        print('    %-12s %-5d %-9s %-6s %s'
              % (key, len(ps), latest, len(missing) if td else '-', flag or 'OK'))

    # D
    inbound = build_inbound(pages)
    orphans = sorted(r for r, c in inbound.items()
                     if c == 0 and not any(s in r for s in R.ORPHAN_WHITELIST_SUBSTR))
    print('\n[D] 孤儿页（无任何静态入链，已排除白名单）：%d' % len(orphans))
    for r in orphans[:40]:
        print('    - ' + r)
    if orphans:
        problems.append('D: %d 个孤儿页（用户无法从任何页面点到）' % len(orphans))

    # E
    try:
        import _nav
        entries = list(_nav.SECTIONS)
    except Exception as e:
        entries = []
        structural.append('E: 无法载入 _nav.SECTIONS (%s)' % e)
    miss_entry = [(t, p) for t, p in entries if p not in pages]
    print('\n[E] 导航入口存在性：%d/%d' % (len(entries) - len(miss_entry), len(entries)))
    for t, p in miss_entry:
        print('    x %s -> %s 缺失' % (t, p))
    if miss_entry:
        structural.append('E: %d 个导航入口缺失' % len(miss_entry))

    print('\n' + '=' * 74)
    if structural:
        print('结构性问题：')
        for s in structural:
            print('  [STRUCT] ' + s)
    if problems:
        print('覆盖缺口：')
        for p in problems:
            print('  [GAP]    ' + p)
    if not structural and not problems:
        print('ALL_COVERED — 全部页面族已覆盖 %s，0 缺口 / 0 孤儿' % until)
    print('=' * 74)

    if a.json:
        rep = dict(since=since, until=until, pages=len(pages),
                   trade_days=sorted(td), unregistered=unregistered,
                   structural=structural, problems=problems, orphans=orphans)
        out = os.path.join(ROOT, 'quant', '_coverage_report.json')
        io.open(out, 'w', encoding='utf-8').write(json.dumps(rep, ensure_ascii=False, indent=2))
        print('JSON -> ' + out)

    return 2 if structural else (1 if problems else 0)


if __name__ == '__main__':
    sys.exit(main())
