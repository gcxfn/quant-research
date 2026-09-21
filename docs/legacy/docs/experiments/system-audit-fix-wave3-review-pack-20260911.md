# 系统审计 wave2 复审修复包 — Codex round-3 送审包

- **送审日期**: 2026-09-11
- **裁决来源**: `docs/experiments/system-audit-wave2-independent-review-20260911.md`(round-2 对 b9373ba 的 CHANGES_REQUESTED;六项发现 W2-01..06)
- **验证仪器**: `experiments/system_audit_wave2_independent_probe_20260911.py` —— Codex round-2 原探针,**未做任何修改**随包入库;三份 JSON:`-json`（Codex 原始证据）、`-rerun`（主对话修复前复跑坐实）、`-postfix`（修复后全段翻绿）。主对话验收全部以该探针为权威仪器。
- **提交**: 单一 commit(本包与全部修复同 commit 入库;不预填 hash,Codex 按送审时 `git log -1` 核对)。
- **送审请求**: 审核 W2-01..06 全部修复;PASS 前不重启 R0、不改变 VALIDATION/LOCKBOX 状态、MT 不作为门禁。

## 0. 本包范围

round-2 六项发现全部修复,按复审 §4 指定次序:先"成交事件≠估值+估值时序+基准同窗"(W2-01/02/03,F5),再"跨月状态+轴入口校验"(W2-04/05,F6),单独修构池代码分类(W2-06,F7)。三代理领地互斥;5 个正交文件由主对话以协调者身份裁决修复(§4)。同包入库:上轮遗留更正(round-2 送审包 §6.3 误表、EG 图撤回叙述标注——见 §5)。

## 1. 修复清单

| 项 | 级别 | 内容 | 主要文件 | 状态 |
|---|---|---|---|---|
| W2-01 | P1 | 实际退出事件与 MTM 估值分离:`_new_slot` 仅 status=executed 设 sale_j/sale_value;未平仓保留数量/市值/资金占用,逐月披露 open_positions(含 mark_date/mark_stale_sessions);"持续停牌到样本末"端到端断言 | backtest.py、wave2_backtest 测试 | 已修+探针 |
| W2-02 | P1 | 估值双边界接口 `_mark_info`:开盘边界=当日 open 或**严格早于该日**的有效收盘(禁当日收盘);样本末=截止日收盘(缺失回溯);估值时点+陈旧会话数随持仓披露;测试全用 open≠close 数据 | backtest.py | 已修+探针 |
| W2-03 | P1 | 基准改逐名槽位生命周期(bench_pos):与组合同执行日资格/入场检查/退出调度/双边界估值/递延拆分/未决剔除;月 bench=活跃槽位期初期末价值等权;单资产同规则组合毛=基准毛(探针两月逐位);旧"完整未来交易标签"口径删除 | backtest.py、amendment §5.7 | 已修+探针 |
| W2-04 | P2 | 未成熟跨月传递:`_slot_re_resolve` 每期按原始退出目标重试(executed/mtm_deferred/维持未决);n_immature 从期末全部未决持仓重建;恢复只由新增行情触发 | backtest.py、amendment §5.8 | 已修+探针 |
| W2-05 | P2 | 轴入口统一校验:evaluate 入口共同日期轴(ragged close→CompileError);取数口校验符号∈close universe+序列长度=轴长(CS_RANK 子表达式同口);显式 symbols 与默认 universe 同契约;纯/np 同消息拒绝;D-32 稀疏全 None 合法保留 | compiler.py、operators_np.py | 已修+探针 |
| W2-06 | P1 | `VERIFIED_CODE_EXCLUSIONS` 受控代码排除表(517520.SH 跨境/518880.SH 黄金现货/159985.SZ 豆粕期货,逐只依据)先于 513 段与名称规则;`group_etfs` 行为保持重构供测试共用;517520 真实代码+简称反例+重建不带回验证 | build_pool.py、pool_exclusion 测试 | 已修+直验 |

## 2. 实现要点

**W2-01/02/03/04(F5,backtest.py +323/−94)**:`_new_slot` 槽位档案(组合与基准共用生命周期结构);卖出循环只处理 sale_j 非 None 的确认成交;期末 `_mark_info` 双边界估值(boundary="open"/"close" 显式传参,`_mark_price` 标量兼容接口保留供探针直调);bench_pos 全池逐名槽位、同规则无费用无资金约束;`_slot_re_resolve` 未决重试。amendment §5 新增第 6 条(估值接口+实际退出≠估值+顺延超限不自动重试+open_positions 披露)、第 7 条(基准同窗规则全清单+单资产毛相等验证要求)、第 8 条(未决调度与恢复条件)、第 9 条(披露键与旧 bench 口径作废声明)。

