# numpy 双路径运行前独立审核（2026-09-10）

结论：**CHANGES_REQUESTED**。受审 HEAD：`832a3c0581c7b650265d9de9d06c342cca610229`。送审包：`factor-miner-numpy-dual-path-review-pack-20260910.md`。

本轮不授权正式 TRAIN 使用 `FACTOR_MINER_NUMPY`，VALIDATION/LOCKBOX 状态不变。不修改实现、不启动正式批、不干预既有纯 Python 批次。工作树存在其他历史修改，本审核仅针对本包新增双路径及其验证工具。

## 1. [P1] 常数窗口产生缺失模式与方向分歧

位置：`experiments/factor_miner/operators_np.py:163–167`（ZSCORE），同类问题见 `:219–227`（CORR）。

numpy 的均值归约与纯路径 `sum(win)` 顺序不同；在常数或近常数浮点窗口上，这会改变方差是否精确为零。不能把它归为 1e-12 的可接受输出误差。独立实测：

| 输入/算子（末日） | 纯 Python | numpy |
|---|---|---|
| `[1.1]*20`，ZSCORE 20 | None | -0.9746794344808966 |
| `[1.1]*60`，ZSCORE 60 | -0.9916316520429012 | +0.9916316520429012 |
| x=`[1.1]*20`、y=`range(20)`，CORR 20 | None | 0.0 |

已通过 `compiler.compile_formula/evaluate` 双环境入口复现，不限于直接调用内部函数。冻结公式 `META_flowlhb_12`（`CS_RANK(lhb_net_buy / circ_mv) * ZSCORE(close,20)`）在两股 close 均为 `[1.1]*20`、lhb_net_buy 分别恒为 1/2、circ_mv 恒为 100 时：纯路径末日两股均 None，numpy 为 -0.4873397172404483 / -0.9746794344808966。这是冻结公式中的无信号→有信号变化；尚未声称真实全市场已发生门禁翻转。

修复要求：以冻结纯路径为语义基准，处理不稳定窗口（例如保守回落到参考计算），覆盖常数小数、近零方差、复合排名/条件/符号传播；不能单方面把两侧零方差规则改成新的 epsilon 策略后仍称为原协议等价。补充反例并重跑差分。

最小复现（仓库根执行；不读真实数据）：

```python
from experiments.factor_miner import operators as p, operators_np as q
for op, args in [
    ('ZSCORE', [[1.1]*20, 20]),
    ('ZSCORE', [[1.1]*60, 60]),
    ('CORR', [[1.1]*20, list(range(20)), 20]),
]:
    print(op, p.apply_window_op(op, args)[-1],
          q._apply_window_op_np(op, args)[-1])
```

## 2. [P2] 差分探针会将排名换位和非逐位重复错误判 PASS

位置：`experiments/np_dualpath_diff_probe.py:200–201,208,229–232`。

发现换位后只记入 `tie_flips` 并 `continue`，最终 PASS 条件未检查该列表。独立注入纯结果 a=0.5/b=1.0、numpy a=1.0/b=0.5，调用真实 `main()`：打印 `tie-flip transpositions ...: 1`，但仍打印 `differential verdict: PASS` 并返回 0。与送审冻结的“零白名单、有限输出容差”冲突，且首个差异被归因后会跳过该单元剩余位置的核查。

同一路径双跑也复用容差比较：`compare_unit({'a':[1.0]}, {'a':[1.0+5e-13]})` 返回 True，却被报告为 `two runs bitwise`。实际当前证据是否存在此类差异，不能由该检查器判定。

修复要求：换位仅作为诊断，仍计失败；同路径重复使用严格比较。另须按送审 §3 对 registry 中 bootstrap 输出采用逐位比较、整数计数精确比较；当前 `np_dualpath_registry_compare.py:61–62` 对所有数值统一放宽至容差，不能证明这两项冻结要求。固定输入 bootstrap 的 RNG 专项通过，只证明固定输入下环境开关不改变该函数，不替代全链输入与输出核验。

## 验证与复审条件

- 独立运行新增双路径专项：43 tests OK。
- 独立运行 `python -m unittest discover -s tests -p test_factor_miner*.py`：260 tests OK，115.239 秒（包含上述 43 项及合成管线测试）。
- 独立运行 `np_dualpath_stats_check.py`：Spearman、pool/nopool 六期限衰减曲线、固定输入 bootstrap 环境切换均 PASS。
- 上述常数窗口、冻结复合公式与探针假 PASS 反例均独立复现。
- 本轮未重跑全市场正式批；送审包的 1072 项全仓测试与 250 公式全量合成结果属于提交方证据，不作为本轮独立复跑声明。

修复后重新提交运行前审核。即使现有随机/真实子集样本通过，也不能覆盖已复现的缺失模式分歧；本轮不签发附条件 PASS。
