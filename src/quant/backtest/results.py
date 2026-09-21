"""Standardized backtest output and cross-framework parity comparison.

Both adapters must return the exact same schema so a P0 parity test can compare
every order and every daily account value instead of only comparing total
return. Nothing here executes trades; it only normalizes and diffs results.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Mapping, Sequence

import numpy as np
import pandas as pd

FILL_COLUMNS = ("date", "symbol", "quantity", "price", "fee")
EQUITY_COLUMNS = ("cash", "positions_value", "equity")
SCHEDULE_COLUMNS = ("decision_dates", "exec_date", "symbol", "quantity")
REJECT_COLUMNS = ("decision_date", "symbol", "quantity", "reason")

DEFAULT_RTOL = 1e-9
DEFAULT_ATOL = 1e-6


def _empty_fills() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": pd.Series(dtype="object"),
            "symbol": pd.Series(dtype="object"),
            "quantity": pd.Series(dtype="int64"),
            "price": pd.Series(dtype="float64"),
            "fee": pd.Series(dtype="float64"),
        }
    )


def _empty_rejects() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "decision_date": pd.Series(dtype="object"),
            "symbol": pd.Series(dtype="object"),
            "quantity": pd.Series(dtype="int64"),
            "reason": pd.Series(dtype="object"),
        }
    )


def normalize_fills(records: Sequence[Mapping]) -> pd.DataFrame:
    """Validate and order the canonical fill records."""

    if not records:
        return _empty_fills()
    frame = pd.DataFrame(list(records), columns=list(FILL_COLUMNS))
    frame["date"] = frame["date"].map(lambda value: value.date() if isinstance(value, dt.datetime) else value)
    frame["symbol"] = frame["symbol"].astype(str)
    frame["quantity"] = frame["quantity"].astype("int64")
    frame["price"] = frame["price"].astype("float64")
    frame["fee"] = frame["fee"].astype("float64")
    if (frame["quantity"] == 0).any():
        raise ValueError("fill records must not contain zero quantity")
    if not np.isfinite(frame[["price", "fee"]].to_numpy()).all():
        raise ValueError("fill records must contain finite price and fee")
    frame = frame.sort_values(["date", "symbol", "quantity"], kind="stable")
    return frame.reset_index(drop=True)


def normalize_rejects(records: Sequence[Mapping]) -> pd.DataFrame:
    if not records:
        return _empty_rejects()
    frame = pd.DataFrame(list(records), columns=list(REJECT_COLUMNS))
    frame["decision_date"] = frame["decision_date"].map(
        lambda value: value.date() if isinstance(value, dt.datetime) else value
    )
    frame["symbol"] = frame["symbol"].astype(str)
    frame["quantity"] = frame["quantity"].astype("int64")
    frame["reason"] = frame["reason"].astype(str)
    frame = frame.sort_values(["decision_date", "symbol", "reason", "quantity"], kind="stable")
    return frame.reset_index(drop=True)


@dataclass(frozen=True)
class BacktestResult:
    """Standardized output contract shared by vectorbt and Backtrader.

    ``fills``, ``cash``, ``positions`` and ``equity`` are reported the same way by
    both adapters so they can be compared row by row. ``rejected_orders`` holds
    the shared structural rejections plus any framework-level rejection.
    """

    framework: str
    initial_cash: float
    commission_pct: float
    dates: pd.DatetimeIndex
    symbols: tuple[str, ...]
    fills: pd.DataFrame
    scheduled_orders: pd.DataFrame
    rejected_orders: pd.DataFrame
    cash: pd.Series
    positions: pd.DataFrame
    equity: pd.DataFrame

    def __post_init__(self) -> None:
        if list(self.fills.columns) != list(FILL_COLUMNS):
            raise ValueError(f"fills columns must be {FILL_COLUMNS}, got {tuple(self.fills.columns)}")
        if list(self.rejected_orders.columns) != list(REJECT_COLUMNS):
            raise ValueError(f"rejected_orders columns must be {REJECT_COLUMNS}")
        if list(self.scheduled_orders.columns) != list(SCHEDULE_COLUMNS):
            raise ValueError(f"scheduled_orders columns must be {SCHEDULE_COLUMNS}")
        if list(self.positions.columns) != list(self.symbols):
            raise ValueError("positions columns must match panel symbols in order")
        if list(self.equity.columns) != list(EQUITY_COLUMNS):
            raise ValueError(f"equity columns must be {EQUITY_COLUMNS}")
        for name, index in (
            ("cash", self.cash.index),
            ("positions", self.positions.index),
            ("equity", self.equity.index),
        ):
            if not pd.DatetimeIndex(index).equals(pd.DatetimeIndex(self.dates)):
                raise ValueError(f"{name} index must equal the panel session index")

    @property
    def final_equity(self) -> float:
        return float(self.equity["equity"].iloc[-1])

    @property
    def total_fees(self) -> float:
        return float(self.fills["fee"].sum()) if len(self.fills) else 0.0

    def summary(self) -> dict:
        """Compact metrics for run manifests and benchmark reports."""

        buys = self.fills[self.fills["quantity"] > 0]
        sells = self.fills[self.fills["quantity"] < 0]
        buy_notional = float((buys["quantity"] * buys["price"]).sum()) if len(buys) else 0.0
        sell_notional = float((-sells["quantity"] * sells["price"]).sum()) if len(sells) else 0.0
        final_equity = self.final_equity
        return {
            "framework": self.framework,
            "n_sessions": int(len(self.dates)),
            "n_symbols": int(len(self.symbols)),
            "n_fills": int(len(self.fills)),
            "n_rejected": int(len(self.rejected_orders)),
            "n_buy_fills": int(len(buys)),
            "n_sell_fills": int(len(sells)),
            "buy_notional": buy_notional,
            "sell_notional": sell_notional,
            "turnover": buy_notional + sell_notional,
            "total_fees": self.total_fees,
            "initial_cash": float(self.initial_cash),
            "final_cash": float(self.cash.iloc[-1]),
            "final_positions_value": float(self.equity["positions_value"].iloc[-1]),
            "final_equity": final_equity,
            "total_return": final_equity / float(self.initial_cash) - 1.0,
        }


@dataclass
class ParityReport:
    """Row-level diff between two standardized results."""

    left: str
    right: str
    messages: list[str] = field(default_factory=list)
    max_abs_diff: dict[str, float] = field(default_factory=dict)
    fills_diff: pd.DataFrame = field(default_factory=pd.DataFrame)
    cash_diff: pd.DataFrame = field(default_factory=pd.DataFrame)
    positions_diff: pd.DataFrame = field(default_factory=pd.DataFrame)
    equity_diff: pd.DataFrame = field(default_factory=pd.DataFrame)
    rejected_diff: pd.DataFrame = field(default_factory=pd.DataFrame)

    @property
    def ok(self) -> bool:
        return not self.messages

    def describe(self) -> str:
        if self.ok:
            return (
                f"{self.left} == {self.right}: fills, rejected orders, daily cash, "
                f"positions and equity match (max abs diff "
                f"{max(self.max_abs_diff.values(), default=0.0):.3e})"
            )
        lines = [f"{self.left} != {self.right}:"]
        lines.extend(f"  - {message}" for message in self.messages)
        for name, diff in (
            ("fills", self.fills_diff),
            ("rejected", self.rejected_diff),
            ("cash", self.cash_diff),
            ("positions", self.positions_diff),
            ("equity", self.equity_diff),
        ):
            if len(diff):
                lines.append(f"  first {min(len(diff), 5)} of {len(diff)} {name} mismatches:")
                lines.append(diff.head(5).to_string(index=False))
        return "\n".join(lines)


def _numeric_row_diffs(left: pd.DataFrame, right: pd.DataFrame, columns: Sequence[str]) -> pd.DataFrame:
    """Return rows where any ``columns`` differ beyond tolerance (aligned frames)."""

    if not left.index.equals(right.index):
        return pd.DataFrame()
    mask = pd.Series(False, index=left.index)
    for column in columns:
        mask = mask | (~np.isclose(left[column].to_numpy(), right[column].to_numpy(), rtol=DEFAULT_RTOL, atol=DEFAULT_ATOL))
    if not mask.any():
        return pd.DataFrame()
    out = pd.DataFrame(
        {
            "date": left.index[mask],
            **{f"left_{c}": left.loc[mask, c].to_numpy() for c in columns},
            **{f"right_{c}": right.loc[mask, c].to_numpy() for c in columns},
        }
    )
    return out.reset_index(drop=True)


def _compare_fills(left: pd.DataFrame, right: pd.DataFrame, messages: list[str], max_abs_diff: dict) -> pd.DataFrame:
    if len(left) != len(right):
        messages.append(f"fill count differs: {len(left)} vs {len(right)}")
    keys = ["date", "symbol", "quantity"]
    n = min(len(left), len(right))
    mismatched = np.array([], dtype=int)
    diff = pd.DataFrame(columns=["row", *[f"left_{c}" for c in FILL_COLUMNS], *[f"right_{c}" for c in FILL_COLUMNS]])
    if n:
        left_head = left.head(n).reset_index(drop=True)
        right_head = right.head(n).reset_index(drop=True)
        key_mismatch = np.zeros(n, dtype=bool)
        for key in keys:
            key_mismatch |= left_head[key].to_numpy() != right_head[key].to_numpy()
        if key_mismatch.any():
            first_key = int(np.flatnonzero(key_mismatch)[0])
            messages.append(
                f"fill key mismatch at row {first_key}: left={left_head.loc[first_key, keys].to_dict()} "
                f"right={right_head.loc[first_key, keys].to_dict()}"
            )
        value_mismatch = np.zeros(n, dtype=bool)
        for column in ("price", "fee"):
            left_values = left_head[column].to_numpy()
            right_values = right_head[column].to_numpy()
            max_abs_diff[f"fills_{column}"] = float(np.max(np.abs(left_values - right_values)))
            value_mismatch |= ~np.isclose(left_values, right_values, rtol=DEFAULT_RTOL, atol=DEFAULT_ATOL)
        if value_mismatch.any():
            row = int(np.flatnonzero(value_mismatch)[0])
            messages.append(
                f"fill price/fee differs at row {row}: left={left_head.loc[row, ['price', 'fee']].to_dict()} "
                f"right={right_head.loc[row, ['price', 'fee']].to_dict()}"
            )
        mismatched = np.flatnonzero(key_mismatch | value_mismatch)
        diff = pd.DataFrame(
            {
                "row": mismatched,
                **{f"left_{c}": left_head.loc[mismatched, c].to_numpy() for c in FILL_COLUMNS},
                **{f"right_{c}": right_head.loc[mismatched, c].to_numpy() for c in FILL_COLUMNS},
            }
        )
    if len(left) != len(right):
        # Surface the unmatched tail so fills_diff describes the real difference.
        longer, shorter = (left, right) if len(left) > len(right) else (right, left)
        tail = longer.iloc[min(len(left), len(right)) :].reset_index(drop=True)
        side = "left" if len(left) > len(right) else "right"
        other = "right" if side == "left" else "left"
        extra = pd.DataFrame(
            {
                "row": np.arange(min(len(left), len(right)), len(longer)),
                **{f"{side}_{c}": tail[c].to_numpy() for c in FILL_COLUMNS},
                **{f"{other}_{c}": [None] * len(tail) for c in FILL_COLUMNS},
            }
        )
        extra = extra.reindex(columns=["row", *[f"left_{c}" for c in FILL_COLUMNS], *[f"right_{c}" for c in FILL_COLUMNS]])
        diff = pd.concat([diff, extra], ignore_index=True) if len(diff) else extra.reset_index(drop=True)
    return diff


def _compare_frame_pair(
    name: str,
    left: pd.DataFrame,
    right: pd.DataFrame,
    columns: Sequence[str],
    messages: list[str],
    max_abs_diff: dict,
) -> pd.DataFrame:
    if not left.index.equals(right.index):
        messages.append(f"{name} index differs ({len(left)} vs {len(right)} sessions)")
        return pd.DataFrame()
    if list(left.columns) != list(right.columns):
        messages.append(f"{name} columns differ: {list(left.columns)} vs {list(right.columns)}")
        return pd.DataFrame()
    for column in columns:
        diff = float(np.max(np.abs(left[column].to_numpy() - right[column].to_numpy()))) if len(left) else 0.0
        max_abs_diff[f"{name}_{column}"] = diff
    diff_rows = _numeric_row_diffs(left, right, columns)
    if len(diff_rows):
        first = diff_rows.iloc[0].to_dict()
        messages.append(f"{name} differs on {len(diff_rows)} of {len(left)} sessions; first mismatch: {first}")
    return diff_rows


def _compare_series(name: str, left: pd.Series, right: pd.Series, messages: list[str], max_abs_diff: dict) -> pd.DataFrame:
    return _compare_frame_pair(name, left.to_frame("value"), right.to_frame("value"), ["value"], messages, max_abs_diff)


def compare_results(
    left: BacktestResult,
    right: BacktestResult,
) -> ParityReport:
    """Compare two standardized results order by order and day by day."""

    report = ParityReport(left=left.framework, right=right.framework)

    if not pd.DatetimeIndex(left.dates).equals(pd.DatetimeIndex(right.dates)):
        report.messages.append("session index differs between frameworks")
    if tuple(left.symbols) != tuple(right.symbols):
        report.messages.append(f"symbol set differs: {left.symbols} vs {right.symbols}")
    if not np.isclose(left.initial_cash, right.initial_cash):
        report.messages.append(f"initial cash differs: {left.initial_cash} vs {right.initial_cash}")
    if not np.isclose(left.commission_pct, right.commission_pct):
        report.messages.append(f"commission differs: {left.commission_pct} vs {right.commission_pct}")

    report.fills_diff = _compare_fills(left.fills, right.fills, report.messages, report.max_abs_diff)
    report.cash_diff = _compare_series("cash", left.cash, right.cash, report.messages, report.max_abs_diff)
    report.positions_diff = _compare_frame_pair(
        "positions", left.positions, right.positions, list(left.positions.columns), report.messages, report.max_abs_diff
    )
    report.equity_diff = _compare_frame_pair(
        "equity", left.equity, right.equity, list(EQUITY_COLUMNS), report.messages, report.max_abs_diff
    )

    left_rejects = sorted(map(tuple, left.rejected_orders.to_numpy().tolist()))
    right_rejects = sorted(map(tuple, right.rejected_orders.to_numpy().tolist()))
    if left_rejects != right_rejects:
        report.messages.append(f"rejected orders differ: {len(left_rejects)} vs {len(right_rejects)}")
        report.rejected_diff = pd.concat(
            [
                left.rejected_orders.add_prefix("left_").reset_index(drop=True),
                right.rejected_orders.add_prefix("right_").reset_index(drop=True),
            ],
            axis=1,
        )

    left_schedule = sorted(map(tuple, left.scheduled_orders.to_numpy().tolist()))
    right_schedule = sorted(map(tuple, right.scheduled_orders.to_numpy().tolist()))
    if left_schedule != right_schedule:
        report.messages.append("scheduled execution orders differ between frameworks")

    # Note: max_abs_diff is informational only. Every field was already compared
    # with a combined relative/absolute tolerance above, so a large absolute diff
    # on a large account is not by itself a failure.

    # De-duplicate while preserving order so a single root cause is reported once.
    seen: set[str] = set()
    unique: list[str] = []
    for message in report.messages:
        if message not in seen:
            seen.add(message)
            unique.append(message)
    report.messages = unique
    return report


def assert_parity(left: BacktestResult, right: BacktestResult) -> ParityReport:
    report = compare_results(left, right)
    if not report.ok:
        raise AssertionError(report.describe())
    return report
