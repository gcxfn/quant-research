"""P2 screen contract tests on synthetic data with hand-checked values.

These tests pin the corrected event-study semantics: exact next market session
entry, trading-day holding horizon, raw vs adjusted labels, all-in fee model
(no separate stamp), preserved events with statuses, and the gate's
past-window/board/ST rules.  Synthetic frames are contract data only, never
profitability evidence.
"""
from __future__ import annotations

from datetime import date, timedelta

import polars as pl
import pytest

from quant.research.screen import (  # noqa: E402
    STATUS_COMPLETED,
    STATUS_ENTRY_LIMIT_UP,
    STATUS_ENTRY_RESTRICTED,
    STATUS_ENTRY_UNAVAILABLE,
    STATUS_EXIT_LIMIT_DOWN,
    STATUS_EXIT_UNAVAILABLE,
    STATUS_HORIZON_OUT_OF_RANGE,
    STATUS_INSUFFICIENT_BUDGET,
    STATUS_NO_NEXT_SESSION,
    STATUS_SIGNAL_OUT_OF_RANGE,
    STATUS_VALUES,
    FeeBand,
    ScreenConfig,
    daily_rank_picks,
    eligible_universe,
    fee_band_for,
    screen_returns,
)

D = date


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def weekdays(count: int, start: date = D(2022, 1, 4)) -> list[date]:
    days: list[date] = []
    day = start
    while len(days) < count:
        if day.weekday() < 5:
            days.append(day)
        day += timedelta(days=1)
    return days


def px_frame(symbol: str, dates: list[date], opens: list[float], *,
             adj: list[float] | None = None,
             tradestatus: list[float] | None = None,
             isST: list[float | None] | None = None) -> pl.DataFrame:
    n = len(dates)
    return pl.DataFrame({
        'symbol': [symbol] * n,
        'date': dates,
        'open': opens,
        'adj_factor': adj if adj is not None else [1.0] * n,
        'tradestatus': tradestatus if tradestatus is not None else [1.0] * n,
        'isST': isST if isST is not None else [0.0] * n,
    }, schema_overrides={'date': pl.Date})


def scored_frame(symbol: str, signal_date: date, **extra: object) -> pl.DataFrame:
    data: dict[str, list[object]] = {'symbol': [symbol], 'signal_date': [signal_date]}
    data.update({name: [value] for name, value in extra.items()})
    return pl.DataFrame(data, schema_overrides={'signal_date': pl.Date})


def daily_frame(symbol: str, dates: list[date], *, close: float = 3.0,
                amount: float = 60_000_000.0, tradestatus: float = 1.0,
                isST: float | None = 0.0) -> pl.DataFrame:
    n = len(dates)
    return pl.DataFrame({
        'symbol': [symbol] * n,
        'date': dates,
        'close': [float(close)] * n,
        'amount': [float(amount)] * n,
        'tradestatus': [float(tradestatus)] * n,
        'isST': [isST] * n,
    }, schema_overrides={'date': pl.Date})


def row_of(frame: pl.DataFrame) -> dict:
    assert frame.height == 1
    return frame.row(0, named=True)


# --------------------------------------------------------------------------- #
# event study: entry / exit sessions
# --------------------------------------------------------------------------- #
def test_entry_is_next_session_open_not_close():
    # opens deliberately different from closes; entry must use the next open
    prices = px_frame('sh.600000', weekdays(4), opens=[10.0, 11.0, 12.0, 13.0])
    out = screen_returns(scored_frame('sh.600000', D(2022, 1, 4)), prices,
                         ScreenConfig(holding_days=1, top_n=1, cost_round_trip=0.0))
    row = row_of(out)
    assert row['entry_date'] == D(2022, 1, 5)
    assert row['exit_date'] == D(2022, 1, 6)
    assert row['entry_price'] == 11.0   # raw next open, not the 01-04 close
    assert row['exit_price'] == 12.0
    assert row['status'] == STATUS_COMPLETED
    assert row['gross_return'] == pytest.approx(12.0 / 11.0 - 1.0, rel=1e-12)
    assert row['net_return_pct'] == pytest.approx((12.0 / 11.0 - 1.0) * 100, rel=1e-12)


