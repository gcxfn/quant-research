# exp-20260917-event-data-scout：事件类数据批次预研清点

- 性质：预研清点（scout）。只读盘点，不计算任何因子、不跑回测，不构成任何盈利结论。
- 运行记录：`artifacts/runs/20260917T231747-event-scout-f2d1ea/`（脚本 `event_scout_scan.py`、全量统计 `scan_results.json`、控制台日志、manifest）。
- 数据边界：`data/raw/` 只读；冻结边界 **2024-12-31**（>该日仅统计，不删除不修改）；目标研究窗口 2015–2024。
- 标的池参照：`data/raw/baostock/daily/`（5,552 只，仅 sh/sz；ts_code 映射 `600000.SH <-> sh.600000`）。北交所按账户规则排除，各批次 .BJ 标的仅统计。

## 0. 一页结论

| 批次 | 行数 | 可得日范围 | PIT 公告日缺失 | 窗口内行数(≤2024) | 冻结区(>2024) | 自由文本量级 | LLM 需求 |
|---|---:|---|---:|---:|---:|---|---|
| forecast 业绩预告 | 50,406 | 20180903–20260904 | **0%** | 40,079 | 10,327 | ~1,140 万字符（change_reason 为主） | 高（仅 change_reason） |
| express 业绩快报 | 8,488 | 20190104–20260825 | **0%** | 8,314 | 174 | 0（perf_summary 全空） | 无 |
| repurchase 回购 | 61,718 | 20160104–20260909 | **0%** | 49,093 | 12,625 | 枚举（proc，2.5 字符） | 无 |
| share_float 解禁 | 5,661,143 | 20160101–20260909 | **0%** | 4,207,790 | 1,453,353 | 半结构（holder_name 29.6 字符） | 无 |
| stk_holdertrade 增减持 | 149,108 | 20160101–20260909 | **0%** | 127,752 | 21,356 | holder_name 10.2 字符（名称型） | 无 |
| top_list 龙虎榜 | 141,985 | 20190102–20260908 | **0%**（trade_date） | 110,162 | 31,823 | reason 22.8 字符（封闭词表） | 无（字典映射） |
| top_inst 龙虎榜机构 | 1,785,667 | 20190102–20260909 | **0%**（trade_date） | 1,444,273 | 341,394 | exalter+reason ~3,300 万字符（封闭词表+营业部名） | 无 |
| margin_detail 两融 | 5,474,653 | 20190102–20260908 | **0%**（trade_date） | 3,744,251 | 1,730,402 | 无文本 | 无 |
| disclosure_date 披露计划 | 148,313 | 20181227–20260827 | **0%** | 114,451 | 33,862 | 无文本 | 无 |
| index_member_all 行业归属 | 6,413 | in_date 19891101– | in_date 8.0% 缺（快照文件无此列） | 快照型 | 334 | 行业名（枚举） | 无 |
| events | **0** | – | – | 0 | 0 | – | – |

核心发现：
1. **全部 9 个含日期批次的 ann_date / trade_date 实测缺失率为 0%**。事件方向的主要 PIT 风险不在"公告日缺失"，而在**发布滞后语义**（龙虎榜 T 日晚间公布、两融 T+1 早晨公布、增减持为事后公告）与**覆盖窗口普遍晚于 2015 年**。
2. `events/` 是空壳目录（仅 fetch 日志）。旧库三拉文档明确："`events/` 目录为空壳，事件族数据落在各自顶层目录"——日志中"3 数据集 × 129 月"即 repurchase / share_float / stk_holdertrade（各 129 个月块，数目吻合）。
3. 最有价值批次：**forecast**（方向、幅度、修正链俱全，公告日可知性强）与 **share_float**（公告先行、解禁日未来可知，566 万行可聚合为干净事件面）。理由见 §4。

## 1. 逐批次清点

主键为"候选主键"（本次未做全量唯一性断言；fetch 侧 manifest 记录了 repurchase/holdertrade 拉取时去重 1–8 行/月的动作）。"窗口内"指可得日 ≤2024-12-31。

### 1.1 forecast 业绩预告（forecast/20260909-r1，97 个月块）

