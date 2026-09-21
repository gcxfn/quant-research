"""Order contract shared by the vectorbt and Backtrader adapters.

This module is the single definition of the P0 order/price contract. It is not a
backtest engine: it only validates inputs and turns externally supplied signed
quantity orders into framework-neutral execution instructions.

Semantics (identical for both adapters):

* An order carries ``decision_date`` -- the session whose close the decision is
  known at. It executes at the **open of the first session strictly after**
  ``decision_date``. Decisions therefore can never use the price they trade at.
* ``quantity`` is signed whole shares: ``> 0`` buys, ``< 0`` sells. Positions may
  become negative; the P0 fixture assumes ample cash and no borrowing rules.
* Orders sharing the same execution session and symbol are netted into one
  aggregated order before reaching either framework. Without netting, two
  opposite orders would produce two fills (and two commissions) in Backtrader
  but one fill in vectorbt, which would break fee parity.
* Orders that cannot be represented identically in both frameworks are rejected
  with an explicit reason instead of being silently dropped.
"""

from __future__ import annotations

import bisect
import datetime as dt
from dataclasses import dataclass
from typing import Iterable, Sequence

import numpy as np
import pandas as pd

# Rejection reasons. Kept as short stable strings so both adapters and the
# parity comparison can rely on them.
REJECT_UNKNOWN_SYMBOL = "unknown_symbol"
REJECT_ZERO_QUANTITY = "zero_quantity"
REJECT_NO_NEXT_SESSION = "no_next_session"
REJECT_BEFORE_PANEL = "decision_before_first_session"
REJECT_NET_ZERO = "net_zero_quantity"
REJECT_BAD_OPEN_PRICE = "bad_open_price"

ORDER_COLUMNS = ("decision_date", "symbol", "quantity")
REJECT_COLUMNS = ("decision_date", "symbol", "quantity", "reason")
SCHEDULE_COLUMNS = ("decision_dates", "exec_date", "symbol", "quantity")

_VALID_REJECT_REASONS = frozenset(
    {
        REJECT_UNKNOWN_SYMBOL,
        REJECT_ZERO_QUANTITY,
        REJECT_NO_NEXT_SESSION,
        REJECT_BEFORE_PANEL,
        REJECT_NET_ZERO,
        REJECT_BAD_OPEN_PRICE,
    }
)


def _as_date(value: dt.date, field: str) -> dt.date:
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    if isinstance(value, pd.Timestamp):
        return value.date()
    raise TypeError(f"{field} must be a datetime.date, got {type(value).__name__}")


@dataclass(frozen=True)
class Order:
    """A decision expressed as a signed quantity, executed at the next open."""

    decision_date: dt.date
    symbol: str
    quantity: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "decision_date", _as_date(self.decision_date, "decision_date"))
        if not isinstance(self.symbol, str) or not self.symbol:
            raise ValueError("symbol must be a non-empty string")
        if isinstance(self.quantity, bool) or not isinstance(self.quantity, (int, np.integer)):
            raise TypeError(f"quantity must be an integer number of shares, got {type(self.quantity).__name__}")
        object.__setattr__(self, "quantity", int(self.quantity))


@dataclass(frozen=True)
class BacktestConfig:
    """Account settings that must be identical for a valid cross-framework test.

    ``commission_pct`` is a fraction of traded notional (``0.001 == 0.1%``) and is
    applied by both frameworks as ``abs(quantity) * price * commission_pct``.
    ``initial_cash`` is deliberately large in P0 so cash never constrains order
    execution and no borrowing or margin logic is exercised.
    """

    initial_cash: float = 1_000_000.0
    commission_pct: float = 0.0
    allow_negative_positions: bool = True

    def __post_init__(self) -> None:
        if not np.isfinite(self.initial_cash) or self.initial_cash <= 0:
            raise ValueError("initial_cash must be a positive finite number")
        if not np.isfinite(self.commission_pct) or self.commission_pct < 0:
            raise ValueError("commission_pct must be a non-negative finite number")


@dataclass(frozen=True)
class ExecutionOrder:
    """Framework-neutral instruction: net signed quantity at one session's open."""

    exec_index: int
    exec_date: dt.date
    symbol: str
    quantity: int
    decision_dates: tuple[dt.date, ...]

    def to_record(self) -> dict:
        return {
            "decision_dates": self.decision_dates,
            "exec_date": self.exec_date,
            "symbol": self.symbol,
            "quantity": self.quantity,
        }


