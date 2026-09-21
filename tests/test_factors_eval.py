"""tests for src/quant/factors/eval.py (F1) — synthetic hand-computed cases."""

from __future__ import annotations

import math
from datetime import date as D

import polars as pl
import pytest

from quant.factors.eval import (
    FREEZE_END,
    FactorEvalConfig,
    FactorEvalError,
    eval_cache_key,
    evaluate_factor,
    pit_financial,
)


def _panel(rows):
    """rows: (date, symbol, close, preclose[, tradestatus, isST])."""
    cols = {
        "date": [r[0] for r in rows],
        "symbol": [r[1] for r in rows],
        "close": [float(r[2]) for r in rows],
        "preclose": [float(r[3]) for r in rows],
    }
    if len(rows[0]) > 4:
        cols["tradestatus"] = [r[4] for r in rows]
        cols["isST"] = [r[5] for r in rows]
    return pl.DataFrame(cols).with_columns(pl.col("date").cast(pl.Date))


def _factor(rows):
    return pl.DataFrame(
        {"symbol": [r[0] for r in rows], "signal_date": [r[1] for r in rows],
         "value": [float(r[2]) for r in rows]}
    ).with_columns(pl.col("signal_date").cast(pl.Date))


# ---------------------------------------------------------------------------
# fixtures: 3 symbols x 6 days, all trading, no ST, horizon=2
# gross daily returns chosen for hand computation:
#   sh.600001: +10%, +10%,  +5%,  +5%,  0%   (forward from d0: 1.1*1.1-1=0.21)
#   sh.600002: -10%, -10%,  -5%,  -5%,  0%
#   sh.600003:   0%,   0%,   0%,   0%,  0%
# ---------------------------------------------------------------------------

def base_panel():
    days = [D(2015, 1, 5 + i) for i in range(5)]
    px1 = [110.0, 121.0, 127.05, 133.4025, 133.4025]
    px2 = [90.0, 81.0, 76.95, 73.1025, 73.1025]
    px3 = [100.0, 100.0, 100.0, 100.0, 100.0]
    rows = []
    for i, d in enumerate(days):
        prev1 = 100.0 if i == 0 else px1[i - 1]
        prev2 = 100.0 if i == 0 else px2[i - 1]
        prev3 = 100.0 if i == 0 else px3[i - 1]
        rows.append((d, "sh.600001", px1[i], prev1, 1, 0))
        rows.append((d, "sh.600002", px2[i], prev2, 1, 0))
        rows.append((d, "sh.600003", px3[i], prev3, 1, 0))
    return _panel(rows)


CFG_FAST = FactorEvalConfig(
    horizon_days=2, n_groups=2, min_history_rows=0, eval_freq="D"
)


def test_rank_ic_exact_and_alignment():
    """Ordered factor vs ordered 2-day forward return, hand-checked.

    Window for signal t0 is days 2..3 (NOT days 1..2): sym1 = 1.10*1.05-1
    = +0.155, sym2 = 0.90*0.95-1 = -0.145, sym3 = 0.  A harness that leaked
    the signal day's own return (+10%/-10%/0) would produce different
    numbers (+0.21/-0.19), so these assertions pin the alignment.
    """
    p = base_panel()
    f = _factor([
        ("sh.600001", D(2015, 1, 5), 1.0),
        ("sh.600002", D(2015, 1, 5), -1.0),
        ("sh.600003", D(2015, 1, 5), 0.0),
    ])
    res = evaluate_factor(f, p, CFG_FAST)
    assert res["n_dates"] == 1
    # groups (n=3, g=2): low = {sym2}, high = {sym3, sym1}
    assert res["group_mean_ret"][0] == pytest.approx(-0.145)
    assert res["group_mean_ret"][1] == pytest.approx((0.155 + 0.0) / 2)
    assert res["long_short_mean"] == pytest.approx(0.0775 - (-0.145))
    assert res["monotonicity"] == pytest.approx(1.0)


