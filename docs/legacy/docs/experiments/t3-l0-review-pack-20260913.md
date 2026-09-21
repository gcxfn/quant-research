# T3 L0 交代材料包（2026-09-13）

**一句话状态**：任务三「大规模分层因子挖掘」的 L0 事前登记已完成并冻结为
`artifacts/new-factor-research-20260912-3/`（**1456 个构造**＝R1池继承 213 + 新目录 1243），
20 行合规试跑正在跑，全量 L0 批跑等试跑结果后启动；另有一批 wave3 推理挖掘的原始池
（520 行）待走登记。本文是"我做了什么"的交代材料，供你直接看，不依赖任何子代理审核。

配对任务书：`docs/tasks/new-factor-research-20260912.md`（执行）、
`docs/tasks/new-factor-research-review-20260912.md`（审核）。

---

## 1. 我做了什么（按工作块）

### 1.1 摸底：先弄清能复用什么（不重写平台）
- 盘出既有资产：`factor_miner` 的编译器/校验器/统计/回测、R0 已处置 248 项、
  **R1 池 215 行（从未评估）**、20 条封存死区、L1 成本账户与费用模块已存在但属未提交状态。
- 关键发现（决定了后面所有设计）：月末截面 RankIC 是 **Spearman**，
  因此**单调变换**（LOG/CS_RANK 包一层）与**全截面共同缩放**（市场级序列做乘子/分母/
  加减项）都不产生新信息；窗口哈希按出现顺序归一化，`evaluation_units` 会把同哈希组内
  每个不同窗口公式各展开成一个求值单元——所以"参数变体"能被逐个求值并逐个计数。

### 1.2 写枚举器，产出 wave1 目录
- `experiments/t3_enumerate_20260912.py`：模板目录（事前冻结在源码里）→ 参数枚举 →
  复用 `validator` 六条校验 → 哈希去重 → 家族/模板配额 → 20×≤100 分片 → 登记工件。
- wave1 目录 98 个模板，覆盖动量反转/波动/流动性/隔夜日内/估值/规模/资金流/联动/
  价格路径/量能动态/筹码成本/交互等机制。

### 1.3 按你的指令扩目录（wave2）
- `experiments/t3_catalog_wave2_20260913.py`：新增 **4 个机制家族**（SHAPE 分布形状、
  TREND 趋势质量、VOLCOND 个股级量能条件化、CANDLE K线形态）+ 对 11 族做信息结构扩容
  （跳空、波动分解与期限结构、贝塔分解、VWAP 均价、估值动态与质量比、规模-流动性-杠杆
  交互、截面秩交互、多窗一致、加权成本锚）。
- 同时**剔除伪构造**并写进登记：市场级序列当乘子/分母（当月秩不变）、倒数对、
  单调包裹、龙虎榜稀疏字段的窗口聚合（全窗非None才输出→实际全None，删了24条）。

### 1.4 生成首版登记包（-2）
- `artifacts/new-factor-research-20260912-2/`：**1482 行**（继承 215 + 新增 1267）、
  201 模板、17 家族、20 片；`preregistration.json` 冻结门槛（|月RankIC|≥0.02、
  月块 bootstrap B=10000/块3/种子20260909、Bonferroni n_tests=求值单元数、方向一致）、
  股票池（engine 冻结 5552 只含 337 退市 + P1 时点池）、标签（下一月末总收益）、
  L1/L2 口径、4 个 BLOCKED 家族（事件路径未解锁 / 无 PIT 财务字段 / 公式层不可表达市场状态条件化）。

### 1.5 试跑 20 行（真实数据）
- 抽 20 行（跨字段类确定性抽样：11 新目录 + 9 继承），快照内跑通：
  **20/20 单元、P8=17 / P9=3、35 个有效月 IC、约 24 分钟、峰值内存约 4.9GB**，
  新目录构造 `T3-LIQ-LQ12-w005`（VWAP 溢价）过门。批次 id `R0TRAIN-20260913_011620`。

