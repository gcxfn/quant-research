#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""wave-13 收尾自检：batch_013.jsonl 完整性、批 1-12 未动、progress 累计一致性。只读。"""
import json
import os

FD = r"D:\量化\data\features\fcst-reason-struct-full-20260918"
RD = r"D:\量化\artifacts\runs\20260919T044625-fcst-w13-8gsb"


def load(b):
    p = os.path.join(FD, f"batch_{b:03d}.jsonl")
    with open(p, encoding="utf-8") as f:
        return [x for x in f.read().splitlines() if x.strip()]


lines13 = load(13)
lines12 = load(12)
o13 = json.loads(lines13[0])
o12 = json.loads(lines12[0])
print("b13 lines:", len(lines13), "| b12 lines:", len(lines12))
print("field order same as b12:", list(o13.keys()) == list(o12.keys()))
print("b13 first line head:", lines13[0][:80])

counts = {b: len(load(b)) for b in range(1, 13)}
print("b1-12 line counts all 600:", all(v == 600 for v in counts.values()))

prog = json.load(open(os.path.join(FD, "progress.json"), encoding="utf-8"))
cum = prog["cumulative"]
print("cum n_rows:", cum["n_rows"], "| rows_completed:", prog["rows_completed"])
print("batches_completed:", prog["batches_completed"])
print("cum primary sum:", sum(cum["primary_code_distribution"].values()),
      "| sd sum:", sum(cum["supports_direction_distribution"].values()),
      "| conf sum:", sum(cum["confidence_distribution"].values()))
print("updated_at:", prog["updated_at"])

total = 0
for root, _dirs, files in os.walk(RD):
    for f in sorted(files):
        total += 1
        print(os.path.relpath(os.path.join(root, f), RD).replace("\\", "/"))
print("run dir files:", total)
