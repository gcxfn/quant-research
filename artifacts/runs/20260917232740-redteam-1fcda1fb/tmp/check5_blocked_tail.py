# -*- coding: utf-8 -*-
"""Red-team check 5: counterfactual labels for blocked exits (tail truncation)
and suspended-row OHLC in the standardized parquet."""
import polars as pl

px = (
    pl.scan_parquet(r'D:/量化/data/processed/baostock-daily-20260917/daily_2015_2024.parquet')
    .select('symbol', 'date', 'open', 'close', 'preclose', 'volume',
            'tradestatus', 'isST')
    .sort('symbol', 'date')
    .collect()
)
# next tradable open per (symbol,date): shift(-1) within symbol among tradable rows
tradable = px.filter(pl.col('tradestatus') == 1).with_columns(
    pl.col('date').shift(-1).over('symbol').alias('next_date'),
    pl.col('open').shift(-1).over('symbol').alias('next_open'),
)

for tag, path in [
    ('R1', r'D:/量化/artifacts/runs/20260917T161253-p2-first-screen-2443f74c/events.parquet'),
    ('R3', r'D:/量化/artifacts/runs/20260917T164836-p2-round3-screen-a8702198/events.parquet'),
]:
    ev = pl.read_parquet(path)
    done = ev.filter(pl.col('status') == 'completed_label')
    mean_done = done['gross_return'].mean() * 100
    blocked = ev.filter(pl.col('status').is_in(['exit_limit_down', 'exit_unavailable']))
    j = (blocked.select('symbol', 'signal_date', 'entry_date', 'exit_date', 'status')
         .join(px.select('symbol', 'date', 'open').rename({'date': 'entry_date'}),
               on=['symbol', 'entry_date'], how='left')
         .join(tradable.select('symbol', 'date', 'next_date', 'next_open')
               .rename({'date': 'exit_date'}),
               on=['symbol', 'exit_date'], how='left')
         .with_columns((pl.col('next_open') / pl.col('open') - 1.0).alias('gross_cf')))
    have = j.filter(pl.col('gross_cf').is_not_null())
    print(f'== {tag}: completed mean {mean_done:.4f}pp | blocked exits {blocked.height} '
          f'| counterfactual n={have.height} mean_cf {have["gross_cf"].mean()*100:.4f}pp '
          f'median_cf {have["gross_cf"].median()*100:.4f}pp '
          f'worst {have["gross_cf"].min()*100:.2f}pp')

print('=== suspended rows in standardized parquet')
sus = px.filter(pl.col('tradestatus') == 0)
print('suspended rows:', sus.height,
      '| close<=0:', int((sus['close'] <= 0).sum()),
      '| volume==0:', int((sus['volume'] == 0).sum()),
      '| open<=0:', int((sus['open'] <= 0).sum()),
      '| close==preclose:', int((sus['close'] == sus['preclose']).sum()))
bad = sus.filter(pl.col('close') <= 0)
print('sample close<=0 rows:', bad.height)
if bad.height:
    print(bad.select('symbol', 'date', 'open', 'close', 'preclose', 'volume').head(8))
