"""'I sent money to the wrong person': reading a complaint in Bangla, Banglish or English.

Merged from Ferot (our Track 06 project), rules only: phone numbers, transaction IDs, amounts written as digits,
Bangla digits or words ("pach hajar", "৫ হাজার", "5k"), times ("2 tar dike", "gotokal"), and scam cues. No LLM
reads the customer's words, so nothing is sent anywhere and nothing can be prompt-injected.

Then the complaint is matched to one of the customer's recent transfers (amount, number, day and hour), and
the 10-working-day deadline is set (MFS Regulations 2022 §17.3; Bangladesh weekend: Friday and Saturday).
"""
from __future__ import annotations

import math
import re
from datetime import date, timedelta

BN_TO_ASCII = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")
PHONE_RE = re.compile(r"(?<!\d)(?:\+?88[\s-]?)?(01\d(?:[\s-]?\d){8})(?!\d)")
TRX_RE = re.compile(r"\b(?:T\d{8}|TL-\d{4}|TX[0-9A-F]{8})\b", re.IGNORECASE)
NUMBER_WORDS = {
    "ek": 1, "এক": 1, "dui": 2, "দুই": 2, "tin": 3, "তিন": 3, "char": 4, "চার": 4, "pach": 5, "panch": 5,
    "পাঁচ": 5, "পাচ": 5, "choy": 6, "ছয়": 6, "sat": 7, "সাত": 7, "at": 8, "aat": 8, "আট": 8, "noy": 9,
    "নয়": 9, "dosh": 10, "দশ": 10, "bish": 20, "বিশ": 20, "one": 1, "two": 2, "three": 3, "four": 4,
    "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "twenty": 20,
}
THOUSAND = r"(?:hajar|hazar|হাজার|thousand)"
CURRENCY = r"(?:৳|tk\.?|taka|টাকা|bdt|takar)"
CUES = {
    "call": ["call", "phone kore", "ফোন করে", "called", "ফোন"],
    "prize": ["lottery", "prize", "লটারি", "পুরস্কার"],
    "job": ["chakri", "job", "চাকরি", "registration fee", "রেজিস্ট্রেশন"],
    "officer": ["officer", "customer care", "অফিসার", "কাস্টমার কেয়ার"],
    "otp_pin": ["otp", " pin", "পিন", "ওটিপি"],
    "returned": ["ferot dilam", "returned", "ফেরত দিয়েছি", "ferot disi"],
    "wrong": ["vul", "bhul", "wrong", "ভুল", "mistake"],
}
SCAM_CUES = ("call", "prize", "job", "officer", "otp_pin", "returned")
BANGLISH_MARKERS = ["vul", "bhul", "taka", "bhai", "ami", "kore", "pathai", "gese", "korsi", "koren", "ekhon", "dike", "chole"]
SLA_WORKING_DAYS = 10
WEEKEND = (4, 5)                      # Friday, Saturday (Python weekday numbers)


def to_ascii_digits(text: str) -> str:
    return text.translate(BN_TO_ASCII)


def detect_language(text: str) -> str:
    if re.search(r"[ঀ-৿]", text):
        return "bn"
    low = text.lower()
    return "banglish" if sum(1 for m in BANGLISH_MARKERS if re.search(rf"\b{m}", low)) >= 2 else "en"


def _words_to_numbers(text: str) -> str:
    def repl(m: re.Match) -> str:
        head = m.group(1)
        value = NUMBER_WORDS.get(head.lower()) if not head.replace(".", "").isdigit() else float(head)
        return str(int(float(value) * 1000)) if value is not None else m.group(0)

    words = "|".join(sorted(map(re.escape, NUMBER_WORDS), key=len, reverse=True))
    text = re.sub(rf"(\d+(?:\.\d+)?|{words})\s*{THOUSAND}", repl, text, flags=re.IGNORECASE)
    return re.sub(r"(?<![\w.])(\d+(?:\.\d+)?)\s*k\b", lambda m: str(int(float(m.group(1)) * 1000)), text, flags=re.IGNORECASE)


def _find_amount(text: str) -> float | None:
    t = re.sub(r"(?<=\d),(?=\d{3})", "", text)
    for pat in (rf"{CURRENCY}\s*(\d+(?:\.\d+)?)", rf"(\d+(?:\.\d+)?)\s*{CURRENCY}"):
        m = re.search(pat, t, flags=re.IGNORECASE)
        if m:
            return float(m.group(1))
    nums = [float(x) for x in re.findall(r"(?<!\d)(\d{3,6})(?!\d)", t)]
    nums = [n for n in nums if 10 <= n <= 50000]
    return max(nums) if nums else None


