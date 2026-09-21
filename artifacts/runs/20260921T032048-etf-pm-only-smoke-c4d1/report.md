# ETF pm-only 动态回放冒烟（工程链路验证，非研究结论）

运行 `20260921T032048-etf-pm-only-smoke-c4d1`｜窗口 2019-01-01..2019-12-31（244 个交易日）｜三防御腿 sh.511010、sh.518880、sz.159934 各 20% 月度再平衡
引擎 `band_engine v1.5` sha256 `d4b6c3764780e6dec5443174bb8fb0c1ca57ffd737da4e59069cbd3ca6735ed6`（`execution_clock='halfday'` + `etf_routing='pm_only'`，参数默认 `'paired'` 零回归）
预登记 `docs/research/exp-20260921-etf-pm-only-smoke-prereg.md`（运行前冻结）｜决策 `docs/decisions/2026-09-21-etf-pm-only-routing.md`

**明示：本冒烟只验证链路（路由/撮合/费用/可卖/账本），任何数字不得作为策略证据；不补 ETF 日内数据、不合成 am bar、未读 val 与 2025+。**

## 〇、运行身份与确定性

- 数据 pin：`etf-daily-20260919/manifest.json` sha256 `8b5b3fe56c0e02fd`；`daily_2015_2024.parquet` sha256 `b7225d50523106f5`；原始批次 `tushare fund_daily 20260917-r1` 目录聚合 sha256 `21b8bb5f0f05a849`；半日批 manifest 仅作隔离声明引用 （sha256 `2a414174b5df2eee`，本运行向引擎传入 **0 行** HALF 表）。
- 引擎 pin：运行前 = 运行后 = `d4b6c3764780e6dec5443174bb8fb0c1ca57ffd737da4e59069cbd3ca6735ed6`（runner 内断言）。
- 运行：引擎墙钟 0.03 s；本 run 总墙钟 0.98 s；峰值内存 0.38 GB。
- 确定性：本 run 的 8 个数据产物（fills/events/daily_equity/clips_final/decision_points.csv/fill_hand_checks.csv/ledger_hand_checks.json/rebalance_orders.csv）与同输入的前次全窗运行逐字节一致（独立复核会话逐文件比对大小与内容并重算取值）；`outputs/checks.json`、`report.md`、`manifest.json` 随判据块修订（独立复核 P3/C2 处置）与 run_id 变化。4 个月工程预检见 `logs/preflight_4month_runner.log`（非登记运行）。

## 一、五项链路判据

| 判据 | 结果 | 证据 |
|---|---|---|
| 1 路由（pm 决策 → 次日 pm 执行） | PASS | 16 笔成交全部 `decision_session=pm / session=pm / date=决策日次日`；provider 调用 488 = 2×244 决策点；提交 20 行全部 pm |
| 2 日线撮合价合法 | PASS | 成交价=决策日官方收盘锚的 0.001 half-up tick（逐笔核对）；穿透=执行日日线 low<锚 / high>锚 严格不等式（逐笔核对，违规 0）；14 笔当日收盘可给更有利价而未取；10 次 `not_penetrated` 未成交留痕；成交价全部落在计算涨跌停带内（preclose×(1±0.10)，0.001 tick） |
| 3 费用（ETF 免印花 + 万1 最低 5） | PASS | 16 笔逐笔手算一致；全窗费用 80.00 元 = 手算 80.00 |
| 4 T+0 当日可卖 | PASS | 三腿 t_plus=0 标注 + 成交行 `is_etf=True`；卖出笔数 8，减仓数量=决策点持仓−20%目标（手算）；pm-only 无 am 会话→同日回转结构不可观测（如实披露，不合成 am bar） |
| 5 账本反馈 + 现金守恒 | PASS | provider_calls=488、injected=20；逐决策点独立复算 max|Δ|=2.91e-11（0 失败）；期末现金 94030.80 = 初始 + Σ净现金流 （Δ=-1.46e-11）；每日权益恒等式全过 |

## 二、引擎运行计数（链路行为，非策略结果）

- 意图层：orders_generated 26，terminated_expired_halfday 12，terminated_expired_halfday_no_anchor None，terminated_cap 0
- 成交：16 笔（买 8 / 卖 8）；K=3 武装 0、市价兜底成交 0
- 未成交去向：{"buy": {"not_penetrated": 4}, "risk": {"session_unfilled": 6}, "profit": {}}
- 期末持仓：sh.511010 300 份、sh.518880 12700 份、sz.159934 12800 份；合计市值 121888.90 元

## 三、手算抽检留痕

- 费用：`outputs/fill_hand_checks.csv` 逐笔（名义、佣金、印花、净现金流四项手算 vs 引擎）；抽两笔列示：
  - F000001 sz.159934 buy 14100 份 @ 2.822：佣金手算 5.00 = 引擎 5.00；印花 0.0；净现金流 -39795.20 = 引擎 -39795.20
  - F000002 sh.511010 buy 300 份 @ 116.444：佣金手算 5.00 = 引擎 5.00；印花 0.0；净现金流 -34938.20 = 引擎 -34938.20
- am 时点权益（最近已成交收盘估值，手算抽检 2 处，`outputs/ledger_hand_checks.json`）：
  - 2019-02-11 am：现金 160204.80 + 挂账(0.00, 0.00) + Σ 持仓×最近成交收盘 (sz.159934:14100, sh.511010:116.83|sh.518880:2.852|sz.159934:2.833) = 200150.10 = 引擎 equity_snapshot 200150.10（Δ=0）
  - 2019-12-31 am：现金 94030.80 + 挂账(0.00, 0.00) + Σ 持仓×最近成交收盘 (sh.511010:300|sh.518880:12700|sz.159934:12800, sh.511010:119.637|sh.518880:3.361|sz.159934:3.334) = 215281.80 = 引擎 equity_snapshot 215281.80（Δ=0）
- 决策点账本全量留痕：`outputs/decision_points.csv`（488 行，逐点现金/挂账/快照/持仓/独立复算）

## 四、披露

- 半日表以 **0 行**参与本次运行（pm-only 契约下 ETF 不要求任何半日 bar）；执行 bar = 真实日线 OHLC（契约 §8.1 口径：全日区间，不做日内路径假设）。
- 2019 窗口内三腿 preclose 与前一交易日收盘逐行一致（偏差 0 条）→ 未传 dividend_events / splits / corporate_actions 为惰性选择，已核验。
- T+0：pm-only 下 ETF 每笔 live session 均为 pm，同日买卖回转结构上不可观测；判据落在标注 + 可卖数量手算，未合成 am bar。
- 本 run 的 provider 是**固定权重再平衡形态**（H2-03 底仓参照），不是策略候选；收益/回撤/换手数字不进入任何结论。

## 五、结论

五项链路判据 全部 PASS（失败 0 项）→ 混合主线 ETF 防御腿的 pm-only 动态单账本回放链路**已用真实日线数据打开**，可交整合方统一更新主计划/README/台账。
