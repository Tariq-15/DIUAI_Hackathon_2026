"""'Am I talking to a scammer?' A transparent rule check for a message or call script.

The customer pastes what the caller or SMS said (Bangla, Banglish or English). Each known social-
engineering cue is a named pattern, so the answer can say exactly why. Rules, not a model: there
are no labelled scam messages in the synthetic world to learn from, and a rule list is easy to
audit and extend on site. The text is not stored and is never sent to an LLM.
"""
from __future__ import annotations

import re

# code -> (weight, regex, English label, Bangla label, Bangla advice)
CUES = {
    "asks_pin_otp": (3, r"(otp|o\.?t\.?p|ও\s?টি\s?পি|ওটিপি|\bpin\b|পিন|কোড|code|verification|ভেরিফিকেশন|গোপন নম্বর)",
                     "Asks for a PIN, OTP or code", "পিন / ওটিপি / কোড চাওয়া হয়েছে",
                     "upay কখনো ফোন বা মেসেজে আপনার পিন বা ওটিপি চায় না। কাউকে বলবেন না।"),
    "impersonates": (2, r"(upay|উপায়|বিকাশ|bkash|নগদ|nagad|ব্যাংক|bank|customer care|কাস্টমার কেয়ার|হেল্পলাইন|অফিস থেকে|"
                        r"পুলিশ|police|র‍্যাব|\brab\b|ডিবি|thana|থানা|জেল|jail|উকিল|lawyer|ম্যাজিস্ট্রেট|কর্মকর্তা|officer|agent)",
                     "Claims to be upay, a bank, police or an official", "নিজেকে upay, ব্যাংক, পুলিশ বা কর্মকর্তা বলে দাবি",
                     "পরিচয় যাচাই করতে নিজে ১৬২৬৮ নম্বরে কল করুন; যে নম্বর থেকে কল এসেছে সেখানে নয়।"),
    "threat_urgency": (2, r"(এখনই|এক্ষুনি|জরুরি|urgent|immediately|দ্রুত|তাড়াতাড়ি|\d+\s?(মিনিট|ঘণ্টা|minute|hour)|block|ব্লক|বন্ধ হয়ে যাবে|"
                          r"বন্ধ করে দেওয়া|suspend|arrest|গ্রেফতার|মামলা|case হবে|জরিমানা|fine)",
                       "Threatens or rushes you", "ভয় দেখানো বা তাড়াহুড়া করানো",
                       "প্রতারকেরা সময় দেয় না। থামুন, ফোন রেখে দিন, পরিবারের কারো সাথে কথা বলুন।"),
    "prize_lottery": (2, r"(লটারি|lottery|পুরস্কার|prize|জিতেছেন|won|winner|বিজয়ী|মোটরসাইকেল|গাড়ি জিত|গিফট|gift|বোনাস|bonus|ক্যাশব্যাক জিত)",
                      "Promises a prize, lottery or gift", "পুরস্কার, লটারি বা উপহারের প্রলোভন",
                      "পুরস্কার পেতে কখনো আগে টাকা দিতে হয় না।"),
    "fee_first": (2, r"(চাকরি|job|লোন|loan|ঋণ|ভিসা|visa|রেজিস্ট্রেশন ফি|registration fee|processing fee|প্রসেসিং|অগ্রিম|advance|জামানত|"
                     r"security deposit|ডেলিভারি চার্জ|delivery charge|কাস্টমস|customs|পার্সেল|parcel)",
                  "Asks for a fee first (job, loan, parcel, visa)", "চাকরি, লোন, পার্সেল বা ভিসার জন্য আগে টাকা চাওয়া",
                  "আগে টাকা চাইলে সাবধান। প্রতিষ্ঠানটির অফিসিয়াল নম্বরে নিজে যোগাযোগ করুন।"),
    "wrong_send_return": (2, r"(ভুল করে|ভুলে|ভুল নম্বরে|wrong number|by mistake|mistake|ফেরত দিন|ফেরত পাঠান|return (the|my) money|send it back)",
                          "Says money was sent to you by mistake and asks for it back", "ভুল করে টাকা পাঠানো হয়েছে বলে ফেরত চাওয়া",
                          "নিজের ব্যালেন্স ও লেনদেনের ইতিহাস দেখুন। সত্যিই টাকা এসে থাকলে ১৬২৬৮-এর মাধ্যমে ফেরত দিন, সরাসরি নয়।"),
    "remote_app_link": (3, r"(https?://|www\.|\.com|\.xyz|লিংক|link|anydesk|any desk|teamviewer|quick ?support|screen ?share|অ্যাপ ডাউনলোড|app install|apk)",
                        "Sends a link or asks you to install an app", "লিংক পাঠানো বা অ্যাপ ইনস্টল করতে বলা",
                        "অপরিচিত লিংকে ক্লিক বা স্ক্রিন-শেয়ার অ্যাপ ইনস্টল করবেন না; এতে আপনার ফোনের নিয়ন্ত্রণ চলে যেতে পারে।"),
    "secrecy": (2, r"(কাউকে বলবেন না|কাউকে বলো না|গোপন রাখুন|don'?t tell|keep (it )?secret|পরিবারকে জানাবেন না)",
                "Tells you to keep it secret", "গোপন রাখতে বলা",
                "যে কেউ গোপন রাখতে বললে সেটাই সবচেয়ে বড় সতর্কসংকেত।"),
    "send_money_now": (1, r"(টাকা পাঠান|টাকা পাঠাও|send money|সেন্ড মানি|ক্যাশ ইন করে|cash ?in|বিকাশ করুন|পেমেন্ট করুন|transfer)",
                       "Asks you to send or cash in money", "টাকা পাঠাতে বা ক্যাশ-ইন করতে বলা",
                       "যাকে চেনেন না তাকে টাকা পাঠানোর আগে Prohori-র সতর্কবার্তা মন দিয়ে পড়ুন।"),
}
ADVICE_EN = {
    "asks_pin_otp": "upay never asks for your PIN or OTP by phone or message. Do not tell anyone.",
    "impersonates": "To check who it is, call 16268 yourself, not the number that called you.",
    "threat_urgency": "Scammers do not give you time. Stop, hang up and talk to someone in your family.",
    "prize_lottery": "You never pay first to receive a prize.",
    "fee_first": "Be careful when someone asks for money first. Contact the organisation on its official number yourself.",
    "wrong_send_return": "Check your own balance and history. If money really arrived, return it through 16268, not directly.",
    "remote_app_link": "Do not open unknown links or install screen-sharing apps; they can take control of your phone.",
    "secrecy": "Being told to keep it secret is the biggest warning sign of all.",
    "send_money_now": "Before sending money to someone you do not know, read Prohori's warning carefully.",
}
_COMPILED = {k: re.compile(v[1], re.I) for k, v in CUES.items()}


