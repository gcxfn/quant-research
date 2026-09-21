# 十年研究基础设施（任务一）交接与审阅材料

日期：2026-09-13。用途：交给独立审阅 agent——自包含，不需要先读其他会话历史。
配套任务书：`docs/tasks/ten-year-research-infrastructure-20260912.md`；配对审核书：`docs/tasks/ten-year-research-infrastructure-review-20260912.md`。
批次工件：`artifacts/ten-year-infrastructure-20260912-1/`（manifest.json / coverage.csv / issues.json / verification.md / review-infrastructure.md / review-current-20260913.md / review-followup-20260913.md / e2e-2015-2016-sample/ / minute-probe-20260913/）。

## 0. 一句话状态

最新主审复核已执行：本轮整改 **PASS_WITH_LIMITATIONS**。T1-A盘点受限通过；T1-B信号恢复能力可用、账户现金/费用/持仓/公司行为样例及独立重算已补交并复核通过（§11）；T1-C运行支持继续RUNNING，整体未完成。复核唯一未闭合项（D-7空分红摘要分支）已按复核要求整改并复验关闭，详见 §10。统计有效性仍 UNKNOWN、晋级仍 BLOCK、2025+ 仍冻结。这些是当前事实，不因本文件而改变。

## 1. 三轮审核账（裁决与整改，按时间）

| 轮次 | 文件 | 裁决 | 缺陷与处置 |
|---|---|---|---|
| 1 | review-infrastructure.md | T1-A PASS、T1-B PASS_WITH_LIMITATIONS、T1-C PARTIAL | D-1（停牌机制描述错误）、D-2（批次归属表述不完整）→ 文档更正，复核关闭 |
| 1.5 | （20260913 增补复核） | G2/G3/G4 PASS；G1 发现 D-3 | D-3：daily_basic 5 个整市场空 chunk（瞬时限流空帧）→ 空日复核补齐、5 日重抓、D-4 多批单测；G1 升 PASS |
| 2 | review-current-20260913.md | **CHANGES_REQUIRED**（D-5/D-6/D-7/D-8） | 四项整改完成 → 独立复核各 PASS；复核同时抓出分红消费循环缩进回归 → 修复并补负例 → **改判 PASS** |
| 3 | review-followup-20260913.md | **CHANGES_REQUIRED**（D-9 P1 + D-6/D-7/D-8 跟进） | 全部整改完成（见 §4 追溯矩阵）；**独立复核未执行，PENDING** |

审阅者请注意：第 3 轮之前的 PASS 不覆盖第 3 轮的发现；本文件不自行签署第 3 轮结论。

## 2. 任务一交付物（当前磁盘事实）

### 2.1 代码（未提交，工作区状态）

