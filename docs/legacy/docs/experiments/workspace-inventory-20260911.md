# 工作区盘点(2026-09-11,WX 只读盘点)

- 目的:支撑"只含系统审计修复波(ours)文件"的单一 commit 的文件选择交叉核对。
- 方法:只读。仅使用 `git status/log/diff --numstat/diff`(只读)、目录大小统计与文档内路径存在性检查;未读 data/ 与 artifacts/ 内部大文件内容,未读他人修改文件正文(仅 diff 行数汇总)。
- **活动工作区警示**:盘点期间在飞代理持续产出——两次快照间未跟踪条目从 163 增至 165(新增 `docs/experiments/data-census-20260911.md`、`docs/experiments/t0-minute-evidence-20260911.md`、`experiments/system_audit_constarg_scan_20260911.py`)。**本表为末次快照(165 untracked + 29 modified = 194 条),commit 选文件前必须重新跑 `git status --porcelain` 当场核对。**
- 盘点期间零写入、零删除、零移动(本文档除外);未触碰 .git 内部与他人文件。

---

## 1. 总览

| 顶层 | 体积 | 文件数 | 入库状态 |
|---|---|---|---|
| artifacts/ | ~21,790 MB | 133,738 | **gitignore 排除,0 个被跟踪**(政策:"数据与产物不入库") |
| data/ | ~8,193 MB | 50,628 | gitignore 排除(raw 8,171 MB / processed 35 MB / positions.json / history) |
| docs/ | ~3 MB | 118 | 部分入库(docs/experiments 87 个中约 70 未跟踪;docs/plans 27 个中 22 未跟踪) |
| experiments/ | ~5 MB | 143 | 部分入库 |
| tests/ | ~6 MB | 221 | 部分入库 |
| quant/ | ~1 MB | 44 | 入库 |
| configs/ | ~1 MB | 27 | 7 个未跟踪 |
| scripts/ | ~1 MB | 3 | build_pool.py / build_stock_pool.py / show_signal.py |
| src/ | 0 | 0 | **空目录树**(src/quant 无任何文件) |
| 根文件 | — | 3 | AGENTS.md、CHANGELOG.md、README.md(均无未提交改动) |

artifacts/ 体积大头:short-foundation 19,588 MB、pv1-precision 839 MB、family-screening 589 MB、short-target 223 MB、weekly-trade 193 MB、short-profit 124 MB、event-family 103 MB(其余均 <70 MB)。

无 staged 改动(`git diff --cached` 为空);所有改动均在工作区。

---

## 2. git 状态分类表(全量逐条,末次快照)

类别:**ours-modified / ours-untracked(可收编)/ ours-inflight(ours 波但在飞,暂不收编)/ others-modified / others-untracked / ambiguous**。

### 2.1 modified(共 29 条)

#### ours-modified(15)

| 路径 | diff(+/-) | 备注 |
|---|---|---|
| docs/decisions.md | +10/-0 | 全部为末尾追加的 D-2026-09-11-01 段,逐行核验无他人内容混入 |
| experiments/factor_miner/operators.py | — | 审计修复波 |
| experiments/factor_miner/operators_np.py | — | 审计修复波 |
| experiments/factor_miner/engine.py | — | 审计修复波 |
| experiments/factor_miner/stats.py | — | 审计修复波 |
| experiments/factor_miner/director.py | — | 审计修复波 |
| experiments/factor_miner/backtest.py | — | 审计修复波 |
| experiments/np_dualpath_diff_probe.py | +118/-4 | ours 清单内(清单写名 np_dualpath_diff_probe.py,一致) |
| experiments/np_dualpath_registry_compare.py | +9/-0 | ours 清单内(清单写名 np_registry_compare.py,**实际文件名带 dualpath 前缀**) |
| experiments/np_dualpath_stats_check.py | +68/-0 | ours 清单内(同上,实际名 np_dualpath_stats_check.py) |
| quant/validation.py | +64/-12 | B-02 等 |
| quant/execution.py | +20/-4 | 审计加固 |
| tests/test_factor_miner_engine.py | +3/-1 | ours 清单"一处修改"吻合 |
| tests/test_factor_miner_np_tools.py | +775/-0 | ours 清单列为"新测试",实为**已跟踪文件的大幅扩展**(见 §7-4) |
| tests/test_factor_miner_numpy_path.py | +10/-6 | **ours 清单未列**;diff 内容为 B-01 零方差规则修正(与 system-audit findings B-01 对应)→ 判定 ours |

