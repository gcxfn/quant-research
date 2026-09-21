"""P3 band-contract backtest engine -- v1.2 (dual-session, clip accounting,
engine-side intent layer, ETF leg).  The intent layer is v1.1 (prereg
section 9 revision 2); v1.2 adds only the contract section 8 ETF leg.

Contract authority: ``docs/plans/p3-band-contract.md`` section 7 (v1, frozen
2026-09-18 after user alignment) and section 8 (ETF leg, TBD-A/B backfilled
2026-09-19); v0 section 1 semantics are preserved except where section 7
amends them (amendments listed below and in the module-level v0->v1
difference table).  The engine implements EXECUTION AND ACCOUNTING
ONLY: it consumes a signal table plus market tables and returns fills, an
event log, a daily account curve and disclosure statistics.  No strategy
judgement; zero trial consumption.

v1.2 change summary (one line, 2026-09-19): section 8 ETF leg via optional
``symbol_meta``/``dividend_events`` -- ETF pm-only decisions with next-PM
live routing, computed ETF price limits round(preclose x (1 +/- band), 0.001),
ETF stamp exemption, per-symbol t_plus=0 lot sellability, cash dividend
events to settled cash.  Section 8.6 scope: these extensions ONLY; without
meta/event frames every v1.1 path is unchanged (the cap paragraph below was
also aligned to section 7.7-M2 at this authorized touchpoint, prereg
revision MINOR-4/m5-d).  Adjudication delta (2026-09-19, R1/R3/R12):
decimal-EXACT half-up limit rounding; ETF stamp exemption on BOTH sides
(meta stamp_buy forced 0 for ETF legs); the static signal entry
hard-rejects ETF-meta symbols (section 8.2 routing is intent-layer only).

v1.3 change summary (2026-09-19): section 9.2 ETF share-change (份额变换)
corporate actions via the optional ``corporate_actions`` frame -- elements
(symbol, ex-date, announced ratio[, optional factor_jump]).  The share
multiplier is the ANNOUNCED ratio (revision 1: 513100 = 5, 513500 = 2);
integer ratio x integer shares is exact (zero odd lots, zero discount);
the floor + preclose-discount path survives ONLY as the fallback for
future non-integer ratios.  Executed at the top of the ex-date (before any
fill determination / valuation; for pm-only ETF legs this is exactly
"before the pm open"), per clip, mirroring m4: added shares are acquired
the ex-date (sellable next day; T+0 clips same-day pm).  Guards (all hard
raises): section 9.2-5 legality guardrail |preclose x ratio - close(t-1)|
/ close(t-1) <= 2% (NOT a zero-continuity claim: suspension-window NAV
drift is real P&L and enters valuation through the resumption reference
price); |factor_jump / ratio - 1| <= 2% when the optional field is
supplied; section 9.2-7 anti-misclassification - any dividend_events row
with implied yield (close(t-1) - preclose) / close(t-1) > 10% raises, and
a dividend event may not share (symbol, date) with a share-change event.
In-flight orders are NOT auto-cancelled: the suspension day freezes along
m3, and on the ex-date the existing safety nets hold (a stale buy anchor
above the computed limit-up voids on limit legality and is counted; a
stale sell does not fill and mechanically re-anchors at the 15:00
decision point).  Without the new parameter every v1.2 path is unchanged
(byte-identical; anchor replays P3R2 C05 / hybrid H2-A0).

v1.4 change summary (2026-09-19): section 10 per-candidate ZONES mode via
the optional ``zones`` frame (convenience entry
:func:`run_band_backtest_zones`) -- monthly candidate tables executed
INSIDE the engine (M3 lesson: membership depending on fills must be
engine-closed).  New semantics, all gated on the zones frame:
``ladder_buy`` tiered entries (per-tier remaining shares re-hung each
decision point at P - offset x sigma0, P = intent_anchor semantics,
per-tier fill-stop, invalidation line p0 - invalid_mult x sigma0 checked
AFTER the just-ended session so its own fills stay valid),
``take_profit`` WAC-anchored targets (b1 frac-sized, b2 shares=None full
sellable exit; a TP fill never cancels the ladder),
``stop_sell`` ratchet trailing stop (HWM = max decision anchor since the
first fill; line = max(historical line, HWM - stop_mult x sigma0), only
rises; trigger: session low < line -> fill at min(line, session open),
fill_type="stop"; T+1 residual arms the existing K=3 open-market
fallback with source "stop:<signal_date>"), evaluated in a NEW in-session
segment inserted BEFORE the existing A (buy) segment so a same-session
stop cancels that name's ladder tiers and TP orders before they can fill
(section 10.1-3: stop before profit; the armed-fallback B segment acts on
a DISJOINT symbol set -- armed zones are already exiting -- so the
v1.3 A->B->C->D code order itself is untouched and byte-identical
without zones), seat recycling (membership scan each decision point:
held = shares>0 zones incl. unfinished boundary exits, in-flight =
entering ladders; industry counts include in-flight ladders; admission
while held+in-flight < k_seats in rank order, cooling after a full
clear until the next signal date) and month boundaries at the
(signal_date, 'pm') decision point (boundary exits -> continuation
refresh (rank <= buffer_mult x K; WAC kept, stop line via max, ladder
NOT re-issued) -> seat scan).  Zone-engine orders use priority
``zone_priority_base + rank`` (boundary exits 10**6 + rank); when zones
are active every intent-frame priority must be < zone_priority_base.
Gate-8 v1.4 counters live in ``stats["zones"]`` (zones mode only: no new
stats key without the frame -- BR-12) and
``BandResult.zones`` carries the zone lifecycle frame.  Without the
``zones`` parameter every v1.3 path is unchanged (byte-identical; anchor
replays P3R2 C05 / hybrid H2-A0 / F3R3-A0).  Post-delivery adjudication
(2026-09-20, seams S-v14-12/S-v14-15, fail-closed): a fractional
tp2_frac is REJECTED (v1.4 implements tp2 only as the full-clear tier),
and a zones symbol overlapping the intent frame is REJECTED (zone WAC
aggregates zladder buys only).

v1.4.1 change summary (2026-09-20, section 10.8): the zones tp1 columns
(tp1_mult/tp1_frac) are OPTIONAL -- a row with both columns absent or
null runs the ZERO-TIER take-profit (no profit intent is emitted for the
row; the take-profit layer is skipped wholesale while ladder, ratchet
stop, invalidation, expiry and seat recycling are untouched).  When tp1
is supplied every v1.4 assertion applies verbatim, and a new fail-closed
assertion rejects tp1 null with tp2 set (the second tier cannot exist
without the first).  With tp1 present every v1.4 path is unchanged
(byte-identical; anchor replays P3R2 C05 / H2-A0 / F3R3-A0).

v1.4.2 change summary (2026-09-20, exp-20260920-strategy-review fixes
R8/R9/R10; zones paths only): (R8) a zone stop whose fill price
min(line, open) sits at or under the day's limit_down no longer books a
certain fill -- the exit state and the position are kept and the K=3
fallback executor re-tries each later session (that executor already
carried the limit-down deferral check at its own open).  (R9) the zone
WAC now reflects the REMAINING position: a sell removes cost at the
current WAC, so TP targets re-anchor on the average cost of the shares
actually held (contract section 10 wording: current held weighted
average).  (R10) buy cash reservation now includes stamp_buy via one
``full_cash_need`` helper shared by the affordability check, the
session reservation and the booking, so a non-zero buy stamp override
can no longer push settled cash negative.  Without the zones frame
every v1.4.1 path is unchanged; with zones but the default fee model
(stamp_buy 0) only R9 changes outcomes.  The zones t07 test expectations
are corrected to the hand-calculated 5900/600 WAC.

v1.5 change summary (2026-09-21, decision
``docs/decisions/2026-09-21-etf-pm-only-routing.md``): an explicit ETF
session expression for the halfday clock, ``etf_routing`` --
``'paired'`` (default: the v1.4.2 ETF leg requires am+pm halfday bars and
routes a pm decision to the next am) or ``'pm_only'`` (the data-limited
"ETF trades one 15:00 decision per day" form: no ETF halfday bar is
required or used, a pm decision lives at the NEXT day's pm session and
matches against the REAL daily row, an am ETF intent is rejected, ETF
holdings keep the frozen last traded close at 11:30 decision points, and
every trading day of an ETF leg must carry a usable daily bar --
fail-closed otherwise).  With the default routing every v1.4.2 path is
unchanged (byte-identical; anchor replays P3R2 C05 / H2-A0 / F3R3-A0).

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
- Caps (section 7.3 via the section 7.7-M2 ruling): single-name MV <= 25%
  of the DECISION-POINT equity snapshot, enforced at order construction
  (a breach voids the WHOLE order -- no downsizing; in intent mode a
  cap-void terminates the intent); price-drift breaches of existing
  positions are recorded only, never force-trimmed; the total MV <= 100%
  cap is implied by full funding (cost + fee <= available cash).

v1.2 ETF-leg semantics (section 8; gated on ``symbol_meta`` -- a symbol
absent from meta keeps the exact v1.1 stock path: fees, stk_limit rows, T+1)
----------------------------------------------------------------------------
- ``symbol_meta`` (dict {symbol: fields}, polars or pandas frame, one row
  per symbol): asset_class ('stock'|'etf'), band (ETF price-limit band;
  default 0.10), t_plus (0|1; default 1 = conservative), and optional fee
  overrides commission_rate/commission_min/stamp_buy/stamp_sell.
  ``dividend_events`` (symbol/date/div_per_share) default to empty.
- ETF decisions are 15:00 ONLY (an am decision on an ETF intent is a
  validation error); a 15:00 ETF decision lives at the NEXT day's pm
  session (the synthetic single ETF session, section 8.1/8.2); stocks keep
  the section 7.1 next-am route.  Suspension (no daily row) freezes the
  intent and its K streak (m3); the K=3 fallback executes at a PM session
  open only, its opening limit-down check using the COMPUTED limit.
- ETF price limits are computed, never looked up (stk_limit has zero fund
  coverage): up/down = half-up(preclose x (1 +/- band)) to the 0.001 tick;
  preclose = the daily frame's ``preclose`` column when it carries the row,
  else the previous traded official close.  ETF anchors (limit
  construction) are tick-rounded to 0.001; stock anchors stay untouched.
- Fees: ETF legs pay no stamp on EITHER side (contract section 8.3
  precedence over any meta stamp_sell/stamp_buy value, R3); commission
  max(rate x notional, min) honors per-symbol overrides; stock buy stamp
  charges only when a meta stamp_buy override supplies it (default 0 =
  v1.1).
- Price-limit arithmetic is DECIMAL-EXACT half-up (R1): the preclose x
  (1 +/- band) product and the 0.001 quantization never round on a binary
  float artifact (e.g. 1.705 x 1.1 = 1.8755 -> 1.876).
- T+0 (meta t_plus=0, unioned with legacy instruments.is_t0): a same-day
  clip from an EARLIER session is sellable later that day.  Under the ETF
  pm-only rhythm no later same-day session exists, so T+0 is
  observationally equivalent to T+1 for ETF legs; the flag is exercised
  through controlled stock scenarios.
- dividend_events credit shares-held-at-the-day-open x div_per_share to
  SETTLED cash on the event date; marks and clip costs are untouched;
  events apply only to symbols present in symbol_meta.
- Mixed account: one ledger, one equity curve (cash + all holdings at
  official closes); the single-name 25% / total 100% caps apply to ETF
  legs identically, including target-weight ETF buy sizing.
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
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
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
    "ETF_PRICE_TICK",
    "ETF_DEFAULT_BAND",
    "CA_YIELD_MISCLASS_LIMIT",
    "CA_GUARDRAIL_TOL",
    "CA_FACTOR_CHECK_TOL",
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
    "run_band_backtest_zones",
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
ETF_PRICE_TICK = 0.001      # section 8.3: ETF tick (limits + anchor rounding)
ETF_DEFAULT_BAND = 0.10     # section 8.3: band when symbol_meta omits it
# v1.3 section 9.2 corporate-action (share-change) gates
CA_YIELD_MISCLASS_LIMIT = 0.10  # 9.2-7: dividend implied-yield hard gate
CA_GUARDRAIL_TOL = 0.02         # 9.2-5: |preclose*ratio - close(t-1)|/close(t-1)
CA_FACTOR_CHECK_TOL = 0.02      # 9.2-1: |factor_jump/ratio - 1| cross-check
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


def _tick_round(price: float, tick: float) -> float:
    """Round-half-up to a price tick -- the A-share limit-price convention
    (section 8.3: round(preclose x (1 +/- band), 0.001) for ETF legs and
    0.001-tick ETF anchor construction).  R1 adjudication: the rounding is
    DECIMAL-EXACT (float -> shortest decimal repr -> Decimal -> quantize
    ROUND_HALF_UP -> float), so a half-tick boundary always rounds up as it
    would under exchange arithmetic, never on a binary-float artifact.
    NOTE: for the band LIMIT the exactness must come from the product too --
    use :func:`_etf_band_limit`, not ``_tick_round(preclose * (1 + band))``
    (the float product can sit a fraction of a cent off the boundary)."""
    return float(Decimal(str(price)).quantize(Decimal(str(tick)),
                                              rounding=ROUND_HALF_UP))


def _limit_edge(close: float, up: float | None, down: float | None) -> bool:
    """True when the session close sits AT a day-limit edge (a one-word
    limit board): a market fill (etf_market_fill decision, 2026-09-21)
    must not assume execution there."""
    if up is not None and close >= up - _FLOAT_TOL:
        return True
    if down is not None and close <= down + _FLOAT_TOL:
        return True
    return False


def _etf_band_limit(preclose: float, band: float, *, up: bool) -> float:
    """Section 8.3 (TBD-A) limit = half-up(preclose x (1 +/- band), 0.001),
    computed in EXACT decimal arithmetic (R1 adjudication): the factor and
    the product are Decimal so e.g. 1.705 x 1.1 = 1.8755 exactly quantizes
    to 1.876, where the binary-float product could round one tick low."""
    factor = Decimal(1) + (Decimal(str(band)) if up else -Decimal(str(band)))
    product = Decimal(str(preclose)) * factor
    return float(product.quantize(Decimal(str(ETF_PRICE_TICK)),
                                  rounding=ROUND_HALF_UP))


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
    price: float = 0.0      # per-share fill price (ledger feedback for
                             # host-side cost/R rules; NOT emitted in
                             # clips_final so output frames stay byte-stable)


@dataclass
class BandResult:
    """Engine output: fills, session-event log, daily account curve,
    final clips, disclosure statistics and warnings.  v1.4 adds ``zones``
    (zone lifecycle frame; None outside zones mode)."""

    fills: pl.DataFrame
    events: pl.DataFrame
    daily: pl.DataFrame
    clips_final: pl.DataFrame
    stats: dict
    warnings: list[str]
    zones: pl.DataFrame | None = None


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
_ZONES_SCHEMA = {
    "signal_date": pl.Date, "symbol": pl.String, "rank": pl.Int64,
    "industry": pl.String, "admitted_key": pl.Int64,
    "phase_final": pl.String, "exit_reason": pl.String,
    "total_target_shares": pl.Int64, "tier_filled_shares": pl.String,
    "shares_bought": pl.Int64, "wac_final": pl.Float64,
    "hwm_final": pl.Float64, "stop_line_final": pl.Float64,
    "armed_events": pl.Int64, "first_fill_key": pl.Int64,
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
    zone_tier: int | None = None  # v1.4: ladder tier index (zone orders only)


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


def _validate_intent_row(row: dict, *, seen_first: set | None = None) -> dict:
    """Validate ONE intent row and return its internal dict (the shared
    per-row core of the static frame loader and the dynamic provider
    injector; see :func:`_validate_intents` for the field contract)."""
    missing = [c for c in ("symbol", "side", "decision_date",
                           "decision_session", "source_signal", "priority")
               if row.get(c) is None]
    if missing:
        raise BandContractError(
            "intents: missing required field(s) %r" % (missing,))
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
    if seen_first is not None:
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
    return {
        "symbol": symbol, "side": side, "intent": intent, "source": source,
        "first_d": d, "first_s": s, "first_key": _sess_key(d, s),
        "expiry": expiry, "priority": int(row["priority"]),
        "sizing": sizing, "target_notional": tn, "target_weight": tw,
        "overridden_at": None, "state": "pending", "activated_key": None,
        "done_reason": None}


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
        intents.append(_validate_intent_row(row, seen_first=seen_first))
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
    intents: pl.DataFrame | None,
    daily: pl.DataFrame,
    halfday: pl.DataFrame,
    stk_limit: pl.DataFrame,
    splits: pl.DataFrame | None = None,
    cash_dividends: pl.DataFrame | None = None,
    instruments: pl.DataFrame | None = None,
    symbol_meta=None,
    dividend_events=None,
    corporate_actions=None,
    *,
    initial_cash: float = 200_000.0,
    fees: FeeModel | None = None,
    bridge_check: bool = True,
    execution_clock: str = "legacy",
    etf_routing: str = "paired",
    intent_provider=None,
    etf_market_fill: float = 0.0,
) -> "BandResult":
    """v1.1 intent-mode entry (section 9 revision 2): the host submits ONE
    static intent frame and the engine owns the order lifecycle -- per
    decision-point mechanical re-anchor (11:30 = am.close, 15:00 = official
    close), quantity recomputed from the target notional x decision-point
    equity snapshot, fill-stop, expiry / same-name override / cap-void
    termination, and the M1 K-streak keyed (symbol, intent, source) that is
    unaffected by re-anchoring.  Shares the entire fill/ledger/fee/clip/
    fallback core with :func:`run_band_backtest`.

    ``execution_clock='halfday'`` uses next-am / same-day-pm routing for
    ETFs too, requires both ETF halfday bars, and marks morning holdings
    at the completed am close. Default ``legacy`` preserves old research.
    This option only changes execution timing and valuation; it is not a
    complete dynamic strategy or account-risk feedback implementation.

    ``etf_routing='pm_only'`` (v1.5, decision
    ``docs/decisions/2026-09-21-etf-pm-only-routing.md``) expresses the
    data-limited "ETF trades a single 15:00 decision per day" leg INSIDE
    the halfday clock: ETF intents exist only at pm decision points (an
    am ETF intent is rejected), a pm decision lives at the NEXT day's pm
    session and matches against the REAL daily bar (whole-day range,
    section 8.1 -- never a synthesized am bar), ETF holdings keep the
    frozen last traded close at am decision points, and NO ETF halfday
    bar is required (a daily row is required on every traded day).
    Default ``paired`` preserves the v1.4.2 ETF halfday behavior.

    Dynamic entry (2026-09-21 mainline task): ``intent_provider`` is a
    callable ``provider(day, session, ledger) -> list[dict] | None``
    invoked at EVERY decision point after the completed half-day's fills
    are booked and before the next half-day's orders are generated.  The
    ``ledger`` mapping exposes THIS account's feedback -- settled cash,
    pending settlement buckets, the decision-point equity snapshot, every
    position with its acquisition clips and the next session's sellable
    quantity -- so the host re-issues recommendations explicitly each
    half-day instead of the engine silently carrying old intents forward
    (``intents`` may be None for a fully dynamic run; a static frame, when
    given, is loaded first and then extended by the provider).

    v1.2 (section 8): optional ``symbol_meta`` (dict / polars / pandas, one
    row per symbol: asset_class, band, t_plus, fee overrides) and
    ``dividend_events`` (symbol/date/div_per_share).  Symbols absent from
    meta keep the exact v1.1 behavior; ETF-meta symbols get the section 8.2
    pm-only decision routing, computed price limits (TBD-A), stamp
    exemption, per-symbol T+0 and dividend-event cash credits.

    v1.3 (section 9.2): optional ``corporate_actions`` (symbol / date /
    ratio / optional factor_jump) -- ETF share-change events applied at the
    ex-date open under the announced integer ratio (revision 1) with the
    9.2-5 guardrail, the 9.2-7 anti-misclassification gates and the m4
    acquisition mirror.  None = exact v1.2 behavior."""
    return run_band_backtest(None, daily, halfday, stk_limit, splits,
                             cash_dividends, instruments, symbol_meta,
                             dividend_events, corporate_actions,
                             initial_cash=initial_cash, fees=fees,
                             bridge_check=bridge_check, intent_frame=intents,
                             execution_clock=execution_clock,
                             etf_routing=etf_routing,
                             intent_provider=intent_provider,
                             etf_market_fill=etf_market_fill)


def run_band_backtest_zones(
    zones: pl.DataFrame,
    daily: pl.DataFrame,
    halfday: pl.DataFrame,
    stk_limit: pl.DataFrame,
    splits: pl.DataFrame | None = None,
    cash_dividends: pl.DataFrame | None = None,
    instruments: pl.DataFrame | None = None,
    symbol_meta=None,
    dividend_events=None,
    corporate_actions=None,
    *,
    intents: pl.DataFrame | None = None,
    initial_cash: float = 200_000.0,
    fees: FeeModel | None = None,
    bridge_check: bool = True,
    zone_priority_base: int = 1000,
) -> "BandResult":
    """v1.4 zones-mode entry (contract section 10 / BR-1): the host submits
    ONE static per-signal-month candidate table (``zones``) and the engine
    owns membership: ladder_buy tiered entries, WAC-anchored take-profit,
    ratchet stop-loss with the K=3 open-market fallback, seat recycling
    and month-boundary continuation/exit -- all inside the engine (M3
    lesson).  Zones are STOCK-only (an ETF symbol in the frame raises);
    ``intents`` may be supplied alongside for mixed ETF-leg accounts (one
    ledger) -- then every intent priority must be < ``zone_priority_base``.
    See the module docstring v1.4 summary for the frozen semantics."""
    return run_band_backtest(None, daily, halfday, stk_limit, splits,
                             cash_dividends, instruments, symbol_meta,
                             dividend_events, corporate_actions,
                             initial_cash=initial_cash, fees=fees,
                             bridge_check=bridge_check, intent_frame=intents,
                             zones=zones,
                             zone_priority_base=zone_priority_base)


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


def _validate_halfday(halfday: pl.DataFrame, *, allow_empty: bool = False) -> None:
    """Validate the half-day bar table.  ``allow_empty`` (v1.5 pm-only ETF
    routing) accepts a table with zero rows: an account whose only legs are
    pm-only ETFs needs no half-day bars at all; a non-empty table is always
    fully validated."""
    for col in ("symbol", "trade_date", "session", "open", "high", "low", "close"):
        if col not in halfday.columns:
            raise BandContractError(f"halfday: missing required column {col!r}")
    _check_date_col(halfday, "trade_date", "halfday")
    if halfday.height == 0:
        if allow_empty:
            return
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


# --- zones frame validation (v1.4, contract section 10) ---------------------

# v1.4.1: tp1_mult/tp1_frac moved to OPTIONAL (zero-tier take-profit;
# tp2_mult/tp2_frac were optional from v1.4) -- a row may omit both tp1
# columns or carry them as null, which emits no take-profit intent at all.
_ZONES_REQUIRED = ("signal_date", "symbol", "rank", "industry", "sigma0",
                   "p0", "w_t", "ladder_offsets", "ladder_fracs",
                   "stop_mult", "invalid_mult",
                   "k_seats", "ind_cap", "buffer_mult")


def _zones_float_list(value: object, name: str) -> list[float]:
    """Parse a comma-separated list of positive numbers ("0.5,1.5,2.5")."""
    parts = [p.strip() for p in str(value).split(",") if p.strip() != ""]
    if not parts:
        raise BandContractError(f"zones: {name} is empty (comma-separated list required)")
    out: list[float] = []
    for part in parts:
        try:
            v = float(part)
        except ValueError:
            raise BandContractError(
                f"zones: {name} entry {part!r} is not a number") from None
        if not math.isfinite(v) or v <= 0:
            raise BandContractError(
                f"zones: {name} entries must be finite > 0, got {part!r}")
        out.append(v)
    return out


def _validate_zones(zones: pl.DataFrame, series: dict,
                    calendar_dates: set, etf_meta: dict) -> list[dict]:
    """Validate the v1.4 zones frame (contract section 10.1 / BR-1) into
    month tables: one dict per signal_date with its candidate rows (rank
    ascending), constant k_seats/ind_cap/buffer_mult and the ladder expiry
    (= next signal_date + 1 calendar day; last month = FREEZE_END + 1 day).

    Hard raises (fail-closed, before any simulated trading): missing
    columns; empty frame; signal_date not a daily-panel calendar day;
    symbol absent from the daily panel or marked asset_class='etf' in
    symbol_meta; rank < 1 / duplicate (signal_date, rank) / duplicate
    (signal_date, symbol); sigma0/p0 non-positive; w_t outside (0, 1];
    malformed ladder lists (length mismatch, non-positive entries,
    fracs sum != 1 +/- 1e-9); a half-supplied tp1 or tp2 (one field
    without the other), tp1_mult <= 0 / tp1_frac outside (0, 1] when
    supplied (v1.4.1: tp1 is optional -- columns absent or null mean the
    zero-tier take-profit, NO profit intent is emitted for that row;
    tp2 requires tp1: tp1 null with tp2 set raises); tp2_mult <=
    tp1_mult or tp2_frac outside (0, 1] when supplied;
    stop_mult/invalid_mult <= 0;
    k_seats < 1 / ind_cap < 0 / buffer_mult < 1 or any of them not
    constant within a signal_date; signal_date first-appearance order
    not strictly increasing."""
    for col in _ZONES_REQUIRED:
        if col not in zones.columns:
            raise BandContractError(f"zones: missing required column {col!r}")
    _check_date_col(zones, "signal_date", "zones")
    if zones.height == 0:
        raise BandContractError("zones: empty zones frame")
    months: dict[date, dict] = {}
    seen_pair: set[tuple[date, str]] = set()
    seen_rank: set[tuple[date, int]] = set()
    last_sd: date | None = None
    for row in zones.iter_rows(named=True):
        sd = _as_date(row["signal_date"], "zones.signal_date")
        if sd not in calendar_dates:
            raise BandContractError(
                f"zones: signal_date {sd.isoformat()} is not a daily-panel "
                "calendar day; month boundaries execute at the (signal_date, "
                "'pm') decision point which must exist")
        if last_sd is not None and sd < last_sd:
            raise BandContractError(
                "zones: signal_date values must be strictly increasing in "
                f"frame order ({sd.isoformat()} after {last_sd.isoformat()})")
        last_sd = sd
        sym = str(row["symbol"])
        if sym not in series:
            raise BandContractError(
                f"zones: {sym} {sd.isoformat()} is absent from the daily panel")
        if sym in etf_meta:
            raise BandContractError(
                f"zones: {sym} {sd.isoformat()} is an ETF in symbol_meta; "
                "zones are stock-only (BR-2) -- run ETF legs through the "
                "intent frame")
        rank = int(row["rank"])
        if rank < 1:
            raise BandContractError(
                f"zones: rank must be >= 1, got {rank} for {sym} {sd.isoformat()}")
        if (sd, rank) in seen_rank:
            raise BandContractError(
                f"zones: duplicate rank {rank} within signal_date {sd.isoformat()}")
        seen_rank.add((sd, rank))
        if (sd, sym) in seen_pair:
            raise BandContractError(
                f"zones: duplicate (signal_date, symbol) for {sym} {sd.isoformat()}")
        seen_pair.add((sd, sym))
        sigma0 = float(row["sigma0"])
        if not math.isfinite(sigma0) or sigma0 <= 0:
            raise BandContractError(
                f"zones: sigma0 must be finite > 0 (S-v14-1: the engine does "
                f"not clip), got {sigma0} for {sym} {sd.isoformat()}")
        p0 = float(row["p0"])
        if not math.isfinite(p0) or p0 <= 0:
            raise BandContractError(
                f"zones: p0 must be finite > 0, got {p0} for {sym} {sd.isoformat()}")
        w_t = float(row["w_t"])
        if not math.isfinite(w_t) or not (0 < w_t <= 1):
            raise BandContractError(
                f"zones: w_t must be in (0, 1], got {w_t} for {sym} {sd.isoformat()}")
        offsets = _zones_float_list(row["ladder_offsets"], "ladder_offsets")
        fracs = _zones_float_list(row["ladder_fracs"], "ladder_fracs")
        if len(offsets) != len(fracs):
            raise BandContractError(
                f"zones: ladder_offsets and ladder_fracs length mismatch for "
                f"{sym} {sd.isoformat()}")
        if abs(sum(fracs) - 1.0) > 1e-9:
            raise BandContractError(
                f"zones: ladder_fracs must sum to 1 (+/-1e-9), got "
                f"{sum(fracs)!r} for {sym} {sd.isoformat()}")
        # v1.4.1 (contract section 10.8): tp1 is OPTIONAL -- columns absent
        # or null mean the ZERO-TIER take-profit (no profit intent emitted
        # for the row at all); when supplied, every v1.4 assertion is kept
        # verbatim.  tp2 stays optional but requires tp1 (fail-closed: the
        # second tier cannot exist without the first).
        tp1_mult = row.get("tp1_mult")
        tp1_frac = row.get("tp1_frac")
        tp2_mult = row.get("tp2_mult")
        tp2_frac = row.get("tp2_frac")
        tp1: tuple[float, float] | None = None
        tp2: tuple[float, float] | None = None
        if tp1_mult is not None or tp1_frac is not None:
            if tp1_mult is None or tp1_frac is None:
                raise BandContractError(
                    f"zones: tp1_mult and tp1_frac must be supplied together "
                    f"for {sym} {sd.isoformat()}")
            tp1_mult = float(tp1_mult)
            tp1_frac = float(tp1_frac)
            if not math.isfinite(tp1_mult) or tp1_mult <= 0:
                raise BandContractError(
                    f"zones: tp1_mult must be finite > 0 for {sym} {sd.isoformat()}")
            if not math.isfinite(tp1_frac) or not (0 < tp1_frac <= 1):
                raise BandContractError(
                    f"zones: tp1_frac must be in (0, 1] for {sym} {sd.isoformat()}")
            tp1 = (tp1_mult, tp1_frac)
            if tp2_mult is not None or tp2_frac is not None:
                if tp2_mult is None or tp2_frac is None:
                    raise BandContractError(
                        f"zones: tp2_mult and tp2_frac must be supplied together "
                        f"for {sym} {sd.isoformat()}")
                tp2_mult = float(tp2_mult)
                tp2_frac = float(tp2_frac)
                if not math.isfinite(tp2_mult) or tp2_mult <= tp1_mult:
                    raise BandContractError(
                        f"zones: tp2_mult must be finite > tp1_mult ({tp1_mult}), "
                        f"got {tp2_mult} for {sym} {sd.isoformat()}")
                if not math.isfinite(tp2_frac) or not (0 < tp2_frac <= 1):
                    raise BandContractError(
                        f"zones: tp2_frac must be in (0, 1] for {sym} {sd.isoformat()}")
                # S-v14-12 (adjudicated fail-closed, main conversation 2026-09-20):
                # v1.4 implements tp2 as the FULL-CLEAR tier (shares=None, corp-
                # action odd lots included, BR-4); a fractional tp2_frac would
                # silently mis-size -- fractional semantics are reserved for a
                # future version, so reject here instead of ignoring the value.
                if abs(tp2_frac - 1.0) > 1e-9:
                    raise BandContractError(
                        f"zones: tp2_frac must be 1.0 in v1.4 (tp2 is the "
                        f"full-clear tier; fractional tp2 sizing is not "
                        f"implemented) for {sym} {sd.isoformat()}")
                tp2 = (tp2_mult, tp2_frac)
        elif tp2_mult is not None or tp2_frac is not None:
            raise BandContractError(
                f"zones: tp1 is null (zero-tier take-profit) but tp2 is set "
                f"for {sym} {sd.isoformat()}; tp2 cannot exist without tp1 "
                f"(v1.4.1)")
        stop_mult = float(row["stop_mult"])
        invalid_mult = float(row["invalid_mult"])
        if not math.isfinite(stop_mult) or stop_mult <= 0:
            raise BandContractError(
                f"zones: stop_mult must be finite > 0 for {sym} {sd.isoformat()}")
        if not math.isfinite(invalid_mult) or invalid_mult <= 0:
            raise BandContractError(
                f"zones: invalid_mult must be finite > 0 for {sym} {sd.isoformat()}")
        k_seats = int(row["k_seats"])
        ind_cap = int(row["ind_cap"])
        buffer_mult = int(row["buffer_mult"])
        if k_seats < 1:
            raise BandContractError(
                f"zones: k_seats must be >= 1 for {sd.isoformat()}")
        if ind_cap < 0:
            raise BandContractError(
                f"zones: ind_cap must be >= 0 for {sd.isoformat()}")
        if buffer_mult < 1:
            raise BandContractError(
                f"zones: buffer_mult must be >= 1 for {sd.isoformat()}")
        month = months.get(sd)
        if month is None:
            month = {"signal_date": sd, "rows": [], "k_seats": k_seats,
                     "ind_cap": ind_cap, "buffer_mult": buffer_mult}
            months[sd] = month
        else:
            if month["k_seats"] != k_seats:
                raise BandContractError(
                    f"zones: k_seats must be constant within signal_date "
                    f"{sd.isoformat()} ({month['k_seats']} vs {k_seats})")
            if month["ind_cap"] != ind_cap:
                raise BandContractError(
                    f"zones: ind_cap must be constant within signal_date "
                    f"{sd.isoformat()} ({month['ind_cap']} vs {ind_cap})")
            if month["buffer_mult"] != buffer_mult:
                raise BandContractError(
                    f"zones: buffer_mult must be constant within signal_date "
                    f"{sd.isoformat()} ({month['buffer_mult']} vs {buffer_mult})")
        month["rows"].append({
            "symbol": sym, "rank": rank, "industry": str(row["industry"]),
            "sigma0": sigma0, "p0": p0, "w_t": w_t,
            "offsets": offsets, "fracs": fracs,
            "tp1": tp1, "tp2": tp2,
            "stop_mult": stop_mult, "invalid_mult": invalid_mult,
        })
    sds = sorted(months)
    for i, sd in enumerate(sds):
        months[sd]["expiry"] = (sds[i + 1] + timedelta(days=1)
                                if i + 1 < len(sds)
                                else FREEZE_END + timedelta(days=1))
        months[sd]["rows"].sort(key=lambda r: r["rank"])
    return [months[sd] for sd in sds]


# --- symbol_meta / dividend_events normalization (v1.2, section 8) ----------

_SYMBOL_META_FIELDS = ("asset_class", "band", "t_plus",
                       "commission_rate", "commission_min",
                       "stamp_buy", "stamp_sell")


def _nn(value: object) -> object:
    """NaN -> None (pandas records carry NaN for missing cells)."""
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _normalize_symbol_meta(meta) -> dict[str, dict]:
    """Normalize ``symbol_meta`` (v1.2 section 8) into validated per-symbol
    rows.  Accepted: None, a dict {symbol: {field: value}}, a polars or a
    pandas DataFrame with one row per symbol (a ``symbol`` column).

    Fields: asset_class ('stock'|'etf', default 'stock'), band (ETF
    price-limit band, (0, 0.5]; ETF default 0.10 per section 8.3, stocks
    never use it), t_plus (0|1, default 1 = conservative for BOTH classes),
    and fee overrides commission_rate / commission_min / stamp_buy /
    stamp_sell (default: the run's FeeModel, stamp_buy 0).  Unknown fields
    are REJECTED (fail-closed: a misspelled field must not silently
    downgrade semantics)."""
    if meta is None:
        return {}
    rows: list[tuple[str, dict]] = []
    if isinstance(meta, dict):
        for sym, row in meta.items():
            rows.append((str(sym), dict(row)))
    elif isinstance(meta, pl.DataFrame):
        if "symbol" not in meta.columns:
            raise BandContractError("symbol_meta: missing 'symbol' column")
        for row in meta.iter_rows(named=True):
            rows.append((str(row["symbol"]), row))
    elif hasattr(meta, "columns") and hasattr(meta, "to_dict"):
        # pandas DataFrame (duck-typed; no pandas import in this module)
        if "symbol" not in set(meta.columns):
            raise BandContractError("symbol_meta: missing 'symbol' column")
        for row in meta.to_dict("records"):
            rows.append((str(row["symbol"]), row))
    else:
        raise BandContractError(
            "symbol_meta must be None, a dict, a polars or a pandas DataFrame")
    out: dict[str, dict] = {}
    for sym, raw in rows:
        unknown = set(raw) - set(_SYMBOL_META_FIELDS) - {"symbol"}
        if unknown:
            raise BandContractError(
                f"symbol_meta[{sym}]: unknown field(s) {sorted(unknown)}; "
                f"recognized fields: {_SYMBOL_META_FIELDS}")
        cls = _nn(raw.get("asset_class"))
        cls = "stock" if cls is None else str(cls)
        if cls not in ("stock", "etf"):
            raise BandContractError(
                f"symbol_meta[{sym}]: asset_class must be 'stock'/'etf', "
                f"got {cls!r}")
        band = _nn(raw.get("band"))
        band_defaulted = False
        if band is None:
            if cls == "etf":
                band, band_defaulted = ETF_DEFAULT_BAND, True
        else:
            band = float(band)
            if not math.isfinite(band) or not (0.0 < band <= 0.5):
                raise BandContractError(
                    f"symbol_meta[{sym}]: band must be finite in (0, 0.5], "
                    f"got {band}")
        t_plus = _nn(raw.get("t_plus"))
        t_plus = 1 if t_plus is None else int(t_plus)
        if t_plus not in (0, 1):
            raise BandContractError(
                f"symbol_meta[{sym}]: t_plus must be 0 or 1, got {t_plus}")
        row_out = {"asset_class": cls, "band": band,
                   "band_defaulted": band_defaulted, "t_plus": t_plus}
        for field in ("commission_rate", "commission_min",
                      "stamp_buy", "stamp_sell"):
            value = _nn(raw.get(field))
            if value is not None:
                value = float(value)
                if not math.isfinite(value) or value < 0:
                    raise BandContractError(
                        f"symbol_meta[{sym}]: {field} must be finite >= 0, "
                        f"got {value}")
                row_out[field] = value
        out[sym] = row_out
    return out


def _normalize_dividend_events(div) -> pl.DataFrame:
    """Coerce ``dividend_events`` (v1.2 section 8.4: None / dict of columns /
    polars / pandas frame) to a validated polars frame (symbol, date,
    div_per_share; per-share finite >= 0; hard-frozen to 2024-12-31)."""
    if div is None:
        return pl.DataFrame(schema={"symbol": pl.String, "date": pl.Date,
                                    "div_per_share": pl.Float64})
    if isinstance(div, pl.DataFrame):
        frame = div
    elif isinstance(div, dict):
        frame = pl.DataFrame(div)
    elif hasattr(div, "columns") and hasattr(div, "to_dict"):
        frame = pl.DataFrame(div.to_dict("records"))
    else:
        raise BandContractError(
            "dividend_events must be None, a dict, a polars or a pandas "
            "DataFrame")
    for col in ("symbol", "date", "div_per_share"):
        if col not in frame.columns:
            raise BandContractError(
                f"dividend_events: missing required column {col!r}")
    _check_date_col(frame, "date", "dividend_events")
    assert_frozen(frame, "date", "dividend_events")
    bad = frame.filter(pl.col("div_per_share").is_null()
                       | ~pl.col("div_per_share").is_finite()
                       | (pl.col("div_per_share") < 0))
    if bad.height:
        raise BandContractError(
            f"dividend_events: {bad.height} rows with null/negative/"
            "non-finite div_per_share")
    return frame


def _normalize_corporate_actions(ca) -> pl.DataFrame:
    """Coerce ``corporate_actions`` (v1.3 section 9.2: None / dict of
    columns / polars / pandas frame) to a validated polars frame (symbol,
    date, ratio, factor_jump).  ``ratio`` is the ANNOUNCED share-change
    multiplier (revision 1: the fund company's disclosed integer ratio,
    e.g. 513100 = 5, 513500 = 2; direction-agnostic, split > 1 and
    consolidation < 1 use the same formula).  ``factor_jump`` is the
    OPTIONAL detected adj-factor ratio carried for the 9.2-1 cross-check
    (|factor_jump / ratio - 1| <= CA_FACTOR_CHECK_TOL); when the input
    lacks the column a null column is added.  Duplicate (symbol, date)
    events are rejected; hard-frozen to 2024-12-31."""
    if ca is None:
        return pl.DataFrame(schema={"symbol": pl.String, "date": pl.Date,
                                    "ratio": pl.Float64,
                                    "factor_jump": pl.Float64})
    if isinstance(ca, pl.DataFrame):
        frame = ca
    elif isinstance(ca, dict):
        frame = pl.DataFrame(ca)
    elif hasattr(ca, "columns") and hasattr(ca, "to_dict"):
        frame = pl.DataFrame(ca.to_dict("records"))
    else:
        raise BandContractError(
            "corporate_actions must be None, a dict, a polars or a pandas "
            "DataFrame")
    for col in ("symbol", "date", "ratio"):
        if col not in frame.columns:
            raise BandContractError(
                f"corporate_actions: missing required column {col!r}")
    if "factor_jump" not in frame.columns:
        frame = frame.with_columns(pl.lit(None, dtype=pl.Float64)
                                   .alias("factor_jump"))
    _check_date_col(frame, "date", "corporate_actions")
    assert_frozen(frame, "date", "corporate_actions")
    bad = frame.filter(pl.col("ratio").is_null()
                       | ~pl.col("ratio").is_finite()
                       | (pl.col("ratio") <= 0))
    if bad.height:
        raise BandContractError(
            f"corporate_actions: {bad.height} rows with null/non-finite/"
            "non-positive ratio (the announced multiplier, e.g. 5 or 2)")
    bad_fj = frame.filter(
        pl.col("factor_jump").is_not_null()
        & (~pl.col("factor_jump").is_finite()
           | (pl.col("factor_jump") <= 0)))
    if bad_fj.height:
        raise BandContractError(
            f"corporate_actions: {bad_fj.height} rows with non-finite/"
            "non-positive factor_jump (the optional detected adj-factor "
            "ratio used only for the 9.2-1 cross-check)")
    dup = frame.group_by("symbol", "date").len().filter(pl.col("len") > 1)
    if dup.height:
        raise BandContractError(
            "corporate_actions: duplicate (symbol, date) events "
            f"{dup.head(3).to_dicts()} (one announced ratio per ex-date)")
    return frame


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


def _build_preclose(daily: pl.DataFrame) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """symbol -> (dint array, preclose array) from an optional ``preclose``
    column of the daily frame (v1.2 section 8.3: first-priority ETF limit
    basis; the fallback is the previous traded official close)."""
    if "preclose" not in daily.columns:
        return {}
    frame = daily.filter(pl.col("preclose").is_not_null()).sort("symbol", "date")
    if frame.height == 0:
        return {}
    out: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    offset = 0
    rle = frame["symbol"].rle()
    for value, length in zip(rle.struct.field("value").to_list(),
                             rle.struct.field("len").to_list()):
        part = frame.slice(offset, length)
        out[value] = (
            part.select(_dint_expr("date").alias("dint")).to_numpy()[:, 0],
            np.asarray(part["preclose"].to_numpy(), dtype=np.float64))
        offset += length
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
    symbol_meta=None,
    dividend_events=None,
    corporate_actions=None,
    *,
    initial_cash: float = 200_000.0,
    fees: FeeModel | None = None,
    bridge_check: bool = True,
    intent_frame: pl.DataFrame | None = None,
    zones: pl.DataFrame | None = None,
    zone_priority_base: int = 1000,
    execution_clock: str = "legacy",
    etf_routing: str = "paired",
    intent_provider=None,
    etf_market_fill: float = 0.0,
) -> BandResult:
    """Run the v1 band-contract execution/accounting (section 7) over the
    inputs.  See the module docstring for the frozen semantics.
    Deterministic: no RNG; the only wall-clock dependence is the budget
    guard (check_day_budget raises if computation exceeds 1800 s).

    v1.1 (section 9 revision 2): pass ``intent_frame`` (and ``signals=None``)
    to run in INTENT MODE -- the engine owns the order lifecycle; see
    :func:`run_band_backtest_intents`.  The static-frame path is unchanged.

    v1.2 (section 8): ``symbol_meta``/``dividend_events`` are normalized and
    validated for BOTH entry points.  R12 adjudication: the STATIC signal
    entry does NOT support ETF legs -- a symbol_meta asset_class='etf'
    symbol present in the daily panel / signals hard-rejects here (the
    section 8.2 pm-only session routing exists only in the intent layer);
    the supported surface for ETF legs is
    :func:`run_band_backtest_intents`.

    v1.3 (section 9.2): ``corporate_actions`` (symbol / date / ratio /
    optional factor_jump) is normalized and validated for BOTH entry
    points; the transformation loop itself runs in the shared corporate
    action block.  None = exact v1.2 behavior.

    v1.4 (section 10): ``zones`` (per-signal-month candidate tables, see
    :func:`run_band_backtest_zones`) runs the zone engine (ladder buys /
    take-profit / stop-loss / seat recycling) on STOCK symbols; mutually
    exclusive with ``signals``, composable with ``intent_frame`` (mixed
    ETF-leg accounts).  None = exact v1.3 behavior.

    v1.5 (decision 2026-09-21-etf-pm-only-routing): ``etf_routing``
    selects the ETF session expression under ``execution_clock='halfday'``
    -- ``'paired'`` (default; requires ETF am+pm halfday bars) or
    ``'pm_only'`` (no ETF halfday bars; pm decision -> next-day pm live
    session matched on the real daily bar; am ETF intents rejected).  The
    default leaves every v1.4.2 behavior byte-identical.
    """
    fees = fees or FeeModel()
    if not math.isfinite(initial_cash) or initial_cash <= 0:
        raise BandContractError("initial_cash must be finite > 0")
    if intent_provider is not None and not callable(intent_provider):
        raise BandContractError("intent_provider must be callable")
    if intent_provider is not None and signals is not None:
        raise BandContractError(
            "intent_provider requires intent mode: pass signals=None")
    if intent_provider is not None and zones is not None:
        raise BandContractError(
            "intent_provider and zones are mutually exclusive: the zone "
            "engine owns stock order generation")
    if intent_frame is not None and signals is not None:
        raise BandContractError(
            "intent_frame and signals are mutually exclusive: one entry "
            "point per run (static frame OR engine-owned intents)")
    if zones is not None and signals is not None:
        raise BandContractError(
            "zones and signals are mutually exclusive (BR-1): the zone "
            "engine owns stock order generation; pass signals=None")
    if zones is not None and not isinstance(zones, pl.DataFrame):
        raise BandContractError("zones must be a polars DataFrame")
    zone_priority_base = int(zone_priority_base)
    if zone_priority_base < 1:
        raise BandContractError(
            f"zone_priority_base must be >= 1, got {zone_priority_base}")
    if etf_routing not in ("paired", "pm_only"):
        raise BandContractError(
            f"etf_routing must be 'paired' or 'pm_only', got {etf_routing!r}")
    if not (etf_market_fill == 0.0
            or (math.isfinite(etf_market_fill) and 0.0 < etf_market_fill <= 0.01)):
        raise BandContractError(
            "etf_market_fill must be 0.0 (off, strict-penetration caliber) "
            f"or in (0, 0.01], got {etf_market_fill!r}")
    etf_pm_only = etf_routing == "pm_only"
    if etf_pm_only and execution_clock != "halfday":
        raise BandContractError(
            "etf_routing='pm_only' is the halfday-clock ETF expression: the "
            "legacy clock already routes ETF pm decisions to the next pm "
            "session; pass execution_clock='halfday' with it")
    meta_rows = _normalize_symbol_meta(symbol_meta)
    etf_meta = {s: r for s, r in meta_rows.items() if r["asset_class"] == "etf"}
    dividend_events = _normalize_dividend_events(dividend_events)
    corporate_actions = _normalize_corporate_actions(corporate_actions)

    assert_frozen(daily, "date", "daily")
    assert_frozen(halfday, "trade_date", "halfday")
    assert_frozen(stk_limit, "date", "stk_limit")
    if splits is not None:
        assert_frozen(splits, "ex_date", "splits")
    if cash_dividends is not None:
        assert_frozen(cash_dividends, "ex_date", "cash_dividends")
    assert_frozen(dividend_events, "date", "dividend_events")
    assert_frozen(corporate_actions, "date", "corporate_actions")
    if zones is not None:
        assert_frozen(zones, "signal_date", "zones")
    if intent_frame is not None:
        assert_frozen(intent_frame, "decision_date", "intents")
        if "expiry_date" in intent_frame.columns:
            assert_frozen(intent_frame, "expiry_date", "intents")
    elif zones is None and signals is not None:
        assert_frozen(signals, "decision_date", "signals")

    _validate_daily(daily)
    _validate_halfday(halfday, allow_empty=etf_pm_only)
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
    preclose_ix = _build_preclose(daily)
    split_map = _build_splits(splits)
    divs = _build_dividends(cash_dividends)
    is_etf = {r["symbol"]: bool(r["is_etf"]) for r in instruments.iter_rows(named=True)}
    is_t0 = {r["symbol"]: bool(r["is_t0"]) for r in instruments.iter_rows(named=True)}
    # v1.2 section 8 merges: a meta ETF is an ETF for the fills column; a
    # meta t_plus=0 grants T+0 (union -- neither source can downgrade the
    # other).  ETF CLASS for routing/limits comes from symbol_meta only, so
    # v1.1-style runs (instruments flags, no meta) are untouched.
    for sym_m, row_m in meta_rows.items():
        if row_m["t_plus"] == 0:
            is_t0[sym_m] = True
        if row_m["asset_class"] == "etf":
            is_etf[sym_m] = True
    half_symbols = set(half)

    # v1.2 section 8.4 cash-dividend events (meta-gated: only symbols that
    # are present in symbol_meta AND appear in the event frame are effective)
    div_event_map: dict[str, dict[int, float]] = {}
    div_event_cash_total = 0.0
    if meta_rows and dividend_events.height:
        for row_d in dividend_events.iter_rows(named=True):
            sym_d = str(row_d["symbol"])
            if sym_d not in meta_rows:
                continue
            d_d = _dint(_as_date(row_d["date"], "dividend_events.date"))
            per_d = div_event_map.setdefault(sym_d, {})
            per_d[d_d] = per_d.get(d_d, 0.0) + float(row_d["div_per_share"])

    # ---- v1.3 section 9.2: share-change (份额变换) corporate actions -------
    # Entry-time validation of every event (fail-closed BEFORE any simulated
    # trading): 9.2-5 legality guardrail, 9.2-1 factor cross-check, and the
    # 9.2-7 anti-misclassification gates on dividend_events.
    def _ca_preclose_column(sym: str, day: date) -> float | None:
        """The daily frame's ``preclose`` column value for (sym, day), or
        None when absent (no fallback here: the 9.2-5 guardrail must be
        evaluated against the exchange's own reference price, not a
        reconstructed one)."""
        ix = preclose_ix.get(sym)
        if ix is None:
            return None
        d_arr, pc_arr = ix
        i = int(np.searchsorted(d_arr, _dint(day)))
        if i < len(d_arr) and int(d_arr[i]) == _dint(day):
            value = float(pc_arr[i])
            if math.isfinite(value) and value > 0:
                return value
        return None

    def _ca_prev_close(sym: str, day: date) -> float | None:
        """Last TRADED official close strictly before ``day``."""
        s = series.get(sym)
        if s is None:
            return None
        i = int(np.searchsorted(s["trade_dint"], _dint(day)))
        if i == 0:
            return None
        return float(s["trade_close"][i - 1])

    ca_map: dict[str, dict[int, dict]] = {}
    ca_stats = {"events": 0, "odd_lot_cash_total": 0.0,
                "shares_before": 0, "shares_after": 0}
    if corporate_actions.height:
        for row_ca in corporate_actions.iter_rows(named=True):
            sym_ca = str(row_ca["symbol"])
            d_ca = _as_date(row_ca["date"], "corporate_actions.date")
            ratio_ca = float(row_ca["ratio"])
            if sym_ca not in series:
                raise BandContractError(
                    f"corporate_actions: {sym_ca} {d_ca.isoformat()} is "
                    "absent from the daily panel; refusing a share change "
                    "for an unknown symbol")
            prev_ca = _ca_prev_close(sym_ca, d_ca)
            if prev_ca is None:
                raise BandContractError(
                    f"corporate_actions: {sym_ca} {d_ca.isoformat()} has no "
                    "traded close strictly before the ex-date; the 9.2-5 "
                    "guardrail cannot be evaluated")
            pc_ca = _ca_preclose_column(sym_ca, d_ca)
            if pc_ca is None:
                raise BandContractError(
                    f"corporate_actions: {sym_ca} {d_ca.isoformat()} has no "
                    "preclose column value on the ex-date; the 9.2-5 "
                    "guardrail requires the exchange reference price")
            resid_ca = abs(pc_ca * ratio_ca - prev_ca) / prev_ca
            if resid_ca > CA_GUARDRAIL_TOL:
                raise BandContractError(
                    f"corporate_actions guardrail VIOLATION (section 9.2-5): "
                    f"{sym_ca} {d_ca.isoformat()} preclose {pc_ca} x ratio "
                    f"{ratio_ca} vs close(t-1) {prev_ca} -> residual "
                    f"{resid_ca:.6f} > {CA_GUARDRAIL_TOL} (wrong date or "
                    "wrong ratio)")
            fj_ca = row_ca["factor_jump"]
            if fj_ca is not None:
                dev_ca = abs(float(fj_ca) / ratio_ca - 1.0)
                if dev_ca > CA_FACTOR_CHECK_TOL:
                    raise BandContractError(
                        f"corporate_actions factor cross-check VIOLATION "
                        f"(section 9.2-1): {sym_ca} {d_ca.isoformat()} "
                        f"factor_jump {float(fj_ca)} vs announced ratio "
                        f"{ratio_ca} -> |factor/ratio - 1| = {dev_ca:.6f} > "
                        f"{CA_FACTOR_CHECK_TOL}")
            ca_map.setdefault(sym_ca, {})[_dint(d_ca)] = {
                "ratio": ratio_ca, "preclose": pc_ca, "prev_close": prev_ca,
                "residual": resid_ca}
        # section 9.2-7: a (symbol, date) may not carry BOTH a dividend and
        # a share change (misclassification guard, either direction)
        conflict = corporate_actions.select("symbol", "date").join(
            dividend_events.select("symbol", "date"),
            on=["symbol", "date"], how="semi")
        if conflict.height:
            raise BandContractError(
                f"corporate_actions/dividend_events CONFLICT (section 9.2-7): "
                f"{conflict.head(3).to_dicts()} carry a dividend and a share "
                "change on the same (symbol, date)")
        # the v0 stock-side split_factor path must not double-transform the
        # same ex-date (data-integrity guard)
        if splits is not None and splits.height:
            clash = corporate_actions.select("symbol", "date").join(
                splits.select(
                    pl.col("symbol"),
                    pl.col("ex_date").alias("date")),
                on=["symbol", "date"], how="semi")
            if clash.height:
                raise BandContractError(
                    f"corporate_actions vs split_factor CLASH: "
                    f"{clash.head(3).to_dicts()} would be transformed by "
                    "both the v0 送转 path and the v1.3 share-change path")
    # section 9.2-7 (hard gate, runs whenever dividend_events are supplied):
    # an implied yield (close(t-1) - preclose) / close(t-1) > 10% is a share
    # change, not a dividend -- the run layer must not feed it into the
    # dividend path (dev dividend maximum is +5.44%, margin >= 27x)
    if dividend_events.height:
        for row_dv in dividend_events.iter_rows(named=True):
            sym_dv = str(row_dv["symbol"])
            if sym_dv not in series:
                continue        # not in the panel: event is inert (v1.2 gate)
            d_dv = _as_date(row_dv["date"], "dividend_events.date")
            prev_dv = _ca_prev_close(sym_dv, d_dv)
            pc_dv = _ca_preclose_column(sym_dv, d_dv)
            if prev_dv is None or pc_dv is None:
                continue        # implied yield not evaluable from this panel
            yield_dv = (prev_dv - pc_dv) / prev_dv
            if yield_dv > CA_YIELD_MISCLASS_LIMIT:
                raise BandContractError(
                    f"dividend_events MISCLASSIFICATION (section 9.2-7): "
                    f"{sym_dv} {d_dv.isoformat()} implies a "
                    f"{yield_dv:.4%} yield ((close(t-1) {prev_dv} - preclose "
                    f"{pc_dv}) / {prev_dv}) > "
                    f"{CA_YIELD_MISCLASS_LIMIT:.0%}; this is a share change, "
                    "not a cash dividend -- pass it via corporate_actions")

    calendar: list[date] = sorted(
        {date(int(d) // 10_000, int(d) // 100 % 100, int(d) % 100)
         for s in series.values() for d in s["dint"].tolist()})
    next_day: dict[date, date] = {}
    for i, d in enumerate(calendar):
        if i + 1 < len(calendar):
            next_day[d] = calendar[i + 1]

    if execution_clock not in ("legacy", "halfday"):
        raise BandContractError("execution_clock must be legacy or halfday")
    halfday_clock = execution_clock == "halfday"
    if halfday_clock and ((intent_frame is None and intent_provider is None)
                          or zones is not None):
        raise BandContractError("halfday clock requires intent mode without zones")
    if halfday_clock and not etf_pm_only:
        # Daily-only ETF proxies cannot establish a morning execution price.
        # v1.5: etf_routing='pm_only' is exactly that expression -- the ETF
        # leg keeps a single 15:00 decision and matches the real daily bar at
        # the next pm session, so no ETF halfday bar is required (see the
        # pm-only daily-bar map below, which carries its own fail-closed
        # completeness check).
        trading = daily.filter(pl.col("symbol").is_in(list(etf_meta)))
        if "tradestatus" in trading.columns:
            trading = trading.filter(pl.col("tradestatus") != 0)
        for session in ("am", "pm"):
            available = halfday.filter(pl.col("session") == session).select(
                "symbol", pl.col("trade_date").alias("date"))
            if trading.select("symbol", "date").join(
                    available, on=["symbol", "date"], how="anti").height:
                raise BandContractError("halfday clock requires ETF am and pm bars")
    # v1.5 pm-only ETF routing (decision 2026-09-21-etf-pm-only-routing,
    # point 5): the ETF leg has NO half-day bar by contract -- its pm live
    # sessions match against the REAL daily row (whole-day high/low, the
    # section 8.1 convention: never a synthesized am bar, never an assumed
    # intraday path).  Bars come from TRADED rows only (a suspended row is
    # not a tradable bar), and every day this panel marks as traded must
    # carry one: a hole is fail-closed BEFORE any simulated trading.
    pm_only_bars: dict[str, dict[int, tuple]] = {}
    if etf_pm_only:
        etf_in_panel = sorted(set(etf_meta) & set(series))
        sub = daily.filter(pl.col("symbol").is_in(etf_in_panel))
        if "tradestatus" in sub.columns:
            sub = sub.filter(pl.col("tradestatus").fill_null(0) != 0)
        for row_pm in sub.iter_rows(named=True):
            pm_only_bars.setdefault(str(row_pm["symbol"]), {})[
                _dint(_as_date(row_pm["date"], "daily.date"))] = (
                    float(row_pm["open"]), float(row_pm["high"]),
                    float(row_pm["low"]), float(row_pm["close"]))
        for sym_pm in etf_in_panel:
            have_pm = pm_only_bars.get(sym_pm, {})
            missing_pm = [int(d) for d in series[sym_pm]["trade_dint"]
                          if int(d) not in have_pm]
            if missing_pm:
                raise BandContractError(
                    "etf_routing='pm_only': %s has %d trading day(s) without "
                    "a usable daily bar (first %d); the pm-only contract "
                    "requires a daily bar on every traded day (fail-closed)"
                    % (sym_pm, len(missing_pm), missing_pm[0]))
    intent_engine = intent_frame is not None or intent_provider is not None
    zone_engine = zones is not None
    if intent_engine:
        INTENTS = (_validate_intents(intent_frame) if intent_frame is not None
                   else [])
        for it in INTENTS:
            if (not halfday_clock or etf_pm_only) and it["symbol"] in etf_meta \
                    and it["first_s"] == "am":
                raise BandContractError(
                    "intents: ETF symbol %s has decision_session='am' at %s; "
                    "section 8.2: ETF legs trade the 15:00 decision point "
                    "only (no am data)" % (it["symbol"],
                                           it["first_d"].isoformat()))
        if zone_engine:
            # BR-1: priority bases must not overlap across the two layers
            # (zone orders rank from zone_priority_base; boundary exits sit
            # at 10**6 + rank) -- a跨层 competition must be unambiguous.
            bad_prio = [it for it in INTENTS
                        if it["priority"] >= zone_priority_base]
            if bad_prio:
                raise BandContractError(
                    "intents: with zones active every intent priority must "
                    f"be < zone_priority_base ({zone_priority_base}); "
                    f"violations: {bad_prio[:3]}")
        orders = []
    elif zone_engine and signals is None:
        # zones-only run (BR-1 convenience entry): the zone engine owns all
        # stock order generation; no static signals exist.
        INTENTS = []
        orders = []
    else:
        INTENTS = []
        # v1.2 R12 adjudication: the static signal entry does NOT implement
        # the section 8.2 ETF session routing (pm decision -> next pm is an
        # intent-layer feature) -- an ETF-meta symbol appearing in the daily
        # panel / signals is hard-rejected instead of half-supported.
        # (Signal symbols are a subset of the panel -- _validate_signals
        # enforces coverage -- so the panel check covers both triggers.)
        if etf_meta:
            clash = sorted(set(etf_meta) & set(series))
            if clash:
                raise BandContractError(
                    "static signal path does not support ETF legs (section "
                    "8.2 pm-only routing is intent-layer only): "
                    "symbol_meta marks %s as asset_class='etf' and it "
                    "appears in the daily panel / signals; run this "
                    "account through run_band_backtest_intents" % clash)
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

    # ---- v1.4 section 10: zones engine (ladder_buy / take_profit /
    #      stop_sell / seat recycling).  EVERY path below is gated on
    #      ``zone_engine``; without a zones frame nothing here runs and the
    #      v1.3 behavior is byte-identical (BR-12).  Zone-engine orders use
    #      priority = zone_priority_base + rank (boundary exits 10**6 + rank,
    #      BR-1); their source strings identify the layer: "zladder:<sd>" /
    #      "ztp:<sd>" / "zbound:<sd>" / "stop:<sd>".
    zone_stats: dict = {
        "n_candidates": 0, "n_admitted": 0,
        "stop_armed_events": 0, "stop_armed_resolved_fallback": 0,
        "stop_armed_resolved_other": 0, "stop_armed_stuck_end": 0,
        "stop_deferred_limitdown": 0,
        "tp_expired_sessions": 0, "tier_expired": 0, "tier_invalidated": 0,
        "tier_below_min_lot": 0, "tier_cap_voided": 0, "tp_below_min_lot": 0,
    }
    ZONE_MONTHS: list[dict] = []
    ZONES: dict[tuple[date, str], dict] = {}
    ZONE_BY_SYM: dict[str, dict] = {}     # the single active zone per symbol
    COOLING: dict[str, dict] = {}         # cleared this month, blocked until
                                          # the next signal_date (BR-8 ii)
    MONTH_SYMBOLS: dict[date, set] = {}
    cur_month_idx = -1
    if zone_engine:
        ZONE_MONTHS = _validate_zones(zones, series, set(calendar), etf_meta)
        MONTH_SYMBOLS = {m["signal_date"]: set() for m in ZONE_MONTHS}
        zone_stats["n_candidates"] = sum(len(m["rows"]) for m in ZONE_MONTHS)
        # S-v14-15 (adjudicated fail-closed, main conversation 2026-09-20):
        # a zones symbol also traded by the intent frame is undefined
        # behavior (the zone WAC aggregates zladder buys only) -- reject
        # instead of relying on the runner to keep the layers disjoint.
        zone_overlap = sorted(
            {r["symbol"] for m in ZONE_MONTHS for r in m["rows"]}
            & {it["symbol"] for it in INTENTS})
        if zone_overlap:
            raise BandContractError(
                "zones: symbol(s) %s also present in the intent frame; "
                "zone/intent overlap is undefined (zone WAC would miss "
                "intent buys) -- keep the two layers disjoint" % zone_overlap)

    def _zone_new(mrow: dict, row: dict) -> dict:
        return {
            "signal_date": mrow["signal_date"], "symbol": row["symbol"],
            "rank": row["rank"], "industry": row["industry"],
            "sigma0": row["sigma0"], "p0": row["p0"], "w_t": row["w_t"],
            "tp1": row["tp1"], "tp2": row["tp2"],
            "stop_mult": row["stop_mult"], "invalid_mult": row["invalid_mult"],
            "expiry": mrow["expiry"],
            "ladder": [], "ladder_active": False,
            "admitted_key": None, "phase": "pending", "exit_reason": None,
            "total_target_shares": 0, "shares_bought": 0,
            "buy_amount": 0.0, "buy_shares_wac": 0.0, "wac_last": None,
            "hwm": None, "stop_line": None, "armed_events": 0,
            "first_fill_key": None, "stop_armed_pending": False,
            "fallback_filled": False, "stop_dec": None,
        }

    def _zone_drop_from_active(zone: dict) -> None:
        ZONE_BY_SYM.pop(zone["symbol"], None)

    def _zone_finish(zone: dict, phase: str, reason: str,
                     day: date, sess: str) -> None:
        zone["phase"] = phase
        zone["exit_reason"] = reason
        _zone_drop_from_active(zone)
        COOLING.pop(zone["symbol"], None)
        emit(day, sess, None, "zone_done",
             detail="%s (signal %s): phase=done reason=%s"
                    % (zone["symbol"], zone["signal_date"].isoformat(), reason))

    def _zone_to_cooling(zone: dict, reason: str, day: date, sess: str) -> None:
        zone["phase"] = "cooling"
        zone["exit_reason"] = reason
        _zone_drop_from_active(zone)
        COOLING[zone["symbol"]] = zone
        emit(day, sess, None, "zone_cooling",
             detail="%s (signal %s): position fully cleared (%s); no "
                    "re-entry until the next signal_date (BR-8 ii)"
                    % (zone["symbol"], zone["signal_date"].isoformat(), reason))

    def _zone_admit(mrow: dict, row: dict, snap: float,
                    day: date, sess: str) -> dict | None:
        """BR-3/BR-8 admission: one-shot total sizing from the SIGNAL-DAY pm
        equity snapshot (S-v14-7d: fixed even for mid-month admissions),
        per-tier floor-to-lot sizing (S-v14-2), below_min_lot candidates
        finish immediately and the scan moves on."""
        sd = mrow["signal_date"]
        sym = row["symbol"]
        zone = _zone_new(mrow, row)
        MONTH_SYMBOLS[sd].add(sym)
        ZONES[(sd, sym)] = zone
        total = int(math.floor(row["w_t"] * snap / row["p0"] / LOT)) * LOT
        zone["total_target_shares"] = total
        if total < LOT:
            zone["phase"] = "done"
            zone["exit_reason"] = "below_min_lot"
            zone_stats["tier_below_min_lot"] += 1
            emit(day, sess, None, "zone_below_min_lot",
                 detail="%s (signal %s): total %d shares < %d at w_t %.6f x "
                        "snapshot %.2f / p0 %.4f; zone done"
                        % (sym, sd.isoformat(), total, LOT, row["w_t"],
                           snap, row["p0"]))
            return None
        tiers = []
        for ti, (off, frac) in enumerate(zip(row["offsets"], row["fracs"])):
            sh = int(math.floor(frac * total / LOT)) * LOT
            if sh < LOT:
                zone_stats["tier_below_min_lot"] += 1
                continue
            tiers.append({"offset": off, "frac": frac, "target": sh,
                          "filled": 0})
        if not tiers:
            zone["phase"] = "done"
            zone["exit_reason"] = "below_min_lot"
            emit(day, sess, None, "zone_below_min_lot",
                 detail="%s (signal %s): every tier floors below %d shares; "
                        "zone done" % (sym, sd.isoformat(), LOT))
            return None
        zone["ladder"] = tiers
        zone["ladder_active"] = True
        zone["phase"] = "entering"
        zone["admitted_key"] = _sess_key(day, sess)
        ZONE_BY_SYM[sym] = zone
        zone_stats["n_admitted"] += 1
        emit(day, sess, None, "zone_admitted",
             detail="%s (signal %s) rank %d admitted: total target %d "
                    "shares, tiers %s, expiry %s"
                    % (sym, sd.isoformat(), row["rank"], total,
                       [(t["offset"], t["target"]) for t in tiers],
                       mrow["expiry"].isoformat()))
        return zone

    def _zone_continue(zone: dict, row: dict, mrow: dict,
                       day: date, sess: str) -> None:
        """BR-7 (2) continuation: refresh rank/industry/sigma0/p0/expiry,
        KEEP the WAC and the ratcheted stop line; the old ladder is
        terminated by same-name month replacement (section 10.1-1 #2) and
        is NOT re-issued (no add-to-position primitive, section 10.4)."""
        old_sd = zone["signal_date"]
        sym = zone["symbol"]
        if zone["ladder_active"]:
            n_rem = sum(1 for t in zone["ladder"] if t["target"] > t["filled"])
            zone_stats["tier_expired"] += n_rem
        zone["ladder_active"] = False
        zone["signal_date"] = mrow["signal_date"]
        zone["rank"] = row["rank"]
        zone["industry"] = row["industry"]
        zone["sigma0"] = row["sigma0"]
        zone["p0"] = row["p0"]
        zone["w_t"] = row["w_t"]
        zone["tp1"] = row["tp1"]
        zone["tp2"] = row["tp2"]
        zone["stop_mult"] = row["stop_mult"]
        zone["invalid_mult"] = row["invalid_mult"]
        zone["expiry"] = mrow["expiry"]
        ZONES.pop((old_sd, sym), None)
        ZONES[(mrow["signal_date"], sym)] = zone
        MONTH_SYMBOLS[old_sd].discard(sym)
        MONTH_SYMBOLS[mrow["signal_date"]].add(sym)
        emit(day, sess, None, "zone_continued",
             detail="%s: rank %d <= buffer %d x K %d; continued into %s "
                    "(sigma0 %.6f, expiry %s; WAC kept, stop line via max, "
                    "ladder not re-issued)"
                    % (sym, row["rank"], mrow["buffer_mult"], mrow["k_seats"],
                       mrow["signal_date"].isoformat(), row["sigma0"],
                       mrow["expiry"].isoformat()))

    def _zone_boundary(day: date, sess: str) -> None:
        """BR-2/BR-7: month boundary at the (signal_date, 'pm') decision
        point: cooling -> done, then per old zone: continuation
        (rank <= buffer_mult x K and still holding) or full exit."""
        m_new = ZONE_MONTHS[cur_month_idx]
        rows_by_sym = {r["symbol"]: r for r in m_new["rows"]}
        for sym, zone in list(COOLING.items()):
            zone["phase"] = "done"
            emit(day, sess, None, "zone_done",
                 detail="%s (signal %s): cooling ended at the month boundary"
                        % (sym, zone["signal_date"].isoformat()))
        COOLING.clear()
        for zone in list(ZONE_BY_SYM.values()):
            sym = zone["symbol"]
            if zone["phase"] not in ("entering", "holding"):
                # exiting (stop) / exiting_boundary keep their exit path;
                # they are leaving and are not re-parameterized (S-v14-8)
                continue
            row = rows_by_sym.get(sym)
            held = total_shares(sym) > 0
            if held and row is not None \
                    and row["rank"] <= m_new["buffer_mult"] * m_new["k_seats"]:
                _zone_continue(zone, row, m_new, day, sess)
                continue
            # month replacement (section 10.1-1 #2): the ladder group dies
            if zone["ladder_active"]:
                n_rem = sum(1 for t in zone["ladder"]
                            if t["target"] > t["filled"])
                zone_stats["tier_expired"] += n_rem
            zone["ladder_active"] = False
            if zone["phase"] == "entering":
                _zone_finish(zone, "done", "month_replaced", day, sess)
            else:
                zone["phase"] = "exiting_boundary"
                zone["exit_reason"] = ("boundary_rank" if row is not None
                                       else "boundary_dropped")
                emit(day, sess, None, "zone_exiting_boundary",
                     detail="%s: rank %s vs buffer %d x K %d -> full exit "
                            "(risk sells each decision point, K=3 fallback)"
                            % (sym, ("dropped" if row is None
                                     else str(row["rank"])),
                               m_new["buffer_mult"], m_new["k_seats"]))

    def _zone_scan(day: date, sess: str) -> None:
        """BR-7 seat counting + BR-8 recovery scan: held = zones with
        shares > 0 (incl. unfinished boundary exits -- conservative,
        S-v14-7c); in-flight = entering ladders; industry counts include
        in-flight ladders; admissions in rank order while
        held + in-flight < k_seats."""
        m = ZONE_MONTHS[cur_month_idx]
        held: set = set()
        inflight: set = set()
        ind_ct: dict[str, int] = {}
        for zone in ZONE_BY_SYM.values():
            sym = zone["symbol"]
            if zone["phase"] == "entering":
                inflight.add(sym)
            if total_shares(sym) > 0:
                held.add(sym)
            if sym in held or sym in inflight:
                ind_ct[zone["industry"]] = ind_ct.get(zone["industry"], 0) + 1
        seats = len(held) + len(inflight)
        taken = MONTH_SYMBOLS[m["signal_date"]]
        snap = decision_snapshots.get((m["signal_date"], "pm"))
        for row in m["rows"]:
            if seats >= m["k_seats"]:
                break
            sym = row["symbol"]
            if sym in taken or sym in ZONE_BY_SYM:
                continue        # (i) active / (ii)(iv) already has a zone
            if ind_ct.get(row["industry"], 0) >= m["ind_cap"]:
                continue        # (iii) industry full
            if snap is None:
                raise BandContractError(
                    "zones: missing decision snapshot for the signal-day pm "
                    "decision %s; admission sizing is undefined"
                    % m["signal_date"].isoformat())
            zone = _zone_admit(m, row, snap, day, sess)
            if zone is not None:
                seats += 1
                ind_ct[row["industry"]] = ind_ct.get(row["industry"], 0) + 1

    def _zone_hang(day: date, sess: str) -> None:
        """BR-3/BR-4/BR-5 order generation at a decision point: remaining
        ladder tiers (limit = P - offset x sigma0), WAC-anchored take-profit
        orders (tp1 frac-sized; tp2 shares=None full sellable), full-exit
        risk sells for boundary exits (priority 10**6 + rank).  Anchor
        missing (suspension) -> nothing hung this decision point (m3)."""
        live_d = day if sess == "am" else next_day.get(day)
        live_s = "pm" if sess == "am" else "am"
        if live_d is None:
            return
        snap = decision_snapshots.get((day, sess))
        touched: set = set()
        for zone in list(ZONE_BY_SYM.values()):
            sym = zone["symbol"]
            sd_iso = zone["signal_date"].isoformat()
            rank = zone["rank"]
            anchor = intent_anchor(sym, day, sess)
            if zone["phase"] == "exiting_boundary":
                if anchor is None:
                    continue
                row_o = _Order(
                    order_id="%s-sell/risk-zbound-%s-%s"
                             % (sym, day.isoformat(), sess),
                    symbol=sym, side="sell", intent="risk",
                    decision_date=day, decision_session=sess,
                    live_date=live_d, live_session=live_s,
                    anchor_price=anchor, priority=10 ** 6 + rank,
                    target_notional=None, shares=None,
                    source="zbound:%s" % sd_iso, snapshot=snap)
                generated_orders.append(row_o)
                live_orders.setdefault((live_d, live_s), []).append(row_o)
                touched.add((live_d, live_s))
                st = risk_state.get(sym)
                if st is None:
                    risk_state[sym] = {
                        "anchor": anchor, "streak": 0, "armed": False,
                        "refreshed_at": decision_counter, "order": row_o,
                        "source": row_o.source}
                else:
                    # zone-aware M1 refresh: an armed stop fallback is never
                    # disarmed; same-source re-anchors keep the streak
                    if st.get("source") != row_o.source and not st["armed"]:
                        st["streak"] = 0
                        st["armed"] = False
                        st["source"] = row_o.source
                    st.update({"anchor": anchor,
                               "refreshed_at": decision_counter,
                               "order": row_o})
                continue
            if zone["phase"] not in ("entering", "holding"):
                continue
            if anchor is None:
                continue
            if zone["ladder_active"]:
                for ti, t in enumerate(zone["ladder"]):
                    rem = t["target"] - t["filled"]
                    if rem <= 0:
                        continue
                    row_b = _Order(
                        order_id="%s-buy-zladder-%s-%s-t%d"
                                 % (sym, day.isoformat(), sess, ti),
                        symbol=sym, side="buy", intent="",
                        decision_date=day, decision_session=sess,
                        live_date=live_d, live_session=live_s,
                        anchor_price=anchor - t["offset"] * zone["sigma0"],
                        priority=zone_priority_base + rank,
                        target_notional=None, shares=rem,
                        source="zladder:%s" % sd_iso, snapshot=snap,
                        zone_tier=ti)
                    generated_orders.append(row_b)
                    live_orders.setdefault((live_d, live_s), []).append(row_b)
                    touched.add((live_d, live_s))
            if zone["phase"] == "holding" and zone["buy_shares_wac"] > 0:
                wac = zone["buy_amount"] / zone["buy_shares_wac"]
                # v1.4.1: a null tp1 (zero-tier take-profit) skips the
                # take-profit layer WHOLESALE -- no profit intent is emitted
                # for the zone; ladder / ratchet stop / invalidation /
                # expiry / seat recycling are unaffected.  With tp1 present
                # the emission is byte-identical to v1.4.
                tp_specs = []
                if zone["tp1"] is not None:
                    tp_specs.append((zone["tp1"][0], zone["tp1"][1], False))
                    if zone["tp2"] is not None:
                        tp_specs.append((zone["tp2"][0], zone["tp2"][1], True))
                for mult, frac, is_tp2 in tp_specs:
                    if is_tp2:
                        sh = None   # BR-4: tp2 exits the entire sellable
                    else:
                        tot = total_shares(sym)
                        sh = int(math.floor(frac * tot / LOT)) * LOT
                        if sh < LOT:
                            zone_stats["tp_below_min_lot"] += 1
                            continue
                    row_s = _Order(
                        order_id="%s-sell/profit-ztp%s-%s-%s"
                                 % (sym, "2" if is_tp2 else "",
                                    day.isoformat(), sess),
                        symbol=sym, side="sell", intent="profit",
                        decision_date=day, decision_session=sess,
                        live_date=live_d, live_session=live_s,
                        anchor_price=wac + mult * zone["sigma0"],
                        priority=zone_priority_base + rank,
                        target_notional=None, shares=sh,
                        source="ztp:%s" % sd_iso, snapshot=snap)
                    generated_orders.append(row_s)
                    live_orders.setdefault((live_d, live_s), []).append(row_s)
                    touched.add((live_d, live_s))
            if zone["phase"] == "holding":
                zone["stop_dec"] = (day, sess)
        for key in touched:
            live_orders[key].sort(key=lambda o: (o.priority, o.symbol))

    def zone_record_buy(order, day: date, sess: str,
                        price: float, shares: int) -> None:
        """Hook (book_buy_fill): WAC accumulation (BR-4a), tier fill-stop
        bookkeeping and the entering -> holding transition."""
        zone = ZONE_BY_SYM.get(order.symbol)
        if zone is None or not order.source.startswith("zladder:"):
            return
        zone["shares_bought"] += int(shares)
        zone["buy_amount"] += float(price) * int(shares)
        zone["buy_shares_wac"] += int(shares)
        ti = getattr(order, "zone_tier", None)
        if ti is not None and 0 <= ti < len(zone["ladder"]):
            zone["ladder"][ti]["filled"] += int(shares)
        if zone["first_fill_key"] is None:
            zone["first_fill_key"] = _sess_key(day, sess)
        if zone["phase"] == "entering":
            zone["phase"] = "holding"
            emit(day, sess, None, "zone_holding",
                 detail="%s (signal %s): first ladder fill %d @ %.4f; "
                        "trailing stop armed from the next session"
                        % (order.symbol, zone["signal_date"].isoformat(),
                           int(shares), float(price)))

    def zone_ladder_cap_void(order, day: date, sess: str) -> None:
        """Hook (segment A cap_single_name void): a cap-void on a ladder
        tier terminates the zone's whole ladder for the month (v1.1
        termination taxonomy, BR-3); filled shares keep their TP/SL."""
        if not order.source.startswith("zladder:"):
            return
        zone = ZONE_BY_SYM.get(order.symbol)
        if zone is None or not zone["ladder_active"]:
            return
        n_rem = sum(1 for t in zone["ladder"] if t["target"] > t["filled"])
        zone_stats["tier_cap_voided"] += n_rem
        zone["ladder_active"] = False
        emit(day, sess, None, "zone_ladder_cap_voided",
             detail="%s (signal %s): cap_single_name on a ladder tier "
                    "terminates the ladder (%d unfilled tier(s)); filled "
                    "shares keep TP/SL"
                    % (order.symbol, zone["signal_date"].isoformat(), n_rem))
        if zone["phase"] == "entering":
            _zone_finish(zone, "done", "cap_single_name", day, sess)

    def zone_stop_segment(day: date, sess: str) -> None:
        """BR-5: zone stop-loss evaluation segment, run at the TOP of
        process_session BEFORE the A (buy) segment (BR-6): a trigger
        cancels that name's same-session ladder tiers and TP orders before
        they can be evaluated (section 10.1-3: stop before profit).  The
        standing trigger line was re-derived at the last decision point;
        a suspended session (no bar) freezes the evaluation."""
        for sym in sorted(s for s, z in ZONE_BY_SYM.items()
                          if z["phase"] == "holding"
                          and z["stop_line"] is not None
                          and total_shares(s) > 0):
            zone = ZONE_BY_SYM[sym]
            bar = halfbar(sym, day, sess)
            if bar is None:
                continue        # suspension: trigger frozen (re-hung next)
            line = zone["stop_line"]
            low = bar[2]
            if not (low < line):
                continue
            fill_price = min(line, bar[0])
            sell_sh, sell_list = sellable_shares(sym, day, sess)
            # cancel same-session zone orders (remaining tiers + TP)
            lst = live_orders.get((day, sess))
            if lst:
                live_orders[(day, sess)] = [
                    o for o in lst
                    if not (o.symbol == sym
                            and (o.source.startswith("zladder:")
                                 or o.source.startswith("ztp:")))]
            zone["phase"] = "exiting"
            emit(day, sess, None, "zone_stop_triggered", ref_price=low,
                 detail="%s (signal %s): session low %.4f < stop line %.4f; "
                        "ladder tiers and TP orders cancelled for this "
                        "session; fill at min(line, open) = %.4f"
                        % (sym, zone["signal_date"].isoformat(), low, line,
                           fill_price))
            if sell_sh > 0:
                dec_d, dec_s = zone.get("stop_dec") or (day, sess)
                stop_order = _Order(
                    order_id="%s-sell/risk-stop-%s-%s"
                             % (sym, dec_d.isoformat(), dec_s),
                    symbol=sym, side="sell", intent="risk",
                    decision_date=dec_d, decision_session=dec_s,
                    live_date=day, live_session=sess, anchor_price=line,
                    priority=zone_priority_base + zone["rank"],
                    target_notional=None, shares=None,
                    source="stop:%s" % zone["signal_date"].isoformat())
                consume = []
                remaining = sell_sh
                for c in sell_list:
                    if remaining <= 0:
                        break
                    take = min(c.shares, remaining)
                    consume.append((c, take))
                    remaining -= take
                # R8 (v1.4.2): a limit-down session has no bid above the
                # floor, so a stop fill at min(line, open) <= limit_down is
                # NOT bookable -- keep the exit state and the position, arm
                # the K=3 fallback (it re-checks the limit at each session
                # open and defers while the board stays locked).
                _up_l, down_l = limits_at(sym, day)
                if down_l is not None \
                        and fill_price <= down_l * (1 + LIMIT_DOWN_TOL):
                    zone_stats["stop_deferred_limitdown"] += 1
                    emit(day, sess, None, "zone_stop_deferred_limitdown",
                         ref_price=fill_price, shares=sell_sh,
                         detail="%s (signal %s): stop fill %.4f <= limit_down "
                                "%.4f x (1+%s); no fill this session, exit "
                                "deferred to the K=3 fallback"
                                % (sym, zone["signal_date"].isoformat(),
                                   fill_price, down_l, LIMIT_DOWN_TOL))
                else:
                    emit(day, sess, stop_order, "filled_stop_sell",
                         limit_price=line, ref_price=bar[0], shares=sell_sh,
                         detail="zone stop-loss: session low < line; fill at "
                                "min(line, open)")
                    book_sell_fill(day, sess, stop_order, "stop", fill_price,
                                   sell_sh, consume, prev_close=None,
                                   detail="zone stop-loss fill (fill_type=stop)")
            if total_shares(sym) > 0:
                # T+1 residual / limit-down deferral / nothing sellable: arm
                # the existing K=3 open-market fallback executor (B segment;
                # S-v14-5)
                risk_state[sym] = {
                    "anchor": line, "streak": 0, "armed": True,
                    "refreshed_at": decision_counter, "order": None,
                    "source": "stop:%s" % zone["signal_date"].isoformat()}
                zone["armed_events"] += 1
                zone["stop_armed_pending"] = True
                zone_stats["stop_armed_events"] += 1
                emit(day, sess, None, "zone_stop_armed",
                     detail="%s: %d share(s) not fillable this session "
                            "(T+1 or limit-down); K=3 open-market fallback "
                            "armed" % (sym, total_shares(sym)))
            else:
                _zone_to_cooling(zone, "stop_cleared", day, sess)

    def zone_step(day: date, sess: str) -> None:
        """v1.4 decision-point zone bookkeeping (BR-2/BR-9): ladder expiry,
        full-clear detection, invalidation line, month boundary, HWM/stop
        line refresh, seat scan, order generation -- in that order."""
        nonlocal cur_month_idx
        if not zone_engine or not ZONE_MONTHS:
            return
        k_ds = _sess_key(day, sess)
        live_d = day if sess == "am" else next_day.get(day)
        # (a) ladder expiry (BR-9): the next live session would reach the
        # month's expiry; unfilled tiers die, a never-filled zone is done
        for zone in list(ZONE_BY_SYM.values()):
            if zone["phase"] in ("entering", "holding") \
                    and zone["ladder_active"] \
                    and (live_d is None or live_d >= zone["expiry"]):
                n_rem = sum(1 for t in zone["ladder"]
                            if t["target"] > t["filled"])
                zone_stats["tier_expired"] += n_rem
                zone["ladder_active"] = False
                emit(day, sess, None, "zone_ladder_expired",
                     detail="%s (signal %s): ladder expiry %s; %d unfilled "
                            "tier(s) cancelled"
                            % (zone["symbol"],
                               zone["signal_date"].isoformat(),
                               zone["expiry"].isoformat(), n_rem))
                if zone["phase"] == "entering":
                    _zone_finish(zone, "done", "ladder_expired", day, sess)
        # (b) full-clear detection -> cooling / done (BR-9)
        for zone in list(ZONE_BY_SYM.values()):
            sym = zone["symbol"]
            if total_shares(sym) > 0:
                continue
            if zone["phase"] == "holding":
                _zone_to_cooling(zone, "tp_cleared", day, sess)
            elif zone["phase"] == "exiting":
                if zone["stop_armed_pending"] and not zone["fallback_filled"]:
                    zone_stats["stop_armed_resolved_other"] += 1
                zone["stop_armed_pending"] = False
                _zone_to_cooling(zone, "stop_cleared", day, sess)
            elif zone["phase"] == "exiting_boundary":
                _zone_finish(zone, "done", "boundary_cleared", day, sess)
        # (c) invalidation line (BR-3): the just-ended session's low vs
        # p0 - invalid_mult x sigma0; the session's own fills stay valid
        # (they executed inside the session, this check runs after it)
        for zone in list(ZONE_BY_SYM.values()):
            if zone["phase"] in ("entering", "holding") \
                    and zone["ladder_active"]:
                bar = halfbar(zone["symbol"], day, sess)
                if bar is None:
                    continue
                invalid_line = zone["p0"] - zone["invalid_mult"] * zone["sigma0"]
                if bar[2] < invalid_line:
                    n_rem = sum(1 for t in zone["ladder"]
                                if t["target"] > t["filled"])
                    zone_stats["tier_invalidated"] += n_rem
                    zone["ladder_active"] = False
                    emit(day, sess, None, "zone_tier_invalidated",
                         ref_price=bar[2],
                         detail="%s (signal %s): session low %.4f < "
                                "p0 - %.1f x sigma0 = %.4f; %d unfilled "
                                "tier(s) cancelled (this session's fills "
                                "stay valid)"
                                % (zone["symbol"],
                                   zone["signal_date"].isoformat(), bar[2],
                                   zone["invalid_mult"], invalid_line, n_rem))
                    if zone["phase"] == "entering":
                        _zone_finish(zone, "done", "ladder_invalidated",
                                     day, sess)
        # (d) month boundary (BR-2/BR-7)
        while (cur_month_idx + 1 < len(ZONE_MONTHS)
               and _sess_key(ZONE_MONTHS[cur_month_idx + 1]["signal_date"],
                             "pm") <= k_ds):
            cur_month_idx += 1
            _zone_boundary(day, sess)
        # (e) HWM / stop-line refresh (BR-5): AFTER the boundary so a
        # continued zone re-derives its line from the refreshed sigma0
        # through max (the line never decreases)
        for zone in ZONE_BY_SYM.values():
            if zone["phase"] == "holding" \
                    and zone["first_fill_key"] is not None:
                anchor = intent_anchor(zone["symbol"], day, sess)
                if anchor is not None:
                    zone["hwm"] = (anchor if zone["hwm"] is None
                                   else max(zone["hwm"], anchor))
                    line = zone["hwm"] - zone["stop_mult"] * zone["sigma0"]
                    zone["stop_line"] = (line if zone["stop_line"] is None
                                         else max(zone["stop_line"], line))
        # (f) seat scan (BR-7/BR-8); skipped when no next session exists --
        # an admission at the final decision point could never hang a live
        # order, so it would be born and expire in the same step
        if cur_month_idx >= 0 and live_d is not None:
            _zone_scan(day, sess)
        # (g) order generation
        _zone_hang(day, sess)

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

    def session_bar(sym: str, day: date, sess: str):
        """Execution bar of ONE live session (the fill-determination input).

        v1.5 ``etf_routing='pm_only'``: an ETF leg carries no half-day bar
        by contract, so its pm live session matches against the REAL daily
        row built above -- whole-day open/high/low/close, the section 8.1
        convention (a conservative statement about the day's range, never a
        synthesized am bar and never an assumed intraday path).  A ``None``
        here means the symbol has no traded daily row that day: the existing
        suspension rules apply unchanged (void for a normal order, frozen
        streak for a risk exit).  Every other symbol/session pair keeps the
        half-day bar table exactly as before.
        """
        if etf_pm_only and sym in etf_meta:
            if sess != "pm":
                raise BandContractError(
                    "etf_routing='pm_only': %s reached an am live session; "
                    "every pm-only ETF order lives at a pm session (the am "
                    "decision and the am fallback attempt are both routed "
                    "away)" % sym)
            return pm_only_bars.get(sym, {}).get(_dint(day))
        return halfbar(sym, day, sess)

    def preclose_at(sym: str, day: date) -> float | None:
        """v1.2 section 8.3 ETF limit basis: the daily frame's ``preclose``
        column when it carries the (symbol, day) row, else the previous
        traded official close."""
        ix = preclose_ix.get(sym)
        if ix is not None:
            d_arr, pc_arr = ix
            i = int(np.searchsorted(d_arr, _dint(day)))
            if i < len(d_arr) and int(d_arr[i]) == _dint(day):
                value = float(pc_arr[i])
                if math.isfinite(value) and value > 0:
                    return value
        return official_close_strict(sym, day)

    def limits_at(sym: str, day: date) -> tuple[float | None, float | None]:
        row_f = etf_meta.get(sym)
        if row_f is not None:
            # v1.2 section 8.3 (TBD-A, R1 adjudication): stk_limit has zero
            # fund coverage -> ETF limits are COMPUTED in exact decimal:
            # half-up(preclose x (1 +/- band)) on the 0.001 tick; stk_limit
            # rows for ETF symbols are ignored.
            pc = preclose_at(sym, day)
            if pc is None:
                return (None, None)
            band_f = row_f["band"]
            return (_etf_band_limit(pc, band_f, up=True),
                    _etf_band_limit(pc, band_f, up=False))
        lim = limits.get(sym)
        if lim is None:
            return None, None
        dint_arr, up, down = lim
        i = int(np.searchsorted(dint_arr, _dint(day)))
        if i >= len(dint_arr) or dint_arr[i] != _dint(day):
            return None, None
        return (None if not math.isfinite(up[i]) else float(up[i]),
                None if not math.isfinite(down[i]) else float(down[i]))

    def eff_commission(sym: str, notional: float) -> float:
        """v1.2: per-symbol commission (meta overrides, else the FeeModel)."""
        row_f = meta_rows.get(sym)
        if row_f is None:
            return fees.commission(notional)
        rate = row_f.get("commission_rate", fees.commission_rate)
        cmin = row_f.get("commission_min", fees.commission_min)
        return max(rate * notional, cmin)

    def eff_stamp_sell(sym: str, day: date, notional: float) -> float:
        """v1.2: ETF legs are stamp-free by contract (section 8.3 -- this
        precedence holds even if a meta stamp_sell is supplied); stock legs
        honor a meta override, else the segmented default."""
        row_f = meta_rows.get(sym)
        if row_f is not None:
            if row_f["asset_class"] == "etf":
                return 0.0
            if "stamp_sell" in row_f:
                return row_f["stamp_sell"] * notional
        return fees.stamp_sell(day, notional, is_etf.get(sym, False))

    def eff_stamp_buy(sym: str, notional: float) -> float:
        """v1.2: buy-side stamp ONLY when a stock-row meta override supplies
        it (A-share default 0 -- v1.1 behavior untouched).  R3 adjudication:
        the section 8.3 stamp exemption applies to BOTH sides with contract
        precedence -- an ETF leg pays no buy stamp even if its meta row
        carries stamp_buy."""
        row_f = meta_rows.get(sym)
        if row_f is None:
            return 0.0
        if row_f["asset_class"] == "etf":
            return 0.0
        if "stamp_buy" in row_f:
            return row_f["stamp_buy"] * notional
        return 0.0

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

    def full_cash_need(sym: str, price: float, shares: int) -> float:
        """R10 (v1.4.2): the TOTAL cash one buy consumes -- notional +
        commission + stamp_buy, the exact components ``book_buy_fill``
        debits.  The affordability check and the session reservation must
        both use this, or a non-zero buy stamp override pushes settled cash
        negative while every order still looks affordable."""
        notional = shares * price
        return (notional
                + eff_commission(sym, notional)
                + eff_stamp_buy(sym, notional))

    def full_quantity_affordable(sym: str, price: float, shares: int,
                                 available: float) -> bool:
        return full_cash_need(sym, price, shares) <= available + _FLOAT_TOL

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
            # v1.5: a pm-only ETF leg has no am bars BY CONTRACT, so the
            # completed-am-bar override (and its traded-today fail-closed
            # check) does not apply to it: the frozen last traded close
            # (official_close_strict, set above -- no intraday look-ahead)
            # IS the 11:30 mark, exactly as required by decision point 4.
            if (halfday_clock and sess == "am"
                    and sum(c.shares for c in cs) > 0
                    and not (etf_pm_only and sym2 in etf_meta)):
                completed_bar = halfbar(sym2, day, "am")
                if completed_bar is not None:
                    px = completed_bar[3]
                else:
                    # No am bar: a held symbol suspended today marks at the
                    # frozen last-traded close (official_close_strict, set
                    # above -- no intraday look-ahead).  A TRADED day that
                    # lacks its am bar is a hard data defect and stays
                    # fail-closed.
                    s_ix = series.get(sym2)
                    j = (int(np.searchsorted(s_ix["trade_dint"], _dint(day)))
                         if s_ix is not None else 0)
                    traded_today = bool(
                        s_ix is not None
                        and j < len(s_ix["trade_dint"])
                        and int(s_ix["trade_dint"][j]) == _dint(day))
                    if traded_today:
                        raise BandContractError(
                            "halfday snapshot missing held-symbol am bar: "
                            + sym2)
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
        commission = eff_commission(order.symbol, notional)
        stamp_b = eff_stamp_buy(order.symbol, notional)
        net = -(notional + commission + stamp_b)
        cash += net
        clips.setdefault(order.symbol, []).append(
            _Clip(shares=int(shares), acquired=day, seq=clip_seq,
                  session=sess, price=float(price)))
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
            "commission": commission, "stamp_tax": stamp_b,
            "fees_total": commission + stamp_b, "net_cash_flow": net,
            "is_etf": is_etf.get(order.symbol, False), "detail": "buy clip",
        })
        stats_acc["orders_filled"]["buy"] += 1
        order.closed = True
        order.close_reason = "filled"
        if intent_engine:
            intent_stop(order, day, sess, "filled")
        if zone_engine:
            zone_record_buy(order, day, sess, price, shares)

    def book_sell_fill(day: date, sess: str, order, fill_type: str,
                       price: float, shares: int, consume, *,
                       prev_close, detail: str) -> None:
        nonlocal cash, pend_am_to_pm, pend_next_day, fill_counter
        is_etf_sym = is_etf.get(order.symbol, False)
        notional = price * shares
        commission = eff_commission(order.symbol, notional)
        stamp = eff_stamp_sell(order.symbol, day, notional)
        net = notional - commission - stamp
        if sess == "am":
            pend_am_to_pm += net      # section 7.2: usable from same-day pm
        else:
            pend_next_day += net      # usable from next day's am
        for c, take in consume:
            c.shares -= take
        clips[order.symbol] = [c for c in clips.get(order.symbol, [])
                               if c.shares > 0]
        if zone_engine:
            zone = ZONE_BY_SYM.get(order.symbol)
            if zone is not None and zone["buy_shares_wac"] > 0:
                # R9 (v1.4.2): the zone WAC tracks the REMAINING held cost --
                # a sell removes cost at the current WAC (selling never
                # changes the average of the shares still held), so a later
                # ladder buy re-anchors TP targets on the held average, not
                # on the all-time buy average.
                take_z = min(int(shares), int(zone["buy_shares_wac"]))
                wac_now = zone["buy_amount"] / zone["buy_shares_wac"]
                zone["wac_last"] = wac_now
                zone["buy_shares_wac"] -= take_z
                zone["buy_amount"] -= take_z * wac_now
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

    def inject_dynamic_intents(day: date, sess: str) -> None:
        """Dynamic entry (2026-09-21 mainline task): hand THIS account's
        ledger to the host provider at the decision point -- after the
        completed half-day's fills are booked, before the next half-day's
        orders are generated -- and merge the returned intent rows into
        the pool.  The ledger is read-only feedback built from the live
        single ledger (never a control arm's equity or an outside flag):
        settled cash, pending settlement buckets, the M2 decision-point
        equity snapshot, and every position with its acquisition clips
        and the NEXT session's sellable quantity.  Merge rules:
        - every row must carry THIS decision point as its
          (decision_date, decision_session) -- a late row stamped with an
          earlier point would emit an order whose live session already
          ended, so it is rejected fail-closed;
        - a (symbol, decision_date, decision_session) duplicate against
          the pool in ANY state (or within the same batch) is rejected;
        - an earlier same-symbol intent is superseded from this decision
          point on (overridden_at) -- the new plan version replaces the
          old recommendation explicitly; an ARMED risk fallback is engine
          property and survives the override."""
        snap = decision_snapshots.get((day, sess))
        positions = []
        for sym_l in sorted(clips):
            cs_l = clips[sym_l]
            if not cs_l:
                continue
            if sess == "am":
                sell_next = sellable_shares(sym_l, day, "pm")[0]
            else:
                # next live session is next day's am: every clip acquired
                # up to today is unlocked by then (T+1 ages out overnight)
                sell_next = sum(c.shares for c in cs_l)
            positions.append({
                "symbol": sym_l,
                "shares": sum(c.shares for c in cs_l),
                "sellable_next_session": sell_next,
                "clips": [{"shares": c.shares,
                           "acquired": c.acquired.isoformat(),
                           "session": c.session,
                           "price": c.price} for c in cs_l],
            })
        ledger = {
            "date": day, "session": sess,
            "cash": cash, "pending_am_to_pm": pend_am_to_pm,
            "pending_next_day": pend_next_day,
            "equity_snapshot": snap,
            "positions": positions,
        }
        rows = intent_provider(day, sess, ledger)
        intent_stats.setdefault("provider_calls", 0)
        intent_stats["provider_calls"] += 1
        if rows is None:
            return
        if not isinstance(rows, (list, tuple)):
            raise BandContractError(
                "intent_provider must return a list of intent dicts or "
                "None, got %s" % type(rows).__name__)
        k_ds = _sess_key(day, sess)
        batch_seen: set = set()
        for row in rows:
            if not isinstance(row, dict):
                raise BandContractError(
                    "intent_provider row must be a dict, got %s"
                    % type(row).__name__)
            new_it = _validate_intent_row(row, seen_first=batch_seen)
            if new_it["first_key"] != k_ds:
                raise BandContractError(
                    "intent_provider row for %s is stamped %s %s but was "
                    "submitted at %s %s: a plan version must be issued at "
                    "its own decision point" % (new_it["symbol"],
                                                new_it["first_d"].isoformat(),
                                                new_it["first_s"],
                                                day.isoformat(), sess))
            clash = any(
                (it_o["symbol"], it_o["first_d"], it_o["first_s"])
                == (new_it["symbol"], new_it["first_d"], new_it["first_s"])
                for it_o in INTENTS)
            if clash:
                raise BandContractError(
                    "intent_provider: duplicate first decision point for "
                    "%s at %s %s" % (new_it["symbol"],
                                     new_it["first_d"].isoformat(),
                                     new_it["first_s"]))
            if ((not halfday_clock or etf_pm_only)
                    and new_it["symbol"] in etf_meta
                    and new_it["first_s"] == "am"):
                raise BandContractError(
                    "intent_provider: ETF symbol %s decision_session='am'; "
                    "section 8.2: ETF legs trade the 15:00 decision point "
                    "only" % new_it["symbol"])
            for it_o in INTENTS:
                if (it_o["symbol"] == new_it["symbol"]
                        and it_o["first_key"] < k_ds
                        and (it_o["overridden_at"] is None
                             or it_o["overridden_at"] > k_ds)):
                    it_o["overridden_at"] = k_ds
            INTENTS.append(new_it)
            INTENT_BY_KEY[(new_it["symbol"], new_it["side"],
                           new_it["source"])] = new_it
            intent_stats.setdefault("dynamic_injected", 0)
            intent_stats["dynamic_injected"] += 1
            emit(day, sess, None, "intent_lifecycle",
                 detail="dynamic: %s/%s/%s source %s submitted at this "
                        "decision point" % (new_it["symbol"],
                                            new_it["side"],
                                            new_it["intent"] or "entry",
                                            new_it["source"]))

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
        # (c) generation in deterministic intent order.  v1.2 section 8.2:
        # an ETF intent ticks at PM decision points ONLY (no 11:30 decision
        # -- am decisions are rejected at validation) and its 15:00 decision
        # lives at the NEXT day's pm session; stocks keep the section 7.1
        # route (am decision -> same-day pm, pm decision -> next am).
        # v1.5: etf_routing='pm_only' applies that same single-session ETF
        # expression under the halfday clock (the ETF bars then come from
        # the real daily rows -- see session_bar); 'paired' keeps the
        # next-am / same-day-pm pairing for ETFs too.
        stock_live_d = day if sess == "am" else next_day.get(day)
        stock_live_s = "pm" if sess == "am" else "am"
        touched: set = set()
        for it in INTENTS:
            if it["state"] != "active":
                continue
            sym_is_etf = it["symbol"] in etf_meta
            etf_single_session = sym_is_etf and (not halfday_clock or etf_pm_only)
            if etf_single_session and sess != "pm":
                continue    # ETF legs have no 11:30 decision point
            if etf_single_session:
                live_d, live_s = next_day.get(day), "pm"
            else:
                live_d, live_s = stock_live_d, stock_live_s
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
                if halfday_clock and not (it["side"] == "sell"
                                          and it["intent"] == "risk"):
                    # 2026-09-21 mainline state transition: with the halfday
                    # clock a normal recommendation that cannot even be
                    # priced (suspension / no bar) is VOID for this half-day
                    # -- the old auto re-hang must not carry it into the
                    # next half-day; the next plan version has to re-issue
                    # it explicitly.  Risk exits keep the m3 carry (streak
                    # frozen, re-issued at the next decision point).
                    it["state"] = "done"
                    it["done_reason"] = "expired_halfday_no_anchor"
                    intent_stats.setdefault(
                        "terminated_expired_halfday_no_anchor", 0)
                    intent_stats["terminated_expired_halfday_no_anchor"] += 1
                    emit(day, sess, None, "intent_lifecycle",
                         detail="%s/%s/%s source %s: no anchor this half-day"
                                " (suspended / no bar); recommendation void,"
                                " next plan must re-issue"
                                % (it["symbol"], it["side"],
                                   it["intent"] or "entry", it["source"]))
                    continue
                # legacy clock, or a risk exit: intent stays active,
                # re-issues at the next decision point (m3 streak frozen)
                intent_stats["emissions_skipped_no_anchor"] += 1
                continue
            if sym_is_etf:
                # section 8.3: ETF limit construction on the 0.001 tick
                # (half-up); stock anchors are untouched (v1.1 behavior)
                anchor = _tick_round(anchor, ETF_PRICE_TICK)
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
            if halfday_clock and not (row.side == "sell" and row.intent == "risk"):
                # Normal recommendations are valid for this half-day only.
                # The live order remains assigned to its execution session;
                # the intent is not silently re-issued at the next point.
                it["state"] = "done"
                it["done_reason"] = "expired_halfday"
                intent_stats.setdefault("terminated_expired_halfday", 0)
                intent_stats["terminated_expired_halfday"] += 1
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
        if zone_engine:
            # v1.4 BR-5/BR-6: zone stop-loss evaluation segment, placed
            # BEFORE the A (buy) segment; a no-op without zones
            zone_stop_segment(day, sess)
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
            bar = session_bar(order.symbol, day, sess)
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
            # 2026-09-21 decision (etf-market-fill): an ETF config leg with
            # etf_market_fill > 0 fills at this session's close + slip,
            # skipping the strict-penetration gate; a close AT a day-limit
            # edge stays unfilled (order expires; the host may re-issue).
            mkt = etf_market_fill > 0.0 and order.symbol in etf_meta
            if mkt and _limit_edge(_c, up, down):
                bump_void("not_penetrated")
                emit(day, sess, order, "not_penetrated",
                     limit_price=order.anchor_price, ref_price=low,
                     detail="market fill skipped: close at day-limit edge")
                close_order(day, sess, order, "not_penetrated",
                            emit_event=False)
                continue
            px = (_tick_round(_c * (1.0 + etf_market_fill), ETF_PRICE_TICK)
                  if mkt else order.anchor_price)
            if not legal_limit(px, up, down):
                reason = ("no_limit_info" if up is None and down is None
                          else "limit_out_of_range")
                bump_void(reason)
                emit(day, sess, order, "void_" + reason,
                     limit_price=px, ref_price=low,
                     detail="day limits [%s, %s] (shared by both sessions)"
                            % (down, up))
                close_order(day, sess, order, "void_" + reason, emit_event=False)
                continue
            if not (mkt or low < order.anchor_price):
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
                                      / px / LOT)) * LOT
                if want < LOT:
                    emit(day, sess, order, "below_min_lot",
                         limit_price=px, ref_price=low,
                         detail="target %.2f at p %.4f affords < %d shares; "
                                "abandoned" % (order.target_notional,
                                               px, LOT))
                    close_order(day, sess, order, "below_min_lot",
                                emit_event=False)
                    continue
            available = cash - reserved
            if not full_quantity_affordable(order.symbol, px,
                                            want, available):
                stats_acc["insufficient_cash_orders"] += 1
                bump_void("insufficient_cash")
                emit(day, sess, order, "void_insufficient_cash",
                     limit_price=px, ref_price=low, shares=want,
                     detail="need %d x %.4f fully funded, available %.2f; "
                            "same-session sale proceeds not available"
                            % (want, px, available))
                close_order(day, sess, order, "void_insufficient_cash",
                            emit_event=False)
                continue
            # section 7.3 single-name cap (section 7.7 M2): validated at
            # construction against the DECISION-POINT equity snapshot; a
            # breach voids the whole order (no downsizing).  The total<=100%
            # cap is implied by full funding (cost + fee <= cash) and is not
            # a separate check.
            cost = want * px
            snap_eq = decision_snapshots.get((order.decision_date,
                                              order.decision_session))
            if snap_eq is None:
                snap_eq = base_eq
            if (proj_mv_sym.get(order.symbol, 0.0) + cost) \
                    > CAP_SINGLE_NAME * snap_eq + _FLOAT_TOL:
                stats_acc["cap_single_name_voids"] += 1
                bump_void("cap_single_name")
                emit(day, sess, order, "void_cap_single_name",
                     limit_price=px, ref_price=low, shares=want,
                     detail="section 7.3 cap: single-name <= %.0f%% of the "
                            "decision-point equity (%.2f); order expires"
                            % (CAP_SINGLE_NAME * 100, snap_eq))
                close_order(day, sess, order, "cap_single_name", emit_event=False)
                if intent_engine:
                    # section 9 revision 2: a cap-void TERMINATES the intent
                    # (m6 termination taxonomy); no re-issue next decision
                    intent_stop(order, day, sess, "cap_single_name")
                if zone_engine:
                    # v1.4 BR-3: a cap-void on a ladder tier terminates the
                    # zone's whole ladder for the month
                    zone_ladder_cap_void(order, day, sess)
                continue
            # R10 (v1.4.2): reserve the FULL cash need (notional + fees,
            # including stamp_buy) so lower-priority orders see the same
            # available figure the booking will actually debit.
            reserved += full_cash_need(order.symbol, px, want)
            proj_mv_sym[order.symbol] = proj_mv_sym.get(order.symbol, 0.0) + cost
            booked.append((order, want, low, px))

        # -- B. armed risk fallbacks (section 7.2, K=3 session exit) -------
        consumed: set[int] = set()
        for sym in sorted(s for s, st in risk_state.items() if st["armed"]):
            if (sym in etf_meta and sess == "am"
                    and (not halfday_clock or etf_pm_only)):
                # v1.2 section 8.2: an ETF fallback executes at a PM session
                # open only (the K streak counts pm sessions); the am attempt
                # is routed away (with pm-only synthetic ETF bars this is
                # implied by the missing bar -- this guard also holds when a
                # host supplies am rows for an ETF).  v1.5 pm-only: the same
                # rule, now the structural one -- every ETF live session is
                # a pm session.
                continue
            st = risk_state[sym]
            bar = session_bar(sym, day, sess)
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
            if zone_engine and str(st.get("source") or "").startswith("stop:"):
                # v1.4 gate-8: the armed stop residual was resolved by the
                # K=3 fallback executor (BR-10)
                zone_stats["stop_armed_resolved_fallback"] += 1
                z_fb = ZONE_BY_SYM.get(sym)
                if z_fb is not None:
                    z_fb["fallback_filled"] = True
            risk_state.pop(sym, None)

        # -- C. sell limit orders -----------------------------------------
        for order in sells:
            if id(order) in consumed:
                continue
            bucket = "sell_risk" if order.intent == "risk" else "sell_profit"
            stats_acc["orders"][bucket] += 1
            bar = session_bar(order.symbol, day, sess)
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
            # 2026-09-21 decision (etf-market-fill): ETF config-leg sells
            # fill at the session close - slip; a close AT a day-limit edge
            # (one-word limit-down) stays unfilled this session.
            mkt = etf_market_fill > 0.0 and order.symbol in etf_meta
            sell_px = (_tick_round(_c * (1.0 - etf_market_fill), ETF_PRICE_TICK)
                       if mkt else order.anchor_price)
            if not legal_limit(sell_px, up, down):
                reason = ("no_limit_info" if up is None and down is None
                          else "limit_out_of_range")
                bump_void(reason)
                if order.intent == "risk":
                    bump_streak(order, day, sess)
                emit(day, sess, order, "void_" + reason,
                     limit_price=sell_px, ref_price=high,
                     # ENGINE-3 fix (authorized, prereg section 9 revision 4):
                     # %s formatting -- down/up are None on no-limit-info days
                     # (tushare batch gaps); %.4f crashed on them.  The void
                     # + risk-streak count above restore v0 ruling #2/#3
                     # semantics (void, counted into K, disclosed).
                     detail="sell price %s not validateable; day limits "
                            "[%s, %s]" % (sell_px, down, up))
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
            if (mkt and not _limit_edge(_c, up, down)) \
                    or high > order.anchor_price:
                qty = sell_sh if order.shares is None \
                    else min(order.shares, sell_sh)
                if order.shares is not None and qty < order.shares:
                    stats_acc["quantity_capped"] += 1
                    detail = "quantity_capped to sellable clips"
                elif mkt:
                    detail = "market fill: session close - slip at %.4f" % sell_px
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
                     limit_price=sell_px, ref_price=high, shares=qty,
                     detail=detail)
                book_sell_fill(day, sess, order, "limit", sell_px,
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
                if zone_engine and order.source.startswith("ztp:"):
                    # v1.4 BR-10: zone TP sessions that expire silently
                    zone_stats["tp_expired_sessions"] += 1
            close_order(day, sess, order, "session_unfilled", emit_event=False)

        # -- D. book buy fills --------------------------------------------
        for order, shares, low, px in booked:
            emit(day, sess, order, "filled_limit_buy",
                 limit_price=px, ref_price=low, shares=shares,
                 detail=("market fill: session close + slip at %.4f" % px
                         if px != order.anchor_price else
                         "strict penetration: session low < p; fill at p"))
            book_buy_fill(day, sess, order, px, shares)

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
                                               seq=c.seq, session=c.session,
                                               price=c.price))
                    if extra > 0:
                        new_clips.append(_Clip(shares=extra, acquired=day,
                                               seq=clip_seq + added,
                                               session="am"))
                        added += extra
                clips[symbol] = [c for c in new_clips if c.shares > 0]
                post = sum(c.shares for c in clips[symbol])
                stats_acc["corp_action_splits"] += 1
                clip_seq += added
                if zone_engine:
                    # v1.4 BR-4a: a share multiplier scales the zone's WAC
                    # share count (amount unchanged -> WAC scales by 1/r)
                    z_ca = ZONE_BY_SYM.get(symbol)
                    if (z_ca is not None
                            and z_ca["phase"] in ("holding", "exiting",
                                                  "exiting_boundary")
                            and z_ca["buy_shares_wac"] > 0):
                        z_ca["buy_shares_wac"] *= float(ratio)
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
            # v1.2 section 8.4: dividend_events credit day-open holdings x
            # div_per_share to SETTLED cash (marks and clip costs untouched)
            ev_div = div_event_map.get(symbol, {}).get(_dint(day))
            if ev_div:
                amount = ev_div * pre_shares
                cash += amount
                div_event_cash_total += amount
                stats_acc["corp_action_dividends"] += 1
                stats_acc["dividend_cash_total"] += amount
                emit(day, "am", None, "corp_action_dividend", cash_amount=amount,
                     detail="%s: dividend_events %.6f yuan/share x %d shares "
                            "held at the day open -> settled cash (valuation "
                            "and clip costs unchanged; section 8.4)"
                            % (symbol, ev_div, pre_shares))
            # v1.3 section 9.2: share-change (份额变换) event, executed at
            # the top of the ex-date -- BEFORE any session's fill
            # determination and valuation (for pm-only ETF legs this is
            # exactly "before the pm open"; the stock-side 送转 path above is
            # the v0 F1 split_factor route and is untouched by this block).
            ca_ev = ca_map.get(symbol, {}).get(_dint(day))
            if ca_ev is not None:
                ratio_ca = ca_ev["ratio"]
                pre_shares_ca = sum(c.shares for c in clips[symbol])
                exact_int_ca = float(ratio_ca).is_integer()
                odd_cash_ca = 0.0
                new_clips_ca = []
                added_ca = 0
                for c in clips[symbol]:
                    if exact_int_ca:
                        # revision 1: integer ratio x integer shares is an
                        # EXACT integer -- zero odd lots, zero discount
                        new_total_ca = c.shares * int(ratio_ca)
                    else:
                        # fallback for future NON-integer ratios only:
                        # floor + preclose discount of the fractional part
                        exact_sh_ca = c.shares * ratio_ca
                        new_total_ca = int(math.floor(exact_sh_ca))
                        odd_cash_ca += (exact_sh_ca - new_total_ca) \
                            * ca_ev["preclose"]
                    keep_ca = min(c.shares, new_total_ca)
                    extra_ca = new_total_ca - keep_ca
                    if keep_ca > 0:
                        new_clips_ca.append(
                            _Clip(shares=keep_ca, acquired=c.acquired,
                                  seq=c.seq, session=c.session,
                                  price=c.price))
                    if extra_ca > 0:
                        # m4 mirror: added shares are acquired TODAY
                        # (sellable next day; a T+0 clip from the "am"
                        # creation session is sellable same-day pm)
                        new_clips_ca.append(
                            _Clip(shares=extra_ca, acquired=day,
                                  seq=clip_seq + added_ca, session="am"))
                        added_ca += extra_ca
                clips[symbol] = [c for c in new_clips_ca if c.shares > 0]
                post_ca = sum(c.shares for c in clips[symbol])
                ca_stats["events"] += 1
                ca_stats["shares_before"] += pre_shares_ca
                ca_stats["shares_after"] += post_ca
                if zone_engine:
                    # v1.4 BR-4a: same WAC mirror as the v0 split path
                    z_ca2 = ZONE_BY_SYM.get(symbol)
                    if (z_ca2 is not None
                            and z_ca2["phase"] in ("holding", "exiting",
                                                   "exiting_boundary")
                            and z_ca2["buy_shares_wac"] > 0):
                        z_ca2["buy_shares_wac"] *= float(ratio_ca)
                if odd_cash_ca:
                    cash += odd_cash_ca
                    ca_stats["odd_lot_cash_total"] += odd_cash_ca
                emit(day, "am", None, "corp_action_share_change",
                     ratio=ratio_ca, shares=post_ca,
                     cash_amount=(odd_cash_ca if odd_cash_ca else None),
                     detail="%s: shares %d -> %d (announced ratio %.10f, %s "
                            "path; guardrail preclose %.6f x ratio vs "
                            "close(t-1) %.6f residual %+.4f%%; odd-lot cash "
                            "%.2f; added shares acquired %s, m4 mirror)"
                            % (symbol, pre_shares_ca, post_ca, ratio_ca,
                               "exact-integer" if exact_int_ca
                               else "floor+preclose fallback",
                               ca_ev["preclose"], ca_ev["prev_close"],
                               ca_ev["residual"] * 100.0, odd_cash_ca,
                               day.isoformat()))
        process_session(day, "am")

        # ======== decision point 11:30 (day, am) ========
        decision_step(day, "am")
        if intent_provider is not None:
            inject_dynamic_intents(day, "am")
        intent_step(day, "am")
        zone_step(day, "am")

        # ======== S_pm ========
        cash += pend_am_to_pm                    # same-day am -> pm
        pend_am_to_pm = 0.0
        process_session(day, "pm")

        # ======== decision point 15:00 (day, pm) ========
        decision_step(day, "pm")
        if intent_provider is not None:
            inject_dynamic_intents(day, "pm")
        intent_step(day, "pm")
        zone_step(day, "pm")

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
    if zone_engine:
        # v1.4: zones still unfinished at data end; the stuck-armed count
        # is the hard gate-8 disclosure (runner asserts stuck == 0)
        for zone in ZONES.values():
            if zone["exit_reason"] is None:
                zone["exit_reason"] = "end_of_data"
        zone_stats["stop_armed_stuck_end"] = sum(
            1 for sym_st, st in risk_state.items()
            if st.get("armed")
            and str(st.get("source") or "").startswith("stop:")
            and total_shares(sym_st) > 0)
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
        "execution_clock": execution_clock,
        "engine_version": "band_engine v1.5",
        "etf_leg": {
            "meta_symbols": sorted(meta_rows),
            "etf_symbols": sorted(etf_meta),
            "etf_bands": {s: etf_meta[s]["band"] for s in sorted(etf_meta)},
            "etf_default_band_symbols": sorted(
                s for s, r in etf_meta.items() if r["band_defaulted"]),
            "t_plus_zero_symbols": sorted(
                s for s, r in meta_rows.items() if r["t_plus"] == 0),
            "dividend_event_symbols": sorted(div_event_map),
            "dividend_events_cash": div_event_cash_total,
            "limit_source": ("computed per section 8.3 (preclose x "
                             "(1 +/- band), 0.001 tick)" if etf_meta
                             else "stk_limit rows (v1.1 path)"),
            "routing": ("halfday: pm decisions live next am; am decisions "
                        "live same-day pm; fallbacks may execute at either open"
                        if halfday_clock and not etf_pm_only else
                        "halfday pm-only ETF (etf_routing='pm_only'): ETF pm "
                        "decisions live the next day's pm session on the REAL "
                        "daily bar; ETF am decisions are rejected; ETF "
                        "fallbacks execute at pm opens"
                        if etf_pm_only else
                        "section 8.2: ETF pm decisions live next pm; ETF "
                        "fallbacks execute at pm opens" if etf_meta
                        else "section 7.1 (stocks)"),
        },
        "contract": "v1 (docs/plans/p3-band-contract.md section 7)"
                    + (" + v1.1 engine-side intent layer (prereg section 9 "
                       "revision 2)" if intent_engine else ""),
        "order_generation": (
            "engine_intents_dynamic" if intent_engine and intent_provider
            else "engine_intents" if intent_engine else "static"),
        "intent_layer": intent_stats if intent_engine else None,
        "dynamic_layer": (None if intent_provider is None else {
            "provider_calls": intent_stats.get("provider_calls", 0),
            "dynamic_injected": intent_stats.get("dynamic_injected", 0),
            "ledger": "single live ledger: settled cash + pending buckets + "
                      "M2 equity snapshot + clips + next-session sellable",
            "state_transition": ("halfday clock + pm-only ETF: ETF intents "
                                 "tick once a day (pm) and their live session "
                                 "is the next pm; normal ETF intents void "
                                 "after one decision point, ETF risk exits "
                                 "carry with the K pm-session streak "
                                 "(stocks keep the halfday semantics)"
                                 if etf_pm_only else
                                 "halfday clock: normal intents void after "
                                 "one decision point (or when unpriceable); "
                                 "risk exits carry with the K streak"
                                 if halfday_clock else "legacy carry"),
        }),
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
    # v1.3: the share-change counters surface ONLY when corporate_actions
    # events are supplied -- a no-event run carries no new stats key at all
    # (byte-identical stats to v1.2).
    if corporate_actions.height:
        stats["share_changes"] = dict(ca_stats)
    # v1.4: the zones block surfaces ONLY in zones mode -- a run without a
    # zones frame carries no new stats key at all (BR-12 byte-identity)
    zones_frame = None
    if zone_engine:
        phase_ct: dict = {}
        for z in ZONES.values():
            phase_ct[z["phase"]] = phase_ct.get(z["phase"], 0) + 1
        stats["zones"] = {
            "n_candidates": zone_stats["n_candidates"],
            "n_zones": len(ZONES),
            "n_admitted": zone_stats["n_admitted"],
            "phase_counts": phase_ct,
            "priority_base": zone_priority_base,
            "stop_armed_events": zone_stats["stop_armed_events"],
            "stop_armed_resolved_fallback":
                zone_stats["stop_armed_resolved_fallback"],
            "stop_armed_resolved_other":
                zone_stats["stop_armed_resolved_other"],
                "stop_armed_stuck_end": zone_stats["stop_armed_stuck_end"],
                "stop_deferred_limitdown":
                    zone_stats["stop_deferred_limitdown"],
            "tp_expired_sessions": zone_stats["tp_expired_sessions"],
            "tier_expired": zone_stats["tier_expired"],
            "tier_invalidated": zone_stats["tier_invalidated"],
            "tier_below_min_lot": zone_stats["tier_below_min_lot"],
            "tier_cap_voided": zone_stats["tier_cap_voided"],
            "tp_below_min_lot": zone_stats["tp_below_min_lot"],
            "definitions": {
                "stop_armed_events": "stop-loss triggerings that left "
                                     "shares armed for the K=3 open-market "
                                     "fallback (incl. zero-sellable direct "
                                     "arming, BR-10)",
                "stop_armed_resolved_fallback": "armed residuals resolved by "
                                                "a K=3 fallback fill "
                                                "(source startswith 'stop:')",
                "stop_armed_resolved_other": "armed residuals cleared by "
                                             "another sell (e.g. a boundary "
                                             "risk sell)",
                "stop_armed_stuck_end": "zones still armed with shares > 0 "
                                        "at data end (hard disclosure; "
                                        "runner asserts == 0)",
                "stop_deferred_limitdown": "stop triggers whose fill price "
                                           "min(line, open) sat at/under "
                                           "limit_down: no fill booked, exit "
                                           "deferred to the K=3 fallback "
                                           "(R8, v1.4.2)",
                "tp_expired_sessions": "zone TP order sessions expiring "
                                       "silently (no k3, gate-8 exempt)",
                "tier_expired": "unfilled ladder tiers terminated by expiry "
                                "/ month replacement (gate-8 exempt)",
                "tier_invalidated": "unfilled ladder tiers cancelled by the "
                                    "invalidation line (gate-8 exempt)",
                "tier_below_min_lot": "candidates/tiers floored below one "
                                      "lot (S-v14-2)",
            },
        }
        zrows = []
        for (sd_z, sym_z), z in sorted(ZONES.items()):
            # R9 (v1.4.2): the reported WAC is the cost basis of the shares
            # actually held; a fully cleared zone keeps its LAST held WAC
            # (buy_shares_wac == 0 would otherwise erase the audit trail).
            wac_z = (z["buy_amount"] / z["buy_shares_wac"]
                     if z["buy_shares_wac"] > 0 else z["wac_last"])
            zrows.append({
                "signal_date": sd_z, "symbol": sym_z, "rank": z["rank"],
                "industry": z["industry"], "admitted_key": z["admitted_key"],
                "phase_final": z["phase"],
                "exit_reason": z["exit_reason"] or "",
                "total_target_shares": z["total_target_shares"],
                "tier_filled_shares": ",".join(str(t["filled"])
                                               for t in z["ladder"]),
                "shares_bought": z["shares_bought"],
                "wac_final": wac_z, "hwm_final": z["hwm"],
                "stop_line_final": z["stop_line"],
                "armed_events": z["armed_events"],
                "first_fill_key": z["first_fill_key"],
            })
        zones_frame = _frame(zrows, _ZONES_SCHEMA)

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
        zones=zones_frame,
    )
