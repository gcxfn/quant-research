# 个股主收益：可信系统重建与策略研究（阶段 C0–C9）

- 建立日期：2026-09-22（C0 阶段）
- 状态：**C2 已实施／待独立审阅**（C1 已独立审阅 accepted）。本文件是本项目新阶段线的主计划**索引**，不是执行包全文的副本。
- 计划正本：`docs/quant_stage_plan_20260922/01_master_plan.md`（阶段目标、方法、验收、预算、停机决策全部以该文件为准）
- 验收矩阵：`docs/quant_stage_plan_20260922/02_acceptance_matrix.csv`（80 项，C0-01..C9-08）
- 授权与边界建议：`docs/quant_stage_plan_20260922/03_governance.json`（**建议稿，未部署**）
- 证据与接口字段规格：`docs/quant_stage_plan_20260922/04_evidence_spec.md`；手算与反证场景：`docs/quant_stage_plan_20260922/05_test_vectors.md`
- C0 证据目录：`docs/evidence/trust-rebuild/20260922T013755-trust-c0-c17494/`
- C1 证据目录：`docs/evidence/trust-rebuild/20260922T020344-trust-c1-479c46/`
- C2 证据目录：`docs/evidence/trust-rebuild/20260922T025434-trust-c2-a17b3e/`
- 上一个阶段线（A/B 与旧 P 系列）的历史记录：`docs/plans/daily-short-term-rebuild.md`、`docs/research/research-ledger-20260921.md`、`docs/evidence/trial-ledger.md`

> 维护规则：本文件只保留长期有效的目标、阶段表、当前状态与接口要点。实验参数、单次运行结果与交接细节写入对应的预登记、研究报告与运行目录。每个阶段的完成记录追加到本文件末节，不另开平行主计划。

## 1. 目标

在统一的 **500,000 元**账户内，以**个股为主要收益来源、现金为防守资金**，研究税费后全账户复利年化**严格大于 10%**、每日账户权益最大回撤幅度**严格小于 20%** 的历史可行策略。账户级结果包含全部闲置现金；不以股票投入部分的年化替代总账户成绩。不保证未来、不把历史达标当实盘授权。

工程侧目标是与策略业绩无关的第二条线：给定同一输入、同一合同、同一版本，能够独立重建交易、资金与权益，差异可解释，违规可阻断，证据可追溯。

## 2. 阶段表（C0–C9）

阶段定义、进入条件、方法与验收以执行包主计划第 5–14 节为准；下表只做导航，不复制正文。

| 阶段 | 唯一核心问题 | 主要产物 | 依赖 | 状态 |
|---|---|---|---|---|
| C0 | 当前在执行哪份合同、哪些工作已做过？ | 冻结配置、冲突表、证据索引、授权状态 | — | **accepted**（8/8 门；`20260922T013755-trust-c0-c17494`） |
| C1 | 所有决策/标签/估值是否只看到许可信息？ | Dev 沙箱、数据卡、接口与时间断言 | C0 | **accepted**（8/8 门；`20260922T020344-trust-c1-479c46`） |
| C2 | 给定同一批成交，钱和股票是否算对？ | 独立参考账本、逐分对账、手算证据 | C1 | **accepted**（8/8 门；`20260922T025434-trust-c2-a17b3e`） |
| C3 | 给定同一订单，为何会成交？策略规则如何形成订单？ | 独立撮合、订单链、批次/席位/恢复测试 | C1 | **accepted**（8/8 门；`20260922T035220-trust-c3-c8af13`） |
| C4 | 哪些差异确实需要修？ | 缺陷关闭、受影响重放、可信性报告 | C2+C3 | **accepted**（8/8 门，G4 达成，ACCEPTED_SCOPED；`20260922T051244-trust-c4-c4fc42`） |
| C5 | B1 有没有尚值得花预算的时间合规线索？ | 逐事件表、匹配对照、聚集风险、捕获漏斗 | C4 | not_started（**待用户批准后进入**；输入已就绪） |
| C6 | 优势丢在席位接纳还是订单实现？ | 固定 4 主臂矩阵（≤32 输出配置）、全臂留存 | C5 | not_started |
| C7 | 经证据支持的机制能否支持 10%/20%？ | 统一账户、≤20 配置、压力结果 | C6 | not_started |
| C8 | 冻结候选在授权后续样本是否仍成立？ | 一次性验证包（≤2 候选） | C7 且用户单独授权 | not_started（默认锁住） |
| C9 | 真实账户输入与建议闭环是否安全一致？ | 合成演练、影子运行申请、操作手册 | C8 | not_started |

并行边界（主计划 4、15.3）：C1 验收后 C2 与 C3 可并行；C6 禁止与 C4 的代码修复并行；C8 不与使用其输出的开发任务并行。接口未冻结前不得让另一个 agent 猜字段先开工。

## 3. 当前状态（C0 实测，2026-09-22）

