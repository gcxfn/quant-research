"""Minimal Backtrader adapter for the shared P0 order contract.

This is an adapter, not an engine: it replays already-scheduled signed quantity
orders on Backtrader data feeds and reads back the standardized P0 outputs.

Execution semantics: an order is submitted during the strategy ``next()`` call of
the session *before* its execution session. Backtrader's default broker cannot
execute an order on the bar it was created on (``coc=False``), so a market order
created on day D-1 fills at day D's open -- the same next-open rule the vectorbt
adapter implements.

P0 limitation: this is not an A-share broker adaptation. There is no T+1
settlement, no price-limit or suspension handling, no lot/odd-lot rounding and no
board/lot fee schedule. It only verifies that both frameworks agree on the shared
synthetic contract.
"""

from __future__ import annotations

from typing import Sequence

import backtrader as bt
import numpy as np
import pandas as pd

from .orders import BacktestConfig, ExecutionOrder, Order, PricePanel, build_schedule, schedule_frame
from .results import BacktestResult, normalize_fills, normalize_rejects

REJECT_BROKER_MARGIN = "broker_margin"
REJECT_BROKER_REJECTED = "broker_rejected"
REJECT_BROKER_CANCELED = "broker_canceled"
REJECT_BROKER_EXPIRED = "broker_expired"
REJECT_UNFILLED_AT_END = "unfilled_at_end"

# Synthetic volume for Backtrader feeds. The P0 panel carries no volume and the
# default broker does not constrain market orders by volume, so this only keeps
# the feed well formed.
_SYNTHETIC_VOLUME = 1_000_000.0


class _ScheduledOrderStrategy(bt.Strategy):
    """Submits the pre-computed plan one session ahead and records daily state."""

    params = (
        ("plan_by_index", None),
        ("panel_dates", None),
        ("capture", None),
    )

    def __init__(self) -> None:
        super().__init__()
        self._data_by_symbol = {data._name: data for data in self.datas}
        self._meta: dict[int, ExecutionOrder] = {}
        # Share the dict with the caller so submitted refs survive the run and
        # can be reconciled against fills and rejections afterwards.
        self.p.capture["submitted"] = self._meta

    def next(self) -> None:
        bar_index = len(self) - 1
        bar_date = self.datas[0].datetime.date(0)
        expected = self.p.panel_dates[bar_index]
        if bar_date != expected:
            raise RuntimeError(
                f"Backtrader bar date {bar_date} does not match panel session {expected} at index {bar_index}"
            )

        # Orders planned for the next session are submitted now, at this close.
        for item in self.p.plan_by_index.get(bar_index + 1, ()):
            data = self._data_by_symbol[item.symbol]
            if item.quantity > 0:
                order = self.buy(data=data, size=item.quantity)
            else:
                order = self.sell(data=data, size=-item.quantity)
            self._meta[order.ref] = item

        capture = self.p.capture
        capture["daily"].append(
            {
                "date": bar_date,
                "cash": float(self.broker.getcash()),
                "positions_value": None,  # filled below from marked positions
                "equity": float(self.broker.getvalue()),
                "positions": {
                    symbol: int(self.getposition(data).size)
                    for symbol, data in self._data_by_symbol.items()
                },
                "closes": {symbol: float(data.close[0]) for symbol, data in self._data_by_symbol.items()},
            }
        )

    def notify_order(self, order) -> None:
        capture = self.p.capture
        if order.status in (order.Completed, order.Partial):
            item = self._meta.get(order.ref)
            executed_dt = order.executed.dt
            if item is None or not executed_dt:
                return
            actual_date = bt.num2date(executed_dt).date()
            if actual_date != item.exec_date:
                raise RuntimeError(
                    f"Backtrader filled ref={order.ref} on {actual_date}, expected {item.exec_date}"
                )
            size = int(round(float(order.executed.size)))
            if size != item.quantity:
                raise RuntimeError(
                    f"Backtrader filled ref={order.ref} with size {size}, expected {item.quantity}"
                )
            # Keyed by ref so a Partial followed by Completed overwrites instead of duplicating.
            capture["fills"][order.ref] = {
                "date": actual_date,
                "symbol": item.symbol,
                "quantity": size,
                "price": float(order.executed.price),
                "fee": float(order.executed.comm),
            }
        elif order.status in (order.Margin, order.Rejected, order.Canceled, order.Expired):
            reason = {
                order.Margin: REJECT_BROKER_MARGIN,
                order.Rejected: REJECT_BROKER_REJECTED,
                order.Canceled: REJECT_BROKER_CANCELED,
                order.Expired: REJECT_BROKER_EXPIRED,
            }[order.status]
            item = self._meta.get(order.ref)
            capture["rejects"][order.ref] = {
                "decision_date": item.decision_dates[0] if item else None,
                "symbol": item.symbol if item else str(order.data._name),
                "quantity": item.quantity if item else int(round(float(order.created.size))),
                "reason": reason,
            }


def _feed_frame(panel: PricePanel, symbol: str) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "open": panel.open[symbol].to_numpy(),
            "high": np.maximum(panel.open[symbol].to_numpy(), panel.close[symbol].to_numpy()),
            "low": np.minimum(panel.open[symbol].to_numpy(), panel.close[symbol].to_numpy()),
            "close": panel.close[symbol].to_numpy(),
            "volume": np.full(len(panel.index), _SYNTHETIC_VOLUME),
        },
        index=panel.index,
    )


