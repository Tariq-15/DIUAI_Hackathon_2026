"""M1 complaint extractor: rules first, LLM second, disagreements flagged for the agent.

Rules catch exact patterns (phone numbers, TrxIDs, amounts, Bangla digits and number words). If an
LLM provider is configured, it reads the *masked* text into a fixed schema and fills only the gaps.
When rules and the LLM disagree, neither wins silently: the field is flagged for the agent.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

from ferot.llm.masking import PHONE_RE, TRX_RE, mask_pii, to_ascii_digits, unmask
from ferot.llm.provider import get_provider

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
    "sms": ["sms", "মেসেজ", "message"],
    "prize": ["lottery", "prize", "লটারি", "পুরস্কার"],
    "job": ["chakri", "job", "চাকরি", "registration fee", "রেজিস্ট্রেশন"],
    "officer": ["officer", "customer care", "অফিসার", "কাস্টমার কেয়ার"],
    "otp_pin": ["otp", " pin", "পিন"],
    "returned": ["ferot dilam", "returned", "ফেরত দিয়েছি", "ferot disi"],
    "failed": ["kete nise", "deducted", "কেটে নিয়েছে", "pay nai", "পায়নি", "did not get"],
    "wrong": ["vul", "bhul", "wrong", "ভুল", "mistake"],
}
BANGLISH_MARKERS = ["vul", "bhul", "taka", "bhai", "ami", "kore", "pathai", "gese", "korsi", "koren", "ekhon", "dike"]


@dataclass
class Extraction:
    amount: float | None = None
    number: str | None = None
    number_last4: str | None = None
    day_offset: int | None = None
    hour: int | None = None
    trx_id: str | None = None
    cues: dict[str, bool] = field(default_factory=dict)
    language: str = "en"
    sources: dict[str, str] = field(default_factory=dict)
    disagreements: list[str] = field(default_factory=list)
    llm_used: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


def detect_language(text: str) -> str:
    if re.search(r"[ঀ-৿]", text):
        return "bn"
    low = text.lower()
    if sum(1 for m in BANGLISH_MARKERS if re.search(rf"\b{m}", low)) >= 2:
        return "banglish"
    return "en"


def _words_to_numbers(text: str) -> str:
    # "pach hajar" / "৫ হাজার" / "5k" -> 5000
    def repl(m: re.Match) -> str:
        head = m.group(1)
        value = NUMBER_WORDS.get(head.lower()) if not head.replace(".", "").isdigit() else float(head)
        return str(int(float(value) * 1000)) if value is not None else m.group(0)

    words = "|".join(sorted(map(re.escape, NUMBER_WORDS), key=len, reverse=True))
    text = re.sub(rf"(\d+(?:\.\d+)?|{words})\s*{THOUSAND}", repl, text, flags=re.IGNORECASE)
    text = re.sub(r"(?<![\w.])(\d+(?:\.\d+)?)\s*k\b", lambda m: str(int(float(m.group(1)) * 1000)), text, flags=re.IGNORECASE)
    return text


def _find_amount(text: str) -> float | None:
    t = re.sub(r"(?<=\d),(?=\d{3})", "", text)
    for pat in (rf"{CURRENCY}\s*(\d+(?:\.\d+)?)", rf"(\d+(?:\.\d+)?)\s*{CURRENCY}"):
        m = re.search(pat, t, flags=re.IGNORECASE)
        if m:
            return float(m.group(1))
    nums = [float(x) for x in re.findall(r"(?<!\d)(\d{3,6})(?!\d)", t)]
    nums = [n for n in nums if 10 <= n <= 50000]
    return max(nums) if nums else None


def _find_time(text: str, lang: str) -> tuple[int | None, int | None]:
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
        m = re.search(r"(?<!\d)(\d{1,2})(?!\d)\s*(?:tar|tay|tai|ta(?![a-z])|টার|টায়|টা(?!কা))", low)
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
                hour = h + 12 if 1 <= h <= 6 else h  # "2 tar dike" in a complaint almost always means 2 pm
    return day, hour


def extract_rules(text: str) -> Extraction:
    ascii_text = to_ascii_digits(text)
    out = Extraction(language=detect_language(text))
    phones = [re.sub(r"[\s-]", "", m.group(1)) for m in PHONE_RE.finditer(ascii_text)]
    if phones:
        out.number, out.sources["number"] = phones[0], "rule"
    else:
        m = re.search(r"(?:\.{2,}|…|শেষে|last\s*(?:4|four)\s*digits?\s*(?:is|are)?)\s*(\d{4})(?!\d)", ascii_text, re.IGNORECASE)
        if m:
            out.number_last4, out.sources["number_last4"] = m.group(1), "rule"
    trx = TRX_RE.search(ascii_text)
    if trx:
        out.trx_id, out.sources["trx_id"] = trx.group(0).upper(), "rule"
    without_ids = TRX_RE.sub(" ", PHONE_RE.sub(" ", ascii_text))
    without_ids = re.sub(r"(?:\.{2,}|…)\s*\d{4}", " ", without_ids)
    amount = _find_amount(_words_to_numbers(without_ids))
    if amount is not None:
        out.amount, out.sources["amount"] = amount, "rule"
    day, hour = _find_time(without_ids, out.language)
    if day is not None:
        out.day_offset, out.sources["day_offset"] = day, "rule"
    if hour is not None:
        out.hour, out.sources["hour"] = hour, "rule"
    low = " " + text.lower()
    out.cues = {k: any(w in low for w in words) for k, words in CUES.items()}
    return out


def extract(text: str, use_llm: bool = True) -> Extraction:
    out = extract_rules(text)
    provider = get_provider()
    if not use_llm or provider.name == "offline":
        return out
    masked, mapping = mask_pii(text)
    llm = provider.extract(masked)
    if not llm:
        return out
    llm = unmask(llm, mapping)
    out.llm_used = True
    pairs = [("amount", llm.get("amount")), ("number", llm.get("recipient_token")),
             ("number_last4", llm.get("recipient_last4")), ("day_offset", llm.get("day_offset")),
             ("hour", llm.get("hour")), ("trx_id", llm.get("trx_token"))]
    for name, value in pairs:
        if value in (None, "") or (isinstance(value, str) and value.startswith("<")):
            continue
        current = getattr(out, name)
        if current is None:
            setattr(out, name, value)
            out.sources[name] = "llm"
        elif str(current) != str(value) and not (name == "amount" and abs(float(current) - float(value)) < 1):
            out.disagreements.append(name)
    for cue in llm.get("cues", []):
        if cue in out.cues and not out.cues[cue]:
            out.cues[cue] = True
    return out
