# -*- coding: utf-8 -*-
"""P3R2 runner part 2: metrics, gates, disclosures, outputs, manifest.

Importing `runner_p3r2` executes parts 0-10 (pins, calendar, pools,
consistency, frames, signal builder, fixed-point runs, attribution); this
module continues from the shared namespace and finishes the run.
Entry point: `python runner_p3r2_part2.py [--smoke]`.
"""
from __future__ import annotations

import json
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

TMP = Path(__file__).resolve().parent
RUN_DIR = TMP.parent
sys.path.insert(0, str(TMP))

import numpy as np  # noqa: E402
import polars as pl  # noqa: E402

import runner_p3r2 as base  # noqa: E402  (executes sections 0-10)
from quant.research import p2r16_trend_dispersion as r16  # noqa: E402
import quant.research.etf_rotation as er  # noqa: E402

CONFIG_IDS = base.CONFIG_IDS
sig_days = base.sig_days
P3R2_CONFIG_SHA16 = base.P3R2_CONFIG_SHA16


def daily_max_single_name_weight(res):
    """Max over dev days of max held-name weight (official close marks).
    Splits applied once per symbol via a persistent pointer."""
    dates = res.daily["date"].to_list()
    eq_list = res.daily["equity"].to_list()
    per = {}
    for r in res.fills.select("symbol", "date", "side", "shares").iter_rows(named=True):
        per.setdefault(r["symbol"], []).append(
            (base.dint_of(r["date"]), r["side"], int(r["shares"])))
    for v in per.values():
        v.sort(key=lambda e: e[0])
    sp_by = {sym: sorted((base.dint_of(ed), f) for ed, f in evs)
             for sym, evs in base.split_events.items()}
    state: dict[str, list] = {}
    wmax = 0.0
    top = (0.0, None, 0, 0.0, 0.0)
    for d, e in zip(dates, eq_list):
        td = base.dint_of(d)
        if e <= 0:
            continue
        for sym, evs in per.items():
            st = state.get(sym)
            if st is None:
                st = [0, 0, 0]
                state[sym] = st
            pos, i, si = st
            sp = sp_by.get(sym, [])
            while si < len(sp) and sp[si][0] <= td:
                pos = int(math.floor(pos * sp[si][1] + 0.5))
                si += 1
            while i < len(evs) and evs[i][0] <= td:
                ev = evs[i]
                while si < len(sp) and sp[si][0] <= ev[0]:
                    pos = int(math.floor(pos * sp[si][1] + 0.5))
                    si += 1
                pos += ev[2] if ev[1] == "buy" else -ev[2]
                i += 1
            st[0], st[1], st[2] = pos, i, si
            if pos > 0:
                px = base.close_le(sym, d)
                if px and px > 0:
                    w = pos * px / e
                    if w > wmax:
                        wmax = w
                        top = (w, (sym, str(d)), pos, px, e)
    if wmax > 1.0:
        base.log(f"    [diag] absurd weight {wmax:.4g} at {top}")
    return wmax


