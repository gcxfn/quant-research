# 任务一审核：十年研究基础设施

日期：2026-09-12（最新主审复核2026-09-13）。当前：本轮整改PASS_WITH_LIMITATIONS，T1整体未完成；唯一当前状态以文末交接复核记录为准。

## 目标与独立性

审核数据覆盖和必要实现能否支持目标历史研究。审核者应独立于主要实现者；主对话最终裁决。读取实际diff、日志、输入及工件，不凭执行者自报PASS。不得借审核扩展成全引擎重写或无具体反例的递归审计。

## 检查项目

- 历史股票池包含退市证券，资格使用历史状态；上市年龄、ST/停牌、涨跌停和PIT正确，未用今日名单或行业替代历史。
- 预热与收益窗口分开，无2025以后读取；覆盖矩阵中的“可用”有真实来源证据。
- 分钟按订单依赖检查，身份、网格、复权及数值合法；缺失无静默回退。披露模式扩展有事前规则与负例，阈值不被称为安全保证。
- 公司行为及退市缺价处理诚实；来源不混淆，原始记录未被修正输入覆盖。
- 批次身份、断点续跑及报告状态不漏差异，不把缓存串批当复用。

## 最低验证

检查正常路径、关键负例、一个已知缺陷回归及跨年度小规模端到端。独立重算代表性交易费用、现金、持仓和公司行为，不仅调用被审函数。既有有效证据可复用，不为凑测试数重复运行。

## 裁决与交付

形成审核记录，列出检查命令、实际证据路径、缺陷影响、整改和可放行范围。状态使用PASS、PASS_WITH_LIMITATIONS、CHANGES_REQUIRED、BLOCKED。

数据缺口只阻塞依赖它的工作；受限通过不等于十年覆盖完成。一轮主要审核加具体缺陷复核，证据足够即停止。通过后把可用年份、源规则和批次接口交给任务二、三。

T1与T3立即并行。T3引用既有已验收能力开展训练及账户回测，无须等本审核整体验收；新缺口仅阻塞对应候选的相关阶段。不得以T1尚未完成为由要求T3停止全部计算；T3自身登记审核仍须先完成。

## 阶段放行与具体反例

- A检查盘点和日期读取边界；B检查能力及小样例，允许T2按需拉取订单数据；C检查实际依赖覆盖和剩余限制。禁止把“完整分钟名单依赖正式运行”变成双方互等。
- 必查旧24个月/三账户硬编码已被新入口正确隔离；旧迁移入口默认不变，新入口两账户/120月，缺月必须显式失败而不是压缩日历。
- 构造含2025记录的混合输入、未来修订财务记录及超窗标签负例，验证未进入研究计算。验证跨年费用制度、复权单位和停牌/退市案例；只测与本次变更有关的已有规则。
- 核查续跑在身份改变时拒绝混用，压力新增证券日仍经过校验；覆盖分母清楚，不能只报告“已下载记录全部合法”。
- 报价及分钟来源小幅差异可披露，不要求逐股第二来源一致；结构错误不能因降低门槛放行。

## 审核记录接口

在执行批次内产出review-infrastructure.md，写审核者、时间、代码/配置/输入摘要、检查命令和结果、缺陷及严重度、可放行阶段、限制、下一步。严重度分阻断正确性/影响结论/一般文档问题；只有前两类阻断其影响的依赖。执行者修复后仅复核关联项，审核者不自行改变被审算法再自签。

| 阶段 | 审核状态 | 证据路径/审核者 | 下一步 |
|---|---|---|---|
| A | PASS | `artifacts/ten-year-infrastructure-20260912-1/review-infrastructure.md`；审核者：独立子代理（GLM-5.3-Flash，非实现者），主对话终裁采纳。分母独立重算逐年精确相等（2015: 665,917/665,917；2024: 1,236,574/1,236,574）；日历合并2014-01-02起零周末零重叠；退市股600005止于退市日 | 移交覆盖矩阵给T2/T3 |
| B | PASS_WITH_LIMITATIONS | 同上记录。17项定向测试独立复跑通过；e2e四股批24+24月逐位正确、252会话年龄门精确（600958首观测2016-03-31）；2025隔离/缺月不压缩/续跑身份负例属实；旧入口+partition零diff；费用边界独立重算一致。限制：分钟与2015–2017分红按订单依赖未补（G2/G3）、过户费历史变差未建模（G4）；两文档缺陷D-1/D-2已更正并复核关闭 | T2正式十年运行前按记录§限制执行；订单依赖出现走T1-C |
| C | PARTIAL（未收口） | 同上记录；G1（daily_basic 2015–2018）只阻塞依赖估值字段的T3候选 | T2/T3订单名单出现后补数据，缺口结论后收口T1 |


### 2026-09-13 最新主审记录

最终审核状态：**CHANGES_REQUIRED**。用户明确要求以正确实施任务为准，不使用ponytail。主对话独立核对当前代码、数据及进程，未修改被审算法。

| 阶段 | 当前审核状态 | 证据与影响 | 下一步 |
|---|---|---|---|
| A | CHANGES_REQUIRED | D-8覆盖率分母混用，原日线盘点事实不撤销 | 更正证券日/交易日文件覆盖披露 |
| B | CHANGES_REQUIRED | D-5未绑定实际行情输入；D-6首股失败后不能恢复 | 输入变更负例、零进度/尾部恢复复核 |
| C | CHANGES_REQUIRED | D-7持续空日线仍成功并永久跳过；真实回补975/732文件核实；分钟、公司行为消费、G4r仍未收口 | 修获取质量状态，继续按依赖补齐 |

完整记录及代码行位置：`artifacts/ten-year-infrastructure-20260912-1/review-current-20260913.md`；完整SHA256与逐文件对账：同目录`review-current-20260913-evidence.json`。27项测试及12个子测试通过，不覆盖全部上述缺陷；D-6/D-7另以临时目录无网络实测复现。整改后只复核关联项。旧“全PASS/无遗留整改”不覆盖当前身份；T3可继续不依赖缺陷的已验收路径。统计UNKNOWN、晋级BLOCK及2025以后冻结不变。


### 2026-09-13 修复后再次主审（当前状态入口）

**审核结论：CHANGES_REQUIRED；本条覆盖此前追加代理“全部PASS”和旧主审当前状态。** 审核者：主对话，非实现者；未修改被审算法，按用户要求不使用ponytail。

