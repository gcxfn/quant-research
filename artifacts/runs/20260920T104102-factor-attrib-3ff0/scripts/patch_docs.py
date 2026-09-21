# -*- coding: utf-8 -*-
"""exp-20260920-factor-attribution -- doc updates (ledger TL-38, README status,
main plan 40th update) via literal replacement + assertions."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(r"D:/量化")

TL38_ROW = (
    "| TL-38 | 2026-09-20 | exp-20260920-factor-attribution | "
    "F3 存量审计（归因 + 留一，\"17 代表里有没有坏因子\"；FA-S2 直读 F2R1 分数 "
    "parquet、席位权重贡献原子、sanity 门、§5.1 嫌疑线→§5.2 定罪线→§5.3 清洁采纳线"
    "全机械；引擎 v1.4.1 非 zones 路径，leave-zero-out 锚为前置门槛） "
    "| 19 运行 18 新配置（锚不计） | 1（锚复刻） | "
    "**H1 否证：嫌疑名单空——17 因子贡献 t 全正（+0.19~+1.71）、负年数≤3<4**；"
    "sanity corr 0.9979/符号 100% 过；FA-S2 重建 composite 与 F3R1 parquet "
    "逐位一致（max diff 0）；定罪/清洁机械跳过；留一矩阵描述性在档（剔 B12/D30/B14 "
    "ΔCAGR +1.88/+1.62/+1.56pp 且回撤改善——看过结果不动作，动因集须新预登记）；"
    "**F3 维持 17 因子原样，\"alpha=集中度形态\"加强** | 275→**293** | "
    "run `20260920T104102-factor-attrib-3ff0`；锚五帧 .equals 5/5 + net_cagr "
    "逐位相等（v1.4.1≡v1.3 非 zones 再实证）；归因 11s+锚 42s+留一 205s、"
    "RSS≤3.38GB；[结果](../research/exp-20260920-factor-attribution.md) | val 零接触 |")

README_SEG = (
    "**F3 存量审计收官（归因+留一，\"17 代表里有没有坏因子\"；[预登记]"
    "(docs/research/exp-20260920-factor-attribution-prereg.md)+[结果]"
    "(docs/research/exp-20260920-factor-attribution.md)；引擎 v1.4.1 非 zones "
    "路径）**：**H1 否证（嫌疑名单空）**——17 代表贡献 t 值全为正（+0.19~+1.71）、"
    "无一过 §5.1 嫌疑线；FA-S2 重建 composite 与 F3R1 parquet 逐位一致；sanity "
    "corr 0.9979/符号 100%；leave-zero-out 锚五帧逐字节=底盘（v1.4.1≡v1.3 再实证）；"
    "留一矩阵描述性在档（剔 B12/D30/B14 ΔCAGR +1.88/+1.62/+1.56pp 且回撤改善，"
    "看过结果不动作、动因集须新预登记）；**F3 组合维持 17 因子原样，\"alpha=集中度"
    "形态\"结论加强，对 T1 下游零影响**。试验累计 **293**（TL-38）。")

PLAN_PARA = (
    "2026-09-20（第四十次更新，F3 存量审计收官：归因+留一 H1 否证）："
    "① **预登记执行零停机**（exp-20260920-factor-attribution，run "
    "`20260920T104102-factor-attrib-3ff0`）：FA-S2 走直读分支——F2R1 族逐月分数 "
    "parquet 直接可用，composite 分量按 F3R1 §4 构造重建与 `F3-EW_composite.parquet`"
    " 逐位一致（3 日期×25 股 75 点 max diff 0、键集相等）；r 沿 F2R1 eval harness"
    "（h=20、T+1 起 close/preclose 复利，面板进 harness 前截断 ≤2020-12-31，"
    "68/71 月，2015 前三月 harness min_history 截断）；席位权重逐字取底盘 sleeve log"
    "（每席 w_T=e_T×0.06/0.90，FA-S4）。"
    "② **归因（EW 主表）**：17 因子贡献 t 全正（+0.187 D19 ~ +1.714 E16）、"
    "负年数≤3，§5.1 嫌疑线 0 命中；sanity（Σ(1/17)c_i vs 席位实现收益，65 月）"
    "corr 0.9979、符号一致 100% 过门（ICW 对照 0.9976/98.5%）；贡献相关矩阵全正"
    "（min 0.362 B14×E16，非对角均值 0.753）。"
    "③ **留一**：leave-zero-out 锚五帧 .equals 全 True + net_cagr 逐位相等"
    "（v1.4.1 非 zones ≡ v1.3 再实证）；17 次留一全跑，最大 ΔCAGR=剔 B12 +1.88pp、"
    "剔 D30 +1.62pp、剔 B14 +1.56pp 且 maxDD 均改善——按冻结纪律定罪线只作用于"
    "嫌疑名单（空），0 定罪 0 观察、清洁组合跳过；留一矩阵为描述性证据，"
    "动因集须新预登记。"
    "④ **判定**：H1 否证/H0 确认，F3 组合维持 17 因子原样，对 T1 下游与后续实验"
    "零影响；\"alpha=集中度形态\"结论加强。台账 TL-38（275→293）、README 已更。"
    "悬置不变：R3-05/R3-06 等 6 配置 val 与 F 线生产化方向待用户批准。")


def patch(path: Path, old: str, new: str, expect: int = 1) -> None:
    t = path.read_text(encoding="utf-8")
    n = t.count(old)
    assert n == expect, f"{path.name}: anchor found {n} times (expect {expect}): {old[:60]!r}"
    t2 = t.replace(old, new)
    assert t2 != t and len(t2) > len(t)
    path.write_text(t2, encoding="utf-8", newline="\n")
    print(f"patched {path.name}")


# 1) ledger: TL-38 right after the TL-37 row line (idempotent)
ledger = ROOT / "docs/evidence/trial-ledger.md"
lines = ledger.read_text(encoding="utf-8").split("\n")
idx = [i for i, l in enumerate(lines) if l.startswith("| TL-37 |")]
assert len(idx) == 1, f"TL-37 rows found: {len(idx)}"
i = idx[0]
assert "273→**275**" in lines[i], "TL-37 line content unexpected"
if any(l.startswith("| TL-38 |") for l in lines):
    j = [k for k, l in enumerate(lines) if l.startswith("| TL-38 |")][0]
    assert j == i + 1, f"TL-38 at line {j + 1}, expected right after TL-37 ({i + 2})"
    assert "275→**293**" in lines[j], "TL-38 row content unexpected"
    print("trial-ledger.md already patched (TL-38 verified in place)")
else:
    lines.insert(i + 1, TL38_ROW)
    ledger.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    print("patched trial-ledger.md (TL-38 inserted)")

# 2) README: new status segment after the F4R2 sentence, before 台账补登
readme = ROOT / "README.md"
patch(readme,
      "推荐转 R3-06 生产化前置**。台账补登 TL-33~35",
      "推荐转 R3-06 生产化前置**。" + README_SEG + "台账补登 TL-33~35")

# 3) main plan: append the 40th update paragraph at the end
plan = ROOT / "docs/plans/daily-short-term-rebuild.md"
t = plan.read_text(encoding="utf-8")
assert "第四十次更新" not in t, "40th update already present"
if not t.endswith("\n"):
    t += "\n"
t += "\n" + PLAN_PARA + "\n"
plan.write_text(t, encoding="utf-8", newline="\n")
print("patched daily-short-term-rebuild.md (40th update appended)")