### 1.6 启动 L0 全量分片批跑，随后停止
- 方案：清单按 candidate_id 稳定序切 20 片、每片独占输出目录、完成片跳过（可续跑），
  因为管道没有逐单元异常隔离、没有断点。预计约 17 小时。
- 修好运行身份：HEAD `f32568f` 不含未提交的
  `descriptive_contract.py`/`r0_audited_runner.py`/`fixed_capital_portfolio.py`
  等受审文件，而 R0/T2 已验收证据基于该工作树状态 → 按"运行中固定代码快照"把当前状态
  复制成 `t3-snapshot-20260913`（快照内提交 `d119444c`），**主仓分支与工作树未改动**。
- 批跑在首片（约 50 分钟）**被停止**——原因见 §1.7。停止时零工件产出、未读取任何筛选收益。

### 1.7 独立审核发现阻断缺陷
- 审核裁决 CHANGES_REQUIRED（报告 `-2/review-registration.md`），我逐项独立复现：
  - **A1（阻断）**：wave2 的 XT06/XT07/XT08 变体 tag 我都写成了 `now` → **23 行重复
    candidate_id**（1482 行只有 1462 唯一 id）；管道会在**全部单元算完之后**触发
    fail-closed 槽位守卫并抛错，且不留工件 → 等于 17 小时白跑。
  - **B1**：`MR04`（`RET − MEAN(market_ret,w)`）9 行是秩不变填充——我原来的规则只挡了
    市场级序列的乘除，漏了**加性偏移**。
  - **B2**：字符串精确去重漏掉 canonical+窗口真重复 10 组，另有 15 行与 R0/R1 已评估
    公式语义相同（其中 7 条是 R0 判过 GATE_FAIL 的公式换窗口重测、未披露）。
  - **B3**：登记的"有效月<24→P5"与"年度方向一致性"代码里没实现。
  - **B4**：分片执行会让 Bonferroni 分母降到约 75/片，与登记的全清单口径不同。

### 1.8 整改（R1–R5）并重登记为 -3
| 项 | 措施 | 证据 |
|---|---|---|
| R1 | XT06/07/08 变体 tag 改参数签名；生成期加断言：id 唯一、`canonical+有序窗口值`唯一 | 真实管道回归：`director.dedup → director.evaluation_units` = **1456 单元 / 1456 唯一槽位 / 0 冲突**（修复前 1477/5 冲突） |
| R2 | 删除 MR04 整模板（9 行）；设计规则补"市场级序列的加性偏移同样不改秩" | MR04 已不存在；规则文本在 `-3/preregistration.json::design_rules` |
| R3 | 去重键升级为 `compiler.canonical + 有序窗口值`，对先验语料与批内同口径 | 剔除 **23 条**（22 条与先验/R1同义、1 条批内同义），含 7 条 R0 FAIL 重测；继承行自查后 215→213 |
| R4 | 汇总层实现：有效月<24 → `P5_STAT_INSUFFICIENT`；年度方向一致性（≥2/3 年同向） | `experiments/t3_l0_batch_20260913.py::aggregate` 新增 `coverage`/`annual_direction`/`disposition_registered` |
| R5 | 登记明示：分片内 n_tests 仅描述性，正式门槛＝全清单 n_tests 由汇总层重算；aggregate 声明送审 | `-3/preregistration.json::gate_L0.slice_n_tests_disclosure`、`run_plan.aggregate_script` |

- 顺带抓到并修了我自己的一个 bug：aggregate 原来读 `monthly_ic`，而管道落库字段是
  **`train_monthly_ic`** —— 不修的话门槛重算会拿到空 IC 序列（整套门槛失效）。
- 整改后清单 **1456 行 = 继承 213 + 新增 1243**，200 模板，20 片（73×19 + 69）。

### 1.9 wave3 推理挖掘（按你"随便挖但要做好登记"）
- 派 4 个代理各产 130 行原始池（时序状态转移 / 量价微观结构 / 估值质量交互 /
  尾部与个股级条件化），落在 `artifacts/t3-wave3-llm-raw/researcher_*.jsonl`。
