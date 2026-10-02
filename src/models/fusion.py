"""Graph rule score, score fusion, 0-100 mapping and the four-band decision policy.

Decision logic is plain, auditable Python (not ML):
  fused  = w_clf * p_fraud + w_anom * anomaly_tail + w_graph * graph_score
           (anomaly_tail = how far into the top 10% of unusual behaviour; 0 for ordinary activity)
  score  = monotone piecewise-linear map of `fused`, with knots placed so that each band cut
           equals an operating point chosen on validation (target false-positive rates)
  band   = ALLOW <30 <= NUDGE <60 <= STEP_UP <80 <= HOLD
  then   floors (hard evidence -> at least NUDGE) and the established-parties cap (HOLD -> STEP_UP)
"""
from __future__ import annotations

import itertools

import numpy as np
import pandas as pd


BANDS = ("ALLOW", "NUDGE", "STEP_UP", "HOLD")


def _sig(x):
    return 1.0 / (1.0 + np.exp(-x))


def graph_score(df: pd.DataFrame) -> np.ndarray:
    """Named, explainable network patterns -> [0, 1]. Each component maps to a reason code."""
    g = lambda c: df[c].fillna(0).to_numpy(dtype=float)     # noqa: E731
    age = df["cp_age_days"].fillna(9999).to_numpy(dtype=float)
    collector = _sig((g("cp_in_new_24h") - 6) / 1.5) * (age < 14)
    collector_cashout = _sig((g("cust_in_new_24h") - 6) / 1.5) * (df["txn_type"].to_numpy() == "CASH_OUT")
    chain = np.clip(0.35 * g("chain_depth") - 0.05, 0, 1) * (g("passthrough_ratio") > 0.5)
    fastflow = np.clip((np.maximum(g("g_cp_ff_comp"), g("g_cust_ff_comp")) - 3) / 6, 0, 1)
    reported = np.clip(0.6 * g("cp_complaints") + 0.2 * g("g_cp_nbr_complained"), 0, 1)
    shared_dev = np.clip((g("cp_device_n_wallets") - 2) / 4, 0, 1)
    parts = np.vstack([collector, collector_cashout, chain, fastflow, reported, shared_dev])
    return parts.max(axis=0)


GRAPH_PATTERNS = ["collector_fan_in", "collector_cash_out", "pass_through_chain", "fast_flow_network",
                  "reported_number", "shared_device_ring"]


class ScoreMapper:
    def __init__(self, knots_x, knots_y):
        self.kx = np.asarray(knots_x, float)
        self.ky = np.asarray(knots_y, float)

    @classmethod
    def fit(cls, fused: np.ndarray, y: np.ndarray, target_fpr: dict, bands: dict, target_precision: dict | None = None):
        """Each cut = the stricter of (false-positive-rate target, precision target) on validation."""
        legit = fused[y == 0]
        q = lambda f: float(np.quantile(legit, 1 - f))   # noqa: E731
        cuts = {b: q(target_fpr[b]) for b in ("NUDGE", "STEP_UP", "HOLD")}
        if target_precision:
            from sklearn.metrics import precision_recall_curve
            p, _, thr = precision_recall_curve(y, fused)
            for b in cuts:
                ok = np.flatnonzero(p[:-1] >= target_precision[b])
                if len(ok):
                    cuts[b] = max(cuts[b], float(thr[ok.min()]))
        tn, ts, th = cuts["NUDGE"], cuts["STEP_UP"], cuts["HOLD"]
        eps = 1e-6
        ts = max(ts, tn + eps)
        th = max(th, ts + eps)
        top = max(1.0, th + eps)
        kx = [0.0, tn, ts, th, top]
        ky = [0.0, bands["NUDGE"][0], bands["STEP_UP"][0], bands["HOLD"][0], 100.0]
        return cls(kx, ky)

    def __call__(self, fused):
        return np.interp(np.asarray(fused, float), self.kx, self.ky)

    def to_dict(self):
        return dict(knots_x=self.kx.tolist(), knots_y=self.ky.tolist())


