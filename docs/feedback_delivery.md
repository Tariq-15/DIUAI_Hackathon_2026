# Feedback delivery and measurement protocol

Status: 2026-10-07. Repository changes are implementation work, not evidence of a customer study or successful pilot. The seed-42 reference reports have been preserved. New results belong under `runs/feedback`.

## Pitch and demo opening

Prohori supports an upay customer about to send money to a potentially fraudulent or mistyped recipient. Its secondary user is an upay trust/risk operations analyst investigating high-risk transfers and complaints. Merchants and agents are affected counterparties. Track 01 Trust & Risk Intelligence is primary; keypad-aware wrong-number prevention and complaint matching support Track 06. Demonstrate the customer's cancel/continue decision first, then the analyst's evidence and follow-up.

## Customer and complaint-handler validation — pending partner access

Recruit 24 customers across younger/older and urban/rural groups, including USSD users, and 6 complaint handlers. This is a proposed usability sample, not a population impact estimate. Obtain consent, anonymize observations, and use synthetic recipients and balances. Counterbalance task order; record language, device, age band, familiarity, completion time, assistance, errors, comprehension, cancel/continue choice and participant explanation.

Tasks: a legitimate send; unfamiliar scam recipient; familiar one-key slip; adjacent swap; two similar contacts; an unfamiliar intended recipient resembling a saved contact; unusually large legitimate amount; complaint matching and disposition. Ask participants to explain each warning in their own words, locate cancel and continue, reject an incorrect suggestion, and recover after refresh or interruption. Have Bangla-speaking customers assess wording, screen-reader output, text resizing and audio. Record incorrect suggestions and unsafe continuations independently. Do not treat stated intention as prevented loss.

Exit to shadow scoring only after every participant can cancel, no unresolved critical safety issue remains, and at least 90% explain who receives the money and what continuing does. Report raw counts and uncertainty; revise and repeat failed tasks. Partner approval is required to recruit or process partner data.

## Offline evaluation

Run `python -m tools.feedback_evaluate --out-root runs/feedback` for the fixed recipient diagnostic matrix. It reports suggestions, correct/false suggestions, no-suggestion cases, precision, recall, coverage and binomial intervals by familiarity, mistake and competing contacts. The ordinary Levenshtein comparison shares the existing eligibility, ranking and cutoff; its substitution cost is one and swaps cost two. This is a transparent baseline, not an independently optimized comparator. Default keypad costs are evaluated; learned-cost comparison remains pending.

Run `python -m tools.feedback_evaluate --out-root runs/feedback-full --run-seeds --seeds 42 43 44 --trials 30` for isolated full pipeline runs. Use `--scale 0.05 --trials 0` only for smoke verification; do not compare scaled results with full-data headlines. Each seed has its own data, model, report and captured log. Summary includes mean/range and seed support for PR-AUC, band precision/recall/FPR and scenario recall. Training, validation and untouched test days remain configured in `config.yaml`; fitting and policy selection use validation only. Existing feature-group and component ablations run separately per seed.

**Completed 2026-10-07** (`runs/feedback-full/summary.json`): PR-AUC mean **0.9704**, range 0.9622–0.9781 (n=3; seed
42 reproduced the published 0.9622 exactly). Band precision/recall across the three seeds: NUDGE+ recall
97.2–99.3%, STEP_UP+ precision 70.4–81.1%, HOLD+ precision 86.8–95.3% / recall 88.8–94.0%. Per-scenario STEP_UP+
recall is at or near 100% for S1/S3/S6/S8 across all seeds; S5 (fake-seller / pressure scam, already named as the
weakest case on a single seed) ranges 69.0–94.5% — multiple seeds confirm it as the weakest case, not an artifact
of one run.

Policy reports now include confusion counts and Wilson intervals. Fairness reports add false-warning counts, intervals, minimum support (1,000 legitimate transfers), and intervention rates. Transaction intervals are descriptive: repeated customer observations violate independence. Customer-cluster bootstrap intervals and downstream customer outcomes remain pending.

