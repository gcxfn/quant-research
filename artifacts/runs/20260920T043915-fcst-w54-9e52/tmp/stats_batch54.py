# -*- coding: utf-8 -*-
"""临时统计：各 part 行数、primary/secondary 分布、sd 计数、low 行号、细则11行清单核对。"""
import json
import os
from collections import Counter

base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
work = os.path.join(base, "work")
rows = []
for p in range(1, 7):
    fp = os.path.join(work, f"batch_054_judge_part{p}.jsonl")
    with open(fp, encoding="utf-8") as f:
        lines = [json.loads(x) for x in f.read().splitlines() if x.strip()]
    oids = [r["ordinal"] for r in lines]
    assert oids == list(range(31800 + (p - 1) * 100, 31800 + p * 100)), p
    print(f"part{p}: {len(lines)} rows, ordinal {oids[0]}-{oids[-1]}")
    rows.extend(lines)

pc = Counter(r["primary_code"] for r in rows)
sc = Counter(r["secondary_code"] for r in rows if r["secondary_code"])
sd = Counter(r["supports_direction"] for r in rows)
low = [r["ordinal"] for r in rows if r["confidence"] == "low"]
sd0 = [r["ordinal"] for r in rows if r["supports_direction"] == 0]
sd_m1 = [(r["ordinal"], r["primary_code"], r["secondary_code"]) for r in rows if r["supports_direction"] == -1]
neg_prim = [(r["ordinal"], r["primary_code"]) for r in rows if r["primary_code"] in ("demand_down", "price_down", "cost_up", "fx", "impairment", "epidemic_shock")]
print("total:", len(rows))
print("primary:", dict(pc.most_common()))
print("secondary:", dict(sc.most_common()))
print("sd:", dict(sd))
print("low:", low)
print("sd0:", sd0)
print("sd-1:", sd_m1)
print("negative-direction primary rows:", neg_prim)
