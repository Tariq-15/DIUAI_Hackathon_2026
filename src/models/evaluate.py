"""One-shot evaluation on the untouched TEST window (days 51-60).

    python -m src.models.evaluate                  # everything
    python -m src.models.evaluate --no-ablation    # skip the 10 retrains

Writes reports/metrics_test.json, evaluation.md, per_scenario.csv, fairness.csv,
demo_scenarios.md, model_card.md and figures/*.png.
"""
from __future__ import annotations

import argparse
import json
import time

import numpy as np
import pandas as pd
from sklearn.metrics import precision_recall_curve

from src.common.config import load_config, resolve, save_json
from src.datagen.generate import load as load_data
from src.features.spec import ALL_FEATURES, FEATURE_GROUPS
from . import plots
from .baselines import rules_score
from .explain import customer_message, explainer, reasons_for, shap_matrix
from .fusion import BANDS, fuse
from .metrics import band_report, per_scenario_recall, pr_auc, recall_at_fpr, summary, wilson_interval
from .scoring import X_of, load_bundle, score_frame
from .train import fit_lgbm, load_splits

VICTIM_ROLES = {"takeover_drain", "victim_payment", "buyer_payment", "coerced_send", "card_add_money"}
SCEN_LABEL = {"S1": "S1 OTP/PIN takeover", "S2": "S2 collector wallet", "S3": "S3 mule chain",
              "S5": "S5 fake online seller", "S6": "S6 SIM-swap takeover", "S7": "S7 guided victim (pressure)",
              "S8": "S8 card Add-Money"}
FAIR_COLS = ["gender", "age_band", "urban_rural", "cust_channel", "division", "segment", "kyc_level"]


def fairness(te: pd.DataFrame, customers: pd.DataFrame) -> pd.DataFrame:
    c = customers.rename(columns={"channel": "cust_channel"}).set_index("wallet_id")[FAIR_COLS]
    d = te.join(c, on="cust_id")
    rank = {b: i for i, b in enumerate(BANDS)}
    d["r"] = d.band.map(rank)
    legit = d[d.is_fraud == 0]
    base_n = float((legit.r >= 1).mean())
    base_s = float((legit.r >= 2).mean())
    rows = []
    for col in FAIR_COLS:
        for g, sub in d.groupby(col):
            lg, fr = sub[sub.is_fraud == 0], sub[sub.is_fraud == 1]
            fn = float((lg.r >= 1).mean()) if len(lg) else np.nan
            fs = float((lg.r >= 2).mean()) if len(lg) else np.nan
            rows.append(dict(attribute=col, group=g, legit_txns=len(lg), fraud_txns=len(fr),
                             false_nudge=int((lg.r >= 1).sum()), false_stepup=int((lg.r >= 2).sum()),
                             fpr_nudge_ci_low=wilson_interval(int((lg.r >= 1).sum()), len(lg))[0],
                             fpr_nudge_ci_high=wilson_interval(int((lg.r >= 1).sum()), len(lg))[1],
                             fpr_stepup_ci_low=wilson_interval(int((lg.r >= 2).sum()), len(lg))[0],
                             fpr_stepup_ci_high=wilson_interval(int((lg.r >= 2).sum()), len(lg))[1],
                             minimum_support=len(lg) >= 1000,
                             intervention_rate=float((sub.r >= 1).mean()),
                             fpr_nudge=round(fn, 5), fpr_stepup=round(fs, 5),
                             fpr_nudge_ratio=round(fn / base_n, 2) if base_n else np.nan,
                             fpr_stepup_ratio=round(fs / base_s, 2) if base_s else np.nan,
                             tpr_stepup=round(float((fr.r >= 2).mean()), 3) if len(fr) else np.nan))
    out = pd.DataFrame(rows)
    out["flag"] = (out.legit_txns >= 1000) & ((out.fpr_nudge_ratio > 1.25) | (out.fpr_stepup_ratio > 1.25))
    return out