def test_weekend_is_one_session_not_three_days():
    # Thu, Fri, Mon, Tue: Friday's next session is Monday
    dates = [D(2022, 1, 6), D(2022, 1, 7), D(2022, 1, 10), D(2022, 1, 11)]
    prices = px_frame('sh.600000', dates, opens=[10.0, 11.0, 12.0, 13.0])
    out = screen_returns(scored_frame('sh.600000', D(2022, 1, 7)), prices,
                         ScreenConfig(holding_days=1, top_n=1, cost_round_trip=0.0))
    row = row_of(out)
    assert (row['entry_date'] - D(2022, 1, 7)).days == 3  # calendar days apart
    assert row['entry_date'] == D(2022, 1, 10)            # but one session later
    assert row['exit_date'] == D(2022, 1, 11)             # entry index + 1 session


def test_explicit_calendar_defines_sessions():
    # 01-05 exists in prices but is not in the passed calendar: entry is 01-06
    dates = weekdays(4)  # 01-04, 01-05, 01-06, 01-07
    prices = px_frame('sh.600000', dates, opens=[10.0, 11.0, 12.0, 13.0])
    calendar = pl.Series('date', [D(2022, 1, 4), D(2022, 1, 6), D(2022, 1, 7)],
                         dtype=pl.Date)
    out = screen_returns(scored_frame('sh.600000', D(2022, 1, 4)), prices,
                         ScreenConfig(holding_days=1, top_n=1, cost_round_trip=0.0),
                         calendar=calendar)
    row = row_of(out)
    assert row['entry_date'] == D(2022, 1, 6)
    assert row['entry_price'] == 12.0
    assert row['exit_date'] == D(2022, 1, 7)


def test_holding_days_one_is_t_plus_one_and_zero_rejected():
    with pytest.raises(ValueError):
        ScreenConfig(holding_days=0, top_n=1)
    prices = px_frame('sh.600000', weekdays(4), opens=[10.0, 11.0, 12.0, 13.0])
    out = screen_returns(scored_frame('sh.600000', D(2022, 1, 4)), prices,
                         ScreenConfig(holding_days=1, top_n=1, cost_round_trip=0.0))
    row = row_of(out)
    assert row['exit_date'] > row['entry_date']           # same-day sale impossible
    assert row['exit_date'] == D(2022, 1, 6)


# --------------------------------------------------------------------------- #
# event study: boundaries, missing and blocked sessions
# --------------------------------------------------------------------------- #
def test_end_date_filters_future_and_flags_labels():
    dates = weekdays(4)
    prices = px_frame('sh.600000', dates, opens=[10.0, 11.0, 12.0, 13.0])
    cfg = ScreenConfig(holding_days=2, top_n=1, cost_round_trip=0.0,
                       end_date=D(2022, 1, 6))
    # 01-05 -> entry 01-06 -> exit would be 01-07, beyond the hard boundary
    late = screen_returns(scored_frame('sh.600000', D(2022, 1, 5)), prices, cfg)
    late_row = row_of(late)
    assert late_row['status'] == STATUS_HORIZON_OUT_OF_RANGE
    assert late_row['net_return_pct'] is None and late_row['gross_return'] is None
    assert late_row['exit_date'] is None
    # 01-06 is the last allowed session -> no next session to enter
    last = screen_returns(scored_frame('sh.600000', D(2022, 1, 6)), prices, cfg)
    assert row_of(last)['status'] == STATUS_NO_NEXT_SESSION


def test_global_2024_freeze_ignores_later_prices():
    prices = px_frame('sh.600000', [D(2024, 12, 30), D(2024, 12, 31), D(2025, 1, 2)],
                      opens=[10.0, 11.0, 99.0])
    out = screen_returns(scored_frame('sh.600000', D(2024, 12, 30)), prices,
                         ScreenConfig(holding_days=1, top_n=1, cost_round_trip=0.0))
    row = row_of(out)
    assert row['entry_date'] == D(2024, 12, 31)
    assert row['status'] == STATUS_HORIZON_OUT_OF_RANGE  # 2025-01-02 is filtered out


