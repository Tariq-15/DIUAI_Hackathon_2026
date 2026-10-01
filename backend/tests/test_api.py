"""API tests. Need built data and models: `python -m ferot.cli data && python -m ferot.cli train`."""

import os
import tempfile

import pytest

os.environ["FEROT_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "api-test.db")

from fastapi.testclient import TestClient  # noqa: E402

from ferot.api.main import app  # noqa: E402

AGENT = {"X-Ferot-Actor": "tania", "X-Ferot-Role": "agent"}
SUPERVISOR = {"X-Ferot-Actor": "karim", "X-Ferot-Role": "supervisor"}
COMPLIANCE = {"X-Ferot-Actor": "nadia", "X-Ferot-Role": "compliance"}


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


@pytest.fixture(scope="module")
def rahim(client):
    return next(c for c in client.get("/api/v1/demo/customers").json() if c["key"] == "rahim")


def complaint(r, **kw):
    body = {"claimant": r["wallet"], "text": r["sample_text"], "channel": "app",
            "consent": {"accepted": True}, "as_of_minute": r["now_minute"]}
    body.update(kw)
    return body


def test_health(client):
    assert client.get("/api/v1/health").json()["ok"]


def test_golden_path(client, rahim):
    r = client.post("/api/v1/complaints", json=complaint(rahim))
    assert r.status_code == 201
    case_id = r.json()["case_id"]
    case = client.get(f"/api/v1/cases/{case_id}", headers=AGENT).json()
    assert case["prediction"]["case_type"] == "genuine_wrong_send"
    assert case["intended"]["candidate"] == "01012345678"
    assert case["recommendation"]["rule_id"] == "R-GEN-01"
    assert case["recommendation"]["hold_amount"] == 4200
    done = client.post(f"/api/v1/cases/{case_id}/decision", json={"decision": "approve"}, headers=AGENT).json()
    assert done["status"] == "hold_requested"
    assert client.get("/api/v1/audit/verify", headers=AGENT).json()["ok"]


def test_all_channels(client, rahim):
    """R3: phone, SMS and mail complaints build the same case as the app."""
    for channel in ("app", "call", "sms", "email"):
        assert client.post("/api/v1/complaints", json=complaint(rahim, channel=channel)).status_code == 201


def test_consent_required(client, rahim):
    """R8: no processing without the customer's confirmation of the notice."""
    r = client.post("/api/v1/complaints", json=complaint(rahim, consent={"accepted": False}))
    assert r.status_code == 422


def test_customer_status_hides_internal_details(client, rahim):
    case_id = client.post("/api/v1/complaints", json=complaint(rahim)).json()["case_id"]
    status = client.get(f"/api/v1/cases/{case_id}/status").json()
    assert "prediction" not in status and "drafts" not in status
    assert status["deadline"] and "16236" in status["escalation"]


def test_rejection_needs_supervisor(client):
    """R6: a recommendation to reject needs a supervisor, not an agent."""
    queue = client.get("/api/v1/queue", headers=AGENT).json()
    target = next(c for c in queue if c["approval"] == "supervisor" and c["status"] == "new")
    url = f"/api/v1/cases/{target['case_id']}/decision"
    assert client.post(url, json={"decision": "approve"}, headers=AGENT).status_code == 403
    assert client.post(url, json={"decision": "approve"}, headers=SUPERVISOR).status_code == 200


def test_override_needs_a_reason(client):
    queue = client.get("/api/v1/queue", headers=AGENT).json()
    target = next(c for c in queue if c["status"] == "new" and c["approval"] == "agent")
    url = f"/api/v1/cases/{target['case_id']}/decision"
    assert client.post(url, json={"decision": "override"}, headers=AGENT).status_code == 422
    assert client.post(url, json={"decision": "override", "reason": "customer called back with a TrxID"},
                       headers=AGENT).status_code == 200


def test_export_requires_compliance(client):
    """R13: case data leaves only through compliance, against a verified request."""
    case_id = client.get("/api/v1/queue", headers=AGENT).json()[0]["case_id"]
    url = f"/api/v1/cases/{case_id}/export"
    assert client.post(url, json={"request_ref": "GD-123/2026"}, headers=AGENT).status_code == 403
    r = client.post(url, json={"request_ref": "GD-123/2026"}, headers=COMPLIANCE)
    assert r.status_code == 200 and r.json()["request_ref"] == "GD-123/2026"


def test_reveal_is_logged(client):
    """R9: unmasking a number leaves an audit entry."""
    case_id = client.get("/api/v1/queue", headers=AGENT).json()[0]["case_id"]
    client.post(f"/api/v1/cases/{case_id}/reveal", headers=AGENT)
    actions = [a["action"] for a in client.get(f"/api/v1/cases/{case_id}", headers=AGENT).json()["audit"]]
    assert "pii.reveal" in actions


def test_unknown_role_is_rejected(client):
    assert client.get("/api/v1/queue", headers={"X-Ferot-Role": "admin"}).status_code == 403


def test_dispute_report_csv(client):
    r = client.get("/api/v1/insights/dispute-report.csv", headers=SUPERVISOR)
    assert r.status_code == 200 and r.text.startswith("month,disputes")


def test_unmatched_complaint_asks_for_more_information(client, rahim):
    """No transfer found in the last 7 days: the case is saved and asks the customer for details."""
    r = client.post("/api/v1/complaints", json=complaint(rahim, as_of_minute=60))  # before any of his transfers
    assert r.status_code == 201
    case = client.get(f"/api/v1/cases/{r.json()['case_id']}", headers=AGENT).json()
    assert case["prediction"] is None and case["recommendation"]["rule_id"] == "R-LOW-01"
