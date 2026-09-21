"""P2-R6 ETF rotation/momentum screen (exp-20260917-p2r6-etf-rotation).

Strategy-level replay of the 12 preregistered rotation configs on the
historically-point-in-time ETF pool built from fund_basic x fund_daily x
fund_adj (batch identities and every parameter frozen in
``configs/experiments/p2r6-etf-rotation.json`` BEFORE any signal code ran).

Fixed semantics (all registered in the frozen config):

- eligibility is a pure ROW property of the per-ETF feature table computed
  with data known at each close: registry bounds (list_date <= t-120 calendar
  sessions, delist_date empty or > t), >=120 own quote rows, 20-own-row
  median amount >= 50k file-units (measured thousand-CNY), quoted at t,
  adjusted series known at t.  Delisting information is never a signal input.
- adjusted series = unadjusted price x fund_adj factor joined asof-backward
  per code (picks up factor changes on suspended days).
- monthly/weekly signal at the last session of each month/ISO week; trades at
  the NEXT session's open; Top3 by mean cross-sectional percentile rank of
  R_k (ties by ts_code asc); absolute gate = adj_close > SMA120 AND R60 > 0
  (gate-on: TopN drawn only from gate-passers, empty slots cash); incumbents
  kept, only leavers sold / entrants bought; entry failures skip and backfill
  by rank; exit failures postpone to the next tradable open (replacement buys
  for still-busy slots are cancelled, 3 slots max); held ETFs whose quotes end
  are force-exited at the last available close with fees (never on the entry
  session itself -- T+1); 9.5% open-vs-preclose proxy blocks limit trades.
- 3 independent slots, fixed entry budget capital/3 (fractional shares); slot
  cash may go negative after a loss followed by re-entry (fixed-notional
  assumption, disclosed); equity = sum of slot values.
- segment metrics are slices of ONE continuous equity curve (boundary
  mark-to-market carry, no forced close); the test slice is evaluated once.
- fees: single-branch FeeBand (commission 0.01%, min 5 CNY, stamp 0) reusing
  the screen-layer convention; slippage 0.

Benchmarks: B1 same-pool equal weight (full rebalance every signal period,
per-leg notional 200,000/N, last-close fallback for failed exits), B2 510300
buy-and-hold per segment, B3 random Top3 through the same engine (seeds
17..36), B4 cash 0%.

This is a coarse screening layer (vectorbt-class), not account-level proof.
"""
from __future__ import annotations

import statistics
from bisect import bisect_right
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Callable

import polars as pl

from quant.research.screen import FeeBand

ETF_FEE_BAND = FeeBand(from_date=date(2015, 1, 1), commission_pct=0.0001,
                       commission_min=5.0, stamp_sell_pct=0.0)
GROSS_FEE_BAND = FeeBand(from_date=date(2015, 1, 1), commission_pct=0.0,
                         commission_min=0.0, stamp_sell_pct=0.0)

LIMIT_PCT = 0.095  # registered uniform proxy; stk_limit does not cover funds
FREEZE_END = date(2024, 12, 31)
N_SLOTS = 3
MAX_LEG_FRAC = 0.25  # R7 registered per-name cap: min(exposure/N, 25%)


# --------------------------------------------------------------------------- #
# data loading
# --------------------------------------------------------------------------- #
def _read_chunk(path: Path) -> pl.DataFrame:
    return (pl.read_csv(path, infer_schema_length=0)
            .select('ts_code', 'trade_date', 'open', 'close', 'pre_close', 'amount')
            .with_columns(
                pl.col('trade_date').str.to_date('%Y%m%d'),
                *(pl.col(c).cast(pl.Float64, strict=False)
                  for c in ('open', 'close', 'pre_close', 'amount'))))


def registry_frame(root: Path, config: dict) -> pl.DataFrame:
    """Whitelisted registry rows after the U2 category + QDII-keyword filter."""
    basic = pl.read_csv(root / config['data']['fund_basic']['batch']
                        / config['data']['fund_basic']['file'], infer_schema_length=0)
    reg = basic.select(
        'ts_code', 'name', 'fund_type',
        pl.col('list_date').str.to_date('%Y%m%d', strict=False),
        pl.col('delist_date').str.to_date('%Y%m%d', strict=False))
    reg = reg.filter(pl.col('ts_code').is_in(list(config['u1_whitelist_frozen'])))
    qdii = config['universe']['u2_qdii_keywords_frozen']
    keep_types = config['universe']['u2_category']['fund_type_in']
    name = pl.col('name').fill_null('')
    return reg.filter(pl.col('fund_type').is_in(keep_types)
                      & ~pl.any_horizontal([name.str.contains(k) for k in qdii]))


def load_frames(root: Path, config: dict) -> dict:
    """Load whitelisted fund_daily + fund_adj chunks; asof-join factors;
    compute per-ETF rolling features, calendar indices and registry bounds."""
    whitelist = set(config['u1_whitelist_frozen'])
    daily_dir = root / config['data']['fund_daily']['batch']
    adj_dir = root / config['data']['fund_adj']['batch']

    frames: list[pl.DataFrame] = []
    for path in sorted(daily_dir.glob('chunk_*.csv')):
        code = path.stem.removeprefix('chunk_')
        if code not in whitelist:
            continue
        d = _read_chunk(path)
        a = (pl.read_csv(adj_dir / f'chunk_{code}.csv', infer_schema_length=0)
             .select(pl.col('trade_date').str.to_date('%Y%m%d'),
                     pl.col('adj_factor').cast(pl.Float64, strict=False)))
        j = d.sort('trade_date').join_asof(
            a.sort('trade_date'), on='trade_date', strategy='backward')
        frames.append(j.with_columns(pl.lit(code).alias('ts_code')))
    daily = (pl.concat(frames, how='vertical').sort('ts_code', 'trade_date')
             .filter(pl.col('trade_date') <= FREEZE_END))

    feat = daily.with_columns(
        (pl.col('open') * pl.col('adj_factor')).alias('adj_open'),
        (pl.col('close') * pl.col('adj_factor')).alias('adj_close'))
    feat = (feat.with_columns(
        pl.int_range(pl.len()).over('ts_code').add(1).alias('row_idx'))
        .with_columns([(pl.col('adj_close')
                        / pl.col('adj_close').shift(k).over('ts_code') - 1.0)
                       .alias(f'r{k}') for k in (20, 60, 120)])
        .with_columns(pl.col('adj_close')
                      .rolling_mean(120, min_samples=120).over('ts_code')
                      .alias('sma120'))
        .with_columns(pl.col('amount')
                      .rolling_median(20, min_samples=20).over('ts_code')
                      .alias('amount_med20')))

    feat = feat.join(registry_frame(root, config), on='ts_code', how='inner')

    cal = (feat.select('trade_date').unique().sort('trade_date')
           .with_row_index('cal_idx').with_columns(pl.col('cal_idx').cast(pl.Int32)))
    feat = feat.join(cal, on='trade_date', how='inner')
    # first calendar session ON/AFTER list_date (forward asof): ETFs listed
    # before the window start map to the first session, so their registry
    # bound is satisfied by quote history alone
    list_bounds = (feat.select('ts_code', 'list_date').unique().sort('list_date')
                   .join_asof(cal.rename({'trade_date': '_lcd'}),
                              left_on='list_date', right_on='_lcd',
                              strategy='forward')
                   .rename({'cal_idx': 'list_cal_idx'})
                   .select('ts_code', 'list_cal_idx'))
    feat = feat.join(list_bounds, on='ts_code', how='inner')
    last_dates = feat.group_by('ts_code').agg(pl.col('trade_date').max().alias('_last'))
    feat = (feat.join(last_dates, on='ts_code')
            .with_columns((pl.col('trade_date') == pl.col('_last')).alias('last_row'))
            .drop('_last')
            .with_columns(
                (pl.col('list_cal_idx').is_not_null()
                 & (pl.col('cal_idx') - pl.col('list_cal_idx') >= 120)).alias('list_ok'),
                (pl.col('delist_date').is_null()
                 | (pl.col('trade_date') < pl.col('delist_date'))).alias('delist_ok')))

    liquidity_min = float(config['universe']['u3_pit_rules']['liquidity_min_units'])
    feat = feat.with_columns(
        (pl.col('list_ok') & pl.col('delist_ok')
         & (pl.col('row_idx') >= 120)
         & (pl.col('amount_med20') >= liquidity_min)
         & pl.col('adj_close').is_not_null() & pl.col('adj_close').is_finite()
         ).alias('eligible'),
        ((pl.col('adj_close') > pl.col('sma120'))
         & (pl.col('r60') > 0)).alias('gate_ok'))

    stats = {'rows_whitelisted': feat.height,
             'codes_whitelisted': feat['ts_code'].n_unique(),
             'rows_missing_factor': int(feat['adj_factor'].null_count()),
             'codes_missing_factor': int(
                 feat.filter(pl.col('adj_factor').is_null())['ts_code'].n_unique())}
    return {'feat': feat, 'stats': stats}


# --------------------------------------------------------------------------- #
# calendar helpers
# --------------------------------------------------------------------------- #
def build_calendar(feat: pl.DataFrame) -> list[date]:
    return feat.select('trade_date').unique().sort('trade_date')['trade_date'].to_list()


def rebalance_days(calendar: list[date], freq: str, start: date) -> list[date]:
    """Monthly: last session of each calendar month.  Weekly: last session of
    each ISO week.  Only days >= ``start`` are returned."""
    groups: dict[tuple, date] = {}
    for d in calendar:
        if d < start:
            continue
        if freq == 'monthly':
            key = (d.year, d.month)
        elif freq == 'weekly':
            iso = d.isocalendar()
            key = (iso[0], iso[1])
        else:
            raise ValueError(f'unknown freq {freq!r}')
        groups[key] = d
    return sorted(groups.values())


def next_session_index(calendar: list[date], day: date) -> int | None:
    """First calendar index strictly after ``day`` (None at the end)."""
    lo, hi = 0, len(calendar)
    while lo < hi:
        mid = (lo + hi) // 2
        if calendar[mid] <= day:
            lo = mid + 1
        else:
            hi = mid
    return lo if lo < len(calendar) else None


def first_session_index(calendar: list[date], start: date) -> int:
    for i, d in enumerate(calendar):
        if d >= start:
            return i
    raise ValueError(f'no session on/after {start}')


def last_session_index_at_or_before(calendar: list[date], day: date) -> int:
    idx = next_session_index(calendar, day)
    if idx is None:
        return len(calendar) - 1
    if calendar[idx] == day:
        return idx
    return idx - 1


# --------------------------------------------------------------------------- #
# per-signal-day pools and rankings
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class PoolRow:
    code: str
    r20: float
    r60: float
    r120: float
    gate_ok: bool
    scoreable: bool


def group_pools(feat: pl.DataFrame) -> dict[date, list[PoolRow]]:
    elig = feat.filter(pl.col('eligible')).select(
        'trade_date', 'ts_code', 'r20', 'r60', 'r120', 'gate_ok')
    pools: dict[date, list[PoolRow]] = {}
    for row in elig.iter_rows(named=True):
        pools.setdefault(row['trade_date'], []).append(PoolRow(
            row['ts_code'], row['r20'], row['r60'], row['r120'],
            bool(row['gate_ok']),
            all(row[k] is not None for k in ('r20', 'r60', 'r120'))))
    for rows in pools.values():
        rows.sort(key=lambda r: r.code)
    return pools


_RATTR = {20: 'r20', 60: 'r60', 120: 'r120'}


def rank_pool(rows: list[PoolRow], window: tuple[int, ...]) -> list[PoolRow]:
    """Mean cross-sectional percentile of R_k over scoreable rows; ordered by
    score desc, ties by ts_code asc (deterministic ordinal ranks over
    (value, code) ascending)."""
    scoreable = [r for r in rows if r.scoreable]
    n = len(scoreable)
    if n < 2:
        return sorted(scoreable, key=lambda r: r.code)
    scores = {r.code: 0.0 for r in scoreable}
    for k in window:
        ordered = sorted(scoreable, key=lambda r: (getattr(r, _RATTR[k]), r.code))
        for i, r in enumerate(ordered):
            scores[r.code] += i / (n - 1)
    for code in scores:
        scores[code] /= len(window)
    return sorted(scoreable, key=lambda r: (-scores[r.code], r.code))


