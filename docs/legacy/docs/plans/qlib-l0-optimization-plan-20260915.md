# Qlib 原生 T3 L0 初筛性能与稳定性改造计划

日期：2026-09-15  
适用范围：T3 L0，2020–2022 训练期，2018–2019 仅作预热  
目标入口：`qlib_research/`  
执行边界：只做 Qlib 原生因子求值、月度 RankIC 和 L0 门禁；不启动 L1 成本账户、L2 分钟回测或十年路径。

## 1. 目标和结论

本计划解决当前 Qlib L0 在 2000 个候选、约 5002 只股票、日频 2018–2022 数据上的两个问题：

1. 16 个进程并发时内存和页面文件耗尽，系统出现“页面文件太小，无法完成操作”。
2. Qlib 进程长期停留在 `FileFeatureStorage`、`Path.glob`、`Path.exists`、`Corr` 和表达式加载阶段，批次没有中间进度，无法判断实际完成量和剩余时间。

最终目标是：

- 对冻结的 2000 个 Qlib 原生表达式完成一次真实 L0 初筛；
- 正式运行的内存峰值保持在机器物理内存的安全范围内；
- 通过可观测 checkpoint 明确报告候选、分片和批次进度；
- 在当前机器上把完整 L0 运行控制在 1 小时内；
- 如果基准证明 1 小时不可达，必须在正式全量前报告 `PERFORMANCE_BLOCKED`，不能靠降低候选数、缩短股票池、改月数或复用旧 RankIC 结果制造“完成”。

L0 完成的判定仍然是 2000 个登记候选均有明确处置：`L0_PASS`、`L0_REJECTED`、`P5_STAT_INSUFFICIENT` 或 `BLOCKED_MISSING_FIELD`。不能把未运行、被杀进程或超时候选写成失败。

## 2. 当前证据和问题定位

### 2.1 已确认的现象

当前入口为 `qlib_research/l0_2000.py`。它的基本流程是：

```text
读取公式源
→ qlib.init
→ 读取全市场 close/eligible
→ D.features 批量求表达式
→ 截取月末
→ 计算月度 RankIC
→ checkpoint
→ finalize 门禁和 bootstrap
```

已完成的实测包括：

| 场景 | 实测结果 | 解释 |
|---|---:|---|
| 1 因子、约 5002 只股票、分块月末读取 | 约 41 秒 | 分块读取路径可工作 |
| 10 因子、约 5002 只股票 | 175 秒 | Qlib 原生求值仍然较重 |
| 100 因子、约 5002 只股票 | 1173 秒 | 单进程约 19.6 分钟 |
| 16 进程、全日线全池矩阵 | 页面文件耗尽 | 不能继续使用 |
| 16 进程、股票分块但 125 因子批量 | 首批长期无 checkpoint | 文件扫描和 Qlib 表达式求值争用严重 |

### 2.2 `py-spy` 证据

抽样栈集中在：

```text
qlib.data.storage.file_storage.FileFeatureStorage.__getitem__
qlib.data.ops._load_internal
qlib.data.ops.Corr._load_internal
qlib.data.data.features
qlib_research.l0_2000.load_part
qlib_research.l0_2000.load_feats
```

部分进程停留在：

```text
pathlib.Path.glob
pathlib.Path.exists
pathlib.Path.is_dir
pathlib.Path.parse_parts
```

这说明主要瓶颈不是 RankIC、bootstrap 或 CSV 导出，而是 Qlib provider 的重复文件定位、bin 读取和表达式求值。

### 2.3 不能采用的做法

- 不再使用 16 个进程同时扫描同一个 Qlib provider。
- 不把旧 `-6c` 的 `selection.csv`、RankIC 或 summary 复制到新批次充当新计算结果。
- 不把 Qlib `Rank(x, n)` 冒充横截面 `CS_RANK`。
- 不用旧自研引擎、VectorBT 或 NumPy 账户结果替代 Qlib L0。
- 不通过缩小股票池、减少因子、删除难因子或缩短训练区间满足一小时目标。
- 不在正式运行期间根据已出结果临时改门槛、改公式或重新生成后续候选。

## 3. 冻结输入和身份要求

优化前先建立新的运行身份，不修改历史批次。

### 3.1 输入身份

运行身份必须绑定：

