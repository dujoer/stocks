# -*- coding: utf-8 -*-
"""从交互式 HTML 的 const DATA 中提取真实板块数据，保存为独立 JSON（避免源 HTML 被覆盖后丢失）。"""
import re, json

HTML = r'G:\ai\股票\web\sector-strength-20260827.html'
JSON_OUT = r'G:\ai\股票\quant\sector_strength_data.json'

with open(HTML, encoding='utf-8') as f:
    txt = f.read()

m = re.search(r'const DATA = (\[.*?\]);', txt, re.S)
if not m:
    raise SystemExit('未找到 const DATA')
data = json.loads(m.group(1))
with open(JSON_OUT, 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=0)
print('提取板块数:', len(data), '->', JSON_OUT)
