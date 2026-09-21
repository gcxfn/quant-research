# R0 执行准备盘点（任务A · 只读）

- 日期：2026-09-11。执行：GLM-5.3/MAX（严格代理模式），主对话派发。
- 任务边界：只读盘点 + 本报告为唯一写入；不改代码、不触他人未提交修改、不启动正式批次（待主对话运行前裁决）；**未读取任何 VALIDATION/LOCKBOX 数值**（仅读 TRAIN 侧代码、目录结构与进程状态）。
- 依据：`docs/plans/r0-completion-and-acceptance-plan-20260911.md`（修订稿）+ `docs/experiments/r0-system-plan-review-20260911.md`（原计划审查）+ 用户 2026-09-11 运行方案原则（受审字节隔离快照+外置启动/完成验收器，不为统一入口改引擎）。

## 1. 盘点方法（关键命令，可复现）

- `git status --short` / `git rev-parse HEAD` / `git log --oneline -5`
- `Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'factor_miner|factor-miner|r0' }`（及 Name LIKE '%python%' 全量）
- `Get-ChildItem artifacts/factor-miner -Recurse`（批次/工件存在性）
- `rg -n "REAL_RUN_UNLOCKED|enforce_code_identity|data_version|os.makedirs(out_dir)" experiments/factor_miner`
- 受审文件核验：按 `audited_code_paths()` 语义重建 46 文件全集后 `git status --porcelain -- <46文件>`

## 2. 已证事实

### 2.1 git 与受审身份