- 行数 50,406；ann_date 20180903–20260904，**缺失 0**；end_date（报告期）20180930–20271231。
- schema（13 列）：`ts_code, ann_date, end_date, type, p_change_min, p_change_max, net_profit_min, net_profit_max, last_parent_net, first_ann_date, summary, change_reason, update_flag`。
- 主键候选：`(ts_code, end_date, ann_date, update_flag)`——update_flag=1（修正预告）占 15,962（31.7%），同报告期多版本必须按 first_ann_date→ann_date 链处理。
- PIT 核验：ann_date 缺失 0%。ann−end 中位 +15 天、p10 −38 天，**16.8% 的行 ann_date < end_date**——深市年报预告（扭亏/首亏/续亏）可在报告期结束前（10 月）披露，属合法现象；只要以 ann_date 为可得日即无未来函数。ann_date−first_ann_date 中位 0（93.8% ≤0，即 ann_date≥first_ann_date，存在少量首披晚于记录情形）。
- 冻结区：ann>20241231 共 10,327 行。
- 文本：`type` 为封闭枚举（预增 14,244/首亏 6,987/续亏 7,413/预减 6,445/略增 5,478/扭亏 5,195/略减 2,577/续盈 986…，平均 2 字符）；`summary` 平均 17.1 字符；`change_reason` 平均 **217.2 字符、最长 1,870**，非空 48,582（96.4%）——全批约 1,055 万 + 86 万 ≈ 1,140 万字符，是唯一真正需要 LLM 结构化的文本面。
- 标的：5,754 只，其中 baostock 池内 5,341，.BJ 394（映射时剔除）。
- 抽样（202001 块，截断）：`300146.SZ, 20200101, 20191231, 首亏, -136.92/-136.42, summary="预计净利润-37000~-36500万", change_reason="报告期内，公司对2019年度相关经营情况进行了全面评估…"`；`600519.SH, 20200102, 20191231, 略增, 15/15, update_flag=1`。

### 1.2 express 业绩快报（express/20260909-r1，31 个报告期块，7 个空文件）

- 行数 8,488；ann_date 20190104–20260825，**缺失 0**；end_date 20181231–20260630。空块集中在部分 Q1/Q3（快报以年报/中报为主，属正常；20211231 等年报期也有 0 行空块，属上游无数据，非拉取失败）。
- schema（15 列）：`ts_code, ann_date, end_date, revenue, operate_profit, total_profit, n_income, total_assets, total_hldr_eqy_exc_min_int, diluted_eps, diluted_roe, yoy_net_profit, bps, perf_summary, update_flag`。
- 主键候选：`(ts_code, end_date, ann_date)`。
- PIT 核验：ann−end 中位 **+58 天**（p10 +22 / p90 +101），0% 早于报告期——快报必然在期末后，可得日=ann_date 即可；对比财报 90 天纪律，快报提供更早的基本面确认点。
- 冻结区：174 行。
- 文本：`perf_summary` **全空**（0 非空）——该批次完全结构化，无需 LLM。
- 标的：3,741 只，池内 3,254，.BJ 486。
- 抽样（20200630 块）：`000028.SZ, 20200818, 20200630, revenue=271.70 亿, diluted_eps=1.5, yoy_net_profit=6.49 亿, perf_summary=null`。

### 1.3 repurchase 回购（repurchase/20260909-r3，129 个月块）

- 行数 61,718；ann_date 20160104–20260909，**缺失 0**；exp_date（计划到期）20160618–20270917，部分为空（如"完成"进度行）。样本中出现无后缀老三板码 `400145`——映射时按非标准码剔除并记录。
- schema（9 列）：`ts_code, ann_date, end_date, proc, exp_date, vol, amount, high_limit, low_limit`。
- 主键候选：`(ts_code, ann_date, proc)`（同日多进度行存在）。
- PIT 核验：ann−exp_date 中位 −364 天（公告远早于计划到期，99.98% 公告先行）——回购事件以 ann_date 首次出现（proc=预案）为可知起点，后续 proc 状态推进是**逐行覆盖式披露**，研究须按"首次预案日"对齐，禁用后视状态。
- 冻结区：12,625 行（exp_date 冻结 2,209）。
- 文本：`proc` 封闭枚举：完成 37,106 / 预案 15,482 / 股东大会通过 7,296 / 实施 1,803 / 停止 31。无需 LLM。
- 标的：3,706 只，池内 3,463，.BJ 142。
- 抽样（202001 块）：`300199.SZ, 20200101, proc=完成, vol=3,368.57 万股, amount=3.19 亿, high_limit=16.0`。

### 1.4 share_float 限售解禁（share_float/20260909-r3，129 个月块）

