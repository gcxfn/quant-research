# 独立审阅报告：C1（数据隔离与接口合同）

- 审阅对象 run：`20260922T020344-trust-c1-479c46`
- 审阅者身份：主对话会话（ZCode / GLM-5.3），与实施者子代理不同会话；同时担任本轮编排者。
- 审阅时间（本机）：2026-09-22 02:20—02:35
- 绑定身份：代码 HEAD `ae226d9` + 工作树新增（`src/quant/data/{temporal_contract,dev_sandbox,dev_sandbox_export}.py`、`tools/{export_dev_sandbox,run_record}.py`、`tests/test_{temporal_isolation,dev_sandbox}.py`、沙箱 `data/processed/dev-sandbox-20260922/`、证据目录 34 项）；interface_contract.json `contract_id` 以文件 SHA256 为准（EV-01 已登记）。

## 审阅范围与未覆盖范围

**范围**：C1 全部 8 项门；重点独立复核数据隔离的真实性（不依赖实施者自报）。**未覆盖**：未审查 `dev_sandbox_export.py` 全部行（以输出侧独立扫描代替）；未重放 2026-09-22 凌晨归因批次；沙箱未含分钟线/复权因子/其余事件家族（实施者已列 limitations）——这些不影响 C1 门。

## 独立动作（实际执行）

| # | 动作 | 命令 | 结果 |
|---|---|---|---|
| R1 | 检查器 | `python docs/quant_stage_plan_20260922/tools/check_delivery.py --report docs/evidence/trust-rebuild/20260922T020344-trust-c1-479c46/stage_report.json --root .` | `EVIDENCE_FILES_OK`，exit 0；34 项证据；junit 41 tests / 0 failures / 0 skipped |
| R2 | 越权改动核对 | `git status --porcelain` | 已跟踪文件与 C0 后快照一致（仍为既有 8 项修改）；新增仅 C1 交付物 |
| R3 | 测试独立重跑 | `.venv/Scripts/python.exe -m pytest tests/test_temporal_isolation.py tests/test_dev_sandbox.py --junitxml=reviewer_rerun_temporal.xml` | **41 passed in 0.49s**（存 `reviewer_rerun_temporal.xml`） |
| R4 | 沙箱 2021+ 独立扫描 | polars 逐文件 scan 12 个 parquet 的日期 min/max | 全部 ≤ 2020-12-31（warmup 2014-03-03..2014-12-31 独立成文件，用途=特征历史）；**无一文件含 2021+ 行** |
| R5 | 加载器拒绝亲测 | 构造 4 类非法访问 | 越界相对路径→`PathNotAllowedError`；伪造 dataset_id `val-2021-2024`→`UnknownDatasetError`；manifest 未登记成员→`PathNotAllowedError`；请求 end=2021-06-30→`DateRangeError`（读前拒绝）；读后还有 observed_max 复核断言 |
| R6 | 合法读取与缓存键 | `reg.read('forecast_event')` 等 | 18,042 行，ann 2018-09-04..2020-12-31；cache_key 生成含数据身份的 SHA256 |
| R7 | interface_contract 检查 | 逐节阅读 | 舍入规则按审阅者默认裁定冻结（标 `reviewer_default_pending_user_ratification`，范围明确到 applies_to/does_not_apply_to、零容差）；`trigger_cap`/`limit_price` 双轨必填且写明实现事实与 C3 待验关系；时间四件套不变式、六类 ID、七张表、C2/C3 下游义务均落地 |
| R8 | 删失审计与 C0 台账交叉核对 | 解析 censoring_audit.csv | 102 个 B1 事件窗全部 `window_complete=True`（与 C0 结论"B1 无越界"一致）；86 个 B2/A 家族 2020-12 边界锚点全部 `window_complete=False` 且保留不删；44 只退市证券单独成行——与 access_ledger AL-01 的越界接触登记互相印证 |
| R9 | 测试非同义反复抽查 | 读 `test_pm_change_leaves_1130_output_identical` 及其**正向对照** `test_pm_change_does_change_1500_output_positive_control` | 存在正向对照，"输出不变"不是因为决策函数根本不看行情；freshness gate、TV-B05/B06/B25/B26/B27/B28 均有实质断言 |

## 逐门裁定

| 门 | 裁定 | 依据 |
|---|---|---|
| C1-01 Dev 隔离与许可预热 | **PASS** | R4 独立扫描 + R5 拒绝亲测 + manifest（12 文件/19,501,006 行/实测范围）；warmup 单列 |
| C1-02 available_at/标签终点断言 | **PASS** | R3（41 项含时间断言）+ R7 时间不变式 |
| C1-03 午间不可见午后价格反证 | **PASS** | R9（含正向对照）；范围说明见下"局限" |
| C1-04 未来资格不影响当期预测 | **PASS** | R9（test_future_price_and_eligibility...） |
| C1-05 数据卡 | **PASS** | data_cards.md 七类数据卡含已知缺陷（涨跌停表 3 个缺口日与双向不一致、4 只缺半日 bar 均登记） |
| C1-06 预告历史版本与字段合法性 | **PASS** | announcement_version_audit（18,042 行：valid 15,215/point 929/missing 1,898/invalid 0）+ B1 102 事件抽核 102/102；PIT 结论诚实（"快照不能证明当时可得"逐行标注） |
| C1-07 ID 接口冻结 | **PASS** | R7；schema_version 落地，C2/C3 义务写明 |
| C1-08 边界与缺失样本保留披露 | **PASS** | R8 |

## 核心发现

**事实**：Dev 沙箱经独立扫描确认无 2021+ 行；加载器在路径、dataset_id、日期三个维度拒绝越界且读后复核；时间反证测试含正向对照；C0 三条强制项（舍入规则、cap/limit 双轨、混合文件过滤升级）全部落地；B1 102 事件窗口完整性与 C0 台账交叉一致。

**推断**：C2/C3 的技术前提（冻结接口 + 沙箱 + 时间断言）已具备。

**未知/局限**（不阻断，登记去向）：
1. C1-03/04 的"输出不变"证明在合同层参考决策函数上完成，**尚未在真实策略链（event_family_signals→band_engine）上重证**——该义务属 C3-B（策略到订单语义链）与 C4 重放锚，本审阅已将其记为 C3 必查项。
2. 涨跌停表 3 个整日缺口与 (symbol,date) 双向不一致、4 只缺半日 bar 的 symbol：成因未知，C1 已登记不归因；C3 独立撮合若依赖涨跌停表需按数据卡披露的缺口口径处理。
3. 预告源是 2026-09-09 快照，历史版本可得性不可证——"有数值修订的臂不具完整 PIT 证据"的标记保留，属 C5 研究判定输入。
4. 6 个 MINOR 开放项（沙箱未含分钟线/复权因子/其余家族、run_record 工具早期内存低报已修正等）均不改变 C1 门结论。

## 技术意见

**accepted**（工程验收：C1 通过，8/8 门）。检查器 `EVIDENCE_FILES_OK`；实施者未自签。本 accepted 只覆盖"数据隔离与接口冻结"范围，不证明策略有效性，不授权 Val。

**下一阶段确认**：C2 与 C3 的进入条件均已满足；两者可先后实施（本轮按用户指令串行：先 C2 后 C3，避免同机资源竞争）。C2 必须吃 interface_contract.json 的 fills/corporate_actions/ledger_snapshots 合同并按 `fee_schema.rounding_rule` 逐分对账；C3 必须关闭 C-05 的 cap→限价链条验证（含真实策略链的 11:30 不变性重证，见局限 1）。

此意见绑定上述身份；新提交/数据/配置改变后需复核。