def established_parties(df: pd.DataFrame) -> np.ndarray:
    """Own long-used phone, no recent SIM swap / new login, recipient an old unreported wallet."""
    g = lambda c, d: df[c].fillna(d).to_numpy(dtype=float)     # noqa: E731
    return ((g("is_new_device", 1) == 0) & (g("device_age_hours", 0) >= 72) & (g("hrs_since_sim_swap", 0) >= 72) &
            (g("hrs_since_dev_change", 0) >= 72) & (g("cp_kind", 1) == 0) & (g("cp_age_days", 0) > 180) &
            (g("cp_complaints", 1) == 0) & (g("g_cp_nbr_complained", 1) == 0) & (g("cp_in_new_24h", 99) < 3) &
            (g("g_cp_ff_comp", 99) < 3) & (g("cp_device_n_wallets", 99) <= 2))


def evidence_floors(df: pd.DataFrame) -> dict:
    """Hard evidence that always earns at least a NUDGE (a cheap, one-tap warning)."""
    g = lambda c, d: df[c].fillna(d).to_numpy(dtype=float)     # noqa: E731
    first_p2p = (g("pair_first", 0) == 1) & (g("cp_kind", 1) == 0)
    reported = first_p2p & ((g("cp_complaints", 0) >= 1) | (g("g_cp_nbr_complained", 0) >= 2))
    unusual = first_p2p & (g("drain_ratio", 0) >= 0.7) & (g("amount", 0) >= 5000) & (g("amount_vs_max", 0) >= 3)
    return {"reported_recipient_floor": reported, "unusual_first_transfer_floor": unusual}


def policy_bands(df: pd.DataFrame, score, bands: dict, cap: bool = True, floors: bool = True):
    """Score -> band, then the auditable policy overrides. Returns (band, override_reason)."""
    band = to_band(score, bands)
    why = np.full(len(band), "", dtype=object)
    if floors:
        for name, m in evidence_floors(df).items():
            up = m & (band == "ALLOW")
            band[up] = "NUDGE"
            why[up] = name
    if cap:
        m = (band == "HOLD") & established_parties(df)
        band[m] = "STEP_UP"
        why[m] = "established_parties_cap"
    return band, why


def to_band(score, bands: dict):
    s = np.asarray(score, float)
    out = np.full(s.shape, "ALLOW", dtype=object)
    out[s >= bands["NUDGE"][0]] = "NUDGE"
    out[s >= bands["STEP_UP"][0]] = "STEP_UP"
    out[s >= bands["HOLD"][0]] = "HOLD"
    return out


def fit_weights(y, p, anom, graph, fpr_target=0.005, step=0.05):
    """Grid over the simplex; maximise recall at the STEP_UP false-positive rate, tie-break PR-AUC."""
    from .metrics import pr_auc, recall_at_fpr          # training only: keeps scikit-learn out of serving
    best = None
    grid = np.round(np.arange(0, 1 + 1e-9, step), 3)
    for wc, wa in itertools.product(grid, grid):
        wg = round(1 - wc - wa, 3)
        if wg < -1e-9 or wc < 0.3:                       # the supervised model stays the backbone
            continue
        f = wc * p + wa * anomaly_tail(anom) + wg * graph
        key = (round(recall_at_fpr(y, f, fpr_target), 4), round(pr_auc(y, f), 4))
        if best is None or key > best[0]:
            best = (key, dict(clf=float(wc), anom=float(wa), graph=abs(float(max(wg, 0.0)))))
    return best[1], dict(recall_at_fpr=best[0][0], pr_auc=best[0][1])


def anomaly_tail(anom):
    """Isolation-Forest percentile -> 0 below the 90th percentile, 0..1 across the top 10%."""
    return np.clip((np.asarray(anom, float) - 0.9) / 0.1, 0, 1)


def fuse(weights, p, anom, graph):
    return weights["clf"] * p + weights["anom"] * anomaly_tail(anom) + weights["graph"] * graph
