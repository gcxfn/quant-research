"""主对话独立三锚比对（不复用代理的比对脚本）。"""
import filecmp, json, pathlib, sys

ROOT = pathlib.Path(r"D:\量化")
RUN = ROOT / "artifacts/runs/20260919T222634-engine-v14-impl"
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
for name, (new_dir, src_dir, files) in PAIRS.items():
    for fn in files:
        a, b = new_dir / fn, src_dir / fn
        if not a.exists():
            print(f"{name}: MISSING replay file {fn}"); ok = False; continue
        eq = filecmp.cmp(a, b, shallow=False)
        ok &= eq
        print(f"{name}: {fn} {'BYTE-EQUAL' if eq else '*** DIFFERS ***'}")
# stats 归一化比对（锚 2/3）
for tag, fn, src in (("anchor2", "H2-A0_stats.json",
                      ROOT / "artifacts/runs/20260919T063022-hybrid-v2-2k5b/outputs/H2-A0_stats.json"),
                     ("anchor3", "F3R3-A0_stats.json",
                      ROOT / "artifacts/runs/20260919T201500-f3r3-industry-cap-4b2e/outputs/F3R3-A0_stats.json")):
    new = json.loads((RUN / "outputs" / fn).read_text(encoding="utf-8"))
    old = json.loads(src.read_text(encoding="utf-8"))
    diffs = {k for k in set(new) | set(old)
             if new.get(k) != old.get(k) and k not in ("engine_version", "wall_s")}
    print(f"{tag} stats normalized: {'EQUAL' if not diffs else 'DIFFERS: ' + str(sorted(diffs))}")
    ok &= not diffs
print("MAIN-ACCEPT ANCHORS:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
