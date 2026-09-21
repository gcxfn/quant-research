"""P2-R13 low-frequency monthly cross-sectional survey CLI.

Preregistered by ``docs/research/exp-20260918-p2r13-lowfreq-survey-prereg.md``
with frozen config ``configs/experiments/p2r13-lowfreq-survey.json`` (read-only).

Usage:
  PYTHONPATH=D:/量化/src .venv/Scripts/python.exe -X utf8 \
      src/quant/cli/p2r13_lowfreq_survey.py [--probe | --smoke]

``--probe``  C3 hk_hold 2017-18 completeness probe only (runs first per prereg).
``--smoke``  identical pipeline on the first 6 signal months of 2015
             (correctness + timing; numbers labelled SMOKE, not authoritative).
Default:     full window.  Dev 2015-2020 gates; val 2021-2024 evaluated ONLY
when >= 2 true factors pass all dev gates (one-shot val discipline).
Trial accounting: cumulative 169 + 6 = 175.  Budget 1200 s / 8 GB.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from contextlib import contextmanager
from datetime import date
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'src'))

from quant.research import p2r13_lowfreq as lf  # noqa: E402
from quant.research.runs import Run, find_repo_root, sha256  # noqa: E402

DAILY_1999 = ROOT / 'data/processed/baostock-daily-20260917/daily_1999_2024.parquet'
DAILY_2015 = ROOT / 'data/processed/baostock-daily-20260917/daily_2015_2024.parquet'
PROCESSED_MANIFEST = 'data/processed/baostock-daily-20260917/manifest.json'
EXPECTED_MANIFEST_SHA = ('2b89bef9ef6f4ae58b69ca43021552db067'
                         'b185551c92a05ef6ac71d2be59bd3')
BUDGET_S = 1200.0
RAW_DIRS_VERIFIED = [
    'xiaodefa/hk_hold/20260913-bulk1',
    'xiaodefa/block_trade/20260913-bulk1',
    'tushare/income/20260909-r3',
    'tushare/cashflow/20260909-r3',
    'tushare/balancesheet/20260909-r3',
    'tushare/daily_basic/20260909-r1',
    'tushare/daily_basic/20260913-r2',
    'xiaodefa/stock_basic/20260913-bulk1',
]
HEADER_CHECK_DIRS = [
    ('xiaodefa/hk_hold/20260913-bulk1', 'chunk_*.csv'),
    ('xiaodefa/block_trade/20260913-bulk1', 'chunk_*.csv'),
    ('tushare/income/20260909-r3', 'chunk_*.csv'),
    ('tushare/cashflow/20260909-r3', 'chunk_*.csv'),
    ('tushare/balancesheet/20260909-r3', 'chunk_*.csv'),
    ('xiaodefa/stock_basic/20260913-bulk1', 'chunk_*.csv'),
]

DEVIATIONS = {
    'warmup_file': 'history warmup (listing_index since 1999, 250-session '
                   'rolling high, 60-session overnight sums) reads '
                   'daily_1999_2024.parquet - same processed dataset and '
                   'manifest identity as the pinned daily_2015_2024.parquet, '
                   'which cannot produce C2 for the 2015 signals required by '
                   'the frozen coverage.  The 2015+ slice of the 1999 file is '
                   'asserted row-count-identical to the pinned file.  R10 '
                   'precedent: same superset file for history factors.',
    'own_session_windows': 'history windows (C1 60d, C2 250d, C6 20d, '
                           'liquidity median 20d, listing age) use the '
                           "symbol's OWN traded sessions (suspensions do not "
                           'advance windows), consistent with R10.',
    'hk_hold_t_plus_1': 'northbound holdings of trade date T are treated as '
                        'usable from T+1 (month-end signal s uses trade '
                        'dates s-1 and s-21 only); conservative reading of '
                        'the prereg PIT requirement.',
    'industry_snapshot': 'financial-industry exclusion uses xiaodefa '
                         'stock_basic (East Money industry, 2026-09-13 '
                         'snapshot; fixed set {bank, insurance, securities, '
                         'diversified financials}) - non-PIT approximation, '
                         'disclosed; applied to C4 cross-sections only.',
    'forward_execution': 'entry requires the symbol to trade on the session '
                         'right after the signal (mkt_idx == s+1); exit at '
                         'the first own session with mkt_idx >= s+21 '
                         '(suspension delays exit).  No limit-up/open-block '
                         'modeling in this survey (factor-candidate round; '
                         'any combination round must model execution).',
    'signal_month_2024_12': 'the 2024-12-31 month-end signal is dropped: its '
                            'T+21 open would land after the 2024-12-31 data '
                            'end (2025+ zero-touch); last judged month is '
                            '2024-11.',
    'c4_income_measure': 'accrual numerator uses n_income (net profit incl. '
                         'minority) against total_assets (incl. minority '
                         'interest) - consistent scope; rows filtered to '
                         'report_type=1 (consolidated), end_date=1231, max '
                         'update_flag per (ts_code, end_date).',
    'val_discipline': 'val 2021-2024 statistics are computed ONLY when >= 2 '
                      'true factors pass all dev gates; otherwise the val '
                      'window is not consumed this round (recorded as '
                      '"not_consumed").',
    'c3_month_drop_rule': 'the prereg ">10% missing month dropped from C3 '
                          'judgment" rule is operationalized over '
                          'DISCLOSURE-UNIVERSE MEMBERS (pool stocks with >=1 '
                          'hk_hold row in sessions [s-61, s-1]), because pool '
                          'stocks never covered by the northbound disclosure '
                          'universe are an eligibility property of the factor '
                          'domain (bimodal presence: ~27% of the pool has '
                          'zero rows in any year), not data failures - the '
                          'same treatment as C5 names without block trades.  '
                          'Fixed before any C3 IC was computed; decided from '
                          'coverage metadata only (presence distribution + '
                          'member-relative missing rates).  Superseded run '
                          '20260918T070814-p2r13-lowfreq-survey-051143da had '
                          'used universe-relative missing rates and dropped '
                          'every month; both runs retained on disk.',
}


def _check_budget(start: float, phase: str) -> None:
    elapsed = time.perf_counter() - start
    if elapsed > BUDGET_S:
        raise TimeoutError(f'budget exceeded ({elapsed:.0f}s > {BUDGET_S:.0f}s)'
                           f' at {phase}')


def load_config() -> dict:
    """Load the frozen config read-only.  The frozen file contains
    ``"direction": +1`` literals which standard JSON rejects; it is parsed
    leniently with yaml.safe_load (JSON is a YAML subset; '+1' is a legal
    YAML int).  The file itself is never modified; its sha256 is recorded
    in the run manifest."""
    import yaml
    path = ROOT / 'configs/experiments/p2r13-lowfreq-survey.json'
    return yaml.safe_load(path.read_text(encoding='utf-8'))


def verify_identities(root: Path) -> dict:
    """Fail-closed data-identity checks, before any consumed read."""
    ledger = lf.load_ledger(root)
    out = {'processed': lf.verify_processed_manifest(
        root, PROCESSED_MANIFEST, EXPECTED_MANIFEST_SHA)}
    out['raw_dirs'] = []
    for d in RAW_DIRS_VERIFIED:
        out['raw_dirs'].append(lf.verify_raw_dir(root, d, ledger))
    out['headers_uniform'] = []
    for d, pat in HEADER_CHECK_DIRS:
        out['headers_uniform'].append(lf.assert_uniform_headers(root, d, pat))
    out['daily_2015_2024_sha256'] = sha256(DAILY_2015)
    out['daily_1999_2024_sha256'] = sha256(DAILY_1999)
    n_2015 = pl.scan_parquet(DAILY_2015).select(pl.len()).collect().item()
    n_1999_slice = (pl.scan_parquet(DAILY_1999)
                    .filter(pl.col('date') >= date(2015, 1, 5))
                    .select(pl.len()).collect().item())
    if n_1999_slice != n_2015:
        raise RuntimeError(
            f'identity fail-closed: 1999-file 2015+ slice has {n_1999_slice} '
            f'rows vs pinned file {n_2015}')
    out['row_count_2015_slice_matches_pinned'] = True
    return out


def run_probe(root: Path) -> int:
    config = load_config()
    probe = lf.hk_hold_probe(root)
    zero = probe.filter(pl.col('a_share_rows') == 0)
    summary = {
        'window': '2017-01..2018-12',
        'months_checked': probe.height,
        'min_month_rows': int(probe['a_share_rows'].min()),
        'mean_month_rows': float(probe['a_share_rows'].mean()),
        'min_disclosed_days': int(probe['disclosed_days'].min()),
        'zero_row_months': [str(d) for d in zero['month'].to_list()],
        'verdict': ('NO_MISSING_MONTHS' if zero.height == 0
                    else 'MISSING_MONTHS_PRESENT'),
    }
    with Run(root, 'p2r13-lowfreq-survey', config) as run:
        run.manifest['mode'] = 'probe'
        run.manifest['probe_only'] = True
        run.metrics['probe_hk_hold_2017_18'] = summary
        probe.write_parquet(run.path / 'probe_hk_hold_2017_18.parquet')
        (run.path / 'report.md').write_text(
            '# P2-R13 C3 hk_hold completeness probe (2017-2018)\n\n'
            f"- verdict: **{summary['verdict']}**\n"
            f"- months checked: {summary['months_checked']}; min month rows: "
            f"{summary['min_month_rows']}; min disclosed days: "
            f"{summary['min_disclosed_days']}\n"
            f"- zero-row months: {summary['zero_row_months'] or 'none'}\n"
            f"- full table: probe_hk_hold_2017_18.parquet\n",
            encoding='utf-8')
        print(f"PROBE VERDICT: {summary['verdict']}; run={run.path}")
    return 0


def build_panel(root: Path, cal: pl.DataFrame,
                signals: pl.DataFrame) -> tuple[pl.DataFrame, dict]:
    """Full factor panel (universe + forward + C1..C6 + disclosure columns)."""
    aux: dict = {}
    hist = lf.build_history(DAILY_1999, cal)
    aux['pool_daily'] = (hist.filter(
        (pl.col('isST') == 0.0)
        & (pl.col('listing_index') > lf.NEW_LISTING_SESSIONS)
        & lf.board_ok_expr()
        & (pl.col('amt_med20') >= lf.LIQ_MEDIAN_AMOUNT)
        & (pl.col('close') >= lf.MIN_CLOSE))
        .group_by('date')
        .agg(pl.col('r').mean().alias('r'), pl.len().alias('n'))
        .sort('date'))
    thin = hist.select('symbol', 'mkt_idx', 'o_adj')
    pclose_tbl = hist.select('symbol', 'date', 'mkt_idx', 'pclose')
    sig_rows = hist.join(signals.select('s'), left_on='date',
                         right_on='s', how='semi')
    hist = None  # release the fat frame

    panel, waterfall = lf.universe_signals(sig_rows, signals)
    sig_rows = None
    panel = lf.attach_forward(thin, panel)

    hk = lf.load_hk_hold(root)
    aux['hk_a_share_rows'] = hk.height
    c3 = lf.northbound_delta(hk, cal, panel)
    panel = panel.join(c3.select('s', 'symbol', 'C3'),
                       on=['s', 'symbol'], how='left')
    aux['hk'] = hk

    accrual = lf.build_accrual_table(root)
    aux['accrual_report_rows'] = accrual.height
    c4 = lf.accrual_at_signal(accrual, panel)
    panel = panel.join(c4.select('s', 'symbol', 'C4', 'accrual_raw',
                                 'rep_end_date'),
                       on=['s', 'symbol'], how='left')
    accrual = None

    block = lf.load_block_trades(root, pclose_tbl)
    aux['block_trade_rows'] = block.height
    c5 = lf.block_discount_factor(block, panel)
    panel = panel.join(c5.select('s', 'symbol', 'C5', 'block_amt20'),
                       on=['s', 'symbol'], how='left')
    block = None

    basic = lf.load_daily_basic_at(root,
                                   sorted(panel['s'].unique().to_list()))
    panel = panel.join(basic.rename({'date': 's'}), on=['s', 'symbol'],
                       how='left')
    return panel.sort('s', 'symbol'), {'waterfall': waterfall, **aux}


def coverage_table(panel: pl.DataFrame) -> dict:
    out: dict[str, dict] = {}
    per_all = panel.group_by('s').agg(pl.len().alias('universe_n')).sort('s')
    for f in lf.FACTOR_NAMES:
        per = (panel.group_by('s')
               .agg(pl.col(f).is_not_null().sum().alias('valid_n'))
               .join(per_all, on='s')
               .with_columns((pl.col('valid_n')
                              / pl.col('universe_n')).alias('coverage'))
               .sort('s'))
        out[f] = {
            'mean_names_with_factor': float(per['valid_n'].mean()),
            'mean_coverage': float(per['coverage'].mean()),
            'min_coverage': float(per['coverage'].min()),
            'months_no_data': int((per['valid_n'] == 0).sum()),
            'n_pairs_factor_and_fwd': int(
                panel.filter(pl.col(f).is_not_null()
                             & pl.col('fwd').is_not_null()).height),
        }
    fwd_cov = (panel.group_by('s')
               .agg(pl.col('fwd').is_not_null().mean().alias('cov')))
    out['forward'] = {'mean_coverage': float(fwd_cov['cov'].mean()),
                      'min_coverage': float(fwd_cov['cov'].min()),
                      'mean_universe_n': float(per_all['universe_n'].mean())}
    return out


def fmt(value) -> str:
    if value is None:
        return '-'
    return f'{value:.4f}'


def render_report(metrics: dict, manifest: dict, smoke: bool) -> str:
    tag = ' - SMOKE (not authoritative)' if smoke else ''
    lines = [f'# P2-R13 low-frequency survey (mode={manifest.get("mode")}'
             f'{tag})', '',
             f"- verdict: **{metrics['verdict']}**; dev candidates: "
             f"{metrics['candidates'] or 'none'}",
             f"- panel waterfall: "
             f"{json.dumps(metrics['filter_waterfall'], ensure_ascii=False)}",
             f"- control C6 dev IC: {fmt(metrics['control_C6_dev_ic'])} "
             f"(NW(6) t {fmt(metrics['control_C6_dev_nw_t'])}, "
             f"{metrics['control_C6_dev_n_months']} dev months)",
             '',
             '| factor | dir | dev IC | NW(6) t | n mo | ann gross D10-D1 '
             '(x244/20) | same-sign mo | IC gate | decile gate | incr gate |',
             '|---|---|---|---|---|---|---|---|---|---|']
    for f in lf.FACTOR_NAMES:
        r = metrics['factor_results'][f]
        dev = r['dev']
        g = dev['gates']
        mark = ' (CONTROL)' if f == lf.CONTROL else ''
        if f == lf.CONTROL:
            incr = 'n/a'
        elif f in lf.INCREMENT_FACTORS:
            incr = 'PASS' if g.get('increment_gate') else '-'
        else:
            incr = 'n/a'
        lines.append(
            f"| {f}{mark} | {r['direction']:+d} "
            f"| {fmt(dev['ic']['mean_ic'])} | {fmt(dev['ic']['nw_t'])} "
            f"| {dev['ic']['n_months']} "
            f"| {fmt(dev['spread']['annualized'])} "
            f"| {fmt(dev['spread']['month_share_same_sign'])} "
            f"| {'PASS' if g['ic_gate'] else '-'} "
            f"| {'PASS' if g['decile_gate'] else '-'} | {incr} |")
    lines += ['',
              '- thresholds: |mean IC|>=0.02 & NW(6)|t|>=3; decile annualized '
              'gross >=4% & same-sign months >=60%; increment (C1/C2 only) '
              '|IC| >= 1.3x|IC_C6|',
              f"- C3 vs circ_mv: {json.dumps(metrics['c3_vs_circ_mv'])}; "
              f"family exit (rho>0.7): {metrics['c3_family_exit']}",
              f"- C4 pe/pb residual IC: "
              f"{json.dumps(metrics['c4_pepb_residual'])}",
              f"- C3 dropped months (member-relative missing >10%): "
              f"{json.dumps(metrics['c3_dropped_months'])}",
              f"- coverage: {json.dumps(metrics['coverage'])}",
              f"- M1 TOM: {json.dumps(metrics['m1_tom'], ensure_ascii=False)}",
              f"- val: {json.dumps(metrics['val'], ensure_ascii=False)}",
              f"- net reference (no gate): 20-session round trip on 20k "
              f"notional = {lf.round_trip_fee(date(2022, 1, 4)):.0f} CNY "
              f"(0.150%) before 2023-08-28, "
              f"{lf.round_trip_fee(date(2023, 9, 1)):.0f} CNY (0.100%) after; "
              f"x12.2 round trips/yr = 1.83%/1.22% fee drag",
              f"- trial count: {json.dumps(manifest['trial_count'])}",
              f"- deviations: "
              f"{json.dumps(manifest['deviations_disclosed'], ensure_ascii=False)}",
              f"- timings: {json.dumps(metrics['timings'])}"]
    return '\n'.join(lines) + '\n'


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=Path, default=ROOT /
                        'configs/experiments/p2r13-lowfreq-survey.json')
    parser.add_argument('--probe', action='store_true')
    parser.add_argument('--smoke', action='store_true')
    args = parser.parse_args()
    if args.probe:
        return run_probe(ROOT)

    config = load_config()
    os.chdir(ROOT)
    root = find_repo_root()
    t_start = time.perf_counter()
    smoke = bool(args.smoke)

    with Run(root, 'p2r13-lowfreq-survey', config) as run:
        run.manifest['mode'] = 'smoke' if smoke else 'full'
        run.manifest['prereg'] = config['prereg']
        run.manifest['config_frozen_at'] = config['frozen_at']
        run.manifest['config_file_sha256'] = sha256(
            ROOT / 'configs/experiments/p2r13-lowfreq-survey.json')
        run.manifest['config_parse_note'] = (
            'frozen config parsed leniently with yaml.safe_load because it '
            'contains "direction": +1 literals (invalid strict JSON); the '
            'file on disk was never modified (sha256 recorded above)')
        run.manifest['deviations_disclosed'] = DEVIATIONS
        run.manifest['trial_count'] = {
            'prior_cumulative': config['trials_cumulative_before'],
            'this_round_factors': config['trials_counted_this_round'],
            'cumulative_after': config['trials_cumulative_after']}
        run.manifest['window_declarations'] = {
            'dev': '2015-01-05..2020-12-31, 6th reuse, elimination use only',
            'val': '2021-01..2024-11 one-shot; 4th consumption of this window '
                   '(C08, R11 if reached, R12 if reached, this round); '
                   'consumed ONLY if >= 2 true factors pass all dev gates',
            'freeze': 'no rows on/after 2025-01-01; 2024-12-31 signal dropped '
                      '(its forward window would cross the boundary)'}

        t0 = time.perf_counter()
        run.manifest['identity_checks'] = verify_identities(root)
        run.metrics['timings'] = {
            'identity_s': time.perf_counter() - t0}
        _check_budget(t_start, 'identity verification')

        t0 = time.perf_counter()
        cal = lf.market_calendar(DAILY_1999)
        last_idx = int(cal['mkt_idx'].max())
        signals_full = (lf.month_end_sessions(cal)
                        .filter((pl.col('s') >= lf.DEV_START)
                                & (pl.col('s') <= lf.VAL_END)))
        if smoke:
            signals_full = signals_full.filter(pl.col('s')
                                               <= date(2015, 6, 30))
        frozen_out = signals_full.filter(
            pl.col('s_idx') + lf.HOLD_SESSIONS + 1 > last_idx)
        signals = lf.keep_complete_forward(signals_full, last_idx)
        run.metrics['signals'] = {
            'n_months': signals.height,
            'first_month': str(signals['month'].min()),
            'last_month': str(signals['month'].max()),
            'dropped_by_2025_freeze': [str(d) for d in frozen_out['s']
                                       .to_list()]}
        panel, aux = build_panel(root, cal, signals)
        run.metrics['filter_waterfall'] = aux['waterfall']
        run.metrics['source_row_counts'] = {
            'hk_a_share_rows': aux['hk_a_share_rows'],
            'accrual_report_rows': aux['accrual_report_rows'],
            'block_trade_rows': aux['block_trade_rows']}
        run.metrics['timings']['panel_build_s'] = time.perf_counter() - t0
        _check_budget(t_start, 'panel build')

        # C4 cross-section excludes financials (C4-only filter, disclosed)
        industries = lf.load_financial_symbols(root)
        n_fin_excluded = int(panel.join(industries.filter(
            pl.col('industry').is_in(list(lf.FINANCIAL_INDUSTRIES))),
            on='symbol', how='semi').height)
        panel_c4 = lf.apply_financial_exclusion(panel, industries)
        panel_c3, c3_drops = lf.c3_member_missing(panel, aux['hk'], cal)
        run.metrics['c3_dropped_months'] = c3_drops
        run.metrics['c4_financial_rows_excluded'] = n_fin_excluded

        t0 = time.perf_counter()
        control_ic = lf.window_ic(lf.monthly_rank_ic(panel, lf.CONTROL),
                                  lf.DEV_START, lf.DEV_END)
        run.metrics['control_C6_dev_ic'] = control_ic['mean_ic']
        run.metrics['control_C6_dev_nw_t'] = control_ic['nw_t']
        run.metrics['control_C6_dev_n_months'] = control_ic['n_months']
        results: dict[str, dict] = {}
        panels = {'C1': panel, 'C2': panel, 'C3': panel_c3, 'C4': panel_c4,
                  'C5': panel, 'C6': panel}
        for f in lf.FACTOR_NAMES:
            results[f] = lf.evaluate_dev(
                f, panels[f], control_ic['mean_ic'],
                lf.DIRECTIONS.get(f, 1))
            if f == lf.CONTROL:
                results[f]['is_control'] = True
        candidates = [f for f in lf.CANDIDATES if results[f]['passed_dev']]
        c3_rho = lf.mean_monthly_spearman(
            panel.filter((pl.col('s') >= lf.DEV_START)
                         & (pl.col('s') <= lf.DEV_END)), 'C3', 'circ_mv')
        run.metrics['c3_vs_circ_mv'] = c3_rho
        c3_family_exit = bool((c3_rho['mean_rho'] or 0.0)
                              > lf.C3_FAMILY_EXIT_RHO)
        run.metrics['c3_family_exit'] = c3_family_exit
        if c3_family_exit and 'C3' in candidates:
            candidates.remove('C3')
            results['C3']['family_exit'] = True
        run.metrics['factor_results'] = results
        run.metrics['candidates'] = candidates

        # correlations + C4 residual on the DEV window only (val one-shot)
        dev_panel = panel.filter((pl.col('s') >= lf.DEV_START)
                                 & (pl.col('s') <= lf.DEV_END))
        run.metrics['correlation_matrix_mean_monthly_spearman'] = \
            lf.factor_correlation_matrix(dev_panel)
        run.metrics['c4_pepb_residual'] = lf.c4_pepb_residual_ic(
            dev_panel.filter(pl.col('pe_ttm').is_not_null()
                             & pl.col('pb').is_not_null()))
        run.metrics['timings']['dev_evaluation_s'] = \
            time.perf_counter() - t0
        _check_budget(t_start, 'dev evaluation')

        # ---- val: only when >= 2 true factors pass all dev gates ----
        if len(candidates) >= lf.PASS_MIN_FACTOR_COUNT:
            t0 = time.perf_counter()
            val_out = {}
            for f in candidates:
                val_out[f] = lf.evaluate_val(f, panels[f],
                                             results[f]['dev_direction'])
            run.metrics['val'] = {'consumed': True, 'results': val_out}
            run.metrics['timings']['val_evaluation_s'] = \
                time.perf_counter() - t0
            val_candidates = [f for f, v in val_out.items() if v['pass']]
            run.metrics['val_candidates'] = val_candidates
        else:
            run.metrics['val'] = {
                'consumed': False,
                'reason': f'only {len(candidates)} dev passers (<2): val '
                          f'window NOT consumed this round'}

        # ---- M1 TOM (descriptive over the full window, per prereg) ----
        run.metrics['m1_tom'] = lf.tom_measurement(
            aux['pool_daily'], cal, lf.DEV_START, lf.VAL_END)
        run.metrics['coverage'] = coverage_table(panel)

        # ---- evidence files ----
        t0 = time.perf_counter()
        ic_frames, spread_frames = [], []
        ic_factors = {f: panels[f] for f in lf.FACTOR_NAMES}
        if not run.metrics['val']['consumed']:
            ic_factors = {f: p.filter(pl.col('s') <= lf.DEV_END)
                          for f, p in ic_factors.items()}
        for f, p in ic_factors.items():
            ic_frames.append(lf.monthly_rank_ic(p, f)
                             .with_columns(pl.lit(f).alias('factor')))
            spread_frames.append(
                lf.decile_monthly_spread(p, f)
                .with_columns(pl.lit(f).alias('factor')))
        pl.concat(ic_frames).select('factor', 's', 'n', 'ic') \
            .write_parquet(run.path / 'ic_monthly.parquet')
        pl.concat(spread_frames) \
            .write_parquet(run.path / 'decile_spread_monthly.parquet')
        panel.select('s', 'symbol', 'C1', 'C2', 'C3', 'C4', 'C5', 'C6',
                     'fwd', 'pe_ttm', 'pb', 'circ_mv', 'block_amt20') \
            .write_parquet(run.path / 'panel_signals.parquet')
        run.metrics['timings']['evidence_write_s'] = \
            time.perf_counter() - t0

        verdict = ('REGISTER_CANDIDATES' if len(candidates)
                   >= lf.PASS_MIN_FACTOR_COUNT else 'G4_SURVEY_CLOSED')
        run.metrics['verdict'] = verdict
        run.metrics['pass_threshold'] = lf.PASS_MIN_FACTOR_COUNT
        run.metrics['gate_thresholds'] = {
            'ic_abs_mean': lf.IC_GATE_ABS_MEAN, 'ic_nw_lag': lf.NW_LAG,
            'ic_nw_t': lf.IC_GATE_NW_T,
            'decile_annualized_gross': lf.DECILE_GATE_ANNUAL,
            'decile_month_share': lf.DECILE_GATE_MONTH_SHARE,
            'increment_ratio': lf.INCREMENT_GATE_RATIO,
            'annualize': lf.ANNUALIZE_FACTOR}
        run.metrics['timings']['total_s'] = time.perf_counter() - t_start

        (run.path / 'report.md').write_text(
            render_report(run.metrics, run.manifest, smoke),
            encoding='utf-8')
        _check_budget(t_start, 'total')
        print(f"VERDICT: {verdict}; candidates={candidates}; "
              f"val={run.metrics['val'].get('consumed')}; run={run.path}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
