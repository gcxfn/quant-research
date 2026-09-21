"""P0 contract tests: vectorbt and Backtrader must agree order by order and day by day.

The P0 acceptance requirement is that, under identical simplified assumptions,
the two backtest adapters agree on every order, every daily cash balance, every
daily position and every marked-close equity value -- not merely on total return.
Every scenario below is run through both adapters and compared row by row.

Scope of these tests (P0, deliberately narrow):

* whole-share signed quantity orders supplied externally; no strategy logic;
* execution at the next session open after a decision known at a previous close;
* commissions as a fixed fraction of traded notional, identical in both frameworks;
* ample cash, no borrowing rules, no T+1, no price limits, no suspensions, no
  lot/odd-lot rounding, no A-share fee schedule, no corporate actions.

This is therefore **not** a full A-share broker adaptation test. Those rules
belong to P1/P3 and are out of scope here.
"""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
import pytest

from quant.backtest import (  # noqa: E402
    BacktestConfig,
    Order,
    PricePanel,
    assert_parity,
    compare_results,
    run_backtrader,
    run_vectorbt,
)

FRAMEWORKS = ("vectorbt", "backtrader")

# ---------------------------------------------------------------------------
# Hand-calculated fixture
# ---------------------------------------------------------------------------
# Four consecutive sessions, two symbols, commission 0.1% = 0.001, cash 1,000,000.
#
#   session      AAA open  AAA close    BBB open  BBB close
#   2024-01-08      10.00      10.20       20.00      19.80
#   2024-01-09      10.30      10.50       19.70      20.10
#   2024-01-10      10.40      10.10       20.20      20.40
#   2024-01-11      10.00      10.30       20.50      20.30
#
# Orders (decision made at that session's close, executed next session's open):
#   +1000 AAA decided 01-08 -> fills 01-09 open 10.30, notional 10,300, fee 10.30
#    +500 BBB decided 01-09 -> fills 01-10 open 20.20, notional 10,100, fee 10.10
#    -400 AAA decided 01-10 -> fills 01-11 open 10.00, notional  4,000, fee  4.00
#    -200 BBB decided 01-10 -> fills 01-11 open 20.50, notional  4,100, fee  4.10
#
# Ledger by hand:
#   01-08  cash 1,000,000.00  positions value       0.00  equity 1,000,000.00
#   01-09  cash   989,689.70  positions value  10,500.00  equity 1,000,189.70
#   01-10  cash   979,579.60  positions value  20,300.00  equity   999,879.60
#   01-11  cash   987,671.50  positions value  12,270.00  equity   999,941.50
#   total fees 28.50 = 10.30 + 10.10 + 4.00 + 4.10
FIXTURE_SESSIONS = ("2024-01-08", "2024-01-09", "2024-01-10", "2024-01-11")
FIXTURE_OPEN = {
    "AAA": [10.00, 10.30, 10.40, 10.00],
    "BBB": [20.00, 19.70, 20.20, 20.50],
}
FIXTURE_CLOSE = {
    "AAA": [10.20, 10.50, 10.10, 10.30],
    "BBB": [19.80, 20.10, 20.40, 20.30],
}
FIXTURE_ORDERS = (
    Order(dt.date(2024, 1, 8), "AAA", 1000),
    Order(dt.date(2024, 1, 9), "BBB", 500),
    Order(dt.date(2024, 1, 10), "AAA", -400),
    Order(dt.date(2024, 1, 10), "BBB", -200),
)
FIXTURE_EXPECTED_FILLS = [
    {"date": dt.date(2024, 1, 9), "symbol": "AAA", "quantity": 1000, "price": 10.30, "fee": 10.30},
    {"date": dt.date(2024, 1, 10), "symbol": "BBB", "quantity": 500, "price": 20.20, "fee": 10.10},
    {"date": dt.date(2024, 1, 11), "symbol": "AAA", "quantity": -400, "price": 10.00, "fee": 4.00},
    {"date": dt.date(2024, 1, 11), "symbol": "BBB", "quantity": -200, "price": 20.50, "fee": 4.10},
]
FIXTURE_EXPECTED_CASH = [1_000_000.00, 989_689.70, 979_579.60, 987_671.50]
FIXTURE_EXPECTED_POSITIONS = [[0, 0], [1000, 0], [1000, 500], [600, 300]]
FIXTURE_EXPECTED_POSITIONS_VALUE = [0.00, 10_500.00, 20_300.00, 12_270.00]
FIXTURE_EXPECTED_EQUITY = [1_000_000.00, 1_000_189.70, 999_879.60, 999_941.50]
FIXTURE_INITIAL_CASH = 1_000_000.0
FIXTURE_COMMISSION = 0.001