def test_alignment_uses_next_day_window():
    """A factor equal to the day-t return of a MEAN-REVERTING tape must not
    score IC=+1 under correct alignment (same-day leakage would give +1)."""
    # symbol A: +10% then -10%; symbol B: -10% then +10%
    days = [D(2016, 3, 1), D(2016, 3, 2)]
    rows = [
        (days[0], "sh.600001", 110.0, 100.0, 1, 0),
        (days[0], "sh.600002", 90.0, 100.0, 1, 0),
        (days[1], "sh.600001", 99.0, 110.0, 1, 0),
        (days[1], "sh.600002", 99.0, 90.0, 1, 0),
    ]
    f = _factor([
        ("sh.600001", days[0], 1.0),   # day-0 winner
        ("sh.600002", days[0], -1.0),  # day-0 loser
    ])
    # horizon=1: fwd(t0) is exactly the day-2 return (no same-day leakage)
    res = evaluate_factor(
        f, _panel(rows),
        FactorEvalConfig(horizon_days=1, n_groups=2, min_history_rows=0),
    )
    # fwd(t0) = (-0.1, +0.1) for (A, B); value=(+1,-1) -> rho = -1
    assert res["ic_mean"] == pytest.approx(-1.0)
    assert res["long_short_mean"] == pytest.approx(-0.2)


def test_forward_return_compound_from_preclose_chain():
    """Two-day window hand-checked: (1.10)*(1.05) - 1 = 0.155."""
    days = [D(2017, 6, 1), D(2017, 6, 2), D(2017, 6, 5)]
    rows = [
        (days[0], "sh.600001", 100.0, 100.0, 1, 0),
        (days[1], "sh.600001", 110.0, 100.0, 1, 0),
        (days[2], "sh.600001", 115.5, 110.0, 1, 0),
    ]
    f = _factor([("sh.600001", days[0], 1.0)])
    # single symbol: IC undefined (zero variance) -> guarded error
    with pytest.raises(FactorEvalError):
        evaluate_factor(
            f, _panel(rows),
            FactorEvalConfig(horizon_days=2, n_groups=2, min_history_rows=0),
        )
    # instead verify via group stats of a two-symbol frame
    rows += [
        (days[0], "sh.600002", 100.0, 100.0, 1, 0),
        (days[1], "sh.600002", 100.0, 100.0, 1, 0),
        (days[2], "sh.600002", 100.0, 100.0, 1, 0),
    ]
    f2 = _factor([("sh.600001", days[0], 2.0), ("sh.600002", days[0], 1.0)])
    res = evaluate_factor(
        f2, _panel(rows),
        FactorEvalConfig(horizon_days=2, n_groups=2, min_history_rows=0),
    )
    # sym1 fwd = 1.10*1.05-1 = 0.155; sym2 fwd = 0
    assert res["group_mean_ret"][0] == pytest.approx(0.0)
    assert res["group_mean_ret"][1] == pytest.approx(0.155)
    assert res["ic_mean"] == pytest.approx(1.0)


def test_freeze_breach_raises():
    p = base_panel()
    f = _factor([("sh.600001", D(2025, 1, 2), 1.0)])
    with pytest.raises(FactorEvalError, match="freeze"):
        evaluate_factor(f, p, CFG_FAST)
    bad_panel = _panel([
        (D(2025, 1, 2), "sh.600001", 1.0, 1.0, 1, 0),
    ])
    f_ok = _factor([("sh.600001", D(2015, 1, 6), 1.0)])
    with pytest.raises(FactorEvalError, match="freeze"):
        evaluate_factor(f_ok, bad_panel, CFG_FAST)


def test_pool_filters_st_halt_board():
    p = base_panel()
    # add an ST symbol and a halted symbol with extreme returns
    days = [D(2015, 1, 5 + i) for i in range(5)]
    extra = []
    for i, d in enumerate(days):
        extra.append((d, "sh.600099", 200.0 if i else 100.0, 100.0 if i == 0 else 200.0, 1, 1))  # ST
        extra.append((d, "sh.688001", 200.0 if i else 100.0, 100.0 if i == 0 else 200.0, 1, 0))  # KC board
        extra.append((d, "sh.600098", 100.0, 100.0, 0, 0))  # halted
    p2 = pl.concat([p, _panel(extra)])
    f = _factor([
        ("sh.600001", days[0], 1.0), ("sh.600002", days[0], -1.0),
        ("sh.600003", days[0], 0.0), ("sh.600099", days[0], 5.0),
        ("sh.688001", days[0], 5.0), ("sh.600098", days[0], 5.0),
    ])
    res = evaluate_factor(f, p2, CFG_FAST)
    # excluded symbols must not enter: coverage == 3
    assert res["coverage_mean_symbols"] == pytest.approx(3.0)


