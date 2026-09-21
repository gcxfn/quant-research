"""Build a RQAlpha-native data bundle from project-owned sources.

Contract (verified against rqalpha 6.3.0 installed in .venv, read-only):
- rqalpha/data/base_data_source/storages.py: DayBarStore.DEFAULT_DTYPE
  (datetime int64 + open/close/high/low/volume/total_turnover float64),
  SecuritiesDayBarStore adds limit_up/limit_down; DividendStore/SimpleFactorStore
  are per-order_book_id structured datasets; DateSet files map order_book_id ->
  int YYYYMMDD day arrays; trading_dates.npy is an int array read via
  str(d) -> pandas.to_datetime, i.e. plain YYYYMMDD integers (NOT epoch ns).
- rqalpha/data/base_data_source/data_source.py: BaseDataSource(base_config)
  reads exactly: instruments.pk, stocks.h5, funds.h5, indexes.h5, futures.h5,
  dividends.h5, split_factor.h5, ex_cum_factor.h5, suspended_days.h5,
  st_stock_days.h5, trading_dates.npy, yield_curve.h5, share_transformation.json,
  future_info.json.  futures.h5 / indexes.h5 / stocks.h5 / funds.h5 must exist
  on disk (constructor check); indexes.h5 must contain key '000001.XSHG'
  because BaseDataSource.available_data_range probes that exact key.
- rqalpha/data/bundle/__init__.py (official bundle generators, not
  automatic_update.py which only patches auto-downloadable data):
  dividends rows = book_closure_date (from index) + dividend_cash_before_tax,
  ex_dividend_date, payable_date, round_lot; ex_cum_factor rows = start_date +
  ex_cum_factor with a forced (0, 1.0) prefix row (BaseDataSource re-adds the
  prefix if missing, we write it explicitly).
- datetime encodings (TWO coexisting conventions in rqalpha 6.3.0):
  * day bars (stocks/funds/indexes/futures.h5 'datetime') and simple-factor
    dates (ex_cum_factor 'start_date', split 'ex_date') are written by the
    official generator with convert_date_to_int == year*10^10 + month*10^8 +
    day*10^6, i.e. YYYYMMDDHHMMSS with zero time-of-day for daily bars
    (rqalpha/data/bundle/daybar.py line 40; utils/datetime_func.py lines
    36-42, the pandas-2 int32-overflow fix).  get_bar / history_bars /
    adjust_bars compare against this 14-digit form.
  * trading_dates.npy and dividends row dates use convert_date_to_date_int ==
    plain YYYYMMDD (utils/datetime_func.py lines 31-33); DateSet day lists
    accept both (DateSet._to_dt_int normalises >1e8 by //10^6).

v2 scope (this module evolved in place from the v1 smoke ETL; no copy):
- FULL stock pool from the standardized baostock parquet (boards 60/00/30;
  科创板 sh.688*/sh.689* and 北交所 excluded per AGENTS §1), bars over the
  whole research range 2015-01-01..2024-12-31 (freeze line enforced).
- FULL ETF pool (1169 incl. delisted) with tushare fund_daily as the PRIMARY
  bar source (unadjusted).  Units verified empirically before ingest (40+3
  ETFs, 32k rows): implied vwap = amount*1000/(vol*100) lies inside
  [low, high] for all but rounding-level outliers -> vol is 手 (lots of 100
  shares), amount is 千元.  Bundle stores volume = vol*100 (shares) and
  total_turnover = amount*1000 (yuan).
- Real limit prices for stocks from tushare stk_limit batch 20260917-r1
  (up_limit/down_limit used verbatim).  5 calendar days have header-only
  chunks (20170307/08/09, 20220726, 20230421): the missing-day rule is
  limit_up/limit_down = NaN, which rqalpha treats as "no price limit that
  day" (utils/price_limits.py returns False on non-valid prices) -- an
  optimistic but bounded (5/2431 days) and honestly disclosed fallback.
  tushare stk_limit contains no ETF rows at all -> all ETF limits stay NaN
  (disclosed).
- Stock dividends from tushare dividend batches (r2 = 2015-2017, r3 = 2018+,
  unioned per ex-date day chunk), rows keyed div_proc=='实施'; cash_div is
  PER SHARE pre-tax (verified against real announcements) -> stored x100 as
  per-round_lot cash.  Stock splits/烧转 wired into split_factor.h5 as
  ex_date (14-digit) + split_factor = 1 + stk_div (tushare 每股送转合计);
  consumption: rqalpha position_model._handle_split multiplies the position
  quantity by the ratio and divides price (A-share 送转 semantics).  NOT
  exercised by the fixed smoke scene (zero split events for the 7 scenario
  securities) -- disclosed.
- ETF ex_cum_factor from tushare fund_adj change-points.  Mapping rationale
  (rqalpha source, data/base_data_source/adjust.py): only factor RATIOS
  f(bar_date)/f(adjust_orig) matter, and _factor_for_date takes the last row
  with start_date <= d, i.e. a row (ex_date, f) applies FROM the ex-date.
  tushare adj_factor follows the same hfq convention: f_new/f_prev =
  (close_ex + div)/close_ex on each ex-date (verified: 510050.SH 2016-11-29
  implied 0.0538 yuan/unit vs announced 0.053, plus 8 further year-end
  distributions 0.037-0.055; 510880.SH 10 January distributions 0.05-0.14).
  Hence rows = [(0, 1.0)] + [(_bar_dt(ex_date), f) for each change-point].
  ETF cash-dividend EVENTS have no on-disk source -> ETF dividends.h5 keys
  are absent (engine pays no ETF cash; disclosed).

v2.1 (2026-09-18, fixes red-team R3-1 + full-window index backfill):
- ETF share-conversion events (份额折算/分拆/合并) into split_factor.h5.
  R3-1: fund_adj carries the factor steps but no event reached the engine,
  while positions are valued at RAW prices (portfolio/position.py market_value
  = last_price*quantity) -> on a conversion day equity silently collapsed by
  the raw price gap (e.g. 510230 2020-08-17 raw -78.8%).  Fix rule (fixed
  once, disclosed): scanning fund_adj day-over-day per ETF, a one-day factor
  ratio >= 1.1 or <= 0.9 is a share-conversion event and gets a split row
  with ratio = f(D)/f(D-1); jumps inside (0.9, 1.1) are dividend-class and
  are NOT written as splits.  Direction/orientation (rqalpha
  position_model._handle_split: quantity *= ratio (ROUND_HALF_UP), cached
  price /= ratio; account._on_bar overwrites last_price with the raw close
  each bar): MV ratio on the event day = ratio * close_ex/close_prev, so
  "holding market value continuous across the conversion day" requires
  exactly ratio = factor ratio.  Verified on the known cases: 510230.SH
  2020-08-17 x4.916019, 512670.SH 2021-08-23 x2.0044, 512690.SH 2021-05-17
  x1.9614 (announced 1:1.96) and 2021-12-31 x1.359743 (announced 1:1.36);
  per-event continuity F*close_ex/close_prev listed in the manifest.
- indexes.h5 backfilled with REAL bars for five indices from tushare
  index_daily 20260917-r1 (2015-01-05..2024-12-31 each, 2431 days ==
  calendar): 000300.XSHG replaces the v2 bigquant window copy (2021-08-05+),
  000001.XSHG replaces the NaN range-probe placeholder (the v2 warning
  "probe key must not be consumed as index evidence" is hereby VOID),
  000905/000852/399006 ingested as spares and registered as INDX
  instruments.  Units measured BEFORE ingest against the independent
  bigquant 000300 overlap (826 rows): close identical (max diff 9.1e-13),
  bigquant volume / tushare vol == exactly 100 -> vol is 手 (stored x100),
  bigquant amount[yuan] / tushare amount == exactly 1000 -> index_daily
  amount is 千元, same convention as stocks/funds (stored x1000).  NOTE: a
  first measurement pass compared the wrong join columns and briefly
  suggested amount==yuan; the loader's hard unit guard caught the
  contradiction before ingest and the measurement was corrected.
- Suspended/ST day sets derived from the SAME standardized parquet as the
  bars (tradestatus==0 / isST==1), full pool, full range.
2025+ rows are excluded everywhere (freeze line).  Placeholders are written
only where no eligible source exists and are disclosed in the manifest.
"""
from __future__ import annotations

import csv
import hashlib
import json
import pickle
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

import h5py
import numpy as np
import polars as pl

from quant.data.baostock_daily import FREEZE_END

RESEARCH_START = date(2015, 1, 1)
# Fixed wiring-smoke scene: ~3 months inside 2024, chosen so that the 7
# scenario securities have zero corporate actions, zero suspension and zero
# ST days in-window (except the two exercised dividends, see smoke tool).
SMOKE_WINDOW = (date(2024, 10, 8), date(2024, 12, 31))
FULL_WINDOW = (RESEARCH_START, FREEZE_END)

# --- day-bar dtypes (must match rqalpha storages.py exactly) -------------
BAR_DTYPE = np.dtype([
    ('datetime', np.int64),
    ('open', np.float64),
    ('close', np.float64),
    ('high', np.float64),
    ('low', np.float64),
    ('volume', np.float64),
    ('total_turnover', np.float64),
])
SECURITIES_BAR_DTYPE = np.dtype(BAR_DTYPE.descr + [
    ('limit_up', np.float64),
    ('limit_down', np.float64),
])
DIVIDEND_DTYPE = np.dtype([
    ('book_closure_date', np.int64),
    ('dividend_cash_before_tax', np.float64),
    ('ex_dividend_date', np.int64),
    ('payable_date', np.int64),
    ('round_lot', np.int64),
])
EX_CUM_FACTOR_DTYPE = np.dtype([
    ('start_date', np.int64),
    ('ex_cum_factor', np.float64),
])
# ETF share-conversion rule (fixed, disclosed): one-day fund_adj factor ratio
# >= ETF_SPLIT_JUMP_UP or <= ETF_SPLIT_JUMP_LOW is a conversion event; jumps
# strictly inside the band are dividend-class (no split row).
ETF_SPLIT_JUMP_UP = 1.1
ETF_SPLIT_JUMP_LOW = 0.9

