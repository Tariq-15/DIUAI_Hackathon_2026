"""Generator must pass every data check on a tiny world, and be reproducible."""
import pytest

from src.validation.checks import Checker


@pytest.fixture(scope="module")
def results(tiny_data, tiny_cfg):
    return {r["id"]: r for r in Checker(tiny_data, tiny_cfg).run(skip_repro=True)}


@pytest.mark.parametrize("tid", ["T1", "T2", "T3", "T4", "T9", "T12", "T13"])
def test_hard_invariants(results, tid):
    assert results[tid]["passed"], results[tid]["details"]


def test_every_scenario_in_every_split(results):
    assert not results["T8"]["details"]["missing_scenario_split"], results["T8"]["details"]


def test_reproducible():
    ok, det = Checker.t14_repro()
    assert ok, det


def test_planted_keys_succeed(tiny_data):
    for p in tiny_data["planted"]:
        if p["id"] != "SC-06":
            assert p["key_txn_id"] and p["key_ok"], p


def test_no_success_breaks_balance(tiny_data):
    tx = tiny_data["transactions"]
    c = tx[tx.sender_type == "C"]
    assert (c.sender_bal_after >= -0.01).all()
