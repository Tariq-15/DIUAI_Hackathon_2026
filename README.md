# Ferot — AI wrong-send & dispute copilot (built for upay)

> AI Hackathon 2026 (AI DEV FEST, DIU CPC × upay) · Track 06: Operations & Service Intelligence
> **Prototype. Synthetic data only. Not an official upay product, message or endorsement.**

## Project overview

**Problem.** "I sent money to the wrong number" is one of the most common and stressful MFS complaints in
Bangladesh. Recovery is manual and slow, and it is a race: money can usually be held only while it is still
in the recipient's wallet. The same words also come from scam victims, from people trying to claim money
twice, and from customers who regret a deliberate payment. Bangladesh Bank requires every dispute to be logged
and resolved within 10 working days (MFS Regulations 2022 §17.3).

**Solution.** Ferot (ফেরত, "money back") is a decision-support copilot for upay's support team. It reads a
complaint in Bangla, Banglish or English, finds the disputed transfer, rebuilds the money trail, classifies the
case into five types, estimates how much money is still holdable over the next hours, ranks the queue by taka at
risk, and recommends the next step with drafted replies. **Ferot never moves money: a named human approves every
action.**

**Ferot Guard** works one step earlier. While the customer is still on the confirm screen, it checks the transfer:
is the number one keypad slip from someone they pay often ("Did you mean 01012345678?"), or does the receiving
wallet look like a scam drop? It explains any warning in plain Bangla and adds a 30-second pause for the riskiest
transfers. It never blocks: the customer always decides.

**Purpose.** Recover more customer money, cut handling time, stop false and double-recovery claims, turn
complaints into mule-wallet intelligence for the AML team, and meet Bangladesh Bank's dispute rules by design.

## Features

| Feature | How AI is used |
| --- | --- |
| **Ferot Guard** (before the money leaves) | LightGBM P(scam) on transfer features fused with an IsolationForest anomaly score; warn and pause bands set on validation data; keypad "Did you mean" check; reasons in Bangla and English built only from feature values; never blocks |
| Customer intake (Bangla/English) with consent notice | — (rules: notice, responsibilities, 10-working-day timeline, escalation route) |
| **M1** Complaint extraction | Rules for numbers, TrxIDs, Bangla digits and number words; optional LLM (Claude) on **masked** text fills gaps; disagreements flagged |
| **M2** Transaction matching | Scores the claimant's recent transfers on amount, number, time and TrxID (95% top-1) |
| **M3** Intended-number matcher | Keypad-weighted edit distance against the sender's history: "you paid …5678 eleven times; this went to …5687" |
| **M4** Case classifier (5 types) | LightGBM on ledger, graph and text features, with per-case reasons from TreeSHAP |
| **M5** Recoverability curve | LightGBM per horizon (1 h–72 h): probability the money is still holdable |
| **M6** Queue priority | Taka lost if the case waits + vulnerability + SLA floor |
| **M7** Mule clusters | Wallets named by many complainants, linked by onward transfers |
| Policy engine | Versioned YAML business rules choose the action; hold capped at the disputed amount and balance; cites the procedure followed |
| **M8** Drafted replies | Bangla and English templates with slot-filled numbers; optional LLM polish; every draft checked: grounded, no refund promise, no tipping off |
| Agent console | Queue ranked by money at risk; case file with the "taka drain" (money still holdable, ledger facts then the M5 estimate), a four-part case report (what happened, evidence, next step, limits), TreeSHAP reasons, the ring of complainants and cash-out agents around the receiving wallet, provenance labels on every panel, masked numbers, approve / edit / override, audit trail |
| Evidence view | Alerting metrics (PR-AUC, precision and recall at the policy threshold, false alarms per 100 innocent customers), confusion matrix, baselines, queue simulation with 95% CIs, fairness by language, channel, age, area and KYC, mule clusters, AML queue, Guard warnings, monthly dispute report CSV |
| Compliance | Hash-chained audit log, role checks, export only via compliance on a verified request, 6-year retention setting |

## Results (synthetic data, held-out test window: days 75–90)

| What | Ferot | Baseline |
| --- | --- | --- |
| Case-type macro-F1 (M4) | **0.96** | keyword rules 0.55 · text-only model 0.50 |
| Scam-victim recall | 0.88 (0.90 on a scam type never seen in training) | — |
| Scams held at the policy threshold, P(scam) ≥ 0.45 | recall **0.85**, precision 1.00, 1 wrongful rejection in 219 victims | 0.70 at the old 0.60 threshold |
| Guard: scam transfers warned before sending | **98.8%** (PR-AUC 0.997, 85 scams in 1,223 test transfers) | — |
| Guard: ordinary transfers interrupted | **0.44 per 100** (none paused) | — |
| Guard: typos caught by "Did you mean" | 100% | — |
| Fairness: largest accuracy gap between groups | 3.8 points (app 98.4% vs phone call 94.6%) | — |
| Transaction match top-1 (M2) | 0.95 | — |
| Intended number found on genuine typos (M3) | 0.98 | — |
| Recoverability Brier at 6 h (M5, lower is better) | **0.072** | "balance now" 0.099 |
| Money still holdable when an agent acts (simulation) | **+4.2%** vs first-come-first-served (95% CI 3.8–4.6%) | largest-first +4.5% · oracle ceiling +6.7% |

