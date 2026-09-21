# ETF 数据侦察 + bundle 停建报告

- run_id: `20260918T202734-etf-recon-1d83`
- 日期: 2026-09-18；性质: 数据基础设施（只读侦察 + 身份登记），不运行回测、不消耗试验次数、不修改 `data/raw`、不做 git、不联网。
- 结论级别标注: 【实测】= 本次直接扫描数据；【台账】= 引用 `data/_meta/deep-scan-20260917/` 或批次 manifest，未重扫。

---

## 0. 一句话结论

**`data/raw` 内不存在任何 ETF 历史分钟数据**；同时任务指定的 bundle 主源（baostock 日线，processed 与 raw 一致）**不含任何基金代码（0/5410）**，第 2 步输入前提不成立，按纪律**停建** `data/processed/etf-daily-20260918/`，等用户决策替代主源后再建。

---

## 1. 分钟源结论（第 1 步核心问题）

| 问题 | 答案 | 证据 |
|---|---|---|
| `user_minute_1m` 是否完全没有 ETF 代码 | **是，完全没有** | 【实测】两个批次（`20260913-143215/` 2015–2019、`20260913-2020-2024/` 2020–2024）共 **2431 个**日 parquet 的 `code` 列全量扫描（pyarrow 线程池，17.8s，0 错误）：唯一代码 5589 个，**基金前缀（51/56/58/15/16 开头）0 个**，0 个文件含基金代码。逐年代码数 2811→5435，全为股票。 |
| data/raw 里有没有任何其他分钟级源覆盖 ETF | **没有历史分钟覆盖**；唯一"ETF 分钟"痕迹是探针 | 见下表：`etf-minute-probe/20260909_etf_m5_probe`（3 只 ETF 的 5 分钟**可行性探针**，新浪 3 份约 43KB 近端响应，summary 自述 "ETF 5-minute source feasibility only"、"Raw response presence does not prove valid OHLCV coverage"）；`hf_minute_1m` 仅剩 `000607.SZ`（股票）探针记录，22 只数据副本已删（DATA_SOURCES 记其为 §1 整包子集，故不改变上面结论）；`bigquant/intraday-t0-20260914` 15 个文件全部是 `000300.SH`（指数）bar1m/bar1d/f5；baostock 全部分钟补数批次文件名 0 基金；`bigquant/minute-bulk` 2010–2014 抽样 3 文件 0 基金、2015/16/18/19 按证券 CSV 12,383 个文件名 0 基金（2025/2026 目录冻结未读内容）。 |

## 2. 源 × ETF 覆盖表（研究窗口 2015–2024）

