# Prohori feedback implementation plan

This plan turns the Phase 1 judge feedback (NeuroXLab feedback page) into prioritised work against the current
repository. Prohori is a **Track 01 Trust & Risk Intelligence** submission: the customer-facing pre-transfer guard
and the analyst copilot are the primary users; Track 06 wrong-send support is an integrated capability, not a
replacement for the Track 01 focus.

Work is ordered by **points recoverable ÷ effort**, not by criterion number. Delivery and measurement protocols stay
in [feedback delivery](feedback_delivery.md); this file is the prioritised backlog.

## Phase 1 scores and the lever behind each

| Criterion | Score | Biggest lever in the comments |
|---|---|---|
| Problem relevance | 15.67 / 20 | J2: "no clear target user; does not map to a track" (J1/J3 already positive) |
| AI/ML depth | 14.67 / 20 | J1: unseen scenarios, multi-seed, incremental value of non-LightGBM components; J2: "no sign of train/test separation" |
| Business/customer impact | **9.33 / 20** | lowest share; assumed stop rates and analyst minutes; J2: "no impact metric, no economic reasoning" |
| Prototype quality | 8.0 / 15 | J2: "little/no source code found; no visible UI"; J1: prove the 58 tests and parity, cut the ~12 s load |
| Innovation | 7.0 / 10 | J1: quantify keypad vs ordinary edit distance; J2: no stated differentiator vs existing fintech |
| Scalability & integration | 5.67 / 10 | J2: "no API design for a real backend; no deployment / data-store" |
| Responsible AI & security | 3.33 / 5 | rural/older FPR; verified analyst identity; externally anchored audit; federation threat model |

**Two framing facts drive the ordering.**

1. **Judge 2 lost us points by not finding things that exist** — source code, the UI, the API design, train/test
   separation. Those are built. A large fraction of the gap is packaging and presentation, the cheapest points on
   the board.
2. **Execution has started (2026-10-07).** The environment is provisioned and the first dated artifacts exist:
   **61 tests pass** (`runs/feedback/verification/`) and the keypad vs ordinary-edit-distance diagnostic
   (`runs/feedback/recipient_matrix.json`). The multi-seed full re-run is in progress; latency and partner work are
   still pending. Phase 2 rewards dated artifacts, not plans. Every metric from synthetic data remains simulation
   evidence; assumed stop rates, analyst minutes saved and simulated customer behaviour must not be reported as
   measured impact.

## Tier 0 — Packaging wins (fixes "can't find it"; days, no new engineering)

- [ ] Make the submitted bundle legible: source paths, UI screenshots, live demo link and `/docs` API surface at the
      top level. Add a one-page "where is everything" map (code paths, demo URL, API docs, the test command).
