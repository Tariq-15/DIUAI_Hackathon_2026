"""Product layer: customer warning flow (warn only, the customer decides), analyst copilot, audit, scam checker.

Runs on the trained artifacts (artifacts/model_bundle.joblib, demo_state.joblib, demo_world.joblib);
skipped when they have not been built (python -m src.pipeline).
"""
import json

import pytest

from src.common.config import ROOT

ART = ROOT / "artifacts"
pytestmark = pytest.mark.skipif(not all((ART / f).exists() for f in ("model_bundle.joblib", "demo_state.joblib", "demo_world.joblib")),
                                reason="trained artifacts not built")


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from src.serve.api import app
    c = TestClient(app)
    assert c.post("/api/v1/demo/reset").status_code == 200
    return c


@pytest.fixture(scope="module")
def scen(client):
    out = {}
    for cu in client.get("/api/v1/customers").json()["customers"]:
        for s in cu["scenarios"]:
            out[(cu["key"], s["key"])] = s
    return out


def send(client, who, s, **kw):
    body = {"customer": who, "to": s["to"], "amount": s["amount"], "device_id": s.get("device")}
    body.update(kw)
    r = client.post("/api/v1/risk-score", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def test_usual_transfer_goes_straight_through(client, scen):
    r = send(client, "rahim", scen[("rahim", "normal")])
    assert r["band"] == "ALLOW" and r["alert_id"] is None and r["choices"] == []


def test_collector_gets_the_strongest_warning_with_grounded_bangla_evidence(client, scen):
    r = send(client, "rahim", scen[("rahim", "collector")])
    assert r["band"] == "HOLD" and r["choices"] == ["cancel", "confirm_pin"] and r["question_bn"]
    codes = {x["code"] for x in r["reasons"]}
    assert "many_senders" in codes
    assert any("১৪" in x["bn"] for x in r["reasons"])          # the 14 strangers, quoted from the feature value
    assert "১৬২৬৮" in r["message"]["bn"]
    # nothing is held for an analyst: the transfer waits only for the customer's own answer
    aid = r["alert_id"]
    st = client.get(f"/api/v1/transfers/{aid}").json()
    assert st["status"] == "awaiting_customer" and "report" not in st
    assert client.post(f"/api/v1/alerts/{aid}/decision", json={"choice": "confirm"}).status_code == 422      # needs the PIN
    assert client.post(f"/api/v1/alerts/{aid}/action", json={"action": "RELEASE_TRANSACTION", "analyst": "Nadia"}).status_code == 422
    d = client.post(f"/api/v1/alerts/{aid}/decision", json={"choice": "cancel"})
    assert d.status_code == 200 and d.json()["status"] == "cancelled_by_customer" and d.json()["balance"] == st["balance"]


def test_soft_warning_leaves_the_choice_to_the_customer(client, scen):
    s = scen.get(("rahim", "warn"))
    if s is None:
        pytest.skip("no soft-warning example found in this world")
    r = send(client, "rahim", s)
    assert r["band"] in ("NUDGE", "STEP_UP") and r["question_bn"]
    choice = "confirm" if r["band"] == "NUDGE" else "confirm_pin"
    if choice == "confirm_pin":
        assert client.post(f"/api/v1/alerts/{r['alert_id']}/decision", json={"choice": choice}).status_code == 422
    d = client.post(f"/api/v1/alerts/{r['alert_id']}/decision", json={"choice": choice, "pin": "1234"})
    assert d.status_code == 200 and d.json()["status"] == "sent_after_warning"


def test_sim_swap_takeover_gets_the_strongest_warning(client, scen):
    r = send(client, "salma", scen[("salma", "takeover")])
    assert r["band"] == "HOLD" and "confirm_pin" in r["choices"]
    assert {"new_device", "sim_swap", "pin_reset", "shared_device"} & {x["code"] for x in r["reasons"]}


def test_case_report_is_four_parts_and_grounded(client, scen):
    from src.serve.copilot import unsupported_numbers
    r = send(client, "rahim", scen[("rahim", "collector")])
    d = client.get(f"/api/v1/alerts/{r['alert_id']}").json()
    rep = d["report"]
    for k in ("what_happened", "why_risky", "recommended_action", "confidence_limits"):
        assert rep[k], k
    assert rep["generated_by"] == "template"
    assert "FLAG_RECIPIENT" in rep["actions"] and "CONTACT_SENDERS" in rep["actions"]
    text = " ".join(x for k in ("what_happened", "why_risky", "recommended_action", "confidence_limits") for x in rep[k])
    assert unsupported_numbers(text, [json.dumps(rep["facts"], default=str)]) == []
    payers = [n for n in d["network"]["nodes"] if n["role"] == "payer"]
    assert len(payers) >= 14 and any(e.get("attempt") for e in d["network"]["edges"])
    assert d["shap"] and all("label" in s for s in d["shap"])


def test_llm_is_off_by_default_and_ungrounded_text_is_rejected(monkeypatch):
    from src.serve.copilot import polish_with_llm, unsupported_numbers
    monkeypatch.delenv("PROHORI_LLM", raising=False)
    assert polish_with_llm({"actions": []}, {}) is None
    assert unsupported_numbers("about Tk 99,999 was lost at 03:10", ['{"amount": 15000, "when": "03:10"}']) == ["99999"]


def test_flag_needs_a_name_warns_later_senders_without_blocking_and_is_audited(client, scen):
    r = send(client, "rahim", scen[("rahim", "collector")])
    aid = r["alert_id"]
    assert client.post(f"/api/v1/alerts/{aid}/action", json={"action": "FLAG_RECIPIENT", "analyst": "  "}).status_code == 403
    assert client.post(f"/api/v1/alerts/{aid}/action", json={"action": "DISMISS", "analyst": "Nadia"}).status_code == 422
    ok = client.post(f"/api/v1/alerts/{aid}/action", json={"action": "FLAG_RECIPIENT", "analyst": "Nadia", "note": "collector"})
    assert ok.status_code == 200 and "W9000001" in ok.json()["flagged"]
    assert ok.json()["status"] == "awaiting_customer"          # the flag does not answer Rahim's warning for him
    later = send(client, "salma", {"to": "01090000001", "amount": 500})
    assert later["band"] == "HOLD" and later["policy_override"] == "recipient_flagged_by_analyst"
    # even a flagged wallet is only a warning: the customer can still send with the PIN
    assert later["choices"] == ["cancel", "confirm_pin"]
    assert client.post(f"/api/v1/alerts/{later['alert_id']}/decision", json={"choice": "confirm_pin"}).status_code == 422
    d = client.post(f"/api/v1/alerts/{later['alert_id']}/decision", json={"choice": "confirm_pin", "pin": "1234"})
    assert d.status_code == 200 and d.json()["status"] == "sent_after_warning" and d.json()["balance"] == later["balance"] - 500
    audit = client.get("/api/v1/audit").json()
    assert audit["verify"]["ok"]
    assert any(e["action"] == "analyst.flag_recipient" and e["actor"] == "Nadia" for e in audit["entries"])
    assert any(e["action"] == "customer.confirmed_pin" and e["alert_id"] == later["alert_id"] for e in audit["entries"])


def test_audit_chain_detects_tampering(client):
    from src.serve.api import world
    w = world()
    assert w.verify_audit()["ok"]
    old = w.audit[0]["actor"]
    w.audit[0]["actor"] = "someone-else"
    try:
        assert not w.verify_audit()["ok"]
    finally:
        w.audit[0]["actor"] = old
    assert w.verify_audit()["ok"]


def test_unknown_number_and_self_transfer_are_refused(client):
    assert client.post("/api/v1/risk-score", json={"customer": "rahim", "to": "01000000000", "amount": 100}).status_code == 404
    me = next(c for c in client.get("/api/v1/customers").json()["customers"] if c["key"] == "rahim")
    assert client.post("/api/v1/risk-score", json={"customer": "rahim", "to": me["msisdn"], "amount": 100}).status_code == 422


def test_scam_checker_names_the_cues():
    from src.serve.scamcheck import check
    r = check("আমি upay অফিস থেকে বলছি, আপনার একাউন্ট ২৪ ঘণ্টার মধ্যে বন্ধ হয়ে যাবে, এখনই ওটিপি কোডটা বলুন")
    assert r["verdict"] == "high"
    assert {"asks_pin_otp", "impersonates", "threat_urgency"} <= {c["code"] for c in r["cues"]}
    assert check("ভাই কেমন আছো? কাল সন্ধ্যায় দেখা হবে।")["verdict"] == "none"


def test_ui_is_served(client):
    assert client.get("/", follow_redirects=False).status_code in (302, 307)
    for page in ("/ui/", "/ui/app.html", "/ui/analyst.html"):
        r = client.get(page)
        assert r.status_code == 200 and "প্রহরী" in r.text
        assert "সিন্থেটিক" in r.text or "synthetic" in r.text          # labelled as a prototype on synthetic data


def test_native_contributions_equal_shap():
    """The live scorer uses LightGBM's own TreeSHAP (no shap import at serve time); it must match shap exactly."""
    import joblib
    import numpy as np
    import pandas as pd
    from src.models.explain import explainer, shap_matrix
    from src.models.scoring import X_of
    bundle = joblib.load(ART / "model_bundle.joblib")
    world = joblib.load(ART / "demo_world.joblib")
    X = X_of(pd.DataFrame([a["evidence"] for a in world["alerts"][:8]]).astype(float), bundle["features"])
    native = bundle["lgbm"].booster_.predict(X, pred_contrib=True)[:, :-1]
    assert np.allclose(native, shap_matrix(explainer(bundle), X), atol=1e-6)


PORTABLE = ART / "portable"


@pytest.mark.skipif(not (PORTABLE / "world.pkl.gz").exists(), reason="portable export not built (python -m src.serve.portable)")
def test_portable_bundle_reproduces_the_original_models():
    """The browser build's version-neutral models must score exactly like the pickled originals."""
    import joblib
    import pandas as pd
    from src.models.scoring import score_frame
    from src.serve.portable import load_bundle
    orig, port = joblib.load(ART / "serve_bundle.joblib"), load_bundle(PORTABLE)
    world = joblib.load(ART / "demo_world.joblib")
    rows = pd.DataFrame([dict(a["evidence"], txn_type=a["txn_type"]) for a in world["alerts"]])
    rows[orig["features"]] = rows[orig["features"]].astype(float)
    a, b = score_frame(orig, rows), score_frame(port, rows)
    for c in ("p_fraud", "anomaly", "p_cal", "risk_score"):
        assert (a[c] - b[c]).abs().max() < 1e-12, c
    assert (a.band == b.band).all() and (a.policy_override == b.policy_override).all()


@pytest.mark.skipif(not (PORTABLE / "world.pkl.gz").exists(), reason="portable export not built (python -m src.serve.portable)")
def test_browser_dispatcher_answers_like_the_api():
    from src.serve.browser import Dispatcher
    d = Dispatcher(PORTABLE)
    call = lambda m, p, b=None: json.loads(d.handle(m, p, json.dumps(b) if b is not None else None))   # noqa: E731
    sc = {(c["key"], s["key"]): s for c in call("GET", "/api/v1/customers")["data"]["customers"] for s in c["scenarios"]}
    send = lambda who, s: call("POST", "/api/v1/risk-score", {"customer": who, "to": s["to"], "amount": s["amount"],   # noqa: E731
                                                              "device_id": s.get("device")})
    assert send("rahim", sc[("rahim", "normal")])["data"]["band"] == "ALLOW"
    held = send("rahim", sc[("rahim", "collector")])["data"]
    assert held["band"] == "HOLD" and any("১৪" in r["bn"] for r in held["reasons"])
    assert send("salma", sc[("salma", "takeover")])["data"]["band"] == "HOLD"
    assert call("POST", f"/api/v1/alerts/{held['alert_id']}/decision", {"choice": "confirm"})["status"] == 422
    assert call("POST", "/api/v1/risk-score", {"customer": "rahim", "to": "01000000000", "amount": 10})["status"] == 404
    assert call("POST", f"/api/v1/alerts/{held['alert_id']}/action", {"action": "FLAG_RECIPIENT", "analyst": " "})["status"] == 403
    sent = call("POST", f"/api/v1/alerts/{held['alert_id']}/decision", {"choice": "confirm_pin", "pin": "1234"})
    assert sent["data"]["status"] == "sent_after_warning"       # HOLD is a warning: the customer decides, in the browser too
    assert call("GET", "/api/v1/audit")["data"]["verify"]["ok"]
    assert call("GET", "/api/v1/nope")["status"] == 404
