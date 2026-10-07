"""Metrics that survive judge questions on imbalanced data (no accuracy anywhere)."""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, precision_recall_curve, roc_auc_score, roc_curve


def wilson_interval(successes, total, z=1.959963984540054):
    """95% binomial interval; undefined for an empty denominator.

    Transactions from the same customer are correlated: these intervals are
    descriptive, not customer-cluster-adjusted causal evidence.
    """
    if not 0 <= successes <= total:
        raise ValueError("successes must be between zero and total")
    if total == 0:
        return [None, None]
    p = successes / total
    den = 1 + z * z / total
    center = (p + z * z / (2 * total)) / den
    half = z * ((p * (1 - p) / total + z * z / (4 * total * total)) ** .5) / den
    return [0. if successes == 0 else max(0., center - half),
            1. if successes == total else min(1., center + half)]


def pr_auc(y, s):
    return float(average_precision_score(y, s)) if y.sum() else float("nan")


def roc_auc(y, s):
    return float(roc_auc_score(y, s)) if 0 < y.sum() < len(y) else float("nan")


def recall_at_fpr(y, s, fpr_target):
    fpr, tpr, _ = roc_curve(y, s)
    return float(np.interp(fpr_target, fpr, tpr))


def precision_at_recall(y, s, recall_target):
    p, r, _ = precision_recall_curve(y, s)
    ok = r >= recall_target
    return float(p[ok].max()) if ok.any() else 0.0


def at_threshold(y, s, thr):
    pred = s >= thr
    tp = int((pred & (y == 1)).sum())
    fp = int((pred & (y == 0)).sum())
    fn = int((~pred & (y == 1)).sum())
    tn = int((~pred & (y == 0)).sum())
    return dict(threshold=float(thr), tp=tp, fp=fp, fn=fn, tn=tn,
                precision=tp / max(tp + fp, 1), recall=tp / max(tp + fn, 1), fpr=fp / max(fp + tn, 1),
                alerts=int(pred.sum()))


def summary(y, s, name=""):
    y = np.asarray(y)
    s = np.asarray(s, dtype=float)
    return dict(model=name, pr_auc=round(pr_auc(y, s), 4), roc_auc=round(roc_auc(y, s), 4),
                recall_at_fpr_0p1=round(recall_at_fpr(y, s, 0.001), 4),
                recall_at_fpr_0p5=round(recall_at_fpr(y, s, 0.005), 4),
                recall_at_fpr_2=round(recall_at_fpr(y, s, 0.02), 4),
                precision_at_recall_50=round(precision_at_recall(y, s, 0.5), 4),
                n=int(len(y)), positives=int(y.sum()))


def band_report(df: pd.DataFrame, band_col="band", y_col="is_fraud", order=("ALLOW", "NUDGE", "STEP_UP", "HOLD")):
    """Precision / recall / FPR for 'band >= X' operating points."""
    rank = {b: i for i, b in enumerate(order)}
    r = df[band_col].map(rank).values
    y = df[y_col].values
    out = {}
    for b in order[1:]:
        pred = r >= rank[b]
        tp = int((pred & (y == 1)).sum())
        fp = int((pred & (y == 0)).sum())
        out[f"{b}+"] = dict(alerts=int(pred.sum()), tp=tp, fp=fp, precision=round(tp / max(tp + fp, 1), 4),
                            fn=int(y.sum()) - tp, tn=int((y == 0).sum()) - fp,
                            precision_ci=wilson_interval(tp, tp + fp),
                            recall_ci=wilson_interval(tp, int(y.sum())),
                            fpr_ci=wilson_interval(fp, int((y == 0).sum())),
                            recall=round(tp / max(int(y.sum()), 1), 4), fpr=round(fp / max(int((y == 0).sum()), 1), 5))
    out["band_counts"] = df[band_col].value_counts().reindex(list(order), fill_value=0).to_dict()
    return out


def per_scenario_recall(df: pd.DataFrame, band_col="band", order=("ALLOW", "NUDGE", "STEP_UP", "HOLD")):
    rank = {b: i for i, b in enumerate(order)}
    fr = df[df.is_fraud == 1].copy()
    fr["r"] = fr[band_col].map(rank)
    rows = []
    for sc, g in fr.groupby("scenario"):
        rows.append(dict(scenario=sc, fraud_txns=int(len(g)), cases=int(g.case_id.nunique()),
                         recall_nudge=round(float((g.r >= 1).mean()), 3), recall_stepup=round(float((g.r >= 2).mean()), 3),
                         recall_hold=round(float((g.r >= 3).mean()), 3),
                         case_caught_stepup=round(float(g.groupby("case_id").r.max().ge(2).mean()), 3)))
    return pd.DataFrame(rows)
