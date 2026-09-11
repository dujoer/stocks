# -*- coding: utf-8 -*-
"""抽取 HTML 内联 <script> 并用 node --check 校验语法"""
import re, io, os, subprocess, sys, tempfile

NODE = r'C:/Users/nonoy/.workbuddy/binaries/node/versions/22.22.2-3/node.exe'
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

targets = [a for a in sys.argv[1:] if not a.startswith('--')]
ALL = '--all' in sys.argv
if ALL or not targets:
    base = os.path.join(ROOT, 'web')
    targets = []
    for dp, _dn, fns in os.walk(base):
        targets += [os.path.join(dp, f) for f in fns if f.endswith('.html')]
    rp = os.path.join(ROOT, 'index.html')
    if os.path.exists(rp):
        targets.append(rp)
    targets = sorted(targets)

tmpdir = tempfile.mkdtemp(prefix='jscheck_')
fail = 0
for path in targets:
    t = io.open(path, encoding='utf-8').read()
    blocks = re.findall(r'<script(?![^>]*\ssrc=)[^>]*>(.*?)</script>', t, re.S)
    print('%s  内联 script 块 = %d' % (os.path.basename(path), len(blocks)))
    for i, b in enumerate(blocks):
        if not b.strip():
            continue
        f = os.path.join(tmpdir, '%s_%d.js' % (os.path.basename(path).replace('.html', ''), i))
        io.open(f, 'w', encoding='utf-8').write(b)
        r = subprocess.run([NODE, '--check', f], capture_output=True, text=True, encoding='utf-8', errors='replace')
        if r.returncode != 0:
            fail += 1
            print('  [FAIL] %s block %d: %s' % (os.path.basename(path), i, (r.stderr or '').strip()[:300]))
        elif not ALL:
            print('  [ok] block %d (%d chars)' % (i, len(b)))
print('FAIL =', fail)
sys.exit(1 if fail else 0)