def test_yearly_breakdown_has_2015_key():
    p = base_panel()
    days = [D(2015, 1, 5)]
    f = _factor([
        ("sh.600001", days[0], 1.0),
        ("sh.600002", days[0], -1.0),
        ("sh.600003", days[0], 0.0),
    ])
    res = evaluate_factor(f, p, CFG_FAST)
    assert 2015 in res["ic_by_year"]
    assert 2015 in res["long_short_by_year"]


def test_month_end_frequency_picks_last_trading_day():
    p = base_panel()
    # signals on all 5 days; only the last day (2015-01-09) is month-end-ish
    # build a panel spanning two months to have one month-end each
    days = [D(2015, 1, 5 + i) for i in range(5)] + [D(2015, 2, 2), D(2015, 2, 27)]
    rows = []
    px = {"sh.600001": [], "sh.600002": [], "sh.600003": []}
    closes = [110.0, 121.0, 127.05, 133.4, 133.4, 140.0, 147.0]
    for i, d in enumerate(days):
        c = closes[min(i, len(closes) - 1)]
        prev = closes[i - 1] if i > 0 else 100.0
        for s in ("sh.600001", "sh.600002", "sh.600003"):
            use_c = c if s == "sh.600001" else (200.0 - c if s == "sh.600002" else 100.0)
            use_p = prev if s == "sh.600001" else (200.0 - prev if s == "sh.600002" else 100.0)
            rows.append((d, s, use_c, use_p, 1, 0))
    f_rows = [(s, d, 1.0 if s == "sh.600001" else (-1.0 if s == "sh.600002" else 0.0))
              for d in days for s in ("sh.600001", "sh.600002", "sh.600003")]
    res = evaluate_factor(
        _factor(f_rows), _panel(rows),
        FactorEvalConfig(horizon_days=1, n_groups=2, min_history_rows=0, eval_freq="M"),
    )
    # only 2015-01-09 and 2015-02-27 survive -> 2 dates
    assert res["n_dates"] == 2


def test_turnover_hand_case():
    # top-group membership flips completely between two dates -> turnover 1.0
    days = [D(2015, 1, 5), D(2015, 1, 6), D(2015, 1, 7), D(2015, 1, 8)]
    rows = []
    for i, d in enumerate(days):
        for s, (c0, drift) in {
            "sh.600001": (100.0, 1.0), "sh.600002": (100.0, -1.0),
            "sh.600003": (100.0, 0.5), "sh.600004": (100.0, -0.5),
        }.items():
            prev = c0 + drift * (i - 1) if i > 0 else c0
            rows.append((d, s, c0 + drift * i, prev, 1, 0))
    f_rows = []
    for i, d in enumerate(days):
        vals = {"sh.600001": 4.0, "sh.600002": 3.0, "sh.600003": 2.0, "sh.600004": 1.0}
        if i % 2 == 1:  # alternate the ranking every date -> full membership flip
            vals = {"sh.600001": 1.0, "sh.600002": 2.0, "sh.600003": 3.0, "sh.600004": 4.0}
        for s, v in vals.items():
            f_rows.append((s, d, float(v)))
    res = evaluate_factor(
        _factor(f_rows), _panel(rows),
        FactorEvalConfig(horizon_days=1, n_groups=2, min_history_rows=0),
    )
    # top group alternates {600001,600002} / {600003,600004} -> turnover 1.0
    assert res["turnover_top_group"] == pytest.approx(1.0)


