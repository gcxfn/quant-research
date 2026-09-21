# -*- coding: utf-8 -*-
"""v1.4.1 三锚零回归比对（沿 20260919T222634-engine-v14-impl tmp/
main_accept_anchors.py 的同一口径）：本 run outputs vs 三个 v1.4 pin 时
锚源 run 的 outputs；16 个数据产物 filecmp 逐字节，锚 2/3 stats.json 剔除
{engine_version, wall_s} 后逐键相等。锚 1 metrics/stats 不比对（F-4 既有
口径：五 parquet 覆盖行为面）。"""
import filecmp
import json
import pathlib
import sys

ROOT = pathlib.Path(r"D:\量化")
RUN = ROOT / "artifacts/runs/20260920T031746-engine-v141-anchors-9de3"
PAIRS = {
    "anchor1_P3R2_C05": (
        RUN / "outputs",
        ROOT / "artifacts/runs/20260919T030640-p3r2-dev-ad9e/outputs",
        ["C05_fills.parquet", "C05_events.parquet", "C05_daily_equity.parquet",
         "C05_clips_final.parquet", "C05_intents.parquet"]),
    "anchor2_H2_A0": (
        RUN / "outputs",
        ROOT / "artifacts/runs/20260919T063022-hybrid-v2-2k5b/outputs",
        ["H2-A0_fills.parquet", "H2-A0_events.parquet", "H2-A0_daily_equity.parquet",
         "H2-A0_clips_final.parquet", "H2-A0_intents.parquet", "dividend_events.csv"]),
    "anchor3_F3R3_A0": (
        RUN / "outputs",
        ROOT / "artifacts/runs/20260919T201500-f3r3-industry-cap-4b2e/outputs",
        ["F3R3-A0_fills.parquet", "F3R3-A0_events.parquet", "F3R3-A0_daily_equity.parquet",
         "F3R3-A0_clips_final.parquet", "F3R3-A0_intents.parquet"]),
}
ok = True
n_eq = 0
for name, (new_dir, src_dir, files) in PAIRS.items():
    for fn in files:
        a, b = new_dir / fn, src_dir / fn
        if not a.exists():
            print(f"{name}: MISSING replay file {fn}")
            ok = False
            continue
        if not b.exists():
            print(f"{name}: MISSING pin-time file {fn}")
            ok = False
            continue
        eq = filecmp.cmp(a, b, shallow=False)
        ok &= eq
        n_eq += eq
        print(f"{name}: {fn} {'BYTE-EQUAL' if eq else '*** DIFFERS ***'}")
for tag, fn, src in (
        ("anchor2", "H2-A0_stats.json",
         ROOT / "artifacts/runs/20260919T063022-hybrid-v2-2k5b/outputs/H2-A0_stats.json"),
        ("anchor3", "F3R3-A0_stats.json",
         ROOT / "artifacts/runs/20260919T201500-f3r3-industry-cap-4b2e/outputs/F3R3-A0_stats.json")):
    new = json.loads((RUN / "outputs" / fn).read_text(encoding="utf-8"))
    old = json.loads(src.read_text(encoding="utf-8"))
    # contract sec 10.7 precedent: nested stats.stats layer normalized --
    # strip {engine_version, wall_s} INSIDE the nested stats dict, then
    # compare key by key (the anchor source runs were produced by older
    # engines, so their nested version labels differ by construction)
    ns = {k: v for k, v in new["stats"].items()
          if k not in ("engine_version", "wall_s")}
    os_ = {k: v for k, v in old["stats"].items()
           if k not in ("engine_version", "wall_s")}
    diffs = {k for k in set(ns) | set(os_) if ns.get(k) != os_.get(k)}
    print(f"{tag} stats.stats normalized (excl engine_version/wall_s): "
          f"{'EQUAL' if not diffs else 'DIFFERS: ' + str(sorted(diffs))}")
    ok &= not diffs
print(f"BYTE-EQUAL {n_eq}/16; V141 ANCHORS:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
