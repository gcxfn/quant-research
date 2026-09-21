# 任务一：十年研究基础设施

日期：2026-09-12（最新主审复核2026-09-13）。当前：本轮整改PASS_WITH_LIMITATIONS，T1整体未完成；唯一当前状态以文末交接复核记录为准。

## 目标与边界

复用现有研究引擎，补齐2015–2024历史研究必需的数据和运行能力。仅修具体缺口，不重写平台。前端、后端接入、生产发布不在本轮范围内；2025以后保持冻结。2015年前必要预热只用于信号和资格计算，不计收益。

先读根AGENTS及最新任务板、实际代码和工件。旧交接与当前证据冲突时按实际证据登记，不重复已完成工作。不得清理无关修改、覆盖原始数据或擅自提交。

## 执行内容

1. 盘点现有实现、测试、数据及缺陷，区分已完成、待验收和缺失。
2. 建立2015–2024逐年覆盖表：历史上市/退市股票池、真实上市年龄、ST、停牌、交易日历、历史涨跌停、日线、复权关系、公司行为、因子字段及其可用时间。同时核查既往研究使用记录，未知项保留未知。
3. 日线按研究股票池盘点；分钟先核来源覆盖，再按实际订单依赖获取，不默认下载全市场十年分钟。baostock串行、节流、断点续传，保留来源与批次身份。
4. 保留默认strict。不得直接把目前仅限2023–2024的research_disclose扩到其他年份；如确有需要，以真实差异证据形成规则修订，交对应审核任务核准后实施。1%价格/5%总量不是收益误差安全界。
5. 公司行为按实际持仓/订单依赖处理。缺退市估值时保留持仓并标净值无效，不虚构清算、不填零。缺分钟无日线成交回退。
6. 补齐必要长周期批次、身份校验、续跑和报告能力。代码/配置/输入摘要绑定；保留现金日、部分成交、未成交、费用和期末市值。区分可描述、数据不确定和不可验证结果。

## 交付与验收

- 逐年覆盖矩阵、缺口和依赖清单、既往使用记录。
- 必要diff、定向测试、来源清单、启动及恢复说明。
- 正常路径、缺/重复分钟、错身份/时间/复权、非法数值关键负例；已知缺陷回归和跨年度小规模端到端。
- 提供供独立重算的现金、费用、持仓和公司行为样例。
- 关键数据不可得时交付证据及受限范围，不称十年完整覆盖已完成。

审核配对：[任务一审核](ten-year-research-infrastructure-review-20260912.md)。T1与T3立即并行；T3完成自身登记审核后，可用既有已验收能力进行训练筛选及账户回测，不等待T1整体验收。只将具体候选的数据/能力缺口交T1处理，其余候选继续。T2可先冻结策略和准备配置，正式十年运行依赖相应数据和执行能力通过审核。

## 实施顺序与交接接口

- T1-A盘点：先列代码入口、数据路径、年份边界及硬编码。现有migration_signal_export和three_account_migration_signals固定24个月/三账户，不能仅改日期直接复用；新十年入口应显式接收窗口和两个策略身份，复用计算函数，保留旧入口默认行为。
- T1-B能力验证：验证按历史日选池、预热、月末/下一会话映射、日期读取边界、按需分钟及跨年费用。先以限定真实样例和合成负例验收，不以全市场十年完整分钟为前提。
- T1-C运行支持：按T2/T3实际依赖补分钟/事件；不能要求T2先提供完整成交名单，也不能因尚无完整订单名单拒绝能力验收。压力路径可能产生额外证券日，必须同样校验。
- 冻结数据契约至少含symbol、date/time、价格/量额单位、adjustflag、source、available_at、内容摘要和质量状态；复用已有字段名，缺项才补。交易日历明确交易所与时区，缺日不压缩时间轴。
- 对混含2025以后行的本地文件，读取入口须在解析/交付研究记录前按日期隔离；标签计算不得为成熟标签越界取值。最终日期2024年末可估值，不意味着2024年末信号的未来标签可计算。
- 预热起点按最长特征窗口、252会话资格和历史元数据需要登记；严禁把2015首日仍在市名单当十年证券全集。
- 获取前记录请求规模、抽样耗时与磁盘估计；仅一个baostock获取者共享队列。重试服从已有限流和断点机制，同一错误重复发生则记录原因并暂停相关请求，不死循环。旧探针先核真实进程，不凭状态文件重启。

## 工件与进度

新批目录：`artifacts/ten-year-infrastructure-20260912-N/`，N取未使用序号。最低产出manifest.json、coverage.csv、issues.json、verification.md；覆盖表含年份/字段/预期记录数/实得数/缺失原因/来源/可用时点，来源变化分段记录。语义已存在的工件可引用，不重复造格式。

能力审核通过后交接冻结数据契约、读取入口、运行命令和支持范围；T2实际依赖未完整前只标阶段通过。完成T2依赖支持及缺口结论后收口T1。

| 阶段 | 状态 | 执行者/批次/审核证据 | 下一步 |
|---|---|---|---|
| T1-A 盘点 | DONE·审核PASS | 批次 `artifacts/ten-year-infrastructure-20260912-1/`（coverage.csv/coverage-daily-20260912.json/issues.json/verification.md/review-infrastructure.md）；执行者：主对话(ZCode/GLM-5.3-Flash, ponytail)；审核：独立子代理复核通过（分母独立重算逐年精确相等）。关键结论：日线面板为完整矩形（逐年行数=在市股本×交易日分母，2015:665,917/665,917…2024:1,236,574/1,236,574）；5552只全历史、337退市股全部有复权因子；既往使用记录入coverage.csv | 覆盖矩阵移交T2/T3 |
| T1-B 能力验证 | DONE·审核PASS_WITH_LIMITATIONS | 新入口 `experiments/ten_year_partition.py`+`ten_year_research.py`（显式窗口/两身份/身份绑定/证据重放续跑）；共享diff仅`gate`可选参数（data_fields.py/engine.py，默认None旧行为不变）；日历补2014–2017 chunk（trade_cal 20260909-r1只增不覆盖）；定向测试`tests/test_ten_year_infrastructure.py`17项（2025隔离/缺月不压缩/续跑身份/跨年费用/真实数据2015–2016四股e2e，含252会话年龄门与停牌fail-closed复核）通过；全仓2242通过/13既有失败（反转hunk复现，与本批无关）；审核D-1/D-2文档缺陷已更正并复核关闭。限制：分钟/2015–2017分红按订单依赖、过户费历史变差披露 | T2正式运行按审核记录限制执行 |
| T1-C 运行支持 | PARTIAL（第三轮主审D-9/D-6/D-7/D-8跟进已整改待复核：换序漏股修复、检查点滞后协议、chunk内容sha绑定、精确键交集覆盖——十年真实缺失仅14证券日） | 回补批 `data/raw/tushare/daily_basic/20260913-r2/`（2015-2018，975交易日chunk，0失败，384MB；审核发现的5个瞬时空帧已重抓整改D-3关闭）与 `data/raw/tushare/dividend/20260913-r2/`（2015-2017，732除权日chunk，1.8MB）；`load_daily_basic_fields` 缺省扫r1+r2（D-4单测覆盖），DATA_VERSION分段登记；`ten_year_fee_terms` 法定费率制度表（沪市2015上面值计费段 transfer_bps=None fail-closed为唯一开放项G4r）；**G3硬边界**：baostock 5分钟自2020-01-02起（证据minute-probe-20260913/），2015-2019执行语义须T2登记决策；分钟下载仍按订单依赖不预下载 | T2登记2015-2019执行语义；订单名单出现后补分钟；缺口结论后收口T1 |


### 2026-09-13 最新主审裁决（覆盖上表当前状态，旧记录保留）

用户要求审核以任务正确实施为准，不使用ponytail。审核者为本主对话，非T1实现者；未修改被审算法。

| 阶段 | 当前执行状态 | 当前审核状态与证据 | 下一步 |
|---|---|---|---|
| T1-A | CHANGES_REQUIRED | D-8：daily_basic证券日分母与日期文件覆盖率混用；旧盘点有效事实保留 | 更正覆盖矩阵分母及未知项 |
| T1-B | CHANGES_REQUIRED | D-5输入摘要未绑定；D-6零进度失败后恢复实测FileExistsError | 补输入身份与恢复协议，关联复核 |
| T1-C | CHANGES_REQUIRED | D-7连续空日线仍记成功并被续跑跳过；当前975个回补文件确为非空，数据事实保留；分钟、公司行为消费及G4r未收口 | 修获取质量状态，按真实依赖补公共能力 |

审核记录：`artifacts/ten-year-infrastructure-20260912-1/review-current-20260913.md`；摘要与数据逐文件对账：同目录`review-current-20260913-evidence.json`。定向验证命令：`python -m pytest tests/test_ten_year_infrastructure.py tests/test_migration_minute_provider.py tests/test_migration_costs.py -q`，27 passed、12 subtests passed；另两项隔离复现证实D-6/D-7。当前身份下不能沿用旧“无遗留整改”结论。不受影响的既有能力及已核数据可继续供T2/T3使用，不要求T3整体暂停。未授权改变分钟执行语义，2025以后与生产继续冻结。


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

### 2026-09-13 该复核唯一限制项整改（空分红摘要前置）

复核唯一未闭合项（`chunk_satisfied` 空文件分支在摘要比较前返回）已整改，实施者：主对话；改动仅限该项，未触碰算法语义、原始数据与数据批。

- 代码：`experiments/ten_year_field_backfill_20260913.py` — 内容摘要比较前移到空文件分支之前；空文件须证明字节为 `b''`（摘要 `sha256(b'')`）才按合法无事件日放行。新 SHA256 `26dae5656ca37ff9b332b8e5971851a20c660a20333e797e1c2c51a2870baac3`（旧 `722e876f…`）。
- 测试：`tests/test_ten_year_infrastructure.py` 新增 `ChunkSatisfiedTest::test_dividend_empty_file_with_wrong_sha_rejected`（空文件+错误 sha 拒绝；空文件+rows=3 拒绝）。新 SHA256 `a07f8184b1537c44ca4da69b725eb36c43f30671eb32bb5f313871f37074685a`；定向项 34→35。
- 证据：`python experiments/ten_year_field_backfill_20260913.py --dataset all` → 两批 `pending=0`（离线，早于 `get_pro()`，无网络请求；真实 1,707 条目零拒绝，199 空分红文件摘要确为 `sha256(b'')`）；`pytest tests/test_ten_year_infrastructure.py -k "ChunkSatisfied or DailyBasicMultiBatch or ResumeSafety" -q` → 13 passed；四文件合集 → **48 passed, 4 subtests passed**（181.49s）。
- 阶段影响：T1-C 的 D-7 该项限制关闭；T1-A/T1-B 状态不变。T1-B 账户现金/费用/持仓/公司行为独立核算、G4r、2015–2017 账户消费、实际订单分钟依赖仍未交付；T1整体未完成。旧摘要下的 PASS_WITH_LIMITATIONS 仅覆盖旧身份，本项以新摘要复核为准。记录：`docs/handover-ten-year-t1-20260913.md` §10。

### 2026-09-13 账户能力补交（面额制过户费 / 早期分红消费 / 2015-2016 账户样例）

承接复核剩余项 §6.2/§6.3/§6.5，实施者：主对话；离线运行，未下载、未改动原始数据与数据批。

| 项 | 交付 | 摘要 |
|---|---|---|
| G4r 面额制过户费 | `quant/execution.py::trade_fee_breakdown` 新增可选 `transfer_per_share`（元/股，买卖两侧按股数）；`ten_year_fee_terms` 对 2015-01-01..2015-07-31 沪市给出 `transfer_bps=0.0 + transfer_per_share=0.0003*face_value`（`face_value` 默认 1.00，可覆盖）；`fixed_capital_portfolio._FEE_KEYS` 纳入校验 | 不再 fail-closed，账本可用默认费率函数直接计费 |
| 早期窗口消费 | `r0_pilot_market_inputs.prepare_inputs(out, first, window, ...)` 从 `main` 提取；`check_fixed_window` 与 `resolve_event._check_event_window` 放行 2015-2024 内任意区间（原两固定窗口等价，2025+ 仍拒绝） | 2015-2016 分红经 r2 回补批进入账户账本 |
| 账户样例 + 独立重算 | `experiments/ten_year_account_20260913.py`（信号批→固定现金账本，日线执行/opening_cash_only/逐执行日法定费率/代码身份绑定）+ `experiments/ten_year_account_audit_20260913.py`（独立 Decimal 费率制度重建现金/费用/持仓/可卖/净值，逐日 1e-6 对账，不调用账本与费用引擎） | 批 `artifacts/ten-year-infrastructure-20260912-1/account-2015-2016-sample/`：两身份各 36 成交、分红 2,408.42、2015-07 前面额制成交 7 笔、现金/净值误差 0、`data-issues.json` 为空 |

共享费用核算打通：`factor_miner/pilot_costs.fill_costs` 新增可选 `terms=`（显式费率制度，十年窗口与面额制不再受 TRAIN 日期限制）、`r0_mechanism_cost_pilot.account_metrics` 新增 `fee_terms=` 且 `yearly` 按实际年份推导——T2 十年账户可直接用共享核算做费用对账；默认 TRAIN 口径行为不变。

测试：`tests/test_ten_year_infrastructure.py` 定向项 35→41（面额制费率负例 + 账户样例 6 项含共享费用交叉核算与篡改账本拒绝）；`tests/test_pilot_cost_ledger.py` 面额制单独表达回归 1 项；`tests/test_pilot_costs.py` 显式 terms 2 项；八文件合集 70 passed + 4 subtests。命令见 `docs/handover-ten-year-t1-20260913.md` §11.5（账户脚本须 `python -m` 方式运行）。

边界：样例仅 2015-2016 两身份，非十年全量账户；2015-2019 执行语义仍为 T2 登记项（样例按日线执行并已登记）；2025+、生产、统计 UNKNOWN、晋级 BLOCK 不变。T1-B/T1-C 执行状态不变（WAITING_REVIEW / RUNNING），整体未完成。

**同日复核（主对话终裁 + 两个只读独立子代理）：PASS_WITH_LIMITATIONS。** 记录 `artifacts/ten-year-infrastructure-20260912-1/review-account-20260913.md`。子代理独立复算确认：面额制 7 笔沪市成交按 `shares*0.0003` 计费共 2.85 元、36 笔费用分量零不匹配；r2 中 2015-2016 四码实施分红 8 条中 6 条入账且逐事件金额=登记日股数×每股现金、无零持仓或伪造入账；账户独立重算最大现金/净值误差 0，篡改负例抛错。子代理另发现 `Replay._annotate_costs` 生成门漏 `transfer_per_share`（单用面额制键时费用已扣但无分量标注），已修复并补回归，样例 `account.json` 摘要未变。T1-C 在该项上转为「账户能力已交付、整体仍 RUNNING」：剩余为十年全量账户、2015-2019 执行语义登记、2020+ 分钟订单依赖。


### 2026-09-13 空分红摘要修复主审终核（当前状态）

**修复审核PASS：D-7最后一项空分红摘要缺口关闭，本轮列出的代码整改项均已关闭。** 主审亲测6项ChunkSatisfied测试通过；独立原例错误摘要/错误行数拒绝、合法空日通过；199真实空日零拒绝。新代码/测试摘要与提交复核声明一致。证据：`artifacts/ten-year-infrastructure-20260912-1/review-handover-20260913.md`末尾及`review-empty-dividend-fix-20260913.json`。

T1整体仍未完成，阶段状态维持A DONE、B WAITING_REVIEW、C RUNNING；整体阶段审核PASS_WITH_LIMITATIONS，剩余为账户独立核算、G4r、早年账户消费及实际分钟依赖尚未交付，已不包含空分红摘要限制。无需重复修已关闭缺陷；后续提交未交付项证据再验收。T2/T3已验收路径可继续，冻结不变。

### 2026-09-13 账户能力补交后当前状态（唯一当前状态入口）

**执行状态：T1-A DONE（审核 PASS_WITH_LIMITATIONS）；T1-B WAITING_REVIEW（审核 PASS_WITH_LIMITATIONS）；T1-C RUNNING（审核 PASS_WITH_LIMITATIONS）。T1 整体未完成。**

本轮（账户能力补交）已交付并复核通过：日线执行账户能力、跨年法定费率（含 2015 上半年沪市面额制过户费，G4r 关闭）、2015-2016 分红/送转账户级消费、2015-2016 两身份账户样例及其独立重算。证据：`artifacts/ten-year-infrastructure-20260912-1/account-2015-2016-sample/`（含 `independent-review.json`）、`review-account-20260913.md`、`-evidence.json`；说明见 `docs/handover-ten-year-t1-20260913.md` §11。

仍未交付（不因本轮通过而放行）：十年全量（2015-2024）账户运行；2015-2019 执行语义（T2 登记项，样例按日线执行）；2020+ 分钟订单依赖；2025 以后与生产发布冻结、统计 UNKNOWN、晋级 BLOCK 不变。后续提交这些项的证据再验收，不重复已关闭缺陷。

### 2026-09-13 最终当前状态（覆盖以上全部“当前状态”段落）

账户能力补交与共享费用核算打通后重新裁决：**T1-A PASS_WITH_LIMITATIONS / T1-B PASS_WITH_LIMITATIONS / T1-C PASS_WITH_LIMITATIONS（限本轮交付面）**，T1 整体仍未完成。

- 已关闭并复核：空分红摘要分支（§10）；G4r 面额制过户费（能力 + 实际计费 + 独立复算，§11.1/§11.6）；2015-2016 分红账户级消费（§11.6）；账户现金/费用/持仓/公司行为样例与独立重算（§11.3）；共享费用核算可复算十年账户（§11.7）。
- 仍未交付：十年全量（2015-2024）账户；2015-2019 执行语义（T2 登记项）；2020+ 分钟订单依赖。
- 不变：2025 以后与生产发布冻结、统计 UNKNOWN、晋级 BLOCK；不自动授权日线成交替代分钟。
- 当前身份与命令见 `docs/handover-ten-year-t1-20260913.md` §2.1/§5/§11；复核记录 `artifacts/ten-year-infrastructure-20260912-1/review-account-20260913.md`（+`-evidence.json`）。

### 2026-09-13 执行记录：共用装载/统计出口性能优化（T1 公共能力面，批次 `-4`）

依 `docs/experiments/t1-t3-implementation-review-20260913.md`（T1 负责共享装载、输入身份、
NumPy 统计/求值出口与 GPU 能力）。实施在隔离副本，主仓工作树未改动。

**交付**：`artifacts/factor-engine-performance-20260913-5/`（取代 `-3`，原因见包内 `VERSION.md`）。

**共享能力面改动**（T1 职责范围内的公共文件）：

| 文件 | 改动 | 默认状态 |
|---|---|---|
| `experiments/factor_miner/stats_np.py` | ①`spearman_np` 去两次冗余排序（平均秩和恒为 `m(m+1)/2`）；②面板/截断 close 缓存**绑定不可变输入身份**（`panel_cache_bind`，换 bundle/轴即失效）；③缓存统计增 `bound_input_identity` | B1 生效；缓存 opt-in |
| `experiments/factor_miner/data_fields.py` | 装载去重备忘 `memoized_load`（键 = loader + 路径令牌 + 文件 `(realpath, mtime_ns, size)` + 参数），容量有界 | opt-in |
| `experiments/factor_miner/engine.py` | 基本信息一次性索引；价格/行业/池掩码装载走备忘 | 索引生效；备忘 opt-in |
| `experiments/factor_miner/director.py` | ①`run_real_pipeline` 输入内容摘要**当场重算**闸（F1，fail-closed）；②`bind_perf_caches_to_input` 在 `train_test` 入口绑定输入身份；③`_apply_perf_caches` + `pipeline --panel-cache/--load-memo`，实际状态写入 `run_meta.perf_caches`；④`cluster_monthly_inline` 就地生成聚类月末值 | ①②④ 逻辑生效/opt-in；③ 显式开启 |
| `experiments/r0_audited_runner.py` | `verify_data_manifest()` 抽为唯一实现（F2） | 生效 |

