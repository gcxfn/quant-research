# HANDOFF：因子引擎性能优化 A/B/C/D/E 阶段（批次 `-4`）

**日期** 2026-09-13 · **状态** 交付完成，等外部审核（批次 `-5`；`-4` 因缺少 B1 证据工件被取代） · **入口计划书**
`docs/experiments/t1-t3-implementation-review-20260913.md`

---

## 0. 一句话

按计划书完成 F1–F4 正确性整改、B 阶段 CPU 优化、C 阶段 GPU 局部原型评估、D 阶段
"不做"判定与 E 阶段装箱；有效成果是 **B2 装载去重（进程 wall 1.23×/1.25×）** 与
**四项缺陷修复**；**GPU 不采用**（同源端到端 1.32× < 1.5× 判据）。
全量 20 片**未跑**（用户取消状态未恢复）。

---

## 1. 材料在哪

| 项 | 路径 |
|---|---|
| **交付批次** | `D:/AI/workspace/个人量化/artifacts/factor-engine-performance-20260913-5/` |
| 受审源码（隔离独立仓） | `D:/AI/workspace/factor-engine-perf-isolated-20260913` · `master @ 2c3a31f3` · 工作区干净 |
| A/B 对照侧 | `D:/AI/workspace/factor-engine-perf-a-20260913` · `b231c110`（detached） |
| 主仓 | `D:/AI/workspace/个人量化` · **工作树未改动** |

批次内容：`review.md`（实施说明）、`baseline.md`（实测与 F4 更正）、`VERSION.md`
（取代关系/身份作用域/逐优化默认状态）、`manifest.json`、`diff/`（5 份差量）、
`source/new/`（受审源码全量 + 全部证据生成器）、`source/p1_frozen/`、`equivalence/`。

**自核结果**：59 工件 · `missing_expected: []` · 逐文件 sha256 重算 0 不匹配 ·
5 份差分应用后逐字节一致（忽略 CR）· `evidence_all_newer_than_deps: true`。

---

## 2. 先看这三件（最重要的判断）

1. **为什么有 `-4` 而不是改写 `-3`** — 见 `VERSION.md`。核心理由：`-3` 的
   `spearman_bit_identical: true` / `real_sample_all_identical: true` **没有覆盖**一个真缺陷 ——
   `_average_ranks_batch_torch` 旧实现先 `col[col==col]` 剔 NaN 再排序，**±inf 与缺失交错时
   真实 `inf` 的秩算错**。反例 `x=[nan,1.0,inf,nan,2.0]`：CPU 对 `inf` 给秩 3、旧 GPU 给 4。
   现改两趟稳定排序（有效性分区 + 值排序）+ 压紧回填 + 每列独立哨兵 `m`；
   `rank_equivalence_adversarial` 10 例（含该反例）0 mismatch。
   → `-3` 的等价性声明只说明"当时测到的输入上一致"，不覆盖这个输入类。

2. **A/B 等价性是不是真的** — `equivalence/ab_bphase_compare_r{1,2}.json`：
   两轮 `PASS_EXACT`，`n_diffs=0`、`n_float_diffs=0`、`n_deciding_mismatch=0`；
   两侧 `bt_results_sha256` = `59da29fc…`、`factors_sha256` = `fb75d5f9…` 相同。
   比对器已按 F3 分层（`float_diff>0` 一律不得签 `PASS_EXACT`）。

3. **GPU 不采用站不站得住** — `gpu-bench.json::adoption_criteria`（**独立审核 R3 更正后的口径**）：
   判据**按实际运行配置**分别应用，不跨配置组合，且**两轮结果并列**。本批同源真实计时
   （train_test 2.127s、CPU 衰减 0.969s）：`block=128` 热点 **0.91×** ✗／估计 **0.955×** ✗、
   `block=None` **1.41×** ✗／估计 **1.152×** ✗；上批 `-5`（train_test 2.292s）为 1.66× ✗
   与 **2.13×** ✅（但**计算阶段替换估计 1.318×** ✗）→ **两轮都无配置同时通过两项阈值，故不采用**。
   **跨轮方差约 1.8×（合成面板 2.40→1.76）已披露**，决策不依赖单轮数字。
   **2.3–3.2× 是合成全池形状面板的数字**（本批 3.15/2.65/2.30），**不能**当作任一真实配置
   通过热点门槛的证据；**样本计算阶段估计，GPU 保持原型；全池待测** —— 占比本批 **0.456**
   （上批 0.455）只是 **train_test 计算段之内**的衰减占比，不含装载（占 wall 82.5%）、
   身份核验、聚类、落盘与初始化，与装载占比不是同一分母。

---

## 3. 改了什么

### 3.1 正确性整改（阶段 A）

