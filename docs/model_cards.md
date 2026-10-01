# Model cards

All models are trained and evaluated on synthetic data only (rule R16). Owner: Team Ferot. Version:
`ferot-2026.10.01`. Metrics: `reports/metrics.json` (test window days 75–90).

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
  ECE 0.08.
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
