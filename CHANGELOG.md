# Changelog

What changed in Ferot, newest first. All results are on synthetic data (held-out test window, days 75–90).

## 0.2.0 — 1 October 2026: Ferot Guard and the redesign

### Added
- **Ferot Guard, a check before the money leaves.** While the customer is on the confirm screen, Guard scores the
  transfer and warns in plain Bangla or English. It never blocks: the customer always decides.
  - "Did you mean 01012345678?" when the number is one keypad slip from a contact the customer pays often, with a
    one-tap fix.
  - Scam warning with grounded reasons (new wallet, other customers reported it, money usually cashed out fast,
    first transfer to this number, unusually large amount). The riskiest transfers get a 30-second pause.
  - Model: LightGBM P(scam) fused with an IsolationForest anomaly score; warn and pause bands set at the 99th and
    99.9th percentile of ordinary transfers in validation.
  - API: `POST /api/v1/guard/check`, `POST /api/v1/guard/{id}/decision`, `GET /api/v1/guard/alerts` (numbers masked).
  - Results: 98.8% of scam transfers warned, 0.44 ordinary transfers in 100 interrupted, every typo caught.
- **Four-part case report** on every case: what happened, what the evidence says, next step, limits.
- **Receiving-wallet network** (`GET /api/v1/cases/{id}/network`): other complainants and where the money went
  in the 30 days before the complaint.
- **Holdable-money series** from the ledger, from the transfer to the complaint, for the case view's chart.
- **Fairness report**: accuracy, scam recall and wrongful rejections by language, channel, age, area and KYC level;
  Guard false warnings by channel, age and area.
- **Alerting metrics**: scam PR-AUC, precision and recall at the policy threshold, false alarms, wrongful
  rejections, with a note when scores look too clean.
- **Plain-sentence reasons**: every model reason now reads as a sentence ("The receiving wallet is 23 days old.").
- 8 new tests (117 in total).

### Changed
- **Scam holds start at P(scam) 0.45, down from 0.60.** Scam recall at the policy threshold rose from 0.70 to 0.85;
  precision stayed at 1.00.
- **Every web page redesigned.**
  - Palette: ink, paper, flag green for money that can come back, signal red for money leaving, turmeric for
    estimates. Fonts: Anek Bangla and Hind Siliguri.
  - Home: the demo complaint is read on screen, then Ferot's verdict appears.
  - Customer app: Send money with Guard, plus the existing report flow, in a phone mock with Bangla digits.
  - Agent console: ledger-style queue with money at risk, deadlines and a summary strip.
  - Case view: the "taka drain" (money still holdable, ledger facts then the model estimate), report, reasons,
    the ring around the receiving wallet, drafts, decision and audit trail.
  - Evidence page: alerting metrics, confusion matrix, queue simulation with 95% intervals, fairness, Brier scores.
  - Every panel is labelled as a ledger fact, model estimate, drafted text or policy rule; keyboard focus, reduced
    motion and phone layouts throughout.
- Graphs are plain SVG; React Flow was removed. The web bundle went from 449 KB to 336 KB (140 KB to 100 KB
  gzipped).
- The Docker image uses about 410 MB with the Guard model, still within a 512 MB host.

### Fixed
- The case report said the at-risk amount would leave "within a day"; it is the expected loss if the case waits
  2 hours, and the text now reads that from config.
- Chart labels no longer collide on phone screens.

### Known limits
- Synthetic scam patterns are cleaner than real fraud, so some scores sit near 1.0.
- Phone complaints are 3.8 points less accurate than app complaints.
- Guard warns USSD users more often than app users (0.78 vs 0.34 per 100 ordinary transfers).
- Ferot's queue order recovers about as much as a simple largest-amount-first rule.

## 0.1.0 — 1 October 2026: first complete build

- Synthetic 90-day ledger with planted disputes of five types, respecting upay's published limits; 010 numbers only.
- M1 complaint extraction for Bangla, Banglish and English (rules first, optional Claude on masked text).
- M2 transaction matching and M3 intended-number matching with keypad-weighted distance.
- M4 case classifier with TreeSHAP reasons; M5 recoverability curve; M6 queue priority with the 10-working-day floor.
- M7 mule clusters for the AML team; M8 drafted replies with grounding, no-refund-promise and no-tipping-off checks.
- Policy engine with versioned rules, hold cap, supervisor approvals and cited mock procedures.
- SQLite case store, AML queue and hash-chained audit log.
- FastAPI with role checks, consent, export on a verified request and audit verification.
- Customer app, agent console and analyst view.
- Queue simulation against first-come-first-served, largest-first and an oracle ceiling.
- 109 tests, including a 30-attack prompt-injection suite; CI with tests, web build and secret scanning; Dockerfile
  and Render blueprint.
- Compliance mapping of 20 design rules, project report, model cards, error analysis, on-site playbook and demo
  script.
