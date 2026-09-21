# 证据血缘图审计报告（EG 代理，2026-09-11）

> **快照截止与更正标注（2026-09-11 晚，按 Codex round-2 复审 §3.5 补）**：本图快照截至 HEAD=`d7eeed7` 时点，其后的 wave1 复审（`system-audit-wave1-independent-review-20260911.md`）与修复波（`b9373ba`）不在图内。§3 第 5 条所引「R0 官方批 9 结构静默清零」系 **W1-05 已撤回的错误归属叙述**（首版扫描脚本 glob 漏 hypotheses/ 层，把 R1 行误记为 R0）——更正后命中面为 R0 250 行 1 命中（REV_cond_15）/R1 215 行 12 命中；TW-1 修复（`b9373ba`）后重扫全池 0 命中。引用本图时以本标注为准。本图为索引与审查线索，**不构成新的独立裁决**。

- **性质**：只读审计。结构化血缘（CLAIM→EXPERIMENT→CONFIG→DATA MANIFEST→CODE VERSION→ARTIFACT→METRIC→DECISION）已落盘 `artifacts/evidence-graph-20260911/graph.jsonl`（31 条 claim，逐条 JSON 校验通过、id 唯一）。
- **覆盖范围**：生产规则（V3/t0/short）、冻结门禁（Gate C/D、factor-miner 预登记与分区）、封存家族（MR/事件/粗筛/P3/P4/低波动/每日退出）、本周审计波（system-audit B-01..D-02、U/V/TW/DC/U2 轮）。
- **数据源**：`docs/decisions.md`（1170 行全读）、`docs/experiments/*.md` 结论与审查文档、`docs/plans/*.md`、`artifacts/` 一二级清单、`configs/` 清单、`git log --oneline -15`（只读，HEAD=`d7eeed7`）。所有引用的 config/artifact 路径经 `os.path.exists` 逐条核实。
- **协议-代码抽查（6 项）**：见 §2，6 项中 5 项一致、1 项不一致（高严重级）。

---

## 1. 总体结论

31 条 claim 中：COMPLETE 20、PARTIAL 10、BROKEN 1、STALE 0（STALE 类发现以条目形式落在 §3，对应 AGENTS.md 状态滞后，未单列 claim）。**核心承重结论（各封存家族 FAIL/无晋级、V3 R3 目标 FAIL、P3 八组全负）证据链全部完整**：预登记→config→工件→独立审核/Codex 复算环环可溯。最主要的破口不在研究结论层，而在**生产 ETF 池与冻结排除规则的冲突**（§2 第 6 项）与两处**审计闭环的开放依赖**（B-01 扫描未执行、Codex 终审未送）。

---

## 2. protocol_code_gap（冻结协议 vs 代码，逐项抽查）

| # | 抽查项 | 协议出处 | 代码落点 | 结果 |
|---|---|---|---|---|
| 1 | 17/27/37bps 成本阶梯 | 预登记 §5、factor-mining-program | `experiments/factor_miner/backtest.py:69` `COST_TIERS_BPS = (17, 27, 37)`，:313 白名单校验，:522 阶梯循环 | **一致** |
| 2 | Bonferroni α=0.10/N | 预登记 §5「每轮粗筛 α=0.10/N」 | `stats.py:204-216 _ci_spec`（n_tests 正 int → 端点 α/(2N)）；`director.py:669` `n_tests = len(units)` 自动派生（C-01 修复在位） | **一致**（审计波 C-01 曾发现固定 95%CI 缺陷，已修） |
| 3 | 考试分区日期 | 预登记 §1：TRAIN 2020–2022 / VALIDATION 2023–2024 / LOCKBOX 2025–2026.09 | `partition.py:23-26` `TRAIN=("2020-01-01","2022-12-31")` / `VALIDATION=("2023-01-01","2024-12-31")` / `LOCKBOX=("2025-01-01","2026-09-08")`；READ_END=LOCKBOX 右端 | **一致** |
| 4 | bootstrap 种子 20260909 | 预登记 §5、mr-statarb V3.1 | `mr_statarb.py:147 BOOTSTRAP_SEED = 20260909`；`factor_miner/stats.py:31` 直接复用 `mrs.BOOTSTRAP_SEED` | **一致** |
| 5 | T+1 | 预登记 §1/§5、项目红线 | `quant/execution.py:157-160` `sellable = shares − bought_today`；:149-151 `day_start` 重置 `bought_today`——当日买入不可卖 | **一致** |
| 6 | ETF 排除规则（QDII/债券/商品/货币/北交所） | D-2026-09-09-04：「排除QDII/跨境（513段及名称关键词）、债券、**商品**、货币、北交所……适用于一切ETF池构建」 | `configs/strategy.json` 生产池 55 只**含 sh518880 黄金ETF华安（group=黄金商品）与 sz159985 豆粕ETF华夏（group=豆粕商品）**；`scripts/build_pool.py:26-30` EXCLUDE 正则只剔跨境/债券/货币/REITs/北交所、**无商品关键词**，:45/:63 反而显式建立「黄金商品」「豆粕商品」分组；pool_note 自述「剔除跨境QDII/债券/货币/北交所」漏「商品」 | **不一致——高严重级** |

