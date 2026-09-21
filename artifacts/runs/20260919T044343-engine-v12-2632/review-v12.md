# band_engine v1.2（ETF 腿扩展）独立评审

- run_id：`20260919T044343-engine-v12-2632`
- 评审人：独立评审代理（与实现者无共享上下文）
- 日期：2026-09-19
- 评审对象 sha256（本机复算）：
  - `src/quant/backtest/band_engine.py` = `ceb7be6414280e4c5d5f37dc6ca1148a85e306b2de1a216147f67f89cc4a746d`（2,627 行）——与交付/manifest 声明一致
  - `band_engine_v1.1_snapshot.py` = `d7108c0eccdd77ff3fcbff01e7bd84bfdd2e7cad716b646e357c5644da970a0d`（2,210 行）——与 P3R2 预登记 §9 修订 5 回填 pin 一致
  - `tests/test_band_hybrid.py` = `31100f48...e68235`（764 行）
- 评审方式：difflib 全量 diff（691 行，28 个 hunk 逐个核对）、引擎关键段精读、全仓 pytest 本机复跑、两个自建场景 v1.1 快照 vs v1.2 字节对拍、R1 十进制边界 3,124 点扫描。除本评审文件外未修改任何仓库文件；验证脚本在系统临时目录。

## 结论

**APPROVE**（0 CRITICAL / 0 MAJOR / 3 MINOR，另附 5 条观察项）

范围严格限于交付声明；§8.2–8.6 语义落实与规格一致；R1/R3/R12 三项修复经独立对拍证实；零回归证据（diff + 旧测试 sha/mtime + 全仓 402 复跑 + 双场景字节对拍 + h9 金标闭环）成立。3 个 MINOR 均为测试覆盖/证据留痕缺口，不阻塞本引擎交付，但建议在混合预登记前补齐或登记。

---

## 1. 范围审计（diff v1.1 快照 vs v1.2）

方法：`difflib.unified_diff` 产出 691 行 diff、28 个 hunk，逐 hunk 与 delivery.md §2/§7.2 改动清单对照。

**逐项确认的改动（全部在声明范围内）**：模块 docstring（含 m5-d cap 段落修正——现与 §7.7-M2"决策点权益快照、越限整单作废"一致）；`from decimal import ...`；`__all__` +2；常量 `ETF_PRICE_TICK=0.001`（L205）/`ETF_DEFAULT_BAND=0.10`（L206）；`_tick_round`（L231）/`_etf_band_limit`（L245）；`_normalize_symbol_meta`（L1052）/`_normalize_dividend_events`（L1129）/`_build_preclose`（L1253）；两入口签名 `symbol_meta`/`dividend_events`；`limits_at` etf 分支（L1576）；`preclose_at`（L1562）；`eff_commission/eff_stamp_sell/eff_stamp_buy`（L1599/1608/1620）；`full_quantity_affordable` 加 `sym`（L1693）；`book_buy_fill/book_sell_fill` 费用来源替换；25% 上限预留费用 `eff_commission`；`dividend_events` 入账块（L2398-2411）；intent_step (c) ETF 路由（L1946-1985）；B 段 ETF am 守卫（L2154-2160）；stats 两键（L2485-2502）。

**未发现任何未声明的行为改动**。特别核对（均不在 diff 中，逐字节未动）：
- 股票路径：`_validate_signals`、`limits_at` 非 etf 分支、`official_close_strict`、`mark_close`、涨跌停合法性 `legal_limit`、股票锚。
- `_validate_intents`（L809）、`_Order/_FallbackOrder`、`intent_stop/intent_anchor`、`decision_step`、`sellable_shares` 函数体（L1672-1688，T+0 经头部 `is_t0` 合并生效，函数体未动）。
- 四终止（filled/expired/override/cap）、K=3 武装与顺延逻辑（`bump_streak`、deferred 分支）、现金时序（`pend_am_to_pm`/`pend_next_day`，L2419-2420 原样）、clip 会计、m1-m7 裁定语义。
- 浮点逐位性：`book_buy_fill` 的 `net = -(notional + commission + 0.0)` 对非 meta 标的与 v1.1 `-(notional+commission)` 在 IEEE-754 下逐位一致（非负数加 0.0 不变位）；经场景对拍实证（见 §4）。

范围审计结论：**通过**。

## 2. 规格符合性（§8）

