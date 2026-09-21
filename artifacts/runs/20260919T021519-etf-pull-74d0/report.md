# Run Report: 20260919T021519-etf-pull-74d0

- 任务：从 baostock 补拉 ETF 历史日线（2015-01-01..2024-12-31，不复权，与股票腿同口径）
- 授权：用户 2026-09-19 批复"etf数据去拉"（docs/plans/p3-band-contract.md §6 推荐评估项）
- 状态：**FAILED（源端阻断）** —— baostock 对研究窗口内不存在任何 ETF 日线数据，任务无法完成
- 日期：2026-09-19（凌晨）

## 1. 结论与证据

两条 baostock K 线接口在窗口内均无 ETF 数据（探针全记录见 `endpoint_probes.json`）：

1. `query_history_k_data_plus`（逐代码接口）：对基金代码**确定性返回空集**（err=0、0 行、秒回）。
   验证代码：sh.510050、sh.510300、sz.159915、sz.159503（退市）。双环境（仓库 .venv 与
   hermes venv，均 baostock 0.9.3）结果一致。作为对照，股票代码 sh.600000 走同接口可返回
   err=0（当夜该通道多次超时/挂起，属服务端瞬时不稳，不影响空集结论的确定性）。
2. `query_daily_history_k_ETF`（0.9.x 新增的 ETF 专用按日接口，包内自带 demo）：
   功能正常（2026-02-04 返回 1,419 行，字段含 preclose/turn/tradestatus 等 18 列），但
   **历史深度只到约 2026-02**：窗口内 6 个抽查交易日（2015/2019/2023/2024 各点 + 2024-12-31）
   与 2025 全部 5 个抽查日、2026-01-02 均 err=0、0 行。demo 示例日期恰为 2026-02-04，与此吻合。

旁证：股票腿 `data/raw/baostock/daily`（1999-2024）不含任何基金代码（0/5410）；
recon 报告（artifacts/runs/20260918T202734-etf-recon-1d83）"baostock 无 ETF 数据"的结论在日线层同样成立（该报告 §2 表格漏列 tushare fund_daily 批次一处以盘上文件为准，分钟层结论不受影响）。

## 2. 本批实际产出：ETF 池与差集（有价值的身份记录）

池以 baostock 自己的 `query_stock_basic` 全量 type=5 名录为准（8,967 行全表 → 1,678 只，
全部在市；**baostock 名录不含退市 ETF**，全表 1,187 条退市记录均为股票/指数/转债）。
为满足"含已退市"要求，用盘上已验收的 tushare fund_basic（market=E、名称含 ETF、
list_date<=20241231）补齐名录缺失的 195 只（其中 124 只已退市），`pool_source` 列区分来源。
池共 **1,873** 只，落盘于批次 `pool_type5.csv`。

与 tushare fund_daily 20260917-r1（1,169 只）差集（明细 `pool_diff.json`）：

| 集合 | 数量 | 说明 |
|---|---|---|
| 交集 | 1,026 | 窗口内两源共有的 ETF |
| 仅 baostock | 652 | **全部 ipoDate > 2024-12-31**（2025/2026 新上市，窗口外） |
| 仅 tushare | 143 | 123 只有退市日（2015-08-27..2025-10-14），20 只无退市日（疑似转型/更名） |
| fund_basic 补充 | 195 | 其中 124 只退市；baostock 名录完全缺失退市 ETF |

## 3. 交叉复核

未执行：baostock 侧窗口内 0 行数据，无 (symbol, date) 可比。若未来以其它源补齐 ETF 日线，
对 tushare fund_daily 的 close 同目标跨源复核（不构成独立验证）可复用本目录
`crosscheck_close.py`（已备好，参数见脚本头注释）。

## 4. 实际改动清单

- `D:\量化\.venv`：`uv pip install baostock==0.9.3`（纯 Python；未改 pyproject.toml/uv.lock，
  未动其他包）。注：任务书称 .venv 已装 baostock，实测未装（此前拉取用的是仓库外
  hermes venv）；本次安装仅为执行本任务所需，如后续不再用 baostock 可移除。
- `data/raw/baostock/etf-daily-20260919-r1/`（新批次，3 个文件）：
  `pool_type5.csv`（1,873 只池）、`manifest.json`（**status=failed** + 阻断原因）、
  `sha256.tsv`（批次内校验）。
- `data/_meta/sha256.tsv`：**追加** 3 行（143,665 → 143,668），既有行零改动；
  `data/_meta/inventory.json`：追加 1 个批次条目（1092 → 1093），改动前备份在
  `tmp/inventory.json.bak-20260919_031322`。
- `docs/`、`configs/`、`src/`：零修改。无 git 操作。

## 5. 未完成内容与后续选项

- 未完成：2015-2024 ETF 日线补拉（源端无数据，非脚本或网络偶发问题；重试无意义）。
- 后续选项（需用户明确决定，本任务不做）：
  1. 将盘上已验收的 tushare `fund_daily/20260917-r1`（1,169 只、1,017,121 行）从"交叉源"
     升级为 ETF 腿主源——覆盖 1,026 只交集 + 143 只退市，是窗口内事实上的最全集合；
     缺口为 baostock 独有的 652 只 2025+ 上市品种（窗口外，研究本不需要）。
  2. 或评估 akshare/东财等第三源补齐（需另立任务与授权）。
  3. baostock ETF 数据 2026-02 起才有，对当前研究窗口无补拉价值，不建议再投入。

## 6. 运行留档

- 脚本：`pull_etf_daily.py`（池/manifest）、`fetch_etf_daily_byday.py`（按日拉取+透视，
  含健康守门 canary/daemon 模式，供源端未来补数据后重试）、`crosscheck_close.py`、
  `finalize_batch.py`、`register_meta.py`、`tmp/probe_retry.py`
- 证据：`endpoint_probes.json`、`pool_diff.json`、`tmp/probe_retry.log`、
  `tmp/stock_basic_all.csv`（baostock 全表快照）、`tmp/inventory.json.bak-*`
- 时间线：02:15 建 run → 02:17/02:21 池与差集（修正 to_ts_code 反向 bug 后）→
  02:21-02:55 k 线探针（发现 query_history_k_data_plus 基金空集 + start_date 关键字修正 +
  专用 ETF 端点发现 + 历史深度验证）→ 03:13 批次留档 + _meta 登记 → 03:2x 本报告
