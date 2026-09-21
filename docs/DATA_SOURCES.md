# 数据源口径与陷阱

每个来源的角色、覆盖、文件形态、列名与已知陷阱。写新代码前先读本文；
任何「数据是否可信」的判断都必须回到该目录内的 manifest 与校验文件。

---

## 1. `user_minute_1m/` — 全市场 1 分钟（2015–2024，闲鱼购买，数据商未知）

| 项 | 内容 |
|---|---|
| 形态 | 每交易日一个 Parquet：`<批次>/<年>/YYYYMMDD.parquet`（2026-09-16 由同名 zip 解压，压缩包已删除）；每成员为**全市场当日** 1 分钟 |
| 列 | `code, trade_time, close, open, high, low, vol, amount, date, pre_close, change, pct_chg` |
| 代码格式 | `000032.SZ` / `600000.SH` |
| 单位 | `vol` 股、`amount` 元 |
| 覆盖 | 2015–2024，两批：`20260913-143215/`（2015–2019）、`20260913-2020-2024/`（2020–2024） |
| 身份 | 各批 `transfer-manifest.json` 记录源路径、字节数、SHA-256、源文件删除结果；解压记录见 `docs/evidence/minute-extract.json` |

陷阱：

1. 每日 **241 根**（09:30 一根 + 09:30–11:30/13:00–15:00 共 240 根）。聚合 5 分钟时 09:30 记录
   只并入首根区间一次，午休不跨组，总量不得增减。
2. 价格为 **float32 分币编码**，直接读会出现 `20.209999` 这类值；需要按「分」还原后再用。
3. 尾盘可能出现**零量重复价格**占位记录（2015-07-01 有 11 只深市股票 14:54–15:00 零量且日量缺口），
   不能当成真实成交，也不能简单换算成 5 分钟。
4. 该包**不是干净数据**：已登记 22 项待补/受审证券日（其中 11 项为实际订单阻塞），
   处置链见 `docs/legacy/artifacts-evidence/user-minute-1m-review-20260913-1/` 与
   `data/raw/xiaodefa/minute-repairs-*/patches.json`。
5. `sz.300114` 该股在**任何来源**都缺分钟（2016-05-03 起）。
6. 数据商未知，不能对外声明为交易所级或官方来源。
7. 特定交易日分钟收盘价成批偏离官方收盘（2026-09-18 收盘桥接扫描 run
   `20260918T201955-close-bridge-sweep-74ad`，主对话抽查复算一致）：2015-03-05 有
   1,309/1,418 只深市股票 pm.close 相对官方收盘偏离 >1e-4、2015-04-28 为 1,244/1,424、
   2016-01-22 为 929/1,556、2016-01-04 为 57（熔断提前收市日）、2015-07-01 为 884（即陷阱 3
   之日）。这些日的 bar **极值**经逐"证券×日"复核仍 ≤ 官方极值（零违例），仅收盘价受污染；
   任何收盘价用途应改用官方日线收盘。

---

## 2. `bigquant/` — 1 分钟数据（已解压）+ 探针/补丁

### 2.1 `minute-bulk-20260915-1/years/`（1 分钟数据，已解压）

2026-09-16：压缩原件解压为目录层，`zips/*.zip`（21 个，51.95 GiB）在逐成员 CRC + 成员数/字节校验后删除。

| 年 | 形态 | 成员数 | 覆盖 |
|---|---|---:|---|
| 2010–2014 | 按日 Parquet（`YYYYMMDD.parquet`，全市场当日，同 §1 列） | 242 / 244 / 243 / 238 / 245 | 2010–2014 |
| 2015、2016、2018、2019 | **按证券年度 CSV**（`sh600000_2015.csv`） | 2607 / 2834 / 3370 / 3572 | 2015、2016、2018、2019（**无 2017**） |
| 2025、2026 | 按日 Parquet | 243 / 63 | 2025、2026（研究窗口外） |

- 校验：`manifest/extract-summary.json` 的逐年成员数/字节与本次解压**逐年一致**；
  2010–2013 另有 `manifest/years/*.sha256.txt` 逐文件 SHA-256 清单，解压后**逐一比对通过**
  （共 967 个文件）；其余年份以 zip 成员 CRC 与成员数/字节为准。全过程见 `docs/evidence/minute-extract.json`
  与 `docs/evidence/minute-manifest.json`。
