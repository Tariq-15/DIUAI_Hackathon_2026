from ferot.policy.engine import recommend


def probs(top: str, p: float) -> dict:
    base = {"genuine_wrong_send": 0.0, "scam_victim": 0.0, "double_recovery": 0.0, "false_claim": 0.0,
            "technical_failure": 0.0}
    base[top] = p
    rest = (1 - p) / 4
    return {k: (v if k == top else rest) for k, v in base.items()}


def test_hold_capped():
    """R14: a hold never exceeds the disputed amount or what is still in the wallet."""
    rec = recommend(probs("genuine_wrong_send", 0.95), {"amount": 5000, "recoverable_now": 4200})
    assert rec["rule_id"] == "R-GEN-01" and rec["hold_amount"] == 4200
    rec = recommend(probs("scam_victim", 0.9), {"amount": 3000, "recoverable_now": 9999})
    assert rec["hold_amount"] == 3000


def test_no_balance_means_consent_only():
    rec = recommend(probs("genuine_wrong_send", 0.95), {"amount": 5000, "recoverable_now": 0})
    assert rec["rule_id"] == "R-GEN-02" and rec["hold_amount"] == 0


def test_rejections_need_a_supervisor():
    assert recommend(probs("double_recovery", 0.9), {"amount": 1000, "recoverable_now": 0})["approval"] == "supervisor"
    assert recommend(probs("false_claim", 0.9), {"amount": 1000, "recoverable_now": 0})["approval"] == "supervisor"


def test_agent_disputes_go_to_the_distributor_first():
    """MFS Regulations §17.5."""
    rec = recommend(probs("genuine_wrong_send", 0.95), {"amount": 1000, "recoverable_now": 1000, "involves_agent": True})
    assert rec["rule_id"] == "R-AGENT-01" and rec["action"] == "route_distributor"


def test_low_confidence_asks_for_more_information():
    rec = recommend(probs("genuine_wrong_send", 0.5), {"amount": 1000, "recoverable_now": 1000})
    assert rec["rule_id"] == "R-LOW-01"


def test_scam_flags_recipient_for_aml():
    rec = recommend(probs("scam_victim", 0.8), {"amount": 1000, "recoverable_now": 500})
    assert rec["aml_flag"] == "recipient" and "recipient_neutral" in rec["drafts"]
