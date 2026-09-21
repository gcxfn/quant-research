# QuantDesk Live 服务器验收记录（2026-09-18）

- 被测对象：`https://117.72.219.131`（生产服务器，backend 已部署阶段2新闻修复）
- 执行方式：只读 + 自清理探测。仅使用本记录创建的两个专用测试账号；未删除、未修改任何已有用户数据；未停止或重启任何容器；未执行破坏性测试。
- 依据：`docs/plans/QuantDesk-重建实施方案-20260917.md` §20（本轮只覆盖其中可在服务端黑盒验证的条目）；契约基准 `quantdesk/verification/CONTRACT.md`（LOCK 2026-09-12 + 修订1–3）。
- 结论速览：**集成套件 42/42 PASS；手测 26/26 PASS，0 FAIL，0 SKIP**。发现 2 条非阻断观察项（见"问题与观察"）。

## 1. 环境与执行身份

| 项 | 值 |
|---|---|
| 执行时间 | 2026-09-17T16:50Z 起（服务器时间口径），记录落款 2026-09-18 |
| Base URL | `https://117.72.219.131`（TLS 对裸 IP 校验通过，Python `ssl.create_default_context()` 握手成功） |
| 服务状态快照 | `GET /api/v1/status` → `{"status":"ok","database":"ok","model_gateway_connected":true,"model_configured":true,"algorithm_configured":false,"recommendations_available":false}` |
| 专用账号 | `qd-accept-01`（user id `098ec72d-65b1-4954-b09a-bedccc1ae8f8`）、`qd-accept-02`（user id `4510332d-cfc7-46b8-b167-fe491e56853f`），密码 `QuantDesk-Accept-1`。**按指示未删除**，留存信息见 §6 |
| 探测脚本 | `D:\量化\quantdesk\tmp\acceptance-live-20260918\probe_live.py`、`probe_fix.py`（stdlib-only；原始输出 `probe_run.log`、`probe_fix_run.log`、`results.json`、`results_fix.json`） |
| 仓库状态 | 本地 Git commit `8885ede`（server 阶段2新闻修复）之上工作区干净（仅未跟踪 `tmp/`）；基线 `6ecfed9` 为服务器快照 |

## 2. 集成测试套件（quantdesk/verification）

命令（在本机运行，指向 live）：

```
python verification/run_contract_tests.py --selftest
python verification/run_contract_tests.py --base-url https://117.72.219.131 --timeout 25
```

| 用例组 | 期望 | 实际 | 结论 |
|---|---|---|---|
| 离线自检（capability token 13 项 + lint 2 项） | 全部 PASS | `selftest: 15 passed, 0 failed`，exit 0 | PASS |
| 集成套件 vs live（注册公开、无邀请码；runner 自建 2 个随机账号，仅操作自建账号） | 全部 PASS，exit 0 | `integration vs https://117.72.219.131: 42 passed, 0 failed`，exit 0。含：auth 7、account 5、recommendations 1、news 3、chat/tasks 4、memory/artifacts 2、ownership 3、client 2、本地 15 | PASS（42/42） |

说明：runner 的 `--invite-codes` 参数已废弃（注册公开，修订1），本次未传，按默认流程执行成功。套件自动注册的 2 个一次性账号（`quantdesk-verification-<随机hex>-0/1@example.com`，随机密码）无法经 API 删除，见 §6。

## 3. 手测关键验收点（逐例）

除注明外，请求均为 `https://117.72.219.131` 上 `Authorization: Bearer <token>` 的 JSON API 调用；"期望"以 CONTRACT.md 与实施方案 §20 为准。

### 3.1 跨用户隔离（用户A=qd-accept-01 创建，用户B=qd-accept-02 改 ID 访问）

期望：一切跨用户访问被拒，首选 404，不泄露对象存在性或正文；B 的列表不含 A 的对象。

