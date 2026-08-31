import json

batches = ['batch1_raw.json','batch2_raw.json','batch3_raw.json','batch4_raw.json','batch5_raw.json']
# ROE% 取自步骤1底池返回
roe_map = {
 'sz002313':20.51,'sh688617':15.96,'sz002524':17.15,'sz002795':15.46,
 'sh600506':14.56,'sh600768':12.75,'sz300855':11.68,'sz301606':12.12,
 'sh600839':10.2601,'sh601069':10.92
}
# 量比(volume_ratio) 取自步骤3 data_quote补拉，规则2必须项
vol_map = {
 'sz002313':0.55,'sh688617':0.59,'sz002524':0.58,'sz002795':0.83,
 'sh600506':1.14,'sh600768':0.87,'sz300855':0.44,'sz301606':1.27,
 'sh600839':1.24,'sh601069':0.83
}
# 行业：名称+常识推断（未调用data_profile，标注"名称推断"）
ind_map = {
 'sz002313':'通信(物联网设备)','sh688617':'医疗器械','sz002524':'医疗服务(眼科)',
 'sz002795':'通用设备(阀门)',  'sh600506':'化工(润滑油)',  'sh600768':'新材料',
 'sz300855':'军工/有色新材料(高温合金)','sz301606':'消费电子(连接器)',
 'sh600839':'家电/消费电子',   'sh601069':'黄金'
}

cands=[]
for b in batches:
    with open(b,encoding='utf-8') as f:
        data=json.load(f)['data']
    for code,d in data.items():
        try:
            ma=d['ma']; close=float(d['closePrice'])
            ma5,ma10,ma20,ma60=ma['MA_5'],ma['MA_10'],ma['MA_20'],ma['MA_60']
            dif,dea=d['macd']['DIF'],d['macd']['DEA']; j=d['kdj']['KDJ_J']
        except Exception:
            continue
        near20=(close-ma20)/ma20*100
        r1=(ma20>ma60) and (ma5>=ma20*0.99)
        r3=(-6<=near20<=12)
        r4=(dif>dea); r5=(j<70); r6=(close>ma60) and ((close-ma60)/ma60*100<=35)
        if r1 and r3 and r4 and r5 and r6:
            vr=vol_map.get(code,99)
            if vr < 1.3:
                cands.append({
                  'code':code,'name':d['name'],'roe':roe_map.get(code),
                  'close':round(close,4),'ma5':round(ma5,4),'ma10':round(ma10,4),
                  'ma20':round(ma20,4),'ma60':round(ma60,4),
                  'vol_ratio':vr,'kdj_j':round(j,2),
                  'macd_dif':dif,'macd_dea':dea,'near20pct':round(near20,2),
                  'industry':ind_map.get(code,'(名称推断)')
                })

cands.sort(key=lambda x:x['industry'])
with open('qlqs_candidates_relaxed_2026-08-27.json','w',encoding='utf-8') as f:
    json.dump(cands,f,ensure_ascii=False,indent=2)
print('FINAL candidates:',len(cands))
for c in cands:
    print(f"{c['code']} {c['name']:8} {c['industry']:18} roe={c['roe']} vol={c['vol_ratio']} near20={c['near20pct']}% J={c['kdj_j']} DIF>DEA={c['macd_dif']>c['macd_dea']} ({c['close']})")
