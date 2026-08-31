import json, sys, os

def main():
    path = sys.argv[1]
    with open(path, encoding='utf-8') as f:
        js = json.load(f)
    data = js['data'] if isinstance(js, dict) and 'data' in js else js
    out = []
    print(f"{'code':10} {'name':10} {'n20%':>8} {'n60%':>8} {'J':>7} {'DIF>DEA':>8} {'PRE':>4}")
    for code, d in data.items():
        try:
            close = float(d['closePrice'])
            ma = d['ma']
            ma5, ma10, ma20, ma60 = ma['MA_5'], ma['MA_10'], ma['MA_20'], ma['MA_60']
            dif, dea = d['macd']['DIF'], d['macd']['DEA']
            j = d['kdj']['KDJ_J']
        except Exception as e:
            print(f"{code} ERR {e}")
            continue
        near20 = (close - ma20) / ma20 * 100
        near60 = (close - ma60) / ma60 * 100
        r1 = (ma20 > ma60) and (ma5 >= ma20 * 0.99)
        r3 = (-6 <= near20 <= 12)
        r4 = (dif > dea)
        r5 = (j < 70)
        r6 = (close > ma60) and (near60 <= 35)
        pre = r1 and r3 and r4 and r5 and r6
        mark = '***' if pre else ''
        print(f"{code:10} {d['name']:10} {near20:8.2f} {near60:8.2f} {j:7.1f} {'Y' if dif>dea else 'N':>8} {mark:>4}")
    if pre:
        out.append({
            'code': code, 'name': d['name'], 'close': round(close, 4),
            'ma5': round(ma5, 4), 'ma10': round(ma10, 4), 'ma20': round(ma20, 4), 'ma60': round(ma60, 4),
            'macd_dif': dif, 'macd_dea': dea, 'kdj_j': j,
            'near20pct': round(near20, 2), 'near60pct': round(near60, 2),
        })
    # accumulate pre-candidates across batches into one file
    acc_path = 'pre_candidates.json'
    acc = []
    if os.path.exists(acc_path):
        try:
            with open(acc_path, encoding='utf-8') as f:
                acc = json.load(f)
        except Exception:
            acc = []
    acc.extend(out)
    with open(acc_path, 'w', encoding='utf-8') as f:
        json.dump(acc, f, ensure_ascii=False, indent=2)
    if out:
        print(f"\nPRE (pass r1,r3,r4,r5,r6) in {path}: {len(out)}")
        for o in out:
            print(f"  {o['code']} {o['name']} close={o['close']} ma5={o['ma5']} ma10={o['ma10']} ma20={o['ma20']} ma60={o['ma60']} near20={o['near20pct']}% near60={o['near60pct']}% J={o['kdj_j']} DIF={o['macd_dif']} DEA={o['macd_dea']}")

if __name__ == '__main__':
    main()
