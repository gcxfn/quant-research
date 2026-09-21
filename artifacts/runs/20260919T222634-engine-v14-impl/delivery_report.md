# 引擎 v1.4 交付报告 —— 分档建仓 ladder_buy + 止盈 take_profit + 止损 stop_sell + 席位回收 + 门 8 v1.4（§10.3 A–C）

- 运行 `20260919T222634-engine-v14-impl`；状态 **completed**；试验次数消费 **0**（引擎工程任务）；val 零接触；无 git 操作；无新数据拉取。
- 权威规格：`docs/plans/p3-band-contract.md` §10（语义权威）+ §7（v1 基础语义）+ 冻结接口裁定 BR-1…BR-12（本运行 `brief/task-brief-v14.md`）。
- 引擎：`src/quant/backtest/band_engine.py`；基线 v1.3 sha256 `84a2443ac28fe1b87e4a18f988fd38cc67cf706d577f89b6e262f11465147234082c`（开工亲验一致，2919 行）→ **v1.4 sha256 `56f5fec4d5491fc6dd0cb7110f8e27e54b783889f622d9cbadb98cc8264fe5ad`**（3910 行；**尚未 pin**——pin 属 §10.5-4/5，由主对话复核后执行）。

## 一、实际改动明细（A 项）

全部改动集中在 `src/quant/backtest/band_engine.py` + 新测试文件；docs/README/configs/data/既有 tests/tools/其他 runs 零改动。

