# 实验结构化索引（2026-09-11）

机器可读索引：`artifacts/experiment-index-20260911/experiments.jsonl`（每实验/文档一行 JSON）。本文为人类可读摘要。

- 扫描范围：`docs/experiments/*.md`（83 份）、`docs/plans/*.md`（26 份），共 109 行索引；`docs/decisions.md`（126 条 D-决策）作为裁决对照源。`docs/experiments/` 下的 5 个 `.json` 机器可读工件（factor-ic-stocks / timesfm-* / strategy-v3-* / system-audit-bcde-probe）不单列索引行。
- verdict 口径：PASS/FAIL/SEALED/DESCRIPTIVE/PENDING/null，只按各文档自身明文判定收录；审核送审包（*-review-pack）定格为 PENDING，其后续裁决写入 death_or_survive_reason；审核报告判 CHANGES_REQUESTED 的记 null（枚举外值不推断）。
- 断链判定：文档内提到的 `artifacts/`、`configs/` 路径经 os.path.exists 核实；前缀式提及（如 `researcher_`）标注 note=prefix-match。
- 注意：本工作区存在在飞代理，docs/experiments 在本次扫描期间新增了 5 份 2026-09-11 文档（data-census、t0-minute-evidence、workspace-inventory、system-audit-wave1-independent-review、system-audit-fix-wave1-review-pack 已收录；如再新增需重跑索引）。

## 1. 统计

- verdict 分布：null=54、PENDING=32、FAIL=10、PASS=7、DESCRIPTIVE=5、SEALED=1
- 研究线分布（条数）：v3-etf=19、p4=19、factor-miner=16、system-audit=11、pv1-precision=8、mr-statarb=7、short-foundation=7、event-family=6、family-screening=5、data-audit=4、t0=3、weekly=2、daily-swing=1、top15-product=1
- FAIL/SEALED 集中的研究线：p4（3 条：p4-barrier-stream-result, p4-lowvol-h10-conclusion, p4-revised-selection-conclusion）；v3-etf（2 条：v3-daily-exit-conclusion, v3-daily-exit-independent-review）；weekly（2 条：weekly-entry-research, weekly-trade-research）；event-family（1 条：event-family-round1）；mr-statarb（1 条：mr-statarb-round1）；short-foundation（1 条：short-target-research）；t0（1 条：t0-minute-evidence）
- 决策对应：decisions.md 共 126 条 D-决策，80 条被至少一份索引文档对应，孤儿决策 46 条（见 §4.2）。

## 2. 研究线清单

### short-foundation（2026-09-05 → 2026-09-09）

- 代表文档：short-data-coverage、short-foundation-research、short-profit-research、short-target-research、p3-p1pool-rerun-task-brief
- 现状：死（作为盈利路线）。P0-P3底座建成并通过独立复审，但严格池上八组规则全窗口为负；旧池正收益被证实为幸存者偏差产物；盈利目标（年化10%/夏普1.5）从未达成。底座代码（P1数据层/P2撮合）存活并被后续所有线复用。

### p4（2026-09-07 → 2026-09-09）

- 代表文档：p4-factor-research、p4-revised-selection-conclusion、p4-lowvol-h10-conclusion
- 现状：死。48格（12候选x4止损）全部B2=False、期望净收益为负；低波动5→10会话延期假设FAIL终止；Gate D冻结；日线价量短线选股研发整体暂停。p4-r2 ETF混合池预登记搁置未执行。

### v3-etf（2026-09-09 → 2026-09-10）

- 代表文档：monthly-etf-t0-independent-review、v3-dd-attribution、v3-daily-exit-conclusion、v3-repair-artifact-review-pack、v3-arm-c-mechanism-artifact-review-pack
- 现状：生产主线，部分死。V3 R3（前视修复后）年化10.19%/夏普0.459/回撤58.85%——收益达标、风险目标FAIL，维持生产；修复轮ABC=FAIL封存；每日趋势退出FAIL判死不重开；臂C机制拆分判不确定不改生产；ETF清盘幸存者偏差数值上界不可识别（数据缺口）。

### t0（2026-09-09 → 2026-09-11）

- 代表文档：monthly-etf-t0-minute-probe、t0-range-calibration、t0-minute-evidence
- 现状：定位收窄。ETF分钟长历史免费源未解决（新浪仅320根）；5分钟保守回放显示对称档位做T六组合年度净增益全非正（无增益结论）；区间校准为描述性研究。t0维持费用后保本价位计算器定位，不承担盈利目标。

### mr-statarb（2026-09-09）

- 代表文档：mr-statarb-preregistration-draft、mr-statarb-round1
- 现状：死（本轮封存）。阶段C唯一候选m20_z05净期望+0.1076%、95%CI下界<0；封顶探索级；按预登记封存不追加调参；MR家族结论不重开（残差连续化表达转由 RESID_REV 子矿区承接）。

### event-family（2026-09-09 → 2026-09-10）