| 阶段 | 执行状态 | 审核状态 | 本次证据及下一步 |
|---|---|---|---|
| T1-A | CHANGES_REQUIRED | CHANGES_REQUIRED | D-8已拆文件/证券日行，20项除法核算一致，但异集合总数净差不能当缺失数；按键对账或保留UNKNOWN |
| T1-B | CHANGES_REQUIRED | CHANGES_REQUIRED | D-5原始数据摘要修复受限通过；D-6每100股保存却只允许落后1条；新增D-9相同名单换序恢复出现漏股/重复股且报告完成；修恢复协议与名单身份 |
| T1-C | CHANGES_REQUIRED | CHANGES_REQUIRED | D-7空/None失败处理已验证，但末行截断及错日期同条数文件仍被接受；分红循环修复通过；十年账户样例、G4r、分钟实际依赖仍待补齐 |

证据：`artifacts/ten-year-infrastructure-20260912-1/review-followup-20260913.md`；同目录`review-followup-20260913-evidence.json`绑定完整SHA256，`reproduce-followup-20260913.py`提供隔离复现。亲跑6个关联测试文件：44 passed、16 subtests passed（116.33秒），但测试未覆盖的三类反例已实测。已核数据和不受影响能力可继续，不要求T3整体暂停；仅复核关联整改，不改2025以后/生产冻结，不自动切换日线成交。


### 2026-09-13 交接材料独立主审复核（唯一当前状态）

本轮整改裁决 **PASS_WITH_LIMITATIONS**，覆盖此前“待复核/CHANGES_REQUIRED”的当前状态，旧历史记录保留。审核者：本主对话，非实现者；不使用ponytail，未修改被审算法。证据：`artifacts/ten-year-infrastructure-20260912-1/review-handover-20260913.md`，完整摘要/测试及2016独立交集见同目录`review-handover-20260913-evidence.json`、`review-handover-2016-keycheck.json`。

| 阶段 | 执行状态 | 审核状态 | 范围与下一步 |
|---|---|---|---|
| T1-A | DONE | PASS_WITH_LIMITATIONS | D-8键交集口径通过；2016独立重算missing=1（sh.600656/2016-05-12），其余年份仅复核工件算术并保留已披露缺失 |
| T1-B | WAITING_REVIEW | PASS_WITH_LIMITATIONS | D-6/D-9原恢复反例通过；当前信号能力可用，能力交付仍缺任务书要求的账户现金/费用/持仓/公司行为独立核算，不能写整体DONE |
| T1-C | RUNNING | PASS_WITH_LIMITATIONS | 975+732真实文件摘要全匹配；D-7原两反例已修；空分红分支错误摘要仍接受，未来依赖该分支须修复或独立摘要门禁；G4r/早年账户消费/实际分钟仍待补齐 |

关联测试47 passed、4 subtests passed（165.47秒）；换序续跑两股各一次，合法检查点落后恢复，截断/错日期文件拒绝。当前真实199个空分红文件已由审核独立验真，不因获取器局部限制否定数据。T1整体尚未完成；T2/T3不受影响路径继续。2025以后/生产冻结、统计UNKNOWN、晋级BLOCK不变；不自动授权日线成交替代分钟。

### 2026-09-13 唯一限制项（空分红摘要分支）整改后限定复核

被审身份变化：`experiments/ten_year_field_backfill_20260913.py` SHA256 由 `722e876f…` 变为 `26dae5656ca37ff9b332b8e5971851a20c660a20333e797e1c2c51a2870baac3`；`tests/test_ten_year_infrastructure.py` 由 `74857b2f…` 变为 `a07f8184b1537c44ca4da69b725eb36c43f30671eb32bb5f313871f37074685a`（新增空文件错误摘要负例，34→35 项）。其余 §2.1 12 项摘要未变。

限定复核结论（仅针对该项，不重开无关审核，不改2025以后/生产冻结）：

| 项 | 结论 | 证据 |
|---|---|---|
| 空文件分支摘要前置 | 关闭 | 源码中 `sha256(data)` 比较置于 `if not data` 之前；空文件须满足 `sha256 == sha256(b'')` 且 `rows==0` 且 `dataset=='dividend'` |
| 空文件错误摘要负例 | 通过 | `ChunkSatisfiedTest::test_dividend_empty_file_with_wrong_sha_rejected`（`f`*64 拒绝；正确 sha 但 rows=3 拒绝） |
| 真实数据不被误拒 | 通过 | 离线 `--dataset all` → daily_basic/dividend 均 `pending=0`，1,707 条目零拒绝（199 空分红文件摘要确为 `sha256(b'')`） |
| 关联面回归 | 通过 | 四文件合集 48 passed、4 subtests passed（181.49s）；其子集 13 passed |

仍未交付、且本复核不覆盖：T1-B 账户现金/费用/持仓/公司行为独立核算；T1-C 的 G4r（2015 上半年沪市面值计费过户费）、2015–2017 账户级分红消费、实际订单分钟依赖与 `r0_pilot_market_inputs.main` 早年窗口。T1-A/T1-B/T1-C 执行状态不变（DONE / WAITING_REVIEW / RUNNING），T1整体未完成。整改实施者为执行侧主对话，本条为限定复核记录，不构成对全获取器状态的再验收。

### 2026-09-13 账户能力补交复核（面额制过户费 / 早期分红消费 / 2015-2016 账户样例）

**裁决：PASS_WITH_LIMITATIONS（仅限本轮账户能力；T1 整体未完成）。** 审核者：主对话（非本轮唯一实现者，终裁）+ 两个只读独立子代理 `VerifyFaceValueFee`、`VerifyEarlyDividendConsumption`；未联网、未下载、未改被审代码。记录：`artifacts/ten-year-infrastructure-20260912-1/review-account-20260913.md`、同名 `-evidence.json`。

被审身份（完整 SHA256 见 evidence）：`ten_year_research.py` b370d915…、`ten_year_account_20260913.py` 675c15da…、`ten_year_account_audit_20260913.py` 4f9dd658…、`r0_pilot_market_inputs_20260912.py` 789138fd…、`r0_pilot_corporate_actions_20260912.py` d11e1224…、`quant/execution.py` 8a90ea3c…、`fixed_capital_portfolio.py` a1b58e9c…、`pilot_costs.py` d63092f6…、`r0_mechanism_cost_pilot_20260912.py` d9942e18…、账户样例批 manifest 2db59c8a…（源文件变更后重跑，account.json 摘要未变）、`REV_vola_11/account.json` 293f00fc…、`independent-review.json` 8a52ac02…。

