# 独立审阅报告：C3（独立成交核验与公共策略衔接）

- 审阅对象 run：`20260922T035220-trust-c3-c8af13`
- 审阅者身份：主对话会话（ZCode / GLM-5.3），与实施者子代理不同会话；同时担任本轮编排者。注：上一个实施会话中途连接中断，由接续会话完成；中断留下的半成品 matcher 由接续者接管重写，接管审查发现已在其报告中如实披露。
- 审阅时间（本机）：2026-09-22 03:55—04:15
- 绑定身份：代码 HEAD `ae226d9` + 工作树新增（`src/quant/research/reference_matcher.py`、`reference_matcher_reconcile.py`、`c3_semantic_chain.py`、`tests/test_reference_matcher.py`）；证据目录 27 项哈希登记。

## 审阅范围与未覆盖范围

**范围**：C3 全部 8 项门；按主计划 16.2 完成 C3 类最低独立动作（亲跑一个严格边界、一个 K=3、一个撤单/重挂反证）。**未覆盖**：未逐行复核 5,334 行 order_reconciliation（以汇总一致性 + 分层抽样核对代替）；闭环对照与语义链测试以独立重跑整套（22+2 项）代替逐个亲跑；ETF 腿、创业板、科创板、北交所不在本轮主线范围（合同快照 universe_permission）。

## 独立动作（实际执行）

| # | 动作 | 方法 | 结果 |
|---|---|---|---|
| R1 | 检查器 | `check_delivery.py --report .../stage_report.json --root .` | `EVIDENCE_FILES_OK`；27 项证据；junit 22/0/0 与 2/0/0；0 错误 |
| R2 | 测试独立重跑 | `.venv/Scripts/python.exe -m pytest tests/test_reference_matcher.py` | **22 passed in 0.15s**（reviewer_rerun_matcher.xml） |
| R3 | **亲测①严格穿透边界** | 直接驱动 `ReferenceMatcher.judge_session`：买限价 10.00，(a) 半日 low==10.00 (b) low=9.99 | (a) 不成交、reason=`never_crossed`；(b) 成交且 price=**10.00**（不取更优 9.99）。与冻结合同逐字一致 |
| R4 | **亲测②K=3 兜底与 profit 无兜底** | `pytest -k "tvb10a or tvb11" -v` 单独运行 | 3 个半日未成交→第 4 许可半日市价兜底 PASSED；profit 类无兜底 PASSED；并读测试体确认停牌冻结/跌停顺延有独立用例（tvb10b/10c） |
| R5 | **亲测③撤销/过期不复活** | `pytest -k tvb13 -v` + 读测试体 | 过期单（expires_at<live 半日）经延迟 wrapper 仍不成交、note="past expires_at"；同 intent 同半日双单只认决策点更晚者，旧单 `replaced`。PASSED |
| R6 | C-05 关闭核对 | 解析 intent_to_order_trace.csv 全 102 行 | 63 not_issued + 39 `cap_is_issuance_threshold__limit_is_decision_anchor`；签发 39 单 **limit==anchor 39/39、limit==cap 0/39**；每行带 trigger_cap_1p01 与 decision_anchor 两值及 provider/engine 双侧规则引用——C-05 以真实数据+代码行互证关闭 |
| R7 | 开环对账一致性核对 | 解析 order_reconciliation.csv 5,334 行 | `core_fields_match` **5,334/5,334 True**（含成交与否/日期/半日/股数/价格/原因/末状态）；fill 字段 95 行 False 全部为 C2 已裁定的 ≤0.01 元费用舍入位置差（价格差 0）；1,386 行空白=未成交单无成交字段可比（如实留空非填假值） |
| R8 | 11:30 不变性真实链核对 | eleven_thirty_invariance.csv | A1/A2（11:30 provider 与 engine 输出在午后/收盘扰动下逐位不变）+ B/C **两个正向对照**（15:00 输出变化、改上午则 11:30 变化）+ D（前日决策三变体一致）全部 PASS——不变性不是函数不看行情的假阳性 |
| R9 | 语义链产物核对 | seat/risk/clip 三表 + 分钟对照 | seat_lifecycle 103 行（63 满席/39 签发守恒）、risk_state_trace 19 行+手算对照 9/9、clip_exit_trace 60 行、minute_vs_halfday 抽样 1,030 笔（方向性误判 0、保守少判为主） |

