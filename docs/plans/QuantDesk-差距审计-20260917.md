# QuantDesk 差距审计（2026-09-17）

> 审计对象：`D:\量化\quantdesk-server\apps\quantdesk\`（源码包解压，下称 **apps**）与 `D:\量化\quantdesk-server\quantdesk\`（服务器 live 快照，含 private/，本次只读未动、未外传其内容，下称 **live**）。
> 对照基准：`docs/plans/QuantDesk-重建实施方案-20260917.md`（重点第 5、8–14、18、20 节）。
> 审计方式：纯只读源码走读 + 文件级 diff + 测试清单核对，未运行任何服务端/桌面代码。
> 重要前提：**live 快照比 apps 版新**。两棵树文件清单一致（live 另有 `private/model.env` 与 `infra/_shared/qd_security/secrets.py` 真实密钥，均未读取内容），但 12 个文件 live 领先（见附录 A）。以下结论按"以 apps 为主、live 补充"的口径给出，凡 live 已修复的偏差均单独标注。

## 0. 总体结论

| 阶段（计划 §18） | 状态 | 一句话依据 |
|---|---|---|
| 阶段0 恢复核查与接口冻结 | **已实现** | CONTRACT.md 三次修订、verification 报告、边缘部署证据齐备 |
| 阶段1 可启动桌面与账户 | **部分实现** | 账户后端完整；EXE/图标缺失、视觉违反黑白灰、注册三字段 |
| 阶段2 真实新闻与共享分析 | **部分实现（服务端主体完成）** | 采集/去重/更正/合并正确；字数、筛选、分页、归档四处偏差 |
| 阶段3 私人 Pi 与后台任务 | **已实现（服务端口径）** | 持久队列/SSE 重连/取消/中断恢复/记忆/工件全部在码；桌面为内嵌 dock 非独立窗 |
| 阶段4 联网与 Python 研究 | **已实现（待现场验收）** | egress netguard+钉扎 IP、无网沙箱+资源上限；无人为配额属实 |
| 阶段5 策略接线 | **部分实现** | 适配器合同+发布门禁+等待状态完成；真实算法未接（algorithm_configured=false） |
| 阶段6 整体试用与发布 | **未实现/未验证** | 无版本化 EXE、无图标、证书证据停滞、无备份恢复演练记录 |

已确认的服务器事实（容器健康、新闻实时采集、DeepSeek 端到端共享分析通过、`algorithm_configured=false`）与代码路径一致：`server/quantdesk_server/app.py` 的 `/api/v1/status` 中 `algorithm_configured = bool(settings.strategy_url)`，未配置时建议/情景统一失败为结构化 `ALGORITHM_NOT_CONFIGURED`（`strategy.py`），不存在假建议路径。

---

## 1. 阶段逐项审计

### 阶段0：恢复核查与接口冻结 —— 已实现

证据：
- `verification/CONTRACT.md`：锁定协议转写 + 2026-09-12 三次修订（amendment 1 公开注册、amendment 2 校验器一致性、amendment 3 移除一切 AI 用量配额）。
- `verification/REPORT.md`：独立验证记录，含 14/14 本地向量自检、38 通过/12 缺陷确认的交叉验证（V-004…V-011，其中配额类 V-009/V-010 已在现 config 中移除）。
- `ops/edge/DEPLOYMENT_EVIDENCE.md`：宿主、镜像 digest、端口、证书签发诊断全过程。
- `compose.yaml` + `infra/env/env.example`（仅 CHANGE_ME 占位符）+ `.env.example`。

### 阶段1：可启动桌面与账户 —— 部分实现

已实现（服务端）：
- 注册/登录/登出/me：`server/quantdesk_server/auth.py`；PBKDF2-HMAC-SHA256 20 万次迭代 + 随机盐、仅存 token 哈希（`security.py`、`models.SessionToken`）；统一错误 `INVALID_CREDENTIALS`；按 IP+全局限速；最小密码 8 位（`config.min_password_length`）。
- 账户：`account.py` 乐观并发（`expected_version` 不匹配返回 409 `VERSION_CONFLICT`）、十进制字符串传输（`money_string/decimal_string`）、证券代码归一（`sh600000` 风格，`normalize_symbol`）、费率仅校验不计算、成交幂等（同键同内容返回原记录、不同内容 409 `IDEMPOTENCY_CONFLICT`）、登记即 bump version 并标 `pending_algorithm_reconciliation`。应用侧无任何金融计算（文件头注释与实现一致）。

偏差（详见 §3）：
- **无版本化便携 EXE**（见 §2.1 专项）。
- **无 Q 图标资产**：`desktop/` 全树无 .ico/.svg/.png，`electron-builder.yml` 无 icon 配置（计划 §4.3）。
- **视觉违规**：`desktop/src/styles.css` 主题为青色强调（`--cyan:#2dd4bf`）+ 渐变光晕（`radial-gradient`、`box-shadow rgba(45,212,191,…)`）+ 大量 8–11px 字号，直接违反计划 §4.1/§4.2（黑白灰、正文 14px、"避免 8—10px 中文"）。
- **注册表单三字段**：桌面注册为 邮箱+密码+显示名称（`src/App.tsx` 92/110–111 行）；apps 服务端 `auth.py` 也要求 `email`（正则校验）+必填 `display_name`。live 服务端已改为接受 `username`（2—32 位中英文数字下划线点短横线，`_USERNAME_RE`）、`display_name` 可省略默认取用户名、错误文案中文化——**live 符合计划 §8.1，apps 与桌面端尚未跟进**。
- 无邀请码：两版均无（apps `auth.py` 第 1 行"no invite codes"；CONTRACT.md amendment 1）。`QUANTDESK_INVITE_CODES` 只作为 `verification/run_contract_tests.py` 的遗留 CLI 参数存在（默认 "public"，实际不生效），不属于偏差。`models.Invite` 表与 `security.new_invite_code` 为死代码，建议清理。
- 界面偏好（上次查看日期、窗口尺寸）未持久化（计划 §3.2）。

