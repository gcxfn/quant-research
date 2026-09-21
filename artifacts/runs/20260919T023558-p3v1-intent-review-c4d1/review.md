# P3 引擎 v1.1（意图层扩展）独立复审报告（双签第二签）

- 复审运行：`20260919T023558-p3v1-intent-review-c4d1`
- 复审对象：`src/quant/backtest/band_engine.py` v1.1（意图层 + ENGINE-3）；交付 run `20260919T021744-p3v1-intent-ce78`
- 授权链：`docs/research/exp-20260918-p3r2-band-v1-readjudication-prereg.md` §9 修订 2/3/4/5；`docs/plans/p3-band-contract.md` §7 + §7.7（M1/M2/M3、m1–m7）
- 性质：只读复审。未改动引擎、docs、configs、tests；探针脚本置于本目录 `tmp/`。
- **判决：APPROVE**（0 CRITICAL / 0 MAJOR / 4 MINOR；MINOR 均不阻塞，处置建议见 §5，其中建议 P3R2 重跑前由主对话对 MINOR-1 做一次书面裁定并给 `_validate_intents` 补一行去重守卫）

## 0. 身份核对

- 开工哈希：`d7108c0eccdd77ff3fcbff01e7bd84bfdd2e7cad716b646e357c5644da970a0d`（与交付声称一致）。
- 收工复检：同上，未变（审查期间引擎字节无改动）。
- 交付 run manifest 内 6 项 artifact sha256 逐一与盘上重算一致（hand-calc-samples.md、pytest_engine.log、report.md、引擎、两个测试文件）。

## 1. 静态路径零回归（任务 1）——通过

结构性审查（无 v1 基线可 diff，以结构 + 旁证替代）：

- 全文定位 `intent_engine` / 意图层触点共 16 处，逐处核对：入口互斥守卫（L1062-1065）、`assert_frozen(intent_frame)`（L1074-1077）、`orders = []` 分支（L1119-1125）、`decision_step` 的 `elif intent_engine: pass`（L1378-1381）、`book_buy_fill`/`book_sell_fill` 的 `intent_stop` 调用（L1451/L1505，双重守卫：外层 `if intent_engine` + `intent_stop` 内 `INTENT_BY_KEY` 空表早退）、cap 作废钩子（L1764-1767）、收尾统计（L2066/2086-2090）。全部在守卫之后或新函数内。
- 静态帧路径唯一的行为性差异：stats 字典新增两个惰性元数据键（`order_generation: "static"`、`intent_layer: None`）——见 MINOR-3。
- 决策点快照块（decision_snapshots，M2）：对静态路径只读记录（纯字典写入，不改 cash/clips/orders），cap 校验取 `decision_snapshots` 优先、回落 base_eq——与 §7.7-M2 一致，属 v1 已裁定语义。
- 卖单路径、K=3 兜底（含 m1 跌停顺延计数、停牌冻结、`_FallbackOrder`）、公司行动（m4 逐 clip half-up、新 clip 当日取得次日可卖）、费用（分段印花/ETF 豁免/最低佣金）逐段通读，未发现 v1.1 引入的改动。
- 旁证三件：21 项静态测试原样通过（独立复跑）；`tests/test_band_contract.py` mtime 2026-09-18 23:39 早于授权编辑（01:43）与引擎交付（02:01:45），函数计数 21 与 v1 双签记录一致；v1 冒烟产物（9cc4 run `tmp/smoke/C01_*.parquet`，v1 引擎实际输出）的 fills/events/daily 三张帧 schema 与 v1.1 声明 schema 逐列比对**零增删零改型**。
- 结论：21 项未动测试 + 上述结构与 schema 证据，构成充分无回归证明。未见未覆盖的静态行为变化（stats 两个元数据键除外，MINOR-3）。

## 2. 意图层语义 vs 裁定（任务 2）——通过，1 项边角（MINOR-1）