| 文件 | sha256 前16位 | 作用 |
|---|---|---|
| `experiments/ten_year_partition.py` | 33c815a1e1fd156d | 十年读窗契约：READ 2015-01-01..2024-12-31，WARMUP_FROM 2013-07-01，2025+ 代码级拒绝 |
| `experiments/ten_year_research.py` | b370d91545ad58d4 | 十年两账户信号入口（REV11 + PV1/REV11 blend），显式窗口、输入身份绑定、恢复协议；`ten_year_fee_terms` 现给出 2015 上半年沪市面额制过户费（`transfer_per_share`，见 §11） |
| `experiments/ten_year_field_backfill_20260913.py` | 26dae5656ca37ff9 | 2015-2018 daily_basic / 2015-2017 dividend 回补抓取器（16路并发+自适应节流+内容校验；空文件分支摘要前置，见 §10） |
| `experiments/ten_year_minute_probe_20260913.py` | 5a75357326cd123d | baostock 5分钟来源覆盖探针（证据生成） |
| `experiments/ten_year_calendar_fetch_20260912.py` | cc8490c70dcf9cca | 2014-2017 交易日历补抓（tushare 同源） |
| `experiments/factor_miner/data_fields.py` | 306260fd114c62fa | 共享：`gate` 可选读窗通道 + daily_basic 多批次扫描 |
| `experiments/factor_miner/engine.py` | 3953b40e581553f4 | 共享：`load_stock_rows` 的 `gate` 透传 |
| `experiments/r0_pilot_market_inputs_20260912.py` | 789138fde346462c | 分红消费端接 r2+r3 双批（`collect_dividend_events` 纯函数）；`prepare_inputs` 从 `main` 提取（显式 first-signal 映射，十年早期窗口可用），`train_limit_pct`/`check_fixed_window` 窗口放行 2015-2024 内任意区间 |
| `experiments/ten_year_account_20260913.py` | 675c15daa238a958 | 十年账户样例运行入口：信号批→固定现金账本（逐执行日法定费率、日线执行、opening_cash_only），代码身份绑定 |
| `experiments/ten_year_account_audit_20260913.py` | 4f9dd658261f1005 | 账户独立重算：独立 Decimal 费率制度（含面额制）重建现金/持仓/可卖/净值并逐日对账 |
| `experiments/r0_pilot_corporate_actions_20260912.py` | d11e12247b54dd2f | `resolve_event` 事件窗口放行 2015-2024 内任意区间（原两个固定窗口行为不变） |
| `quant/execution.py` | 8a90ea3c0a95b860 | `trade_fee_breakdown` 新增可选 `transfer_per_share`（元/股，买卖两侧按股数），旧字段语义不变；`Replay._annotate_costs` 的 `fee_breakdown` 生成门同步纳入该键（否则单用面额制表达时费用已扣但无分量标注） |
| `experiments/factor_miner/fixed_capital_portfolio.py` | a1b58e9cf608706a | `_FEE_KEYS` 纳入可选 `transfer_per_share` 校验 |
| `tests/test_pilot_cost_ledger.py` | 29c08f490ceb7141 | 新增面额制过户费单独表达回归（费用按股数、分量写入 `fee_breakdown`、现金对账） |
| `tests/test_ten_year_infrastructure.py` | fff7455808319c68 | 41 项定向测试（含空分红错误摘要负例、面额制过户费负例、十年账户样例 6 项） |
| `experiments/factor_miner/pilot_costs.py` | d63092f6b5b0adde | `fill_costs` 新增可选 `terms=`（显式费率制度：十年窗口/面额制不再受 TRAIN 日期限制） |
| `experiments/r0_mechanism_cost_pilot_20260912.py` | d9942e182e7364da | `account_metrics` 新增可选 `fee_terms=`；`yearly` 由数据年份推导（不再是硬编码 2020-2022） |
| `tests/test_pilot_costs.py` | 06a977c14c37e3e7 | 新增显式 terms 十年/面额制负例与参数校验 2 项 |
| `tests/test_pilot_result_accounting.py` | (未改) | TRAIN 口径回归（`fill_costs`/`account_metrics` 默认路径不变） |
| `tests/test_pilot_market_inputs.py` | d8576d46238a1847 | 新增分红多 chunk 消费负例 2 项 |
| `scripts/ten_year_build_artifacts_20260912.py` | a7f3fa20396797b4 | coverage/issues/manifest 工件生成（G4r 关闭、账户样例登记） |
| `scripts/ten_year_coverage_scan_20260912.py` | 06bdcbe9b2e56ab5 | 日线逐年全量扫描（覆盖分母来源） |
| `artifacts/.../coverage.csv` | 70a6c72700143937 | 逐年覆盖矩阵（含精确键交集行；数值与上版一致，仅分红行用途文字更新） |
| `artifacts/.../issues.json` | 783284b4dfbb91e1 | G4r 移入已关闭项（F6），其余不变 |
| `artifacts/.../manifest.json` | 910eb08d2169e181 | 批次清单：新增账户样例及 G4r 关闭记录 |
| `artifacts/.../account-2015-2016-sample/` | 2db59c8ac8ea842b | 十年账户样例批（manifest）；两身份 account.json + data-issues.json + inputs/ + independent-review.json（8a52ac020292f972） |
| `artifacts/.../coverage-dailybasic-keyinter-20260913.json` | 493d704bdcf6688f | (symbol,date) 精确交集工件 |

变更后请重新计算 sha；任何摘要变化都使本文件的“已验证身份”失效，须复核关联项。

### 2.2 数据（只新增，不覆盖）

