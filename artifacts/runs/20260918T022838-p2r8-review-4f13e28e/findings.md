# P2-R8 双签独立复核报告（review run）

- review_run_id: `20260918T022838-p2r8-review-4f13e28e`
- 复核对象: 正式 run `artifacts/runs/20260918T021054-p2r8-daily-risk-d19a9c07/`、结果文档 `docs/research/exp-20260918-p2r8-daily-risk.md`、冻结配置 `configs/experiments/p2r8-daily-risk.json`、预登记 `docs/research/exp-20260918-p2r8-daily-risk-prereg.md`、R7 锚定 run `artifacts/runs/20260918T004441-p2r7-etf-exposure-d01f4e7a/`
- 复核方式: 不信任执行方自报；全部结论从产物（metrics.json / equity_curves.parquet / trades.parquet / positions.parquet / preanalysis.json）+ 原始数据（`data/raw/tushare/index_daily/20260917-r1/chunk_000300.SH.csv`、`fund_daily`、`fund_adj`）独立重算。未修改任何既有文件，未重跑策略；核验脚本在 `tmp/p2r8-review/`（r1_gates.py、r3_exposure.py、r4_anchors.py、r6b_concentration.py、r7_final.py）。
- 环境: `D:\量化\.venv\Scripts\python.exe -X utf8`，PYTHONPATH=src；复核时间 2026-09-18T02:28+08 起。

## 总判定

**"dev 0/12 全过、按预登记关闭'亚月频风控'方向"成立。** 十项核验全部 PASS。执行方自报数字与独立重算无一实质不符；所列缺陷均为文档/诊断级（见分级清单），不推翻判定。

## 逐项核验结果

### 1. 八条判据 96 格独立复算 — PASS
- 用自建实现（读 metrics 源数值 + benchmarks.B1[m].dev + B3prime_* 块）重算 12 配置 × 8 判据：96/96 格与 `metrics.gates.{cid}.dev` 一致；12 个 dev_pass 独立重算均为 False；`dev_pass_configs=[]`。
- 内部一致性：每配置 `b1m_net_cagr`/`b1m_max_drawdown` 与 `benchmarks.B1[mech_key].dev` 逐位相等（12/12）；`turnover_by_year` 60 格 `buy_notional/mean_equity == one_side_turnover`（最大误差 0）；`max_one_side_turnover == max(逐年)` 12/12。
- 失败判据分布（独立重算）：C01/C02/C03/C08→{4}；C04→{4,5,6}；C05/C06→{5,6}；C07/C12→{4,5}；C09→{5}；C10→{4,5}；C11→{2,3,6}。判据 1/7/8 对 12 配置全过；与结果文档 §3"失败判据"列逐行一致。
- 结果文档 §3 表 12 行全部数字（毛/净/B1(m)/净超额/优势年/回撤/B1(m)回撤/换手max/top1/top3）在舍入容差内逐一吻合。

### 2. C09 / C10 深查 — PASS
- **C09 确实只败判据 5**：净 CAGR 0.117895>0 ✓；净超额 0.069152≥0.02 ✓；优势年 5/5 ✓；回撤 −19.818% ≤20% 且 ≤|B1(m)| −25.979% ✓；换手 6.8056269 > 6.0 ✗（超出上限 0.8056）；top1 0.188953/top3 0.511146 ✓；对 B3′(均值 0.043501)+1pp ✓；执行率 0.996805≥0.95 ✓。其余 7 条全过，与文档一致。
- **C10 相对回撤子句差距**：max_drawdown −0.17221479314224653 vs b1m_max_drawdown −0.17184001111773028，差 0.037478pp；文档"−17.221% vs −17.184%、仅差 0.037pp"精确成立（第一子句 ≤20% 通过，败在第二子句）。C10 同时败判据 5（6.3466>6.0），与文档"4,5"一致。

