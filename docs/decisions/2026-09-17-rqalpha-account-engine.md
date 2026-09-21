# 账户级回测引擎引入 RQAlpha（2026-09-17）

## 决策

- 账户级回测（P3/P4 账户回放：现金竞争、整手、T+1、涨跌停、停牌、费用、分红送转语义）由 RQAlpha 6.3.0 承担。
- Backtrader 不再新增开发；P0 已产出的 vectorbt×backtrader 对账资产保留为历史证据和交叉对照工具。
- 数据只接入自有身份可登记的来源（baostock 日线、tushare 批次），通过实现 rqalpha 的存储接口喂数；不使用米筐官方 bundle 作为研究证据源（其身份无法进入本项目台账）。

## 背景与理由

- 原技术边界（AGENTS §4、主计划 §2）定为 vectorbt 初筛 + Backtrader 账户级验证；用户 2026-09-17 批准改用 RQAlpha：A 股规则内置（T+1、涨跌停、印花税、整手、禁止裸卖空），项目仍在维护（6.3.0），数据层允许完全自有接入。
- 安装冒烟（2026-09-17，Windows、Python 3.11.15）：`uv pip install rqalpha` 成功，引入 h5py 3.16.0 等 19 包，无 bcolz（历史阻塞已不存在）；`import rqalpha` 正常。
- 接口侦察：`rqalpha/data/base_data_source/storage_interface.py` 定义 `AbstractDayBarStore / AbstractCalendarStore / AbstractDividendStore / AbstractSimpleFactorStore / AbstractDateSet`，`BaseDataSource` 按品种注册各 store 与 instruments；`INSTRUMENT_TYPE.ETF` 为一等类型。自定义接入面清晰：日 K、交易日历、分红、拆分/ex-cum-factor、停牌与 ST 日期集、instruments 注册。

## 用户豁免条款（如实记录）

- 用户明确豁免"对 RQAlpha 内置 A 股规则语义的独立复验"，研究阶段有效。
- 不豁免的部分：接线冒烟必须执行（安装→自有数据接入→固定小场景跑通）。它验证的是接线可用性，不是引擎规则正确性。
- 诚实性约束：凡结论依赖 rqalpha 撮合/费用语义的研究记录，必须标注"引擎语义未独立复验（用户豁免）"；生成任何实盘计划（`artifacts/plans/`）之前，必须补最小对账——同一组订单在 rqalpha 与现有 backtrader 或手算的结果一致性。

## 影响面

- 主计划 §2 技术表与 §6 追加"第五次更新"。
- P2 已完成结论不受影响（全部由自有 screen 管线产出，未使用任何回测引擎）。
- 依赖管理：当前仅 `uv pip install`（未入 pyproject/uv.lock）；接线冒烟通过后 `uv add rqalpha` 正式入锁。

## 接线路线（2026-09-17 定）

读源结论：`rqalpha/main.py` 在无 mod 注入时用 `BaseDataSource(config.base)` 直读 bundle 目录；`data/base_data_source/storages.py` 给出全部文件契约——日线 bar 为结构化数组 `datetime(int64) + open/close/high/low/volume/total_turnover(float64)`，停牌/ST 为 int 日期集合 h5，日历为 `trading_dates.npy`，品种表为 `instruments.pk`。**选自建 bundle**：写 ETL 从自有 parquet 生成 bundle 目录（`stocks.h5` / `funds.h5` / `trading_dates.npy` / `dividends.h5` / `ex_cum_factor.h5` / `split_factor.h5` / `suspended_days.h5` / `st_stock_days.h5` / `instruments.pk`，加占位 `yield_curve.h5`、`share_transformation.json`、`future_info.json`），产物落 `data/processed/rqalpha-bundle-<id>/` 并附 manifest（含全部输入 sha256，可重建）；运行时 `base.data_bundle_path` 指向该目录，`BaseDataSource` 不改一行。不选 mod 注入 `set_data_source`：侵入内部接口、维护面更大。ETF 走 rqalpha 原生 `funds.h5` 路径（ETF/LOF/REITs 共用同一 store）。账户语义对照物备而不用：旧项目源码（`docs/legacy/old-source-snapshot.zip`，workspace 快照 `t3-snapshot-20260914-1` 内同）`quant/execution.py` 的独立过审分钟账本，供结果异常时对照，豁免期内不强制。

