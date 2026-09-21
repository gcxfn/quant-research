# band_engine v1.1 → v1.2 交付说明（契约 §8 ETF 腿扩展，零回归）

- run_id：`20260919T044343-engine-v12-2632`
- 状态：**completed**（29 旧测试原样全过 + 新增 12 混合契约测试全过 + 全仓 pytest 402 passed 零失败；含 2026-09-19 第二轮 R1/R3/R12 delta，见 §7）
- 权威规格：`docs/plans/p3-band-contract.md` §7（含 §7.7 M1-M3/m1-m7）与 §8（TBD-A/B 已回填）、§8.6 范围冻结；`docs/research/exp-20260918-p3r2-band-v1-readjudication-prereg.md` §9 修订 2/3/4、m5-a~m5-d。
- 范围遵守：仅 §8.6 两处扩展（ETF pm 决策→次 pm 路由；TBD-A 涨跌停 + TBD-B 现金分红）+ 逐标的元数据。未改 `configs/`、`docs/`、`data/`；未初始化 git；`band_engine_head.tmp` 等既有文件原位未动。

## 1. 交付物与身份

| 文件 | sha256 全串 |
|---|---|
| `src/quant/backtest/band_engine.py`（**v1.2 delta，2,627 行**，含 R1/R3/R12） | `ceb7be6414280e4c5d5f37dc6ca1148a85e306b2de1a216147f67f89cc4a746d`（sha256:16 `ceb7be6414280e4c`） |
| `tests/test_band_hybrid.py`（新增，764 行，**12 测试** h1-h12） | `31100f480604b9f0d60a723a80be0c266de07a5707037a0aaed2c6d376e68235` |
| （历史）第一轮 v1.2：2,577 行 | `46dedf57eb32900fe5ea749ee89f05db65633f470282de355e17220f45328de4`（副本 `band_engine_v1.2.py` 留档） |

零回归证明（旧测试文件逐字节未动，mtime 与改前快照一致，两轮交付后复核一致）：

| 文件 | mtime | sha256 全串 |
|---|---|---|
| `tests/test_band_contract.py`（21 测试） | 2026-09-18 23:39:23.990122300 +0800 | `aaea75007b58852c6b95bcab8d86b8c765971a2dbcde787f3e37abda74f0cdf3` |
| `tests/test_band_intents.py`（8 测试） | 2026-09-19 02:16:43.414233600 +0800 | `01393b81a56fa13fff795d2f95a305c44bfa247024e0f425597e9ad388e031d5` |

v1.1 改前快照：本目录 `band_engine_v1.1_snapshot.py`，sha256 = `d7108c0eccdd77ff3fcbff01e7bd84bfdd2e7cad716b646e357c5644da970a0d`（与预登记 §9 修订 5 回填值一致，改前已核对）。

全量 pytest：本目录 `pytest_full_output.txt`，末行 `399 passed, 6 warnings in 15.36s`（改前基线 390 = 29 band + 361 其余；390 + 9 新增 = 399，除新增文件外零失败、零改动）。warnings 均为既有的 polars join_asof sortedness 提示（p2r13 研究代码，与本交付无关）。

本目录其余文件：`capture_h9_golden.py` + `h9_golden.txt` + `h9_golden_fills/events/daily.csv`（v1.1 金标输出证据）。

## 2. 改动点清单（函数级）

**模块头**
- docstring：版本 v1.1→v1.2 + 一行变更说明（§8 ETF 腿）；新增 "v1.2 ETF-leg semantics" 节；**m5-d 挂账一并清偿**：cap 段落由"fill evaluation / last completed day marks"修正为 §7.7-M2 口径（订单构建时按决策点权益快照、越限整单作废、漂移仅记录、总仓位上限由全额资金保障隐含）。
- `__all__`：新增 `ETF_PRICE_TICK`、`ETF_DEFAULT_BAND`。

**常量**：`ETF_PRICE_TICK = 0.001`、`ETF_DEFAULT_BAND = 0.10`（§8.3）。