def test_signal_out_of_range_has_no_labels():
    prices = px_frame('sh.600000', weekdays(4), opens=[10.0, 11.0, 12.0, 13.0])
    # before data start and after the configured end both flag, not raise
    for signal in (D(2022, 1, 3), D(2022, 2, 1)):
        out = screen_returns(scored_frame('sh.600000', signal), prices,
                             ScreenConfig(holding_days=1, top_n=1, cost_round_trip=0.0))
        row = row_of(out)
        assert row['status'] == STATUS_SIGNAL_OUT_OF_RANGE
        assert row['entry_date'] is None and row['net_return_pct'] is None


def test_future_append_preboundary_does_not_change_labels():
    short = px_frame('sh.600000', weekdays(4), opens=[10.0, 11.0, 12.0, 13.0])
    long = px_frame('sh.600000', weekdays(9),
                    opens=[10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0, 18.0])
    cfg = ScreenConfig(holding_days=1, top_n=1, cost_round_trip=0.0)
    event = scored_frame('sh.600000', D(2022, 1, 4))
    baseline, appended = screen_returns(event, short, cfg), screen_returns(event, long, cfg)
    for column in ('status', 'entry_date', 'exit_date', 'entry_price', 'exit_price',
                   'gross_return', 'net_return_pct'):
        assert baseline[column].to_list() == appended[column].to_list(), column


def test_entry_st_true_or_unknown_blocks():
    dates = weekdays(3)
    for is_st in (1.0, None):
        prices = px_frame('sh.600000', dates, opens=[10.0, 11.0, 12.0],
                          isST=[0.0, is_st, 0.0])
        out = screen_returns(scored_frame('sh.600000', D(2022, 1, 4)), prices,
                             ScreenConfig(holding_days=1, top_n=1, cost_round_trip=0.0))
        row = row_of(out)
        assert row['status'] == STATUS_ENTRY_RESTRICTED
        assert row['entry_price'] is None and row['net_return_pct'] is None


def test_unavailable_entry_is_not_delayed_to_a_later_session():
    # 01-05 suspended, 01-06 tradable: entry stays 01-05 and is unavailable
    prices = px_frame('sh.600000', weekdays(4), opens=[10.0, 10.0, 11.0, 12.0],
                      tradestatus=[1.0, 0.0, 1.0, 1.0])
    out = screen_returns(scored_frame('sh.600000', D(2022, 1, 4)), prices,
                         ScreenConfig(holding_days=1, top_n=1, cost_round_trip=0.0))
    row = row_of(out)
    assert row['status'] == STATUS_ENTRY_UNAVAILABLE
    assert row['entry_date'] == D(2022, 1, 5)   # exact next session, not 01-06
    assert row['entry_price'] is None and row['net_return_pct'] is None


def test_unavailable_exit_is_unresolved_not_sold_later():
    # 01-06 suspended, 01-07 tradable: no later sale is invented
    prices = px_frame('sh.600000', weekdays(4), opens=[10.0, 11.0, 11.0, 12.0],
                      tradestatus=[1.0, 1.0, 0.0, 1.0])
    out = screen_returns(scored_frame('sh.600000', D(2022, 1, 4)), prices,
                         ScreenConfig(holding_days=1, top_n=1, cost_round_trip=0.0))
    row = row_of(out)
    assert row['status'] == STATUS_EXIT_UNAVAILABLE
    assert row['exit_date'] == D(2022, 1, 6)    # scheduled (suspended) session
    assert row['exit_price'] is None and row['net_return_pct'] is None