# old rqalpha split format (pre-6.1-compatible branch in
# position_model._get_split_ratio: ratio = cumprod(split_factor) over the
# events since the previous trading day); ex_date uses the 14-digit form
# (position_model._all_splits normalises by //10^6).
SPLIT_DTYPE = np.dtype([
    ('ex_date', np.int64),
    ('split_factor', np.float64),
])

# --- fixed wiring-smoke scenario (subset of the v2 pools) ----------------
# stock: baostock symbol -> rqalpha order_book_id.
SMOKE_STOCKS = {
    '600036.XSHG': {'baostock': 'sh.600036', 'ts': '600036.SH'},
    '601318.XSHG': {'baostock': 'sh.601318', 'ts': '601318.SH'},
    '600000.XSHG': {'baostock': 'sh.600000', 'ts': '600000.SH'},
    '000001.XSHE': {'baostock': 'sz.000001', 'ts': '000001.SZ'},
    '000651.XSHE': {'baostock': 'sz.000651', 'ts': '000651.SZ'},
}
SMOKE_ETFS = {
    '510050.XSHG': {'ts': '510050.SH'},
    '510300.XSHG': {'ts': '510300.SH'},
}
# ETFs with fund_adj change-points used by smoke assertion A13 (mapping +
# known 510050 2016 dividend case 0.053 yuan/unit, ex 2016-11-29).
SMOKE_ETF_FACTOR_CASES = ('510050.SH', '510880.SH')
# rqalpha hardcodes '000001.XSHG' for its available_data_range probe; that
# probe is an INDX key, unrelated to the sz.000001 stock.
RANGE_PROBE_OID = '000001.XSHG'
BENCHMARK_OID = '000300.XSHG'

BATCHES = {
    'trade_cal': 'data/raw/xiaodefa/trade_cal/20260913-bulk1',
    'stk_limit': 'data/raw/tushare/stk_limit/20260917-r1',
    'dividend_r2': 'data/raw/tushare/dividend/20260913-r2',
    'dividend_r3': 'data/raw/tushare/dividend/20260909-r3',
    'adj_factor': 'data/raw/xiaodefa/adj_factor/20260913-bulk1',
    'fund_daily': 'data/raw/tushare/fund_daily/20260917-r1',
    'fund_adj': 'data/raw/tushare/fund_adj/20260917-r1',
    'fund_basic': 'data/raw/tushare/fund_basic/20260909-r1/chunk_market_E.csv',
    'stock_basic': 'data/raw/tushare/stock_basic/20260909-r3',
}
STOCK_DAILY_PARQUET = 'data/processed/baostock-daily-20260917/daily_2015_2024.parquet'
# v2.1: the v2 bigquant benchmark copy (000300.SH_2021-08-05_2024-12-31) is
# RETIRED; index bars come from tushare index_daily 20260917-r1.  The bigquant
# CSV is kept ONLY as the independent cross-source used to measure units.
BENCHMARK_CSV = ('data/raw/bigquant/intraday-t0-20260914/'
                 '000300.SH_2021-08-05_2024-12-31_bar1d.csv')
# stk_limit calendar days whose chunk exists but is header-only (batch
# manifest 20260917-r1): limits fall back to NaN (disclosed rule).
KNOWN_EMPTY_LIMIT_DAYS = {20170307, 20170308, 20170309, 20220726, 20230421}

# Real index bars (tushare index_daily 20260917-r1, one chunk per index).
# 000001.XSHG doubles as rqalpha's available_data_range probe key; since v2.1
# it carries REAL SSE Composite bars (v2 NaN placeholder retired).
INDEX_DAILY_BATCH = 'data/raw/tushare/index_daily/20260917-r1'
INDEX_SPECS = [
    # (order_book_id, ts_code, name, listed_date) -- listed dates are static
    # index facts for instrument metadata only.
    ('000300.XSHG', '000300.SH', '沪深300', '2005-04-08'),
    ('000001.XSHG', '000001.SH', '上证指数', '1991-07-15'),
    ('000905.XSHG', '000905.SH', '中证500', '2007-01-15'),
    ('000852.XSHG', '000852.SH', '中证1000', '2014-10-17'),
    ('399006.XSHE', '399006.SZ', '创业板指', '2010-06-18'),
]


@dataclass(frozen=True)
class BundleSpec:
    dataset_id: str
    window: tuple[date, date]
    calendar_range: tuple[date, date]


def _repo_root() -> Path:
    from quant.research.runs import find_repo_root
    return find_repo_root()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def _d2i(d: date) -> int:
    return d.year * 10000 + d.month * 100 + d.day


def _bar_dt(d_int: int) -> int:
    """Day-bar / simple-factor datetime: convert_date_to_int of a date is
    YYYYMMDDHHMMSS with zero time (rqalpha 6.3.0, see module docstring)."""
    return d_int * 1_000_000


def _module_sha256() -> str:
    return sha256_file(Path(__file__))


def _iso(d: str | None, fallback: str = '2999-12-31') -> str:
    if not d:
        return fallback
    return f'{d[:4]}-{d[4:6]}-{d[6:]}'


# --- pools ---------------------------------------------------------------

def load_stock_pool(root: Path) -> dict[str, dict]:
    """Full stock pool from the standardized parquet: boards sh.60/sz.00/sz.30;
    科创板 (sh.688*/sh.689*) and 北交所 excluded per AGENTS §1.

    Names/list/delist dates from tushare stock_basic 20260909-r3 (L+D chunks;
    P is an empty file).  Codes absent from stock_basic (old codes terminated
    by merger, e.g. 000022.SZ) fall back to first/last bar dates -- disclosed
    in the manifest via the returned 'listed_source'."""
    parquet = root / STOCK_DAILY_PARQUET
    syms = (pl.scan_parquet(parquet).select(pl.col('symbol').unique())
            .collect()['symbol'].to_list())
    pool_syms = sorted(s for s in syms
                       if not (s.startswith('sh.688') or s.startswith('sh.689')
                               or s.startswith('bj.')))
    basic: dict[str, dict] = {}
    for chunk in ('chunk_L.csv', 'chunk_P.csv', 'chunk_D.csv'):
        path = root / BATCHES['stock_basic'] / chunk
        try:
            frame = pl.read_csv(path, infer_schema_length=0)
        except pl.exceptions.NoDataError:
            continue
        for row in frame.iter_rows(named=True):
            basic.setdefault(row['ts_code'], row)
    pool: dict[str, dict] = {}
    fallback_syms: list[str] = []
    for sym in pool_syms:
        ex, code = sym.split('.')
        oid = f"{code}.{'XSHG' if ex == 'sh' else 'XSHE'}"
        ts = f'{code}.{ex.upper()}'
        row = basic.get(ts)
        if row is None:
            fallback_syms.append(sym)
            pool[oid] = {'baostock': sym, 'ts': ts, 'name': oid,
                         'listed_date': None, 'de_listed_date': None,
                         'board_type': 'ChiNext' if code.startswith('3') else 'MainBoard',
                         'listed_source': 'first_bar_fallback'}
        else:
            pool[oid] = {'baostock': sym, 'ts': ts, 'name': row['name'],
                         'listed_date': _iso(row['list_date']),
                         'de_listed_date': _iso(row.get('delist_date')),
                         'board_type': 'ChiNext' if code.startswith('3') else 'MainBoard',
                         'listed_source': 'stock_basic'}
    if fallback_syms:
        fb = (pl.scan_parquet(parquet)
              .filter(pl.col('symbol').is_in(fallback_syms))
              .group_by('symbol')
              .agg(pl.col('date').min().alias('first'), pl.col('date').max().alias('last'))
              .collect())
        by_sym = {r['symbol']: r for r in fb.iter_rows(named=True)}
        for sym in fallback_syms:
            r = by_sym[sym]
            oid = next(o for o, m in pool.items() if m['baostock'] == sym)
            meta = pool[oid]
            meta['listed_date'] = r['first'].isoformat()
            # last bar before the freeze line => terminated in-window
            meta['de_listed_date'] = (r['last'].isoformat()
                                      if r['last'] < FREEZE_END else '2999-12-31')
    return pool


def load_etf_pool(root: Path) -> dict[str, dict]:
    """Full ETF pool identical to the fund_daily/fund_adj batch universe
    (fund_basic 20260909-r1: market==E, 'ETF' in name, list_date<=20241231,
    delist empty or >=20150101), intersected with the fund_daily chunk files
    (chunk existence = bar ground truth).  fund_adj chunk coverage is
    reported per code ('has_adj': chunk exists with data rows)."""
    rows = pl.read_csv(root / BATCHES['fund_basic'], infer_schema_length=0)
    rows = rows.with_columns(pl.col('delist_date').fill_null(''))
    rows = rows.filter(
        (pl.col('market') == 'E')
        & pl.col('name').str.contains('ETF')
        & (pl.col('list_date') <= '20241231')
        & ((pl.col('delist_date') == '') | (pl.col('delist_date') >= '20150101'))
    )
    universe = {r['ts_code']: r for r in rows.iter_rows(named=True)}
    fund_daily_dir = root / BATCHES['fund_daily']
    chunk_codes = {p.stem.removeprefix('chunk_') for p in fund_daily_dir.glob('chunk_*.csv')}
    if chunk_codes != set(universe):
        raise ValueError(
            f'fund_basic filter ({len(universe)}) != fund_daily chunks ({len(chunk_codes)}): '
            f'{sorted(set(universe) ^ chunk_codes)[:10]}')
    fund_adj_dir = root / BATCHES['fund_adj']
    pool: dict[str, dict] = {}
    for ts, row in sorted(universe.items()):
        code, ex = ts.split('.')
        oid = f"{code}.{'XSHG' if ex == 'SH' else 'XSHE'}"
        adj_path = fund_adj_dir / f'chunk_{ts}.csv'
        has_adj = False
        if adj_path.exists():
            try:
                has_adj = pl.read_csv(adj_path).height > 0
            except pl.exceptions.NoDataError:
                has_adj = False
        pool[oid] = {'ts': ts, 'name': row['name'],
                     'listed_date': _iso(row['list_date']),
                     'de_listed_date': _iso(row.get('delist_date')),
                     'fund_type': row.get('fund_type') or '',
                     'has_adj': has_adj}
    return pool


