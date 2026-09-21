# -*- coding: utf-8 -*-
"""V2 (F line) -- generate the val-window attribution-event builder from the
frozen T1 event-study script (run 20260920T113527-t1-reason-event-b690).

dev = T1's frozen window (ann_date 2018-09-04..2020-12-31): the rebuild must
reproduce outputs/events_dev.parquet bitwise (prereg sec 3 port rule).
val = ann_date 2021-01-01..2024-12-31 (the 2021-2024 slice of the same 38,567
annotated rows; the 2025+ frozen zone is never touched - the price chain is the
pinned panel that ends 2024-12-31, so a val event whose h=20 window would need
2025 prices has no forward return and drops out of the analysis sample).

Only dates, output names and the sample-size gate's scope are parametrized;
the dedup / pool filter / forward-return / 60-session flag calibers are T1
verbatim.
"""
from __future__ import annotations

import io
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUN_DIR = HERE.parent
T1 = RUN_DIR.parent / "20260920T113527-t1-reason-event-b690"

HEADER = '''
# =============================================================================
# V2 val-batch window parametrization (exp-20260920-val-batch, F line).
# dev = the T1 frozen window (port check: rebuild must be bit-identical);
# val = ann_date 2021-01-01..2024-12-31.
# ONLY the window / output names / sample-gate scope below are new; the dedup
# rule, pool filter, forward-return chain and the flag calibers are the T1
# implementation verbatim.
# =============================================================================
import os as _os
_WINDOW = _os.environ.get("VAL_WINDOW", "dev")
assert _WINDOW in ("dev", "val"), _WINDOW
RUN_DIR = Path(__file__).resolve().parents[2]
_OUTDIR = RUN_DIR / "outputs" / f"events_{_WINDOW}"
_OUTDIR.mkdir(parents=True, exist_ok=True)
_TMPDIR = RUN_DIR / "tmp"
_TMPDIR.mkdir(parents=True, exist_ok=True)
if _WINDOW == "val":
    DEV_FIRST, DEV_LAST = "20210101", "20241231"
    DEV_LAST_D = date(2024, 12, 31)
    YEARS_SEG = [("2021", date(2021, 1, 1), date(2021, 12, 31)),
                 ("2022", date(2022, 1, 1), date(2022, 12, 31)),
                 ("2023", date(2023, 1, 1), date(2023, 12, 31)),
                 ("2024", date(2024, 1, 1), date(2024, 12, 31))]
    BUILD_TAG = "val"
else:
    DEV_FIRST, DEV_LAST = "20180904", "20201231"
    DEV_LAST_D = date(2020, 12, 31)
    YEARS_SEG = [("2018H2", date(2018, 9, 1), date(2018, 12, 31)),
                 ("2019", date(2019, 1, 1), date(2019, 12, 31)),
                 ("2020", date(2020, 1, 1), date(2020, 12, 31))]
    BUILD_TAG = "dev"

'''


def adapt(src: Path, dst: Path, reps: list, insert_after: str | None = None):
    s = io.open(src, encoding="utf-8").read()
    n0 = len(s)
    done = []
    for old, new, cnt in reps:
        c = s.count(old)
        assert c == cnt, (f"{src.name}: expected {cnt} for {old[:90]!r}, got {c}")
        s = s.replace(old, new)
        done.append((old.splitlines()[0][:70], cnt))
    if insert_after is not None:
        assert s.count(insert_after) == 1
        s = s.replace(insert_after, insert_after + HEADER)
        done.append(("INSERT HEADER", 1))
    io.open(dst, "w", encoding="utf-8", newline="\n").write(s)
    print(f"adapted {src.name} -> {dst.name}: {len(done)} groups, "
          f"{n0} -> {len(s)} chars")
    for name, cnt in done:
        print(f"   x{cnt}  {name}")


GEN = RUN_DIR / "scripts/generated"
GEN.mkdir(parents=True, exist_ok=True)