### 3. 日频敞口路径独立重建 — PASS
- 原始指数文件 sha256 实测 `05aaa818…878` 与 pin 一致；2,431 行，20150105–20241231（2025+ 零行）；2015 年 244 行、dev 五年 244/244/243/244/243=1218 会话。
- 自建 T200/T60/T20c2（SMA 含 t、两日确认）、D252(10/15)/D60(8)（滚动峰含 t、insufficient→e_low）、X1（T200∧D252）逐会话状态：**C02–C09、C12 共 9 配置 × 5 dev 年的 n_sessions/n_switches/off_share/mean_exposure 全部与 `switch_stats_by_year` 一致**（C02/C09 另做 2016–2024 全窗核验，全对；C03/C05 的 e_low=0.20 路径 mean_exposure 亦吻合）；C01 恒 0.75、零切换 ✓。
- PDD（C10/C11）按登记用 run 净实例权益曲线重建自身峰状态：2016–2020 逐年全部吻合（C10: 0/0/3/7/12 次切换，off .00/.00/.7572/.3934/.4115；C11: 0/0/1/4/14，off .00/.00/.8848/.9877/.7284）；净实例与毛实例 PDD 状态路径确实分叉（parity=False 的结构性豁免成立）。
- 触发日→执行日对齐：C10 dev 22 个状态变化日、C11 dev 19 个，全部 retarget 成交日 = 变化日次一会话（t+1 开盘），无遗漏无多余。
- 见 LOW-4（n_switches 首会话不计数的口径）。

### 4. 锚定回归复核 — PASS
- 对 R7 正式 run 的 equity_curves.parquet 逐位对比（读取对比，未重跑）：C01↔C01、B1-FIX75↔B1-FIX、B1-100↔B1-100 净+毛两条曲线各 2,187 个会话点**逐点完全相等**（首 200000.00，末 305099.4569/231006.6547/256908.8916）。
- B1@100% dev 独立重算：净年化 10.4048%、累计 +63.8918%、回撤 −27.4650%，与已发表 +10.40%/+63.9%/−27.47% 偏差均 <0.0005。`metrics.anchor_regressions` 全部布尔字段为 true 与实测一致。

### 5. 换手复算 — PASS
- 从 trades.parquet 重算 C01/C09/C10 的 2016–2020 逐年 buy_notional、mean_equity（净曲线当年会话均值）、单边换手：15/15 年与 `turnover_by_year` 完全一致（如 C09 2018: 1,479,348.43/217,371.37=6.805627）。
- **风控加仓确实计入买方名义**：C09 dev retarget_buy 56 笔名义 1,469,173.97 = `risk_trades.buy_notional`，占 dev 买方名义 22.1%；C10 33 笔 1,036,696.36 = 留档值；trades 中 `kind=retarget_buy/retarget_sell` 记录在案（抽样见 C10 2018-02-12 卖/02-13 买三腿缩放）。

### 6. 集中度复算 — PASS
- 用 positions.parquet（dev 窗 = 平仓 pnl + 2020-12-31 边界持仓按 原始 close×adj_factor（asof）重估 mark）独立重算 12 配置 pnl_by_code：top1/top3 与 metrics 全部一致到 1e-9。重点配置：C04 0.2877/0.7716、C05 0.2619/0.7226、C06 0.3328/0.8890、C11 0.3954/1.0966（后者 >100% 系负盈亏代码拉低分母所致，与留档口径同源）。C04/C05/C06/C11 判据 6 均败于 top3>70%，与 gates 一致。
- 现金守恒旁证：C01（无风控腿）dev Σpnl = 权益增量 177,056.01（相对误差 1e-16）；有 retarget 配置的残差与偏差 6 披露的"按单位比例缩 entry budget"归因口径定量一致，无现金影响。
- 边界穿越持仓 36+ 腿在边界后均无 retarget（逐腿核验），行内 units/budget 即边界值，重估无近似。

### 7. 负现金与执行率 — PASS
- `max_negative_cash` 12 配置全部精确 0.0；`buys_cash_capped=0`、`risk_buys_cash_capped=0`、`risk_sells_feemin_skipped=0` 全部配置。
- dev 窗执行率 0.9950–0.9980，每配置计划腿 200–505、**恰 1 条未执行**（executed=planned−1，12/12）；风控腿计划数 = legs_planned−200 = `risk_trades.n_trades`（53/223/305/97/31/113/65/54/95），即未执行腿全部为月频 slot-busy 取消，与文档口径一致。全连续窗 0.9975–0.9990 实测与披露一致。
- 说明：现金路径本身未逐步重放（不重跑策略），以 metrics 不变量 + exec_stats + 引擎单测（缩放现金非负等 16 项）佐证，复核深度如实注记。