- 代码版本：`main` @ `ae226d964b1ea1dccfb60a42ae943c6da8a179e6`；本地与 `origin/main` 一致（ahead/behind 0/0）。
- 工作树不干净：8 个已修改 + 7 个未跟踪条目，全部属 2026-09-22 凌晨的「阶段 A/B 复审落地修正」批次。详见 C0 证据目录 `takeover_state.md`。
- **未发现 C1–C9 的任何进展**（按新计划命名的产物、分支、运行均不存在）；仓库内已有的 “C0” 指旧归因修正批次，与阶段 C0 撞名。
- 阶段 A/B 的既有结论维持：基线 v4 FULL-bin 净 CAGR −2.90%/MDD −27.29%；阶段 B 四候选 0/4 存活；随机对照 +1.95%（三种子均值）好于全部候选。
- 归因口径已被 2026-09-22 的复算修正（B1 缺口从“订单结构”改为“席位接纳”）；该修正**零尝试消费**，不新增研究结论的独立性。
- 权限落实：`enforcement_level = procedural_only`（main 未保护、零 CI、无独立环境、实施/审阅同机器同凭据）。见 C0 `permissions_review.md`。
- C1 实测（2026-09-22 02:03–02:35）：工作树状态与 C0 记录一致（既有 8 个已修改文件未动，mtime ≤ 00:35）；C1 只新增文件（3 个 data 模块、2 个工具、2 个测试、1 个沙箱数据集、1 个证据目录），未修改任何既有实现。Dev 沙箱已建立：`data/processed/dev-sandbox-20260922/`（7 类数据集 / 12 文件 / 19,501,006 行 / 374 MB，gitignored）。

## 4. C0 完成记录

### 独立审阅裁定（2026-09-22，主对话会话）

- **工程验收：accepted**（8/8 门 PASS）。审阅证据：`docs/evidence/trust-rebuild/20260922T013755-trust-c0-c17494/independent_review.md`（R1-R7 独立命令核验：git 快照比对、检查器实测、SHA256 抽查 4/4、×1.01 门槛/限价代码亲验、Val 接触来源核对）。
- 执行包检查器终态：`EVIDENCE_FILES_OK`（exit 0，12 项证据验证通过）。
- 开放问题处置：C0-BLK-01（舍入规则）转 C1 强制关闭项，审阅者给出默认裁定（参考账本 Decimal ROUND_HALF_UP 到分，待用户追认）；C0-MAJ-01（×1.01 语义）转 C3-A 必测项；三个 MINOR 分别延期至 C4/用户。详见 independent_review.md"开放问题的处置裁定"。
- 仓库旧"C0"改称"归因修正批次（C0-attrib）"，避免与新阶段 C0 混淆（冲突 C-11）。
- 验收矩阵 `02_acceptance_matrix.csv` C0-01..C0-08 已回填（该文件因此与 package_manifest.json v1.0 的字节记录不一致，属审阅登记的预期变更）。
- 下一阶段：C1 已获用户本会话持续授权（完成 c0-c4 的目标指令）；C1 附加强制项见 independent_review.md"下一阶段确认"。

实施者提交内容（2026-09-22，run `20260922T013755-trust-c0-c17494`）：

- 新增 `docs/evidence/trust-rebuild/20260922T013755-trust-c0-c17494/`：`takeover_state.md`、`contract_snapshot.json`、`contract_conflicts.csv`（12 行）、`evidence_index.csv`（44 行）、`access_ledger.csv`（9 行）、`change_scope_review.md`、`permissions_review.md`、`agents_amendment_proposal.md`、`stage_report.json`。
- 新建本文件；未修改 `src/`、`tests/`、`AGENTS.md` 或任何已跟踪文件；未运行回测/测试/因子计算；未读 2021 年以后行情或任何 Val 收益。
- 门状态（实施者视角）：C0-01..C0-07 自评 PASS，C0-08（独立审阅）PENDING，因此工程验收 = pending。

待用户/审阅者补：审阅者身份与会话、实际执行的命令与退出码、故意反证结果、对 C0-08 的裁定。

## 4.1 C1 完成记录（2026-09-22，实施者视角）

### 独立审阅裁定（2026-09-22，主对话会话）

- **工程验收：accepted**（8/8 门 PASS）。审阅证据：`docs/evidence/trust-rebuild/20260922T020344-trust-c1-479c46/independent_review.md`（R1-R9 独立动作：检查器 `EVIDENCE_FILES_OK`、41 项测试独立重跑、沙箱 12 个 parquet 独立扫描无 2021+ 行、加载器四类非法访问亲测全部拒绝、interface_contract 逐节核对、删失审计与 C0 台账交叉一致、测试正向对照抽查）。
- 检查器终态：`EVIDENCE_FILES_OK`（36 项证据，两份 junit 各 41/0/0）。
- 关键局限（已登记去向）：11:30 不变性当前在合同层参考决策函数上证明，真实策略链的重证义务转 C3-B；涨跌停表缺口与 4 只缺半日 bar 的处理口径转 C3 撮合输入；预告 PIT 不可证标记转 C5。6 个 MINOR 开放项不阻断。
- 下一阶段：C2 先行（本轮按用户指令串行），必须吃 interface_contract.json 并按舍入规则逐分对账。

