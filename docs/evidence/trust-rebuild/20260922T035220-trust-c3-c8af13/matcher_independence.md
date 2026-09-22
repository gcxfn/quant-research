# C3-01 独立性扫描（matcher 及其辅助）

扫描对象：`src/quant/research/reference_matcher.py`、`src/quant/research/reference_matcher_reconcile.py`、`tests/test_reference_matcher.py`、`tests/test_reference_matcher_state.py`
（`c3_semantic_chain.py` 故意读取真实策略/风险代码，属 C3-B 语义链，不在 C3-01 约束内）

## 扫描命令
```
grep -nE "^\s*(import|from)\s" src/quant/research/reference_matcher.py src/quant/research/reference_matcher_reconcile.py
grep -rn "quant\.backtest\|quant\.portfolio" src/quant/research/reference_matcher*.py
```

## 结果（实跑输出）
```
src/quant/research/reference_matcher.py:71:from __future__ import annotations
src/quant/research/reference_matcher.py:73:from dataclasses import dataclass, field, replace
src/quant/research/reference_matcher.py:74:from datetime import date, datetime
src/quant/research/reference_matcher.py:75:from decimal import Decimal
src/quant/research/reference_matcher.py:76:from typing import Callable, Iterable, Mapping, Sequence
src/quant/research/reference_matcher.py:78:from quant.research.reference_ledger import FeeSchedule, cent
src/quant/research/reference_matcher_reconcile.py:49:from __future__ import annotations
src/quant/research/reference_matcher_reconcile.py:51:import argparse
src/quant/research/reference_matcher_reconcile.py:52:import csv
src/quant/research/reference_matcher_reconcile.py:53:import json
src/quant/research/reference_matcher_reconcile.py:54:import re
src/quant/research/reference_matcher_reconcile.py:55:import sys
src/quant/research/reference_matcher_reconcile.py:56:import time
src/quant/research/reference_matcher_reconcile.py:57:from datetime import date
src/quant/research/reference_matcher_reconcile.py:58:from decimal import Decimal
src/quant/research/reference_matcher_reconcile.py:59:from pathlib import Path
src/quant/research/reference_matcher_reconcile.py:61:import polars as pl
src/quant/research/reference_matcher_reconcile.py:65:from quant.data import dev_sandbox  # noqa: E402  (IO 层，非主引擎)
src/quant/research/reference_matcher_reconcile.py:66:from quant.research.reference_matcher import (  # noqa: E402
--- 禁用命名空间命中 ---
src/quant/research/reference_matcher_reconcile.py:6:``quant.research.reference_matcher``。它**不 import** ``quant.backtest`` /
src/quant/research/reference_matcher_reconcile.py:7:``quant.portfolio``，也不复制主引擎的穿透/合法性/生命周期代码。
src/quant/research/reference_matcher.py:16:独立性硬约束（C3-01）：本模块**不 import 也不调用 ``quant.backtest`` 与
src/quant/research/reference_matcher.py:17:``quant.portfolio``**，不复制 band_engine 的穿透/价格合法性/生命周期函数，
src/quant/research/reference_matcher.py:88:# --- 冻结合同常量（独立重述，不从 quant.backtest 导入） --------------------
```

## AST 级复核（结构化，不靠正则）
```
src/quant/research/reference_matcher.py: imports=['__future__', 'dataclasses', 'datetime', 'decimal', 'quant.research.reference_ledger', 'typing']
  forbidden=[]
src/quant/research/reference_matcher_reconcile.py: imports=['__future__', 'argparse', 'csv', 'datetime', 'decimal', 'json', 'pathlib', 'polars', 'quant.data', 'quant.research.reference_matcher', 're', 'sys', 'time']
  forbidden=[]
```

结论：两个模块只 import 标准库 + `quant.research.reference_ledger`（费用合同）+ `quant.data.dev_sandbox`（C1 冻结访问层）+ `polars`（IO）。零 `quant.backtest` / `quant.portfolio` 依赖，C3-01 PASS。

补充：`tests/test_reference_matcher_state.py` 会 import `quant.backtest.band_engine`——它是**对照驱动**（把引擎当被测系统的另一侧），不是 matcher 的辅助实现；`tests/test_reference_matcher.py` 里另有一条断言在测试期对 `reference_matcher.py` 做 AST 扫描，任何未来引入禁用依赖都会让该测试失败。
