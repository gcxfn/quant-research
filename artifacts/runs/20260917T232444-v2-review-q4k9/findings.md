# v2 bundle 独立复核（双签制第二签）findings

- run_id: `20260917T232444-v2-review-q4k9`
- 复核对象: `data/processed/rqalpha-bundle-v2-20260917/` + 交付 run `artifacts/runs/20260917T231506-rqalpha-bundle-v2-3c3ffecd/`
- 方式: 只读复核，全部脚本在本 run `tmp/` 下，抽样种子固定 `20260917`，结论全部用原始 chunk 重新数值比对得出，未照抄任何 manifest 自述。
- 环境: `D:/量化/.venv/Scripts/python.exe -X utf8`（Python 3.11.15, h5py/polars/numpy）。
- 状态: **completed**；未修改 bundle、源数据或任何既有文件；未运行回测引擎。

## 总表

| # | 项目 | 结论 | 关键数值 |
|---|---|---|---|
| 1 | 规模与覆盖 | **PASS**（附说明） | stocks 4745 键 / funds 1169 键；日历 2431 天 [20150105..20241231] |
| 2 | 冻结边界 | **PASS** | 全库 5914 只扫描 max datetime = 20241231000000，越界 0 只 |
| 3 | ETF bar 保真 + 单位 | **PASS** | 3 ETF×5 日 OHLC 逐值全等；volume=vol×100、turnover=amount×1000 精确成立 |
| 4 | 股票涨跌停 | **PASS** | 5 对 (股票,日) 逐值全等（含 000001.XSHE 20241202）；5 个空 chunk 日全 NaN |
| 5 | ex_cum_factor 映射 | **PASS** | 因子 ≡ tushare adj_factor（max\|ratio−1\|=0.0）；已知除息隐含分红 0.0518 ≈ 公告 0.053 |
| 6 | dividends | **PASS**（附 1 个 minor 语义提示） | 000001 2020 行 21.8 = 0.218×100 精确；r2/r3 拼接 2018 无断层 |
| 7 | 股票 bar 保真 | **PASS** | 2 股×3 日 OHLC/volume/turnover 位级全等；adjustflag=3 |
| 8 | instruments.pk | **PASS** | 5 只抽查全部与 stock_basic/fund_basic 一致；CS 4745 + ETF 1169 + INDX 1 |
| 9 | 占位披露 | **PASS**（附 1 个 minor 披露缺口） | 000001.XSHG 全 NaN 占位、000300 真实且与源文件全等、yield_curve 全 0 |
| 10 | 交付 run 断言对照 | **PASS** | A1–A5/A13/A14 与我的独立结果一致；A6–A12 引擎项未重跑但数据前提已抽验 |

无 critical / major 不一致。

---

## 1. 规模与覆盖 — PASS

- `stocks.h5` 键数 **4745**，`funds.h5` 键数 **1169**，两库键无交集。
- `trading_dates.npy`: int64、**2431** 天、首 **20150105**、尾 **20241231**、严格递增；含 20170307、20241202 等真实交易日。
- instruments.pk: CS 4745 + ETF 1169 + INDX 1（000300.XSHG 基准）= 5915；`ex_cum_factor.h5` 键 = 5914 = 股票+ETF 全集（无缺失、无多余）。
- 股票池与源数据一致：baostock parquet 唯一 symbol **5328** = 4745 + **583** 只 688/689（科创板）剔除，无 bj；前缀分布 000/001/002/003/300/301/302/600/601/603/605。
- 说明：任务书预期"约 3300+ 股票"与实际 4745 不符，但 4745 与 bundle manifest（stock_pool_size=4745）及池来源推导**精确一致**；3300+ 应为旧口径（任一时点并存家数口径，本 bundle 为 2015–2024 十年累计有行情家数）。不判 FAIL。

## 2. 冻结边界 — PASS

- 抽样（种子 20260917，含指定 000001.XSHE / 510300.XSHG）：10 只最大 datetime 均 ≤ 20241231000000（其中 515500.XSHG 因 20230131 终止，max=20230131，属正常生命周期）。
- **全库扫描**（stocks+funds 共 5914 只，仅读 datetime 字段）：global max = **20241231000000**，max_day = **20241231**，**0** 只存在 20241231 之后的 bar。

