# R0 启动器独立审核报告（r0_audited_runner）

- 日期：2026-09-11。审核：GLM-5.3/MAX（独立审核代理，主对话派发）。
- 对象：任务A2 外置启动/验收器。**结论：CHANGES_REQUESTED**（2 项 P1、6 项 P2、若干 P3/文档项；PA1/PA2 已先行交付主对话并已派作者修复，本报告为收束全量证据 + 修复后复核协议；修复版 v1（0a9f7e63）已落地并经 §9 独立重放：原 P1 与 V2/V3/V4 确认修复，但发现新 P1（正向路径 json.loads(list) 崩溃），GC1/V5/RB 仍开口——整体维持 CHANGES_REQUESTED。

## 0. 版本绑定

| 文件 | git blob | SHA256 |
|---|---|---|
| experiments/r0_audited_runner.py | c2ac82457ef0ef8c21b2e9975d85fc70c8d2db72 | A8AF21654C8B0B06A497521557E0936BB0552D03E2F0DFA430FF00062A0F9FEC |
| tests/test_r0_audited_runner.py | 6dd9fdec1300cc22a57b52ccdc75cf7baae8bc38 | 7EB659DBFF21FB182D0F01468542D212AC01801E9559B6804D3F9624085CD50A |
| docs/experiments/r0-launch-pack-20260911.md | 9ab4aeab46c254b09f55b63d610234b7fe3bc9aa | 4248EE3F5D624159508FB4C7771C9DD1CF395248ECC5EB18E5D901BE226E4446 |

- 仓库 HEAD：f32568f；三文件为 staged 未提交（A）新文件；审核绑定工作树内容=暂存内容（git diff 为空）。
- 作者修复（主对话据 PA1/PA2 派发）落地后，本报告全部结论仅对上表旧版负责；复核时须重新绑定 hash 并列出版本变化。
- 旧版已固化独占副本：artifacts/r0-launcher-independent-review-20260911/oldcopy/r0_audited_runner.py（hash 复核=c2ac8245，与本报告一致）。攻击组 2/3/4 全部打该副本，与作者正在进行的编辑零冲突。

## 1. 审查范围与执行声明

- 只读：runner、其测试、launch pack 文档、prep 工件（crosscheck/data_roots_inventory/expected_units/launch_config_template/selftest 留档）。
- 允许项内执行：作者单测全量（Ran 20 tests OK，8.5s）；合成攻击（mock Popen 零进程 ×3 组、真实合成 sleep 进程 ×1 组）。
- **未执行**：真实 TRAIN 重读、VALIDATION/LOCKBOX 任何读取、真实批次、大快照、snapshot-prepare（J4 未裁）、全量 data-manifest（J5 未放行）。未修改作者任何文件；写集仅本目录与 artifacts/r0-launcher-independent-review-20260911/。

## 2. 结论汇总