- 我的独立机器复核（全量非抽样）：4×130 行**全部**通过 `validator.validate` 与
  required_fields 一致性；与先验语料（1730 精确公式 / 696 结构）**精确与归一化结构双零碰撞**；
  结构数 31/80/79/42；无单目负号/科学计数/稀疏字段窗口聚合；市场级序列仅出现在
  CORR 内（12 行，合规）。
- 我写了秩等价检测器 `experiments/t3_synonym_check_20260913.py`（合成面板上比较截面秩，
  专门抓"乘个常数/换个窗口"的伪新结构）。**初版有假阳性**：我给的 `market_ret` 是价位量级
  而非收益率，含市场序列的公式在合成面板上退化成常数 → 恒定秩误判为同义；已加入
  真实收益量级的市场序列 + 截面方差守卫并重跑（结果出来后用于 wave3 登记）。

### 1.10 文档
- 本材料包（`docs/experiments/t3-l0-review-pack-20260913.md`）。
- GPU 因子引擎建设计划包（提案、未启动）：`docs/plans/gpu-factor-engine-plan-20260913.md`
  —— 结论：本 workload 瓶颈是内存与单核串行，GPU 端到端收益需先做**列式 bundle**，
  否则会重蹈 numpy v1"比纯 Python 还慢"；估算 3–4 周（含等价性审计），近期更划算的是
  云 CPU 大内存多核（1–2 小时、零代码改动）。

## 2. 现在可核验的事实

| 项 | 值 |
|---|---|
| 当前清单 | `artifacts/new-factor-research-20260912-3/hypotheses.jsonl` = **1456 行**，sha256 `0c5efe0dc15419f0…` |
| 事前登记 | `-3/preregistration.json` sha256 `f4227ee4df61ee6a…` |
| 模板目录 | `-3/catalog.json`（200 模板）sha256 `5265daf03806f5fc…` |
| 候选总表 | `-3/candidates.csv` sha256 `b6ab9fa11b9ad28b…` |
| 枚举报告 | `-3/enumeration_report.json` sha256 `a347ebceeb45021b…` |
| 家族分布 | VOL 181 / CORR 165 / LIQ 137 / OVERNIGHT 115 / FLOW 101 / VALUE 96 / MOMREV 95 / VOLCOND 90 / PATH 87 / COST 75 / CANDLE 68 / TREND 63 / VOLDYN 57 / SIZE 40 / XINTER 40 / SHAPE 31 / R1-STATE 15 |
| 分片 | 20 片（73×19 + 69），按 candidate_id 稳定序 |
| 运行身份 | 快照 `t3-snapshot-20260913`@`d119444c`（54 受审文件 sha256 见 `-3/snapshot_manifest.json`） |
| 首版登记（已取代） | `-2/`：1482 行，`hypotheses.jsonl` `fb9143cd3fede45c…`；试跑批次 `R0TRAIN-20260913_011620`（20/20） |
| 目标缺口 | 2000 − 1456 = **544**（原因：算子白名单 v1 + 字段表无 PIT 财务成长/投资字段、事件路径未解锁、同义纪律不做凑数、固定月频标签、单家族≤400/单模板≤10上限） |

## 3. 改动/新增的文件

**代码（均在 `experiments/`）**：`t3_enumerate_20260912.py`（枚举器，含目录与断言）、
`t3_catalog_wave2_20260913.py`（wave2 目录）、`t3_l0_batch_20260913.py`（分片批跑 + 汇总层）、
`t3_synonym_check_20260913.py`（秩等价检测器）。
**文档**：本材料包、`docs/plans/gpu-factor-engine-plan-20260913.md`、
`docs/tasks/new-factor-research-20260912.md`（进度表更新）。
**工件**：`artifacts/new-factor-research-20260912-1/`（首版，被取代，保留）、
`-2/`（首版登记，被取代，保留，含审核报告）、`-3/`（当前登记包）、
`artifacts/t3-wave3-llm-raw/`（wave3 原始池 + 我的复核 JSON）。
**未改动**：主仓 git 分支与工作树（快照在独立目录内提交）；54 个受审代码文件未改。

