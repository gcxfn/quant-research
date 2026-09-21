# tushare 首批非价量数据拉取（batch 20260909-r1）

日期：2026-09-09 · 脚本：`experiments/tushare_fetch.py` · 数据根目录：`data/raw/tushare/<dataset>/20260909-r1/`

目的：为事件驱动短线研究（业绩预告漂移等）补齐非价量数据（公告日期字段 + 龙虎榜 + 两融明细 + 清盘 ETF 名单）。
本批为 tushare pro 首次拉取；token 读取自用户目录 `~/.tushare/token.csv`，**未写入仓库任何文件、未打印到任何落盘文件**。

## 1. 接口权限与形态探测（第0步）

逐接口最小试探（2026-09-09 实测，均 OK）：

| 接口 | 用途 | 权限 | 单次行数上限(实测) | 是否含公告日期字段 | 可用查询键 |
|---|---|---|---|---|---|
| `forecast` | 业绩预告 | OK | 未知(单日行数远未触顶；请求上限6000) | `ann_date`, `first_ann_date` | **仅 `ann_date` 逐日**（`period` 单独传报参数错误；无范围查询） |
| `express` | 业绩快报 | OK | **2000 行/次** | `ann_date` | `period`（报告期，支持 offset 分页） |
| `top_list` | 龙虎榜 | OK | 未知(单日~65–150行) | 无（`trade_date` 即行情日） | **仅 `trade_date`**（start/end 报"参数错误"） |
| `margin_detail` | 两融明细 | OK | **6000 行/次**（limit=20000 仍只回 6000） | 无（`trade_date` 为交易日） | `trade_date` 单日；或 start/end 范围（倒序+offset 分页，**限流/异常时静默返回空页，有截断风险**，最终弃用） |
| `fund_basic` | 基金基本资料 | OK | 一次可全量(场内2945行) | 无（有 `list_date`/`delist_date`/`status`） | `market`（'E'场内 / 不传=全市场），**默认已含退市/清盘（status=D）**，无 `list_status` 参数 |
| `income` | 利润表 | OK | 单票单期1行 | `ann_date`, `f_ann_date` | 仅探权限，本次不下载 |
| `trade_cal` | 交易日历 | OK | 一次全量 | — | 辅助：top_list/margin_detail 需交易日清单 |

关键形态结论（与任务预估的差异，全部写入 manifest / 本档）：

1. `forecast` 与 `top_list` 接口**不接受日期范围/报告期参数**，只能逐日查询 → 任务原按"报告期逐季/按月分块"的调用预算（~250 次）不成立，改为逐日拉取（forecast 按自然日约 2,930 天，top_list 按交易日约 1,880 天）。
2. `forecast` 在**周末/节假日也有公告**（2019-12 实测 12-21/12-28 两个周六均有行）→ 必须按自然日迭代，不能只用交易日。
3. `express` 单次行数上限 2000 → 每报告期 offset 分页。
4. `margin_detail` 按月范围+offset 分页在 2026-09-09 实测中会**间歇性静默返回空帧**（同一月份多次重试结果不一致；与调用节奏无关，疑似服务端/代理层不稳定——7 次/min 的慢速窗口甚至比 20 次/min 空帧更多），会把整月误判为 0 行或截断；且单日查询比范围查询快（约 2s vs 3–7s）。最终方案：**逐交易日拉取 + 空帧退避重试**，分块=单日，天然断点续传。运行中空帧出现频率低（1,866 日中仅今日 1 个缺口），方案有效。
5. `fund_basic` 默认 `market='E'` 已含退市基金（status=D 677 只），不需要 `list_status`；核心目标"带 delist_date 的清盘 ETF 名单"直接可得。
6. `top_list` 存在服务端整行重复（两融类上榜理由，154 个交易日、471 行），去重口径 141,514 行。

## 2. 落盘结构

```
data/raw/tushare/
├── fetch_20260909-r1.log                     # 运行日志
├── trade_cal/20260909-r1/chunk_sse_20180101_20261231.csv
├── express/20260909-r1/     chunk_period_<YYYYMMDD>.csv × 31 + manifest.json
├── fund_basic/20260909-r1/  chunk_market_E.csv / chunk_market_all.csv + manifest.json
├── margin_detail/20260909-r1/ chunk_<YYYYMMDD>.csv × 1866(交易日) + manifest.json   # 0字节=当日缺口
├── forecast/20260909-r1/     chunk_<YYYYMM>.csv × 97(自然月) + manifest.json
└── top_list/20260909-r1/     chunk_<YYYYMMDD>.csv × 1866(交易日) + manifest.json
```

每个 dataset 一个 `manifest.json`：接口名、参数与范围、计划块数/已完成块数、每块行数与完成时间、失败与跳过记录、注意事项。
写入原子性：CSV 先写 `.tmp` 再 `os.replace`；0 行/缺口也落 0 字节标记文件避免重复请求。
纪律：串行调用、两次调用间隔 ≥0.4s、失败退避重试（5/15/30s × 最多3次，空帧另加 5/10/20/40s 重试）、断点续传（文件存在即跳过）、只新增不覆盖。