- 行数 **5,661,143**（本次最大）；ann_date 20160101–20260909，**缺失 0**；float_date 20151124–20340120（含未来解禁计划——公告先行所致，属正常）。
- schema（7 列）：`ts_code, ann_date, float_date, float_share, float_ratio, holder_name, share_type`。
- 主键候选：`(ts_code, float_date, holder_name, ann_date)`；研究面应聚合到 `(ts_code, float_date, share_type)`（首发战略配售 544.9 万行占 96%，按持有人逐行展开）。
- PIT 核验（本批次最有价值属性）：**ann−float_date 中位 −7 天（p10 −186 / p90 −2），99.999% 公告早于解禁日**——解禁事件在发生前即可知，是天然可前视规划的事件族；"公告日对齐"与"解禁日对齐"是两个不同研究面。
- 冻结区：ann>20241231 共 1,453,353；float_date>20241231 共 1,622,054（其中 2025–2026 的解禁在 2024 前已公告的部分可用作"已知未来计划"型特征，但不得用于 2025+ 窗口的收益标签）。
- 文本：`holder_name` 平均 29.6 字符（人名/机构名，非自由语义文本）；`share_type` 封闭枚举（首发战略配售股份 5,449,063 / 首发原始股 108,085 / 股权激励限售流通 39,414 / 定增股份 54,710 / 公开增发 3,686 / 其他 5,382 / 股改限售 803）。无需 LLM。
- 标的：5,054 只，池内 4,580，.BJ 343。
- 抽样（202001 块）：`300684.SZ, ann=20200101, float_date=20200106, float_ratio=0.4764%, holder="中层核心骨干(46人)", 股权激励限售流通`。

### 1.5 stk_holdertrade 股东增减持（stk_holdertrade/20260909-r3，129 个月块）

- 行数 149,108；ann_date 20160101–20260909，**缺失 0**。本拉取未含 begin_date/close_date（交易发生区间），只有公告日。
- schema（11 列）：`ts_code, ann_date, holder_name, holder_type, in_de, change_vol, change_ratio, after_share, after_ratio, avg_price, total_share`。
- 主键候选：`(ts_code, ann_date, holder_name, in_de, change_vol)`。
- PIT 核验：增减持是**事后公告**（行为发生日不在字段中），可得日只能取 ann_date；若要估计行为日，需要保守回溯假设并记录（见 §5 风险）。in_de：DE 115,108 / IN 34,000；holder_type：C(公司) 77,754 / G(高管) 41,169 / P(个人) 30,185。
- 冻结区：21,356 行。
- 文本：`holder_name` 平均 10.2 字符（名称，最长 170，含"一致行动人"等表述）；其余为编码字段。LLM 仅在需要"持有人身份归类"时有用，默认不需要。
- 标的：5,354 只，池内 4,932，.BJ 422。
- 抽样（202001 块）：`002065.SZ, 20200101, 览海医疗产业投资股份有限公司, C, DE, change_ratio=0.3291%, after_ratio=0.0281%`。

### 1.6 top_list 龙虎榜个股（top_list/20260909-r1，1,866 个日块，1 空文件）

- 行数 141,985；trade_date 20190102–20260908，**缺失 0**。
- schema（15 列）：`trade_date, ts_code, name, close, pct_change, turnover_rate, amount, l_sell, l_buy, l_amount, net_amount, net_rate, amount_rate, float_values, reason`。
- 主键候选：`(trade_date, ts_code, reason)`（同股同日多上榜原因并存）。
- PIT 核验：龙虎榜于 T 日**收盘后晚间**公布——trade_date 当日日内不可用；保守可得日=**下一交易日**。字段本身无公告日列，缺失率按 trade_date 计 0%。
- 冻结区：31,823 行。
- 文本：`reason` 平均 22.8 字符、封闭词表（"日涨幅偏离值达7%前五"6,178、"三日涨幅偏离累计20%"11,161 等），可字典映射；`name` 3.9 字符。无需 LLM。
- 标的：6,416 只，池内 5,355，.BJ 469。覆盖仅 2019 起。
- 抽样（20200102 块）：`000716.SZ, 黑芝麻, close=4.58, pct=10.10, net_amount=1,218 万, reason=日涨幅偏离值达到7%的前五只证券`。

### 1.7 top_inst 龙虎榜机构/营业部明细（top_inst/20260909-r3，1,866 个日块）