#### others-modified(14,不碰不规划)

| 路径 | diff(+/-) |
|---|---|
| docs/plans/p4-factor-research.md | +1/-1 |
| experiments/p4_barrier_screen.py | +266/-38 |
| experiments/p4_factor_research.py | +102/-1 |
| experiments/p4_screen.py | +152/-89 |
| experiments/short_foundation_research.py | +15/-7 |
| quant/analysis.py | +36/-5 |
| quant/backtest.py | +5/-1 |
| quant/cli.py | +15/-2 |
| quant/portfolio_candidate.py | +158/-43 |
| tests/test_analysis.py | +50/-1 |
| tests/test_market.py | +5/-0 |
| tests/test_p4_barrier_screen.py | +177/-4 |
| tests/test_p4_screen.py | +84/-5 |
| tests/test_v3_fixes.py | +37/-1 |

注:任务 others 清单提到 `quant/market.py`,当前状态中**无**其未提交改动(见 §7-5)。

### 2.2 untracked(共 165 条)

#### ours-untracked,可收编(26,含本文档)

| 路径 | 备注 |
|---|---|
| experiments/system_audit_b01_train_scan_20260911.py | ours 清单内 |
| experiments/system_audit_bcde_probe_20260910.py | **ours 清单未明列**;审计 B~E 探针脚本,对应 docs/experiments/system-audit-bcde-probe-20260910.json 与 bcde 独立评审文档,判 ours(波内) |
| tests/test_factor_miner_zero_variance.py | ours 新测试 |
| tests/test_factor_miner_gate_corrections.py | ours 新测试 |
| tests/test_factor_miner_market_axis.py | ours 新测试 |
| tests/test_factor_miner_backtest_fixes.py | ours 新测试 |
| tests/test_factor_miner_c03_lockbox.py | ours 新测试 |
| tests/test_factor_miner_c_components.py | ours 新测试(清单列"新测试"✓) |
| tests/test_validation_b02.py | ours |
| tests/test_history_audit_boundaries.py | ours |
| tests/test_execution_audit_boundaries.py | ours |
| tests/test_trading_audit_boundaries.py | ours |
| docs/experiments/system-audit-scope-20260910.md | ours |
| docs/experiments/system-audit-findings-20260910.md | ours |
| docs/experiments/system-audit-impact-20260910.md | ours |
| docs/experiments/system-audit-conclusion-20260910.md | ours |
| docs/experiments/system-audit-fix-wave1-review-pack-20260910.md | ours |
| docs/experiments/system-audit-b01-train-scan-20260911.md | ours |
| docs/experiments/system-audit-bcde-independent-review-20260910.md | ours |
| docs/experiments/system-audit-bcde-probe-20260910.json | ours(探针工件,放在 docs/experiments 而非 artifacts) |
| docs/experiments/system-component-evaluation-20260910.md | ours |
| docs/experiments/top15-cost-breakeven-20260911.md | ours 清单内 |
| docs/experiments/r1-formula-gap-analysis-20260911.md | ours 清单内 |
| docs/experiments/workspace-inventory-20260911.md | 本文档 |
| docs/plans/factor-miner-engine-preregistration-amendment-20260910.md | ours 清单内 |
| docs/plans/system-risk-based-audit-plan-20260910.md | **ours 清单未明列**;系统审计计划文档,与 system-audit-* 同波,建议随波收编 |

#### ours-inflight(7,暂不收编)

| 路径 | 备注 |
|---|---|
| experiments/t0_minute_evidence_20260911.py | 在飞 t0 代理 |
| experiments/t0_range_calibration_20260911.py | 在飞 t0 代理 |
| experiments/data_census_20260911.py | 在飞 data-census 代理 |
| experiments/system_audit_constarg_scan_20260911.py | **盘点期间新出现**,审计扫描族新脚本,写入是否完成未确认,暂不收编 |
| docs/experiments/t0-range-calibration-20260911.md | 在飞 |
| docs/experiments/t0-minute-evidence-20260911.md | 盘点期间新出现 |
| docs/experiments/data-census-20260911.md | 盘点期间新出现 |

#### others-untracked(132,不碰不规划)

