# -*- coding: utf-8 -*-
"""把批 30 目标行渲染成人工审阅视图。"""
import json
from pathlib import Path

HERE = Path(__file__).parent
targets = json.loads((HERE / "targets_30.json").read_text(encoding="utf-8"))
lines = []
for t in targets:
    lines.append(f"[{t['ordinal']}] {t['type']} | {t['primary_code']}/{t['secondary_code']}")
    lines.append(f"  quote: {t['key_quote']}")
    lines.append(f"  原文: {t['change_reason']}")
    lines.append("")
(HERE / "targets_view_30.txt").write_text("\n".join(lines), encoding="utf-8")
print(f"rows={len(targets)} -> targets_view_30.txt")
