# On-site playbook (final day, 7 October)

The rulebook (§8) gives new requirements at the start of the final day. Use this page to put each change in the
right place fast, commit in small steps, and explain it in the 90-minute second evaluation.

| If the new requirement is about... | Change this | Test to add or update |
| --- | --- | --- |
| A new business rule, threshold or approval | `config/policy_rules.yaml` (+ a section in `sop/`) | `backend/tests/test_policy.py` |
| A new limit, fee or holiday | `config/limits.yaml`, `config/holidays_bd.yaml` | `test_sla.py`, `test_datagen.py` |
| A new case type or scam pattern | `backend/ferot/datagen/generator.py` (plant it), `models/classifier.py` (`CLASSES`), retrain | `test_datagen.py`, check `reports/metrics.json` |
| A new model feature | `backend/ferot/features/evidence.py` (`FEATURES`, `FEATURE_LABELS`), retrain | `test_api.py` golden path still passes |
| A new message or language | `backend/ferot/models/drafts.py` (`T`) | `test_drafts.py` checks run on it automatically |
| A new intake channel | `backend/ferot/api/main.py` (`CHANNELS`) | `test_api.py::test_all_channels` |
| A new API field or endpoint | `backend/ferot/service.py` + `api/main.py` + `web/src/api.ts` | `test_api.py` |
| A new screen or panel | `web/src/pages/*`, shared bits in `web/src/components.tsx` | `npm run build` |
| A new KPI or report | `service.py` (`kpis`, `dispute_report_csv`) + `web/src/pages/Analyst.tsx` | `test_api.py::test_dispute_report_csv` |
| Turning on the LLM | `.env`: `FEROT_LLM_PROVIDER=anthropic` + key in the host dashboard | `test_masking.py` |

## Routine for each requirement

1. Read it, write one line in the commit message about what changes and why.
2. Make the smallest change in the place above; run `python -m pytest` (≈10 s).
3. If data or models change: `python -m ferot.cli build`, commit the new `reports/*.json`.
4. Commit and push. Redeploy, then open the live URL and run the golden path.
5. Note for the judges: requirement → files changed → test that proves it.

## Rules that must still hold after any change

- No refund promises; no tipping off; hold never above the disputed amount or balance.
- Every money action needs a named human; rejections need a supervisor.
- No calls to upay systems; synthetic numbers only (010 prefix); no secrets in the repo.
