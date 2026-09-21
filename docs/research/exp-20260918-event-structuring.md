# exp-20260918-event-structuring：事件类原始批次 -> 事件因子表 v1

- 性质：**纯数据工程**。把 6 个事件类 tushare 原始批次按侦察文档
  [`exp-20260917-event-data-scout.md`](exp-20260917-event-data-scout.md) §3 草案结构化为统一事件表。
  不设计策略、不跑回测、不消费试验次数，**不构成任何盈利结论**。
- 运行记录：`artifacts/runs/20260918T014930-event-struct-v1-ac9046d0/`（status=completed，
  耗时 8.7 s，峰值 RSS 4.85 GB；含 manifest、config、metrics、脚本副本、控制台日志）。
- 产物：`data/features/event-factors-v1-20260918/`（每族一个 parquet + 合并 `manifest.json`，
  大文件不入 Git，.gitignore 已覆盖）。
- 源码：`src/quant/data/event_batches.py`（可复用结构化库）、`tools/build_event_factors_v1.py`（薄命令入口）。
- 已验证运行命令（仓库根目录）：
  `PYTHONPATH=D:/量化/src D:/量化/.venv/Scripts/python.exe -X utf8 tools/build_event_factors_v1.py`
- 测试：`tests/unit/test_event_factors.py` 新增 16 项合成小样本测试全部通过
  （方向字典、修正链取首版、share_float 聚合、ts_available 次一交易日翻滚含周末/节假日、
  冻结过滤、fail-closed 剔除、主键断言、event_id 唯一性）；`tests/unit` 全量 168 项通过。

## 1. 输入身份

| 族 | 批次 | manifest sha256（见 features manifest） | 原始行数 |
|---|---|---|---:|
| forecast | `data/raw/tushare/forecast/20260909-r1` | 记录于产物 manifest | 50,406 |
| express | `data/raw/tushare/express/20260909-r1` | 同上 | 8,488 |
| repurchase | `data/raw/tushare/repurchase/20260909-r3` | 同上 | 61,718 |
| share_float | `data/raw/tushare/share_float/20260909-r3` | 同上 | 5,661,143 |
| stk_holdertrade | `data/raw/tushare/stk_holdertrade/20260909-r3` | 同上 | 149,108 |
| disclosure_date | `data/raw/tushare/disclosure_date/20260909-r1` | 同上 | 148,313 |

交易日历：`data/raw/tushare/index_daily/20260917-r1/chunk_000300.SH.csv` 的 trade_date 集合，
2015-01-05..2024-12-31 共 2,431 日（恰好等于研究窗口）。
标的池：`data/processed/baostock-daily-20260917/daily_1999_2024.parquet` distinct symbol
（冻结过滤后 5,410 只 sh/sz；raw `baostock/daily/` 全宇宙 5,552 只，差额为 2025 年后上市、
仅存在于冻结线外的代码，不可能有 `ts_available ≤ 2024-12-31` 的事件行，对入界行无影响——
已用 raw 全宇宙交叉复核，见 manifest `pool` 与逐族 `outside_raw_universe_rows`）。

## 2. 各族行数（构建流水账）

"入界" = `ts_available ≤ 2024-12-31` 并写入 parquet 的行；"出界" = 超冻结线，仅计数不写表；
"剔除" = 标的码不可用（.BJ / 无后缀非标码）。

