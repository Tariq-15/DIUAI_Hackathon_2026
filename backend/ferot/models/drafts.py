"""M8 drafted replies with guardrails.

Templates hold slots such as {amount}; code fills them from the case file, so no number is ever
typed by a model. An LLM may optionally polish the wording, then every draft must pass three checks:
  * grounded: every number in the text comes from the case file
  * no refund promise (rule R1: upay's terms put wrong-entry risk on the sender)
  * no tipping off in anything a recipient sees (rule R7, MLPA 2012 §6)
A draft that fails falls back to the plain template, which passes by construction (tested).
"""

from __future__ import annotations

import re

from ferot import config
from ferot.llm.masking import to_ascii_digits
from ferot.llm.provider import get_provider

T = {
    "customer_genuine": {
        "en": "Your complaint {case_id} is registered. We found the transfer of Tk {amount} to the number ending {last4}. We have asked for a temporary hold on the amount still in that wallet and are contacting the recipient for consent to return it. A return depends on the recipient's consent or on legal process. We will update you by {deadline}. Never share your PIN or OTP with anyone.",
        "bn": "আপনার অভিযোগ {case_id} গ্রহণ করা হয়েছে। শেষে {last4} নম্বরে পাঠানো {amount} টাকার লেনদেনটি আমরা খুঁজে পেয়েছি। ওই ওয়ালেটে থাকা অর্থের জন্য সাময়িক হোল্ডের অনুরোধ করা হয়েছে এবং ফেরত দেওয়ার সম্মতির জন্য প্রাপকের সাথে যোগাযোগ করা হচ্ছে। অর্থ ফেরত পাওয়া প্রাপকের সম্মতি বা আইনি প্রক্রিয়ার উপর নির্ভর করে। {deadline} তারিখের মধ্যে আপনাকে জানানো হবে। আপনার পিন বা ওটিপি কখনো কাউকে দেবেন না।",
    },
    "customer_genuine_no_balance": {
        "en": "Your complaint {case_id} is registered. The Tk {amount} sent to the number ending {last4} has already left the receiving wallet, so we are asking the recipient for consent to return it. If the recipient does not agree, you can file a General Diary (GD) at your nearest police station and share the GD number with us. A return depends on the recipient's consent or on legal process. We will update you by {deadline}.",
        "bn": "আপনার অভিযোগ {case_id} গ্রহণ করা হয়েছে। শেষে {last4} নম্বরে পাঠানো {amount} টাকা প্রাপকের ওয়ালেট থেকে ইতিমধ্যে সরিয়ে নেওয়া হয়েছে, তাই আমরা প্রাপকের কাছে ফেরত দেওয়ার সম্মতি চাইছি। প্রাপক রাজি না হলে নিকটস্থ থানায় সাধারণ ডায়েরি (জিডি) করে জিডি নম্বরটি আমাদের জানান। অর্থ ফেরত পাওয়া প্রাপকের সম্মতি বা আইনি প্রক্রিয়ার উপর নির্ভর করে। {deadline} তারিখের মধ্যে আপনাকে জানানো হবে।",
    },
    "customer_scam": {
        "en": "Your complaint {case_id} is registered and has been sent to our fraud team. We are reviewing the transfer of Tk {amount} to the number ending {last4} and have requested a temporary hold on any amount still available. You may also file a General Diary (GD) at your nearest police station. We will update you by {deadline}. upay never asks for your PIN or OTP.",
        "bn": "আপনার অভিযোগ {case_id} গ্রহণ করে আমাদের প্রতারণা প্রতিরোধ টিমের কাছে পাঠানো হয়েছে। শেষে {last4} নম্বরে পাঠানো {amount} টাকার লেনদেনটি পর্যালোচনা করা হচ্ছে এবং যে অর্থ এখনো আছে তার জন্য সাময়িক হোল্ডের অনুরোধ করা হয়েছে। আপনি নিকটস্থ থানায় সাধারণ ডায়েরি (জিডি) করতে পারেন। {deadline} তারিখের মধ্যে আপনাকে জানানো হবে। উপায় কখনো আপনার পিন বা ওটিপি চায় না।",
    },
    "customer_technical": {
        "en": "Your complaint {case_id} is registered. Our system shows the transfer of Tk {amount} was not completed. Our technical team is checking it; if an automatic reversal applies, the amount comes back to your account. We will update you by {deadline}.",
        "bn": "আপনার অভিযোগ {case_id} গ্রহণ করা হয়েছে। আমাদের সিস্টেমে দেখা যাচ্ছে {amount} টাকার লেনদেনটি সম্পূর্ণ হয়নি। টেকনিক্যাল টিম বিষয়টি দেখছে; স্বয়ংক্রিয় রিভার্সাল প্রযোজ্য হলে অর্থ আপনার অ্যাকাউন্টে ফিরে আসবে। {deadline} তারিখের মধ্যে আপনাকে জানানো হবে।",
    },
    "customer_reject_double": {
        "en": "Your complaint {case_id} has been reviewed. Our records show that Tk {amount} was already sent back after the original transfer, so we cannot take further action on this claim. If you disagree, you can ask for a supervisor review by calling {helpline}.",
        "bn": "আপনার অভিযোগ {case_id} পর্যালোচনা করা হয়েছে। আমাদের রেকর্ডে দেখা যাচ্ছে মূল লেনদেনের পর {amount} টাকা ইতিমধ্যে ফেরত পাঠানো হয়েছে, তাই এই দাবির বিষয়ে আর কোনো পদক্ষেপ নেওয়া সম্ভব নয়। আপনি একমত না হলে {helpline} নম্বরে কল করে সুপারভাইজারের পর্যালোচনা চাইতে পারেন।",
    },
    "customer_reject_false": {
        "en": "Your complaint {case_id} has been reviewed. Our records show {prior} earlier transfers from your account to this number, so this does not appear to be a wrong-number transfer. If it is about goods or services not received, you can raise a merchant dispute. If you disagree, you can ask for a supervisor review by calling {helpline}.",
        "bn": "আপনার অভিযোগ {case_id} পর্যালোচনা করা হয়েছে। আমাদের রেকর্ডে এই নম্বরে আপনার অ্যাকাউন্ট থেকে আগে {prior}টি লেনদেন দেখা যাচ্ছে, তাই এটি ভুল নম্বরে পাঠানো লেনদেন বলে মনে হচ্ছে না। পণ্য বা সেবা না পেয়ে থাকলে মার্চেন্ট বিরোধ জানাতে পারেন। আপনি একমত না হলে {helpline} নম্বরে কল করে সুপারভাইজারের পর্যালোচনা চাইতে পারেন।",
    },
    "customer_more_info": {
        "en": "Thank you for contacting us about complaint {case_id}. To find your transfer, please share the amount, the number you sent to and the approximate time, or the transaction ID from your SMS. Never share your PIN or OTP with anyone.",
        "bn": "অভিযোগ {case_id} এর জন্য ধন্যবাদ। আপনার লেনদেনটি খুঁজে পেতে টাকার পরিমাণ, যে নম্বরে পাঠিয়েছেন এবং আনুমানিক সময়, অথবা এসএমএস-এ পাওয়া ট্রানজেকশন আইডি জানান। আপনার পিন বা ওটিপি কখনো কাউকে দেবেন না।",
    },
    "customer_agent_route": {
        "en": "Your complaint {case_id} is registered. As required for agent-point transactions, it has first been sent to the distributor responsible for that agent. We will update you by {deadline}.",
        "bn": "আপনার অভিযোগ {case_id} গ্রহণ করা হয়েছে। নিয়ম অনুযায়ী এজেন্ট পয়েন্টের লেনদেন-সংক্রান্ত অভিযোগ প্রথমে সংশ্লিষ্ট ডিস্ট্রিবিউটরের কাছে পাঠানো হয়েছে। {deadline} তারিখের মধ্যে আপনাকে জানানো হবে।",
    },
    "recipient_consent": {
        "en": "Dear customer, Tk {amount} was sent to your account by mistake on {transfer_date}. If you agree to return it to the sender, please call {helpline}. Thank you for your help.",
        "bn": "প্রিয় গ্রাহক, {transfer_date} তারিখে ভুলবশত আপনার অ্যাকাউন্টে {amount} টাকা পাঠানো হয়েছে। আপনি রাজি থাকলে অর্থটি প্রেরককে ফেরত দিতে অনুগ্রহ করে {helpline} নম্বরে কল করুন। আপনার সহযোগিতার জন্য ধন্যবাদ।",
    },
    "recipient_neutral": {
        "en": "Dear customer, we would like to speak with you about a transaction on your account. Please call {helpline} at a convenient time.",
        "bn": "প্রিয় গ্রাহক, আপনার অ্যাকাউন্টের একটি লেনদেন বিষয়ে আমরা আপনার সাথে কথা বলতে চাই। সুবিধামতো সময়ে {helpline} নম্বরে কল করুন।",
    },
}

