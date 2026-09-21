# 验证期因子重建状态

状态：`failed_partial`，不是完成，也没有生成验证 composite。

已完成的独立产物：

- `outputs/factor_val/A_price/`：25 个因子，5,529,898 行；日期 2021-01-29 至 2024-11-29。
- `outputs/factor_val/B_value/`：15 个因子，3,301,884 行；日期 2021-01-29 至 2024-11-29。
- 每个已完成因子均有 parquet 和 JSON，JSON 记录评估身份和覆盖信息。

未完成：C_micro、D_fund、E_event、F_xsec，以及基于冻结代表清单、开发期方向和 `abs(icir)` 权重的验证 composite。因此本 run 不支持验证期收益、ICW 组合或策略通过结论。

阻塞：第一次调用系统 Python 失败，因为没有 `polars`；改用仓库 `.venv` 后，C_micro 进程在没有产生任何输出或 traceback 的情况下退出，日志为空。该现象按进程/资源级失败留档，不能当作成功。历史文件没有覆盖或删除。

可复现入口见同目录 `manifest.json` 的 `commands`，运行前应先确认可用内存并采用分族/分块执行。
