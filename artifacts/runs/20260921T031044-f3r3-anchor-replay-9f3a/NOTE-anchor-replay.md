# 说明：本目录是 F3R3 锚重放（零试验消费），不是新的 F3R3 试验运行

- 用途：任务② 验收条件之「三锚零回归 ③」——用**扩展后引擎 v1.5**（默认
  `etf_routing='paired'`）全期重跑 F3R3，逐位复现冻结 run
  `artifacts/runs/20260921T024449-f3r3-dynamic-45037d/outputs/` 的四个产物帧。
- 脚本：`tmp/runner_f3r3_anchor.py` = 该 run 的 `tmp/runner_f3r3.py` 的**逐字节副本**，
  仅改一行 `ENGINE_SHA_EXPECT_16`（`bcbdd44bb855b803` → `d4b6c3764780e6de`）；
  文件头 8 行注释说明该差异，正文与源脚本逐字节一致（脚本内 self-check 打印）。
  冻结 run 目录**未被改动**（其最新文件 mtime 仍为 2026-09-21T02:56:19）。
- 本目录里的 `manifest.json` / `report.md` / `logs/` 由该副本 runner **自行写出**，
  其中 `experiment_id`、gates 等信息是 F3R3 的复放内容；**它不构成新试验**：
  判据与输入与原 run 完全相同，试验计数消费 0。
- 比对结果：`outputs/anchor_frame_comparison.json`（15 个产物逐一 sha256）。要点：
  - `F3-{EW,ICW}_{fills,events,daily_equity,clips_final}.parquet` 共 **8 帧逐字节相等**；
  - `seat_outcomes.csv`、`dedup_clusters.csv`、`pool_sizes.csv` 同样逐字节相等；
  - `F3-{EW,ICW}_composite.parquet` 文件字节不同、**行多重集与键序完全一致**
    （`sort(columns).equals()` 为 True；属写入顺序/编码差异，喂给引擎后成交帧仍逐字节相等）；
  - `metrics_and_gates.json` 差异仅两处：`engine_sha256_16` 字段与
    `F3-ICW` 换手/均值权益的 ~1e-15 浮点归约噪声；门判定与所有判据数字不变（0/2 dev_pass）。
- 复现命令（工作目录 `D:/量化`）：
  `.venv/Scripts/python.exe artifacts/runs/20260921T031044-f3r3-anchor-replay-9f3a/tmp/runner_f3r3_anchor.py`
  （墙钟约 50–230 s，取决于并发负载；峰值内存 ~3.4 GB；预算 3600 s 内）