def test_missing_rows_are_preserved_not_dropped():
    other = px_frame('sh.600001', weekdays(4), opens=[5.0, 6.0, 7.0, 8.0])
    scored = pl.concat([
        scored_frame('sh.600000', D(2022, 1, 4)),  # symbol has no price rows at all
        scored_frame('sh.600001', D(2022, 1, 4), score=1.0),
    ], how='diagonal')
    out = screen_returns(scored, other, ScreenConfig(holding_days=1, top_n=1,
                                                     cost_round_trip=0.0))
    assert out.height == 2  # every scored event retained
    missing = out.filter(pl.col('symbol') == 'sh.600000').row(0, named=True)
    assert missing['status'] == STATUS_ENTRY_UNAVAILABLE
    assert missing['score'] is None
    present = out.filter(pl.col('symbol') == 'sh.600001').row(0, named=True)
    assert present['status'] == STATUS_COMPLETED and present['score'] == 1.0


# --------------------------------------------------------------------------- #
# event study: labels and costs
# --------------------------------------------------------------------------- #
def test_raw_price_kept_but_label_uses_adjustment_factor():
    # ex-date on 01-06: raw open jumps 10->11 while the factor moves 1.0->1.1
    prices = px_frame('sh.600000', weekdays(3), opens=[10.0, 10.0, 11.0],
                      adj=[1.0, 1.0, 1.1])
    out = screen_returns(scored_frame('sh.600000', D(2022, 1, 4)), prices,
                         ScreenConfig(holding_days=1, top_n=1, cost_round_trip=0.0))
    row = row_of(out)
    assert row['entry_price'] == 10.0 and row['exit_price'] == 11.0  # raw, unadjusted
    assert row['entry_adj_factor'] == 1.0 and row['exit_adj_factor'] == 1.1
    expected = 11.0 * 1.1 / (10.0 * 1.0) - 1.0
    assert row['gross_return'] == pytest.approx(expected, rel=1e-12)
    assert row['gross_return'] != pytest.approx(11.0 / 10.0 - 1.0)


def test_minimum_commission_binds_on_small_notional():
    prices = px_frame('sh.600000', weekdays(3), opens=[10.0, 10.0, 10.0])
    cfg = ScreenConfig(holding_days=1, top_n=1, capital=2_000.0)
    out = screen_returns(scored_frame('sh.600000', D(2022, 1, 4)), prices, cfg)
    row = row_of(out)
    assert row['status'] == STATUS_COMPLETED
    assert row['quantity'] == 100
    assert row['entry_notional'] == 1_000.0
    assert row['buy_fee'] == 5.0 and row['sell_fee'] == 5.0  # min fee, pct is 0.1 yuan
    assert row['net_return_pct'] == pytest.approx((995.0 / 1005.0 - 1.0) * 100, rel=1e-12)


def test_zero_affordable_lots_is_insufficient_budget():
    prices = px_frame('sh.600000', weekdays(3), opens=[10.0, 10.0, 10.0])
    cfg = ScreenConfig(holding_days=1, top_n=1, capital=1_000.0)
    row = row_of(screen_returns(scored_frame('sh.600000', D(2022, 1, 4)), prices, cfg))
    assert row['status'] == STATUS_INSUFFICIENT_BUDGET
    assert row['quantity'] == 0 and row['net_return_pct'] is None


def test_entry_min_fee_must_fit_the_event_budget():
    # 100 shares * 10 = 1000 plus the 5 yuan minimum need 1005 of budget
    prices = px_frame('sh.600000', weekdays(3), opens=[10.0, 10.0, 10.0])
    event = scored_frame('sh.600000', D(2022, 1, 4))
    fits = row_of(screen_returns(event, prices,
                                 ScreenConfig(holding_days=1, top_n=1, capital=1_005.0)))
    assert fits['status'] == STATUS_COMPLETED and fits['quantity'] == 100
    short = row_of(screen_returns(event, prices,
                                  ScreenConfig(holding_days=1, top_n=1, capital=1_004.0)))
    assert short['status'] == STATUS_INSUFFICIENT_BUDGET and short['quantity'] == 0


def test_no_separate_stamp_duty_in_all_in_commission():
    prices = px_frame('sh.600000', weekdays(3), opens=[10.0, 10.0, 11.0])
    cfg = ScreenConfig(holding_days=1, top_n=1, capital=2_000.0,
                       commission_pct=0.0, commission_min=0.0, slippage_bps=0.0)
    row = row_of(screen_returns(scored_frame('sh.600000', D(2022, 1, 4)), prices, cfg))
    gross = 11.0 / 10.0 - 1.0
    assert row['buy_fee'] == 0.0 and row['sell_fee'] == 0.0
    assert row['net_return_pct'] == pytest.approx(gross * 100, rel=1e-12)  # no hidden tax