- 行数 1,785,667；trade_date 20190102–20260909，**缺失 0**。
- schema（10 列）：`trade_date, ts_code, exalter, buy, buy_rate, sell, sell_rate, net_buy, side, reason`（side: 0 卖方榜 892,259 / 1 买方榜 893,408）。注意本拉取未含营业部/机构类别 ID（busin_id），机构专属席位要靠 `exalter` 名称识别（如"机构专用"）。
- 主键候选：`(trade_date, ts_code, side, exalter)`。
- PIT：同 top_list（T 日晚间公布，可得日=次一交易日）。
- 冻结区：341,394 行。
- 文本：`exalter` 平均 18.3 字符（营业部全名）+ `reason` 19.6 字符，全批约 6,800 万字符，但均为封闭词表/名称去重问题（distinct 营业部数千、reason 数十），字典化后无需 LLM。
- 标的：6,184 只，池内 5,353，.BJ 334。
- 抽样（20200102 块）：`000018.SZ, side=0, 华福证券长沙劳动西路营业部, buy=526.5 万, net_buy=526.5 万, reason=退市整理期`。

### 1.8 margin_detail 两融明细（margin_detail/20260909-r1，1,866 个日块，1 空文件）

- 行数 5,474,653；trade_date 20190102–20260908，**缺失 0**。
- schema（10 列）：`trade_date, ts_code, rzye, rqye, rzmre, rqyl, rzche, rqchl, rqmcl, rzrqye`（融资余额/融券余额/融资买入额等，单位元）。
- 主键：`(trade_date, ts_code)`。
- PIT 核验：交易所两融余额为 **T+1 日早晨公布**——trade_date 当日不可用，保守可得日=下一交易日。按 trade_date 计缺失 0%。
- 冻结区：1,730,402 行。
- 文本：无。完全结构化。
- 标的：5,168 只，池内仅 3,790，.BJ 591——差异约 787 只为 **ETF 融资融券标的**（51/15 开头），映射股票池时须按板块前缀过滤；另两融标的池本身是时点变化集合，研究须用历史标的资格（本仓库 stk_limit/交易所名单未含此历史，属缺口）。
- 抽样（20200102 块）：`000001.SZ, rzye=34.76 亿, rzmre=2.73 亿, rzrqye=35.07 亿`。

### 1.9 disclosure_date 披露计划（disclosure_date/20260909-r1，31 个报告期块）

- 行数 148,313（报告期 20181231–20260630，约 4,700–5,000 只/期）；ann_date（计划公告日）20181227–20260827，**缺失 0**。
- schema（5 列）：`ts_code, ann_date, end_date, pre_date, actual_date`。
- 主键候选：`(ts_code, end_date, ann_date)`（同期多次计划变更产生多行）。
- PIT 核验：**pre_date（预约披露日）比计划公告日平均晚约 35 天**（ann−pre 中位 −35，分布 p10 −114 / p90 −23，即多数股票在预约日前 3 周至 3 个月已可知该计划）——财报披露时点是"提前可知"的计划信息；actual_date 与 pre_date 的偏离（延后/提前）本身构成事件。actual_date 缺失即"尚未披露"，属信息而非缺陷。
- 冻结区：ann>20241231 共 33,862；actual_date>20241231 共 38,263。
- 文本：无。
- 标的：5,814 只，池内 5,443，.BJ 354。覆盖 2019 年报期起（20181231 期）。
- 抽样（20200331 块）：`600396.SH, ann=20200330, end=20200331, pre=20200408, actual=20200408`。

### 1.10 index_member_all 行业/指数归属（index_member_all/20260909-r1，1 成员文件 + 3 分类快照）

- 行数 6,413（成员 5,902 + L1/L2/L3 分类 31/134/346）。成员行 in_date 19891101–20260903，**out_date 全空、is_new 全 Y**（fetch manifest 亦记录 out_date 非空=0）。
- schema（11 列）：`l1_code, l1_name, l2_code, l2_name, l3_code, l3_name, ts_code, name, in_date, out_date, is_new`。
- **PIT 结论：现时单点快照，不含每股行业切换历史**——无法重建 2015–2024 任一历史时点的申万归属，直接当历史行业因子用会引入幸存者/重分类偏差。分类树（SW2021）同样是现时快照。此为本批次最大局限；历史行业归属需另寻来源（xiaodefa/sw_daily、ths_daily 或 tushare index_member_all 增量快照的持续积累）。
- 标的：5,902 只（含北交所 349），池内 5,547。
- 抽样：`600679.SH, 上海凤凰, L1=汽车, L2=摩托车及其他, L3=其他运输设备, in_date=19931008, is_new=Y`。

