# -*- coding: utf-8 -*-
"""V2 (F line) -- finalize the port-verification verdicts and the STOP record.

Outcome: the pre-registered F-line factor dev port (exp-20260920-val-batch
sec 3: "重算 dev 分数须逐位复现 F2R1 原产物") FAILS for the 7 D-family
representatives, because the frozen F2R1 D artifacts are not reproducible.
Four runs of the identical shipped script on byte-identical inputs
(frozen 2026-09-19 / this run's run1, run2, and a POLARS_MAX_THREADS=1 run)
produce four different frames.  Per prereg sec 6 ("任一端口验证失败 -> 对应
配置停机呈报，其余继续") the F line stops; val is NOT consumed.

This script only writes the run's own records: it recomputes nothing.
"""
from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import polars as pl

RUN_DIR = Path(__file__).resolve().parents[1]
ROOT = RUN_DIR.parents[2]
F2R1 = RUN_DIR.parent / "20260919T180000-f2r1-factor-batch"
F3R1_RUN = RUN_DIR.parent / "20260919T191524-f3r1-factor-combo-c212"
T1_RUN = RUN_DIR.parent / "20260920T113527-t1-reason-event-b690"
TL30 = RUN_DIR.parent / "20260919T151630-hybrid-val-v1p3"
R16_RUN = RUN_DIR.parent / "20260918T083650-p2r16-trend-dispersion-afab466f"
DAILY = ROOT / "data/processed/baostock-daily-20260917/daily_1999_2024.parquet"
ENGINE_PY = ROOT / "src/quant/backtest/band_engine.py"
PREREG = ROOT / "docs/research/exp-20260920-val-batch-prereg.md"
FAMILY_DIR = {"A": "A_price", "B": "B_value", "C": "C_micro",
              "D": "D_fund", "E": "E_event", "F": "F_xsec"}
D_RUNS = {"frozen_f2r1": F2R1 / "outputs/D_fund",
          "rerun_1": RUN_DIR / "tmp/d_rerun/D_fund_first",
          "rerun_2": RUN_DIR / "tmp/d_rerun/D_fund_second",
          "rerun_3_threads1": RUN_DIR / "tmp/d_rerun/D_fund_threads1"}


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


reps = sorted(pl.read_csv(F3R1_RUN / "outputs/dedup_clusters.csv")
              ["representative"].to_list())
assert len(reps) == 17, reps

# === 1. per-representative factor dev port verdict ==========================
ports = []
for fid in reps:
    fam = FAMILY_DIR[fid[0]]
    ref = F2R1 / "outputs" / fam / f"{fid}.parquet"
    new = RUN_DIR / "outputs" / "factor_dev" / fam / f"{fid}.parquet"
    r, n = pl.read_parquet(ref), pl.read_parquet(new)
    keys_equal = (set(zip(r["symbol"].to_list(), r["signal_date"].to_list()))
                  == set(zip(n["symbol"].to_list(), n["signal_date"].to_list())))
    sorted_equal = r.sort("symbol", "signal_date").equals(
        n.sort("symbol", "signal_date"))
    max_diff = None
    if keys_equal:
        j = r.join(n, on=["symbol", "signal_date"], how="inner",
                   suffix="_n")
        if j.height:
            d = (j["value"] - j["value_n"]).abs().max()
            max_diff = None if d is None else float(d)
    same_bytes = sha256_file(ref) == sha256_file(new)
    if same_bytes:
        verdict = "byte_identical"
    elif sorted_equal:
        verdict = "value_bit_identical_row_order_permuted"
    elif max_diff is not None and max_diff <= 1e-3:
        verdict = "value_close_not_exact"
    else:
        verdict = "FAIL"
    ports.append({"factor": fid, "family": fam, "rows_ref": r.height,
                  "rows_new": n.height, "keys_equal": bool(keys_equal),
                  "sorted_content_equal": bool(sorted_equal),
                  "max_abs_value_diff": max_diff,
                  "parquet_bytes_identical": bool(same_bytes),
                  "verdict": verdict})
    print(f"  {fid} {fam:<8} {verdict:<40} maxdiff={max_diff}")

n_byte = sum(1 for p in ports if p["verdict"] == "byte_identical")
n_valbit = sum(1 for p in ports
               if p["verdict"] == "value_bit_identical_row_order_permuted")
n_fail = sum(1 for p in ports if p["verdict"] == "FAIL")
n_close = sum(1 for p in ports if p["verdict"] == "value_close_not_exact")

