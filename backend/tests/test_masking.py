from ferot.llm.masking import mask_pii, unmask
from ferot.llm.provider import OfflineProvider, get_provider


def test_phone_numbers_and_trx_ids_are_masked():
    text = "আমি ৫০০০ টাকা ০১০১২-৩৪৫৬৮৭ নম্বরে পাঠিয়েছি, TrxID TX001D5B5E, আর 01012345678 আমার ভাই"
    masked, mapping = mask_pii(text)
    assert "01012345687" not in masked and "01012345678" not in masked and "TX001D5B5E" not in masked
    assert "<PHONE_1>" in masked and "<PHONE_2>" in masked and "<TRX_1>" in masked
    assert mapping["<PHONE_1>"] == "01012345687"


def test_same_number_gets_same_token():
    masked, mapping = mask_pii("01012345687 ... again 01012345687")
    assert masked.count("<PHONE_1>") == 2 and len(mapping) == 1


def test_unmask_restores_nested_values():
    _, mapping = mask_pii("send to 01012345687")
    assert unmask({"n": ["<PHONE_1>"]}, mapping) == {"n": ["01012345687"]}


def test_offline_provider_no_network():
    """R10: without explicit configuration Ferot never calls an external model."""
    assert isinstance(get_provider(), OfflineProvider)
    assert OfflineProvider().extract("anything") is None
