import json, re
from pathlib import Path
import polars as pl
root=Path('artifacts/runs/20260920T161436-f2r1-rebuild-d46c81e1')
panel=pl.read_parquet('data/processed/baostock-daily-20260917/daily_2015_2024.parquet').filter(pl.col('date')<=pl.date(2020,12,31))
panel=panel.with_columns(pl.col('symbol').str.starts_with('sh.688').or_(pl.col('symbol').str.starts_with('sz.300')).or_(pl.col('symbol').str.starts_with('bj.')).alias('_excluded'))
# Historical F1-style eligible pool with 60 prior rows.
hist=(panel.filter((pl.col('tradestatus')==1)&(pl.col('isST')==0)&(~pl.col('_excluded')))
      .group_by('symbol').agg(pl.col('date').n_unique().alias('n_hist')))
elig_syms=set(hist.filter(pl.col('n_hist')>=60)['symbol'].to_list())
monthly=panel.filter(pl.col('symbol').is_in(list(elig_syms))).group_by('date').agg(pl.col('symbol').n_unique().alias('eligible')).sort('date')
# factor signal dates are already month-end rows.
base=monthly.filter(pl.col('date').is_in(panel.select('date').unique().to_series().to_list()))
# use per-date eligible counts from actual eligible panel and factor rows.
rows=[]
for fam in sorted([p for p in (Path('artifacts/runs/20260919T180000-f2r1-factor-batch/outputs')).iterdir() if p.is_dir()]):
  for fp in sorted(fam.glob('*.parquet')):
    if not re.fullmatch(r'[A-F]\d{2}\.parquet',fp.name): continue
    f=pl.read_parquet(fp).filter(pl.col('signal_date')<=pl.date(2020,12,31))
    f=f.select(['symbol','signal_date','value']).with_columns(pl.col('signal_date').alias('date'))
    joined=f.join(base,on='date',how='left')
    cov=(joined.filter(pl.col('value').is_not_null()).group_by('date').agg(pl.col('symbol').n_unique().alias('valid'))
         .join(base,on='date',how='left').with_columns((pl.col('valid')/pl.col('eligible')).alias('ratio')))
    median=float(cov['ratio'].median()) if cov.height else 0.0
    rows.append({'factor_id':fp.stem,'family':fam.name.split('_')[0],'coverage_median_ratio':median,'months':cov.height})
pl.DataFrame(rows).write_csv(root/'coverage_audit.csv')
median_baseline=float(base['eligible'].median())
threshold=0.5
out={'eligible_pool_median':median_baseline,'coverage_rule':'factor monthly valid symbol count / monthly eligible pool; median ratio >= 0.5','factors':len(rows),'coverage_pass':sum(r['coverage_median_ratio']>=threshold for r in rows)}
(root/'coverage_audit.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(out,ensure_ascii=False))
