# 迁移报告（2026-09-16）

把旧库 `D:/AI/workspace/个人量化`（224.7 GB）中的**原始数据**迁入新工作区 `D:/量化`，
旧库连同代码、产物、依赖环境一并删除。用户指令：完整拷贝原始数据、去掉重复、旧库删掉、
只复制原始数据（2026-09-16）。

## 1 迁移方式

源与目标同卷（`D:`），盘上仅剩 140.4 GB 空闲而数据本身 145.4 GiB —— 全量复制不可能完成。
因此采用**同卷重命名（Move-Item）**逐源目录搬移：瞬时完成、零额外空间。
（一次性迁移脚本留在 `tools/migration/`：证据抢救、legacy 结构重建、旧库删除，供复核。）

```powershell
# 逐顶层数据源重命名（16 个来源目录），脚本：tools/ 当时的一次性 _move_raw.ps1（已清理）
Move-Item -LiteralPath "<旧>/data/raw/<source>" -Destination "D:\量化\data\raw\<source>"
```

## 2 迁移前后一致性

| 项 | 迁移前基线 | 迁移后复核 | 结果 |
|---|---:|---:|---|
| 顶层来源目录 | 16 | 16 | 一致 |
| 文件数 | 136,348 | 136,348 | 一致 |
| 字节数 | 156,072,876,417 | 156,072,876,417 | **逐源逐字节一致** |

基线逐源记录 `docs/evidence/raw-baseline-before-move.tsv`，迁移后记录 `docs/evidence/raw-after-move.tsv`，
两者 `diff` 为空。搬移过程中源目录零残留。

## 3 完整性校验（迁移后在新位置重算）

| 校验 | 对象 | 结果 |
|---|---|---|
| SHA-256 逐文件 | 21 个分钟 zip（11 个 `bigquant` + 10 个 `user_minute_1m`），对照各自 manifest（**解压前**） | **21/21 一致，0 问题** |
| 解压层校验清单 | `bigquant/minutes-bulk.../manifest/years/*.sha256.txt` | 当时引用的解压层已在去重中删除；2026-09-16 解压重建后**恢复有效**（见 §9） |
| 抽样逐字段核对 | `hf_minute_1m` 22 只证券 × 7 个交易日 = 113 例，与整包比 `close/volume/turnover` | **113/113 相同**（据此判定为子集副本并删除） |
| 批次日期区间重叠 | 全部 1,071 个批次目录（**去重前**状态） | 0 处重叠（无重复拉取） |
| 字节级去重 | 136,348 个文件（同尺寸候选 57,436） | 324 组重复，处置见 [`DEDUPE_REPORT.md`](DEDUPE_REPORT.md) |
| 全量 SHA-256 台账 | 122,576 个文件（`data/_meta/sha256.tsv`）逐文件重算比对（**去重后、解压前**状态） | **0 处不符**（无新增/缺失/摘要不一致） |
| 全量 SHA-256 台账（重算） | 138,887 个文件，1 分钟解压并删除 zip 之后（最终态） | **0 处不符**（见 §9） |

校验输出：`data/_meta/dupes.json`、`docs/evidence/hf-minute-crosscheck.json`、`docs/evidence/minute-extract.json`。

## 4 删除内容

| 对象 | 体积 | 说明 |
|---|---:|---|
| `bigquant/.../years/`（2010–2019 解压层） | 62.66 GiB | 可由 zip 确定性重建；与整包重复形态。**2026-09-16 反转：解压层重建、zip 删除（见 §9）** |
| `user_csv_1m/` 数据集内容 | 6.94 GiB | 与 `bigquant` 逐字节重复 |
| `free-stockdb/` | 2.01 GiB | 第三方工具包，非研究口径数据 |
| `hf_minute_1m/{20260913-all22,20260913-redownload}` | 0.37 GiB | 整包子集副本 |
| **小计** | **71.98 GiB** | 156.07 GB → 79.18 GB |

保留的唯一身份记录：`user_csv_1m/{20260913-2,20260913-3,20260913-4}/` 下 3 份 `patches.json`、
`transfer-manifest.json`、`validation.json` 与 2 个小体量 `*_f5.csv`。

## 5 旧库遗留文本的抢救（删除前）

| 位置 | 内容 | 体积 |
|---|---|---:|
| `docs/legacy/docs/` | 旧库 `docs/` 全树（217 个 .md + .json，含三份任务书、handover、decisions、实验记录） | 4.2 MiB |
| `docs/legacy/{README,AGENTS,CHANGELOG}.md` | 旧库根级说明与协作规则 | — |
| `docs/legacy/artifacts-evidence/` | 定向证据：分钟包审核（review*.json、给数据卖家的核验清单、22 项补修清单、原生 5 分钟对照、旧账户回归）、xiaodefa 数据集目录与盘点、BigQuant 来源修订、覆盖率评审 | 3.9 MiB |
| `docs/legacy/old-source-snapshot.zip` | 旧库源码/配置/文档快照（排除数据、产物、依赖、二进制，单文件 ≤2 MiB） | 42.9 MiB |
| `docs/legacy/old-history.bundle` | 旧库 git 对象（`git bundle create --all`）：含 `refs/heads/master` 与 25 个 `refs/codex/turn-diffs/checkpoints/...` 引用，可 `git clone` 恢复 | 3.9 MiB |

