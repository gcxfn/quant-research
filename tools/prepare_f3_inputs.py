from pathlib import Path
import json,shutil,os,csv
new=Path('artifacts/runs/20260920T190224-f2r1-rebuild-85e7f7e5'); out=Path('artifacts/runs/20260920T190224-f2r1-rebuild-85e7f7e5/f3_inputs'); out.mkdir(exist_ok=True)
old=Path('artifacts/runs/20260919T180000-f2r1-factor-batch/outputs'); droot=Path('artifacts/runs/20260920T190000-d-fund-rebuild-real/D_fund'); e16=Path('artifacts/runs/20260920T180001-e16-rebuild-real/E16.parquet')
# Family folders and hardlinks for new source frames.
for fam in ['A_price','B_value','C_micro','D_fund','E_event','F_xsec']:(out/fam).mkdir(exist_ok=True)
for fam in ['A_price','B_value','C_micro','E_event','F_xsec']:
 for p in (old/fam).glob('[A-F][0-9][0-9].parquet'):
  if p.stem=='E16': continue
  os.link(p,out/fam/p.name)
for p in droot.glob('D*.parquet'): os.link(p,out/'D_fund'/p.name)
os.link(e16,out/'E_event'/'E16.parquet')
reps=json.loads((new/'dedup_report.json').read_text())['representatives']; res=json.loads((new/'factor_results.json').read_text()); rows=[]
for fid,v in res.items():
 t=v['ic_mean']/v['ic_std']*(v['n_dates']**.5) if v['ic_std'] else 0
 rows.append({'factor_id':fid,'family':fid[0],'screen_pass':True,'t_ic':t,'ic_mean':v['ic_mean'],'icir':v['icir'],'n_dates':v['n_dates'],'coverage':float(next(r['coverage'] for r in csv.DictReader((new/'final_screen.csv').open()) if r['factor_id']==fid))})
Path(out/'f2r1_all120.csv').write_text('factor_id,family,screen_pass,t_ic,ic_mean,icir,n_dates,coverage\n'+'\n'.join(f"{x['factor_id']},{x['family']},{str(x['screen_pass']).lower()},{x['t_ic']},{x['ic_mean']},{x['icir']},{x['n_dates']},{x['coverage']}" for x in rows)+'\n',encoding='utf-8')
# Corr matrix in runner-compatible shape.
corr=(new/'correlation_matrix.csv').read_text(encoding='utf-8'); (out/'f2r1_survivors_corr.csv').write_text(corr,encoding='utf-8')
for fid in reps:
 v=res[fid]; (out/({'A':'A_price','B':'B_value','C':'C_micro','D':'D_fund','E':'E_event','F':'F_xsec'}[fid[0]])/(fid+'.json')).write_text(json.dumps({'eval':v,'t_value':v['ic_mean']/v['ic_std']*(v['n_dates']**.5),'survived_prelim':True},ensure_ascii=False),encoding='utf-8')
print('prepared',len(reps),'reps',reps)

