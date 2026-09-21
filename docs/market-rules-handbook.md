# A 股交易规则机读手册 v1（汇编）

- 编制日：2026-09-17（素材含截至 2026-09-18 的仓库记录）。
- **本手册是汇编非立法**：只把仓库内已有证据支撑的规则事实集中登记，不新增、不修改、不裁定任何规则。P3（账户级回测）与 P4（计划生成器）实现时必须**逐条回源验证**后再消费；引用条目不得替代读源文件。
- 本手册**不构成实盘依据**；生产发布与 2025 年及以后数据仍冻结。
- 事实条目带唯一 ID（`fee-*` / `trade-*` / `corp-*` / `pit-*` / `unit-*` / `bound-*`），每条后附来源（仓库相对路径 + 节/更新次序或 JSON 键）。仓库**无证据**的常识性条目集中放在 §7 UNVERIFIED 清单，一律不得当作已验证使用。
- 修改约定：新增事实必须同时给出可回源的证据路径；与现有条目冲突时新增条目并在旧条目标注"被取代"，不原地改写历史口径。

来源缩写（全路径见括号内首次出现）：

| 缩写 | 路径 |
|---|---|
| DEC | `docs/decisions/2026-09-17-rqalpha-account-engine.md` |
| COV | `docs/DATA_COVERAGE.md` |
| SRC | `docs/DATA_SOURCES.md` |
| FEES | `docs/research/exp-20260917-fee-recost.md` |
| PLAN | `docs/plans/daily-short-term-rebuild.md` |
| SCOUT | `docs/research/exp-20260917-event-data-scout.md` |
| NEGSYN | `docs/research/exp-20260917-negative-synthesis.md` |
| R6-PREREG | `docs/research/exp-20260917-p2r6-etf-rotation-prereg.md` |
| R6-RES | `docs/research/exp-20260917-p2r6-etf-rotation.md` |
| CFG-R1 | `configs/experiments/p2-first-screen.json` |
| CFG-R6 | `configs/experiments/p2r6-etf-rotation.json` |
| CFG-R7 | `configs/experiments/p2r7-etf-exposure.json` |
| DEEPSCAN | `data/_meta/deep-scan-20260917/README.md` |

---

## 1. 费用

### 1.1 现行账户费率（用户实参，2026-09-17 确认；P3 起生效）

- `fee-001`：佣金**万 1 全包（已含税费）**；P3 费用模型**不单列印花税**；`p2-first-screen.json` 中独立的 `stamp_duty_sell_pct` 项**作废**（注意：该键仍留在 JSON 文件内，消费时以主计划第三次更新①为准）。〔来源：PLAN §6 第三次更新①〕
- `fee-002`：单笔最低佣金 **5 元**。〔来源：PLAN §6 第三次更新①、第四次更新；CFG-R6 `fees.commission_min=5.0`〕
- `fee-003`：ETF 佣金万 1、单笔最低 5 元（用户确认，R6 执行前修订；费用名义按 20 万登记资金）。早前 FEES 假设节记录的"ETF 佣金万 1 无最低"为重估假设、已被此确认取代。〔来源：PLAN §6 第五次更新③ P2-R6 节、第七次更新③；CFG-R6 `revision_note`；FEES §假设〕
- `fee-004`：总资金 **200,000 元**（费用与仓位名义口径）。〔来源：PLAN §6 2026-09-17 用户实参、第四次更新②〕
- `fee-005`：ETF 场内交易**免印花税**（登记为制度事实）。〔来源：R6-PREREG §5；CFG-R6 `fees.stamp_sell_pct=0` 及 `disclosure`〕
- `fee-006`：ETF **免过户费**（登记为制度事实）。〔来源：R6-PREREG §5；CFG-R6 `fees.transfer_fee_pct=0`〕
- `fee-007`：ETF 最小变动价位 tick **0.001 元**（制度事实；仅登记备用，策略级回放按开盘价成交）。〔来源：R6-PREREG §5；CFG-R6 `fees.tick_registered_only=0.001`〕
- `fee-008`：滑点：P2 各轮为 0；P3 按三档敏感性计入（0 / 中 / 高档，具体比例在 P3 运行前按样本 ATR 定档登记），优势在高档下消失的方向按淘汰规则处理。〔来源：PLAN §3 P3；CFG-R6 `fees.slippage=0`〕
- `fee-009`：股票过户费在 P2 全部研究中**两侧均未计**（CFG-R1 披露约 0.001% 量级 omitted；FEES 重估口径相同）。〔来源：FEES §假设、§限制；CFG-R1 `fees.disclosure`〕
- `fee-010`：股票与 ETF 的**费用模型分开登记**。〔来源：PLAN §3 P2-R6 节〕
- `fee-011`：研究结论必须标注"万 1 全包"口径下的适用性。〔来源：PLAN §3 P3〕

