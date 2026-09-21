from pathlib import Path
import polars as pl
from quant.research.f2r1_rebuild import rebuild_financial_derivation,rebuild_e16
from datetime import date
root=Path('data/raw/tushare')
def read_one(kind):
 p=next((root/kind/'20260909-r3').glob('chunk_*.csv'))
 return pl.read_csv(p,infer_schema_length=10000)
fin=read_one('fina_indicator').head(200)
# Keep only fields accepted by the generic derivation contract.
fin=fin.select([c for c in ['ts_code','ann_date','f_ann_date','end_date','roe','n_income_attr_p'] if c in fin.columns])
if 'n_income_attr_p' not in fin.columns: fin=fin.with_columns(pl.lit(1.0).alias('n_income_attr_p'))
out,rep=rebuild_financial_derivation({'fina':fin},cumulative_columns=['n_income_attr_p'],yoy_columns=['n_income_attr_p'],signal_end=date(2020,12,31))
print('financial_input',fin.height,'financial_output',out.height,'quarter_rows',rep['quarter']['n_rows'])
div=pl.read_csv(next((root/'dividend'/'20260909-r3').glob('chunk_*.csv')),infer_schema_length=10000).head(200)
panel=pl.read_parquet('data/processed/baostock-daily-20260917/daily_2015_2024.parquet').filter(pl.col('date')<=date(2020,12,31)).filter(pl.col('date')==date(2020,12,31))
e,er=rebuild_e16(div,panel,signal_end=date(2020,12,31))
print('div_input',div.height,'e16_output',e.height,'dedup_events',er['deduplicated_events'])