- 公式源文件及 SHA256；
- 2000 个候选 ID 的顺序和唯一性；
- Qlib 表达式版本及冻结表达式文本；
- Qlib 版本和 Python 环境；
- provider 路径、provider manifest 和字段摘要；
- 股票池文件及股票数；
- 交易日历、预热区间和评估区间；
- L0 门禁配置、bootstrap 种子和版本；
- worker 数、股票块大小、表达式批大小；
- 代码快照摘要。

推荐身份文件：

```text
artifacts/qlib-native-l0-<date>-<run>/run-identity.json
```

### 3.2 日期和标签

- 原始读取范围：2018-01-01 至 2022-12-31；
- 评估信号范围：2020-01-01 至 2022-11 月末；
- 2022-12 月末因下月标签未成熟而不参与 IC；
- 月末轴必须由 Qlib 日历生成；
- 因子值在月末截面取值；
- 标签为下一成熟月的 Qlib 收益标签；
- 预热数据不能计入 IC 月数；
- 不读取 2025 年以后数据。

### 3.3 `CS_RANK` 处理

含 `CS_RANK` 的候选必须单独登记为阶段化 Qlib 处理：

```text
日频原始表达式求值
→ 按日期做横截面 CSRankNorm
→ 再进入后续表达式或月末截面
```

如果当前 Qlib 入口无法表达某个嵌套 `CS_RANK`，该候选必须输出：

```text
BLOCKED_UNSUPPORTED_CSRANK
```

不能把它静默替换为时序 `Rank`。阶段化实现完成前，这些候选不能进入正式 L0 门禁；它们的数量和原因必须计入最终汇总。

## 4. 目标架构

### 4.1 总体流程

```text
冻结输入和身份
        │
        ▼
provider 索引预扫描
        │
        ▼
Qlib provider 元数据缓存
        │
        ▼
按股票块读取 Qlib 原始字段/表达式
        │
        ▼
立即压缩到月末截面并写 score cache
        │
        ▼
批量合并月末因子面板
        │
        ▼
批量 RankIC 和便宜门禁
        │
        ▼
只对初筛通过者执行 bootstrap
        │
        ▼
selection.csv / monthly-rankic.csv / summary.json / report.md
```

### 4.2 内存模型

禁止保留：

```text
全股票 × 全日历 × 大批量因子
```

推荐保留：

```text
股票块（250–500只）× 日历 × 当前表达式批
```

读取成功后立即转换为：

```text
月末日期 × 股票块 × 当前表达式批
```

每个股票块处理完后释放日频 DataFrame。月末结果写入 Parquet 或分片 score cache，不把所有日频结果留在 Python 堆中。

### 4.3 并发模型

初始默认配置：

```text
worker：4
股票块：500
表达式批：20–50
每批完成后 checkpoint：是
provider：只读
```

并发只能由基准决定。候选配置必须满足：

- 总常驻内存不超过物理内存的 70%；
- 页面文件不持续增长到危险区；
- 单 worker CPU 使用率和磁盘吞吐不显示严重争用；
- 批次耗时随 worker 增加仍然下降。

禁止直接恢复 16 worker。即使 16 个进程都显示 CPU 忙，也可能是在争抢同一 provider 的文件元数据和 bin 文件。

## 5. 分阶段实施计划

### 阶段 0：冻结和清理运行现场

目标：避免旧进程、旧结果和新实验混在一起。

工作内容：

1. 识别并停止所有属于失败批次的 Qlib 进程，只允许目标批次继续运行。
2. 确认 `-6c`、`-7`、`-8`、`-9` 等历史批次只读保留。
3. 建立新批次目录和 `run-identity.json`。
4. 写入输入、provider、代码和环境摘要。
5. 把当前 16 进程页面文件耗尽记录为性能缺陷证据。

完成条件：

- 新批次目录不存在旧 `selection.csv`、旧 RankIC 或旧 checkpoint；
- 2000 个候选唯一且顺序冻结；
- 旧失败批次仍可追溯；
- 运行前身份核验通过。

### 阶段 1：provider 文件索引和元数据缓存

目标：消除重复的 `glob/exists/is_dir/stat` 扫描。

工作内容：

1. 启动时一次扫描 provider 的 `features/`、`calendars/`、`instruments/`。
2. 构建只读索引：

```text
(field, instrument, freq) -> bin path
(field, instrument) -> exists/start/end/length
provider -> supported frequencies
```