### 阶段2：真实新闻与共享分析 —— 部分实现（服务端主体完成）

已实现：
- 采集经 egress 分段服务拉取，来源白名单文件 `server/config/news_providers.json`（财联社电报 `use_basis: user_confirmed_personal_use`，与计划 §10.1 的"记录实际依据、不伪写授权"一致）；`infra/egress-proxy/sources/registry.json` 同步记录权利与出处。
- 去重主键：`models.py` `uq_news_provider_guid`（provider_id+source_guid 唯一）；更正 = `content_version`（sha256(guid+title+body)）变更 → `status="corrected"`，live 版进一步把旧共享分析标记 `failed/NEWS_CONTENT_CHANGED`（`news.py` diff），旧分析不会冒充新正文（计划 §10.3 达成）。
- 共享分析合并键：`unique_hash = sha256(content_version+model+prompt_version)`，数据库唯一约束 + IntegrityError 复查保证并发只产生一个逻辑任务（`news.py start_analysis`）；提示词仅含新闻公开内容，无用户上下文（verification 测试 `news: analysis shared, no account context`）。
- 按上海时区逐日 JSONL 归档（`_archive`，原子写 + fsync）；重启时把 queued/running 分析标记失败（live `app.py`，`INTERRUPTED_BY_RESTART`）。
- 字数 100—200 服务端校验（`news_target_min/max_chars`，不足 `MODEL_RESULT_TOO_SHORT` 判失败）。