**configs/(7)**:etf-limit-pct-schedules.json、monthly-etf-t0-minute-replay-20260909.json、monthly-etf-t0-v3-review-20260909-r3.json、monthly-etf-t0-v3-review-20260909.json、p4-lowvol-h10-research.json、v3-daily-exit-20260909.json、v3-repair-20260909.json

**docs/experiments/(57)**:
- event-family-*(5):artifact-review-pack-20260910、prerun-review-pack-20260909、prerun-round2/round3-20260909、round1-20260910
- factor-miner-numpy-dual-path-independent-review-20260910(+round2/round3)(3)
- factor-miner-prerun-review-pack-20260910(+round2~round6)(6)
- family-screening-review-pack-20260910、family-screening-round1-20260910(2)
- monthly-etf-t0-*(6):conclusion/execution-protocol/independent-review/minute-probe/termination-coverage/v3-lookahead-audit(均 20260909)
- mr-statarb-*(6):artifact-review-pack、prerun-review-pack(+round2/3/4)、round1(均 20260909)
- p4-*(12):barrier-cache-acceptance-20260909、barrier-stream-20260908、barrier-stream-result-20260909、cutoff-independent-review-20260908、fullpool-pause-review-round6-20260908、lowvol-h10-conclusion/review-20260909、parallel-speed-20260908、r1-independent-acceptance-20260908、revised-round-r1-20260908、revised-selection-conclusion、round6-fix-acceptance
- pv1-precision-prerun-review-pack-20260910(+round2~round6)(6)
- tushare-first/second-pull-20260909、third-pull-20260910(3)
- v3-arm-c-mechanism-(artifact/prerun)-review-pack-20260910(2)
- v3-daily-exit-conclusion/independent-review-20260909(2)
- v3-dd-attribution-20260909(1)
- v3-repair-(artifact/prerun)-review-pack-20260909(+prerun-round2)(3)

**docs/plans/(20)**:event-family-preregistration-draft-20260909、factor-miner-blueprint-reference-20260910、factor-mining-program-20260909、family-batch-screening-preregistration-draft-20260910(+f5/f6 附录 2 份)、monthly-etf-t0-plan-20260909、mr-statarb-external-report-v1.**docx**(二进制)、mr-statarb-preregistration-draft-20260909、p4-lowvol-h10-preregistration-20260909、p4-next-hypothesis-proposal-20260909、p4-r2-etf-mixed-pool-preregistration-draft-20260909、p4-revised-round-20260908、position-sizing-plan-20260909、profit-oriented-next-steps-20260908、pv1-precision-test-preregistration-draft-20260910、v3-arm-c-mechanism-split-preregistration-draft-20260910、v3-daily-exit-preregistration-draft-20260909、v3-dd-attribution-plan-20260909、v3-repair-preregistration-draft-20260909

**experiments/(30)**:event_family.py、event_family_repro_check.py、monthly_etf_t0_minute.py、monthly_etf_t0_minute_probe.py、monthly_etf_t0_minute_replay.py、monthly_etf_t0_v3_review.py、p4_lowvol_h10.py、p4_parallel_screen.py、p4_revised_round.py、p4_stream_barrier.py、screen_forecast_reopen.py、screen_moneyflow.py、sw_l1_refresh_20260909.py、sw_l2_fetch_20260909.py、sw_verify_restore_20260909.py、tushare_fetch.py、tushare_fetch_daily_basic.py、tushare_fetch_r2_light.py、tushare_fetch_r3.py、tushare_fetch_toplist_parallel.py、tushare_probe_r3.py、tushare_probe_r3b.py、tushare_probe_r3c.py、tushare_probe_r3d.py、tushare_stmt_completion_r1.py、tushare_verify_r2_pull.py、v3_arm_c_mechanism.py、v3_daily_exit.py、v3_dd_attribution.py、v3_repair_round.py

**tests/(19)**:p4_barrier_artifact_audit.py、p4_lowvol_h10_artifact_audit.py、test_event_family.py、test_monthly_etf_t0_minute.py、test_monthly_etf_t0_minute_replay.py、test_monthly_etf_t0_v3_audit.py、test_mr_statarb.py、test_p4_lowvol_h10.py、test_p4_parallel_screen.py、test_p4_revised_round.py、test_p4_round6_acceptance.py、test_p4_stream_barrier.py、test_screen_forecast_reopen.py、test_screen_moneyflow.py、test_screen_pricevol.py、test_tushare_stmt_completion_r1.py、test_v3_arm_c_mechanism.py、test_v3_daily_exit.py、test_v3_repair_round.py

