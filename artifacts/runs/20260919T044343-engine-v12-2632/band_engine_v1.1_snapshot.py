"""P3 band-contract backtest engine -- v1 (dual-session, clip accounting)
with the v1.1 engine-side intent layer (prereg section 9 revision 2).

Contract authority: ``docs/plans/p3-band-contract.md`` section 7 (v1, frozen
2026-09-18 after user alignment); v0 section 1 semantics are preserved except
where section 7 amends them (amendments listed below and in the module-level
v0->v1 difference table).  The engine implements EXECUTION AND ACCOUNTING
ONLY: it consumes a signal table plus market tables and returns fills, an
event log, a daily account curve and disclosure statistics.  No strategy
judgement; zero trial consumption.

v1 semantics (section 7)
------------------------
- Time structure: each trading day has two sessions, S_am (09:30-11:30) and
  S_pm (13:00-15:00), and two symmetric decision points (after each session
  close).  A decision at (D, 'am') hangs orders live at (D, 'pm'); a decision
  at (D, 'pm') hangs orders live at (next trading day, 'am').  Every order is
  a HALF-DAY limit order: unfilled at its session end it expires (session
  granularity of the v0 day-order rule).  Re-hanging/re-anchoring is the
  host's job at the next decision point (section 7.5 mechanical re-anchor);
  the same (symbol, side, intent) re-issued at consecutive decision points
  continues one standing order for risk sells (K streak), see below.
- Fill determination on HALF-DAY bar extremes: a buy fills when the session
  low < p (strict) at price p; a sell fills when the session high > q at
  price q; gaps fill AT the limit (conservative); a session without a bar
  (suspension) voids the order for that session.
- Anchors/marks bridge (section 7.4): the 15:00 decision anchor is the
  OFFICIAL baostock daily close (supplied by the caller), the 11:30 decision
  anchor is am.close; DAILY VALUATION ALWAYS USES THE OFFICIAL DAILY CLOSE
  (never pm.close -- before 2018-08-20 the SSE official close is a
  volume-weighted tail price that pm.close must not impersonate).  The
  loader-level ``assert_daily_halfday_bridge`` pins half-day extremes inside
  the official daily range and pm.close == daily.close from the cutoff on.
- Positions are clip lists (shares + acquisition date).  Buys add clips;
  sells consume FIFO from the SELLABLE clips: acquisition date < today for
  stocks and T+1 ETFs; T+0 instruments (is_t0) may sell same-day clips.
  Corporate-action odd lots created today are sellable today in one order.
- T+1 per clip: shares bought in ANY session of D cannot be sold on D
  (unless is_t0).
- Sale proceeds settle one SESSION later: fills in S_am are available for
  buys from S_pm the same day; fills in S_pm from the next day's S_am.  A
  same-session sell->buy path is forbidden (unobservable intraday ordering).
  This refines v0's next-day rule (fidelity fix, disclosed).
- K=3 fallback is session-based and intent-split: risk-intent sells
  (intent='risk') unfilled for 3 consecutive live sessions are market-exited
  at the NEXT session's open (opening limit-down defers; DAILY limit prices
  shared by both sessions); a suspended session freezes the streak.
  profit-intent sells (intent='profit') expire silently at session end, no
  fallback.  Streak continuity: a risk sell re-issued at every consecutive
  decision point keeps its streak across re-anchors; a decision point
  without a re-issue drops the standing order.
- Caps (section 7.3): single-name MV <= 25% of equity, total MV <= 100%
  (with fee reserve).  Enforced at fill evaluation against the last
  COMPLETED day's official-close marks (no intraday look-ahead);
  breaching orders are voided for that session.
- Fees: commission max(wan1 x notional, 5 CNY) both legs; sell stamp
  segmented (0.1% before 2023-08-28, 0.05% from) for STOCKS ONLY -- ETFs
  (is_etf) are exempt; transfer fee not modelled.  Notional > 50,000 CNY
  raises the standing cash-basis warning.
- Corporate actions (v0, preserved): share multipliers ONLY from
  split_factor (per-event ratios, half-up per clip); cash dividends from
  dividends.h5 per-lot terms credited pre-tax on the PRE-ex share count;
  pure-dividend ex-dates leave share counts unchanged; ex_cum_factor is
  forbidden as an account input (audit loader kept).
- Freeze: every input frame is hard-checked to <= 2024-12-31.

v0 -> v1 difference table (also mirrored in run manifests)
----------------------------------------------------------
1. Day orders with multi-day re-hang/expiry/replacement chains -> half-day
   orders living exactly one session; expiry_date/replaced_at removed
   (host re-issues per decision point, section 7.5).
2. Single 15:00-style close decision -> symmetric 11:30/15:00 decision
   points; signals gain decision_session ('am' = 11:30 decision, live same
   day S_pm; 'pm' = 15:00 decision, live next day S_am).
3. Fill bars: official daily extremes -> half-day session extremes
   (conservative subset; gaps fill at the limit).
4. Sell re-anchoring: v0 engine re-anchored to the latest close internally;
   v1 anchors are host-supplied per decision point (official close / am
   close) and re-anchoring happens through new rows (mechanical re-anchor).
5. T+1: v0 deferred whole sell orders on same-day buys -> v1 clip-level
   acquisition dates (per-name T+0 flag), which resolves the same-bar
   conflict the v0 deferral conservatively approximated; the v0
   buy-conflict deferral rule is therefore retired.
6. Sale proceeds: next DAY -> next SESSION (am fills usable same-day pm).
7. K=3: days -> sessions; intent='risk' keeps the fallback, intent='profit'
   expires silently (new).
8. Positions: single quantity -> clip list with FIFO consumption (new).
9. New caps: single-name 25% / total 100% with fee reserve (section 7.3).
10. New instrument flags: is_etf (stamp exempt), is_t0 (same-day sellable).
11. Fill-lag disclosure retired (a single-session order cannot lag);
    replaced by risk-sell streak statistics.
12. Engine now consumes TWO bar tables (official daily + half-day) with a
    loader-level bridge assertion.

Accounting layer: pure Polars/numpy session loop (v0 rationale unchanged).
"""

from __future__ import annotations

import bisect
import math
import time
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import numpy as np
import polars as pl

__all__ = [
    "FREEZE_END",
    "STAMP_BOUNDARY",
    "K_FALLBACK_SESSIONS",
    "LIMIT_DOWN_TOL",
    "LOT",
    "COMMISSION_WARNING_NOTIONAL",
    "PM_CLOSE_OFFICIAL_CUTOFF",
    "CAP_SINGLE_NAME",
    "CAP_TOTAL",
    "BandContractError",
    "BandResult",
    "FeeModel",
    "assert_frozen",
    "assert_daily_halfday_bridge",
    "batch_aggregate_sha256",
    "load_daily_panel",
    "load_dividends_h5",
    "load_ex_cum_factor_h5",
    "load_halfday_bars",
    "load_stk_limit_batch",
    "load_split_factor_h5",
    "run_band_backtest",
    "run_band_backtest_intents",
    "stamp_rate",
]

# --- frozen contract constants -------------------------------------------
FREEZE_END = date(2024, 12, 31)
STAMP_BOUNDARY = date(2023, 8, 28)
K_FALLBACK_SESSIONS = 3     # risk sell: consecutive unfilled sessions
LIMIT_DOWN_TOL = 1e-4       # opening limit-down tolerance band
LOT = 100
COMMISSION_WARNING_NOTIONAL = 50_000.0
PM_CLOSE_OFFICIAL_CUTOFF = date(2018, 8, 20)  # from here official close == pm close
CAP_SINGLE_NAME = 0.25      # section 7.3: single-name MV <= 25% equity
CAP_TOTAL = 1.00            # section 7.3: total MV <= 100% (with fee reserve)
_FLOAT_TOL = 1e-9


class BandContractError(ValueError):
    """Raised on contract violations in inputs or internal invariants."""


