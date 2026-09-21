# B-01 TRAIN 常数窗口定位扫描（系统审计 E 阶段⑥）

日期：2026-09-11。脚本：`experiments/system_audit_b01_train_scan_20260911.py`（只读；零第三方依赖）。
上游发现：`docs/experiments/system-audit-bcde-independent-review-20260910.md` B-01/P1——ZSCORE/STD/CORR 在输入滚动窗**完全常数**（max==min）时，旧实现输出伪值（伪 z=-0.9916…/伪相关）而非 None；修复后（operators.py 零方差规则）输出 None。审计要求「是否命中具体历史窗口尚需 TRAIN 定位」，本脚本即该定位工具。

**状态：脚本已交付并通过合成自检；全市场正式扫描尚未执行**（按分工由主对话在集成阶段择机运行，避免与在途批次争内存）。下文 SCAN 标记块内为占位说明，正式扫描输出由脚本自动渲染写入同两标记之间。

## 1. 语义与边界（先于一切数字）

- **命中定义**：滑窗 `max(win)==min(win)` 且窗内全部值为有限数（`None`/NaN/±inf 一票否决——None 会先传播为 None，按算子语义不算常数命中）。窗口长度与输入表达式取自假设公式静态解析（复用冻结 parser `factor_miner.compiler`，不重写语法）。
- **B-01 相关算子**：STD / ZSCORE / CORR（常数窗 → 未定义/伪值）。CORR 两侧任一为常数窗即命中（分别按 (左输入, n)、(右输入, n) 记账）。
- **信息性需求**（MEAN/SUM/RET/MAX/MIN/DELTA/TS_RANK）：常数窗输出数学上良好，不构成 B-01 缺陷；仅作描述性披露（报告中 B-01 列=info）。
- **双轴对照（B-01×B-03 交互）**：
  - `calendar_axis`＝冻结交易日历 ∩ 窗口（B-03 修复后语义；缺行日=None 断窗）；
  - `compressed_axis`＝该股自身行日期轴（旧「全 bundle 行日期并集」轴的**每股近似**；会越过共同缺行日）。
  - 两列之差量化「旧轴可能多算的伪信号」。近似声明：旧轴是全 bundle 并集而非单股行日期；全 bundle 共同缺日（=B-03 触发条件本身）下，旧轴真实命中可能高于 compressed 列。
- **近常数窗**（浮点残差级差）不在本轮范围（与 operators.py 修复注释同一边界声明）。
- **分区纪律**：所有真实读取经 `partition.enforce_window`/`train_only_window`（`allow_validation/allow_lockbox` 恒 False）+ 预热唯一通道 `partition.warmup_read("TRAIN", ≤365 日历日)`（预热窗 2019-01-02..2019-12-31，只服务窗口完整性）；另有脚本级硬断言（任何进入计数的日期 > TRAIN[1] 即 fail-closed 抛错）。**绝不读取 2024-01-01 之后任何数据。**
- **内存有界**：price/industry 逐股流式；daily_basic/margin/lhb 按 `--batch-size`（缺省 200 只）分批，批间只保留该批标量；全程只累计计数器，不保留跨股序列。CS_RANK 输入与引擎派生字段（market_ret/market_vol/adv_dec_ratio/limit_up_count，`loader=None, derived=True`）**不可逐股扫描**，进 skipped 清单（bundle 级待复算），不臆造计数。

## 2. 需求集合（--parse-only，2026-09-11 实测）

输入：`artifacts/factor-miner/r0-20260910/hypotheses/_all_raw.jsonl`（250 条假设）。

- 解析成功 **250/250**；**parse_fail 清单：空（0 条）**——无因解析失败被排除的因子。
- 含 STD/ZSCORE/CORR 的因子：**67 个**（按家族：STATE 25、REV 18、REL 13、META 11；含同一因子多次命中不同需求）。
- B-01 需求实例 113 个 → 去重后 **38 个可逐股扫描需求**（窗口分布：10 日×3、20 日×22、60 日×13）；**CS_RANK 输入需求 0 个**（本批 250 条公式中 STD/ZSCORE/CORR 的直接输入均不含横截面算子）。
- 信息性去重需求 110 个（DELTA 20、MEAN 32、MAX 6、MIN 7、RET 11、SUM 20、TS_RANK 14）。