- `data/raw/tushare/trade_cal/20260909-r1/chunk_sse_20140101_20171231.csv`（0788c94f70be4b03，1461 行/977 开市日追加到既有批次目录；合并日历 2014-01-02..2026-08-28 共 3078 开市日，无周末污染、新旧 chunk 零重叠）。
- `data/raw/tushare/daily_basic/20260913-r2/`（manifest 5471ca557cdd7051）：2015-2018 共 **975 个交易日 chunk、2,774,097 条非空 turnover_rate**（实际行数=非空值数）；daily_basic manifest 975 条全部绑定内容 sha256；另732条属于dividend manifest，两批合计1707条。
- `data/raw/tushare/dividend/20260913-r2/`（manifest d21031d3709ba7f3）：2015-2017 共 **732 个除权日 chunk、7,626 条事件、199 个合法无事件空日**（0字节文件，本次审核独立校验sha256；获取器空文件分支摘要比较已于 §10 前移，rows=0+错误sha 现被拒绝）。
- `artifacts/.../e2e-2015-2016-sample/`（manifest 7d7a22ef670c9638）：真实四股（sh.600000、sz.000001、sh.600958 2015-03-23 IPO、sh.600005 2017-02-14 退市）2015-2016 两账户信号批，24 信号月+24 执行月，manifest 含 5899 项 input_identity。
- `artifacts/.../minute-probe-20260913/minute-probe.json`：baostock 5 分钟 9 个探针——2015-2019 七个样本日全 0 根，2020-01-02 与 2024-10-08 各 48 根。**来源起点实测 2020-01-02**。

### 2.3 覆盖口径（D-8 之后的精确版本）

coverage.csv 每年 8 行，其中 daily_basic 两行：
1. 交易日文件覆盖：975/975（文件级，D-7 深度校验：sha256+尾行+首行日期+行数）。
2. `turnover_rate key coverage (symbol-day intersection)`：研究键=baostock type=1（5552 只）×交易日×`tradestatus!=0`，与源键（daily_basic 全行，日期 ISO 归一）做集合运算。

**十年精确结论（coverage-dailybasic-keyinter-20260913.json）**：研究键 9,254,330、源键 9,392,025；**真实缺失仅 14 个证券日**（2016 缺 1、2020 缺 11、2021 缺 2），其余年份 100%；额外 137,709 键（其中非沪深137,703，另6个沪深键）为研究池外证券及源对部分停牌日的服务行（逐年在行内披露，从分母排除）。不要再把净差解释成缺失数——这正是第 3 轮 D-8 的整改点。

## 3. 关键常量与纪律

- 读窗：`ten_year_partition.READ`=2015-01-01..2024-12-31；`WARMUP_FROM=2013-07-01`（252 会话年龄+20 流动性+最长特征窗）；2025-01-01 起任何读取抛 `TenYearWindowError`。混含 2025 行的本地文件在解析前按日期隔离（有测试）。
- 费率：`ten_year_research.ten_year_fee_terms(date, code)`——印花税卖出 10bps（<2023-08-28）→5bps；过户费 2015-08-01 起沪深 0.2bps（成交金额制）→2022-04-29 起 0.1bps；2015-08-01 前深市 0.255bps（金额制）；**2015-08-01 前沪市按成交面额 0.3‰ 计费，金额 bps 不可表达，改以 `transfer_per_share=0.0003*face_value`（元/股，买卖两侧按股数）表达，`quant.execution.trade_fee_breakdown` 支持该键**；原开放项 G4r 已于 2026-09-13 关闭并在账户样例中实际计费（§11）。
- 旧入口与冻结区零改动：`partition.py` 的 TRAIN/VALIDATION/LOCKBOX、`three_account_migration_*`、`migration_signal_export_*`、`migration_runtime_*`。共享文件上本批只新增 `gate` 可选参数与 daily_basic 多批次扫描（默认行为逐字节不变）。
- 统计/晋级：UNKNOWN / BLOCK；本批全部结果为描述性、非 Alpha 证明。

## 4. 缺陷 → 修复位置 → 测试 追溯矩阵（供审阅逐项反证）