def ablation(df, bundle, te, verbose=True):
    tr, vf = df[df.subsplit == "train"], df[df.subsplit == "val_fit"]
    y = te.is_fraud.values
    rows = [dict(variant="full model", pr_auc=round(pr_auc(y, te.p_fraud), 4),
                 recall_at_fpr_0p5=round(recall_at_fpr(y, te.p_fraud, 0.005), 4))]
    for g, cols in FEATURE_GROUPS.items():
        feats = [f for f in ALL_FEATURES if f not in cols]
        m = fit_lgbm(bundle["params"], X_of(tr, feats), tr.is_fraud.values, X_of(vf, feats), vf.is_fraud.values,
                     bundle["seed"], 3000, 100)
        p = m.predict_proba(X_of(te, feats))[:, 1]
        rows.append(dict(variant=f"without {g}", pr_auc=round(pr_auc(y, p), 4),
                         recall_at_fpr_0p5=round(recall_at_fpr(y, p, 0.005), 4)))
        if verbose:
            print(f"   [ablation] without {g:<15} PR-AUC {rows[-1]['pr_auc']:.4f}", flush=True)
    w = bundle["weights"]
    combos = {"LightGBM only": dict(clf=1, anom=0, graph=0), "LightGBM + IsolationForest": dict(clf=w["clf"], anom=w["anom"], graph=0),
              "LightGBM + graph rules": dict(clf=w["clf"], anom=0, graph=w["graph"]), "fused (all three)": w}
    comp = []
    for name, ww in combos.items():
        f = fuse(ww, te.p_fraud.values, te.anomaly.values, te.graph.values)
        comp.append(dict(variant=name, pr_auc=round(pr_auc(y, f), 4), recall_at_fpr_0p5=round(recall_at_fpr(y, f, 0.005), 4)))
    return pd.DataFrame(rows), pd.DataFrame(comp)


