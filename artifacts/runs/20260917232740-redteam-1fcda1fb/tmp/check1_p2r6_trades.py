# -*- coding: utf-8 -*-
"""Red-team check 1: P2R6 completed run quantitative probes.

- B1 fee drag by year (min-commission effect vs notional) for both freqs
- limit-block counts (entry/exit) for strategy configs and B1
- forced-delist exits across all configs/segments (survivorship-control evidence)
- B1 exit fallback usage: sells not at t+1 open
- slot negative-cash magnitude distribution
Outputs printed values only; no repo files modified.
"""
import json
import polars as pl

RUN = r'D:/量化/artifacts/runs/20260917T231652-p2r6-etf-rotation-7b72501d'

tr = pl.read_parquet(RUN + r'/trades.parquet')
m = json.load(open(RUN + '/metrics.json', encoding='utf-8'))

print('=== trade parquet shape', tr.shape, 'columns', tr.columns)

# B1 fee drag: sum of fees per year per config
b1 = tr.filter(pl.col('config_id').str.starts_with('B1'))
print('\n=== B1 fee drag per year (fees / 200k notional base)')
for cfg, g in b1.group_by(['config_id']):
    g = g.with_columns(pl.col('session').dt.year().alias('y'))
    agg = (g.group_by('y').agg(
        pl.col('fee').sum().alias('fee'),
        pl.col('notional').filter(pl.col('side') == 'buy').sum().alias('buy_not'),
        pl.len().alias('legs'))
        .sort('y'))
    rows = {int(r['y']): (round(r['fee'], 0), int(r['legs'])) for r in agg.iter_rows(named=True)}
    print(cfg['config_id'], rows)

# strategy limit blocks and forced delists
print('\n=== strategy exec stats (from metrics)')
for cid in sorted(m['configs']):
    es = m['configs'][cid]['exec_stats']
    print(cid, 'entry_limit_blocked', es['entry_limit_blocked'],
          'exit_limit_blocked', es['exit_limit_blocked'],
          'entry_suspended', es['entry_suspended'], 'exit_suspended', es['exit_suspended'],
          'forced_delist', es['sells_forced_delist'],
          'no_candidate', es['buys_no_candidate'],
          'cancelled_busy', es['buys_cancelled_slot_busy'],
          'rate %.4f' % es['execution_rate'])

# forced delist positions across configs
pos = pl.read_parquet(RUN + r'/positions.parquet')
if 'exit_kind' in pos.columns:
    fd = pos.filter(pl.col('exit_kind') == 'forced_delist_close')
    print('\n=== forced_delist positions total:', fd.height)
    if fd.height:
        print(fd.group_by(['config_id']).len().sort('config_id').head(20))
        print(fd.select(['config_id', 'code', 'entry_date', 'exit_date', 'pnl']).head(20))

# equity curve trough check for negative-cash configs
eq = pl.read_parquet(RUN + r'/equity_curves.parquet')
print('\n=== equity sanity: min/max per config (net)')
print(eq.group_by('config_id').agg(pl.col('equity_net').min(), pl.col('equity_net').max())
      .sort('config_id'))
