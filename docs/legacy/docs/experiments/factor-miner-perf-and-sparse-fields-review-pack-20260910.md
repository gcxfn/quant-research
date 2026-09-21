# 因子挖掘引擎 送审包：CS_RANK 记忆化性能修复 + 稀疏字段部分覆盖语义（R0 重启前置审核）

- 送审轮次：引擎第 7 轮（前六轮已 PASS，本包为解锁后受审文件变更的专项复审）
- 日期：2026-09-10
- 决策记录：D-2026-09-10-32
- 审核请求：**两项修复均为纯实现层变更（性能/健壮性），统计与冻结协议零改动；请审核后放行 R0 TRAIN 重启**

## 0. 事件背景（为什么解锁后又要改受审文件）

R0 TRAIN 首次正式运行（HEAD 06cb5d2，16:17 启动）3 小时无工件产出。py-spy 只读采样确诊两处实现缺陷（细节见 D-32）：进程已终止（引擎零落盘设计 → 无半成品污染，TRAIN 重跑免费，零损失）。用户指示修复须经 Codex 复审后才重启 R0。

## 1. 修复一：CS_RANK 截面求值 O(S²·D) 记忆化（性能）

**缺陷**：`evaluate()` 对每 symbol 调 `_eval_node`；AST 含 CS_RANK 时 `_eval_cs_rank` 每次调用都全符号重建 series_map + 逐日全市场排名后只取本 symbol 一列。S=5,552、D=972 时单节点 ~3×10¹⁰ 基本操作——实测 3 小时未完成第一个评估单元。合成 fixture 仅 2 只股票从未暴露。

**修复**（`experiments/factor_miner/compiler.py`）：
- bundle 实例属性缓存（`_fm_cs_rank_cache`）：series_map 按 child 节点冻结键（`_freeze_node`，嵌套 list→tuple 可哈希）缓存一次；逐日 ranked 按 CS_RANK 节点键缓存于 `{date_idx: ranked_dict}`，**按需填充不预填**（保持输出长度仍由请求 symbol 的 close 序列决定的旧语义，含 ragged/缺 close fallback 边界）。
- cross 构造与 `operators.cs_rank` 调用逐字保留（`_rank_at`）；series_map 构建逐字保留（`_build_series_map`）。
- 键不可哈希（理论边界）→ try/except TypeError 回退旧无缓存路径，正确性优先。
- **主对话追加内存围栏**（`director.py` evaluate_units）：①单元间 `compiler.clear_cs_rank_cache(bundle)`——246 单元共用同一 bundle，缓存不清理会跨单元累积至数十 GB；同单元内 train_test 与 evaluate_plan 仍共享缓存（节点重复即命中）。②`factors[key]` 仅在单元 TRAIN 门禁通过时保留——下游唯一消费者 monthly_vals/聚类只读通过者且已有 `key not in factors` 守卫（run_real_pipeline:892），全量保留 246×全市场序列必爆内存；VALIDATION 路径对 factors 整体丢弃（:714 `_factors`）不受影响。

**等价性证据**（`tests/test_factor_miner_cs_rank_cache.py`，9 项）：脏数据（不齐长度/缺 close fallback/None/inf/并列/部分覆盖）下 evaluate() 与测试内旧实现逐位拷贝参考一致；缓存坍缩计数（cs_rank 全截面调用次数=D 非 S×D、series_map 每节点构建 1 次）；同公式两处相同 CS_RANK 节点复用仍正确；跨 bundle 隔离；同 bundle 确定性。

## 2. 修复二：稀疏字段部分覆盖 → None 语义（正确性，探针实测复现）

**缺陷**：`CS_RANK(lhb_net_buy / circ_mv)` 类混合覆盖公式，series_map 按字段覆盖**并集**求值；LHB 仅覆盖上榜股票，缺覆盖股票的字段查找触发 fail-closed CompileError。dev-smoke 探针 400 股实测复现（`missing data for field 'lhb_net_buy' symbol 'sh.600029'`）；正式 R0 第二个评估单元即崩（与性能修复无关、旧代码同样崩——首次运行未到该单元）。