| # | 缺陷（计划书） | 整改 | 证据 |
|---|---|---|---|
| F1 | worker `_input_identity` 只摘要"收盘**长度** + 池掩码 True **计数**"；close 11→999、volume 2→999、两日期掩码**交换**三种扰动下摘要全不变 → 续跑认不出换数据 | `engine.input_content_digest`：对**实际消费的每个字段取值**与**逐日期池掩码**做规范摘要（顺序敏感；None≡NaN、±inf 保留）；`director.run_real_pipeline` 每次调用**当场重算**并比对（自报字符串不构成身份），缺/伪造即 fail-closed | `identity-tests.json` `f1_*` 13 项 |
| F2 | `t3_l0_batch_20260913._verify_identity` 只比清单 JSON **文件自身** SHA；原始数据被改写而清单不变时仍接受旧身份 | 入口按**实际消费数据根**重建清单，启动/恢复与收尾复用 `r0_audited_runner.verify_data_manifest`（新增，**唯一实现**）重算逐文件 sha256 + digest + 文件集合 + 根集合；数据根另做 real-path 绑定 | `identity-tests.json` `f2_*` 15 项 |
| F3 | 比对器把容差内浮点差异只记 counter 不进 `diffs` → `0.1` 与 `0.1+1e-16` 被签成"逐位相同" | 精确层/容差层分开记账；`float_diff>0` 不得 `PASS_EXACT`（新增 `PASS_WITH_TOLERANCE_DIFFS`）；`NaN` 双侧相同、单侧 FAIL；决定性字段容差感知 | `compare-selftest.json` 11 项（含 4 项实质性分歧负例） |
| F4 | `0.30/5.84` 应为 5.14%、`1.24/6.78` 应为 18.29%（旧写 4.4–17.9%）；"中点装载 33%" 与表内不符；13/69.2 min 不构成上下界；含装载 1.168× 与计算段 2.19× 混用 | 三档分开（计算段实测 / 含装载样本实测 / 全量假设）；13–69.2 min 降为**情景假设**；端到端 GPU 估计改**同源**口径 | 包内 `baseline.md` §2 |

### 3.2 CPU 优化（阶段 B）

| # | 改动 | 默认状态 |
|---|---|---|
| B1 | `stats_np.spearman_np` 去两次冗余排序（平均秩和恒为 `m(m+1)/2`） | **生效**；300 组对抗用例逐位相同 |
| B2 | 装载去重 `data_fields.memoized_load`（键 = loader + 路径令牌 + 文件 `(realpath, mtime_ns, size)` + 参数），容量有界 | **opt-in**；状态写入 `run_meta.perf_caches` |
| B4 | 聚类月末值就地生成（同一 `factor_monthly_values` + 同一轴/池），日频因子即释放 | **opt-in** |
| 缓存绑定输入身份 | `stats_np.panel_cache_bind` + `director.bind_perf_caches_to_input`（`train_test` 入口）；换 bundle/轴即整表失效并重置计数 | 随缓存开启生效 |
| B3 / B5 | 内部数组出口 / 面板复用 | **不实施**：插桩实测合计 `b3.series_matrix` 0.152s + `b3.close_panel` 0.007s + `b5.pool_panel` 0.011s = **wall 的 0.34%** → 收益不支持 |

### 3.3 GPU 局部原型（阶段 C）：不采用

`experiments/factor_miner/stats_gpu.py`（隔离模块，**不被 `stats_np` 默认路径导入**）。
修正平均秩缺陷（见 §2.1）；补块/OOM 协议（`DEFAULT_DATE_BLOCK=128`、`MIN_DATE_BLOCK=1`、
减半重试、不可恢复 → `GPUFallbackRequired` → 整候选回落 CPU）；每因子**只上传一次** F/C/pool
（旧路径逐期限逐块重传，正是 `-3` 中真实衰减段仅 0.75× 的原因）；全程 float64。
**未装新依赖、未改驱动**。

### 3.4 D 阶段：不启动

进入条件"B/C 后有实测剩余热点"不满足 —— B3/B5 已否决（<1%），未出现新的支配性热点，
bootstrap/聚类无新增开销证据。

---

## 4. 实测数字（限被测支持集）

### 4.1 A/B（285 股 / 20 单元，交错两轮，同 harness 字节 `d5b18397…`）

| 段 | A（P1+F1–F3） | B（+B1/B2/B4） | 倍数 |
|---|---|---|---|
| 装载 | 55.190 / 55.934s | 41.134 / 41.122s | **1.34× / 1.36×** |
| train_test | 9.083 / 9.109s | 8.757 / 8.705s | 1.037× / 1.046× |
| 成本阶梯 | 12.655 / 12.765s | 12.178 / 12.200s | 1.039× / 1.046× |
| 进程 wall | 77.69 / 78.57s | 63.00 / 62.97s | **1.233× / 1.248×** |
| 峰值工作集 | 597 / 597 MiB | 606 / 605 MiB | 1.015×（无内存回退） |

机制证据：B 侧 `load_memo = {enabled: true, entries: 4, hits: 972, misses: 764}`（两轮一致）；
A 侧为 `None`（无此函数，`hasattr` 守卫）→ 去重**确实发生**。

### 4.2 分段剖析（`profile-reviewfix.json`，270 股 / 728 区域日 / 20 单元）

wall **49.806s**；装载 **41.109s（82.5%）**；单 pass 8.689s（统计段 5.336s）；峰值 RSS 531.6 MiB。
明细：`load.stock_rows` 18.212s / `load.valuation_fields` 13.130s / `load.merged_price_rows` 13.321s /
`load.pool_mask_by_date` 4.577s / `load.margin_fields` 4.336s / `stats_np.ic_decay_curve` 3.973s。
运行**结束后**的缓存遥测：面板 `hits=38, misses=2` + `bound_input_identity` 非空；截断 close `hits=19`。
（`-3` 把该快照取在 `build_real_bundle` 之前，恒为 0，会让人误判 B2 未生效。）

### 4.3 GPU（**按实际运行配置**分别评估；R3 更正后口径）

