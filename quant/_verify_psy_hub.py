# -*- coding: utf-8 -*-
"""只读校验：心理雷达索引页回补结果 + 三期页面结构自检"""
import re, os, io, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HUB = os.path.join(ROOT, 'web', 'psychology', 'index.html')
PAGES = [
    'crowd-psychology-risk-radar-20260828.html',
    'crowd-psychology-risk-radar-20260908.html',
    'crowd-psychology-risk-radar-20260911.html',
]

t = io.open(HUB, encoding='utf-8').read()
print('HUB bytes =', len(t))

# 1) 期数
nums = re.findall(r'crowd-psychology-risk-radar-(\d{8})\.html', t)
print('雷达页引用 =', len(nums), sorted(set(nums)))

# 2) 休市残留
print('休市残留 =', t.count('休市'))
print('nrow holiday =', t.count('nrow holiday'))
print('HOLIDAYS 常量 =', t.count('HOLIDAYS'))

# 3) 统计区
m = re.search(r'<div class="num">(\d+) <small data-i18n="s_issues">', t)
print('期数 num =', m.group(1) if m else 'NOT FOUND')

# 4) REPORTS 条数
blk = re.search(r'var REPORTS = \[(.*?)\n\];', t, re.S)
if blk:
    print('REPORTS 条目 =', blk.group(1).count('"file"'))
else:
    print('REPORTS 条目 = NOT FOUND')

# 5) 时间轴 nrow 行数
print('nrow 总行 =', t.count('<div class="nrow">'))

# 6) 三期页面存在性 + 大小
for p in PAGES:
    f = os.path.join(ROOT, 'web', 'psychology', p)
    if os.path.exists(f):
        s = io.open(f, encoding='utf-8').read()
        print('  %s  %d bytes' % (p, len(s)))
    else:
        print('  %s  MISSING' % p)

# 7) 关键结构：趋势图点数
m = re.search(r'<polyline class="line"[^>]*points="([^"]+)"', t)
if m:
    print('趋势图点数 =', len(m.group(1).split()))

# 8) 断链：hub 指向的每个文件是否存在
files = re.findall(r'"file":\s*"([^"]+)"', t)
base = os.path.join(ROOT, 'web', 'psychology')
miss = [f for f in files if not os.path.exists(os.path.join(base, f))]
print('REPORTS 断链 =', len(miss), miss[:5])
