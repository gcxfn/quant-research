# factor-miner 引擎 Codex 运行前审核送审包（2026-09-10）

审核性质：**运行前代码审核**（引擎尚未接触任何真实数据——`REAL_RUN_UNLOCKED=False` 恒锁，`--allow-real-run` 实测 fail-closed 返回 rc=2 不触数据）。
预登记：`docs/plans/factor-miner-engine-preregistration-draft-20260910.md`（用户批准 D-2026-09-10-06）；蓝本存档 `docs/plans/factor-miner-blueprint-reference-20260910.md`。
实现：flash 子代理一次完成；主对话独立审查通过（本包§三）。解锁协议：Codex PASS 前由主对话保持 `REAL_RUN_UNLOCKED=False`，PASS 后显式翻转并提交。

## 一、交付清单

`experiments/factor_miner/`（10 模块+任务书，零第三方依赖）：

| 模块 | 行数 | 要点 |
|---|---|---|
| schema.py | 109 | §4 字段清单、禁多余键、event 不走公式层 |
| validator.py | 164 | R1–R6 六条强制校验、rejected.jsonl、合并去重（holding_days 并集+lineage） |
| operators.py | 283 | 白名单 v1 全集；NaN=None 传播、min_periods=全窗、STD ddof=1 |
| compiler.py | 345 | 递归下降解析（无 eval）；白名单/负偏移/超长窗编译期拒绝；窗口归一化 canonical→sha256 |
| data_fields.py | 185 | §2 字段注册+时点元数据（available_at 五类）；PRICE 惰性复用 mr_statarb 装载器 |
| partition.py | 96 | 三区冻结；非授权 LOCKBOX 请求/重叠窗口抛 `LockboxViolation`；`train_only_window` 实现期收口 |
| stats.py | 246 | 月末 RankIC（Spearman 平均秩）、衰减曲线、月块 bootstrap **复用 mr_statarb.block_bootstrap_mean_ci**（块3月/B=10000/种子20260909）、十分位毛差、粗筛门禁 |
| registry.py | 119 | §7 最低字段、6 status、12 死亡标签强校验 |
| director.py | 284 | collect→validate→dedup→compile→train-test→gate→registry；`--lockbox` 独立留痕；真实数据 fail-closed |
| prompts/researcher_v1.md | 51 | 蓝本§5+预登记白名单约束冻结版 |

测试：新增 **109 项**（每算子窗口/NaN/时点、validator 正反例、partition 越区异常、compiler 注入防御、7 vs 8 日归一化同哈希、bootstrap 退化 fail-closed、合成 fixture 端到端、锁箱留痕、真实数据 fail-closed）。全仓 unittest 787 OK（skipped=1）；主对话 pytest 复跑 786+1 skip 绿；既有测试零损伤（mr_statarb/event_family/quant/* 未修改，mtime 核对：event_family.py 00:59 修改属事件修复代理已声明范围）。

## 二、建议审核重点（单点故障三处）

1. **compiler.py**：解析器完整性（未覆盖的语法路径）、CS_RANK 横截面求值的长度对齐（`_eval_cs_rank` 以 close 序列长度为基准）。
2. **validator.py R5 去重**：窗口归一化只归一化窗口位整数字面量——若两构造仅阈值常量不同（如 IF 内 0.5 vs 0.6）将判为不同因子（见歧义1）。
3. **partition.py**：窗口重叠检测、train_only_window 与 VALIDATION 读取的衔接（R3 VALIDATION 阶段经 region_window("VALIDATION") 合法读取 2023–2024）。

## 三、主对话独立审查记录（2026-09-10，全部亲手复验）

1. 全仓测试复跑绿；冻结文件 mtime 归属核对（见上）。
2. 对抗注入 10 项：非法算子拒收✓、机制空拒收✓、**7 vs 8 日窗口同哈希✓/RET vs MEAN 异哈希✓**、合并去重 holding_days=[5,10] 且 merged_ids 留痕✓、跨锁箱窗口抛 LockboxViolation✓、直接请求 LOCKBOX 抛✓、实现期读 2023 抛 PartitionError✓、多余键拒收✓、注入 t_plus_5 未来字段 R3 开火✓、director --allow-real-run fail-closed✓。
3. PV 一致性：stats bootstrap 直接复用 mr_statarb 同函数（与已过四轮审核的实现同源）。

## 四、待裁决解释性读法（实现代理 7 条+主对话 1 条）

1. **窗口归一化范围**：仅窗口位整数字面量归一化为 N；表达式常量（IF 阈值等）保留参与哈希——避免阈值调参并入去重，但意味着"仅阈值不同"会立为新因子。
2. **STD ddof=1**：预登记未写明；对齐 mr_statarb std_sample 口径。
3. **RET/DELTA 偏移**：RET(x,n)=x_t/x_{t−n}−1（n 滞后、占 n+1 观测）；滚动算子用 n 观测窗。
4. **IF 条件语义**：白名单无比较算子，取 cond≠0 且非缺失→a，缺失→缺失。
5. **TS_RANK/CS_RANK**：窗口内 ≤当前值占比；平均秩/参与数∈(0,1]，缺失不参与。
6. **schema 禁多余键**：清单外键一律拒收（最保守）。
7. **train_only_window 实际上限为 TRAIN 右端 2022-12-31**（严于 docstring 所写 2023-12-31，行为更保守；docstring 措辞瑕疵留档）。
8. **【主对话补充】PIT_SAFE 含 lhb_day_plus_1 → R3 对当前注册表零覆盖**：读法依据=冻结执行纪律（t 收盘后出信号、t+1 开盘执行），龙虎榜当日盘后发布视为 t 晚间可知，margin/daily_basic 同理（t_close）。R3 对注入的 t_plus_5 字段正常开火（防线存在）。请裁决该 PIT 读法是否接受，以及"R3 零活覆盖"是否要求在未来字段注册时强制显式标注。

## 五、解锁后首批动作（预告，非本包范围）

R0 挖掘（REV/REL/STATE+META 矿区，researcher_v1.md 任务书）须在本审核 PASS、`REAL_RUN_UNLOCKED` 翻转后派发；R0 全程 TRAIN-only（2020–2022），hypothesis JSONL 经 validator 后入引擎。
