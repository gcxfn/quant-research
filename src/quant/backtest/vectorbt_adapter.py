"""Minimal vectorbt adapter for the shared P0 order contract.

This is an adapter, not an engine: it maps already-scheduled signed quantity
orders onto ``vectorbt.Portfolio.from_orders`` and reads back the standardized
P0 outputs. No sizing, selection or risk logic lives here.

Execution semantics: the ``size`` matrix is indexed by execution session and the
``price`` matrix is the open panel, so an order decided at the close of day D is
filled at the open of the next session while equity is still marked at the close.
"""

from __future__ import annotations

import sys
import warnings
from typing import Sequence

import numpy as np
import pandas as pd

from .orders import BacktestConfig, Order, PricePanel, build_schedule, schedule_frame
from .results import BacktestResult, normalize_fills, normalize_rejects


def _ensure_plotly_template_compat() -> None:
    """Allow ``import vectorbt`` when plotly >= 6/7 removed template properties.

    vectorbt 0.28.5 registers a bundled plotly template containing
    ``layout.scattermapbox``. plotly 7 removed that path and raises
    ``Bad property path: scattermapbox`` while importing vectorbt, so upstream
    import never completes. The environment pins plotly < 6; this guarded shim is
    a belt-and-braces fallback for environments where the pin is not honoured.
    """

    if "vectorbt" in sys.modules:
        return
    try:
        import plotly.graph_objects as go
    except Exception:  # pragma: no cover - plotly is an optional import path
        return

    original = go.layout.Template.__init__
    if getattr(original, "_quant_vbt_compat", False):
        return

    def _patched(self, *args, **kwargs):
        kwargs.setdefault("skip_invalid", True)
        return original(self, *args, **kwargs)

    _patched._quant_vbt_compat = True  # type: ignore[attr-defined]
    go.layout.Template.__init__ = _patched


_ensure_plotly_template_compat()
import vectorbt as vbt  # noqa: E402  (must follow the plotly compatibility shim)


def _default_freq(index: pd.DatetimeIndex):
    if len(index) < 3:
        return "1D"
    try:
        return pd.infer_freq(index) or "1D"
    except ValueError:
        return "1D"


def _size_matrix(panel: PricePanel, scheduled: Sequence) -> pd.DataFrame:
    matrix = pd.DataFrame(0.0, index=panel.index, columns=list(panel.symbols))
    for item in scheduled:
        matrix.iat[item.exec_index, panel.column_index(item.symbol)] += float(item.quantity)
    if not (matrix.to_numpy() == np.rint(matrix.to_numpy())).all():  # pragma: no cover
        raise RuntimeError("net order sizes must remain whole shares")
    return matrix


def run_vectorbt(
    panel: PricePanel,
    orders: Sequence[Order],
    config: BacktestConfig | None = None,
    *,
    freq: str | None = None,
) -> BacktestResult:
    """Run the scheduled orders through vectorbt and return standardized output."""

    config = config or BacktestConfig()
    scheduled, rejected = build_schedule(orders, panel)
    size = _size_matrix(panel, scheduled)
    resolved_freq = freq or _default_freq(panel.index)

    with warnings.catch_warnings():
        # vectorbt warns about freq/annualization for irregular synthetic
        # calendars; fills, cash, positions and equity are unaffected.
        warnings.simplefilter("ignore", category=UserWarning)
        portfolio = vbt.Portfolio.from_orders(
            close=panel.close,
            size=size,
            price=panel.open,
            size_type="amount",
            direction="both",
            fees=float(config.commission_pct),
            fixed_fees=0.0,
            slippage=0.0,
            reject_prob=0.0,
            allow_partial=False,
            raise_reject=False,
            init_cash=float(config.initial_cash),
            cash_sharing=True,
            call_seq="auto",
            update_value=False,
            seed=0,
            freq=resolved_freq,
        )

    fill_records = []
    order_records = portfolio.orders.records_readable
    if len(order_records):
        for row in order_records.itertuples(index=False):
            quantity = int(round(float(row.Size)))
            if str(row.Side).strip().lower().startswith("s"):
                quantity = -quantity
            fill_records.append(
                {
                    "date": pd.Timestamp(row.Timestamp).date(),
                    "symbol": str(row.Column),
                    "quantity": quantity,
                    "price": float(row.Price),
                    "fee": float(row.Fees),
                }
            )

    cash = portfolio.cash()
    if isinstance(cash, pd.DataFrame):  # pragma: no cover - only when not grouped
        cash = cash.sum(axis=1)
    cash = cash.reindex(panel.index)
    positions = portfolio.assets().reindex(index=panel.index, columns=list(panel.symbols))
    equity_marked = portfolio.value().reindex(panel.index)
    positions_value = portfolio.asset_value().reindex(panel.index)

    if cash.isna().any() or positions.isna().to_numpy().any() or equity_marked.isna().any():
        raise RuntimeError("vectorbt output could not be aligned to the price panel index")

    positions_int = positions.round().astype("int64")
    equity = pd.DataFrame(
        {
            "cash": cash.astype("float64").to_numpy(),
            "positions_value": positions_value.astype("float64").to_numpy(),
            "equity": equity_marked.astype("float64").to_numpy(),
        },
        index=panel.index,
    )
    check = equity["cash"] + equity["positions_value"] - equity["equity"]
    tolerance = max(1e-6, 1e-9 * float(equity["equity"].abs().max()))
    if float(check.abs().max()) > tolerance:  # pragma: no cover - accounting invariant
        raise RuntimeError(
            "vectorbt equity does not equal cash plus marked positions value "
            f"(max discrepancy {float(check.abs().max())})"
        )

    return BacktestResult(
        framework="vectorbt",
        initial_cash=float(config.initial_cash),
        commission_pct=float(config.commission_pct),
        dates=panel.index,
        symbols=panel.symbols,
        fills=normalize_fills(fill_records),
        scheduled_orders=schedule_frame(scheduled),
        rejected_orders=normalize_rejects(rejected.to_dict("records")),
        cash=pd.Series(cash.to_numpy(), index=panel.index, name="cash", dtype="float64"),
        positions=positions_int,
        equity=equity,
    )
