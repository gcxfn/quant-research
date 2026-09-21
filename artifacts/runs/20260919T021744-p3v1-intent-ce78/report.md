# P3 引擎 v1.1 意图层交付报告（exp-20260918-p3r2-band-v1-readjudication 前置）

- 运行：`20260919T021744-p3v1-intent-ce78`；状态：**completed（交付待双签）**
- 依据：P3R2 预登记 §9 修订 2（生命周期归属=引擎意图层）、修订 3（定价机制披露增量）、修订 4（ENGINE-3 授权）、修订 5（引擎身份重锚）；契约 `docs/plans/p3-band-contract.md` §7.7-M3 补充（执行主体=引擎意图层）。
- 零试验消耗；docs/configs 零改动；引擎改动仅限意图层 + ENGINE-3 行。

## 1. 引擎身份

- 旧引擎（v1）：sha256 `494310195438cbfb…`（21/21 测试，双签 APPROVE，9cc4 运行前后一致）
- 新引擎（v1.1）：sha256 `d7108c0eccdd77ff3fcbff01e7bd84bfdd2e7cad716b646e357c5644da970a0d`
- 静态帧路径行为不变（21/21 原测试原样通过）——即"无回归"证明。

## 2. 测试计数

| 套件 | 结果 |
|---|---|
| `tests/test_band_contract.py`（静态帧，原样未动） | **21/21 passed** |
| `tests/test_band_intents.py`（新增意图层） | **8/8 passed** |
| 合计（本引擎） | **29 passed** |
| 全仓库测试（`pytest tests/`） | **390 passed**（6 条既有警告来自 `p2r13_lowfreq.py`，与引擎无关） |

新增 8 项对任务清单 ①–⑦：①成交即停=i1；②未成交逐决策点重挂重锚+streak 不重置=i2；③到期终止=i3；④同名义覆盖（取消+streak 重置）=i4；⑤rescale-down 逐决策点重算=i5；⑥ENGINE-3 回归（有 bar 无 limit 行不崩溃、作废计入 K）=i6；⑦确定性（两次运行逐位一致）=i7；另加 i8 输入守卫（互斥入口/sizing 互斥/同标的首决策点去重）。

## 3. 意图层 diff 摘要（相对 494310195438cbfb，全部为加法式）

1. **入口**：新增公开 `run_band_backtest_intents(intents, …)`；`run_band_backtest` 加 keyword-only `intent_frame` 参数——两种模式互斥（同传报错），共享同一主循环、成交判定、账本、费用、clip、K=3 兜底核心；静态路径新增代码全部惰性守卫（`if intent_engine:`），行为逐位不变。
2. **意图帧校验** `_validate_intents`：必填 symbol/side/intent/decision_date/decision_session/source_signal/priority，可选 expiry_date/target_notional/target_weight；买入 = 名义或权重(0,1] 二选一；卖出 = 权重[0,1] 或名义或全退；同标的首决策点去重；同符号覆盖链（后一意图从其首决策点起取消前一意图，沿 R16 "latest target supersedes"）。
3. **引擎内生命周期** `intent_step`（挂在两个 decision_step 之后）：
   - 重锚：11:30 决策 = am.close；15:00 决策 = 官方收盘（缺失/停牌 → 本决策点不挂、意图保持活跃，streak 冻结，m3 一致）；
   - 定价（§9 修订 3）：数量 = 目标名义 × 决策点权益快照 ÷ 锚，整手取整（消除宿主外不动点迭代，作为 vs P3R1 差异披露）；rescale-down = 当前持仓 − 目标股数（整手向下取整，<1 手 = at-target 跳过并计数）；sell_full = 全退（shares=None）；
   - 终止：成交即停 / expiry（live session ≥ expiry 不再挂单）/ 同名义覆盖 / 上限作废（M2 语义：越限整单作废即终止意图，m6 终止原因）；不足现金/未穿透/T+1 锁定不终止（下决策点重试）；
   - 生命周期事件 `intent_lifecycle` 全程留痕；统计 `stats["intent_layer"]`（激活数、生成单数、四类终止、at-target 跳过、无锚跳过）。
4. **M1 复用**：K streak 键 (symbol, intent=risk, source_signal) 在 intent_step 内镜像 decision_step 既有刷新逻辑——重锚不重置、同名义新信号（source 变更）重置；静态路径的"无重发即撤销"块在意图模式关闭（意图层自持生命周期）。
5. **ENGINE-3 修复（修订 4）**：`band_engine.py` 风减卖单 `void_no_limit_info` 分支 detail 由 `%.4f` 改 `%s`（None 安全）；作废 + 计入 K + 披露的 v0 裁定 #2/#3 语义恢复；9cc4 的 host 侧跳过偏差随之废止。
6. **`_FallbackOrder`** 补 `source` 字段并在兜底构造时传递——K=3 兜底成交同样触发意图层成交即停。

## 4. 确定性验证

- test_i7_determinism：同一意图帧两次运行 → fills/events/daily/clips_final Polars `.equals()` 逐位相等 + stats JSON 序列化字符串相等：**通过**。
- 引擎无 RNG、无时钟依赖（唯一时间引用为 1800s 预算守卫，不进入结果）。

## 5. 手算样例

`hand-calc-samples.md` 三例：成交即停（含现金 189,995 对账）、到期终止（含跳空日锚越界作废）、rescale-down 逐决策点重算（200 → 100 股），均与测试断言一一对应。

## 6. 停止声明

按派发要求停在此处：待主对话验收 + 双签通过后再派 P3R2 重跑（重跑以新 sha `d7108c0eccdd77ff` 为准，§9 修订 5 回填由主对话执行）。本交付零试验消耗；不构成盈利或实盘声称。
