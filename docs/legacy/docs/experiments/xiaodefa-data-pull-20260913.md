# xiaodefa(Tushare兼容) 全量取数 2026-09-13

用户提供一个 Tushare 兼容代理（HTTP `https://t.xiaodefa.top/`、MCP 端点同源）用于补数据，
并明确本阶段只做取数：登记数据集、按已有数据去重、分块落盘、断点续传；不改策略与账户逻辑。

## 凭据与接口目录

token 只存 `~/.quant-credentials/xiaodefa-token`，代码从该文件读取；不写仓库、不入日志，
错误信息经 `clean()` 脱敏。MCP `tools/list` 返回 283 项接口能力，目录留档
`artifacts/xiaodefa-bulk-20260913/catalog.json`；首批连通性探测留档同目录 `probe/`。

## 落地位置与去重

批次根：`data/raw/xiaodefa/20260913-bulk1/`，每数据集一个 `manifest.json`，分块 `chunk_<key>.csv`。
本地已完整覆盖、不再重下的数据集记在 `data/raw/xiaodefa/skipped-datasets.json`：
日线（用户数据集 1999-2026 沪深）、daily_basic（2015-2026）、
income/balancesheet/cashflow/fina_indicator（5899 股全历史）、dividend（2016-2026）、
stk_mins（2015-2024 用户 1 分钟归档）。

## 取数工具

`experiments/xiaodefa_bulk.py` 四阶段：`ref`（快照/参考）、`daily`（按交易日）、`monthly`（宏观月频）、
`stock`（逐股）。特性：全局节流+自适应放慢+退避重试；快照类按接口单次上限分页并支持中断续传
（`.part_*.csv` 按已落盘行数续传）；日频类单次全量。

调度脚本：`experiments/xiaodefa_bulk_all.ps1`（轻量日频→旧年份→逐股）、
`experiments/xiaodefa_bulk_heavy.ps1`（重型日频单独并行）。两者共用同一 manifest，
chunk 落盘即跳过，重叠列表自动去重。

## 本轮修掉的故障

1. 服务端对部分接口声明 `gzip` 但返回明文 → 解压失败时回退原文（曾表现为 `st`、`ths_index` 失败）。
2. 多线程/多进程写 `manifest.json` 用固定临时名 → 重命名撞车（WinError 5）；改为
   `.manifest.<pid>.<tid>.tmp` 加重试。
3. 单次上限因接口而异（概念/行业板块 2000、通达信板块 1000、部分 5000）→ 曾静默截断；
   旧文件隔离为 `*.csv.truncated*` 并按正确页长重拉；`dc_index` 概念板块超 9.6 万行，
   中途 SSL 断连，已改为分页续传。

## 已完成（截至 2026-09-13 21:55）

| 数据集 | 结果 |
|---|---|
| `adj_factor` 复权因子 | 3088/3088 交易日（2014-01-02..2026-09-11），1286 万行；2 天待重试 |
| `stk_limit` 涨跌停价 | 3088/3088，1483 万行，无失败 |
| `suspend_d` 停复牌 | 2962/3088（已到 2026-03），3 天待重试 |
| 参考/快照 | stock_basic(L/D/P/G)、trade_cal(SSE/SZSE/CFFEX)、index_basic(20752)、
  index_classify(SW2014/SW2021)、index_member_all、fund_basic(场内/场外/全市场)、fund_company、
  etf_basic、etf_index、cb_basic、ths_index、dc_index、tdx_index、stock_company、namechange、
  st、stock_st、bse_mapping |
| 月频宏观 | cn_m/cn_cpi/cn_ppi/cn_pmi/sf_month 完成；cn_schedule 收尾 |
| 港股通/两融 | 本地已有 2019-01-01..2026-09-09，只补 2014-2018（排队） |

`hs_const`、`stock_hsgt` 返回 0 行（无权限或无数据）。

## 进行中

