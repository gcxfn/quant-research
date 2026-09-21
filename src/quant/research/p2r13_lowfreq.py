"""P2-R13 low-frequency monthly cross-sectional survey (preregistered).

Implements the frozen protocol in
``docs/research/exp-20260918-p2r13-lowfreq-survey-prereg.md`` and
``configs/experiments/p2r13-lowfreq-survey.json`` exactly:

- five candidate factors + one control, all fixed a priori:
  C1  overnight crowding   = -sum(60 own-session open/preclose - 1)
  C2  52w-high proximity   = close_adj / rolling-max(close_adj, 250 own sessions)
  C3  northbound 20d delta = ratio(session s-1) - ratio(session s-21), SH/SZ only
  C4  accrual quality      = -(net_income - ocf) / total_assets, latest PIT
                             annual report visible at max(ann_date, end+90d),
                             financial industry excluded
  C5  block-trade discount = -sum20d(disc*amt)/sum20d(amt),
                             disc = 1 - price/prev own-session close (daily file),
                             trades available T+1 (window = market sessions [s-20, s-1])
  C6  CONTROL 20d momentum = close_adj(t)/close_adj(t-20 own sessions) - 1
- signals at month-end close; forward = T+1 open -> T+21 open (20 traded
  sessions, next-open execution) bridged with published preclose (the
  "preclose bridge": every leg open_t/preclose_t and close_t/open_t is
  corporate-action consistent by construction);
- monthly cross-sectional rank IC, Newey-West lag-6 t (monthly series, per
  prereg; differs from the R10 daily NW(5)), direction-aligned decile
  D10-D1 spread annualized x244/20, same-sign month share >= 60%;
- increment gate for C1/C2 only: |IC| >= 1.3 x |IC_CONTROL|;
- universe: SH/SZ main board (sh.60*, sz.00*; no ChiNext/STAR/BSE),
  non-ST, non-suspended at signal (historical isST/tradestatus),
  20-session median amount >= 50,000,000 CNY, close >= 2 CNY,
  more than 120 own traded sessions (C2 additionally needs 250).

Disclosed implementation decisions (see run manifest + results doc):
- history warmup reads ``daily_1999_2024.parquet`` (same processed dataset,
  same manifest identity, sha256 recorded in the run manifest) because the
  pinned 2015-2024 file cannot produce 250-session rolling highs for the
  2015 signals required by the frozen coverage ("C1/C2/C6 2015-01-05..");
  R10 used the same superset file for its history factors;
- history factors use the symbol's OWN traded sessions (suspensions do not
  advance windows), consistent with R10's listing/volume conventions;
- northbound hk_hold disclosure lag = T+1 (holdings of trade date T are
  first usable at T+1 close), the conservative reading of the prereg PIT
  requirement;
- financial industry = East Money industry in {bank, insurance, securities,
  diversified financials} from xiaodefa stock_basic (2026-09-13 snapshot,
  non-PIT approximation, disclosed), applied to C4 cross-sections only;
- signals whose T+21 open would land after 2024-12-31 are dropped
  (2025+ zero-touch); the last judged signal month is 2024-11;
- the C3 ">10% missing month dropped" rule is measured over
  disclosure-universe members (>=1 hk_hold row in [s-61, s-1]); pool stocks
  never covered by the northbound universe are out-of-domain (eligibility),
  not missing data - decided from coverage metadata before any C3 IC
  existed (see run manifests for the full disclosure).
"""
from __future__ import annotations

import random
from datetime import date, timedelta
from typing import Final

import numpy as np
import polars as pl

from quant.research.p2r10_halfday import newey_west_t  # reused verbatim

# --------------------------------------------------------------------------- #
# frozen protocol constants
# --------------------------------------------------------------------------- #
DEV_START: Final[date] = date(2015, 1, 5)
DEV_END: Final[date] = date(2020, 12, 31)
VAL_START: Final[date] = date(2021, 1, 1)
VAL_END: Final[date] = date(2024, 12, 31)
FREEZE_START: Final[date] = date(2025, 1, 1)
FREEZE_LAST: Final[date] = date(2024, 12, 31)

FACTOR_NAMES: Final[tuple[str, ...]] = ('C1', 'C2', 'C3', 'C4', 'C5', 'C6')
CANDIDATES: Final[tuple[str, ...]] = ('C1', 'C2', 'C3', 'C4', 'C5')
CONTROL: Final[str] = 'C6'
INCREMENT_FACTORS: Final[tuple[str, ...]] = ('C1', 'C2')
DIRECTIONS: Final[dict[str, int]] = {
    'C1': -1, 'C2': 1, 'C3': 1, 'C4': -1, 'C5': -1}

NW_LAG: Final[int] = 6
SESSIONS_PER_YEAR: Final[int] = 244
HOLD_SESSIONS: Final[int] = 20
ANNUALIZE_FACTOR: Final[float] = SESSIONS_PER_YEAR / HOLD_SESSIONS  # 12.2

IC_GATE_ABS_MEAN: Final[float] = 0.02
IC_GATE_NW_T: Final[float] = 3.0
DECILE_GATE_ANNUAL: Final[float] = 0.04
DECILE_GATE_MONTH_SHARE: Final[float] = 0.60
INCREMENT_GATE_RATIO: Final[float] = 1.3
PASS_MIN_FACTOR_COUNT: Final[int] = 2
MIN_IC_STOCKS: Final[int] = 50

NEW_LISTING_SESSIONS: Final[int] = 120
C2_MIN_SESSIONS: Final[int] = 250
LIQ_MEDIAN_AMOUNT: Final[float] = 50_000_000.0
MIN_CLOSE: Final[float] = 2.0
C3_MISSING_MONTH_DROP: Final[float] = 0.10
C3_FAMILY_EXIT_RHO: Final[float] = 0.70

FINANCIAL_INDUSTRIES: Final[frozenset[str]] = frozenset(
    {'银行', '保险', '证券', '多元金融'})

EXCLUDED_INDEX_SYMBOLS: Final[frozenset[str]] = frozenset(
    {'sz.000905', 'sz.000852'})

SEED: Final[int] = 17
TOM_WINDOW_SESSIONS: Final[int] = 6
TOM_N_PERMUTATION_SEEDS: Final[int] = 20