- **重锚口径**：`intent_anchor`：am 决策 = am.close（半日 bar[3]）；pm 决策 = 官方日线 close（dint 匹配 + trading 位检查）。全路径无 pm.close（L1544-1555）✓ §7.4。
- **定价（修订 3）**：buy `tn = target_weight × 决策点快照`（或绝对名义）→ 成交评估时 `want = floor(tn/锚/100)×100` 整手向下；sell rescale-down `目标股数 = floor(base_tn/锚/100)×100`，`卖量 = 持仓 − 目标股数` 再整手向下，`<1 手` at-target 跳过且**不终止**（仅计数 `at_target_skips`）✓。快照时点无未来信息：am 决策用 strict 前收、pm 决策用当日官方收盘 ✓。
- **四种终止**：filled（两个 book_*_fill → `intent_stop(...,"filled")`）；expired（`live_d >= expiry`，live session 日期口径）；override（`k_ds >= overridden_at`，链在 `_validate_intents` 预计算）；cap（`intent_stop(...,"cap_single_name")` 于 L1764-1767 接线，触发条件 = M2 构建时点校验越限 → **整单作废后**终止意图，无缩量 ✓ 探针 A 实证：weight=1.0 意图经历 insufficient-cash 重试后，在可负担但越限的 emission 上被 `void_cap_single_name` + `intent_lifecycle: cap_single_name` + `terminated_cap=1` 终止）。
- **三种不终止**：insufficient_cash / not_penetrated / T+1 锁定均只 `close_order`、不触发 `intent_stop`，下决策点重试 ✓（探针 F2 实证重试回路：10 次 insufficient-cash void 披露、现金恒非负、优先级竞争 (priority, symbol) 有序）。
- **M1 键控**：intent_step 内刷新逻辑与 decision_step 静态版逐语义镜像：同 source 重锚不重置 streak 且 armed 保留；source 变更 → streak=0、armed=False（探针 B 实证：armed 之后到达的覆盖在下一 session 前解除武装，无兜底成交，新 source 首发报 streak 1）；到期不再重发即停止计数 ✓ §7.7-M1。`_FallbackOrder.source` 传递 st["source"]（最新站立意图），兜底成交 `intent_stop` 按 (symbol, side, source) 命中正确意图；旧意图已 done 时早退不误伤。
- **override 链跨 side**：链按 first_key 排序、`prev.overridden_at = nxt.first_key`，后买压前卖、后卖压前买对称成立；同标同 (d,s) 首决策点去重使"同决策点激活+覆盖并存"不可能发生（事件顺序恒为：先覆盖旧、后激活新，探针 D 事件序验证）；被覆盖意图的在途单生命周期恰一个 session，且其 live session 先于覆盖决策点完成，无悬挂单。边角注记：armed 兜底对**买入意图覆盖**不自解装（沿 v1"armed 不可撤"裁定，见 §4 注 2）。
- **expiry**：`live_d >= expiry`，live_d 恒为交易日；非交易日 expiry（如周末）等价于顺延至首个其后交易日 live session 终止——确定性、无歧义（代码审读结论，未单测，见 §4 缝清单）。
- **m3**：无 am bar → 跳过 emission、streak 冻结 ✓；无 pm bar → 见 MINOR-1。
- **m6 对账**：terminated_expired/terminated_cap/terminated_override 单列 ✓；"停牌放弃"在意图层不作为终止态存在（停牌意图保持活跃），该项属 runner 门 8 映射职责，P3R2 未开跑，不构成本轮缺陷（登记观察）。

## 3. ENGINE-3（任务 3）——通过

- 买卖两侧 no_limit_info detail 均为 `%s` 格式（L1706 / L1884-1885），None 安全 ✓ 修订 4。
- `test_i6` 真实复现原崩溃三要素：live 风险卖单 + 有 bar（HALF_B D2am/D2pm/D3am）+ stk_limit 行缺失（D2–D4 过滤）；作废经 `bump_streak` 计入 K（断言 armed==1），detail 含 'None' 字样。若回退 `%.4f` 该测试必然 TypeError——是有效回归测试 ✓ v0 裁定 #2/#3 语义恢复。

