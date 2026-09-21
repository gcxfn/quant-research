# tushare 第二轮数据拉取（batch 20260909-r1）：申万行业体系 + 财报披露计划 + 每日市值/换手

日期：2026-09-09 · 脚本：`experiments/tushare_fetch_r2_light.py`（申万日线/index_member_all/disclosure_date）、
`experiments/tushare_fetch_daily_basic.py`（daily_basic，含 `--backfill-manifest` 维护模式）·
校验：`experiments/tushare_verify_r2_pull.py` · 数据根目录：`data/raw/tushare/<dataset>/20260909-r1/`

目的：为 D-2026-09-09-09 残差均值回归预登记补齐**申万一级行业指数日线**（主线解锁项）与**时点行业归属**数据缺口，
并连带拉取财报披露计划（disclosure_date）与每日市值/换手（daily_basic）。token 仅由 `ts.pro_api()` 读自
用户目录 `~/.tushare/token.csv`，**未写入仓库任何文件、未打印到任何落盘文件**。
并发纪律按 D-2026-09-09-10：tushare 通道 2–3 workers + 每 worker ≥0.6–0.8s 节律 + 限流退避 5/15/30s +
连续限流降速；给可能仍在拉 top_list 的进程留余量（实测全程限流事件 0 次）。

## 1. 接口权限与形态探测（实测）

| 接口 | 用途 | 权限结论 | 实测形态 |
|---|---|---|---|
| `sw_daily` | 申万指数日线 | **无权限**（错误=「没有接口(sw_daily)的访问权限」，doc_id=108；积分不足） | — |
| `index_daily` | 指数日线 | **有权限但申万代码无数据**：`index_daily(ts_code='801010.SI')` 返回 OK 但 0 行 | 不支持 `.SI` 指数 → 不可用于申万 |
| `index_member`（旧） | 指数成分 | 有权限但对申万码返回 0 行（原面向 CSI 类指数） | 不可用于申万 |
| `index_member_all` | 申万行业归属 | **OK** | 支持 `offset` 分页（单页上限 3000）；`ts_code` 参数=股票代码，无参=全市场；**每股一行现时归属**，见 §4 |
| `index_classify` | 申万分类体系 | **OK** | `level=L1/L2/L3, src=SW2021` → 31/134/346 行 |
| `disclosure_date` | 财报披露计划 | **OK** | `end_date` 参数=**报告期过滤**（非披露日），返回该报告期全部公司计划（5437 行/期量级） |
| `daily_basic` | 每日市值/换手等 | **OK** | 单 `trade_date` 一次取全（2019 年约 3.5 千行 → 2026 年约 5.5 千行/日），响应 3–6s |

**申万指数日线数据源最终结论：tushare 两接口均不可得 → akshare 兜底** `ak.index_hist_sw(symbol, period='day')`
（上游=申万宏源研究 swsresearch.com 官方发布，现行 SW2021 口径回溯序列）。接口名/字段差异已记入 manifest 与本档。

## 2. 下载结果总表

| 数据集 | 范围 | 分块 | 行数 | 用时 | 缺口/失败 |
|---|---|---|---|---|---|
| sw_index_daily 申万一级日线 | 2019-01-02→2026-08-28（源站最末） | 31 指数 | 54,251 | ~7 min（akshare 串行） | 源站缺 10 个交易日 + 3 指数晚发 + 尾部滞后 8 交易日（§3） |
| index_member_all 行业归属 | 现时快照（含北交所） | 1 块 + classify L1/L2/L3 快照 | 5,902 | ~1 min | 无 out_date/多段历史（语义缺口 §4） |
| disclosure_date 披露计划 | 报告期 20181231→20260630 | 31 期 | 148,313 | ~4 min | 无 |
| daily_basic 每日市值/换手 | 交易日 2019-01-02→2026-09-09 | 1,866 日 | 8,850,300 | 两段合计 ~47 min（~46 次/min） | 无（limit/empty/failed 全 0） |

接口调用总计 ~2,200 次（tushare ~250 + daily_basic 1,866 + akshare 31+2），限流事件 0；两轮运行因后台
600s 时限被杀 1 次，断点续传无损恢复（458 块 pre_exists 跳过）。落盘共 ~1.3 GB。

## 3. 申万一级行业指数日线（`data/raw/tushare/sw_index_daily/20260909-r1/`）

- 31 个一级指数（SW2021，代码来自 `index_classify` L1 实测 31 行），文件 `chunk_<6位码>.csv`，
  列：`code, date(ISO), open, high, low, close, volume, amount`（点位/量额按源站口径原样保存，未复权概念）。
- 覆盖：28 个指数 2019-01-02→2026-08-28 各 **1,848 行**；**801960 石油石化 / 801970 环保 / 801980 美容护理
  源站序列自 2021-12-13 起**（各 1,136 行，更早无发布）；801950 煤炭 1,851 行（源站缺日比别家少 3 个）。
