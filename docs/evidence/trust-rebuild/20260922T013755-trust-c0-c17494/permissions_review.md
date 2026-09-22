# C0 权限落实程度审查（permissions_review）

- 阶段：C0 / run `20260922T013755-trust-c0-c17494`
- 结论：**`enforcement_level = procedural_only`**
- 含义：本轮的“实施者不能自签验收”“不得改硬规则”“不得读未授权数据”全部只靠**指令流程与自律**维持；没有任何技术门禁、独立环境或受保护权限在阻止越权。按主计划 16.3 的写法：不能声称技术上无法越权。

## 1. 实测到的权限事实

| 项 | 实测值 | 来源命令 | 风险 |
|---|---|---|---|
| 远端仓库 | `gcxfn/quant-research`，**public**（公开） | `gh api repos/gcxfn/quant-research` | 任何一次 push 即对外公开；含研究细节与产物索引 |
| 默认分支 | `main` | 同上 | 单分支开发，没有阶段分支 |
| 分支保护 | **未保护**（`Branch not protected`，HTTP 404） | `gh api repos/gcxfn/quant-research/branches/main/protection` | 任何有写权限的账号可直推 main、可 force-push |
| 规则集（rulesets） | 空数组 `[]` | `gh api repos/gcxfn/quant-research/rulesets` | 无“新提交使旧审批失效”等机制 |
| CI / 状态检查 | `total_count = 0`；仓库内也没有 `.github/` 目录 | `gh api .../actions/workflows`；`ls .github` | 没有自动测试关卡，没有必需状态检查 |
| 本地与远端一致性 | `HEAD == origin/main == ae226d9…`，ahead/behind = 0/0 | `git rev-parse` + `git rev-list --left-right --count` | 当前唯一的分支就是生产分支 |
| 本地分支 | 只有 `main` 与 `origin/main` | `git branch -a` | 没有为阶段实施隔离的分支或 worktree |
| 凭据 | 本机会话已用 `gh` 以 `gcxfn` 身份登录（token 具备 `repo`、`workflow` scope） | `gh auth status` | 实施者、审阅者、责任人共用同一账号与同一台机器 |
| 交付检查工具 | 执行包自带 `tools/check_delivery.py` 只能查文件存在、SHA256、门ID与基础 run/JUnit 信息 | 读 `00_README.md` | 它自述不校验会计、不判断 Alpha、不认证许可（主计划 16.3 同） |

## 2. 与执行包建议配置的差距

`03_governance.json` 建议（**proposed_not_deployed**，`enforcement_level: not_deployed`）与现状对照：

| 建议项 | 建议值 | 当前实际 | 差距 |
|---|---|---|---|
| 实施者不直接写 main | `direct_main_push: false` | main 未保护，可直推 | 未部署 |
| 禁止 force-push | `force_push: false` | 无保护，无规则集 | 未部署 |
| 实施者不能给自己签验收 | `implementation_agent_may_accept_own_work: false` | 只有提示词约束；本轮 C0-08 只能由另一会话完成 | 未部署 |
| 独立审阅必须存在 | `independent_review_required: true` | 本机没有第二个受控身份或环境 | 未部署 |
| 目标运行权限 | `authorized_execution_stages: []` | 实际执行的是执行包外的指令（C0），治理文件本身没有登记授权 | 未部署 |
| K 角色（隔离数据、执行命令、归档） | 主计划 3.1 建议四角色 | 本机由同一会话承担 I，K 角色缺位 | 未部署 |

补充事实：`03_governance.json` 的 `authorized_execution_stages` 是空数组，说明**本轮 C0 的授权并不来自该治理文件**，而只来自 `prompts/01_start_C0.md` 这段文字。治理文件与真实授权是两条线。

## 3. 因此本轮哪些“保证”是真实的、哪些不是

**是真实的**（有字节或命令证据）：

- 未改已跟踪文件：`git status --porcelain` 与 `git diff --stat` 可复核（见 `change_scope_review.md`）。
- 未运行回测/策略/因子：本轮没有产生任何新 run 目录（`artifacts/runs/` 下最新仍是 20260922T002611）。
- 证据文件的 SHA256：本目录各文件哈希由用户或审阅者用同一命令复核（命令写在 `stage_report.json` 的 `verification_commands`）。
- 远端 main 未被动过：`git rev-list --left-right --count HEAD...origin/main` = 0/0。

**不是真实的（不得声称）**：

- 不能声称“实施者技术上无法修改硬规则/证据”。本会话拥有对仓库全部文件（含 `AGENTS.md`、`docs/evidence/`、`data/_meta/sha256.tsv`）的写权限，且无任何门禁阻止。
- 不能声称“审阅者是独立第三方”。同一账号、同一机器、同一模型家族；主计划 3.1 已指出这类独立性的极限。
- 不能声称“哈希证明内容正确”。SHA256 只证明字节身份（主计划 16.3）。
- 不能把本文件里的 `reviewer_id`（本阶段为空）当作真实审核的证明。

## 4. 建议的下一步权限措施（**均未部署**，供用户在批准 C1 前决定）

按“先做最省事且真能拦住的”排序：

1. **给阶段实施开独立分支**：例如 `stage/c1-data-isolation`，实施者只推该分支；`main` 仅由用户或指定会话合并。这是最小成本的一条硬隔离。
2. **给 main 加保护**：`required_pull_request_reviews`（至少 1 个审批）+ `dismiss_stale_reviews`（新提交使旧审批失效）+ 禁止 force-push。注意：个人项目无法给自己审批，需再开一个协作者账号或使用环境级检查，否则该保护在单账号下会把自己锁死（这点必须先决定）。
3. **加一条最小 CI 状态检查**：当前仓库零 workflow。哪怕只跑 `pytest -q` + `check_delivery.py`，也能把“测试是否真的通过”从文字声明变成可核验状态；否则 C0-06/C0-08 这类门只能靠日志文件。
4. **验证数据与实施环境分离**：C1 要求 Dev-only 挂载。实际做法是由 K 角色（可由用户在另一台机器或另一账号的会话承担）导出受控工作集，实施者会话不持有全量数据路径；否则“不看未来”永远只是代码断言。
5. **证据目录改为“只能追加、且由审查会话复核哈希”**：至少做到每次交付把关键证据哈希写到独立文件，并由另一会话/账号用 `sha256sum` 复核后记录复核哈希，避免实施者单方面改写证据。
6. **明确谁保管 Val 与 2025+ 数据的访问权限**：目前全量数据在本机磁盘上、任何会话都能读；主计划 13 要求 C8 前锁住，这在当前权限模型下无法执行。

以上六项需要用户决定与操作，不是 agent 能自行"安装"的能力。