偏差（计划 §10.2/§10.4/§10.5、验收 §20.4）：
1. 超长处理为**截断加"（已截断）"**，而计划要求"一次精简重写，仍不满足判失败、不得截断"（apps `news.py` 244–245 行；live 未改）。
2. **相关性过滤在内存中进行**：先 `limit(100)` 再 Python 过滤（`list_news`），违反"筛选在数据库查询阶段执行之后再分页"。
3. **日期筛选按 `observed_at`（采集时间）而非发布时间**，与"日期按新闻发布时间转换到 Asia/Shanghai"不符；且无 `发布时间+ID` 游标分页（固定 limit 100）。
4. 归档为单层 `data/newsarchive/<day>.jsonl`，无计划 §10.2 的 `cls/2026/09/17/items.jsonl+manifest.json` 布局，无 `news_archive_jobs` 对账/补写表（验收 §20.4 最后一项不满足）。
5. 分析合并键缺 `output_schema_version` 维度（计划 §10.4；现有三要素+news_id 隐含，属可接受近似，记录在案）。
6. 采集线程 `except: continue` 吞错：apps 版来源故障无状态暴露；live 已加 `news_source_status` 与 `/api/v1/news` coverage 状态（"财联社暂时无法更新"文案），**live 已修复**。
7. 采集刷新周期 apps 默认 900s，**live 已改 60s**（`config.py` diff），符合"60 秒量级"。

### 阶段3：私人 Pi 与后台任务 —— 已实现（服务端口径）

已实现：
- SDK 接入：`pi/src/runner.ts` 使用 `@earendil-works/pi-coding-agent@0.85.1`（`pi/package.json` 锁定）`createAgentSession`，`noTools:"builtin"` 禁用内置 Shell，仅挂自定义工具；`pi/src/sessions.ts` 私人会话持久化（worker 测试"real Pi SDK persists and restores a private external session"）。
- 持久任务：`server/quantdesk_server/tasks.py` —— `skip_locked` 领取、幂等键唯一索引（`uq_tasks_user_idem`）、事件序号 `UPDATE…RETURNING` 单调递增、`TaskEvent(task_id,seq)` 唯一约束；worker 启动时把 running 标记 `INTERRUPTED_BY_RESTART` 并保留已收文本（计划 §11.4"关闭 EXE 任务继续、重启标中断"达成）。
- SSE：`GET /tasks/{id}/events` 支持 `Last-Event-ID` 续传、`: keepalive` 心跳、终态自动收流；桌面侧在主进程 fetch 流解析并转发（`desktop/electron/ipc.ts qd:stream:start`）。
- 取消：`POST /tasks/{id}/cancel` 置位 + 同步 `DELETE` pi-manager 运行（`tasks.py cancel`→`worker.cancel`）；Pi worker 显式 abort（`runner.ts`），测试"explicit cancellation aborts a streaming SDK run"、"client disconnect does not cancel backend-owned run"。
- 记忆与工件：`memory_artifacts.py` 列表/保存/按 ID 删除、工件鉴权下载（所有权校验 + 安全文件名 + `nosniff`）；Pi 写记忆需请求级意图门（`_MEMORY_INTENT/NEGATION` + `internal.py` `MEMORY_NOT_AUTHORIZED`），测试"memory writes require explicit intent"。
- 能力令牌：`capability.py` HMAC 令牌按 (user,task,scopes,ttl) 签发，长任务由 manager 凭 manager token 换新（`internal.py /tasks/{id}/capability/renew`），网关侧回验 active task（`infra/model-gateway/app/security.py require_active_task`）。
- 无配额属实：服务端 Settings 无任何每日/Token/轮数/时长额度字段（仅队列并发 1+1 与沙箱 120 秒技术保护）；amendment 3 落实。