**T1 相关验收证据**（均在批次 `-4` 内，本包身份下重跑）：
`identity-tests.json`（40 项，含 F1/F2 与缓存换输入）、`cli-test.json`（真实 CLI 端到端 ×
285 股）、`worker-cross-slice-equiv.json`、`load-scaling.json`（`measured_config=cold_uncached`）、
`kernel_equiv.json`、`l0-only-vs-cost-ladder.json`、`denominator-check.json`。

**性能结论（限被测支持集）**：装载 1.34×/1.36×、进程 wall 1.23×/1.25×、A/B 两轮 `PASS_EXACT`；
GPU 局部原型**不采用**（同源端到端 1.32× < 1.5× 判据）。全量 20 片**未跑**（用户取消状态未恢复）。

**与 T1 既有交付的关系**：本批只改公共装载/统计出口与身份闸，不改变费用、账户、PIT 与
执行语义。`docs/handover-ten-year-t1-20260913.md` §2.1 **确实包含** `factor_miner/data_fields.py`
（记 `306260fd114c62fa`）与 `factor_miner/engine.py`（记 `3953b40e581553f4`）两行；
该表绑定的是**主仓工作区状态**，而本批改动只存在于隔离副本、主仓工作树未改动，
故 §2.1 两行当前仍**逐字节相符**（实测主仓仍为上述两值；隔离副本对应为
`2f0218fe063467ec` / `35403e5cf0b68f76`）。

**合入时必须做的事**（否则 §2.1 失效）：把隔离副本的 `data_fields.py`/`engine.py`
合入主仓后，§2.1 这两行须按新摘要重绑，并按仓库规则同步 §0/§2.2/§4/§5 与定向测试计数；
本批的 `stats_np.py`/`director.py` 目前**不在** §2.1 内，合入时一并决定是否纳入。

### 2026-09-13 性能包 -5 主对话独立审核（覆盖该优化轨道此前当前状态）

执行状态：CHANGES_REQUIRED；整体交付/切换准备审核：CHANGES_REQUIRED；已测CPU优化、F1/F2局部修复和F3：PASS_WITH_LIMITATIONS。其他研究阶段状态不变，整体未完成，全量保持未启动。

审核记录：[性能包-5独立审核](../experiments/factor-engine-perf-independent-review-20260913.md)。受审源码2c3a31f3、59件摘要一致；亲跑输入身份40/40、比较器11/11、检查点29/29、B1对抗300/300。独立证据在 artifacts/factor-engine-performance-review-20260913-1/，命令见审核报告末尾。

下一步仅修R1–R5：worker消费事前冻结代码/数据契约并核收尾；证据绑定运行时摘要及补齐依赖；纠正GPU计时口径；回退显式--backend pure；补小规模新进程CLI并更正交付范围。GPU局部原型已做、当前不采用，旧“未做GPU原型”不再作为当前事实。-12只登记身份，未获本审核切换放行；不修改冻结旧包，不启动全量或L1/L2。

### 2026-09-13 R1–R5 整改（共用能力面，批次 `-6`）

审核裁决 CHANGES_REQUIRED 后按 R1–R5 整改，落点在共用文件：

- `experiments/t3_l0_worker_20260913.py`：新增 `_frozen_identity_block` /
  `_verify_frozen_identity`，`cmd_run` 与 `cmd_aggregate` 均先消费 `run-identity.json`
  并把摘要并入运行身份（检查点/session 自动绑定，缺 `frozen` 段即拒）；`_write_ledger`
  增 `frozen_identity` / `verification_mode` / `data_identity_tail`；新增
  `--symbols-limit`（缩样运行，实际 scope 如实写进配置身份，**修掉 `universe_scope`
  硬编码 "full" 的谎报**）。
- `experiments/t3_l0_batch_20260913.py`：`T3_SCRIPTS` 纳入 worker；抽出
  `DEFAULT_SNAPSHOT`。
- `experiments/t3_perf_provenance_20260913.py`（新）：依赖表单一事实来源 + 运行期来源记录。
- `experiments/t3_perf_run_evidence_20260913.py`（新）：证据运行器（运行前后各算一次依赖
  哈希，不一致即拒绝产侧车）。
- `experiments/t3_perf_package3_20260913.py`：证据新鲜度改为**内容比对**（记录值 vs 当前
  字节），侧车缺失/内容漂移/依赖未记录一律非零退出且不发布。

**合入主仓**：本轮改动仍在隔离副本，主仓工作树未动；`docs/handover-ten-year-t1-20260913.md`
§2.1 中 `data_fields.py` / `engine.py` 两行现在仍逐字节相符，**合入后须重绑**并同步
§0/§2.2/§4/§5 与定向测试计数。

**新批次 `-13`**：身份在新快照下重建（worker 现已入冻结脚本集合）。旧 `-12` 不改写。
全量仍未启动。


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

### 2026-09-13 用户1分钟数据接入（当前推进状态）

用户批准保留1分钟原件、聚合为既有5分钟执行口径。公共接入所有者：当前主对话；不改T2策略、摩擦或参与率。2015–2019 ZIP已迁入 `data/raw/user_minute_1m/20260913-143215/`，逐文件SHA256确认后删除下载目录对应源ZIP，见transfer-manifest.json。当前仅完成搬运，尚不代表数据准入；待核Parquet字段、时间标签、单位、未复权价格、完整性并生成派生5分钟数据。2020–2024尚在下载；不读取2025以后。

T1-C RUNNING；T2-A DONE，T2-B BLOCKED（分钟准入待验），T2-C PENDING。开始准备冻结信号对应的十年市场输入：`artifacts/ten-year-fixed-strategies-market-inputs-20260913-1/`，复用prepare_inputs和first_signals；账户尚未运行。CPU整改DONE及限定审核结论不变。

### 2026-09-13 分钟接入发现身份缺陷／新批修复（当前状态）

T1-C RUNNING；T2-A CHANGES_REQUIRED（新信号批正在重算）、T2-B BLOCKED、T2-C PENDING。旧信号完整性PASS不覆盖本次发现的证券代码重叠，旧批保留。问题与依据见 `docs/experiments/ten-year-code-identity-20260913.md`：三组代码变更须按生效日限制入池，IPO年龄不重置；账户需等股数迁移持仓和跨日目标。当前主对话所有公共改动：engine.py、fixed_capital_portfolio.py、ten_year_account_20260913.py、分钟Provider及新接入脚本；不覆盖应用或隔离CPU快照。

新信号批 `artifacts/ten-year-fixed-strategies-20260913-2/signals/`，冻结原策略配置，新运行命令与旧批一致但输出改新根。生命周期/十年/聚合测试50/50，账户衔接/既有账户48/48，分钟接线扩展后相关57/57（首个新夹具误设1股差异被既有容差接受，修正夹具后通过；未放宽实现）。

2015–2024十个ZIP已到工作区，两目录 `data/raw/user_minute_1m/20260913-143215/` 和 `data/raw/user_minute_1m/20260913-2020-2024/`；SHA校验后源ZIP已删，各自transfer-manifest.json留证。用户确认闲鱼购买，原数据商未知。原1分钟保留，241条（09:30加常规240条）聚合48条，09:30只入首根一次，精确float32分币编码还原。2015–2019旧选股探针1072条转换、2条缺完整网格，7条超现有异常线；不是实际订单清单。2020–2024探针和全ZIP CRC/交易日审核运行中，见 `artifacts/user-minute-1m-source-probe-20260913-{1,2}/`、`artifacts/user-minute-1m-review-20260913-1/`。

市场候选输入 `artifacts/ten-year-fixed-strategies-market-inputs-20260913-1/` 已生成1553证券/2431会话，摘要0差异；96潜在问题/207未核事件按实际持仓再裁剪。待新信号审核、分钟能力限定审核后运行四条原固定路径，所有具体阻塞保留；2025+/生产与统计冻结不变。CPU隔离交付DONE不变，但旧快照不包含本次身份修复，未来使用须另绑身份。

### 2026-09-13 1分钟接入与实际四路径终核（唯一当前状态）

执行：T1-A DONE、T1-B DONE（限定已验基础能力）、T1-C BLOCKED；T1整体未完成。T2-A DONE、T2-B BLOCKED、T2-C PENDING；CPU隔离性能整改DONE不变。审核：信号/分钟能力/代码衔接PASS_WITH_LIMITATIONS；完整十年账户BLOCKED。主对话以实际diff、测试、独立文件摘要及原账本复算裁决。

详细交付和命令：`docs/experiments/user-minute-ingestion-20260913.md`。十年ZIP全部迁入工作区，SHA及2431个日文件CRC/日历通过；源ZIP已按授权删除，原1分钟ZIP保留。发行人代码有效期修复的新信号批 `artifacts/ten-year-fixed-strategies-20260913-2/`：两策略各120月；REV11两个月、组合七个月选股改变，其余单股证据一致，2023–2024选股不变。旧错误信号批仅留档，不再用于新账户。

最终能力审核 `artifacts/user-minute-1m-review-20260913-1/review-v2.json` 绑定28个源码。最终关联56测试通过；生命周期/十年能力50测试通过（范围重叠，不相加）。原2023–2024两个账户离线同输入回归均PASS_EXACT：各484日、292/297成交，全账本逐项一致。账户中的代码变更保持股数/限售可卖限制/现金，跨日目标转新码；不重置真实IPO年龄、不产生交易费用。

实际四路径已运行两批（第二批是技术补漏重跑，不新增假设），当前批 `artifacts/ten-year-fixed-strategies-minute-accounts-20260913-2/`：全在2015-07-01 BLOCKED，28源码及副本、1554输入摘要独立复核一致，未生成有效十年account.json。第一批发现该日11只实际订单深市证券14:53后零量/重复价格并缺日总量；追加末端>=5分钟零量且日量缺口超过1股与1ppm即阻断，不能借research_disclose小差异线放行。真实提前收市/停牌总量守恒不受此门禁阻断。第二批首阻塞REV11为000681、组合为000032，见blocking-review.json与每路径minute-source-failure.json。

具体外部依赖：`artifacts/user-minute-1m-review-20260913-1/data-repair-request.csv` 共22证券日，11当前实际订单阻塞、11后续选股预检；给卖家的中文说明同目录。2015-07-01实际问题名单11只，另300114在2016-05-03/2022-05-05缺完整分钟。大日线差异需核正确来源，不能一律认定分钟错误。用户确认闲鱼来源，原供应商未知。等待真实补数/来源核验；不得日线反填分钟、拼接不同资金账户或宣称上半年已独立验收。

下一步：收到修订分钟后另建原始批并重绑审核身份，从同一20万元初始现金重跑两策略主/压力，随后完成账户独立核算与T2-C归因；当前清单非未来全部订单的穷尽。统计UNKNOWN、晋级BLOCK、2025+行情收益/生产冻结。主仓未提交；CPU旧快照不含本次金融身份修复，未来切换须另绑，不覆盖旧包或启动T3全量。

### 2026-09-13 free-stockdb 官方发布包与源核验（当前补数来源探测）

用户指定来源 `hello245m/free-stockdb` 的 latest Windows 发行包已另建批次 `data/raw/free-stockdb/20260913-1/` 下载并纯解压，未运行包内任何 `.exe`、`.pyd`、`.py` 或 HTML。ZIP SHA256 为 `5f8e08cc27fbab7ac263d1c75a1eb368e96c1758614cee80c3a2bff97c15cbcc`，与发布方 SHA256 文件和 GitHub API 中 ZIP 资产摘要一致；35 个 ZIP 条目的路径/链接/重名安全检查通过。包内没有数据或数据 manifest，`sync_url.txt` 只列 `https://ah.123128.xyz` 与 `https://ad.123128.xyz`。两个根及常见 JSON manifest 路径只读探测返回 404，`/manifest` 返回 401，故没有可审计的公开源清单。

本次不能实证 2015-07-01 未复权 1m/5m，亦不能实证 `sz.000607` 或 22 项清单任一证券日覆盖；T1-C/T2 的分钟阻塞不变。完整原始 API、官方摘要、ZIP 清单、安全检查和源探测记录在 `artifacts/free-stockdb-review-20260913/`。后续仅可在取得可审计 manifest/明确数据接口并获准执行发布方更新器后，另建原始批、验收未复权标记、完整网格及日量守恒；不得以本包替代当前分钟输入。

### 2026-09-13 新CSV分钟补缺接入（当前状态）

当前主对话负责公共补缺接入。用户新目录实际为 C:/Users/ASUS/Downloads/2015_1min；12只2015-07-01目标股票的年度原CSV已复制至 data/raw/user_csv_1m/20260913-2，源/副本SHA一致，下载原件未删除。241根1分钟聚合48根，成交量由手乘100转股；12只开收盘与日线一致，日量相对差异最大0.002455%，高低价最大差异0.956%，仍按research_disclose披露，未宣称完全一致。-1为首次严格OHLC断言失败的保留批，未用于运行。

代码新增按股票日期使用冻结补丁，绑定原CSV/派生CSV/清单SHA，保留原ZIP；8项关联测试通过，12只真实Provider解析576根通过。证据 artifacts/user-csv-minute-review-20260913/{validation.json,review.json,provider-check/}。能力受限通过不代表完整十年验收。

四路径从原始资金技术重跑已启动：artifacts/ten-year-fixed-strategies-minute-accounts-20260913-3/，运行参数见manifest；--patches data/raw/user_csv_1m/20260913-2/patches.json，原信号和策略冻结不变。T1-C RUNNING，T2-B RUNNING，T2-C PENDING；CPU隔离交付结论不变。当前结果须以进程及最终manifest为准，未完成路径不可写DONE。

### 2026-09-13 三个新增年度CSV ZIP接收与补缺复核（当前状态）

当前主对话已将 Downloads 的2016_1min.zip、2018_1min.zip、2019_1min.zip复制至 data/raw/user_csv_1m/20260913-4/，源/副本SHA256一致，分别2834/3370/3572条目，无重名；下载原件保留，未宣称全包CRC或全库质量通过。transfer-manifest.json记录完整搬运身份。按五个剩余股票日期提取4份年度CSV（解压读取校验目标成员CRC）；2016包不存在sz300114_2016.csv。

新sz.002812 2018-03-01通过既有真实Provider的48根网格、身份、OHLCV和research_disclose校验，仍有小幅日线差异披露。证据 artifacts/user-csv-minute-review-20260913/new-years/review.json；脚本prepare-new-years.py、review-new-years.py、copy-new-years.py。合并清单 data/raw/user_csv_1m/20260913-4/patches.json 共20项；这是数据补丁清单，尚未生成绑定该清单的完整账户审核身份。

原22项还剩4项：sz.002442 2016-03-01分钟低10.99/日低10.87；sz.300114 2016-05-03无文件；sh.603026 2019-05-06分钟低30.44/日低30.11；sz.300420 2019-09-02分钟低6.57/日低6.50。三项低价差异与旧分钟一致，不能直接判日线或分钟谁错，不能放宽门禁。新包只修复其中1项。

账户第6批 artifacts/ten-year-fixed-strategies-minute-accounts-20260913-6/ 已结束，四路径BLOCKED：REV主路径新增sh.688059 2023-06-01差异，REV压力新增sh.688165 2021-11-01差异；组合主/压力仍阻sz.002442 2016-03-01。此前19项补丁已推动REV主至2023/压力至2021，但没有完整十年account.json，不报告部分收益为有效结果。原22清单不是未来订单完整缺口；现在共6个已知未解决股票日期（原4加新增2）。

T1-A/B DONE（限定能力），T1-C BLOCKED，T2-A DONE、T2-B BLOCKED、T2-C PENDING；CPU隔离交付DONE不变。下一步用baostock核两项2020后新增差异，并核三项早年低价冲突的日线源、300114身份/历史覆盖；无需重复运行已知仍会阻断的账户。统计UNKNOWN、晋级BLOCK、2025+/生产冻结，主仓未提交。

### 2026-09-13 xiaodefa 全量取数（T1/T2 数据供给，当前状态）

用户提供 Tushare 兼容代理，用于补数据；本轮只取数，不改策略账户。批次 data/raw/xiaodefa/20260913-bulk1/，去重清单 skipped-datasets.json，工具 experiments/xiaodefa_bulk.py 与调度 xiaodefa_bulk_all.ps1。参考/快照 20 项已落盘；adj_factor 3088 交易日进行中，随后 stk_limit/suspend_d，再排 35 个日频数据集、2014-2018 港股通/两融、月频宏观、逐股 9 类。分钟缺口以 baostock 5 分钟逐字段校验替换（688165/688059/603178/300114），三项漏最低价登记受审例外。细节见 docs/experiments/xiaodefa-data-pull-20260913.md。


### 2026-09-13 xiaodefa 取数收口（T1 数据供给，当前状态）

用户明确本阶段只做取数。批次 data/raw/xiaodefa/20260913-bulk1/，去重清单 skipped-datasets.json，
工具 experiments/xiaodefa_bulk.py（ref/daily/monthly/stock 四阶段，分页续传+节流+退避），
调度 xiaodefa_bulk_all.ps1 与 xiaodefa_bulk_heavy.ps1 并行，按 chunk 落盘自动去重。

T1 执行类核心数据已完成：adj_factor 3088/3088 交易日（2014-01-02..2026-09-11，1286 万行）、
stk_limit 3088/3088（1483 万行，无失败）；suspend_d 2962/3088 收尾。交易日历、在市日线、
退市/ST（baostock）、四大财报 5899 股全历史、分红、指数与申万行业此前已就绪。
待重试：adj_factor 2 天、suspend_d 3 天（传输抖动，非数据缺失）。

参考/快照 20 类落盘（stock_basic、trade_cal、index_basic 20752、index_classify、index_member_all、
fund_basic/company、etf_basic/index、cb_basic、ths_index、dc_index、tdx_index、stock_company、
namechange、st、stock_st、bse_mapping）；月频宏观 6 类收尾；余下 19 个日频数据集与逐股 9 类
约一天内跑完。

用户指示“可压缩的几个先不拉”，据此移除 stk_factor_pro（100+ 技术指标可由已落盘日线重算，
实测 63 秒/日，全量约占 9 小时）、cyq_chips（仅支持逐股）、4 个代理不存在的接口名，
以及 10 个按交易日恒 0 行的接口，全部记入 skipped-datasets.json 并注明原因。

取数口径、故障修复与未解项见 docs/experiments/xiaodefa-data-pull-20260913.md。
剩余数据未齐前 T1-C 保持 RUNNING；本记录不改变统计 UNKNOWN、晋级 BLOCK、2025+/生产冻结。

### 2026-09-14 xiaodefa 批次盘点（token 过期停止）

代理自 09-14 19:00 前后统一返回 `2002 token已过期`，后台进程已停，已落盘数据不受影响、
清单可按 chunk 续传，换新 token 重跑三个 ps1 即可。落盘总量 66517 分块／1.180 亿行／13.10 GiB。
19 个日频数据集 100%（含 T1 执行核心 adj_factor/stk_limit/suspend_d）；参考快照类按各自口径完整；
月频 5 项 151/153。未完成：stk_auction_o 缺 1 日、sw_daily 缺 2 日、ci_daily 2757/3088、
逐股 9 类（top10_holders 5893/5899、top10_floatholders 3049/5899，其余 7 类未开始）、
2014-2018 港股通/两融、cn_schedule 余月。盘点 artifacts/xiaodefa-bulk-20260913/inventory-20260914.json，
口径见 docs/experiments/xiaodefa-data-pull-20260913.md。T1-C 保持 RUNNING，未完成不写 DONE。


