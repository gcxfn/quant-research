# C0 实际执行命令与退出码（command log）

- 阶段：C0 / run `20260922T013755-trust-c0-c17494`
- 会话时间（UTC）：2026-09-21T17:31Z — 2026-09-21T17:55Z（本机本地 2026-09-22 01:31—01:55，Asia/Shanghai）
- 执行解释器：`D:\量化\.venv\Scripts\python.exe`（Python 3.11.15）
- 性质：只读命令 + 只新增文档。命令按实际执行的顺序与形态记录；输出为原样摘录或计数，不是重新运行的结果。

## 1. 版本与工作树

| # | 命令 | 退出码 | 结果摘要 |
|---|---|---|---|
| 1 | `git rev-parse HEAD` | 0 | `ae226d964b1ea1dccfb60a42ae943c6da8a179e6` |
| 2 | `git branch --show-current` | 0 | `main` |
| 3 | `git remote -v` | 0 | `origin https://github.com/gcxfn/quant-research.git`（fetch/push 同址） |
| 4 | `git status --porcelain` | 0 | 8 个 ` M` + 7 个 `??`（原样输出见 `takeover_state.md` §1） |
| 5 | `git log --oneline -20` | 0 | 5 个提交，最新 `ae226d9` |
| 6 | `git diff --stat` | 0 | 8 files changed, 165 insertions(+), 34 deletions(-) |
| 7 | `git diff <file>`（逐文件，8 次） | 0 | 用于判定每个未提交文件的性质 |
| 8 | `git log --format='%h|%ad|%s' --date=iso -6` | 0 | 提交时间确认（最新 2026-09-21 23:58:16 +0800） |
| 9 | `git branch -a` | 0 | 只有 `main` 与 `remotes/origin/main` |
| 10 | `git rev-parse origin/main` / `git rev-list --left-right --count HEAD...origin/main` | 0 | `ae226d9…`；`0 0`（本地与远端一致） |

## 2. 权限事实（GitHub 只读查询）

| # | 命令 | 退出码 | 结果摘要 |
|---|---|---|---|
| 11 | `gh auth status` | 0 | 已以 `gcxfn` 登录，token scope `gist, read:org, repo, workflow` |
| 12 | `gh api repos/gcxfn/quant-research` | 0 | `{"full_name":"gcxfn/quant-research","private":false,"visibility":"public","default_branch":"main","pushed_at":"2026-09-21T15:58:20Z"}` |
| 13 | `gh api repos/gcxfn/quant-research/branches/main/protection` | 非 0（HTTP 404） | `{"message":"Branch not protected"}` |
| 14 | `gh api repos/gcxfn/quant-research/rulesets` | 0 | `[]` |
| 15 | `gh api repos/gcxfn/quant-research/actions/workflows --jq .total_count` | 0 | `0`（仓库内也没有 `.github/` 目录） |

## 3. 文件哈希（用于 `evidence_index.csv`）

| # | 命令 | 退出码 | 说明 |
|---|---|---|---|
| 16 | `.venv/Scripts/python.exe -c "hashlib.sha256(...)"`（3 批，共 45 个文件） | 0 | 每个文件同时计算原始 SHA256 与把 CRLF 归一为 LF 后的 SHA256；结果写进 `evidence_index.csv` |
| 17 | `.venv/Scripts/python.exe -c "import csv; ..."`（列数校验） | 0 | `contract_conflicts.csv` 表头 11 列 / 12 行 / 无错行；`evidence_index.csv` 11 列 / 44 行 / 无错行；`access_ledger.csv` 12 列 / 9 行 / 无错行 |

## 4. 环境与资源实测

