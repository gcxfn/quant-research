# 系统审计二波修复包 — Codex 审核送审包（全量：审计八项 + 加固波）

- **送审日期**:2026-09-11
- **裁决来源**:`docs/experiments/system-audit-bcde-independent-review-20260910.md`(B~E 首轮,9 项发现)
- **配套预登记修订**:`docs/plans/factor-miner-engine-preregistration-amendment-20260910.md`(随本包一并送审,§1–§7 对应各修复)
- **送审请求**:审核全部修复、加固产物与预登记修订;PASS 前不据此运行任何正式批次、不恢复 R0、不改变 VALIDATION/LOCKBOX 状态。
- **提交**:单一 commit(本包与全部修复同 commit 入库;不预填 hash 以避免提交—回填—再提交循环,Codex 按送审时 `git log -1` 核对)

## 0. 本包范围

首轮审计 9 项发现的全部处置(B-01/B-02/B-03/C-01/C-02/C-03/C-04/D-01/D-02),加上按审计计划 A/D 阶段要求主动补的对抗测试波(发现并修复 2 个 execution 真缺陷、4 个检查器真缺口),加上送审前 flash 盲预审轮(U:3 项发现——P1-1 execution_status 管线未接线、P1-2 门禁④⑤读 net_edge 致 27bps 压力档静默失效、P2-1 超大 int OverflowError;V 轮修复)、C 组件边界审计轮(TW:5 个真缺陷钉住未修+常量实参 12/215 命中面扫描+5 条裁决边界)、数据普查轮(DC:B-03/B-02 开放问题的数据答案)、二次盲预审(U2:PASS 零 P1/P2,4 条 P3 已处置),以及配套分析工件(E 阶段影响矩阵、B-01 定位扫描脚本与报告、R1 候选池(17 文件 215 行,W4D/W4EF 已落并经主对话零碰撞复验;冻结时另出冻结清单与去重裁决)、Top15 成本口径表)。实现全部由 flash 子代理完成、主对话逐项对抗复验(独立复跑测试、亲测反例、diff 逐行复核);主对话不担任独立审核,Codex 仍是唯一独立审核方。

## 1. 修复清单与文件领地(按文件冲突边界并发切分)