38 个 B-01 可扫描需求（op(输入,窗口)）：

```text
CORR(RET(close,1),20)            CORR(RET(close,1),60)            CORR(RET(margin_balance,1),20)
CORR(adv_dec_ratio,20)*          CORR(close,20)                   CORR(industry_ret_l1,60)
CORR(limit_up_count,20)*         CORR(market_ret,20)*             CORR(market_ret,60)*
CORR(volume,20)                  STD(((close/open)-1),10)         STD(((open/preclose)-1),10)
STD((RET(close,1)-industry_ret_l1),60)  STD((RET(close,1)-market_ret),60)*
STD(RET(close,1),10)             STD(RET(close,1),20)             STD(RET(margin_balance,1),20)
STD(market_ret,20)*              ZSCORE((ABS(RET(close,1))/amount),20)
ZSCORE((RET(close,20)-SUM(industry_ret_l1,20)),60)
ZSCORE((RET(close,20)-SUM(market_ret,20)),60)*
ZSCORE(RET(close,1),20)          ZSCORE(RET(close,20),60)         ZSCORE(RET(close,5),20)
ZSCORE(STD(RET(close,1),20),60)  ZSCORE(SUM((RET(close,1)-industry_ret_l1),20),60)
ZSCORE(SUM((RET(close,1)-market_ret,20)),60)*
ZSCORE(adv_dec_ratio,20)*        ZSCORE(adv_dec_ratio,60)*        ZSCORE(amount,20)
ZSCORE(close,20)                 ZSCORE(lhb_net_buy,60)           ZSCORE(limit_up_count,20)*
ZSCORE(margin_balance,20)        ZSCORE(margin_buy,20)            ZSCORE(turnover_rate,20)
ZSCORE(turnover_rate_f,20)       ZSCORE(volume,20)
```

带 `*` 的 9 个需求引用引擎派生 STATE 字段（market_ret/market_vol/adv_dec_ratio/limit_up_count 的裸字段或子表达式），**逐股扫描不可行**（这些序列由全 bundle 派生），正式扫描会归入 skipped 清单（bundle 级待复算），共 38−9=29 个需求可直接扫描。装载路由：price（含 open/high/low/close/preclose/volume/amount）、valuation（daily_basic）、margin、lhb、industry（industry_ret_l1 市场级序列注入逐股 pass）；路由函数 `route_demands` 有自检覆盖。

## 3. 自检（纯合成数据，不触真实数据目录）

命令与输出（2026-09-11 实测）：

```text
$ python experiments/system_audit_b01_train_scan_20260911.py --self-test
SELF-TEST OK: 18/18 assertions passed
## 常数窗口命中矩阵（扫描输出）

- 扫描股票数：2
- 命中口径：滑窗 max==min 且窗内全为有限值；轴日期落在 TRAIN 2020-01-01..2022-12-31 内；窗口含 None 不命中。
- calendar_axis=冻结交易日历轴（B-03 修复后语义）；compressed_axis=该股自身行日期轴（旧并集轴的每股近似）。
- skipped（未逐股扫描，bundle 级待复算）：{}
- parse_fail：0 条

| op | 输入 | 窗口 | kind | B-01 | calendar_axis | compressed_axis | 命中股数 | 末次命中 |
|---|---|---|---|---|---|---|---|---|
| STD | `volume` | 5 | field | yes | 27 | 27 | 1 | 2020-01-31 |
| STD | `turnover_rate*2` | 10 | expr | yes | 3 | 3 | 1 | 2020-01-12 |
| ZSCORE | `close` | 10 | field | yes | 1 | 1 | 1 | 2020-01-10 |
```

自检覆盖的 18 条断言：常数窗检出（全常数 volume：窗 5 命中 27 处）、None 断窗（close 常数段被 None 劈开：仅 1 处命中）、expr 输入求值（`turnover_rate*2` 窗 10 命中 3 处）、CS_RANK 输入不入逐股计数、缺行场景双轴分歧（calendar=0 / compressed=1，即 B-01×B-03 交互方向）、路由归类（price/valuation/margin/lhb/industry + skipped：派生字段、CS 输入、含派生字段的 expr）、报告渲染结构。

## 4. 全市场正式扫描（主对话集成阶段执行）

