# Model cards

All models are trained and evaluated on synthetic data only (rule R16). Owner: Team Ferot. Version:
`ferot-2026.10.01`. Metrics: `reports/metrics.json` (test window days 75–90).

## Ferot Guard (pre-send check)
- **Purpose:** warn the customer before a transfer that is likely a typo or a scam. It never blocks.
- **Data:** 7,000 ordinary transfers plus every scam and typo transfer in the synthetic ledger, split by time
  (train, validation, test). Features are computed as of the moment of sending: relationship with the recipient
  (first-ever, earlier transfers, typo distance to a frequent contact), receiving-wallet behaviour (age, distinct and
  first-time senders in 7 days, pass-through and inbound in 30 days, earlier complaints), amount versus the sender's
  usual, hour.
- **Method:** LightGBM (`scale_pos_weight` 20, early stopping) for P(scam), plus an IsolationForest anomaly score on
  amount versus usual, unusual hour, first-time payee and amount. The fusion weight is chosen on validation (it chose the model alone, weight 1.0). Bands: warn
  above the 99th percentile and pause above the 99.9th percentile of ordinary validation transfers, mapped to a
  0–100 risk (warn at 30, review at 70). A separate keypad check warns on a first-time number within keypad distance
  1.6 of a contact paid at least twice (`config/guard.yaml`).
- **Results (test):** PR-AUC 0.997; 98.8% of scam transfers warned (precision 94.4%); 0.44 ordinary transfers in
  100 warned, none paused; typos caught 100%.
- **Fairness:** ordinary transfers warned per 100: app 0.34, USSD 0.78; rural 0.39, urban 0.54; by age 0–1.13.
- **Limits:** the synthetic scam drop wallets are cleaner than real ones. Reasons are built only from feature values
  (tested). Guard cannot see who called the customer.

## M1 Complaint extractor
- **Purpose:** read amount, number (or last 4 digits), relative time, TrxID and scam cues from Bangla, Banglish or English.
- **Method:** rules first (Bangla digits, number words such as "pach hajar" / "৫ হাজার" / "5k", phone and TrxID
  patterns). Optional Claude call on masked text (phone numbers and TrxIDs replaced by tokens) with a fixed JSON
  schema; rules win on exact patterns, disagreements are flagged.
- **Results:** 100% on generated complaints; 24/24 hand-written complaints pass.
- **Limits:** dialects and voice notes not covered; partial numbers rely on "...1234" style.

## M2 Transaction matcher
- **Purpose:** find the disputed transfer among the claimant's transfers in the last 7 days.
- **Method:** score on TrxID, amount, number similarity, stated time and recency; the margin gives a confidence.
- **Results:** top-1 0.95. Low confidence means the agent confirms.

## M3 Intended-number matcher
- **Purpose:** find the number the customer meant to type.
- **Method:** keypad-weighted Damerau–Levenshtein distance (neighbouring key 0.6, swap 0.8) against numbers paid in
  the last 120 days, weighted by frequency and recency.
- **Results:** 0.98 on genuine typos; fires on 2.7% of other cases.

## M4 Case classifier
- **Purpose:** genuine wrong-send, scam victim, double-recovery claim, false claim, technical failure.
- **Method:** LightGBM (balanced classes, early stopping) on 33 as-of features: relationship, timing, recipient
  graph behaviour, return flows, claimant history, system events, text cues. Reasons from TreeSHAP contributions.
- **Results:** macro-F1 0.96 (keyword rules 0.55, text-only 0.50); scam recall 0.88; unseen job-offer scams 0.90;
  ECE 0.08. At the hold threshold P(scam) ≥ 0.45: recall 0.85, precision 1.00, 1 wrongful rejection among 219 victims
  (the threshold was 0.60, recall 0.70).
- **Fairness (accuracy by group):** language gap 1.3 points; channel 3.8 (app 98.4%, phone 94.6%); age 4.4; area
  0.5; KYC 1.7. Scam recall is lower for phone complaints (81.4%), limited KYC (80.0%) and ages 25–34 (78.3%).
- **Limits:** see `docs/error_analysis.md`. Never acts alone: the policy engine and a human decide.

## M5 Recoverability
- **Purpose:** chance that at least half the disputed money is still holdable after 1, 6, 24, 48, 72 hours.
- **Method:** one LightGBM classifier per horizon; monotone curve; expected taka = holdable now × probability.
- **Results:** Brier at 6 h 0.072 vs 0.099 for the "balance now" baseline.

## M6 Queue priority
- **Purpose:** order the queue. priority = R(0) − R(wait) + vulnerability + SLA term.
- **Results (simulation):** +4.2% holdable money vs first-come-first-served (95% CI 3.8–4.6%); largest-first +4.5%;
  oracle ceiling +6.7%.

## M7 Mule clusters
- **Purpose:** surface wallets named by ≥3 complainants, linked by onward transfers, for the AML/CFT team.
- **Limits:** a lead for analysts, not an accusation; the AML team decides any report (MLPA §6).

## M8 Drafts
- **Purpose:** customer, recipient and internal messages in Bangla and English.
- **Method:** templates with code-filled slots; optional LLM polish. Checks: grounded numbers, no refund promise,
  no tipping off for anyone under AML review. A failed check falls back to the template.