## 4. 未完成与下一步

1. **合规试跑（-3，20 行）**：正在跑（约 25 分钟量级）。跑完核对 20/20 与分类计数。
2. **L0 全量批跑**：试跑通过后启动（20 片、预计约 17 小时；可选把调度改成 4 组×约 365 行
   以省约 3.5 小时 bundle 重建，属调度修正、不改清单与门槛，需要你点头）。
3. **wave3 登记（R6）**：等秩等价重跑结果，剔除同义项并把 id/去重键纪律套上后，
   作为独立子轮登记（不与 -3 混算）。
4. **L1 成本账户 / L2 分钟回测**：按你的决定等 T1/T2 能力就绪后再启动（任务书 T3-C 标 BLOCKED）。
5. **结果交付**：L0 批跑结束后我会出通过集合与完整负证据（含未通过/数据不足的逐条依据）。

## 5. 如实说明（包含我做得不好的地方）

- **流程偏差**：这一轮实际是"冻结 → 试跑 → 启动全量 → 才做独立审核"。按纪律应是
  "冻结 → 审核 → 跑"。门槛与清单确实在看收益之前冻结（没有事后调参），但审核后置导致
  一次本可避免的批跑启动；A1 若没被审核拦下，代价是整批算完才崩（约 17 小时白跑）。
  我已经把整改前移（R1 的唯一性断言现在在生成期就拦），后续批次改成先审后跑。
- **我自己的两个错误**：XT 模板变体 tag 重名（阻断项 A1）；汇总层字段名读错
  （`monthly_ic` vs `train_monthly_ic`）。两者都已修并留下回归检查。
- **目标没到 2000**：只到 1456。缺口 544 的原因见上表；我没有用同义公式或换窗口去凑数，
  这一点我建议保留——宁可少而实。
- **继承行的性质**：R1 池 215 行此前从未被评估过（不是失败项），本轮吸收其 213 个
  互异结构（2 条内部语义重复已剔），标签期限统一冻结为 20 会话。
- **稀疏字段限制**：龙虎榜两个字段只在少数日期有值，窗口聚合必然输出全 None，
  因此只能用逐点元素形态，跨截面有效样本数偏少（已在家族失败模式披露）。
- **未跑任何收益结论**：目前所有 L0 数字只有试跑 20 行的门槛记录（且是未校准的
  GATE_PASS_UNCALIBRATED），**不能当作因子有效性结论**；统计仍按 UNKNOWN、晋级 BLOCK 处理。
- **子代理审核已按你的要求停用**：本材料由我自己写，不含第三方复核意见；
  如需再引入复核，说一声即可。

## 6. 复现命令

```bash
# 1) 生成当前登记包（幂等；只新增不覆盖）
python experiments/t3_enumerate_20260912.py --out artifacts/new-factor-research-20260912-3

# 2) 槽位唯一性回归（真实管道函数）
python - <<'PY'
import json,sys,collections; sys.path.insert(0,'experiments'); sys.path.insert(0,'.')
from factor_miner import director, validator
rows=[json.loads(l) for l in open("artifacts/new-factor-research-20260912-3/hypotheses.jsonl",encoding="utf-8") if l.strip()]
acc=[h for h in rows if validator.validate(h)["ok"]]
merged,_=director.dedup(acc)
units,_=director.evaluation_units(merged, source_meta=director.source_meta_from_rows(acc))
ids=[u[3]["execution_unit_id"] for u in units]
print(len(ids), len(set(ids)), "collisions:", len(ids)-len(set(ids)))
PY

# 3) 合规试跑（快照内执行）
FACTOR_MINER_NUMPY=1 python -m experiments.factor_miner.director pipeline \
  --hypotheses artifacts/new-factor-research-20260912-3/hypotheses-trial20.jsonl \
  --out artifacts/new-factor-research-20260912-3/trial20-run --allow-real-run

# 4) L0 全量分片 + 汇总（试跑通过后）
python experiments/t3_l0_batch_20260913.py run \
  --roster-dir artifacts/new-factor-research-20260912-3 \
  --out-root artifacts/new-factor-research-20260912-3/l0
python experiments/t3_l0_batch_20260913.py aggregate \
  --roster-dir artifacts/new-factor-research-20260912-3 \
  --out-root artifacts/new-factor-research-20260912-3/l0

# 5) 秩等价（同义构造）检测
python experiments/t3_synonym_check_20260913.py --pool <pool.jsonl> --corpus --report <out.json>
```

