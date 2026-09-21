#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""wave-48 备制：由 w28 混合口径模板（ordinal|type|REASON）派生。
b48: ordinals 28200-28799，600 行全部预增（改善组，单一 type）。
"""
import os
import subprocess
import sys

W28 = "D:/量化/artifacts/runs/20260919T231937-fcst-w28-9af7/scripts"
WDIR = "D:/量化/artifacts/runs/20260920T034647-fcst-w48-7228"
PY = "D:/量化/.venv/Scripts/python.exe"
ROOT = "D:/量化"
BATCH, BASE = 48, 28200

os.makedirs(os.path.join(WDIR, "scripts"), exist_ok=True)
os.makedirs(os.path.join(WDIR, "work"), exist_ok=True)
os.makedirs(os.path.join(WDIR, "tmp"), exist_ok=True)
old, new = "batch_028", f"batch_{BATCH:03d}"

with open(os.path.join(W28, "extract_cues.py"), encoding="utf-8") as f:
    t = f.read()
assert t.count("default=28") == 1
t = t.replace("default=28", f"default={BATCH}")
n = t.count(old)
assert n >= 2
t = t.replace(old, new)
with open(os.path.join(WDIR, "scripts", "extract_cues.py"), "w", encoding="utf-8", newline="\n") as f:
    f.write(t)
print(f"extract_cues.py: default={BATCH}, {n} refs")

with open(os.path.join(W28, "merge_batch28.py"), encoding="utf-8") as f:
    m = f.read()
assert m.count('pl.col("batch_id") == 28') == 1
m = m.replace('pl.col("batch_id") == 28', f'pl.col("batch_id") == {BATCH}')
assert m.count("expect_lo = 16200") == 1
m = m.replace("expect_lo = 16200", f"expect_lo = {BASE}")
n = m.count(old)
assert n >= 6
m = m.replace(old, new)
n2 = m.count("wave-28")
m = m.replace("wave-28", f"wave-{BATCH}")
with open(os.path.join(WDIR, "scripts", f"merge_batch{BATCH}.py"), "w", encoding="utf-8", newline="\n") as f:
    f.write(m)
print(f"merge_batch{BATCH}.py: filter=={BATCH}, base={BASE}, {n} refs, {n2} wave refs")

for fn in ("check_batch_full.py", "quality_stats.py"):
    with open(os.path.join(W28, fn), encoding="utf-8") as f:
        s = f.read()
    with open(os.path.join(WDIR, "scripts", fn), "w", encoding="utf-8", newline="\n") as f:
        f.write(s)

r = subprocess.run(
    [PY, os.path.join(WDIR, "scripts", "extract_cues.py"), "--repo-root", ROOT, "--batch", str(BATCH)],
    capture_output=True, text=True, encoding="utf-8", cwd=os.path.join(WDIR, "scripts"),
)
print("cues:", r.stdout.strip())
if r.returncode != 0:
    print("stderr:", r.stderr.strip())
    sys.exit(1)