def topn(rows: list[PoolRow], window: tuple[int, ...], gate: bool,
         n: int = N_SLOTS) -> list[PoolRow]:
    ranked = rank_pool(rows, window)
    if gate:
        ranked = [r for r in ranked if r.gate_ok]
    return ranked[:n]


# --------------------------------------------------------------------------- #
# per-code price access
# --------------------------------------------------------------------------- #
class CodeData:
    def __init__(self, code: str, df: pl.DataFrame, cal_index: dict[date, int],
                 freeze_end: date = FREEZE_END):
        self.code = code
        self.pos = [cal_index[d] for d in df['trade_date'].to_list()]
        self.open = df['open'].to_list()
        self.close = df['close'].to_list()
        self.pre_close = df['pre_close'].to_list()
        self.adj_open = df['adj_open'].to_list()
        self.adj_close = df['adj_close'].to_list()
        self.last_row = df['last_row'].to_list()
        # U4: a quote stream that stops BEFORE the freeze boundary is a real
        # termination (delist/liquidation/unknown-stop); a stream reaching the
        # boundary belongs to a still-listed ETF and is carried, not exited
        self.stopped_mid = bool(self.pos) and df['trade_date'][-1] < freeze_end
        self._at = dict(zip(self.pos, range(len(self.pos))))
        self._mark: dict[int, int] = {}

    def idx_at(self, session: int) -> int | None:
        return self._at.get(session)

    def mark_idx(self, session: int) -> int | None:
        hit = self._mark.get(session)
        if hit is not None:
            return hit if hit >= 0 else None
        lo, hi = 0, len(self.pos)
        while lo < hi:
            mid = (lo + hi) // 2
            if self.pos[mid] <= session:
                lo = mid + 1
            else:
                hi = mid
        idx = lo - 1
        self._mark[session] = idx
        return idx if idx >= 0 else None

    def mark_adj_close(self, session: int) -> float | None:
        mi = self.mark_idx(session)
        return None if mi is None else self.adj_close[mi]

    def limit_blocked(self, idx: int, side: str) -> bool | None:
        """True when the open trips the 9.5% proxy for this side; None when
        open/pre_close are unavailable."""
        o, pc = self.open[idx], self.pre_close[idx]
        if o is None or pc is None or pc <= 0:
            return None
        ratio = o / pc - 1.0
        if side == 'buy':
            return ratio >= LIMIT_PCT
        return ratio <= -LIMIT_PCT


class CodeDataBank:
    def __init__(self, feat: pl.DataFrame, calendar: list[date]):
        self.cal_index = {d: i for i, d in enumerate(calendar)}
        self._feat = feat
        self._bank: dict[str, CodeData] = {}

    def get(self, code: str) -> CodeData:
        cd = self._bank.get(code)
        if cd is None:
            df = self._feat.filter(pl.col('ts_code') == code).sort('trade_date')
            cd = CodeData(code, df, self.cal_index)
            self._bank[code] = cd
        return cd


# --------------------------------------------------------------------------- #
# simulation engine (3-slot rotation; also used by B3 with a shuffled selector)
# --------------------------------------------------------------------------- #
@dataclass
class ExecStats:
    planned_buy_legs: int = 0
    buys_filled: int = 0
    buys_no_candidate: int = 0
    buys_cancelled_slot_busy: int = 0
    planned_sell_legs: int = 0
    sells_filled: int = 0
    sells_postponed_then_filled: int = 0
    sells_forced_delist: int = 0
    sells_pending_at_end: int = 0
    entry_limit_blocked: int = 0
    entry_suspended: int = 0
    exit_limit_blocked: int = 0
    exit_suspended: int = 0
    # R7: a buy whose budget, capped by the available cash pool, fell to the
    # commission minimum or below is skipped as a rule-compliant cash slot
    # (registered sizing rule "cash never negative").  Always 0 in P2-R6 runs.
    buys_cash_capped: int = 0
    # R8 daily risk overlay counters (descriptive; gate-8 reads leg_log which
    # carries monthly AND risk legs)
    risk_legs_planned: int = 0
    risk_buys_filled: int = 0
    risk_sells_filled: int = 0
    risk_buys_cash_capped: int = 0
    risk_sells_feemin_skipped: int = 0
    risk_suspended: int = 0
    risk_limit_blocked: int = 0

    def execution_rate(self) -> tuple[int, int, float | None]:
        planned = self.planned_buy_legs + self.planned_sell_legs
        done = (self.buys_filled + self.buys_no_candidate + self.buys_cash_capped
                + self.sells_filled + self.sells_postponed_then_filled
                + self.sells_forced_delist)
        rate = (done / planned) if planned else None
        return done, planned, rate

    def as_dict(self) -> dict:
        done, planned, rate = self.execution_rate()
        return {**self.__dict__, 'legs_executed': done, 'legs_planned': planned,
                'execution_rate': rate}


@dataclass
class SimResult:
    config_id: str
    sessions: list[date] = field(default_factory=list)
    equity: list[float] = field(default_factory=list)
    trades: list[dict] = field(default_factory=list)
    positions: list[dict] = field(default_factory=list)
    exec_stats: ExecStats = field(default_factory=ExecStats)
    max_negative_cash: float = 0.0
    final_open: list[dict] = field(default_factory=list)
    extra: dict = field(default_factory=dict)
    # R7: one entry per planned leg {'plan_date', 'side', 'outcome', 'code'};
    # outcomes in {'filled', 'no_candidate', 'cash_capped', 'sell_at_open',
    # 'postponed_then_filled', 'cancelled_slot_busy', 'pending_at_end'}.
    # Enables the registered dev-window execution rate (revision-2 item 5).
    leg_log: list[dict] = field(default_factory=list)


@dataclass
class _Slot:
    code: str | None = None
    units: float = 0.0
    cash: float = 0.0
    exit_due: bool = False
    entry: dict | None = None
    # R7 exposure engine: the leg_log entry of a planned sell that was
    # postponed, so its outcome can be resolved when it eventually fills
    sell_leg: dict | None = None
    # R8 daily risk overlay: a postponed re-sizing target {'frac', 'equity_t',
    # 'leg'} that retries at the next tradable open; the LATEST target wins
    risk_target: dict | None = None


def _buy_fee(budget: float, fees: FeeBand) -> float:
    return max(budget * fees.commission_pct, fees.commission_min)


def build_plan(slots: list[_Slot], ranked: list[str], stats: ExecStats,
               n: int = N_SLOTS) -> dict:
    """Incumbents in TopN stay; leavers are sold; new entrants walk the full
    ranked list in order so a failed entry backfills by rank (prereg 4.2)."""
    top = ranked[:n]
    held = [s.code for s in slots if s.code is not None]
    keep = [c for c in held if c in top]
    sell_slots = [s for s in slots if s.code is not None and s.code not in top]
    n_buy = n - len(keep)
    buys = [c for c in ranked if c not in keep]
    stats.planned_sell_legs += len(sell_slots)
    stats.planned_buy_legs += n_buy
    return {'sell_slots': sell_slots, 'buys': buys, 'n_buy': n_buy}


def simulate(config_id: str, bank: CodeDataBank, calendar: list[date],
             start: date, signal_days: list[date],
             selector: Callable[[date], list[str]],
             *, budget: float, fees: FeeBand) -> SimResult:
    """One continuous 3-slot rotation path from ``start`` to the calendar end.

    ``selector(t)`` returns the ordered candidate codes for signal day t (the
    full ranked list for the strategy so failed entries backfill by rank, or a
    shuffled pool for B3).  Before the first signal day the portfolio is cash
    (3 x budget).  Exits planned at close t execute at the t+1 open; failures
    postpone to the next tradable open.  Positions still held at the window
    end are mark-to-market carried (registered boundary rule).
    """
    result = SimResult(config_id=config_id)
    stats = result.exec_stats
    slots = [_Slot(cash=budget) for _ in range(N_SLOTS)]
    pending: dict | None = None
    signal_set = set(signal_days)
    start_idx = first_session_index(calendar, start)
    last_idx = len(calendar) - 1

    for si in range(start_idx, last_idx + 1):
        day = calendar[si]

        # 1. retry exits postponed from earlier sessions
        for slot in slots:
            if slot.exit_due and slot.code is not None:
                cd = bank.get(slot.code)
                idx = cd.idx_at(si)
                if idx is None:
                    continue
                blocked = cd.limit_blocked(idx, 'sell')
                if blocked is None or blocked:
                    if blocked:
                        stats.exit_limit_blocked += 1
                    continue
                _close(slot, cd, idx, si, day, 'sell_postponed', fees, stats, result)

        # 2. forced delist exits (quote stream stops mid-window while held;
        # never on the entry day: T+1; boundary-reaching streams are carried)
        for slot in slots:
            if slot.code is not None and not slot.exit_due:
                cd = bank.get(slot.code)
                if not cd.stopped_mid:
                    continue
                idx = cd.idx_at(si)
                if (idx is not None and cd.last_row[idx]
                        and slot.entry['entry_session'] < si):
                    _close(slot, cd, idx, si, day, 'forced_delist_close', fees,
                           stats, result, at_close=True)

        # 3. execute the plan built at the previous close (t+1 open)
        if pending is not None:
            _execute_plan(pending, slots, bank, si, day, budget, fees, stats,
                          result, calendar)
            pending = None

        # 4. mark equity
        equity = 0.0
        for slot in slots:
            v = slot.cash
            if slot.code is not None:
                cd = bank.get(slot.code)
                mi = cd.mark_idx(si)
                if mi is not None:
                    v += slot.units * cd.adj_close[mi]
            equity += v
            result.max_negative_cash = min(result.max_negative_cash, slot.cash)
        result.sessions.append(day)
        result.equity.append(equity)

        # 5. plan at this close for the next session
        if day in signal_set and si < last_idx:
            pending = build_plan(slots, selector(day), stats)

    for slot in slots:
        if slot.code is not None:
            stats.sells_pending_at_end += 1
            result.final_open.append({**slot.entry, 'open_at_end': True,
                                      'exit_session': last_idx})
    return result


def _execute_plan(plan: dict, slots: list[_Slot], bank: CodeDataBank, si: int,
                  day: date, budget: float, fees: FeeBand, stats: ExecStats,
                  result: SimResult, calendar: list[date]) -> None:
    # exits first
    freed: list[_Slot] = []
    for slot in plan['sell_slots']:
        cd = bank.get(slot.code)
        idx = cd.idx_at(si)
        if idx is None:
            stats.exit_suspended += 1
            slot.exit_due = True  # postpone; retried on later sessions
            continue
        blocked = cd.limit_blocked(idx, 'sell')
        if blocked is None or blocked:
            if blocked:
                stats.exit_limit_blocked += 1
            slot.exit_due = True
            continue
        _close(slot, cd, idx, si, day, 'sell_at_open', fees, stats, result)
        freed.append(slot)

    # buys: already-cash slots first, then slots freed by successful exits
    # (deduped by identity: a freed slot is also code-None now);
    # replacement buys for slots whose exit was postponed are cancelled
    freed_ids = {id(s) for s in freed}
    targets = ([s for s in slots if s.code is None and id(s) not in freed_ids]
               + freed)
    cancelled = plan['n_buy'] - len(targets)
    if cancelled > 0:
        stats.buys_cancelled_slot_busy += cancelled
    for slot in targets[:plan['n_buy']]:
        filled = False
        while plan['buys']:
            code = plan['buys'].pop(0)
            if any(s.code == code for s in slots):
                continue
            cd = bank.get(code)
            idx = cd.idx_at(si)
            if idx is None:
                stats.entry_suspended += 1
                continue
            blocked = cd.limit_blocked(idx, 'buy')
            if blocked is None or blocked:
                if blocked:
                    stats.entry_limit_blocked += 1
                continue
            _open(slot, cd, idx, si, day, budget, fees, stats, result)
            filled = True
            break
        if not filled:
            stats.buys_no_candidate += 1