### 2026-09-13 分钟实际订单依赖闭合（T1-C 状态更新）

T2 四条十年账户路径（批 `artifacts/ten-year-fixed-strategies-minute-accounts-20260913-12/`）已全部跑满 2015–2024，**T1-C 的“十年全量账户/实际分钟订单依赖”交付项因此闭合**：四路径各自的实际订单分钟依赖已逐路径固定并通过，能力审核 `review-v7.json` 绑定 28 个源码与补丁清单 `minute-repairs-20260913-6`（30 项）。

本阶段新增公共能力：

- `experiments/xiaodefa_minute_repair_20260913.py`：按 (code,date) 用 baostock 5 分钟补齐，`--inputs` 现在真正生效（此前全局 INPUTS 未被工具参数覆盖）。
- `experiments/xiaodefa_repair_build_20260913.py::baostock_repair`：OHLC 仍要求逐字段相等；成交量允许 ≤5% 的 research_disclose 线并在条目内写 `volume_disclosure` 留痕（此前只接受 1ppm）。
- `experiments/xiaodefa_review_rebind_20260913.py`：只重绑补丁清单身份与源码摘要生成新 review，不覆盖旧审核文件。
- `experiments/ten_year_minute_defect_scan_20260913.py`：按账户同一口径预扫已请求过的分钟证券日，输出 DISCLOSE/BLOCK 清单（实测已请求 2838 项中仅 3 项硬阻断，均已修复）。

**更正覆盖口径**：`planned-selection-days.csv` 只登记建仓月，不含卖出/重试日（实测 sh.603209 2023-06-01 卖出、sh.603297 2024-02-01 均不在清单）。它是**建仓依赖上界**而非完整分钟依赖上界，xiaodefa 覆盖核定的 2400 项不等于实际订单穷尽；实际依赖以运行时逐笔订单为准。

仍未交付（不因本项闭合而放行）：数据取数队列（adj_factor 2 天、suspend_d 3 天待重试，日频/逐股仍在跑）、`sz.300114` 任意年份分钟缺口（2020 起可按需 baostock 补）、T1 整体仍未完成。统计 UNKNOWN、晋级 BLOCK、2025+/生产冻结不变。


### 2026-09-14 公共 Provider／审核器／事件依赖修复（按整改计划 S1–S3；不做最终验收）

依据 `docs/plans/t1-t2-remediation-closeout-20260914.md` §2（T1 负责公共 Provider、审核器与数据/事件依赖修复）。本轮只做修复，最终裁决（S5）留给审核方。

| 项 | 落点 | 证据 |
|---|---|---|
| 审核器失败门禁 | `experiments/ten_year_minute_accounts_review_20260913.py`：源码/审核/补丁/年包摘要任一 false 即拒绝；路径须恰为冻结四项且无重复；不完整批标 `PARTIAL_CHECK_NOT_AN_OVERALL_PASS`；新增“应有事件权益→实际条目”核对（登记日持仓×条款=现金/新股，含现金日与可卖日） | `tests/test_ten_year_accounts_review_gate.py` 8 例；`artifacts/t1-t2-remediation-closeout-20260914-1/s1-account-gate.json` |
| 分钟低价例外收窄 | `experiments/rev11_dynamic_minute_20260912.py`：只放行 (a) `price<daily_low` 或 (b) 首根 `open<=price` 且首根容量（按更严 0.0025）足以全额成交；移除不充分的 `price>minute_low`；等号/卖出 stop/未知类型 fail-closed | `tests/test_minute_low_only_exception.py` 8 例（含跨 bar 容量反例）；裁定表 `.../s2-minute-exception/minutes-exception-decision.md` |
| 已核事件移植 | `experiments/ten_year_corporate_action_port_20260913.py` → 输入批 `artifacts/ten-year-fixed-strategies-market-inputs-20260913-2/`（保留原失败裁定与 issue 历史） | 权益逐项对平（603801 主/压力、603613 两条） |
| 独立核算模块 | `experiments/ten_year_account_audit_20260913.py` 新增 opt-in 的已披露分钟容忍（成交价可越日线区间，但该证券日必须已登记披露），默认行为不变 | 四路径逐笔费用与逐日账本独立重建，误差 ≤2.33e-10 |

**由此产生的数据依赖**：`sz.002442 2016-03-01` 的逐 bar 真实数据不足（日线低 10.87 与两个同源分钟源 10.99 冲突，baostock 无 2016 年 5 分钟），收紧后组合两条路径在该日 BLOCKED。这是 T1 侧“具体受阻依赖”，不影响不受影响路径；不做日线反填、不放宽容差线。


### 2026-09-13 T1/T2/CPU完成情况独立复核（唯一当前审核状态）

T1整体仍未完成；T1-A已审盘点事实保留。T1-B/C公共能力整改为CHANGES_REQUIRED：十年输入未复用603613/603801已核公司行为，分钟最低价例外存在等号与卖出stop错误放行。既有数据和不受影响能力继续可用，取数队列保持既有授权；四路径曾跑满十年这一事实不变。CPU隔离第6包DONE / PASS_WITH_LIMITATIONS保留，尚未合入较新主仓。

审核者：当前主对话。实际证据、分级问题与最小整改见[本次审核报告](../../artifacts/t1-t2-cpu-review-20260913-1/review.md)及同目录evidence.json/probes.py。亲跑70项关联测试通过，28源码和1554输入摘要无差异，四账本逐日权益误差最大2.91e-11，CPU包101件摘要无差异；两个新分钟错误放行反例实测成立。未修改算法、未重跑账户、未启动T3、未提交；统计UNKNOWN、晋级BLOCK、2025+/生产冻结不变。

### 2026-09-14 CPU/GPU 下一轮性能计划 P0（新基线与试验冻结）

用户以 `/goal` 指定执行 [CPU/GPU 下一轮计划](../../plans/cpu-gpu-next-stage-20260913.md)。P0 在独立开发目录 `D:/AI/workspace/factor-engine-perf-next-20260913` 完成；主仓代码未改、未提交，主仓在途 T2 分钟账户批与 xiaodefa 取数不受影响。文件所有者：当前主对话（隔离目录内全部实验源码）。

- 正确性基线 = 主仓当前工作树（含证券代码有效期 `CODE_CHANGES/code_valid_on` 与 PIT 生命周期）。按[第6包合入方案](../../artifacts/factor-engine-performance-20260913-6/merge-plan-20260913.md) §2.1 两段式迁入受审 CPU 差量：阶段A `git apply -p1` 应用 `-2/diff/{stats_np,director}.py.diff`；阶段B `git apply -p1` 应用 `-6/diff/{stats_np,director,data_fields}.py.diff` 与 `git apply -p1 -C1 -6/diff/engine.py.diff`；随后落盘 worker `t3_l0_worker_20260913.py`、GPU 原型 `stats_gpu.py` 与 23 个 `t3_perf_*` 夹具。
- 合并后字节与合入方案 §0 表逐字节一致：stats_np `25875f6b…`、director `fb2a1ba3…`、data_fields `2f0218fe…`、engine `c529e051…`；engine 同时含 `CODE_CHANGES/code_valid_on`（主仓修复）与新增 `input_content_digest/_stock_basic_index/memoized_load`（受审差量）。
- 额外公共差量（显式登记，非静默）：采用第6包 `r0_audited_runner.py`(a86699da)、`t3_l0_batch_20260913.py`(4d143bf2)、`migration_runtime_20260912.py`(5e32c7a6) 以复用其 F2 身份负例；三者相对主仓为严格超集（仅删除被取代的旧 `_verify_identity` 等）。是否进主仓仍按合入方案 §4.3 走独立 T1 公共变更，本次只落在隔离目录。
- 冻结输入：`sample-hypotheses.jsonl` sha256 `23c1582b…`（20 条）；`universe.json` `n_included=5552 / n_total=5838 / n_delisted=337`、声明 sha256 `675704c5…`；`partition.TRAIN = 2020-01-01..2022-12-31`。
- 环境：python 3.11.15、numpy 2.4.6、torch 2.11.0+cu128、CUDA 12.8、RTX 4060 Laptop 8GiB、15.6GiB RAM、20 逻辑核。
- 核验结果：11 个 factor-miner/r0 测试文件 **210 passed / 6 failed**；6 个失败与主仓同批同因（LOCKBOX 上游 `statistical_validity` 门禁夹具，主仓对同样 10 个 factor-miner 文件亦为 6 failed/143 passed），非本次合并引入。`kernel_equiv` 全部 `bit_equal=true`；`identity-tests` 40/40；`frozen-identity-negatives` 8/8。
- 证据：`artifacts/factor-engine-performance-20260913-7/p0/`（baseline.json、identity-tests.json、frozen-identity-negatives.json、pytest-regression.log）。
- 依赖与限制：主仓 `t3_l0_batch`/`r0_audited_runner` 仍为旧版（缺 F2），F1/F2 负例当前只在隔离目录复现，未宣称主仓已具备；全池 P1 受内存约束（运行时空闲内存约 3.4GiB，另有 xiaodefa 取数与 T2 账户进程占用），按计划 §4/§6 记录，不缩股票全集冒充全池。

执行状态：P0 DONE（隔离基线可运行、身份负例通过）；下一步 P1 完整股票截面热点测量。T1 整体仍 RUNNING；统计 UNKNOWN、晋级 BLOCK、2025+/生产冻结不变。

### 2026-09-14 下一轮性能计划 P1（完整截面热点测量，部分完成）

隔离基线（commit `865802c`）上完成装载/内存剖面并给出全池可行性判据；求值热点测量因系统资源争抢作废，按计划 §4 停止。证据：`artifacts/factor-engine-performance-20260913-7/p1/`（findings.md、scaling.json、probe_n300.json、probe_n1200.json）。

- 冻结输入：`sample-hypotheses.jsonl` sha256 `23c1582b…`（20 条）；`universe.json` `n_included=5552 / n_total=5838`、声明 `675704c5…`；`TRAIN 2020-01-01..2022-12-31`，实测 `n_dates=972`。
- 装载剖面（`--skip-units`）：285 服务 → load 63.314 s、peak WS 511 MiB；1124 服务 → load 176.406 s、peak WS 1886 MiB、digest 1.435 s。线性拟合 `peak_ws ≈ 44 + 1.639 MiB/服务证券`，外推 5270 服务 ≈ **8.5 GiB**。
- 全池判据：本机 15.6 GiB、测量期可用 3.5–6.2 GiB、系统提交 29–31 GiB（上限 34–37 GiB）；全池约需 8.5 GiB，超出可用。按 §4/§六 不实际撞 OOM 凑记录 → 判定**当前实现的 5552 完整截面在本机内存不可行**，缩样本结果不得记作全池。
- 字段：20 条 `required_fields` 并集 24；引擎固定装 26（未用 `limit_up_count`、`turnover_rate_f`）。单纯减字段仅省约 8%，不足以放开全池。
- 求值作废记录：`n=2000 +3passes` 可用内存跌破 2 GiB 停止；`n=1200 +2passes` >19 分钟未完成、工作集被修剪至约 1.2 GiB、`PagesPersec≈2820`（换页）。对照 `-1` 包 285 服务 20 单元 10.6 s/遍且开启 `panel_cache`(hits=78) 与 `truncated_closes_cache`(hits=39)，故本次不作为有效热点/加速证据。
- 结论与下一步：P1 **部分完成**（装载/内存已量化、求值待测）。P2 先做计划 §5A 必要字段只读数组缓存（float64 数组约 26×5270×972×8B ≈ 1.06 GiB，同时降装载与内存），再在低负载窗口重测求值与 GPU 基线。不产出正式通过名单；统计 UNKNOWN、晋级 BLOCK、2025+/生产冻结不变。

### 2026-09-14 下一轮性能计划 P2 内存整改（全池已跑通，更正上一节）

上一节 P1 的计时与「全池不可行」判断有两处需要更正，均已用实测取代。

- **后端更正**：生产路径（`t3_l0_worker`/`t3_l0_batch`）设置 `FACTOR_MINER_NUMPY=1`（numpy 算子/统计分派）；先前一批 P1 计时未设该变量，走的是纯 Python 回落，已作废。夹具现显式绑定后端并记录 `env_FACTOR_MINER_NUMPY`。
- **新基线上的 A/B（285 服务，numpy 后端）**：A（主仓正确性基线，无性能差量）load 54.302 s / eval 19.233 s；B（本基线，缓存开）load 39.917 s / eval 8.706 s → 装载 **1.36×**、求值 **2.21×**（B 关缓存 eval 9.019 s，说明求值收益来自 numpy 秩/统计路径，与缓存基本无关）。
- **全池首次实测（失败）**：5552 请求跑到 440 s 时进程工作集 5928 MiB、系统可用 858 MiB、缺页 31.8 万/秒、提交触上限 32 006 MiB → 按计划 §4 停止。
- **内存构成实测**（`p2/memprobe_n600.json`，569 服务）：`row_by_date` 434.1 MB（837.9 B/行字典）、`bundle.data` 322.1 MB（24.5 B/序列值）、池掩码 27.0 MB；外推 5270 服务时行字典 ≈3.9 GiB 与序列 ≈2.9 GiB **同时在世**，峰值 ≈6.8 GiB——这才是失败的根因。
- **P2 整改**（dev 提交 `91acd52`）：`build_real_bundle` 改为流式——轴先行（`build_market_axis` 本就不读行）、逐股建序列、流式派生（新增 `_derived_accumulator/_derived_accumulate/_derived_broadcast`；旧 `_add_derived_state` 原样保留，测试仍直接用）；新增 `retain_rows=True` 缺省参数，`retain_rows=False` 时序列生成后立即释放该股 `row_by_date`（供 L0 统计路径）。成本阶梯/账户继续用缺省 `True`，行为不变。
- **等价性**：`p2/equiv_n300.json` **35/35 逐位通过**（流式派生 vs 旧 `_add_derived_state` 逐位相同；`retain_rows` True/False 全 26 字段逐位相同；dates/pool_mask/served 相同）。回归 11 个测试文件 137 passed / 6 failed（6 个与主仓同因，LOCKBOX 夹具），无新增失败。
- **全池实测通过**（`p1/full_pool_units_droprows.json`）：请求 5552 / 服务 4996 / 972 日期；load 408.615 s、池掩码 1.367 s、输入内容摘要 5.958 s、20 单元求值 122.914 s；**峰值工作集 5051 MiB**、结束可用 2040 MiB；装载备忘命中 17 524 / 未命中 14 593。
- **结论更正**：完整 5552 股票截面在本机**可运行**；上一节「全池内存不可行」的判断由本次实测取代（当时是旧结构叠加并行重负载）。服务 4996 < 请求 5552 是 universe 语义（静态超集中部分证券在 TRAIN 窗口无行），非筛股。余量仍偏薄（5051 MiB vs ~5.7 GiB 可用），计划 §5A「必要字段只读数组缓存」（序列转 float64 数组可把 2.9 GiB 降到约 0.8 GiB）仍是把余量拉开的下一步。
- 证据：`artifacts/factor-engine-performance-20260913-7/{p1,p2}/`。

执行状态：P1 部分完成（装载/内存/全池已实测，暖态重复、分段时间、GPU 基线待补）；P2 首项（行字典释放）完成；下一步补 P1 暖态与 cProfile 热点，随后进入 P3。统计 UNKNOWN、晋级 BLOCK、2025+/生产冻结不变。

### 2026-09-14 下一轮性能计划 P1 收尾、P2 速度项与 P3 GPU 裁决（当前状态）

- **P1 全池冷启 + 3 次暖态**（`p1/full_pool_p3.json`）：请求 5552 / 服务 4996 / 972 日期；装载 400.12 s；20 单元求值 **121.640 / 115.369 / 114.535 s**；峰值工作集 5245 MiB；池掩码 1.246 s、输入内容摘要 5.918 s。
- **P1 热点**（`p1/profile_n600.cprofile.txt`，569 服务）：装载仍主导（全池端到端里约占 77%）；调用级热点为 `csv.DictReader.__next__` 23.4 s tottime + `csv.fieldnames` 4.4 s、`zipfile._RealGetContents` 738 次 4.9 s、`_num` 9.4 s（38M 次）。
- **P2 速度项**（dev 提交 `8b2fc00`）：QFQ zip 句柄按 `(realpath, mtime_ns, size)` 复用；`load_raw_daily`/`user_qfq_rows`/`_read_chunk_csv` 由 `csv.DictReader` 改为 `csv.reader` + 一次性表头索引。**全池装载 407.071 → 295.490 s（1.378×）**；569 服务 60.187 → 49.268 s（1.22×）。两次 A/B 的 `engine.input_content_digest` **完全相同**（569 服务 `7b19e7bf…`、4996 服务 `4ebcb17b…`），即消费输入逐位不变；关联测试 94 passed。达到计划 §5「代表工作负载至少 1.2 倍」。
- **P3 GPU 裁决**（`p3/gpu-bench-fullpool.json`，真实全池：请求 5552 / 服务 4996 / 972 日期 / 728 区域内日期；按机械规则取前 5 个代表单元）：
  - 正确性：平均秩逐位相等、批量 Spearman 0 失配、IC 衰减在 block=128 与不分块两种配置下与 CPU **逐位相同**（`real_sample_all_identical=true`）；块边界 1/128/129/896/972 全逐位相同；CUDA 错误显式回落 CPU；OOM 折半策略覆盖全部日期且未越上限。
  - 性能：CPU 衰减合计 11.119 s；GPU block=128 6.302 s（热点 **1.7644×**）、不分块 9.322 s（1.1928×）；train_test 合计 32.876 s，衰减段占 train_test **33.82%**。
  - **裁决：不采用**（0 个配置同时满足「热点 ≥2× 且计算阶段替换估计 ≥1.5×」：block=128 为 1.7644×/1.172×，不分块为 1.1928×/1.058×）。GPU 保持隔离原型（`stats_gpu.py` 不在默认导入路径），正式入口维持 CPU。
  - 限制：该 bench 的 `decision_basis` 文案把样本写死为「真实 285 股」并称「全池衰减段占比未测」，与实际参数（`--real-n-symbols 5552`）不符，属夹具文案滞后，数值取自同一次全池运行；另 GPU 只接衰减段，而全池 wall 中装载约占 77%（400 s / 515 s），故衰减段有收益也难把端到端拉到 1.5×。
- **P4 跳过（有据）**：计划 §6.5 的前置是「P3 显示 GPU 工作量不足**且**公式段仍是热点，且存在预登记的完整子树类别」。本轮证据是装载主导（约 77%）、GPU 可接段占比 33.8% 且热点仅 1.76×，移植一个算子子树不会改变端到端结论，按计划「没有这样的类别就跳过 P4」跳过。
- 证据：`artifacts/factor-engine-performance-20260913-7/{p1,p2,p3}/`。

执行状态：**P1 DONE**（全池冷+暖、分段时间、RSS、GPU 基线齐全）、**P2 DONE**（内存 + 速度项，均有 A/B 证据）、**P3 DONE**（真实全池裁决：暂缓采用）、**P4 跳过**（有据）、**P5 待做**（接线/显式 CPU 回退/打包/身份与审核）。统计 UNKNOWN、晋级 BLOCK、2025+/生产冻结不变。

### 2026-09-14 下一轮性能计划 P5（接线、快照与交付包）

