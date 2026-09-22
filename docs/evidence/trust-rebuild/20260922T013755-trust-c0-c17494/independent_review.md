# 独立审阅报告：C0（接管与合同冻结）

- 审阅对象 run：`20260922T013755-trust-c0-c17494`
- 审阅者身份：主对话会话（ZCode / GLM-5.3），与实施者子代理为不同会话与不同模型实例；同时担任本轮编排者。独立性边界见"未覆盖范围"。
- 审阅时间（本机）：2026-09-22 01:55—02:10
- 绑定身份：
  - 代码提交：`ae226d964b1ea1dccfb60a42ae943c6da8a179e6`（工作树含未提交批次，清单见 takeover_state.md）
  - 证据目录：`docs/evidence/trust-rebuild/20260922T013755-trust-c0-c17494/`（10 文件）
  - 执行包：`docs/quant_stage_plan_20260922/`（package_manifest.json v1.0）

## 审阅范围与未覆盖范围

**范围**：C0 全部 8 项门（02_acceptance_matrix.csv C0-01..C0-08）；实施者交付的 10 个文件全部逐份阅读；关键事实声明做独立命令核验（下表）。**未覆盖**：未重跑 713 项测试套件（授权范围外，留 C4）；未打开任何行情数据文件（含 Dev）；未核验 4 个 attrib2 运行的数值正确性（属 C2/C5 范围）；AGENTS 修订提案与未提交批次处置属用户决策，本审阅只确认其被正确登记。

## 独立动作（实际执行的命令与结果）

| # | 动作 | 命令 | 结果 |
|---|---|---|---|
| R1 | 核对交付物存在 | `ls docs/evidence/trust-rebuild/20260922T013755-trust-c0-c17494/` | 10 文件齐全 |
| R2 | 核对未越权改动 | `git status --porcelain`、`git diff --stat`（与 C0 开始前快照比对） | 完全一致：8 文件 165+/34−，无 src/tests 新改动；新增仅有 C0 交付物与执行包 |
| R3 | 运行执行包检查器 | `python docs/quant_stage_plan_20260922/tools/check_delivery.py --report docs/evidence/trust-rebuild/20260922T013755-trust-c0-c17494/stage_report.json --root .` | exit 2 / `EVIDENCE_CHECK_FAILED`；11 项证据文件全部验证；错误恰为 `C0-08: gate is not PASS` 与 `unclosed blocker: C0-MAJ-01`——均为真实状态而非格式问题 |
| R4 | SHA256 抽查 | python hashlib 重算 evidence_index.csv 随机 4 行（EV-10/21/26/42） | 4/4 匹配 |
| R5 | 亲验关键代码声明（C-05：×1.01 是门槛不是限价） | `sed -n '225,240p;660,690p' src/quant/research/event_family_signals.py`、`sed -n '3558,3600p' src/quant/backtest/band_engine.py` | **证实**：`cap = float(ev.cap_price); if anchor > cap: skip_cap`（仅签发门槛）；订单 `anchor_price=anchor`（限价=决策锚价）。stock 锚不做 tick 处理。合同快照 entry_price_policy 的描述与代码一致 |
| R6 | 核对 Val 接触声明（AL-05：13 个配置） | `ls docs/research/exp-20260920-val-batch-*.md exp-20260919-hybrid-family-val.md` | 文件存在，与台账登记的来源文档一致；精确配置数未逐份重数（MINOR，不影响 C0 结论） |
| R7 | 核对阶段报告结构 | 解析 stage_report.json | 8 门状态、5 个开放问题（1 BLOCKING/1 MAJOR/3 MINOR）均有 contract_clause 与 actual_evidence；工程验收=pending（未自签） |

## 逐门裁定