### 1.2 历史分段费率表（P2 R1–R5 原口径）

- `fee-012`：历史费用按下表分段（佣金为**保守假设的当时线上零售费率，不是用户实况**；印花税段为制度事实）：

| 生效自 | 佣金（单边） | 最低佣金 | 印花税（卖出单边） |
|---|---|---|---|
| 2015-01-01 | 0.03%（万 3） | 5 元 | 0.1%（千 1） |
| 2018-01-01 | 0.025%（万 2.5） | 5 元 | 0.1% |
| 2020-01-01 | 0.02%（万 2） | 5 元 | 0.1% |
| 2022-01-01 | 0.015%（万 1.5） | 5 元 | 0.1% |
| 2023-08-28 | 0.015%（万 1.5） | 5 元 | 0.05%（万 5） |

〔来源：CFG-R1 `fees.schedule`、`fees.disclosure`；PLAN §6 第三次更新②〕

- `fee-013`：印花税卖方制度分段：**2023-08-28 前 0.1%、2023-08-28 起 0.05%**（买方免）。〔来源：FEES §假设、§结果；CFG-R1 `fees.disclosure`（"stamp duty segments are institutional facts: 0.1% sell until 2023-08-27, 0.05% from 2023-08-28"）〕
- `fee-014`：禁止用当前费率平推 2015–2024 历史（P2 历史筛选费用口径定为仅历史分段费率）。FEES 重估把现行印花税 0.05% 外推全历史是**显式假设**（"按今天的费率交易要花多少"），会低估 2015–2023-08-27 实际费用。〔来源：PLAN §6 第三次更新②；FEES §假设、§限制〕
- `fee-015`：FEES 重估结果（178,724 笔逐笔复现校验后）：实况口径总费用 -27.1%；2023-08-28 及以后卖出的 24,892 笔（13.9%）反而劣化（旧佣金 1.5bp < 重估假设 2.5bp、印花税两侧同为 5bp）；无一配置由负转正。〔来源：FEES §结果、§结论；PLAN §6 第七次更新②〕

### 1.3 最低佣金对小单的费用放大（P3/P4 必读）

- `fee-016`：佣金万 1 + 最低 5 元时，**单笔 5 万元名义恰达最低线**（5 元 = 5 万 × 万 1）；单笔不足 5 万元的成交（如两批各 2.5 万的分批执行）实际佣金比例被抬高（数值推导：2.5 万单批 → 5/25,000 = 万 2，翻倍），P3 分批对照**必须计入**。〔来源：PLAN §6 第四次更新⑤（原句）；放大倍率为本手册按 fee-001/fee-002 数值推导〕
- `fee-017`：实证：R6 基准 B1 早年腿多名义小（每腿 < 5 万）时最低佣金生效、抬高 B1 费用（Top3 每笔 ≈6.67 万时最低不生效）。〔来源：R6-RES §成交情况表注；R6-PREREG §5〕

---

## 2. 交易约束与撮合

### 2.1 T+1 与可卖数量

- `trade-001`：**收盘信号最早下一交易日执行**（收盘生成信号 → 次一交易日开盘成交是仓库统一执行口径；不假设日内有利路径）。〔来源：AGENTS.md §3、§4；SCOUT §2 共同纪律；R6-PREREG §4.2〕
- `trade-002`：**不允许 A 股当日新买仓位当日卖出**（T+1 硬约束）。〔来源：AGENTS.md §4〕
- `trade-003`：研究层处理口径：**统一按 T+1，含制度上可 T+0 回转的品种（如黄金 ETF）——保守统一并披露**（月频下无实质差异）；**卖出款项次一交易日可用**（保守）。T+0 品种清单仓库未登记（见 `unv-004`）。〔来源：R6-PREREG §4.2；CFG-R6 `execution_semantics.t_plus`；CFG-R7 同〕
- `trade-004`：rqalpha 内置 T+1；bundle 接线冒烟 12/12 断言含"T+1 拒单"通过（验证的是接线可用性，不是引擎规则正确性）。〔来源：DEC §决策、§未决事项（2026-09-17 冒烟结果）〕

### 2.2 整手与零股

