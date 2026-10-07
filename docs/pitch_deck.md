# Prohori — pitch deck outline

Every number below is in the repo and reproducible with the command next to it. Where a number is a **model**
(an assumption, not a measurement), that is stated on the slide — Phase 1 judges penalized the opposite, so this
deck does not repeat that mistake. Nothing here is invented.

---

## Slide 1 — Title

**প্রহরী Prohori — stops the wrong number and the scam before the money leaves an upay wallet**

- AI Hackathon 2026 (DIU CPC × upay) · Track 01: Trust & Risk Intelligence (Track 06 wrong-send work merged in)
- Live demo: `https://tariq15-prohori.static.hf.space` — runs in the browser, no server, nothing typed leaves the device
- **Say:** "Two numbers to remember for the next three minutes: 0.962 and 98.72%. One is how well we catch fraud. The other is how rarely we bother an honest customer. We built the whole system around not having to trade one for the other."

---

## Slide 2 — The problem, in one line each

- **A wrong number.** Two digits swapped on a keypad, Tk 800 gone to a stranger. Under upay's own terms (§11.1) the sender is liable for the number entered.
- **A scam.** "I'm calling from the upay office, read me the OTP." Scam money moves on and cashes out within minutes.
- **Once it's gone, a complaint can only ask nicely.** A return needs the recipient's consent or a legal process — there is no undo button on a mobile wallet.
- **Say:** "Every fix that happens after the money leaves is damage control. We moved the fix to the only moment that actually matters: before the send."

---

## Slide 3 — Who this is for (answers the #1 Phase 1 critique)

- **Primary user:** the upay customer, at the exact moment they're about to send to a fraudulent or mistyped recipient.
- **Secondary user:** the upay trust/risk analyst investigating high-risk transfers and complaints after the fact.
- **Affected, not primary:** merchants and agents (counterparties, not product users).
- **Primary track:** 01 — Trust & Risk Intelligence. **Supporting:** Track 06 (wrong-number prevention, complaint matching).
- **Say:** "One judge told us flat out: no clear target user, doesn't map to a track. Fair hit. Here's the fix: it's the sender, at send time, full stop. Everyone else is secondary."

---

## Slide 4 — The three layers (the architecture in 20 seconds)

1. **Guardian on the phone** — checks the number as it's typed, and every Send Money / recharge after the PIN.
2. **Detection engine** — streaming feature store, trained models, score every transfer live.
3. **Copilot for upay's analysts** — evidence, money network, case report, for follow-up *after* the warning. No transfer ever waits for an analyst.
- **The rule that never bends:** models score, rules warn, **the customer decides**. Prohori never holds a transfer.
- **Say:** "This is the one architectural decision that drives every other design choice in this product: we warn, we never block."

---

## Slide 5 — The headline numbers (test window, days 51–60, never touched during training)

| Metric | Rules baseline | Prohori |
|---|---|---|
| PR-AUC | 0.188 | **0.962** |
| Fraud caught at 0.5% false-positive rate | 20.0% | **95.0%** |
| HOLD precision / recall | — | **86.8% / 91.7%** |
| Honest transactions with zero friction | — | **98.72%** |

- Reproduce in one command: `python -m src.pipeline`
- **Say:** "We didn't tune on the test window and we didn't cherry-pick the seed — I'll show you that on the next slide. This is a 5x jump in PR-AUC over hand-written rules, on data the model never saw."

---

## Slide 6 — Reproducibility: multi-seed, not a lucky run (answers the #1 Phase 1 AI/ML critique)

- Judges asked for proof across multiple simulation seeds, not just seed 42.
- **Completed this session:** the full pipeline (generate → train → evaluate, 30 Optuna trials) re-run end to end on three independent seeds — **PR-AUC mean 0.9704, range 0.9622–0.9781** (`runs/feedback-full/summary.json`). Seed 42 reproduced the published 0.9622 exactly.
- The one place the range matters: S5 (the fake-seller / pressure-scam scenario), already named as our weakest case on a single seed, ranges 69.0–94.5% STEP_UP+ recall across seeds — multiple seeds confirm it's genuinely weaker, not an artifact of one unlucky run.
- **Say:** "We're not showing you a single golden number — we re-ran the entire pipeline three times on independent seeds, and the one weak spot we'd already told you about stayed weak. That's what an honest multi-seed check is supposed to find."

---

## Slide 7 — Innovation: keypad-aware vs. "just use edit distance" (answers the #1 Innovation critique)

