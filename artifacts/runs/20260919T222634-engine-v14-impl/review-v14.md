# 引擎 v1.4 独立复核报告（双签链第二签）

- 复核代理：独立复核子代理（与实施代理、主对话验收相互独立）。
- 复核时间：2026-09-20 00:34 – 00:44（墙钟约 10 分钟，含两次后台亲跑）。
- 性质说明：本报告为**重发首次落盘**——前次复核代理死于基础设施，无任何已落盘产出（复核开始时确认 `review-v14.md` 不存在），本次全部八项清单从零亲验，非续写。
- 复核方式：只读 + 运行验证；除本报告文件外未修改任何文件。锚 1 runner 重写了本 run `outputs/` 下的 C05 五帧与 `metrics_and_gates.json`（复核预期行为，本身即复跑验证）；源 run 目录与其他产物未触碰。

## 0. 判定

**APPROVE**。

八项清单全部 PASS；零 CRITICAL、零 MAJOR；2 条 MINOR/INFO 级发现（均不阻断，见 §10）。依据判定标准：全部 PASS 且无 CRITICAL/MAJOR → APPROVE。契约 §10.5-5 的 pin（sha256 `7ad35014d72711cb43ab6aedc232d70adf7eece60604b2a057ee039c9bd11e78`）可以执行。

## 1. 清单 1：哈希亲验 —— PASS

`sha256sum src/quant/backtest/band_engine.py` → `7ad35014d72711cb43ab6aedc232d70adf7eece60604b2a057ee039c9bd11e78`，与复核任务书给定值逐字一致（3936 行）。锚 1 runner 内建 pin（`tmp/runner_p3r2_intents.py:92` `ENGINE_SHA_EXPECT_FULL`）同为该值，运行时 `match=True`（`logs/anchor1_p3r2.log`）。复核继续。

## 2. 清单 2：全量测试亲跑 —— PASS

命令：`cd D:/量化 && ./.venv/Scripts/python.exe -m pytest tests -q`。

结果：**460 passed / 0 failed / 0 skipped**（93.51 s），与裁定记录（交付 458 + 护栏 2 = 460）一致，满足任务书 ≥457 与契约 §10.2 ≥445。6 条 warning 均为 `src/quant/research/p2r13_lowfreq.py` 的 polars join_asof 既有提示，与引擎无关，口径同交付报告。

## 3. 清单 3：锚 1 亲跑 + 逐字节比对 —— PASS

亲跑 `runner_p3r2_intents.py`（exit 0，runner 全程 119 s，引擎段 23.6 s，峰值 RSS 4.52 GB），复现判定 `VERDICT: 0/8 dev_pass`，与源 run 既判结果一致（复放忠实，非新结论）。runner 身份 pin 全部 match=True（engine/r16_config/p3r2_config/daily/split_factor/dividends/index_000300/stk_limit aggregate）。

`filecmp.cmp(shallow=False)` 逐字节比对五帧 vs `artifacts/runs/20260919T030640-p3r2-dev-ad9e/outputs/` 同名文件，并独立重算双方 sha256：

| 文件 | 结果 | sha256（前 16 位，两侧一致） |
|---|---|---|
| C05_fills.parquet | BYTE-EQUAL | 11f8af46686df411 |
| C05_events.parquet | BYTE-EQUAL | 2dde945782accd70 |
| C05_daily_equity.parquet | BYTE-EQUAL | c3945567de4250ef |
| C05_clips_final.parquet | BYTE-EQUAL | b44dbea22a529529 |
| C05_intents.parquet | BYTE-EQUAL | 36dedda1cf8d7661 |

重写范围核验：本次 runner 只重写 C05 五帧 + `metrics_and_gates.json`（mtime 00:36:37）；主对话裁后重验写入的锚 2/锚 3 产物（00:18/00:20）未被触碰。`metrics_and_gates.json` 不比对的原因（含本次复放的引擎 sha 与计时、C05 单配置范围）已在 manifest 注明，五帧等价覆盖行为面。

## 4. 清单 4：零回归结构论证 —— PASS

通读 `band_engine.py` 全文（3936 行），逐处追踪 v1.4 新代码路径：