- `trade-005`：整手约束已在冒烟中断言（"整手拒单/折整"）。〔来源：DEC §未决事项（2026-09-17 冒烟结果）〕
- `trade-006`：与单标的上限叠加的量化后果：20 万资金、单标的上限 50,000 元（25%）下，**股价约高于 500 元的标的无法建仓一手**。〔来源：PLAN §6 第四次更新②〕
- `trade-007`：P2-R6/R7 研究层使用零股（fractional shares、无整手约束）简化并披露；P3 账户级必须恢复整手。〔来源：CFG-R6 `execution_semantics.slot_accounting`；CFG-R7 同〕

### 2.3 涨跌停（分品种；仓库证据等级标注）

- `trade-008`：**股票主板 ±10% 有实测支撑**：`xiaodefa/stk_limit` 的 `limit_price` 单位为元，"与前收盘 ±10% 关系成立，confidence=high"（主板池实测）。〔来源：DEEPSCAN `xiaodefa/stk_limit` 行；COV 读取层强制规则 6〕
- `trade-009`：股票涨跌停价的注册主源：tushare `stk_limit` 批次 `20260917-r1`（9,705,448 行；bundle v2 断言"股票涨跌停 = stk_limit 逐值"）；源缺口：**5 个零行日**（该 5 日 NaN 规则成立）。〔来源：DEC §未决事项（v2 双签）；PLAN §6 第七次更新⑤〕
- `trade-010`：ETF 涨跌停**按品种 10% / 20% 两档**——此为预登记记载；`stk_limit` 不覆盖基金；其规则准确性在预登记中列为"待确认项"。P3 使用前须回源确认。〔来源：R6-PREREG §4.2、§8 待确认项；CFG-R6 `execution_semantics.limit_proxy`〕
- `trade-011`：研究层代理：开盘价相对前收 **≥ +9.5% 不买入、≤ -9.5% 不卖出**（双向统一保守阈值，因品种两档差异而设；替代方案是 stk_limit 真实价，仅股票可用）。〔来源：CFG-R6 `execution_semantics.limit_proxy`、`entry`、`exit`；R6-PREREG §4.2；PLAN §6 第五次更新②〕
- `trade-012`：入场阻断语义：t+1 无开盘（停牌）或开盘 ≥ +9.5% → 跳过，并按排名顺延补位（次优非持仓候选）；无候选则槽位留现金。〔来源：CFG-R6 `execution_semantics.entry`〕
- `trade-013`：出场阻断语义：停牌或开盘 ≤ -9.5% → **顺延至下一可交易日开盘**卖出，期间按最后可得收盘计价。〔来源：CFG-R6 `execution_semantics.exit`〕
- `trade-014`：个股 P2 轮同口径：`block_limits=true`、`limit_pct=0.1`（开盘涨跌停阻断）。〔来源：CFG-R1 `execution`〕
- 创业板/科创板股票 ±20%、ST ±5%、北交所 ±30% 等分代幅度：仓库**无证据**，见 `unv-001`。

### 2.4 停牌与退市

- `trade-015`：停牌日**无行情行**（fund_daily / baostock 日线均无该日行）；信号日停牌者不参与排名。〔来源：R6-PREREG §4.2；CFG-R6 `universe.u3_pit_rules.quoted_at_t`〕
- `trade-016`：窗口特征按各标的**自身行情行**滚动（t−k 指 k 个自身报价行之前，停牌自然跳过）。〔来源：CFG-R6 `universe.window_features`〕
- `trade-017`：强制退市退出语义：持仓标的行情终止（退市）→ 按**最后可得收盘价强制卖出并计卖出费**，计入并归属损益；R6 实测强制退市退出 0 笔。〔来源：CFG-R6 `execution_semantics.forced_delist_exit`、`universe.u4_delisting`；R6-RES §成交情况〕
- `trade-018`：bundle 中停牌与 ST 为 int 日期集合（`suspended_days.h5` / `st_stock_days.h5`）；其来源（复用 P2 掩码 vs 从 raw 重算）在决策记录中仍为**开放项**，以 bundle manifest 为准。〔来源：DEC §接线路线、§未决事项；PLAN §6 第六次更新①〕
- `trade-019`：历史 ST 状态仅 baostock `isST` 一源（已披露单源限制），复核用 tushare `namechange` 抽查。〔来源：PLAN §6 2026-09-17 单源风险披露〕

### 2.5 时段与撮合纪律

