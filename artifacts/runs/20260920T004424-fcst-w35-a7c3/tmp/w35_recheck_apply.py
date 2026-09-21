#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""批 35 基数嫌疑行 sd 回改（细则 11）：42 行 0→+1，只改 supports_direction。
逐行校验：目标行恰含一处 '"supports_direction": 0'；非目标行字节不变。"""
import json
import os
import shutil
import sys

sys.stdout.reconfigure(encoding="utf-8")

RUN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = os.path.join(RUN, "work")
TMP = os.path.join(RUN, "tmp")

# 42 行基数类回改清单（全部 0→+1），按 part 分组
TARGETS = {
    1: [20403, 20413, 20429, 20436, 20437, 20442, 20443, 20445, 20446, 20454, 20455, 20488],
    2: [20501, 20517, 20523, 20549, 20550],
    3: [20610, 20677, 20682, 20693],
    4: [20704, 20714, 20716, 20720, 20726, 20745, 20753, 20757, 20762, 20765, 20792, 20793, 20794],
    5: [20805, 20823, 20824, 20828, 20840, 20861],
    6: [20923],
}
OLD = '"supports_direction": 0'
NEW = '"supports_direction": 1'

total = 0
changed = []
for part, oids in TARGETS.items():
    path = os.path.join(WORK, f"batch_035_judge_part{part}.jsonl")
    with open(path, encoding="utf-8", newline="") as f:
        raw = f.read()
    lines = raw.split("\n")
    want = set(oids)
    out = []
    for ln in lines:
        if not ln.strip():
            out.append(ln)
            continue
        oid = json.loads(ln)["ordinal"]
        if oid in want:
            if ln.count(OLD) != 1:
                raise SystemExit(f"FAIL part{part} ordinal {oid}: pattern count != 1")
            out.append(ln.replace(OLD, NEW))
            changed.append(oid)
            want.discard(oid)
        else:
            out.append(ln)
    if want:
        raise SystemExit(f"FAIL part{part}: ordinals not found: {sorted(want)}")
    new_text = "\n".join(out)
    # 备份 + 回写
    shutil.copy2(path, os.path.join(TMP, f"batch_035_judge_part{part}.jsonl.bak-sdfix"))
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(new_text)
    # 回读验证：其余字段逐字节不变、sd 已改
    with open(path, encoding="utf-8", newline="") as f:
        back = f.read()
    if back != new_text:
        raise SystemExit(f"FAIL part{part}: rewrite mismatch")
    total += len(oids)

# 全量重读：确认 42 行 sd==1 且仅 supports_direction 变化（对照备份）
for part, oids in TARGETS.items():
    with open(os.path.join(TMP, f"batch_035_judge_part{part}.jsonl.bak-sdfix"), encoding="utf-8") as f:
        old_lines = {json.loads(x)["ordinal"]: x for x in f if x.strip()}
    with open(os.path.join(WORK, f"batch_035_judge_part{part}.jsonl"), encoding="utf-8") as f:
        for x in f:
            if not x.strip():
                continue
            j = json.loads(x)
            old = json.loads(old_lines[j["ordinal"]])
            if j["ordinal"] in oids:
                assert j["supports_direction"] == 1, f"ordinal {j['ordinal']} not 1"
                old["supports_direction"] = 1
                assert j == old, f"ordinal {j['ordinal']}: other field changed"
            else:
                assert j == old, f"ordinal {j['ordinal']}: unexpectedly changed"

print(json.dumps({
    "targets": total,
    "changed_0_to_1": sorted(changed),
    "verify": "only supports_direction mutated; all other lines/fields byte-identical",
}, ensure_ascii=False))