- run：`20260922T020344-trust-c1-479c46`；证据目录 `docs/evidence/trust-rebuild/20260922T020344-trust-c1-479c46/`（stage_report.json 与 34 项哈希证据）。
- 代码版本：`ae226d964b1ea1dccfb60a42ae943c6da8a179e6`（沿用 C0 的工作树状态；C1 未提交任何改动）。
- 交付包检查器：`EVIDENCE_CHECK_FILES_OK`（exit 0，34 项证据验证通过，junit 41 passed / 0 skipped）。
- **本次实际新增（只新增，未改既有实现）**：
  - `src/quant/data/temporal_contract.py`：时间四件套、保守时钟、标签窗（自身/市场交易日两种口径 + 边界标记）、预告区间与版本链、新鲜度门。纯函数、仅标准库。
  - `src/quant/data/dev_sandbox.py`：Dev 沙箱加载器（dataset_id 白名单 + manifest 文件白名单 + 日期上限与读后实测断言 + 缓存键构造）。
  - `src/quant/data/dev_sandbox_export.py` + `tools/export_dev_sandbox.py`：受控导出，输出后逐文件重扫并硬断言不含 2021+ 行。
  - `tools/run_record.py`：跑真实命令并产出符合模板的 run 记录（含子进程峰值内存采样、代码/配置身份前后比对、输出臂核对）。
  - `tests/test_temporal_isolation.py`（28 项）、`tests/test_dev_sandbox.py`（13 项）：全部合成数据，41 passed、0 skip/xfail。
  - `data/processed/dev-sandbox-20260922/`：7 类数据集、12 个文件、19,501,006 行、374 MB，附 `dataset_manifest.json`（源 SHA256、过滤规则、实测日期范围、输出 SHA256、`no_2021plus_verification.passed=true`）。
  - 证据：`interface_contract.json`（C1-07 冻结接口）、`data_cards.md`（C1-05）、`announcement_version_audit.csv` + `b1_102_field_spotcheck.csv`（C1-06）、`censoring_audit.csv`（C1-08）、`sandbox_permission_demo.log`（权限演示 22/22 符合预期）。
- **C0 强制项关闭情况**：
  1. 舍入规则已在 `interface_contract.json:fee_schema.rounding_rule` 落为审阅者默认裁定（Decimal + 每笔现金变动 ROUND_HALF_UP 到 0.01 元、逐分一致、未解释一分差即阻断），标注"审阅者裁定，待用户追认"；未改任何费率。
  2. C-05 双轨：订单 schema 中 `trigger_cap` 与 `limit_price` 为两个独立必填字段，注明"cap=签发门槛、limit=决策锚价"的实现事实与 C3-A 待验关系；C1 只登记不裁定。
  3. 混合年份过滤口径已写入数据卡第 0 节，并升级为受控导出 + 白名单加载器（AL-02 的风险从"程序化过滤"改为"沙箱隔离正常路径"）。
- **门状态（实施者自评，非验收）**：C1-01..C1-08 均 PASS 并附证据；独立审阅未发生，因此 `engineering_state=pending`，不由实施者代签。
- **已知限制与开放项**：见证据目录 `stage_report.json`（6 条 MINOR，归属 C2/C3/C4/C5）与其中 limitations（物理隔离仍为 procedural_only、单一行情上游、未重跑既有测试套件等）。
- **未做**：未跑任何回测/策略/因子；未读 2021+ 行情或任何 Val 收益；未改 `src/quant/backtest|research|portfolio|factors` 与 AGENTS.md；未 git 提交/推送。



来自 `04_evidence_spec.md` 与 C0 合同核对，C1 需要落地的关键点：

1. **标识体系分层**：`event_id`（信息事件）/ `intent_id`（经济意图）/ `order_id`（具体半日订单）/ `fill_id`（成交）/ `position_cycle_id`（持有周期）/ `clip_id`（取得批次）。重挂产生新 `order_id` 但关联同 `intent_id`；禁止用“同股票三日内首笔买入”代替唯一对应（归因 v1 的缺陷正是这一条）。
2. **时间字段四件套**：`event_at`（发生）/ `available_at`（公开可得）/ `label_end_at`（样本可评价终点）/ 决策点 `decision_at`，关系必须是 `available_at <= decision_at < live_from`。只有披露日期没有时分时，沿既有保守时钟：公告当日收盘后视为可得，下一交易日 11:30 最早决策。
3. **金额与舍入必须先冻结**：C0 已把 `fee_schema.rounding_rule` 标为 BLOCKING。C1 必须明确舍入发生在哪个节点、用哪种规则（分/角、half-up 或截断），否则 C2 的“逐分对账”没有判定标准。
4. **cap→限价链条必须显式化**：当前入场的 ×1.01 只是签发门槛，实际订单限价等于决策锚价（C0 冲突 `C-05`）。C1/C3 需要在订单表里分开 `trigger_cap` 与 `limit_price` 两个字段，并证明二者关系。
5. **标签边界字段**：每个 20 日标签同时保存 `window_complete`、`n_market_sessions`、`n_own_sessions`、`crosses_dev_boundary`；不完整窗口保留、不进完整窗口均值；对照必须同日同起止。
6. **数据挂载方式**：C1 要求 Dev-only 受控导出。当前各运行读混合年份文件后程序化过滤（`assert_frozen`），属“过滤”而非“隔离”，不能当成隔离已落实。
7. **产物字段版本化**：所有产物记录 `schema_version / run_id / code_commit / source_sha256 / contract_sha256 / dataset_id`；文件原始 SHA256 与规范化 SHA256 分开。