def run_backtrader(
    panel: PricePanel,
    orders: Sequence[Order],
    config: BacktestConfig | None = None,
) -> BacktestResult:
    """Run the scheduled orders through Backtrader and return standardized output."""

    config = config or BacktestConfig()
    scheduled, rejected = build_schedule(orders, panel)

    plan_by_index: dict[int, list[ExecutionOrder]] = {}
    for item in scheduled:
        plan_by_index.setdefault(item.exec_index, []).append(item)

    capture: dict = {"fills": {}, "rejects": {}, "daily": []}
    # ``capture["submitted"]`` is injected by the strategy as {order.ref: ExecutionOrder}

    cerebro = bt.Cerebro(stdstats=False)
    cerebro.broker.setcash(float(config.initial_cash))
    cerebro.broker.setcommission(
        commission=float(config.commission_pct),
        commtype=bt.CommInfoBase.COMM_PERC,
        percabs=True,
        # BackBroker.setcommission defaults to stocklike=False (futures-like),
        # which would value a position at abs(size) * margin instead of
        # size * price and silently break equity parity with vectorbt.
        stocklike=True,
    )
    cerebro.broker.set_coc(False)
    cerebro.broker.set_coo(False)
    cerebro.broker.set_slippage_perc(0.0)
    for symbol in panel.symbols:
        cerebro.adddata(bt.feeds.PandasData(dataname=_feed_frame(panel, symbol)), name=symbol)
    cerebro.addstrategy(
        _ScheduledOrderStrategy,
        plan_by_index=plan_by_index,
        panel_dates=panel.dates,
        capture=capture,
    )
    strategies = cerebro.run()
    if len(strategies) != 1:  # pragma: no cover - defensive
        raise RuntimeError(f"expected exactly one Backtrader strategy, got {len(strategies)}")

    daily = capture["daily"]
    if len(daily) != panel.n_sessions:
        raise RuntimeError(
            f"Backtrader produced {len(daily)} daily records, expected {panel.n_sessions}"
        )

    submitted: dict[int, ExecutionOrder] = capture["submitted"]
    filled_refs = set(capture["fills"])
    broker_rejected_refs = set(capture["rejects"])
    if filled_refs & broker_rejected_refs:  # pragma: no cover - mutually exclusive states
        raise RuntimeError(f"orders both filled and rejected: {sorted(filled_refs & broker_rejected_refs)}")
    if len(submitted) != len(scheduled):  # pragma: no cover - a plan item was never submitted
        raise RuntimeError(
            f"only {len(submitted)} of {len(scheduled)} scheduled orders were submitted to Backtrader"
        )

    rejects = list(rejected.to_dict("records"))
    rejects.extend(capture["rejects"][ref] for ref in sorted(broker_rejected_refs))
    # An order accepted but never filled by the end of the run must be reported
    # rather than silently lost.
    for ref in sorted(set(submitted) - filled_refs - broker_rejected_refs):
        item = submitted[ref]
        rejects.append(
            {
                "decision_date": item.decision_dates[0],
                "symbol": item.symbol,
                "quantity": item.quantity,
                "reason": REJECT_UNFILLED_AT_END,
            }
        )

    # Every submitted order now ends in exactly one reported state: filled,
    # broker-rejected, or explicitly reported as unfilled at end of run.
    fills = [capture["fills"][ref] for ref in sorted(capture["fills"])]

    dates = pd.DatetimeIndex(panel.index)
    positions = pd.DataFrame(
        {symbol: [record["positions"][symbol] for record in daily] for symbol in panel.symbols},
        index=dates,
        dtype="int64",
    )
    positions_value = pd.Series(
        [
            float(sum(record["positions"][symbol] * record["closes"][symbol] for symbol in panel.symbols))
            for record in daily
        ],
        index=dates,
        name="positions_value",
        dtype="float64",
    )
    cash = pd.Series([record["cash"] for record in daily], index=dates, name="cash", dtype="float64")
    market_value = pd.Series([record["equity"] for record in daily], index=dates, name="equity", dtype="float64")
    equity = pd.DataFrame(
        {
            "cash": cash.to_numpy(),
            "positions_value": positions_value.to_numpy(),
            "equity": market_value.to_numpy(),
        },
        index=dates,
    )
    check = equity["cash"] + equity["positions_value"] - equity["equity"]
    tolerance = max(1e-6, 1e-9 * float(equity["equity"].abs().max()))
    if float(check.abs().max()) > tolerance:  # pragma: no cover - accounting invariant
        raise RuntimeError(
            "Backtrader equity does not equal cash plus marked positions value "
            f"(max discrepancy {float(check.abs().max())})"
        )

    return BacktestResult(
        framework="backtrader",
        initial_cash=float(config.initial_cash),
        commission_pct=float(config.commission_pct),
        dates=dates,
        symbols=panel.symbols,
        fills=normalize_fills(fills),
        scheduled_orders=schedule_frame(scheduled),
        rejected_orders=normalize_rejects(rejects),
        cash=cash,
        positions=positions,
        equity=equity,
    )