| 项 | 级别 | 内容 | 文件 | 状态 |
|---|---|---|---|---|
| B-01 | P1 | 零方差语义:窗口 max==min → STD/ZSCORE/CORR 输出 None;两路径同步 | operators.py、operators_np.py | 已修+复验 |
| B-02 | P1 | 公共验证器拒 ±inf/NaN/非数值/缺键,检查器不崩 | quant/validation.py | 已修+复验 |
| B-03 | P1 | 因子日轴=冻结交易日历,缺行 None 占位不压缩;日历缺失/空窗 fail-closed | factor_miner/engine.py | 已修+复验 |
| C-01 | P1 | TRAIN α=0.10/N:端点 [α/2N, 1−α/2N];N=len(units) 自动派生入 registry | stats.py、director.py | 已修+复验 |
| C-02 | P1 | 门禁输入 fail-closed(NaN/inf/越界/乱序 → fail+invalid_ic_input) | stats.py | 已修+复验 |
| C-03 | P1 | 锁箱访问原子化:读数前 STARTED/FAILED/COMPLETED 三态留痕、候选集合排序规范化身份、跨 out_dir 共享占用点 | director.py | 已修+复验 |
| C-04 | P2 | 十分位并列平均秩分组+股序不变量+有限值过滤 | stats.py | 已修+复验 |
| D-01 | P1 | 成交日资格(停牌/零量/ST/未知/缺 raw_preclose;退出顺延+实际退出日+逐笔原因) | factor_miner/backtest.py | 已修+复验 |
| D-02 | P1 | 账本约束(未成交槽位现金口径分母 n_hold、递延持仓跨期追踪阻再开仓、未成熟月 None、同月配对)+精确费用(bps 三档降级 proxy 并注明关系) | factor_miner/backtest.py | 已修+复验 |
| EXEC-1 | P2 | 同 bar 卖出竞争改按成交价排序(兑现保守承诺;原按委托价,跳空时乐观) | quant/execution.py | 已修+复验 |
| EXEC-2 | P2 | 买入部分成交在所有板块执行完整手数网格(修复科创板/北交所 step=1 绕过最低手数;卖出语义不动) | quant/execution.py | 已修+复验 |
| CHK-1..4 | P2 | 检查器缺口:numpy 静默回落参与性验证×2、compile_fail 退出码、int↔float 类型翻转检测 | np_dualpath_*.py ×3 | 已修+复验 |
| U-P1-1 | P1 | 预审发现:主管线两处 cost_ladder 未接线 execution_status(D-01 机制死代码)→ TRAIN 阶梯+VALIDATION 门禁双点接线 | director.py | 已修+复验 |
| U-P1-2 | P1 | 预审发现:门禁④⑤读 net_edge(D-02 后不随档位变,27bps 压力档静默失效)→ 判据改读 net_edge_proxy,旧形状 dict 回退 net_edge(披露边界) | director.py | 已修+复验 |
| U-P2-1 | P2 | 预审发现:validate_bars 超大 int(10**400)OverflowError 裸崩 → _isfinite 溢出安全封装(OHLC+volume 两调用点) | quant/validation.py | 已修+复验 |
| TW-1..5 | P1~P3 | C 组件边界审计五缺陷:常量实参静默空序列(215 冻结公式命中 12,R0 官方批 9 条静默清零)/CS_RANK 缺价静默全 None/evaluate 缺省 symbols 写死/registry load 重复 id 末者胜/接受 None id | compiler.py、registry.py | **测试钉住未修,方向待裁** |

## 2. 各修复的实现要点与自查偏差

**B-01**(`operators.py`/`operators_np.py`):纯路径 `_std_sample` 在 `len<2` 检查后加 `max(win)==min(win)→None`(一处覆盖 STD+ZSCORE),`_corr` 加双侧常数窗 continue;numpy 路径 `_std_arr/_zscore_arr` 有效掩码追加 `w.max(axis=1)!=w.min(axis=1)`,`_corr_arr` 双侧谓词与 `sxx>0/syy>0` 并存——两侧谓词逐位对齐。**协议修订披露**:常数窗输出从伪值(如 ZSCORE([1.1]*60)=−0.9916…)变 None,属审计验收要求的语义修订,非兼容性保留;近常数窗(浮点残差级非完全相等)明确不在本轮,仍两遍式,docstring 双侧声明。Codex 三条原始反例两侧实测全 None。

**B-02**(`quant/validation.py`):OHLC/volume 逐项独立检查缺键/非映射行/非数值(含 bool 显式拒,旧代码静默接受 True)/非有限(±inf、NaN)/非正;日期不可比 try/except TypeError 干净报错;不变量检查只在四价全有效时做。旧报错文案与 `"row i (date):"` 前缀逐字保留(`daily_swing_oos.py:645` 行号解析契约兼容)。自查收紧:bool 拒绝属新语义(fail-closed 方向)。

**B-03**(`factor_miner/engine.py`):`build_market_axis` 第 4 参 calendar=冻结交易日历(tushare trade_cal,与 P1 掩码同源);`calendar is None`→RuntimeError(禁止回落行日期并集——即被审计缺陷路径);窗口零会话→RuntimeError;`build_real_bundle` 日历改无条件获取。个股缺行 None 占位继承 `StockRows.series` 既有语义,全池共同缺行保留会话输出降级。numpy 路径消费同一 bundle 自动继承(有环境变量守卫的双路径等价测试)。

