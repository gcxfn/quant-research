# V3 生产 ETF 池商品排除修复（D-2026-09-11-04）

日期：2026-09-11
执行：flash 实现代理（removal-only，最小可审计变更）
授权：用户确认 D-2026-09-11-04；规则依据 D-2026-09-09-04（ETF 纳入/排除冻结）

## 1. 背景

D-2026-09-09-04 冻结规则：**纳入跟踪 A 股指数的股票型 ETF，排除 QDII/跨境
（513 段及名称关键词）、债券、商品、货币、北交所（T+0 或定价机制不同），适用
于一切 ETF 池构建，剔除名单逐只留档。**

`docs/experiments/evidence-graph-20260911.md` #6 审计发现：`configs/strategy.json`
生产池含两只商品 ETF（sh518880 黄金现货、sz159985 豆粕期货），且首条 V3 生产
信号（2026-09-04，decisions.md）Top3 即含 sz159985，生产收益引擎已实际把商品
ETF 纳入轮动候选，与冻结规则直接冲突。`scripts/build_pool.py` 已有"黄金商品/
豆粕商品"主题分组（GROUPS），但分组结果不排除。用户确认走规则级修复
（D-2026-09-11-04）。

## 2. 方法与数据

- **离线**：未重新抓取任何数据（任务禁令）。定性证据全部来自仓库内已有
  `data/raw/tushare/fund_basic/20260909-r1/`（2026-09-09 批次，主对话抽审
  PASS），字段 `fund_type`/`invest_type`/`benchmark`（业绩基准）为基金标的
  性质的权威时点快照。
- 对现有池 **全部 55 只成员** 逐只与 fund_basic 对账（ts_code 精确匹配，
  55/55 命中，无缺行），按"商品期货/商品现货合约 = 商品；基准含港股/海外
  市场 = 跨境；fund_type=债券型/货币型/QDII；北交所代码段"逐维度核验。
- diff 为**纯删除**：不新增成员、不修改保留成员的任何字段（symbol/name/
  group 原样，顺序原样）；`configs/strategy.json` 仅删除 3 个数组元素并更新
  `pool_note`，键序与缩进不变。

## 3. 剔除清单（逐只留档）

| # | symbol | 池内简称 | 组 | 基金全称（fund_basic） | fund_type | invest_type | 业绩基准 | 依据条款 |
|---|--------|----------|----|------------------------|-----------|-------------|----------|----------|
| 1 | sh518880 | 黄金ETF华安 | 黄金商品 | 华安易富黄金ETF | 其他 | **黄金现货合约** | 国内黄金现货价格收益率(Au99.99合约)×100% | **商品**（商品现货合约 ETF，非股票型，不跟踪 A 股指数） |
| 2 | sz159985 | 豆粕ETF华夏 | 豆粕商品 | 华夏饲料豆粕期货ETF | 其他 | **豆粕期货型** | 大连商品交易所豆粕期货价格指数收益率×100% | **商品**（商品期货 ETF，非股票型） |
| 3 | sh517520 | 黄金股ETF永赢 | 黄金股 | 永赢中证**沪深港**黄金产业股票ETF | 股票型 | 被动指数型 | 中证**沪深港**黄金产业股票指数收益率×100% | **跨境**（基准为跨沪-深-港市场指数，含港股成分，不满足"跟踪 A 股指数"纳入条款；基金全称含跨境名称关键词"沪深港"，池内简称"黄金股ETF永赢"将该关键词缩写掩盖；原 `build_pool.EXCLUDE` 仅有"沪港深"这一种词序，属工具词序缺口） |

池规模：55 → 52。保留的 52 只成员字段与顺序零改动。

