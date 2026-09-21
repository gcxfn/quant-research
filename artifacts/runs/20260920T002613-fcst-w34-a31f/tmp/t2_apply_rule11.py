# -*- coding: utf-8 -*-
"""细则 11 回改：批 34 基数嫌疑行 sd 0→+1（上年同期存在一次性收益/减值冲回、本期无或减少）。
只改 judge 文件 supports_direction 字段；逐行断言其余内容字节不变后一次性写回。"""
import json
from pathlib import Path

WORK = Path(r"D:/量化/artifacts/runs/20260920T002613-fcst-w34-a31f/work")
BATCH = Path(r"D:/量化/data/features/fcst-reason-struct-full-20260918/batch_034.jsonl")

# 逐行人工复核结论：54 行全部为"上年同期存在该一次性收益（本期无或减少）/本期较上年减少"，
# 解释恶化组（预减）方向 → sd=+1；无 -1（无"本期收益却预减"矛盾行）；无维持 0（均有具体一次性项目）。
TARGETS = [
    19823, 19825, 19826, 19830, 19834, 19840, 19853, 19856, 19867, 19872,
    19880, 19884, 19885, 19887, 19893,
    19901, 19904, 19928, 19930, 19941, 19980, 19981, 19990,
    20015, 20018, 20024, 20036, 20039, 20048, 20053, 20058, 20060, 20068,
    20107, 20159, 20194,
    20208, 20219, 20265, 20277, 20283, 20295,
    20300, 20303, 20305, 20310, 20311, 20332, 20342, 20345, 20359, 20361,
    20382, 20391,
]
assert len(TARGETS) == 54 == len(set(TARGETS))

batch_rows = [json.loads(l) for l in BATCH.read_text(encoding="utf-8").splitlines() if l.strip()]
for o in TARGETS:
    r = batch_rows[o - 19800]
    assert r["primary_code"] in ("non_recurring", "impairment") and r["supports_direction"] == 0, o

changed = {}
for part in range(1, 7):
    fp = WORK / f"batch_034_judge_part{part}.jsonl"
    lines = fp.read_text(encoding="utf-8").splitlines()
    out = []
    for line in lines:
        obj = json.loads(line)
        if obj["ordinal"] in TARGETS:
            assert obj["primary_code"] in ("non_recurring", "impairment"), obj["ordinal"]
            assert obj["supports_direction"] == 0, obj["ordinal"]
            # 与 batch 行逐字段一致性（除 sd 外不应有任何差异来源）
            br = batch_rows[obj["ordinal"] - 19800]
            assert obj["primary_code"] == br["primary_code"]
            assert obj["secondary_code"] == br["secondary_code"]
            assert obj["key_quote"] == br["key_quote"]
            assert obj["confidence"] == br["confidence"]
            obj["supports_direction"] = 1
            new_line = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
            changed[obj["ordinal"]] = new_line
        else:
            new_line = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
        # 未改行必须与原行字节一致（证明序列化方式与源文件一致、未触碰其他内容）
        assert new_line == line or obj["ordinal"] in changed, obj["ordinal"]
        out.append(new_line)
    fp.write_text("\n".join(out) + "\n", encoding="utf-8", newline="\n")
    print(f"part{part}: ok, targets_here={sum(1 for o in changed if 19800+(part-1)*100 <= o < 19800+part*100)}")

print(f"total changed sd 0->1: {len(changed)}")
