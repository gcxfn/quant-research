# -*- coding: utf-8 -*-
"""DIAGNOSTIC ONLY (tmp/): pinpoint the engine _frame inference defect.

Wraps band_engine._frame with a probe: try the original (inference-based)
construction; on the known ComputeError, rebuild with the module's OWN
declared schema (the proposed one-line fix) and record the evidence
(inferred-first-100 schema, first diverging row/column/value).  The engine
file itself is NOT touched.  Runs C01 pass-1 only.
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

RUN_DIR = Path(__file__).resolve().parents[1]
ROOT = RUN_DIR.parents[2]
SRC = ROOT / 'src'
sys.path.insert(0, str(SRC))

import polars as pl

import quant.research.etf_rotation as er  # noqa: E402
from quant.research import p2r16_trend_dispersion as r16  # noqa: E402
from quant.backtest import band_engine as be  # noqa: E402
from quant.backtest.band_engine import (  # noqa: E402
    load_dividends_h5, load_split_factor_h5, load_stk_limit_batch,
    run_band_backtest)

D = date
R16_RUN = ROOT / 'artifacts/runs/20260918T083650-p2r16-trend-dispersion-afab466f'
DEV_START, DEV_END = D(2015, 1, 5), D(2020, 12, 31)

evidence = {}


def probe(rows, schema):
    try:
        return pl.DataFrame(rows).select(list(schema)).cast(schema)
    except Exception as exc:
        pinned = pl.DataFrame(rows, schema=schema)
        if 'events' not in evidence:
            # reproduce the original inference to find the divergence point
            try:
                pl.DataFrame(rows[:100])
                inferred = pl.DataFrame(rows[:100]).schema
            except Exception:
                inferred = 'first-100 also fails'
            first_bad = None
            if not isinstance(inferred, str):
                growing = pl.DataFrame(rows[:100])
                for i in range(100, len(rows)):
                    try:
                        growing = pl.concat(
                            [growing, pl.DataFrame([rows[i]], schema=inferred)])
                    except Exception as e2:
                        first_bad = {'row_index': i, 'row': rows[i],
                                     'error': str(e2)[:160]}
                        break
            evidence['events'] = {
                'n_rows': len(rows),
                'first100_inferred_schema': {k: str(v) for k, v in
                                             (inferred.items()
                                              if not isinstance(inferred, str)
                                              else [])},
                'first_divergence': first_bad,
                'original_error': str(exc)[:200],
                'proposed_fix_frame_height': pinned.height,
            }
        return pinned


be._frame = probe

config = json.loads((ROOT / 'configs/experiments/p2r16-trend-dispersion.json')
                    .read_text(encoding='utf-8'))
leg = pl.read_parquet(R16_RUN / 'leg_log.parquet')
cal = r16.market_calendar(ROOT / 'data/processed/baostock-daily-20260917/'
                                 'daily_1999_2024.parquet')
calendar_full = cal['date'].to_list()
idx_of = {d: i for i, d in enumerate(calendar_full)}
all_sig = r16.month_end_sessions(cal).filter(
    (pl.col('s') >= DEV_START) & (pl.col('s') <= DEV_END))['s'].to_list()
signal_days = [d for d in all_sig
               if idx_of[d] + 1 < len(calendar_full)
               and calendar_full[idx_of[d] + 1] <= DEV_END]
hist = r16.build_history_r16(
    ROOT / 'data/processed/baostock-daily-20260917/daily_1999_2024.parquet', cal)
pools_at = r16.pools_by_signal(r16.signal_pools(hist, pl.DataFrame({'s': signal_days})))
symbols = sorted({s for p in pools_at.values() for s in p['ranked']})
hist = None
index_close = r16.load_index_close(
    ROOT / 'data/raw/tushare/index_daily/20260917-r1/chunk_000300.SH.csv'
).filter(pl.col('trade_date') <= r16.FREEZE_LAST)
exposures = r16.t200_month_end_exposures(index_close, calendar_full, signal_days)

cid = 'C01'
K = int(config['configs'][cid]['K'])
panel_symbols = sorted(leg.filter(pl.col('config_id') == cid)['symbol'].unique()
                       .to_list())
leg_c1 = leg.filter((pl.col('config_id') == cid)
                    & (pl.col('plan_date').is_in(signal_days)))
panel_symbols = sorted(leg_c1['symbol'].unique().to_list())
daily = (pl.scan_parquet(ROOT / 'data/processed/baostock-daily-20260917/'
                         'daily_1999_2024.parquet')
         .filter(pl.col('symbol').is_in(panel_symbols))
         .filter((pl.col('date') >= DEV_START) & (pl.col('date') <= DEV_END))
         .select('symbol', 'date', 'open', 'high', 'low', 'close', 'tradestatus')
         .sort('symbol', 'date').collect())
limits = (load_stk_limit_batch(ROOT / 'data/raw/tushare/stk_limit/20260917-r1')[0]
          .rename({'up_limit': 'limit_up', 'down_limit': 'limit_down'})
          .filter(pl.col('symbol').is_in(panel_symbols))
          .filter((pl.col('date') >= DEV_START) & (pl.col('date') <= DEV_END)))
splits = (load_split_factor_h5(BUNDLE / 'split_factor.h5')[0]
          if (BUNDLE := ROOT / 'data/processed/rqalpha-bundle-v2-1-20260918')
          .exists() else None)
splits = splits.filter(pl.col('symbol').is_in(panel_symbols))
dividends = (load_dividends_h5(BUNDLE / 'dividends.h5')[0]
             .filter(pl.col('symbol').is_in(panel_symbols)))

rows = []
next_sig = {signal_days[i]: (signal_days[i + 1] if i + 1 < len(signal_days)
                             else DEV_END) for i in range(len(signal_days))}
close_at = {(s, d): v for s, d, v in zip(daily['symbol'].to_list(),
                                         daily['date'].to_list(),
                                         daily['close'].to_list())}
for t in signal_days:
    g = leg_c1.filter(pl.col('plan_date') == t)
    rank = {s: i + 1 for i, s in enumerate(pools_at[t]['ranked'])}
    for sym in sorted(g.filter(pl.col('kind') == 'buy_open')['symbol'].to_list()):
        rows.append({'symbol': sym, 'signal_date': t, 'side': 'buy',
                     'anchor_price': float(close_at[(sym, t)]),
                     'priority': rank.get(sym, 10 ** 6),
                     'target_notional': round(exposures[t] * 200_000.0 / K, 2),
                     'shares': None, 'expiry_date': next_sig[t]})
    for sym in sorted(g.filter(pl.col('kind') == 'sell_full')['symbol'].to_list()):
        rows.append({'symbol': sym, 'signal_date': t, 'side': 'sell',
                     'anchor_price': float(close_at.get((sym, t), float('nan'))),
                     'priority': rank.get(sym, 10 ** 6),
                     'target_notional': None, 'shares': None,
                     'expiry_date': next_sig[t]})
sig_frame = pl.DataFrame(rows, schema={
    'symbol': pl.String, 'signal_date': pl.Date, 'side': pl.String,
    'anchor_price': pl.Float64, 'priority': pl.Int64,
    'target_notional': pl.Float64, 'shares': pl.Int64, 'expiry_date': pl.Date})
res = run_band_backtest(sig_frame, daily, limits, splits, dividends,
                        initial_cash=200_000.0)
print('C01 pass-1 completed under the schema-pinned probe:',
      f"fills={res.fills.height}, events={res.events.height}, "
      f"equity_end={res.daily['equity'][-1]:,.0f}")
(RUN_DIR / 'tmp' / 'frame_defect_evidence.json').write_text(
    json.dumps(evidence, ensure_ascii=False, indent=2, default=str),
    encoding='utf-8')
print(json.dumps(evidence, ensure_ascii=False, indent=2, default=str)[:1500])
