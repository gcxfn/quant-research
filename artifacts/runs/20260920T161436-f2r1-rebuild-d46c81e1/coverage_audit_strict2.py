import re
from pathlib import Path
import polars as pl
root=Path('artifacts/runs/20260920T161436-f2r1-rebuild-d46c81e1')
panel=pl.read_parquet('data/processed/baostock-daily-20260917/daily_2015_2024.parquet').filter(pl.col('date')<=pl.date(2020,12,31))
panel=panel.with_columns((pl.col('symbol').str.starts_with('sh.688')|pl.col('symbol').str.starts_with('sz.300')|pl.col('symbol').str.starts_with('bj.')).alias('_excluded'))
signal_dates=pl.read_parquet('artifacts/runs/20260919T180000-f2r1-factor-batch/outputs/A_price/A01.parquet').select('signal_date').unique().sort('signal_date')
elig=(panel.sort(['symbol','date']).with_columns(pl.col('date').cum_count().over('symbol').alias('_hist')).join(signal_dates,left_on='date',right_on='signal_date',how='inner').filter((pl.col('_hist')>=60)&(pl.col('tradestatus')==1)&(pl.col('isST')==0)&(~pl.col('_excluded'))).select([pl.col('date'),pl.col('symbol')]))
base=elig.group_by('date').agg(pl.col('symbol').n_unique().alias('eligible'))
rows=[]
for fam in sorted([p for p in Path('artifacts/runs/20260919T180000-f2r1-factor-batch/outputs').iterdir() if p.is_dir()]):
 for fp in sorted(fam.glob('*.parquet')):
  if not re.fullmatch(r'[A-F]\d{2}\.parquet',fp.name): continue
  f=pl.read_parquet(fp).filter(pl.col('signal_date')<=pl.date(2020,12,31)).select(['symbol','signal_date','value']).rename({'signal_date':'date'})
  j=f.join(elig,on=['date','symbol'],how='inner').filter(pl.col('value').is_not_null())
  cov=j.group_by('date').agg(pl.col('symbol').n_unique().alias('valid')).join(base,on='date').with_columns((pl.col('valid')/pl.col('eligible')).alias('ratio'))
  rows.append({'factor_id':fp.stem,'coverage_median_ratio':float(cov['ratio'].median()),'coverage_max_ratio':float(cov['ratio'].max()),'months':cov.height})
pl.DataFrame(rows).write_csv(root/'coverage_audit_strict.csv')
print('factors',len(rows),'over100',sum(r['coverage_max_ratio']>1 for r in rows),'pass',sum(r['coverage_median_ratio']>=.5 for r in rows),'pool_median',base['eligible'].median())
