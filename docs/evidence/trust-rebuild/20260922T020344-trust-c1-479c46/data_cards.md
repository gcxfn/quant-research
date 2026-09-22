# C1 数据卡（Dev 沙箱逐类登记）

- run：`20260922T020344-trust-c1-479c46`
- 沙箱数据集：`dev-sandbox-20260922`（`data/processed/dev-sandbox-20260922/`，manifest 为唯一身份来源）
- 代码版本：`ae226d964b1ea1dccfb60a42ae943c6da8a179e6`（工作树含未提交批次，见 C0 证据）
- 接口合同：本目录 `interface_contract.json`（`contract_sha256` 已写入 dataset_manifest）
- 所有数字来自本目录 `run_records/` 中记录的实跑命令；未实测的量写 unknown。

> 阅读方式：每张卡先给「能用来做什么 / 不能用来做什么」，再给字段与缺陷。
> 缺陷只引用 `docs/DATA_SOURCES.md`、`docs/DATA_COVERAGE.md`、`docs/MIGRATION_REPORT.md`
> 与本次实测，不重述未验证的旧结论。

---

## 0. 混合年份文件过滤口径（C0 access_ledger AL-02 强制项）

**事实：** 原始/派生行情文件物理上含 2021–2024（部分还含 2025+），旧运行的做法是
「载入整表后按 `DEV_START/DEV_END` 过滤 + `assert_frozen` 断言」（AL-02 登记为
「程序化过滤而不是物理隔离」）。C1 建立受控导出层：

| 环节 | 旧做法（C0 之前） | C1 做法 |
|---|---|---|
| 数据可见性 | 运行可读混合年份文件，靠代码断言不越界 | 研究运行只挂载 `dev-sandbox-20260922`；manifest 外路径与其它 `dataset_id` 一律拒绝 |
| 越界检测 | 内存过滤，错误路径依赖实现正确 | 导出时逐文件重扫并在 manifest 声明窗口内硬断言；读取后再断言一次实测最大/最小日期 |
| 证据 | 无导出清单 | `dataset_manifest.json` 记录源文件 SHA256、过滤规则、行数、实测日期范围、输出 SHA256、`no_2021plus_verification` |

**导出规则（逐数据集实测，`no_2021plus_verification.passed=true`）：**

| 数据集 | 过滤规则 | 实测最大日期 |
|---|---|---|
| bars_daily | `2015-01-05 <= date <= 2020-12-31` | 2020-12-31 |
| bars_daily_warmup | `2014-03-01 <= date <= 2015-01-04`（用途=特征历史，不计绩效年份） | 2014-12-31 |
| bars_halfday | `2015-01-05 <= date <= 2020-12-31`，逐年分区 | 2020-12-31 |
| limit | 只读取文件名在 Dev 窗口内的逐日 chunk，再按日期过滤 | 2020-12-31 |
| forecast_event | 只读取与 2018-09..2020-12 相交的月 chunk，再按 `ann_date` 过滤 | 2020-12-31 |
| dividend | `ex_date` 落在 Dev 窗口 | 2020-12-31 |
| split_factor | `ex_date` 落在 Dev 窗口 | 2020-12-31 |

导出的这些文件合计 19,501,006 行 / 374,236,283 字节（manifest `totals`），
峰值内存 1,040 MB（导出器自测；`run_records/c1_export_dev_sandbox.json` 独立采样 1,029 MB），
耗时 13.45 s。没有超过 2 GB，因此不需要降级为最小集，半日线按原计划纳入。

**残留边界（诚实说明）：** 导出工具本身必须能读混合年份源文件——它是 K 角色的受控提取，
不是研究运行。研究运行（含 C1 的审计脚本与权限演示）只走沙箱加载器。
另外「物理隔离」在本机是**同一账号同一磁盘**，任何会话仍可用绝对路径直接打开原始文件；
`enforcement_level=procedural_only` 的结论仍然成立（见 C0 `permissions_review.md`），
C1 只把「正常路径」收窄到沙箱，不能声称已技术上禁止越权。

---

