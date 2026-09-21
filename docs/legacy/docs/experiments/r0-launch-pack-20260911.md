# R0 启动与验收包（任务A2 · 轻量实现与 dry-run 验证）

- 日期：2026-09-11。执行：GLM-5.3/MAX（严格代理）；主对话派发并裁决。
- **本包不构成正式可启动结论**。正式 R0 TRAIN 仍需：wave3 round-3 外部裁决、J1–J5 裁决、主对话运行前裁决。本包所有运行为合成 dry-run 或假设元数据计算，未触行情数据、未读取 VALIDATION/LOCKBOX 数值、未启动正式批次。

## 0. 增补（2026-09-11 15:00）：正式 R0 暂停统计校准独立复核 + 暂停闸落地

- **用户指令（2026-09-11）**：正式 R0 暂停，等待统计校准独立复核；**禁止改冻结协议或忽略该风险**。
- **风险原文（按 §8 勘误更新，2026-09-11 主对话审核后；见 `artifacts/r0-stat-oracle-20260911/AUDIT_ADDENDUM.md`）**：
  - 勘误A：MC-A/A35 的 ρ=0.3"依赖保留"**未实现**——共享因子 z 在 unit 循环内新抽，单元间实际独立；逐单元边际率不受影响，两次 MC 的 FWER 实测于**独立场景**。
  - 勘误C：FWER 比较基准=**Bonferroni 保证界 0.10（任意依赖）**，9.6% 仅为独立近似、作废；**A35 FWER 14.3% CP95[10.57%,18.82%] 下界已超 0.10 界**（A24 17.3% [13.22%,22.10%] 同超；MC-B 8.3% [2.76%,18.39%] 无分辨）。
  - 勘误B：方向门禁 H0 名义通过率为单侧 α/(2N)（N=12→0.417%），非 §1.2 所写 0.83%；A35 实测 1.33% 为正确名义的 **~3.2×**（下界倍数，"1.6×"作废）。
  - F-3 **已撤回**：修订案 §2 已冻结 **N=评估单元数（结构×窗口变体=units 列表长度，当前 248）**，与实现逐字一致；仅余修订案生效状态核实（文件头自标草案 vs AGENTS 记 D-33 round6 PASS）交主对话。F-1（None 月压缩轴）仍待 S5/主对话裁决。
  - 立场更正：撤回"协议属性只报告"可能隐含的可放行读法——"S3 校准异常……在主对话裁定前应视为未闭合，R0 冻结门禁产生的晋级结论应受限标注或阻断，由主对话裁决；执行方无权降格"。
- **工具落地（不改协议，只披露与拦截）**：`verify` 新增第 9 项检查 `statistical_calibration_disclosure`——现实模式从 registry 工件提取 n_tests/alpha_total/ci_percentiles 与外部预期单元数比对并全文引用上述风险；manifest 默认 `stat_calibration_pause=true`，暂停未解除时整体判定 **`BLOCKED_ADJUDICATE`（rc=2，非 PASS）**；主对话复核闭合后以 `prepare-launch --stat-calibration-cleared` 显式解除。合成模式不适用（PASS）。**冻结协议零改动**。
- **decisions.md:95 精确原文（MT 前置，J1 裁决输入）**："- **R0 重启新增前置(用户 2026-09-11 批准):MT 变异测试幸存者清零**——清零定义:全部幸存 mutant 完成分诊;真盲区类(未来函数/费用/掩码时序/对齐/缓存键/排序方向/np 双路径分歧)补测试杀灭;语义等价变异留档豁免(非字面零幸存)。与既有前置(Codex PASS/AUDIT-1 类缺陷修复/引擎身份冻结/OS 分离启动器+资源独占)并列。"——**按最新计划及用户批准实际范围判断**：同日晚些的 20260911 修订计划（附录A L61"276 项变异测试：不是本次 R0 启动必要门禁"）与本轮用户指令范围（轻量启动器+单测+合成演练，主对话审后才能正式）均未含 MT 执行；故 MT 不在本实现路径内，保留为 J1 待主对话确认，不据此阻断轻量工作。
- **junction 再确认**：junction 仅名称转发，**不是不可变数据快照，不虚构数据保护**；不可变性仍待 J3 裁决（纪律+首尾哈希为默认且残余风险如实披露）。
- **B01 已完成**（只读核证）：两 PID 已退出（进程计数 0），报告 `docs/experiments/system-audit-b01-train-scan-20260911.md` 14:57 落定（19,141B，尾部 `<!-- SCAN:END -->` 收尾）——**J5 串行 I/O 窗口打开**，但 ~5.9GB 全量哈希仍待主对话放行后串行执行。
- **交接文档扫描（`docs/handover-codex-20260911.md`，只读防重复）**：其中 R0 重启前置"OS 级分离启动器"即本启动器（外置/进程分离/stderr 落盘），无重复实现；`experiments/mutation_driver_20260911.py` 属 MT 域无重叠；§3 队列将"MT 幸存者清零"列于 R0 重启前（J1 冲突仍在，待裁）。九检查版 selftest 已刷新留档至 `artifacts/r0-launch-prep-20260911/selftest-v2/`（含 `statistical_calibration_disclosure`，合成模式 PASS）。