def test_adverse_slippage_reduces_net_return_exactly():
    prices = px_frame('sh.600000', weekdays(3), opens=[10.0, 10.0, 10.0])
    cfg = ScreenConfig(holding_days=1, top_n=1, capital=2_000.0, slippage_bps=100.0)
    row = row_of(screen_returns(scored_frame('sh.600000', D(2022, 1, 4)), prices, cfg))
    # entry at 10*1.01, exit indicative 1010, sale at 1010*0.99
    expected = (1010.0 * 0.99 - 5.0) / (1010.0 + 5.0) - 1.0
    assert row['entry_notional'] == pytest.approx(1010.0, rel=1e-12)
    assert row['net_return_pct'] == pytest.approx(expected * 100, rel=1e-12)


def test_cost_round_trip_override_is_gross_only():
    prices = px_frame('sh.600000', weekdays(3), opens=[10.0, 11.0, 12.0])
    row = row_of(screen_returns(scored_frame('sh.600000', D(2022, 1, 4)), prices,
                                ScreenConfig(holding_days=1, top_n=1,
                                             cost_round_trip=0.01)))
    gross = 12.0 / 11.0 - 1.0
    assert row['net_return_pct'] == pytest.approx((gross - 0.01) * 100, rel=1e-12)
    assert row['quantity'] is None and row['buy_fee'] is None


def test_screen_rejects_bad_inputs():
    prices = px_frame('sh.600000', weekdays(3), opens=[10.0, 11.0, 12.0])
    event = scored_frame('sh.600000', D(2022, 1, 4))
    with pytest.raises(ValueError):
        screen_returns(event, prices.drop('adj_factor'), ScreenConfig(1, 1))
    with pytest.raises(ValueError):
        screen_returns(event, pl.concat([prices, prices.head(1)]), ScreenConfig(1, 1))
    with pytest.raises(ValueError):
        screen_returns(pl.concat([event, event]), prices, ScreenConfig(1, 1))
    with pytest.raises(ValueError):
        ScreenConfig(holding_days=1, top_n=4)
    with pytest.raises(ValueError):
        ScreenConfig(holding_days=1, top_n=1, cost_round_trip=-0.1)
    with pytest.raises(TypeError):
        screen_returns(event, prices, ScreenConfig(1, 1),
                       calendar=[D(2022, 1, 4)])  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# gate (eligible_universe)
# --------------------------------------------------------------------------- #
def test_gate_warmup_requires_full_window():
    dates = weekdays(21)
    gate = eligible_universe(daily_frame('sh.600000', dates))
    assert gate.select('date').to_series().to_list() == dates[19:21]


def test_gate_excludes_st_and_unknown_st_but_keeps_clean():
    dates = weekdays(20)
    daily = pl.concat([
        daily_frame('sh.600000', dates, isST=1.0),
        daily_frame('sz.000001', dates, isST=None),
        daily_frame('sz.000002', dates, isST=0.0),
    ])
    gate = eligible_universe(daily)
    assert gate['symbol'].unique().sort().to_list() == ['sz.000002']
    # null ST is unknown data: it must not be silently treated as clean
    assert gate.height == 1


def test_gate_board_prefixes_and_chinext_opt_in():
    dates = weekdays(20)
    symbols = ['sh.600000', 'sz.000001', 'sh.688001', 'sh.689009',
               'bj.430047', 'bj.830799', 'sz.300001', 'sz.301001']
    daily = pl.concat([daily_frame(symbol, dates) for symbol in symbols])
    default = eligible_universe(daily)
    assert default['symbol'].unique().sort().to_list() == ['sh.600000', 'sz.000001']
    chinext = eligible_universe(daily, allow_chinext=True)
    assert chinext['symbol'].unique().sort().to_list() == [
        'sh.600000', 'sz.000001', 'sz.300001', 'sz.301001']


