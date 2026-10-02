"""The merged features: wrong-number check (which contact, which digit), Banglish complaints, federated learning.

Pure-function tests always run; the end-to-end ones need the trained artifacts (python -m src.pipeline).
"""
import json
from datetime import date

import numpy as np
import pytest

from src.common.config import ROOT
from src.serve import complaints as cmp
from src.serve import recipient as rc

ART = ROOT / "artifacts"
PORTABLE = ART / "portable"
built = pytest.mark.skipif(not all((ART / f).exists() for f in ("model_bundle.joblib", "demo_state.joblib", "demo_world.joblib")),
                           reason="trained artifacts not built")


# ---------------------------------------------------------------- which digit went wrong
def test_describe_names_the_swapped_or_wrong_digits():
    s = rc.describe("01076254257", "01076254275")
    assert s["kind"] == "swap" and s["positions"] == [10, 11] and (s["meant"], s["typed"]) == ("57", "75")
    assert "10 and 11" in s["en"] and "১০ ও ১১" in s["bn"]
    k = rc.describe("01076254257", "01076254258")
    assert k["kind"] == "wrong_key" and k["positions"] == [11] and k["neighbour"] and "next to it" in k["en"]
    far = rc.describe("01076254257", "01076254251")
    assert far["kind"] == "wrong_key" and not far["neighbour"]


def test_check_picks_the_frequent_contact_one_slip_away():
    msisdn = {"W1": "01076254257", "W2": "01076254258", "W3": "01711111111"}
    costs = rc.default_costs()
    best = rc.check({"W1": 14, "W2": 2, "W3": 30}, msisdn, "01076254275", costs)
    assert best["wallet"] == "W1" and best["slip"]["kind"] == "swap" and best["distance"] == 0.8
    assert rc.check({"W1": 1}, msisdn, "01076254275", costs) is None            # paid once: not a known contact
    assert rc.check({"W3": 30}, msisdn, "01076254275", costs) is None           # far away: no suggestion
    assert rc.check({"W1": 14}, msisdn, "01076254257", costs) is None           # typed exactly: nothing to fix


def test_keypad_distance_prefers_neighbour_slips():
    c = rc.default_costs()
    assert rc.keypad_distance("5", "8", c) == 0.6 and rc.keypad_distance("5", "9", c) == 1.0
    assert rc.keypad_distance("57", "75", c) == 0.8


# ---------------------------------------------------------------- Banglish complaints
def test_complaint_words_are_read_by_rules():
    e = cmp.extract("Bhai ajke bhul kore 800 taka onno number e chole gese, number er sesh 4 digit 4275. 2 ta digit ulta hoye gechilo.")
    assert e["amount"] == 800 and e["number_last4"] == "4275" and e["day_offset"] == 0 and e["language"] == "banglish"
    assert e["hour"] is None                                    # "2 ta digit" counts digits, it is not 2 o'clock
    b = cmp.extract("গতকাল রাত ৮টার দিকে ০১৭১১২২৩৩৪৪ নম্বরে ১৫০০ টাকা ভুলে চলে গেছে")
    assert (b["number"], b["amount"], b["day_offset"], b["hour"]) == ("01711223344", 1500, 1, 20)
    assert cmp.extract("I sent 1200 tk to ...4275 yesterday 8pm")["number_last4"] == "4275"


def test_complaint_deadline_is_ten_working_days_without_friday_and_saturday():
    assert cmp.sla_deadline(date(2026, 5, 31)) == date(2026, 6, 14)


# ---------------------------------------------------------------- federated learning
def test_secure_aggregation_hides_each_part_and_sums_exactly():
    from src.fl import fedgbdt, ondevice
    rng = np.random.default_rng(0)
    parts = [rng.normal(size=(3, 5)) for _ in range(4)]
    assert np.allclose(fedgbdt.secure_sum(parts, rng), np.sum(parts, axis=0), atol=1e-6)
    rows = rng.normal(size=(50, 101))
    total, masked = ondevice.secure_sum(rows, rng)
    assert np.allclose(total, rows.sum(axis=0), atol=1e-4)
    seen = masked.view(np.int64).astype(float) / ondevice.FIXED
    assert np.abs(seen - rows).min() > 1e3                        # what the server receives looks nothing like a report