- 包级 SHA-256 的历史记录（**非本次重算**）：`manifest/zips.sha256.json` 的 11 项
  （与下载源逐字节比对，全部 match）——原件已删除，包级摘要不可再重算。
- 按证券 CSV 的列：`时间,代码,名称,开盘价,收盘价,最高价,最低价,成交量,成交额,涨幅,振幅`（UTF-8）。
  **成交量为「手」**（×100 得股），价格与成交额为元。
- 与 §1 整包**同源但不同快照**：2019-05-06 `sh603026` 首根两包逐字段相同（量 2423 手 = 242300 股）；
  2015-07-01 `sz000032` 首根存在差异（整包 32000 股 / 652800 元 vs CSV 316 手 / 644640 元）。
  两包**不能互为独立验证**，混用需登记。

### 2.2 `minute-bulk-20260915-1/manifest/`

- `zips.sha256.json`：原始压缩包身份与校验（**历史证据**，包已删除）。
- `extract-summary.json`：2010–2019 解压记录（逐年成员数/字节/耗时/错误），现在同时是 `years/` 的内容基准。
- `years/*.sha256.txt`：2010–2013 解压层的逐文件校验清单（**当前有效**，覆盖 967 个文件）。

### 2.3 其它批次

| 批次 | 内容 |
|---|---|
| `intraday-t0-20260914/` | 指数/ETF 的 `bar1m`、`bar1d` CSV（`date,instrument,open,high,low,close,volume,amount`）+ `fetch_log.json` |
| `minute-check-20260914-1/` | BigQuant SDK 只读查询 CSV（8 字段，639 证券日/77 日期），补充来源证据 |
| `minute-repairs-20260914-1/` | 33 项分钟补丁 `patches.json`（仅替换 3 个证券日，其余 30 项不变） |

---

## 3. `user_dataset/` — 用户日线数据集（百度网盘）

| 项 | 内容 |
|---|---|
| 形态 | `2026-09-03/{上证,深证}/{不复权,前复权,后复权}.zip`，zip 内每证券一个 CSV |
| 成员 | 上证 2316 只（`600000_浦发银行.csv` … `689009_九号公司.csv`）；深证 3185 只（含 `399998_中证煤炭指数.csv` 等指数） |
| 列 | `日期,代码,股票名称,开盘价,最高价,最低价,收盘价,前收盘价,成交量(股),成交金额(元),换手率(%),涨跌幅(%),涨跌额,振幅(%)` |
| 编码 | UTF-8 BOM + CRLF；起始 1999-11-10 |

陷阱：三种复权形态**分别单独分发**，不要混用；`前收盘价` 为源给出字段，与 baostock `preclose` 不保证一致。

---

## 4. `baostock/` — 日线 / 复权因子 / 5 分钟 / 退市与 ST 补齐

| 批次 | 内容 |
|---|---|
| `daily/` | 5552 只证券日线 CSV + `.meta.json`；列 `date,code,open,high,low,close,preclose,volume,amount,adjustflag,turn,tradestatus,pctChg,isST`；`adjustflag=3` 为**不复权**；区间 1999-11-10 … 2026-09-04 |
| `adjust_factor/` | 343 只证券的复权因子；列 `code,dividOperateDate,foreAdjustFactor,backAdjustFactor,adjustFactor`（**注意覆盖率仅 343 只**） |
| `minute/` | 研究批次：`*_f5.csv` + `.meta.json` 共 2357 组（按证券日的 5 分钟补数，不是全量分钟库） |
| `20260905_225721/`、`20260905_230017/` | 板块/停复牌/ST/交易日等参考数据抓取批次 |
| `intraday-t0-*`、`ten-year-repair-*`、`*-dynamic-minute-*`、`t0-minute-evidence-20260911` | 各研究阶段的按需补数批次 |

| `etf-daily-20260919-r1/` | **失败批次（status=failed，留档）**：ETF 日线补拉探针与池差集。结论=**baostock 对 2015–2024 窗口不存在 ETF 日线**——`query_history_k_data_plus` 基金代码恒空集、`query_daily_history_k_ETF` 历史仅回溯 ~2026-02（证据 `artifacts/runs/20260919T021519-etf-pull-74d0/endpoint_probes.json`；重试脚本 `fetch_etf_daily_byday.py` 随目录保留） |

