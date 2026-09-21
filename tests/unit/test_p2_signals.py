"""Round-2 signal definition tests on synthetic frames (contract data only).

Each test pins one preregistered definition's boundary, ranking direction and
null handling.  Synthetic values are never profitability evidence.
"""
from __future__ import annotations

from datetime import date, timedelta

import polars as pl
import pytest

from quant.research.p2_first_screen import signal_candidates  # noqa: E402

D = date


def sessions(count: int, start: date = D(2022, 1, 4)) -> list[date]:
    days: list[date] = []
    day = start
    while len(days) < count:
        if day.weekday() < 5:
            days.append(day)
        day += timedelta(days=1)
    return days


def eligible_frame(n_dates: int) -> pl.DataFrame:
    """Eligible-mask frame: every (symbol, date) passes the gate."""
    dates = sessions(n_dates)
    return pl.DataFrame({
        'symbol': ['sh.600000'] * n_dates,
        'date': dates,
        'amount_med20': [1e8] * n_dates,
    }, schema_overrides={'date': pl.Date})


def daily_frame(**overrides) -> pl.DataFrame:
    """Full daily frame with neutral defaults; override per column.

    Defaults: flat prices (open=close=high=low=10, preclose=10), zero-volume
    and null rolling stats so each test overrides only what its definition
    reads.  ret_*_adj / max250_adj / volatility_20 / vol_mean_20 / turn_mean_20
    / range_mean_20 are provided directly (they come from attach_factors).
    """
    n = overrides.pop('n', 1)
    base = {
        'symbol': ['sh.600000'] * n,
        'date': sessions(n),
        'open': [10.0] * n,
        'preclose': [10.0] * n,
        'close': [10.0] * n,
        'high': [10.0] * n,
        'low': [10.0] * n,
        'pctChg': [0.0] * n,
        'turn': [1.0] * n,
        'volume': [100.0] * n,
        'ret_1_adj': [0.0] * n,
        'ret_5_adj': [0.0] * n,
        'ret_20_adj': [0.0] * n,
        'adj_close': [10.0] * n,
        'max250_adj': [10.0] * n,
        'volatility_20': [0.01] * n,
        'vol_mean_20': [100.0] * n,
        'turn_mean_20': [1.0] * n,
        'range_mean_20': [0.02] * n,
        'z20': [None] * n,
        'z20_prev': [None] * n,
        'sma5_adj': [10.0] * n,
        'sma10_adj': [10.0] * n,
        'sma150_adj': [10.0] * n,
        'sma300_adj': [10.0] * n,
    }
    base.update(overrides)
    return pl.DataFrame(base, schema_overrides={'date': pl.Date})


def test_volconfirm_requires_both_drop_and_volume():
    eligible = eligible_frame(3)
    daily = daily_frame(n=3, ret_5_adj=[-0.09, -0.09, -0.07],
                        volume=[200.0, 100.0, 200.0], vol_mean_20=[100.0] * 3)
    out = signal_candidates(daily, eligible, 'R2-volconfirm-reversal')
    # row 0: deep drop + volume ok; row 1: drop but no volume; row 2: volume but shallow
    assert out['date'].to_list() == [sessions(3)[0]]
    assert out['score'][0] == 0.09  # score = -ret_5, deepest ranked first by caller


def two_symbol_daily(column: str, values_a: list, values_b: list, **shared) -> pl.DataFrame:
    """Two symbols per date so the daily median split is non-degenerate."""
    n = len(values_a)
    frame_a = daily_frame(n=n, **{column: values_a}, **shared)
    frame_b = daily_frame(n=n, **{column: values_b}, **shared)
    frame_b = frame_b.with_columns(pl.lit('sh.600001').alias('symbol'))
    return pl.concat([frame_a, frame_b])


def two_symbol_eligible(n: int) -> pl.DataFrame:
    dates = sessions(n)
    return pl.DataFrame({
        'symbol': ['sh.600000'] * n + ['sh.600001'] * n,
        'date': dates + dates,
        'amount_med20': [1e8] * (2 * n),
    }, schema_overrides={'date': pl.Date})