## 3. 下载结果

五个数据集全部完成（batch `20260909-r1`，见 `data/raw/tushare/<dataset>/20260909-r1/` 及各自 manifest.json）：

| 数据集 | 范围 | 分块 | 行数 | 用时 | 缺口/失败 |
|---|---|---|---|---|---|
| express 业绩快报 | 报告期 20181231→20260630 | 31 期 | 8,488 | ~4.4 min | 无（若干报告期 0 行属正常） |
| fund_basic 基金资料 | 全量快照 | market_E + market_all | 35,691 | ~1 min | 无 |
| margin_detail 两融明细 | 交易日 2019-01-01→2026-09-09 | 1,866 日 | 5,474,653 | ~69 min | 仅 2026-09-09（当日未发布） |
| forecast 业绩预告 | 公告日 2018-09-01→2026-09-09 | 97 月 | 50,406 | ~92 min | 无 |
| top_list 龙虎榜 | 交易日 2019-01-01→2026-09-09 | 1,866 日 | 141,985（去重后 141,514） | ~28 min | 仅 2026-09-09；471 行服务端整行重复(见 §4) |

合计约 5,711,223 行（top_list 去重口径 5,710,966）。接口层面总调用约 8,000+ 次（forecast 逐自然日约 2,950、margin/top_list 各约 1,900、express ~65、fund_basic ~9），全部串行、带节律与退避；token 未入仓库/未落盘。

### express（业绩快报，已完成）

- 报告期范围：20181231 → 20260630 逐季（31 期）。
- 行数合计：**8,488 行**；分块 31/31，无失败，跨页重复 0。
- `ann_date` 非空率：**100%**；`ann_date` 覆盖 2019-01-04 → 2026-08-25。
- 若干报告期为 0 行属正常（Q1 快报极少，如 20190331/20200331/20211231/20221231/20241231/20251231、20200930、20250331 等）。
- 字段（15）：`ts_code, ann_date, end_date, revenue, operate_profit, total_profit, n_income, total_assets, total_hldr_eqy_exc_min_int, diluted_eps, diluted_roe, yoy_net_profit, bps, perf_summary, update_flag`。
- 同 (ts_code, end_date) 重复 5 条 = 快报修正（update_flag=1 共 1 条），非错误。
- 落盘：`data/raw/tushare/express/20260909-r1/`，用时约 4.4 分钟（~65 次调用）。

### fund_basic（基金基本资料，已完成）

- 场内 `market='E'`：2,945 只，其中 **status=L 2,207 / status=D(退市/清盘) 677**；`delist_date` 非空 626。
- **清盘 ETF（名称含 ETF 且 delist_date 非空）：128 只**（全部 status=D）；名称含 ETF 共 1,873 只。
- 全市场（不传 market）：32,746 只（场内 E 2,945 + 场外 O 29,801）。
- 字段（25）：`ts_code, name, management, custodian, fund_type, found_date, due_date, list_date, issue_date, delist_date, issue_amount, m_fee, c_fee, duration_year, p_value, min_amount, exp_return, benchmark, status, invest_type, type, trustee, purc_startdate, redm_startdate, market`。
- 落盘：`data/raw/tushare/fund_basic/20260909-r1/`，用时约 1 分钟。
- 说明：基金无 `list_status` 列/参数，退市识别用 `status='D'` 或 `delist_date` 非空；两者差异 51 条（D 但 delist_date 空）见抽查备注。

### margin_detail / forecast / top_list（margin_detail 已完成；forecast/top_list 执行中/待执行）

#### margin_detail（融资融券明细，已完成）

- 查询方式：**逐交易日 `trade_date` 单日拉取**（放弃"按月范围+offset 分页"——该方式在限流/服务端异常时静默返回空页，会把整月误判为 0 行或截断，2026-09-09 实测已废弃）。
- 范围：2019-01-01 → 2026-09-09，按 SSE 交易日历共 **1,866 个交易日**，落盘 1,866 个日块（`chunk_<YYYYMMDD>.csv`），覆盖无缺失。
- 行数合计：**5,474,653 行**；跨日重复 0。单日行数随两融标的扩围从约 1,000(2019) 增长到约 4,300(2025)。
- 逐年行数：2019=309,221；2020=447,172；2021=532,783；2022=650,055；2023=861,439；2024=943,581；2025=1,006,059；2026(至9/9)=724,343。
- 缺口：仅 **2026-09-09（当日，两融数据尚未发布）** 为 0 字节标记（manifest.failed 记录）；此前探测中"2019-01-02 无数据"亦为接口间歇空帧，本次逐日拉取该日有数据（早期"缺口"结论作废）。
- 字段（10）：`trade_date, ts_code, rzye, rqye, rzmre, rqyl, rzche, rqchl, rqmcl, rzrqye`。
- 用时：约 69 分钟（~1,900 次调用，串行；接口偶发空帧，5/10/20/40s 退避重试命中若干次，最终仅当日 1 个缺口）。
- 落盘：`data/raw/tushare/margin_detail/20260909-r1/`。