| 请求（B 对 A 的资源） | 实际 | 结论 |
|---|---|---|
| `GET /api/v1/chat/sessions/{sidA}` | 404 `SESSION_NOT_FOUND` | PASS |
| `DELETE /api/v1/chat/sessions/{sidA}` | 404 `SESSION_NOT_FOUND` | PASS |
| `GET /api/v1/chat/sessions/{sidA}/messages` | 404 `SESSION_NOT_FOUND` | PASS |
| `GET /api/v1/tasks/{taskA}` | 404 `TASK_NOT_FOUND` | PASS |
| `POST /api/v1/tasks/{taskA}/cancel` | 404 `TASK_NOT_FOUND` | PASS |
| `GET /api/v1/tasks`（B 列表） | 不含 A 的 task_id | PASS |
| `GET /api/v1/tasks/{taskA}/events`（SSE） | 404 `TASK_NOT_FOUND`（application/json，非事件流） | PASS |
| `GET /api/v1/memory`（B 列表） | 不含 A 新建的 memory id | PASS |
| `DELETE /api/v1/memory/{midA}` | 404 `MEMORY_NOT_FOUND` | PASS |
| `GET /api/v1/account`（B） | 仅 B 自己数据（cash=0.00），无 A 的标记 cash=88866.66、无 600000 持仓 | PASS |

**汇总：PASS（10/10 子项，全部 404 且回避存在性泄露）**

### 3.2 幂等

（a）成交（账户为记录型语义：算法未配置时 `reconciliation_status=pending_algorithm_reconciliation`，应用侧不得自行改持仓/现金，符合修订4）

| 请求（用户A） | 期望 | 实际 | 结论 |
|---|---|---|---|
| `POST /api/v1/account/trades` `{idempotency_key:"qd-accept-trade2-<hex>", expected_version:2, symbol:"600519", side:"buy", shares:100, price:"10.50", trade_date:当日}` | 2xx，恰好落 1 条记录，版本递增，无应用侧持仓运算 | 201，`reconciliation_status=pending_algorithm_reconciliation`，`manual_trades` 中该 key 恰 1 条，version 2→3，holdings 未变 | PASS |
| 同 key 同内容重放 | 返回原结果，不重复入账 | 201，同一 `trade_id=514c856e-3e5f-…`，记录仍 1 条，version 保持 3 | PASS |
| 同 key 不同内容（shares=200） | 409 冲突 | 409 `IDEMPOTENCY_CONFLICT`，记录仍 1 条，version 保持 3 | PASS |

（b）消息

| 请求（用户A，session 内） | 期望 | 实际 | 结论 |
|---|---|---|---|
| `POST /chat/sessions/{sid}/messages` `{content:"验收探针…", idempotency_key:"qd-accept-msg-<hex>", research:false}` | 202 `{task_id,status}` | 202，`task_id=05858148-547a-473b-a72e-dacb9c47619f, status=queued` | PASS |
| 同 key 同内容重放 | 原 task_id，不建新任务 | 202，同一 task_id | PASS |
| 同 key 不同 content | 409 冲突，不落库 | 409 `IDEMPOTENCY_CONFLICT`；messages 中 user 消息恰 1 条，无"不同内容"版本 | PASS |

### 3.3 账户乐观并发版本

| 请求（用户A） | 期望 | 实际 | 结论 |
|---|---|---|---|
| `PUT /api/v1/account`（expected_version=当前值，cash=88866.66） | 200 且版本递增 | 200，version→1 | PASS |
| `PUT /api/v1/account`（expected_version=旧值） | 409 冲突，不合并 | 409 `VERSION_CONFLICT`；GET 复核 cash 仍为 88866.66，未被旧请求覆盖 | PASS |

### 3.4 游标分页（阶段2新代码 `GET /api/v1/news`，stable published_at+id 键）