## 3. ETF bar 保真与单位换算 — PASS

抽样 3 只：510300.XSHG（指定）、511310.XSHG、515090.XSHG（种子随机），各 5 个日期：

- OHLC 与 `fund_daily` chunk **逐值位级全等**（15 行×4 字段 exact_equal=True，max_abs_diff=0.0）。
- **volume 单位（数值证明）**：bundle volume = `vol[手] × 100`（份），float64 同一运算下逐值全等（含 510300 20210331 的 2308126.76×100=230812675.99999997 浮点尾部一致），比率 = 100.0。
- **total_turnover 来源（数值证明）**：bundle total_turnover = `amount[千元] × 1000`（元），逐值全等，比率 = 1000.0。
- 全量 1,017,121 行隐含 VWAP = turnover/volume 落在 [low, high] 内 **1,007,948 行（99.10%）**；9,173 行在外，其中 8,095 为 one-price 日（high==low，源数据舍入必致细微偏离，其中 3,075 行同时成交额<1000 元）、3,336 行成交额<1000 元；剩余 **817 行**成交量中位数仅 602 份（709/817 < 1 万份），对当日中价最大相对偏差 **0.87%**——与 2 位小数"手"/3 位小数"千元"的源舍入量级一致。若单位错（如少乘 100/1000）偏差应为 2–3 个数量级且 100% 越界，故单位结论成立。交付 manifest 的 vwap_outside=9,172 与我的 9,173 差 1 行，为边界 epsilon 口径，无实质影响（severe violations 双方均为 0）。
- funds 库 limit_up/limit_down **全 1,017,121 行均 NaN**，与披露一致（tushare stk_limit 无 ETF 行）。

## 4. 股票涨跌停 — PASS

5 对 (股票, 日期)，limit_up/limit_down 与 `stk_limit` chunk 逐值全等：

| 股票 | 日期 | bundle | raw |
|---|---|---|---|
| 000001.XSHE | **20241202** | 12.52 / 10.24 | 12.52 / 10.24 |
| 300774.XSHE | 20231030 | 12.78 / 8.52 | 12.78 / 8.52 |
| 000929.XSHE | 20160817 | 19.93 / 16.31 | 19.93 / 16.31 |
| 002626.XSHE | 20181227 | 13.34 / 10.92 | 13.34 / 10.92 |
| 301608.XSHE | 20241107 | 78.84 / 52.56 | 78.84 / 52.56 |

5 个 header-only chunk 日（20170307/08/09、20220726、20230421）raw 行数=0，bundle 当日全部 bar（3130/3131/3131/4296/4453）limit 字段均 NaN，与"NaN=无涨跌停限制"披露一致。

## 5. ex_cum_factor 映射 — PASS

对 510880.XSHG（11 个变点）、510050.XSHG（10）、510300.XSHG（11）：

- **数学关系：恒等映射。** 每个变点 bundle 因子与同日 tushare `adj_factor` **完全相等**（max |ratio−1| = 0.0，三个 ETF 全部变点无一例外）；仅在序列头部前置 rqalpha 约定的锚点行 (0, 1.0)。无归一化、无常数倍数。首末值与 fund_adj 首末值一致（如 510880: 1.1245 → 1.6557）。
- 因子序列单调不减；`start_date` 为 14 位 YYYYMMDDHHMMSS 编码（与 manifest contract 一致）；159842.XSHE 无 adj 数据，仅锚点行（与披露一致）。
- **除息日跳变与价格一致性**：隐含每单位分红 D = pre_close × (1 − f_pre/f_ex)。
  - 已知公告案例 510050 20161129：D = 2.407×(1−1.2093/1.2359) = **0.0518 元/份**，对照公告每 10 份 0.53 元（0.053），偏差 2.3%，处于源精度内（价格 3 位小数、因子 4 位小数的舍入量级约 ±0.5–2%）。交付 manifest 用除息日收盘价作基数得 0.0538，同样落在公告值附近——两种基数算法结论一致。
  - 510880 全部 10 个年检变点（20150120..20240123）隐含分红 0.049–0.137 元/份，与其年度分红节奏吻合；除息日全收益口径 (close+D)/pre_close−1 在 +0.4%~+5.8%（2015 年 1 月高波动期最大），即"未复权收盘跌幅 ≈ D"仅在市场当日不动时严格成立，本复核实测均在该语义下无矛盾。