def _open(slot: _Slot, cd: CodeData, idx: int, si: int, day: date,
          budget: float, fees: FeeBand, stats: ExecStats, result: SimResult) -> None:
    fee = _buy_fee(budget, fees)
    units = (budget - fee) / cd.adj_open[idx]
    slot.cash -= budget
    slot.units = units
    slot.code = cd.code
    slot.exit_due = False
    slot.entry = {'code': cd.code, 'entry_session': si, 'entry_date': day,
                  'budget': budget, 'units': units,
                  'entry_adj': cd.adj_open[idx], 'entry_raw': cd.open[idx],
                  'buy_fee': fee}
    stats.buys_filled += 1
    result.trades.append({
        'session': day, 'code': cd.code, 'side': 'buy', 'kind': 'open',
        'raw_price': cd.open[idx], 'adj_price': cd.adj_open[idx],
        'notional': budget, 'fee': fee, 'units': units, 'status': 'filled'})


def _close(slot: _Slot, cd: CodeData, idx: int, si: int, day: date, kind: str,
           fees: FeeBand, stats: ExecStats, result: SimResult,
           at_close: bool = False) -> None:
    exit_adj = cd.adj_close[idx] if at_close else cd.adj_open[idx]
    exit_raw = cd.close[idx] if at_close else cd.open[idx]
    gross = slot.units * exit_adj
    fee = max(gross * fees.commission_pct, fees.commission_min)
    proceeds = gross - fee
    slot.cash += proceeds
    if kind == 'sell_postponed':
        stats.sells_postponed_then_filled += 1
    elif kind == 'forced_delist_close':
        stats.sells_forced_delist += 1
    else:
        stats.sells_filled += 1
    entry = slot.entry or {}
    result.trades.append({
        'session': day, 'code': cd.code, 'side': 'sell', 'kind': kind,
        'raw_price': exit_raw, 'adj_price': exit_adj, 'notional': gross,
        'fee': fee, 'units': slot.units, 'status': 'filled',
        'entry_date': entry.get('entry_date'),
        'pnl': proceeds - entry['budget'] if entry else None})
    if entry:
        result.positions.append({**entry, 'exit_session': si, 'exit_date': day,
                                 'exit_adj': exit_adj, 'exit_raw': exit_raw,
                                 'sell_fee': fee, 'proceeds': proceeds,
                                 'pnl': proceeds - entry['budget'],
                                 'exit_kind': kind})
    slot.code, slot.units, slot.exit_due, slot.entry = None, 0.0, False, None


# --------------------------------------------------------------------------- #
# benchmark B1: same-pool equal weight, full rebalance every signal period
# --------------------------------------------------------------------------- #
def simulate_b1(pools: dict[date, list[PoolRow]], bank: CodeDataBank,
                calendar: list[date], start: date, signal_days: list[date],
                *, total: float, fees: FeeBand) -> SimResult:
    """Equal-weight ALL eligible ETFs at every signal day (1/N of equity),
    full rebalance each period: entries at t+1 open (limit-up/missing-open
    legs sit out the period in cash), exits at the next t+1 open with the
    registered fallback of the last available adjusted close on/before the
    failed exit session.  Per-leg notional 200,000/N (fee-min applies)."""
    result = SimResult(config_id='B1')
    stats = result.exec_stats
    start_idx = first_session_index(calendar, start)
    signals = sorted(d for d in signal_days if d >= start)
    if len(signals) < 2:
        raise ValueError('B1 needs at least two signal days')
    exec_of = {t: next_session_index(calendar, t) for t in signals}
    entry_at: dict[int, date] = {}
    exit_at: set[int] = set()
    for i, t in enumerate(signals):
        if exec_of[t] is not None:
            entry_at[exec_of[t]] = t
        if i + 1 < len(signals) and exec_of[signals[i + 1]] is not None:
            exit_at.add(exec_of[signals[i + 1]])

    legs: list[dict] = []
    idle_value = total  # cash until the first entry
    turnover_acc: dict[int, dict] = {}

    def mark_value(si: int) -> float:
        value = idle_value
        for leg in legs:
            m = bank.get(leg['code']).mark_adj_close(si)
            if m is not None:
                value += leg['units'] * m
        return value

    for si in range(start_idx, len(calendar)):
        day = calendar[si]

        if si in exit_at and legs:
            gross_total = fee_total = 0.0
            for leg in legs:
                cd = bank.get(leg['code'])
                idx = cd.idx_at(si)
                exit_adj = None
                if idx is not None and cd.limit_blocked(idx, 'sell') is False:
                    exit_adj = cd.adj_open[idx]
                if exit_adj is None:
                    exit_adj = cd.mark_adj_close(si)
                g = leg['units'] * exit_adj
                f = max(g * fees.commission_pct, fees.commission_min)
                gross_total += g
                fee_total += f
                book = turnover_acc.setdefault(
                    day.year, {'buy_notional': 0.0, 'sell_notional': 0.0})
                book['sell_notional'] += g
            stats.sells_filled += len(legs)
            legs = []
            idle_value = 0.0
            realized = gross_total - fee_total
        else:
            realized = None

        if si in entry_at:
            pool = pools.get(entry_at[si], [])
            n = len(pool)
            base = realized if realized is not None else mark_value(si)
            if n == 0:
                idle_value = base
            else:
                idle_value = 0.0
                legs = []
                for row in pool:
                    frac = 1.0 / n
                    cd = bank.get(row.code)
                    idx = cd.idx_at(si)
                    if idx is not None and cd.limit_blocked(idx, 'buy') is False:
                        budget = base * frac
                        fee = _buy_fee(budget, fees)
                        units = (budget - fee) / cd.adj_open[idx]
                        legs.append({'code': row.code, 'units': units})
                        stats.buys_filled += 1
                        book = turnover_acc.setdefault(
                            day.year, {'buy_notional': 0.0, 'sell_notional': 0.0})
                        book['buy_notional'] += budget
                    else:
                        if idx is None:
                            stats.entry_suspended += 1
                        else:
                            stats.entry_limit_blocked += 1
                        idle_value += base * frac
                stats.planned_buy_legs += n

        result.sessions.append(day)
        result.equity.append(mark_value(si))
    result.extra['turnover_acc'] = turnover_acc
    return result


# --------------------------------------------------------------------------- #
# benchmark B2: index ETF buy-and-hold per segment
# --------------------------------------------------------------------------- #
def simulate_b2(code: str, bank: CodeDataBank, calendar: list[date],
                seg_start: date, seg_end: date, *, total: float,
                fees: FeeBand) -> dict:
    sessions_idx = [i for i, d in enumerate(calendar) if seg_start <= d <= seg_end]
    if not sessions_idx:
        raise ValueError(f'B2 {code}: no sessions in {seg_start}..{seg_end}')
    e_i, x_i = sessions_idx[0], sessions_idx[-1]
    cd = bank.get(code)
    e_idx, x_idx = cd.idx_at(e_i), cd.idx_at(x_i)
    if e_idx is None or x_idx is None:
        raise ValueError(f'B2 {code}: missing quotes at segment bounds')
    marks = []
    for i in sessions_idx:
        mi = cd.mark_idx(i)
        marks.append(cd.adj_close[mi] if mi is not None else None)
    if marks[0] is None or marks[-1] is None:
        raise ValueError(f'B2 {code}: missing adjusted marks at bounds')
    out = {'code': code, 'entry_date': calendar[e_i], 'exit_date': calendar[x_i],
           'entry_raw': cd.open[e_idx], 'exit_raw': cd.close[x_idx],
           'entry_adj_open': cd.adj_open[e_idx]}
    # both variants enter at the segment-start OPEN and are marked at the
    # segment-end CLOSE (registered B2 definition); they differ by fees only
    out['gross_curve'] = [total * (m / cd.adj_open[e_idx]) for m in marks]
    out['gross_total_return'] = marks[-1] / cd.adj_open[e_idx] - 1.0
    fee_b = _buy_fee(total, fees)
    units = (total - fee_b) / cd.adj_open[e_idx]
    gross_x = units * marks[-1]
    fee_s = max(gross_x * fees.commission_pct, fees.commission_min)
    out['net_curve'] = [units * m for m in marks]
    out['net_total_return'] = (gross_x - fee_s) / total - 1.0
    out['buy_fee'] = fee_b
    out['sell_fee'] = fee_s
    return out


# --------------------------------------------------------------------------- #
# P2-R7 dynamic exposure (exp-20260917-p2r7-etf-exposure)
#
# Registered semantics (frozen config configs/experiments/p2r7-etf-exposure.json,
# written BEFORE any R7 signal ran): three exposure mechanisms (FIX 75%,
# VOLT clip(15%/vol60 pool equal-weight, 40%, 100%), TREND 000300.SH
# close>SMA200 -> 90% else 40%); per-leg budget = min(exposure_t/N, 25%) x
# equity marked at the signal-day close t; a single portfolio-level cash pool
# that never goes negative (buy budgets capped by available cash; a capped
# budget <= commission min skips the leg as a rule-compliant cash slot);
# everything else inherits the P2-R6 engine unchanged.
# --------------------------------------------------------------------------- #
def leg_frac(exposure: float, n: int) -> float:
    """Registered R7 sizing: fraction of equity per leg."""
    return min(exposure / n, MAX_LEG_FRAC)


def fix_exposures(signal_days: list[date], level: float = 0.75) -> dict[date, float]:
    return {d: level for d in signal_days}


def pool_daily_returns(feat: pl.DataFrame) -> dict[date, float]:
    """Registered VOLT input: equal-weight pool daily returns.  Per session the
    cross-sectional mean, over the eligible pool quoted that day, of own-row
    adjusted daily returns (suspended days have no row; first own row has no
    previous close and is skipped by the null-aware mean)."""
    r = (feat.filter(pl.col('eligible')).sort('ts_code', 'trade_date')
         .with_columns((pl.col('adj_close')
                        / pl.col('adj_close').shift(1).over('ts_code') - 1.0)
                       .alias('_r'))
         .group_by('trade_date')
         .agg(pl.col('_r').mean().alias('pool_ret'))
         .sort('trade_date'))
    return {d: v for d, v in zip(r['trade_date'], r['pool_ret'])
            if v is not None}


def volt_exposures(calendar: list[date], signal_days: list[date],
                   pool_ret: dict[date, float], *, target_vol: float = 0.15,
                   clip_min: float = 0.40, clip_max: float = 1.00,
                   window: int = 60, sessions_per_year: int = 244
                   ) -> dict[date, float]:
    """clip(target_vol / (vol60 * sqrt(244)), clip_min, clip_max) at each
    signal day.  vol60 = sample std (ddof=1) of the pool return over the last
    ``window`` calendar sessions ending at t (null sessions skipped).
    Fallbacks (registered): no 60-session window -> expanding std of all pool
    returns up to t; still unavailable -> clip_min.  An exactly-zero vol takes
    the formula's limit clip_max (never observed; defensive)."""
    idx_of = {d: i for i, d in enumerate(calendar)}
    out: dict[date, float] = {}
    for t in signal_days:
        i = idx_of[t]
        vals = [pool_ret[d] for d in calendar[max(0, i - window + 1):i + 1]
                if d in pool_ret]
        vol = statistics.stdev(vals) if len(vals) >= 2 else None
        if vol is None:
            expanding = [v for d, v in pool_ret.items() if d <= t]
            vol = statistics.stdev(expanding) if len(expanding) >= 2 else None
        if vol is None:
            out[t] = clip_min
            continue
        if vol <= 0.0:
            out[t] = clip_max
            continue
        ann = vol * sessions_per_year ** 0.5
        out[t] = min(clip_max, max(clip_min, target_vol / ann))
    return out


def load_index_close(index_csv: Path) -> pl.DataFrame:
    return (pl.read_csv(index_csv, infer_schema_length=0)
            .select(pl.col('trade_date').str.to_date('%Y%m%d'),
                    pl.col('close').cast(pl.Float64, strict=False))
            .sort('trade_date'))


