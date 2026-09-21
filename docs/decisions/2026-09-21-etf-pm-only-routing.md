# 决策：halfday 时钟 ETF pm-only 单会话路由（ETF 暂时每日决策）

日期：2026-09-21｜性质：引擎契约变更（规则级）｜状态：已批准，待落地

## 决策

批准引擎扩展路径 (b)：为 `execution_clock='halfday'` 增加显式的 ETF
"pm-only 单会话"路由——ETF 每天只在 15:00 决策点产生意图，次日按日线
bar 撮合，不要求、不使用任何 ETF 半日 bar。这是"ETF 暂时只做每日决策"
的引擎表达，数据受限的暂时简化，不是终态承诺。

## 背景与依据

- 数据事实（运行 `artifacts/runs/20260921T023606-etf-dynamic-identity-e41c/`，
  四项核验 + P1–P4 探针，全部可复现）：`halfday-bars-20260918` 对 ETF
  零覆盖（0/1,169，三只防御腿各 0 行）；ETF 主源 `tushare fund_daily
  20260917-r1` 仅日线；仓库内全部日内派生数据集均无 ETF 符号。ETF 分钟
  补源按 P3 契约 §6/§7.4 明文"维持不回补"。
- 契约事实：契约 §8.2 本来就规定 ETF 腿只交易 15:00 决策点；legacy 时钟
  下 pm-only 形态可用（探针 P4 成交与手算一致），halfday 时钟的 guard
  （"requires ETF am and pm bars"）把该形态结构性拒绝（探针 P1/P2）。
- 主线事实：混合主线单账本回放必须股票半日线与 ETF 共用一个账本；全局
  退回 legacy（路径 c）会失去半日重发与半日账本反馈，账户级风险主线
  无法验证，故否决。

## 否决/搁置的路径

- (a) 补 ETF 日内数据源：P3 契约明文不回补，未获授权；留待未来单独决策。
- (c) 混合主线整体退回 legacy 时钟：断掉股票线半日能力与账户级反馈主线。

## 扩展语义（五点，实现必须逐点对应）

1. 显式开关（如 `etf_routing='pm_only'`），默认值保持现行为
   （am+pm 成对要求不变）；已运行的 F3R3 语义不漂移。
2. ETF 意图仅 pm 决策点；am 决策点的 ETF 意图恢复拒绝。
3. pm 决策 → 次日 pm 会话，日线 bar 撮合；停牌/无行日按既有停牌规则。
4. am 决策点权益快照对 ETF 持仓用 `official_close_strict`（最近已成交
   收盘，与停牌冻结同语义，无未来信息）；daily mark 维持日线收盘。
5. pm-only 模式下 ETF 不要求任何半日 bar；日线有成交行的日子必须有
   日线行，缺失即 fail-closed。

## 执行条件（落地门槛）

- 三锚零回归：① 全仓测试回归全绿（当前基线 617 passed）；②
  `tests/test_band_dynamic.py` d1–d8 原断言零改动通过；③ F3R3 全期重跑
  逐位复现（fills/events/daily_equity/clips_final 与
  `artifacts/runs/20260921T024449-f3r3-dynamic-45037d/outputs/` 逐位一致）。
  任一锚失败即回退重审，不得"近似通过"。
- 新增针对性测试至少四项：pm→次日 pm 日线撮合、am 决策点 ETF 意图拒绝、
  am 快照用最近成交收盘（手算）、ETF 无半日 bar 不触发 am+pm 守卫。
- 新引擎 sha 写入本决策、任务①②预登记与各 manifest；语义节执行者写、
  整合方复核签认（双签）后方可作为冒烟与后续实验的运行基座。
- 探针 P1/P2 在 pm-only 模式下转为通过、P4 legacy 行为不变，作为语义
  闭环的核验点。

## 执行记录（2026-09-21，落地与 pin）

- **引擎 pin**：`band_engine v1.4.1`（`bcbdd44bb855b803ed8fa2dfc4915319af4c0b79e78e7b789c0b1bfb2d75ee4a`，
  218,654 B / 4,291 行）→ **`band_engine v1.5` `d4b6c3764780e6dec5443174bb8fb0c1ca57ffd737da4e59069cbd3ca6735ed6`**
  （226,756 B / 4,425 行）。新参数 `etf_routing='pm_only'`（默认 `'paired'`，默认路径零回归）。
- **验收结果（§执行条件逐条）**：① 全仓 **638 passed / 0 failed / 0 skipped**
  （改动前实测收集 630 项；本扩展新增 8 项；任务书引用的旧基线 617 已被并行工作流的
  测试增补推到 630）；② `tests/test_band_dynamic.py` **未改动**（sha256 前缀
  `c56dc9432d8737ed`）且 9 项全过；③ F3R3 全期锚重放：`F3-{EW,ICW}_{fills,events,
  daily_equity,clips_final}` **8 帧逐字节相等**（另 seat_outcomes/dedup_clusters/
  pool_sizes 亦逐字节相等；`composite.parquet` 仅文件字节差而行多重集与键序一致、
  `metrics_and_gates.json` 仅 engine sha 字段与 ~1e-15 归约噪声，判定数字与门结果不变）；
  ④ 四项针对性测试全覆盖（文件 `tests/test_band_engine_v15_etf_pm_only.py`，8 项）；
  ⑤ 探针 P1/P2 在 pm_only 下**转为通过**（且补/不补 §8.1 合成 pm bar 结果一致），
  P4 legacy 与其原记录逐字段一致。
  **引擎 sha 同时写入**：本决策、冒烟预登记
  `docs/research/exp-20260921-etf-pm-only-smoke-prereg.md`、
  扩展验收 run `artifacts/runs/20260921T031044-engine-v15-pm-only-9f3a/manifest.json`、
  锚重放 run `artifacts/runs/20260921T031044-f3r3-anchor-replay-9f3a/`、
  冒烟 run `artifacts/runs/20260921T032048-etf-pm-only-smoke-c4d1/manifest.json`。
