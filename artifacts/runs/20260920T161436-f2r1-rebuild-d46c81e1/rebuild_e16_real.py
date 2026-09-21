from pathlib import Path
from datetime import date
import polars as pl
from quant.research.f2r1_rebuild import rebuild_e16
root=Path('data/raw/tushare/dividend')
files=[]
for batch in ['20260913-r2','20260909-r3']:
 for p in (root/batch).glob('chunk_*.csv'):
  if p.stat().st_size>100: files.append(p)
frames=[]
for p in files:
 d=pl.read_csv(p,infer_schema_length=10000)
 keep=[c for c in ['ts_code','div_proc','ann_date','ex_date','cash_div'] if c in d.columns]
 d=d.select(keep).with_columns(pl.col('cash_div').cast(pl.Float64,strict=False) if 'cash_div' in d.columns else pl.lit(None,dtype=pl.Float64).alias('cash_div'))
 if 'div_proc' in d.columns: d=d.filter(pl.col('div_proc')=='实施')
 frames.append(d)
div=pl.concat(frames,how='diagonal').with_columns(
    pl.col('ann_date').cast(pl.String).str.to_date('%Y%m%d', strict=False),
    pl.col('ex_date').cast(pl.String).str.to_date('%Y%m%d', strict=False),
)
future=div.filter(
    (pl.col('ann_date') > pl.date(2024, 12, 31)) |
    (pl.col('ex_date') > pl.date(2024, 12, 31))
).height
div=div.filter(
    (pl.col('ann_date').is_null() | (pl.col('ann_date') <= pl.date(2024, 12, 31))) &
    (pl.col('ex_date').is_null() | (pl.col('ex_date') <= pl.date(2024, 12, 31)))
)
panel=pl.read_parquet('data/processed/baostock-daily-20260917/daily_2015_2024.parquet')
panel=panel.filter(pl.col('date')<=date(2020,12,31))
out,rep=rebuild_e16(div,panel,signal_end=date(2020,12,31))
outdir=Path('artifacts/runs/20260920T180001-e16-rebuild-real'); outdir.mkdir(parents=True,exist_ok=False)
out.write_parquet(outdir/'E16.parquet')
(outdir/'report.json').write_text(__import__('json').dumps(rep,ensure_ascii=False,indent=2),encoding='utf-8')
print('files',len(files),'raw_after_freeze',div.height,'future_discarded',future,'out',out.height,'report',rep)