#### forecast（业绩预告，已完成）

- 查询方式：**逐自然日 `ann_date`**（周末/节假日亦有公告，实测 2019-12-21/28 周六有行，不能只用交易日）。
- 范围：公告日 2018-09-01 → 2026-09-09，共 **97 个自然月块**（2018-09 … 2026-09），全部完成。
- 行数合计：**50,406 行**；`ann_date` 非空 **100%**；公告日覆盖 2018-09-03 → 2026-09-04；行重复 0。
- 报告期：`end_date` 落在目标季末集合 [20181231..20260630] 内 49,264 行（97.7%）；其余 1,142 行为相邻报告期（2018Q3 等在公告窗内的预告、及个别远期预告），原始数据未裁剪，下游可按 `end_date` 过滤。
- 字段（13）：`ts_code, ann_date, end_date, type, p_change_min, p_change_max, net_profit_min, net_profit_max, last_parent_net, first_ann_date, summary, change_reason, update_flag`。
- 用时：约 92 分钟（~2,950 次调用）。
- 落盘：`data/raw/tushare/forecast/20260909-r1/`。

#### top_list（龙虎榜，已完成）

- 查询方式：**逐交易日 `trade_date`**（接口不接受日期范围）。
- 范围：2019-01-01 → 2026-09-09，按 SSE 交易日历 **1,866 个交易日**，1,866 个日块，覆盖无缺失。
- 行数合计：**141,985 行**（含重复）；`trade_date` 范围 2019-01-02 → 2026-09-08。平均约 76 行/日。
- 重复：471 行（237 组）为**服务端返回的整行重复**，集中在"两融类上榜理由"（如"单只标的证券的当日融资买入数量达到当日该证券总交易量的50％以上"），出现在 154 个交易日，单日最多 8 条额外重复；原始文件不裁剪，下游按全行/`(trade_date, ts_code, reason)` 去重即可（去重后 141,514 行）。
- 字段（15）：`trade_date, ts_code, name, close, pct_change, turnover_rate, amount, l_sell, l_buy, l_amount, net_amount, net_rate, amount_rate, float_values, reason`。
- 缺口：仅 2026-09-09（当日，榜单尚未发布）。
- 用时：约 28 分钟（~1,870 次调用）。
- 落盘：`data/raw/tushare/top_list/20260909-r1/`。

## 4. 抽查核验

- **express**：31/31 报告期分块完整；`ann_date` 非空 100%；行重复 0；ann_date 覆盖 2019-01-04→2026-08-25；部分 Q1/Q4 报告期 0 行属正常（无快报）。
- **fund_basic**：场内 2,945 只含 status=D 677 只；清盘 ETF（名称含 ETF + delist_date 非空）128 只；全市场 E+O=32,746。manifest 与文件行数一致。
- **margin_detail**：1,866/1,866 交易日全覆盖（对照 SSE trade_cal，缺失 0）；逐文件无跨日重复；`trade_date` 非空 100%；唯一 0 字节缺口 = 2026-09-09（当日数据未发布）。
- **forecast**：97/97 月块完整；`ann_date` 非空 100%、行重复 0；公告日覆盖 2018-09-03→2026-09-04；97.7% 行报告期落在 [20181231..20260630]。
- **top_list**：1,866/1,866 交易日全覆盖（对照 SSE trade_cal，缺失 0）；整行重复 471 行（237 组、154 个交易日，两融类上榜理由的服务端重复），去重后 141,514 行；唯一 0 字节缺口 = 2026-09-09。
- manifest 与文件实际行数一致（express/fund_basic/margin_detail/forecast/top_list 均已核对）。

## 5. 已知缺口与注意事项

- `margin_detail` 服务端间歇性空帧（与调用节奏无关）→ 逐日+重试方案已缓解；唯一缺口为 2026-09-09（当日数据未发布，manifest.failed 记录）。
- tushare 两融/龙虎榜历史口径：`margin_detail` 单日行数约 1,000(2019) → 4,300(2025)（随两融标的扩围增长）。
- 原预估 ~250 次调用/30–60 分钟不适用：接口查询形态与文档假设不同（见 §1），实际调用量约为预估的 10 倍以上。
- 本批按任务要求全程串行（间隔≥0.4s）。执行期间 AGENTS.md 更新了 tushare 规则（D-2026-09-09-10）：允许 2—4 workers + 共享速率预算（先探测积分档位压下限）。后续补拉/增量可依新规则提速，本批结果不受影响。
- 本批为一次性研究取数，未纳入任何离线单测；未 git commit。

## 6. 复现/续跑

```bash
python experiments/tushare_fetch.py --dataset express|fund_basic|margin_detail|forecast|top_list|all
```

按块文件存在与否自动续传；同一 batch 目录只新增不覆盖，历史批次目录保持原样。