def make_panel(sessions, open_map, close_map) -> PricePanel:
    index = pd.DatetimeIndex(pd.to_datetime(list(sessions)))
    return PricePanel(
        open=pd.DataFrame(open_map, index=index),
        close=pd.DataFrame(close_map, index=index),
    )


def hand_fixture_panel() -> PricePanel:
    return make_panel(FIXTURE_SESSIONS, FIXTURE_OPEN, FIXTURE_CLOSE)


def hand_fixture_config() -> BacktestConfig:
    return BacktestConfig(initial_cash=FIXTURE_INITIAL_CASH, commission_pct=FIXTURE_COMMISSION)


def run_both(panel, orders, config):
    return {
        "vectorbt": run_vectorbt(panel, orders, config),
        "backtrader": run_backtrader(panel, orders, config),
    }


# ---------------------------------------------------------------------------
# Hand-calculated ledger
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("framework", FRAMEWORKS)
def test_hand_calculated_fixture_matches_manual_ledger(framework):
    panel = hand_fixture_panel()
    result = run_both(panel, FIXTURE_ORDERS, hand_fixture_config())[framework]

    expected_fills = pd.DataFrame(
        {
            "date": pd.Series([row["date"] for row in FIXTURE_EXPECTED_FILLS], dtype="object"),
            "symbol": pd.Series([row["symbol"] for row in FIXTURE_EXPECTED_FILLS], dtype="object"),
            "quantity": pd.Series([row["quantity"] for row in FIXTURE_EXPECTED_FILLS], dtype="int64"),
            "price": pd.Series([row["price"] for row in FIXTURE_EXPECTED_FILLS], dtype="float64"),
            "fee": pd.Series([row["fee"] for row in FIXTURE_EXPECTED_FILLS], dtype="float64"),
        }
    )
    pd.testing.assert_frame_equal(result.fills, expected_fills)
    assert result.rejected_orders.empty

    np.testing.assert_allclose(result.cash.to_numpy(), FIXTURE_EXPECTED_CASH, rtol=0, atol=1e-9)
    np.testing.assert_array_equal(result.positions.to_numpy(), np.array(FIXTURE_EXPECTED_POSITIONS))
    np.testing.assert_allclose(
        result.equity["positions_value"].to_numpy(), FIXTURE_EXPECTED_POSITIONS_VALUE, rtol=0, atol=1e-9
    )
    np.testing.assert_allclose(result.equity["equity"].to_numpy(), FIXTURE_EXPECTED_EQUITY, rtol=0, atol=1e-9)
    np.testing.assert_allclose(result.equity["cash"].to_numpy(), result.cash.to_numpy(), rtol=0, atol=0)

    assert result.total_fees == pytest.approx(28.50, abs=1e-9)
    assert result.final_equity == pytest.approx(999_941.50, abs=1e-9)
    assert list(result.positions.columns) == ["AAA", "BBB"]
    assert result.cash.index.equals(panel.index)