- **§8.2 路由**：ETF 意图 am 决策在 `_validate_intents` 之后硬报错（L1401-1406，h1 断言 match `'15:00'`）；pm 决策 `live_d, live_s = next_day.get(day), "pm"`（L1960-1963）；股票路径保留 §7.1 am 路由（同 hunk 上下文逐字未动）。停牌（无日线行）→ `intent_anchor` 返回 None → `emissions_skipped_no_anchor`、意图保持 active、K 冻结（L1976-1981；h5 全链路验证：void_suspended、streak 冻结后恢复首个未成交 session 报 streak 1）。**符合**。
- **§8.3 成交与费用**：严格穿透走共享路径未动；ETF 涨跌停 = `_etf_band_limit(preclose, band)`（L1583-1592，无视 stk_limit 行）；免印花双侧（L1608-1616 卖侧合同优先 = R2；L1626-1630 买侧 = R3）；佣金 `max(rate×notional, min)` 逐标的（默认 = FeeModel 同式，L266-267）；tick 0.001 用于涨跌停与锚（L1985）；整手/below_min_lot 走共享 LOT=100 逻辑。**符合**。
- **§8.4 分红**：day-open 持仓（`pre_shares`，拆股前、session 前）× div_per_share 计入 `cash`（已结算，L2398-2411）；估值与 clip 成本不动（h4 以总回报恒等式 (1.97+0.05)/2.00−1 = +1% 钉死）；meta 门控 = `sym_d not in meta_rows: continue`（L1383-1392）；`dividend_events` 冻结断言双重存在（L1129 归一化内 + L1329）。§8.4 的触发判定（preclose 跳变 + fund_adj 跳变）属数据层，引擎以事件帧为输入，与"数据可依"文义一致。**符合**。
- **§8.5 混合账户**：单账本单权益（clips/cash 共享，daily 曲线统一按官方收盘估值）；单票 25% 在订单构建时按 `decision_snapshots[(decision_date, decision_session)]` 校验、越限整单作废 + 意图终止（L2126-2146；h6：E3 30% → void_cap_single_name + terminated_cap=1）；总仓位 100% 由全额资金保障隐含。**符合**。
- **§8.6 范围冻结**：diff 证实仅"pm→次 pm 路由 + 计算涨跌停/现金分红"两处扩展 + 逐标的元数据（费用覆盖字段随元数据一并声明）；无 meta 时全路径 v1.1（§4 实证）。**符合**。

## 3. R1 / R3 / R12 修复落实（独立验证）

- **R1（十进制精确 half-up）— 已落实且必要性属实**。`_etf_band_limit`（L245-256）乘积在 Decimal 中完成（`Decimal(str(preclose)) × (1 ± Decimal(str(band)))`）再 `quantize(0.001, ROUND_HALF_UP)`；`_tick_round`（L231-243）float→最短 repr→Decimal→半升。独立对拍：
  - 自找 6 个半 tick 边界案例（1.235×1.1、0.945×1.1、2.345×0.9、1.865×1.1、3.675×0.9、0.565×0.9）：引擎 6/6 等于精确十进制 half-up；
  - 网格扫描 preclose ∈ [0.1, 4.0] 步长 0.005 × band {0.10, 0.20} × 双侧 = 3,124 次计算：旧浮点法 `floor(x×1000+0.5)/1000` 与精确十进制在 **24 个真实半 tick 边界上分歧**（例：0.565×1.1 旧 0.621 / 精确 0.622；0.815×0.9 旧 0.733 / 精确 0.734），引擎与精确十进制 **0 分歧**。修复消除的是真实、非摆设的分歧。
  - 引擎行为路径（非仅单函数）：h10 以 preclose=1.705 面板经 `limits_at` → void detail 解析 [1.535, 1.876] 验证。
- **R3（etf 买侧印花豁免）— 已落实**。`eff_stamp_buy`（L1620-1633）etf 分支先于 meta `stamp_buy` 返回 0.0（合同优先对称）；h11 双向对照：etf+stamp_buy=0.001 → stamp 0、net −10,005；stock+stamp_buy=0.001 → stamp 10.0、net −10,015（防"修过头"）。与 `eff_stamp_sell` 的 etf 先行分支（L1608-1616，R2 卖侧合同优先）构成双侧对称。**落实**。
- **R12（静态入口硬拒绝）— 已落实**。`run_band_backtest` 静态分支在 `_validate_signals` 之前检查 `set(etf_meta) ∩ set(series)`（L1414-1423，`series` 由日线面板构建；信号 symbol ⊆ 面板由 `_validate_signals` 强制，故面板检查同时覆盖两个触发）。h12(a) 信号触发、(b) 仅面板触发（错误信息含 etf symbol）、对照组去 meta 后正常成交 1 笔。**落实**。

## 4. 零回归（独立复核）

