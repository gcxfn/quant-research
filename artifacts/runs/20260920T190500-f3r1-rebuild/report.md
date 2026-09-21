# F3R1 因子组合：两臂 band 引擎 v1.3 八门判定（dev）

- 运行 `20260920T190500-f3r1-rebuild`；引擎 v1.3 sha256:16 `31022babbc2858ea`；预登记 `docs/research/exp-20260919-factor-round-f3r1-prereg.md`（冻结，含 ICW 权重运行前澄清补钉）。
- 去重：42 幸存者 → 20 簇 → 20 代表 （A17, A20, A25, B11, B12, B14, C19, D08, D09, D10, D14, D18, D19, D20, D21, D25, E16, F02, F06, F09）；可执行池 = R16 冻结池 ∩ 组合覆盖（≥10/20 代表非空）。
- 信号 2015-01-30..2020-11-30（71 个月末）；val 2021–2024 零接触。全部数字为历史回放，不构成盈利声称。

## 八门判定表

| 臂 | 净CAGR | B1(m) | 超额 | 优势年 | 回撤 | 换手 | 单票max | 门8成交率 | B3′ | 过/8 | 失败门 | ≥10%目标 | 判定 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| F3-EW | +9.47% | +1.66% | +7.81pp | 3/6 | -39.75% | 5.77 | 24.0% | 74.9% | -1.89% | 5 | 3_advantage_years_ge_5_of_6, 4_mdd_le_20pct_and_le_B1m, 8_execution_rate_ge_95pct | not met | eliminated |
| F3-ICW | +15.28% | +1.66% | +13.62pp | 4/6 | -41.19% | 6.21 | 22.4% | 76.7% | -1.89% | 4 | 3_advantage_years_ge_5_of_6, 4_mdd_le_20pct_and_le_B1m, 5_one_side_turnover_le_6, 8_execution_rate_ge_95pct | MET | eliminated |

## 判定：no arm passed all dev gates (0/2); val not consumed

## 死因与披露要点

- **F3-EW**：门8 终止结构 {'expiry': 59, 'override_same_name': 196, 'cap_void': 0, 'suspension_abandon': 11}；规则阻断 {'below_min_lot': 0, 'void_no_position': 218, 'void_insufficient_cash': 2}；零发射意图 8；过期空操作 0；席位置空规则=买入意图过期即空仓至该票离池再入（静态帧不重发，预登记 §5 登记注记）。
- **F3-ICW**：门8 终止结构 {'expiry': 59, 'override_same_name': 189, 'cap_void': 0, 'suspension_abandon': 15}；规则阻断 {'below_min_lot': 0, 'void_no_position': 216, 'void_insufficient_cash': 1}；零发射意图 9；过期空操作 0；席位置空规则=买入意图过期即空仓至该票离池再入（静态帧不重发，预登记 §5 登记注记）。

## 基准口径

- B1(m)_F3 = 可执行池等权月频 fractional、exposure=1、rate-only 费率（R16 原约定，本轮池重算）：净 +1.66%、回撤 -64.42%。
- B3′_F3 = 随机 K=10、种子 17–36 共 20 次、整手 + STOCK_FEE_SCHEDULE：均值 -1.89%（R16 用 K=20 对应其 K 族，本轮对齐自身席位，偏差登记于预登记 §5）。