| 族（event_type） | 原始行 | 剔除 .BJ | 剔除非标 | fail-closed（ts_knowledge 缺失） | 族内规则过滤/聚合 | 入界（写入） | 出界（计数） | in_pool=false |
|---|---:|---:|---:|---:|---|---:|---:|---:|
| forecast（forecast） | 50,406 | 749 | 10 | 0 | 修正链 49,647→46,803 链组 | 37,227 | 9,576 | 31 |
| express（express） | 8,488 | 700 | 0 | 0 | – | 7,619 | 169 | 2 |
| repurchase（repurchase_plan） | 61,718 | 1,463 | 1,080 | 0 | 仅 proc=预案（滤除 44,353） | 12,204 | 2,618 | 0 |
| share_float（unlock） | 5,661,143 | 14,320 | 2,229 | 0 | 聚合为 22,730 组 | 19,101 | 3,629（组级） | 0 |
| stk_holdertrade（holder_trade） | 149,108 | 3,028 | 0 | 0 | in_de 非 IN/DE：0 | 126,098 | 19,982 | 0 |
| disclosure_date（disclosure_shift） | 148,313 | 4,548 | 0 | 0 | pre_date 缺失：0 | 109,483 | 34,282 | 323 |

- 入界行的方向分布：forecast +1=20,359 / −1=16,254 / 0=614；
  express +1=6,880 / −1=713 / 0=26；repurchase_plan 全 +1；unlock 全 −1；
  holder_trade +1=29,823 / −1=96,275；disclosure_shift 全 0。
- 出界口径注意：share_float 的 3,629 是**聚合组级**计数（按组内最早 ann_date 判断），
  与侦察 §0 的原始行级冻结计数（1,453,353 行 ann>2024）口径不同，不可直接对比。
- forecast 出界 9,576 也是链组级（按最早披露版本判断），与侦察行级"ann>2024 共 10,327 行"口径不同。

## 3. 字段口径（逐族）

统一字段：`event_id, event_type, ts_code, ts_event, ts_knowledge, ts_available, direction,
direction_source, confidence, magnitude, raw_text, source_batch, in_pool`。

| 族 | ts_event | ts_knowledge | direction（来源） | confidence | magnitude（单位） | raw_text |
|---|---|---|---|---|---|---|
| forecast | end_date（报告期末） | ann_date | type 枚举字典（field_enum） | high | p_change_min（%，同比区间下界）；额外列 magnitude_max=p_change_max | change_reason；额外列 summary |
| express | end_date | ann_date | sign(yoy_net_profit)（derived） | high | yoy_net_profit（元，tushare 原值） | – |
| repurchase_plan | ann_date（首次预案公告日） | ann_date | 常量 +1（field_enum） | high | null（v1 不带规模字段） | – |
| unlock | float_date（解禁日） | 组内最早 ann_date | 常量 −1（field_enum，供给压力） | medium | 聚合 float_ratio（%，占总股本，"求和比例"）；额外列 float_share_sum/agg_row_count/agg_ann_date_count | – |
| holder_trade | ann_date（行为日缺失） | ann_date | in_de：IN→+1 / DE→−1（field_enum） | medium | change_ratio（%） | – |
| disclosure_shift | pre_date（预约披露日） | ann_date | 常量 0（field_enum） | medium | null | – |

时间契约：`ts_available` = `ts_knowledge` 的**次一交易日**（严格大于；收盘信号最早次一交易日执行）。
ts_knowledge 早于日历首日的行映射到日历首日并计数（实测全族均为 0）；
ts_knowledge 晚于日历末日的行 ts_available 为空 → 计入出界。
ts_knowledge 缺失的行 fail-closed 剔除并计数（实测全族 0，与侦察一致，规则纯防御）。
单位不跨族归一（上表逐族写明）。

方向字典版本：`event-direction-dict-v1`（manifest 内含完整映射）。
forecast：预增/略增/扭亏/续盈→+1；预减/略减/首亏/续亏→−1；不确定/增亏/减亏/其他/null→0
（任务规则"其余→0"逐字执行，故增亏/减亏虽语义偏空仍记 0）。

`event_id` = `{event_type}.{ts_code}.{ts_event:%Y%m%d}.{seq}`，seq 在 (ts_code, ts_event) 内按
确定性排序 1 起编（repurchase_plan 同日多 campaign、disclosure 同 pre_date 链等靠 seq 区分）。
六表各自 event_id 全量唯一（已断言）。

## 4. 口径与规则决策（本实施的解释空间，逐条记录）