1. **入口与校验**：`zones`/`zone_priority_base` 为 keyword-only 新参（1665-1682）；`assert_frozen(zones...)` 仅 zones 非 None（1743-1744）；`_validate_zones` 仅 `zone_engine` 时调用（2032-2033）；zones+signals 互斥 raise（1719-1722）。不传 zones 时全部短路。
2. **zone-stop 段插入位置**：`process_session` 顶部 `if zone_engine: zone_stop_segment(day, sess)`（3172-3175），位于既有 A 段（3180 起）之前。`zone_stop_segment`（2406-2483）只遍历 `ZONE_BY_SYM`（zones 模式之外为空 dict），非 zones 零操作。既有 A（3180-3284）→ B（3286-3378）→ C（3380-3485）→ D（3487-3492）段代码顺序未移动；v1.4 在段内仅以 `if zone_engine:` 插入三个 hook：A 段 cap-void 后 `zone_ladder_cap_void`（3277-3280）、B 段兜底成交后 `stop_armed_resolved_fallback` 计数（3371-3377）、C 段 profit 静默过期后 `tp_expired_sessions` 计数（3482-3484）。BR-6 声明的"语义次序表"把 B 段列在 zone-stop 之前，代码实际顺序为 zone-stop→A→B→C——两者作用于不相交 symbol 集（zone-stop 只筛 `phase=="holding"`，armed 属 exiting zone；`zone_stop_segment` 2413-2416 的筛选条件），任务书 BR-6 同时明确"不得移动既有段代码顺序本身"，故此为文档表述与代码顺序的有裁定背书的字面差异，非缺陷（见 §10-1）。
3. **决策点挂接**：`zone_step` 挂在两个决策点（3639、3649），首行 `if not zone_engine or not ZONE_MONTHS: return`（2490-2491）零回归门控。
4. **stats 键**：`stats["zones"]` 仅 `zone_engine` 时写入（3848-3893）；`stats_acc` 初始化（2594-2614）无 v1.4 新键；引擎收尾的 stuck 计数块同样 `if zone_engine` 门控（3689-3699）。`engine_version` 全局标签 v1.3→v1.4（3720），属锚协议允许的唯一差异。
5. **BandResult.zones**：缺省 None（691），仅 zones 模式构造 zones 帧（3847、3912、3935）。非 zones 模式对象形状与 v1.3 等价（新增字段有默认值）。
6. **WAC 公司行动镜像**：v0 送转路径（3534-3535）与 v1.3 份额变换路径（3610-3617）两处均为 `if zone_engine` + zone 存在性双重门控。
7. **既有 tests 零改动的佐证**：`tests/` 目录 mtime 排查——除 v14 新测试文件（00:14，护栏 t28/t29 加入时刻）外，全部既有测试文件 mtime 早于实施窗口开始（22:26）：test_band_contract.py 09-18 23:39、v13 corporate_actions 09-19 13:50、hybrid 09-19 05:17、intents 09-19 02:16、factors_eval 09-19 16:59。
8. **行为面证据**：460 测试中 432 项为基线（v1.3）测试，全过；锚 1 五帧逐字节复现（§3）。

结论：全部 v1.4 新路径以 `zone_engine` 门控，不传 zones 时零执行、零新 stats 键、既有段顺序未动。

## 5. 清单 5：语义抽核（八项，逐条对照代码）—— PASS

