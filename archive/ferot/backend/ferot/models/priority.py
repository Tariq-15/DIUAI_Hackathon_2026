"""M6 queue priority: the taka lost if this case waits, plus weights for vulnerability and the SLA.

    priority = R(0) - R(w) + lambda_v * vulnerable + lambda_s * sla_risk

R is the recoverability curve (M5), w the expected wait. The SLA term guarantees that small cases are
never starved: as the 10-working-day limit nears (MFS Regulations 2022, §17.3) their priority rises.
"""

from __future__ import annotations

from ferot import config
from ferot.models.recoverability import expected_at


def priority_score(curve: list[dict], vulnerable: bool, sla: dict) -> dict:
    p = config.assumptions()["priority"]
    wait_min = p["expected_wait_hours"] * 60
    lost_by_waiting = expected_at(curve, 0) - expected_at(curve, wait_min)
    limit = max(sla.get("working_days_limit", 10), 1)
    sla_risk = min(1.0, sla.get("working_days_used", 0) / limit) ** 2
    score = lost_by_waiting + p["lambda_vulnerable"] * float(vulnerable) + p["lambda_sla"] * sla_risk
    if sla.get("breached"):
        score += 10 * p["lambda_sla"]
    return {"score": round(score, 2), "lost_by_waiting": round(lost_by_waiting, 2),
            "vulnerable": bool(vulnerable), "sla_risk": round(sla_risk, 3)}
