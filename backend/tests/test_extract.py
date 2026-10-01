import json
from pathlib import Path

import pytest

from ferot.models.extract import extract_rules

HANDWRITTEN = json.loads((Path(__file__).parent / "data" / "handwritten_complaints.json").read_text(encoding="utf-8"))


def test_golden_rahim_banglish():
    e = extract_rules("bhai 5000 taka vul number e chole gese, 01012-345687, ajke 2 tar dike")
    assert e.amount == 5000 and e.number == "01012345687"
    assert e.day_offset == 0 and e.hour == 14 and e.language == "banglish"


def test_bangla_digits_and_words():
    e = extract_rules("আমি ভুল করে ৫ হাজার টাকা ০১০১২৩৪৫৬৮৭ নম্বরে পাঠিয়ে ফেলেছি গতকাল রাত ৯টার দিকে।")
    assert e.amount == 5000 and e.number == "01012345687"
    assert e.day_offset == 1 and e.hour == 21 and e.language == "bn"


def test_partial_number_and_trx_id():
    e = extract_rules("I sent 2,500 taka to ...5687 yesterday around 7 pm. TrxID: TX001D5B5E.")
    assert e.amount == 2500 and e.number is None and e.number_last4 == "5687"
    assert e.trx_id == "TX001D5B5E" and e.hour == 19


def test_scam_cues():
    e = extract_rules("ekjon call kore bollo vul kore taka pathaise, sms o ashse. ami 3000 taka 01099988877 e ferot dilam")
    assert e.cues["call"] and e.cues["sms"] and e.cues["returned"]


@pytest.mark.parametrize("item", HANDWRITTEN, ids=[h["id"] for h in HANDWRITTEN])
def test_handwritten_set(item):
    """Complaints written by hand, separately from the generator's templates."""
    e = extract_rules(item["text"])
    if item.get("amount") is not None:
        assert e.amount == item["amount"]
    if item.get("number"):
        assert e.number == item["number"]
    if item.get("last4"):
        assert e.number_last4 == item["last4"]
