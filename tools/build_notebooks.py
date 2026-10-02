"""Generate the notebooks in notebooks/ (thin wrappers over src/, so code lives in one place).

    python tools/build_notebooks.py
    python tools/build_notebooks.py --execute     # also run 01-06 against the existing full-run outputs
"""
from __future__ import annotations

import argparse
from pathlib import Path

import nbformat as nbf

ROOT = Path(__file__).resolve().parents[1]
NB = ROOT / "notebooks"

SETUP = r'''# --- setup: find the repo root (works locally, in Colab and on Kaggle) -------------------------
import os, sys, shutil, subprocess
from pathlib import Path

REPO_URL = ""          # optional: your GitHub repo URL, cloned if the code is not found
ROOT = None
for cand in [Path.cwd(), Path.cwd().parent, *Path("/kaggle/input").glob("*")] if Path("/kaggle/input").exists() else [Path.cwd(), Path.cwd().parent]:
    if (cand / "src" / "pipeline.py").exists():
        ROOT = cand
        break
if ROOT is None and REPO_URL:
    subprocess.run(["git", "clone", "--depth", "1", REPO_URL, "prohori"], check=True)
    ROOT = Path("prohori").resolve()
assert ROOT is not None, "Put this notebook next to the repo (or add the repo as a Kaggle dataset / set REPO_URL)"
if str(ROOT).startswith("/kaggle/input"):          # Kaggle inputs are read-only: work on a copy
    dst = Path("/kaggle/working/prohori")
    shutil.copytree(ROOT, dst, dirs_exist_ok=True)
    ROOT = dst
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))
print("repo root:", ROOT)
'''

IMPORTS = r'''import json
import warnings
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from IPython.display import Image, Markdown, display

warnings.filterwarnings("ignore")
pd.set_option("display.max_columns", 40, "display.width", 200)
from src.common.config import load_config, resolve
from src.models import plots
plots.style()
cfg = load_config()                 # config.yaml (seed 42, full scale)
REPORTS = resolve(cfg, "reports_dir")
'''


def md(s):
    return nbf.v4.new_markdown_cell(s.strip())


def code(s):
    return nbf.v4.new_code_cell(s.strip())


def nb(cells, name):
    n = nbf.v4.new_notebook()
    n.metadata["kernelspec"] = {"display_name": "Python 3", "language": "python", "name": "python3"}
    n.metadata["language_info"] = {"name": "python"}
    n.cells = cells
    NB.mkdir(exist_ok=True)
    nbf.write(n, NB / name)
    return NB / name


def kaggle():
    return nb([
        md("""
# 00 · Prohori end to end (Kaggle / Colab / laptop)

Runs the full pipeline: **generate → validate (T1–T14) → features → train → Agent Watch → evaluate → export**.

| Step | Time on a laptop / Kaggle CPU (measured, full scale) |
|---|---|
| Generate ~680k transactions | ~10 s |
| Validate T1–T14 | ~25 s |
| Streaming features + hourly graph | ~1 min |
| Train (Optuna 30 trials) | ~8–15 min (set `TRIALS = 0` for ~1 min) |
| Agent Watch + evaluate (with ablation & SHAP) | ~2 min |

No GPU needed. On Kaggle: add this repo as a Dataset (or set `REPO_URL` in the next cell) and run all.
To keep the generated data, save `/kaggle/working/prohori/data/generated` as a private Kaggle Dataset.
"""),
        code(SETUP),
        code("""
# Kaggle images already ship most of these; this only fills gaps.
import importlib.util, subprocess, sys
need = [p for p in ("lightgbm", "xgboost", "shap", "optuna", "networkx", "yaml", "pyarrow") if importlib.util.find_spec(p) is None]
if need:
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", *[{"yaml": "pyyaml"}.get(p, p) for p in need]], check=True)
print("missing before install:", need or "none")
"""),
        md("## Parameters"),
        code("""
SCALE = 1.0      # 1.0 = 10k customers / ~680k txns; 0.1 = quick smoke run
TRIALS = 30      # Optuna trials for LightGBM (0 = use config params)
OUT_ROOT = None  # e.g. "runs/small" to keep a scaled run separate from the full one
"""),
        code("""
import subprocess, sys
cmd = [sys.executable, "-m", "src.pipeline", "--trials", str(TRIALS)]
if SCALE != 1.0:
    cmd += ["--scale", str(SCALE)]
if OUT_ROOT:
    cmd += ["--out-root", OUT_ROOT]
print(" ".join(cmd))
r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
print(r.stdout[-6000:])
print(r.stderr[-3000:])
assert r.returncode == 0, "pipeline failed - see output above"
"""),
        md("## Results"),
        code(IMPORTS.replace('cfg = load_config()                 # config.yaml (seed 42, full scale)',
                             'cfg = load_config(scale=SCALE if SCALE != 1.0 else None)\nif OUT_ROOT:\n    cfg["paths"]["reports_dir"] = OUT_ROOT + "/reports"')),
        code("""
display(Markdown((REPORTS / "data_validation.md").read_text(encoding="utf-8")))
m = json.loads((REPORTS / "metrics_test.json").read_text(encoding="utf-8"))
display(pd.DataFrame(m["comparison"]))
display(pd.DataFrame(m["per_scenario"]))
print(json.dumps(m["impact"], indent=1))
"""),
        code("""
for f in ("pr_curves_test.png", "recall_by_scenario_test.png", "shap_global_top15.png", "agent_watch_sc06.png"):
    p = REPORTS / "figures" / f
    if p.exists():
        display(Image(filename=str(p)))
display(Markdown((REPORTS / "demo_scenarios.md").read_text(encoding="utf-8")))
"""),
    ], "00_kaggle_end_to_end.ipynb")


