"""Fixed-scene wiring smoke for the self-built RQAlpha bundle (v2.1).

Scene unchanged from v1/v2: 5 stocks + 2 ETFs from project-owned sources,
2024-10-08..2024-12-31 (61 trading days), rqalpha run_func + base.data_bundle_path
pointing at the FULL v2.1 bundle data/processed/rqalpha-bundle-v2-1-20260918
built by src/quant/data/rqalpha_bundle.py.  The strategy buys all 7 securities
on day 1 (odd-lot quantities on purpose), attempts a same-day sell (T+1
rejection) and an odd 55-share order (round-lot rejection), and liquidates on
the penultimate day.

v2.1 additions on top of the 14 v2 assertions:
- A15 (R3-1 fix, red-team run 20260917232740): a SECOND engine scene buys
  510230.XSHG on 2020-08-10 and holds across its share-conversion day
  2020-08-17 (fund_adj 1.2217 -> 6.0059, x4.916019; raw close 5.679 -> 1.188).
  Asserts the position quantity is multiplied by the split ratio
  (ROUND_HALF_UP, exactly what position_model._handle_split does with our
  split_factor row), the marked market value on the conversion day is
  continuous (NOT the raw -78.8% collapse -- no silent equity evaporation,
  no engine error), and the scene ends with exact cash conservation.
- A16: indexes.h5 now carries REAL bars for five indices (v2 had a
  2021-08-05+ bigquant copy for 000300 and a NaN placeholder probe for
  000001.XSHG).  Asserts the five keys, 000300.XSHG 2015-06-12 close ==
  5335.1151 (index_daily batch-manifest registered value), full-window
  sampled equality vs the tushare index_daily chunks (OHLC + vol*100 +
  amount*1000), and sampled close identity vs the retired bigquant copy on
  its overlap window.
- A4 updated: the range-probe key 000001.XSHG is now REAL data (v2 asserted
  the NaN placeholder; that disclosure is void since v2.1).

v2 assertions (14, unchanged in scope, re-verified against the v2.1 bundle):
- A1 stock bar fidelity vs standardized parquet, sampled across the FULL
  2015-2024 range for the 5 scenario stocks;
- A2 ETF bar fidelity vs the tushare fund_daily RAW CHUNKS (primary source):
  OHLC exact, volume == vol*100 shares, total_turnover == amount*1000 yuan,
  limits NaN (disclosed: no ETF limit source);
- A3 calendar == xiaodefa SSE; A4 freeze line + indexes structure;
- A5 instruments + full BaseDataSource file set;
- A6 fills across stocks.h5/funds.h5 at current-bar close; A7 T+1; A8 round lot;
- A9 cash/position conservation; A10 fee config; A11 benchmark path;
- A12 dividend cash lands (000001/601318 real cases);
- A13 (v2) ETF fund_adj -> ex_cum_factor mapping for two dividend cases
  (510050.SH, 510880.SH), including the announcement-verified 510050 2016
  dividend 0.053 yuan/unit;
- A14 (v2) sampled stocks.h5 limit_up/limit_down == tushare stk_limit raw
  values, plus the NaN rule on the 5 header-only chunk days.

Scope statement: this verifies WIRING and data fidelity only.  RQAlpha's
built-in A-share semantics (matching, T+1, lot rules, fees) are exempted
from independent re-verification by user decision
(docs/decisions/2026-09-17-rqalpha-account-engine.md); assertions only check
that our inputs reach the engine unchanged and that the engine applies its
own rules consistently with the configured parameters.
"""
from __future__ import annotations

import json
import os
import pickle
import sys
import time
import traceback
import uuid
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import h5py
import numpy as np

from quant.data import rqalpha_bundle as etl
from quant.data.rqalpha_bundle import (BENCHMARK_OID, RANGE_PROBE_OID,
                                       SMOKE_ETF_FACTOR_CASES, SMOKE_ETFS,
                                       SMOKE_STOCKS, SMOKE_WINDOW)
from quant.research.runs import find_repo_root

DATASET_ID = 'rqalpha-bundle-v2-1-20260918'
INITIAL_CASH = 200_000.0
COMMISSION_RATE = 0.0001   # 万1 全包(含税) -> multiplier 0.125 on the 0.0008 base
MIN_COMMISSION = 5.0
BUY_QTY = {oid: 201 if oid in SMOKE_ETFS else 101 for oid in list(SMOKE_STOCKS) + list(SMOKE_ETFS)}
EXPECTED_LOT_FILL = {oid: 200 if oid in SMOKE_ETFS else 100 for oid in BUY_QTY}
SMOKE_WINDOW_INTS = (SMOKE_WINDOW[0].year * 10000 + SMOKE_WINDOW[0].month * 100 + SMOKE_WINDOW[0].day,
                     SMOKE_WINDOW[1].year * 10000 + SMOKE_WINDOW[1].month * 100 + SMOKE_WINDOW[1].day)

# --- A15 (R3-1) share-conversion scene ------------------------------------
# 510230.XSHG 份额折算 2020-08-17: fund_adj 1.2217 -> 6.0059 (x4.916019),
# raw close 5.679 (prev bar 2020-08-14) -> 1.188 (2020-08-17).  Buy 300 units
# on 2020-08-10, hold across the event, liquidate on 2020-08-21.
SPLIT_SCENE_OID = '510230.XSHG'
SPLIT_SCENE_WINDOW = (datetime(2020, 8, 10).date(), datetime(2020, 8, 21).date())
SPLIT_EVENT_DATE = 20200817
SPLIT_BUY_QTY = 300


class Capture:
    """Collect trades / order rejections / daily account snapshots."""

    def __init__(self) -> None:
        self.trades: list[dict] = []
        self.rejections: list[dict] = []
        self.daily: list[dict] = []

    def on_trade(self, event) -> None:
        t = event.trade
        dt = t.trading_datetime or t.datetime
        d = dt.date()
        self.trades.append({
            'order_book_id': t.order_book_id,
            'side': t.side,               # rqalpha SIDE enum (str-based)
            'date': f'{d.year:04d}{d.month:02d}{d.day:02d}',
            'quantity': int(t.last_quantity),
            'price': float(t.last_price),
            'commission': float(t.commission),
            'tax': float(t.tax),
            'cost': float(t.transaction_cost),
        })

    def on_reject(self, event) -> None:
        self.rejections.append({
            'order_book_id': getattr(event, 'order_book_id', None),
            'reason': str(getattr(event, 'reason', '')),
        })

    def snapshot(self, trading_dt, portfolio) -> None:
        self.daily.append({
            'date': str(trading_dt.date()),
            'cash': float(portfolio.cash),
            'market_value': float(portfolio.market_value),
            'total_value': float(portfolio.total_value),
            'positions': {oid: int(p.quantity) for oid, p in portfolio.positions.items()},
        })


