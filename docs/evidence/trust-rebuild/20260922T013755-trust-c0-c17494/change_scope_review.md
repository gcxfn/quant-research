# C0 改动范围自查（change_scope_review）

- 阶段：C0 / run `20260922T013755-trust-c0-c17494`
- 结论：本轮**只新增文档**，未修改任何已跟踪文件、未运行任何策略/回测/测试/因子计算、未读取 2021 年以后行情或任何 Val 收益。
- 性质提醒：本文件是**实施者自查**，不能替代独立审阅（C0-08 仍为 PENDING）。

## 1. 本轮新增的文件（全部在 `docs/` 下）

| 路径 | 大小 | 说明 |
|---|---|---|
| `docs/evidence/trust-rebuild/20260922T013755-trust-c0-c17494/` | 目录（新建） | C0 证据目录 |
| 同上 `takeover_state.md` | 约 8.6 KB | 版本/工作树接管与未提交文件性质 |
| 同上 `contract_snapshot.json` | 约 20 KB | 合同快照（含 1 个 BLOCKING 字段） |
| 同上 `contract_conflicts.csv` | 12 行 | 冲突表 |
| 同上 `evidence_index.csv` | 44 行 | 证据索引（含实测 SHA256） |
| 同上 `access_ledger.csv` | 9 行 | 样本接触台账 |
| 同上 `change_scope_review.md` | 本文件 | 改动范围自查 |
| 同上 `permissions_review.md` | 约 6 KB | 权限落实程度 |
| 同上 `agents_amendment_proposal.md` | 约 11 KB | AGENTS 最小修订提案（草稿） |
| 同上 `stage_report.json` | 见文件 | 阶段报告 |
| `docs/plans/stock-first-trust-rebuild.md` | 约 13 KB | 新阶段线主计划索引 |

## 2. 逐项声明

### 2.1 未修改 `src/` 与 `tests/`

命令与结果（会话开始时与结束时各测一次，两次结果相同）：

```text
$ git status --porcelain
 M src/quant/research/event_family_signals.py        ← 会话开始前就存在（2026-09-22 凌晨批次）
（src/ 下没有任何其他条目变化；tests/ 下无已跟踪条目变化）

$ sha256
src/quant/backtest/band_engine.py            40f1aaebe49b8c5dba04e6d235155ff1e3db96c70d2b70490f7eb4e3a4537abd
src/quant/research/event_family_signals.py   994d6d09de4932a56918645cbc2c4686f81459a006cf454a70299abd6bd0ba5d
src/quant/research/single_name_rules.py      9f9cf8c6928f7495ab9d5ad4383b1451b02f5e720d3544267c1bb978a1fe0e92
src/quant/research/risk_overlay_runner.py    022640dd2c51b721026e870490943f8cbae7395f5c11ad3a1d6e20ce429dcf0a
src/quant/research/attribution_lib.py        0867f740546cd06d855c2ca1b20fb90c8b0122bef1a8e1eb8678aa9635569deb
tests/test_event_attribution_c0.py           73367994f167fe3edb38ab2f44be2e4e218523ff0ffbcdd7b6f6f62cd06d5298
```

说明：`src/quant/research/event_family_signals.py` 的 ` M` 标记与 `attribution_lib.py`、`test_event_attribution_c0.py` 的未跟踪状态都是**本轮之前**（2026-09-22 凌晨）就存在的，不属于 C0 改动；它们的哈希在整个 C0 会话期间未变。

### 2.2 未运行任何策略/回测/测试/因子计算

- 本轮没有产生任何新的 `artifacts/runs/<run_id>/` 目录：`ls -1t artifacts/runs | head -3` 仍为 `20260922T002611`、`20260922T002000`、`20260922T001713`。
- 未执行 `pytest`：`docs/evidence/` 下最新测试日志仍是 2026-09-21 的两份，本阶段没有新增日志。
- 未执行任何 `python -m quant...`、未调用引擎、未生成权益曲线或指标。
- 允许执行过的只有：`git` 只读命令、文件哈希计算、`gh api` 只读查询（仓库可见性/分支保护/工作流计数）、对本轮新写文档的 CSV/JSON 解析校验，以及执行包自带的离线检查器 `check_delivery.py`（只读文件与哈希，返回 exit 2，原因见下）。这些都写在 `stage_report.json` 的 `verification_commands` 里。
- 检查器实测：`status = EVIDENCE_CHECK_FAILED`、`exit code 2`、`verified_file_count = 11`（证据哈希全部匹配），errors 恰为 `C0-08: gate is not PASS` 与 `unclosed blocker: C0-MAJ-01` —— 分别对应“独立审阅未做”和“入场限价合同-实现落差留给 C3”，属预期状态，不是本轮的自查失败。

### 2.3 未读取新行情、未读取 Val 收益

- 未打开任何 `data/` 下的行情文件做统计（本轮不打开任何 `data/` 文件）。
- 唯一含价格数字的读取是 `artifacts/runs/20260922T002611-eventfam-attrib2-eed5cf/outputs/B1_event_funnel.csv`，其事件与成交全部落在 Dev 2015-2020（B1 最晚标签终点 2020-11-13）。
- 未读取任何 2021–2024 的收益数字；Val 消费情况只从 `docs/research/research-ledger-20260921.md`、`docs/evidence/trial-ledger.md`、`docs/research/exp-20260921-mean-reversion-val.md` 的**文字记录**转写进 `access_ledger.csv`，没有重新计算。
- 接触清单见 `access_ledger.csv`（AL-07 是本轮自身的访问记录），并明确区分“已知看过”与“不确定/unknown”。

### 2.4 未改硬规则、未覆盖旧证据

- `AGENTS.md` 未修改（`git status` 无该文件），只产出提案 `agents_amendment_proposal.md`。
- `data/_meta/sha256.tsv` 等校验基线未被触碰。
- 未执行 `git commit / push / stash / reset / clean`；远端 `origin/main` 与本地一致（ahead/behind 0/0）可复核。
- 未删除、未移动、未重命名任何历史文件或运行目录。

### 2.5 唯一一处对既有内容的“写入”

无。所有既有文件保持原字节；`git diff --stat` 在本会话开始与结束时完全相同（8 个文件、165 插入、34 删除），这 8 个文件全部属于会话开始前就存在的未提交批次。

## 3. 自查结论

| 检查项 | 结论 | 复核方式 |
|---|---|---|
| 未改 `src/`/`tests/` | 成立 | `git status` + 前后两次 SHA256 相同 |
| 未跑策略/回测/因子 | 成立 | 无新 run 目录、无新测试日志 |
| 未读新行情/Val | 成立 | 接触清单 AL-07；未打开 `data/` 任何文件 |
| 未改硬规则/未覆盖旧证据 | 成立 | `AGENTS.md`、`data/_meta/` 未出现在 `git status` |
| 未做 git 提交/推送 | 成立 | 无提交、`HEAD == origin/main` |
| 新增内容位置合规 | 成立 | 全部位于 `docs/evidence/trust-rebuild/<run_id>/` 与 `docs/plans/`，符合 AGENTS §2 文件归属 |

**这个自查只证明"我声称没做的事有命令证据"，不证明文件内容正确。** C0-06 与 C0-08 的最终裁定仍需独立审阅者用同一组命令复核，并按 `evidence_index.csv` 的 SHA256 逐文件比对。
