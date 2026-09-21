# -*- coding: utf-8 -*-
"""wave-24 adaptation: merge_batch23.py -> merge_batch24.py (ascii-safe replacements only)."""
import io
import os

here = os.path.dirname(os.path.abspath(__file__))
src = io.open(os.path.join(here, "merge_batch23.py"), encoding="utf-8").read()

pairs = [
    ("wave-23", "wave-24"),
    ("merge_batch23.py", "merge_batch24.py"),
    ("batch_023", "batch_024"),
    ('pl.col("batch_id") == 23', 'pl.col("batch_id") == 24'),
    ("13200", "13800"),
]
for old, new in pairs:
    n = src.count(old)
    assert n >= 1, "missing: " + old
    src = src.replace(old, new)
    print("replace %r x%d" % (old, n))

assert "13200" not in src, "residual 13200"
assert "batch_023" not in src, "residual batch_023"
assert 'batch_id") == 23' not in src, "residual batch 23"

io.open(os.path.join(here, "merge_batch24.py"), "w", encoding="utf-8", newline="\n").write(src)
os.remove(os.path.join(here, "merge_batch23.py"))
print("OK -> merge_batch24.py")
