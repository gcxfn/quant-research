# R0-1 wave3 六项修复独立复审（任务B）

- **日期**: 2026-09-11　**审查者**: GLM-5.3/MAX（严格代理模式任务B，独立执行）
- **审查对象**: 提交 `0fb349b`（wave3 送审包 `docs/experiments/system-audit-fix-wave3-review-pack-20260911.md` 所列 W2-01..06 全部修复）；受审文件 `experiments/factor_miner/backtest.py`、`compiler.py`、`operators_np.py`、`scripts/build_pool.py` 及 6 个测试文件，经 `git diff HEAD` 核对与提交零差异（工作树其余脏修改 `quant/*` 系他人他任务在途，不交叉、未触碰）。
- **裁决来源**: round-2 独立复审 `docs/experiments/system-audit-wave2-independent-review-20260911.md`（W2-01..06 判据原文逐条对照）。
- **裁决**: **六项全部 PASS，未发现新的实现缺陷；无阻断**。本 PASS 仅覆盖 W2-01..06 修复复审，不构成 R0 重启授权（重启仍按计划须主对话运行前裁决 + 用户恢复决定）。

## 1. 验证方法与仪器

1. **权威探针复跑**（Codex round-2 原仪器 `experiments/system_audit_wave2_independent_probe_20260911.py`，零修改）：`python experiments/system_audit_wave2_independent_probe_20260911.py --output artifacts/r0-review-20260911/probe-rerun.json`，exit 0，六段结果与送审 postfix JSON **逐位相等**（程序化 `a==b` 为 True）。
2. **独立合成反例**（自建日历/行情/oracle，不复用受审夹具与断言；全部落 `artifacts/r0-review-20260911/`）：`independent_w201_w202_w204.py`（63 检查，exit 0）、`independent_w203_bench.py`（16 检查，exit 0）、`independent_w205_axis.py`（11 检查，exit 0）、`independent_w206_exclusion.py`（10 检查，exit 0）、`check_concentration_arithmetic.py`（exit 0）。首轮三处脚本自误（ledger 键名、oracle 价格归属、成功 dict/错误 dict 判定），修正后全绿——均为审查脚本缺陷，非实现发现，如实记录。
3. **受审测试模块限定复跑**（顺序、低负载，避开在跑的 B01 扫描）：九模块共 **335 项全 OK、exit 0**——wave2_backtest 26、backtest_fixes 30、wave2_constarg_registry 46、c_components 73、np_tools 83、cs_rank_cache 9、numpy_path 35、round2_fixes 15、v3_pool_exclusion 18。不将送审自报的全仓 1697 项写成本次独立复跑数。
4. **测试改判 diff 亲读**：cs_rank_cache / numpy_path / round2_fixes 三文件的协调者改判逐 hunk 审阅（见 §3.5）。

## 2. 六项逐条裁决

### W2-01 长期停牌账本 — PASS

实现：`_new_slot` 仅 status=executed 设 sale_j/sale_value；卖出循环只处理确认成交；期末 `open_positions` 披露（shares/mv/mark_date/mark_stale_sessions/status）。

独立反例（a 自 03-02 停牌至样本末、有价格行，7 个月）：全程 7 个月 `exit_actual={}`、`sell_fees=0`、`exit_proceeds=0`（零卖出印花税）、`n_open_positions=1`、shares=5000、状态恒 mtm_deferred_exit（递延超限不自动重卖，§5.6 冻结口径）。m1 精确手算全对：权益 50000→39987.5、net=−0.20025、gross=−0.2、买入费 12.5、卖费 0。资金守恒 `equity_start(k+1)=equity_end(k)+injected(k+1)` 逐月成立（含 m2 注入 12.5 归一负现金）。探针 never_sellable=[] 一致。

### W2-02 开盘边界估值 — PASS

实现：`_mark_info(boundary="open"/"close")` 双边界；开盘边界当日开盘、缺失回溯**严格更早**收盘；样本末按截止日收盘；返回 (price, mark_date, stale)。

