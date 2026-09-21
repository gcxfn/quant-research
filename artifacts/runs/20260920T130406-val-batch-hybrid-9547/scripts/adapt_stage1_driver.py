# -*- coding: utf-8 -*-
"""Stage-1 driver (exp-20260920-val-batch, V1 mixed family).

Runs the TL-30 adapter -- a byte-identical copy of
artifacts/runs/20260919T151630-hybrid-val-v1p3/scripts/adapt_v3_to_val.py,
kept here as scripts/adapt_stage1_tl30.py -- over the v3 mother runner
(scripts/runner_hybrid_v3.py, sha256 873251e1..., byte-identical to the v3
run's own copy) inside THIS run directory.

SRC -> scripts/runner_hybrid_v3.py
DST -> scripts/runner_hybrid_val_tl30.py   (= TL-30 runner, sha 26409c6b...)

Chain-reproduction check: the produced bytes must hash to TL-30's own
runner_hybrid_val.py (26409c6bc18c350bd9547615d3b9bd3ecbdb63d3eda47898cb145
8c4d462afaa).  Mismatch aborts: that means the TL-30 adaptation is not
reproducible from the pinned pair and the whole derivation chain is invalid.

Stage 2 (scripts/adapt_stage2_valbatch.py) then derives this run's runner from
that output with asserted incremental replacements.
"""
from __future__ import annotations

import hashlib
import io
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUN = HERE.parent
ROOT = RUN.parents[2]

TL30_ADAPTER = HERE / "adapt_stage1_tl30.py"
V3_SRC = HERE / "runner_hybrid_v3.py"
DST = HERE / "runner_hybrid_val_tl30.py"
TL30_RUNNER = (ROOT / "artifacts/runs/20260919T151630-hybrid-val-v1p3"
               / "scripts/runner_hybrid_val.py")
PATCHED = RUN / "tmp" / "adapt_stage1_patched.py"
CHECK = RUN / "tmp" / "stage1_repro_check.json"


def sha256(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main() -> int:
    s = io.open(TL30_ADAPTER, encoding="utf-8").read()
    s = s.replace('SRC = os.path.join(HERE, "runner_hybrid_v3.py")',
                  f'SRC = r"{V3_SRC}"')
    s = s.replace('DST = os.path.join(HERE, "runner_hybrid_val.py")',
                  f'DST = r"{DST}"')
    assert f'SRC = r"{V3_SRC}"' in s and f'DST = r"{DST}"' in s
    io.open(PATCHED, "w", encoding="utf-8", newline="\n").write(s)
    ns: dict = {"__name__": "__main__", "__file__": str(PATCHED)}
    exec(compile(s, str(PATCHED), "exec"), ns)  # noqa: S102

    got, want = sha256(DST), sha256(TL30_RUNNER)
    ok = got == want
    CHECK.write_text(
        '{\n "v3_source_sha256": "%s",\n "tl30_adapter_sha256": "%s",\n'
        ' "produced_runner_sha256": "%s",\n'
        ' "tl30_runner_sha256": "%s",\n "chain_reproduced": %s\n}\n'
        % (sha256(V3_SRC), sha256(TL30_ADAPTER), got, want,
           "true" if ok else "false"), encoding="utf-8")
    print(f"stage1: produced {got[:16]} vs TL-30 {want[:16]} -> "
          f"{'REPRODUCED' if ok else 'MISMATCH'}")
    if not ok:
        print("ABORT: stage-1 chain not reproducible", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
