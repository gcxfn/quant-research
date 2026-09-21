# P4 CPU 多进程提速

用户授权执行提速；仅改变统计运行方式，不修改候选、阈值、费用、随机种子及截止日。

## 实现

`experiments/p4_screen.py` 拆出逐日统计与统一汇总函数。`experiments/p4_parallel_screen.py` 将本轮已保存的JSONL按日期顺序扫描分区，保留同一天的原输入顺序和重复标签最后覆盖语义；每个进程只读一个交易日，最多同时派发workers项，主进程严格按日期顺序汇总，避免完成顺序改变浮点累计与非重叠收益取样。

逐日统计原子落盘，恢复时只算未完成日期。缓存必须限于相同本轮数据、配置、统计代码；源配置和run_state比较相同，输入/统计语义变化须新批次。分区只存统计需要的字段，批量缓冲约16MiB字符，文件逐个写入；未新增第三方依赖或GPU依赖。

## 验证

拆分前代码留存于本轮研究artifacts上层的 `pre-parallel-screen.py`，合成四年、多期限、并列值、缺失和非有限标签、市场门槛两状态的完整统计dict与拆分后相同。新测试实测Windows spawn的1/2/4进程，完整结果与串行一致；逐日缓存恢复结果一致，恢复时禁止再次计算，确保真正复用。相关集合118项、零依赖合成CLI smoke通过。小批量分区修正后对应多进程端到端测试再次通过。

## 运行记录

旧恢复进程PID29872停止，未产生完整筛选结果；其本轮原始中间件保留。第一次按日分区在标签约50万行时进程退出码1、无堆栈，原因未确认；不完整 `date-partitions-v1` 保留且不使用。改为小批量写入后的新目录为 `date-partitions-v2`，新日志 `parallel-benchmark-run.log`。只将存在完整manifest的分区作为可复用输入。

测速使用本轮真实选择窗每40个交易日取一日，共24日，同一输入比较1、2、4进程并严格比较完整结果。计时包含进程启动和分区读取，不含一次性分区。实测1进程18.213秒、2进程13.214秒、4进程6.297秒；4进程为单进程的2.89倍速度。三种进程数完整统计dict相等，工件 `parallel_benchmark.json`。另在2020-01-02、2020-12-29、2021-12-24、2022-12-21四个真实横截面，与保存的改造前代码逐字段比较完整结果相等。

已选择4进程启动全池，日志 `parallel-full-run.log`；此测速只代表24日样本，不保证全池固定2.89倍，也不与此前内存压力下未完成的长跑作精确倍数比较。

全池实测：970个交易日于257.7秒完成逐日统计，`screen/p4_screen_parallel.json`已生成；选择窗因子4370014条、标签4177687条（原生成因子含2019预热，数量更大）。各活动Python进程工作集现场抽查约43—72MiB；不是全过程峰值。随后继续原固定随机对照。此计时不含一次性分区和随机诊断。

最终运行退出码0；完整计时257.79秒，原随机诊断完成PASS（两集合均0/20过Gate A）。`round_summary.json` 已生成，状态 `PENDING_INDEPENDENT_REVIEW`。本轮后台计算已经结束，不再引用旧进程“仍在运行”的状态。

命令：

```powershell
python -u -B -S -X utf8 -m experiments.p4_parallel_screen --round-dir artifacts/short-foundation/p4-screen/revised-r1-20260908 --benchmark
python -u -B -S -X utf8 -m experiments.p4_parallel_screen --round-dir artifacts/short-foundation/p4-screen/revised-r1-20260908 --workers 4
```

输出：本轮 `screen/p4_screen_parallel.json`、`screen/parallel_timing.json`、`screen/daily-statistics-v1/`，随后运行原固定随机对照。新的性能改造及研究工件仍待独立复审；障碍步骤2和Gate D不解锁。