| # | 级别 | 发现 | 实证 |
|---|---|---|---|
| PA1 | **P1** | 统计暂停闸不在启动路径：real 模式 + pause=true + 双旗标照常启动，暂停仅在 verify 事后拦截 | attack_pri_report.json |
| PA2 | **P1** | command 为任意 JSON，无 TRAIN 入口绑定/形状校验 | attack_pri_report.json |
| A3b+V2 | **P1（同族）** | manifest 事后改写无任何检测：PREPARED ledger 快照存在但 launch/verify 均不读回比对；命令换装、mode real→synthetic 翻转绕过统计闸 | attack4/attack3 报告 |
| GC1 | **P2** | 超时只 proc.kill() 直接子进程，孙子进程存活泄漏；且 reader 线程被孙子继承的管道句柄拖住，join(5)×2 白等 | attack2_report.json |
| V3 | **P2** | 清闸后 n_tests≠评估单元数仍 PASS（仅披露）；作者测试 L248-260 已把 rc==0 固化为预期 | attack3_report.json |
| V4 | **P2** | verify 数据根缺失直接崩溃（RuntimeError），completion_report.json 残留旧 PASS（mtime 未变），违背自身 docstring"验收失败原因逐项落盘" | attack3_report.json |
| V5 | **P2** | expected/hypotheses/data_manifest 文件哈希记入 manifest 但 verify 从不复核；candidates+expected+run_meta 三处一致篡改 → PASS（"双方同时漏"不可检） | attack3_report.json |
| A3a | **P2** | manifest 删 timeout_sec：KeyError 发生在 Popen **之后**，真实后果=无超时无账本的孤儿正式进程；ledger 仅剩 PREPARED | attack4_report.json |
| RB | **P2（裁决项）** | 资源预算零实现：rg 全文无 Job Object/内存限额/亲和性/psutil；决链 D-2026-09-11-01 前置含"资源独占"，工具级未落实 | rg 证据 |
| A5 | P3 | prepare 接受 --real-mode 无 --command；launch 时 TypeError 崩溃、无 ledger 记录 | attack4_report.json |
| STUB | P3 | prepare 中途失败（如 AUDITED_EXTRA_PATHS 缺文件）留空 launch 目录（makedirs L609 先于哈希 L615），卡死 only-new 重试 | 攻击搭建时实测留档 |
| ATOM | P3 | _write_json 直写无 temp+rename，崩溃可留半截 manifest/completion_report | 代码 L585-588 |
| V7 | P3 | holding_days 松散 int 强转：[True]（→1）与 [5.9]（→5）均通过 _schema_check，偏离冻结整型集合语义 | attack3_report.json |
| DOC | P3 | 文档漂移：runner docstring L21"八项检查"与 pack L116"八项验收" vs 实际九项（_VERIFY_CHECKS L786-790）；pack L26/L81"16 项单测" vs 实际 20 项 | 通读对照 |
| ENV | 观察 | real 模式继承全部 os.environ（PYTHONPATH/PYTHONHASHSEED 未清洗）；D-30 教训相关但引擎已全元组排序，不构成缺陷 | 代码 L735 |
| V6 | 观察 | 数据根内 junction 子树**会**被 os.walk 纳入哈希（完整性正向）；环状 junction 无死循环保护（未实测，挂起风险如实披露） | attack3_report.json |

## 3. P1 详情与代码摘录

### PA1 统计暂停闸非启动闸

- cmd_launch real 分支（L728-733）仅查双旗标：`if not (args.real and args.acknowledge_official_run): raise RuntimeError(...)` 随即 `cmd = json.loads(manifest["command"])` 进入 Popen。
- `stat_calibration_pause` 唯一消费点在 cmd_verify（L981）：`if manifest.get("stat_calibration_pause", True): stat_status = "ADJUDICATE"`——运行结束后才 BLOCKED。
- 实证（mock Popen，命令标记 OFFICIAL_RUN_SHOULD_NOT_START）：manifest mode=real、pause=true、双旗标 → launch rc=0，ledger PREPARED→LAUNCHED→EXITED 全链落账。控制组：双旗标守卫本身完好（无旗标 RuntimeError）。
- 修复方向：cmd_launch real 分支前置拒启（pause=true → 拒绝 + REFUSED ledger 事件 + rc≠0）；prepare-launch --real-mode 在 pause 未清时同样拒绝（纵深）。

### PA2 command 任意 + A3b 换装 + V2 relabel（manifest 完整性族）

- prepare 的 --command 为任意 JSON（L1194-1195），launch 原样 Popen（L733-749）。实证：["cmd.exe","/c","echo","ARBITRARY_NOT_TRAIN_ENTRY"] 抵达 Popen，无 TRAIN 入口（director pipeline --allow-real-run 模板）比对。
- A3b：PREPARED ledger 记命令 A（L638-639 含全量 manifest），事后改 manifest 命令为 B → launch 执行 B，无任何比对。ledger 留有 A/B 不一致证据但工具不查。
- V2：运行后将 manifest mode real→synthetic 翻转 → verify rc=0 PASS，统计检查显示 "synthetic: not applicable"——正式运行的工件可被事后降格标签绕过统计闸。
- V5（同根因）：expected/hypotheses/data_manifest 的 sha256 记入 manifest（L617-624）但 verify 从不复核文件哈希（L894 直接 _load_json(expected_path)）；candidates+expected+run_meta 一致篡改（幽灵单元 GHOST|w:999）→ rc=0 PASS。
- 修复方向：launch 与 verify 均将 launch_manifest.json 与 PREPARED 事件逐字段比对（至少 mode/command/stat_calibration_pause/audited_files_sha256）；verify 复核 expected/hypotheses/data_manifest 三文件 sha256 与 manifest 记录值；command 限冻结 TRAIN 模板形状。

## 4. P2 详情与代码摘录