3. 将索引写成当前批次绑定的 `provider-index.json` 或紧凑二进制索引。
4. 在 Qlib 调用前做全局缺字段检查。
5. 对 Qlib `FileFeatureStorage` 的路径元数据做进程内缓存；缓存必须绑定 provider manifest，不能跨 provider 复用。
6. 对缺 bin 的局部股票返回 NaN，对全局缺字段 fail-closed。

实现限制：

- 不修改安装环境中的 Qlib 源码；
- 优先在 `qlib_research/` 通过初始化护栏、缓存对象或 provider 包装实现；
- 所有缓存命中和回退次数写入性能日志。

验证：

- 同一 provider 的冷启动和热启动分别统计 `glob_count`、`stat_count`、读取耗时；
- 修改一个 bin 后 manifest 校验必须拒绝旧索引；
- 缺字段和缺单只股票的负例必须区分。

### 阶段 2：Qlib 股票块流式求值

目标：消除全池全日线大矩阵。

工作内容：

1. `load_feats` 改为股票块迭代器。
2. 每个块内调用 Qlib `D.features`，不跨块保留日频结果。
3. 每块读取后只保留月末日期和当前表达式列。
4. 立即写入：

```text
score-cache/<shard>/<batch>.parquet
```

5. 写入后删除日频 DataFrame，并记录 RSS、Private Bytes 和块耗时。
6. 同一表达式批次的所有股票块完成后，才将该批次标记为 done。
7. 某股票块失败时只重试该块；某表达式失败时递归二分表达式批，不让整批全部退化为逐表达式读取。

推荐文件字段：

```text
datetime
instrument
candidate_id
score
finite
eligible
provider_identity
```

验证：

- 1、10、100 因子分别运行股票块流式路径；
- 月末值与同输入全量小样本路径逐值比较；
- 证明 5002 只股票不再生成全日线全批矩阵；
- 任何块失败都有明确 `BLOCKED_DATA` 或技术失败记录。

### 阶段 3：公共子表达式和 Qlib 计算复用

目标：减少 2000 个表达式之间的重复字段读取和滚动计算。

工作内容：

1. 对 Qlib 表达式做规范化和去重。
2. 统计重复的基础字段、滚动窗口和公共子表达式，例如：

```text
Ref($close, 1)
Mean($close, 20)
Std($market_ret, 20)
Sum($volume, 20)
```

3. 优先缓存 Qlib 可安全复用的基础表达式结果。
4. 缓存键必须包含：表达式文本、provider identity、股票块、日期范围、Qlib 版本和精度配置。
5. 缓存输出只用于同一身份的 L0 批次；身份变化必须新建缓存。
6. 对相关但不等价的表达式不做数值替换。

成功标准：

- 100 因子基准中重复子表达式读取次数明显下降；
- 缓存命中后冷/热路径耗时分开报告；
- 缓存命中不改变月末因子值；
- 未经证明的近似不能进入正式结果。

### 阶段 4：批量 RankIC 和门禁分层

目标：让 Qlib 求值和统计筛选解耦，避免把昂贵 bootstrap 放在所有候选之后。

工作内容：

1. 月末 score cache 形成 `month × instrument × factor_batch` 面板。
2. 一次性计算当前批次所有因子的横截面秩。
3. 先做便宜检查：

```text
有限值比例
有效月数
每月最小股票数
月均 RankIC
年度方向一致性
```

4. 只有达到基础方向和有效月门槛的候选才进入 bootstrap。
5. bootstrap 参数保持冻结：块长 3、B=10000、种子 20260909、Bonferroni 口径不变。
6. 统计不足必须写 `P5_STAT_INSUFFICIENT`，不能写成策略失败。
7. 缺字段、表达式不支持和计算异常分别记录。

### 阶段 5：可观测运行器和恢复机制

目标：任何时候都能知道已完成多少、正在做什么、还能否恢复。

每个分片每个批次写入：

```json
{
  "shard": 0,
  "batch": 3,
  "candidate_start": 300,
  "candidate_end": 349,
  "candidate_count": 50,
  "completed_count": 50,
  "phase": "monthly_projection",
  "elapsed_seconds": 123.4,
  "rss_mb": 812.3,
  "read_seconds": 98.1,
  "expression_seconds": 20.2,
  "rankic_seconds": 3.8,
  "status": "DONE"
}
```