| 检查项 | 结论 | 证据 |
|---|---|---|
| 面额制过户费能力（G4r） | 关闭 | 独立 Decimal 实现复算两身份 36 笔成交费用分量零不匹配；7 笔沪市 9,500 股按 `shares*0.0003` 计费共 2.85 元；`ten_year_fee_terms` 在该区间给 `transfer_bps=0.0 + transfer_per_share=0.0003*face_value` |
| 子代理发现的缺陷 | 已修并复现 | `Replay._annotate_costs` 生成门漏 `transfer_per_share`（单用该键时费用已扣但无 `fee_breakdown`、账本 `commission` 混入过户费）；修复后与显式 `transfer_bps=0.0` 结果一致；回归 `test_pilot_cost_ledger.py::test_per_share_transfer_fee_alone_reaches_fills_and_breakdown`；样例 `account.json` 摘要未变 |
| 早期分红账户级消费 | PASS | r2 中 2015-2016 四码实施事件 8 条、r3 同区间 0 条；账本 6 条分红逐事件通过来源/持仓/登记日股数×每股现金校验，合计 2,408.42；无零持仓或伪造入账；43,566 行 chunk 扫描确认 ex_date 与文件名一致 |
| 账户独立重算 | PASS | 独立模块（不调用账本与费用引擎）重建现金/费用/持仓/可卖/净值：488 日、两身份，最大现金误差 0、最大净值误差 0、`invalid_nav_days=0`、`data-issues.json` 空；篡改账本负例抛错 |
| 关联面回归 | 通过 | 定向 41 passed；八文件合集 70 passed + 4 subtests（226.09s，含面额制单独表达回归、TRAIN 默认口径回归、十年费用交叉核算） |
| 共享费用核算复算十年账户 | 通过 | 复核发现能力未接共享核算（`train_fee_terms` 限 2020-2022、`fill_costs` 只认 `transfer_bps`）→ 已加 `fill_costs(terms=)`/`account_metrics(fee_terms=)`；样例两身份复算费用分量=fees_paid、面额制计入 transfer、yearly={2015,2016}；范围仅费用/现金/收益复算，明细持仓/净值仍以 `ten_year_account_audit_20260913.py` 为准，TRAIN 专用入口保持冻结 |
| 工件数值稳定性 | 通过 | `coverage.csv`/`issues.json` 仅文本更新，逐行 diff 确认数值未变 |

可放行：十年窗口内的日线执行账户能力、跨年法定费率（含面额制）、早期分红/送转账户级消费、账户级独立重算方法。
未放行：十年全量（2015-2024）账户；2015-2019 执行语义（T2 登记项，样例按日线执行）；2020+ 分钟订单依赖；2025 以后与生产冻结、统计 UNKNOWN、晋级 BLOCK 不变。
本轮未重开无关审核项；`coverage.csv`/`issues.json` 旧摘要裁决只覆盖旧身份。


### 2026-09-13 空分红摘要修复主审终核（当前状态）

**修复审核PASS：D-7最后一项空分红摘要缺口关闭，本轮列出的代码整改项均已关闭。** 主审亲测6项ChunkSatisfied测试通过；独立原例错误摘要/错误行数拒绝、合法空日通过；199真实空日零拒绝。新代码/测试摘要与提交复核声明一致。证据：`artifacts/ten-year-infrastructure-20260912-1/review-handover-20260913.md`末尾及`review-empty-dividend-fix-20260913.json`。

T1整体仍未完成，阶段状态维持A DONE、B WAITING_REVIEW、C RUNNING；整体阶段审核PASS_WITH_LIMITATIONS，剩余为账户独立核算、G4r、早年账户消费及实际分钟依赖尚未交付，已不包含空分红摘要限制。无需重复修已关闭缺陷；后续提交未交付项证据再验收。T2/T3已验收路径可继续，冻结不变。

### 2026-09-13 账户能力复核后当前状态（唯一当前状态入口）

**当前审核状态：T1-A PASS_WITH_LIMITATIONS；T1-B PASS_WITH_LIMITATIONS；T1-C PASS_WITH_LIMITATIONS（限账户能力本轮）。T1 整体未完成。**

本轮已关闭：G4r 面额制过户费（能力+实际计费+独立复算）、2015-2016 分红账户级消费、账户现金/费用/持仓/公司行为样例与独立重算。子代理发现的 `Replay._annotate_costs` 生成门漏 `transfer_per_share` 已修复并补回归。

仍未放行：十年全量账户、2015-2019 执行语义（T2 登记项）、2020+ 分钟订单依赖；2025 以后与生产冻结、统计 UNKNOWN、晋级 BLOCK 不变。证据：`review-account-20260913.md` + `-evidence.json`。

### 2026-09-13 最终当前状态（覆盖以上全部“当前状态”段落）

账户能力补交与共享费用核算打通后重新裁决：**T1-A PASS_WITH_LIMITATIONS / T1-B PASS_WITH_LIMITATIONS / T1-C PASS_WITH_LIMITATIONS（限本轮交付面）**，T1 整体仍未完成。

- 已关闭并复核：空分红摘要分支（§10）；G4r 面额制过户费（能力 + 实际计费 + 独立复算，§11.1/§11.6）；2015-2016 分红账户级消费（§11.6）；账户现金/费用/持仓/公司行为样例与独立重算（§11.3）；共享费用核算可复算十年账户（§11.7）。
- 仍未交付：十年全量（2015-2024）账户；2015-2019 执行语义（T2 登记项）；2020+ 分钟订单依赖。
- 不变：2025 以后与生产发布冻结、统计 UNKNOWN、晋级 BLOCK；不自动授权日线成交替代分钟。
- 当前身份与命令见 `docs/handover-ten-year-t1-20260913.md` §2.1/§5/§11；复核记录 `artifacts/ten-year-infrastructure-20260912-1/review-account-20260913.md`（+`-evidence.json`）。

### 2026-09-13 性能包 -5 主对话独立审核（覆盖该优化轨道此前当前状态）

执行状态：CHANGES_REQUIRED；整体交付/切换准备审核：CHANGES_REQUIRED；已测CPU优化、F1/F2局部修复和F3：PASS_WITH_LIMITATIONS。其他研究阶段状态不变，整体未完成，全量保持未启动。

审核记录：[性能包-5独立审核](../experiments/factor-engine-perf-independent-review-20260913.md)。受审源码2c3a31f3、59件摘要一致；亲跑输入身份40/40、比较器11/11、检查点29/29、B1对抗300/300。独立证据在 artifacts/factor-engine-performance-review-20260913-1/，命令见审核报告末尾。

下一步仅修R1–R5：worker消费事前冻结代码/数据契约并核收尾；证据绑定运行时摘要及补齐依赖；纠正GPU计时口径；回退显式--backend pure；补小规模新进程CLI并更正交付范围。GPU局部原型已做、当前不采用，旧“未做GPU原型”不再作为当前事实。-12只登记身份，未获本审核切换放行；不修改冻结旧包，不启动全量或L1/L2。


### 2026-09-13 Codex续做：身份整改与T2信号交付（当前状态）

