# 系统审计 wave1 复审修复包 — Codex round-2 送审包

- **送审日期**: 2026-09-11
- **裁决来源**: `docs/experiments/system-audit-wave1-independent-review-20260911.md`(round-1 对 7eb7a67 的 CHANGES_REQUESTED;五项 W1 主张+§二三条用户命名裁决+§三处置表+§四次序)
- **验证仪器**: `experiments/system_audit_wave1_independent_probe_20260911.py` —— Codex round-1 原探针,**未做任何修改**随本包入库;`docs/experiments/system-audit-wave1-independent-probe-20260911.json` 为修复后复跑输出捕获。主对话全部修复验证均以该探针为权威仪器(审核方工具验证审核方主张)。
- **提交**: 单一 commit(本包与全部修复同 commit 入库;不预填 hash 以避免提交—回填循环,Codex 按送审时 `git log -1` 核对)。
- **送审请求**: 审核 round-1 全部条目的修复与并行交付物;PASS 前不重启 R0、不改变 VALIDATION/LOCKBOX 状态、变异测试不作为任何门禁。

## 0. 本包范围

round-1 五项缺陷(W1-01..05)全部修复、§二三条用户命名裁决全部落实(§二.1 轴广播方向、§二.2 成本口径与命名、§二.3 proxy 字段统一不回退)、§三第 4 条预登记 §5 措辞更正("重等权仅对实际成交集"→"未成交资金留现金、不得向成交者重配")、§三第 11 条 TW 五项按裁决方向实现。同波并行交付一并入库:变异测试基建(MT-0 驱动器+MT-1 规格,**未运行**——修复波改动了锚点文件,按计划 round-2 提交后重验锚点再生漂移规格再整批跑)、实验索引(EX1)、死区簿(EX2)、证据图(EG)、V3 生产池商品 ETF 修复(V3P,用户确认 D-2026-09-11-04)。实现全部由 flash 子代理按互斥文件领地完成(F1 轴对齐/F2 连续账本/F3 算子与注册表/F4 检查器/V3P 生产池),主对话逐项对抗复验;主对话不担任独立审核,Codex 仍是唯一独立审核方。

## 1. 修复清单

| 项 | 级别 | 内容 | 主要文件 | 状态 |
|---|---|---|---|---|
| W1-01 | P1 | warmup 截断日期错位:`truncate_to_region` 后因子轴与传入 `cost_ladder` 的 dates 轴不一致 | factor_miner/director.py | 已修+探针复验 |
| W1-02 | P1 | 递延持仓只挡同股不扣资金、无连续账本 → 跨月连续权益账本+资本约束 | factor_miner/backtest.py、amendment §5 | 已修+守恒手算复验 |
| W1-03 | P1 | `_exec_day_check` 只拒全字段缺失:部分缺失/None/inf volume/isST=None 均放行,字符串 volume 裸 TypeError → 必需字段+类型+有限性 fail-closed,稳定理由码 | factor_miner/backtest.py | 已修+探针五例复验 |
| W1-04 | P2 | 无信号现金月 gross=null 被均值剔除 → month_type 判定,cash 月 0.0 计入 | factor_miner/backtest.py | 已修+探针复验 |
| W1-05 | P1 | 主对话 constarg 扫描 glob 漏 hypotheses/ 层+退出码恒 0 → 已修;修正后 R0=1/R1=12 命中(首版"R0 九结构"叙述撤回);F3 修复后重扫全池 0 命中 | system_audit_constarg_scan_20260911.py | 已修+双绿复验 |
| TW-1 | (裁决§二.1) | 常量实参按**明确数据轴**广播(非编译期拒绝);纯/numpy 同步;不等长显式拒;纯常量公式=常量序列 | compiler.py、operators.py、operators_np.py | 已修+13 受害者清零 |
| TW-2 | (裁决§三.11) | 缺 PRICE 拒绝边界统一:幽灵股票(无 close 轴)标量/CS_RANK/numpy 三路径同一 fail-closed | compiler.py | 已修+双路径测试 |
| TW-3 | (裁决§三.11) | universe=显式 close 轴契约,废除任意 first-field 兜底(可固定 close+修文档) | compiler.py | 已修+契约测试 |
| TW-4 | (裁决§三.11) | registry load 拒绝冲突与相同重复 id(报路径+行号);upsert 留身份历史;显式 upsert 与静默 load 覆盖分开 | registry.py | 已修(LOW 残留见 §6.1) |
| TW-5 | (裁决§三.11) | factor_id 必须非空字符串 | registry.py | 已修 |
| §二.2 | 用户裁决 | "精确税佣净额(不含滑点)"命名;最低佣金临界=2 万元(非 5 万);17/27/37 降 proxy 描述字段;20bps 算术认可但不作 Top15 真实统一成本;不改冻结阈值不改写历史工件 | backtest.py、amendment §5.4 | 已落实 |
| §二.3 | 用户裁决 | ④⑤门禁判据不回退:`net_edge_proxy` 缺键/None → `net_edge_<N>bps_undecidable` 判拒绝;legacy 回退仅显式 opt-in 测试档 | director.py(`_tier_edge_for_gate`)、gate_corrections 测试 | 已修+测试 |
| §三.4 | 处置表 | amendment §5"重等权"→"未成交资金留现金、不得向成交者重配" | amendment §5 | 已改 |
| (并行) | — | MT-0 变异驱动器+MT-1 276 规格(未运行)、EX1 索引、EX2 死区簿、EG 证据图、V3P 商品池修复 | 见 §5 | 已验收 |

