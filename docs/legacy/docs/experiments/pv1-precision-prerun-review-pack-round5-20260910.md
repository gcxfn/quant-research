# PV1 精测 Codex 运行前审核送审包 第 5 轮（2026-09-10）

审核性质：运行前代码审核第 5 轮。第 4 轮唯一剩余 P1（候选身份未冻结价格数据内容）已修复，主对话复验通过；第 4 轮已接受的跨月挂单修复未动。全仓 971 项 unittest OK/1 skip（主对话自跑权威数）；HOLDOUT_UNLOCKED 保持 False、中央台账不存在。前包：round4。

## 一、第 4 轮处置（主对话复验）

| 项 | 处置 | 复验 |
|---|---|---|
| ③[P1] 候选身份没有冻结实际价格数据内容 | 新增 `data_manifest()`（pv1_precision_test.py:209-249）：对装载器实际读取的全部价格数据根做确定性内容清单——每文件 {path(仓库相对,正斜杠), size, sha256}，按 path 升序，返回 {roots, n_files, files, digest=全清单 canonical JSON sha256}；任一根缺失/文件不可读 → RuntimeError（fail-closed）。`_data_manifest_roots()`（:178-188）从 mrs 常量派生 4 根：`RAW_DAILY_DIR` 全目录、`ADJUST_DIR` 全目录、两市前复权.zip（档名取 `quant.history.USER_ADJUST_DIRS["qfq"]`，不硬编码）。**装载器追踪结论**：mr_statarb `user_qfq_rows`（:1581-1591）只打开 qfq 档 zip；涨跌停判定的原始价来自 baostock daily（已覆盖）；**不复权/后复权 zip 不被读取故不入清单**（未实际读取的输入不入身份，避免身份对无关文件敏感）。`candidate_identity()`（:313）并入 `data_manifest`；`run()` 把完整 manifest 落 `<out_dir>/data_manifest.json`（:949-950）并写入 in_window.json 的 identity 键 | 主对话实测：n_files=**11,792**（11,104 daily + 686 adjust_factor + 2 qfq zip，约 2.70GB，哈希约 35 秒）、digest `f2e943134828ca31…`；工件内 identity.data_manifest 与落档 data_manifest.json 逐字节一致；6 项新反例测试（根覆盖/缺根 fail-closed/tmp 假树改一字节 digest 变化/身份联动/锁恒闭）全绿 |

## 二、r5 重跑（新独立批次）

- `artifacts/pv1-precision/round-20260910-inwindow-r5`（独占新建；r4 未动）。
- **与 r4 深度比对（主对话自跑）**：剔除新增 identity 键后**全部顶层字段逐位一致**——mode/window/read_end/counts/te_list/plan/n_stock_months/results 全同；net17/net27/net37 的 stats（年化 +7.682005865686888%、MDD −28.5020%、夏普）、bootstrap（下界 −0.8606834472156362%）、monthly_returns（各 47 条）、mean_monthly_turnover、contribution、net17 十二项执行现实计数全部逐字段一致；changed fields = NONE。与 r3→r4 结论相同：数据未变，身份扩展是正确性保持。
- r5 的 in_window.json 含 identity.data_manifest（r4 无 identity 键）；holdout_gate 未触碰、台账零消费。

## 三、新增解释性读法（2 条）

1. manifest 的 4 根=装载器实际读取全集而非仅 Codex 点名最小清单；若未来装载器新增读取根（如启用不复权 zip），manifest 必须同步扩根——根清单与装载器代码同批受审。
2. holdout 台账单行因含 11,792 文件条目而增大到 MB 级（一次性门禁、append-only），机械上仍为逐行 JSONL 读取，不影响 gate 语义。

## 四、建议审核重点

1. 4 根清单完备性：PV1 路径除 RAW_DAILY_DIR/ADJUST_DIR/两市 qfq zip 外是否还有其它实际读取的价格输入（含经 mrs 常量间接派生的路径）。
2. digest 确定性：os.walk 顺序无关性（收集后按 path 全序排序）、canonical JSON（sort_keys+紧凑分隔符）。
3. r5=r4 仅身份键差异的独立性（两批均为全新独立运行，非缓存复用）。

## 五、结论边界（不变）

选择窗年化 +7.6820059%、95%CI [−0.8606834%, +2.6450247%] 含零——费用后盈利性仍不能判定。PASS → PV1 代码/数据资格冻结；留出窗按 D-2026-09-10-18 用户决定攒批后统一开考，本包不含留出窗运行。