**C-01**(`stats.py`/`director.py`):`_ci_spec`:n_tests 为正 int → lo=α/2N、hi=1−α/2N(α_total=0.10;N=246 端点 0.0203252%/99.9796748% 与审计期望值逐位一致);None→描述性 95%。`continuous_gate` 返回新增 `alpha_total/n_tests/ci_mode/ci_percentiles`。`evaluate_units` 与 fixture 管线自动派生 `n_tests=len(units)`(docstring 注明禁止手填);`update_registry` 经 `.get()` 守卫落 `train_multiple_testing` 字段。LOCKBOX `0.05/N_frozen` 独立路径零改动,测试钉住。

**C-02**:入口校验(非 None IC 必须有限且∈[−1,1],bool 拒)在 bootstrap 之前 fail-closed;bootstrap 输出 lo/hi 有限且 lo≤ho 校验;失败时 `mean_ic=None` 保守。

**C-04**(`stats.py decile_top_bottom_spread`):先 `avg_ranks` 赋平均秩(×2 整数化避免浮点边界),秩→十分位整组同档;端档求和前 `sorted()` 规范化(浮点加法不结合);非有限因子值/收益过滤。修复中额外发现并修复前任半成品缺陷:字典迭代序求和在逆转序时末位漂移。50 轮随机重并列正序/逆转/洗牌三向逐位一致(主对话亲测)。

**D-01/D-02**(`factor_miner/backtest.py`,+368/−55):`execution_status_from_rows` 执行日状态派生;入场五负例(停牌/ST/状态未知两路/无量/缺 raw_preclose→`no_trade:missing_preclose`);退出受阻顺延(上限 `EXIT_DEFER_MAX_SESSIONS=20` 后 MTM 披露);`open_pos` 跨期追踪+`no_trade:carry_still_held` 阻再开仓;未成交槽位现金口径(分母 n_hold,全现金月 0.0 计入均值);未成熟月 gross/net=None+`n_immature` 披露;net/bench 同月配对 `n_paired_months`;`trade_fee` 精确逐笔费用(股票佣金万 2.5 最低 5 元、卖出印花税 5bps)为权威口径,17/27/37bps 三档降级 `descriptive_proxy` 字段并注明 `DEFAULT_TRADE_NOTIONAL=50000` 机制假设与适用边界(scope_note:20万/15只≈13.3k/笔时最低佣金生效、非真实组合收益)。修复过程中纠正前任半成品三处错误(gross 重配缺陷实际未修只改注释、递延持仓双重开仓、未成熟月误记 0)。`tests/test_factor_miner_engine.py:270` 一处旧断言(assertIsNone(gross))编码了被审计判定的新旧语义变更,由主对话更新为 assertEqual 0.0 并注明缘由。

**EXEC-1/EXEC-2**(`quant/execution.py`):同 bar 卖出竞争从委托价排序改为先算每单本 bar 成交价(`_sell_fill_price` 跳空语义不变)后 `touchable.sort` 成交价升序(止盈限价@9.0 跳空高开 vs 止损 9.8 场景下,旧排序止盈乐观先行,新排序止损保守先行);`_part_fill` 买入方向全板块手数网格(qty<minimum→0 成交订单保留,attempt 仍 volume_cap),卖出零股清仓与 step>1 网格原样。两缺陷由对抗测试员以最小反例钉住(expectedFailure)后修复转正,73 项(71+2 新增)全绿。

**CHK-1..4**(`experiments/np_dualpath_diff_probe.py`/`registry_compare.py`/`stats_check.py`):numpy 参与性验证=monkeypatch `operators_np.evaluate`/`stats_np.*` 计数分派,零分派 FAIL(修复"numpy 缺失静默回落纯路径→双路径逐位相同→假 PASS");compile_fail>0→退出码 1(覆盖缩水对 CI 可见,文案保留);registry `walk` 在 bool/None 分支后加 `type(a) is not type(b)`(JSON 层 35/35.0 可区分,计数类型污染不再静默)。4 个 expectedFailure 转正+3 个新正例,83 项全绿;真实探针 250 冻结假设参与性 250/250 PASS、coverage PASS、差分 PASS、5.5×加速。