**新增模块级函数**
- `_tick_round(price, tick)`：半升（四舍五入）到 tick；涨跌停与 ETF 锚构造共用。
- `_normalize_symbol_meta(meta)`：dict / polars / pandas（鸭子类型，不引入 pandas import）→ 逐 symbol 校验行；字段 `asset_class`('stock'|'etf'，默认 stock)、`band`((0,0.5]，etf 缺省 0.10)、`t_plus`(0|1，缺省 1)、`commission_rate/commission_min/stamp_buy/stamp_sell`（缺省 = FeeModel / 0）；NaN→缺省；**未知字段报错**（fail-closed）。
- `_normalize_dividend_events(div)`：None/dict/polars/pandas → 校验（symbol/date/div_per_share，≥0 有限，冻结线断言）的 polars 帧。
- `_build_preclose(daily)`：可选 `preclose` 列 → symbol→(dint 数组, preclose 数组) 索引。

**入口**
- `run_band_backtest_intents(...)`：新增可选 `symbol_meta`、`dividend_events`（位于 `instruments` 之后、`*` 之前，位置/关键字均可），透传核心。
- `run_band_backtest(...)`：同样新增两个可选参数；docstring 注明 §8.2 路由属意图层（ETF 腿受支持入口 = `run_band_backtest_intents`）。

**run_band_backtest 主体**
- 头部：meta 归一化 + `etf_meta` 提取 + dividend_events 归一化；freeze 块补 `assert_frozen(dividend_events, "date", ...)`。
- instrument 映射合并（仅增量、不降级）：meta `t_plus=0` → `is_t0`；meta etf → `is_etf`（fills 列）。ETF **类别**（路由/涨跌停）只认 symbol_meta，`instruments.is_etf` 保持 v1.1 的免印花旗标语义——v1.1 型运行零回归。
- dividend 事件映射构建：仅收 meta 中且出现在事件帧的 symbol（字面规则）；`div_event_cash_total` 累计器。
- 意图模式：`_validate_intents` 之后校验 **etf symbol + decision_session='am' → BandContractError**（§8.2 禁 11:30 决策）。
- `preclose_at(sym, day)`：显式 preclose 列优先，否则前一台官方收盘。
- `limits_at(sym, day)`：**etf 分支 = 计算涨跌停** `half-up(preclose×(1±band), 0.001)`（TBD-A；对 etf 无视 stk_limit 行）；非 etf 走原 stk_limit 路径逐字节不变。
- `eff_commission(sym, notional)` / `eff_stamp_sell(sym, day, notional)` / `eff_stamp_buy(sym, notional)`：逐标的费率解析（etf 卖印花恒 0 = 合同优先；stock 可被 meta stamp_sell 覆盖，否则分段默认；stamp_buy 仅在 meta 提供时收取）。
- `full_quantity_affordable` 加 `sym` 参数（占用 = 限价×数量 + 逐标的佣金）；唯一调用点同步。
- `book_buy_fill`：佣金逐标的 + 可选 stamp_buy（缺省 0 → `-(notional+commission+0.0)` 与 v1.1 浮点逐位一致）。
- `book_sell_fill`：佣金/印花逐标的。
- 买单 25% 上限检查的预留费用改用 `eff_commission`。
- am 公司行动块：dividend_events 入账（day-open 持仓 × div_per_share → **已结算现金**；估值与 clip 成本不动；emit `corp_action_dividend`，detail 注明来源 §8.4）。
- `intent_step`：(c) 生成段重构——非 etf 意图 `live_d/live_s` 与 v1.1 逐位一致；**etf 意图：am 决策点整体跳过（含 expiry/覆盖边界自然落在 pm）**；**pm 决策 → 次日 pm**；锚获取后 etf 做 0.001 tick 半升取整（股票锚不动）。
- `process_session` B 段（K=3 兜底）：**etf 标的在 am 会话静默跳过**（兜底只在 pm 开盘执行；pm-only 合成 bar 下由缺 bar 隐含，此守卫额外覆盖宿主误供 am bar 的情形）。
- stats：仅**新增**顶层键 `engine_version = "band_engine v1.2"` 与 `etf_leg`（meta symbols / etf bands / 默认带标的 / t_plus=0 标的 / dividend 事件标的与金额 / limit 来源 / routing 描述）；既有键（含 `corp_actions` 子字典形状）零改动。

**未改动**：`_validate_intents`、`_Order/_FallbackOrder`、`intent_stop/intent_anchor`、`decision_step`、`sellable_shares` 函数体（T+0 经合并后的 `is_t0` 生效）、成交穿透语义、现金时序、clip 会计、四终止、m1-m7 全部裁定语义。

