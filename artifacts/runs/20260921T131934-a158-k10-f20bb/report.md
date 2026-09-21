# 固定方案实验：混合主线完整合同回放（dev）

- 运行 `20260921T131934-a158-k10-f20bb`；引擎 f3650f8440c713b8；预登记已冻结。
- 2 条曲线 = 2 股票腿 × 4 账户级配置；40/60；全部历史回放，不构成盈利声称。

| 曲线 | 净CAGR | 超额 | 优势年 | 回撤 | 换手 | 单票max | 门8 | 过/8 | 失败门 | ≥10% | 判定 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| MLK10G0 | -8.14% | -14.30pp | 1/6 | -52.70% | 10.50 | 25.4% | 43.1% | 1 | 1_net_cagr_gt_0,2_excess_vs_B1mix_ge_2pp,3_advantage_years_ge_5_of_6,4_mdd_le_20pct_and_le_B1mix,5_one_side_turnover_le_6,7_vs_B3mix_plus_1pp,8_execution_rate_ge_95pct | no | eliminated |
| MLK10G3 | -1.67% | -7.83pp | 2/6 | -18.04% | 4.75 | 20.7% | 41.8% | 2 | 1_net_cagr_gt_0,2_excess_vs_B1mix_ge_2pp,3_advantage_years_ge_5_of_6,4_mdd_le_20pct_and_le_B1mix,7_vs_B3mix_plus_1pp,8_execution_rate_ge_95pct | no | eliminated |

## 0/2 过全部门；val 不消费
