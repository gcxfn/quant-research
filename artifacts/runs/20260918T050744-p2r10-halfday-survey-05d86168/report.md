# P2-R10 half-day survey (mode=smoke - SMOKE)

- verdict: **REGISTER_CANDIDATES**; candidates: ['F03', 'F07', 'F08']
- panel: {"halfday_rows_total": 9440361, "symbols_total": 5324, "baostock_daily_1999_2024_rows": 16344349, "after_suspended_st": 8984194, "after_new_listing_120": 8654270, "after_boards": 8236096, "after_missing_keys": 8236096, "after_smoke_window": 126600, "after_t1_outlier_021": 126600, "symbols_filtered": 2435, "days_filtered": 57, "t2_non_null": 124165, "f8_non_null": 116904, "f7_non_null": 126600}
- control F12 dev IC: 0.43183821145314505

| factor | dir | dev IC | NW t | ann. gross D10-D1 | month share | buyable ann. | buyable share | IC gate | decile gate | incr gate | net ann. ref |
|---|---|---|---|---|---|---|---|---|---|---|---|
| F01 | -1 | -0.0749 | -5.0113 | 0.5440 | 1.0000 | 0.4186 | 1.0000 | PASS | PASS | - | 0.5433 |
| F02 | -1 | -0.0749 | -5.0113 | 0.5440 | 1.0000 | 0.4186 | 1.0000 | PASS | PASS | - | 0.5433 |
| F03 | -1 | -0.0734 | -4.9253 | 0.5621 | 1.0000 | 0.4529 | 1.0000 | PASS | PASS | PASS | 0.5614 |
| F04 | -1 | -0.0151 | -1.4605 | 0.4165 | 1.0000 | 0.2973 | 1.0000 | - | PASS | PASS | 0.4160 |
| F05 | +1 | 0.0099 | 0.9403 | 0.0922 | 0.6667 | 0.1740 | 1.0000 | - | PASS | PASS | 0.0921 |
| F06 | -1 | -0.0237 | -1.7371 | -0.0665 | 0.6667 | -0.1772 | 0.6667 | - | - | PASS | -0.0664 |
| F07 | -1 | -0.0346 | -3.2284 | 0.3608 | 1.0000 | 0.2922 | 1.0000 | PASS | PASS | PASS | 0.3603 |
| F08 | +1 | 0.0331 | 3.3964 | 0.2781 | 1.0000 | 0.2244 | 1.0000 | PASS | PASS | PASS | 0.2778 |
| F09 | -1 | -0.0316 | -3.2199 | 0.0120 | 0.3333 | -0.2151 | 0.6667 | PASS | - | PASS | 0.0120 |
| F10 | -1 | -0.0351 | -4.0831 | 0.2195 | 1.0000 | 0.1552 | 1.0000 | PASS | PASS | - | 0.2193 |
| F11 | -1 | -0.0333 | -2.7262 | 0.3365 | 1.0000 | 0.3252 | 1.0000 | - | PASS | PASS | 0.3361 |
| F12 (CONTROL) | +1 | 0.4318 | 29.2772 | 6.0467 | 1.0000 | 6.7232 | 1.0000 | PASS | PASS | PASS | 6.0392 |

- thresholds: {"ic_abs_mean": 0.02, "ic_nw_t": 3.0, "decile_annualized_gross": 0.04, "decile_month_share": 0.6, "increment_ratio_vs_F12": 1.3}
- yearly IC (descriptive 2021-2024, no gates): see metrics.json factor_results[*].yearly_ic
- timings: {"panel_build_s": 5.974591499980306, "factor_evaluation_s": 1.3498770000005607, "evidence_write_s": 0.7394275999977253, "total_s": 8.951205600023968}
- trial count: {"prior_cumulative": 139, "this_round_factors": 12, "cumulative_after": 151}
- T2 descriptive: {"mean": 0.0027365084466723848, "std": 0.02181285080769015, "n_non_null": 124165, "note": "overnight + next-morning return; disclosed only, no gate"}
