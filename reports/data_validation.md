# Data validation (T1-T14)

| Test | Check | Result | Key numbers |
|---|---|---|---|
| T1 | schema & keys | PASS | `{"problems": []}` |
| T2 | referential integrity | PASS | `{"bad_sender": 0, "bad_receiver": 0, "labels_match": true, "bad_event_wallet": 0, "bad_complaint_wallet": 0, "bad_home_agent": 0}` |
| T3 | balance conservation | PASS | `{"row_errors": 0, "chain_breaks": 0, "negative_balances": 0, "wallets": 12438}` |
| T4 | KYC limits | PASS | `{"violations": {"per_txn": 0, "daily_amount": 0, "daily_count": 0, "monthly_amount": 0}, "rejected_attempts": 2205}` |
| T5 | temporal realism | PASS | `{"night_share_00_06": 0.053, "peak_hour": 20, "eid_p2p_vs_median_day": 1.96, "salary_on_days_1_10": true, "friday_p2p_vs_weekday": 1.148, "normal_cash_night_share": 0.0005}` |
| T6 | volume & mix | PASS | `{"rows": 683148, "target": 600000, "ratio": 1.139, "out_of_band": {}, "failure_rate": 0.0426}` |
| T7 | amount realism | PASS | `{"p2p_round100_share": 0.535, "p2p_median": 894.0, "p2p_p99_over_median": 14.1, "recharge_amounts_valid": true, "payment_round100_share": 0.01}` |
| T8 | fraud prevalence & spread | PASS | `{"fraud_share": 0.00536, "fraud_rows": 3664, "missing_scenario_split": [], "rogue_agents": 9, "rogue_episode_splits": ["test", "train", "val"]}` |
| T9 | label consistency | PASS | `{"fraud_rows_missing_meta": 0, "nonfraud_with_scenario": 0, "cases": 593, "empty_cases": 7, "nonempty_share": 0.988, "orphan_case_ids": 0}` |
| T10 | scenario signatures | PASS | `{"S2_new_collector_age_days_max": 2.91, "S2_min_unique_victims": 8, "S3_median_hop_delay_min": 13.3, "S6_swap_before_drain_share": 1.0, "S1_remote_access_share": 0.102, "S1_drain_on_new_device_share": 1.0, "S7_send_on_own_device_share": 0.963, "S8_starts_wi...` |
| T11 | anti-shortcut | PASS | `{"aged_mule_share": 0.25, "fraud_night_share": 0.116, "normal_night_share": 0.047, "legit_new_wallets": 765, "legit_device_changes": 2042, "legit_sim_swaps": 91, "benign_fanin_wallet_days_ge8": 1485}` |
| T12 | split integrity | PASS | `{"split_mismatch": 0, "contiguous": true, "planted_keys_in_test": true, "cases_spanning_3_splits": 0, "fraud_rows_per_split": {"train": 2153, "val": 777, "test": 734}, "rows_per_split": {"train": 466451, "val": 109634, "test": 107063}}` |
| T13 | planted scenarios | PASS | `{"SC-01_key_success": true, "SC-02_key_success": true, "SC-03_key_success": true, "SC-04_key_success": true, "SC-05_key_success": true, "SC-07_key_success": true, "SC-08_key_success": true, "SB-01_key_success": true, "SB-02_key_success": true, "SB-03_key_su...` |
| T14 | reproducibility | PASS | `{"seed42_run1": "b8f42d16a7ea436f", "seed42_run2": "b8f42d16a7ea436f", "seed43": "e1aa63fdd17f6162"}` |

Full details: `reports/data_validation.json`.