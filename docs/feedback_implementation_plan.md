# Prohori feedback implementation plan

This plan turns the Phase 1 judge feedback in the supplied NeuroXLab feedback page into work that can be completed against the current Prohori repository. The project is a Track 01 Trust & Risk Intelligence submission; its customer-facing pre-transfer guard and analyst copilot are the primary users. Track 06 wrong-send support is an integrated capability, not a replacement for the Track 01 focus.

## Current evidence and limits

Implementation status and protocols: [feedback delivery](feedback_delivery.md). The repository now includes an isolated multi-seed runner, recipient baseline matrix, policy/fairness uncertainty, and opt-in verified server analyst identities. Execution is pending because this workstation has no Python interpreter on PATH. Customer studies, unseen-scenario scoring, local-state federation, robustness experiments, device measurements and production ledger integration remain open; the checkboxes below are not evidence of completion.

The repository already has a time-disjoint test window, component ablations, fairness reports, federated simulations, a browser and server scorer, an API, and phone/analyst interfaces. Use the existing outputs as a baseline before adding more claims. Relevant artifacts include `reports/evaluation.md`, `reports/metrics_test.json`, `reports/fairness.csv`, `reports/federated_*.json`, and `docs/test_numbers.md`.

All metrics from synthetic data are simulation evidence. Do not describe assumed warning stop rates, analyst minutes saved, or simulated customer behavior as measured impact. Customer validation, complaint-handler input, real transaction samples, and a live pilot require partner access and must be reported as pending until obtained.

## Work plan

### P0 — Sharpen the problem, user, and track

- [ ] In the README, pitch, and demo opening, name the primary persona: an upay customer about to send money to a potentially fraudulent or mistyped recipient.
- [ ] Name the secondary persona: upay trust/risk operations analyst investigating high-risk transfers and complaints. Describe merchants and agents as affected counterparties, not primary product users.
- [ ] State the mapping explicitly: Track 01 Trust & Risk Intelligence is the primary track; keypad-aware wrong-number prevention and complaint matching are supporting Track 06 capabilities.
- [ ] Add a short validation protocol for upay customers and complaint handlers: task walkthroughs for scam warnings, keypad-slip suggestions for unfamiliar recipients and similar numbers, comprehension, incorrect suggestions, and whether the user can safely cancel or continue. Record sample, method, and limitations; do not imply interviews happened before they do.

**Acceptance:** README and presentation have consistent personas/track framing; a reviewer can identify whose decision the product supports and at what point in the transfer.

### P1 — Make the evaluation claims stronger and auditable

- [ ] Preserve the existing time split (training, validation, untouched test window) and report it next to every headline result. Never tune thresholds on the test window.
- [ ] Re-run the current evaluation across multiple generator seeds. Report mean and range for PR-AUC, precision/recall by risk band, false-positive rates, wrong-number suggestion precision/coverage, and scenario-level catches. Keep the current seed-42 run as a reproducibility reference.
- [ ] Expand component ablations to isolate the incremental value of keypad-aware distance over ordinary edit distance, amount habits over the base model, graph signals, and federated vs central learning. Include error counts and confidence intervals where sample sizes support them.
- [ ] Evaluate keypad suggestions on an explicit matrix: familiar vs unfamiliar recipient, one-key error vs adjacent swap, and similar-number contacts. Measure suggestion precision, recall/coverage, false suggestions, and no-suggestion cases against ordinary edit distance.
- [ ] Add unseen scenario variants and a documented evaluation set; keep them held out from feature and threshold tuning.
- [ ] Document why the system combines components even when one model dominates a particular aggregate metric. Show per-scenario or subgroup improvements and failure cases rather than asserting that each component improves every metric.
- [ ] Add a privacy-preserving cross-silo evaluation that uses local silo state and aggregated sufficient statistics only. Document which existing federated runs still rely on a pooled feature store or pooled validation thresholds; do not call that deployment-ready federation.

**Acceptance:** a reproducible report separates existing test results from multi-seed/unseen-scenario results, has an explicit baseline for ordinary edit distance, and discloses any pooled-data assumptions.

### P2 — Replace assumed impact with a pilot measurement design

