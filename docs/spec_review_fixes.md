# How the spec review was addressed

| Review point | What the code does now | Where |
|---|---|---|
| Caps conflict with scenarios (SC-02 KYC-1 victim sending 12,500; SC-01 two 29,000 cash-outs) | The ledger enforces per-txn / daily / monthly / count caps per KYC tier on every row; attempts over a cap are written as FAILED `LIMIT_EXCEEDED`. SC-02's victim is KYC2; SC-01's two big cash-outs come from two different KYC2 mules, each under the Tk 30,000 cap. Validation T4 checks no successful row breaks a cap | `config.yaml: limits`, `src/datagen/engine.py`, `src/datagen/planted.py`, T4 |
| Verify upay's current limits | Limits live in config with a `VERIFY` note. Full-KYC values follow the 2025 coverage (P2P Tk 50k/day, cash-out Tk 30k/day); KYC1 values are a stated assumption. Change config, re-run, and everything follows | `config.yaml` |
| "56%" statistic | Not used anywhere in code or reports. If a slide needs a number, cite the PRI report directly and call it a 2021 survey | README "Claims to avoid" |
| SB-05 ALLOW (26) vs NUDGE (30+) | Picked **ALLOW** as expected (remittance families cash out right after the inflow every month, so the history makes it normal), NUDGE tolerated. Scores are model outputs, so specs now state bands, not exact scores | `src/datagen/planted.py` |
| SC-06 88 vs formula 89 | Same fix: no hard-coded scores. SC-06 must be FLAGGED (score >= 80) by Agent Watch; the report prints the actual score | `src/agents/agent_watch.py`, `reports/demo_scenarios.md` |
| Too few entities for a time split | 40 collectors, 60 mule chains, 40 fake sellers, 9 rogue agents (4 episodes each: 2 train, 1 val, 1 test), 190 takeovers, 165 pressure scams, 55 SIM swaps, 36 card cases. Every scenario appears in train, val and test (T8). Agents use peer z-scores with case (episode) evaluation, not ML | `config.yaml: fraud`, T8 |
| Plant demo scenarios in the test period | All SC/SB scenarios are on days 51-58 (test). T12 checks it | `planted.py`, T12 |
| Agent-register harvesting | S1 variant (40% of takeovers): victims visit one of 4 compromised agents 1-6 days before the takeover; 4 sends to fake-NID mules within ~30 s. Agent Watch tests whether complainants cluster on one agent (Poisson vs footfall) | `fraud.py: s1_takeover`, `agent_watch.py: register_compromise` |
| Aged mule accounts | 25% of mules are bought old accounts (half dormant for 10-45 days first), logged into from the gang's phone; new mules are recruited weeks ahead and "warmed up" with small normal activity | `fraud.py: buy_account, warm_up`, T11 (aged share) |
| Card-to-wallet fraud | S8: 2-5 Add Money chunks from a stolen card (some rejected by the add-money cap), cash-out within minutes (often at the rogue agent), wallet goes silent | `fraud.py: s8_card_add_money`, SC-07 |
| Pressure scams to a personal wallet | S7: victim on their OWN phone (often 60+, USSD), may cash in first, sends to a personal wallet that cashes out within minutes and goes silent | `fraud.py: s7_guided_victim`, SC-05 |
| SIM-swap victims skew to businesspeople | S6 victims are KYC2 small-business / high-income salaried; they bank 20-30k the days before; drain up to the daily cap, sometimes again next morning | `fraud.py: s6_sim_swap`, SC-01 |
| Don't commit CSVs > 100 MB | `data/generated/` is git-ignored; the generator + config + seed rebuild it in ~10 s; a ~20k-row sample is in `data/sample/` | `.gitignore`, README |
| 512 MB Render limit | API loads only the model bundle and a few-MB demo state (feature store + last graph snapshot), never the dataset | `src/serve/export_state.py`, `Dockerfile` |
| Don't rebuild the graph per transaction | Graph snapshots are rebuilt once per hour (24 h window); a transaction sees the snapshot from the start of its hour | `src/features/graph.py` |

## Extra realism added after the first training run
The first model scored validation PR-AUC 0.99, which is not credible. Each fraud row was anomalous on several
axes while honest customers never were. Fixes, all documented in `config.yaml`:

- legit look-alikes: f-commerce sellers (many first-time payers, cash-out every evening), family hub wallets that
  forward money within minutes, quick cash-outs after receiving, shared family/shop phones (up to 4 wallets),
  new phones followed by bigger transfers, monthly 10-25k bank top-ups, 14 legit signups a day.
- harder fraud: remote-access takeovers on the victim's own phone (25% of OTP takeovers), partial drains,
  gangs on 6-15 burner phones, warmed-up mule wallets, slower cash-outs for 40% of mules.