## 6. dividends — PASS（附 minor）

- `dividends.h5['000001.XSHE']` 共 **11** 行，全部落在 2015–2024（年度分红 20150413..20240614 + 20241010 特别分红），与"每年应有分红"相符。
- 2020 行数值比对：bundle `dividend_cash_before_tax` = **21.8**（round_lot=100）= tushare `cash_div` **0.218 元/股 × 100**，精确相等；payable_date 20200528 == raw pay_date；book_closure 20200527 == record_date。
- r2/r3 拼接：r2 覆盖 chunk 20150105..20171229，r3 覆盖 20180102..20260909；原始 `实施` 行按年：2015:2405 / 2016:2416 / 2017:2805 / **2018:3209** / 2019:3013 / … / 2024:5358——**2018 无断层**；bundle 行按年 2206/2152/2540/2904/2715/2734/2943/3063/3166/4027（2015–2024）每年皆有，约占 raw 的 85–90%，与 4745 只池过滤（剔 688/689）及去重 676 行的口径一致（bundle 28450 行 = codes_with_dividends 4512）。
- **[minor] 字段语义提示**：bundle 取 tushare `cash_div` 并命名为 `dividend_cash_before_tax`；数值上与源精确一致，但 raw 中有 **2,095 / 42,561** 行 `cash_div < cash_div_tax`（旧差别化税收年代，如 000001 20150413：0.1653 vs 0.174），这些行 `cash_div` 实为税后口径，"before_tax"命名不成立。金额本身忠于所选源字段，仅命名/语义需注意，不构成数值错误。

## 7. 股票 bar 保真 — PASS

600036.XSHG（20151118/20160817/20210709）、000651.XSHE（20160622/20210316/20210330）对 baostock parquet 逐值比对：OHLC、volume、total_turnover（=amount）**全部位级全等**（max_abs_diff=0.0）；抽样行 `adjustflag='3'`（不复权）确认。附带验证：000651 20160622 停牌日 bar（volume=0, tradestatus=0）被原样保留，未伪造行情。

## 8. instruments.pk — PASS

抽查 5 只（3 股 + 2 ETF，含指定的 000001.XSHE、510300.XSHG）：

| oid | type | round_lot | listed_date | 源 list_date | de_listed_date | 名称一致 |
|---|---|---|---|---|---|---|
| 000001.XSHE | CS | 100 | 1991-04-03 | 19910403 | 2999-12-31（源 null） | 平安银行 ✓ |
| 300774.XSHE | CS | 100 | 2021-08-04 | 20210804 | 2999-12-31 | 倍杰特 ✓ |
| 600148.XSHG | CS | 100 | 1998-05-20 | 19980520 | 2999-12-31 | 长春一东 ✓ |
| 510300.XSHG | ETF | 100 | 2012-05-28 | 20120528 | 2999-12-31 | 华泰柏瑞沪深300ETF ✓ |
| 159672.XSHE | ETF | 100 | 2023-04-03 | 20230403 | 2999-12-31 | 博时中证主要消费ETF ✓ |

全部 market_tplus=1；INDX 仅 000300.XSHG（round_lot=1）。

## 9. 占位复核 — PASS（附 1 个 minor 披露缺口）