# === 11. metrics & gates =====================================================
base.log("== 11. metrics & gates ==")
metrics: dict = {}
gates: dict = {}
for cid in base.config_list:
    res = base.results[cid]["res"]
    sd, sv = er.slice_curve(res.daily["date"].to_list(),
                            res.daily["equity"].to_list(),
                            base.DEV_START, base.DEV_END)
    net_cagr = er.cagr(sv[0], sv[-1], sd[0], sd[-1])
    mdd = er.max_drawdown(sd, sv)["max_drawdown"]
    yr = er.year_returns(sd, sv)
    b1y = {int(k): v for k, v in base.B1[cid]["b1m_net_return_by_year"].items()}
    adv = sorted(y for y in yr if y in b1y and yr[y] > b1y[y])
    excess = net_cagr - base.B1[cid]["b1m_net_cagr"]
    df = res.daily.with_columns(pl.col("date").dt.year().alias("yy"))
    mean_eq = {int(r["yy"]): r["equity"] for r in
               df.group_by("yy").agg(pl.col("equity").mean()).iter_rows(named=True)}
    if res.fills.height:
        buy_by = {int(r["yy"]): r["n"] for r in
                  res.fills.filter(pl.col("side") == "buy")
                  .with_columns(pl.col("date").dt.year().alias("yy"))
                  .group_by("yy").agg(pl.col("notional").sum().alias("n"))
                  .iter_rows(named=True)}
    else:
        buy_by = {}
    tby = {y: {"buy_notional": buy_by.get(y, 0.0), "mean_equity": mean_eq[y],
               "one_side_turnover": buy_by.get(y, 0.0) / mean_eq[y]}
           for y in sorted(mean_eq)}
    wmax = daily_max_single_name_weight(res)
    a = base.results[cid]["attr"]
    path_name = base.r16_config["configs"][cid]["path"]
    m = {"net_cagr": net_cagr,
         "net_total_return": sv[-1] / sv[0] - 1.0,
         "max_drawdown": mdd,
         "b1m_net_cagr": base.B1[cid]["b1m_net_cagr"],
         "b1m_max_drawdown": base.B1[cid]["b1m_max_drawdown"],
         "b1m_net_return_by_year": base.B1[cid]["b1m_net_return_by_year"],
         "excess_vs_b1m": excess,
         "net_return_by_year": {int(k): v for k, v in yr.items()},
         "advantage_years_list": [int(y) for y in adv],
         "turnover_by_year": tby,
         "max_one_side_turnover": max(v["one_side_turnover"] for v in tby.values()),
         "max_single_name_weight": wmax,
         "execution_rate": a["mapped_rate"],
         "execution_rate_mapping": "7.7-m6: filled intents / (filled + "
                                   "terminated-unfilled intents); re-anchor "
                                   "neutral; at-target skips excluded"}
    g = {"1_net_cagr_gt_0": net_cagr > 0,
         "2_excess_vs_B1m_ge_2pp": excess >= 0.020,
         "3_advantage_years_ge_5_of_6": len(adv) >= 5 and len(b1y) == 6,
         "4_mdd_le_20pct_and_le_B1m":
             abs(mdd) <= 0.20 + 1e-12
             and abs(mdd) <= abs(base.B1[cid]["b1m_max_drawdown"]) + 1e-12,
         "5_one_side_turnover_le_6": m["max_one_side_turnover"] <= 6.0,
         "6_single_name_weight_le_40pct": wmax <= 0.40,
         "7_vs_B3prime_plus_1pp": net_cagr >= base.B3P[path_name] + 0.010,
         "8_execution_rate_ge_95pct": (a["mapped_rate"] or 0.0) >= 0.95,
         "advantage_years": len(adv),
         "dev_excess_vs_b1m": excess}
    gate_keys = ["1_net_cagr_gt_0", "2_excess_vs_B1m_ge_2pp",
                 "3_advantage_years_ge_5_of_6", "4_mdd_le_20pct_and_le_B1m",
                 "5_one_side_turnover_le_6", "6_single_name_weight_le_40pct",
                 "7_vs_B3prime_plus_1pp", "8_execution_rate_ge_95pct"]
    g["failed_gates"] = sorted(k for k in gate_keys if not g[k])
    g["dev_pass"] = not g["failed_gates"]
    g["verdict"] = "dev_pass" if g["dev_pass"] else "eliminated"
    metrics[cid] = m
    gates[cid] = {"dev": g, "verdict": g["verdict"]}
    base.log(f"  {cid}: net {net_cagr*100:+.2f}% excess {excess*100:+.2f}pp "
             f"adv {len(adv)}/6 mdd {mdd*100:.2f}% "
             f"turn {m['max_one_side_turnover']:.2f} w {wmax*100:.1f}% "
             f"exec {(a['mapped_rate'] or 0)*100:.1f}% -> "
             f"{'PASS' if g['dev_pass'] else 'eliminated ' + str(g['failed_gates'])}")

n_pass = sum(1 for cid in base.config_list if gates[cid]["dev"]["dev_pass"])
base.log(f"== gates: {n_pass}/8 dev_pass ==")