T1-A DONE，T1-B WAITING_REVIEW，T1-C RUNNING；整体未完成。公共性能整改所有者：当前主对话，代码落在 `D:/AI/workspace/factor-engine-perf-isolated-20260913/`，不覆盖主仓较新的T1恢复/费用实现。新证据批 `artifacts/ten-year-infrastructure-20260912-2/` 绑定隔离源完整SHA：D1 mixed/canonical/repeat/verify在12根20275文件上通过，两个回归测试通过；旧清单摘要口径变更，历史工件不改写。

T2十年信号已交付：5552只、两策略各120月，2023–2024同输入信号回归及实际重叠窗口选股/权重/执行日均一致，见 `artifacts/ten-year-fixed-strategies-20260912-1/`。四账户尚未启动。用户明确将提供分钟数据，2015–2019执行缺口保持BLOCKED；其余实际订单/公司行为依赖待收到数据后处理。不授权日线替代。CPU -6与新快照正在收口，T3全量未启动，2025+/生产冻结。


### 2026-09-13 CPU整改交付终核（唯一当前状态）

CPU性能整改执行状态 DONE，审核 PASS_WITH_LIMITATIONS（限定隔离实现、交付包与新快照接线；不代表T1/T2整体完成）。交付 `artifacts/factor-engine-performance-20260913-6/`：101件摘要独立重算0差异、25件证据内容来源通过、5份diff应用后源码一致、A侧5文件字节复核一致、missing=[]。最终复核 `artifacts/ten-year-infrastructure-20260912-2/performance-package-review.json`，包manifest SHA256 `6b33b880b048e65c6ecb7725af9d3f7c8466909661cf63b8fdb0bdeb8c9ea810`。

D1规范化修复实测12根20275文件mixed/canonical/repeat/verify通过；历史清单口径不再沿用且旧工件不改写。D2真实B测量提交12c5c0d54d3b2b1079dcb8676c5cb134f5088c76，机械diff证明测量路径未变，A/B两轮PASS_EXACT、0差异。D3新生成器随包交付；D4双侧SHA与A字节齐全；D5临时副本变异、mtime回拨仍拒绝且复原SHA相等、真实核心源码未动；D6夹具禁止正式gate，另真实1430清单新进程接线2/2且在装载前停止。

最终测试：身份40/40、检查点31/31、同进程CLI9/9（40股/144项）、新进程CLI7/7（40股/8项）、冻结负例8/8、打包负例6/6；L0-only20项逐位等价、跨片6文件及run_meta一致。CPU原A/B样本装载55.190/55.934s→41.134/41.122s（1.34–1.36倍），求值9.083/9.109s→8.757/8.705s（1.037–1.046倍），不是全池wall测量。GPU保留原型、不采用，未外推全池。

用户授权隔离提交已执行：运行源码43dba5b6ffa1500322471bb97fe7c22c05734420，打包器字段修复ac669ef（仅交付工具）；新快照 `D:/AI/workspace/t3-snapshot-20260913-3/` 保持43dba5b6，55受审文件干净校验通过。新批 `artifacts/new-factor-research-20260912-13/` 的启动/收尾原始数据核验PASS，20片/1430分母不变；未运行全量。模块命令需 `PYTHONPATH=<快照>/experiments`，pure回退显式 `--backend pure` 且新输出根。主仓性能源码未覆盖、主仓未提交，不能整仓覆盖较新的T1修复。

T1整体仍未完成：A DONE、B WAITING_REVIEW、C RUNNING；T2-A DONE、B BLOCKED、C PENDING。十年信号5552只、两策略各120月完成并审核，旧窗口信号回归与重叠选股/权重/日期一致；用户将提供分钟数据，四账户未启动，2015–2019缺口保持，不用日线替代。统计UNKNOWN、晋级BLOCK、2025+/生产冻结。下一步只接收分钟数据并推进实际订单依赖及四账户；T3全量取消状态未改变。

保留本轮失败记录：首次CLI批检查点旧正式gate断言与stdout格式失败，修后31/31；首次打包缺GNU工具已改difflib/git apply；正式打包旧mtime汇总字段KeyError已在ac669ef修复。预检临时目录清理被自动策略拒绝（blocked by policy），未再删除；失败staging不是交付，只有带manifest且经上述终核的-6是正式包。

### 2026-09-13 1分钟接入与实际四路径终核（唯一当前状态）

执行：T1-A DONE、T1-B DONE（限定已验基础能力）、T1-C BLOCKED；T1整体未完成。T2-A DONE、T2-B BLOCKED、T2-C PENDING；CPU隔离性能整改DONE不变。审核：信号/分钟能力/代码衔接PASS_WITH_LIMITATIONS；完整十年账户BLOCKED。主对话以实际diff、测试、独立文件摘要及原账本复算裁决。

详细交付和命令：`docs/experiments/user-minute-ingestion-20260913.md`。十年ZIP全部迁入工作区，SHA及2431个日文件CRC/日历通过；源ZIP已按授权删除，原1分钟ZIP保留。发行人代码有效期修复的新信号批 `artifacts/ten-year-fixed-strategies-20260913-2/`：两策略各120月；REV11两个月、组合七个月选股改变，其余单股证据一致，2023–2024选股不变。旧错误信号批仅留档，不再用于新账户。

最终能力审核 `artifacts/user-minute-1m-review-20260913-1/review-v2.json` 绑定28个源码。最终关联56测试通过；生命周期/十年能力50测试通过（范围重叠，不相加）。原2023–2024两个账户离线同输入回归均PASS_EXACT：各484日、292/297成交，全账本逐项一致。账户中的代码变更保持股数/限售可卖限制/现金，跨日目标转新码；不重置真实IPO年龄、不产生交易费用。

实际四路径已运行两批（第二批是技术补漏重跑，不新增假设），当前批 `artifacts/ten-year-fixed-strategies-minute-accounts-20260913-2/`：全在2015-07-01 BLOCKED，28源码及副本、1554输入摘要独立复核一致，未生成有效十年account.json。第一批发现该日11只实际订单深市证券14:53后零量/重复价格并缺日总量；追加末端>=5分钟零量且日量缺口超过1股与1ppm即阻断，不能借research_disclose小差异线放行。真实提前收市/停牌总量守恒不受此门禁阻断。第二批首阻塞REV11为000681、组合为000032，见blocking-review.json与每路径minute-source-failure.json。

具体外部依赖：`artifacts/user-minute-1m-review-20260913-1/data-repair-request.csv` 共22证券日，11当前实际订单阻塞、11后续选股预检；给卖家的中文说明同目录。2015-07-01实际问题名单11只，另300114在2016-05-03/2022-05-05缺完整分钟。大日线差异需核正确来源，不能一律认定分钟错误。用户确认闲鱼来源，原供应商未知。等待真实补数/来源核验；不得日线反填分钟、拼接不同资金账户或宣称上半年已独立验收。