| 缺陷 | 修复位置 | 对应测试（tests/test_ten_year_infrastructure.py 除注明外） |
|---|---|---|
| D-1/D-2 文档 | verification.md §3/§1 | 无（文档更正，复核已关闭） |
| D-3 空 chunk | backfill `fetch_one` 空日复核 | ChunkSatisfiedTest::test_daily_basic_empty_content_rejected_even_with_sha |
| D-4 多批次无测试 | — | DailyBasicMultiBatchTest（3 项） |
| D-5 输入未绑定 | `data_input_identity`（5899 项 sha256）+ 续跑/终局校验 | DataInputIdentityTest（2 项，含篡改拒绝） |
| D-6 恢复协议 | `_trim_incomplete_evidence_tail`、证据前缀校验、立即 save input_identity | ResumeProtocolTest（2 项）、ResumeSafetyTest（滞后/领先/缺身份 3 项） |
| D-7 跳过前不校验内容 | `chunk_satisfied` 四重校验 + 原子写 + manifest 绑 sha；空文件分支摘要比较前置（§10） | ChunkSatisfiedTest（6 项，含第 3 轮两个原例与空分红错误摘要负例） |
| D-8 净差当缺失 | 精确键交集 + coverage.csv 集合口径 | coverage-dailybasic-keyinter-20260913.json（可独立重算） |
| D-9 换序漏股 | `prepare` sorted 规范化 + `seen` 前缀核对 + 导出前覆盖断言 | ResumeSafetyTest::test_reordered_universe_resume_keeps_full_coverage |
| 分红缩进回归（第 2 轮复核发现） | `collect_dividend_events` 纯函数归位 | tests/test_pilot_market_inputs.py::CollectDividendEventsTest（2 项） |

## 5. 复现与验收命令

```bash
# 定向测试（约 1-2 分钟）
python -m pytest tests/test_ten_year_infrastructure.py -q
# 受影响面（信号入口 + 分红消费 + 既有市场输入回归 + 账户样例 + 费用核算）
python -m pytest tests/test_ten_year_infrastructure.py tests/test_pilot_costs.py tests/test_pilot_cost_ledger.py tests/test_pilot_result_accounting.py tests/test_pilot_market_inputs.py tests/test_migration_market_inputs.py tests/test_pilot_st_exit.py tests/test_pilot_corporate_actions.py -q
# 执行者自报基线：定向 41 passed；八文件合集 70 passed + 4 subtests（2026-09-13 实测；§11 全部整改后计数）

# 十年账户样例：信号批 → 账本 → 独立重算（离线；须以模块方式运行）
python -m experiments.ten_year_account_20260913 --signals artifacts/ten-year-infrastructure-20260912-1/e2e-2015-2016-sample --out <新目录>
python -m experiments.ten_year_account_audit_20260913 <上一步目录>

# 数据校验（离线、只读；应两批均 "nothing pending"）
python experiments/ten_year_field_backfill_20260913.py --dataset all

# 小样例入口（真实数据；约 1 分钟含 6.4s 输入哈希）
python experiments/ten_year_research.py --out <新目录> --window-start 2015-01-01 --window-end 2016-12-31
# 注意：CLI 走默认全市场名单；测试内用小名单是 main(symbols=[...]) 参数

# 覆盖交集独立重算：研究键=baostock type=1×交易日×tradestatus!=0，源键=daily_basic r1+r2 全行（日期归一 ISO）
```

## 6. 未完成项与边界（不得在本轮声称 T1 完成）

1. **第 3 轮独立复核 PENDING**（本文件的直接目的）。复核要点：§4 矩阵逐项反证 + §2.3 交集独立重算 + 两批 manifest 的 sha 绑定。
2. ~~**十年账户端到端独立核算**未交付~~ → 本轮已交付 2015-2016 两账户样例及其独立重算（§11.3）；十年全量（2015-2024）账户仍未跑。
3. ~~**G4r**：2015 上半年沪市面值计费过户费需 T2 在账本加 0.0003 元/股~~ → 已在 `quant.execution.trade_fee_breakdown` 实现 `transfer_per_share`，`ten_year_fee_terms` 直接给出，并在样例账本中实际计费与复算（§11.1）。
4. **2015-2019 执行语义**：baostock 分钟自 2020-01-02 起才有；T2 须先登记（日线执行模式或接受受限范围），不得由缺数自动放行日线回退。2020+ 保持按订单依赖获取，不预下载全市场。样例已按日线执行并在批次清单登记。
5. ~~`r0_pilot_market_inputs.main` 仍只接受 2020-2022 / 2023-2024 固定窗口~~ → `prepare_inputs` 已提取并支持十年早期窗口，2015-2016 分红已进入账户账本（§11.2/§11.3）；`main` 自身的诊断书入口仍限定原两个窗口。
6. 2025+ 冻结、生产发布、实时前向维持不变。

