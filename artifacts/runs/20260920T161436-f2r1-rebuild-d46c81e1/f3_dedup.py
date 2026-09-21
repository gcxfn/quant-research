import csv,json,math
from pathlib import Path
from datetime import datetime,timezone
import polars as pl
src=Path('artifacts/runs/20260920T161436-f2r1-rebuild-d46c81e1'); out=Path('artifacts/runs/20260920T170000-f3r1-rebuild-local'); out.mkdir(parents=True,exist_ok=False)
ids=[r['factor_id'] for r in csv.DictReader((src/'final_survivors_strict.csv').open(encoding='utf-8'))] if (src/'final_survivors_strict.csv').exists() else ['A01']
# Build from strict final IDs directly from factor files.
ids=['A01','A02','A05','A09','A10','A17','A18','A19','A20','A21','A22','A23','A24','A25','B09','B10','B11','B12','B14','B15','C01','C11','C12','C19','D07','D08','D09','D10','D12','D13','D14','D16','D17','D18','D19','D20','D30','E16','F02','F06','F09','F10']
famdir={'A':'A_price','B':'B_value','C':'C_micro','D':'D_fund','E':'E_event','F':'F_xsec'}
frames=[]
for fid in ids:
 p=Path('artifacts/runs/20260919T180000-f2r1-factor-batch/outputs')/famdir[fid[0]]/(fid+'.parquet')
 f=pl.read_parquet(p).filter(pl.col('signal_date')<=pl.date(2020,12,31)).select(['symbol','signal_date','value']).rename({'value':fid})
 frames.append(f)
base=frames[0]
for f in frames[1:]: base=base.join(f,on=['symbol','signal_date'],how='inner')
# Per-month Spearman then average, matching historical logic, deterministic IDs.
M={fid:{x:1.0 if x==fid else None for x in ids} for fid in ids}
for i,a in enumerate(ids):
 for b in ids[i+1:]:
  vals=base.group_by('signal_date').agg(pl.corr(pl.col(a).rank('average'),pl.col(b).rank('average')).alias('rho')).drop_nulls()['rho']
  rho=float(vals.mean()) if vals.len() else 0.0
  M[a][b]=M[b][a]=rho
pairs=[]
for i,a in enumerate(ids):
 for b in ids[i+1:]:
  if abs(M[a][b])>=0.6: pairs.append({'a':a,'b':b,'rho':M[a][b]})
pairs.sort(key=lambda x:(-abs(x['rho']),x['a'],x['b']))
# connected components by |rho| threshold, representative max |t_ic| then factor id.
parent={x:x for x in ids}
def find(x):
 while parent[x]!=x: parent[x]=parent[parent[x]]; x=parent[x]
 return x
def union(a,b):
 ra,rb=find(a),find(b)
 if ra!=rb: parent[rb]=ra
for x in pairs: union(x['a'],x['b'])
clusters={}
for x in ids: clusters.setdefault(find(x),[]).append(x)
metrics=json.loads((src/'factor_results.json').read_text(encoding='utf-8'))
def t(fid):
 v=metrics[fid]; return abs(v['ic_mean']/v['ic_std']*math.sqrt(v['n_dates'])) if v['ic_std'] else 0
cluster_rows=[]; reps=[]
for members in clusters.values():
 members=sorted(members); rep=sorted(members,key=lambda x:(-t(x),x))[0]; reps.append(rep); cluster_rows.append({'cluster_id':len(cluster_rows)+1,'members':','.join(members),'representative':rep,'representative_abs_t':t(rep)})
pl.DataFrame(cluster_rows).write_csv(out/'dedup_clusters.csv')
pl.DataFrame([dict({'factor':a}, **{b:M[a][b] for b in ids}) for a in ids]).write_csv(out/'correlation_matrix.csv')
(out/'pairs_abs_rho_ge_0.6.json').write_text(json.dumps(pairs,ensure_ascii=False,indent=2),encoding='utf-8')
(out/'manifest.json').write_text(json.dumps({'status':'completed','experiment_id':'exp-20260920-f3r1-rebuild','source_run':str(src),'factor_count':len(ids),'inner_join_rows':base.height,'threshold':0.6,'representatives':sorted(reps),'created_at':datetime.now(timezone.utc).isoformat()},ensure_ascii=False,indent=2),encoding='utf-8')
print('factors',len(ids),'inner_rows',base.height,'pairs',len(pairs),'clusters',len(clusters),'representatives',len(reps),','.join(sorted(reps)))

