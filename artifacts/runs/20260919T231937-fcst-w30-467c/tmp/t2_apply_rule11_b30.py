# -*- coding: utf-8 -*-
"""细则 11 回改（批 30）：基数嫌疑行 sd 0→+1（上年同期存在一次性收益、本期无或减少，
解释预减方向）。只改 judge part 文件 supports_direction 字段，其余字段不动；
同步 work/tmp/make_judge_parts.py 的 R 元组保持重生成一致（judge 文件仍为权威源）。"""
import json
import re
from pathlib import Path

HERE = Path(__file__).parent
WORK = HERE.parent / "work"
BATCH = Path(r"D:/量化/data/features/fcst-reason-struct-full-20260918/batch_030.jsonl")
GEN = WORK / "tmp" / "make_judge_parts.py"

targets = json.loads((HERE / "targets_30.json").read_text(encoding="utf-8"))
TARGETS = sorted(t["ordinal"] for t in targets)
assert len(TARGETS) == 77 == len(set(TARGETS)), len(TARGETS)
assert all(17400 <= o < 18000 for o in TARGETS)

# 逐行复核结论：77 行全部为"上年同期存在该一次性收益（政府补助/理财/处置/重估等），本期无或减少"，
# 解释恶化组（预减）方向 → sd=+1；无 -1（无"本期一次性收益却预减"矛盾行）；
# 无维持 0（原文均点名具体一次性项目或总量同比减少，非纯"基数效应"措辞）。
DECISION = {o: 1 for o in TARGETS}

# 与 batch 行一致性预断言
batch_rows = [json.loads(l) for l in BATCH.read_text(encoding="utf-8").splitlines() if l.strip()]
for o in TARGETS:
    r = batch_rows[o - 17400]
    assert r["primary_code"] in ("non_recurring", "impairment") and r["supports_direction"] == 0, o

# 1) judge part 文件：只改 supports_direction
changed = {}
for part in range(1, 7):
    fp = WORK / f"batch_030_judge_part{part}.jsonl"
    lines = fp.read_text(encoding="utf-8").splitlines()
    out = []
    for line in lines:
        obj = json.loads(line)
        if obj["ordinal"] in DECISION:
            assert obj["primary_code"] in ("non_recurring", "impairment"), obj["ordinal"]
            assert obj["supports_direction"] in (0, DECISION[obj["ordinal"]]), obj["ordinal"]
            br = batch_rows[obj["ordinal"] - 17400]
            assert obj["primary_code"] == br["primary_code"]
            assert obj["secondary_code"] == br["secondary_code"]
            assert obj["key_quote"] == br["key_quote"]
            assert obj["confidence"] == br["confidence"]
            obj["supports_direction"] = DECISION[obj["ordinal"]]
            new_line = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
            changed[obj["ordinal"]] = new_line
        else:
            new_line = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
        # 未改行必须与原行字节一致（证明未触碰其他内容、序列化方式与源一致）
        assert new_line == line or obj["ordinal"] in changed, obj["ordinal"]
        out.append(new_line)
    fp.write_text("\n".join(out) + "\n", encoding="utf-8", newline="\n")
    n_here = sum(1 for o in changed if 17400 + (part - 1) * 100 <= o < 17400 + part * 100)
    print(f"part{part}: ok, targets_here={n_here}")

assert len(changed) == 77, len(changed)

# 2) 同步 make_judge_parts.py 的 R 元组（仅目标行 sd 字面量 0→1）
pat = re.compile(r'^\s*\((\d+), "(\w+)", (?:None|"\w+"), (-?\d), ')
gen_lines = GEN.read_text(encoding="utf-8").splitlines()
gen_changed = 0
seen = set()
for i, line in enumerate(gen_lines):
    m = pat.match(line)
    if not m:
        continue
    oid = int(m.group(1))
    sd = int(m.group(3))
    if oid in DECISION:
        assert sd in (0, DECISION[oid]), (oid, sd)
        new_line = line[:m.start(3)] + "1" + line[m.end(3):]
        assert new_line != line
        gen_lines[i] = new_line
        gen_changed += 1
        seen.add(oid)
    else:
        # 非目标行不得被波及
        pass
assert gen_changed == 77 and seen == set(TARGETS), (gen_changed, len(seen))
GEN.write_text("\n".join(gen_lines) + "\n", encoding="utf-8", newline="\n")
print(f"make_judge_parts.py synced: {gen_changed} rows sd 0->1")

# 3) 语法自检重生成脚本
import py_compile
py_compile.compile(str(GEN), doraise=True)
print("make_judge_parts.py compiles OK")
print(f"total changed sd 0->1: {len(changed)}")