## 3. h1-h9 手算对照（数字给全过程）

测试数据全部为受控合成行情；日期 D1..D6 = 2024-01-02/03/04/05/08/09。

### h1 pm 路由（`test_h1_pm_routing`）
同一 (D1, **pm**) 决策点、同一 200,000 现金账户：
- 股票 sh.600001 buy target 10,000：锚 = D1 官方收盘 10.0 → `floor(10000/10.0/100)×100 = 1000` 股 → live (D2, **am**)（§7.1 不变）；D2 am low 9.95 < 10.0 严格穿透 → 成交 @10.0；名义 10,000；佣金 max(1.0, 5) = 5.0；净现金流 −10,005.00。
- ETF sh.510300 buy target 2,000：锚 = D1 官方收盘 2.0 → 1000 股 → live (D2, **pm**)（§8.2）；D2 pm low 1.94 < 2.0 → 成交 @2.0；净 −2,005.00。合法性用计算涨跌停 [round(2.0×0.9,3), round(2.0×1.1,3)] = [1.8, 2.2]，锚 2.0 在界内。
- 断言：两腿 fill 的 (date, session) 分别为 (D2, am) / (D2, pm)；ETF 全程零 am 会话事件；etf+am 决策帧 → BandContractError('15:00')；未知 meta 字段 → 报错。

### h2 计算涨跌停（`test_h2_computed_limits`）
- E10（meta 无 band → 默认 0.10）：D2 preclose 1.70 → up = half-up(1.70×1.10) = **1.870**，down = half-up(1.70×0.90) = **1.530**。锚（D1 收盘）2.00 > 1.870 → 整单 void_limit_out_of_range，detail 披露 "[1.53, 1.87]"（解析浮点 ≈ 断言）。
- E20（band 0.20，同价格）：up = half-up(1.70×1.20) = **2.040**，down = half-up(1.70×0.80) = **1.360**；2.00 ≤ 2.04 合法 → D2 pm low 1.99 < 2.0 成交 @2.0，1000 股。同一数据 10% 拒、20% 收 = 带宽分档证明。
- ER（band 0.10，preclose **1.234**，乘积不落在 tick 上）：up = half-up(1.234×1.1 = 1.357**4**) = **1.357**（第 4 位 4 → 舍去）；down = half-up(1.234×0.9 = 1.110**6**) = **1.111**（第 4 位 6 → 进位）。锚 1.40 > 1.357 → void，detail "[1.111, 1.357]"。两个舍入方向各一例。
- 直测 `_tick_round`：1.357 / 1.111 / 2.04 / 1.36 四例逐一对拍。
- stats：`etf_default_band_symbols == ['E10']`、`etf_bands == {'E10':0.10,'E20':0.20,'ER':0.10}`。

### h3 ETF 费用（`test_h3_etf_fees`）
- (a) min 触发：5,000 股 ×2.0 = 10,000 名义 → 佣金 max(10,000×1e-4, 5) = max(1.0, **5.0**) = 5.0；印花 0；net = −10,005.00。
- (b) min 未触发：50,000 股 ×2.0 = 100,000 名义（initial_cash 400,000，单票 100,000 ≤ 25%×400,000 过上限）→ 佣金 max(**10.0**, 5.0) = 10.0；net = −100,010.00；>5 万名义佣金守警计数 = 1。
- (c) 逐标的覆盖（rate 2e-4 / min 1.0）：10,000 名义 → max(2.0, 1.0) = **2.0**。
- 三例 `stamp_tax == 0.0`、`is_etf == True` 全部断言。