### 1.11 events（events/ 目录）

- **无数据文件，仅 `fetch_20260909-r3.log`**。日志显示曾拉取"3 数据集 × 129 月块"并走到 384/384 完成，但目录无任何 CSV/manifest。旧库三拉审核文档明确："`events/` 目录为空壳，事件族数据落在各自顶层目录"——即 repurchase/share_float/stk_holdertrade（三批各 129 月块，与日志吻合）。结论：events 不是独立数据集，无需补拉；若未来把"事件族"重新组织目录，须按 AGENTS 以新批次命名，不得移动现有批次。

## 2. 跨批次 PIT 与时间口径汇总

| 批次 | 可得日（knowledge） | 发布滞后语义 | 事件日（event） | ann−event 中位 |
|---|---|---|---|---|
| forecast | ann_date | 公告即知 | end_date（报告期） | +15 天（16.8% 早于期末，合法） |
| express | ann_date | 公告即知 | end_date | +58 天 |
| repurchase | ann_date | 公告即知（状态推进逐行披露） | exp_date | −364 天 |
| share_float | ann_date | 公告即知 | float_date | **−7 天（99.999% 先行）** |
| stk_holdertrade | ann_date | 事后公告（行为日未知） | 无 | – |
| top_list / top_inst | trade_date + 1 交易日 | T 日晚间公布 | trade_date | 0（须 +1 修正） |
| margin_detail | trade_date + 1 交易日 | T+1 早公布 | trade_date | 0（须 +1 修正） |
| disclosure_date | ann_date | 计划公告即知 | pre_date / actual_date | −35 天（预约日可知） |

共同纪律（写入读取层契约的建议）：**收盘信号最早下一交易日执行**——所有事件可得日均应归一化为"可得日次一交易日收盘后可见"，与现有价量管线同一时间口径；无 ann_date 的行直接弃用（fail-closed，本批实测缺失 0%，该规则纯防御）。

## 3. 事件因子 schema 草案

统一事件记录（`data/features/<feature_set_id>/` 产出的上游契约，字段定义）：

| 字段 | 类型 | 定义 |
|---|---|---|
| `event_id` | str | `{event_type}.{ts_code}.{ts_event}.{seq}`，同键多行加序号；跨批次唯一 |
| `event_type` | enum | `forecast` / `express` / `repurchase_plan` / `unlock` / `holder_trade` / `dragon_top` / `margin_move` / `disclosure_shift` / `disclosure_near` |
| `ts_code` | str | tushare 代码；映射 baostock 池失败（.BJ/非标码）则标记 `in_pool=false` 并默认剔除 |
| `ts_event` | date | 事件发生日：end_date(报告期型用期末)、float_date、trade_date、actual_date |
| `ts_knowledge` | date | 最早可知日：ann_date 或 trade_date |
| `ts_available` | date | **严格可得时间戳**：ts_knowledge 的次一交易日（两融/龙虎榜天然 +1，其余按收盘信号纪律统一 +1） |
| `direction` | enum | `+1`（利多：预增/回购预案/增持…）、`-1`（预减/首亏/减持/解禁-供给压力…）、`0`（中性/无法判定） |
| `direction_source` | enum | `field_enum`（type/proc/in_de 等封闭枚举直接映射）/ `llm_struct`（change_reason 等自由文本，附 `struct_version`）/ `derived`（数值规则） |
| `confidence` | enum | `high`（官方数值+首次公告）/ `medium`(修正预告、预约变更) / `low`（文本推断、事后公告行为日不明） |
| `horizon` | enum | 预期影响周期标签：`d1_5` / `d5_20` / `d20_60`（仅作分组标签，不做参数承诺） |
| `magnitude` | float | 归一化强度：如 `p_change_min/max` 区间、`float_ratio`（占总股本比例，样本量级 %，单位口径进 features 层前复核）、`change_ratio`、`net_amount/float_values`、`rzye` 变化率 |
| `raw_text` | str? | 仅 forecast.change_reason / summary 保留原文 + `llm_struct_version`；其余批次不携带文本 |
| `source_batch` | str | 数据身份：`tushare/<dataset>/<batch>`，保证回溯到 manifest |

