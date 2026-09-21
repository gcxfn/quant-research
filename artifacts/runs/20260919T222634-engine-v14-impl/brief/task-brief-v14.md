# 引擎 v1.4 实施任务书（主对话 → 实施子代理，2026-09-19 22:26 冻结）

权限语义权威：`docs/plans/p3-band-contract.md` §10（已冻结）。本文件补冻结接口级设计裁定（编号 BR-*，实施中不得更改；发现语义问题或本文件未覆盖的情形一律停下、在交付报告"open seams"节列出，不得静默即兴）。本任务为引擎工程任务，不消费试验次数。

## 0. 角色、环境与边界

- 你是实施子代理。产出 = 代码 + 测试 + 三锚零回归回放 + 交付报告 + manifest。不写策略结论、不做任何 F4 实验、不碰 val、不拉数据、不 git 操作。
- 环境：Windows 10 / Git Bash；仓库根 `D:/量化`；Python `D:/量化/.venv/Scripts/python.exe`（3.11.15，polars 1.44.2）。测试命令：`D:/量化/.venv/Scripts/python.exe -m pytest tests -q`（在仓库根执行）。中文路径注意：所有路径用正斜杠、显式用 .venv 的 python。
- 可改文件（仅限）：`src/quant/backtest/band_engine.py`、新测试文件 `tests/test_band_engine_v14_zones.py`、本运行目录 `artifacts/runs/20260919T222634-engine-v14-impl/` 内的一切。禁改：docs/、README、configs/、其他 runs、data/、tools/、tests/ 既有文件。
- 基线（任务开始时核验，不符立即停）：`band_engine.py` sha256 = `84a2443ac28fe1b87e4a18f988fd38cc67cf706d577f89b6e262f11465147234082c`（v1.3 pin，2919 行）；全量测试 432 passed / 0 failed / 0 skipped。
- 运行目录：`artifacts/runs/20260919T222634-engine-v14-impl/`，结构 `manifest.json`、`delivery_report.md`、`logs/`、`outputs/`（三锚回放产物）、`scripts/`（改造 runner）、`tmp/`（工作区，含本任务书副本）。

## 1. 目标（契约 §10.1 五项）

在 band_engine 上实现 v1.4：`ladder_buy` 阶梯买入、`take_profit` 成本锚定止盈、`stop_sell` 棘轮移动止损、席位回收（成员资格进引擎）、门 8 v1.4 口径计数。全部新能力以新区模式（zones 帧）引入；**不传 zones 帧时一切 v1.3 路径逐字节不变**（三锚验证）。

## 2. 接口设计（BR-1，冻结）

- 新增可选参数 `zones`（pl.DataFrame）进入 `run_band_backtest(...)`，并加便捷入口 `run_band_backtest_zones(intents=None, zones=..., ...)` 转发。校验：`zones` 与 `signals` 互斥（同传即 raise）；`zones` 与 `intent_frame` 可并存（F4R1 = ETF 腿 intent 帧 + 个股 zones 帧同跑一份账本）；两者都为 None 且 signals 为 None 时维持现状（signals 校验自然报错，不新增行为）。
- zones 帧列（全部必填，除注明 optional）：

| 列 | 类型 | 语义 |
|---|---|---|
| signal_date | Date | 信号月边界日；必须是日线面板日历内的交易日（校验，fail-closed） |
| symbol | String | 个股代码；必须存在于日线面板；**不得是 symbol_meta 中的 ETF**（校验 raise） |
| rank | Int | 月内名次，≥1，同一 signal_date 内唯一（校验） |
| industry | String | 行业标签（IND_CAP 计数用） |
| sigma0 | Float>0 | 运行层给定，引擎不下限裁剪（S-v14-1） |
| p0 | Float>0 | 信号日官方收盘（运行层给定） |
| w_t | Float∈(0,1] | 目标权重（阶梯总量折算用） |
| ladder_offsets | String | 逗号分隔正数列表，如 "0.5,1.5,2.5" |
| ladder_fracs | String | 逗号分隔正数列表，与 offsets 等长，和=1±1e-9，如 "0.4,0.4,0.2" |
| tp1_mult, tp1_frac | Float | 第一止盈档（mult>0，frac∈(0,1]） |
| tp2_mult, tp2_frac | Float (optional) | 第二止盈档；给出时须 tp2_mult>tp1_mult、frac∈(0,1] |
| stop_mult | Float>0 | 止损系数（如 3.0） |
| invalid_mult | Float>0 | 失效线系数（如 3.5） |
| k_seats | Int≥1 | K，同一 signal_date 内必须恒定（校验） |
| ind_cap | Int≥0 | 行业上限，同月恒定（校验） |
| buffer_mult | Int≥1 | 续持阈值系数（rank ≤ buffer_mult×K 续持），同月恒定（校验） |

