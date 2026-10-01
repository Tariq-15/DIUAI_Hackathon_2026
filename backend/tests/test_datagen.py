import numpy as np

from ferot import config
from ferot.datagen.typos import apply_typo, changed_positions, keypad_distance


def test_numbers_use_010_prefix(small_world):
    """R16: no generated number can belong to a real person."""
    assert small_world.wallets["wallet_no"].str.match(r"^010\d{8}$").all()
    tx = small_world.transactions
    assert tx["sender"].str.startswith("010").all() and tx["receiver"].str.startswith("010").all()


def test_limits_respected(small_world):
    """R17: no customer breaks upay's published per-transaction or daily limits."""
    lim = config.limits()
    tx = small_world.transactions
    owner = dict(zip(small_world.wallets["wallet_no"], small_world.wallets["owner_type"]))
    people = tx["sender"].map(owner).isin(["customer", "mule", "fraudster"])
    day = tx["minute"] // 1440
    send = tx[(tx["type"] == "send_money") & people]
    cash = tx[(tx["type"] == "cash_out") & people]
    assert send["amount"].max() <= lim["send_money"]["per_txn_max"]
    assert send.groupby([send["sender"], day]).amount.sum().max() <= lim["send_money"]["daily_max"]
    assert cash.groupby([cash["sender"], day]).amount.sum().max() <= lim["cash_out_agent"]["daily_max"]


def test_balances_never_negative(small_world):
    tx = small_world.transactions
    assert (tx["sender_balance_after"].dropna() >= -0.01).all()
    assert (tx["receiver_balance_after"].dropna() >= -0.01).all()


def test_all_five_case_types_and_golden_cases_present(small_world):
    cases = small_world.cases
    assert set(cases["case_type"]) == {"genuine_wrong_send", "scam_victim", "false_claim",
                                       "double_recovery", "technical_failure"}
    assert set(cases["golden"]) >= {"rahim", "shirin"}
    assert cases["disputed_trx_id"].notna().all()


def test_held_out_scam_variant_only_in_test_split(small_world):
    c = small_world.cases
    job = c[c["variant"] == "job_offer"]
    assert len(job) > 0 and (job["split"] == "test").all()


def test_double_recovery_has_return_flow(small_world):
    c = small_world.cases
    tx = small_world.transactions
    direct = c[(c["case_type"] == "double_recovery") & (c["variant"] == "")].iloc[0]
    back = tx[(tx["sender"] == direct["recipient"]) & (tx["receiver"] == direct["claimant"])
              & (tx["minute"] > direct["transfer_minute"]) & (tx["minute"] < direct["complaint_minute"])]
    assert len(back) >= 1
    # in the accomplice variant the victim "returns" the money to someone else
    acc = c[(c["case_type"] == "double_recovery") & (c["variant"] == "accomplice")]
    assert len(acc) > 0


def test_typo_is_one_slip_away():
    rng = np.random.default_rng(0)
    mix = config.assumptions()["typos"]
    for _ in range(200):
        wrong = apply_typo("01012345678", rng, mix)
        assert wrong != "01012345678" and len(wrong) == 11 and wrong.startswith("010")
        assert keypad_distance("01012345678", wrong) <= 2.0


def test_transposition_is_cheap_and_positions_reported():
    assert keypad_distance("01012345678", "01012345687") == 0.8
    assert changed_positions("01012345678", "01012345687") == [9, 10]


def test_complaints_have_text_in_three_languages(small_world):
    c = small_world.cases
    assert c["complaint_text"].str.len().min() > 10
    assert set(c["text_language"]) == {"bn", "banglish", "en"}