1. **旧测试未动自证**：`tests/test_band_contract.py`（21）与 `tests/test_band_intents.py`（8）sha256 与 mtime 本机复算，与 delivery §1 表逐字段一致；两文件单独跑 29/29 passed。
2. **全仓 pytest 本机复跑**：`402 passed, 0 failed`（6 warnings 均为既有 polars join_asof 提示），与 `pytest_full_output_delta.txt` 及交付声明（390 基线 + 12 新增）一致；hybrid 单独 12/12。
3. **h9 金标方法学成立**：`capture_h9_golden.py` 经 importlib 加载 v1.1 快照原件捕获；金标 CSV 文件哈希 = `h9_golden.txt` 记录 = 测试内嵌常量。本评审将同一场景**现在**同时跑 v1.1 快照与 v1.2：四帧 sha 三方（v1.1 = 金标 = v1.2）全等（fills `ab6cd52d…`、events `9a9f7c87…`、daily `e6dde4e3…`、clips `036c5964…`）。
4. **自建场景对拍（超出 h9 场景的独立验证）**：
   - 场景一（3 标的、7 日、跨印花税段前、含现金竞争优先级、below_min_lot、cap 作废、拆股 corp action、意图生命周期 6 事件）：v1.1 vs v1.2 四帧 sha 全等；stats 顶层键差 = 仅 `engine_version`/`etf_leg` 两键，**任何共同键值零差异**。
   - 场景二变体（持仓中分红 6,000 = 20 手×300 入已结算现金、边界日 2023-08-28 卖出印花 0.0005 段、streak 路径）：四帧 sha 全等。
5. 逻辑闭合：无 meta 时 `div_event_map` 恒为空、`meta_rows.get` 恒 None，新增代码路径全部不可达，与实测字节相等互证。

零回归结论：**成立**。

## 5. 测试质量（h1-h12）

总体：断言钉住语义（具体日期/会话/价格/股数/净额/detail 字符串），无 tautology；h8 的 `.equals()` 全帧比较、h9 的 sha 对比、h7 的 streak 序列断言强度高。缺口如下（均为 MINOR）：

- **MINOR-1（缺测：分红日现金时序边角）**：h4 只覆盖"除息日前持有"。未测：除息日当天买入的 clip 不得息（day-open 口径的排除侧）、除息日当天卖出仍得息（登记日口径的保留侧）。该口径是 §8.4/day-open 裁定的核心语义，目前仅由代码读证（`pre_shares` 在 session 处理前采样）支撑，无断言钉住。
- **MINOR-2（缺测：混合同 session 现金竞争）**：h6 三个买单 live 在不同 session，未构造"同 pm 会话两个 ETF 买单按 m7 clip 创建序竞争现金、低优先级 void_insufficient_cash"的场景；m7 与 ETF 买单的交互无直接断言。
- **MINOR-3（证据留痕：第一轮测试文件未归档）**：delivery §7.4 声明"h1-h9 现有断言一字未改（diff 仅新增三个测试 + docstring + import math）"，但 run 目录只归档了现行 12 测试版；第一轮 9 测试版（manifest sha `ab5835cf…`）无副本可 diff，该声明不可独立复核（仅 manifest 自证）。

其他观察（不计 MINOR）：
- h5 `emissions_skipped_no_anchor >= 1` 为弱断言（可接受；后续 `not_penetrated` streak 1 断言补强了冻结证明）。
- h8 t_plus=0 卖出费用手算值（stamp 5.10）只在 delivery 文字中，测试未断言（fills 行已钉）。
- 纯 ETF 面板日历行为（R6）按裁定不改日历规则、由 runner 断言承担——引擎测试不含属裁定预期，但**混合预登记 runner 在运行前必须实际实现**"etf_default_band_symbols 空 / preclose 全覆盖 / 纯 ETF 面板=SSE 日历"三项断言，目前它们只是登记的承诺。
- `if ev_div:`（L2401）对 div_per_share=0.0 事件静默跳过（无事件行、无计数）；现金上等价于无操作，但审计轨迹上与 v1.1 股票分红 `if div:` 同式，沿旧例可接受。
- polars/pandas meta 帧内重复 symbol 行后者静默覆盖（dict 语义）；与 R14 fail-closed 精神相比略宽松，属宿主输入卫生。

## 6. 诚实性抽查（delivery.md vs 实际）

