# 数据覆盖矩阵

统计时点 2026-09-16（迁移、去重、1 分钟解压后）。目标研究窗口 **2015–2024**；2025 以后与生产发布继续冻结。
精确到批次的数据见 [`DATA_INVENTORY.md`](DATA_INVENTORY.md)（自动生成）与 `data/_meta/inventory.json`。

## 读取层强制规则（2026-09-17 全量深扫后）

逐批次深扫台账：`data/_meta/deep-scan-20260917/`（455 个批次报告 + README 汇总；514 批次单元、run `20260917T232604-raw-deepscan-a7c3`）。任何新读取代码必须遵守：

1. **冻结边界过滤**：几乎所有在市批次都拉到了 2026-09（深扫 465 条 blocker 中 457 条为此）——读取层必须过滤 `>2024-12-31`，涉及 tx/ths/em_fin 全部批次、xiaodefa 44 个 dataset、bigquant 2025/2026 目录等。
2. **列序不可信**：xiaodefa `moneyflow`（1,378/3,088 文件列序为 `ts_code,trade_date`，与主流相反）、`sw_daily`、`cyq_perf`、`stk_limit` 存在文件间列序不一致——按列名归一，禁止按位置拼接。
3. **tx 跨页重叠**：全部 176 个多页批次存在固定分页边界重复 K 线（重叠日含 2006-12-08 / 2010-03-25 / 2013-07-15 / 2016-10-25 / 2020-02-06 / 2023-05-22）——按 `(symbol, date)` 去重。
4. **表头校验**：存在首行为空的文件（实证：`xiaodefa/stk_limit/20260913-bulk1/chunk_20220705.csv`）——载入时校验首行非空，空表头文件的列名须显式提供。
5. **复权因子已知缺陷**：`xiaodefa/adj_factor` 的 600069.SH 因子在 6.415 与 0.6604 间反复振荡——该股复权序列在人工复核前禁止用于任何复权计算。
6. **单位结论**（深扫实测表，详见深扫 README）：`daily_basic.close`=元 / `total_mv`=万元；`xiaodefa/stk_limit`=元；`moneyflow` 金额列=万元；`margin_detail` 余额列=元；`tushare/index_daily`：vol=手、amount=千元（v2.1 双签数值证明）。

## 1 分钟全市场（全部为解压后的目录层）

| 年份 | 来源 | 形态 | 交易日数 | 备注 |
|---:|---|---|---:|---|
| 2010 | `bigquant/minute-bulk-20260915-1/years/2010/` | 按日 Parquet | 242 | 全市场当日 1 分钟 |
| 2011 | `…/years/2011/` | 按日 Parquet | 244 | |
| 2012 | `…/years/2012/` | 按日 Parquet | 243 | |
| 2013 | `…/years/2013/` | 按日 Parquet | 238 | |
| 2014 | `…/years/2014/` | 按日 Parquet | 245 | |
| 2015 | `user_minute_1m/20260913-143215/2015/` | 按日 Parquet | 244 | 另有 `…/years/2015/`（2607 只按证券 CSV，同源异形态） |
| 2016 | `user_minute_1m/.../2016/` | 按日 Parquet | 244 | 另有 `…/years/2016/`（2834 只） |
| 2017 | `user_minute_1m/.../2017/` | 按日 Parquet | 244 | **仅此一处** |
| 2018 | `user_minute_1m/.../2018/` | 按日 Parquet | 243 | 另有 `…/years/2018/`（3370 只） |
| 2019 | `user_minute_1m/.../2019/` | 按日 Parquet | 244 | 另有 `…/years/2019/`（3572 只） |
| 2020 | `user_minute_1m/20260913-2020-2024/2020/` | 按日 Parquet | 243 | |
| 2021 | `.../2021/` | 按日 Parquet | 243 | |
| 2022 | `.../2022/` | 按日 Parquet | 242 | |
| 2023 | `.../2023/` | 按日 Parquet | 242 | |
| 2024 | `.../2024/` | 按日 Parquet | 242 | |
| 2025 | `bigquant/.../years/2025/` | 按日 Parquet | 243 | **窗口外** |
| 2026 | `bigquant/.../years/2026/` | 按日 Parquet | 63 | 2026-01-05 … 2026-04-10，**窗口外** |

合计按日 Parquet 成员 2431（2015–2024）+ 1518（2010–2014/2025/2026）＝ 3949 个交易日文件；
另有按证券年度 CSV 12,383 个（2015/2016/2018/2019）。逐年文件数/字节见
[`evidence/minute-manifest.json`](evidence/minute-manifest.json)。

已知缺口与缺陷（详见 [`DATA_SOURCES.md`](DATA_SOURCES.md)）：2015-07-01 有 11 只深市股票尾盘
零量重复价格；22 项已登记待补/受审证券日；`sz.300114` 无任何年份分钟；另有 4 个分钟收盘价
成批偏离官方收盘的交易日（2015-03-05、2015-04-28、2016-01-22、2016-01-04，极值不受影响，
见 DATA_SOURCES 陷阱 7）；全源无 ETF 分钟数据、主日线源无基金代码（ETF 线待数据源决策）。