## 1. 日线 bar（`bars_daily` / `bars_daily_warmup`）

**能用来做什么：** 官方日收盘估值与 15:00 锚价、历史池资格判定（板块/ST/停牌/流动性）、
20 日自身交易日标签、ATR 等波动指标。**不能用来做什么：** 11:30 锚价（没有上午收盘）、
订单成交价（成交价来源是半日 bar，不是日线收盘）。

| 项 | 值 |
|---|---|
| 上游 | `data/processed/baostock-daily-20260917/daily_1999_2024.parquet`（源 `data/raw/baostock/daily/`，5552 只，1999-11-10…2026-09-04 原始；派生产物已裁剪到 ≤2024-12-31） |
| 沙箱文件 | `bars_daily_dev.parquet`（4,871,112 行 / 4,187 只 / 4,187 个 symbol）、`bars_daily_warmup.parquet`（528,428 行 / 2,596 只） |
| 列 | `symbol, date, open, high, low, close, preclose, volume, amount, adjustflag, turn, tradestatus, pctChg, isST` |
| 单位 | 价格=元（不复权，`adjustflag` 全为 `'3'`）；`volume`=股；`amount`=元；`turn`=% |
| 板块 | 物理含 `000/001/002/003/300/302/600/601/603/605/688/689`；池过滤在资格层执行，导出层不删（保留可审计性） |

**关键语义**
- `close` = 官方日收盘，是全项目唯一允许作为 mark 与 15:00 锚价的价格（合同：`p3-band-contract.md`；旧 ETF 腿另有 pm-only 路由）。
- `preclose` = 供应商官方前收，用于公司行动守卫（`|preclose×ratio − close(t−1)|/close(t−1) ≤ 2%` 等）。它与
  `user_dataset/` 的「前收盘价」**不保证一致**（DATA_SOURCES §3），不得混用两个来源的前收。
- `tradestatus`：`1`=正常交易，`0`=停牌；历史时点字段。
- `isST`：历史 ST 状态；本项目按 `isST == 0` 过滤，空值按不合格拒绝。
- `adjustflag=3`（不复权）是冻结口径；复权序列须另配因子并登记口径，**不得**用前复权价当历史成交价（AGENTS §4）。

**已实测缺陷 / 已知缺口**
1. 2 行全空价格且 `tradestatus=0`：`sz.000022 2018-12-26`、`sz.000043 2019-12-16`
   （processed `quality.json` 登记；沙箱内实测 `close` 空值行数=2）。保持原样，靠空值传播排除信号。
2. 调整因子未随沙箱导出。上游因子覆盖率差异大：baostock `adjust_factor/` 仅 343 只；
   `xiaodefa/adj_factor` 全市场但 `600069.SH` 因子在 6.415 与 0.6604 间振荡、人工复核前禁止用于复权（DATA_COVERAGE §1.5）。
   → 任何跨公司行动的多日收益必须在 C2/C5 明确登记复权来源与口径，不能用「不复权 close 直接算多日收益」。
3. 单一来源（baostock 官方日线）。`tx/`、`sina/` 是复核源，但与 baostock 不是同一上游封装，也存在未复权/前复权口径差异，
   不能当独立行情来源（DATA_SOURCES §7；`05_test_vectors.md` TV-B31）。
4. 2025+ 行在派生产物里已被裁掉；导出再裁到 2020-12-31。冻结线以上仍由沙箱加载器拒绝。
5. `bars_daily_warmup` 只作特征历史：**不得**据其计算收益标签、账户权益或绩效年份。

**对研究的影响：** 池资格与标签可在此表上复算；任何跨公司行动的收益与估值必须显式使用
`dividend` / `split_factor`（见第 5 卡），否则会出现「不复权价格跳跃被当成收益」。

---

## 2. 半日 bar（`bars_halfday`）

**能用来做什么：** 11:30 决策锚价（`am` 的 close）、半日限价单的穿透判定（`low`/`high`）、
T+1 可卖判定的半日粒度、停牌/缺 bar 判定。**不能用来做什么：** 官方收盘/账户 mark/15:00 锚价。