- 代表文档：event-family-preregistration-draft、event-family-round1
- 现状：死（本轮封存）。四构造无一过晋级线（E1_bull差3.3bp）；工件复算PASS后FAIL封存；事件型封存不重开（③家族连续化转 FLOW_CONT 子矿区）。

### family-screening（2026-09-10）

- 代表文档：family-batch-screening-preregistration-draft、family-screening-round1、⑤财务两附录
- 现状：部分存活。②③0/5未晋级（家族代表制不判死家族）；④价量仅PV1获精测资格；⑤财务F1/F4晋级+财务扩展F18/F20/F26/F27/F30晋级（7构造入攒批统考队列）。

### pv1-precision（2026-09-10）

- 代表文档：pv1-precision-test-preregistration-draft、pv1-precision-prerun-review-pack-round7
- 现状：在途（未定）。代码7轮审核PASS；in-window净年化+7.68%但CI含零；留出窗一次性考试按D-18攒批推迟，队列=PV1+财务7构造+R0幸存者。

### factor-miner（2026-09-10 → 2026-09-11）

- 代表文档：factor-miner-engine-preregistration-draft、prerun-review-pack x6、numpy双路径三评审、r1-formula-gap-analysis
- 现状：在途（开发主线引擎）。引擎六轮PASS后R0 TRAIN解锁；首跑因CS_RANK O(S^2*D)与稀疏字段崩溃终止修复，第7轮专项PASS后官方批重启；随后系统审计B~E首轮CHANGES_REQUESTED→R0暂停待修复审核；numpy路径未获正式授权；R1研究员池扩充中（实际215条）。

### system-audit（2026-09-10 → 2026-09-11）

- 代表文档：system-audit-conclusion、system-audit-fix-wave1-review-pack、system-audit-wave1-independent-review、data-census、workspace-inventory
- 现状：在途。分层审查A/B/C/D首轮全部CHANGES_REQUESTED；二波修复+加固波+盲预审闭合送审（D-2026-09-11-01）后，wave1独立复审仍CHANGES_REQUESTED（W1-01预热截断日期错位、W1-02递延账本等）；B-01 TRAIN定位扫描与数据普查已交付；R0重启待审核闭合。

### weekly（2026-09-05）

- 代表文档：weekly-entry-research、weekly-trade-research
- 现状：死。三组入场规则与周内标签方案均未达10%/1.5目标；冻结选出者样本外转负；不事后升级。

### daily-swing（2026-09-04/05）

- 代表文档：daily-swing-oos-methodology
- 现状：降级存活。daily-swing-v1降为研究对照（D-2026-09-05-01）；本实验仅方法学证据，未判有效性。

### data-audit（2026-09-09 → 2026-09-11）

- 代表文档：tushare三批拉取、data-census
- 现状：存活（基础设施）。三批tushare数据抽审PASS支撑事件/财务/资金流各线；数据普查确认TRAIN窗原始层无共同缺行、无inf/NaN污染（在市股范围）。

### top15-product（2026-09-11）

- 代表文档：top15-cost-breakeven
- 现状：在途（开发主线前置分析）。个股多因子月频Top15组合（D-2026-09-10-31）成本盈亏平衡表——k=15时最低佣金生效、双边12.5bps；无任何可执行判定。

## 3. 断链清单（referenced_artifacts / referenced_configs 不存在，共 13 处）

复现性风险点：以下文档引用的路径在当前工作区不存在。背景：artifacts/ 整体被 gitignore 排除（见 workspace-inventory-20260911 §7.9），所有送审包引用的工件仅存本地盘，换机即失。

| 实验/文档 id | 类型 | 路径 | 备注 |
|---|---|---|---|
| pv1-precision-prerun-review-pack-round2 | artifacts | `artifacts/pv1-precision/holdout_ledger.jsonl` |  |
| short-profit-research | artifacts | `artifacts/short-profit/new-run` |  |
| short-profit-research | artifacts | `artifacts/short-profit/reproduced` |  |
| short-target-research | artifacts | `artifacts/short-target/new-run` |  |
| short-target-research | artifacts | `artifacts/short-target/reproduced` |  |
| weekly-entry-research | artifacts | `artifacts/weekly-entry/new-run` |  |
| weekly-trade-research | artifacts | `artifacts/weekly-trade/new-run` |  |
| p4-factor-research | artifacts | `artifacts/short-foundation/p4-portfolio` |  |
| p4-factor-research | artifacts | `artifacts/short-foundation/p4-validation` |  |
| profit-oriented-next-steps | artifacts | `artifacts/short-forward` |  |
| profit-oriented-next-steps | artifacts | `artifacts/short-foundation/p4-portfolio` |  |
| profit-oriented-next-steps | artifacts | `artifacts/short-foundation/p4-validation` |  |
| short-foundation-rebuild | artifacts | `artifacts/short-forward` |  |

## 4. 孤儿

### 4.1 无决策对应的实验/文档（6 条）

data-census、r1-formula-gap-analysis、t0-minute-evidence、t0-range-calibration、top15-cost-breakeven、workspace-inventory。
（均为 2026-09-10/11 的分析/证据类新文档，尚无对应 D-决策条目。）