def check(text: str) -> dict:
    text = (text or "")[:2000]
    found = []
    for code, (w, _rx, en, bn_, adv) in CUES.items():
        m = _COMPILED[code].search(text)
        if m:
            found.append(dict(code=code, weight=w, en=en, bn=bn_, advice_bn=adv, advice_en=ADVICE_EN[code], matched=m.group(0)))
    score = sum(c["weight"] for c in found)
    combo = {c["code"] for c in found}
    if score >= 5 or "asks_pin_otp" in combo and ("impersonates" in combo or "threat_urgency" in combo):
        verdict, bn_v, en_v = "high", "প্রায় নিশ্চিত প্রতারণার কৌশল", "Very likely a scam script"
    elif score >= 3:
        verdict, bn_v, en_v = "medium", "সন্দেহজনক, সাবধান থাকুন", "Suspicious: be careful"
    elif score >= 1:
        verdict, bn_v, en_v = "low", "কিছু সতর্কসংকেত আছে", "A few warning signs"
    else:
        verdict, bn_v, en_v = "none", "পরিচিত কোনো প্রতারণার সংকেত পাওয়া যায়নি", "No known scam cues found"
    return dict(verdict=verdict, verdict_bn=bn_v, verdict_en=en_v, score=score, cues=found,
                always_bn="সন্দেহ হলে লেনদেন করবেন না এবং ১৬২৬৮ নম্বরে কল করুন।",
                always_en="If in doubt, do not send money, and call 16268.",
                method="rule-based cue check (no model, text not stored)")
