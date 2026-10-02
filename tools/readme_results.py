"""Refresh the README results block from reports/*.json (run after the pipeline)."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REP = ROOT / "reports"
START, END = "<!-- RESULTS:START -->", "<!-- RESULTS:END -->"


def pct(x, nd=1):
    return f"{100 * x:.{nd}f}%"


def main():
    m = json.loads((REP / "metrics_test.json").read_text(encoding="utf-8"))
    v = json.loads((REP / "metrics_val.json").read_text(encoding="utf-8"))
    aw = json.loads((REP / "agent_watch.json").read_text(encoding="utf-8"))
    dv = json.loads((REP / "data_validation.json").read_text(encoding="utf-8"))
    gen = json.loads((ROOT / "data" / "generated" / "generation_report.json").read_text(encoding="utf-8")) \
        if (ROOT / "data" / "generated" / "generation_report.json").exists() else {}
    L = []
    L.append(f"Data: {gen.get('n_transactions', 0):,} transactions, {gen.get('fraud_rows', 0):,} fraud "
             f"({pct(gen.get('fraud_share', 0), 2)}); validation **{sum(r['passed'] for r in dv)}/{len(dv)} checks pass**.")
    L += ["", "**Model comparison (test window)**", "",
          "| Model | PR-AUC | ROC-AUC | Recall @ 0.5% FPR | Recall @ 2% FPR |", "|---|---|---|---|---|"]
    for r in m["comparison"]:
        L.append(f"| {r['model']} | {r['pr_auc']:.3f} | {r['roc_auc']:.3f} | {pct(r['recall_at_fpr_0p5'])} | {pct(r['recall_at_fpr_2'])} |")
    b = m["bands"]
    L += ["", "**Policy operating points (test)**", "", "| Band reached | Alerts | Precision | Recall | False-positive rate |",
          "|---|---|---|---|---|"]
    for k in ("NUDGE+", "STEP_UP+", "HOLD+"):
        L.append(f"| {k} | {b[k]['alerts']:,} | {pct(b[k]['precision'])} | {pct(b[k]['recall'])} | {pct(b[k]['fpr'], 2)} |")
    L += ["", "**Recall by scam type (share of fraud transactions at STEP_UP or higher)**", "",
          "| Scenario | Fraud txns | Cases | NUDGE+ | STEP_UP+ | HOLD | Cases with a STEP_UP+ hit |", "|---|---|---|---|---|---|---|"]
    for r in m["per_scenario"]:
        L.append(f"| {r['scenario']} | {r['fraud_txns']} | {r['cases']} | {pct(r['recall_nudge'])} | {pct(r['recall_stepup'])} | "
                 f"{pct(r['recall_hold'])} | {pct(r['case_caught_stepup'])} |")
    i, f = m["impact"], m["friction"]
    L += ["", "**Customer impact and friction**", "",
          f"- Victim-side scam transactions (money leaving a victim) flagged STEP_UP or higher: **{pct(i['victim_side_recall_stepup'])}** "
          f"(NUDGE+ {pct(i['victim_side_recall_nudge'])}).",
          f"- Expected victim money protected: **Tk {i['expected_prevented_tk']:,} of Tk {i['victim_loss_tk']:,} "
          f"({pct(i['expected_prevented_share'])})** under the stated stop-rate assumptions.",
          f"- Honest customers over the 10 test days: {pct(f['customers_nudged_share'])} saw any warning, "
          f"{pct(f['customers_stepup_share'])} were asked for a PIN step-up, {pct(f['customers_held_share'])} had a "
          f"transaction held. Legit transactions allowed without friction: {pct(f['legit_txn_share_by_band']['ALLOW'], 2)}.",
          f"- Analyst load: {f['alerts_per_day']['HOLD']} HOLD cases/day → {f['analyst_hours_manual']} h manual vs "
          f"{f['analyst_hours_with_copilot']} h with the copilot over 10 days (assumed minutes per case)."]
    if m.get("ablation"):
        full = m["ablation"][0]["pr_auc"]
        worst = sorted(m["ablation"][1:], key=lambda r: r["pr_auc"])[:3]
        L += ["", "**Ablation:** removing a feature group and retraining costs the most PR-AUC for "
              + ", ".join(f"{r['variant'].replace('without ', '')} (−{full - r['pr_auc']:.3f})" for r in worst)
              + f" (full model {full:.3f}). Component view: "
              + "; ".join(f"{r['variant']} {r['pr_auc']:.3f}" for r in m["component_ablation"]) + "."]
    ff = m.get("fairness_flags") or []
    L += ["", "**Fairness:** groups whose false-positive rate exceeds 1.25× the overall rate (≥ 1,000 legit txns): "
          + (", ".join(f"{r['attribute']}={r['group']} (NUDGE ×{r['fpr_nudge_ratio']}, STEP_UP ×{r['fpr_stepup_ratio']})" for r in ff)
             if ff else "none")
          + ". These attributes are not model inputs. The gaps come from behaviour that correlates with the group "
            "(farmers and older customers transact rarely and in lumps, so a normal transfer looks large against their own "
            "history; small-business wallets are paid by many first-time senders). "
            "They are monitored in `reports/fairness.csv`, not corrected with per-group thresholds."]
    tr = aw["by_split"].get("test", {})
    L += ["", f"**Agent Watch (test):** {tr.get('episodes_flagged')}/{tr.get('episodes')} rogue episodes flagged, "
          f"{tr.get('false_alarm_agent_days_per_day')} false-alarm agent-days per day across 300 agents. "
          f"SC-06 agent {aw['sc06']['agent']}: score {aw['sc06']['max_score']}, "
          f"{aw['sc06']['max_volume_vs_peer_median']}× its area's median cash-out volume. Register-compromise test: "
          f"{aw['register_compromise']['harvested_flagged']}/{aw['register_compromise']['harvested_agents']} harvested agents "
          f"flagged, {aw['register_compromise']['other_agents_flagged']} other."]
    demo = m.get("demo_scenarios", [])
    L += ["", f"**Planted demo scenarios:** {sum(d.get('pass', False) for d in demo)}/{len(demo)} land in an acceptable band.", "",
          "| ID | Scenario | Expected | Actual | Score |", "|---|---|---|---|---|"]
    for d in demo:
        act = d.get("actual") + (f" ({d['policy_override'].replace('_', ' ')})" if d.get("policy_override") else "")
        L.append(f"| {d['id']} | {d['title']} | {d['expected']} | {act} | {d.get('risk_score')} |")
    L += ["", f"Validation (days 46–50) fused PR-AUC {v['val_cal_metrics'][-1]['pr_auc']:.3f}; LightGBM "
          f"{v['lgbm_trees']} trees; fusion weights { {k: abs(x) for k, x in v['fusion_weights'].items()} }. Full detail: `reports/evaluation.md`, "
          "`reports/model_card.md`."]
    block = START + "\n" + "\n".join(L) + "\n" + END
    readme = ROOT / "README.md"
    s = readme.read_text(encoding="utf-8")
    if START in s:
        s = re.sub(re.escape(START) + ".*?" + re.escape(END), lambda _: block, s, flags=re.S)
    else:
        s = s.replace("RESULTS_PLACEHOLDER", block)
    readme.write_text(s, encoding="utf-8")
    print("README results updated")


if __name__ == "__main__":
    main()