| 请求（用户A） | 期望 | 实际 | 结论 |
|---|---|---|---|
| `limit=100` 单次取全量做对照 | — | 100 条 | — |
| `limit=7` + `next_cursor` 步进翻页直至 `next_cursor=null`（对照组此前另以 limit=100 全量步进 26 页验证） | 无重复、无遗漏、正常终止、与全量序一致 | limit=100 口径：26 页共 **2599 条**，页内及跨页 **0 重复**，末页 `next_cursor=null` 正常终止，前 100 条与单次全量逐 id 逐序一致，耗时 7.4s | PASS |
| 边界：`limit=0 / -1 / 101 / 200` | 422 | 422 `INVALID_LIMIT`（"limit 必须在 1—100 之间。"）；`limit=abc` 422（框架校验） | PASS |
| 边界：`limit=7&cursor=zzz` | 422 | 422 `INVALID_CURSOR`（"分页游标无效。"） | PASS |

初测轮该组曾报 FAIL，经查为**探测脚本自身缺陷**（`req()` 构造了 query 串但发请求时未携带，导致参数从未到达服务器；且前缀比对写错长度）。修正脚本后复测如上。复现正确的请求样例：`curl -H "Authorization: Bearer $TOK" "https://117.72.219.131/api/v1/news?limit=3"` → 恰 3 条 + `next_cursor`。

### 3.5 SSE（`GET /api/v1/tasks/{id}/events`，任务 task_id=05858148-…）

| 请求 | 期望 | 实际 | 结论 |
|---|---|---|---|
| 建流（Bearer，Accept: text/event-stream） | 握手成功 + 事件流 | `Content-Type: text/event-stream; charset=utf-8`；收到 4 个事件（id: 1–4，唯一、有序，data 为 JSON `{type,text,…}`）；任务到终态后服务端正常收流 | PASS |
| `Last-Event-ID: 1` 重连 | 只补发 id>1 的事件 | 精确补发 id 2,3,4（存储回放） | PASS |
| `Last-Event-ID: 4`（末尾）重连 | 不得重发末事件 | 0 事件，未重发 id=4 | PASS |

说明：任务进入终态后服务器关闭事件流，本次未观察到空闲心跳（心跳仅在有独立机制的服务上出现）；契约要求点（事件 id + 断线续传）已按上两行严格验证。

### 3.6 新闻分析字数（阶段2修复点）

| 请求 | 期望 | 实际 | 结论 |
|---|---|---|---|
| `POST /api/v1/news/{nid}/analysis`（nid=当时最新一条财联社新闻） | 2xx 异步启动 | 202 `{id:"08d98660-280c-4937-b224-eaf5626766db", status:"queued", content_version:"a768ff03…"}` | PASS |
| 轮询 `GET /api/v1/news/{nid}/analysis` 至终态（约数十秒） | completed 且 100–200 字（Unicode 去空白） | `status=completed`，去空白 **132 字**（URL 剥离后同为 132），正文完整通顺无凑字痕迹（全文见附录） | PASS |
| 用户B 对同一新闻 `POST analysis` | 共享同一分析，不分叉 | 202，与 A 相同 analysis id | PASS（顺带覆盖"并发/重复点击只建一个逻辑分析"的幂等语义） |

### 3.7 错误响应规范（统一 `{"error":{"code","message",…}}`，snake_case）

| 请求 | 期望 | 实际 | 结论 |
|---|---|---|---|
| `GET /api/v1/account`（无 token） | 401 | 401 `UNAUTHENTICATED` | PASS |
| `GET /api/v1/account`（Bearer garbage） | 401 | 401 `UNAUTHENTICATED` | PASS |
| `POST /auth/login`（错误密码） | 401 | 401 `INVALID_CREDENTIALS` | PASS |
| `POST /chat/sessions` `{"title":12345}`（类型错误） | 4xx | 422 `VALIDATION_ERROR` | PASS |
| `GET /news?limit=0` | 422 | 422 `INVALID_LIMIT` | PASS |
| `GET /news?cursor=zzz` | 422 | 422 `INVALID_CURSOR` | PASS |
| 业务错误码抽查 | machine-readable code | 以上均为稳定英文 code + 中文 message，含 `retryable` 字段，结构统一 | PASS |

