# -*- coding: utf-8 -*-
"""Red-team check 3: fee-recost run vs doc claims (exp-20260917-fee-recost.md).
- event count, mean net_diff per window, worsened-trade count
- reverse-engineer implied old/new commission and stamp rates by period
- min-commission binding frequency
- totals cross-check vs doc table
"""
import polars as pl

RUN = r'D:/量化/artifacts/runs/20260917T193747-fee-recost-a571044a'
ev = pl.read_parquet(RUN + r'/recost_events.parquet')
print('rows:', ev.height, 'cols:', ev.columns)
print('windows:', ev.group_by('window').len().sort('window'))

for w in ('dev', 'validation'):
    g = ev.filter(pl.col('window') == w)
    md = g['net_diff'].mean() * 100
    print(f'{w}: n={g.height} mean net_diff={md:.4f}pp')

worse = ev.filter(pl.col('net_diff') < 0)
print('worsened:', worse.height, f'({worse.height/ev.height*100:.1f}%)',
      'mean', worse['net_diff'].mean() * 100)
worse_2023 = worse.filter(pl.col('exit_date') > pl.date(2023, 8, 28))
worse_pre = worse.filter(pl.col('exit_date') <= pl.date(2023, 8, 28))
print('worsened exits > 2023-08-28:', worse_2023.height,
      'mean', worse_2023['net_diff'].mean() * 100)
print('worsened exits <= 2023-08-28:', worse_pre.height,
      'mean', worse_pre['net_diff'].mean() * 100)

# implied rates
ev = ev.with_columns([
    (pl.col('buy_fee_old') / pl.col('entry_notional')).alias('buy_rate_old'),
    (pl.col('buy_fee_new') / pl.col('entry_notional')).alias('buy_rate_new'),
    (pl.col('sell_fee_old') / pl.col('exit_notional')).alias('sell_rate_old'),
    (pl.col('sell_fee_new') / pl.col('exit_notional')).alias('sell_rate_new'),
])
pre = ev.filter(pl.col('exit_date') <= pl.date(2023, 8, 27))
post = ev.filter(pl.col('exit_date') >= pl.date(2023, 8, 28))
for name, g in (('pre-2023-08-28', pre), ('post-2023-08-28', post)):
    print(name, 'n=', g.height)
    print('  buy_rate_old median %.6f  buy_rate_new median %.6f'
          % (g['buy_rate_old'].median(), g['buy_rate_new'].median()))
    print('  sell_rate_old median %.6f  sell_rate_new median %.6f'
          % (g['sell_rate_old'].median(), g['sell_rate_new'].median()))
    print('  min buy_fee_old %.4f (at notional %.0f)' %
          (g['buy_fee_old'].min(), g.sort('entry_notional')['entry_notional'][0]))
    print('  min-commission binding old: %d / %d' %
          ((g['buy_fee_old'] <= 5.000001).sum(), g.height))

tot_old = (ev['buy_fee_old'] + ev['sell_fee_old']).sum()
tot_new = (ev['buy_fee_new'] + ev['sell_fee_new']).sum()
print('total fees old %.0f new %.0f decline %.1f%%' % (tot_old, tot_new, (1 - tot_new / tot_old) * 100))
print('mean entry notional %.0f  exit %.0f' % (ev['entry_notional'].mean(), ev['exit_notional'].mean()))
# per-window totals vs doc
for w in ('dev', 'validation'):
    g = ev.filter(pl.col('window') == w)
    fo = (g['buy_fee_old'] + g['sell_fee_old']).sum()
    fn = (g['buy_fee_new'] + g['sell_fee_new']).sum()
    print(w, 'fees old %.0f new %.0f' % (fo, fn))
# stamp component split: implied stamp_old = sell_rate_old - commission component
# assume old commission = median buy_rate_old (both legs same rate)
for name, g in (('pre', pre),):
    c_old = g['buy_rate_old'].median()
    print(name, 'implied old stamp rate median %.6f' % (g['sell_rate_old'].median() - c_old))
    c_new = g['buy_rate_new'].median()
    print(name, 'implied new stamp rate median %.6f' % (g['sell_rate_new'].median() - c_new))
