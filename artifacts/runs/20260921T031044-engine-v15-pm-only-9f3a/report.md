# 任务② 引擎扩展交付与验收记录：halfday 时钟 ETF pm-only 路由（引擎 v1.5）

运行目录 `artifacts/runs/20260921T031044-engine-v15-pm-only-9f3a/`｜日期 2026-09-21
决策（权威）：`docs/decisions/2026-09-21-etf-pm-only-routing.md`
冒烟预登记：`docs/research/exp-20260921-etf-pm-only-smoke-prereg.md`
性质：**引擎工程任务 + 工程冒烟**，试验计数消费 **0**，无策略结论。

## 1. 交付物

| 文件 | 变化 | 身份 |
|---|---|---|
| `src/quant/backtest/band_engine.py` | 新参数 `etf_routing`（默认 `'paired'`）、pm-only 路由与其守卫、`session_bar` 执行 bar 取用、`_validate_halfday(allow_empty=…)`、版本标签 `v1.4.1 → v1.5` | **v1.5 sha256 `d4b6c3764780e6dec5443174bb8fb0c1ca57ffd737da4e59069cbd3ca6735ed6`**（226,756 B / 4,425 行；基线 bcbdd44b… 218,654 B / 4,291 行，+134 行） |
| `tests/test_band_engine_v15_etf_pm_only.py` | 新增，8 个测试覆盖四项针对性判据；独立复核发现 1 项不可证伪断言后**已按复核方案加强**（见 §4 与 `verification_report.md`） | sha256 `fd29fa215990a7ace5a8e4abdc24b38a7854433be5ffa132c0de29bcbd9a20a7`（14,697 B / 310 行；复核前版本 `d4dbd177…`） |
| `tests/test_band_engine_v14_zones.py` | 仅两处 `engine_version` 断言随版本推进（v1.4.1 → v1.5，先例 S-v13-3） | sha256 前缀 `9953c27f9074a53c` |
| `tests/test_band_dynamic.py` | **未改动**（d1–d8 原断言零改动） | sha256 前缀 `c56dc9432d8737ed` |

新增代码全部以新参数为门：`etf_routing` 出现 18 处、`etf_pm_only` 14 处、
`session_bar` 5 处、`pm_only_bars` 4 处、`allow_empty` 4 处。

## 2. 决策五点语义 → 实现逐点对应

| 决策语义 | 实现位置与做法 |
|---|---|
| ① 显式开关、默认保持现行为 | `etf_routing: str = "paired"`（两入口同签名，默认透传）；取值校验 `('paired','pm_only')` 且 pm_only 必须配 `execution_clock='halfday'`（legacy 时钟本就是 pm-only 形态，显式拒绝以免语义重叠） |
| ② ETF 意图仅 pm 决策点；am 决策点 ETF 意图拒绝 | 静态意图帧与 provider 注入两处 ETF-am 守卫条件由 `not halfday_clock` 扩为 `not halfday_clock or etf_pm_only`；生成循环里 ETF 意图在非 pm 决策点 `continue` |
| ③ pm 决策 → 次日 pm 会话、日线 bar 撮合；停牌按既有规则 | 路由 `etf_single_session = sym_is_etf and (not halfday_clock or etf_pm_only)` → `live=(next_day,'pm')`；执行段三处 bar 取用统一走 `session_bar()`：pm_only 的 ETF 用**真实日线 OHLC**（构建于入口、只取 traded 行），无行 = 停牌（普通单作废、风减冻结 streak，沿既有规则） |
| ④ am 决策点权益快照对 ETF 持仓用 `official_close_strict` | `decision_step` 的 am 标记：pm-only 的 ETF 持仓跳过"已结束 am bar 覆盖"及其 traded-today fail-closed 检查 → 保留 `official_close_strict`（最近已成交收盘，无未来信息）；daily mark 仍为日线收盘 |
| ⑤ 不要求任何半日 bar；有成交日缺行 fail-closed | 半日 ETF am/pm 守卫在 pm_only 下整体跳过；`_validate_halfday(allow_empty=True)` 允许 **0 行**半日表；入口构建 `pm_only_bars` 时对每个 ETF 标的断言 `trade_dint ⊆ bar 日集`，缺失即 `BandContractError`（在任何撮合发生前） |

## 3. 验收（决策门槛，全部满足）

