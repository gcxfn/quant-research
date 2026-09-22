# 返工轮 R1 报告

**run_id：** `20260922T104206-trust-rework1-bed4cf`｜**日期：** 2026-09-22｜**执行者：** C0–C4 独立审阅会话（用户授权）
**性质：** 证据留痕修复。不改 `src/`、不改测试断言、不改交易语义、不开启 C5。

## 触发与授权

C0–C4 独立审阅结论：技术实质成立、无 CRITICAL，但存在 5 项 MAJOR 证据留痕缺陷。用户 2026-09-22 裁定：① **追认 C2 舍入位置表示差裁定**（引擎 float 不舍入 vs 参考 Decimal 逐笔 ROUND_HALF_UP；日权益差 ≤0.14 元、95 笔费用 ≤0.01 元、精确轨道残差 ~1e-10，判为数值表示差而非账实不符）；② 授权执行本返工。

## 修复清单

| ID | 缺陷 | 修复内容 | 新哈希（前 16） |
|---|---|---|---|
| R1-1 | C1-07 证据身份失效：interface_contract.json 经 C4 A-01 升版（schema 1.0→1.1）后四处仍 pin 旧哈希 `c2ede244…`，检查器复跑失败 | 矩阵 C1-07、C1 stage_report EV-01＋顶层 `contract_sha256`、`dataset_manifest.json` 的 `contract_sha256` 统一回刷至 `5bef4159…`；旧值保留在 `sha256_superseded`；当前版本字节冻结为 `interface_contract_schema1.1_frozen.json` | `5bef41594fc0be5a` |
| R1-2 | 活文档被当固定字节证据 pin：C0 stage_report E10 pin 主计划文档，后续阶段追加后哈希漂移；检查器三处历史记录冲突（exit2×2 有日志 vs 计划文档 exit0 无日志） | E10 回刷＋`living_document` 注记＋`sha256_superseded`（C0 时点 `4b1e3f31…`）；C0/C1 stage_report 增加 `post_stage_corrections` 对账说明；返工后检查器复跑归档于本目录（见下"验证"） | 计划文档 `3dd4a7a988bc37fe` |
| R1-3 | hand_calculated_expected.csv TV-A03 两行算错（08-25 待结算 49445 少 500；08-28 待结算 49470 少 500 且费用 55 误用旧税率，应为 30） | 更正为 49945/549945/55 与 49970/549970/30，note 列补算式；`.md` 与 `test_tv_a03` 原本即正确，账本结论不变；矩阵 C2-02 回刷 | `88242aae00bd15b3` |
| R1-4 | C3 intent_to_order_trace.csv cap 列用 A 族口径（触发日收盘×1.01）套 B1 事件，18/39 行 cap<anchor 与 provider_rule 文字自相矛盾；case report §5.1 ① 的 skip_cap 描述仅适用 A 族 | 新增 `provider_cap_b1` 列（＝决策锚价×1.01，BEvent 分支）；`cap_ge_anchor` 重算（39 行翻正，全 True）；`provider_rule` 改 B1 分支语义；`relationship` 改 `limit_is_decision_anchor__b1_cap_ungated`；`trigger_cap_1p01` 保留为 A 族诊断列；case report §5.1 追加更正注记。39/39 limit==anchor、0/39 limit==cap 核心观测不变；矩阵 C3-07 回刷 | trace `d734fc730e2b6b02f` |
| R1-5 | C1 independent_review.md R8 把 86 个跨界锚点误标"B2/A 家族"（实为 B1 事件证券），使读者误以为 B2/A 越界已被独立复算 | 更正为 B1 并注明 B2/A 的 2020-12-29 越界未在该审计复算（仍以 C0 access_ledger AL-01 为准）；C1 stage_report EV-35 回刷 | `aafd5c1f883fd8dd` |
| 用户裁定 | C2-03 字面条件（一致到分）依赖舍入差裁定 | 矩阵 C2-03 备注登记追认；C2 stage_report `post_stage_corrections` 同步 | — |

## 改动的文件与备份

全部 11 个被修改文件的改前字节备份于 `originals/`（文件名以 `__` 代路径分隔符）。修复脚本 `apply_fixes.py` 随档可复现。

## 已知不可恢复项（如实登记）

- 升版前 interface_contract v1.0 字节无任何副本，C4"纯追加、未动 fee_schema/entry_price_dual_track"无法逐字节独立验证；只能依据 C1 记录的旧哈希与 A-01 自述推断。**规则：今后接口修订必须先归档改前字节再改。**
- 主计划 §4 所引"C0 检查器终态 exit 0"当时无归档命令日志，无法追认；以本目录 `checker_c0.txt`（返工后复跑，exit 0）为准。

## 验证（实际运行）

| 检查 | 命令 | 结果 |
|---|---|---|
| 交付检查器 C0 | `PYTHONPATH=src .venv/Scripts/python.exe docs/quant_stage_plan_20260922/tools/check_delivery.py --report …/trust-c0-c17494/stage_report.json --root .` | **EVIDENCE_FILES_OK，exit 0，12 项证据验证**（checker_c0.txt） |
| 交付检查器 C1 | 同上，指向 trust-c1-479c46 | **EVIDENCE_FILES_OK，exit 0，36 项证据＋41/41×2 junit**（checker_c1.txt） |
| 全量测试 | `PYTHONPATH=src .venv/Scripts/python.exe -m pytest tests -q` | **804 passed / 0 failed** |
| 验收矩阵哈希终检 | 逐行重算 40 个 actual_sha256 | **40/40 一致，0 缺失** |

## 未处理遗留

约 15 项 MINOR（各 stage_report accepted/pending 文案自相矛盾、行数口径笔误、`delivery_check_output.json` 旧快照、C0 交付清单漏列 c0_run_log.md 等）不在本轮范围，见独立审阅报告。C5 及之后阶段未开启、未授权。

**范围声明：** 本轮仅修复证据链可复核性。工程 accepted 不等于策略有效，不授权 Val/2025+ 或实盘。

## R1b 补记（2026-09-22 同日，用户裁决轮）

用户裁定关闭 C0 全部 12 项待决项（决策记录 `docs/decisions/2026-09-22-c0-open-items-adjudication.md`）后，主计划追加 §7"裁决结果"，C0 stage_report E10 哈希再次回刷（`52a472e9…`，R1 时值 `3dd4a7a9…` 见上表）。同轮落地：AGENTS.md 六处修订合入、README 更新（C0-attrib 改名＋信任重建状态）、最小 CI 建立（`.github/workflows/tests.yml`；5 个真实数据测试加数据缺失跳过守卫：`test_band_engine_v13_corporate_actions.py` ×4、`test_band_contract.py::test_06b`，无数据环境实测 796 passed＋8 skipped / 0 failed，本地 804 passed）、C1-S 预登记草案起草（未授权运行）、工作树分两段提交（未推送）。检查器复跑结果见 `checker_c0_r1b.txt`。
