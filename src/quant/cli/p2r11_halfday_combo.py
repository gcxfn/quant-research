"""P2-R11 half-day candidate combination CLI (exp-20260918-p2r11-halfday-combo).

Preregistered by ``docs/research/exp-20260918-p2r11-halfday-combo-prereg.md``
with frozen config ``configs/experiments/p2r11-halfday-combo.json``
(06:35 freeze, read-only input; never modified).

Usage:
  PYTHONPATH=D:/量化/src .venv/Scripts/python.exe -X utf8 \
      src/quant/cli/p2r11_halfday_combo.py [--smoke]

Fail-closed preflight (before any computation): dataset sha256 chain from
the config authority_chain, the R10 config sha256 lock, R10 run-metrics
factor directions, market circuit-breaker day assertion, freeze boundary.

``--smoke`` runs the identical pipeline on 2015-01-05..2015-03-31 for
correctness and timing only (labelled SMOKE, not authoritative).
Full run: continuous 2015-01-05..2024-12-31 simulation for 12 configs +
B1 + B3' (seeds 17-36); dev gates for all 12; the priority-first dev
passer - and only it - is consumed on validation; test only if validation
passes.  Equity/trade evidence files are truncated at the furthest
consumed window.  Trial accounting: cumulative 151 + 12 = 163.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from datetime import date
from pathlib import Path

import numpy as np
import polars as pl

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'src'))

from quant.research.p2r11_halfday_combo import (  # noqa: E402
    B3_SEEDS,
    CAPITAL,
    CONFIGS,
    DEV_WINDOW,
    P2R10_MODULE_SHA256_AFTER_M1_FIX,
    PRIORITY,
    TEST_WINDOW,
    VAL_WINDOW,
    b1_daily_marks,
    b1_equity_series,
    build_execution_table,
    build_pool,
    evaluate_dev_gates,
    evaluate_window_gates,
    mark_breaker_days,
    market_arrays_with_score,
    pool_mask,
    prepare_market,
    random_score_array,
    run_portfolio,
    score_array,
    window_metrics,
)
from quant.research.runs import Run, find_repo_root, sha256  # noqa: E402

HALFDAY_PARQUET = ROOT / 'data/processed/halfday-1130-20260918/halfday_1130.parquet'
DAILY_2015 = ROOT / 'data/processed/baostock-daily-20260917/daily_2015_2024.parquet'
DAILY_1999 = ROOT / 'data/processed/baostock-daily-20260917/daily_1999_2024.parquet'
BAOSTOCK_MANIFEST = ROOT / 'data/processed/baostock-daily-20260917/manifest.json'
R10_CONFIG = ROOT / 'configs/experiments/p2r10-halfday-survey.json'
R11_CONFIG = ROOT / 'configs/experiments/p2r11-halfday-combo.json'
R10_RUN_MANIFEST = ROOT / ('artifacts/runs/20260918T051252-p2r10-halfday-'
                           'survey-54a3d885/manifest.json')
R10_RUN_METRICS = ROOT / ('artifacts/runs/20260918T051252-p2r10-halfday-'
                          'survey-54a3d885/metrics.json')
R10_REVIEW_RUN = '20260918T054627-p2r10-review-c7d9x2'
SMOKE_END = date(2015, 3, 31)
BREAKER_EXPECTED = [date(2016, 1, 7)]
FREEZE_LINE = date(2025, 1, 1)

DEVIANCES = [
    {'id': 'D1', 'text': 'M-1 fix applied to src/quant/research/p2r10_halfday.py '
     '(F08 line 217-220 and load_daily_vol20): shift(1) moved INSIDE '
     ".over('symbol'); no other logic touched. Fixed module sha256 "
     + P2R10_MODULE_SHA256_AFTER_M1_FIX + '. Review run ' + R10_REVIEW_RUN
     + ' quantified: ghost rows 3,780/4,279,962 = 0.088% (F08 dev panel), '
     'F03/F07 affected rows exactly zero (ghost lands on each symbol first '
     'baostock row, excluded by the listing gate), fixed-vs-buggy F08 dev '
     'IC +0.01316/+5.47 vs +0.01314/+5.47, IC gate FAIL unchanged -> R11 '
     'factor values unaffected by the fix; two regression unit tests added '
     '(later-symbol first row null).', 'kind': 'mandated_fix'},
    {'id': 'D2', 'text': 'Listing gate and 20-day median amount gate read the '
     'daily_2015_2024 file per the frozen config role table. Seasoning rule: '
     'symbols whose first in-file traded date equals the file first date '
     '(2015-01-05) are treated as pre-2015 listings (120-session rule not '
     'applicable, per prereg section 1); edge: a stock suspended across '
     '2015-01-05 resuming later is conservatively treated as new.',
     'kind': 'implementation_note'},
    {'id': 'D3', 'text': 'The 20-session median amount gate uses in-file '
     'history: every symbol (including pre-2015 listings) is excluded until '
     '20 traded sessions accumulate in the 2015-2024 file, so the dev pool '
     'ramps up over roughly the first four weeks of 2015. Benchmarks share '
     'the same pool, so comparisons stay internally consistent.',
     'kind': 'implementation_note'},
    {'id': 'D4', 'text': 'F07/daily_vol20 (factor input for F03/F11) follows '
     'the R10 lineage: daily_1999_2024.parquet (hash d9a63f4c..., verified '
     'against the R10 run manifest) with the M-1-fixed loader; using the '
     '2015 file here would change frozen factor values in Jan 2015.',
     'kind': 'implementation_note'},
    {'id': 'D5', 'text': 'Winsorize quantiles use linear interpolation; '
     'constant cross-sections (std 0/null, e.g. F09 on stk_limit zero-row '
     'days) map to z=0 (neutral contribution) instead of null - otherwise '
     'the whole market would be untradeable those days.', 'kind':
     'implementation_note'},
    {'id': 'D6', 'text': 'Buy rule when limit_up is null (18,402 active rows '
     'on 6 days: 2017-03-07/08/09, 2019-07-22 (1 row), 2022-07-26, '
     '2023-04-21): conservatively blocked (replacement consumed). Sell rule '
     'when limit_down is null: executed if a valid price exists (blocking '
     'sells on missing data would create phantom holdings).', 'kind':
     'implementation_note'},
    {'id': 'D7', 'text': 'Circuit-breaker detection is data-derived: a day '
     'where EVERY active stock is flat across close_1100/close_1130/'
     'open_1300 (vendor placeholders; share==1.0 isolates 2016-01-07, next '
     'highest 0.83). On such days only the 09:25 auction point is valid; '
     '11:30/13:01/close points postpone sells (each counted as execution '
     'failure) and buys are skipped without attempts.', 'kind':
     'implementation_note'},
    {'id': 'D8', 'text': 'Held share counts adjust at the day boundary by '
     'close(prev traded day)/preclose(today) (M-1-safe shift-inside-over), '
     'a reinvested-dividend approximation; 99.68% of consecutive symbol-day '
     'pairs have preclose == previous close (0.31% true ex-days), consistent '
     'with review run ' + R10_REVIEW_RUN + '. No-event-day exactness is '
     'asserted in tests/preflight.', 'kind': 'implementation_note'},
    {'id': 'D9', 'text': 'B1 applies fees proportionally (no 5-yuan commission '
     'minimum: meaningless at whole-pool scale). B1 marks at the sell-day '
     '11:30; the strategy marks at the official close - an inherent timing '
     'difference of the benchmark definition.', 'kind': 'implementation_note'},
    {'id': 'D10', 'text': 'Fill rate counts every attempted plan (buy '
     'candidates actually considered incl. replacements; sell schedule '
     'attempts incl. each postponed retry); positions still open at data '
     'end count one failed plan each (test window only).', 'kind':
     'implementation_note'},
    {'id': 'D11', 'text': 'daily_2015_2024.parquet sha256 '
     '1cbb09a11f7c10136981749c13467f12a1757b59e7e95fb6f86666f96edfc1de '
     'observed at preflight and recorded here (the frozen config locks this '
     'dataset via its manifest sha256; no external per-file record exists).',
     'kind': 'implementation_note'},
]


def _fail(msg: str) -> None:
    print(f'PREFLIGHT FAIL: {msg}', file=sys.stderr)
    raise SystemExit(2)


def preflight(config: dict) -> dict:
    """Fail-closed identity checks; returns the recorded identity dict."""
    ac = config['authority_chain']
    if config.get('status') != 'frozen':
        _fail('config status is not frozen')
    half_sha = sha256(HALFDAY_PARQUET)
    if half_sha != ac['datasets'][0]['sha256']:
        _fail(f'halfday sha256 {half_sha} != locked {ac["datasets"][0]["sha256"]}')
    man_sha = sha256(BAOSTOCK_MANIFEST)
    if man_sha != ac['datasets'][1]['manifest_sha256']:
        _fail(f'baostock manifest sha256 {man_sha} != locked')
    d15_sha = sha256(DAILY_2015)
    d99_sha = sha256(DAILY_1999)
    r10_manifest = json.loads(R10_RUN_MANIFEST.read_text(encoding='utf-8'))
    r10_locked_99 = r10_manifest['dataset']['baostock_daily_1999_2024']['sha256']
    if d99_sha != r10_locked_99:
        _fail(f'daily_1999 sha256 {d99_sha} != R10 recorded {r10_locked_99}')
    r10_cfg_sha = sha256(R10_CONFIG)
    if r10_cfg_sha != ac['p2r10_config_sha256']:
        _fail(f'R10 config sha256 {r10_cfg_sha} != locked '
              f'{ac["p2r10_config_sha256"]}')
    r10_metrics = json.loads(R10_RUN_METRICS.read_text(encoding='utf-8'))
    dirs = {f: r10_metrics['factor_results'][f]['direction']
            for f in ('F03', 'F06', 'F09', 'F11')}
    from quant.research.p2r11_halfday_combo import FROZEN_DIRECTIONS
    if dirs != FROZEN_DIRECTIONS:
        _fail(f'R10 directions {dirs} != frozen {FROZEN_DIRECTIONS}')
    candidates = r10_metrics.get('candidates')
    if sorted(candidates or []) != ['F03', 'F06', 'F09', 'F11']:
        _fail(f'R10 candidates {candidates} != the four frozen candidates')
    fixed_sha = sha256(ROOT / 'src/quant/research/p2r10_halfday.py')
    if fixed_sha != P2R10_MODULE_SHA256_AFTER_M1_FIX:
        _fail(f'p2r10_halfday.py sha256 {fixed_sha} != post-M-1-fix hash')
    breaker = mark_breaker_days(HALFDAY_PARQUET)
    if breaker != BREAKER_EXPECTED:
        _fail(f'breaker days {breaker} != expected {BREAKER_EXPECTED}')
    hd_max = pl.scan_parquet(HALFDAY_PARQUET).select(
        pl.col('date').max()).collect().item()
    d_max = pl.scan_parquet(DAILY_2015).select(
        pl.col('date').max()).collect().item()
    d_min = pl.scan_parquet(DAILY_2015).select(
        pl.col('date').min()).collect().item()
    if hd_max >= FREEZE_LINE or d_max >= FREEZE_LINE:
        _fail(f'freeze boundary violated: halfday max {hd_max}, daily max {d_max}')
    if d_min != DEV_WINDOW[0]:
        _fail(f'daily file starts {d_min}, expected {DEV_WINDOW[0]}')
    return {
        'halfday_sha256': half_sha, 'baostock_manifest_sha256': man_sha,
        'daily_2015_sha256': d15_sha, 'daily_1999_sha256': d99_sha,
        'r10_config_sha256': r10_cfg_sha,
        'p2r10_module_sha256_post_m1_fix': fixed_sha,
        'r10_factor_directions': dirs, 'r10_candidates': candidates,
        'breaker_days': [str(d) for d in breaker],
        'halfday_max_date': str(hd_max), 'daily_max_date': str(d_max),
        'r10_review_run': R10_REVIEW_RUN,
    }


def check_budget(start_ts: float, limit_s: float, phase: str) -> None:
    elapsed = time.perf_counter() - start_ts
    if elapsed > limit_s:
        raise TimeoutError(f'budget exceeded ({elapsed:.0f}s > '
                           f'{limit_s:.0f}s) at {phase}')


def assert_run_invariants(res, dates: list[date], label: str) -> None:
    if not np.isfinite(res.equity).all() or (res.equity <= 0).any():
        raise AssertionError(f'{label}: equity not strictly positive/finite')
    if res.cash_final < -1e-9:
        raise AssertionError(f'{label}: negative cash {res.cash_final}')
    if abs(res.equity[-1] - (res.cash_final + res.open_value)) > 1e-6:
        raise AssertionError(f'{label}: equity != cash + open marks')
    bought = sold = 0.0
    for t in res.trades:
        if t['sell_day'] is not None and t['sell_day'] <= t['buy_day']:
            raise AssertionError(f'{label}: T+1 violated in {t}')
        if t['buy_shares'] % 100 != 0:
            raise AssertionError(f'{label}: lot violation in {t}')
        bought += t['buy_shares'] * t['buy_price'] + t['buy_fee']
        if t['sell_day'] is not None:
            sold += t['shares'] * t['sell_price'] - t['sell_fee']
    ledger = CAPITAL - bought + sold
    if abs(ledger - res.cash_final) > 1e-6:
        raise AssertionError(f'{label}: cash ledger mismatch {ledger} vs '
                             f'{res.cash_final}')
    if res.max_weight.max() > 1.0 + 1e-12:
        raise AssertionError(f'{label}: weight > 1')


def sanitize(obj):
    """Make metrics JSON-safe (no NaN/Inf: write_json forbids them)."""
    if isinstance(obj, dict):
        return {k: sanitize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [sanitize(v) for v in obj]
    if isinstance(obj, float) and not math.isfinite(obj):
        return None
    if isinstance(obj, (np.floating, np.integer)):
        return sanitize(obj.item())
    if isinstance(obj, date):
        return str(obj)
    return obj


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=Path, default=R11_CONFIG)
    parser.add_argument('--smoke', action='store_true')
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding='utf-8'))
    mode = {'mode': 'smoke_3m_2015Q1'} if args.smoke else {}
    run_config = {**config, **mode}

    import os
    os.chdir(ROOT)
    root = find_repo_root()
    t_start = time.perf_counter()
    limit_s = float(config['limits']['max_runtime_s'])

    identity = preflight(config)
    print('PREFLIGHT OK: hash chain + directions + breaker + freeze '
          'boundary all verified')
    breaker_dates = [date.fromisoformat(x) for x in identity['breaker_days']]

    with Run(root, 'p2r11-halfday-combo', run_config) as run:
        run.manifest['config_name'] = config['name']
        run.manifest['prereg'] = config['prereg']
        run.manifest['preregistered_at'] = config['preregistered_at']
        run.manifest['config_frozen_at'] = config['frozen_at']
        run.manifest['mode'] = 'smoke' if args.smoke else 'full'
        run.manifest['identity'] = identity
        run.manifest['authority_chain'] = config['authority_chain']
        run.manifest['trial_count'] = {
            'prior_cumulative': config['trials_cumulative_before'],
            'this_round_configs': len(CONFIGS),
            'cumulative_after': config['trials_cumulative_after']}
        run.manifest['m1_fix'] = {
            'review_run': R10_REVIEW_RUN,
            'fixed_module_sha256': identity['p2r10_module_sha256_post_m1_fix'],
            'ghost_rows': '3,780/4,279,962 = 0.088% (F08 dev panel)',
            'f03_f07_affected_rows': 0,
            'f08_dev_ic_fixed_vs_buggy': '+0.01316/+5.47 vs +0.01314/+5.47'}
        run.manifest['window_declarations'] = {
            'dev': '2015-01-05..2020-12-31 (5th reuse; same-window '
                   'new-information-set per R10 disclosure)',
            'validation': '2021-01-01..2022-12-31 (2nd consumption of this '
                          'window; consumed only by the priority-first dev '
                          'passer)',
            'test': '2023-01-01..2024-12-31 (first consumption; only if '
                    'validation passes; one-way)',
            'freeze': 'no rows on/after 2025-01-01 enter any path '
                      '(preflight asserted)'}
        run.manifest['semantics'] = {
            'signal': 'T 11:30 cross-section', 'buy': 'T 13:01 open_1300',
            'sells': config['execution']['sell_schedules'],
            'bridge': config['execution']['corporate_action_bridge'],
            'directions': 'R10 dev-IC signs (all -1): high composite = buy '
                          'side', 'sessions_per_year': 244}
        run.manifest['deviations'] = DEVIANCES

        # ---------------- panel + market ----------------
        t0 = time.perf_counter()
        pool, waterfall = build_pool(HALFDAY_PARQUET, DAILY_2015, DAILY_1999,
                                     smoke=args.smoke)
        exec_tab = build_execution_table(HALFDAY_PARQUET, DAILY_2015)
        if args.smoke:
            exec_tab = exec_tab.filter(pl.col('date') <= SMOKE_END)
        static = prepare_market(exec_tab, breaker_dates)
        is_pool = pool_mask(static, pool)
        t_build = time.perf_counter() - t0
        waterfall['exec_rows'] = exec_tab.height
        waterfall['exec_symbols'] = exec_tab['symbol'].n_unique()
        run.metrics['filter_waterfall'] = waterfall
        run.metrics['timings'] = {'build_s': t_build}
        run.metrics['pool_rows_in_exec'] = int(is_pool.sum())
        check_budget(t_start, limit_s, 'panel build')
        print(f'pool rows {waterfall["pool_rows"]}, exec rows '
              f'{exec_tab.height}, build {t_build:.0f}s')

        # ---------------- B1 ----------------
        marks = b1_daily_marks(pool, exec_tab, breaker_dates)
        b1_eq = b1_equity_series(marks, static['dates'])
        b1_maxw = np.zeros(len(static['dates']))
        b1_buynot = np.zeros(len(static['dates']))
        b1_m = window_metrics(static['dates'], b1_eq, b1_maxw, b1_buynot,
                              [], [], date(2015, 1, 1), date(2024, 12, 31))

        # ---------------- 12 config runs ----------------
        results: dict[str, dict] = {}
        runs_store: dict[str, object] = {}
        t0 = time.perf_counter()
        for cname, cdef in CONFIGS.items():
            sc = score_array(static, pool, cdef['composite'])
            mkt = market_arrays_with_score(static, sc)
            res = run_portfolio(mkt, cdef['K'], cdef['sell'])
            assert_run_invariants(res, static['dates'], cname)
            runs_store[cname] = res
            del mkt, sc
        t_sims = time.perf_counter() - t0
        run.metrics['timings']['config_sims_s'] = t_sims
        check_budget(t_start, limit_s, 'config sims')

        # ---------------- B3' ----------------
        t0 = time.perf_counter()
        b3_store: dict[str, object] = {}
        for seed in B3_SEEDS:
            sc = random_score_array(static, is_pool, seed)
            mkt = market_arrays_with_score(static, sc)
            res = run_portfolio(mkt, 3, 'S_1130')
            assert_run_invariants(res, static['dates'], f'B3prime_s{seed}')
            b3_store[seed] = res
            del mkt, sc
        t_b3 = time.perf_counter() - t0
        run.metrics['timings']['b3_sims_s'] = t_b3
        check_budget(t_start, limit_s, 'B3 sims')

        # ---------------- windows & gates (procedural consumption) ----
        def wmetrics(res, lo, hi):
            return window_metrics(static['dates'], res.equity, res.max_weight,
                                  res.buy_notional, res.trades, res.attempts,
                                  lo, hi)

        b3_dev = [wmetrics(b3_store[s], *DEV_WINDOW)['net_cagr']
                  for s in B3_SEEDS]
        b3_dev_mean = float(np.mean(b3_dev))
        b1_dev = window_metrics(static['dates'], b1_eq, b1_maxw, b1_buynot,
                                [], [], *DEV_WINDOW)

        dev_block: dict[str, dict] = {}
        for cname in CONFIGS:
            m = wmetrics(runs_store[cname], *DEV_WINDOW)
            g = evaluate_dev_gates(m, b1_dev, b3_dev_mean)
            dev_block[cname] = {'metrics': m, 'gates': g}
        passers = [c for c in PRIORITY if dev_block[c]['gates']['all_pass']]
        run.metrics['dev'] = dev_block
        run.metrics['b1_dev'] = b1_dev
        run.metrics['b3prime_dev'] = {'mean_net_cagr': b3_dev_mean,
                                      'per_seed_net_cagr': b3_dev,
                                      'seeds': list(B3_SEEDS)}
        run.metrics['dev_passers_in_priority_order'] = passers

        val_block = None
        test_block = None
        cutoff = SMOKE_END if args.smoke else DEV_WINDOW[1]
        if passers and not args.smoke:
            sel = passers[0]          # priority-first only
            b1_val = window_metrics(static['dates'], b1_eq, b1_maxw,
                                    b1_buynot, [], [], *VAL_WINDOW)
            m_val = wmetrics(runs_store[sel], *VAL_WINDOW)
            val_block = {'config': sel, 'metrics': m_val,
                         'gates': evaluate_window_gates(m_val, b1_val),
                         'b1': b1_val}
            cutoff = VAL_WINDOW[1]
            if val_block['gates']['all_pass']:
                b1_test = window_metrics(static['dates'], b1_eq, b1_maxw,
                                         b1_buynot, [], [], *TEST_WINDOW)
                m_test = wmetrics(runs_store[sel], *TEST_WINDOW)
                decay = {
                    'dev_excess_vs_b1': dev_block[sel]['gates']['cells'][2]
                    ['value'],
                    'val_excess_vs_b1': val_block['gates']['cells'][1]
                    ['value'],
                    'test_excess_vs_b1': m_test['net_cagr'] - b1_test[
                        'net_cagr'],
                    'dev_cagr': dev_block[sel]['metrics']['net_cagr'],
                    'val_cagr': m_val['net_cagr'],
                    'test_cagr': m_test['net_cagr']}
                test_block = {'config': sel, 'metrics': m_test,
                              'gates': evaluate_window_gates(m_test,
                                                             b1_test),
                              'b1': b1_test, 'decay_disclosure': decay}
                cutoff = TEST_WINDOW[1]
        run.metrics['validation'] = sanitize(val_block)
        run.metrics['test'] = sanitize(test_block)
        run.metrics['evidence_cutoff_date'] = str(cutoff)

        # ---------------- execution quality ----------------
        execq: dict[str, dict] = {}
        for cname, res in runs_store.items():
            buys = [a for a in res.attempts if a['kind'] == 'buy']
            sells = [a for a in res.attempts if a['kind'] == 'sell']
            execq[cname] = {
                'buy_attempts': len(buys),
                'buy_failed': sum(1 for a in buys if not a['success']),
                'sell_attempts': len(sells),
                'sell_blocked': sum(1 for a in sells if not a['success']),
                'open_at_end': res.open_positions}
        run.metrics['execution_quality'] = execq

        # ---------------- evidence files (truncated at cutoff) --------
        t0 = time.perf_counter()
        trade_schema = {
            'buy_day': pl.Int64, 'sell_day': pl.Int64, 'sym': pl.Int64,
            'shares': pl.Float64, 'buy_shares': pl.Float64,
            'buy_price': pl.Float64, 'buy_fee': pl.Float64,
            'sell_price': pl.Float64, 'sell_fee': pl.Float64}
        eq_frames = []
        for cname, res in runs_store.items():
            eq_frames.append(pl.DataFrame({
                'label': cname,
                'date': static['dates'],
                'equity': res.equity,
                'max_weight': res.max_weight}))
        for seed in B3_SEEDS:
            res = b3_store[seed]
            eq_frames.append(pl.DataFrame({
                'label': f'B3prime_s{seed}',
                'date': static['dates'],
                'equity': res.equity,
                'max_weight': res.max_weight}))
        eq_frames.append(pl.DataFrame({
            'label': 'B1', 'date': static['dates'],
            'equity': b1_eq, 'max_weight': b1_maxw}))
        equity_long = pl.concat(eq_frames).filter(
            pl.col('date') <= cutoff)
        equity_long.write_parquet(run.path / 'equity_daily.parquet')

        tr_frames = []
        for cname, res in runs_store.items():
            tr_frames.append(pl.DataFrame(res.trades, schema=trade_schema)
                             .with_columns(pl.lit(cname).alias('label')))
        for seed in B3_SEEDS:
            tr_frames.append(
                pl.DataFrame(b3_store[seed].trades, schema=trade_schema)
                .with_columns(pl.lit(f'B3prime_s{seed}').alias('label')))
        day_to_date = {i: d for i, d in enumerate(static['dates'])}
        trades_long = pl.concat(tr_frames).with_columns(
            pl.col('buy_day').replace_strict(
                list(day_to_date.keys()), list(day_to_date.values()),
                return_dtype=pl.Date).alias('buy_date'),
            pl.when(pl.col('sell_day').is_not_null())
            .then(pl.col('sell_day').replace_strict(
                list(day_to_date.keys()), list(day_to_date.values()),
                return_dtype=pl.Date))
            .otherwise(None).alias('sell_date'))
        trades_long = trades_long.drop('buy_day', 'sell_day').filter(
            pl.col('sell_date').is_null() | (pl.col('sell_date') <= cutoff))
        trades_long.write_parquet(run.path / 'trades.parquet')
        run.metrics['timings']['evidence_write_s'] = time.perf_counter() - t0

        run.metrics['timings']['total_s'] = time.perf_counter() - t_start
        run.metrics['deviances'] = DEVIANCES
        run.metrics = sanitize(run.metrics)

        (run.path / 'report.md').write_text(
            render_report(run.metrics, run.manifest, args.smoke),
            encoding='utf-8')
        verdict = (f'dev passers={passers}; '
                   + (f'val={"PASS" if val_block["gates"]["all_pass"] else "FAIL"}'
                      if val_block else 'val=not-consumed')
                   + (f'; test={"PASS" if test_block["gates"]["all_pass"] else "FAIL"}'
                      if test_block else ''))
        print(f'RUN DONE: {verdict}; run={run.path}')
    return 0


def render_report(metrics: dict, manifest: dict, smoke: bool) -> str:
    def fmt(v, spec='.4f'):
        return '-' if v is None else format(v, spec)

    lines = [
        f"# P2-R11 half-day combination (mode={manifest.get('mode')}"
        f"{' - SMOKE, not authoritative' if smoke else ''})", '',
        f"- dev passers (priority order): "
        f"{metrics['dev_passers_in_priority_order'] or 'none'}",
        f"- B1 dev: {json.dumps(metrics['b1_dev'], default=str)[:400]}",
        f"- B3' dev mean CAGR: "
        f"{metrics['b3prime_dev']['mean_net_cagr']}",
        '', '## dev gates (12 configs x 8 cells)', '',
        '| cfg | CAGR | g1 | excess | g2 | advY | g3 | maxDD | g4 '
        '| turn | g5 | maxW | g6 | vsB3 | g7 | fill | g8 | all |',
        '|---|---|---|---|---|---|---|---|---|---|---|---|---|---|'
        '---|---|---|---|',
    ]
    for cname in CONFIGS:
        b = metrics['dev'][cname]
        m, g = b['metrics'], b['gates']['cells']
        lines.append(
            f"| {cname} | {fmt(m['net_cagr'])} | {g[1]['pass']} "
            f"| {fmt(g[2]['value'])} | {g[2]['pass']} | {g[3]['value']} "
            f"| {g[3]['pass']} | {fmt(m['max_dd'])} | {g[4]['pass']} "
            f"| {fmt(m['turnover_annual'], '.1f')} | {g[5]['pass']} "
            f"| {fmt(m['max_weight'], '.3f')} | {g[6]['pass']} "
            f"| {fmt(g[7]['value'])} | {g[7]['pass']} "
            f"| {fmt(m['fill_rate'])} | {g[8]['pass']} "
            f"| {b['gates']['all_pass']} |")
    lines += ['', f"- cutoff: {metrics['evidence_cutoff_date']}",
              f"- timings: {json.dumps(metrics['timings'])}",
              f"- deviations: {len(metrics['deviances'])} recorded "
              '(see metrics.json / results doc)']
    if metrics.get('validation'):
        v = metrics['validation']
        lines += ['', f"## validation ({v['config']})",
                  f"- metrics: {json.dumps(v['metrics'], default=str)[:400]}",
                  f"- gates: {json.dumps(v['gates']['cells'], default=str)}"]
    if metrics.get('test'):
        t = metrics['test']
        lines += ['', f"## test ({t['config']}) - one-way",
                  f"- metrics: {json.dumps(t['metrics'], default=str)[:400]}",
                  f"- gates: {json.dumps(t['gates']['cells'], default=str)}",
                  f"- decay: {json.dumps(t['decay_disclosure'])}"]
    return '\n'.join(lines) + '\n'


if __name__ == '__main__':
    raise SystemExit(main())
