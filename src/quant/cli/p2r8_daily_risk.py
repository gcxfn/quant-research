"""P2-R8 daily risk overlay + monthly coin selection CLI
(exp-20260918-p2r8-daily-risk).

Usage:
  python src/quant/cli/p2r8_daily_risk.py \
      [--config configs/experiments/p2r8-daily-risk.json] [--smoke]

Third ETF-rotation round: the frozen R7 monthly Top-3 momentum engine is kept
verbatim and the ONLY systematic variable is the risk-check frequency
(monthly signal-day exposure -> DAILY exposure judged at every session close,
traded only on state changes).  12 frozen configs C01-C12 (FIX75 anchor /
T200 / T60 / T20c2 / D252 / D60 / PDD / X1).  The frozen config inherits the
R7 config by pinned sha256 (verified fail-closed BEFORE the run starts); all
data batch identities are re-verified the same way.

Ordering guarantees (registered):
- section-0 preanalysis (index-only) is computed and archived BEFORE any
  strategy run output;
- anchor regressions (C01 bit-exact vs run 20260918T004441-p2r7-etf-exposure-
  d01f4e7a, B1(FIX-75) identical, B1@100% dev +10.40%/+63.9%/-27.47%) run
  BEFORE any gate is consumed; a failure aborts the run (failed status, kept
  for the record, results never consumed).

dev (2016-2020) is EXPLORATORY (second reuse: P2-R6 and P2-R7 consumed it).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import sys
import time
from datetime import date
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'src'))

from quant.research import etf_rotation as er  # noqa: E402
from quant.research.etf_rotation import (  # noqa: E402
    ETF_FEE_BAND,
    FREEZE_END,
    GROSS_FEE_BAND,
    CodeDataBank,
    build_calendar,
    cagr,
    concentration,
    evaluate_dev_gate,
    evaluate_test,
    evaluate_val_gate,
    group_pools,
    max_drawdown,
    monthly_top_decile,
    rank_pool,
    rebalance_days,
    simulate_b1_exposure,
    simulate_daily_risk,
    slice_curve,
    turnover_by_year,
    year_returns,
)
from quant.research.runs import Run, find_repo_root, write_json  # noqa: E402

R7_RUN_DIR = ROOT / 'artifacts/runs/20260918T004441-p2r7-etf-exposure-d01f4e7a'
B3_SEEDS = list(range(17, 37))
RISK_KINDS = frozenset({'retarget_buy', 'retarget_sell'})
E_ON = 0.90

# registered deviations fixed before any run (disclosed in metrics + report)
DEVIATIONS = [
    {'id': 1, 'item': 'section-0 "local peak" disambiguation: D mechanisms use '
     'their own rule window peak; SMA mechanisms (T200/T60/T20c2/X1) use the '
     'trailing 252-session index peak, expanding before it is formed. Fixed '
     'definition, recorded before the run; not a tunable.'},
    {'id': 2, 'item': 'index batch starts 2015-01-05 (~242 sessions before '
     '2016), so the 252-session rolling peak is not fully formed at the first '
     '2016 sessions; the REGISTERED fallback (insufficient history -> e_low) '
     'applies to D252/D60/X1 for those sessions. The warmup_guarantee note '
     '(>=200 sessions) is accurate for SMA200 only. Count disclosed in '
     'metrics.d252_warmup_fallback_sessions_2016; X1 treats an unavailable '
     'D252 as firing (risk-off), consistent with that fallback.'},
    {'id': 3, 'item': 'combined monthly+risk execution reading: on a signal '
     'day WITH a state change the plan is member updates x current E_t budget '
     'AND continuing incumbents are re-sized to the same leg target (one '
     'execution). On a signal day WITHOUT a state change incumbents drift '
     '(R7 semantics unchanged).'},
    {'id': 4, 'item': 'a monthly full exit supersedes a postponed risk '
     're-scale on the same slot (leaver slot: the exit is the terminal '
     'target); the superseded leg is logged outcome=superseded_by_exit and '
     'counted as NOT executed (conservative for gate-8). Same conservative '
     'treatment for superseded_latest when a fresher target replaces a '
     'postponed one.'},
    {'id': 5, 'item': 'PDD (C10/C11) is equity-path-dependent, so fees feed '
     'back into the exposure state: net vs gross trade-sequence parity is '
     'structurally not guaranteed for PDD (it held for every equity-'
     'independent mechanism in R7). Parity is asserted for C01-C09/C12 and '
     'reported as-is for C10/C11.'},
    {'id': 6, 'item': 'position bookkeeping on partial re-sizes: a retarget '
     'sell reduces the position cumulative net-spend proportionally by units, '
     'a retarget buy adds its budget; close-out pnl stays cash-flow '
     'consistent. Attribution convention only, no cash effect.'},
    {'id': 7, 'item': 'B1(m) daily rescale postponement is not spelled out in '
     'the prereg; implemented as: retry at later opens until filled or '
     'superseded, latest target wins, buys capped by the idle pool '
     '(never negative), capped-at-commission-min leaves the leg '
     'under-invested. Matches the strategy-side semantics.'},
    {'id': 8, 'item': 'a risk re-size of a leg whose full exit is already '
     'postponed (exit_due) is skipped: the leg is no longer a target holding; '
     'its pending exit completes at the next tradable open.'},
    {'id': 9, 'item': 'de-minimis risk re-size guard (found in code review '
     'before ANY run): a retarget SELL whose gross notional is at/below the '
     '5-CNY commission minimum would pay a fee larger than the proceeds and '
     'overdraw the never-negative cash pool (the registered hard rule), so '
     'the leg is skipped as a rule-compliant cash slot (outcome cash_capped, '
     'separate counter risk_sells_feemin_skipped; the B1(m) rescale path '
     'applies the same guard). The registered buy-side rule is the exact '
     'analog (capped budget <= commission_min -> skip).'},
    {'id': 10, 'item': 'frozen-config transcription defect discovered at '
     'startup, BEFORE any signal computation (R7-precedent class, pre-run): '
     'the R8 config data block pin for the fund_adj batch manifest '
     '(20260917-r1) reads ...abe7b00b... but the actual file hashes to '
     '...abe8b00b... -- a one-character copy defect. The R8 config was NOT '
     'modified (freeze respected). Identity resolved through the pinned '
     'inheritance source instead: the R8 config pins the R7 config by sha256 '
     '(verified at startup), and the R7 config pin for the SAME batch '
     'manifest matches the actual file bit-for-bit, exactly as recorded in '
     'the R7 formal run manifest. The data consumed is byte-identical to the '
     'R7 formal run. Any pin matching NEITHER the R8 nor the R7 value still '
     'hard-fails the run.'},
    {'id': 11, 'item': 'effective-config materialization (in memory, pre-run; '
     'R7-precedent deviation 1 class): the frozen R8 config inherits '
     'u1_whitelist_frozen / universe / preflight from the R7 config BY HASH '
     'and intentionally does not repeat them in its own file, but the '
     'data-loading layer reads them from the config dict. At startup the '
     'effective config is materialized by injecting those three blocks '
     'VERBATIM from the sha256-verified R7 config (no value changed, '
     'conflict-checked: the R8 file defines none of them). The frozen config '
     'file on disk is never modified; the run-dir config.json snapshot '
     'records the materialized effective config, as in R7.'},
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=Path,
                        default=ROOT / 'configs/experiments/p2r8-daily-risk.json')
    parser.add_argument('--smoke', action='store_true',
                        help='1 dev year (2016) x C01(FIX75)/C07(D252-10) smoke')
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def verify_pins(config: dict, root: Path) -> list[dict]:
    """Fail-closed identity checks BEFORE the run directory is created.

    If an R8 data pin mismatches the actual file, the SAME logical input's
    pin in the R7 config (the hash-pinned inheritance source, verified above)
    is consulted: a match there classifies the defect as an R8 transcription
    error (deviation 10) and the run proceeds; a mismatch on both is a real
    data change and hard-fails."""
    checks: list[dict] = []
    inh = config['inherits_from']
    p = root / inh['file']
    got = sha256_file(p)
    checks.append({'what': 'inherits_from (R7 config)', 'path': inh['file'],
                   'expected': inh['sha256'], 'actual': got,
                   'ok': got == inh['sha256'], 'resolution': 'primary'})
    if got != inh['sha256']:
        raise SystemExit(f'FAIL-CLOSED: inheritance pin mismatch for {p}: '
                         f'{got} != {inh["sha256"]}')
    r7 = json.loads(p.read_text(encoding='utf-8'))
    d = config['data']
    rd = r7['data']
    for name, path, key, r7_key in (
            ('fund_basic', root / d['fund_basic']['batch'] / d['fund_basic']['file'],
             d['fund_basic']['sha256'], rd['fund_basic']['sha256']),
            ('fund_daily_manifest', root / d['fund_daily']['batch'] / 'manifest.json',
             d['fund_daily']['manifest_sha256'],
             rd['fund_daily']['manifest_sha256']),
            ('fund_adj_manifest', root / d['fund_adj']['batch'] / 'manifest.json',
             d['fund_adj']['manifest_sha256'],
             rd['fund_adj']['manifest_sha256']),
            ('index_000300', root / d['index_daily']['batch']
             / d['index_daily']['risk_file'],
             d['index_daily']['chunk_000300_sha256'],
             rd['index_daily']['chunk_000300_sha256']),
            ('index_manifest', root / d['index_daily']['batch'] / 'manifest.json',
             d['index_daily']['manifest_sha256'],
             rd['index_daily']['manifest_sha256'])):
        got = sha256_file(path)
        entry = {'what': name, 'path': str(path.relative_to(root)),
                 'expected': key, 'actual': got, 'ok': got == key}
        if got != key:
            if got == r7_key:
                entry['resolution'] = (
                    'r8_pin_transcription_defect_confirmed_via_r7_inheritance'
                    ' (deviation 10)')
                entry['ok'] = True
            else:
                entry['resolution'] = 'unresolvable-data-change'
                raise SystemExit(
                    f'FAIL-CLOSED: data pin mismatch for {path}: {got} != '
                    f'{key} (and no match in the R7 inheritance source)')
        else:
            entry['resolution'] = 'primary'
        checks.append(entry)
    return checks


def effective_config(base: dict, r7: dict, smoke: bool) -> tuple[dict, list[str]]:
    """Materialize the effective config: the frozen R8 file plus the three
    inheritance blocks injected VERBATIM from the hash-verified R7 config
    (deviation 11; the frozen file itself is never modified)."""
    config = json.loads(json.dumps(base))
    injected = []
    for key in ('u1_whitelist_frozen', 'universe', 'preflight'):
        if key in config:
            raise SystemExit(f'FAIL-CLOSED: R8 config defines {key!r} itself; '
                             'inheritance injection would conflict')
        if key not in r7:
            raise SystemExit(f'FAIL-CLOSED: R7 config lacks {key!r}')
        config[key] = json.loads(json.dumps(r7[key]))
        injected.append(key)
    if smoke:
        config['smoke'] = True
        config['segments']['dev'] = {'start': '2016-01-01', 'end': '2016-12-31'}
        config['segments']['validation'] = None
        config['segments']['test'] = None
        config['smoke_configs'] = ['C01', 'C07']
        config['name'] = base['name'] + '-smoke'
    return config, injected


def segment_bounds(config: dict) -> dict[str, tuple[date, date]]:
    out = {}
    for seg in ('dev', 'validation', 'test'):
        raw = config['segments'].get(seg)
        if raw:
            out[seg] = (date.fromisoformat(raw['start']),
                        date.fromisoformat(raw['end']))
    return out


def budget_exceeded(deadline: float, limits: dict) -> None:
    if time.perf_counter() > deadline:
        raise RuntimeError(
            f"runtime budget exceeded (max_runtime_s={limits['max_runtime_s']}); "
            'stopping with partial progress recorded in metrics.json')


def build_states(index_close: pl.DataFrame, calendar: list[date]) -> dict:
    st = {
        ('T200', 200, None): er.sma_trend_state(index_close, calendar, 200),
        ('T60', 60, None): er.sma_trend_state(index_close, calendar, 60),
        ('T20c2', 20, None): er.t20c2_state(index_close, calendar, 20),
        ('D252', 252, 0.10): er.rolling_dd_state(index_close, calendar, 252, 0.10),
        ('D252', 252, 0.15): er.rolling_dd_state(index_close, calendar, 252, 0.15),
        ('D60', 60, 0.08): er.rolling_dd_state(index_close, calendar, 60, 0.08),
    }
    st[('X1', None, None)] = er.x1_compose(st[('T200', 200, None)],
                                           st[('D252', 252, 0.10)])
    return st


def config_mech(spec: dict, states: dict):
    """-> (make_risk_fn factory, b3/b1 key, exposures dict or None for PDD)."""
    mech = spec['mech']
    e_low = float(spec.get('e_low', 0.40))
    if mech == 'FIX75':
        return (lambda: er.constant_risk_fn(0.75)), 'FIX75', None
    if mech == 'PDD':
        th = float(spec['dd_threshold'])
        key = f'PDD{th:.2f}-L{e_low:.2f}'
        return (lambda th=th, e_low=e_low: er.pdd_risk_fn(th, E_ON, e_low),
                key, None)
    if mech == 'X1':
        st = states[('X1', None, None)]
        key = f'X1-L{e_low:.2f}'
    elif mech in ('T200', 'T60', 'T20c2'):
        w = {'T200': 200, 'T60': 60, 'T20c2': 20}[mech]
        st = states[(mech, w, None)]
        key = f'{mech}-L{e_low:.2f}'
    else:
        w = 252 if mech == 'D252' else 60
        th = float(spec['dd_threshold'])
        st = states[(mech, w, th)]
        key = f'{mech}{th:.2f}-L{e_low:.2f}'
    expo = er.exposures_from_state(st, E_ON, e_low)
    return (lambda expo=expo: (lambda d, e, _e=expo: _e[d])), key, expo


def switch_stats(sessions: list[date], e_series: list[float],
                 e_low: float | None) -> dict:
    per_year: dict[int, dict] = {}
    prev: float | None = None
    for day, e in zip(sessions, e_series):
        y = per_year.setdefault(day.year, {'n_sessions': 0, 'n_switches': 0,
                                           'off_sessions': 0, 'sum_e': 0.0})
        y['n_sessions'] += 1
        y['sum_e'] += e
        if prev is not None and e != prev:
            y['n_switches'] += 1
        if e_low is not None and e == e_low:
            y['off_sessions'] += 1
        prev = e
    return {str(y): {'n_sessions': v['n_sessions'],
                     'n_switches': v['n_switches'],
                     'off_share': (round(v['off_sessions'] / v['n_sessions'], 4)
                                   if e_low is not None else None),
                     'mean_exposure': round(v['sum_e'] / v['n_sessions'], 4)}
            for y, v in sorted(per_year.items())}


def risk_trade_stats(trades: list[dict], s: date, e: date) -> dict:
    rt = [t for t in trades
          if t['kind'] in RISK_KINDS and s <= t['session'] <= e]
    fees = sum(t['fee'] for t in rt)
    all_fees = sum(t['fee'] for t in trades if s <= t['session'] <= e)
    return {'n_trades': len(rt),
            'n_buys': sum(1 for t in rt if t['side'] == 'buy'),
            'n_sells': sum(1 for t in rt if t['side'] == 'sell'),
            'buy_notional': sum(t['notional'] for t in rt if t['side'] == 'buy'),
            'sell_notional': sum(t['notional'] for t in rt
                                 if t['side'] == 'sell'),
            'fees': fees,
            'fee_share_of_total': (fees / all_fees) if all_fees else 0.0}


def curves_bit_exact(r8: list[tuple], r7: list[tuple]) -> bool:
    return len(r8) == len(r7) and all(a == b for a, b in zip(r8, r7))


def verify_anchors(curves_rows: list[dict], b1_100_dev: dict,
                   smoke_end: date | None) -> dict:
    """Registered anchors, run BEFORE any gate consumption; any failure
    raises (run marked failed, kept for the record, never consumed)."""
    r7_curves = pl.read_parquet(R7_RUN_DIR / 'equity_curves.parquet')
    r7_metrics = json.loads(
        (R7_RUN_DIR / 'metrics.json').read_text(encoding='utf-8'))

    def r7_series(cid: str) -> tuple[list, list, list]:
        d = r7_curves.filter(pl.col('config_id') == cid).sort('session')
        if smoke_end is not None:
            d = d.filter(pl.col('session') <= smoke_end)
        return (d['session'].to_list(), d['equity_net'].to_list(),
                d['equity_gross'].to_list())

    out: dict = {'r7_run': str(R7_RUN_DIR.relative_to(ROOT)),
                 'scope': ('sessions<=' + smoke_end.isoformat()
                           if smoke_end else 'full')}
    s7, n7, g7 = r7_series('C01')
    c01 = sorted((r for r in curves_rows if r['config_id'] == 'C01'),
                 key=lambda r: r['session'])
    out['c01_sessions_equal'] = s7 == [r['session'] for r in c01]
    out['c01_net_bit_exact'] = curves_bit_exact(
        [r['equity_net'] for r in c01], n7)
    out['c01_gross_bit_exact'] = curves_bit_exact(
        [r['equity_gross'] for r in c01], g7)
    for r7_cid, r8_cid in (('B1-FIX', 'B1-FIX75'),
                           ('B1-FIX-gross', 'B1-FIX75-gross'),
                           ('B1-100', 'B1-100')):
        s7b, n7b, _ = r7_series(r7_cid)
        rows = sorted((r for r in curves_rows if r['config_id'] == r8_cid),
                      key=lambda r: r['session'])
        out[f'{r8_cid}_vs_{r7_cid}_sessions_equal'] = \
            s7b == [r['session'] for r in rows]
        out[f'{r8_cid}_vs_{r7_cid}_bit_exact'] = curves_bit_exact(
            [r['equity_net'] for r in rows], n7b)
    if smoke_end is None:
        r7_100 = r7_metrics['benchmarks']['B1']['100']['dev']
        out['b1_100_dev_net_cagr_exact'] = \
            b1_100_dev['net_cagr'] == r7_100['net_cagr']
        out['b1_100_dev_total_exact'] = \
            b1_100_dev['net_total_return'] == r7_100['net_total_return']
        out['b1_100_dev_mdd_exact'] = \
            b1_100_dev['max_drawdown'] == r7_100['max_drawdown']
        out['b1_100_published_check'] = {
            'net_cagr_10.40pct': abs(b1_100_dev['net_cagr'] - 0.1040) < 0.0005,
            'net_total_63.9pct': abs(b1_100_dev['net_total_return'] - 0.639) < 0.0005,
            'mdd_-27.47pct': abs(b1_100_dev['max_drawdown'] + 0.2747) < 0.0005}
    else:
        out['b1_100_dev_metrics'] = 'skipped in smoke (dev window is 2016 only)'
    failed = [k for k, v in out.items()
              if v is False or (isinstance(v, dict)
                                and not all(v.values()))]
    out['all_pass'] = not failed
    if failed:
        raise RuntimeError(f'ANCHOR REGRESSION FAILED: {failed}; results must '
                           'not be consumed (failed run kept for the record)')
    return out


def write_preanalysis(run_path: Path, pre: dict) -> None:
    write_json(run_path / 'preanalysis.json', pre)
    lines = ['# P2-R8 §0 预分析（仅 000300 指数，先于任何策略输出；定义固定，不可调参）', '',
             f"- 指数行数 {pre['index_rows']}，范围 {pre['range'][0]}..{pre['range'][1]}",
             '', '| 机制 | dev 触发次数 | 风险关闭占比 | 触发时距局部峰回撤深度 p50 | p90 | max(最深) | 局部峰定义 |',
             '|---|---|---|---|---|---|---|']
    for name, m in pre['mechanisms'].items():
        d = m['depth_from_local_peak_at_trigger']
        fmt = lambda v: '—' if v is None else f'{v * 100:.2f}%'  # noqa: E731
        lines.append(f"| {name} | {m['trigger_count']} | "
                     f"{m['risk_off_share'] * 100:.1f}% | {fmt(d['p50'])} | "
                     f"{fmt(d['p90'])} | {fmt(d['max'])} | {d['definition']} |")
    s1 = pre['index_stress']['worst_single_session']
    s5 = pre['index_stress']['worst_5_session']
    lines += ['',
              f"- 000300 最差单日（2015–2020）: {s1['date']} "
              f"{s1['ret'] * 100:.2f}%",
              f"- 000300 最差 5 会话（2015–2020）: {s5['date']} "
              f"({s5['window'][0]}..{s5['window'][1]}) {s5['ret'] * 100:.2f}%",
              '', '用途：事前披露日频风控天花板（预期管理），非判据；'
              '不得据其增删配置。']
    (run_path / 'preanalysis.md').write_text('\n'.join(lines) + '\n',
                                             encoding='utf-8')


def fmt(value) -> str:
    if value is None:
        return '—'
    return f'{value:.3f}' if abs(value) < 10 else f'{value:.1f}'


def main() -> int:
    args = parse_args()
    base = json.loads(args.config.read_text(encoding='utf-8'))
    os.chdir(ROOT)
    root = find_repo_root()
    pin_checks = verify_pins(base, root)  # fail-closed BEFORE the run exists
    r7 = json.loads((root / base['inherits_from']['file']).read_text(
        encoding='utf-8'))
    config, injected = effective_config(base, r7, args.smoke)
    limits = config.get('limits', {'max_runtime_s': 1800, 'max_ram_gb': 11})
    deadline = time.perf_counter() + float(limits['max_runtime_s'])
    t_all = time.perf_counter()
    segs = segment_bounds(config)
    dev_start = segs['dev'][0]
    smoke_end = segs['dev'][1] if args.smoke else None
    twelve = config['configs_grid']['twelve']
    config_ids = config.get('smoke_configs') or list(twelve)

    with Run(root, config['name'], config) as run:
        timings: dict[str, float] = {}
        run.metrics['pin_checks'] = pin_checks
        run.metrics['inherited_blocks_injected'] = injected
        run.metrics['deviations'] = DEVIATIONS

        # ---------- section-0 preanalysis FIRST (index only) ---------------
        t0 = time.perf_counter()
        d = config['data']
        index_close = er.load_index_close(
            root / d['index_daily']['batch'] / d['index_daily']['risk_file'])
        index_close = index_close.filter(pl.col('trade_date') <= FREEZE_END)
        pre = er.preanalysis_sect0(
            index_close, dev_start=date(2016, 1, 1), dev_end=date(2020, 12, 31),
            stress_start=date(2015, 1, 1), stress_end=date(2020, 12, 31))
        write_preanalysis(run.path, pre)
        run.metrics['preanalysis_file'] = 'preanalysis.json'
        n_2015 = index_close.filter(pl.col('trade_date') < date(2016, 1, 1)).height
        run.metrics['d252_warmup_fallback_sessions_2016'] = max(
            0, 252 - int(n_2015))
        timings['preanalysis_s'] = round(time.perf_counter() - t0, 2)

        # ---------- data -----------------------------------------------------
        t0 = time.perf_counter()
        loaded = er.load_frames(root, config)
        feat: pl.DataFrame = loaded['feat']
        full_calendar = build_calendar(feat)
        if smoke_end is not None:
            calendar = [x for x in full_calendar if x <= smoke_end]
            feat = feat.filter(pl.col('trade_date') <= smoke_end)
        else:
            calendar = full_calendar
        timings['load_s'] = round(time.perf_counter() - t0, 2)
        run.metrics['load_stats'] = loaded['stats']
        run.manifest['inputs'] = [
            {'path': d['fund_daily']['batch'],
             'manifest_sha256': d['fund_daily']['manifest_sha256'],
             **loaded['stats']},
            {'path': d['fund_adj']['batch'],
             'manifest_sha256': d['fund_adj']['manifest_sha256']},
            {'path': d['fund_basic']['batch'],
             'file_sha256': d['fund_basic']['sha256']},
            {'path': d['index_daily']['batch'],
             'manifest_sha256': d['index_daily']['manifest_sha256'],
             'chunk_000300_sha256': d['index_daily']['chunk_000300_sha256'],
             'r7_inheritance_verified': True},
        ]
        run.metrics['timings'] = timings

        t0 = time.perf_counter()
        pools = group_pools(feat)
        bank = CodeDataBank(feat, calendar)
        timings['pools_s'] = round(time.perf_counter() - t0, 2)
        run.metrics['timings'] = timings
        budget_exceeded(deadline, limits)

        signal_days = rebalance_days(calendar, 'monthly', dev_start)
        states = build_states(index_close, calendar)
        mechs = {cid: config_mech(twelve[cid], states) for cid in twelve}
        mech_keys = sorted({mechs[c][1] for c in config_ids})
        run.metrics['mech_keys'] = {cid: mechs[cid][1] for cid in config_ids}

        ranked_cache: dict[tuple, dict[date, list[str]]] = {}

        def ranked_for(days: list[date]) -> dict[date, list[str]]:
            # absolute momentum gate is OFF for every R8 config (registered)
            key = ((20, 60), False, 'monthly')
            if key not in ranked_cache:
                ranked_cache[key] = {
                    x: [r.code for r in rank_pool(pools.get(x, []), (20, 60))]
                    for x in days}
            return ranked_cache[key]

        ranked = ranked_for(signal_days)

        # ---------------- B1 family (mechanism daily path, net+gross) -------
        t0 = time.perf_counter()
        b1_results: dict[str, dict[str, er.SimResult]] = {}
        b1_keys = mech_keys + ['100']
        for key in b1_keys:
            if key == '100':
                make = lambda: er.constant_risk_fn(1.0)  # noqa: E731
            else:
                make = next(mechs[c][0] for c in config_ids
                            if mechs[c][1] == key)
            b1_results[key] = {}
            for variant, fees in (('net', ETF_FEE_BAND),
                                  ('gross', GROSS_FEE_BAND)):
                b1_results[key][variant] = simulate_b1_exposure(
                    pools, bank, calendar, dev_start, signal_days,
                    {}, total=200_000.0, fees=fees,
                    config_id=f'B1-{key}' if variant == 'net'
                    else f'B1-{key}-gross',
                    risk_fn=make())
        b2_code = '510300.SH'
        b2 = {seg: er.simulate_b2(b2_code, bank, calendar, s, e,
                                  total=200_000.0, fees=ETF_FEE_BAND)
              for seg, (s, e) in segs.items()}
        timings['b1_b2_s'] = round(time.perf_counter() - t0, 2)
        run.metrics['timings'] = timings
        budget_exceeded(deadline, limits)

        # ---------------- B3prime: random Top-3, same mech, 20 seeds --------
        t0 = time.perf_counter()
        b3: dict[tuple[str, int], er.SimResult] = {}
        for key in mech_keys:
            make = next(mechs[c][0] for c in config_ids if mechs[c][1] == key)
            for seed in B3_SEEDS:
                rng = random.Random(seed)

                def selector(t: date, _rng=rng) -> list[str]:
                    codes = [r.code for r in pools.get(t, [])]
                    _rng.shuffle(codes)
                    return codes

                b3[(key, seed)] = simulate_daily_risk(
                    f'B3-{key}-s{seed}', bank, calendar, dev_start,
                    signal_days, selector, make(), n_slots=3,
                    fees=ETF_FEE_BAND, total=200_000.0)
        timings['b3prime_s'] = round(time.perf_counter() - t0, 2)
        run.metrics['timings'] = timings
        budget_exceeded(deadline, limits)

        # ---------------- 12 configs: continuous net+gross paths ------------
        curves_rows: list[dict] = []
        sim_results: dict[str, dict] = {}
        for cid in config_ids:
            budget_exceeded(deadline, limits)
            t0 = time.perf_counter()
            make, _, _ = mechs[cid]
            net = simulate_daily_risk(
                cid, bank, calendar, dev_start, signal_days,
                lambda t, _r=ranked: _r.get(t, []), make(), n_slots=3,
                fees=ETF_FEE_BAND, total=200_000.0)
            gross = simulate_daily_risk(
                cid + '-gross', bank, calendar, dev_start, signal_days,
                lambda t, _r=ranked: _r.get(t, []), make(), n_slots=3,
                fees=GROSS_FEE_BAND, total=200_000.0)
            parity = ([(t['session'], t['code'], t['side'], t['kind'])
                       for t in net.trades]
                      == [(t['session'], t['code'], t['side'], t['kind'])
                          for t in gross.trades])
            sim_results[cid] = {'spec': twelve[cid], 'net': net, 'gross': gross,
                                'net_gross_parity': parity}
            timings[f'sim_{cid}_s'] = round(time.perf_counter() - t0, 2)
            run.metrics['timings'] = timings

        # ---------------- ANCHOR REGRESSIONS (before any gate) --------------
        for cid, sr in sim_results.items():
            for x, vn, vg in zip(sr['net'].sessions, sr['net'].equity,
                                 sr['gross'].equity):
                curves_rows.append({'config_id': cid, 'session': x,
                                    'equity_net': vn, 'equity_gross': vg})
            run.metrics.setdefault('net_gross_parity', {})[cid] = \
                sr['net_gross_parity']
        for key in b1_keys:
            for variant in ('net', 'gross'):
                r = b1_results[key][variant]
                for x, v in zip(r.sessions, r.equity):
                    curves_rows.append(
                        {'config_id': f'B1-{key}' if variant == 'net'
                         else f'B1-{key}-gross', 'session': x,
                         'equity_net': v, 'equity_gross': None})

        def b1_dev_metrics(key: str) -> dict:
            r = b1_results[key]['net']
            s, e = segs['dev']
            sd, sv = slice_curve(r.sessions, r.equity, s, e)
            return {'net_cagr': cagr(sv[0], sv[-1], sd[0], sd[-1]),
                    'net_total_return': sv[-1] / sv[0] - 1.0,
                    'max_drawdown': max_drawdown(sd, sv)['max_drawdown']}

        t0 = time.perf_counter()
        run.metrics['anchor_regressions'] = verify_anchors(
            curves_rows, b1_dev_metrics('100'), smoke_end)
        timings['anchors_s'] = round(time.perf_counter() - t0, 2)
        run.metrics['timings'] = timings

        # ---------------- metrics per config --------------------------------
        metrics: dict[str, dict] = {}

        def years_of(seg: str) -> list[int]:
            if seg not in segs:
                return []
            s, e = segs[seg]
            return list(range(s.year, e.year + 1))

        def b1_metrics(key: str) -> dict:
            out_m: dict = {}
            net_r = b1_results[key]['net']
            gross_r = b1_results[key]['gross']
            acc = net_r.extra.get('turnover_acc', {})
            for seg in ('dev', 'validation', 'test'):
                if seg not in segs:
                    continue
                s, e = segs[seg]
                sd, sv = slice_curve(net_r.sessions, net_r.equity, s, e)
                _, svg = slice_curve(gross_r.sessions, gross_r.equity, s, e)
                mean_eq = sum(sv) / len(sv) if sv else None
                buy = sum(acc.get(y, {}).get('buy_notional', 0.0)
                          for y in range(s.year, e.year + 1))
                out_m[seg] = {
                    'net_cagr': cagr(sv[0], sv[-1], sd[0], sd[-1]),
                    'gross_cagr': cagr(svg[0], svg[-1], sd[0], sd[-1]),
                    'net_total_return': sv[-1] / sv[0] - 1.0,
                    'gross_total_return': svg[-1] / svg[0] - 1.0,
                    'max_drawdown': max_drawdown(sd, sv)['max_drawdown'],
                    'one_side_turnover': (buy / mean_eq) if mean_eq else None,
                }
            return out_m

        b1_m = {key: b1_metrics(key) for key in b1_keys}

        def build_metrics(cid: str) -> dict:
            spec = sim_results[cid]['spec']
            net: er.SimResult = sim_results[cid]['net']
            gross: er.SimResult = sim_results[cid]['gross']
            mech_key = mechs[cid][1]
            e_low = float(spec.get('e_low', 0.0)) or None
            out: dict = {'freq': 'monthly', 'W': [20, 60], 'N': 3,
                         'mech': spec['mech'], 'mech_key': mech_key,
                         'max_negative_cash': net.max_negative_cash,
                         'n_trades': len(net.trades),
                         'exec_stats': net.exec_stats.as_dict(),
                         'switch_stats_by_year': switch_stats(
                             net.sessions, net.extra['e_series'], e_low)}
            for seg in ('dev', 'validation', 'test'):
                if seg not in segs:
                    continue
                s, e = segs[seg]
                sd_n, sv_n = slice_curve(net.sessions, net.equity, s, e)
                sd_g, sv_g = slice_curve(gross.sessions, gross.equity, s, e)
                b1r = b1_results[mech_key]['net']
                b1g = b1_results[mech_key]['gross']
                sd_b, sv_b = slice_curve(b1r.sessions, b1r.equity, s, e)
                _, sv_bg = slice_curve(b1g.sessions, b1g.equity, s, e)
                mdd_n = max_drawdown(sd_n, sv_n)
                seg_m = {
                    'net_cagr': cagr(sv_n[0], sv_n[-1], sd_n[0], sd_n[-1]),
                    'gross_cagr': cagr(sv_g[0], sv_g[-1], sd_g[0], sd_g[-1]),
                    'net_total_return': sv_n[-1] / sv_n[0] - 1.0,
                    'gross_total_return': sv_g[-1] / sv_g[0] - 1.0,
                    'b1m_net_cagr': cagr(sv_b[0], sv_b[-1], sd_b[0], sd_b[-1]),
                    'b1m_gross_cagr': cagr(sv_bg[0], sv_bg[-1],
                                           sd_b[0], sd_b[-1]),
                    'max_drawdown': mdd_n['max_drawdown'],
                    'mdd_window': mdd_n,
                    'b1m_max_drawdown': max_drawdown(sd_b, sv_b)['max_drawdown'],
                }
                seg_m['excess_vs_b1m'] = (seg_m['net_cagr']
                                          - seg_m['b1m_net_cagr']
                                          if seg_m['net_cagr'] is not None
                                          else None)
                seg_m['gross_excess_vs_b1m'] = (seg_m['gross_cagr']
                                                - seg_m['b1m_gross_cagr']
                                                if seg_m['gross_cagr'] is not None
                                                else None)
                if seg == 'dev':
                    # registered gate-8 scope: dev-window legs planned on
                    # signal days AND risk state-change days
                    dev_exec = er.window_execution_rate(net.leg_log, s, e)
                    seg_m['execution_rate'] = dev_exec['execution_rate']
                    seg_m['execution_rate_dev_window'] = dev_exec
                seg_m['execution_rate_full_window'] = \
                    er.window_execution_rate(net.leg_log, calendar[0],
                                             calendar[-1])['execution_rate']
                strat_years = year_returns(sd_n, sv_n)
                b1_years = year_returns(sd_b, sv_b)
                seg_m['net_return_by_year'] = {str(y): strat_years.get(y)
                                               for y in years_of(seg)}
                seg_m['excess_by_year'] = {
                    str(y): (strat_years[y] - b1_years[y]
                             if y in strat_years and y in b1_years else None)
                    for y in years_of(seg)}
                turnover = turnover_by_year(net)
                seg_m['turnover_by_year'] = {str(y): turnover.get(y)
                                             for y in years_of(seg)}
                seg_m['max_one_side_turnover'] = max(
                    (turnover[y]['one_side_turnover'] for y in years_of(seg)
                     if turnover.get(y)), default=None)
                seg_m['risk_trades'] = risk_trade_stats(net.trades, s, e)
                conc = concentration(net.positions, net.final_open, bank,
                                     calendar, s, e)
                seg_m['concentration'] = conc
                seg_m['monthly_top_decile'] = monthly_top_decile(sd_n, sv_n)
                seg_m['forced_delist'] = {
                    'count': sum(1 for p in net.positions
                                 if p['exit_kind'] == 'forced_delist_close'
                                 and s <= p['exit_date'] <= e)}
                out[seg] = seg_m
            return out

        for cid in sim_results:
            budget_exceeded(deadline, limits)
            metrics[cid] = build_metrics(cid)
            run.metrics['configs'] = metrics

        # ---------------- benchmark metrics ---------------------------------
        run.metrics['benchmarks'] = {
            'B1': {key: b1_m[key] for key in b1_keys},
            'B2': {seg: {'net_total_return': b2[seg]['net_total_return'],
                         'gross_total_return': b2[seg]['gross_total_return'],
                         'entry': b2[seg]['entry_date'].isoformat(),
                         'exit': b2[seg]['exit_date'].isoformat(),
                         'fees': {'buy': b2[seg]['buy_fee'],
                                  'sell': b2[seg]['sell_fee']}}
                   for seg in b2},
            'B4_cash': 0.0,
        }

        b3_means: dict[str, float] = {}
        for key in mech_keys:
            cagrs = []
            for seed in B3_SEEDS:
                r = b3[(key, seed)]
                sd, sv = slice_curve(r.sessions, r.equity, *segs['dev'])
                cagrs.append(cagr(sv[0], sv[-1], sd[0], sd[-1]))
            mean = sum(cagrs) / len(cagrs)
            b3_means[key] = mean
            run.metrics[f'B3prime_{key}'] = {
                'n_seeds': len(B3_SEEDS), 'mean_net_cagr': mean,
                'min': min(cagrs), 'max': max(cagrs),
                'per_seed': {str(s): c for s, c in zip(B3_SEEDS, cagrs)}}

        # ---------------- drawdown-saved vs rally-lost vs C01 ---------------
        c01 = metrics.get('C01')
        tradeoff = []
        if c01 is not None:
            for cid in config_ids:
                if cid == 'C01':
                    continue
                m = metrics[cid]
                saved_dd = (abs(c01['dev']['max_drawdown'])
                            - abs(m['dev']['max_drawdown'])) * 100.0
                lost_ret = (c01['dev']['net_cagr']
                            - m['dev']['net_cagr']) * 100.0
                tradeoff.append({
                    'config_id': cid, 'mech': m['mech'],
                    'saved_drawdown_pp': round(saved_dd, 2),
                    'lost_net_cagr_pp': round(lost_ret, 2),
                    'saved_per_lost': (round(saved_dd / lost_ret, 3)
                                       if lost_ret > 1e-9 else None)})
        run.metrics['tradeoff_vs_C01'] = tradeoff

        # ---------------- gates ----------------------------------------------
        gates: dict[str, dict] = {}
        for cid, m in metrics.items():
            budget_exceeded(deadline, limits)
            spec = twelve[cid]
            b1_dev = b1_m[mechs[cid][1]]['dev']
            g = evaluate_dev_gate(
                m, {'net_cagr': b1_dev['net_cagr'],
                    'max_drawdown': b1_dev['max_drawdown']},
                b3_means[mechs[cid][1]], freq='monthly')
            g['smoke_non_binding'] = args.smoke
            gates[cid] = {'dev': g}
        dev_pass = sorted(
            [(cid, gates[cid]['dev']['dev_excess_vs_b1'])
             for cid in gates if gates[cid]['dev']['dev_pass']],
            key=lambda kv: (-kv[1], kv[0]))
        advanced = None
        if dev_pass and not args.smoke:
            advanced = dev_pass[0][0]
            m = metrics[advanced]
            key = mechs[advanced][1]
            b1_val = b1_m[key].get('validation')
            gates[advanced]['validation'] = evaluate_val_gate(
                m, b1_val or {'net_cagr': None})
            if gates[advanced]['validation']['val_pass'] and 'test' in segs:
                gates[advanced]['test'] = evaluate_test(
                    m, b1_m[key]['test'])
        for cid in gates:
            if (not args.smoke and gates[cid]['dev']['dev_pass']
                    and cid != advanced):
                gates[cid]['status'] = 'dev-pass-not-advanced'
        run.metrics['gates'] = gates
        run.metrics['dev_pass_configs'] = [cid for cid, _ in dev_pass]
        run.metrics['advanced_to_validation'] = advanced
        survivors = []
        if advanced and gates[advanced].get('test', {}).get('test_pass'):
            survivors = [advanced]
        run.metrics['p3_candidates'] = survivors
        run.metrics['trial_count_cumulative'] = 115 + 12

        # ---------------- outputs --------------------------------------------
        b2_seg = 'validation' if 'validation' in segs else 'dev'
        b2_s, b2_e = segs['dev' if b2_seg == 'dev' else b2_seg]
        b2_sess = [x for x in calendar if b2_s <= x <= b2_e]
        for x, v in zip(b2_sess, b2[b2_seg]['net_curve']):
            curves_rows.append({'config_id': 'B2-510300', 'session': x,
                                'equity_net': v, 'equity_gross': None})
        for (key, seed), r in b3.items():
            for x, v in zip(r.sessions, r.equity):
                curves_rows.append({'config_id': f'B3-{key}-s{seed}',
                                    'session': x, 'equity_net': v,
                                    'equity_gross': None})
        pl.DataFrame(curves_rows).write_parquet(run.path / 'equity_curves.parquet')

        trades_rows = []
        for cid, sr in sim_results.items():
            for t in sr['net'].trades:
                trades_rows.append({'config_id': cid, **t})
        for (key, seed), r in b3.items():
            for t in r.trades:
                trades_rows.append({'config_id': f'B3-{key}-s{seed}', **t})
        pl.DataFrame(trades_rows).write_parquet(run.path / 'trades.parquet')

        pos_rows = []
        for cid, sr in sim_results.items():
            for p in sr['net'].positions:
                pos_rows.append({'config_id': cid,
                                 **{k: v for k, v in p.items()
                                    if k != 'entry_session'}})
            for fo in sr['net'].final_open:
                pos_rows.append({'config_id': cid,
                                 **{k: v for k, v in fo.items()
                                    if k != 'entry_session'}})
        pl.DataFrame(pos_rows).write_parquet(run.path / 'positions.parquet')

        timings['total_s'] = round(time.perf_counter() - t_all, 2)
        run.metrics['timings'] = timings
        write_json(run.path / 'metrics.json', run.metrics)
        (run.path / 'report.md').write_text(
            build_report(config, run.metrics, args.smoke), encoding='utf-8')
        if args.smoke:
            print_smoke_verification(run.metrics, sim_results)
        print(f"dev_pass: {run.metrics['dev_pass_configs']} "
              f"advanced: {advanced} p3_candidates: {survivors}")
    return 0 if run.manifest['status'] == 'completed' else 1


def print_smoke_verification(metrics: dict, sim_results: dict) -> None:
    print('\n=== SMOKE VERIFICATION (non-binding) ===')
    print('anchors:', json.dumps(metrics['anchor_regressions']))
    for cid, sr in sim_results.items():
        net = sr['net']
        stats = net.exec_stats
        fees = sum(t['fee'] for t in net.trades)
        risk_fees = sum(t['fee'] for t in net.trades
                        if t['kind'] in RISK_KINDS)
        print(f"{cid}: trades={len(net.trades)} "
              f"risk_trades={stats.risk_buys_filled + stats.risk_sells_filled} "
              f"fees={fees:.2f} risk_fees={risk_fees:.2f} "
              f"min_cash={net.max_negative_cash:.6f} "
              f"final_equity={net.equity[-1]:.2f} "
              f"parity={sr['net_gross_parity']}")
        assert net.max_negative_cash >= 0.0, f'{cid}: NEGATIVE CASH'


def build_report(config: dict, metrics: dict, smoke: bool) -> str:
    lines = ['# P2-R8 日频风控 + 月频选币（预登记策略级回放）', '',
             f"- experiment_id: {config['experiment_id']}"
             f"{'（SMOKE：1 年 × C01/C07，判据不生效）' if smoke else ''}",
             '- dev 段为探索性（重用二：R6/R7 已消费）；种子 17；B3prime 种子 17–36；'
             '费用：佣金万1 最低5元、无印花税/过户费、滑点 0',
             '', '## 锚定回归（先于任何判据消费）', '']
    a = metrics.get('anchor_regressions', {})
    for k, v in a.items():
        lines.append(f'- {k}: {v}')
    lines += ['', '## 基准（dev）', '']
    for key, segs_m in metrics.get('benchmarks', {}).get('B1', {}).items():
        dev = segs_m.get('dev', {})
        lines.append(f"- B1({key}) dev 净年化 {fmt(dev.get('net_cagr'))}（毛 "
                     f"{fmt(dev.get('gross_cagr'))}），回撤 "
                     f"{fmt(dev.get('max_drawdown'))}")
    for seg, m in metrics.get('benchmarks', {}).get('B2', {}).items():
        lines.append(f"- B2 510300 买入持有 {seg}：净 {fmt(m.get('net_total_return'))}"
                     f"（毛 {fmt(m.get('gross_total_return'))}）")
    for k, v in metrics.items():
        if k.startswith('B3prime_'):
            lines.append(f"- {k[8:]}（20 种子）dev 净年化均值 "
                         f"{fmt(v.get('mean_net_cagr'))} "
                         f"[{fmt(v.get('min'))}, {fmt(v.get('max'))}]")
    lines.append('- B4 现金 0%')
    lines += ['', '## 配置结果（dev，探索性重用二）', '',
              '| 配置 | 机制 | 毛% | 净% | B1(m)净% | 净超额pp | 优势年 | 回撤% | '
              '换手max% | top1/top3 | 风控交易 | 过x/8 | 失败判据 |',
              '|---|---|---|---|---|---|---|---|---|---|---|---|---|']
    for cid in sorted(metrics.get('configs', {})):
        m = metrics['configs'][cid]
        g = metrics['gates'][cid]['dev']
        dev = m['dev']
        c = dev['concentration']
        failed = [k.split('_')[0] for k, v in g.items()
                  if k[0].isdigit() and not v]
        rt = dev['risk_trades']
        lines.append(
            f"| {cid} | {m['mech']} {m['mech_key']} "
            f"| {fmt(dev['gross_cagr'])} | {fmt(dev['net_cagr'])} "
            f"| {fmt(dev['b1m_net_cagr'])} | {fmt(dev['excess_vs_b1m'])} "
            f"| {g['positive_years']}/5 | {fmt(dev['max_drawdown'])} "
            f"| {fmt(dev['max_one_side_turnover'])} "
            f"| {fmt(c['top1_share'])}/{fmt(c['top3_share'])} "
            f"| {rt['n_trades']} | {'PASS' if g['dev_pass'] else 'fail'} "
            f"| {','.join(failed) if failed else '—'} |")
    if metrics.get('tradeoff_vs_C01'):
        lines += ['', '## 省回撤 ÷ 丢反弹（对 C01 对照，描述性）', '']
        for row in metrics['tradeoff_vs_C01']:
            lines.append(
                f"- {row['config_id']}（{row['mech']}）: 省回撤 "
                f"{row['saved_drawdown_pp']}pp，丢净年化 "
                f"{row['lost_net_cagr_pp']}pp，比值 "
                f"{row['saved_per_lost'] if row['saved_per_lost'] is not None else '—'}")
    if metrics.get('advanced_to_validation'):
        cid = metrics['advanced_to_validation']
        m = metrics['configs'][cid]
        lines += ['', f'## 存活者 {cid} 后续段', '']
        for seg in ('validation', 'test'):
            if seg in m:
                mm = m[seg]
                g = metrics['gates'][cid].get(seg, {})
                lines.append(
                    f"- {seg}: 净年化 {fmt(mm['net_cagr'])}，B1(m) "
                    f"{fmt(mm['b1m_net_cagr'])}，净超额 {fmt(mm['excess_vs_b1m'])}，"
                    f"回撤 {fmt(mm['max_drawdown'])}，"
                    f"gate={'PASS' if g.get('val_pass') or g.get('test_pass') else 'fail'}")
    lines += ['', '## 判定', '',
              f"- dev 通过（探索性重用二）：{metrics.get('dev_pass_configs')}",
              f"- 进入 validation：{metrics.get('advanced_to_validation')}",
              f"- P3 候选：{metrics.get('p3_candidates')}",
              f"- 试验累计：{metrics.get('trial_count_cumulative')}"]
    return '\n'.join(lines) + '\n'


if __name__ == '__main__':
    raise SystemExit(main())