def data_nb():
    return nb([
        md("""
# 01 · Synthetic upay world: generation and validation

The generator (`src/datagen/`) simulates 60 days of an upay-like MFS: normal life (salaries on days 1–5,
Friday remittance-style transfers, Eid salami, bills mid-month, cash-in/out at agents), legit look-alikes
(new wallets, shared family phones, f-commerce sellers, family hub wallets, phone changes) and eight injected
fraud scenarios **S1–S8** with ground truth. A ledger enforces balances and KYC limits on every row.
"""),
        code(SETUP), code(IMPORTS),
        code("""
REBUILD = False      # True = regenerate (seed 42, ~10 s) even if data exists
from src.datagen.generate import build, write, load
data_dir = resolve(cfg, "data_dir")
if REBUILD or not (data_dir / "transactions.parquet").exists():
    write(build(cfg), cfg)
data = load(cfg)
tx, lab, cust = data["transactions"], data["labels"], data["customers"]
print(json.dumps(data["report"], indent=1, default=str)[:2500])
"""),
        md("## Validation T1–T14 (`python -m src.validation.run_checks`)"),
        code("""
from src.validation.checks import Checker
res = Checker(data, cfg).run(skip_repro=True)      # T14 (re-generates twice) runs in the CLI / pytest
pd.DataFrame([{"test": r["id"], "check": r["name"], "passed": r["passed"]} for r in res])
"""),
        code("""
for r in res:
    if r["id"] in ("T5", "T10", "T11", "T13"):
        print(r["id"], json.dumps(r["details"], default=str)[:700], "\\n")
"""),
        md("## Daily rhythm: salary days, Friday, Eid"),
        code("""
x = tx.merge(lab[["txn_id", "is_fraud"]], on="txn_id")
day = x.groupby([x.ts.dt.floor("D"), "txn_type"]).size().unstack(fill_value=0)
fig, ax = plt.subplots(figsize=(9, 3.6))
for i, t in enumerate(["SEND_MONEY", "MOBILE_RECHARGE", "PAYMENT", "CASH_IN"]):
    ax.plot(day.index, day[t], color=plots.SERIES[i], label=t.replace("_", " ").title())
eid = [pd.Timestamp(cfg["world"]["start_date"]) + pd.Timedelta(days=d - 1) for d in cfg["world"]["eid_days"]]
ax.axvspan(eid[0], eid[-1] + pd.Timedelta(days=1), color=plots.GRID, alpha=0.8, linewidth=0)
ax.text(eid[0], ax.get_ylim()[1] * 0.95, " Eid", color=plots.INK2, fontsize=9, va="top")
ax.set_title("Transactions per day by type"); ax.set_ylabel("Transactions"); ax.legend(ncol=4, loc="lower right")
plt.tight_layout(); plt.show()
"""),
        md("## Hour of day: fraud is NOT only a night problem"),
        code("""
sc = x[x.txn_type.isin(["SEND_MONEY", "CASH_OUT", "PAYMENT", "ADD_MONEY"])]
h = pd.crosstab(sc.ts.dt.hour, sc.is_fraud, normalize="columns")
fig, ax = plt.subplots(figsize=(7, 3.4))
ax.plot(h.index, h[0], color=plots.SERIES[0], label="legit")
ax.plot(h.index, h[1], color=plots.SERIES[1], label="fraud")
ax.set_xlabel("Hour"); ax.set_ylabel("Share of transactions"); ax.set_title("Hourly profile, legit vs fraud")
ax.legend(); plt.tight_layout(); plt.show()
"""),
        md("## Fraud by scenario and split (every scenario appears in train, val and test)"),
        code("""
fr = lab[lab.is_fraud == 1]
pd.crosstab(fr.scenario, fr.split).reindex(columns=["train", "val", "test"])
"""),
        code("""
data["cases"].groupby("scenario").agg(cases=("case_id", "size"), fraud_txns=("n_fraud_txns", "sum"),
                                       variants=("variant", lambda v: ", ".join(sorted(set(v) - {""}))))
"""),
        md("## One planted case end to end: SC-01 SIM-swap takeover"),
        code("""
ev = data["account_events"]
display(ev[ev.case_id == "SC-01"][["ts", "wallet_id", "event_type", "device_id", "area_id"]])
c = x.merge(lab[["txn_id", "case_id", "fraud_role"]], on="txn_id")
c[c.case_id == "SC-01"][["ts", "txn_type", "sender_id", "receiver_id", "amount", "status", "device_id", "fraud_role"]]
"""),
        md("## Population (used for the fairness audit only, never as model inputs)"),
        code("""
pd.concat({k: cust[k].value_counts(normalize=True).round(3) for k in ["segment", "kyc_level", "channel", "gender", "age_band", "urban_rural"]}).to_frame("share")
"""),
    ], "01_data_generation_and_validation.ipynb")


