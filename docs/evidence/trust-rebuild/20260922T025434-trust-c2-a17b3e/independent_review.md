# 独立审阅报告：C2（独立参考账本）

- 审阅对象 run：`20260922T025434-trust-c2-a17b3e`
- 审阅者身份：主对话会话（ZCode / GLM-5.3），与实施者子代理不同会话；同时担任本轮编排者。
- 审阅时间（本机）：2026-09-22 02:55—03:15
- 绑定身份：代码 HEAD `ae226d9` + 工作树新增（`src/quant/research/reference_ledger.py`、`reference_ledger_reconcile.py`、`tests/test_reference_ledger.py`）；证据目录 16+ 项哈希登记（stage_report.json）。

## 审阅范围与未覆盖范围

**范围**：C2 全部 8 项门；按主计划 16.2 完成 C2 类审阅者最低独立动作（亲算费用/公司行动/现金结算各一例 + 独立复跑）。**未覆盖**：未逐行阅读参考账本全部实现（以 26 项测试 + 复现一致性 + 亲算抽样代替）；未复核 3319 笔成交逐笔（以逐日权益/期末股数/逐类费用合计的全量对比结果 + 抽样亲算代替）；C 表九类反证注入的注入点细节未逐个复现（测试断言"注入必须报错"已在独立重跑中通过）。

## 独立动作（实际执行）

| # | 动作 | 命令/方法 | 结果 |
|---|---|---|---|
| R1 | 检查器 | `check_delivery.py --report .../stage_report.json --root .` | 16 项证据验证；junit 26/0/0；唯一错误=`C2-08 gate not PASS`（本审阅关闭前的真实状态） |
| R2 | 测试独立重跑 | `.venv/Scripts/python.exe -m pytest tests/test_reference_ledger.py --junitxml=reviewer_rerun_ledger.xml` | **26 passed in 0.06s**（含 TV-A01..A05、九类反证注入、TV-B30 单调性） |
| R3 | 独立性验证 | `grep "^import\|^from" reference_ledger*.py` | `reference_ledger.py` 仅标准库（dataclasses/datetime/decimal/typing）；reconcile 驱动仅加 polars（IO）与 `quant.data.dev_sandbox`（C1 冻结访问层）；**零 `quant.backtest`/`quant.portfolio` 依赖** |
| R4 | **全量对账独立复跑** | `PYTHONPATH=src .venv/Scripts/python.exe -m quant.research.reference_ledger_reconcile --evidence-dir .../reviewer_rerun`（0.63s） | `fee_type/corporate_action/ledger_reconciliation` 三张 CSV 与实施者输出 **SHA256 字节级一致**；reconcile_summary 仅时间戳/耗时字段不同 |
| R5 | **亲算①费用**（半分边界案例 F000565 sh.600584 2020-03-24 pm 卖出） | Decimal 手算：名义 14805.00 × 0.001 = 14.805 → HALF_UP=14.81（ref）；float 14.805 表示略小 → 14.80（engine）；net_cash 两者同为 14785.19 | **证实为纯舍入位置表示差，经济影响 0.00**；实施者的"半分边界 float 表示"解释成立 |
| R6 | **亲算②公司行动**（sz.000711 2017-04-18 分红） | 手算 10.0 元/手 ÷ 100 × 600 股 = 60.00 元 | 与 run 记录和参考复算一致（146 条公司行动 ratio/cash/shares 差异全为 0） |
| R7 | **亲算③现金结算**（F000565 卖出款时点） | 沙箱行情核对 2020-03-24/25 为连续交易日 | 2020-03-24 pm 卖出款 2020-03-25 am 转可用，符合"次一 session"冻结合同；cash_reconciliation 逐 checkpoint 对上（首分叉日 2016-03-01 起 0.01 元级累计，2019 年末最大 -0.06 元） |
| R8 | 覆盖核对 | coverage_manifest.json | 10 个已列名臂（基线 3 + 四主臂 4 + 随机对照 3）× 14620 日 × 3319 笔成交 × 146 条公司行动全覆盖；exact 轨道最大残差 3.6×10⁻¹⁰ 元 |