1. **接口**（BR-1）：`run_band_backtest` 追加 keyword-only `zones=None` 与 `zone_priority_base=1000`；新增便捷入口 `run_band_backtest_zones(zones, daily, halfday, stk_limit, …, *, intents=None, …)` 转发。校验：zones 与 signals 互斥（raise）；zones 与 intent_frame 可并存（混合账本）；zones 激活时 intent 帧全部 priority < zone_priority_base（否则 raise）；zone 顺序（zone 层 base+rank，边界退出 10^6+rank）与意图层基座分离。`BandResult` 新增 `zones` 字段（非 zones 模式为 None）。
2. **zones 帧校验**（`_validate_zones`，模拟交易前 fail-closed）：16 必需列 + 可选 tp2 双字段（半给 raise）；空帧 raise；signal_date 必须在日线面板日历内（接缝 S-11）；symbol 必须在面板且不得是 symbol_meta 中的 ETF；rank≥1、(signal_date,rank) 唯一、(signal_date,symbol) 唯一；signal_date 首现顺序严格递增；sigma0/p0>0（引擎不下限裁剪，S-v14-1）、w_t∈(0,1]；ladder 逗号列表解析（等长、全正、fracs 和=1±1e-9）；tp1_mult>0、tp1_frac∈(0,1]；tp2_mult>tp1_mult；stop_mult/invalid_mult>0；k_seats≥1、ind_cap≥0、buffer_mult≥1 且三者同 signal_date 内恒定；冻结断言 ≤2024-12-31。
3. **月边界**（BR-2/BR-7）：固定在 (signal_date,"pm") 决策点，次序 = 冷却翻月 done → 逐 zone（续持 rank≤buffer_mult×K 且仍持有：刷新 rank/industry/σ0/p0/expiry，WAC 不变，止损线经 max 不降，旧阶梯按 §10.1-1 #2 "同名义覆盖" 终止（未成交档计 tier_expired）、不重发；否则 entering→done(month_replaced) / holding→exiting_boundary）→ 席位扫描补位。
4. **阶梯买入**（BR-3）：准入一次性总量 `floor(w_t×snapshot(signal_date,"pm")/p0/LOT)×LOT`（补位准入同锚信号日快照，S-4/BR-11d）；total<LOT → done(below_min_lot)、扫描顺位继续；各档 `floor(frac×total/LOT)×LOT`、<100 丢档计 tier_below_min_lot（S-v14-2）；每决策点按每档**剩余股数**挂普通限价买（限价 = 决策锚 P − offset×σ0，P 走 intent_anchor 语义：am=am.close、pm=官方收盘；锚缺失不挂，m3）；成交判定/现金预留/整手/25% 上限全走既有买入路径；单档 cap_single_name void → 该 zone 本月阶梯整体终止（v1.1 分类法，计 tier_cap_voided），已成交部分继续 TP/SL；失效线：决策点检查刚结束 session 的 low < p0−invalid_mult×σ0 → 取消全部未成交档（tier_invalidated），当 session 成交优先（次序冻结自然成立）。
5. **止盈**（BR-4/BR-4a）：WAC = zone 生命周期全部 zladder 买入成交额加权价（费用不计；卖出不减不重置；公司行动乘数 r → Σshares×r、Σ金额不变 → WAC 正确折算，v0 送转与 v1.3 份额变换两条路径都挂钩；跨月续持不清零；全清后重新准入从零重计）。每决策点重挂：b1 = WAC+mult×σ0、`floor(frac×总持股/LOT)×LOT`（floor<100 不挂、计 tp_below_min_lot）；b2 按冻结文本 shares=None 全卖可卖（含零股；见接缝 S-5）；普通 profit 限价卖、跳空按限价、无 k3、到期静默（session_expired 计 tp_expired_sessions）；T+1 未到 → 既有 void_t1_locked 路径。止盈成交不撤在途阶梯（§10.1-2）。
6. **止损**（BR-5）：首笔成交后（first_fill_key = 成交 session 的收市决策点 key）每决策点 HWM = max(HWM, 决策锚)（停牌冻结，S-v14-4）；触发线 = max(历史线, HWM−stop_mult×σ0) 只升不降（跨月 σ0 刷新经 max）；新增 **zone-stop 评估段插在既有 A（买单）段之前**（process_session 顶部，非 zones 零操作，不移动既有段代码，BR-6）：session low < 线 → 按 min(线, 开盘) 成交（fill_type="stop"、intent="risk"）卖出全部可卖 clip；同 session 该名义阶梯档与 TP 单从 live 列表移除（止损先于止盈，§10.1-3）；可卖=0 且持股>0 → 直接武装；T+1 残部 → risk_state 置 armed、source="stop:<signal_date>"，复用既有 B 段开盘市价兜底执行器（跌停顺延/停牌冻结/缺涨跌停计入，S-v14-5）。
7. **席位回收**（BR-7/BR-8）：每决策点扫描——持有数 = 总股数>0 的 zone 符号（含 exiting_boundary 未清与止损 exiting 残部，保守，BR-11c）；在途 = entering 且阶梯未终止；行业计数 = 持有∪在途（在途占行业额度）；沿当月 rank 升序、跳过当月已有 zone 的符号（covering 已持有/冷却/已 done）与行业已满者，持有+在途 < k_seats 时依序准入；清仓（TP 全清/止损全清）→ cooling 至下一 signal_date 翻月 done，冷却结束自然解锁回补。
8. **门 8 v1.4**（BR-10）：`stats["zones"]` 仅 zones 模式出现——stop_armed_events / stop_armed_resolved_fallback / stop_armed_resolved_other / stop_armed_stuck_end（硬披露）+ tp_expired_sessions / tier_expired / tier_invalidated / tier_below_min_lot（另加 tier_cap_voided、tp_below_min_lot 两项披露计数）；k3 既有块保持 v1.3 口径不动。
9. **零回归铁律**（BR-12）：全部新路径以 `zone_engine` 门控；不传 zones 时 stats 键集与 v1.3 完全一致（仅 engine_version 标签 v1.3→v1.4，锚协议允许），既有校验/段代码顺序不动；模块 docstring 增补 v1.4 change summary。三锚回放（下节）证明五/六帧逐字节相等。

## 二、测试清单与结果（B 项）

新文件 `tests/test_band_engine_v14_zones.py`（26 项，全部通过；sha256 `2fc1015fca4dd28194ff4fccf3c0886c5b6e1b9ff7f88f0017520e71497d5466`）。合成面板全部内联构造并明确标注 synthetic；期望值手算写入注释并对账；价格限用合成 ±90% 带宽（真实 ±10% 限价合法性路径由既有 v1.x 测试覆盖）。