偏差：
- **AI 窗口非独立 BrowserWindow**：聊天为应用内底部 dock（`App.tsx chat-dock`），且 `webview.setVisible(!accountOpen && !tradeOpen && !chatExpanded)` —— **展开聊天即隐藏同花顺行情**，直接违反验收 §20.1"主窗口同花顺与 AI 窗可同时使用，不因聊天隐藏行情"。计划 §5.6 允许阶段性用内嵌浮窗但"必须明确兼容限制"，桌面 README 未声明这一隐藏行为。
- Enter 发送未检查输入法组词状态（`onKeyDown` 无 `isComposing` 判断），验收 §20.1"中文输入法不误发送"存在缺陷。
- SSE 事件类型命名与计划 §14.2 不同（`queued/tool/text_delta/done/error` vs `task_started/tool_started/…`），语义覆盖但无 `artifact_created` 事件；任务终态 `canceled/failed`（interrupted 并入 failed+`INTERRUPTED_BY_RESTART` 错误码），与计划字面有差异。
- `heartbeat_at` 有更新但无运行中租约失联检测（仅启动时恢复）；单 worker 嵌入式部署下可接受，多 worker 前需补。
- 多窗口身份代次（计划 §7.2）：单窗架构下天然简化，退出时主进程 abort 全部流并清 token（`ipc.ts qd:auth:logout`），但"两窗广播清理"机制不存在——改独立窗时必须补。

### 阶段4：联网与 Python 研究 —— 已实现（待现场验收）

已实现：
- 受控出口：`infra/egress-proxy/app/netguard.py` 拒绝回环/私网/链路本地/云元数据(169.254.169.254)/CGNAT/组播/非全球 IPv6，**DNS 任一答案非公网即整批拒绝**（防 rebinding）；`httpclient.py` 每一跳重定向重新解析校验 + IP 钉扎（`_PinnedResolver`，`ttl_dns_cache=0`）——满足计划 §12.4"每次重定向重新检查、考虑 DNS 解析后变化"。
- 来源注册表 + 搜索（SearXNG 可配，`search.py`）+ 财联社适配器（`cls.py`）。
- 沙箱：`infra/pi-manager/app/runtime.py run_sandbox` 一次性容器——`network_disabled=True`、只读根 fs、tmpfs noexec、256MB/1 CPU/64 pids、120 秒超时 kill、用后强制删除；`infra/sandbox/runner.py` PID1 监督回收 setsid 子进程、产物仅收常规文件（lstat 先于 resolve、拒绝软链/超限）、输出上限；无模型密钥、无宿主目录（仅 base64 INPUTS + /work/output）。
- Pi 工具面与计划 §11.2 对应：account/recommendations/news/calculate_fees(情景)/export_data(仅管理员登记数据集 `DatasetExport`)/memory_list/save/delete/artifact_save/web_search/web_fetch/python_sandbox（`pi/src/tools.ts`、`server internal.py`）；权威金融答案只来自策略接口（recommendations/calculate_fees 直通适配器），沙箱不承担官方口径。
- 公告/更新接口已实现（`client_info.py`，文件后端 `server/config/announcements.json`、`client_release.json`，含 SHA256/版本/HTTPS 下载 URL 校验；两份 JSON 目前不在仓库，需运维放置）。

偏差/待办：
- 仓库内无沙箱逃逸/越权专项测试（验收 §20.5 的 Python→宿主/Docker 断言只有 `infra/tests/test_infra.py` 4 条与 worker 测试间接覆盖），需在阶段6补现场测试记录。
- `search` 依赖 SearXNG 实例，仓库未见其部署单元（compose 无该服务），联网搜索路径可能未部署。

### 阶段5：策略接线 —— 部分实现