| 声明 | 抽查结果 |
|---|---|
| 引擎 sha256/2,627 行 | 一致（本机复算） |
| v1.1 快照 sha = 预登记修订 5 pin | 一致 |
| test_band_hybrid.py sha/764 行/12 测试 | 一致 |
| 旧 29 测试 sha/mtime 未动 | 一致（复算） |
| 402 passed（delta）/399（第一轮） | 复跑 402 ✓；留存输出 399 ✓ |
| h9 金标四帧 sha 与抽查数字（−10,005.00 / 8,490.75 / 198,485.75） | 与 `h9_golden.txt`/CSV 逐项一致，且 v1.1 快照现跑复现 |
| stats 仅新增两键、既有键零改动 | 场景对拍实证（共同键值零差异） |
| "未改动"清单（_validate_intents/四终止/K=3/现金时序/clip 会计等） | diff 逐项不在改动集 |
| warnings 均为既有 polars 提示 | 复跑一致 |
| `docs/`、`configs/`、`data/` 未改 | docs 相关文件 mtime（04:27 及更早）早于交付窗口（04:43-05:19），一致 |
| m5-d 挂账清偿 | docstring cap 段已改为 §7.7-M2 口径，与 v1.1 实际代码（decision_snapshots 快照校验）相符 |

未发现夸大或不实声明。第一轮测试文件未归档见 MINOR-3。

## 7. 15 项裁定落实对照（逐项）

| 项 | 裁定 | 落实复核 |
|---|---|---|
| R1 十进制精确 half-up | 需修 | ✅ 已修（L231/L245/L1583-1592）；3,124 点扫描 0 分歧、旧法 24 处真实分歧 |
| R2 卖侧合同优先 | 接受 | ✅ 按现实现（L1608-1616 etf 先于 meta stamp_sell 返回 0） |
| R3 etf 买侧印花豁免 | 需修 | ✅ 已修（L1626-1630）；h11 双向对照 |
| R4 band 缺省 0.10 | 接受 | ✅ 引擎缺省 + stats 披露（h2）；runner 侧"缺省列表为空"断言已登记为预登记项 |
| R5 preclose 回退 | 接受 | ✅ 显式列优先 + 前收盘回退（L1562-1574）；runner 侧全覆盖断言登记 |
| R6 停牌日日历 | 接受 | ✅ 日历规则零改动（无相关 hunk）；纯 ETF 面板=SSE 日历断言登记于 runner |
| R7 etf 缺省 T+1 | 接受 | ✅ `_normalize_symbol_meta` 缺省 1（保守） |
| R8 stock 行 t_plus=0 | 接受 | ✅ h8 受控场景验证类感知逐 lot 判定 |
| R9 dividend meta 门控 | 接受 | ✅ 字面规则（L1383-1392）；h4 ghost symbol 忽略 |
| R10 分红按 day-open | 接受 | ✅ `pre_shares`（session 前）；h4 恒等式 |
| R11 ETF K=3 = 3 交易日 | 接受 | ✅ streak 按 pm session 计数（h7：3 个 pm session 武装） |
| R12 静态入口 fail-fast | 需修 | ✅ 已修（L1414-1423）；h12 信号/面板双触发 + 对照 |
| R13 stats 新增键 | 接受 | ✅ 仅 `engine_version`/`etf_leg`；无 meta 时内容为 v1.1 描述，共同键零变化 |
| R14 未知 meta 字段报错 | 接受 | ✅ fail-closed（h1 断言 'unknown field'） |
| R15 股票锚不取整 | 接受 | ✅ `_tick_round` 仅在 `sym_is_etf` 分支（L1982-1985）；股票锚逐字节 v1.1 |

## 8. 发现清单汇总

- **MINOR-1**：分红日现金时序边角（ex-date 当日买入不得息 / 当日卖出得息）无测试断言（`tests/test_band_hybrid.py` h4 仅覆盖事前持有）。
- **MINOR-2**：混合账本同 session 现金竞争（m7 优先级 × ETF 买单，含 insufficient_cash 路径）无测试。
- **MINOR-3**：第一轮 9 测试版 `test_band_hybrid.py` 未在 run 目录归档，"h1-h9 断言一字未改"仅余 manifest sha 自证，不可独立 diff。

观察项：R4/R5/R6 的 runner 侧断言（缺省带列表空 / preclose 全覆盖 / 纯 ETF 面板=SSE 日历）为登记承诺，混合预登记运行前必须落实；`if ev_div:` 对 0 元分红事件不留痕；meta 帧重复 symbol 行静默覆盖；静态路径 + 纯 stock meta（费用覆盖生效）无专门测试（组成件均已分别测试）；h8 的 t0 卖出费用手算值仅见于 delivery 文字。

## 9. 判定

**APPROVE**。引擎 v1.2（sha `ceb7be64…`）与 `tests/test_band_hybrid.py`（sha `31100f48…`）可按 §8.6 进入"老流程双签后运行混合预登记"的下一触点；3 个 MINOR 建议随混合预登记的 runner/测试补齐，不阻塞本交付。本评审未修改任何被评审文件；本文件为唯一新增产物。
