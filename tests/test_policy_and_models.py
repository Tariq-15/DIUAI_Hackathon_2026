"""Policy, reason codes and the trained bundle on the tiny world."""
import numpy as np
import pandas as pd

from src.models.explain import bn, customer_message, reasons_for
from src.models.fusion import ScoreMapper, policy_bands, to_band

BANDS = {"ALLOW": [0, 30], "NUDGE": [30, 60], "STEP_UP": [60, 80], "HOLD": [80, 101]}


def test_mapper_is_monotone_and_hits_cuts():
    rng = np.random.default_rng(0)
    fused = np.r_[rng.beta(1, 30, 5000), rng.beta(5, 2, 100)]
    y = np.r_[np.zeros(5000), np.ones(100)]
    m = ScoreMapper.fit(fused, y, {"NUDGE": 0.02, "STEP_UP": 0.005, "HOLD": 0.001}, BANDS)
    s = m(np.sort(fused))
    assert np.all(np.diff(s) >= 0) and s.min() >= 0 and s.max() <= 100
    legit_nudge = (m(fused[y == 0]) >= 30).mean()
    assert legit_nudge <= 0.021


def test_bands():
    assert list(to_band([0, 29.9, 30, 59.9, 60, 80, 100], BANDS)) == ["ALLOW", "ALLOW", "NUDGE", "NUDGE", "STEP_UP", "HOLD", "HOLD"]


def test_established_parties_cap():
    df = pd.DataFrame([dict(is_new_device=0, device_age_hours=500, hrs_since_sim_swap=720, hrs_since_dev_change=720,
                            cp_kind=0, cp_age_days=900, cp_complaints=0, g_cp_nbr_complained=0, cp_in_new_24h=0,
                            g_cp_ff_comp=1, cp_device_n_wallets=1)] * 2)
    df.loc[1, "hrs_since_sim_swap"] = 2.0                  # SIM swapped 2 h ago -> no cap
    band, why = policy_bands(df, [95, 95], BANDS, floors=False)
    assert list(band) == ["STEP_UP", "HOLD"] and why[0] == "established_parties_cap"


def test_evidence_floors_raise_allow_to_nudge():
    base = dict(pair_first=1, cp_kind=0, cp_complaints=0, g_cp_nbr_complained=0, drain_ratio=0.1, amount=1000,
                amount_vs_max=1.0)
    rows = [dict(base, cp_complaints=1),                                   # recipient already reported to 16268
            dict(base, drain_ratio=0.9, amount=20000, amount_vs_max=7.0),  # first-time transfer draining the wallet
            dict(base)]                                                    # nothing special
    band, why = policy_bands(pd.DataFrame(rows), [5, 5, 5], BANDS, cap=False)
    assert list(band) == ["NUDGE", "NUDGE", "ALLOW"]
    assert list(why[:2]) == ["reported_recipient_floor", "unusual_first_transfer_floor"]


def test_bangla_reason_codes():
    assert bn(2026) == "২০২৬"
    row = dict(cp_age_days=2.0, cp_in_uniq_24h=14, pair_first=1, cp_kind=0)
    r = reasons_for(row, {"cp_age_days": 1.0, "cp_in_new_24h": 0.8, "pair_first": 0.3})
    assert [x["code"] for x in r] == ["new_recipient", "many_senders", "first_time_pair"]
    assert "১৪ জন" in r[1]["bn"] and "২ দিন" in r[0]["bn"]
    msg = customer_message("NUDGE", r)
    assert "চেনেন" in msg["bn"] and customer_message("ALLOW", r)["bn"] == ""


def test_trained_bundle_beats_rules(tiny_bundle):
    bundle, report = tiny_bundle
    rows = {r["model"]: r for r in report["val_cal_metrics"]}
    assert rows["lightgbm"]["pr_auc"] > rows["rules_baseline"]["pr_auc"]
    assert set(bundle["weights"]) == {"clf", "anom", "graph"}


def test_score_frame_outputs(tiny_bundle, tiny_features):
    from src.models.scoring import score_frame
    bundle, _ = tiny_bundle
    te = tiny_features[tiny_features.scored & (tiny_features.split == "test")].head(500)
    out = score_frame(bundle, te)
    assert set(out.band) <= {"ALLOW", "NUDGE", "STEP_UP", "HOLD"}
    assert out.risk_score.between(0, 100).all()