| 源/批次 | 类型 | ETF/基金代码数 | 日期范围（窗内部分） | 口径/备注 |
|---|---|---:|---|---|
| `user_minute_1m/20260913-143215` + `20260913-2020-2024` | 1 分钟按日 parquet | **0**（实测全扫） | 2015–2024（无 ETF） | 5589 唯一代码全股票 |
| `bigquant/minute-bulk-20260915-1/years/2010–2014` | 1 分钟按日 parquet | 0（抽样 2010/2012/2014 各 1 文件） | 窗外（2010–2014） | 同包族，预期同构 |
| `bigquant/minute-bulk-20260915-1/years/2015,2016,2018,2019` | 1 分钟按证券年度 CSV | 0（12,383 个文件名扫描） | 窗内 | 文件名 `sh600000_2015.csv` 型 |
| `bigquant/minute-bulk .../years/2025,2026` | 1 分钟按日 parquet | 未读（冻结） | 窗外 | 冻结纪律：未读内容，仅登记 |
| `bigquant/intraday-t0-20260914` | bar1m/bar1d/f5 CSV | **0（指数 000300.SH 专属）** | 2021-08-05–2024-12-31 | 15 文件全为 000300.SH |
| `bigquant/minute-check-20260914-1` | SDK 查询证据 CSV | 0 | 2015–2024 | instrument 为 `600163.SH` 型个股 |
| `baostock/minute`（2357 组）+ 9 个 `*-dynamic-minute-*`/`t0-minute-evidence`/`ten-year-repair`/`rev11-minute-probe` 批次 | 5 分钟补数/证据 | **0**（文件名扫描） | 2020 起按需 | 全为个股证券日 |
| `etf-minute-probe/20260909_etf_m5_probe` | 5 分钟探针 | **3 只**（sh510300, sz159915, sh588000） | 仅 2026-09 近端数根 | 可行性探针，**非历史覆盖**；fetch 多源失败仅 sina 成功 |
| `hf_minute_1m/20260913-probe` | 1 分钟探针记录 | 0（000607.SZ 股票） | 2015-07-01 单日 | 22 只副本已删，只剩探针与 README（HuggingFace `neigezhu/china-a-share-1min-ohlcv` 来源记录） |
| `baostock/daily`（5552 证券）+ `data/processed/baostock-daily-20260917/`（5410 符号） | 日线 | **0**【实测：raw 文件名 0 命中；processed 前缀直方图无基金】 | 1999-12-19–2024-12-31 | 前缀分布：300/002/600/603/688/000/301/601/605/001/003/302/689，**无 51/56/58/15/16** |
| `user_dataset/2026-09-03`（6 zip，上证 2316 + 深证 3185） | 日线（三复权） | **0**（zip 成员名实测） | 1999-11-10 起 | 深证 399xxx 为指数；无基金 |
| `sina/`（181 目录中 **58 只 ETF**） | **未复权日线**（scale=240, datalen=6000） | 58 | 最早 sh510050 2005-02-23；末日 2026-09-04 | 列仅 day/OHLC/volume，**无 amount、无 tradestatus**；>2024-12-31 需冻结过滤 |
| `ths/`（58 只 ETF，71 批次）【台账】 | **前复权日线** | 58（与 sina 集合完全相同，comm 差集为空） | 2021-09-06–2026-09-02 | 窗内仅约 3.3 年；key 走环境变量；>2024 冻结行每批约 405 |
| `tx/`（178 目录中 **55 只 ETF**）【台账】 | **前复权日线**+快照 | 55（= 58 集合去掉 sh512480/sh513100/sh516160） | 各自上市日（最早 sh510050 2005-02-23）–2026-09-04 | 已知分页边界重叠缺陷：需按 (symbol,date) 去重；>2024 冻结行每批约 407 |
| `sina_universe` `sina_industries` `em_fin` `tushare`（除 fund_basic） `xiaodefa` 截面类 | 参考/个股 | 0（em_fin 实测 0；其余为个股口径）【台账】 | - | - |
| 参考快照：`xiaodefa/etf_basic`（3414 行，含 cname/index_name/etf_type/list_date/list_status）、`xiaodefa/etf_index`（560）、`xiaodefa/fund_basic`（65,956，主键重复 32,978/65,956）、`tushare/fund_basic`（35,691，主键重复 2,945 键/5,890 行） | 基金参考表 | 全市场基金/ETF 名录 | 快照（list_date 至 2026-09） | **非 PIT**；用前需清洗去重；本轮仅用于 58 只侦察集注释 |

要点：**窗内有实质 ETF 日线历史的只有 sina（未复权，2015 起完整）与 tx（前复权，多数 2015 前上市）**；ths 只补 2021-09 之后的前复权；三源集合高度重叠（58/58/55），**互为同目标不同口径的复核源，不能当独立验证**（ths 与 tx 均为第三方行情转发）。

## 3. 第 2 步 bundle：停建说明（不硬闯）

任务预期主源 `data/processed/baostock-daily-20260917/daily_1999_2024.parquet`（symbol 形如 sh.510300）：

- 列名核实【实测】：`symbol,date,open,high,low,close,preclose,volume,amount,adjustflag,turn,tradestatus,pctChg,isST` —— 与任务描述一致；
- 内容核实【实测】：5410 个唯一 symbol 中基金前缀 **0 个**；日期范围 1990-12-19–2024-12-31；其自身 manifest 的 `boards_present` 也无基金前缀（源身份自洽，非构建事故）；raw `baostock/daily` 11,104 个文件名 0 基金（源生来无 ETF）。

若强行执行"过滤基金区间代码"将得到 **0 行** bundle——无意义且具有误导性。替代主源涉及口径决策（未复权 sina vs 前复权 tx vs 等待新源），属预登记/用户决定事项。**留给用户/预登记的选项**（不在本轮实施）：

1. 以 `sina/` 58 只未复权日线为主源建 bundle（2015–2024 完整；缺 amount/tradestatus 列；公司行动需另配）；
2. 以 `tx/` 55 只前复权日线为主源（多数覆盖 2015 前；须先解决分页重叠去重与冻结过滤；前复权价不得直接当历史成交价）；
3. 双源建仓 + 相互复核（同源异包装风险已登记：不能称独立验证）；
4. 若需要全市场 ETF 池与 LOF，须新增取数批次（本轮禁止联网）。

## 4. 第 3 步分类草稿（仅事实，不做决策，不写 configs）

对象＝**侦察集**：出现在 sina/ths/tx 的 58 只 ETF（不是全市场 ETF 池）。方法＝代码前缀 + `xiaodefa/etf_basic` 快照参考（2026-09 快照，**非 PIT**；cname 匹配 58/58）。**标注：前缀+快照启发式，未确认，与 T+0 资格无关。**

