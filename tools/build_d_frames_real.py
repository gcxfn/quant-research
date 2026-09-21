from pathlib import Path
from datetime import date
import polars as pl, json
src=Path('artifacts/runs/20260920T190000-d-fund-rebuild-real/financial_intermediate.parquet'); out=Path('artifacts/runs/20260920T190000-d-fund-rebuild-real/D_fund'); out.mkdir(exist_ok=True)
fin=pl.read_parquet(src).filter(pl.col('signal_date')<=date(2020,12,31)).sort(['symbol','end_date','signal_date'])
panel=pl.read_parquet('data/processed/baostock-daily-20260917/daily_2015_2024.parquet').filter(pl.col('date')<=date(2020,12,31)).filter(pl.col('tradestatus')==1)
me=panel.group_by(pl.col('date').dt.year().alias('_y'),pl.col('date').dt.month().alias('_m')).agg(pl.col('date').max().alias('t')).sort('t')['t'].to_list()
rows=[]
for t in me:
 v=fin.filter(pl.col('signal_date')<=t).sort(['symbol','signal_date','end_date']).group_by('symbol').last().with_columns(pl.lit(t).alias('signal_date'))
 rows.append(v)
asof=pl.concat(rows)
asof=asof.with_columns([
 (pl.col('n_cashflow_act')/pl.col('revenue')).alias('D07'),
 (pl.col('n_cashflow_act')/pl.col('total_assets')).alias('D08'),
 ((pl.col('n_income_attr_p')-pl.col('n_cashflow_act'))/pl.col('total_assets')).alias('D15'),
 (pl.col('total_assets')/pl.col('total_hldr_eqy_exc_min_int')).alias('D26'),
 ((pl.col('total_assets')-pl.col('intan_assets')-pl.col('goodwill'))/pl.col('total_hldr_eqy_exc_min_int')).alias('D27'),
 ((pl.col('sell_exp')+pl.col('admin_exp'))/pl.col('revenue')).alias('D28'),
 ((pl.col('n_income_attr_p')-pl.col('profit_dedt'))/pl.col('n_income_attr_p').abs()).alias('D29'),
])
# Change features on the PIT report sequence, calculated before monthly as-of.
seq=fin.sort(['symbol','end_date']).with_columns([
 pl.col('eps').shift(1).over('symbol').alias('_eps_prev'),
 pl.col('q_roe').rolling_sum(4,min_samples=4).over('symbol').alias('D22'),
 pl.col('grossprofit_margin').alias('D23'),
])
seq=seq.with_columns([
 (pl.col('roe')-pl.col('roe_ly')).alias('D13'),(pl.col('grossprofit_margin')-pl.col('grossprofit_margin_ly')).alias('D14'),(pl.col('debt_to_assets')-pl.col('debt_to_assets_ly')).alias('D25'),(pl.col('eps')-pl.col('_eps_prev')).alias('D24'),
 (pl.col('n_cashflow_act')/pl.col('revenue')).alias('D07'),(pl.col('n_cashflow_act')/pl.col('total_assets')).alias('D08'),((pl.col('n_income_attr_p')-pl.col('n_cashflow_act'))/pl.col('total_assets')).alias('D15'),(pl.col('total_assets')/pl.col('total_hldr_eqy_exc_min_int')).alias('D26'),((pl.col('total_assets')-pl.col('intan_assets')-pl.col('goodwill'))/pl.col('total_hldr_eqy_exc_min_int')).alias('D27'),((pl.col('sell_exp')+pl.col('admin_exp'))/pl.col('revenue')).alias('D28'),((pl.col('n_income_attr_p')-pl.col('profit_dedt'))/pl.col('n_income_attr_p').abs()).alias('D29'),
])
# Use sequence-derived columns for monthly as-of.
seq=seq.with_columns((pl.col('n_income_attr_p_q') / pl.col('n_income_attr_p_q').shift(4).over('symbol').abs() - 1.0).alias('D21'))
seq=seq.filter(pl.col('signal_date')<=date(2020,12,31)); rows=[]
for t in me:
 rows.append(seq.filter(pl.col('signal_date')<=t).sort(['symbol','signal_date','end_date']).group_by('symbol').last().with_columns(pl.lit(t).alias('signal_date')))
asof=pl.concat(rows)
base={'D01':'roe','D02':'roa','D03':'grossprofit_margin','D04':'netprofit_margin','D05':'debt_to_assets','D06':'current_ratio','D07':'D07','D08':'D08','D09':'eps','D10':'bps','D11':'tr_yoy','D12':'netprofit_yoy','D13':'D13','D14':'D14','D15':'D15','D18':'assets_turn','D19':'ocf_yoy','D20':'q_sales_yoy','D21':'D21','D22':'D22','D23':'D23','D24':'D24','D25':'D25','D26':'D26','D27':'D27','D28':'D28','D29':'D29','D30':'ocfps'}
for fid,col in base.items(): asof.select(['symbol','signal_date',pl.col(col).alias('value')]).drop_nulls('value').write_parquet(out/(fid+'.parquet'))
# D16/D17 are composites; use within-date ranks from available source fields.
comp=asof.with_columns([(pl.col('roe').rank().over('signal_date')+pl.col('eps').rank().over('signal_date')).alias('D16'),(pl.col('D07').rank().over('signal_date')+(-pl.col('debt_to_assets')).rank().over('signal_date')).alias('D17')])
for fid in ['D16','D17']: comp.select(['symbol','signal_date',pl.col(fid).alias('value')]).drop_nulls('value').write_parquet(out/(fid+'.parquet'))
print('written',len(list(out.glob('D*.parquet'))),'asof_rows',asof.height)


