"""Online risk engine: same feature store + same bundle as training, one transaction at a time."""
from __future__ import annotations

import gc
import os
from pathlib import Path

import numpy as np
import pandas as pd

from src.common.config import ROOT
from src.features.graph import GRAPH_FEATURES
from src.features.store import SCORED_TYPES, STREAM_FEATURES
from src.models.explain import customer_message, reasons_for
from src.models.scoring import X_of, score_frame

KIND = {"W": "C", "A": "A", "M": "M", "B": "B", "X": "X"}


def kind_of(acct: str) -> str:
    return KIND.get(acct[:1], "C")


class RiskEngine:
    def __init__(self, artifacts_dir: str | Path | None = None, bundle: dict | None = None, state: dict | None = None):
        self.dir = Path(artifacts_dir) if artifacts_dir else ROOT / "artifacts"
        if bundle is None:
            import joblib
            slim = self.dir / "serve_bundle.joblib"       # same policy, without the comparison models (no XGBoost needed)
            fed = self.dir / "fed_serve_bundle.joblib"    # PROHORI_SCORER=federated: the model trained across 8 silos
            if os.environ.get("PROHORI_SCORER") == "federated" and fed.exists():
                slim = fed
            bundle = joblib.load(slim if slim.exists() else self.dir / "model_bundle.joblib")
        self.bundle = bundle
        self.state = self.store = None
        if state is None:
            self.load_state()
        else:
            self.set_state(state)

    def load_state(self):
        """(Re)load the replayed feature store. The old one is released first: it is most of the memory."""
        import joblib
        self.state = self.store = None
        gc.collect()
        self.set_state(joblib.load(self.dir / "demo_state.joblib"))

    def set_state(self, state: dict):
        self.state = state
        self.store = state["store"]
        self.now = state["now_sec"]
        self.start = pd.Timestamp(state["start"])

    def resolve_wallet(self, x: str) -> str:
        return self.state["msisdn"].get(x, x)

    def _graph(self, node):
        if node is None:
            return (np.nan,) * 6
        return self.state["graph"]["nodes"].get(node, (0, 0, 0.0, 1, 0, 0))

    def score(self, txn: dict, commit: bool = False) -> dict:
        typ = txn.get("txn_type", "SEND_MONEY")
        if typ not in SCORED_TYPES:
            raise ValueError(f"txn_type must be one of {SCORED_TYPES}")
        src, dst = self.resolve_wallet(txn["sender_id"]), self.resolve_wallet(txn["receiver_id"])
        sk, dk = kind_of(src), kind_of(dst)
        t = int(txn.get("ts_sec") or self.now + 60)
        self.now = max(self.now, t)
        amount = float(txn["amount"])
        cust = src if typ != "ADD_MONEY" else dst
        ws = self.store.w.get(cust)
        device = txn.get("device_id") or (ws.last_device if ws is not None else None)
        channel = txn.get("channel") or "APP"
        bal = self.state["balances"]
        sb0, rb0 = bal.get(src, np.nan), bal.get(dst, np.nan)
        dow = int((self.start + pd.Timedelta(seconds=t)).dayofweek)
        store = self.store              # compute() only trims windows to `t`; state changes only on commit
        f, depth = store.compute(t, typ, src, sk, dst, dk, amount, sb0, rb0, device, channel, txn.get("area_id"), dow)
        cp = dst if typ != "ADD_MONEY" else src
        a, b = self._graph(cust), self._graph(cp)
        g = (a[0], a[1], a[2], a[3], a[5], b[0], b[1], b[2], b[3], b[4], b[5])
        row = dict(zip(STREAM_FEATURES, f))
        row.update(zip(GRAPH_FEATURES, g))
        row["txn_type"] = typ
        df = pd.DataFrame([row])
        s = score_frame(self.bundle, df).iloc[0]
        # TreeSHAP from LightGBM itself: identical to shap.TreeExplainer here (checked), without importing shap
        sv = self.bundle["lgbm"].booster_.predict(X_of(df, self.bundle["features"]), pred_contrib=True)[0][:-1]
        self.last_shap = sv                     # per-feature SHAP of the last scored transaction (copilot view)
        reasons = reasons_for(row, dict(zip(self.bundle["features"], sv)), dict(graph=s.graph, anomaly=s.anomaly))
        msg = customer_message(s.band, reasons)
        if commit:
            store.update(t, typ, src, sk, dst, dk, amount, True, device, channel, txn.get("area_id"), depth)
            if sk != "X":
                bal[src] = bal.get(src, 0.0) - amount
            if dk != "X":
                bal[dst] = bal.get(dst, 0.0) + amount
        return dict(
            sender_id=src, receiver_id=dst, txn_type=typ, amount=amount, risk_score=float(s.risk_score), band=s.band,
            policy_override=s.policy_override or None, p_fraud=round(float(s.p_fraud), 4),
            p_fraud_calibrated=round(float(s.p_cal), 4), anomaly=round(float(s.anomaly), 3), graph=round(float(s.graph), 3),
            reasons=reasons, customer_message=msg,
            evidence={k: (None if isinstance(v, float) and np.isnan(v) else round(float(v), 3)) for k, v in row.items()
                      if k != "txn_type"},
            committed=commit,
        )