### h4 现金分红（`test_h4_dividend_events`）
- 买入 1000 股 @2.0（D2 pm）：cash = 200,000 − 2,005 = **197,995**；D2 权益 = 197,995 + 1000×2.00 = **199,995**。
- D3 除息：分红 = 0.05 元/股 × 1000 股（day-open 持仓）= **50.00** 计入已结算现金 → cash **198,045**；估值 1000×1.97 = **1,970**（原价、成本不动）；权益 = **200,015**。数据自洽：D3 preclose 1.95 = 2.00 − 0.05（除息调整），close 1.97 为原价。
- 权益分解手算：Δequity = +20.00 = 1000×(1.97−2.00) + 50 = (−30) + 50 ✓。
- 总回报恒等式：(1.97 + 0.05)/2.00 − 1 = **+1.0%** → 持仓财富 2,000×1.01 = **2,020** = 1,970（价格部分）+ 50（现金部分）✓——分红恰好桥接除息缺口，权益不含市场以外的漂移。
- 对照运行（无事件帧）：D3 cash = 197,995、权益 = 199,965 → 两运行权益差恰 **50.0**。
- 门控：`sh.999999`（不在 meta）事件被忽略（事件总数 = 1）；clips_final = 1000 股 @ 原价 1.97。

### h5 ETF 停牌（`test_h5_etf_suspension`）
面板含一只每日交易的股票仅为锚定市场日历（生产混合面板形态；见待裁定项 6）。
- 买入 1000 股 @2.0（D2 pm 成交，low 1.95 < 2.0）：cash 197,995。
- 风减卖单 (D2, pm) 决策，锚 2.00 → live (D3=01-04, pm)；D3 无该 ETF 日线行 → **void_suspended**（detail 含 "K streak frozen"，bump 未调用 = 计数冻结）。
- (D3, pm) 决策：官方收盘不存在 → `emissions_skipped_no_anchor ≥ 1`，意图保持 active（冻结）。
- (D4, pm) 决策：锚 2.00 → live (D5, pm)：D5 high 2.00 == q（触价不成交）→ not_penetrated 且 detail = "risk K streak **1**"——若 D3 被计数应为 ≥2，**冻结证明**。
- (D5, pm) 决策 → live (D6, pm)：high 2.05 > 2.00 → 成交 @2.00；net = 2,000 − 5.0 − 0 = 1,995（pm 成交 → pending_next_day）。
- 期末权益 = 197,995 + 1,995 = **199,990** ✓；ETF 全程零 am 事件。

### h6 混合账本（`test_h6_mixed_account`）
- 股票 1000 股 @10.0（D2 am，10,005）；ETF `E` weight=0.20：决策点快照 = 200,000 → 目标名义 40,000 → 20,000 股 @2.0 → 占用 40,000 + 佣金 max(4.0, 5.0)=5.0；上限检查 40,000 ≤ 0.25×200,000 ✓、现金 189,995 ≥ 40,005 ✓ → D2 pm 成交。
- ETF `E3` weight=0.30：目标名义 60,000 → 30,000 股 → 60,000 > 0.25×200,000 = 50,000 → **void_cap_single_name 整单作废**，意图终止（`terminated_cap = 1`，M2）。
- D3 混合估值：settled = 200,000 − 10,005 − 40,005 = **149,990**；positions = 1,000×10.0 + 20,000×2.0 = **50,000**；equity = **199,990**；n_positions = 2（同一账本同一权益曲线，两资产类统一适用 25%/100%）。

### h7 K=3 兜底次 pm 开盘（`test_h7_k3_fallback_pm`）
- 买入 1000 股 @10.0（D1 pm，low 9.4 < 10.0）。
- 风减卖（(D1, pm) 决策，锚 9.60）pm 会话逐日重锚未穿透：(D2,pm) high 9.2 ≤ 9.6 → streak 1；(D3,pm) high 8.6 ≤ 9.0（重锚 D2 收盘 9.00）→ streak 2；(D4,pm) high 8.3 ≤ 8.4（重锚 8.40）→ streak 3 → **armed**。
- (D4,pm) 决策 → live (D5, pm)。D5 preclose 8.10 → 计算跌停 = half-up(8.10×0.90) = **7.290**。D5 开盘 7.29 ≤ 7.29×(1+1e-4) = 7.290729 → `market_exit_deferred_limitdown`（detail 含 "open 7.2900 <= limit_down 7.2900"，**m5 用计算涨跌停**）；限价单继续工作：high 7.29 ≤ 8.10 → not_penetrated streak 4（顺延日计数，无重复计数）。
- (D5,pm) 决策 → 锚 D5 收盘 7.20 → live (D6, pm)。D6 preclose 7.20 → down = half-up(7.20×0.90) = **6.480**；开盘 6.60 > 6.480648 → **次 pm 会话开盘市价执行** @6.60：net = 6,600 − 5.0 − 0 = **6,595.00**；k3 pnl = 6,595 − 1000×7.20（前官方收盘）= **−605.00**。
- stats：armed 1 / executed 1 / deferred_limitdown_sessions 1；armed 期间 D5/D6 am 无任何 ETF 事件（兜底 am 路由走空）。

