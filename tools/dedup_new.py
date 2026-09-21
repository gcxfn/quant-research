from pathlib import Path
import polars as pl,json,math
run=Path('artifacts/runs/20260920T190224-f2r1-rebuild-85e7f7e5'); ids=pl.read_csv(run/'final_screen.csv').filter(pl.col('screen_pass'))['factor_id'].to_list(); old=Path('artifacts/runs/20260919T180000-f2r1-factor-batch/outputs'); droot=Path('artifacts/runs/20260920T190000-d-fund-rebuild-real/D_fund'); paths={}
for fam in ['A_price','B_value','C_micro','E_event','F_xsec']:
 for p in (old/fam).glob('[A-F][0-9][0-9].parquet'):
  if p.stem!='E16': paths[p.stem]=p
paths['E16']=Path('artifacts/runs/20260920T180001-e16-rebuild-real/E16.parquet')
for p in droot.glob('D*.parquet'): paths[p.stem]=p
base=None
for fid in ids:
 f=pl.read_parquet(paths[fid]).filter(pl.col('signal_date')<=pl.date(2020,12,31)).select(['symbol','signal_date','value']).rename({'value':fid}); base=f if base is None else base.join(f,on=['symbol','signal_date'],how='inner')
M={a:{b:(1.0 if a==b else None) for b in ids} for a in ids}; pairs=[]
for i,a in enumerate(ids):
 for b in ids[i+1:]:
  z=base.group_by('signal_date').agg(pl.corr(pl.col(a).rank('average'),pl.col(b).rank('average')).alias('rho')).drop_nulls()['rho']; rho=float(z.mean()) if z.len() else 0.; M[a][b]=M[b][a]=rho
  if abs(rho)>=.6:pairs.append({'a':a,'b':b,'rho':rho})
parent={x:x for x in ids}
def find(x):
 while parent[x]!=x: parent[x]=parent[parent[x]]; x=parent[x]
 return x
def union(a,b):
 a,b=find(a),find(b)
 if a!=b:parent[b]=a
for x in pairs:union(x['a'],x['b'])
clusters={}
for x in ids:clusters.setdefault(find(x),[]).append(x)
metrics=json.loads((run/'factor_results.json').read_text(encoding='utf-8')); rows=[]; reps=[]
for i,m in enumerate(clusters.values(),1):
 m=sorted(m); rep=sorted(m,key=lambda x:(-(abs(metrics[x]['ic_mean']/metrics[x]['ic_std']*math.sqrt(metrics[x]['n_dates'])) if metrics[x]['ic_std'] else 0),x))[0];reps.append(rep);rows.append({'cluster_id':i,'members':','.join(m),'representative':rep})
pl.DataFrame(rows).write_csv(run/'dedup_clusters.csv'); pl.DataFrame([dict({'factor':a},**M[a]) for a in ids]).write_csv(run/'correlation_matrix.csv'); (run/'dedup_report.json').write_text(json.dumps({'factor_count':len(ids),'inner_rows':base.height,'high_corr_pairs':len(pairs),'clusters':len(clusters),'representatives':sorted(reps)},ensure_ascii=False,indent=2),encoding='utf-8');print('ids',len(ids),'inner',base.height,'pairs',len(pairs),'clusters',len(clusters),'reps',len(reps),sorted(reps))
