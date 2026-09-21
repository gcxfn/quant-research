# 方案B：引擎计算路径 numpy 双路径 — Codex 运行前审核送审包

- **送审日期**：2026-09-10（深夜）；**round-2 修订**：同日（Codex 第1轮 CHANGES_REQUESTED 后，见 §10）
- **决策依据**：D-2026-09-10-34（用户指示"现在做，马上"立项；纪律修订=计算路径 opt-in numpy + 全功能回落 + 离线零依赖测试不破）
- **送审请求**：审核本变更包。**PASS 前任何正式运行（pipeline / validation / lockbox，含 TRAIN）禁用 `FACTOR_MINER_NUMPY`**；PASS 后请求授权：用 numpy 路径重跑 R0 TRAIN 作新基线（全新批次目录），并与正在运行的纯 Python R0 批（HEAD 7b2f530 启动）做全量门禁判定对照；VALIDATION/LOCKBOX 解锁状态不变。
- **审核基线**：本包随代码同 commit 提交（commit hash 见 §8），受审文件全集经 `audited_code_paths()` 自动纳入新文件（`experiments/factor_miner/*.py` 目录 glob + `tests/test_factor_miner*.py`）。
- **round-2 摘要**：P1（常数窗口 ZSCORE 零方差边界 None↔值翻转）以**求和同序化**修复——`_seq_sum` 沿窗口轴 cumsum 与 Python `sum(win)` 舍入路径逐位一致，纯路径浮点运气行为被逐位复刻；P2（探针换位豁免 + 确定性误用容差）两处假 PASS 机制删除。验证货币定稿：掩码/边界严格逐位、有限数值 1e-12 容差零豁免（残差唯一来源=平台 libm pow，实证见 §10.3）。全证据链重跑：1075 项全仓绿、250 公式 PASS、真实数据 12 单元零分歧。**§2/§3/§4 中与 round-2 冲突的旧表述以 §10 为准。**
- **round-3 摘要（当前版，提交 {COMMIT}）**：Codex round-2 两条 P2（探针确定性仅改文案未改机制；registry 整数计数/bootstrap 未严格比较）修复——`compare_strict` 真严格分支接入确定性循环；registry 三层协议（整数精确/bootstrap 子树严格/其余浮点容差）；**10 项负例测试按 Codex 自给反例固化**（5e-13 确定性漂移→退出码 1；bootstrap 5e-13→FAIL；10**12 计数漂移→检出）。真实探针与 registry 复验 PASS。**§11 为本轮权威。**

## 1. 变更清单

| 文件 | 状态 | 行数 | 内容 |
|---|---|---|---|
| `experiments/factor_miner/operators_np.py` | 新增 | 642 | 17 算子 numpy 等价实现：端到端数组管线、精确 inf 语义、字段级缓存、CS_RANK 整轴缓存 |
| `experiments/factor_miner/stats_np.py` | 新增 | 155 | `spearman_np` + `ic_decay_curve_np`（单元耗时 60~70% 所在热路径） |
| `experiments/factor_miner/stats.py` | 修改 | +~20 | `spearman`/`ic_decay_curve` 入口薄分派（env 非空且 numpy 可导入才走 stats_np，import 失败静默回落） |
| `experiments/factor_miner/compiler.py` | 修改 | +32 | `evaluate()` 分派 + `clear_cs_rank_cache` 追加 numpy 缓存清理（v1 轮引入，本轮未再改） |
| `tests/test_factor_miner_numpy_path.py` | 新增 | 528 | 32 项：逐算子脏边界、inf 精确性专项、随机容差、整数精确、端到端脏 bundle、缓存边界、确定性 |
| `tests/test_factor_miner_stats_np.py` | 新增 | 207 | 11 项：spearman 等价、衰减曲线分派等价、bootstrap RNG 身份保护 |
| `experiments/np_dualpath_diff_probe.py` | 新增 | ~230 | 主对话差分探针（250 冻结公式 × 合成脏数据双路径对比） |
| `experiments/np_dualpath_stats_check.py` | 新增 | ~100 | 统计层专项差分 |
| `experiments/np_dualpath_registry_compare.py` | 新增 | ~90 | dev-smoke 双环境 registry 深比较 |
| `experiments/np_dualpath_rank_diag.py` | 新增 | ~90 | v1 调查期秩分歧聚焦诊断（留档） |
| `docs/decisions.md` | 修改 | +12 | D-34 全链（立项→v1 发现→v2 规格→v2 证据） |