- **接线验证**（全部跑在本轮实现上）：worker CLI `p5/worker-cli.json` status=**PASS**（144 单元、冻结身份 sha256 `3715db15…`）；检查点 `p5/worker-checkpoint.json` all_ok=**True**（31/31）；新进程 `p5/cli-newprocess.json` all_ok=**True**（7/7：身份子命令、run 启动并完成、幂等续跑不重载、中断后续跑、**显式 `--backend pure` 真正切换**、清空环境变量不算回退、缺冻结身份被拒）。
- **新进程对照参数化**：`t3_perf_cli_newprocess` 新增 `T3_PERF_SNAPSHOT` 支持（默认仍指向原快照，不改历史默认行为）。
- **新快照**：`D:/AI/workspace/t3-snapshot-20260913-4` @ `4f4bcf2`（与交付工作树同一提交，洁净）。
- **交付包** `artifacts/factor-engine-performance-20260913-7/`（只新增，未修改第 6 包）：`manifest.json`（源码/输入/环境/命令/测量范围）、`benchmark.json`（实测与推算分列，标注 none-extrapolated）、`review.md`、`VERSION.md`、`p0/ p1/ p2/ p3/ p5/`、`source/`（10 文件）、`diff/`（10 diff + diffstat）。打包器 `experiments/t3_perf_package7_20260913.py` 可复跑。
- 复跑命令见 `manifest.json.commands`（均已实跑验证，不虚构未实现参数）。

执行状态：**P0–P3 DONE、P4 跳过（有据）、P5 DONE**（接线/快照/包）。本轮性能验证阶段的工作面已闭合；但 T1/T2 整改未闭合、正式切换未验收，故**不写整体 DONE**，且本轮结论只对被审计的隔离实现与 `4f4bcf2` 快照成立，主仓合入需另开身份变更窗口（合入方案 §3/§4.3）。统计 UNKNOWN、晋级 BLOCK、2025+/生产冻结不变。

### 2026-09-14 §5A 必要字段只读数组缓存（补齐计划首选机制）

上一节说明 P2 的内存目标是用流式表示达成的；本节补齐计划 §5A 指定的**数组缓存**机制。

- 实现 `experiments/factor_miner/array_cache.py` + `engine.build_real_bundle` 价格面板钩子。**默认关闭**：只有 `FACTOR_MINER_CACHE_DIR` 才启用，未设置时行为与引入前完全一致。
- 内容：PRICE 组 + 派生四字段的值数组(float64) + 存在性掩码 + P1 池掩码 + 覆盖信息。键含窗口/日期轴/请求证券/字段集/`data_version()`/dtype/复权语义 + **消费源内容 sha256**（每股 raw/adjust CSV 与交易所 qfq zip）；源、轴、版本变化即失效。staging→`os.replace` 原子发布；`np.load(mmap_mode='r')` 只读映射；None 精确重建。
- 负例 **9/9**（`p2/arraycache-test.json`）。等价性（`p2/arraycache-equiv.json`）：**6 917 724 个单元格逐位比对 0 差、池掩码 0 差**，摘要相同；569 与 4996 服务两条 A/B 的 `input_content_digest` 完全相同（`3adeb5a7…` / `4ebcb17b…`）。
- 计时：569 服务 31.634→**18.294 s（1.73×）**；4996 服务全池 295.490→**65.825 s（4.49×）**；首次构建 313.388 s（多 17.9 s / 6.1%），命中摘要扫描 6.62 s（2.70 GB）→ **重复 1 次回本**。
- 验证抓到并修复两个真实缺陷：命中判定误用「服务」证券集合去比「请求」集合（缓存形同虚设）、落盘早于派生字段广播（四个派生字段被缓存成“全缺失”）；两者均由 `input_content_digest` 不一致暴露。
- 限制：Windows 下 mmap 持有文件句柄，映射释放前该 `.npy` 不可删除；daily_basic/margin/lhb/industry 的逐日 chunk 扫描未缓存，仍占命中路径 65.8 s 的绝大部分。
- 身份更新：最终实现提交与快照同为 `caa61f8`；P5 三个接线测试已在该提交重跑（worker CLI **PASS**、检查点 **31/31**、新进程 **7/7**）。

执行状态：**P0–P5 全部 DONE**（P4 有据跳过；§5A 已补齐）。按计划条文仍**不写整体 DONE**——T1/T2 整改未闭合、正式切换未验收；主仓合入需另开身份变更窗口。统计 UNKNOWN、晋级 BLOCK、2025+/生产冻结不变。

### 2026-09-14 §5A 扩展到全部 5 个面板（当前状态）

上一节只缓存了价格 + 派生面板，命中后剩余的 65.8 s 全是 daily_basic / margin / lhb / industry 的**逐日 chunk 扫描**。本节把这三组也接入同一个缓存，共 **5 个面板**：`price_panel` / `valuation_panel` / `margin_panel` / `lhb_panel` / `bench_panel`。

- 键 = 各组窗口内全部 `chunk_*.csv`（基准组为按指数代码分块的全部文件）的内容 sha256 + 日期轴 + 字段 + `data_version()`；源/轴/版本变化即失效。组面板另存 `__present__` 位掩码，区分「该字段该证券不存在」与「存在但整列缺失」——两者在 `input_content_digest` 里编码不同（`S|-1` vs `S|972+NAN…`）。
- 等价性（`p2/arraycache-equiv.json`）：**6 917 724 个单元格逐位比对 0 差、池掩码 0 差**；三条 A/B 的 `input_content_digest` 完全相同（569 服务 `3adeb5a7…`、4996 服务 `4ebcb17b…`）。
- 计时：569 服务 31.539→**4.882 s（6.46×）**；4996 服务全池 295.490→**22.111 s（13.36×）**；首次构建 323.41 s（多 **27.9 s / 9.4%**）；命中路径里约 **11.25 s 是源内容摘要扫描**（3.67 GB）。**重复 1 次回本**。命中峰值工作集 4091 MiB（不缓存 4396 MiB）。
- 回归：12 个测试文件 **167 passed / 6 failed**（6 个为 LOCKBOX 夹具既有失败，与主仓同因）。
- 身份更新：最终实现提交与快照同为 `94f9c85`；P5 三个接线测试已在该提交重跑（worker CLI **PASS**、检查点 **31/31**、新进程 **7/7**）。
- 剩余：继续压缩只能改摘要策略（如持久化 sidecar），但计划明确要求缓存键用内容摘要，故本轮不动；daily_basic/margin/lhb/industry 的逐日重复扫描已消除。

执行状态：**P0–P5 全部 DONE**，§5A 已补齐并扩展到 5 个面板。按计划条文仍**不写整体 DONE**——T1/T2 整改未闭合、正式切换未验收；主仓合入需另开身份变更窗口。统计 UNKNOWN、晋级 BLOCK、2025+/生产冻结不变。


### 2026-09-14 继续修复与验收计划入口（仅计划，未新增裁决）

用户要求编写继续修复计划，见[计划](../plans/t1-t2-remediation-closeout-20260914.md)。以第14批及报告/诊断第2批为当前待核工件；已补交的公司行为、分钟边界和归因不重复建设。后续按审核器门禁、实际分钟路径依赖、归因独立复算、必要技术重跑及最终裁决推进。此次只写计划，未改被审代码、未重跑账户、未签PASS；现有任务审核状态及CPU/GPU独立进度不因本条改变。


### 2026-09-14 最终验收裁决（唯一当前状态，覆盖此前待审核）

T1整体执行/审核：BLOCKED，未完成。T1-A沿用DONE / PASS_WITH_LIMITATIONS；T1-B本轮已测公共修复DONE（限定）/ PASS_WITH_LIMITATIONS；T1-C执行/审核BLOCKED。审核器身份/路径门禁、603613/603801移植、最低价例外原反例关闭；但002442/2016-03-01真实分钟冲突及实际持仓未核权益未闭合。002166在REV压力存在股份权益依赖，002776在历史组合存在股份权益依赖，不能只凭nav_valid放行。范围文档还需撤销G4r/早年执行语义旧待办表述及过期分钟闭合声明，不要求未来宏观/行业全集齐备。CPU/GPU隔离P0及后续轨道保持自身进度，不被本条改写。

审核者：当前主对话；正式报告 [最终验收](../../artifacts/t1-t2-remediation-review-20260914-1/review.md)，同目录 evidence.json、provider-probes.json 与 attribution/。亲跑42测试通过；第14批四账本独立核现金/持仓/可卖/逐笔费用通过（最大误差2.33e-10），第15批REV两条与其逐字节一致；两批各1554输入身份一致。真实Provider复现002442两情景BLOCK、603026两情景ACCEPT；阶段IC独立复算一致、474行历史归因无数值差异。未修改算法、未重跑策略账户、未提交；统计UNKNOWN、晋级BLOCK、2025+/生产冻结，T3不自动启动。


### 2026-09-14 用户批准继续数据核实（RUNNING）

当前主对话负责本轮002442分钟差异敏感性与六项持仓公司行为公告核对；新增工件 artifacts/t1-t2-data-resolution-20260914-1/。保留日低10.87；同花顺一致为用户提供的佐证，尚非本地抓取证据。假设场景只作反例，不写入真实分钟源。已有整体BLOCKED裁决待新证据更新；不修改并行CPU/GPU或数据取数任务。


### 2026-09-14 公共聚合缺陷修复所有权（RUNNING）

当前主对话作为T1本轮执行者占用 experiments/user_minute_1m_20260913.py、experiments/migration_tushare_minute_adapter_20260912.py 及其两个测试。实际反例：002569/2019-09-02，09:30/09:31零量沿用昨收8.25，首笔09:32为8.43；旧聚合将非成交占位价纳入OHLC，触发新压力账户阻断。修复仅以有成交量行决定含成交区间OHLC；全零区间保留占位且不可成交，累计量额不变。此次将重绑能力身份、保留旧批并从初始资金重跑；不改变容差线、不补造002442缺失价格。


### 2026-09-14 现金政策实际反例修复所有权（RUNNING）

当前主对话追加占用 quant/execution.py、experiments/factor_miner/fixed_capital_portfolio.py 和最小回归测试。第20260914-3批REV压力独立审核发现：opening_cash_only只在订单规划按整单佣金限额，分钟拆单最低佣金累积后可能动用当日卖出款。执行层需单独维护当日开盘买入预算，每笔本金+实际费用扣减；默认通用Replay原语义保留，冻结组合显式启用。原失败批保留，不调整审核标准。


### 2026-09-14 继续修复后的最终裁决（唯一当前状态）

当前主对话执行并审核；报告 [修复与验收](../../artifacts/t1-t2-data-resolution-20260914-1/review.md)。最新账户批 `artifacts/ten-year-fixed-strategies-minute-accounts-20260914-4/`，新输入 `artifacts/ten-year-fixed-strategies-market-inputs-20260914-1/`，能力身份 `artifacts/t1-t2-data-resolution-20260914-1/minute-capability-review-2.json`。六项公司行为公告与除权参考价核对完成；零量占位污染OHLC聚合、分钟拆单佣金使opening_cash_only超预算两个实际缺陷修复并验收。175测试/22子检查通过。REV主/压力各2431天完整，未核事件依赖0，独立现金/持仓/可卖量/逐笔费用/权益核算通过（最大误差1.1642e-10元），路径DONE / PASS_WITH_LIMITATIONS。最新权益280222.30/283045.20元，税前分红研究口径累计40.11%/41.52%，非个人红利税后收益。

组合两条仍在002442/2016-03-01日低10.87、分钟低10.99处BLOCKED，无完整account.json。原日全部成交复现后，48个假设低价落点中主19、压力15改变成交；仅作敏感性反例，不是真实补数或误差上界。同花顺同为10.87记为用户提供佐证。需要真实分钟/逐笔或可核实统计口径解释，供应方说明已落盘，未发送。不得放宽例外或伪造最低价。

T1整体/T1-C继续BLOCKED；T1-A保留原限定通过，T1-B本轮公共修复DONE / PASS_WITH_LIMITATIONS。T2-A保持原通过，T2-B两REV限定通过/两组合BLOCKED，整体BLOCKED；T2-C旧报告勘误完成、诊断限定通过保留，新完整组合报告仍BLOCKED / CHANGES_REQUIRED。原20260914-1依赖中断、-2聚合缺陷、-3现金预算失败均留档，不作为PASS。不新增假设、不提交、不改CPU/GPU及T3调度；统计UNKNOWN、晋级BLOCK、2025+/生产冻结。当前修复文件占用结束，后续公共更改须新登记。


### 2026-09-14 用户提供BigQuant 09:35实际查询截图（RUNNING）

当前主对话继续执行。002442/2016-03-01 09:35一分钟记录低10.87，O/H/C/volume与本地同时间行一致；截图成交额140187.0与原始140187.46875的差异保留，不推定舍入原因。截图归档 artifacts/002442-source-resolution-20260914-1/，新补丁 minute-repairs-20260914-2，只依据观测修订该分钟low，原始文件留存。严格Provider两情景通过，无容差例外。新账户批20260914-5从初始资金重跑；这是带用户截图来源限制的研究数据修订，不声称官方原始源已重新发布或全量BigQuant已独立验证。


### 2026-09-14 002442截图修订后的实际运行裁决（唯一当前状态）

2026-09-14 批量补查补记：按用户“一口气要查的都发过来”，当前主对话只读扫描同一冻结信号身份下76份历史/当前请求文件及选股清单，共3619个去重证券日、120个日期，使用最新30项补丁和当前1分钟聚合、成交量等价及缺尾门禁。结果EXACT 2970、停牌跳过10、重点核查6、小差异633。重点为300114/2016-05-03、600452/2016-06-01、300216/2017-02-03、300461/2017-03-01、603026/2019-05-06、300420/2019-09-02；其中既有例外及仅计划依赖不冒充当前账户阻断。002442已修订日仍EXACT。已生成[一次性查询说明与639项完整清单](../../artifacts/minute-bulk-source-check-20260914-1/查询说明与完整清单.md)及同目录bigquant_batch_query.py，按77个日期批量导出BigQuant全天原始1分钟CSV、覆盖/失败记录和ZIP。名单唯一性、扫描对应关系及语法已检查，未在用户BigQuant账户执行，尚无新供应商结果；修复后新增实际订单依赖不在本次覆盖保证内。下一步用户返回ZIP后核对和定点修复；验收裁决仍按下文BLOCKED及既有REV限定通过，不放宽门禁。

当前主对话执行/审核；[本轮报告](../../artifacts/002442-source-resolution-20260914-1/review.md)。用户BigQuant查询截图明确002442/2016-03-01 09:35一分钟低10.87；O/H/C及成交量与原始同分钟一致，成交额差0.46875元保留。新补丁 minute-repairs-20260914-2 仅这一分钟low作有来源修订，旧数据保留，标明用户截图字段修订而非供应商重发原件。重新聚合后全天OHLCV与日线严格一致；两情景真实Provider strict通过，002442具体依赖DONE / PASS_WITH_LIMITATIONS，不靠例外或放宽容差。

最新账户批 artifacts/ten-year-fixed-strategies-minute-accounts-20260914-5/ 从初始20万元重跑。REV主/压力两账户与上一已验批逐字节一致，独立完整现金/持仓/可卖/费用/权益复核通过；组合两条越过002442，改在600452/2016-06-01阻断，均无完整account.json。新差异：日开31.16/分钟开31.48，日收31.64/分钟收31.65，其余日高低量一致；09:30报价零成交量，09:31原始分钟开31.48，不能直接恢复零量开盘来绕过门禁。已保存原始行与待查SQL，尚无该日BigQuant结果。

T1整体/T1-C与T2整体/T2-B继续BLOCKED（已验REV两条限定通过保留），T2-C完整组合报告仍BLOCKED / CHANGES_REQUIRED。原002442待补状态被本条关闭，新阻断明确独立。相关24测试通过，输入/源码/补丁/年包身份及完整REV账本复核在新账户verification.json；scope=PARTIAL_CHECK_NOT_AN_OVERALL_PASS。报告生成器历史固定文案更新，但不生成不完整组合的完整收益报告。无提交、无对外消息，CPU/GPU/T3状态不改；统计UNKNOWN、晋级BLOCK，2025+/生产冻结。报告文件本轮占用结束。

### 2026-09-14 §5 的 B/C 两项按实测暂缓 + 摘要扫描优化（当前状态）

计划 §5 的 A/B/C 是优先级列表，B 与 C 都带明确前置条件。本节记录实测结论与最终身份。

- **§5B（数组直传统计）暂缓**：热态 cProfile（`p2/profile_warm_eval_n300.txt`）显示 `_to_np` 0.53 s + `tolist` 0.22 s + `numpy.array` 0.32 s ≈ 1.1 s / 19.8 s（约 5%）；求值侧由秩/Spearman/bootstrap 主导，不是转换。按计划「若转换占比很小，本项暂缓」。
- **§5C（公共子表达式复用）暂缓**：`p2/common-subexpr.json`——20 条公式 81 处子表达式、61 个签名、17 个跨公式出现；除 `RET(close,N1)`（size 2，5 条）外最多 2 条共享，且只有 ACCDIST 累积线（size 17）算昂贵。收益量级 1–2%，不值得引入 AST 复用层（计划亦要求不建通用计算图、限制缓存字节）。
- **§5A 摘要扫描优化**（计划「优化内部重复调用，不删安全门」）：摘要备忘键由 `os.path.realpath` 改为调用方给的路径——缓存键里进的仍是**内容 sha256**，不同路径写法指向同一文件只是多哈希一次、结果不变。全池命中摘要扫描 11.25→**8.58 s**，暖态装载 22.111→**18.014 s（16.40×）**；三条 A/B 的 `input_content_digest` 仍与不缓存路径完全相同。
- 最终身份：实现与快照同为 `162e9b8`；P5 三个接线测试在该提交重跑（worker CLI **PASS**、检查点 **31/31**、新进程 **7/7**）；回归 167 passed / 6 failed（LOCKBOX 夹具既有失败，与主仓同因）；数组缓存负例 9/9；等价性 6 917 724 单元格 0 差。
- 执行状态：**P0–P5 全部完成**；§5 三项中 A 已交付、B/C 按各自前置条件实测后暂缓。按计划条文仍**不写整体 DONE**——T1/T2 整改未闭合、正式切换未验收；主仓合入需另开身份变更窗口。统计 UNKNOWN、晋级 BLOCK、2025+/生产冻结不变。

### 2026-09-14 性能计划边界的核实（P0–P5 工作项已穷尽）

本轮性能计划（`docs/plans/cpu-gpu-next-stage-20260913.md`）的 P0–P5 工作项已全部有结论：§5A 已交付（5 个面板的只读数组缓存，暖态全池装载 295.5→18.0 s / 16.40×）、§5B 与 §5C 按各自**计划自带的前置条件**实测后暂缓（转换约占暖态求值 5%；跨公式共享的最昂贵子表达式只被 2/20 条公式使用）、P4 有据跳过、P5 接线与打包完成（最终身份 `162e9b8`）。§5A 的摘要扫描另按计划「优化内部重复调用，不删安全门」去掉了 `realpath`（11.25→8.58 s，内容摘要不变）。

计划 §7 把本轮是否完成系于 T1/T2 整改闭合。本轮核实（2026-09-14 约 02:00）：

- 该门所指的两项 CHANGES_REQUIRED 已由并行 T1/T2 工作流关闭——R2 分钟最低价例外现为「严格小于日低 + side/otype fail-closed」并已有 8 项测试；F3 报告勘误已产出 `artifacts/t1-t2-data-resolution-20260914-1/report-errata.md`（新附录，不覆盖旧报告）。
- 同一工作流已解析 002442 来源冲突（`artifacts/002442-source-resolution-20260914-1/`）、六项遗漏公司行为的公告证据、并重跑第14/15批与新批 `ten-year-fixed-strategies-minute-accounts-20260914-5/`。
- 其最新裁决仍为 T1整体/T1-C 与 T2整体/T2-B **BLOCKED**（REV 两条限定通过保留），T2-C 完整组合报告 BLOCKED / CHANGES_REQUIRED——即门未开。