| 口径 | 本批 `-6` | 上批 `-5` |
|---|---|---|
| 合成：批量 Spearman S=5552，K=971/952/728（含传输/同步） | **3.15× / 2.65× / 2.30×** | 2.88× / 2.72× / 2.79× |
| 合成：衰减面板（S=400,D=972） | `block=None` **1.76×** / `block=128` **1.42×** | 2.40× / 2.06× |
| 真实 285 股衰减段 · `block=128`（协议配置） | 热点 **0.91×**（0.969/1.070）✗；计算阶段替换估计 **0.955×** ✗ | 热点 1.66× ✗；估计 1.220× ✗ |
| 真实 285 股衰减段 · `block=None`（不分块） | 热点 **1.41×**（0.969/0.688）✗；计算阶段替换估计 **1.152×** ✗ | 热点 2.13× ✅；估计 1.318× ✗ |
| `real_decay_share`（作用域 = **train_test 计算段之内**，非含装载端到端） | **0.456**（分母 = train_test 总耗时 2.127s） | 0.455（分母 2.292s） |
| 纯 argsort 微基准 | <1×（单列并行度不足 → 计划书 §2 的 18.34× 不可外推） | 同 |

合成两行**是合成面板，不是真实运行配置的计时**，不作任一真实配置达标的证据。

**跨轮方差必须一并读**：同一二进制、同一输入，两轮之间 GPU 段倍数可差约 **1.8×**
（合成面板 2.40 → 1.76）。逐单元数据显示首个单元含 CUDA 首次调用开销
（首单元 `gpu_sec_blocked=0.286s` vs 后续 `0.198/0.197s`），且本批整轮跑在长时间重负载之后。

**两轮都没有真实配置同时满足两项阈值**：本批两者皆不达；上批 `block=None` 达 2×（2.13×）
但其计算阶段估计 **1.318× 仍 < 1.5×**。故决策**不依赖任何单轮数字** → 不采用；
结论只到**样本计算阶段估计**，**GPU 保持原型，全池待测**。

### 4.4 全量（**未跑**）

`load-scaling.json`：285→64.0s、570→101.4s、1140→173.4s，拟合 `slope=0.1277 s/symbol`、
`intercept=28.0s` → 全池（5552）≈737s ≈ 12.3 min（与历史单点 780s 比值 0.94）。
**这是外推，不是全批实测**，不作为承诺。

---

## 5. 计划书 §9 逐条对照