def features_nb():
    return nb([
        md("""
# 02 · Streaming feature store + hourly graph features

`src/features/store.py` replays transactions in time order: **compute features from the past, then update
state**. Graph features (`src/features/graph.py`) come from 24 h snapshots rebuilt once per hour, so a
transaction never sees a snapshot newer than the start of its hour.
"""),
        code(SETUP), code(IMPORTS),
        code("""
REBUILD = False
from src.features.build import build as build_features
from src.features.spec import FEATURE_GROUPS, ALL_FEATURES
fpath = resolve(cfg, "features_dir") / "features.parquet"
if REBUILD or not fpath.exists():
    build_features(cfg).to_parquet(fpath, index=False)
F = pd.read_parquet(fpath)
S = F[F.scored]
print(f"{len(F):,} rows, {len(S):,} scored (Send Money / Cash Out / Payment / Add Money), {len(ALL_FEATURES)} features")
pd.DataFrame([(g, len(c), ", ".join(c)) for g, c in FEATURE_GROUPS.items()], columns=["group", "n", "features"])
"""),
        md("## Leakage check: delete the future, features must not change"),
        code("""
from src.datagen.generate import load
from src.features.build import replay
data = load(cfg)
cut = data["transactions"].ts.quantile(0.3)
small = dict(data)
small["transactions"] = data["transactions"][data["transactions"].ts < cut].reset_index(drop=True)
small["account_events"] = data["account_events"][data["account_events"].ts < cut]
small["complaints"] = data["complaints"][data["complaints"].ts < cut]
part, _, _ = replay(small, cfg, verbose=False)
full = F.iloc[:len(part)][part.columns].to_numpy()
same = (full == part.to_numpy()) | (np.isnan(full) & np.isnan(part.to_numpy()))
print(f"rows compared: {len(part):,}; identical feature values: {same.mean():.6f}")
"""),
        md("## Anti-shortcut: no single feature separates fraud on its own"),
        code("""
from sklearn.metrics import roc_auc_score
y = S.is_fraud.values
auc = {f: max(a, 1 - a) for f in ALL_FEATURES for a in [roc_auc_score(y, S[f].fillna(-999).values)]}
top = pd.Series(auc).sort_values(ascending=False).head(15).round(3)
plots.hbar(top.to_dict(), REPORTS / "figures" / "univariate_auc.png", "Best single features (ROC-AUC alone)", "ROC-AUC", fmt="{:.3f}")
display(Image(filename=str(REPORTS / "figures" / "univariate_auc.png")))
"""),
        md("## What a collector wallet looks like to the counterparty features"),
        code("""
f = S[S.txn_type == "SEND_MONEY"]
g = f.assign(kind=np.where(f.is_fraud == 1, "fraud: " + f.scenario, "legit"))
g.groupby("kind")[["cp_age_days", "cp_in_new_24h", "pair_first", "amount_z", "device_age_hours", "chain_depth"]].median().round(2)
"""),
    ], "02_feature_engineering.ipynb")


