"""P0 backtest layer: one order contract, two minimal framework adapters.

The shared contract is intentionally small and lives in :mod:`quant.backtest.orders`:

* orders are signed whole-share quantities stamped with the session whose close
  the decision is known at;
* every order executes at the open of the next session (never at the price the
  decision observed);
* fills, daily cash, positions, marked-close equity and rejected orders come back
  in one standardized schema from both frameworks.

:func:`compare_results` diffs two results row by row so a P0 acceptance test can
compare every order and every daily account value instead of only total return.

P0 scope limits: this is not a full A-share broker adaptation. T+1 settlement,
price limits, suspensions, lot/odd-lot rules, historical A-share fee schedules,
corporate actions and order lifecycle/partial fills are out of scope and belong
to P1/P3.
"""

from .backtrader_adapter import run_backtrader
from .orders import (
    ORDER_COLUMNS,
    REJECT_BAD_OPEN_PRICE,
    REJECT_BEFORE_PANEL,
    REJECT_NET_ZERO,
    REJECT_NO_NEXT_SESSION,
    REJECT_UNKNOWN_SYMBOL,
    REJECT_ZERO_QUANTITY,
    REJECT_COLUMNS,
    SCHEDULE_COLUMNS,
    BacktestConfig,
    ExecutionOrder,
    Order,
    PricePanel,
    build_schedule,
    schedule_frame,
)
from .results import (
    DEFAULT_ATOL,
    DEFAULT_RTOL,
    EQUITY_COLUMNS,
    FILL_COLUMNS,
    BacktestResult,
    ParityReport,
    assert_parity,
    compare_results,
    normalize_fills,
    normalize_rejects,
)
from .vectorbt_adapter import run_vectorbt

__all__ = [
    "ORDER_COLUMNS",
    "REJECT_COLUMNS",
    "SCHEDULE_COLUMNS",
    "FILL_COLUMNS",
    "EQUITY_COLUMNS",
    "DEFAULT_RTOL",
    "DEFAULT_ATOL",
    "REJECT_UNKNOWN_SYMBOL",
    "REJECT_ZERO_QUANTITY",
    "REJECT_NO_NEXT_SESSION",
    "REJECT_BEFORE_PANEL",
    "REJECT_NET_ZERO",
    "REJECT_BAD_OPEN_PRICE",
    "BacktestConfig",
    "BacktestResult",
    "ExecutionOrder",
    "Order",
    "ParityReport",
    "PricePanel",
    "assert_parity",
    "build_schedule",
    "compare_results",
    "normalize_fills",
    "normalize_rejects",
    "run_backtrader",
    "run_vectorbt",
    "schedule_frame",
]