- `indexes.h5['000001.XSHG']`：2431 行、OHLC 全 NaN、volume 全 0、turnover 全 NaN——**仍是占位探针**（真实无数据）。
- `indexes.h5['000300.XSHG']`：**826 行真实数据**（20210805..20241231），5 个抽样日对源文件 `data/raw/bigquant/intraday-t0-20260914/000300.SH_2021-08-05_2024-12-31_bar1d.csv` OHLC/volume/turnover **逐值全等**。
- `yield_curve.h5`：2431 行，日期与日历完全一致，10 个期限列**全 0**。
- 其余披露逐项验证：futures.h5 空 ✓、share_transformation.json = {} ✓、future_info.json 单条 PLACEHOLDER 结构行 ✓、159842 identity-only ✓、ETF 不在 dividends/suspended/st ✓、split_factor = 1 + stk_div（000001 20150413: 1.2 = 1+0.2 ✓）。
- **[minor] 披露缺口**：bundle manifest 的 `placeholders`（10 条）**未列入** indexes.h5 的两条事实：(a) 000001.XSHG 为全 NaN 探针行；(b) 000300.XSHG 基准 bar 仅覆盖 **2021-08-05..2024-12-31**（源文件即此窗口）。仅在 `params.range_probe_oid/benchmark_oid` 及 inputs 文件名（含日期）中隐含。对本次 2024-10..12 冒烟窗口无影响；但若对 2015–2021-08 全窗口回测，基准早期将无 bar。建议在 manifest placeholders 中补一条明示（属披露完备性问题，非数据错误——本复核不修改，留待交付方处理）。

## 10. 交付 run 断言 vs 本次复核 — PASS

| 交付断言 | 交付结果 | 我的独立复核 | 一致性 |
|---|---|---|---|
| A3 日历 | PASS 2431 天 [20150105,20241231] | 同 | ✓ |
| A1 股票 bar | PASS 150 值全等 | check7 全等（重抽不同样本） | ✓ |
| A2 ETF bar | PASS 80 值全等 + 单位 | check3 全等 + 单位证明（VWAP 口径独立复核） | ✓ |
| A4 冻结/indexes | PASS 5914 只 max 20241231 | 全库扫描同为 5914 只 / max 20241231 | ✓ |
| A5 instruments/文件 | PASS CS4745+ETF1169+INDX1 | 同 | ✓ |
| A13 ex_cum_factor | PASS（恒等映射叙述） | 恒等映射证实（ratio≡1.0）；隐含分红数值因基数价选择略异（0.0538 vs 0.0518），结论相同 | ✓ |
| A14 涨跌停 | PASS 5 对 + NaN 规则 | 同（重抽，含 20241202） | ✓ |
| A6 引擎成交 | PASS 14 笔 | 引擎未重跑（按约束）；但 14 个成交价与 bundle bar close 逐一核对**全等** | ✓（数据前提） |
| A7/A8/A9/A10/A11/A12 | PASS | 引擎行为项，超出本次数据复核范围（UNVERIFIED-by-rerun）；A12 依赖的 dividends.h5 数据侧已由 check6 证实 | 不适用 |

## 不一致清单（均非数据错误）

1. **[minor]** bundle manifest `placeholders` 未披露 indexes.h5 中 000001.XSHG 全 NaN 探针行与 000300.XSHG 覆盖窗口仅 20210805–20241231 的事实（见第 9 项）。
2. **[minor]** `dividend_cash_before_tax` 命名与 tushare `cash_div` 在 2,095 行旧税制记录上的实际（税后）语义不符；金额本身与所选源字段精确一致（见第 6 项）。
3. **[note]** 任务书"约 3300+ 股票"预期与实际 4745 不符，但与 bundle manifest 及池推导精确一致（十年累计口径，见第 1 项）。
4. **[note]** 交付 A13 的 implied dividend（0.0538）与我的独立算法（0.0518）基数价不同，两者均 ≈ 公告 0.053；fund_daily VWAP 越界计数 9,172 vs 9,173 为 epsilon 口径差。均无实质影响。

## 三个换算关系的数值结论

- **ETF volume**：`bundle.volume = fund_daily.vol[手] × 100`（份），抽 15 行比率=100.0 且 float64 位级全等；全库隐含 VWAP 检验支持（99.10% 落于 [low,high]，例外均可归因源舍入）。
- **ETF total_turnover**：`bundle.total_turnover = fund_daily.amount[千元] × 1000`（元），同样位级全等（比率=1000.0）。
- **ex_cum_factor**：`bundle.ex_cum_factor(t) = tushare fund_adj.adj_factor(t)`（恒等，ratio−1 最大值 = 0.0），仅在头部加 rqalpha 锚点 (0, 1.0)；无归一化、无缩放。