## 逐门裁定

| 门 | 裁定 | 依据 |
|---|---|---|
| C2-01 核心会计函数未调用主引擎 | **PASS** | R3；reference_independence.md |
| C2-02 手算期望先于主引擎结果形成 | **PASS** | TV-A01..A05 取自 2026-09-21 执行包（先于一切 C2 代码）；hand_calculated_expected.csv 25 行含 4 个扩展手算案例（附过程 md） |
| C2-03 固定成交费用与现金逐分对账 | **PASS** | R4/R5：逐笔费用 3319 笔中仅 8 笔半分边界差（佣金 1、印花 7），逐条列出且 net_cash 差 0.00；exact 轨道 3.6e-10 |
| C2-04 待结算与可用现金无重复计入 | **PASS** | R7；cash_reconciliation 51 行 checkpoint（free/unsettled/total 三分离对上） |
| C2-05 分红/送转/零股及批次数量正确 | **PASS** | R6；146 条差异全 0；期末股数 10/10 臂一致 |
| C2-06 所选真实 run 全部事件已覆盖 | **PASS** | R8（任务书列名 10 臂全覆盖；"9 个"为任务书笔误，实施者按列名覆盖并如实记录） |
| C2-07 固定路径费用压力单调性 | **PASS** | R2（TV-B30 测试通过；测试限定固定成交序列，未外推动态路径） |
| C2-08 独立复跑且无未解释差 | **PASS（本文件）** | R4 字节级复现 + R5-R7 亲算三例 + 表示差逐条裁决（下） |

## 关键裁决：0.01 元级舍入位置差（C2 核心问题）

**裁定：纯数值表示差，接受，非阻断。**依据：
1. exact 轨道（Decimal 不舍入 vs 引擎 float64）最大残差 3.6×10⁻¹⁰ 元——证明账本无事件遗漏、无经济错误；
2. 全部差异定位在"每笔现金变动处 HALF_UP 到分"（参考，合同口径）与"全程 float 不舍入"（引擎，实现事实）两种舍入制度的半分边界，且逐条列出发生节点与累计影响（fee_type_reconciliation + implementer_rerun_and_diff_analysis.md），符合主计划 §7"逐个列明、由审阅者判断"的程序，**不是**"笔数×一分"的毯式容差；
3. R5 审阅者亲算复现了边界机制。

**后续处置**：该差不影响 C3/C5 及以后任何研究结论的量级（≤0.14 元/日，相对 50 万本金 3×10⁻⁷）。若用户要求引擎也逐笔量化到分，属 C4 代码修复需另行授权；默认维持现状并以参考账本为对账标准。**用户裁决项保留**（实施者已列）。

## 开放问题处置

| 问题 | 裁定 |
|---|---|
| C2-OBS-01 估值 mark 实为停牌日 carry-forward close，合同文本只写"官方日线 close" | **转 C4 合同文本修订项**（文档补充，非引擎改动；引擎行为是合理解释，参考实现按对齐后口径复算通过） |
| FIFO 消耗与逐批风险意图错配（INFO） | 转 C3 席位/批次链核验（主计划 8-C3-B 已预设） |
| 3 个 MINOR（run 产物缺中间现金拆分明细等） | 维持登记，C4 收尾统一处置 |

## 技术意见

**accepted**（工程验收：C2 通过，8/8 门）。账本层"钱和股票算得对"在所选 10 臂范围内成立；此 accepted 不延伸为"引擎完全可靠/可实盘"，成交真实性属 C3。

**下一阶段确认**：C3 进入条件满足。C3 必须包含：①C-05 cap→限价链条在真实策略链上的验证；②11:30 不变性在真实决策路径的重证（C1 局限 1）；③FIFO/批次/席位/恢复链（含 C2 转入的错配项）；④涨跌停表缺口口径按 C1 数据卡执行。

此意见绑定上述身份；新提交/数据/配置改变后需复核。