| # | 命令 | 退出码 | 结果摘要 |
|---|---|---|---|
| 18 | `.venv/Scripts/python.exe -V` | 0 | `Python 3.11.15` |
| 19 | `python -V` / `python -c "import sys;print(sys.executable)"` | 0 | 也是 3.11.15，但指向 `D:\AI\agent\hermes\venv\Scripts\python.exe`（agent 自身环境，非项目环境） |
| 20 | `.venv/Scripts/python.exe -c "import importlib.metadata as m; ..."` | 0 | pytest 9.1.1、polars 1.44.2、numpy 1.26.4、pandas 2.3.3、pyarrow 25.0.1、psutil 7.2.2、scipy 1.17.1、scikit-learn 1.9.1、lightgbm 4.7.0、vectorbt 0.28.5、backtrader 1.9.78.123、rqalpha 6.3.0、baostock 0.9.3、tushare 1.4.29、matplotlib 3.11.2 |
| 21 | `.venv/Scripts/python.exe -c "psutil / shutil.disk_usage ..."` | 0 | 20 逻辑核 / 14 物理核；内存总 16.8 GB、可用 4.7 GB；D 盘总 777.7 GB、可用 212.5 GB |
| 22 | `du -sh data artifacts src tests docs` | 0 | data 131G、artifacts 1.3G、src 4.0M、tests 5.7M、docs 58M |
| 23 | `grep -rc "def test_" tests/**` 汇总 | 0 | 静态测试函数 691 处（参数化后收集数会更多，未运行） |

## 5. 证据阅读（只读）

| # | 路径 | 用途 |
|---|---|---|
| 24 | `artifacts/runs/20260922T00*/manifest.json`（4 份，用 python json 打印） | 判定 attrib2 四运行的输入输出口径与状态 |
| 25 | `artifacts/runs/20260922T002611-.../outputs/B1_event_funnel.csv`（csv 解析） | 核对 102 行漏斗：slot_full 63 / issued 39 / filled 35 / cancel_cap 4；签发单 `order_price_first == decision_anchor_price` 39/39 |
| 26 | `docs/evidence/affected_runs.csv`、`docs/evidence/trial-ledger.md`、`docs/research/research-ledger-20260921.md`、`docs/research/exp-20260921-mean-reversion-val.md`、`docs/research/exp-20260921-short-reversal.md` | Val 消费与受影响范围的**文字**记录（未重算） |
| 27 | `src/quant/backtest/band_engine.py`、`src/quant/research/event_family_signals.py`、`src/quant/research/risk_overlay_runner.py`、`src/quant/research/screen.py`、`docs/plans/p3-band-contract.md`、`docs/research/stock_event_research_prereg.md`、`AGENTS.md` | 合同快照与冲突表的来源 |
| 28 | `grep`/`find` 全树检索（`trust-rebuild`、`stock-first-trust`、`contract_snapshot`、`access_ledger`、`evidence_index`、`acceptance_matrix`、`C1-S`、`复审`） | 判定是否已有 C 类进展；结论见 `takeover_state.md` §3 |

## 6. 交付自查（执行包的离线检查器）

| # | 命令 | 退出码 | 结果摘要 |
|---|---|---|---|
| 29 | `.venv/Scripts/python.exe docs/quant_stage_plan_20260922/tools/check_delivery.py --report docs/evidence/trust-rebuild/20260922T013755-trust-c0-c17494/stage_report.json --root .` | 2 | `status = EVIDENCE_CHECK_FAILED`；`verified_file_count = 11`（11 项证据 SHA256 全部匹配）；errors 恰为两条：`C0-08: gate is not PASS`、`unclosed blocker: C0-MAJ-01`。两条都是本阶段的真实状态（审阅未做；cap/限价接口问题留给 C3），不是格式或哈希问题。该工具自述不验会计、不认证身份、不构成批准 |

## 7. 本轮明确未执行的命令类别

- 任何 `pytest` / `unittest` 调用。
- 任何 `python -m quant.*`、任何回测/因子/训练/归因脚本（包括复跑 `runner_attrib2.py`）。
- 任何 `git commit` / `git push` / `git stash` / `git reset` / `git clean` / `git checkout` / `git branch -d`。
- 任何写入 `src/`、`tests/`、`AGENTS.md`、`data/`、`artifacts/` 的命令。
- 任何对 `data/` 下文件的打开或统计。