### h8 T+0 lot 可卖标志（`test_h8_t_plus_zero`）
受控场景用 stock+meta `t_plus=0` 直接验证逐 lot 类感知判定：
- t_plus=0：买入成交 (D2, **am**) @10.0（low 9.95<10.0）→ clip 取得日 D2、session am。卖单 (D2, am) 决策（锚 = am.close 10.2）→ live (D2, pm)：可卖判定 `acquired < day` 否 / 零股否 / **t_plus=0 且 clip.session(am) ≠ 判定 session(pm) → 可卖** → high 10.5 > 10.2 → **当日成交** @10.2（名义 10,200，佣金 5.0，印花 0.0005×10,200 = 5.10，net 10,189.90）。
- t_plus=1（显式）：同 clip 锁定 → void_t1_locked (D2, pm)；(D2, pm) 决策重发（锚 = 官方收盘 10.3）→ (D3, am) high 10.6 > 10.3 → 次日成交 @10.3。
- ETF pm-only 等价性：ETF clip 只会产生于 pm（当日最后会话），同日无后续会话 → t_plus 0 与 1 两次运行的 fills/events/daily **逐位相等**（断言 `.equals()`）；差异只在"同日后续会话存在"时可观测（即上述 stock 场景）。此等价性已写入模块 docstring。

### h9 零回归（`test_h9_zero_regression`）
改前用 v1.1 原件（`band_engine_v1.1_snapshot.py`）在固定小场景（买入意图 10,000 + 风减卖，6 日下跌面板，含重锚/streak/K3 兜底/印花分段路径）上捕获金标（`capture_h9_golden.py`，输出 `h9_golden*.csv/txt`），v1.2 无 meta 运行同一场景：

| 帧 | v1.1 金标 sha256 | v1.2 |
|---|---|---|
| fills.csv | `ab6cd52d3ea9939849cb9ccffa56c236148f4658e287c8a602733d795a426af2` | 一致 |
| events.csv | `9a9f7c87667707b744a649a52ebe92589cbaaafef14c6936bc81fdfb3da05482` | 一致 |
| daily.csv | `e6dde4e3e6d2243a918bf234133a6b1c0e78968f240a1afaa0b0d5de79e94714` | 一致 |
| clips_final.csv | `036c596489022bd907d78f3674280aa106f9435541d31a83cc46c6c293f95b0a` | 一致 |

抽查数字：买入 1,000@10.0（D1 pm，net −10,005.00）；K3 兜底 1,000@8.5（01-05 am 开盘，net = 8,500 − 5.0 佣金 − 4.25 印花(0.0005) = 8,490.75）；期末权益 **198,485.75**。

## 4. 测试计数

- 旧：`tests/test_band_contract.py` 21 + `tests/test_band_intents.py` 8 = **29，一字未改全部原样通过**（两轮交付后均复核）。
- 新：`tests/test_band_hybrid.py` **12**（h1-h9 第一轮 + h10-h12 第二轮 delta）。
- 全仓：第一轮 399 passed；**delta 后 402 passed, 0 failed**（390 基线 + 12 新增；最新输出 `pytest_full_output_delta.txt`，第一轮留存 `pytest_full_output.txt`）。

## 5. 接缝/待裁定项（宁多勿漏；均为实现时依文义与保守方向的选择，未静默扩大语义）