### 独立审阅裁定（2026-09-22，主对话会话）

- **工程验收：accepted**（8/8 门 PASS）。审阅证据：`docs/evidence/trust-rebuild/20260922T025434-trust-c2-a17b3e/independent_review.md`（R1-R8：26 项测试独立重跑、全量对账独立复跑三张 CSV 字节级一致、亲算费用半分边界/分红/结算时点三例、import 独立性扫描）。
- 关键裁决：0.01 元级差异裁定为**纯舍入位置表示差，接受**（exact 轨道 3.6e-10 证明无经济错误；逐条列出非毯式容差）。用户裁决项保留：是否要求引擎逐笔量化到分（属 C4 需另授权，默认不要求）。
- 开放问题去向：C2-OBS-01（停牌日 mark=carry-forward，合同文本欠明确）转 C4 文本修订；FIFO 与逐批风险意图错配转 C3。
- 下一阶段：C3 进入条件满足。

## 4.2 C2 完成记录（2026-09-22，实施者视角）

- run：`20260922T025434-trust-c2-a17b3e`；证据目录 `docs/evidence/trust-rebuild/20260922T025434-trust-c2-a17b3e/`（stage_report.json + 16 项哈希证据）。
- 代码版本：`ae226d964b1ea1dccfb60a42ae943c6da8a179e6`（沿用 C0/C1 工作树；本轮只**新增**文件，未改任何既有实现，未提交）。
- 运行状态：completed。工程验收：**pending**（C2-08 独立复跑属审阅者职责，实施者不代签）。研究结论：not_evaluated（本阶段不涉及策略判定）。
- **本次实际新增**：
  - `src/quant/research/reference_ledger.py`：独立参考账本（纯标准库 `decimal`/`datetime`/`dataclasses`）。实现费用公式、现金三分离（free_settled / am_to_pm / unsettled_sale_proceeds）、T+1 可卖量（含公司行动零股当日可卖）、FIFO 批次消耗、送转逐 clip half-up、分红每手÷round_lot×除息前持股、权益恒等式、年度收益与 MDD 幅度。
  - `src/quant/research/reference_ledger_reconcile.py`：对账驱动（只读 run 产物 + C1 Dev 沙箱；新增依赖仅 polars 与 `quant.data.dev_sandbox`）。
  - `tests/test_reference_ledger.py`：26 项测试，0 skip/xfail。含 TV-A01..A05 手算（精确到分）、4 个扩展手算案例、C 表九类反证注入（重复成交、价格×100、每手误当每股、成本符号反转、卖出款提前可用、旧批次残留、未来价替代上午价、首年收益遗漏、负号 MDD）、T+1/结算/可卖量/公司行动衔接专项、TV-B30 费用单调性。
  - 证据：`reference_independence.md`（AST + 加载期扫描）、`hand_calculated_expected.csv` + `.md`、`ledger_reconciliation.csv`、`cash_reconciliation.csv`、`fee_type_reconciliation.csv`、`corporate_action_reconciliation.csv`、`coverage_manifest.json`、`ledger_tests.xml`、`reconcile_summary.json`、`implementer_rerun_and_diff_analysis.md`、两个 run_record。
- **对账范围与结果**：10 个臂（阶段 A `20260921T210100-baseline-replay4` 的 FULL-bin/NOSNR-bin/NOACCT-bin + 阶段 B `20260921T223157-eventfam-main` 的 A1/A2/B1/B2 + 三条随机对照 `20260921T223217-eventfam-rnd` 的 RND-11/23/47；任务书文字写"9 个目标"，逐项列名实为 3+4+3=10，本阶段全覆盖）。14620 个交易日记录 + 3319 笔成交 + 146 条公司行动全部复算：
  - 精确口径（Decimal 不舍入）与主引擎逐日权益最大差 **3.6×10⁻¹⁰ 元**（float eps），10/10 臂期末股数完全一致 → 无遗漏事件、无经济错误。
  - 逐笔舍入口径（合同评分口径）日终权益差最大 **0.14 元**，已定位为"舍入位置"表示差；逐笔费用中佣金 1 笔、印花 7 笔差 0.01 元，全部为半分边界 float 表示；未解释金额差/股数差/结算时序差 = 0。
  - 现金三分离逐日对上（run 产物含 settled / pending_next_day / pending_am_to_pm 三列，无需补中间状态）；146 条公司行动 ratio/cash/shares 差异全 0。