- 另校验：(signal_date, symbol) 唯一；signal_date 集合严格递增；zones 为空帧 raise；FREEZE 边界检查沿 `assert_frozen(zones, "signal_date", ...)`。
- 参数 `zone_priority_base: int = 1000`（run_band_backtest 关键字参数）：zones 模式下所有引擎生成订单 priority = base + rank（阶梯买/止盈/止损）；边界退出 risk 卖 priority = 10**6 + rank。zones 激活时校验 intent 帧全部 priority < zone_priority_base（防跨层竞争歧义，BR-1 裁定）。
- 结果新增：`BandResult.zones`（zone 生命周期帧；非 zones 模式为 None）与 `stats["zones"]` 统计块（仅 zones 模式出现——非 zones 模式 stats 不得新增任何键，锚回放逐字节要求）。`zones` 帧固定列至少含：signal_date, symbol, rank, industry, admitted_key(Int), phase_final(String), exit_reason(String), total_target_shares(Int), tier_filled_shares(String "a,b,c"), shares_bought(Int), wac_final(Float|null), hwm_final(Float|null), stop_line_final(Float|null), armed_events(Int), first_fill_key(Int|null)。engine_version 标签改为 `band_engine v1.4`（锚协议允许的唯一 stats 差异之一）。

## 3. 语义实施细则（BR-2…BR-12，冻结；与 §10.1 冲突时以 §10.1 为准并停下报告）

**BR-2 时间结构**：zones 为个股专用，双决策点（11:30/15:00）都 tick，股票路由沿 §7.1（am 决策挂当日 pm、pm 决策挂次日 am）。月边界固定在 (signal_date, "pm") 决策点执行，顺序：(1) 边界退出 → (2) 续持刷新 → (3) 活跃集扫描补位。expiry = 下一 signal_date + 1 历日；最后一个月 = FREEZE_END + 1 天。

**BR-3 阶梯买入**：准入时一次性计算总量 `total = floor(w_t × decision_snapshots[(signal_date,"pm")] / p0 / LOT) × LOT`（补位准入也用信号日快照，不随准入时点变）。total < LOT → 该候选 below_min_lot 计数、zone 置 done、扫描顺位继续下一位。各档 shares = floor(frac×total/LOT)×LOT，<100 的档丢弃并计 below_min_lot（S-v14-2）。每决策点对每档**剩余**股数挂普通限价买单（限价 = 决策锚 P − offset×σ0，P 取 intent_anchor 语义：am=am.close，pm=官方收盘；锚缺失即停牌 → 本决策点不挂，m3 冻结）。逐档 fill-stop：某档成交即该档完成（不重挂），不影响其余档。成交判定/现金预留/整手/25% 单一上限全部走既有买入路径（priority 排序）；单档 cap_single_name void → 该 zone 本月阶梯整体终止（v1.1 终止分类法），已成交部分继续 TP/SL。失效线：决策点检查刚结束 session 的 low < p0 − invalid_mult×σ0 → 自本决策点起取消全部未成交档（tier_invalidated 计数）；该 session 已发生的成交有效（先成交后失效，§10.1-1 冻结次序自然成立——挂单在 session 内先执行，失效判定在 session 后的决策点）。

**BR-4 止盈**：仅在持股>0 时挂单。目标价 = WAC + mult×σ0；数量 = floor(frac×当前总持股/LOT)×LOT（floor<100 则本次不挂、计数）；tp2（frac 通常 1.0）以 shares=None 全卖可卖仓位（含公司行动零股，走既有 odd_lot 路径）。挂单为普通 profit 限价卖（session high > 目标 → 按目标价成交；跳空按限价；无 k3；到期静默；expiry 沿 BR-2）。tp 成交不撤在途阶梯（§10.1-2）。同 session b1/b2 双双触价都成交（两单独立，price 不同）。
**BR-4a WAC 定义**：WAC = 本 zone 生命周期内全部**买入成交**的成交额加权平均价（Σprice×shares/Σshares，费用不计），卖出不减、不重置；公司行动份额乘数 r 触发时 Σshares×r（Σ金额不变 → WAC 正确折半）；跨月续持不清零；全清后重新准入则从零重计。（"当前所持 clip 加权价"在 FIFO 消耗下不可稳定镜像，此为可辩护简化，作 S-v14 候选接缝披露。）