#### ambiguous(1 类)

- **artifacts/ 下全部 ours 相关新工件**:`artifacts/factor-miner/r1-pool-20260911/`(17 个研究员 jsonl,215 行)、`artifacts/audits/`、`artifacts/data-census-20260911/`(5 MB)、`artifacts/t0-range-calibration-20260911/`(16 MB)等——它们不出现在 `git status`(被 .gitignore 第 3 行 `artifacts/` 整体排除),因此"是否入 commit"不是 git add 问题而是**政策问题**:现行政策为工件不入库。若审计波要求工件入库须显式 `git add -f` 并改 .gitignore,属用户决定,本文档不规划。

---

## 3. 单一 commit 候选清单(ours 全集最佳 git add 列表)

```bash
# --- ours-modified(15) ---
git add docs/decisions.md
git add experiments/factor_miner/operators.py experiments/factor_miner/operators_np.py \
        experiments/factor_miner/engine.py experiments/factor_miner/stats.py \
        experiments/factor_miner/director.py experiments/factor_miner/backtest.py
git add experiments/np_dualpath_diff_probe.py experiments/np_dualpath_registry_compare.py \
        experiments/np_dualpath_stats_check.py
git add quant/validation.py quant/execution.py
git add tests/test_factor_miner_engine.py tests/test_factor_miner_np_tools.py \
        tests/test_factor_miner_numpy_path.py   # 清单外,但 diff 即 B-01 零方差修正,见 §7-6

# --- ours-untracked 新测试(10) ---
git add tests/test_factor_miner_zero_variance.py tests/test_factor_miner_gate_corrections.py \
        tests/test_factor_miner_market_axis.py tests/test_factor_miner_backtest_fixes.py \
        tests/test_factor_miner_c03_lockbox.py tests/test_factor_miner_c_components.py \
        tests/test_validation_b02.py tests/test_history_audit_boundaries.py \
        tests/test_execution_audit_boundaries.py tests/test_trading_audit_boundaries.py

# --- ours 探针/脚本(2) ---
git add experiments/system_audit_b01_train_scan_20260911.py \
        experiments/system_audit_bcde_probe_20260910.py   # 清单外判 ours,见 §7-7

# --- ours 文档(15,含本文档) ---
git add docs/experiments/system-audit-scope-20260910.md docs/experiments/system-audit-findings-20260910.md \
        docs/experiments/system-audit-impact-20260910.md docs/experiments/system-audit-conclusion-20260910.md \
        docs/experiments/system-audit-fix-wave1-review-pack-20260910.md \
        docs/experiments/system-audit-b01-train-scan-20260911.md \
        docs/experiments/system-audit-bcde-independent-review-20260910.md \
        docs/experiments/system-audit-bcde-probe-20260910.json \
        docs/experiments/system-component-evaluation-20260910.md \
        docs/experiments/top15-cost-breakeven-20260911.md docs/experiments/r1-formula-gap-analysis-20260911.md \
        docs/experiments/workspace-inventory-20260911.md \
        docs/plans/factor-miner-engine-preregistration-amendment-20260910.md \
        docs/plans/system-risk-based-audit-plan-20260910.md   # 清单外判 ours,见 §7-7
```

合计:modified 15 + untracked 26 = **41 个文件**(其中 3 个为清单外判定项,均已在上文标注理由)。

**暂不收编(ours-inflight,7)**:experiments/t0_minute_evidence_20260911.py、experiments/t0_range_calibration_20260911.py、experiments/data_census_20260911.py、experiments/system_audit_constarg_scan_20260911.py(盘点期间新出现)、docs/experiments/t0-range-calibration-20260911.md、docs/experiments/t0-minute-evidence-20260911.md、docs/experiments/data-census-20260911.md。到收编时点后另行入账。

**不入库(仓库政策)**:artifacts/ 全部(含 r1-pool-20260911 与审计探针产物);data/ 全部。`.gitignore:3` 为 `artifacts/`,强行入库需 `git add -f` + 政策变更,不在本 commit 范围。

**绝不 add(others,132 untracked + 14 modified)**:见 §2 others 各节。

---

## 4. 类别目录