**W2-05(F6,compiler.py +115、operators_np.py +90)**:`_validate_market_axis`(bundle 全部 close 序列等长)/`_validate_fetched_series`(取数即校验:close universe 成员+长度对齐),`_eval_node`/`_field_np` 字段分支接线(np 侧先于缓存写入);`_rank_at`/`_build_ranked_np` 截面补缺失改防御性拒绝;两路径拒绝消息逐字一致。设计取舍:共同轴校验取 bundle 级(数据边界校验不按公式内容开关;生产 build_real_bundle 恒等长零误伤);`DataBundle.__init__` 不加校验(拒绝统一在求值入口)。

**W2-06(F7,build_pool.py +171/−17)**:排除表按 `_norm_thscode` 规范化精确匹配(防大小写/空白绕过);名称层黄金股放行保留(泛化语义)与代码表(已核实个案)分层不互替;docstring/rule 字段/运行打印同步。

## 3. 探针复跑结果(权威验证,仪器=Codex round-2 原探针)

| 探针段 | round-2 结果 | 本包结果(postfix JSON) |
|---|---|---|
| never_sellable | 停牌到样本末仍 exit_actual/卖税/回笼 | **[]**(无卖出流水;未平仓非零由端到端测试断言:n_open_positions=1/mv/status) |
| single_name_benchmark | m1 组合 −10% vs 基准 +10% | m1 双方 −0.1;m2 双方 +0.2222(1e-16 浮点差) |
| missing_boundary_open | mark=20(当日未来收盘) | **mark_at_open=10.0**(严格早于边界日收盘) |
| final_mark_helper | 10(open 优先) | **20.0**(按截止日收盘) |
| persistently_immature | m2 自动恢复 normal/0.0 | 两月均 immature/n_immature=1/net=None |
| removed_etf_reentry | keep_etf=True | **False** |
| axis_contract 三例 | 双路径静默吞 | 三例纯/np 双路径一致 CompileError(短序列/ghost 缺 close 轴/ragged close) |

## 4. 主对话对抗复核与协调者裁决

1. **六项主张坐实**(round-2 送达时):探针复跑逐项确认,无驳回。
2. **修复逐项验收**:探针全六段翻绿;F5 双模块 56 测试独立复跑;F6 三套件+新增 11 项;F7 18 项;全仓 `discover`=**1697 tests OK(skipped=1,0 失败)**(round-2 基线 1671→1697)。
3. **协调者裁决修复(5 文件,领地孤儿按新裁决改判并注明理由)**:
   - `experiments/np_dualpath_diff_probe.py`:合成 bundle 改 bundle 级均匀长度+移除"个别股票缺 close 但有子字段"构造(原为触发 TW-3 已废除的 first-field 回退;W2-05 后该构造只会制造非法 bundle)。
   - `tests/test_factor_miner_cs_rank_cache.py`:`_dirty_bundle` 改均匀长度 5(脏数据特征保留);"字段有数据但符号在 close universe 外"拒绝改由 F6 新增 W205AxisEntryContractTests case2 覆盖,本文件 fail-closed 测试改用全 absent 符号;`test_window_child_with_uneven_lengths` 更名 `test_window_child_with_dirty_values`。
   - `tests/test_factor_miner_numpy_path.py`:`_e2e_bundle` 改均匀 L=80;`test_cs_rank_length_exceeds_child_series` 改 `test_cs_rank_child_shorter_than_close_rejected`(旧 [1,1,1,None,None] 补缺断言按 W2-05 废除,改双路径 CompileError)。
   - `tests/test_factor_miner_round2_fixes.py`:集中度期望值 1.6/1.95→(1.6+1/11)/((1.6+1/11)+(0.35+2.54/12.54))≈0.75371,**主对话手算逐位核验**:第 4 月待决槽位(11 入/末值 10 等)样本末收盘 MTM 贡献合法入账(W2-01 未平仓保留市值+W2-04 待决传递的语义后果);冻结公式 Σ|单样本贡献| 未变,"先盈后亏不抵消"反例意图仍成立(assertNotAlmostEqual 0.6/0.85 保留)。
   - `experiments/system_audit_bcde_probe_20260910.py`:补 `LockboxDisciplineError` catch——原漏 catch 使探针第二进入(其自身设计)崩溃,且被误读为"manifest 被并行运行消费";**已核实其 registry/manifest/claim 全在 tempfile 临时目录,真实锁箱台账零污染**(全盘 find 无真实 registry 下 lockbox_ledger.d)。该探针 B 段仍钉 pre-B-03 三参 `build_market_axis` API(现 fail-closed),属历史仪器:其 committed JSON 证据留档,不进本轮验证组;未追改至新 API。
