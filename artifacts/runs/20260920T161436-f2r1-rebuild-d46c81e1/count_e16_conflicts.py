from pathlib import Path
import polars as pl
root=Path('data/raw/tushare/dividend'); fs=[p for b in ['20260913-r2','20260909-r3'] for p in (root/b).glob('chunk_*.csv') if p.stat().st_size>100]
xs=[]
for p in fs:
 d=pl.read_csv(p,infer_schema_length=10000); keep=[c for c in ['ts_code','div_proc','ann_date','ex_date','cash_div'] if c in d.columns]; d=d.select(keep).with_columns(pl.col('cash_div').cast(pl.Float64,strict=False));
 if 'div_proc' in d: d=d.filter(pl.col('div_proc')=='实施')
 xs.append(d)
d=pl.concat(xs,how='diagonal').with_columns(pl.col('ex_date').cast(pl.String).str.to_date('%Y%m%d',strict=False),pl.col('ann_date').cast(pl.String).str.to_date('%Y%m%d',strict=False),pl.concat_str(pl.col('ts_code').str.split('.').list.last().str.to_lowercase(),pl.lit('.'),pl.col('ts_code').str.split('.').list.first()).alias('symbol')).filter(pl.col('ex_date')<=pl.date(2024,12,31))
c=d.group_by('symbol','ex_date').agg(pl.col('cash_div').n_unique().alias('n'),pl.col('cash_div').drop_nulls().unique().alias('vals'),pl.len().alias('rows')).filter(pl.col('n')>1)
print('groups',c.height); print(c.filter(pl.col('vals').list.len()>1).select(['symbol','ex_date','vals','rows']).head(30))