## 7. 给审阅 agent 的最小检查清单

1. 重算 §2.1 关键文件 sha256，确认与表一致（不一致即身份失效，列出差异）。
2. 跑 §5 两组 pytest，核对 34 项与 47+4 的计数。
3. 对 D-9：亲自构造换序续跑（见 §4 对应测试的实现），确认不会漏/重股票。
4. 对 D-7：确认旧两批 manifest 1707 条目均有 sha256；自造截断/错日期文件确认拒绝。
5. 对 D-8：抽 2016 年独立重算交集，确认 missing=1 且能定位具体 symbol-date。
6. 抽查 e2e 批：24+24 月、sh.600958 首观测 2016-03-31（252 会话年龄门）、sh.600005 无越界。
7. 记录复核结论（PASS/PASS_WITH_LIMITATIONS/CHANGES_REQUIRED）并追加到 `review-followup-20260913.md`；不修改被审代码再自签。

## 8. 审阅者不应做的事

不重开无关审计；不为凑测试数重复全仓运行（全仓有 13 个与本批无关的既有失败，位于 lockbox/director 准入路径，执行者已用“反转 hunk 复现”判定非本批引入）；不采信本文件的 PASS 措辞而不看命令与工件；不修改被审算法、测试、原始数据。


## 9. 最新主审复核（2026-09-13，覆盖前文历史PENDING描述）

**PASS_WITH_LIMITATIONS**，不等于T1完成。主对话亲跑47项测试+4子测试通过，交接14项摘要全匹配；975+732文件摘要独立全核一致；2016交集独立重算缺sh.600656/2016-05-12。原换序漏股/检查点落后/截断错日反例已修。

剩余局部限制：空分红文件遇rows=0、错误非空sha曾被chunk_satisfied接受——该项已按复核要求整改（摘要比较前置+空文件错误摘要负例），见 §10；当前199空日真实摘要已核一致。（本节其余“账户独立核算/G4r/早年账户消费未交付”为该轮状态，§11 已交付并复核，见文末最终当前状态。）完整记录：`artifacts/ten-year-infrastructure-20260912-1/review-handover-20260913.md`；最新阶段以配套两份任务书末尾为准。§2.2回补行数及§2.3额外键合计已由主审据实更正。

## 10. 交接复核后整改：空分红分支摘要前置（2026-09-13）

复核文件 `artifacts/ten-year-infrastructure-20260912-1/review-handover-20260913.md` 的唯一未闭合项：`chunk_satisfied` 的 `if not data` 分支在内容摘要比较**之前**返回，导致“空文件 + rows=0 + 任意非空 sha256”仍被判为已满足，与 D-7“跳过前必须校验内容”不符。

整改（不改变任何其他行为）：

1. `experiments/ten_year_field_backfill_20260913.py` `chunk_satisfied`（约第136行起）：把 `sha256(data) == entry['sha256']` 比较前移到空文件分支之前；空文件必须先证明其字节确为 `b''`（摘要等于 `sha256(b'')`）才按合法无事件日放行，`rows==0` 与 `dataset=='dividend'` 条件不变。新摘要 `26dae5656ca37ff9b332b8e5971851a20c660a20333e797e1c2c51a2870baac3`。
2. `tests/test_ten_year_infrastructure.py`：新增 `ChunkSatisfiedTest::test_dividend_empty_file_with_wrong_sha_rejected`（空文件+错误 sha 拒绝；空文件+正确 sha 但 rows=3 亦拒绝）。文件新摘要 `a07f8184b1537c44ca4da69b725eb36c43f30671eb32bb5f313871f37074685a`（该轮身份；当前见 §2.1），定向测试 34→35 项（当前 41）。

验证证据（离线、未联网、未改动原始数据）：

