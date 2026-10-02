"""Version-neutral serving bundle, so the trained models can run in the browser (Pyodide).

    python -m src.serve.portable        # -> artifacts/portable/ (model text, tree arrays, JSON, staged world)

The joblib pickles of the training environment (pandas 3, scikit-learn 1.9, LightGBM 4.7) cannot be loaded by the
older libraries Pyodide ships, so each model is written in a neutral form and wrapped by a small adapter that
behaves like the original object in `score_frame`:
  - LightGBM: its own text model format (loaded by any LightGBM 4.x), still predicting with LightGBM itself
  - Isolation Forest: the 300 trees as arrays, scored with the same arithmetic as scikit-learn's score_samples
  - isotonic calibrator: its threshold arrays (linear interpolation, clipped), as scikit-learn does
  - everything else (features, fusion weights, score mapper, bands, policy flags): JSON
tests/test_product.py checks the adapters reproduce the original models on real transactions.

The live demo world is also saved here after staging (world.pkl.gz), so the browser starts in seconds
instead of re-staging the scenarios.
"""
from __future__ import annotations

import gzip
import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd

from src.common.config import ROOT

DIRNAME = "portable"


# ---------------------------------------------------------------- adapters
class PortableLGBM:
    """Looks like LGBMClassifier for score_frame (predict_proba) and the scorer (booster_.predict(pred_contrib))."""

    def __init__(self, model_str: str, best_iteration: int):
        import lightgbm
        self.booster_ = lightgbm.Booster(model_str=model_str)
        self.best_iteration_ = best_iteration

    def predict_proba(self, X):
        p = self.booster_.predict(X)
        return np.column_stack([1.0 - p, p])


class PortableIsolationForest:
    """scikit-learn IsolationForest.score_samples, re-implemented on exported tree arrays (same arithmetic)."""

    def __init__(self, arrays: dict, denominator: float):
        off = arrays["offsets"]
        cut = lambda a: [a[off[i]:off[i + 1]] for i in range(len(off) - 1)]       # noqa: E731
        self.left, self.right = cut(arrays["left"]), cut(arrays["right"])
        self.feature, self.threshold, self.leaf = cut(arrays["feature"]), cut(arrays["threshold"]), cut(arrays["leaf"])
        self.denominator = float(denominator)

    def score_samples(self, X):
        X = np.asarray(X, dtype=np.float32)                       # scikit-learn trees compare float32 inputs
        n = X.shape[0]
        rows = np.arange(n)
        depths = np.zeros(n, dtype=np.float64)
        for left, right, feat, thr, leaf in zip(self.left, self.right, self.feature, self.threshold, self.leaf):
            node = np.zeros(n, dtype=np.int64)
            while True:
                inner = left[node] != -1
                if not inner.any():
                    break
                go_left = X[rows, np.maximum(feat[node], 0)] <= thr[node]
                node = np.where(inner, np.where(go_left, left[node], right[node]), node)
            depths += leaf[node]
        scores = 2 ** (-np.divide(depths, self.denominator, out=np.ones_like(depths), where=self.denominator != 0))
        return -scores


class PortableIsotonic:
    def __init__(self, x, y, clip: bool):
        self.x, self.y, self.clip = np.asarray(x, float), np.asarray(y, float), clip

    def predict(self, p):
        p = np.asarray(p, dtype=float)
        if self.clip:
            p = np.clip(p, self.x[0], self.x[-1])
        return np.interp(p, self.x, self.y)


