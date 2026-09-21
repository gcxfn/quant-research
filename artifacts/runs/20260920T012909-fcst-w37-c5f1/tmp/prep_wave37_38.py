#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""wave-37/38 备制（双批实验）：两波均由 w28 混合口径模板（ordinal|type|REASON）派生。
b37: ordinals 21600-22199，混合批（376 预增 + 224 预减）。
b38: ordinals 22200-22799，单一预增（改善组）。
"""
import os
import subprocess
import sys

W28 = "D:/量化/artifacts/runs/20260919T231937-fcst-w28-9af7/scripts"
PY = "D:/量化/.venv/Scripts/python.exe"
ROOT = "D:/量化"

WAVES = {
    37: ("20260920T012909-fcst-w37-c5f1", 21600),
    38: ("20260920T012909-fcst-w38-d6a4", 22200),
}


def derive(batch, wave_dir, base_ord):
    wdir = os.path.join(ROOT, "artifacts", "runs", wave_dir)
    sdir = os.path.join(wdir, "scripts")
    os.makedirs(sdir, exist_ok=True)
    os.makedirs(os.path.join(wdir, "work"), exist_ok=True)
    os.makedirs(os.path.join(wdir, "tmp"), exist_ok=True)
    old, new = f"batch_028", f"batch_{batch:03d}"

    # extract_cues.py
    with open(os.path.join(W28, "extract_cues.py"), encoding="utf-8") as f:
        t = f.read()
    assert t.count("default=28") == 1
    t = t.replace("default=28", f"default={batch}")
    n = t.count(old)
    assert n >= 2, f"extract {old} hit {n}"
    t = t.replace(old, new)
    with open(os.path.join(sdir, "extract_cues.py"), "w", encoding="utf-8", newline="\n") as f:
        f.write(t)
    print(f"w{wave_dir} extract_cues.py: default={batch}, {n} filename refs")

    # merge_batchNN.py
    with open(os.path.join(W28, "merge_batch28.py"), encoding="utf-8") as f:
        m = f.read()
    assert m.count('pl.col("batch_id") == 28') == 1
    m = m.replace('pl.col("batch_id") == 28', f'pl.col("batch_id") == {batch}')
    assert m.count("expect_lo = 16200") == 1
    m = m.replace("expect_lo = 16200", f"expect_lo = {base_ord}")
    n = m.count(old)
    assert n >= 6, f"merge {old} hit {n}"
    m = m.replace(old, new)
    n2 = m.count("wave-28")
    m = m.replace("wave-28", f"wave-{batch}")
    with open(os.path.join(sdir, f"merge_batch{batch}.py"), "w", encoding="utf-8", newline="\n") as f:
        f.write(m)
    print(f"w{wave_dir} merge_batch{batch}.py: filter=={batch}, base={base_ord}, {n} filename refs, {n2} wave refs")

    for fn in ("check_batch_full.py", "quality_stats.py"):
        with open(os.path.join(W28, fn), encoding="utf-8") as f:
            shutil_t = f.read()
        with open(os.path.join(sdir, fn), "w", encoding="utf-8", newline="\n") as f:
            f.write(shutil_t)

    r = subprocess.run(
        [PY, os.path.join(sdir, "extract_cues.py"), "--repo-root", ROOT, "--batch", str(batch)],
        capture_output=True, text=True, encoding="utf-8", cwd=sdir,
    )
    print("cues:", r.stdout.strip())
    if r.returncode != 0:
        print("stderr:", r.stderr.strip())
        sys.exit(1)


for b, (wd, bo) in WAVES.items():
    derive(b, wd, bo)