**一行未动**：`operators.py`（语义基准）、`director.py`、`engine.py`、`backtest.py`、`registry.py`、`partition.py`、`validator.py`、`schema.py`、预登记文档。默认路径（不设环境变量）行为与 HEAD~ 完全一致（分派在 env 检查后才可能 import numpy）。

## 2. 设计规格（冻结，D-34）

### 2.1 双路径与回落
- 环境变量 `FACTOR_MINER_NUMPY` 非空且 `import numpy` 成功 → numpy 路径；否则纯路径。三层回落安全：env 未设（短路，零开销）/ env 设但 numpy 缺（try-except 静默）/ `operators_np` 自身 import 失败（回落）。
- numpy 全部惰性 import（模块顶层无 numpy）；离线零第三方依赖测试纪律不破（相关测试 `skipIf` 无 numpy）。

### 2.2 端到端数组管线
- v1 教训（已入 D-34）：每算子边界 list↔数组逐元素转换实测 0.6×（负加速）。v2：`_field_np` 字段入口转换一次（bundle 属性 `_fm_np_field_cache`，**bundle 生命周期**，不随单元清理——原始字段与单元无关）→ 中间全程 ndarray/标量 → `evaluate()` 出口每 symbol 一次 `_from_np`。
- `clear_caches(bundle)` 只清 CS_RANK 两个缓存（series_map / 逐日排名），**不清字段缓存**（docstring 写明区别）；`compiler.clear_cs_rank_cache` 同时清理纯路径与 numpy 路径缓存。

### 2.3 精确 inf 语义（数据域 = {None, 有限数, ±inf}）
- `_to_np`：None→NaN，**±inf 原样保留**；`_from_np`：**只把 NaN→None，±inf 原样输出**。
- 逐算子掩码与 `operators.py` 的 `_finite` 口径精确对齐：
  - 滚动窗（MEAN/SUM/MAX/MIN/STD/ZSCORE/TS_RANK）：窗内任一非有限（NaN 或 ±inf）→ 该日 None（`np.isfinite(w).all(axis=1)`）；min_periods=全窗；STD ddof=1 且 n=1 全 None；ZSCORE std==0 掩码；TS_RANK 精确整数计数（含并列 ≤）。
  - ABS：`np.where(isfinite, abs, arr)`——**非有限直通**（±inf 原样、None→None），复刻纯路径 `v if not _finite(v) else abs(v)`（含 ABS(−inf)=−inf）。
  - neg：`−arr` 直通（−inf→+inf）。
  - IF：cond 非有限 → None（**numpy 的 NaN≠0 为 True 陷阱已掩码**）；选中分支值**原样透传含 ±inf**。
  - arith：任一侧非有限 → None；除法分母==0（含 −0.0）→ None 显式掩码（numpy 除零给 inf）；**有限输入溢出产生的 ±inf 保留输出**（与纯路径一致）。
  - LOG：非有限或 ≤0 → None；SIGN：非有限 → None；RET：两侧有限且 base≠0；DELTA：两侧有限；CORR：双窗全有限 + sxx>0 + syy>0。
  - CS_RANK：参与=仅有限值；并列平均秩（1-based）/参与数 ∈ (0,1]；±inf 与 NaN 同样不参与；ragged 序列 close 轴长度回退语义逐字复刻 `compiler._eval_cs_rank`（含 length>D 超出日期输出 None，有反例测试）。

### 2.4 stats_np 范围与 RNG 身份隔离
- 仅加速 `spearman` 与 `ic_decay_curve`（后者占单元耗时 60~70%：6 水平 × 972 日逐日截面 Spearman）。
- **配对掩码精确复刻纯路径**：`spearman_np` 用 `(x==x) & (y==y)`（只剔 NaN，**±inf 参与排名**——秩为有限值，Pearson 不受影响）= 纯路径 `a is not None and a == a`；`ic_decay_curve_np` 前向收益掩码 `(c0>0) & (c1>0)` = 纯路径 `c0 and c1 and c0>0 and c1>0` 的数组等价（NaN/0/−inf 剔除、+inf 保留；inf/inf→NaN 由 spearman 的 NaN 剔除兜底，与纯路径一致）。
- **绝不 numpy 化**：`monthly_block_bootstrap`、`continuous_gate`、`forward_returns`、`avg_ranks`、`decile_top_bottom_spread`——bootstrap 的 random 消费序列与种子身份必须逐位不变；`monthly_rank_ic_series` 经 `rank_ic_cross_section→spearman` 分派自动受益，本身不改。
- 并列平均秩：稳定 argsort + 游程（同 `operators.cs_rank` 内环语义），排序并列不影响平均秩值。