reps = [
    # identity pins: window tag in the manifest/stop paths
    ('T1_DIR = ROOT / "data/features/fcst-reason-struct-full-20260918"',
     'T1_DIR = ROOT / "data/features/fcst-reason-struct-full-20260918"', 1),
    ('DEV_FIRST, DEV_LAST = "20180904", "20201231"\nDEV_LAST_D = date(2020, 12, 31)',
     '# window: see the parametrization header', 1),
    ('''YEARS_SEG = [("2018H2", date(2018, 9, 1), date(2018, 12, 31)),
             ("2019", date(2019, 1, 1), date(2019, 12, 31)),
             ("2020", date(2020, 1, 1), date(2020, 12, 31))]''',
     '# YEARS_SEG: see the parametrization header', 1),
    # tmp artifacts -> window-tagged names
    ('(RUN_DIR / "tmp" / "t1_batch_sha256.txt")',
     '(_TMPDIR / f"t1_batch_sha256_{BUILD_TAG}.txt")', 3),
    ('(RUN_DIR / "tmp" / "annotations_merged.parquet")',
     '(_TMPDIR / f"annotations_merged_{BUILD_TAG}.parquet")', 3),
    # outputs -> per-window dir
    ('drift.write_csv(RUN_DIR / "outputs" / "type_drift.csv")',
     'drift.write_csv(_OUTDIR / "type_drift.csv")', 1),
    ('pl.DataFrame(mrows).write_csv(\n    RUN_DIR / "outputs" / "primary_within_type.csv")',
     'pl.DataFrame(mrows).write_csv(\n    _OUTDIR / "primary_within_type.csv")',
     1),
    ('(RUN_DIR / "outputs" / "anova_main.json").write_text(',
     '(_OUTDIR / "anova_main.json").write_text(', 1),
    ('              for r in sens_rows]).write_csv(\n    RUN_DIR / "outputs" / "sensitivity.csv")',
     '              for r in sens_rows]).write_csv(\n    _OUTDIR / "sensitivity.csv")',
     1),
    ('diag.write_csv(RUN_DIR / "outputs" / "category_diagnostics.csv")',
     'diag.write_csv(_OUTDIR / "category_diagnostics.csv")', 1),
    ('ev_out.write_parquet(RUN_DIR / "outputs" / "events_dev.parquet")',
     'ev_out.write_parquet(_OUTDIR / f"events_{BUILD_TAG}.parquet")', 1),
    ('(RUN_DIR / "outputs" / "pool_filter_counts.json").write_text(',
     '(_OUTDIR / "pool_filter_counts.json").write_text(', 1),
    ('MANIFEST["outputs"] = {\n    name: sha256_file(RUN_DIR / "outputs" / name) for name in\n'
     '    ("events_dev.parquet", "type_drift.csv", "primary_within_type.csv",\n'
     '     "anova_main.json", "sensitivity.csv", "pool_filter_counts.json",\n'
     '     "category_diagnostics.csv")}',
     '_out_names = (f"events_{BUILD_TAG}.parquet", "type_drift.csv",\n'
     '              "primary_within_type.csv", "anova_main.json",\n'
     '              "sensitivity.csv", "pool_filter_counts.json",\n'
     '              "category_diagnostics.csv")\n'
     'MANIFEST["outputs"] = {name: sha256_file(_OUTDIR / name)\n'
     '                       for name in _out_names}', 1),
    ('(RUN_DIR / "manifest.json").write_text(\n        json.dumps(MANIFEST, ensure_ascii=False, indent=1, default=str),\n'
     '        encoding="utf-8")',
     '(RUN_DIR / "tmp" / f"manifest_events_{BUILD_TAG}.json").write_text(\n'
     '        json.dumps(MANIFEST, ensure_ascii=False, indent=1, default=str),\n'
     '        encoding="utf-8")', 1),
    ('    (RUN_DIR / "tmp" / "stop_report.md").write_text(\n        "# STOP REPORT -- exp-20260920-t1-reason-event\\n\\n"',
     '    (_TMPDIR / f"stop_report_events_{BUILD_TAG}.md").write_text(\n'
     '        "# STOP REPORT -- exp-20260920-t1-reason-event (V2 events port)\\n\\n"',
     1),
    ('_sr = RUN_DIR / "tmp" / "stop_report.md"',
     '_sr = _TMPDIR / f"stop_report_events_{BUILD_TAG}.md"', 1),
    # sample-size gates are a T1-experiment rule: kept verbatim in dev (port
    # fidelity), converted to a disclosure in val (the V2 batch does not
    # re-adjudicate T1's H1; it only needs the flagged event table).
    ('if ev_pool.height < GATE_MIN_TOTAL:\n'
     '    stop(f"样本量门槛触发: 池过滤后总数 {ev_pool.height} < {GATE_MIN_TOTAL}")',
     'if _WINDOW == "dev" and ev_pool.height < GATE_MIN_TOTAL:\n'
     '    stop(f"样本量门槛触发: 池过滤后总数 {ev_pool.height} < {GATE_MIN_TOTAL}")',
     1),
    ('if small_types:\n'
     '    stop(f"样本量门槛触发: 进检验 type <{GATE_MIN_TYPE}: {small_types}")',
     'if _WINDOW == "dev" and small_types:\n'
     '    stop(f"样本量门槛触发: 进检验 type <{GATE_MIN_TYPE}: {small_types}")',
     1),
    # val-only: assert the price chain (and hence every analysis window) stays
    # inside 2024-12-31 (2025+ zero contact) and quantify the dropped tail.
    ('ev_out = ana_g.select(out_cols)\nassert ev_out["fwd_h20"].null_count() == 0',
     'ev_out = ana_g.select(out_cols)\n'
     'assert ev_out["fwd_h20"].null_count() == 0\n'
     'if _WINDOW == "val":\n'
     '    _wend_max = ev_out["wend_h20"].max()\n'
     '    assert _wend_max is None or _wend_max <= date(2024, 12, 31), (\n'
     '        f"val window right edge beyond the freeze line: {_wend_max}")\n'
     '    print(f"[val] {n_no_fwd} pool-passed events dropped for lack of a "\n'
     '          f"complete h=20 window inside 2024-12-31; max window end "\n'
     '          f"{_wend_max}")', 1),
]