def test_gate_past_rows_are_not_removed_before_the_median():
    # 10 early rows are ineligible today (low close / suspended) but still
    # occupy the trailing window; dropping them would inflate the median to
    # 60M and wrongly pass.  With them the median is 30M, below the gate.
    dates = weekdays(20)
    low_price = daily_frame('sh.600000', dates, close=3.0, amount=60_000_000.0)
    low_price = low_price.with_columns(
        pl.when(pl.int_range(pl.len()) < 10).then(1.0).otherwise(pl.col('close')).alias('close'),
        pl.when(pl.int_range(pl.len()) < 10).then(0.0).otherwise(pl.col('amount')).alias('amount'),
    )
    suspended = daily_frame('sh.600001', dates, close=3.0, amount=60_000_000.0)
    suspended = suspended.with_columns(
        pl.when(pl.int_range(pl.len()) < 10).then(0.0).otherwise(pl.col('tradestatus')).alias('tradestatus'),
        pl.when(pl.int_range(pl.len()) < 10).then(0.0).otherwise(pl.col('amount')).alias('amount'),
    )
    gate = eligible_universe(pl.concat([low_price, suspended]))
    assert gate.height == 0


def test_gate_is_invariant_to_row_shuffle():
    dates = weekdays(21)
    ordered = daily_frame('sh.600000', dates)
    shuffled = ordered.sample(fraction=1.0, shuffle=True, seed=7)
    left = eligible_universe(ordered).sort('symbol', 'date')
    right = eligible_universe(shuffled).sort('symbol', 'date')
    assert left.to_dicts() == right.to_dicts()


def test_gate_validates_keys_and_values():
    dates = weekdays(20)
    valid = daily_frame('sh.600000', dates)
    with pytest.raises(ValueError):
        eligible_universe(pl.concat([valid, valid.head(1)]))
    with pytest.raises(ValueError):
        eligible_universe(valid.with_columns(pl.lit(None, dtype=pl.String).alias('symbol')))
    with pytest.raises(ValueError):
        eligible_universe(valid.drop('isST'))
    with pytest.raises(ValueError):
        eligible_universe(valid.with_columns(pl.lit(float('inf')).alias('amount')))
    with pytest.raises(ValueError):
        eligible_universe(valid, amount_median_window=0)


# --------------------------------------------------------------------------- #
# ranking
# --------------------------------------------------------------------------- #
def test_daily_rank_picks_deterministic_top_n_with_symbol_ties():
    feat = pl.DataFrame({
        'symbol': ['sh.B', 'sh.A', 'sh.C', 'sh.D'],
        'date': [D(2022, 1, 4)] * 4,
        'score': [3.0, 3.0, 1.0, 2.0],
    }, schema_overrides={'date': pl.Date})
    picks = daily_rank_picks(feat, pl.col('score'), n_per_day=2)
    assert picks['symbol'].to_list() == ['sh.A', 'sh.B']  # tie broken by symbol


def test_daily_rank_picks_supports_negative_scores():
    feat = pl.DataFrame({
        'symbol': ['sh.A', 'sh.B', 'sh.C'],
        'date': [D(2022, 1, 4)] * 3,
        'score': [-1.0, -3.0, -2.0],
    }, schema_overrides={'date': pl.Date})
    picks = daily_rank_picks(feat, pl.col('score'), n_per_day=1)
    assert picks['symbol'].to_list() == ['sh.A']  # least negative wins


def test_daily_rank_picks_excludes_nan_inf_and_null_scores():
    feat = pl.DataFrame({
        'symbol': ['sh.A', 'sh.B', 'sh.C', 'sh.D', 'sh.E'],
        'date': [D(2022, 1, 4)] * 5,
        'score': [2.0, None, float('nan'), float('inf'), float('-inf')],
    }, schema_overrides={'date': pl.Date})
    picks = daily_rank_picks(feat, pl.col('score'), n_per_day=3)
    assert picks['symbol'].to_list() == ['sh.A']


