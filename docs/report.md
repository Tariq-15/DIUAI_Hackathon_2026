# Ferot — Project Report

AI Hackathon 2026 (AI DEV FEST, DIU CPC × upay) · Track 06: Operations & Service Intelligence
Repository: https://github.com/Tariq-15/DIUAI_Hackathon_2026 · Prototype on synthetic data · Not an upay product

## 1. Problem

"I sent money to the wrong number" is one of the most common and distressing MFS complaints in Bangladesh;
Bangladesh Bank itself notes that one wrong digit sends money to the wrong account. Recovery today is manual and
slow, and it is a race: money can usually be held only while it is still in the recipient's wallet.

The same complaint words hide five different situations: a genuine typo, a scam victim tricked into sending, a
fraudster trying to be paid twice ("double recovery"), a customer who regrets a deliberate payment, and a technical
failure. Each needs a different path. Under upay's Terms (§11.1) the sender is responsible for the number entered,
so recovery is a service, not a liability, but Bangladesh Bank requires every dispute to be logged and resolved
within 10 working days (MFS Regulations 2022 §17.3).

**Users:** support agents (primary), customers who lost money, risk/AML analysts, supervisors and compliance.

## 2. Proposed idea

Ferot (ফেরত, "money back") is a decision-support copilot for the dispute desk. It turns a free-text complaint into
an explained case file in about a second, ranks the queue by taka at risk if a case waits, and recommends the
next step under upay-owned business rules. Humans approve every action; Ferot never moves money.

Problem statement: *For upay customers who send money to the wrong number or are tricked into sending it, slow
manual dispute handling lets the money be cashed out before anyone acts. Ferot uses complaint text and the
transaction ledger to classify each case, rank the queue by recoverable money at risk and recommend the next
action, measured by recovery, time-to-action and handling time.*

## 3. Implemented solution

- **Ferot Guard (before sending):** while the customer is on the confirm screen, a LightGBM scam model and an
  anomaly score check the receiving wallet, and a keypad check catches likely typos ("Did you mean…?"). Warnings
  are in plain Bangla with reasons; the riskiest transfers get a 30-second pause. The customer always decides.
- **Customer app (Bangla/English):** pick the transfer, describe it, read a consent notice (purpose, retention,
  who sees it, how to withdraw) and the customer's responsibilities, get a case number, a 10-working-day deadline
  and the route to Bangladesh Bank; contest an outcome for a human-only review.
- **Agent console:** queue sorted by taka at risk with deadlines; case file with the "taka drain" (money still
  holdable from the transfer to the complaint, then the model's estimate), a four-part case report (what happened,
  why, next step, limits), the ring of complainants and cash-out agents around the receiving wallet, extracted
  fields, ledger facts, intended-number diff, class probabilities with TreeSHAP reasons,
  rule-based recommendation with the cited procedure, editable drafts, approve / edit / override, masked numbers
  with logged reveals, export for compliance, and a hash-chained audit trail.
- **Evidence view:** alerting metrics, confusion matrix, baselines, queue simulation, fairness by customer group,
  mule clusters, AML queue, Guard warnings and a monthly dispute report for Bangladesh Bank (§16.3).
- **Engineering:** FastAPI + React, one Docker image, 117 automated tests, CI with secret scanning.

## 4. Key features and AI approach

| Component | Approach | Result (synthetic test window) |
| --- | --- | --- |
| Ferot Guard | LightGBM P(scam) + IsolationForest, bands from validation percentiles; keypad typo check | 98.8% of scam sends warned; 0.44 ordinary sends in 100 interrupted; all typos caught |
| M1 extraction | Rules (Bangla digits, number words, patterns) + optional Claude on masked text, fixed JSON schema | 24/24 hand-written complaints |
| M2 matching | Score claimant's recent transfers | top-1 0.95 |
| M3 intended number | Keypad-weighted edit distance over sender history | 0.98 on genuine typos |
| M4 case type | LightGBM on ledger, graph and text features; TreeSHAP reasons | macro-F1 0.96 vs 0.55 keyword, 0.50 text-only; scams held at P ≥ 0.45: recall 0.85, precision 1.00 |
| M5 recoverability | LightGBM per horizon (1–72 h) | Brier 0.072 vs 0.099 baseline (6 h) |
| M6 priority | Taka lost by waiting + vulnerability + SLA floor | +4.2% holdable money vs first-come-first-served |
| M7 clusters | Wallets named by many complainants, linked by transfers | Leads for the AML team |
| M8 drafts | Templates with code-filled numbers; optional LLM polish; three automatic checks | 0 refund promises, 0 tipping off |

**Data.** A seeded generator builds a 90-day ledger (≈317,000 transactions, ≈5,000 wallets) that respects upay's
published limits, with 1,600 planted disputes across five types, realistic ambiguity (first-time payees,
accomplice returns, sparse histories), 5% label noise, a time-based split and a scam type held out of training.
All phone numbers use the unassigned 010 prefix.

**Responsible AI.** ML and rules decide; the LLM only reads text in and polishes text out, on masked input. A named
human approves every money action; rejections need a supervisor. Numbers are masked; reveals are logged. Drafts
never promise refunds and never tip off anyone under AML review. 30 prompt-injection attacks cannot raise a hold.

**Compliance.** 20 design rules from upay's Terms and Privacy Policy, Bangladesh Bank's MFS Regulations 2022 and
ICT Security Guideline, the Money Laundering Prevention Act 2012 and the Personal Data Protection Ordinance 2025,
each traced to code and a test (`docs/compliance.md`).

## 5. Real-life impact

- **Fewer wrong sends in the first place:** a "Did you mean" prompt at the confirm screen stops the most common
  mistake before any dispute exists, at a cost of under one interruption per 100 ordinary transfers.
- **More money recovered:** ranking by money at risk keeps more of it holdable when an agent acts (+4.2% in
  simulation, 95% CI 3.8–4.6%; the perfect-foresight ceiling is +6.7%).
- **Faster, consistent handling:** a pre-built case file and drafted Bangla replies replace manual look-ups.
- **Fewer wrongful outcomes:** double-recovery and false claims are flagged with ledger evidence, protecting innocent
  recipients.
- **Fraud intelligence:** complaints become mule-wallet leads for the AML/CFT team.
- **Regulatory fit:** SLA timer, dispute log, 6-year records and the §16.3 report come built in.

Honest limits: synthetic data with a cleaner scam pattern than real fraud; ordering alone performs like a
"largest-first" rule; phone complaints are 3.8 points less accurate than app complaints; Guard warns USSD users
about twice as often as app users. See `docs/error_analysis.md`.

## 6. Next steps

1. Technical and business review with upay; fill the value formula with upay's own volumes and costs.
2. Retrain on 3–6 months of anonymised disputes inside upay's environment (data stays in Bangladesh).
3. Four weeks of shadow mode: measure agreement with agents and the money that would have been held.
4. Randomised pilot with one team; go/no-go on recovery, time-to-action, overrides and fairness.