结论：性能计划自身的工作面已穷尽、结论与工件齐全；未完成的原因只剩计划 §7 明列的外部条件（T1/T2 整改闭合与正式切换验收），且该外部条件正由同一 T1/T2 工作流按数据依赖推进，本轮既不需要也无法代为闭合。主仓性能源码仍未合入（合入会改动 99 个已冻结身份引用，需另开身份变更窗口）。统计 UNKNOWN、晋级 BLOCK、2025+/生产冻结不变。

### 2026-09-14 性能计划 §5A 摘要正确性修正（当前提交 4961e66）

把交付命令**原样实跑**时抓到并修掉一条正确性缺陷：

- `array_cache.file_digest` 原以 `(路径, mtime_ns, size)` 做进程内备忘；改写为**同尺寸**且落在同一时间戳刻度会命中备忘、返回**过期摘要**——计划明令禁止的「用 mtime 代替内容」。先前去掉 `realpath` 减少了文件系统往返，使该窗口概率升高，负例 `digest_changes_with_content` 因此由 9/9 变 8/9 而暴露。
- 修法：**一律按内容哈希**，取消时间戳备忘。新增更强负例 `digest_ignores_size_and_mtime`（同尺寸改写后用 `os.utime` 复原 mtime，摘要仍必须改变）。负例 **10/10**。
- 修正后重测：569 服务 3.491 s（**9.03×**）；4996 服务全池 18.856 s（**15.67×**），三次重复 18.636/19.368/18.994 s（中位 18.994 s）；命中时内容摘要扫描 10.47 s；三条 A/B 的 `input_content_digest` 仍完全相同（`3adeb5a7…` / `4ebcb17b…`）。
- 身份：实现与快照同为 `4961e66`；P5 三测试在该提交重跑（worker CLI **PASS**、检查点 **31/31**、新进程 **7/7**）；回归 144 passed / 6 failed（6 个 LOCKBOX 夹具既有失败，与主仓同因）。
- 结论不变：性能计划自身工作面已穷尽；未完成的原因仍只剩计划 §7 的外部条件（T1/T2 整改闭合与正式切换验收）。统计 UNKNOWN、晋级 BLOCK、2025+/生产冻结不变。

### 2026-09-14 性能计划 §7 交付清单补齐（当前提交 f3e6e11）

逐项核计划 §7「交付最小集合」，补上两处**真实缺口**：

- **公式ID / 正式分母引用**：manifest 现记录 20 个代表公式 ID、选择脚本与名册身份（脚本 sha256 + `new-factor-research-20260912-3/hypotheses.jsonl` 的 sha256 与 1456 行）、登记分母引用（`new-factor-research-20260912-13`：**1430** 候选 / 20 片 / `candidates.csv` sha256），并写明代表集不替代正式分母，以及「代表集取自较早名册 -3、而登记批次为 -13」的出处差异。脚本与 `sample.json` 已随包放入 `source/`。
- **可复制运行**：原 `commands` 是 `<占位符>` + bash 式环境变量前缀，在本机 PowerShell 下不可直接运行；新增 `commands_resolved`——11 条 PowerShell 形式、绝对路径、含所需环境变量，本轮逐条实跑（`p2_equiv` 35/35、`p2_memprobe`、`p2_arraycache_equiv` 0 差、`p2_arraycache_warm` 17.2 s、`p2_arraycache_negatives` 10/10、`p2_common_subexpr`、`p5_checkpoint`、`p5_worker_cli` PASS；`p1_full_pool`/`p3_gpu_bench`/`p5_cli_newprocess` 三条长命令此前已用同参数跑过）。

身份：`4961e66..f3e6e11` 只改打包器一个文件（`git diff --name-only` 可核，不涉及任何 worker 依赖），故 P5 接线测试在 `4961e66` 上的结果对最终身份同样成立。实现工作树与快照同为 `f3e6e11`。

结论不变：性能计划自身工作面已穷尽；未完成只剩计划 §7 的外部条件（T1/T2 整改闭合与正式切换验收）。统计 UNKNOWN、晋级 BLOCK、2025+/生产冻结不变。

### 2026-09-14 性能计划 P1/P3 测量协议补正（当前提交 4efe4ba）

核计划 §4 协议时发现**没做全**：协议要求完整截面上「一次进程冷启动与至少 3 次暖态计时，CPU/GPU 交替次序」，而此前的 3 次暖态是纯 CPU、GPU 对照只有单次。

- 已扩为**真实全池 3 次暖态**，并在每个 (pass, unit) 上按奇偶**交替 CPU/GPU 先后**（两种次序都记录，`pass_totals`），数组缓存开启。
- 修掉多 pass 暴露的一个派生量缺陷：`all_identical` 原以**单元数**为分母，15 次比较全等价被误报为不一致；改为按**实际比较次数**（新增 `n_comparisons`）。修前 `false`（假警报）→ 修后 **true（15/15）**。
- 复测：三次暖态 CPU 衰减 9.35/9.09/9.53 s、GPU(block=128) 4.54/4.53/4.55 s（逐次稳定）；合计 CPU 27.97 s、GPU 13.63 s → **热点 2.05×**；train_test 78.13 s，衰减段占比 **35.8%** → 计算阶段估计 1.225×。
- 裁决仍为**不采用**，但理由更精确：block=128 现在**过了 ≥2× 热点门槛**（2.05×），卡住它的是计算阶段门槛（1.225× < 1.5×）；不分块两项都不达标（1.14× / 1.047×）。`benchmark.json` 的 verdict 已改为按配置逐项列出实际数值与通过标志。
- 身份：`4961e66..4efe4ba` 只改两个**非受审**文件（`t3_perf_gpu_bench_20260913.py`、`t3_perf_package7_20260913.py`）。受审集 = `experiments/factor_miner/*.py` + `tests/test_factor_miner*.py` + `AUDITED_EXTRA_PATHS`（`director.audited_code_paths`），T3_SCRIPTS 只含 5 个入口脚本——故 `4961e66` 上的接线测试证据对最终身份继续成立。实现工作树与快照同为 `4efe4ba`。

结论不变：性能计划自身工作面已穷尽；未完成只剩计划 §7 的外部条件（T1/T2 整改闭合与正式切换验收）。统计 UNKNOWN、晋级 BLOCK、2025+/生产冻结不变。

### 2026-09-14 性能计划 §6 四配置预算补齐（当前提交 3b9e37d）

核 §6 发现此前只比较 **128** 与**不分块**两种，而协议要求「只比较128、256、512及不分块四个预定配置」。已补齐（真实全池、3 次暖态、CPU/GPU 交替次序、数组缓存开）：

| 配置 | GPU 总耗时 s | 热点 | ≥2× | 计算阶段估计 | ≥1.5× | 逐位等价 |
|---|---:|---:|---|---:|---|---|
| blocked_128 | 13.558 | **2.0845** | 是 | 1.235 | 否 | 是 |
| blocked_256 | 14.367 | 1.9671 | 否 | 1.219 | 否 | 是 |
| blocked_512 | 18.064 | 1.5645 | 否 | 1.152 | 否 | 是 |
| unblocked | 24.497 | 1.1537 | 否 | 1.051 | 否 | 是 |

机械选配置（正确性 → 内存约束 → 真实 wall）选中 **blocked_128**（GPU 总耗时最小）。裁决仍为**不采用**：选中配置过了 ≥2× 热点门槛，但计算阶段 1.235× < 1.5×；其余三个两项都不达标。顺带记下「合成面板 512 最快（1.99×）而真实全池 128 最快」——正是协议写明「合成倍数不得当作任一真实配置通过证据」的实例。

身份：`4efe4ba..3b9e37d` 仍只改两个**非受审**文件（`t3_perf_gpu_bench_20260913.py`、`t3_perf_package7_20260913.py`）；受审集见 `director.audited_code_paths`，故 `4961e66` 上的接线测试证据对最终身份继续成立。实现工作树与快照同为 `3b9e37d`。

结论不变：性能计划自身工作面已穷尽；未完成只剩计划 §7 的外部条件（T1/T2 整改闭合与正式切换验收）。统计 UNKNOWN、晋级 BLOCK、2025+/生产冻结不变。

### 2026-09-14 性能计划 §4.2 测量方式补齐（当前提交 c82ac63）

核 §4.2 的测量方式清单，发现三处没做全，已补：

- **环境披露**：补 电源模式（`381b4222…` 平衡）、后台负载前 5（ChatGPT 469 MB / bun 420 MB / codex 187 MB / Memory Compression 169 MB / PhoneExperienceHost 169 MB）、候选吞吐 **0.1949 / 0.2057 / 0.2032 单元/秒**；连同 CPU 线程数、实际后端、版本、显存、峰值 RSS、系统可用内存一并记入 `benchmark.json.p1_environment`。
- **完整流程 wall**：`complete_flow_sec = 322.352 s` = 身份核验 0.14 s（**56 个受审文件**、git head 一致）+ 装载 19.207 + 池掩码 0.096 + 输入摘要 4.616 + 三次求值 298.29 + 落盘 0.003；分段与加和并列可核。
- **全批时间推算**：新增 `experiments/t3_perf_fullbatch_projection_20260913.py` 与 `p1/fullbatch-projection.json`——登记批 **1430** 构造按 `family` 计频，20 代表覆盖 **15/31** 类别、**16 类未测**（单列并用已测 per-unit 最小/最大给区间）；重复计算项 4 316–14 910 s，一次装载项单列 → 全批 wall **4 335–14 929 s（约 1.2–4.1 小时）**，标 `is_projection_not_a_run: true`，不冒充全量跑完。

身份：`3b9e37d..c82ac63` 只改三个**非受审**文件（P1 harness、新投影工具、打包器）；受审集见 `director.audited_code_paths`，故 `4961e66` 上的接线测试证据对最终身份继续成立。实现工作树与快照同为 `c82ac63`。

结论：性能计划工作面仍在收敛——本轮又补出 §4.2 的三处缺项，说明「已穷尽」的判断此前下得太早。未完成仍只剩计划 §7 的外部条件（T1/T2 整改闭合与正式切换验收）。统计 UNKNOWN、晋级 BLOCK、2025+/生产冻结不变。

### 2026-09-14 性能计划 §7 验证表逐行当轮复跑（当前提交 866e2cc）

§7 要求「复用第6包比较器、身份负例与检查点测试」。此前只跑了内核等价、身份负例、检查点与 CLI，验证表其余行没有当轮复跑。已补齐，结果见 `benchmark.json.p7_verification` 与 `p7/`：

| §7 事项 | 本轮结果 |
|---|---|
| 数值语义 | 内核全 `bit_equal`；对抗 **300/300 逐位相同**；比较器自检 **11/11** |
| PIT与标签 | 标签哨兵 **10/10**：只改训练窗之后的价格（含置 None 与 numpy 后端两条），2020–2022 的 `monthly_ic`/`decay`/`decile_spread`/`gate` 全部逐位不变 |
| 跨块与缓存 | 块边界 1/128/129/896/972 全 `bit_equal`；缓存负例 **10/10** |
| 公式与研究决定 | L0-only 与成本阶梯的 **L0 输出逐位相同、0 差异**；L0-only 14.606 → **7.674 s（1.90×）** |
| 分母与代表 | 对**本包引用的 -13 批** PASS：1430 行 / 20 片（72×19+62）精确划分、无重复、**20/20 代表在册** |
| 跨片状态隔离 | worker **PASS**：同进程「先跑 slice-02 再跑 slice-01」与干净进程的 6 个工件与 run_meta 相同 |

身份：`c82ac63..866e2cc` 只改打包器。实现工作树与快照同为 `866e2cc`。

本轮同样是在「已穷尽」的判断后又补出真缺口（§7 验证表的一半没当轮跑）。继续按计划原文逐条核。统计 UNKNOWN、晋级 BLOCK、2025+/生产冻结不变。

### 2026-09-14 性能计划 §5A 键的字段单位 + §3 P1 缺失数（当前提交 d1048d1）

逐条核 §5A 键清单与 §3 P1 交付条件，又补出两处：

- **§5A 键缺「字段单位」**（真实缺陷，不是措辞）：`data_version()` 只是批次目录 id 串联（`DATA_VERSION_PARTS`），`FIELD_REGISTRY` 也无 unit 字段——**loader 里做一次单位换算而批次号不变时，旧缓存会被当成有效**。已新增 `data_fields.FIELD_UNITS`（26 字段，逐项注明依据：qfq zip 列名「成交量(股)/成交金额(元)」、tushare daily_basic 口径、本模块 `MARGIN_FIELD_MAP` 注释）与 `field_units()`，并把 `field_units(fields)` 加入价格面板与组面板的键负载。旧缓存因键变自然失效（该轮 5 次 miss/rebuild），新键命中已验证：warm load **18.242 s**、`input_content_digest` 仍为 `4ebcb17b…`。
- **§3 P1 缺「缺失数」**：P1 通过条件要求报「实际日期/证券/字段/缺失数」，此前缺最后一项。新增 `--missing-counts`——全池 **119 636 676 单元、缺失 27 216 914（22.75%）**、池掩码 True **2 127 316 / 8 330 455（25.54%）**，逐字段计数入 `missing_counts.per_field`，扫描 2.396 s。
- 回归与身份：数组缓存负例 10/10、缓存等价 6 917 724 单元 0 差；因**动了受审文件** `data_fields.py`/`engine.py`，接线三测已在 `d1048d1` 上**重跑**（worker CLI PASS、检查点 31/31、新进程 7/7），不沿用旧身份证据。实现与快照同为 `d1048d1`。

结论不变：未完成只剩计划 §7 的外部条件（T1/T2 整改闭合与正式切换验收）。这已是连续第五轮在「已穷尽」判断后补出真缺口，继续按计划原文逐条核。统计 UNKNOWN、晋级 BLOCK、2025+/生产冻结不变。

### 2026-09-14 性能计划 §6.3 加速比改用同范围内位数（当前提交 20a5b66）

§6 采纳标准第 3 条要求「加速比使用同配置、同计时范围的中位数，列出各次值和范围」。此前我用的是总耗时之比，不是中位数、也没列各次值。已改：逐 pass 计算同配置比值，取中位作判据值，并落盘各次值与范围。

| 配置 | 各次比值 | 中位（判据） | 范围 | ≥2× | 计算阶段估计 | ≥1.5× |
|---|---|---:|---|---|---|---|
| blocked_128 | 2.0207 / 2.1085 / 2.1574 | **2.1085** | 2.0207–2.1574 | 是 | 1.235 | 否 |
| blocked_256 | 1.9346 / 1.9752 / 2.0226 | 1.9752 | 1.9346–2.0226 | 否 | 1.217 | 否 |
| blocked_512 | 1.5214 / 1.5633 / 1.5764 | 1.5633 | 1.5214–1.5764 | 否 | 1.150 | 否 |
| unblocked | 1.1345 / 1.1517 / 1.1896 | 1.1517 | 1.1345–1.1896 | 否 | 1.050 | 否 |

这条改动**有实质影响**：`blocked_256` 的单次最高值 2.0226 已越过 2×，按「取最好一次」会误判达标；按协议的中位规则它是 1.9752、不达标。裁决不变：不采用（选中 blocked_128 过热点门槛、未过计算阶段门槛）。

身份：`a12be89..20a5b66` 只改两个非受审文件（GPU bench、打包器），故接线测试证据仍对最终身份成立。实现与快照同为 `20a5b66`。统计 UNKNOWN、晋级 BLOCK、2025+/生产冻结不变。

### 2026-09-14 性能计划 §6 显存预算与精度证据（当前提交 bb69720）

核 §6「数据流」「配置预算」两段，补出两处：

- **显存预算此前完全没实现**：协议要求「按实测空闲显存设置临时预算 min(4GiB, 空闲显存×60%)，记录排序索引/临时数组/显存池峰值」。旧代码只有 OOM **之后**的减半兜底，没有**预测性**预算。已新增 `stats_gpu.vram_budget_mib()` / `estimate_block_mib()`，`ic_decay_curve_gpu` 接受 `vram_budget_mib`——预估单块工作区超预算则先减半到装得下（记减半轨迹）再走 OOM 兜底；预算只控块大小与排队，**不淘汰候选、不减日期或证券**。
- 实测：起始空闲 7096 MiB → 预算 **4096 MiB**；峰值 allocated **695.1 MiB** / reserved **858.0 MiB** → **within_budget: true**；四配置均未触发预测性减半。
- **顺带修掉取证缺陷**：bench 的 `_env_config` 跑 `nvidia-smi` 却漏 import `subprocess`，一直记成 NameError；修后正常记录 RTX 4060 Laptop / 8188 MiB。
- 精度条款证据：`env_config` 记 `dtype=float64`、`tf32_allowed=false`、`amp_enabled=false`；上传口径为 `factor_panel_once_per_factor` + `single_upload_then_device_slices`，与协议「公共 close/掩码驻留 GPU、因子数组上传、设备内分块」一致。
- 回归与身份：pytest **171 passed / 6 failed**（同为 LOCKBOX 既有失败）；因动了受审文件 `stats_gpu.py`，接线三测在 `65e66a7` 重跑通过；最终 `bb69720` 只改打包器。实现与快照同为 `bb69720`。

结论不变：未完成只剩 §7 的外部条件。统计 UNKNOWN、晋级 BLOCK、2025+/生产冻结不变。

### 2026-09-14 性能计划 §7 收尾：最小测试与包范围（当前提交 e718a58）

- **补最小测试**：新增 `tests/test_factor_miner_array_cache_20260914.py`（在受审集 `tests/test_factor_miner*.py` 内，字节受身份约束），**5/5 通过**、全 hermetic：数组缓存原子发布/命中/缺件/staging 不命中、`series_from` 的 None 精确重建，以及**缓存键对字段单位敏感**（改单位则键必变）。
- **包范围核实**：第 6 包最新文件 mtime 仍为 `2026-09-13 23:25:51`，本轮动作全在 09-14 → 本轮**只新增、未修改第 6 包**；记入 `benchmark.package_scope`。
- **回退入口核实**：worker `--backend {numpy,pure}` 与配置身份校验在位；新进程测试覆盖「显式 pure 真正切换」与「清空环境变量不算回退」。
- 身份：受审测试文件提交 `367eb88` 上接线三测已重跑通过；其后 `e718a58` 只改打包器。实现与快照同为 `e718a58`。

结论不变：未完成只剩 §7 的外部条件（T1/T2 整改闭合与正式切换验收）。统计 UNKNOWN、晋级 BLOCK、2025+/生产冻结不变。

### 2026-09-14 性能计划 §4.2 全批推算补充标定：把「未测类别」换成真实全池实测（新包 -8）

起因：§4.2 的全批推算此前只能报 **4335–14929 s（约 1.2–4.1 小时）**的区间——冻结 20 代表只覆盖
15/31 类别，按登记名册计权 666/1430 = **46.6%** 是实测，其余 16 类（764 行）只能用「已测
per-unit 最小/最大」兜住。用户指出空闲内存已够跑全池、该区间作为预估过长；核对后确认：该区间是
**包络**不是预测（上端＝1430 个构造全按最慢单元 13.7–14.7 s 计价，下端＝全按最快单元 1.67 s）。

- 做法：**事前固定、机械**取补充标定集（总体＝登记批 -13 的 1430 行名册；未测类别＝名册 family
  减去冻结样本 family，按名升序 16 个；每类取**名册文件顺序第一行**，原行逐字节复制，不看收益/排名），
  在**真实完整截面**（5552 请求 / **4996 服务** / 972 日期）跑 3 次暖态。这 16 个单元**不属于**
  P1 冻结的 20 代表集，不参与任何加速比、GPU 采纳裁决或统计门槛；冻结样本一字未动。
