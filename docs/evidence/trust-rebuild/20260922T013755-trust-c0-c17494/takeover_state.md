# C0 接管状态（takeover_state）

- 阶段：C0（接管与合同冻结）
- 本文件所属 run：`20260922T013755-trust-c0-c17494`
- 记录时间（UTC）：2026-09-21T17:31Z—17:45Z（本机本地时间 2026-09-22 01:31—01:45）
- 记录者：实施者 I（ZCode 会话，模型 new-provider/deepseek-v4.1-flash）
- 性质：现状接管记录。不包含策略运行、不包含新的收益数字。

## 1. 版本与工作树（实测）

| 项 | 值 | 来源命令 |
|---|---|---|
| remote | `origin https://github.com/gcxfn/quant-research.git`（fetch/push 同址） | `git remote -v` |
| 分支 | `main`（本地与 `origin/main` 都存在，无其他分支） | `git branch -a` |
| HEAD | `ae226d964b1ea1dccfb60a42ae943c6da8a179e6` | `git rev-parse HEAD` |
| 计划基准提交 | `ae226d964b1ea1dccfb60a42ae943c6da8a179e6`（执行包 `01_master_plan.md` 与 `03_governance.json` 记录值） | 文本核对 |
| HEAD 与基准 | **完全同一提交**，不存在“基准之后已有提交” | `git rev-parse HEAD` |
| 提交历史 | 共 5 个提交：`ae226d9`（2026-09-21 23:58）、`c09a8ff`（23:29）、`7f3469d`（22:47）、`9490b14`（17:31）、`0c4e3a2`（17:30） | `git log --oneline -20` |
| 工作树 | 不干净：8 个已修改、7 个未跟踪条目（其中 4 个是运行目录） | `git status --porcelain` |

### `git status --porcelain` 原样输出

```text
 M README.md
 M docs/evidence/affected_runs.csv
 M docs/plans/daily-short-term-rebuild.md
 M docs/research/exp-20260921-event-families.md
 M docs/research/exp-20260921-eventfam-attribution.md
 M docs/research/stock_cash_baseline.md
 M docs/research/stock_event_research_prereg.md
 M src/quant/research/event_family_signals.py
?? artifacts/runs/20260922T001213-eventfam-attrib2-837163/
?? artifacts/runs/20260922T001713-eventfam-attrib2-cdf1e1/
?? artifacts/runs/20260922T002000-eventfam-attrib2-10a787/
?? artifacts/runs/20260922T002611-eventfam-attrib2-eed5cf/
?? docs/quant_stage_plan_20260922/
?? src/quant/research/attribution_lib.py
?? tests/test_event_attribution_c0.py
```

### 规模

`git diff --stat`：8 个文件、165 行新增、34 行删除。未执行 reset / clean / stash，现场保持原样。

## 2. 每个未提交文件的性质判断

判断依据：逐文件 `git diff`、run manifest、文件 mtime、以及文件内自述。

| 文件 | 性质 | 依据 |
|---|---|---|
| `README.md` | 2026-09-22 凌晨的进度刷新：把“阶段 A/B 复审落地、C0 归因修正完成、713 项测试”写进首页，并撤回旧的“执行摩擦上界/信号残差”读法 | `git diff README.md`；第 3-8 行 |
| `docs/research/exp-20260921-eventfam-attribution.md` | 新增 §0「C0 修订」，明确宣布 §1–§6 的部分表述被撤回（B1 因果改口径、+5.99pp 须与均值对均值 +3.66pp 并列、type 分支说法撤回） | `git diff`；§0 第 14-70 行 |
| `docs/research/exp-20260921-event-families.md` | 2026-09-22 更正：补入 2015 年分年口径（A1 +14.05%/A2 +2.60%），撤回“六年全负/对 BM1 六年全输”，更正 B1-floor 归因 | `git diff`；§分年与 §5B 区块 |
| `docs/research/stock_cash_baseline.md` | 2026-09-22 撤回五层拆解的可加性读法与 `−0.64pp` 残差归因，改标“成对差异不可加总” | `git diff`；§3 表格与残差段 |
| `docs/research/stock_event_research_prereg.md` | 追加第 7 节「运行后披露」：102 事件 type_upgrade 0 / numeric_revision 102；新增 `b1_strict_numeric` 参数说明。冻结的第 1–6 节未改 | `git diff`；文件末尾 |
| `docs/evidence/affected_runs.csv` | 补记两行受影响运行：`20260921T230639-eventfam-attrib-f38756`（归因 v1 五项缺陷，B1 已复算、B2/A 未复算）与 `20260921T223157-eventfam-main-cb4cff`（`year_returns()` 漏首年） | `git diff`；文件末尾两行 |
| `docs/plans/daily-short-term-rebuild.md` | 追加一段 2026-09-22 完成记录，逐条列出六项核心更正、测试新增 10 项、713 passed、零尝试消费、以及“中间运行留痕不引用”的三个 run | `git diff`；文件末尾段 |
| `src/quant/research/event_family_signals.py` | **代码改动**：新增 `FamilyParams.b1_strict_numeric`（默认 False）、`BEvent` 四个诊断字段（end_date / update_flag / type_upgrade / numeric_revision / numeric_available），触发逻辑改为 `numeric_revision or improved`（默认行为等价）。文件哈希 `994d6d09de4932a56918645cbc2c4686f81459a006cf454a70299abd6bd0ba5d` 与两个 attrib2 运行的 manifest pin 一致 | `git diff`；manifest `pins.event_family_signals` |
| `src/quant/research/attribution_lib.py` | 未跟踪新增库：边界感知收益窗（`tr_window`）、漏斗分类、成交成本起算收益、FIFO + 分红时序净损益。最终版哈希 `0867f740546cd06d855c2ca1b20fb90c8b0122bef1a8e1eb8678aa9635569deb`（前两次运行 pin 的是 `f3f0a6fb…`，说明中间被改过） | 文件头注释；三个 attrib2 manifest 的 pin |
| `tests/test_event_attribution_c0.py` | 未跟踪新增测试，自述覆盖边界、2021+ 改写不变性、严格数值臂、漏斗分类、FIFO/分红时序 | 文件内容与 `daily-short-term-rebuild.md` 追加段 |
| `artifacts/runs/20260922T001213-eventfam-attrib2-837163/` | **失败运行**（`status=failed`，`missing engine order for submission sz.002299 2019-01-09 am`），无 outputs | `manifest.json` |
| `artifacts/runs/20260922T001713-eventfam-attrib2-cdf1e1/` | 完成但被取代（attribution_lib pin `f3f0a6fb…`） | `manifest.json`；项目文档自述 |
| `artifacts/runs/20260922T002000-eventfam-attrib2-10a787/` | 完成但被取代（同上 pin） | `manifest.json` |
| `artifacts/runs/20260922T002611-eventfam-attrib2-eed5cf/` | 当前有效：B1 归因 v2，`status=completed`，88 秒，零尝试消费，identity 断言（fills/equity/触发计数与主运行逐位相等） | `manifest.json` |
| `docs/quant_stage_plan_20260922/` | 本次用户下发的阶段执行包（含本 C0 的授权指令），未入库 | 目录内容 |

