"""Cross-silo federated gradient boosting for the scam model: 8 division silos, raw data never pooled.

    python -m src.fl.fedgbdt                  # -> artifacts/fed_serve_bundle.joblib, reports/federated_crosssilo.json

Simulates upay's data split into 8 silos by the customer's division (it could equally be upay + partner banks).
The protocol is horizontal federated histogram boosting, the scheme behind federated XGBoost / FedTree:
  1. bins: each silo sends quantile sketches of each feature (not rows); the server merges them into shared edges
  2. each tree, level by level: each silo computes gradient / hessian / count histograms of ITS rows per node,
     feature and bin; the server receives only their sum (secure aggregation: ring masks, integers mod 2^64)
  3. the server picks the best split per node from the summed histograms and broadcasts it; silos route their
     rows locally. Leaf values come from the summed statistics.
  4. early stopping on the validation log-loss, also summed across silos
The trees are written in LightGBM's own model format, so the live policy, the SHAP explanations (LightGBM's
TreeSHAP) and the in-browser build use the federated model with no other change.

Honest limits: features are computed by the existing feature store, which sees all wallets (a real deployment
would compute cross-silo counterparty and graph features with privacy-preserving joins). The aggregated
histograms are not differentially private here; secure aggregation hides each silo's own histograms from the server.
"""
from __future__ import annotations

import argparse
import json
import time

import numpy as np
import pandas as pd

from src.common.config import ROOT, load_config, resolve

NB = 63                     # value bins per feature; bin NB is "missing"
FIXED = 2 ** 24             # fixed-point scale for exact masked sums


def secure_sum(parts: list[np.ndarray], rng) -> np.ndarray:
    """Sum silo arrays through ring masks: silo i adds s_i - s_(i+1); the server sees masked arrays only."""
    enc = np.stack([np.round(p * FIXED).astype(np.int64).view(np.uint64) for p in parts])
    s = rng.integers(0, 2 ** 63, size=enc.shape, dtype=np.uint64)
    masked = enc + s - np.roll(s, -1, axis=0)
    return masked.sum(axis=0, dtype=np.uint64).view(np.int64).astype(float) / FIXED


class Silo:
    """One data holder. Holds its rows; exposes only sketches and summed statistics."""

    def __init__(self, name, X, y, w, Xv, yv, wv):
        self.name, self.X, self.y, self.w, self.Xv, self.yv, self.wv = name, X, y, w, Xv, yv, wv

    def sketch(self, qs):
        q = np.nanquantile(self.X, qs, axis=0) if len(self.X) else np.full((len(qs), self.X.shape[1]), np.nan)
        return q, np.sum(~np.isnan(self.X), axis=0)

    def bin(self, edges):
        self.B = binize(self.X, edges)
        self.Bv = binize(self.Xv, edges)
        self.F = np.full(len(self.y), self.base)
        self.Fv = np.full(len(self.yv), self.base)

    def grads(self):
        p = 1 / (1 + np.exp(-self.F))
        return self.w * (p - self.y), self.w * p * (1 - p)

    def val_loss(self):
        p = np.clip(1 / (1 + np.exp(-self.Fv)), 1e-12, 1 - 1e-12)
        return np.array([-(self.wv * (self.yv * np.log(p) + (1 - self.yv) * np.log(1 - p))).sum(), self.wv.sum()])


def binize(X, edges):
    out = np.full(X.shape, NB, dtype=np.uint8)
    for f, e in enumerate(edges):
        col = X[:, f]
        ok = ~np.isnan(col)
        out[ok, f] = np.minimum(np.searchsorted(e, col[ok], side="left"), NB - 1)
    return out