| 锚/门槛 | 做法 | 结果 |
|---|---|---|
| ① 全仓测试回归全绿 | `.venv/Scripts/python.exe -m pytest -q` | **638 passed / 0 failed / 0 skipped**（改动前实测收集 **630** 项；本任务新增 8 项 → 638）。日志 `logs/pytest_full_suite.log`（一次性 Windows HDF5 文件锁抖动 `test_06c_split_loader_anchor_regression` 单测重跑通过、全仓重跑 exit 0，见 §5） |
| ② d1–d8 原断言零改动通过 | `pytest tests/test_band_dynamic.py -q` | **9 passed**；该文件 sha 未变（`c56dc9432d8737ed`），断言零改动。日志 `logs/pytest_band_dynamic_d1d8.log` |
| ③ F3R3 全期逐位复现 | `artifacts/runs/20260921T031044-f3r3-anchor-replay-9f3a/tmp/runner_f3r3_anchor.py`（F3R3 runner 的逐字节副本：文件头 +8 行注释说明差异、正文仅改 `ENGINE_SHA_EXPECT_16` 一行，脚本内 self-check 打印「body identical: True」） | **两臂各四帧共 8 个产物逐字节相等**：`F3-{EW,ICW}_{fills,events,daily_equity,clips_final}.parquet`；另 `seat_outcomes.csv`/`dedup_clusters.csv`/`pool_sizes.csv` 亦逐字节相等。两个良性差异已披露（composite 行序/编码；metrics ~1e-15 归约噪声 + engine sha 字段），详见 `…-f3r3-anchor-replay-9f3a/NOTE-anchor-replay.md` 与 `outputs/anchor_frame_comparison.json` |
| ④ 新增四项针对性测试 | `tests/test_band_engine_v15_etf_pm_only.py` | **8 passed**（复核后加强版，2026-09-21 重跑）；四项判据全覆盖（t1 pm→次日 pm 日线撮合含未穿透反例；t2 两入口 am ETF 意图拒绝 + 股票 am 意图仍按 §7.1 当日 pm 执行；t3 am 快照=最近成交收盘，手算 189,995+5,000×2.10=200,495 与引擎一致；t4 空半日表在 pm_only 下跑通、默认路由同输入报错、模式/时钟守卫报错）。日志 `logs/pytest_v15_targeted.log` |
| ⑤ 探针 P1/P2 转通过、P4 legacy 不变 | `tmp/etf_pm_only_probe.py`（复用步骤 1 的 P1–P4 输入，全部真实行） | P1/P2（默认路由）仍 `BandContractError: halfday clock requires ETF am and pm bars`；**P1p/P2p（pm_only）跑通且两者结果完全一致**（补/不补 §8.1 合成 pm bar 无差别 → 证明不依赖任何 ETF 半日 bar）；P3 对照不变（权益 200,000）；**P4 legacy 与步骤 1 记录逐字段一致**（2015-01-08 pm 成交 8,100 份 @2.445、佣金 5、结算现金 180,190.5、权益 199,946.4）；P4p（pm_only 动态）同价成交且决策点→次日 pm 路由、手算到分。JSON 输出重跑字节稳定（sha256 `fda7fff8b2e1fde6`） |

手算留痕：P4/P4p 各 1 组（份额/佣金/印花/现金/权益/持仓市值逐项，`tmp/etf_pm_only_probe.json` 的 `hand_checks`）。

## 4. 双签

- **第一签（语义节执行者，本任务执行方）**：实现 + 上表全部验收亲跑；pin
  `d4b6c3764780e6dec5443174bb8fb0c1ca57ffd737da4e59069cbd3ca6735ed6`。
- **第二签（独立复核代理 `EngineDoubleSign`，2026-09-21，6m53s）**：结论 **APPROVE**
  （零 CRITICAL、零 MAJOR、1 项 P3）；完整报告 `verification_report.md`（含复核方逐项
  数字、最强/最弱证据与 0.85 置信度）。
- **发现处置（F1，P3）**：`t1_am_...` 原断言不可证伪（provider 处处返 None）→ 已按复核
  方案改为"提交真实单 + am 会话零事件"，并顺带纠正 t1 内一处注释误标（C1）、把冒烟
  runner 中恒真的 am 判据替换为可证伪的 `routing_no_etf_order_in_any_am_session`（C2）；
  测试文件 sha 因此由 `d4dbd177…` 变为 `fd29fa21…`，冒烟重跑仍 16 笔、判据全过。
  引擎文件在复核后**未被改动**（sha 不变），故 [1][2][5] 结论有效。
- **复核方无法验证项（如实转述）**：改动前引擎文本盘上无副本、仓库无 VCS，因此
  "默认路径不变"只能靠结构论证 + 逐字节锚 + 全仓绿，**不能做源码 diff**。