## 逐门裁定

| 门 | 裁定 | 依据 |
|---|---|---|
| C3-01 独立 matcher 未调用原撮合函数 | **PASS** | matcher_independence.md + 我方 grep 复核（无 quant.backtest/portfolio import） |
| C3-02 实际限价/数量/生效时间可见 | **PASS** | order_reconciliation 逐单含 limit/shares/live 半日；"只有 target_weight 无解算价格"的输入在 trace 中以 sizing_note 登记 |
| C3-03 严格穿透与跳空同合同核验 | **PASS** | R3/R7 + TV-B01..B04 合成用例 |
| C3-04 T+1/资金/停牌/涨跌停正确 | **PASS** | TV-B07/B08/B09 用例 + 涨跌停缺口按 C1 数据卡口径（缺行=保守拒绝） |
| C3-05 过期/替换/延迟订单不得复活 | **PASS** | R5（TV-B13）+ TV-B14 部分成交重挂只处理剩余 |
| C3-06 risk/profit 与 K=3 类语义正确 | **PASS** | R4（TV-B10a/b/c、B11、B12 重挂同源计数连续） |
| C3-07 cap 到最终限价链条一致 | **PASS** | R6：C-05 关闭，结论="×1.01 是签发门槛，限价=决策锚价"，与 C0 代码发现、39/39 观测、双侧规则引用三方互证 |
| C3-08 席位/批次/退出/风控闭环无冲突 | **PASS** | R9 + state_transition_tests.xml（22 项，含 TV-B18 唯一优先级、B22 被动漂移、B23 超帽拒绝）；FIFO vs 逐批风险意图错配**已逐 clip 列出**并转 C4 处置（正确做法：错配是合同设计层问题，不属 matcher 缺陷） |

## 核心发现

**事实**：9 臂 5,334 张订单独立重判核心字段 100% 一致；74 次 K=3 兜底全部复现；C-05 以"门槛而非限价"定论；11:30 不变性在真实策略链 5/5（含双向对照）；半日粒度相对分钟是保守少判（1,030 笔抽样 0 反向误判）。接管审查发现的 10 项半成品缺陷与 7 项对账驱动状态重建错误均如实披露且修复后差异归零——这些是我方核对 `core_fields_match` 全 True 后可以采信的。

**推断**：成交判定层在所选 9 臂与冻结合同范围内可复现；"归档 provider 并未把 cap 作为限价交付"的主计划预判（8-C3-A）被证实。

**未知**：交易所逐笔路径是否相同（无订单簿，合同局限已列）；attrib2 run 无订单级产物（转 C4 登记产物缺口）；4 只缺半日 bar 的 symbol 撮合按 no_bar 保守拒绝（数据缺口，非 matcher 行为）。

## 开放问题处置

| 问题 | 裁定 |
|---|---|
| C3-OBS-03/04（FIFO vs 逐批风险原语、席位账同源/25% 帽快照口径） | **转 C4 定向处置清单**（属合同/接口层修订，非撮合缺陷） |
| C3-OBS-05/06/07（INFO：合同局限、attrib2 无订单产物、缺 bar symbol） | 登记；attrib2 产物缺口并入 C4 台账义务 |
| 95 笔费用 0.01 元差 | 沿用 C2 裁定（纯舍入位置表示差），不重复立项 |

## 技术意见

**accepted**（工程验收：C3 通过，8/8 门）。成交真实性与策略-订单语义链在指定范围成立；此 accepted 不延伸为"引擎完全可靠/可实盘"。

**下一阶段确认**：C4 进入条件满足。C4 的定向修复清单输入：①FIFO vs 逐批风险意图错配（C3-OBS-03）；②席位账同源与 25% 帽快照口径（C3-OBS-04）；③C2-OBS-01 停牌日 mark 口径的合同文本修订；④attrib2 运行的产物缺口登记与 affected_runs/trial ledger 补登（C0-MIN-03）；⑤C0-MIN-01 的 713→804 项全量测试日志归档义务；⑥旧错误解释修订（claim_correction_log：首年收益、未参与≠限价未成交等主计划 §9 列举项）。修复纪律按主计划 §9：最小补丁+受影响重放+无关路径控制，禁夹带策略改动。

此意见绑定上述身份；新提交/数据/配置改变后需复核。
