# 系统风险分层审查：发现与闭合状态

日期：2026-09-10。当前阶段：A。总体裁决：**CHANGES_REQUESTED**。

## 已闭合的 round-3 数值比较项

当前 HEAD 的确定性循环已调用 `compare_strict`，能拒绝同路径 `5e-13` 漂移。registry 的整数分支使用精确比较，bootstrap 子树使用严格浮点比较；单侧缺因子集合会失败。独立执行：

```text
python -m unittest tests.test_factor_miner_np_tools tests.test_factor_miner_numpy_path tests.test_factor_miner_stats_np
Ran 56 tests in 1.618s
OK
```

测试出现 numpy 无效数运算 `RuntimeWarning`，没有测试失败。独立直接调用还确认：排名换位、None/值翻转由比较器拒绝；上述已闭合项不再作为当前阻断。

## A-01 [P1] registry 装载器吞掉重复或无效 ID

位置：`experiments/np_dualpath_registry_compare.py:23-30`。

触发条件：同一 JSONL 内出现相同或冲突的重复 `factor_id`；或记录缺少 ID、ID 为 null、空字符串。`load()` 使用 `out[rec.get("factor_id")] = rec`，后值覆盖前值，且 `None`/空字符串被当作合法 dict 键。

独立微型 JSONL 结果：

| 负例 | 实际报告 | 实际退出码 | 预期 |
|---|---:|---:|---|
| 冲突重复 f1 | PASS | 0 | FAIL |
| 相同重复 f1 | PASS | 0 | FAIL |
| 缺失 factor_id | PASS | 0 | FAIL |
| factor_id=null | PASS | 0 | FAIL |
| factor_id="" | PASS | 0 | FAIL |

影响：冲突 gate、计数或统计记录可以被静默覆盖，检查器无法证明 registry 的全量一致性。

修复要求：装载时要求 `factor_id` 为非空字符串并拒绝任何重复；错误包含文件与行号；CLI 打印 FAIL 且非零退出。测试必须使用自带微型文件覆盖相同重复、冲突重复、缺失/null/空/非字符串 ID。

## A-02 [P1] 双空及双方共同漏单元可获 PASS

位置：`experiments/np_dualpath_registry_compare.py:76-86`。

两侧空 JSONL 的独立结果为 `factors compared: 0 / diffs: 0 / VERDICT: PASS`，退出码 0。工具仅比较两侧集合；即使两侧共同缺少同一冻结候选，也会通过。单侧缺 f1 已正确 FAIL、退出 1，但不能覆盖共同遗漏情形。

修复要求：CLI 必须接收或读取一个独立冻结的预期 ID 清单及数量，并同时验证 pure、numpy 各自精确等于该集合；拒绝空输入。预期清单不能从任一待比较 registry 自举。报告须列预期、各侧实际及遗漏/额外 ID，退出码与 verdict 一致。

## A-03 [P1] 差分探针对零覆盖和编译失败返回 PASS

位置：`experiments/np_dualpath_diff_probe.py:174-229`。

独立 mock bundle 负例：

| 输入 | 实际报告 | `main()` 返回码 | 预期 |
|---|---:|---:|---|
| 空 hypothesis JSONL | differential PASS | 0 | FAIL |
| 唯一公式不在白名单、compiled=0/compile_fail=1 | differential PASS | 0 | FAIL |

探针还没有验证 hypothesis ID 的唯一性、类型、非空和冻结预期集合。重复 key 会在 `evaluate_all()` 的 results dict 中覆盖，`plans` 又按重复 key 重读同一结果，无法证明每个冻结单元都被独立覆盖。

修复要求：装载前验证冻结预期清单、数量、有效且唯一 ID；任何解析/编译失败、零计划、结果键缺失/额外均使最终 verdict FAIL 和返回码非零。负例应完全使用测试自带微型假设与 bundle，不读取 `artifacts`。

## A-04 [P2] 工件代码身份未被门禁检查

位置：`experiments/np_dualpath_registry_compare.py:20,37-40` 及 numpy 送审包身份声明。

`code_commit` 和 `code_identity` 被无条件忽略，工具本身也没有接受冻结预期代码身份。因而两侧来自不同非预期实现时，只要其余字段相同就可 PASS。送审包说明两条路径因包内文件变化而身份必然不同，这是历史 dev-smoke 的解释，不能替代 A 阶段要求的“固定受审代码与配置、校验冻结代码身份”。

修复要求：明确双路径允许的受审身份模型并实现检查。若两侧确需不同 identity，必须分别绑定事前冻结的 expected identity，不能简单忽略；记录实际 commit、受审文件 digest、配置/假设清单 digest 和 Python/numpy 版本。身份不符时 FAIL、非零退出。

## 报告与退出码结论

已覆盖的成功和失败路径中，工具打印的 verdict 与自身返回/CLI 退出码一致；问题在于错误条件没有进入 verdict。修复后需为每项负例同时断言报告文字和退出码，并增加 subprocess 级 CLI 测试，避免仅测内部函数。

## 闭合条件

主审 B～E 首轮补充：完整问题、定位、最小反例及修复验收见 `system-audit-bcde-independent-review-20260910.md`。新增 B-01～03、C-01～04、D-01～02；编号按阶段独立，不覆盖本文件 A-01～04。B/C/D 均 CHANGES_REQUESTED，E 仅首轮初筛，尚未最终验收。

A-01 至 A-04 修复、固定新提交身份后，由独立审核复跑全部微型负例、相关专项和一次目标文件漂移检查。当前不得用“56 项通过”“全仓 1085 项通过”或旧真实工件零差异替代这些闭合条件。
