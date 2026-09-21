"""P2-R10 half-day (11:30) cross-sectional signal survey CLI.

Preregistered by ``docs/research/exp-20260918-p2r10-halfday-survey-prereg.md``
with the frozen config ``configs/experiments/p2r10-halfday-survey.json``
(config is read-only input; never modified).

Usage:
  PYTHONPATH=D:/量化/src .venv/Scripts/python.exe -X utf8 \
      src/quant/cli/p2r10_halfday_survey.py [--smoke]

``--smoke`` runs the identical pipeline on 2015-01-01..2015-03-31 for
correctness and timing only (numbers labelled SMOKE, not authoritative).
Full run: dev 2015-2020 gates + 2021-2024 descriptive-only disclosure.
Trial accounting: cumulative 139 + 12 = 151.  Stop rule: no further rounds
tonight after this run.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'src'))

from quant.research.p2r10_halfday import (  # noqa: E402
    CONTROL,
    DECILE_GATE_ANNUAL,
    DECILE_GATE_MONTH_SHARE,
    DEV_END,
    DEV_START,
    DESC_END,
    DESC_START,
    FACTOR_NAMES,
    IC_GATE_ABS_MEAN,
    IC_GATE_NW_T,
    INCREMENT_GATE_RATIO,
    MIN_IC_STOCKS,
    MOMENTUM_FAMILY,
    PASS_MIN_FACTOR_COUNT,
    SESSIONS_PER_YEAR,
    T1_OUTLIER_BOUND,
    apply_sample_filters,
    attach_net_one_day,
    compute_factors,
    daily_rank_ic,
    decile_gate_pass,
    decile_spread_series,
    factor_direction,
    ic_gate_pass,
    increment_gate_pass,
    load_daily_vol20,
    load_listing_index,
    net_reference,
    spread_window_stats,
    window_ic,
    yearly_ic,
)
from quant.research.runs import Run, find_repo_root, sha256  # noqa: E402

HALFDAY_PARQUET = ROOT / 'data/processed/halfday-1130-20260918/halfday_1130.parquet'
BAOSTOCK_DAILY = ROOT / 'data/processed/baostock-daily-20260917/daily_1999_2024.parquet'
EXTRACT_RUN = '20260918T035435-halfday-extract-k4x8vt'
BUDGET_S = 1800.0

HALFDAY_COLS = [
    'symbol', 'date', 'preclose_official', 'open_930', 'close_1100',
    'close_1130', 'open_1300', 'close_day_official', 'high_am', 'low_am',
    'vol_am', 'am_limit_up_touch_minutes', 'tradestatus', 'isST',
]


def _check_budget(start_ts: float, phase: str) -> None:
    elapsed = time.perf_counter() - start_ts
    if elapsed > BUDGET_S:
        raise TimeoutError(
            f'budget exceeded ({elapsed:.0f}s > {BUDGET_S:.0f}s) at {phase}')


def build_panel(smoke: bool) -> tuple[pl.DataFrame, dict]:
    """Filtered factor panel + per-stage waterfall counts."""
    counts: dict[str, object] = {}
    halfday = pl.read_parquet(HALFDAY_PARQUET, columns=HALFDAY_COLS)
    counts['halfday_rows_total'] = halfday.height
    counts['symbols_total'] = halfday['symbol'].n_unique()

    listing = load_listing_index(BAOSTOCK_DAILY)
    vol20 = load_daily_vol20(BAOSTOCK_DAILY)
    counts['baostock_daily_1999_2024_rows'] = pl.scan_parquet(
        BAOSTOCK_DAILY).select(pl.len()).collect().item()

    symbol = pl.col('symbol')
    board_ok = (
        (symbol.str.starts_with('sh.60'))
        | (symbol.str.starts_with('sz.00'))
        | (symbol.str.starts_with('sz.30'))
    ) & ~symbol.is_in({'sz.000905', 'sz.000852'})

    df = (halfday
          .filter(pl.col('tradestatus') == 1)
          .filter(pl.col('isST') == 0))
    counts['after_suspended_st'] = df.height
    df = (df.join(listing, on=['symbol', 'date'], how='left')
            .join(vol20, on=['symbol', 'date'], how='left')
            .filter(pl.col('listing_index') > 120))
    counts['after_new_listing_120'] = df.height
    df = df.filter(board_ok)
    counts['after_boards'] = df.height
    df = df.filter(
        pl.col('preclose_official').is_not_null()
        & pl.col('open_930').is_not_null()
        & pl.col('open_1300').is_not_null()
        & pl.col('close_day_official').is_not_null())
    counts['after_missing_keys'] = df.height

    if smoke:
        df = df.filter((pl.col('date') >= date(2015, 1, 1))
                       & (pl.col('date') <= date(2015, 3, 31)))
        counts['after_smoke_window'] = df.height

    df = compute_factors(df)
    df = df.filter(pl.col('T1').abs() <= T1_OUTLIER_BOUND)
    counts['after_t1_outlier_021'] = df.height
    df = attach_net_one_day(df)
    counts['symbols_filtered'] = df['symbol'].n_unique()
    counts['days_filtered'] = df['date'].n_unique()
    counts['t2_non_null'] = df['T2'].is_not_null().sum()
    counts['f8_non_null'] = df['F08'].is_not_null().sum()
    counts['f7_non_null'] = df['F07'].is_not_null().sum()
    return df, counts


def evaluate_factor(factor: str, panel: pl.DataFrame) -> dict:
    """All dev gates + descriptive windows for one factor."""
    ic = daily_rank_ic(panel, factor, 'T1')
    dev_ic = window_ic(ic, DEV_START, DEV_END)
    direction = factor_direction(dev_ic['mean_ic'])
    spread = decile_spread_series(panel, factor)
    dev_stats = spread_window_stats(spread, DEV_START, DEV_END, direction)

    buyable = panel.filter(pl.col('am_limit_up_touch_minutes') == 0)
    spread_b = decile_spread_series(buyable, factor)
    dev_stats_b = spread_window_stats(spread_b, DEV_START, DEV_END, direction)

    net = net_reference(panel, factor, direction, DEV_START, DEV_END)

    years = yearly_ic(ic, direction) if ic.height else []

    gates = {
        'ic_gate': ic_gate_pass(dev_ic),
        'decile_gate': decile_gate_pass(dev_stats),
        'increment_gate': increment_gate_pass(
            factor, dev_ic['mean_ic'], None),
        'buyable_disclosure': {
            'annualized': dev_stats_b.annualized,
            'month_share_same_sign': dev_stats_b.month_share_same_sign,
            'n_days': dev_stats_b.n_days,
        },
    }
    return {'factor': factor, 'direction': direction, 'dev_ic': dev_ic,
            'dev_spread': {
                'n_days': dev_stats.n_days,
                'mean_daily': dev_stats.mean_daily,
                'annualized_gross': dev_stats.annualized,
                'month_share_same_sign': dev_stats.month_share_same_sign,
                'n_months': dev_stats.n_months,
            },
            'dev_net_reference': net,
            'yearly_ic': years,
            'gates': gates}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=Path,
                        default=ROOT / 'configs/experiments/p2r10-halfday-survey.json')
    parser.add_argument('--smoke', action='store_true')
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding='utf-8'))
    if args.smoke:
        config = {**config, 'mode': 'smoke_3m_2015Q1'}

    import os
    os.chdir(ROOT)
    root = find_repo_root()
    t_start = time.perf_counter()

    with Run(root, config['name'], config) as run:
        run.manifest['prereg'] = config['prereg']
        run.manifest['preregistered_at'] = config['preregistered_at']
        run.manifest['config_frozen_at'] = config['frozen_at']
        run.manifest['mode'] = 'smoke' if args.smoke else 'full'
        run.manifest['dataset'] = {
            'id': config['dataset']['id'],
            'halfday_parquet': {
                'path': str(HALFDAY_PARQUET.relative_to(root)),
                'sha256': sha256(HALFDAY_PARQUET),
                'rows': 9440361,
                'extract_run': EXTRACT_RUN,
            },
            'baostock_daily_1999_2024': {
                'path': str(BAOSTOCK_DAILY.relative_to(root)),
                'sha256': sha256(BAOSTOCK_DAILY),
                'use': 'F03/F07 past-20-session daily volume + listing age '
                       '(superset of the P1-accepted 2015-2024 file: '
                       'pre-2015 history for pre-2015 listings)',
            },
            'extract_assertions_note': 'A3 sampled-day 3 violations are '
                'covered by the A3b full-window diagnostic (268 rows = 243 '
                'suspended placeholders + 25 trading-row vendor divergence); '
                '243 suspended rows are dropped by the tradestatus filter, '
                'the 25 trading rows remain and are disclosed',
        }
        run.manifest['window_declarations'] = {
            'dev': '2015-01-01..2020-12-31 DECLARED CONSUMED by 91 prior '
                   'stock-side units; same-window new-information-set claim '
                   '(11:30 cross-section vs prior close cross-sections)',
            'descriptive_2021_2024': 'consumed once by 47 units; yearly '
                                     'descriptive disclosure only, NO gates',
            'freeze': 'no rows on/after 2025-01-01 (dataset ends 2024-12-31)',
        }
        run.manifest['trial_count'] = {
            'prior_cumulative': 139, 'this_round_factors': 12,
            'cumulative_after': 151}
        run.manifest['semantics'] = {
            'open_1300': '13:01 first afternoon bar open (vendor has no '
                         '13:00 bar); T1 = close_day_official/open_1300 - 1 '
                         'therefore starts at 13:01, disclosed as deviation',
            't1': 'close_day_official / open_1300 - 1 (primary)',
            't2': 'next filtered open_930 / close_1130 - 1 (descriptive)',
            'min_ic_stocks': MIN_IC_STOCKS,
            'sessions_per_year': SESSIONS_PER_YEAR,
            'chinext_ruling': 'ChiNext included per user 2026-09-17 '
                              'permission confirmation (overrides main-plan '
                              'v4 exclusion); disclosed decision',
        }

        t0 = time.perf_counter()
        panel, waterfall = build_panel(args.smoke)
        t_build = time.perf_counter() - t0
        run.metrics['filter_waterfall'] = waterfall
        run.metrics['timings'] = {'panel_build_s': t_build}
        _check_budget(t_start, 'panel build')

        t0 = time.perf_counter()
        results: dict[str, dict] = {}
        control_ic = window_ic(daily_rank_ic(panel, CONTROL, 'T1'),
                               DEV_START, DEV_END)['mean_ic']
        run.metrics['control_F12_dev_ic'] = control_ic
        for factor in FACTOR_NAMES:
            entry = evaluate_factor(factor, panel)
            if factor in MOMENTUM_FAMILY:
                entry['gates']['increment_gate'] = increment_gate_pass(
                    factor, entry['dev_ic']['mean_ic'], control_ic)
            if factor == CONTROL:
                entry['is_control'] = True
            results[factor] = entry
        t_eval = time.perf_counter() - t0
        run.metrics['timings']['factor_evaluation_s'] = t_eval
        _check_budget(t_start, 'factor evaluation')

        # candidate registration (F12 excluded from the numerator)
        candidates = [
            f for f in FACTOR_NAMES
            if f != CONTROL
            and results[f]['gates']['ic_gate']
            and results[f]['gates']['decile_gate']
            and results[f]['gates']['increment_gate']
        ]
        verdict = ('REGISTER_CANDIDATES' if len(candidates)
                   >= PASS_MIN_FACTOR_COUNT else 'G2_ROUND1_CLOSED')
        run.metrics['factor_results'] = results
        run.metrics['candidates'] = candidates
        run.metrics['verdict'] = verdict
        run.metrics['pass_threshold'] = PASS_MIN_FACTOR_COUNT
        run.metrics['gate_thresholds'] = {
            'ic_abs_mean': IC_GATE_ABS_MEAN, 'ic_nw_t': IC_GATE_NW_T,
            'decile_annualized_gross': DECILE_GATE_ANNUAL,
            'decile_month_share': DECILE_GATE_MONTH_SHARE,
            'increment_ratio_vs_F12': INCREMENT_GATE_RATIO}

        # ---- evidence files (small) ----
        t0 = time.perf_counter()
        ic_long = pl.concat([
            daily_rank_ic(panel, f, 'T1').with_columns(pl.lit(f).alias('factor'))
            for f in FACTOR_NAMES]).select('factor', 'date', 'n', 'ic')
        ic_long.write_parquet(run.path / 'ic_daily.parquet')

        spread_frames = []
        for f in FACTOR_NAMES:
            base = decile_spread_series(panel, f).with_columns(
                pl.lit(f).alias('factor'), pl.lit(False).alias('buyable_only'))
            buy = decile_spread_series(
                panel.filter(pl.col('am_limit_up_touch_minutes') == 0), f
            ).with_columns(pl.lit(f).alias('factor'),
                           pl.lit(True).alias('buyable_only'))
            cols = ['factor', 'date', 'buyable_only', 'd1', 'd10', 'spread']
            spread_frames.append(base.select(cols))
            spread_frames.append(buy.select(cols))
        pl.concat(spread_frames).write_parquet(run.path / 'decile_spread_daily.parquet')
        t_out = time.perf_counter() - t0
        run.metrics['timings']['evidence_write_s'] = t_out

        # T2 descriptive summary
        t2 = panel.select('T2')
        run.metrics['t2_descriptive'] = {
            'mean': float(t2['T2'].mean()),
            'std': float(t2['T2'].std()),
            'n_non_null': int(t2['T2'].is_not_null().sum()),
            'note': 'overnight + next-morning return; disclosed only, no gate',
        }
        run.metrics['timings']['total_s'] = time.perf_counter() - t_start

        (run.path / 'report.md').write_text(
            render_report(run.metrics, run.manifest, args.smoke),
            encoding='utf-8')
        print(f"VERDICT: {verdict}; candidates={candidates}; "
              f"run={run.path}")
    return 0


def render_report(metrics: dict, manifest: dict, smoke: bool) -> str:
    lines = [
        f"# P2-R10 half-day survey (mode={manifest.get('mode', 'full')}"
        f"{' - SMOKE' if smoke else ''})", '',
        f"- verdict: **{metrics['verdict']}**; candidates: "
        f"{metrics['candidates'] or 'none'}",
        f"- panel: {json.dumps(metrics['filter_waterfall'], ensure_ascii=False)}",
        f"- control F12 dev IC: {metrics['control_F12_dev_ic']}",
        '',
        '| factor | dir | dev IC | NW t | ann. gross D10-D1 | '
        'month share | buyable ann. | buyable share | IC gate | decile gate '
        '| incr gate | net ann. ref |',
        '|---|---|---|---|---|---|---|---|---|---|---|---|',
    ]
    for f in FACTOR_NAMES:
        r = metrics['factor_results'][f]
        g = r['gates']
        ic = r['dev_ic']
        sp = r['dev_spread']
        nb = g['buyable_disclosure']
        mark = ' (CONTROL)' if f == CONTROL else ''
        if f == CONTROL:
            incr_cell = 'n/a (control)'
        elif f in MOMENTUM_FAMILY:
            incr_cell = 'PASS' if g['increment_gate'] else '-'
        else:
            incr_cell = 'n/a'
        lines.append(
            f"| {f}{mark} | {r['direction']:+d} | {fmt(ic['mean_ic'])} | "
            f"{fmt(ic['nw_t'])} | {fmt(sp['annualized_gross'])} | "
            f"{fmt(sp['month_share_same_sign'])} | {fmt(nb['annualized'])} | "
            f"{fmt(nb['month_share_same_sign'])} | "
            f"{'PASS' if g['ic_gate'] else '-'} | "
            f"{'PASS' if g['decile_gate'] else '-'} | "
            f"{incr_cell} | "
            f"{fmt(r['dev_net_reference']['annualized_net_spread'])} |")
    lines += ['', f"- thresholds: {json.dumps(metrics['gate_thresholds'])}",
              f"- yearly IC (descriptive 2021-2024, no gates): see "
              f"metrics.json factor_results[*].yearly_ic",
              f"- timings: {json.dumps(metrics['timings'])}",
              f"- trial count: {json.dumps(manifest['trial_count'])}",
              f"- T2 descriptive: {json.dumps(metrics['t2_descriptive'])}"]
    return '\n'.join(lines) + '\n'


def fmt(value) -> str:
    return '-' if value is None else f'{value:.4f}'


if __name__ == '__main__':
    raise SystemExit(main())