- `python experiments/ten_year_field_backfill_20260913.py --dataset all` → daily_basic `pending=0`、dividend `pending=0`（4.13s）。收紧后的校验对真实两批 1,707 个条目零拒绝，即 199 个空分红文件的 manifest 摘要确为 `sha256(b'')`，数据可用性不受整改影响。
- `python -m pytest tests/test_ten_year_infrastructure.py -k "ChunkSatisfied or DailyBasicMultiBatch or ResumeSafety" -q` → 13 passed。
- `python -m pytest tests/test_ten_year_infrastructure.py tests/test_pilot_market_inputs.py tests/test_migration_market_inputs.py tests/test_pilot_st_exit.py -q` → **48 passed, 4 subtests passed**（181.49s；复核前为 47+4，新增负例 +1）。

限制：本次只关闭该 P2 局部缺口，未重开其余审核项；T1-B 账户独立核算、T1-C 的 G4r、2015–2017 账户消费、实际订单分钟依赖仍未交付。§2.1 两个文件摘要已更新，其余 12 项不变，绑定旧摘要的裁决仅覆盖旧身份。

## 11. 账户能力补交：面额制过户费 + 早期分红消费 + 2015-2016 账户样例（2026-09-13）

§6 复核清单的第 2/3/5 项本轮交付，均离线、未下载、未改动原始数据。

**11.1 G4r 面额制过户费（能力闭环，非近似）**

- `quant/execution.py::trade_fee_breakdown` 新增可选 `transfer_per_share`（元/股，买卖两侧按**股数**计），与金额制 `transfer_bps` 并列；未提供该键时旧行为逐字节不变。`fixed_capital_portfolio._FEE_KEYS` 同步纳入该校验（可选、非负有限）。
- `ten_year_fee_terms` 对 2015-01-01..2015-07-31 沪市改为 `transfer_bps=0.0` + `transfer_per_share=0.0003*face_value`（`face_value` 默认 1.00 元，可显式覆盖）；深市该区间仍 0.255bps 金额制；>=2015-08-01 与 2022-04-29 边界不变。依据：中国结算 2015-07-01 公告（沪市原按成交面额 0.3‰ 双向、深市按成交金额 0.0255‰；2015-08-01 起统一为成交金额 0.02‰）。
- 结论：不再有 fail-closed 开放项，账本可直接用默认 `fees_for_date=ten_year_fee_terms`，无需调用方自加 0.0003 元/股。

**11.2 早期窗口账户消费接入**

- `experiments/r0_pilot_market_inputs_20260912.py`：把 `main` 主体提取为 `prepare_inputs(out, first, window, *, migration=False, extra_manifest=None)`，按显式 first-signal 映射准备价格/状态/涨跌停/公司行为；`main` 原有诊断书身份校验与窗口准入不变。
- 窗口准入由「两个固定窗口白名单」改为「2015-01-01..2024-12-31 内任意区间」（`check_fixed_window` 与 `resolve_event._check_event_window`）：既有 2020-2022 / 2023-2024 调用逐行等价，2025 以后仍拒绝。
- 分红来源固定为 r2(2015-2017 回补)+r3(2018 起)；2016 以前只有 r2 能提供事件，故 2015-2016 账户分红必然来自回补批，不存在跨源混用。

**11.3 2015-2016 两账户样例 + 独立重算**

- 新增 `experiments/ten_year_account_20260913.py`：读十年信号批（同窗、24 个信号月完整、输出摘要一致），准备账户输入，按身份跑固定 20 万现金账本——日线执行、`opening_cash_only`、参与率 0.005、逐执行日法定费率（含 11.1 面额制）、已核实施分红/送转入账；窗口前信号月只作账本初态（断言无持仓/无收益/零费用）。运行开始绑定 10 个源文件摘要，结束前复核。
- 新增 `experiments/ten_year_account_audit_20260913.py`：**不调用**账本与费用引擎，用 stdlib + `Decimal` 自行实现 2015-2024 费率制度（含面额制），从输入工件与成交记录逐步重建现金、费用、持仓、可卖量、市值/净值、分红与送转，逐日与被审 `account.json` 比对（1e-6），并校验涨跌停、T+1、参与量、生命周期与逐笔费用四分量。
- 真实样例批 `artifacts/ten-year-infrastructure-20260912-1/account-2015-2016-sample/`（四只样本：老股×2、2015 IPO、退市股；窗口 2015-01-01..2016-12-31，488 个账本日）：