陷阱：baostock **串行**、需 login/logout 配对与节流；2020 年前**无分钟数据**；
`volume` 为股、`amount` 为元；`tradestatus`/`isST` 是历史状态字段，可用于退市与 ST 判定；
**ETF 日线不要再用 baostock**（上表失败批次已钉死，ETF 主源=tushare `fund_daily/20260917-r1`，见 p3-band-contract §6）。

---

## 5. `tushare/` — Tushare 官方财务与日指标（46 个批次目录，24 个数据集）

| 数据集 | 分块数 | 说明 |
|---|---:|---|
| `balancesheet` `cashflow` `income` | 5905 / 5909 / 5904 | 财报三表，逐股历史 |
| `fina_indicator` | 5904 | 财务指标 |
| `daily_basic` | 2845 | 每日指标（18 列：`ts_code,trade_date,close,turnover_rate,…,total_share,float_share,free_share,total_mv,circ_mv`）；**分两批** `20260909-r1`（2019 起）与 `20260913-r2`（2015–2018 回补），读取需合并 |
| `dividend` | 2844 | 分红除权 |
| `disclosure_date`、`express`、`forecast`、`repurchase`、`stk_holdertrade` | 33–131 | 披露日/快报/预告/回购/股东增减持 |
| `margin_detail`、`top_list`、`top_inst` | 1867 / 1868 / 1868 | 两融明细、龙虎榜 |
| `share_float`、`sw_index_daily`、`sw_index_daily_l2` | 131 / 131 / 133 | 解禁、申万行业指数 |
| `stock_basic`、`trade_cal`、`fund_basic`、`index_member_all` | 少量 | 参考数据 |

陷阱：财务数据**时点纪律**——报告期 Q 的数据在 Q 结束后 90 天才对回测可见（旧库既定规则），
防未来函数；`trade_date` 为 `YYYYMMDD` 字符串；`total_share/float_share` 单位万股。

---

## 6. `xiaodefa/` — Tushare 兼容代理全量取数（63 个数据集，13.11 GiB）

- 目录结构：`<dataset>/<批次>/chunk_<YYYYMMDD>.csv`（日频按交易日）或逐股分块；每数据集独立 manifest。
- 已 100% 完成（按旧库盘点）：`adj_factor`(3088 日)、`stk_limit`(3088)、`stk_auction_c`(3088)、
  `moneyflow`(3088)、`stk_nineturn`(3088)、`idx_factor_pro`(3088)、`cyq_perf`(2111)、`ths_daily`(3088)、
  `daily_info`、`sz_daily_info`、`ggt_daily`、`block_trade`、`suspend_d`、`hk_hold`、`ccass_hold` 等。
- 参考/快照类：`stock_basic`、`trade_cal`、`index_basic`、`index_classify`、`fund_basic`、`etf_basic`、
  `cb_basic`、`ths_index`、`dc_index`、`tdx_index`、`stock_company`、`namechange`、`st`、`stock_st`、
  `bse_mapping`。月频宏观：`cn_m/cn_cpi/cn_ppi/cn_pmi/sf_month`。
- **未拉全**（代理 token 于 2026-09-14 过期）：`stk_auction_o` 缺 1 日、`sw_daily` 缺 2 日、
  `ci_daily` 2757/3088、`top10_holders` 5893/5899、`top10_floatholders` 3049/5899、
  `stk_holdernumber`/`pledge_stat`/`pledge_detail`/`stk_managers`/`stk_rewards`/`fina_mainbz`/`fina_audit`
  未开始、2014–2018 港股通/两融补旧未完成、`cn_schedule` 仅 9/153。
  完整盘点见 `docs/legacy/artifacts-evidence/xiaodefa-bulk-20260913/inventory-20260914.json`。
- `skipped-datasets.json`：用户决定不拉的项与「恒 0 行」接口（多为参数口径问题）。
- 分钟补丁链：`minute-repairs-20260913-{3,4,5,6}/`、`minute-repairs-20260914-{1,2,3}/patches.json`，
  是 1 分钟包的修正清单（**补丁清单本身是数据身份的一部分，不要重命名**）。
- 凭据：token 只存 `~/.quant-credentials/xiaodefa-token`。

陷阱：该代理 `stk_mins` 与 §1 整包**同源**，不能互为独立验证；接口限流与单次上限按接口不同
（概念/行业 2000、通达信 1000、部分 5000），截断文件曾以 `*.csv.truncated*` 隔离。