def evaluate(cfg, ablate=True, do_shap=True, verbose=True):
    log = (lambda *a: print(*a, flush=True)) if verbose else (lambda *a: None)
    t_all = time.time()
    bundle = load_bundle(cfg)
    data = load_data(cfg)
    df = load_splits(cfg)
    te = df[df.split == "test"].copy()
    te = te.join(score_frame(bundle, te))
    y = te.is_fraud.values
    Xte = X_of(te)
    rep, fig = resolve(cfg, "reports_dir"), resolve(cfg, "reports_dir") / "figures"
    log(f"[eval] test rows {len(te):,}, fraud {int(y.sum())}, cases {te[te.is_fraud == 1].case_id.nunique()}")

    # ---------------- model comparison
    comps = {"rules baseline": rules_score(te), "logistic regression": bundle["logit"].predict_proba(Xte)[:, 1],
             "XGBoost": bundle["xgb"].predict_proba(Xte)[:, 1], "LightGBM": te.p_fraud.values,
             "Isolation Forest": te.anomaly.values, "graph rules": te.graph.values, "Prohori fused score": te.fused.values}
    comparison = [summary(y, s, k) for k, s in comps.items()]
    curves = {}
    for k in ("rules baseline", "logistic regression", "Isolation Forest", "LightGBM", "Prohori fused score"):
        p, r, _ = precision_recall_curve(y, comps[k])
        curves[k] = (p, r, pr_auc(y, comps[k]))
    plots.pr_curves(curves, fig / "pr_curves_test.png")
    bands = band_report(te)
    cuts = {b: cfg["policy"]["bands"][b][0] for b in ("NUDGE", "STEP_UP", "HOLD")}
    plots.score_hist(te.risk_score.values, y, cuts, fig / "score_distribution_test.png")

    # ---------------- per scenario / role / victim side
    ps = per_scenario_recall(te)
    ps["label"] = ps.scenario.map(SCEN_LABEL).fillna(ps.scenario)
    plots.scenario_recall(ps.sort_values("scenario"), fig / "recall_by_scenario_test.png")
    rank = {b: i for i, b in enumerate(BANDS)}
    te["r"] = te.band.map(rank)
    fr = te[te.is_fraud == 1]
    per_role = fr.groupby("fraud_role").agg(n=("r", "size"), recall_nudge=("r", lambda v: (v >= 1).mean()),
                                            recall_stepup=("r", lambda v: (v >= 2).mean()),
                                            recall_hold=("r", lambda v: (v >= 3).mean())).round(3).reset_index()
    vict = fr[fr.fraud_role.isin(VICTIM_ROLES)]
    legit = te[te.is_fraud == 0]
    stop = cfg["policy"]["stop_rate"]
    vict_ok = vict[vict.status == "SUCCESS"]
    amt = data["transactions"].set_index("txn_id").amount
    v_amt = amt.reindex(vict_ok.txn_id).values
    prevented = float(np.sum(v_amt * vict_ok.band.map(stop).values))
    total_loss = float(np.sum(v_amt))
    cases = fr.groupby("case_id").agg(scenario=("scenario", "first"), max_r=("r", "max"))
    impact = dict(
        evidence='modeled impact with assumed behavior on synthetic transactions',
        victim_side_txns=int(len(vict)), victim_side_recall_nudge=round(float((vict.r >= 1).mean()), 3),
        victim_side_recall_stepup=round(float((vict.r >= 2).mean()), 3),
        victim_side_recall_hold=round(float((vict.r >= 3).mean()), 3),
        victim_loss_tk=round(total_loss), expected_prevented_tk=round(prevented),
        expected_prevented_share=round(prevented / max(total_loss, 1), 3), stop_rate_assumption=stop,
        cases_in_test=int(len(cases)), cases_caught_stepup=round(float((cases.max_r >= 2).mean()), 3),
        cases_caught_nudge=round(float((cases.max_r >= 1).mean()), 3),
    )
    impact['sensitivity'] = [dict(stop_rate_multiplier=multiplier,
                                  expected_prevented_tk=round(prevented * multiplier),
                                  expected_prevented_share=prevented * multiplier / max(total_loss, 1))
                             for multiplier in (0., .5, 1.)]
    impact['analyst_sensitivity'] = [dict(copilot_minutes=minutes,
                                         manual_minutes=cfg['policy']['analyst_minutes']['manual'],
                                         modeled_hours_saved=int((te.r >= 3).sum()) *
                                         (cfg['policy']['analyst_minutes']['manual'] - minutes) / 60)
                                   for minutes in (3, 10, 20)]
    days = te.day.nunique()
    lc = legit.groupby("cust_id").r.max()
    friction = dict(
        legit_customers=int(len(lc)), customers_nudged_share=round(float((lc >= 1).mean()), 4),
        customers_stepup_share=round(float((lc >= 2).mean()), 4), customers_held_share=round(float((lc >= 3).mean()), 4),
        legit_txn_share_by_band=legit.band.value_counts(normalize=True).reindex(list(BANDS), fill_value=0).round(5).to_dict(),
        alerts_per_day=dict(HOLD=round(float((te.r >= 3).sum() / days), 1), STEP_UP=round(float((te.r == 2).sum() / days), 1),
                            NUDGE=round(float((te.r == 1).sum() / days), 1)),
    )
    am = cfg["policy"]["analyst_minutes"]
    holds = int((te.r >= 3).sum())
    friction["analyst_hours_manual"] = round(holds * am["manual"] / 60, 1)
    friction["analyst_hours_with_copilot"] = round(holds * am["with_copilot"] / 60, 1)
    log(f"[eval] fused PR-AUC {comparison[-1]['pr_auc']:.4f} | victim-side recall STEP_UP+ {impact['victim_side_recall_stepup']:.1%}"
        f" | expected prevented {impact['expected_prevented_share']:.1%} of Tk {total_loss:,.0f}")

    # ---------------- fairness
    fair = fairness(te, data["customers"])
    fair.to_csv(rep / "fairness.csv", index=False)
    by = fair[fair.attribute.isin(["gender", "age_band", "urban_rural", "cust_channel"])]
    plots.hbar({f"{a}: {g}": v for a, g, v in zip(by.attribute, by.group, by.fpr_nudge)}, fig / "fairness_fpr_nudge.png",
               "Legit transactions warned (NUDGE or higher), by group", "False-positive rate",
               ref=float((legit.r >= 1).mean()), ref_label="overall", fmt="{:.2%}")

    # ---------------- ablation
    abl, comp_abl = (None, None)
    if ablate:
        abl, comp_abl = ablation(df, bundle, te, verbose)
        full = abl.pr_auc.iloc[0]
        plots.hbar({r.variant.replace("without ", ""): full - r.pr_auc for r in abl.iloc[1:].itertuples()},
                   fig / "ablation_pr_auc_drop.png", "PR-AUC lost when a feature group is removed",
                   "Drop in test PR-AUC (higher = group matters more)", fmt="{:.4f}")

    # ---------------- SHAP + reasons + demo scenarios
    shap_global, demo = {}, []
    if do_shap:
        expl = explainer(bundle)
        rng = np.random.default_rng(cfg["seed"])
        samp = pd.concat([te[te.is_fraud == 1], te[te.is_fraud == 0].sample(min(3000, len(legit)), random_state=1)])
        sv = shap_matrix(expl, X_of(samp))
        mean_abs = pd.Series(np.abs(sv).mean(0), index=ALL_FEATURES).sort_values(ascending=False)
        shap_global = mean_abs.head(20).round(4).to_dict()
        grp = {g: float(mean_abs.reindex(c).fillna(0).sum()) for g, c in FEATURE_GROUPS.items()}
        plots.hbar(dict(list(shap_global.items())[:15]), fig / "shap_global_top15.png",
                   "What drives the fraud score (mean |SHAP|, test sample)", "mean |SHAP value| (log-odds)", fmt="{:.3f}")
        planted = data["planted"]
        aw_path = rep / "agent_watch.json"
        aw = json.loads(aw_path.read_text(encoding="utf-8")) if aw_path.exists() else None
        allrows = pd.read_parquet(resolve(cfg, "features_dir") / "features.parquet")
        for p in planted:
            rec = dict(id=p["id"], title=p["title"], expected=p["expected"], acceptable=p["acceptable"])
            if p["id"] == "SC-06":
                a = (aw or {}).get("sc06") or {}
                rec.update(actual="FLAGGED" if a.get("flagged") else ("not run" if not aw else "NOT FLAGGED"),
                           risk_score=a.get("max_score"), agent=p.get("agent"))
                rec["pass"] = bool(a.get("flagged"))
                demo.append(rec)
                continue
            row = allrows[allrows.txn_id == p["key_txn_id"]]
            if row.empty:
                rec.update(actual="missing", **{"pass": False})
                demo.append(rec)
                continue
            s = score_frame(bundle, row).iloc[0]
            svr = shap_matrix(expl, X_of(row))[0]
            fr_row = row[ALL_FEATURES].iloc[0].to_dict()
            fr_row["txn_type"] = row.txn_type.iloc[0]
            reasons = reasons_for(fr_row, dict(zip(ALL_FEATURES, svr)), dict(graph=s.graph, anomaly=s.anomaly))
            msg = customer_message(s.band, reasons)
            rec.update(txn_id=p["key_txn_id"], txn_type=row.txn_type.iloc[0], actual=s.band, risk_score=float(s.risk_score),
                       policy_override=s.policy_override or "",
                       p_fraud=round(float(s.p_fraud), 4), anomaly=round(float(s.anomaly), 3), graph=round(float(s.graph), 3),
                       reasons_en=[r["en"] for r in reasons], reasons_bn=[r["bn"] for r in reasons],
                       customer_message_bn=msg["bn"], customer_message_en=msg["en"])
            rec["pass"] = s.band in p["acceptable"]
            demo.append(rec)

    # ---------------- write everything
    metrics = dict(seed=cfg['seed'], splits=cfg['splits'], evidence='synthetic simulation',
                   uncertainty_note='Wilson transaction intervals; not customer-cluster adjusted',
                   comparison=comparison, bands=bands, impact=impact, friction=friction,
                   per_scenario=ps.drop(columns="label").to_dict("records"), per_role=per_role.to_dict("records"),
                   fairness_flags=fair[fair.flag].to_dict("records"), shap_top20=shap_global,
                   ablation=None if abl is None else abl.to_dict("records"),
                   component_ablation=None if comp_abl is None else comp_abl.to_dict("records"),
                   demo_scenarios=demo, fusion_weights=bundle["weights"], seconds=round(time.time() - t_all, 1))
    save_json(metrics, rep / "metrics_test.json")
    ps.to_csv(rep / "per_scenario.csv", index=False)
    (rep / "demo_scenarios.md").write_text(demo_md(demo), encoding="utf-8")
    (rep / "evaluation.md").write_text(evaluation_md(metrics, cfg), encoding="utf-8")
    (rep / "model_card.md").write_text(model_card(metrics, cfg, bundle), encoding="utf-8")
    log(f"[eval] demo scenarios: {sum(d.get('pass', False) for d in demo)}/{len(demo)} in an acceptable band")
    log(f"[eval] done in {metrics['seconds']}s -> {rep}")
    return metrics