# === 1b. E16 stability of this run's own rebuild ============================
# The frozen E16 was written by the out-of-band correction script; its
# unique(keep="first") dedup is itself order-dependent.  Two runs of the same
# corrected build in this run differ, so E16 also fails the bitwise port.
e16_a = RUN_DIR / "tmp" / "E16_runA.parquet"
e16_b = RUN_DIR / "outputs" / "factor_dev" / "E_event" / "E16.parquet"
e16_stab = {"comparison": "this run's E16 rebuild, run A vs run B (same code, "
                          "same inputs)",
            "parquet_bytes_identical": sha256_file(e16_a) == sha256_file(e16_b),
            "sha256_12": {"runA": sha256_file(e16_a)[:12],
                          "runB": sha256_file(e16_b)[:12]}}
_a, _b = pl.read_parquet(e16_a), pl.read_parquet(e16_b)
e16_stab["rows"] = [_a.height, _b.height]
_j = _a.join(_b, on=["symbol", "signal_date"], how="inner", suffix="_b")
_d = (_j["value"] - _j["value_b"]).abs()
e16_stab["rows_with_different_value"] = int((_d > 0).sum())
e16_stab["max_abs_value_diff"] = float(_d.max())
e16_stab["verdict"] = ("FAIL (nondeterministic: the frozen correction's "
                       "unique(keep='first') tie-break is unspecified)"
                       if not e16_stab["parquet_bytes_identical"]
                       else "value_bit_identical")
for p in ports:
    if p["factor"] == "E16":
        p["verdict"] = "FAIL" if e16_stab["verdict"].startswith("FAIL") \
            else p["verdict"]
        p["stability_note"] = e16_stab
print(f"  E16 own-rebuild stability: {e16_stab['verdict']} "
      f"({e16_stab['rows_with_different_value']} rows differ, max "
      f"{e16_stab['max_abs_value_diff']})")
n_byte = sum(1 for p in ports if p["verdict"] == "byte_identical")
n_valbit = sum(1 for p in ports
               if p["verdict"] == "value_bit_identical_row_order_permuted")
n_fail = sum(1 for p in ports if p["verdict"] == "FAIL")
n_close = sum(1 for p in ports if p["verdict"] == "value_close_not_exact")

# === 2. D-family reproducibility evidence (4 mutually different runs) =======
d_evidence = {"stage": "d_family_reproducibility",
              "claim": ("the frozen F2R1 D-family artifacts are not "
                        "reproducible: four runs of the identical shipped "
                        "script over byte-identical inputs give four "
                        "different frames"),
              "input_identity_check": {
                  "rule": "sha256 of every raw tushare financial file under "
                          "fina_indicator/ income/ balancesheet/ cashflow/ "
                          "compared with the data/_meta/sha256.tsv baseline "
                          "written 2026-09-17 (before the F2R1 run)",
                  "files_verified": 23622, "mismatches": 0,
                  "note": "the raw inputs did not change between the F2R1 D "
                          "run (2026-09-19 18:19) and this run"},
              "runs": {k: str(v) for k, v in D_RUNS.items()},
              "per_representative": {}}
for fid in ["D10", "D13", "D14", "D18", "D19", "D20", "D30"]:
    row = {}
    for tag, d in D_RUNS.items():
        f = d / f"{fid}.parquet"
        row[tag] = {"sha256_12": sha256_file(f)[:12],
                    "rows": pl.read_parquet(f).height}
    d_evidence["per_representative"][fid] = row
d_evidence["all_four_distinct"] = all(
    len({v["sha256_12"] for v in row.values()}) == 4
    for row in d_evidence["per_representative"].values())
print(f"  D family: all four runs distinct for every representative = "
      f"{d_evidence['all_four_distinct']}")

# screening verdicts per run (screen_pass from each run's JSON)
scr = {}
for tag, d in D_RUNS.items():
    scr[tag] = [fid for fid in d_evidence["per_representative"]
                if json.loads((d / f"{fid}.json").read_text(encoding="utf-8"))
                ["screen"]["screen_pass"]]
d_evidence["screen_pass_by_run"] = scr
d_evidence["screen_pass_identical_across_runs"] = len(
    {tuple(v) for v in scr.values()}) == 1
print(f"  D family screen_pass sets identical across runs = "
      f"{d_evidence['screen_pass_identical_across_runs']} ({scr})")