## 0.1 P1 修复（2026-09-11 15:45，依 Carver 独立审查）

- **攻击实证**（`artifacts/r0-launcher-independent-review-20260911/attack_pri_report.json`）：PA1=real+pause=True 下 launch 仍达 Popen（LAUNCHED/EXITED，rc=0）；PA2=任意命令（`cmd.exe /c echo`）直达 Popen；双旗标守卫本身完好。attack2（子孙进程泄漏）按用户指示后续补，本轮不实现。
- **六项修复**（仅 `experiments/r0_audited_runner.py`+`tests/test_r0_audited_runner.py`，factor_miner 与阈值零改动，统计闸保持关闭）：
  1. real launch 在任何 Popen 前检查 `stat_calibration_pause`，**键缺失默认拒绝**；拒绝留 `REFUSED` ledger 事件（rc=4，无子进程、无 stdout/stderr 日志）。
  2. 正式命令**只由可信配置构造**（`python -u -m experiments.factor_miner.director pipeline --hypotheses <绝对路径> --out <绝对路径> --allow-real-run`）；prepare 拒收任意 `--command`、拒相对路径；validation/lockbox 不在构造范围。
  3. PREPARED 事件绑定 manifest canonical 哈希；launch 与 verify 双侧比对（含 mode/command/pause/代码身份/外部预期/数据 manifest）——**mode 翻 synthetic、pause 翻 false、command 替换均 REFUSED/FAIL**；审批状态变化须**新包**并带 `--adjudication-ref`（主对话裁决引用），旧 manifest 只读留史。
  4. n_tests 必须与外部动态 expected units（当前 248）严格一致：清除暂停后分叉即 FAIL（原"999 通过"改为独立负例拒绝）。
  5. verify 每次先作废 completion_report（`INCOMPLETE` 起手），异常中断落 `INCOMPLETE+error`（rc=1），不再残留可误读旧 PASS。
  6. real launch 前置全链检查：PREPARED 绑定→暂停闸→命令契约→**快照 enforce 等效**（git tracked+干净，非 git 即拒）→**依赖身份**（受审字节+hypotheses/expected/数据 manifest 哈希），全部先于 Popen；资源/子孙退出按独立审查后续补。
- **回归测试**：`TestAttackP1` 11 项逐攻击回归（暂停拒绝/缺键默认拒/mode 翻转拒/任意命令拒/非 git 快照拒/身份漂移拒/prepare 三拒/命令形状/verify 绑定 FAIL/异常 INCOMPLETE）+ 原套件更新。**计数更正（§11.1）**：当时写"共 32/32 OK"有误——独立复核实测 Ran 32 tests、OK (skipped=1)，即 **31 项执行通过 + 1 项跳过**（真实输入交叉核对在审核环境跳过），并非 32 项全部执行通过（日志 `artifacts/r0-launch-prep-20260911/test_log_p1_20260911.txt`）；合成 smoke selftest-v3 PASS。运行范围=tests+合成 smoke，未触真实数据、未启动正式。

## 0.2 §11 独立复核缺陷修复（2026-09-11 晚，CHANGES_REQUESTED 收敛轮）