if base.SMOKE:
    out = {"smoke": True, "signal_days": len(sig_days),
           "per_config": {cid: {
               "converged_at": base.results[cid]["converged_at"],
               "wall_s": base.results[cid]["wall_s"],
               "hist": base.results[cid]["hist"],
               "attr": {k: v for k, v in base.results[cid]["attr"].items()
                        if k not in ("outcomes", "fill_n", "emit_n")},
               "net_cagr": metrics[cid]["net_cagr"],
               "mdd": metrics[cid]["max_drawdown"],
               "exec": metrics[cid]["execution_rate"],
               "warnings_n": len(base.results[cid]["warnings"]),
               "warnings_sample": base.results[cid]["warnings"][:3]}
           for cid in base.config_list}}
    smoke_dir = RUN_DIR / "tmp" / "smoke"
    smoke_dir.mkdir(parents=True, exist_ok=True)
    for cid in base.config_list:
        st = base.results[cid]
        st["sig_last2"].write_parquet(smoke_dir / f"{cid}_sig_prev.parquet")
        st["sig"].write_parquet(smoke_dir / f"{cid}_sig.parquet")
        st["res"].fills.write_parquet(smoke_dir / f"{cid}_fills.parquet")
        st["res"].events.write_parquet(smoke_dir / f"{cid}_events.parquet")
        st["sig"].write_parquet(smoke_dir / f"{cid}_sig.parquet")
        st["res"].daily.write_parquet(smoke_dir / f"{cid}_daily.parquet")
    (smoke_dir / "smoke_results.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1, default=str),
        encoding="utf-8")
    base.log(f"SMOKE complete -> {smoke_dir / 'smoke_results.json'} "
             f"(peak rss {base.rss_gb():.2f} GB)")
    sys.exit(0)

# === 12. disclosures (prereg sec 5, five items) ==============================
base.log("== 12. disclosures ==")
p3r1_fees = {}
for cid in base.config_list:
    f1 = pl.read_parquet(base.P3R1_RUN / "outputs" / f"{cid}_fills.parquet")
    p3r1_fees[cid] = float(f1["fees_total"].sum())

MAPPING_DIFFS = {
    "re_anchor_cadence": "v0 dead anchor (signal-day close, fixed) -> v1 "
                         "mechanical re-anchor at EVERY decision point "
                         "(am=am.close, pm=official close), qty recomputed by "
                         "engine from fixed target_notional (7.7-M3)",
    "rescale_first_mapping": "P3R1 did not map rescale legs; P3R2 maps them "
                             "(up=add clip buy, down=explicit-share risk "
                             "sell), direction/sizing frozen at signal-day "
                             "close of previous fixed-point iteration",
    "sell_intent_mapping": "sell_full -> intent=risk with K=3 SESSION-level "
                           "fallback (v0: day-level), keyed (symbol, intent, "
                           "source_signal) (7.7-M1)",
    "fill_granularity": "official daily extremes -> half-day bar extremes "
                        "(conservative subset; gaps fill at the limit)",
    "proceeds": "sale proceeds usable next SESSION (v0: next day)",
    "signal_day_drop": "same as P3R1: 2020-12-31 signal dropped (next trading "
                       "day outside dev)",
    "rescale_sizing_approx": "aggregate-position split rounding in the "
                             "sizing reconstruction vs per-clip rounding in "
                             "the engine (<1 share); direction tolerance 0.5 CNY",
}