## 4. 测试质量与未覆盖缝（任务 4）

8 项测试测的是**语义**（重锚价序列 9.3→9.1→8.75、streak 明细文本、fill 时点/价格、现金 189,995 对账、生命周期事件、统计计数），非实现细节。test_i7 无假阳性可能：引擎无模块级缓存/全局可变状态（risk_state、INTENTS、INTENT_BY_KEY 均为调用内局部），两次运行相互独立；其断言的是独立计算的逐位一致，只会假阴性不会假阳性。

未被测试覆盖的缝（本轮以探针或代码审读闭合，登记为后续加固建议）：

1. cap 终止接线（无测试；探针 A 实证正确）；
2. override 发生在 armed 之后（无测试；探针 B 实证先解装）；
3. expiry 恰为非交易日（审读：等价顺延，无风险）；
4. 同决策点多意图现金竞争（无测试；探针 F2 实证优先级+费用预留+非负现金+重试披露）；
5. buy 权重 sizing × 现金不足交互（探针 A 顺带实证：insufficient-cash 先于 cap 检查，重试后 cap 终止）；
6. 意图模式下 `_FallbackOrder` 路径（武装与执行之间遇停牌）无测试——代码审读确认 source 传递与 intent_stop 命中正确；
7. profit 意图在意图模式无测试（m2 已登记本轮映射不出现）；
8. at_target_skips 路径无直接断言（探针 D 间接经过）。

**MINOR-1（m3 字面偏差，边角）**：标的当日无 S_pm bar（市场级半日或午后停牌）时，`intent_anchor(pm)` 用官方日线 close（仅反映上午成交，无未来信息），15:00 决策点照常重挂、live 次日 am。§7.7-m3 字面为"当日无 15:00 决策点，在途意图次日首个决策点重挂"——引擎较该读法**早一个 session**执行，且与引擎自身 decision_step 注释（"there is no 15:00 decision for them"，该注释的 streak 冻结部分成立、重挂部分不成立）不一。探针 C 实证（D2 无 pm bar：`(D2,pm)` 决策以官方收盘 10.7 重挂 live (D3,am)）。数据侧核实（2015–2016 全表）：市场级无 pm bar 交易日恰 1 天（2016-01-07，熔断日，am 2,549 行/pm 0 行），其余为个别标的午后停牌（每日 1–2 只量级）。定性：修订 2（"引擎逐决策点内部完成机械重锚，15:00=官方收盘"，无停牌豁免）与 m3（宿主时代文本）存在**裁定文冲突**，引擎采修订 2 且保留 m3 的 streak 冻结，方向可辩护；影响有界（受影响 (标的,日) 对的重挂时点/锚价），无未来信息、无判定数字已消费。处置建议：P3R2 重跑前由主对话在 §7.7-M3 或新修订节书面裁定（认可现行为，或要求 pm 决策 emission 以 pm bar 存在为闸）——二选一均可，引擎无需必改。

**MINOR-2（生命周期键与 M1 键不一致 + 去重缺口，边角）**：`INTENT_BY_KEY` 键为 (symbol, side, source_signal)，缺 intent 维度；M1 计数键为 (symbol, intent=risk, source)。`_validate_intents` 不拒绝重复 (symbol, side, source)（含潜在 risk+profit 同 source 并存——m2 已裁定本轮映射不出现）。经激活时序论证：先前意图成交时后者必为 pending → `intent_stop` 早退，**不会误终止活跃意图**；叠加逐决策点重算的自纠（at-target / 无持仓 void），无资金损坏。实际后果限于：`stopped_filled` 漏计、成交缺 `intent_lifecycle` 事件、原意图迟至覆盖/到期才 done（探针 D 实证）。处置建议：`_validate_intents` 增一行重复键拒绝（约 3 行改动），或登记为宿主映射约束。冻结映射 §4 每 (symbol, side, source) 唯一，本轮不触发。