def test_daily_rank_picks_validates_n_per_day():
    feat = pl.DataFrame({
        'symbol': ['sh.A'], 'date': [D(2022, 1, 4)], 'score': [1.0],
    }, schema_overrides={'date': pl.Date})
    for bad in (0, 4):
        with pytest.raises(ValueError):
            daily_rank_picks(feat, pl.col('score'), n_per_day=bad)


def test_status_names_are_stable():
    assert set(STATUS_VALUES) == {
        STATUS_COMPLETED, STATUS_SIGNAL_OUT_OF_RANGE, STATUS_NO_NEXT_SESSION,
        STATUS_HORIZON_OUT_OF_RANGE, STATUS_ENTRY_UNAVAILABLE,
        STATUS_ENTRY_RESTRICTED, STATUS_ENTRY_LIMIT_UP,
        STATUS_EXIT_UNAVAILABLE, STATUS_EXIT_LIMIT_DOWN,
        STATUS_INSUFFICIENT_BUDGET,
    }


# --------------------------------------------------------------------------- #
# historical fee schedule / position budget / limit proxy
# --------------------------------------------------------------------------- #
def test_fee_band_for_picks_last_effective_band():
    bands = (FeeBand(D(2022, 1, 1), 0.0003, 5.0, 0.001),
             FeeBand(D(2022, 6, 1), 0.0002, 5.0, 0.001),
             FeeBand(D(2023, 8, 28), 0.00015, 5.0, 0.0005))
    assert fee_band_for(bands, D(2021, 12, 31)) is bands[0]
    assert fee_band_for(bands, D(2022, 1, 1)) is bands[0]
    assert fee_band_for(bands, D(2022, 5, 31)) is bands[0]
    assert fee_band_for(bands, D(2022, 6, 1)) is bands[1]
    assert fee_band_for(bands, D(2024, 12, 31)) is bands[2]


def test_fee_schedule_rejects_unsorted_and_bad_bands():
    with pytest.raises(ValueError):
        FeeBand(D(2022, 1, 1), -0.001, 5.0)
    with pytest.raises(TypeError):
        FeeBand('2022-01-01', 0.001, 5.0)  # type: ignore[arg-type]
    duplicate = (FeeBand(D(2022, 1, 1), 0.0003, 5.0),
                 FeeBand(D(2022, 1, 1), 0.0002, 5.0))
    with pytest.raises(ValueError):
        ScreenConfig(holding_days=1, top_n=1, fee_schedule=duplicate)


def test_schedule_fees_use_entry_band_buy_and_exit_band_sell():
    # entry 01-05 (band A: 万3, no stamp), exit 01-06 after band B starts
    # (万1 + 千1 stamp on sell): both legs hand-checked on a 10.0->11.0 open.
    dates = weekdays(3)
    prices = px_frame('sh.600000', dates, opens=[10.0, 10.0, 11.0])
    bands = (FeeBand(D(2022, 1, 1), 0.0003, 5.0, 0.0),
             FeeBand(D(2022, 1, 6), 0.0001, 5.0, 0.001))
    cfg = ScreenConfig(holding_days=1, top_n=1, capital=200_000.0,
                       fee_schedule=bands, position_budget=50_000.0)
    row = row_of(screen_returns(scored_frame('sh.600000', D(2022, 1, 4)), prices, cfg))
    assert row['status'] == STATUS_COMPLETED
    assert row['quantity'] == 4900                       # 49,000 notional <= 50k budget
    assert row['entry_notional'] == pytest.approx(49_000.0, rel=1e-12)
    assert row['buy_fee'] == pytest.approx(49_000.0 * 0.0003, rel=1e-12)  # 14.7 > 5 min
    exit_notional = 49_000.0 * 11.0 / 10.0               # 53,900
    commission = max(exit_notional * 0.0001, 5.0)
    assert row['sell_fee'] == pytest.approx(commission + exit_notional * 0.001, rel=1e-12)
    expected = ((exit_notional - row['sell_fee'])
                / (49_000.0 + row['buy_fee']) - 1.0)
    assert row['net_return_pct'] == pytest.approx(expected * 100, rel=1e-9)