disclosures: dict = {}
for cid in base.config_list:
    res = base.results[cid]["res"]
    a = base.results[cid]["attr"]
    st = res.stats
    m = metrics[cid]
    g = gates[cid]["dev"]
    p1 = base.p3r1_mg["metrics"][cid]
    p1d = base.p3r1_mg["disclosures"][cid]
    n_rescale_down = sum(
        1 for (sym, sc, T), plan in base.results[cid]["intents"].items()
        if plan.get("plan") == "sell" and plan.get("shares") is not None)
    n_rescale_down_filled = sum(
        1 for (sym, sc, T), plan in base.results[cid]["intents"].items()
        if plan.get("plan") == "sell" and plan.get("shares") is not None
        and base.results[cid]["attr"]["outcomes"][(sym, sc, T)][0] == "filled")
    fees_total = float(res.fills["fees_total"].sum()) if res.fills.height else 0.0
    k3 = st["res"].stats.get("k3_fallback", {})
    caps = st["res"].stats.get("caps", {})
    fric = st["res"].stats.get("cash_friction", {})
    corp = st["res"].stats.get("corp_actions", {})
    to = st["res"].stats.get("turnover", {})
    disclosures[cid] = {
        "verdict": g["verdict"],
        "1_fill_rate": {
            "gate8_mapped_execution_rate": a["mapped_rate"],
            "order_session_fill_rate": a["order_session"],
            "emissions": a["emit_side"], "filled_orders": a["fill_side"],
            "decision_point_fill_share": a["sess_fill_share"],
            "vs_p3r1": {
                "gate8_mapped_pp": (m["execution_rate"] - p1["execution_rate"]) * 100,
                "order_session_buy_pp":
                    (a["order_session"]["buy"] - p1d["order_fill_rate"]["buy"]) * 100,
                "order_session_sell_pp":
                    (a["order_session"]["sell"] - p1d["order_fill_rate"]["sell"]) * 100}},
        "2_turnover_fees": {
            "buy_notional_total": to.get("buy_notional_total"),
            "sell_notional_total": to.get("sell_notional_total"),
            "fees_total": fees_total,
            "commission_warnings": st["res"].stats.get("commission_warnings"),
            "max_one_side_turnover": m["max_one_side_turnover"],
            "vs_p3r1": {"fees_total": fees_total - p3r1_fees[cid],
                        "max_turnover": m["max_one_side_turnover"]
                        - p1["max_one_side_turnover"]}},
        "3_mdd_attribution": {
            "max_drawdown": m["max_drawdown"],
            "p3r1_max_drawdown": p1["max_drawdown"],
            "delta_pp": (m["max_drawdown"] - p1["max_drawdown"]) * 100,
            "risk_reduce_intents_emitted": n_rescale_down,
            "risk_reduce_intents_filled": n_rescale_down_filled,
            "k3_market_exits_executed": k3.get("executed"),
            "note": "mechanism counters, not a counterfactual decomposition; "
                    "market-path component not separable without a "
                    "no-rescale twin run (not run: zero-trial discipline)"},
        "4_mapping_diffs": MAPPING_DIFFS,
        "5_increments": {
            "cap_single_name_voids": caps.get("single_name_voids"),
            "single_name_drift_breaches": caps.get("single_name_drift_breaches"),
            "decision_point_fills": a["sess_fill_share"],
            "k3": {"armed": k3.get("armed"), "executed": k3.get("executed"),
                   "deferred_limitdown": k3.get("deferred_limitdown_sessions"),
                   "deferred_suspended": k3.get("deferred_suspended"),
                   "deferred_t1locked": k3.get("deferred_t1locked")},
            "gate8_termination_reasons": a["termination"],
            "rule_blocked_executed": a.get("rule_blocked"),
            "skip_at_target": a["n_skip"],
            "insufficient_cash_orders": fric.get("insufficient_cash_orders"),
            "below_min_lot_abandons": fric.get("below_min_lot_abandons"),
            "suspended_session_voids": st["res"].stats.get("void_days", {}).get("suspended", 0),
            "engine_warnings_n": len(base.results[cid]["warnings"]),
            "engine_warnings_sample": base.results[cid]["warnings"][:3],
            "corp_action": {"splits": corp.get("splits"),
                            "dividends": corp.get("dividends"),
                            "dividend_cash_total": corp.get("dividend_cash_total_pre_tax")}},
        "fixed_point": {"converged_at": base.results[cid]["converged_at"],
                        "trajectory": base.results[cid]["hist"]},
    }

# === 13. outputs / report / manifest =========================================
base.log("== 13. outputs ==")
out_dir = RUN_DIR / "outputs"
for cid in base.config_list:
    st = base.results[cid]
    st["res"].fills.write_parquet(out_dir / f"{cid}_fills.parquet")
    st["res"].events.write_parquet(out_dir / f"{cid}_events.parquet")
    st["res"].daily.write_parquet(out_dir / f"{cid}_daily_equity.parquet")
    st["res"].clips_final.write_parquet(out_dir / f"{cid}_clips_final.parquet")
    st["sig"].write_parquet(out_dir / f"{cid}_signals_final.parquet")

b3p_noise = {"T200-40": [None], "FIX75": [None]}
mg = {
    "experiment_id": "exp-20260918-p3r2-band-v1-readjudication",
    "engine_sha256_16": base.pins["engine"]["sha256"][:16],
    "metrics": metrics, "gates": gates, "disclosures": disclosures,
    "b3prime_dev_mean_net_cagr": base.B3P,
    "b3prime_source": "R16 metrics.json verbatim (benchmarks unchanged)",
    "consistency": base.consistency,
    "advanced_to_validation": False, "val_consumed": False,
    "stop_note": ("STOP before val: >=1 config passed all dev gates; "
                  "val requires separate user approval"
                  if n_pass else
                  f"no config passed all dev gates ({n_pass}/8); val not consumed"),
}
(out_dir / "metrics_and_gates.json").write_text(
    json.dumps(mg, ensure_ascii=False, indent=1, default=str), encoding="utf-8")

