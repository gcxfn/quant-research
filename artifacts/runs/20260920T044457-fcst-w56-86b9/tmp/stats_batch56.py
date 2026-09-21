# -*- coding: utf-8 -*-
"""批 56 交付统计：按 type 分组的 primary 分布、sd 计数、low / sd=0 / sd=-1 行号。只读。"""
import json
import os
from collections import Counter

run = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
work = os.path.join(run, "work")

types = {}
with open(os.path.join(work, "batch_056_cues.txt"), encoding="utf-8") as f:
    for line in f:
        oid, t, _ = line.rstrip("\n").split("|", 2)
        types[int(oid)] = t

rows = []
for i in range(1, 7):
    with open(os.path.join(work, f"batch_056_judge_part{i}.jsonl"), encoding="utf-8") as f:
        rows += [json.loads(x) for x in f if x.strip()]

print("total rows:", len(rows))
for t in ("预增", "首亏"):
    sub = [r for r in rows if types[r["ordinal"]] == t]
    print(f"\n== type={t} n={len(sub)} primary_code 分布 ==")
    for code, n in Counter(r["primary_code"] for r in sub).most_common():
        print(f"  {code}: {n}")
    sec = Counter(r["secondary_code"] for r in sub if r["secondary_code"])
    print(f"  secondary 非空 {sum(sec.values())}:", dict(sec))
    print(f"  sd 计数: " + str(dict(Counter(r["supports_direction"] for r in sub))))
    print(f"  confidence low: {[r['ordinal'] for r in sub if r['confidence'] == 'low']}")

print("\nsd=0 行:", [(r["ordinal"], types[r["ordinal"]], r["primary_code"]) for r in rows if r["supports_direction"] == 0])
print("sd=-1 行:", [(r["ordinal"], types[r["ordinal"]], r["primary_code"]) for r in rows if r["supports_direction"] == -1])
