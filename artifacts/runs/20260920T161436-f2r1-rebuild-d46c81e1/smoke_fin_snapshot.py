from pathlib import Path
from datetime import date
import polars as pl
from quant.research.financial_snapshot import development_snapshot
from quant.research.f2r1_rebuild import rebuild_financial_derivation
p=next(x for x in Path('data/raw/tushare/fina_indicator/20260909-r3').glob('chunk_*.csv') if x.stat().st_size>100)
f=pl.read_csv(p,infer_schema_length=10000).head(500)
cols=[c for c in ['ts_code','ann_date','f_ann_date','end_date','roe','n_income_attr_p'] if c in f.columns]
f=f.select(cols)
if 'n_income_attr_p' not in f: f=f.with_columns(pl.lit(1.0).alias('n_income_attr_p'))
snap,rep=development_snapshot(f,dev_end=date(2020,12,31),label='fina_indicator')
out,dr=rebuild_financial_derivation({'fina':snap},cumulative_columns=['n_income_attr_p'],yoy_columns=['n_income_attr_p'],signal_end=date(2020,12,31))
print('raw',f.height,'snapshot',snap.height,'dropped_future',rep['dropped_after_freeze_end'],'derived',out.height)
