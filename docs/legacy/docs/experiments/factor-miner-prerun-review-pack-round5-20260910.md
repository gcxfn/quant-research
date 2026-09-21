# factor-miner 引擎 Codex 运行前审核送审包 第 5 轮（2026-09-10）

审核性质：运行前代码审核第 5 轮。第 4 轮 4 项全部修复+主对话复验通过。全仓 926 项 unittest OK/1 skip；REAL_RUN_UNLOCKED 保持 False。前包：round4。

**过程披露（如实记录）**：第 4 轮修复代理中途死亡（会话中断），留下 director.py docstring 半成品断裂（SyntaxError）；续修代理先修复断裂再逐项核验——第 1–3 项为死亡代理已完成（续修代理核验无改动），第 4 项（测试泄漏）与断裂由续修代理补齐。主对话独立复验全部通过。

## 一、第 4 轮处置（主对话复验）

| 项 | 处置 | 复验 |
|---|---|---|
| ①[P1] universe 遗漏退市股+TRAIN 窗静态过滤 | `load_formal_universe` 重写（engine.py:373-408）：universe=全历史 basic 静态超集（`load_basic_stock_map`：type=1、sh.6/sz.0/sz.3、**含退市**）∪ 数据集枚举去重并集；**"TRAIN 窗内≥1 合格日"静态过滤已删除**——退市股与晚成熟新股不被静态排除，每日截面资格只由 P1 动态掩码求值时决定。掩码调用（右端 TRAIN[1]）仅作 no_raw_daily 探测（baostock 日线缺失→fail-closed 排除计数）；not_in_basic 计数留档照常纳入。universe.json 披露 n_universe/n_delisted/semantics="static_superset_with_daily_p1_mask" | 主对话实测：超集 5,552 条、退市 337 只（与 Codex 独立核对及主对话复算逐位一致）、sh.600631（outDate 2011-08-23）在集；round5 反例测试 8 项含"TRAIN 窗内全不合格仍留超集/晚成熟新股不排除" |
| ②[P1] code_commit 不能标识未跟踪受审代码 | `code_identity()`（director.py:62-126）= git_head + 受审文件 sha256 清单（experiments/factor_miner/ 全部 .py、预登记、tests/test_factor_miner*.py 共 24 文件）写入 run_meta（dev-smoke 亦记录）；真实数据通道读取数据前 `enforce_code_identity` fail-closed：任一受审路径未跟踪或相对 HEAD 有改动 → RuntimeError 列出违规路径（解锁提交必须包含全部受审源码且工作区洁净）；dev/fixture 只记录不强制（run_meta `code_identity_enforced` 字段区分） | 主对话实测清单 24 文件覆盖全部预期路径、无多余；round5 反例：未跟踪/脏工作区两路径拒收 |
| ③[P1] 非基准窗口过线被静默丢弃 | 语义冻结=**仅基准单元（is_base）参与正式 TRAIN 门禁与 VALIDATION，其余 descriptive_scan**（家族代表制）：run_meta `n_train_gate_pass` 只计基准单元，新增 `n_train_gate_pass_all_units`+`gate_semantics`；candidates.jsonl 每行 `disposition: formal_gate/descriptive_scan`；validation 阶段非基准行不再静默 continue，落该阶段 rejected 带 `reject_reason="non_base_descriptive_scan"`；registry `gate_pass` 只对基准单元置 True；INTERPRETATION_NOTES 新增条款（引用预登记家族代表制多重检验口径） | round5 反例：disposition 生成、gate_semantics 落档、registry 基准限定、validation 留痕四路径 |
| ④[P2] round4 测试解锁状态泄漏 | `StageSplitTests._run_train`（test_factor_miner_round4_fixes.py:112-137）改 try/finally 就地保存/恢复 REAL_RUN_UNLOCKED 与 load_formal_universe，不依赖 addCleanup | 主对话按 Codex 报告顺序实跑 `tests.test_factor_miner_round4_fixes tests.test_factor_miner_director` 36 项 0 失败；round5 回归测试：手工实例化调用后断言 REAL_RUN_UNLOCKED is False |

新增 `tests/test_factor_miner_round5_fixes.py` 8 项；第 1–3 轮已通过项未动。

## 二、解释性读法（新增 1 条）

6. 非基准评估单元（is_base=False）为描述性扫描：正式 TRAIN 门禁统计与 VALIDATION 只计基准单元（家族代表制——多重检验校正只施加于基准评估单元，其余窗口仅作描述性披露）；描述性窗口过线不构成晋级依据。（已作为 INTERPRETATION_NOTES 第 5 条入 run_meta。）

## 三、建议审核重点

1. universe 静态超集语义：no_raw_daily 探测用 TRAIN[1] 作读取右端是否引入窗口依赖（掩码结果未用于过滤，仅探测可得性——退市股全量有 raw，实测排除应为 0）。
2. code_identity 的受审文件集合完备性（是否遗漏影响正式运行结果的路径——如 quant/ 依赖在引擎侧经 mr_statarb 装载器，其哈希是否应纳入清单；当前清单=factor_miner 包+预登记+测试）。
3. 基准单元语义与 registry/train_meta 的对应（base_unit_key 判定链）。

## 四、解锁预告（不变）

PASS → 主对话显式翻转 REAL_RUN_UNLOCKED（提交留痕，含全部受审源码）→ R0 派发（REV/REL/STATE+META，连续因子，TRAIN-only）→ R0 工件回归审核通道。