**#6 详情（本审计最高严重级发现）**：规则冻结于 2026-09-09，池构建于 2026-09-03（D-2026-09-03-03），但规则明文「适用于一切ETF池构建；剔除名单逐只留档」，且无任何豁免留档。更实的一层：`docs/decisions.md:1026` 记录首条 V3 生产信号（2026-09-04）Top3 即含 **sz159985 豆粕**——生产收益引擎已实际把商品 ETF 纳入轮动候选，与冻结规则直接冲突。次要疑点：sh517520 黄金股 ETF 跟踪股票指数、sh561360 石油ETF 标的指数性质待核实，若按「跟踪A股指数的股票型ETF」口径可能合规，不影响上述两只期货型商品 ETF 的定性。**建议**：或回溯排除两只商品 ETF 并重建池（属生产规则变更，须走决策留痕），或由用户明示豁免并补「剔除名单逐只留档」。

---

## 3. 审计发现清单

### 3.1 contradiction（表述冲突）
- **[高] 生产 ETF 池 vs 冻结排除规则**：同 §2 #6。依据：`configs/strategy.json`、`scripts/build_pool.py:26-30,45,63`、`docs/decisions.md`（D-2026-09-09-04 与 :1026 生产信号记录）互证。
- **[低·已自我披露] 17bps 构成 vs 用户确认费率**：`docs/plans/factor-mining-program-20260909.md` 的 17bps=佣金万1双边2bps+印花5bps+滑点双边10bps，佣金档与用户确认的股票万2.5 不同——`docs/experiments/top15-cost-breakeven-20260911.md` §7 出入清单第 1 条已如实列出，非隐蔽矛盾。
- **[中] D-2026-09-11-01「B-01..D-02 全部修复」vs B-01 扫描未执行**：决策宣称 9 项审计缺陷全部修复并对抗复验，而 `docs/experiments/system-audit-b01-train-scan-20260911.md` 明示「全市场正式扫描尚未执行」、SCAN 块为占位符；B-01 验收条款要求「命中因子从因子值节点重算」——受影响候选集合尚未枚举，修复与重算范围未闭合。非文字矛盾，属开放依赖（对应 C27 PARTIAL）。

### 3.2 orphan_claim（有结论、证据链有缺口）
- **[中] MR-statarb R1 FAIL 的工件复算环未闭合**：`D-2026-09-09-15` 记「待Codex复算确认后本轮封存」并留送审包 `mr-statarb-artifact-review-pack-20260909.md`，但全决策日志未见复算完成条目；后续（D-2026-09-10-06 等）已直接引用「MR R1 C 阶段 FAIL 封存」。工件本身在（`artifacts/mr-statarb/round-20260909/`），FAIL 判定数字可复算，但「经 Codex 复算确认」这一声明环节缺失。
- **[中] TW 组件边界审计 5 缺陷无独立文档**：仅以一段压缩文字存在于 `D-2026-09-11-01`，含「R0 官方批 9 结构静默清零」的重算级后果；扫描脚本在（`experiments/system_audit_constarg_scan_20260911.py`）但无 TW 结论文档与逐缺陷明细留档。
- **[低] C 机制拆分正式结果（M1/M2/M3）仅存 decisions.md**：`artifacts/v3-arm-c-mechanism/round-20260910-formal` 工件在，但 docs/experiments 下无结论文档，「判不确定」的可读依据只有决策日志。