重型日频：`stk_auction_c` 2970/3088、`stk_auction_o` 2263/3088、`moneyflow`、`cyq_perf`、
`idx_factor_pro`、`stk_nineturn`、`hk_hold`、`ccass_hold`。
轻量日频：`limit_list_d` 1624/3088、`daily_info`、`sz_daily_info`、`ggt_daily`、`block_trade`、
`stk_surv`、`hm_detail`、`ths_daily`、`dc_daily`、`sw_daily`、`ci_daily`。
逐股 9 类（约 5900 只）：top10_holders、top10_floatholders、stk_holdernumber、pledge_detail、
pledge_stat、stk_managers、stk_rewards、fina_mainbz、fina_audit。

预计：日频余下约 12 小时，逐股约 15 小时，合计约一天内跑完（不含已砍项）。

## 用户决定不拉的可压缩项

2026-09-13 用户指示“可压缩的几个先不拉”，据此从队列移除并记入 `skipped-datasets.json`：

- `stk_factor_pro`：Tushare 自算 100+ 技术指标，可由已落盘日线重算；实测单次 63 秒，
  全量约需 9 小时。
- `cyq_chips`：只支持逐股（必填标的），全市场逐日为不可行规模；同日口径由 `cyq_perf` 覆盖。
- 该代理无此接口名：`stock_mx`、`stock_vx`、`cls_member`、`cls_market_shock`。
- 按交易日查询恒返回 0 行：`moneyflow_dc`、`moneyflow_ths`、`tdx_daily`、`dc_member`、
  `dc_concept`、`dc_hot`、`ths_hot`、`stk_shock`、`stk_high_shock`、`stk_alert`。

上述“恒 0 行”多为参数口径问题（如需 market/theme_code/symbol），若后续需要可另立批次按正确参数补。

## 分钟数据：缺口与核定

同一代理的 `stk_mins` 与闲鱼那批 1 分钟**同源**（逐字段一致），不能互为独立验证；
且该接口只能逐股按日拉取，全市场十年分钟不经济，故分钟仍以用户 1 分钟归档为主。

对已确认缺口改用 baostock 5 分钟（2020 起覆盖）并逐字段校验：

- `sh.688165 2021-11-01`、`sh.688059 2023-06-01`、`sh.603178 2022-02-07`：代理/闲鱼分钟
  首根开盘价错误，baostock 开盘价与日线一致，整日替换。
- `sz.300114 2022-06-01`：主归档该股该日为 0 行，baostock 补入。
- `sz.002442 2016-03-01`、`sh.603026 2019-05-06`、`sz.300420 2019-09-02`：分钟源漏一笔最低价
  （两个独立日线源一致为更低值），baostock 无该年分钟；登记受审例外
  `LOW_ONLY_MISSING_PRINT_NO_TRIGGER_DEPENDENCY`，仅当每笔买单价格不在 `(daily_low, minute_low]`
  区间内才放行（限价买入按 `open<=price` 或 `low<=price` 成交，卖单只看 high，不受低价差异影响）。

补丁清单 `data/raw/xiaodefa/minute-repairs-20260913-3/patches.json`（27 项，SHA256
`94817d0256a64e7b1fdb471e91faaa0c3cce10faba6f7a915da37b9ebc8f1f57`）；
脚本 `xiaodefa_repair_build_20260913.py`、`xiaodefa_repair_build2_20260913.py`、
通用补缺工具 `xiaodefa_minute_repair_20260913.py`。能力审核 `review-v3.json` 绑定当时源码身份，
新增用例 `tests/test_minute_low_only_exception.py`（正例放行+反例阻断共 3 例）。

## 分钟覆盖核定（选股依赖上界）

`experiments/xiaodefa_minute_coverage_20260913.py` 按信号批 `planned-selection-days.csv`
逐证券日核 2400 项，走运行时同一路径（float32 分币还原 + 241→48 聚合 + 停牌跳过）：

| 结果 | 数量 |
|---|---|
| EXACT（与日线逐字段一致） | 1921 |
| DISCLOSE（1% 价格 / 5% 量异常线内） | 443 |
| PATCH（冻结补丁覆盖） | 24 |
| SUSPENDED_SKIP（当日停牌，账户不请求） | 11 |
| BLOCKED | 1 |

唯一阻断为 `sz.300114 2016-05-03`：主归档与代理分钟库均无该股分钟。该日属选股上界，
不属当前实际订单（REV 两条路径跑完十年未请求）。证据
`artifacts/xiaodefa-minute-coverage-20260913/{coverage.json,coverage.csv}`。