# ====================================================================== markdown writers
def _tbl(rows, cols, fmt=None):
    fmt = fmt or {}
    out = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for r in rows:
        out.append("| " + " | ".join(fmt.get(c, "{}").format(r.get(c, "")) for c in cols) + " |")
    return "\n".join(out)


def demo_md(demo):
    lines = ["# Planted demo scenarios (test window, unseen by training)", "",
             "| ID | Scenario | Expected | Actual | Score | Pass |", "|---|---|---|---|---|---|"]
    for d in demo:
        act = d.get("actual") + (f" ({d['policy_override'].replace('_', ' ')})" if d.get("policy_override") else "")
        lines.append(f"| {d['id']} | {d['title']} | {d['expected']} | {act} | {d.get('risk_score', '')} | "
                     f"{'yes' if d.get('pass') else '**no**'} |")
    lines.append("")
    for d in demo:
        if d.get("reasons_en"):
            lines += [f"## {d['id']}: {d['title']}", f"- txn `{d.get('txn_id')}` ({d.get('txn_type')}), band **{d['actual']}**, "
                      f"score {d['risk_score']} (p_fraud {d['p_fraud']}, anomaly {d['anomaly']}, graph {d['graph']})"]
            lines += [f"- {e}  \n  {b}" for e, b in zip(d["reasons_en"], d["reasons_bn"])]
            if d.get("customer_message_bn"):
                lines += [f"- Customer sees: {d['customer_message_bn']}", f"  ({d['customer_message_en']})"]
            lines.append("")
    return "\n".join(lines)