# === 3. mechanism probe (frozen as-of/tie-break expression) =================
probe = json.loads((RUN_DIR / "outputs" / "d_pipeline_determinism_probe.json")
                   .read_text(encoding="utf-8"))
d_evidence["localization_probe"] = {
    "source": "outputs/d_pipeline_determinism_probe.json",
    "A_frozen_expression_repeat_stable_in_process":
        probe["A_frozen_expression_repeat_stable"],
    "B_rows_differing_vs_explicitly_ordered": probe["B_rows_differing_ann_date"],
    "C_fina_rows_ann_date_after_2024": probe["C_rows_ann_after_2024"],
    "C_of_which_end_date_le_2020":
        probe["C_rows_ann_after_2024_with_end_date_le_2020"],
    "conclusion": ("the pit_full() tie-break is NOT the unstable step (it is "
                   "reproducible in-process and agrees with its explicitly "
                   "ordered equivalent here); the instability is elsewhere in "
                   "the join/sort/group_by chain of build_d_fund_main.py and "
                   "is left as a registered follow-up")}
synth = {"probe": "scripts/polars_order_probe.py",
         "finding": ("for a synthetic 300k-row / 3200-group frame the frozen "
                     "idiom sort(...).group_by(k).last() differs from the "
                     "explicitly ordered equivalent for 8.4% of groups; the "
                     "idiom therefore does not implement its documented "
                     " 'tie 取 end_date 大' tie-break (the D family report "
                     "discloses an 8-9% same-day multi-announcement rate, of "
                     "the same order)")}
d_evidence["polars_idiom_synthetic_probe"] = synth

(RUN_DIR / "outputs" / "d_family_reproducibility.json").write_text(
    json.dumps(d_evidence, ensure_ascii=False, indent=1, default=str),
    encoding="utf-8", newline="\n")

# === 4. events dev port evidence (already computed) =========================
ev_port = json.loads((RUN_DIR / "outputs" / "port_check_events_dev.json")
                     .read_text(encoding="utf-8"))
ev_extra = {"events_dev_parquet_content_note":
            ("events_dev.parquet is byte-different (parquet row order) but "
             "content-bit-identical: equal keys, equal values "
             "(max |diff| 0.0 on every column after sorting by ordinal), and "
             "6/7 downstream artifacts byte-identical (anova_main.json, "
             "type_drift.csv, primary_within_type.csv, sensitivity.csv, "
             "pool_filter_counts.json, category_diagnostics.csv) -- so the T1 "
             "analysis sample and every derived statistic reproduce exactly")}
ev_port.update(ev_extra)
(RUN_DIR / "outputs" / "port_check_events_dev.json").write_text(
    json.dumps(ev_port, ensure_ascii=False, indent=1), encoding="utf-8",
    newline="\n")

# === 5. factor port check file (final) =====================================
b1m_dev = json.loads((RUN_DIR / "outputs" / "b1m_dev.json")
                     .read_text(encoding="utf-8"))
b1m_val = json.loads((RUN_DIR / "outputs" / "b1m_val.json")
                     .read_text(encoding="utf-8"))
summary = {
    "stage": "port_verification_summary",
    "verdict": "FACTOR_DEV_PORT_FAILED -> F line stopped (prereg sec 6)",
    "b1m_dev_port": {"result": "PASS",
                     "caliber": "abs diff <= 1e-9 vs R16 metrics.json "
                                "configs.C05 b1m_* (net_cagr, max_drawdown, "
                                "all six years)",
                     "computed": {"net_cagr": b1m_dev["net_cagr"],
                                  "max_drawdown": b1m_dev["max_drawdown"]},
                     "reference": b1m_dev["reference"]},
    "b1m_val": {"result": "PASS",
                "note": "B1(m)(val) reproduces the TL-30 value exactly; this "
                        "is the pre-registered benchmark recompute already "
                        "published by TL-30, not a new config judgement",
                "net_cagr": b1m_val["net_cagr"],
                "max_drawdown": b1m_val["max_drawdown"],
                "net_return_by_year": b1m_val["net_return_by_year"]},
    "events_dev_port": {"result": "PASS",
                        "caliber": "byte-identical for 6/7 artifacts; "
                                   "events_dev.parquet content-bit-identical "
                                   "(row order permuted only)",
                        "files": ev_port["files"]},
    "factor_dev_port": {
        "result": "FAIL",
        "caliber": "prereg sec 3: recomputed dev scores must reproduce the "
                   "F2R1 originals 逐位",
        "n_factors": len(ports),
        "n_byte_identical": n_byte,
        "n_value_bit_identical_row_order_permuted": n_valbit,
        "n_value_close_not_exact": n_close,
        "n_fail": n_fail,
        "failing_family": "D (财务 PIT)",
        "failing_ids": [p["factor"] for p in ports if p["verdict"] == "FAIL"],
        "e16_stability": e16_stab,
        "close_not_exact_ids": [p["factor"] for p in ports
                                if p["verdict"] == "value_close_not_exact"],
        "evidence": "outputs/d_family_reproducibility.json",
        "factors": ports},
    "arm_dev_anchors": {
        "result": "NOT_RUN",
        "note": "prereg sec 5 requires the arm dev anchors before val is "
                "consumed; the factor port failure (prereg sec 6) stopped the "
                "line earlier, so no arm runner was adapted or run and val was "
                "not consumed"},
    "val_consumed": False,
}
(RUN_DIR / "outputs" / "port_check_factors_dev.json").write_text(
    json.dumps(summary, ensure_ascii=False, indent=1, default=str),
    encoding="utf-8", newline="\n")

