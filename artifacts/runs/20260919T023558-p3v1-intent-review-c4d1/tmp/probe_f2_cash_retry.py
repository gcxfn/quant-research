"""Probe F2: insufficient-cash retry loop with 5 symbols (cap-boundary buys)."""
import sys
from datetime import date
from pathlib import Path

import polars as pl

SRC = Path(r"D:\量化\src")
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
from quant.backtest.band_engine import run_band_backtest_intents  # noqa: E402

D = date
D1, D2, D3, D4, D5, D6 = (D(2024, 1, d) for d in (2, 3, 4, 5, 8, 9))
SYMS = [f"sh.60000{k}" for k in range(1, 6)]

daily = pl.concat([pl.DataFrame({
    "symbol": [s] * 6, "date": [D1, D2, D3, D4, D5, D6],
    "open": [10.0, 10.2, 10.2, 10.2, 10.2, 10.2],
    "high": [10.1, 10.3, 10.3, 10.3, 10.3, 10.3],
    "low": [9.5, 10.0, 10.0, 10.0, 10.0, 10.0],
    "close": [9.6, 10.2, 10.2, 10.2, 10.2, 10.2],
    "tradestatus": [1.0] * 6}) for s in SYMS])
half = pl.concat([pl.DataFrame({
    "symbol": [s] * 12, "trade_date": [d for d in (D1, D2, D3, D4, D5, D6)
                                       for _ in ("am", "pm")],
    "session": ["am", "pm"] * 6,
    "open": [10.0, 9.9, 10.2, 10.2, 10.2, 10.2, 10.2, 10.2, 10.2, 10.2,
             10.2, 10.2],
    "high": [10.05, 10.0, 10.3, 10.3, 10.3, 10.3, 10.3, 10.3, 10.3, 10.3,
             10.3, 10.3],
    "low": [9.9, 9.5, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0,
            10.0, 10.0],
    "close": [10.0, 9.6, 10.2, 10.2, 10.2, 10.2, 10.2, 10.2, 10.2, 10.2,
              10.2, 10.2]}) for s in SYMS])
limits = daily.select(
    "symbol", "date", (pl.col("close") * 1.1).alias("limit_up"),
    (pl.col("close") * 0.9).alias("limit_down"))

rows = [{
    "symbol": s, "side": "buy", "intent": None, "decision_date": D1,
    "decision_session": "am", "source_signal": D(2024, 1, 2),
    "expiry_date": None, "priority": p,
    "target_notional": float(t), "target_weight": None}
    for s, p, t in zip(SYMS, range(5), [4_000, 5_000, 5_000, 5_000, 5_000])]
res = run_band_backtest_intents(pl.DataFrame(
    rows, schema={"symbol": pl.String, "side": pl.String, "intent": pl.String,
                  "decision_date": pl.Date, "decision_session": pl.String,
                  "source_signal": pl.Date, "expiry_date": pl.Date,
                  "priority": pl.Int64, "target_notional": pl.Float64,
                  "target_weight": pl.Float64}),
    daily, half, limits, initial_cash=20_000.0)

print("fills:")
for r in res.fills.sort("date", "session").iter_rows(named=True):
    print("  ", r["symbol"], r["priority"], r["date"], r["session"],
          r["shares"], "@", r["price"])
print("cap voids:", res.stats["caps"]["single_name_voids"],
      "| insufficient_cash voids:",
      res.stats["cash_friction"]["insufficient_cash_orders"])
print("min settled cash:", res.daily["settled_cash"].min(),
      "| final:", res.stats["final"]["settled_cash"])
print("intent_layer:", {k: v for k, v in res.stats["intent_layer"].items()
                        if k != "n_intents"})