1. **计算涨跌停的舍入口径**：规格写 `round(..., 3)`；实现为四舍五入（half-up，`floor(x/tick+0.5)×tick`，交易所惯例）。对乘积恰落在 0.0005 半 tick 边界的极端值，二进制浮点表示可能与严格十进制 half-up 相差一个 tick（~1e-16 量级触发）。h2 案例避开半 tick；若裁定须十进制精确 half-up，需改实现。
2. **ETF 免印花优先级**：meta 在 etf 行上提供 `stamp_sell` 时被忽略（§8.3 合同豁免优先）。若 meta 应可覆盖合同，需裁定。
3. **stamp_buy 的类覆盖**：`stamp_buy` 是 v1.1 不存在的买方字段，实现为"meta 提供即收取（含 etf 行）"。与第 2 条的合同优先不一致（卖侧合同压制 meta、买侧无合同条款可压制）。若买方也应被 etf 豁免压制，需裁定（当前默认 0，实际不触发）。
4. **band 缺省 0.10**：§8.3 有"默认 10%"，实现为 etf 无 band 时静默默认并在 stats `etf_default_band_symbols` 披露；若应改为缺 band 直接报错（强制宿主带宽表完整、贴合"逐标的带宽表原则"），需裁定。
5. **preclose 来源与回退**：优先日线帧显式 `preclose` 列；列缺失或该行缺值时回退"前一台官方收盘"。回退值在除息日 ≠ 真实除息 preclose，会使该日计算带整体下移（兜底跌停顺延更难触发 → 开盘市价更易执行，非保守方向）。生产面板（fund_daily 带 pre_close）不走回退；是否收紧为"无 preclose 列即 etf 涨跌停不可校验（void no_limit_info）"需裁定。
6. **停牌日的日历可见性**：m3 冻结语义要求停牌日存在于运行日历（日历 = 日线帧日期并集，v1.1 规则未动）。混合面板（生产形态）由股票腿锚定日历，冻结路径成立（h5）；**纯 ETF 面板**中整日缺失的日期直接从日历消失——该日无 void 事件、在途单顺延至下一存在的 pm 会话（锚仍为停牌前收盘、streak 未计），语义等价于"挂到次一可交易日"但事件轨迹不同。是否为纯 ETF 面板合成市场日历，需裁定（当前不动日历规则以保零回归）。
7. **ETF t_plus 缺省 = 1（保守）**：T+0 属性须 meta 逐标的显式声明（§7.2"T+0 名录按品种类型清单冻结"）。若期望 etf 类缺省即 T+0，需裁定（现取更保守的 T+1）。
8. **stock 行的 t_plus=0**：允许（h8 受控场景即用它验证类感知逐 lot 判定；§7.3"可卖数量……T+0 品种为全部"按品种而非资产类）。若 t_plus 应对 stock 行忽略，需裁定。
9. **dividend_events 门控**：按任务字面实现——仅对"在 meta 中且出现在事件帧"的 symbol 生效；无 meta 时事件帧整体惰性。若应放宽为对所有持仓 symbol 生效，需裁定。
10. **dividend 入账时点**：按 day-open 持仓（拆股前、当日交易前）计息，与 v1.1 股票分红"pre-ex shares"惯例一致；与真实 A 股"股权登记日收盘持有者得息"（当日卖出得息、当日买入不得息）方向一致。
11. **ETF K=3 的时间尺度**：streak 按 session 计数不变；ETF 只有 pm 会话 → 3 个 session = **3 个交易日**（股票为 3 个半日 session = 1.5 交易日），ETF 兜底武装更慢。此为 §8.2"K=3 兜底全部适用"+"仅 pm 会话"的字面推论，确认是否为预期。
12. **静态路径 + symbol_meta**：`run_band_backtest`（静态信号）会应用 meta 的费用/涨跌停/T+0/分红，但 §8.2 路由属意图层——静态 ETF 信号将保持 v1.1 的 pm→次日 am 路由（半支持状态，docstring 已注明受支持入口为 intents）。是否改为静态入口直接拒绝 etf-meta symbol，需裁定。
13. **stats 新增键**：顶层新增 `engine_version` 与 `etf_leg`（无 meta 时也恒存在，内容为 v1.1 路径描述）；未改动任何既有键值（`corp_actions` 子字典形状不变，`test_06` 的精确断言原样通过）。若版本键不应进入 stats，可移除。
14. **未知 meta 字段 = 报错**（fail-closed，防拼写降级语义）而非静默忽略；前向兼容代价由宿主承担。若要宽松模式需裁定。
15. **ETF 锚 tick 取整范围**：仅意图生成的 ETF 重锚价做 0.001 半升取整；股票锚（含 11:30 am.close）完全不取整（"股票 = 0.01 不变"读作维持 v1.1 行为——官方收盘本身在 0.01 tick 上）。若股票锚也须显式 0.01 取整，需裁定（会改变 v1.1 字节行为，故未做）。

## 6. 诚实边界