### code
- `quant/`(44 文件,全部入库):生产与研究共用层。本次 ours 改 validation.py(B-02)、execution.py(审计加固);others 改 analysis/backtest/cli/portfolio_candidate。
- `experiments/`(143 文件):
  - factor_miner 包(17 项:`__init__/backtest/compiler/data_fields/director/engine/event_stats/operators/operators_np/partition/registry/schema/stats/stats_np/validator/prompts/`):本轮 ours 改 6 个;compiler.py 等其余 8 个无改动(最后提交 832a3c0)。
  - 双路径验证工具:np_dualpath_diff_probe / np_dualpath_registry_compare / np_dualpath_stats_check(本轮 ours 改)。
  - 审计扫描:system_audit_b01_train_scan / system_audit_bcde_probe / system_audit_constarg_scan(在飞)。
  - 既有主线(已入库):mr_statarb.py、weekly_entry/weekly_trade_research、short_foundation_research(others 改)、history/market/execution 等支撑模块。
  - 未入库的其他波脚本:30 个(others)。

### tests
- 221 文件,零第三方依赖。子群:factor_miner 系(含本轮 6 新 + 3 改)、审计边界系(validation_b02/history/execution/trading)、mr_statarb、p4 系、v3 系、monthly_etf_t0 系。本轮 ours 测试共 13 个文件(10 新 + 3 改)。

### docs
- `docs/plans/`:入库 5 + 未跟踪 22。本轮 ours 增 2(预登记修订案、审计计划);其余 20 属 mr-statarb/event-family/p4/v3/pv1/factor-miner-program 等已完结或在飞他波。含 1 个二进制 .docx。
- `docs/experiments/`:入库约 17 + 未跟踪 71。本轮 ours 增 12(9 个 system-audit + top15-cost-breakeven + r1-formula-gap + 本盘点);in-flight 3;其余 57 属其他波(含 6 份 pv1、6 份 factor-miner-prerun 送审包等,**均为从未入库的历史波审计痕迹**,见 §7-8)。
- `docs/decisions.md`:共享追加式决策日志。当前未提交 diff 仅 +10 行 = D-2026-09-11-01 段(ours),无他人段混入。
- `AGENTS.md`:无未提交改动(others 清单中列出,但当前工作区干净)。