## 2. 实现要点

**W1-01(F1,director.py +123)**:`evaluate_units` 中 `truncate_to_region` 截断 raw 后,传入 `cost_ladder` 的 dates 同步改为截断后的 `bt_dates`(原为全量 dates);新增 `_assert_axis_aligned` 在调用前断言因子轴与日期轴逐位对齐(不对齐即崩,防回归)。

**W1-02(F2,backtest.py 重写)**:跨月连续权益账本——全局现金跨月记账(费用挂账可为负);每期期初现金归一为 max(0, 目标槽位−递延占用)×单笔名义(注入/撤回记 `capital_injected`,不计当月收益,非复利机制假设);`equity_start=现金+递延持仓入场日开盘市值`;新开仓名次高者先填槽,同股在途→`carry_still_held`、无空闲槽位→`no_free_slot`、本金不足→`no_free_cash`;期内实际退出按实际退出价回笼现金计卖出费;期末未了结仓位按下一入场日开盘 MTM(缺行回溯最近可得收盘);月 net=期末权益/期初权益−1,gross=(权益变动+本期费用)/期初权益;递延收益按 MTM 拆分归属(买费归入场月、卖费归卖出月,不重不漏);逐月 `ledger` 块披露全部现金/持仓/权益分项供复算;`position_net_return` 降级为独立逐笔标签函数,组合 gross/net/门禁输入唯一来源=账本。**与旧口径一致性**:正常整月往返(无递延)与旧"目标槽位+现金"分母逐位一致(测试双验证)。

**W1-03(F2)**:`_exec_day_check` 必需字段判定——tradestatus/isST ∈{0,1} 整数(拒 bool,兼容 numpy 标量)、volume 有限数值>0;理由码 `partial_status`/`invalid_status_type`/`nonfinite_volume`/`st_unknown_on_exec`,既有 `suspended_on_exec`/`zero_volume`/`st_on_exec` 语义不回退;`execution_status_from_rows` 派生语义不动(行缺字段仍记 None,与执行判定分离)。

**W1-04(F2)**:`month_type` 判定 immature→None 剔除;cash_no_signal/cash_blocked→0.0 计入均值;normal。全 None 因子月=真现金月由账本自然给 0.0。

**TW-1/2/3(F3,compiler.py +150、operators.py、operators_np.py +124)**:常量标量按显式数据轴长度广播(纯路径 `_broadcast` 用轴长,numpy 路径同步);不等长输入显式拒绝防 zip 截短;纯常量公式输出常量序列;CS_RANK 子表达式 universe 契约——引用字段=覆盖符号并集、纯常量=close 轴全体、皆空 fail-closed;`_eval_cs_rank` 输出长度=显式 close 轴(废除 first-field 兜底);幽灵股票三路径统一拒绝;轴长契约先于 series_map 校验。

**TW-4/5(F3,registry.py +69)**:load 逐行读入遇重复 factor_id(冲突或相同)报错退出,消息含路径+行号;`_check_factor_id` 要求非空字符串;upsert 身份历史链(前快照 deepcopy 入 history);显式 upsert 幂等(同对象/同内容不增长历史)。