| # | 语义项 | 代码位置 | 结论 |
|---|---|---|---|
| 1 | 阶梯总量 `floor(w_t×snap/p0/LOT)×LOT`（snap=信号日 pm 决策快照，补位同锚 S-v14-10）；逐档 `floor(frac×total/LOT)×LOT`、<LOT 丢档计数 | `_zone_admit` 2100-2119（`decision_snapshots.get((signal_date,"pm"))` 2239；快照缺失 raise 2248-2252） | 一致 |
| 2 | 每决策点按**剩余股数**重挂（`rem=target−filled`），限价 = 决策锚 − offset×σ0，锚走 intent_anchor（am=am.close、pm=官方收盘）；锚缺失不挂（m3） | `_zone_hang` 2311-2329；`intent_anchor` 3035-3046 | 一致 |
| 3 | 失效线在决策点检查**刚结束 session** 的 low < p0−invalid_mult×σ0 → 取消未成交档；该 session 成交优先（挂单在本 session A 段先执行，失效判定在其后的决策点） | `zone_step` (c) 2526-2552 | 一致 |
| 4 | TP：目标 = WAC+mult×σ0；b1 = `floor(frac×总持股/LOT)×LOT`、floor<100 不挂并计数；b2 shares=None 全卖可卖；profit 无 k3、到期静默计数 | `_zone_hang` 2330-2357（WAC=buy_amount/buy_shares_wac 2331）；C 段 3442-3485 | 一致 |
| 5 | 止损：HWM = 首笔成交后每决策点决策锚最大值（锚缺失冻结）；线 = max(历史线, HWM−mult×σ0) 只升不降（跨月 σ0 刷新经 max）；触发按 min(线， 开盘)；T+1 残部武装既有 B 段兜底（source="stop:<sd>"） | (e) 2559-2571；`zone_stop_segment` 2418-2481；B 段 3288-3378 | 一致 |
| 6 | 同 session 止损先于止盈与买单：zone-stop 段在 A 段之前，触发即从 live 列表移除同名义 zladder/ztp 单 | 3172-3175 + 2427-2434（t11 实证） | 一致 |
| 7 | 席位扫描：held=总股数>0 的 zone（含 exiting/exiting_boundary 残部）、inflight=entering；行业计数=held∪inflight；跳过当月已有 zone（含冷却/done，MONTH_SYMBOLS）与行业已满；(held+inflight)<K 沿 rank 升序准入 | `_zone_scan` 2219-2256；`_zone_admit` 2098 | 一致 |
| 8 | 月边界（(signal_date,"pm")）：次序 = ladder expiry 先于边界（S-v14-13 同点次序）→ cooling→done → 逐 zone 退出（exiting_boundary，rank 用旧月值不重参数化）/续持刷新（WAC 不变、止损线经 max、旧阶梯终止不重发）→ 席位补位 | `zone_step` (a)→(d)→(e)→(f) 2494-2576；`_zone_boundary` 2176-2217；`_zone_continue` 2141-2174 | 一致 |

附加核对（裁定接缝的代码落实）：S-v14-9 席位含残部（2229-2236）；S-v14-14 续持旧阶梯"同名义覆盖"终止、tier_expired 计数、不重发（2149-2152）；S-v14-16 exiting 区不重参数化（2190-2193）；S-v14-17 MONTH_SYMBOLS 每月每符号一次（2098、2166-2167、2244）；S-v14-20 zone 武装不增 `k3_fallback.armed`（2471-2477 直接置 risk_state，不调 bump_streak）、B 段兜底成交仍计 k3_executed（2967-2968）；S-v14-21 最后决策点 live_d=None 不准入（2575）但 expiry 照常（2499）；S-v14-22 stop 成交计 orders_filled.sell_risk（2990-2993 按 intent 分桶）、不计 orders.sell_risk（该计数在 C 段 3385）、fill_type="stop" 不计 k3_executed（2967 仅 market_fallback）。

## 6. 清单 6：主对话两条护栏复核 —— PASS

- **S-v14-12（分数 tp2_frac raise）**：`_validate_zones` 内 `abs(tp2_frac−1.0) > 1e-9 → BandContractError`（band_engine.py 1303-1312），fail-closed（校验发生在任何模拟交易之前，2033 行调用点），错误消息写明"tp2 is the full-clear tier"。测试 t28（test_band_engine_v14_zones.py 1094-1110）：`tp2_frac=0.7` raise + `tp2_frac=1.0` 正常准入，两侧真实覆盖。
- **S-v14-15（zone/intent 符号重叠 raise）**：zones 激活时，zone 符号集合 ∩ intent 符号集合 ≠ ∅ → BandContractError（2036-2047），fail-closed。测试 t29（1113-1140）：重叠 raise + 不相交（zones=B、intent=A）正常同账本组合，两侧真实覆盖。t24 正向用例已改为不相交符号（985-1016，注释写明原同符号写法早于该裁定）。
- 两条护栏随引擎进 sha `7ad35014…`，全量 460 通过（§2），锚 1 复现（§3）证明护栏未影响零回归路径。

