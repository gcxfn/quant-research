# ETF 动态路径数据身份核验清单（任务②-步骤1）

运行：`artifacts/runs/20260921T023606-etf-dynamic-identity-e41c/`
日期：2026-09-21｜性质：数据身份核验（工程），零试验消费，无策略结论
状态：**FAIL-CLOSED 停止**——半日数据批对 ETF 零覆盖，按任务书"任何身份缺口记录后停止扩大"执行

## 0. 结论（一句话）

`data/processed/halfday-bars-20260918` 与 ETF 主源 `tushare fund_daily 20260917-r1` 的
标的交集为空（0/1,169），三条防御腿在半日批中各 0 行；冻结引擎在半日时钟下按契约
`halfday clock requires ETF am and pm bars` 直接 fail-closed 拒绝运行。因此**混合主线 ETF
防御腿的动态（半日时钟）回放链路无法用盘上真实数据打开**，本 run 不做任何 ETF 策略回放、
不造 am bar、不扩大范围。

## 1. 身份冻结点（运行时复算，`tmp/identity_pins.json`）

| 对象 | 身份 | 与既有登记一致 |
|---|---|---|
| 引擎 `src/quant/backtest/band_engine.py` | sha256 `bcbdd44bb855b803ed8fa2dfc4915319af4c0b79e78e7b789c0b1bfb2d75ee4a`（218,654 B） | 与任务书冻结点前缀 `bcbdd44bb855b803` **一致**（与 F3R3 §8 修复后引擎同版） |
| 半日批 `halfday-bars-20260918` | `manifest.json` sha256 `2a414174b5df2eeed4c6bd6a7cd7f9f09f9b2efc8f05673ccc4b7695812cd679`；目录聚合 `c52f3cdc3d184f484ff13cece7a6ca7a7ed589d66c4e4727bb3bc7056f6ecd93`（12 文件 / 372,833,812 B） | manifest sha 与 F3R3 预登记引用前缀 `2a414174b5df2eee` **一致** |
| ETF 标准化 `etf-daily-20260919` | `manifest.json` sha256 `8b5b3fe56c0e02fd6af634bb3740c4f40c3b5f1dfabc984764433c0134eb1c8a`；目录聚合 `75777221a8b335028bf8da60f14c59c6a3659f9d91578204308488d0f0fb7c2e`；1,017,121 行 / 1,169 只 | 与 P3 契约 §8.1 登记（1,017,121 行）**一致** |
| 原始批次 `data/raw/tushare/fund_daily/20260917-r1` | 1,170 文件（1,169 chunk + manifest），status `completed`，range 20150101..20241231，目录聚合 `21b8bb5f0f05a8494641910ffc01f7b80bd9752f22b37e0eaa2cf3d440abe8f1` | 批次只读，未改 |

三只防御腿（H2-03 参照）chunk 与批次 manifest 声明**逐字节一致**（`tmp/identity_pins.json.raw_leg_chunks`）：

| 标的 | chunk | 声明行数 | 窗口内行数 | 首/末交易日 | sha256 比对 |
|---|---|---|---|---|---|
| sh.511010 国债 | `chunk_511010.SH.csv` | 2,431 | 2,431 | 20150105 / 20241231 | match |
| sh.518880 黄金 | `chunk_518880.SH.csv` | 2,431 | 2,431 | 20150105 / 20241231 | match |
| sz.159934 黄金 | `chunk_159934.SZ.csv` | 2,431 | 2,431 | 20150105 / 20241231 | match |

## 2. 核验清单（四项，逐项判定）

### ① 符号命名 —— PASS（命名契约可桥接，但半日层无 ETF 符号）
- 半日批 symbol 为库内规范形 `sh.600000`（5,322 只），代码前缀仅
  `{000,001,002,003,300,301,600,601,603,605,688,689}`（全部股票代码段）。
- ETF 主源 symbol 同形 `sh.511010`（1,169 只），代码前缀
  `{159,160,161,162,501,502,510,511,512,513,515,516,517,518,520,530,560,561,562,563,588}`。