---

## 11. 主审 CHANGES_REQUIRED（F1–F7）整改执行记录（2026-09-13，执行者：本对话）

主审报告：`artifacts/new-factor-research-20260912-3/review-new-factors.md`（另一侧主对话，
直接核代码与负例、未派子代理、未重启真实收益计算）。整改后**重登记为**
`artifacts/new-factor-research-20260912-5/`（`-1`…`-4` 保留不删；`-5/SUPERSEDES.json`
记录取代关系）。

### 11.1 清单侧整改（F2/F3/F7）

| 项 | 措施 | 机器证据 |
|---|---|---|
| **F7 方向身份（P1）** | 同归一化结构组内方向统一：对少数派方向的行把符号移入公式（`0 - (原式)`，canonical 变化→独立结构组）并同步翻转方向，**假设等价**（V 与方向 D ≡ −V 与方向 opposite(D)）；生成期断言"任何结构组不得出现混合方向" | 移号 **38 行**；`director.dedup→evaluation_units` 后 `source_direction≠adopted_direction` 的单元数＝**0**（整改前分片内 13 行、整批 38 行错向） |
| **F2 空条件 IF（P1）** | 生成期审计：抽取全部 `IF` 的第一参数，在合成面板上求值，条件**恒非零/恒零**即判空条件（IF 语义＝非零取第一分支）；空条件行移入技术修复队列，不进入本轮求值 | 剔除 **7 条**继承行（`UVOL_pressure_ratio`/`flow_stab_gap`/`dir_vol_shock`/`maxdom_asym`/`surrender`/`flow_mkt_coupling`/`bigvol_purity`）；新目录 `CD05/CD06` 条件改为**指示式加权**（`(high−open)·(1+SIGN(open−close))/2 + (high−close)·(1−SIGN(open−close))/2` 等），不再依赖 IF；`SH05/SH07`（`IF(close−MAX(close,w),0,1)`）经核为**正确**用法（新高日条件为0→取第二分支） |
| **F3 互补重复（P1）** | 删除 `VC02`（下跌量占比 = 1 − VC01）与 `GP03`（同向占比 = 1 − GP02）共 **18 行**；方向与保留映射见 `-5/enumeration_report.json`（`VC01`/`GP02` 保留，方向各自与互补项相反） | 两族构造数 VC 9→…、GP 各减 9；F2 修正后 `CD05/CD06` 与 `CD02/CD03` 不再是同一表达式 |

**旧声明纠正**：此前"目录不含 IF、无单目负号"的说法不成立——wave2 早期模板含 IF
（已修），`SH05/SH07` 与继承行的指示式 IF 保留（合法）；单目负号仍未使用（符号一律用
`0 - (…)` 表达）。此前"两次 trial20 共 40 个构造"的说法也不准确：两次是**同 20 个构造**
（第二次为技术重跑），另有 1436 条在取消前无完成结果。

### 11.2 运行与汇总侧整改（F1/F4/F5/F6）

`experiments/t3_l0_batch_20260913.py` 重写：

