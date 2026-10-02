import pytest

from ferot.models.drafts import REFUND_PROMISES, TIPPING_OFF, T, check_draft, generate_drafts

FACTS = {"amount": 5000.0, "recipient": "01012345687", "earlier_transfers_to_recipient": 3,
         "transfer_ts": "2026-08-27T14:02:00", "hold_amount": 4200.0}
ALL = list(T)


@pytest.fixture
def drafts():
    return generate_drafts(ALL + ["internal_note"], "FC-01601", FACTS, "2026-09-10", "note", use_llm=False)


def test_no_refund_promises(drafts):
    """R1: nothing we send a customer promises the money back."""
    for draft_id, d in drafts.items():
        if d["audience"] == "internal":
            continue
        for lang in ("en", "bn"):
            assert not any(p in d[lang].lower() for p in REFUND_PROMISES), (draft_id, lang)


def test_no_tipping_off(drafts):
    """R7 / MLPA §6: a recipient message never hints at suspicion."""
    for draft_id, d in drafts.items():
        if d["audience"] == "recipient" or draft_id == "customer_reject_double":
            for lang in ("en", "bn"):
                assert not any(w in d[lang].lower() for w in TIPPING_OFF), (draft_id, lang)


def test_every_template_passes_its_checks(drafts):
    for draft_id, d in drafts.items():
        assert d["checks"]["passed"], draft_id


def test_grounding_catches_an_invented_number():
    checks = check_draft("We will return Tk 9999 by tomorrow.", {"5000"}, "customer")
    assert not checks["grounded"] and checks["unsupported_numbers"] == ["9999"]


def test_refund_promise_is_caught():
    assert not check_draft("You will get your money back.", set(), "customer")["passed"]


def test_bangla_digits_are_checked_too():
    assert not check_draft("আপনি ৯৯৯৯ টাকা পাবেন", {"5000"}, "customer")["grounded"]
