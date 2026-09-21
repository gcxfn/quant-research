"""Hand-checked component tests for fixed_scheme_lib (zero trial use)."""
from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

import polars as pl

from quant.research.fixed_scheme_lib import (
    ATRTable, ConstantOverlayHost, DefensiveLeg, build_atr20,
    cagr_from_monthly, defensive_month_returns, mdd_from_monthly,
    mix_from_monthly, monthly_returns_from_equity, t200_monthly,
)

SYM = "sh.600001"


def daily_frame(rows):
    return pl.DataFrame({
        "symbol": [SYM] * len(rows), "date": [r[0] for r in rows],
        "open": [float(r[1]) for r in rows],
        "high": [float(r[2]) for r in rows],
        "low": [float(r[3]) for r in rows],
        "close": [float(r[4]) for r in rows]})


def test_atr20_constant_range():
    days = [date(2020, 1, i) for i in range(1, 32)]  # 31 sessions
    rows = [(d, 10.0, 10.6, 9.4, 10.0) for d in days]   # TR = 1.2 always
    tbl = build_atr20(daily_frame(rows))
    # atr at day 25 uses TR of days 1..24 (idx 0..23) -> 1.2
    assert abs(tbl.atr(SYM, date(2020, 1, 25)) - 1.2) < 1e-9
    # below the 21-session floor there is no value
    try:
        tbl.atr(SYM, date(2020, 1, 21))
        raised = False
    except KeyError:
        raised = True
    assert raised


def test_t200_monthly_gate(tmp_path: Path):
    # 260 flat sessions at 100 then a slide to 80: after the slide the
    # close < SMA200 -> E_OFF; before it, close == sma -> invested
    days = [date(2019, 1, 1) + __import__("datetime").timedelta(days=i)
            for i in range(300)]
    closes = [100.0] * 260 + [100.0 - 0.2 * (i - 259) for i in range(260, 300)]
    frame = pl.DataFrame({
        "ts_code": ["000300.SH"] * len(days),
        "trade_date": [d.strftime("%Y%m%d") for d in days],
        "close": closes})
    p = tmp_path / "idx.csv"
    frame.write_csv(p)
    sig = [date(2019, 6, 1), date(2019, 10, 1)]
    out = t200_monthly(p, days, sig)
    assert out[sig[0]] == 1.0    # flat at 100: close >= sma
    assert out[sig[1]] == 0.4    # deep below the average


def test_defensive_month_returns_equal_weight(tmp_path: Path):
    # two ETFs, three month-ends: A 10->11->12.1 (+10%/month), B flat
    rows = []
    month_ends = [date(2020, 1, 31), date(2020, 2, 29), date(2020, 3, 31)]
    for sym, closes in (("sh.511010", [10.0, 11.0, 12.1]),
                        ("sz.159934", [5.0, 5.0, 5.0])):
        for d, c in zip(month_ends, closes):
            rows.append({"symbol": sym, "date": d, "close": c})
        lines = ["ts_code,trade_date,adj_factor"]
        lines += ["X,%s,1.0" % d.strftime("%Y%m%d") for d in month_ends]
        (tmp_path / f"chunk_{sym.split('.')[1]}."
         f"{sym.split('.')[0].upper()}.csv").write_text(
            "\n".join(lines) + "\n", encoding="utf-8")
    etf = pl.DataFrame(rows)
    out = defensive_month_returns(
        etf, tmp_path, symbols=("sh.511010", "sz.159934"))
    assert abs(out["2020-02"] - 0.05) < 1e-12   # (10% + 0%)/2
    assert abs(out["2020-03"] - 0.05) < 1e-12


def test_defensive_leg_exit_and_rebalance():
    closes = {"sh.511010": 9.0, "sh.518880": 3.0, "sz.159934": 3.0}
    leg = DefensiveLeg(close_at=lambda s, d: closes[s],
                       high60_at=lambda s, d: (10.0 if s == "sh.511010"
                                               else 3.05))
    # drawdown exit: 511010 at 9.0 vs high 10.0 = -10% -> exit; held
    ledger = {"positions": [
        {"symbol": "sh.511010", "shares": 100,
         "clips": [{"shares": 100, "acquired": "2020-01-05",
                    "session": "am", "price": 10.0}]}],
        "equity_snapshot": 100_000.0}
    rows = leg.decide(date(2020, 3, 2), ledger, rebalance=True,
                      equity=100_000.0)
    exits = [r for r in rows if r["symbol"] == "sh.511010"]
    assert len(exits) == 1 and exits[0]["intent"] == "risk"
    assert leg.active == {"sh.518880", "sz.159934"}
    # rebalance targets 0.6/2 = 30% -> capped at 25%
    tw = leg.target_weight()
    assert abs(tw - 0.25) < 1e-12
    # remaining legs get buy rows at 25%
    buys = [r for r in rows if r["side"] == "buy"]
    assert {b["symbol"] for b in buys} == {"sh.518880", "sz.159934"}
    assert all(abs(b["target_weight"] - 0.25) < 1e-12 for b in buys)


def test_constant_host_trim_and_topup():
    e_table = {date(2020, 1, 31): 1.0, date(2020, 2, 28): 0.4}
    marks = {"sh.600001": 10.0}

    def mark(s, d):
        return marks.get(s)

    host = ConstantOverlayHost(e_table, mark)
    ledger = {"date": date(2020, 2, 3), "session": "pm",
              "equity_snapshot": 100_000.0,
              "positions": [{"symbol": "sh.600001", "shares": 1_000,
                             "clips": [{"shares": 1_000,
                                        "acquired": "2020-01-06",
                                        "session": "am",
                                        "price": 10.0}]}]}
    st = host.step(ledger, members=["sh.600001"],
                   rank_of={"sh.600001": 1},
                   source_signal=date(2020, 2, 28), expiry=None)
    # weight 10% vs target 4% -> trim to 4%
    assert st.trims == ("sh.600001",)
    assert abs(st.rows[0]["target_weight"] - 0.04) < 1e-12
    assert st.rows[0]["intent"] == "risk"
    # restore month: E back to 1.0 -> top-up buy
    ledger_small = dict(ledger, positions=[
        {"symbol": "sh.600001", "shares": 300,
         "clips": [{"shares": 300, "acquired": "2020-01-06",
                    "session": "am", "price": 10.0}]}])
    st2 = host.step(ledger_small, members=["sh.600001"],
                    rank_of={"sh.600001": 1},
                    source_signal=date(2020, 1, 31), expiry=None)
    assert st2.topups == ("sh.600001",)


def test_mix_helpers_hand_check():
    stock = {"2020-01": 0.10, "2020-02": -0.10}
    defn = {"2020-01": 0.00, "2020-02": 0.02}
    mix = mix_from_monthly(stock, defn, w_stock=0.4)
    assert abs(mix["2020-01"] - 0.04) < 1e-12
    assert abs(mix["2020-02"] - (-0.028)) < 1e-12
    eq = monthly_returns_from_equity(
        [date(2020, 1, 31), date(2020, 2, 29)],
        [100.0, 110.0])
    assert abs(eq["2020-02"] - 0.10) < 1e-12
    m = {"2020-01": 0.10, "2020-02": -0.10}
    year = {f"2020-{m:02d}": 0.01 for m in range(1, 13)}
    assert abs(cagr_from_monthly(year) - (1.01 ** 12 - 1)) < 1e-9
    assert abs(mdd_from_monthly(m) - (-0.10)) < 1e-12
