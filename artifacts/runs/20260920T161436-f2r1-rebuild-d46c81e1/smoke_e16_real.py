from pathlib import Path
from datetime import date
import polars as pl
from quant.research.f2r1_rebuild import rebuild_e16
p=next(x for x in Path('data/raw/tushare/dividend/20260909-r3').glob('chunk_*.csv') if x.stat().st_size>100)
d=pl.read_csv(p,infer_schema_length=10000).head(300)
panel=pl.read_parquet('data/processed/baostock-daily-20260917/daily_2015_2024.parquet').filter(pl.col('date')==date(2020,12,31))
out,rep=rebuild_e16(d,panel,signal_end=date(2020,12,31))
print('input',d.height,'output',out.height,'deduplicated_events',rep['deduplicated_events'],'signals',rep['signal_dates'])
assert out.height >= 0 and rep['deduplicated_events'] <= d.height