- **F1 分母与身份**：`aggregate` 的分母由**冻结清单派生**（对清单做 validate→dedup→
  evaluation_units 展开得权威单元身份集），不再由结果行数决定；结果须与权威身份集
  逐单元相等（factor_id/公式/方向/窗口），缺失片→`PARTIAL`（只发布部分进度、
  `full_pass_set_published=false`），重复/未登记/错身份→`IDENTITY_ERROR` 并非零退出。
- **F4 资格口径**：分离 `ic_gate_pass` / `coverage_ok` / `data_ok` / `eligible_L1`；
  有效月＝2020–2022 内**有限且唯一**的月；越界月份/重复月份/非法 IC→`DATA_ANOMALY`
  （不进 P8 策略失败）；年度不一致单列 `annual_pause_L1`；输出 JSON 无 NaN。
- **F5 完成与续跑**：完成＝状态成功 ∧ 单元数一致 ∧ 身份一致；失败/中断保留旧工件、
  在**新 attempt 目录**续跑并记映射；日志追加不覆盖；`subprocess` 带 `--timeout-sec`
  （默认 48h）；任一片失败→进程非零退出，台账 `complete` 不为真。
- **F6 运行身份**：新增 `identity` 子命令与 `run-identity.json`（T3 四脚本在快照与主仓的
  sha256 + 清单/目录/登记/配置/数据清单摘要），`run`/`aggregate` 启动即校验；
  旧 prereg 中"按 HEAD f32568f 运行 + audited_runner + 49h/超时48h"的表述已改为
  **实际入口**（快照内分片直调 director + 48h/片超时 + 单进程 + 峰值约5–6GB）。

**负例回归**（`-4/runner-negative-tests.py`，输出 `-4/runner-negative-tests.json`）：
| 负例 | 期望 | 实测 |
|---|---|---|
| 完全无结果（缺全部片） | PARTIAL、分母仍为全清单、不发布完整通过集合 | rc=3，`n_tests_registered=1431`、`n_missing=1431`、`full_pass_set_published=false` ✓ |
| 混入未登记单元 | 拒绝、非零退出 | rc=2、`IDENTITY_ERROR`、无通过集合 ✓ |
| 同一单元重复 | 拒绝 | rc=2、`duplicate_unit` ✓ |
| 2023 月份 + NaN IC | 数据异常（不得进 P8）、无 NaN 字面量 | `DATA_ANOMALY`、`month_out_of_range:2023-01`+`invalid_ic`、`eligible_L1=false`、文件中无 `NaN` ✓ |
| 片状态 FAILED | 不得记完成 | `_slice_done`→False（`status=FAILED`）✓ |

### 11.3 当前冻结身份（-5）

| 工件 | sha256（前16） |
|---|---|
| `hypotheses.jsonl`（1431 行 = 继承 206 + 新增 1225） | `ae9181f110723381` |
| `preregistration.json` | `0ba02b8bd30592d7` |
| `catalog.json`（198 模板） | `3de4bdfbd2db6e6d` |
| `candidates.csv` | `1d7f7822df54c967` |
| `run-identity.json` | `8b8d0f50058fb9d5` |

家族：VOL 174 / CORR 165 / LIQ 137 / OVERNIGHT 106 / FLOW 101 / VALUE 96 / MOMREV 95 /
VOLCOND 81 / PATH 87 / COST 75 / CANDLE 68 / TREND 63 / VOLDYN 57 / SIZE 40 / XINTER 40 /
SHAPE 31 / R1-STATE 15；20 片；槽位回归 **1431 单元 / 1431 唯一 / 0 冲突**。
`-5` 尚未跑试跑（20 行试跑沿用 `-3` 的 `R0TRAIN-20260913_030908`，其 20 行在 `-5` 中的
方向/公式身份未变，但按纪律应以 `-5` 重跑一次试跑后再启动全量）。

### 11.4 仍未闭环

- **wave3**：520 行仍为原始池；秩等价检测（修正假阳性后）标出 14 条匹配记录/13 个候选
  需逐条裁决（有限面板同秩≠代数恒等），且其 IF 误用同样存在；须另行登记，PENDING。
