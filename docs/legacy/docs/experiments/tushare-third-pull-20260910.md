# tushare 第三批拉取与主对话抽审（2026-09-10）

批次：`20260909-r3`（拉取器 `experiments/tushare_fetch_r3.py`，2026-09-09 23:15 → 2026-09-10 02:53，bounded concurrency）。
范围：stock_basic、财务四接口（balancesheet/income/cashflow/fina_indicator，逐股全历史）、top_inst、dividend、repurchase、share_float、stk_holdertrade。
forecast/express 为 r1 旧批（本批未动）。`events/` 目录为空壳，事件族数据落在各自顶层目录。

## 一、主对话抽审结果（全量流式复算，非抽样）

### 财务四接口

| 接口 | chunk 数 | 行数（=manifest） | 股票数 | 期间覆盖 | ann_date 覆盖 |
|---|---|---|---|---|---|
| balancesheet | 5,899 | 408,781 | 5,894 | 1990-12-31 → 2026-06-30 | 100% |
| income | 5,899 | 421,679 | 5,895 | 1990-12-31 → 2026-06-30 | 100% |
| cashflow | 5,899 | 396,385 | 5,881 | 2001-12-31 → 2026-06-30 | 100% |
| fina_indicator | 5,899 | 458,575 | 5,896 | 1990-12-31 → 2026-06-30 | 100%（无 f_ann_date/report_type 列） |

- 行数与 manifest 逐块一致，无截断；report_type 全部为 1（合并报表）。
- comp_type（行业类型）：一般企业 ~98.5%，银行/保险/证券合计 ~1.2%（构造时如遇分行业会计口径差异须在 ⑤ 预登记中显式处理或排除金融股，TBD ⑤ 预登记定夺）。
- cashflow 起点晚于其余三表（2001-12-31），tushare 源边界，如实披露。

### 对账与一致性

- **茅台 2023 年报逐字段对账**（income 600519.SH，ann 2024-04-03）：营业总收入 1505.60 亿、营业收入 1476.94 亿、净利润（含少数股东）775.21 亿（归母 747.34 亿+少数股东 ≈27.9 亿，n_income 口径为合并净利润）；fina_indicator eps 59.49、加权 roe 36.1755 —— 与公告一致。
- **披露时效**：年报首披滞后中位 113 天、p90 120 天（与 4 月 30 日法定期限吻合）；2026 中报（期末 2026-06-30）覆盖 5,683 只、2026 一季报 5,588 只（拉取时点 2026-09-09，应披尽披）。

### 数据质量裁定（⑤ 财务家族预登记必须冻结的取数契约）

1. **update_flag 不可作为披露次序依据**：年报行 update_flag 分布逐年异常（2023 年报 flag0 仅 508 行 vs flag1 5,741 行），且 flag=1 组的最早 ann_date **早于** flag=0 组（2023：2024-01-27 < 2024-02-23）——flag 是 tushare 库记录版本号。**PIT 契约：同 (ts_code, end_date) 取 ann_date 最早的行**；更晚 ann_date 的同期末行仅作重述感知，不入因子值。income/balancesheet/cashflow 的 f_ann_date 亦同理不作首披依据。
2. **ann_date < end_date 的违规行**：仅 3 行（920185.BJ 2012 三季报 2 行 + 603400.SH 2026 中报 1 行空指标行）。契约：ann_date < end_date 的行直接剔除（fail-closed）。
3. **fina_indicator 同 (ts_code, end_date, ann_date) 多行**：多出的 194,479 行中 45,158 组非空字段集不同（分次填充形态），且**重叠字段取值冲突真实存在**（roe 2,233 组、netprofit_margin 976、debt_to_assets 860、eps 535、gross_margin 482、or_yoy 617）。契约：⑤ 构造使用 fina_indicator 任一字段时，同键组内该字段非空值必须唯一，否则该 (股票, 期末) 的该字段 fail-closed 缺失（禁 first-non-null 类非确定性合并）。
4. **income/balancesheet/cashflow 重复键**：加入 update_flag 后重复余量仅 339（balancesheet，跨 flag 的真重复），分析侧按 (ts_code, end_date, ann_date, update_flag) 去重后使用。
5. **金融股与北交所**：comp_type 2/3/4/7 合计 ~1.2% 留待 ⑤ 预登记决定排除与否；920185.BJ 等北交所代码在库，但 P1 时点池（价格资格）本就排除北交所，因子截面不受影响。

### 空块缺口（已补拉闭合）

实测空块 = 30 个 (接口, 代码) 组合、25 只代码（10 只在市股缺口 + 退市无电子记录）。原拉取器把 0 行块视为已完成，属空响应未复核缺口。
处置：新批次 `20260910-r1`（`experiments/tushare_stmt_completion_r1.py`，独立脚本不触碰 r3 批次；空响应冷却复核≥3 次，仍空记 `confirmed_empty_after_retry`；单测 8 项 OK）。

| 接口 | 补到块/行 | 确认空（全退市） |
|---|---|---|
| balancesheet | 3 / 241 | 2（600631.SH、T600018.SH） |
| income | 2 / 233 | 2（600631.SH、T600018.SH） |
| cashflow | 7 / 388 | 11（000412/000508/000542/000618/000763/000817/600631/600632/600772/600899/T600018.SH） |
| fina_indicator | 2 / 143 | 1（T600018.SH） |
| **合计** | **14 / 1,005** | **16** |

- 14 只在市股缺口全部补到（华侨城A 财务指标 100 行、期间 2012Q3→2026H1）；16 个确认空组合全部为退市股，tushare 无电子化记录，主对话复验 r3 仍为 5/4/18/3 个 0 字节块未被触碰。
- 分析侧读取顺序：r3 为主体，r1 非空 chunk 覆盖同 (接口, 代码) 的 r3 空块；confirmed_empty 清单即最终覆盖边界。

### 其余三批（快速清点）

- top_inst r3：1,866 个按日文件、1,785,667 行、0 空文件（net_buy 字段语义已在引擎接线轮核实）。
- dividend r3：2,109 个按除息日文件、35,940 行、462 个空日期文件（多数为该日无分红，空日复核机制见拉取器 note）。
- repurchase/share_float/stk_holdertrade r3：各 129 个文件（按月）。

## 二、结论

第三批主线数据前提成立：行数完整、PIT 字段 100%、对账通过、时效合理、在市股缺口已补拉闭合（14 块 1,005 行，退市确认空 16 组合即最终边界）；四条取数契约（最早披露、ann<end 剔除、fina_indicator 字段冲突 fail-closed、跨 flag 去重）须原文写入 ⑤ 财务家族预登记并在实现中强制。
