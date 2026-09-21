# -*- coding: utf-8 -*-
"""收官双签 · 校验脚本 1：交付物一致性（只读）。

 1) manifest 全部输出哈希复算；
 2) metrics_and_gates.json vs report.md 表（转写自报告的期望值）逐数核对；
 3) B1(m)/B3' 与 R16 权威 metrics.json 完全一致；
 4) 门 8 双口径：mapped 与 raw blend 全部 <95%（8/8）且与披露区间一致；
 5) C06/C08 边距提取（门 1/门 2/门 8）；
 6) 判定逻辑核对（0/8 eliminated、无 untradeable、val 未消费标记）。
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

RUN = Path(r"D:\量化\artifacts\runs\20260918T145900-p3r1-dev-262f")
R16 = Path(r"D:\量化\artifacts\runs\20260918T083650-p2r16-trend-dispersion-afab466f")
FAILS: list[str] = []
PASS = 0


def check(cond, label):
    global PASS
    if cond:
        PASS += 1
        print(f"  [OK ] {label}")
    else:
        FAILS.append(label)
        print(f"  [FAIL] {label}")


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


manifest = json.loads((RUN / "manifest.json").read_text(encoding="utf-8"))
mg = json.loads((RUN / "outputs" / "metrics_and_gates.json").read_text(encoding="utf-8"))
r16m = json.loads((R16 / "metrics.json").read_text(encoding="utf-8"))

print("== 1) manifest 输出哈希 ==")
bad = [rel for rel, want in manifest["outputs"].items()
       if not (RUN / rel).exists() or sha256_file(RUN / rel) != want]
check(not bad, f"全部 {len(manifest['outputs'])} 个输出哈希匹配 manifest（bad={bad}）")
check(sha256_file(Path(r"D:\量化\src\quant\backtest\band_engine.py"))
      == manifest["engine"]["sha256"] == manifest["engine_fix_ENGINE_1"]["sha256_after"],
      "当前引擎哈希 == manifest engine == ENGINE-1 sha256_after")

print("== 2) metrics_and_gates vs report.md 表 ==")
# 期望值转写自 run 目录 report.md 表格（人工抄录，独立于生成脚本）
report_expect = {
    "C01": dict(cagr=0.0517, b1=0.0060, adv=3, mdd=-0.3061, to=1.37, w=0.218,
                exec=0.914, n_pass=5,
                failed=["3_advantage_years_ge_5_of_6", "4_mdd_le_20pct_and_le_B1m",
                        "8_execution_rate_ge_95pct"], verdict="eliminated"),
    "C02": dict(cagr=-0.0233, b1=0.0060, adv=3, mdd=-0.4833, to=2.20, w=0.202,
                exec=0.933, n_pass=2, verdict="eliminated"),
    "C03": dict(cagr=0.0060, b1=0.0186, adv=4, mdd=-0.4991, to=1.76, w=0.141,
                exec=0.911, n_pass=3, verdict="eliminated"),
    "C04": dict(cagr=-0.0568, b1=0.0186, adv=4, mdd=-0.6152, to=2.40, w=0.138,
                exec=0.928, n_pass=2, verdict="eliminated"),
    "C05": dict(cagr=0.0508, b1=0.0060, adv=3, mdd=-0.3357, to=1.42, w=0.135,
                exec=0.917, n_pass=5, verdict="eliminated"),
    "C06": dict(cagr=0.0025, b1=0.0060, adv=3, mdd=-0.4847, to=2.09, w=0.145,
                exec=0.911, n_pass=4,
                failed=["2_excess_vs_B1m_ge_2pp", "3_advantage_years_ge_5_of_6",
                        "4_mdd_le_20pct_and_le_B1m", "8_execution_rate_ge_95pct"],
                verdict="eliminated"),
    "C07": dict(cagr=0.0022, b1=0.0186, adv=4, mdd=-0.4664, to=1.61, w=0.143,
                exec=0.918, n_pass=3, verdict="eliminated"),
    "C08": dict(cagr=-0.0386, b1=0.0186, adv=4, mdd=-0.5737, to=2.07, w=0.085,
                exec=0.914, n_pass=2, verdict="eliminated"),
}
for cid, exp in report_expect.items():
    m = mg["metrics"][cid]
    g = mg["gates"][cid]["dev"]
    d = mg["disclosures"][cid]
    ok = (abs(m["net_cagr"] - exp["cagr"]) < 5e-5
          and abs(m["b1m_net_cagr"] - exp["b1"]) < 5e-5
          and g["advantage_years"] == exp["adv"]
          and abs(m["max_drawdown"] - exp["mdd"]) < 5e-5
          and abs(m["max_one_side_turnover"] - exp["to"]) < 5e-3
          and abs(m["max_single_name_weight"] - exp["w"]) < 5e-4
          and abs(m["execution_rate"] - exp["exec"]) < 5e-4
          and 8 - len(g["failed_gates"]) == exp["n_pass"]
          and d["verdict"] == exp["verdict"]
          and (exp.get("failed") is None or g["failed_gates"] == exp["failed"]))
    check(ok, f"{cid} JSON 与 report 表一致（CAGR/回撤/优势年/换手/权重/执行率/失败门/判定）")

print("== 3) B1(m)/B3' 与 R16 权威值一致 ==")
b1_ok = all(
    mg["metrics"][cid]["b1m_net_cagr"] == r16m["configs"][cid]["b1m_net_cagr"]
    and mg["metrics"][cid]["b1m_max_drawdown"] == r16m["configs"][cid]["b1m_max_drawdown"]
    and mg["metrics"][cid]["b1m_net_return_by_year"] == r16m["configs"][cid]["b1m_net_return_by_year"]
    for cid in report_expect)
check(b1_ok, "8 配置 B1(m) CAGR/回撤/逐年 与 R16 metrics.json 完全相等")
check(mg["b3prime_dev_mean_net_cagr"] == r16m["B3prime_dev_mean_net_cagr"],
      "B3' dev 均值与 R16 完全相等")
check(mg.get("b3prime_noise_band_same_path") is not None, "B3' 同路径噪声带已披露")

print("== 4) 门 8 双口径 ==")
for cid in report_expect:
    m = mg["metrics"][cid]
    d = mg["disclosures"][cid]
    st_signals = None
    # 从披露的订单口径成交率反推 raw blend 需要订单数——直接用 JSON 里的原始计数
    exec_map = m["execution_rate"]
    fr = d["order_fill_rate"]
    check(abs(d["gate8_mapped_execution_rate"] - exec_map) < 1e-12,
          f"{cid} gate8_mapped == metrics.execution_rate ({exec_map*100:.1f}%)")
    check(0.90 <= exec_map < 0.95, f"{cid} 映射执行率在 [90,95) 区间: {exec_map*100:.1f}%")
    check(fr["buy"] < 0.95 and fr["sell"] < 0.95,
          f"{cid} 原始订单口径 fill 买/卖均 <95%: {fr['buy']*100:.1f}/{fr['sell']*100:.1f}%")
mapped_all = [mg["metrics"][c]["execution_rate"] for c in report_expect]
check(all(0.91 <= x <= 0.935 for x in mapped_all),
      f"映射执行率全部落在披露区间 91–93.3%: {sorted(round(x*100,1) for x in mapped_all)}")
check(all("8_execution_rate_ge_95pct" in mg["gates"][c]["dev"]["failed_gates"]
          for c in report_expect), "门 8 对 8/8 配置全部失败（<95%）")

print("== 5) C06/C08 边距 ==")
m6 = mg["metrics"]["C06"]
g6 = mg["gates"]["C06"]["dev"]
print(f"    C06: net {m6['net_cagr']*100:+.2f}% (门1 边距 +{m6['net_cagr']*100:.2f}pp); "
      f"excess {m6['excess_vs_b1m']*100:+.2f}pp (门2 短差 {2.0 - m6['excess_vs_b1m']*100:.2f}pp); "
      f"门8 距离 {95 - m6['execution_rate']*100:.1f}pp")
check(abs(m6["excess_vs_b1m"] * 100 - (-0.35)) < 0.01,
      "C06 excess = -0.35pp（即门 2 距离 +2pp 需 +2.35pp，非 0.35pp 可翻转）")
b3_t = mg["b3prime_dev_mean_net_cagr"]["T200-40"]
print(f"    C06 门7: net {m6['net_cagr']*100:+.2f}% vs B3'+1pp = {(b3_t+0.01)*100:+.2f}% "
      f"-> 边距 {(m6['net_cagr']-b3_t-0.01)*100:+.2f}pp（通过）")
check(m6["net_cagr"] >= b3_t + 0.010, "C06 门 7 通过（与 failed_gates 无门 7 一致）")
m8 = mg["metrics"]["C08"]
print(f"    C08: net {m8['net_cagr']*100:+.2f}%; 门2 短差 {2.0 - m8['excess_vs_b1m']*100:.2f}pp; "
      f"门8 距离 {95 - m8['execution_rate']*100:.1f}pp")

print("== 6) 判定与 val 纪律 ==")
check(all(mg["disclosures"][c]["verdict"] == "eliminated" for c in report_expect),
      "8/8 判定 = eliminated")
check(mg["advanced_to_validation"] is False and mg["val_consumed"] is False,
      "advanced_to_validation=False, val_consumed=False")
check(all(d["verdict"] != "untradeable_under_contract" for d in mg["disclosures"].values()),
      "无 untradeable_under_contract 判定（整体 fill 均 ≥30% 或不在噪声带）")
blend = {}
for cid in report_expect:
    d = mg["disclosures"][cid]
    blend[cid] = (d["order_fill_rate"]["buy"], d["order_fill_rate"]["sell"])
print(f"    订单口径 fill 区间: 买 {min(v[0] for v in blend.values())*100:.1f}"
      f"–{max(v[0] for v in blend.values())*100:.1f}% / "
      f"卖 {min(v[1] for v in blend.values())*100:.1f}–{max(v[1] for v in blend.values())*100:.1f}%")

print()
print(f"校验 1 断言: {PASS} passed, {len(FAILS)} failed")
if FAILS:
    for f in FAILS:
        print("  FAILED:", f)
    sys.exit(1)
print("ALL CONSISTENCY CHECKS PASSED")