The numbers above come from the default 4,000-customer build. The Docker image builds a 2,500-customer world so it fits a 512 MB host; its results are similar (macro-F1 0.97) and the hosted analyst page shows that build's own numbers.

Honest notes: the data is synthetic, so these numbers show the method works on planted patterns, not real-world
accuracy. Scores near 1.0 (Guard PR-AUC, scam PR-AUC) mean the synthetic scam pattern is cleaner than real fraud.
Guard warns USSD users more often than app users (0.78 vs 0.34 per 100 ordinary transfers); both are low, and the
gap is reported. Ferot's ordering matches the strong "largest amount first" heuristic; its extra value is the case file,
the explanation and the compliance controls. See [docs/error_analysis.md](docs/error_analysis.md). Full numbers:
[reports/metrics.json](reports/metrics.json) and [reports/simulation.json](reports/simulation.json).

## Technology stack

- **Languages:** Python 3.12, TypeScript
- **Backend:** FastAPI, Uvicorn, pandas, NumPy, PyArrow, SQLite
- **ML:** LightGBM, scikit-learn (metrics), TreeSHAP via LightGBM `pred_contrib`
- **LLM (optional):** Anthropic Claude via the official `anthropic` Python SDK, default model `claude-opus-5-5`,
  structured JSON outputs, server-side refusal fallback; behind a swappable provider interface. **Off by default.**
- **Frontend:** React 19, Vite, Tailwind CSS 4; charts and graphs are hand-written SVG; fonts Anek Bangla and Hind Siliguri
- **Ops:** Docker, GitHub Actions (pytest, web build, gitleaks), Render blueprint

## Requirements

- Python 3.12+ and Node.js 22+ (or just Docker)
- ~1 GB free RAM; no GPU
- Internet only for installing dependencies. The app itself runs offline unless you enable the LLM provider.

## Installation and setup

```bash
git clone https://github.com/Tariq-15/DIUAI_Hackathon_2026.git
cd DIUAI_Hackathon_2026

# 1. backend
python -m venv backend/.venv
# Windows: backend\.venv\Scripts\activate    macOS/Linux: source backend/.venv/bin/activate
pip install -r backend/requirements.txt

# 2. synthetic data, models and simulation (about 1 minute)
cd backend
python -m ferot.cli build
cd ..

# 3. web app
cd web && npm ci && npm run build && cd ..

# 4. optional settings
cp .env.example .env    # edit if you want the LLM provider (see below)
```

## Environment variables

| Variable | Purpose | Default |
| --- | --- | --- |
| `FEROT_LLM_PROVIDER` | `offline` (rules + templates, no network) or `anthropic` | `offline` |
| `ANTHROPIC_API_KEY` | Only for `anthropic`. Set it in your shell or host dashboard; never commit it | *(placeholder)* |
| `FEROT_LLM_EXTRACT_MODEL` / `FEROT_LLM_DRAFT_MODEL` | Claude model IDs used when the provider is `anthropic` | `claude-opus-5-5` |
| `FEROT_SEED`, `FEROT_CUSTOMERS`, `FEROT_DAYS` | Size and seed of the synthetic world | `42`, `4000`, `90` |
| `FEROT_DB_PATH` | SQLite case store | `backend/ferot.db` |
| `FEROT_CORS_ORIGINS` | Allowed origins in development | `http://localhost:5173` |

## Run and build commands

```bash
# Run everything on one port (API + built web app)
cd backend
python -m uvicorn ferot.api.main:app --port 8000
# open http://localhost:8000   ·   API docs: http://localhost:8000/docs

# Frontend development with hot reload (API must be running on :8000)
cd web && npm run dev            # http://localhost:5173

# Docker (builds data and models inside the image)
docker build -t ferot .
docker run --rm -p 8000:8000 ferot
```

Rebuild pieces individually: `python -m ferot.cli data` · `train` · `simulate`.

## Live deployment URL

**Live demo:** _to be added after deployment_ (Render free tier; first load after idle can take ~1 minute).