**U 轮送审前盲预审与 V 轮处置**:预审员 U(flash,独立模拟 Codex 视角)审出 3 项,主对话逐项对抗复核确认真实后才派修——**U-P1-1**(主管线两处 cost_ladder 调用缺 execution_status 参数,D-01 停牌/ST 执行日资格机制在主管线为死代码;主对话 grep 零接线亲查确认);**U-P1-2**(门禁④⑤读 bt17/bt27 的 net_edge,该键为每笔精确费用、D-02 改写后不随档位变化→17/27 两档恒同值同号,27bps 压力档被静默撤销;主对话亲读键语义确认);**U-P2-1**(validate_bars 遇 10**400 级超大 int,math.isfinite 转 float 抛 OverflowError 裸崩;主对话亲测复现)。V 轮修复:U-P1-1 于 `evaluate_units`(director.py:689-692)与 `run_validation_stage`(:1237-1239)双点接线 `execution_status_from_rows`,并配管线级反例测试(validate_all→dedup→evaluation_units 全链,对照组成交 vs 入场执行日全停牌→17/27/37 三档齐 `no_fill:suspended_on_exec`、现金口径 gross=0.0、换手 0、次月恢复成交);U-P1-2 新增 `_tier_edge_for_gate`(:429)④⑤判据改读 `net_edge_proxy`,键缺失/None 时回退 `net_edge`——**回退仅覆盖旧形状手造 dict 测试档**(tests/test_factor_miner_engine.py 与 test_factor_miner_round4_fixes.py 的旧形状 dict fixture;engine.py 文件本身非不可改——D-02 轮已有 :270 断言更新),正式 cost_ladder 输出恒含 proxy 键(backtest.py:503 无条件),主管线判据不受回退影响;⑥37bps 描述字段仍读 net_edge(残留披露瑕疵,纯描述不参与晋级,已列 §4 审核点);U-P2-1 `_isfinite` 溢出安全封装(validation.py:9,OHEC :58/volume :77 两调用点,错误文案与格式不变)。amendment §5 增④⑤判据口径补释、§7 增 manifest_hash 哈希基线切换无遗留影响说明(仓库无历史锁箱消费记录)。

**TW 轮(C 组件边界审计:compiler/partition/registry)**:交付 `tests/test_factor_miner_c_components.py` 73 项(68 通过+5 AUDIT_FOUND 钉现状 expectedFailure;PYTHONHASHSEED 三种子一致;主对话复跑核实),**发现 5 个真缺陷,均只钉未修,修复方向请 Codex 裁决**:TW-1(P1 级,compiler.py:346)常量标量实参经 `_broadcast(v,_len_of(v))` 广播到长度 0——任何含字面量序列臂的公式输出空序列(`IF(SIGN(close),1,-1)`→`[]`,主对话亲测复现);**命中面实证扫描**(主对话执行,`experiments/system_audit_constarg_scan_20260911.py` 可复跑):215 条冻结公式(R0 250+R1 池)合成 bundle 真跑,**12 条命中**——R0 官方批 9 条静默清零(LIQ_impact_asym、NOMINAL_tick_illiq_gate、NOMINAL_lowpx_hotmarket_gate、UVOL_pressure_ratio/flow_stab_gap/dir_vol_shock/maxdom_asym/bucket_coupling/bigvol_purity)+R1 池 3 条(TURN_hotmom_kill_250 静默;UVOL_surrender/UVOL_flow_mkt_coupling 以长度不匹配 OperatorError 面出现,同根因)。**影响定性:假阴性方向保守**(9 结构死于缺陷而非数据,死因在 registry 误标),修复后需重算,构成 R0 重启的新输入;修复方向两案请裁:常量按轴长广播 vs 编译期拒绝常量序列臂。TW-2(compiler.py:461)CS_RANK 对缺价格股票静默全 None,与标量路径 `missing data` 异常的 fail-closed 边界不一致。TW-3(compiler.py:513)evaluate 缺省 symbols 写死 close,不兑现 docstring"首个字段的符号集"。TW-4(registry.py:83-91)load 冲突重复 factor_id 静默末者胜(与 np 探针 round-4 的重复 id 拒绝同类但路径不同)。TW-5(registry.py:59-70)validate 只查键存在,接受 factor_id=None/""。**五条裁决边界(非缺陷,测试已钉现状)**:窗口互换哈希碰撞(占位符按出现序,MEAN(close,20)-MEAN(close,60) 同哈希)、整值浮点窗口接受(RET(close,20.0)≡20)、upsert 版本内覆盖属文档化承诺(仅 load 冲突标缺陷)、partition 无数据版本概念(版本身份在 data_fields/registry 层)、常量纯公式(1+1)与 TW-1 同根因。

