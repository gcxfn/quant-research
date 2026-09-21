# 预登记：ETF pm-only 动态回放冒烟（exp-20260921-etf-pm-only-smoke）

日期：2026-09-21｜性质：**工程冒烟（链路验证）**｜试验计数消费 **0**
任务书：任务②（修正版）——ETF pm-only 路由落地与动态冒烟
决策依据：`docs/decisions/2026-09-21-etf-pm-only-routing.md`（已批准）
前置事实：`artifacts/runs/20260921T023606-etf-dynamic-identity-e41c/`（步骤 1，不重跑）

**本预登记在运行前冻结**；任何偏离在下节「执行偏差」逐条登记，不得静默改口径。
**明示：本冒烟的任何数字都不得进入策略结论**——它是"链路能否打开"的证据，
不是收益、回撤、换手或门级判定。

## 0. 目标与判据性质

用**真实日线数据**打开混合主线 ETF 防御腿在 pm-only 路由下的动态（单账本）
回放链路。判据**仅为链路正确性**（路由、撮合、费用、可卖、账本反馈），
不含任何策略有效性判据；五项全过即可交整合方，任一失败即停并登记缺口。

## 1. 冻结身份

| 对象 | 身份 |
|---|---|
| 引擎 `src/quant/backtest/band_engine.py` | v1.5，sha256 `d4b6c3764780e6dec5443174bb8fb0c1ca57ffd737da4e59069cbd3ca6735ed6`（本轮扩展后 pin；运行前后各校验一次） |
| 路由/时钟 | `execution_clock='halfday'` + `etf_routing='pm_only'`（新参数，默认 `'paired'` 零回归） |
| 数据主源 | tushare `fund_daily` 批次 `data/raw/tushare/fund_daily/20260917-r1`（三腿 chunk 逐文件哈希核对；批次目录聚合 sha256 前缀 `21b8bb5f0f05a849`） |
| 标准化 ETF 日线 | `data/processed/etf-daily-20260919/`：manifest sha256 `8b5b3fe56c0e02fd6af634bb3740c4f40c3b5f1dfabc984764433c0134eb1c8a`；`daily_2015_2024.parquet` sha256 `b7225d50523106f53fc87bf21a92f12978ecc31a7b195ed2b4cf4e39f7a0d661` |
| 半日批（**仅作隔离声明**） | `data/processed/halfday-bars-20260918/manifest.json` sha256 前缀 `2a414174b5df2eee`：本冒烟**不读其任何行**（该批对 ETF 零覆盖），引擎收到**空半日表** |
| 窗口 | 2019-01-02..2019-12-31（开发期内）；**val 2021–2024 与 2025+ 零接触** |
| 账户 | 初始权益 200,000 元；总仓 ≤100%；单只 ≤25%；佣金 max(万1×名义, 5 元)；ETF 双侧免印花；过户费不计（沿既有口径） |
| 三防御腿 | `sh.511010`（国债）`sh.518880`（黄金）`sz.159934`（黄金）；`band=0.10`、`t_plus=0`（H2-03 三腿 park 形态与契约 §8.1/§8.3 逐字继承） |

## 2. provider（唯一策略性输入，形态照 H2-03 底仓）

- **标的与目标**：三腿各 **20%**（合计 60%），**月度固定权重再平衡**。
- **决策点**：每月**最后一个交易日**的 15:00 决策点（`pm`）；其余决策点返回 `[]`。
- **动作**：按决策点账本快照 `equity_snapshot` 与各腿最新锚价（决策日官方收盘）比较：
  - 低于目标且差额可买 ≥1 手 → `buy`，`target_notional = 目标市值 − 当前市值`；
  - 高于目标 → `sell`/`intent='risk'`，`target_weight = 0.20`（引擎侧 reduce-to-target 减仓）；
  - 差额不足一手 → 不动。
- **有效性**：`expiry_date` = 下一再平衡决策日；意图由下月同标的行显式覆盖（不沿用旧订单）。
- **再发行纪律**：未成交买单在 pm-only 下半日作废（`terminated_expired_halfday`），
  由下月计划版本重新发行；风险减仓沿 K=3 pm 会话 streak 携带并在武装后按既有限价兜底成交。

