# F3R3 动态引擎因子组合重测：两臂八门判定（dev）

- 运行 `20260921T120143-clip-price-anchor-6137d`；重建引擎 sha256:16 `f3650f8440c713b8`；预登记 `docs/research/exp-20260921-factor-round-f3r3-prereg.md`（运行前冻结）。
- 组合与 F3R1 完全一致：43 存活 → 20 簇 → 20 代表；差异仅在执行模型（半日时钟 + provider 席位重发，席位置空取消）。
- 信号 2015-01-30..2020-11-30（71 个月末）；val 2021–2024 零接触。全部数字为历史回放，不构成盈利声称。

## 八门判定表

| 臂 | 净CAGR | B1(m) | 超额 | 优势年 | 回撤 | 换手 | 单票max | 门8成交率 | B3′ | 过/8 | 失败门 | ≥10%目标 | 判定 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| F3-EW | +6.50% | +1.66% | +4.85pp | 3/6 | -38.84% | 9.58 | 14.5% | 96.9% | -1.89% | 5 | 3_advantage_years_ge_5_of_6, 4_mdd_le_20pct_and_le_B1m, 5_one_side_turnover_le_6 | not met | eliminated |
| F3-ICW | +8.52% | +1.66% | +6.86pp | 4/6 | -39.50% | 9.93 | 16.4% | 96.9% | -1.89% | 5 | 3_advantage_years_ge_5_of_6, 4_mdd_le_20pct_and_le_B1m, 5_one_side_turnover_le_6 | not met | eliminated |

## 判定：no arm passed all dev gates; val not consumed

## 与 F3R1（旧引擎）的对照

| 臂 | F3R1 净CAGR | F3R3 净CAGR | F3R1 门8 | F3R3 门8 |
|---|---|---|---|---|
| F3-EW | +9.47% | +6.50% | 74.9% | 96.9% |
| F3-ICW | +15.28% | +8.52% | 76.7% | 96.9% |

注：F3R1 数字来自 `artifacts/runs/20260920T190500-f3r1-rebuild/`（旧引擎 v1.3 静态帧）。

## 座位归因

- **F3-EW**：座位 1066（成交 1033、规则阻断 0 {'below_min_lot': 0, 'void_no_position': 0, 'void_insufficient_cash': 0}、过期空座 33）；动态层 {'provider_calls': 2924, 'dynamic_injected': 2632, 'ledger': 'single live ledger: settled cash + pending buckets + M2 equity snapshot + clips + next-session sellable', 'state_transition': 'halfday clock: normal intents void after one decision point (or when unpriceable); risk exits carry with the K streak'}。
- **F3-ICW**：座位 1128（成交 1093、规则阻断 0 {'below_min_lot': 0, 'void_no_position': 0, 'void_insufficient_cash': 0}、过期空座 35）；动态层 {'provider_calls': 2924, 'dynamic_injected': 2855, 'ledger': 'single live ledger: settled cash + pending buckets + M2 equity snapshot + clips + next-session sellable', 'state_transition': 'halfday clock: normal intents void after one decision point (or when unpriceable); risk exits carry with the K streak'}。