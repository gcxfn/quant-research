# 20260918T014930-event-struct-v1-ac9046d0

- experiment: exp-20260918-event-structuring
- 性质：纯数据工程（事件原始批次 -> 统一事件表 v1）。无策略、无回测、无收益结论。
- status: completed；耗时 8.7s；峰值 RSS 4.85 GB。
- 输入：data/raw/tushare/ 下 6 个批次（forecast 20260909-r1、express 20260909-r1、
  repurchase/share_float/stk_holdertrade 20260909-r3、disclosure_date 20260909-r1），只读。
  交易日历 = index_daily/20260917-r1/chunk_000300.SH.csv（2015-01-05..2024-12-31，2431 日）。
- 输出：data/features/event-factors-v1-20260918/（6 parquet + manifest.json）。

| 族 | raw | 剔除.BJ | 剔除非标 | fail-closed | 入界(写入) | 出界(仅计数) |
|---|---:|---:|---:|---:|---:|---:|
| forecast | 50,406 | 749 | 10 | 0 | 37,227 | 9,576 |
| express | 8,488 | 700 | 0 | 0 | 7,619 | 169 |
| repurchase(plan) | 61,718 | 1,463 | 1,080 | 0 | 12,204 | 2,618 |
| share_float(agg) | 5,661,143 | 14,320 | 2,229 | 0 | 19,101 | 3,629 |
| stk_holdertrade | 149,108 | 3,028 | 0 | 0 | 126,098 | 19,982 |
| disclosure_date | 148,313 | 4,548 | 0 | 0 | 109,483 | 34,282 |

- 出界行 = ts_available > 2024-12-31（share_float 为聚合组级计数，非原始行）。
- 主键全行重复 0 组；候选键碰撞（内容不同的合法多行）逐组登记于 features manifest，未静默去重。
- 结果文档：docs/research/exp-20260918-event-structuring.md
