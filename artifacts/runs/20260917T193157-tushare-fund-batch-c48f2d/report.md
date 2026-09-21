# Run 报告：tushare fund_daily / fund_adj / stk_limit raw 批次拉取

- run_id: `20260917T193157-tushare-fund-batch-c48f2d`
- 日期: 2026-09-17；状态: **completed**
- token: `~/.quant-credentials/tushare-token`（仅脚本内读取；全仓泄漏扫描 CLEAN，token 未出现在任何落盘文件）
- 研究窗口硬边界: **20150101–20241231**；脚本断言 + 事后扫描确认无 2025+ 交易日数据。

## 1. 探针（19:34）

- `fund_daily` 510300.SH 20260911–20260917: **5 行，权限通过**（列含 pre_close/open/high/low/close/pct_chg/vol/amount）。
- `fund_adj` 510300.SH 同窗口: **5 行，权限通过**。
- 无 API 报错（attempts=1）。探针数据为 2026 年日期，**已丢弃，未写入 raw**。

## 2. 批次与覆盖

ETF 名册：`fund_basic/20260909-r1/chunk_market_E.csv`，过滤 `market==E 且名称含 ETF 且 list_date<=20241231 且（delist 为空或 >=20150101）` → **1169 只**（SH 693 / SZ 476；含已退市 128）。

| 批次目录 | chunk 数 | 行数 | 覆盖 | 缺口 |
|---|---|---|---|---|
| `data/raw/tushare/fund_daily/20260917-r1/` | 1169 (0 空) | 1,017,121 | 20150105–20241231，每个交易日全池均有行 | 对照 SSE 日历：0 缺日；未拉 ETF：0 |
| `data/raw/tushare/fund_adj/20260917-r1/` | 1169（1 空） | 1,032,863 | 同上 | **159842.SZ 无复权因子（0 行）**；未拉 ETF：0 |
| `data/raw/tushare/stk_limit/20260917-r1/` | 2431 日 | 9,705,448 | 20150105–20241231，2426/2431 日有数据 | **5 个零行日**（源无数据）：20170307、20170308、20170309、20220726、20230421 |

分年行数见 manifest `chunks` 与下方 run manifest `totals`；fund_daily 分年 29,437 (2015) 递增至 235,867 (2024)。

### 源口径备注（使用前必读）

1. `fund_adj` 有 **17,862 个 (ETF, 日)** 因子记录出现在 `fund_daily` 无行情的日期（涉及 309 只，如 159001.SZ 20191018、159503.SZ 2024-07 停牌日）；另有 2 只 ETF（含 159842.SZ）共 2,120 个行情日缺因子。复权时不得假设两表日期键一一对应。
2. `fund_daily` 为**不复权**价；`fund_adj` 因子口径以 tushare 定义为准，未在本次验证复权连续性。
3. `stk_limit` 实测列 = `trade_date,ts_code,up_limit,down_limit`（**无 pre_close 列**，与接口文档描述不同）。
4. ETF 名册以 20260909-r1 快照为准；当日之后新上市/退市变化不在此批。

## 3. 过程记录

- 主任务 fund_daily+fund_adj: 19:35:26–20:25:39，**50.2 min**（预算 150 min）。2338 次请求全部 attempts=1，**0 重试、0 失败**，未触发频控。
- 次任务 stk_limit: 20:31:52–21:42:17，**70.4 min 墙钟**（预算 80 min / 任务上限 90 min）。21:31 后台进程被外部终止于 chunk 2061/2431，**断点续传**恢复后跳过 2069 个已完成 chunk，剩余 362 日补齐；0 API 失败。
- 失败记录：仅冒烟阶段 2 类，均已解决并重拉成功——
  1. `stk_limit` 列 schema 预期错误（`"['pre_close'] not in index"`，3 个 chunk），修正列序后清空当日新建空目录重拉；
  2. 探针/主任务无任何 API 权限或频控错误。

## 4. 台账登记（只追加）

- `data/_meta/sha256.tsv`：追加 **4,772 行**（fund 两批 2,340 + stk_limit 2,432 = 2431 csv + manifest），既有行未改动（138,887 → 143,659 行）。
- `data/_meta/inventory.json`：追加 **3 个批次条目**，既有条目原样保留。
- 各批次 `manifest.json`：逐 chunk rows / first / last trade_date / done_at / attempts / sha256，状态 completed。

## 5. 未完成 / 后续

- 5 个 stk_limit 零行日为源缺口，重试仍返回空；如需补齐须换源（未执行）。
- 159842.SZ 无 fund_adj 因子；如需该 ETF 复权须另寻来源。
- 未做：复权连续性验证、与 baostock/xiaodefa 交叉核对、分钟级数据——不在本任务范围。