设计要点：direction/confidence 拆成两列（方向与可靠度独立演化）；一切时间判断只用 `ts_available`；文本推断必须带版本号，便于审计与复算。

## 4. 可行的事件窗口研究候选（只列候选与所需数据，不设计参数）

1. **业绩预告方向与公告后漂移（PEAD-预告）**。数据：forecast（type/p_change/修正链）+ 现有日线收益 + express 作交叉确认。关键点：update_flag 修正链取首披版本；type→direction 字典映射无需 LLM。
2. **解禁双日历研究：公告日反应 vs 解禁日反应**。数据：share_float（聚合到 ts_code×float_date×share_type）+ 日线 + 流通股本（daily_basic 已有）。关键点：ann_date 与 float_date 两个对齐面分开登记；share_type 分层。
3. **披露时点信号：预约变更与披露临近效应**。数据：disclosure_date（pre_date 变更序列、actual vs pre 偏离）+ 财报三表/fina_indicator（已在库）。关键点：同一 (ts_code, end_date) 多次计划变更要按 ann_date 排序成事件流。
4. **龙虎榜上榜后短期量价路径（2019+ 子窗口）**。数据：top_list + top_inst（机构席位识别、"机构专用"净买聚合）+ 日线。关键点：可得日 +1；只覆盖 2019–2024，结论不得外推到 2015–2018。
5. **股东增减持公告反应**。数据：stk_holdertrade（in_de/holder_type/change_ratio）+ 日线。关键点：行为日缺失，默认以 ann_date 为事件日并标记 confidence=medium；与解禁/回购事件重叠样本的去重规则需预登记。

辅助面（非独立候选）：margin_detail 两融余额异动可作为 4/5 的状态变量（可得日 +1；标的资格历史缺失是先决缺口）。

## 5. 缺口与风险

1. **覆盖窗口普遍晚于 2015**：forecast 2018-09+、express/disclosure_date 2019 年报期+、top_list/top_inst/margin_detail 2019+、repurchase/share_float/holdertrade 2016+。跨事件族的统一比较最长只有 **2019–2024**；2015–2018 仅有三个 2016 起批次，任何"2015–2024 全窗口事件结论"都不可做。
2. **发布滞后语义风险**（最大的前视隐患）：龙虎榜 T 日晚间、两融 T+1 早、增减持事后公告。若直接拿 trade_date/ann_date 当日内可得，会把信息提前到当日盘中。保守滞后规则建议：**统一可得日 = ts_knowledge 次一交易日**；对两融/龙虎榜不得使用任何"当日收盘前可知"假设；无公告日的行 fail-closed 剔除（而非插补）。
3. **index_member_all 无历史**：行业归属与申万分类均为现时快照，2015–2024 历史时点重建不可行；事件研究若需行业分组，须改用时点可辨的替代（sw_daily 指数行情只能给指数收益，给不了成分历史）或接受该维度缺失并记录。
4. **forecast 同键多版本**：update_flag=1 占 31.7%，沿用旧库契约——最早披露版本为可用信号，同键冲突字段 fail-closed，禁 first-non-null 合并。
5. **margin_detail 标的资格历史缺失**：当前只有"现时是两融标的"的部分证据（且混入 ETF 与北交所标的），样本内生性（能上两融池的公司本身有选择性）须在候选 5 类研究中作为选择偏差记录。
6. **主键唯一性未断言**：本次只清点未做全量 dup 扫描（fetch 侧有去重痕迹）；进入 features 层前须按候选主键做正式唯一性核验。
7. **LLM 结构化吞吐量（仅 forecast.change_reason 值得做）**：窗口内约 40,079 行 × 平均 217 字符 ≈ 870 万字符（≈ 500–600 万 token）。按单 worker 每小时数百次调用的常见速度是"数十小时级"批量任务——此为未测量的量级估算，不作为承诺；替代路径：先按 change_reason 高频 n-gram/关键词做廉价分类，仅对低置信残差做 LLM。其余批次均可字典/规则结构化，LLM 需求为零。
8. **杂项数据质量**：repurchase 出现无后缀老三板码（400145）；top_list/margin_detail 各 1 个空文件；express 7 个空报告期（多属正常）；各批次尾日不一（20260904–20260909），合并时按各自 manifest 身份记录。冻结区行数已全部统计在册（见 §0 表），进入研究前按 2024-12-31 边界过滤可得日。
