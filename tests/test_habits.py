"""Amount habits (federated thresholds), mobile recharge, and the judges' test kit.

Pure-function tests always run; the end-to-end ones need the trained artifacts and the portable export
(python -m src.pipeline, then python -m src.fl.amounts and python -m src.serve.portable).
"""
import json

import numpy as np
import pytest

from src.common.config import ROOT
from src.serve import habits as hb

ART = ROOT / "artifacts"
PORTABLE = ART / "portable"
built = pytest.mark.skipif(not all((ART / f).exists() for f in ("model_bundle.joblib", "demo_state.joblib", "demo_world.joblib"))
                           or not (PORTABLE / "amount_profiles.npz").exists() or not (PORTABLE / "test_kit.json").exists(),
                           reason="trained artifacts / portable export not built")
DAY = 86_400


# ---------------------------------------------------------------- the habit arithmetic
def test_habit_uses_only_earlier_transfers_and_skips_today_for_the_usual_day():
    prev = [(d * DAY + 3600, a) for d, a in enumerate([500, 600, 700, 800, 900, 600])] + [(6 * DAY + 100, 400)]
    h = hb.habit(prev, 6 * DAY + 5000)
    assert h["n"] == 7 and h["median"] == 600 and h["max"] == 900
    assert h["day_usual"] == 650 and h["last24"] == 400     # today is not an earlier day; yesterday was 24 h 23 min ago


def test_unusual_needs_history_the_ratio_and_the_floor():
    thr = {"amount_ratio": 10.0, "day_ratio": 10.0}
    few = [(i * DAY, 500.0) for i in range(3)]
    assert hb.is_unusual("send", hb.habit(few, 10 * DAY), 50_000, thr) == (False, [])           # too little history
    many = [(i * DAY, 100.0) for i in range(20)]
    assert hb.is_unusual("send", hb.habit(many, 30 * DAY), 1500, thr) == (False, [])            # 15x, but under the floor
    flag, why = hb.is_unusual("send", hb.habit(many, 30 * DAY), 2500, thr)
    assert flag and "amount" in why


def test_federated_threshold_estimator_matches_the_central_one_without_noise():
    from src.fl import amounts as A
    rng = np.random.default_rng(0)
    x = rng.normal(0, 1.2, size=(400, 20))                      # 400 phones, log2 ratios
    hists = np.zeros((400, len(A.EDGES)))
    for i in range(400):
        for v in x[i]:
            hists[i, A._bin(v)] += 1
    hists /= hists.sum(axis=1, keepdims=True)
    central = A.threshold_from(hists.sum(axis=0), 0.01)
    fed = A.threshold_from(A.federate([hists], sigma=1e-9, group=400, rng=rng)[0], 0.01)
    assert central == fed and 2 ** 2.25 <= central <= 2 ** 3.5    # 99th percentile of N(0, 1.2) is ~2.8 in log2


# ---------------------------------------------------------------- end to end
@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from src.serve.api import app
    c = TestClient(app)
    assert c.post("/api/v1/demo/reset").status_code == 200
    return c


@built
def test_customers_carry_their_usual_amounts(client):
    rahim = next(c for c in client.get("/api/v1/customers").json()["customers"] if c["key"] == "rahim")
    send, rech = rahim["habits"]["send"], rahim["habits"]["recharge"]
    assert send["enough"] and send["low"] <= send["usual"] <= send["high"] and send["threshold"] > 1
    assert rech["usual"] and rech["threshold"] > 1


@built
def test_unusual_amount_to_a_known_contact_gets_one_check(client):
    client.post("/api/v1/demo/reset")
    rahim = next(c for c in client.get("/api/v1/customers").json()["customers"] if c["key"] == "rahim")
    maa = rahim["contacts"][0]["msisdn"]
    usual = client.post("/api/v1/risk-score", json={"customer": "rahim", "to": maa, "amount": 800}).json()
    assert usual["band"] == "ALLOW" and not usual["habit"]["unusual"]
    big = client.post("/api/v1/risk-score", json={"customer": "rahim", "to": maa, "amount": 15000}).json()
    assert big["band"] == "NUDGE" and big["policy_override"] == "unusual_amount" and big["habit"]["unusual"]
    assert big["reasons"][0]["code"] == "unusual_amount" and "times" in big["reasons"][0]["en"]
    assert big["question_en"] == "Is this amount right?"
    det = client.get(f"/api/v1/alerts/{big['alert_id']}").json()
    assert det["habit"]["ratio"] >= det["habit"]["threshold"] and any("amount habit" in x for x in det["report"]["confidence_limits"])
    row = next(a for a in client.get("/api/v1/alerts").json() if a["id"] == big["alert_id"])
    assert row["unusual_amount"]
    sent = client.post(f"/api/v1/alerts/{big['alert_id']}/decision", json={"choice": "confirm"}).json()
    assert sent["status"] == "sent_after_warning"


