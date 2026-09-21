# P2-R10 half-day survey (mode=full)

- verdict: **REGISTER_CANDIDATES**; candidates: ['F03', 'F06', 'F09', 'F11']
- panel: {"halfday_rows_total": 9440361, "symbols_total": 5324, "baostock_daily_1999_2024_rows": 16344349, "after_suspended_st": 8984194, "after_new_listing_120": 8654270, "after_boards": 8236096, "after_missing_keys": 8236096, "after_t1_outlier_021": 8235983, "symbols_filtered": 4703, "days_filtered": 2431, "t2_non_null": 8231280, "f8_non_null": 8217174, "f7_non_null": 8235983}
- control F12 dev IC: 0.43429924066937975

| factor | dir | dev IC | NW t | ann. gross D10-D1 | month share | buyable ann. | buyable share | IC gate | decile gate | incr gate | net ann. ref |
|---|---|---|---|---|---|---|---|---|---|---|---|
| F01 | -1 | -0.0627 | -16.4619 | 0.4885 | 0.8889 | 0.4383 | 0.8472 | PASS | PASS | - | 0.4879 |
| F02 | -1 | -0.0627 | -16.4619 | 0.4885 | 0.8889 | 0.4383 | 0.8472 | PASS | PASS | - | 0.4879 |
| F03 | -1 | -0.0618 | -16.3680 | 0.4961 | 0.9306 | 0.4401 | 0.8472 | PASS | PASS | n/a | 0.4954 |
| F04 | -1 | -0.0099 | -3.9439 | 0.2918 | 0.9306 | 0.2083 | 0.8750 | - | PASS | n/a | 0.2915 |
| F05 | +1 | 0.0158 | 7.3446 | 0.1681 | 0.8056 | 0.2060 | 0.8750 | - | PASS | n/a | 0.1679 |
| F06 | -1 | -0.0430 | -12.4778 | 0.2226 | 0.6667 | 0.1488 | 0.6389 | PASS | PASS | n/a | 0.2223 |
| F07 | -1 | -0.0161 | -5.8438 | 0.1060 | 0.6944 | 0.0069 | 0.5833 | - | PASS | n/a | 0.1058 |
| F08 | +1 | 0.0131 | 5.4613 | 0.0857 | 0.6389 | 0.0491 | 0.6111 | - | PASS | n/a | 0.0856 |
| F09 | -1 | -0.0222 | -9.9126 | 0.2498 | 0.8611 | 0.0971 | 0.6389 | PASS | PASS | n/a | 0.2495 |
| F10 | -1 | -0.0505 | -17.3471 | 0.3831 | 0.9306 | 0.3620 | 0.9306 | PASS | PASS | - | 0.3826 |
| F11 | -1 | -0.0362 | -12.4306 | 0.3794 | 0.8750 | 0.4071 | 0.9028 | PASS | PASS | n/a | 0.3789 |
| F12 (CONTROL) | +1 | 0.4343 | 109.4605 | 5.6163 | 1.0000 | 6.0749 | 1.0000 | PASS | PASS | n/a (control) | 5.6093 |

- thresholds: {"ic_abs_mean": 0.02, "ic_nw_t": 3.0, "decile_annualized_gross": 0.04, "decile_month_share": 0.6, "increment_ratio_vs_F12": 1.3}
- yearly IC (descriptive 2021-2024, no gates): see metrics.json factor_results[*].yearly_ic
- timings: {"panel_build_s": 7.464189599995734, "factor_evaluation_s": 37.45466529999976, "evidence_write_s": 28.989774400019087, "total_s": 74.60344330000225}
- trial count: {"prior_cumulative": 139, "this_round_factors": 12, "cumulative_after": 151}
- T2 descriptive: {"mean": -0.001040671872350148, "std": 0.02418539954952349, "n_non_null": 8231280, "note": "overnight + next-morning return; disclosed only, no gate"}
