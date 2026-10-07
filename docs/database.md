# Database documentation

This prototype has **no relational or document database**. It uses flat files (Parquet/JSON) for synthetic data
and trained artifacts, plus an in-memory Python object for live serving. That is accurate for a hackathon prototype
and is stated plainly below. The second half of this document is a **proposed production schema** — the concrete
answer to the Phase 1 feedback "no deployment / data-store consideration" (Scalability & integration, 5.67/10) —
and is clearly marked as a design target, not something this repository implements.

## 1. What exists today (current state)

### 1.1 Synthetic entity tables — `data/generated/` (Parquet)
Written once by `python -m src.datagen.generate`, read-only afterward. Full column-level reference:
[`docs/data_dictionary.md`](data_dictionary.md). Summary:

| Table | Rows (full scale) | Role |
|---|---|---|
| `transactions` | ≈680,000 | the ledger: every SEND_MONEY, CASH_OUT, CASH_IN, PAYMENT, BILL_PAY, RECHARGE, ADD_MONEY, SALARY, REMITTANCE_IN, FLOAT_TOPUP, with before/after balances |
| `account_events` | — | SIGNUP, DEVICE_CHANGE, SIM_SWAP, PIN_RESET |
| `complaints` | — | 16268-helpline-style reports, category FRAUD / WRONG_SEND |
| `customers`, `agents`, `merchants`, `billers` | — | entity attributes; protected fields (gender, age band, division, urban/rural, segment) are flagged for fairness audit only, never a model input |
| `labels`, `cases`, `wallet_truth`, `agent_truth`, `planted_scenarios.json` | — | ground truth, evaluation-only, never a feature |

### 1.2 Feature store — `data/features/features.parquet`
73 engineered features in 9 groups (`src/features/spec.py`), built once by `python -m src.features.build` from the
streaming store (`src/features/store.py`), which computes each row from the past only — verified by
`tests/test_features.py::test_no_future_leakage`.

### 1.3 Trained artifacts — `artifacts/*.joblib` (committed, a few MB)
| File | Contents |
|---|---|
| `model_bundle.joblib` | LightGBM + Isolation Forest + graph rules + fusion weights + calibration |
| `serve_bundle.joblib` | the serving-only subset (drops XGBoost/logistic comparison models) |
| `fed_serve_bundle.joblib` | the federated cross-silo GBDT, same interface as `model_bundle` |
| `demo_state.joblib` | the feature store replayed to end-of-window, for a fast boot |
| `demo_world.joblib` | staged demo scenarios (recent edges, historical alerts, demo customers) |

These are the only files the running API needs — never the raw dataset. `artifacts/portable/` holds the same
models re-exported as version-neutral JSON/text for the in-browser (Pyodide) build.

### 1.4 Live serving state — in-memory only, resets on restart
`src/serve/live.py`'s `World` object holds everything the demo mutates while running: `self.alerts` (dict, every
pre-send alert, complaint and recharge), `self.order` (display order), `self.engine.state["balances"]` (the ledger,
mutated by every ALLOW/confirm), `self.flagged` (recipient → alert id, from analyst `FLAG_RECIPIENT` actions),
`self.complained` (wallets reported), `self.audit` (the hash-chained log, see below), `self.personas` (resolved
demo customers). **None of this is written to disk.** A process restart reloads `demo_world.joblib` and starts
over from the staged snapshot — by design, so every demo run starts from the same reproducible world.

### 1.5 Audit log — hash-chained, in-memory
`World._audit()` (`src/serve/live.py:369`) appends one record per event:

```
{seq, at, actor, role, action, alert_id, detail, prev, hash}
```
`hash = SHA256(json(record without hash))`; `prev` is the previous record's hash. `World.verify_audit()` walks the
chain and reports the first break. This **detects in-process tampering** (any edited or reordered record breaks the
chain) but is **not independently tamper-proof**: it is one Python list in one process's memory, with no
external anchor and no durable storage. That limitation is stated here deliberately, not glossed over.

### 1.6 What this architecture is good for, and what it is not
Good for: a fully reproducible, offline, judge-runnable demo where every run starts from the same world and every
number is explainable from code the team wrote. **Not** a production data store: no durability across restarts, no
multi-instance consistency, no encryption at rest, no retention policy, no independent audit anchor.

---

## 2. Proposed production schema (design target, not implemented)