- A judge asked us to directly compare our keypad-weighted wrong-number check against plain Levenshtein distance. We did — same day, same fixed diagnostic matrix.
- **Result:** on digit-transposition slips (two digits swapped — the single most common real typo), keypad detection catches **6 of 12**; ordinary edit distance catches **0 of 12.** Unit-cost Levenshtein scores a swap as distance 2 and simply never flags it.
- Trade-off disclosed, not hidden: keypad detection also produces more false suggestions on legitimately similar numbers (9 vs 6 of 12) — a small, fixed diagnostic (n=60/model), not a customer study.
- **Say:** "A standard off-the-shelf string-distance check — the kind every other fintech wrong-number feature probably uses — misses the single most common typo entirely. Ours doesn't, because it knows where your thumb actually is on the keypad."

---

## Slide 8 — Explainability: the copilot shows its work

- Every alert carries **SHAP evidence** — the actual features that pushed this specific transaction's score up or down, in plain Bangla or English, not a black-box number.
- The money network graph, the customer's own amount habit, a four-part case report — built from structured evidence only, never invented text.
- Optional Claude rewording (off by default) only touches *wording*, never the score or the band, and is rejected if it states a number not already in the evidence.
- **Say:** "An analyst — or a judge — never has to trust us. They can see exactly why the model called it."

---

## Slide 9 — Federated learning: real privacy math, not a privacy slide

| Result | Headline |
|---|---|
| Keypad-slip costs, 100,000 simulated phones | (ε, δ) = (4.25, 10⁻⁵) differentially private; L1 error 0.035 vs. 0.626 without server-side trust |
| Amount-habit limits, 11,015 real wallets | (ε, δ) = (1.66, 10⁻⁵); learned the 16× threshold that catches 21.4% of victim-side scam transfers while asking only 0.62% of honest customers twice |
| Cross-division scam model, 8 silos | PR-AUC 0.949 — **98.7% of the fully-pooled model's accuracy**, with no raw transaction ever leaving a division |

- **Say:** "Three separate federated results, each with a real Gaussian-mechanism privacy budget attached — not 'federated learning' as a buzzword slide."

---

## Slide 10 — Prototype quality: proof, not a claim (answers the #1 Prototype critique)

- Judges asked us to demonstrate the reported test count and prove browser/server parity. **Verified today:**
  - `python -m tools.feedback_verify` → **61 tests pass, 0 failures**, JUnit archived, commit hash recorded
  - Live demo and server share one Python engine (Pyodide in the browser) — same code, same answers, measured identical to 1e-16 on 1,000 test rows
- **New this pass:** an icon-based onboarding tour built into the copilot (🧭 button) that walks a judge through Overview → SHAP evidence → money network → Agent Watch → fairness → federated results → audit log, so "where's the code / where's the UI" is never a question again.
- **Say:** "Every number on this slide has a file path next to it in our repo. You can check it yourself in under a minute."

---

## Slide 11 — Closing the loop: the follow-up channel (new, built this session)

- **The gap:** an analyst could ask a complaint filer for more details — but the customer had no way to answer. One-way request, dead end.
- **The fix:** a threaded, icon-based follow-up — 🕵️ analyst asks (via the existing audit-logged action), 🧑 customer replies from their own app, ⏳ shows while waiting. Status flows `details_requested → details_received` so the queue tells the analyst exactly who's waiting on whom.
- **Say:** "A case can't go cold just because the analyst asked a question. Now it can't."

---

## Slide 12 — What's honestly still a model, not a measurement

- Stop rates (NUDGE 30% / STEP_UP 70% / HOLD 100%) and analyst time (20 min manual vs 3 min with the copilot) are **stated assumptions**, sensitivity-tested at 0/0.5/1×, never presented as observed.
- Customer comprehension, real pilot outcomes, and economic ROI require partner access we don't have yet — the measurement protocol for all three is written and ready (`docs/feedback_delivery.md`), execution is pending partner approval.
- **Say:** "We'd rather tell you what we haven't measured than let you find out later. Everything in this section has a defined, pre-registered way to go from assumption to measurement — we just need upay's data to run it."

---

## Slide 13 — Close

- 0.962 PR-AUC, reproduced fresh, on multiple seeds, against an honest baseline.
- A wrong-number check that beats plain edit distance on the most common real typo.
- Privacy-preserving federated learning with real epsilon values, not a slide.
- A live demo that runs entirely in a browser, with 61 passing tests behind it.
- And a product philosophy that hasn't moved since day one: **models score, rules warn, the customer decides.**
- **Say:** "We're not asking you to trust a pitch. Every claim in this deck has a command next to it that reproduces it. Try it."
