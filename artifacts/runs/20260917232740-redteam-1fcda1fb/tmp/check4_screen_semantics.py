# -*- coding: utf-8 -*-
"""Red-team check 4: screen.py semantics probes on saved P2 runs.
- exit-while-ST events (entry isST==0, exit isST==1) and whether the exit open
  crossed the ST 5% limit-down without the 10% proxy noticing
- status distribution (blocked exits excluded from labels = tail truncation)
- blocked exits: their counterfactual label using a later tradable session
- suspended-row OHLC in the standardized parquet (bundle poisoning check)
"""
import polars as pl

RUNS = [
    ('R1', r'D:/量化/artifacts/runs/20260917T161253-p2-first-screen-2443f74c/events.parquet'),
    ('R2', r'D:/量化/artifacts/runs/20260917T163824-p2-round2-screen-7f9584bc/events.parquet'),
    ('R3', r'D:/量化/artifacts/runs/20260917T164836-p2-round3-screen-a8702198/events.parquet'),
    ('R5', r'D:/量化/artifacts/runs/20260917T182002-p2-round5-trend-dip-3961e8c1/events.parquet'),
]

px = (
    pl.scan_parquet(r'D:/量化/data/processed/baostock-daily-20260917/daily_2015_2024.parquet')
    .select('symbol', 'date', 'open', 'close', 'preclose', 'tradestatus', 'isST')
    .collect()
)

for tag, path in RUNS:
    ev = pl.read_parquet(path)
    done = ev.filter(pl.col('status') == 'completed_label')
    print(f'== {tag}: events={ev.height} completed={done.height}')
    st_counts = (ev.group_by('status').len().sort('len', descending=True)
                 .head(6).to_dicts())
    print('   status:', {r['status']: r['len'] for r in st_counts})

    j = (done.select('symbol', 'signal_date', 'entry_date', 'exit_date', 'gross_return')
         .join(px.select('symbol', 'date', 'isST', 'open', 'preclose')
               .rename({'date': 'exit_date', 'isST': 'exit_isST',
                        'open': 'exit_open', 'preclose': 'exit_preclose'}),
               on=['symbol', 'exit_date'], how='left'))
    st_exit = j.filter(pl.col('exit_isST') == 1)
    print('   completed events with exit_isST==1:', st_exit.height)
    if st_exit.height:
        st_exit = st_exit.with_columns(
            (pl.col('exit_open') / pl.col('exit_preclose') - 1.0).alias('open_gap'))
        at5 = st_exit.filter((pl.col('open_gap') <= -0.0495) & (pl.col('open_gap') > -0.095))
        print('   of which exit open in [-9.5%,-4.95%] (ST limit-down fills NOT blocked):',
              at5.height)
        if at5.height:
            print(at5.select('symbol', 'exit_date', 'open_gap', 'gross_return').head(8))
        # mean gross of completed with vs without st exits removed
        g_all = j['gross_return'].mean()
        g_no = j.filter(pl.col('exit_isST') != 1)['gross_return'].mean()
        print(f'   mean gross all completed {g_all*100:.4f}pp; excl ST-exit rows {g_no*100:.4f}pp')

    # counterfactual for blocked exits: label mean excluding blocked exit rows
    blocked = ev.filter(pl.col('status').is_in(['exit_limit_down', 'exit_unavailable']))
    if blocked.height:
        print('   blocked exit rows (no label):', blocked.height)

print('=== suspended rows in standardized parquet')
sus = px.filter(pl.col('tradestatus') == 0)
print('suspended rows:', sus.height,
      '| close==0:', int((sus['close'] == 0).sum()),
      '| close<=0:', int((sus['close'] <= 0).sum()),
      '| volume==0:', int((sus['volume'] == 0).sum()),
      '| open==0:', int((sus['open'] == 0).sum()))
sample = sus.filter(pl.col('close') <= 0).head(5)
if sample.height:
    print(sample)
nz = sus.filter((pl.col('close') > 0) & (pl.col('volume') == 0))
print('suspended rows close>0 & volume==0:', nz.height)
if nz.height:
    print(nz.select('symbol', 'date', 'open', 'close', 'preclose').head(5))
