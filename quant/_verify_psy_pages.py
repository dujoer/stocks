# -*- coding: utf-8 -*-
"""新生成雷达页质检：污染 / 主题 / 导航 / 日期一致性 / 关键数据"""
import re, io, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PSY = os.path.join(ROOT, 'web', 'psychology')
PAGES = {
    '20260828': 'crowd-psychology-risk-radar-20260828.html',
    '20260908': 'crowd-psychology-risk-radar-20260908.html',
}

for d, fn in PAGES.items():
    p = os.path.join(PSY, fn)
    t = io.open(p, encoding='utf-8').read()
    print('===== %s =====' % fn)
    print('  bytes =', len(t))
    print('  污染 data-page-node-id =', t.count('data-page-node-id'))
    print('  _theme.css =', t.count('_theme.css'), '| _app.js =', t.count('_app.js'))
    print('  topnav =', t.count('class="topnav"'))
    print('  外链 http(s) =', len(re.findall(r'(?:href|src)="https?://', t)))
    # 日期
    iso = '2026-%s-%s' % (d[:4], d[4:6])
    print('  日期串 %s 出现 =' % d, t.count(d), '| ISO %s =' % iso, t.count(iso))
    # title
    m = re.search(r'<title>(.*?)</title>', t, re.S)
    print('  title =', m.group(1).strip() if m else 'N/A')
    # 残留未替换日期
    for other in ('20260911', '20260910', '20260909'):
        c = t.count(other)
        if c:
            print('  [warn] 残留 %s = %d' % (other, c))
    # 关键数字残留（09-11 特征）
    for kw in ('3888.11', '13471.26', '3322.04', '955'):
        c = t.count(kw)
        if c:
            print('  [check] 含 %s = %d' % (kw, c))
    # 风险等级
    m = re.search(r'risk:"(.*?)"', t)
    print('  页面 risk 字段 =', m.group(1) if m else 'N/A')
    # 数据占位/未编造标注
    print('  未编造/暂缺标注 =', t.count('暂缺') + t.count('未编造') + t.count('缺失'))