- **前缀交集 = ∅；符号交集 = 0/1,169（`symbol_intersection` 为空表）**。
→ 两侧命名规则兼容（`<交易所>.<6 位代码>`），若半日批含 ETF 行则无需改名；但半日层不存在
任何 ETF 符号，命名一致性无法在半日层被实际验证。

### ② 日期覆盖（am+pm 成对）—— **FAIL：ETF 0 行**
- 半日批覆盖 2,431 个交易日（2015-01-05..2024-12-31），symbol-day 时对分布
  `both = 9,241,735 / am_only = 3,427 / pm_only = 42`；逐年数值与数据集自带
  `quality.json` 逐值一致（例：2015 `both 568,547 / am_only 277 / pm_only 20`），
  说明本扫描口径可复现该批 QC。
- **ETF 行数 = 0（am 0 / pm 0）；出现过至少一行的 ETF 符号数 = 0；三只防御腿各 0 行。**
→ ETF am+pm 成对覆盖率 0%，配对率不可评估；11:30 锚、pm 锚、成交判定在 ETF 上全部无据。

### ③ 与 daily 源的交易日一致性 —— 日历层 PASS / 标的层不可评估
- ETF 日线 distinct `date` = 2,431，与半日批交易日集合**完全相同**（双向差集为空，
  `identical_calendar = true`）。
→ 交易所日历口径一致：一旦存在 ETF 半日 bar，其交易日维度可直接对齐；但标的层
`(symbol, date)` 一致性（半日批 ↔ 日线源）无法计算，因为半日批无 ETF 行可 join。

### ④ 停牌日行为 —— 有面但不可执行
- 窗内 ETF 宇宙：270 只在自身 [首, 末] 区间内存在无行日，合计 **12,881 个 symbol-day**
  （最深 sh.511950 757 天、sh.511970 649 天）；**H2-03 三只防御腿各 0 个无行日**
  （2,431/2,431，即全窗每个交易日都有行）→ 这三只本身不提供停牌样本面。
- 三腿原始 chunk 行数 = processed 行数（2,431）→ 标准化未静默丢行。
→ 引擎半日时钟的停牌语义（am 快照改用冻结最近成交收盘，合成测试 d8/d8b 覆盖）在 ETF 上
**完全无法以真实数据核验**：ETF 既无 am bar、也无停牌 bar。

### 附：仓库内日内派生数据全扫（排除"ETF 半日 bar 在别处"）
| 数据集 | 符号数 | 代码前缀 | ETF 符号 |
|---|---|---|---|
| `halfday-bars-20260918` | 5,322 | 全部股票段 | 0 |
| `halfday-1130-20260918` | 5,324 | 全部股票段 | 0 |
| `minute-feats-20260918` | 5,322 | 全部股票段 | 0 |
| `data/raw/user_minute_1m`（分钟源，抽 4 个日文件复核） | — | 全部股票段（含 `920` 北交所，未进半日批） | 0 |

与既有侦察 run `20260918T202734-etf-recon-1d83`（2,431 个分钟日文件全量 0 基金代码）
结论一致，本次为独立抽检复核。

## 3. 引擎侧 fail-closed 实证（无法绕过，`tmp/etf_dynamic_identity_probe.json`）

全部输入取**真实行**（未造任何价格或 bar）：