下一步：收到修订分钟后另建原始批并重绑审核身份，从同一20万元初始现金重跑两策略主/压力，随后完成账户独立核算与T2-C归因；当前清单非未来全部订单的穷尽。统计UNKNOWN、晋级BLOCK、2025+行情收益/生产冻结。主仓未提交；CPU旧快照不含本次金融身份修复，未来切换须另绑，不覆盖旧包或启动T3全量。


### 2026-09-13 T1/T2/CPU完成情况独立复核（唯一当前审核状态）

本次裁决：T1整体未完成，公共公司行为消费与分钟最低价例外CHANGES_REQUIRED。T1-A已审事实和不受影响能力保留；CPU第6包限定交付通过不等于主仓集成或T1完成。

审核者：当前主对话。实际证据、分级问题与最小整改见[本次审核报告](../../artifacts/t1-t2-cpu-review-20260913-1/review.md)及同目录evidence.json/probes.py。亲跑70项关联测试通过，28源码和1554输入摘要无差异，四账本逐日权益误差最大2.91e-11，CPU包101件摘要无差异；两个新分钟错误放行反例实测成立。未修改算法、未重跑账户、未启动T3、未提交；统计UNKNOWN、晋级BLOCK、2025+/生产冻结不变。


### 2026-09-14 最终验收裁决（唯一当前状态，覆盖此前待审核）

T1整体执行/审核：BLOCKED，未完成。T1-A沿用DONE / PASS_WITH_LIMITATIONS；T1-B本轮已测公共修复DONE（限定）/ PASS_WITH_LIMITATIONS；T1-C执行/审核BLOCKED。审核器身份/路径门禁、603613/603801移植、最低价例外原反例关闭；但002442/2016-03-01真实分钟冲突及实际持仓未核权益未闭合。002166在REV压力存在股份权益依赖，002776在历史组合存在股份权益依赖，不能只凭nav_valid放行。范围文档还需撤销G4r/早年执行语义旧待办表述及过期分钟闭合声明，不要求未来宏观/行业全集齐备。CPU/GPU隔离P0及后续轨道保持自身进度，不被本条改写。

审核者：当前主对话；正式报告 [最终验收](../../artifacts/t1-t2-remediation-review-20260914-1/review.md)，同目录 evidence.json、provider-probes.json 与 attribution/。亲跑42测试通过；第14批四账本独立核现金/持仓/可卖/逐笔费用通过（最大误差2.33e-10），第15批REV两条与其逐字节一致；两批各1554输入身份一致。真实Provider复现002442两情景BLOCK、603026两情景ACCEPT；阶段IC独立复算一致、474行历史归因无数值差异。未修改算法、未重跑策略账户、未提交；统计UNKNOWN、晋级BLOCK、2025+/生产冻结，T3不自动启动。


### 2026-09-14 继续修复后的最终裁决（唯一当前状态）

当前主对话执行并审核；报告 [修复与验收](../../artifacts/t1-t2-data-resolution-20260914-1/review.md)。最新账户批 `artifacts/ten-year-fixed-strategies-minute-accounts-20260914-4/`，新输入 `artifacts/ten-year-fixed-strategies-market-inputs-20260914-1/`，能力身份 `artifacts/t1-t2-data-resolution-20260914-1/minute-capability-review-2.json`。六项公司行为公告与除权参考价核对完成；零量占位污染OHLC聚合、分钟拆单佣金使opening_cash_only超预算两个实际缺陷修复并验收。175测试/22子检查通过。REV主/压力各2431天完整，未核事件依赖0，独立现金/持仓/可卖量/逐笔费用/权益核算通过（最大误差1.1642e-10元），路径DONE / PASS_WITH_LIMITATIONS。最新权益280222.30/283045.20元，税前分红研究口径累计40.11%/41.52%，非个人红利税后收益。

组合两条仍在002442/2016-03-01日低10.87、分钟低10.99处BLOCKED，无完整account.json。原日全部成交复现后，48个假设低价落点中主19、压力15改变成交；仅作敏感性反例，不是真实补数或误差上界。同花顺同为10.87记为用户提供佐证。需要真实分钟/逐笔或可核实统计口径解释，供应方说明已落盘，未发送。不得放宽例外或伪造最低价。

T1整体/T1-C继续BLOCKED；T1-A保留原限定通过，T1-B本轮公共修复DONE / PASS_WITH_LIMITATIONS。T2-A保持原通过，T2-B两REV限定通过/两组合BLOCKED，整体BLOCKED；T2-C旧报告勘误完成、诊断限定通过保留，新完整组合报告仍BLOCKED / CHANGES_REQUIRED。原20260914-1依赖中断、-2聚合缺陷、-3现金预算失败均留档，不作为PASS。不新增假设、不提交、不改CPU/GPU及T3调度；统计UNKNOWN、晋级BLOCK、2025+/生产冻结。当前修复文件占用结束，后续公共更改须新登记。


### 2026-09-14 002442截图修订后的实际运行裁决（唯一当前状态）

2026-09-14 批量补查补记：按用户“一口气要查的都发过来”，当前主对话只读扫描同一冻结信号身份下76份历史/当前请求文件及选股清单，共3619个去重证券日、120个日期，使用最新30项补丁和当前1分钟聚合、成交量等价及缺尾门禁。结果EXACT 2970、停牌跳过10、重点核查6、小差异633。重点为300114/2016-05-03、600452/2016-06-01、300216/2017-02-03、300461/2017-03-01、603026/2019-05-06、300420/2019-09-02；其中既有例外及仅计划依赖不冒充当前账户阻断。002442已修订日仍EXACT。已生成[一次性查询说明与639项完整清单](../../artifacts/minute-bulk-source-check-20260914-1/查询说明与完整清单.md)及同目录bigquant_batch_query.py，按77个日期批量导出BigQuant全天原始1分钟CSV、覆盖/失败记录和ZIP。名单唯一性、扫描对应关系及语法已检查，未在用户BigQuant账户执行，尚无新供应商结果；修复后新增实际订单依赖不在本次覆盖保证内。下一步用户返回ZIP后核对和定点修复；验收裁决仍按下文BLOCKED及既有REV限定通过，不放宽门禁。