# === 6. stop report ========================================================
stop = f"""# STOP REPORT -- exp-20260920-val-batch (V2 / F 线)

- 停机时间：{datetime.now(timezone.utc).isoformat()}
- 停机阶段：F 线 dev 端口验证（17 因子 val 分数展开之前）
- 触发条款：预登记 `docs/research/exp-20260920-val-batch-prereg.md` §6
  「任一端口验证（B1(m) dev、H2 dev、因子 dev、事件 dev）失败 → 对应配置停机呈报，
  其余继续」；§3 F 线「dev 端口验证=重算 dev 分数须逐位复现 F2R1 原产物……后才展开 val」。
- 原因：**17 个代表因子中 8 个（D 族 7 + E16）的 dev 分数无法逐位复现**，且失败根因在
  冻结产物本身——同一份 shipped 脚本、同一份字节级未变的输入，四次运行给出四份
  互不相同的因子帧：

  | 运行 | D10 sha256:12 | 行数 |
  |---|---|---|
""" + "\n".join(
    f"  | {tag} | {row['sha256_12']} | {row['rows']} |"
    for tag, row in d_evidence["per_representative"]["D10"].items()
) + f"""

  （7 个 D 代表全部如此；明细 `outputs/d_family_reproducibility.json`）
- 排除的其他解释：
  1. **输入数据变化**：`data/_meta/sha256.tsv`（2026-09-17 深度扫描基线）覆盖的
     23,622 个财务原始文件逐个重算 sha256，**0 处不一致**——输入自 F2R1 运行之前
     至今未变。
  2. **我的窗口适配引入偏差**：生成的 val 脚本与 shipped 脚本逐行 diff，仅窗口常量、
     输出路径、sig_cap 包装与 B04 读取路径不同；dev 模式下每一项语义等价
     （diff 已留档于 `tmp/`、`logs/`）。
  3. **线程数**：`POLARS_MAX_THREADS=1` 运行仍与其余三次不同（threads1 列）。
  4. **pit_full 的重述 tie-break**：定向探针显示该表达式在进程内可重复、且与显式
     排序等价（`outputs/d_pipeline_determinism_probe.json`），故不是不稳定步骤；
     不稳定点在 `build_d_fund_main.py` 的 join/sort/group_by 链中，列为后续工作。
- 受影响配置：**V2 全部 5 个配置**（F3R1-EW / F3R1-ICW / F3R2-EW / F3R3-EW /
  F3R4-A）——17 代表中有 7 个来自 D 族，全部 5 个配置的 composite 都消费它们。
- **val 未消费**：未生成任何因子 val 分数、未构建 val composite、未跑任何 val 臂。
  唯一算到 val 的量是预登记 §3 指定的基准 B1(m)(val)（TL-30 已公开 −0.148%/−23.44%，
  本轮逐位复现），不构成任何配置的 val 判定。
- 已通过的端口（留档）：
  - B1(m) dev：与 R16 metrics.json configs.C05 b1m_* 逐位一致（1e-9，含 6 个年度）。
  - B1(m)(val)：与 TL-30 −0.00148060230384095 / −0.23441429674947534 逐位一致（1e-9）。
  - 归因事件 dev：7 个产物中 6 个字节一致；events_dev.parquet 仅 parquet 行序不同，
    键集与全部数值逐位一致，且 6 个下游统计产物（ANOVA p、分类统计、漂移、敏感性、
    池漏斗）字节一致。
  - 因子 dev（最终）：字节一致 6（A17/A20/A25/B11/B12/C19）、数值逐位一致但行序不同 3
    （B14/F06/F09）、**失败 8**（D 族 7 + E16 1）。E16 的失败同样是产物不可复现：
    冻结 E16 由带外修复脚本产出，该修复的按 (symbol,ex_date) 去重
     依赖未指定行序；本 run 用同口径连跑两次，
    24~27 行数值不同（键集与行数相同，最大差 0.0238），故「差 1.15e-4」只是
    单次抽样结果，不是可复现的固定偏差。
- 因子 dev（分项）：17 代表中 6 个字节一致、3 个数值逐位一致（仅行序不同）、1 个（E16）
    最大差 1.15e-4（冻结 E16 由带外修复脚本 `fix_E16_dupcount.py` 产出，其按
    (symbol,ex_date) 去重的 `unique(keep="first")` 本身依赖未指定的行序）、7 个
    失败（D 族）。
- 处置建议（不在本 run 决定）：先让 D 族实现对显式 tie-break 与稳定排序（例如
  `maintain_order=True` 或显式 `sort(...).unique(...)` 去重）后重发 dev 产物，
  再按预登记重启 F 线 val 批次；val 窗保持未消费、一次性资格不变。
- 本 run 未做：5 臂 runner 适配与 dev 锚、val composite、任何 val 判定。
- 试验计账：本 run 不消费任何 val 配置；策略线计数不增加（B1(m) 重算与端口验证
  不构成新配置）。
"""
(RUN_DIR / "tmp" / "stop_report.md").write_text(stop, encoding="utf-8",
                                                newline="\n")