独立反例（哨兵价）：边界日 04-01 开盘缺失、当日收盘 99 → 实测 mark=03-31 收盘 9.0、stale=1、mv=45000（99 从未出现于任何月估值）；样本末开盘 77/收盘 9.5 → 末月 mv=47500（77 未用）；开盘在场时用开盘（m1 边界 03-02 开盘 8 → mv=40000，非当日收盘 9）。探针 mark_at_open=10.0（禁当日 20）、final_mark=20.0 一致。

### W2-03 基准同经济窗（多资产/部分受阻/跨月/无信号月） — PASS

实现：bench_pos 逐名槽位生命周期（同执行日资格/入场检查/退出调度/双边界估值/递延拆分/未决剔除/同股不重复开仓）；月 bench=活跃槽位期初期末价值等权。

独立反例（quantile=1.0 持 a/b/c，7 个月，手算 oracle 全对到 1e-9）：a 正常往返、b 退出日停牌 03-23 恢复（跨月递延）、c 仅入场日受阻、04-30 信号全 None（无信号月）。实测 bench_m1=0.04（b 的 +0.2 **未**提前计入；旧完整未来标签口径会给 0.14，已反证排除）、bench_m2 含 b 恢复卖出 +0.2 且卖出事件落 m2（exit_actual b=2020-03-23）、无信号月 m4 组合 cash_no_signal gross=net=0.0 而基准照常 −0.019231、m7 三名未决 → bench=None 且组合 immature。组合 m1 gross=0.08/3 与账本一致（差异仅来自 c 现金槽位，非时间归属）。探针单资产两月组合毛=基准毛（−0.1/−0.1、+0.2222/+0.2222）一致。

### W2-04 未决状态递延 — PASS

实现：`_slot_re_resolve` 每期对 incomplete_label 按原始退出目标重试；n_immature 从期末全部未决持仓重建；mtm_deferred 不重试。

独立反例（a 自 03-02 行全删，7 个月）：全月 month_type=immature、n_immature=1、net=None（round-2 反例的"下月自动恢复 normal/0.0"不复现）、mean_net=None；m1 估值回溯 02-28 收盘、stale=1。机制级恢复（自建槽位+注入行情）：无新数据维持未决；注入 03-06 可卖开盘 12 → executed、sale_j=47、sale_value=60000；仅停牌行（有收盘不可卖）→ mtm_deferred_exit、sale_j/sale_value=None（不假卖出）。探针两月 immature 一致。

### W2-05 纯/np 轴入口与稀疏字段 — PASS

实现：`_validate_market_axis`（bundle 全部 close 等长）+ `_validate_fetched_series`（取数口：symbol∈close universe、序列长度=轴长）双路径逐字镜像；`_rank_at`/`_build_ranked_np` 防御性拒绝；D-32 稀疏 None 序列天然通过。

独立用例（探针三例之外）：ragged 4v3 双路径同消息 CompileError；字段序列**长于**轴（5 vs 3，探针只测了短于）双路径同消息拒绝（"series length 5 != close axis length 3"）；稀疏 pe_ttm 部分覆盖合法（b=[None,None,None]、a=[1,2,3]，纯/np 逐位相等，CS_RANK 同）；无 close 退化 bundle 按字段长度钉死行为不变；未被求值的多余 ghost 字段数据不拒（拒绝边界=被求值 symbol）；`operators_np.evaluate` 直调镜像入口同样拒绝 ragged。分离性：旧"补缺失 [1,1,1,None,None]"断言废除改为双路径拒绝（改判 diff 亲读，补缺语义已由 W2-05 明令废除，属正确改判非删反例；"字段有数据但符号在 close universe 外"迁移至 W205AxisEntryContractTests case2，已确认存在且通过）。

### W2-06 V3 受控排除（单独验收） — PASS

实现：`VERIFIED_CODE_EXCLUSIONS`（517520.SH/518880.SH/159985.SZ 逐只依据）经 `_norm_thscode` 规范化精确匹配，先于 513 段与名称规则；名称层泛化（GOLD_EQUITY）保留。