def trend_exposures(index_close: pl.DataFrame, signal_days: list[date], *,
                    sma_sessions: int = 200, level_on: float = 0.90,
                    level_off: float = 0.40) -> dict[date, float]:
    """000300.SH close > SMA200(close, ``sma_sessions`` index sessions ending
    at t inclusive) -> level_on else level_off, at each signal day (asof:
    index row with trade_date <= t; unavailable SMA -> level_off)."""
    frame = index_close.with_columns(
        pl.col('close').rolling_mean(sma_sessions, min_samples=sma_sessions)
        .alias('_sma'))
    dates = frame['trade_date'].to_list()
    closes = frame['close'].to_list()
    smas = frame['_sma'].to_list()
    out: dict[date, float] = {}
    for t in signal_days:
        pos = bisect_right(dates, t) - 1
        if pos < 0 or smas[pos] is None:
            out[t] = level_off
        else:
            out[t] = level_on if closes[pos] > smas[pos] else level_off
    return out


def _open_ex(slot: _Slot, cd: CodeData, idx: int, si: int, day: date,
             budget: float, fees: FeeBand, stats: ExecStats,
             result: SimResult) -> None:
    """R7 entry: records the position; the caller moves ``budget`` out of the
    shared cash pool (identical trade/entry records to the P2-R6 engine)."""
    fee = _buy_fee(budget, fees)
    units = (budget - fee) / cd.adj_open[idx]
    slot.units = units
    slot.code = cd.code
    slot.exit_due = False
    slot.entry = {'code': cd.code, 'entry_session': si, 'entry_date': day,
                  'budget': budget, 'units': units,
                  'entry_adj': cd.adj_open[idx], 'entry_raw': cd.open[idx],
                  'buy_fee': fee}
    stats.buys_filled += 1
    result.trades.append({
        'session': day, 'code': cd.code, 'side': 'buy', 'kind': 'open',
        'raw_price': cd.open[idx], 'adj_price': cd.adj_open[idx],
        'notional': budget, 'fee': fee, 'units': units, 'status': 'filled'})


def _close_ex(slot: _Slot, cd: CodeData, idx: int, si: int, day: date,
              kind: str, fees: FeeBand, stats: ExecStats, result: SimResult,
              at_close: bool = False) -> float:
    """R7 exit: returns the proceeds; the caller adds them to the cash pool."""
    exit_adj = cd.adj_close[idx] if at_close else cd.adj_open[idx]
    exit_raw = cd.close[idx] if at_close else cd.open[idx]
    gross = slot.units * exit_adj
    fee = max(gross * fees.commission_pct, fees.commission_min)
    proceeds = gross - fee
    if kind == 'sell_postponed':
        stats.sells_postponed_then_filled += 1
    elif kind == 'forced_delist_close':
        stats.sells_forced_delist += 1
    else:
        stats.sells_filled += 1
    entry = slot.entry or {}
    result.trades.append({
        'session': day, 'code': cd.code, 'side': 'sell', 'kind': kind,
        'raw_price': exit_raw, 'adj_price': exit_adj, 'notional': gross,
        'fee': fee, 'units': slot.units, 'status': 'filled',
        'entry_date': entry.get('entry_date'),
        'pnl': proceeds - entry['budget'] if entry else None})
    if entry:
        result.positions.append({**entry, 'exit_session': si, 'exit_date': day,
                                 'exit_adj': exit_adj, 'exit_raw': exit_raw,
                                 'sell_fee': fee, 'proceeds': proceeds,
                                 'pnl': proceeds - entry['budget'],
                                 'exit_kind': kind})
    slot.code, slot.units, slot.exit_due, slot.entry = None, 0.0, False, None
    slot.sell_leg = None
    return proceeds


def _execute_plan_exposure(plan: dict, slots: list[_Slot], bank: CodeDataBank,
                           si: int, day: date, cash: float, fees: FeeBand,
                           stats: ExecStats, result: SimResult) -> float:
    """R7 plan execution at t+1 open: exits first (proceeds into the cash
    pool), then buys with leg budgets min(exposure/N, 25%) x equity_t capped by
    available cash.  Returns the updated cash."""
    p = plan['plan']
    n_slots = len(slots)
    leg_target = leg_frac(plan['exposure'], n_slots) * plan['equity_t']

    freed: list[_Slot] = []
    for slot, leg in zip(p['sell_slots'], plan['sell_legs']):
        cd = bank.get(slot.code)
        idx = cd.idx_at(si)
        if idx is None:
            stats.exit_suspended += 1
            slot.exit_due = True
            continue
        blocked = cd.limit_blocked(idx, 'sell')
        if blocked is None or blocked:
            if blocked:
                stats.exit_limit_blocked += 1
            slot.exit_due = True
            continue
        cash += _close_ex(slot, cd, idx, si, day, 'sell_at_open', fees, stats,
                          result)
        freed.append(slot)
        leg['outcome'] = 'sell_at_open'

    freed_ids = {id(s) for s in freed}
    targets = ([s for s in slots if s.code is None and id(s) not in freed_ids]
               + freed)
    cancelled = p['n_buy'] - len(targets)
    if cancelled > 0:
        stats.buys_cancelled_slot_busy += cancelled
    buy_legs = plan['buy_legs']
    for leg in buy_legs[:cancelled]:  # arbitrary which planned leg is the
        leg['outcome'] = 'cancelled_slot_busy'  # cancelled one; rate-irrelevant
    walked_legs = buy_legs[cancelled:]
    for i, slot in enumerate(targets[:p['n_buy']]):
        leg = walked_legs[i]
        filled = False
        while p['buys']:
            code = p['buys'].pop(0)
            if any(s.code == code for s in slots):
                continue
            cd = bank.get(code)
            idx = cd.idx_at(si)
            if idx is None:
                stats.entry_suspended += 1
                continue
            blocked = cd.limit_blocked(idx, 'buy')
            if blocked is None or blocked:
                if blocked:
                    stats.entry_limit_blocked += 1
                continue
            budget = min(leg_target, cash)
            if budget <= fees.commission_min:
                # registered hard rule: cash never negative; too small to pay
                # the minimum commission -> rule-compliant cash slot
                stats.buys_cash_capped += 1
                leg['outcome'] = 'cash_capped'
            else:
                _open_ex(slot, cd, idx, si, day, budget, fees, stats, result)
                cash -= budget
                leg['outcome'] = 'filled'
            filled = True
            break
        if not filled:
            stats.buys_no_candidate += 1
            leg['outcome'] = 'no_candidate'
    return cash


def simulate_exposure(config_id: str, bank: CodeDataBank, calendar: list[date],
                      start: date, signal_days: list[date],
                      selector: Callable[[date], list[str]],
                      exposure_of: dict[date, float], *, n_slots: int,
                      fees: FeeBand, total: float = 200_000.0) -> SimResult:
    """One continuous N-slot rotation path under a dynamic exposure mechanism.

    Differences from the P2-R6 ``simulate``: ``n_slots`` in {3, 5}; a single
    portfolio-level cash pool (starts at ``total``); at each signal day t the
    plan stores exposure_t and equity marked at the t close, and every new leg
    buys min(exposure_t / N, 25%) x equity_t, additionally capped by the
    available cash so the pool never goes negative.  Next-open execution, 9.5%
    limit proxy, suspension postponement, slot-busy cancellation, forced delist
    exits and boundary mark-to-market carry are inherited unchanged."""
    result = SimResult(config_id=config_id)
    stats = result.exec_stats
    slots = [_Slot() for _ in range(n_slots)]
    cash = total
    pending: dict | None = None
    signal_set = set(signal_days)
    start_idx = first_session_index(calendar, start)
    last_idx = len(calendar) - 1

    for si in range(start_idx, last_idx + 1):
        day = calendar[si]

        # 1. retry exits postponed from earlier sessions
        for slot in slots:
            if slot.exit_due and slot.code is not None:
                cd = bank.get(slot.code)
                idx = cd.idx_at(si)
                if idx is None:
                    continue
                blocked = cd.limit_blocked(idx, 'sell')
                if blocked is None or blocked:
                    if blocked:
                        stats.exit_limit_blocked += 1
                    continue
                leg_ref = slot.sell_leg  # captured BEFORE _close_ex clears it
                cash += _close_ex(slot, cd, idx, si, day, 'sell_postponed',
                                  fees, stats, result)
                if leg_ref is not None:
                    leg_ref['outcome'] = 'postponed_then_filled'

        # 2. forced delist exits (never on the entry session: T+1)
        for slot in slots:
            if slot.code is not None and not slot.exit_due:
                cd = bank.get(slot.code)
                if not cd.stopped_mid:
                    continue
                idx = cd.idx_at(si)
                if (idx is not None and cd.last_row[idx]
                        and slot.entry['entry_session'] < si):
                    cash += _close_ex(slot, cd, idx, si, day,
                                      'forced_delist_close', fees, stats,
                                      result, at_close=True)

        # 3. execute the plan built at the previous close (t+1 open)
        if pending is not None:
            cash = _execute_plan_exposure(pending, slots, bank, si, day, cash,
                                          fees, stats, result)
            pending = None

        # 4. mark equity
        equity = cash
        for slot in slots:
            if slot.code is not None:
                cd = bank.get(slot.code)
                mi = cd.mark_idx(si)
                if mi is not None:
                    equity += slot.units * cd.adj_close[mi]
        if cash < -1e-6:  # registered invariant; engine caps budgets so this
            raise RuntimeError(  # must never fire
                f'{config_id}: negative cash pool on {day}: {cash:.6f}')
        result.max_negative_cash = min(result.max_negative_cash, cash)
        result.sessions.append(day)
        result.equity.append(equity)

        # 5. plan at this close for the next session
        if day in signal_set and si < last_idx:
            plan = build_plan(slots, selector(day), stats, n=n_slots)
            sell_legs = [{'plan_date': day, 'side': 'sell', 'outcome': None,
                          'code': s.code} for s in plan['sell_slots']]
            buy_legs = [{'plan_date': day, 'side': 'buy', 'outcome': None,
                         'code': None} for _ in range(plan['n_buy'])]
            exposure = exposure_of.get(day)
            if exposure is None:
                raise RuntimeError(
                    f'{config_id}: missing exposure for signal day {day}')
            pending = {'plan': plan, 'signal_day': day, 'equity_t': equity,
                       'exposure': exposure, 'sell_legs': sell_legs,
                       'buy_legs': buy_legs}
            result.leg_log.extend(sell_legs)
            result.leg_log.extend(buy_legs)
            for slot, leg in zip(plan['sell_slots'], sell_legs):
                slot.sell_leg = leg

    for slot in slots:
        if slot.code is not None:
            stats.sells_pending_at_end += 1
            result.final_open.append({**slot.entry, 'open_at_end': True,
                                      'exit_session': last_idx})
    for leg in result.leg_log:  # unresolved planned legs = pending at end
        if leg['outcome'] is None:
            leg['outcome'] = 'pending_at_end'
    return result


_EXECUTED_OUTCOMES = frozenset({'filled', 'no_candidate', 'cash_capped',
                                'sell_at_open', 'postponed_then_filled'})


def window_execution_rate(leg_log: list[dict], start: date,
                          end: date) -> dict:
    """Registered gate-8 quantity (revision-2 item 5): the leg-level execution
    rate over legs PLANNED on signal days inside [start, end].  Executed =
    filled / backfilled / rule-compliant cash slot (incl. cash-capped) /
    postponed-then-filled; not executed = slot-busy cancelled / still pending.
    Forced delist exits are unplanned and appear on neither side."""
    planned = [l for l in leg_log if start <= l['plan_date'] <= end]
    done = sum(1 for l in planned if l['outcome'] in _EXECUTED_OUTCOMES)
    return {'legs_executed': done, 'legs_planned': len(planned),
            'execution_rate': (done / len(planned)) if planned else None}