当前主对话执行/审核；[本轮报告](../../artifacts/002442-source-resolution-20260914-1/review.md)。用户BigQuant查询截图明确002442/2016-03-01 09:35一分钟低10.87；O/H/C及成交量与原始同分钟一致，成交额差0.46875元保留。新补丁 minute-repairs-20260914-2 仅这一分钟low作有来源修订，旧数据保留，标明用户截图字段修订而非供应商重发原件。重新聚合后全天OHLCV与日线严格一致；两情景真实Provider strict通过，002442具体依赖DONE / PASS_WITH_LIMITATIONS，不靠例外或放宽容差。

最新账户批 artifacts/ten-year-fixed-strategies-minute-accounts-20260914-5/ 从初始20万元重跑。REV主/压力两账户与上一已验批逐字节一致，独立完整现金/持仓/可卖/费用/权益复核通过；组合两条越过002442，改在600452/2016-06-01阻断，均无完整account.json。新差异：日开31.16/分钟开31.48，日收31.64/分钟收31.65，其余日高低量一致；09:30报价零成交量，09:31原始分钟开31.48，不能直接恢复零量开盘来绕过门禁。已保存原始行与待查SQL，尚无该日BigQuant结果。

T1整体/T1-C与T2整体/T2-B继续BLOCKED（已验REV两条限定通过保留），T2-C完整组合报告仍BLOCKED / CHANGES_REQUIRED。原002442待补状态被本条关闭，新阻断明确独立。相关24测试通过，输入/源码/补丁/年包身份及完整REV账本复核在新账户verification.json；scope=PARTIAL_CHECK_NOT_AN_OVERALL_PASS。报告生成器历史固定文案更新，但不生成不完整组合的完整收益报告。无提交、无对外消息，CPU/GPU/T3状态不改；统计UNKNOWN、晋级BLOCK，2025+/生产冻结。报告文件本轮占用结束。


### 2026-09-14 用户批准现有分钟源研究基准（执行中）

用户批准：Tushare日线仍为信号/估值基准，现有一分钟及已验补丁保留原值作为执行研究基准，已知日线差异可登记后继续，不再强制BigQuant佐证；结果DATA_UNCERTAIN_DESCRIPTIVE，须作受影响成交敏感性检查。不是Tushare官方真实性认证。缺/重复分钟、身份/复权错误、非法数值和账本缺陷仍阻断，strict默认保留。

主对话承担T1公共修改所有者：experiments/rev11_dynamic_minute_20260912.py、experiments/ten_year_minute_execution_20260913.py及相关定向测试；T2冻结策略/信号不变。新工件artifacts/minute-source-baseline-20260914-1，新补丁批minute-repairs-20260914-3，新账户批ten-year-fixed-strategies-minute-accounts-20260914-6。先对扫描已知合法差异按具体code/date/分钟摘要/日线值登记接受，未登记差异仍按旧门禁。已修订002442保留截图证据，不恢复已知错误。状态RUNNING / PENDING；最终验收待完整运行与独立核算。


### 2026-09-14 性能第7/8包独立详细审核（覆盖本性能轨道此前当前状态）

审核者：当前审核主对话；对象为隔离实现/快照 `68bbc252fa4ae7a4252c95798e4c6eebc7647cf7`。**性能执行 CHANGES_REQUIRED / 审核 CHANGES_REQUIRED，正式切换 BLOCKED**；不能继续表述为“性能已通过，只剩T1/T2外部条件”。

报告：[独立详细审核与后续优化建议](../../artifacts/factor-engine-performance-review-20260914-1/review.md)。R1：pipeline和worker仍默认retain_rows=True，测得的价格缓存/流式装载未接入；R2：缓存键缺生命周期和预处理身份，真实Timeline合成反例复现5个退市后日期被错误保留；R3：改写缓存数值仍命中、截断NPY抛错；R4：GPU最新确认结果无运行时源码/输入摘要；R5：复跑命令未展开别名/cwd且会覆写旧证据；R6：55份引用中2份摘要过期；R7：reset/关闭缓存后仍持旧bundle强引用，weakref确认。详见报告逐项整改与验收要求。

亲跑基础13测试、缓存负例10、比较器11、B1对抗300、身份40、检查点31均通过；新反例仍成立。开发与快照45文件行尾归一化内容一致。GPU四配置计时独立复算，最佳热点1.921343倍、计算段替换估计1.178980倍，维持不采用GPU；不是完整workflow实测。

按用户要求增加优化建议：先修正确性和入口接线，再评估按片字段装载、广播字段单份存储、缓存生命周期及单bundle复用、内部摘要复用、有限精确子表达式复用；bootstrap索引复用仅低优先级同协议验证。全1430公式/20片仅静态解析，无新增因子计算或假设。证据/脚本在报告同目录。

下一步：实现侧先处理R2/R3/R7，再接R1，补运行身份/新输出命令与最终索引，限定重跑后送审。此次未改算法/原始数据/旧包，未提交或切换，未启动T3。此条只更新性能轨道；T1/T2既有账户裁决、统计UNKNOWN、晋级BLOCK、2025+/生产冻结不变。


### 2026-09-14 用户批准分钟源基准后最终验收（唯一当前状态）

主对话最终裁决：本轮T1对T2实际依赖支持及T2固定四路径研究目标DONE / PASS_WITH_LIMITATIONS；不是全市场分钟覆盖或未来T3依赖放行。详见[本轮验收报告](../../artifacts/minute-source-baseline-20260914-1/review.md)、同目录独立代码审核及manifest。新账户-20260914-6四路径各2431交易日/120月，未核公司行为依赖0、无效净值0；完整身份及独立现金/持仓/可卖/逐笔费用/权益通过，最大误差2.33e-10元。37测试/23子检查通过。T1-A既有盘点限定结论保留、T1-B本轮源基准能力通过、T1-C本批实际支持完成；T2-A冻结信号通过保留、T2-B四路径通过、T2-C新完整报告和归因通过。

REV主/压力期末280222.30/283045.20元（累计40.11%/41.52%，回撤57.86%/57.83%）；组合主/压力241468.97/220823.72元（20.73%/10.41%，回撤49.11%/50.81%）。原始分钟不改，002442截图修订保留；已知5项差异身份登记，新补丁33项，300114缺失未豁免且本批无实际请求。102项单日固定订单敏感性假设保留，不是收益误差界。报告artifacts/ten-year-fixed-strategies-report-20260914-2，归因独立474行差异0，实际CSV排名已核；manifest五股列表反向展示为无rank列表差别。一般元数据问题及未触发缺口见报告，不冒充已修复。

研究结论DATA_UNCERTAIN_DESCRIPTIVE，统计UNKNOWN、晋级BLOCK；税前红利口径、2025+/生产冻结和旧迁移拒绝结论保留。下一步可供后续研究复用，新增具体依赖仍单独校验；无需再等待BigQuant作为本轮前提。共享文件占用释放，无提交。


### 2026-09-14 BigQuant试用权限开通后补充证据