独立用例：真实代码+简称拒（False）；`"  517520.sh "` 大小写/空白绕过失败；518880/159985 配股票型名称仍拒（代码绑定独立于名称）；不在表的黄金股名称放行（泛化保留）；513 段、正常宽基照旧；keep_etf 过滤后经 `group_etfs` 重建不含任何已排除代码（机制级"重建不带回"）。**与 R0 门禁分离**：`rg VERIFIED_CODE_EXCLUSIONS|keep_etf|build_pool experiments/factor_miner/ quant/` 零命中；`tests/test_v3_pool_exclusion_20260911.py` 经 importlib 独立装载 scripts/build_pool.py，18 项单独验收通过，不与 R0 门禁混项。

## 3. 配套核验

### 3.1 集中度期望值改判（送审包 §4.3）— 算术复核 PASS

独立手算：a=1.6+1/11=1.690909090909，b=0.35+2.54/12.54=0.552551834131，top1=a/(a+b)=**0.753705612626** ≈ 0.75371（送审包数正确）；与旧符号累计口径 0.6/0.85=0.705882 差 0.0478（`assertNotAlmostEqual` 反例意图仍有效）、与旧期望 1.6/1.95=0.820513 差 0.0668（旧值确不再成立）。场景亲读确认：尾月待决槽位（a 11 入/末值 10、b 12.54 入/末值 10）样本末收盘 MTM 贡献按 W2-01/W2-04 语义合法入账，冻结公式 Σ|单样本贡献| 未变——期望值更新是语义后果不是公式变更。

### 3.2 测试改判未删除有效反例 — PASS

三文件 diff 逐 hunk 亲读：cs_rank_cache ragged 夹具改均匀（钉的宽容语义已被裁决明令废除）、全 absent 符号 fail-closed 保留（"zzz"）；numpy_path 补缺断言改双路径 CompileError；round2_fixes 见 §3.1。所有改判有裁决依据、反例意图保留或迁移到专项新测试。

### 3.3 受审身份 — 干净

六项修复的全部受审文件与 HEAD `0fb349b` 零差异；工作树脏修改（quant/analysis.py、quant/backtest.py、quant/cli.py、quant/portfolio_candidate.py、部分 tests/p4* 等）属他人任务在途，与受审文件集不交叉。

## 4. 残留与须主对话裁决事项（不构成六项阻断）

1. **MT 前置口径需主对话澄清**：`docs/decisions.md` 第 95 行存在用户 2026-09-11 批准的决策原文——"R0 重启新增前置(用户 2026-09-11 批准):MT 变异测试幸存者清零——清零定义:全部幸存 mutant 完成分诊;真盲区类(未来函数/费用/掩码时序/对齐/缓存键/排序方向/np 双路径分歧)补测试杀灭;语义等价变异留档豁免(非字面零幸存)。与既有前置(Codex PASS/AUDIT-1 类缺陷修复/引擎身份冻结/OS 分离启动器+资源独占)并列。"——A 的主张有此原文依据；但修订计划（`r0-completion-and-acceptance-plan-20260911.md` S3）写"关键风险注入 R0 前必须做（276 数量不是门槛）"。两份文件的门槛表述需主对话统一裁决，本审查不自行升级或降级任何一方。另注：decisions.md 第 36 行要求 MT 整批执行须独占期（无并行写代码任务），当前 B01 扫描在跑，客观上也不满足独占条件。
2. **静态数据轴下跨月恢复不可端到端触发**（送审包 §6.2 已披露）：单次调用内 incomplete 恢复只能机制级验证（本审查已独立复验两分支）；真实恢复需 director 级数据自然补齐场景，属 R0-3 小样本/正式运行验收范围。
3. **bench 口径数值不连续**（§6.3 已声明）：旧 bench 工件不得复用，此前使用旧口径的结论不因本 PASS 复活。
4. 递延超限持仓永不自动重卖、永久占槽（§6.1 冻结保守口径）——接受为冻结语义，产品层若需补卖须另行预登记。

## 5. 交付物清单

- `artifacts/r0-review-20260911/`：五个独立审查脚本 + `probe-rerun.json`（权威探针复跑证据）。
- 本报告。未修改任何生产/研究代码；未读取真实 VALIDATION/LOCKBOX 数值；未启动任何正式批次。