**DC 轮(数据普查,TRAIN-only 只读)**:B-03/B-02 两个审计开放问题获得数据答案——`experiments/data_census_20260911.py`+`docs/experiments/data-census-20260911.md`:TRAIN 窗 728 冻结会话×5,501 只为**完全面板**(共同缺行会话=0、逐会话 rows==listed、5,046 只有行股全零缺会话、455 零行股全为窗后上市新股)——B-03 的"全池共同缺行降级"路径在真实 TRAIN 数据零触发;22,629,460 单元格 inf/NaN/非正价/负量**零实例**——B-02 修复保留为边界加固、无真实命中。意外事实(仅披露):停牌存在两种编码(形态 A volume=0.0;形态 B volume/amount 空→None,1,842 行/321 只,装载后引擎按缺值断窗)。局限:仅覆盖在市股票快照(退市走 baostock)、原始层非 bundle 层、qfq/hfq 未扫。

**U2 轮(送审前二次盲预审,全新 flash 独立视角)**:**裁决 PASS,零 P1/P2,4 条 P3**。关键推演(主对话采信前抽查其依据):net/net_proxy 均以 `gross is None` 为唯一分支→两键 None 状态恒同步→回退在正式管线不可达(27bps 档不可能被复活);全仓 cost_ladder 生产调用恰两处均已接线;行号六处亲核与包声明一致。P3 处置:P3-1 基线数漂移(1468→1541)→§3 已补披露;P3-2 director.py:786 dev-smoke registry 的 `cost_ladder_net_edge_by_window` 读 `net_edge`(三档恒同值,与⑥同类残留)→列入 §4 第 10 条留裁;P3-3 backtest.py:123 `_exec_day_check` volume 非数值抛 TypeError 而非 fail-closed 理由码(上游有类型保证,实害低)→列入 §4 第 10 条留裁;P3-4 §2"不可改测试"措辞张力→已改"旧形状 dict fixture 不可改"。

**B 阶段补充测试**(审计计划 B5 要求):`tests/test_history_audit_boundaries.py` 38 项(history.py 七类边界:截断/退市/复权因子/公司行为/预热/流动性严格<t/掩码)零缺陷发现;`tests/test_trading_audit_boundaries.py` 123 项(market/account/positions/t0:最低佣金临界/保本价闭式解/手数/T+1/零现金反T/涨跌停档位/时效边界/降级路径)零缺陷发现。

## 3. 验证证据

{EVIDENCE}

**终稿全量(2026-09-11,主对话本机复跑,非代理自报)**:`python -m unittest discover -s tests` → V 轮终稿时点 **1468 项 OK(skipped=1)**;TW 边界波测试文件入树后同命令为 **1541 项 OK(skipped=1,expected failures=5**——5 项即下文 TW 段 AUDIT_FOUND 缺陷的钉现状 expectedFailure**)**。基线数随并行研究波交付的测试文件漂移,**Codex 复跑以本 commit 文件集为准**(并波在飞的 TA/DC/MT 等代理不产生 tests/ 文件,不影响)。numpy 双路径真实探针(250 冻结假设)参与性/确定性/差分全 PASS、实测加速 5.5×。