REFUND_PROMISES = ["will refund", "guarantee", "definitely", "will be returned to you", "full refund",
                   "you will get your money back", "অবশ্যই ফেরত", "নিশ্চিতভাবে", "ফেরত দেওয়া হবে", "ফেরত পাবেন"]
AML_SUBJECT_DRAFTS = {"customer_reject_double"}
TIPPING_OFF = ["fraud", "scam", "suspicious", "suspected", "mule", "laundering", "aml", "police", "blocked",
               "investigation", "প্রতারণা", "জালিয়াতি", "সন্দেহ", "লন্ডারিং", "পুলিশ", "তদন্ত"]


def _numbers(text: str) -> set[str]:
    return set(re.findall(r"\d+", to_ascii_digits(text).replace(",", "")))


def check_draft(text: str, allowed_numbers: set[str], audience: str) -> dict:
    low = text.lower()
    unsupported = sorted(n for n in _numbers(text) if n not in allowed_numbers)
    promises = [p for p in REFUND_PROMISES if p in low]
    tipping = [w for w in TIPPING_OFF if w in low] if audience == "recipient" else []
    return {"grounded": not unsupported, "unsupported_numbers": unsupported,
            "no_refund_promise": not promises, "refund_phrases": promises,
            "no_tipping_off": not tipping, "tipping_phrases": tipping,
            "passed": not unsupported and not promises and not tipping}