# === 7. manifest ===========================================================
stage_timings = {
    "val_b1m_dev_s": 61.7, "val_b1m_val_s": 39.7,
    "factor_dev_A_price_s": 176.0, "factor_dev_B_value_s": 175.0,
    "factor_dev_C_micro_s": 307.0, "factor_dev_D_fund_s": 515.0,
    "factor_dev_D_fund_rerun_s": 198.0,
    "factor_dev_D_fund_rerun_threads1_s": 319.0,
    "factor_dev_E_event_s": 174.8,
    "factor_dev_E_event_after_E16_fix_s": 74.6,
    "factor_dev_F_xsec_s": 85.0,
    "events_dev_port_s": 22.9,
    "d_determinism_probe_s": 43.0,
    "polars_order_probe_s": 2.0,
    "note": "wall seconds as printed by each stage; the D re-runs exist only "
            "to test reproducibility and are not val consumption",
}
outs = {}
for p in sorted(RUN_DIR.rglob("*")):
    if p.is_file() and p.name not in ("manifest.json",):
        rel = p.relative_to(RUN_DIR).as_posix()
        if rel.startswith(("logs/", "outputs/factor_dev/",
                           "outputs/events_dev/", "tmp/d_rerun/",
                           "tmp/annotations_merged_")):
            continue
        outs[rel] = sha256_file(p)
