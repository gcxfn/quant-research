# 1分钟数据接入与十年账户阻塞记录

当前状态（2026-09-13 晚更新）：T1 整体未完成（A DONE、B DONE〔限定已验能力〕、C RUNNING，分钟实际订单依赖已闭合）；T2-A DONE、**T2-B 四路径十年账户已产出完整账本待审核**、T2-C PENDING。CPU 隔离整改 DONE 不变。原始数据商未知，用户说明从闲鱼购买。

## 已交付

- 2015–2024十个ZIP迁入工作区，逐文件SHA256确认后删除下载目录中的对应ZIP。原始1分钟ZIP保留在 `data/raw/user_minute_1m/20260913-143215/` 与 `data/raw/user_minute_1m/20260913-2020-2024/`；各自transfer-manifest.json记录源/目标/摘要/删除结果。
- 全部2431个Parquet日文件CRC通过，年份交易日清单与研究日历一致，无缺日、重复日。CRC只能证明压缩文件可读，不能证明行情完整。
- `experiments/user_minute_1m_20260913.py`：严格核241条时间网格及代码/日期/OHLCV，09:30记录合入首根，生成48根5分钟；午休不跨组，总量不增减。只将确为float32分币编码的价格还原到分，原始ZIP不改。Parquet读取单日，按需筛证券，未全量解压。
- 独立探针转换2127个旧选股证券日：1722匹配或满足既有取整条件，394有界差异披露、11超异常线，另4项网格缺失。探针使用旧选股清单，是数据检查，不是最终订单清单。
- 新增代码有效期与等股数持仓衔接；见[身份修复](ten-year-code-identity-20260913.md)。新信号批 `artifacts/ten-year-fixed-strategies-20260913-2/`，5552证券、两策略各120个月；REV11选股改变2个月，组合7个月；仅001872、001914、302132的单股证据变化，其余单股证据一致。2023–2024选股不变。旧批及失败不覆盖。
- 新的四账户分钟入口、原数据/信号/源码/审核身份前后校验，以及代码变更持仓、限售股、跨日目标衔接。原2023–2024两个账户用原输入离线回归：每账户484日，292/297笔成交，全账本逐项一致。

## 当前实际阻塞

四条路径均运行至2015-07-01的数据获取/校验阶段后BLOCKED，未生成有效十年account.json。此前程序执行不代表上半年账本已独立验收，不能据此披露有效阶段收益。

该日实际订单共涉及21只证券，其中11只深市股票最后正成交量均为14:53，14:54–15:00是零量重复价格，且日总量有缺口。全部11项：000032、000560、000607、000632、000681、000802、000989、002349、300006、300100、300322。属于尾盘疑似缺失，不能用小差异披露放行；例如000607分钟收盘13.99、日线13.30，分钟总量少7.7414%。

新增拦截：连续至少5条末端零量记录，同时分钟总量少于日线超过1股且超过1ppm，直接BLOCK。有真实停牌/提前收市且总量守恒的记录仍可通过。该规则不证明其他所有缺失均被识别。

第一次实际批 `artifacts/ten-year-fixed-strategies-minute-accounts-20260913-1/` 保留原异常线拦截及21只实际订单诊断。补尾盘门禁后新批 `...-2/` 再运行四路径，仍于同日阻断；REV11首阻塞000681，组合首阻塞000032。第二批28个源码身份、1554个输入文件及源码副本独立重算一致；见该批blocking-review.json。

## 接下来需要的数据

可直接转给卖家的[核验/补数说明](../../artifacts/user-minute-1m-review-20260913-1/给数据卖家的核验清单.md)及[22项CSV清单](../../artifacts/user-minute-1m-review-20260913-1/data-repair-request.csv)。其中11项是当前实际订单阻塞，另外11项只是修复后选股的预检问题，不是已经发生的订单。较大日线差异须核实哪一来源有误，不能一律归咎分钟源。

补数据后新建原始批，保留旧ZIP及失败，重新绑定输入与审核身份，再从同一初始现金重跑原四路径。不得拼接不同现金启动账户、把日线成交替代分钟，或把零量占位记录当成真实补数。后续订单还可能发现新依赖，现清单不保证十年订单穷尽。

T2完整收益、逐月/逐年归因及统计仍未交付；统计UNKNOWN、晋级BLOCK、2025以后行情/收益与生产冻结不变。T1已验能力可复用，实际数据补齐前整体不写DONE。CPU旧隔离快照不含这次代码身份修复，未来研究切换需另绑身份；本轮未提交主仓。

## 复现与审核

