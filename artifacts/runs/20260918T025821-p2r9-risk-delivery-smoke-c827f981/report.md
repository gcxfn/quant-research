# P2-R9 日频风控交付工程轮（换手×相对回撤×集中度；预登记策略级回放）

- experiment_id: exp-20260918-p2r9-risk-delivery（SMOKE：1 年 × C01/C03，判据不生效）
- dev 段为探索性（重用三：R6/R7/R8 已消费 dev）；种子 17；B3prime 种子 17–36；费用：佣金万1 最低5元、无印花税/过户费、滑点 0

## 锚定回归（先于任何判据消费）

- r8_run: artifacts\runs\20260918T021054-p2r8-daily-risk-d19a9c07
- r8_run_trial_count: 127
- scope: sessions<=2016-12-31
- A1_vs_C01_sessions_equal: True
- A1_vs_C01_net_bit_exact: True
- A1_vs_C01_gross_bit_exact: True
- A2_vs_C09_sessions_equal: True
- A2_vs_C09_net_bit_exact: True
- A2_vs_C09_gross_bit_exact: True
- b1_100_vs_r8_sessions_equal: True
- b1_100_vs_r8_bit_exact: True
- b1_100_dev_metrics: skipped in smoke (dev window is 2016 only)
- all_pass: True

## 基准（dev）

- B1(D60-8H4-L0.4) dev 净年化 2.72%（毛 3.11%），回撤 -6.29%
- B1(FIX75) dev 净年化 7.22%（毛 7.60%），回撤 -7.15%
- B1(100) dev 净年化 9.68%（毛 10.06%），回撤 -9.34%
- B2 510300 买入持有 dev：净 -9.67%（毛 -9.65%）
- D60-8H4-L0.4 N=3（20 种子）dev 净年化均值 1.22% [-5.01, 9.98]
- B4 现金 0%

## 配置结果（dev，探索性重用三）

| 配置 | W/N | 机制 | 毛% | 净% | B1(m)净% | 净超额pp | 优势年 | 回撤% | B1(m)回撤% | 余量pp | 换手max% | top1/top3 | 风控交易 | 过x/8 | 失败判据 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| C01 | W2S/3 | D60 D60-8H4-L0.4 | 4.82 | 4.71 | 2.72 | 2.00 | 1/5 | -6.45 | -6.29 | 15.87 | 458.89 | 48.50/105.55 | 3 | fail | 2,3,4,6 |
| C03 | W2L/3 | D60 D60-8H4-L0.4 | 2.61 | 2.51 | 2.72 | -0.20 | 0/5 | -5.35 | -6.29 | -94.30 | 449.51 | 92.11/188.42 | 3 | fail | 2,3,6 |

## 换手分解（dev，逐年最大；选币基础 vs 风控缩放增量）

| 配置 | 年 | 选币换手% | 风控增量% | 合计% |
|---|---|---|---|---|
| C01 | 2016 | 425.45 | 33.44 | 458.89 |
| C03 | 2016 | 415.12 | 34.40 | 449.51 |

## 相对回撤余量（策略 dd − B1(m) dd，负 = 深于基准）

- C01: 策略 -6.45% vs B1(m) -6.29%，余量 15.87pp
- C03: 策略 -5.35% vs B1(m) -6.29%，余量 -94.30pp

## 迟滞切换统计（dev；off 触发 / re-arm / 关闭占比）

- C01: 2016: 0/1/26%
- C03: 2016: 0/1/26%

## 判定

- dev 通过（探索性重用三：R6/R7/R8 已消费 dev）：[]
- 进入 validation：None
- P3 候选：[]
- 试验累计：139
- 停机规则：this line gets NO further rounds tonight regardless of outcome (prereg section 0)