| # | 测试 | 覆盖（§10.3 十二项） |
|---|---|---|
| 1 | t01_ladder_sequence_and_lots | ①单边下跌 a1→a2→a3 跨 session 逐档成交 9.5/7.8/5.5、400/400/200 整手守恒；WAC=(3800+3120+1100)/1000=8.02；现金 191965 到分；zones 帧固定列 |
| 2 | t03_halfday_reanchor | ③a3 未成交档限价序 7.5（pm 决策锚 10.0）→ 6.8（am 决策锚 9.3）→ 成交 5.5（pm 决策锚 8.0）；am→当日 pm、pm→次日 am 路由 |
| 3 | t04_tp_double_tier_same_session | ④b1 +2σ 卖半（200@11.5）→ b2 +3σ 清余；D4am 双双触价同 session 成交（100@11.5 + 100@12.5）；现金 200877.65 |
| 4 | t05_tp_gap_fills_at_limit | ④跳空：开盘 12.0 > 目标 11.5 → 按限价 11.5 成交 |
| 5 | t06_tp_no_k3_silent | ④无 k3：market_fallback=0、k3 armed/executed=0；tp_expired_sessions=3 手算（D2pm 对为 T+1 作废 void_t1_locked 非到期）；止盈到期静默不入门 8 分母 |
| 6 | t07_tp_keeps_ladder | ⑤b1 成交（D3pm 200@11.5）后 a2 仍成交（D4am 400@10.0）；新 WAC 9.75 重锚 TP1→11.75 |
| 7 | t08_stop_ratchet | ⑥HWM 9.3→10.5 后回落：线 = max(7.5, 跌后 4.7) = 7.5 不降；lows 未穿线不触发；hwm_final/stop_line_final 断言 |
| 8 | t09_stop_gap_open | ⑦开盘 7.0 低于线 7.5 → 按开盘成交 7.0 非线价；全清→cooling(stop_cleared)、无武装 |
| 9 | t10_stop_t1_armed_fallback | ⑧买入当日触发：可卖 0 → 直接武装（stop_armed_events=1）、当日 deferred_t1locked、次 session 开盘 5.9 兜底成交 400；resolved_fallback=1；现金 198548.82 |
| 10 | t20_stop_partial_sellable_residual | ⑧部分可卖：止损卖可卖 400@6.3、T+1 残部 600 武装→D4am 开盘 6.1 兜底；现金 197931.91 |
| 11 | t11_stop_before_tp_same_session | ⑨同 session low 7.4<线 7.5 且 high 11.6>TP 目标 11.5：止损段先于 C 段 → TP 单取消不成交，仅止损 400@7.5 成交 |
| 12 | t12_seat_recovery_after_stop_cooling | ⑩k=1：A 止损全清→(D3,am) 决策点检测 cooling→同决策点扫描准入 B（A 因当月已有 zone 不回补——冷却阻止）；B a1 当日 pm 成交 200@19.5 |
| 13 | t13_industry_count_inflight | ⑩ind_cap=1：A 在途（未成交）已占 X 行业额度 → B(X) 跳过、C(Y) 准入 |
| 14 | t14_seat_cap_hold_plus_inflight | ⑩k=2：A+B 占满 → C 永不准入 |
| 15 | t15_month_boundary_exit_continue_refill | ⑪月边界：A rank5>4 → exiting_boundary（risk 卖 10^6+1，F2am 400@9.3 成交→done boundary_cleared）；C rank1≤4 → 续持（WAC 4.5 不变、σ0→2 → TP1 重锚 8.5）；A 清仓释放席位后 B 才准入（(F2,am)）；tier_expired=6 手算 |
| 16 | t16_cash_priority_m7 | ⑫同决策点 5 条 ladder 现金竞争（m7）：rank1–4 全额成交（各 23565），rank5 a1 10455 成交、a2/a3 insufficient_cash 作废；成交按 (priority,symbol) 排序；现金 285 到分 |
| 17 | t17_mixed_etf_intent_one_ledger | 附加：zones 个股腿 + intent ETF 腿同一账本（ETF 2000@5.0 免印花、个股 400@9.5），现金 186190；ETF 符号不进 zones |
| 18 | t18_ladder_expiry_br9 | BR-9：零成交阶梯 expiry（下一 signal_date+1）到期 → 3 档取消、zone done(ladder_expired)；末月无下一 session 同样到期；tier_expired=6 |
| 19 | t19_below_min_lot_scan_continues | BR-3/S-v14-2：w_t=0.001 → total<LOT → done(below_min_lot)，扫描继续准入 B |
| 20 | t21_stats_shape_zero_regression | BR-12：非 zones 运行无 stats["zones"] 键、BandResult.zones=None；zones 运行含 BR-10 全部键 |
| 21 | t22_determinism | 同输入两次 → 五帧 + zones 帧 bit-identical、stats JSON 相等 |
| 22 | t23_raise_etf_symbol_in_zones | 校验：ETF 符号入 zones 帧 raise |
| 23 | t24_raise_priority_base | 校验：intent priority ≥ zone_priority_base raise；< 基座通过 |
| 24 | t25_raise_signal_date_not_calendar_day | 校验：signal_date 不在面板日历 raise |
| 25 | t26_raise_k_seats_inconsistent | 校验：k_seats/ind_cap/buffer_mult 月内不一致各自 raise |
| 26 | t27_raise_validation_misc | 校验：zones+signals 互斥、空帧、重复 (sd,symbol)、重复 rank、fracs 和≠1、tp2 半给、rank<1、ladder 列表长度不匹配、zones 非 DataFrame |