---

## 7. 复核与辅助源

| 来源 | 内容 | 陷阱 |
|---|---|---|
| `tx/` | 腾讯前复权日线 + 批量快照，`<symbol>/<抓取时刻>/{meta.json,response_*.json}` | 科创板 `volume` 原始为**股**，其余板块为**手** |
| `sina/` | 未复权 K 线复核（181 个证券目录，2 批次） | 未复权，需另配复权因子 |
| `sina_universe/` | A 股全市场列表（560 文件/280 批次） | 时点快照，不能当作历史在市名单 |
| `sina_industries/` | 行业分类 | **未覆盖科创板**，历史行业缺口存在 |
| `ths/` | 同花顺 ETF 前复权日线（`response.json` + `meta.json`） | 仅近 5 年；key 走环境变量，不入库 |
| `em_fin/` | 东财 F10 季报主要指标（每证券 `response.json`，最近 9 期） | 季度粒度、披露滞后，务必按 90 天规则使用 |
| `etf-minute-probe/` | ETF 5 分钟探针批（2026-09-09） | 探针，非全量 |
| `hf_minute_1m/` | 第三方 22 只证券 1 分钟（2010–2026） | 与 §1 整包逐字段相同，属子集副本；`20260913-probe/` 是来源探针记录 |

---

## 8. `user_csv_1m/` — 仅保留身份记录

7 个文件（3 份 `patches.json`、`transfer-manifest.json`、`validation.json`、2 个小体量 `*_f5.csv`）。
其余内容在 2026-09-16 去重中删除，因为与 `bigquant/years`（当时已删，现已解压重建）、
`xiaodefa/minute-repairs-20260914-1/` 逐字节重复。删除明细见 `docs/DEDUPE_REPORT.md`。

---

## 9. 已删除的数据

| 路径 | 原因 |
|---|---|
| `bigquant/minute-bulk-20260915-1/zips/`（21 个 zip，51.95 GiB） | 2026-09-16 解压为 `years/` 后删除；逐成员 CRC、成员数/字节、2010–2013 逐文件 SHA-256 全部通过（`docs/evidence/minute-extract.json`） |
| `user_minute_1m/*/<year>.zip`（10 个 zip） | 同上，解压为 `<批次>/<年>/` 目录层 |
| `free-stockdb/`（2.06 GB） | 第三方 Windows 工具包（`stockdb.exe` + 未解析 `data1/*.ldb`），非研究口径数据、无 manifest |
| `user_csv_1m/` 数据集内容（6.94 GB） | 与 `bigquant` 逐字节重复 |
| `hf_minute_1m/20260913-all22/`、`20260913-redownload/` | 与 §1 整包逐字段相同的子集副本 |

注：早期整理曾删除 `bigquant/years/` 解压层（保留 zip）；2026-09-16 按用户要求反转为
「保留解压层、删除压缩包」，最终形态即 §2.1。

---

## 10. Wind MCP（插件在线检索，2026-09-19 只读探测盘点）

角色：**只读在线交叉核验与权威公告检索源**，非批量下载库——自然语言接口、单次行数受限，不适合全量落地；如未来需落地为数据，按追加批次 + manifest 纪律另行执行。Wind 与 tushare/baostock 属不同上游封装，可作独立交叉验证（不同于 §1/§2 同源陷阱）。纪律：只发市场数据查询，不发送任何私有输入。

实测结论（探测日 2026-09-19，逐项证据为当次查询输出）：

