# p2r12-event-veto run report

Frozen prereg: docs/research/exp-20260918-p2r12-event-veto-prereg.md; config: configs/experiments/p2r12-event-veto.json.

## verdicts (dev -> val one-shot)
| unit | dev | val |
|---|---|---|
| C01 | False | None |
| C02 | False | None |
| C03 | False | None |
| C04 | False | None |
| C05 | False | None |
| C06 | False | None |

## C01
- dev: {"n_matched": 1345, "mean_excess": -0.001350743359685978, "mean_excess10": 6.226137426852311e-06, "gate_primary": false, "gate_no_rebound": false, "gate_years": false, "pass": false}
- val: {"n_matched": 803, "mean_excess": 0.0033975200736768396, "mean_excess10": 0.008077279039430719, "gate_primary": false, "gate_no_rebound": false, "gate_years": false, "pass": false}

## C02
- dev: {"n_down": 168, "n_deep": 131, "n_first_negative": 1735, "verdict": "evidence_insufficient", "gate_primary": null, "gate_deep": null, "gate_years": null, "pass": false}
- val: {"n_down": 113, "n_deep": 72, "n_first_negative": 2833, "verdict": "evidence_insufficient", "gate_primary": null, "gate_deep": null, "gate_years": null, "pass": false}

## C03
- dev: {"n_matched": 34448, "q05_marked": -0.14934793741109537, "q05_ctrl": -0.14, "tail_gap": 0.009347937411095353, "mean_marked": -0.013067806037284689, "mean_ctrl": -0.015454812617536557, "mean_loss": 0.002387006580251868, "block_rate_marked": 0.02400929017273915, "block_rate_ctrl": 0.020001161170459823, "block_ratio": 1.200394815486964, "block_rate_marked_window": 0.06337639715488459, "block_rate_ctrl_window": 0.04813051555968416, "block_ratio_window": 1.316761235941776, "gate_tail": false, "gate_block": false, "gate_mean_cap": false, "pass": false}
- val: {"n_matched": 77385, "q05_marked": -0.11107132060677401, "q05_ctrl": -0.09652007722007716, "tail_gap": 0.014551243386696847, "mean_marked": 0.007780141911515846, "mean_ctrl": 0.007062618842711986, "mean_loss": 0.0007175230688038605, "block_rate_marked": 0.00856755185113394, "block_rate_ctrl": 0.00757252697551205, "block_ratio": 1.1313993174061434, "block_rate_marked_window": 0.03576920591845965, "block_rate_ctrl_window": 0.022898494540285586, "block_ratio_window": 1.5620767494356658, "gate_tail": false, "gate_block": false, "gate_mean_cap": true, "pass": false}

## C04
- dev: {"pass": false, "gp_mean_excess": 0.0007412378885354759, "gp_n": 1018, "asymmetry_secondary_ok": true}
- val: {"pass": false, "gp_mean_excess": -0.001221605327438493, "gp_n": 881, "asymmetry_secondary_ok": true}

## C05
- dev: {"gate_ratio": false, "gate_years": false, "secondary_mean_excess": -0.01929824455551245, "secondary_n": 600, "secondary_gate": true, "pass": false}
- val: {"gate_ratio": false, "gate_years": false, "secondary_mean_excess": -0.020909592394252698, "secondary_n": 456, "secondary_gate": true, "pass": false}

## C06
- dev: {"n_host": 737010, "n_vetoed": 86345, "cut_share": 0.11715580521295504, "mean_host": 0.00410116440325184, "mean_vetoed": -0.0029835612068056442, "mean_kept": 0.005041326595471205, "mean_loss": -0.007084725610057484, "q05_host": -0.0966257668711657, "q05_kept": -0.09305906063792488, "tail_gain": 0.03691257879480972, "mean_host_net": 0.002596414135314733, "mean_kept_net": 0.0035354014185210764, "mean_vetoed_net": -0.004479457781153576, "gate_mean_loss": true, "gate_tail_gain": false, "gate_cut_share": true, "pass": false}
- val: {"n_host": 1800129, "n_vetoed": 189394, "cut_share": 0.10521134874222902, "mean_host": 0.0012555936278070075, "mean_vetoed": 0.0029011581397126065, "mean_kept": 0.0010621042920889352, "mean_loss": 0.001645564511905599, "q05_host": -0.09514563106796121, "q05_kept": -0.09403669724770636, "tail_gain": 0.011655120763903078, "mean_host_net": -6.950738924594529e-05, "mean_kept_net": -0.0002650311718000571, "mean_vetoed_net": 0.0015933594380679995, "gate_mean_loss": false, "gate_tail_gain": false, "gate_cut_share": true, "pass": false}
  - per_year dev: [{"year": 2019, "n_host": 332402, "n_vetoed": 44596, "mean_loss": -0.012710582039930671, "tail_gain": 0.07856338772958267}, {"year": 2020, "n_host": 404608, "n_vetoed": 41749, "mean_loss": -0.001075114259763766, "tail_gain": 0.0049561798518432945}]
  - per_year val: [{"year": 2021, "n_host": 399997, "n_vetoed": 37959, "mean_loss": 0.0001838087813389429, "tail_gain": 0.009025758413902154}, {"year": 2022, "n_host": 483146, "n_vetoed": 49365, "mean_loss": -0.0016912553800899077, "tail_gain": 0.02281809482525986}, {"year": 2023, "n_host": 443517, "n_vetoed": 47115, "mean_loss": 0.0014787555306128995, "tail_gain": 0.017932896755529344}, {"year": 2024, "n_host": 473469, "n_vetoed": 54955, "mean_loss": 0.005762725463310211, "tail_gain": -0.0042624360320109005}]

## C07 (non-judging adjunct)
{"window_sessions": 10, "n_unlock_events": 7907, "n_c_de_events": 14265, "n_unlock_with_nearby_de": 297, "share_unlock_with_nearby_de": 0.03756165423042873, "n_de_with_nearby_unlock": 342, "share_de_with_nearby_unlock": 0.023974763406940065}

## assembly counts
{"daily": {"daily_rows": 9532019, "factor_rows": 10607881, "noncontiguous_symbols": 0, "banned_adj_rows_dropped": 1378, "stk_limit_rows": 8171212, "listing_rows": 15762653, "eligible_rows": 3962578}, "session_rows": 3962578, "session_dates": ["2015-01-30", "2024-12-31"], "c01": {"groups_passing_thresholds": 9401, "announced_at_or_after_float": 14, "out_of_calendar": 897, "activation_before_window_start": 0, "dedup_activation_duplicates": 583}, "c03": {"records": 109483, "records_out_of_calendar_or_empty": 2717}, "c02": {"rows_in_freeze": 39745, "chain_groups": 37228, "multi_version_chains": 2452, "downgrade_events": 887, "deep_events": 615, "first_negative_events": 14898, "down_dedup": 0, "firstneg_dedup": 17}, "c04": {"rows_in_freeze": 126160, "c_de_events": 14269, "gp_events": 6294}, "c05": {"cf_annual_keys": 88146, "bs_annual_keys": 83613, "joined_keys": 81825, "keys_pit_in_window": 51223, "keys_with_valid_accrual": 50642, "financial_excluded": 940, "industry_unavailable_excluded": 2511, "cohort_rows": 45095, "cohorts_with_session": 45095, "forecast_negative_rows": 16247, "forecast_coverage_start": "2018-09-03"}}