@pytest.mark.parametrize("framework", FRAMEWORKS)
def test_hand_calculated_fixture_conserves_cash(framework):
    result = run_both(hand_fixture_panel(), FIXTURE_ORDERS, hand_fixture_config())[framework]

    signed_notional = float((result.fills["quantity"] * result.fills["price"]).sum())
    expected_final_cash = FIXTURE_INITIAL_CASH - signed_notional - result.total_fees
    assert result.cash.iloc[-1] == pytest.approx(expected_final_cash, abs=1e-9)
    # Accounting identity holds on every session, not just the last one.
    identity = result.equity["cash"] + result.equity["positions_value"] - result.equity["equity"]
    np.testing.assert_allclose(identity.to_numpy(), np.zeros(len(identity)), rtol=0, atol=1e-6)


def test_hand_calculated_fixture_cross_framework_parity_row_by_row():
    results = run_both(hand_fixture_panel(), FIXTURE_ORDERS, hand_fixture_config())
    report = assert_parity(results["vectorbt"], results["backtrader"])
    assert report.max_abs_diff["cash_value"] == pytest.approx(0.0, abs=1e-9)
    assert report.max_abs_diff["equity_equity"] == pytest.approx(0.0, abs=1e-9)
    assert report.max_abs_diff["fills_fee"] == pytest.approx(0.0, abs=1e-9)
    np.testing.assert_array_equal(
        results["vectorbt"].positions.to_numpy(), results["backtrader"].positions.to_numpy()
    )


# ---------------------------------------------------------------------------
# Next-open timing
# ---------------------------------------------------------------------------
def test_next_open_timing_and_no_lookahead():
    """A decision must never be filled at a price observable at decision time."""

    panel = hand_fixture_panel()
    orders = FIXTURE_ORDERS
    decision_by_fill = {
        (dt.date(2024, 1, 9), "AAA"): dt.date(2024, 1, 8),
        (dt.date(2024, 1, 10), "BBB"): dt.date(2024, 1, 9),
        (dt.date(2024, 1, 11), "AAA"): dt.date(2024, 1, 10),
        (dt.date(2024, 1, 11), "BBB"): dt.date(2024, 1, 10),
    }
    for framework, result in run_both(panel, orders, hand_fixture_config()).items():
        for row in result.fills.itertuples(index=False):
            decision = decision_by_fill[(row.date, row.symbol)]
            assert row.date > decision, f"{framework}: fill on the decision session"
            sessions = panel.dates
            assert row.date == sessions[sessions.index(decision) + 1], f"{framework}: not the next session"
            assert row.price == pytest.approx(panel.open.loc[pd.Timestamp(row.date), row.symbol])
            assert row.price != pytest.approx(panel.close.loc[pd.Timestamp(decision), row.symbol])
            assert row.price != pytest.approx(panel.open.loc[pd.Timestamp(decision), row.symbol])
        # Equity on the decision session must not include the future fill.
        assert result.positions.loc[pd.Timestamp("2024-01-08")].sum() == 0


def test_decision_on_non_session_date_executes_at_next_available_open():
    """A decision dated on a session missing from the panel waits for the next one."""

    sessions = ("2024-01-08", "2024-01-09", "2024-01-11", "2024-01-12")
    panel = make_panel(
        sessions,
        {"AAA": [10.00, 10.30, 11.00, 11.40]},
        {"AAA": [10.20, 10.50, 11.20, 11.60]},
    )
    orders = [Order(dt.date(2024, 1, 10), "AAA", 100)]  # 01-10 is absent from the panel
    for framework, result in run_both(panel, orders, BacktestConfig(initial_cash=100_000.0)).items():
        assert len(result.fills) == 1, framework
        fill = result.fills.iloc[0]
        assert fill["date"] == dt.date(2024, 1, 11)
        assert fill["price"] == pytest.approx(11.00)
        assert result.positions["AAA"].tolist() == [0, 0, 100, 100]


def test_datetime_decision_is_normalized_to_its_date():
    panel = hand_fixture_panel()
    orders = [Order(dt.datetime(2024, 1, 8, 15, 30), "AAA", 10)]
    for framework, result in run_both(panel, orders, BacktestConfig(initial_cash=100_000.0)).items():
        assert len(result.fills) == 1, framework
        assert result.fills.iloc[0]["date"] == dt.date(2024, 1, 9)