心跳文件：

```text
checkpoint/heartbeat.s<shard>.json
```

恢复规则：

- 只加载身份一致且原子写完的 checkpoint；
- 发现中间文件、缺列、候选集合不一致或 provider manifest 变化，拒绝恢复；
- 失败批次写入 attempt-N，不覆盖旧 attempt；
- 汇总前检查所有 2000 个候选都有终态；
- 未完成候选必须是 `PENDING` 或 `BLOCKED`，不能被汇总成 `REJECTED`。

### 阶段 6：性能调优和正式 L0

按以下顺序做基准，不直接启动 2000 全量：

| 基准 | 股票块 | 因子数 | worker | 目的 |
|---|---:|---:|---:|---|
| S1 | 500 | 1 | 1 | 正确性和单因子内存 |
| S2 | 500 | 10 | 1 | 批量收益 |
| S3 | 500 | 100 | 1 | 单 worker 基线 |
| S4 | 500 | 100 | 2 | 并发争用 |
| S5 | 500 | 100 | 4 | 推荐并发候选 |
| S6 | 500 | 100 | 6 | 上限候选 |
| S7 | 500 | 125 | 推荐正式批 | 预计全量耗时 |

每次记录：

- 总耗时；
- Qlib 数据读取耗时；
- 表达式求值耗时；
- 月末压缩耗时；
- RankIC 耗时；
- RSS/Private Bytes 峰值；
- provider 文件访问次数；
- checkpoint 写入耗时；
- 错误和重试数量。

正式放行条件：

- S1、S2 数值正确性通过；
- S3 无内存泄漏；
- S4/S5 不出现页面文件持续增长；
- S5 估算全量时间不超过 45 分钟，给最终汇总和异常重试留出 15 分钟；
- 任何正式 worker 峰值 Private Bytes 不超过物理内存的 20%；
- 运行器可以中断后恢复；
- 所有 2000 候选有终态。

如果 S5 无法达到 45 分钟估算，状态写为 `PERFORMANCE_BLOCKED`，先继续优化，不启动正式全量。

## 6. 预计代码改动

主要改动集中在三个位置：

### `qlib_research/l0_2000.py`

- 增加 provider index 和运行身份校验；
- 将 `load_feats` 改为股票块流式接口；
- 增加表达式批次递归二分；
- 增加月末 score cache；
- 增加 heartbeat、RSS、阶段耗时和批次状态；
- 将基础门禁、bootstrap 和导出拆成明确阶段；
- 增加 `--workers`、`--instrument-chunk`、`--batch-size`、`--heartbeat-seconds`；
- 增加正式超时和内存保护。

### 新增 `qlib_research/provider_index.py`

- provider 文件扫描；
- 字段/股票/freq 索引；
- manifest 校验；
- 缺字段分类；
- 只读元数据缓存。

### 新增 `qlib_research/l0_monitor.py`

- 读取 heartbeat；
- 输出分片/批次进度；
- 输出 RSS、Private Bytes、CPU 和阶段耗时；
- 检查超时、无心跳和页面文件风险；
- 生成 `progress.json` 和 `performance-report.md`。

### 可能新增 `qlib_research/csrank_stage.py`

- 实现 Qlib `CSRankNorm` 分阶段流程；
- 绑定日期轴和股票池；
- 对嵌套 `CS_RANK` 做显式阶段拆分；
- 无法安全拆分时 fail-closed。

## 7. 测试计划

### 7.1 单元测试

- provider index 对新增、缺失、变异 bin 的识别；
- 路径缓存命中和失效；
- 股票块拼接不重复、不漏股票；
- 月末日期选择；
- 2022-12 未成熟标签排除；
- 递归批次失败只隔离坏表达式；
- checkpoint 原子写入和恢复；
- identity 变化拒绝旧缓存；
- `CS_RANK` 不被转换为时序 `Rank`。

### 7.2 数值等价测试

使用 30 只股票、20 个表达式、2020–2022 的夹具，对比：

- 原生小规模 Qlib 直接路径；
- 股票块流式路径；
- score cache 路径；
- RankIC 和有效股票数；
- 缺字段和局部缺 bin 处理。

允许浮点误差必须事先固定，例如按 Qlib float32 输出给出绝对/相对误差界；不能用“结果看起来差不多”作为依据。