def simulate_b1_exposure(pools: dict[date, list[PoolRow]], bank: CodeDataBank,
                         calendar: list[date], start: date,
                         signal_days: list[date],
                         exposure_of: dict[date, float], *, fees: FeeBand,
                         total: float = 200_000.0,
                         config_id: str = 'B1',
                         risk_fn: Callable[[date, float], float] | None = None
                         ) -> SimResult:
    """B1(m): same-pool equal weight at every signal day with the mechanism's
    exposure path.  Per-leg fraction of base equity =
    min(exposure_t / N_pool, 25%); base equity follows the registered P2-R6 B1
    convention (realized open proceeds at the execution session when all exits
    filled at that open, else close-marked equity at that session) EXTENDED by
    the carried idle cash (P2-R6 B1 was always fully invested so its idle was
    always zero; with partial exposure the un-invested share must persist).
    Full rebalance each period; entries at t+1 open (limit-up/missing-open
    legs sit out in cash); exits at the next t+1 open with the last-available
    adjusted close fallback; per-leg commission max(0.01%, min).

    R8 daily risk overlay (``risk_fn`` not None): the mechanism's exposure is
    judged at EVERY session close; when E_t != E_{t-1} and legs are held, all
    legs are re-sized toward frac(E_t) x base (close-marked equity incl. idle)
    at the t+1 open; a rescale leg with no quote or a tripped 9.5% proxy
    retries at later opens until filled or superseded by a fresher target;
    rescale buys are capped by the idle pool (never negative) and counted in
    the turnover books; a capped budget at/below the commission minimum leaves
    the leg under-invested (rule-compliant cash slot).  Rescales are never
    scheduled on signal-day closes (the rebalance already consumes E_t) and
    die when the monthly exit empties the legs.  risk_fn=None reproduces the
    R7 engine bit-exactly (anchor requirement)."""
    result = SimResult(config_id=config_id)
    stats = result.exec_stats
    start_idx = first_session_index(calendar, start)
    signals = sorted(d for d in signal_days if d >= start)
    if len(signals) < 2:
        raise ValueError('B1 needs at least two signal days')
    exec_of = {t: next_session_index(calendar, t) for t in signals}
    entry_at: dict[int, date] = {}
    exit_at: set[int] = set()
    for i, t in enumerate(signals):
        if exec_of[t] is not None:
            entry_at[exec_of[t]] = t
        if i + 1 < len(signals) and exec_of[signals[i + 1]] is not None:
            exit_at.add(exec_of[signals[i + 1]])

    legs: list[dict] = []
    idle_value = total  # cash until the first entry
    turnover_acc: dict[int, dict] = {}
    prev_e: float | None = None
    rescale: dict | None = None  # {'frac', 'base', 'done'} scheduled at close t
    current_n: int | None = None
    e_at: dict[date, float] = {}  # E judged at each close (single truth)

    def mark_value(si: int) -> float:
        value = idle_value
        for leg in legs:
            m = bank.get(leg['code']).mark_adj_close(si)
            if m is not None:
                value += leg['units'] * m
        return value

    for si in range(start_idx, len(calendar)):
        day = calendar[si]

        if si in exit_at and legs:
            gross_total = fee_total = 0.0
            for leg in legs:
                cd = bank.get(leg['code'])
                idx = cd.idx_at(si)
                exit_adj = None
                if idx is not None and cd.limit_blocked(idx, 'sell') is False:
                    exit_adj = cd.adj_open[idx]
                if exit_adj is None:
                    exit_adj = cd.mark_adj_close(si)
                g = leg['units'] * exit_adj
                f = max(g * fees.commission_pct, fees.commission_min)
                gross_total += g
                fee_total += f
                book = turnover_acc.setdefault(
                    day.year, {'buy_notional': 0.0, 'sell_notional': 0.0})
                book['sell_notional'] += g
            stats.sells_filled += len(legs)
            legs = []
            # proceeds join the carried idle pool (with partial exposure the
            # un-invested share persists; in P2-R6 B1 it was always zero)
            idle_value += gross_total - fee_total
            rescale = None  # no holdings left to re-size

        # R8: execute the risk rescale scheduled at the previous close (opens
        # only; never overlaps entries -- rescales are not scheduled on
        # signal-day closes)
        if rescale is not None and legs:
            target = rescale['frac'] * rescale['base']
            for li, leg in enumerate(legs):
                if li in rescale['done']:
                    continue
                cd = bank.get(leg['code'])
                idx = cd.idx_at(si)
                if idx is None:
                    continue  # retry at a later open
                adj = cd.adj_open[idx]
                delta = target - leg['units'] * adj
                if abs(delta) <= 1e-9:
                    rescale['done'].add(li)
                    continue
                if delta > 0.0:
                    blocked = cd.limit_blocked(idx, 'buy')
                    if blocked is None or blocked:
                        continue
                    budget = min(delta, idle_value)
                    if budget <= fees.commission_min:
                        rescale['done'].add(li)  # rule-compliant cash slot
                        continue
                    fee = _buy_fee(budget, fees)
                    leg['units'] += (budget - fee) / adj
                    idle_value -= budget
                    book = turnover_acc.setdefault(
                        day.year, {'buy_notional': 0.0, 'sell_notional': 0.0})
                    book['buy_notional'] += budget
                else:
                    blocked = cd.limit_blocked(idx, 'sell')
                    if blocked is None or blocked:
                        continue
                    units_sold = min(leg['units'], -delta / adj)
                    gross = units_sold * adj
                    if gross <= fees.commission_min:
                        # de-minimis: the commission minimum would overdraw
                        # the idle pool (never negative); skip (deviation 9)
                        rescale['done'].add(li)
                        continue
                    fee = max(gross * fees.commission_pct, fees.commission_min)
                    idle_value += gross - fee
                    leg['units'] -= units_sold
                    book = turnover_acc.setdefault(
                        day.year, {'buy_notional': 0.0, 'sell_notional': 0.0})
                    book['sell_notional'] += gross
                rescale['done'].add(li)
            if len(rescale['done']) == len(legs):
                rescale = None

        if si in entry_at:
            t = entry_at[si]
            pool = pools.get(t, [])
            n = len(pool)
            if risk_fn is not None:
                # R8: the daily risk_fn is the single source of E (PDD has no
                # static exposure dict); its value at the signal-day close was
                # recorded when that session was marked
                exposure = e_at[t]
            else:
                exposure = exposure_of.get(t)
                if exposure is None:
                    raise RuntimeError(f'{config_id}: missing exposure at {t}')
            # after exits (legs emptied, proceeds already in the idle pool)
            # this is carried idle + realized proceeds; otherwise the usual
            # close-marked equity
            base = mark_value(si)
            if n == 0:
                idle_value = base
            else:
                legs = []
                invested = 0.0
                for row in pool:
                    frac = leg_frac(exposure, n)
                    cd = bank.get(row.code)
                    idx = cd.idx_at(si)
                    if idx is not None and cd.limit_blocked(idx, 'buy') is False:
                        budget = base * frac
                        fee = _buy_fee(budget, fees)
                        units = (budget - fee) / cd.adj_open[idx]
                        legs.append({'code': row.code, 'units': units})
                        invested += budget
                        stats.buys_filled += 1
                        book = turnover_acc.setdefault(
                            day.year, {'buy_notional': 0.0, 'sell_notional': 0.0})
                        book['buy_notional'] += budget
                    else:
                        if idx is None:
                            stats.entry_suspended += 1
                        else:
                            stats.entry_limit_blocked += 1
                # un-invested base stays in the idle cash pool (with frac<1
                # this is more than just the blocked legs' shares; with the
                # P2-R6 frac=1/N the two formulations coincide)
                idle_value = base - invested
                stats.planned_buy_legs += n
                current_n = n

        result.sessions.append(day)
        eq_si = mark_value(si)
        result.equity.append(eq_si)
        # R8: judge the mechanism at this close; schedule a rescale for the
        # next open on a state change (never on a signal-day close: the next
        # rebalance consumes E_t itself)
        if risk_fn is not None:
            e_t = risk_fn(day, eq_si)
            e_at[day] = e_t
            if (prev_e is not None and e_t != prev_e and legs and current_n
                    and si + 1 < len(calendar)):
                rescale = {'frac': leg_frac(e_t, current_n), 'base': eq_si,
                           'done': set()}
            prev_e = e_t
    result.extra['turnover_acc'] = turnover_acc
    result.extra['e_at'] = e_at  # R9: E judged at each close (B1(m) disclosure)
    return result


# --------------------------------------------------------------------------- #
# metrics
# --------------------------------------------------------------------------- #
def cagr(v0: float, v1: float, d0: date, d1: date) -> float:
    if v0 <= 0 or v1 <= 0:
        return -1.0
    years = (d1 - d0).days / 365.25
    if years <= 0:
        return 0.0
    return (v1 / v0) ** (1.0 / years) - 1.0


def max_drawdown(sessions: list[date], values: list[float]) -> dict:
    peak = values[0]
    peak_i = 0
    mdd = 0.0
    mdd_peak = mdd_trough = 0
    for i, v in enumerate(values):
        if v > peak:
            peak, peak_i = v, i
        dd = v / peak - 1.0 if peak > 0 else 0.0
        if dd < mdd:
            mdd, mdd_peak, mdd_trough = dd, peak_i, i
    return {'max_drawdown': mdd,
            'peak_date': sessions[mdd_peak].isoformat() if mdd < 0 else None,
            'trough_date': sessions[mdd_trough].isoformat() if mdd < 0 else None}


def slice_curve(sessions: list[date], values: list[float],
                seg_start: date, seg_end: date) -> tuple[list[date], list[float]]:
    idx = [i for i, d in enumerate(sessions) if seg_start <= d <= seg_end]
    return [sessions[i] for i in idx], [values[i] for i in idx]


def year_returns(sessions: list[date], values: list[float]) -> dict[int, float]:
    """Calendar-year simple returns chained from the curve (the first year
    starts at the first curve value)."""
    marks: dict[int, float] = {}
    for d, v in zip(sessions, values):
        marks[d.year] = v
    out: dict[int, float] = {}
    prev = values[0]
    for y in sorted(marks):
        out[y] = marks[y] / prev - 1.0
        prev = marks[y]
    return out


def turnover_by_year(result: SimResult) -> dict[int, dict]:
    per_year: dict[int, dict] = {}
    eq_by_year: dict[int, list[float]] = {}
    for d, v in zip(result.sessions, result.equity):
        eq_by_year.setdefault(d.year, []).append(v)
    for t in result.trades:
        y = t['session'].year
        book = per_year.setdefault(y, {'buy_notional': 0.0, 'sell_notional': 0.0})
        if t['side'] == 'buy':
            book['buy_notional'] += t['notional']
        else:
            book['sell_notional'] += t['notional']
    out = {}
    for y, book in per_year.items():
        eqs = eq_by_year.get(y, [])
        mean_eq = sum(eqs) / len(eqs) if eqs else None
        out[y] = {'buy_notional': book['buy_notional'],
                  'sell_notional': book['sell_notional'],
                  'mean_equity': mean_eq,
                  'one_side_turnover': (book['buy_notional'] / mean_eq
                                        if mean_eq else None)}
    return out


def concentration(positions: list[dict], final_open: list[dict],
                  bank: CodeDataBank, calendar: list[date],
                  seg_start: date, seg_end: date) -> dict:
    """Per-code net P&L inside the segment; positions crossing the boundary
    are marked at boundary closes (synthetic attribution marks, no fee).
    Sum of per-code P&L reconciles with the segment equity delta."""
    s0 = first_session_index(calendar, seg_start)
    s1 = last_session_index_at_or_before(calendar, seg_end)
    pnl_by_code: dict[str, float] = {}
    records = [(p, False) for p in positions] + [(fo, True) for fo in final_open]
    for pos, open_at_end in records:
        e = pos['entry_session']
        x = pos.get('exit_session')
        if e > s1 or (x is not None and x < s0):
            continue
        cd = bank.get(pos['code'])
        mark0 = cd.mark_adj_close(s0)
        mark1 = cd.mark_adj_close(s1)
        if open_at_end or x is None or x > s1:
            # still held at the segment end: mark at the boundary close
            pnl = pos['units'] * mark1 - (pos['units'] * mark0 if e < s0
                                          else pos['budget'])
        elif e < s0:
            pnl = pos['proceeds'] - pos['units'] * mark0
        else:
            pnl = pos['pnl']
        pnl_by_code[pos['code']] = pnl_by_code.get(pos['code'], 0.0) + pnl
    total = sum(pnl_by_code.values())
    ordered = sorted(pnl_by_code.items(), key=lambda kv: -kv[1])
    top1 = ordered[0][1] / total if ordered and total > 0 else None
    top3 = (sum(v for _, v in ordered[:3]) / total) if ordered and total > 0 else None
    # R7: top-5 share, disclosed for N=5 configs (the gate stays top-1/top-3)
    top5 = (sum(v for _, v in ordered[:5]) / total) if ordered and total > 0 else None
    # R9: top-4 share, disclosed for N=4 configs (the gate stays top-1/top-3)
    top4 = (sum(v for _, v in ordered[:4]) / total) if ordered and total > 0 else None
    return {'pnl_by_code': pnl_by_code, 'total_pnl': total,
            'top1_share': top1, 'top3_share': top3, 'top4_share': top4,
            'top5_share': top5,
            'n_codes_positive': sum(1 for _, v in ordered if v > 0)}