- `trade-020`：连续交易时段 **09:30–11:30 / 13:00–15:00**：1 分钟包每交易日 241 根（09:30 一根 + 上述两段共 240 根），午休不跨组——此为数据形态证据（集合竞价时段无记载，见 `unv-002`）。〔来源：SRC §1 陷阱 1〕
- `trade-021`：用户操作时段实参：**交易日全时段均可人工执行**，不限于开盘。〔来源：PLAN §6 第四次更新⑤〕
- `trade-022`：撮合纪律：日线触价不等于必然成交；不默认有利的日内路径；不凭 OHLC 推断多次有利成交；基础日线撮合采用保守且明确的假设并报告日内路径歧义。〔来源：AGENTS.md §4；PLAN §3 P3〕
- `trade-023`：歧义成交核对：对通过的少量候选及歧义成交，用允许年份内的分钟数据局部核对；**利润主要依赖歧义成交则不予通过**。〔来源：PLAN §3 P3〕
- `trade-024`：引擎语义豁免（如实登记）：rqalpha 内置 A 股规则（T+1、涨跌停、印花税、整手、禁止裸卖空）经用户豁免不复验；凡结论依赖 rqalpha 撮合/费用语义的研究记录**必须标注"引擎语义未独立复验（用户豁免）"**；生成任何实盘计划（`artifacts/plans/`）前必须补最小对账（同组订单在 rqalpha 与 backtrader 或手算间一致）。〔来源：DEC §用户豁免条款；PLAN §6 第五次更新①〕
- `trade-025`：bundle 占位与缺口（P3 消费红线）：`yield_curve.h5` 全 0；v2 中 `indexes.h5['000001.XSHG']` 探测键占位警示**已被 v2.1 真实数据作废**（五指数均为 tushare index_daily 20260917-r1，各 2,431 日）；其余以 bundle manifest `placeholders` 为准。〔来源：DEC §未决事项（冒烟结果、v2、v2.1）〕

---

## 3. 公司行动

### 3.1 分红派息（股票）

- `corp-001`：分红事件时间线三日期（dividends.h5 行内字段）：**登记日 `book_closure_date` / 除权除息日 `ex_dividend_date` / 到账日 `payable_date`**；行结构 = `[book_closure_date(i8), dividend_cash_before_tax(f8), ex_dividend_date(i8), payable_date(i8), round_lot(i8)]`，按 `ex_dividend_date` 排序；日历与行内日期为 8 位 YYYYMMDD。〔来源：DEC §未决事项（契约查证）〕
- `corp-002`：金额口径：`dividend_cash_before_tax` 语义为**每手（round_lot 股）税前现金**；tushare `cash_div` 为**每股**口径（已对真实公告核对），ETL 须 ×round_lot 入库。〔来源：DEC §未决事项（契约查证、A12）〕
- `corp-003`：分红批次身份：`20260913-r2` 只含 2015–2017，`20260909-r3` 含 2018+；**必须按日期并批**，只用 r2 会丢 2018+ 全部分红。〔来源：DEC §未决事项（契约查证）〕
- `corp-004`：已知口径瑕疵：`dividend_cash_before_tax` 沿用 tushare `cash_div`，其中 **2,095/42,561 行**（旧差别化股息税制期，例：000001 20150413 0.1653 vs 税前 0.174）源字段实为**税后**口径；入账偏低属保守方向，登记为已知瑕疵（红利税税率本身无记载，见 `unv-007`）。〔来源：DEC §未决事项（v2 双签）、（v2.1）；PLAN §6 第九次更新④〕
- `corp-005`：分红现金入账已经冒烟断言（"分红现金精确入账"）；股票侧 tushare dividend → dividends.h5 映射已实现并经真实分红断言（A12）。〔来源：DEC §未决事项（冒烟结果、A12）〕

### 3.2 送转与 ETF 份额折算