@dataclass(frozen=True)
class PricePanel:
    """Complete synthetic or standardized daily panel: open and close per symbol.

    Both frames must share one sorted ``DatetimeIndex`` and one column order.
    P0 requires a gap-free panel: missing sessions are a P1 data-contract concern
    and Backtrader cannot represent NaN bars faithfully.
    """

    open: pd.DataFrame
    close: pd.DataFrame

    def __post_init__(self) -> None:
        if not isinstance(self.open, pd.DataFrame) or not isinstance(self.close, pd.DataFrame):
            raise TypeError("open and close must be pandas DataFrames")
        if self.open.shape != self.close.shape:
            raise ValueError(f"open and close shape mismatch: {self.open.shape} vs {self.close.shape}")
        if len(self.open) == 0:
            raise ValueError("price panel must contain at least one session")
        if list(self.open.columns) != list(self.close.columns):
            raise ValueError("open and close must have identical columns in identical order")

        idx = pd.DatetimeIndex(self.open.index)
        if idx.has_duplicates:
            raise ValueError("price panel index contains duplicate sessions")
        if not idx.is_monotonic_increasing:
            raise ValueError("price panel index must be sorted ascending")
        if list(idx) != list(pd.DatetimeIndex(self.close.index)):
            raise ValueError("open and close must share one identical index")

        open_df = self.open.copy()
        close_df = self.close.copy()
        open_df.index = idx.normalize()
        close_df.index = idx.normalize()
        open_df = open_df.astype("float64")
        close_df = close_df.astype("float64")

        for name, frame in (("open", open_df), ("close", close_df)):
            values = frame.to_numpy()
            if not np.isfinite(values).all():
                bad = frame.index[~np.isfinite(values).all(axis=1)].tolist()
                raise ValueError(f"{name} panel contains non-finite values on {bad[:3]}")
            if (values <= 0).any():
                raise ValueError(f"{name} panel must contain strictly positive prices")
            if not (frame.columns.map(lambda c: isinstance(c, str) and bool(c))).all():
                raise ValueError("symbol columns must be non-empty strings")

        object.__setattr__(self, "open", open_df)
        object.__setattr__(self, "close", close_df)

    @property
    def index(self) -> pd.DatetimeIndex:
        return pd.DatetimeIndex(self.open.index)

    @property
    def dates(self) -> tuple[dt.date, ...]:
        return tuple(ts.date() for ts in self.index)

    @property
    def symbols(self) -> tuple[str, ...]:
        return tuple(self.open.columns)

    @property
    def n_sessions(self) -> int:
        return len(self.open)

    def column_index(self, symbol: str) -> int:
        try:
            return self.open.columns.get_loc(symbol)
        except KeyError as exc:  # pragma: no cover - guarded by callers
            raise KeyError(f"unknown symbol {symbol!r}") from exc


def _reject_frame(records: Sequence[dict]) -> pd.DataFrame:
    frame = pd.DataFrame(list(records), columns=list(REJECT_COLUMNS))
    if frame.empty:
        return frame
    frame = frame.sort_values(["decision_date", "symbol", "reason", "quantity"], kind="stable")
    return frame.reset_index(drop=True)


def build_schedule(
    orders: Iterable[Order], panel: PricePanel
) -> tuple[list[ExecutionOrder], pd.DataFrame]:
    """Validate orders and net them into one instruction per (session, symbol).

    Returns the execution orders sorted by ``(exec_index, symbol)`` plus a frame
    of rejected orders with the reason. Rejections are computed once here and are
    therefore identical for every adapter -- they are not framework artifacts.
    """

    dates = panel.dates
    n_sessions = len(dates)
    symbol_set = set(panel.symbols)
    rejected: list[dict] = []

    def reject(order: Order, reason: str) -> None:
        if reason not in _VALID_REJECT_REASONS:  # pragma: no cover - programmer guard
            raise ValueError(f"unknown rejection reason {reason!r}")
        rejected.append(
            {
                "decision_date": order.decision_date,
                "symbol": order.symbol,
                "quantity": order.quantity,
                "reason": reason,
            }
        )

    staged: dict[tuple[int, str], list[Order]] = {}
    for order in orders:
        if not isinstance(order, Order):
            raise TypeError(f"orders must be quant.backtest.Order instances, got {type(order).__name__}")
        if order.symbol not in symbol_set:
            reject(order, REJECT_UNKNOWN_SYMBOL)
            continue
        if order.quantity == 0:
            reject(order, REJECT_ZERO_QUANTITY)
            continue
        # First session strictly after the decision date. A decision made after
        # the close of day D can only trade at the open of a later session.
        exec_index = bisect.bisect_right(dates, order.decision_date)
        if exec_index >= n_sessions:
            reject(order, REJECT_NO_NEXT_SESSION)
            continue
        if exec_index == 0:
            # No session at or before the decision date exists in the panel, so
            # there is no observable prior close and Backtrader cannot submit.
            reject(order, REJECT_BEFORE_PANEL)
            continue
        staged.setdefault((exec_index, order.symbol), []).append(order)

    scheduled: list[ExecutionOrder] = []
    for (exec_index, symbol), group in sorted(staged.items()):
        net = int(sum(order.quantity for order in group))
        if net == 0:
            for order in group:
                reject(order, REJECT_NET_ZERO)
            continue
        open_price = float(panel.open.iat[exec_index, panel.column_index(symbol)])
        if not np.isfinite(open_price) or open_price <= 0:
            for order in group:
                reject(order, REJECT_BAD_OPEN_PRICE)
            continue
        scheduled.append(
            ExecutionOrder(
                exec_index=exec_index,
                exec_date=dates[exec_index],
                symbol=symbol,
                quantity=net,
                decision_dates=tuple(sorted({order.decision_date for order in group})),
            )
        )

    return scheduled, _reject_frame(rejected)


def schedule_frame(scheduled: Sequence[ExecutionOrder]) -> pd.DataFrame:
    if not scheduled:
        return pd.DataFrame(columns=list(SCHEDULE_COLUMNS))
    return pd.DataFrame([item.to_record() for item in scheduled], columns=list(SCHEDULE_COLUMNS))