### GC1 超时只杀直接子进程（真实进程实证）

- L765-769：`proc.wait(timeout=...)` 超时 → `proc.kill()`（仅直接子进程，无 Job Object / taskkill /T）。
- 实证：child（sleep 45s，派生 grandchild）超时 3s 被杀已死；grandchild pid 13036 存活且已写运行标记；ledger 记 timeout_killed。孙子继承 stdout/stderr 管道句柄 → 两个 reader 线程各 join(5) 失败，ledger elapsed_sec=13.03s（3s 超时+10s 白等）。
- 影响：正式引擎若开 multiprocessing/子进程，超时后 worker 泄漏继续运行（含继续写 out_dir 的竞态）。修复方向：Windows Job Object（JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE）或 taskkill /T；reader 线程 join 失败时在 EXITED 事件披露"管道仍被占用"。

### V3 清闸后 n_tests 分歧仅披露

- L987-990：`elif found: stat_status = "PASS"`——不校验 n_tests_matches_expected_units。实证：pause=false + registry n_tests=999（expected_units_n=3）→ rc=0 PASS。作者测试 test_real_mode_cleared_records_n_tests_divergence（L248-260）明文断言 rc==0，属已固化设计。
- 鉴于 F-3 前科（n_tests 口径错误），建议改 FAIL 并交主对话裁决语义。

### V4 verify 崩溃残留旧 PASS

- L878-880：verify 内 build_data_manifest 对缺失根直接 raise RuntimeError，无捕获 → 整个 verify 崩溃（traceback，rc=1），completion_report.json 不更新。实证：删除数据根后 verify 崩溃，报告文件仍为旧 PASS、mtime 未变。后续读者看到 PASS。
- 修复方向：verify 全程 try/except，任何检查内异常 → 该检查 FAIL + 报告照写；或至少写 overall=FAIL 的最小报告后再退出。

### A3a manifest 缺 key → Popen 后 KeyError 孤儿

- L759-765：LAUNCHED 落账与 wait 均引用 manifest["timeout_sec"]；键被删时 KeyError 发生在 Popen 之后。实证（mock）：POPN 已发生、ledger 仅 PREPARED。真实后果：正式子进程已启动、无超时、无 EXITED 记录。
- 修复方向：launch 入口先做 manifest 必备键完整性与类型校验（缺键 → REFUSED + ledger），再 Popen。

### RB 资源预算零实现（裁决项）

- rg 全文：无 resource/Job/psutil/win32job/affinity/limit。决链 D-2026-09-11-01 前置原文含"OS 分离启动器+资源独占"。当前工具仅提供进程分离+超时。
- 交主对话：要求工具级 Job Object 内存上限，或明示接受程序性纪律并留档。

## 5. 正向确认（作者实现有效部分）

- 双旗标守卫、verify 九项检查的单侧篡改检测（幽灵候选行被 expected_units_bidirectional 抓获）、code/data identity 首尾双采漂移检测、数据根缺失 fail-closed（manifest 构建期）、BLOCKED_ADJUDICATE rc=2 语义与默认 pause=true 缺省、only-new 规则、junction 子树纳入哈希（V6）、expected-units 独立实现与引擎在真实冻结输入上公式集合双向零差异（crosscheck 工件：250/0/0/246/248、formula_set_equal=true）。
- 作者单测 20/20 OK（含真实输入交叉核对）；selftest 四场景+三负例行为与文档 T5 描述一致。

## 6. 修复后独立复核协议（作者修复落地时执行）

1. 重绑 hash：新 runner/tests/pack 三文件 git blob + SHA256；diff oldcopy（c2ac8245）列全部版本变化，逐项对照本报告修复方向。
2. 重放攻击（对修复版）：PA1（pause=true 拒启+REFUSED 账目）、PA2/A3b（命令绑定或 PREPARED 比对拒换装）、V2（relabel 被 verify 拒绝）、V5（三文件哈希复核拦截合谋篡改）、GC1（树杀或等价）、V4（崩溃→FAIL 报告落盘无残留）、V3（按主对话裁决后的语义）、A3a（缺键 Popen 前拒绝）、A5（real 无 command 拒绝于 prepare）。
3. 作者全量单测 + selftest 在修复版上全绿；冻结协议与披露文本零改动比对。
4. 上述任一不满足 → 维持 CHANGES_REQUESTED。