def test_pit_financial_dedup_priority_and_fallback():
    ev = pl.DataFrame({
        "ts_code": ["600519.SH", "600519.SH", "000001.SZ", "000002.SZ"],
        "end_date": ["20200331", "20200331", "20200630", "20200930"],
        "ann_date": ["20200420", "20200428", None, "20201030"],
        "f_ann_date": [None, "20200429", None, None],
        "update_flag": [1, 0, 1, 1],
    })
    out = pit_financial(ev)
    rows = {r["symbol"]: r for r in out.to_dicts()}
    # amendment (later ann_date, f_ann_date present) wins
    assert rows["sh.600519"]["signal_date"] == D(2020, 4, 29)
    assert rows["sh.600519"]["end_date"] == D(2020, 3, 31)
    # missing both dates -> 90d fallback from quarter end 2020-06-30
    assert rows["sz.000001"]["signal_date"] == D(2020, 9, 28)
    assert rows["sz.000001"]["used_90d_fallback"] is True
    assert rows["sz.000002"]["signal_date"] == D(2020, 10, 30)
    assert rows["sz.000002"]["used_90d_fallback"] is False


def test_config_validation_and_cache_key_stability():
    with pytest.raises(FactorEvalError):
        FactorEvalConfig(horizon_days=0)
    with pytest.raises(FactorEvalError):
        FactorEvalConfig(eval_freq="W")
    cfg = FactorEvalConfig(horizon_days=5)
    k1 = eval_cache_key({"code": "mom20", "params": {"w": 20}}, "abc", cfg)
    k2 = eval_cache_key({"code": "mom20", "params": {"w": 20}}, "abc", cfg)
    k3 = eval_cache_key({"code": "mom20", "params": {"w": 21}}, "abc", cfg)
    k4 = eval_cache_key({"code": "mom20", "params": {"w": 20}}, "abd", cfg)
    assert k1 == k2 and k1 != k3 and k1 != k4
    assert len(k1) == 64


def test_duplicate_factor_keys_rejected():
    f = _factor([
        ("sh.600001", D(2015, 1, 5), 1.0),
        ("sh.600001", D(2015, 1, 5), 2.0),
    ])
    with pytest.raises(FactorEvalError, match="duplicate"):
        evaluate_factor(f, base_panel(), CFG_FAST)


def test_corr_with_others():
    p = base_panel()
    f = _factor([
        ("sh.600001", D(2015, 1, 5), 1.0),
        ("sh.600002", D(2015, 1, 5), -1.0),
        ("sh.600003", D(2015, 1, 5), 0.0),
    ])
    inv = _factor([
        ("sh.600001", D(2015, 1, 5), -1.0),
        ("sh.600002", D(2015, 1, 5), 1.0),
        ("sh.600003", D(2015, 1, 5), 0.0),
    ])
    res = evaluate_factor(f, p, CFG_FAST, others={"inv": inv})
    assert res["corr_with_others"]["inv"] == pytest.approx(-1.0)


# --- R11 (2026-09-20 strategy review): the chain keeps mid-window rows -------

