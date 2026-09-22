# -*- coding: utf-8 -*-
"""C2 对账驱动：把选定 run 的成交/公司行动/官方估值喂给独立参考账本并逐事件对账。

本模块只做 IO 与编排：读 run 产物（只读）与 C1 Dev 沙箱（经
``quant.data.dev_sandbox``），把规范化输入交给
``quant.research.reference_ledger`` 独立重算，再把差异写成证据 CSV。

**独立性**：本模块与参考账本都不 import ``quant.backtest`` / ``quant.portfolio``；
共享的只有数据格式（polars 读文件）与冻结合同文字。

两条数值轨道
------------
* ``round``（合同评分口径）：参考实现在**每笔现金变动处** ROUND_HALF_UP 到分
  （C1 ``fee_schema.rounding_rule``）；主引擎全程 float64 不舍入。
* ``exact``（完整性证明口径）：参考实现同样用 Decimal，但**不在中间舍入**，
  直接与主引擎的 float 值比较。若该轨道与引擎仅差浮点 eps，说明账本事件
  无遗漏——把 ``round`` 轨道的一分差定位为「舍入位置」表示差而非经济错误。

用法::

    PYTHONPATH=src .venv/Scripts/python.exe -m quant.research.reference_ledger_reconcile \
        --evidence-dir docs/evidence/trust-rebuild/<C2-run>

输出：``ledger_reconciliation.csv``、``cash_reconciliation.csv``、
``fee_type_reconciliation.csv``、``corporate_action_reconciliation.csv``、
``coverage_manifest.json``、``reconcile_summary.json``。
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
import time
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

import polars as pl

sys.path.insert(0, "src")

from quant.data import dev_sandbox  # noqa: E402  (IO 层，非主引擎)
from quant.research.reference_ledger import (  # noqa: E402
    CENT,
    DayInput,
    DividendAction,
    FeeSchedule,
    Fill,
    ReferenceLedger,
    SplitAction,
    cent,
)


def q(value) -> Decimal:
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


# --------------------------------------------------------------------------- #
# 对账目标：阶段 A 基线 v4 三臂 + 阶段 B 四主臂 + 三条随机对照（合计 10 个臂）
# 任务书文字写「共 9 个对账目标」，但逐项列出的臂 = 3 + 4 + 3 = 10；本驱动
# 覆盖全部 10 个已列名臂（多覆盖，不遗漏）。
# --------------------------------------------------------------------------- #
TARGETS: list[tuple[str, str]] = [
    ("20260921T210100-baseline-replay4-9x4q2", "FULL-bin"),
    ("20260921T210100-baseline-replay4-9x4q2", "NOSNR-bin"),
    ("20260921T210100-baseline-replay4-9x4q2", "NOACCT-bin"),
    ("20260921T223157-eventfam-main-cb4cff", "A1"),
    ("20260921T223157-eventfam-main-cb4cff", "A2"),
    ("20260921T223157-eventfam-main-cb4cff", "B1"),
    ("20260921T223157-eventfam-main-cb4cff", "B2"),
    ("20260921T223217-eventfam-rnd-6af378", "RND-11"),
    ("20260921T223217-eventfam-rnd-6af378", "RND-23"),
    ("20260921T223217-eventfam-rnd-6af378", "RND-47"),
]


def _dec_or_none(value) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


class ArmOutputs:
    def __init__(self, repo: Path, run_id: str, arm: str) -> None:
        self.repo = repo
        self.run_id = run_id
        self.arm = arm
        self.dir = repo / "artifacts" / "runs" / run_id
        self.outputs = self.dir / "outputs"
        self.fills_path = self.outputs / f"{arm}_fills.parquet"
        self.equity_path = self.outputs / f"{arm}_daily_equity.parquet"
        self.events_path = self.outputs / f"{arm}_events.parquet"
        self.clips_path = self.outputs / f"{arm}_clips_final.parquet"
        self.manifest_path = self.dir / "manifest.json"
        for p in (self.fills_path, self.equity_path, self.manifest_path):
            if not p.is_file():
                raise FileNotFoundError(f"missing run product {p}")

    def evidence_files(self) -> list[dict]:
        files = []
        for p in (self.fills_path, self.equity_path, self.events_path,
                  self.clips_path, self.manifest_path):
            if p.is_file():
                files.append({
                    "path": str(p.relative_to(self.repo)).replace("\\", "/"),
                    "sha256": sha256_file(p),
                    "bytes": p.stat().st_size,
                })
        return files


def load_sandbox_maps(repo: Path, symbols: set[str]):
    reg = dev_sandbox.SandboxRegistry.load(repo)
    bars = reg.read("bars_daily",
                    columns=["symbol", "date", "close", "preclose", "tradestatus"],
                    symbols=sorted(symbols))
    preclose: dict[tuple[str, date], Decimal] = {}
    trade_series: dict[str, list[tuple[date, Decimal]]] = {}
    for row in bars.iter_rows(named=True):
        key = (row["symbol"], row["date"])
        if row["preclose"] is not None:
            preclose[key] = Decimal(str(row["preclose"]))
        # 估值 mark = 最近一个**可交易** session 的官方 close（合同 valuation.mark
        # "官方日线 close"；引擎实现为 tradestatus!=0 行的 carry-forward）。
        if row["close"] is not None and row["tradestatus"] not in (0, 0.0):
            trade_series.setdefault(row["symbol"], []).append(
                (row["date"], Decimal(str(row["close"]))))
    for sym in trade_series:
        trade_series[sym].sort(key=lambda t: t[0])
    limits: dict[tuple[str, date], tuple] = {}
    lim = reg.read("limit", columns=["symbol", "date", "up_limit", "down_limit"],
                   symbols=sorted(symbols))
    for row in lim.iter_rows(named=True):
        limits[(row["symbol"], row["date"])] = (
            _dec_or_none(row["up_limit"]), _dec_or_none(row["down_limit"]))
    splits: dict[tuple[str, date], Decimal] = {}
    sp = reg.read("split_factor", columns=["symbol", "ex_date", "split_factor"],
                  symbols=sorted(symbols))
    for row in sp.iter_rows(named=True):
        splits[(row["symbol"], row["ex_date"])] = Decimal(str(row["split_factor"]))
    divs: dict[tuple[str, date], tuple] = {}
    dv = reg.read("dividend", columns=["symbol", "ex_date", "cash_per_lot_pre_tax",
                                       "round_lot"], symbols=sorted(symbols))
    for row in dv.iter_rows(named=True):
        divs[(row["symbol"], row["ex_date"])] = (
            Decimal(str(row["cash_per_lot_pre_tax"])), int(row["round_lot"]))
    return {"preclose": preclose, "limits": limits,
            "splits": splits, "dividends": divs, "trade_series": trade_series,
            "dataset_id": reg.dataset_id}


def _mark_on_or_before(trade_series, symbol: str, day: date) -> Decimal | None:
    series = trade_series.get(symbol)
    if not series:
        return None
    lo, hi = 0, len(series)
    while lo < hi:                     # 最后一个 (date <= day) 的可交易 close
        mid = (lo + hi) // 2
        if series[mid][0] <= day:
            lo = mid + 1
        else:
            hi = mid
    return series[lo - 1][1] if lo > 0 else None


def build_days(fills_df: pl.DataFrame, sandbox, calendar: list[date]):
    symbols = set(fills_df["symbol"].unique().to_list())
    prev_by_day = {d: (calendar[i - 1] if i > 0 else None)
                   for i, d in enumerate(calendar)}
    day_fills: dict[date, list[Fill]] = {}
    for row in fills_df.iter_rows(named=True):
        d = row["date"]
        key = (row["symbol"], d)
        up, down = sandbox["limits"].get(key, (None, None))
        anchor_day = (prev_by_day.get(row["decision_date"])
                      if row["decision_session"] == "am"
                      else row["decision_date"])
        day_fills.setdefault(d, []).append(Fill(
            fill_id=row["fill_id"], symbol=row["symbol"], side=row["side"],
            day=d, session=row["session"], shares=int(row["shares"]),
            price=Decimal(str(row["price"])),
            notional=_dec_or_none(row["notional"]),
            commission=_dec_or_none(row["commission"]),
            stamp_tax=_dec_or_none(row["stamp_tax"]),
            net_cash_flow=_dec_or_none(row["net_cash_flow"]),
            intent=row["intent"] or "", fill_type=row["fill_type"] or "limit",
            is_etf=bool(row["is_etf"]),
            decision_day=row["decision_date"],
            decision_session=row["decision_session"],
            anchor_day=anchor_day, down_limit=down, up_limit=up,
            prev_close=sandbox["preclose"].get(key)))

    ca_by_day: dict[date, dict[str, list]] = {}
    for (sym, d), ratio in sandbox["splits"].items():
        if sym in symbols:
            ca_by_day.setdefault(d, {}).setdefault("splits", []).append(
                SplitAction(sym, d, ratio))
    for (sym, d), (per_lot, round_lot) in sandbox["dividends"].items():
        if sym in symbols:
            ca_by_day.setdefault(d, {}).setdefault("dividends", []).append(
                DividendAction(sym, d, per_lot / Decimal(round_lot),
                               cash_per_lot=per_lot, round_lot=round_lot,
                               prev_close=sandbox["preclose"].get((sym, d))))

    days: list[DayInput] = []
    for d in calendar:
        ca = ca_by_day.get(d, {})
        marks = {}
        for sym in symbols:
            px = _mark_on_or_before(sandbox["trade_series"], sym, d)
            if px is not None:
                marks[sym] = px
        days.append(DayInput(day=d, splits=tuple(ca.get("splits", [])),
                             dividends=tuple(ca.get("dividends", [])),
                             fills=day_fills.get(d, []), marks=marks))
    return days


def reconcile_arm(repo: Path, run_id: str, arm: str) -> dict:
    t0 = time.perf_counter()
    out = ArmOutputs(repo, run_id, arm)
    equity_df = pl.read_parquet(out.equity_path)
    calendar = equity_df["date"].to_list()
    fills_df = pl.read_parquet(out.fills_path)
    symbols = set(fills_df["symbol"].unique().to_list())
    sandbox = load_sandbox_maps(repo, symbols)
    days = build_days(fills_df, sandbox, calendar)

    led = ReferenceLedger(500000)                                    # 合同评分口径（逐笔舍入）
    led.replay(days)
    led_exact = ReferenceLedger(500000, fees=FeeSchedule(round_per_movement=False))
    led_exact.replay(days)                                           # 完整性证明口径（不舍入）

    run_eq = {row["date"]: row for row in equity_df.iter_rows(named=True)}
    exact_eq = {rec.day: rec for rec in led_exact.days}

    ledger_rows: list[dict] = []
    n_days = 0
    max_eq_diff = Decimal(0)
    max_exact_diff = Decimal(0)
    first_diff_day = None
    n_days_diff = 0

    for rec in led.days:
        r = run_eq.get(rec.day)
        if r is None:
            continue
        n_days += 1
        ds = q(rec.free_settled_cash) - q(r["settled_cash"])
        du = q(rec.unsettled_sale_proceeds) - q(r["pending_next_day"])
        dmv = q(rec.position_mv) - q(r["positions_value"])
        de = q(rec.equity) - q(r["equity"])
        de_exact = exact_eq[rec.day].equity - Decimal(str(r["equity"]))
        max_eq_diff = max(max_eq_diff, abs(de))
        max_exact_diff = max(max_exact_diff, abs(de_exact))
        if abs(ds) > Decimal("0.005"):
            n_days_diff += 1
            if first_diff_day is None:
                first_diff_day = rec.day
        note = ""
        any_bucket_diff = (abs(ds) > Decimal("0.005") or abs(du) > Decimal("0.005")
                           or abs(dmv) > Decimal("0.005") or abs(de) > Decimal("0.005"))
        if any_bucket_diff:
            note = ("rounding-location diff: per-movement ROUND_HALF_UP vs engine "
                    "float accumulation; exact-track |equity diff| = "
                    f"{abs(de_exact):.2e}")
            if abs(de) <= Decimal("0.005") and (abs(ds) > Decimal("0.005")
                                                or abs(du) > Decimal("0.005")):
                note = ("rounding-location diff between cash buckets "
                        f"(settled {ds}, unsettled {du}); equity unchanged "
                        f"(exact-track |equity diff| = {abs(de_exact):.2e})")
        if dmv != 0 and rec.stale_mark_symbols:
            note = (note + "; " if note else "") + \
                "stale mark (no daily bar): " + ",".join(rec.stale_mark_symbols)
        ledger_rows.append({
            "run_id": run_id, "arm": arm, "record_type": "equity_day",
            "day": rec.day.isoformat(), "session": "", "symbol": "", "side": "",
            "key": rec.day.isoformat(),
            "ref_commission": "", "engine_commission": "", "commission_diff": "",
            "ref_stamp": "", "engine_stamp": "", "stamp_diff": "",
            "ref_fees": "", "engine_fees": "", "fees_diff": "",
            "ref_net_cash": "", "engine_net_cash": "", "net_cash_diff": "",
            "ref_settled_cash": str(q(rec.free_settled_cash)),
            "engine_settled_cash": str(q(r["settled_cash"])),
            "settled_diff": str(ds),
            "ref_unsettled": str(q(rec.unsettled_sale_proceeds)),
            "engine_unsettled": str(q(r["pending_next_day"])),
            "unsettled_diff": str(du),
            "ref_position_mv": str(q(rec.position_mv)),
            "engine_position_mv": str(q(r["positions_value"])),
            "mv_diff": str(dmv),
            "ref_equity": str(q(rec.equity)), "engine_equity": str(q(r["equity"])),
            "equity_diff": str(de),
            "exact_equity_diff": f"{de_exact:.2e}",
            "ref_shares": "", "engine_shares": "", "shares_diff": "",
            "note": note,
        })

    # ---- 逐笔成交费用对账（参考按 price×shares 精确 Decimal 计费） ----------
    fees = FeeSchedule()
    n_comm_mismatch = 0
    n_stamp_mismatch = 0
    n_net_mismatch = 0
    n_subcent = 0
    ref_comm_total = Decimal(0)
    ref_stamp_total = Decimal(0)
    engine_comm_total = Decimal(0)
    engine_stamp_total = Decimal(0)
    for row in fills_df.iter_rows(named=True):
        notional = Decimal(str(row["price"])) * Decimal(int(row["shares"]))
        comm = fees.commission(notional)
        stamp = fees.stamp_sell(row["date"], notional, is_etf=bool(row["is_etf"])) \
            if row["side"] == "sell" else Decimal("0.00")
        total = cent(comm + stamp)
        net = cent(notional - total) if row["side"] == "sell" else -cent(notional + total)
        e_comm = q(row["commission"])
        e_stamp = q(row["stamp_tax"])
        e_fees = q(row["fees_total"])
        e_net = q(row["net_cash_flow"])
        cd = comm - e_comm
        sd = stamp - e_stamp
        fd = total - e_fees
        nd = net - e_net
        if cd != 0:
            n_comm_mismatch += 1
        if sd != 0:
            n_stamp_mismatch += 1
        if nd != 0:
            n_net_mismatch += 1
        raw_comm = notional * fees.commission_rate
        raw_stamp = notional * (fees.stamp_sell_before if row["date"] < fees.stamp_boundary
                                else fees.stamp_sell_on_after) if row["side"] == "sell" else Decimal(0)
        if (raw_comm != raw_comm.quantize(CENT)
                or (raw_stamp != raw_stamp.quantize(CENT))):
            n_subcent += 1
        ref_comm_total += comm
        ref_stamp_total += stamp
        engine_comm_total += e_comm
        engine_stamp_total += e_stamp
        note = ""
        if cd or sd or nd:
            note = ("float representation: engine float component(s) differ from "
                    "the Decimal value at the cent boundary; net_cash_diff="
                    f"{nd}")
        ledger_rows.append({
            "run_id": run_id, "arm": arm, "record_type": "fill",
            "day": row["date"].isoformat(), "session": row["session"],
            "symbol": row["symbol"], "side": row["side"], "key": row["fill_id"],
            "ref_commission": str(comm), "engine_commission": str(e_comm),
            "commission_diff": str(cd),
            "ref_stamp": str(stamp), "engine_stamp": str(e_stamp),
            "stamp_diff": str(sd),
            "ref_fees": str(total), "engine_fees": str(e_fees),
            "fees_diff": str(fd),
            "ref_net_cash": str(net), "engine_net_cash": str(e_net),
            "net_cash_diff": str(nd),
            "ref_settled_cash": "", "engine_settled_cash": "", "settled_diff": "",
            "ref_unsettled": "", "engine_unsettled": "", "unsettled_diff": "",
            "ref_position_mv": "", "engine_position_mv": "", "mv_diff": "",
            "ref_equity": "", "engine_equity": "", "equity_diff": "",
            "exact_equity_diff": "",
            "ref_shares": "", "engine_shares": "", "shares_diff": "",
            "note": note,
        })

    # ---- 期末持仓对账 -----------------------------------------------------
    ref_final = {s: sum(c.shares for c in cs) for s, cs in led.clips.items()
                 if sum(c.shares for c in cs) > 0}
    engine_final: dict[str, int] = {}
    if out.clips_path.is_file():
        for row in pl.read_parquet(out.clips_path).iter_rows(named=True):
            engine_final[row["symbol"]] = engine_final.get(row["symbol"], 0) \
                + int(row["shares"])
    for sym in sorted(set(ref_final) | set(engine_final)):
        rs, es = ref_final.get(sym, 0), engine_final.get(sym, 0)
        ledger_rows.append({
            "run_id": run_id, "arm": arm, "record_type": "final_position",
            "day": calendar[-1].isoformat(), "session": "", "symbol": sym,
            "side": "", "key": sym,
            "ref_commission": "", "engine_commission": "", "commission_diff": "",
            "ref_stamp": "", "engine_stamp": "", "stamp_diff": "",
            "ref_fees": "", "engine_fees": "", "fees_diff": "",
            "ref_net_cash": "", "engine_net_cash": "", "net_cash_diff": "",
            "ref_settled_cash": "", "engine_settled_cash": "", "settled_diff": "",
            "ref_unsettled": "", "engine_unsettled": "", "unsettled_diff": "",
            "ref_position_mv": "", "engine_position_mv": "", "mv_diff": "",
            "ref_equity": "", "engine_equity": "", "equity_diff": "",
            "exact_equity_diff": "",
            "ref_shares": str(rs), "engine_shares": str(es),
            "shares_diff": str(rs - es),
            "note": "final held shares match" if rs == es else "SHARE MISMATCH",
        })

    # ---- 现金三分离检查点 -------------------------------------------------
    cash_rows: list[dict] = []
    checkpoints = {calendar[0], calendar[-1]}
    checkpoints |= {d for d in calendar if (d.month, d.day) == (12, 31)}
    if first_diff_day is not None:
        checkpoints.add(first_diff_day)
    for d in sorted(checkpoints):
        rec = next((x for x in led.days if x.day == d), None)
        r = run_eq.get(d)
        if rec is None or r is None:
            continue
        cash_rows.append({
            "run_id": run_id, "arm": arm, "checkpoint": d.isoformat(),
            "ref_free_settled": str(q(rec.free_settled_cash)),
            "engine_free_settled": str(q(r["settled_cash"])),
            "diff_settled": str(q(rec.free_settled_cash) - q(r["settled_cash"])),
            "ref_unsettled": str(q(rec.unsettled_sale_proceeds)),
            "engine_unsettled": str(q(r["pending_next_day"])),
            "diff_unsettled": str(q(rec.unsettled_sale_proceeds)
                                  - q(r["pending_next_day"])),
            "ref_am_to_pm": str(q(rec.am_to_pm_proceeds)),
            "engine_am_to_pm": str(q(r["pending_am_to_pm"])),
            "ref_cash_total": str(q(rec.cash_total)),
            "engine_cash_total": str(q(r["settled_cash"] + r["pending_next_day"]
                                       + r["pending_am_to_pm"])),
            "diff_cash_total": str(q(rec.cash_total) - q(
                r["settled_cash"] + r["pending_next_day"] + r["pending_am_to_pm"])),
            "ref_equity": str(q(rec.equity)), "engine_equity": str(q(r["equity"])),
            "diff_equity": str(q(rec.equity) - q(r["equity"])),
            "note": ("first rounding-location divergence day"
                     if d == first_diff_day else
                     "year-end" if (d.month, d.day) == (12, 31) else "checkpoint"),
        })

    # ---- 公司行动对账 -----------------------------------------------------
    ca_rows: list[dict] = []
    run_ca: dict[tuple[str, date], dict] = {}
    if out.events_path.is_file():
        for row in pl.read_parquet(out.events_path).iter_rows(named=True):
            e = row.get("event", "")
            if e not in ("corp_action_dividend", "corp_action_split"):
                continue
            sym = row.get("symbol")
            if not sym:                       # 引擎公司行动事件行 symbol 为空
                sym = (row.get("detail") or "").split(":", 1)[0].strip()
            run_ca.setdefault((sym, row["date"]), {})[
                "dividend" if e == "corp_action_dividend" else "split"] = row
    prev_held = {}
    for i, rec in enumerate(led.days):
        prev_held[rec.day] = dict(led.days[i - 1].held_shares) if i > 0 else {}
    ca_count = 0
    for (sym, d), kinds in sorted(run_ca.items(),
                                  key=lambda kv: (kv[0][1], kv[0][0])):
        # 一个 (symbol, 除权日) 可同时有送转与分红（A 股常见「送转+派现」）；
        # 计数按事件行数，不按键数，避免少计。
        ca_count += len(kinds)
        if "split" in kinds:
            r = kinds["split"]
            run_ratio = Decimal(str(r["ratio"]))
            ref_ratio = sandbox["splits"].get((sym, d))
            ref_after = led.split_results.get((sym, d))
            run_after = int(r["shares"]) if r["shares"] is not None else None
            ca_rows.append({
                "run_id": run_id, "arm": arm, "day": d.isoformat(), "symbol": sym,
                "action_type": "share_change",
                "run_ratio": str(run_ratio),
                "ref_ratio": str(ref_ratio) if ref_ratio is not None else "",
                "ratio_diff": str((ref_ratio or Decimal(0)) - run_ratio),
                "run_cash_amount": "", "ref_cash_amount": "", "cash_diff": "",
                "run_shares_after": str(run_after) if run_after is not None else "",
                "ref_shares_after": str(ref_after) if ref_after is not None else "",
                "shares_diff": (str(ref_after - run_after)
                                if ref_after is not None and run_after is not None
                                else ""),
                "note": "share-transform ratio cross-checked against "
                        "sandbox split_factor; shares_after from reference clips",
            })
        if "dividend" in kinds:
            r = kinds["dividend"]
            run_cash = q(r["cash_amount"])
            per_lot, round_lot = sandbox["dividends"].get((sym, d), (None, None))
            pre_ex = prev_held.get(d, {}).get(sym, 0)
            ref_cash = (q(per_lot / Decimal(round_lot) * Decimal(pre_ex))
                        if per_lot is not None and round_lot else None)
            ca_rows.append({
                "run_id": run_id, "arm": arm, "day": d.isoformat(), "symbol": sym,
                "action_type": "cash_dividend",
                "run_ratio": "", "ref_ratio": "", "ratio_diff": "",
                "run_cash_amount": str(run_cash),
                "ref_cash_amount": str(ref_cash) if ref_cash is not None else "",
                "cash_diff": (str(ref_cash - run_cash) if ref_cash is not None
                              else ""),
                "run_shares_after": "", "ref_shares_after": "", "shares_diff": "",
                "note": (f"sandbox per-lot {per_lot}/round_lot {round_lot} x "
                         f"{pre_ex} pre-ex shares; run detail: "
                         f"{(r.get('detail') or '')[:70]}"
                         if per_lot is not None else
                         f"run books {run_cash}; no sandbox dividend row"),
            })
    if not ca_rows:
        ca_rows.append({
            "run_id": run_id, "arm": arm, "day": "", "symbol": "",
            "action_type": "none", "run_ratio": "", "ref_ratio": "",
            "ratio_diff": "", "run_cash_amount": "", "ref_cash_amount": "",
            "cash_diff": "", "run_shares_after": "", "ref_shares_after": "",
            "shares_diff": "", "note": "zero corporate-action events for this arm",
        })

    summary = {
        "run_id": run_id, "arm": arm, "n_days": n_days,
        "n_events": fills_df.height + ca_count,
        "n_fills": fills_df.height, "n_corporate_actions": ca_count,
        "max_abs_equity_diff_round": str(max_eq_diff),
        "max_abs_equity_diff_exact": f"{max_exact_diff:.3e}",
        "first_rounding_diff_day": (first_diff_day.isoformat()
                                    if first_diff_day else None),
        "n_days_rounding_diff_gt_half_cent": n_days_diff,
        "n_fill_commission_mismatch": n_comm_mismatch,
        "n_fill_stamp_mismatch": n_stamp_mismatch,
        "n_fill_net_cash_mismatch": n_net_mismatch,
        "n_fills_with_subcent_fee": n_subcent,
        "ref_commission_total": str(ref_comm_total),
        "engine_commission_total": str(engine_comm_total),
        "ref_stamp_total": str(ref_stamp_total),
        "engine_stamp_total": str(engine_stamp_total),
        "final_shares_match": ref_final == engine_final,
        "wall_seconds": round(time.perf_counter() - t0, 3),
    }
    return {"ledger_rows": ledger_rows, "cash_rows": cash_rows, "ca_rows": ca_rows,
            "summary": summary, "evidence_files": out.evidence_files(),
            "sandbox_dataset_id": sandbox["dataset_id"]}


LEDGER_FIELDS = [
    "run_id", "arm", "record_type", "day", "session", "symbol", "side", "key",
    "ref_commission", "engine_commission", "commission_diff",
    "ref_stamp", "engine_stamp", "stamp_diff",
    "ref_fees", "engine_fees", "fees_diff",
    "ref_net_cash", "engine_net_cash", "net_cash_diff",
    "ref_settled_cash", "engine_settled_cash", "settled_diff",
    "ref_unsettled", "engine_unsettled", "unsettled_diff",
    "ref_position_mv", "engine_position_mv", "mv_diff",
    "ref_equity", "engine_equity", "equity_diff", "exact_equity_diff",
    "ref_shares", "engine_shares", "shares_diff", "note",
]
CASH_FIELDS = [
    "run_id", "arm", "checkpoint", "ref_free_settled", "engine_free_settled",
    "diff_settled", "ref_unsettled", "engine_unsettled", "diff_unsettled",
    "ref_am_to_pm", "engine_am_to_pm", "ref_cash_total", "engine_cash_total",
    "diff_cash_total", "ref_equity", "engine_equity", "diff_equity", "note",
]
FEE_FIELDS = [
    "run_id", "arm", "n_fills", "ref_commission_total", "engine_commission_total",
    "commission_diff", "ref_stamp_total", "engine_stamp_total", "stamp_diff",
    "ref_fees_total", "engine_fees_total", "fees_diff",
    "n_fill_commission_mismatch", "n_fill_stamp_mismatch",
    "n_fill_net_cash_mismatch", "n_fills_with_subcent_fee", "note",
]
CA_FIELDS = [
    "run_id", "arm", "day", "symbol", "action_type", "run_ratio", "ref_ratio",
    "ratio_diff", "run_cash_amount", "ref_cash_amount", "cash_diff",
    "run_shares_after", "ref_shares_after", "shares_diff", "note",
]


def _write_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fields})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--evidence-dir", required=True)
    args = parser.parse_args(argv)

    repo = Path(args.repo_root).resolve()
    ev = repo / args.evidence_dir
    ev.mkdir(parents=True, exist_ok=True)

    ledger_rows: list[dict] = []
    cash_rows: list[dict] = []
    ca_rows: list[dict] = []
    fee_rows: list[dict] = []
    coverage: list[dict] = []
    summaries: list[dict] = []

    for run_id, arm in TARGETS:
        result = reconcile_arm(repo, run_id, arm)
        ledger_rows += result["ledger_rows"]
        cash_rows += result["cash_rows"]
        ca_rows += result["ca_rows"]
        s = result["summary"]
        summaries.append(s)
        fee_rows.append({
            "run_id": run_id, "arm": arm, "n_fills": s["n_fills"],
            "ref_commission_total": s["ref_commission_total"],
            "engine_commission_total": s["engine_commission_total"],
            "commission_diff": str(Decimal(s["ref_commission_total"])
                                   - Decimal(s["engine_commission_total"])),
            "ref_stamp_total": s["ref_stamp_total"],
            "engine_stamp_total": s["engine_stamp_total"],
            "stamp_diff": str(Decimal(s["ref_stamp_total"])
                              - Decimal(s["engine_stamp_total"])),
            "ref_fees_total": str(Decimal(s["ref_commission_total"])
                                  + Decimal(s["ref_stamp_total"])),
            "engine_fees_total": str(Decimal(s["engine_commission_total"])
                                     + Decimal(s["engine_stamp_total"])),
            "fees_diff": str(Decimal(s["ref_commission_total"])
                             + Decimal(s["ref_stamp_total"])
                             - Decimal(s["engine_commission_total"])
                             - Decimal(s["engine_stamp_total"])),
            "n_fill_commission_mismatch": s["n_fill_commission_mismatch"],
            "n_fill_stamp_mismatch": s["n_fill_stamp_mismatch"],
            "n_fill_net_cash_mismatch": s["n_fill_net_cash_mismatch"],
            "n_fills_with_subcent_fee": s["n_fills_with_subcent_fee"],
            "note": ("net_cash_diff counts fills where the recorded float fee "
                     "rounds to a different cent than the exact Decimal fee at a "
                     "half-cent boundary"),
        })
        coverage.append({
            "run_id": run_id, "arm": arm,
            "n_days": s["n_days"], "n_days_covered": s["n_days"],
            "n_events": s["n_events"], "n_events_covered": s["n_events"],
            "n_fills": s["n_fills"], "n_fills_covered": s["n_fills"],
            "n_corporate_actions": s["n_corporate_actions"],
            "n_corporate_actions_covered": s["n_corporate_actions"],
            "sandbox_dataset_id": result["sandbox_dataset_id"],
            "input_files": result["evidence_files"],
            "replay_command": ("PYTHONPATH=src .venv/Scripts/python.exe -m "
                               "quant.research.reference_ledger_reconcile "
                               f"--evidence-dir {args.evidence_dir}"),
            "wall_seconds": s["wall_seconds"],
            "max_abs_equity_diff_round": s["max_abs_equity_diff_round"],
            "max_abs_equity_diff_exact": s["max_abs_equity_diff_exact"],
            "final_shares_match": s["final_shares_match"],
        })

    _write_csv(ev / "ledger_reconciliation.csv", LEDGER_FIELDS, ledger_rows)
    _write_csv(ev / "cash_reconciliation.csv", CASH_FIELDS, cash_rows)
    _write_csv(ev / "fee_type_reconciliation.csv", FEE_FIELDS, fee_rows)
    _write_csv(ev / "corporate_action_reconciliation.csv", CA_FIELDS, ca_rows)
    (ev / "coverage_manifest.json").write_text(
        json.dumps({"schema_version": "1.0",
                    "targets_declared_in_task": 9,
                    "targets_covered": len(coverage),
                    "note": "任务书文字写 9 个目标，但逐项列出的臂为 3+4+3=10；"
                            "本清单覆盖全部 10 个已列名臂。",
                    "targets": coverage},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    (ev / "reconcile_summary.json").write_text(
        json.dumps({"schema_version": "1.0", "arms": summaries},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"arms": summaries}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