| 门 | 要求 | 裁定 | 依据 |
|---|---|---|---|
| C0-01 | HEAD、dirty 状态与新进展核对 | **PASS** | takeover_state.md §1-3：remote/branch/HEAD/porcelain 原样输出；5 提交全列；关键词+分支+未跟踪三路搜索确认无 C1-C9 进展；发现"旧 C0（归因修正）与新 C0 撞名"并列为 C-11 |
| C0-02 | 个股主线与旧 ETF 主线冲突已列明 | **PASS** | contract_conflicts.csv C-01（主线定义）+ C-03（七席 vs 四席）+ C-08（Day0 三候选范围），附 agents_amendment_proposal.md 草案（未合入，正确） |
| C0-03 | 本金/费率/时钟/持仓硬边界有来源 | **PASS** | contract_snapshot.json 21 字段全带 source_path/section/commit/authority/mutable；费率、时钟、T+1、K=3 等逐项与 p3-band-contract.md/band_engine.py 对得上（R5 抽验一致）；**例外**：fee_schema.rounding_rule 无合同来源，正确地标 null+BLOCKING 而非编造（C0-BLK-01，转 C1 关闭，见下） |
| C0-04 | A/B 有效、作废、待复验记录区分 | **PASS** | evidence_index.csv 44 行，状态分布 valid 28 / valid_with_corrections 4 / superseded 3 / pending_commit 3 / invalid 1 等；受影响运行（year_returns 漏首年、归因 v1 五缺陷）单独成行 |
| C0-05 | 样本接触与验证授权未清零 | **PASS** | access_ledger.csv 9 行：2021 年初越界标签接触（B2/A，非 B1）、13 个已查看 Val 配置、混合年份文件的物理含禁区行但运行内 assert_frozen 过滤——均如实登记，未宣称"全新样本外"；未知处标 unknown（AL-09 复审文档缺失） |
| C0-06 | 无策略运行、无越权源码修改 | **PASS** | R2 亲测：会话前后 git 快照一致；change_scope_review.md 自查 + 审阅者独立比对 |
| C0-07 | 权限实际落实程度明确 | **PASS** | permissions_review.md：enforcement_level=procedural_only（public 仓库、main 无保护、零 CI、无受保护执行环境），明确"未部署"而非声称已有门禁 |
| C0-08 | 独立审阅及下一阶段范围确认 | **PASS（本文件）** | 见下节"下一阶段确认" |

## 核心发现（事实 / 推断 / 未知）

**事实**（审阅者独立复核成立的）：
1. ×1.01 追价上限在实现中只是签发门槛，实际限价=决策锚价（R5 亲验代码）。阶段 B 预登记文本与实现不一致，该落差被如实登记为 C-05/C0-MAJ-01 而非掩盖。
2. 费用/现金舍入规则在任何权威源中都不存在（合同与治理配置均未定义），实现为无舍入 float64。C0 没有编造规则，正确升级为 BLOCKING。
3. 已有 2021 年初越界标签接触与 13 个 Val 配置查看历史，不可清零，已入台账。
4. 仓库 enforcement=procedural_only；实施者未自签验收（engineering_state=pending）。

**推断**：C0 交付质量足以支撑 C1 启动；两个开放高位问题（舍入规则、入场限价语义）都有明确的后续归属阶段（C1/C3），不构成 C0 自身缺陷。

**未知**：用户复审文档 `quant_phase_ab_review_20260921` 不在仓库（MIN-02）；713 passed 无日志（MIN-01）；创业板权限无账户证据（C-07）。均不阻断 C0。

## 开放问题的处置裁定

| 问题 | 裁定 |
|---|---|
| C0-BLK-01 舍入规则未冻结 | **转 C1 强制关闭项**。审阅者依据主计划 §7（C2 数值验收）与 p3-band-contract.md 第 60 行"逐分对账"给出默认裁定：C2 参考账本以 Decimal 计算并在每笔现金变动处按 ROUND_HALF_UP 取到 0.01 元；主引擎 float 输出换算到同口径后必须逐分一致，未解释的一分差即阻断。该裁定只定义对账判定标准，不改变任何费率或金额，待用户追认；用户另有指示时以其为准 |
| C0-MAJ-01 入场限价合同-实现不一致 | **转 C3-A 必测项**（主计划 8/C3-A 已预判此问题）；C1 只登记不改 |
| C0-MIN-01 713 passed 无日志 | 延期至 C4：C4 验收时全量测试须实际运行并归档日志（tests.xml 门 C4-07） |
| C0-MIN-02 复审文档缺失 | 需用户提供或书面接受"授权依据不可独立核验"；不阻断工程阶段 |
| C0-MIN-03 未提交运行未登记 | 并入 C4 收尾的台账义务（affected_runs.csv / trial ledger 补登） |
| C-11 新旧 C0 撞名 | 采纳改名提案：仓库旧"C0"一律改称"归因修正批次（C0-attrib）"；后续文档遵循 |

## 技术意见

**accepted**（工程验收：C0 通过）。理由：8/8 门通过；实施者未自签；证据可定位、可复算（R1-R7）；发现的缺口全部被登记并路由到正确的后续阶段，无掩盖、无越权、无编造。此 accepted 仅覆盖"C0 现状接管与文档交付"范围，不代表策略有效性，也不代表引擎正确性。

**下一阶段确认（C1 进入条件）**：
- 用户在本会话的目标指令（"根据执行包一个阶段一个阶段完成 c0-c4"）构成 C1-C4 工程批次的持续性授权；C1 可启动。
- C1 必须交付的额外强制项：①冻结舍入规则（上述默认裁定或用户指示）；②interface_contract.json 中把 C-05 的门槛/限价语义双轨记录；③数据卡覆盖 access_ledger.csv 登记的混合年份文件过滤口径。
- 沿用阻断边界：不读 2021+ 行情、不跑新策略、不动费率与硬约束、不 git 提交/推送。

此意见绑定上述身份；新提交、数据或配置改变后需复核。本文件不提供真实身份认证；用户/可信平台保管最终权限。
