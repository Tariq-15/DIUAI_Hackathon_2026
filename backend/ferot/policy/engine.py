"""Policy engine: turns model outputs into a recommended action using upay-owned rules.

Rules live in `config/policy_rules.yaml` so operations and compliance can change them without code.
The engine never acts: every recommendation waits for a named human's approval (R6), and a hold is
capped at the disputed amount and at what is still in the wallet (R14).
"""

from __future__ import annotations

from ferot import config


def recommend(probs: dict[str, float], facts: dict) -> dict:
    cfg = config.policy_rules()
    top = max(probs, key=probs.get)
    p = probs[top]
    for rule in cfg["rules"]:
        when = rule.get("when", {})
        if when.get("involves_agent") and not facts.get("involves_agent"):
            continue
        if "case_type" in when and (top != when["case_type"] or p < when.get("min_prob", 0.0)):
            continue
        if "recoverable_gt" in when and not facts.get("recoverable_now", 0.0) > when["recoverable_gt"]:
            continue
        hold = 0.0
        if rule.get("hold"):
            hold = round(min(float(facts.get("amount", 0.0)), float(facts.get("recoverable_now", 0.0))), 2)
        return {
            "rule_id": rule["id"],
            "action": rule["action"],
            "summary": rule["summary"],
            "approval": rule.get("approval", "agent"),
            "hold_amount": max(hold, 0.0),
            "aml_flag": rule.get("aml_flag"),
            "drafts": rule.get("drafts", []),
            "case_type": top,
            "confidence": round(p, 4),
            "policy_version": cfg.get("version"),
        }
    raise RuntimeError("policy rules must end with a catch-all rule")
