# -*- coding: utf-8 -*-
"""P3R1 eight-config dev readjudication runner (exp-20260918-p3r1-band-readjudication).

Executes the dual-sign-approved band-contract engine (src/quant/backtest/
band_engine.py, UNMODIFIED) on the R16 frozen eight configs, dev window
2015-01-05..2020-12-31 ONLY.  Trial accounting 189 -> 197 (prereg).

Signal source (instruction 1): the authoritative R16 run
20260918T083650-p2r16-trend-dispersion-afab466f leg_log.parquet is REUSED --
per signal date, buy_open legs = entries, sell_full legs = exits, rescale
legs = held incumbents (no band signal).  An independent recompute with the
verbatim r16 module (pools + buffer_membership state machine) must equal the
leg_log-derived membership on every (config, signal) or the run STOPS.

Registered mapping decisions (disclosed in the manifest/report):
- band contract v0 has no partial-rescale primitive: incumbent rescale legs
  are NOT mapped (no drift trimming; exposure paths scale ENTRY sizing only);
- sells = membership exits only (expiry = next signal date; re-issued while
  still departed; K=3 fallback lives inside the engine);
- the 2020-12-31 signal is DROPPED (execution would land in 2021 = val data;
  same registered freeze-drop rule as R16's 2024-12-31 signal);
- buy target_notional = exposure(t) x band-account equity(t) / K (iterative
  to a fixed point; R16 sized from its own mark -- different by construction).
"""
from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

import polars as pl

RUN_DIR = Path(__file__).resolve().parents[1]
ROOT = RUN_DIR.parents[2]
SRC = ROOT / 'src'
sys.path.insert(0, str(SRC))

import numpy as np  # noqa: E402

import quant.research.etf_rotation as er  # noqa: E402
from quant.research import p2r16_trend_dispersion as r16  # noqa: E402
from quant.backtest.band_engine import (  # noqa: E402
    load_dividends_h5, load_split_factor_h5, load_stk_limit_batch,
    run_band_backtest)

D = date
STARTED = datetime.now(timezone.utc)
BUDGET_S = 1800.0
LOG: list[str] = []


def log(msg: str) -> None:
    LOG.append(str(msg))
    print(msg, flush=True)


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open('rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2,
                               allow_nan=False), encoding='utf-8')


def rss_gb() -> float:
    import psutil
    return psutil.Process().memory_info().rss / 1e9


def check_budget(t0: float) -> None:
    if time.perf_counter() - t0 > BUDGET_S:
        raise TimeoutError(f'budget exceeded: {time.perf_counter() - t0:.0f}s '
                           f'> {BUDGET_S:.0f}s')


R16_RUN = ROOT / 'artifacts/runs/20260918T083650-p2r16-trend-dispersion-afab466f'
CONFIG_PATH = ROOT / 'configs/experiments/p2r16-trend-dispersion.json'
DAILY = ROOT / 'data/processed/baostock-daily-20260917/daily_1999_2024.parquet'
STK_DIR = ROOT / 'data/raw/tushare/stk_limit/20260917-r1'
BUNDLE = ROOT / 'data/processed/rqalpha-bundle-v2-1-20260918'
INDEX_CHUNK = ROOT / 'data/raw/tushare/index_daily/20260917-r1/chunk_000300.SH.csv'
DEV_START, DEV_END = D(2015, 1, 5), D(2020, 12, 31)
CONFIG_IDS = ['C01', 'C02', 'C03', 'C04', 'C05', 'C06', 'C07', 'C08']
PINS = {  # (path, expected sha256:16, role)
    'p2r16_config': (CONFIG_PATH, '27f846a7330919a4', 'eight-config authority'),
    'daily_parquet': (DAILY, 'd9a63f4cc3032926', 'daily OHLC/pool source'),
    'split_factor_h5': (BUNDLE / 'split_factor.h5', '2f436b2f13d09a9b', 'share multipliers'),
    'dividends_h5': (BUNDLE / 'dividends.h5', '46121c09cddde72e', 'per-lot pre-tax cash'),
    'index_chunk_000300': (INDEX_CHUNK, None, 'T200-40 trend basis (R8 pin via r8 config)'),
}


def fail(reason: str) -> None:
    log(f'!! STOP: {reason}')
    write_json(RUN_DIR / 'manifest.json', {
        'run_id': RUN_DIR.name,
        'experiment_id': 'exp-20260918-p3r1-band-readjudication',
        'status': 'failed', 'failure_reason': reason,
        'started_at': STARTED.isoformat(),
        'ended_at': datetime.now(timezone.utc).isoformat()})
    (RUN_DIR / 'logs' / 'runner.log').write_text('\n'.join(LOG) + '\n', encoding='utf-8')
    sys.exit(1)