**总体判断**：这 7 项未跟踪条目 + 8 项已修改全部属于**同一批工作**（2026-09-22 凌晨的“阶段 A/B 复审落地修正”，见 `daily-short-term-rebuild.md` 末段），与执行包同批产生、互不冲突。它们不是散落的意外改动。

## 3. 与基准提交 `ae226d9` 的差异结论：是否已有 C 类进展

**结论：未发现按执行包定义的 C1–C9 阶段进展。**

搜索范围（实际执行）：

1. `git log --oneline -20`：只有 5 个提交，最新 `ae226d9` 时间 2026-09-21 23:58，早于执行包文件 mtime（2026-09-21 16:51）之后的任何新提交；2026-09-22 无新提交。
2. 全仓库内容检索（排除执行包目录本身）：把 `trust-rebuild`、`stock-first-trust`、`contract_snapshot`、`access_ledger`、`evidence_index`、`acceptance_matrix` 作为关键词在整个工作树检索 → **零命中**（即除执行包外没有任何文件按新计划命名或引用新阶段产物）。
3. 阶段标识检索：`C1-S`、`C1 臂`、`S 臂` → 只命中 `README.md` 与归因文档对“若重开，方向是 C1-S 臂（席位接纳优先级）”的文字建议，属研究建议，不是已执行的阶段。
4. 未跟踪文件清单：只有执行包、归因修正的 4 个运行、1 个新库、1 个测试文件；没有 C1 数据隔离产物、没有 reference ledger 源码、没有 matcher。
5. 分支：只有 `main` 与 `origin/main`，没有为阶段实施另开的分支或 worktree。

**发现的“看起来像 C 类”的东西，其实是另一件事（命名撞车）**：

仓库现有文档里的 “C0” 指的是**2026-09-22 的 B1 归因修正最小方案**（用户复审文档 §八-C0，见 `README.md` 第 5 行、`docs/plans/daily-short-term-rebuild.md` 第 399 行、`exp-20260921-eventfam-attribution.md` §0、以及 4 个 `*-attrib2-*` 运行的 `role` 字段写着 `C0-correction`）。这与执行包的**阶段 C0（接管与合同冻结）**是完全不同的两件事，必须区分，已列为冲突 `C-11`。

另外，仓库里的 `C1`/`C2`/`C3`/`C4`/`Q1`/`Q2` 是更早的**源码复审编号**（`docs/code_audit_stock_first.md`），也与执行包的 C 阶段无关。

## 4. 证据缺口（本阶段新发现，不是推断）

1. **授权依据文档缺失**：归因 v2 运行自述“Review doc: `quant_phase_ab_review_20260921` §三/§四/§八-C0”，但该复审文档在仓库内不存在（全树 `find`/`grep` 均未命中）。因此“按用户复审文档执行”的原始指令无法在仓库内独立核验，只能从它的效果反推。见 `access_ledger.csv` AL-09。
2. **测试声明缺归档日志**：`README.md` 与旧主计划都写“全仓 713 项测试通过”（2026-09-22），但 `docs/evidence/` 下只有 2026-09-21 两轮 pytest 日志，没有对应 2026-09-22 的日志文件。C0 未运行测试（不在授权范围），所以该数字在本阶段属**未复核声明**。
3. **受影响清单不完整**：`docs/evidence/affected_runs.csv` 补记了 2 行，但 4 个 attrib2 运行（含 `status=failed` 的 `20260922T001213`）都没有登记。失败运行的存在只由旧主计划正文一行文字承载。
4. **失败运行与中间运行**：`20260922T001213` 与执行版本差异较大（无 `role` 字段、无 outputs），只能作失败留痕，不得引用其数字。

## 5. 本文件不声称的内容

- 没有重跑任何回测、测试或因子计算；第 1 节的版本信息全部来自 git 命令的原样输出。
- 没有读取 2021 年以后行情数据、没有读取任何 Val 收益（读取范围见 `access_ledger.csv` AL-07）。
- 没有修改任何已跟踪文件；本轮改动清单见 `change_scope_review.md`。