**U/V 轮验证(主对话执行)**:三项发现独立确认后才派修(grep 零接线亲查/bt 键语义亲读/OverflowError 亲测复现);V 交付后定向复跑 79 项 OK(test_validation_b02+test_factor_miner_backtest_fixes+test_factor_miner_gate_corrections);代码五处亲读(`_tier_edge_for_gate`、④⑤接线 :483/:486、TRAIN 接线 :689-692、VALIDATION 接线 :1237-1239、`_isfinite` 双调用点);backtest.py:503 无条件含 net_edge_proxy 键亲核;改动范围核查=V 恰好只动许可清单 6 文件(检出 TA/TB/DC/W4EF 各自产出,与本包无关);新测试实体亲读(全链管线反例,断言三档齐阻断+现金口径+次月恢复)。

已完成的独立复验(主对话执行,非代理自报):

- B-01:三条 Codex 反例纯路径直测 None;70 项定向测试(numpy_path/zero_variance/stats_np/cs_rank/sparse_fields)复跑 OK。
- B-02:Codex 反例(OHLC 全 +inf、volume=NaN 单行)非空错误;旧契约四项抽查保留;24+33 项复跑 OK。
- B-03:7 项新测试(含审计原场景 01-02/01-06 两行→轴含 01-03、全池缺行不压缩)复跑 OK;全 factor_miner discover 当时 OK。
- C-01/02/04:N=246 端点数值亲测与审计期望一致;NaN 输入 fail 亲测;股序不变量 50 轮三向逐位一致;67 项复跑 OK。
- D-01/02:29 项新测试+全 factor_miner 套件 OK;分母 n_hold 现金口径代码亲读核实。
- EXEC:73 项复跑 OK;两缺陷 diff 逐行复核;手数网格 150→100/250→200 手推核实。
- CHK:83 项复跑 OK;registry/stats_check/真实探针(250 单元、参与性、确定性、差分全 PASS)主对话亲跑。
- history/trading 边界:38+123 项复跑 OK,零第三方依赖确认。

## 4. 建议审核点

1. B-01:谓词两侧一致性、近常数窗边界声明的充分性、协议修订(伪值→None)的工件影响裁决(见 §6 影响矩阵);
2. C-01:N 接线(units 长度自动派生)与 LOCKBOX 独立路径的不受影响性;
3. C-03:台账原子原语(临时写+rename)在 Windows 的原子性、FAILED 不自动恢复预算的语义;
4. D-01/02:现金口径分母/递延阻开仓/未成熟月 None 三处账本语义、精确费用与 proxy 双轨的标注充分性、`tests/test_factor_miner_engine.py:270` 旧断言更新(主对话执行)的正当性;
5. EXEC-1:成交价排序的实现(每单只算一次 fill price)与 ambiguous 事件 orders 列表语义变化(委托价序→成交价序);
6. CHK:参与性 monkeypatch 的接线是否可绕过、"NOT CHECKED"分支(仅测试 mock 场景)的威胁模型边界;
7. 预登记修订草案 §1–§7 与既有预登记的一致性;**成本口径出入**:factor-mining-program-20260909 的 17bps 档构成按佣金万 1 计,现行确认股票费率万 2.5,同构成应为 20bps(见 top15-cost-breakeven §7),请裁决修订口径;
8. 三个非缺陷口径问题留裁:科创板 t0 lots 字段命名(200 股/轮 vs docstring 100 股/手)、positions 卖出无最低股数校验(事实记录器定位)、保本价恰落 tick 时档位净利可为 0;
9. engine `_add_derived_state` 的 market_vol 仍用无保护 `_std_sample`(常数窗残留路径,残差级偏差,保守披露见影响矩阵 E 节);
10. U-P1-2 回退语义(仅旧形状 dict 缺 proxy 键时回退 net_edge,U2 推演其正式管线不可达——net/net_proxy 的 None 状态恒同步)与 ⑥37bps 描述字段仍读不随档位变化的 net_edge 之残留披露瑕疵是否需一并统一口径;另两处同类残留(U2 P3-2/P3-3):director.py:786 dev-smoke registry 的 `cost_ladder_net_edge_by_window` 读 net_edge(三档恒同值)、backtest.py:123 `_exec_day_check` volume 非数值抛 TypeError 而非 fail-closed 理由码(上游有类型保证,实害低)——建议一并裁决是否统一/harden;
11. TW 五缺陷修复方向(重点 TW-1:常量按轴长广播 vs 编译期拒绝常量序列臂两案,及其 R0 九结构重算安排)与五条裁决边界(窗口互换哈希碰撞/浮点整值窗口/upsert 覆盖留痕/partition 版本身份/常量纯公式)的处置。

