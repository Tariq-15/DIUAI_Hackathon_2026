# What changed after Phase 1 feedback — session log, 2026-10-07

Honest, dated record of this session's work against the Phase 1 judge feedback (see
`docs/feedback_implementation_plan.md` for the prioritized backlog this follows). Every item below is traceable to
a file in this repo. **Nothing here is committed yet** — it is uncommitted working-tree changes on top of commit
`7fc5ec1`; `git status` lists the touched files. Nothing was invented for this log.

## Environment (the blocker the previous verification record flagged)

The 2026-10-07 verification record originally said Python was unavailable on PATH, so none of the evidence tooling
had ever run. This session:
- Confirmed Python 3.12.10 is in fact installed and on PATH.
- Installed the missing packages the pipeline needs: `optuna` (hyperparameter tuning) and `matplotlib` (evaluation
  plots) — both were absent and caused real failures, caught by the smoke test below.
- Fixed a real bug in `tools/feedback_evaluate.py`: it read `metrics_test.json` with `.read_text()` and no
  encoding, which crashes on Windows (cp1252 default) against the Bangla reason-code strings inside the file. Now
  reads with `encoding='utf-8'`. Without this fix the multi-seed aggregation step would have failed after a 30+
  minute training run.

## Executed and verified (not just planned)

- **`python -m tools.feedback_verify --out-root runs/feedback/verification`** — ran for real. Result: **61 tests
  pass, 0 failures, 0 errors, 0 skipped** (JUnit at `runs/feedback/verification/pytest.xml`), commit `7fc5ec1`, pip
  freeze and git status archived. The README's test badge said 58; updated to 61 to match this captured run.
- **`python -m tools.feedback_evaluate --out-root runs/feedback`** — refreshed the keypad vs. ordinary-edit-distance
  diagnostic (`runs/feedback/recipient_matrix.json`). Result: on digit-transposition ("swap") slips, the keypad
  check gets **6 of 12** right; unit-cost Levenshtein gets **0 of 12** (it scores a swap as distance 2 and never
  suggests). The keypad check also produces more false suggestions on legitimately similar numbers (9 vs. 6 of 12)
  — that trade-off is reported, not hidden. This is a small, fixed diagnostic (n=60 per model), explicitly labelled
  "not customer validation" in the artifact itself.
- **Smoke test** (`--run-seeds --seeds 42 --scale 0.1 --trials 0`) — run before committing to the long multi-seed
  job. It caught both real bugs above (missing matplotlib, the encoding bug) before they could waste a 1.5-hour run.
- **Multi-seed full evaluation** (`--run-seeds --seeds 42 43 44 --trials 30`) — **in progress at the time of this
  log**, not finished. Seed 42 completed in ~37 minutes and reproduced **PR-AUC 0.962 exactly**, matching the
  published seed-42 reference — a real sanity check that the environment and the pipeline reproduce cleanly on a
  fresh run. Seed 43 was running at last check; seed 44 had not started. `runs/feedback-full/summary.json` will
  exist only once all three seeds finish; it does not exist yet.

## Product features built this session

- **Judge onboarding tour** (`ui/analyst.html`, `ui/analyst.js`, `ui/prohori.css`) — a 🧭 button in the copilot
  header opens a 9-step, icon-based, bilingual (bn/en) walkthrough that switches tabs and highlights the real
  Overview, alert queue, SHAP/money-network, Agent Watch, model/fairness, federated/privacy and audit-log elements.
  Auto-opens once for a first-time, non-embedded visit; suppressed inside the showcase's embedded iframe view
  (matching how the existing "About this demo" guide already behaves there). Verified structurally: every DOM id
  referenced in the JS was cross-checked against the HTML; a local `uvicorn` server was booted and the served
  `analyst.html`/`analyst.js`/`prohori.css` were fetched with `curl` to confirm the new markup, CSS and JS ship.
  **Not done:** an actual browser click-through — installing Playwright's Chromium (195 MB) didn't fit the time
  budget, so this was verified structurally, not visually, and that limitation is stated rather than glossed over.
- **Customer↔analyst follow-up channel** — closes a real product gap: an analyst could ask a complaint filer for
  more details (the existing `ASK_CUSTOMER_DETAILS` action), but the customer had no way to respond; the thread
  dead-ended. Built:
  - `src/serve/live.py`: `respond_to_complaint()` — ownership-checked (only the wallet that filed the complaint may
    reply), audit-logged (`complaint.reply_details`), appends to a `thread` list on the complaint record, moves
    status `details_requested → details_received`.
  - `src/serve/api.py`: new route `POST /api/v1/complaints/{cid}/respond`.
  - `ui/app.js`: the customer's case tracker now shows the thread (🕵️ analyst / 🧑 customer bubbles) and a 📨 reply
    box when a reply is wanted.
  - `ui/analyst.js`: the copilot's complaint detail view shows the same thread, plus a ⏳ "waiting for customer"
    indicator when none has arrived yet.
  - All touched JS/Python files pass a syntax check (`node --check`, `python -m py_compile`). **Not done:** a live
    click-through test of the full request→reply round trip in a running browser, for the same Playwright-install
    time reason as above.

## Documentation updated to match reality (not aspiration)

- `docs/feedback_delivery.md` — the verification-record section no longer says "Python was unavailable"; it now
  states the actual 2026-10-07 result (61 passed, 0 failed) with the artifact paths.
- `docs/feedback_implementation_plan.md` — ticked only the items that actually ran (environment, verify, keypad
  matrix); the multi-seed item is marked in-progress, not done; everything partner-gated is still marked pending.
- `README.md` — test badge corrected to 61; the "execution... pending" line now points at the dated artifacts
  instead of asserting nothing had run.
- `docs/pitch_deck.md` — a 13-slide outline built the same way: every claim paired with the file or command that
  reproduces it, including an explicit slide (12) listing what is still a modeled assumption, not a measurement.

## Explicitly still open (not claimed as done)

- The multi-seed run itself (seeds 43, 44, and the aggregated `summary.json`).
- Any customer or complaint-handler usability study, shadow scoring, or pilot — all partner-gated, per
  `docs/feedback_delivery.md`; none of that access exists.
- Browser-level (not just structural) verification of the two new UI features.
- Everything in Tiers 2–4 of `docs/feedback_implementation_plan.md` (impact reframing, integration adapter,
  fairness remediation study, federation threat experiments) — not started this session.
- **None of this session's changes are committed to git.** They are visible only in the working tree
  (`git status`) until a commit is made.