# net reference annotation (no gate): 20-session round trip, wan-1 commission
# with 5-yuan minimum, segmented stamp duty (same fee facts as R10)
NET_NOTIONAL: Final[float] = 20000.0
NET_COMMISSION_PCT: Final[float] = 0.0001
NET_COMMISSION_MIN: Final[float] = 5.0


def round_trip_fee(day: date) -> float:
    """One 20-session round trip on NET_NOTIONAL: buy+sell commission (the
    5-yuan minimum binds at 20k) plus stamp duty on the sell at exit date."""
    stamp = 0.0005 if day >= date(2023, 8, 28) else 0.001
    commission = max(NET_NOTIONAL * NET_COMMISSION_PCT, NET_COMMISSION_MIN)
    return 2 * commission + NET_NOTIONAL * stamp


# --------------------------------------------------------------------------- #
# data identity (fail-closed)
# --------------------------------------------------------------------------- #
def load_ledger(root) -> dict[str, tuple[int, str]]:
    """data/_meta/sha256.tsv -> {path relative to data/raw: (bytes, sha256)}."""
    ledger: dict[str, tuple[int, str]] = {}
    for line in (root / 'data/_meta/sha256.tsv').read_text(
            encoding='utf-8').splitlines():
        parts = line.split('\t')
        if len(parts) != 3:
            continue
        rel, size, digest = parts
        ledger[rel.replace('\\', '/')] = (int(size), digest)
    if not ledger:
        raise RuntimeError('empty sha256 ledger data/_meta/sha256.tsv')
    return ledger