def test_r11_midwindow_st_return_stays_in_chain():
    """R11 hand-calc from the review's 4-row counter-example: signal day
    non-ST @10; day+1 turns ST and falls to 9 (-10%); days +2/+3 back to
    non-ST, flat at 9.  horizon_days=1 must read the -10% ST-day return;
    the pre-R11 engine deleted the ST row first and chained over the flat
    rows, reading 0% and silently extending the window."""
    days = [D(2016, 3, 1), D(2016, 3, 2), D(2016, 3, 3), D(2016, 3, 4)]
    rows = [
        (days[0], "sh.600001", 10.0, 10.0, 1, 0),
        (days[1], "sh.600001", 9.0, 10.0, 1, 1),   # ST turn: -10% same day
        (days[2], "sh.600001", 9.0, 9.0, 1, 0),
        (days[3], "sh.600001", 9.0, 9.0, 1, 0),
        (days[0], "sh.600002", 10.0, 10.0, 1, 0),
        (days[1], "sh.600002", 10.0, 10.0, 1, 0),
        (days[2], "sh.600002", 10.0, 10.0, 1, 0),
        (days[3], "sh.600002", 10.0, 10.0, 1, 0),
    ]
    f = _factor([("sh.600001", days[0], 1.0), ("sh.600002", days[0], -1.0)])
    res = evaluate_factor(
        f, _panel(rows),
        FactorEvalConfig(horizon_days=1, n_groups=2, min_history_rows=0),
    )
    # group 1 (low value) = the flat control at 0%; group 2 = the ST-turn
    # name at -10%.  The pre-R11 chain read 0% for BOTH.
    assert res["group_mean_ret"][0] == pytest.approx(0.0)
    assert res["group_mean_ret"][1] == pytest.approx(-0.10)
    assert res["long_short_mean"] == pytest.approx(-0.10)
    # eligibility is point-in-time: a signal dated ON the ST day produces
    # no evaluation row for that symbol (two eligible rows stay -> IC
    # still defined)
    rows3 = rows + [
        (days[0], "sh.600003", 10.0, 10.0, 1, 0),
        (days[1], "sh.600003", 11.0, 10.0, 1, 0),   # +10% keeps IC defined
        (days[2], "sh.600003", 11.0, 11.0, 1, 0),
        (days[3], "sh.600003", 11.0, 11.0, 1, 0),
    ]
    f_st = _factor([
        ("sh.600001", days[1], 1.0),   # signal on the ST day -> excluded
        ("sh.600002", days[0], -1.0),
        ("sh.600003", days[0], 0.5),
    ])
    res2 = evaluate_factor(
        f_st, _panel(rows3),
        FactorEvalConfig(horizon_days=1, n_groups=2, min_history_rows=0),
    )
    assert res2["coverage_mean_symbols"] == pytest.approx(2.0)


def test_r11_halted_row_freezes_chain_at_zero():
    """R11: a halted row enters the chain at return 0 (the price is frozen
    at the last trade); the resumption gap lands on the resumption row.
    Hand-calc, horizon=2 from d0 across (halt, -10% resumption):
    (1 + 0) x (1 - 0.10) - 1 = -0.10."""
    days = [D(2017, 9, 1), D(2017, 9, 4), D(2017, 9, 5), D(2017, 9, 6)]
    rows = [
        (days[0], "sh.600001", 10.0, 10.0, 1, 0),
        (days[1], "sh.600001", 10.0, 10.0, 0, 0),   # halted: frozen price
        (days[2], "sh.600001", 9.0, 10.0, 1, 0),    # resumes: -10%
        (days[3], "sh.600001", 9.0, 9.0, 1, 0),
        (days[0], "sh.600002", 10.0, 10.0, 1, 0),
        (days[1], "sh.600002", 10.0, 10.0, 1, 0),
        (days[2], "sh.600002", 10.0, 10.0, 1, 0),
        (days[3], "sh.600002", 10.0, 10.0, 1, 0),
    ]
    f = _factor([("sh.600001", days[0], 1.0), ("sh.600002", days[0], -1.0)])
    res = evaluate_factor(
        f, _panel(rows),
        FactorEvalConfig(horizon_days=2, n_groups=2, min_history_rows=0),
    )
    assert res["group_mean_ret"][0] == pytest.approx(0.0)
    assert res["group_mean_ret"][1] == pytest.approx(-0.10)


def test_r11_trading_row_null_return_raises():
    """R11: a TRADING row with a null close/preclose return is a data
    defect -- it must raise, not silently enter the chain as 0."""
    panel = pl.DataFrame({
        "date": [D(2018, 1, 1), D(2018, 1, 2)],
        "symbol": ["sh.600001"] * 2,
        "close": [10.0, None],
        "preclose": [None, 10.0],
        "tradestatus": [1, 1],
        "isST": [0, 0],
    }).with_columns(pl.col("date").cast(pl.Date))
    f = _factor([("sh.600001", D(2018, 1, 1), 1.0)])
    with pytest.raises(FactorEvalError, match="null close/preclose"):
        evaluate_factor(
            f, panel,
            FactorEvalConfig(horizon_days=1, n_groups=2, min_history_rows=0),
        )
