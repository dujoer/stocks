#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""解析券商导出的持仓表(.xls 实为 GBK 文本/TSV)，生成 deliverables/trading-agent/_all_store.json。"""
import json, os
from datetime import datetime

SRC = r"C:/Users/nonoy/Downloads/table.xls"
OUT = r"G:/ai/股票/deliverables/trading-agent/_all_store.json"
# updated 取导出文件 mtime（即券商导出日），避免硬编码失真
UPDATED = datetime.fromtimestamp(os.path.getmtime(SRC)).strftime("%Y-%m-%d")

def load_rows(path):
    raw = open(path, 'rb').read()
    text = None
    for enc in ('utf-8-sig', 'gbk', 'gb18030', 'latin-1'):
        try:
            text = raw.decode(enc)
            break
        except Exception:
            continue
    lines = [l for l in text.splitlines() if l.strip()]
    header = [h.strip() for h in lines[0].split('\t')]
    rows = []
    for line in lines[1:]:
        cells = [c.strip() for c in line.split('\t')]
        if len(cells) < len(header):
            continue
        rows.append(dict(zip(header, cells)))
    return header, rows

def num(x):
    x = (x or '').strip().replace(',', '')
    if x in ('', '--', 'None', 'null'):
        return None
    try:
        return float(x)
    except Exception:
        return None

header, rows = load_rows(SRC)
market_map = {'上海Ａ股': 'SH', '上海A股': 'SH', '深圳Ａ股': 'SZ', '深圳A股': 'SZ'}
stocks = []
for r in rows:
    code = (r.get('证券代码') or '').strip()
    name = (r.get('证券名称') or '').strip()
    qty = num(r.get('实际数量'))
    market = market_map.get((r.get('交易市场') or '').strip(), (r.get('交易市场') or '').strip())
    is_bond = code == '888880'
    stocks.append({
        'code': code,
        'name': name,
        'market': market,
        'type': 'bond' if is_bond else 'stock',
        'held': (qty or 0) > 0,
        'balance': num(r.get('股票余额')),
        'qty': qty,
        'available': num(r.get('可用余额')),
        'frozen': num(r.get('冻结数量')),
        'cost': num(r.get('成本价')),
        'price': num(r.get('市价')),
        'pnl': num(r.get('盈亏')),
        'pnl_pct': num(r.get('盈亏比例(%)')),
        'day_pnl': num(r.get('当日盈亏')),
        'day_pnl_pct': num(r.get('当日盈亏比(%)')),
        'mv': num(r.get('市值')),
        'weight': num(r.get('仓位占比(%)')),
        'buy_today': num(r.get('当日买入')),
        'sell_today': num(r.get('当日卖出')),
        'hold_days': num(r.get('持股天数')),
    })

held = [s for s in stocks if s['held']]
total_mv = sum((s['mv'] or 0) for s in held)
total_pnl = sum((s['pnl'] or 0) for s in held)
total_day_pnl = sum((s['day_pnl'] or 0) for s in stocks)
out = {
    'meta': {
        'updated': UPDATED,
        'source_file': SRC,
        'schema_version': 1,
        'generated_by': 'quant/build_store.py',
        'note': '由券商导出的持仓明细(GBK文本/.xls)解析生成；held 以 实际数量>0 标记。原始自动化 spec 假设约26只，本文件以实际导出为准。'
    },
    'summary': {
        'total_rows': len(stocks),
        'held_count': len(held),
        'total_held_market_value': round(total_mv, 2),
        'total_held_pnl': round(total_pnl, 2),
        'total_held_pnl_pct': round(total_pnl / total_mv * 100, 3) if total_mv else 0,
        'total_day_pnl': round(total_day_pnl, 2),
    },
    'stocks': stocks,
}
os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, 'w', encoding='utf-8') as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
print('wrote', OUT)
print('rows=%d held=%d total_held_mv=%.2f total_held_pnl=%.2f' % (len(stocks), len(held), total_mv, total_pnl))
for s in stocks:
    print(' ', s['code'], s['name'], 'held' if s['held'] else 'closed', 'qty=', s['qty'], 'mv=', s['mv'])