## 日线与复权

| 数据 | 来源 | 覆盖 | 形态 |
|---|---|---|---|
| 用户日线数据集 | `user_dataset/` | 上证 2316 只 + 深证 3185 只（含指数），1999-11-10 起 | 6 个 zip × 3 复权（不复权/前复权/后复权），每证券一个 CSV |
| 在市日线 + 退市/ST/停牌 | `baostock/daily/` | 5552 只，1999-11-10 … 2026-09-04 | 每证券 CSV + meta（`adjustflag=3` 不复权） |
| 复权因子 | `baostock/adjust_factor/` | **仅 343 只** | 每证券 CSV |
| 5 分钟补数 | `baostock/minute/` | 2357 组证券日（2020 起，按需拉取） | `*_f5.csv` + meta |
| 退市/ST/板块参考 | `baostock/20260905_*` | 时点抓取 | CSV + meta JSON |
| **ETF 日线（标准化）** | tushare `fund_daily`/`fund_adj` 20260917-r1 → `processed/etf-daily-20260919/` | 1,169 只 ETF（含 128 退市），2015-01-05…2024-12-31，1,017,121 行；2025+ 零行 | 单 parquet（volume=股、amount=元、不复权）+ pool/质量/偏离明细；**复权因子系列在 raw chunk，按 symbol join**；已知缺陷：159842 因子全缺、sh.502056 因子缺前段、sz.159919 2019-01-14 份额折算因子漏记、sh.510500 2015-04-15 份额合并（ratio 0.28）——后两者已从混合族宇宙剔除（契约 §8.4） |

## 截面与执行参数（`xiaodefa/`，2014-01-02 … 2026-09-11，3088 个交易日）

| 类别 | 数据集（分块数） |
|---|---|
| 复权/涨跌停/停复牌 | `adj_factor`(3089)、`stk_limit`(3089)、`suspend_d`(3089) |
| 集合竞价/资金流/筹码 | `stk_auction_c`(3089)、`stk_auction_o`(3089)、`moneyflow`(3089)、`cyq_perf`(2112)、`stk_nineturn`(3089)、`idx_factor_pro`(3089) |
| 两融/港股通/龙虎榜 | `margin_detail`、`top_list`、`top_inst`、`hk_hold`(2285)、`ccass_hold`(1385)、`ggt_daily`(2702) |
| 板块与行业 | `ths_daily`(3089)、`dc_daily`(1625)、`sw_daily`、`ci_daily`(2758)、`dc_index`、`tdx_index`、`index_classify`、`index_member_all` |
| 参考/快照 | `stock_basic`、`trade_cal`、`fund_basic`、`etf_basic`、`cb_basic`、`namechange`、`st`、`stock_st`、`stock_company`、`bse_mapping` |
| 月频宏观 | `cn_m`、`cn_cpi`、`cn_ppi`、`cn_pmi`、`sf_month`（各 151–153 个月） |

**未拉全**：见 [`DATA_SOURCES.md`](DATA_SOURCES.md) §6 与
`docs/legacy/artifacts-evidence/xiaodefa-bulk-20260913/inventory-20260914.json`。

## 财务与日指标（`tushare/`）

| 数据集 | 覆盖 | 分块 |
|---|---|---|
| `daily_basic` | 2015-01-05 … 2026-09-09（r2 补 2015–2018 + r1 2019 起） | 1867 + 977 |
| `margin_detail` | 2019-01-02 … 2026-09-09 | 1867 |
| `dividend` | 2015-01-05 … 2026-09-09（r2 + r3） | 733 + 2110 |
| `income` / `balancesheet` / `cashflow` / `fina_indicator` | 逐股全历史（约 5900 只） | 各 5900 |
| `disclosure_date`、`express`、`forecast`、`repurchase`、`stk_holdertrade` | 逐股 | 33–131 |
| `share_float`、`sw_index_daily(_l2)` | 逐股 / 逐指数 | 131 |
| `stock_basic`、`trade_cal`、`fund_basic`、`index_member_all` | 参考 | 少量 |

财务使用时点纪律：报告期数据在期末后 **90 天**才对回测可见。

## 复核与辅助

| 来源 | 覆盖 |
|---|---|
| `tx/` | 腾讯前复权日线 + 快照，193 个批次（个股池复核） |
| `sina/` | 未复权 K 线复核，181 个证券 |
| `sina_universe/` | 全市场列表快照，280 批次 |
| `sina_industries/` | 行业分类（未覆盖科创板） |
| `ths/` | 同花顺 ETF 前复权日线，71 批次（近 5 年） |
| `em_fin/` | 东财 F10 季报指标，125 个证券（最近 9 期） |
| `etf-minute-probe/` | ETF 5 分钟探针，1 批 |
| `hf_minute_1m/20260913-probe/` | 第三方 1 分钟来源探针记录（数据副本已删） |