已实现（合同与门禁层）：
- `strategy.py`：v1 合同（`quantdesk.strategy_adapter.v1`）、请求带 `input_digest`（sha256 规范化 JSON）、响应绑定校验（user_id/digest/版本/快照/行情 ID/input_account_version/operation 任一不符即 502 协议错误）；计算结束复查账户版本，变了返回 409 `ACCOUNT_CHANGED`——"旧计算晚返回不能覆盖新账户"达成。
- 发布门禁 fail-closed：`executable` 仅当 `release_enabled` + ReleaseFlag + 快照 `signed_off` + `review_proof`（reviewer/decision_id）+ `valid_until`/行情时效 + `gates.data_valid/market_current` 全部通过才可为真；测试 `test_algorithm_output_is_unwrapped_and_never_self_releases` 明确"算法自封 executable 无效"。快照离线导入 `release.py`（research 状态永不可执行）。
- 未接算法时：`ALGORITHM_NOT_CONFIGURED`（503）、桌面文案"策略算法尚未配置。账户输入可以保存…"（`src/lib.ts` 46 行）、诚实空态"这里不会用演示名单替代真实结果"——符合计划 §18 阶段5"先完成合同测试和不生成假建议的等待状态"。

未实现：
- 真实策略算法未接入（`strategy_url` 空 → `algorithm_configured=false`，与服务器现状一致）；`POST /scenarios` 公共端点不存在（情景计算仅作为 Pi 内部工具 `calculate_fees`）；`GET /recommendations/{id}` 缺失；无独立行情接口与 5 分钟/1 分钟刷新调度（计划 §9.6，桌面 `refresh()` 仅挂载时执行一次）；无 `recommendation_snapshots` 持久表（旧建议仅客户端隐藏）；账户输入与算法间的"验收核对脚本"（计划 A.2）未见。

### 阶段6：整体试用与发布 —— 未实现/未验证

- 无版本化 `QuantDesk-Portable-x.y.z.exe` 与 SHA256（§2.1）。
- 无图标交付物与"从 EXE 提取图标核验"记录。
- 1366×768、125%/150% 缩放、断网/欠费/限流文案、同花顺真实登录、备份恢复演练：仓库内均无记录。
- 公网 HTTPS：`ops/edge/DEPLOYMENT_EVIDENCE.md`（截至 2026-09-12）记录 **TLS-ALPN 签发失败**（云厂商路径吞 ClientHello 首段，Let's Encrypt 多视角校验不过），`verify-edge.sh` 未报 `edge_ok`；文件明确"Public readiness must not be claimed until…"。若当前服务器已可正常 HTTPS 访问，须补录新的签发/续期验证证据，否则按计划 §16.2 属未闭环。

---

## 2. 专项核对结果

### 2.1 桌面 EXE 构建产物是否在 release-final/ —— **否**
- `apps/quantdesk/desktop/release-final/` 仅有 `builder-debug.yml`（62KB）与 `win-unpacked/`；**`win-unpacked/` 内没有 QuantDesk.exe**（仅 Electron 运行时 DLL/pak 与 `resources/app.asar`、`default_app.asar`）。live 快照同。
- `builder-debug.yml` 内嵌路径指向旧构建机 `D:\AI\workspace\个人量化\apps\quantdesk\desktop`，说明这是旧机器拷回的**未完成打包残留**，不是可交付产物。
- `desktop/release-artifacts/win-unpacked.tmp/` 同为中间残留。
- `npm run package` 目标产物名 `release-delivery/QuantDesk-Portable-<version>.exe`（electron-builder.yml `directories.output: release-delivery`，与 release-final 目录名还不一致）；版本号 0.1.0（package.json）。
- 结论：计划 §17/§18 阶段1"可双击的 EXE"与 §21 交付材料第 1 项**未达成**。

### 2.2 认证是否"用户名+密码无邀请码"
- 无邀请码：**是**（两版均无；`QUANTDESK_INVITE_CODES` 仅为契约测试遗留参数，默认 public，不构成邀请码门禁；服务器 verification 提到它属历史遗留，非当前源码行为）。
- 仅用户名+密码：**否（部分）**。
  - apps 源码（`server/quantdesk_server/auth.py`）：注册必须 `email`（邮箱正则）+`password`+`display_name` 三字段 → **与计划 §8.1 明确偏差**。
  - live 快照（同名文件）：`AliasChoices("username","email")` + `_USERNAME_RE ^[\w.-]{2,32}$`（UNICODE，含中文）+ `display_name` 可选默认取用户名 + 中文错误文案 → **符合计划**。即该偏差在服务器运行版已修复，apps 拉回包与桌面 UI（仍渲染"邮箱""显示名称"输入框）落后。