- [ ] Make the train/validation/test split unmissable: days 1–40 train, 41–50 validation, 51–60 untouched test, read
      once. Put the split next to every headline metric in the README opening and the pitch, not in a collapsed
      section. (Directly answers J2's "no sign of train/test separation".)
- [ ] Name the personas and track in the README, pitch and demo opening: primary — an upay customer about to send to
      a potentially fraudulent or mistyped recipient; secondary — an upay trust/risk operations analyst. Merchants
      and agents are affected counterparties, not primary users. Track 01 primary; keypad-aware wrong-number
      prevention and complaint matching support Track 06.

**Acceptance:** a reviewer opening the bundle finds code, UI and API within one click, can state whose decision the
product supports and at what moment, and sees the test window beside every headline result.

## Tier 1 — Execute the offline evidence (highest value, no partner needed)

Blocked only on a working interpreter. Resolve the environment first (see Dependencies), then run and commit dated
artifacts under `runs/feedback/`.

- [x] Provision Python 3.12 on PATH (done: Python 3.12.10, Windows 11; optuna and matplotlib added to complete the
      pipeline environment). Captured in the verification record.
- [x] `python -m tools.feedback_verify --out-root runs/feedback/verification` (2026-10-07, commit `7fc5ec1`):
      **61 tests pass, 0 failures**, with pip freeze, git HEAD, working-tree status and JUnit archived. Supersedes
      the historical 58-test badge.
- [~] `python -m tools.feedback_evaluate --out-root runs/feedback-full --run-seeds --seeds 42 43 44 --trials 30`:
      **in progress** (seeds 42/43/44, 30 Optuna trials each; regenerates ~600k-row data per seed). Will yield mean
      and range for PR-AUC, band precision/recall/FPR, wrong-number suggestion precision/coverage, and scenario
      catches. Seed-42 remains the reproducibility reference, isolated from new seeds. A `--trials 0` quick
      stability variant is available if a completed multi-seed result is needed sooner.
- [x] Keypad vs ordinary-edit-distance matrix (`runs/feedback/recipient_matrix.json`, 2026-10-07): keypad catches
      adjacent-digit **swaps 6/12 vs ordinary edit distance 0/12** (unit-cost Levenshtein scores a transposition as
      2 and never suggests), at the cost of more false suggestions on legitimately-similar numbers (9 vs 6); both
      correctly stay silent on distant numbers and exact contacts. Small fixed diagnostic (n=60/model, wide binomial
      intervals); labelled "not customer validation".
- [ ] Prepare and freeze an unseen later-window scenario set (lower-volume collectors, older warmed mules, delayed
      cash-out, fewer complaints, seasonal lump transfers); publish variant parameters and denominators before
      scoring; never refit on it.
- [ ] Incremental ablations: keypad-aware distance over ordinary edit distance, amount habits over the base model,
      graph signals, federated vs central — with error counts and intervals where sample size supports them. Document
      *why* components are combined even when LightGBM dominates the aggregate: show per-scenario and subgroup wins
      and failure cases, not an assertion that each component improves every metric.

**Acceptance:** a reproducible report separates the seed-42 reference from multi-seed and unseen-scenario results,
carries an explicit ordinary-edit-distance baseline, and discloses every pooled-data assumption.

## Tier 2 — Impact reframing (the 9.33/20, the largest raw gap)

- [ ] Replace the single "money protected" headline with one table that labels every number as **simulated
      detection**, **modeled scenario**, or **observed**. Current stop rates (NUDGE .3 / STEP_UP .7 / HOLD 1) and
      analyst times (20 vs 3 min) are assumptions: report prevented-value projections at 0 / 0.5 / 1× each non-ALLOW
      stop rate and handling savings at 3 / 10 / 20 min.
- [ ] State the economic formula with partner-approvable low/base/high inputs: net benefit = observed attributable
      prevented loss − incremental review cost − incremental support cost − implementation/serving cost. Do not
      publish ROI until inputs and outcomes are validated. (Answers J2 "no economic reasoning" and J3 "replace
      assumed stop rates".)
- [ ] Define the primary pilot outcomes and denominators (wrong-number transfers prevented per 1,000 eligible sends,
      scam completion after warning by band, incorrect-suggestion rate, legitimate abandonment, comprehension,
      analyst handling time and disposition quality) as the measurement path for each claim.

**Acceptance:** impact tables distinguish observed, simulated and assumed values, and show a concrete measurement
path for each claim.

## Tier 3 — Prototype, integration and Responsible-AI depth

- [ ] Latency and robustness measurements (needs the Tier 1 environment): cold/warm load and p50/p95 scoring latency
      on a low-end phone profile and a typical laptop, ≥30 reps, against a stated target; concurrent analyst actions,
      refresh/interruption/backend restart and recovery. Answers J1's ~12 s load concern.
- [ ] Turn the production integration contract into a runnable adapter stub: score-without-commit bound to a ledger
      transaction; request fields, decision response, latency budget (p95 < 200 ms design target), authentication,
      replay protection and fail-safe (timeout/unavailable never fabricates ALLOW). Demonstrate
      `PROHORI_INTEGRATION=1` token auth with a reused idempotency key returning 409. (Answers J2 "no API design that
      could connect to a real backend".)
- [ ] Document production data-store and deployment boundaries: authoritative server-side scoring and policy,
      protected append-only audit records with external hash anchoring, client receives decision/explanation only,
      retention/access controls and monitoring. State plainly that the browser demo and the in-memory world are not
      authoritative for holds.
- [ ] Fairness remediation study on validation for rural farmers and older customers: calibration, sample size and
      feature causes; candidate mitigation confirmed on the untouched later window; no silent per-group thresholds.
      Add Wilson intervals, minimum-support labels (≥1,000 legit txns) and intervention rates alongside FPR.
- [ ] Verified analyst identities and role-based authorization in the integration prototype; log actor, action,
      target, timestamp and reason server-side. Define key management, rotation, verification and recovery for the
      anchored audit; avoid implying the local hash chain is independently tamper-proof.
- [ ] Federation threat model with simulated robustness experiments: client dropout before/after mask exchange,
      small cohorts, colluding neighbours and coordinator, gradient sign flips, oversized and poisoned updates.
      Report attack strength and compromised-client count; state what secure aggregation and differential privacy do
      not protect against. Add a local-state cross-silo evaluation that uses aggregated sufficient statistics only
      and reports the accuracy loss from unavailable cross-silo edges.

**Acceptance:** measured performance, a runnable backend-integration contract, a clear demo-vs-production boundary,
fairness follow-up with measured outcomes, and federation claims that name their tested threat assumptions.

## Tier 4 — Partner-gated (present as protocol, label pending)

- [ ] Customer and complaint-handler usability study (24 customers across age/urban-rural/USSD, 6 handlers), then
      partner-approved shadow scoring, then a consented controlled pilot with guardrails, incident escalation and
      rollback. Fully specified in [feedback delivery](feedback_delivery.md); report as pending until partner access
      and approval are obtained. Customer validation and real-data work cannot be completed solo and must never be
      implied to have happened.

## Dependencies and sequence

1. **Tier 0** packaging and persona/track framing — immediately; no interpreter needed.
2. **Resolve the environment** (Python 3.12 on PATH or a container) — this unblocks all of Tier 1 and the Tier 3
   latency work. It is the single gate in front of the highest-value evidence.
3. **Tier 1** offline evidence — run against the existing generated-data pipeline; keep new seeds and the unseen
   window isolated from tuning; commit dated artifacts.
4. **Tier 2** impact reframing — can proceed in parallel with Tier 1; finalise numbers once Tier 1 artifacts land.
5. **Tier 3** integration, latency, fairness and federation — in parallel where possible after the environment is up.
6. **Tier 4** customer/handler validation and any live-pilot work — only with an MFS partner and approved access.
7. Update README, pitch and demo claims **only** from dated artifacts produced by these items.

## Feedback traceability

| Judge feedback theme | Score | Plan tier |
|---|---|---|
| Target user and track fit | 15.67/20 | Tier 0 |
| Train/test separation visibility | 14.67/20 | Tier 0, Tier 1 |
| Unseen scenarios, seeds, ablations, baseline comparison | 14.67/20 | Tier 1 |
| Keypad vs ordinary edit distance, incorrect suggestions | 7.0/10 | Tier 1 |
| Real impact, economic reasoning, assumed stop rates/time | 9.33/20 | Tier 2 |
| "Source code / UI not found", prove tests and parity | 8.0/15 | Tier 0, Tier 1 |
| Load time, low-end devices, concurrency, recovery | 8.0/15 | Tier 3 |
| Secure pre-transfer integration, API, data store | 5.67/10 | Tier 3 |
| Rural/older false positives, explainability, fairness | 3.33/5 | Tier 3 |
| Verified analyst permissions, anchored audit, federation threats | 3.33/5 | Tier 3 |
| Cross-division privacy-preserving graph/federated design | 5.67/10 | Tier 3 |
| Customer and complaint-handler validation | 15.67/20 | Tier 4 |
