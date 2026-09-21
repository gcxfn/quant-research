# 残差均值回归主线 R1 — Codex 工件复算验证材料包（2026-09-09）

**审核性质：正式运行工件的复算验证。运行前审核四轮已闭合（PASS，D-2026-09-09-14）；本包请求对产出工件做独立复算与一致性验证，确认后可按冻结判据落锤判定。**

## 主对话按冻结判据宣布的判定（待 Codex 复算确认）

**FAIL。** 阶段 C（m20_z05，2024-01-01→2026-08-28）：17bps 机会净期望 +0.1076%，95% CI [−0.8338%, +1.2406%] 下界<0 → `ci_lower_not_above_zero`。事件数 237≥30 ✓、Top5 贡献占比 39.17%≤50% ✓、非退化 ✓——三项辅助条件全过，主指标 CI 未过。本轮封顶探索级结论：**该候选在留出窗无正期望证据，按预登记终止，不追加调参。**

## 送审工件

| 路径 | 说明 |
|---|---|
| `artifacts/mr-statarb/round-20260909/screening.json` | 阶段 A 全量逐股记录（2.5MB；含每股三口径 n_market_days/n_eps_days/n_signal_days） |
| `artifacts/mr-statarb/round-20260909/cells.json` | 阶段 B 六格事件研究表 + 选优 trace |
| `artifacts/mr-statarb/round-20260909/oos.json` | 阶段 C 表 + verdict/verdict_reasons |
| `artifacts/mr-statarb/round-20260909/frozen_list.csv` | 39 只冻结名单 |
| `artifacts/mr-statarb/round-20260909/manifest.json` | 批次/口径/缺日/无信号时段/16 条 notes |
| `artifacts/mr-statarb/round-20260909/pass1/`（5546 文件）、`pass2/`（39 文件） | 逐股原始记录（复算的最小单元） |
| `docs/experiments/mr-statarb-round1-20260909.md` | 人类可读报告（34 行，由 JSON 生成） |
| `artifacts/mr-statarb/run-20260909.log` | 运行日志（约 13 分钟，19:24→19:37） |

## 关键结果（供复算对表）

- **阶段 A**：n_tasks 5546；有效会话<200 剔除 912；no_rows 98、no_data 3；无映射 5、board 1；**资格通过 39 只**。
- **阶段 B 六格**（17bps 机会净期望 | 99.1667% CI 下界 | 门禁）：
  m15_z0 +0.5286% | −0.4557% | 否；m15_z05 +0.5949% | −0.4304% | 否；
  m20_z0 +1.2269% | −0.1250% | 否；**m20_z05 +1.3303% | +0.0246% | 通过（唯一）**；
  m25_z0 +0.5806% | −1.0496% | 否；m25_z05 +0.6281% | −0.9734% | 否。无退化、无零事件格。
- **唯一选优**：m20_z05（唯一通过格）。
- **阶段 C**：事件 237（成交 235/no_trade 2/过滤器跳过 1）；17bps +0.1076%、27bps +0.0086%（cb_ratio17=0.0809）；95% CI [−0.8338%, +1.2406%]；Top5 0.391662（Σ|contrib|=3.796035）；verdict=FAIL。
- **B 段 m20_z05 明细**：回归概率 57.34%（164/286，immature 14）；已成交 net17 均值 +1.3438%、中位 +0.471%、胜率 54.21%；exit z_open 22/force_close 274/force_deferred 1；失败归因 other_unidentified 114/industry_crash_assoc 21/announcement_assoc 1。
- **披露**：index 7 缺日；无信号时段近似 [2022-03-03→2022-11-01]、[2023-09-08→2024-03-12]（2022 年 B 窗仅 15 事件与此一致；2023 全年 B 净期望 −0.72%）；逐股覆盖见 screening.json 三口径。

## 运行后代码改动披露（两处，均为报告渲染层，未触碰统计逻辑）

1. `write_report_md` `%` 格式符 bug（字面 `%`+全角顿号）：导致首轮运行 exit 1、md 缺失；修复为拆句。md 由一次性 heredoc 基于已落盘 JSON 重生成，**未重算**。
2. 同函数「B→C 唯一选优」行渲染收敛：完整 JSON → 格子 id + 选优依据简述。

两处改动后 `python -m unittest discover -s tests`：**550 项 OK（跳过 1）**（主对话复验一致）。pass1/pass2/screening/cells/oos/manifest 均在改动前落盘，不受影响。

## 建议复算路径

1. 从 `pass1/*.json` 独立聚合重算 screening/frozen/六格表，对表 cells.json（含 bootstrap：事件日块、块长 20、B=10000、种子 20260909、99.1667% 分位）。
2. 从 `pass2/*.json` 重算 C 表与 95% CI，对表 oos.json；核对 verdict 逻辑（ci_lower>0 ∧ n≥30 ∧ Top5≤50%）。
3. 抽查若干只冻结股的逐事件记录 vs 原始日线（入场次日开盘、强退第 5 市场会话收盘、跌停顺延、避雷过滤）。
4. 核对 md 与 JSON 数字一致性、披露项齐备性。

## 回执格式建议

PASS（工件与判定可落锤）/ CHANGES_REQUESTED（逐条列差异与位置）。