def best_split(G, H, C, lam, min_leaf, min_gain, nvalid):
    """G, H, C: (features, NB+1) summed stats of one node; nvalid: edges per feature (thresholds exist for bins below it).
    Returns (gain, feature, bin, nan_left) or None."""
    best = None
    g_tot, h_tot = G.sum(axis=1), H.sum(axis=1)
    parent = g_tot ** 2 / (h_tot + lam)
    gl, hl, cl = np.cumsum(G[:, :NB], axis=1), np.cumsum(H[:, :NB], axis=1), np.cumsum(C[:, :NB], axis=1)
    gn, hn, cn = G[:, NB:NB + 1], H[:, NB:NB + 1], C[:, NB:NB + 1]
    c_tot = C.sum(axis=1)[:, None]
    for nan_left in (False, True):
        GL, HL, CL = (gl + gn, hl + hn, cl + cn) if nan_left else (gl, hl, cl)
        GR, HR, CR = g_tot[:, None] - GL, h_tot[:, None] - HL, c_tot - CL
        gain = GL ** 2 / (HL + lam) + GR ** 2 / (HR + lam) - parent[:, None]
        gain[(CL < min_leaf) | (CR < min_leaf)] = -np.inf
        gain[np.arange(NB)[None, :] >= nvalid[:, None]] = -np.inf   # a split needs a real edge as threshold
        f, b = np.unravel_index(np.argmax(gain), gain.shape)
        if gain[f, b] > min_gain and (best is None or gain[f, b] > best[0]):
            best = (float(gain[f, b]), int(f), int(b), nan_left)
    return best


def train(silos, n_features, edges, trees=1500, depth=6, lr=0.05, lam=1.0, min_leaf=20, min_gain=0.0, colsample=0.6,
          patience=60, seed=42, log=print):
    rng = np.random.default_rng(seed)
    nvalid = np.array([len(e) for e in edges])
    model, best_loss, best_iter, hist = [], np.inf, 0, []
    t0 = time.time()
    for it in range(trees):
        feats = np.sort(rng.choice(n_features, max(1, int(colsample * n_features)), replace=False))
        gh = [s.grads() for s in silos]
        node = [np.zeros(len(s.y), dtype=np.int32) for s in silos]          # node id per row (local)
        nodes = {0: dict(depth=0)}
        frontier = [0]
        for d in range(depth):
            if not frontier:
                break
            pos = {n: i for i, n in enumerate(frontier)}
            parts = []
            for s, (g, h), nd in zip(silos, gh, node):
                k = np.full(len(nd), -1, dtype=np.int64)
                for n, i in pos.items():
                    k[nd == n] = i
                sel = k >= 0
                arr = np.zeros((3, len(frontier), len(feats), NB + 1))
                for j, f in enumerate(feats):
                    idx = k[sel] * (NB + 1) + s.B[sel, f]
                    size = len(frontier) * (NB + 1)
                    arr[0, :, j, :] = np.bincount(idx, weights=g[sel], minlength=size).reshape(len(frontier), NB + 1)
                    arr[1, :, j, :] = np.bincount(idx, weights=h[sel], minlength=size).reshape(len(frontier), NB + 1)
                    arr[2, :, j, :] = np.bincount(idx, minlength=size).reshape(len(frontier), NB + 1)
                parts.append(arr)
            tot = secure_sum(parts, rng)                                     # the server sees only this sum
            new_frontier = []
            for n, i in pos.items():
                G, H, C = tot[0, i], tot[1, i], tot[2, i]
                nodes[n].update(G=float(G[0].sum()), H=float(H[0].sum()), C=float(C[0].sum()))
                sp = best_split(G, H, C, lam, min_leaf, min_gain, nvalid[feats]) if d < depth else None
                if sp is None:
                    continue
                gain, j, b, nan_left = sp
                f = int(feats[j])
                left, right = len(nodes), len(nodes) + 1
                nodes[n].update(split=dict(feature=f, bin=b, nan_left=nan_left, gain=gain), children=(left, right))
                nodes[left], nodes[right] = dict(depth=d + 1), dict(depth=d + 1)
                for s, nd in zip(silos, node):                               # each silo routes its own rows
                    m = nd == n
                    col = s.B[m, f]
                    go_left = np.where(col == NB, nan_left, col <= b)
                    nd[m] = np.where(go_left, left, right)
                new_frontier += [left, right]
            frontier = new_frontier
        # leaves: summed G, H for nodes without children
        leaf_ids = [n for n, v in nodes.items() if "children" not in v]
        parts = []
        for (g, h), nd in zip(gh, node):
            arr = np.zeros((3, len(nodes)))
            arr[0] = np.bincount(nd, weights=g, minlength=len(nodes))
            arr[1] = np.bincount(nd, weights=h, minlength=len(nodes))
            arr[2] = np.bincount(nd, minlength=len(nodes))
            parts.append(arr)
        tot = secure_sum(parts, rng)
        value = {n: float(-tot[0, n] / (tot[1, n] + lam) * lr) for n in leaf_ids}
        for n in leaf_ids:
            nodes[n].update(G=float(tot[0, n]), H=float(tot[1, n]), C=float(tot[2, n]), value=value[n])
        tree = dict(nodes=nodes)
        model.append(tree)
        for s, nd in zip(silos, node):
            s.F += np.array([value.get(n, 0.0) for n in range(len(nodes))])[nd]
            s.Fv += predict_tree(tree, s.Bv)
        loss = secure_sum([s.val_loss() for s in silos], rng)
        vl = loss[0] / loss[1]
        hist.append(vl)
        if vl < best_loss - 1e-7:
            best_loss, best_iter = vl, it + 1
        if (it + 1) % 50 == 0:
            log(f"[fed-gbdt] tree {it + 1}: validation log-loss {vl:.5f} (best {best_loss:.5f} at {best_iter}), {time.time() - t0:.0f}s")
        if it + 1 - best_iter >= patience:
            break
    return model[:best_iter], dict(best_iter=best_iter, val_logloss=best_loss, curve=hist)