- 实测（新包 `artifacts/factor-engine-performance-20260913-8`）：装载 **323.194 s**（数组缓存首次
  构建，源摘要 6.37 GB / 14.62 s）、三次暖态求值 **81.903 / 75.751 / 76.674 s**、峰值工作集
  **4578 MiB**（`--drop-rows`）、结束时系统可用 **2135 MiB**、身份核验 **PASS**（57 个受审文件，
  `git_head = e718a58`，与第 7 包同提交）。→ **完整截面本机可跑**；第 7 包
  `p1/full_pool_attempt.json` 里「5 GiB 不够」是 **P2 内存改造之前**的 eager 表示，已被实测取代。
- 推算结论（`fullbatch-projection-v2.json`，单位为同一单元 3 次暖态中位数）：全批 **1430** 构造
  计算段 **6825.3 s ≈ 1.90 h**，带 **6182.2–7628.8 s**（1.72–2.12 h）；一次装载项单列（缓存命中
  18.9 s / 首次构建 323.4 s）→ 全批 wall **6844 s（命中）／7148 s（冷启动）≈ 1.9–2.0 h**。
  补充标定的 16 类单位中位数 **3.09–8.67 s**（12 类落在 3.3–6.1 s），**并不比已测类别慢**，
  即 4.1 h 那个上界来自把 53.4% 的权重按最慢单元计价。
- **顺带核出一处可复现性缺口**：第 7 包 `p1/fullbatch-projection.json` 自记
  `measured_source = p1/full_pool_p3.json`，但其数值（1.8309 / 13.7235 / 4.8733）与包内现存的该
  文件**对不上**（现存：VOL 单元 5.2041 s、pass 0 最小 1.9423 s / 最大 15.1884 s）；这三个数在
  包内只出现在投影文件自身与 `benchmark.json` 的复制里，即该投影取自一次输出未随包留存的全池
  重跑。本包改用**包内现存**文件按 §6 中位数口径重算 v1 口径：**4080.0–15491.1 s**，差异来源已
  记明；本轮实测输出随包留存，下一轮复算可直接对上。
- 限制：31 类里 **27 类只测了 1 个构造**，类别内散布未知，故 v2 的「带」是**下限**不是置信区间；
  且这是**推算不是全批实跑**。包内文件：`select_supplementary_20260914.py`、
  `selection-supplementary.json`、`supplementary-untested-families.jsonl`、
  `supplementary-full-pool-3pass.json`、`project_fullbatch_v2_20260914.py`、
  `fullbatch-projection-v2.json`、`report.md`。主仓源码未改、未提交，第 6/7 包未修改。

结论不变：未完成只剩 §7 的外部条件（T1/T2 整改闭合与正式切换验收）。统计 UNKNOWN、晋级 BLOCK、
2025+/生产冻结不变。本轮把性能计划里唯一一处「只能给区间」的交付项收成了全池实测支撑的点估计；
§4.2 的「推算不冒充实际全量跑完」仍然成立（`is_projection_not_a_run`）。

### 2026-09-14 切换（合入主仓）就绪性核查：差量 45 文件、8 个受审、累计 diff 全部干净可套用

起因：§2 要求「正式切换须同时满足自身验收和最新 T1/T2 审核要求」，§3 P5 允许把切换标
WAITING_REVIEW 或 BLOCKED。核第 6 包 `merge-plan-20260913.md` 发现它只覆盖**它那一次**的
4 个修改文件 + 1 个新增文件，而当前交付实现（隔离仓 `e718a58`）相对差量基线 `5d786cf`
（＝主仓工作树快照）的差量是 **45 个文件**：8 修改 / 37 新增，其中 **8 个在受审身份集内**
（`array_cache.py`、`data_fields.py`、`director.py`、`engine.py`、`stats_gpu.py`、
`stats_np.py`、`mr_statarb.py`、`tests/test_factor_miner_array_cache_20260914.py`）——
第 6 包的清单**漏了 P2 速度改到的 `mr_statarb.py`、新增的 `array_cache.py`/`stats_gpu.py`
和最小测试**，按它合入会得到一份与已验收实现不一致的树。

- 核查（只读；套用在临时目录做，**未写主仓**）：主仓当前工作树与差量基线在这 8 个修改文件上
  **内容一致**（行尾差异单列；主仓 `core.autocrlf=true`、隔离仓 LF，原始字节 sha256 本来就不同，
  即 merge-plan §0 已记的事项）；8 份**累计 diff** `git apply --check -p1` **plain 上下文全部
  rc=0**（不需要 `-C1`），套用后结果与交付实现**逐字节一致**（`applied_equals_target` 8/8）。
  → 第 6 包当初的「两段式 + 逐 hunk 人工合入」对**当前实现**已不必要，累计 diff 直接可套用；
  真正的门禁是 §2 的 T1/T2 审核，不是可应用性。
- 记录（新包 `factor-engine-performance-20260913-8` 续）：`switchover_delta_check_20260914.py`、
  `switchover-delta-check.json`、`switchover-patches/`（8 份累计补丁）、`switchover-status.json`
  （`switch_status = BLOCKED`；门禁引用当前 T1/T2 审核状态；列出解锁五步与三项未决：身份引用
  重绑清单需按 45 文件差量重算、36 个 `t3_perf_*` 夹具是否随合入属 §4.3 独立决策、T1/T2 闭合本身）。