Before unseen evaluation, freeze model/cost/threshold hashes. Prepare a separate later window with lower-volume collectors, older warmed mules, delayed cash-out, fewer complaints, and legitimate seasonal lump transfers. Publish variant parameters, labels and scenario denominators before scoring; never refit on this window. Amount-habit incremental ablation and local-state cross-silo evaluation are outstanding, not completed by the runner.

Do not infer component value from equal aggregate PR-AUC. Compare scenario misses and benign look-alikes; expose failures. For rural farmers and older customers, examine amount deviation, frequency and calibration on validation, compare history-support gates and global calibration, then confirm a selected mitigation on a later untouched window. Group thresholds are not introduced.

## Pilot outcomes and economic accounting

Stage 1 is the usability study. Stage 2 is partner-approved shadow scoring without intervention. Stage 3 is a consented controlled pilot, randomized by customer with stratification and a frozen analysis plan. Specify power using shadow base rates before enrollment; for a binary outcome with rate p and margin e, an initial independent-observation estimate is n = 1.96² p(1-p)/e², inflated for customer clustering and attrition. Use a power calculation for treatment differences; 24 usability participants cannot establish impact.

| Outcome | Measurement and denominator |
|---|---|
| Wrong-number transfers prevented per 1,000 eligible sends | Independently confirmed intended recipient, correction/cancellation, and subsequent transfer reconciliation; eligible sends defined before randomization |
| Scam completion after warning | Confirmed scam sends completed / confirmed scam warnings, separately by band |
| Incorrect suggestion rate | Incorrect recipient suggestions / all suggestions; blinded confirmation |
| Legitimate abandonment | Legitimate eligible sends abandoned / legitimate eligible sends; compare control and reconcile later sends |
| Comprehension | Correct teach-back / completed warning tasks, by language and age |
| Analyst time and quality | Measured active handling time and blinded rubric-scored disposition; randomized case assignment |

Pre-register cohort sizes, exclusion rules, incident escalation owner, stop rules and rollback before intervention. Proposed guardrails for partner review: stop on any system-caused recipient misdirection or unauthorized action; investigate a legitimate-abandonment increase above 1 percentage point; proceed only if comprehension reaches 90% and the upper 95% interval for incorrect suggestions is below 1%. These are proposed targets, not approved policy.

Net benefit = observed attributable prevented loss − incremental review cost − incremental support cost − implementation/serving cost. Prevented loss needs independently adjudicated outcomes and a controlled counterfactual; amounts cancelled in a demo are not observed loss saved. Review cost = cases × measured minutes / 60 × partner-approved hourly cost. Support cost = attributable contacts × unit support cost. Evaluate low/base/high partner-approved cost inputs and prevention attribution. Do not publish ROI until these inputs and outcomes are validated.

Current stop rates ALLOW/NUDGE/STEP_UP/HOLD = 0/.3/.7/1 and analyst times 20/3 minutes are assumptions. For sensitivity, report prevented-value projections at 0, .5 and 1 times each non-ALLOW stop rate; handling savings at copilot times 3, 10 and 20 minutes. Label all such outputs modeled scenarios, separate from simulated detection metrics and observed pilot outcomes.

## Integration contract and production boundaries

The current `/api/v1/risk-score` is a stateful demo: ALLOW can execute a synthetic transfer. It is not an authoritative MFS authorization endpoint. Do not send actual transfers to it. A production adapter must score without committing and bind the response to the ledger transaction.

Proposed request: authenticated partner/client identity, customer wallet ID, recipient ID, amount/currency, transaction type, channel/device signals, request ID, unique idempotency key, event timestamp and nonce. Proposed response: request ID, decision ID, score/band, policy/model version, explanation codes, expiry and required customer confirmation. The ledger validates binding/expiry and executes once. A reused idempotency key with different fields returns 409; identical retries return the original response. Timestamp/nonce checks prevent replay. Authentication uses partner mTLS and audience-bound short-lived tokens; never trust a client-supplied actor or risk score.