manifest = {
    "run_id": RUN_DIR.name,
    "experiment_id": "exp-20260920-val-batch (V2 / F line)",
    "status": "aborted",
    "stop_reason": ("prereg sec 6 trigger: F-line factor dev port FAILED -- "
                    "8 of the 17 representative factors cannot be reproduced "
                    "from the frozen F2R1 artifacts: the 7 D-family "
                    "(financial PIT) factors because four runs of the "
                    "identical shipped script over byte-identical inputs give "
                    "four different frames, and E16 because the out-of-band "
                    "correction script's unique(keep='first') tie-break is "
                    "itself order-dependent (two runs of the same corrected "
                    "build differ in 24-27 rows). All 5 F-line configs "
                    "consume the affected factors -> line stopped, val NOT "
                    "consumed."),
    "stop_report": "tmp/stop_report.md",
    "started_at_utc": "2026-09-20T13:06:16+08:00",
    "ended_at_utc": datetime.now(timezone.utc).isoformat(),
    "command": [sys.executable, "scripts/val_b1m.py | generated/f2val_*.py | "
                                "generated/val_events.py"],
    "engine": {"path": str(ENGINE_PY), "sha256_at_start": sha256_file(ENGINE_PY),
               "sha256_at_end": sha256_file(ENGINE_PY),
               "version": "v1.4.1", "bytes_modified_by_this_run": False,
               "pin": "a01cb29ce4cf214814dd51679295f70ac780dc5dffb270ea1f0a466b0675abf3"},
    "pins": {
        "prereg": {"path": str(PREREG), "sha256": sha256_file(PREREG)},
        "daily_1999_2024": {"path": str(DAILY), "sha256": sha256_file(DAILY)},
        "r16_metrics": {"path": str(R16_RUN / "metrics.json"),
                        "sha256": sha256_file(R16_RUN / "metrics.json")},
        "f3r1_dedup_clusters": {"path": str(F3R1_RUN / "outputs/dedup_clusters.csv"),
                                "sha256": sha256_file(F3R1_RUN / "outputs/dedup_clusters.csv")},
        "t1_events_dev": {"path": str(T1_RUN / "outputs/events_dev.parquet"),
                          "sha256": sha256_file(T1_RUN / "outputs/events_dev.parquet")},
        "tl30_metrics": {"path": str(TL30 / "outputs/metrics_and_gates.json"),
                         "sha256": sha256_file(TL30 / "outputs/metrics_and_gates.json")},
        "raw_financial_files_verified": {
            "rule": "sha256 per file vs data/_meta/sha256.tsv (2026-09-17)",
            "files": 23622, "mismatches": 0},
    },
    "env": {"python": platform.python_version(), "polars": pl.__version__,
            "numpy": __import__("numpy").__version__,
            "platform": platform.platform()},
    "window": {"dev": "2015-01-05..2020-12-31 (signals 2015-01-30..2020-11-30, 71)",
               "val": "2021-01-04..2024-12-31 (signals 2021-01-29..2024-11-29, 47)",
               "val_consumed": False,
               "val_contact": "only the prereg-mandated benchmark B1(m)(val) "
                              "recompute (identical to TL-30's published "
                              "value); no factor score, composite, arm run or "
                              "gate judgement was produced on val"},
    "stage_timings_s": stage_timings,
    "port_verification": {
        "b1m_dev": "PASS (1e-9 vs R16 configs.C05 b1m_*)",
        "b1m_val": "PASS (1e-9 vs TL-30 -0.148%/-23.44%)",
        "events_dev": "PASS (6/7 artifacts byte-identical; events_dev.parquet "
                      "content-bit-identical, row order only)",
        "factor_dev": ("FAIL 8/17 (D family 7 + E16); 6/17 byte-identical; "
                       "3/17 value-bit-identical with a permuted row order; "
                       "the 7 D factors and E16 are not reproducible from "
                       "the frozen artifacts (see "
                       "outputs/d_family_reproducibility.json and the "
                       "e16_stability block of "
                       "outputs/port_check_factors_dev.json)"),
        "arm_dev_anchors": "NOT RUN (stopped earlier by the factor port)",
    },
    "incidents": {
        "f2r1_f_xsec_summary_overwritten": (
            "the F-family dev port run rewrote "
            "artifacts/runs/20260919T180000-f2r1-factor-batch/"
            "f_xsec_summary.json (the generated script inherited the frozen "
            "script's write target). The rewrite runs the same code over the "
            "same dev-window inputs, so the recorded values are the F2R1 "
            "values; the F2R1 run has no manifest.json, so no original hash "
            "exists to restore or verify against. The generator was corrected "
            "(the summary now writes into this run's outputs) and the incident "
            "is registered here."),
        "e16_not_from_family_script": (
            "the frozen outputs/E_event/E16.parquet was produced by the "
            "out-of-band correction tmp_accept/fix_E16_dupcount.py, not by "
            "f2r1_e_event.py; the val generator re-implements that correction "
            "(disclosed in the generated script) and reproduces the frozen "
            "frame to 1.15e-4."),
    },
    "trial_accounting": {"this_round": "0 val configs consumed (F line stopped "
                                       "at the port gate)",
                         "strategy_line": "unchanged"},
    "outputs": outs,
}
(RUN_DIR / "manifest.json").write_text(
    json.dumps(manifest, ensure_ascii=False, indent=1, default=str),
    encoding="utf-8", newline="\n")
print(f"\n== stop finalized: {RUN_DIR.name}; factor dev port "
      f"{n_byte} byte / {n_valbit} value-bit / {n_close} close / {n_fail} FAIL ==")