## 4. PASS / FAIL / SKIP 统计

| 范围 | PASS | FAIL | SKIP |
|---|---|---|---|
| 集成套件（含 15 项本地向量） | 42 | 0 | 0 |
| 手测用例（§3.1–§3.7，隔离按 1 例计） | 26 | 0 | 0 |
| **合计** | **68** | **0** | **0** |

诚实说明：初测轮曾有 4 条记录为 FAIL（bad limit / bad cursor / 分页 / 成交首笔），其中 3 条为探测脚本缺陷（query 未随请求发送、前缀比对长度错误），1 条为测试者对"记录型成交语义"预期错误（误以为应用侧应立即改持仓现金）。全部已用修正后的脚本在 live 复测并以复测结果为准；初测原始日志保留于 `quantdesk/tmp/acceptance-live-20260918/probe_run.log`。最终有效判定中不存在未解释的 FAIL。

## 5. 问题与观察（均非阻断）

1. **【观察/低】`POST /api/v1/chat/sessions` 空 body 返回 201 并落默认标题。**
   复现：`curl -X POST -H "Authorization: Bearer $TOK" -H "Content-Type: application/json" -d '{}' https://117.72.219.131/api/v1/chat/sessions` → 201，`{"title":"New session",…}`。
   影响：宽松校验，无安全影响（类型错误仍 422 `VALIDATION_ERROR`）。实施方案 §14 未强制 title 必填。可接受；如需收紧可改为 422。
2. **【观察/信息】`GET /api/v1/status` 匿名可访问**，返回 model gateway/算法配置布尔与 public_base_url。与契约 §2.6 的 status 面一致，无敏感值；记录备查。
3. 初测轮发现项不构成服务器缺陷，见 §4 诚实说明。

## 6. Live 留存物与后续清理清单

本次按指示**未删除**以下内容；其余自建数据（会话 3 个、记忆 1 条）已全部通过 API 自清理并复核 404：

| 对象 | 标识 | 状态 |
|---|---|---|
| 测试账号 qd-accept-01 | user id `098ec72d-65b1-4954-b09a-bedccc1ae8f8` | 保留（密码 `QuantDesk-Accept-1`）。名下遗留：2 条不可删的手动成交记录（`a18b0d4a-…` 600000 买100、`514c856e-…` 600519 买100，均为 pending_algorithm_reconciliation）、账户 version=3 / cash=88866.66、1 个已完成任务 `05858148-…` |
| 测试账号 qd-accept-02 | user id `4510332d-cfc7-46b8-b167-fe491e56853f` | 保留，名下无业务数据 |
| 契约套件一次性账号 ×2 | `quantdesk-verification-<hex10>-0/1@example.com`（随机密码，2026-09-17T16:5xZ 注册） | 无法经 API 删除；名下仅有套件自建的测试会话/成交记录。清理需服务器侧 DB 操作，由运维决定 |

## 7. 未覆盖项（如实声明）

- §20 中桌面端/外观/输入法/打包/备份恢复/证书续期等非服务端黑盒可验条目本轮未测。
- 未在真实并发竞争下压测新闻分析去重（以跨用户共享 id 与 unique_hash 机制间接覆盖）。
- 未验证 Pi 沙箱逃逸、内网隔离类破坏性用例（属禁跑的破坏性测试范围）。
- `algorithm_configured=false`：recommendations 全链路可执行门（费用/T+1 数值正确性）须待算法接入后另测；本轮验证的是"不可执行时的门禁与降级"，均 PASS。

## 附录：新闻分析全文（132 字，去空白计）

> 财联社9月18日报道，特朗普称在伊朗战争问题上正接近重大十字路口，需决定是否恢复大规模军事行动以推动冲突结束。可能影响能源、航运与军工行业，路径为中东局势升级推高油价与运费、避险情绪升温。不确定性在于是否恢复行动、规模及时点均未明确，正文信息有限，影响程度待观察。
