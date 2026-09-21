"""Capture v1.1 golden outputs for test_band_hybrid.py test_h9 (zero
regression byte-compare).  Imports the pristine v1.1 snapshot, runs a fixed
stock-only intent scenario, and hashes fills/events/daily CSV serializations.
Run once BEFORE any v1.2 edit; outputs recorded in h9_golden.txt."""
import hashlib
import importlib.util
import sys
from datetime import date
from pathlib import Path

import polars as pl

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    "band_engine_v11", HERE / "band_engine_v1.1_snapshot.py")
be = importlib.util.module_from_spec(spec)
sys.modules["band_engine_v11"] = be
spec.loader.exec_module(be)

D = date
SYM = "sh.600001"
D1, D2, D3, D4, D5, D6 = (D(2024, 1, d) for d in (2, 3, 4, 5, 8, 9))
S1, S2 = D(2024, 1, 2), D(2024, 1, 3)

daily = pl.DataFrame({
    "symbol": [SYM] * 6, "date": [D1, D2, D3, D4, D5, D6],
    "open": [10.0, 9.4, 8.9, 8.5, 8.5, 8.5], "high": [10.1, 9.5, 9.0, 8.55, 8.52, 8.52],
    "low": [9.5, 9.0, 8.55, 8.4, 8.48, 8.48], "close": [9.6, 9.1, 8.6, 8.5, 8.5, 8.5],
    "tradestatus": [1.0] * 6})
half = pl.DataFrame({
    "symbol": [SYM] * 12,
    "trade_date": [D1, D1, D2, D2, D3, D3, D4, D4, D5, D5, D6, D6],
    "session": ["am", "pm"] * 6,
    "open": [10.0, 9.9, 9.4, 9.2, 8.9, 8.7, 8.5, 8.5, 8.5, 8.5, 8.5, 8.5],
    "high": [10.05, 10.0, 9.5, 9.25, 9.0, 8.7, 8.55, 8.55, 8.52, 8.51, 8.52, 8.51],
    "low": [9.9, 9.5, 9.2, 9.0, 8.7, 8.55, 8.45, 8.4, 8.48, 8.49, 8.48, 8.49],
    "close": [10.0, 9.6, 9.3, 9.1, 8.75, 8.6, 8.5, 8.5, 8.5, 8.5, 8.5, 8.5]})
limits = daily.select("symbol", "date", (pl.col("close") * 1.1).alias("limit_up"),
                      (pl.col("close") * 0.9).alias("limit_down"))
intents = pl.DataFrame([
    {"symbol": SYM, "side": "buy", "intent": None, "decision_date": D1,
     "decision_session": "am", "source_signal": S1, "expiry_date": None,
     "priority": 1, "target_notional": 10_000.0, "target_weight": None},
    {"symbol": SYM, "side": "sell", "intent": "risk", "decision_date": D2,
     "decision_session": "am", "source_signal": S2, "expiry_date": None,
     "priority": 1, "target_notional": None, "target_weight": None},
], schema={"symbol": pl.String, "side": pl.String, "intent": pl.String,
           "decision_date": pl.Date, "decision_session": pl.String,
           "source_signal": pl.Date, "expiry_date": pl.Date,
           "priority": pl.Int64, "target_notional": pl.Float64,
           "target_weight": pl.Float64})

res = be.run_band_backtest_intents(intents, daily, half, limits,
                                   initial_cash=200_000.0)

def sha_of(frame: pl.DataFrame) -> str:
    import io
    buf = io.BytesIO()
    frame.write_csv(buf)
    return hashlib.sha256(buf.getvalue()).hexdigest()

lines = []
lines.append("fills_sha256=" + sha_of(res.fills))
lines.append("events_sha256=" + sha_of(res.events))
lines.append("daily_sha256=" + sha_of(res.daily))
lines.append("clips_final_sha256=" + sha_of(res.clips_final))
lines.append("final_equity=%r" % res.daily["equity"][-1])
lines.append("final_settled_cash=%r" % res.daily["settled_cash"][-1])
for row in res.fills.iter_rows(named=True):
    lines.append("fill: %s %s %s %s %s shares=%d price=%r notional=%r "
                 "commission=%r stamp=%r net=%r is_etf=%s"
                 % (row["fill_id"], row["side"], row["intent"], row["date"],
                    row["session"], row["shares"], row["price"],
                    row["notional"], row["commission"], row["stamp_tax"],
                    row["net_cash_flow"], row["is_etf"]))
lines.append("n_events=%d" % res.events.height)
res.fills.write_csv(HERE / "h9_golden_fills.csv")
res.events.write_csv(HERE / "h9_golden_events.csv")
res.daily.write_csv(HERE / "h9_golden_daily.csv")
(HERE / "h9_golden.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
print("\n".join(lines))