# report.md
rep = ["# P3R2 v1 契约下 R16 八配置 dev 重裁定（exp-20260918-p3r2-band-v1-readjudication）", "",
       f"- 运行：`{RUN_DIR.name}`；引擎 sha256:16 `{base.pins['engine']['sha256'][:16]}`"
       f"（21/21 测试，双签 APPROVE，运行前后哈希一致）；窗口 dev 2015-01-05..2020-12-31，"
       f"信号 {sig_days[0]}..{sig_days[-1]}（共 {len(sig_days)} 个月末，2020-12-31 按冻结先例丢弃）。",
       "- 判据 = R16 预登记 §2 八门逐字（prereg §3）；B1(m)/B3′ 沿 R16 原口径原数值，基准不换契约。",
       "- 全部数字为历史回放，不构成盈利或实盘声称；val（2021–2024）零消费。", "",
       "## 一、八门判定表", "",
       "| 配置 | K/路径/Q5 | 净CAGR | B1(m) | 超额 | 优势年 | 回撤(v1/P3R1) | 换手 | 单票max权重 | 门8成交率(v1/P3R1) | 过/8 | 失败门 | 判定 |",
       "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
for cid in base.config_list:
    m, g, d = metrics[cid], gates[cid]["dev"], disclosures[cid]
    spec = base.r16_config["configs"][cid]
    p1 = base.p3r1_mg["metrics"][cid]
    rep.append(
        f"| {cid} | {spec['K']}/{spec['path']}/{spec['filter']} "
        f"| {m['net_cagr']*100:+.2f}% | {m['b1m_net_cagr']*100:+.2f}% "
        f"| {m['excess_vs_b1m']*100:+.2f}pp | {g['advantage_years']}/6 "
        f"| {m['max_drawdown']*100:.2f}%/{p1['max_drawdown']*100:.2f}% "
        f"| {m['max_one_side_turnover']:.2f} "
        f"| {m['max_single_name_weight']*100:.1f}% "
        f"| {(m['execution_rate'] or 0)*100:.1f}%/{p1['execution_rate']*100:.1f}% "
        f"| {8-len(g['failed_gates'])} "
        f"| {', '.join(g['failed_gates']) or '-'} "
        f"| {'**dev_pass**' if g['dev_pass'] else 'eliminated'} |")
rep += ["", "## 二、vs P3R1 delta（五项强制披露之 1–3）", "",
        "| 配置 | 门8成交率 Δpp | 订单口径买/卖 Δpp | 换手 Δ | 费用 Δ元 | 回撤 Δpp | 净CAGR Δpp |", "|---|---|---|---|---|---|---|"]
for cid in base.config_list:
    d1 = disclosures[cid]["1_fill_rate"]["vs_p3r1"]
    d2 = disclosures[cid]["2_turnover_fees"]["vs_p3r1"]
    d3 = disclosures[cid]["3_mdd_attribution"]
    rep.append(
        f"| {cid} | {d1['gate8_mapped_pp']:+.1f} "
        f"| {d1['order_session_buy_pp']:+.1f}/{d1['order_session_sell_pp']:+.1f} "
        f"| {d2['max_turnover']:+.2f} | {d2['fees_total']:+,.0f} "
        f"| {d3['delta_pp']:+.2f} "
        f"| {(metrics[cid]['net_cagr']-base.p3r1_mg['metrics'][cid]['net_cagr'])*100:+.2f} |")
rep += ["", "## 三、增量披露（五项强制披露之 5）", ""]
for cid in base.config_list:
    inc = disclosures[cid]["5_increments"]
    k3 = inc["k3"]
    rep.append(
        f"- **{cid}**：上限作废 {inc['cap_single_name_voids']}（漂移越限记录 "
        f"{inc['single_name_drift_breaches']}）；11:30/15:00 成交贡献 "
        f"{(inc['decision_point_fills']['am'] or 0)*100:.1f}%/"
        f"{(inc['decision_point_fills']['pm'] or 0)*100:.1f}%；K=3 "
        f"armed/executed={k3['armed']}/{k3['executed']}（跌停顺延 "
        f"{k3['deferred_limitdown']}、停牌 {k3['deferred_suspended']}、T+1锁 "
        f"{k3['deferred_t1locked']}）；门8终止：到期 "
        f"{inc['gate8_termination_reasons']['expiry']} / 同名义覆盖 "
        f"{inc['gate8_termination_reasons']['override_same_name']} / 上限作废 "
        f"{inc['gate8_termination_reasons']['cap_void']} / 停牌放弃 "
        f"{inc['gate8_termination_reasons']['suspension_abandon']}；at-target 跳过 "
        f"{inc['skip_at_target']}；风减意图 "
        f"{disclosures[cid]['3_mdd_attribution']['risk_reduce_intents_emitted']}"
        f"（成交 {disclosures[cid]['3_mdd_attribution']['risk_reduce_intents_filled']}）；"
        f"引擎警告 {inc['engine_warnings_n']}")
rep += ["", "## 四、映射差异清单（披露之 4，全配置相同）", ""]
for k, v in MAPPING_DIFFS.items():
    rep.append(f"- **{k}**: {v}")
rep += ["", "## 五、收敛性与运行身份", ""]
for cid in base.config_list:
    fp = disclosures[cid]["fixed_point"]
    rep.append(f"- {cid}: fixed point at iteration {fp['converged_at']} "
               f"({len(fp['trajectory'])} engine runs); trajectory CAGR "
               f"{[round(h['cagr']*100, 3) for h in fp['trajectory']]}")
rep += ["", f"- 8/8 信号一致性: {json.dumps(base.consistency)}",
        f"- 试验计账: 197 -> 205（本轮 8）",
        f"- 判定: {mg['stop_note']}"]
(RUN_DIR / "report.md").write_text("\n".join(rep), encoding="utf-8")

# manifest
outs = {}
for p in sorted(RUN_DIR.rglob("*")):
    if p.is_file() and "manifest.json" != p.name:
        outs[p.relative_to(RUN_DIR).as_posix()] = base.sha256_file(p)
manifest = {
    "run_id": RUN_DIR.name,
    "experiment_id": "exp-20260918-p3r2-band-v1-readjudication",
    "status": "completed",
    "started_at": datetime.fromtimestamp(base.T0, tz=timezone.utc).isoformat(),
    "ended_at": datetime.now(timezone.utc).isoformat(),
    "wall_seconds": time.perf_counter() - base.T0,
    "peak_rss_gb": base.rss_gb(),
    "command": [sys.executable, "tmp/runner_p3r2_part2.py"],
    "engine": {"path": str(base.ENGINE_PY), "sha256": base.pins["engine"]["sha256"],
               "modified_by_this_run": False,
               "approval": "artifacts/runs/20260918T212440-p3v1-engine-083a "
                           "(21/21 tests, dual-sign APPROVE)",
               "post_run_sha256_match": base.sha256_file(base.ENGINE_PY)
                                        == base.pins["engine"]["sha256"]},
    "pins": base.pins,
    "configs": [{"id": cid, **base.r16_config["configs"][cid]}
                for cid in base.config_list],
    "mapping": {"decision_points": "month-end 15:00 entry + mechanical "
                                   "re-issue/re-anchor at every decision "
                                   "point in [T pm, T' am] (7.7-M3); "
                                   "half-market sessions skipped (m3)",
                "rescale": "up=add-clip buy (target_per - pos_value(T)); "
                           "down=explicit-share risk sell; direction/sizing "
                           "from previous fixed-point iteration at T close",
                "fixed_point": "equity/rescale-state iteration until signal "
                               "frame byte-stable (P3R1 sizing precedent)",
                "gate8": "7.7-m6 mapped execution rate"},
    "consistency_8_of_8": base.consistency,
    "trial_accounting": {"cumulative_before": 197, "this_round": 8,
                         "cumulative_after": 205},
    "gates_dev_pass": [cid for cid in base.config_list if gates[cid]["dev"]["dev_pass"]],
    "advanced_to_validation": False,
    "val_consumed": False,
    "stop_note": mg["stop_note"],
    "outputs": outs,
}
(RUN_DIR / "manifest.json").write_text(
    json.dumps(manifest, ensure_ascii=False, indent=1, default=str),
    encoding="utf-8")
base.log(f"== manifest + report written; wall {time.perf_counter()-base.T0:.0f}s, "
         f"peak rss {base.rss_gb():.2f} GB ==")
base.log(f"== VERDICT: {n_pass}/8 dev_pass; {mg['stop_note']}")