- **复算发现（登记，不改主引擎）**：估值 mark 的 carry-forward 口径——合同 `valuation.mark` 只写"官方日线 close"，主引擎实现为 `tradestatus!=0` 行的 on/before carry-forward；参考账本初版用当日原始 close，导致 3 个臂 18–544 元市值差，对齐后精确残差回到 float eps。列为合同文字欠明确（C2-OBS-01），一并登记逐笔舍入位置差（C2-OBS-02）、FIFO 与逐批风险意图错配（C2-OBS-04，转 C3/C4）。
- **检查器**：`check_delivery.py` 验证 16 项证据全部通过、junit 26/0/0/0、两份 run_record 有效；唯一报错是 `C2-08: gate is not PASS`——因独立复跑属审阅者职责，实施者按纪律不自签，`engineering_state=pending`。这是预期的、诚实的状态。
- **未做**：未重做信号/回测/撮合；未改 `src/quant/backtest|portfolio` 与 AGENTS.md；未读 2021+ 行情或任何 Val 收益；未 git 提交/推送。C2-08 的独立复跑与费用/分红/多批卖出亲算待审阅者完成。

### 独立审阅裁定（2026-09-22，主对话会话）

- **工程验收：accepted**（8/8 门 PASS）。审阅证据：`docs/evidence/trust-rebuild/20260922T035220-trust-c3-c8af13/independent_review.md`（R1-R9：亲测严格穿透边界/K=3 兜底/过期不复活三例、22 项测试独立重跑、5334 单 core_fields_match 全 True 核对、C-05 以 39/39 limit==anchor 关闭、11:30 不变性含双向对照）。
- 定性结论新增：×1.01 是签发门槛而非限价（C-05 关闭）；9 臂成交判定 100% 可复现。
- 开放问题去向：FIFO vs 逐批风险错配、席位账同源、25% 帽快照口径 → 转 C4 定向处置；95 笔费用 0.01 元差沿用 C2 裁定。
- 下一阶段：C4 进入条件满足，定向修复清单见审阅意见。

## 4.3 C3 完成记录（2026-09-22，实施者视角）

- run：`20260922T035220-trust-c3-c8af13`；证据目录 `docs/evidence/trust-rebuild/20260922T035220-trust-c3-c8af13/`（stage_report.json + 27 项哈希证据）。
- 代码版本：`ae226d964b1ea1dccfb60a42ae943c6da8a179e6`（沿用 C0/C1 工作树；本轮只**新增**文件 + 重写接管那份半成品 matcher，未改任何既有实现，未提交）。
- 运行状态：completed。工程验收：**pending**（C3-01..C3-08 为实施者自评，G3 与 independent_review 由审阅者另行完成，实施者不自签）。研究结论：not_evaluated。
- **本次实际新增/改动**：
  - `src/quant/research/reference_matcher.py`：独立第二套撮合实现（重写接管）。接管时该文件 758 行、无调用方、无测试；逐项对照冻结合同后保留数据模型与判定骨架，**修复 10 项缺陷**（A1 开环卖单主路径实为抛异常的桩、A2 卖单漏传 symbol 致 ETF 错加印花、A3 用值相等定位批次会改错同值批次、A4 缺 expires_at 守卫、A5 无替代/同半日覆盖规则、A6 无部分成交语义、A7 K 计数在无关原因上误累加、A8 无公司行动份额变换、A9 末状态枚举缺 partial_fill、A10 允许隐式推断日历会静默丢停牌半日）。逐项处置见 `c3_case_report.md` 第 1 节。
  - `src/quant/research/reference_matcher_reconcile.py`：C3-A 开环对账驱动（只读 run 产物 + C1 沙箱；零 `quant.backtest`/`quant.portfolio` 依赖）。
  - `src/quant/research/c3_semantic_chain.py`：C3-B/C 语义链驱动（**故意**读真实策略/风险代码；已在文件内声明不在 C3-01 约束内）。
  - `tests/test_reference_matcher.py`（22 项，0 skip）与 `tests/test_reference_matcher_state.py`（2 项，0 skip）：TV-B01..B14 全场景 + TV-B18/B22/B23 + 闭环状态响应对照。
- **C3-A 开环匹配结果**：9 个具订单级产物的臂（baseline replay 5 臂 + eventfam main 4 臂）共 **5,260 张限价单 + 74 次 K=3 兜底尝试**逐笔重新判定，成交与否/日期/半日/股数/价格/未成交原因/末状态 **100% 一致**；4,948 笔成交中 4,853 笔连费用逐分一致，其余 95 笔只差 ≤0.01 元（C2 已裁定的 HALF_UP-到-分 vs float64 表示差），股数与价格差为 0。缺订单日志的臂只有 `20260922T002611-eventfam-attrib2-eed5cf`（只有汇总结论），登记为 C4 缺口。
- **C3-A 闭环对照**：合成确定性策略 + 同一段合成半日行情，独立 matcher+C2 口径账本 vs `band_engine`（`execution_clock='halfday'`）逐半日对比成交/股数/价格/费用/持股/现金；两个场景（当日成交+部分止盈卖出；风险卖出 K=3 兜底 + 停牌冻结计数）全部一致，期末现金差 < 0.05 元。
- **C3-B 结果**：
  - **C-05 关闭**：`×1.01` 是**签发门槛**不是限价。B1 全部 102 事件逐单给出 trigger_close / trigger_cap / decision_anchor / limit_price 四值；39/39 签发单限价 == 决策锚价，0/39 等于 cap；63/102 因 slot_full 未签发。与 provider 的 `cap_price=lvl×(1+CHASE)` + `anchor>cap 则 skip_cap` 和引擎建单 `anchor_price=anchor` 两处代码互证。**只关闭追踪义务，不改合同不改代码**。
  - **11:30 不变性真实链重证**（C1 局限 1 的关闭）：真实 `EventFamilyProvider` + 真实引擎，6 个决策点，5/5 检查 PASS——改当日午后（含官方收盘）后 11:30 的 provider 输出与引擎订单行逐位不变；正向对照（改午后使 15:00 变化、改上午使 11:30 变化）均成立；D1 历史在三个变体下完全一致。
  - 席位账 102 行分组守恒（issued 39 + slot_full 63 = 102），无 `held+pending>4`；D3 恢复队列两条合成路径（正常反弹 / 持续低迷）与独立手算 9/9+9/9 一致；退出→订单映射 59 行覆盖 stop/time_exit/account_trim/take_half/clear/protection。