4. **W1 语义不回退**:守恒不变量、W1-02 资本约束、W1-03 执行日五例、W1-04 现金月全部保持绿(回归测试原样通过)。

## 5. 上轮遗留更正

1. **round-2 送审包 §6.3 误表更正**:原文"R0 官方公式双一致异常(round-1 扫描曾见 R0 批 numpy 路径长度不匹配异常)"表述错误——round-1 修正后证据为 **R0 250 行仅 REV_cond_15 一条空序列命中;两条长度不匹配异常在 R1 池;且当时扫描走默认纯路径**(非 numpy)。已提交的 round-2 包文本不改(保持送审原貌),以本条为准。
2. **EG 图标注**(复审 §3.5):`docs/experiments/evidence-graph-20260911.md` 头部加快照截止(HEAD=d7eeed7 时点)与「R0 九结构」撤回叙述标注(更正后:R0=1/R1=12 命中;TW-1 修复后重扫全池 0 命中)。
3. **registry 身份历史界定**(复审 §3.3):接受"get 返回引用、原地修改无快照"的如实界定;TW-4/5 按 round-2 裁决单项闭合;fresh-dict 重放增长列为后续可选修复(不阻塞)。
4. **MT 纪律**(复审 §3.4):276 条规格已按 round-2 后代码重锚(MT-2 代理,13 条漂移规格逐条等价改写,dry-run 276/276 VALID+FINAL_TREE_CLEAN,主对话独立复跑+程序化 diff 恰 13 条+语义复核);**整批执行仍待独占期**(无并行写代码任务+先确认未变异基线全绿),本轮未跑,不报杀伤率。
5. **EX1/EX2/EG 定位**(复审 §3.5):接受"索引与审查线索,非新独立裁决"定位;死区簿用于 R1 机器比对前将移至受控位置再审。

## 6. 残留与开放项

1. **递延超限不自动重卖**(§5.6 冻结保守口径):顺延超限持仓永不自动卖出、永久占槽并披露;产品层若要求"恢复交易后补卖"须另行预登记重试窗口语义。
2. **静态数据轴下跨月恢复不可端到端触发**:恢复条件机制以 `_slot_re_resolve` 机制级测试覆盖(注入新行验证两分支);真实跨月恢复需数据自然补齐场景。
3. **bench 口径变更**:`bench_gross/net_edge/net_edge_proxy` 数值与旧工件不可比(amendment §5.9 已声明旧口径作废);此前使用旧 bench 的工件不得复用。
4. **bcde 探针 B 段**:钉 pre-B-03 API 的历史仪器(见 §4.3),留档不改。
5. **双路径一致异常政策**(复审 §3.1):接受"不豁免为成功覆盖、触发时按预冻结政策登记处置、不得见结果后删候选/缩 N/改写 PASS";真实批次触发时按此办理并送裁。
6. **现金归一模型定位**(复审 §3.2):接受"明确披露的研究模型"定位;Top15 文字改历史示例、每笔费用按金额与最低佣金计、持仓规则入后续组合精测冻结——留待组合精测预登记(本包不动 17/27/37 历史阈值)。

## 7. 测试汇总

| 套件 | 结果 |
|---|---|
| 全仓 discover | **1697 OK(skipped=1,0 失败)** |
| F5 双模块(backtest_fixes+wave2_backtest) | 56 OK |
| F6 三套件(c_components+constarg_registry+np_tools) | 202 OK |
| F7(pool_exclusion) | 18 OK(原 13+新 5) |
| 协调者三文件(numpy_path+cs_rank_cache+round2_fixes 等) | 127+9+专项全绿 |
| wave2 探针(修复前坐实/修复后翻绿) | rerun/postfix 双 JSON 入库 |

## 8. 送审请求

1. 审核 W2-01..06 修复与 §4 协调者裁决(尤其 §4.3 集中度期望值手算与 §4.4 的 5 文件改判)。
2. 裁决 §6 各残留的接受性。
3. PASS 前维持:R0 挂起、VALIDATION/LOCKBOX 不变、MT 非门禁。