**全量测试**：`python -m pytest tests -q` → **458 passed / 0 failed / 0 skipped**（基线 432 + 新增 26，满足任务书 ≥457 与契约 §10.2 "≥445"）；6 条 warning 为无关研究模块的 polars join_asof 既有提示。

## 三、锚回放证据（C 项，均不传 zones）

改造方式沿 v1.3 模板：源 runner 复制进本运行 `tmp/`，只改引擎 sha pin、CONFIG_IDS（单锚范围）、日志名、manifest/report 写入重定向 tmp/（diff 全部核验，见 manifest edits 字段）。

### 锚 1：P3R2 C05（源 `artifacts/runs/20260919T030640-p3r2-dev-ad9e/`）

- 改动：CONFIG_IDS→["C05"]、引擎 sha pin→v1.4、日志名、manifest/report 重定向、PANEL_BY_CFG setdefault（R16 指标含全部 8 配置，共 8 行 diff）。
- 结果：**C05_fills / C05_events / C05_daily_equity / C05_clips_final / C05_intents 五个 parquet 与源 outputs 逐字节相等**（sha256 逐一比对一致）；32s 墙钟、峰值 RSS 4.02 GB；身份 pin 全部 match=true（含新引擎 sha，见 `tmp/anchor1_manifest.json`）。

### 锚 2：混合族 H2-A0（源 `artifacts/runs/20260919T063022-hybrid-v2-2k5b/`）

- 改动：CONFIG_IDS→["H2-A0"]、sha pin、日志名、重定向（8 行 diff）。
- 结果：**H2-A0 五个 parquet + dividend_events.csv 与源 outputs 逐字节相等**；runner 内建回归断言（H2-A0 四帧 .equals P3R2 C05 + net_cagr 1e-12 一致）全 True（日志留痕）；43s、峰值 RSS 2.38 GB。
- `H2-A0_stats.json` 归一化后**仅两个字段不同**：`engine_version`（v1.2→v1.4 标签）、`wall_s`（墙钟）。其余全部键值逐字节一致。

### 锚 3：F3R3-A0（源 `artifacts/runs/20260919T201500-f3r3-industry-cap-4b2e/`）

- 改动：CONFIG_IDS→["F3R3-A0"]、sha pin、日志名、重定向、F3R1 前置断言的 sha 从本 replay pin 改回 F3R1 实际产线 sha（84a2443a 前缀——该断言校验的是"历史 F3R1 composite 由 v1.3 引擎产出"，与本 replay 无关；共 9 行 diff）。
- 结果：**F3R3-A0 五个 parquet 与源 outputs 逐字节相等**；`F3R3-A0_stats.json` 归一化后仅 `engine_version`（v1.3→v1.4）与 `wall_s` 两字段不同；38s、峰值 RSS 2.61 GB。

## 四、接缝登记

### BR-11 预披露接缝（照任务书抄录，待主对话裁定后编号 S-v14-7+）

- (a) 契约"止损全清后终止 ladder"实施为**"触发即终止"**：触发时 zone→exiting、剩余阶梯与同 session TP 单立即取消，席位待全清后回收。
- (b) **WAC 生命周期口径**（BR-4a）：Σ 买入成交额 / Σ 买入股数；卖出不减不重置；公司行动乘数折算 Σshares；跨月续持不清零；全清后重新准入从零重计。（"当前所持 clip 加权价"在 FIFO 消耗下不可稳定镜像，此为可辩护简化。）
- (c) **席位计数含边界退出未成交**（BR-7）：exiting_boundary 未清与止损 exiting 残部仍占席位（保守），随退出成交逐席释放。
- (d) **补位准入总量仍锚信号日快照**（BR-3）：`decision_snapshots[(signal_date,"pm")]` 固定，不随准入时点变。
- (e) **zones 与 intent 帧优先级基座分离**（BR-1）：intent priority < zone_priority_base（默认 1000）≤ zone 订单（base+rank）< 边界退出（10^6+rank）。

### 实施中新发现（编号建议 S-v14-7+，未静默取舍，逐条列出证据与影响）