def test_lowvol_dip_needs_median_split_and_drop():
    eligible = two_symbol_eligible(3)
    # A calm (0.005 <= two-symbol median 0.0125) with deep/shallow dips;
    # B volatile (0.02 > median) with a deep dip that must NOT signal.
    daily = two_symbol_daily(
        'volatility_20', [0.005, 0.005, 0.005], [0.02, 0.02, 0.02],
        ret_5_adj=[-0.06, -0.03, -0.01])
    out = signal_candidates(daily, eligible, 'R2-lowvol-dip')
    assert out['date'].to_list() == [sessions(3)[0]]
    assert out['symbol'].to_list() == ['sh.600000']


def test_near52w_requires_proximity_and_down_day():
    eligible = eligible_frame(3)
    daily = daily_frame(n=3, adj_close=[9.5, 9.5, 8.0], max250_adj=[10.0] * 3,
                        ret_1_adj=[-0.01, 0.01, -0.01])
    out = signal_candidates(daily, eligible, 'R2-near52w-dip')
    assert out['date'].to_list() == [sessions(3)[0]]
    assert out['score'][0] == 0.95  # proximity itself is the ranking score


def test_turnover_capitulation_thresholds():
    eligible = eligible_frame(3)
    daily = daily_frame(n=3, turn=[3.0, 3.0, 1.5], turn_mean_20=[1.0] * 3,
                        pctChg=[-6.0, -4.0, -6.0])
    out = signal_candidates(daily, eligible, 'R2-turnover-capitulation')
    # row 0: 3x turnover + -6%; row 1: drop too small; row 2: turnover too low
    assert out['date'].to_list() == [sessions(3)[0]]
    assert out['score'][0] == 3.0


def test_gapdown_recovery_requires_gap_and_green_close():
    eligible = eligible_frame(3)
    daily = daily_frame(n=3, open=[9.5, 9.5, 10.5], preclose=[10.0] * 3,
                        close=[9.8, 9.4, 10.8])
    out = signal_candidates(daily, eligible, 'R2-gapdown-recovery')
    # row 0: -5% gap, close 9.8 > open 9.5; row 1: gap but red close; row 2: gap up
    assert out['date'].to_list() == [sessions(3)[0]]
    assert abs(out['score'][0] - (9.8 - 9.5) / 9.5) < 1e-12


def test_squeeze_breakout_needs_compression_and_break():
    eligible = two_symbol_eligible(3)
    # A compressed (0.01 <= median 0.02) with/without a break; B wide (0.03)
    # with a break that must NOT signal.
    daily = two_symbol_daily(
        'range_mean_20', [0.01, 0.01, 0.01], [0.03, 0.03, 0.03],
        pctChg=[4.0, 2.0, 2.0])
    out = signal_candidates(daily, eligible, 'R2-squeeze-breakout')
    assert out['date'].to_list() == [sessions(3)[0]]
    assert out['symbol'].to_list() == ['sh.600000']
    assert out['score'][0] == 4.0


def test_null_conditions_never_signal():
    eligible = eligible_frame(2)
    daily = daily_frame(n=2, ret_5_adj=[None, -0.09], volume=[200.0, None],
                        vol_mean_20=[100.0, 100.0])
    out = signal_candidates(daily, eligible, 'R2-volconfirm-reversal')
    assert out.height == 0  # null drop or null volume excludes, never passes


def test_unknown_signal_set_raises():
    eligible = eligible_frame(1)
    with pytest.raises(ValueError):
        signal_candidates(daily_frame(), eligible, 'R3-not-registered')


# --------------------------------------------------------------------------- #
# round 3: price-volume mean reversion
# --------------------------------------------------------------------------- #
def test_mr_z_oversold_threshold_and_score():
    eligible = eligible_frame(3)
    daily = daily_frame(n=3, z20=[-1.6, -1.4, -2.0])
    out = signal_candidates(daily, eligible, 'R3-mr-z-oversold')
    # row 1 (-1.4) above threshold; rows 0 and 2 signal, deepest ranked first by caller
    assert out['date'].to_list() == [sessions(3)[0], sessions(3)[2]]
    assert out['score'].to_list() == [1.6, 2.0]


