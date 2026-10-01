# Prohori – upay Scam Shield 🛡️
### AI Dev Fest 2026 · Track 01: Trust and Risk Intelligence · DIU CPC × upay

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)]()
[![License: MIT](https://img.shields.io/badge/license-MIT-green)]()

---

## What is Prohori?

**Prohori** (প্রহরী – *guardian*) is a real-time scam detection system for Bangladesh's mobile financial services (MFS). It interrupts fraudulent transactions before money leaves the victim's wallet — with risk warnings in Bangla for USSD / feature-phone users.

### How it works

```
Transaction  →  Feature Store  →  Risk Score  →  Warning (Bangla/English)
             (stateful, no leak)  (0-100/100)    ALLOW / NUDGE / WARN / HIGH
```

Risk score = `0.5 × P(fraud) + 0.3 × Anomaly + 0.2 × Graph`

---

## Quick Start

### 1 – Install dependencies

```bash
pip install pandas numpy pyyaml lightgbm xgboost scikit-learn joblib
# optional (feature store speed): pyarrow
# optional (tuning): optuna
# optional (explainability): shap
# optional (API): fastapi uvicorn
```

### 2 – Generate the dataset

```bash
python -m src.datagen.generate
```

This creates `data/` with:
| File | Rows | Description |
|------|------|-------------|
| `customers.csv` | 10,000 | Synthetic customer profiles |
| `agents.csv` | 300 | Cash-in/out agents in 30 peer groups |
| `transactions.csv` | ~600,000 | Time-sorted MFS transactions |
| `labels.csv` | ~600,000 | Ground-truth labels (NEVER a model feature) |
| `data/sample/` | ~20,000 | Git-safe stratified sample |

**Options:**
```
--config config.yaml   # path to config (all parameters are in here)
--out    data/         # output directory
--sample 20000         # rows for the git-safe sample
--parquet              # also write .parquet files
--no-tests             # skip T1-T14 acceptance tests
```

> ⏱️ Estimated time: **3–10 minutes** on a modern laptop.

### 3 – Compute features

```bash
python src/features/feature_store.py data/
```

Produces `data/features.parquet` — 20+ derived features with zero future leakage.

### 4 – Train models

```bash
python -m src.training.train --data data/ --models models/
# With Optuna tuning (~30 trials, +10-20 min):
python -m src.training.train --data data/ --models models/ --tune
```

### 5 – Score a transaction (demo)

```bash
python src/inference/score.py --models models/
```

### 6 – Run the API

```bash
uvicorn src.inference.score:app --host 0.0.0.0 --port 8000
# POST /score  with feature JSON
# GET  /health
```

---

## Repository Structure

```
Prohori/
├── config.yaml                      # All parameters (KYC caps, fees, volumes)
├── prohori_warnings_bn.json         # Bangla UI strings (UTF-8)
├── src/
│   ├── datagen/
│   │   ├── config_loader.py         # Module 1 – load config.yaml
│   │   ├── builders.py              # Module 2 – customers, agents, profiles
│   │   ├── normal_life.py           # Module 3 – legitimate transaction simulation
│   │   ├── fraud_injectors.py       # Module 4 – S1…S7 fraud injection
│   │   ├── scenarios.py             # Module 5 – SC-01…SC-10, SB-01…SB-08
│   │   ├── generate.py              # Orchestrator (run this)
│   │   └── tests.py                 # Module 8 – T1–T14 acceptance tests
│   ├── features/
│   │   └── feature_store.py         # Stateful rolling feature engine
│   ├── training/
│   │   └── train.py                 # LightGBM + XGBoost + IsolationForest
│   └── inference/
│       └── score.py                 # Risk scoring + FastAPI endpoint
├── notebooks/
│   └── prohori_full_pipeline.py     # Kaggle-ready notebook
├── data/
│   └── sample/                      # Git-safe 20k-row sample (seed=42)
├── docs/
│   └── data_validation.txt          # T1-T14 results (auto-generated)
└── models/                          # Trained model artifacts
```

---

## Dataset Schema

### transactions.csv (key columns)
| Column | Type | Description |
|--------|------|-------------|
| `txn_id` | str | T00000001… |
| `timestamp` | datetime | Asia/Dhaka, sorted ascending |
| `sender_id` / `recipient_id` | str | customer_id, agent_id, or merchant M0001… |
| `txn_type` | str | P2P_SEND, CASH_OUT_AGENT, CASH_IN, … |
| `amount_tk` | float | BDT; respects KYC caps |
| `fee_tk` | float | P2P=0; agent cash-out ~1.4% |
| `channel` | str | APP / USSD / AGENT_ASSISTED |
| `device_changed` | 0/1 | New device for sender |
| `session_seconds` | int | Coached victims: 150-600 s |
| `pin_attempts` | int | Normal=1; coached/confused: 2-4 |

### labels.csv (never used as model input)
| Column | Description |
|--------|-------------|
| `is_fraud` | 0/1 |
| `fraud_class` | S1-S7 |
| `fraud_role` | victim_send / takeover_send / collector_inbound / mule_hop / cashout |
| `case_id` | Groups rows of one scam |
| `scenario_id` | SC-01…SC-10 or SB-01…SB-08 |
| `is_benign_lookalike` | Legit rows that resemble fraud |
| `expected_band` | ALLOW / NUDGE / WARN / HIGH |

---

## Fraud Typology Summary

| Class | Story | Key signals |
|-------|-------|-------------|
| **S1** OTP/PIN takeover | Fake customer care call | 22-04h, new device, drain 70-98% |
| **S2** Prize/lottery | 'You won' fee to collector | Collector age <3 days, 15-40 victims |
| **S3** Mule chain | Stolen funds hop through wallets | Pass-through lag 2-15 min, graph path |
| **S4** Fake seller | Facebook shop advance payment | Zero supplier outflows, in-degree |
| **S5** Rogue agent | 7-10× peer cash-out volume | agent_peer_zscore, flagged wallet share |
| **S6** SIM swap | New device, early morning, drain | Borderline score (NUDGE) by design |
| **S7** Guided victim | Elderly coached by caller | session_seconds 150-600, pin_attempts 2-4 |

---

## Risk Score & Warning UX

| Score | Band | Action |
|-------|------|--------|
| 0-29 | **ALLOW** | Normal flow |
| 30-59 | **NUDGE** | One-line hint |
| 60-84 | **WARN** | Full warning + Cancel default |
| 85-100 | **HIGH** | Strong warning + 10-min cooling-off + freeze recommendation |

Bangla strings: [`prohori_warnings_bn.json`](prohori_warnings_bn.json)

---

## Dataset Disclosure

**100% synthetic** — no real phone numbers, NIDs, names, or upay data. Generated with `seed=42`; same seed reproduces byte-identical CSVs.

- Fraud is **over-represented** (0.5% vs ~0.01-0.1% real-life) so models have enough positives. Report PR-AUC and recall at fixed false-alarm rate, not accuracy.
- KYC caps and fee rates are based on 2021-22 public sources — **verify** on upay's official limits-and-charges page before citing them in your pitch.
- Fraud labels are ground-truth from the generator. Real upay data would have noisy labels — report this as a limitation.
- Scenario numbers (e.g. "34 unique senders") are illustrative recipes, not statistics.
- As of: October 2026. Bangladesh Bank MFS Regulations 2022.

---

## Acceptance Tests

Run `python -m src.datagen.generate` to auto-run T1-T14. Results saved to `docs/data_validation.txt`.

| # | Test | Pass condition |
|---|------|----------------|
| T1 | Row count & window | 550k-650k rows; sorted |
| T2 | Fraud prevalence | 0.4%-0.6%; class mix ±5 pts |
| T3 | Balance integrity | after = before - amount - fee |
| T4 | KYC caps | <1% normal rows over cap |
| T5 | Normal amount shape | Median P2P 900-2,500 Tk |
| T6 | Calendar effects | Friday +20-50%; Eid 2-3× |
| T7 | Night activity | Normal <2%; S1 >50% |
| T8 | Scenario presence | All SC-01..SC-10, SB-01..SB-08 |
| T9 | Collector structure | >10 unique senders; >80% first-time |
| T10 | Agent outliers | Rogue agents 7-10× peers |
| T11 | No leakage | labels.csv columns NOT in transactions.csv |
| T12 | Benign look-alikes | ≥1.5× fraud rows |
| T13 | Reproducibility | seed=42 → identical CSVs |
| T14 | Privacy | No real phone/NID patterns |

---

## Deployment

**Render (free tier):**
```bash
# requirements.txt → installs only inference deps
# Start command:
uvicorn src.inference.score:app --host 0.0.0.0 --port $PORT
```
> ⚠️ Render free tier spins down after 15 min idle. Open URL 2 min before judging.

**Hugging Face Spaces (backup):** CPU Basic, 2 vCPU, 16 GB RAM — no model training needed, just inference.

---

## References

- Policy Research Institute (PRI) Bangladesh: MFS fraud survey (~7,300 users, ~2,000 agents)
- Bangladesh Bank MFS Regulations 2022 and BFIU AML/CFT circulars
- upay official limits-and-charges page *(verify date)*
- PaySim benchmark: Kaggle `ealaxi/paysim1` *(used for technical comparison only)*