def predict_tree(tree, B):
    nodes = tree["nodes"]
    out = np.zeros(len(B))
    node = np.zeros(len(B), dtype=np.int32)
    for _ in range(64):
        inner = np.array(["children" in nodes[n] for n in range(len(nodes))])
        act = inner[node]
        if not act.any():
            break
        for n in np.unique(node[act]):
            m = node == n
            sp, (l, r) = nodes[n]["split"], nodes[n]["children"]
            col = B[m, sp["feature"]]
            node[m] = np.where(np.where(col == NB, sp["nan_left"], col <= sp["bin"]), l, r)
    for n in np.unique(node):
        out[node == n] = nodes[n]["value"]
    return out


def to_lightgbm(model, base, edges, names) -> str:
    """Write the federated trees as a LightGBM text model (binary objective, NaN-aware splits)."""
    blocks = []
    for t, tree in enumerate(model):
        nodes = tree["nodes"]
        inner = [n for n in sorted(nodes) if "children" in nodes[n]]
        leaves = [n for n in sorted(nodes) if "children" not in nodes[n]]
        ii, li = {n: i for i, n in enumerate(inner)}, {n: i for i, n in enumerate(leaves)}
        ref = lambda n: ii[n] if n in ii else -(li[n] + 1)              # noqa: E731
        add = base if t == 0 else 0.0
        if not inner:                                                    # a single-leaf tree
            blocks.append(f"Tree={t}\nnum_leaves=1\nnum_cat=0\nsplit_feature=\nsplit_gain=\nthreshold=\ndecision_type=\n"
                          f"left_child=\nright_child=\nleaf_value={nodes[leaves[0]]['value'] + add!r}\nleaf_weight={nodes[leaves[0]]['H']!r}\n"
                          f"leaf_count={int(nodes[leaves[0]]['C'])}\ninternal_value=\ninternal_weight=\ninternal_count=\n"
                          f"is_linear=0\nshrinkage=1\n\n")
            continue
        f = lambda xs: " ".join(repr(float(x)) for x in xs)              # noqa: E731
        i_ = lambda xs: " ".join(str(int(x)) for x in xs)                # noqa: E731
        blocks.append("\n".join([
            f"Tree={t}", f"num_leaves={len(leaves)}", "num_cat=0",
            "split_feature=" + i_(nodes[n]["split"]["feature"] for n in inner),
            "split_gain=" + f(nodes[n]["split"]["gain"] for n in inner),
            "threshold=" + f(edges[nodes[n]["split"]["feature"]][nodes[n]["split"]["bin"]] for n in inner),
            "decision_type=" + i_(8 + (2 if nodes[n]["split"]["nan_left"] else 0) for n in inner),
            "left_child=" + i_(ref(nodes[n]["children"][0]) for n in inner),
            "right_child=" + i_(ref(nodes[n]["children"][1]) for n in inner),
            "leaf_value=" + f(nodes[n]["value"] + add for n in leaves),
            "leaf_weight=" + f(nodes[n]["H"] for n in leaves),
            "leaf_count=" + i_(nodes[n]["C"] for n in leaves),
            "internal_value=" + f(0.0 for n in inner),
            "internal_weight=" + f(nodes[n]["H"] for n in inner),
            "internal_count=" + i_(nodes[n]["C"] for n in inner),
            "is_linear=0", "shrinkage=1", "", ""]))
    infos = " ".join(f"[{e[0]!r}:{e[-1]!r}]" if len(e) else "none" for e in edges)
    head = "\n".join(["tree", "version=v4", "num_class=1", "num_tree_per_iteration=1", "label_index=0",
                      f"max_feature_idx={len(names) - 1}", "objective=binary sigmoid:1",
                      "feature_names=" + " ".join(names), "feature_infos=" + infos, "", ""])
    return head + "".join(blocks) + "end of trees\n\nfeature_importances:\n\nparameters:\nend of parameters\n\npandas_categorical:[]\n"