| 项 | 值 |
|---|---|
| 上游 | `data/processed/halfday-bars-20260918/year=YYYY/bars.parquet`（由 `user_minute_1m/` 全市场 1 分钟包聚合） |
| 沙箱文件 | `bars_halfday/year=2015..2020/bars.parquet`（9,193,283 行 / 4,181 只 / 1,462 个交易日） |
| 列 | `symbol, date, session, open, high, low, close, volume, amount, n_minutes, n_minutes_expected, partial` |
| 单位 | 价格=元（不复权，float32 分币编码按分还原）；`volume`=股；`amount`=元 |
| 分段 | `am`：`trade_time <= 11:30:00`（含 09:30 集合竞价 bar）；`pm`：`trade_time >= 13:00:00`（含 15:00） |

**关键语义**
- 缺行 = 该标的该时段无任何有量 bar → 该时段不可交易（不是价格 0）。
- `open` = 时段内最早有量 bar 的开；`close` = 时段内最晚有量 bar 的收。
- `partial = n_minutes < n_minutes_expected`；`n_minutes_expected` 是该日全市场该时段的 distinct 分钟网格数
  （AM 通常 121、PM 通常 120）。`vol==0` 是 vendor 占位，不进入聚合（DATA_SOURCES §1.3）。
  实测 `partial=True` 占 5,842,201/9,193,283 行（63.6%）——主要来自个股零量分钟被丢弃，**不是**缺 OHLC。

**已实测缺陷 / 已知缺口**
1. **6 个 symbol 有日线但完全没有半日行**（实测差集）：`sh.601268`（92 行日线全部停牌）、
   `sz.000562`（16 行全部停牌）—— 这两个可由「全期停牌、无有量分钟」解释；
   但 `sz.000022`（973 行，仅 282 行停牌）、`sz.000043`（1,208 行，仅 81 行停牌）、
   `sz.300114`（1,462 行，0 行停牌）、`sz.302132`（1,462 行，0 行停牌）**有可交易日却没有半日 bar**。
   其中 `sz.300114` 与 `docs/DATA_COVERAGE.md` 登记的「无任何年份分钟」一致；
   其余 3 只的原因（分钟供应商代码空间缺口、代码变更、或提取遗漏）**unknown**，C1 不归因。
   影响：这些标的没有半日执行路径，回测中只能表现为「缺 bar → 不成交」，不能假设有价格。
2. 半日 `pm.close` 与官方日收盘不一致，且 `DATA_SOURCES.md` §1.7 登记了 4 个整批偏离日
   （2015-03-05、2015-04-28、2016-01-22、2016-01-04，以及 2015-07-01 的零量重复价格日）。
   这些日的 bar **极值**经逐证券日复核仍 ≤ 官方极值（零违例），仅收盘价受污染。
   → 沙箱因此同时导出官方日线；任何 close 用途走 `bars_daily`。
2. `user_minute_1m` 数据商未知，不能对外称交易所级来源（DATA_SOURCES §1.6）。
3. `bigquant/years` 与 `user_minute_1m` 同源不同快照，**不能互为独立验证**（DATA_SOURCES §2.1）。
4. 沙箱未导出分钟线本身；订单「生效半日前已穿透」这类分钟级核验属 C3-C 范围，需要时单独申请受控提取。

**对研究的影响：** 半日语义是冻结成交合同的基础（严格穿透、触价不成交、不取更优价）。
半日无法观测半日内的价格先后顺序，因此「同半日买后卖」「用同半日卖出款买入」都必须按合同禁止（见 `05_test_vectors.md` TV-B07/B08）。

---

## 3. 停牌 / ST / tradestatus 处理

| 状态 | 字段与来源 | 用法 | 实测（Dev） |
|---|---|---|---|
| 停牌 | `bars_daily.tradestatus`（0/1）、`bars_halfday` 缺行 | 停牌不成交、停牌冻结 K=3 计数、缺 bar 不造行 | 日线 `tradestatus != 1` 行数 265,531 |
| ST | `bars_daily.isST`（0/1，空值拒绝） | 池资格 `isST == 0` | `isST != 0` 行数 141,446 |
| 可卖数量 | 逐 clip 的取得半日（`T+1`，`band_engine` LOT=100） | 当日新买份额当日不可卖 | 由成交/批次台账派生，不由行情表直接给出 |