def evaluation_md(m, cfg):
    c = m["comparison"]
    imp, fr = m["impact"], m["friction"]
    L = ["# Test-window evaluation (days 51-60, never used for training or tuning)", "",
         "## Model comparison", _tbl(c, ["model", "pr_auc", "roc_auc", "recall_at_fpr_0p5", "recall_at_fpr_2", "precision_at_recall_50"]),
         "", "![PR curves](figures/pr_curves_test.png)", "",
         "## Decision policy (bands)", "```", json.dumps(m["bands"], indent=1), "```",
         "![Score distribution](figures/score_distribution_test.png)", "",
         "## Recall by scam type", _tbl(m["per_scenario"], ["scenario", "fraud_txns", "cases", "recall_nudge", "recall_stepup",
                                                          "recall_hold", "case_caught_stepup"]),
         "", "![Recall by scenario](figures/recall_by_scenario_test.png)", "",
         "## Recall by role in the scam", _tbl(m["per_role"], ["fraud_role", "n", "recall_nudge", "recall_stepup", "recall_hold"]),
         "", "## Customer impact (assumption-based estimate)",
         f"- Victim-side scam transactions in test: **{imp['victim_side_txns']}**; flagged STEP_UP or higher: "
         f"**{imp['victim_side_recall_stepup']:.1%}** (NUDGE or higher {imp['victim_side_recall_nudge']:.1%}).",
         f"- Victim money at risk: Tk {imp['victim_loss_tk']:,}; expected prevented with stop rates "
         f"{imp['stop_rate_assumption']}: **Tk {imp['expected_prevented_tk']:,} ({imp['expected_prevented_share']:.1%})**.",
         f"- Scam cases with at least one STEP_UP+ intervention: {imp['cases_caught_stepup']:.1%} of {imp['cases_in_test']}.",
         "", "## Friction for honest customers",
         f"- Legit customers active in test: {fr['legit_customers']:,}; ever nudged {fr['customers_nudged_share']:.2%}, "
         f"ever asked to step up {fr['customers_stepup_share']:.2%}, ever held {fr['customers_held_share']:.2%}.",
         f"- Alerts per day: {fr['alerts_per_day']}. Analyst time for HOLD cases: {fr['analyst_hours_manual']} h manual vs "
         f"{fr['analyst_hours_with_copilot']} h with the copilot (assumed {cfg['policy']['analyst_minutes']} minutes per case).",
         "", "## Fairness", "Groups with >= 1,000 legit transactions whose false-positive rate is > 1.25x the overall rate:",
         ("none" if not m["fairness_flags"] else _tbl(m["fairness_flags"], ["attribute", "group", "legit_txns", "fpr_nudge", "fpr_nudge_ratio", "fpr_stepup_ratio"])),
         "", "Full table: `fairness.csv`. ![Fairness](figures/fairness_fpr_nudge.png)", ""]
    if m.get("ablation"):
        L += ["## Ablation", _tbl(m["ablation"], ["variant", "pr_auc", "recall_at_fpr_0p5"]), "",
              _tbl(m["component_ablation"], ["variant", "pr_auc", "recall_at_fpr_0p5"]), "",
              "![Ablation](figures/ablation_pr_auc_drop.png)", ""]
    if m.get("shap_top20"):
        L += ["## Explainability", "Top features by mean |SHAP| on a test sample:", "",
              _tbl([dict(feature=k, mean_abs_shap=v) for k, v in m["shap_top20"].items()], ["feature", "mean_abs_shap"]),
              "", "![SHAP](figures/shap_global_top15.png)", "", "Planted demo scenarios: see `demo_scenarios.md`."]
    L += ["", "> Synthetic data with injected patterns: treat these as upper bounds. Real upay data will be noisier, and "
              "the honest comparison is the gap over the rules baseline and per-scenario recall, not the absolute PR-AUC."]
    return "\n".join(L)