def slot_values(case_id: str, facts: dict, deadline: str) -> dict:
    lim = config.limits()
    return {"case_id": case_id, "amount": f"{facts.get('amount', 0):,.0f}", "last4": str(facts.get("recipient", ""))[-4:],
            "deadline": deadline, "helpline": lim["helpline"], "prior": str(facts.get("earlier_transfers_to_recipient", 0)),
            "transfer_date": str(facts.get("transfer_ts", ""))[:10], "hold": f"{facts.get('hold_amount', 0):,.0f}"}


def generate_drafts(draft_ids: list[str], case_id: str, facts: dict, deadline: str,
                    internal_note: str, use_llm: bool = True) -> dict:
    values = slot_values(case_id, facts, deadline)
    allowed = set().union(*(_numbers(str(v)) for v in values.values()))
    provider = get_provider()
    out = {}
    for draft_id in draft_ids:
        if draft_id == "internal_note":
            out[draft_id] = {"audience": "internal", "en": internal_note, "source": "template",
                             "checks": {"passed": True}}
            continue
        audience = "recipient" if draft_id.startswith("recipient") else "customer"
        # the reader of these drafts may be the subject of an AML review: never tip them off (R7)
        check_as = "recipient" if draft_id in AML_SUBJECT_DRAFTS or audience == "recipient" else audience
        entry = {"audience": audience, "source": "template"}
        for lang in ("en", "bn"):
            template = T[draft_id][lang]
            text = template.format(**values)
            checks = check_draft(text, allowed, check_as)
            if use_llm and provider.name != "offline" and audience == "customer":
                polished = provider.rephrase(template, lang)
                if polished:
                    try:
                        candidate = polished.format(**values)
                        cand_checks = check_draft(candidate, allowed, check_as)
                        if cand_checks["passed"]:
                            text, checks, entry["source"] = candidate, cand_checks, "llm"
                    except (KeyError, IndexError, ValueError):
                        pass  # the model broke a placeholder: keep the template
            entry[lang] = text
            entry[f"checks_{lang}"] = checks
        entry["checks"] = {"passed": entry["checks_en"]["passed"] and entry["checks_bn"]["passed"]}
        out[draft_id] = entry
    return out