- **双签（本节由语义节执行者写、独立复核方签认）**：
  - 第一签（执行方）：实现 + 上述验收亲跑；交付与验收记录见
    `artifacts/runs/20260921T031044-engine-v15-pm-only-9f3a/report.md`。
  - 第二签（独立复核代理 `EngineDoubleSign`，2026-09-21，6m53s）：**APPROVE**——
    零 CRITICAL、零 MAJOR、1 项 P3；复核方以自有工具逐项重算（sha 亲验、默认路径结构
    等价逐条枚举、638 全绿、8 帧锚哈希亲验、探针重跑字节不变、16 笔冒烟成交从原始 2019
    日线独立重算、写入边界与冻结目录 mtime 核查），置信度 0.85，并如实声明"改动前引擎
    文本无副本可 diff"这一不可验证项。报告：
    `artifacts/runs/20260921T031044-engine-v15-pm-only-9f3a/verification_report.md`。
  - P3 发现处置（执行方，已落地并重跑）：测试 `t1_am_...` 的不可证伪断言 → 提交真实单 +
    "am 会话零事件"断言（测试文件 sha `d4dbd177…` → `fd29fa21…`）；t1 一处注释误标更正；
    冒烟 runner 中恒真判据 → `routing_no_etf_order_in_any_am_session`（可证伪），冒烟重跑
    仍 16 笔、判据全过。**引擎文件复核后未改动**（sha 不变），签认状态：**APPROVED**。
  - 增量再确认（同代理）：处置后三处增量（测试 / 冒烟 / 引擎未改）全部 PASS，
    **APPROVE 对最终字节维持有效**；三条卫生级意见（pyc 入 manifest 哈希、确定性表述口径、
    判据计数）已处置并登记于复核报告 §4 与本任务 manifest。
- **文档纪律**：主计划、README 与台账由整合方统一更新（本任务不自行改动），
  并需登记"任务① 引擎 pin `bcbdd44bb855b803`（v1.4.1）与任务② v1.5 pin 并存、
  任务①新运行需重 pin"的事实。

## 暂时性条款

本决策是数据受限的暂时简化。若未来获得授权补齐 ETF 日内数据、或将
防御腿提升至半日节奏，需新的数据批次、新预登记与独立验证；不得以本
决策的 pm-only 结果外推半日执行表现。

## 关联

- 核验证据：`artifacts/runs/20260921T023606-etf-dynamic-identity-e41c/`
  （identity_checklist.md 及 tmp/ 复现脚本，三脚本重跑哈希不变）
- 裁定对话：2026-09-21 主会话（批准 + "ETF 暂时只做每日决策"确认）
- 受影响任务：任务②（ETF 动态冒烟，修正文本见其预登记）；任务①
  （股票线，不受影响，但其 manifest 需登记实际引擎 pin 与双 pin 事实）

## 落地与签认（2026-09-21）

扩展已落地并完成验收，记录如下：

- 引擎 v1.5 sha256 `d4b6c3764780e6dec5443174bb8fb0c1ca57ffd737da4e59069cbd3ca6735ed6`
  （默认 `etf_routing='paired'` 保持既有行为；工程与验收记录见
  `artifacts/runs/20260921T031044-engine-v15-pm-only-9f3a/report.md`）。
- 三锚零回归：全仓 638 passed（基线 630 + 新增 8）；d1–d8 原断言零改动 9 passed；
  F3R3 全期重放 8 帧逐位相等（`artifacts/runs/20260921T031044-f3r3-anchor-replay-9f3a/`，
  首次尝试因脚本复制截断失败留痕，重制逐字节副本后通过）。
- 四项针对性测试（`tests/test_band_engine_v15_etf_pm_only.py`，8 passed）；探针
  P1p/P2p 通过、P4 legacy 逐字段不变。
- 冒烟：`artifacts/runs/20260921T032048-etf-pm-only-smoke-c4d1/`（2019 全年，五项链路
  判据全 PASS，手算抽检 Δ=0）。
- 签认：第一签为任务执行方；第二签为独立复核代理（APPROVE，1 项 P3 断言加强已
  处置）。**整合方确认**（2026-09-21）：独立复跑全仓 638 passed、核验三锚日志与
  冒烟判据后认可上述结论，本决策正式生效；后续 ETF 相关运行以 v1.5 pin 为基座。
- 双 pin 事实：任务①（账户级风险对照）于本扩展落地前用 `bcbdd44bb855b803` 完成，
  其 D0 控制组与 F3R3 载体五帧一致性门独立成立，不需重跑；其结论不受引擎 v1.5
  影响（股票线路径逐位未变，锚 ③ 已证）。