- **C3-C 披露**：已授权分钟样本是每股每日一行的投影表（无分钟价格路径）。抽样 1,030 笔 `never_crossed` 订单：半日极值**零越界**（没有制造数据）；以全日分钟极值为细粒度一侧时 246 笔（23.9%）本可穿透、严格归因于本 session 的 19 笔（1.8%），方向恒为「半日保守少判成交」，反向误判 0 例。「订单生效半日前是否已穿透」与「排队成交率」**未核验**（需受控提取原始分钟序列 + 无订单簿）。
- **转 C4 的已知项**：①FIFO 消耗 vs 逐批风险意图错配（C2 转入，建议保持 FIFO 并明确无逐批退出原语）；②席位账取自与 B1 同参数的 attrib2 run（B1 主 run 不落漏斗产物），建议让主 run 落 `event_funnel` 级产物；③25% 帽的决策点权益快照口径需按 M2 精确定义；④attrib2 run 若需订单级核验须重跑留产物。
- **未做**：未跑新回测、未改 `src/quant/backtest|portfolio` 与 AGENTS.md、未读 2021+ 行情；合成场景（闭环对照、11:30 不变性、D3 恢复路径）全部在产物与报告中标注为合成；未 git 提交/推送。G3 的独立审阅与四份产物（order_reconciliation / intent_to_order_trace / seat_lifecycle / state_transition 之外的审阅动作）待审阅者完成。

### 独立审阅裁定（2026-09-22，主对话会话）——工程批次收官

- **工程验收：accepted**（8/8 门 PASS；**G4 达成，C0-C4 工程批次全部验收通过**）。审阅证据：`docs/evidence/trust-rebuild/20260922T051244-trust-c4-c4fc42/independent_review.md`（R1-R7：检查器 24 项证据+junit 804/0/0、零引擎改动 git 核验、合同纯追加核验、台账补登核验、A1 2015 首年 +14.0509% 独立复算一致、裁决与决策记录闭合性）。
- 裁决确认：**ACCEPTED_SCOPED**。公共系统（账本/撮合/语义链）在主板股票半日合同范围内可信；工程按 G4 退出条件停止无收益关联的扩张。
- 三项定向调查（FIFO 错配/席位账同源/停牌 mark）全部文档化关闭，零引擎代码修复；六项旧解释修正落账；804 项测试归档。
- 下一阶段（C5 归因复算）**不在本轮授权内**，需用户另行批准；其输入已就绪。
- 用户留存决策：舍入规则追认、未提交批次的 git 提交方式（当前 C0-C4 全部产物未提交）、板块权限与环境项。

## 4.4 C4 完成记录（2026-09-22，实施者视角）

- run：`20260922T051244-trust-c4-c4fc42`；证据目录 `docs/evidence/trust-rebuild/20260922T051244-trust-c4-c4fc42/`（stage_report.json + run_manifest.json + tests.xml + 9 份交付物）。
- 代码版本：`ae226d964b1ea1dccfb60a42ae943c6da8a179e6`（沿用 C0/C1/C2/C3 工作树；**本轮零 src 改动**，未提交）。
- 运行状态：completed。工程验收：**pending**（C4-01..C4-08 为实施者自评，G4 与 independent_review 由审阅者另行完成，实施者不自签）。研究结论：not_evaluated。
- **裁决：ACCEPTED_SCOPED**（实施者视角，待独立审阅确认）。C2/C3 已证明**未发现引擎/账户层代码缺陷**，故本轮**无引擎修复 → 无重跑回测的重放义务**；受影响面收缩为「受影响统计复算 + 台账/声明登记」。
- **三项定向调查（全部文档化关闭，不改码）**：
  1. `C4-DEF-01` FIFO 消耗 vs 逐批风险意图（C3-OBS-03）：策略侧风险退出为**整仓退出**（`single_name_rules.py` 头部 + `decide()`：任一 clip 触发整仓清），唯一的逐批数量阶梯 +2R 分批止盈是**整仓绝对总股目标**（模块明文 FIFO 无害）；B1 真实 46 笔卖出 `oversell=0`，部分 risk 卖出来自 D3 持仓级减仓。→ 保持 FIFO，明确「本策略不存在逐批风险退出原语」，逐批风险结论改述为聚合口径。决策记录 `docs/decisions/2026-09-22-fifo-vs-per-clip-risk-intent.md`。
  2. `C4-DEF-02` 席位账同源与 25% 帽快照（C3-OBS-04）：attrib2 manifest 断言 `fills/equity/trigger_stats` 与主 run **逐位相等**、engine sha 与盘上一致 → 是产物粒度差异而非语义不同源；12 个被对账臂事件表扫描 `cap` 命中 **0 条**、25% 帽从未绑定，故引擎与 matcher 的 am 快照潜在口径差**对已发表结论零影响**；引擎口径（`decision_snapshots[(day,sess)]`，pm 官方收盘 carry-forward / am 完成 am bar close）写入决策记录。决策记录 `docs/decisions/2026-09-22-seat-ledger-source-and-cap-snapshot.md`。
  3. `C4-DEF-03` 停牌/无行情日估值 mark（C2-OBS-01）：`p3-band-contract.md` **追加 §11** 修订节（不改原文），语义 = 停牌/无行情日按最近可得官方收盘 **carry-forward**，永不使用 `pm.close`；同步 C1 `interface_contract.json` 的 `ledger_snapshots.valuation` 段 + `schema_version 1.0→1.1` + `amendments A-01`。
