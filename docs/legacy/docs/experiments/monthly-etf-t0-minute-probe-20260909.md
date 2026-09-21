# ETF 5分钟公开源探针（2026-09-09）

批次：`D:/AI/workspace/个人量化/data/raw/etf-minute-probe/20260909_etf_m5_probe/`。目的仅为可行性探查；没有回放、成交或盈利结论。

| 标的 | 腾讯 | 东财 | 新浪 | 新浪有效5分钟覆盖 |
| --- | --- | --- | --- | --- |
| sh510300（普通ETF） | SSL/连接失败 | HTTP 200但 `data:null`，83 bytes | 原始响应保存 | 320 bars，2026-08-31 10:55 至 2026-09-08 15:00 |
| sz159915（20% ETF） | 连接中断 | 远端断开 | 原始响应保存 | 320 bars，同上 |
| sh588000（20% ETF） | SSL EOF | 远端断开 | 原始响应保存 | 320 bars，同上 |

新浪三份响应均含 `day/open/high/low/close/volume/amount`，并覆盖所请求窗口 2026-09-01 至 2026-09-04；接口忽略显式起止参数而返回最近 320 根，故不能据此主张长历史可得。腾讯与东财失败的请求 URL、错误和原始响应均记录在同批次 `summary.json`。

结论：新浪可作为三个 ETF 的**近期**5分钟 OHLCVA 样本源；历史回放所需的 V3 池/实际持仓全量长窗口仍未证明可得。不得使用 baostock 或股票分钟线替代 ETF 实证。

主审随后批准了仅这三只ETF、2026-09-01--04的固定研究回放。冻结配置为 [monthly-etf-t0-minute-replay-20260909.json](../../configs/monthly-etf-t0-minute-replay-20260909.json)，输出为 [report.json](../../artifacts/monthly-etf-t0/minute-replay-20260909-fixed-v1/report.json)。它按前一交易日新浪原始分钟收盘锚定、要求与本地新浪非复权日线同日收盘在一个ETF tick内一致，并不作 raw/QFQ 变换；首腿成交后第二腿只能在下一根 bar 进入撮合，限价严格穿越，0.005只是未校准工程容量情景。该四会话工件不年化、不合并顺势和反T独立账户，也不构成做T盈利或执行验证；仍待独立验收。