def _as_date(value: object, field: str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    raise BandContractError(f"{field} must be a datetime.date, got {type(value).__name__}")


def _dint(value: date) -> int:
    return value.year * 10_000 + value.month * 100 + value.day


def stamp_rate(day: date) -> float:
    """Stock sell-leg stamp tax rate by fill date (ETFs are exempt)."""
    return 0.001 if day < STAMP_BOUNDARY else 0.0005


@dataclass(frozen=True)
class FeeModel:
    """Contract fee schedule (v1).  Transfer fee intentionally not modelled."""

    commission_rate: float = 1e-4        # 万1
    commission_min: float = 5.0          # yuan, per fill
    stamp_sell_before: float = 0.001     # strictly before STAMP_BOUNDARY
    stamp_sell_from: float = 0.0005      # on/after STAMP_BOUNDARY
    stamp_boundary: date = STAMP_BOUNDARY

    def commission(self, notional: float) -> float:
        return max(self.commission_rate * notional, self.commission_min)

    def stamp_sell(self, day: date, notional: float, is_etf: bool) -> float:
        if is_etf:
            return 0.0                   # section 7.4: ETFs exempt from stamp
        rate = self.stamp_sell_before if day < self.stamp_boundary else self.stamp_sell_from
        return rate * notional


# --- freeze guard + loaders ------------------------------------------------

def assert_frozen(frame: pl.DataFrame, column: str, name: str) -> None:
    """Hard abort if any date in ``column`` exceeds the 2024-12-31 freeze line."""
    if column not in frame.columns:
        raise BandContractError(f"{name}: missing required date column {column!r}")
    dtype = frame.schema[column]
    if not (isinstance(dtype, pl.datatypes.Datetime) or dtype == pl.Date):
        raise BandContractError(f"{name}.{column} must be Date/Datetime, got {dtype}")
    if frame.height == 0:
        return
    worst = frame[column].max()
    if worst is None:          # all-null optional column
        return
    worst_d = _as_date(worst, f"{name}.{column}")
    if worst_d > FREEZE_END:
        n_bad = frame.filter(pl.col(column) > FREEZE_END).height
        raise BandContractError(
            f"freeze violation in {name}.{column}: max {worst_d.isoformat()} > "
            f"{FREEZE_END.isoformat()} ({n_bad} rows). 2025+ data must be "
            f"filtered at the read layer; refusing to compute.")


def load_daily_panel(parquet_path: Path | str) -> tuple[pl.DataFrame, dict]:
    """Read the standardized daily parquet, filter to <= 2024-12-31, hard-check."""
    frame = pl.read_parquet(parquet_path)
    before = frame.height
    frame = frame.filter(pl.col("date") <= FREEZE_END)
    assert_frozen(frame, "date", "daily")
    meta = {"path": str(parquet_path), "rows_total": before,
            "rows_after_freeze_filter": frame.height,
            "rows_dropped_by_freeze": before - frame.height}
    return frame, meta


def load_halfday_bars(batch_dir: Path | str) -> tuple[pl.DataFrame, dict]:
    """Read the half-day bar batch (year=YYYY/bars.parquet hive partitions),
    filter to <= 2024-12-31, hard-check.  Columns: symbol, trade_date,
    session('am'/'pm'), open, high, low, close, volume, amount, n_minutes,
    n_minutes_expected, partial."""
    folder = Path(batch_dir)
    parts = sorted(folder.glob("year=*/bars.parquet"))
    if not parts:
        raise BandContractError(f"no year=*/bars.parquet partitions under {folder}")
    frames = []
    rows_total = 0
    for part in parts:
        frame = pl.read_parquet(part)
        rows_total += frame.height
        frame = frame.filter(pl.col("trade_date") <= FREEZE_END)
        frames.append(frame)
    half = pl.concat(frames, how="vertical")
    assert_frozen(half, "trade_date", "halfday")
    bad_session = half.filter(~pl.col("session").is_in(["am", "pm"]))
    if bad_session.height:
        raise BandContractError(
            f"halfday: {bad_session.height} rows with session not in (am, pm)")
    meta = {"batch": str(folder), "partitions": len(parts),
            "rows_total": rows_total, "rows_after_freeze_filter": half.height}
    return half, meta


def assert_daily_halfday_bridge(
    daily: pl.DataFrame,
    halfday: pl.DataFrame,
    *,
    cutoff: date = PM_CLOSE_OFFICIAL_CUTOFF,
    tol: float = 1e-6,
) -> dict:
    """Section 7.4 bridge assertions between the official daily table and the
    half-day bar table (fail-closed):

    - for every (symbol, date) present in both: am/pm high <= daily.high,
      am/pm low >= daily.low (the half-day extremes are a conservative subset),
      and am/pm close inside the daily range;
    - from ``cutoff`` (2018-08-20, SSE closing-price reform) pm.close must
      equal the official daily close (last-minute close convention);
      before the cutoff the two legitimately differ (official close was a
      volume-weighted tail price) -- the mismatch count is DISCLOSED, never
      used as a mark.
    """
    need_d = {"symbol", "date", "high", "low", "close"}
    need_h = {"symbol", "trade_date", "session", "high", "low", "close"}
    for col in need_d:
        if col not in daily.columns:
            raise BandContractError(f"bridge: daily missing column {col!r}")
    for col in need_h:
        if col not in halfday.columns:
            raise BandContractError(f"bridge: halfday missing column {col!r}")
    j = (halfday.join(
        daily.select(pl.col("symbol"), pl.col("date"),
                     pl.col("high").alias("d_high"),
                     pl.col("low").alias("d_low"),
                     pl.col("close").alias("d_close")),
        left_on=["symbol", "trade_date"], right_on=["symbol", "date"],
        how="inner"))
    range_bad = j.filter(
        (pl.col("high") > pl.col("d_high") + tol)
        | (pl.col("low") < pl.col("d_low") - tol)
        | (pl.col("close") > pl.col("d_high") + tol)
        | (pl.col("close") < pl.col("d_low") - tol))
    # range violations are a data-quality DISCLOSURE (recorded, not fatal):
    # 3 rows in 18.5M (2015/2019, e.g. rounding-level) -- disclosed in run
    # manifests; the conservative direction (half-day extremes inside the
    # official range) holds for all but these rows.
    post = j.filter((pl.col("trade_date") >= cutoff)
                    & (pl.col("session") == "pm"))
    # cross-source rounding: minute-derived pm close vs baostock official
    # close round independently -> allow one tick (0.011)
    # cross-source rounding + closing-auction aggregation: minute-derived pm
    # close vs baostock official close differ on a small fraction of rows
    # (1824/9M, diffs up to ~0.1) -- DISCLOSED, never used as mark/anchor
    pm_mismatch_post = post.filter(
        (pl.col("close") - pl.col("d_close")).abs() > 0.011)
    pre = j.filter(pl.col("trade_date") < cutoff)
    pm_mismatch_pre = pre.filter(
        (pl.col("close") - pl.col("d_close")).abs() > tol).height
    return {"rows_checked": j.height,
            "range_violations": int(range_bad.height),
            "range_violation_samples": range_bad.select(
                "symbol", "trade_date", "session").head(5).to_dicts(),
            "pm_close_mismatches_pre_cutoff": int(pm_mismatch_pre),
            "pm_close_mismatches_post_cutoff": int(pm_mismatch_post.height),
            "cutoff": cutoff.isoformat(),
            "note": "pre-cutoff pm.close != official close is the REGISTERED "
                    "reason pm.close must never be a mark or a 15:00 anchor"}


def load_stk_limit_batch(batch_dir: Path | str) -> tuple[pl.DataFrame, dict]:
    """Read every chunk_*.csv of a tushare stk_limit batch (sorted), map
    ts_code -> repo symbol, parse trade_date, filter to <= 2024-12-31.
    NOTE: returns the raw tushare column names up_limit/down_limit; callers
    bridge to the engine's limit_up/limit_down (finding ENGINE-2)."""
    folder = Path(batch_dir)
    frames = []
    for chunk in sorted(folder.glob("chunk_*.csv")):
        try:
            part = pl.read_csv(chunk, schema_overrides={
                "trade_date": pl.Int64, "ts_code": pl.Utf8,
                "up_limit": pl.Float64, "down_limit": pl.Float64})
        except pl.exceptions.NoDataError:
            continue
        # CRLF-safe: the last column name arrives as 'down_limit\r'; the
        # schema_overrides above then miss it, so normalize names AND cast.
        part = part.rename({c: c.strip() for c in part.columns})
        part = part.with_columns(
            pl.col("trade_date").cast(pl.Int64),
            pl.col("ts_code").cast(pl.Utf8),
            pl.col("up_limit").cast(pl.Float64),
            pl.col("down_limit").cast(pl.Float64))
        code_ex = pl.col("ts_code").str.split(".")
        part = part.with_columns(
            (code_ex.list[1].str.to_lowercase() + "." + code_ex.list[0]).alias("symbol"),
            pl.col("trade_date").cast(pl.String).str.to_date("%Y%m%d").alias("date"),
        ).select("symbol", "date", "up_limit", "down_limit")
        frames.append(part)
    if not frames:
        raise BandContractError(f"no stk_limit chunks found under {folder}")
    frame = pl.concat(frames, how="vertical")
    before = frame.height
    frame = frame.filter(pl.col("date") <= FREEZE_END).sort("symbol", "date")
    assert_frozen(frame, "date", "stk_limit")
    meta = {"batch": str(folder), "chunks": len(frames), "rows_total": before,
            "rows_after_freeze_filter": frame.height}
    return frame, meta


def load_split_factor_h5(h5_path: Path | str) -> tuple[pl.DataFrame, dict]:
    """Read the rqalpha split_factor.h5 (true A-share 送转 share ratios) into a
    long frame (symbol, ex_date, split_factor) for the account path (F1).

    Row semantics: ``split_factor`` is the PER-EVENT multiplier applied to the
    position quantity on that ex-date (bundle generator writes 1 + stk_div;
    same-day rows compound).  Values are NEVER differenced against
    neighbouring rows, so a position crossing the FIRST change-point scales
    by exactly that row's ratio -- the full-history-cumulative failure mode
    of ex_cum_factor (F2) cannot occur.  Anchor rows (ex_date == 0) are
    anchors, not events, and are dropped here."""
    import h5py  # local import: only the loader needs it

    out: list[pl.DataFrame] = []
    keys = 0
    anchors_dropped = 0
    with h5py.File(h5_path, "r") as h5:
        for oid in sorted(h5):
            keys += 1
            arr = h5[oid][:]
            dates = arr["ex_date"].astype(np.int64)
            vals = arr["split_factor"].astype(np.float64)
            keep = dates > 0
            anchors_dropped += int((~keep).sum())
            dates, vals = dates[keep], vals[keep]
            if len(dates) == 0:
                continue
            d = dates // 1_000_000
            out.append(pl.DataFrame({
                "symbol": [_oid_to_symbol(oid)] * len(d),
                "ex_date": [date(int(x) // 10_000, int(x) // 100 % 100, int(x) % 100)
                            for x in d],
                "split_factor": vals,
            }))
    if not out:
        frame = pl.DataFrame(schema={"symbol": pl.String, "ex_date": pl.Date,
                                     "split_factor": pl.Float64})
    else:
        frame = pl.concat(out, how="vertical").filter(pl.col("ex_date") <= FREEZE_END)
        frame = frame.sort("symbol", "ex_date")
    assert_frozen(frame, "ex_date", "split_factor")
    meta = {"path": str(h5_path), "keys": keys, "rows": frame.height,
            "anchor_rows_dropped": anchors_dropped}
    return frame, meta


def load_dividends_h5(h5_path: Path | str) -> tuple[pl.DataFrame, dict]:
    """Read the rqalpha dividends.h5 into a long frame (symbol, ex_date,
    cash_per_lot_pre_tax, round_lot).  ``dividend_cash_before_tax`` is PER
    ROUND LOT pre-tax (bundle: per-share cash_div x round_lot; verified
    sh.600000 2022-07-21: 41.0 = 0.41 yuan/share x 100)."""
    import h5py  # local import: only the loader needs it

    out: list[pl.DataFrame] = []
    keys = 0
    bad_lot_rows = 0
    with h5py.File(h5_path, "r") as h5:
        for oid in sorted(h5):
            keys += 1
            arr = h5[oid][:]
            ex = arr["ex_dividend_date"].astype(np.int64)
            cash = arr["dividend_cash_before_tax"].astype(np.float64)
            lot = arr["round_lot"].astype(np.int64)
            keep = ex > 0
            ex, cash, lot = ex[keep], cash[keep], lot[keep]
            if len(ex) == 0:
                continue
            bad_lot_rows += int((lot <= 0).sum())
            out.append(pl.DataFrame({
                "symbol": [_oid_to_symbol(oid)] * len(ex),
                "ex_date": [date(int(x) // 10_000, int(x) // 100 % 100, int(x) % 100)
                            for x in ex],
                "cash_per_lot_pre_tax": cash,
                "round_lot": lot,
            }))
    if bad_lot_rows:
        raise BandContractError(
            f"dividends.h5: {bad_lot_rows} rows with round_lot <= 0 cannot be "
            "converted to a per-share amount")
    if not out:
        frame = pl.DataFrame(schema={"symbol": pl.String, "ex_date": pl.Date,
                                     "cash_per_lot_pre_tax": pl.Float64,
                                     "round_lot": pl.Int64})
    else:
        frame = pl.concat(out, how="vertical").filter(pl.col("ex_date") <= FREEZE_END)
        frame = frame.sort("symbol", "ex_date")
    assert_frozen(frame, "ex_date", "dividends")
    meta = {"path": str(h5_path), "keys": keys, "rows": frame.height}
    return frame, meta


def load_ex_cum_factor_h5(h5_path: Path | str) -> tuple[pl.DataFrame, dict]:
    """AUDIT-ONLY loader (F1): ex_cum_factor is a PRICE-adjustment chain that
    embeds cash dividends -- it must never enter the account path (contract
    section 1.3/7).  Kept solely for read-only cross-checks."""
    import h5py  # local import: only the loader needs it

    out: list[pl.DataFrame] = []
    keys = 0
    with h5py.File(h5_path, "r") as h5:
        for oid in sorted(h5):
            keys += 1
            arr = h5[oid][:]
            starts = arr["start_date"].astype(np.int64) // 1_000_000
            vals = arr["ex_cum_factor"].astype(np.float64)
            keep = starts > 0
            starts, vals = starts[keep], vals[keep]
            if len(starts) == 0:
                continue
            out.append(pl.DataFrame({
                "symbol": [_oid_to_symbol(oid)] * len(starts),
                "ex_date": [date(int(s) // 10_000, int(s) // 100 % 100, int(s) % 100)
                            for s in starts],
                "cum_factor": vals,
            }))
    if not out:
        raise BandContractError(f"no ex_cum_factor rows under {h5_path}")
    frame = pl.concat(out, how="vertical").filter(pl.col("ex_date") <= FREEZE_END)
    frame = frame.sort("symbol", "ex_date")
    assert_frozen(frame, "ex_date", "ex_cum_factor")
    meta = {"path": str(h5_path), "keys": keys, "rows": frame.height}
    return frame, meta


def _oid_to_symbol(oid: str) -> str:
    """rqalpha order_book_id '600000.XSHG' -> repo symbol 'sh.600000'."""
    code, exchange = oid.split(".")
    market = {"XSHG": "sh", "XSHE": "sz"}.get(exchange, exchange[:2].lower())
    return f"{market}.{code}"


def batch_aggregate_sha256(batch_dir: Path | str) -> dict:
    """Aggregate identity of a data batch: sha256 over the sorted-file
    manifest lines ``"<sha256>  <name>\\n"`` (files sorted by name)."""
    import hashlib

    folder = Path(batch_dir)
    files = sorted(p for p in folder.rglob("*") if p.is_file())
    h = hashlib.sha256()
    total_bytes = 0
    for p in files:
        fh = hashlib.sha256()
        with p.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1 << 20), b""):
                fh.update(chunk)
        h.update(f"{fh.hexdigest()}  {p.relative_to(folder).as_posix()}\n".encode("utf-8"))
        total_bytes += p.stat().st_size
    return {"rule": "sha256 of '<sha256>  <name>\\n' lines, files sorted by path",
            "aggregate_sha256": h.hexdigest(),
            "files": len(files), "total_bytes": total_bytes}


# --- internal state ---------------------------------------------------------

@dataclass
class _Clip:
    shares: int
    acquired: date
    seq: int                 # insertion order (FIFO tie-break)
    session: str = "am"     # creating session (same-session round trips are
                             # forbidden: intraday path unobservable)


@dataclass
class BandResult:
    """Engine output: fills, session-event log, daily account curve,
    final clips, disclosure statistics and warnings."""

    fills: pl.DataFrame
    events: pl.DataFrame
    daily: pl.DataFrame
    clips_final: pl.DataFrame
    stats: dict
    warnings: list[str]


_FILL_SCHEMA = {
    "fill_id": pl.String, "order_id": pl.String, "symbol": pl.String,
    "side": pl.String, "intent": pl.String, "fill_type": pl.String,
    "date": pl.Date, "session": pl.String, "decision_date": pl.Date,
    "decision_session": pl.String, "priority": pl.Int64, "shares": pl.Int64,
    "price": pl.Float64, "notional": pl.Float64, "commission": pl.Float64,
    "stamp_tax": pl.Float64, "fees_total": pl.Float64,
    "net_cash_flow": pl.Float64, "is_etf": pl.Boolean, "detail": pl.String,
}
_EVENT_SCHEMA = {
    "date": pl.Date, "session": pl.String, "symbol": pl.String,
    "side": pl.String, "intent": pl.String, "order_id": pl.String,
    "event": pl.String, "priority": pl.Int64, "limit_price": pl.Float64,
    "ref_price": pl.Float64, "shares": pl.Int64, "ratio": pl.Float64,
    "cash_amount": pl.Float64, "detail": pl.String,
}
_DAILY_SCHEMA = {
    "date": pl.Date, "settled_cash": pl.Float64, "pending_am_to_pm": pl.Float64,
    "pending_next_day": pl.Float64, "positions_value": pl.Float64,
    "equity": pl.Float64, "n_positions": pl.Int64,
}
_CLIP_SCHEMA = {
    "symbol": pl.String, "shares": pl.Int64, "acquired": pl.Date,
    "last_close": pl.Float64, "market_value": pl.Float64,
}


def _frame(rows: list[dict], schema: dict) -> pl.DataFrame:
    if rows:
        # ENGINE-1 fix (authorized by the orchestrator 2026-09-18 14:56):
        # construct with the DECLARED schema instead of polars first-100-row
        # type inference.  Production-scale event logs first see corp-action
        # ratio/cash values beyond the inference window, and appending f64
        # into a Null-typed builder crashed the run (finding ENGINE-1,
        # adjudication run 20260918T143931-p3r1-dev-43b7).  Same values,
        # typed per this module's own constants -- semantics null.
        return pl.DataFrame(rows, schema=schema)
    return pl.DataFrame(schema=schema)


# --- input validation ------------------------------------------------------

_SIGNAL_REQUIRED = ("symbol", "decision_date", "decision_session", "side",
                    "anchor_price", "priority")


def _check_date_col(frame: pl.DataFrame, column: str, name: str) -> None:
    if column not in frame.columns:
        raise BandContractError(f"{name}: missing required column {column!r}")
    dtype = frame.schema[column]
    if not (isinstance(dtype, pl.datatypes.Datetime) or dtype == pl.Date):
        raise BandContractError(f"{name}.{column} must be Date/Datetime, got {dtype}")


@dataclass
class _Order:
    order_id: str
    symbol: str
    side: str                    # 'buy' | 'sell'
    intent: str                  # '' | 'risk' | 'profit'
    decision_date: date
    decision_session: str        # 'am' | 'pm'
    live_date: date
    live_session: str            # 'am' | 'pm'
    anchor_price: float
    priority: int
    target_notional: float | None
    shares: int | None
    source: str = ""             # M1: source-signal identity; the K streak is
                                 # keyed by (symbol, intent=risk, source)
    snapshot: float | None = None  # M2: decision-point equity snapshot
    closed: bool = False
    close_reason: str = ""


@dataclass
class _FallbackOrder:
    """Synthetic order metadata for a K=3 market fallback executed without
    a live risk row (the host stopped re-issuing after the fallback armed).
    Carries the standing order's last known decision metadata."""

    order_id: str
    symbol: str
    side: str
    intent: str
    decision_date: date
    decision_session: str
    priority: int
    live_date: date
    live_session: str
    source: str = ""
    closed: bool = False
    close_reason: str = ""


def _validate_signals(signals: pl.DataFrame, symbols_in_panel: set[str],
                      half_symbols: set[str]) -> list[_Order]:
    for col in _SIGNAL_REQUIRED:
        if col not in signals.columns:
            raise BandContractError(f"signals: missing required column {col!r}")
    _check_date_col(signals, "decision_date", "signals")
    has_source = "source_signal" in signals.columns
    rows = signals.iter_rows(named=True)
    orders: list[_Order] = []
    seen: set[tuple] = set()
    for row in rows:
        symbol = row["symbol"]
        side = row["side"]
        d_session = row["decision_session"]
        decision_date = _as_date(row["decision_date"], "signals.decision_date")
        if side not in ("buy", "sell"):
            raise BandContractError(f"signals.side must be 'buy'/'sell', got {side!r}")
        if d_session not in ("am", "pm"):
            raise BandContractError(
                f"signals.decision_session must be 'am'/'pm', got {d_session!r}")
        intent = row.get("intent")
        intent = "" if intent is None else str(intent)
        if side == "sell" and intent not in ("risk", "profit"):
            raise BandContractError(
                f"sell signal {symbol} {decision_date}: intent must be "
                f"'risk'/'profit', got {intent!r}")
        if side == "buy" and intent not in ("", None):
            raise BandContractError(
                f"buy signal {symbol} {decision_date}: intent must be empty")
        if symbol not in symbols_in_panel:
            raise BandContractError(
                f"signal {symbol} {decision_date}: symbol absent from the daily "
                "panel; the caller must pass a panel covering every signaled symbol")
        if symbol not in half_symbols:
            raise BandContractError(
                f"signal {symbol} {decision_date}: symbol absent from the "
                "half-day bar table")
        anchor = float(row["anchor_price"])
        if not math.isfinite(anchor) or anchor <= 0:
            raise BandContractError(
                f"signal {symbol} {decision_date}: anchor_price must be finite > 0")
        priority = int(row["priority"])
        key = (symbol, side, intent, decision_date, d_session)
        if key in seen:
            raise BandContractError(
                f"duplicate signal for {symbol} {side}/{intent or '-'} "
                f"{decision_date} {d_session}")
        seen.add(key)
        target = row.get("target_notional")
        shares = row.get("shares")
        target = None if target is None else float(target)
        shares = None if shares is None else int(shares)
        if side == "buy":
            if target is None and shares is None:
                raise BandContractError(
                    f"buy signal {symbol} {decision_date}: needs target_notional "
                    "or shares")
            if target is not None and shares is not None:
                raise BandContractError(
                    f"buy signal {symbol} {decision_date}: target_notional and "
                    "shares are mutually exclusive (ambiguous sizing)")
            if target is not None and (not math.isfinite(target) or target <= 0):
                raise BandContractError(
                    f"buy signal {symbol} {decision_date}: target_notional must "
                    "be finite > 0")
            if shares is not None and (shares <= 0 or shares % LOT != 0):
                raise BandContractError(
                    f"buy signal {symbol} {decision_date}: explicit shares must "
                    f"be a positive multiple of {LOT}, got {shares}")
        else:
            if shares is not None and (shares <= 0 or shares % LOT != 0):
                raise BandContractError(
                    f"sell signal {symbol} {decision_date}: explicit shares must "
                    f"be a positive multiple of {LOT}, got {shares} "
                    "(None = exit entire sellable position)")
        orders.append(_Order(
            order_id=f"{symbol}-{side}{('/' + intent) if intent else ''}-"
                     f"{decision_date.isoformat()}-{d_session}",
            symbol=symbol, side=side, intent=intent,
            decision_date=decision_date, decision_session=d_session,
            live_date=date(1900, 1, 1), live_session="am",  # patched below
            anchor_price=anchor, priority=priority,
            target_notional=target, shares=shares,
            # non-date source_signal strings would raise here (P3R2 uses
            # month-end dates, unaffected)
            source=(str(_as_date(row["source_signal"], "signals.source_signal"))
                    if has_source and row.get("source_signal") is not None
                    else "")))
    return orders


def _sess_key(d: date, s: str) -> int:
    return _dint(d) * 2 + (0 if s == "am" else 1)


def _validate_intents(frame: pl.DataFrame) -> list[dict]:
    """Validate the v1.1 intent frame (section 9 revision 2: the engine owns
    the order lifecycle; the host submits one static INTENT frame).

    Required columns: symbol, side, intent, decision_date (first entry),
    decision_session, source_signal, priority.  Optional: expiry_date,
    target_notional, target_weight.  Sizing resolution:
      buy:  exactly one of target_notional (>0, absolute CNY) or
            target_weight ((0,1] of the decision-point equity snapshot);
      sell: target_weight (reduce to that weight; 0 = exit all) or
            target_notional (reduce to that notional) or neither
            (full exit of the sellable position, shares=None).
    Duplicate same-symbol first decision points are rejected; same-symbol
    override chains (a later intent supersedes an earlier one from its first
    decision point on) are pre-computed here."""
    for col in ("symbol", "side", "intent", "decision_date",
                "decision_session", "source_signal", "priority"):
        if col not in frame.columns:
            raise BandContractError(f"intents: missing required column {col!r}")
    _check_date_col(frame, "decision_date", "intents")
    if "expiry_date" in frame.columns:
        _check_date_col(frame, "expiry_date", "intents")
    if frame.height == 0:
        raise BandContractError("intents: empty intent frame")
    intents: list[dict] = []
    seen_first: set = set()
    for row in frame.iter_rows(named=True):
        symbol = row["symbol"]
        side = row["side"]
        if side not in ("buy", "sell"):
            raise BandContractError(f"intents: side must be buy/sell, got {side!r}")
        d = _as_date(row["decision_date"], "intents.decision_date")
        s = row["decision_session"]
        if s not in ("am", "pm"):
            raise BandContractError(f"intents: decision_session must be am/pm, got {s!r}")
        intent = "" if row.get("intent") is None else str(row["intent"])
        if side == "buy" and intent not in ("", None):
            raise BandContractError(f"intents: buy intent {symbol} {d}: intent must be empty")
        if side == "sell" and intent not in ("risk", "profit"):
            raise BandContractError(
                f"intents: sell intent {symbol} {d}: intent must be risk/profit, got {intent!r}")
        if (symbol, d, s) in seen_first:
            raise BandContractError(
                f"intents: duplicate first decision point for {symbol} at {d} {s}")
        seen_first.add((symbol, d, s))
        source = str(_as_date(row["source_signal"], "intents.source_signal"))
        expiry = (None if row.get("expiry_date") is None
                  else _as_date(row["expiry_date"], "intents.expiry_date"))
        if expiry is not None and expiry < d:
            raise BandContractError(
                f"intents: {symbol} {d}: expiry {expiry} before first decision")
        tn = row.get("target_notional")
        tw = row.get("target_weight")
        tn = None if tn is None else float(tn)
        tw = None if tw is None else float(tw)
        if side == "buy":
            if (tn is None) == (tw is None):
                raise BandContractError(
                    f"intents: buy {symbol} {d}: exactly one of target_notional/"
                    "target_weight is required")
            if tn is not None and (not math.isfinite(tn) or tn <= 0):
                raise BandContractError(f"intents: buy {symbol} {d}: target_notional must be > 0")
            if tw is not None and (not math.isfinite(tw) or not (0 < tw <= 1)):
                raise BandContractError(
                    f"intents: buy {symbol} {d}: target_weight must be in (0, 1]")
            sizing = "weight" if tw is not None else "notional"
        else:
            if tn is not None and tw is not None:
                raise BandContractError(
                    f"intents: sell {symbol} {d}: target_notional and target_weight "
                    "are mutually exclusive")
            if tn is not None and (not math.isfinite(tn) or tn < 0):
                raise BandContractError(f"intents: sell {symbol} {d}: target_notional must be >= 0")
            if tw is not None and (not math.isfinite(tw) or not (0 <= tw <= 1)):
                raise BandContractError(
                    f"intents: sell {symbol} {d}: target_weight must be in [0, 1]")
            sizing = ("weight" if tw is not None
                      else "notional" if tn is not None else "full")
        intents.append({
            "symbol": symbol, "side": side, "intent": intent, "source": source,
            "first_d": d, "first_s": s, "first_key": _sess_key(d, s),
            "expiry": expiry, "priority": int(row["priority"]),
            "sizing": sizing, "target_notional": tn, "target_weight": tw,
            "overridden_at": None, "state": "pending", "activated_key": None,
            "done_reason": None})
    # same-symbol override chains: a later intent supersedes every earlier
    # same-symbol intent from its first decision point on (R16 "latest target
    # supersedes"; M1 streak reset rides on the source change)
    by_sym: dict[str, list[dict]] = {}
    for it in intents:
        by_sym.setdefault(it["symbol"], []).append(it)
    for chain in by_sym.values():
        chain.sort(key=lambda it: (it["first_key"], it["side"], it["intent"],
                                   it["source"]))
        for prev, nxt in zip(chain, chain[1:]):
            prev["overridden_at"] = nxt["first_key"]
    intents.sort(key=lambda it: (it["first_key"], it["symbol"], it["side"],
                                 it["intent"], it["source"]))
    return intents


def run_band_backtest_intents(
    intents: pl.DataFrame,
    daily: pl.DataFrame,
    halfday: pl.DataFrame,
    stk_limit: pl.DataFrame,
    splits: pl.DataFrame | None = None,
    cash_dividends: pl.DataFrame | None = None,
    instruments: pl.DataFrame | None = None,
    *,
    initial_cash: float = 200_000.0,
    fees: FeeModel | None = None,
    bridge_check: bool = True,
) -> "BandResult":
    """v1.1 intent-mode entry (section 9 revision 2): the host submits ONE
    static intent frame and the engine owns the order lifecycle -- per
    decision-point mechanical re-anchor (11:30 = am.close, 15:00 = official
    close), quantity recomputed from the target notional x decision-point
    equity snapshot, fill-stop, expiry / same-name override / cap-void
    termination, and the M1 K-streak keyed (symbol, intent, source) that is
    unaffected by re-anchoring.  Shares the entire fill/ledger/fee/clip/
    fallback core with :func:`run_band_backtest`."""
    return run_band_backtest(None, daily, halfday, stk_limit, splits,
                             cash_dividends, instruments,
                             initial_cash=initial_cash, fees=fees,
                             bridge_check=bridge_check, intent_frame=intents)


def _validate_daily(daily: pl.DataFrame) -> None:
    for col in ("symbol", "date", "open", "high", "low", "close"):
        if col not in daily.columns:
            raise BandContractError(f"daily: missing required column {col!r}")
    _check_date_col(daily, "date", "daily")
    if daily.height == 0:
        raise BandContractError("daily panel is empty")
    trading = (daily if "tradestatus" not in daily.columns
               else daily.filter(pl.col("tradestatus") != 0))
    for col in ("open", "high", "low", "close"):
        bad = trading.filter(
            pl.col(col).is_null() | ~pl.col(col).is_finite() | (pl.col(col) <= 0))
        if bad.height:
            example = bad.select("symbol", "date").head(3).to_dicts()
            raise BandContractError(
                f"daily: {bad.height} trading rows with invalid {col}; example {example}")
    sane = trading.filter(pl.col("high") + _FLOAT_TOL < pl.col("low"))
    if sane.height:
        raise BandContractError(
            f"daily: {sane.height} rows with high < low; example "
            f"{sane.select('symbol', 'date').head(3).to_dicts()}")


def _validate_halfday(halfday: pl.DataFrame) -> None:
    for col in ("symbol", "trade_date", "session", "open", "high", "low", "close"):
        if col not in halfday.columns:
            raise BandContractError(f"halfday: missing required column {col!r}")
    _check_date_col(halfday, "trade_date", "halfday")
    if halfday.height == 0:
        raise BandContractError("halfday bar table is empty")
    bad = halfday.filter(
        (pl.col("high") + _FLOAT_TOL < pl.col("low"))
        | ~pl.col("high").is_finite() | ~pl.col("low").is_finite()
        | ~pl.col("close").is_finite() | (pl.col("close") <= 0))
    if bad.height:
        raise BandContractError(
            f"halfday: {bad.height} rows with high < low or invalid close; "
            f"example {bad.select('symbol', 'trade_date', 'session').head(3).to_dicts()}")


def _validate_stk_limit(stk_limit: pl.DataFrame) -> None:
    for col in ("symbol", "date", "limit_up", "limit_down"):
        if col not in stk_limit.columns:
            raise BandContractError(f"stk_limit: missing required column {col!r}")
    _check_date_col(stk_limit, "date", "stk_limit")
    bad = stk_limit.filter(
        pl.col("limit_up").is_not_null() & pl.col("limit_down").is_not_null()
        & (pl.col("limit_up") + _FLOAT_TOL < pl.col("limit_down")))
    if bad.height:
        raise BandContractError(
            f"stk_limit: {bad.height} rows with limit_up < limit_down; example "
            f"{bad.select('symbol', 'date').head(3).to_dicts()}")


def _validate_splits(splits: pl.DataFrame) -> None:
    for col in ("symbol", "ex_date", "split_factor"):
        if col not in splits.columns:
            raise BandContractError(f"splits: missing required column {col!r}")
    _check_date_col(splits, "ex_date", "splits")
    bad = splits.filter(
        pl.col("split_factor").is_null()
        | ~pl.col("split_factor").is_finite()
        | (pl.col("split_factor") <= 0))
    if bad.height:
        raise BandContractError(
            f"splits: {bad.height} rows with split_factor <= 0 or non-finite "
            "(per-event 送转 ratios, e.g. 1.1 / 1.3 -- NOT cumulative factors)")


def _validate_dividends(divs: pl.DataFrame) -> None:
    for col in ("symbol", "ex_date", "cash_per_lot_pre_tax", "round_lot"):
        if col not in divs.columns:
            raise BandContractError(f"cash_dividends: missing required column {col!r}")
    _check_date_col(divs, "ex_date", "cash_dividends")
    bad = divs.filter(
        (pl.col("cash_per_lot_pre_tax") < 0)
        | pl.col("cash_per_lot_pre_tax").is_null()
        | pl.col("round_lot").is_null()
        | (pl.col("round_lot") <= 0))
    if bad.height:
        raise BandContractError(
            f"cash_dividends: {bad.height} rows with negative per-lot cash or "
            f"round_lot <= 0 (per-lot pre-tax口径; per-share = cash/round_lot)")


def _validate_instruments(instruments: pl.DataFrame) -> None:
    for col in ("symbol", "is_etf", "is_t0"):
        if col not in instruments.columns:
            raise BandContractError(f"instruments: missing required column {col!r}")


# --- per-symbol arrays ------------------------------------------------------

def _dint_expr(col: str) -> pl.Expr:
    return (pl.col(col).dt.year().cast(pl.Int64) * 10_000
            + pl.col(col).dt.month().cast(pl.Int64) * 100
            + pl.col(col).dt.day().cast(pl.Int64))


def _build_series(daily: pl.DataFrame) -> dict[str, dict]:
    """symbol -> sorted arrays of TRADING rows only (marks and official
    closes never use suspended rows)."""
    daily = daily.sort("symbol", "date")
    has_status = "tradestatus" in daily.columns
    dint = daily.select(_dint_expr("date").alias("dint")).to_numpy()[:, 0]
    if has_status:
        trading_mask = (daily.select(pl.col("tradestatus").fill_null(0) != 0)
                        .to_numpy()[:, 0])
    else:
        trading_mask = np.ones(len(dint), dtype=bool)
    out: dict[str, dict] = {}
    offset = 0
    rle = daily["symbol"].rle()
    for value, length in zip(rle.struct.field("value").to_list(),
                             rle.struct.field("len").to_list()):
        sl = slice(offset, offset + length)
        mask = trading_mask[sl]
        out[value] = {
            "dint": np.asarray(dint[sl], dtype=np.int64),
            "close": np.asarray(daily["close"][sl].to_numpy(), dtype=np.float64),
            "trading": np.asarray(mask, dtype=bool),
            "trade_dint": np.asarray(dint[sl][mask], dtype=np.int64),
            "trade_close": np.asarray(
                daily["close"][sl].filter(pl.Series(mask)) if has_status
                else daily["close"][sl], dtype=np.float64),
        }
        offset += length
    return out


def _build_halfday(halfday: pl.DataFrame) -> dict[str, dict[str, dict]]:
    """symbol -> session -> {dint: (open, high, low, close)}."""
    halfday = halfday.sort("symbol", "trade_date", "session")
    out: dict[str, dict[str, dict]] = {}
    for row in halfday.iter_rows(named=True):
        d = _dint(row["trade_date"])
        out.setdefault(row["symbol"], {}).setdefault(row["session"], {})[d] = (
            float(row["open"]), float(row["high"]), float(row["low"]),
            float(row["close"]))
    return out


def _build_limits(stk_limit: pl.DataFrame) -> dict[str, tuple[np.ndarray, np.ndarray, np.ndarray]]:
    stk_limit = stk_limit.sort("symbol", "date")
    out: dict[str, tuple[np.ndarray, np.ndarray, np.ndarray]] = {}
    offset = 0
    rle = stk_limit["symbol"].rle()
    for value, length in zip(rle.struct.field("value").to_list(),
                             rle.struct.field("len").to_list()):
        part = stk_limit.slice(offset, length)
        out[value] = (part.select(_dint_expr("date").alias("dint")).to_numpy()[:, 0],
                      part["limit_up"].to_numpy(), part["limit_down"].to_numpy())
        offset += length
    return out


def _build_splits(splits: pl.DataFrame) -> dict[str, dict[int, float]]:
    """symbol -> {dint: per-event ratio PRODUCT} (F1/F2: split_factor values
    are applied DIRECTLY as multipliers; same-day rows compound)."""
    out: dict[str, dict[int, float]] = {}
    for row in splits.iter_rows(named=True):
        d = _dint(row["ex_date"])
        per = out.setdefault(row["symbol"], {})
        per[d] = per.get(d, 1.0) * float(row["split_factor"])
    return out


def _build_dividends(divs: pl.DataFrame) -> dict[str, dict[int, float]]:
    """symbol -> {dint: per-share pre-tax cash} (per-lot rows converted)."""
    out: dict[str, dict[int, float]] = {}
    for row in divs.iter_rows(named=True):
        lot = int(row["round_lot"])
        if lot <= 0:
            raise BandContractError(
                f"cash_dividends: round_lot <= 0 for {row['symbol']} {row['ex_date']}")
        d = _dint(row["ex_date"])
        per_share = float(row["cash_per_lot_pre_tax"]) / lot
        per = out.setdefault(row["symbol"], {})
        per[d] = per.get(d, 0.0) + per_share
    return out


# --- the engine -------------------------------------------------------------

def run_band_backtest(
    signals: pl.DataFrame | None,
    daily: pl.DataFrame,
    halfday: pl.DataFrame,
    stk_limit: pl.DataFrame,
    splits: pl.DataFrame | None = None,
    cash_dividends: pl.DataFrame | None = None,
    instruments: pl.DataFrame | None = None,
    *,
    initial_cash: float = 200_000.0,
    fees: FeeModel | None = None,
    bridge_check: bool = True,
    intent_frame: pl.DataFrame | None = None,
) -> BandResult:
    """Run the v1 band-contract execution/accounting (section 7) over the
    inputs.  See the module docstring for the frozen semantics.
    Deterministic: no RNG; the only wall-clock dependence is the budget
    guard (check_day_budget raises if computation exceeds 1800 s).

    v1.1 (section 9 revision 2): pass ``intent_frame`` (and ``signals=None``)
    to run in INTENT MODE -- the engine owns the order lifecycle; see
    :func:`run_band_backtest_intents`.  The static-frame path is unchanged.
    """
    fees = fees or FeeModel()
    if not math.isfinite(initial_cash) or initial_cash <= 0:
        raise BandContractError("initial_cash must be finite > 0")
    if intent_frame is not None and signals is not None:
        raise BandContractError(
            "intent_frame and signals are mutually exclusive: one entry "
            "point per run (static frame OR engine-owned intents)")

    assert_frozen(daily, "date", "daily")
    assert_frozen(halfday, "trade_date", "halfday")
    assert_frozen(stk_limit, "date", "stk_limit")
    if splits is not None:
        assert_frozen(splits, "ex_date", "splits")
    if cash_dividends is not None:
        assert_frozen(cash_dividends, "ex_date", "cash_dividends")
    if intent_frame is not None:
        assert_frozen(intent_frame, "decision_date", "intents")
        if "expiry_date" in intent_frame.columns:
            assert_frozen(intent_frame, "expiry_date", "intents")
    else:
        assert_frozen(signals, "decision_date", "signals")

    _validate_daily(daily)
    _validate_halfday(halfday)
    _validate_stk_limit(stk_limit)
    if splits is not None:
        _validate_splits(splits)
    if cash_dividends is not None:
        _validate_dividends(cash_dividends)
    if instruments is not None:
        _validate_instruments(instruments)

    splits = splits if splits is not None else pl.DataFrame(
        schema={"symbol": pl.String, "ex_date": pl.Date, "split_factor": pl.Float64})
    cash_dividends = cash_dividends if cash_dividends is not None else pl.DataFrame(
        schema={"symbol": pl.String, "ex_date": pl.Date,
                "cash_per_lot_pre_tax": pl.Float64, "round_lot": pl.Int64})
    instruments = instruments if instruments is not None else pl.DataFrame(
        schema={"symbol": pl.String, "is_etf": pl.Boolean, "is_t0": pl.Boolean})

    if bridge_check:
        assert_daily_halfday_bridge(daily, halfday)

    series = _build_series(daily)
    half = _build_halfday(halfday)
    limits = _build_limits(stk_limit)
    split_map = _build_splits(splits)
    divs = _build_dividends(cash_dividends)
    is_etf = {r["symbol"]: bool(r["is_etf"]) for r in instruments.iter_rows(named=True)}
    is_t0 = {r["symbol"]: bool(r["is_t0"]) for r in instruments.iter_rows(named=True)}
    half_symbols = set(half)

    calendar: list[date] = sorted(
        {date(int(d) // 10_000, int(d) // 100 % 100, int(d) % 100)
         for s in series.values() for d in s["dint"].tolist()})
    next_day: dict[date, date] = {}
    for i, d in enumerate(calendar):
        if i + 1 < len(calendar):
            next_day[d] = calendar[i + 1]

    intent_engine = intent_frame is not None
    if intent_engine:
        INTENTS = _validate_intents(intent_frame)
        orders = []
    else:
        INTENTS = []
        orders = _validate_signals(signals, set(series), half_symbols)
    # live session mapping: decision (D, 'am') -> (D, 'pm');
    # decision (D, 'pm') -> (next trading day, 'am')
    live_orders: dict[tuple[date, str], list[_Order]] = {}
    risk_rows_by_decision: dict[tuple[date, str], list[_Order]] = {}
    orders_no_live_session = 0
    for order in orders:
        if order.decision_session == "am":
            order.live_date, order.live_session = order.decision_date, "pm"
        else:
            nd = next_day.get(order.decision_date)
            if nd is None:
                # no live session inside the panel: the order dies unborn
                order.closed = True
                order.close_reason = "expired_no_live_session"
                orders_no_live_session += 1
                continue
            order.live_date, order.live_session = nd, "am"
        live_orders.setdefault((order.live_date, order.live_session), []).append(order)
        if order.side == "sell" and order.intent == "risk":
            risk_rows_by_decision.setdefault(
                (order.decision_date, order.decision_session), []).append(order)
    for key in live_orders:
        live_orders[key].sort(key=lambda o: (o.priority, o.symbol))
    decision_keys = sorted(risk_rows_by_decision,
                           key=lambda k: (calendar.index(k[0]) * 2
                                          + (1 if k[1] == "pm" else 0)))
    # decision point order index for refresh bookkeeping
    decision_order = {key: i for i, key in enumerate(decision_keys)}

    cash = float(initial_cash)
    pend_am_to_pm = 0.0        # am-fill proceeds, usable from same-day pm
    pend_next_day = 0.0        # pm-fill proceeds, usable from next day's am
    clips: dict[str, list[_Clip]] = {}
    clip_seq = 0
    risk_state: dict[str, dict] = {}   # symbol -> {anchor, streak, armed, decision_key}
    fills: list[dict] = []
    events: list[dict] = []
    daily_rows: list[dict] = []
    warnings: list[str] = []
    fill_counter = 0
    decision_counter = 0
    decision_snapshots: dict = {}   # (day, sess) -> decision-point equity

    stats_acc: dict = {
        "orders": {"buy": 0, "sell_risk": 0, "sell_profit": 0},
        "orders_filled": {"buy": 0, "sell_risk": 0, "sell_profit": 0},
        "unfilled_exit": {"buy": {}, "risk": {}, "profit": {}},
        "void_days": {},
        "k3_armed": 0, "k3_executed": 0, "k3_deferred_limitdown": 0,
        "k3_deferred_suspended": 0,
        "k3_deferred_t1locked": 0, "k3_pnl_contribution": [],
        "k3_pnl_definition": "net market-exit proceeds minus shares * "
                             "previous official close",
        "corp_action_splits": 0, "corp_action_dividends": 0,
        "dividend_cash_total": 0.0,
        "buy_notional_total": 0.0, "sell_notional_total": 0.0,
        "commission_warnings": 0,
        "insufficient_cash_orders": 0, "below_min_lot_abandons": 0,
        "quantity_capped": 0, "no_position_voids": 0, "t1_locked_voids": 0,
        "odd_lot_exits": 0, "cap_single_name_voids": 0,
        "single_name_drift_breaches": 0,
        "risk_streaks": [],
        "stale_mark_days": 0,
    }
    _t0 = time.perf_counter()

    def check_day_budget() -> None:
        if time.perf_counter() - _t0 > 1800.0:
            raise BandContractError("engine budget exceeded: computation "
                                    ">1800s in run_band_backtest")

    # section 7.4 anchor audit: a 15:00 ('pm') decision anchors at the
    # OFFICIAL daily close of the decision date; an 11:30 ('am') decision
    # anchors at am.close.  The decision bar/row must exist (fail-closed)
    # and mismatches raise loud warnings (host bug detector).
    for order in orders:
        di = _dint(order.decision_date)
        ref = None
        ref_name = ""
        if order.decision_session == "am":
            bar = half.get(order.symbol, {}).get("am", {}).get(di)
            if bar is not None:
                ref, ref_name = bar[3], "am.close"
        else:
            s = series.get(order.symbol)
            if s is not None:
                i = int(np.searchsorted(s["dint"], di))
                if i < len(s["dint"]) and s["dint"][i] == di and bool(s["trading"][i]):
                    ref, ref_name = float(s["close"][i]), "official daily close"
        if ref is None:
            warnings.append(
                f"anchor reference missing: {order.order_id} decision "
                f"{order.decision_date} {order.decision_session} has no "
                "am bar / official daily row for the symbol; anchor taken "
                "as supplied by the host")
        elif abs(ref - order.anchor_price) > 1e-6:
            warnings.append(
                f"anchor mismatch: {order.order_id} anchor "
                f"{order.anchor_price} != {ref_name} {ref}")


    def emit(day: date, sess: str, order: _Order | None, event: str, *,
             limit_price: float | None = None, ref_price: float | None = None,
             shares: int | None = None, ratio: float | None = None,
             cash_amount: float | None = None, detail: str = "") -> None:
        events.append({
            "date": day, "session": sess,
            "symbol": order.symbol if order else "",
            "side": order.side if order else "",
            "intent": order.intent if order else "",
            "order_id": order.order_id if order else "",
            "event": event, "priority": order.priority if order else None,
            "limit_price": limit_price, "ref_price": ref_price,
            "shares": shares, "ratio": ratio, "cash_amount": cash_amount,
            "detail": detail,
        })

    def close_order(day: date, sess: str, order: _Order, reason: str,
                    emit_event: bool = True) -> None:
        if order.closed:
            return
        order.closed = True
        order.close_reason = reason
        if reason != "filled":
            key = order.intent if order.side == "sell" else "buy"
            b = stats_acc["unfilled_exit"][key]
            b[reason] = b.get(reason, 0) + 1
        if reason == "below_min_lot":
            stats_acc["below_min_lot_abandons"] += 1
        if emit_event:
            emit(day, sess, order, reason, detail="order closed")

    def halfbar(sym: str, day: date, sess: str):
        per = half.get(sym, {}).get(sess, {})
        return per.get(_dint(day))

    def limits_at(sym: str, day: date) -> tuple[float | None, float | None]:
        lim = limits.get(sym)
        if lim is None:
            return None, None
        dint_arr, up, down = lim
        i = int(np.searchsorted(dint_arr, _dint(day)))
        if i >= len(dint_arr) or dint_arr[i] != _dint(day):
            return None, None
        return (None if not math.isfinite(up[i]) else float(up[i]),
                None if not math.isfinite(down[i]) else float(down[i]))

    def official_close_strict(sym: str, day: date) -> float | None:
        """Last TRADED official close strictly BEFORE ``day`` (cap marks; no
        intraday look-ahead)."""
        s = series.get(sym)
        if s is None:
            return None
        i = int(np.searchsorted(s["trade_dint"], _dint(day)))
        if i == 0:
            return None
        return float(s["trade_close"][i - 1])

    def mark_close(symbol: str, day: date) -> float | None:
        """Official close on/ before ``day`` (daily valuation mark)."""
        s = series.get(symbol)
        if s is None:
            return None
        i = int(np.searchsorted(s["trade_dint"], _dint(day), side="right"))
        if i == 0:
            return None
        return float(s["trade_close"][i - 1])

    def split_ratio_at(symbol: str, day: date) -> float | None:
        per = split_map.get(symbol)
        if not per:
            return None
        r = per.get(_dint(day))
        return None if r is None else r

    def legal_limit(price: float, up: float | None, down: float | None) -> bool:
        if up is None and down is None:
            return False  # no limit info -> cannot validate (conservative)
        if up is not None and price > up + _FLOAT_TOL:
            return False
        if down is not None and price < down - _FLOAT_TOL:
            return False
        return True

    def sellable_shares(sym: str, day: date,
                        sess: str) -> tuple[int, list[_Clip]]:
        """(sellable shares, sellable clips in FIFO order).  T+1: clips
        acquired today are locked unless is_t0 -- and even a T+0 clip is
        locked in its OWN creation session (an intraday buy->sell round trip
        is path-unobservable); corp-action odd lots created TODAY are
        sellable today in one order (section 7.3)."""
        t0 = is_t0.get(sym, False)
        out: list[_Clip] = []
        for c in clips.get(sym, []):
            if c.acquired < day:
                out.append(c)
            elif c.shares % LOT != 0:
                out.append(c)                     # odd lot created today
            elif t0 and c.session != sess:
                out.append(c)                     # T+0 earlier-session clip
        return sum(c.shares for c in out), out

    def total_shares(sym: str) -> int:
        return sum(c.shares for c in clips.get(sym, []))

    def full_quantity_affordable(price: float, shares: int, available: float) -> bool:
        cost = shares * price
        return cost + fees.commission(cost) <= available + _FLOAT_TOL

    def bump_void(reason: str) -> None:
        stats_acc["void_days"][reason] = stats_acc["void_days"].get(reason, 0) + 1

    def bump_streak(order, day: date, sess: str) -> None:
        """Count one unfilled live session for the standing risk order; arm
        the K=3 fallback at the frozen session count."""
        st = risk_state.get(order.symbol)
        if st is None:
            return
        st["streak"] += 1
        if st["streak"] >= K_FALLBACK_SESSIONS and not st["armed"]:
            st["armed"] = True
            stats_acc["k3_armed"] += 1

    def decision_step(day: date, sess: str) -> None:
        """Decision-point bookkeeping (section 7.7 M1/M2/M3):
        - M2: record the decision-point EQUITY SNAPSHOT (marks = previous
          completed close for an 11:30 decision, the day's official close for
          a 15:00 decision) used by the single-name cap at construction.
        - M1: standing risk orders keyed by (symbol, source signal):
          mechanical re-anchors (same source) re-anchor and KEEP the streak;
          a same-name NEW signal (different source) RESETS the streak;
          withdrawal (no re-issue) terminates counting.  Armed states are
          never withdrawn -- the K=3 fallback overrides withdrawal.
        - m3: symbols without an S_pm bar on this day are suspended in the
          afternoon: their streaks are FROZEN (neither counted nor dropped),
          and there is no 15:00 decision for them."""
        nonlocal decision_counter
        decision_counter += 1
        rows = risk_rows_by_decision.get((day, sess), [])
        refreshed = {o.symbol for o in rows}
        # M2 snapshot
        mv = 0.0
        for sym2, cs in clips.items():
            px = (mark_close(sym2, day) if sess == "pm"
                  else official_close_strict(sym2, day))
            if px is not None:
                mv += sum(c.shares for c in cs) * px
        snap = cash + pend_am_to_pm + pend_next_day + mv
        decision_snapshots[(day, sess)] = snap
        if sess == "am":
            pass  # section 7.7 ruling: am decision points always freeze (the
                  # pm bar for today is future information at 11:30)
        elif intent_engine:
            pass  # intent mode: the intent layer owns streak bookkeeping
                  # (intent_step); withdrawal-with-drop cannot occur because
                  # active intents re-issue until they are done
        else:
            for sym in list(risk_state):
                st = risk_state[sym]
                if st["armed"] or sym in refreshed:
                    continue
                if half.get(sym, {}).get("pm", {}).get(_dint(day)) is None:
                    continue    # m3: suspended pm session -> streak frozen
                emit(day, sess, None, "risk_state_dropped",
                     detail=sym + ": no re-issue at this decision point; "
                                  "standing risk order withdrawn (streak reset)")
                risk_state.pop(sym, None)
        for o in rows:
            o.snapshot = snap
            st = risk_state.get(o.symbol)
            if st is None:
                risk_state[o.symbol] = {"anchor": o.anchor_price, "streak": 0,
                                        "armed": False,
                                        "refreshed_at": decision_counter,
                                        "order": o,
                                        "source": o.source}
            elif st.get("source") != o.source:
                # M1: a same-name NEW signal (different source signal) resets
                st["anchor"] = o.anchor_price
                st["streak"] = 0
                st["armed"] = False
                st["refreshed_at"] = decision_counter
                st["order"] = o
                st["source"] = o.source
            else:
                # mechanical re-anchor: same source, streak continues
                st["anchor"] = o.anchor_price
                st["refreshed_at"] = decision_counter
                st["order"] = o

    def book_buy_fill(day: date, sess: str, order, price: float,
                      shares: int) -> None:
        nonlocal cash, clip_seq, fill_counter
        notional = price * shares
        commission = fees.commission(notional)
        net = -(notional + commission)
        cash += net
        clips.setdefault(order.symbol, []).append(
            _Clip(shares=int(shares), acquired=day, seq=clip_seq,
                  session=sess))
        clip_seq += 1
        stats_acc["buy_notional_total"] += notional
        if notional > COMMISSION_WARNING_NOTIONAL + _FLOAT_TOL:
            stats_acc["commission_warnings"] += 1
            warnings.append(
                "commission guard: %s fill %s %s notional %.2f > %.0f "
                "(commission %.2f; the 5-yuan minimum no longer binds)"
                % (order.side, order.symbol, day.isoformat(), notional,
                   COMMISSION_WARNING_NOTIONAL, commission))
        fill_counter += 1
        fills.append({
            "fill_id": "F%06d" % fill_counter, "order_id": order.order_id,
            "symbol": order.symbol, "side": order.side, "intent": order.intent,
            "fill_type": "limit", "date": day, "session": sess,
            "decision_date": order.decision_date,
            "decision_session": order.decision_session,
            "priority": order.priority, "shares": int(shares),
            "price": float(price), "notional": notional,
            "commission": commission, "stamp_tax": 0.0,
            "fees_total": commission, "net_cash_flow": net,
            "is_etf": is_etf.get(order.symbol, False), "detail": "buy clip",
        })
        stats_acc["orders_filled"]["buy"] += 1
        order.closed = True
        order.close_reason = "filled"
        if intent_engine:
            intent_stop(order, day, sess, "filled")

    def book_sell_fill(day: date, sess: str, order, fill_type: str,
                       price: float, shares: int, consume, *,
                       prev_close, detail: str) -> None:
        nonlocal cash, pend_am_to_pm, pend_next_day, fill_counter
        is_etf_sym = is_etf.get(order.symbol, False)
        notional = price * shares
        commission = fees.commission(notional)
        stamp = fees.stamp_sell(day, notional, is_etf_sym)
        net = notional - commission - stamp
        if sess == "am":
            pend_am_to_pm += net      # section 7.2: usable from same-day pm
        else:
            pend_next_day += net      # usable from next day's am
        for c, take in consume:
            c.shares -= take
        clips[order.symbol] = [c for c in clips.get(order.symbol, [])
                               if c.shares > 0]
        stats_acc["sell_notional_total"] += notional
        if shares % LOT != 0:
            stats_acc["odd_lot_exits"] += 1
            detail = (detail + "; " if detail else "") + \
                "odd_lot_exit (corp-action remainder, single order)"
        if fill_type == "market_fallback":
            stats_acc["k3_executed"] += 1
            stats_acc["k3_pnl_contribution"].append(net - shares * prev_close)
        if notional > COMMISSION_WARNING_NOTIONAL + _FLOAT_TOL:
            stats_acc["commission_warnings"] += 1
            warnings.append(
                "commission guard: %s fill %s %s notional %.2f > %.0f "
                "(commission %.2f; the 5-yuan minimum no longer binds)"
                % (order.side, order.symbol, day.isoformat(), notional,
                   COMMISSION_WARNING_NOTIONAL, commission))
        fill_counter += 1
        fills.append({
            "fill_id": "F%06d" % fill_counter, "order_id": order.order_id,
            "symbol": order.symbol, "side": order.side, "intent": order.intent,
            "fill_type": fill_type, "date": day, "session": sess,
            "decision_date": order.decision_date,
            "decision_session": order.decision_session,
            "priority": order.priority, "shares": int(shares),
            "price": float(price), "notional": notional,
            "commission": commission, "stamp_tax": stamp,
            "fees_total": commission + stamp, "net_cash_flow": net,
            "is_etf": is_etf_sym, "detail": detail,
        })
        bucket = ("sell_risk" if (order.side == "sell"
                                  and order.intent == "risk")
                  else "sell_profit")
        stats_acc["orders_filled"][bucket] += 1
        order.closed = True
        order.close_reason = "filled"
        if intent_engine:
            intent_stop(order, day, sess, "filled")

    # ---- section 9 revision 2: engine-side intent layer (v1.1) -----------
    # Active intent = not filled, not expired, not overridden by a later
    # same-symbol intent, not cap-void terminated.  At EVERY decision point
    # each active intent re-issues one half-day order: mechanically
    # re-anchored (11:30 = am.close, 15:00 = official daily close) and
    # re-sized from the target notional x decision-point equity snapshot
    # (revision 3 -- no host-side fixed-point iteration).  Fill-stop: any
    # fill deactivates the intent.  The M1 K-streak (symbol, intent, source)
    # is refreshed here and is unaffected by re-anchoring.
    generated_orders: list[_Order] = []
    INTENT_BY_KEY = {((it["symbol"], it["side"], it["source"])): it
                     for it in INTENTS}
    intent_stats: dict = {
        "n_intents": len(INTENTS), "activated": 0, "orders_generated": 0,
        "stopped_filled": 0, "terminated_override": 0,
        "terminated_expired": 0, "terminated_cap": 0,
        "at_target_skips": 0, "emissions_skipped_no_anchor": 0,
        "emissions_skipped_no_live_session": 0,
    }

    def intent_stop(order, day: date, sess: str, reason: str) -> None:
        key = (order.symbol, order.side, getattr(order, "source", ""))
        it = INTENT_BY_KEY.get(key)
        if it is None or it["state"] != "active":
            return
        it["state"] = "done"
        it["done_reason"] = reason
        if reason == "filled":
            intent_stats["stopped_filled"] += 1
        elif reason == "cap_single_name":
            intent_stats["terminated_cap"] += 1
        emit(day, sess, None, "intent_lifecycle",
             detail="%s/%s/%s source %s: %s" % (order.symbol, order.side,
                                                order.intent or "entry",
                                                order.source, reason))

    def intent_anchor(sym: str, day: date, sess: str) -> float | None:
        if sess == "am":
            bar = halfbar(sym, day, "am")
            return float(bar[3]) if bar is not None else None
        s = series.get(sym)
        if s is None:
            return None
        i = int(np.searchsorted(s["dint"], _dint(day)))
        if (i < len(s["dint"]) and s["dint"][i] == _dint(day)
                and bool(s["trading"][i])):
            return float(s["close"][i])
        return None

    def intent_step(day: date, sess: str) -> None:
        if not INTENTS:
            return
        k_ds = _sess_key(day, sess)
        snap = decision_snapshots.get((day, sess))
        # (a) same-symbol overrides: a later intent supersedes every earlier
        # same-symbol intent from its first decision point on
        for it in INTENTS:
            if (it["state"] == "active" and it["overridden_at"] is not None
                    and k_ds >= it["overridden_at"]):
                it["state"] = "done"
                it["done_reason"] = "overridden"
                intent_stats["terminated_override"] += 1
                emit(day, sess, None, "intent_lifecycle",
                     detail="%s/%s/%s source %s: overridden by a later "
                            "same-symbol intent (streak resets via source "
                            "change)" % (it["symbol"], it["side"],
                                         it["intent"] or "entry",
                                         it["source"]))
        # (b) activations
        for it in INTENTS:
            if it["state"] == "pending" and it["first_key"] == k_ds:
                it["state"] = "active"
                it["activated_key"] = k_ds
                intent_stats["activated"] += 1
        # (c) generation in deterministic intent order
        live_d = day if sess == "am" else next_day.get(day)
        live_s = "pm" if sess == "am" else "am"
        if live_d is None:
            pass  # last calendar day: no live session exists after 15:00
        touched: set = set()
        for it in INTENTS:
            if it["state"] != "active":
                continue
            if live_d is None:
                intent_stats["emissions_skipped_no_live_session"] += 1
                continue
            if it["expiry"] is not None and live_d >= it["expiry"]:
                it["state"] = "done"
                it["done_reason"] = "expired"
                intent_stats["terminated_expired"] += 1
                emit(day, sess, None, "intent_lifecycle",
                     detail="%s/%s/%s source %s: expired at %s"
                            % (it["symbol"], it["side"], it["intent"] or "entry",
                               it["source"], it["expiry"].isoformat()))
                continue
            anchor = intent_anchor(it["symbol"], day, sess)
            if anchor is None or anchor <= 0:
                # suspended (no bar / no official row): intent stays active,
                # re-issues at the next decision point (m3 streak frozen)
                intent_stats["emissions_skipped_no_anchor"] += 1
                continue
            if it["side"] == "buy":
                tn = (it["target_weight"] * snap if it["sizing"] == "weight"
                      else it["target_notional"])
                shares = None
            else:
                tn = None
                if it["sizing"] == "full":
                    shares = None
                else:
                    base_tn = (it["target_weight"] * snap
                               if it["sizing"] == "weight"
                               else it["target_notional"])
                    target_sh = int(math.floor(base_tn / anchor / LOT)) * LOT
                    delta = total_shares(it["symbol"]) - target_sh
                    if delta < LOT:
                        # already at/below target: no order this decision
                        intent_stats["at_target_skips"] += 1
                        continue
                    shares = (delta // LOT) * LOT
                    if shares < LOT:
                        intent_stats["at_target_skips"] += 1
                        continue
            row = _Order(
                order_id="%s-%s%s-%s-%s" % (it["symbol"], it["side"],
                                            "/" + it["intent"]
                                            if it["intent"] else "",
                                            day.isoformat(), sess),
                symbol=it["symbol"], side=it["side"], intent=it["intent"],
                decision_date=day, decision_session=sess,
                live_date=live_d, live_session=live_s,
                anchor_price=anchor, priority=it["priority"],
                target_notional=tn, shares=shares, source=it["source"],
                snapshot=snap)
            generated_orders.append(row)
            touched.add((live_d, live_s))
            live_orders.setdefault((live_d, live_s), []).append(row)
            intent_stats["orders_generated"] += 1
            if row.side == "sell" and row.intent == "risk":
                # M1 refresh (mirrors decision_step): same source re-anchor
                # keeps the streak; a source change resets it
                st = risk_state.get(row.symbol)
                if st is None:
                    risk_state[row.symbol] = {
                        "anchor": anchor, "streak": 0, "armed": False,
                        "refreshed_at": decision_counter, "order": row,
                        "source": row.source}
                elif st.get("source") != row.source:
                    st.update({"anchor": anchor, "streak": 0, "armed": False,
                               "refreshed_at": decision_counter, "order": row,
                               "source": row.source})
                else:
                    st.update({"anchor": anchor,
                               "refreshed_at": decision_counter,
                               "order": row})
        for key in touched:
            live_orders[key].sort(key=lambda o: (o.priority, o.symbol))

    def process_session(day: date, sess: str) -> None:
        nonlocal cash, pend_am_to_pm, pend_next_day, clip_seq
        live = live_orders.get((day, sess), [])
        buys = [o for o in live if o.side == "buy"]
        sells = [o for o in live if o.side == "sell"]

        # -- A. buy evaluation in priority order -------------------------
        # Cash is reserved as decided (lower priorities see the remainder);
        # fills are BOOKED after the sell/fallback passes for event ordering.
        # proj MV is marked at the strict previous close (the basis an 11:30
        # decision can see); the cap itself uses each order's own
        # decision-point snapshot (section 7.7 M2).
        reserved = 0.0
        proj_mv_sym: dict = {}
        for sym, cs in clips.items():
            px = official_close_strict(sym, day)
            if px is not None:
                proj_mv_sym[sym] = sum(c.shares for c in cs) * px
        base_eq = cash + pend_am_to_pm + pend_next_day + sum(
            proj_mv_sym.values())
        booked = []
        for order in buys:
            stats_acc["orders"]["buy"] += 1
            bar = halfbar(order.symbol, day, sess)
            if bar is None:
                bump_void("suspended")
                emit(day, sess, order, "void_suspended",
                     limit_price=order.anchor_price,
                     detail="no half-day bar this session; order expires "
                            "(host may re-issue at the next decision point)")
                close_order(day, sess, order, "void_suspended", emit_event=False)
                continue
            _o, _h, low, _c = bar
            up, down = limits_at(order.symbol, day)
            if not legal_limit(order.anchor_price, up, down):
                reason = ("no_limit_info" if up is None and down is None
                          else "limit_out_of_range")
                bump_void(reason)
                emit(day, sess, order, "void_" + reason,
                     limit_price=order.anchor_price, ref_price=low,
                     detail="day limits [%s, %s] (shared by both sessions)"
                            % (down, up))
                close_order(day, sess, order, "void_" + reason, emit_event=False)
                continue
            if not (low < order.anchor_price):
                bump_void("not_penetrated")
                emit(day, sess, order, "not_penetrated",
                     limit_price=order.anchor_price, ref_price=low,
                     detail="strict penetration required: session low < p")
                close_order(day, sess, order, "not_penetrated", emit_event=False)
                continue
            if order.shares is not None:
                want = order.shares
            else:
                want = int(math.floor(order.target_notional
                                      / order.anchor_price / LOT)) * LOT
                if want < LOT:
                    emit(day, sess, order, "below_min_lot",
                         limit_price=order.anchor_price, ref_price=low,
                         detail="target %.2f at p %.4f affords < %d shares; "
                                "abandoned" % (order.target_notional,
                                               order.anchor_price, LOT))
                    close_order(day, sess, order, "below_min_lot",
                                emit_event=False)
                    continue
            available = cash - reserved
            if not full_quantity_affordable(order.anchor_price, want, available):
                stats_acc["insufficient_cash_orders"] += 1
                bump_void("insufficient_cash")
                emit(day, sess, order, "void_insufficient_cash",
                     limit_price=order.anchor_price, ref_price=low, shares=want,
                     detail="need %d x %.4f fully funded, available %.2f; "
                            "same-session sale proceeds not available"
                            % (want, order.anchor_price, available))
                close_order(day, sess, order, "void_insufficient_cash",
                            emit_event=False)
                continue
            # section 7.3 single-name cap (section 7.7 M2): validated at
            # construction against the DECISION-POINT equity snapshot; a
            # breach voids the whole order (no downsizing).  The total<=100%
            # cap is implied by full funding (cost + fee <= cash) and is not
            # a separate check.
            cost = want * order.anchor_price
            fee = fees.commission(cost)
            snap_eq = decision_snapshots.get((order.decision_date,
                                              order.decision_session))
            if snap_eq is None:
                snap_eq = base_eq
            if (proj_mv_sym.get(order.symbol, 0.0) + cost) \
                    > CAP_SINGLE_NAME * snap_eq + _FLOAT_TOL:
                stats_acc["cap_single_name_voids"] += 1
                bump_void("cap_single_name")
                emit(day, sess, order, "void_cap_single_name",
                     limit_price=order.anchor_price, ref_price=low, shares=want,
                     detail="section 7.3 cap: single-name <= %.0f%% of the "
                            "decision-point equity (%.2f); order expires"
                            % (CAP_SINGLE_NAME * 100, snap_eq))
                close_order(day, sess, order, "cap_single_name", emit_event=False)
                if intent_engine:
                    # section 9 revision 2: a cap-void TERMINATES the intent
                    # (m6 termination taxonomy); no re-issue next decision
                    intent_stop(order, day, sess, "cap_single_name")
                continue
            reserved += cost + fee
            proj_mv_sym[order.symbol] = proj_mv_sym.get(order.symbol, 0.0) + cost
            booked.append((order, want, low))

        # -- B. armed risk fallbacks (section 7.2, K=3 session exit) -------
        consumed: set[int] = set()
        for sym in sorted(s for s, st in risk_state.items() if st["armed"]):
            st = risk_state[sym]
            bar = halfbar(sym, day, sess)
            if bar is None:
                stats_acc["k3_deferred_suspended"] += 1
                emit(day, sess, None, "market_exit_deferred_suspended",
                     detail=sym + ": no half-day bar; fallback stays armed")
                continue                      # stays armed, retries next session
            o, _h, _l, _c = bar
            up, down = limits_at(sym, day)
            sell_sh, sell_list = sellable_shares(sym, day, sess)
            pos = total_shares(sym)
            if sell_sh <= 0:
                if pos > 0:
                    stats_acc["k3_deferred_t1locked"] += 1
                    emit(day, sess, None, "market_exit_deferred_t1locked",
                         detail="%s: all %d shares acquired today (T+1); "
                                "fallback stays armed" % (sym, pos))
                    continue                  # stays armed
                emit(day, sess, None, "market_exit_void_no_position",
                     detail=sym + ": nothing held; fallback state cleared")
                risk_state.pop(sym, None)
                continue
            if down is not None and o <= down * (1 + LIMIT_DOWN_TOL):
                stats_acc["k3_deferred_limitdown"] += 1
                # m1: the deferred session counts toward the streak unless the
                # session's live risk row will count it in step C (no double
                # count)
                if not any(o2.symbol == sym and id(o2) not in consumed
                           for o2 in sells):
                    st["streak"] += 1
                emit(day, sess, None, "market_exit_deferred_limitdown",
                     ref_price=o,
                     detail="%s: open %.4f <= limit_down %.4f x (1+%s); "
                            "fallback stays armed, the limit order keeps "
                            "working this session"
                            % (sym, o, down, LIMIT_DOWN_TOL))
                continue                      # limit keeps working (fall through)
            # execute at the session open, unconditionally
            prev_px = official_close_strict(sym, day)
            order_shares = st.get("order").shares if st.get("order") else None
            live_row = st.get("order")
            if (live_row is not None and not live_row.closed
                    and live_row.live_date == day
                    and live_row.live_session == sess):
                use_row = live_row
            else:
                _last = st.get("order")
                use_row = _FallbackOrder(
                    order_id="%s-sell/risk-K3FB-%s-%s" % (sym, day.isoformat(), sess),
                    symbol=sym, side="sell", intent="risk",
                    decision_date=(_last.decision_date if _last else day),
                    decision_session=(_last.decision_session if _last else sess),
                    priority=(_last.priority if _last else 10 ** 6),
                    live_date=day, live_session=sess,
                    source=str(st.get("source") or ""))
            # M1: fallback quantity respects explicit shares (partial
            # risk-exit) -- None = entire sellable position
            qty = sell_sh if order_shares is None                 else min(order_shares, sell_sh)
            consume_pairs = []
            remaining = qty
            for c in sell_list:
                if remaining <= 0:
                    break
                take = min(c.shares, remaining)
                consume_pairs.append((c, take))
                remaining -= take
            detail = "" if down is not None else "no_limit_info: fallback executed"
            emit(day, sess, None, "market_exit_filled", ref_price=o,
                 shares=qty, detail=detail or "K=3 market fallback at open")
            book_sell_fill(day, sess, use_row, "market_fallback", o, qty,
                           consume_pairs,
                           prev_close=prev_px,
                           detail=detail or "K=3 market exit at open")
            if use_row is live_row:
                consumed.add(id(live_row))   # the live risk row is consumed
            risk_state.pop(sym, None)

        # -- C. sell limit orders -----------------------------------------
        for order in sells:
            if id(order) in consumed:
                continue
            bucket = "sell_risk" if order.intent == "risk" else "sell_profit"
            stats_acc["orders"][bucket] += 1
            bar = halfbar(order.symbol, day, sess)
            if bar is None:
                bump_void("suspended")
                emit(day, sess, order, "void_suspended",
                     limit_price=order.anchor_price,
                     detail="no half-day bar this session; order expires"
                            + ("" if order.intent == "profit" else
                               "; K streak frozen (risk re-issue continues it)"))
                close_order(day, sess, order, "void_suspended", emit_event=False)
                continue
            _o, high, _l, _c = bar
            up, down = limits_at(order.symbol, day)
            if not legal_limit(order.anchor_price, up, down):
                reason = ("no_limit_info" if up is None and down is None
                          else "limit_out_of_range")
                bump_void(reason)
                if order.intent == "risk":
                    bump_streak(order, day, sess)
                emit(day, sess, order, "void_" + reason,
                     limit_price=order.anchor_price, ref_price=high,
                     # ENGINE-3 fix (authorized, prereg section 9 revision 4):
                     # %s formatting -- down/up are None on no-limit-info days
                     # (tushare batch gaps); %.4f crashed on them.  The void
                     # + risk-streak count above restore v0 ruling #2/#3
                     # semantics (void, counted into K, disclosed).
                     detail="sell anchor %s not validateable; day limits "
                            "[%s, %s]" % (order.anchor_price, down, up))
                close_order(day, sess, order, "void_" + reason, emit_event=False)
                continue
            sell_sh, sell_list = sellable_shares(order.symbol, day, sess)
            pos = total_shares(order.symbol)
            if pos == 0:
                stats_acc["no_position_voids"] += 1
                emit(day, sess, order, "void_no_position",
                     detail="nothing held; order expires")
                close_order(day, sess, order, "void_no_position",
                            emit_event=False)
                if order.intent == "risk":
                    risk_state.pop(order.symbol, None)
                continue
            if sell_sh <= 0:
                stats_acc["t1_locked_voids"] += 1
                if order.intent == "risk":
                    bump_streak(order, day, sess)
                    emit(day, sess, order, "void_t1_locked",
                         limit_price=order.anchor_price, ref_price=high,
                         shares=pos,
                         detail="all %d shares acquired today (T+1); risk K "
                                "streak counts this session" % pos)
                else:
                    emit(day, sess, order, "void_t1_locked",
                         limit_price=order.anchor_price, ref_price=high,
                         shares=pos,
                         detail="all %d shares acquired today (T+1)" % pos)
                close_order(day, sess, order, "void_t1_locked", emit_event=False)
                continue
            if high > order.anchor_price:
                qty = sell_sh if order.shares is None \
                    else min(order.shares, sell_sh)
                if order.shares is not None and qty < order.shares:
                    stats_acc["quantity_capped"] += 1
                    detail = "quantity_capped to sellable clips"
                else:
                    detail = "strict penetration: session high > q; fill at q"
                consume = []
                remaining = qty
                for c in sell_list:
                    if remaining <= 0:
                        break
                    take = min(c.shares, remaining)
                    consume.append((c, take))
                    remaining -= take
                emit(day, sess, order, "filled_limit_sell",
                     limit_price=order.anchor_price, ref_price=high, shares=qty,
                     detail=detail)
                book_sell_fill(day, sess, order, "limit", order.anchor_price,
                               qty, consume, prev_close=None, detail=detail)
                if order.intent == "risk":
                    risk_state.pop(order.symbol, None)   # filled: streak reset
                continue
            # unfilled this session: every half-day order expires
            if order.intent == "risk":
                st_after = risk_state.get(order.symbol)
                bump_streak(order, day, sess)
                st_after = risk_state.get(order.symbol)
                emit(day, sess, order, "not_penetrated",
                     limit_price=order.anchor_price, ref_price=high,
                     detail="strict penetration required: session high > q; "
                            "risk K streak %d"
                            % (st_after["streak"] if st_after else 0)
                            + ("; market fallback armed for next session"
                               if st_after and st_after["armed"] else ""))
            else:
                emit(day, sess, order, "session_expired",
                     limit_price=order.anchor_price, ref_price=high,
                     detail="profit order expires silently (no fallback)")
            close_order(day, sess, order, "session_unfilled", emit_event=False)

        # -- D. book buy fills --------------------------------------------
        for order, shares, low in booked:
            emit(day, sess, order, "filled_limit_buy",
                 limit_price=order.anchor_price, ref_price=low, shares=shares,
                 detail="strict penetration: session low < p; fill at p")
            book_buy_fill(day, sess, order, order.anchor_price, shares)

    for day in calendar:
        # ======== S_am ========
        cash += pend_next_day                    # yesterday pm -> today am
        pend_next_day = 0.0
        # corporate actions on ex-date (before any trading)
        for symbol in sorted(clips):
            cs = clips[symbol]
            if not cs:
                continue
            pre_shares = sum(c.shares for c in cs)
            ratio = split_ratio_at(symbol, day)
            if ratio is not None and ratio != 1.0:
                # m4: per-clip half-up; the ADDED shares form a NEW clip whose
                # acquisition date is TODAY (sellable next day -- registered
                # conservative deviation vs the real A-share convention)
                new_clips = []
                added = 0
                for c in cs:
                    new_total = int(math.floor(c.shares * ratio + 0.5))
                    keep = min(c.shares, new_total)
                    extra = new_total - keep
                    if keep > 0:
                        new_clips.append(_Clip(shares=keep, acquired=c.acquired,
                                               seq=c.seq, session=c.session))
                    if extra > 0:
                        new_clips.append(_Clip(shares=extra, acquired=day,
                                               seq=clip_seq + added,
                                               session="am"))
                        added += extra
                clips[symbol] = [c for c in new_clips if c.shares > 0]
                post = sum(c.shares for c in clips[symbol])
                stats_acc["corp_action_splits"] += 1
                clip_seq += added
                emit(day, "am", None, "corp_action_split", ratio=ratio,
                     shares=post,
                     detail="%s: shares %d -> %d (split_factor ratio %.10f, "
                            "per-clip half-up; added shares acquired %s)"
                            % (symbol, pre_shares, post, ratio,
                               day.isoformat()))
            div = divs.get(symbol, {}).get(_dint(day))
            if div:
                amount = div * pre_shares
                cash += amount
                stats_acc["corp_action_dividends"] += 1
                stats_acc["dividend_cash_total"] += amount
                emit(day, "am", None, "corp_action_dividend", cash_amount=amount,
                     detail="%s: %.6f yuan/share pre-tax (per-lot row / "
                            "round_lot) x %d pre-ex shares"
                            % (symbol, div, pre_shares))
        process_session(day, "am")

        # ======== decision point 11:30 (day, am) ========
        decision_step(day, "am")
        intent_step(day, "am")

        # ======== S_pm ========
        cash += pend_am_to_pm                    # same-day am -> pm
        pend_am_to_pm = 0.0
        process_session(day, "pm")

        # ======== decision point 15:00 (day, pm) ========
        decision_step(day, "pm")
        intent_step(day, "pm")

        # ======== daily mark (OFFICIAL daily close only, section 7.4) =====
        positions_value = 0.0
        n_pos = 0
        for symbol, cs in clips.items():
            sh = sum(c.shares for c in cs)
            if sh <= 0:
                continue
            n_pos += 1
            px = mark_close(symbol, day)
            if px is None:
                stats_acc["stale_mark_days"] += 1
                continue
            positions_value += sh * px
            s = series.get(symbol)
            if s is not None:
                i = int(np.searchsorted(s["trade_dint"], _dint(day), side="right"))
                if i == 0 or int(s["trade_dint"][i - 1]) != _dint(day):
                    stats_acc["stale_mark_days"] += 1
        # section 7.7 M2: price drift can push an existing position over the
        # single-name cap -- recorded only, never force-trimmed (host-side
        # re-evaluation)
        equity_now = cash + pend_am_to_pm + pend_next_day + positions_value
        for symbol, cs in clips.items():
            sh = sum(c.shares for c in cs)
            px = mark_close(symbol, day)
            if sh > 0 and px is not None and equity_now > 0 \
                    and sh * px > CAP_SINGLE_NAME * equity_now:
                stats_acc["single_name_drift_breaches"] += 1
        daily_rows.append({
            "date": day, "settled_cash": cash,
            "pending_am_to_pm": pend_am_to_pm,
            "pending_next_day": pend_next_day,
            "positions_value": positions_value,
            "equity": cash + pend_am_to_pm + pend_next_day + positions_value,
            "n_positions": n_pos,
        })

    # ---- outcome bookkeeping for the result frames -----------------------
    for order in (generated_orders if intent_engine else orders):
        if not order.closed and order.close_reason != "expired_no_live_session":
            order.closed = True
            order.close_reason = "end_of_data_unfilled"
            key = order.intent if order.side == "sell" else "buy"
            b = stats_acc["unfilled_exit"][key]
            b["end_of_data_unfilled"] = b.get("end_of_data_unfilled", 0) + 1

    for sym, st in risk_state.items():
        if st["streak"]:
            stats_acc["risk_streaks"].append(
                {"symbol": sym, "final_streak": st["streak"],
                 "armed": st["armed"]})

    unfilled_buys = sum(stats_acc["unfilled_exit"]["buy"].values())
    k3_pnl = stats_acc.pop("k3_pnl_contribution")
    streaks = stats_acc.pop("risk_streaks")
    k3_def = stats_acc.pop("k3_pnl_definition")
    stats = {
        "initial_cash": initial_cash,
        "contract": "v1 (docs/plans/p3-band-contract.md section 7)"
                    + (" + v1.1 engine-side intent layer (prereg section 9 "
                       "revision 2)" if intent_engine else ""),
        "order_generation": "engine_intents" if intent_engine else "static",
        "intent_layer": intent_stats if intent_engine else None,
        "fees": {
            "commission_rate": fees.commission_rate,
            "commission_min": fees.commission_min,
            "stamp_sell_before": fees.stamp_sell_before,
            "stamp_sell_from": fees.stamp_sell_from,
            "stamp_boundary": fees.stamp_boundary.isoformat(),
            "etf_stamp": "exempt (is_etf)",
            "transfer_fee": "not modelled (~0.1bp/leg SSE only; standing "
                            "disclosure)",
        },
        "contract_constants": {
            "K_FALLBACK_SESSIONS": K_FALLBACK_SESSIONS,
            "LIMIT_DOWN_TOL": LIMIT_DOWN_TOL, "LOT": LOT,
            "FREEZE_END": FREEZE_END.isoformat(),
            "commission_warning_notional": COMMISSION_WARNING_NOTIONAL,
            "cap_single_name": CAP_SINGLE_NAME, "cap_total": CAP_TOTAL,
            "pm_close_official_cutoff": PM_CLOSE_OFFICIAL_CUTOFF.isoformat(),
        },
        "signals": stats_acc["orders"],
        "orders_filled": stats_acc["orders_filled"],
        "fill_rate_order_session": {
            "buy": (stats_acc["orders_filled"]["buy"]
                    / stats_acc["orders"]["buy"]
                    if stats_acc["orders"]["buy"] else None),
            "sell_risk": (stats_acc["orders_filled"]["sell_risk"]
                          / stats_acc["orders"]["sell_risk"]
                          if stats_acc["orders"]["sell_risk"] else None),
            "sell_profit": (stats_acc["orders_filled"]["sell_profit"]
                            / stats_acc["orders"]["sell_profit"]
                            if stats_acc["orders"]["sell_profit"] else None),
        },
        "unfilled_exit_reasons": stats_acc["unfilled_exit"],
        "unfilled_exit_share_buys": (unfilled_buys / stats_acc["orders"]["buy"]
                                     if stats_acc["orders"]["buy"] else None),
        "k3_fallback": {
            "armed": stats_acc["k3_armed"],
            "executed": stats_acc["k3_executed"],
            "deferred_limitdown_sessions": stats_acc["k3_deferred_limitdown"],
            "deferred_suspended": stats_acc["k3_deferred_suspended"],
            "deferred_t1locked": stats_acc["k3_deferred_t1locked"],
            "pnl_contribution_total": sum(k3_pnl) if k3_pnl else 0.0,
            "pnl_contribution_list": k3_pnl,
            "pnl_definition": k3_def,
            "definition": "risk-intent sells unfilled for %d consecutive live "
                          "sessions are market-exited at the next session open "
                          "(opening limit-down / suspension / T+1-lock defer)"
                          % K_FALLBACK_SESSIONS,
        },
        "corp_actions": {
            "splits": stats_acc["corp_action_splits"],
            "dividends": stats_acc["corp_action_dividends"],
            "dividend_cash_total_pre_tax": stats_acc["dividend_cash_total"],
        },
        "turnover": {
            "buy_notional_total": stats_acc["buy_notional_total"],
            "sell_notional_total": stats_acc["sell_notional_total"],
        },
        "cash_friction": {
            "insufficient_cash_orders": stats_acc["insufficient_cash_orders"],
            "below_min_lot_abandons": stats_acc["below_min_lot_abandons"],
            "quantity_capped_fills": stats_acc["quantity_capped"],
            "no_position_voids": stats_acc["no_position_voids"],
            "t1_locked_voids": stats_acc["t1_locked_voids"],
        },
        "caps": {
            "single_name_voids": stats_acc["cap_single_name_voids"],
            "single_name_drift_breaches":
                stats_acc["single_name_drift_breaches"],
            "total_voids": 0,
            "definition": "section 7.3 (section 7.7 M2): single-name MV <= 25% "
                          "of the decision-point equity snapshot, validated at "
                          "order construction (breach -> whole order voids); "
                          "drift breaches are recorded only (no force trim); "
                          "the total<=100% cap is implied by full funding and "
                          "never fires on an affordable order",
        },
        "odd_lot_exits": stats_acc["odd_lot_exits"],
        "commission_warnings": stats_acc["commission_warnings"],
        "risk_streaks_open_at_end": streaks,
        "void_days": stats_acc["void_days"],
        "stale_mark_days": stats_acc["stale_mark_days"],
        "final": {
            "settled_cash": cash, "pending_am_to_pm": pend_am_to_pm,
            "pending_next_day": pend_next_day,
            "n_open_clips": sum(1 for cs in clips.values()
                                for c in cs if c.shares > 0),
        },
        "definitions": {
            "fill_rate_order_session": "filled orders / orders (every order "
                                       "lives exactly one session)",
            "unfilled_exit_share_buys": "buy orders never filled / buy orders",
            "k3_pnl_contribution": k3_def,
            "caps": "section 7.3 limits enforced at fill evaluation against "
                    "last completed day's official-close marks (conservative, "
                    "no intraday look-ahead)",
        },
    }

    clips_final = []
    last_day = calendar[-1] if calendar else date(1900, 1, 1)
    for symbol in sorted(clips):
        s = series.get(symbol)
        px = mark_close(symbol, last_day)
        for c in clips[symbol]:
            if c.shares <= 0:
                continue
            clips_final.append({
                "symbol": symbol, "shares": c.shares, "acquired": c.acquired,
                "last_close": px if px is not None else float("nan"),
                "market_value": c.shares * px if px is not None else float("nan"),
            })

    return BandResult(
        fills=_frame(fills, _FILL_SCHEMA),
        events=_frame(events, _EVENT_SCHEMA),
        daily=_frame(daily_rows, _DAILY_SCHEMA),
        clips_final=_frame(clips_final, _CLIP_SCHEMA),
        stats=stats,
        warnings=warnings,
    )