def _find_time(text: str) -> tuple[int | None, int | None]:
    low = text.lower()
    day = None
    if re.search(r"\b(today|ajke|aj)\b|আজ", low):
        day = 0
    if re.search(r"\b(yesterday|gotokal|kal)\b|গতকাল", low):
        day = 1
    m = re.search(r"(\d+)\s*(?:days?\s*ago|din\s*age|দিন\s*আগে)", low)
    if m:
        day = int(m.group(1))
    hour = None
    m = re.search(r"(?<!\d)(\d{1,2})\s*(am|pm)\b", low)
    if m:
        h = int(m.group(1)) % 12
        hour = h + 12 if m.group(2) == "pm" else h
    else:
        hits = list(re.finditer(r"(?<!\d)(\d{1,2})(?!\d)\s*(?:tar|tay|tai|ta(?![a-z])|টার|টায়|টা(?!কা))", low))
        # "2 ta digit" / "দুইটা ডিজিট" (a count of digits or numbers) is never a time
        hits = [h for h in hits if not re.match(r"\s*(?:digit|ডিজিট|number|নম্বর|songkha|সংখ্যা)", low[h.end():])]
        PERIOD = r"sokal|dupur|bikel|bikal|sondha|sondhay|raat|rat|সকাল|দুপুর|বিকাল|বিকেল|সন্ধ্যা|রাত"
        # "2 ta digit" (two digits) is a count, not a time: prefer the hit with a time-of-day word just before it
        m = next((h for h in hits if re.search(PERIOD, low[max(0, h.start() - 20):h.start()])), hits[0] if hits else None)
        if m:
            h = int(m.group(1)) % 12
            period = low[max(0, m.start() - 20):m.start()]
            if re.search(r"dupur|bikel|bikal|sondha|sondhay|raat|rat|দুপুর|বিকাল|বিকেল|সন্ধ্যা|রাত", period):
                hour = h + 12 if not (re.search(r"dupur|দুপুর", period) and h == 0) else 12
                if re.search(r"raat|rat|রাত", period) and h < 5:
                    hour = h
            elif re.search(r"sokal|সকাল", period):
                hour = h
            else:
                hour = h + 12 if 1 <= h <= 6 else h          # "2 tar dike" in a complaint almost always means 2 pm
    return day, hour


LAST4_RE = re.compile(
    r"(?:\.{2,}|…|শেষে|শেষের|(?:last|sesh|shesh|seser|shesher)(?:\s*(?:e|er))?)\s*(?:(?:4|four|char|চার)\s*(?:ta|ti|টা|টি)?\s*)?"
    r"(?:digits?|number|songkha|ডিজিট|সংখ্যা|নম্বর)?\s*(?:is|are|chilo|holo|ছিল|হলো|:)?\s*(\d{4})(?!\d)", re.IGNORECASE)


def extract(text: str) -> dict:
    """What the customer's words say, each field with where it came from (all 'rule' here)."""
    ascii_text = to_ascii_digits(text)
    out = dict(amount=None, number=None, number_last4=None, day_offset=None, hour=None, trx_id=None,
               language=detect_language(text), sources={})
    phones = [re.sub(r"[\s-]", "", m.group(1)) for m in PHONE_RE.finditer(ascii_text)]
    if phones:
        out["number"], out["sources"]["number"] = phones[0], "rule"
    else:
        m = LAST4_RE.search(ascii_text)
        if m:
            out["number_last4"], out["sources"]["number_last4"] = m.group(1), "rule"
            ascii_text = ascii_text[:m.start()] + " " + ascii_text[m.end():]
    trx = TRX_RE.search(ascii_text)
    if trx:
        out["trx_id"], out["sources"]["trx_id"] = trx.group(0).upper(), "rule"
    without_ids = TRX_RE.sub(" ", PHONE_RE.sub(" ", ascii_text))
    without_ids = re.sub(r"(?:\.{2,}|…)\s*\d{4}", " ", without_ids)
    amount = _find_amount(_words_to_numbers(without_ids))
    if amount is not None:
        out["amount"], out["sources"]["amount"] = amount, "rule"
    day, hour = _find_time(without_ids)
    if day is not None:
        out["day_offset"], out["sources"]["day_offset"] = day, "rule"
    if hour is not None:
        out["hour"], out["sources"]["hour"] = hour, "rule"
    low = " " + text.lower()
    out["cues"] = {k: any(w in low for w in words) for k, words in CUES.items()}
    return out


def match_transfer(e: dict, transfers: list[dict], now_ts: int, chosen_id: str | None = None) -> dict:
    """Which of the customer's recent transfers is this about? Scores amount, number, day and hour."""
    if chosen_id:
        for t in transfers:
            if t["id"] == chosen_id:
                return dict(transfer=t, confidence=1.0, how="chosen by the customer", candidates=[])
    scored = []
    for t in transfers:
        s, why = 0.0, []
        if e.get("amount"):
            gap = abs(t["amount"] - e["amount"]) / max(e["amount"], 1.0)
            s += 3.0 if gap < 0.005 else 1.5 if gap < 0.05 else 0.0
            if gap < 0.05:
                why.append("amount")
        to = t.get("number") or ""                              # the number as the customer typed it
        if e.get("number") and to == e["number"]:
            s, why = s + 4.0, why + ["number"]
        elif e.get("number_last4") and to.endswith(e["number_last4"]):
            s, why = s + 2.5, why + ["last 4 digits"]
        days_ago = (now_ts - t["ts"]) / 86_400
        if e.get("day_offset") is not None and abs(math.floor(days_ago) - e["day_offset"]) == 0:
            s, why = s + 1.0, why + ["day"]
        if e.get("hour") is not None and abs(((t["ts"] % 86_400) // 3_600) - e["hour"]) <= 1:
            s, why = s + 1.0, why + ["hour"]
        s += max(0.0, 0.5 - days_ago / 14)                      # prefer recent transfers on ties
        scored.append((s, t, why))
    scored.sort(key=lambda x: -x[0])
    if not scored or scored[0][0] < 2.5:
        return dict(transfer=None, confidence=0.0, how="no transfer matches: ask the customer for details",
                    candidates=[t for _, t, _ in scored[:3]])
    best, second = scored[0], (scored[1][0] if len(scored) > 1 else 0.0)
    conf = round(min(1.0, best[0] / 9.0) * (1.0 if best[0] - second >= 1.5 else 0.7), 2)
    return dict(transfer=best[1], confidence=conf, how="matched on " + ", ".join(best[2]),
                candidates=[t for _, t, _ in scored[1:3]])


def sla_deadline(opened: date, working_days: int = SLA_WORKING_DAYS) -> date:
    d, left = opened, working_days
    while left:
        d += timedelta(days=1)
        if d.weekday() not in WEEKEND:
            left -= 1
    return d