**交叉源（未进入沙箱）：** bundle 另有 `st_stock_days.h5`（629 只）与 `suspended_days.h5`（2,973 只），
上游与 baostock 不同封装；其覆盖与定义未在 C1 逐一核对（unknown），只能当**线索**，不能拿来覆盖 `isST/tradestatus`。
`wind-stock` / `hexin` 的历史状态查询均**不可用**（DATA_SOURCES §10 §11：只返回当前状态或静默丢弃日期条件），
因此历史池过滤仍只能靠 baostock 单源。

**对研究的影响：** 单源 ST/停牌意味着池资格与「不可交易」判定存在系统性错配风险；
C4/C5 若结论对这个错配敏感，需要新的独立状态源（当前不存在）。

---

## 4. 涨跌停价格表（`limit`）

| 项 | 值 |
|---|---|
| 上游 | `data/raw/tushare/stk_limit/20260917-r1/chunk_YYYYMMDD.csv`（逐交易日 chunk，全窗口 2431 个） |
| 沙箱文件 | `limits/limit_dev.parquet`（4,871,551 行 / 4,234 只 / 1,459 个交易日） |
| 列 | `symbol, date, up_limit, down_limit`（元；`ts_code` 已换算为 repo symbol） |
| 时间口径 | 当日涨跌停价（不是前一日），用于订单价格合法性与涨跌停/跳空边界 |

**已实测缺陷 / 已知缺口**
1. **3 个交易日整日缺失**：源 chunk `20170307`、`20170308`、`20170309` 只有表头零数据行
   （manifest `sources.limit_source.empty_chunks_skipped` 登记）。这 3 天任何订单合法性判定都无法用该表完成。
2. 覆盖率双向不一致（实测）：`limit` 有而 `bars_daily` 无的 `(symbol, date)` 对 = 17,132；
   `bars_daily` 有而 `limit` 无的 = 16,693（1,462 个日线交易日 vs 1,459 个有涨跌停表的日子，差额即上面 3 天）。
   可能来源包括退市/新上市/停牌日的登记差异；**C1 不做归因**。
3. `up_limit`/`down_limit` 是交易所规则的事后计算值还是原始公布值，源 manifest 未说明（unknown）。

**对研究的影响：** C3 的价格合法性检查必须定义「涨跌停表缺行」的处置：
按项目保守原则应为**拒绝该订单并留痕**，不得把缺行当成「无涨跌停约束」或「无非法价」。
这是一项需要在 C3 冻结的合同细节（已登记为开放问题）。

---

## 5. 分红与送转（`dividend` / `split_factor`）

| 项 | dividend | split_factor |
|---|---|---|
| 上游 | `data/processed/rqalpha-bundle-v2-1-20260918/dividends.h5`（4,512 只） | 同目录 `split_factor.h5`（2,878 只） |
| 读取方式 | 主引擎冻结读取器 `band_engine.load_dividends_h5` | `band_engine.load_split_factor_h5` |
| 沙箱文件 | `corporate_actions/dividends_dev.parquet`（15,251 行 / 3,527 只） | `corporate_actions/split_factor_dev.parquet`（3,339 行 / 2,196 只） |
| 列 | `symbol, ex_date, cash_per_lot_pre_tax, round_lot` | `symbol, ex_date, split_factor` |
| 口径 | **每整手（round_lot 股）税前现金分红**，不是每股金额；`round_lot` 实测全为 100 | 该除权日的份额乘数（1 + 送转比例），同日多行连乘，**不得**与相邻行差分 |
| 实测 | `cash_per_lot_pre_tax` 中位数 10.0 元/手，最大 1702.5；其中 0 元行 492 行（纯送转或不分红） | `split_factor` 中位数 1.5，最大约 4.916，最小 0.2803 |