| 身份 | 状态 | 成交 | 分红入账 | 2015-07 前面额制成交 | 期末权益 | 独立重算 |
|---|---|---|---|---|---|---|
| REV_vola_11 | COMPLETED | 36 | 2,408.42 | 7 | 196,470.6936 | 现金/净值误差 0 |
| PV1_REV11_RANK50_TRAIN_V1 | COMPLETED | 36 | 2,408.42 | 7 | 196,470.6936 | 现金/净值误差 0 |

- 逐日现金、费用累计、持仓、可卖量、净值与逐笔费用分量均与独立实现一致；`data-issues.json` 为空（无持仓相关未核公司行为、无缺价净值日）。样例包含 2015-07 前沪市成交，故面额制过户费在真实账本上被实际计费并复算，而非仅存在于费率函数中。
- 命令（须以模块方式运行，包内导入依赖仓库根）：`python -m experiments.ten_year_account_20260913 --signals <信号批> --out <新目录>`；`python -m experiments.ten_year_account_audit_20260913 <账户批>`。

**11.4 本轮仍未交付/未放行**

1. 十年全量（2015-2024）账户仍未跑；样例只覆盖 2015-2016 两身份。
2. 2015-2019 执行语义仍是 T2 登记项（无分钟来源；样例按日线执行并已显式登记）。
3. 2015-2017 分红只做到账户级消费与样例验证；更早年份无事件需求，不下载。
4. 2025+ 冻结、生产发布、实时前向、统计 UNKNOWN、晋级 BLOCK 均不变。

**11.5 本轮验证命令与计数**

```bash
python -m pytest tests/test_ten_year_infrastructure.py -q                      # 41 passed
python -m pytest tests/test_ten_year_infrastructure.py tests/test_pilot_costs.py \
  tests/test_pilot_cost_ledger.py tests/test_pilot_result_accounting.py \
  tests/test_pilot_market_inputs.py tests/test_migration_market_inputs.py \
  tests/test_pilot_st_exit.py tests/test_pilot_corporate_actions.py -q         # 70 passed, 4 subtests
```

**11.6 独立复核（2026-09-13）**

复核记录：`artifacts/ten-year-infrastructure-20260912-1/review-account-20260913.md`（+ 同名 `-evidence.json`）。裁决 **PASS_WITH_LIMITATIONS**；两个独立 reviewer 子代理（`VerifyFaceValueFee`、`VerifyEarlyDividendConsumption`）只读复核，未修改被审代码。

- 面额制：独立 Decimal 实现复算样例两身份全部 36 笔成交费用分量，零不匹配；7 笔沪市（9,500 股）按 `shares*0.0003` 计费共 2.85 元（`independent-review.json` 记 2.8500000000000005）。
- **子代理发现缺陷（已修）**：`Replay._annotate_costs` 的 `fee_breakdown` 生成门漏了新键 `transfer_per_share`——单用面额制表达时费用照扣但填充明细缺失、账本 `commission` 混入过户费。已修并补 `tests/test_pilot_cost_ledger.py::test_per_share_transfer_fee_alone_reaches_fills_and_breakdown`；因 `ten_year_fee_terms` 该区间始终给 `transfer_bps`，样例 `account.json` 摘要逐字节未变（293f00fc…/ffb75253…），样例结论不受影响。
- 分红消费：独立提取 r2 中 2015-2016 四码实施事件 8 条（r3 同区间 0 条），账本 6 条分红逐事件通过三项校验（来源/持仓/登记日股数×每股现金），合计 2,408.42 与账本一致；sh.600958 的两条除权日无持仓事件在收集阶段即被排除，无零持仓入账；732+2,109 个 chunk 共 43,566 行中 0 行 ex_date 与文件名不符。

**11.7 共享费用核算打通（复核后追加）**

面额制能力此前只接进账户引擎，共享的逐笔费用核算仍走 TRAIN 口径：`pilot_costs.fill_costs` 只认 `transfer_bps` 且 `train_fee_terms` 对 2020-2022 之外直接抛错，`r0_mechanism_cost_pilot.account_metrics` 因此无法复算任何十年账户（要么报「fee policy covers TRAIN 2020-2022 only」，要么在 2015-08 前沪市成交上误报分量不符）。