- HEAD = `0fb349b34190dc941099dd3224703c9c6c5d7e1d`（D-2026-09-11-08，wave2 六缺陷闭合；wave3 送审包同 commit 入库）。
- 工作区脏：17 个 modified + 大量 untracked，全部属系统审计/其他研究线（quant/backtest.py、quant/portfolio_candidate.py、experiments/system_audit_b01_train_scan_20260911.py 等）。
- **受审文件全集 46 个**（experiments/factor_miner/*.py ×15 + tests/test_factor_miner*.py ×25 + 预登记文档 + 5 个显式运行依赖：experiments/mr_statarb.py、quant/history.py、quant/market.py、prompts/researcher_v1.md、configs/short-foundation-research.json）。实测 `git status --porcelain -- <46文件>` **输出为空** → 全部 tracked+干净 → 当前主工作区即可通过 `enforce_code_identity()`（静态推断，未实跑引擎验证）。

### 2.2 进程

- **无任何 R0/factor_miner 进程在跑**；旧官方批 PID 31976（7b2f530）已不存在。
- 在跑两个 python（PID 5984 包装 / 24148 真身，2026-09-11 08:17:49 起）：`experiments/system_audit_b01_train_scan_20260911.py --scan --report docs/experiments/system-audit-b01-train-scan-20260911.md`——B01 TRAIN 扫描（审计线，报告文件正被改写），**不可杀、正式批不得与之并行**。命令行无凭据类参数。

### 2.3 批次与工件（防重复结论）

- `artifacts/factor-miner/r0-20260910/` **仅含 hypotheses/ 输入目录，无任何 run_meta.json/candidates.jsonl/registry.jsonl 输出** → R0 官方 TRAIN 从未落盘完成。
- 两个 0 字节日志实证失败无痕：`artifacts/factor-miner/r0-20260910-train.run.log`（16:24）、`r0-train-7b2f530.run.log`（19:19）。
- decisions.md 三次尝试史：15:39 首启主动终止（测试修复改受审文件）；16:17 PID 7884 因 CS_RANK O(S²·D) 确诊被杀；19:19 PID 31976 于 22:53 无工件消失（死因未定，疑并发内存竞争），用户当时指示暂不重启。
- 结论：**无在跑批次、无已完成批次**；新批必须全新目录（引擎 `_check_out_dir_free` 独占强制），无重复批次风险。

### 2.4 冻结候选与正式入口

- 冻结输入：`artifacts/factor-miner/r0-20260910/hypotheses/_all_raw.jsonl`（303,444 B，实测 250 行，2026-09-10 15:34）+ 18 个研究员分文件；`_wave1_merged.jsonl` 118 行（115 结构，历史口径）。246 结构为历史去重口径，按 R0-2 要求以实际冻结输入复核、不预填计数。
- R1 输入在 `artifacts/factor-miner/r1-pool-20260911/`（16 文件）——另一条线，不得混入 R0。
- 正式入口：`python -m experiments.factor_miner.director pipeline --hypotheses <_all_raw.jsonl 绝对路径> --out <全新目录> --allow-real-run`。`director.py:37`：`REAL_RUN_UNLOCKED = True`；真实通道数据读取前 `enforce_code_identity()` fail-closed；enforce_window 单区域只读 TRAIN；VALIDATION/LOCKBOX 走独立子命令且程序上未授权。

### 2.5 上轮三问题核对——全部仍在（原文摘录）

1. **data_version 仅批次 id**（`experiments/factor_miner/data_fields.py:129-131`）：
   ~~~python
   def data_version():
       """registry 用：各来源批次目录 id 串联（换批次=新研究身份）。"""
       return "|".join("%s=%s" % (k, v) for k, v in sorted(DATA_VERSION_PARTS.items()))
   ~~~
   DATA_VERSION_PARTS 六键：PRICE=user_dataset_20260903+baostock_daily；VALUATION=tushare_daily_basic_20260909-r1；BENCH=tushare_sw_index_daily_20260909-r3；FLOW_MARGIN=tushare_margin_detail_20260909-r1；FLOW_LHB=tushare_top_list_20260909-r1+top_inst_20260909-r3；EVENT=tushare_event_tables_20260909-batches。无任何内容哈希。
2. **代码结束身份缺失（无尾采）**：`director.py:989` 仅在数据读取前 enforce 一次（`code_id = enforce_code_identity()`）；run_meta.code_identity 为启动时快照；candidates 行仅携带 `{"git_head": ..., "n_files": ...}`（:1069-1070）；运行结束无任何再次校验。
3. **启动失败无记录**（`director.py:1006-1009`）：
   ~~~python
   train_results, bt_results, factors = evaluate_units(...)
   os.makedirs(out_dir)   # 独占新批次（竞态下已存在会直接抛）
   ~~~
   评估期崩溃零工件零留痕；两个 0 字节 run.log 为实证。lockbox 路径已有 FAILED run_log（error_type/error_message/pid）而 TRAIN 路径无——不对称。

### 2.6 wave3 审核与 S0 工件

- wave3 送审包已入库（`docs/experiments/system-audit-fix-wave3-review-pack-20260911.md`，随 0fb349b），**待外部 round-3 裁决**；包内自述"PASS 前不重启 R0、不改变 VALIDATION/LOCKBOX 状态"。
- 探针仪器：`experiments/system_audit_wave2_independent_probe_20260911.py` + 三份 JSON（-json/-rerun/-postfix）。
- S0 侧工件已存在（workspace-inventory / evidence-graph / experiment-index / data-census，均 20260911）；B01 扫描进行中。
- "全仓 1697 测试 OK"为送审方自报，本轮未独立重跑（未知）。

## 3. R0 依赖与阻断清单

| # | 阻断 | 状态 | 关闭方式 |
|---|---|---|---|
| B1 | wave3 送审包外部复审（=新计划 R0-1） | 待裁决 | 外部 Codex round-3 |
| B2 | numpy 双路径 A 阶段裁决与正式引擎选择（纯 py vs numpy） | 未闭合 | 主对话据 wave3/双路径证据裁决 |
| B3 | MT 变异测试幸存者清零（用户 2026-09-11 批准前置） | 未执行 | MT-run 独占期执行+分诊 |
| B4 | R0-3 启动包三缺口（数据内容身份/首尾双采/失败记录） | 已证仍缺，最小路径已判可行（§4） | 按 §6 任务实施 |
| B5 | 资源独占：B01 扫描在跑；22:53 无工件消失事故教训 | 占用中 | 等待/错峰+OS 分离启动器 |
| B6 | 修订计划本身"待独立复核" | 流程项 | 主对话安排 |
| B7 | 主对话运行前裁决（用户本轮指令） | 待 B1-B5 | 启动包齐备后裁决 |

依赖关系：B4 各任务可先行准备（只读+新目录，不影响他人）；正式启动需 B1+B2+B3+B5+B7 同时满足。

## 4. 最小修复路径判断（按用户原则，未实施）

1. **隔离快照合规 enforce——可行**。`enforce_code_identity()` 用 `git ls-files` + `git status --porcelain`（cwd=_ROOT；_ROOT 由模块 __file__ 上推三级，快照内自然指向快照根）→ 快照必须是真 git 检出。方案：`git worktree add --detach <path> <裁决提交>`（或本地 clone，避免动主仓 .git 元数据）。受审 46 文件在快照内 tracked+clean → enforce 通过；git_head=裁决提交，溯源清晰；启动包 ledger 显式标注主树脏态快照来源。
2. **数据引用不复制全集**。装载路径：`data_fields.py:174-176` `_REPO_ROOT`（模块推导）+`TUSHARE_ROOT=<_REPO_ROOT>/data/raw/tushare`；价格根经 mr_statarb init_runtime 读 `configs/short-foundation-research.json`（随快照检出，本身受审）。快照内以 Windows junction 指向主仓 `data/`（只读纪律），不复制。junction 端到端未演练（R0-3 小样本时验）。
3. **数据内容身份——外置 manifest**。复用 PV1 round5 内容哈希法，覆盖 R0 实际读取根：PRICE（user_dataset/2026-09-03 qfq zip + baostock daily + adjust_factor，PV1 r5 已有 11,792 文件 manifest 可复用）、daily_basic/20260909-r1、sw_index_daily/20260909-r3、margin_detail/20260909-r1、top_list/20260909-r1 + top_inst/20260909-r3。启动前/完成时双算比对，漂移→identity_drift 不得验收。`data_version()` 本身不改（批次 id 仍入 run_meta，manifest 为补充身份账）。
4. **首尾双采+失败记录——外置启动器/验收器**。OS 级分离启动（Start-Process Hidden + `python -u` 行缓冲 stdout/stderr 落盘）+ ledger JSONL（启动时间/PID/命令/环境/退出码/结束时间）；完成验收器在退出后重算 46 受审文件 sha256 + 数据 manifest + 候选文件哈希 vs 启动前清单；`run_meta.json` 缺失 → 记 FAILED（含 stderr 尾部）。引擎零改动；makedirs-after-evaluate 行为保留，由验收器补中断证据。
5. **新输出目录**：`artifacts/factor-miner/r0-train-<commit8>-<ts>/`（绝对路径传 --out）。

## 5. 未知项（不推断）

- 全仓测试当前是否绿（未独立重跑）；
- junction 快照内端到端装载（未演练）；
- B01 扫描预计结束时间；
- numpy 干净环境性能实测（D-34 遗留）；
- 246/115 计数须以实际冻结输入复核（R0-2 不预填）。

## 6. 最小实施任务清单（建议派发顺序，均不改引擎）

1. **T1 启动包生成器**（新脚本）：固定受审 46 文件清单+sha256、配置、候选文件哈希、命令模板、资源上限。
2. **T2 数据 manifest 生成器**（新脚本，只读）：§4.3 五根内容哈希清单。
3. **T3 快照建立演练**：worktree --detach + data junction + 快照内 enforce 通过性验证 + dev-smoke-train（只读 TRAIN）装载演练。
4. **T4 分离启动器+完成验收器**（新脚本）：§4.4 全项。
5. **T5 R0-3 小样本演练**：临时目录合成数据走真实编排（数据→因子→统计→账本→工件→验收器），不触 VALIDATION/LOCKBOX。

每项交付后主对话审核；T1-T5 全过 → 运行前裁决 → R0-4 正式 TRAIN。

## 7. 纪律声明

本轮唯一写入=本报告；零代码修改；未触 B01 进程与他人未提交修改；未读 VALIDATION/LOCKBOX 数值；未启动任何正式批次；原始数据全程只读。

## 8. 增补（2026-09-11 晚）：A2 外置启动器独立复核缺陷修复进展

- 本报告 §2.5 所列引擎侧三缺口（data_version 仅批次 id、无尾采、启动失败无记录）**全部仍在**——本轮未改 factor_miner 受审核心，继续由外置启动/验收器补偿（§4.4 路径不变）。
- 外置启动器（`experiments/r0_audited_runner.py`）经独立复核（`docs/experiments/r0-launcher-independent-review-20260911.md` §11，CHANGES_REQUESTED）后已修复三项确定缺陷：正向命令契约（json.loads(list) TypeError）、外部输入运行后身份（expected 等三文件 prepare 绑定+launch/verify 双侧复核）、超时进程树清理（Windows Job Object 整树击杀+方法入账）。**数据根覆盖风险已识别并落最小措施**：数据根改指他处（含字节相同的替换）由 prepare 期 `data_roots_resolved`（realpath 绑定）在 launch/verify 重解析比对拦截；junction 仅名称转发、非只读非不可变，运行窗内"改后还原"残余风险仍待 J3 裁决。明细见 `docs/experiments/r0-launch-pack-20260911.md` §0.2。
- B4 关闭条件不变：上述修复不改变 B1/B2/B3/B5/B7 阻断状态；正式 R0 仍暂停（统计校准独立复核 J0 未闭合），本增补不产生任何解闸或放行结论。

## 9. 增补（2026-09-11 夜）：fix-round3 外部锚与工程纪律修复（主审裁决定向）

- **依据**：`artifacts/system-audit-20260911/r0-review.md`（外部信任锚缺口 Attack A：launch_dir 内全量协同改写曾 verify 全 PASS；sidecar 自写自验结构性不可 FAIL；repo_root 三层 dirname 活代码缺陷）+ 主审裁决与中间审阅两点（Popen 资源失败 job 句柄泄漏、sidecar TOCTOU）。
- **五项修复**（写入集=runner+tests+launch-pack+本文+`artifacts/system-audit-20260911/runner-recovery/`）：①外部可信摘要——prepare 输出 `manifest_canonical_sha256` 供主对话存档，real launch/verify 必填 `--trusted-digest`（64 位小写 hex）且须等于当前 canonical，禁自读 launch_dir/anchor 充信任，verify 新增 `trusted_anchor`（12 项检查）；②PREPARED 三方绑定（哈希字段+内嵌副本+当前 manifest）；③sidecar 职责分离——launch 子进程退出时独占创建（open "x"）写入，verify 只读；④Job 纪律——先建 Job 再 CREATE_SUSPENDED 启动→并入→Resume，WinAPI 11 原型全显式签名，建 job/并入/恢复/Popen 资源失败任一失败拒绝启动并关句柄/杀树+记 cleanup_confirmed；⑤repo_root 两层 dirname+.git 断言。
- **状态**：合成与单测层面完成（含 Attack A 复演被固定摘要拦截、真实进程树清理确认）；**真实 director CLI 兼容性仍未实测（R0-3 范围）**；待主审审阅+独立复核后方可作为 R0 启动器候选。正式 R0、VALIDATION/LOCKBOX、MT、统计正式批全部维持禁跑。

## 10. 增补（2026-09-11 夜）：fix-round4（Halley 独立复核六反例定向修复）

- fix-round3 经 Halley 独立复核（`artifacts/system-audit-20260911/fixround3-independent-review-20260911/`，六探针反例全部复现）；主审批准后按 §0.4（launch-pack）完成 F1/F2/F3/F4/F5/F6 修复与回归：pytest 67 passed（含 p1/p2 原样复演被拒、worktree 可用、有界 post-kill 等待、异常路径 job 句柄恰关一次）。工件 `artifacts/system-audit-20260911/runner-fixround4/`；r3 封存于 runner-recovery。
- **收口边界（主审裁定）**：runner 合成验收=本包单独收口，待一次独立复核+主审终裁；**不据旧全仓哈希宣布整系统绿**。依赖变化：merge_rows 丢 preclose（STATE 缺失/limit_up 静默 0）由 Sartre 独立修复中——真实启动受审身份（含 mr_statarb.py 哈希）在其审定后重锚。正式运行维持禁令。