用户通知SDK权限已开通，主对话继续此前639证券日只读查询，77个日期全部返回，638非空/1空（300114/2016-05-03），153758行，CSV约10.53MB；仅8字段，原始文件和SQL/摘要已落盘data/raw/bigquant/minute-check-20260914-1。详见[SDK补充核对](../../artifacts/bigquant-sdk-enabled-20260914-1/review.md)。603026日低30.11定位09:37、300420日低6.50定位09:31；600452收盘31.64获佐证但分钟开盘31.48分歧仍在；300216/300461开盘分歧仍在。BigQuant首行09:25与旧档案09:30不同，603026总量还差2000股，不能静默替换。当前为补充来源证据，未改33项补丁、正式账户及前述PASS_WITH_LIMITATIONS身份；未把空记录当停牌事实。后续若修订须新批及受影响成交回归。


### 2026-09-14 用户批准BigQuant三日修订及300114状态核对（执行中）

主对话只新增artifacts/bigquant-source-repair-20260914-1与data/raw/bigquant/minute-repairs-20260914-1，不改公共引擎，旧33补丁/账户-6保留。核实三日不仅单字段不同，故以完整股票日BigQuant记录作为修订候选，禁止拼接挑价；09:25集合竞价只在派生聚合中映入首个09:35区间，240连续分钟保持原时间，原始CSV不改。比较全部字段及实际当日成交，变化才重跑完整受影响账户。300114本地正常交易、日线量2635640股，接口daily有对应量价，分钟缺失仍阻断实际依赖。T3不因本批整体暂停；策略/信号/门槛不变。状态RUNNING/PENDING。


### 2026-09-14 性能整改件 -20260914-1 送审（R1–R7 全清，请求定向复核）

送审对象：[一页送审页](../../artifacts/factor-engine-performance-20260914-1/SUBMISSION.md)
→ 整改报告 [report.md](../../artifacts/factor-engine-performance-20260914-1/report.md)。
实现身份：隔离仓 D:/AI/workspace/factor-engine-perf-next-20260913 @ 0ea1764
（提交序列 7d88101 → 0e6b970 → 0ea1764）；快照 t3-snapshot-20260913-5 已前移；主仓未合入未提交。

上一轮（[review-20260914-1](../../artifacts/factor-engine-performance-review-20260914-1/review.md)，
CHANGES_REQUIRED）七项处置：R2/R3/R7 于 7d88101 修（审核反例在本包 probe-from-review/ 原样复跑：
n_stale_true_days 5→0、code_change_key 与 preprocessor_key 均 false、corrupt_cache.accepted false、
truncated_cache → miss、alive_after_public_reset_and_disable false；反例已固化为包内 pytest 10/10）；
R1 于 0e6b970 接（L0-only 显式 retain_rows=False，pipeline 增 --with-cost-ladder/--no-cost-ladder；
probe_r1_wiring 4/4、worker CLI 带缓存 PASS 9/9 且真实生成 price_panel/）；R4 于 0ea1764 补运行身份
并重跑（身份 ok、20/20 代表、60 次比较逐位相同、仍不采用 GPU）；R5 打包侧修（33 条可复制命令 +
实跑一条 rc=0）；R6 本包冻结重算（plan-conformance-after-r6.json：44 行 / 102 条证据 / 缺路径 0；
除审核点名的 -8/report.md 与 -8/switchover-status.json 外，其余 97 条与 -8 索引逐字节相同，
无第三条漂移）。

必须保留的两句口径：R1 只接 L0-only 路径，成本阶梯开时仍保留逐股行字典（backtest 需要，有意不是漏接）；
跨会话计时漂移使 blocked_128 热点给区间 1.38–1.92x，两次都不过 2x，GPU 裁决不变。

本轮请求：只做定向复核（上一轮已写明无需重跑全部长基准）——R2/R3/R7 反例是否真闭、R1 接线是否可达
且不改变阶梯路径、R4 身份是否 fail-closed、R6 索引是否绑定本包最终版本。通过后即可申请正式切换
窗口（切换要动主仓，须用户确认）。附：T3 L0 按 2000 构造的外推为 2.2–3.1 h 串行
（-14-1/report.md §六），不改变 T3 未启动状态。此次未改算法/原始数据/账户规则；T1/T2 既有裁决、
统计 UNKNOWN、晋级 BLOCK、2025+/生产冻结不变。


### 2026-09-14 BigQuant三日修订完成（唯一当前补充状态）

主对话执行/最终验收，具体数据修订DONE / PASS_WITH_LIMITATIONS，见[验收报告](../../artifacts/bigquant-source-repair-20260914-1/review.md)及verification.json。三日源记录存在多个字段差异，采用完整股票日BigQuant来源而非挑价拼接；09:25竞价纳入首个09:35派生区间，原始时间保留。新data/raw/bigquant/minute-repairs-20260914-1/patches.json共33项，仅603026/2019-05-06、300420/2019-09-02、600452/2016-06-01替换，其他30项不变。能力身份同目录minute-capability-review.json。独立聚合3×48根864字段完全一致、9个时间网格负例拒绝，Provider通过。

四条已验账户请求独立枚举只有组合主/压力两个日期共4路径日受影响；全日基准成交/现金先复现，再用完整新源回放，fills完整字典相同、现金差0、费用差0，所有实际依赖覆盖。按用户批准规则，无需重跑全账户；旧-20260914-6账户及-20260914-2报告保留旧来源身份，收益/回撤结论不变，不冒充新源完整重跑。引擎源码摘要未变；未来新引擎或新候选仍须自身验收。

603026保留2000股总量差；600452开盘31.48/日线31.16差仍按既有研究源接受，新身份绑定，不称已解释。300114/2016-05-03本地与proxy daily价量一致且成交2635640股，确认为当前证据下正常交易的分钟缺口，非停牌；本批无实际依赖，未来实际触发只阻断对应候选。T1/T2既有受限通过保留，T3不因本修订整体等待，未代替新引擎联合验收；统计UNKNOWN/晋级BLOCK/2025+生产冻结保持。无公共代码修改、无提交、无BigQuant重复下载。


### 2026-09-14 性能整改整体第二轮复审（当前性能轨道状态）

对象：整改包factor-engine-performance-20260914-1、隔离实现/快照0ea176430880ef35ebe5ec0dfeb372fc46c2564c。审核者：当前审核主对话。执行/审核仍CHANGES_REQUIRED，正式切换未放行。报告：[整体复审](../../artifacts/factor-engine-performance-review-20260914-2/review.md)。