建议执行方式（先小样本试点，再全量；避免与在途批次/其他代理并行争内存）：

```bash
# 试点（约 50 只，验证装载与产出结构；写报告标记块）
python experiments/system_audit_b01_train_scan_20260911.py --scan \
  --symbols-file <试点清单文件> --report docs/experiments/system-audit-b01-train-scan-20260911.md
# 全量（universe=engine.load_formal_universe；批 200 可调）
python experiments/system_audit_b01_train_scan_20260911.py --scan \
  --report docs/experiments/system-audit-b01-train-scan-20260911.md
```

输出写入下方 SCAN 标记块之间（不覆盖文档其余内容；`_write_report_block` 独占重写标记内文本）。

<!-- SCAN:BEGIN（脚本自动渲染，勿手改） -->
## 常数窗口命中矩阵（扫描输出）

- 扫描股票数：27760
- 命中口径：滑窗 max==min 且窗内全为有限值；轴日期落在 TRAIN 2020-01-01..2022-12-31 内；窗口含 None 不命中。
- calendar_axis=冻结交易日历轴（B-03 修复后语义）；compressed_axis=该股自身行日期轴（旧并集轴的每股近似）。
- skipped（未逐股扫描，bundle 级待复算）：["CORR|adv_dec_ratio|20", "CORR|limit_up_count|20", "CORR|market_ret|20", "CORR|market_ret|60", "DELTA|(RET(close,20) - SUM(market_ret,20))|10", "DELTA|CORR(RET(close,1),market_ret,60)|20", "DELTA|adv_dec_ratio|5", "DELTA|market_vol|5", "MAX|(RET(close,1) - market_ret)|20", "MEAN|(RET(close,1) - market_ret)|60", "MEAN|CORR(RET(close,1),market_ret,60)|20", "MEAN|adv_dec_ratio|20", "MEAN|adv_dec_ratio|60", "MEAN|limit_up_count|20", "MEAN|limit_up_count|60", "MEAN|market_ret|20", "MEAN|market_vol|20", "MEAN|market_vol|60", "MIN|(RET(close,1) - market_ret)|20", "MIN|SUM((RET(close,1) - market_ret),5)|20", "RET|market_ret|20", "STD|(RET(close,1) - market_ret)|60", "STD|market_ret|20", "SUM|(0.5 * (1 - SIGN((RET(close,1) - market_ret))))|20", "SUM|(RET(close,1) - (CORR(RET(close,1),market_ret,60) * market_ret))|20", "SUM|(RET(close,1) - market_ret)|20", "SUM|(RET(close,1) - market_ret)|5", "SUM|market_ret|20", "SUM|market_ret|60", "TS_RANK|SUM((RET(close,1) - market_ret),20)|60", "TS_RANK|adv_dec_ratio|60", "TS_RANK|limit_up_count|60", "TS_RANK|market_vol|60", "ZSCORE|(RET(close,20) - SUM(market_ret,20))|60", "ZSCORE|SUM((RET(close,1) - market_ret),20)|60", "ZSCORE|adv_dec_ratio|20", "ZSCORE|adv_dec_ratio|60", "ZSCORE|limit_up_count|20"]
- parse_fail：0 条

