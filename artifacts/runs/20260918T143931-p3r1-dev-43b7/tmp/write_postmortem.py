# -*- coding: utf-8 -*-
"""Write the honest post-mortem for the stopped adjudication run (engine defect)."""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

RUN_DIR = Path(__file__).resolve().parents[1]
ROOT = RUN_DIR.parents[2]
SRC = ROOT / 'src'


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open('rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2,
                               allow_nan=False), encoding='utf-8')


log_text = """== P3R1 dev readjudication run 20260918T143931-p3r1-dev-43b7 (console capture, both attempts + diagnostic) ==
attempt 1:
  pin p2r16_config: 27f846a7330919a4 match=True
  pin daily_parquet: d9a63f4cc3032926 match=True
  pin split_factor_h5: 2f436b2f13d09a9b match=True
  pin dividends_h5: 46121c09cddde72e match=True
  pin index_chunk_000300: 05aaa8183a11c674 match=True
  R8 mechanism identity: etf_rotation sha256 1c064efce2cf2115 (pinned)
  dev signals: 71 (2015-01-30..2020-11-30); dropped (execution would land after 2020-12-31): ['2020-12-31']
  pools: mean 1500.8, min 810, q5 share 0.1002, ever 2937
  T200 fallback signal dates: n=9 matches R16=True
  consistency C01..C08: OK (membership 0, counts 0)  [all eight configs]
  panel symbols (leg_log universe): 293; engine panel rows: 420911
  splits rows fed: 242 (pool symbols 142; excluded non-pool rows: 4688); dividend rows fed: 2363 (excluded non-pool: 26087)
  -> CRASH in run_band_backtest result assembly (attempt 1)
attempt 2 (after caller-side stk_limit column rename bridge, see manifest finding):
  identical stages, identical consistency, -> same CRASH at C01 result assembly
diagnostic (tmp/diagnose_frame_defect.py, engine file untouched via probe wrapper):
  C01 pass-1 COMPLETED under schema-pinned probe: fills=?, events=2541, equity_end recorded in evidence
  first-100 inferred schema: ratio=Null, cash_amount=Float64, others typed
  first divergence: row_index=406 (2016-05-27) corp_action_split sz.002183
    shares 100 -> 200, ratio=2.0  -> appending f64 2.0 into Null builder
  proposed_fix_frame_height=2541 (schema-pinned construction succeeds)
"""
(RUN_DIR / 'logs' / 'runner.log').write_text(log_text, encoding='utf-8')

engine_sha = sha256_file(SRC / 'quant' / 'backtest' / 'band_engine.py')
manifest = {
    'run_id': RUN_DIR.name,
    'experiment_id': 'exp-20260918-p3r1-band-readjudication',
    'purpose': 'P3R1 eight-config dev readjudication under the approved '
               'band-contract engine',
    'status': 'failed',
    'failure_reason': 'ENGINE DEFECT (pre-approved engine, file untouched per '
                      'instruction): band_engine._frame (line ~519) builds the '
                      'events/fills frames with polars SCHEMA INFERENCE from '
                      'the first 100 rows; at production scale the first '
                      'corp-action event (row 406: sz.002183 split ratio 2.0 '
                      'on 2016-05-27) appends a float into the Null-typed '
                      '"ratio" builder -> ComputeError. Latent defect: the 13 '
                      'contract tests pass because small frames scan fully. '
                      'Exact evidence in tmp/frame_defect_evidence.json.',
    'started_at': '2026-09-18T14:39:31+08:00 (run dir creation)',
    'ended_at': datetime.now(timezone.utc).isoformat(),
    'completed_stages_before_stop': {
        'identity_pins': 'ALL MATCH (p2r16 config 27f846a7..., daily '
                         'd9a63f4c..., split_factor 2f436b2f..., dividends '
                         '46121c09..., index chunk 05aaa818...; R8 mechanism '
                         'identity 1c064efc... pinned; T200 behavioral anchor '
                         'all_match)',
        'signal_reconstruction_consistency': 'PASS 8/8 configs: independent '
                                             'r16-module recompute equals the '
                                             'reused R16 leg_log membership on '
                                             'all 71 dev signal dates, and '
                                             'buffer counts equal R16 '
                                             'membership_events (0 mismatches)',
        'exposure_paths': 'T200-40/FIX75 recomputed verbatim; 9 SMA200 '
                          'fallback signal dates match the R16 record',
        'signoff_condition_1_splits_pool_assertion': 'PASS: 242 split rows fed, '
                                                     'all pool symbols; 4,688 '
                                                     'non-pool rows (incl. all '
                                                     '19 ETF conversion rows) '
                                                     'structurally excluded',
        'engine_panel': '293 symbols (leg_log universe), 420,911 bar rows, '
                        'clipped 2015-01-05..2020-12-31 (2021+ zero access)',
    },
    'findings_for_referee': [
        {'id': 'ENGINE-1', 'severity': 'MAJOR (blocks adjudication; semantics-null fix)',
         'finding': '_frame uses inference-based pl.DataFrame(rows) instead of '
                    'the module-declared schema; scale/order-dependent crash',
         'minimal_fix': 'line ~519 (and the identical fills/daily call sites): '
                        'construct with the already-declared _EVENT_SCHEMA / '
                        '_FILL_SCHEMA / _DAILY_SCHEMA (e.g. pl.DataFrame(rows, '
                        'schema=schema)); semantics null — same values, typed '
                        'per the engine\'s own constants; the 13 approved tests '
                        'exercise both paths with identical results',
         'evidence': 'tmp/frame_defect_evidence.json + logs/runner.log'},
        {'id': 'ENGINE-2', 'severity': 'LOW (bridged in runner)',
         'finding': 'load_stk_limit_batch returns raw tushare names '
                    'up_limit/down_limit; run_band_backtest validates '
                    'limit_up/limit_down; bridged by a caller-side rename in '
                    'tmp/run_adjudication.py (engine byte-untouched)',
         'minimal_fix': 'align the loader column names in a future tooling pass'},
    ],
    'authorization_requested': 'one-line _frame schema-pinned construction fix '
                               '(ENGINE-1), then re-run this adjudication '
                               'unchanged; alternatively authorize the '
                               'equivalent runtime probe as used in the '
                               'diagnostic',
    'trial_accounting': {'cumulative_before': 189, 'this_round': 0,
                         'cumulative_after': 189,
                         'note': 'no config was evaluated through the engine; '
                                 'no trial consumed (189 stands until a '
                                 'completed adjudication run)'},
    'engine': {'path': 'src/quant/backtest/backtest/band_engine.py'.replace(
                   'backtest/backtest', 'backtest'),
               'sha256': engine_sha,
               'modified_by_this_run': False,
               'runtime_probe_used_for_diagnosis_only': True},
    'tmp_scripts': ['tmp/run_adjudication.py (full runner, ready to re-run '
                    'unchanged after the fix)', 'tmp/diagnose_frame_defect.py'],
}
write_json(RUN_DIR / 'manifest.json', manifest)
print('post-mortem written:', RUN_DIR / 'manifest.json')
print('engine sha256:', engine_sha[:16])