### 4.2 无实验文档对应的决策（46 / 126 条）

多为工程/流程/数据/工具链决策（无独立实验文档），按时间倒序：

- D-2026-09-02-01、D-2026-09-03-01、D-2026-09-03-02、D-2026-09-03-03、D-2026-09-03-04、D-2026-09-03-05
- D-2026-09-03-06、D-2026-09-03-07、D-2026-09-03-08、D-2026-09-03-09、D-2026-09-04-01、D-2026-09-04-02
- D-2026-09-04-03、D-2026-09-04-05、D-2026-09-04-06、D-2026-09-05-02、D-2026-09-06-05、D-2026-09-06-06
- D-2026-09-07-01、D-2026-09-07-03、D-2026-09-07-04、D-2026-09-07-05、D-2026-09-07-06、D-2026-09-07-07
- D-2026-09-07-08、D-2026-09-07-09、D-2026-09-07-10、D-2026-09-07-11、D-2026-09-07-12、D-2026-09-07-14
- D-2026-09-07-16、D-2026-09-07-17、D-2026-09-07-19、D-2026-09-07-20、D-2026-09-08-03、D-2026-09-08-04
- D-2026-09-08-05、D-2026-09-08-06、D-2026-09-09-12、D-2026-09-09-17、D-2026-09-10-08、D-2026-09-10-10
- D-2026-09-10-24、D-2026-09-10-28、D-2026-09-10-31、D-2026-09-11-02

## 5. 明确的死线（已判死/封存且文档声明不重开）

| 死线 | 依据文档 | 死因/封存条款 |
|---|---|---|
| 事件家族（事件型，round-20260909） | event-family-round1-20260910 | 四构造无一过晋级线；本轮FAIL封存、不追加参数搜索；重开须按家族代表制另行预登记；③事件型封存不重开（引擎预登记） |
| 残差均值回归（MR，round-20260909） | mr-statarb-round1-20260909 | 阶段C CI下界<0；封顶探索级、封存不追加调参；MR/事件家族结论不重开（引擎预登记）；2024起留出窗曾一次性观察（污染披露冻结） |
| P4 价量短线选股（48格） | p4-revised-selection-conclusion | 48格B2全False、净期望全负、完整交集为空；原48格如实封存：F2不反向重选、C1/C2不追认、不扩大网格、不打开2024+ |
| 低波动5→10会话延期 | p4-lowvol-h10-conclusion-20260909 | 双事前继续条件均失败；按预登记终止，不扫描其他周期/止损/因子；无新经济依据暂停同方向 |
| V3 每日/加快趋势退出 | v3-daily-exit-conclusion-20260909 | 年化10.19%→1.99%、回撤恶化；按预登记终止；v3-repair预登记明文：该方向已判死、本轮不重开 |
| V3 修复轮 A/B 臂 | v3-repair-artifact-review-pack-20260909 | ABC=FAIL复算落锤；按预登记FAIL封存不追加参数搜索；C单臂有效属事后观察须另行预登记（已另立arm-c轮，判不确定） |
| PV2 日内反转 / PV5 高换手x反转（精测资格） | family-screening-review-pack-20260910 | 终裁：PV2不满足冻结方向条款（强负向探索发现）、PV5非预登记构造（事后发现）；均无正式精测资格 |
| 周内入场三规则 / 周内标签模型 | weekly-entry-research、weekly-trade-research | 均未达标且冻结选出者样本外转负；不事后升级；目标未达成 |
| 日线价量因子当盈利引擎（产品层） | monthly-etf-t0-plan-20260909 | P3/P4证据：真实成本结构下毛收益不覆盖成本；产品主线改为月频ETF+做T，价量短线研发暂停，恢复须用户授权并重新预登记 |
| 做T 对称档位日内往返（分钟证据口径） | t0-minute-evidence-20260911 | 六组合年度净增益中位全非正（无增益结论）；本轮冻结规则上不得继续调参；增益导向后续须重新预登记 |
| TimesFM / Kronos 基座模型接入 | docs/decisions.md D-2026-09-03-08/09、D-2026-09-04-01 | 预注册主方案失败、消融否决接入；Kronos用户决定终止；动量因子保留（仅决策记录，无独立实验文档） |
| token-router（Hermes工具链，非交易） | docs/decisions.md D-2026-09-06-06 | A/B降幅0.0%未过≥50%门槛，DO_NOT_ENABLE（仅决策记录） |
| P4 R2 ETF混合池 / 仓位分级 | p4-r2-etf-mixed-pool-preregistration-draft-20260909、position-sizing-plan-20260909 | 前者搁置（产品主线变更）、后者作废（用户改选改规则路线）；恢复均须用户授权 |

---

*生成：EX1 实验结构化索引代理，2026-09-11。只读扫描 docs/experiments、docs/plans、docs/decisions.md 与 artifacts/ 一级目录；除本文件与 experiments.jsonl 外零写入。verdict/key_metrics 均抄自文档原文，未做推断或计算；审核送审包的后续裁决取自 docs/decisions.md 并在 reason 字段标注。*
