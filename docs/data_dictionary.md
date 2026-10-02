# Data dictionary

All files are written by `python -m src.datagen.generate` to `data/generated/` (Parquet; add `--csv` for CSV).
Timestamps are naive local time (Asia/Dhaka), simulation day 1 = `world.start_date`. Every identifier is
synthetic: wallets `W0000001…`, agents `A00001…`, merchants `M00001…`, billers `B001…`, external
counterparties `X_EMPLOYER / X_REMIT / X_BANK / X_CARD`, MSISDNs `010xxxxxxxx` (010 is not an allocated
Bangladeshi operator prefix).

## Model inputs (what a real MFS would see)

### transactions (≈680k rows at full scale)
| column | meaning |
|---|---|
| txn_id | `T00000000…`, in time order |
| ts | timestamp |
| txn_type | SEND_MONEY, CASH_OUT, CASH_IN, PAYMENT, BILL_PAY, MOBILE_RECHARGE, ADD_MONEY, SALARY, REMITTANCE_IN, FLOAT_TOPUP |
| sender_id / sender_type | id and kind: C customer, A agent, M merchant, B biller, X external |
| receiver_id / receiver_type | same |
| amount, fee | Tk; cash-out fee 1.85%, send-money fee Tk 5 above Tk 25,000 (config) |
| status, fail_reason | SUCCESS / FAILED (INSUFFICIENT_BALANCE, LIMIT_EXCEEDED). Failed attempts are kept: fraudsters probe limits |
| sender_bal_before/after, receiver_bal_before/after | ledger balances (NaN for externals); chain exactly per wallet (validation T3) |
| device_id | `DV…` customer/gang phone, `AT…` agent terminal, empty for system credits |
| channel | APP, USSD, AGENT (cash-in by agent), SYSTEM |
| area_id | where it happened (`DHK-01` …) |

### account_events
SIGNUP, DEVICE_CHANGE (login from a new phone), SIM_SWAP, PIN_RESET with `ts, wallet_id, device_id, area_id,
channel`. Both legit (phone upgrades, lost SIMs) and fraud events (takeover logins). `case_id` is ground truth
and is never a feature.

### complaints (16268 helpline)
`ts, complainant_id, reported_wallet_id, category (FRAUD | WRONG_SEND), related_txn_id`. Filed with a
realistic delay after the scam (hours to days); features only use complaints already filed.

### customers / agents / merchants / billers
Customers: `wallet_id, msisdn, signup_ts, kyc_level (KYC1/KYC2), channel, segment, gender, age_band,
division, area_id, urban_rural, home_agent_id`. **Gender, age band, division, urban/rural and segment are
used only for the fairness audit, never as model inputs.** Agents: `agent_id, area_id, division,
urban_rural, onboard_ts, terminal_device_id`.

## Ground truth (evaluation only)

| file | contents |
|---|---|
| labels | one row per transaction: `is_fraud, scenario (S1…S8 / NONE), case_id, fraud_role, split` |
| cases | one row per scam case: scenario, ring, start, split, variant, victims, wallets, parent case (S3 chains), harvested agent |
| wallet_truth | wallets with a role: victim, mule (+aged), collector, fake_seller, scam_recipient, card_fraud_wallet, recruited |
| agent_truth | rogue agents with episode day ranges; register-harvested agents |
| planted_scenarios.json | SC-01…SC-08, SB-01…SB-05: key transaction id, wallets, expected / acceptable band |
| generation_report.json | counts, mix, timings |

`fraud_role` values: `takeover_drain, victim_payment, buyer_payment, coerced_send, card_add_money` (money
leaving a victim: the transactions Prohori warns about) and `mule_hop, mule_cashout, collector_cashout,
recipient_cashout, seller_cashout, cashout` (the laundering side).

## Features (`data/features/features.parquet`)
73 model features in 9 groups (see `src/features/spec.py`): transaction, behaviour, device_session, flow,
counterparty, agent, complaints, graph. Built by `python -m src.features.build` with the streaming store
(features from the past only, verified by `tests/test_features.py::test_no_future_leakage`).
