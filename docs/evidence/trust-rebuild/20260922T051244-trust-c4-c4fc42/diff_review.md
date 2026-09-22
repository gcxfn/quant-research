# C4 改动清单与「无夹带」声明（diff_review）

- run_id：`20260922T051244-trust-c4-c4fc42`
- 代码提交：`ae226d964b1ea1dccfb60a42ae943c6da8a179e6`（工作树含未提交批次）
- 性质：本文件逐项列出 **C4 本轮实际改动**，并把 C4 之前的未提交批次与 C4 改动分开；
  同时声明没有任何策略参数、费率、阈值或测试预期的改动。

## 1. 改动归属（先分清谁改的）

C4 开始前工作树已存在的未提交修改（**C4 未触碰**，仅作背景）：

| 文件 | 归属 | 说明 |
|---|---|---|
| `README.md` | 更早批次 | C4 未改（git diff 仍显示其既有改动） |
| `docs/plans/daily-short-term-rebuild.md` | 更早批次 | C4 未改 |
| `docs/research/exp-20260921-event-families.md` | C0 复审更正 | 2026-09-22 首年/BM2/B1 归因注记，C4 只复核、未再改 |
| `docs/research/exp-20260921-eventfam-attribution.md` | C0 复审更正 | §0 C0 修订，C4 只引用、未再改 |
| `docs/research/stock_cash_baseline.md` | C0 复审更正 | §3 可加性撤回，C4 只引用、未再改 |
| `docs/research/stock_event_research_prereg.md` | C0 复审更正 + **C4 一行补注** | 见下 §2 |
| `docs/evidence/affected_runs.csv` | 更早批次 2 行 + **C4 4 行** | 见下 §2 |
| `src/quant/research/event_family_signals.py` | C0 归因修正批次（`b1_strict_numeric` 等） | C4 未改；其 sha256 `994d6d09…` 与 attrib2 run pin 逐字节一致 |

结论：**C4 只改动了 3 个此前干净的已跟踪文件 + 2 个新决策文档 + 1 个既有未提交文件的一行补注 + C4 证据目录**。

## 2. C4 本轮改动（逐项）

| # | 文件 | 改动 | 性质 | 是否触碰策略/费用 |
|---|---|---|---|---|
| D1 | `docs/plans/p3-band-contract.md` | **追加** §11「合同文本修订：停牌/无行情日估值 mark 口径」（+9 行，无删除） | 合同文字补写既有实现事实 | 否 |
| D2 | `docs/evidence/trust-rebuild/20260922T020344-trust-c1-479c46/interface_contract.json` | `schema_version` 1.0→1.1；`ledger_snapshots.valuation` 补写 carry-forward，新增 `valuation_implementation`；新增顶层 `amendments[]`（A-01） | C1 未提交新文件的口径同步 | 否（未动 `fee_schema`、`entry_price_dual_track` 等） |
| D3 | `docs/decisions/2026-09-22-fifo-vs-per-clip-risk-intent.md` | 新建（C4-DEF-01 裁决） | 决策记录 | 否 |
| D4 | `docs/decisions/2026-09-22-seat-ledger-source-and-cap-snapshot.md` | 新建（C4-DEF-02 裁决） | 决策记录 | 否 |
| D5 | `docs/evidence/affected_runs.csv` | **追加 4 行** attrib2 运行（001213/001713/002000/002611），旧 17 行未删未改 | 台账补登 | 否 |
| D6 | `docs/evidence/trial-ledger.md` | **追加**「C4 补登」节（+36 行，无删除） | 分账 + engineering_replay 登记 | 否 |
| D7 | `docs/evidence/trial-ledger.json` | 新增顶层键 `c4_registration`（旧键逐键相等，见校验） | 机器可读补登 | 否 |
| D8 | `docs/research/stock_event_research_prereg.md` | §7 **追加** BM2 最低佣金伪影补注（约 +12 行，无删除） | 披露性补注（旧判定与数字留档不改） | 否 |
| D9 | `docs/evidence/trust-rebuild/20260922T051244-trust-c4-c4fc42/*` | 新建证据目录（见下 §3） | 交付物 | 否 |

