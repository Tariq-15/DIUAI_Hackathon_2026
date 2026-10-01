# Error analysis (M4 case classifier, held-out test window)

Test window: days 75–90 of the synthetic ledger, 335 cases, clean labels (training used 5% noisy labels).
Result: **11 errors out of 335** (macro-F1 0.96). All 11 are scam victims.

| Case | Variant | Predicted | Confidence | What happened |
| --- | --- | --- | --- | --- |
| FC-00965 | prize | genuine wrong-send | 0.47 | Quick complaint (≈10 min), receiving wallet had only 2 senders that week |
| FC-00967 | job offer (unseen type) | double recovery | 0.57 | Victim had filed an earlier claim; repeat victims look like repeat claimants |
| FC-00973 | fake SMS | genuine wrong-send | 0.50 | Mule ring quiet that week (1 sender in 7 days) |
| FC-00986 | job offer (unseen type) | double recovery | 0.41 | Two earlier claims by the same victim |
| FC-00997 | impersonation | double recovery | 0.34 | Low-activity mule wallet |
| FC-01004 | impersonation | double recovery | 0.39 | Three earlier claims by the victim |
| FC-01005 | prize | false claim | **0.73** | Late complaint (≈2 days) after an earlier claim |
| FC-01009 | impersonation | genuine wrong-send | 0.66 | Only 2 earlier complaints about the wallet |
| FC-01010 | impersonation | double recovery | 0.41 | Low-activity mule wallet |
| FC-01013 | fake SMS | double recovery | 0.41 | "Returned the money" in the text, like a double-recovery story |
| FC-01031 | prize | technical failure | 0.28 | Weak signals everywhere |

## Patterns

1. **Quiet mule wallets.** When a ring had few victims in the past 7 days, the graph features are weak and scams
   can look like typos. Mitigation for a pilot: longer look-back windows and links between ring members.
2. **Repeat victims look like repeat claimants.** `claimant_prior_claims` helps catch double-recovery fraud but
   hurts people who are scammed more than once. A pilot should separate "earlier claims upheld" from "earlier
   claims rejected".
3. **The safety net works.** 10 of 11 errors have confidence below the policy thresholds (0.6–0.8), so the
   recommendation falls back to `R-LOW-01` ("ask for more information"), not a wrong action. The one confident
   error (FC-01005, 0.73) would recommend a rejection, which **needs a supervisor** (rule R6) and is never
   automatic.

## Fairness

`reports/metrics.json` → `fairness` slices the test cases by language, channel, age band, area and KYC level.
The largest accuracy gap is by channel: app complaints 98.4%, phone complaints 94.6%. Phone complaints describe the
transfer less exactly, so the matcher and the classifier have less to go on. Mitigation: on calls, the agent
confirms the TrxID before deciding; the queue shows the channel on every row. Scam recall is lower for phone
complaints (81.4%), limited-KYC customers (80.0%) and ages 25–34 (78.3%) than overall (87.6%). These groups are
small (88–148 cases), so the gaps are noisy, but a pilot should track them first.

## Ferot Guard

- **False warnings fall unevenly.** USSD users get 0.78 false warnings per 100 ordinary transfers, app users 0.34.
  We have not yet traced the cause. Both rates are low; a pilot should watch this slice first.
- **Too clean to trust as is.** PR-AUC 0.997 reflects synthetic scam drop wallets with planted patterns. Real mule
  wallets borrow history and look ordinary; expect lower recall.
- **The typo check fires on its own.** Rahim's transfer has a scam risk of 20 (allow) but is warned because the
  number is one keypad slip from his brother's. This is intended, and the evidence page says so.

## Other known limitations

- **Synthetic data.** Patterns are planted by `datagen`; real data will be noisier. The scores show the method,
  not real-world accuracy.
- **Text cues can lower confidence.** In the injection suite, 2 of 30 attack strings (mentioning "call" or a
  "failed" transfer) moved a genuine case to "ask for more information". They never increase a hold.
- **Queue ordering gain is modest.** Ferot's ordering recovers +4.2% vs first-come-first-served, level with the
  simple "largest amount first" heuristic; the oracle ceiling is +6.7% on this data.
- **Extraction on templates is easy.** M1 scores 100% on generated complaints; the 24 hand-written complaints in
  `backend/tests/data` are the more honest check (all pass).
- **Holidays.** Lunar-calendar public holidays must be added each year from the government notification.