def test_equity_is_marked_at_close_not_open():
    sessions = ("2024-01-08", "2024-01-09")
    panel = make_panel(sessions, {"AAA": [10.00, 10.00]}, {"AAA": [10.00, 99.00]})
    orders = [Order(dt.date(2024, 1, 8), "AAA", 10)]
    for framework, result in run_both(panel, orders, BacktestConfig(initial_cash=10_000.0)).items():
        assert result.positions.iloc[-1]["AAA"] == 10, framework
        assert result.equity.iloc[-1]["positions_value"] == pytest.approx(990.0), framework
        assert result.equity.iloc[-1]["positions_value"] != pytest.approx(100.0), framework
        assert result.equity.iloc[-1]["equity"] == pytest.approx(result.cash.iloc[-1] + 990.0), framework


# ---------------------------------------------------------------------------
# Multiple symbols and position sign
# ---------------------------------------------------------------------------
def test_multiple_symbols_are_tracked_independently_and_agree():
    sessions = pd.bdate_range("2024-03-04", periods=6)
    rng = np.random.default_rng(7)
    symbols = [f"S{i}" for i in range(5)]
    opens = {s: np.round(10.0 + 3.0 * rng.random(len(sessions)) + i, 2) for i, s in enumerate(symbols)}
    closes = {s: np.round(opens[s] * (1.0 + 0.02 * (rng.random(len(sessions)) - 0.5)), 2) for s in symbols}
    panel = make_panel([d.date().isoformat() for d in sessions], opens, closes)

    orders = [
        Order(sessions[0].date(), "S0", 100),
        Order(sessions[0].date(), "S1", -50),
        Order(sessions[1].date(), "S2", 300),
        Order(sessions[2].date(), "S3", 200),
        Order(sessions[2].date(), "S0", -40),
        Order(sessions[3].date(), "S4", 150),
        Order(sessions[3].date(), "S1", 25),
    ]
    config = BacktestConfig(initial_cash=5_000_000.0, commission_pct=0.0008)
    results = run_both(panel, orders, config)
    assert_parity(results["vectorbt"], results["backtrader"])

    expected_final = {"S0": 60, "S1": -25, "S2": 300, "S3": 200, "S4": 150}
    for framework, result in results.items():
        assert list(result.positions.columns) == symbols, framework
        assert result.positions.iloc[-1].to_dict() == expected_final, framework
        assert len(result.fills) == len(orders), framework
        assert result.rejected_orders.empty, framework


def test_sell_of_unheld_shares_produces_signed_position_in_both_frameworks():
    sessions = ("2024-01-08", "2024-01-09", "2024-01-10")
    panel = make_panel(sessions, {"AAA": [10.0, 11.0, 12.0]}, {"AAA": [10.5, 11.5, 12.5]})
    orders = [Order(dt.date(2024, 1, 8), "AAA", -300)]
    results = run_both(panel, orders, BacktestConfig(initial_cash=100_000.0, commission_pct=0.001))
    assert_parity(results["vectorbt"], results["backtrader"])
    for framework, result in results.items():
        assert result.positions["AAA"].tolist() == [0, -300, -300], framework
        assert result.fills.iloc[0]["quantity"] == -300, framework
        assert result.fills.iloc[0]["fee"] == pytest.approx(300 * 11.0 * 0.001), framework
        assert result.equity.iloc[-1]["positions_value"] == pytest.approx(-300 * 12.5), framework