### 8. §0 预分析 — PASS
- 从原始指数文件独立重算：触发次数 T200/T60/T20c2/D252-10/D252-15/D60-8/X1 = 9/40/51/16/5/21/16，触发日期逐日一致（含格式）；off 占比 0.339901/0.399015/0.469622/0.435140/0.281609/0.229885/0.456486 一致；触发深度 p50/p90/max（D 族自身窗峰、SMA 族尾 252 峰）全部一致。
- 指数压力：最差单日 −8.7477%（2015-08-24）、最差 5 会话 −22.1414%（close[i]/close[i-5]，窗 2015-08-19→08-26）与 `index_stress` 逐位一致。
- 归档顺序证据：preanalysis.json/md mtime 2026-09-18 02:10:54.896/.897，早于全部策略产物（trades/curves/metrics 均为 02:11:02.2+）；代码顺序亦为先写 preanalysis 再跑策略（`p2r8_daily_risk.py` 写 preanalysis → 加载数据 → 模拟）。

### 9. 冻结与继承 — PASS
- 冻结配置 mtime 2026-09-18 01:11:00（+08）< 正式运行开始 02:10:54（=18:10:54Z）；预登记 mtime 01:10:26。运行后冻结文件未被改动（pin_checks"expected"仍记录 abe7b00b 笔误原样）。
- `inherits_from.sha256 = 902ac69b…1f77` 对 `configs/experiments/p2r7-etf-exposure.json` 实测**一致**（本次独立重算确认）。
- fund_adj pin 笔误核实：冻结文件内确为 `…abe7b00b…`；实测 `data/raw/tushare/fund_adj/20260917-r1/manifest.json` sha256 = `348d2ec4…abe8b00b…ccd4`（一字符之差）；R7 冻结配置 pin 与 R7 正式运行 manifest 记录均为 abe8b00b 实测值；R7（16:44Z）与 R8（18:10Z）读同一批次目录、哈希未变 ⇒ **数据身份解析正确且与 R7 正式运行逐字节相同**。run 生效快照（config.json）按设计保留冻结原 pin，经 pin_checks `resolution` 字段走 R7 继承解析（fail-closed），机制与偏差 10 披露一致。
- 三个继承块（u1_whitelist_frozen/universe/preflight）与 R7 配置逐字相同（字典相等）；`manifest.config_sha256=5ca75ce7…` 复现为生效配置规范化哈希 ✓。

### 10. val/test 零消费 + 统计出处 — PASS
- `gates.{cid}` 仅含 `dev` 键（12/12）；gates JSON 无 validation/test 字样；validation/test 数值块 12 配置全部留档（如 C09 val 净 −17.38%/回撤 −34.46%、test 净 +9.26%）；`advanced_to_validation=null`、`p3_candidates=[]`、`trial_count_cumulative=127`（=115+12）。
- 抽样 10 项统计"产物+字段出处 + 独立复算吻合"：① C10 相对回撤差 0.037pp（configs.C10.dev.max_drawdown/b1m_max_drawdown，复算 0.037478）；② C09 2018 单边换手 6.8056（dev.turnover_by_year + trades 重算）；③ C06 风控费用占 59.4%（dev.risk_trades.fee_share_of_total，与 trades 重算同源核验）；④ T200 dev 触发 9 次（preanalysis.json.mechanisms.T200，指数重算）；⑤ 最差单日 −8.75%@2015-08-24（index_stress，重算逐位）；⑥ B1@100 dev 三值（benchmarks.B1.100.dev，曲线重算 <0.0005）；⑦ dev 会话 1218（指数行计数）；⑧ C10/C11 2019-2020 切换数（switch_stats_by_year，权益曲线 PDD 重建吻合）；⑨ equity_curves 608,471 行、trades 189,364 行、positions 2,676 行（parquet 实测）；⑩ 11/12 配置最深回撤窗 2020-02-25→04-01、C11 在 2018（dev.mdd_window，曲线重算逐一吻合）。

## 不一致与缺陷清单

**CRITICAL**：无。

**MAJOR**：无。