1. **主键唯一性断言的双层解释**：侦察 §1 的"候选主键"全量核验结果——forecast/express/disclosure_date
   0 碰撞；repurchase 2,039 组、share_float 157 组、stk_holdertrade 3,457 组候选键碰撞。
   逐组核查证实**没有任何全行完全重复**（fetch 侧 repurchase/holdertrade 的"去重N行"动作之外，
   剩余碰撞全部是内容不同的合法记录：同日多 campaign、同持有人多笔解禁批次、同键多次权益变动申报）。
   因此实施定义：*重复行 = 全行完全重复*（0 组，命中即 fail）；*候选键碰撞但内容不同* = 合法多行，
   逐组计数 + 抽样登记进 features manifest（`pk_report`），全部保留、不静默去重，靠 event_id seq 区分。
   "批次 manifest 已登记去重动作"的复核方式：确认剩余行中全行重复为 0，与 fetch 侧已去重的状态一致。
2. **forecast 修正链**：按 (first_ann_date, ann_date, update_flag) 排序取每组最早一行，
   **不做任何跨版本字段合并**（禁 first-non-null）。链组 46,803 个，同 (first_ann,ann) 并列组 0 个
   （无需并列裁决）；first_ann_date 缺失 23 行回退用 ann_date 参与排序（已计数）。
3. **forecast magnitude 拆两列**：任务要求"magnitude 用 p_change_min/max（缺失记 null）"，
   但统一 schema 只有单列 magnitude。决策：magnitude=p_change_min（区间下界），另加
   `magnitude_max=p_change_max` 附加列，丢失为零、不发明中位数。raw_text=change_reason，
   另加 `summary` 附加列（侦察 §3 草案本就提到 change_reason/summary 两处文本）。
4. **share_float 聚合的 PIT 近似**：聚合键 (ts_code, float_date, share_type)，ts_knowledge 取组内
   **最早** ann_date；若组内有多个 ann_date（改期/更正再披露），聚合和可能混入晚于 ts_knowledge
   才披露的行。入界组中这类多 ann_date 组 5,139 个（占 26.9%），已逐组给出
   `agg_ann_date_count` 附加列供下游自行收紧（例如只取 =1 的组）。全部 ratio 为空的组 1,185 个
   → magnitude=null。
5. **repurchase 只认 proc='预案'**：其他进度行（完成/股东大会通过/实施/停止，44,353 行）滤除并计数，
   是状态推进的覆盖式披露，非事件起点。同一 (ts_code, ann_date) 多 campaign 全保留
   （入界后同日多 campaign 组 475 个），靠 event_id seq 区分。
6. **holder_trade 的 ts_event**：批次无行为发生日字段，按侦察 §4.5 默认 ts_event=ts_knowledge=ann_date，
   confidence=medium。同键多行（如 603708.SH 单日单持有人 74 行、仅 after_* 不同）全部保留，
   可能对应同一经济事件的多次申报——**去重规则留给研究层预登记，v1 不裁决**。
7. **B 股与非标码**：`^\d{6}\.(SH|SZ)$` 之外的码剔除并计数（含 repurchase 的无后缀老三板码
   1,080 行、各族 .BJ 共 24,808 行）。B 股（200xxx.SZ/900xxx.SH）后缀合法故保留，
   但不在 baostock 池内 → `in_pool=false`（disclosure_date 323 行、forecast 31、express 2；
   forecast 中另有 001235.SZ/300060.SZ/603361.SH/688688.SH 等 baostock 覆盖缺口的 A 股码被同样标记）。
   下游构建股票池时应过滤 in_pool=false。
8. **交易日历用 000300 指数日**：与 A 股交易所日历一致（指数交易日=全市场交易日），
   2,431 日恰为 2015–2024 全窗口。
9. **express 批次 manifest 异常记录**：其 fetch manifest 把 31 个报告期全部列入 `skipped`，
   但磁盘上 24 个文件有数据（8,488 行）、7 个空文件。按批次原样登记身份（sha256），不做解释性修补。