### artifacts(全部不入库)
- 大头:short-foundation 19.6GB(历史 P1/P3 波)、pv1-precision 839MB、family-screening 589MB。
- 本轮相关:factor-miner/(2MB,含 r0-20260910、dev-smoke×2、dev-probe-out、**r1-pool-20260911/**17 个研究员 jsonl/215 行)、audits/(1MB)、t0-range-calibration-20260911/(16MB)、data-census-20260911/(5MB,+smoke 1MB+console.log)。

### configs
- 27 个,入库 20;未跟踪 7 全部属其他波(others),本轮 ours 无 configs 改动。

### data(全部不入库)
- raw 8.17GB / processed 35MB / positions.json / history。未枚举内部文件。

---

## 5. 文档↔工件交叉引用

**ours 文档引用的工件路径逐一存在性检查**:system-audit-*(9 份)、top15-cost-breakeven、r1-formula-gap 共 11 份文档中提取的全部 `artifacts/...` 具体路径均存在(factor-miner/dev-smoke×2、dev-probe-out、r0-20260910/ 及其 hypotheses/_all_raw.jsonl、r1-pool-20260911/)。3 处形如 `researcher_*.jsonl`、`f5-...`、`round-...` 的引用为文档内通配/占位写法,非真实路径,不判缺失。

**无文档引用的孤儿工件目录(仅列名)**:
- `artifacts/audits/`(1MB)——0 引用;命名推断为审计产物,但 9 份 system-audit 文档均未指向它,归属存疑。
- `artifacts/backtests/`——0 引用,历史遗留。
- `artifacts/forward_log/`——0 引用,历史遗留。
- (`artifacts/data-census-20260911/` 在盘点开始时 0 引用,盘点期间在飞代理已写出 `docs/experiments/data-census-20260911.md` 引用它——属在飞正常产出,不算孤儿。)

---

## 6. 清理候选(只列不做,绝不执行)

| 项 | 理由 |
|---|---|
| `src/`(空目录树,0 文件) | 空壳目录,无 git 影响,可删 |
| `artifacts/parse_battery.ps1` | 与量化无关的 PowerShell 脚本混在 artifacts 顶层 |
| `artifacts/data-census-20260911_console.log` | 运行日志落在 artifacts 顶层;仓库已有 logs/ 忽略政策,宜移走 |
| `artifacts/audits/`、`artifacts/backtests/`、`artifacts/forward_log/` | 0 文档引用的历史目录,可归档(确认无在飞写入后) |
| `experiments/tushare_probe_r3.py / _r3b / _r3c / _r3d` | 同一探针的 4 个连续修订版并存(others 文件,归档旧版候选) |
| `artifacts/experiments/` 下 kronos_*/timesfm_* | 旧模型实验产物(24MB),项目已转向 factor-miner 主线 |
| `scripts/build_pool.py` 与 `build_stock_pool.py` | 命名高度相似疑功能重叠(未读内容,仅命名线索) |

---

## 7. 风险与矛盾

1. **活动工作区**:盘点期间未跟踪条目 163→165(新增 data-census 文档、t0-minute-evidence 文档、system_audit_constarg_scan 脚本)。commit 前必须重新 `git status` 逐条核对 §3 清单,防止在飞文件被误收编或 ours 新文件漏收。
2. **r1-pool 文档口径漂移**:`r1-formula-gap-analysis-20260911.md` 记 "12 个文件,153 条";实际目录现含 **17 个 jsonl / 215 行**(W3A/W3B/W3C/W4D/W4EF 为文档写就后新增)。commit 前应更新该口径或加"随波次增量"注记。
3. **ours 清单文件名与实际不符**:清单写 `np_registry_compare.py`、`np_stats_check.py`,实际为 `np_dualpath_registry_compare.py`、`np_dualpath_stats_check.py`(均已按实际名收编)。
4. **"新测试"与实际状态不符**:清单将 np_tools、c_components 列为新增测试;c_components 确为新增,`tests/test_factor_miner_np_tools.py` 实为已跟踪文件的 **+775 行大改**。
5. **others 清单与状态不符**:`quant/market.py` 在 others 清单中但当前无未提交改动;`AGENTS.md` 同样不在当前 modified 列表。他人改动可能已在其会话中提交或还原——不影响本次 commit。
6. **清单外 ours 判定项(3 个,已入 §3)**:`tests/test_factor_miner_numpy_path.py`(diff 即 B-01 零方差规则修正)、`experiments/system_audit_bcde_probe_20260910.py`(bcde 探针,文档链完整)、`docs/plans/system-risk-based-audit-plan-20260910.md`(审计计划)。若主对话对其中任何一项不属于本波有异议,从 §3 剔除即可,其余互不依赖。
7. **compiler.py 无改动**:ours 清单提"compiler.py 相关测试配套",该文件本身最后修改于提交 832a3c0,本轮未动;配套测试改动落在 test_factor_miner_* 各文件。
8. **factor-miner 程序审计痕迹未入库**:约 21 份 20260910 波的预登记/送审/评审文档(prerun-review-pack×6、numpy-dual-path 评审×3、family-screening×2、pv1×6、blueprint、program、预登记草稿等)从未 commit。HEAD 之上看不到这些波的审核链,与"重大变化须有独立审查记录"的工程规则存在张力。它们不属本波 ours,但建议主对话尽早安排补录。
9. **工件不入库 vs 审计可回溯**:所有送审包引用的工件仅在本地盘(gitignore),换机即失;本波审计证据(b01-train-scan 的扫描输出、bcde 探针 JSON——后者恰好在 docs/experiments 而非 artifacts,已可入库)存放位置不一致。
10. **docs/experiments 混放机器可读工件**:`system-audit-bcde-probe-20260910.json` 是 JSON 工件却放在文档目录;与"工件入 artifacts"的分层惯例不一致(但正因如此它才可被 git 跟踪)。
11. **命名易混**:`artifacts/t0/`(旧做T扫描,20260904 起)与 `artifacts/t0-range-calibration-20260911/`(在飞新批次)并存;`docs/experiments/t0-*.md`(在飞, ours 波)与 `monthly-etf-t0-*.md`(已完结他波)前缀相近,commit 时注意区分。
12. **decisions.md 共享文件**:`docs/decisions.md` 属多人追加;本次 diff 已逐行核验仅含 D-2026-09-11-01 一段(+10 行)。commit 该文件前建议再跑一次 `git diff docs/decisions.md` 确认无新增他人段落插入同一 hunk。

---

*盘点代理 WX,2026-09-11。全程只读;本文档为唯一写入。*
