"""Re-cost saved P2 event studies under a different fee schedule.

Reads ``events.parquet`` files saved by the P2 screen pipeline (one row per
candidate event, including per-event fees charged under the original
historical fee schedule) and re-applies a *target* fee schedule to the exact
same trades.  Trade selection, quantity and entry notional stay frozen: this
module never re-runs a strategy, re-selects candidates or re-sizes positions
-- it only re-prices the two fee legs of each already-saved trade.

Per trade (mirrors ``screen._event_metrics`` exactly, slippage excluded
because the source runs were saved with ``slippage_bps = 0``)::

    buy_fee  = max(entry_notional * buy_commission_pct, commission_min)
    exit_notional = entry_notional * (1 + gross_return)   # as saved
    sell_fee = max(exit_notional * sell_commission_pct, commission_min)
               + exit_notional * stamp_sell_pct
    net      = (exit_notional - sell_fee) / (entry_notional + buy_fee) - 1

The original schedule is re-applied as well and must reproduce the saved
``buy_fee`` / ``sell_fee`` / ``net_return_pct`` columns bit-tight; a mismatch
raises ``FeeRecostError`` so stale or hand-edited inputs cannot silently pass.
"""

from __future__ import annotations

import math
from datetime import date
from typing import Final

import polars as pl

from quant.research.screen import FeeBand, fee_band_for, validate_fee_schedule

STATUS_COMPLETED: Final[str] = 'completed_label'
DEV_END: Final[date] = date(2020, 12, 31)
VALIDATION_START: Final[date] = date(2021, 1, 1)

# Symbol prefixes that would indicate fund/ETF instruments (baostock codes).
# The P2 screens are stock-only; the target account also has an ETF rate but
# it cannot apply to any event in these runs.
_ETF_PREFIXES: Final[tuple[str, ...]] = ('sh.5', 'sz.15', 'sh.50', 'sh.51',
                                         'sh.56', 'sh.58', 'sz.16', 'sz.18')

_REQUIRED_COLUMNS: Final[tuple[str, ...]] = (
    'symbol', 'signal_date', 'status', 'entry_date', 'exit_date',
    'gross_return', 'net_return_pct', 'quantity', 'entry_notional',
    'buy_fee', 'exit_notional', 'sell_fee', 'config_id',
)

# Saved fees must reproduce to within this absolute tolerance (yuan) before
# the target-schedule recost is applied.
_VERIFY_TOLERANCE: Final[float] = 1e-6


class FeeRecostError(ValueError):
    """Raised when saved events do not reproduce under the original schedule."""


def validate_target_schedule(schedule: tuple[FeeBand, ...]) -> None:
    """The target schedule must be a valid, non-empty fee schedule."""
    if not schedule:
        raise FeeRecostError('target fee schedule must not be empty')
    validate_fee_schedule(schedule)


def check_stock_only(events: pl.DataFrame) -> int:
    """Return the number of fund-like symbols; the P2 pool must have zero."""
    symbols = events['symbol'].unique().to_list()
    fund_like = [s for s in symbols
                 if isinstance(s, str) and s.startswith(_ETF_PREFIXES)]
    return len(fund_like)


def window_for(signal_date: date) -> str | None:
    """Dev/validation split used by every P2 round (by signal date)."""
    if signal_date <= DEV_END:
        return 'dev'
    if signal_date >= VALIDATION_START:
        return 'validation'
    return None


def _legs(notional: float, band: FeeBand) -> tuple[float, float]:
    """(commission, stamp) charged on one leg at ``band``."""
    return max(notional * band.commission_pct, band.commission_min), \
        notional * band.stamp_sell_pct