## 7. 证据文件清单（artifacts/r0-launcher-independent-review-20260911/）

- oldcopy/r0_audited_runner.py（审核版本固化）
- attack_pri_launch_gate.py + attack_pri_report.json（PA1/PA2）
- attack2_grandchild_leak.py + attack2_report.json（GC1，真实合成进程）
- attack3_verify_integrity.py + attack3_report.json + attack3_stdout.log（V1-V7）
- attack4_launch_integrity.py + attack4_report.json（A3a/A3b/A5）
- attack*_work/ 各场景工作目录（含 ledger/manifest/completion_report 原样留存）

## 8. 纪律声明

本审核未触碰 VALIDATION/LOCKBOX、未启动正式批次、未跑全量 data-manifest、未执行 snapshot-prepare；被审三文件零修改；作者修复期间全部攻击打旧版独占副本。统计校准复核（J0）未闭合前，任何修复版验证通过均不构成解闸——REAL_RUN 仍按用户 2026-09-11 指令暂停。

## 9. 修复版 v1 独立复核（作者修复落地 2026-09-11 午后；blob 0a9f7e63 / tests 27bc2d4c）

修复落地于本报告收束期间；已固化独占副本 artifacts/r0-launcher-independent-review-20260911/fixcopy-v1/（hash 复核=0a9f7e63）。全部重放打该副本，与作者后续编辑零冲突。旧版证据（§2-§4）不因此作废。

### 9.1 版本变化摘要（oldcopy c2ac8245 → fixcopy 0a9f7e63，+200/-7）

prepare-launch：路径绝对性+hypotheses 存在性前置校验；**命令由函数可信构造**（director pipeline TRAIN-only + --allow-real-run），任意 --command 仅当与构造结果完全一致才接受；--stat-calibration-cleared 须 --adjudication-ref（主对话裁决引用），审批变化须新建包；PREPARED 事件新增 manifest_canonical_sha256。launch：**任何 Popen 前**依次执行 PREPARED canonical 哈希绑定（任何事后编辑=manifest_binding_mismatch 拒启）→ 暂停闸（缺键默认拒绝）→ 命令契约 → 快照 enforce 等效（git tracked+干净）→ 受审字节+hypotheses/expected/data_manifest 三文件身份复核；新增 _refuse() 统一 REFUSED ledger 事件（rc=4）。verify：新增 manifest_binding 检查（_VERIFY_CHECKS 现 10 项）；开始即作废旧报告写 INCOMPLETE，异常捕获后写 INCOMPLETE+error（rc=1）；清闸后 n_tests≠外部预期单元数改判 FAIL。

### 9.2 重放结果（attack5/attack6 报告 JSON）

| 重放 | 场景 | 结果 | 判定 |
|---|---|---|---|
| R1 | real+pause(true)+双旗标 | REFUSED rc=4，reason=stat_calibration_pause_active，Popen 前留痕 | **PA1 修复确认** |
| R3 | PREPARED 后改命令 | REFUSED rc=4，manifest_binding_mismatch（PREPARED/current 哈希并列披露） | **A3b/PA2 修复确认** |
| R2 | 合法正向：cleared+ref+repo 快照，全闸通过 | **TypeError: the JSON object must be str...not list**——prepare 现存 command 为 list（L661），cmd_launch L796 仍 json.loads(manifest["command"])；崩溃于全部闸门之后、Popen 之前，ledger 仅 PREPARED 无 REFUSED | **新 P1：正向路径断裂** |
| R4a | real 形态完整工件 verify 正向控制 | rc=0 PASS，binding/stat 全绿 | 正向 verify 路径健康 |
| R4b | real→synthetic 翻转 | manifest_binding FAIL rc=1（哈希不匹配明细） | **V2 修复确认**（§9.2 初测 R4 为无操作误构造，已重做） |
| R5 | pause=false + n_tests=999 | stat FAIL rc=1 | **V3 修复确认** |
| R6 | 数据根删除 | rc=1，报告 INCOMPLETE+error 字段，无旧 PASS 残留 | **V4 修复确认** |
| R7 | launch 后 candidates+expected+run_meta 协同篡改 | verify rc=0 PASS | **V5 仍开口（P2）** |
| selftest | fixcopy 全量 | rc=0 | 作者自测路径未回归 |

### 9.3 修复版 v1 剩余问题清单

