# 独立复核报告（双签第二签）：引擎 v1.5 `etf_routing='pm_only'` 与 2019 冒烟

- 复核方：独立复核代理 `EngineDoubleSign`（任务子代理，非语义节执行者）
- 时间：2026-09-21（会话时长 6m53s）
- 复核基线：引擎 sha `d4b6c3764780e6dec5443174bb8fb0c1ca57ffd737da4e59069cbd3ca6735ed6`；
  冒烟 run `artifacts/runs/20260921T032048-etf-pm-only-smoke-c4d1/`；
  锚重放 run `artifacts/runs/20260921T031044-f3r3-anchor-replay-9f3a/`；
  探针 `tmp/etf_pm_only_probe.py`；预登记与决策文档。
- **复核结论：APPROVE**（零 CRITICAL、零 MAJOR；1 项 P3 发现已处置）。

## 1. 复核方原文（逐项结论摘要）

- **[1] sha256 与安装副本一致性 —— PASS**：`src` 与 `.venv/Lib/site-packages` 副本
  哈希相等且 `cmp` 逐字节相同；226,756 B / 4,425 行与交付记录一致。
- **[2] 默认路径等价性（结构论证）—— PASS**：逐枚举 `etf_routing`(18)/`etf_pm_only`(14)/
  `session_bar`(5)/`pm_only_bars`(4)/`allow_empty`(4) 的全部出现位置，逐条论证
  `'paired'` 下表达式与旧式等价（`if halfday_clock and not etf_pm_only` ≡ 旧
  `if halfday_clock`；`session_bar` 的 else 分支字面返回 `halfbar(...)` 且无前置副作用；
  `_validate_halfday` 的单一调用点即 `allow_empty=etf_pm_only`）；并指出残留两处直接
  `halfbar` 调用在 pm_only 下不可达（zone 段与 `intent_anchor` 的 am 分支）。
- **[3] 四项针对性测试 —— PASS（8 passed）**：逐 seam 核对真实触发；发现 1 项
  **不可证伪断言**（见 §2）。
- **[4] 全仓测试 —— PASS**：638 passed / 0 failed；`--ignore` 新文件后收集 630 项，
  与宣称的 630→638 一致。
- **[5] 锚零回归 —— PASS**：8 帧逐字节相等（哈希亲验）；两处已披露差异独立复核成立
  （composite：106,538 行全行字符串多重集相等 + 键序 `equals()` True，仅编码/顺序差异；
  metrics json：12 处数值差全部 ≤4.7e-10 绝对值即 ~2e-15 相对，`gates` 整块相同）；
  重放日志逐计数复现（provider 2924/2924、injected 2632/2855、orders 2624/2799、
  filled 512/542、expired_halfday 2016/2150、no_anchor 88/148、门 0/2）。
  **限制（复核方标注）**：该锚不传 `symbol_meta`（无 ETF 腿），因此只证明**非 ETF 半日
  路径**零回归；ETF-meta 的 `'paired'` 分支靠既有 `test_band_hybrid` 与新 t4 守卫覆盖。
- **[6] 探针 —— PASS**：重跑 exit 0 且 JSON 字节不变（sha256 `fda7fff8…`，与复核前副本
  逐字节相同）；P1/P2 仍拒绝、P1p/P2p 结果一致（证明不读 ETF 半日 bar）、P3 与
  P4 legacy 与步骤 1 记录逐字段相等；P4p 手算逐项独立重推一致。
- **[7] 冒烟独立复算 —— PASS**：以 2019 原始日线自行重算 16 笔成交的路由、锚价
  （最大偏差 0.0）、日线极值穿透、费用（佣金逐笔、印花 0、全窗 80.0）、现金守恒
  （Δ=−1.455e-11）、provider_calls=488=2×244、injected=20；`decision_points.csv` 488 行
  最大自算差 2.91e-11；两处 am 手算样本独立复现（Δ=0）。
- **[8] 诚实性与边界 —— PASS**：数据只读一处且在与读取同一管线内过滤 2019；半日批仅以
  manifest 引用、引擎收到 0 行；无随机源；写入目标均在本 run 目录内；F3R3 run 目录
  21 个文件最新 mtime 2026-09-21T02:56:19 未被本次工作触碰；引擎/测试/预登记/数据
  pin 逐项复算一致。
- **不可验证项（复核方如实声明）**：改动前引擎文本（`bcbdd44…`）盘上无副本、仓库无
  版本控制，故"默认路径不变"依赖 [2] 的结构论证 + 逐字节锚 + 638 全绿，**无法做源码 diff**。
- **最强/最弱证据与置信度**：最强 = 8 帧逐字节锚 + 16 笔成交从原始数据的独立重算 +
  探针字节稳定重跑；最弱 = pm_only 行为证据目前仅合成测试 + 一个 2019 冒烟（16 笔/3 腿）、
  pm_only 下"股票同僚行为"仅单例；**置信度 0.85**。

## 2. 复核发现与处置