def verify_raw_file(root, rel: str, ledger: dict[str, tuple[int, str]]) -> str:
    """Fail-closed sha256 check of one data/raw file against the ledger."""
    import hashlib
    path = root / 'data/raw' / rel
    if rel not in ledger:
        raise RuntimeError(f'identity fail-closed: {rel} absent from ledger')
    digest = hashlib.sha256()
    with path.open('rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            digest.update(chunk)
    got = digest.hexdigest()
    if got != ledger[rel][1]:
        raise RuntimeError(f'identity fail-closed: {rel} sha256 {got} != '
                           f'ledger {ledger[rel][1]}')
    return got


def verify_raw_dir(root, rel_dir: str,
                   ledger: dict[str, tuple[int, str]]) -> dict:
    """Every ledger-listed file under a data/raw dir must exist and hash-match;
    every on-disk file must be ledger-listed (batch identity, no mutation)."""
    base = root / 'data/raw' / rel_dir
    prefix = rel_dir.rstrip('/') + '/'
    listed = {k: v for k, v in ledger.items() if k.startswith(prefix)}
    on_disk = {str(p.relative_to(root / 'data/raw')).replace('\\', '/')
               for p in base.rglob('*') if p.is_file()}
    missing = sorted(set(listed) - on_disk)
    unregistered = sorted(on_disk - set(listed))
    if missing:
        raise RuntimeError(f'identity fail-closed: ledger lists files absent '
                           f'on disk under {rel_dir}: {missing[:5]}')
    if unregistered:
        raise RuntimeError(f'identity fail-closed: on-disk files missing from '
                           f'ledger under {rel_dir}: {unregistered[:5]}')
    for rel in sorted(listed):
        verify_raw_file(root, rel, ledger)
    return {'dir': rel_dir, 'files_verified': len(listed)}


def assert_uniform_headers(root, rel_dir: str, pattern: str = 'chunk_*.csv') -> dict:
    """Deep-scan rule: never trust per-file column order in multi-file CSV
    batches.  Non-empty files in the batch must share one header line before
    any positional multi-file scan is allowed.  0-byte files are skipped by
    the reader (raise_if_empty=False) and counted here (known batch artifact,
    deep-scan rule #4); a NON-empty file without a header still fails."""
    directory = root / 'data/raw' / rel_dir
    header: str | None = None
    empty_files = 0
    for f in sorted(directory.glob(pattern)):
        with f.open('rb') as fh:
            first = fh.readline().decode('utf-8', errors='replace')
        if first.strip() == '':
            if f.stat().st_size == 0:
                empty_files += 1
                continue
            raise RuntimeError(f'identity fail-closed: empty header {f.name} '
                               f'in {rel_dir}')
        if header is None:
            header = first
        elif first != header:
            raise RuntimeError(f'identity fail-closed: header mismatch in '
                               f'{rel_dir}: {f.name}')
    if header is None:
        raise RuntimeError(f'identity fail-closed: no non-empty files in '
                           f'{rel_dir}')
    return {'dir': rel_dir, 'empty_files_skipped': empty_files}


def verify_processed_manifest(root, rel_manifest: str,
                              expected_sha: str) -> dict:
    import hashlib
    got = hashlib.sha256((root / rel_manifest).read_bytes()).hexdigest()
    if got != expected_sha:
        raise RuntimeError(f'identity fail-closed: {rel_manifest} sha256 {got} '
                           f'!= config {expected_sha}')
    return {'manifest': rel_manifest, 'sha256': got}


# --------------------------------------------------------------------------- #
# small helpers
# --------------------------------------------------------------------------- #
def ts_to_symbol(ts_code: str) -> str | None:
    """'600000.SH' -> 'sh.600000'; None when not an A-share stock code."""
    if not isinstance(ts_code, str) or '.' not in ts_code:
        return None
    code, _, suffix = ts_code.partition('.')
    if len(code) != 6 or not code.isdigit() or suffix not in ('SH', 'SZ'):
        return None
    return suffix.lower() + '.' + code


def symbol_from_ts_expr(col: str = 'ts_code') -> pl.Expr:
    """Vectorized :func:`ts_to_symbol`; null for non A-share-stock codes."""
    return (
        pl.when(pl.col(col).str.contains(r'^\d{6}\.SH$'))
        .then(pl.col(col).str.replace(r'^(\d{6})\.SH$', 'sh.$1'))
        .when(pl.col(col).str.contains(r'^\d{6}\.SZ$'))
        .then(pl.col(col).str.replace(r'^(\d{6})\.SZ$', 'sz.$1'))
        .otherwise(None)
        .alias('symbol'))


def visible_date(ann_date: date | None, end_date: date) -> date:
    """PIT visibility of a report: max(valid ann_date, end_date + 90d)."""
    fallback = end_date + timedelta(days=90)
    if ann_date is None:
        return fallback
    return max(ann_date, fallback)


def board_ok_expr() -> pl.Expr:
    symbol = pl.col('symbol')
    return ((symbol.str.starts_with('sh.60'))
            | (symbol.str.starts_with('sz.00'))) \
        & ~symbol.is_in(EXCLUDED_INDEX_SYMBOLS)


# --------------------------------------------------------------------------- #
# calendar and month-end signals
# --------------------------------------------------------------------------- #
def market_calendar(daily_path) -> pl.DataFrame:
    """(date, mkt_idx) over all traded sessions in the daily file."""
    return (
        pl.scan_parquet(daily_path)
        .select(pl.col('date').unique().alias('date'))
        .sort('date')
        .with_columns(pl.int_range(pl.len()).alias('mkt_idx'))
        .collect()
    )


def month_end_sessions(cal: pl.DataFrame) -> pl.DataFrame:
    """Last traded session of each calendar month: (month, s, s_idx)."""
    return (
        cal.group_by(pl.col('date').dt.month_start().alias('month'))
        .agg(pl.col('date').max().alias('s'))
        .join(cal.rename({'date': 's', 'mkt_idx': 's_idx'}), on='s',
              how='inner')
        .sort('month')
        .select('month', 's', 's_idx')
    )


def keep_complete_forward(signals: pl.DataFrame,
                          last_mkt_idx: int) -> pl.DataFrame:
    """2025+ zero-touch: keep only signals whose T+21 open anchor
    (first own session with mkt_idx >= s_idx+21) can exist within the data:
    s_idx + HOLD_SESSIONS + 1 <= last_mkt_idx."""
    return signals.filter(
        pl.col('s_idx') + HOLD_SESSIONS + 1 <= last_mkt_idx)


# --------------------------------------------------------------------------- #
# history frame: chain factors C1/C2/C6 + universe state columns
# --------------------------------------------------------------------------- #
def history_factor_exprs() -> dict[str, pl.Expr]:
    """Row expressions over a frame sorted by (symbol, date) holding
    open/close/preclose/amount, 'overnight' and the adjusted chain 'c_adj'.

    Every shift/rolling lives INSIDE .over('symbol') (P2-R10 M-1 rule: a
    shift outside .over leaks the previous symbol's value into each
    symbol's first rows).
    """
    return {
        'c_adj': (pl.col('close') / pl.col('preclose')).cum_prod()
                  .over('symbol'),
        'o_adj': (pl.col('c_adj').shift(1).over('symbol')
                  * pl.col('open') / pl.col('preclose')),
        'C1': -(pl.col('overnight').rolling_sum(60, min_samples=60)
                .over('symbol')),
        'C2': (pl.col('c_adj') / pl.col('c_adj')
               .rolling_max(C2_MIN_SESSIONS, min_samples=C2_MIN_SESSIONS)
               .over('symbol')),
        'C6': (pl.col('c_adj') / pl.col('c_adj').shift(HOLD_SESSIONS)
               .over('symbol') - 1.0),
        'amt_med20': (pl.col('amount').rolling_median(20, min_samples=20)
                      .over('symbol')),
        'pclose': pl.col('close').shift(1).over('symbol'),
    }


def attach_history_factors(df: pl.DataFrame) -> pl.DataFrame:
    """Add overnight + chain factors to a frame sorted by (symbol, date) with
    open/close/preclose/amount.  Split into staged with_columns blocks because
    polars expressions cannot reference columns created in the same block."""
    exprs = history_factor_exprs()
    df = df.with_columns(
        (pl.col('open') / pl.col('preclose') - 1.0).alias('overnight'))
    df = df.with_columns(exprs['c_adj'].alias('c_adj'))
    df = df.with_columns([exprs[n].alias(n) for n in
                          ('o_adj', 'C1', 'C2', 'C6', 'amt_med20', 'pclose')])
    return df.with_columns(
        (pl.col('close') / pl.col('preclose') - 1.0).alias('r'))


def build_history(daily_path, cal: pl.DataFrame,
                  warmup_start: date = date(2012, 1, 1)) -> pl.DataFrame:
    """Per (symbol, traded session) frame with chain factors.

    listing_index counts ALL own traded sessions since 1999 (computed before
    the warmup cut) so pre-2015 listings are never "new" in 2015.  Rows on or
    after 2025-01-01 are dropped here (2025+ zero-touch, structural).
    """
    hist = (
        pl.scan_parquet(daily_path)
        .filter(pl.col('tradestatus') == 1.0)
        .sort('symbol', 'date')
        .select(
            'symbol', 'date', 'open', 'close', 'preclose', 'amount', 'isST',
            pl.int_range(pl.len()).over('symbol', order_by='date')
            .add(1).alias('listing_index'))
        .filter((pl.col('date') >= warmup_start)
                & (pl.col('date') <= FREEZE_LAST))
        .join(cal.lazy(), on='date', how='inner')
        .sort('symbol', 'date')
    )
    raw = (hist.select('symbol', 'date', 'mkt_idx', 'open', 'close',
                       'preclose', 'amount', 'isST', 'listing_index')
           .collect())
    df = attach_history_factors(raw)
    # fail-closed: a null price leg inside traded rows would silently break
    # the cumulative chain for that symbol from that day on.
    leg_nulls = df.filter(pl.col('c_adj').is_null()
                          & (pl.col('listing_index') > 1))
    if leg_nulls.height:
        raise RuntimeError(
            f'null price leg in traded rows breaks the preclose bridge: '
            f'{leg_nulls.height} rows, e.g. '
            f'{leg_nulls.select("symbol", "date").head(3).rows()}')
    return df


# --------------------------------------------------------------------------- #
# universe at the month-end signal + forward returns
# --------------------------------------------------------------------------- #
def universe_signals(hist: pl.DataFrame,
                     signals: pl.DataFrame) -> tuple[pl.DataFrame, dict]:
    """Frozen pool filters at the signal session; returns (panel, waterfall).
    ``signals`` holds (month, s, s_idx); hist rows are already tradestatus==1.
    """
    base = hist.join(signals, left_on='date', right_on='s', how='inner')
    counts: dict[str, object] = {'rows_at_signal_sessions': base.height}
    df = base.filter(pl.col('isST') == 0.0)
    counts['after_st'] = df.height
    df = df.filter(pl.col('listing_index') > NEW_LISTING_SESSIONS)
    counts['after_listing_120'] = df.height
    df = df.filter(board_ok_expr())
    counts['after_boards'] = df.height
    df = df.filter(pl.col('amt_med20') >= LIQ_MEDIAN_AMOUNT)
    counts['after_liq_50m'] = df.height
    df = df.filter(pl.col('close') >= MIN_CLOSE)
    counts['after_close_2yuan'] = df.height
    panel = df.select(
        pl.col('month'), pl.col('date').alias('s'),
        pl.col('mkt_idx').alias('s_idx'),
        'symbol', 'close', 'C1', 'C2', 'C6').sort('s', 'symbol')
    counts['universe_names_mean'] = float(
        panel.group_by('s').agg(pl.len().alias('n'))['n'].mean())
    counts['universe_names_min'] = int(
        panel.group_by('s').agg(pl.len().alias('n'))['n'].min())
    return panel, counts


def attach_forward(hist: pl.DataFrame, panel: pl.DataFrame) -> pl.DataFrame:
    """Forward return T+1 open -> T+21 open via the preclose bridge.

    entry anchor: the symbol's own traded session with mkt_idx == s_idx+1
    (a symbol not trading there cannot be entered at the protocol price ->
    fwd null, counted in coverage);
    exit anchor: first own traded session with mkt_idx >= s_idx+21
    (suspension after entry delays the exit to the resume open).
    """
    entry_idx = panel.select(
        pl.col('s'), 'symbol', (pl.col('s_idx') + 1).alias('e_idx'))
    right = hist.select('symbol', 'mkt_idx', 'o_adj').filter(
        pl.col('mkt_idx').is_in(entry_idx['e_idx'].unique().to_list()))
    entry = (entry_idx.join(right, left_on=['symbol', 'e_idx'],
                            right_on=['symbol', 'mkt_idx'], how='left')
             .select('s', 'symbol', pl.col('o_adj').alias('o_entry')))

    exits = (panel.select('s', 'symbol',
                          (pl.col('s_idx') + HOLD_SESSIONS + 1).alias('x_key'))
             .sort('x_key'))
    right_all = hist.select('symbol', 'mkt_idx', 'o_adj').sort('mkt_idx')
    exit_j = (exits.join_asof(right_all, left_on='x_key', right_on='mkt_idx',
                              by='symbol', strategy='forward')
              .select('s', 'symbol', pl.col('o_adj').alias('o_exit')))

    return (panel
            .join(entry, on=['s', 'symbol'], how='left')
            .join(exit_j, on=['s', 'symbol'], how='left')
            .with_columns(
                (pl.col('o_exit') / pl.col('o_entry') - 1.0).alias('fwd'))
            .drop('o_entry', 'o_exit'))


# --------------------------------------------------------------------------- #
# C3 northbound (T+1 disclosure lag; exact sessions s-1 and s-21)
# --------------------------------------------------------------------------- #
def _hk_hold_scan(root) -> pl.LazyFrame:
    return pl.concat([
        pl.scan_csv(f, schema_overrides={'ratio': pl.Float64})
        .filter(pl.col('exchange').is_in(['SH', 'SZ']))
        .select(pl.col('ts_code'),
                pl.col('trade_date').cast(pl.String).str.to_date('%Y%m%d')
                .alias('date'),
                pl.col('ratio'))
        for f in sorted((root / 'data/raw/xiaodefa/hk_hold/20260913-bulk1')
                        .glob('chunk_*.csv'))])


def load_hk_hold(root) -> pl.DataFrame:
    df = _hk_hold_scan(root).collect()
    df = df.with_columns(symbol_from_ts_expr())
    return (df.drop_nulls('symbol')
              .group_by('symbol', 'date').agg(pl.col('ratio').mean())
              .select('symbol', 'date', 'ratio'))


def hk_hold_probe(root, lo: date = date(2017, 1, 1),
                  hi: date = date(2018, 12, 31)) -> pl.DataFrame:
    """2017-2018 A-share row-count completeness probe (per month)."""
    df = (_hk_hold_scan(root).select('date').collect())
    return (df.filter((pl.col('date') >= lo) & (pl.col('date') <= hi))
              .group_by(pl.col('date').dt.month_start().alias('month'))
              .agg(pl.len().alias('a_share_rows'),
                   pl.col('date').n_unique().alias('disclosed_days'))
              .sort('month'))


def northbound_delta(hk: pl.DataFrame, cal: pl.DataFrame,
                     panel: pl.DataFrame) -> pl.DataFrame:
    """C3 = ratio(session s-1) - ratio(session s-21), exact sessions.

    T+1 disclosure: values published for trade date T enter first at T+1,
    so a month-end signal at s may only see trade dates <= s-1.
    """
    hk_idx = (hk.join(cal, on='date', how='inner')
                .select('symbol', 'mkt_idx', 'ratio'))
    keys = panel.select('s', 'symbol',
                        (pl.col('s_idx') - 1).alias('a_key'),
                        (pl.col('s_idx') - 21).alias('b_key'))
    a = (keys.join(hk_idx.rename({'mkt_idx': 'a_key', 'ratio': 'r_a'}),
                   on=['symbol', 'a_key'], how='left')
         .select('s', 'symbol', 'r_a'))
    b = (keys.join(hk_idx.rename({'mkt_idx': 'b_key', 'ratio': 'r_b'}),
                   on=['symbol', 'b_key'], how='left')
         .select('s', 'symbol', 'r_b'))
    return (a.join(b, on=['s', 'symbol'], how='left')
             .with_columns((pl.col('r_a') - pl.col('r_b')).alias('C3'))
             .select('s', 'symbol', 'r_a', 'r_b', 'C3'))


def c3_member_missing(panel: pl.DataFrame, hk: pl.DataFrame,
                      cal: pl.DataFrame) -> tuple[pl.DataFrame, list[dict]]:
    """C3 month-drop rule (prereg: months with missing rate > 10 percent are
    dropped from C3 judgment).

    The missing rate is measured over DISCLOSURE-UNIVERSE MEMBERS: pool
    stocks with at least one hk_hold row in sessions [s-61, s-1].  Pool
    stocks never covered by the northbound disclosure universe are an
    economic eligibility property of the factor domain (bimodal presence:
    ~27 percent of the pool has zero rows in any year) - they are
    out-of-domain names, not data failures, exactly like C5's
    no-block-trade names.  Source-delivery failures (e.g. the 2024-08-16
    disclosure stop, backfill gaps) show up as members without usable
    values and drive the month drop.
    """
    hk_idx = (hk.join(cal, on='date', how='inner')
                .select('symbol', 'mkt_idx')
                .sort('mkt_idx'))  # asof requires the right side sorted by key
    last = (panel.select('s', 'symbol',
                         (pl.col('s_idx') - 1).alias('hi_key'),
                         (pl.col('s_idx') - 61).alias('lo_key'))
            .sort('hi_key')
            .join_asof(hk_idx, left_on='hi_key', right_on='mkt_idx',
                       by='symbol', strategy='backward'))
    members = (last.filter(pl.col('mkt_idx') >= pl.col('lo_key'))
                   .select('s', 'symbol')
                   .with_columns(pl.lit(True).alias('member')))
    joined = members.join(panel.select('s', 'symbol', 'C3'),
                          on=['s', 'symbol'], how='left')
    per = (joined.group_by('s')
                 .agg(pl.len().alias('members_n'),
                      pl.col('C3').is_null().sum().alias('missing_n'))
                 .with_columns((pl.col('missing_n')
                                / pl.col('members_n')).alias('missing_rate'))
                 .sort('s'))
    dropped_rows = per.filter(
        pl.col('missing_rate') > C3_MISSING_MONTH_DROP)
    dropped = set(dropped_rows['s'].to_list())
    details = [{'month': str(d), 'members_n': int(m), 'missing_n': int(x),
                'missing_rate': round(float(r), 4)}
               for d, m, x, r in zip(per['s'], per['members_n'],
                                     per['missing_n'],
                                     per['missing_rate'])
               if d in dropped]
    return (panel.filter(~pl.col('s').is_in(sorted(dropped))), details)


# --------------------------------------------------------------------------- #
# C4 accruals (PIT annual reports, financials excluded)
# --------------------------------------------------------------------------- #
def _read_statement_table(root, rel_dir: str,
                          value_cols: list[str]) -> pl.DataFrame:
    lf = pl.scan_csv(
        str(root / 'data/raw' / rel_dir / 'chunk_*.csv'),
        raise_if_empty=False,
        schema_overrides={c: pl.String for c in
                          ['ts_code', 'ann_date', 'f_ann_date', 'end_date',
                           'report_type', 'update_flag']})
    df = (lf.filter((pl.col('report_type') == '1')
                    & pl.col('end_date').str.ends_with('1231')
                    & (pl.col('end_date') < '20250101'))  # 2025+ zero-touch
          .select('ts_code', 'ann_date', 'end_date', 'update_flag',
                  *value_cols)
          .collect())
    return (df.with_columns(
                pl.col('ann_date').str.to_date('%Y%m%d'),
                pl.col('end_date').str.to_date('%Y%m%d'),
                pl.col('update_flag').cast(pl.Int32, strict=False))
            .sort('ts_code', 'end_date', 'update_flag', 'ann_date')
            .unique(subset=['ts_code', 'end_date'], keep='last'))


def build_accrual_table(root) -> pl.DataFrame:
    """(symbol, end_date, visible, accrual): accrual =
    (n_income - n_cashflow_act) / total_assets of the latest PIT annual
    report; visibility = max(valid ann_date, end_date + 90d)."""
    income = _read_statement_table(root, 'tushare/income/20260909-r3',
                                   ['n_income'])
    cashflow = _read_statement_table(root, 'tushare/cashflow/20260909-r3',
                                     ['n_cashflow_act'])
    balance = _read_statement_table(root, 'tushare/balancesheet/20260909-r3',
                                    ['total_assets'])
    j = (income
         .join(cashflow.select('ts_code', 'end_date', 'n_cashflow_act'),
               on=['ts_code', 'end_date'], how='inner')
         .join(balance.select('ts_code', 'end_date', 'total_assets'),
               on=['ts_code', 'end_date'], how='inner'))
    j = (j.with_columns(symbol_from_ts_expr())
            .drop_nulls('symbol')
            .with_columns(
                (pl.col('n_income') - pl.col('n_cashflow_act')).alias('num'),
                pl.struct('ann_date', 'end_date')
                .map_elements(lambda s: visible_date(s['ann_date'],
                                                     s['end_date']),
                              return_dtype=pl.Date).alias('visible')))
    return (j.filter(pl.col('total_assets') != 0)
             .with_columns((pl.col('num') / pl.col('total_assets'))
                           .alias('accrual'))
             .sort('symbol', 'visible', 'end_date')
             .unique(subset=['symbol', 'visible'], keep='last')
             .select('symbol', 'end_date', 'visible', 'accrual'))


def accrual_at_signal(accrual: pl.DataFrame,
                      panel: pl.DataFrame) -> pl.DataFrame:
    """Latest report with visible <= s per (symbol, s): asof backward join."""
    left = panel.select('s', 'symbol').sort('s')
    right = accrual.sort('visible').select('symbol', 'visible', 'end_date',
                                           'accrual')
    return (left.join_asof(right, left_on='s', right_on='visible',
                           by='symbol', strategy='backward')
            .rename({'accrual': 'accrual_raw', 'end_date': 'rep_end_date',
                     'visible': 'rep_visible'})
            .with_columns((-pl.col('accrual_raw')).alias('C4'))
            .select('s', 'symbol', 'accrual_raw', 'rep_end_date',
                    'rep_visible', 'C4'))


def load_financial_symbols(root) -> pl.DataFrame:
    """East Money industry snapshot (xiaodefa stock_basic 20260913-bulk1)."""
    df = pl.concat([
        pl.read_csv(f, schema_overrides={'symbol': pl.String})
        for f in sorted((root / 'data/raw/xiaodefa/stock_basic/20260913-bulk1')
                        .glob('chunk_*.csv'))])
    return (df.with_columns(symbol_from_ts_expr())
            .drop_nulls('symbol')
            .select('symbol', 'industry'))


def apply_financial_exclusion(panel: pl.DataFrame,
                              industries: pl.DataFrame) -> pl.DataFrame:
    """C4-only filter: drop financial-industry rows from the cross-section.
    Symbols with no industry snapshot row are kept (unknown != financial)."""
    return (panel.join(industries, on='symbol', how='left')
                 .filter(pl.col('industry').is_null()
                         | ~pl.col('industry')
                         .is_in(list(FINANCIAL_INDUSTRIES)))
                 .drop('industry'))


# --------------------------------------------------------------------------- #
# C5 block-trade discount
# --------------------------------------------------------------------------- #
def load_block_trades(root, hist: pl.DataFrame) -> pl.DataFrame:
    """Block trades with discount vs the stock's previous own-session close
    (from the daily file), restricted to market sessions;
    per (symbol, t_idx): sum(disc*amt), sum(amt)."""
    lf = pl.concat([
        pl.scan_csv(f, schema_overrides={'price': pl.Float64,
                                         'vol': pl.Float64,
                                         'amount': pl.Float64})
        .select('ts_code', 'trade_date', 'price', 'amount')
        for f in sorted((root / 'data/raw/xiaodefa/block_trade/20260913-bulk1')
                        .glob('chunk_*.csv'))])
    df = (lf.filter(pl.col('ts_code').str.contains(r'^\d{6}\.(SH|SZ)$'))
          .with_columns(
              symbol_from_ts_expr(),
              pl.col('trade_date').cast(pl.String).str.to_date('%Y%m%d')
              .alias('date'))
          .drop_nulls('symbol')
          .collect())
    df = (df.join(hist.select('symbol', 'date', 'mkt_idx', 'pclose'),
                  on=['symbol', 'date'], how='inner')
          .filter((pl.col('price') > 0) & (pl.col('pclose') > 0))
          .select('symbol', pl.col('mkt_idx').alias('t_idx'),
                  (1.0 - pl.col('price') / pl.col('pclose')).alias('disc'),
                  pl.col('amount').alias('amt')))
    return (df.drop_nulls('disc')
              .group_by('symbol', 't_idx')
              .agg((pl.col('disc') * pl.col('amt')).sum().alias('w'),
                   pl.col('amt').sum().alias('amt')))


def block_discount_factor(block: pl.DataFrame,
                          panel: pl.DataFrame) -> pl.DataFrame:
    """C5 = -sum([s-20, s-1] disc*amt) / sum([s-20, s-1] amt) via per-symbol
    cumulative sums and two backward asof joins (T+1: window ends at s-1).
    Null when the symbol had no block trades in the window."""
    cum = (block.sort('symbol', 't_idx')
           .with_columns(pl.col('w').cum_sum().over('symbol').alias('cw'),
                         pl.col('amt').cum_sum().over('symbol').alias('ca'))
           .select('symbol', 't_idx', 'cw', 'ca'))
    keys = (panel.select('s', 'symbol',
                         (pl.col('s_idx') - 1).alias('hi_key'),
                         (pl.col('s_idx') - 21).alias('lo_key'))
            .sort('hi_key'))
    hi = (keys.join_asof(cum, left_on='hi_key', right_on='t_idx', by='symbol',
                         strategy='backward')
          .rename({'cw': 'cw_hi', 'ca': 'ca_hi'})
          .drop('t_idx', 'hi_key')
          .sort('lo_key'))
    lo = (hi.join_asof(cum, left_on='lo_key', right_on='t_idx', by='symbol',
                       strategy='backward')
          .rename({'cw': 'cw_lo', 'ca': 'ca_lo'})
          .drop('t_idx', 'lo_key'))
    denom = pl.col('ca_hi').fill_null(0.0) - pl.col('ca_lo').fill_null(0.0)
    numer = pl.col('cw_hi').fill_null(0.0) - pl.col('cw_lo').fill_null(0.0)
    return (lo.with_columns(
                denom.alias('block_amt20'),
                pl.when(denom > 0).then(-(numer / denom))
                .otherwise(None).alias('C5'))
            .select('s', 'symbol', 'C5', 'block_amt20'))


# --------------------------------------------------------------------------- #
# daily_basic at signal dates (circ_mv disclosure / C4 pe-pb residual)
# --------------------------------------------------------------------------- #
def load_daily_basic_at(root, signal_dates: list[date]) -> pl.DataFrame:
    want = {d.strftime('%Y%m%d') for d in signal_dates}
    frames = []
    for batch in ('20260909-r1', '20260913-r2'):
        directory = root / 'data/raw/tushare/daily_basic' / batch
        for f in sorted(directory.glob('chunk_*.csv')):
            if f.stem.replace('chunk_', '') not in want:
                continue
            frames.append(
                pl.scan_csv(f, schema_overrides={'ts_code': pl.String})
                .select('ts_code', 'trade_date', 'pe_ttm', 'pb', 'circ_mv')
                .with_columns(
                    pl.col('trade_date').cast(pl.String).str.to_date('%Y%m%d')
                    .alias('date'))
                .collect())
    df = pl.concat(frames, how='vertical')
    df = df.with_columns(symbol_from_ts_expr())
    return (df.drop_nulls('symbol')
              .group_by('symbol', 'date')
              .agg(pl.col('pe_ttm').mean(), pl.col('pb').mean(),
                   pl.col('circ_mv').mean()))


# --------------------------------------------------------------------------- #
# monthly IC / deciles / gates (reuses R10 Newey-West verbatim)
# --------------------------------------------------------------------------- #
def monthly_rank_ic(panel: pl.DataFrame, factor: str,
                    target: str = 'fwd') -> pl.DataFrame:
    """Per-month Spearman rank IC on complete (factor, target) pairs; months
    with fewer than MIN_IC_STOCKS valid pairs are dropped."""
    return (
        panel.filter(pl.col(factor).is_not_null() & pl.col(target).is_not_null())
        .group_by('s')
        .agg(pl.corr(factor, target, method='spearman').alias('ic'),
             pl.len().alias('n'))
        .filter(pl.col('n') >= MIN_IC_STOCKS)
        .sort('s')
    )


def window_ic(ic: pl.DataFrame, lo: date, hi: date) -> dict:
    w = ic.filter((pl.col('s') >= lo) & (pl.col('s') <= hi))
    n_dropped = int((~w['ic'].is_finite()).sum()) if w.height else 0
    w = w.filter(pl.col('ic').is_finite())
    if w.height == 0:
        return {'n_months': 0, 'mean_ic': None, 'nw_t': None,
                'n_dropped_nonfinite': n_dropped}
    return {'n_months': w.height,
            'mean_ic': float(w['ic'].mean()),
            'nw_t': newey_west_t(w['ic'].to_numpy(), NW_LAG),
            'n_dropped_nonfinite': n_dropped}


def decile_monthly_spread(panel: pl.DataFrame, factor: str,
                          target: str = 'fwd') -> pl.DataFrame:
    """Monthly (s, d1..d10, spread=d10-d1); ordinal ranks over the month,
    ties broken by the frame's deterministic (s, symbol) order."""
    ranked = (
        panel.sort('s', 'symbol')
        .filter(pl.col(factor).is_not_null() & pl.col(target).is_not_null())
        .with_columns(
            ((pl.col(factor).rank(method='ordinal').over('s') - 1.0)
             / pl.len().over('s')).alias('_pct')))
    ranked = ranked.with_columns(
        (((pl.col('_pct') * 10.0).floor().clip(0, 9)) + 1)
        .cast(pl.Int32).alias('_decile'))
    per = ranked.group_by('s', '_decile').agg(
        pl.col(target).mean().alias('ret'), pl.len().alias('n'))
    wide = per.sort('s', '_decile').pivot(on='_decile', index='s',
                                          values='ret')
    wide = wide.rename({str(i): f'd{i}' for i in range(1, 11)
                        if str(i) in wide.columns})
    missing = [pl.lit(None, dtype=pl.Float64).alias(f'd{i}')
               for i in range(1, 11) if f'd{i}' not in wide.columns]
    if missing:
        wide = wide.with_columns(missing)
    return (wide.sort('s')
            .with_columns((pl.col('d10') - pl.col('d1')).alias('spread'))
            .select('s', *[f'd{i}' for i in range(1, 11)], 'spread'))


def spread_window_stats(spread: pl.DataFrame, lo: date, hi: date,
                        direction: int) -> dict:
    """Direction-aligned monthly D10-D1 stats; annualized x244/20."""
    w = spread.filter((pl.col('s') >= lo) & (pl.col('s') <= hi)
                      & pl.col('spread').is_finite())
    if w.height == 0:
        return {'n_months': 0, 'mean_aligned': None, 'annualized': None,
                'month_share_same_sign': None}
    d = w.with_columns(pl.col('spread') * direction)
    mean_aligned = float(d['spread'].mean())
    same = float((d['spread'] * (1.0 if mean_aligned >= 0 else -1.0)
                  > 0).mean())
    return {'n_months': w.height, 'mean_aligned': mean_aligned,
            'annualized': mean_aligned * ANNUALIZE_FACTOR,
            'month_share_same_sign': same}


def yearly_ic(ic: pl.DataFrame) -> list[dict]:
    out = []
    years = sorted({d.year for d, v in zip(ic['s'], ic['ic'])
                    if v is not None and np.isfinite(v)})
    for year in years:
        w = ic.filter((pl.col('s').dt.year() == year)
                      & pl.col('ic').is_finite())
        out.append({'year': year, 'n_months': w.height,
                    'mean_ic': float(w['ic'].mean()),
                    'nw_t': newey_west_t(w['ic'].to_numpy(), NW_LAG)})
    return out


def ic_gate_pass(stats: dict) -> bool:
    return (stats['mean_ic'] is not None and stats['nw_t'] is not None
            and abs(stats['mean_ic']) >= IC_GATE_ABS_MEAN
            and abs(stats['nw_t']) >= IC_GATE_NW_T)


def decile_gate_pass(stats: dict) -> bool:
    return (stats['annualized'] is not None
            and stats['month_share_same_sign'] is not None
            and stats['annualized'] >= DECILE_GATE_ANNUAL
            and stats['month_share_same_sign'] >= DECILE_GATE_MONTH_SHARE)


def increment_gate_pass(ic_mean: float | None,
                        control_ic_mean: float | None) -> bool:
    if ic_mean is None or control_ic_mean is None:
        return False
    return abs(ic_mean) >= INCREMENT_GATE_RATIO * abs(control_ic_mean)


def mean_monthly_spearman(panel: pl.DataFrame, a: str, b: str) -> dict:
    per = (panel.filter(pl.col(a).is_not_null() & pl.col(b).is_not_null())
           .group_by('s')
           .agg(pl.corr(a, b, method='spearman').alias('rho'),
                pl.len().alias('n'))
           .filter(pl.col('n') >= MIN_IC_STOCKS)
           .filter(pl.col('rho').is_finite())
           .sort('s'))
    if per.height == 0:
        return {'mean_rho': None, 'n_months': 0}
    return {'mean_rho': float(per['rho'].mean()), 'n_months': per.height}


def factor_correlation_matrix(panel: pl.DataFrame) -> dict:
    out: dict[str, dict[str, float | None]] = {}
    for a in FACTOR_NAMES:
        out[a] = {}
        for b in FACTOR_NAMES:
            out[a][b] = (1.0 if a == b else
                         mean_monthly_spearman(panel, a, b)['mean_rho'])
    return out


def c4_pepb_residual_ic(panel: pl.DataFrame) -> dict:
    """Monthly rank-C4 residualized on rank(pe_ttm) + rank(pb); residual IC
    is a disclosure (C4 must not be a pe/pb马甲), never a gate."""
    sub = panel.filter(pl.col('C4').is_not_null()
                       & pl.col('pe_ttm').is_not_null()
                       & pl.col('pb').is_not_null()
                       & pl.col('fwd').is_not_null())
    n_months = 0
    rhos: list[float] = []
    if sub.height:
        sub = sub.with_columns(
            pl.col('C4').rank(method='average').over('s').alias('_rc4'),
            pl.col('pe_ttm').rank(method='average').over('s').alias('_rpe'),
            pl.col('pb').rank(method='average').over('s').alias('_rpb'))
        for _, g in sub.group_by(['s'], maintain_order=True):
            if g.height < MIN_IC_STOCKS:
                continue
            x = np.column_stack([np.ones(g.height),
                                 g['_rpe'].to_numpy(), g['_rpb'].to_numpy()])
            y = g['_rc4'].to_numpy()
            beta, *_ = np.linalg.lstsq(x, y, rcond=None)
            resid = y - x @ beta
            ra = pl.Series(resid).rank(method='average').to_numpy()
            rb = pl.Series(g['fwd'].to_numpy()).rank(method='average')\
                .to_numpy()
            rhos.append(float(np.corrcoef(ra, rb)[0, 1]))
            n_months += 1
    if not rhos:
        return {'mean_residual_ic': None, 'nw_t': None, 'n_months': 0}
    arr = np.array(rhos)
    return {'mean_residual_ic': float(arr.mean()),
            'nw_t': newey_west_t(arr, NW_LAG), 'n_months': n_months}


# --------------------------------------------------------------------------- #
# M1 TOM measurement (descriptive only, H-35)
# --------------------------------------------------------------------------- #
def tom_measurement(pool_daily: pl.DataFrame, cal: pl.DataFrame,
                    lo: date, hi: date) -> dict:
    """TOM window (last 3 + first 3 sessions around each month boundary)
    equal-weight pool mean daily return vs outside, plus 20-seed random
    6-session-window permutation.  Pure description, no gate."""
    pd_ = (pool_daily.filter((pl.col('date') >= lo) & (pl.col('date') <= hi))
           .sort('date'))
    dates = pd_['date'].to_list()
    rets = pd_['r'].to_numpy()
    idx_of = {d: i for i, d in enumerate(dates)}
    month_ends = (cal.filter((pl.col('date') >= lo) & (pl.col('date') <= hi))
                  .group_by(pl.col('date').dt.month_start().alias('month'))
                  .agg(pl.col('date').max().alias('s')).sort('month')['s']
                  .to_list())
    windows: list[tuple[int, int]] = []
    for i in range(len(month_ends) - 1):
        a = idx_of.get(month_ends[i])
        b = idx_of.get(month_ends[i + 1])
        if a is None or b is None:
            continue
        start, end = a - 2, b + 2  # last 3 of the month + first 3 of the next
        if start >= 0 and end < len(dates):
            windows.append((start, end))
    if not windows:
        return {'n_windows': 0}
    mask = np.zeros(len(dates), dtype=bool)
    for a, b in windows:
        mask[a:b + 1] = True
    inside = float(rets[mask].mean())
    outside = float(rets[~mask].mean())
    per_window = np.array([rets[a:b + 1].mean() - outside
                           for a, b in windows])
    rng = random.Random(SEED)
    perm_stats = []
    for _ in range(TOM_N_PERMUTATION_SEEDS):
        draws = [rng.randrange(0, len(dates) - TOM_WINDOW_SESSIONS)
                 for _ in windows]
        vals = [float(rets[a:a + TOM_WINDOW_SESSIONS].mean() - outside)
                for a in draws]
        perm_stats.append(float(np.mean(vals)))
    perm = np.array(perm_stats)
    stat = inside - outside
    return {
        'n_windows': len(windows),
        'n_days': len(dates),
        'mean_daily_inside': inside,
        'mean_daily_outside': outside,
        'tom_excess': stat,
        'nw_t_windows': newey_west_t(per_window, NW_LAG),
        'permutation_mean': float(perm.mean()),
        'permutation_p05': float(np.percentile(perm, 5)),
        'permutation_p95': float(np.percentile(perm, 95)),
        'tom_exceeds_permutation_share': float((stat > perm).mean()),
        'note': 'descriptive only (H-35 M1); 20 seeds, base seed 17',
    }


# --------------------------------------------------------------------------- #
# factor evaluation driver
# --------------------------------------------------------------------------- #
def evaluate_dev(factor: str, panel: pl.DataFrame,
                 control_dev_ic: float | None,
                 direction: int) -> dict:
    """Dev-window (2015-2020) gates for one factor.  Val is evaluated by
    :func:`evaluate_val` ONLY for dev-passing factors (one-shot discipline)."""
    ic = monthly_rank_ic(panel, factor)
    dev_ic = window_ic(ic, DEV_START, DEV_END)
    spread = decile_monthly_spread(panel, factor)
    dev_spread = spread_window_stats(spread, DEV_START, DEV_END, direction)
    gates = {'ic_gate': ic_gate_pass(dev_ic),
             'decile_gate': decile_gate_pass(dev_spread)}
    if factor in INCREMENT_FACTORS:
        gates['increment_gate'] = increment_gate_pass(dev_ic['mean_ic'],
                                                      control_dev_ic)
    dev_direction = 1 if (dev_ic['mean_ic'] or 0.0) >= 0 else -1
    return {'factor': factor, 'direction': direction,
            'dev': {'ic': dev_ic, 'spread': dev_spread,
                    'yearly_ic': yearly_ic(ic.filter(
                        (pl.col('s') >= DEV_START)
                        & (pl.col('s') <= DEV_END))),
                    'gates': gates},
            'dev_direction': dev_direction,
            'passed_dev': bool(all(gates.values()))}


def evaluate_val(factor: str, panel: pl.DataFrame,
                 dev_direction: int) -> dict:
    """Val (2021-2024, one-shot): IC gate + decile gate + direction unchanged."""
    ic = monthly_rank_ic(panel, factor)
    val_ic = window_ic(ic, VAL_START, VAL_END)
    spread = decile_monthly_spread(panel, factor)
    val_spread = spread_window_stats(spread, VAL_START, VAL_END, dev_direction)
    direction_ok = dev_direction == (1 if (val_ic['mean_ic'] or 0.0) >= 0
                                     else -1)
    return {'ic': val_ic, 'spread': val_spread,
            'direction_unchanged': bool(direction_ok),
            'pass': bool(ic_gate_pass(val_ic)
                         and decile_gate_pass(val_spread)
                         and direction_ok)}