### 3.3 orphan_artifact（工件无文档引用）
- **[低·在途] `artifacts/experiment-index-20260911/`**（`_batch5.json`、`experiments.jsonl`）：0 处文档引用。判断为并行 EX1 索引代理的在途产物，其对应报告落盘后应回链，暂不计为永久孤儿。
- **[低·与既有清点一致] `artifacts/audits/`、`artifacts/backtests/`、`artifacts/forward_log/`**：`docs/experiments/workspace-inventory-20260911.md:241,254` 已标「0 文档引用的历史目录，可归档」；本次复核 `artifacts/backtests` 的引用仅存在于该清点文档与 CHANGELOG（历史 V2 时代回测目录，20260903-04 时间戳），结论相互印证。
- 说明：`artifacts/analysis/`（含 v3-dd-attribution 工件）、`artifacts/experiments/`、`artifacts/signals/`、`artifacts/forecast-scores/`、`artifacts/data-census-20260911-smoke/` 均有具体路径级引用，非孤儿。

### 3.4 stale_claim（结论基于旧状态且无更新记录）
- **[中] AGENTS.md Scope 段两处状态滞后于决策日志**：①「官方TRAIN批以HEAD 06cb5d2运行中」——实际 06cb5d2 批已主动终止，7b2f530 重启批又于 22:53 无工件消失，「R0 维持挂起」（D-2026-09-10-34、D-2026-09-11-01）；②「PV1 round6……送审包待打包」——round6 已完成修复验收（D-2026-09-10-30）、round7 已 PASS（D-2026-09-10-33）。AGENTS.md 属用户维护文档，此条仅供更新参考，不构成研究结论错误。

### 3.5 broken_lineage（引用路径不存在）
- **无**。抽核的全部文档点名 config/artifact 路径（24 个）均存在。初次目录列举因 `head` 截断曾误判 `v3-repair-*`、`v3-daily-exit-*` 文档缺失，经逐文件核实全部存在——未落入报告。

### 3.6 复算可行性注记
- **[低·已自我披露] top15-cost-breakeven 无落盘工件**：计算脚本「用后即删」（文档原话），复算只能按文中公式手工进行。冻结事实引用（COST_TIERS、`DEFAULT_TRADE_NOTIONAL=50000`、proxy 角色）经代码核实一致。

---

## 4. 血缘完整性概览（按 lineage_status）

| 状态 | 数量 | claim |
|---|---|---|
| COMPLETE | 20 | C01,C02,C03,C05,C06,C08,C09,C12,C13,C14,C15,C16,C17,C19,C20,C22,C23,C24,C25,C29 |
| PARTIAL | 10 | C04,C07,C11,C18,C21,C26,C27,C28,C30,C31 |
| BROKEN | 1 | C10（ETF 排除规则→生产池实现断链） |
| STALE | 0 | （AGENTS.md 滞后以 §3.4 条目形式记录） |

各 PARTIAL 的具体缺口（缺哪一环、查了什么）逐条写在 graph.jsonl 的 `lineage_basis` 字段：C04 生产规则无单一实验链；C07 缺独立结论文档；C11 缺 Codex 复算完成记录；C18 独立审查/样本外未完成（文档自认）；C21 死因未定（自认）；C26 Codex 终审未送；C27 正式扫描未执行；C28 无独立明细文档；C30 工件被有意删除；C31 状态型结论、代码侧未逐行复核。

---

## 5. 审计方法与边界

- 只读；除本报告与 `artifacts/evidence-graph-20260911/graph.jsonl` 外零写入；git 仅 `log --oneline`；未读 `data/raw/` 内容。
- claim_text/key_metrics 均为文档原文摘抄（≤3 条）；lineage_status 判定依据逐条注明核实对象（文档存在性、`os.path.exists` 路径核实、代码 grep/sed 实读、决策日志交叉引用）。
- 时间预算内完成全部 6 项协议-代码抽查；未重跑任何测试套件（1468 OK 等数字只作记录引用，不作独立复验）。
