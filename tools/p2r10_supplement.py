"""Post-run supplement for the completed P2-R10 survey run.

Adds ONLY descriptive disclosures that the frozen protocol lists but the
main CLI did not persist: (a) per-factor rank-IC vs the T2 target
(next open_930 / close_1130 - 1; disclosed, never gated), (b) per-year
D10-D1 decile spread descriptive stats for 2021-2024 (dev direction, no
gates, no selection).  The panel is rebuilt deterministically by the same
`build_panel` code path; no new factors, parameters or trials are created.

Run as:
  PYTHONPATH=D:/量化/src .venv/Scripts/python.exe -X utf8 \\
      tools/p2r10_supplement.py <run_dir>
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))

from quant.cli.p2r10_halfday_survey import (  # noqa: E402
    DEV_END, DEV_START, FACTOR_NAMES, build_panel, yearly_ic)
from quant.research.p2r10_halfday import (  # noqa: E402
    daily_rank_ic, spread_window_stats, window_ic)
from quant.research.runs import sha256, write_json  # noqa: E402

RUN = Path(sys.argv[1])
metrics = json.loads((RUN / 'metrics.json').read_text(encoding='utf-8'))


def main() -> None:
    panel, _ = build_panel(False)

    # (a) T2 rank-IC series per factor (descriptive only)
    t2_frames = []
    t2_summary: dict[str, dict] = {}
    for f in FACTOR_NAMES:
        ic = daily_rank_ic(panel, f, 'T2').with_columns(
            pl.lit(f).alias('factor'))
        t2_frames.append(ic.select('factor', 'date', 'n', 'ic'))
        dev = window_ic(ic, DEV_START, DEV_END)
        years = yearly_ic(ic)
        t2_summary[f] = {'dev': dev, 'yearly': years}
    pl.concat(t2_frames).write_parquet(RUN / 'supplement_t2_ic_daily.parquet')

    # (b) per-year spread descriptive from the saved decile evidence
    spread = pl.read_parquet(RUN / 'decile_spread_daily.parquet')
    by_year = {}
    for f in FACTOR_NAMES:
        direction = metrics['factor_results'][f]['direction']
        rows = []
        for year in range(2015, 2025):
            lo, hi = date(year, 1, 1), date(year, 12, 31)
            s = (spread.filter((pl.col('factor') == f)
                               & (~pl.col('buyable_only'))))
            st = spread_window_stats(s, lo, hi, direction)
            sb = spread_window_stats(
                spread.filter((pl.col('factor') == f)
                              & pl.col('buyable_only')), lo, hi, direction)
            rows.append({
                'year': year,
                'annualized_gross': st.annualized,
                'month_share_same_sign': st.month_share_same_sign,
                'n_days': st.n_days,
                'buyable_annualized': sb.annualized,
            })
        by_year[f] = rows

    write_json(RUN / 'supplement_descriptive.json', {
        'purpose': 'post-run descriptive supplement: T2 IC disclosure and '
                   'per-year decile spread stats (dev direction); no gates, '
                   'no selection, no new trials',
        't2_ic': t2_summary,
        'spread_by_year': by_year,
    })

    # update manifest outputs + disclose the post-completion addition
    manifest = json.loads((RUN / 'manifest.json').read_text(encoding='utf-8'))
    outputs = {str(p.relative_to(RUN)): sha256(p)
               for p in RUN.rglob('*') if p.is_file()
               and p.name != 'manifest.json'}
    manifest['outputs'] = outputs
    manifest['supplement'] = {
        'added_after_completion': True,
        'files': ['supplement_t2_ic_daily.parquet',
                  'supplement_descriptive.json'],
        'purpose': 'descriptive-only disclosures (T2 IC; per-year decile '
                   'spread); deterministic rebuild via build_panel; no '
                   'gates, no selection, no trial-count change',
    }
    write_json(RUN / 'manifest.json', manifest)
    print('supplement written to', RUN)


if __name__ == '__main__':
    main()