def test_mr_z_oversold_excludes_infinite_z():
    # zero std upstream yields null z; a raw inf injected here must never signal
    eligible = eligible_frame(2)
    daily = daily_frame(n=2, z20=[-float('inf'), -1.5])
    out = signal_candidates(daily, eligible, 'R3-mr-z-oversold')
    assert out['date'].to_list() == [sessions(2)[1]]


def test_mr_shrink_dip_requires_low_volume_ratio():
    eligible = eligible_frame(3)
    daily = daily_frame(n=3, ret_5_adj=[-0.06, -0.06, -0.03],
                        volume=[50.0, 100.0, 50.0], vol_mean_20=[100.0] * 3)
    out = signal_candidates(daily, eligible, 'R3-mr-shrink-dip')
    # row 0: drop + 0.5x volume; row 1: full volume; row 2: shrink but shallow
    assert out['date'].to_list() == [sessions(3)[0]]


def test_mr_z_shrink_combo_needs_both():
    eligible = eligible_frame(3)
    daily = daily_frame(n=3, z20=[-1.2, -0.8, -1.2], volume=[70.0, 70.0, 90.0],
                        vol_mean_20=[100.0] * 3)
    out = signal_candidates(daily, eligible, 'R3-mr-z-shrink-combo')
    # row 0: z + shrink; row 1: shrink but z above -1.0; row 2: z but volume 0.9x
    assert out['date'].to_list() == [sessions(3)[0]]


def test_mr_z_confirmed_uses_prior_day_deviation_and_up_close():
    eligible = eligible_frame(3)
    daily = daily_frame(n=3, z20_prev=[-1.6, -1.6, -0.5],
                        ret_1_adj=[0.01, -0.01, 0.02])
    out = signal_candidates(daily, eligible, 'R3-mr-z-confirmed')
    # row 0: prior oversold + up day; row 1: down day; row 2: not oversold
    assert out['date'].to_list() == [sessions(3)[0]]
    assert out['score'][0] == 0.01


# --------------------------------------------------------------------------- #
# round 5: weekly-trend / daily-dip (user-specified 2026-09-17)
# --------------------------------------------------------------------------- #
def trend_frame(adj: list[float], sma5: list[float], sma10: list[float],
                sma150: list[float], sma300: list[float]) -> pl.DataFrame:
    return daily_frame(
        n=len(adj), adj_close=adj, sma5_adj=sma5, sma10_adj=sma10,
        sma150_adj=sma150, sma300_adj=sma300)


def test_trend_dip_30w_5d_requires_above_long_below_short():
    eligible = eligible_frame(3)
    daily = trend_frame(
        adj=[10.0, 10.0, 10.0],
        sma5=[10.5, 9.5, 10.5],      # row0 below (dip), row1 above, row2 above
        sma10=[10.6, 10.6, 10.6],
        sma150=[9.0, 9.0, 11.0],     # row2 below the long line -> excluded
        sma300=[8.0] * 3)
    out = signal_candidates(daily, eligible, 'R5-trend-dip-30w-5d')
    assert out['date'].to_list() == [sessions(3)[0]]
    assert out['score'][0] == pytest.approx(10.5 / 10.0 - 1.0)


def test_trend_dip_60w_10d_uses_the_300_session_line():
    eligible = eligible_frame(3)
    daily = trend_frame(
        adj=[10.0, 10.0, 10.0],
        sma5=[10.4] * 3,
        sma10=[10.7, 9.5, 10.7],
        sma150=[9.0] * 3,
        sma300=[9.0, 9.0, 11.5])    # row2 below the 60w line -> excluded
    out = signal_candidates(daily, eligible, 'R5-trend-dip-60w-10d')
    assert out['date'].to_list() == [sessions(3)[0]]
    assert out['score'][0] == pytest.approx(10.7 / 10.0 - 1.0)