**BR-5 止损**：状态按 zone 维护：首笔成交后（first_fill_key = 首笔成交所在 session 的收市决策点 key），每决策点 HWM = max(HWM, 决策锚)（停牌/锚缺失跳过=冻结，S-v14-4）；触发线 = max(历史线, HWM − stop_mult×σ0)，只升不降（跨月 σ0 刷新也经 max，线不降）。持股>0 时每决策点挂常驻触发单。**评估位置：新增 session 内评估段，置于既有 A（买单）段之前**（实现上在 process_session 开头插入 zone-stop 段；B 段 armed 兜底与本段作用于不相交的 symbol 集——armed 属 exiting zone，stop 单属非 exiting zone——次序无关，但 stop 必须先于 A 段使触发 session 的同名义阶梯档被取消不成交、先于 C 段使同 session 止盈不触发：§10.1-3 止损先于止盈）。触发：session low < 线 → 按 min(线, 该 session 开盘价) 成交（fill_type="stop"，intent="risk"），卖出全部可卖 clip（T+1 过滤）；可卖=0 且持股>0 → 无成交、直接武装兜底（stop_armed 计数）；T+1 残部 → risk_state[sym] 置 armed=True、source="stop:<signal_date>"（复用既有 B 段开盘市价兜底执行器：开盘跌停顺延、停牌冻结、缺涨跌停数据计入——S-v14-5）。触发即：zone → exiting、剩余阶梯全部取消（BR-11：契约原文"全清后终止"，实施取更保守的"触发即终止买入、席位待全清后回收"，披露）、同 session 该名义 TP 单取消。

**BR-6 同 session 次序总表**（zones 模式）：B 段 armed 兜底（开盘）→ zone-stop 触发段 → A 段买单（阶梯档）→ C 段限价卖（TP + 边界退出 risk 卖）→ D 段买单入账。与 v1.3 的 A→B→C→D 在非 zones 模式下逐字节等价（zone-stop 段整体跳过；不得移动既有段代码顺序本身——在既有 A 段前插入新段且新段 zones 为空时零操作即可保证）。

**BR-7 月边界**：(1) 上月持有但本月 rank > buffer_mult×K 或掉出名单 → 全仓退出：zone 置 exiting_boundary，每决策点重挂全卖 risk 限价卖（priority=10**6+rank，K=3 兜底沿既有 risk 语义——streak 由重挂维持，armed 后 B 段执行）；成交清零后 zone=done（不冷却——按构造不会再入本月名单）。(2) 续持（rank ≤ buffer_mult×K 且仍持有）：zone 绑定新月参数（σ0 刷新、expiry 刷新、rank/industry 更新），WAC 不变、止损线经 max 不降（BR-5），阶梯不重发（已持有即跳过扫描 (i)，无加仓原语，§10.4）。(3) 扫描补位。
**席位计数冻结**：扫描中 持有数 = 总股数>0 的 zone 符号（含 exiting_boundary 未清、含续持）；在途 = entering 且阶梯未终止的 zone。边界退出在成交前仍占席位（保守；随退出成交逐席释放——席位回收自然发生）。行业计数 = 持有 ∪ 在途 的 industry 计数（在途阶梯占行业额度）。

**BR-8 席位回收扫描**（每决策点，状态刷新后）：沿当月 rank 升序，跳过 (i) 已持有、(ii) 本月已清仓冷却（止损/止盈全清后至下一 signal_date，zone=cooling）、(iii) 行业已满（BR-7 计数）、(iv) 本月 zone 已 done/阶梯已失效或耗尽；(持有数+在途数) < k_seats 时依序准入（entering，BR-3 总量折算；below_min_lot 置 done 后继续顺位）。冷却结束=下一 signal_date 边界自然翻月。

**BR-9 全清检测与状态迁移**（zone_step，决策点）：exiting（止损）与 holding/entering 中 TP 全清（总股数=0 且曾持有）→ cooling（若因 TP-b2/止损）；exiting_boundary 清零 → done；阶梯 expiry 到期：有成交 → holding（TP/SL 继续），零成交 → done。所有迁移 emit 事件（event 名 `zone_*`）。

**BR-10 门 8 v1.4 计数**（stats["zones"]）：`stop_armed_events`（止损触发后留滞武装次数，含零可卖直接武装）；`stop_armed_resolved_fallback`（B 段兜底成交且 source 以 "stop:" 开头）；`stop_armed_resolved_other`（武装被其他成交清零，如跨月边界 risk 卖）；`stop_armed_stuck_end`（数据结束时仍 armed 且持股>0 —— 硬披露，runner 侧 stuck==0 断言用）；另披露 `tp_expired_sessions`、`tier_expired`、`tier_invalidated`、`tier_below_min_lot`（止盈到期与买入档到期/失效不入门 8 分母，单独计数——§10.1-5）。

**BR-11 接缝预披露**（写入交付报告，主对话裁定后编号 S-v14-7+）：(a) 契约"止损全清后终止 ladder"实施为"触发即终止"；(b) WAC 生命周期口径（BR-4a）；(c) 席位计数含边界退出未成交（BR-7）；(d) 补位准入总量仍锚信号日快照；(e) zones 与 intent 帧优先级基座分离（BR-1）。

