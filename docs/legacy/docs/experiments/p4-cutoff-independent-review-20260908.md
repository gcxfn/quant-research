# P4 校验阶段截止读取独立复审

日期：2026-09-08。审阅者：独立子代理 `p4_cutoff_independent_review`（Anscombe）。本文由主对话按审阅者最终回报归档；以下独立测试由审阅者执行，不冒充主对话重跑证据。

## 裁决：PASS

基线为 `HEAD 8bdad7d` 加既有脏工作区。仅验收共享验证器读取器注入、两个正式入口的截止传递及对应测试，未发现需要修改的问题。未重新审查共同样本 IC、方向化 B1 或 P2/P3。

- `experiments/short_foundation_research.py:1095`：qfq 校验三处读取可注入；`:1214` 覆盖校验同样处理。默认调用仍使用原读取函数，后续判定不变。
- `experiments/p4_screen.py:702`、`experiments/p4_barrier_screen.py:902`：构池前显式注入按配置 `selection_end` 截止的读取器；任一门禁失败均停止。
- `tests/test_p4_round6_acceptance.py:55`：两条入口反例经过实际验证器，检查读取次数和截止参数，覆盖此前仅检查构池的缺口。

## 独立执行证据

9 项定向测试全部通过，覆盖两个正式入口及共享验证器默认调用：

```powershell
python -B -S -X utf8 -m unittest tests.test_p4_round6_acceptance.Round6Acceptance.test_full_screen_preflight_read_boundary tests.test_p4_round6_acceptance.Round6Acceptance.test_full_barrier_preflight_read_boundary tests.test_short_foundation_research.QfqValidationTest tests.test_short_foundation_research.FactorCoverageTest
```

另外通过标准输入构造内存 CSV/ZIP 的 8 个独立场景全部通过：保留实际截止读取器和验证器，将截止改为 `2022-12-31`；窗后价格、因子、qfq 的 `POISON` 不影响门禁，窗内原始价格偏差、负因子、qfq 偏差分别阻断。两个正式入口均覆盖，无界读取函数均设为调用即失败。脚本未落盘；证据为独立审阅执行回报。首次夹具将“收盘价”误写为“收盘”，按真实接口修正后完成，非产品缺陷。

零第三方依赖的合成回测 smoke PASS：

```powershell
python -B -S -X utf8 -m quant.cli --config configs/test-fixture.json smoke --fixture tests/fixtures/rotation/pool.csv
```

## 既有工件核对与边界

审阅者核对 `artifacts/short-foundation/p4-round6-acceptance-20260908/cutoff_data_gates.json`：截止 `2023-12-31`，qfq 六项匹配，研究窗覆盖有效，`fail_closed=false`。存在 **94 处研究窗外未覆盖跳变，不能称为全历史覆盖通过**。既有 sanity 工件的记录数和空异常列表与实现报告一致。这些真实数据结果仅核对已有工件，本次未重跑。

审阅全程未修改仓库、未提交、未联网取数、未读取实际 2024+ 行情、未运行全池。此 PASS 只关闭新增读取缺口，不代表阶段一整体完成，不直接解锁障碍步骤 2 或 Gate D。下一项为阶段一剩余的修订轮预登记、有效 G5 选择窗基线核对及新全池步骤 1 工件与独立复审。