- `corp-006`：rqalpha split 语义：数量 **×ratio**（按拆股/折算前数量入账，ROUND_HALF_UP），引擎逐 bar 以原始 close 重标记；ex_cum_factor 仅影响序列视图，不影响持仓估值路径。〔来源：DEC §未决事项（P3 硬前置、v2.1）〕
- `corp-007`：**ETF 份额折算事件规则（一次定死）**：fund_adj 单日因子比 **≥1.1 或 ≤0.9** 视为份额折算，split_factor 行 ratio = 因子比；**(0.9, 1.1) 内跳变视为分红类、不入 split**。〔来源：DEC §未决事项（v2.1）〕
- `corp-008`：折算事件清单：**90 事件 / 76 ETF**，位置在 bundle manifest `data_quality.etf_split_events`（数据集 `data/processed/rqalpha-bundle-v2-1-20260918/`）；四个已知案例全部命中：510230 2020-08-17 ×4.916019、512670 2021-08-23 ×2.0044、512690 2021-05-17 ×1.9614（≈1:1.96）、2021-12-31 ×1.359743（≈1:1.36）。〔来源：DEC §未决事项（v2.1）；CFG-R6 `preflight.fund_adj_coverage.suspect_examples`〕
- `corp-009`：折算账户级验收（A15 专项）：持有 510230 跨折算日，数量 300→1,475，折算日市值连续（raw 不处理路径为 -78.8% 权益蒸发）——**折算不处理 = 静默蒸发且无报错**，此为 P3 硬前置的原始发现（红队 R3-1）。〔来源：DEC §未决事项（P3 硬前置、v2.1）〕
- `corp-010`：折算日遇停牌的行为：159919 2019-01-11 折算日无 bar，split 行照常生效、次一真实 bar 起市值正确；折算当日按停牌陈旧价高估一日（已披露）。〔来源：DEC §未决事项（v2.1）〕

### 3.3 ETF 现金分红（源缺口如实登记）

- `corp-011`：fund_adj **覆盖 ETF 现金分红**（抽样证据：510880.SH 十次因子跳变全部为 1 月中旬年度分红除息日、跳变日调整收益平滑 |apct|≤2.5%）；512690 两次份额折算调整收益平滑（+2.0%/−0.8%）。〔来源：CFG-R6 `preflight.fund_adj_coverage.sampling_conclusion`；R6-RES §3〕
- `corp-012`：**ETF 现金分红不作为现金事件入账**：(0.9,1.1) 内跳变视为分红类不入 split，即 bundle 路径下 ETF 现金分红只体现在 fund_adj 因子中、不产生现金入账（"ETF 现金分红不付的既有披露不变"）。ETF 现金分红的独立分红源**仍缺**（v2 前登记"ETF 分红与折算口径缺源"，折算半边已由 v2.1 关闭，现金半边维持缺口登记）。〔来源：DEC §未决事项（tushare 映射节、v2.1）〕
- `corp-013`：fund_adj 大比例折算日的已知残差：4 个事件（160615.SZ×2、510230、512670）存在 4–9% 单日残差捕获误差，登记为已知瑕疵。〔来源：CFG-R6 `preflight.fund_adj_coverage`；R6-RES §3〕
- `corp-014`：复权口径主从：**fund_adj 为注册权威调整源**；ths/tx 前复权批次降级为交叉复核源（其加性前复权方法在折算/分红案例上与 fund_adj 系统性分歧：512690 −6,945bps、510880 −1,837bps）。〔来源：R6-RES §3；PLAN §6 第五次更新⑤〕
- `corp-015`：股票复权因子已知缺陷：`xiaodefa/adj_factor` 的 **600069.SH** 因子在 6.415 与 0.6604 间反复振荡——人工复核前**禁止用于任何复权计算**。〔来源：COV 读取层强制规则 5〕
- `corp-016`：ETF 复权因子源缺口：**159842.SZ** 无 fund_adj 行（U1 白名单 1,168 = 1,169 − 1）。〔来源：PLAN §6 第七次更新⑤；CFG-R6 `preflight.u1_counts`〕
- `corp-017`：股票复权契约验证：除权日连续性合同测试 + tushare 双源因子对照 59/59 + 价格复核 3/3（P1，`src/quant/data/adjustment.py`）。〔来源：PLAN §3 P1〕
- `corp-018`：ETF 侧复权恒等式（双签数值证明）：bundle `ex_cum_factor` ≡ fund_adj 因子（仅加 (0, 1.0) 锚点）。〔来源：DEC §未决事项（v2 双签）〕

---

## 4. 信息时点（PIT）

- `pit-001`：**统一可得日口径：`ts_available` = `ts_knowledge` 的次一交易日**（收盘信号最早下一交易日执行的同一时间口径）；两融/龙虎榜天然 +1，其余按收盘纪律统一 +1；一切时间判断只用 `ts_available`。〔来源：SCOUT §2、§3〕
- `pit-002`：事件可得日语义表（逐批次，来源均为 SCOUT §2 表）：

