# 新对话交接：量化策略研究持续推进至后端

交接日期2026-09-12。用户希望在新对话执行，本次只整理代码现状、文档与可执行计划；未创建新对话、未启动新的回测或后端服务。

## 新对话第一条任务

先读根AGENTS、`docs/plans/strategy-to-backend-20260912.md`与`docs/tasks/strategy-to-backend-20260912.md`，核当前工作树/进程，完成B01披露模式和报告接线，再按阶段主审推进至真实后端联调。不要重新从R0启动器、MT276或泛化安全审计开始。

## 当前在什么阶段

R0计算已结束，目前是2023–2024历史迁移（时间窗口对应Validation，但不是通过验证或全新未见数据）。固定两个相关策略REV11/50% PV1-REV11和低换手对照，均独立20万账户。三个旧批因分钟日线汇总差异中止，无完整迁移收益。

用户已经明确选择baostock分钟主源，并反对过度防御：日线做信号和估值，分钟做成交；小差异披露并做有限压力检查，不能等全市场逐股第二来源一致才继续。结构/PIT/公司行为错误仍须实际处理。暂无确认独立Alpha，统计UNKNOWN/晋级BLOCK，2025以后及生产冻结。

## 未完成代码：不要漏接或误认已放行

- `experiments/rev11_dynamic_minute_20260912.py`：Provider新增mismatch_policy，默认strict；仅2023–2024允许research_disclose。数值合法性新增有限数/正价格/OHLC/非负量额检查；时间网格/代码/日期/adjustflag仍检查。披露模式内价格相对差<=1%、总量<=5%允许原bar继续，差异保存minute-data-discrepancies.json。此线仅临时异常线，非收益误差保证，后续须在结果前明确裁决。
- `experiments/three_account_migration_run_20260912.py`：CLI新增--mismatch-policy，manifest记录，差异并入data-issues；因此完整账户仍可标DATA_ISSUE，不能自动晋级。
- `experiments/three_account_migration_report_20260912.py`：尚未修改，现有DATA_ISSUE路径不输出metrics；必须区分可描述的分钟差异与无效数据/公司行为，保留不确定性，不以删issues绕过。
- 已执行`python -m unittest tests.test_migration_batch_integration.MigrationBatchIntegrationTest tests.test_migration_minute_provider`，5项通过；另真实002356记录strict中止、research_disclose返回48根且留差异。未证明新增模式完整三账户端到端，需补关键负例和报告覆盖。无需因本次文档整理重跑全系统。
- 上一对话说“现在启动”后被打断：实际目录仅accounts-1/-2/-3，**未启动新批**。启动前先完成B01、主审留痕，创建新目录，绝不覆盖旧批。

## 可直接复用的证据

| 内容 | 路径 |
|---|---|
| 冻结配置 | configs/research/three-account-migration-20260912.json |
| 已审核迁移信号 | artifacts/three-account-migration-signals-20260912-1 |
| 市场输入/15项公司行为疑点 | artifacts/three-account-migration-market-inputs-20260912-1 |
| 旧账户与原始分钟 | artifacts/three-account-migration-accounts-20260912-1、-2、-3 |
| 问题日并集原始记录及订单诊断 | artifacts/migration-20230901-minute-inventory-20260912-1 |
| 源探针/单日Tushare转换 | artifacts/migration-minute-source-probe-20260912-1 |
| 详细问题处置历史 | docs/experiments/migration-minute-data-interruption-20260912.md |
| 候选汇总 | docs/plans/candidate-batch-review-20260912.md |

第三批曾将600000单日替换为Tushare；新的baostock主批不要整盘无审查继承覆盖优先级，应只复用baostock原始记录。15项公司行为未必实际持有，但不能先写不影响。

## 后台进程与工作树

交接期间已用工具核实session52027活跃：按每3665秒请求Tushare603799.SH、600602.SH的2023-09-01分钟，首次计划22:03:34北京时间；尚无结果。状态文件hourly-probe-state.json。未来核实真实进程，不根据状态文件重启；观察句柄失效时查进程/产物再决定。它是可选抽查，不阻断baostock主线，禁止继续每分钟发API请求。

没有活跃优化子代理的已知证据，优化已交付；主对话直接执行并最终审核，必要独立子代理GLM-5.3/high或DeepSeek Flash/high。仓库有大量历史未提交修改，应用并行开发；不要reset/checkout/批量清理/提交或覆盖他人代码。当前两个研究模式代码文件也必须保留。

## 后端目标与现有接点

用户最新要求计划推进至后端，覆盖此前“接口只记录暂不做”的阶段安排；本轮只写计划，新对话按研究与工程阶段实施。

已有消费者`apps/quantdesk/server/quantdesk_server/strategy.py`及`apps/quantdesk/verification/CONTRACT.md`，使用quantdesk.strategy_adapter.v1、POST /v1/evaluate。消费者实际build_request包含账户、人工成交、input_digest、策略/行情/账户版本与operation，并校验返回身份、时间和发布状态。新对话读最新文件，不依赖本文猜接口。

算法统一计算手续费/保本/资金仓位/标的价位，前端/Pi不得另算；账户资金和费率不同必须得到对应真实计算，200k不是硬编码产品。先研究/影子不可执行模式实际HTTP联调，再由独立发布决定是否人工实盘。不以空壳服务或mock通过代替真实算法接入。

## 旧因子可否重测

可以有理由地有限复测，不全体复活。先给每个旧淘汰结论找到证据及原因，数据/实现问题影响者优先；换分钟线不能自动解决弱IC/年度不稳/过拟合/集中度。新周期/方向/退出是新假设，先登记。详见主计划P2/P3。

## 交接完整性

旧AGENTS42,579字节归档至docs/archive/AGENTS-before-backend-handover-20260912.md，SHA256为770aa43107c0d9a04b58053c843551d533b0949938087bdda2fb1da2b5c84e89；同名JSON记录。AGENTS现仅当前规则，历史正文不删除。新主计划/任务板优先，旧handover和R0计划保留参考。
