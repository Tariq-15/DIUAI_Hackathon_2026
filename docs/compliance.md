# Compliance: the rules Ferot is built under

Ferot is a hackathon prototype built on **synthetic data only**. This file is the team's reading of
public sources, not legal advice; upay's compliance team has the final word.

Every rule below (R1–R20) is enforced in code and checked by a test. The traceability table at the
end shows where.

## Sources (status as of 1 October 2026)

| Source | Status | What it governs for Ferot |
| --- | --- | --- |
| upay Terms and Conditions (upaybd.com) | In force | Customer liability for wrong entries (§11.1), site and brand use (§4, §7) |
| upay Privacy Policy | In force | Sharing only with contracted service providers; law-enforcement disclosure on verified request |
| upay FAQ and Limits page | Published (the two limit tables disagree) | Limits, fees, helpline 16268, KYC levels |
| Bangladesh MFS Regulations 2022 (PSD Circular 04/2022) | In force since 15 Feb 2022 | Dispute deadline, complaint channels, records, ICT security, AML |
| Bangladesh Bank Guideline on ICT Security v4.0 | April 2023; covers MFS providers | Encryption, access control, audit logs, secure development |
| Payment and Settlement Systems Act 2024 | Passed July 2024 | Licensing and oversight of payment services |
| Money Laundering Prevention Act 2012 / Anti-Terrorism Act 2009 | In force (BFIU) | STRs, record keeping, no tipping off (MLPA §6) |
| Personal Data Protection Ordinance 2025 | Gazetted 6 Nov 2025; compliance window to ~May 2027 | Consent, data-subject rights, automated decisions, data localisation |
| Cyber Security Ordinance 2025 | Gazetted 21 May 2025 | Cyber offences incl. data theft |
| AI DEV FEST 2026 Rulebook + Student Guideline | Current | 72-hour build, public repo, README, synthetic data, responsible AI |

## Design rules

| ID | Ferot must | Source |
| --- | --- | --- |
| R1 | Never promise a refund or imply upay is liable; a return depends on the recipient's consent or legal process | upay T&C §11.1 |
| R2 | Log every dispute with its status and resolve it within 10 working days; show an SLA timer on every case | MFS Regs §17.3 |
| R3 | Accept disputes 24 hours a day by phone, SMS, IVR and mail | MFS Regs §17.3 |
| R4 | Tell the customer their responsibilities, the process, the timeline and the escalation route to Bangladesh Bank | MFS Regs §17.4, §17.6 |
| R5 | Keep case and transaction records at least 6 years; export on a valid request | MFS Regs §18; MLPA record keeping |
| R6 | A named human approves every hold, reversal or rejection; customers can contest and ask for human-only review | Student Guideline §14; PDPO 2025 |
| R7 | Mule flags go only to upay's AML/CFT team; no message may tip off the subject | MLPA 2012 §6; MFS Regs §11 |
| R8 | At intake, state purpose, retention, who sees the data and how to withdraw; record consent | PDPO 2025 §6 |
| R9 | Mask personal data before any LLM call; show numbers masked to the last 4 digits; log every reveal | PDPO 2025; upay Privacy Policy |
| R10 | Keep confidential data in Bangladesh in production; external LLM only as a contracted processor | PDPO 2025; upay Privacy Policy |
| R11 | Encrypt transaction data at rest and in transit; least-privilege roles | PDPO 2025; ICT Guideline v4.0; MFS Regs §12.2 |
| R12 | Tamper-evident audit log; every decision tied to a named approver | MFS Regs §12.2; ICT Guideline v4.0 |
| R13 | Release case data to law enforcement only through compliance, on a verified request | upay Privacy Policy; MFS Regs §18.2 |
| R14 | Hold only the disputed amount; notify the recipient and let them respond | Student Guideline §14 |
| R15 | Never access, scrape or frame upay's site or APIs; no upay name/logo without written permission; label demo messages as prototype | upay T&C §4.1, §4.4, §7 |
| R16 | Synthetic data only; synthetic phone numbers use the 010 prefix | Student Guideline §11; PDPO 2025 |
| R17 | Respect upay's published limits and fees | upay Limits page and FAQ; MFS Regs §9 |
| R18 | Secure development: no secrets in code, secret scanning, injection tests | ICT Guideline v4.0; Cyber Security Ordinance 2025 |
| R19 | Label facts, predictions and generated text; show reasons; publish model cards | Student Guideline §14; PDPO 2025 |
| R20 | Build inside the 72-hour window, public repo, continuous commits, disclose external APIs and AI help | Rulebook §4–§6, §9 |

