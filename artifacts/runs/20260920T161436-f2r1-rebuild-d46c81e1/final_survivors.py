import json,csv,math
from pathlib import Path
p=Path('artifacts/runs/20260920T161436-f2r1-rebuild-d46c81e1')
d=json.loads((p/'factor_results.json').read_text(encoding='utf-8'))
c={r['factor_id']:float(r['coverage_median_ratio']) for r in csv.DictReader((p/'coverage_audit.csv').open(encoding='utf-8'))}
def sg(x): return 0 if x is None else (1 if x>0 else (-1 if x<0 else 0))
out=[]
for k,v in d.items():
 t=v['ic_mean']/v['ic_std']*math.sqrt(v['n_dates']) if v['ic_std'] else 0
 ic15=v['ic_by_year'].get('2015')
 disaster=sg(ic15)!=0 and sg(ic15)!=sg(v['ic_mean']) and abs(ic15)>0.03
 basic=abs(t)>=2 and abs(v['monotonicity'])>=.3 and sg(v['monotonicity'])==sg(v['ic_mean']) and not disaster
 final=basic and c.get(k,0)>=.5
 out.append({'factor_id':k,'t_ic':t,'coverage_median_ratio':c.get(k,0),'basic_pass':basic,'screen_pass':final})
Path(p/'final_survivors.csv').write_text('factor_id,t_ic,coverage_median_ratio,basic_pass,screen_pass\n'+'\n'.join(f"{x['factor_id']},{x['t_ic']:.6f},{x['coverage_median_ratio']:.6f},{str(x['basic_pass']).lower()},{str(x['screen_pass']).lower()}" for x in out)+'\n',encoding='utf-8')
print('final',sum(x['screen_pass'] for x in out),'basic',sum(x['basic_pass'] for x in out),'coverage_fail_basic',[(x['factor_id'],round(x['coverage_median_ratio'],3)) for x in out if x['basic_pass'] and not x['screen_pass']])
for fam in 'ABCDEF':
 z=[x for x in out if x['factor_id'].startswith(fam)]; print(fam,sum(x['screen_pass'] for x in z),'/ ',len(z))