def test_round_trip_returns_to_flat_with_exact_cash_after_fees():
    sessions = ("2024-01-08", "2024-01-09", "2024-01-10")
    panel = make_panel(sessions, {"AAA": [10.0, 10.0, 10.0]}, {"AAA": [10.0, 11.0, 12.0]})
    orders = [Order(dt.date(2024, 1, 8), "AAA", 100), Order(dt.date(2024, 1, 9), "AAA", -100)]
    config = BacktestConfig(initial_cash=100_000.0, commission_pct=0.001)
    results = run_both(panel, orders, config)
    assert_parity(results["vectorbt"], results["backtrader"])
    for framework, result in results.items():
        assert result.positions.iloc[-1]["AAA"] == 0, framework
        # Bought and sold at the same price, so the whole loss is commission.
        assert result.total_fees == pytest.approx(100 * 10.0 * 0.001 * 2), framework
        assert result.final_equity == pytest.approx(100_000.0 - result.total_fees, abs=1e-9), framework
        assert result.equity.iloc[-1]["positions_value"] == 0.0, framework


# ---------------------------------------------------------------------------
# Commissions
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("rate", [0.0, 0.0003, 0.001, 0.0025])
def test_commission_is_a_fraction_of_notional_and_matches_in_both_frameworks(rate):
    panel = hand_fixture_panel()
    config = BacktestConfig(initial_cash=FIXTURE_INITIAL_CASH, commission_pct=rate)
    results = run_both(panel, FIXTURE_ORDERS, config)
    assert_parity(results["vectorbt"], results["backtrader"])

    for framework, result in results.items():
        expected = (result.fills["quantity"].abs() * result.fills["price"] * rate).to_numpy()
        np.testing.assert_allclose(result.fills["fee"].to_numpy(), expected, rtol=1e-12, atol=1e-12)
        assert result.commission_pct == rate, framework
        expected_cash = FIXTURE_INITIAL_CASH - float(
            (result.fills["quantity"] * result.fills["price"]).sum()
        ) - float(result.fills["fee"].sum())
        assert result.cash.iloc[-1] == pytest.approx(expected_cash, abs=1e-9), framework


def test_zero_commission_produces_zero_fees_and_full_notional_cash():
    panel = hand_fixture_panel()
    config = BacktestConfig(initial_cash=FIXTURE_INITIAL_CASH, commission_pct=0.0)
    for framework, result in run_both(panel, FIXTURE_ORDERS, config).items():
        assert (result.fills["fee"] == 0.0).all(), framework
        assert result.cash.iloc[-1] == pytest.approx(FIXTURE_INITIAL_CASH - 12_300.0, abs=1e-9), framework


# ---------------------------------------------------------------------------
# Order netting and rejections
# ---------------------------------------------------------------------------
def test_opposite_orders_on_same_session_are_netted_into_one_fill():
    """Netting keeps fee parity: two Backtrader fills would double the commission."""

    sessions = ("2024-01-08", "2024-01-09", "2024-01-10")
    panel = make_panel(sessions, {"AAA": [10.0, 10.0, 10.0]}, {"AAA": [10.0, 11.0, 11.0]})
    orders = [
        Order(dt.date(2024, 1, 8), "AAA", 120),
        Order(dt.date(2024, 1, 8), "AAA", 30),
        Order(dt.date(2024, 1, 8), "AAA", -50),
    ]
    config = BacktestConfig(initial_cash=100_000.0, commission_pct=0.001)
    results = run_both(panel, orders, config)
    assert_parity(results["vectorbt"], results["backtrader"])
    for framework, result in results.items():
        assert len(result.fills) == 1, framework
        assert result.fills.iloc[0]["quantity"] == 100, framework
        # Exactly one commission on the net 100 shares, not one per input order.
        assert result.fills.iloc[0]["fee"] == pytest.approx(100 * 10.0 * 0.001), framework
        assert result.rejected_orders.empty, framework
        assert len(result.scheduled_orders) == 1, framework
        assert list(result.scheduled_orders.iloc[0]["decision_dates"]) == [dt.date(2024, 1, 8)]