## 3. 等价性验证协议（D-34 冻结的"验证货币"）

求和顺序（Python 顺序 vs numpy pairwise）使逐位一致不可达，验证货币为：
1. **None/±inf 位置逐位相同**（掩码模式零白名单）；
2. 有限数值 `math.isclose(rel_tol=1e-12, abs_tol=1e-12)`；
3. **门禁判定（gate 布尔）逐单元相同**、n 计数精确相同、bootstrap 输出逐位相同；
4. 确定性：同路径双跑逐位一致。

## 4. 证据链（主对话独立执行，全部可复现，命令见 §8）

### 4.1 单元测试
- `tests.test_factor_miner_numpy_path` + `tests.test_factor_miner_stats_np` → **43 tests OK**（主对话独立复跑）。
- 全仓 `python -m unittest discover -s tests` → **Ran 1072 tests, OK (skipped=1)**（主对话独立复跑 181.7s；skip 为既有本地数据缺失项）。

### 4.2 全量公式差分（合成脏数据，零白名单）
`python experiments/np_dualpath_diff_probe.py`：250 个 R0 冻结公式（`_all_raw.jsonl` 全量）× 合成 bundle（26 字段、120 股、ragged 长度 880~972、None 8%/±inf 0.5%/零 3%/并列密集/常数段零方差/非价格字段稀疏覆盖/末股无 close 触发 fail-closed）：
- **232 计算单元：None 掩码逐位相同 + 数值 ≤1e-12（worst 1.39e-12 通过）**；
- **18 单元：双路径抛出完全相同的 CompileError**（无 close 股票的 PRICE 缺失 fail-closed 路径）；
- 确定性（numpy 双跑含 None 掩码逐位）：PASS；
- 性能：**7.7×~8.6×**（120 股规模；热身后 ~9.5×）。
- 迭代留痕：v1 曾有 3 个 inf 透传分歧单元与 0.6× 负加速（D-34 已档）；修正数据几何（同股票字段共享长度，对齐真实 bundle 语义）后 v2 零白名单通过。`experiments/np_dualpath_rank_diag.py` 为当时聚焦诊断脚本。

### 4.3 统计层专项差分
`python experiments/np_dualpath_stats_check.py`：40 股 × 300 日脏数据（含 ±inf 11.5%、零、并列、常数段零方差、逐日随机 pool 掩码 80%）：
- `spearman` 双路径：PASS（容差内）；
- `ic_decay_curve` pool/nopool 两配置 × 6 水平：n 精确相同、mean_ic 容差内：PASS；
- **bootstrap 同输入在环境变量开/关两次调用逐位一致**（RNG 身份未被分派触及）：PASS。

### 4.4 真实数据全管线差分（最强证据）
dev-smoke 通道（TRAIN-only、60 只真实股票、12 个家族覆盖单元——含 LHB/margin/pxval 的 CS_RANK 单元、REV/STATE/VAL 滚动单元、及 v1 期合成分歧过的 `META_margin_10`、`REV_liq_cs_turnz_loser`）双环境各跑一次：
- 纯：`out_dir=.../np_real_diff/pure/dev-smoke/20260910_215721`（41.4s）
- numpy：`.../np_real_diff/numpy/dev-smoke/20260910_215814`（38.2s；60 股时墙钟由建包主导）
- `python experiments/np_dualpath_registry_compare.py` 深比较两份 registry.jsonl（身份字段除外全字段递归：gate 布尔、月度 IC 序列、衰减曲线、成本阶梯净边际）：**12 factors, diffs: 0, VERDICT PASS**。

### 4.5 回落模拟
`sys.modules['numpy']=None` + env=1：分派返回 None 回落纯路径，求值结果正确（PASS）。

## 5. 主对话复验中的亲手修正（如实披露）

