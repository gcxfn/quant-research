# P4 第6轮修复验收与新增修复记录

日期：2026-09-08。基线：`8bdad7d` 加进入本轮时既有工作区修改。范围仅为共同样本 IC、方向化 B1、正式入口读取截止；未重审 P2/P3，未运行全池筛选、障碍筛选或 Gate D。

## 裁决

**原修复包：CHANGES_REQUESTED。共同样本 IC 与方向化 B1 的定向反例通过；读取截止仍漏掉正式入口的数据校验阶段。**

**新增修复已获独立窄范围 PASS，见 `p4-cutoff-independent-review-20260908.md`。阶段一未整体完成，全池须先完成修订轮预登记。** 原修复不是本轮主对话实现，前两项为本轮独立检查；下述新补丁由本轮主对话实现，其测试与现场结果属于实现者验证，独立证据单列于复审报告。

## 1. 已核实的两项修复

证据：`D:/AI/workspace/个人量化/tests/test_p4_round6_acceptance.py`。

- 共同样本：30 个有并列值、严格负相关的有效配对，加入仅因子可用和 NaN 观察后，调用实际 `screen()` 输出 IC=-1，符合手算结果。
- 方向与费用：从两个非重叠轮次的原始十分位收益进入 `screen()`，再传给 B1，而非直接编造 B1 汇总。
  - 低减高逐轮净收益为 +0.096、−0.024，累计 `1.096 * 0.976 - 1 = 0.069696`。
  - 高减低逐轮净收益为 −0.104、+0.016，累计 `0.896 * 1.016 - 1 = -0.089664`。
  - 负向 F1 选低减高并通过该合成例 B1；正向 F6 选高减低并失败；中性 C1 无 B1。

这是定向语义证据，不是因子有效性或盈利证据。

## 2. 新发现：数据校验先于构池，仍读全历史

修复前两个正式入口均先调用 `_validate_qfq_construction(ds, ADJUST_VALIDATE)`，随后才进入已经修好的截止构池。验证器内部仍调用 `history.load_daily(code)`、`_load_factor_rows(code)`、`ds.load(code, "qfq")`；退市因子覆盖验证同样使用全历史加载器。覆盖验证传入窗口只限制报告统计，并不限制加载范围。

证据路径：

- `D:/AI/workspace/个人量化/experiments/p4_screen.py`，`run_full_screen()` 数据门禁。
- `D:/AI/workspace/个人量化/experiments/p4_barrier_screen.py`，`run_full_barrier_screen()` 数据门禁。
- `D:/AI/workspace/个人量化/experiments/short_foundation_research.py`，两个验证器。

先加入两条正式入口反例：禁止无界 `history.load_daily` 和 `UserDataset.load`，用合成选择窗数据替代截止读取器。原补丁在构池前抛出 `AssertionError: unbounded raw history read before pool`，两例均 FAIL。复现中在真实文件读取前拦截，没有加载实际验证窗行情。

既有 `FullPoolReadBoundaryTests` 只检查构池函数如何传参，不能覆盖它之前的数据校验；这是漏检原因。

## 3. 最小修复

为两个共享验证器增加可选的读取函数参数；不传时仍使用既有读取器，原 P1/P3 调用语义不变。两个 P4 正式入口显式传入已有的截止原始日线、因子和用户 qfq 读取器。没有复制整套校验逻辑或另建加载框架，没有改交易规则、费用、候选和 Gate 门槛。

本轮代码写入：

- `D:/AI/workspace/个人量化/experiments/short_foundation_research.py`
- `D:/AI/workspace/个人量化/experiments/p4_screen.py`
- `D:/AI/workspace/个人量化/experiments/p4_barrier_screen.py`
- `D:/AI/workspace/个人量化/tests/test_p4_round6_acceptance.py`（新增）

原有工作区修改保持，不做 git 提交、恢复或清理。

## 4. 验证及其边界

1. 新增四条定向反例：修复前 2 PASS / 2 FAIL；修复后 4 PASS。正式入口现在通过两个数据门禁到达构池，原始/因子读取器分别调用两次，qfq 调用一次，截止参数均为 2023-12-31。
2. P4 离线集合 + 新反例 + 共享验证器原默认路径测试：**113 项通过**。命令：

```powershell
python -X utf8 -m unittest tests.test_p4_factor_research tests.test_p4_barrier_labels tests.test_p4_screen tests.test_p4_barrier_screen tests.test_p4_round6_acceptance tests.test_short_foundation_research.QfqValidationTest tests.test_short_foundation_research.FactorCoverageTest
```

这些集合使用合成输入/配置，覆盖共同样本、方向和验证器默认调用回归。未运行会加载真实 2024+ 行情的全量集合。

3. 端到端回测 smoke **PASS**：

```powershell
python -X utf8 -m quant.cli --config configs/test-fixture.json smoke --fixture tests/fixtures/rotation/pool.csv
```

该夹具为 symA/symB/symC 合成数据，虽日历标签为 2024–2025，不是实际市场验证窗数据；其收益不能用于任何盈利结论。

4. 真实选择窗小样本 sanity：20 只股票 + 市场序列，24,264 条因子记录、19,247 条标签记录，`anomalies=[]`。命令：

```powershell
python -X utf8 -m experiments.p4_factor_research --sample 20 --output-dir artifacts/short-foundation/p4-round6-acceptance-20260908/sanity
```

工件：`D:/AI/workspace/个人量化/artifacts/short-foundation/p4-round6-acceptance-20260908/sanity/p4_sanity_20260908_160927.json`。该小样本只证明因子/标签路径可跑，不是全池筛选、完整正式入口或收益验收。

5. 使用截止读取器运行真实数据门禁：6/6 qfq 对账通过，337 只退市证券覆盖校验 `fail_closed=False`；截止为 2023-12-31。工件：`D:/AI/workspace/个人量化/artifacts/short-foundation/p4-round6-acceptance-20260908/cutoff_data_gates.json`。

读取边界的准确含义：源按日期顺序逐行处理，遇第一个大于截止日的行后停止，不向价格、因子、状态计算或输出传递该行。它不是“操作系统从未预读任何后续字节”的物理保证。

## 5. 尚待完成的阶段一工作

新增读取器注入及两条入口反例已获独立 PASS，详见独立复审报告。剩余按已批准的阶段一顺序：建立 P4 修订轮并冻结设计型对照；核对有效 G5 选择窗基线；从新空目录重跑全池步骤1并完成工件复审。

本轮未建立生效的修订轮、未重建全池中间件；不得开启障碍筛选步骤2或 Gate D。独立复审应只覆盖新增缺口及其影响，不重做前两项已经通过的全量审计。