| 能力 | 工具 | 结论 |
|---|---|---|
| ETF 日线 K 线（不复权/复权） | `wind-fund get_fund_kline` | **可用**。513100 于 2022-01-04~20 与 tushare `fund_daily` 逐字段一致（01-07 收 5.188、01-12 收 5.192、01-14 开 1.010/收 1.015/量 125,644,069/额 126,977,793）；且**停牌日有占位行**（2022-01-13 OHLC=5.192、量额 null）——tushare 无该行，Wind 可作停牌的独立证据与 ETF 主源交叉复核 |
| ETF 分钟历史 | `wind-fund get_fund_quote` | **不可用**：513100 2022-01-14 分钟查询空返回；ETF 分钟缺口（p3-band-contract §6）Wind 补不上 |
| ETF 分红记录（结构化） | `wind-fund get_fund_financials` | **不可用**：510880 查询 2021–2024 分红返回 0 次（实际 4 次），场内 ETF 覆盖缺失 |
| 基金/上市公司公告检索（文本） | `wind-docs get_company_announcements` | **可用且权威，本项目最高价值能力**。已用于：① 513100 国泰份额拆分公告（比例 1:5 整数、总份额精确 ×5）与 513500 博时拆分公告（1:2）——引擎 v1.3 S-v13-1/2 接缝据此关闭（证据见实施运行目录 `tmp/corporate-action-announcements-evidence.md`）；② 510880 华泰柏瑞收益分配公告（每 10 份 1.310 元、除息 2024-01-23）与本地因子检测隐含分红 0.131 元/份逐分吻合 |
| 股票分红结构化事件 | `wind-stock get_stock_events` | **可用**：600519 2019–2021 返回除权除息日 + 税前每股派息（17.025/19.293/21.675；除息 2020-06-24/2021-06-25/2022-06-30），可作股票分红 bundle 交叉源 |
| 指数日线 | `wind-index get_index_kline` | **可用**：000300.SH 2021-01-04~08 正常返回，可交叉复核基准指数 |
| 涨跌停价（历史） | `wind-fund/wind-stock get_*_price_indicators` | **不可用**：仅最新交易日快照（513100/510880 实测返回 2026-09-18 当日涨停/跌停），无历史序列，不能补 ETF 历史涨跌停表（§8.3 计算规则仍为唯一口径） |
| ST/退市历史状态 | `wind-stock get_stock_basicinfo` | **受限**：仅当前状态快照，不含状态变动历史，不能替代 baostock `isST`/`tradestatus` 的历史池过滤 |
| 股票/基金财务、宏观 EDB | `wind-stock`/`wind-fund`/`wind-economic` | 未探测（财务主源 tushare 三表已全；EDB 暂无当期需求）——待有具体需求再测 |

---

## 11. 同花顺插件 hexin（ZCode 网关 iFinD，2026-09-19 会话重启后探测）

插件 v0.1.0（`requiresPaidPlan`，网关认证），五组服务 stock/global-stock/index/fund/bond。**当前为试用账号**（分钟端点报 `-4309`：trial account 仅 1 年数据）。纪律同 §10：只读、只发市场数据查询。与 `data/raw/ths/`（§7，环境变量 key 的 HTTP 抓取、仅近 5 年）是**不同通道**。只测了 §10 未覆盖的缺口，与 Wind/tushare 重叠的能力（财务/估值/股东/指数日线）未测。

| 能力 | 工具 | 结论（2026-09-19 实测） |
|---|---|---|
| ETF 日线（股票端点直收 ETF 代码） | `hexin-stock get_stock_performance` | **可用**：513100 2022-01 窗与 tushare `fund_daily`、Wind 三源逐字段一致（含 01-13 停牌占位行 OHLC=前收、量额 null，与 Wind 同形、tushare 无该行）；另有换手率列。第三个独立 ETF 日线交叉源 |
| 历史分钟 | `stock_highfreq_quotes` | **不可用（试用账号）**：请求 2022-01-14 分钟报 `-4309` trial account 1 年限制；日线端点不受此限（2022 数据正常返回）。研究窗 2015–2024 分钟缺口仍补不上 |
| 问财历史时点状态（ST PIT 过滤） | `search_stocks` | **不可用**：两次问法（"2021-06-30 处于 ST 状态"、"2021-06-30 当天简称包含 ST"）均静默丢弃日期条件，返回**当前** ST 名单（混入 2024 年后才戴帽的 ST闻泰/ST华谊/ST绝味/ST人福 等，及 920 北交所新代码段）——印证该工具 docstring 自己的"条件静默丢弃"警告。历史池过滤仍只能靠 baostock `isST`/`tradestatus` |
| 问财一般筛选 | `search_stocks` | 现状条件筛选可用但**不保证问法全条件被解析**，每次须核对返回列；任何"历史某日"类条件视为不可用，除非有独立证据 |

结论：hexin 当前对本仓库的增量 = **第三个 ETF 日线交叉源**；两个高价值缺口（ETF 历史分钟、PIT 状态过滤）一个卡在试用账号、一个能力不存在。若用户转正式账号，可重测分钟端点的历史深度（但研究窗在冻结区外的部分有限，优先级低）。