## 5. 纪律声明

- 本包不运行任何 `--allow-real-run` 管线;R0 维持挂起(用户指示);VALIDATION/LOCKBOX 状态不变;
- numpy 正式启用仍以其独立送审链为准;本包内 CHK 修复属于检查器自我强化,真实探针在合成数据上重跑 PASS 不构成正式运行授权;
- 工作树中他人未提交修改(quant/backtest.py、cli.py、portfolio_candidate.py 等)未被触碰、未纳入本包提交;
- 所有子代理产出经主对话对抗复验(测试独立复跑、反例亲测、diff 逐行复核)后入包;主对话自查失误(检查脚本签名/参数形状三次报错)均为自查工具错误,不影响结论。

## 6. 配套工件清单

- E 阶段影响矩阵:`docs/experiments/system-audit-impact-20260910.md`(E-0~E-7:八缺陷触发条件/调用路径/工件三档/重跑清单;PV1 与财务扩展 import 级不经过已核;r0 官方批无计算产物)
- B-01 TRAIN 定位扫描:`experiments/system_audit_b01_train_scan_20260911.py`(self-test 18/18;250/250 解析;67 因子含零方差算子、38 去重需求)——正式全市场扫描待本包 PASS 后先 `--symbols-file` 试点
- R1 候选池:`artifacts/factor-miner/r1-pool-20260911/`(随波次增量,截至本包终稿 17 文件 215 行,W4D/W4EF 已落并经主对话 validator 复跑+全库去重零碰撞复验;冻结时另出冻结清单与去重裁决),validator 全接受 0 拒,与 R0 250 条及跨批公式哈希零新增冲突(既有 5 组重复=3 组 R0 内部+2 组波内 F↔J 同构,冻结时各留一条并记录 lineage);**未冻结、未运行任何评估**
- Top15 成本口径:`docs/experiments/top15-cost-breakeven-20260911.md`(决策支持分析,非规则变更;最低佣金生效线 2 万/k=10 等值点/k=15 双边 12.5bps/`DEFAULT_TRADE_NOTIONAL=50000` 在 k≥15 失效)
- 公式空间缺口分析:`docs/experiments/r1-formula-gap-analysis-20260911.md`(403 条全量 AST 三级原型归类;算子×字段族 135 格中 44 零格;21 个空白方向全部可编译且与语料零哈希碰撞;13 条饱和警告供后续波次避撞;主对话抽查复验:三个优先缺口公式编译 OK、饱和声明属实、池 153 行确认)
- TW 边界测试:`tests/test_factor_miner_c_components.py`(compiler 31+partition 21+registry 16+AUDIT_FOUND 5;三哈希种子一致)
- 常量实参命中面扫描:`experiments/system_audit_constarg_scan_20260911.py`(自检过;12/215 命中清单见 §2 TW 段)
- 数据普查:`experiments/data_census_20260911.py`+`docs/experiments/data-census-20260911.md`+`artifacts/data-census-20260911/`(B-03 全池共同缺行零触发、B-02 inf/NaN 零实例;TRAIN-only 只读)