- **声明修正（C4-06，6 行）**：`claim_correction_log.csv` 落账主计划 §9 六项——①「未参与」≠「限价未成交」（归因 v1 `unmatched` 口径废止，63/67 为席位满员跳过）；②首年收益（独立复算 A1 2015 **+14.0509%**、A2 **+2.5999%**，与文档 +14.05%/+2.60% 一致；A1/A2 2016–2020 仍逐年为负；判定不变）；③IDEAL/FULL 差不可加减（`stock_cash_baseline.md` 已撤回可加性读法）；④BM2 最低佣金伪影（`stock_event_research_prereg.md` §7 补注，旧判定与数字留档不改）；⑤「22 次」分账（独立配置 22 / 冒烟 0 / 工程复现 4 / 结果查看另记）；⑥Val 标签接触精准窗口（AL-01 2021-01..02 仅 B2/A 家族；AL-05 2021-01-01..2024-12-31、13 配置）。
- **台账补登**：`affected_runs.csv` **追加 4 行** attrib2（001213 failed / 001713、002000 superseded / 002611 valid），旧行未删未改；`trial-ledger.md` 追加「C4 补登」节、`trial-ledger.json` 新增 `c4_registration` 键（旧键逐键相等），attrib2 4 run 按 `engineering_replay` 登记父 run + bug_id，0 试验消费。
- **全量测试归档**：`PYTHONPATH=src .venv/Scripts/python.exe -m pytest tests/ --junitxml=<EV>/tests.xml -q` → **804 passed / 0 failed / 0 skipped**，47.46s，exit 0（`tests.xml` + `pytest_full.log`）。裸命令（无 `PYTHONPATH`）因 editable `.pth` 中文路径失效报 4 个收集错误，已如实留档（`pytest_nopath_failed.log`）并登记 `C4-OBS-04`。
- **无关路径控制（C4-04）**：零引擎/账户层代码改动（`git diff --stat -- src/quant/backtest src/quant/portfolio` 为空）+ `anchor_comparison.csv` 20 个锚/控制项修复前后语义等价（v4 FULL-bin −2.90%/−27.29%、NOSNR、NOACCT、SIG-reg/old、事件族四臂、随机对照三种子与均值）。
- **未做**：未改任何策略参数/费率/阈值、未改测试预期、未删除失败用例、未重跑回测、未读 2021+ 行情、未 git 提交/推送。G4 的独立审阅与 accepted/rejected 由审阅者完成。
- **移交用户/下一阶段的未决项**：费率舍入规则追认（C0-BLK-01→C1）；创业板/科创板/北交所权限（C-07）；editable 安装环境（C4-OBS-04）；README/p3 版本文字与引擎实际 v1.5 不一致（C4-OBS-05）；AL-05 三次 val 消费 run_id 未定位（C5 前补齐）。

## 6. 资源调查（本机实测，2026-09-22）