def recost_events(events: pl.DataFrame, *, run_tag: str,
                  old_schedule: tuple[FeeBand, ...],
                  target_schedule: tuple[FeeBand, ...]) -> pl.DataFrame:
    """Re-price every completed saved event under ``target_schedule``.

    Returns one row per completed event with old/new fees and net returns.
    Raises :class:`FeeRecostError` when the saved fees do not reproduce under
    ``old_schedule`` or when the saved notionals are inconsistent.
    """
    missing = [c for c in _REQUIRED_COLUMNS if c not in events.columns]
    if missing:
        raise FeeRecostError(f'{run_tag}: events missing columns: {missing}')
    if events['signal_date'].dtype != pl.Date:
        events = events.with_columns(pl.col('signal_date').cast(pl.Date))
    if events['entry_date'].dtype != pl.Date:
        events = events.with_columns(pl.col('entry_date').cast(pl.Date))
    if events['exit_date'].dtype != pl.Date:
        events = events.with_columns(pl.col('exit_date').cast(pl.Date))

    fund_like = check_stock_only(events)
    if fund_like:
        raise FeeRecostError(
            f'{run_tag}: {fund_like} fund/ETF-like symbols found; the ETF '
            'fee rate would be required but this pipeline is stock-only')

    done = events.filter(pl.col('status') == STATUS_COMPLETED)
    rows = done.to_dicts()
    out = []
    for row in rows:
        entry_notional = float(row['entry_notional'])
        exit_notional = float(row['exit_notional'])
        gross = float(row['gross_return'])
        if not (math.isfinite(entry_notional) and math.isfinite(exit_notional)
                and entry_notional > 0.0):
            raise FeeRecostError(
                f"{run_tag}: bad notionals for {row['symbol']} "
                f"{row['signal_date']}")
        if abs(exit_notional - entry_notional * (1.0 + gross)) > 1e-6:
            raise FeeRecostError(
                f"{run_tag}: exit_notional inconsistent with gross_return "
                f"for {row['symbol']} {row['signal_date']}")

        entry_day, exit_day = row['entry_date'], row['exit_date']
        old_buy_comm, _ = _legs(entry_notional, fee_band_for(old_schedule, entry_day))
        old_sell_comm, old_sell_stamp = _legs(exit_notional, fee_band_for(old_schedule, exit_day))
        old_buy_fee = old_buy_comm
        old_sell_fee = old_sell_comm + old_sell_stamp
        saved_buy, saved_sell = float(row['buy_fee']), float(row['sell_fee'])
        if (abs(saved_buy - old_buy_fee) > _VERIFY_TOLERANCE
                or abs(saved_sell - old_sell_fee) > _VERIFY_TOLERANCE):
            raise FeeRecostError(
                f"{run_tag}: saved fees do not reproduce under the original "
                f"schedule for {row['symbol']} {row['signal_date']} "
                f'(buy {saved_buy} vs {old_buy_fee}, sell {saved_sell} '
                f'vs {old_sell_fee})')

        new_buy_comm, _ = _legs(entry_notional, fee_band_for(target_schedule, entry_day))
        new_sell_comm, new_sell_stamp = _legs(exit_notional, fee_band_for(target_schedule, exit_day))
        new_buy_fee = new_buy_comm
        new_sell_fee = new_sell_comm + new_sell_stamp

        net_old = (exit_notional - old_sell_fee) / (entry_notional + old_buy_fee) - 1.0
        net_new = (exit_notional - new_sell_fee) / (entry_notional + new_buy_fee) - 1.0
        saved_net = float(row['net_return_pct']) / 100.0
        if abs(saved_net - net_old) > 1e-9:
            raise FeeRecostError(
                f"{run_tag}: saved net_return_pct inconsistent for "
                f"{row['symbol']} {row['signal_date']}")

        window = window_for(row['signal_date'])
        out.append({
            'run_tag': run_tag,
            'config_id': row['config_id'],
            'signal_set': row.get('signal_set'),
            'hold': row.get('hold'),
            'symbol': row['symbol'],
            'signal_date': row['signal_date'],
            'entry_date': entry_day,
            'exit_date': exit_day,
            'window': window,
            'year': row['signal_date'].year,
            'entry_notional': entry_notional,
            'exit_notional': exit_notional,
            'gross_return': gross,
            'buy_fee_old': old_buy_fee,
            'sell_fee_old': old_sell_fee,
            'net_old': net_old,
            'buy_fee_new': new_buy_fee,
            'sell_fee_new': new_sell_fee,
            'net_new': net_new,
            'net_diff': net_new - net_old,
            'drag_old': gross - net_old,
            'drag_new': gross - net_new,
        })
    return pl.DataFrame(out)


_AGG_MAP: Final[dict[str, pl.Expr]] = {
    'n_completed': pl.len(),
    'mean_gross_pct': pl.col('gross_return').mean() * 100.0,
    'mean_net_old_pct': pl.col('net_old').mean() * 100.0,
    'mean_net_new_pct': pl.col('net_new').mean() * 100.0,
    'mean_net_diff_pp': pl.col('net_diff').mean() * 100.0,
    'mean_drag_old_pp': pl.col('drag_old').mean() * 100.0,
    'mean_drag_new_pp': pl.col('drag_new').mean() * 100.0,
    'total_profit_old_yuan': (
        (pl.col('net_old') * (pl.col('entry_notional') + pl.col('buy_fee_old')))
        .sum()),
    'total_profit_new_yuan': (
        (pl.col('net_new') * (pl.col('entry_notional') + pl.col('buy_fee_new')))
        .sum()),
    'total_fees_old_yuan': (pl.col('buy_fee_old') + pl.col('sell_fee_old')).sum(),
    'total_fees_new_yuan': (pl.col('buy_fee_new') + pl.col('sell_fee_new')).sum(),
}


def summarize(recosted: pl.DataFrame) -> pl.DataFrame:
    """Aggregate re-costed events per run_tag x config_id x window.

    ``window`` is one of ``dev`` / ``validation`` / ``other`` (events whose
    signal date falls in neither registered window; the P2 pipeline should
    produce none of the last).
    """
    frame = recosted.with_columns(
        pl.col('window').fill_null('other'))
    keys = ['run_tag', 'config_id', 'window']
    return frame.group_by(keys).agg(**_AGG_MAP).sort(keys)
