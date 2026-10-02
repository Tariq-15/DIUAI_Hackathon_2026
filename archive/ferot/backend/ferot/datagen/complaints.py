"""Complaint text for every planted case, in Bangla, Banglish or English, with realistic noise.

Genuine wrong-sends, false claims and double-recovery claims deliberately read the same: the words
cannot tell them apart, only the ledger can. That is the point Ferot is built to prove.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

BN_DIGITS = str.maketrans("0123456789", "০১২৩৪৫৬৭৮৯")

GENUINE = {
    "bn": [
        "আমি ভুল করে {amount} টাকা {number} নম্বরে পাঠিয়ে ফেলেছি{time}। দয়া করে টাকাটা ফেরত পেতে সাহায্য করুন।",
        "সেন্ড মানি করতে গিয়ে নম্বর ভুল হয়ে গেছে। {amount} টাকা চলে গেছে {number} নম্বরে{time}। এখন কী করব?",
        "ভাই, ভুল নম্বরে {amount} টাকা পাঠিয়েছি{time}। নম্বরটা {number}। প্লিজ হেল্প করেন।",
    ],
    "banglish": [
        "bhai ami vul kore {amount} taka {number} e pathiye felsi{time}. please help koren",
        "vul number e taka chole gese, {amount} tk, number {number}{time}. ki korbo ekhon?",
        "send money korte giye number vul hoye gese. {number} e {amount} taka gese{time}. taka ta ferot chai",
    ],
    "en": [
        "I sent {amount} taka to the wrong number {number}{time}. Please help me get it back.",
        "Wrong number! {amount} tk went to {number}{time}. What can I do?",
        "I made a mistake while sending money. {amount} BDT was sent to {number} instead of my brother's number{time}.",
    ],
}

SCAM = {
    "fake_sms": {
        "bn": "একজন ফোন করে বলল সে ভুল করে আমার নম্বরে টাকা পাঠিয়েছে, মেসেজও এসেছিল। আমি {amount} টাকা {number} নম্বরে ফেরত দিয়েছি{time}। পরে দেখি আমার একাউন্টে কোনো টাকা আসেনি।",
        "banglish": "ekjon call kore bollo vul kore amar number e taka pathaise, sms o ashse. ami {amount} taka {number} e ferot dilam{time}. pore dekhi kono taka ashe nai",
        "en": "Someone called and said he sent money to me by mistake, I even got an SMS. I returned {amount} taka to {number}{time}. Later I saw no money had come to my account.",
    },
    "impersonation": {
        "bn": "একজন নিজেকে কাস্টমার কেয়ার অফিসার বলে ফোন করে বলল আমার একাউন্ট বন্ধ হয়ে যাবে। তার কথামতো {amount} টাকা {number} নম্বরে পাঠিয়েছি{time}। এখন তার নম্বর বন্ধ।",
        "banglish": "ekjon nijeke customer care officer bole call dilo, bollo account block hoye jabe. tar kotha moto {amount} taka {number} e pathaisi{time}. ekhon number off",
        "en": "A man called saying he was from customer care and my account would be blocked. I sent {amount} taka to {number} as he said{time}. Now his phone is off.",
    },
    "prize": {
        "bn": "আমাকে বলা হয়েছে আমি লটারিতে পুরস্কার জিতেছি, প্রসেসিং ফি হিসেবে {amount} টাকা {number} নম্বরে পাঠাতে হবে। পাঠিয়েছি{time}, কিন্তু কোনো পুরস্কার পাইনি।",
        "banglish": "amake bolse lottery te prize jitsi, processing fee {amount} taka {number} e pathate hobe. pathaisi{time} kintu kichu pai nai",
        "en": "I was told I won a lottery prize and had to pay a {amount} taka processing fee to {number}. I paid{time} but got nothing.",
    },
    "job_offer": {
        "bn": "চাকরির জন্য রেজিস্ট্রেশন ফি হিসেবে {amount} টাকা {number} নম্বরে পাঠিয়েছিলাম{time}। এখন তারা আর ফোন ধরছে না।",
        "banglish": "chakrir registration fee hisabe {amount} taka {number} e pathaisilam{time}. ekhon ar phone dhore na",
        "en": "I paid a {amount} taka registration fee for a job to {number}{time}. Now they don't answer the phone.",
    },
}

TECHNICAL = {
    "bn": "{amount} টাকা সেন্ড মানি করেছি {number} নম্বরে{time}, আমার একাউন্ট থেকে টাকা কেটে নিয়েছে কিন্তু প্রাপক টাকা পায়নি।",
    "banglish": "{number} e {amount} taka send korsi{time}, amar account theke taka kete nise kintu receiver pay nai",
    "en": "I sent {amount} taka to {number}{time}. The money was deducted from my account but the receiver did not get it.",
}

GOLDEN = {
    "rahim": "bhai 5000 taka vul number e chole gese, 01012-345687, ajke 2 tar dike",
    "shirin": "একজন ফোন করে বলল সে ভুল করে আমার নম্বরে টাকা পাঠিয়েছে, মেসেজও এসেছিল। আমি ৩০০০ টাকা ০১০৯৯৯৮৮৮৭৭ নম্বরে ফেরত দিয়েছি আজ সকাল ১১টার দিকে। পরে দেখি আমার একাউন্টে কোনো টাকা আসেনি।",
}


def _period(hour: int, lang: str) -> str:
    table = {
        "bn": [(5, "সকাল"), (12, "দুপুর"), (16, "বিকাল"), (18, "সন্ধ্যা"), (20, "রাত")],
        "banglish": [(5, "sokal"), (12, "dupur"), (16, "bikel"), (18, "sondhay"), (20, "raat")],
    }[lang]
    name = table[-1][1]
    for start, label in table:
        if hour >= start:
            name = label
    return table[-1][1] if hour < 5 else name


def time_phrase(transfer: pd.Timestamp, complaint: pd.Timestamp, lang: str) -> str:
    days = (complaint.normalize() - transfer.normalize()).days
    h = transfer.hour
    h12 = h % 12 or 12
    if lang == "en":
        day = {0: "today", 1: "yesterday"}.get(days, f"{days} days ago")
        return f" {day} around {h12} {'am' if h < 12 else 'pm'}"
    if lang == "bn":
        day = {0: "আজ", 1: "গতকাল"}.get(days, f"{days} দিন আগে")
        return f" {day} {_period(h, 'bn')} {h12}টার দিকে"
    day = {0: "ajke", 1: "gotokal"}.get(days, f"{days} din age")
    return f" {day} {_period(h, 'banglish')} {h12} tar dike"


def _format_number(number: str, rng: np.random.Generator, partial: bool) -> str:
    if partial:
        return f"...{number[-4:]}"
    r = rng.random()
    if r < 0.3:
        return f"{number[:5]}-{number[5:]}"
    if r < 0.4:
        return f"{number[:3]} {number[3:7]} {number[7:]}"
    return number


def _format_amount(amount: float, lang: str, rng: np.random.Generator) -> str:
    a = int(round(amount))
    if lang == "banglish" and a % 1000 == 0 and rng.random() < 0.2:
        return f"{a // 1000}k"
    if lang == "bn" and a % 1000 == 0 and rng.random() < 0.25:
        return f"{a // 1000} হাজার"
    if rng.random() < 0.3 and a >= 1000:
        return f"{a:,}"
    return str(a)


def render(case: pd.Series, rng: np.random.Generator) -> dict:
    lang = case["language"] if case["language"] in ("bn", "banglish", "en") else "bn"
    if case.get("golden"):
        text = GOLDEN[case["golden"]]
        return {"complaint_text": text, "noise": "", "stated_amount": float(case["amount"]),
                "stated_number": case["recipient"], "text_language": "banglish" if case["golden"] == "rahim" else "bn"}

    wrong_amount = rng.random() < 0.10
    partial = rng.random() < 0.15
    no_time = rng.random() < 0.30
    with_trx = rng.random() < 0.20
    amount = float(case["amount"])
    if wrong_amount:
        amount = max(100.0, round(amount * float(rng.choice([0.9, 1.1])), -2))
    number = _format_number(case["recipient"], rng, partial)
    tphrase = "" if no_time else time_phrase(case["transfer_ts"], case["complaint_ts"], lang)

    if case["case_type"] == "scam_victim":
        template = SCAM.get(case["variant"], SCAM["fake_sms"])[lang]
    elif case["case_type"] == "technical_failure":
        template = TECHNICAL[lang]
    else:  # genuine, false claim and double recovery all read like a plain wrong-send
        template = GENUINE[lang][int(rng.integers(0, len(GENUINE[lang])))]
    text = template.format(amount=_format_amount(amount, lang, rng), number=number, time=tphrase)
    if with_trx:
        text += {"bn": f" ট্রানজেকশন আইডি {case['disputed_trx_id']}।", "banglish": f" TrxID {case['disputed_trx_id']}",
                 "en": f" TrxID: {case['disputed_trx_id']}."}[lang]
    bangla_digits = lang == "bn" and rng.random() < 0.7
    if bangla_digits:
        # keep the TrxID Latin; customers copy it from the SMS
        trx = case["disputed_trx_id"]
        text = text.replace(trx, "\x00").translate(BN_DIGITS).replace("\x00", trx)
    noise = ",".join(k for k, v in [("wrong_amount", wrong_amount), ("partial_number", partial),
                                     ("missing_time", no_time), ("trx_id", with_trx),
                                     ("bangla_digits", bangla_digits)] if v)
    return {"complaint_text": text, "noise": noise, "stated_amount": amount,
            "stated_number": case["recipient"] if not partial else case["recipient"][-4:],
            "text_language": lang}


def attach_complaints(cases: pd.DataFrame, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed + 1)
    rendered = pd.DataFrame([render(row, rng) for _, row in cases.iterrows()], index=cases.index)
    return pd.concat([cases, rendered], axis=1)
