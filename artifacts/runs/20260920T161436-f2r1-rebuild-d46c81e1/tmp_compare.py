import csv,json,math
from pathlib import Path
old=Path('artifacts/runs/20260919T180000-f2r1-factor-batch/outputs/f2r1_all120.csv')
new=Path('artifacts/runs/20260920T161436-f2r1-rebuild-d46c81e1/factor_results.json')
old_rows={r['factor_id']:r for r in csv.DictReader(old.open(encoding='utf-8'))}
nd=json.loads(new.read_text(encoding='utf-8'))
rows=[]
for k,v in nd.items():
    n=v['n_dates']; t=v['ic_mean']/v['ic_std']*math.sqrt(n) if v['ic_std'] else None
    ic15=v['ic_by_year'].get('2015'); sign=lambda x: 0 if x is None else (1 if x>0 else (-1 if x<0 else 0))
    disaster=sign(ic15)!=0 and sign(ic15)!=sign(v['ic_mean']) and abs(ic15)>0.03
    pass_basic=abs(t or 0)>=2 and abs(v['monotonicity'])>=.3 and sign(v['monotonicity'])==sign(v['ic_mean']) and not disaster
    rows.append((k,v,t,pass_basic,old_rows.get(k,{}).get('screen_pass','')))
print('count',len(rows),'new_basic',sum(x[3] for x in rows),'old_pass',sum(x[4].lower()=='true' for x in rows))
print('changed metrics',sum(abs(x[1]['ic_mean']-float(old_rows[x[0]]['ic_mean']))>1e-8 for x in rows if x[0] in old_rows))
print('changed family counts')
for fam in 'ABCDEF':
    rs=[x for x in rows if x[0].startswith(fam)]
    print(fam,len(rs),sum(x[3] for x in rs),sum(x[4].lower()=='true' for x in rs))
print('new_basic_ids',','.join(x[0] for x in rows if x[3]))
print('old_only',','.join(x[0] for x in rows if x[4].lower()=='true' and not x[3]))
print('new_only',','.join(x[0] for x in rows if x[3] and x[4].lower()!='true'))