This section answers the integration contract already drafted in
[`docs/feedback_delivery.md`](feedback_delivery.md#integration-contract-and-production-boundaries) with concrete
tables. A real deployment needs a transactional database (e.g. PostgreSQL) for decisions/idempotency and an
append-only, externally-anchored store for audit — not the in-memory list above.

### 2.1 `decisions` — one row per scored transfer, source of idempotency
| Column | Type | Notes |
|---|---|---|
| `request_id` | uuid, PK | from the calling MFS client |
| `idempotency_key` | text, unique | a reused key with different fields → `409`; identical retry → original response |
| `customer_wallet_id`, `recipient_wallet_id` | text | |
| `amount`, `currency`, `txn_type`, `channel` | | |
| `decision_id` | uuid | returned to the client |
| `score`, `band` | numeric, enum(ALLOW/NUDGE/STEP_UP/HOLD) | |
| `policy_version`, `model_version` | text | for audit and rollback |
| `explanation_codes` | jsonb | reason codes shown to the customer, never free text |
| `expiry`, `customer_confirmation_required` | timestamptz, boolean | |
| `created_at` | timestamptz | |

Indexes: unique on `idempotency_key`; btree on `(customer_wallet_id, created_at)` for the customer's own history.

### 2.2 `complaints` — filed disputes, now with the follow-up thread built this session
| Column | Type | Notes |
|---|---|---|
| `case_id` | text, PK | `C-0001` style |
| `customer_wallet_id` | text | FK → the filer; checked on every reply (`respond_to_complaint`, `src/serve/live.py`) |
| `text`, `problem`, `language` | | the customer's own words, read by rules only, never by an LLM |
| `matched_transfer_id` | text, nullable | FK → `decisions` |
| `case_type`, `status` | enum | `genuine_wrong_send` / `likely_scam_victim` / `needs_review` / `needs_details`; status now includes `details_requested` → `details_received` |
| `thread` | jsonb array | `{role: analyst\|customer, by, text, at}` — the follow-up channel added this session |
| `deadline` | date | 10 working days, Fri/Sat excluded |

### 2.3 `analyst_actions` — verified identity, not an entered name
| Column | Type | Notes |
|---|---|---|
| `action_id` | uuid, PK | |
| `case_id` or `alert_id` | text | target |
| `actor_id` | text | **from a verified session/token, never a client-supplied name string** — closes the Phase 1 "verify analyst identities beyond entered names" gap |
| `role` | text | only `risk_analyst` may act, per `PROHORI_INTEGRATION` prototype already in `src/serve/live.py` |
| `action`, `note` | enum, text | `note` required for `DISMISS`; flows into the complaint `thread` for `ASK_CUSTOMER_DETAILS` |
| `at` | timestamptz | |

### 2.4 `audit_log` — append-only, externally anchored
Same record shape as today's in-memory chain (`seq, at, actor, role, action, target, detail, prev, hash`), but:
- **Storage:** append-only table or log store (e.g. a WORM-configured object store), never updated in place.
- **External anchor:** periodically sign the current chain head with a managed key (e.g. KMS) and publish the
  signature + key version to a location outside this system's own write access, so a compromise of this database
  alone cannot rewrite history undetected.
- **Key management:** rotation schedule, versioned signatures so old anchors still verify, and a tested
  restore/verify procedure — not just a key that exists.
- This is the concrete answer to "do not imply a local hash chain is independently tamper-proof" from
  `docs/feedback_delivery.md`; today's chain (§1.5) has none of this yet.

### 2.5 Retention, access and encryption (policy, not code)
- Encrypted at rest; least-privilege access by role (`risk_analyst` reads/writes cases; customer-facing services
  read only their own wallet's decisions).
- Partner-approved retention and deletion schedule per data class (decisions, complaint text, audit log) —
  no schedule is defined in this prototype.
- Monitoring on latency, error rate, score drift, and intervention/subgroup outcome rates (ties to the fairness
  audit in `reports/fairness.csv`), not just uptime.

### 2.6 What stays out of this database entirely
Per the federation design (`docs/feedback_delivery.md` §Federation threat model), raw transaction history for
cross-silo features is never pooled into one store without privacy-preserving aggregation — the production
data-store design must keep each division's ledger local and exchange only secure-aggregated sufficient
statistics, exactly as the current federated GBDT already does for model training.

---

**Status:** §1 describes this repository as it runs today, verified against `src/serve/live.py` and the files
actually in `artifacts/`. §2 is a design proposal; no migration, ORM model, or running database exists for it in
this codebase.