def test_on_device_learning_recovers_the_slip_pattern_with_a_privacy_budget():
    from src.fl import ondevice
    out = ondevice.run(n_phones=20_000, rounds=3, verbose=False)
    r = out["result"]
    assert r["top_slip_is_neighbour"] == 1.0 and r["final_l1_error"] < 0.15
    assert r["neighbour_cost_mean"] < r["other_cost_mean"]
    assert ondevice.epsilon(6, 2, 6.0) == pytest.approx(4.25, abs=0.01)
    assert ondevice.epsilon(6, 2, 12.0) < ondevice.epsilon(6, 2, 6.0)


def test_federated_trees_load_in_lightgbm_with_the_same_scores():
    import lightgbm as lgb
    from src.fl import fedgbdt
    rng = np.random.default_rng(3)
    X = rng.normal(size=(1200, 4))
    X[rng.random(X.shape) < 0.05] = np.nan
    y = ((np.nan_to_num(X[:, 0]) + 0.5 * np.nan_to_num(X[:, 1]) + rng.normal(0, .5, 1200)) > 0.8).astype(float)
    edges = [np.unique(np.nanquantile(X[:, f], np.linspace(0.02, 0.98, 30))) for f in range(4)]
    base = float(np.log(y.mean() / (1 - y.mean())))
    silos = []
    for part in np.array_split(np.arange(1200), 3):
        s = fedgbdt.Silo("s", X[part], y[part], np.ones(len(part)), X[part][:50], y[part][:50], np.ones(50))
        s.base = base
        s.bin(edges)
        silos.append(s)
    model, _ = fedgbdt.train(silos, 4, edges, trees=8, depth=3, min_leaf=10, colsample=1.0, patience=100, log=lambda *_: None)
    ours = base + sum(fedgbdt.predict_tree(t, fedgbdt.binize(X, edges)) for t in model)
    booster = lgb.Booster(model_str=fedgbdt.to_lightgbm(model, base, edges, [f"f{i}" for i in range(4)]))
    assert np.abs(booster.predict(X, raw_score=True) - ours).max() < 1e-9


# ---------------------------------------------------------------- end to end, through the API
@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from src.serve.api import app
    c = TestClient(app)
    assert c.post("/api/v1/demo/reset").status_code == 200
    return c


@pytest.fixture(scope="module")
def typo(client):
    rahim = next(c for c in client.get("/api/v1/customers").json()["customers"] if c["key"] == "rahim")
    return next(s for s in rahim["scenarios"] if s["key"] == "typo"), rahim


@built
def test_typed_number_shows_who_was_meant_and_which_digits(client, typo):
    s, rahim = typo
    maa = rahim["contacts"][0]
    r = client.post("/api/v1/recipient-check", json={"customer": "rahim", "to": s["to"]}).json()
    assert r["exists"] and r["suggestion"]["msisdn"] == maa["msisdn"]
    assert (r["suggestion"]["name"], r["suggestion"]["name_en"]) == ("মা", "Mother")
    assert r["suggestion"]["slip"]["kind"] == "swap" and r["suggestion"]["slip"]["positions"] == [10, 11]
    ok = client.post("/api/v1/recipient-check", json={"customer": "rahim", "to": maa["msisdn"]}).json()
    assert ok["known_contact"] == "মা" and ok["suggestion"] is None


@built
def test_wrong_number_warning_then_send_to_the_number_meant(client, typo):
    s, rahim = typo
    res = client.post("/api/v1/risk-score", json={"customer": "rahim", "to": s["to"], "amount": 800}).json()
    assert res["band"] == "NUDGE" and res["policy_override"] == "possible_wrong_recipient"
    assert res["reasons"][0]["code"] == "wrong_recipient" and "উল্টে" in res["reasons"][0]["bn"]
    assert "use_suggested" in res["choices"] and res["question_en"] == "Is this the right number?"
    d = client.post(f"/api/v1/alerts/{res['alert_id']}/decision", json={"choice": "use_suggested"}).json()
    assert d["status"] == "changed_to_suggested"
    again = client.post("/api/v1/risk-score", json={"customer": "rahim", "to": res["suggestion"]["msisdn"], "amount": 800}).json()
    assert again["band"] == "ALLOW" and again["txn_id"]
    row = next(a for a in client.get("/api/v1/alerts").json() if a["id"] == res["alert_id"])
    assert row["wrong_number"] and row["status"] == "changed_to_suggested"


