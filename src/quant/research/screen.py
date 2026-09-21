"""P2 first screen: event-study evaluation of pre-registered signals.

Fixed semantics (preregistered in ``configs/experiments/p2-first-screen.json``):

- signal known at the close of ``signal_date``;
- entry is the exact next market session strictly after it -- the calendar's
  next session, never a later session picked by skipping suspensions or
  missing rows;
- exit is the session at ``entry_index + holding_days`` (``holding_days >= 1``,
  so a same-day round trip is impossible);
- every scored event is preserved with a documented ``status``: a
  missing/blocked entry or exit yields a null label rather than a dropped row
  or a pretend fill;
- prices must be raw and unadjusted: ``symbol, date, open, adj_factor,
  tradestatus, isST``.  The economic gross label is
  ``exit_open*exit_adj_factor / (entry_open*entry_adj_factor) - 1`` -- an
  adjustment-derived estimate, not an exact corporate-action cash ledger;
- with ``block_limits`` a daily-line proxy blocks entries at limit-up opens
  and exits at limit-down opens (registered approximation, P3 re-checks on
  minute data); stop fills are never modelled: labels are indicative
  event-study outcomes, not account-level fills.

This is a coarse screening layer (vectorbt-class), not account-level proof.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from typing import Final

import polars as pl

FREEZE_END: Final[date] = date(2024, 12, 31)
LOT_SIZE: Final[int] = 100

COMMISSION_PCT: Final[float] = 0.0001
COMMISSION_MIN: Final[float] = 5.0

# Stable, documented event statuses.
STATUS_COMPLETED: Final[str] = 'completed_label'
STATUS_SIGNAL_OUT_OF_RANGE: Final[str] = 'signal_out_of_range'
STATUS_NO_NEXT_SESSION: Final[str] = 'no_next_session'
STATUS_HORIZON_OUT_OF_RANGE: Final[str] = 'horizon_out_of_range'
STATUS_ENTRY_UNAVAILABLE: Final[str] = 'entry_unavailable'
STATUS_ENTRY_RESTRICTED: Final[str] = 'entry_restricted'
STATUS_ENTRY_LIMIT_UP: Final[str] = 'entry_limit_up'
STATUS_EXIT_UNAVAILABLE: Final[str] = 'exit_unavailable'
STATUS_EXIT_LIMIT_DOWN: Final[str] = 'exit_limit_down'
STATUS_INSUFFICIENT_BUDGET: Final[str] = 'insufficient_budget'

STATUS_VALUES: Final[tuple[str, ...]] = (
    STATUS_COMPLETED,
    STATUS_SIGNAL_OUT_OF_RANGE,
    STATUS_NO_NEXT_SESSION,
    STATUS_HORIZON_OUT_OF_RANGE,
    STATUS_ENTRY_UNAVAILABLE,
    STATUS_ENTRY_RESTRICTED,
    STATUS_ENTRY_LIMIT_UP,
    STATUS_EXIT_UNAVAILABLE,
    STATUS_EXIT_LIMIT_DOWN,
    STATUS_INSUFFICIENT_BUDGET,
)

# Board prefixes never eligible for the P2 universe (STAR / BSE).
EXCLUDED_BOARD_PREFIXES_3: Final[tuple[str, ...]] = ('688', '689')
EXCLUDED_BOARD_PREFIXES_1: Final[tuple[str, ...]] = ('4', '8')
# ChiNext excluded: the account has no ChiNext permission (2026-09-17).
CHINEXT_BOARD_PREFIXES: Final[tuple[str, ...]] = ('300', '301', '302')
# CSI cross-listed indexes published inside the SZ 000xxx stock code space:
# they pass every board filter and the liquidity gate but are not tradable
# instruments for this account (found in the standardized table 2026-09-17).
EXCLUDED_INDEX_SYMBOLS: Final[tuple[str, ...]] = ('sz.000905', 'sz.000852')

PRICE_COLUMNS: Final[tuple[str, ...]] = (
    'symbol', 'date', 'open', 'adj_factor', 'tradestatus', 'isST',
)


@dataclass(frozen=True)
class FeeBand:
    """One segment of a historical fee schedule, effective from ``from_date``.

    ``stamp_sell_pct`` is charged on the sell notional only.  Buy fees use the
    band effective on the entry date, sell fees the band on the exit date.
    """

    from_date: date
    commission_pct: float
    commission_min: float
    stamp_sell_pct: float = 0.0

    def __post_init__(self) -> None:
        for name in ('commission_pct', 'commission_min', 'stamp_sell_pct'):
            value = getattr(self, name)
            if not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                raise ValueError(f'{name} must be a finite non-negative number')
        if not isinstance(self.from_date, date):
            raise TypeError('from_date must be a datetime.date')


def validate_fee_schedule(schedule: tuple[FeeBand, ...]) -> None:
    if not schedule:
        raise ValueError('fee_schedule must not be empty')
    previous: date | None = None
    for band in schedule:
        if not isinstance(band, FeeBand):
            raise TypeError('fee_schedule entries must be FeeBand instances')
        if previous is not None and band.from_date <= previous:
            raise ValueError('fee_schedule bands must be strictly increasing by from_date')
        previous = band.from_date


def fee_band_for(schedule: tuple[FeeBand, ...], day: date) -> FeeBand:
    """Last band whose ``from_date`` is on or before ``day`` (schedule sorted)."""
    selected = schedule[0]
    for band in schedule:
        if day >= band.from_date:
            selected = band
        else:
            break
    return selected


@dataclass(frozen=True)
class ScreenConfig:
    """Fixed P2 screen parameters.  ``cost_round_trip`` is a gross-cost
    override used only for synthetic hand-checks; when ``None`` the fee model
    below runs.  With ``fee_schedule=None`` the single all-in commission
    applies to both legs (user '万 1 全包'); with a schedule, buy fees use the
    entry-date band and sell fees the exit-date band (commission + stamp on
    sell).  ``position_budget`` caps the per-event notional below
    ``capital / top_n`` when set (user cap: 50k of 200k).  With
    ``block_limits`` the daily-line limit proxy blocks entries at limit-up
    opens and exits at limit-down opens; ``prices`` must then carry
    ``preclose``."""

    holding_days: int
    top_n: int  # candidate slots per signal day, used for the per-event budget
    cost_round_trip: float | None = None
    capital: float = 200_000.0
    commission_pct: float = COMMISSION_PCT
    commission_min: float = COMMISSION_MIN
    fee_schedule: tuple[FeeBand, ...] | None = None
    position_budget: float | None = None
    slippage_bps: float = 0.0
    block_limits: bool = False
    limit_pct: float = 0.10
    end_date: date = FREEZE_END

    def __post_init__(self) -> None:
        if int(self.holding_days) < 1:
            raise ValueError('holding_days must be >= 1 (T+1)')
        if not 1 <= int(self.top_n) <= 3:
            raise ValueError('top_n must be in 1..3')
        for name in ('capital', 'commission_pct', 'commission_min', 'slippage_bps',
                     'limit_pct'):
            value = getattr(self, name)
            if not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f'{name} must be a finite number')
        if self.capital <= 0:
            raise ValueError('capital must be positive')
        if self.commission_pct < 0 or self.commission_min < 0 or self.slippage_bps < 0:
            raise ValueError('commission/slippage parameters must be non-negative')
        if not 0 < self.limit_pct < 0.5:
            raise ValueError('limit_pct must be in (0, 0.5)')
        if self.position_budget is not None:
            if (not isinstance(self.position_budget, (int, float))
                    or not math.isfinite(self.position_budget) or self.position_budget <= 0):
                raise ValueError('position_budget must be a positive finite number')
        if self.fee_schedule is not None:
            if not isinstance(self.fee_schedule, tuple):
                raise TypeError('fee_schedule must be a tuple of FeeBand')
            validate_fee_schedule(self.fee_schedule)
        if self.cost_round_trip is not None:
            if not math.isfinite(self.cost_round_trip) or self.cost_round_trip < 0:
                raise ValueError('cost_round_trip must be a finite non-negative number')
        if not isinstance(self.end_date, date):
            raise TypeError('end_date must be a datetime.date')

    def event_budget(self) -> float:
        budget = self.capital / self.top_n
        if self.position_budget is not None:
            budget = min(budget, float(self.position_budget))
        return budget


# --------------------------------------------------------------------------- #
# shared validation helpers
# --------------------------------------------------------------------------- #
def _require_columns(frame: pl.DataFrame, columns: tuple[str, ...], name: str) -> None:
    if not isinstance(frame, pl.DataFrame):
        raise TypeError(f'{name} must be a polars.DataFrame, got {type(frame).__name__}')
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise ValueError(f'{name} is missing required columns: {missing}')


def _validate_keys(frame: pl.DataFrame, keys: tuple[str, ...], name: str) -> None:
    for key in keys:
        nulls = int(frame[key].null_count())
        if nulls:
            raise ValueError(f'{name}: key column {key!r} has {nulls} null value(s)')
    duplicates = frame.group_by(list(keys)).len().filter(pl.col('len') > 1)
    if duplicates.height:
        raise ValueError(
            f'{name}: duplicate {list(keys)} keys, examples '
            f'{duplicates.head(3).to_dicts()}')


def _reject_non_finite(frame: pl.DataFrame, columns: tuple[str, ...], name: str) -> None:
    for column in columns:
        if not frame.schema[column].is_numeric():
            raise ValueError(f'{name}: column {column!r} must be numeric')
        finite = frame[column].cast(pl.Float64).is_finite().fill_null(True)
        if not bool(finite.all()):
            raise ValueError(f'{name}: column {column!r} contains nan/inf value(s)')


def _positive_finite(expr: pl.Expr) -> pl.Expr:
    """True only for non-null strictly positive finite values."""
    return expr.is_not_null() & expr.is_finite() & (expr > 0)


def _not_trading(expr: pl.Expr) -> pl.Expr:
    """True when a tradestatus value is null or not 1."""
    return expr.is_null() | (expr != 1)


def _affordable_lots(price: float, budget: float, commission_pct: float,
                     commission_min: float, lot: int = LOT_SIZE) -> int:
    """Largest whole board lot whose notional plus buy fee fits ``budget``.

    The entry minimum fee is honored, so ``amount + max(amount*pct, min) <=
    budget``.  Returns 0 when not even one lot is affordable.
    """
    quantity = int(budget / (price * (1.0 + commission_pct)) // lot) * lot
    while quantity > 0:
        amount = quantity * price
        fee = max(amount * commission_pct, commission_min)
        if amount + fee <= budget + 1e-9:
            break
        quantity -= lot
    return max(quantity, 0)


# --------------------------------------------------------------------------- #
# H3 liquidity / tradability gate
# --------------------------------------------------------------------------- #
def eligible_universe(daily: pl.DataFrame, *, amount_median_window: int = 20,
                      amount_min: float = 50_000_000, price_min: float = 2.0,
                      allow_chinext: bool = False) -> pl.DataFrame:
    """Preregistered H3 gate, evaluated with data known at each close.

    The trailing ``amount_median_window``-row median is computed over every
    historical row *before* any price/status/ST filter, so a filter applied
    today cannot rewrite the past window.  Rows are then kept only when the
    board is allowed, ``tradestatus == 1``, ``close >= price_min``,
    ``isST == 0`` and ``amount_med20 >= amount_min``.  Unknown (null) ST is
    rejected as ineligible.  Non-finite values raise ``ValueError``; nonpositive
    price/amount simply fail the thresholds.  Output is sorted by (symbol, date).
    """
    if int(amount_median_window) < 1:
        raise ValueError('amount_median_window must be >= 1')
    _require_columns(daily, ('symbol', 'date', 'close', 'amount', 'tradestatus', 'isST'),
                     'daily')
    _validate_keys(daily, ('symbol', 'date'), 'daily')
    _reject_non_finite(daily, ('close', 'amount', 'tradestatus', 'isST'), 'daily')
    if daily.schema['date'] != pl.Date:
        raise ValueError("daily: column 'date' must have dtype Date")

    code = pl.col('symbol').str.split('.').list.last()
    board3 = code.str.slice(0, 3)
    allowed = (
        ~board3.is_in(list(EXCLUDED_BOARD_PREFIXES_3))
        & ~code.str.slice(0, 1).is_in(list(EXCLUDED_BOARD_PREFIXES_1))
        & ~pl.col('symbol').is_in(list(EXCLUDED_INDEX_SYMBOLS))
    )
    if not allow_chinext:
        allowed = allowed & ~board3.is_in(list(CHINEXT_BOARD_PREFIXES))

    # Median first (all rows), filters second: today's gate cannot rewrite it.
    ordered = daily.sort('symbol', 'date')
    return (ordered
            .with_columns(
                pl.col('amount')
                  .rolling_median(int(amount_median_window),
                                  min_samples=int(amount_median_window))
                  .over('symbol').alias('amount_med20'))
            .filter(allowed
                    & (pl.col('tradestatus') == 1)
                    & (pl.col('close') >= price_min)
                    & (pl.col('isST') == 0)
                    & (pl.col('amount_med20') >= amount_min)))


# --------------------------------------------------------------------------- #
# daily ranking
# --------------------------------------------------------------------------- #
def daily_rank_picks(feat: pl.DataFrame, score_expr: pl.Expr, *, n_per_day: int,
                     signal_date_col: str = 'date',
                     symbol_col: str = 'symbol') -> pl.DataFrame:
    """Score rows at close t and pick the top ``n_per_day`` per session.

    Negative scores are valid; only null, NaN and infinite scores are excluded.
    Ties are broken deterministically by symbol.  ``n_per_day`` must be 1..3.
    """
    if not 1 <= int(n_per_day) <= 3:
        raise ValueError('n_per_day must be in 1..3')
    _require_columns(feat, (signal_date_col, symbol_col), 'feat')

    score = score_expr.cast(pl.Float64)
    return (feat
            .with_columns(score.alias('score'))
            .filter(pl.col('score').is_not_null() & pl.col('score').is_finite())
            .sort([signal_date_col, 'score', symbol_col],
                  descending=[False, True, False])
            .group_by(signal_date_col, maintain_order=True).head(int(n_per_day))
            .rename({signal_date_col: 'signal_date'}))


# --------------------------------------------------------------------------- #
# event study
# --------------------------------------------------------------------------- #
def _calendar(prices: pl.DataFrame, calendar: pl.Series | None,
              end_boundary: date) -> pl.Series:
    if calendar is None:
        sessions = prices.select('date').unique().sort('date')['date']
    else:
        if not isinstance(calendar, pl.Series):
            raise TypeError('calendar must be a polars.Series of Dates')
        if calendar.dtype != pl.Date:
            raise ValueError('calendar must have dtype Date')
        if calendar.null_count():
            raise ValueError('calendar contains null dates')
        sessions = (pl.DataFrame({'date': calendar}).unique().sort('date')
                    .filter(pl.col('date') <= end_boundary)['date'])
    return sessions.sort().filter(sessions <= end_boundary)


def _event_metrics(row: dict, cfg: ScreenConfig) -> dict:
    entry, entry_adj = float(row['entry_price']), float(row['entry_adj_factor'])
    exit_px, exit_adj = float(row['exit_price']), float(row['exit_adj_factor'])
    gross = exit_px * exit_adj / (entry * entry_adj) - 1.0

    if cfg.cost_round_trip is not None:
        # Gross-cost override for synthetic hand-checks: no lot/budget model.
        return {'_row_id': row['_row_id'], 'gross_return': gross,
                'net_return_pct': (gross - cfg.cost_round_trip) * 100.0,
                'quantity': None, 'entry_notional': None, 'buy_fee': None,
                'exit_notional': None, 'sell_fee': None}

    buy_band = (fee_band_for(cfg.fee_schedule, row['entry_date'])
                if cfg.fee_schedule is not None else None)
    sell_band = (fee_band_for(cfg.fee_schedule, row['exit_date'])
                 if cfg.fee_schedule is not None else None)
    buy_pct = buy_band.commission_pct if buy_band is not None else cfg.commission_pct
    buy_min = buy_band.commission_min if buy_band is not None else cfg.commission_min
    sell_pct = sell_band.commission_pct if sell_band is not None else cfg.commission_pct
    sell_min = sell_band.commission_min if sell_band is not None else cfg.commission_min
    sell_stamp = sell_band.stamp_sell_pct if sell_band is not None else 0.0

    budget = cfg.event_budget()
    buy_slip = cfg.slippage_bps / 10_000.0
    sell_slip = cfg.slippage_bps / 10_000.0
    price_eff = entry * (1.0 + buy_slip)
    quantity = _affordable_lots(price_eff, budget, buy_pct, buy_min)
    if quantity == 0:
        return {'_row_id': row['_row_id'], 'gross_return': gross,
                'net_return_pct': None, 'quantity': 0, 'entry_notional': None,
                'buy_fee': None, 'exit_notional': None, 'sell_fee': None}

    entry_notional = quantity * price_eff
    buy_fee = max(entry_notional * buy_pct, buy_min)
    # Indicative exit notional scaled by the adjusted gross (not a corporate
    # action cash ledger); fees are charged on that indicative notional.
    exit_notional = entry_notional * (1.0 + gross)
    sell_fee = (max(exit_notional * sell_pct, sell_min)
                + exit_notional * sell_stamp)
    proceeds = exit_notional * (1.0 - sell_slip)
    net = (proceeds - sell_fee) / (entry_notional + buy_fee) - 1.0
    return {'_row_id': row['_row_id'], 'gross_return': gross,
            'net_return_pct': net * 100.0, 'quantity': quantity,
            'entry_notional': entry_notional, 'buy_fee': buy_fee,
            'exit_notional': exit_notional, 'sell_fee': sell_fee}


_METRIC_SCHEMA = {
    '_row_id': pl.UInt32, 'gross_return': pl.Float64, 'net_return_pct': pl.Float64,
    'quantity': pl.Int64, 'entry_notional': pl.Float64, 'buy_fee': pl.Float64,
    'exit_notional': pl.Float64, 'sell_fee': pl.Float64,
}

_OUTPUT_METRICS = (
    'status', 'entry_date', 'exit_date', 'entry_price', 'exit_price',
    'entry_adj_factor', 'exit_adj_factor', 'gross_return', 'net_return_pct',
    'quantity', 'entry_notional', 'buy_fee', 'exit_notional', 'sell_fee',
)

_HELPER_COLUMNS = ('entry_tradestatus', 'entry_isST', 'exit_tradestatus', 'exit_isST',
                   'entry_preclose', 'exit_preclose')


def screen_returns(scored: pl.DataFrame, prices: pl.DataFrame, cfg: ScreenConfig,
                   *, calendar: pl.Series | None = None) -> pl.DataFrame:
    """Attach entry/exit sessions, raw prices and labels to every scored event.

    ``scored`` needs ``symbol`` and ``signal_date`` (unique, non-null); extra
    columns are preserved.  ``prices`` needs ``symbol, date, open, adj_factor,
    tradestatus, isST`` (unique ``(symbol, date)``).  ``calendar`` is an
    optional ``pl.Series`` of market dates; by default the sorted unique price
    dates are used.  Session indices come from the calendar and prices are
    joined on exact ``(symbol, date)`` -- never a range or many-to-many join.

    Prices are hard-filtered to ``<= min(cfg.end_date, 2024-12-31)``; signals
    outside that boundary are flagged and receive no labels.  Entry ST
    true/unknown blocks trading.  Suspended or missing entry/exit sessions are
    reported (``entry_unavailable`` / ``exit_unavailable``) and never delayed
    to a later session.  Rows that pass but cannot afford one board lot get
    ``insufficient_budget``.
    """
    if not isinstance(cfg, ScreenConfig):
        raise TypeError('cfg must be a ScreenConfig')
    _require_columns(prices, PRICE_COLUMNS, 'prices')
    if cfg.block_limits and 'preclose' not in prices.columns:
        raise ValueError("prices must carry 'preclose' when cfg.block_limits is set")
    _require_columns(scored, ('symbol', 'signal_date'), 'scored')
    _validate_keys(prices, ('symbol', 'date'), 'prices')
    _validate_keys(scored, ('symbol', 'signal_date'), 'scored')
    if prices.schema['date'] != pl.Date or scored.schema['signal_date'] != pl.Date:
        raise ValueError('date and signal_date columns must have dtype Date')

    end_boundary = min(cfg.end_date, FREEZE_END)
    px = prices.sort('symbol', 'date').filter(pl.col('date') <= end_boundary)
    sessions = _calendar(px, calendar, end_boundary)
    n_sessions = len(sessions)

    cal = pl.DataFrame({'date': sessions}).with_row_index('_cal_index')
    events = scored.with_row_index('_row_id')
    ev = events.join(cal.rename({'date': 'signal_date'}), on='signal_date', how='left')
    ev = ev.with_columns(
        pl.when(pl.col('_cal_index').is_not_null())
          .then(pl.col('_cal_index').cast(pl.Int64) + 1)
          .otherwise(None).alias('_entry_idx'))
    ev = ev.with_columns((pl.col('_entry_idx') + int(cfg.holding_days)).alias('_exit_idx'))

    index_dates = cal.select(pl.col('_cal_index').cast(pl.Int64), pl.col('date'))
    ev = ev.join(index_dates.rename({'_cal_index': '_entry_idx', 'date': 'entry_date'}),
                 on='_entry_idx', how='left')
    ev = ev.join(index_dates.rename({'_cal_index': '_exit_idx', 'date': 'exit_date'}),
                 on='_exit_idx', how='left')

    entry_px = px.select(
        'symbol', pl.col('date').alias('entry_date'),
        pl.col('open').alias('entry_price'),
        pl.col('adj_factor').alias('entry_adj_factor'),
        pl.col('tradestatus').alias('entry_tradestatus'),
        pl.col('isST').alias('entry_isST'),
        pl.col('preclose').alias('entry_preclose') if 'preclose' in px.columns else pl.lit(None, dtype=pl.Float64).alias('entry_preclose'),
        pl.lit(True).alias('_entry_row'))
    exit_px = px.select(
        'symbol', pl.col('date').alias('exit_date'),
        pl.col('open').alias('exit_price'),
        pl.col('adj_factor').alias('exit_adj_factor'),
        pl.col('tradestatus').alias('exit_tradestatus'),
        pl.col('isST').alias('exit_isST'),
        pl.col('preclose').alias('exit_preclose') if 'preclose' in px.columns else pl.lit(None, dtype=pl.Float64).alias('exit_preclose'),
        pl.lit(True).alias('_exit_row'))
    ev = ev.join(entry_px, on=['symbol', 'entry_date'], how='left')
    ev = ev.join(exit_px, on=['symbol', 'exit_date'], how='left')

    has_next = pl.col('_entry_idx').is_not_null() & (pl.col('_entry_idx') < n_sessions)
    has_exit = has_next & (pl.col('_exit_idx') < n_sessions)
    entry_ok = (
        pl.col('_entry_row').is_not_null()
        & ~_not_trading(pl.col('entry_tradestatus'))
        & (pl.col('entry_isST') == 0)
        & _positive_finite(pl.col('entry_price'))
        & _positive_finite(pl.col('entry_adj_factor'))
    )
    exit_ok = (
        pl.col('_exit_row').is_not_null()
        & ~_not_trading(pl.col('exit_tradestatus'))
        & _positive_finite(pl.col('exit_price'))
        & _positive_finite(pl.col('exit_adj_factor'))
    )
    # Daily-line limit proxy (registered approximation, P3 re-checks on
    # minute data): an open at/above the rounded limit-up price is not a
    # fillable buy, an open at/below limit-down not a fillable sell.  The
    # 0.005 tolerance covers exchange round-half-up vs float rounding.
    if cfg.block_limits:
        entry_limit_up = pl.col('entry_price') >= (
            (pl.col('entry_preclose') * (1.0 + cfg.limit_pct)).round(2) - 0.005)
        exit_limit_down = pl.col('exit_price') <= (
            (pl.col('exit_preclose') * (1.0 - cfg.limit_pct)).round(2) + 0.005)
    else:
        entry_limit_up = pl.lit(False)
        exit_limit_down = pl.lit(False)

    ev = ev.with_columns(
        pl.when(pl.col('_cal_index').is_null()).then(pl.lit(STATUS_SIGNAL_OUT_OF_RANGE))
          .when(~has_next).then(pl.lit(STATUS_NO_NEXT_SESSION))
          .when(~has_exit).then(pl.lit(STATUS_HORIZON_OUT_OF_RANGE))
          .when(pl.col('_entry_row').is_null()).then(pl.lit(STATUS_ENTRY_UNAVAILABLE))
          .when(pl.col('entry_isST').is_null() | (pl.col('entry_isST') != 0))
              .then(pl.lit(STATUS_ENTRY_RESTRICTED))
          .when(~entry_ok).then(pl.lit(STATUS_ENTRY_UNAVAILABLE))
          .when(entry_limit_up).then(pl.lit(STATUS_ENTRY_LIMIT_UP))
          .when(~exit_ok).then(pl.lit(STATUS_EXIT_UNAVAILABLE))
          .when(exit_limit_down).then(pl.lit(STATUS_EXIT_LIMIT_DOWN))
          .otherwise(pl.lit('_ready')).alias('status'))

    ready = (ev.filter(pl.col('status') == '_ready')
             .select('_row_id', 'entry_date', 'exit_date', 'entry_price',
                     'entry_adj_factor', 'exit_price', 'exit_adj_factor'))
    records = [_event_metrics(row, cfg) for row in ready.iter_rows(named=True)]
    metrics = pl.DataFrame(records, schema=_METRIC_SCHEMA)

    available = pl.col('status') == '_ready'
    ev = ev.with_columns(
        pl.when(available).then(pl.col('entry_price')).otherwise(None).alias('entry_price'),
        pl.when(available).then(pl.col('entry_adj_factor')).otherwise(None).alias('entry_adj_factor'),
        pl.when(available).then(pl.col('exit_price')).otherwise(None).alias('exit_price'),
        pl.when(available).then(pl.col('exit_adj_factor')).otherwise(None).alias('exit_adj_factor'),
    )
    ev = ev.join(metrics, on='_row_id', how='left')

    if cfg.cost_round_trip is not None:
        final_status = (pl.when(pl.col('status') != '_ready').then(pl.col('status'))
                        .otherwise(pl.lit(STATUS_COMPLETED)))
    else:
        final_status = (pl.when(pl.col('status') != '_ready').then(pl.col('status'))
                        .when(pl.col('quantity') > 0).then(pl.lit(STATUS_COMPLETED))
                        .otherwise(pl.lit(STATUS_INSUFFICIENT_BUDGET)))
    ev = ev.with_columns(final_status.alias('status'))

    drop = [c for c in ev.columns if c.startswith('_')]
    drop += [c for c in _HELPER_COLUMNS if c in ev.columns]
    ev = ev.drop(drop)
    extras = [c for c in ev.columns
              if c not in ('symbol', 'signal_date', *_OUTPUT_METRICS)]
    return ev.select(['symbol', 'signal_date', *extras, *_OUTPUT_METRICS]).sort(
        'symbol', 'signal_date')