- 密码最短 8 位、登录/注册限速、错误统一文案：达标。

### 2.3 账户接口字段 vs 计划 §9.2/§9.5
- 已达成：`expected_version` 并发控制、版本自增事务、十进制字符串、费率 stock/etf 分存含最低佣金、`allowed_boards`、`open_t`、持仓 `sellable_shares`（T+1 可卖）、成交幂等键唯一+内容冲突 409、待对账状态独立展示（桌面"待算法对账"）。
- 偏差/缺口：
  - 字段命名与计划示例不同：`cash`（非 `cash_available`）、无 `account_id/account_version/as_of/currency/slippage_assumptions/pending_trade_ids` 顶层字段（语义部分由 `version/reconciliation_watermark/manual_trades[].reconciliation_status` 承担）；持仓无"可卖数量对应交易日"。
  - 成交仅 `trade_date`（无"实际时间"时分秒），无"实际费用（已知时）"录入字段（`models.Trade` 预留 notional/commission/stamp/cash_after 列但从不写入）。
  - 无 `reconciliation_results` 表与更正记录（计划 §9.5 第 6/7 条、A.3），对账完全依赖算法侧 watermark。

### 2.4 SSE
- 服务端：持久化先行（事件先落 `task_events` 再被轮询推流）、`task_id+seq` 唯一、`Last-Event-ID` 续传、15s 量级 keepalive 注释（idle%20*0.25s≈5s 一条，计划建议 15—30s，更频繁但无害）、`X-Accel-Buffering:no`。达标。
- 客户端：主进程流式解析 + 按 id 去重转发（`parseSseBlock`），断流发 `stream_error` 可恢复，不重建任务。达标（契约测试 `tasks: sse ids + Last-Event-ID resume`、worker 测试覆盖）。
- 事件类型命名与计划 §14.2 字面不同（见 §1 阶段3偏差）。

### 2.5 沙箱与 egress 限制
- 沙箱：无网、只读根、tmpfs、mem/cpu/pids/120s/输出字节/产物数量全部有上限并实测路径见码；产物回收检查软链/常规文件/大小；每调用后容器强制删除。与计划 §12.3 逐条对应。
- egress：netguard 黑名单全面（含云元数据）、DNS 全答案校验防 rebinding、逐跳钉扎；仅注册表来源 + 工具经 egress。与计划 §12.4 对应。
- 待补：现场逃逸测试记录（§20.5）、SearXNG 部署缺失。

---

## 3. 与计划的偏差清单（汇总）

