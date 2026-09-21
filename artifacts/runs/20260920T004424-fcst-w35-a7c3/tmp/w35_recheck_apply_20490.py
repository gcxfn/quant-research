#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""补改遗漏行 20490（300071.SZ，2021 年重整综合收益基数，本期不再存在 → +1）。
同口径：只改 supports_direction，备份到独立文件名，逐字段核对。"""
import json
import os
import shutil
import sys

sys.stdout.reconfigure(encoding="utf-8")

RUN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(RUN, "work", "batch_035_judge_part1.jsonl")
BAK = os.path.join(RUN, "tmp", "batch_035_judge_part1.jsonl.bak-sdfix-20490")
OLD = '"supports_direction": 0'
NEW = '"supports_direction": 1'
OID = 20490

with open(PATH, encoding="utf-8", newline="") as f:
    lines = f.read().split("\n")

out, hit = [], False
for ln in lines:
    if ln.strip() and json.loads(ln)["ordinal"] == OID:
        assert ln.count(OLD) == 1, f"ordinal {OID}: pattern count != 1"
        out.append(ln.replace(OLD, NEW))
        hit = True
    else:
        out.append(ln)
assert hit, f"ordinal {OID} not found"

shutil.copy2(PATH, BAK)
with open(PATH, "w", encoding="utf-8", newline="") as f:
    f.write("\n".join(out))
with open(PATH, encoding="utf-8", newline="") as f:
    assert f.read() == "\n".join(out)

# 对照备份逐字段核对：仅 supports_direction 0→1，其余行字节不变
with open(BAK, encoding="utf-8") as f:
    old_map = {json.loads(x)["ordinal"]: x for x in f if x.strip()}
with open(PATH, encoding="utf-8") as f:
    for x in f:
        if not x.strip():
            continue
        j = json.loads(x)
        old = json.loads(old_map[j["ordinal"]])
        if j["ordinal"] == OID:
            assert j["supports_direction"] == 1
            old["supports_direction"] = 1
            assert j == old
        else:
            assert j == old, f"ordinal {j['ordinal']}: unexpectedly changed"

print(json.dumps({"changed_0_to_1": [OID],
                  "verify": "only supports_direction mutated"}, ensure_ascii=False))
