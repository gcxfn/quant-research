# factor-miner 引擎 Codex 运行前审核送审包 第 6 轮（2026-09-10）

审核性质：运行前代码审核第 6 轮。第 5 轮 2 项 P1（均在研究身份链）已修复，主对话复验通过；其余 round5 修复项第 5 轮已接受未动。全仓 971 项 unittest OK/1 skip（主对话自跑权威数）；REAL_RUN_UNLOCKED 保持 False。前包：round5。

## 一、第 5 轮处置（主对话复验）

| 项 | 处置 | 复验 |
|---|---|---|
| ①[P1] 身份清单遗漏真实运行依赖 | `AUDITED_EXTRA_PATHS`（director.py:68-74）显式并入五个运行依赖：`experiments/mr_statarb.py`、`quant/history.py`、`quant/market.py`、`experiments/factor_miner/prompts/researcher_v1.md`、**`configs/short-foundation-research.json`**（代理排查新发现：`mr_statarb._resolve_paths()` 经 `init_runtime()` 在正式路径读取，mr_statarb.py:1941-1944——主对话已独立核实该调用存在）。`audited_code_paths()`（:77-88）= 原 glob 并集 + 五依赖，受审文件 24→30。排查结论：`data_fields.data_version()` 纯硬编码常量不读文件；其余路径常量均在 mr_statarb.py 源码内（该文件入清单即覆盖）；无其它独立配置文件被正式路径读取 | 主对话实测：清单含 5/5 新依赖；`enforce_code_identity()` 在当前仓库状态（factor_miner 包未跟踪、mr_statarb.py 未跟踪、quant/ 多处工作区修改）**实测 fail-closed 拒绝并列出违规**——解锁提交必须包含全部受审源码且工作区洁净的纪律现在真实生效 |
| ②[P1] 身份校验只覆盖 TRAIN | 新增 `code_identity_files_match()`（:142-159）：键集合完全一致（多键/少键都违规）+ 逐 sha256 相等；`git_head` 只作溯源不参与比对（阶段间允许文件内容不变时发生提交）。**VALIDATION**（:1087-1109）：真实通道判定=（bundle_builder is None ∧ universe is None ∧ build_real_bundle 未被注入替换）→ `enforce_code_identity()`，开发通道只记 `code_identity()`；**无条件**与 train_meta["code_identity"] 逐文件比对，缺键/不一致 → PipelineScopeError（错误信息含双 git_head 与全部差异文件）；比对先于任何 VALIDATION 数据读取。**LOCKBOX**（:1484-1513）：同构——真实通道（bundle_builder is None ∧ 未注入）enforce；与 registry 同目录 run_meta.json 冻结身份无条件比对，文件缺失/缺键/不一致 → LockboxDisciplineError。两阶段 run_meta/run_log 落 `code_identity`/`code_identity_enforced`/双 git_head（:1209-1210、:1555-1557） | 14 项新反例测试（tests/test_factor_miner_round6_fixes.py）：篡改任一文件哈希/多键/少键双向拒收、缺 code_identity 键拒收、真实通道 enforce 调用与开发通道不强制、清单构成断言。既有夹具补嵌当前 `director.code_identity()` 后全绿。定向 41 项（round4+5+6）OK |

第 5 轮已接受项（universe 静态超集、descriptive_scan 冻结、测试泄漏修复）零改动。

## 二、新增解释性读法（3 条）

1. VALIDATION/LOCKBOX 的冻结身份比对基线：VALIDATION=TRAIN 批 run_meta；LOCKBOX=registry 同目录 run_meta.json（TRAIN 批或 VALIDATION 阶段副本，两处均落完整 code_identity）。
2. git_head 不要求跨阶段相等：文件哈希清单才是身份；阶段间的合法提交（内容不变）不构成身份变化，但两个 head 均落档可溯源。
3. 比对对开发/fixture 通道同样无条件执行（测试用合成 run_meta 嵌入当前 code_identity 满足）；只有 git 洁净强制（enforce_code_identity）限真实通道。

## 三、建议审核重点

1. 五依赖清单的完备性：除 `AUDITED_EXTRA_PATHS` + factor_miner 包 + 预登记 + 测试外，正式路径是否仍读取任何未入清单的代码/配置文件（尤其经 mrs 模块属性间接读取的路径）。
2. `configs/short-foundation-research.json` 入清单的合理性：它只决定数据根路径（用户数据集目录），不哈希数据内容本身——引擎侧数据身份由 universe 冻结与 registry data_version 承担，本文件入清单防的是路径语义漂移。
3. LOCKBOX 比对基线取 registry 同目录 run_meta 的链路在 VALIDATION→LOCKBOX 传递下是否闭合（validation 副本含完整 code_identity）。

## 四、解锁预告（不变）

PASS → 主对话显式翻转 REAL_RUN_UNLOCKED（提交留痕，含全部受审源码、工作区洁净——enforce 已实测拦截当前脏状态）→ R0 派发（REV/REL/STATE+META，连续因子，TRAIN-only）。事件型引擎路径不在本轮解锁范围。