- 本交付为引擎实现 + 契约测试，零试验消耗、零策略判定、无盈利/速度声称；2025+ 冻结区零接触（dividend_events 亦有冻结断言）。
- h1-h9 全部为受控合成小样本，仅证契约语义，不代表完整盈利验证或生产数据正确性；ETF 真实数据（etf-daily-20260919 批次）接入前的对账仍须按 §8.1 manifest 披露执行。
- m5-d（docstring cap 表述）已在本授权触点一并清偿。

## 7. delta 交付（第二轮，2026-09-19：R1/R3/R12 修复 + 12 项裁定响应）

### 7.1 裁定-响应对照（15 项）

| 项 | 裁定 | 响应 |
|---|---|---|
| R1 十进制精确 half-up | **需修** | **已修**：`_tick_round` 改为 `Decimal(str(price)).quantize(Decimal(str(tick)), ROUND_HALF_UP)`（float → 最短十进制 repr → 精确十进制 → 半升 → float）；新增 `_etf_band_limit(preclose, band, *, up)`——**乘积本身在 Decimal 中完成**（`Decimal(str(preclose)) × (Decimal(1) ± Decimal(str(band)))`）再 quantize，`limits_at` 的 etf 分支改用它；ETF 意图锚的 0.001 tick 取整同用 `_tick_round`。股票路径一字未动（股票不走这两个函数）。模块 docstring 与 §8 语义节同步更新。 |
| R2 卖侧合同优先于 meta | 接受 | 按现实现接受（etf 行 meta stamp_sell 忽略，§8.3 豁免优先）。 |
| R3 etf 双侧免印花 | **需修** | **已修**：`eff_stamp_buy` 增加 etf 分支强制返回 0.0（合同优先对称作用于买卖两侧）；stock 行 meta stamp_buy 仍可覆盖（h11 反向对照防"修过头"）。 |
| R4 band 缺省 0.10 | 接受 | 引擎保留缺省 + stats `etf_default_band_symbols` 披露；**runner 侧将断言该列表为空**（登记为预登记 runner 自检项，引擎不改）。 |
| R5 preclose 回退 | 接受 | 保留显式列优先 + 前收盘回退；**runner 侧断言面板 preclose 列全覆盖**（使回退不可达）。 |
| R6 停牌日日历可见性 | 接受 | 保留 v1.1 日历规则（日线帧日期并集）；**runner 侧断言纯 ETF 面板日期并集 = SSE 日历**。 |
| R7 etf 缺省 T+1（保守） | 接受 | 按现实现接受。 |
| R8 stock 行允许 t_plus=0 | 接受 | 按现实现接受（h8 受控场景依赖）。 |
| R9 dividend_events meta 门控 | 接受 | 按现实现接受（字面规则）。 |
| R10 分红按 day-open 持仓 | 接受 | 按现实现接受（与登记日口径一致）。 |
| R11→（编号对齐上轮 §5 第 11 条）ETF K=3=3 交易日 | 接受 | 按现实现接受（§8.2 字面推论）。 |
| R12 静态路径 fail-fast | **需修** | **已修**：`run_band_backtest` 静态分支在校验信号前检查 `etf_meta ∩ 日线面板 symbol ≠ ∅` → `BandContractError`（"static signal path does not support ETF legs…"；信号 symbol ⊆ 面板已由 `_validate_signals` 强制，故面板检查同时覆盖"出现在信号/日线"两个触发）。docstring 警告升级为硬拒绝。意图路径不受影响。 |
| R13 stats 新增键 | 接受 | 按现实现接受。 |
| R14 未知 meta 字段报错 | 接受 | 按现实现接受（fail-closed）。 |
| R15 股票锚不取整 | 接受 | 按现实现接受（v1.1 字节行为优先）。 |

### 7.2 delta 改动点清单（函数级）