| # | 级别 | 内容 | 处置 |
|---|---|---|---|
| F1 | P3（不阻断） | `test_t1_am_decision_point_never_emits_an_etf_order_under_pm_only` 的 provider 处处返回 `None`，故 `orders_generated == 0` **不可证伪**——若未来回归把 pm-only ETF 的 live session 路由到 am，该测试仍会通过（复核方给出了替换方案并实测通过） | **已按复核方方案实施**：改为在首个 pm 决策点提交真实买单，断言 `seen == [(D1,am,0),(D1,pm,0),(D2,am,0),(D2,pm,1)]`、`orders_generated == 1`、成交落在 (D2, pm)，并新增"任一 am 会话事件不得带 symbol"断言；测试文件 sha256 由 `d4dbd177f2565c82…` → `fd29fa215990a7ac…`（**仅注释与该项断言变更，其余 7 项未动**） |
| C1 | 说明（非发现） | t1 内注释把 2.005 说成"AT the anchor" | **已改为**"the session low sits ABOVE the anchor (2.005 > 2.00)"，并注明 low==anchor 的触价不成交由 `tests/test_band_contract.py::test_05_touch_penetrate` 覆盖 |
| C2 | 说明 | 冒烟 runner 的 `routing_no_etf_am_intent_rejected` 判据恒真（`x >= 0 and calls > 0`） | **已替换为可证伪判据** `routing_no_etf_order_in_any_am_session`（断言引擎事件流中不存在带 symbol 的 am 会话事件），冒烟重跑全过（checks 全 true、16 笔成交不变）；am 意图拒绝本身由引擎测试 t2 覆盖 |

## 3. 复核后增量的再确认

- 处置后的三份证据已重新生成：测试文件、冒烟 run（重跑，产物除 `checks.json`/manifest
  时间戳与判据名外不变）、本 run 的 manifest 与 report。
- 具体复核命令（工作目录 `D:/量化`）：
  1. `sha256sum tests/test_band_engine_v15_etf_pm_only.py` → `fd29fa215990a7ace5a8e4abdc24b38a7854433be5ffa132c0de29bcbd9a20a7`
  2. `.venv/Scripts/python.exe -m pytest tests/test_band_engine_v15_etf_pm_only.py -q` → 8 passed
  3. `.venv/Scripts/python.exe -m pytest -q` → 638 passed / 0 failed
  4. `.venv/Scripts/python.exe artifacts/runs/20260921T032048-etf-pm-only-smoke-c4d1/tmp/runner_etf_pm_smoke.py` → 16 fills / failures 0
- 引擎文件在复核后**未被改动**（sha 仍为 `d4b6c376…`），故 [1][2][5] 的结论继续有效。

## 4. 复核方增量再确认（2026-09-21，同一复核代理，处置后）

复核方对三处增量逐项复核的回复（原文要点）：

- **(a) D1 测试 —— PASS**：sha256 `fd29fa215990a7ac…`（310 行）与执行方数值一致；
  通读 310 行，与受审版本仅两处差异（t1 注释更正；am 决策测试按建议改写），
  t2（两个）、t3、t4（两个）与模块 docstring **逐行比对实质未变、无断言被改动**；
  `pytest tests/...` → 8 passed；新增的 am 事件断言可证伪。
- **(b) D2 冒烟 —— PASS**：替换后的判据确实可证伪，旧的恒真判据名已消失；
  `checks.json` 19 项判据全 True、`failures` 空；manifest 状态 completed、
  引擎前后 sha 均 `d4b6c376…`、`test_file_sha256` = `fd29fa21…`；
  **8 个数据产物与复核前逐字节一致**（大小全同，独立重算仍复现：16 笔 = 8 买 8 卖、
  0 路由/价格/穿透/费用违规、全窗费用 80.0、现金守恒 Δ=−1.455e-11、provider_calls 488、
  injected 20、期末结算现金 94,030.79999999996、权益 215,919.69999999995）。
  复核方亦纠正执行方措辞：本轮重跑变化的文件是 `checks.json`、`report.md` 与 `manifest.json`
  （而非仅 checks/manifest 时间戳）；数据产物才是"不变"的那部分。
- **(c) D3 引擎未改 —— PASS**：`src` 与 `.venv` 副本 sha 均仍为 `d4b6c376…` 且 `cmp` 一致；
  冻结 F3R3 目录最新 mtime 仍 2026-09-21T02:56:19.371。
- **(d) 结论**：对最终字节（引擎 `d4b6c376…`、测试文件 `fd29fa21…`、重跑后的冒烟 run）
  **APPROVE 维持有效**。

### 复核方的三条卫生级新意见与处置（均不阻断）

| # | 意见 | 处置 |
|---|---|---|
| F2 | `tmp/__pycache__/…pyc` 被计入 manifest 输出哈希，使产物集依赖解释器 | **已处置**：runner 的输出扫描排除 `logs/`、`__pycache__/`、`*.pyc`，并加 `outputs_note` 说明；`.pyc` 已删除，重跑后 manifest 无任何陈旧哈希（逐项复算 0 处不符） |
| F3 | 冒烟 report §〇 的确定性表述在判据块修订后已过时 | **已处置**：改写为"8 个数据产物与同输入前次全窗运行逐字节一致（复核方独立比对）；`checks.json`/`report.md`/`manifest.json` 随判据块修订与 run_id 变化" |
| F4 | 执行方交接口径把判据数说成 17，实际 19 | **已确认**：产物自洽为 **19** 项判据（routing 5 / matching 4 / fees 2 / T0 3 / ledger 5），报告正文按 5 条链路分组表述，无数字冲突 |

复核方同时重申其限制（与本报告 §1 一致）：改动前引擎文本盘上无副本、仓库无 VCS，
"默认路径不变"只能由结构门控论证 + 8 帧逐字节锚 + 全仓 638 绿共同支撑。