def test_opposite_orders_netting_to_zero_are_rejected_not_silently_dropped():
    sessions = ("2024-01-08", "2024-01-09")
    panel = make_panel(sessions, {"AAA": [10.0, 10.0]}, {"AAA": [10.0, 10.0]})
    orders = [Order(dt.date(2024, 1, 8), "AAA", 40), Order(dt.date(2024, 1, 8), "AAA", -40)]
    results = run_both(panel, orders, BacktestConfig(initial_cash=100_000.0))
    assert_parity(results["vectorbt"], results["backtrader"])
    for framework, result in results.items():
        assert result.fills.empty, framework
        assert result.scheduled_orders.empty, framework
        assert result.rejected_orders["reason"].tolist() == ["net_zero_quantity", "net_zero_quantity"], framework
        assert result.rejected_orders["quantity"].tolist() == [-40, 40] or (
            result.rejected_orders["quantity"].tolist() == [40, -40]
        ), framework
        np.testing.assert_allclose(result.cash.to_numpy(), [100_000.0, 100_000.0]), framework


def test_structural_rejections_are_identical_in_both_frameworks():
    panel = hand_fixture_panel()
    orders = [
        Order(dt.date(2024, 1, 8), "MISSING", 100),  # unknown symbol
        Order(dt.date(2024, 1, 8), "AAA", 0),  # zero quantity
        Order(dt.date(2024, 1, 11), "AAA", 100),  # decision on the last session
        Order(dt.date(2024, 1, 5), "AAA", 100),  # decision before the first session
    ]
    results = run_both(panel, orders, BacktestConfig(initial_cash=100_000.0))
    assert_parity(results["vectorbt"], results["backtrader"])

    expected = sorted(
        [
            (dt.date(2024, 1, 8), "MISSING", 100, "unknown_symbol"),
            (dt.date(2024, 1, 8), "AAA", 0, "zero_quantity"),
            (dt.date(2024, 1, 11), "AAA", 100, "no_next_session"),
            (dt.date(2024, 1, 5), "AAA", 100, "decision_before_first_session"),
        ]
    )
    for framework, result in results.items():
        assert result.fills.empty, framework
        actual = sorted(map(tuple, result.rejected_orders.itertuples(index=False, name=None)))
        assert actual == expected, framework
        assert result.cash.iloc[-1] == pytest.approx(100_000.0), framework
        assert result.equity["equity"].nunique() == 1, framework


def test_order_and_config_validation():
    with pytest.raises(ValueError):
        Order(dt.date(2024, 1, 8), "", 10)
    with pytest.raises(TypeError):
        Order(dt.date(2024, 1, 8), "AAA", 10.5)
    with pytest.raises(TypeError):
        Order(dt.date(2024, 1, 8), "AAA", True)
    with pytest.raises(ValueError):
        BacktestConfig(initial_cash=0.0)
    with pytest.raises(ValueError):
        BacktestConfig(commission_pct=-0.001)


def test_price_panel_validation():
    index = pd.to_datetime(["2024-01-08", "2024-01-09"])
    good_open = pd.DataFrame({"AAA": [10.0, 10.0]}, index=index)
    good_close = pd.DataFrame({"AAA": [10.0, 10.0]}, index=index)

    with pytest.raises(ValueError):
        PricePanel(open=good_open, close=good_close.rename(columns={"AAA": "BBB"}))
    with pytest.raises(ValueError):
        PricePanel(open=good_open, close=pd.DataFrame({"AAA": [10.0]}, index=index[:1]))
    with pytest.raises(ValueError):
        PricePanel(open=good_open, close=pd.DataFrame({"AAA": [10.0, np.nan]}, index=index))
    with pytest.raises(ValueError):
        PricePanel(open=good_open, close=pd.DataFrame({"AAA": [10.0, 0.0]}, index=index))
    with pytest.raises(ValueError):
        PricePanel(open=good_open, close=pd.DataFrame({"AAA": [10.0, 10.0]}, index=index[::-1]))
    with pytest.raises(ValueError):
        PricePanel(
            open=pd.DataFrame({"AAA": [10.0, 10.0]}, index=pd.to_datetime(["2024-01-08", "2024-01-08"])),
            close=pd.DataFrame({"AAA": [10.0, 10.0]}, index=pd.to_datetime(["2024-01-08", "2024-01-08"])),
        )