Parquet依赖隔离在 `D:/AI/workspace/.minute-parquet-deps`，pyarrow 25.0.1（wheel SHA256 `62cd0d785b8aa6675ee355f9fc02252a340f4441257c42674937826fd7594325`）。基础聚合/账本测试不依赖pyarrow。

```powershell
$env:PYTHONPATH='D:/AI/workspace/.minute-parquet-deps'
$env:FACTOR_MINER_NUMPY='1'
& D:/AI/agent/hermes/venv/Scripts/python.exe -X utf8 -m experiments.ten_year_minute_accounts_20260913 --signals artifacts/ten-year-fixed-strategies-20260913-2/signals --inputs artifacts/ten-year-fixed-strategies-minute-accounts-20260913-1/inputs --raw data/raw/user_minute_1m/20260913-143215 --raw data/raw/user_minute_1m/20260913-2020-2024 --source-review artifacts/user-minute-1m-review-20260913-1/review-v2.json --mismatch-policy research_disclose --out artifacts/ten-year-fixed-strategies-minute-accounts-20260913-2
```

以上是已执行命令，复跑必须换新输出根。审核 `artifacts/user-minute-1m-review-20260913-1/review-v2.json` 绑定当前28个源码摘要；身份变更须重新审核。原生5分钟对照9个2020–2022样本的网格一致，部分价格/量存在来源差异，不能声称逐bar完全等同。

最终关联测试56项通过；此前生命周期/十年能力50项通过（两组范围有重叠，不相加计数）。旧窗口回归脚本 `artifacts/user-minute-1m-review-20260913-1/old-account-regression.py`，结果同目录old-account-regression.json。完整ZIP与日历审核脚本为review.py；补尾盘后的实际负例与最终能力裁决见review-v2.json。

## 2026-09-13 晚：四路径十年账户完成（分钟阻塞链闭合）

最终批 `artifacts/ten-year-fixed-strategies-minute-accounts-20260913-12/`，四路径全部 WAITING_REVIEW：`REV_vola_11` 主/压力与组合 `PV1_REV11_RANK50_TRAIN_V1` 主/压力，各 120 次调仓、2431 交易日、`nav_invalid_days=0`。核查脚本 `experiments/ten_year_minute_accounts_review_20260913.py`，输出 `-12/verification.json`（批身份全部匹配，权益恒等式与现金重建通过，逐笔费用分量零差）。

补丁与审核推进（只新增）：`minute-repairs-20260913-{3,4,5,6}/patches.json` 依次修 `sh.603178 2022-02-07`、`sh.603209 2023-06-01`、`sh.688159 2023-10-09`、`sh.603297 2024-02-01`（同一缺陷类：1 分钟首根 open 取到前收，baostock 5 分钟整日替换后 OHLC 逐字段相等）；`review-v4..v7.json` 由 `experiments/xiaodefa_review_rebind_20260913.py` 重绑，命令：

```powershell
python -X utf8 experiments/xiaodefa_minute_repair_20260913.py --out data/raw/xiaodefa/minute-repairs-20260913-6 `
  --inputs artifacts/ten-year-fixed-strategies-minute-accounts-20260913-11/inputs `
  --base data/raw/xiaodefa/minute-repairs-20260913-5/patches.json sh.603297:2024-02-01
python -X utf8 experiments/xiaodefa_review_rebind_20260913.py --parent artifacts/user-minute-1m-review-20260913-1/review-v6.json `
  --out artifacts/user-minute-1m-review-20260913-1/review-v7.json `
  --patches data/raw/xiaodefa/minute-repairs-20260913-6/patches.json --note "..."
python -X utf8 -m experiments.ten_year_minute_accounts_20260913 --signals artifacts/ten-year-fixed-strategies-20260913-2/signals `
  --inputs artifacts/ten-year-fixed-strategies-minute-accounts-20260913-1/inputs `
  --raw data/raw/user_minute_1m/20260913-143215 --raw data/raw/user_minute_1m/20260913-2020-2024 `
  --source-review artifacts/user-minute-1m-review-20260913-1/review-v7.json `
  --patches data/raw/xiaodefa/minute-repairs-20260913-6/patches.json `
  --mismatch-policy research_disclose --out artifacts/ten-year-fixed-strategies-minute-accounts-20260913-12
```

预扫描能力 `experiments/ten_year_minute_defect_scan_20260913.py` 按账户同一口径核已请求过的 2838 个证券日：DISCLOSE 526、硬阻断仅 3（均已修复）。

十年累计（20 万起点）：REV 主 282,178.32（+41.09%）、REV 压力 275,571.62（+37.79%）、组合主 223,479.11（+11.74%）、组合压力 206,450.21（+3.23%）。均为模型内历史描述，不是独立 Alpha；统计 UNKNOWN、晋级 BLOCK、2025+/生产冻结不变。
