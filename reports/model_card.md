# Model card: Prohori transaction risk score

## Intended use
Score customer-initiated money movement (Send Money, Cash Out, Payment, Add Money) before it executes, and map the score to ALLOW / NUDGE / STEP_UP / HOLD. A human (the customer, or an upay analyst for HOLD) makes every consequential decision. Not for credit, KYC or account closure decisions.

## Models
- LightGBM classifier (777 trees, Optuna-tuned on validation), 73 features from a streaming feature store (no future information).
- Isolation Forest on behaviour-deviation features (unsupervised, labels unused).
- Graph rules on hourly 24 h transaction-graph snapshots (fan-in collectors, pass-through chains, fast-flow networks, reported numbers, shared devices).
- Fusion weights fitted on validation: {'clf': 1.0, 'anom': 0.0, 'graph': 0.0}; score knots map validation false-positive targets {'NUDGE': 0.01, 'STEP_UP': 0.003, 'HOLD': 0.001} to band cut-offs 30 / 60 / 80.

## Data
Synthetic upay-like world (seed 42): 10,000 customers, 300 agents, 60 days; fraud scenarios S1-S8 injected with ground truth. Time split: train days [1, 40], validation [41, 50], test [51, 60]. No real personal data; phone numbers use the unallocated 010 prefix.

## Performance (test window)
- PR-AUC 0.9622, ROC-AUC 0.9985, recall at 0.5% FPR 0.9496 (rules baseline PR-AUC 0.188).
- Victim-side recall at STEP_UP+: 90.8%; legit customers ever held: 0.95%.
- Weakest scenarios: S5 (78%), S7 (94%).

## Fairness
Gender, age band, division, urban/rural, segment are NOT model inputs. False-positive rates are audited per group (reports/fairness.csv); flagged groups: age_band=45-59 (x1.33), age_band=60+ (x1.12), segment=farmer_rural (x1.99), segment=small_business (x1.28), kyc_level=KYC1 (x1.23).

## Limitations
- Trained on synthetic patterns; absolute numbers will drop on real data. Re-fit thresholds on real validation data.
- Social-engineering scams on the victim's own phone (S5, S7) are hardest; the warning is a nudge, not a block.
- Complaint-derived features depend on helpline reporting rates.
- Stop rates per band in the impact estimate are assumptions, not measurements.

## Responsible use
Models score, plain rules decide, people confirm. The LLM copilot (if enabled) only rewrites the structured evidence into language and never changes a band. Warnings never name or accuse the recipient.