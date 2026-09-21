import json,csv,math
from pathlib import Path
p=Path('artifacts/runs/20260920T161436-f2r1-rebuild-d46c81e1')
d=json.loads((p/'factor_results.json').read_text(encoding='utf-8'))
c={r['factor_id']:float(r['coverage_median_ratio']) for r in csv.DictReader((p/'coverage_audit_strict.csv').open(encoding='utf-8'))}
def sg(x): return 0 if x is None else (1 if x>0 else (-1 if x<0 else 0))
out=[]
for k,v in d.items():
 t=v['ic_mean']/v['ic_std']*math.sqrt(v['n_dates']) if v['ic_std'] else 0
 ic15=v['ic_by_year'].get('2015'); disaster=sg(ic15)!=0 and sg(ic15)!=sg(v['ic_mean']) and abs(ic15)>0.03
 basic=abs(t)>=2 and abs(v['monotonicity'])>=.3 and sg(v['monotonicity'])==sg(v['ic_mean']) and not disaster
 out.append((k,basic,c.get(k,0),basic and c.get(k,0)>=.5))
print('final',sum(x[3] for x in out),'basic',sum(x[1] for x in out))
print('coverage differences from previous',[(x[0],x[2]) for x in out if x[0] in {'E13','B04','F02'}])
print('ids',','.join(x[0] for x in out if x[3]))
