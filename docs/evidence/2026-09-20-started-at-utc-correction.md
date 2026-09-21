# 更正:16 个运行 manifest 的 `started_at_utc` 为 1970 年代假时间

登记日期:2026-09-20。来源:exp-20260920-strategy-review.md R7。

## 问题

受影响的 runner 脚本把 `time.perf_counter()` 的计时值传给了
`datetime.fromtimestamp()`,得到 1970-01-01 之后数天的假时间戳。
`perf_counter()` 的零点未定义(通常距开机仅数小时到数天),不是 Unix
纪元秒。原始脚本按仓库规范保留原位只读,manifest 原文不改、不重写。

## 更正口径

- 这些 manifest 中的 `started_at_utc`(及同源的 `started_at`)不可信,
  不得用于开始/结束时间、预登记或执行顺序审计。
- 各运行的真实开始时间以 `run_id` 前缀 `YYYYMMDDTHHMMSS` 为更可信的
  锚点(该前缀在运行启动时生成)。本轮未逐个核对前缀与实际启动钟点
  的一致性;需要精确时间时以文件系统时间戳交叉验证。
- 耗时字段(elapsed 类,由 `perf_counter()` 差值计算)不受影响。

## 受影响清单(started_at_utc 原值)

| run_id | started_at_utc(错误值) |
|---|---|
| 20260918T035435-halfday-extract-k4x8vt | 1970-01-03T14:22:44 |
| 20260919T030640-p3r2-dev-ad9e | 1970-01-04T05:12:44+00:00 |
| 20260919T054649-hybrid-v1-9k2f | 1970-01-04T08:01:44+00:00 |
| 20260919T063022-hybrid-v2-2k5b | 1970-01-04T08:28:16+00:00 |
| 20260919T110500-hybrid-v3-r3ld | 1970-01-04T12:56:11+00:00 |
| 20260919T112300-hybrid-v4-h4sx | 1970-01-04T13:12:44+00:00 |
| 20260919T151047-hybrid-rob-05bf | 1970-01-01T02:52:36+00:00 |
| 20260919T151630-hybrid-val-v1p3 | 1970-01-01T02:28:55+00:00 |
| 20260919T161737-exp-universe-v1-3eu1 | 1970-01-01T04:09:46+00:00 |
| 20260919T191524-f3r1-factor-combo-c212 | 1970-01-01T07:01:58+00:00 |
| 20260919T194700-f3r2-hybrid-chassis-e7a1 | 1970-01-01T07:30:44+00:00 |
| 20260919T201500-f3r3-industry-cap-4b2e | 1970-01-01T08:40:04+00:00 |
| 20260920T011431-f4r1-smoke-4d9e | 1970-01-01T13:24:45+00:00 |
| 20260920T020201-f4r1-full-a3b7 | 1970-01-01T14:17:49+00:00 |
| 20260920T030215-f4r2-notp-f3b1 | 1970-01-01T15:25:25+00:00 |
| 20260920T130406-val-batch-hybrid-9547 | 1970-01-02T01:18:32+00:00 |

## 防复发

`src/quant/research/runs.py` 的 `Run` 类自始正确:`started_at` 用
`datetime.now(timezone.utc)`,耗时用 `perf_counter()` 差值。新一轮
运行统一经 `Run`(或等价入口)写 manifest,不再在实验脚本内自行调用
`datetime.fromtimestamp(time.perf_counter())`。
