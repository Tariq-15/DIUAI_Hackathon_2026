"""Single source of truth for model feature names and groups (used by training, ablation,
SHAP reason codes and the API). Protected attributes (gender, age band, division,
urban/rural, segment) are deliberately NOT features; they are only used for the fairness audit."""
from __future__ import annotations

from .graph import GRAPH_FEATURES
from .store import FEATURE_GROUPS as _STREAM_GROUPS

FEATURE_GROUPS = {k: list(v) for k, v in _STREAM_GROUPS.items()}
FEATURE_GROUPS["graph"] = [f for f in GRAPH_FEATURES if "complained" not in f]
FEATURE_GROUPS["complaints"] = FEATURE_GROUPS["complaints"] + [f for f in GRAPH_FEATURES if "complained" in f]
ALL_FEATURES = [f for g in FEATURE_GROUPS.values() for f in g]
CATEGORICAL = ["f_type", "channel", "cp_kind"]

# behaviour-deviation subset for the unsupervised Isolation Forest
ANOMALY_FEATURES = ["log_amount", "amount_z", "drain_ratio", "hour_surprise", "is_new_device", "device_age_hours",
                    "cust_out_cnt_1h", "cust_new_cp_24h", "pair_first", "cp_age_days", "cp_in_new_24h",
                    "passthrough_ratio", "chain_depth", "hours_since_last", "channel_switch", "is_new_area",
                    "hrs_since_sim_swap", "device_n_wallets", "cust_woke_gap_days", "cp_woke_gap_days"]

PROTECTED = ["gender", "age_band", "division", "urban_rural", "segment", "kyc_level", "cust_channel"]