def model_card(m, cfg, bundle):
    c = {r["model"]: r for r in m["comparison"]}
    f = c["Prohori fused score"]
    return "\n".join([
        "# Model card: Prohori transaction risk score", "",
        "## Intended use",
        "Score customer-initiated money movement (Send Money, Cash Out, Payment, Add Money) before it executes, and map the "
        "score to ALLOW / NUDGE / STEP_UP / HOLD. A human (the customer, or an upay analyst for HOLD) makes every "
        "consequential decision. Not for credit, KYC or account closure decisions.", "",
        "## Models",
        f"- LightGBM classifier ({bundle['lgbm'].best_iteration_} trees, Optuna-tuned on validation), "
        f"{len(bundle['features'])} features from a streaming feature store (no future information).",
        "- Isolation Forest on behaviour-deviation features (unsupervised, labels unused).",
        "- Graph rules on hourly 24 h transaction-graph snapshots (fan-in collectors, pass-through chains, fast-flow "
        "networks, reported numbers, shared devices).",
        f"- Fusion weights fitted on validation: {bundle['weights']}; score knots map validation false-positive targets "
        f"{cfg['policy']['target_fpr']} to band cut-offs 30 / 60 / 80.", "",
        "## Data",
        f"Synthetic upay-like world (seed {cfg['seed']}): {cfg['world']['n_customers']:,} customers, {cfg['world']['n_agents']} "
        f"agents, {cfg['world']['n_days']} days; fraud scenarios S1-S8 injected with ground truth. Time split: train days "
        f"{cfg['splits']['train_days']}, validation {cfg['splits']['val_days']}, test {cfg['splits']['test_days']}. No real "
        "personal data; phone numbers use the unallocated 010 prefix.", "",
        "## Performance (test window)",
        f"- PR-AUC {f['pr_auc']}, ROC-AUC {f['roc_auc']}, recall at 0.5% FPR {f['recall_at_fpr_0p5']} "
        f"(rules baseline PR-AUC {c['rules baseline']['pr_auc']}).",
        f"- Victim-side recall at STEP_UP+: {m['impact']['victim_side_recall_stepup']:.1%}; legit customers ever held: "
        f"{m['friction']['customers_held_share']:.2%}.",
        "- Weakest scenarios: " + ", ".join(f"{r['scenario']} ({r['recall_stepup']:.0%})" for r in
                                             sorted(m["per_scenario"], key=lambda r: r["recall_stepup"])[:2]) + ".", "",
        "## Fairness",
        "Gender, age band, division, urban/rural, segment are NOT model inputs. False-positive rates are audited per "
        "group (reports/fairness.csv); flagged groups: "
        + (", ".join(f"{r['attribute']}={r['group']} (x{r['fpr_nudge_ratio']})" for r in m["fairness_flags"]) or "none") + ".", "",
        "## Limitations",
        "- Trained on synthetic patterns; absolute numbers will drop on real data. Re-fit thresholds on real validation data.",
        "- Social-engineering scams on the victim's own phone (S5, S7) are hardest; the warning is a nudge, not a block.",
        "- Complaint-derived features depend on helpline reporting rates.",
        "- Stop rates per band in the impact estimate are assumptions, not measurements.", "",
        "## Responsible use",
        "Models score, plain rules decide, people confirm. The LLM copilot (if enabled) only rewrites the structured evidence "
        "into language and never changes a band. Warnings never name or accuse the recipient.",
    ])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=None)
    ap.add_argument("--no-ablation", action="store_true")
    ap.add_argument("--no-shap", action="store_true")
    a = ap.parse_args()
    evaluate(load_config(a.config), ablate=not a.no_ablation, do_shap=not a.no_shap)


if __name__ == "__main__":
    main()