## 5. 真实行手工核对（≥3 条，全部一致）

| 族 | 标的/键 | 原始值（raw CSV） | 事件表值 | 核对点 |
|---|---|---|---|---|
| forecast | 300146.SZ end=20191231 | 首亏，−136.9193/−136.4204，change_reason 791 字 | direction=−1，magnitude=−136.9193，magnitude_max=−136.4204，ts_knowledge=2020-01-01，ts_available=2020-01-02 | 方向字典、区间两列、文本保留、跨元旦翻日 |
| forecast | 600519.SH end=20191231 | 仅 1 行：略增 15/15，ann=20200102（update_flag=1） | direction=+1，magnitude=15.0，ts_knowledge=2020-01-02，ts_available=2020-01-03 | 修正链取最早版（该键无更早版本） |
| express | 000028.SZ end=20200630 | yoy_net_profit=649,154,400 元（≈6.49 亿，侦察抽样同源） | direction=+1，magnitude=649154400.0，ts_available=2020-08-19 | sign 派生、次一交易日 |
| share_float | 300684.SZ float=20200106 股权激励限售流通 | 5 行原始，ratio 和=0.7304，share 和=1,840,800 | magnitude=0.7304，float_share_sum=1840800.0，agg_row_count=5，direction=−1，ts_available=2020-01-02 | 求和聚合、供给方向 |
| stk_holdertrade | 002065.SZ ann=20200101 览海医疗 DE | change_ratio=0.3291 | direction=−1，magnitude=0.3291，ts_event=ts_knowledge=2020-01-01，ts_available=2020-01-02 | DE→−1、事后公告口径 |
| disclosure_date | 600396.SH end=20191231 | ann=20200330，pre=20200408 | ts_event=2020-04-08，ts_knowledge=2020-03-30，ts_available=2020-03-31，direction=0 | pre_date 作事件日、direction=0 |

## 6. 已知局限（沿侦察 §5，v1 未解决也不应在 v1 解决）

1. **覆盖窗口晚于 2015**：forecast 自 2018-09、express/disclosure_date 自 2018 年报期（2019 披露）、
   repurchase/share_float/holdertrade 自 2016 起。跨族统一比较最长只有 2019–2024；
   任何"2015–2024 全窗口事件结论"不可做。
2. **事后公告语义**：holder_trade 行为日未知（ts_event=ann_date 是近似）；解禁（unlock）是天然的
   公告先行事件，但本表只保留了 float_date 事件面，"公告日反应 vs 解禁日反应"两个研究面对齐
   需要下游从 ts_event/ts_knowledge 两列分别取用。
3. **非 PIT 注册表类风险**：share_float 多 ann_date 组的聚合近似（§4.4）；B 股与 baostock 覆盖缺口
   股以 in_pool=false 标记而非删除；industry/index 归属仍是现时快照（本轮未消费）。
4. **出界口径为链组/聚合组级**（forecast、share_float），与侦察行级冻结计数口径不同（§2 注）。
5. **候选键碰撞保留**：holder_trade 同键多行、repurchase 同日多 campaign 均未做经济事件去重，
   事件计数会高于"独立经济事件数"；研究层使用前须预登记去重规则。
6. **交易日历为指数代理**：无独立交易所日历来源时使用 000300 交易日，未发现差异迹象但未做第二来源核验。
7. **ts_available 为纯日历翻滚**：未考虑公告发布时点（如盘后 vs 盘中），统一按"公告日收盘后可知、
   次一交易日可执行"的保守口径。

## 7. 声明

本轮仅为把既有原始批次结构化为统一事件表的数据工程交付。direction/confidence/magnitude 是
**字典与规则映射的字段**，不是可交易信号；本文档与产物不包含任何收益、胜率或策略有效性结论；
2025-01-01 及以后仍处于冻结状态，超界行仅完成计数。