### 7.3 故障恢复测试

- 第一批完成后强制中断；
- 中间 checkpoint 损坏；
- provider manifest 变化；
- 候选源改变一行；
- 某表达式触发 Corr 异常；
- 某股票块缺字段；
- 单个 worker 被系统终止；
- 汇总时缺一片；
- 内存保护主动停止。

每个负例都必须 fail-closed，并留下可读原因。

### 7.4 性能测试

性能测试不只看墙钟时间，还必须看：

- 单因子耗时；
- 每 10/50/100 因子耗时；
- provider 文件访问次数；
- CPU 利用率；
- RSS 和 Private Bytes；
- 页面文件使用量；
- 并发扩展曲线；
- 热缓存与冷缓存差异。

## 8. 最终验收工件

有效正式批次必须包含：

```text
run-identity.json
provider-index.json
performance-report.md
progress.json
selection.csv
monthly-rankic.csv
monthly-rankic.parquet
summary.json
report.md
checkpoint/
heartbeat/
logs/
```

`summary.json` 至少包含：

```json
{
  "candidate_count": 2000,
  "terminal_count": 2000,
  "status_counts": {},
  "completed_shards": 16,
  "engine": "qlib",
  "qlib_version": "0.9.7",
  "elapsed_seconds": 0,
  "peak_rss_mb": 0,
  "performance_status": "PASS_WITH_LIMITATIONS"
}
```

`report.md` 必须明确：

- 计算是否在一小时内完成；
- 实际 worker、股票块和表达式批大小；
- 是否有重试和恢复；
- 2000 个候选的完整状态计数；
- 缺字段和不支持表达式清单；
- Qlib 版本和 provider 身份；
- 统计结论仍是探索性 L0，不等于 Alpha、盈利或可实盘；
- L1/L2 尚未启动。

## 9. 时间和人力估算

### 止血版本

包括路径缓存、4–6 worker、股票块流式读取、进度心跳和 checkpoint 改造：

```text
约 1–2 个工程日
```

这只能改善稳定性和可观测性，不能承诺一小时完成。

### 一小时正式版本

包括 provider 索引、流式月末缓存、批量 RankIC、公共子表达式复用、恢复机制、CSRankNorm 阶段化和完整性能验证：

```text
约 4–8 个工程日
```

其中：

- 计算路径改造：2–4 天；
- PIT、缺失值、CS_RANK 和日期边界验证：1–2 天；
- 2000 候选压力、恢复和独立核算：1–2 天。

当前 100 因子单进程基准为 1173 秒。要把 2000 因子压到一小时内，需要同时取得批量复用、provider 索引缓存和适度并发的综合收益，不能只依赖增加进程数。

## 10. 实施顺序和停止条件

实施顺序固定为：

```text
停止失控批次
→ 冻结新身份
→ provider 索引
→ 股票块流式读取
→ 单元和数值测试
→ 1/10/100 基准
→ 并发基准
→ 2000 正式 L0
→ 独立复核
```

停止条件：

- 任何测试发现因子值改变但无法解释，停止正式运行；
- provider identity 变化，停止并新建批次；
- Private Bytes 或页面文件持续增长，停止当前并发配置；
- 30 秒无 heartbeat 且 CPU/IO 无变化，标记 worker 需要恢复；
- 估算正式全量超过一小时，写 `PERFORMANCE_BLOCKED`，不以半成品冒充完成；
- L0 完成后不自动进入 L1/L2。

## 11. 成功定义

本计划只有同时满足以下条件才算 L0 性能改造完成：

1. 2000 个候选全部有终态；
2. 结果来自 Qlib 原生表达式和当前 provider；
3. 没有复用旧批次 RankIC 或 selection 结果；
4. 运行过程有可验证 heartbeat、checkpoint、资源和耗时记录；
5. 正式运行未发生页面文件耗尽或未记录的进程丢失；
6. `selection.csv`、`monthly-rankic.csv`、`summary.json`、`report.md` 完整；
7. 一小时目标得到实际墙钟证据，或正式报告明确记录 `PERFORMANCE_BLOCKED` 及原因；
8. 独立复核可以从输入身份和 checkpoint 重建候选集合；
9. 统计有效性仍与工程完成分开，L0 通过不代表盈利、Alpha 或生产放行。