# --- input readers --------------------------------------------------------

def load_calendar(root: Path, spec: BundleSpec) -> tuple[np.ndarray, Path]:
    """SSE trading calendar (is_open==1), clipped to the research range.

    Source: data/raw/xiaodefa/trade_cal/20260913-bulk1 (SSE chunk)."""
    path = root / BATCHES['trade_cal'] / (
        'chunk_exchange-SSE_start_date-20140101_end_date-20261231.csv')
    lo, hi = _d2i(spec.calendar_range[0]), _d2i(spec.calendar_range[1])
    days = []
    with path.open(encoding='utf-8') as f:
        for row in csv.DictReader(f):
            if row['exchange'] != 'SSE' or row['is_open'] != '1':
                continue
            d = int(row['cal_date'])
            if lo <= d <= hi:
                days.append(d)
    days = sorted(days)
    if not days or days[-1] > _d2i(FREEZE_END):
        raise ValueError('calendar violates freeze line or is empty')
    return np.asarray(days, dtype=np.int64), path


def load_stk_limit(root: Path, spec: BundleSpec, calendar: np.ndarray,
                   pool_ts: set[str]) -> tuple[pl.DataFrame, dict]:
    """Real limit prices from tushare stk_limit 20260917-r1 (columns
    trade_date,ts_code,up_limit,down_limit), filtered to the pool.

    Missing-day rule (disclosed): the 5 header-only chunk days
    (20170307/08/09, 20220726, 20230421) simply contribute no rows; after the
    left-join in load_stock_bars those (stock, day) bars carry NaN limits,
    which rqalpha treats as "no price limit" (optimistic fallback, bounded to
    5/2431 days).  Chunk files absent for a calendar day would be a hard
    error (batch is registered complete)."""
    folder = root / BATCHES['stk_limit']
    w0, w1 = _d2i(spec.window[0]), _d2i(spec.window[1])
    frames: list[pl.DataFrame] = []
    zero_row_days: list[int] = []
    used = 0
    rows_read = 0
    for d in calendar:
        d = int(d)
        if not (w0 <= d <= w1):
            continue
        path = folder / f'chunk_{d}.csv'
        if not path.exists():
            raise FileNotFoundError(f'stk_limit chunk missing for calendar day {d}')
        used += 1
        try:
            frame = pl.read_csv(
                path,
                schema_overrides={'trade_date': pl.Int64, 'ts_code': pl.Utf8,
                                  'up_limit': pl.Float64, 'down_limit': pl.Float64})
        except pl.exceptions.NoDataError:
            zero_row_days.append(d)
            continue
        rows_read += frame.height
        if frame.height == 0:
            zero_row_days.append(d)
            continue
        if pool_ts:
            frame = frame.filter(pl.col('ts_code').is_in(pool_ts))
        if frame.height:
            frames.append(frame)
    limits = pl.concat(frames, how='vertical') if frames else pl.DataFrame()
    meta = {'chunks_used': used, 'rows_after_pool_filter': int(limits.height),
            'rows_in_chunks': rows_read, 'zero_row_days': zero_row_days,
            'expected_zero_row_days': sorted(KNOWN_EMPTY_LIMIT_DAYS)}
    if set(zero_row_days) - KNOWN_EMPTY_LIMIT_DAYS:
        meta['unexpected_zero_row_days'] = sorted(set(zero_row_days) - KNOWN_EMPTY_LIMIT_DAYS)
    return limits, meta


def load_stock_bars(root: Path, spec: BundleSpec, calendar: np.ndarray,
                    pool: dict[str, dict]) -> tuple[dict[str, np.ndarray], dict]:
    """Unadjusted daily bars for the full pool from the standardized parquet,
    joined with tushare stk_limit up/down prices.  Volume in shares, amount
    in yuan (P1 manifest).  Suspended rows (tradestatus==0) are kept as-is
    with their source values.  Window is the full research range in v2."""
    w0, w1 = spec.window
    parquet = root / STOCK_DAILY_PARQUET
    ts_by_baostock = {m['baostock']: m['ts'] for m in pool.values()}
    frame = (
        pl.scan_parquet(parquet)
        .filter(pl.col('symbol').is_in(list(ts_by_baostock)))
        .filter((pl.col('date') >= w0) & (pl.col('date') <= w1))
        .select(['symbol', 'date', 'open', 'high', 'low', 'close',
                 'volume', 'amount', 'tradestatus'])
        .sort(['symbol', 'date'])
        .collect()
    )
    limits, limit_meta = load_stk_limit(root, spec, calendar, set(ts_by_baostock.values()))
    limits_by_code: dict[str, tuple[np.ndarray, np.ndarray, np.ndarray]] = {}
    for key, part in limits.partition_by('ts_code', as_dict=True).items():
        lim = part.sort('trade_date')
        limits_by_code[key[0]] = (lim['trade_date'].to_numpy(),
                                  lim['up_limit'].to_numpy(),
                                  lim['down_limit'].to_numpy())
    # run-length boundaries over the sorted frame: zero-copy per-oid slices
    sym_col = frame['symbol']
    rle = sym_col.rle()
    bounds: dict[str, tuple[int, int]] = {}
    off = 0
    for val, length in zip(rle.struct.field('value').to_list(),
                           rle.struct.field('len').to_list()):
        bounds[val] = (off, length)
        off += length
    out: dict[str, np.ndarray] = {}
    nan_limit_rows = 0
    nan_limit_on_suspended = 0
    for oid, meta in pool.items():
        start, length = bounds[meta['baostock']]
        sub = frame.slice(start, length)
        n = sub.height
        if n == 0:
            raise ValueError(f'no bar rows for {oid} in window')
        arr = np.zeros(n, dtype=SECURITIES_BAR_DTYPE)
        arr['datetime'] = (sub.select(
            (pl.col('date').dt.year().cast(pl.Int64) * 10**10
             + pl.col('date').dt.month().cast(pl.Int64) * 10**8
             + pl.col('date').dt.day().cast(pl.Int64) * 10**6).alias('datetime'))
            .to_numpy()[:, 0])
        for field in ('open', 'high', 'low', 'close', 'volume'):
            arr[field] = sub[field].to_numpy()
        arr['total_turnover'] = sub['amount'].to_numpy()
        lim = limits_by_code.get(meta['ts'])
        if lim is None:
            arr['limit_up'] = np.nan
            arr['limit_down'] = np.nan
            nan_limit_rows += n
            nan_limit_on_suspended += int((sub['tradestatus'] == 0.0).sum())
        else:
            lim_dates, lim_up, lim_down = lim
            d_ints = arr['datetime'] // 1_000_000
            pos = np.searchsorted(lim_dates, d_ints)
            hit = (pos < len(lim_dates))
            pos_clipped = np.clip(pos, 0, max(len(lim_dates) - 1, 0))
            hit &= lim_dates[pos_clipped] == d_ints
            arr['limit_up'] = np.where(hit, lim_up[pos_clipped], np.nan)
            arr['limit_down'] = np.where(hit, lim_down[pos_clipped], np.nan)
            nan_limit_rows += int((~hit).sum())
            nan_limit_on_suspended += int(((~hit) & (sub['tradestatus'] == 0.0).to_numpy()).sum())
        out[oid] = arr
    meta = dict(limit_meta)
    meta['bar_rows_with_nan_limit'] = int(nan_limit_rows)
    meta['nan_limit_rows_on_suspended_bars'] = int(nan_limit_on_suspended)
    return out, meta


