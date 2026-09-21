# P4 R1 障碍检验执行方式

授权：用户要求持续自主推进。最新分工为主对话只做规划、分派和最终审核，代码实现交 Sol，不再派 Terra；此前指定 Terra 的记录仅为历史。阶段一独立PASS见 `p4-r1-independent-acceptance-20260908.md`，本轮只进入2020—2023选择窗障碍步骤2，Gate D仍冻结。

## 冻结口径

不更改12候选、4止损档、费用、信号方向、完整市场交易日历、非重叠轮次和2000次block bootstrap。48检验的Bonferroni线保持0.05/48，C1/C2只作描述。通过完整A/B且方向一致才讨论组合；B1价差不作为多头账户收益。

## 内存与运行

原入口同时保留全池日线、全部障碍字典及14列所有十分位record引用。改用 `iter_p1_pool_rows_until` 逐证券生成原标签并按日期保存；原 `build_p1_pool_rows_until` 仍将相同迭代器收集为list，语义不变。每日因子来自本轮已接受分区，显式股票代码排序并核对分区行数，避免并列值边界改变分组。

逐因子读完整日期数据，保留所有十分位的原统计输入和目标十分位的完整B2轮次；不把B2拆成彼此独立的日检验。最多2进程，并行的是不同因子，单因子仍使用完整交易日历和全期目标轮次。每列完成后原子保存，最终合并14列，检验族仍48，记录数不按14倍累加。

新入口 `experiments/p4_stream_barrier.py`。同一批次缓存只供未改变输入/统计代码的中断恢复；变更规则或输入要用新批次，不覆写已有正式研究结果。流式 manifest 绑定规范化 `round_dir`、完整因子分区 manifest（含来源状态、计数和配置）及完整 B1 结果内容；启动、worker 和已完成列复用均逐字段核对。生成标签前后也核对同一绑定，避免生成期间上游变化后记录错误版本。

验证：改造前模块与新流式模块合成完整dict相等（含并列因子、状态缺口、四止损及多种结果）；单因子全周期与全列结果相等，48检验线不变。缓存反例另覆盖：产列后替换 `source_state`、替换 B1 内容、列自身绑定不一致、相同配置换 `round_dir` 均拒绝，输入不变则正常续跑。相关测试及零依赖合成回测 smoke 为实现者证据，不是独立 PASS；运行前由主对话最终审核。

主对话运行前审核已于 2026-09-09 通过，记录见 `p4-barrier-cache-acceptance-20260909.md`。正式运行改用全新 20260909 输出目录：

```powershell
python -u -B -S -X utf8 -m experiments.p4_stream_barrier --round-dir artifacts/short-foundation/p4-screen/revised-r1-20260908 --out-dir artifacts/short-foundation/p4-barrier-screen/revised-r1-stream-20260909 --workers 2
```

本报告不是独立PASS，实际审阅及运行结果另行追加。