1. **stats_np 掩码语义**：v2 代理按送审规格用 `isfinite` 配对，但纯路径 `spearman` 是 `a==a`（±inf 参与排名）、`ic_decay` 前向是 `c0>0`（+inf 保留）——**规格系主对话笔误**，已按纯路径精确语义改正（§2.4）。教训已入 D-34：差分以纯路径为唯一基准，不信任人写的规格。
2. `_series_matrix`/`_pool_matrix` 由逐元素 Python 双循环改为逐行构造（原实现每单元多付 6~10s）。
3. `_delta_arr` 对将被掩码丢弃的无效位（inf−inf）补 `errstate` 抑制告警（纯语义无影响）。

## 6. 已知边界与限制（如实声明）

- **数值容差非逐位**：求和顺序差异 → 1e-12 相对容差。理论后果：近并列值（差距 <1e-12）在两路径下的秩可能相差一步（离散化）。合成差分与真实数据差分均零命中；全量门禁对照（PASS 后 numpy 重跑 vs 纯 Python R0 工件）将给出 250 单元实证。
- **字段缓存内存**：numpy 启用时每 (field,symbol) 持一份 float64 数组（R0 全量 26 字段 × 5,552 股 × 972 日 ≈ 1.1GB），与纯 list 数据并存，numpy 正式批峰值内存估计 6.5~7GB（15.6GB 机器可行；纯 Python R0 与 numpy 批不得并发）。
- **矩阵级全市场向量化未做**（v3 可选）：当前逐 symbol 数组，全量加速比待正式批实测（合成规模 7.7~9.5×；60 股真实端到端受建包主导）。
- `evaluate` 的 symbols 缺省语义两侧一致（`sorted(set(bundle.data.get("close", {})))`），director 调用显式传参不受影响。
- dev-smoke 双跑的 registry `code_identity` 字段必然不同（本包自身在受审文件内），深比较已按身份字段豁免——这是预期差异，非等价性破口。

## 7. 建议审核点

1. §2.3 逐算子掩码与 `operators.py` 逐行对照（重点：IF 的 cond 掩码、arith 除零含 −0.0、ABS 非有限直通、溢出保留）；
2. §2.4 掩码数组等价性证明（`a==a` vs `(x==x)&(y==y)`；`c0 and c1 and c0>0 and c1>0` vs `(c0>0)&(c1>0)`）；
3. RNG 身份：`stats.py` 分派是否可能间接改变 `monthly_block_bootstrap`/`continuous_gate` 的 random 消费序列（含 `spearman` 分派对 `monthly_rank_ic_series` 的传导）；
4. 缓存生命周期：字段缓存（bundle 级）与 CS 缓存（单元级）的清理边界、跨单元内存不变式；
5. 回落完备性（env 未设 / numpy 缺失 / import 中途失败三档）与"默认路径零改动"声明核实；
6. `np_dualpath_diff_probe.py` 的合成数据是否足以覆盖剩余风险，或需补充哪些反例。

## 8. 复现命令（全部在 commit 后的工作树执行）

```bash
python -m unittest tests.test_factor_miner_numpy_path tests.test_factor_miner_stats_np -v
python -m unittest discover -s tests
python experiments/np_dualpath_diff_probe.py            # ~2分钟
python experiments/np_dualpath_stats_check.py           # 秒级
# 真实数据双跑（各约 40~60 秒,输出目录时间戳各异）:
python experiments/factor_miner/director.py dev-smoke-train \
  --hypotheses <12单元假设文件> --symbols <60股逗号清单> --out-root <目录A>
FACTOR_MINER_NUMPY=1 python experiments/factor_miner/director.py dev-smoke-train \
  --hypotheses <同上> --symbols <同上> --out-root <目录B>
python experiments/np_dualpath_registry_compare.py <目录A>/dev-smoke/<ts>/registry.jsonl <目录B>/dev-smoke/<ts>/registry.jsonl
```
（本包证据所用 12 单元假设文件与 60 股清单：`C:\Users\ASUS\.zcode\cli\exec\dev_smoke_hyps.jsonl` 与 `dev_smoke_syms.txt`，内容为 R0 冻结清单子集，可从 `_all_raw.jsonl` 按 id 复制重建。）

## 9. 纪律声明

- `REAL_RUN_UNLOCKED=True` 授权边界不变（R0 TRAIN-only；VALIDATION/LOCKBOX 未解锁）；本包不翻转任何解锁状态。
- 正在运行的纯 Python R0（PID 31976，HEAD 7b2f530 启动，全新批次目录）不受本包影响（其身份快照于启动时）；其工件将作为 PASS 后 numpy 重跑的全量门禁对照基准。
- 本包未运行任何 `--allow-real-run` 管线；dev-smoke 为 DEV_SMOKE 通道（TRAIN-only、只写 dev-smoke 输出、不触 REAL_RUN_UNLOCKED）。
- 任何正式运行使用 numpy 路径，以本包 **Codex PASS** 为前提（D-34 冻结）。