def train_nb():
    return nb([
        md("""
# 03 · Model training (train days 1–40, tune on 41–45, calibrate/fuse on 46–50)

- **LightGBM** (Optuna-tuned, class imbalance via `scale_pos_weight`), with **XGBoost** and **logistic
  regression** as comparisons and a hand-written **rules baseline**.
- **Isolation Forest** on behaviour-deviation features (no labels).
- **Graph rules** (fan-in collector, pass-through chain, fast-flow network, reported number, shared device).
- **Fusion** weights and **0–100 score knots** fitted on the second half of validation. The test window is not read.
"""),
        code(SETUP), code(IMPORTS),
        code("""
RETRAIN = False      # True = retrain here (TRIALS below); False = load the saved bundle + report
TRIALS = 30
if RETRAIN or not (resolve(cfg, "artifacts_dir") / "model_bundle.joblib").exists():
    from src.models.train import train
    bundle, report = train(cfg, trials=TRIALS)
else:
    from src.models.scoring import load_bundle
    bundle = load_bundle(cfg)
    report = json.loads((REPORTS / "metrics_val.json").read_text(encoding="utf-8"))
print("rows:", report["split_rows"], "fraud:", report["split_fraud"])
print("LightGBM params:", report["lgbm_params"], "trees:", report["lgbm_trees"])
print("fusion weights:", report["fusion_weights"], "| score knots:", np.round(report["score_mapper"]["knots_x"], 4))
"""),
        md("## Validation comparison (val_cal, days 46–50)"),
        code("""
pd.DataFrame(report["val_cal_metrics"]).set_index("model")
"""),
        code("""
print(json.dumps(report["val_cal_bands"], indent=1))
"""),
        md("## Optuna search"),
        code("""
p = REPORTS / "optuna_trials.csv"
if p.exists():
    t = pd.read_csv(p)
    fig, ax = plt.subplots(figsize=(7, 3.2))
    ax.plot(t.number, t.value, "o", color=plots.SERIES[0], markersize=4, label="trial")
    ax.plot(t.number, t.value.cummax(), color=plots.SERIES[1], label="best so far")
    ax.set_xlabel("Trial"); ax.set_ylabel("Val PR-AUC"); ax.set_title("Optuna: LightGBM validation PR-AUC"); ax.legend()
    plt.tight_layout(); plt.show()
    display(t.sort_values("value", ascending=False).head(5))
"""),
        md("## Feature importance (gain)"),
        code("""
imp = pd.Series(report["top_features_gain"]).head(20)
plots.hbar((imp / imp.sum()).round(4).to_dict(), REPORTS / "figures" / "lgbm_gain_top20.png", "LightGBM gain share, top 20", "Share of total gain", fmt="{:.1%}")
display(Image(filename=str(REPORTS / "figures" / "lgbm_gain_top20.png")))
"""),
    ], "03_model_training.ipynb")


def eval_nb():
    return nb([
        md("""
# 04 · Test evaluation (days 51–60, touched once)

PR-AUC, recall at fixed false-positive rates, per-scenario and per-role recall, victim money protected
(assumption-based), friction for honest customers, fairness by group, feature-group ablation, SHAP, and the
planted demo scenarios with Bangla warnings.
"""),
        code(SETUP), code(IMPORTS),
        code("""
RERUN = False
if RERUN or not (REPORTS / "metrics_test.json").exists():
    from src.models.evaluate import evaluate
    evaluate(cfg)
m = json.loads((REPORTS / "metrics_test.json").read_text(encoding="utf-8"))
pd.DataFrame(m["comparison"]).set_index("model")
"""),
        code("""display(Image(filename=str(REPORTS / "figures" / "pr_curves_test.png")))
display(Image(filename=str(REPORTS / "figures" / "score_distribution_test.png")))
print(json.dumps(m["bands"], indent=1))"""),
        md("## Which scams get caught"),
        code("""display(pd.DataFrame(m["per_scenario"]))
display(pd.DataFrame(m["per_role"]))
display(Image(filename=str(REPORTS / "figures" / "recall_by_scenario_test.png")))"""),
        md("## Impact and friction"),
        code("""print(json.dumps(m["impact"], indent=1))
print(json.dumps(m["friction"], indent=1))"""),
        md("## Fairness (protected attributes are not model inputs; we audit false positives per group)"),
        code("""fair = pd.read_csv(REPORTS / "fairness.csv")
display(fair[fair.attribute.isin(["gender", "age_band", "urban_rural", "cust_channel", "kyc_level"])])
display(Image(filename=str(REPORTS / "figures" / "fairness_fpr_nudge.png")))"""),
        md("## Ablation: what each feature group / model adds"),
        code("""if m.get("ablation"):
    display(pd.DataFrame(m["ablation"]))
    display(pd.DataFrame(m["component_ablation"]))
    display(Image(filename=str(REPORTS / "figures" / "ablation_pr_auc_drop.png")))"""),
        md("## Explainability"),
        code("""display(Image(filename=str(REPORTS / "figures" / "shap_global_top15.png")))
display(Markdown((REPORTS / "demo_scenarios.md").read_text(encoding="utf-8")))"""),
    ], "04_test_evaluation.ipynb")