**无 src 代码改动**：
`git diff --stat -- src/quant/backtest src/quant/portfolio` 输出为空（exit 0）；
`src/quant/research/` 下 C4 未增删任何文件，唯一被修改的 `event_family_signals.py` 属 C4 之前的
C0 归因批次（哈希与 attrib2 运行 pin 一致，见 `run_manifest.json`）。

## 3. C4 证据目录内容（新文件）

| 文件 | 用途 |
|---|---|
| `issue_register.csv` | 8 个问题逐行（3 个 C4-DEF + 5 个 C4-OBS），含合同条款/反例/独立预期/证据/处置 |
| `diff_review.md` | 本文件 |
| `anchor_comparison.csv` | 20 个锚/控制项，修复前后语义等价 |
| `claim_correction_log.csv` | 主计划 §9 六项旧解释的 old→corrected 落账 |
| `c4_first_year_recompute.py` / `.json` | 首年与分年收益独立复算（只读归档曲线） |
| `c4def01_fifo_analysis.py` / `.json` | FIFO vs 逐批风险意图调查（源码文本 + B1 真实成交） |
| `c4def02_cap_scan.py` / `.json` | 25% 帽是否绑定的全臂扫描（命中 0） |
| `run_manifest.json` | 本轮命令与源码起止哈希、测试运行清单 |
| `run_records/pytest_full.log` | 全量测试 stdout（804 passed / exit 0） |
| `run_records/pytest_nopath_failed.log` | 裸命令失败留档（环境问题，非代码问题） |
| `tests.xml` | 全量测试 junit（804/0/0/0） |
| `system_verdict.md` | G4 裁决与未覆盖局限 |
| `stage_report.json` | C4-01..08 逐门 + 哈希证据 |

## 4. 无夹带声明（逐项）

1. **未改任何策略参数**：席位上限、每席权重、D3 阈值/恢复/冷却、止损 ATR 倍数与区间、
   止盈 R 倍数、持有窗、信号排序、TTL、追价上限策略——全部未动。
2. **未改任何费率**：佣金 0.0001/最低 5 元、印花 0.001→0.0005 分段、过户费不计——
   未动；`interface_contract.fee_schema` 的 `rates_unchanged_by_c1` 语义仍成立。
3. **未改任何硬约束**：T+1、整手 100、涨跌停、停牌、25% 单名帽、100% 总仓、
   K=3 兜底与止盈无兜底——未动。
4. **未改任何测试或测试预期**：`tests/` 未被修改；全量 804 passed / 0 failed / 0 skipped。
   失败尝试（裸命令）只留档，未通过删测试或改断言规避。
5. **未重跑回测**：本轮零回测重跑；受影响的只是统计口径与文档/台账。
   无 A 项真缺陷触发重放（三项调查均以文档化关闭）。
6. **未删除任何历史行**：`affected_runs.csv` 旧 17 行、`trial-ledger.md` 旧行、
   `event-families/attribution/baseline` 旧段落全部在原地保留；改动一律追加。
7. **未读 2021+ 行情、未消费 val**：全轮只读 2015–2020 Dev 归档产物与文档。
8. **未做 git 提交/推送**：工作树保持未提交状态。

## 5. 关键校验（可复跑）

- `git diff --stat -- src/quant/backtest src/quant/portfolio` → 空。
- `git diff --numstat` → `docs/evidence/affected_runs.csv` 6/0（其中 C4 4 行）、
  `docs/evidence/trial-ledger.md` 36/0、`docs/plans/p3-band-contract.md` 9/0——**全为新增、零删除**。
- `trial-ledger.json` 校验：旧键逐键与 HEAD 相等，仅新增 `c4_registration`。
- `interface_contract.json` 校验：JSON 合法、schema 1.1、`amendments` 长度 1。
- 源码起止哈希：`band_engine.py 40f1aaeb…37abd`（= attrib2 pin）、
  `single_name_rules.py 9f9cf8c6…0e92`（= attrib2 pin）在轮内未变。