# additional val-only fact recorded in the manifest
reps.append((
    'if chain["date"].max() > date(2024, 12, 31):\n'
    '    stop(f"冻结区违例: 收益链日期 {chain[\'date\'].max()}")',
    'chain_max_date = chain["date"].max()\n'
    'if chain_max_date > date(2024, 12, 31):\n'
    '    stop(f"冻结区违例: 收益链日期 {chain_max_date}")', 1))
reps.append((
    'MANIFEST["results"] = {\n    "main_p": main_p, "main_verdict": main_verdict,',
    'if _WINDOW == "val":\n'
    '    MANIFEST["freeze_discipline"] = {\n'
    '        "price_chain_max_date": str(chain_max_date),\n'
    '        "events_in_window_dropped_no_forward": n_no_fwd,\n'
    '        "wend_h20_max": str(ev_out["wend_h20"].max()),\n'
    '        "note": "the h=20 window right edge uses the pinned panel that "\n'
    '                "ends 2024-12-31; T1 (dev) allowed a natural spill past "\n'
    '                "its window, the val build does not touch 2025+, so the "\n'
    '                "few pool-passed val events whose 20-session window "\n'
    '                "would need 2025 prices drop out of the analysis "\n'
    '                "sample (they are all later than the last val signal "\n'
    '                "month 2024-11-29, so no flag month is affected)"}\n'
    'MANIFEST["results"] = {\n    "main_p": main_p, "main_verdict": main_verdict,',
    1))

adapt(T1 / "scripts/run_t1_event.py", GEN / "val_events.py", reps,
      insert_after='RUN_DIR = Path(__file__).resolve().parents[1]\n')