- [ ] Define primary outcomes: wrong-number transfers prevented per 1,000 eligible sends; scam transfer completion after warning by band; incorrect suggestion rate; legitimate-transfer abandonment; customer comprehension; analyst handling time and case disposition quality.
- [ ] Define economic accounting with partner-approved inputs: prevented loss (observed amount at risk, not a simulated stop-rate multiplier), operational review cost, customer support cost, and implementation/serving cost. Show formula and sensitivity ranges; do not claim ROI without validated inputs.
- [ ] Design a staged evaluation: usability study first; shadow scoring with no transaction intervention; then a partner-approved controlled pilot with consent, guardrails, incident escalation, and rollback. Establish minimum sample sizes and decision thresholds before the pilot.
- [ ] Treat NUDGE/STEP_UP/HOLD stop rates and analyst minutes as assumptions until directly measured. Label current projections as modeled scenarios and show how outcomes change when assumptions vary.

**Acceptance:** impact tables distinguish observed, simulated, and assumed values and show a concrete measurement path for each claim.

### P3 — Demonstrate prototype and integration quality

- [ ] Produce a compact verification record for the existing automated test suite and browser/server prediction parity, with commands, environment, date, and results. Do not report a test count without a captured run.
- [ ] Measure initial load and scoring latency on a low-end phone profile and a typical laptop; identify optimizations against a stated target. Measure concurrent analyst actions and recovery after refresh/interrupted sessions.
- [ ] Exercise API behavior for authorization, idempotency, timeout, unavailable scorer, retries, and audit-event persistence. Document a real MFS pre-transfer contract: request fields, decision response, latency budget, authentication, replay protection, and fail-safe behavior.
- [ ] Document production data-store and deployment boundaries: authoritative server-side scoring and policy, protected audit records, client receives only decision/explanation, retention/access controls, and operational monitoring. The browser demo is not authoritative for transaction holds.
- [ ] Demonstrate end-to-end customer and analyst flows using the current UI; track interaction friction and recovery issues from the usability pass.

**Acceptance:** a reviewer can see measured performance, reproducible parity evidence, a backend integration contract, and a clear boundary between demo and authoritative production controls.

### P4 — Close fairness, security, and federation gaps

- [ ] Use the existing group FPR findings as a prioritized remediation study, especially rural farmers and older customers. Examine calibration, sample size, and feature causes; test candidate mitigations on validation data and confirm on a later untouched evaluation set. Do not silently introduce per-group thresholds.
- [ ] Add uncertainty intervals and minimum-support labels to fairness results. Report intervention rates and customer outcomes alongside FPR so low-volume groups are not overinterpreted.
- [ ] Replace entered-name-only analyst actions with authenticated identities and role-based authorization in any integration prototype; log actor, action, target, timestamp, and reason server-side.
- [ ] Define append-only audit storage and external hash anchoring for a production design; identify key management, rotation, verification, and recovery. Avoid implying a local hash chain is independently tamper-proof.
- [ ] Threat-model federated aggregation for client dropout, collusion, malicious updates, poisoning, and small cohorts. Add simulated robustness experiments and state what secure aggregation and differential privacy do not protect against.
- [ ] Validate customer-facing Bangla and warning comprehension with target users, including accessibility and age-related usability.

**Acceptance:** fairness follow-up has measured outcomes, consequential actions require verified permissions in the integration design, and federation/privacy claims name tested threat assumptions.

## Sequence and dependencies

1. Complete P0 and capture the current baseline before changing model behavior.
2. Run P1 offline using the existing generated-data pipeline; keep new seeds/scenarios isolated from tuning.
3. Complete P3 technical verification and P4 offline threat/fairness analyses in parallel where possible.
4. Run customer/handler validation and any real-data or live-pilot work only with an MFS partner and approved access. P2 real-world outcomes depend on that access.
5. Update README, pitch, and demo claims only from dated artifacts produced by these work items.

## Feedback traceability

| Judge feedback theme | Plan section |
|---|---|
| Target user and track fit | P0 |
| Customer and complaint-handler validation | P0, P4 |
| Unseen scenarios, seeds, ablations, baseline comparison | P1 |
| Real impact, economic reasoning, assumed stop rates/time | P2 |
| Test evidence, load, low-end devices, concurrency, recovery | P3 |
| Secure pre-transfer integration, API, throughput, data store | P3 |
| Cross-division privacy-preserving graph/federated design | P1, P4 |
| Rural/older customer false positives, explainability, fairness | P4 |
| Verified analyst permissions and tamper-evident audit | P4 |
