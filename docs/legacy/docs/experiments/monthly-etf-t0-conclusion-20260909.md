# 月频 ETF + 做T 工作项结论（2026-09-09）

本文件汇总当轮实际状态。所有交易仍为人工执行；不产生自动下单、收益承诺或新的可执行做T信号。

1. **ETF涨跌停工程：限定 PASS。** `analysis.bar_side_locked` 已按逐只 `limit_pct_schedule` 的生效日识别ETF 10%/20%限制，并使用0.001 ETF tick；未配置特例时保留普通ETF的10%默认，不能据此宣称未知ETF均已核验。它没有扩大到未核验标的的20%主张。
2. **V3开盘前视修复与R3：限定 PASS，目标 FAIL。** 旧R1/R2保留为执行日收盘前视的缺陷证据；修复后R3是52只当前在市ETF、2020-01-02至2026-09-04的已观察历史复核。年化收益10.19458924%、夏普0.45908651、最大回撤58.85484294%，不通过夏普1.5和约20%回撤目标，也不是严格新样本外。
3. **ETF 5分钟回放：限定 PASS。** 固定配置和工件为 `configs/monthly-etf-t0-minute-replay-20260909.json` 与 `artifacts/monthly-etf-t0/minute-replay-20260909-fixed-v1/report.json`。六个独立情景不可相加、四会话不年化。费用后压力增量分别为：sh510300 顺势 −36.7900（首腿未平）、反T +37.4494；sz159915 顺势 −108.0466（首腿未平）、反T +59.9944；sh588000 顺势 −77.0464（首腿未平）、反T 0（无成交）。主审逐笔限定验收了严格穿越、容量、时点、T+1、费用、压力净值和未平仓MTM；它不证明长期覆盖、盘口排队、成交概率或择时盈利。
4. **ETF终止/清盘偏差：未完成数值上界。** `artifacts/monthly-etf-t0/termination-coverage-20260909/termination_cases.json` 记录五个交易所公告样本和baostock快照缺口。缺历史全目录、逐只终止类型及末次价格/清算净值，因此结论为 `UPPER_BOUND_NOT_IDENTIFIABLE`。

仍需未来数据的严格V3前向 shadow，以及可覆盖终止基金的完整资料；这些缺口不等于本轮工程、R3复核或限定分钟工件没有完成。

主审证据与最终裁决：[独立审核报告](D:/AI/workspace/个人量化/docs/experiments/monthly-etf-t0-independent-review-20260909.md)。全量481项测试OK（跳过1项），V3 smoke PASS；未提交，账户与Gate C/D冻结边界保持。