**关于 sh517520 的判断说明（供用户复核）**：evidence-graph #6 曾记"若按
「跟踪A股指数的股票型ETF」口径可能合规"。本次 fund_basic 基准证据
（中证沪深港黄金产业股票指数）落实后，该指数按构造同时纳入沪、深、港三地
黄金产业股票，严格不满足纳入条款"跟踪 A 股指数"；且 D-04 对"跨境"的识别
口径（513 段及名称关键词）在其基金全称上同样命中（"沪深港"）。两条路径
结论一致，故按跨境剔除。若用户采纳更窄口径（仅 513 段+池内简称关键词），
恢复该成员只需在 `configs/strategy.json` 池数组原位插回
`{"symbol": "sh517520", "name": "黄金股ETF永赢", "group": "黄金股"}` 并
修订本文件与 `pool_note`，属一行可审计变更。

## 4. 其余维度核验结论（55 只全量）

| 维度 | 结论 |
|------|------|
| 商品（期货/现货合约） | **漏网 2 只**：sh518880（黄金现货合约）、sz159985（豆粕期货型）→ 已剔除 |
| 跨境/QDII | **漏网 1 只**：sh517520（沪深港基准，见上）→ 已剔除。其余 54 只基准均为中证/国证/上证/深交所纯 A 股指数；无 fund_type=QDII 成员；无 513 段代码 |
| 债券 | 干净：无 fund_type=债券型，名称无债券关键词 |
| 货币 | 干净：无 fund_type=货币型 |
| 北交所 | 干净：全部为 sh51x/sh56x/sh58x/sz159x，无北交所代码 |
| REITs | 干净：无 |

审计遗留待核实项 sh561360"石油ETF国泰"已定性：fund_basic 全称
**国泰中证油气产业ETF**，股票型/被动指数型，基准=中证油气产业指数收益率
（A 股股票指数）→ **合规保留**，非商品（区别于原油商品/原油 QDII 基金）。

同类易混成员一并复核为股票型保留：sh512400 有色金属ETF南方（中证申万有色
金属指数）、sh562800 稀有金属ETF嘉实（中证稀有金属主题指数）、sh516150
稀土ETF嘉实（中证稀土产业指数）、sz159870 化工ETF鹏华（中证细分化工产业
主题指数）、sz159865 养殖ETF国泰（中证畜牧养殖指数）——均为 A 股行业股票
指数，与商品期货 ETF（大成有色金属期货ETF、建信易盛能源化工期货ETF 等）
性质不同。

## 5. `scripts/build_pool.py` 排除逻辑修复

- 新增 `keep_etf(item)` 作为**单一池纳入规则入口**（便于测试与复算）：
  513 跨境段常量化（`CROSS_BORDER_SEGMENT`）→ `EXCLUDE` 名称关键词
  （新增"沪深港"词序，补齐与"沪港深"的词序缺口）→ 商品关键词
  `COMMODITY = 黄金|上海金|豆粕|粮油|原油|白银|商品|期货|现货|能化|能源化工`，
  其中 `GOLD_EQUITY = 黄金股|黄金产业|黄金矿业|黄金股票` 先放行防误杀。
- 分组后 `COMMODITY_GROUPS = {黄金商品, 豆粕商品}` 主题组兜底剔除（双保险）。
- 防误杀边界（有意为之）：裸"化工"（中证细分化工=股票）、裸"能源"
  （中证能源=石油煤炭股票）、"石油"（中证油气产业=股票）、"有色"
  （中证申万有色金属=股票）均不被商品关键词命中。
- 已知边界：池内简称若不含商品/跨境关键词（如"黄金股ETF永赢"简称），
  工具层面无法识别其基准含港股；须以 fund_basic 基准证据人工复核
  （见第 7 节）。

## 6. V3 影响注记

- **生效时点**：下一信号/回测运行起生效。历史信号、历史工件、账本均
  **不追溯**（2026-09-04 首条生产信号含 sz159985 属规则冻结前的既成事实，
  留档不改）。
- **对照回测**（剔除 3 只对 V3 历史业绩的影响量化）**另行安排，不属本任务**
  （任务禁令），不据此改动任何生产规则。