**§二.3(F1 领地,director.py)**:`_tier_edge_for_gate(bt, tier, allow_legacy_net_edge=False)` ——正式路径读 `net_edge_proxy`,缺键/None 返回 None → 门禁按 `net_edge_<N>bps_undecidable` 判拒绝;legacy 回退仅显式 opt-in(历史测试档),主管线不可达。

**F4(检查器,np_dualpath_diff_probe.py +107、registry_compare.py +147)**:numpy 参与性验证=真实分派计数(零分派 FAIL);覆盖判据 `coverage_ok=(compile_fail==0) and (exc_units==0)`;VERDICT 只有双一致+覆盖才 PASS,bare PASS 消除;REAL_EVALUATE_ALL 守卫。

## 3. 探针复跑结果(权威验证,仪器=Codex round-1 原探针)

| 探针段 | round-1 结果 | 本包结果 |
|---|---|---|
| execution_status 五例 | 仅全缺拒;字符串 volume TypeError | 五例全部 [false, 稳定理由码]:partial_status / st_unknown_on_exec / partial_status / nonfinite_volume / invalid_status_type |
| carry_months(探针场景) | B 照常入场(资金未扣) | m1:A 持有入次月;**m2:B `no_trade:no_free_slot`**,A 03-05 实际退出回笼 49962.50 |
| empty_signal_month | gross=null 被剔除 | month_type=cash_no_signal,gross/net=0.0,全 ledger 字段落盘 |
| warmup_alignment | dates 90 vs factor 首值错位 | dates_length=90=factor_length,first_date=2020-01-29=first_factor |
| corrected_scan | (round-1 指出脚本双 bug) | R0 250 行 0 命中、R1 215 行 0 命中、0 其他错误 |

**守恒手算(主对话独立复算,贯穿递延场景)**:m1 equity_end 49987.50 + m2 注入 12.50 = 50000 = m2 equity_start;m2 equity_end 49962.50 + m3 注入 37.50 = 50000。两月净 −0.00025/−0.00075 复合 ≈ −0.001 = 全往返精确税佣费用 50/50000(买费 12.5 归 m1、卖费 37.5 归 m2,不重不漏)。测试 `TestContinuousLedgerConservation` 三期全 ledger 字段手算对账+全月循环不变量断言。

## 4. 主对话对抗复核记录

1. **五项 W1 主张逐项亲证**(round-1):全部用 Codex 原探针复跑坐实,无驳回项;W1-05 主对话自认扫描脚本双 bug(glob 漏层+退出码),修正后撤回"R0 九结构"叙述。
2. **本包修复逐项复验**:探针四段全绿(§3);F2 双模块 46 测试独立复跑 OK;五新测试文件合跑 117 OK;守恒算术手算复核;amendment §5 措辞、2 万临界注释、"精确税佣净额"命名全文 grep 核实(无"完整成本权威净收益"肯定性表述)。
3. **constarg 扫描收尾**:F3 修复后主对话重扫全池 465 行 0 命中;`_SelfTest` 原断言缺陷现状,已改断言修复后行为(IF 序列条件+常量臂→close 轴等长,动态对轴长),自检+主扫描双绿。
4. **领地外测试裁决(5 个,主对话以协调者身份改判并注明缘由)**:F1/F3 修复致 5 旧测试红——3 个钉 TW-3 已废除的 first-field 兜底(`test_factor_miner_cs_rank_cache.py` 改钉新 close 轴契约)、2 个喂 legacy net_edge-only 旧形状 dict(`test_factor_miner_engine.py`/`test_factor_miner_round4_fixes.py` 夹具补 net_edge_proxy 键)。**旧测试更新不作为修复正确性证明**,正确性证据=§3 探针+新反例测试。
5. **稳定性**:全仓 `python -m unittest discover -s tests` = **1671 tests OK(skipped=1)**(wave-1 基线 1541→1671,新增 130);F2 交付时曾报一次未复现瞬时失败(合跑 tail 丢失 traceback),其后 12+ 次受控合跑(换序/5 个 PYTHONHASHSEED/反序/6 连跑)全绿,主对话验收合跑无复发,判为并行编辑期文件竞争。
6. **Codex 证据两文件**(review md+probe py)未修改,随包入库保溯源。

## 5. 并行交付物(同 commit)