该清单是选股依赖**上界**，非实际订单清单；实际订单为其子集，逐日按需在运行时校验。

## 2026-09-14 20:20 盘点：token 过期，批次停止

代理自 09-14 19:00 前后开始对全部接口返回 `2002 token已过期`，两个后台进程随即空转重试，
已全部停止。**已落盘数据不受影响，清单仍可按 chunk 续传**；补拉只需换新 token 后重跑
`experiments/xiaodefa_bulk_all.ps1`、`xiaodefa_bulk_heavy.ps1`、`xiaodefa_bulk_stocks.ps1`。

落盘总量：**66517 个分块、1.180 亿行、13.10 GiB**。盘点明细
`artifacts/xiaodefa-bulk-20260913/inventory-20260914.json`，脚本
`experiments/xiaodefa_inventory_20260914.py`。

已完成（19 个日频数据集 100%）：`adj_factor`(3088日/1286万行)、`stk_limit`(3088/1483万)、
`stk_auction_c`(3088/1284万)、`moneyflow`(3088/1195万)、`stk_nineturn`(3088/1188万)、
`cyq_perf`(2111/948万)、`idx_factor_pro`(3088/796万)、`hk_hold`(2284+71空)、
`ccass_hold`(1384+971空)、`ths_daily`(3088/290万)、`dc_daily`(1624+1464空)、
`block_trade`、`suspend_d`、`stk_surv`(1167+1921空)、`hm_detail`(989+2099空)、
`limit_list_d`(1624+1464空)、`daily_info`、`sz_daily_info`、`ggt_daily`。

参考/快照类按各自口径完整：`stock_basic`、`trade_cal`、`index_basic`(20752)、`index_classify`、
`index_member_all`、`fund_basic`(65956)、`fund_company`、`etf_basic`、`etf_index`、`cb_basic`、
`ths_index`、`stock_company`、`namechange`(34749)、`st`、`dc_index`(195781)、
`tdx_index`(148507)、`bse_mapping`、`stock_st`(101000，滚动窗口)。
`hs_const`/`stock_hsgt` 确认无权限。月频：`cn_m`/`cn_cpi`/`cn_ppi`/`cn_pmi`/`sf_month` 各 151/153 个月，
`cn_schedule` 9/153。

未完成（换 token 后接着拉）：

- `stk_auction_o` 3087/3088（缺 1 日）；`sw_daily` 3086/3088（2 日失败）；`ci_daily` 2757/3088。
- 逐股：`top10_holders` 5893/5899、`top10_floatholders` 3049/5899；`stk_holdernumber`、
  `pledge_stat`、`pledge_detail`、`stk_managers`、`stk_rewards`、`fina_mainbz`、`fina_audit` 未开始。
- 2014–2018 港股通/两融补旧年份（`top_list`/`top_inst`/`margin_detail`）未完成。
- 月频 `cn_schedule` 剩余月份。

## 未解与后续

### 逐股 9 类的取舍（2026-09-14 决定：全部拉取）

评估时的判断是：对当前三个任务逐股 9 类均不在关键路径（T2 月频价量只需价量/涨跌停/停复牌/
公司行为，T1 执行支撑数据已就绪）；按因子原料的独立信息量，前 4 类明显更高、后 5 类偏低或
与现有数据重叠。用户随后决定**9 类全部拉取**，故 `STOCKS` 保留全部 9 项，不再设暂缓层。

分工与工期：现在单独起一个进程先拉最重的 4 类（约 6 小时），轻量队排到逐股阶段时再按
chunk 落盘自动跳过已完成项。9 类合计约 15 小时（3 个进程并行分摊）。

### 其他

- `sz.300114`：任何年份分钟都缺，只能逐日按需用 baostock 补（2020 起）或另找来源。
- 待重试交易日：`adj_factor` 2 天、`suspend_d` 3 天（传输抖动，重跑即可）。
- “恒 0 行”接口需按正确参数另立批次，本轮不拉。
- 代理计费/限流额度未公开，长期全量拉取需持续观察失败率与耗时。
