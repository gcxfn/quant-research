"""Thin command entry for exp-20260918-p2r12-event-veto (P2-R12 event veto chain).

Run (repo root):
  PYTHONPATH=D:/量化/src D:/量化/.venv/Scripts/python.exe -X utf8 \
      tools/run_p2r12_event_veto.py            # full window run
  ... tools/run_p2r12_event_veto.py --smoke    # single-family 3-month assertions

Implements the frozen preregistration
docs/research/exp-20260918-p2r12-event-veto-prereg.md and
configs/experiments/p2r12-event-veto.json; all computation lives in
src/quant/research/p2r12_event_veto.py.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

import polars as pl

from quant.research import p2r12_event_veto as ev
from quant.research.runs import Run, find_repo_root, write_json

CONFIG_PATH = Path('configs/experiments/p2r12-event-veto.json')


# --------------------------------------------------------------------------- #
# assembly
# --------------------------------------------------------------------------- #
def assemble(root: Path, calendar: ev.Calendar) -> tuple[pl.DataFrame, dict]:
    """Load every input, build S and all event frames; return counts."""
    art: dict = {}
    daily, counts = ev.build_daily_frame(root, calendar)
    art['daily'] = counts
    circ = ev.load_circ_mv(root)
    s = ev.build_session_frame(daily, circ, calendar)
    del daily, circ
    art['session_rows'] = s.height
    art['session_dates'] = [str(s['date'].min()), str(s['date'].max())]

    sf = pl.read_parquet(root / ev.EVENT_DIR / 'share_float.parquet')
    unlock_events, unlock_ranges, c01c = ev.build_unlock_events(sf, calendar)
    art['c01'] = c01c
    n_dup = unlock_events.height
    unlock_events = unlock_events.unique(subset=['symbol', 'pos'], keep='first')
    art['c01']['dedup_activation_duplicates'] = n_dup - unlock_events.height

    dd = pl.read_parquet(root / ev.EVENT_DIR / 'disclosure_date.parquet')
    disc_ranges, c03c = ev.build_disclosure_ranges(dd, calendar)
    art['c03'] = c03c

    raw_fcst = pl.scan_csv(root / 'data/raw/tushare/forecast/20260909-r1/chunk_*.csv') \
        .select('ts_code', pl.col('ann_date').cast(pl.String),
                pl.col('end_date').cast(pl.String), pl.col('type').cast(pl.String),
                'p_change_min', pl.col('first_ann_date').cast(pl.String),
                pl.col('update_flag').cast(pl.Int64))
    down_events, firstneg_events, c02c = ev.build_forecast_chains(
        raw_fcst.collect(), calendar)
    art['c02'] = c02c
    for name in ('down', 'firstneg'):
        frame = down_events if name == 'down' else firstneg_events
        if frame.height:
            n = frame.height
            frame = frame.unique(subset=['symbol', 'pos'], keep='first')
            art['c02'][f'{name}_dedup'] = n - frame.height
            if name == 'down':
                down_events = frame
            else:
                firstneg_events = frame

    raw_ht = pl.scan_csv(root / 'data/raw/tushare/stk_holdertrade/20260909-r3/chunk_*.csv') \
        .select('ts_code', pl.col('ann_date').cast(pl.String), 'holder_type',
                'in_de', 'change_ratio')
    c_de_events, gp_events, c04c = ev.build_holdertrade_events(raw_ht.collect(), calendar)
    art['c04'] = c04c
    if c_de_events.height:
        c_de_events = c_de_events.unique(subset=['symbol', 'pos'], keep='first')
    if gp_events.height:
        gp_events = gp_events.unique(subset=['symbol', 'pos'], keep='first')

    cf = (pl.scan_csv(root / 'data/raw/tushare/cashflow/20260909-r3/chunk_*.csv')
          .select(pl.col('ts_code'), pl.col('ann_date').cast(pl.String),
                  pl.col('f_ann_date').cast(pl.String),
                  pl.col('end_date').cast(pl.String),
                  pl.col('net_profit').cast(pl.Float64, strict=False),
                  pl.col('n_cashflow_act').cast(pl.Float64, strict=False),
                  pl.col('update_flag').cast(pl.String))
          .filter(pl.col('end_date').str.ends_with('1231'))
          .collect())
    bs = (pl.scan_csv(root / 'data/raw/tushare/balancesheet/20260909-r3/chunk_*.csv')
          .select(pl.col('ts_code'), pl.col('ann_date').cast(pl.String),
                  pl.col('f_ann_date').cast(pl.String),
                  pl.col('end_date').cast(pl.String),
                  pl.col('total_assets').cast(pl.Float64, strict=False),
                  pl.col('update_flag').cast(pl.String))
          .filter(pl.col('end_date').str.ends_with('1231'))
          .collect())
    industries = ev.load_financial_industries(root)
    cohorts, c05c = ev.build_accrual_cohorts(cf, bs, industries, calendar)
    art['c05'] = c05c

    s = ev.attach_veto_flags(s, calendar, unlock_ranges, down_events,
                             disc_ranges, c_de_events, cohorts)

    forecast_tab = pl.read_parquet(root / ev.EVENT_DIR / 'forecast.parquet')
    forecast_neg = (forecast_tab.filter(pl.col('direction') == -1)
                    .filter(pl.col('in_pool'))
                    .with_columns(ev.ts_symbol_expr().alias('symbol'))
                    .select('symbol', 'ts_knowledge'))
    art['c05']['forecast_negative_rows'] = forecast_neg.height
    forecast_start = forecast_tab['ts_knowledge'].min()
    art['c05']['forecast_coverage_start'] = str(forecast_start)

    frames = {
        'sf': sf, 'unlock_events': unlock_events, 'unlock_ranges': unlock_ranges,
        'down_events': down_events, 'firstneg_events': firstneg_events,
        'c_de_events': c_de_events, 'gp_events': gp_events,
        'cohorts': cohorts, 'forecast_neg': forecast_neg,
        'forecast_start': forecast_start,
    }
    return s, frames, art


def events_with_session(events: pl.DataFrame, s: pl.DataFrame,
                        label: str) -> tuple[pl.DataFrame, int]:
    """Attach the signal session to event rows; returns (frame, dropped)."""
    n0 = events.height
    out = events.join(s.select('symbol', 'pos', 'date'),
                      on=['symbol', 'pos'], how='inner')
    return out, n0 - out.height


# --------------------------------------------------------------------------- #
# unit evaluations
# --------------------------------------------------------------------------- #
def unit_c01(s: pl.DataFrame, unlock_events: pl.DataFrame) -> tuple[dict, pl.DataFrame]:
    ev_fr, dropped = events_with_session(unlock_events, s, 'C01')
    matched, mcounts = ev.match_controls(
        s, ev_fr, 'v1', 'fwd5',
        carry_ctrl=('fwd10',),
        carry_event=('fwd10', 'exit5_date', 'exit10_date'))
    matched = matched.with_columns(
        (pl.col('fwd10_event') - pl.col('fwd10_ctrl')).alias('excess10'))
    matched = matched.rename({'exit5_date_event': 'exit5_date',
                              'exit10_date_event': 'exit10_date'})
    # purge on the LONGER horizon so neither label crosses the dev/val boundary
    matched, wcounts = ev.assign_window(matched, exit_col='exit10_date')
    matched = matched.with_columns(pl.col('date').dt.year().alias('year'))
    out: dict = {'dropped_not_in_pool_session': dropped,
                 'counts': {**mcounts, **wcounts}}
    for window in ('dev', 'val'):
        part = matched.filter(pl.col('window') == window)
        stats = ev.window_excess_stats(part)
        if part.height:
            stats['mean_excess10'] = float(part['excess10'].mean())
            stats['ci10'] = ev.bootstrap_ci_mean(part['excess10'].to_numpy(),
                                                 part['date'].to_numpy())
        else:
            stats['mean_excess10'] = None
            stats['ci10'] = None
        gate_primary = bool(stats['mean_excess'] is not None
                            and stats['mean_excess'] <= ev.C01_PRIMARY_MAX
                            and ev.ci_excludes_zero(stats['ci']))
        gate_norebound = bool(stats['mean_excess10'] is not None
                              and stats['mean_excess10'] <= ev.C01_NOREBOUND_MAX)
        stats['gate_primary'] = gate_primary
        stats['gate_no_rebound'] = gate_norebound
        stats['gate_years'] = stats['years_gate']['pass']
        stats['pass'] = bool(gate_primary and gate_norebound
                             and stats['gate_years'])
        out[window] = stats
    return out, matched


def unit_c02(s: pl.DataFrame, down_events: pl.DataFrame,
             firstneg_events: pl.DataFrame) -> tuple[dict, dict, dict]:
    def run(frame: pl.DataFrame) -> tuple[dict, pl.DataFrame]:
        ev_fr, dropped = events_with_session(frame, s, 'C02')
        matched, stats = ev.run_excess_unit(ev_fr, s, 'v2', 'fwd5')
        stats['dropped_not_in_pool_session'] = dropped
        return stats, matched

    down_stats, matched_down = run(down_events)
    deep_stats, matched_deep = run(down_events.filter(pl.col('deep'))
                                   if down_events.height else down_events)
    fn_stats, matched_fn = run(firstneg_events)
    out: dict = {'down': down_stats, 'deep': deep_stats, 'first_negative': fn_stats}
    for window in ('dev', 'val'):
        n = down_stats[window]['n_matched']
        cells: dict = {'n_down': n, 'n_deep': deep_stats[window]['n_matched'],
                       'n_first_negative': fn_stats[window]['n_matched']}
        if n < ev.C02_MIN_SAMPLE:
            cells['verdict'] = 'evidence_insufficient'
            cells['gate_primary'] = None
            cells['gate_deep'] = None
            cells['gate_years'] = None
            cells['pass'] = False
        else:
            prim = down_stats[window]
            cells['gate_primary'] = bool(prim['mean_excess'] is not None
                                         and prim['mean_excess'] <= ev.C02_PRIMARY_MAX)
            cells['gate_years'] = prim['years_gate']['pass']
            mean_deep = deep_stats[window]['mean_excess']
            mean_fn = fn_stats[window]['mean_excess']
            gap = (mean_deep - mean_fn) if (mean_deep is not None
                                            and mean_fn is not None) else None
            cells['deep_minus_firstneg'] = gap
            cells['gate_deep'] = bool(mean_deep is not None
                                      and mean_deep <= ev.C02_DEEP_MAX
                                      and gap is not None
                                      and gap <= -ev.C02_DEEP_GAP)
            cells['pass'] = bool(cells['gate_primary'] and cells['gate_deep']
                                 and cells['gate_years'])
        out[window] = {**out.get(window, {}), **cells}
    return out, matched_down, matched_deep


def unit_c03(s: pl.DataFrame) -> tuple[dict, pl.DataFrame]:
    ev_fr = (s.filter(pl.col('v3'))
             .select('symbol', 'pos', 'date', 'exit5_date',
                     'block5_exit', 'block5_window'))
    matched, mcounts = ev.match_controls(s, ev_fr, 'v3', 'fwd5',
                                         carry_ctrl=('block5_exit',
                                                     'block5_window'))
    matched, wcounts = ev.assign_window(matched, exit_col='exit5_date')
    matched = matched.with_columns(pl.col('date').dt.year().alias('year'))
    out = ev.evaluate_c03(matched)
    out['counts'] = {**mcounts, **wcounts}
    return out, matched


def _segment_gate(stats: dict) -> dict:
    gate_primary = bool(stats['mean_excess'] is not None
                        and stats['mean_excess'] <= ev.C04_PRIMARY_MAX
                        and ev.ci_excludes_zero(stats['ci']))
    return {'gate_primary': gate_primary,
            'gate_years': stats['years_gate']['pass'],
            'pass': bool(gate_primary and stats['years_gate']['pass']),
            **stats}


def unit_c04(s: pl.DataFrame, c_de_events: pl.DataFrame,
             gp_events: pl.DataFrame) -> tuple[dict, pl.DataFrame, pl.DataFrame]:
    cev, dropped_c = events_with_session(c_de_events, s, 'C04')
    matched_c, stats_c = ev.run_excess_unit(cev, s, 'v4', 'fwd10')
    gev, dropped_g = events_with_session(gp_events, s, 'C04GP')
    matched_g, stats_g = ev.run_excess_unit(gev, s, 'v4', 'fwd10')
    out: dict = {'dropped_not_in_pool_session': {'c': dropped_c, 'gp': dropped_g}}
    for window in ('dev', 'val'):
        cells: dict = {}
        segments = ('pre', 'post') if window == 'dev' else ('post',)
        for segment in segments:
            part = matched_c.filter((pl.col('window') == window)
                                    & (pl.col('segment') == segment))
            cells[segment] = _segment_gate(ev.window_excess_stats(part))
        cells['pass'] = bool(all(cells[seg]['pass'] for seg in segments))
        gp_part = matched_g.filter(pl.col('window') == window)
        gp_mean = (float(gp_part['excess'].mean()) if gp_part.height else None)
        cells['gp_mean_excess'] = gp_mean
        cells['gp_n'] = gp_part.height
        cells['asymmetry_secondary_ok'] = bool(
            gp_mean is not None and abs(gp_mean) < ev.C04_GP_BOUND)
        out[window] = cells
    out['counts'] = {'c': stats_c['counts'], 'gp': stats_g['counts']}
    return out, matched_c, matched_g


def unit_c05(s: pl.DataFrame, cohorts: pl.DataFrame, forecast_neg: pl.DataFrame,
             forecast_start) -> tuple[dict, pl.DataFrame, pl.DataFrame]:
    incidence = ev.c05_incidence(cohorts, forecast_neg, forecast_start)
    detail = incidence.pop('detail')
    marked = cohorts.filter(pl.col('marked'))
    n0 = marked.height
    marked = marked.unique(subset=['symbol', 'pos'], keep='first')
    ev_fr, dropped = events_with_session(marked, s, 'C05')
    matched, stats = ev.run_excess_unit(ev_fr, s, 'v5', 'fwd60')
    out: dict = {'incidence': incidence,
                 'secondary_dropped_not_in_pool_session': dropped,
                 'secondary_dedup_cohort_rows': n0 - marked.height}
    for window in ('dev', 'val'):
        inc = incidence['windows'][window]
        sec = stats[window]
        cells = {'gate_ratio': inc['gate_ratio'],
                 'gate_years': inc['years_gate']['pass'],
                 'secondary_mean_excess': sec['mean_excess'],
                 'secondary_n': sec['n_matched'],
                 'secondary_gate': bool(sec['mean_excess'] is not None
                                        and sec['mean_excess'] <= ev.C05_SECONDARY_MAX)}
        cells['pass'] = bool(inc['gate_ratio'] and inc['years_gate']['pass'])
        out[window] = cells
    out['secondary_counts'] = stats['counts']
    return out, matched, detail


def run_units(s: pl.DataFrame, frames: dict) -> tuple[dict, dict]:
    metrics: dict = {}
    details: dict = {}
    metrics['C01'], details['C01'] = unit_c01(s, frames['unlock_events'])
    metrics['C02'], m_down, m_deep = unit_c02(s, frames['down_events'],
                                              frames['firstneg_events'])
    details['C02_down'] = m_down
    details['C02_deep'] = m_deep
    metrics['C03'], details['C03'] = unit_c03(s)
    metrics['C04'], details['C04'], details['C04_gp'] = unit_c04(
        s, frames['c_de_events'], frames['gp_events'])
    metrics['C05'], details['C05'], details['C05_incidence'] = unit_c05(
        s, frames['cohorts'], frames['forecast_neg'], frames['forecast_start'])
    metrics['C06'] = ev.evaluate_c06(s)
    metrics['C07'] = ev.evaluate_c07(frames['unlock_events'],
                                     frames['c_de_events'])

    # dev -> val one-shot verdicts
    verdicts: dict = {}
    for unit in ('C01', 'C02', 'C03', 'C04', 'C05', 'C06'):
        dev_pass = bool(metrics[unit]['dev'].get('pass'))
        val_pass = bool(metrics[unit]['val'].get('pass')) if dev_pass else None
        verdicts[unit] = {'dev_pass': dev_pass, 'val_pass': val_pass}
    metrics['verdicts'] = verdicts
    return metrics, details


# --------------------------------------------------------------------------- #
# smoke (single family, 3 months, full assertions)
# --------------------------------------------------------------------------- #
def run_smoke(s: pl.DataFrame, frames: dict, calendar: ev.Calendar) -> dict:
    lo, hi = date(2019, 1, 1), date(2019, 3, 31)
    unlock = frames['unlock_events']
    keep = set()
    for rec in unlock.select('pos').iter_rows(named=True):
        d = calendar.date_at(rec['pos'])
        if lo <= d <= hi:
            keep.add(rec['pos'])
    sub = unlock.filter(pl.col('pos').is_in(sorted(keep)))
    metrics, matched = unit_c01(s, sub)
    checks: dict = {}

    # knowledge date on or before the signal session (announcement at close
    # of session t feeds the t-close signal; entry is t+1)
    joined = (sub.join(s.select('symbol', 'pos', 'date'),
                       on=['symbol', 'pos'], how='inner')
              .join(frames['sf'].select('event_id', 'ts_knowledge'),
                    on='event_id', how='left'))
    checks['pit_knowledge_not_after_signal'] = bool(
        (joined['ts_knowledge'] <= joined['date']).all())
    checks['window_2_to_21'] = bool(
        ((joined['float_pos'] - joined['pos'] >= 2)
         & (joined['float_pos'] - joined['pos'] <= 21)).all())
    # controls unmarked by v1
    ctrl = (matched.select('ctrl_symbol', 'date')
            .join(s.select('symbol', 'date', 'v1'),
                  left_on=['ctrl_symbol', 'date'],
                  right_on=['symbol', 'date'], how='left'))
    checks['controls_unmarked'] = bool((~ctrl['v1'].fill_null(True)).all())
    # labels inside freeze; exit = signal pos + 5 exactly
    checks['labels_within_freeze'] = bool(
        (matched['exit5_date'] <= ev.FREEZE_END).all())
    pos_map = {d: p for p, d in enumerate(calendar.dates.to_list())}
    sample = matched.head(200)
    checks['exit5_exact_session'] = all(
        pos_map[r['date']] + 5 == pos_map[r['exit5_date']]
        for r in sample.iter_rows(named=True))
    # bootstrap determinism under seed 17
    ci1 = ev.bootstrap_ci_mean(matched['excess'].to_numpy(),
                               matched['date'].to_numpy())
    ci2 = ev.bootstrap_ci_mean(matched['excess'].to_numpy(),
                               matched['date'].to_numpy())
    checks['bootstrap_deterministic'] = ci1 == ci2
    # zero contact with 2025+
    checks['freeze_s'] = str(s['date'].max()) <= str(ev.FREEZE_END)
    metrics['smoke_checks'] = checks
    metrics['smoke_window'] = [str(lo), str(hi)]
    metrics['smoke_events'] = sub.height
    if not all(checks.values()):
        failed = [k for k, v in checks.items() if not v]
        raise AssertionError(f'smoke checks failed: {failed}')
    return metrics


# --------------------------------------------------------------------------- #
# report
# --------------------------------------------------------------------------- #
def write_report(path: Path, metrics: dict, art: dict, smoke: bool) -> None:
    lines = ['# p2r12-event-veto run report', '',
             'Frozen prereg: docs/research/exp-20260918-p2r12-event-veto-prereg.md; '
             'config: configs/experiments/p2r12-event-veto.json.', '']
    if smoke:
        lines += ['## SMOKE RUN (C01 family, 2019-01..2019-03)', '',
                  f"events: {metrics.get('smoke_events')}", '',
                  'checks: ' + json.dumps(metrics.get('smoke_checks', {})), '']
        path.write_text('\n'.join(lines), encoding='utf-8')
        return
    lines.append('## verdicts (dev -> val one-shot)')
    lines.append('| unit | dev | val |')
    lines.append('|---|---|---|')
    for unit, v in metrics['verdicts'].items():
        lines.append(f"| {unit} | {v['dev_pass']} | {v['val_pass']} |")
    lines.append('')
    for unit in ('C01', 'C02', 'C03', 'C04', 'C05', 'C06'):
        lines.append(f'## {unit}')
        for window in ('dev', 'val'):
            cells = metrics[unit].get(window, {})
            flat = {k: v for k, v in cells.items()
                    if not isinstance(v, (dict, list))}
            lines.append(f"- {window}: {json.dumps(flat, ensure_ascii=False, default=str)}")
        if unit == 'C06':
            for window in ('dev', 'val'):
                per = metrics[unit][window].get('per_year', [])
                lines.append(f'  - per_year {window}: ' +
                             json.dumps(per, ensure_ascii=False, default=str))
        lines.append('')
    lines.append('## C07 (non-judging adjunct)')
    lines.append(json.dumps(metrics['C07'], ensure_ascii=False, default=str))
    lines.append('')
    lines.append('## assembly counts')
    lines.append(json.dumps(art, ensure_ascii=False, default=str))
    path.write_text('\n'.join(lines), encoding='utf-8')


# --------------------------------------------------------------------------- #
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--smoke', action='store_true',
                    help='single-family (C01) 3-month assertions run')
    args = ap.parse_args(argv)

    root = find_repo_root()
    config = ev.json_load(root / CONFIG_PATH)
    name = 'p2r12-event-veto-smoke' if args.smoke else 'p2r12-event-veto'
    with Run(root, name, config) as run:
        calendar = ev.load_calendar(root)
        identity = ev.validate_identity(root, config)
        run.manifest['inputs_identity'] = identity
        s, frames, art = assemble(root, calendar)
        run.manifest['assembly_counts'] = art
        write_json(run.path / 'assembly_counts.json', art)
        if args.smoke:
            metrics = run_smoke(s, frames, calendar)
            write_json(run.path / 'smoke_metrics.json', metrics)
            write_report(run.path / 'report.md', metrics, art, smoke=True)
            run.metrics = {'smoke': metrics}
            print('SMOKE OK', run.path)
            return 0

        metrics, details = run_units(s, frames)
        events_dir = run.path / 'events'
        events_dir.mkdir()
        for unit, frame in (('C01', details['C01']),
                            ('C02_down', details['C02_down']),
                            ('C02_deep', details['C02_deep']),
                            ('C03', details['C03']),
                            ('C04_c_de', details['C04']),
                            ('C04_gp', details['C04_gp']),
                            ('C05_secondary', details['C05']),
                            ('C05_incidence', details['C05_incidence'])):
            frame.write_parquet(events_dir / f'{unit}.parquet')
        run.metrics = metrics
        write_json(run.path / 'metrics.json', metrics)
        write_report(run.path / 'report.md', metrics, art, smoke=False)
        print('RUN OK', run.path)
    return 0


if __name__ == '__main__':
    sys.exit(main())