# ---------------------------------------------------------------------------
# Planner edge cases
# ---------------------------------------------------------------------------
def test_empty_order_plan_produces_a_flat_account_in_both_frameworks():
    panel = hand_fixture_panel()
    results = run_both(panel, [], hand_fixture_config())
    assert_parity(results["vectorbt"], results["backtrader"])
    for framework, result in results.items():
        assert result.fills.empty, framework
        assert result.rejected_orders.empty, framework
        assert result.scheduled_orders.empty, framework
        np.testing.assert_array_equal(result.positions.to_numpy(), np.zeros((4, 2), dtype="int64"))
        np.testing.assert_allclose(result.cash.to_numpy(), np.full(4, FIXTURE_INITIAL_CASH)), framework
        np.testing.assert_allclose(result.equity["equity"].to_numpy(), np.full(4, FIXTURE_INITIAL_CASH)), framework


def test_backtrader_captures_broker_rejection_when_cash_is_not_ample():
    """Ample cash is a P0 assumption; if violated the rejection must be reported.

    This is intentionally not a parity test: vectorbt has no cash-constraint
    rejection, so the two frameworks only agree while the ample-cash assumption
    holds. The test pins the documented limitation instead of hiding it.
    """

    panel = hand_fixture_panel()
    orders = [Order(dt.date(2024, 1, 8), "AAA", 1000)]
    config = BacktestConfig(initial_cash=100.0, commission_pct=0.0)
    result = run_backtrader(panel, orders, config)
    assert result.fills.empty
    assert len(result.rejected_orders) == 1
    reason = result.rejected_orders.iloc[0]["reason"]
    assert reason.startswith("broker_"), reason
    assert result.cash.iloc[-1] == pytest.approx(100.0)


# ---------------------------------------------------------------------------
# Scale and determinism
# ---------------------------------------------------------------------------
def test_seeded_multi_symbol_scenario_agrees_on_every_order_and_session():
    rng = np.random.default_rng(20240101)
    sessions = pd.bdate_range("2024-02-01", periods=40)
    symbols = ["AAA", "BBB", "CCC", "DDD"]
    opens = {}
    closes = {}
    for i, symbol in enumerate(symbols):
        base = 8.0 + 12.0 * i
        drift = np.cumsum(rng.normal(0.0, 0.35, len(sessions)))
        opens[symbol] = np.round(base + drift, 2)
        closes[symbol] = np.round(base + drift + rng.normal(0.0, 0.15, len(sessions)), 2)
    panel = make_panel([d.date().isoformat() for d in sessions], opens, closes)

    orders = []
    used: set[tuple[dt.date, str]] = set()
    for _ in range(60):
        decision = sessions[int(rng.integers(0, len(sessions) - 1))].date()
        symbol = symbols[int(rng.integers(0, len(symbols)))]
        quantity = int(rng.integers(-8, 9)) * 100
        # One order per (decision, symbol) keeps the expected fill count exact and
        # makes this a test of parity rather than of same-session netting.
        if quantity == 0 or (decision, symbol) in used:
            continue
        used.add((decision, symbol))
        orders.append(Order(decision, symbol, quantity))
    assert len(orders) >= 30

    config = BacktestConfig(initial_cash=50_000_000.0, commission_pct=0.0006)
    results = run_both(panel, orders, config)
    report = assert_parity(results["vectorbt"], results["backtrader"])

    # Bit-identical expectations are wrong for float accumulation over ~40
    # sessions and 10^8 cash; agreement must hold far below one cent instead.
    assert report.max_abs_diff["cash_value"] < 1e-4
    assert report.max_abs_diff["equity_equity"] < 1e-4
    assert report.max_abs_diff["fills_fee"] < 1e-9
    assert report.max_abs_diff["positions_AAA"] == 0.0
    assert report.max_abs_diff["positions_DDD"] == 0.0
    assert len(results["backtrader"].fills) == len(orders)
    assert results["backtrader"].rejected_orders.empty
    assert results["vectorbt"].scheduled_orders.equals(results["backtrader"].scheduled_orders)

    # Determinism: the same inputs reproduce byte-identical daily accounts.
    again = run_vectorbt(panel, orders, config)
    pd.testing.assert_frame_equal(again.equity, results["vectorbt"].equity)
    pd.testing.assert_frame_equal(again.fills, results["vectorbt"].fills)


