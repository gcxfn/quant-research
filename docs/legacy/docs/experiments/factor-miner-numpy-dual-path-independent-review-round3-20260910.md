# numpy 双路径 round-3 工作树独立复审

日期：2026-09-10。结论：**CHANGES_REQUESTED；上一轮两处数值比较问题已闭合，完整性检查和正式送审身份尚未闭合。** 不授权正式运行，不恢复 R0。

## 受审状态

读取时 HEAD 仍为 `94581d9`（round-2）。round-3 送审包、两个检查脚本为未提交修改，`tests/test_factor_miner_np_tools.py` 未跟踪；送审 §11.4 全仓测试数量仍为 `{N}`。本记录仅对应本次读取的工作树，不能作为任何后续提交自动 PASS，也不声称后台全仓测试已完成。

## 已闭合和独立证据

- 确定性循环现调用 compare_strict；第三次输出漂移 5e-13 的负例通过（即正确拒绝）。
- registry 整数精确分支、bootstrap 严格分支接线正确；上一轮两个负例能拒绝。
- 独立执行 `python -m unittest tests.test_factor_miner_np_tools tests.test_factor_miner_numpy_path tests.test_factor_miner_stats_np`：56 tests OK（含 10 项新检查器测试）。存在无效数运算 RuntimeWarning，但此次测试无失败。
- 独立注入换位与 None/值翻转：compare_unit 均返回 False；registry 一侧缺 f1：main 输出 FAIL，退出码 1。

## [P2] 重复 ID 静默折叠，冲突记录可被吞掉

位置：`experiments/np_dualpath_registry_compare.py:23–30`。

独立临时文件反例：纯侧两行 `{"factor_id":"f1","gate":false}` 与 `{"factor_id":"f1","gate":true}`，numpy 侧仅一行后者。load 按 dict 键覆盖第一行，main 输出 `factors compared: 1 / diffs: 0 / VERDICT: PASS`，退出码 0。检查器不能证明单元完整和 gate 全量一致。

修复：解析时拒绝重复 ID（相同或冲突均拒绝），验证 ID 存在、类型和非空；包含文件/行号的错误信息与非零退出码。加入真实文件 main/CLI 负例。此为用户主动指出后由本轮独立复现的问题。

## [P2] 双空工件被判通过

位置：`experiments/np_dualpath_registry_compare.py:76–86`。

两侧都是空 JSONL 时，main 输出 `factors compared: 0 / diffs: 0 / VERDICT: PASS`，退出码 0。不存在任何因子证据，仍被当作等价验收。

修复：本次非空冻结候选批的检查必须校验预期 ID 集合/数量，拒绝空输入及双方同时漏单元，不能仅比较两侧相等集合。需要空批语义的其他场景另行显式定义为无可评估证据，不能混用为本轮 PASS。探针同样须检查输入清单完整、无重复及编译失败是否使覆盖不足。

## A 阶段移交和边界

先补上述文件完整性检查与退出码负例。新测试当前 mock evaluate_all，但仍通过 probe.main 读取本地冻结 hypotheses 并构造真实规模的合成 bundle；建议改用测试自带微型假设和 bundle，使负例不依赖 artifacts 是否存在。

提交方补齐 round-3 实际提交身份、全仓结果和新检查器验证记录后，再审增量并核对冻结真实工件预期集合。只有数值比较修复不能签发完整运行 PASS。

采纳用户提供的现状：R0 已停止且用户暂停重启。A 闭合和 numpy 裁决后再决定计算路径、身份与恢复；旧残缺批不能默认承担完整门禁对照。审查计划已补对应状态行。B～E 工时在 A 完成后按实测重新估计，本轮不承诺“半天”固定工期。