- **运行时消费核对（只读不改 quant/）**：`quant/cli.py::_collect_pool` 逐
  成员读取 `cfg["pool"]` 的 `symbol/name` 并各自过门禁，无池长度假设；
  `quant/signal.py` 权重按 `1.0/len(picks)` 动态计算，`eligible_count/
  rejected_count` 动态统计；`quant/plan.py::_rows_for` 对已持有但已被剔除
  的标的回退 `own_data` 路径（data/processed 历史数据未删除），不因剔除而
  断链。**纯池成员变化的配置可被现有代码直接消费，无需任何代码改动。**
- `cmd_fetch_all` 按 `cfg["pool"]` 取数，被剔除成员自动停止更新（其已落盘
  原始数据按"原始数据不可被结果覆盖"原则保留不动）。

## 7. 未随本任务变更的相关文件（留档说明）

- `configs/pool-generated.json`：build_pool.py 的历史输出（含 518880/159985/
  517520），本任务禁联网未重新生成。下次以新规则再生成时，sh518880/sz159985
  会被自动剔除；**sh517520 因池内简称不含关键词会复入 pool-generated.json**，
  复制入 strategy.json 前须按本文件第 3 节人工核验剔除（或届时以 fund_basic
  基准证据重核）。
- `configs/_tmp_tx.json`：临时文件含同三只成员，非生产配置，不在领地内未动。

## 8. 测试结果

新增 `tests/test_v3_pool_exclusion_20260911.py`（离线零第三方依赖），
覆盖：商品名称剔除（池内简称+基金全称两种口径）、513 段与 QDII/沪深港
关键词剔除、黄金股防误杀、GROUPS 黄金股先于黄金商品匹配、商品主题组兜底、
52 只真实池成员反误杀专项（含 石油vs原油/化工vs能化/有色股票vs有色期货/
农牧食品vs豆粕粮油易混对）、strategy.json 纯删除+规则一致+pool_note 留档
的配置级回归钉。

```
$ python -m unittest tests.test_v3_pool_exclusion_20260911 -v
（13 项）
test_commodity_group_constants ... ok
test_commodity_groups_belt_removed ... ok
test_commodity_names_excluded ... ok
test_gold_equity_not_killed_by_gold_keyword ... ok
test_group_order_gold_stock_before_gold_commodity ... ok
test_513_segment_excluded ... ok
test_qdii_cross_border_name_keywords_excluded ... ok
test_sector_etfs_not_killed_by_commodity_keywords ... ok
test_specific_confusable_names ... ok
test_pool_is_pure_deletion_to_52 ... ok
test_pool_members_pass_inclusion_rule ... ok
test_pool_note_lists_commodity ... ok
test_removed_entries_only_in_documentation_note ... ok
Ran 13 tests in 0.004s
OK
```

相关既有测试（test_cli_daily / test_backtest / test_analysis）：

```
$ python -m unittest tests.test_cli_daily tests.test_backtest tests.test_analysis
Ran 52 tests in 0.267s
OK
```

## 9. 变更文件清单

| 文件 | 变更 |
|------|------|
| `configs/strategy.json` | 池 55→52（纯删除 sh518880/sz159985/sh517520）；`pool_note` 排除清单补"商品"并记本次剔除与文档指引 |
| `scripts/build_pool.py` | 排除逻辑修复：`keep_etf` 单一规则入口、商品关键词+黄金股放行、商品主题组兜底、EXCLUDE 补"沪深港"、513 段常量化 |
| `docs/experiments/v3-pool-commodity-exclusion-20260911.md` | 本文件（新） |
| `tests/test_v3_pool_exclusion_20260911.py` | 新（13 项测试） |

未动：quant/ 全部代码（只读核对）、experiments/factor_miner/、AGENTS.md、
decisions.md、configs/pool-generated.json、configs/_tmp_tx.json。