- **试跑与全量**：`-5` 的试跑与全量批跑**均未启动**（用户已取消全量；本记录不恢复运行）。
- **L1/L2**：等 T1/T2 能力就绪，维持 BLOCKED。

---

## 12. 主审第二轮（R1–R5）整改执行记录（2026-09-13）

主审复审报告：`artifacts/new-factor-research-20260912-5/review-new-factors.md`
（裁决 CHANGES_REQUIRED，R1–R5）。整改后**重登记为**
`artifacts/new-factor-research-20260912-8/`（`-1`…`-7` 保留不删）。
-8 冻结身份：`hypotheses.jsonl` `6af8d4b8ae013ed0`（**1430 行 = 继承 205 + 新增 1225**，
20 片 72×19+62）、`preregistration.json` `5322aaa89af69c9e`、
`catalog.json` `3de4bdfbd2db6e6d`、`candidates.csv` `879a14f77d0e8fbc`、
`enumeration_report.json` `20b5aea93ab1bb75`、`run-identity.json` `544406171c9c4b92`。

| 项 | 根因（主审认定） | 整改 | 机器验证 |
|---|---|---|---|
| **R1（P1）** | 我的 `expected_units` 用合并组**首行公式**与**整批 dedup 槽位 ID** 作权威身份，实际落库是 lineage 公式、逐片 dedup 槽位 → 正常结果被拒（主审实测：1431 中 456 接受 / 869 公式不符 / 106 未登记） | 身份改为**与分组无关**：key=`canonical_eval_key`（canonical+有序窗口值），预期公式/窗口取清单行自身；`_slice_check` 与 aggregate 同口径 | `-8/normal-path-test.py`：按 director 落库格式造逐片完整结果 → **1430/1430 接受、COMPLETE、0 身份错误、rc=0** |
| **R2（P1）** | `_slice_done` 只看状态与计数；成功 attempt 不被复用/汇总；无结果的成功状态也算完成 | `slice-attempts.json` 片→有效 attempt 映射；`_slice_check`＝状态成功 ∧ 单元数一致 ∧ candidates 齐全 ∧ 身份一致；run 复用、aggregate 按映射（或扫描）读取 | 负例 N8（原目录无效+attempt1 有效）→ COMPLETE/1430；N7（状态 FAILED）→ PARTIAL、该片 72 单元 NOT_RUN、rc=3 |
| **R3（P1）** | 分片文件未入身份；数据清单摘要只写不校；manifest 快照与运行 cwd 未比较；汇总不核 run_meta/代码/数据/窗口 | `run-identity.json` 绑定 20 分片（逐文件+并集）、快照路径与提交、数据清单摘要、期望 `code_commit`/`data_version`（取自参考 run_meta）、月末轴；结果行须匹配窗口/方向/代码/数据 | 负例 N4（窗口/代码/方向篡改）→ 显式拒绝；N9（改分片文件）→ 拒绝运行；N2（未登记键）、N3（跨片重复）→ `slice_invalid`/`unregistered_key`/`duplicate_unit` 拒绝 |
| **R4（P1）** | `UVOL_bigvol_purity` 的 `SIGN(TS_RANK(volume,20)-0.8)` 被当"非零为真"→ 低量日也算入 | 新增**比较式 IF** 规则检测（`SIGN(expr±常数)`，排除合法指示式 `0.5*(1±SIGN(x))`）；该行入技术修复队列 | IF 误用排除合计 **8 条**（7 条恒真 + 1 条比较式）；生成期断言不得残留 |
| **R5（P2）** | 有效月只按完整日期串去重，同月多日可补足覆盖 | 有效月＝**交易日历派生的月末轴**（36 个月末）内、按 YYYY-MM 唯一、升序；同月多日不计 | 负例 N6（20-01-01…12 + 21-01-01…12）→ `valid_months=0`、DATA_ANOMALY、`eligible_L1=false` |