@built
def test_recharge_habit_and_rapid_recharge_rule(client):
    client.post("/api/v1/demo/reset")
    rahim = next(c for c in client.get("/api/v1/customers").json()["customers"] if c["key"] == "rahim")
    own, contacts = rahim["msisdn"], [c["msisdn"] for c in rahim["contacts"]]
    ok = client.post("/api/v1/recharge", json={"customer": "rahim", "number": own, "amount": 50}).json()
    assert ok["band"] == "ALLOW" and ok["txn_id"] and ok["own"]
    big = client.post("/api/v1/recharge", json={"customer": "rahim", "number": own, "amount": 1000}).json()
    assert big["band"] == "NUDGE" and big["reasons"][0]["code"] == "unusual_amount" and big["alert_id"]
    det = client.get(f"/api/v1/alerts/{big['alert_id']}").json()
    assert det["kind"] == "recharge" and det["report"]["generated_by"] == "template (recharge)"
    bal = client.post(f"/api/v1/alerts/{big['alert_id']}/decision", json={"choice": "confirm"}).json()["balance"]
    assert bal == pytest.approx(ok["balance"] - 1000)
    client.post("/api/v1/demo/reset")
    outs = [client.post("/api/v1/recharge", json={"customer": "rahim", "number": n, "amount": 100}).json() for n in contacts[:3]]
    assert [o["band"] for o in outs] == ["ALLOW", "ALLOW", "NUDGE"]
    assert any(r["code"] == "recharge_burst" for r in outs[-1]["reasons"])
    assert client.post("/api/v1/recharge", json={"customer": "rahim", "number": own, "amount": 5000}).status_code == 422
    assert client.post("/api/v1/recharge", json={"customer": "rahim", "number": "123", "amount": 50}).status_code == 422
    assert client.get("/api/v1/audit").json()["verify"]["ok"]


@built
def test_test_kit_numbers_answer_as_recorded_on_a_fresh_demo(client):
    client.post("/api/v1/demo/reset")
    kit = client.get("/api/v1/test-kit").json()
    items = [it for g in kit["groups"] for it in g["items"]]
    assert len(items) >= 20 and {g["key"] for g in kit["groups"]} >= {"everyday", "mistakes", "staged", "dataset", "recharge"}
    from src.serve.api import world
    w = world()
    for it in items:
        if it["kind"] != "send":
            continue
        if it["expected"] == "NO_ACCOUNT":
            r = client.post("/api/v1/recipient-check", json={"customer": "rahim", "to": it["number"]}).json()
            assert not r["exists"]
            continue
        r = w.preview(it["persona"], it["number"], it["amount"], it.get("device"))
        assert r["band"] == it["expected"], (it["label_en"], r["band"], it["expected"])
    roles = {it["role"] for g in kit["groups"] if g["key"] == "dataset" for it in g["items"]}
    assert roles >= {"collector", "scam_recipient", "fake_seller", "mule", "card_fraud"}


@built
def test_browser_build_answers_recharge_and_test_kit():
    from src.serve.browser import Dispatcher
    d = Dispatcher(PORTABLE)
    call = lambda m, p, b=None: json.loads(d.handle(m, p, json.dumps(b) if b is not None else None))   # noqa: E731
    rahim = next(c for c in call("GET", "/api/v1/customers")["data"]["customers"] if c["key"] == "rahim")
    assert rahim["habits"]["send"]["enough"]
    r = call("POST", "/api/v1/recharge", {"customer": "rahim", "number": rahim["msisdn"], "amount": 1000})["data"]
    assert r["band"] == "NUDGE"
    assert call("POST", "/api/v1/recharge", {"customer": "rahim", "number": rahim["msisdn"], "amount": 0})["status"] == 422
    assert call("GET", "/api/v1/test-kit")["data"]["groups"]
    assert call("GET", "/api/v1/customers/rahim/recharges")["data"] == []        # the NUDGE was not sent yet
    assert call("GET", "/api/v1/model")["data"]["federated"]["amounts"]["thresholds"]["send"]["amount_ratio"] > 1