@built
def test_banglish_complaint_finds_the_transfer_and_a_person_holds_the_money(client, typo):
    s, _ = typo
    res = client.post("/api/v1/risk-score", json={"customer": "rahim", "to": s["to"], "amount": 800}).json()
    assert client.post(f"/api/v1/alerts/{res['alert_id']}/decision", json={"choice": "confirm"}).json()["status"] == "sent_after_warning"
    text = "Bhai ajke bhul kore 800 taka onno number e chole gese, number er sesh 4 digit 4275"
    assert client.post("/api/v1/complaints", json={"customer": "rahim", "text": text, "consent": False}).status_code == 422
    st = client.post("/api/v1/complaints", json={"customer": "rahim", "text": text, "consent": True}).json()
    assert st["transfer"]["number"] == s["to"] and st["deadline"] and st["step"] == 1
    det = client.get(f"/api/v1/alerts/{st['case_id']}").json()
    assert det["complaint"]["case_type"] == "genuine_wrong_send" and det["complaint"]["slip"]["slip"]["kind"] == "swap"
    assert det["report"]["actions"][:2] == ["HOLD_DISPUTED_AMOUNT", "ASK_RECIPIENT_CONSENT"]
    assert client.post(f"/api/v1/alerts/{st['case_id']}/action", json={"action": "HOLD_DISPUTED_AMOUNT", "analyst": " "}).status_code == 403
    a = client.post(f"/api/v1/alerts/{st['case_id']}/action", json={"action": "HOLD_DISPUTED_AMOUNT", "analyst": "QA"}).json()
    assert a["status"] == "hold_requested"
    det = client.get(f"/api/v1/alerts/{st['case_id']}").json()
    assert 0 < det["hold_amount"] <= 800
    assert client.get(f"/api/v1/complaints/{st['case_id']}").json()["step"] == 2
    assert client.get("/api/v1/audit").json()["verify"]["ok"]


@built
def test_model_card_carries_both_federated_results(client):
    f = client.get("/api/v1/model").json()["federated"]
    if not f:
        pytest.skip("federated results not packaged (python -m src.fl.summary)")
    assert f["ondevice"]["epsilon_total"] > 0 and f["ondevice"]["noise"] == "distributed"
    models = [r["model"] for r in f["crosssilo"]["comparison"]]
    assert any("federated" in m for m in models) and any("central" in m for m in models)
    assert "transactions" in f["crosssilo"]["never_shared"]


@built
@pytest.mark.skipif(not (PORTABLE / "world.pkl.gz").exists(), reason="portable export not built")
def test_browser_build_answers_the_new_routes():
    from src.serve.browser import Dispatcher
    d = Dispatcher(PORTABLE)
    call = lambda m, p, b=None: json.loads(d.handle(m, p, json.dumps(b) if b is not None else None))   # noqa: E731
    rahim = next(c for c in call("GET", "/api/v1/customers")["data"]["customers"] if c["key"] == "rahim")
    s = next(x for x in rahim["scenarios"] if x["key"] == "typo")
    assert call("POST", "/api/v1/recipient-check", {"customer": "rahim", "to": s["to"]})["data"]["suggestion"]["slip"]["kind"] == "swap"
    assert call("POST", "/api/v1/complaints/preview", {"text": "800 taka bhul number e"})["data"]["amount"] == 800
    assert call("POST", "/api/v1/complaints", {"customer": "rahim", "text": "bhul number", "consent": False})["status"] == 422
    assert isinstance(call("GET", "/api/v1/customers/rahim/transfers")["data"], list)
    assert call("GET", "/api/v1/model")["data"]["federated"]