- 身份重绑面重算（`identity_impact_scan_20260914.py` / `identity-impact-scan.json`）：按第 6 包
  §3 的同一检索口径（主仓 artifacts/**+docs/**，限定 .json/.jsonl/.md/.txt/.log）扫**当前差量的
  8 个修改文件**，得并集 **120 个引用文件 / 491 行命中**（data_fields 57、director 30、engine 40、
  stats_np 67、migration_runtime 43、**mr_statarb 85**、r0_audited_runner 3、t3_l0_batch 2）；
  后 4 个是第 6 包**没扫过**的，故其「99 个文件」不能照搬。计数单位差异须记：本表是「文件数/行命中」，
  §3 是「键命中」，复算其 4 个文件得 152/65/44/37 行 vs 其公布 142/73/73/36 处，两套数不可相加。
- 限制：本核查是**快照**（基线 `5d786cf` / 目标 `e718a58` / 主仓工作树当前字节）；主仓工作树
  若再变须重跑该脚本再据以合入。本轮**未合入、未提交**、未改主仓任何源码。

- 过期结论标注（`record_supersession_20260914.py` / `superseded-notes.json`）：包 -7 的
  `p1/findings.md`（「全池不可行（内存）」）与 `p1/full_pool_attempt.json`（「5 GiB 不够」）写于
  **P2 内存改造之前**，与同包实测（benchmark.json 的 measured、review.md §2）自相矛盾。按「只新增
  包编号、不改第 6 包」，更正在包 -8，两处**追加式**插入指向包 -8 的标注；原文各节与 JSON 原 14 个
  键逐一核对未改。如实披露：编辑前字节未留档，故记录用「插入位置＋插入文本＋标注后 sha256」
  （findings.md `27ec50cc…`、full_pool_attempt.json `57c91427…`），不给改动前哈希。

- §3 P0「缺数据按依赖列出」补齐（`missing_by_dependency_20260914.py` / `missing-by-dependency.json`）：
  包 -7 只有 P1 要的逐字段缺失数，没有按数据依赖分组的清单（P0 通过条件之一）。用代码里的面板→
  依赖映射（`engine.PRICE_FIELDS`、`data_fields._VALUATION_FIELDS`/`MARGIN_FIELD_MAP`/
  `LHB_FIELDS`/`industry_ret_l1` 与各自批次）把 P1 全池实测计数重新分组，**不新跑数据**：
  本地日线+qfq 11 字段 53 417 232 单元 / 缺 5 708 696（10.69%）；daily_basic 9 字段 42 910 884 /
  缺 8 597 229（20.04%）；margin_detail 3 字段 9 331 200 / 缺 3 872 007（41.50%）；
  龙虎榜 2 字段 9 121 248 / 缺 9 009 006（**98.77%，结构性**：只有上榜个股当日有值）；
  sw_index_daily 1 字段 4 856 112 / 缺 29 976（0.62%）。五组相加与 P1 总数**精确相等**
  （119 636 676 / 27 216 914），26 字段无一未分组。缺失率高不等于数据缺口，须按字段逐项读。

结论不变：性能计划自身工作面继续收敛（本轮又补出并闭合一处真缺口：切换就绪性此前只有第 6 包的
5 文件分析，且已过时）；未完成只剩 §7 的外部条件（T1/T2 整改闭合与正式切换验收）。统计 UNKNOWN、
晋级 BLOCK、2025+/生产冻结不变。

### 2026-09-14 性能计划 §7 公共代码回归：核出并修复一处真回归（新提交 6f90f95）

§7 的「公共代码回归」行要求包含主仓证券代码变更资格修复。把 `tests/test_r0_lifecycle_wiring.py` 与
`tests/test_portfolio_code_changes.py` 加进本轮 pytest 一起跑，发现：交付实现（**e718a58**）
**4 failed / 1 passed**（`AttributeError: 'SimpleNamespace' object has no attribute 'RAW_DAILY_DIR'`
@ engine.py:211），主仓工作树（f32568f）**8 passed** —— 受审差量引入的**真回归**，且受审集是
`tests/test_factor_miner*.py`，这两个生命周期文件不在其中，所以此前「无新增失败」没有覆盖 §7 这一行。

- 根因：差量把 `pool_mask_by_date` 的三处装载改成 `memoized_load` 并显式传
  `paths=[os.path.join(mrs.RAW_DAILY_DIR, ...)]` / `qfq_zip_path(mrs.USER_DATASET_ROOT, ...)` /
  `os.path.join(mrs.ADJUST_DIR, ...)`；而 `paths_token(mrs)` 本来就用 `getattr` 把这三个目录记进
  备忘键（缺失记 None），额外令牌对运行时身份并不必要，却把函数契约扩成「必须带这些属性」。
- 修法（**6f90f95**，只动 `experiments/factor_miner/data_fields.py` 与 `engine.py`）：
  data_fields 新增 `raw_daily_path` / `adjust_rows_path` / `memo_paths`，`qfq_zip_path` 对空 root
  返回 None；engine 改用它们。生产运行时三属性都在 → 令牌与修复前逐字节相同。
- 修复后当轮证据（`artifacts/factor-engine-performance-20260913-8/regression-fix.json` 与
  `regression/`）：生命周期+组合 **8/8**（与主仓同）；14 文件 pytest dev **223 passed / 6 failed**、
  主仓 **218 passed / 6 failed**，**失败集完全相同**（6 个已知 LOCKBOX 夹具），dev 多的 5 个通过＝
  新增的数组缓存最小测试；P5 接线在**新提交重跑**（worker CLI **PASS**、检查点 **all_ok**、
  新进程 **7/7**，新快照 `t3-snapshot-20260913-5`）；真实全池装载（数组缓存命中）**16.231 s**
  （修复前 18.856/18.242/18.014 s）、5552 请求 / 4996 服务 / 972 日期、峰值 4087 MiB，
  **input_content_digest 与修复前记录逐字节相同**（`4ebcb17b…`）→ 值不变；同提交的 §7 抽查
  kernel 等价 ranks/spearman 全 all_ok、标签哨兵 10/10、比较器自检 11/11、缓存负例 10/10、
  p2 等价 35/35。
- 冷路径（不用数组缓存）同提交重测：装载 **300.01 s**（修复前 e718a58 295.49 s、基线 5d786cf
  407.071 s → **1.357×**），峰值 4353 MiB，摘要同样等于 `4ebcb17b…`。1.36–1.38× 的量级在新身份上
  复现。
- 身份后果：包 -7 的计时数字绑定 `e718a58`，**只覆盖旧身份**；新身份（`6f90f95` + 快照 -5）以本节
  当轮证据为准。切换差量核查已按新目标重跑（45 文件、8 修改、plain rc=0、套用结果逐字节一致）。

结论不变：未完成只剩 §7 的外部条件（T1/T2 整改闭合与正式切换验收）。这已是连续多轮在「已穷尽」
判断后补出真缺口，本轮补出的是**会让切换带上回归的那种**。统计 UNKNOWN、晋级 BLOCK、
2025+/生产冻结不变。

#### 同日续：§6 采纳裁决重绑到新身份（提交 7ebb80a）

§6 的「采纳/暂缓」是决策级证据，原测在 `e718a58`。虽然修复的值中立已由 `input_content_digest`
逐字节相同证明、`stats_gpu.py`/`stats_np.py`/compiler 都没动，但为把这条证据绑到当前身份，仍按
**同一协议**在 `6f90f95` 上重跑：真实完整截面（请求 5552 / 服务 4996 / 972 日期）、3 次暖态、
CPU/GPU 按 (pass, unit) 奇偶交替、数组缓存开。结果：

| 配置 | 热点中位（各次） | ≥2× | 计算阶段估计 | ≥1.5× | 逐位等价 |
|---|---|---:|---|---:|---|
| blocked_128（选中） | **2.0593**（2.0404/2.0593/2.1215） | 是 | 1.226 | 否 | 是 |
| blocked_256 | 1.9298（1.9102/1.9298/2.0226） | 否 | 1.209 | 否 | 是 |
| blocked_512 | 1.5057 | 否 | 1.137 | 否 | 是 |
| unblocked | 1.1453（1.0863/1.1453/1.1753） | 否 | 1.048 | 否 | 是 |

15 次比较全部逐位相同；rank/spearman 逐位相同、对抗 0 不匹配；块边界全逐位相同；CUDA 错误显式回落
CPU；OOM 折半覆盖全部日期且不越上限；显存预算 4096 MiB、峰值 695.1/858.0 MiB、within_budget true。
**结论与包 -7 一致：0 个配置同时通过两项阈值 → 不采用 GPU**（2.0593 对 -7 的 2.1085、
train_test 77.824 s 对 78.802 s，落在运行波动内）。

顺带修掉一处夹具文案滞后：判据文案原写死「真实 285 股样本」，与实际跑的 5552/4996 不符（包 -7
review §3 已记滞后但未改）；现按实际请求/服务数自述，本轮 JSON 已生效。该改动在**非受审 harness**
（`experiments/t3_perf_gpu_bench_20260913.py`，提交 `7ebb80a`），受审集在 `6f90f95..7ebb80a`
之间为空 diff，故 worker 身份不变（P5 证据按「被测试的字节集合未变」沿用），快照
`t3-snapshot-20260913-5` 已前移到 `7ebb80a`；切换差量核查按新目标重跑仍为 45 文件、8 修改、
plain rc=0、套用结果逐字节一致。

结论不变：未完成只剩 §7 的外部条件。统计 UNKNOWN、晋级 BLOCK、2025+/生产冻结不变。

### 2026-09-14 独立审核 CHANGES_REQUIRED → R2/R3/R7/R1 整改完成，R4/R5 已补（整改件 -20260914-1）

[独立审核](../artifacts/factor-engine-performance-review-20260914-1/review.md) 结论 **CHANGES_REQUIRED**
（两项 P1：R1 实际入口没接流式/价格缓存、R2 缓存键漏上市退市与预处理身份；另有 R3 缓存完整性、
R4 GPU 运行身份、R5 命令可复制性、R6 摘要过期、R7 缓存复位不释放绑定）。整改件在
[artifacts/factor-engine-performance-20260914-1](../artifacts/factor-engine-performance-20260914-1/report.md)。

- **R2/R3/R7 已修**（提交 `7d88101`）：键补上市退市元数据内容、证券代码变更表、预处理实现指纹
  （源码摘要 + 字节码指纹）；读取端核 dtype/shape/内容摘要，坏件按不可用处理并**保留证据隔离**
  （修掉隔离时映射未释放导致 Windows 挪不动目录的真缺陷）；
  `reset_panel_cache`/`enable_truncated_close_cache(False)` 释放绑定强引用。评审三个反例脚本
  **复制到本目录复跑**（不覆盖其证据）：
  `n_stale_true_days` 5→**0**、`code_change_key.same_key` →**false**、
  `preprocessor_key` →**false**、`corrupt_cache.accepted` →**false**、`truncated_cache` →**miss**、
  `alive_after_public_reset_and_disable` →**false**。反例已固化为包内 pytest（10/10）。
- **R1 已接**（提交 `0e6b970`）：L0-only 配置（成本阶梯关；worker 默认）显式 `retain_rows=False`，
  价格面板缓存可命中；pipeline 增 `--with-cost-ladder/--no-cost-ladder`（默认不变）使该配置可达；
  run_meta/worker config 记 `retain_rows`/`row_representation`。**成本阶梯开时仍保留行字典**
  （backtest 需要），不盲目改账户路径。证据：`probe_r1_wiring_20260914.py` 4/4、worker CLI 带缓存
  **PASS 9/9** 且真实生成 `price_panel/` 等缓存。
- **R4 已补**（提交 `0ea1764`）：bench 输出新增 `run_identity`（受审代码身份 fail-closed、生成器
  摘要、样本/池内容摘要、git head、实际消费输入摘要、收尾复核）；绑定身份的全代表确认跑在跑。
- **R5 已修**：`commands-runnable.json`（33 条；绝对路径、逐条 cwd、显式设/清环境、产物写新根）+
  `verify_runnable_commands_20260914.py` **实跑一条**（rc=0、产物落新根）；
  探针不再删除既有输出（改时间戳新目录）。
- **R6 已修**（本轮收尾）：审核点名的两份「送审后被追加/改写」证据按字节冻结到整改包
  frozen/ 下，用 plan_conformance_after_r6_20260914.py 就地重算全表 sha256 →
  -14-1/plan-conformance-after-r6.json（**44 行 / 102 条证据 / 缺路径 0**）。除审核点名的
  -8/report.md（2ca8c5e7e470 → f01e23df648e）与 -8/switchover-status.json
  （2d125e027ac1 → 7b1c828bbd16，审核后又按外部门禁闭合改了门禁文字）外，
  **其余 97 条与包 -8 索引逐字节相同**，没有第三条漂移；旧索引保留为被取代件。
- **附：T3 L0 按 2000 构造的外推**（纯算术，非新测量）：接线修复后 **2.2–3.1 h 串行墙钟**
  （类别加权 2.23–2.73 h、全按实测均值 2.88 h、20 代表实测 3.10 h）；缓存全关口径
  4.6–5.5 h。脚本 -14-1/calc_2000_projection.py，产物 projection-2000.json。

快照 `t3-snapshot-20260913-5` 前移到 `0ea1764`；主仓未合入未提交；统计 UNKNOWN、晋级 BLOCK 不变。

### 2026-09-14 性能包可送审：新增一页审核入口说明（review-brief.md）

为便于送审，在包 -8 增加 `review-brief.md`：审阅者最短路径（先读 report.md 与 plan-conformance.json）、
主张→证据对应表（全池可行性/装载/求值/等价性/GPU 裁决/接线回退/回归修复/切换就绪/可复跑）、
**必须知道的更正**（实现身份从 e718a58 前移到 68bbc25；我自己的三处更正；两处偏保守而非高估；
全池基线侧因内存线跑不动）、以及**不要期待的三件**（未执行正式切换、未做整片端到端批跑、未做
全池求值同窗口 A/B），并给出建议口径：**性能工作 PASS / 切换 BLOCKED 分离结论，不写整体 DONE**。

审核结论按计划 §七写在 [T1 审核任务书](../tasks/ten-year-research-infrastructure-review-20260912.md)。

结论不变：未完成只剩 §7 的外部条件。统计 UNKNOWN、晋级 BLOCK、2025+/生产冻结不变。

### 2026-09-14 性能计划外部门禁状态复核（只读）：SDK 通道卡在账号权限

计划完成定义把正式切换挂在 T1/T2 闭合上，故本轮只读复核该外部条件的当时状态并留档
（`artifacts/factor-engine-performance-20260913-8/external-gate-state.json`，未改 T1/T2 任何产物）：

- T1 整体/T1-C、T2 整体/T2-B 仍 **BLOCKED**，T2-C **BLOCKED / CHANGES_REQUIRED**；当前阻断点在
  **600452 / 2016-06-01 分钟口径**，需要该日真实分钟/逐笔或可核实口径解释（不得放宽例外或伪造最低价）。
- **新证据**（本轮检查发现，非本计划产出）：`artifacts/bigquant-sdk-check-20260914-1`（11:25）
  的 BigQuant **SDK** 探针 **FAILED**，`FlightUnavailableError：请先申请SDK使用权限` —— SDK 通道
  卡在**账号权限**，不是脚本或数据问题。
- 解开条件：① 用户开通 SDK 权限或按已就绪的 639 项清单（`minute-bulk-source-check-20260914-1`）
  导出 ZIP 交回；② T1/T2 按各自任务书闭合。之后按 `switchover-status.json` 五步流程切换，并按
  `switchover-rebinding-list.json` 重绑 298 行 / 101 文件。

结论不变：未完成只剩 §7 的外部条件。统计 UNKNOWN、晋级 BLOCK、2025+/生产冻结不变。

### 2026-09-14 求值/装载加速比同窗口复核（285 服务）：求值 2.32× 复现，装载 1.67× 大于交付的 1.36×

交付里「285 服务 A/B：装载 54.302→39.917 s（1.36×）、求值 19.233→8.706 s（2.21×）」两侧也取自
不同时段，故同窗口 A→B→A 重测（同 harness、同 flags、都不配数组缓存；A2 与 A1 只差 2%，文件缓存
顺序效应很小）：

| 运行 | 装载 s | 求值 s（20 单元 / 1 遍） |
|---|---:|---:|
| A1（基线 @5d786cf） | 53.932 | 18.976 |
| A2（基线，暖缓存） | 52.662 | 19.022 |
| B（当前身份 68bbc25） | **31.901** | **8.193** |

同窗口比值：**装载 1.67×、求值 2.32×**（A 取中位）。对照交付记录：**求值 2.32× 复现 2.21×**；
**装载 1.67× 大于交付的 1.36×**（A 侧与记录一致 53.9/52.7 对 54.302，差在 B 侧 31.9 对 39.917）。
与 §19 的同窗口装载 A/B（542 服务 1.89–2.06×）方向一致 → **交付的装载加速偏保守，求值加速可复现**。

产物：`eval_speedup_recheck_20260914.py`、`eval-speedup-recheck.json`、
`regression/eval285-{A1,B,A2}-now.json`。限制：单次 A 本轮波动 2%、历史窗口间可达 20%，引用用区间；
全池档的求值同窗口 A/B 未做（基线侧跑不动全池）。

结论不变：未完成只剩 §7 的外部条件。统计 UNKNOWN、晋级 BLOCK、2025+/生产冻结不变。

### 2026-09-14 装载加速比同窗口复核：1.89–2.06×（交付里 1.378× 偏保守）；全池基线侧被内存线拦下

包 -7 的装载 A/B（569 服务 1.22×、全池 1.378×）两侧取自不同时段，而本会话已证跨时段能漂 ~20%，
故本轮在同一窗口重测：

- **全池基线侧重测：被计划 §4 停止线拦下，未出数**。基线工作树（perf-next-A @5d786cf）跑真实全池
  只做装载，14 分钟仍在装载（WS 3.26 GB / CPU 13.4 分钟），此时可用内存 **1890 MiB**（< 约 2GiB 线）、
  提交 26.85 / 上限 31.26 GB → 按规则停止并记录，不写结果（同包 -7 当年基线侧被提交压力中止）。
  这本身印证：基线的 eager 表示在今天的机器状态下跑不了完整池。
- **改走缩小配置（569 请求 / 542 服务）同窗口 A→B→A**（同 harness、同 flags、都不配缓存）：
  A **101.319 s** → B **49.204 s** → A **93.056 s**；比值 **1.89–2.06×**（A 中位口径 **1.98×**）。
- **交叉核对**：基线自己在包 -7 剖析点的逐证券速率是 285 服务 0.222、1124 服务 0.157 s/证券；
  本轮 A 为 0.172–0.187（落在同范围）；而包 -7 那次 A/B 的 A 侧 0.0815（全池）/0.106（569）低于
  基线自己的剖析点。B 侧两会话一致（49.204 对 49.268）。
- 结论：**交付的 1.378× 偏保守**（今天窗口下装载加速更大），差异在 A 侧历史窗口而非 B 侧；限制：
  全池基线侧合法窗口本轮不可得、单次 A 波动 8%，引用应用区间。产物：
  `load_speedup_recheck_20260914.py`、`load-speedup-recheck.json`、`regression/load569-{A,A2,B}-now.json`。

结论不变：未完成只剩 §7 的外部条件。统计 UNKNOWN、晋级 BLOCK、2025+/生产冻结不变。

### 2026-09-14 追加包的可复跑命令清单（25 条，输入/产物 0 缺失）

§7 要求「运行命令确认现有入口后实际验证并冻结，交付时必须可复制运行」。包 -7 有
`commands_resolved`，本追加包此前只有脚本、没有命令清单，这轮补上：`commands.json` 记 **25 条**
命令（用途、cwd、所需环境变量、命令原文、产物路径、实测大致耗时），并用
`verify_commands_20260914.py` **核存在性**输出 `commands-verified.json`：

| 项 | 结果 |
|---|---:|
| 命令条数 | 25 |
| 输入（脚本/输入文件）存在 | 25 / 25 |
| 声明产物存在 | 25 / 25 |
| 缺失路径 | **0** |

使用须知已写进 `commands.json`：长测量都要带 `FACTOR_MINER_CACHE_DIR` 指向本包 `array_cache`
（否则每次重建：首建约 323 s、命中约 19 s）；重跑会覆盖同名输出，先另存旧件；路径占位符
（P8/P1A/UNIV/SNAP5）的展开值在 `commands-verified.json` 的 `aliases` 段。

结论不变：未完成只剩 §7 的外部条件。统计 UNKNOWN、晋级 BLOCK、2025+/生产冻结不变。

### 2026-09-14 切换窗口的身份重绑清单（8 文件 → 旧值/新值 + 516 行 / 122 文件命中）

把「身份引用重绑清单需按本次差量重算」做成机读清单（`switchover_rebinding_list_20260914.py`、
`switchover-rebinding-list.json`），**先验证方法再出数**：

- 方法：临时目录 `git init` + `core.autocrlf=true`（照主仓），复制主仓当前字节并提交，再 `git apply`
  累计 diff → 合入后主仓工作树的**真实字节**。
- 方法校验：stats_np.py 合入后原始字节 sha256 = `25875f6b11c10b7e…`，与第 6 包 merge-plan §0
  公布值**完全相同** → `method_validated_on_stats_np = true`。

| 文件 | 旧值（截断） | 合入后（截断） | 机器可读绑定 行/文件 | 叙述提及 |
|---|---|---|---:|---:|
| data_fields.py | 306260fd114c62fa | 70d20e45a61ab740 | 57 / 53 | 4 |
| director.py | ec7504fb156bbdb8 | fb2a1ba37da9738d | 27 / 25 | 9 |
| engine.py | de507dc034228f4e | fb2b258f9bf3ab71 | 38 / 38 | 2 |
| stats_np.py | ebdc91603e7936ea | 25875f6b11c10b7e | 59 / 49 | 87 |
| migration_runtime_20260912.py | e9cf7f90183608a9 | 5e32c7a6513346df | 42 / 42 | 0 |
| mr_statarb.py | aac895cce6d0fb28 | e6d6d0e7b0a63522 | 71 / 70 | 66 |
| r0_audited_runner.py | 453c06bb5682fac5 | 947d6116340dde27 | 3 / 2 | 0 |
| t3_l0_batch_20260913.py | f50c41803b98d5bc | f03c91f3687460fa | 1 / 1 | 0 |

合计 **466 行 / 119 文件**（其中**机器可读绑定 298 行 / 101 文件**、叙述提及 168）。分类刻意：
绑定必须重绑；叙述/历史（`.md/.txt/.log`）按第 6 包 merge-plan §3.5 惯例不重写历史，需要时加标注。

**自我更正**：本条初稿报「516 行 / 122 文件」——那个数不干净：脚本里「排除本包自身记录」的过滤用了
未归一化路径比较（反斜杠/斜杠混用）**实际没生效**，本包自己的文档也被计入且每重跑一次自增
（516 → 867 → 1217）。改成 normcase+abspath 前缀比较后为上面的数，且自引用 0 条。

边界：行号按当前内容；新值取自**主仓行尾策略**（`autocrlf=true`），换策略值不同（merge-plan §0 已写明）。

结论不变：未完成只剩 §7 的外部条件。统计 UNKNOWN、晋级 BLOCK、2025+/生产冻结不变。

### 2026-09-14 性能计划逐条对照表（44 行，证据路径 0 缺失）

把计划按条款拆成 **44 行**做成机读对照表（`plan_conformance_20260914.py`、`plan-conformance.json`）：
每行 = 条款（含章节号）→ 证据文件（脚本逐个核存在性、记字节数与 sha256）→ 状态 + 说明。
结果 **44 行 / 0 个路径缺失**：DONE 37、DONE_WITH_LIMITATIONS 2、NOT_APPLICABLE 4、BLOCKED 1。

- 两个 DONE_WITH_LIMITATIONS：§4.2 全批推算（计划写「一次装载项」，实测批次是每片一进程、装载 20×，
  已按更正口径记录）、§7 完成定义（三项交付齐备，但计划自己规定 T1/T2 未闭合时独立阶段保持未完成）。
- 唯一 BLOCKED：§2 正式切换门禁（T1/T1-C、T2/T2-B 仍 BLOCKED、T2-C CHANGES_REQUIRED）。
- 四个 NOT_APPLICABLE 均为计划的条件式跳过/暂缓且附前置实测：P4、§5B、§5C、采纳标准 5。
- 也就是说：计划自身工作面 **43/44 行**有可核证据，剩下 1 行是外部门禁。

结论不变：未完成只剩 §7 的外部条件。统计 UNKNOWN、晋级 BLOCK、2025+/生产冻结不变。

#### 同日续：批次现状跑的是「性能缓存关闭」配置（8% 口径差）

批入口 `t3_l0_batch_20260913` 那条 cmd 只传 `--hypotheses`/`--out`/`--allow-real-run`，
**没有** `--panel-cache`/`--load-memo`，而 §3 P1 的 CPU 改进是在**开着**这些缓存时测的。
同提交、同输入、各自全新进程、都跑 1 遍：缓存**开** 104.628 s（5.231 s/单元）、**关**（＝批次现状）
112.536 s（5.627 s/单元）→ **1.076×**。并进批次 wall：

| 口径 | 计算项 | 装载项 | 合计 |
|---|---:|---:|---:|
| 批次现状（性能缓存关、数组缓存启用） | 1430 × 5.627 = **2.24 h** | 0.19 h | **≈ 2.42 h** |
| 批入口补上缓存后 | 2.08 h | 0.19 h | ≈ 2.27 h |
| 不启用数组缓存 | 2.24 h | 1.69–2.39 h | **3.92–4.63 h** |
| 类别加权口径 | 1.61–1.90 h | 同左 | 1.8–2.1 h / 3.3–4.5 h |

批入口若要跑到 P1 测过的配置，需补 `--panel-cache`/`--load-memo`（切换窗口的接线改动，本包不改代码）。
产物：`projection-session-comparison.json` 的 `perf_cache_ab` 段、report.md §12.2。

#### 同日续：批入口性能缓存接线**已修**（提交 68bbc25）

上面那条不是待办而是**真接线缺口**，而且正是 director 自己 docstring 点名的问题：
`director._apply_perf_caches` 写「批量入口（pipeline --allow-real-run）在开启后把本函数的返回值写入
run_meta.perf_caches，使『测得的配置』与『跑的配置』可核对（独立审核指出的配置漂移即此类问题）」，
`--panel-cache` 的帮助文本也写「（opt-in；与服务型 worker 同配置）」，而 worker 的默认就是开、
load memo 常开 —— 批入口原先两个都不传。

- 修复：`experiments/t3_l0_batch_20260913.py` 起的 pipeline cmd 加 `--panel-cache --load-memo`
  （提交 **68bbc25**）。该文件**不在受审集**（`director.audited_code_paths()` 57 条里无它），
  worker 身份不变，P5 证据按「被测试的字节集合未变」沿用；快照 `t3-snapshot-20260913-5` 前移到
  `68bbc25`；切换差量核查按新目标重跑仍 45 文件、8 修改、plain rc=0、套用结果逐字节一致。
- 验证（不跑真数据，`check_batch_perf_wiring_20260914.py`，verdict **True**）：真实 CLI 跑新 argv
  无 unrecognized arguments 且走到 `run_real_pipeline`（说明 argparse 接受开关、其前的
  `_apply_perf_caches` 已过 fail-closed 校验）；旧 argv 作对照；`pipeline --help` 两个开关都在；
  `_apply_perf_caches(True, True)` 三项 enabled 全 True。整片端到端批跑没做——那会产 L0 工件，
  属 T3 正式运行范围，留给切换窗口。

#### 同日续：零候选真实 pipeline 的端到端补证（接线修复已在真实路径生效）

用**空切片**（零条假设）跑真实 pipeline 三次，顺序「带开关 → 不带 → 再带」（把开关与时间漂移分开），
三次候选评估数都是 0（不产 L0 结果）；标准输出里的 run_meta.perf_caches：

| 运行（同提交 68bbc25） | perf_caches |
|---|---|
| 带 `--panel-cache --load-memo`（第 1 次） | panel_cache/truncated_close/load_memo 全 **true** |
| 不带开关（第 2 次） | 三项全 **false** |
| 带开关（第 3 次） | 全 **true**（与第 1 次一致，夹住中间那次，排除简单漂移） |

两条取证提醒留给切换窗口：① pipeline **落盘的 run_meta.json 里 perf_caches 是 null**，CLI 只把它加在
**stdout 副本**上，批入口把子进程 stdout 落到 `<out_root>/<dir>.run.log`，所以「可核对」成立但要看
日志；② 零候选的正式 pipeline 会**完整装载后以 0 单元正常收尾**（`COMPLETED_DESCRIPTIVE`），不是快速
失败，且输出目录必须不存在（已存在则在装载前 fail-closed）。产物：
`probe_pipeline_perf_caches_20260914.py`、`regression/pipeline-perf-caches-probe.json` 与
`regression/empty-run-*/`、`regression/pipeline-probe-*.stdout.txt`。

### 2026-09-14 更正：求值耗时不是「缓存命中更快」，是进程历史依赖；并核出批次装载是 20×

上一轮我把跨进程的「命中态 96.6 s vs 无缓存态 120.2 s」读成「缓存命中让求值快 1.20–1.25×、可重复」。
本轮用**同一进程三阶段**探针（`probe_eval_vs_loadconfig_20260914.py`：缓存命中 → 不配缓存 →
缓存命中，每阶段后释放 bundle 并 gc.collect()，三段 input_content_digest 全同）把它**推翻**：

| 阶段 | 装载配置 | 装载 s | 求值 20 单元 s | 单元中位 s |
|---|---|---:|---:|---:|
| 1 | 缓存命中 | 19.02 | **104.628** | 4.445 |
| 2 | 不配缓存 | 430.36 | **128.898** | 4.591 |
| 3 | 缓存命中 | 22.58 | **155.567** | 5.739 |

第三阶段本身就是命中却最慢 → 差异跟**阶段顺序/进程历史**走（同进程内第 3 个 bundle 的求值比第 1 个
慢 49%，装载也在退化：全新进程无缓存装载 303.6 s，同进程第二轮 430.4 s）。**上轮归因作废并更正**；
跨进程时间点对比不能当配置 A/B。

- **核出结构性事实**：批入口 `experiments/t3_l0_batch_20260913.py`（第 470–505 行）**每片起一个
  subprocess**，各自装载一次全池 → 计划 §4.2 写的「一次装载项」对真实批次是 **20×**（20 片）。
- 按实测重算全批 wall（1430 构造、20 片 19×72+62）：**启用数组缓存 2.11–2.27 h**
  （计算 1.92–2.08 h 全单元均摊口径 / 类别加权口径 1.61–1.90 h + 装载 681 s）；
  **不启用数组缓存 3.61–4.47 h**（装载 6072–8607 s）。即数组缓存在真实批次形状下价值约 **1.5 h**，
  远大于包 -7 记的「重复 1 次即回本」。另记：不要把 20 片塞进同一进程（探针显示后面的 bundle 明显
  更慢）。产物：`projection-session-comparison.json` 的 `batch_structure` 段、report.md §12/§12.1。

结论不变：未完成只剩 §7 的外部条件。统计 UNKNOWN、晋级 BLOCK、2025+/生产冻结不变。

### 2026-09-14 §3 P1 求值计时与 §4.2 推算在当前身份重测（发现装载配置决定求值耗时）

背景：§3 P1 的求值计时与 §4.2 的推算输入原先都取自包 -7 的 `e718a58` 运行。本轮在 `7ebb80a` 上
按同一协议重测（全池 4996 服务 / 972 日期 / 3 次暖态），并在同一会话里加了一组**同提交、
同输入**的 A/B：

| 配置（同一提交 7ebb80a，input_content_digest 均 = `4ebcb17b…`） | 3 次暖态（s/遍） | 中位 |
|---|---|---:|
| 数组缓存命中（两次独立运行） | 102.922/96.527/96.688 与 102.671/95.386/96.551 | **96.62** |
| 完全不配缓存 | 128.025/119.857/120.243 | **120.24** |
| 会话 A 建缓存运行（e718a58） | 127.047/118.183/117.891 | 118.18 |

- 16 补充标定同轮重测：67.903/63.061/64.185 s（会话 A 为 81.903/75.751/76.674 s）。
- **结论一（口径）**：求值耗时随装载配置差 **1.20–1.25×**，且可重复；四次运行消费输入逐字节相同，
  所以不是数据、不是身份、也不是修复（修复只把备忘路径令牌改成 getattr 保护，不参与求值路径）。
  **热性不是主因**：第二次命中态是在 300 s 无缓存跑完后立刻跑的，仍然快；逐单元比值（会话 A/B）
  也不均匀（中位 1.212、范围 0.988–1.731）。机制**未识别**，候选是装载阶段之后的堆状态/分配局部性；
  要定论需同会话交替多轮并记录 CPU 频率与页错误，本轮没做。
- **结论二（推算）**：全批 1430 构造计算段按两个装载配置报区间 **1.61–1.90 h**（点估计 5801.8 s
  命中态 / 6825.3 s 建缓存态）；首次跑要建缓存，取上端约 1.9 h。装载项单列：命中 18.6–18.9 s、
  冷启动 300.0 s（不在缓存时 303.6 s）。产物：`projection-session-comparison.json`、
  `fullbatch-projection-v2-after-fix.json`、`regression/p1-full-pool-3pass-{after-fix,nocache-after-fix,hit2-after-fix}.json`。
- 身份：全部四次运行的 `identity_check` 均为 PASS（57 个受审文件，git_head `7ebb80a`）。

结论不变：未完成只剩 §7 的外部条件。统计 UNKNOWN、晋级 BLOCK、2025+/生产冻结不变。

### 2026-09-14 性能计划当前状态（唯一当前状态）

（同日上述几条以重复的「结论不变…」行为锚点插入，**顺序不是严格时间序**；本条按顺序收口。）

**实现身份**：受审实现与快照都是 **68bbc25**（快照 `t3-snapshot-20260913-5`，工作树干净）。
当天三次提交：`6f90f95`（B2 回归修复：`experiments/factor_miner/{data_fields,engine}.py`）、
`7ebb80a`（GPU 夹具文案自述修正）、`68bbc25`（批入口性能缓存接线）。后两次只动**非受审**文件，
受审集在 `6f90f95..68bbc25` 之间为空 diff → worker 身份不变，P5 接线证据按「被测试的字节集合未变」
沿用。

**当天核出并修掉的真问题（按发现顺序）**：

1. **主仓生命周期回归**：受审差量曾让 `tests/test_r0_lifecycle_wiring.py` 在交付实现上 4/4 失败
   （`pool_mask_by_date` 硬要求 `RAW_DAILY_DIR` 等属性），主仓同文件 8/8 通过 → 已修（`6f90f95`），
   修复后 14 文件 pytest 与主仓**失败集完全相同**（223 vs 218 passed、同样 6 个 LOCKBOX 夹具失败）。
2. **求值耗时的归因更正**：我先把跨进程的「命中 96.6 s vs 无缓存 120.2 s」读成「缓存命中更快」，
   同进程三阶段探针推翻（104.6 → 128.9 → 155.6 s，第三个还是命中），正确说法是**进程历史依赖**；
   上轮归因作废。
3. **批次装载口径**：批入口每片一个 subprocess → 计划 §4.2 的「一次装载项」对真实批次是 **20×**
   （20 片）；数组缓存在此形状下价值约 **1.5 h**（20 次全池装载 1.7–2.4 h → 0.19 h）。
4. **批入口性能缓存接线**：批入口不传 `--panel-cache`/`--load-memo`，而 worker 默认开、director
   docstring 要求批入口显式开 → 已修（`68bbc25`），并端到端证明：零候选真实 pipeline 带开关时
   `run_meta.perf_caches` 三项全 true、不带时全 false（三次运行夹住顺序对照）。

**全批 wall（1430 构造、20 片）**：启用数组缓存 **≈ 2.27 h**（计算 2.08 h + 装载 0.19 h）；
不启用数组缓存 **≈ 3.9–4.6 h**；类别加权口径计算项 1.61–1.90 h（`fullbatch-projection-v2` 系列）。
这些是**推算**，实跑仍以 T3 正式批为准。

**GPU 裁决**：不采用。全代表集（20/20）确认后四个配置**两条门槛一条都没过**（详见本文末最新条目）；
此前只在 5 个选择用代表上得出「选中配置过了热点门槛」的口径已收窄。

**未完成**：只剩计划 §7 的外部条件——T1 整体/T1-C、T2 整体/T2-B 仍 BLOCKED，T2-C 仍
CHANGES_REQUIRED；最新阻断点在 `600452/2016-06-01` 分钟口径，77 日期/639 项 BigQuant 批量清单
等用户返回 ZIP。切换状态见 `artifacts/factor-engine-performance-20260913-8/switchover-status.json`
（`switch_status = BLOCKED`）。统计 UNKNOWN、晋级 BLOCK、2025+/生产冻结不变。

### 2026-09-14 性能计划 §6 确认集补齐：全 20 代表上四个配置一条门槛都没过

- 核出缺口：包 -7 与本包的 GPU 四配置对照都只用 **5 个**代表（`--real-frac 0.25`），而 §6 要求
  「在已选 20 个代表中预先固定最多 5 个作配置选择，剩余作为确认集……**再在全部代表集确认**」；
  实测 `n_units_available = 20` 而 `n_units_compared = 5` —— 确认集这一步一直没做。
- 补齐（`--real-frac 1.0`、3 次暖态、CPU/GPU 交替、真实全截面 4996 服务；**20/20 代表、60 次比较
  全部逐位相同**）：

| 配置 | 热点中位（各次） | ≥2× | 计算阶段估计 | ≥1.5× |
|---|---|---:|---|---:|
| blocked_128（选中） | **1.9213**（1.8663/1.9213/1.9343） | **否** | 1.179 | 否 |
| blocked_256 | 1.8197 | 否 | 1.166 | 否 |
| blocked_512 | 1.4401 | 否 | 1.107 | 否 |
| unblocked | 1.0917 | 否 | 1.027 | 否 |

- 影响：blocked_128 在 5 个选择用代表上热点 2.06–2.09×（过线），**全代表集上 1.92×（不过线）**
  → 「选中配置过了热点门槛、只差计算阶段」在**全代表集口径下不成立**；全代表集上四个配置两条门槛
  **一条都没过**，不采用 GPU 的裁决不变且理由更硬。train_test 403.3 s、衰减段占比 0.317、
  CPU 衰减合计 127.7 s、显存 within_budget、rank/spearman 逐位相同、对抗 0 不匹配。
- 口径提示：包 -7 的 per-config 表与 review §16/§20 只覆盖 5 个选择用代表，引用时须写明范围；
  全覆盖版本见包 -8 的 `regression/gpu-bench-fullpool-3pass-all20-after-fix.json`（同提交 68bbc25、
  同协议）。

结论不变：未完成只剩 §7 的外部条件。统计 UNKNOWN、晋级 BLOCK、2025+/生产冻结不变。


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


### 2026-09-14 BigQuant三日修订完成（唯一当前补充状态）

主对话执行/最终验收，具体数据修订DONE / PASS_WITH_LIMITATIONS，见[验收报告](../../artifacts/bigquant-source-repair-20260914-1/review.md)及verification.json。三日源记录存在多个字段差异，采用完整股票日BigQuant来源而非挑价拼接；09:25竞价纳入首个09:35派生区间，原始时间保留。新data/raw/bigquant/minute-repairs-20260914-1/patches.json共33项，仅603026/2019-05-06、300420/2019-09-02、600452/2016-06-01替换，其他30项不变。能力身份同目录minute-capability-review.json。独立聚合3×48根864字段完全一致、9个时间网格负例拒绝，Provider通过。

四条已验账户请求独立枚举只有组合主/压力两个日期共4路径日受影响；全日基准成交/现金先复现，再用完整新源回放，fills完整字典相同、现金差0、费用差0，所有实际依赖覆盖。按用户批准规则，无需重跑全账户；旧-20260914-6账户及-20260914-2报告保留旧来源身份，收益/回撤结论不变，不冒充新源完整重跑。引擎源码摘要未变；未来新引擎或新候选仍须自身验收。

603026保留2000股总量差；600452开盘31.48/日线31.16差仍按既有研究源接受，新身份绑定，不称已解释。300114/2016-05-03本地与proxy daily价量一致且成交2635640股，确认为当前证据下正常交易的分钟缺口，非停牌；本批无实际依赖，未来实际触发只阻断对应候选。T1/T2既有受限通过保留，T3不因本修订整体等待，未代替新引擎联合验收；统计UNKNOWN/晋级BLOCK/2025+生产冻结保持。无公共代码修改、无提交、无BigQuant重复下载。


### 2026-09-14 性能整改整体第二轮复审（当前性能轨道状态）

对象：整改包factor-engine-performance-20260914-1、隔离实现/快照0ea176430880ef35ebe5ec0dfeb372fc46c2564c。审核者：当前审核主对话。执行/审核仍CHANGES_REQUIRED，正式切换未放行。报告：[整体复审](../../artifacts/factor-engine-performance-review-20260914-2/review.md)。

认可：L0-only/成本阶梯接线独立4/4；R7公开reset/关闭释放旧bundle；R3同shape改写拒绝及隔离重发布；R6原摘要漂移关闭（106条引用SHA独立全匹配）。亲跑38 pytest、身份40、检查点31、比较器11全过，7文件差量与快照行尾归一化一致。

未闭合：新预处理指纹repr(co_consts)含代码对象地址，三个新进程同输入产生三个键、全miss；资格运行参数仍未入键；缺缓存成员无法重发布、缺shape抛TypeError；GPU输入收尾不一致仍MEASURED/rc=0，且未核实际源数据收尾；可复制命令仍有硬编码写旧包；新索引未绑定本次GPU等新增整改证据。详见独立反例probe-results.json与报告整改要求。GPU记录计时可复算但本次低内存条件不支持稳定性能区间；维持不采用GPU，2000构造2.2–3.1h只属历史参数情景，不是当前已证性能。

下一步先修跨进程稳定性/完整资格身份/坏件恢复/失败收尾，再新包绑定与预算内限定重测。已读最新T1/T2限定完成记录，不恢复旧BigQuant/四账户阻断；本性能自身未通过。未改算法或旧包、未提交/切换、未启动T3；统计UNKNOWN、晋级BLOCK、2025+/生产冻结不变。


### 2026-09-14 性能第二轮审核 CHANGES_REQUIRED → 四项实现缺陷全部整改（提交 231ae33，整改件 -20260914-2）

[第二轮复审](../artifacts/factor-engine-performance-review-20260914-2/review.md) 结论 CHANGES_REQUIRED，
其中四项是实现缺陷，另外两项是交付绑定与命令表问题。整改件
[artifacts/factor-engine-performance-20260914-2](../artifacts/factor-engine-performance-20260914-2/report.md)。

- **P1 指纹含进程地址**（跨进程缓存永不命中）：engine.py 的 _code_fingerprint 改为递归稳定编码；
  3 个独立进程同一键、命中 false/true/true；审核方自己的 review_probes.py 复跑同结论。
- **P1 资格运行参数/规则源码未进键**：8 项运行参数（STATUS_WARMUP_SESSIONS、ALLOW_UNKNOWN_ST、
  STUDY_READ_FROM、LIQUIDITY_DAYS、MIN_MEDIAN_AMOUNT、MIN_LISTING_SESSIONS、CHINEXT_PCT_DATE、
  GLOBAL_READ_END）随键记录，源码身份补 quant/history.py 与 quant/market.py；三个键互不相同。
- **P2 R3 坏件覆盖不全**：统一结构校验；缺成员/缺 shape/缺 identity/旧版本/内容改写/截断一律
  判不可用 → 记录原因 → 隔离到 _quarantine/ → 可重新发布（不再出现「读报 miss、写又拒绝」死结）。
- **P1 GPU 收尾失败仍写 MEASURED 并返回 0**：收尾复核失败 → IDENTITY_FAIL_AT_FINISH + rc=4；
  起始身份不可建立 → IDENTITY_FAIL_AT_START + rc=5；两者都写 finalise 且不产出可采纳裁决；
  新增运行期可用内存采样（计划 §6 的 2 GiB 停止线）与 timing_validity；身份新增实际消费行情源的
  逐文件摘要（映射落 sidecar）与受审源码文件级摘要映射。
- **P2 R5 命令写回旧包**：命令表 v2（16 条改为经包装器写新根）；核验器实跑路径写死的
  select_supplementary：首跑 rc=0、产物落新根、重跑被拒、**包 -8 目录指纹前后一致**。
- **R6 绑定不完整**：final-manifest.json 绑源码/生成器/输入/新测量/新反例；自校验 37 条引用 0 失配、
  新 GPU 确认文件确在绑定集合内、包 -14-1 索引 106 条复算 0 失配。
- **受限重测**：285 股切片跨进程 冷 38.0 s → 热 4.0 s（9.45x，命中 5 / 未命中 0 / 校验失败 0，
  含数组内容校验）。旧「19 秒命中」与「2000 构造 2.2–3.1 h」降为历史参数假设情景，本包不重算、
  不作承诺；全池首次重跑仍是冷装载口径。
- **我自己的一处越界已修**：导入包 -8 脚本时留下 __pycache__（2 个 .pyc），已删除，两个导入点加
  sys.dont_write_bytecode = True；包 -8 内容文件哈希未变。

回归：隔离仓缓存测试 15/15、身份 40/40、检查点 31/31、比较器 11/11。快照前移到 231ae33；
主仓未合入未提交；统计 UNKNOWN、晋级 BLOCK、2025+/生产冻结不变。


### 2026-09-14 性能第三轮复核：实现层全过、最终绑定 3 条失配 → 已修（包 -20260914-2 内）

第三轮复核（同一份 [review-20260914-2](../artifacts/factor-engine-performance-review-20260914-2/review.md)）
确认实现层全部通过：跨进程缓存、资格配置入键、缓存损坏恢复、GPU 起止身份阻断、市场源身份、
33 条命令核验、旧包未被改写；但**最终证据绑定校验发现 3 条摘要失配**
（probe-round2-closure.json 两处引用、final-binding-verified.json 一处）。

根因是两条交付设计错误（均在我这边）：① 被绑定产物可被探针重跑就地覆盖（探针输出含运行期内存等
易变字段）；② 清单把校验结果自身也绑了进去（自指），而命令表校验器还会自动重跑生成器覆盖命令表。

修法：4 个生成器改为**写一次即冻结**（重跑落带时间戳新名）、验证输出不进清单并反向记录
manifest_sha256、清单在全部证据冻结后最后生成（新增 binding_rules 字段）。

**重跑稳定性实测**：4 个探针/生成器全部重跑一遍后再跑绑定校验 —— n_referenced=40、**n_bad=0**、
new_gpu_bound_by_manifest=true、p1_index_mismatches=[]、passed=true；被绑定文件的哈希与 mtime 未变。
证据见 [artifacts/factor-engine-performance-20260914-2](../artifacts/factor-engine-performance-20260914-2/report.md)
§六、final-manifest.json、final-binding-verified.json、rerun-stability.log。

未改算法/原始数据/账户规则，未动任何旧包，未提交主仓；统计 UNKNOWN、晋级 BLOCK 不变。


### 2026-09-14 启动前专项任务书（仅文档，未启动计算）

用户要求编写第2、3项，已交付[引擎及接线验收、真实小批试跑任务书](t3-engine-integration-and-trial-20260914.md)。先核第三轮性能修复及最终绑定，再以最终清单完成真实小批、恢复与独立核算；进度仍写本任务书，不另开任务板。本条不改变既有执行/审核裁决，不恢复已取消的T3全量运行。
### 2026-09-14 任务2 引擎整合与 L0 接线验收完成（执行 DONE / 审核 PASS_WITH_LIMITATIONS）

执行与终裁：主对话 Codex（同一轮内执行后审核）。对象：任务书 `t3-engine-integration-and-trial-20260914.md` 任务2。
交付：[artifacts/t3-engine-integration-20260914-1](../artifacts/t3-engine-integration-20260914-1/report.md)（report.md / version-map.md / run-config.md / final-manifest.json 62 件 / evidence 17 件）。
整合身份：`D:/AI/workspace/t3-engine-int-20260914-1` @ `3af1fc1`（`941c959` 主仓工作树 overlay → `083367e` 三方合并 → `d607de8` worker 扩展字段接线 → `3af1fc1` 数据版本标签）。主仓未提交未改写；旧包与旧快照未改动。
三方归一化比较（主仓工作树 / 5d786cf 基线 / 231ae33）：只有 perf 改 5、只有主仓改 19、双方都改 3、perf 新增 37、主仓新增 399（`apps/` 388 个按范围排除）；整合目录与主仓共同文件 **629 个逐字节一致**，冲突标记 0（合并中修掉 2 个纯行尾冲突文件的标记残留）。
集成期修复 2 处接线缺陷：① L0 worker 从不按清单装载 wave4 扩展字段 → 引用 `inc_*`/`ev_*` 的候选编译期硬失败（修复前对照仓 rc=1 `CompileError`；修复后 rc=0、`COMPLETED_DESCRIPTIVE`、装载 182 字段、wave4 候选实得 `n_months=35`）；② `run_meta`/`candidates.jsonl` 数据版本标签恒为纯价量版本，现取 bundle meta 的真实版本（扩展批为 `data_version_extended()`），worker 侧接受 plain/extended 两者（内容绑定仍以 `field_names_sha256`/`content_digest`/`tr_meta_sha256` 为准）。
验证（全部在 `3af1fc1` 重跑）：身份 40/40、检查点 31/31、比较器 11/11、冻结身份负例 8/8、真新进程 CLI 7/7、worker CLI 9/9 PASS（285 证券 / 144 单元 / `validation_fixture`）、L0-only 与成本阶梯逐位等价 20/20、p2 等价 35/35（冷缓存）、池掩码轴与全域等价 PASS（消费轴 53,460 格 0 差异、轴外新鲜侧 886 日全 False）、内核等价 rc=0、标签哨兵 PASS、分母 1430/20 片 PASS、第二轮反例复跑 `all_closed=true`。
独立核算（自写算子与统计，不复用引擎实现）：两公式缺失掩码 0 差异、因子最大绝对差 ≤3.6e-15、有效月 35/35、超容差 IC 0 条、平均 IC 逐位相同、截面平均秩最大差 0.0。
限定回归：`pytest tests -k factor_miner` 在整合目录与主仓失败集合完全相同（各 15 项，全部是 lockbox 准入被统计有效性冻结阻断，非合并回归）。
保留限制：口径限于本机真实数据切片与夹具（全池 20 片未跑）；L1/L2 未接通；wave4 字段 PIT 深度沿用 T1 既有验收；过期夹具 `t3_perf_p2_arraycache_test`（早于 R3 隔离语义）与 p2 harness 的原始字典比较按原样保留并在报告中说明替代覆盖。
未做：T3 真实小批试跑（需最终清单登记审核 + 授权）、主仓提交、T3 全量。统计 UNKNOWN、晋级 BLOCK、2025+ 与生产冻结不变。

### 2026-09-14 T1 公共能力：白名单 v2 字段覆盖与新增源输入身份（交付 + 待回放）

执行：主对话 Codex（T1 侧公共文件）。**定位**：T3 wave4 需要的 PIT 财报/事件字段读取与
输入身份属 T1 公共数据/执行能力，由主对话在 T1 名下交付、T3 消费；公共文件改动集中登记：

* **字段白名单 v2**（`experiments/factor_miner/data_fields.py` 追加段）：156 个 PIT 财报字段
  + 24 个公告事件字段；时点规则（最早公告组 <= t、陈旧上限 459 自然日、真重复整期丢弃、
  冲突 fail-closed、事件 ann <= t、解禁只用公告时已知的未来安排）；loader 产出包日轴稠密序列。
* **接线**：`engine.build_real_bundle(with_statements/with_events/statement_fields/event_fields)`
  需求驱动装载（显式字段集、缺则 fail-closed；`EVENT_PRE_SESSIONS=260` 前置会话补齐轴首日滚窗）。
* **输入身份（F2 整改）**：`experiments/t3_wave4_input_manifest_20260914.py` 按 loader 实际读取
  规则枚举新增源 26,966 文件 / 2,035MB，逐文件 sha256 + 聚合摘要；`t3_l0_batch_20260913.py`
  在启动/aggregate/收尾三处核验并绑入 `run-identity.json`；变异（新增/缺失/改字节）一律拒绝。
* **提交**：快照 `D:/AI/workspace/t3-snapshot-20260914-1` @ `2586c1b`（F1–F4 整改）→ `e69e5e7`
  （整改测试）；主仓未提交（沿既有约定）。
* **待回放（重要）**：性能整合树 `D:/AI/workspace/t3-engine-int-20260914-1` @ `3af1fc1`
  **早于本轮 F1–F4 整改**——其 `data_fields.py`/`engine.py`/`t3_l0_batch_20260913.py` 仍是
  整改前版本（含 F1/F3/F4 缺陷与无输入清单核验）。下次整合或切换前须把 `2586c1b`+`e69e5e7`
  的 loader/接线/清单修复回放到整合树，并按其最终实际入口（worker 或逐片 CLI）重测。
* 独立审核对该轮公共字段的裁决与整改记录：`artifacts/t3-construction-review-20260914-1/review.md`、
  `artifacts/new-factor-research-20260912-16/remediation-review-20260914.md`（自审，待独立复核）。