**MINOR**
1. **判据 5 预登记措辞歧义（不推翻判定，须留痕）**：预登记 §4 写"换手年 ≤1200% 且**月频子限** ≤600%"，冻结配置细化为"annual one-side max ≤12.0; monthly sub-cap ≤6.0 (selection is monthly…)"，实现按"月频选币配置的年单边换手 max ≤6.0"执行。该读法与 R6/R7 冻结配置原文（"monthly configs additionally <= 6.0"）及 R6/R7 已发表结果（把 600% 上限用于年单边 max）完全一致，且预登记明示"判据数值与 R7 完全一致"——故执行的读法是先例一致读法、且偏严格方向。**敏感性**：若把 6.0 读成"逐日历月单边换手 ≤6.0"，重算 12 配置月度最大单边换手仅 0.79–1.89，全部通过判据 5，C09 将成为唯一 dev 全过并按规则进阶 validation。建议后续预登记直接写明统计周期，消除两读法。
2. **`d252_warmup_fallback_sessions_2016=8` 实为 7**：代码按 `252−244` 估算；实际 2016 年第 8 个会话（0-based 行 251）滚动窗已含 252 行，不足窗会话为 7 个。仅诊断字段/文档 §2、偏差 2 的计数错位；模拟本体用真实滚动规则（C07/C08/C12 状态逐年核验全对），无判据影响。
3. **结果文档 §9 "B3′ 220 曲线"应为 240**（12 机制 × 20 种子，实测 240 条 B3 曲线；279 条曲线总数与"12+26+1+B3"分解一致；608,471 行正确）。

**LOW**
4. `switch_stats_by_year.n_switches` 不计首会话（模拟起点 prev=None）的状态建立：按严格"较上一会话"口径 C04/C05/C09 的 2016 年应为 +1（17/17/2）。无任何判据消费 n_switches；off_share/mean_exposure 不受影响。
5. 结果文档 §5 表 C12 比值印作 1.58（metrics=1.575，report.md=1.575；1.575 属半舍入口径差异），其余 32 格一致。

**INFO**
6. `src/quant/research/etf_rotation.py` 在正式运行后（02:44）被追加了 P2-R9 段（对应 02:58 的 p2r9 冒烟 run），为 append-only、与 R8 函数无命名冲突；manifest 已锁定运行时版本哈希（当前文件 ≠ 运行时哈希属预期）。当前文件上 16/16 项 R8 单测通过；全套测试现为 243 通过（文档所称 230 为运行时点数，其后开发新增）。
7. `manifest.config_sha256` 是生效配置（含内存注入继承块）的规范化 JSON 哈希而非冻结文件哈希；冻结文件本身的 sha256 未在运行时留档——本次以"笔误原样保留 + mtime 早于运行 + pin_checks expected 记录"三重旁证冻结完整性（结论：未改动）。
8. C11 毛（2.97%）< 净（5.79%）为 PDD 费用反馈进路径的结构性结果，偏差 5 已预先披露；本次以净/毛双实例 PDD 状态路径确实分叉独立证实。
9. review 运行未触碰 docs/legacy、data/raw、data/_meta 与既有产物；无 2025+ 数据访问（指数文件 2025+ 为 0 行、读取层过滤实测有效）。

## 结论

独立复核支持正式 run 的全部关键声明：96 格判据、C09/C10 差距数字、日频敞口路径、锚定回归、换手（含风控买入计入）、集中度、零负现金、执行率、§0 预分析、冻结与继承身份（含一字符 pin 笔误的处置）、val/test 零消费均与产物和原始数据吻合。**"12 配置 dev 无一通过全部八条判据（0/12）、按预登记记录并关闭'亚月频风控'方向、validation/test 一次性承诺完整保留、累计 127 次试验 0 存活"的判定成立。** 唯一需要在后续预登记中修补的是判据 5 的统计周期措辞（MINOR-1），以及两处文档/诊断计数更正（MINOR-2/3）。

复核脚本与中间输出：`tmp/p2r8-review/`（r1_gates.py、r3_exposure.py、r4_anchors.py、r6_concentration.py、r6b_concentration.py、r7_final.py；r6_concentration.py 为含边界口径错误的初版，被 r6b 取代，留作轨迹）。
