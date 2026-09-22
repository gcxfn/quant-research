# C2 参考账本独立性报告

- 阶段：C2（独立参考账本）
- run：`20260922T025434-trust-c2-a17b3e`
- 参考实现：`src/quant/research/reference_ledger.py`（核心账本，纯标准库）
- 对账驱动：`src/quant/research/reference_ledger_reconcile.py`（IO/编排）
- 测试：`tests/test_reference_ledger.py`
- 独立性验收门：C2-01（核心会计函数未调用主引擎）

## 1. 结论

参考账本的**核心会计实现只依赖 Python 标准库**（`decimal` / `datetime` /
`dataclasses` / `typing` / `__future__`），不 import `quant.backtest` 或
`quant.portfolio`，也不调用主引擎的费用、公司行动、现金结算、FIFO、估值或收益
函数。对账驱动新增的依赖只有 polars（读 parquet）与 `quant.data.dev_sandbox`
（C1 冻结的沙箱访问路径）——属于约定的 IO 层共享，不是会计逻辑共享。

排除静态导入之外，另做了**加载期实证**：import 对账驱动后，`sys.modules` 中
不存在任何 `quant.backtest` / `quant.portfolio` 模块（见 §3 命令 3 输出）。

## 2. 共享依赖清单

| 模块 | 依赖 | 性质 | 是否允许 |
|---|---|---|---|
| `reference_ledger.py` | `__future__`, `dataclasses`, `datetime`, `decimal`, `typing` | 标准库 | 允许 |
| `reference_ledger_reconcile.py` | 上述 + `argparse`, `csv`, `hashlib`, `json`, `pathlib`, `sys`, `time` | 标准库 | 允许 |
| `reference_ledger_reconcile.py` | `polars` | 读 run parquet / 沙箱 parquet（纯 IO） | 允许（数据格式共享） |
| `reference_ledger_reconcile.py` | `quant.data.dev_sandbox` | C1 冻结的 Dev 沙箱加载器（本身上游只有 polars/标准库） | 允许（IO 层） |
| `reference_ledger_reconcile.py` | `quant.research.reference_ledger` | 本阶段参考实现自身 | 允许 |
| `tests/test_reference_ledger.py` | 上述 + `pytest` | 测试框架 | 允许 |

与主引擎的共享仅限两处：**数据格式**（读写 parquet 的字段名与含义）与
**冻结合同文字**（费率、结算时序、T+1、公司行动口径、估值口径）。费用公式、
现金时序、FIFO 消耗、公司行动换算、可卖量判断、权益恒等式全部在参考模块内独立
实现（见 `reference_ledger.py` 的 `FeeSchedule`、`_replay_day`、`_book_fill`、
`_consume_fifo`、`_apply_split`、`_apply_dividend`）。

## 3. 实际执行的扫描命令与结果

**命令 1（grep 禁止依赖）：**

```bash
grep -nE "quant\.(backtest|portfolio)|from quant import|import quant\.(backtest|portfolio)" \
  src/quant/research/reference_ledger.py \
  src/quant/research/reference_ledger_reconcile.py \
  tests/test_reference_ledger.py
```

结果：仅命中 2 行**文档字符串**（说明"不得 import …"的文字），无任何实际 import：

```
src/quant/research/reference_ledger.py:10:**不得** import ``quant.backtest`` 或 ``quant.portfolio``，也不调用主引擎的
src/quant/research/reference_ledger_reconcile.py:8:**独立性**：本模块与参考账本都不 import ``quant.backtest`` / ``quant.portfolio``；
```

**命令 2（AST 逐文件导入枚举）：**

```bash
python -c "import ast; [print(p, sorted({(a.name if isinstance(n,ast.Import) else n.module) for n in ast.walk(ast.parse(open(p,encoding='utf-8').read())) if isinstance(n,(ast.Import,ast.ImportFrom)) for a in (n.names or [None])})) for p in [...]]"
```

结果（三个文件全部导入）：

```
src/quant/research/reference_ledger.py          : __future__, dataclasses, datetime, decimal, typing
src/quant/research/reference_ledger_reconcile.py: __future__, argparse, csv, datetime, decimal, hashlib,
                                                  json, pathlib, polars, quant.data, sys, time,
                                                  quant.research.reference_ledger
tests/test_reference_ledger.py                  : __future__, datetime, decimal, pytest, sys,
                                                  quant.research.reference_ledger
```

**命令 3（加载期实证，排除传递依赖）：**

```bash
PYTHONPATH=src python -c "import quant.research.reference_ledger_reconcile as m, sys; \
  print(sorted(k for k in sys.modules if k.startswith('quant'))); \
  print('FORBIDDEN loaded:', [k for k in sys.modules if k.startswith(('quant.backtest','quant.portfolio'))])"
```

结果：

```
modules loaded after import: ['quant', 'quant.data', 'quant.data.dev_sandbox', 'quant.research',
                              'quant.research.reference_ledger', 'quant.research.reference_ledger_reconcile']
FORBIDDEN loaded: []
```

## 4. 未覆盖的边界（如实声明）

- 本次独立性判定基于 **Python 模块级导入**与加载期证据，不排除两个实现存在
  共同的模型偏差或同一份合同文字被两处同样误读；独立性来自不同代码与不同实现，
  不等于绝对独立第三方（主计划 3.1）。
- 运行产物（`artifacts/runs/<run>/outputs/*_fills.parquet`、`*_daily_equity.parquet`、
  `*_events.parquet`、`*_clips_final.parquet`）由主引擎生成，参考账本**只读**它们，
  不重做信号与撮合（主计划 7 边界）。
- `quant.data.dev_sandbox.py` 属 C1 交付，不是本轮 C2 的实现对象；它对上游的依赖
  （仅 polars/标准库）已由 C1 审阅覆盖。

## 5. 文件哈希（写入本报告时的字节身份）

| 文件 | SHA256 |
|---|---|
| `src/quant/research/reference_ledger.py` | `5bfa1362ad252a1297ec9db0a489c527ca227acd4ee29bc4b432b71cbf020beb` |
| `src/quant/research/reference_ledger_reconcile.py` | `2095cbf0a643f8d874e158ee962e49d053c3c7c83ad52babd8c42f7459878660` |
| `tests/test_reference_ledger.py` | `9fd3da32293b119f2698f2b45fd504893d795f652151be210f15b581c93354ba` |

这些哈希同时登记在 `stage_report.json` 的 evidence 条目与两个 run_record 的
`code_files` 摘要中。