认可：L0-only/成本阶梯接线独立4/4；R7公开reset/关闭释放旧bundle；R3同shape改写拒绝及隔离重发布；R6原摘要漂移关闭（106条引用SHA独立全匹配）。亲跑38 pytest、身份40、检查点31、比较器11全过，7文件差量与快照行尾归一化一致。

未闭合：新预处理指纹repr(co_consts)含代码对象地址，三个新进程同输入产生三个键、全miss；资格运行参数仍未入键；缺缓存成员无法重发布、缺shape抛TypeError；GPU输入收尾不一致仍MEASURED/rc=0，且未核实际源数据收尾；可复制命令仍有硬编码写旧包；新索引未绑定本次GPU等新增整改证据。详见独立反例probe-results.json与报告整改要求。GPU记录计时可复算但本次低内存条件不支持稳定性能区间；维持不采用GPU，2000构造2.2–3.1h只属历史参数情景，不是当前已证性能。

下一步先修跨进程稳定性/完整资格身份/坏件恢复/失败收尾，再新包绑定与预算内限定重测。已读最新T1/T2限定完成记录，不恢复旧BigQuant/四账户阻断；本性能自身未通过。未改算法或旧包、未提交/切换、未启动T3；统计UNKNOWN、晋级BLOCK、2025+/生产冻结不变。


### 2026-09-14 性能整改件 -20260914-2 送审（第二轮四项实现缺陷已修，请求定向复核）

送审对象：[整改报告](../../artifacts/factor-engine-performance-20260914-2/report.md)
与[最终绑定清单](../../artifacts/factor-engine-performance-20260914-2/final-manifest.json)。
实现身份：隔离仓 D:/AI/workspace/factor-engine-perf-next-20260913 @ 231ae33
（上一轮 0ea1764）；主仓未合入未提交。

第二轮点名的六项处置：① 指纹改为递归稳定编码 —— 3 进程同一键、命中 false/true/true，
审核方自己的 review_probes.py 复跑同结论；② 8 项资格运行参数进键 + 源码身份补
quant/history.py、quant/market.py，三个键互不相同；③ 统一结构校验，缺成员/缺 shape/旧版本/
改写/截断一律隔离且可重发布；④ GPU 收尾失败 rc=4、起始身份失败 rc=5，均写 finalise 且不产出
采纳裁决，另加可用内存采样与 timing_validity；⑤ 命令表 v2（16 条写新根），实跑路径写死的
生成器：首跑 rc=0、重跑被拒、包 -8 目录指纹未变；⑥ final-manifest.json 绑源码/生成器/输入/
新测量/新反例，自校验 37 条 0 失配、新 GPU 文件在绑定内、包 -14-1 索引 106 条 0 失配。

受限重测（审核要求「修好后重测受影响性能」）：285 股切片跨进程 冷 38.0 s → 热 4.0 s（9.45x，
命中 5/0/0，含内容校验）；口径限于该切片，不外推全池，旧 19 s 数字不再沿用。

口径：2000 构造 2.2–3.1 h 降为历史假设情景，本包不重算；缓存键变更使包 -8 数组缓存按设计
一次性失效，全池首次重跑为冷装载口径。另披露并已修我自己的一处越界：导入包 -8 脚本留下
__pycache__（2 个 .pyc）已删除，内容文件哈希未变。

本轮请求：定向复核上述六项是否真闭（无需重跑全池长基准）；通过后即可申请正式切换窗口
（切换要动主仓，须用户确认）。未改算法/原始数据/账户规则，未启动 T3。


### 2026-09-14 性能整改件 -20260914-2 第三轮送审（绑定可复现性已修，请复核 n_bad=0 / passed=true）

对象：[整改报告](../../artifacts/factor-engine-performance-20260914-2/report.md)（§六 本轮修复）、
[最终绑定清单](../../artifacts/factor-engine-performance-20260914-2/final-manifest.json) 与校验结果
final-binding-verified.json。实现身份仍为 231ae33（未再改代码）。

第三轮点名的 3 条摘要失配已修：① 被绑定产物改为**写一次即冻结**（探针/生成器重跑改落带时间戳
新名，不再就地覆盖）；② 验证输出 final-binding-verified.json **不再进清单**（消除自指），改为
反向记录 manifest_sha256 与逐条结果；③ 清单在全部证据冻结之后最后生成，并新增 binding_rules
字段明写该规则。

复核方式（一条命令，约 15 秒）：

    D:/AI/agent/hermes/venv/Scripts/python.exe -X utf8 artifacts/factor-engine-performance-20260914-2/verify_final_binding_20260914.py

当前结果：n_referenced=40、**n_bad=0**、new_gpu_bound_by_manifest=true、p1_index_mismatches=[]、
旧包未被改写、无 __pycache__、**passed=true**；并且这是在把 4 个探针/生成器**全部重跑过一遍**之后
仍然成立（过程见 rerun-stability.log，重跑产物均为带时间戳的新文件）。

请求：确认绑定校验通过后即可申请正式切换窗口（切换要动主仓，须用户确认）。
### 2026-09-14 任务2 审核裁决：引擎整合与 L0 入口接线 PASS_WITH_LIMITATIONS

对象：[artifacts/t3-engine-integration-20260914-1](../artifacts/t3-engine-integration-20260914-1/report.md)，整合仓 `3af1fc1`。审核者：当前审核主对话。
核了实际 diff（629 共同文件逐字节一致、8 个差异文件逐个说明来源与决议）、可复制命令、数值与工件，并复核 17 件证据：身份 40/40、检查点 31/31、比较器 11/11、冻结负例 8/8、真新进程 CLI 7/7、worker CLI 9/9、L0-only 逐位等价、p2 等价（冷缓存）35/35、池掩码轴等价、内核等价、标签哨兵、分母核对、独立核算（两公式月 RankIC 逐位相同、截面秩 0 差异）。
两处集成期缺陷（worker 扩展字段接线、`run_meta` 数据版本标签）已修并定向复验；另登记 3 项限制（不改动旧工件）：① `t3_perf_p2_arraycache_test` 早于 R3 隔离语义，属过期夹具；② p2 harness 的 `pool_mask_equal` 比较原始字典，热缓存下过严（轴等价与内容摘要相等已单独取证）；③ `_assert_preloaded_ok` 的 `n_pool_true` 字段语义为掩码字典全部条目，热缓存下字典只覆盖消费轴（实测两态取值相同，不参与身份哈希）。
裁决 PASS_WITH_LIMITATIONS：所选整合路径无未闭合的结果正确性、身份、恢复或接线缺陷，实际版本与可复现命令明确，可进入正式 L0 启动流程（受届时授权与最终清单登记约束）；限定口径不外推全池，L1/L2 未接通，统计 UNKNOWN、晋级 BLOCK、2025+ 与生产冻结不变。