def load_etf_bars(root: Path, spec: BundleSpec,
                  pool: dict[str, dict]) -> tuple[dict[str, np.ndarray], dict]:
    """ETF daily bars from tushare fund_daily 20260917-r1 (unadjusted, primary
    source).  Units verified preflight (module docstring): volume = vol*100
    shares, total_turnover = amount*1000 yuan; limit columns NaN (tushare
    stk_limit has no ETF rows).  A unit guard recomputes implied vwap for
    every row with vol>0 and amount>0; violations beyond +/-0.5% outside
    [low, high] are a hard error, rounding-level ones are counted."""
    w1 = _d2i(spec.window[1])
    folder = root / BATCHES['fund_daily']
    out: dict[str, np.ndarray] = {}
    checked = minor = severe = 0
    tiny_amount = one_price = 0
    severe_samples: list[str] = []
    for oid, meta in pool.items():
        path = folder / f"chunk_{meta['ts']}.csv"
        if not path.exists():
            raise FileNotFoundError(f'fund_daily chunk missing for {meta["ts"]}')
        frame = pl.read_csv(
            path,
            schema_overrides={'trade_date': pl.Int64, 'vol': pl.Float64,
                              'amount': pl.Float64, 'open': pl.Float64,
                              'high': pl.Float64, 'low': pl.Float64,
                              'close': pl.Float64})
        frame = frame.filter((pl.col('trade_date') <= w1)
                             & pl.col('trade_date').is_not_null()).sort('trade_date')
        n = frame.height
        if n == 0:
            raise ValueError(f'no fund_daily rows for {oid}')
        arr = np.zeros(n, dtype=SECURITIES_BAR_DTYPE)
        arr['datetime'] = [_bar_dt(int(d)) for d in frame['trade_date'].to_list()]
        for field in ('open', 'high', 'low', 'close'):
            arr[field] = frame[field].to_numpy()
        vol = frame['vol'].fill_nan(0.0).to_numpy()
        amount = frame['amount'].fill_nan(0.0).to_numpy()
        arr['volume'] = vol * 100.0          # 手 -> shares (unit-verified)
        arr['total_turnover'] = amount * 1000.0  # 千元 -> yuan (unit-verified)
        arr['limit_up'] = np.nan
        arr['limit_down'] = np.nan
        lo = frame['low'].to_numpy()
        hi = frame['high'].to_numpy()
        mask = (vol > 0) & (amount > 0) & ~np.isnan(lo) & ~np.isnan(hi)
        if mask.any():
            vwap = amount[mask] * 1000.0 / (vol[mask] * 100.0)
            outside = vwap < lo[mask] - 1e-9
            outside |= vwap > hi[mask] + 1e-9
            checked += int(mask.sum())
            idx = np.where(mask)[0]
            # rounding-aware classification: the amount unit (千元, 3 decimals)
            # truncates at 1 yuan; on tiny turnover this alone pushes the
            # implied vwap outside [low, high].  One-price days (low==high,
            # e.g. limit-locked cross-border ETFs) can carry session-extras in
            # amount.  Neither affects bar OHLC/volume fidelity.
            small = amount[idx][outside] < 1.0
            tiny_amount += int(small.sum())
            big_idx = idx[outside][~small]
            real = 0
            if len(big_idx):
                bo = vwap[outside][~small]
                bl = lo[big_idx]
                bh = hi[big_idx]
                bv = vol[big_idx]
                one_price += int((bl == bh).sum())
                err = np.maximum(bl - bo, bo - bh)
                allowed = np.maximum(1.0 / (bv * 100.0), 0.005 * bl)
                not_one_price = bl != bh
                real += int((not_one_price & (err > allowed)).sum())
                if real and len(severe_samples) < 10:
                    severe_samples.extend(
                        f"{oid} {int(frame['trade_date'][i])}" for i in
                        big_idx[not_one_price & (err > allowed)][:10 - len(severe_samples)])
            minor += int(outside.sum())
            severe += real
        out[oid] = arr
    if severe:
        raise ValueError(f'fund_daily unit guard failed: {severe} severe vwap '
                         f'violations beyond rounding/tiny-amount/one-price '
                         f'explanations, samples {severe_samples}')
    return out, {'rows': int(sum(len(a) for a in out.values())),
                 'vwap_checked': checked,
                 'vwap_outside_low_high': minor,
                 'vwap_outside_tiny_amount_lt_1k_yuan': tiny_amount,
                 'vwap_outside_one_price_days': one_price,
                 'vwap_severe_violations': severe,
                 'unit_note': 'volume = fund_daily vol[手]*100 shares; '
                              'total_turnover = amount[千元]*1000 yuan; units '
                              'verified by implied-vwap-inside-[low,high] test'}


def load_dividends_and_splits(root: Path, spec: BundleSpec, calendar: np.ndarray,
                              ts_to_oid: dict[str, str]) -> tuple[dict[str, np.ndarray],
                                                                  dict[str, np.ndarray], dict,
                                                                  list[tuple[Path, str]]]:
    """Stock dividends + splits from tushare dividend chunks (keyed by
    ex_date, div_proc=='实施'), batch r2 (2015-2017) unioned with r3 (2018+)
    in calendar order.

    Unit contract verified against real announcements: cash_div is PER SHARE
    pre-tax -> dividend_cash_before_tax = cash_div * round_lot (100).
    cash_div_tax ignored (smoke runs dividend_tax_enabled=False).
    record_date/pay_date missing -> fallback to ex_dividend_date (disclosed;
    rqalpha pays the cash on payable_date).

    Splits: rows with stk_div > 0 (每股送转合计) emit a split_factor row
    (ex_date 14-digit, split_factor = 1 + stk_div) -- rqalpha multiplies the
    position quantity by this ratio on the ex-date (A-share 送转)."""
    batches = [root / BATCHES['dividend_r2'], root / BATCHES['dividend_r3']]
    per_code: dict[str, list[tuple]] = {c: [] for c in ts_to_oid}
    seen: dict[str, set[tuple]] = {c: set() for c in ts_to_oid}
    used: list[tuple[Path, str]] = []
    w0, w1 = _d2i(spec.window[0]), _d2i(spec.window[1])
    duplicates_dropped = 0
    book_fallback = pay_fallback = pay_equals_ex = 0
    for d in calendar:
        d = int(d)
        if not (w0 <= d <= w1):
            continue
        path = None
        for batch in batches:
            candidate = batch / f'chunk_{d}.csv'
            if candidate.exists():
                path = candidate
                break
        if path is None:
            raise FileNotFoundError(
                f'dividend chunk for {d} missing in both r2 and r3 batches')
        used.append((path, path.parent.name))
        try:
            frame = pl.read_csv(path, infer_schema_length=0)
        except pl.exceptions.NoDataError:
            continue
        if frame.height == 0:
            continue
        for row in frame.iter_rows(named=True):
            code = row['ts_code']
            if code not in per_code or row['div_proc'] != '实施':
                continue
            ex_raw = row.get('ex_date') or ''
            if not ex_raw:
                continue  # 预案/未实施 rows without ex-date
            ex = int(ex_raw)
            book_raw = row.get('record_date') or ''
            pay_raw = row.get('pay_date') or ''
            book = int(book_raw) if book_raw else ex
            pay = int(pay_raw) if pay_raw else ex
            book_fallback += int(not book_raw)
            pay_fallback += int(not pay_raw)
            pay_equals_ex += int(bool(pay_raw) and pay == ex)
            cash = float(row['cash_div']) if row.get('cash_div') else 0.0
            stk = float(row['stk_div']) if row.get('stk_div') else 0.0
            key = (book, cash, ex, pay, stk)
            if key in seen[code]:
                duplicates_dropped += 1
                continue
            seen[code].add(key)
            per_code[code].append((book, cash * 100.0, ex, pay, 100, stk))
    dividends: dict[str, np.ndarray] = {}
    splits: dict[str, np.ndarray] = {}
    n_div = n_split = 0
    split_near_dup_dropped = 0
    cash_multi_rows: list[str] = []
    for code, rows in per_code.items():
        if not rows:
            continue
        rows.sort(key=lambda r: r[2])  # order by ex_dividend_date (searchsorted contract)
        arr = np.zeros(len(rows), dtype=DIVIDEND_DTYPE)
        by_ex: dict[int, list[tuple[float, float]]] = {}
        for i, (book, cash, ex, pay, lot, stk) in enumerate(rows):
            arr[i] = (book, cash, ex, pay, lot)
            by_ex.setdefault(ex, []).append((cash, stk))
        # audit: multiple 实施 rows on the same ex-date with near-equal cash
        # are either two real distributions paid the same day (summed by
        # rqalpha -- kept) or a double-recorded event (audit trail below)
        for ex, cashevs in sorted(by_ex.items()):
            pos_cash = [c for c, _ in cashevs if c > 0]
            if len(pos_cash) > 1:
                mx = max(pos_cash)
                if all(abs(c - pos_cash[0]) <= 1e-6 * max(mx, 1e-9) for c in pos_cash):
                    cash_multi_rows.append(f'{code} {ex} x{len(pos_cash)}')
        srows: list[tuple[int, float]] = []
        for ex, cashevs in sorted(by_ex.items()):
            for cash, stk in cashevs:
                if stk <= 0:
                    continue
                fac = 1.0 + stk
                # rqalpha multiplies same-day split rows; near-identical
                # factors on one ex-date are double-recorded events (e.g.
                # 000033.SZ 2016-04-15) and must not compound
                dup = any(abs(fac - f0) <= 1e-6 * f0 for f0 in
                          (x[1] for x in srows if x[0] == _bar_dt(ex)))
                if dup:
                    split_near_dup_dropped += 1
                    continue
                srows.append((_bar_dt(ex), fac))
        oid = ts_to_oid[code]
        dividends[oid] = arr
        n_div += len(rows)
        if srows:
            sarr = np.zeros(len(srows), dtype=SPLIT_DTYPE)
            for i, (ex, fac) in enumerate(srows):
                sarr[i] = (ex, fac)
            splits[oid] = sarr
            n_split += len(srows)
    meta = {'dividend_rows': n_div, 'split_rows': n_split,
            'duplicate_rows_dropped': duplicates_dropped,
            'split_near_dup_dropped': split_near_dup_dropped,
            'same_day_near_equal_cash_groups': cash_multi_rows[:20],
            'same_day_near_equal_cash_count': len(cash_multi_rows),
            'book_closure_fallback_to_ex': book_fallback,
            'payable_fallback_to_ex': pay_fallback,
            'payable_equals_ex_from_source': pay_equals_ex,
            'codes_with_dividends': len(dividends),
            'codes_with_splits': len(splits)}
    return dividends, splits, meta, used