Deploy your own: on [Render](https://render.com) choose **New → Blueprint**, select this repository, and Render
reads [`render.yaml`](render.yaml). The free tier has 512 MB RAM; the image (2,500 customers) uses about 390 MB.
Any Docker host works: `docker build -t ferot . && docker run -p 8000:8000 -e PORT=8000 ferot`.

## Testing instructions

```bash
cd backend
python -m pytest          # 117 tests: rules R1–R20, data, extraction, models, Guard, policy, drafts, audit, API, injection
```

Manual check of the demo (about 4 minutes):
0. **Customer app → Send money (Ferot Guard)** → choose *Rahim* → *ভাইকে নিয়মিত পাঠানো টাকা* → *Next*: no warning.
   Pick *যে লেনদেনটি ভুল হয়েছিল* → *Next*: "Did you mean 01012345678?" with the swapped digits; *Use this number* sends
   to the right one. Then *Shirin* → *Next*: a red warning with three reasons and a 30-second pause on *Send anyway*.
1. **Customer app → Report a problem** → choose *Rahim* → *ভুল নম্বরে টাকা গেছে* → pick the ৳5,000 transfer to …5687 → *Next* → tick the
   notice → submit. You get a case number and a 10-working-day deadline.
2. **Agent console** → sign in as an agent → open Rahim's case: *Genuine wrong-send*, digits 9–10 swapped against his
   brother's number (paid 11 times), ৳4,200 holdable, rule `R-GEN-01`. Approve; the audit trail updates.
3. Back in the customer app, submit *Shirin*'s complaint: same kind of words, but Ferot says *Scam victim*: a
   23-day-old wallet that 14 other customers complained about, money gone in minutes.
4. **Evidence** → alerting metrics, confusion matrix, baselines, simulation, fairness, mule clusters, Guard warnings, dispute report CSV.
5. Sign in as an agent and try to approve a `R-FALSE-01` or `R-DBL-01` case: it needs a supervisor (R6).

## Other configuration

- `config/limits.yaml` — upay's published limits and fees (the FAQ and Limits page disagree; the stricter value is used).
- `config/policy_rules.yaml` — business rules, approvals and procedure citations; change without code.
- `config/holidays_bd.yaml` — Bangladesh public holidays for the 10-working-day timer. **Add each year's lunar holidays
  from the government notification before real use.**
- `config/assumptions.yaml` — every synthetic-data and modelling assumption, with a reason.
- `sop/` — mock operating procedures written by the team (not upay's).
- Roles in the prototype come from the console's sign-in screen (`X-Ferot-Role` header). Production would use upay's SSO.

## Compliance by design

Ferot is built under 20 design rules drawn from upay's Terms and Conditions and Privacy Policy, Bangladesh Bank's MFS
Regulations 2022 and ICT Security Guideline, the Money Laundering Prevention Act 2012, the Personal Data Protection
Ordinance 2025 and the hackathon rulebook. Each rule is mapped to code and a test in
[docs/compliance.md](docs/compliance.md). Highlights: 10-working-day SLA timer and dispute log, consent at intake,
masked numbers with logged reveals, no refund promises (upay T&C §11.1), no tipping off (MLPA §6), hold capped at the
disputed amount, supervisor approval for rejections, tamper-evident audit log, no calls to upay systems.

## Disclosures

As required by the rulebook (§4.4, §9.2):
- **AI coding assistance:** this codebase was written with substantial help from Claude Code (Anthropic), working
  with the team. Commits carry a `Co-Authored-By` line. The team reviewed the design and can explain every component.
- **External API (optional, off by default):** Anthropic Claude API for complaint extraction and draft polishing.
- **Open-source libraries:** FastAPI, Uvicorn, pandas, NumPy, PyArrow, LightGBM, scikit-learn, PyYAML, React, Vite,
  Tailwind CSS, Playwright (screenshots only, not shipped). Fonts: Anek Bangla and Hind Siliguri (Google Fonts, OFL).
- **Data:** entirely synthetic, generated by `backend/ferot/datagen`. No real customer data. Phone numbers use the 010
  prefix. Public facts used: upay's published limits and fees, and Bangladesh Bank regulations (see docs).
- **Brand:** "upay" is used only to describe who the prototype is for. No upay logos or assets are used.

## Repository layout

```text
backend/ferot/   datagen/ features/ models/ policy/ llm/ store/ sim/ api/ service.py cli.py
backend/tests/   117 tests
web/src/         customer app (Send money with Guard, Report a problem), agent console, case file, evidence
config/          limits, assumptions, policy rules, holidays
docs/            compliance, project report, model cards, error analysis, on-site playbook, demo script
reports/         metrics.json, simulation.json
sop/             mock procedures
```

## License

MIT — see [LICENSE](LICENSE).