**修复**（`compiler.py` `_none_series_for_partial_field` + 字段分支）：
- 已知非价格字段（`data_fields.FIELD_REGISTRY` group≠PRICE）对个别股票缺覆盖 → 返回对齐该股 close 轴的全 None 序列（无信号），与截面排名 None 跳过、算术 None 传播（operators.arith 既有语义）一致。
- fail-closed 边界完整保留：未知字段名（编译期白名单已拦截，求值层纵深防御）、已知但本 bundle 未装载字段、**PRICE 组字段缺股票**（bundle 构建保证价格字段全符号在场，缺失=构建异常）、该股无 close 轴——均照旧抛 CompileError。
- 覆盖内股票的稀疏日期本就为 None（`align_series_to_axis` 语义），全 None 序列是同一语义的极端情形。

**证据**（`tests/test_factor_miner_sparse_fields.py`，7 项）：混合覆盖 CS_RANK 值与手工参考一致且缺覆盖股票全 None 不崩；裸稀疏字段公式缺覆盖股票得 None 序列；四条 fail-closed 边界反例（未知名/PRICE 缺股票/未装载/无 close 轴）仍抛错；确定性。

## 3. 解锁后测试债务（非本修复引入）

round2 `test_formal_path_still_fail_closed_when_locked` 与 round5 `test_manual_run_train_does_not_leak_real_run_unlocked` 在 D-2026-09-10-27 解锁翻转默认值后即失效（断言锁定态），本包一并修复：显式钉住 `REAL_RUN_UNLOCKED=False` 于 try/finally（与 06cb5d2 的 director 测试同法）。修复前可独立复现失败、与 compiler 变更无关。

## 4. 测试与探针

- 全 factor_miner 套件：**217 项全绿**（`python -m unittest discover -s tests -p "test_factor_miner*.py"`；含新增 9+7 项与修复的 2 项）。
- dev-smoke 通道探针（ sanctioned dev 入口，`dev-smoke-train`）：5 个 CS_RANK 单元（含全部 5 条 LHB 混合覆盖公式）× 400 股 × n_dates=972，端到端 72 秒（建包约 65 秒+评估数秒）；registry 门禁结果正常产出（mean_ic 数值合理；400 股玩具切片不具统计代表性，仅冒烟）。
- 外推正式 R0：建包 10–20 分钟 + 246 单元评估约 1–3 小时（单线程、15.6GB 内存内：bundle ~6GB + 单元内瞬时缓存 + 通过者因子）。

## 5. 变更文件清单

| 文件 | 变更 |
|---|---|
| `experiments/factor_miner/compiler.py` | 记忆化缓存 + clear 函数 + 稀疏字段 None 回退 |
| `experiments/factor_miner/director.py` | evaluate_units：单元间清缓存 + factors 仅留通过者（try/finally） |
| `tests/test_factor_miner_cs_rank_cache.py` | 新增（9 项） |
| `tests/test_factor_miner_sparse_fields.py` | 新增（7 项） |
| `tests/test_factor_miner_round2_fixes.py` | 过期锁定态测试钉旗标 |
| `tests/test_factor_miner_round5_fixes.py` | 同上 |

operators.py / engine.py / stats.py / validator.py / 预登记 / 全部统计参数：**零改动**。

## 6. 纪律声明

- REAL_RUN_UNLOCKED=True 授权边界不变：R0 TRAIN-only；VALIDATION/LOCKBOX 未授权、锁箱台账未触碰。
- 统计协议（α=0.10/N、bootstrap 种子 20260909、|RankIC|≥0.02、17/27/37bps、聚类 0.70）零改动；两项修复只影响"能否算完"与"缺覆盖股票按 None 处理"，不改变任何已算出的数字语义（等价性测试为证）。
- R0 TRAIN 重启以本包 PASS 为前置（用户指示）。

## 7. 建议审核点

1. 记忆化等价性：`_rank_at`/`_build_series_map` 与旧逻辑的逐字一致性；按需填充 ranked 对 ragged 长度语义的保持。
2. 内存围栏：单元间清理位置（finally）与 factors 仅留通过者是否影响任何下游（已核 :714 丢弃 / :892 守卫）。
3. 稀疏 None 语义的 fail-closed 边界是否如声明完整（尤其 PRICE 组不放宽）。
4. 探针工件：`artifacts/factor-miner/dev-probe-out/dev-smoke/20260910_190004/`（run_meta + registry.jsonl）。