def _sample_indices(n: int) -> list[int]:
    return [0, n // 4, n // 2, 3 * n // 4, n - 1]


def check_bundle(root: Path, bundle_dir: Path, results: dict) -> None:
    """File-level assertions against the original sources."""
    import polars as pl

    # A3 calendar
    cal = np.load(bundle_dir / 'trading_dates.npy', allow_pickle=False)
    expected_cal, _ = etl.load_calendar(
        root, etl.BundleSpec(dataset_id=DATASET_ID, window=etl.FULL_WINDOW,
                             calendar_range=(etl.RESEARCH_START, etl.FREEZE_END)))
    problems = []
    if cal.dtype != np.int64:
        problems.append(f'calendar dtype {cal.dtype} != int64')
    if not np.array_equal(cal, expected_cal):
        problems.append('calendar != xiaodefa SSE is_open==1')
    if not np.all(np.diff(cal) > 0):
        problems.append('calendar not strictly increasing')
    if cal[0] < 20150101 or cal[-1] > 20241231:
        problems.append('calendar crosses research/freeze bounds')
    results['A3_calendar'] = {
        'status': 'PASS' if not problems else 'FAIL',
        'days': int(len(cal)),
        'range': [str(cal[0]), str(cal[-1])],
        'detail': ('trading_dates.npy == xiaodefa SSE calendar (is_open==1), '
                   '2015-01-01..2024-12-31, int64 plain YYYYMMDD'),
        'problems': problems,
    }

    # A1 stock bar fidelity vs standardized parquet, FULL range sampling
    parquet = root / etl.STOCK_DAILY_PARQUET
    symbols = [m['baostock'] for m in SMOKE_STOCKS.values()]
    frame = (
        pl.scan_parquet(parquet)
        .filter(pl.col('symbol').is_in(symbols))
        .select(['symbol', 'date', 'open', 'high', 'low', 'close',
                 'volume', 'amount'])
        .sort(['symbol', 'date'])
        .collect()
    )
    mismatches: list[str] = []
    checked = 0
    with h5py.File(bundle_dir / 'stocks.h5', 'r') as h5:
        for oid, meta in SMOKE_STOCKS.items():
            bars = h5[oid][:]
            if bars.dtype.names != etl.SECURITIES_BAR_DTYPE.names:
                mismatches.append(f'{oid} dtype {bars.dtype.names}')
                continue
            src = frame.filter(pl.col('symbol') == meta['baostock'])
            if src.height != len(bars):
                mismatches.append(f'{oid} row count {len(bars)} != {src.height}')
                continue
            for idx in _sample_indices(src.height):
                row = src.row(idx, named=True)
                d_int = row['date'].year * 10000 + row['date'].month * 100 + row['date'].day
                bar = bars[int(np.searchsorted(bars['datetime'], d_int * 1_000_000))]
                for field in ('open', 'high', 'low', 'close', 'volume', 'total_turnover'):
                    src_val = float(row['amount']) if field == 'total_turnover' else float(row[field])
                    checked += 1
                    if float(bar[field]) != src_val:
                        mismatches.append(f'{oid} {d_int} {field}: {bar[field]} != {src_val}')
    results['A1_stock_bar_fidelity'] = {
        'status': 'PASS' if not mismatches else 'FAIL',
        'values_checked': checked,
        'detail': ('stocks.h5 open/high/low/close/volume/total_turnover == baostock '
                   'parquet (unadjusted), 5 sampled dates across 2015-2024 x 5 '
                   'scenario stocks, exact float equality'),
        'mismatches': mismatches,
    }

    # A2 ETF bar fidelity vs tushare fund_daily raw chunks (v2 primary source)
    mismatches = []
    checked = 0
    fd_dir = root / etl.BATCHES['fund_daily']
    with h5py.File(bundle_dir / 'funds.h5', 'r') as h5:
        for oid, meta in SMOKE_ETFS.items():
            bars = h5[oid][:]
            if bars.dtype.names != etl.SECURITIES_BAR_DTYPE.names:
                mismatches.append(f'{oid} dtype {bars.dtype.names}')
                continue
            src = pl.read_csv(fd_dir / f"chunk_{meta['ts']}.csv").sort('trade_date')
            src = src.filter(pl.col('trade_date') <= 20241231)
            if src.height != len(bars):
                mismatches.append(f'{oid} row count {len(bars)} != {src.height}')
                continue
            for idx in _sample_indices(src.height):
                r = src.row(idx, named=True)
                d_int = int(r['trade_date'])
                bar = bars[int(np.searchsorted(bars['datetime'], d_int * 1_000_000))]
                for field in ('open', 'close', 'high', 'low'):
                    checked += 1
                    if float(bar[field]) != float(r[field]):
                        mismatches.append(f'{oid} {d_int} {field}: {bar[field]} != {r[field]}')
                checked += 2
                if float(bar['volume']) != float(r['vol']) * 100.0:
                    mismatches.append(f"{oid} {d_int} volume: {bar['volume']} != {r['vol']}*100")
                if float(bar['total_turnover']) != float(r['amount']) * 1000.0:
                    mismatches.append(f"{oid} {d_int} total_turnover: "
                                      f"{bar['total_turnover']} != {r['amount']}*1000")
                checked += 2
                if not (np.isnan(bar['limit_up']) and np.isnan(bar['limit_down'])):
                    mismatches.append(f'{oid} {d_int} limits not NaN (no ETF limit source)')
    results['A2_etf_bar_fidelity'] = {
        'status': 'PASS' if not mismatches else 'FAIL',
        'values_checked': checked,
        'detail': ('funds.h5 OHLC == tushare fund_daily raw chunks (unadjusted), '
                   'volume == vol*100 shares, total_turnover == amount*1000 yuan '
                   '(units verified preflight by implied-vwap test), limits NaN '
                   '(no ETF limit source, disclosed), 5 sampled dates x 2 ETFs, '
                   'exact float equality'),
        'mismatches': mismatches,
    }

    # A4 freeze + indexes structure (v2.1: probe key carries REAL data)
    max_dts = {}
    for name in ('stocks.h5', 'funds.h5'):
        with h5py.File(bundle_dir / name, 'r') as h5:
            for oid in h5:
                max_dts[oid] = int(h5[oid]['datetime'][-1]) // 1_000_000
    freeze_ok = all(d <= 20241231 for d in max_dts.values())
    index_problems = []
    expected_index_keys = {oid for oid, *_ in etl.INDEX_SPECS}
    with h5py.File(bundle_dir / 'indexes.h5', 'r') as h5:
        if not expected_index_keys.issubset(set(h5.keys())):
            index_problems.append(f'indexes.h5 missing keys: '
                                  f'{sorted(expected_index_keys - set(h5.keys()))}')
        else:
            probe = h5[RANGE_PROBE_OID][:]
            bench = h5[BENCHMARK_OID][:]
            if (int(probe['datetime'][0]) != int(cal[0]) * 1_000_000
                    or int(probe['datetime'][-1]) != int(cal[-1]) * 1_000_000):
                index_problems.append('probe (000001.XSHG) does not span calendar')
            if not bool(np.all(np.isfinite(probe['close']))) or not bool(np.all(probe['close'] > 0)):
                index_problems.append('probe closes are not real positive values '
                                      '(v2.1 requires real SSE Composite bars)')
            if not bool(np.all(probe['volume'] > 0)):
                index_problems.append('probe volumes not positive (real data expected)')
            if int(bench['datetime'][0]) != int(cal[0]) * 1_000_000:
                index_problems.append('benchmark no longer starts at the window start '
                                      '(v2 bigquant copy began 2021-08-05; v2.1 is full-window)')
            if int(bench['datetime'][-1]) != 20241231 * 1_000_000:
                index_problems.append('benchmark bars end != 2024-12-31')
    results['A4_freeze_and_indexes'] = {
        'status': 'PASS' if freeze_ok and not index_problems else 'FAIL',
        'freeze_check': {'securities_checked': len(max_dts),
                         'max_bar_datetime': max(max_dts.values()) if max_dts else None},
        'detail': ('no bar beyond the 2024-12-31 freeze line across all '
                   f'{len(max_dts)} securities in stocks.h5+funds.h5; indexes.h5 '
                   'carries REAL bars for five indices -- 000300.XSHG full window '
                   f'(v2.1) and the probe key {RANGE_PROBE_OID} as the real SSE '
                   'Composite (the v2 NaN-placeholder warning is void)'),
        'problems': index_problems,
    }

    # A5 instruments + full BaseDataSource file set
    with (bundle_dir / 'instruments.pk').open('rb') as f:
        instruments = {i['order_book_id']: i for i in pickle.load(f)}
    problems = []
    expected = {oid: 'CS' for oid in SMOKE_STOCKS} | {oid: 'ETF' for oid in SMOKE_ETFS}
    for oid, typ in expected.items():
        ins = instruments.get(oid)
        if ins is None:
            problems.append(f'{oid} missing')
            continue
        if ins['type'] != typ or ins['round_lot'] != 100 or ins['market_tplus'] != 1:
            problems.append(f'{oid} bad fields: {ins}')
    n_cs = sum(1 for i in instruments.values() if i['type'] == 'CS')
    n_etf = sum(1 for i in instruments.values() if i['type'] == 'ETF')
    if n_cs != 4745 or n_etf != 1169:
        problems.append(f'instrument counts CS={n_cs} ETF={n_etf} != 4745/1169')
    required_files = ['stocks.h5', 'funds.h5', 'indexes.h5', 'futures.h5', 'dividends.h5',
                      'split_factor.h5', 'ex_cum_factor.h5', 'suspended_days.h5',
                      'st_stock_days.h5', 'trading_dates.npy', 'instruments.pk',
                      'yield_curve.h5', 'share_transformation.json', 'future_info.json',
                      'manifest.json']
    missing = [n for n in required_files if not (bundle_dir / n).exists()]
    if missing:
        problems.append(f'missing files: {missing}')
    results['A5_instruments_and_files'] = {
        'status': 'PASS' if not problems else 'FAIL',
        'counts': {'CS': n_cs, 'ETF': n_etf, 'INDX': len(instruments) - n_cs - n_etf},
        'detail': ('instruments.pk exposes the full pool (4745 CS + 1169 ETF + 1 '
                   'INDX benchmark) with round_lot=100 / market_tplus=1, and every '
                   'file BaseDataSource.__init__ reads exists'),
        'problems': problems,
    }

    # A13 (v2) ETF fund_adj -> ex_cum_factor mapping (dividend cases)
    mismatches = []
    mapping_info = {}
    for ts in SMOKE_ETF_FACTOR_CASES:
        src = pl.read_csv(root / etl.BATCHES['fund_adj'] / f'chunk_{ts}.csv').sort('trade_date')
        src = src.filter(pl.col('trade_date') <= 20241231)
        vals = src['adj_factor'].to_numpy()
        dates = src['trade_date'].to_list()
        changes = [(dates[0], float(vals[0]))]
        for i in range(1, len(vals)):
            if abs(vals[i] - vals[i - 1]) / vals[i - 1] >= 1e-3:
                changes.append((dates[i], float(vals[i])))
        code = ts.split('.')[0]
        oid = f"{code}.{'XSHG' if ts.endswith('SH') else 'XSHE'}"
        with h5py.File(bundle_dir / 'ex_cum_factor.h5', 'r') as h5:
            rows = h5[oid][:]
        exp = [(0, 1.0)] + [(int(d) * 1_000_000, float(v)) for d, v in changes]
        if len(rows) != len(exp):
            mismatches.append(f'{oid} row count {len(rows)} != {len(exp)}')
            continue
        for (sd, sf), (ed, ef) in zip(rows, exp):
            if int(sd) != ed or float(sf) != ef:
                mismatches.append(f'{oid} row {int(sd)},{sf} != {ed},{ef}')
        if len(changes) == 0:
            mismatches.append(f'{oid} has no change-point (not a dividend case)')
        mapping_info[oid] = {'change_points': len(changes),
                             'first': changes[0], 'last': changes[-1]}
        # implied cash dividend at each step must be a plausible per-unit payout
        fd = pl.read_csv(root / etl.BATCHES['fund_daily'] / f'chunk_{ts}.csv').sort('trade_date')
        closes = dict(zip(fd['trade_date'].to_list(), fd['close'].to_list()))
        implied = {}
        prev_f = None
        for d, v in changes:
            if prev_f is not None:
                ex_close = closes.get(d)
                if ex_close is None:
                    mismatches.append(f'{oid} {d}: close missing for implied-div check')
                    continue
                div = ex_close * (v / prev_f - 1)
                implied[d] = round(div, 4)
                if not (0 < div < 1.0):
                    mismatches.append(f'{oid} {d}: implied dividend {div} implausible')
            prev_f = v
        mapping_info[oid]['implied_dividends_per_unit'] = implied
    # known announcement case: 510050.SH 2016-11-29 每份 0.053 元
    known_date, known_div = 20161129, 0.053
    imp510050 = mapping_info.get('510050.XSHG', {}).get('implied_dividends_per_unit', {})
    got = imp510050.get(known_date)
    if got is None:
        mismatches.append(f'known case {known_date} missing from 510050 implied dividends')
    elif abs(got - known_div) > 0.002:
        mismatches.append(f'known case {known_date}: implied {got} != announced {known_div}')
    results['A13_etf_ex_cum_factor_mapping'] = {
        'status': 'PASS' if not mismatches else 'FAIL',
        'mapping': mapping_info,
        'known_case': {'etf': '510050.XSHG', 'ex_date': known_date,
                       'announced_per_unit': known_div, 'implied_per_unit': got,
                       'source': '华夏基金利润分配公告 2016-11-11: 每10份0.53元, '
                                 '权益登记 2016-11-28, 除息 2016-11-29, 发放 2016-12-02'},
        'detail': ('ex_cum_factor rows == [(0,1.0)] + fund_adj change-points '
                   '(relative step >= 1e-3; smaller steps are source revisions); '
                   'rqalpha adjust_bars consumes factor RATIOS only so the '
                   'absolute values carry over directly; each step implies a '
                   'positive per-unit cash dividend; the 510050 2016-11-29 step '
                   'implies 0.053 yuan/unit matching the public announcement'),
        'mismatches': mismatches,
    }

    # A14 (v2) sampled stock limits == tushare stk_limit raw + NaN rule
    mismatches = []
    checked = 0
    rng = np.random.RandomState(20260917)
    pairs = []
    nan_days_checked = []
    with h5py.File(bundle_dir / 'stocks.h5', 'r') as h5:
        all_oids = sorted(h5.keys())
        picks = rng.choice(len(all_oids), size=5, replace=False)
        for pi in picks:
            oid = all_oids[int(pi)]
            bars = h5[oid]
            n = len(bars)
            pos = int(n // 2)
            while pos < n - 1 and int(bars['datetime'][pos]) // 1_000_000 in etl.KNOWN_EMPTY_LIMIT_DAYS:
                pos += 1
            d_int = int(bars['datetime'][pos]) // 1_000_000
            pairs.append((oid, d_int, float(bars['limit_up'][pos]), float(bars['limit_down'][pos])))
        for d in sorted(etl.KNOWN_EMPTY_LIMIT_DAYS):
            bars = h5['000001.XSHE']
            i = int(np.searchsorted(bars['datetime'], d * 1_000_000))
            if i < len(bars) and int(bars['datetime'][i]) == d * 1_000_000:
                nan_days_checked.append(d)
                if not (np.isnan(bars['limit_up'][i]) and np.isnan(bars['limit_down'][i])):
                    mismatches.append(f'000001.XSHE {d}: limits not NaN on empty-source day')
    sl_dir = root / etl.BATCHES['stk_limit']
    for oid, d_int, up, down in pairs:
        if oid in SMOKE_STOCKS:
            ts = SMOKE_STOCKS[oid]['ts']
        else:
            code, ex = oid.split('.')
            ts = f"{code}.{'SH' if ex == 'XSHG' else 'SZ'}"
        src = pl.read_csv(sl_dir / f'chunk_{d_int}.csv')
        row = src.filter(pl.col('ts_code') == ts)
        if row.height != 1:
            mismatches.append(f'{oid} {d_int}: source rows {row.height} != 1')
            continue
        checked += 2
        if up != float(row['up_limit'][0]) or down != float(row['down_limit'][0]):
            mismatches.append(f'{oid} {d_int}: ({up},{down}) != '
                              f"({row['up_limit'][0]},{row['down_limit'][0]})")
    results['A14_stock_limit_prices'] = {
        'status': 'PASS' if not mismatches else 'FAIL',
        'values_checked': checked,
        'sampled_pairs': [{'order_book_id': o, 'date': d} for o, d, _, _ in pairs],
        'nan_rule_days_checked': nan_days_checked,
        'detail': ('stocks.h5 limit_up/limit_down == tushare stk_limit raw chunk '
                   'values for 5 randomly sampled (stock, day) pairs across the '
                   'full pool (seed 20260917); on the 5 header-only chunk days the '
                   'bundle carries NaN (engine treats NaN as no price limit, '
                   'disclosed optimistic fallback)'),
        'mismatches': mismatches,
    }

    # A16 (v2.1) real index bars: five keys, registered value, source equality
    mismatches = []
    checked = 0
    details = {}
    idir = root / etl.INDEX_DAILY_BATCH
    with h5py.File(bundle_dir / 'indexes.h5', 'r') as h5:
        got_keys = set(h5.keys())
        expected_keys = {oid for oid, *_ in etl.INDEX_SPECS}
        if got_keys != expected_keys:
            mismatches.append(f'indexes.h5 keys {sorted(got_keys)} != {sorted(expected_keys)}')
        for oid, ts, _name, _listed in etl.INDEX_SPECS:
            if oid not in got_keys:
                continue
            bars = h5[oid][:]
            if bars.dtype.names != etl.BAR_DTYPE.names:
                mismatches.append(f'{oid} dtype {bars.dtype.names}')
                continue
            src = pl.read_csv(
                idir / f'chunk_{ts}.csv',
                schema_overrides={'trade_date': pl.Int64, 'open': pl.Float64,
                                  'high': pl.Float64, 'low': pl.Float64,
                                  'close': pl.Float64, 'vol': pl.Float64,
                                  'amount': pl.Float64}).sort('trade_date')
            src = src.filter(pl.col('trade_date') <= 20241231)
            if src.height != len(bars):
                mismatches.append(f'{oid} rows {len(bars)} != {src.height}')
                continue
            for idx in _sample_indices(src.height):
                r = src.row(idx, named=True)
                d_int = int(r['trade_date'])
                bar = bars[int(np.searchsorted(bars['datetime'], d_int * 1_000_000))]
                for field in ('open', 'close', 'high', 'low'):
                    checked += 1
                    if float(bar[field]) != float(r[field]):
                        mismatches.append(f'{oid} {d_int} {field}: '
                                          f'{bar[field]} != {r[field]}')
                checked += 2
                if float(bar['volume']) != float(r['vol']) * 100.0:
                    mismatches.append(f"{oid} {d_int} volume != vol*100")
                if float(bar['total_turnover']) != float(r['amount']) * 1000.0:
                    mismatches.append(f"{oid} {d_int} total_turnover != amount*1000")
        # registered spot value from the index_daily batch manifest
        bench = h5[BENCHMARK_OID][:]
        i = int(np.searchsorted(bench['datetime'], 20150612 * 1_000_000))
        got = float(bench['close'][i])
        details['000300_20150612_close'] = got
        if int(bench['datetime'][i]) != 20150612 * 1_000_000 or got != 5335.1151:
            mismatches.append(f'000300.XSHG 2015-06-12 close {got} != 5335.1151 (registered)')
        # close identity vs the retired bigquant copy on its overlap window
        bg = pl.read_csv(root / etl.BENCHMARK_CSV)
        bg = bg.with_columns(pl.col('date').str.slice(0, 10).str.replace_all('-', '')
                             .cast(pl.Int64).alias('d')).sort('d')
        for idx in _sample_indices(bg.height):
            r = bg.row(idx, named=True)
            bar = bench[int(np.searchsorted(bench['datetime'], int(r['d']) * 1_000_000))]
            checked += 1
            if float(bar['close']) != float(r['close']):
                mismatches.append(f"overlap {r['d']}: {bar['close']} != {r['close']}")
    results['A16_index_bars'] = {
        'status': 'PASS' if not mismatches else 'FAIL',
        'values_checked': checked,
        'keys': sorted(got_keys),
        'registered_value_check': details,
        'detail': ('indexes.h5 carries the five REAL tushare index_daily series '
                   '(2431 days each, full window): OHLC == raw chunks, volume == '
                   'vol*100 (手), total_turnover == amount*1000 (千元, unit-proven '
                   'on the bigquant overlap); 000300.XSHG 2015-06-12 close == '
                   '5335.1151 (batch manifest registered value); sampled closes '
                   'identical to the retired bigquant 000300 copy on 2021-08-05+; '
                   'the v2 NaN probe placeholder for 000001.XSHG is replaced by '
                   'the real SSE Composite'),
        'mismatches': mismatches,
    }


def run_engine(bundle_dir: Path, run_dir: Path, results: dict) -> Capture:
    from rqalpha import run_func
    from rqalpha.const import SIDE
    from rqalpha.core.events import EVENT
    from rqalpha.environment import Environment
    from rqalpha.api import order_shares

    capture = Capture()
    state = {'day': 0, 'liquidated': False}

    def init(context):
        env = Environment.get_instance()
        env.event_bus.add_listener(EVENT.TRADE, capture.on_trade)
        env.event_bus.add_listener(EVENT.ORDER_CREATION_REJECT, capture.on_reject)

    def handle_bar(context, bar_dict):
        state['day'] += 1
        if state['day'] == 1:
            # 1) buy all 7 with odd quantities (101 / 201) -> lot-rounded fills
            for oid, qty in BUY_QTY.items():
                order_shares(oid, qty)
            # 2) T+1: same-day sell of the first stock must be rejected
            order_shares(next(iter(SMOKE_STOCKS)), -100)
            # 3) round lot: 55 shares floors to 0 and must be rejected
            order_shares(list(SMOKE_STOCKS)[-1], 55)
            return
        if state['day'] == 60 and not state['liquidated']:
            state['liquidated'] = True
            for oid, pos in list(context.portfolio.positions.items()):
                if pos.quantity > 0:
                    order_shares(oid, -pos.quantity)

    def after_trading(context):
        capture.snapshot(context.now, context.portfolio)

    config = {
        'base': {
            'start_date': SMOKE_WINDOW[0],
            'end_date': SMOKE_WINDOW[1],
            'frequency': '1d',
            'accounts': {'stock': INITIAL_CASH},
            'data_bundle_path': str(bundle_dir),
        },
        'mod': {
            'sys_analyser': {
                'enabled': True,
                'benchmark': BENCHMARK_OID,
                'output_file': str(run_dir / 'result.pkl'),
                'plot': False,
            },
            'sys_transaction_cost': {
                'stock_commission_multiplier': COMMISSION_RATE / 0.0008,
                'tax_multiplier': 0.0,
                'stock_min_commission': MIN_COMMISSION,
            },
        },
    }
    t0 = time.perf_counter()
    result = run_func(config=config, init=init, handle_bar=handle_bar,
                      after_trading=after_trading)
    results['engine_elapsed_seconds'] = round(time.perf_counter() - t0, 3)

    # A6 fills across both store paths, at current-bar close
    buys = [t for t in capture.trades if t['side'] == SIDE.BUY]
    day1_fills = [t for t in buys if t['date'] == '20241008']
    filled_oids = {t['order_book_id'] for t in capture.trades}
    problems = []
    if len(day1_fills) != 7:
        problems.append(f'day1 fills {len(day1_fills)} != 7')
    if filled_oids != set(BUY_QTY):
        problems.append(f'unfilled securities: {set(BUY_QTY) - filled_oids}')
    price_bad = []
    with h5py.File(bundle_dir / 'stocks.h5', 'r') as h5s, \
            h5py.File(bundle_dir / 'funds.h5', 'r') as h5f:
        for t in capture.trades:
            store = h5s if t['order_book_id'] in SMOKE_STOCKS else h5f
            data = store[t['order_book_id']]
            d_int = int(t['date']) * 1_000_000
            pos = int(np.searchsorted(data['datetime'][:], d_int))
            if pos >= len(data) or int(data['datetime'][pos]) != d_int:
                price_bad.append(f"{t['order_book_id']} {t['date']} no bar")
            elif float(data['close'][pos]) != t['price']:
                price_bad.append(f"{t['order_book_id']} {t['date']} {t['price']} != "
                                 f"{float(data['close'][pos])}")
    results['A6_engine_fills'] = {
        'status': 'PASS' if not problems and not price_bad else 'FAIL',
        'trades': [{**t, 'side': str(t['side'])} for t in capture.trades],
        'detail': ('7 day-1 fills across the stocks.h5 (CS) and funds.h5 (ETF) store paths; '
                   'each fill price equals the same-day bar close stored in the bundle '
                   '(rqalpha 1d current-bar-close matching)'),
        'problems': problems + price_bad,
    }

    # A7 T+1
    first_stock = next(iter(SMOKE_STOCKS))
    t1_rejects = [r for r in capture.rejections if r['order_book_id'] == first_stock]
    day1_positions = capture.daily[0]['positions']
    problems = []
    if len(t1_rejects) != 1:
        problems.append(f'expected exactly 1 rejection for {first_stock}, got {len(t1_rejects)}')
    elif not any(m in t1_rejects[0]['reason'] for m in ('可平仓', 'closable')):
        problems.append(f'unexpected rejection reason: {t1_rejects[0]["reason"]}')
    if day1_positions.get(first_stock) != EXPECTED_LOT_FILL[first_stock]:
        problems.append(f'day1 position {day1_positions.get(first_stock)} != '
                        f'{EXPECTED_LOT_FILL[first_stock]} (sell must not have reduced it)')
    results['A7_t_plus_1'] = {
        'status': 'PASS' if not problems else 'FAIL',
        'rejections': t1_rejects,
        'day1_position_first_stock': day1_positions.get(first_stock),
        'detail': ('same-day sell (day-1 buy, day-1 sell 100 shares) rejected by the position '
                   'validator (closable quantity); position remains the bought 100 shares'),
        'problems': problems,
    }

    # A8 round lot
    last_stock = list(SMOKE_STOCKS)[-1]
    odd_rejects = [r for r in capture.rejections if r['order_book_id'] == last_stock]
    problems = []
    if len(odd_rejects) != 1 or not any(
            m in odd_rejects[0]['reason'] for m in ('下单数量为 0', '0 order quantity')):
        problems.append(f'odd-lot rejection wrong: {odd_rejects}')
    if day1_positions.get(last_stock) != EXPECTED_LOT_FILL[last_stock]:
        problems.append(f'day1 position {day1_positions.get(last_stock)} != '
                        f'{EXPECTED_LOT_FILL[last_stock]}')
    bad_qty = [t for t in capture.trades if t['quantity'] % 100 != 0]
    if bad_qty:
        problems.append(f'non-multiple-of-100 fills: {bad_qty}')
    results['A8_round_lot'] = {
        'status': 'PASS' if not problems else 'FAIL',
        'odd_rejections': odd_rejects,
        'day1_position_last_stock': day1_positions.get(last_stock),
        'detail': ('55-share order floored to 0 -> "0 order quantity" creation reject; '
                   '101/201-share orders fill 100/200; every fill quantity is a '
                   'round_lot=100 multiple'),
        'problems': problems,
    }

    # A9 cash & position conservation (dividends of held scenario stocks only)
    held_oids = set(SMOKE_STOCKS) | set(SMOKE_ETFS)
    expected_dividend_cash = 0.0
    dividend_rows = []
    with h5py.File(bundle_dir / 'dividends.h5', 'r') as h5:
        for oid in h5:
            if oid not in held_oids:
                continue  # only scenario securities are ever held in this scene
            for row in h5[oid][:]:
                ex = int(row['ex_dividend_date'])
                if not SMOKE_WINDOW_INTS[0] <= ex <= SMOKE_WINDOW_INTS[1]:
                    continue
                cash = float(row['dividend_cash_before_tax'])
                expected_dividend_cash += cash  # holding == round_lot at each ex-date
                dividend_rows.append({'order_book_id': oid,
                                      'ex_dividend_date': ex,
                                      'payable_date': int(row['payable_date']),
                                      'cash_for_100_shares': cash})
    total_cost = sum(t['cost'] for t in capture.trades)
    buy_notional = sum(t['price'] * t['quantity'] for t in capture.trades if t['side'] == SIDE.BUY)
    sell_notional = sum(t['price'] * t['quantity'] for t in capture.trades if t['side'] == SIDE.SELL)
    final = capture.daily[-1]
    expected_final_cash = (INITIAL_CASH - total_cost + expected_dividend_cash
                           - buy_notional + sell_notional)
    problems = []
    if abs(final['cash'] - expected_final_cash) > 1e-6:
        problems.append(f"final cash {final['cash']} != initial - costs {expected_final_cash}")
    if any(q != 0 for q in final['positions'].values()):
        problems.append(f"non-zero positions at end: {final['positions']}")
    if abs(final['total_value'] - final['cash']) > 1e-6:
        problems.append(f"total_value {final['total_value']} != cash {final['cash']}")
    daily_ok = all(
        abs(d['total_value'] - (d['cash'] + d['market_value'])) < 1e-6 for d in capture.daily)
    if not daily_ok:
        problems.append('total_value != cash + market_value on some day')
    results['A9_conservation'] = {
        'status': 'PASS' if not problems else 'FAIL',
        'initial_cash': INITIAL_CASH,
        'total_transaction_cost': total_cost,
        'expected_dividend_cash': expected_dividend_cash,
        'final_cash': final['cash'],
        'expected_final_cash': expected_final_cash,
        'final_positions': final['positions'],
        'final_total_value': final['total_value'],
        'dividend_rows': dividend_rows,
        'holding_pnl': round(sell_notional - buy_notional, 6),
        'detail': ('final cash == 200000 - transaction costs + dividend cash + holding P&L '
                   '(sell notional - buy notional at the verified fill prices); '
                   'total_value == cash + market_value every day; zero positions at end'),
        'problems': problems,
    }

    # A12 dividend cash lands on payable dates (engine dividends.h5 mapping)
    problems = []
    by_date = {d['date'].replace('-', ''): d['cash'] for d in capture.daily}
    dates_sorted = sorted(by_date)
    for row in dividend_rows:
        ex = str(row['ex_dividend_date'])
        if ex not in by_date:
            problems.append(f'ex-date {ex} not a backtest day')
            continue
        prev_date = dates_sorted[dates_sorted.index(ex) - 1]
        delta = by_date[ex] - by_date[prev_date]
        if abs(delta - row['cash_for_100_shares']) > 1e-6:
            problems.append(f'{row["order_book_id"]} ex {ex}: cash delta {delta} != '
                            f'{row["cash_for_100_shares"]}')
    results['A12_dividend_cash'] = {
        'status': 'PASS' if not problems else 'FAIL',
        'dividend_rows': dividend_rows,
        'detail': ('on each ex-date the account cash rises by exactly '
                   'dividend_cash_before_tax for the held 100-share lot '
                   '(tushare cash_div per share -> bundle cash per round_lot), '
                   'with no trades on those days; real cases 000001.XSHE '
                   '2024-10-10 and 601318.XSHG 2024-10-18'),
        'problems': problems,
    }

    # A10 fee wiring: 万1 全包, min 5, tax 0
    fee_bad = []
    for t in capture.trades:
        expected_fee = max(MIN_COMMISSION, t['price'] * t['quantity'] * COMMISSION_RATE)
        if abs(t['cost'] - expected_fee) > 1e-9 or t['tax'] != 0.0:
            fee_bad.append({**t, 'side': str(t['side']), 'expected_cost': expected_fee})
    results['A10_fee_config'] = {
        'status': 'PASS' if not fee_bad else 'FAIL',
        'bad_trades': fee_bad,
        'detail': 'every trade cost == max(5, notional*0.0001) and tax == 0 (万1全包, min 5 元)',
    }

    # A11 benchmark path through the INDX store
    summary = {}
    if isinstance(result, dict):
        analyser = result.get('sys_analyser') or {}
        summary = analyser.get('summary', {}) if isinstance(analyser, dict) else {}
    bench = summary.get('benchmark_total_returns')
    problems = [] if bench is not None else ['benchmark_total_returns missing from summary']
    results['A11_benchmark_path'] = {
        'status': 'PASS' if not problems else 'FAIL',
        'benchmark': BENCHMARK_OID,
        'benchmark_total_returns': bench,
        'detail': ('sys_analyser computed benchmark returns from the real 000300.XSHG bars '
                   'in indexes.h5 (no missing-data failure)'),
        'problems': problems,
    }
    return capture


def run_split_scene(bundle_dir: Path, run_dir: Path, results: dict) -> None:
    """A15 (R3-1): hold 510230.XSHG across its 2020-08-17 share conversion.

    Verifies OUR split_factor row reaches the engine and that the engine
    applies its own documented split semantics: quantity *= ratio
    (ROUND_HALF_UP) on the ex-date, valuation re-marked to the RAW close ->
    the marked market value stays continuous instead of collapsing by the raw
    price gap (-78.8% here), with no error and exact cash conservation."""
    from rqalpha import run_func
    from rqalpha.const import SIDE
    from rqalpha.core.events import EVENT
    from rqalpha.environment import Environment
    from rqalpha.api import order_shares

    capture = Capture()
    state = {'day': 0}

    def init(context):
        env = Environment.get_instance()
        env.event_bus.add_listener(EVENT.TRADE, capture.on_trade)
        env.event_bus.add_listener(EVENT.ORDER_CREATION_REJECT, capture.on_reject)

    def handle_bar(context, bar_dict):
        state['day'] += 1
        if state['day'] == 1:
            order_shares(SPLIT_SCENE_OID, SPLIT_BUY_QTY)
            return
        if context.now.date() == SPLIT_SCENE_WINDOW[1]:
            pos = context.portfolio.positions.get(SPLIT_SCENE_OID)
            if pos is not None and pos.quantity > 0:
                order_shares(SPLIT_SCENE_OID, -pos.quantity)

    def after_trading(context):
        capture.snapshot(context.now, context.portfolio)

    config = {
        'base': {
            'start_date': SPLIT_SCENE_WINDOW[0],
            'end_date': SPLIT_SCENE_WINDOW[1],
            'frequency': '1d',
            'accounts': {'stock': INITIAL_CASH},
            'data_bundle_path': str(bundle_dir),
        },
        'mod': {
            'sys_analyser': {
                'enabled': True,
                'benchmark': BENCHMARK_OID,
                'output_file': str(run_dir / 'result_split_scene.pkl'),
                'plot': False,
            },
            'sys_transaction_cost': {
                'stock_commission_multiplier': COMMISSION_RATE / 0.0008,
                'tax_multiplier': 0.0,
                'stock_min_commission': MIN_COMMISSION,
            },
        },
    }
    t0 = time.perf_counter()
    run_func(config=config, init=init, handle_bar=handle_bar,
             after_trading=after_trading)
    elapsed = round(time.perf_counter() - t0, 3)

    # bundle-side ground truth for the event
    with h5py.File(bundle_dir / 'split_factor.h5', 'r') as h5:
        rows = h5[SPLIT_SCENE_OID][:]
        hit = rows[rows['ex_date'] == SPLIT_EVENT_DATE * 1_000_000]
        if len(hit) != 1:
            raise AssertionError(f'{SPLIT_SCENE_OID}: expected exactly 1 split row '
                                 f'on {SPLIT_EVENT_DATE}, got {len(hit)}')
        ratio = float(hit['split_factor'][0])
    with h5py.File(bundle_dir / 'funds.h5', 'r') as h5:
        bars = h5[SPLIT_SCENE_OID][:]
        j = int(np.searchsorted(bars['datetime'], SPLIT_EVENT_DATE * 1_000_000))
        close_ex = float(bars['close'][j])
        close_prev = float(bars['close'][j - 1])
    expected_qty = int((Decimal(SPLIT_BUY_QTY) * Decimal(ratio)).quantize(
        Decimal('1'), rounding=ROUND_HALF_UP))
    expected_mv_ratio = expected_qty * close_ex / (SPLIT_BUY_QTY * close_prev)

    daily = {d['date'].replace('-', ''): d for d in capture.daily}
    problems = []
    if str(SPLIT_EVENT_DATE) not in daily:
        raise AssertionError(f'{SPLIT_EVENT_DATE} not in daily snapshots '
                             f'(got {sorted(daily)})')
    prev_date = max(d for d in daily if d < str(SPLIT_EVENT_DATE))
    ev_day = daily[str(SPLIT_EVENT_DATE)]
    prev_day = daily[prev_date]
    qty_prev = prev_day['positions'].get(SPLIT_SCENE_OID, 0)
    qty_ev = ev_day['positions'].get(SPLIT_SCENE_OID, 0)
    if qty_prev != SPLIT_BUY_QTY:
        problems.append(f'position before event {qty_prev} != {SPLIT_BUY_QTY}')
    if qty_ev != expected_qty:
        problems.append(f'event-day quantity {qty_ev} != ROUND_HALF_UP '
                        f'({SPLIT_BUY_QTY} x {ratio}) = {expected_qty}')
    mv_ratio = ev_day['market_value'] / prev_day['market_value']
    if abs(mv_ratio - expected_mv_ratio) > 1e-9 * expected_mv_ratio:
        problems.append(f'event-day MV ratio {mv_ratio} != expected '
                        f'{expected_mv_ratio} (qty x close basis)')
    raw_ratio = close_ex / close_prev
    if not (mv_ratio > 0.5):  # raw path would be 0.2120 -- the R3-1 evaporation
        problems.append(f'MV ratio {mv_ratio} near raw collapse {raw_ratio} '
                        '(equity evaporated)')
    qty_after = daily[min(d for d in daily if d > str(SPLIT_EVENT_DATE))][
        'positions'].get(SPLIT_SCENE_OID, 0)
    if qty_after != expected_qty:
        problems.append(f'post-event quantity {qty_after} != {expected_qty}')
    if capture.rejections:
        problems.append(f'unexpected order rejections: {capture.rejections}')
    # exact conservation (no ETF dividends in this scene/window)
    cost = sum(t['cost'] for t in capture.trades)
    buy_notional = sum(t['price'] * t['quantity'] for t in capture.trades if t['side'] == SIDE.BUY)
    sell_notional = sum(t['price'] * t['quantity'] for t in capture.trades if t['side'] == SIDE.SELL)
    final = capture.daily[-1]
    expected_final_cash = INITIAL_CASH - cost - buy_notional + sell_notional
    if abs(final['cash'] - expected_final_cash) > 1e-6:
        problems.append(f"final cash {final['cash']} != {expected_final_cash}")
    if any(q != 0 for q in final['positions'].values()):
        problems.append(f'non-zero end positions: {final["positions"]}')
    results['A15_etf_share_conversion'] = {
        'status': 'PASS' if not problems else 'FAIL',
        'scene': {'oid': SPLIT_SCENE_OID, 'window': [str(d) for d in SPLIT_SCENE_WINDOW],
                  'buy_qty': SPLIT_BUY_QTY, 'engine_elapsed_seconds': elapsed},
        'event': {'ex_date': SPLIT_EVENT_DATE, 'split_factor_in_bundle': ratio,
                  'close_prev': close_prev, 'close_ex': close_ex,
                  'raw_close_ratio': raw_ratio,
                  'expected_qty_round_half_up': expected_qty,
                  'expected_mv_ratio_with_split': expected_mv_ratio,
                  'observed_mv_ratio': mv_ratio},
        'daily_around_event': [{'date': d, **{k: v for k, v in daily[d].items() if k != 'positions'}}
                               for d in sorted(daily)],
        'trades': [{**t, 'side': str(t['side'])} for t in capture.trades],
        'detail': ('R3-1 fix: held 510230.XSHG across its 2020-08-17 份额折算 '
                   '(split_factor row 4.916019 written from the fund_adj jump); '
                   'quantity 300 -> 1475 (ROUND_HALF_UP x ratio, engine split '
                   'semantics), event-day marked MV ratio == qty_new*close_ex / '
                   '(qty_old*close_prev) -- continuous, vs the raw -78.8% collapse '
                   'the v2 bundle silently produced; no rejections; exact final '
                   'cash conservation'),
        'problems': problems,
    }


def main() -> int:
    root = find_repo_root()
    bundle_dir = root / 'data/processed' / DATASET_ID
    now = datetime.now()
    run_id = now.strftime('%Y%m%dT%H%M%S') + '-rqalpha-bundle-v21-' + uuid.uuid4().hex[:8]
    run_dir = root / 'artifacts' / 'runs' / run_id
    (run_dir / 'logs').mkdir(parents=True, exist_ok=False)

    bundle_manifest = None
    if (bundle_dir / 'manifest.json').exists():
        bundle_manifest = json.loads(
            (bundle_dir / 'manifest.json').read_text(encoding='utf-8'))

    manifest = {
        'run_id': run_id,
        'status': 'running',
        'started_at': now.isoformat(timespec='seconds'),
        'task': ('RQAlpha self-built bundle v2.1 fixed-scene wiring smoke: 5 stocks + '
                 '2 ETFs, 2024-10-08..2024-12-31, on the FULL v2.1 bundle (4745 stocks '
                 '+ 1169 ETFs, 2015-2024, ETF share-conversion splits + five real '
                 'index series); a second scene holds 510230.XSHG across its '
                 '2020-08-17 share conversion (R3-1). The smoke consumes the '
                 'prebuilt bundle and does not rebuild it'),
        'command': [sys.executable, '-X', 'utf8', *sys.argv],
        'env': {
            'python': sys.version.split()[0],
            'cwd': str(Path.cwd()),
            'PYTHONPATH': os.environ.get('PYTHONPATH', ''),
            'pythonpath_note': 'PYTHONPATH=src makes quant.* resolve to src/, not the copied site-packages install',
        },
        'inputs': {
            'bundle_dataset_id': DATASET_ID,
            'bundle_dir': str(bundle_dir),
            'bundle_manifest_summary': (
                {k: bundle_manifest[k] for k in
                 ('dataset_id', 'created_at', 'params', 'freeze')}
                if bundle_manifest else None),
        },
        'outputs': [str(run_dir)],
        'notes': [
            'wiring smoke only: engine built-in A-share semantics are exempted from independent '
            're-verification by user decision (docs/decisions/2026-09-17-rqalpha-account-engine.md)',
            'fee config: 万1全包 -> stock_commission_multiplier=0.125 (0.0008*0.125=0.0001), '
            'tax_multiplier=0, stock_min_commission=5',
            'scenario 1: day1 buy all 7 (101/201 shares), same-day sell attempt (T+1 reject), '
            '55-share odd order (round-lot reject); day60 liquidate all; window contains two '
            'real stock dividends (000001.XSHE ex 2024-10-10, 601318.XSHG ex 2024-10-18) '
            'exercising the dividends.h5 path; v2 adds A13 (ETF fund_adj->ex_cum_factor '
            'mapping incl. announced 510050 2016 case) and A14 (stk_limit raw value '
            'sampling + NaN rule on 5 header-only days)',
            'v2.1 adds A15 (R3-1: second engine scene holding 510230.XSHG across its '
            '2020-08-17 share conversion -- quantity x4.916019 ROUND_HALF_UP, MV continuous, '
            'no evaporation, conservation holds) and A16 (five real index series in '
            'indexes.h5, 000300 2015-06-12 close == 5335.1151 registered value, units '
            'vol*100/amount*1000, bigquant-overlap close identity); A4 now expects REAL '
            '000001.XSHG probe data (v2 NaN placeholder retired)',
        ],
    }
    (run_dir / 'manifest.json').write_text(
        json.dumps(manifest, indent=1, ensure_ascii=False), encoding='utf-8')

    status, error = 'completed', None
    results: dict = {}
    t0 = time.perf_counter()
    capture: Capture | None = None
    try:
        check_bundle(root, bundle_dir, results)
        capture = run_engine(bundle_dir, run_dir, results)
        results['engine_daily_snapshots'] = capture.daily
        run_split_scene(bundle_dir, run_dir, results)
    except Exception:
        status, error = 'failed', traceback.format_exc()
        raise
    finally:
        manifest['status'] = status
        manifest['finished_at'] = datetime.now().isoformat(timespec='seconds')
        manifest['elapsed_seconds'] = round(time.perf_counter() - t0, 2)
        manifest['assertions'] = {
            k: v.get('status') for k, v in results.items()
            if isinstance(v, dict) and 'status' in v
        }
        manifest['error'] = error
        (run_dir / 'manifest.json').write_text(
            json.dumps(manifest, indent=1, ensure_ascii=False, default=str), encoding='utf-8')
        (run_dir / 'assertion_results.json').write_text(
            json.dumps(results, indent=1, ensure_ascii=False, default=str), encoding='utf-8')
        # NOTE: rqalpha patches print inside strategy user modules on failure;
        # sys.stdout.write bypasses that patched user_print.
        sys.stdout.write(json.dumps(manifest['assertions'], ensure_ascii=False, indent=1) + '\n')
    all_pass = all(
        v.get('status') == 'PASS' for v in results.values()
        if isinstance(v, dict) and 'status' in v
    )
    return 0 if status == 'completed' and all_pass else 1


if __name__ == '__main__':
    raise SystemExit(main())