| op | 输入 | 窗口 | kind | B-01 | calendar_axis | compressed_axis | 命中股数 | 末次命中 |
|---|---|---|---|---|---|---|---|---|
| STD | `((close / open) - 1)` | 10 | expr | yes | 2516 | 2516 | 290 | 2022-01-21 |
| STD | `RET(close,1)` | 10 | expr | yes | 1852 | 1852 | 207 | 2022-01-21 |
| CORR | `close` | 20 | field | yes | 1539 | 1539 | 11 | 2022-11-01 |
| ZSCORE | `close` | 20 | field | yes | 1539 | 1539 | 11 | 2022-11-01 |
| CORR | `RET(close,1)` | 20 | expr | yes | 1530 | 1530 | 11 | 2022-11-01 |
| STD | `RET(close,1)` | 20 | expr | yes | 1530 | 1530 | 11 | 2022-11-01 |
| ZSCORE | `RET(close,1)` | 20 | expr | yes | 1530 | 1530 | 11 | 2022-11-01 |
| ZSCORE | `RET(close,5)` | 20 | expr | yes | 1494 | 1494 | 11 | 2022-11-01 |
| CORR | `RET(close,1)` | 60 | expr | yes | 1307 | 1307 | 5 | 2020-12-15 |
| CORR | `volume` | 20 | field | yes | 1300 | 1300 | 9 | 2020-12-15 |
| ZSCORE | `amount` | 20 | field | yes | 1300 | 1300 | 9 | 2020-12-15 |
| ZSCORE | `volume` | 20 | field | yes | 1300 | 1300 | 9 | 2020-12-15 |
| ZSCORE | `RET(close,20)` | 60 | expr | yes | 1250 | 1250 | 5 | 2020-12-15 |
| CORR | `RET(margin_balance,1)` | 20 | expr | yes | 0 | 0 | 0 | - |
| CORR | `industry_ret_l1` | 60 | field | yes | 0 | 0 | 0 | - |
| STD | `((open / preclose) - 1)` | 10 | expr | yes | 0 | 0 | 0 | - |
| STD | `(RET(close,1) - industry_ret_l1)` | 60 | expr | yes | 0 | 0 | 0 | - |
| STD | `RET(margin_balance,1)` | 20 | expr | yes | 0 | 0 | 0 | - |
| ZSCORE | `(ABS(RET(close,1)) / amount)` | 20 | expr | yes | 0 | 0 | 0 | - |
| ZSCORE | `(RET(close,20) - SUM(industry_ret_l1,20))` | 60 | expr | yes | 0 | 0 | 0 | - |
| ZSCORE | `STD(RET(close,1),20)` | 60 | expr | yes | 0 | 0 | 0 | - |
| ZSCORE | `SUM((RET(close,1) - industry_ret_l1),20)` | 60 | expr | yes | 0 | 0 | 0 | - |
| ZSCORE | `lhb_net_buy` | 60 | field | yes | 0 | 0 | 0 | - |
| ZSCORE | `margin_balance` | 20 | field | yes | 0 | 0 | 0 | - |
| ZSCORE | `margin_buy` | 20 | field | yes | 0 | 0 | 0 | - |
| ZSCORE | `turnover_rate_f` | 20 | field | yes | 0 | 0 | 0 | - |
| ZSCORE | `turnover_rate` | 20 | field | yes | 0 | 0 | 0 | - |
| RET | `close` | 1 | field | info | 3024572 | 3024572 | 4760 | 2022-12-30 |
| RET | `margin_balance` | 1 | field | info | 1524707 | 1524707 | 3185 | 2022-12-30 |
| MEAN | `SIGN(RET(close,1))` | 5 | expr | info | 144674 | 144674 | 4711 | 2022-11-21 |
| MAX | `((ABS(RET(close,1)) - RET(close,1)) / 2)` | 10 | expr | info | 5663 | 5663 | 1275 | 2022-08-25 |
| MEAN | `((ABS(RET(close,1)) - RET(close,1)) / 2)` | 10 | expr | info | 5663 | 5663 | 1275 | 2022-08-25 |
| SUM | `((ABS(RET(close,1)) - RET(close,1)) / 2)` | 10 | expr | info | 5663 | 5663 | 1275 | 2022-08-25 |
| MEAN | `((1 - SIGN(RET(close,1))) / 2)` | 10 | expr | info | 4543 | 4543 | 1318 | 2022-08-26 |
| MAX | `close` | 5 | field | info | 3976 | 3976 | 482 | 2021-11-19 |
| MIN | `close` | 5 | field | info | 3976 | 3976 | 482 | 2021-11-19 |
| RET | `close` | 5 | field | info | 3976 | 3976 | 482 | 2021-11-19 |
| DELTA | `amount` | 5 | field | info | 2527 | 2527 | 281 | 2021-07-15 |
| TS_RANK | `volume` | 5 | field | info | 2526 | 2526 | 281 | 2021-07-15 |
| MEAN | `((close / open) - 1)` | 10 | expr | info | 2516 | 2516 | 290 | 2022-01-21 |
| RET | `close` | 10 | field | info | 2098 | 2098 | 237 | 2022-01-21 |
| MEAN | `ABS(RET(close,1))` | 10 | expr | info | 1852 | 1852 | 207 | 2022-01-21 |
| SUM | `ABS(RET(close,1))` | 10 | expr | info | 1852 | 1852 | 207 | 2022-01-21 |
| SUM | `RET(close,1)` | 10 | expr | info | 1852 | 1852 | 207 | 2022-01-21 |
| MEAN | `SIGN(RET(close,1))` | 20 | expr | info | 1550 | 1550 | 19 | 2020-07-29 |
| MAX | `close` | 20 | field | info | 1539 | 1539 | 11 | 2022-11-01 |
| MEAN | `close` | 20 | field | info | 1539 | 1539 | 11 | 2022-11-01 |
| MIN | `close` | 20 | field | info | 1539 | 1539 | 11 | 2022-11-01 |
| RET | `close` | 20 | field | info | 1539 | 1539 | 11 | 2022-11-01 |
| TS_RANK | `close` | 20 | field | info | 1539 | 1539 | 11 | 2022-11-01 |
| MAX | `high` | 20 | field | info | 1533 | 1533 | 11 | 2022-11-01 |
| MIN | `low` | 20 | field | info | 1531 | 1531 | 11 | 2022-11-01 |
| MAX | `RET(close,1)` | 20 | expr | info | 1530 | 1530 | 11 | 2022-11-01 |
| MEAN | `RET(close,1)` | 20 | expr | info | 1530 | 1530 | 11 | 2022-11-01 |
| MIN | `RET(close,1)` | 20 | expr | info | 1530 | 1530 | 11 | 2022-11-01 |
| SUM | `(volume * SIGN(RET(close,1)))` | 10 | expr | info | 1515 | 1515 | 139 | 2021-07-15 |
| SUM | `volume` | 10 | field | info | 1514 | 1514 | 139 | 2021-07-15 |
| DELTA | `RET(close,20)` | 5 | expr | info | 1513 | 1513 | 13 | 2022-11-01 |
| RET | `close` | 30 | field | info | 1449 | 1449 | 11 | 2022-11-01 |
| SUM | `(((1 - SIGN(RET(close,1))) / 2) * volume)` | 20 | expr | info | 1379 | 1379 | 27 | 2020-07-29 |
| RET | `close` | 60 | field | info | 1310 | 1310 | 5 | 2020-12-15 |
| TS_RANK | `close` | 60 | field | info | 1310 | 1310 | 5 | 2020-12-15 |
| RET | `volume` | 20 | field | info | 1300 | 1300 | 9 | 2020-12-15 |
| SUM | `(SIGN(RET(close,1)) * volume)` | 20 | expr | info | 1300 | 1300 | 9 | 2020-12-15 |
| SUM | `amount` | 20 | field | info | 1300 | 1300 | 9 | 2020-12-15 |
| SUM | `volume` | 20 | field | info | 1300 | 1300 | 9 | 2020-12-15 |
| TS_RANK | `RET(close,20)` | 60 | expr | info | 1250 | 1250 | 5 | 2020-12-15 |
| MEAN | `close` | 120 | field | info | 1117 | 1117 | 5 | 2020-12-15 |
| RET | `close` | 120 | field | info | 1117 | 1117 | 5 | 2020-12-15 |
| MEAN | `((close - low) / (high - low))` | 5 | expr | info | 341 | 341 | 194 | 2020-07-09 |
| DELTA | `lhb_net_buy` | 5 | field | info | 21 | 21 | 5 | 2020-08-25 |
| MEAN | `SIGN(lhb_net_buy)` | 20 | expr | info | 6 | 6 | 1 | 2021-05-28 |
| MEAN | `((((2 * close) - high) - low) / (high - low))` | 10 | expr | info | 3 | 3 | 3 | 2021-04-06 |
| DELTA | `((high - low) / preclose)` | 5 | expr | info | 0 | 0 | 0 | - |
| DELTA | `(RET(close,20) - SUM(industry_ret_l1,20))` | 10 | expr | info | 0 | 0 | 0 | - |
| DELTA | `(margin_balance / circ_mv)` | 20 | expr | info | 0 | 0 | 0 | - |
| DELTA | `CORR(RET(close,1),industry_ret_l1,60)` | 20 | expr | info | 0 | 0 | 0 | - |
| DELTA | `DELTA(margin_balance,5)` | 5 | expr | info | 0 | 0 | 0 | - |
| DELTA | `LOG(pe_ttm)` | 20 | expr | info | 0 | 0 | 0 | - |
| DELTA | `STD(RET(close,1),20)` | 20 | expr | info | 0 | 0 | 0 | - |
| DELTA | `margin_balance` | 20 | field | info | 0 | 0 | 0 | - |
| DELTA | `margin_balance` | 5 | field | info | 0 | 0 | 0 | - |
| DELTA | `pb` | 20 | field | info | 0 | 0 | 0 | - |
| DELTA | `pb` | 60 | field | info | 0 | 0 | 0 | - |
| DELTA | `turnover_rate` | 20 | field | info | 0 | 0 | 0 | - |
| DELTA | `turnover_rate` | 5 | field | info | 0 | 0 | 0 | - |
| MEAN | `(((high + low) - (2 * close)) / preclose)` | 5 | expr | info | 0 | 0 | 0 | - |
| MEAN | `((close - low) / preclose)` | 5 | expr | info | 0 | 0 | 0 | - |
| MEAN | `((close - open) / preclose)` | 5 | expr | info | 0 | 0 | 0 | - |
| MEAN | `((high - close) / preclose)` | 5 | expr | info | 0 | 0 | 0 | - |
| MEAN | `((high - low) / preclose)` | 20 | expr | info | 0 | 0 | 0 | - |
| MEAN | `((open / preclose) - 1)` | 10 | expr | info | 0 | 0 | 0 | - |
| MEAN | `(ABS(RET(close,1)) / amount)` | 20 | expr | info | 0 | 0 | 0 | - |
| MEAN | `(RET(close,1) - industry_ret_l1)` | 60 | expr | info | 0 | 0 | 0 | - |
| MEAN | `industry_ret_l1` | 20 | field | info | 0 | 0 | 0 | - |
| MEAN | `turnover_rate` | 60 | field | info | 0 | 0 | 0 | - |
| MEAN | `volume_ratio` | 20 | field | info | 0 | 0 | 0 | - |
| MIN | `(RET(close,1) - industry_ret_l1)` | 20 | expr | info | 0 | 0 | 0 | - |
| RET | `margin_balance` | 20 | field | info | 0 | 0 | 0 | - |
| SUM | `((high - low) / preclose)` | 10 | expr | info | 0 | 0 | 0 | - |
| SUM | `(RET(close,1) - industry_ret_l1)` | 20 | expr | info | 0 | 0 | 0 | - |
| SUM | `industry_ret_l1` | 20 | field | info | 0 | 0 | 0 | - |
| SUM | `lhb_net_buy` | 20 | field | info | 0 | 0 | 0 | - |
| SUM | `margin_buy` | 20 | field | info | 0 | 0 | 0 | - |
| TS_RANK | `((high - low) / preclose)` | 20 | expr | info | 0 | 0 | 0 | - |
| TS_RANK | `DELTA(margin_balance,5)` | 60 | expr | info | 0 | 0 | 0 | - |
| TS_RANK | `LOG(pe_ttm)` | 250 | expr | info | 0 | 0 | 0 | - |
| TS_RANK | `RET(margin_balance,20)` | 60 | expr | info | 0 | 0 | 0 | - |
| TS_RANK | `lhb_net_buy` | 60 | field | info | 0 | 0 | 0 | - |
| TS_RANK | `pb` | 250 | field | info | 0 | 0 | 0 | - |
<!-- SCAN:END -->

## 5. 结果用途与重算衔接

- 命中数>0 的 (因子, 输入, 窗口)：其 TRAIN 因子值/排名/IC/门禁在旧代码下含伪值成分 → 按 B-01 验收条款「命中因子从因子值节点重算，不沿用旧结果」办理；修复后代码（operators.py 零方差规则，工作树已在位、待独立复审闭合）下这些窗口输出 None，相关统计须以新代码重算。
- 命中数=0 的需求：静态证明旧缺陷在该需求上无 TRAIN 真实命中（在 compressed_axis 与 calendar_axis 两列均为 0 时），可解除该因子的 B-01 重算必要（其余缺陷 C-01/D-01 等的重算要求独立成立，不因 B-01 零命中而豁免）。
- skipped 需求（引擎派生 STATE 输入）：留待 bundle 级复算（与正式流水线共用 build_real_bundle 时一并计算），不得以逐股近似代替。