**单位证据（可复算）：** `sh.600000` 2022-07-21 源值 41.0 = 0.41 元/股 × 100
（`band_engine.load_dividends_h5` docstring 记录，未在 C1 重新核对 —— 该事件在 Dev 窗口之外，本审计不越界读取）。

**已实测异常（均为 ETF，属已知缺陷范围）**
- `sh.510500 2015-04-15 split_factor=0.2803`（份额合并）与 `sh.510230 2020-08-17 split_factor≈4.916`。
  `DATA_COVERAGE.md` 已登记 510500 份额合并并说明该 ETF 已从混合族宇宙剔除（`p3-band-contract.md` §8.4）。
  本卡确认这些行**物理存在于**送转表，但对应标的在当前个股主线宇宙之外。

**已实测缺陷 / 已知缺口**
1. 源 h5 另含 `book_closure_date`（股权登记日）与 `payable_date`（应付日）；**C1 未导出**。
   冻结账户合同按**除息日**计入已结算现金（`corporate_action_policy.cash_dividend`）。
   若要改用付款日记账，属合同变更，须先登记再实现（不得静默改时点）。
2. `ex_cum_factor.h5`（含分红的累计复权因子）**禁止**作为账户输入（只可作对照审计），因此未导出。
   禁止「既把现金分红计入账本、又用含分红复权价估值」的双计。
3. 因子只覆盖有事件的证券；无事件证券不会出现在表中，`join` 时缺行 = 无公司行动（不是未知）。
4. ETF 分红与份额折算另有专门缺陷清单（DATA_COVERAGE §日线与复权表），当前主线不涉及。

**对研究的影响：** 账户级权益与成交成本必须用这两张表逐事件处理；任何「用复权因子代替份额乘数」
或用「累计因子差分」的做法都会重演 F1/F2 缺陷。

---

## 6. 业绩预告批次（`forecast_event`）

| 项 | 值 |
|---|---|
| 上游 | `data/raw/tushare/forecast/20260909-r1/`（逐月 chunk，抓取时间 2026-09-09T13:51:52） |
| 沙箱文件 | `events/forecast_b_window.parquet`（18,042 行，ann_date 2018-09-04..2020-12-31） |
| 列 | `ts_code, ann_date, end_date, type, p_change_min, p_change_max, net_profit_min, net_profit_max, last_parent_net, first_ann_date, summary, change_reason, update_flag` |
| 单位 | `net_profit_min/max` = 万元；`p_change_min/max` = % |
| 版本标识 | `update_flag`（vendor 版本号）+ `ann_date`；同财务期多版本行按 `(ann_date, update_flag)` 排序 |

**结构事实（`announcement_version_audit.csv` 实测）：** 16,562 个 (ts_code, end_date) 财务期组，
其中 1,419 组有多于一个版本行；区间合法性分类：`valid` 15,215 / `point`(min==max) 929 /
`missing`(min 或 max 空) 1,898 / `invalid`(min>max) 0；非标准代码（非 `\d{6}.(SH|SZ)`）28 行未进沙箱语义。

**已实测缺口**
1. **同一公告日的多版本在本窗口内为 0 组**（实测）：Dev B 窗口不存在「同日修订」样本。
   因此 TV-B28 的「同日多版本」只能用合成数据覆盖（见 `tests/test_temporal_isolation.py`）。
2. 该批次是 **as-fetched 快照**（2026-09-09 抓取），保留了多版本行，但**无法证明字段值等于公告当时的原值**。
   逐行结论写在 `announcement_version_audit.csv` 的 `version_evidence_class` / `pit_conclusion` 列：
   单版本组=无历史可比、无可靠 PIT 证据；多版本组=有「版本存在性与顺序」证据，仍不具完整 PIT 证据。
   → 依赖历史数值修订的臂（如严格数值上修）在 C5 必须带着这个限制，不能声称等价于当时可得信息。