| # | 级别 | 偏差 | 位置 | 状态 |
|---|---|---|---|---|
| D1 | 高 | 视觉主题违反黑白灰规范：青色强调、渐变光晕、8–11px 中文小字 | `desktop/src/styles.css` | 未修复 |
| D2 | 高 | AI 为内嵌 dock 且展开时隐藏同花顺视图，违反 §20.1；未声明该兼容限制 | `desktop/src/App.tsx`（setVisible 逻辑） | 未修复 |
| D3 | 高 | 无版本化便携 EXE、无 SHA256；release-final 仅为旧机残留的 win-unpacked（无 exe） | `desktop/release-final/` | 未交付 |
| D4 | 高 | 无任何图标资产（.ico/.svg/.png），builder 无 icon 配置 | `desktop/` 全树 | 未交付 |
| D5 | 中 | apps 服务端注册要 email+display_name；桌面表单同；计划要求仅用户名+密码 | apps `auth.py`、`desktop/src/App.tsx` | live 服务端已修复，apps 与桌面未跟进 |
| D6 | 中 | 新闻分析超长"截断"而非"精简重写后判失败" | `server/.../news.py`（两版） | 未修复 |
| D7 | 中 | 相关性过滤内存执行（limit 100 后）、日期按采集时间、无游标分页 | `server/.../news.py list_news` | 未修复 |
| D8 | 中 | 归档无 manifest/对账任务表，非按来源逐日布局 | `news.py _archive`、models | 未修复 |
| D9 | 中 | 公网 HTTPS 证书证据停滞（2026-09-12 签发失败），无新的 edge_ok 记录 | `ops/edge/DEPLOYMENT_EVIDENCE.md` | 待补验证 |
| D10 | 中 | 聊天 Enter 未检查 IME 组词（isComposing） | `desktop/src/App.tsx` 391 行 | 未修复 |
| D11 | 低 | 账户/成交字段命名与 §9.2 有出入；成交无实际时间/实际费用；无 reconciliation_results/更正记录 | `account.py`、`models.py` | 未实现（待算法合同冻结时对齐） |
| D12 | 低 | `POST /scenarios`、`GET /recommendations/{id}` 公共端点缺失；无行情服务与定时刷新 | `strategy.py`、`app.py` | 随阶段5接线补 |
| D13 | 低 | SSE 事件类型命名与 §14.2 不同；无 `interrupted` 独立状态、无 `artifact_created` 事件 | `tasks.py` | 记录在案，可按合同裁决 |
| D14 | 低 | 死代码：`invites` 表、invite 帮助函数、契约测试 invite 参数 | `models.py`、`security.py`、`run_contract_tests.py` | 建议清理 |
| D15 | 低 | 界面偏好/草稿未持久化；聊天窗位置尺寸无记忆（§3.2/§5.6） | `desktop/src/App.tsx` | 未实现 |
| D16 | 低 | `client_release.json`/`announcements.json` 不在仓库，接口现返回空 | `server/config/` | 运维放置即可 |
| D17 | 低 | 无 audit_events、model_usage 业务表（用量在网关侧记账 `/internal/usage`，审计事件无表） | `models.py`、gateway accounting | 与计划 §13 有出入，记录在案 |

## 4. 测试盘点（证据基础）

- 服务端 pytest：`server/tests/test_backend.py` 12 条（账户版本/新闻更正失效/取消事件单调/能力令牌严格向量/缺算法结构化/结果解包且不可自放行/非对象协议错误/client info 空安全）。
- verification：本地 14 向量自检 + 42 条集成检查注册（auth/memory/artifacts/capability/lint/news/ownership/chat/tasks/recommendations/account，fail-closed 设计）+ `run_impl_crossval`（历史运行 38 通过/12 缺陷确认）。
- Pi worker：`pi/test/worker.test.ts` 16 项（含真实 SDK 会话持久恢复、取消、令牌续期、断连不取消、错误净化、DeepSeek SSE 工具往返）。
- 桌面：`desktop/tests/` 8 项（信任边界、URL 策略、金额展示、409 版本冲突、演示不可执行）。Playwright 缺失（README 已声明）。
- infra：`infra/tests/test_infra.py` 4 项。
- 覆盖缺口：多用户 SSE 清理、沙箱逃逸现场测试、备份恢复演练、真实 EXE 启动、T+1/整手/费用守恒（按架构属算法侧责任，应用侧仅透传，符合 §9.1 但验收记录为空）。

## 5. 建议下一步实施顺序