说明：用户要求"只复制原始数据"，因此上述均为**文本证据/可读结论**级别的小体积留存；
旧库其余内容（`artifacts/` 73 GB 产物、`apps/`、依赖环境）**未保留、已随旧库删除**。
若不需要留存，删除 `docs/legacy/` 即可，不影响 `data/raw`。

## 6 旧库删除

- 方式：`tools/migration/wipe_old_library.py`（robocopy 空目录镜像 `/MIR` 清空 + 删除空壳）。
- 旧库删除前规模：4,004,822 个文件 / 79,556,845,144 B（74.09 GiB）。
- 执行输出：

```
target files=4004822 bytes=79556845144 (74.09 GiB)
robocopy rc: 2                      # 2 = 目标存在源没有的多余项并被清除，镜像删除的预期返回码
target exists after wipe: False
```

- 结果：`D:/AI/workspace/个人量化` **已删除**，`D:/AI/workspace` 下只剩环境目录与无关工程。
- 磁盘：D 盘 已用 583.9 GB / 空闲 140.4 GB → 已用 439.3 GB / **空闲 285.0 GB**。
- 新工作区 `data/raw` 未受影响（删除后复核文件数与字节数不变，见 §7）。

## 7 迁移后状态（最终态，含 §9 解压变更）

| 项 | 值 |
|---|---|
| 新工作区 | `D:/量化`（`README.md` / `data/` / `docs/` / `tools/`） |
| 数据规模 | 1,088 个批次目录 / 138,887 个文件 / 135,634,263,041 B（126.34 GiB） |
| 磁盘 | D 盘已用 492.3 GB / 空闲 **232.0 GB**（迁移前 已用 583.9 GB / 空闲 140.4 GB；旧库删除后 285.0 GB；1 分钟解压 −51.95 GiB 包 +104.9 GiB 目录后 232.0 GB） |
| 台账 | `docs/DATA_INVENTORY.md`、`data/_meta/inventory.json`、`data/_meta/sha256.tsv`（重算后 0 处不符） |
| 其余文档 | `docs/DATA_SOURCES.md`（口径与陷阱）、`docs/DATA_COVERAGE.md`（覆盖矩阵）、`docs/DEDUPE_REPORT.md`（去重与解压） |

## 8 迁移引入的路径引用问题（需在新工程中处理）

被搬移的批次 manifest 内仍记录**旧库绝对路径**（`D:\AI\workspace\个人量化\...`），
属于数据身份的历史记录，**不得改写**（改写会破坏与既有校验摘要的对应关系）。
新工程读取时按「以 `data/raw` 为根的相对路径」解析，不要直接使用这些绝对路径。

已知受影响文件（节选，同一模式可全库检索）：

- `bigquant/minute-bulk-20260915-1/manifest/zips.sha256.json` → `dest_path`
- `user_minute_1m/*/transfer-manifest.json` → `source` / `destination` / `target_root`
- `baostock/20260905_230017/summary.json` → `evidence.*`、`canonical_csv`
- `baostock/intraday-t0-*/fetch_log.json`、`bigquant/intraday-t0-20260914/fetch_log.json` → `script` / `path`
- `xiaodefa/minute-repairs-*/patches.json`、`baostock/ten-year-repair-*/{patches,manifest}.json` → `path` / `raw_path` / `previous_derived_path`
- `user_csv_1m/*/patches.json` → 同上

另：`data/raw/xiaodefa/minute-repairs-*` 等补丁清单引用的部分文件位于已删除的 `artifacts/` 下
（例如 `artifacts/ten-year-fixed-strategies-minute-accounts-20260913-7/derived-minute/...`），
这些派生路径**不可恢复**；补丁本身及其摘要仍在清单内，可作为身份记录使用。

## 9 后续变更：1 分钟压缩包解压（2026-09-16，用户追加指令）

「1 分钟原件解压出来，然后压缩包就不要了」——21 个分钟 zip 全部解压为目录层，压缩包删除。

| 项 | 值 |
|---|---:|
| 解压包数 | 21（`bigquant/…/zips` 11 + `user_minute_1m/*/` 10） |
| 解压结果 | `bigquant/minute-bulk-20260915-1/years/<年>/`、`user_minute_1m/<批次>/<年>/` |
| 解压文件数 / 字节 | 16,332 / 112,636,981,157 B（104.9 GiB） |
| 删除压缩包 | 21 个，51.95 GiB |
| 解压校验 | 逐成员 zip CRC；成员数/字节 21/21 一致；`extract-summary.json` 逐年成员数/字节一致（9 年）；2010–2013 逐文件 SHA-256 967/967 通过 |
| 变更后全树 | 138,887 个文件 / 135,634,263,041 B（126.34 GiB） |

- 工具：`tools/extract_minute_zips.py`（`--verify-only` 只核对不重解压），记录 `docs/evidence/minute-extract.json`。
- 退役：`tools/verify_zips.py` 与 `data/_meta/verify.json`（其对象是已删除的分钟 zip；当前完整性用 `tools/hash_manifest.py` 的全树台账）。
- 清单：`tools/minute_manifest.py` → `docs/evidence/minute-manifest.json`（逐年文件数/字节/首末交易日）。
- 台账与去重报告中的路径表述已同步；包级摘要的证据缺口见 [`DEDUPE_REPORT.md`](DEDUPE_REPORT.md) §6。
- 未动的同名压缩包：`user_dataset/2026-09-03/{上证,深证}/*.zip`（日线前/后复权，非 1 分钟）。