def agents_nb():
    return nb([
        md("""
# 05 · Agent Watch (rule-based, case-level evaluation)

With ~9 rogue agents, a supervised model would learn 9 examples. Agent Watch instead scores each agent-day
against **peers in the same area on the same day** (volume vs peer median, night share, share paid to
wallets under 7 days old, pass-through share, share already reported to 16268) and evaluates per **episode**.
A second signal tests whether fraud victims cluster on one agent's register (Poisson test vs footfall).
"""),
        code(SETUP), code(IMPORTS),
        code("""
RERUN = False
if RERUN or not (REPORTS / "agent_watch.json").exists():
    from src.agents.agent_watch import run
    run(cfg)
aw = json.loads((REPORTS / "agent_watch.json").read_text(encoding="utf-8"))
display(pd.DataFrame(aw["by_split"]).T)
print("register compromise:", aw["register_compromise"])
print("SC-06:", aw["sc06"])
display(Image(filename=str(REPORTS / "figures" / "agent_watch_sc06.png")))
"""),
        code("""
ad = pd.read_parquet(resolve(cfg, "features_dir") / "agent_scores.parquet")
ad.groupby("is_episode")[["cashouts", "volume", "volume_ratio", "night_share", "young_share", "pass_share", "reported_share", "score"]].median().round(2)
"""),
        code("""pd.DataFrame(aw["top_agents_last_day"])"""),
    ], "05_agent_watch.ipynb")


def api_nb():
    return nb([
        md("""
# 06 · Inference: the risk engine behind the API

The deployed service ships only `artifacts/model_bundle.joblib` and `artifacts/demo_state.joblib`
(the feature store replayed to the end of the window + the last graph snapshot): a few MB, so it fits
Render's 512 MB free tier. Start it with `uvicorn src.serve.api:app`.
"""),
        code(SETUP), code(IMPORTS),
        code("""
from src.serve.scorer import RiskEngine
eng = RiskEngine()
wallets = list(eng.store.w)[:3]
r = eng.score(dict(sender_id=wallets[0], receiver_id=wallets[1], amount=1500))
print(r["band"], r["risk_score"], [x["en"] for x in r["reasons"]])
"""),
        md("## A large first-time transfer from an unknown phone at 02:00"),
        code("""
t = eng.now + 3600 * ((26 - (eng.now % 86400) // 3600) % 24)       # next 02:00
r = eng.score(dict(sender_id=wallets[0], receiver_id=wallets[2], amount=25000, device_id="DV9999999", ts_sec=int(t)))
print(r["band"], r["risk_score"])
for x in r["reasons"]:
    print("-", x["en"], "|", x["bn"])
print(r["customer_message"]["bn"])
"""),
        md("## Recorded outcomes for the planted scenarios"),
        code("""pd.DataFrame(eng.state["demo"])[["id", "title", "expected", "actual", "risk_score", "pass"]]"""),
    ], "06_inference_api_demo.ipynb")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--execute", action="store_true")
    a = ap.parse_args()
    paths = [kaggle(), data_nb(), features_nb(), train_nb(), eval_nb(), agents_nb(), api_nb()]
    print("\n".join(str(p) for p in paths))
    if a.execute:
        from nbconvert.preprocessors import ExecutePreprocessor
        for p in paths[1:]:
            n = nbf.read(p, as_version=4)
            ExecutePreprocessor(timeout=1800, kernel_name="python3").preprocess(n, {"metadata": {"path": str(NB)}})
            nbf.write(n, p)
            print("executed", p.name)


if __name__ == "__main__":
    main()