- `experiments/factor_miner/pilot_costs.py::fill_costs` 新增可选 `terms=`：调用方传 `ten_year_fee_terms(date, code)` 时不再套用 TRAIN 日期守卫，并逐笔计入面额制 `transfer_per_share`（元/股 × 股数）；`terms` 经 `_checked_terms`（与 `quant.execution.trade_fee_breakdown` 同键、缺省 0、非负有限校验）。未传 `terms` 时逐字节旧行为——默认路径同样经 `_checked_terms`归一，TRAIN 调用方（`test_pilot_costs`、`test_pilot_result_accounting`、r0 探针）行为不变。
- `experiments/r0_mechanism_cost_pilot_20260912.py::account_metrics` 新增可选 `fee_terms=`（(date, code)->制度字典），逐笔用该制度复算费用与现金；`yearly` 由实际月份年份推导（不再硬编码 2020-2022，十年账户返回 2015/2016）。
- 复核：`TenYearAccountSampleTest::test_shared_cost_crosscheck_reconciles_ten_year_account` 用共享核算复算 2015-2016 样例两身份——费用分量与 `fees_paid` 一致、`transfer` 分量覆盖面额制金额、`yearly` = {2015, 2016}。T2 的十年运行可直接 `account_metrics(account, inputs, friction, fee_terms=ten_year_fee_terms)` 做费用对账。

范围界定：`account_metrics` 的十年可用性仅限「费用/现金/净值/月度-年度收益可由显式 `fee_terms` 复算」这一路径（`yearly` 已改为按实际月份年份推导，实测 2015-2016 样例返回 {2015, 2016}）；更细的持仓/可卖量/逐日净值重算仍以 `experiments/ten_year_account_audit_20260913.py` 为准，`r0_mechanism_cost_pilot` 其余 TRAIN 专用入口（`main` 的 9 策略 + 3 费用压力、`train_fee_terms` 日期守卫）保持冻结不变。



### 2026-09-13 空分红摘要修复主审终核（当前状态）

**修复审核PASS：D-7最后一项空分红摘要缺口关闭，本轮列出的代码整改项均已关闭。** 主审亲测6项ChunkSatisfied测试通过；独立原例错误摘要/错误行数拒绝、合法空日通过；199真实空日零拒绝。新代码/测试摘要与提交复核声明一致。证据：`artifacts/ten-year-infrastructure-20260912-1/review-handover-20260913.md`末尾及`review-empty-dividend-fix-20260913.json`。

T1整体仍未完成，阶段状态维持A DONE、B WAITING_REVIEW、C RUNNING；整体阶段审核PASS_WITH_LIMITATIONS，剩余为账户独立核算、G4r、早年账户消费及实际分钟依赖尚未交付，已不包含空分红摘要限制。无需重复修已关闭缺陷；后续提交未交付项证据再验收。T2/T3已验收路径可继续，冻结不变。

### 2026-09-13 最终当前状态（覆盖以上全部“当前状态”段落）

账户能力补交与共享费用核算打通后重新裁决：**T1-A PASS_WITH_LIMITATIONS / T1-B PASS_WITH_LIMITATIONS / T1-C PASS_WITH_LIMITATIONS（限本轮交付面）**，T1 整体仍未完成。

- 已关闭并复核：空分红摘要分支（§10）；G4r 面额制过户费（能力 + 实际计费 + 独立复算，§11.1/§11.6）；2015-2016 分红账户级消费（§11.6）；账户现金/费用/持仓/公司行为样例与独立重算（§11.3）；共享费用核算可复算十年账户（§11.7）。
- 仍未交付：十年全量（2015-2024）账户；2015-2019 执行语义（T2 登记项）；2020+ 分钟订单依赖。
- 不变：2025 以后与生产发布冻结、统计 UNKNOWN、晋级 BLOCK；不自动授权日线成交替代分钟。
- 当前身份与命令见 §2.1/§5/§11.5-11.7；复核记录 `artifacts/ten-year-infrastructure-20260912-1/review-account-20260913.md`（+`-evidence.json`）。


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