**测试顺带发现的真 bug（已修）**：`aggregate` 原会读取"状态 FAILED 但目录里有
candidates"的片子（等于把失败当完成）；现只接受通过 `_slice_check` 的成功 attempt，
且片级完整性违规（身份/计数不符）会显式报 `slice_invalid` 并非零退出。

**文档更正（本轮）**：① 此前把 `UVOL_bigvol_purity` 写成"已排除"有误——本轮才排除
（另 7 条恒真条件为 pressure_ratio/flow_stab_gap/dir_vol_shock/maxdom_asym/surrender/
flow_mkt_coupling/bucket_coupling）；② 分片尺寸是 **72×19+62**（此前 SUBMISSION 写的
73×19+69 是旧版本）；③ prereg 与设计规则中"目录不含 IF"的旧声明已改为"IF 仅限指示式
0.5*(1±SIGN(x)) 或窗口恒零条件，恒零/恒非零与比较式由生成期审计剔除"；
④ 目录保留移号前的模板原式，**执行权威＝清单 `hypotheses.jsonl` 的最终式**
（`enumeration_report.json::audit_F7_direction.fixes` 给出原式→最终式映射）。

**本轮未闭环**：`-8` 未跑真实试跑；全量维持用户取消；wave3 未登记（13–14 条同秩记录
待逐条裁决）；L1/L2 BLOCKED。

---

## 13. 主审第三轮（S1–S3）整改执行记录（2026-09-13）

主审对 `-8` 的复审报告：`artifacts/new-factor-research-20260912-8/review-new-factors.md`
（裁决 CHANGES_REQUIRED，S1–S3；随后发现并行修改导致脚本摘要漂移，属正常迭代）。
整改后**重登记为 `artifacts/new-factor-research-20260912-11/`**：
`hypotheses.jsonl` `6af8d4b8ae013ed0`（1430 行，20 片 72×19+62）、
`run-identity.json` `eb5dd2b07f947647`、`normal-path-test.json` `2224ac94c9effb6c`、
`negative-tests.json` `9e8c0f81614f42b0`。

| 项 | 根因 | 整改 | 负例证据（-11） |
|---|---|---|---|
| S1a 公式 | 只信结果自报的 key，未核公式 | 公式必须等于登记公式；**用结果自身公式重算 canonical+窗口键**并与自报键比对 | N10 改公式（保留键）→ `identity:formula` 拒绝 |
| S1b 实际方向 | 优先用 source_direction，未核 adopted | `adopted_direction` 必须存在且等于登记方向 | N11 → `adopted_direction negative != positive` 拒绝 |
| S1c 运行元数据 | 完成检查不核 run_meta | 要求 run_meta 存在且 `code_commit`/`data_version`/`n_candidates`/`n_train_tested` 与期望一致 | N15 删除 → 片 NOT_RUN；N16 篡改 → `slice_invalid` |
| S2a 集合 | 片完成只看状态与数量 | **该片预期键集合精确相等**（重复+缺项即拒） | N12 片内重复替换（数量不变）→ 键集合不等拒绝 |
| S2b 中断恢复 | run 只查映射与原目录；新编号只看映射 | run/aggregate 共用发现逻辑（映射 + 磁盘现存 attempt）；新编号**避开磁盘已存在目录** | N14 占用 attempt1 且无映射 → 选 attempt2；N8 常规映射 → 复用成功 |
| S3 标签成熟 | 月末在轴内即计入 | identity 记录 `immature_month_ends`；末月非空 IC → 数据异常、不计覆盖/门槛 | N13 末月填 IC → `immature_label_has_ic:2022-12-30`、eligible=false |

**过程中我自己踩的坑（如实记录）**：为修 S1 引入的 `_key_of` 助手因补丁顺序被覆盖，
导致 -10 直接 NameError；已修并定版 -11。这也说明"改脚本→身份失效→新版本送审"的
链条是有效的（-8 复审自己也观察到该漂移）。

**未闭环**：`-11` 无真实试跑；全量维持用户取消；wave3 未登记；L1/L2 BLOCKED。