def load_ex_cum_factors(root: Path, spec: BundleSpec, calendar: np.ndarray,
                        stock_pool: dict[str, dict],
                        etf_pool: dict[str, dict]) -> tuple[dict[str, np.ndarray], dict]:
    """ex_cum_factor rows = [(0, 1.0)] + change-points of the cumulative
    adjustment factor.

    Stocks: xiaodefa (tushare-口径) adj_factor daily chunks -- streaming
    change-point detection (factor value differing from the last observation
    of the same code).  adj_factor is the hfq cumulative factor anchored at
    listing; adjust_bars consumes ratios only, so the absolute values carry
    over directly (module docstring, verified ETF case).

    ETFs: tushare fund_adj per-code chunks; codes with empty/missing chunks
    (159842.SZ) keep the identity row only -- disclosed."""
    folder = root / BATCHES['adj_factor']
    w0, w1 = _d2i(spec.window[0]), _d2i(spec.window[1])
    stock_ts = {m['ts'] for m in stock_pool.values()}
    last_value: dict[str, float] = {}
    changes: dict[str, list[tuple[int, float]]] = {}
    micro_steps = 0
    used = 0
    # tushare/xiaodefa adj_factor carries tiny factor REVISIONS (verified:
    # e.g. 000001.SZ 2020-01-02 109.169 -> 109.1694, even negative steps at
    # 2024-06-25/26) that are source corrections, not corporate actions.
    # Steps below MIN_FACTOR_STEP relative change are not emitted as factor
    # rows (disclosed); every real A-share cash/股票 dividend moves the
    # factor by >= ~0.1%.
    min_step = 1e-3
    for d in calendar:
        d = int(d)
        if not (w0 <= d <= w1):
            continue
        path = folder / f'chunk_{d}.csv'
        if not path.exists():
            raise FileNotFoundError(f'adj_factor chunk missing for calendar day {d}')
        used += 1
        frame = pl.read_csv(
            path, schema_overrides={'ts_code': pl.Utf8, 'trade_date': pl.Int64,
                                    'adj_factor': pl.Float64})
        for code, td, fac in zip(frame['ts_code'], frame['trade_date'],
                                 frame['adj_factor']):
            if code not in stock_ts:
                continue
            prev = last_value.get(code)
            if prev is None:
                changes.setdefault(code, []).append((int(td), float(fac)))
            elif abs(fac - prev) / abs(prev) >= min_step:
                changes.setdefault(code, []).append((int(td), float(fac)))
            else:
                micro_steps += 1
            last_value[code] = fac
    out: dict[str, np.ndarray] = {}
    for oid, meta in stock_pool.items():
        rows = changes.get(meta['ts'], [])
        arr = np.zeros(len(rows) + 1, dtype=EX_CUM_FACTOR_DTYPE)
        arr[0] = (0, 1.0)
        for i, (d, v) in enumerate(rows):
            arr[i + 1] = (_bar_dt(d), v)
        out[oid] = arr
    etf_without_adj = []
    for oid, meta in etf_pool.items():
        if meta['has_adj']:
            frame = pl.read_csv(root / BATCHES['fund_adj'] / f"chunk_{meta['ts']}.csv",
                                schema_overrides={'trade_date': pl.Int64,
                                                  'adj_factor': pl.Float64})
            frame = frame.filter(pl.col('trade_date') <= w1).sort('trade_date')
            vals = frame['adj_factor'].to_numpy()
            dates = frame['trade_date'].to_list()
            rows: list[tuple[int, float]] = []
            for i in range(len(vals)):
                if i == 0 or abs(vals[i] - vals[i - 1]) / abs(vals[i - 1]) >= min_step:
                    rows.append((dates[i], float(vals[i])))
            arr = np.zeros(len(rows) + 1, dtype=EX_CUM_FACTOR_DTYPE)
            arr[0] = (0, 1.0)
            for i, (d, v) in enumerate(rows):
                arr[i + 1] = (_bar_dt(d), v)
        else:
            arr = np.zeros(1, dtype=EX_CUM_FACTOR_DTYPE)
            arr[0] = (0, 1.0)
            etf_without_adj.append(oid)
        out[oid] = arr
    meta = {'adj_factor_chunks_used': used,
            'stock_codes_with_changes': sum(1 for r in changes.values() if r),
            'micro_revision_steps_filtered': micro_steps,
            'micro_step_filter': 'adj_factor steps with relative change < 1e-3 '
                                 'are source revisions, not corporate actions '
                                 '(not emitted as ex_cum_factor rows)',
            'etf_codes_with_adj_data': sum(
                1 for oid, m in etf_pool.items() if m['has_adj']),
            'etf_identity_only': etf_without_adj}
    return out, meta


def load_suspended_st_days(root: Path, spec: BundleSpec,
                           pool: dict[str, dict]) -> tuple[dict[str, np.ndarray],
                                                           dict[str, np.ndarray], dict]:
    """Suspended / ST day sets derived from the SAME standardized parquet as
    the bars (tradestatus==0 / isST==1), full pool over the research range.
    ETFs have no suspension/ST source here -> absent keys, which rqalpha
    DateSet treats as 'never suspended/ST' (disclosed)."""
    parquet = root / STOCK_DAILY_PARQUET
    symbols = sorted({m['baostock'] for m in pool.values()})
    frame = (
        pl.scan_parquet(parquet)
        .filter(pl.col('symbol').is_in(symbols))
        .filter((pl.col('date') >= RESEARCH_START) & (pl.col('date') <= FREEZE_END))
        .select(['symbol', 'date', 'tradestatus', 'isST'])
        .sort(['symbol', 'date'])
        .with_columns((pl.col('date').dt.year().cast(pl.Int64) * 10000
                       + pl.col('date').dt.month().cast(pl.Int64) * 100
                       + pl.col('date').dt.day().cast(pl.Int64)).alias('dint'))
        .collect()
    )
    baostock_to_oid = {m['baostock']: oid for oid, m in pool.items()}
    rle = frame['symbol'].rle()
    bounds: dict[str, tuple[int, int]] = {}
    off = 0
    for val, length in zip(rle.struct.field('value').to_list(),
                           rle.struct.field('len').to_list()):
        bounds[val] = (off, length)
        off += length
    suspended: dict[str, np.ndarray] = {}
    st_days: dict[str, np.ndarray] = {}
    for sym, oid in baostock_to_oid.items():
        if sym not in bounds:
            continue
        start, length = bounds[sym]
        sub = frame.slice(start, length)
        dint = sub['dint'].to_numpy()
        sus = dint[sub['tradestatus'].to_numpy() == 0.0]
        st = dint[sub['isST'].to_numpy() == 1.0]
        if len(sus):
            suspended[oid] = np.asarray(sus, dtype=np.int64)
        if len(st):
            st_days[oid] = np.asarray(st, dtype=np.int64)
    meta = {'codes_with_suspension': len(suspended),
            'codes_with_st_days': len(st_days),
            'suspended_rows': int(sum(len(v) for v in suspended.values())),
            'st_rows': int(sum(len(v) for v in st_days.values()))}
    return suspended, st_days, meta


def load_instruments(stock_pool: dict[str, dict],
                     etf_pool: dict[str, dict]) -> list[dict]:
    """Instrument dicts for instruments.pk.  market_tplus=1 enforces T+1 for
    both CS and ETF; round_lot=100; board_type avoids the KSH round_lot==1
    branch in rqalpha Instrument.round_lot.  Real delist dates are kept for
    delisted stocks/ETFs ('2999-12-31' when still listed).  The five real
    indices are registered as INDX instruments (sys_analyser resolves the
    benchmark from them; their bars live in indexes.h5)."""
    instruments = []
    for oid, meta in sorted(stock_pool.items()):
        instruments.append({
            'order_book_id': oid,
            'symbol': meta['name'],
            'abbrev_symbol': meta['name'],
            'round_lot': 100,
            'exchange': oid.split('.')[-1],
            'type': 'CS',
            'listed_date': meta['listed_date'],
            'de_listed_date': meta['de_listed_date'],
            'board_type': meta['board_type'],
            'market_tplus': 1,
        })
    for oid, meta in sorted(etf_pool.items()):
        instruments.append({
            'order_book_id': oid,
            'symbol': meta['name'],
            'abbrev_symbol': meta['name'],
            'round_lot': 100,
            'exchange': oid.split('.')[-1],
            'type': 'ETF',
            'listed_date': meta['listed_date'],
            'de_listed_date': meta['de_listed_date'],
            'market_tplus': 1,
        })
    for oid, ts, name, listed in INDEX_SPECS:
        instruments.append({
            'order_book_id': oid,
            'symbol': name,
            'abbrev_symbol': name,
            'round_lot': 1,
            'exchange': oid.split('.')[-1],
            'type': 'INDX',
            'listed_date': listed,
            'de_listed_date': '2999-12-31',
        })
    return instruments