def run(cfg, trees=1500, verbose=True) -> dict:
    import joblib
    from sklearn.isotonic import IsotonicRegression
    from src.features.spec import ALL_FEATURES
    from src.models.fusion import ScoreMapper, fit_weights, fuse, graph_score
    from src.models.metrics import summary
    from src.models.scoring import X_of, score_frame
    from src.models.train import load_splits
    from src.serve.portable import PortableLGBM

    log = print if verbose else (lambda *a: None)
    t_all = time.time()
    df = load_splits(cfg)
    cust = pd.read_parquet(resolve(cfg, "data_dir") / "customers.parquet").set_index("wallet_id")["division"]
    side = np.where(df.txn_type.values == "ADD_MONEY", df.receiver_id.values, df.sender_id.values)
    df["silo"] = pd.Series(side).map(cust).fillna("Dhaka").values
    tr, vf, vc, te = (df[df.subsplit == s] for s in ("train", "val_fit", "val_cal", "test"))
    feats = list(ALL_FEATURES)
    spw = float(np.sqrt((tr.is_fraud == 0).sum() / max(tr.is_fraud.sum(), 1)))          # as train.py
    silos = []
    for name in sorted(df.silo.unique()):
        a, b = tr[tr.silo == name], vf[vf.silo == name]
        wa = np.where(a.is_fraud.values == 1, spw, 1.0)
        wb = np.where(b.is_fraud.values == 1, spw, 1.0)
        silos.append(Silo(name, X_of(a, feats).to_numpy(float), a.is_fraud.values.astype(float), wa,
                          X_of(b, feats).to_numpy(float), b.is_fraud.values.astype(float), wb))
    log(f"[fed-gbdt] {len(silos)} silos: " + ", ".join(f"{s.name} {len(s.y):,} rows / {int(s.y.sum())} fraud" for s in silos))
    # 1. shared bins from quantile sketches (no rows leave a silo)
    qs = np.linspace(0, 1, NB + 1)[1:-1]
    sk = [s.sketch(qs) for s in silos]
    edges = []
    for f in range(len(feats)):
        w = np.array([c[f] for _, c in sk], float)
        qv = np.array([q[:, f] for q, _ in sk])
        ok = (w > 0) & ~np.isnan(qv).any(axis=1)
        e = np.average(qv[ok], axis=0, weights=w[ok]) if ok.any() else np.array([0.0])
        edges.append(np.unique(e))
    # 2. base score from summed label statistics
    tot = secure_sum([np.array([(s.w * s.y).sum(), (s.w * (1 - s.y)).sum()]) for s in silos], np.random.default_rng(1))
    base = float(np.log(tot[0] / tot[1]))
    for s in silos:
        s.base = base
        s.bin(edges)
    model, info = train(silos, len(feats), edges, trees=trees, log=log)
    log(f"[fed-gbdt] {info['best_iter']} trees, best validation log-loss {info['val_logloss']:.5f}")
    text = to_lightgbm(model, base, edges, feats)
    fed = PortableLGBM(text, info["best_iter"])
    # check: LightGBM reading the exported text gives the federated model's own predictions
    chk = vf.head(2000)
    own = np.full(len(chk), base) + sum(predict_tree(t, binize(X_of(chk, feats).to_numpy(float), edges)) for t in model)
    gap = float(np.abs(fed.booster_.predict(X_of(chk, feats), raw_score=True) - own).max())
    log(f"[fed-gbdt] LightGBM text export reproduces the federated model: max raw-score gap {gap:.2e}")

    # 3. the same post-processing as train.py, on VAL-CAL (pooled here: in deployment from summed score histograms)
    serve = joblib.load(resolve(cfg, "artifacts_dir") / "serve_bundle.joblib")
    Xvc = X_of(vc, feats)
    p_vc = fed.predict_proba(Xvc)[:, 1]
    from src.models.scoring import anomaly_scores
    a_vc, g_vc = anomaly_scores(serve, vc), graph_score(vc)
    weights, _ = fit_weights(vc.is_fraud.values, p_vc, a_vc, g_vc, fpr_target=cfg["policy"]["target_fpr"]["STEP_UP"])
    mapper = ScoreMapper.fit(fuse(weights, p_vc, a_vc, g_vc), vc.is_fraud.values, cfg["policy"]["target_fpr"],
                             cfg["policy"]["bands"], cfg["policy"].get("target_precision"))
    cal = IsotonicRegression(out_of_bounds="clip", y_min=0, y_max=1).fit(p_vc, vc.is_fraud.values)
    bundle = {k: v for k, v in serve.items() if k not in ("lgbm", "weights", "mapper", "calibrator")}
    bundle.update(lgbm=fed, weights=weights, mapper=mapper.to_dict(), calibrator=cal, federated=True, fed_model_text=text)
    joblib.dump(bundle, resolve(cfg, "artifacts_dir") / "fed_serve_bundle.joblib", compress=3)

    # 4. held-out test window: federated vs central, same features, same policy procedure
    yte = te.is_fraud.values
    s_fed, s_cen = score_frame(bundle, te), score_frame(serve, te)
    comp = [summary(yte, s_cen.p_fraud.values, "central LightGBM (pooled data)"),
            summary(yte, s_fed.p_fraud.values, "federated GBDT (8 silos, secure aggregation)")]

    def bands(sc):
        out = {}
        for b in ("NUDGE", "STEP_UP", "HOLD"):
            reach = sc.band.isin({"NUDGE": ["NUDGE", "STEP_UP", "HOLD"], "STEP_UP": ["STEP_UP", "HOLD"], "HOLD": ["HOLD"]}[b]).values
            tp = int((reach & (yte == 1)).sum()); fp = int((reach & (yte == 0)).sum())
            out[b + "+"] = dict(alerts=int(reach.sum()), precision=round(tp / max(tp + fp, 1), 4),
                                recall=round(tp / max(int(yte.sum()), 1), 4), fpr=round(fp / max(int((yte == 0).sum()), 1), 5))
        return out

    planted = [p for p in json.loads((resolve(cfg, "data_dir") / "planted_scenarios.json").read_text(encoding="utf-8"))
               if p.get("key_txn_id")]
    keyed = te.set_index("txn_id")
    demo = []
    for p in planted:
        if p["key_txn_id"] in keyed.index:
            r = keyed.loc[[p["key_txn_id"]]].reset_index()
            sf = score_frame(bundle, r).iloc[0]
            demo.append(dict(id=p["id"], expected=p["expected"], acceptable=p["acceptable"], federated=sf.band,
                             ok=sf.band in p["acceptable"] or (p["expected"] == "ALLOW" and sf.band in ("ALLOW", "NUDGE"))))
    result = dict(
        method="horizontal federated histogram GBDT; quantile-sketch bins; secure aggregation of gradient/hessian/count "
               "histograms (ring masks, integers mod 2^64); early stopping on summed validation log-loss",
        silos=[dict(name=s.name, train_rows=int(len(s.y)), train_fraud=int(s.y.sum())) for s in silos],
        trees=info["best_iter"], depth=6, learning_rate=0.05, bins=NB, export_gap=gap, comparison=comp,
        bands=dict(central=bands(s_cen), federated=bands(s_fed)), planted=demo,
        shared_with_server=["per-feature quantile sketches (once)", "summed gradient/hessian/count histograms per tree level",
                            "summed validation loss", "split decisions and leaf values (the model)"],
        never_shared=["transactions", "customer or wallet identifiers", "any single silo's histograms"],
        limits=["features are computed by one feature store that sees all wallets; a real deployment needs privacy-preserving "
                "cross-silo joins for counterparty and graph features",
                "summed histograms are not differentially private; secure aggregation only hides each silo's own",
                "policy thresholds were fitted on the pooled validation window; in deployment they come from summed score histograms"],
        seconds=round(time.time() - t_all),
    )
    (ROOT / "reports" / "federated_crosssilo.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    log(json.dumps(result["comparison"], indent=1))
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trees", type=int, default=1500)
    run(load_config(), trees=ap.parse_args().trees)


if __name__ == "__main__":
    main()