## 10. round-2：Codex 第1轮 CHANGES_REQUESTED 的处置

### 10.1 P1（数值语义分歧）——修复：求和同序化

**Codex 反例**：常数窗口 `[1.1]*20` 的 ZSCORE，纯路径 None、numpy 路径 −0.9747；冻结复合公式无信号变有信号。

**根因**：numpy `pairwise` 归约（`.sum(axis=1)`/`.mean`/`.std`）与 Python 顺序 `sum(win)` 在零方差边界上差 1ulp——`sum([1.1]*20)/20` 恰好精确等于窗值时纯路径方差精确 0 → `if not sd` → None；pairwise 均值偏 1ulp → 方差 ~1e-32 → 垃圾 z 分。

**修复**（`operators_np._seq_sum`）：沿窗口轴 `np.cumsum(...)[:, -1]`——cumsum 是真前缀扫描（左到右逐元素累加），与 Python `sum(win)` 的舍入路径**逐位一致**。应用于 MEAN/SUM/STD/ZSCORE/CORR（表达式结构照抄纯实现，含 `var ** 0.5` 位置）。`stats_np.spearman` 同源修复：`mx/my` 用 `cumsum(sort(ranks))[-1]/m` 复刻纯 `sum(dict.values())` 的**秩升序插入序**（并列秩为相等浮点，相邻等值加法可交换，任意升序排序求和序等价）；`sxx/syy/sxy` 用数组原序 cumsum 复刻纯下标序。

**边界行为验证**（`tests/test_factor_miner_numpy_path.py::ConstantWindowBoundaryTests`，3 项新增回归）：
```
const=1.1 n=20 pure[n-1]=None  numpy[n-1]=None   -> BITWISE-EQUAL  ← Codex 反例
const=1.3 n=60 pure=0.99163…  numpy=0.99163…    -> BITWISE-EQUAL  ← 纯路径自身的
const=2.9 n=33 pure=-0.98473… numpy=-0.98473…   -> BITWISE-EQUAL    浮点运气垃圾z
const=3.7 n=20 pure=-0.97468… numpy=-0.97468…   -> BITWISE-EQUAL    同样被逐位复刻
```
即：None↔值翻转类分歧（P1 实质）被消除；纯参考实现的边界怪癖被原样保留而非"修正"。

### 10.2 P2（验证工具假 PASS）——修复：删除两处机制

1. **秩换位豁免删除**：v2 探针的 `analyze_transposition` 找到换位搭档即将该单元移出 fails（`continue`）——豁免机制与"零白名单"声明矛盾。round-2：该函数仅作失败时附加诊断信息（`[transposition-partner: …]`），**不改变 FAIL 判定**。
2. **确定性改严格 ==**：v2 的"逐位确定性"实际复用容差 `compare_unit`。round-2：确定性检查独立使用严格元素级 `==`。

### 10.3 验证货币定稿（比 D-34 原案与 v2 实现都更细）

| 对象 | 标准 |
|---|---|
| 长度、None/±inf 位置、零方差边界（None↔值翻转） | **严格逐位** |
| 有限非零数值 | `isclose(rel_tol=1e-12, abs_tol=1e-12)`，**零豁免** |
| 门禁布尔、n 计数、bootstrap 输出 | **严格逐位** |
| 同路径确定性 | **严格 ==** |

有限数值保留 1e-12 容差的唯一残差来源，实证定位为**平台 libm pow 与 IEEE 正确舍入的 1ulp 差**（2.2M 随机样本：Python `x**2 != x*x` 1117 例；Python `x**0.5 != np.sqrt(x)` 约 50%）——纯路径 STD/ZSCORE/CORR 内嵌 `**2`/`**0.5`，逐位复刻 Windows libm pow 不现实；1ulp 级扰动不改变 None 位置与门禁布尔（门禁消费月度聚合 IC）。此为协议终态，不再收窄。

### 10.4 round-2 全证据重跑

