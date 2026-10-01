# Video demonstration script (≈5 minutes)

The rulebook (§7.2) asks the video to show how the idea works, the features and AI components, and the real-life
impact. Record at 1440×900, browser zoom 100%, from the live URL (or `localhost:8000`).

| Time | Show | Say |
| --- | --- | --- |
| 0:00–0:30 | Home page | "One wrong digit, and a race against cash-out. In Bangladesh, a wrong-send can usually be recovered only while the money is still in the recipient's wallet." |
| 0:30–1:15 | Customer app → Rahim → *ভুল নম্বরে টাকা গেছে* → pick the ৳5,000 transfer → Bangla notice → submit | "Rahim picks the transfer and writes in Banglish. Before anything is processed he sees why we use his data, how long it is kept, who sees it, and that a return depends on the recipient's consent. He gets a case number and a 10-working-day deadline, as Bangladesh Bank requires." |
| 1:15–2:30 | Agent console → Rahim's case | "Ferot found the transfer, saw that he paid his brother's number eleven times and this one has the last two digits swapped. Genuine wrong-send, 82%. ৳4,200 is still in the wallet, but it will decay. The business rule recommends a temporary hold, capped at what is left, and a consent request to the recipient. Every panel says whether it is a fact, a prediction or generated text. Numbers are masked. I approve, and the hash-chained audit log records who did what." |
| 2:30–3:15 | Customer app → Shirin → submit → her case | "Shirin's words look the same. The ledger doesn't: a 23-day-old wallet that 14 other customers complained about, cashed out within minutes. Ferot says scam victim, routes it to the fraud team and the AML queue, and the message to the recipient is neutral, so nobody is tipped off." |
| 3:15–4:15 | Analyst & evidence | "Does the AI matter? Keyword rules score 0.55 and a text-only model 0.50; with the ledger, 0.96, and 0.90 on a scam type it never saw. In a queue simulation Ferot keeps 4.2% more money holdable than first-come-first-served; a perfect oracle reaches 6.7%. Here are the mule clusters and the monthly dispute report for Bangladesh Bank." |
| 4:15–4:45 | `docs/compliance.md` or the README | "It is built to 20 rules from upay's terms and Bangladesh law: no refund promises, no tipping off, human approval, consent, 6-year records, and no calls to upay systems. Synthetic data only." |
| 4:45–5:00 | Home page | "Next step: three months of anonymised disputes and four weeks of shadow mode." |

Checklist before recording: `Reset demo` as a supervisor; sign out between roles; close other tabs.