def main() -> int:
    t0 = time.perf_counter()
    log(f'== P3R1 dev readjudication run {RUN_DIR.name} ==')

    # ---------------- 0a. contract tests (14; must all pass) ----------------
    proc_t = subprocess.run(
        [sys.executable, '-m', 'pytest', 'tests/test_band_contract.py', '-q'],
        cwd=str(ROOT), capture_output=True, text=True, encoding='utf-8',
        errors='replace')
    tests_tail = [ln for ln in proc_t.stdout.strip().splitlines() if ln.strip()][-1]
    log(f'  contract tests: exit={proc_t.returncode}: {tests_tail}')
    (RUN_DIR / 'logs' / 'pytest.log').write_text(
        proc_t.stdout + '\n--- stderr ---\n' + proc_t.stderr, encoding='utf-8')
    if proc_t.returncode != 0:
        fail(f'contract tests failed: {tests_tail}')
    tests_passed = int(tests_tail.split('passed')[0].strip().split()[-1])

    # ---------------- 0. config + identity pins (fail-closed) ---------------
    config = json.loads(CONFIG_PATH.read_text(encoding='utf-8'))
    r16_metrics = json.loads((R16_RUN / 'metrics.json').read_text(encoding='utf-8'))
    r16_manifest = json.loads((R16_RUN / 'manifest.json').read_text(encoding='utf-8'))
    pins = {}
    for name, (path, expect16, role) in PINS.items():
        got = sha256_file(path)
        ok = True if expect16 is None else got.startswith(expect16)
        pins[name] = {'path': str(path.relative_to(ROOT)).replace('\\', '/'),
                      'sha256': got, 'expected16': expect16, 'match': ok, 'role': role}
        log(f'  pin {name}: {got[:16]} match={ok}')
        if not ok:
            fail(f'identity pin mismatch: {name}')
    if not r16_manifest.get('config_file_sha256', '').startswith('27f846a7330919a4'):
        fail('R16 authority run did not pin the frozen config bytes')
    if r16_manifest.get('status') != 'completed':
        fail('R16 authority run is not completed')
    mech = r16.assert_mechanism_identity()          # R8 module fail-closed
    log(f"  R8 mechanism identity: etf_rotation sha256 {mech['module_sha256'][:16]} (pinned)")
    rss0 = rss_gb()

    # ---------------- 1. calendar / signal days / pools ---------------------
    cal = r16.market_calendar(DAILY)
    calendar_full = cal['date'].to_list()
    all_signals = r16.month_end_sessions(cal).filter(
        (pl.col('s') >= DEV_START) & (pl.col('s') <= DEV_END))
    sig_all = all_signals['s'].to_list()
    # execution-safe dev signals: the last one whose execution stays in dev
    idx_of_full = {d: i for i, d in enumerate(calendar_full)}
    signal_days = [d for d in sig_all
                   if idx_of_full[d] + 1 < len(calendar_full)
                   and calendar_full[idx_of_full[d] + 1] <= DEV_END]
    dropped = [d for d in sig_all if d not in set(signal_days)]
    log(f'  dev signals: {len(signal_days)} ({signal_days[0]}..{signal_days[-1]}); '
        f'dropped (execution would land after {DEV_END}): {[str(d) for d in dropped]}')

    log('  building pools (full cross-section, r16 verbatim infrastructure)...')
    hist = r16.build_history_r16(DAILY, cal)
    pool_frame = r16.signal_pools(hist, pl.DataFrame({'s': signal_days}))
    pools_at = r16.pools_by_signal(pool_frame)
    symbols = sorted({s for p in pools_at.values() for s in p['ranked']})
    pool_stats = {
        'n_signals': len(signal_days),
        'mean_pool_size': sum(p['n'] for p in pools_at.values()) / len(pools_at),
        'min_pool_size': min(p['n'] for p in pools_at.values()),
        'mean_q5_share': (sum(sum(1 for v in p['q5'].values() if v)
                              for p in pools_at.values()) / sum(p['n'] for p in pools_at.values())),
    }
    hist = None
    log(f"  pools: mean {pool_stats['mean_pool_size']:.1f}, "
        f"min {pool_stats['min_pool_size']}, q5 share "
        f"{pool_stats['mean_q5_share']:.4f}, ever {len(symbols)}")
    check_budget(t0)

    # ---------------- 2. exposures (T200-40 / FIX75, verbatim) --------------
    index_close = r16.load_index_close(INDEX_CHUNK).filter(
        pl.col('trade_date') <= r16.FREEZE_LAST)
    anchor = r16.t200_behavioral_anchor_check(index_close, calendar_full)
    exposures_by_path = {
        'T200-40': r16.t200_month_end_exposures(index_close, calendar_full, signal_days),
        'FIX75': r16.fix75_exposures(signal_days),
    }
    fallback = r16.t200_fallback_signal_dates(index_close, calendar_full, signal_days)
    r16_fb = r16_metrics.get('t200_fallback_signals', {})
    fb_match = (len(fallback) == r16_fb.get('n', -1)
                and [str(d) for d in fallback] == r16_fb.get('dates', []))
    log(f'  T200 fallback signal dates: n={len(fallback)} matches R16={fb_match}')
    if not fb_match:
        fail('T200 fallback signal dates differ from the R16 record')
    if not anchor.get('all_match'):
        fail('T200 behavioral anchor check failed')

    # ---------------- 3. reuse R16 leg_log + consistency (stop on mismatch) -
    leg = pl.read_parquet(R16_RUN / 'leg_log.parquet')
    mem_events = pl.read_parquet(R16_RUN / 'membership_events.parquet')
    leg_dev = leg.filter(pl.col('plan_date').is_in(signal_days))
    legs_by: dict[tuple[str, date], pl.DataFrame] = {
        k: g for k, g in leg_dev.partition_by(['config_id', 'plan_date'],
                                              as_dict=True).items()}
    consistency = {'per_config': {}, 'all_match': True}
    r16_by = {(r['config_id'], r['signal']): r for r in mem_events.iter_rows(named=True)}
    for cid in CONFIG_IDS:
        spec = config['configs'][cid]
        K, q5_on = int(spec['K']), spec['filter'] == 'on'
        prev: list[str] = []
        mism: list[str] = []
        cnt_mism: list[str] = []
        for t in signal_days:
            g = legs_by.get((cid, t))
            if g is None:
                fail(f'leg_log missing (config={cid}, signal={t})')
            members = set(g.filter(pl.col('kind').is_in(['buy_open', 'rescale']))['symbol'])
            entrants = set(g.filter(pl.col('kind') == 'buy_open')['symbol'])
            leavers = set(g.filter(pl.col('kind') == 'sell_full')['symbol'])
            pool = pools_at.get(t)
            if pool is None:
                fail(f'pool missing for signal {t}')
            nxt, info = r16.buffer_membership(prev, pool['ranked'], pool['q5'], K, q5_on)
            if set(nxt) != members:
                mism.append(str(t))
            ev = r16_by.get((cid, t))
            if ev is None or (ev['n_kept'], ev['n_entrants'], ev['n_left'],
                              ev['n_cash_seats']) != (info['n_kept'], info['n_entrants'],
                                                      info['n_left'], info['n_cash_seats']):
                cnt_mism.append(str(t))
            prev = nxt
        ok = not mism and not cnt_mism
        consistency['per_config'][cid] = {
            'signals_checked': len(signal_days), 'membership_mismatches': mism,
            'count_mismatches_vs_membership_events': cnt_mism, 'match': ok}
        consistency['all_match'] = consistency['all_match'] and ok
        log(f'  consistency {cid}: {"OK" if ok else "MISMATCH"} '
            f'(membership {len(mism)}, counts {len(cnt_mism)})')
        check_budget(t0)
    if not consistency['all_match']:
        fail('signal reconstruction consistency failed vs the R16 records '
             '(leg_log membership and/or membership_events counts)')

    # ---------------- 4. engine input frames --------------------------------
    panel_symbols = sorted({s for (cid, _), g in legs_by.items()
                            for s in g['symbol'].to_list()})
    log(f'  panel symbols (leg_log universe): {len(panel_symbols)}')
    daily = (pl.scan_parquet(DAILY)
             .filter(pl.col('symbol').is_in(panel_symbols))
             .filter((pl.col('date') >= DEV_START) & (pl.col('date') <= DEV_END))
             .select('symbol', 'date', 'open', 'high', 'low', 'close', 'tradestatus')
             .sort('symbol', 'date').collect())
    log(f'  engine panel rows: {daily.height}')
    limits_full, limits_meta = load_stk_limit_batch(STK_DIR)
    # WIRING NOTE (engine untouched): the approved loader returns the raw
    # tushare column names up_limit/down_limit while run_band_backtest
    # validates limit_up/limit_down (the schema its 13 contract tests pin).
    # The bridge is a caller-side rename; recorded in the manifest as a
    # finding for the referee (naming inconsistency only -- no computational
    # effect; the engine never saw differently-named data).
    limits_full = limits_full.rename({'up_limit': 'limit_up',
                                      'down_limit': 'limit_down'})
    limits = (limits_full.filter(pl.col('symbol').is_in(panel_symbols))
              .filter((pl.col('date') >= DEV_START) & (pl.col('date') <= DEV_END)))
    splits_all, _ = load_split_factor_h5(BUNDLE / 'split_factor.h5')
    divs_all, _ = load_dividends_h5(BUNDLE / 'dividends.h5')
    splits = splits_all.filter(pl.col('symbol').is_in(panel_symbols))
    dividends = divs_all.filter(pl.col('symbol').is_in(panel_symbols))
    # SIGN-OFF condition 1: splits fed to the engine contain POOL symbols only
    orphan_splits = sorted(set(splits_all['symbol'].unique()) - set(panel_symbols))
    orphan_divs = sorted(set(divs_all['symbol'].unique()) - set(panel_symbols))
    assert set(splits['symbol']) <= set(panel_symbols), 'splits outside pool!'
    assert set(dividends['symbol']) <= set(panel_symbols), 'dividends outside pool!'
    log(f"  splits rows fed: {splits.height} (pool symbols {splits['symbol'].n_unique()}; "
        f"excluded non-pool rows: {splits_all.height - splits.height}); "
        f"dividend rows fed: {dividends.height} "
        f"(excluded non-pool: {divs_all.height - dividends.height})")
    panel_syms_set = set(panel_symbols)
    close_at = {(s, d): v for s, d, v in zip(
        daily['symbol'].to_list(), daily['date'].to_list(), daily['close'].to_list())}

    # ---------------- 5. run the eight configs through the band engine ------
    from quant.backtest.band_engine import BandResult  # noqa: F401
    results: dict[str, BandResult] = {}
    iterations: dict[str, int] = {}
    for cid in CONFIG_IDS:
        spec = config['configs'][cid]
        K, path = int(spec['K']), spec['path']
        exposures = exposures_by_path[path]
        # entrants / leavers / ranks per signal date for this config
        plan: dict[date, tuple[set, set]] = {}
        for t in signal_days:
            g = legs_by[(cid, t)]
            entrants = sorted(g.filter(pl.col('kind') == 'buy_open')['symbol'].to_list())
            leavers = sorted(g.filter(pl.col('kind') == 'sell_full')['symbol'].to_list())
            plan[t] = (set(entrants), set(leavers))
        rank_of = {t: {s: i + 1 for i, s in enumerate(pools_at[t]['ranked'])}
                   for t in signal_days}
        next_sig = {signal_days[i]: (signal_days[i + 1] if i + 1 < len(signal_days)
                                     else DEV_END) for i in range(len(signal_days))}
        equity_guess = {t: 200_000.0 for t in signal_days}
        prev_rows = None
        res = None
        for it in range(1, 7):
            rows = []
            for t in signal_days:
                entrants, leavers = plan[t]
                nxt = next_sig[t]
                target = round(exposures[t] * equity_guess[t] / K, 2)
                for sym in sorted(entrants):
                    rows.append({
                        'symbol': sym, 'signal_date': t, 'side': 'buy',
                        'anchor_price': float(close_at[(sym, t)]),
                        'priority': rank_of[t].get(sym, 10 ** 6),
                        'target_notional': target, 'shares': None,
                        'expiry_date': nxt})
                for sym in sorted(leavers):
                    rows.append({
                        'symbol': sym, 'signal_date': t, 'side': 'sell',
                        'anchor_price': float(close_at.get((sym, t), np.nan)),
                        'priority': rank_of[t].get(sym, 10 ** 6),
                        'target_notional': None, 'shares': None,
                        'expiry_date': nxt})
            sig_frame = pl.DataFrame(rows, schema={
                'symbol': pl.String, 'signal_date': pl.Date, 'side': pl.String,
                'anchor_price': pl.Float64, 'priority': pl.Int64,
                'target_notional': pl.Float64, 'shares': pl.Int64,
                'expiry_date': pl.Date})
            if prev_rows is not None and sig_frame.equals(prev_rows):
                iterations[cid] = it - 1
                break
            prev_rows = sig_frame
            res = run_band_backtest(sig_frame, daily, limits,
                                    splits, dividends, initial_cash=200_000.0)
            eq_at = dict(zip(res.daily['date'].to_list(),
                             res.daily['equity'].to_list()))
            equity_guess = {t: float(eq_at.get(t, 200_000.0)) for t in signal_days}
            iterations[cid] = it
        else:
            log(f'  {cid}: sizing did NOT fully converge in 6 iterations '
                '(last pass used; disclosed)')
        results[cid] = res
        st = res.stats
        log(f"  {cid} ({spec['K']}/{spec['path']}/filter-{spec['filter']}): "
            f"iters={iterations[cid]} fills={res.fills.height} "
            f"orders={st['signals']} filled={st['orders_filled']} "
            f"equity_end={res.daily['equity'][-1]:,.0f} "
            f"k3_exec={st['k3_fallback']['executed']}")
        check_budget(t0)

    # ---------------- 6. metrics, gates, disclosures ------------------------
    def dev_slice(res: BandResult):
        return er.slice_curve(res.daily['date'].to_list(),
                              res.daily['equity'].to_list(), DEV_START, DEV_END)

    def weights_max(res: BandResult, splits: pl.DataFrame) -> float:
        """Replay fills + split events to daily single-name weights."""
        import bisect
        shares: dict[str, float] = {}
        split_at: dict[tuple[str, date], float] = {}
        for r in splits.iter_rows(named=True):
            split_at[(r['symbol'], r['ex_date'])] = float(r['split_factor'])
        by_date: dict[date, list] = {}
        for f in res.fills.sort('date').iter_rows(named=True):
            by_date.setdefault(f['date'], []).append(f)
        mark_dates: dict[str, list[date]] = {}
        mark_close: dict[str, list[float]] = {}
        for s, d, c in zip(daily['symbol'].to_list(), daily['date'].to_list(),
                           daily['close'].to_list()):
            mark_dates.setdefault(s, []).append(d)
            mark_close.setdefault(s, []).append(c)
        dates = res.daily['date'].to_list()
        equity = res.daily['equity'].to_list()
        wmax = 0.0
        for day, eq in zip(dates, equity):
            for sym in list(shares):
                r = split_at.get((sym, day))
                if r is not None and r != 1.0:
                    shares[sym] = float(np.floor(shares[sym] * r + 0.5))
            for f in by_date.get(day, []):
                delta = f['shares'] if f['side'] == 'buy' else -f['shares']
                shares[f['symbol']] = shares.get(f['symbol'], 0) + delta
            wmax_day = 0.0
            for sym, sh in shares.items():
                if sh <= 0:
                    continue
                dlist = mark_dates.get(sym)
                if not dlist:
                    continue
                i = bisect.bisect_left(dlist, day)
                if i == 0:
                    continue
                mv = sh * mark_close[sym][i - 1]
                wmax_day = max(wmax_day, mv / eq if eq > 0 else 0.0)
            wmax = max(wmax, wmax_day)
        return wmax

    metrics_out: dict[str, dict] = {}
    gates_out: dict[str, dict] = {}
    disclosures: dict[str, dict] = {}
    b3_means = r16_metrics['B3prime_dev_mean_net_cagr']
    b3_seeds = r16_metrics['B3prime_per_seed_dev_net_cagr']
    b3_range = {p: [min(v for k, v in b3_seeds.items() if k.startswith(p)),
                    max(v for k, v in b3_seeds.items() if k.startswith(p))]
                for p in ('T200-40', 'FIX75')}
    any_full_pass = False
    for cid in CONFIG_IDS:
        spec = config['configs'][cid]
        path = spec['path']
        res = results[cid]
        st = res.stats
        sd, sv = dev_slice(res)
        net_cagr = er.cagr(sv[0], sv[-1], sd[0], sd[-1])
        mdd = er.max_drawdown(sd, sv)['max_drawdown']
        strat_years = er.year_returns(sd, sv)
        r16m = r16_metrics['configs'][cid]
        b1_years = {int(k): v for k, v in r16m['b1m_net_return_by_year'].items()}
        years = list(range(sd[0].year, sd[-1].year + 1))
        excess_by_year = {str(y): (strat_years.get(y, 0.0) - b1_years[y]
                                   if y in b1_years else None) for y in years}
        # turnover: buys / mean daily equity per year (R16 formula)
        eq_by_year: dict[int, list[float]] = {}
        for d, v in zip(sd, sv):
            eq_by_year.setdefault(d.year, []).append(v)
        buy_by_year: dict[int, float] = {}
        for f in res.fills.filter(pl.col('side') == 'buy').iter_rows(named=True):
            buy_by_year[f['date'].year] = buy_by_year.get(f['date'].year, 0.0) \
                + f['notional']
        turnover_by_year = {}
        for y in years:
            eqs = eq_by_year.get(y, [])
            mean_eq = sum(eqs) / len(eqs) if eqs else None
            turnover_by_year[str(y)] = {
                'buy_notional': buy_by_year.get(y, 0.0), 'mean_equity': mean_eq,
                'one_side_turnover': (buy_by_year.get(y, 0.0) / mean_eq
                                      if mean_eq else None)}
        max_to = max((v['one_side_turnover'] for v in turnover_by_year.values()
                      if v['one_side_turnover'] is not None), default=None)
        # gate-8 band mapping: filled + rule-compliant no-fill (below_min_lot
        # buys, void_no_position sells, buys cash-blocked through expiry) over
        # all orders -- the analog of R16's at_target/no_lots/cash_capped/
        # feemin_skipped being "executed" and superseded/pending not.
        n_orders = st['signals']['buy'] + st['signals']['sell']
        filled = st['orders_filled']['buy'] + st['orders_filled']['sell']
        ue = st['unfilled_exit_reasons']
        rule_ok = (ue['buy'].get('below_min_lot', 0)
                   + ue['sell'].get('void_no_position', 0))
        ev = res.events
        cash_buy_ids = set(ev.filter(
            (pl.col('event') == 'void_insufficient_cash')
            & (pl.col('side') == 'buy'))['order_id'].to_list())
        filled_buy_ids = set(res.fills.filter(
            pl.col('side') == 'buy')['order_id'].to_list())
        cash_blocked_expired = len(cash_buy_ids - filled_buy_ids)
        executed = filled + rule_ok + cash_blocked_expired
        exec_rate = executed / n_orders if n_orders else None
        m = {
            'net_cagr': net_cagr,
            'net_total_return': sv[-1] / sv[0] - 1.0,
            'max_drawdown': mdd,
            'max_single_name_weight': weights_max(res, splits),
            'turnover_by_year': turnover_by_year,
            'max_one_side_turnover': max_to,
            'execution_rate': exec_rate,
            'execution_rate_mapping': 'band: filled + below_min_lot + '
                                      'void_no_position + cash-blocked-expired '
                                      'over all orders (R16 at_target/no_lots/'
                                      'cash_capped/feemin_skipped analog)',
            'net_return_by_year': {str(y): strat_years.get(y) for y in years},
            'b1m_net_cagr': r16m['b1m_net_cagr'],
            'b1m_max_drawdown': r16m['b1m_max_drawdown'],
            'b1m_net_return_by_year': r16m['b1m_net_return_by_year'],
            'excess_vs_b1m': net_cagr - r16m['b1m_net_cagr'],
            'excess_by_year': excess_by_year,
            'membership_stats': None,
        }
        gates = r16.evaluate_dev_gates(m, b3_means[path])
        m['config'] = spec
        metrics_out[cid] = m
        gates_out[cid] = {'dev': gates}
        any_full_pass = any_full_pass or gates['dev_pass']
        # verdict per prereg labels
        overall_fill = ((st['orders_filled']['buy'] + st['orders_filled']['sell'])
                        / n_orders if n_orders else None)
        in_noise = (b3_range[path][0] <= net_cagr <= b3_range[path][1])
        if gates['dev_pass']:
            verdict = 'pass'
        elif (overall_fill is not None and overall_fill < 0.30 and in_noise):
            verdict = 'untradeable_under_contract'
        else:
            verdict = 'eliminated'
        # disclosures
        lag = st['fill_lag_trading_days']['buy']
        k3_missing_limit = sum(
            1 for r in res.fills.iter_rows(named=True)
            if 'no_limit_info' in (r['detail'] or ''))
        disclosures[cid] = {
            'verdict': verdict,
            'fill_rate_order_day': st['fill_rate_order_day'],
            'order_fill_rate': st['order_fill_rate'],
            'gate8_mapped_execution_rate': exec_rate,
            'fill_lag_buy': lag,
            'k3_fallback': {k: v for k, v in st['k3_fallback'].items()
                            if k != 'pnl_contribution_list'},
            'k3_fallback_executed_missing_limit_info': k3_missing_limit,
            'unfilled_exit_reasons': st['unfilled_exit_reasons'],
            'unfilled_exit_share_buys': st['unfilled_exit_share_buys'],
            'odd_lot_exits': st['odd_lot_exits']['count'],
            'commission_warnings': st['commission_warnings'],
            'void_days': st['void_days'],
            'same_bar_deferred_sells': st['same_bar_deferred_sells'],
            'vs_r16_delta': {
                'net_cagr': {'band': net_cagr, 'r16': r16m['net_cagr']},
                'max_drawdown': {'band': mdd, 'r16': r16m['max_drawdown']},
                'max_one_side_turnover': {'band': max_to,
                                          'r16': r16m['max_one_side_turnover']},
                'execution_rate': {'band': exec_rate,
                                   'r16': r16m['execution_rate'],
                                   'note': 'different outcome mappings; see '
                                           'execution_rate_mapping'},
                'b3_noise_band_same_path': b3_range[path],
            },
        }
        gates_out[cid]['verdict'] = verdict
        log(f"  {cid}: netCAGR {net_cagr*100:+.2f}% (B1 {r16m['b1m_net_cagr']*100:+.2f}%, "
            f"excess {m['excess_vs_b1m']*100:+.2f}pp) mdd {mdd*100:.2f}% "
            f"adv {gates['advantage_years']}/6 to {max_to:.2f} w {m['max_single_name_weight']*100:.1f}% "
            f"exec {exec_rate*100 if exec_rate else 0:.1f}% fill {overall_fill*100 if overall_fill else 0:.1f}% "
            f"-> {verdict} failed={gates['failed_gates']}")

    # ---------------- 7. outputs -------------------------------------------
    out = RUN_DIR / 'outputs'
    out.mkdir(exist_ok=True)
    for cid, res in results.items():
        res.fills.write_parquet(out / f'{cid}_fills.parquet')
        res.daily.write_parquet(out / f'{cid}_daily_equity.parquet')
        res.events.write_parquet(out / f'{cid}_events.parquet')
        res.positions_final.write_parquet(out / f'{cid}_positions_final.parquet')
    if any_full_pass:
        log('  !! at least one config passed ALL dev gates -- STOPPING before '
            'val (2021-2024 untouched; val requires separate approval)')
    write_json(out / 'metrics_and_gates.json', {
        'metrics': metrics_out, 'gates': gates_out,
        'disclosures': disclosures,
        'b3prime_dev_mean_net_cagr': b3_means,
        'b3prime_noise_band_same_path': b3_range,
        'advanced_to_validation': False,
        'val_consumed': False,
        'stop_note': ('dev full pass present -> val requires separate '
                      'orchestrator approval' if any_full_pass else
                      'no config passed all dev gates; val not consumed '
                      '(one-shot discipline)')})

    report = ['# P3R1 八配置 dev 重裁定（区间契约）', '',
              f'- run: `{RUN_DIR.name}`；引擎：`src/quant/backtest/band_engine.py`'
              '（双签放行版，未改动）',
              f'- 窗口：dev 2015-01-05..2020-12-31（只跑 dev；val 未消费）；'
              f'信号 {signal_days[0]}..{signal_days[-1]}（{len(signal_days)} 个月末，'
              f'2020-12-31 信号按冻结先例丢弃：执行将落入 2021）',
              '- 门定义 = R16 冻结判据逐字（配置 gates.dev / 预登记 §2）；'
              'B1(m)/B3′ 沿 R16 原口径原数值（基准不换契约）',
              '',
              '| 配置 | K/路径/过滤 | 净CAGR | B1(m) | 超额 | 优势年 | 回撤 | '
              '换手max | 权重max | 成交率(引擎) | 门8映射执行率 | 过x/8 | 失败门 | 判定 |',
              '|---|---|---|---|---|---|---|---|---|---|---|---|---|---|']
    for cid in CONFIG_IDS:
        spec = config['configs'][cid]
        m, g, d = metrics_out[cid], gates_out[cid]['dev'], disclosures[cid]
        report.append(
            f"| {cid} | {spec['K']}/{spec['path']}/{spec['filter']} "
            f"| {m['net_cagr']*100:+.2f}% | {m['b1m_net_cagr']*100:+.2f}% "
            f"| {m['excess_vs_b1m']*100:+.2f}pp | {g['advantage_years']}/6 "
            f"| {m['max_drawdown']*100:.2f}% | {m['max_one_side_turnover']:.2f} "
            f"| {m['max_single_name_weight']*100:.1f}% "
            f"| {(d['order_fill_rate']['buy'] or 0)*100:.1f}/"
            f"{(d['order_fill_rate']['sell'] or 0)*100:.1f}% "
            f"| {d['gate8_mapped_execution_rate']*100:.1f}% "
            f"| {8 - len(g['failed_gates'])}/8 | {', '.join(g['failed_gates']) or '-'} "
            f"| {d['verdict']} |")
    report += ['', '## 强制披露（每配置）', '']
    for cid in CONFIG_IDS:
        d = disclosures[cid]
        k3 = d['k3_fallback']
        lag = d['fill_lag_buy']
        ue_share = d['unfilled_exit_share_buys']
        report += [
            f"### {cid}（判定 {d['verdict']}）",
            f"- 成交率：买单挂单日口径 {(d['fill_rate_order_day']['buy'] or 0)*100:.1f}%，"
            f"卖单 {(d['fill_rate_order_day']['sell'] or 0)*100:.1f}%；"
            f"订单口径 买 {(d['order_fill_rate']['buy'] or 0)*100:.1f}% / "
            f"卖 {(d['order_fill_rate']['sell'] or 0)*100:.1f}%",
            f"- 买入成交滞后：n={lag['n']}, min={lag['min']}, p50={lag['p50']}, "
            f"max={lag['max']}, mean={lag['mean'] and round(lag['mean'], 2)} 交易日",
            f"- K=3 兜底：scheduled={k3['scheduled']}, executed={k3['executed']}, "
            f"开盘跌停顺延={k3['deferred_limitdown_days']}, "
            f"损益贡献合计={k3['pnl_contribution_total']:.2f} CNY, "
            f"其中缺涨跌停数据日执行={d['k3_fallback_executed_missing_limit_info']}",
            f"- 未成交放弃（买单口径）={ue_share if ue_share is None else round(ue_share, 4)}；"
            f"零股卖出={d['odd_lot_exits']}；同bar顺延={d['same_bar_deferred_sells']}; "
            f"佣金报警={d['commission_warnings']}",
            '']
    report += ['## vs-R16 同配置差异', '',
               '| 配置 | 净CAGR band/R16 | 回撤 band/R16 | 换手 band/R16 | '
               '执行率 band/R16 |', '|---|---|---|---|---|']
    for cid in CONFIG_IDS:
        dv = disclosures[cid]['vs_r16_delta']
        report.append(
            f"| {cid} | {dv['net_cagr']['band']*100:+.2f}% / "
            f"{dv['net_cagr']['r16']*100:+.2f}% "
            f"| {dv['max_drawdown']['band']*100:.2f}% / "
            f"{dv['max_drawdown']['r16']*100:.2f}% "
            f"| {dv['max_one_side_turnover']['band']:.2f} / "
            f"{dv['max_one_side_turnover']['r16']:.2f} "
            f"| {dv['execution_rate']['band']*100:.1f}% / "
            f"{dv['execution_rate']['r16']*100:.1f}% |")
    report += ['',
               '## 映射决策（契约 v0 无部分调仓原语，登记如下）',
               '- 买入信号 = R16 leg_log 的 buy_open legs（入场席位；含上月',
               '  未成交席位按新锚重挂）；卖出信号 = sell_full legs（换期/跌出',
               '  缓冲带/资格丧失）；rescale legs（存量 drift 调仓）不映射——',
               '  敞口路径仅缩放入场目标名义，存量持有到成员退出为止',
               '  （vs R16：R16 每月向目标名義双向再平衡，差异计入 delta 表）',
               '- 全部信号 expiry = 下个信号日（换期重发；同名义覆盖）',
               '- 目标名义 = exposure(t) × 账户权益(t) / K（迭代到不动点，',
               '  迭代次数见 manifest；R16 用其自身 mark，机制同源）',
               '', '## 判定',
               f'- 0/8 或若干配置 pass；任何 full pass 即停在此，val 未消费' 
               if any_full_pass else
               '- **无配置通过全部八门**；val 2021–2024 未消费（一次性纪律）',
               '- 试验计账：189 → 197（本轮 8 配置）',
               '- 全部数字为历史回放，不构成盈利或实盘声称', '']
    (RUN_DIR / 'report.md').write_text('\n'.join(report), encoding='utf-8')

    # ---------------- 8. manifest -------------------------------------------
    ended = datetime.now(timezone.utc)
    stk_agg = batch_agg = None
    sys.path.insert(0, str(SRC))
    from quant.backtest.band_engine import batch_aggregate_sha256
    batch_agg = batch_aggregate_sha256(STK_DIR)
    manifest = {
        'run_id': RUN_DIR.name,
        'experiment_id': 'exp-20260918-p3r1-band-readjudication',
        'purpose': 'P3R1 eight-config dev readjudication under the approved '
                   'band-contract engine (SIGN-OFF '
                   'artifacts/runs/20260918T140610-p3r1-engine-fix-e850/SIGN-OFF.md)',
        'status': 'completed',
        'started_at': STARTED.isoformat(),
        'ended_at': ended.isoformat(),
        'command': [sys.executable, str(Path(__file__).relative_to(ROOT))],
        'trial_accounting': {'cumulative_before': 189, 'this_round': 8,
                             'cumulative_after': 197,
                             'note': 'prereg exp-20260918-p3r1 §0; engine '
                                     'acceptance consumed zero trials'},
        'window': {'dev': '2015-01-05..2020-12-31 (engine calendar clipped at '
                          'DEV_END; 2021+ zero access)',
                   'val': 'NOT consumed (one-shot discipline; requires '
                          'separate approval even if a config passes)',
                   'signals_dropped': [str(d) for d in dropped],
                   'signals_used': [str(d) for d in signal_days]},
        'authority_chain': {
            'pins': pins,
            'r8_mechanism_identity': mech,
            't200_behavioral_anchor': {'all_match': anchor['all_match']},
            'r16_authority_run': {'path': str(R16_RUN.relative_to(ROOT)),
                                  'config_file_sha256': r16_manifest.get('config_file_sha256'),
                                  'status': r16_manifest.get('status')},
            'stk_limit_batch_aggregate': batch_agg,
        },
        'signal_reconstruction': {
            'source': 'R16 leg_log.parquet REUSED as authoritative '
                      '(buy_open->buy, sell_full->sell, rescale->held); '
                      'independent recompute with the verbatim r16 module '
                      '(signal_pools + buffer_membership) compared on every '
                      '(config, signal)',
            'consistency': consistency,
            'verdict': 'PASS' if consistency['all_match'] else 'FAIL',
            're_pin_note': 'consistency is RECOMPUTED and re-pinned by every '
                           'run (deterministic); the failed predecessor run '
                           '20260918T143931-p3r1-dev-43b7 had already verified '
                           'the identical 8/8 PASS state (archived, untouched)',
            'exposure_paths': {'T200-40_fallback_signals': len(fallback),
                               'matches_r16': fb_match},
            'sizing': 'target_notional = exposure(t) x band-account equity(t) / K; '
                      'iterated to fixed point',
            'sizing_iterations': iterations,
        },
        'mapping_decisions': [
            'rescale legs (incumbent drift trimming) not mapped: band contract '
            'v0 has no partial-exit primitive; exposure scales entry sizing '
            'only; incumbents held until membership exit',
            'all signals expire at the next signal date (re-issued while the '
            'intent persists; replacement per contract)',
            'the 2020-12-31 signal dropped: execution would land in 2021 '
            '(val window zero-touch)',
            'priority = liquidity rank at the signal date (1 = highest); '
            'departed names without rank get 10**6',
            'sizing iterations disclose equity fixed-point convergence',
        ],
        'signoff_conditions': {
            'splits_pool_assertion': {
                'passed': True,
                'fed_rows': int(splits.height),
                'excluded_rows': int(splits_all.height - splits.height),
                'excluded_symbols_sample': orphan_splits[:5]},
            'stk_limit_missing_info_market_fallbacks': {
                cid: disclosures[cid]['k3_fallback_executed_missing_limit_info']
                for cid in CONFIG_IDS},
        },
        'inputs': {
            'daily_parquet': pins['daily_parquet'],
            'stk_limit_batch': {'path': str(STK_DIR.relative_to(ROOT)),
                                'aggregate': batch_agg},
            'split_factor_h5': pins['split_factor_h5'],
            'dividends_h5': pins['dividends_h5'],
            'ex_cum_factor': 'REMOVED_FROM_ACCOUNT_INPUTS (F1)',
            'r16_reused_artifacts': {
                'leg_log': str((R16_RUN / 'leg_log.parquet').relative_to(ROOT)),
                'membership_events': str((R16_RUN / 'membership_events.parquet').relative_to(ROOT)),
                'metrics_json': str((R16_RUN / 'metrics.json').relative_to(ROOT))},
            'index_chunk_000300': pins['index_chunk_000300'],
        },
        'engine': {
            'path': 'src/quant/backtest/band_engine.py',
            'sha256': sha256_file(SRC / 'quant' / 'backtest' / 'band_engine.py'),
            'modified_by_this_run': False,
            'approval': 'SIGN-OFF APPROVE 20260918T140610-p3r1-engine-fix-e850',
            'finding_for_referee':
                'load_stk_limit_batch returns raw tushare names '
                '(up_limit/down_limit) while run_band_backtest validates '
                'limit_up/limit_down; bridged by a caller-side rename in this '
                'runner (engine byte-untouched). Naming inconsistency only; '
                'recommend aligning the loader in a future tooling pass',
        },
        'engine_fix_ENGINE_1': {
            'authorized_by': 'orchestrator ruling 2026-09-18 14:56 (prereg §7)',
            'scope': 'band_engine._frame ONLY: construct with the caller-'
                     'passed declared schema instead of first-100-row type '
                     'inference; semantics null (same values, typed per the '
                     "module's own constants)",
            'sha256_before': '0582949193ad229f' + ' (approved engine-fix-e850 bytes)',
            'sha256_after': sha256_file(SRC / 'quant' / 'backtest' / 'band_engine.py'),
            'diff': {
                'removed': 'return pl.DataFrame(rows).select(list(schema)).cast(schema)',
                'added': ['ENGINE-1 comment lines (authorized-fix provenance),',
                          'return pl.DataFrame(rows, schema=schema)'],
            },
            'tests': {'passed': tests_passed, 'failed': 0,
                      'note': '13 pre-existing tests UNCHANGED (expectations '
                              'untouched) + new test_14_frame_schema_regression '
                              '(>100-row logs, None-first columns, declared '
                              'dtypes)'},
        },
        'environment': {
            'python': sys.version, 'platform': platform.platform(),
            'packages': {p: __import__('importlib.metadata', fromlist=['version']).version(p)
                         for p in ['polars', 'numpy', 'pandas', 'pyarrow']},
            'peak_rss_gb': round(rss_gb(), 2),
            'elapsed_seconds': round(time.perf_counter() - t0, 1),
            'budget': {'max_runtime_s': BUDGET_S, 'max_ram_gb': 8},
        },
        'outputs': {},
    }
    (RUN_DIR / 'logs' / 'runner.log').write_text('\n'.join(LOG) + '\n', encoding='utf-8')
    manifest['outputs'] = {
        str(p.relative_to(RUN_DIR)).replace('\\', '/'): sha256_file(p)
        for p in sorted(RUN_DIR.rglob('*'))
        if p.is_file() and p.name != 'manifest.json'}
    write_json(RUN_DIR / 'manifest.json', manifest)
    log(f'== manifest written: {RUN_DIR / "manifest.json"} ==')
    log(f'== elapsed {time.perf_counter() - t0:.0f}s, peak RSS {rss_gb():.1f} GB ==')
    return 0


if __name__ == '__main__':
    sys.exit(main())