- `tests.test_factor_miner_numpy_path` + `tests.test_factor_miner_stats_np`：**35+11=46 项 OK**（+3 常数窗口回归）；
- 全仓：**Ran 1075 tests, OK (skipped=1)**（主对话独立复跑）；
- 250 公式探针（协议标签明示"masks/boundary STRICT BITWISE; finite values tol 1e-12 (no exemption); determinism strict =="）：**PASS**（232 计算单元 + 18 一致 fail-closed）；
- 统计专项：spearman/ic_decay×pool/nopool/bootstrap-RNG 全 PASS；
- **真实数据 dev-smoke 双跑**（cumsum 修复后重做）：60 股 × 12 单元，registry 深比较 **12 factors, diffs: 0**（纯 20260910_224529 vs numpy 20260910_224701）。
- 性能注记：cumsum 比 pairwise 归约慢，且当晚 R0 正式批竞争 CPU，合成规模实测 2.4×（热身 3.5×，此前不竞争时段 7.7~9.5×）；**干净环境实测待 R0 退出后补充**，加速比不是等价性论据，仅影响是否值得做 v3 矩阵化的决策。

### 10.5 round-2 建议审核点（增量）

1. `_seq_sum` 的 cumsum=顺序求和等价性（含 memory-layout/strided view 下的轴序）；
2. `stats_np.spearman` 的 `cumsum(sort(ranks))` 与纯 `sum(dict.values())` 插入序等价性论证（并列等值加法可交换前提）；
3. 常数窗口回归测试是否覆盖足够多的常数/窗口组合（当前 1.1/1.3/0.7/2.9/3.7/10.01/−4.2 × n=5..120）；
4. 1e-12 容差残差归因（libm pow）的实证是否充分、是否存在其他未识别残差源。

## 11. round-3：Codex round-2 CHANGES_REQUESTED 的处置

### 11.1 [P2] 探针确定性检查仍用容差（probe:211）——修复

Codex 反例（mock 注入第三次调用 5e-13 漂移 → 探针仍报 PASS、退出码 0）证实 round-2 只改了打印文案未改比较机制。round-3 修复：

- 新增 `compare_strict`（严格元素级 `==`，零容差，含 None/±inf 掩码与长度），**确定性循环改调用它**（`np_dualpath_diff_probe.py`）；
- **负例测试固化**（`tests/test_factor_miner_np_tools.py::ProbeDeterminismNegativeTests`）：用与 Codex 相同的 mock 注入方式——第三次 `evaluate_all` 漂移 5e-13 → 断言 `main()` 退出码 1 且输出含 FAIL/NONDETERMINISTIC；稳定 mock → 退出码 0；`compare_strict` 对 5e-13 与 None 掩码漂移的单点断言。

### 11.2 [P2] registry 未严格比较 bootstrap 与整数计数（compare:59-62）——修复

Codex 反例（bootstrap.lower 0.1→0.1+5e-13 差异列表为空；n 10**12→10**12+1 被 isclose 吸收）。round-3 修复（三层比较协议）：

- **整数（非 bool）一律精确 `==`**（n/n_months/长度类计数）；
- **路径含 `bootstrap` 的子树严格 `==`**（RNG 种子身份输出不容差）；
- 其余有限浮点维持 1e-12 容差（§10.3 协议；残差=libm pow 1ulp）；
- **负例测试固化**（`RegistryCompareNegativeTests`，6 项）：10**12 计数漂移必须检出；bootstrap 5e-13 漂移必须检出；普通浮点 5e-13 按协议容差不报；端到端临时 registry 文件含 bootstrap 漂移 → `main()` SystemExit(1) 且 VERDICT: FAIL。

### 11.3 对 Codex 结语句的正面回应

「有限数值的一般容差与离散信号/门禁一致性是不同约束，不能由'误差只有 1ulp'直接推导门禁永不改变」——接受。门禁一致性不由容差推导，由以下**独立严格通道**建立：①registry 深比较中 gate_pass/gate_reasons 走 bool/str 精确分支；②探针的 None/边界掩码严格逐位（None↔值翻转即 FAIL）；③整数计数精确；④bootstrap 子树严格。1e-12 容差仅适用于非离散连续浮点字段（如 mean_ic），其与门禁的关系只作为经验证据而非推导。

### 11.4 round-3 证据

