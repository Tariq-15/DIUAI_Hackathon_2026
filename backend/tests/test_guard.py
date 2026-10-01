"""Ferot Guard: the pre-send check. Needs built data and models (`python -m ferot.cli build`)."""

import os
import tempfile

import pytest

os.environ.setdefault("FEROT_DB_PATH", os.path.join(tempfile.mkdtemp(), "guard-test.db"))

from fastapi.testclient import TestClient  # noqa: E402

from ferot.api.main import app  # noqa: E402
from ferot.models.guard import band_for, reasons_for  # noqa: E402

AGENT = {"X-Ferot-Actor": "tania", "X-Ferot-Role": "agent"}


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


@pytest.fixture(scope="module")
def demo(client):
    return {c["key"]: c for c in client.get("/api/v1/demo/customers").json()}


def send(client, customer, key, **kw):
    sc = next(s for s in customer["send_scenarios"] if s["key"] == key)
    body = {"sender": customer["wallet"], "recipient": sc["recipient"], "amount": sc["amount"],
            "as_of_minute": sc["minute"]}
    body.update(kw)
    r = client.post("/api/v1/guard/check", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def test_usual_transfer_is_allowed(client, demo):
    r = send(client, demo["rahim"], "usual")
    assert r["band"] == "allow"
    assert r["reasons"] == [] and r["advice"] is None


def test_typo_is_caught_before_sending(client, demo):
    r = send(client, demo["rahim"], "risky")
    assert r["band"] in ("warn", "review")
    assert r["typo"]["candidate"] == "01012345678"
    assert r["reasons"][0]["key"] == "typo"
    assert "01012345678" in r["reasons"][0]["bn"]


def test_scam_number_is_flagged_with_grounded_reasons(client, demo):
    r = send(client, demo["shirin"], "risky")
    assert r["band"] == "review"
    keys = {x["key"] for x in r["reasons"]}
    assert "complaints" in keys
    f = r["features"]
    # every reason is backed by the feature it describes
    if "complaints" in keys:
        assert f["prior_complainants_on_recipient"] >= 1
    if "new_wallet" in keys:
        assert f["recipient_age_days"] <= 45
    if "first_time" in keys:
        assert f["first_ever"] == 1
    assert r["advice"]["bn"] and r["advice"]["en"]


def test_guard_never_blocks():
    """The customer always decides: there is no 'block' band."""
    for risk in range(0, 101, 5):
        for typo in (True, False):
            assert band_for(risk, typo) in ("allow", "warn", "review")


def test_reasons_need_evidence():
    quiet = {"recipient_age_days": 400, "prior_complainants_on_recipient": 0, "recipient_distinct_senders_7d": 1,
             "recipient_new_sender_share_7d": 0.0, "recipient_passthrough_30d": 0.1, "recipient_inbound_30d": 2,
             "first_ever": 0, "_amount_ratio": 1.0}
    assert reasons_for(quiet, None) == []


def test_decision_is_logged_and_alerts_are_masked(client, demo):
    r = send(client, demo["shirin"], "risky")
    d = client.post(f"/api/v1/guard/{r['check_id']}/decision", json={"decision": "cancelled"})
    assert d.status_code == 200 and d.json()["decision"] == "cancelled"
    alerts = client.get("/api/v1/guard/alerts", headers=AGENT).json()
    mine = next(a for a in alerts if a["check_id"] == r["check_id"])
    assert mine["decision"] == "cancelled"
    assert "sender" not in mine and len(mine["recipient_last4"]) == 4
    assert client.get("/api/v1/audit/verify", headers=AGENT).json()["ok"]


def test_bad_input_is_rejected(client, demo):
    w = demo["rahim"]["wallet"]
    assert client.post("/api/v1/guard/check", json={"sender": w, "recipient": "12345", "amount": 100}).status_code == 422
    assert client.post("/api/v1/guard/check",
                       json={"sender": w, "recipient": "01012345678", "amount": 30000}).status_code == 422
    assert client.post("/api/v1/guard/GC-99999/decision", json={"decision": "cancelled"}).status_code == 404
    assert client.post("/api/v1/guard/GC-00001/decision", json={"decision": "deleted"}).status_code == 422


def test_case_report_and_network(client, demo):
    s = demo["shirin"]
    body = {"claimant": s["wallet"], "text": s["sample_text"], "channel": "app", "consent": {"accepted": True},
            "as_of_minute": s["now_minute"]}
    case_id = client.post("/api/v1/complaints", json=body).json()["case_id"]
    case = client.get(f"/api/v1/cases/{case_id}", headers=AGENT).json()
    rep = case["report"]
    assert set(rep) == {"what_happened", "why_risky", "next_step", "limits"}
    assert "Tk 3,000" in rep["what_happened"]
    assert any("synthetic" in x for x in rep["limits"])
    assert "refund" not in rep["next_step"].lower()  # R1: never promise a refund
    net = client.get(f"/api/v1/cases/{case_id}/network", headers=AGENT).json()
    assert net["center"] == case["facts"]["recipient"]
    assert net["complainants"] >= 3
    kinds = {n["kind"] for n in net["nodes"]}
    assert {"center", "this_customer", "complainant"} <= kinds
    ids = {n["id"] for n in net["nodes"]}
    assert all(e["source"] in ids and e["target"] in ids for e in net["edges"])