| 条 | 要求 | 落点 | 状态 |
|---|---|---|---|
| §9.1 | 源码差量 + 代码/输入/清单摘要 + Py/NumPy/Torch/CUDA/设备配置 | `manifest.json`（`changed_files`/`diffs`/`env.runtime`）、`gpu-bench.json::env_config` | ✅ Python 3.11.15 / numpy 2.4.6 / torch 2.11.0+cu128 / CUDA 可用 / RTX 4060 Laptop 8188 MiB |
| §9.2 | 合成基准 + 原始三轮计时 + 代表 ID 与选择规则 + 分段计时 + RSS/显存 + 回退记录；A/B 明确是否含成本阶梯 | `gpu-bench.json`（`rank_microbench_5552`/`spearman_batch_panel`/`real_sample`/`fallback`/`vram_after`）、`b-phase-ab-n285.json`（两侧同 `--with-cost-ladder --panel-cache --reuse-factor`） | ✅ |
| §9.3 | 正常路径、F1–F3 反例、并列/缺失/±inf/全常数/训练末尾边界/**块边界**/**缓存换输入**/中断恢复/**OOM** | 见 §5.1 映射表 | ✅ |
| §9.4 | 掩码/有效数/秩/月IC/bootstrap/gate/衰减/分层/聚类及候选处置对照；比对器区分精确与容差 | `equivalence/` 6 份 + `b-phase-ab-n285.json::compare` | ✅（`PASS_EXACT` 两轮；容差层自检于 `compare-selftest.json`） |
| §9.5 | 原片集合与 1430 分母检查、每候选后端、CPU 回退/技术重跑记录 | `denominator-check.json` | ✅ 1430 行 / 20 片精确划分 / 20 代表全在册 / `n_tests` 对齐分母 / `status: PASS` |

### 5.1 §9.3 负例映射（逐项）

| 类别 | 落点 | 计数 |
|---|---|---|
| 正常路径 | `checkpoint-test.json`、`cli-test.json`（真实 `-8` 分片 × 285 股端到端） | 29 / PASS |
| F1 三类扰动 + 缺失语义 + 重算闸三态 | `identity-tests.json` `f1_*` | 13 |
| F2 内容改写/新增/删除/根缺项/根改指 + 启动与收尾 | `identity-tests.json` `f2_*` | 15 |
| F3 精确/容差/NaN 对称/决定性字段（含 4 项实质性分歧） | `compare-selftest.json` | 11 |
| **缓存换输入**（B2 备忘文件内容/路径根、面板重绑清空、同身份保留、日期轴变化） | `identity-tests.json` `b2_*`/`p1_*` | 8 |
| 并列/缺失/±inf 平均秩 | `gpu-bench.json::rank_equivalence_adversarial` | 10 |
| **块边界** `n_dates=1/128/129/896/972` | `gpu-bench.json::block_boundary` | 5（全部 `bit_identical: true`、`n_mismatch: 0`、日期覆盖完整） |
| **OOM** 减半/上限/不可恢复回落 | `gpu-bench.json::oom_policy` | 减半覆盖全部日期 ✅、不超上限 ✅、`GPUFallbackRequired` ✅ |
| 中断恢复/缺片/篡改/门禁分歧 | `checkpoint-test.json` | 29 |
| CUDA 故障回落 | `gpu-bench.json`（结果与 CPU 逐字段相同） | ✅ |

---

## 6. 我自己认的问题（审核时请一并看）

1. **`EVIDENCE` 里曾把打包器 `t3_perf_package3_20260913.py` 误声明为 6 条 A/B 证据的生成器**
   （应为 `_perf_work/b_phase_ab.py`）。已修全部 6 条；模块扫描现报
   `entries whose generator is the packager: NONE`。
2. **`review.md` 里面板缓存绑定的作用域我一开始写宽了**。准确说法已补进文档：条目的 `id()`
   键本就持强引用并做 `is` 复核，**跨对象串用本来就不可能**；绑定解决的是 (a) 计划书 §4
   "缓存生命周期属于输入身份"、(b) **遥测口径**（不重置则 hits/misses 跨身份累加会读错）、
   (c) 日期轴变化。**"原地改写仍在被引用的面板对象"未加值级校验**，已明示为**调用方只读契约**。
3. **打包器新鲜度判据返工**：初版用"证据 mtime 晚于 HEAD 提交时间"，**既不充分也不必要** ——
   改打包工具也要求全部 18 份证据重跑（实际白跑过一轮）。已改为**声明式依赖面**：每条证据声明
   读取的源码集合与生成器，逐文件比对 mtime，并把依赖文件的当前 sha256 写进
   `manifest.json::evidence_provenance`。验证：提交打包器后 **0 条证据失效**。
4. **打包器改为暂存后原子发布**：缺件/依赖更新/文档缺失一律非零退出且**不留产物**（旧实现
   只在 manifest 里列 `missing` 并 exit 0，等于交付半个包）。已用三个负例实测（缺件、目标已存在、
   旧证据）→ 均 exit 1 且无产物。
5. **`denominator-check.json` 的 `n_tests` 口径**：A/B harness 原先用 1456（旧清单），
   已对齐**冻结分母 1430**；l0-only 默认值同步改为 1430。
6. **`-4` 发布后我发现自己引了一个无工件的数字**：文档引用"300 组随机对抗用例逐位相同"
   作为 B1 等价性依据，但 `-4` 包内**没有**这件工件（`kernel_equiv.json` 只有 15 个命名
   ranks 用例 + 25 个命名 spearman 用例）。数字为真但**不可复核** —— 这正是审核会抓的那类
   问题。已补 `b1-adversarial.json`（固定种子 20260913、300 组、12 类，与优化前原始字节
   `repr` 级逐位对照，**300/300 ok、0 mismatch**），并把生成器
   `t3_perf_b1_adversarial_20260913.py` 一并交付，故重建为 **`-5`**（`-4` 原样冻结、不改写）。
7. **cProfile 有插桩开销**（同剖析内自比可比、绝对耗时不可与常规运行混比）；B3/B5 结论取自
   **常规运行的分段计时**，cProfile 仅用于内部分解与交叉核对。

---

## 7. 未做 / 未决（不因本批通过而放行）

- **全量 20 片 / 全池 5552 股未跑**（用户取消状态未恢复）。§4 所有倍数只覆盖 285 股样本 + 合成面板。
- **全量**：计划书要求"用户恢复全量后再按新快照运行并核 1430 结果覆盖；未恢复前保持未启动"。
  现仍未启动。授权恢复后按 §7.1 的命令跑，跑完核对 1430/1430 接受与 0 身份错误。

### 7.1 T3 新快照已登记（本文件写作后又补做）

| 项 | 值 |
|---|---|
| 新快照 | `D:/AI/workspace/t3-snapshot-20260913-2/` |
| 快照提交 | `2c3a31f3`（= 本批受审源码身份），worktree detached，工作区干净 |
| 数据 | `data/` junction → `D:/AI/workspace/个人量化/data`（只读用途） |
| 新批次 | `D:/AI/workspace/个人量化/artifacts/new-factor-research-20260912-12/` |
| 批次内容 | `-11` 的 1430 清单 + 20 片**原样复制**；`run-identity.json` 与 `data-manifest.json` 由 identity 子命令**在新快照下重建**（计划书 §4：新身份用新输出目录，不在旧检查点上更新摘要后复用旧片） |
| 旧批次 | `-11` 的 `run-identity.json`/`data-manifest.json` **未改动**（只新增不覆盖） |
| 身份摘要 | `snapshot_commit=2c3a31f3`、`n_slices=20`、`data_manifest_n_files=20275`、12 个数据根、36 个期望月末 |
| 身份一致性 | `run-identity.json::files` 里 `repo:` 与 `snapshot:` 两侧 4 个 runner 摘要**逐个相同** → 新快照确实带着 F2 修复的 runner |

**已用真 CLI 验证**（可复算）：`identity` 子命令实测通过（13 文件 / 20 片 / 期望月末 36 个）。

#### ⚠ 两个入口必须分开说（决定全量耗时差数小时）

| 入口 | 装载付费次数 | 全量装载成本 | 是否在 `run-identity.json` 内 |
|---|---|---|---|
| `experiments/t3_l0_batch_20260913.py run` | **每片一次**（20 次 `director pipeline` 子进程） | 20 × (199s universe + bundle) ≈ **1.5 h+** | ✅ 4 个脚本都在 |
| `experiments/t3_l0_worker_20260913.py run` ← **应当用这个** | **一次**（一次装载顺序消费全部分片） | universe 199s + bundle ≈ **12–13 min** | ❌ **未登记** |

worker 自己的 docstring 就是为此写的：「现批跑器每片新起一个 director 进程 → 每片重复
`load_formal_universe`（实测约 302s）与 `build_real_bundle`（数百秒）。20 片即纯装载占整批的
三分之一以上。本 worker 一次装载、顺序消费全部逻辑分片 → 装载只付一次。」

**（本节的绑定缺口已在 `-6` 修好，保留原文以便对照）**：`T3_SCRIPTS` 只含
`t3_enumerate_20260912.py` / `t3_catalog_wave2_20260913.py` / `t3_l0_batch_20260913.py` /
`t3_synonym_check_20260913.py`，**没有 worker**。worker 在运行时会自绑
（`code_sha256` 含其自身字节，见 `_code_identity_now` / M-2），所以**结果不是无绑定的**；
但**冻结阶段没有 worker 字节的记录**。若全量确定走 worker，
**须先把 worker 加入 `T3_SCRIPTS` 并在新批次目录重建 identity**；该改动会落在
`t3_l0_batch_20260913.py` 上，而它是 `identity-tests.json` 与 `cli-test.json` 的声明依赖，
按依赖面规则这两份证据须重跑，性能包相应重建为**新编号**。**此项待审核裁决后再定**，
不在本批（`-5`）内做 —— 避免在用户已送审的材料上再翻一版。

```bash
PY=D:/AI/agent/hermes/venv/Scripts/python.exe
SNAP=D:/AI/workspace/t3-snapshot-20260913-2
ROSTER=D:/AI/workspace/个人量化/artifacts/new-factor-research-20260912-12

# 身份登记/复核（已实测通过）
$PY -X utf8 $SNAP/experiments/t3_l0_batch_20260913.py identity --roster-dir $ROSTER --snapshot $SNAP

# 路径一（在 run-identity 内，但装载付 20 次；需用户先恢复授权）
$PY -X utf8 $SNAP/experiments/t3_l0_batch_20260913.py run \
    --roster-dir $ROSTER --out-root <新输出根> --snapshot $SNAP
$PY -X utf8 $SNAP/experiments/t3_l0_batch_20260913.py aggregate \
    --roster-dir $ROSTER --out-root <新输出根> --snapshot $SNAP

# 路径二（装载只付一次；worker 自绑。**用前须先补 T3_SCRIPTS 并重建 identity**）
$PY -X utf8 $SNAP/experiments/t3_l0_worker_20260913.py run \
    --roster-dir $ROSTER --out-root <新输出根>
$PY -X utf8 $SNAP/experiments/t3_l0_worker_20260913.py aggregate \
    --roster-dir $ROSTER --out-root <新输出根>
```

**CPU 回退命令（独立审核第 4 条更正 —— 本文件早前版本在此写错了）**：

```bash
# 正确：回退必须**显式** --backend pure，且换新输出根
$PY -X utf8 $SNAP/experiments/t3_l0_worker_20260913.py run \
    --roster-dir $ROSTER --out-root <新的输出根> --snapshot $SNAP \
    --backend pure            # ← 少这个参数就不是回退
```

审核亲测：清掉 `FACTOR_MINER_NUMPY` 后执行**默认参数**，requested/actual 仍是
numpy、环境变量又被置回 `1`；只有显式 `--backend pure` 才得到 pure。原因是
worker 的 `_apply_runtime_config` 按 `args.backend` **主动设置**环境变量（这正是
设计意图：不让"环境里恰好有什么"决定被测面），所以"清环境变量"不是回退手段。
本批已把这条钉成新进程证据（`cli-newprocess.json` 的
`explicit_pure_backend_actually_switches` 与反例
`clearing_env_var_is_not_a_fallback`）。

另注：`--backend pure` 只是**当前代码**的纯 Python 统计路径，**不是**恢复优化前的
源码。批跑 director 入口的配置机制与之分开（它用 `FACTOR_MINER_NUMPY` 与
`director pipeline --panel-cache/--load-memo`），两套说明不要混用。
要关面板缓存再加 `--no-panel-cache`。两个入口都会把已完成片判为 `already_done` 并跳过，
故回退验证必须用**新的输出根**（计划书 §9 禁止把新旧片拼成同一执行身份）。

### 7.2 独立审核 R1–R5 整改（2026-09-13 审核后补做）

审核裁决：**整体交付/切换准备 CHANGES_REQUIRED；已测 CPU 优化与局部正确性修复
PASS_WITH_LIMITATIONS**。逐条整改落点（复核材料在**新批次** `-6`，不覆盖 `-5`）：

| 项 | 审核要求 | 本批落点 |
|---|---|---|
| **R1** | worker 绕过事前冻结数据与代码契约（推荐入口不读 `run-identity.json`/`data-manifest.json`） | worker 在**装载前/恢复前/汇总前**调 `batch_mod._verify_identity`，把冻结摘要作为 `frozen` 段并入运行身份 → 检查点与 session **自动绑定**冻结 manifest 摘要；收尾调 `_verify_data_identity_tail` 复核原始文件。无装载快路径保留，但 ledger 显式标 `verification_mode=resume-artifact-only` + `data_identity_tail.checked=false`（**历史工件核对**，与需核当前数据的 `run` 分开）。worker 加入 `T3_SCRIPTS`，用**新批次** `-13` 登记（`-12` 不改写）。负例 8 条：`frozen-identity-negatives.json` |
| **R2** | 新鲜度仍由 mtime 推断，且漏掉实际依赖 | 判据换成**内容比对**：生成器运行期记录依赖源码 SHA（运行前后各算一次，不一致即不产侧车），打包器拿记录值比当前字节，mtime 仅辅助；依赖表成为单一事实来源并补齐 `r0_audited_runner`/`director` 两项漏依赖；**并修正反向的过度声明** —— A/B 的 `MEASUREMENT_PATHS` 不再列 worker（A/B harness 根本不 import 它，列上会逼出一次无谓的 ~40 分钟重跑）。负例 6 条：`package-negatives.json`，含审核指定的"字节改变但时间戳不变仍拒绝" |
| **R3** | GPU 决策混用计算阶段/含装载流程/不同配置；撤回 0.5–0.55 预测 | 判据改为**按实际运行配置分别**评估（**两轮结果**）：本批 `-6` blocked 热点 0.91×／估计 0.955×、不分块 1.41×／估计 1.152×（均不过）；上批 `-5` blocked 1.66×（不过 2×）、不分块 2.13×（过热点）但估计 1.318×（不过 1.5×）→ 两轮 `adopted=false`、通过配置数 0；合成面板数字单列 `basis`，不再冒充真实配置达标；**跨轮方差约 1.8× 显式披露**；0.5–0.55 预测撤回为无证据假设 |
| **R4** | 交接的 CPU 回退命令不会切换 worker 后端 | 上方命令更正为显式 `--backend pure` + 新输出根；反例随证据交付 |
| **R5** | 交付与测试范围描述需与工件一致 | 同进程 harness / 小规模**新进程** CLI / 全量研究三者分开表述（§7.3）；任务书陈旧文字（`-4` 标题、57 件、"未做 GPU 原型"）已更正 |

### 7.3 三条范围必须分开读（R5）

| 范围 | 是什么 | 能证明 | 不能证明 |
|---|---|---|---|
| `cli-test.json` | **同进程** harness：一个 Python 进程内多次调 `W.main`，替换 universe loader 做 285 股子集（2 片 144 项，`n_tests=144`） | 参数解析到 worker 的样本路径、同进程恢复 | 真进程的启动/恢复/回退；正式 1430 分母 |
| `cli-newprocess.json` | **真新进程**（`subprocess`）+ worker 原生 `--symbols-limit` 缩样 | 启动 / 中断恢复 / 显式 `pure` 回退 / 无冻结身份被拒 | 全量研究结论（面板是缩样） |
| 正式新快照 CLI 全量 | `-13` 批次 + 全池 1430 分母 | 正式运行契约与研究发现 | **未跑**，待用户恢复全量授权 |

缩样样本里的 7 项 gate 通过只是**样本路径**观察，**不可**当 1430 分母下的研究发现。

### 7.4 本批新增证据文件（`-6` 包）

| 文件 | 内容 |
|---|---|
| `frozen-identity-negatives.json` | R1：8 条负例（无冻结身份 / 登记后改数据 / 改 worker / 改分片 / 收尾数据变化 / 恢复路径自我声明） |
| `package-negatives.json` | R2：6 条打包器负例，含"字节改变但时间戳不变仍拒绝" |
| `label-sentinel.json` | 审核建议 4：训练尾哨兵 + 边界锐利性对照（见 §7.5） |
| `cli-newprocess.json` | R4/R5：真新进程启动 / 中断恢复 / 显式回退 / 反例 / 无身份被拒 |
| 各证据同名 `.prov.json` | R2：运行期来源记录（依赖源码 + 生成器 SHA），打包器据此做内容比对 |

### 7.5 训练尾哨兵的结果（审核建议 4）

`label-sentinel.json`（合成面板 30 股 / 1043 数据日 / 训练轴 783 日）：

- **尾部扰动不变性**：只改 2023 年以后的价格（7800 格，含"设为缺失"变体、含
  `FACTOR_MINER_NUMPY=1` + 面板缓存的 numpy 路径），2020–2022 的月度 IC 序列与
  六期限衰减曲线**逐位不变**（`monthly_ic`/`decay`/`decile_spread`/`gate`/整份
  `train_test` 摘要全等）。
- **非平凡性对照（关键）**：同一扰动挪到窗内（index 300 起）**会**改变输出（9 条差异）；
  只改**轴内最后一个合法日** `D-1`（2022-12-30）**也会**改变输出（8 条差异）。
  即边界**锐利**：轴内最后一日被消费、轴外第一日不被消费 —— 不变性不是空转。
- **越界一位探测**：只改 `D`（2023-01-02，轴外第一日，30 格）→ 整份结果摘要不变。
- **尾部消费计数**：轴长 783、数据数组 1043、轴外 260 日；轴内月末 36 个、
  返回 36 行、其中有前向收益标签的 35 个月，末月（2022-12-30）`ic=null, n=0`。
- **常量截面**：两条统计路径（纯 Python 与 numpy）对常量因子/常量目标一律返回
  `None`（含"常量 vs 变量"与"常量 vs 常量"），不是 0、也不是 NaN。

---

### 7.6 阻断缺陷与新交接（2026-09-13 续做后补）

本轮续做时发现一个**阻断性缺陷**：`experiments/r0_audited_runner.py::build_data_manifest`
按**原始**路径字符串排序条目，而 `verify_data_manifest` 从清单 JSON 重新取 roots
（已是 `os.path.abspath` 规范化拼写），两侧顺序不同 → **build 与 verify 恒定产出不同
digest**。根因是 `_consumed_data_roots()` 里 2 个根用正斜杠（`mrs.USER_DATASET_ROOT`
派生的 `D:/…`）、10 个用反斜杠，排序时错位；digest 是顺序敏感的。

实测排除数据侧：20275 个文件逐个 sha256 **全部一致**、集合增删 0、同输入两次 build 相同
→ **不是数据漂移**。**更正**：`-11`/`-12` 记录的 `403071ae…` **不是**另一代实现 ——
实测清单里 `files` 的实存顺序**就是原始路径排序**，用它算出的 digest 恰为 `403071ae…`
（= 记录值）；只有 `verify` 换成规范化拼写后才错位。**一个现存 bug**，不是口径漂移。

后果：`-12` 的登记被自己的校验拒绝（`digest_mismatch`），`-13` 用同一代码登记会同样
恒挂，**全量运行会在启动或收尾 fail-closed**。故本批**不出 `-6` 包**。

**续做入口（唯一当前状态入口）**：
[R1–R5 整改续做交接](handover-factor-engine-perf-20260913-R1R2-continuation.md)
——含根因定位到行、修法与验证口径、D2–D7 其余必修项、已核实无需改的条目、
修复后的串行执行顺序、关键路径清单与禁止事项。

---

## 8. 复现命令

```bash
PY=D:/AI/agent/hermes/venv/Scripts/python.exe
ISO=D:/AI/workspace/factor-engine-perf-isolated-20260913
M=D:/AI/workspace/个人量化
export FACTOR_MINER_NUMPY=1        # 与生产同口径
export T3_PERF_CONCURRENCY_NOTE="serial: each evidence step runs alone on the host"

# 1) F1/F2 + §9.3 缓存换输入（40 用例，秒级）
$PY -X utf8 $ISO/experiments/t3_perf_identity_tests_20260913.py --out <out>/identity-tests.json
# 2) F3 比对器分层（11 用例）
$PY -X utf8 $ISO/experiments/t3_perf_compare_selftest_20260913.py --out <out>/compare-selftest.json
# 3) 检查点/身份/恢复（29 用例）
$PY -X utf8 $ISO/experiments/t3_perf_worker_checkpoint_test_20260913.py > <out>/checkpoint-test.json
# 4) §9.5 分母与分片划分
$PY -X utf8 $ISO/experiments/t3_perf_denominator_check_20260913.py --out <out>/denominator-check.json --n-tests-used 1430
# 5) 真实 CLI 端到端（真实 -8 分片 × 285 股）
$PY -X utf8 $ISO/experiments/t3_perf_worker_cli_test_20260913.py --n-symbols 285 --out <out>/cli-test.json
# 6) A/B 交错两轮（含比对裁决）
$PY -X utf8 $ISO/_perf_work/b_phase_ab.py --out <out>/b-phase-ab-n285.json --n-symbols 285 --rounds 2
# 7) GPU 基准（合成 + 真实样本 + 对抗/块边界/OOM）
$PY -X utf8 $ISO/experiments/t3_perf_gpu_bench_20260913.py --out <out>/gpu-bench.json \
  --real-n-symbols 285 --real-frac 0.25 \
  --sample-hyp $M/artifacts/factor-engine-performance-20260913-1/sample-hypotheses.jsonl \
  --universe $M/artifacts/new-factor-research-20260912-2/trial20-run/universe.json
# 8) 分段计时 + cProfile（B3/B5 判定仪器）
$PY -X utf8 $ISO/experiments/t3_perf_profile_20260913.py --sample $M/artifacts/factor-engine-performance-20260913-1/sample.json \
  --universe $M/artifacts/new-factor-research-20260912-2/trial20-run/universe.json \
  --n-symbols 285 --out <out>/profile-reviewfix.json --tag reviewfix
$PY -X utf8 $ISO/experiments/t3_perf_profile_20260913.py --sample $M/artifacts/factor-engine-performance-20260913-1/sample.json \
  --universe $M/artifacts/new-factor-research-20260912-2/trial20-run/universe.json \
  --n-symbols 285 --out <out>/profile-b3.json --tag reviewfix --cprofile --cprofile-out <out>/profile-b3.cprofile.txt
# 9) 打包（只新增不覆盖；缺件/依赖更新即非零退出且不发布）
$PY -X utf8 $ISO/experiments/t3_perf_package3_20260913.py --out <批次目录>
```

**回退**：默认路径未改变 —— CPU 即默认；GPU 模块只有显式调用
（`stats_gpu.ic_decay_curve_gpu`）才生效，且失败自动回落 CPU 并记录原因。
opt-in 缓存（`--panel-cache` / `--load-memo` / `cluster_monthly_inline`）关掉即回到
P1 之前的逐次重建路径，**取值不受影响**。

---

## 9. 任务书记录

- `docs/tasks/new-factor-research-20260912.md` — 追加"实施记录：因子引擎性能优化
  A/B/C/D/E 阶段（2026-09-13，批次 `-4`）"，含 F1–F4、B/C/D 决议、全量未启动状态与
  身份纪律更正。
- `docs/tasks/ten-year-research-infrastructure-20260912.md` — 追加"共用装载/统计出口
  性能优化（T1 公共能力面，批次 `-4`）"，含共享文件改动清单与合入时 §2.1 重绑要求。

## 10. 请审核者优先回答的三个问题

1. `VERSION.md` 声明的"`-3` 等价性未覆盖 ±inf/缺失交错缺陷"是否成立（可跑
   `gpu-bench.json::rank_equivalence_adversarial` 的 10 例，或直接看
   `source/new/stats_gpu.py` 的 `_average_ranks_batch_torch` 两趟排序实现）。
2. GPU"不采用"的判据是否被**正确地**应用：是否**按实际运行配置分别**判（热点 ≥2× ∧
   计算阶段估计 ≥1.5×，同一配置同时满足）？合成面板数字是否已与真实配置计时**分开**？
   以及**跨轮方差**（同输入 1.66/2.13 × → 0.91/1.41 ×）是否被如实披露、而非挑一轮好看的？
   注意 `1.32×` 一类数字只是**计算阶段替换估计**，不是实测 CPU/GPU pipeline wall。
3. §9.3 是否还有**未覆盖**的负例类别（`checkpoint-test.json` 的"全常数、训练末尾边界"
   与 §6 的"前向收益边界不越界读 2023 标签"是我认为覆盖较弱的两处，请重点看）。


### 2026-09-13 Codex续做（当前状态：RUNNING）

D1规范路径身份修复已在12根20275文件上通过；D2测量提交改正且两轮A/B PASS_EXACT；D3/D4生成器与A侧字节交付补齐；D5负例仅改临时副本并断言复原，D6夹具不能产正式门禁。检查点31/31、身份40/40、冻结负例8/8已实测。新进程pure回退已产生pure账本，剩余默认后端反例正在运行。CPU代码仍仅在隔离仓；用户已明确允许仅提交隔离仓本次整改以冻结新快照，须等在飞身份验证结束后提交。-13和-6仍待完成，不宣称已经交付。

T3全量未启动，1430分母不变，缩样结果不是研究发现。另按用户请求T2十年信号已完成（5552证券/两策略各120月）；用户将提供分钟数据，T2四账户仍未运行，记录见对应任务书。


### 2026-09-13 新快照登记完成（性能包仍待最后打包）

隔离提交 `43dba5b6ffa1500322471bb97fe7c22c05734420`，用户明确授权仅提交隔离仓本轮整改；主仓未提交。新快照 `D:/AI/workspace/t3-snapshot-20260913-3/`，55受审文件通过 `enforce_code_identity`。新登记 `artifacts/new-factor-research-20260912-13/`：20片，1430项清单不变；`identity-verification.json` 实测启动/收尾PASS，20275文件，digest=b19006a6d4797d530137247efe970dd7ce414dc291031c8680e770ec8b512015。旧-11/-12不改写。入口保留历史顶层导入，模块命令需显式 `PYTHONPATH=<快照>/experiments`。

小样本新进程CLI 7/7（8项、40证券），同进程CLI 9/9（144项、40证券），两者run_scope=validation_fixture，不签正式门禁。另 `formal-contract-newprocess.json` 实际1430项清单的新进程numpy/pure身份/分母/配置接线2/2，哨兵在数据装载前停止，无全量求值。L0-only与cost-ladder20项输出逐位一致；跨片证据和打包负例最后串行收口。T3全量仍未运行。


### 2026-09-13 CPU整改交付终核（唯一当前状态）

CPU性能整改执行状态 DONE，审核 PASS_WITH_LIMITATIONS（限定隔离实现、交付包与新快照接线；不代表T1/T2整体完成）。交付 `artifacts/factor-engine-performance-20260913-6/`：101件摘要独立重算0差异、25件证据内容来源通过、5份diff应用后源码一致、A侧5文件字节复核一致、missing=[]。最终复核 `artifacts/ten-year-infrastructure-20260912-2/performance-package-review.json`，包manifest SHA256 `6b33b880b048e65c6ecb7725af9d3f7c8466909661cf63b8fdb0bdeb8c9ea810`。

D1规范化修复实测12根20275文件mixed/canonical/repeat/verify通过；历史清单口径不再沿用且旧工件不改写。D2真实B测量提交12c5c0d54d3b2b1079dcb8676c5cb134f5088c76，机械diff证明测量路径未变，A/B两轮PASS_EXACT、0差异。D3新生成器随包交付；D4双侧SHA与A字节齐全；D5临时副本变异、mtime回拨仍拒绝且复原SHA相等、真实核心源码未动；D6夹具禁止正式gate，另真实1430清单新进程接线2/2且在装载前停止。

最终测试：身份40/40、检查点31/31、同进程CLI9/9（40股/144项）、新进程CLI7/7（40股/8项）、冻结负例8/8、打包负例6/6；L0-only20项逐位等价、跨片6文件及run_meta一致。CPU原A/B样本装载55.190/55.934s→41.134/41.122s（1.34–1.36倍），求值9.083/9.109s→8.757/8.705s（1.037–1.046倍），不是全池wall测量。GPU保留原型、不采用，未外推全池。

用户授权隔离提交已执行：运行源码43dba5b6ffa1500322471bb97fe7c22c05734420，打包器字段修复ac669ef（仅交付工具）；新快照 `D:/AI/workspace/t3-snapshot-20260913-3/` 保持43dba5b6，55受审文件干净校验通过。新批 `artifacts/new-factor-research-20260912-13/` 的启动/收尾原始数据核验PASS，20片/1430分母不变；未运行全量。模块命令需 `PYTHONPATH=<快照>/experiments`，pure回退显式 `--backend pure` 且新输出根。主仓性能源码未覆盖、主仓未提交，不能整仓覆盖较新的T1修复。

T1整体仍未完成：A DONE、B WAITING_REVIEW、C RUNNING；T2-A DONE、B BLOCKED、C PENDING。十年信号5552只、两策略各120月完成并审核，旧窗口信号回归与重叠选股/权重/日期一致；用户将提供分钟数据，四账户未启动，2015–2019缺口保持，不用日线替代。统计UNKNOWN、晋级BLOCK、2025+/生产冻结。下一步只接收分钟数据并推进实际订单依赖及四账户；T3全量取消状态未改变。

保留本轮失败记录：首次CLI批检查点旧正式gate断言与stdout格式失败，修后31/31；首次打包缺GNU工具已改difflib/git apply；正式打包旧mtime汇总字段KeyError已在ac669ef修复。预检临时目录清理被自动策略拒绝（blocked by policy），未再删除；失败staging不是交付，只有带manifest且经上述终核的-6是正式包。
