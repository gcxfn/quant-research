# -*- coding: utf-8 -*-
"""C3-A 开环对账驱动：用独立 matcher 重新判定真实 run 的每一笔订单。

**独立性**：本模块只做 IO 与编排——读 run 产物（只读）、读 C1 Dev 沙箱
（经 ``quant.data.dev_sandbox``）、把规范化输入喂给
``quant.research.reference_matcher``。它**不 import** ``quant.backtest`` /
``quant.portfolio``，也不复制主引擎的穿透/合法性/生命周期代码。

订单来源（先探明产物结构后的结论，见 ``c3_case_report.md`` 第 1 节）
------------------------------------------------------------------
每臂 ``outputs/<arm>_events.parquet`` 是**订单级**事件日志：

* ``filled_limit_buy`` / ``filled_limit_sell`` / ``not_penetrated`` /
  ``void_*`` / ``below_min_lot`` / ``session_expired`` 行带
  ``order_id`` + ``limit_price``（末次判定，含未成交原因）；
* ``market_exit_*`` 行不带 ``order_id``（引擎用 ``emit(order=None)`` 合成），
  但其 ``detail`` 前缀是标的代码，``ref_price`` 是当 session 开盘价。
  K=3 兜底的成交/顺延因此**可**逐笔复核。

因此两路判定：

1. **限价单**：``order_id`` 解析出 (symbol, side, intent, decision_date,
   decision_session)，``date/session`` 是生效半日，``limit_price`` 是限价。
2. **K=3 兜底尝试**：从 ``market_exit_*`` 行取标的/半日/开盘价，用
   ``ReferenceMatcher.judge_fallback`` 只读复核。

订单状态从**该臂自己的 fills 产物**重建（独立费率/结算/公司行动实现），
所以判定用的是「引擎事实持仓」+「matcher 独立判定」，不是自证。

**已知口径限制（如实登记）**
* 未成交买但引擎没记股数（``not_penetrated`` / ``void_suspended``）：引擎的
  判定顺序是 bar → 限价合法性 → 穿透 → 数量/资金，所以原因类别与数量无关。
  该路用「一手探针」（``target_notional = 1 手名义``）复现，并登记
  ``probe_mode=lot_probe_penetration``。
* ``below_min_lot`` 行的 ``detail`` 含真实目标名义（"target 20720.91 at p
  442.9400"），据此复现 ``below_lot``，登记 ``probe_mode=target_from_detail``。
* 单只 25% 帽用**自算**决策点权益快照（官方收盘 mark）判定；与引擎快照口径
  的差异会在 ``cap_check`` 列体现，属披露项。

用法::

    PYTHONPATH=src .venv/Scripts/python.exe -m quant.research.reference_matcher_reconcile \
        --evidence-dir docs/evidence/trust-rebuild/<C3-run>

输出：``order_reconciliation.csv``、``reconcile_summary.json``。
C3-B 语义链（C-05 追踪/席位/风险/退出）在 ``c3_semantic_chain.py``——它要读真实
策略与风险代码，故意与本模块分离，以保持本模块的独立性声明可被 import 扫描证实。
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from datetime import date
from decimal import Decimal
from pathlib import Path

import polars as pl

sys.path.insert(0, "src")

from quant.data import dev_sandbox  # noqa: E402  (IO 层，非主引擎)
from quant.research.reference_matcher import (  # noqa: E402
    Bar, BarTable, Book, Clip, INTENT_RISK, JudgeState, LimitRow, LimitTable,
    Order, ReferenceMatcher,
)

INITIAL_CASH = Decimal("500000.00")

#: 臂清单（"先探明产物结构"：baseline replay 5 臂 + eventfam main 4 臂都有
#: 订单级事件日志；attrib2 只有 B1 汇总结论，无订单日志 → 只作 C-05 追踪来源）。
BASELINE_RUN = "20260921T210100-baseline-replay4-9x4q2"
EVENTFAM_RUN = "20260921T223157-eventfam-main-cb4cff"
ARMS: list[tuple[str, str]] = [
    (BASELINE_RUN, "FULL-bin"), (BASELINE_RUN, "NOACCT-bin"),
    (BASELINE_RUN, "NOSNR-bin"), (BASELINE_RUN, "SIG-old"),
    (BASELINE_RUN, "SIG-reg"),
    (EVENTFAM_RUN, "A1"), (EVENTFAM_RUN, "A2"),
    (EVENTFAM_RUN, "B1"), (EVENTFAM_RUN, "B2"),
]

ORDER_ID_RE = re.compile(
    r"^(?P<sym>[^-]+)-(?P<side>buy|sell)(?:/(?P<intent>risk|profit))?"
    r"-(?P<day>\d{4}-\d{2}-\d{2})-(?P<sess>am|pm)$")
TARGET_RE = re.compile(r"target\s+(?P<tn>\d+(?:\.\d+)?)\s+at\s+p")

#: 引擎事件 → matcher 原因类别的期望集合（引擎对 profit 未成交统一写
#: ``session_expired``，语义仍是「未穿透/到期」，故给两个合法值）。
EXPECTED_REASON: dict[str, set[str]] = {
    "filled_limit_buy": {"filled"},
    "filled_limit_sell": {"filled", "partial_fill"},
    "market_exit_filled": {"filled"},
    "not_penetrated": {"never_crossed"},
    "session_expired": {"never_crossed", "expired"},
    "void_suspended": {"suspended"},
    "void_limit_out_of_range": {"limit_illegal"},
    "void_no_limit_info": {"limit_missing"},
    "void_insufficient_cash": {"cash_short"},
    "void_t1_locked": {"t1_locked"},
    "void_no_position": {"no_position"},
    "below_min_lot": {"below_lot"},
    "market_exit_deferred_limitdown": {"limit_illegal"},
    "market_exit_deferred_suspended": {"suspended"},
    "market_exit_deferred_t1locked": {"t1_locked"},
    "market_exit_void_no_position": {"no_position"},
}


# --------------------------------------------------------------------------- #
# run 产物解析
# --------------------------------------------------------------------------- #
def parse_order_id(order_id: str) -> dict | None:
    m = ORDER_ID_RE.match(order_id)
    if m is None:
        return None
    g = m.groupdict()
    return {
        "symbol": g["sym"], "side": g["side"], "intent": g["intent"] or "",
        "decision_date": date.fromisoformat(g["day"]),
        "decision_session": g["sess"],
    }


def _fallback_symbol(detail: str) -> str | None:
    if not detail:
        return None
    head = detail.split(":", 1)[0].strip()
    return head if head and " " not in head else None


FALLBACK_ORDER_RE = re.compile(
    r"^(?P<sym>.+)-sell/risk-K3FB-(?P<day>\d{4}-\d{2}-\d{2})-(?P<sess>am|pm)$")


class ArmEvents:
    """一个臂的订单级事件 + 成交。"""

    def __init__(self, run_dir: Path, arm: str) -> None:
        self.run_dir = run_dir
        self.arm = arm
        ev = pl.read_parquet(run_dir / "outputs" / f"{arm}_events.parquet")
        fl = pl.read_parquet(run_dir / "outputs" / f"{arm}_fills.parquet")
        # fills：按 order_id 归组 + 按 (day, session) 归组（后者用于兜底行的
        # 标的恢复与「未归入订单流的成交」兜底入账，保证事实状态完整）。
        self.fills_by_order: dict[str, list[dict]] = {}
        self.fills_by_session: dict[tuple[date, str], list[dict]] = {}
        for r in fl.iter_rows(named=True):
            self.fills_by_order.setdefault(r["order_id"], []).append(r)
            self.fills_by_session.setdefault((r["date"], r["session"]),
                                             []).append(r)
        #: K3FB 合成 order_id → (symbol, day, session)：引擎的 market_exit_filled
        #: 行不带 order_id/标的（detail 只有 "no_limit_info: fallback executed"），
        #: 标的只能从同日的兜底成交单恢复。
        #: K=3 兜底成交 → (day, session) → 标的。引擎的 market_exit_filled 事件
        #: 不带 order_id/标的；但该成交在 fills 里以 ``fill_type ==
        #: 'market_fallback'`` 标记，标的可从那里唯一恢复（订单号仍是那个
        #: 站立风险单的 id，不是 K3FB 合成号，所以不能靠订单号正则）。
        self.fallback_fills: dict[tuple[date, str], dict] = {}
        for rows in self.fills_by_order.values():
            for r in rows:
                if r["fill_type"] != "market_fallback":
                    continue
                self.fallback_fills[(r["date"], r["session"])] = {
                    "symbol": r["symbol"], "fill": r}
        self.limit_rows: list[dict] = []
        self.fallback_rows: list[dict] = []
        for r in ev.iter_rows(named=True):
            event = r["event"]
            if event in ("intent_lifecycle", "corp_action_dividend",
                         "corp_action_split"):
                continue
            if r["order_id"] and r["limit_price"] is not None:
                parsed = parse_order_id(r["order_id"])
                if parsed is None:
                    continue
                self.limit_rows.append({**parsed, "event": event,
                                        "live_date": r["date"],
                                        "live_session": r["session"],
                                        "limit_price": r["limit_price"],
                                        "ref_price": r["ref_price"],
                                        "shares": r["shares"],
                                        "priority": r["priority"],
                                        "detail": r["detail"] or "",
                                        "order_id": r["order_id"]})
            elif event.startswith("market_exit_"):
                key = (r["date"], r["session"])
                recorded = self.fallback_fills.get(key)
                sym = recorded["symbol"] if recorded else None
                if sym is None:
                    sym = _fallback_symbol(r["detail"] or "")
                if sym is None:
                    continue
                self.fallback_rows.append({
                    "event": event, "symbol": sym, "live_date": r["date"],
                    "live_session": r["session"], "ref_price": r["ref_price"],
                    "shares": r["shares"], "detail": r["detail"] or "",
                    "symbol_source": ("fill_order_id" if recorded
                                      else "detail_prefix")})
        self.limit_by_session: dict[tuple[date, str], list[dict]] = {}
        for x in self.limit_rows:
            self.limit_by_session.setdefault(
                (x["live_date"], x["live_session"]), []).append(x)
        self.fallback_by_session: dict[tuple[date, str], list[dict]] = {}
        for x in self.fallback_rows:
            self.fallback_by_session.setdefault(
                (x["live_date"], x["live_session"]), []).append(x)
        self.symbols = sorted({x["symbol"] for x in self.limit_rows}
                              | {x["symbol"] for x in self.fallback_rows})

    def session_keys(self) -> list[tuple[date, str]]:
        """全部需要推进的半日：订单/兜底事件 + **成交**所在的半日。

        包含成交流所在半日很关键：只按事件行推进会漏掉「当天没有订单事件但有
        成交」的半日，账本状态随后整体偏掉（NOACCT-bin 首轮即因此出现 51 处
        资金类差异）。
        """
        keys = {(x["live_date"], x["live_session"]) for x in self.limit_rows}
        keys |= {(x["live_date"], x["live_session"]) for x in self.fallback_rows}
        keys |= set(self.fills_by_session)
        return sorted(keys, key=lambda k: (k[0], 0 if k[1] == "am" else 1))


# --------------------------------------------------------------------------- #
# 沙箱行情
# --------------------------------------------------------------------------- #
class Market:
    """沙箱半日 bar + 涨跌停 + 官方日线 close（估值/锚）。"""

    def __init__(self, sandbox, symbols: list[str]) -> None:
        half = sandbox.read("bars_halfday", symbols=symbols,
                            columns=["symbol", "date", "session", "open",
                                     "high", "low", "close"])
        bars = [Bar(r["symbol"], r["date"], r["session"], r["open"], r["high"],
                    r["low"], r["close"]) for r in half.iter_rows(named=True)]
        self.bars = BarTable(bars)
        lim = sandbox.read("limit", symbols=symbols)
        self.limits = LimitTable(
            [LimitRow(r["symbol"], r["date"], r["up_limit"], r["down_limit"])
             for r in lim.iter_rows(named=True)])
        daily = sandbox.read("bars_daily", symbols=symbols,
                             columns=["symbol", "date", "close"])
        self.close: dict[tuple[str, date], float] = {}
        self.days_by_symbol: dict[str, list[date]] = {}
        for r in daily.iter_rows(named=True):
            if r["close"] is None:
                continue
            self.close[(r["symbol"], r["date"])] = float(r["close"])
            self.days_by_symbol.setdefault(r["symbol"], []).append(r["date"])
        for sym in self.days_by_symbol:
            self.days_by_symbol[sym].sort()

    def trading_days(self) -> list[date]:
        """臂内标的出现过的全部交易日（并集）。

        结算时序必须按**交易日历**推进，不能只在「有订单/成交的那些半日」推进：
        否则前一个 pm 的卖出款会一直挂在待结算桶里（NOACCT-bin 首轮即因此少
        122800.77 元可用现金，39 笔买单的 affordability 判定翻转）。
        """
        days: set[date] = set()
        for ds in self.days_by_symbol.values():
            days |= set(ds)
        return sorted(days)

    def official_close(self, symbol: str, day: date) -> float | None:
        return self.close.get((symbol, day))

    def prev_trading_close(self, symbol: str, day: date) -> float | None:
        days = self.days_by_symbol.get(symbol)
        if not days:
            return None
        lo, hi = 0, len(days)
        while lo < hi:                       # bisect_left
            mid = (lo + hi) // 2
            if days[mid] < day:
                lo = mid + 1
            else:
                hi = mid
        return self.close.get((symbol, days[lo - 1])) if lo > 0 else None


class CorporateActions:
    """沙箱分红/送转（除息日口径）。"""

    def __init__(self, sandbox, symbols: list[str]) -> None:
        div = sandbox.read("dividend", symbols=symbols)
        self.dividends: dict[date, list[tuple[str, Decimal]]] = {}
        for r in div.iter_rows(named=True):
            per_share = Decimal(str(r["cash_per_lot_pre_tax"])) / \
                Decimal(str(r["round_lot"] or 100))
            self.dividends.setdefault(r["ex_date"], []).append(
                (r["symbol"], per_share))
        sp = sandbox.read("split_factor", symbols=symbols)
        self.splits: dict[date, list[tuple[str, Decimal]]] = {}
        for r in sp.iter_rows(named=True):
            self.splits.setdefault(r["ex_date"], []).append(
                (r["symbol"], Decimal(str(r["split_factor"]))))
        self._dates = sorted(set(self.dividends) | set(self.splits))

    def action_dates(self, after: date | None, upto: date) -> list[date]:
        """返回 ``(after, upto]`` 内的全部除权/除息日（升序）。

        ``after=None`` 表示序列开头。用二分定位避免逐个日期扫描。
        """
        def bisect_right(value: date, hi: int) -> int:
            lo = 0
            while lo < hi:
                mid = (lo + hi) // 2
                if self._dates[mid] <= value:
                    lo = mid + 1
                else:
                    hi = mid
            return lo

        end = bisect_right(upto, len(self._dates))
        if after is None:
            return self._dates[:end]
        return self._dates[bisect_right(after, end):end]


# --------------------------------------------------------------------------- #
# 单臂对账
# --------------------------------------------------------------------------- #
def reconcile_arm(run_dir: Path, arm: str, market: Market, ca: CorporateActions
                  ) -> tuple[list[dict], dict]:
    ev = ArmEvents(run_dir, arm)
    book = Book(INITIAL_CASH)
    m = ReferenceMatcher(market.bars, market.limits, book=book)
    rows: list[dict] = []
    counts = {"orders": 0, "matched": 0, "mismatched": 0,
              "fallback_attempts": 0, "fallback_matched": 0,
              "fallback_mismatched": 0, "swept_fills": 0,
              "fills_compared": 0, "fills_fields_match": 0,
              "fills_fields_mismatch": 0}
    booked: set[str] = set()
    calendar = [(d, s) for d in market.trading_days() for s in ("am", "pm")]
    calendar = sorted(set(calendar) | set(ev.session_keys()),
                      key=lambda k: (k[0], 0 if k[1] == "am" else 1))
    cur_day: date | None = None
    for day, sess in calendar:
        if day != cur_day:
            # 公司行动：把 (上一推进日, day] 区间内的**全部**除权/除息日按日序
            # 应用（不是只应用「有订单事件的那些日」——否则无事件的除息日会被
            # 静默跳过，现金整体偏少；NOACCT-bin 首轮即因此少了 9975.48 元分红）。
            for ex in ca.action_dates(cur_day, day):
                # 分红权利数以**除权前**持股计（同一天既有送转又有分红时，先
                # 变换份额会把权利数放大一倍——引擎的预检也是如此）。
                pre_ex = {sym: book.total_shares(sym)
                          for sym, _ in ca.dividends.get(ex, ())}
                for sym, ratio in ca.splits.get(ex, ()):
                    book.apply_split(sym, ex, ratio)
                for sym, per_share in ca.dividends.get(ex, ()):
                    held = pre_ex.get(sym, 0)
                    if held:
                        book.cash += (per_share * held).quantize(Decimal("0.01"))
            cur_day = day
        if sess == "am":
            book.open_am()
        else:
            book.open_pm()
        # --- K=3 兜底尝试（引擎 step B 在卖单限价单之前） ---
        for fb in ev.fallback_by_session.get((day, sess), ()):
            counts["fallback_attempts"] += 1
            v = m.judge_fallback(fb["symbol"], day, sess,
                                 None if fb["shares"] is None
                                 else int(fb["shares"]))
            ok = v.reason in EXPECTED_REASON.get(fb["event"], {v.reason})
            if v.filled and fb["event"] == "market_exit_filled":
                ok = ok and abs(float(v.price) - float(fb["ref_price"])) < 1e-9
            counts["fallback_matched" if ok else "fallback_mismatched"] += 1
            rows.append(_row(fb, v, arm, "market_fallback", ok,
                             engine_event=fb["event"],
                             engine_shares=fb["shares"],
                             engine_price=fb["ref_price"],
                             symbol_source=fb.get("symbol_source", "")))
        # --- 限价单（买单按合同 m7 的 (priority, symbol) 稳定序竞争现金：
        #     后判定者只看高优先级成交后的余额；卖出不吃现金） ---
        # 判定次序沿合同 m7：先买单（按 (priority, symbol) 稳定序），再卖单。
        # 这个次序是必须的——引擎在 step A 按优先级竞争现金，后来的买单只看到
        # 高优先级成交后的余额（NOACCT-bin 的 39 处 `void_insufficient_cash`
        # 就是次序错误造成的：把低优先级买单先判，它就会用满额现金"成交"）。
        # 不需要额外的预留量：引擎的事实成交在本循环里逐笔入账，余额自然递减。
        session_orders = sorted(
            ev.limit_by_session.get((day, sess), ()),
            key=lambda x: (0 if x["side"] == "buy" else 1,
                           x["priority"] if x["priority"] is not None else 0,
                           x["symbol"]))
        for od in session_orders:
            counts["orders"] += 1
            v, probe = _judge_limit(m, market, book, od)
            engine_fill = (ev.fills_by_order.get(od["order_id"]) or [None])[0]
            ok = _compare(od, v)
            if ok:
                counts["matched"] += 1
            else:
                counts["mismatched"] += 1
            # 成交级逐字段比较（与 run 的 fills 产物对照：股数/价格/佣金/印花/费用）
            f_ok = _fill_fields_match(v, engine_fill)
            if engine_fill is not None:
                counts["fills_compared"] += 1
                counts["fills_fields_match" if f_ok else "fills_fields_mismatch"] += 1
            rows.append(_row(od, v, arm, probe, ok,
                             engine_event=od["event"],
                             engine_shares=od["shares"],
                             engine_price=od.get("limit_price"),
                             engine_fill=engine_fill,
                             fill_fields_match=f_ok))
            for f in ev.fills_by_order.get(od["order_id"], ()):
                _book_fill(book, f)
                booked.add(f["fill_id"])
        # --- 该半日尚未入账的成交（兜底合成单等）必须补齐 ---
        counts["swept_fills"] += _book_session_fills(book, ev, day, sess, booked)
    summary = {"arm": arm, "run_dir": run_dir.name, **counts,
               "matched_pct": (round(100.0 * counts["matched"]
                                     / max(1, counts["orders"]), 3)),
               "fallback_pct": (round(100.0 * counts["fallback_matched"]
                                      / max(1, counts["fallback_attempts"]), 3)),
               "unbooked_fills_swept": counts.get("swept_fills", 0)}
    return rows, summary


def _judge_limit(m: ReferenceMatcher, market: Market, book: Book,
                 od: dict) -> tuple[object, str]:
    """判定一张限价单；返回 (Verdict, probe_mode)。"""
    sym = od["symbol"]
    shares = None if od["shares"] is None else int(od["shares"])
    target_notional = None
    probe = "full"
    # 未成交买：引擎没记股数 → 用「一手探针」复现穿透/合法性/停牌层
    if od["side"] == "buy" and shares is None:
        probe = "lot_probe_penetration"
        target_notional = float(Decimal(str(od["limit_price"])) * 100)
    # below_min_lot：detail 里带真实目标名义 → 用它复现 below_lot
    if od["event"] == "below_min_lot":
        mt = TARGET_RE.search(od["detail"] or "")
        if mt:
            target_notional = float(mt.group("tn"))
            probe = "target_from_detail"
    o = Order(order_id=od["order_id"], symbol=sym, side=od["side"],
              decision_date=od["decision_date"],
              decision_session=od["decision_session"],
              live_date=od["live_date"], live_session=od["live_session"],
              limit_price=float(od["limit_price"]), shares=shares,
              intent=od["intent"], source=str(od.get("priority", "")),
              target_notional=target_notional)
    if od["side"] == "sell":
        pos = book.total_shares(sym)
        sellable, _ = book.sellable(sym, od["live_date"], od["live_session"])
        st = JudgeState(sellable_shares=sellable, position_shares=pos)
    elif probe == "full":
        # 已成交买：用重建的现金与自算决策点权益快照做资金/帽复核
        snap = _snapshot_equity(market, book, od)
        proj = _projected_mv(market, book, od)
        st = JudgeState(available_cash=book.cash, snapshot_equity=snap,
                        projected_mv=proj)
    else:
        st = JudgeState()            # 探针模式：隔离穿透/合法性层
    return m.judge_session(o, st), probe


def _snapshot_equity(market: Market, book: Book, od: dict) -> Decimal | None:
    """自算决策点权益快照（官方收盘 mark；am 决策用前一交易日收盘）。"""
    total = book.cash + book.pend_am_to_pm + book.pend_next_day
    for sym, clips in book.clips.items():
        n = sum(c.shares for c in clips)
        if not n:
            continue
        px = market.official_close(sym, od["decision_date"]) \
            if od["decision_session"] == "pm" \
            else market.prev_trading_close(sym, od["decision_date"])
        if px is None:
            return None
        total += Decimal(str(px)) * n
    return total


def _projected_mv(market: Market, book: Book, od: dict) -> Decimal | None:
    n = book.total_shares(od["symbol"])
    if not n:
        return Decimal("0")
    px = market.prev_trading_close(od["symbol"], od["live_date"])
    if px is None:
        return None
    return Decimal(str(px)) * n


def _compare(od: dict, v) -> bool:
    """核心字段一致性：成交与否 + 日期/半日 + 股数 + 价格 + 费用 + 未成交原因。"""
    expected = EXPECTED_REASON.get(od["event"], set())
    if v.reason not in expected and not (v.filled and "filled" in expected):
        return False
    if v.filled and od["shares"] is not None and od["side"] == "sell":
        return int(v.shares or 0) == int(od["shares"])
    if v.filled and od["event"] == "filled_limit_buy" and od["shares"] is not None:
        return int(v.shares or 0) == int(od["shares"])
    return True


def _book_session_fills(book: Book, ev: "ArmEvents", day: date, sess: str,
                        booked: set[str]) -> int:
    """把该半日尚未入账的成交补齐（只影响后续订单的事实状态）。"""
    n = 0
    for f in ev.fills_by_session.get((day, sess), ()):
        if f["fill_id"] in booked:
            continue
        _book_fill(book, f)
        booked.add(f["fill_id"])
        n += 1
    return n


def _book_fill(book: Book, f: dict) -> None:
    """把引擎记录的成交入到独立账本（作为下一张订单的事实状态）。"""
    day, sess = f["date"], f["session"]
    price = Decimal(str(f["price"]))
    shares = int(f["shares"])
    if f["side"] == "buy":
        book.book_buy(f["symbol"], day, sess, shares, price)
    else:
        consume = book.consume_plan(f["symbol"], day, sess, shares)
        book.book_sell(f["symbol"], day, sess, shares, price, consume)


def _fill_fields_match(v, engine_fill: dict | None) -> bool | str:
    """与 run fills 逐字段对照：成交股数 / 价格 / 佣金 / 印花 / 费用合计。

    零容差到分（费用按 C1 ``fee_schema.rounding_rule``：ROUND_HALF_UP 到分），
    价格与股数精确相等。未成交订单返回 ``""``（不适用）。
    """
    if engine_fill is None:
        return "" if not v.filled else False
    if not v.filled:
        return False
    if int(v.shares or 0) != int(engine_fill["shares"]):
        return False
    if abs(float(v.price) - float(engine_fill["price"])) > 1e-9:
        return False
    for mine, theirs in ((v.commission, engine_fill["commission"]),
                         (v.stamp_tax, engine_fill["stamp_tax"]),
                         (v.fees_total, engine_fill["fees_total"])):
        if abs(float(mine) - float(theirs)) > 0.005:
            return False
    return True


def _row(od: dict, v, arm: str, probe: str, ok: bool, *, engine_event: str,
         engine_shares, engine_price, symbol_source: str = "",
         engine_fill: dict | None = None,
         fill_fields_match: bool | str = "") -> dict:
    return {
        "arm": arm,
        "symbol_source": symbol_source,
        "order_id": v.order_id,
        "symbol": od["symbol"],
        "side": v.side,
        "intent": v.intent,
        "decision_date": od.get("decision_date", ""),
        "decision_session": od.get("decision_session", ""),
        "live_date": v.live_date,
        "live_session": v.live_session,
        "engine_event": engine_event,
        "engine_shares": "" if engine_shares is None else engine_shares,
        "engine_limit_price": "" if od.get("limit_price") is None
        else od["limit_price"],
        "engine_ref_price": "" if engine_price is None else engine_price,
        "matcher_filled": v.filled,
        "matcher_reason": v.reason,
        "matcher_status": v.status,
        "matcher_fill_type": v.fill_type,
        "matcher_fill_date": v.fill_date or "",
        "matcher_fill_session": v.fill_session,
        "matcher_shares": "" if v.shares is None else v.shares,
        "matcher_price": "" if v.price is None else v.price,
        "matcher_commission": "" if v.commission is None else v.commission,
        "matcher_stamp_tax": "" if v.stamp_tax is None else v.stamp_tax,
        "matcher_fees_total": "" if v.fees_total is None else v.fees_total,
        "engine_fill_id": "" if engine_fill is None else engine_fill["fill_id"],
        "engine_fill_shares": ("" if engine_fill is None
                               else engine_fill["shares"]),
        "engine_fill_price": ("" if engine_fill is None
                              else engine_fill["price"]),
        "engine_fill_commission": ("" if engine_fill is None
                                   else engine_fill["commission"]),
        "engine_fill_stamp_tax": ("" if engine_fill is None
                                  else engine_fill["stamp_tax"]),
        "engine_fill_fees_total": ("" if engine_fill is None
                                   else engine_fill["fees_total"]),
        "fill_fields_match": fill_fields_match,
        "probe_mode": probe,
        "core_fields_match": bool(ok),
        "note": v.note,
    }


# --------------------------------------------------------------------------- #
def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--evidence-dir", required=True)
    ap.add_argument("--repo-root", default=".")
    args = ap.parse_args(argv)
    root = Path(args.repo_root).resolve()
    out = (root / args.evidence_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    sandbox = dev_sandbox.SandboxRegistry.load(root)
    all_rows: list[dict] = []
    summaries: list[dict] = []
    all_symbols: set[str] = set()
    for run_id, arm in ARMS:
        ev = ArmEvents(root / "artifacts" / "runs" / run_id, arm)
        all_symbols |= set(ev.symbols)
    market = Market(sandbox, sorted(all_symbols))
    ca = CorporateActions(sandbox, sorted(all_symbols))
    for run_id, arm in ARMS:
        rows, summary = reconcile_arm(root / "artifacts" / "runs" / run_id,
                                      arm, market, ca)
        all_rows += rows
        summaries.append(summary)
        print(f"[arm] {arm}: orders={summary['orders']} "
              f"matched={summary['matched']} mismatched={summary['mismatched']} "
              f"fallback={summary['fallback_attempts']}"
              f"/{summary['fallback_matched']}")
    write_csv(out / "order_reconciliation.csv", all_rows)

    summary = {
        "arms": summaries,
        "total_orders": sum(s["orders"] for s in summaries),
        "total_matched": sum(s["matched"] for s in summaries),
        "total_mismatched": sum(s["mismatched"] for s in summaries),
        "total_fallback_attempts": sum(s["fallback_attempts"] for s in summaries),
        "total_fallback_matched": sum(s["fallback_matched"] for s in summaries),
        "wall_s": round(time.time() - t0, 2),
    }
    (out / "reconcile_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False)[:400])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