## 7. 清单 7：测试诚实性（独立重推）—— PASS

从测试文件内联的合成面板数据**独立重推**以下场景至分（不依赖测试注释结论），全部与断言一致：

1. **t01（阶梯序/WAC/现金）**：(D1,pm) 快照 200000 → total=floor(0.05×200000/10/100)×100=1000 → 档 400/400/200。(D1,pm) 锚=官方收盘 10.0 → a1=9.5 live D2am；D2am low 9.2<9.5 → 400@9.5。(D2,am) 锚=am.close 9.3 → a2=7.8 live D2pm；D2pm low 7.6 → 400@7.8。(D2,pm) 锚=8.0 → a3=5.5 live D3am；D3am low 5.4 → 200@5.5。现金 200000−3805−3125−1105=**191965.00**；WAC=(3800+3120+1100)/1000=**8.02**。与断言逐分一致；fills 的 decision/session/date 路由（pm→次 am、am→当日 pm）与断言一致。
2. **t09（跳空止损现金）**：(D2,pm) 决策点 HWM=max(9.3, 官方收盘 10.5)=10.5 → 线=max(6.3, 7.5)=7.5。D3am open 7.0、low 6.9<7.5 → 触发，成交价=min(7.5, 7.0)=**7.0**（非线价）；400 股（D2 取得）全可卖 → 全清 cooling、零武装。net=2800−5−1.4=2793.60 → 现金 200000−3805+2793.60=**198988.60**。一致。
3. **t15（月边界现金）**：(F1,pm)=月边界决策点：(a) 两 zone 的 live_d=F2=2024-02-02 ≥ expiry（SD2+1）→ tier_expired 计 A 2+C 2；(d) A rank5>2×2 → exiting_boundary（rank 保持月 1 的 1，risk 卖 priority=10^6+**1**、锚=F1 官方收盘 9.3）；C rank1≤4 → 续持（σ0=2、WAC 4.5 不变、线=max(1.9, 4.9−6)→1.9 不降）。F2am risk 卖成交 400@9.3 → net=3720−5−1.86=3713.14；A 全清→done(boundary_cleared)；(F2,am) 补位 B：snap=decision_snapshots[(SD2,"pm")]=192590+400×9.3+800×4.9=200230 → total=floor(0.05×200230/10/100)×100=1000；B a1=(F2,pm) 锚 9.2−0.5=8.7 live F3am 成交 400@8.7（成本 3485）。现金 200000−3805(A a1)−3605(C a1)+3713.14−3485=**192818.14**；tier_expired=2+2+B 2(数据结束)=**6**。逐分一致。
4. **t16（m7 现金竞争）**：cash 105000、w_t=0.28 → 每名 total=2900、档 1100/1100/500（a1/a2/a3 需求 10455/9355/3755）。A 段按 (priority=1000+rank, symbol)：rank1-4 全额 4×23565=94260；rank5 a1 需 10455 ≤ 余 10740 → 成交；a2/a3 insufficient_cash void（计数 2）。末现金 105000−94260−10455=**285**；成交 13 笔、rank5 最后入账；rank5 未成交 2 档在数据结束日经 live_d=None 路径 tier_expired=**2**。逐分一致。

另核 t12（止损清仓→同决策点补位，现金 194803.74=200000−3805+2513.74−3905）与 t20（部分可卖止损+T+1 残部兜底，现金 197931.91=200000−8235+2513.74+3653.17），均一致。断言无 xfail/skip（全量 0 skipped）；现金断言容差 1e-6（到分）、价格断言 1e-9；未见"为通过而削弱"的断言——所有期望值均从面板数据可独立推导。

## 8. 清单 8：接缝裁定完备性 —— PASS

交付报告 §四共 **16 条候选**（BR-11(a)-(e) 5 条 + 实施中新发现 S-7..S-17 11 条），与 `adjudication-v14.md` 裁定表 S-v14-7..22（16 条，编号连续无缺）逐条对应：

