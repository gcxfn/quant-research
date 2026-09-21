import json,csv,math
from pathlib import Path
p=Path('artifacts/runs/20260920T161436-f2r1-rebuild-d46c81e1'); d=json.loads((p/'factor_results.json').read_text(encoding='utf-8')); c={r['factor_id']:float(r['coverage_median_ratio']) for r in csv.DictReader((p/'coverage_audit_strict.csv').open(encoding='utf-8'))}
def sg(x): return 0 if x is None else (1 if x>0 else (-1 if x<0 else 0))
out=[]
for k,v in d.items():
 t=v['ic_mean']/v['ic_std']*math.sqrt(v['n_dates']) if v['ic_std'] else 0; i=v['ic_by_year'].get('2015'); bad=sg(i)!=0 and sg(i)!=sg(v['ic_mean']) and abs(i)>0.03
 basic=abs(t)>=2 and abs(v['monotonicity'])>=.3 and sg(v['monotonicity'])==sg(v['ic_mean']) and not bad
 out.append((k,basic,c[k],basic and c[k]>=.5))
print('final',sum(x[3] for x in out),'basic',sum(x[1] for x in out),'basic_coverage_fail',[(x[0],round(x[2],3)) for x in out if x[1] and not x[3]])
for fam in 'ABCDEF': print(fam,sum(x[3] for x in out if x[0].startswith(fam)))
print('ids',','.join(x[0] for x in out if x[3]))