| 用例 | 输入 | 结果 |
|---|---|---|
| P1 | 真实 ETF 日线面板（三腿，2015-01-05..09）+ **真实股票** am/pm 半日 bar + ETF meta + `execution_clock='halfday'` | `BandContractError: halfday clock requires ETF am and pm bars` |
| P2 | 同上，但 ETF 半日帧改用契约 §8.1 形态（H2-03 runner 的 `etf_pm_bars`：单一合成 `pm` 会话 = 当日真实 OHLC） | 同一拒绝（缺 am 会话） |
| P3 对照 | 股票面板 + 其真实 am/pm bar + halfday 时钟 | 正常跑完（0 意图，权益 200,000）→ 探针 harness 健全，失败绑定在 ETF 缺 bar |
| P4 对照 | 同 §8.1 帧 + **legacy** 时钟 + 1 笔真实价 ETF 买单（pm 决策） | 正常跑完：518880 于 2015-01-08 pm 成交 8,100 份 @2.445、佣金 5 元；结算现金 180,190.5、权益 199,946.4（手算一致：8,100×2.445+5=19,809.5；持仓市值 8,100×2.439=19,755.9） |

→ 差距被定位到 **halfday 时钟**（契约 §8.2 的 pm-only 单会话 ETF 形态在 legacy 下可用，
在 halfday 时钟下被 guard 结构性拒绝），而不是 ETF 数据本身缺失成交语义。

## 4. 阻塞、解封选项与停止纪律

未执行、需用户裁定的三条路径（任一都需预登记与新 pin/新批次）：

- **(a) 补 ETF 日内数据源**：拉取并标准化真实 ETF am/pm bar（新批次 + 口径桥接 + 预登记）。
  现状：ETF 分钟补源**未授权**（P3 契约 §6/§7.4 明文"ETF 分钟数据维持不回补"）。
- **(b) 引擎扩展**：让 halfday 时钟对 ETF 表达"pm-only 单会话"路由（现 guard 与
  `sym_is_etf and not halfday_clock` 路由写死要求 am+pm 成对）——需新 pin + 双签 + 三锚零回归。
- **(c) 混合主线退回 legacy 时钟**：即 H2-03 已验证形态，代价 = ETF 腿无 11:30 决策点、
  无半日重发、无半日时钟账本反馈。

停止纪律执行情况：未运行任何 ETF 策略回放；未合成/外推 am bar；未触碰 val（2021–2024）
与 2025+ 冻结区（本 run 仅用 2015-01-05..09 的真实行情做路由/守卫探针）；试验台账零消费。

## 5. 证据文件

| 文件 | 内容 | sha256 |
|---|---|---|
| `tmp/identity_pins.json` | 引擎/数据集/批次身份复算 | `1de3e493628798fcb39575946003082030d4fb0a8604cd6d3f16a64341dbb4f7` |
| `tmp/etf_identity_scan.py` / `.json` | 四项核验扫描（命名/覆盖/日历/停牌） | `1ec57cf3e92210f838471c463ebfaf5740bcce45e56177d435259348dc909203` / `0f01e1372afc72e7b3c317cb307ace3139c27d4ab581de901745b52dbaeffeff` |
| `tmp/etf_dynamic_identity_probe.py` / `.json` | 引擎守卫 fail-closed 实证 P1–P4 | `92874a5105492d5de9a66bdb27439157f4f4f9d474acc602e63096fd387b9c02` / `b81010ffed2c1dd32747e7d0353a1ea6bcc70707cd34763f312f80cf8fd94ad1` |

复现命令（`PYTHONPATH=src`，工作目录 `D:/量化`）：

```
.venv/Scripts/python.exe artifacts/runs/20260921T023606-etf-dynamic-identity-e41c/tmp/identity_pins.py
.venv/Scripts/python.exe artifacts/runs/20260921T023606-etf-dynamic-identity-e41c/tmp/etf_identity_scan.py
.venv/Scripts/python.exe artifacts/runs/20260921T023606-etf-dynamic-identity-e41c/tmp/etf_dynamic_identity_probe.py
```

环境：Python 3.11.15、polars 1.44.2、numpy 1.26.4（`.venv` 非 editable）。
三个脚本重跑 exit 0 且输出字节确定（`identity_pins.json`、`etf_dynamic_identity_probe.json` 重跑哈希不变；`etf_identity_scan.py` 已改为排序输出后同样不变）；实测墙钟 5.1 s + 2.3 s + 5.0 s = 12.3 s。