def test_summary_reports_fill_turnover_and_fee_totals():
    result = run_vectorbt(hand_fixture_panel(), FIXTURE_ORDERS, hand_fixture_config())
    summary = result.summary()
    assert summary["framework"] == "vectorbt"
    assert summary["n_fills"] == 4
    assert summary["n_buy_fills"] == 2
    assert summary["n_sell_fills"] == 2
    assert summary["n_rejected"] == 0
    assert summary["buy_notional"] == pytest.approx(20_400.0, abs=1e-9)
    assert summary["sell_notional"] == pytest.approx(8_100.0, abs=1e-9)
    assert summary["turnover"] == pytest.approx(28_500.0, abs=1e-9)
    assert summary["total_fees"] == pytest.approx(28.50, abs=1e-9)
    assert summary["final_equity"] == pytest.approx(999_941.50, abs=1e-9)
    assert summary["total_return"] == pytest.approx(999_941.50 / 1_000_000.0 - 1.0, abs=1e-15)


# ---------------------------------------------------------------------------
# The comparison itself must be able to fail
# ---------------------------------------------------------------------------
def test_compare_results_rejects_a_mutated_fee():
    import dataclasses

    results = run_both(hand_fixture_panel(), FIXTURE_ORDERS, hand_fixture_config())
    good = results["vectorbt"]
    tampered = dataclasses.replace(good, framework="tampered", fills=good.fills.copy())
    tampered.fills.loc[0, "fee"] = tampered.fills.loc[0, "fee"] + 0.01

    report = compare_results(good, tampered)
    assert not report.ok
    assert any("fee" in message for message in report.messages)
    with pytest.raises(AssertionError):
        assert_parity(good, tampered)


def test_compare_results_rejects_mutated_cash_positions_and_rejections():
    import dataclasses

    results = run_both(hand_fixture_panel(), FIXTURE_ORDERS, hand_fixture_config())
    good = results["vectorbt"]

    cash_bad = dataclasses.replace(good, framework="cash_bad", cash=good.cash.copy())
    cash_bad.cash.iloc[-1] += 1.0
    assert not compare_results(good, cash_bad).ok

    positions_bad = dataclasses.replace(good, framework="pos_bad", positions=good.positions.copy())
    positions_bad.positions.iloc[-1, 0] = 0
    assert not compare_results(good, positions_bad).ok

    rejects = pd.DataFrame(
        [{"decision_date": dt.date(2024, 1, 8), "symbol": "AAA", "quantity": 5, "reason": "x"}]
    )
    rejects_bad = dataclasses.replace(good, framework="rej_bad", rejected_orders=rejects)
    assert not compare_results(good, rejects_bad).ok


def test_compare_results_describes_order_count_and_missing_fill_differences():
    import dataclasses

    results = run_both(hand_fixture_panel(), FIXTURE_ORDERS, hand_fixture_config())
    good = results["vectorbt"]

    fewer = dataclasses.replace(good, framework="fewer", fills=good.fills.iloc[:3].reset_index(drop=True))
    report = compare_results(good, fewer)
    assert not report.ok
    assert any("fill count differs" in message for message in report.messages)
    assert len(report.fills_diff) >= 1

    empty = dataclasses.replace(good, framework="empty", fills=good.fills.iloc[0:0].reset_index(drop=True))
    report = compare_results(good, empty)
    assert not report.ok
    assert len(report.fills_diff) == len(good.fills)

    other_symbols = tuple(reversed(good.symbols))
    swapped = dataclasses.replace(
        good,
        framework="swapped",
        symbols=other_symbols,
        positions=good.positions[list(other_symbols)],
    )
    assert not compare_results(good, swapped).ok
