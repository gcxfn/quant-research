# 决策：席位账 run 来源与单名 25% 帽快照口径（C4-DEF-02）

日期：2026-09-22｜性质：证据来源与口径裁定（只读调查，不改码）｜状态：已裁定，文档化关闭

## 背景

C3 的席位账/漏斗产物并非取自 B1 主 run（`20260921T223157-eventfam-main-cb4cff`），
而是取自同参数的 attrib2 run（`20260922T002611-eventfam-attrib2-eed5cf`）；C3 登记为
`C3-OBS-04`（MINOR）转 C4。同一小节还登记「单名 25% 帽快照：matcher 与引擎各自自算快照，
本阶段无差异样本；若 C4 出现差异，需按合同 M2 精确定义决策点权益快照的价格来源与时刻」
（`c3_case_report.md` §7 第 4 项）。

## 一、席位账 run 同源性

**事实**：B1 主 run 的产物（`B1_events.parquet`、`B1_fills.parquet`、
`B1_exit_reason_log.csv`）只落**已签发/已成交**事件，**不含**候选被 `slot_full` 跳过的
漏斗行；因此席位守恒（39 签发 + 63 满席 = 102）只能取自会落漏斗的 attrib2 run。

**同源证据（独立核对 attrib2 manifest）**：

- `identity.fills_equal_main_run = true`、`daily_equity_equal_main_run = true`、
  `trigger_stats_equal_main_run = true`、`event_counts_equal_main_manifest = true`、
  `funnel_counts_equal_provider_counters = true`；
- `trials_note`：「B1 replay uses the identical config/inputs as the main run; fills + equity +
  trigger stats asserted bit-equal to the archived outputs before statistics are emitted」；
- `pins.engine.sha256 = 40f1aaeb…37abd`，与当前盘上 `src/quant/backtest/band_engine.py`
  SHA256 **逐字节相同**（C4 独立复算），即席位账与被对账的成交/权益出自同一引擎版本。

**裁定**：这不是语义不同源，而是**产物粒度差异**——attrib2 用与主 run 相同的配置与机制
复放，并在发统计前断言成交/权益/触发计数与主 run 逐位相等。C4 采信该等效性，
**不改主 run runner、不新增漏斗产物**（重跑属研究层改动，主计划禁止在工程批次顺手做）。
残留局限：席位账仍是「主 run 机制 + attrib2 产物」的组合，非单 run 内闭环，如实登记。

## 二、单名 25% 帽快照口径

合同 M2（`p3-band-contract.md` §7.7）：单票 ≤25% 作用于**订单构建时**，
按**决策点权益快照**，越限**整单作废**（不缩量）；既有持仓因价格漂移越限不强制减持。

**引擎口径（实现事实，只有一处定义）**：
`decision_snapshots[(day, sess)] = cash + pend_am_to_pm + pend_next_day + Σ shares × mark`，
其中 `mark =` pm 决策用 `mark_close`（官方收盘 carry-forward）、am 决策用
`official_close_strict`（clk 半日模式下已持有标的用**当日完成的 am bar close**，停牌则冻结
上一可交易收盘）。帽判定在**建单时**读 `decision_snapshots[(order.decision_date,
order.decision_session)]`：`projected_mv + cost > 0.25 × snap` → `cap_single_name` 整单作废
（`band_engine.py` L3136-3172、L3732-3751）。

**独立 matcher 口径**：`reference_matcher_reconcile._snapshot_equity` 自算
`cash + 两个待结算桶 + Σ shares × px`，pm 用 `official_close(decision_date)`、
**am 用 `prev_trading_close(decision_date)`**。

**已识别的潜在口径差**：在半日时钟下，am 决策点的**已持有标的** mark，引擎用「当日完成的
am bar close」，matcher 用「上一交易日收盘」。这是**口径差**而非经济差前提下的现实分歧点。

**为何本轮无需修复**：

- 实测**所有**被对账臂（基线 5 臂 + 事件族 4 臂 + 随机对照 3 臂）的事件产物中，
  `detail` 含 `cap` 的行 **0 条**、无 `cap_single_name` 作废事件——即 25% 帽在这些臂中
  **从未绑定**，没有一例成交/作废/统计依赖该快照。
- 因此该潜在口径差对已发表结论**零影响**；C3 报「无差异样本」与此一致。
- 不修改 matcher：matcher 是 C3 独立参照，改它属于工程改动；且修 am mark 需重新对齐全部
  对账（无观测收益）。

**裁定**：合同层面的「决策点权益快照」以**引擎口径**为准（已写入本文件作为精确定义）；
matcher 的 am mark 潜在口径差登记为 INFO 局限。若未来某臂出现 25% 帽绑定，必须先按本定义
对齐 matcher 的 am mark（当日完成 am bar close / 停牌冻结），再采信其帽判定。

## 证据路径

- `artifacts/runs/20260922T002611-eventfam-attrib2-eed5cf/manifest.json`（identity 块）
- `src/quant/backtest/band_engine.py` L3136-3172（快照）、L3732-3751（帽判定）
- `src/quant/research/reference_matcher_reconcile.py` `_snapshot_equity` / `_projected_mv`
- `docs/evidence/trust-rebuild/20260922T035220-trust-c3-c8af13/seat_lifecycle.csv`、
  `semantic_chain_summary.json`、`c3_case_report.md` §5.3/§7
- C4 独立扫描：事件族与基线全部事件的 `detail` 无 `cap` 命中（见 `issue_register.csv` C4-DEF-02 行）