| 草稿类目 | 数量 | 符号 |
|---|---:|---|
| 股票（境内行业/宽基） | 49 | 510050/510300/510500/510880/512010/512100/512170/512200/512480/512690/512710/512800/512880/512890/512980/515030/515170/515790/515800/515880/516150/516160/516510/516970/560080/560170/560280/562800/563300/588000/588170/588220/159301/159530/159565/159611/159732/159745/159755/159766/159819/159852/159865/159869/159915/159949/159992/159996/159998 等 |
| 股票（商品链行业，跟踪股票指数，非商品期货） | 4 | 512400 有色金属、515210 钢铁、515220 煤炭、159870 化工 |
| 股票（黄金主题/油气产业） | 2 | 517520 黄金产业股票、561360 油气产业 |
| 跨境（QDII） | 1 | 513100 纳斯达克100 |
| 黄金（实物） | 1 | 518880 |
| 商品期货 | 1 | 159985 豆粕期货 |
| 债券 / 货币 / 其他 | 0 / 0 / 0 | 侦察集内无 |

逐年可得标的数（按 etf_basic `list_date ≤ 当年` 估算，未考虑退市/停牌）：2015:8 → 2016:11 → 2017:14 → 2018:15 → 2019:23 → 2020:32 → 2021:46 → 2022:48 → 2023:54 → 2024:57（588170 上市日 2025-04-08，整段在窗外）。逐符号明细见 `tmp/sina58_reference_annotation.json` 与 `tmp/recon_summary_stats.json`。

## 5. 异常与数据质量问题清单

1. 【阻塞】主日线源（raw+processed）0 基金代码 → bundle 停建（§3）。
2. 【口径】任务给定的过滤区间（sh.51*/56*/58*/sz.15*/16*）不含 **sh.50x（501/502 LOF/封基）**；etf_basic 快照中存在该区间。将来定区间规则时需决定是否纳入。sz.16x 主要为 LOF（本轮侦察集内无 16x 行情）。
3. 【冻结】ths/tx/sina 所有批次末段含 2025+ 行（每批约 405–407 行），读取层必须过滤 `>2024-12-31`；bigquant 2025/2026 分钟目录本轮未读内容。
4. 【口径】ETF 三源复权口径不一致：sina 未复权（无 amount/tradestatus）、ths 前复权仅 2021-09 起、tx 前复权但有分页边界重叠（按 (symbol,date) 去重）。前复权价不得直接当历史实际成交价。
5. 【覆盖】sina 首日晚于 etf_basic 上市日的符号 2 个：sh512010（上市 2013-10-28，sina 首日 2015-08-04，缺 645 天）、sh513100（缺 77 天）；tx 可补（tx sh512010 自 2013-10-28 起）。
6. 【窗外标的】sh588170 上市 2025-04-08，全部数据在冻结区；sz159301 2024-07-22 上市，窗内仅约 5 个月。
7. 【已删数据】hf_minute_1m 22 只 1 分钟副本已删（与 §1 整包逐字段相同），只剩 000607.SZ 探针与来源 README（HuggingFace `neigezhu/china-a-share-1min-ohlcv`），身份链以 `probe-review.json` 为准。
8. 【参考表质量】`xiaodefa/fund_basic` 主键重复 32,978/65,956；`tushare/fund_basic` 重复 2,945 键/5,890 行；etf_basic 为当前快照（含 2025+ 上市记录 1,040 行），均非 PIT，用前需清洗与时点化。
9. 【探针限制】etf-minute-probe 各源大量失败（tencent SSL、eastmoney 断连），仅 sina 成功且仅近端数根；summary 自述不构成有效 OHLCV 覆盖证据。
10. 【执行】本轮 user_minute_1m 全扫 17.8s、sha256 重算 <1s，全程未超预算（约 33 分钟墙钟，含文档阅读）。

## 6. 附录：关键实测代码摘要（无 Git，留源码摘要）

```python
# user_minute_1m 全扫（核心逻辑）
from concurrent.futures import ThreadPoolExecutor
import pyarrow.parquet as pq
def scan_file(f):
    codes = pq.ParquetFile(f).read(columns=["code"]).column(0).unique().to_pylist()
    return f, set(codes)
# 2431 文件, max_workers=8；基金前缀判定 c[:2] in ("51","56","58","15","16")
# processed 日线前缀扫描（polars）
pl.scan_parquet(p).select(pl.col("symbol")).unique()  # → str.slice(3,3) 前缀直方图
```

输入身份：`daily_1999_2024.parquet` sha256 `d9a63f4c…8a472a6`；`daily_2015_2024.parquet` sha256 `1cbb09a1…edfc1de`（完整值见 manifest.json）。