1. **以 live 为准归档源码**：apps 包落后 12 个文件（auth/config/news/account/app/errors/memory_artifacts/provider/runtime/model.ts/backup.sh/Dockerfile），先把 live 版同步回工作区再继续开发，避免重复修已修复的缺陷（含用户名注册、60s 采集、重启恢复、DeepSeek 兼容）。
2. **对齐注册口径**：桌面登录/注册表单改为用户名+密码两字段（服务端 live 已就绪），删除"邮箱/显示名称"输入。
3. **视觉重构**：按计划 §4.2 变量重写 `styles.css`（#171717/#ECECEC 灰阶、去渐变光晕、正文 14px、最小 12px），同时给聊天 Enter 补 `isComposing` 判断。
4. **AI 独立窗口**：按 §5.6 把 chat-dock 迁移为独立 BrowserWindow（或最低限度：展开聊天不再隐藏同花顺，并在 README 声明限制）；补多窗口身份代次与退出广播清理。
5. **交付链路**：制作 Q 图标（SVG→多尺寸 ICO）→ `npm run package` 产出 `QuantDesk-Portable-0.1.0.exe` → 提取图标核验 → SHA256 → 在干净 Windows 机启动测试。
6. **新闻四处修复**（D6/D7/D8）+ 归档 manifest 与补写任务。
7. **边缘与运维证据**：重跑 `verify-edge.sh` 并把证书签发/续期结果补进 DEPLOYMENT_EVIDENCE；完成一次隔离恢复演练并记录；放置 announcements/client-release JSON。
8. **阶段5接线准备**：冻结算法合同字段（顺带解决 D11 命名对齐），补 `/scenarios` 公共端点与行情快照契约测试；算法到位前保持 `ALGORITHM_NOT_CONFIGURED` 等待态。

## 附录 A：live 快照领先 apps 的文件（12 个）

| 文件 | live 新增要点 |
|---|---|
| `server/quantdesk_server/auth.py` | 用户名注册（2—32 位含中文）、display_name 可选、中文错误文案 |
| `server/quantdesk_server/config.py` | 新闻刷新默认 60s；EGRESS_TOKEN 兼容双命名 |
| `server/quantdesk_server/app.py` | 重启时把 queued/running 共享分析标记 `INTERRUPTED_BY_RESTART` |
| `server/quantdesk_server/news.py` | 采集来源状态暴露、超时 25s、失败不杀轮询、更正使旧分析 `NEWS_CONTENT_CHANGED`、超时/上游错误码净化 |
| `server/quantdesk_server/account.py` | 成交/账户路径补 `set_user_context`（RLS 上下文修复） |
| `server/quantdesk_server/errors.py` | 校验错误脱敏 + 中文化（不回吐 pydantic 原始 details） |
| `server/quantdesk_server/memory_artifacts.py` | 新增 `GET /artifacts` 列表（对齐计划 §14） |
| `infra/model-gateway/app/provider.py` | DeepSeek 域名自动加 `thinking:{type:disabled}` |
| `infra/model-gateway/Dockerfile` | 随 provider 变更 |
| `infra/pi-manager/app/runtime.py` | worker 容器命令列表化；销毁时强制断开服务网络 |
| `pi/src/model.ts` | OpenAI 兼容参数关闭 developer role/store/reasoning_effort、max_tokens 字段映射 |
| `infra/scripts/backup.sh` | 恢复容器加 `DAC_READ_SEARCH` 能力修复 |

（live 另有 `private/model.env`、`infra/_shared/qd_security/secrets.py`，属真实密钥，本次未读取、未复制、未在报告中引用其内容。）

## 附录 B：本次审计未发现的问题类型声明

- 未发现未来函数、假数据回退或"演示冒充真实"路径：桌面 `--demo` 显式参数 + 常驻横幅 + 推荐不可执行（`desktop/src/demo.ts`、测试"demo 永不可执行"）。
- 未发现密钥入库：`.env.example`/`env.example` 均 CHANGE_ME 占位；模型密钥仅 `private/model.env` 注入 model-gateway（compose/README 约束）。
- 未发现配额类隐藏配置：amendment 3 涉及的 `task_max_turns`/`QD_PI_RUN_MAX_TIMEOUT_SECONDS`/每日额度已从现源码移除（verification V-009/V-010 闭环）。
