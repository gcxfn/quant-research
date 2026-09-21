# 固定方案实验：混合主线完整合同回放（dev）

- 运行 `20260921T121615-fixed-scheme-6e8be`；引擎 f3650f8440c713b8；预登记已冻结。
- 8 条曲线 = 2 股票腿 × 4 账户级配置；40/60；全部历史回放，不构成盈利声称。

| 曲线 | 净CAGR | 超额 | 优势年 | 回撤 | 换手 | 单票max | 门8 | 过/8 | 失败门 | ≥10% | 判定 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| MF-G0 | -0.01% | -5.66pp | 2/6 | -42.72% | 14.88 | 23.3% | 29.1% | 1 | 1_net_cagr_gt_0,2_excess_vs_B1mix_ge_2pp,3_advantage_years_ge_5_of_6,4_mdd_le_20pct_and_le_B1mix,5_one_side_turnover_le_6,7_vs_B3mix_plus_1pp,8_execution_rate_ge_95pct | no | eliminated |
| MF-G1 | +0.72% | -4.93pp | 2/6 | -39.10% | 13.43 | 23.3% | 29.6% | 2 | 2_excess_vs_B1mix_ge_2pp,3_advantage_years_ge_5_of_6,4_mdd_le_20pct_and_le_B1mix,5_one_side_turnover_le_6,7_vs_B3mix_plus_1pp,8_execution_rate_ge_95pct | no | eliminated |
| MF-G2 | +2.59% | -3.07pp | 2/6 | -19.88% | 7.00 | 20.4% | 29.2% | 2 | 2_excess_vs_B1mix_ge_2pp,3_advantage_years_ge_5_of_6,4_mdd_le_20pct_and_le_B1mix,5_one_side_turnover_le_6,7_vs_B3mix_plus_1pp,8_execution_rate_ge_95pct | no | eliminated |
| MF-G3 | +2.74% | -2.91pp | 2/6 | -17.37% | 4.69 | 20.4% | 29.0% | 4 | 2_excess_vs_B1mix_ge_2pp,3_advantage_years_ge_5_of_6,7_vs_B3mix_plus_1pp,8_execution_rate_ge_95pct | no | eliminated |
| MC-G0 | -8.30% | -13.95pp | 1/6 | -50.44% | 9.62 | 25.2% | 19.5% | 1 | 1_net_cagr_gt_0,2_excess_vs_B1mix_ge_2pp,3_advantage_years_ge_5_of_6,4_mdd_le_20pct_and_le_B1mix,5_one_side_turnover_le_6,7_vs_B3mix_plus_1pp,8_execution_rate_ge_95pct | no | eliminated |
| MC-G1 | -5.12% | -10.77pp | 2/6 | -41.02% | 8.85 | 25.2% | 19.2% | 1 | 1_net_cagr_gt_0,2_excess_vs_B1mix_ge_2pp,3_advantage_years_ge_5_of_6,4_mdd_le_20pct_and_le_B1mix,5_one_side_turnover_le_6,7_vs_B3mix_plus_1pp,8_execution_rate_ge_95pct | no | eliminated |
| MC-G2 | -2.48% | -8.13pp | 2/6 | -24.53% | 4.41 | 22.1% | 17.4% | 2 | 1_net_cagr_gt_0,2_excess_vs_B1mix_ge_2pp,3_advantage_years_ge_5_of_6,4_mdd_le_20pct_and_le_B1mix,7_vs_B3mix_plus_1pp,8_execution_rate_ge_95pct | no | eliminated |
| MC-G3 | -1.84% | -7.49pp | 2/6 | -19.11% | 3.71 | 21.2% | 16.7% | 3 | 1_net_cagr_gt_0,2_excess_vs_B1mix_ge_2pp,3_advantage_years_ge_5_of_6,7_vs_B3mix_plus_1pp,8_execution_rate_ge_95pct | no | eliminated |

## 0/8 过全部门；val 不消费
