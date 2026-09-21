from pathlib import Path
import polars as pl,json,math,re,csv
run=Path('artifacts/runs/20260920T190224-f2r1-rebuild-85e7f7e5'); results=json.loads((run/'factor_results.json').read_text(encoding='utf-8'))
old=Path('artifacts/runs/20260919T180000-f2r1-factor-batch/outputs'); newd=Path('artifacts/runs/20260920T190000-d-fund-rebuild-real/D_fund'); e16=Path('artifacts/runs/20260920T180001-e16-rebuild-real/E16.parquet')
paths={}
for fam in ['A_price','B_value','C_micro','E_event','F_xsec']:
 for p in (old/fam).glob('[A-F][0-9][0-9].parquet'):
  if p.stem!='E16': paths[p.stem]=p
paths['E16']=e16
for p in newd.glob('D*.parquet'): paths[p.stem]=p
panel=pl.read_parquet('data/processed/baostock-daily-20260917/daily_2015_2024.parquet').filter(pl.col('date')<=pl.date(2020,12,31)); panel=panel.with_columns((pl.col('symbol').str.starts_with('sh.688')|pl.col('symbol').str.starts_with('sz.300')|pl.col('symbol').str.starts_with('bj.')).alias('_x')); sig=pl.read_parquet(paths['A01']).select(pl.col('signal_date').alias('date')).unique(); elig=(panel.sort(['symbol','date']).with_columns(pl.col('date').cum_count().over('symbol').alias('_h')).join(sig,on='date').filter((pl.col('_h')>=60)&(pl.col('tradestatus')==1)&(pl.col('isST')==0)&(~pl.col('_x'))).select('date','symbol')); den=elig.group_by('date').agg(pl.col('symbol').n_unique().alias('n'))
rows=[]
for k,v in results.items():
 f=pl.read_parquet(paths[k]).filter(pl.col('signal_date')<=pl.date(2020,12,31)).rename({'signal_date':'date'}).join(elig,on=['date','symbol']).filter(pl.col('value').is_not_null()).group_by('date').agg(pl.col('symbol').n_unique().alias('v')).join(den,on='date').with_columns((pl.col('v')/pl.col('n')).alias('r'))
 cov=float(f['r'].median()) if f.height else 0
 t=v['ic_mean']/v['ic_std']*math.sqrt(v['n_dates']) if v['ic_std'] else 0; i=v['ic_by_year'].get('2015'); sg=lambda x:0 if x is None else (1 if x>0 else -1); bad=sg(i)!=0 and sg(i)!=sg(v['ic_mean']) and abs(i)>0.03; basic=abs(t)>=2 and abs(v['monotonicity'])>=.3 and sg(v['monotonicity'])==sg(v['ic_mean']) and not bad; rows.append({'factor_id':k,'t_ic':t,'coverage':cov,'basic_pass':basic,'screen_pass':basic and cov>=.5})
pl.DataFrame(rows).sort('factor_id').write_csv(run/'final_screen.csv'); print('basic',sum(x['basic_pass'] for x in rows),'final',sum(x['screen_pass'] for x in rows),'ids',','.join(x['factor_id'] for x in rows if x['screen_pass']))