1. **新 P1（R2）**：真实正式启动在全部闸门通过后于 json.loads(list) 崩溃——修复版**无法启动任何正式运行**，且崩溃无 REFUSED 留痕（违背其自身拒绝纪律）。根因：L661 manifest["command"]=cmd（list）vs L796 json.loads(...)。作者 13 项新测试全部测拒启，无一正向成功用例，故未暴露。修复：L796 改 manifest["command"] 直接使用（或统一 JSON 字符串），并补一条"全闸通过后 Popen 前成功到达"的正向单测（mock Popen 即可）。
2. **GC1（P2）未动**：超时击杀区无改动（rg 无 taskkill/Job Object /T）；孙子泄漏与 reader 线程 5s×2 白等原样保留。
3. **V5（P2）仍开口**：verify 不复核 expected/hypotheses/data_manifest 文件哈希（launch 期 _prelaunch_identity 不覆盖 launch→verify 窗口）；协同篡改照旧 PASS。修复：verify 内对三文件 sha256 与 manifest 记录值复核（引擎侧 run_meta/candidates 完整性另属工件审核）。
4. **RB（P2 裁决项）未动**：资源预算仍零实现。
5. **P3 未动**：stub 目录（快照缺受审文件时 prepare 崩溃仍留空 launch 目录，attack6 已在修复版复现）；docstring L21 仍写"八项检查"（实际 10 项）；_write_json 仍非原子；holding_days 松散强转（V7）未动。
6. 观察：A5 随命令可信构造自然消亡（command 不再可为 None）。

### 9.4 修复版 v1 总判定

**维持 CHANGES_REQUESTED**。原 2 项 P1 与 V2/V3/V4 修复经独立重放确认；但 R2 新 P1 使正式路径完全不可用（方向 fail-closed，无越权风险，但工具目标未达成），GC1/V5 两个 P2 与资源裁决项仍开口。作者下一轮修复范围建议：R2（一行+正向单测）、V5（verify 三文件哈希复核）、GC1（Job Object 或 taskkill /T+join 失败披露）、RB 待主对话裁决、P3 顺带。

## 10. 证据文件清单（增补）

- fixcopy-v1/r0_audited_runner.py（修复版固化，0a9f7e63）
- attack5_replay_fixed.py + attack5_report.json + attack5_stdout.log（R1/R2/R3/R5/R6/R7 与 selftest）
- attack6_r4_redo.py + attack6_report.json（R4a/R4b/stub 复核）

## 11. 当前字节常规正确性复核（本节取代此前对“当前版本”的推测）

范围按用户最后三条指令收窄：仅本地合成文件、unittest mocks、合成 selftest；不访问网络/凭据/真实行情，不要求防御本地管理员同时改代码与证据。被审代码未修改。证据目录为 artifacts/r0-launcher-independent-review-20260911/current-review/。

### 11.1 字节与测试

- runner SHA256：f60906ce2320646475f39519a231966d617fe805e840a477b5053d9aa32ea828。
- tests SHA256：287396c338612b42c10a45047a0f0928b639055c72ff62e16b0a187651a94081。
- 两文件原样固化到 current-review；测试通过模块注入固定 runner，临时目录限定在审查工件目录，禁写 pycache。
- 作者测试独立运行：Ran 32 tests，OK (skipped=1)，31 执行通过、0 failures、0 errors。唯一跳过项为真实 hypotheses/引擎交叉核对；不能写成32项实际执行全PASS。
- 独立 selftest rc=0；ok=PASS、no_meta/fail/hang=FAIL。作者 selftest-v3/launch_ok/completion_report.json 只读观察为10检查PASS；另在固定当前副本独立重跑，未把旧日志视为当前字节证明。
- tests.log、probes.log、results.json、corrected.log、corrected.json 留档。首次 runlaunch 的 Popen mock 也拦截了 Git 检查，results.json 的 positive/三项输入漂移计数不代表 TRAIN Popen；这些四项以 corrected.json 为准。校正先实际确认合成 Git clean(7 files)，然后只替代已确认的 Git检查结果，其余身份检查与命令代码原样执行。

### 11.2 实际结果与独立 PASS 范围