- `tests.test_factor_miner_np_tools`：**10 项 OK**（含全部 Codex 反例负例）；
- 探针真实重跑（严格确定性分支生效）：**differential verdict: PASS，determinism (strict ==): PASS**；
- registry 深比较（三层协议）重跑 round-2 真实工件（224529/224701）：**12 factors, diffs: 0**；
- 全仓：**Ran 1085 tests, OK (skipped=1)**（主对话独立复跑；1075+10 负例）。
- 注：本轮未重跑 dev-smoke 双跑——registry 检查器的三层协议由负例测试直接证明，round-2 已有真实工件在新检查器下复验通过；如 Codex 要求可随时重跑。

### 11.5 round-3 建议审核点

1. `compare_strict` 的严格性（None/±inf/长度/元素级 ==）与确定性循环的接线；
2. registry 三层判定的边界：int/bool 分流、`"bootstrap" in path` 子树判据是否足够（是否有其他需严格的离散字段未覆盖——请指出即改）；
3. 负例测试与 Codex 反例的等价性（mock 注入方式、5e-13/10**12+1 量级）。

## 12. round-4：Codex round-3 CHANGES_REQUESTED 的处置（A 阶段完整性收尾）

Codex round-3 确认：round-2 两处数值比较问题已闭合（其独立注入换位/None 翻转/缺单元均被正确拒绝；56 tests OK）。新增两条 P2 均为工件完整性缺口，另要求探针测试自包含化。**受审时序说明：Codex round-3 读取的是 46a84db 提交前的工作树（{N} 占位符未填）；实际提交 46a84db 已含全仓 1085 项结果与全部 round-3 材料，本节为其后增量（round-4 提交 35fe217）。**

### 12.1 [P2] 重复 factor_id 静默折叠——修复

`load()` 逐行解析（1-based 行号）：**任何重复 factor_id（相同或冲突内容）→ LoadError，stderr 报"路径:行号: 重复 factor_id 'X' (首次出现于第 N 行)"，退出码 1**；缺失/空字符串 factor_id、非 JSON 对象行、非法 JSON 行同样 fail-closed。

### 12.2 [P2] 双空工件判 PASS——修复

- 新增 `--expect-ids <path>`（冻结候选清单：jsonl 每行 factor_id/id 字段，或纯 ID 文本）：提供时校验两侧 ID 集合**双向完整等于**预期（缺失与多余均 FAIL 并列出具体 ID）；
- 未提供时任一侧空工件 → stderr 提示"空工件需 --expect-ids 定义空批语义" + VERDICT: FAIL + 退出码 1；
- **空批语义（显式）**：预期清单本身为空文件且两侧 registry 均空 → 视为显式声明的空批 → PASS（Codex 要求"需要空批语义的场景另行显式定义"的实现位置）。

### 12.3 探针输入完整性与测试自包含化

- `main(hypotheses=None)` 可选注入参数（缺省读冻结文件，行为不变）；**重复 hypothesis id → stderr 报错（含两个出现位置）→ 退出码 1**；
- `compile_fail>0` 时在 verdict 前打印 `COVERAGE WARNING: compile_fail=N`（覆盖不足可见化，不改变例外单元 fail-closed 的 PASS 逻辑）；
- 全部 mock 测试改用内置 4 条微公式 + 微型 bundle，**不再依赖 artifacts/ 存在**。

### 12.4 round-4 证据

- `tests.test_factor_miner_np_tools`：**18 项 OK**（10 旧 + 8 新端到端负例：重复 ID 相同/冲突、缺/空 factor_id、双空、--expect-ids 缺单元 FAIL、--expect-ids 完整 PASS、探针重复 id）；
- 三文件合计 64 项专项测试 OK（主对话独立复跑）；
- **真实工件复验**（12 单元冻结清单作 --expect-ids）：`factors compared: 12 / diffs: 0 / VERDICT: PASS`（退出码 0）；
- CLI 冒烟（主对话独立执行）：重复 ID → exit 1（错误含 `dup.jsonl:2:`）；双空 → exit 1；缺预期单元 → exit 1；
- 全仓：**Ran 1093 tests, OK (skipped=1)**（主对话独立复跑；1085+8 新负例）。提交 35fe217。

### 12.5 round-4 建议审核点

1. 空批语义边界：空预期清单 + 双空 registry → PASS 的显式读法是否可接受；
2. `load_expect_ids` 对"非 jsonl 行按纯 ID 文本回退"的处理（损坏 jsonl 行会成为字面 ID 而非报错）——是否需要收严为必须显式声明清单格式；
3. 探针 compile_fail 警告不改变 verdict 的读法（覆盖不足由人工判断，还是应升级为 FAIL）。