def test_position_budget_caps_notional_below_capital_share():
    # capital/top_n would allow 66,666 but the 50k account cap binds first
    dates = weekdays(3)
    prices = px_frame('sh.600000', dates, opens=[10.0, 10.0, 10.0])
    cfg = ScreenConfig(holding_days=1, top_n=3, capital=200_000.0,
                       commission_pct=0.0, commission_min=0.0,
                       position_budget=50_000.0)
    row = row_of(screen_returns(scored_frame('sh.600000', D(2022, 1, 4)), prices, cfg))
    assert row['quantity'] == 5000 and row['entry_notional'] == 50_000.0
    unbudgeted = ScreenConfig(holding_days=1, top_n=3, capital=200_000.0,
                              commission_pct=0.0, commission_min=0.0)
    row2 = row_of(screen_returns(scored_frame('sh.600000', D(2022, 1, 4)), prices, unbudgeted))
    assert row2['quantity'] == 6600                       # 66,600 without the cap


def limit_frame(symbol: str, opens: list[float], precloses: list[float],
                dates: list[date]) -> pl.DataFrame:
    frame = px_frame(symbol, dates, opens=opens)
    return frame.with_columns(pl.Series('preclose', precloses, dtype=pl.Float64))


def test_limit_up_open_blocks_entry_under_proxy():
    # preclose 10.00 -> limit-up 11.00; entry open exactly 11.00 is blocked
    dates = weekdays(3)
    prices = limit_frame('sh.600000', opens=[10.0, 11.0, 11.5],
                         precloses=[9.9, 10.0, 11.0], dates=dates)
    cfg = ScreenConfig(holding_days=1, top_n=1, cost_round_trip=0.0, block_limits=True)
    row = row_of(screen_returns(scored_frame('sh.600000', D(2022, 1, 4)), prices, cfg))
    assert row['status'] == STATUS_ENTRY_LIMIT_UP
    assert row['net_return_pct'] is None
    # one cent below the limit price stays tradable
    prices_ok = limit_frame('sh.600000', opens=[10.0, 10.99, 11.5],
                            precloses=[9.9, 10.0, 10.99], dates=dates)
    row_ok = row_of(screen_returns(scored_frame('sh.600000', D(2022, 1, 4)), prices_ok, cfg))
    assert row_ok['status'] == STATUS_COMPLETED


def test_limit_down_open_blocks_exit_under_proxy():
    # entry fine; exit session opens at limit-down (preclose 11.0 -> 9.90)
    dates = weekdays(3)
    prices = limit_frame('sh.600000', opens=[10.0, 10.0, 9.90],
                         precloses=[10.1, 10.0, 11.0], dates=dates)
    cfg = ScreenConfig(holding_days=1, top_n=1, cost_round_trip=0.0, block_limits=True)
    row = row_of(screen_returns(scored_frame('sh.600000', D(2022, 1, 4)), prices, cfg))
    assert row['status'] == STATUS_EXIT_LIMIT_DOWN
    assert row['net_return_pct'] is None and row['exit_price'] is None


def test_block_limits_requires_preclose_column():
    dates = weekdays(3)
    prices = px_frame('sh.600000', dates, opens=[10.0, 11.0, 12.0])  # no preclose
    cfg = ScreenConfig(holding_days=1, top_n=1, cost_round_trip=0.0, block_limits=True)
    with pytest.raises(ValueError):
        screen_returns(scored_frame('sh.600000', D(2022, 1, 4)), prices, cfg)


def test_gate_excludes_csi_index_codes_and_302_board():
    dates = weekdays(20)
    symbols = ['sz.000905', 'sz.000852', 'sz.302001', 'sh.600000']
    daily = pl.concat([daily_frame(symbol, dates) for symbol in symbols])
    gate = eligible_universe(daily)
    assert gate['symbol'].unique().sort().to_list() == ['sh.600000']
    # indexes stay excludable even with the ChiNext opt-in
    assert eligible_universe(daily, allow_chinext=True)['symbol'].unique().sort().to_list() == [
        'sh.600000', 'sz.302001']
