# Prohori (প্রহরী): upay scam and wrong-number shield

AI Hackathon 2026 (DIU CPC × upay) · **Track 01: Trust & Risk Intelligence**, with our Track 06 work merged in.
**Prototype on synthetic data. Not an upay product; the wallet screens are an upay-style mock.**

**Live demo: https://tariq15-prohori.static.hf.space**. The trained models run inside your browser, with no server.
The first visit downloads about 50 MB and takes about 15 s to start; later visits load from the cache.
Bangla ⇄ English switch on every screen; works on a phone (390 px) as well as a laptop.

Prohori protects a customer's money **before it leaves the wallet**, and helps get it back when it already has:

1. **Wrong number, caught while typing.** "আপনি কি মা-কে পাঠাতে চেয়েছিলেন?" Prohori compares the number with the
   people this customer pays often and shows **which contact was meant and which digits are wrong** (for example
   "digits 10 and 11 are swapped: you typed 75 instead of 57"). One tap sends to the right number instead.
2. **Scam, caught before the PIN goes through.** Every Send Money is scored live (LightGBM + Isolation Forest +
   graph rules, four bands ALLOW / NUDGE / STEP-UP / HOLD), with the reasons in plain Bangla or English.
3. **Already sent? Report it in your own words.** Bangla, Banglish or English ("Bhai ajke bhul kore 800 taka onno
   number e chole gese…"). Rules read the amount, number and time, match the transfer, decide whether it looks like a
   keypad slip or a scam, and open a case with the legal 10-working-day deadline.
4. **Investigation copilot for upay's analysts.** Live queue, SHAP evidence, the money network, a four-part case
   report, and actions (freeze, hold the disputed amount, ask the recipient for consent) that need a person's name.
5. **Federated learning, so the data stays where it is.** The typing-slip pattern behind check 1 is learned on
   phones that never send their contacts or slips; the scam model can be trained across upay's eight divisions
   without pooling a single transaction.

Models score, rules decide, people approve.

```
python -m src.pipeline          # generate -> validate T1-T14 -> features -> train -> Agent Watch -> evaluate -> export -> demo world
python -m src.fl.ondevice       # federated: learn keypad-slip costs on (simulated) phones
python -m src.fl.fedgbdt        # federated: train the scam model across 8 divisions
uvicorn src.serve.api:app       # open http://localhost:8000  (customer app + analyst copilot side by side)
```

## What is in this repository

| Path | What |
|---|---|
| `/` (root) | **Prohori, the merged project**: data generator, feature store, models, evaluation, federated learning, risk API, upay-style app, analyst copilot, static in-browser build |
| `archive/ferot/` | **Ferot**, our Track 06 prototype (wrong-send and dispute copilot). Its two best ideas, the keypad-slip "Did you mean…?" check and the Banglish complaint reader, now live in Prohori (`src/serve/recipient.py`, `src/serve/complaints.py`). The original, with its React agent console, 121 tests and the team's upay-style app clone (`archive/ferot/upay frontend clone/`), still runs from that folder |
| `docs/prohori-plan.md` | the team's implementation plan for Prohori |

## 0. The product (what judges click)

The three layers of the Track 01 playbook, all on the trained models, plus the merged Track 06 flows:

| Layer | Where | What it does |
|---|---|---|
| 1. Pre-Transaction Guardian | `ui/app.html`, upay-style phone | **As the number is typed:** known contact ✓, new number, no wallet, or "Did you mean মা (01076-254257)?" with the wrong digits marked. **After the PIN:** Prohori scores the transfer. **ALLOW** goes through. **NUDGE** asks a question with the evidence and a cancel default (for a likely slip: "Send to মা instead"). **STEP_UP** asks for the PIN again. **HOLD** pauses it for an analyst ("your money is still in your wallet"). 🔊 reads the warning aloud (the browser's own voice, no network). Also: **Report a problem** (Banglish complaints, consent never pre-ticked, case tracker) and an "Am I talking to a scammer?" checker |
| 2. Detection engine | `src/serve/live.py` + the trained bundle | The same streaming feature store, LightGBM, Isolation Forest, graph rules and four-band policy used in evaluation, plus the keypad-slip check with federated costs. Nothing is pre-recorded: every transfer is scored when it is sent |
| 3. Investigation copilot | `ui/analyst.html` | Live queue (pre-send alerts and complaints; filters for complaints and wrong numbers), SHAP evidence, the money network, the digit diff for wrong numbers, the customer's own words for complaints, a four-part case report, actions that need an analyst's name. Tabs: Agent Watch, model and fairness, **federated learning and privacy**, hash-chained audit log |

`ui/index.html` shows the phone and the copilot side by side with the demo script along the top (on a phone it
shows one at a time with a Phone / Copilot switch). The **বাং | EN** switch changes both screens at once.

**How the live demo world is made.** The API loads the feature store replayed to the end of the 60 days and moves
the clock to 09:30 the next morning. It then *stages* scenarios as ordinary synthetic events in the same store the
model reads:
- a collector wallet opened 2 days ago, paid by 14 strangers in the last 3 hours, part cashed out at agent A00044
  (the SC-06 rogue agent);
- a SIM-swap takeover of Salma's account (SIM replaced, a "gang phone" linked to three young wallets logs in,
  PIN reset);
- a fake online seller paid by six first-time buyers, one of whom already reported it to 16268;
- a stranger's wallet whose number is Rahim's mother's number with the last two digits swapped.

Then the real model scores whatever the app sends:

| Demo transfer | Band (live) | Main evidence shown to the customer |
|---|---|---|
| Rahim → his mother, Tk 800 | ALLOW | (none) |
| Rahim → his mother's number with two digits swapped, Tk 800 | NUDGE (`possible_wrong_recipient`) | "Did you mean মা (01076254257)? You have sent there 14 times; digits 10 and 11 are swapped: you typed 75 instead of 57" + one-tap "Send to মা" |
| Rahim → a new number someone gave him, Tk 6,000 (found by rule: an ordinary wallet the model puts in NUDGE/STEP_UP) | NUDGE | amount vs his largest, first transfer to the number |
| Rahim → collector, Tk 15,000 ("job deposit") | HOLD 100 | 14 different people paid this number in 24 h; fast money-movement ring; opened 2 days ago |
| Rahim → fake seller, Tk 4,500 | HOLD | reported to 16268; opened 20 days ago; 6 different payers |
| Salma's account from the gang phone, Tk 50,000 | HOLD 100 | new phone 0.7 h ago; recipient 9 days old; 2.1× her largest transfer |

If Rahim sends to the swapped number anyway, "Report a problem" with *"Bhai ajke bhul kore 800 taka onno number e
chole gese, number er sesh 4 digit 4275"* reads amount Tk 800, number ending 4275, today; matches transfer TL-xxxx
(confidence 0.94); types the case **genuine wrong send (keypad slip)**; recommends **hold the disputed amount**
(capped at what the receiving wallet still holds) and **ask the recipient for consent**; and sets the deadline 10
working days ahead (Friday and Saturday excluded). A scam complaint is typed **likely scam victim** instead.

The analyst queue also holds the planted test-window cases (SC-01 to SC-08, SB look-alikes) and the final test
day's STEP_UP/HOLD alerts, re-scored by the bundle with their real money networks. It includes false alarms,
labelled with the synthetic ground truth so judges can see both kinds.

**Rules that keep people in control** (plain code, `src/serve/live.py`, `copilot.py`):
- The customer cancels or confirms NUDGE/STEP_UP warnings. A HOLD cannot be pushed through by the customer;
  only an analyst can release it. A likely keypad slip always gets a one-tap check, even when the model says ALLOW.
- Recommended actions come from a fixed list (freeze recipient, verify owner, contact senders, review agent,
  release, watchlist, dismiss, hold disputed amount, ask recipient consent, ask customer details), picked by rules.
  Every action needs an analyst name; a dismissal needs a reason.
- An analyst's freeze becomes policy: any later transfer to that wallet is held (`recipient_frozen_by_analyst`).
- A complaint needs explicit consent (never pre-ticked). A hold is never more than the disputed amount or what the
  wallet holds. Nothing promises a refund: upay's terms make the sender responsible for the number entered, and a
  return needs the recipient's consent or a legal process. The customer is told how to escalate to Bangladesh Bank.
- Every model alert, customer choice, complaint and analyst action goes into a SHA-256 hash-chained audit log
  (`GET /api/v1/audit` verifies it).
- The case report is a template filled only from structured evidence. Optionally (`PROHORI_LLM=anthropic` +
  `ANTHROPIC_API_KEY`), Claude (`claude-opus-5-5`) may reword it. It sees structured facts only, never a
  customer's own words, and its text is rejected if it contains any number not in the evidence. It is off by
  default, so the demo runs with no internet.
- Complaint text and scam-check text are read by transparent rules, never by a language model.

API (stable contract `POST /api/v1/risk-score`):

| Endpoint | Purpose |
|---|---|
| `POST /api/v1/risk-score` | `{customer \| sender_id, to, amount, device_id?}` → band, score, Bangla/English reasons and message, allowed choices, `suggestion` (the contact probably meant, with the wrong digits) |
| `POST /api/v1/recipient-check` | as the number is typed: does a wallet use it, is it a known contact, or one slip from one |
| `POST /api/v1/alerts/{id}/decision` | customer: `cancel` / `confirm` / `confirm_pin` / `use_suggested` |
| `GET /api/v1/transfers/{id}` | customer's view of a warned transfer (status only) |
| `GET /api/v1/customers/{key}/transfers` | the customer's own last 7 days, for "which transfer?" |
| `POST /api/v1/complaints/preview`, `POST /api/v1/complaints`, `GET /api/v1/complaints/{id}` | read the words back; file (consent required); the customer's case status |
| `GET /api/v1/alerts`, `GET /api/v1/alerts/{id}` | queue; case file with SHAP, network, report, trail (`?llm=1` to reword) |
| `POST /api/v1/alerts/{id}/action` | analyst action `{action, analyst, note}` |
| `GET /api/v1/agent-watch`, `/api/v1/model`, `/api/v1/audit` | panels (`/api/v1/model` includes both federated results) |
| `POST /api/v1/scam-check` | "Am I talking to a scammer?" (Bangla and English advice) |
| `GET /api/v1/customers`, `POST /api/v1/demo/reset` | demo customers and scenarios; restage the world |

One command, seed 42, about 15 minutes on a laptop CPU (about 3 minutes with `--trials 0`). No GPU, no real customer data.

## Federated learning: the data stays where it is

Both runs are simulations on synthetic data; the protocols and the arithmetic are real, and both results are
shown in the copilot's **Federated & privacy** tab.

**① On the phone: which digits people mistype** (`src/fl/ondevice.py`). When a customer taps "Send to মা instead",
the phone records one confirmed slip (digit meant → digit typed, or two digits swapped). Phones never send those
events. Each round, a phone sends one 101-number count vector with its share of Gaussian noise, masked with
pairwise ring masks (integers mod 2⁶⁴), so the server sees only the sum over 1,000 phones. From the sums it learns
how likely each slip is and turns that into the edit costs the wrong-number check uses
(`artifacts/portable/slip_costs.json`).

| | Value |
|---|---|
| Simulated phones | 100,000; 6 rounds, half online each round, at most 2 slips reported per phone per round |
| Privacy | each group sum is (ε, δ) = (**4.25**, 10⁻⁵) differentially private over all 6 rounds (Gaussian mechanism, Rényi accounting) |
| Accuracy | L1 error vs the true slip pattern **0.035**; with the same ε but noise added only on each phone (no trust in the server) **0.626** |
| What it learned | neighbouring key costs 0.61, any other key 0.93 (Ferot's hand-set values were 0.6 and 1.0); swaps 35% of slips (true 35%) |
| Leaves the phone | one noisy, masked vector of 101 counts per round |
| Never leaves | contacts, numbers typed, the slips themselves |

**② Across divisions: the scam model without pooling transactions** (`src/fl/fedgbdt.py`). A horizontal federated
gradient-boosted tree model over 8 division silos: shared quantile sketches for the bins, then per tree level each
silo sends gradient/hessian/count histograms through secure aggregation (ring masks, mod 2⁶⁴); the server picks
splits from the sum only; early stopping on the summed validation loss. The result is written as a LightGBM text
model (largest difference from our own tree walk: 2.8e-14) and runs as a drop-in (`PROHORI_SCORER=federated`).

| Test window (days 51–60) | Central LightGBM (pooled data) | Federated GBDT (8 silos) |
|---|---|---|
| PR-AUC | 0.962 | **0.949** (98.7% of central) |
| ROC-AUC | 0.9985 | 0.9979 |
| Recall at 0.5% FPR | 95.0% | 94.6% |
| HOLD+ precision / recall | 86.8% / 91.7% | 85.0% / 88.0% |
| Planted scenarios in an acceptable band | 12 / 12 | 12 / 12 |

The live demo keeps the central model (higher HOLD recall); the federated one is one setting away. Limits, stated in
the tab too: features come from one feature store that sees all wallets (a real deployment needs privacy-preserving
cross-silo joins for counterparty and graph features); summed histograms are protected by secure aggregation but are
not differentially private; policy thresholds were fitted on the pooled validation window.

---

## 1. Quick start

```bash
python -m venv .venv && .venv/Scripts/activate        # Windows  (Linux/macOS: source .venv/bin/activate)
pip install -r requirements.txt -c constraints.txt      # constraints = the versions the committed models were built with

pytest                                                  # 50 tests, ~1 min (tiny world, product layer, wrong-number, complaints, FL)
uvicorn src.serve.api:app --port 8000                   # API + UI on the committed models: http://localhost:8000

python -m src.pipeline                                  # rebuild everything (Optuna 30 trials)
python -m src.pipeline --trials 0                       # fast: config params, no tuning
python -m src.pipeline --scale 0.1 --trials 0 --out-root runs/small     # ~1k customers, separate folder
python -m src.fl.ondevice && python -m src.fl.fedgbdt   # the two federated runs (~1 s and ~8 min)
```

Individual stages:

| Stage | Command | Output |
|---|---|---|
| Generate | `python -m src.datagen.generate [--scale 0.1] [--csv]` | `data/generated/*.parquet`, `data/sample/*.csv` |
| Validate | `python -m src.validation.run_checks [--skip-repro]` | `reports/data_validation.{md,json}` (exit 1 on failure) |
| Features | `python -m src.features.build` | `data/features/features.parquet` |
| Train | `python -m src.models.train [--trials 30]` | `artifacts/model_bundle.joblib`, `reports/metrics_val.json` |
| Agent Watch | `python -m src.agents.agent_watch` | `reports/agent_watch.json`, `data/features/agent_scores.parquet` |
| Evaluate | `python -m src.models.evaluate [--no-ablation]` | `reports/evaluation.md`, `metrics_test.json`, `model_card.md`, `fairness.csv`, `demo_scenarios.md`, `figures/` |
| Export | `python -m src.serve.export_state` | `artifacts/demo_state.joblib` (few MB, for deployment) |
| Demo world | `python -m src.serve.demo_world` | `artifacts/demo_world.joblib`: recent edges, historical alerts with networks, demo customers |
| FL on-device | `python -m src.fl.ondevice` | `artifacts/portable/slip_costs.json`, `reports/federated_ondevice.json` |
| FL cross-silo | `python -m src.fl.fedgbdt [--trees 1500]` | `artifacts/fed_serve_bundle.joblib`, `reports/federated_crosssilo.json` |
| Portable / static | `python -m src.serve.portable` · `python tools/build_static.py` | `artifacts/portable/` (incl. `federated.json`) · `site/` |

**Kaggle / Colab:** open `notebooks/00_kaggle_end_to_end.ipynb`, add this repo as a Kaggle Dataset (or set
`REPO_URL`), run all. Save `data/generated/` as a private Kaggle Dataset if you want to reuse it. Notebooks
01–06 walk through each stage with tables and charts and are committed with outputs.

## 2. Repository layout

```
config.yaml                 every synthetic assumption, limits, fraud volumes, model + policy settings (seed 42)
src/datagen/                world.py (entities) · normal.py (normal life) · engine.py (ledger) · fraud.py (S1-S8) · planted.py (SC/SB) · generate.py
src/validation/             checks.py (T1-T14) · run_checks.py
src/features/               store.py (streaming store) · graph.py (hourly graph) · spec.py (feature groups) · build.py
src/models/                 train.py · baselines.py · fusion.py (policy) · scoring.py · explain.py (SHAP -> Bangla/English reasons) · evaluate.py · metrics.py · plots.py
src/agents/agent_watch.py   rogue-agent peer z-scores + register-compromise test
src/fl/                     ondevice.py (slip costs, secure aggregation, DP) · fedgbdt.py (federated trees across 8 divisions) · summary.py
src/serve/                  scorer.py (online engine) · live.py (live world, alerts, complaints, audit) · recipient.py (wrong-number check) ·
                            complaints.py (Banglish complaint reader, transfer matching, SLA) · copilot.py (case reports) · scamcheck.py ·
                            api.py · browser.py (same routes inside the browser) · portable.py · demo_world.py · export_state.py
ui/                         index.html (showcase) · app.html/app.js (upay-style customer app) · analyst.html/analyst.js (copilot) ·
                            prohori.css/js (Bangla/English switch, shared helpers) · fonts/ (Noto Sans Bengali) · engine.js/pyworker.js (in-browser engine)
src/pipeline.py             one-command runner
tests/                      pytest: data invariants, leakage, policy, reason codes, mini training, product layer, wrong-number check, complaints, federated learning
tools/                      build_static.py · deploy_space.py · readme_results.py · build_report_pdf.py
notebooks/                  00 Kaggle end-to-end · 01 data · 02 features · 03 training · 04 test evaluation · 05 Agent Watch · 06 inference
docs/                       data_dictionary.md · spec_review_fixes.md · prohori-plan.md · Prohori_Work_Breakdown.pdf
data/sample/                ~20k-row sample (2 test days) + entity tables, committed
artifacts/, reports/        trained bundle, federated bundle, demo state, demo world, portable models; all metrics and figures from the seed-42 run
archive/ferot/              Track 06 prototype (see above)
```

## 3. The synthetic upay world

60 days, 10,000 base customers (+ legit signups during the window), 300 agents, 600 merchants, 12 billers,
48 areas in 8 divisions. About **680k transactions, 0.5% fraud**. Every row passes through a ledger that
enforces balances and KYC limits, so balances chain exactly and no successful row breaks a cap.

**Normal life:** salaries on days 1–5 (garment workers 5–10) followed by money sent home; Friday/Saturday
rhythm; Eid salami (small round transfers to many contacts); bills mid-month; recharges; cash-in/out at
agents only during shop hours; remittance families cashing out soon after money lands; customers who are
short walk to an agent, cash in, and retry.

**Legit look-alikes (so no single signal is a giveaway):** 14 new wallets a day; shared family and shop phones;
night owls; family "hub" wallets forwarding money within minutes; quick cash-outs after receiving;
f-commerce sellers paid by many first-time buyers; phone changes and SIM replacements followed by bigger
transfers; big one-off transfers to new recipients (rent, hospital); monthly 10–25k bank top-ups.

**Injected fraud, with ground truth on every row:**

| ID | Scenario | Grounding |
|---|---|---|
| S1 | OTP/PIN takeover from a gang phone: login, PIN reset, drain to 1–4 mules. Variants: **agent-register harvesting** (victims visited one of 4 compromised agents; 4 sends in ~30 s to fake-NID mules) and **remote-access app** (on the victim's own phone) | playbook §2.3; TBS register-harvest case |
| S2 | Collector wallet 1–3 days old receives from 8–25 first-time victims in hours (job fee, lottery, parcel, loan fee), then cashes out | playbook §5.2 pattern B |
| S3 | Mule chain: 2–4 hops within minutes, sometimes splitting, 10% gang cut, ending in cash-out | playbook pattern C |
| S4 | Rogue agents (9): episodes of 2–3 days at ~8–10× peer cash-out volume, open at night for the gang | playbook "injected agent risk" |
| S5 | Fake online seller: advance payments from buyers over days, nightly cash-outs, then silence | f-commerce scams |
| S6 | SIM-swap takeover of business owners with high balances: SIM swap, new phone, PIN reset, drain to the daily cap | SIM-swap gang reports |
| S7 | Guided victim / pressure scam (jail guard, lawyer, police, relative in hospital): victim's own phone, often 60+ and USSD, cash-in first, personal recipient wallet cashes out within minutes | pressure-scam reports |
| S8 | Stolen card → Add Money bursts (some rejected by the cap) → cash-out within minutes → wallet silent | card-to-wallet case |

25% of mules are **aged, bought accounts** (some dormant first). New mules are recruited weeks ahead and
warmed up with small normal activity, so "new wallet = fraud" does not work.

**Planted demo scenarios** (all in the test window, unseen by training): SC-01…SC-08 must be caught; SB-01…SB-05
are benign look-alikes that must not be blocked. See `reports/demo_scenarios.md`.

Full column list: `docs/data_dictionary.md`.

## 4. Validation T1–T14

| | Check | | Check |
|---|---|---|---|
| T1 | schema, keys, time order | T8 | fraud 0.3–0.8%, every scenario in train/val/test, rogue episodes in every split |
| T2 | referential integrity | T9 | label consistency (case, role) |
| T3 | balances chain exactly per wallet, none negative | T10 | scenario signatures (collector age, hop delay, SIM swap before drain, own vs new device, S4 ~8–10×) |
| T4 | no successful row breaks a KYC cap | T11 | anti-shortcut: aged-mule share, fraud not only at night, legit new wallets / phone changes / fan-in exist, no single feature AUC > 0.95 |
| T5 | night trough, evening peak, Eid spike, salary days, Friday | T12 | time-disjoint splits, planted keys in test |
| T6 | volume and type mix | T13 | planted scenario facts (e.g. SC-03: 2-day-old wallet, exactly 14 senders in 3 h) |
| T7 | round-number amounts, heavy tail, valid recharge amounts | T14 | same seed → identical data, different seed → different |

## 5. Features and models

**Streaming feature store** (`src/features/store.py`): for each transaction, compute from the past, then
update. 62 streaming features in 7 groups plus 11 hourly-graph features:

- **transaction:** amount, hour, channel …
- **behaviour:** amount vs own history, drain ratio, velocity, hour surprise, dormancy …
- **device_session:** new phone, phone age on account, wallets per phone, SIM swap / PIN reset / new-login recency …
- **flow:** pass-through ratio, chain depth, first-time senders received …
- **counterparty:** recipient age, first-time pair, recipient fan-in, recipient phone sharing …
- **agent:** agent cash-out spike, young-wallet share …
- **complaints:** 16268 reports on the recipient and its neighbours
- **graph:** degree, PageRank, fast-flow component size, two-hop fan-in

`tests/test_features.py` deletes the future and checks that no feature value changes.

**Models:**

- **LightGBM**, Optuna-tuned. Compared against XGBoost, logistic regression, a hand-written rules baseline, and PaySim's `isFlaggedFraud` rule.
- **Isolation Forest** on behaviour-deviation features (unsupervised).
- **Graph rules:** collector fan-in, pass-through chain, fast-flow network, reported number, shared device.
- **Wrong-number check** (`src/serve/recipient.py`): keypad-weighted Damerau–Levenshtein distance from the number
  typed to each contact paid at least twice, with federated slip costs; a contact within 1.6 is suggested, frequent
  contacts first. `describe()` names the slip: two neighbouring digits swapped, or one wrong key (and whether it is
  the key next to the right one).

**Decision policy** (`src/models/fusion.py`, plain auditable Python):
`fused = w·[p_fraud, anomaly, graph]` → monotone map to 0–100 → **ALLOW < 30 ≤ NUDGE < 60 ≤ STEP_UP < 80 ≤ HOLD**.

- **Cut-offs:** each cut is the stricter of a false-positive budget (1% / 0.3% / 0.1% of legit transactions) and a precision floor (40% / 70% / 90%), both measured on validation.
- **Established-parties cap:** a HOLD becomes a PIN step-up when only the customer's own behaviour is unusual. That means their own long-used phone, no SIM swap, and a recipient that is an old wallet nobody has reported. The customer decides; nothing is frozen.
- **Likely keypad slip:** an ALLOW becomes a NUDGE with "Send to … instead" (`possible_wrong_recipient`).

**Explanations:** SHAP picks the evidence; templates turn values into English and Bangla, e.g.
"এই নম্বরটি মাত্র ২ দিন আগে খোলা হয়েছে। গত ২৪ ঘণ্টায় ১৪ জন ভিন্ন মানুষ এই নম্বরে টাকা পাঠিয়েছেন।"
The LLM copilot (if enabled) only rewrites this structured evidence and never changes a band.

**Complaints** (`src/serve/complaints.py`, from Ferot): rules for amounts (digits, Bangla digits, words like
"পাঁচশো"), full numbers or the last four digits ("sesh 4 digit 4275"), day and time-of-day words in Bangla, Banglish
and English ("2 ta digit" is a count, not 2 o'clock), transaction IDs and scam cues; then the best-matching transfer
in the customer's last 7 days with a confidence. The case type comes from the slip check and the model's view of the
receiving wallet: genuine wrong send, likely scam victim, needs review, or needs details.

**Agent Watch:** with only 9 rogue agents, supervised ML would learn 9 examples. Agent Watch uses peer
z-scores instead: volume vs area median, night share, young-wallet share, pass-through share, and share already
reported. It is evaluated per episode. A Poisson test flags agents visited by far more complaining victims
than their footfall predicts (register harvesting).

## 6. Results (seed 42, test window days 51–60, never used for training or tuning)

<!-- RESULTS:START -->
Data: 683,148 transactions, 3,664 fraud (0.54%); validation **14/14 checks pass**.

**Model comparison (test window)**

| Model | PR-AUC | ROC-AUC | Recall @ 0.5% FPR | Recall @ 2% FPR |
|---|---|---|---|---|
| rules baseline | 0.188 | 0.896 | 20.0% | 38.4% |
| logistic regression | 0.899 | 0.997 | 92.4% | 97.0% |
| XGBoost | 0.961 | 0.998 | 95.5% | 98.0% |
| LightGBM | 0.962 | 0.999 | 95.0% | 98.1% |
| Isolation Forest | 0.405 | 0.886 | 39.1% | 52.0% |
| graph rules | 0.142 | 0.788 | 20.1% | 33.8% |
| Prohori fused score | 0.962 | 0.999 | 95.0% | 98.1% |

**Policy operating points (test)**

| Band reached | Alerts | Precision | Recall | False-positive rate |
|---|---|---|---|---|
| NUDGE+ | 1,551 | 46.1% | 97.4% | 1.28% |
| STEP_UP+ | 975 | 71.5% | 95.0% | 0.42% |
| HOLD+ | 775 | 86.8% | 91.7% | 0.16% |

**Recall by scam type (share of fraud transactions at STEP_UP or higher)**

| Scenario | Fraud txns | Cases | NUDGE+ | STEP_UP+ | HOLD | Cases with a STEP_UP+ hit |
|---|---|---|---|---|---|---|
| S1 | 174 | 36 | 100.0% | 100.0% | 98.9% | 100.0% |
| S2 | 151 | 9 | 100.0% | 100.0% | 98.0% | 100.0% |
| S3 | 66 | 11 | 98.5% | 98.5% | 92.4% | 100.0% |
| S5 | 136 | 13 | 88.2% | 77.9% | 74.3% | 100.0% |
| S6 | 70 | 12 | 100.0% | 100.0% | 100.0% | 100.0% |
| S7 | 93 | 34 | 97.8% | 93.5% | 84.9% | 97.1% |
| S8 | 44 | 7 | 100.0% | 100.0% | 95.5% | 100.0% |

**Customer impact and friction**

- Victim-side scam transactions (money leaving a victim) flagged STEP_UP or higher: **90.8%** (NUDGE+ 95.4%).
- Expected victim money protected: **Tk 2,401,775 of Tk 2,526,620 (95.1%)** under the stated stop-rate assumptions.
- Honest customers over the 10 test days: 7.3% saw any warning, 2.6% were asked for a PIN step-up, 0.9% had a transaction held. Legit transactions allowed without friction: 98.72%.
- Analyst load: 77.5 HOLD cases/day → 258.3 h manual vs 38.8 h with the copilot over 10 days (assumed minutes per case).

**Ablation:** removing a feature group and retraining costs the most PR-AUC for counterparty (−0.137), behaviour (−0.026), complaints (−0.016) (full model 0.962). Component view: LightGBM only 0.962; LightGBM + IsolationForest 0.962; LightGBM + graph rules 0.962; fused (all three) 0.962.

**Fairness:** groups whose false-positive rate exceeds 1.25× the overall rate (≥ 1,000 legit txns): age_band=45-59 (NUDGE ×1.33, STEP_UP ×1.28), age_band=60+ (NUDGE ×1.12, STEP_UP ×1.65), segment=farmer_rural (NUDGE ×1.99, STEP_UP ×2.22), segment=small_business (NUDGE ×1.28, STEP_UP ×1.57), kyc_level=KYC1 (NUDGE ×1.23, STEP_UP ×1.34). These attributes are not model inputs. The gaps come from behaviour that correlates with the group (farmers and older customers transact rarely and in lumps, so a normal transfer looks large against their own history; small-business wallets are paid by many first-time senders). They are monitored in `reports/fairness.csv`, not corrected with per-group thresholds.

**Agent Watch (test):** 6/9 rogue episodes flagged, 1.1 false-alarm agent-days per day across 300 agents. SC-06 agent A00044: score 85.8, 10.4× its area's median cash-out volume. Register-compromise test: 3/4 harvested agents flagged, 1 other.

**Planted demo scenarios:** 13/13 land in an acceptable band.

| ID | Scenario | Expected | Actual | Score |
|---|---|---|---|---|
| SC-01 | SIM-swap takeover of a business owner at 01:40 | HOLD | HOLD | 100.0 |
| SC-02 | Agent-register harvest: OTP takeover drains 12,500 to 4 mules in 30 s | STEP_UP | HOLD | 100.0 |
| SC-03 | Collector wallet: 2 days old, 14 strangers paid it in 3 h; victim #15 about to send | STEP_UP | HOLD | 100.0 |
| SC-04 | Mule chain through a 400-day-old dormant account (hops of 4, 6, 9 min) | STEP_UP | HOLD | 98.0 |
| SC-05 | 'Jail guard' pressure scam: 60+ USSD farmer cashes in 20,000 and sends it | NUDGE | NUDGE | 30.5 |
| SC-06 | Rogue agent: night cash-outs for the ring, ~8-10x peer volume | FLAGGED | FLAGGED | 85.8 |
| SC-07 | Stolen card: 2 x 25,000 Add Money at 03:10, cash-out 29,500 at 03:40 | HOLD | HOLD | 100.0 |
| SC-08 | Fake phone seller: 9 advance payments in 3 days; buyer #1 already reported it to 16268 | NUDGE | HOLD | 88.6 |
| SB-01 | Busy shop owner's personal wallet: 12 payers in a day | ALLOW | ALLOW | 10.6 |
| SB-02 | Legit new phone, then usual bill + 2,000 to mother | ALLOW | ALLOW | 15.3 |
| SB-03 | Rent advance: 35,000 to a new landlord, Friday 11:00, own phone | NUDGE | STEP_UP (established parties cap) | 98.6 |
| SB-04 | Student cashes out 4,900 twelve minutes after parent sends 5,000 | ALLOW | ALLOW | 0.2 |
| SB-05 | Remittance family cashes out 29,500 twenty minutes after 48,250 lands | ALLOW | ALLOW | 2.4 |

Validation (days 46–50) fused PR-AUC 0.967; LightGBM 777 trees; fusion weights {'clf': 1.0, 'anom': 0.0, 'graph': 0.0}. Full detail: `reports/evaluation.md`, `reports/model_card.md`.
<!-- RESULTS:END -->

> These numbers come from synthetic data with injected patterns: read them as upper bounds. The defensible
> claims are the gap over the rules baseline, recall by scam type, the friction numbers, and the fact that
> every number is reproducible with one command.
>
> Honest notes for Q&A:
> - **Fusion weights are fitted on validation, and on this data they put all the weight on LightGBM.** The graph
>   signals already enter LightGBM as features, and adding the Isolation Forest or graph rules on top did not
>   raise validation recall. Both still earn their place: graph patterns drive reason codes and the
>   reported-recipient floor, and the Isolation Forest is reported as an unsupervised alarm for attacks with no
>   labels yet.
> - **The weakest cases are the social-engineering ones on the victim's own phone (S5 fake seller, S7 pressure
>   scam).** They get a NUDGE through the evidence floors rather than a high model score. Re-generating with
>   another seed moves recall on these by a few points.
> - **The federated runs are simulations.** The slip events and phones are synthetic; the cross-silo silos are the
>   8 divisions of the same synthetic world.

## 7. Time split and data hygiene

Train days 1–40 · validation 41–45 (early stopping, Optuna) · validation 46–50 (fusion weights, calibration,
band cut-offs) · **test 51–60, read once by `evaluate`**. No random splits. Protected attributes (gender, age
band, division, urban/rural, segment) are never model inputs; false-positive rates are audited per group.

## 8. Deploy (inference only)

The API and UI need `artifacts/model_bundle.joblib` (or `serve_bundle.joblib`), `demo_state.joblib` and
`demo_world.joblib` (a few MB) and `ui/`, never the dataset. The UI loads no external scripts, styles or fonts, so the
demo works offline. Bangla text uses **Noto Sans Bengali**, bundled in `ui/fonts/` (variable WOFF2 from Google
Fonts, about 150 KB; SIL Open Font License 1.1, `ui/fonts/OFL.txt`).

```bash
docker build -t prohori . && docker run -p 8000:8000 prohori
curl localhost:8000/health
curl -X POST localhost:8000/v1/score -H "content-type: application/json" -d '{"sender_id":"W0000050","receiver_id":"W0000051","amount":25000,"device_id":"DV9999999"}'
```

**Live deployment (free): a static Hugging Face Space where the models run in the browser.** Docker Spaces now
need Hugging Face PRO, so the free deployment ships no server at all:
- `python -m src.serve.portable` writes the models in version-neutral form (`artifacts/portable/`): LightGBM's own
  text model, the Isolation Forest trees as arrays, the isotonic calibrator as arrays, the rest as JSON, plus the
  federated slip costs and results. It also saves the demo world after staging. On 4,734 test-window transactions
  (all 734 frauds plus 4,000 honest), every probability, score, band, policy override and SHAP contribution is
  identical to the pickled originals. In real Pyodide the largest difference on 1,000 rows is 1e-16.
- `python tools/build_static.py` builds `site/`: the same `ui/` pages, `config.js` in browser mode, and
  `py/prohori.zip` (our Python package plus the portable models, 6.4 MB). `ui/pyworker.js` boots Pyodide 0.28 in a Web
  Worker (numpy, pandas and LightGBM from the jsDelivr CDN) and answers every `/api/v1` route through
  `src/serve/browser.py`. The showcase's phone and copilot share one engine, so alerts still flow between them.
- `python tools/deploy_space.py --space USER/prohori --static` uploads it (16 files, 6.7 MB). Measured on the live
  Space: ready 15 s after opening, about 100 ms per scored transfer, about 340 MB of browser memory. In the browser
  the 24-hour graph snapshot from 09:30 is kept (networkx is not loaded); training also rebuilt it only hourly.

**Server version on Hugging Face Docker Spaces (needs PRO) or any Docker host.** One command uploads only what the image
needs (Dockerfile, pinned requirements, `config.yaml`, `src/`, `ui/`, three artifacts: about 9.5 MB):

```bash
pip install huggingface_hub
hf auth login                                        # token with WRITE access from huggingface.co/settings/tokens
python tools/deploy_space.py --space YOUR-HF-USERNAME/prohori --source https://github.com/YOUR/REPO   # Docker Space (PRO)
# or, free:  python tools/deploy_space.py --space YOUR-HF-USERNAME/prohori --static
```

`--dry-run` lists the upload without sending anything. Re-running the command redeploys and mirrors the folder.
The script uses the Hub API because a plain `git push` to a Space rejects binary files (`.joblib`, `.woff2`).
Docker Spaces sleep after about 48 hours without visitors; static Spaces do not sleep.

**Measured in Docker (Linux, the image the Space builds):** healthy 12 seconds after start, about 476 MiB right
after start, about 545 MiB after the full demo and a reset. The demo world is built once at start-up, on the main
thread. Building it lazily in a request thread used 200-350 MB more. The serving bundle leaves out the XGBoost and
logistic-regression comparison models; the live policy never uses them, and the image then needs no XGBoost.
`requirements-serve.txt` pins the exact versions the artifacts were pickled with (pandas 3 also needs `pyarrow`).
Set `PROHORI_SCORER=federated` to serve the federated model instead (`artifacts/fed_serve_bundle.joblib`).

**Render:** `render.yaml` works with the same Dockerfile but asks for the Standard plan (2 GB). The Free and
Starter plans have 512 MB, below what the app uses after a demo.

Endpoints: the product API in section 0, plus the original inference routes `POST /v1/score`, `GET /v1/demo`,
`/v1/demo/{SC-03}`, `GET /v1/agents/top` and `GET /v1/metrics`.

## 9. Assumptions you may be asked about

Every number is in `config.yaml`. The ones that matter most:

| Assumption | Value | Status |
|---|---|---|
| KYC2 limits | Send Money Tk 50,000/day, Cash Out Tk 30,000/day, Add Money Tk 25,000/txn | 2025 news coverage of BB circulars; **verify upay's current numbers** |
| KYC1 limits | Tk 10,000/day send / cash-out | synthetic assumption |
| Cash-out fee | 1.85% | typical BD MFS, synthetic |
| Fraud prevalence | ~0.5% of transactions | synthetic, chosen for a usable test set |
| Complaint rates | 35–95% of victims call 16268, after 2 h – 5 days | synthetic |
| Stop rates | NUDGE 30%, STEP_UP 70%, HOLD 100% of scams stopped | **assumption** behind the "money protected" estimate |
| Analyst time | 20 min manual vs 3 min with copilot per HOLD | assumption |
| Eid placement | days 9–11 | synthetic placement (not the real 2026 calendar) |
| Complaint deadline | 10 working days, Friday and Saturday excluded | MFS Regulations 2022 §17.3 |
| Keypad-slip suggestion | distance ≤ 1.6, contact paid at least twice | Ferot Guard settings |
| Slip events on phones | 70% neighbouring key, 30% other key, 35% of slips are swaps | **simulation assumption** for the on-device run |

**Claims to avoid on slides:** the "56% of fraud was compromised PINs/impersonation" figure. In the source
found, 56% was the share of victims whose complaints were resolved satisfactorily, from an Aug–Sep 2021
survey. Check the PRI report before quoting anything from it.

What changed versus the reviewed spec, and why: `docs/spec_review_fixes.md`.

## Disclosures

As required by the rulebook (§4.4, §9.2):
- **AI coding assistance:** this codebase was written with substantial help from Claude Code (Anthropic), working
  with the team. The team reviewed the design and can explain every component.
- **External API (optional, off by default):** Anthropic Claude API, only to reword the analyst case report from
  structured facts. Complaint and scam-check text is read by rules, never sent to an LLM.
- **Open-source libraries:** pandas, NumPy, PyArrow, SciPy, scikit-learn, LightGBM, XGBoost, SHAP, Optuna, NetworkX,
  PyYAML, Matplotlib, FastAPI, Uvicorn, Pyodide (in-browser build), Playwright (testing only, not shipped).
  Font: Noto Sans Bengali (Google Fonts, SIL OFL 1.1). `archive/ferot/` lists its own (React, Vite, Tailwind CSS…).
- **Data:** entirely synthetic, generated by `src/datagen`. No real customer data. Phone numbers use the 010 prefix.
- **Brand:** "upay" is used only to describe who the prototype is for. No upay logo files or assets are used. The
  upay-style screens imitate the look of a wallet app (yellow and blue colours) and are labelled on screen as a
  prototype on synthetic data, not upay's app.

## License

MIT, see [LICENSE](LICENSE).