- **依据**：`docs/experiments/r0-launcher-independent-review-20260911.md` §11 与 `artifacts/r0-launcher-independent-review-20260911/current-review/corrected.json`。三项确定缺陷全部修复；不触 factor_miner 受审核心与统计协议、不读真实 VALIDATION/LOCKBOX、不启动正式批次。
- **1. 正向命令契约（§11.3-1，P1）**：prepare 落盘 `command` 为 JSON 数组（list），launch 原对 list 做 `json.loads` → 全闸通过后 TypeError、正式路径完全不可用（Popen=0）。修复=命令契约检查后直接 `list(manifest["command"])`；新增正向合成 mock 测试（真实 git 快照+真实三文件哈希+PREPARED 绑定，mock Popen 仅拦截 director 命令、git 检查走真实子进程）：Popen 恰 1 次、命令=`expected_train_command` 原样 list 含 `--allow-real-run`、ledger LAUNCHED→EXITED(0) 无 REFUSED。
- **2. 外部输入运行后身份（§11.3-3）**：修复前 launch 后仅给 expected 追加空白（不动 ledger/output）verify 仍 rc=0。新增 `_external_inputs_status`：hypotheses/expected/data_manifest 三文件 sha256 与 prepare 绑定值在 **launch（Popen 前，漂移即 REFUSED rc=4）与 verify（新检查项 `external_inputs_identity`，FAIL 即 rc=1）双侧复核**，明细逐文件并列 bound/current 哈希；selftest 增"运行后 expected 追加空白→FAIL、还原→回 PASS"负例。
- **3. 数据根覆盖识别与最小前后身份核查（§11.3-4）**：识别风险=数据根（junction/直连路径）可在清单构建后**改指他处**（根覆盖）。最小措施（已实现）：prepare 对每根绑定 `os.path.realpath`（manifest 新增 `data_roots_resolved`），launch/verify 重解析比对——junction 改指**字节完全相同**的另一份拷贝也判漂移（合成实证 `root_SYN_redirected`）；根下内容字节由 verify `data_identity_tail` 全量重算 digest 兜底（prepare 前/verify 后两时点比对）。**junction 仅名称转发、非只读非不可变，不虚构数据保护**；开放条件如实披露：launch 期不重读约 11,792 个数据文件字节（大 I/O，属 J5 放行事项），运行窗内"改后还原"不可检（残余风险，J3 裁决三选项不变）。
- **4. 超时进程树清理（§11.3-2，GC1）**：原 `proc.kill()` 仅杀直接子进程——旧实证孙子存活泄漏且 reader 线程被继承管道句柄拖住（elapsed 13.03s 含 10s 白等）。修复=Popen 后立即并入 Windows Job Object（`JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`，后代自动继承入 job），超时 `TerminateJobObject` 内核级整树击杀→回退 `taskkill /F /T`→最后仅直接杀；实际方法入 EXITED 账目（`timeout_kill_method`），reader 线程 join(5) 后仍存活则 `pipes_still_held` 披露。新增真实合成父子进程测试（非 mock）：孙进程（写存活标记、继承 runner 管道）随树终止，**测试自建的无关进程存活**（只终止本启动器自建树），方法∈{job_terminate_tree, taskkill_tree} 且≠direct_kill_only。本机实测 `job_terminate_tree` 生效，hang 场景 elapsed 1.011s（对照旧实证 13.03s）。
- **5. verify 检查项数同步**：`_VERIFY_CHECKS` 现 **11 项**（新增 `external_inputs_identity`；历史"八项/九项"计数系漂移，本文 T4/§8 已同步更正）。
- **实测与留档**：本工作区 `python -m unittest tests.test_r0_audited_runner` → **Ran 36 tests, OK（0 failures, 0 errors, 0 skipped）**（真实冻结输入存在，交叉核对实际执行）；selftest 合成 smoke PASS（四场景+四负例：受审字节漂移/数据漂移/幽灵候选/**运行后 expected 漂移**）。日志与修复记录留档 `artifacts/r0-launch-prep-20260911/fix-round2-20260911/`。

## 0.3 外部锚与工程纪律修复（2026-09-11 夜，fix-round3；主审裁决定向）

- **依据**：`artifacts/system-audit-20260911/r0-review.md`（Attack A 外部信任锚缺口、repo_root 活代码缺陷）+ 主审裁决（外部可信摘要方案、Job 先建后启动、sidecar 职责分离）+ 主审中间审阅两点（Popen 资源失败句柄泄漏、sidecar TOCTOU）。写入集=runner+tests+本文+readiness+`artifacts/system-audit-20260911/runner-recovery/`；不触 factor_miner、不读 VALIDATION/LOCKBOX、不跑正式。
- **1. 外部可信摘要（Attack A 根治）**：`prepare-launch` 输出 **`manifest_canonical_sha256`** 供主对话抄录存档（可选 `--anchor-out` 落 launch_dir 之外的交叉记录）；real `launch`/`verify` **必填 `--trusted-digest`**（64 位小写 hex，格式不符即拒），与当前 manifest canonical 哈希一致方可启动/通过；synthetic 免填、一旦提供即校验。**任何代码路径禁止自读 launch_dir/anchor 文件充信任**——唯一信任根是主对话在 prepare 后抄录存档的 CLI 摘要；威胁边界（不防本地管理员改 runner 字节/解释器/主对话存档）在源码注释显式声明。verify 新增第 3 项检查 `trusted_anchor`（现 **12 项**）。Attack A 复演测试：launch_dir 内全量协同改写（manifest+PREPARED 字段+内嵌副本+sidecar 全自洽）在合成无锚模式仍 PASS（**边界如实披露**）、调用方固定摘要即 rc=1。
- **2. PREPARED 三方绑定**：launch 与 verify 双侧核对"PREPARED 哈希字段、事件内嵌 manifest 副本、当前 manifest"三方一致——"字段已改、副本留旧"的 Attack A 变体（旧两方比对曾通过）现 FAIL/REFUSED。
- **3. sidecar 职责分离 + 原子写**：`external_data_identity_sidecar.json` 改由 **launch 在子进程退出时写入**（绑定 pid/run_meta 字节/manifest canonical/数据 digest），verify **只读校验、绝不写入**（mtime 不变测试钉死）；生产路径用 **open "x" 独占创建**（主审评审：两步检查-写入有 TOCTOU；已存在即原样保留+`SIDECAR_PREEXISTING` 留痕）；`written_by` 须为 `launch_at_child_exit`，篡改/缺失/伪造来源均 FAIL。
- **4. Job 纪律**：**先建 Job 再 Popen**（CREATE_SUSPENDED 启动→并入 job→线程枚举 Resume，杜绝后代先行竞态）；11 个 kernel32 原型**全部显式 argtypes/restype**；建 job/并入/恢复/**Popen 资源失败**（主审专项：job 句柄 try/except 关闭，专项测试断言 `_close_job` 恰调一次）任一失败均拒绝启动（REFUSED rc=4）并尽力杀树+记 `cleanup_confirmed`；超时清理返回 (method, cleanup_confirmed)，确认失败标 `cleanup_unconfirmed`、中止分类 `aborted_*` 绝不 clean_exit；正常退出也查询 job 残余后代→Terminate→确认归零。
- **5. repo_root 修复**：两层 dirname + `.git` 断言（原三层 dirname 解析到 `D:\AI\workspace`，snapshot-prepare 缺省 --repo 时 git rc=128 未捕获栈崩溃）；负例测试（仓库外副本 fail-closed）。
- **回归**：pytest 全量通过（含真实进程专项：suspended 启动全链、assign/resume/Popen 失败杀树、超时整树击杀+无关进程幸存+cleanup_confirmed；Attack A 复演/锚交叉记录负例/摘要格式负例/三方绑定负例/sidecar 四负例/repo_root 正负例）。日志、diff、fix_record 留档 `artifacts/system-audit-20260911/runner-recovery/`。

## 0.4 Halley 复核缺陷修复（2026-09-11 夜，fix-round4；主审批准定向）

- **依据**：`artifacts/system-audit-20260911/fixround3-independent-review-20260911/`（独立 REVIEW+六探针，反例全部复现成立）+ 主审批准（F1/F2 定向修、F3/F5/F6 按 B 级有界补偿、F4 顺手修不扩攻击面）。r3 受审字节封存（`runner-recovery/r3-freeze-notice.md`），本轮基线经哈希核验后打 diff。
- **F1**：verify exit_record 成功判定必须与分类/清理状态一致（clean_exit、cleanup_confirmed≠False、无 cleanup_unconfirmed/timeout_kill_method/post_kill_wait_timeout）——Halley p1 的"超时伪装正常完成 12 项全 PASS"复演被拒。
- **F2**：候选科学字段与冻结预期逐行语义核对（is_base/派生 disposition/family/expected_direction/formula_hash/factor_type）+ launch 逐工件 sha256（candidates/registry/rejected/universe）入 sidecar、verify 逐项比对、stdout 公布 sidecar_sha256 供主对话外部保全（同权限极限：本地同权限者可连 sidecar 改写，信任根=主对话外部存档摘要）——p2 的 is_base 翻转与非语义字段篡改均被拒。
- **F3**：账本须恰含 SIDECAR_WRITTEN 且无 SIDECAR_PREEXISTING（事件改名绕过被拒）。**F4**：repo_root 支持 git worktree（.git 文件+gitdir 存在性只读验证；无效仍 fail-closed）。**F5**：杀树后等待有界 10s，超限 cleanup_confirmed=False+披露（且被 F1 拒绝）。**F6**：spawn 后全路径 try/finally，job 句柄异常路径不泄漏、原异常保留。
- **实测**：pytest **67 passed**（57 项 r3 回归+10 项新）+ selftest PASS；工件 `artifacts/system-audit-20260911/runner-fixround4/`（diff×2、双日志、fix_record_round4.json、r3 双基线重建+哈希核验）。
- **依赖变化声明（主审 2026-09-11 夜）**：merge_rows 丢 preclose 致 STATE 缺失/limit_up 静默 0，Sartre 独立修复中——**runner 合成验收仅本包收口，不据此宣布整系统绿；真实启动受审身份（含 mr_statarb.py）须待 preclose 修复审定后重锚**。

## 1. 交付物（本轮仅四处写入）

| 文件 | 内容 |
|---|---|
| `experiments/r0_audited_runner.py` | 外置启动/验收器（stdlib-only，**不 import factor_miner**）：expected-units / data-manifest / snapshot-prepare / prepare-launch / launch / verify / selftest |
| `tests/test_r0_audited_runner.py` | 36 项单测（tokenizer/外部预期/manifest/端到端正负路径/双旗标守卫/攻击回归/正向 launch 回归/外部输入身份/进程树击杀/真实输入交叉核对；计数沿革见 §0.1/§0.2） |
| `docs/experiments/r0-launch-pack-20260911.md` | 本文档 |
| `artifacts/r0-launch-prep-20260911/` | 外部预期、交叉核对、数据根清单、配置模板、自测留档 |

factor_miner 受审核心零修改（git status 可核：受审 46 文件仍全部 tracked+干净）。

## 2. T1–T5 入口与实测结果

### T1 expected-units（独立外部预期，无 hardcode）

`python experiments/r0_audited_runner.py expected-units --hypotheses artifacts/factor-miner/r0-20260910/hypotheses/_all_raw.jsonl --out <path>`

独立实现：schema 15 冻结字段、R4 非空、公式 tokenizer（算子白名单/窗口末位整型/CORR 三参/N1-N2 占位规范化+sha256/R2 字段集比对/R6 industry 标记）、哈希去重+谱系、评估单元枚举。**真实冻结输入实测**（`expected_units_all_raw.json`）：

- 源行 250、解析错误 0、拒绝 0、事件型 0；
- **合并组 246；评估单元 248**（历史口径"246 结构"=合并组数；评估单元=248，两者与 250 行不可互证——计划 R0-2 预警的正是此事）；
- EXPLORATORY_ONLY（industry 相关）单元 16；
- 全部计数由规则派生，无任何预填。

**交叉核对**（`crosscheck_engine_vs_external.json`）：引擎自身 collect/validate/dedup/evaluation_units 与外部实现 **公式集合双向零差异**（engine_minus_external=0、external_minus_engine=0，计数逐项一致 250/0/0/246/248）。此为一次性一致性证据；正式验收仍用外部预期独立核对 candidates，不以本次一致替代。

### T2 data-manifest（数据内容身份）

`python experiments/r0_audited_runner.py data-manifest --root NAME=PATH [--root ...] --out <path>`

逐文件 size+sha256（分块读字节，**不解析内容，不产生留出数值观察**），排序路径、canonical digest，根缺失/不可读 fail-closed。R0 实际读取根与体积（`data_roots_inventory.json`，2026-09-11 实测）：

| 根 | 路径 | 文件 | MB |
|---|---|---|---|
| PRICE（PV1 r5 同四根） | qfq 两 zip + baostock daily + adjust_factor | ~11,792（PV1 r5 口径） | ~3,600 |
| VALUATION | tushare/daily_basic/20260909-r1 | 1,867 | 1,215.3 |
| BENCH | tushare/sw_index_daily/20260909-r3 | 33 | 10.8 |
| FLOW_MARGIN | tushare/margin_detail/20260909-r1 | 1,867 | 485.8 |
| FLOW_LHB | tushare/top_list/20260909-r1 + top_inst/20260909-r3 | 3,734 | 312.9 |

合计约 5.9GB。EVENT 表 R0 连续因子不读取，不入清单。**全量哈希待 B01 结束或串行低速窗口执行（J5），本轮未跑**（避免与 B01 抢 I/O）。

### T3 snapshot-prepare（detached 快照，已授权未执行）

`python experiments/r0_audited_runner.py snapshot-prepare --repo <root> --commit <sha> --dest <绝对路径> --out <manifest路径> [--no-link-data]`

`git worktree add --detach` + 快照内受审 46 文件 ls-files/status 派生 enforce 等效校验 + 主树脏态摘要哈希入档 + 可选 data junction。dest 只新建（已存在即拒）。**本轮未执行**（等 J4 路径裁决与 J5 时机）。

### T4 prepare-launch / launch / verify

- `prepare-launch`：manifest+ledger **先落**（受审文件 sha256、hypotheses/expected/数据 manifest 哈希、命令、超时、引擎 env、out_dir 独占检查）。
- `launch`：默认合成 dry-run；`--real --acknowledge-official-run` 双旗标才走正式入口（本工具不替代主对话裁决）；子进程 `python -u`、stdout/stderr 线程即时落盘（带时间戳）；超时击杀/异常终止分类（timeout_killed / windows_fatal / nonzero_exit 等）入 ledger。
- `verify` 十二项检查：manifest_present、manifest_binding（§0.3 升级：PREPARED 三方绑定+命令契约）、**trusted_anchor（§0.3 增补：调用方固定摘要必填且须等于当前 canonical；锚文件仅交叉记录）**、exit_record、**run_meta_present（缺失即 FAIL——未完不 PASS）**、code_identity_tail（首尾双采）、data_identity_tail（manifest 重算比对）、**external_inputs_identity（§0.2 增补：三文件字节+数据根 real-path 与 prepare 绑定值复核）**、expected_units_bidirectional（外部预期 vs candidates 双向集合核对）、candidates_field_completeness（13 必备字段+disposition 枚举+n_candidates 一致）、sidecar_binding（§0.3 升级：launch 退出时写入、verify 只读+独占创建原子性）、**statistical_calibration_disclosure（§0 增补；暂停未解除 → BLOCKED_ADJUDICATE）**。

### T5 selftest（合成端到端）

`python experiments/r0_audited_runner.py selftest --workdir <dir>`。已跑（`artifacts/r0-launch-prep-20260911/selftest/`）：四场景 ok/no_meta/fail/hang + 三负例（受审字节漂移→code_identity FAIL；数据漂移→data_identity FAIL；幽灵候选行→双向核对 FAIL），全部按预期判定，恢复后 verify 回 PASS。

## 3. 测试

`python -m unittest tests.test_r0_audited_runner` → **Ran 36 tests, OK（0 skip）**（§0.2 修复轮实测，~20s；真实冻结输入在本工作区存在故交叉核对实际执行，其他工作区无该文件时该项自动跳过）。历史"16/16""32/32"计数均为漂移表述，分别按实际 20/31+1skip 更正（§11.1/§0.1/§0.2）。离线零第三方依赖。

## 4. 关键纠正落实：junction ≠ 只读/不可变

接受用户纠正：junction 仅是名称转发，**不能宣称解决运行中改后还原**；首尾哈希只是附加证据（残余风险：运行窗内临时改再还原不可检）。快照内 data 经 junction 引用主仓数据（不复制 5.9GB）。不可变性策略三选项待 **J3 裁决**：(a) 批次"只新增不覆盖"纪律+首尾全量哈希（默认，残余风险如实披露）；(b) 运行窗内数据根 ACL deny-write（可逆系统级变更，需授权且确认无写者）；(c) 字节归档拷贝（最硬、大 I/O）。

## 5. B01 只读核查（2026-09-11 ~11:00 起，15:00 复核）

- PID 5984（venv 包装，父 25124）→ PID 24148（真身，ParentProcessId=5984，同一命令行）——**父子同任务**，system_audit_b01_train_scan `--scan --report docs/experiments/system-audit-b01-train-scan-20260911.md`。
- 真身 CPU 累计 9,834s（≈2.7 核时，11:00 读数）→ 10,616s（12:00 前后）后退出；15:00 复核**进程计数 0**，报告 19,141B、14:57 落定并以 `<!-- SCAN:END -->` 收尾——**B01 扫描已完成**。全程未干预。

## 6. 前置引用（精确原文）

- **MT**（`docs/decisions.md` D-2026-09-11-01 末条）："**R0 重启新增前置(用户 2026-09-11 批准):MT 变异测试幸存者清零**——清零定义:全部幸存 mutant 完成分诊;真盲区类(未来函数/费用/掩码时序/对齐/缓存键/排序方向/np 双路径分歧)补测试杀灭;语义等价变异留档豁免(非字面零幸存)。与既有前置(Codex PASS/AUDIT-1 类缺陷修复/引擎身份冻结/OS 分离启动器+资源独占)并列。"
- **MT 反证**（`docs/experiments/r0-system-plan-review-20260911.md` 附录A L61，原计划后置工作）："276 项变异测试：**不是本次 R0 启动必要门禁**；如执行，须隔离独占副本、未变异基线通过，不在多人写入的工作树修改再还原。"（修订计划 §4 亦未列 MT 前置。）
- **numpy**（`docs/decisions.md` D-2026-09-10-34 流程纪律）："实现（flash）→ 主对话对抗复验 + 差分 → 送审包 → **Codex PASS 前任何正式运行不得使用 numpy 路径**（REAL_RUN_UNLOCKED 的授权边界随之约束引擎身份）；PASS 后用 numpy 引擎重跑 R0 TRAIN 作新基线，此后 TRAIN/VALIDATION/LOCKBOX 同引擎身份。"
- **A 阶段**（`docs/experiments/system-audit-scope-20260910.md` 阶段边界）："A 阶段尚未闭合，故不能签发 numpy 运行前 PASS，也不能据旧 `REAL_RUN_UNLOCKED=True` 恢复 R0。"（`docs/plans/system-risk-based-audit-plan-20260910.md` §5 表首行同义："单项 PASS、旧 REAL_RUN_UNLOCKED=True 或历史启动授权不构成此次恢复授权"。）

## 7. 裁决项（J1–J5）

| # | 事项 | 选项/建议 |
|---|---|---|
| J0 | **统计校准独立复核（正式 R0 暂停中）** | Herschel/S3 三项（FWER 偏离披露口径、F-1 观测月轴、F-3 n_tests 口径）闭合裁决；闭合前 verify 恒 BLOCKED_ADJUDICATE |
| J1 | MT 前提冲突（D-2026-09-11-01 vs 20260911 计划） | 主对话裁定 MT-run/幸存者清零是否仍为 R0 硬前置 |
| J2 | 引擎选择与 A 阶段闭合判据 | wave3 round-3 外部裁决是否同时闭合 A 阶段；正式批 pure 还是 numpy |
| J3 | 数据不可变机制 | (a) 纪律+首尾哈希（默认）/(b) ACL deny-write（需授权）/(c) 5.9GB 归档拷贝 |
| J4 | 快照路径 | 建议 `.r0-snapshots/r0-<commit8>-<ts>`（workspace 内、只新建、不污染 artifacts 搜索） |
| J5 | 串行 I/O 时机 | B01 结束或低速窗口后跑全量 data-manifest + snapshot-prepare |

## 8. 后续步骤（待裁决后执行）

1. **J0 统计校准复核闭合**（解除 `stat_calibration_pause` 前置）；J5 窗口已开（B01 完成）：全量数据 manifest（~5.9GB 串行哈希，待主对话放行）→ `data_manifest.json`；
2. J4 路径裁决后：snapshot-prepare（detached 快照 + junction + enforce 等效校验）；
3. 快照内 dev-smoke-train 只读 TRAIN 装载演练（junction 端到端可行性，未演练项）；
4. prepare-launch（真实命令模板填充）→ 主对话运行前裁决 → 方可 `launch --real --acknowledge-official-run`；
5. 运行后 `verify` 十二项验收（real 须 `--trusted-digest`）+ 工件回归审核。

## 9. 纪律声明

本轮写入仅四处（runner/测试/本文/artifacts 目录）；factor_miner 与全部受审文件零修改；B01 进程未干预；未读取 VALIDATION/LOCKBOX 数值；数据全程序只读；正式批次未启动，**本包不宣称正式可启动**。