## 3. 判据（五项链路，全部满足才继续）

1. **路由事件**：每笔意图 `decision_session='pm'`；每笔成交
   `decision_session='pm'`、`session='pm'`、`date` = 决策日之后的**首个交易日**。
2. **日线撮合价合法**：买单成交价 = 决策日官方收盘锚；穿透判定用执行日**日线 low**
   的严格不等式（`low < 锚`）；未穿透的挂单必须记录 `not_penetrated` 且不成交；
   不得出现"触价即成交"或取更有利价格；ETF 涨跌停按 `round(preclose×(1±band),0.001)`。
3. **费用**：ETF 双侧印花税 = 0；佣金 = max(万1×名义, 5 元)；
   逐笔手算核对 ≥2 笔 + 全窗合计核对（Σ成交行 fees_total 与手算一致）。
4. **T+0 当日可卖**：三腿在 `stats.etf_leg.t_plus_zero_symbols`、成交行 `is_etf=True`；
   卖出路径（月度减仓）对前一 pm 买入的 clip 可卖数量 = 全持仓（手算 ≥1 笔）。
   **结构性披露**：pm-only 下 ETF 无 am 会话，**同日双会话回转不可观测**，
   T+0 与 T+1 在 ETF 腿上观察等价（引擎文档同款声明）——不得为此合成 am bar。
5. **账本反馈**：`provider_calls` = 决策点数（2×窗口交易日数）、
   `dynamic_injected` = 提交行数；am 决策点 `equity_snapshot` = 现金 + 挂账桶 +
   Σ持仓×**最近已成交收盘**（手算抽检 ≥2 处，引擎侧另设逐点对账断言）。
   **另加守恒**：期末 `settled_cash + pending_am_to_pm + pending_next_day`
   = 初始权益 + Σ成交行 `net_cash_flow`（现金守恒，误差 0）。

## 4. 留痕与产物

运行目录 `artifacts/runs/<时间戳>-etf-pm-only-smoke-<短串>/`：
`manifest.json`（真实 UTC 起止、引擎 pin（运行前后）、数据 pin、命令、环境、峰值内存、产物哈希）、
`outputs/`（fills / events / daily_equity / clips_final / 决策点账本日志 /
再平衡订单表 / 判据与手算 JSON）、`report.md`（五项链路逐项结论 + 披露）、`logs/`、`tmp/`（runner + 复现脚本）。

## 5. 禁止事项（沿任务书）

- 不补 ETF 日内数据、不合成 am bar；
- 不把冒烟数字当策略证据；不读 2021–2024 或 2025+ 数据；
- 不改 F3R3 既有语义或其运行目录；不动任务①的目录。

## 6. 执行偏差

- **无口径偏离**：窗口、标的、目标权重、决策点、判据五项与上文逐条一致；
  2019 全窗 244 个交易日 × 3 腿，12 个月末再平衡决策点。
- **判据 4 的落点（运行前已在 §3-4 写明的结构性事实）**：全窗出现 8 笔减仓成交，
  判据按"减仓数量 = 决策点持仓 − 20% 目标（手算核对）"执行并通过；同日双会话回转
  仍不可观测（pm-only 无 ETF am 会话），未合成 am bar。
- **工程预检（非登记运行）**：先以 `SMOKE_WINDOW=2019-01-01:2019-04-30` 跑过
  4 个月预检（79 个交易日 / 6 笔成交 / 0 失败），用于校验 runner 与判据管线；
  预检日志留档 `logs/preflight_4month_runner.log`（冒烟 run 目录内），
  **登记运行使用全窗默认值**（`mode: smoke`，manifest 记录真实 UTC 起止）。
- **确定性**：登记运行重跑一次（同输入）产物逐字节一致，唯 `outputs/checks.json`
  因内嵌 `run_id`（目录名）不同而字节不同。
- 引擎 pin：运行时前后均为 `d4b6c3764780e6de…`（runner 内断言，前后不一致即失败）。