def monthly_top_decile(sessions: list[date], values: list[float]) -> dict:
    month_end: dict[tuple[int, int], float] = {}
    month_open: dict[tuple[int, int], float] = {}
    prev_mark: float | None = None
    for d, v in zip(sessions, values):
        key = (d.year, d.month)
        month_end[key] = v
        if key not in month_open:
            month_open[key] = prev_mark if prev_mark is not None else values[0]
        prev_mark = v
    months = sorted(month_open)
    pnl = {m: month_end[m] - month_open[m] for m in months}
    total = sum(pnl.values())
    if not months or total <= 0:
        return {'top_decile_share': None, 'n_months': len(months),
                'total_pnl': total}
    ordered = sorted(pnl.items(), key=lambda kv: -kv[1])
    k = max(1, -(-len(ordered) // 10))
    return {'top_decile_share': sum(v for _, v in ordered[:k]) / total,
            'n_months': len(months), 'top_months': [m for m, _ in ordered[:k]],
            'total_pnl': total}


# --------------------------------------------------------------------------- #
# gates (numbers fixed by prereg section 6; structure per frozen config)
# --------------------------------------------------------------------------- #
def evaluate_dev_gate(m: dict, b1_dev: dict, b3_dev_mean: float | None,
                      *, freq: str) -> dict:
    checks = {}
    net = m['dev']['net_cagr']
    checks['1_net_cagr_gt_0'] = net is not None and net > 0
    excess = (net - b1_dev['net_cagr']) if net is not None else None
    checks['2_excess_vs_B1_ge_2pp'] = excess is not None and excess >= 0.020
    pos_years = [y for y, e in m['dev']['excess_by_year'].items()
                 if e is not None and e > 0]
    checks['3_positive_years_ge_4_of_5'] = len(pos_years) >= 4
    checks['4_mdd_le_20_and_le_B1'] = (
        m['dev']['max_drawdown'] is not None
        and abs(m['dev']['max_drawdown']) <= 0.20
        and b1_dev['max_drawdown'] is not None
        and abs(m['dev']['max_drawdown']) <= abs(b1_dev['max_drawdown']))
    cap = 6.0 if freq == 'monthly' else 12.0
    to = m['dev']['max_one_side_turnover']
    checks['5_turnover_le_cap'] = to is not None and to <= cap
    checks['5_turnover_cap'] = cap
    c = m['dev']['concentration']
    checks['6_top1_le_40_top3_le_70'] = (c['top1_share'] is not None
                                         and c['top1_share'] <= 0.40
                                         and c['top3_share'] is not None
                                         and c['top3_share'] <= 0.70)
    checks['7_vs_random_plus_1pp'] = (net is not None and b3_dev_mean is not None
                                      and net >= b3_dev_mean + 0.010)
    rate = m['dev']['execution_rate']
    checks['8_execution_ge_95pct'] = rate is not None and rate >= 0.95
    checks['dev_pass'] = all(v for k, v in checks.items() if k != 'dev_pass')
    checks['dev_excess_vs_b1'] = excess
    checks['positive_years'] = len(pos_years)
    return checks


def evaluate_val_gate(m: dict, b1_val: dict) -> dict:
    checks = {}
    net = m['val']['net_cagr']
    excess = (net - b1_val['net_cagr']) if net is not None else None
    checks['1_excess_ge_1pp'] = excess is not None and excess >= 0.010
    yearly = m['val']['excess_by_year']
    checks['2_both_years_positive'] = (len(yearly) == 2
                                       and all(e is not None and e > 0
                                               for e in yearly.values()))
    cap = 6.0 if m['freq'] == 'monthly' else 12.0
    to = m['val']['max_one_side_turnover']
    c = m['val']['concentration']
    checks['3_risk_limits'] = (m['val']['max_drawdown'] is not None
                               and abs(m['val']['max_drawdown']) <= 0.20
                               and to is not None and to <= cap
                               and c['top1_share'] is not None
                               and c['top1_share'] <= 0.40
                               and c['top3_share'] is not None
                               and c['top3_share'] <= 0.70)
    checks['val_pass'] = all(checks.values())
    checks['val_excess_vs_b1'] = excess
    return checks


def evaluate_test(m: dict, b1_test: dict) -> dict:
    net = m['test']['net_cagr']
    excess = (net - b1_test['net_cagr']) if net is not None else None
    ok = (excess is not None and excess >= 0.0
          and m['test']['max_drawdown'] is not None
          and abs(m['test']['max_drawdown']) <= 0.20)
    return {'test_excess_vs_b1': excess, 'test_max_dd': m['test']['max_drawdown'],
            'test_pass': ok}


# --------------------------------------------------------------------------- #
# P2-R8 daily risk overlay (exp-20260918-p2r8-daily-risk)
#
# Registered semantics (frozen config configs/experiments/p2r8-daily-risk.json,
# written BEFORE any R8 signal ran; inherits p2r7-etf-exposure.json by pinned
# sha256): monthly Top-3 momentum selection inherited verbatim from R7; the
# exposure E_t is now judged at EVERY session close; trades happen only on a
# STATE CHANGE (E_t != E_{t-1}), executed at the t+1 open by re-sizing ALL
# held legs to min(E_t/3, 25%) x equity(t close) (members unchanged); a
# monthly signal day colliding with a state change merges into ONE combined
# target executed once; postponed re-sizing legs retry at later opens and the
# LATEST target wins; risk buys count toward gate-5 buy notional; the cash
# pool never goes negative.  Mechanisms: FIX75 (control anchor, zero risk
# trades, MUST equal R7 C01 bit-exactly), T200/T60 (index SMA), T20c2 (two
# consecutive sessions above SMA20: fast-out slow-in), D252/D60 (rolling-peak
# drawdown, insufficient history -> e_low), PDD (own-instance equity vs its
# running peak, path-dependent), X1 (T200-off OR D252(10%)-off -> e_low).
# --------------------------------------------------------------------------- #
def sma_trend_state(index_close: pl.DataFrame, calendar: list[date],
                    sma_sessions: int) -> dict[date, bool]:
    """True = risk-on: index close > SMA(sma_sessions index sessions ending at
    t inclusive), asof row with trade_date <= calendar day.  SMA unavailable
    -> risk-off (registered fallback)."""
    frame = index_close.with_columns(
        pl.col('close').rolling_mean(sma_sessions, min_samples=sma_sessions)
        .alias('_sma'))
    dates = frame['trade_date'].to_list()
    closes = frame['close'].to_list()
    smas = frame['_sma'].to_list()
    out: dict[date, bool] = {}
    for d in calendar:
        pos = bisect_right(dates, d) - 1
        out[d] = bool(pos >= 0 and smas[pos] is not None
                      and closes[pos] > smas[pos])
    return out


def t20c2_state(index_close: pl.DataFrame, calendar: list[date],
                sma_sessions: int = 20) -> dict[date, bool]:
    """Two-day-confirm trend: on iff close > SMA20 on the two CONSECUTIVE
    index sessions t-1 and t (fast-out slow-in: one day below exits, two days
    above re-enter).  Insufficient history -> risk-off."""
    frame = index_close.with_columns(
        pl.col('close').rolling_mean(sma_sessions, min_samples=sma_sessions)
        .alias('_sma'))
    dates = frame['trade_date'].to_list()
    above = [c is not None and s is not None and c > s
             for c, s in zip(frame['close'].to_list(), frame['_sma'].to_list())]
    on2 = [above[i - 1] and above[i] if i >= 1 else False
           for i in range(len(above))]
    out: dict[date, bool] = {}
    for d in calendar:
        pos = bisect_right(dates, d) - 1
        out[d] = bool(pos >= 0 and on2[pos])
    return out


def rolling_dd_state(index_close: pl.DataFrame, calendar: list[date],
                     window: int, dd_threshold: float) -> dict[date, bool]:
    """On iff close >= rolling peak (max over ``window`` index sessions ending
    at t inclusive) x (1 - dd_threshold).  Insufficient history -> risk-off
    (registered fallback)."""
    frame = index_close.with_columns(
        pl.col('close').rolling_max(window, min_samples=window).alias('_peak'))
    dates = frame['trade_date'].to_list()
    closes = frame['close'].to_list()
    peaks = frame['_peak'].to_list()
    out: dict[date, bool] = {}
    for d in calendar:
        pos = bisect_right(dates, d) - 1
        out[d] = bool(pos >= 0 and peaks[pos] is not None
                      and closes[pos] >= peaks[pos] * (1.0 - dd_threshold))
    return out


def x1_compose(t200: dict[date, bool], d252: dict[date, bool]) -> dict[date, bool]:
    """X1: risk-on iff the T200 state AND the D252(0.10) state are both on
    (either firing -> e_low)."""
    return {d: (t200[d] and d252[d]) for d in t200}


def exposures_from_state(state: dict[date, bool], level_on: float,
                         level_off: float) -> dict[date, float]:
    return {d: (level_on if s else level_off) for d, s in state.items()}


def constant_risk_fn(level: float) -> Callable[[date, float], float]:
    def fn(day: date, equity: float) -> float:
        return level
    return fn


def pdd_risk_fn(dd_threshold: float, level_on: float = 0.90,
                level_off: float = 0.40) -> Callable[[date, float], float]:
    """Own-instance running-peak drawdown gate (PDD).  Each instance (strategy
    net/gross run, B1(m), each B3' seed) gets a FRESH closure; the running
    peak never resets within the simulation; the first judged session has zero
    drawdown -> e_on (registered fallback)."""
    peak: float | None = None

    def fn(day: date, equity: float) -> float:
        nonlocal peak
        peak = equity if peak is None else max(peak, equity)
        return level_on if equity >= peak * (1.0 - dd_threshold) else level_off
    return fn


def _scale_leg(slot: _Slot, cd: CodeData, idx: int, day: date, target: float,
               cash: float, fees: FeeBand, stats: ExecStats,
               result: SimResult) -> tuple[float, str]:
    """R8 re-size one held leg toward ``target`` (value) at the current open.
    Returns (cash_delta, outcome); outcome is 'filled' or 'cash_capped' (a
    buy budget capped by the cash pool at/below the commission minimum).
    Quote/limit checks are the caller's responsibility.  The position's
    cumulative net-spend (entry budget) is adjusted proportionally on sells
    and additively on buys so the close-out pnl stays cash-flow consistent."""
    adj = cd.adj_open[idx]
    value = slot.units * adj
    delta = target - value
    if abs(delta) <= 1e-9:
        return 0.0, 'filled'
    if delta > 0.0:
        budget = min(delta, cash)
        if budget <= fees.commission_min:
            stats.risk_buys_cash_capped += 1
            return 0.0, 'cash_capped'
        fee = _buy_fee(budget, fees)
        units = (budget - fee) / adj
        slot.units += units
        if slot.entry is not None:
            slot.entry['budget'] = slot.entry.get('budget', 0.0) + budget
            slot.entry['units'] = slot.units  # keep the position book in sync
        stats.risk_buys_filled += 1
        result.trades.append({
            'session': day, 'code': cd.code, 'side': 'buy',
            'kind': 'retarget_buy', 'raw_price': cd.open[idx],
            'adj_price': adj, 'notional': budget, 'fee': fee, 'units': units,
            'status': 'filled'})
        return -budget, 'filled'
    units_sold = min(slot.units, -delta / adj)
    gross = units_sold * adj
    if gross <= fees.commission_min:
        # de-minimis re-size: the 5-CNY commission minimum would make the
        # proceeds negative and overdraw the never-negative cash pool ->
        # rule-compliant skip (registered cash discipline, sell-side analog;
        # disclosed deviation 9)
        stats.risk_sells_feemin_skipped += 1
        return 0.0, 'cash_capped'
    fee = max(gross * fees.commission_pct, fees.commission_min)
    proceeds = gross - fee
    if slot.entry is not None and slot.units > 0:
        slot.entry['budget'] *= (slot.units - units_sold) / slot.units
    slot.units -= units_sold
    if slot.entry is not None:
        slot.entry['units'] = slot.units  # keep the position book in sync
    stats.risk_sells_filled += 1
    result.trades.append({
        'session': day, 'code': cd.code, 'side': 'sell',
        'kind': 'retarget_sell', 'raw_price': cd.open[idx], 'adj_price': adj,
        'notional': gross, 'fee': fee, 'units': units_sold, 'status': 'filled',
        'pnl': None})
    return proceeds, 'filled'


def _build_risk_plan(slots: list[_Slot], day: date, ranked: list[str] | None,
                     changed: bool, e_t: float, equity: float,
                     stats: ExecStats, n_slots: int) -> dict:
    """Plan built at the close of session t for the t+1 open.  ``ranked`` is
    not None on a monthly signal day (R7 member plan); ``changed`` marks a
    risk state change.  Monthly + changed = ONE combined target (member
    updates x current E_t budget, keepers re-sized too)."""
    if ranked is not None:
        plan = build_plan(slots, ranked, stats, n=n_slots)
        sell_legs = [{'plan_date': day, 'side': 'sell', 'outcome': None,
                      'code': s.code, 'risk': False}
                     for s in plan['sell_slots']]
        buy_legs = [{'plan_date': day, 'side': 'buy', 'outcome': None,
                     'code': None, 'risk': False}
                    for _ in range(plan['n_buy'])]
        rescale: list[dict] = []
        sell_ids = {id(s) for s in plan['sell_slots']}
        if changed:
            for slot in slots:
                if (slot.code is not None and not slot.exit_due
                        and id(slot) not in sell_ids):
                    rescale.append({
                        'slot': slot,
                        'leg': {'plan_date': day, 'side': 'rescale',
                                'outcome': None, 'code': slot.code,
                                'risk': True}})
        # a plan supersedes the postponed targets of the slots it covers
        # (leavers: the full exit wins; keepers on a changed day: the fresher
        # re-size wins).  Uncovered keepers keep retrying their old target.
        for slot in slots:
            rt = slot.risk_target
            if rt is None or rt['leg']['outcome'] is not None:
                continue
            if id(slot) in sell_ids:
                rt['leg']['outcome'] = 'superseded_by_exit'
                slot.risk_target = None
            elif changed:
                rt['leg']['outcome'] = 'superseded_latest'
                slot.risk_target = None
        scope_ids = sell_ids | {id(r['slot']) for r in rescale}
        stats.risk_legs_planned += len(rescale)
        return {'kind': 'monthly', 'plan': plan, 'signal_day': day,
                'equity_t': equity, 'exposure': e_t, 'sell_legs': sell_legs,
                'buy_legs': buy_legs, 'rescale': rescale,
                'frac': leg_frac(e_t, n_slots), 'scope_ids': scope_ids,
                'changed': changed}
    frac = leg_frac(e_t, n_slots)
    rescale = []
    for slot in slots:
        if slot.code is None or slot.exit_due:
            continue
        rt = slot.risk_target
        if rt is not None and rt['leg']['outcome'] is None:
            rt['leg']['outcome'] = 'superseded_latest'  # latest target wins
        slot.risk_target = None
        rescale.append({'slot': slot,
                        'leg': {'plan_date': day, 'side': 'rescale',
                                'outcome': None, 'code': slot.code,
                                'risk': True}})
    stats.risk_legs_planned += len(rescale)
    return {'kind': 'retarget', 'plan': None, 'signal_day': None,
            'equity_t': equity, 'exposure': e_t, 'sell_legs': [],
            'buy_legs': [], 'rescale': rescale, 'frac': frac,
            'scope_ids': {id(r['slot']) for r in rescale}, 'changed': True}


def _execute_risk_plan(pending: dict, slots: list[_Slot],
                       bank: CodeDataBank, si: int, day: date, cash: float,
                       fees: FeeBand, stats: ExecStats,
                       result: SimResult) -> float:
    """Execute the plan at the t+1 open.  Monthly plans run the unchanged R7
    executor first (exits then entrant buys); then every keeper re-scale leg
    moves toward frac(E_t) x equity_t; quote/limit failures postpone the leg
    with the latest target."""
    if pending['kind'] == 'monthly':
        p7 = {'plan': pending['plan'], 'signal_day': pending['signal_day'],
              'equity_t': pending['equity_t'], 'exposure': pending['exposure'],
              'sell_legs': pending['sell_legs'], 'buy_legs': pending['buy_legs']}
        cash = _execute_plan_exposure(p7, slots, bank, si, day, cash, fees,
                                      stats, result)
    target = pending['frac'] * pending['equity_t']
    for item in pending['rescale']:
        slot, leg = item['slot'], item['leg']
        if slot.code is None:  # force-delisted earlier in this open
            leg['outcome'] = 'no_holding'
            continue
        cd = bank.get(slot.code)
        idx = cd.idx_at(si)
        if idx is None:
            stats.risk_suspended += 1
            slot.risk_target = {'frac': pending['frac'],
                                'equity_t': pending['equity_t'], 'leg': leg}
            continue
        side = 'buy' if target > slot.units * cd.adj_open[idx] else 'sell'
        blocked = cd.limit_blocked(idx, side)
        if blocked is None or blocked:
            if blocked:
                stats.risk_limit_blocked += 1
            slot.risk_target = {'frac': pending['frac'],
                                'equity_t': pending['equity_t'], 'leg': leg}
            continue
        delta_cash, outcome = _scale_leg(slot, cd, idx, day, target, cash,
                                         fees, stats, result)
        cash += delta_cash
        leg['outcome'] = outcome
    return cash


def simulate_daily_risk(config_id: str, bank: CodeDataBank,
                        calendar: list[date], start: date,
                        signal_days: list[date],
                        selector: Callable[[date], list[str]],
                        risk_fn: Callable[[date, float], float], *,
                        n_slots: int, fees: FeeBand,
                        total: float = 200_000.0) -> SimResult:
    """One continuous N-slot rotation path under the R8 DAILY risk overlay.

    Identical loop skeleton to ``simulate_exposure`` (next-open execution,
    9.5% proxy, suspension postponement, slot-busy cancellation, forced delist
    exits, boundary carry, single never-negative cash pool).  Differences:
    ``risk_fn(day, equity_close)`` is judged at EVERY session close; a state
    change (E_t != E_{t-1}) plans a re-size of all held legs to
    min(E_t/N, 25%) x equity_t for the next open; monthly signal days merge
    with a coincident state change into one combined execution; postponed
    re-scales retry with the latest target.  With a constant ``risk_fn`` the
    engine performs zero risk trades and reproduces ``simulate_exposure``
    bit-exactly (C01 anchor requirement)."""
    result = SimResult(config_id=config_id)
    stats = result.exec_stats
    slots = [_Slot() for _ in range(n_slots)]
    cash = total
    pending: dict | None = None
    signal_set = set(signal_days)
    start_idx = first_session_index(calendar, start)
    last_idx = len(calendar) - 1
    prev_e: float | None = None
    e_series: list[float] = []

    for si in range(start_idx, last_idx + 1):
        day = calendar[si]

        # 1. retry exits postponed from earlier sessions (R7 semantics)
        for slot in slots:
            if slot.exit_due and slot.code is not None:
                cd = bank.get(slot.code)
                idx = cd.idx_at(si)
                if idx is None:
                    continue
                blocked = cd.limit_blocked(idx, 'sell')
                if blocked is None or blocked:
                    if blocked:
                        stats.exit_limit_blocked += 1
                    continue
                leg_ref = slot.sell_leg  # captured BEFORE _close_ex clears it
                cash += _close_ex(slot, cd, idx, si, day, 'sell_postponed',
                                  fees, stats, result)
                if leg_ref is not None:
                    leg_ref['outcome'] = 'postponed_then_filled'

        # 1b. retry risk re-scales postponed from earlier sessions (latest
        # target wins; slots covered by the pending plan wait for step 3)
        for slot in slots:
            rt = slot.risk_target
            if rt is None or slot.code is None or slot.exit_due:
                continue
            if pending is not None and id(slot) in pending['scope_ids']:
                continue
            cd = bank.get(slot.code)
            idx = cd.idx_at(si)
            if idx is None:
                continue
            side = ('buy' if rt['frac'] * rt['equity_t']
                    > slot.units * cd.adj_open[idx] else 'sell')
            blocked = cd.limit_blocked(idx, side)
            if blocked is None or blocked:
                if blocked:
                    stats.risk_limit_blocked += 1
                continue
            leg = rt['leg']
            delta_cash, outcome = _scale_leg(
                slot, cd, idx, day, rt['frac'] * rt['equity_t'], cash, fees,
                stats, result)
            cash += delta_cash
            leg['outcome'] = (outcome if outcome == 'cash_capped'
                              else 'postponed_then_filled')
            slot.risk_target = None

        # 2. forced delist exits (never on the entry session: T+1)
        for slot in slots:
            if slot.code is not None and not slot.exit_due:
                cd = bank.get(slot.code)
                if not cd.stopped_mid:
                    continue
                idx = cd.idx_at(si)
                if (idx is not None and cd.last_row[idx]
                        and slot.entry['entry_session'] < si):
                    cash += _close_ex(slot, cd, idx, si, day,
                                      'forced_delist_close', fees, stats,
                                      result, at_close=True)

        # 3. execute the plan built at the previous close (t+1 open)
        if pending is not None:
            cash = _execute_risk_plan(pending, slots, bank, si, day, cash,
                                      fees, stats, result)
            pending = None

        # 4. mark equity
        equity = cash
        for slot in slots:
            if slot.code is not None:
                cd = bank.get(slot.code)
                mi = cd.mark_idx(si)
                if mi is not None:
                    equity += slot.units * cd.adj_close[mi]
        if cash < -1e-6:  # registered invariant; engine caps budgets so this
            raise RuntimeError(  # must never fire
                f'{config_id}: negative cash pool on {day}: {cash:.6f}')
        result.max_negative_cash = min(result.max_negative_cash, cash)
        result.sessions.append(day)
        result.equity.append(equity)

        # 5. R8 daily risk state at this close; plan for the next open
        e_t = risk_fn(day, equity)
        e_series.append(e_t)
        changed = prev_e is not None and e_t != prev_e
        if si < last_idx and (day in signal_set or changed):
            ranked = selector(day) if day in signal_set else None
            pending = _build_risk_plan(slots, day, ranked, changed, e_t,
                                       equity, stats, n_slots)
            result.leg_log.extend(pending['sell_legs'])
            result.leg_log.extend(pending['buy_legs'])
            result.leg_log.extend(item['leg'] for item in pending['rescale'])
            if pending['plan'] is not None:
                for slot, leg in zip(pending['plan']['sell_slots'],
                                     pending['sell_legs']):
                    slot.sell_leg = leg
        prev_e = e_t

    for slot in slots:
        if slot.code is not None:
            stats.sells_pending_at_end += 1
            result.final_open.append({**slot.entry, 'open_at_end': True,
                                      'exit_session': last_idx})
        if (slot.risk_target is not None
                and slot.risk_target['leg']['outcome'] is None):
            slot.risk_target['leg']['outcome'] = 'pending_at_end'
    for leg in result.leg_log:  # unresolved planned legs = pending at end
        if leg['outcome'] is None:
            leg['outcome'] = 'pending_at_end'
    result.extra['e_series'] = e_series
    return result


# --------------------------------------------------------------------------- #
# P2-R9 risk-delivery engineering round (exp-20260918-p2r9-risk-delivery)
#
# Registered semantics (frozen config configs/experiments/p2r9-risk-delivery.json,
# written BEFORE any R9 signal ran; inherits p2r7-etf-exposure.json by pinned
# sha256 and reuses the R8 daily-risk engine verbatim): on top of the R8 daily
# overlay the exposure state machine gains HYSTERESIS -- state starts ON, goes
# OFF when the mechanism drawdown >= T and re-arms ON only when the drawdown
# FROM THE SAME REFERENCE PEAK <= T/2 (D-family reference = rolling-window
# peak, the window keeps rolling; PDD reference = all-time running peak, never
# resets).  X1 (C11) is OFF when EITHER arm fires and ON only when BOTH arms
# have re-armed.  With rearm=None the R8 no-hysteresis path functions are used
# verbatim so the A1/A2 bit-exact anchors cannot be perturbed.  Everything else
# (monthly selection, leg budget min(E_t/N, 25%), next-open execution,
# never-negative cash pool) inherits R8 unchanged; N in {3, 4}.
# --------------------------------------------------------------------------- #
def rolling_dd_series(index_close: pl.DataFrame, calendar: list[date],
                      window: int) -> dict[date, float | None]:
    """Positive drawdown of the index close from the rolling ``window``-session
    peak (inclusive of t), asof row with trade_date <= calendar day; None while
    the window is not formed (registered insufficient-history fallback).  The
    windowing matches ``rolling_dd_state`` exactly (same rolling_max, same
    asof), so a state derived as ``dd is not None and dd <= threshold``
    coincides with the R8 no-hysteresis state session for session."""
    frame = index_close.with_columns(
        pl.col('close').rolling_max(window, min_samples=window).alias('_peak'))
    dates = frame['trade_date'].to_list()
    closes = frame['close'].to_list()
    peaks = frame['_peak'].to_list()
    out: dict[date, float | None] = {}
    for d in calendar:
        pos = bisect_right(dates, d) - 1
        out[d] = (None if pos < 0 or peaks[pos] is None
                  else 1.0 - closes[pos] / peaks[pos])
    return out


def hysteresis_state(dd_of: dict[date, float | None], calendar: list[date],
                     threshold: float, rearm: float, start: date
                     ) -> dict[date, bool]:
    """Registered R9 hysteresis state machine over a drawdown series (True =
    risk-on).  State starts ON at the first calendar session on/after
    ``start``; OFF when dd >= ``threshold`` or the window is not formed
    (registered insufficient-history fallback = treated as triggered);
    re-arms ON when dd (vs the series' current reference peak) <= ``rearm``."""
    state = True
    out: dict[date, bool] = {}
    for d in calendar:
        if d < start:
            continue
        dd = dd_of.get(d)
        if dd is None:
            state = False
        elif state:
            if dd >= threshold:
                state = False
        elif dd <= rearm:
            state = True
        out[d] = state
    return out


def pdd_hysteresis_risk_fn(dd_threshold: float, rearm: float,
                           level_on: float = 0.90,
                           level_off: float = 0.40
                           ) -> Callable[[date, float], float]:
    """PDD with the registered R9 hysteresis: the reference peak is the
    instance's all-time running equity peak (never resets); OFF when
    dd >= dd_threshold, re-arms ON when dd <= rearm from the SAME peak.
    Each instance (strategy net/gross run, B1(m), each B3' seed) gets a FRESH
    closure; the first judged session has zero drawdown -> e_on."""
    peak: float | None = None
    on = True

    def fn(day: date, equity: float) -> float:
        nonlocal peak, on
        peak = equity if peak is None else max(peak, equity)
        dd = 1.0 - equity / peak
        if on:
            if dd >= dd_threshold:
                on = False
        elif dd <= rearm:
            on = True
        return level_on if on else level_off
    return fn


def x1_hysteresis_risk_fn(d_state: dict[date, bool], pdd_threshold: float,
                          pdd_rearm: float, level_on: float = 0.90,
                          level_off: float = 0.40
                          ) -> Callable[[date, float], float]:
    """C11 X1 with hysteresis: OFF when the index D-arm state is off OR the
    own-equity PDD arm has fired; ON only when BOTH arms are (re-)armed.
    The D-arm state is a precomputed dict (shared, equity-independent); the
    PDD arm maintains its own all-time-peak state machine (fresh per
    instance, never resets)."""
    peak: float | None = None
    pdd_on = True

    def fn(day: date, equity: float) -> float:
        nonlocal peak, pdd_on
        peak = equity if peak is None else max(peak, equity)
        dd = 1.0 - equity / peak
        if pdd_on:
            if dd >= pdd_threshold:
                pdd_on = False
        elif dd <= pdd_rearm:
            pdd_on = True
        return level_on if (pdd_on and d_state[day]) else level_off
    return fn


def turnover_decomposition(result: SimResult) -> dict[int, dict]:
    """R9 registered disclosure: per-year BUY notional split into the monthly
    selection base (trade kind 'open') and the risk-overlay increment
    ('retarget_buy'; risk buys count toward gate-5 with no exemption), each
    also as one-side turnover over mean equity."""
    per_year: dict[int, dict] = {}
    for t in result.trades:
        book = per_year.setdefault(
            t['session'].year,
            {'selection_buy_notional': 0.0, 'risk_buy_notional': 0.0})
        if t['side'] == 'buy':
            key = ('risk_buy_notional' if t['kind'] == 'retarget_buy'
                   else 'selection_buy_notional')
            book[key] += t['notional']
    eq_by_year: dict[int, list[float]] = {}
    for d, v in zip(result.sessions, result.equity):
        eq_by_year.setdefault(d.year, []).append(v)
    out = {}
    for y, book in sorted(per_year.items()):
        eqs = eq_by_year.get(y, [])
        mean_eq = sum(eqs) / len(eqs) if eqs else None
        total_buy = book['selection_buy_notional'] + book['risk_buy_notional']
        out[y] = {**book, 'total_buy_notional': total_buy,
                  'mean_equity': mean_eq,
                  'one_side_turnover': (total_buy / mean_eq) if mean_eq else None,
                  'selection_turnover': (book['selection_buy_notional'] / mean_eq
                                         if mean_eq else None),
                  'risk_increment_turnover': (book['risk_buy_notional'] / mean_eq
                                              if mean_eq else None)}
    return out


def hysteresis_switch_stats(sessions: list[date], e_series: list[float],
                            e_low: float) -> dict[int, dict]:
    """R9 registered disclosure: per-year counts of OFF triggers (on->off) and
    re-arms (off->on) of the hysteresis machine, with off share and mean
    exposure."""
    per_year: dict[int, dict] = {}
    prev: float | None = None
    for day, e in zip(sessions, e_series):
        y = per_year.setdefault(day.year, {
            'n_sessions': 0, 'n_off_triggers': 0, 'n_rearms': 0,
            'n_switches': 0, 'off_sessions': 0, 'sum_e': 0.0})
        y['n_sessions'] += 1
        y['sum_e'] += e
        if prev is not None and e != prev:
            y['n_switches'] += 1
            if e == e_low:
                y['n_off_triggers'] += 1
            else:
                y['n_rearms'] += 1
        if e == e_low:
            y['off_sessions'] += 1
        prev = e
    return {str(y): {'n_sessions': v['n_sessions'],
                     'n_switches': v['n_switches'],
                     'n_off_triggers': v['n_off_triggers'],
                     'n_rearms': v['n_rearms'],
                     'off_share': round(v['off_sessions'] / v['n_sessions'], 4),
                     'mean_exposure': round(v['sum_e'] / v['n_sessions'], 4)}
            for y, v in sorted(per_year.items())}


# --------------------------------------------------------------------------- #
# P2-R8 section 0 preanalysis (index-only; fixed definitions, computed BEFORE
# any strategy run output; expectation management, NOT a gate)
# --------------------------------------------------------------------------- #
def percentile(vals: list[float], q: float) -> float | None:
    """Linear-interpolation percentile (q in [0, 1]); None for empty input."""
    if not vals:
        return None
    s = sorted(vals)
    if len(s) == 1:
        return s[0]
    pos = (len(s) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (pos - lo)


def preanalysis_sect0(index_close: pl.DataFrame, *, dev_start: date,
                      dev_end: date, stress_start: date, stress_end: date,
                      peak_reference: int = 252) -> dict:
    """Registered section-0 statistics from the pinned 000300.SH batch only.

    Per mechanism (T200/T60/T20c2/D252-10/D252-15/D60-8/X1) over the dev
    window: on->off trigger count, risk-off session share, and the index
    decline already suffered from the local peak at each trigger (p50/p90/
    max).  Local-peak reference: the mechanism's OWN rolling window for the
    D mechanisms (== the rule quantity) and the trailing 252-session peak
    (expanding before it is formed) for the SMA mechanisms -- a fixed
    disambiguation recorded in the deviation list, not a tunable.  Index
    stress: worst single-session and 5-session declines in the stress window
    (index own rows)."""
    dates = index_close['trade_date'].to_list()
    closes = index_close['close'].to_list()
    n = len(dates)
    cal = dates  # judge the mechanisms on the index's own sessions
    states = {
        'T200': sma_trend_state(index_close, cal, 200),
        'T60': sma_trend_state(index_close, cal, 60),
        'T20c2': t20c2_state(index_close, cal, 20),
        'D252-10': rolling_dd_state(index_close, cal, 252, 0.10),
        'D252-15': rolling_dd_state(index_close, cal, 252, 0.15),
        'D60-8': rolling_dd_state(index_close, cal, 60, 0.08),
    }
    states['X1'] = x1_compose(states['T200'], states['D252-10'])
    own_window = {'D252-10': 252, 'D252-15': 252, 'D60-8': 60}

    def decline_at(i: int, window: int | None) -> float:
        w = window if window is not None else peak_reference
        seg = closes[max(0, i - w + 1):i + 1]
        return 1.0 - closes[i] / max(seg)  # positive depth; max = deepest

    mechs: dict[str, dict] = {}
    for name, st in states.items():
        dev_rows = [i for i in range(n) if dev_start <= dates[i] <= dev_end]
        off = sum(1 for i in dev_rows if not st[dates[i]])
        triggers = [i for i in dev_rows
                    if not st[dates[i]] and i > 0 and st[dates[i - 1]]]
        declines = [decline_at(i, own_window.get(name)) for i in triggers]
        mechs[name] = {
            'dev_sessions': len(dev_rows),
            'trigger_count': len(triggers),
            'trigger_dates': [dates[i].isoformat() for i in triggers],
            'risk_off_share': (off / len(dev_rows)) if dev_rows else None,
            'depth_from_local_peak_at_trigger': {
                'definition': ('own rolling window peak'
                               if name in own_window else
                               f'trailing {peak_reference}-session peak '
                               '(expanding before formed)'),
                'convention': 'positive drawdown depth; max = deepest',
                'p50': percentile(declines, 0.50),
                'p90': percentile(declines, 0.90),
                'max': percentile(declines, 1.0),
                'n': len(declines)},
        }

    worst1 = worst5 = None
    for i in range(n):
        if not (stress_start <= dates[i] <= stress_end):
            continue
        if i >= 1:
            r = closes[i] / closes[i - 1] - 1.0
            if worst1 is None or r < worst1['ret']:
                worst1 = {'date': dates[i].isoformat(), 'ret': r}
        if i >= 5:
            r = closes[i] / closes[i - 5] - 1.0
            if worst5 is None or r < worst5['ret']:
                worst5 = {'date': dates[i].isoformat(), 'ret': r,
                          'window': [dates[i - 5].isoformat(),
                                     dates[i].isoformat()]}
    return {'index_rows': n, 'range': [dates[0].isoformat(),
                                       dates[-1].isoformat()],
            'mechanisms': mechs,
            'index_stress': {
                'definition': 'min close/prev-close and min close/close(5 own rows back)',
                'worst_single_session': worst1,
                'worst_5_session': worst5}}