def load_index_bars(root: Path, spec: BundleSpec) -> tuple[dict[str, np.ndarray], dict]:
    """Real index daily bars for the five INDEX_SPECS from tushare index_daily
    20260917-r1 (window-clipped).  Units measured, not assumed (module
    docstring, v2.1): volume = vol*100 (vol is 手, proven by the independent
    bigquant 000300 overlap where volume/vol == exactly 100 on all 826 rows),
    total_turnover = amount*1000 (index_daily amount is 千元, proven by the
    same overlap: bigquant-amount[yuan] / tushare-amount == exactly 1000).
    Guards (hard errors): dates must equal the trading calendar exactly; the
    000300 cross-source checks must reproduce."""
    w0, w1 = _d2i(spec.window[0]), _d2i(spec.window[1])
    out: dict[str, np.ndarray] = {}
    per_index: dict[str, dict] = {}
    vwap_stats = {}
    for oid, ts, _name, _listed in INDEX_SPECS:
        path = root / INDEX_DAILY_BATCH / f'chunk_{ts}.csv'
        if not path.exists():
            raise FileNotFoundError(f'index_daily chunk missing for {ts}')
        frame = pl.read_csv(
            path,
            schema_overrides={'trade_date': pl.Int64, 'open': pl.Float64,
                              'high': pl.Float64, 'low': pl.Float64,
                              'close': pl.Float64, 'vol': pl.Float64,
                              'amount': pl.Float64})
        frame = frame.filter((pl.col('trade_date') >= w0)
                             & (pl.col('trade_date') <= w1)).sort('trade_date')
        n = frame.height
        if n == 0:
            raise ValueError(f'no index_daily rows for {oid}')
        arr = np.zeros(n, dtype=BAR_DTYPE)
        arr['datetime'] = [_bar_dt(int(d)) for d in frame['trade_date'].to_list()]
        for field in ('open', 'high', 'low', 'close'):
            arr[field] = frame[field].to_numpy()
        vol = frame['vol'].fill_nan(0.0).to_numpy()
        amount = frame['amount'].fill_nan(0.0).to_numpy()
        arr['volume'] = vol * 100.0          # 手 -> units (cross-source proven)
        arr['total_turnover'] = amount * 1000.0  # 千元 -> yuan (cross-source proven)
        out[oid] = arr
        dates = frame['trade_date'].to_numpy()
        if len(np.unique(dates)) != n:
            raise ValueError(f'{oid}: duplicate index_daily dates')
        # plausibility guard: implied per-share vwap (yuan/share) of the
        # aggregated constituents must be a plausible stock price; an index
        # POINT is not a share price so [low, high] containment does not apply.
        mask = (vol > 0) & (amount > 0)
        vwap = amount[mask] * 1000.0 / (vol[mask] * 100.0)
        vwap_stats[oid] = {'min': float(vwap.min()), 'median': float(np.median(vwap)),
                           'max': float(vwap.max())}
        if vwap.min() <= 0 or vwap.max() > 5000.0:
            raise ValueError(f'{oid}: implausible implied per-share vwap {vwap_stats[oid]}')
        per_index[oid] = {'rows': int(n),
                          'first_date': int(dates[0]), 'last_date': int(dates[-1])}
    # calendar-exactness guard
    calendar, _ = load_calendar(root, spec)
    cal_set = {int(d) for d in calendar}
    for oid in out:
        got = {int(d // 1_000_000) for d in out[oid]['datetime']}
        if got != cal_set:
            raise ValueError(f'{oid}: index dates != trading calendar '
                             f'(missing {sorted(cal_set - got)[:5]}, extra {sorted(got - cal_set)[:5]})')
    # cross-source unit proof vs the retired v2 bigquant benchmark copy
    overlap_path = root / BENCHMARK_CSV
    unit_proof: dict = {'source': 'bigquant ' + BENCHMARK_CSV,
                        'method': 'close identity + exact volume/amount ratios on '
                                  'the 000300 overlap (independent source)'}
    ts300 = out['000300.XSHG']
    bg_rows = []
    with overlap_path.open(encoding='utf-8') as f:
        for row in csv.DictReader(f):
            d = int(row['date'][:10].replace('-', ''))
            if d * 1_000_000 < int(ts300['datetime'][0]):
                continue
            if d * 1_000_000 > int(ts300['datetime'][-1]):
                break
            bg_rows.append((d, float(row['close']), float(row['volume']),
                            float(row['amount'])))
    pos = int(np.searchsorted(ts300['datetime'], bg_rows[0][0] * 1_000_000))
    ts_win = ts300[pos:pos + len(bg_rows)]
    bg_close = np.array([r[1] for r in bg_rows])
    max_close_diff = float(np.max(np.abs(ts_win['close'] - bg_close)))
    vol_ratio = np.array([r[2] for r in bg_rows]) / (ts_win['volume'] / 100.0)
    amt_ratio = np.array([r[3] for r in bg_rows]) / (ts_win['total_turnover'] / 1000.0)
    if max_close_diff > 1e-6:
        raise ValueError(f'000300 close identity vs bigquant failed: {max_close_diff}')
    # bigquant CSV prints amounts with ~10 significant digits -> allow 1e-8
    # relative slack around the exact ratios 100 / 1000
    if not (np.all(np.abs(vol_ratio - 100.0) <= 1e-8 * 100.0)
            and np.all(np.abs(amt_ratio - 1000.0) <= 1e-8 * 1000.0)):
        raise ValueError(f'index unit proof failed: vol ratio {vol_ratio.min()}..'
                         f'{vol_ratio.max()}, amount ratio {amt_ratio.min()}..{amt_ratio.max()}')
    unit_proof.update({'overlap_rows': len(bg_rows),
                       'max_abs_close_diff': max_close_diff,
                       'volume_ratio_min_max': [float(vol_ratio.min()), float(vol_ratio.max())],
                       'amount_ratio_min_max': [float(amt_ratio.min()), float(amt_ratio.max())],
                       'conclusion': 'vol unit = 手 (x100 to units); amount unit = 千元 '
                                     '(x1000 to yuan, same convention as stocks/funds); '
                                     'close identical to the retired bigquant 000300 '
                                     'source on the whole overlap'})
    meta = {'batch': INDEX_DAILY_BATCH,
            'rows': {oid: per_index[oid]['rows'] for oid in per_index},
            'implied_per_share_vwap_yuan': vwap_stats,
            'unit_proof': unit_proof,
            'unit_note': 'volume = index_daily vol[手]*100; total_turnover = '
                         'amount[千元]*1000 yuan; proven on the bigquant 000300 '
                         'overlap (bigquant amount is yuan)'}
    return out, meta


def load_etf_split_events(root: Path, spec: BundleSpec, etf_pool: dict[str, dict],
                          etf_bars: dict[str, np.ndarray]) -> tuple[dict[str, np.ndarray], list[dict], dict]:
    """ETF share-conversion events (red-team R3-1 fix) from tushare fund_adj
    day-over-day factor jumps.

    Rule (fixed, disclosed): a one-day factor ratio >= 1.1 or <= 0.9 is a
    share-conversion event -> split_factor row (ex_date 14-digit,
    split_factor = ratio).  Jumps strictly inside (0.9, 1.1) are
    dividend-class (ETF cash dividends remain unpaid -- separate disclosed
    gap) and get NO split row.

    Orientation (rqalpha position_model._handle_split): quantity *= ratio
    (ROUND_HALF_UP), cached price /= ratio, and account._on_bar re-marks
    last_price to the raw close each bar, so the event-day MV ratio equals
    ratio * close_ex/close_prev; holding MV is continuous iff ratio = the
    factor ratio -- which is what we store.  Continuity is verified per event
    as cont = ratio * close_ex/close_prev(bars) and reported in the manifest
    (values ~1.0 confirm orientation; residuals like 160615.SZ 2022-06-28
    +8.9% are fund_adj absorption noise inherited by the adjusted view, not
    evaporation)."""
    w1 = _d2i(spec.window[1])
    folder = root / BATCHES['fund_adj']
    events: list[dict] = []
    for oid, meta in sorted(etf_pool.items()):
        path = folder / f"chunk_{meta['ts']}.csv"
        if not path.exists():
            continue
        try:
            frame = pl.read_csv(path, schema_overrides={
                'trade_date': pl.Int64, 'adj_factor': pl.Float64})
        except pl.exceptions.NoDataError:
            continue
        # chunk_159842.SZ.csv is header-only with CRLF -> the last column
        # name parses as 'adj_factor\r'; normalise and skip empties.
        frame = frame.rename({c: c.strip() for c in frame.columns})
        if 'adj_factor' not in frame.columns or frame.height == 0:
            continue
        frame = frame.filter(pl.col('trade_date') <= w1).sort('trade_date')
        vals = frame['adj_factor'].to_numpy()
        dates = frame['trade_date'].to_numpy()
        bars = etf_bars.get(oid)
        bar_dates = bars['datetime'] // 1_000_000 if bars is not None else ()
        for i in range(1, len(vals)):
            prev, cur = vals[i - 1], vals[i]
            if not (prev == prev and cur == cur) or prev == 0:
                continue
            ratio = cur / prev
            if not (ratio >= ETF_SPLIT_JUMP_UP or ratio <= ETF_SPLIT_JUMP_LOW):
                continue
            d = int(dates[i])
            has_bar = bool(len(bar_dates)) and bool(
                (bar_dates == d).any())
            ev = {'order_book_id': oid, 'ex_date': d,
                  'ratio': float(ratio),
                  'fund_adj_prev': float(prev), 'fund_adj': float(cur)}
            if has_bar:
                j = int(np.searchsorted(bar_dates, d))
                close_ex = float(bars['close'][j])
                close_prev = float(bars['close'][j - 1]) if j > 0 else None
                ev.update({'close_prev': close_prev, 'close_ex': close_ex,
                           'raw_close_ratio': (close_ex / close_prev)
                                              if close_prev else None,
                           'mv_continuity_with_split':
                               (ratio * close_ex / close_prev) if close_prev else None})
            else:
                ev.update({'close_prev': None, 'close_ex': None,
                           'raw_close_ratio': None,
                           'mv_continuity_with_split': None,
                           'no_bar_on_ex_date': True})
            events.append(ev)
    events.sort(key=lambda e: (e['ex_date'], e['order_book_id']))
    splits: dict[str, np.ndarray] = {}
    for ev in events:
        splits.setdefault(ev['order_book_id'], []).append(
            (_bar_dt(ev['ex_date']), ev['ratio']))
    out: dict[str, np.ndarray] = {}
    for oid, rows in splits.items():
        arr = np.zeros(len(rows), dtype=SPLIT_DTYPE)
        for i, (ex, fac) in enumerate(rows):
            arr[i] = (ex, fac)
        out[oid] = arr
    conts = [e['mv_continuity_with_split'] for e in events
             if e.get('mv_continuity_with_split') is not None]
    meta = {'rule': f'fund_adj one-day factor ratio >= {ETF_SPLIT_JUMP_UP} or '
                    f'<= {ETF_SPLIT_JUMP_LOW} -> split row with ratio = factor '
                    'ratio; jumps inside (0.9, 1.1) are dividend-class, no '
                    'split row (ETF cash stays unpaid per the dividends gap '
                    'disclosure)',
            'orientation_basis': ('rqalpha position_model._handle_split: quantity *= '
                                  'ratio (ROUND_HALF_UP), cached price /= ratio; account '
                                  '_on_bar re-marks last_price to the raw close -> MV '
                                  'ratio on ex-date = ratio * close_ex/close_prev; '
                                  'continuity iff ratio = factor ratio'),
            'events': events,
            'count': len(events),
            'etfs_with_events': len({e['order_book_id'] for e in events}),
            'events_without_bar_on_ex_date': [
                f"{e['order_book_id']} {e['ex_date']}" for e in events
                if e.get('no_bar_on_ex_date')],
            'mv_continuity_min': float(min(conts)) if conts else None,
            'mv_continuity_max': float(max(conts)) if conts else None}
    return out, events, meta


def build_bundle(root: Path, out_dir: Path, spec: BundleSpec, *,
                 pool_limit: int | None = None,
                 hash_inputs: bool = True) -> dict:
    """Write the full BaseDataSource file set into out_dir and return the
    bundle manifest (inputs with sha256, params, data-quality notes,
    placeholders, step timings).

    pool_limit (pilot/budgeting only) trims each pool to the first N sorted
    oids and skips input hashing; the pilot manifest discloses this."""
    timers: dict[str, float] = {}

    def tick(name: str, t0: float) -> None:
        timers[name] = round(time.perf_counter() - t0, 2)

    t_build = time.perf_counter()
    out_dir.mkdir(parents=True, exist_ok=True)
    inputs: list[dict] = []
    placeholders: list[str] = []

    def record_input(role: str, path: Path, note: str = '') -> None:
        inputs.append({'role': role, 'path': str(path.relative_to(root)),
                       'sha256': sha256_file(path), 'note': note})

    # 0. pools ------------------------------------------------------------
    t0 = time.perf_counter()
    stock_pool = load_stock_pool(root)
    etf_pool = load_etf_pool(root)
    pool_note = None
    if pool_limit is not None:
        stock_pool = dict(sorted(stock_pool.items())[:pool_limit])
        etf_pool = dict(sorted(etf_pool.items())[:pool_limit])
        pool_note = (f'PILOT: pools trimmed to {pool_limit} sorted oids each; '
                     'input hashing skipped; not a complete bundle')
    else:
        missing = ([o for o in SMOKE_STOCKS if o not in stock_pool]
                   + [o for o in SMOKE_ETFS if o not in etf_pool])
        if missing:
            raise ValueError(f'smoke scenario securities missing from pools: {missing}')
    tick('pools', t0)

    # 1. calendar ---------------------------------------------------------
    t0 = time.perf_counter()
    calendar, cal_path = load_calendar(root, spec)
    np.save(out_dir / 'trading_dates.npy', calendar, allow_pickle=False)
    if hash_inputs:
        record_input('trade_calendar', cal_path)
    tick('calendar', t0)

    # 2. stock bars + real limits ----------------------------------------
    t0 = time.perf_counter()
    stock_bars, limit_meta = load_stock_bars(root, spec, calendar, stock_pool)
    with h5py.File(out_dir / 'stocks.h5', 'w') as h5:
        for oid in sorted(stock_bars):
            h5.create_dataset(oid, data=stock_bars[oid])
    if hash_inputs:
        record_input('stock_daily_bars', root / STOCK_DAILY_PARQUET,
                     'unadjusted (adjustflag=3), volume shares, amount yuan')
        folder = root / BATCHES['stk_limit']
        for d in calendar:
            d = int(d)
            if spec.window[0] <= date(d // 10000, d // 100 % 100, d % 100) <= spec.window[1]:
                record_input('stk_limit', folder / f'chunk_{d}.csv')
    tick('stock_bars', t0)

    # 3. ETF bars (funds.h5 native channel, tushare primary) --------------
    t0 = time.perf_counter()
    etf_bars, etf_meta = load_etf_bars(root, spec, etf_pool)
    with h5py.File(out_dir / 'funds.h5', 'w') as h5:
        for oid in sorted(etf_bars):
            h5.create_dataset(oid, data=etf_bars[oid])
    if hash_inputs:
        folder = root / BATCHES['fund_daily']
        for oid in sorted(etf_pool):
            record_input('fund_daily', folder / f"chunk_{etf_pool[oid]['ts']}.csv",
                         f'{oid} (unadjusted; vol 手*100, amount 千元*1000)')
    tick('etf_bars', t0)

    # 4. stock dividends + splits + ETF share-conversion events (v2.1 R3-1) --
    t0 = time.perf_counter()
    ts_to_oid = {m['ts']: oid for oid, m in stock_pool.items()}
    dividends, splits, div_meta, div_used = load_dividends_and_splits(
        root, spec, calendar, ts_to_oid)
    etf_bars_for_split = etf_bars  # loaded in step 3
    etf_splits, etf_split_events, etf_split_meta = load_etf_split_events(
        root, spec, etf_pool, etf_bars_for_split)
    collided = set(splits) & set(etf_splits)
    if collided:
        raise ValueError(f'split key collision stock vs ETF: {sorted(collided)}')
    all_splits = {**splits, **etf_splits}
    with h5py.File(out_dir / 'dividends.h5', 'w') as h5:
        for oid in sorted(dividends):
            h5.create_dataset(oid, data=dividends[oid])
    with h5py.File(out_dir / 'split_factor.h5', 'w') as h5:
        for oid in sorted(all_splits):
            h5.create_dataset(oid, data=all_splits[oid])
    if hash_inputs:
        for path, batch in sorted(div_used, key=lambda x: (x[0].parent.name, x[0].name)):
            record_input('dividends', path, f'batch {batch}')
    tick('dividends_splits', t0)

    # 5. ex_cum_factor (stocks: xiaodefa adj_factor; ETFs: fund_adj) ------
    t0 = time.perf_counter()
    ex_factors, ex_meta = load_ex_cum_factors(root, spec, calendar, stock_pool, etf_pool)
    with h5py.File(out_dir / 'ex_cum_factor.h5', 'w') as h5:
        for oid in sorted(ex_factors):
            h5.create_dataset(oid, data=ex_factors[oid])
    if hash_inputs:
        folder = root / BATCHES['adj_factor']
        for d in calendar:
            d = int(d)
            if spec.window[0] <= date(d // 10000, d // 100 % 100, d % 100) <= spec.window[1]:
                record_input('adj_factor', folder / f'chunk_{d}.csv')
        folder = root / BATCHES['fund_adj']
        for oid in sorted(etf_pool):
            path = folder / f"chunk_{etf_pool[oid]['ts']}.csv"
            if path.exists():
                record_input('fund_adj', path, f'{oid}')
    tick('ex_cum_factor', t0)

    # consistency guard (reporting, not fatal): every adj-factor change must
    # have a matching dividend row on the same ex-date, otherwise price is
    # adjusted without cash paid (or 送转 without split row).
    t0 = time.perf_counter()
    div_ex = {oid: {int(r['ex_dividend_date']) for r in rows}
              for oid, rows in dividends.items()}
    mismatch: list[str] = []
    no_factor_dividend: list[str] = []
    for oid, arr in ex_factors.items():
        if oid in etf_pool:
            continue  # ETF factor mapping has no dividend source (disclosed)
        # skip the (0, 1.0) prefix AND the window-start baseline row (the
        # first observation carries the pre-window accumulated factor; it is
        # not an in-window corporate action)
        ch = {int(d) // 1_000_000 for d in arr['start_date'][2:] if int(d) != 0}
        miss = ch - div_ex.get(oid, set())
        for d in sorted(miss):
            mismatch.append(f'{oid} {d}')
        for d in sorted(div_ex.get(oid, set()) - ch):
            no_factor_dividend.append(f'{oid} {d}')
    tick('consistency_guard', t0)

    # 6. futures.h5 must exist (BaseDataSource builds FutureDayBarStore at
    # init even with no futures configured); no futures in this bundle.
    with h5py.File(out_dir / 'futures.h5', 'w'):
        pass
    placeholders.append('futures.h5 empty: no futures instruments in this bundle')

    # 7. suspended / ST day sets
    t0 = time.perf_counter()
    suspended, st_days, sus_meta = load_suspended_st_days(root, spec, stock_pool)
    with h5py.File(out_dir / 'suspended_days.h5', 'w') as h5:
        for oid in sorted(suspended):
            h5.create_dataset(oid, data=suspended[oid])
    with h5py.File(out_dir / 'st_stock_days.h5', 'w') as h5:
        for oid in sorted(st_days):
            h5.create_dataset(oid, data=st_days[oid])
    tick('suspended_st', t0)

    # 8. indexes: REAL bars for five indices (v2.1: full-window 000300 +
    # real 000001 probe key + three spares; v2's NaN probe is retired)
    t0 = time.perf_counter()
    index_bars, index_meta = load_index_bars(root, spec)
    if hash_inputs:
        folder = root / INDEX_DAILY_BATCH
        for _oid, ts, _n, _l in INDEX_SPECS:
            record_input('index_daily', folder / f'chunk_{ts}.csv',
                         'volume vol[手]*100, turnover amount[千元]*1000 '
                         '(unit-proven on the bigquant 000300 overlap)')
    with h5py.File(out_dir / 'indexes.h5', 'w') as h5:
        for oid in sorted(index_bars):
            h5.create_dataset(oid, data=index_bars[oid])
    tick('indexes', t0)

    # 9. instruments
    t0 = time.perf_counter()
    instruments = load_instruments(stock_pool, etf_pool)
    with (out_dir / 'instruments.pk').open('wb') as f:
        pickle.dump(instruments, f, protocol=2)
    if hash_inputs:
        for chunk in ('chunk_L.csv', 'chunk_P.csv', 'chunk_D.csv'):
            path = root / BATCHES['stock_basic'] / chunk
            if path.exists() and path.stat().st_size > 0:
                record_input('stock_basic', path)
        record_input('fund_basic', root / BATCHES['fund_basic'])
    tick('instruments', t0)

    # 10. yield_curve placeholder (no bond-yield source; analyser needs >=1 row
    # for its risk-free-rate query, so all-zero rows on calendar days)
    yc_tenors = ('0S', '1M', '3M', '6M', '1Y', '2Y', '3Y', '5Y', '7Y', '10Y')
    yc_dtype = np.dtype([('date', np.int64)] + [(t, np.float64) for t in yc_tenors])
    yc = np.zeros(len(calendar), dtype=yc_dtype)
    yc['date'] = calendar
    with h5py.File(out_dir / 'yield_curve.h5', 'w') as h5:
        h5.create_dataset('data', data=yc)
    placeholders.append(
        'yield_curve.h5 all-zero placeholder rows on calendar days: no bond-yield '
        'source in data/raw; analyser queries a risk-free rate at tear-down and an '
        'empty table hard-crashes (YieldCurveStore.get_yield_curve IndexError), so '
        'risk-free rate is the disclosed neutral 0.0')

    # 11. share_transformation / future_info structural placeholders
    (out_dir / 'share_transformation.json').write_text('{}', encoding='utf-8')
    placeholders.append(
        'share_transformation.json empty: no share-transformation source '
        '(share mergers/successor conversions are NOT modeled; delisted-in-window '
        'stocks keep their own instruments with real de_listed_date)')
    future_info = [{
        'underlying_symbol': 'PLACEHOLDER',
        'close_commission_ratio': 0.0,
        'close_commission_today_ratio': 0.0,
        'commission_type': 'by_volume',
        'open_commission_ratio': 0.0,
        'margin_rate': 0.0,
        'tick_size': 1.0,
    }]
    (out_dir / 'future_info.json').write_text(
        json.dumps(future_info, indent=1), encoding='utf-8')
    placeholders.append(
        'future_info.json single structural placeholder (rqalpha FutureInfoStore '
        'requires margin_rate on first item at load); no futures in bundle')

    # --- v2 disclosures ---------------------------------------------------
    placeholders.append(
        'stock limit prices: tushare stk_limit verbatim; (stock, day) pairs with '
        'no source row (the 5 header-only chunk days '
        f'{sorted(KNOWN_EMPTY_LIMIT_DAYS)} plus mostly suspended-day omissions) '
        'carry limit_up/limit_down = NaN, which rqalpha treats as NO price '
        'limit that day (optimistic fallback; '
        f"{limit_meta['bar_rows_with_nan_limit']} of "
        f"{sum(len(a) for a in stock_bars.values())} bar rows affected, of which "
        f"{limit_meta['nan_limit_rows_on_suspended_bars']} are suspended-day rows "
        'that cannot trade anyway)')
    placeholders.append(
        'ETF limit_up/limit_down all NaN: tushare stk_limit contains no ETF rows '
        '(verified); no ETF limit source on disk')
    placeholders.append(
        'ETF dividends absent from dividends.h5: no ETF cash-dividend event '
        'source on disk (fund_adj only carries factor steps); the engine will '
        'NOT pay ETF cash dividends, while ETF price factors ARE adjusted -- '
        'ETF total-return accounting under-counts dividends until an event '
        'source is registered.  v2.1 splits off the SHARE-CONVERSION-class '
        f'factor jumps (one-day ratio >= {ETF_SPLIT_JUMP_UP} or <= '
        f'{ETF_SPLIT_JUMP_LOW}) into split_factor.h5; dividend-class jumps '
        '(inside the band) remain unpaid cash')
    placeholders.append(
        'ETF suspension unknown -> no suspended_days/st keys for ETF oids '
        '(rqalpha DateSet then reports never-suspended).  Known interaction '
        'with v2.1 splits: 159919.SZ 2019-01-11 converts on a day its bars '
        'lack (suspended); the split row still fires (quantity x1.110937) '
        'while the stale pre-conversion price is marked until the next real '
        'bar -- the marked MV is overstated for that one day, then correct '
        '(no evaporation)')
    placeholders.append(
        'split_factor.h5 = stock 送转 rows (1 + stk_div, tushare dividend '
        'batches) PLUS v2.1 ETF share-conversion rows (rule + per-event list '
        'in data_quality.etf_split_events); engine consumption (position '
        'quantity x ratio, price / ratio) verified by source reading; the '
        'R3-1 wiring smoke scene exercises the ETF path end-to-end')
    if ex_meta['etf_identity_only']:
        placeholders.append(
            'ETF ex_cum_factor identity-only (empty/missing fund_adj chunk): '
            + ', '.join(ex_meta['etf_identity_only']))
    placeholders.append(
        'indexes.h5 v2.1: five REAL index series from tushare index_daily '
        '20260917-r1 (000300 full window replaces the v2 bigquant 2021-08-05+ '
        'copy; 000001.XSHG -- rqalpha\'s available_data_range probe key -- '
        'carries the real SSE Composite, the v2 warning "probe key must not '
        'be consumed as index evidence" is VOID; 000905/000852/399006 '
        'ingested as spares and registered as INDX instruments).  Index '
        'volume/turnover units proven on the bigquant overlap (see '
        'data_quality.index_daily.unit_proof)')
    if pool_note:
        placeholders.append(pool_note)

    # freeze check: nothing beyond 2024-12-31 anywhere (bar datetimes are
    # 14-digit YYYYMMDDHHMMSS -> compare the YYYYMMDD part)
    max_dt = 0
    for name in ('stocks.h5', 'funds.h5', 'indexes.h5'):
        with h5py.File(out_dir / name, 'r') as h5:
            for oid in h5:
                max_dt = max(max_dt, int(h5[oid]['datetime'][-1]) // 1_000_000)
    if max_dt > _d2i(FREEZE_END):
        raise ValueError(f'freeze violation: max bar datetime {max_dt}')

    manifest = {
        'dataset_id': spec.dataset_id,
        'created_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'generator': 'src/quant/data/rqalpha_bundle.py',
        'generator_sha256': _module_sha256(),
        'contract_source': (
            'rqalpha 6.3.0 in .venv: data/base_data_source/{storages,data_source,adjust}.py, '
            'data/bundle/{__init__,daybar}.py (official generators); day-bar & factor '
            'dates = convert_date_to_int (YYYYMMDDHHMMSS, zero time), calendar npy & '
            'dividend dates = convert_date_to_date_int (plain YYYYMMDD); split ex_date '
            '14-digit (position_model._all_splits normalises //10^6); adjust_bars uses '
            'factor ratios only'),
        'params': {
            'bar_window': [spec.window[0].isoformat(), spec.window[1].isoformat()],
            'calendar_range': [spec.calendar_range[0].isoformat(), spec.calendar_range[1].isoformat()],
            'calendar_days': int(len(calendar)),
            'stock_pool_size': len(stock_pool),
            'etf_pool_size': len(etf_pool),
            'pool_limit': pool_limit,
            'scenario_stocks': {oid: m['baostock'] for oid, m in SMOKE_STOCKS.items()},
            'scenario_etfs': {oid: m['ts'] for oid, m in SMOKE_ETFS.items()},
            'benchmark_oid': BENCHMARK_OID,
            'range_probe_oid': RANGE_PROBE_OID,
            'range_probe_note': ('v2.1: 000001.XSHG carries the REAL SSE Composite; '
                                 'the v2 NaN-placeholder warning is void'),
            'index_bars': {oid: ts for oid, ts, _n, _l in INDEX_SPECS},
            'etf_split_rule': etf_split_meta['rule'],
            'pools_source': {'stocks': STOCK_DAILY_PARQUET + ' (60/00/30 boards; 688/689/bj excluded)',
                             'etfs': BATCHES['fund_basic'] + ' (market==E, ETF in name)'},
        },
        'data_quality': {
            'stk_limit': limit_meta,
            'fund_daily_units': etf_meta,
            'dividends_splits': {**div_meta,
                                 'etf_conversion_split_rows': len(etf_split_events),
                                 'total_split_codes': len(all_splits)},
            'etf_split_events': etf_split_meta,
            'index_daily': index_meta,
            'ex_cum_factor': ex_meta,
            'suspended_st': sus_meta,
            'adj_change_without_dividend_row': {'count': len(mismatch),
                                                'samples': mismatch[:20]},
            'dividend_row_without_adj_change': {'count': len(no_factor_dividend),
                                                'samples': no_factor_dividend[:20]},
        },
        'timing_seconds': timers,
        'inputs': inputs,
        'placeholders': placeholders,
        'freeze': {'research_end': FREEZE_END.isoformat(), 'max_bar_datetime': int(max_dt)},
    }
    timers['build_total'] = round(time.perf_counter() - t_build, 2)
    manifest['timing_seconds'] = timers
    (out_dir / 'manifest.json').write_text(
        json.dumps(manifest, indent=1, ensure_ascii=False), encoding='utf-8')
    return manifest