| 交付候选 | 终号 | 交付候选 | 终号 |
|---|---|---|---|
| BR-11(a) 触发即终止 | S-v14-7 | S-7 expiry/边界同点次序 | S-v14-13 |
| BR-11(b) WAC 生命周期 | S-v14-8 | S-8 续持同名义覆盖 | S-v14-14 |
| BR-11(c) 席位含残部 | S-v14-9 | S-9 退出区不重参数化 | S-v14-16 |
| BR-11(d) 补位锚信号日快照 | S-v14-10 | S-10 MONTH_SYMBOLS | S-v14-17 |
| BR-11(e) 优先级基座分离 | S-v14-11 | S-11 signal_date 日历校验 | S-v14-18 |
| | | S-12 tp2_frac 解耦 | S-v14-12（护栏） |
| | | S-13 tp_below_min_lot 键 | S-v14-19 |
| | | S-14 武装不经 k3 块 | S-v14-20 |
| | | S-15 zone WAC 只归集 zladder | S-v14-15（护栏） |
| | | S-16 数据结束不准入 | S-v14-21 |
| | | S-17 stop 统计不对称 | S-v14-22 |

编号一致、无遗漏、无静默取舍；S-v14-1..6 为契约 §10.6 设计期预登记，不在交付候选内，无冲突。BR-11(a)-(e) 五项在交付报告 §四"BR-11 预披露接缝"逐条落档、裁定表逐条对应。manifest 含 `post_adjudication` 块（裁后 sha、460 测试、三锚重验）。全部 16 条裁定的代码落实已在 §5 附加核对逐条验证。

## 9. 复核覆盖范围与限制（如实声明）

- 亲验：sha256、全量测试、锚 1 复跑 + 五帧 filecmp/sha256、引擎 3936 行与测试 1140 行通读、八项语义抽核、两条护栏、四个半场景手算重推、16 条接缝映射、runner pin 与日志 pin、tests/ mtime。
- 未亲验（依赖交付链记录，风险已由其他证据覆盖）：锚 2（H2-A0）与锚 3（F3R3-A0）本次未重跑（不在复核清单内）；其裁后重验记录在 manifest `post_adjudication` 与 `logs/anchor2_hybrid.log`/`anchor3_f3r3.log` 的 pin 行中（本次抽查了日志 pin 段，match=True），其 stats 归一化比对未独立重做——锚 1 五帧逐字节复现已覆盖零回归的核心行为面。
- 本复核不构成盈利或绩效判断；三锚 VERDICT（0/8 等）为源 runner 既判结果的忠实复放。

## 10. 发现分级列表

无 CRITICAL、无 MAJOR。以下两条不阻断：

1. **INFO**：任务书 BR-6 的 zones 模式"语义次序表"（B 段兜底列在 zone-stop 之前）与代码实际顺序（zone-stop→A→B→C→D，B 段仍在 A 后）字面不一致。两段作用于不相交 symbol 集（`zone_stop_segment` 2413-2416 仅筛 `phase=="holding"`，armed 属 exiting zone），任务书同段明确"不得移动既有段代码顺序本身"，语义等价、有裁定背书。建议未来版本在 BR-6 文本处补一句"B 段与 zone-stop 段代码序以实现为准（不相交集，次序无关）"，避免下轮复核重复排查。
2. **MINOR（测试卫生）**：`tests/test_band_engine_v14_zones.py:976-978`（t23 内）`half` 被连续赋值两次，第一次构造（含 `A+'_x'` 空列表项）立即被第二次覆盖，为死语句，无语义影响。可在下次触碰该文件时顺手清理。

## 11. 复核结论

引擎 v1.4（sha256 `7ad35014d72711cb43ab6aedc232d70adf7eece60604b2a057ee039c9bd11e78`）通过独立复核：语义与契约 §10/§7 及 BR-1..BR-12 一致，两条 fail-closed 护栏真实有效，零回归有结构论证 + 432 基线测试 + 锚 1 逐字节复现三重证据，测试手算诚实，接缝裁定完备。

**APPROVE**。可执行 §10.5-5 的 pin 步骤；pin 后按 §10.0 门控解禁后续流程。