| 场景 | 结果 |
|---|---|
| real + pause=true；缺 pause | rc=4，TRAIN Popen=0：PASS |
| 缺 mode | KeyError，Popen=0：不启动成立；统一失败留痕未完成 |
| 非既定TRAIN命令 | rc=4，Popen=0：PASS |
| 准备后 manifest 改值；ledger哈希意外改值 | rc=4，Popen=0：PASS |
| 准备后 hypotheses/expected/data-manifest 文件追加字节 | 三项均rc=4，TRAIN Popen=0：PASS |
| n_tests=999 vs expected=3 | statistical_calibration_disclosure=FAIL，rc=1：PASS |
| verify JSON异常，之前有PASS | rc=1，报告INCOMPLETE+error，旧PASS失效：PASS |
| 普通数据字节改动 | 尾部verify rc=1：PASS |
| 合成hang直接子进程 | selftest真实超时退出被记录；mock另外确认kill=1、wait=2 |
| launch之后expected文件意外增加空白（未改ledger/output） | verify仍rc=0，说明未复核已登记的expected字节hash |
| 合法正向命令，全闸通过 | TypeError: the JSON object must be str, bytes or bytearray, not list；TRAIN Popen=0：FAIL |

### 11.3 关键源码及剩余阻断

1. **正向路径阻断，当前仍未修**。L661为 command: cmd（list）；L796仍为 cmd = json.loads(manifest["command"])。合成正向反例已独立重现，作者32测试通过不覆盖此路径。没有执行真实TRAIN，Popen为mock且调用数0。
2. **子孙清理尚无实现**。L831仅 proc.kill()，L832 proc.wait()；没有进程树/作业对象清理。当前直接子进程合成路径已验证；当前版本真实孙子进程清理未重跑，记UNKNOWN，不能把旧版子孙泄漏实证冒充本版重跑。旧版GC1证据保留，当前代码同一机制的静态缺口仍在。L846无条件return 0导致超时launch命令rc=0；必须再verify才得到FAIL，不能以launch rc=0认定运行成功。
3. **外部输入运行后身份缺口**。_prelaunch_identity(L915起)检查代码和hypotheses/expected/data-manifest文件字节；verify未复核这些文件的已登记hash。当前用单文件普通误改（追加空白，不改ledger、不改其他输出）即证明缺口；不再将同时恶意改多份证据作为新增安全阻断。
4. **数据策略是开放条件，而非要求大快照**。合成持久数据漂移在尾部检测失败；原始数据变化后直接调用_prelaunch_identity仍返回identical，因为这里只核对清单文件，不重读清单所列字节。未验证真实读取根全集、运行中改后还原、实际独占控制，均UNKNOWN。用户允许“有证据的独占+前后hash/漂移失败”，本轮尚无该现实证据；junction仅路径转发，不可称其只读或不可变。不据此要求额外密码学防篡改架构。
5. **批准引用的边界**。L629只检查非空字符串；合成 TYPO-NONEXISTENT-SYNTHETIC-REF 能令prepare接受cleared。它是人工裁决引用字段，不是裁决真实性验证器。真实校准暂停仍由主对话保持；若流程期望工具拒绝错引用，当前无法提供该保证。未创建/更改任何真实批准记录。
6. **PREPARED正常误改模型**。哈希误改和manifest误改均拒绝；代码只取最后一个PREPARED的manifest_canonical_sha256，没有重新验证该事件内manifest副本。ledger与manifest同时一致改写不在本轮防御目标内，不新增阻断。
7. **快照/入口/外部units边界**。启动前确有git tracked+clean与代码字节检查，cwd指向snapshot_root；但wrapper自身不在audited_code_paths集合，清单由glob动态形成。合成7文件的Git快照能通过该“干净”检查，不能推导为受审46文件全集或指定受审commit匹配。实际director CLI参数兼容性、真实导入依赖全集、冻结规范全文一致性、外部units与真实输入交叉核对均未读取/未测，UNKNOWN。外部公式/schema测试通过只证明已测合成规则；不能宣称能抓两实现共同规范错误或双方同时遗漏。

### 11.4 本轮结论

**CHANGES_REQUESTED；上述拒启、输入漂移、n_tests、旧PASS失效与合成selftest给出限定独立PASS。** 正向list/json转换错误为确定阻断；子孙清理与运行后输入身份仍未闭合。实际数据独占/根全集/真实入口不在本轮实测范围，不给予PASS。无任何正式运行、真实解闸或数据访问授权由本报告产生。此前“F-3前科”的措辞不准确：F-3已撤回；本轮n_tests检验是常规一致性约束，不重开已撤回统计指控。

