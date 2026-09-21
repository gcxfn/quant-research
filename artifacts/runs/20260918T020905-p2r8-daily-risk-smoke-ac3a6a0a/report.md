# P2-R8 日频风控 + 月频选币（预登记策略级回放）

- experiment_id: exp-20260918-p2r8-daily-risk（SMOKE：1 年 × C01/C07，判据不生效）
- dev 段为探索性（重用二：R6/R7 已消费）；种子 17；B3prime 种子 17–36；费用：佣金万1 最低5元、无印花税/过户费、滑点 0

## 锚定回归（先于任何判据消费）

- r7_run: artifacts\runs\20260918T004441-p2r7-etf-exposure-d01f4e7a
- scope: sessions<=2016-12-31
- c01_sessions_equal: True
- c01_net_bit_exact: True
- c01_gross_bit_exact: True
- B1-FIX75_vs_B1-FIX_sessions_equal: True
- B1-FIX75_vs_B1-FIX_bit_exact: True
- B1-FIX75-gross_vs_B1-FIX-gross_sessions_equal: True
- B1-FIX75-gross_vs_B1-FIX-gross_bit_exact: True
- B1-100_vs_B1-100_sessions_equal: True
- B1-100_vs_B1-100_bit_exact: True
- b1_100_dev_metrics: skipped in smoke (dev window is 2016 only)
- all_pass: True

## 基准（dev）

- B1(D2520.10-L0.40) dev 净年化 0.018（毛 0.022），回撤 -0.047
- B1(FIX75) dev 净年化 0.072（毛 0.076），回撤 -0.071
- B1(100) dev 净年化 0.097（毛 0.101），回撤 -0.093
- B2 510300 买入持有 dev：净 -0.097（毛 -0.097）
- D2520.10-L0.40（20 种子）dev 净年化均值 0.012 [-0.032, 0.075]
- FIX75（20 种子）dev 净年化均值 0.053 [-0.025, 0.150]
- B4 现金 0%

## 配置结果（dev，探索性重用二）

| 配置 | 机制 | 毛% | 净% | B1(m)净% | 净超额pp | 优势年 | 回撤% | 换手max% | top1/top3 | 风控交易 | 过x/8 | 失败判据 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| C01 | FIX75 FIX75 | 0.083 | 0.082 | 0.072 | 0.010 | 1/5 | -0.065 | 4.707 | 0.409/0.905 | 0 | fail | 2,3,6 |
| C07 | D252 D2520.10-L0.40 | 0.027 | 0.026 | 0.018 | 0.009 | 1/5 | -0.046 | 3.224 | 0.438/0.914 | 12 | fail | 2,3,6 |

## 省回撤 ÷ 丢反弹（对 C01 对照，描述性）

- C07（D252）: 省回撤 1.95pp，丢净年化 5.55pp，比值 0.352

## 判定

- dev 通过（探索性重用二）：[]
- 进入 validation：None
- P3 候选：[]
- 试验累计：127