- **S-7（候选）阶梯 expiry 与月边界的同点次序**：expiry = 下一 signal_date + 1 历日；在 (下一 signal_date, "pm") 决策点 `live_d ≥ expiry` 先行触发（未成交档计 tier_expired、entering 区 done），随后月边界转换。两机制同点发生时计数归 expiry。数据结束（无下一 session，live_d=None）同样视为到期：entering→done(ladder_expired)、holding→阶梯终止（TP/SL 继续）。最后一个月 expiry = FREEZE_END+1 在数据内不可达，故其 zone 的阶梯在数据结束日经 live_d=None 路径到期——语义上等价于"不会再有成交"。
- **S-8（候选）续持区旧阶梯按"同名义覆盖"终止**：BR-7"阶梯不重发、无加仓原语"+ §10.1-1 终止 #2 → 续持时旧阶梯未成交档取消（计 tier_expired），新月份不产生新档。被放弃的另一种读法（旧档带新 σ0 续挂）会构成加仓原语。
- **S-9（候选）exiting/exiting_boundary 区跨月不重参数化**：止损触发区与边界退出区到达月边界时保持退出路径（σ0/rank/source 不刷新、不挂新单），清仓后 cooling→done。BR-7 未覆盖"止损退出区恰逢翻月"。
- **S-10（候选）当月再准入阻止键**：以 MONTH_SYMBOLS（每 signal_date 每符号至多一个 zone 记录）实现 BR-8 (ii)/(iv)——冷却与当月已 done 的符号不再准入；翻月自然解锁。等价于"每候选每月至多一次准入"。
- **S-11（候选）signal_date 的"交易日"校验口径**：实现为"存在于日线面板日历"（面板可能含 tradestatus=0 的停牌行日期）； operative 要求 = (signal_date,"pm") 决策点存在，该点在引擎日历中恒存在。
- **S-12（候选）TP2 sizing 与 tp2_frac 解耦**：按 BR-4 冻结文本，tp2 无条件 shares=None 全卖可卖（含公司行动零股）；tp2_frac 仅校验（∈(0,1]）不参与 sizing。若运行层给出 tp2_frac≠1.0，行为仍为全卖——请在接缝裁定中确认或改为 frac 参与计算。
- **S-13（候选）TP floor<100 的计数目标**：BR-4"floor<100 则本次不挂、计数"未指明计数键——实现为 `stats["zones"]["tp_below_min_lot"]`（每个未挂决策点计一次）。
- **S-14（候选）zone 武装不经 k3_armed 计数**：止损武装直接置 risk_state.armed（不经 bump_streak），`stats["k3_fallback"]["armed"]` 不增；B 段兜底成交仍计 k3_executed。门 8 v1.4 分母在 stats["zones"]["stop_armed_events"]，k3 块保持 v1.3 口径。
- **S-15（候选）zone WAC 只归集 zladder 买单**：混合账本下 intent 帧对同一 zones 符号的买入不进 WAC（F4R1 形态 = ETF 腿 intent + 个股 zones，符号不相交；重叠属未定义行为，由运行层约定排除）。
- **S-16（候选）数据结束日不做准入**：最后决策点 live_d=None 时跳过席位扫描（该准入无法挂出任何 live 订单，出生即死）；同点 expiry 照常触发（见 S-7）。
- **S-17（候选）stop fill 的统计不对称**：zone 止损成交（fill_type="stop"）计入 orders_filled.sell_risk 但不经 C 段的 orders.sell_risk 计数——与既有 B 段 market_fallback 的统计模式一致（v1.3 已存在），非本轮引入。

## 五、未完成内容与边界

- §10.5-4/5（双签 APPROVE、接缝裁定 S-v14-\*、pin、README/契约记账）未做——按任务分工属主对话；本报告与 manifest 已含 pin 所需新 sha256。
- 未运行任何 F4 实验、不动 val、无 git 操作、data/ 与既有 runs 零改动（锚复放脚本对源目录只读）。
- 不构成盈利或性能声称；三锚 VERDICT（0/8、0/1、0/0 dev_pass）为源 runner 既判结果的忠实复放，非本轮新结论。

## 六、运行身份与耗时

- 环境：Python 3.11.15 / polars 1.44.2 / Windows 10（Git Bash）；venv `D:/量化/.venv`。
- 预算：任务书目标 ≤4 小时；实际墙钟约 2 小时 05 分（实施约 55 分 + 测试迭代约 40 分 + 三锚回放约 2 分 + 交付物约 28 分）；无单问题卡住超 30 分钟。
- 测试迭代期间的失败运行均在本文件 §二/manifest 留痕口径内修正（全部为测试侧手算 slip 或合成数据设计修正，未改判据、未改引擎以迁就测试——每处修正见各测试注释的手算重算）。