| 批次 | ts_knowledge（可得日） | 发布滞后语义 | 事件日 | ann−event 中位 |
|---|---|---|---|---|
| forecast 业绩预告 | ann_date | 公告即知 | end_date（报告期） | +15 天（16.8% 早于期末，合法） |
| express 业绩快报 | ann_date | 公告即知 | end_date | +58 天 |
| repurchase 回购 | ann_date | 公告即知（状态推进逐行披露） | exp_date | −364 天 |
| share_float 解禁 | ann_date | 公告即知 | float_date | −7 天（99.999% 先行） |
| stk_holdertrade 增减持 | ann_date | **事后公告（行为日未知）** | 无 | – |
| top_list / top_inst 龙虎榜 | trade_date + 1 交易日 | **T 日晚间公布** | trade_date | 0（须 +1 修正） |
| margin_detail 两融 | trade_date + 1 交易日 | **T+1 早晨公布** | trade_date | 0（须 +1 修正） |
| disclosure_date 披露计划 | ann_date | 计划公告即知 | pre_date / actual_date | −35 天（预约日提前可知） |

- `pit-003`：无公告日（ann_date 缺失）的行**直接弃用（fail-closed）**，不插补（本批 9 个含日期批次实测缺失率 0%，该规则纯防御）。〔来源：SCOUT §2、§5.2〕
- `pit-004`：财务披露滞后纪律：**报告期数据在期末后 90 天才对回测可见**。〔来源：COV §财务与日指标〕
- `pit-005`：express 快报提供比 90 天纪律更早的基本面确认点（ann−end 中位 +58 天，0% 早于报告期）。〔来源：SCOUT §1.2〕
- `pit-006`：forecast 同键多版本：update_flag=1（修正预告）占 31.7%；**最早披露版本为可用信号**，同键冲突字段 fail-closed，禁 first-non-null 合并；ann_date < end_date 的 16.8%（深市年报预告在报告期结束前披露）属合法现象，以 ann_date 为可得日即无未来函数。〔来源：SCOUT §1.1、§5.4〕
- `pit-007`：龙虎榜（top_list/top_inst）与两融（margin_detail）**覆盖仅 2019 年起**，事件结论不得外推到 2015–2018；跨事件族统一比较最长 2019–2024。〔来源：SCOUT §1.6–1.8、§5.1〕
- `pit-008`：`index_member_all` 行业归属为**现时单点快照、无每股切换历史**——不能重建 2015–2024 任一历史时点行业归属，直接当历史行业因子会引入幸存者/重分类偏差。〔来源：SCOUT §1.10、§5.3〕
- `pit-009`：两融标的资格历史缺失：现库只有"现时是两融标的"的部分证据，且混入 ETF（51/15 开头）与北交所标的，映射股票池须按前缀过滤；两融标的池是时点变化集合，历史资格是缺口。〔来源：SCOUT §1.8、§5.5〕
- `pit-010`：share_float 的未来解禁（float_date > 公告日，float_date 2025–2026 且在 2024 前已公告）可用作"已知未来计划"型特征，但**不得用于 2025+ 窗口的收益标签**。〔来源：SCOUT §1.4〕

---

## 5. 单位与数据格式换算

- `unit-001`：**fund_daily（ETF 日线）：vol = 手 × 100 股、amount = 千元 × 1000 元**（bundle v2.1 双签数值证明：`volume = fund_daily.vol[手]×100`、`total_turnover = amount[千元]×1000`；另经 VWAP 交叉验证 implied_vwap/中价中位 = 1.0，n=2800）。〔来源：DEC §未决事项（v2 双签）；CFG-R6 `preflight.amount_vol_units_measured`〕
- `unit-002`：**index_daily（指数日线）：vol = 手、amount = 千元**（与股票/基金同约定；双签实测：与 bigquant 000300 重叠 826 行 close 恒等 ≤9.1e-13、volume/vol ≡100、amount 比 ≡1000）。〔来源：DEC §未决事项（v2.1）；COV 读取层强制规则 6〕
- `unit-003`：`tushare/daily_basic`：`close` = 元（与 baostock 不复权收盘一致）、`total_mv` = 万元（confidence=high）。〔来源：COV 读取层强制规则 6；DEEPSCAN `tushare/daily_basic` 行〕
- `unit-004`：`xiaodefa/moneyflow`：金额列 = **万元**量级（confidence=medium）。〔来源：COV 读取层强制规则 6；DEEPSCAN `xiaodefa/moneyflow` 行〕
- `unit-005`：`margin_detail`：余额列 = **元**。〔来源：COV 读取层强制规则 6；SCOUT §1.8〕
- `unit-006`：`xiaodefa/stk_limit`：`limit_price` = **元**。〔来源：COV 读取层强制规则 6；DEEPSCAN `xiaodefa/stk_limit` 行〕
- `unit-007`：1 分钟包 `user_minute_1m`：`vol` = **股**、`amount` = **元**；价格为 float32 分币编码（须按分还原后再用）。〔来源：SRC §1〕
- `unit-008`：bundle 数据格式：日线 bar 与 ex_cum_factor/split 的日期 = `convert_date_to_int`（YYYYMMDDHHMMSS，日级时间位为 0，即 YYYYMMDD×10⁶）；`trading_dates.npy` 与 dividends 行内日期 = 8 位 YYYYMMDD。〔来源：DEC §未决事项（契约查证）〕
- `unit-009`：价格口径契约：**调整价（×复权因子）用于信号与收益，不复权价用于可交易性判断（价格下限、涨跌停代理）**；前复权价格不得直接充当历史实际成交价；停牌行因子为空 → 收益为空（保守）。〔来源：CFG-R1 `data.price_convention`；AGENTS.md §4〕