- **增量再确认（同代理，处置后）**：D1 测试（sha `fd29fa21…`，除注释与该项断言外其余
  测试逐行实质未变 → 8 passed）、D2 冒烟（19 项判据全 True、8 个数据产物逐字节不变、
  manifest 自洽）、D3 引擎未改（src 与 .venv 副本仍 `d4b6c376…`）全部 PASS，
  **对最终字节的 APPROVE 维持有效**。三条卫生级意见（pyc 入哈希 / 确定性表述过时 /
  判据计数口径）已全部处置，详见 `verification_report.md` §4。

## 5. 限制、披露与偏差

1. **未改动清单**：不动 F3R3 运行目录（其最新文件 mtime 仍为 2026-09-21T02:56:19）、
   不动任务①目录；未补 ETF 日内数据、未合成任何 am bar；未读 2021–2024 与 2025+。
2. **T+0 可观测性**：pm-only 下 ETF 每笔 live session 均为 pm，同日买卖回转
   **结构上不可观测**（引擎既有文档即如此声明）；冒烟判据因此落在"t_plus=0 标注 +
   成交行 is_etf + 减仓数量=全持仓可卖的手算核对"，未以合成 am bar 制造观测面。
3. **版本标签连带**：`engine_version` 由 v1.4.1 升到 v1.5，`tests/test_band_engine_v14_zones.py`
   两处断言随之推进（先例 S-v13-3：锚比较规则 = 数据产物逐字节相等 + stats 剔除
   `{engine_version, wall_s}` 后逐键相等）。
4. **`stats` 无新增键**：pm-only 的信息体现在既有 `etf_leg.routing` 与
   `dynamic_layer.state_transition` 字符串分支（仅在 pm_only 下变化），
   因此默认路由下 `stats` 与 v1.4.1 的差异仍只有 `engine_version`。
5. **测试环境抖动**：首轮全仓测试出现一次 `OSError Win32 GetLastError() = 33`
   （Windows 文件锁，`tests/test_band_contract.py::test_06c_split_loader_anchor_regression`，
   与本次改动无关）：该单测单独重跑通过、全仓重跑 638 passed / exit 0。
6. **并发工作流提醒（交整合方）**：并行推进的账户级风控任务① 以其预登记把引擎 pin 冻结在
   `bcbdd44bb855b803`（v1.4.1）。本任务按决策扩展引擎后，该 pin 对**新运行**会 fail-closed
   拒绝；其已产出的运行目录不受影响（产物已冻结）。整合方需在台账/主计划中登记引擎
   版本推进与两任务 pin 的实际关系。
7. **一次性执行差错（留痕，不影响结论）**：F3R3 锚脚本首次拷贝时把说明文字插到了
   模块 docstring 内部（未闭合的三引号），导致该副本语法错误、未产生任何输出；
   已改为注释块并重新拷贝（正文与源脚本逐字节一致，脚本内自检打印）。失败日志留档
   `logs/f3r3_anchor_first_attempt_failed_copylog.txt`。

8. **覆盖说明（如实）**：四项针对性测试的 pm 路由用例走 **provider 入口**；静态意图帧
   入口在 pm_only 下只覆盖了"am ETF 意图拒绝"（t2）。两个入口的行校验不同，但 pm 路由
   与执行 bar 取用是同一段代码（`intent_step` 生成 + `session_bar`），且探针 P4p 与冒烟的
   实际成交均经该段；如需静态帧 pm 用例，建议在混合主线预登记时一并补。


## 6. 交整合方清单（本任务不自行改动主计划/README/台账）

1. 主计划 `docs/plans/daily-short-term-rebuild.md`：记一节「2026-09-21 ETF pm-only 路由落地
   + 动态冒烟」（引擎 v1.5 pin、三锚零回归、四项测试、探针闭环、冒烟五链全过、试验计数 0）；
   并把待办第 2 条（ETF 主源的动态主线冒烟）从"待跑"改为"链路已打开，待混合主线预登记"。
2. README：引擎版本行与测试计数（**630 → 638**）同步；冒烟 run 目录与两份报告入链。
3. 台账/试验计数：本任务**零试验消费**；如需登记，写"工程项"而非 trial。
4. 任务① 的 pin 事实：其预登记把引擎冻结在 `bcbdd44bb855b803`（v1.4.1），本任务后工作区
   引擎为 v1.5 `d4b6c3764780e6de…`；任务①若重启新运行需重 pin，并在其 manifest 登记
   "任务② 已推进引擎版本"。两份 pin 并存的事实建议在台账写一行。
5. 契约 `docs/plans/p3-band-contract.md` §8.2 已加一行指向本决策的 pm_only 实现（本任务改）；
   如整合方有统一文档口径，可在主计划里引用该行。
6. 未决（不在本任务范围）：混合主线（股票半日线 + ETF pm-only 腿同账本）的正式预登记；
   ETF 日内数据是否补拉（决策 (a) 路径，需用户授权）。