## Bangladesh MFS Regulations 2022: build checklist

| Clause | Requirement | Where in the code |
| --- | --- | --- |
| §17.2 | Prompt complaint handling, easy to find | `web/src/pages/customer/*` — "How to report a problem" |
| §17.3 | 24-hour intake by phone, SMS, IVR, mail | `POST /api/v1/complaints` with `channel` = app / call / sms / email |
| §17.3 | Resolve within 10 working days | `backend/ferot/policy/sla.py` (Sun–Thu working days, Fri–Sat weekend, holidays from config) |
| §17.3 | Log and track every dispute | `backend/ferot/store/audit.py` (hash-chained log) + case status history |
| §17.4 | Escalation to Bangladesh Bank (CIPC) | Confirmation and status screens |
| §17.5 | Agent disputes: distributor first | `config/policy_rules.yaml` rule `R-AGENT-01` |
| §17.6 | Explain roles, responsibilities, risks, liabilities | Intake notice in the customer app |
| §18.1 | Records kept ≥ 6 years | `config/assumptions.yaml` `retention_years: 6`; no delete endpoint |
| §18.2 | Copies of records on request | `GET /api/v1/cases/{id}/export` (compliance role only) |
| §12.1–12.2 | Confidentiality, integrity, authorization, non-repudiation | Role checks in `api/security.py`; audit hash chain; named approver |
| §12.3 | Transactions authenticated by the account holder | Ferot never moves money; it raises requests for an authorized officer |
| §11 | AML/CFT (BFIU) | Mule flags → AML queue; `drafts.py` blocks tipping-off phrases |
| §10.1(ii) | Monitor agent patterns | Cash-out agents appear in money trail and clusters |
| §15 | Customer fraud awareness | Safety line on every customer screen |
| §16.3 | Statements to Bangladesh Bank | `GET /api/v1/insights/dispute-report.csv` |

## Traceability: rule → code → test

| Rule | Code | Test |
| --- | --- | --- |
| R1 | `models/drafts.py` banned-phrase filter | `tests/test_drafts.py::test_no_refund_promises` |
| R2 | `policy/sla.py`, `models/priority.py` | `tests/test_sla.py` |
| R3 | `api/main.py` complaint channels | `tests/test_api.py::test_all_channels` |
| R4 | Customer confirmation screen | Manual check in demo |
| R5 | `assumptions.yaml` retention; export endpoint | `tests/test_api.py::test_export_requires_compliance` |
| R6 | `api/main.py` decision endpoint | `tests/test_api.py::test_rejection_needs_supervisor` |
| R7 | `models/drafts.py` tipping-off filter | `tests/test_drafts.py::test_no_tipping_off` |
| R8 | Consent stored with every case | `tests/test_api.py::test_consent_required` |
| R9 | `llm/masking.py` | `tests/test_masking.py` |
| R10 | `llm/provider.py` swappable provider | `tests/test_masking.py::test_offline_provider_no_network` |
| R11 | `api/security.py` roles | `tests/test_api.py` role tests |
| R12 | `store/audit.py` hash chain | `tests/test_audit.py::test_tamper_breaks_chain` |
| R13 | Export restricted to compliance | `tests/test_api.py::test_export_requires_compliance` |
| R14 | `policy/engine.py` hold cap | `tests/test_policy.py::test_hold_capped` |
| R15 | No upay URLs in code | `tests/test_repo_rules.py::test_no_upay_endpoints` |
| R16 | `datagen/generator.py` 010 prefix | `tests/test_datagen.py::test_numbers_use_010_prefix` |
| R17 | `config/limits.yaml` | `tests/test_datagen.py::test_limits_respected` |
| R18 | `.github/workflows/ci.yml` gitleaks; injection suite | `tests/test_injection.py` |
| R19 | Labels in UI; `docs/model_cards/` | Manual check in demo |
| R20 | Public repo, commit history, README Disclosures | Commit history |