- **日期连续性抽查（801010 农林牧渔 / 801780 银行，与 SSE 交易日历对账）**：无重复、无日历外日期、close 无空值；
  全 31 文件缺口集合一致（除上述 3 晚发与煤炭）。窗口内缺口共 **10 个交易日**，已回源核验为 **swsresearch 源站本身缺行**：
  `2021-08-06, 2021-10-08, 2021-10-22, 2022-03-03, 2022-03-23, 2022-03-31, 2022-04-14, 2022-05-05, 2022-05-09, 2023-09-08`
  （下载非缺陷；下游可前值/剔除处理）。尾部 2026-08-31→2026-09-09 共 8 个交易日源站尚未更新（滞后约 1.5 周）。
- 应用提示：序列为 SW2021 现行口径回溯，与 index_member_all 现时归属口径一致；与"2019–2020 申万行业归属"搭配时的
  时点映射限制见 §4。

## 4. index_member_all 行业归属（`data/raw/tushare/index_member_all/20260909-r1/`）

- `chunk_all.csv`：**5,902 行、11 列** `l1_code/l1_name/l2_code/l2_name/l3_code/l3_name/ts_code/name/in_date/out_date/is_new`；
  每股一行，ts_code 无重复；**含北交所 349 只**；`out_date` 全空、`is_new` 全 'Y'；`in_date` 范围 1989-11-01→2026-09-03。
- L1 行业数 31，个股最多前 3：机械设备 628 / 医药生物 528 / 电子 528。
- 另有 `classify_L1/L2/L3_SW2021.csv` 分类体系快照（31/134/346 行，含 industry_code/is_pub/parent_code）。
- **语义缺口（必须向主对话/预登记方明示）**：本接口=**现时点归属快照（每股单行归属段）**，不是每股多段的历史时间线；
  发生过行业切换的股票只保留"当前段"的 `in_date`（=进入现行业日期），旧段无任何记录；无 `out_date` 段、
  退市/剔除股不在表内。因此 **2020–2023 筛选窗的逐日时点行业归属不可由此接口单独重建**——行业切换股在切换前的
  行业归属缺失，与预登记"index_member_all 优先"的预期不符。备选仍为 `stock_basic.industry`（现时近似，同级别缺口），
  或需另找含多段行业进出历史的源（如申万宏源官网成分调整公告）。该结论已写入 manifest `notes`。

## 5. disclosure_date 财报披露计划（`data/raw/tushare/disclosure_date/20260909-r1/`）

- 报告期 20181231→20260630 逐季 **31/31 期**，`chunk_period_<报告期>.csv`；总行数 **148,313**，单期 3,624（20190331）→
  5,561（20260630）随上市公司扩容递增。
- 列：`ts_code, ann_date, end_date, pre_date, actual_date`（ann/pre/actual 均带，可做"预约披露日 vs 实际披露日"事件研究）。
- 无 0 行/失败/空期。工程备注：首轮运行曾因季码生成 bug（Q2/Q3 误为 `0631/0931`）空拉 16 期，修复为 `0630/0930`
  后补拉完成；manifest notes 已清掉首轮误导记录并留更正说明。

## 6. daily_basic 每日市值/换手（`data/raw/tushare/daily_basic/20260909-r1/`）

- 交易日 2019-01-02→2026-09-09 **1,866/1,866 日**，`chunk_<YYYYMMDD>.csv`，**总行数 8,850,300**，1.27 GB；
  limit/empty/failed 全 0，限流事件 0。
- 列（18，默认全字段）：`ts_code, trade_date, close, turnover_rate, turnover_rate_f, volume_ratio, pe, pe_ttm,
  pb, ps, ps_ttm, dv_ratio, dv_ttm, total_share, float_share, free_share, total_mv, circ_mv`（tushare 惯例：股数单位万股、
  市值单位万元）。
- **两日行数抽查**：`chunk_20260630.csv` rows=5,508 / ts_code 去重 5,508；`chunk_20260909.csv` rows=5,550 / 去重 5,550（无重复码）。
- 行数单调演进合理：2019-01-02 3,555 → 2021 中 4,100+ → 2024 中 5,300+ → 2026-09 5,550。

## 7. 合规与工程备注

- token 纪律：全程未出现 token 读写/打印；脚本内无任何凭据。
- 批次目录只增不覆盖：新数据集均新建 `20260909-r1/`，未触碰 top_list/express/margin_detail/forecast/fund_basic 既有文件。
- 并发：tushare 侧 2–3 workers + ≥0.6s 节律 + 限流退避/降速（与 top_list 并行脚本同款实现）；akshare 串行（外部站点无 SLA）。
- 断点续传：daily_basic 被 600s 后台时限中断一次，重启后 458 块跳过、其余续拉，结果与整段运行一致（无重复/无缺）。
- 每数据集 `manifest.json` 记录创建时间、每块行数/日期/完成时间、summary、notes（含探测与语义结论）、failed/skipped。
- 运行日志：`data/raw/tushare/<dataset>/fetch_20260909-r1.log`（三份）。
- 遗留提示：① 申万指数尾部 8 个交易日待源站更新后补拉（源站滞后所致，非本仓缺口）；② 时点行业映射的多段历史缺口
  需主对话裁决替代方案（§4）。
