# numpy 双路径运行前独立审核 round-2

结论：**CHANGES_REQUESTED**。审核提交 `94581d9`，增量基线 `832a3c0`。正式 numpy TRAIN 仍不授权；VALIDATION/LOCKBOX 状态不变。本轮仅审核与记录，未修改实现、未启动正式批。

## 已闭合部分

独立复跑 `tests.test_factor_miner_numpy_path` / `tests.test_factor_miner_stats_np`：46 tests OK。统计专项脚本 Spearman、pool/nopool 衰减曲线、固定输入 bootstrap RNG 检查均 PASS。

上一轮明确的反例已复算一致：`ZSCORE([1.1]*20,20)` 两侧 None；`ZSCORE([1.1]*60,60)` 两侧 -0.9916316520429012；`CORR([1.1]*20,range(20),20)` 两侧 None。求和同序化修复了这些反例，不代表对任意输入、任意 Python/numpy 版本证明了逐位等价。排名换位从失败列表中豁免的 continue 已删除。

## [P2] 确定性检查仍用容差，文档声称的修复未实现

位置：`experiments/np_dualpath_diff_probe.py:211`。

同路径两次结果仍调用 `compare_unit(np1[key], np2[key])`；该函数对有限值使用 1e-12 容差。只改了打印文字为 `strict ==`，没有改比较机制。

独立反例：通过 unittest.mock 注入一个合法 close 假设，三次 evaluate_all 返回值依次为 `{'x': {'a': [1.0]}}`、同前、`{'x': {'a': [1.0+5e-13]}}`，调用探针真实 main()。输出 `numpy determinism (two runs strict ==): PASS`、`differential verdict: PASS`，退出码 0。违反送审 §10.3 同路径严格比较要求。

要求：同路径重复建立真正的严格比较分支，加入针对 main() 退出状态的负例，防止文案改变掩盖比较逻辑未改。

## [P2] registry 仍未按协议严格比较 bootstrap 和整数计数

位置：`experiments/np_dualpath_registry_compare.py:59–62`。

所有 int/float 仍统一进入 math.isclose，无 bootstrap 路径特判，也无整数精确比较。独立调用 walk：bootstrap.lower 从 0.1 改为 `0.1+5e-13`，差异列表仍为空。另以 n 从 10**12 改为 10**12+1 可证明计数分支也非精确（此大计数仅用于检查器负例，不声称是实际股票数量）。送审 §10.3 明确 bootstrap 输出、n 计数严格逐位，当前真实数据“diffs: 0”不能证明该标准。

要求：整数计数采用精确比较，bootstrap 子树采用严格比较，其他获准有限浮点字段才使用容差；增加会使检查器失败的负例。固定输入的 bootstrap RNG 专项不替代全链 bootstrap 输出核验。

## 证据范围与后续

本轮独立运行 46 项相关单测及统计专项、复算已知 P1、注入两项验证工具负例；未重跑全仓 1075 项或正式全市场批次。已有阻断可由小反例确定，不需先消耗全量计算。

修复验证工具后，重新比较 round-2 真实工件（包括 bootstrap 严格比较），重跑确定性检查，提交实际输出。不要仅更新 PASS 文案。有限数值的一般容差与离散信号/门禁一致性是不同约束，不能由“误差只有 1ulp”直接推导门禁永不改变。