**BR-12 零回归铁律**：不传 zones 时——不新增 stats 键、fills/events/daily/clips 逐字节不变、`_validate_intents` 等既有校验不动、既有测试文件零改动。stats 的 engine_version v1.3→v1.4 为锚协议允许差异。模块 docstring 增补 v1.4 change summary 段。

## 4. 契约测试（§10.3 十二项，全部手算对账）

新文件 `tests/test_band_engine_v14_zones.py`，≥25 个测试（覆盖 §10.3 的 12 个领域各至少 1 个具名测试），每个场景用合成日线+半日面板，期望值手算写进注释并对 assert。合成面板构造参考 `tests/test_band_intents.py` 与 `tests/test_band_engine_v13_corporate_actions.py` 的既有 helper 风格（自建小面板，注意 tradestatus/停牌行、stk_limit 供给或缺失路径）。十二项：①阶梯成交序与数量（单边下跌 a1→a2 逐档、剩余档继续、整手守恒）②失效线（穿透 session 成交优先、下一决策点取消）③半日重锚（am 决策挂 pm、pm 决策挂次日 am，档价随 P 刷新）④止盈双档（+2σ 卖半、+3σ 清余、同 session 双触发、跳空按限价、无 k3）⑤止盈不撤 ladder ⑥止损棘轮（HWM 先涨后跌线不降）⑦止损跳空按开盘 ⑧止损 T+1 跨日（当日买不可卖→次 session k3，计入 armed）⑨同 session 止损先于止盈 ⑩席位回收（止损清仓→rank 顺位下一位激活；冷却阻止回补；行业计数含在途；持有+在途<K 才放行）⑪月度边界（续持 rank≤2K / 退出 >2K 与补位同决策点完成）⑫现金竞争（同决策点多 ladder 按 rank 占现金，沿 m7）。另加：zones+intent ETF 腿混合冒烟（一份账本）、ETF 符号入 zones 帧 raise、priority 基座校验 raise、非交易日 signal_date raise、k_seats 月内不一致 raise。

## 5. 三锚零回归回放（沿 v1.3 程序，run 20260919T132557-engine-v13-b7e2 为模板）

- 锚 1 P3R2 C05：改造 `artifacts/runs/20260919T030640-p3r2-dev-ad9e/tmp/runner_p3r2_intents.py`（CONFIG_IDS→["C05"]、engine sha pin→v1.4 新 sha、日志名、产物写 tmp/）。比对 `outputs/` 五帧（fills/events/daily_equity/clips_final/intents）与 `artifacts/runs/20260919T030640-p3r2-dev-ad9e/outputs/` **逐字节相等**（filecmp）。
- 锚 2 混合 H2-A0：改造 `artifacts/runs/20260919T063022-hybrid-v2-2k5b/scripts/runner_hybrid_v2.py`（CONFIG_IDS→["H2-A0"]、sha pin、写 tmp/）。六产物逐字节 + stats.json 归一化相等（仅 engine_version、wall_s 差异）+ runner 内部 .equals() 校验。
- 锚 3 F3R3-A0：改造 `artifacts/runs/20260919T201500-f3r3-industry-cap-4b2e/scripts/runner_f3r3.py`（CONFIG_IDS→["F3R3-A0"]、sha pin、写 tmp/）。五帧逐字节 + stats 归一化相等。
- 三锚的源 runner 改动清单逐条写入 manifest（沿 v1.3 manifest 的 edits 字段格式）。

## 6. 交付与验收标准（§10.5）

1. 全量测试绿、零 skip：432 基线 + ≥25 新 = ≥457（同时满足契约 §10.2 "≥445" 字面）。
2. 三锚数据产物逐字节相等；stats 仅 {engine_version, wall_s} 差异。
3. 手算样例逐分对账（阶梯/止盈/止损各至少一组——测试即证据）。
4. `delivery_report.md`：改动摘要（v1.4 change summary）、sha256 before/after、测试计数、三锚结果、BR-11 接缝清单、open seams（未覆盖语义，应为空或最小）、预算耗时。
5. `manifest.json`：沿 v1.3 manifest 结构（run_id、status、wall、commands、code_identity、input_data_identity、results、non_goals_respected）。trial_accounting = 0。
6. 不 pin（pin 是主对话在双签后的步骤）；不改 docs/README。

## 7. 预算与停止规则

目标墙钟 ≤4 小时。单个问题卡住 >30 分钟：记录、绕行（留 TODO+测试 xfail 不许用——直接留下未过测试并在报告置顶披露）或停下报告。发现语义歧义/缺陷：先停下写入 open seams，不得静默取舍。任何失败运行（测试红、锚不等）都在 logs/ 留痕后重试，不改判据不改数据来"变绿"。