| 项 | 实测值 | 来源 |
|---|---|---|
| 操作系统 | Windows 10.0.26200（中文路径 `D:\量化`，UTF-8） | `platform.platform()` |
| CPU | 20 逻辑核 / 14 物理核 | `os.cpu_count()` / `psutil` |
| 内存 | 总 16.8 GB，**当前可用 4.7 GB** | `psutil.virtual_memory()` |
| D 盘 | 总 777.7 GB，**可用 212.5 GB** | `shutil.disk_usage` |
| 仓库数据体积 | `data/` 131 GB（原始 15 个来源目录 + processed 8 个数据集）；`artifacts/` 1.3 GB | `du -sh` |
| 项目解释器 | `D:\量化\.venv\Scripts\python.exe` = Python 3.11.15（运行 manifest 记录的也是它） | `.venv/Scripts/python.exe -V` |
| PATH 上的 `python` | 指向 `D:\AI\agent\hermes\venv`（agent 自己的环境，pandas 2.2.2）。**跑项目脚本必须显式用 `.venv` 的解释器** | `sys.executable` |
| pytest | 9.1.1 | `importlib.metadata` |
| 核心库 | polars 1.44.2、numpy 1.26.4、pandas 2.3.3、pyarrow 25.0.1、psutil 7.2.2 | 同上 |
| 研究与回测库 | scipy 1.17.1、scikit-learn 1.9.1、lightgbm 4.7.0、vectorbt 0.28.5、backtrader 1.9.78.123、rqalpha 6.3.0 | 同上 |
| 数据访问库 | baostock 0.9.3、tushare 1.4.29 | 同上 |
| 测试规模 | `tests/` 下静态 `def test_` 共 691 处（参数化后收集数会更多；报告中“713 passed”未在本阶段重跑，也无对应归档日志） | `grep -c` |
| 近期运行峰值内存 | 6.0–7.5 GB（基线 v4 6.0 GB；attrib2 三次运行 7.0/7.5/6.1 GB） | 各 run manifest `peak_memory_mb` |

**据此得到的资源结论**：单次全流程运行约需 6–8 GB 峰值内存，而当前可用内存只有 4.7 GB —— **不能并行跑两个全流程运行**，主计划 15.1 的“默认单 worker”在本机不是保守建议而是硬约束。任何新阶段在开工前必须先做小样本计时与峰值内存探测，并把上限写进预登记。磁盘 212 GB 可用对当前用法（单 run 数十 MB，数据只读）是充足的。

## 7. 真正需要用户裁决的缺口清单

以下事项 C0 无法自行裁定（其余技术细节已按主计划 2.3 的优先级处理）。

**A. 未提交工作如何处置**

1. 2026-09-22 凌晨那批修改（8 个已修改文件 + `attribution_lib.py` + `test_event_attribution_c0.py` + 4 个 attrib2 运行目录）要不要提交、以什么形式提交（一个提交还是拆分）、是否先入独立分支？C0 按指令未做任何 git 提交。
2. `20260922T001213-eventfam-attrib2-837163` 是 `status=failed` 的运行，目前既未提交也未登记进 `affected_runs.csv`。是否同意由下一阶段补登记（含失败原因与取代关系）？

**B. 权限与流程**

3. 是否给阶段实施开独立分支，以及是否给 `main` 加分支保护？注意本仓库是**单账号（`gcxfn`）个人项目且 main 未保护、零 CI**；单账号下 PR 审批会把自己锁死，需要先决定由谁承担审阅身份。
4. 是否建立最小 CI（至少 `pytest -q`）？否则“测试通过”永远只是文字声明。
5. 谁承担 K 角色（隔离数据、执行获准命令、归档）与 Val/2025+ 数据访问权限？目前全量数据在同一台机器上，任何会话都能读。

**C. 合同未定项**

6. **金额舍入规则**（`fee_schema.rounding_rule`）：BLOCKING。是否同意由 C1 在起草接口时先冻结（建议：费用与现金按分 half-up，价格按各自 tick），还是用户指定别种口径？
7. **入场限价语义**：确认为“×1.01 是签发门槛、实际限价 = 决策锚价”这一实现事实是本轮 E0 的**有意**设计，还是需要在 C4 统一改成“限价 = 上限”？这直接决定 C6 的 E0/E1 两臂是否真存在处理差异。
8. **创业板权限**：账户是否有创业板（300/301/302）权限？当前代码按“无权限”排除，依据是 2026-09-17 的会话判断，仓库内无账户证据。权限存在与否会改变股票池与全部历史结论的适用范围。
9. **研究范围口径**：是否同意把 AGENTS 的“默认 2015–2024”收窄为“开发期 2015–2020，2021–2024 须单独授权”，与主计划一致？

**D. 主线与历史结论**

10. 是否接受 C0 交付的 `agents_amendment_proposal.md` 的 6 处最小修订（个股+现金主线、四股票席位、50 万不可覆盖、验收来源指向本文件、新增 §1.3 阶段与权限、研究范围收窄）？
11. 旧 “C0”（B1 归因修正批次）是否同意改称“复审修正批次（C0-attrib）”以避免与阶段 C0 撞名？
12. 阶段 B 的 B1 若重开，方向按归因修正后的建议是“席位接纳优先级（C1-S 臂）”。是否授权起草该预登记？（**本阶段不授权运行**。）

**E. 明确无需用户裁决的事项**（避免重复询问）

- 50 万元本金、个股只做多、现金防守、不连券商、不自动下单：用户已明确，C0 直接采用。
- 主计划 C0→C9 的依赖顺序与各阶段验收门：属计划内约定，按文件执行即可。
- 每席 10% 与单只 25% 的语义区分：C0 已在合同快照中分列，不需要用户选择。

## 8. 本文件之外不做的事

- 不复制执行包正文，不替代 `docs/plans/daily-short-term-rebuild.md` 的历史记录功能。
- 不在本文件写单次实验参数或收益数字（写入对应预登记/研究报告/运行目录）。
- 不在未经用户授权时开启任何阶段。