**MINOR-3（静态 stats 元数据键）**：静态模式 stats 新增 `order_generation`/`intent_layer` 两个键（值 "static"/None）。四张输出帧逐位不变；纯元数据增量。交付报告"行为逐位不变"就交易行为与全部数字而言成立，就 stats schema 而言是加法式变化——披露精度注记。

**MINOR-4（既有 docstring 漂移，v1 期遗留）**：模块 docstring"Enforced at fill evaluation against the last COMPLETED day's official-close marks"早于 §7.7-M2 的"决策点权益快照"表述。非本轮引入；建议随下次获授权的文档触点更新，现在不动。

## 5. 披露诚实性对账（任务 5）——逐条属实

| 交付声明 | 复核 |
|---|---|
| sha256 = d7108c0e…a0d | 开工、manifest、收工三次一致 ✓ |
| 21/21 静态原样通过 | 独立复跑 29/29（含 8 新增），21 项函数计数与 v1 双签记录一致，mtime/schema 旁证 ✓ |
| 8/8 新增意图层测试 | 通过，且为语义断言 ✓ |
| 全仓库 390 passed（6 条 p2r13 警告） | 独立复跑 `pytest tests/ -q`：**390 passed, 6 warnings in 12.20s**，警告源与声称一致 ✓ |
| 静态路径全部加法式/惰性守卫 | 结构审查成立（MINOR-3 的 stats 元数据键为唯一 schema 级增量，非行为）✓ |
| 零试验消耗 | 无新 p3r2-dev run 目录（仅已登记的 9cc4 ABORTED）；02:15 的 run 为无关 ETF 拉数 ✓ |
| docs/configs 零改动（授权编辑除外） | 两份授权文档 mtime 01:43:30 早于引擎 02:01:45，内容即修订 2–5/M3 补充本身；configs 最新 mtime 09-18 23:55（冻结配置），交付期间未动 ✓ |
| 手算样例 1/2/3 | 样例 1 主对话已复算；本复审独立重算样例 2（事件序与到期边界逐时点）与样例 3（快照 199,595→200,995、目标 800→900、卖量 200→100、@11.00 成交、终持仓 900），与代码路径及测试断言全部吻合 ✓ |
| `_FallbackOrder` 补 source 并传递 | 核实（L624、L1830）✓ |

## 6. 独立重跑（任务 6）

- `.venv/Scripts/python.exe -m pytest tests/test_band_contract.py tests/test_band_intents.py -q` → **29 passed in 5.16s**。
- `.venv/Scripts/python.exe -m pytest tests/ -q` → **390 passed, 6 warnings in 12.20s**。

## 7. 判决与证据清单（APPROVE）

**APPROVE**。依据：§0 身份三次一致；§1 静态零回归（结构 + 21/21 + v1 冒烟 schema 同一性）；§2 意图层与修订 2/3、M1/M2、m1/m4/m5/m6 逐条吻合，四种终止/三种不终止全部对裁，cap 接线、armed-后-覆盖解装、M1 兜底命中经探针实证；§3 ENGINE-3 修复与回归测试有效；§5 披露逐条属实；§6 独立复跑全绿；收工哈希未变。无 CRITICAL/MAJOR。

随判决移交主对话裁量的事项（均不阻塞引擎身份重锚）：

1. MINOR-1：P3R2 重跑前对"无 pm bar 日的 15:00 决策点"做书面裁定（修订节或 §7.7-M3 注记）；
2. MINOR-2：`_validate_intents` 补重复 (symbol, side, source) 拒绝（或登记为宿主映射约束），可与裁定一并授权；
3. MINOR-3/4：披露精度与 docstring 漂移注记，随下次授权文档触点处理；
4. §4 缝清单 1–8 作为后续测试加固建议（不阻塞）。

复审过程产物：`tmp/probe_intents.py`（探针 A/B/C/D/F）、`tmp/probe_f2_cash_retry.py`（探针 F2）。本报告不构成盈利或实盘声称；2025+ 冻结区零接触。