# ---------------------------------------------------------------- export (training environment)
def export_bundle(bundle: dict, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    lg = bundle["lgbm"]
    (out / "lgbm.txt").write_text(lg.booster_.model_to_string(num_iteration=lg.best_iteration_), encoding="utf-8")

    iff = bundle["iforest"]
    lefts, rights, feats, thrs, leaves, offsets = [], [], [], [], [], [0]
    for t, (est, cols) in enumerate(zip(iff.estimators_, iff.estimators_features_)):
        tr = est.tree_
        cols = np.asarray(cols)
        lefts.append(tr.children_left.astype(np.int32))
        rights.append(tr.children_right.astype(np.int32))
        f = tr.feature.astype(np.int64)
        feats.append(np.where(f >= 0, cols[np.maximum(f, 0)], -2).astype(np.int16))   # tree column -> model column
        thrs.append(tr.threshold.astype(np.float64))
        # the per-leaf term scikit-learn adds: decision-path length + average path length of the leaf - 1
        leaves.append((iff._decision_path_lengths[t] + iff._average_path_length_per_tree[t] - 1.0).astype(np.float64))
        offsets.append(offsets[-1] + tr.node_count)
    from sklearn.ensemble._iforest import _average_path_length
    denom = len(iff.estimators_) * float(_average_path_length([iff.max_samples_])[0])
    np.savez_compressed(out / "iforest.npz", left=np.concatenate(lefts), right=np.concatenate(rights),
                        feature=np.concatenate(feats), threshold=np.concatenate(thrs), leaf=np.concatenate(leaves),
                        offsets=np.asarray(offsets, np.int64), if_ref=np.asarray(bundle["if_ref"], np.float64))
    cal = bundle["calibrator"]
    meta = dict(
        features=list(bundle["features"]), weights=bundle["weights"], mapper=bundle["mapper"], bands=bundle["bands"],
        established_parties_cap=bool(bundle.get("established_parties_cap", True)),
        evidence_floors=bool(bundle.get("evidence_floors", True)),
        if_fill={k: float(v) for k, v in bundle["if_fill"].items()}, if_denominator=denom,
        calibrator=dict(x=cal.X_thresholds_.tolist(), y=cal.y_thresholds_.tolist(), clip=cal.out_of_bounds == "clip"),
        lgbm_best_iteration=int(lg.best_iteration_), lgbm_trees=int(lg.booster_.num_trees()),
    )
    (out / "bundle.json").write_text(json.dumps(meta), encoding="utf-8")


def load_bundle(d: str | Path) -> dict:
    d = Path(d)
    meta = json.loads((d / "bundle.json").read_text(encoding="utf-8"))
    arr = np.load(d / "iforest.npz")
    return dict(
        features=meta["features"], weights=meta["weights"], mapper=meta["mapper"], bands=meta["bands"],
        established_parties_cap=meta["established_parties_cap"], evidence_floors=meta["evidence_floors"],
        lgbm=PortableLGBM((d / "lgbm.txt").read_text(encoding="utf-8"), meta["lgbm_best_iteration"]),
        iforest=PortableIsolationForest({k: arr[k] for k in ("left", "right", "feature", "threshold", "leaf", "offsets")},
                                        meta["if_denominator"]),
        if_fill=pd.Series(meta["if_fill"]), if_ref=arr["if_ref"],
        calibrator=PortableIsotonic(meta["calibrator"]["x"], meta["calibrator"]["y"], meta["calibrator"]["clip"]),
    )


def save_world(world, path: Path) -> None:
    with gzip.open(path, "wb", compresslevel=6) as f:
        pickle.dump(world.snapshot(), f, protocol=4)


def export(artifacts: Path | None = None, verbose=True) -> Path:
    import joblib
    from .live import LiveWorld
    art = Path(artifacts) if artifacts else ROOT / "artifacts"
    out = art / DIRNAME
    export_bundle(joblib.load(art / "serve_bundle.joblib"), out)
    lw = LiveWorld(art)                                   # stages the scenarios with the original models
    save_world(lw, out / "world.pkl.gz")
    if verbose:
        size = sum(p.stat().st_size for p in out.iterdir()) / 1e6
        print(f"[portable] {', '.join(sorted(p.name for p in out.iterdir()))} -> {out} ({size:.1f} MB)")
    return out


if __name__ == "__main__":
    export()