## 未决事项（2026-09-17 ETL 实现与冒烟后更新，两项关闭）

- ~~日线 datetime 编码与 dividends.h5 行结构~~ **已查证**（冒烟 run `20260917T204121-rqalpha-bundle-smoke-c700ba8e`，bundle manifest 附查证来源）：权威契约在官方生成器 `data/bundle/{__init__,daybar}.py` 与读取方 `storages.py`/`data_source.py`/`position_model.py`；`automatic_update.py` 只是盘中增量补数脚本，当初以其为准的线索有误。日线 bar 与 ex_cum_factor/split 的日期 = `convert_date_to_int`（YYYYMMDDHHMMSS，日级时间位为 0，即 YYYYMMDD×10⁶）；`trading_dates.npy` 与 dividends 行内日期 = 8 位 YYYYMMDD。dividends.h5 行 = [book_closure_date(i8), dividend_cash_before_tax(f8), ex_dividend_date(i8), payable_date(i8), round_lot(i8)]，按 ex_dividend_date 排序；`dividend_cash_before_tax` 语义为**每手（round_lot 股）税前现金**（`position_model.py:254` 除以 round_lot 折每股）；tushare `cash_div` 为每股口径（已对真实公告核对，非每 10 股），ETL 须 ×round_lot 入库。dividend 批次拼接：`20260913-r2` 只含 2015–2017，`20260909-r3` 含 2018+，须按日期并批，只用 r2 会丢 2018+ 全部分红。
- tushare dividend / xiaodefa adj_factor → dividends.h5 / ex_cum_factor.h5 映射：股票侧已实现并经真实分红断言（A12）；**ETF 分红与折算口径仍缺源**（fund_adj 批次落盘后处理）。
- 停牌/ST 日期集来源：smoke bundle 暂与 bars 同源派生（标准化 parquet 的 tradestatus/isST）；P3 全量 bundle 前决定复用 P2 掩码还是从 raw 重算（仍开放）。
- 2026-09-17 冒烟结果：固定小场景（5 股 + 2 ETF、2024-10-08..12-31、61 交易日）12/12 断言通过——bar 与源 parquet/tx 逐值相等、日历 = xiaodefa SSE 2431 天、无越冻结线 bar、T+1 拒单、整手拒单/折整、逐日守恒、费用 = max(5 元, 名义×万1) 且税 0、分红现金精确入账、真实 000300 基准路径可用。`uv add rqalpha` 已入 pyproject/uv.lock。占位与缺口以 bundle manifest `placeholders` 为准（要点：`indexes.h5['000001.XSHG']` 为 rqalpha 探测键占位，**不得作为指数证据消费**；yield_curve 全 0；ETF 通道暂用 tx 前复权源、量纲未验证，待 tushare fund_daily 批次落盘后升级重建）。
- 2026-09-17 v2 全量重建并双签验收（交付 run `20260917T231506-rqalpha-bundle-v2-3c3ffecd`，复核 run `20260917T232444-v2-review-q4k9`）：4745 股票 + 1169 ETF、日历 2431 天、全库 5914 键 datetime 扫描越界 0；ETF 通道已升级 tushare 主源。三个换算关系双签数值证明：volume = fund_daily.vol[手]×100、total_turnover = amount[千元]×1000、ex_cum_factor ≡ fund_adj.adj_factor 恒等（仅加 (0,1.0) 锚点）；股票涨跌停 = stk_limit 逐值、5 个零行日 NaN 规则成立；dividends r2+r3 并批无 2018 断层。已知瑕疵（minor，双签复核发现并裁决）：① `indexes.h5` 的 000300.XSHG 基准 bar 仅覆盖 2021-08-05 起（bigquant 源文件窗口所限）——全窗口账户级回测的基准须待 `index_daily` 批次落盘后回填重建（处理中）；② `dividend_cash_before_tax` 沿用 tushare `cash_div`，其中 2,095/42,561 行（旧差别化股息税制期，如 000001 20150413：0.1653 vs 税前 0.174）源字段实为税后口径，字段名"before_tax"对这部分不成立——金额忠于所选源字段，入账偏低属保守方向，登记为已知口径瑕疵，重建时若得上游税前字段再修。
- **P3 硬前置（红队 R3-1，2026-09-17，run `20260917232740-redteam-1fcda1fb`）**：ETF 份额折算（如 510230 2020-08-17 ×4.9、512670 2021-08-23 ×2.0）只存在于 fund_adj 因子，不在 dividends.h5/split_factor.h5 事件中；rqalpha 按原始价估值持仓（`position.py` / `data_proxy.py`，ex_cum_factor 仅影响序列视图）→ 折算日账户权益静默蒸发且无报错。修复路径：ETL 从 fund_adj 大比例跳变生成 ETF 折算事件写入 split_factor.h5（rqalpha split 语义按拆股前数量入账），随 bundle v2.1（连同 000300 全窗口基准回填）实施；**完成前任何 ETF 的账户级 rqalpha 回测结果不可信**。
- **上述 P3 硬前置已关闭（2026-09-18，bundle v2.1）**：数据集 `data/processed/rqalpha-bundle-v2-1-20260918/`（ETL run `20260918T002453-rqalpha-bundle-v21-82a57865`，33s；冒烟 run `20260918T002657-rqalpha-bundle-v21-264845d2`，16/16 PASS）。① ETF 折算：规则一次定死——fund_adj 单日因子比 ≥1.1 或 ≤0.9 视为份额折算事件，split_factor 行 ratio = 因子比（方向依据 rqalpha `position_model._handle_split` 数量 ×ratio、引擎逐 bar 以原始 close 重标记，验收 = 持仓市值折算日连续）；(0.9,1.1) 内跳变视为分红类不入 split（ETF 现金分红不付的既有披露不变）。共 90 事件/76 ETF（清单在 bundle manifest `data_quality.etf_split_events`），四个已知案例全部命中（510230 2020-08-17 ×4.916019、512670 2021-08-23 ×2.0044、512690 2021-05-17 ×1.9614≈1:1.96、2021-12-31 ×1.359743≈1:1.36）；A15 专项场景（持有 510230 跨折算日）实测数量 300→1475（ROUND_HALF_UP ×ratio）、折算日市值比 1.04250982… 与"数量×原始价"期望完全相等（raw 路径应为 -78.8% 蒸发）、全程守恒。159919 2019-01-11 折算日无 bar（停牌），split 行照常生效、次一真实 bar 起市值正确（当日按停牌陈旧价高估一日，已披露）。② 指数回填：indexes.h5 五指数（000300/000001/000905/000852/399006）全为 tushare index_daily 20260917-r1 真实数据（各 2431 日=日历）；000300 全窗口替换 bigquant 窗口版、000001.XSHG 探针键改真实上证指数（v2"占位不得消费"警示作废）。单位实测：与 bigquant 000300 重叠 826 行 close 恒等（≤9.1e-13）、volume/vol ≡100 → vol=手 ×100、amount 比 ≡1000 → index_daily amount=千元 ×1000（与股票/基金同约定；首轮误测 amount=元，被 loader 单位硬守卫拦截后修正）。指数断言：000300.XSHG 2015-06-12 close == 5335.1151（批次 manifest 登记值）。两个 v2 已知瑕疵中的基准窗口瑕疵就此关闭；dividend 税前口径瑕疵维持原披露。引擎 A 股语义复验豁免照旧（本次仅验证自有 split 行进入引擎并触发其自述语义）。