Proposed service budget: p95 scoring below 200 ms, p99 below 500 ms under partner-agreed load. Timeout or unavailable scorer returns explicit unavailable status and invokes partner-approved fallback/step-up; it never fabricates ALLOW. Client retries use bounded exponential backoff and the same idempotency key. These budgets and behaviors are design targets; idempotency, scorer timeout and durable ledger integration are not implemented in the demo.

`PROHORI_INTEGRATION=1` protects server analyst actions using `PROHORI_ANALYST_TOKENS`, a secret JSON mapping bearer tokens to `{name, role}`. Only `risk_analyst` can act; audit identity comes from server configuration. Missing configuration fails closed. This is a minimal integration authentication prototype; all other demo routes remain unsuitable for public production deployment. Replace static tokens with partner identity provider credentials, revocation and rotation before deployment. Browser analyst actions remain local simulation.

Authoritative server scoring/policy and the ledger retain protected evidence; clients receive decisions/explanations only. Use durable transactional state for decisions and idempotency, encrypted restricted audit storage, partner-approved retention/deletion schedules, least-privilege access and monitoring for latency, errors, drift, intervention and subgroup outcomes. The current in-memory world resets on restart. A local hash chain detects some modifications but cannot independently establish integrity: store append-only events with sequence, actor, action, target, reason, timestamp, previous hash and version; periodically sign externally stored anchors with managed keys, record key versions, rotate keys and test restore/verification. No claim of independent tamper resistance is made.

## Federation threat model

Existing federated GBDT uses a pooled streaming feature store and pooled serving/calibration infrastructure. Secure aggregation simulation and local training do not make that deployment-ready federation. A local-state evaluation must construct histories and graph features per silo, expose aggregate sufficient statistics only, freeze validation-selected thresholds and report the accuracy loss from unavailable cross-silo edges. This remains pending.

Test client dropout before/after mask exchange, small cohorts, colluding neighbours and coordinator, gradient sign flips, oversized updates and poisoned labels. Compare rejection/clipping/quorum controls against clean accuracy and minority-cohort errors; report attack strength and compromised-client count. Ring masks need dropout recovery and independent parties; all simulated masks coexist in one process. Secure aggregation does not validate updates or defeat collusion beyond protocol assumptions. Differential privacy does not prevent poisoning or hide all public metadata; specify clipping, sampling, epsilon/delta and composition. Robustness experiments remain pending.

## Verification record

Captured 2026-10-07 on Windows 11, Python 3.12.10, commit `7fc5ec1` (`python -m tools.feedback_verify --out-root runs/feedback/verification`): **61 tests passed, 0 failures, 0 errors, 0 skipped** (`pytest -q -ra`, JUnit in `runs/feedback/verification/pytest.xml`); pip freeze, git HEAD and working-tree status are archived alongside (`0.log`–`3.log`, `verification.json`). The recipient keypad vs ordinary-edit-distance diagnostic ran the same day (`runs/feedback/recipient_matrix.json`). The multi-seed full re-run (seeds 42/43/44, `--trials 30`) and browser/device latency measurements remain pending on this machine. Earlier badge counts of 58 are superseded by this captured 61.

On a provisioned environment run `python -m tools.feedback_verify --out-root runs/feedback/verification` to capture interpreter/package versions, commit, working-tree status, test output and JUnit results. Also archive the working-tree diff. The existing portable-model and browser-dispatcher tests validate scorer parity in Python; actual browser execution also requires browser measurements. Measure cold/warm load and p50/p95 score latency on a low-end phone and laptop with stated CPU/network profiles, at least 30 repetitions. Exercise simultaneous analyst actions, refresh, interruption, backend restart and retries; record duplicate actions, lost state and recovery time. No measurements have been invented.