1. 模块导入：`from decimal import ROUND_HALF_UP, Decimal`。
2. `_tick_round`：实现替换为 Decimal 精确半升（签名/语义不变；docstring 注明带限价须用 `_etf_band_limit`）。
3. 新增 `_etf_band_limit(preclose, band, *, up)`：精确十进制乘积 + 0.001 半升 quantize。
4. `limits_at` etf 分支：`(pc*(1.0±band), ETF_PRICE_TICK)` 浮点乘积 → `_etf_band_limit(pc, band_f, up=…)`。
5. `eff_stamp_buy`：etf 分支强制 0（R3）。
6. `run_band_backtest` 静态分支：etf-meta symbol ∈ 面板 → BandContractError（R12，置于 `_validate_signals` 之前）。
7. docstring 三处：模块变更摘要加 R1/R3/R12 一句；§8 语义节费用条改为"双侧豁免 + 精确十进制"；`run_band_backtest` docstring 警告升级为硬拒绝。

### 7.3 h10-h12 手算对照

**h10（`test_h10_decimal_half_up`）**——全部为精确十进制第 4 位小数 = 5 的半 tick 边界：
- 1.705×1.1 = **1.8755** → half-up 到 0.001 = **1.876** ✓
- 1.705×0.9 = **1.5345** → **1.535** ✓
- 3.415×1.1 = **3.7565** → **3.757** ✓
- 3.415×0.9 = **3.0735** → **3.074** ✓
- 真实分歧例（R1 危险的实证）：0.565×0.9 = **0.5085**（精确十进制）→ Decimal **0.509**；旧浮点路径 `floor(0.5085×1000+0.5)/1000`：0.5085 的浮点 ×1000 = 508.49999999999994 → floor(508.999…)=508 → **0.508**（错 1 tick）。测试同时断言两侧。
- 引擎行为路径：preclose = 1.705 的面板（band 0.10）→ 计算带 [1.535, 1.876]；锚 2.00 > 1.876 → void，detail 解析 ≈ [1.535, 1.876] ✓。
- 平台核对说明：指定的 1.705/3.415 四例在本平台的旧浮点法下恰好也落在正确侧（浮点乘积为 1.8755000000000002 / 3.7565000000000004 等，均高于边界），因此它们验证**正确性**；0.565 例验证**分歧真实存在**；Decimal 化后结果不再依赖浮点乘积落在边界哪一侧（表征无关）。
- 回归核对：h2 既有的 `_tick_round(1.234*1.1) == 1.357` 等四例直测与 E10/E20/ER 的 void detail 在 Decimal 实现下逐项不变（乘积非半 tick，±1e-16 噪声不影响舍入位），h1-h9 全部原样通过。

**h11（`test_h11_etf_stamp_buy`）**：
- ETF：meta 含 `stamp_buy: 0.001`，买入 10,000 名义（5,000 股 ×2.0）→ `stamp_tax == 0.0`（强制豁免）、佣金 5.0、net = −**10,005.00**（若未修将为 −10,015.00）。
- 对照（防修过头）：stock 行 meta `stamp_buy: 0.001` → `stamp_tax = 0.001×10,000 = 10.00`、net = −(10,000+5+10) = −**10,015.00** → 覆盖仅对 etf 类生效。

**h12（`test_h12_static_rejects_etf_meta`）**：
- (a) 静态入口 + etf-meta symbol 本身出现在信号/日线 → `BandContractError`（match "static signal path"）。
- (b) etf-meta symbol 仅在日线面板（信号只有股票）→ 同样报错，错误信息含该 etf symbol（面板触发覆盖）。
- 对照：同一静态运行去掉 meta 表 → 正常，股票买单成交 1 笔（证明拒绝只由 etf-meta 触发，非签名/数据问题）。

### 7.4 delta 后身份与证明

- 引擎 sha256：`ceb7be6414280e4c5d5f37dc6ca1148a85e306b2de1a216147f67f89cc4a746d`（sha256:16 `ceb7be6414280e4c`），2,627 行；副本 `band_engine_v1.2_delta.py`。
- `tests/test_band_hybrid.py` sha256：`31100f480604b9f0d60a723a80be0c266de07a5707037a0aaed2c6d376e68235`，764 行，12 测试。
- 旧 29 测试：两文件 sha256/mtime 与改前快照一致（§1 表，delta 后复核）；**h1-h9 现有断言一字未改**（diff 仅新增三个测试函数 + docstring 测试清单三行 + `import math`）。
- 全仓 pytest：**402 passed, 0 failed**（`pytest_full_output_delta.txt`）；h9 金标 sha 在 delta 后仍逐字节一致（hybrid 套件内含该断言，随套件通过）。
- 状态：**completed，停等复核**。