3. 源端 `first_ann_date` 可能为空（旧结构表构造时用 `ann_date` 兜底，属已披露的收窄）。
4. 预告只是 B 家族一个来源；`express`/`repurchase`/`share_float`/`stk_holdertrade`/`disclosure_date`
   五个同类批次**不在 C1 导出范围**（当前主线只用 B1/B2）。

**对研究的影响：** B1「可验证的向上修订」的样本定义依赖上面这条版本链；`min==max` 是合法点预测，
`min>max` 才是非法区间，二者不能一起丢（`temporal_contract.classify_forecast_interval` 已区分并有测试）。
B1 全部 102 事件的字段抽核结论：源行身份 102/102 唯一匹配，前序版本 102/102 存在，
`type_upgrade` / `numeric_revision_up` / `numeric_available` 与归档漏斗标志 102/102 一致（
`b1_102_field_spotcheck.csv`）。

---

## 7. 缺失与终止证券处理

**原则：保留 + 标记，不删除；缺终点不填 0；不用后来年份报价强行结算。**

| 情形 | 处理 | 实测证据 |
|---|---|---|
| 停牌导致某半日无 bar | 不造行；`tradestatus`/缺行参与可交易判定 | 半日 4,181 只 vs 日线 4,187 只：6 只完全没有半日行（2 只全期停牌，4 只原因 unknown，见第 2 卡缺陷 1） |
| 日线全空价格行（停牌） | 保留原样；空值传播排除信号 | 2 行（`sz.000022 2018-12-26`、`sz.000043 2019-12-16`） |
| 20 日窗跨 Dev 边界 | 保留事件、标 `window_complete=false`、`crosses_dev_boundary=true`；进不了完整窗口均值；终点在 2021 不推算 | 市场层面：Dev 最后 20 个交易日（2020-12-04 起）的 20 日窗都跨边界；86 只 B1 事件证券各自的首个跨界锚定日已列出 |
| 证券在 Dev 内退市/终止 | 保留、标 `ended_by_panel_end`（与跨界区分）；沙箱内该证券在终止日之后**没有任何行**，因此不可能拿到后续报价 | 面板终止（最后一行日线早于 2020-12-24）共 46 只，其中 44 只有可交易自身交易日（`censoring_audit.csv` `record_type=delisted_symbol`；另 2 只全期无交易行） |
| B1 事件标签缺失 | 计数并披露；`net_return` 不填 0 | 102 个事件：完整窗 102、右删失 0、缺失标签 0；与归档 `label_end_decision` 逐条一致（0 处不符） |
| 删除样本 | **0** | `censoring_audit.csv` 汇总行 `deleted_samples=0` |

**对研究的影响：** 因为 Dev 沙箱物理上不含 2021 行，「跨界」与「终止」必须靠调用方声明
（`own_session_label_window(panel_truncated_at=...)`）区分，两种都 `window_complete=false`，
但归因不同、披露不同。这避免了两种常见错误：把跨界样本当完整样本算进均值；
或者把窗口不足额当成「样本不存在」直接删掉。

---

## 8. 股票池资格所需字段

池资格所需的直接字段全部在 `bars_daily`：`symbol, date, close, preclose, amount, turn, tradestatus, isST`，
外加板块前缀与上市时长规则。规则清单写进 `dataset_manifest.json` 的
`datasets[kind=bars_daily].pool_eligibility`：

- `tradestatus == 1`（历史停牌状态）
- `isST == 0`（历史 ST 状态，空值按不合格拒绝）
- `close >= 2.0` 元
- `amount` 的 20 自身交易日滚动中位数 `>= 50,000,000` 元
- 板块前缀（主板 `sh.60*` / `sz.00*`）；创业板按 C1 授权边界排除（账户权限证据仍缺，C0 冲突 C-07 未决）
- 上市满 120 个自身交易日

**派生但未导出**：`amt_med20`、`vol20`、`turn20`、`listing_index`、`c_adj`。
导出层**不携带任何因子值**，使用方必须在沙箱数据上自行计算，避免「把旧因子结果当输入」。
`listing_index`/上市日期的上游未在 C1 核对（unknown）：Dev 面板首行不等于真实上市日，
这一点在 C2/C5 使用前需要单独确认。
