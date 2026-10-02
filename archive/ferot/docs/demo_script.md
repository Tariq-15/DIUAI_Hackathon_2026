# Video demonstration script (≈5 minutes)

The rulebook (§7.2) asks the video to show how the idea works, the features and AI components, and the real-life
impact. Record at 1440×900, browser zoom 100%, from the live URL (or `localhost:8000`).

| Time | Show | Say |
| --- | --- | --- |
| 0:00–0:25 | Home page (let the complaint be read and the verdict appear) | "One wrong digit, and a race against cash-out. Ferot reads Rahim's Banglish complaint and, two seconds later, knows he swapped two digits of his brother's number." |
| 0:25–1:00 | Customer app → Send money → Rahim → *যে লেনদেনটি ভুল হয়েছিল* → Next | "Better still, stop it before it happens. Ferot Guard sees that this number is one keypad slip from the one Rahim paid eleven times and asks, in Bangla, 'Did you mean…?'. One tap fixes it. His usual transfer gets no warning at all: fewer than one ordinary transfer in a hundred is interrupted." |
| 1:00–1:20 | Shirin → Next | "Shirin is about to 'return' money to a caller. The wallet is 23 days old and 14 people reported it. Guard shows why, and *Send anyway* waits 30 seconds. It never blocks; she decides." |
| 1:20–1:50 | Customer app → Report a problem → Rahim → *ভুল নম্বরে টাকা গেছে* → pick the ৳5,000 transfer → Bangla notice → submit | "Rahim picks the transfer and writes in Banglish. Before anything is processed he sees why we use his data, how long it is kept, who sees it, and that a return depends on the recipient's consent. He gets a case number and a 10-working-day deadline, as Bangladesh Bank requires." |
| 1:50–3:00 | Agent console → Rahim's case | "The dark strip shows where the ৳5,000 is: ৳800 paid out, ৳4,200 still holdable, and the dashed line is what the model expects if nobody acts. Genuine wrong-send, 82%, and here is why. The business rule recommends a temporary hold, capped at what is left, and a consent request to the recipient. Every panel says whether it is a fact, a prediction or generated text. Numbers are masked. I approve, and the hash-chained audit log records who did what." |
| 3:00–3:40 | Customer app → Shirin → submit → her case | "Shirin's words look the same. The ledger doesn't: the ring graph shows 14 other victims around a 23-day-old wallet, cashed out at an agent within seven minutes. Ferot says scam victim, routes it to the fraud team and the AML queue, and the message to the recipient is neutral, so nobody is tipped off." |
| 3:40–4:30 | Evidence | "Does the AI matter? Keyword rules score 0.55, with the ledger 0.96. At our hold threshold we catch 85% of scams with no false holds. We publish where it fails: phone complaints are 3.8 points less accurate, and Guard warns USSD users a little more often. In the queue simulation Ferot keeps 4.2% more money holdable; a simple largest-first rule does about as well, so we say so." |
| 4:30–4:50 | `docs/compliance.md` or the README | "It is built to 20 rules from upay's terms and Bangladesh law: no refund promises, no tipping off, human approval, consent, 6-year records, and no calls to upay systems. Synthetic data only." |
| 4:50–5:00 | Home page | "Next step: three months of anonymised disputes and four weeks of shadow mode." |

Checklist before recording: `Reset demo` as a supervisor; sign out between roles; close other tabs.