---

## 6. 数据与研究边界

- `bound-001`：**冻结边界 2024-12-31**：读取层必须硬过滤 `>2024-12-31` 的行（几乎所有在市批次拉到 2026-09，深扫 457/465 blocker 为此类）；涉及 tx/ths/em_fin 全部批次、xiaodefa 44 个 dataset、bigquant 2025/2026 目录等。〔来源：COV 读取层强制规则 1〕
- `bound-002`：**2025-01-01 及以后为禁区**：不用于研究、筛选、调参或绩效查看；解锁需要用户明确决定。〔来源：AGENTS.md §3；PLAN §1〕
- `bound-003`：标签、成交与持有期**不得跨越冻结边界**；跨 2024-12-31 的事件由筛选层标记 horizon_out_of_range。〔来源：AGENTS.md §3；CFG-R1 `validation.freeze`〕
- `bound-004`：股票池板块排除（历史时点状态过滤）：科创 **688/689**、北交所（前缀 **4/8**）、**ST/*ST**、停牌；第四次更新起研究池再剔除创业板 **300/301/302**、限定沪深主板；指数/非个股代码须显式剔除（曾发生 sz.000905/000852 两只主板股票被误当指数的登记更正）。〔来源：PLAN §1、§6 第四次更新①、更正节；CFG-R1 `universe_filter`；SCOUT §0 标的池参照〕
- `bound-005`：**创业板权限冲突待用户澄清（P3/P4 前必须解决）**：第四次更新登记"无创业板权限"（股票池剔除 300/301/302）与 2026-09-17"创业板/科创板 ETF 权限确认有、R6 池纳入"两处登记冲突，未代改股票池规则。〔来源：PLAN §3 P2-R6 节、§6 第七次更新④、第九次更新⑧；CFG-R6 `revision_note`；R6-RES §8.5〕
- `bound-006`：ETF 池规则（R6 冻结）：U1 白名单 **1,168 只**（fund_basic 规则 + 有 fund_daily 行 + 有 fund_adj 行；registry 是 2026-09-09 快照、非 PIT）；U2 剔除债券/货币/REITs/混合型 + QDII 关键词表；U3 PIT 规则：上市满 **120 个交易日**（日历索引算术）+ 自身 ≥120 条行情行 + 近 20 行成交额中位 ≥ **50,000 千元（=5,000 万元）** + 信号日有行情 + 当日因子可得（asof-backward）。〔来源：CFG-R6 `preflight`、`universe`；R6-PREREG §3〕
- `bound-007`：**列序不可信**：xiaodefa `moneyflow`（1,378/3,088 文件列序翻转）、`sw_daily`、`cyq_perf`、`stk_limit` 存在文件间列序不一致——**按列名归一，禁止按位置拼接**。〔来源：COV 读取层强制规则 2〕
- `bound-008`：tx 跨页重叠：全部 176 个多页批次存在固定分页边界重复 K 线——按 `(symbol, date)` 去重。〔来源：COV 读取层强制规则 3〕
- `bound-009`：表头校验：存在首行为空的文件（实证 `xiaodefa/stk_limit/20260913-bulk1/chunk_20220705.csv`）——载入时校验首行非空，空表头文件的列名须显式提供。〔来源：COV 读取层强制规则 4〕
- `bound-010`：**2015–2024 已被旧项目反复查看**：结论是滚动历史验证，不是全新样本外；冻结区也未在未审计历史访问前宣称从未查看。〔来源：CFG-R6 `segments.history_note`；AGENTS.md §3；NEGSYN §通用口径〕
- `bound-011`：时间划分纪律（R6/R7 冻结版）：dev 2016–2020（2015 预热年仅作指标回看）、validation 2021–2022、test 2023–2024 **一次性**（test 失败即方向死亡，不得回头改参数或换段重跑）；单连续模拟切片、边界市值结转（不强制平仓）。个股 P2 轮划分：dev 2015–2020 / validation 2021–2024，出口端标签隔离（dev 事件必须在 2020-12-31 前退出）。〔来源：CFG-R6 `segments`；CFG-R7 `gates`；CFG-R1 `validation`〕
- `bound-012`：凭据仅放 `~/.quant-credentials/`（tushare token 在 `~/.quant-credentials/tushare-token`）；真实账户与日志不得含 token，不将私有输入发送外部服务；tushare 批次验收含"token 零泄漏"断言。〔来源：AGENTS.md §3；PLAN §6 第四次更新、第七次更新⑤〕

---

## 7. UNVERIFIED 清单（仓库无证据，禁止当作已验证）

以下条目是 A 股常识、但**本仓库没有任何文档/数据证据**支撑其数值或语义。P3/P4 若需使用，必须先补充权威来源登记（新开配置或决策记录），不得直接引用本清单当作已验证。

- `unv-001`：**分板块股票涨跌停幅度**：创业板股票 ±20%、科创板股票 ±20%、ST/*ST ±5%、北交所 ±30%。仓库仅实测支撑主板 ±10%（`trade-008`）与 stk_limit 逐值（`trade-009`）；ETF 10%/20% 品种差异只有预登记记载且列为待确认项（`trade-010`）。因股票池排除规则，这些板块从未进入研究，也无 bundle 级断言。
- `unv-002`：**集合竞价时段与撮合规则**（开盘集合竞价 09:15–09:25、收盘集合竞价 14:57–15:00、竞价成交价确定规则）。仓库只有连续时段的分钟数据形态证据（`trade-020`）与 `stk_auction_c/o` 两个数据集存在性，无任何竞价规则记载。
- `unv-003`：**股票过户费具体费率及其历史调整**。仓库仅登记"未计/约 0.001% omitted"（`fee-009`）与"ETF 免"（`fee-006`），无确切数值、无分时段表。
- `unv-004`：**ETF T+0 回转交易的品种清单**（跨境/债券/货币/黄金等）。仓库仅登记"统一按 T+1 处理、含 T+0 品种"的保守口径（`trade-003`），未列举哪些品种制度上可 T+0。
- `unv-005`：**卖出零股/碎股规则**（买入须整手、卖出零股须一次性卖出的细则）。仓库只验证了"整手拒单/折整"冒烟断言（`trade-005`），无卖出侧规则记载。
- `unv-006`：**股票最小变动价位 tick = 0.01 元**。无记载（ETF tick 0.001 有登记，见 `fee-007`）。
- `unv-007`：**差别化红利税税率**（按持股期限）与分红实际到账银行延迟。仓库只有 dividends 行的 `payable_date` 字段与税前/税后口径瑕疵披露（`corp-001`、`corp-004`），无税率表。
- `unv-008`：**新股/上市首日涨跌幅与临时停牌规则**。无记载（上市历史仅作为池准入条件出现，见 `bound-006`）。
- `unv-009`：**ST/风险警示板交易限制细则**（幅度 5% 之外：日内换手限制、退市整理期安排等；top_inst 样本中出现过"退市整理期"上榜原因，但无规则记载）。
- `unv-010`：**大宗交易、盘后固定价格交易（科创/创业板）规则**。无记载。

---

## 附：P3/P4 消费顺序建议（非规则）

1. 先读 §7 UNVERIFIED 与 `bound-005`（创业板权限冲突）：这两类是唯二"实现前必须先补决策"的阻塞项。
2. 费用按 §1 现行实参建模；历史分段表只用于复现 P2/R1–R5 原口径，不用于 P3。
3. 涨跌停：股票用 stk_limit 真实价（注意 5 个零行日 NaN），ETF 在 `unv-001`/`trade-010` 关闭前只能沿用 9.5% 代理并披露。
4. 公司行动：股票分红按 `corp-001`–`corp-005` 契约；ETF 折算按 `corp-007`–`corp-010`；ETF 现金分红缺口（`corp-012`）在结果中披露。
5. 一切事件/信号时间判断只用 `ts_available`（`pit-001`）；引用 rqalpha 语义处按 `trade-024` 标注豁免状态。