- **MT-0**(`experiments/mutation_driver_20260911.py` 804 行+527 行测试):变异测试驱动器——字节快照恢复(严禁 git 命令)、白名单单文件(experiments/factor_miner/*.py+quant/validation.py+quant/execution.py)、锚点唯一匹配、逐变异子进程(PYTHONDONTWRITEBYTECODE+__pycache__ 清理)、FINAL_TREE_CLEAN 批末断言。**未运行**:修复波改动锚点文件,按计划 round-2 提交后重验锚点→再生漂移规格→分寓进程整批跑;MT 结果不作为任何门禁(送审请求)。
- **MT-1**(`artifacts/mutation-testing-20260911/specs_wave1.json`,gitignore 目录按路径引用):276 条变异规格 9 类矩阵(backtest 39/director 52/execution 38/operators_np 34/stats 29/operators 28/engine 25/compiler 21/validation 10)。
- **EX1/EX2/EG**:`docs/experiments/experiment-index-20260911.md`(109 实验索引)+`artifacts/experiment-index-20260911/experiments.jsonl`;`docs/experiments/experiment-clustering-20260911.md`+`artifacts/experiment-index-20260911/dead_zones.jsonl`(20 死区,machine-readable identity_keys,供 R1 预登记 EX-D 合并时机器比对);`docs/experiments/evidence-graph-20260911.md`。
- **V3P**(用户确认 D-2026-09-11-04):`configs/strategy.json` 池 55→52(剔除 sh518880 黄金、sz159985 豆粕、sh517520 沪深港黄金股——纯删除 diff,逐只留档 `docs/experiments/v3-pool-commodity-exclusion-20260911.md`);`scripts/build_pool.py` 排除规则补商品类;13 项排除测试。V3 规则零改动。对照回测按 D-04 时序在本包发出后跑。

## 6. 残留与开放项

1. **registry 同内容重放历史增长(LOW,知悉)**:fresh-dict 同内容 upsert 在**已发生过一次覆盖后**重放会累积 history(生产 get→改→upsert 同对象模式不受影响——prev 是 rec 即跳过)。不改代码,留档。
2. **F4 覆盖判据语义后果(知悉/触发时请裁)**:`coverage_ok=(compile_fail==0) and (exc_units==0)` 使"双一致但抛异常的单元"计入覆盖失败——真实批次若触发该情形,须门禁责任人裁决异常单元是否可豁免。
3. **R0 官方公式双一致异常(触发时请裁)**:round-1 扫描曾见 R0 批 numpy 路径长度不匹配异常(error_surface);F3 修复常量广播后重扫 0 命中,但真实数据批(非合成 bundle)的 numpy 双路径差分仍按 F4 新判据执行,异常单元出现时按上条裁决。
4. **死区簿位置(后续动作)**:`dead_zones.jsonl` 现在 gitignore 的 artifacts/ 下;R1 预登记 EX-D 机器比对需其受控可复现,届时挪至受控位置(configs/ 或 docs/data/)并在 R1 冻结清单登记——不在本包动。
5. **20/30/40 成本档**(§二.2 裁决留口):本次不改冻结阈值;若未来修订基准并保持 +10/+20 压力档,须明文登记 20/30/40 并处理与 34bps 粗筛线的关系——届时另立预登记修订送审。
6. **t0 证据四文件**(TA/TB 波产出:`t0_minute_evidence_20260911.py`/`t0_range_calibration_20260911.py`+两 md):AGENTS.md t0 量级表述修正待用户授权,四文件未入本 commit,授权后随表述修正一并入库。

## 7. 测试汇总

| 套件 | 结果 |
|---|---|
| 全仓 discover | 1671 OK(skipped=1) |
| 五新测试文件(wave2_backtest/constarg_registry/director/checker_gates/mutation_driver) | 117 OK |
| backtest 双模块(backtest_fixes+wave2_backtest) | 46 OK |
| F2 交付时三模块+全仓 factor_miner 套件 | 66 OK / 565 OK |
| constarg 扫描 --self-test + 主扫描 | 双绿(465 行 0 命中 0 错误) |
| V3P 排除测试 | 13 OK |
| F2 稳态压测 | 12+ 次受控合跑(换序/5 hashseed/反序/6 连跑)全绿 |

## 8. 送审请求

1. 审核 W1-01..05、TW-1..5、§二.2/§二.3、§三.4 全部修复与测试证据;探针可原样复跑(§3 为期望输出)。
2. 裁决 §6.2/§6.3 的触发时处理方式(或确认留待触发)。
3. PASS 前维持:R0 不重启、VALIDATION/LOCKBOX 不动、MT 不作门禁、历史 17/27/37 工件不改写。
