"""Investigation copilot: a fixed four-part case report built only from structured evidence.

    what happened -> why it is risky -> recommended action -> confidence and limits

The template writer is the default and works offline. An LLM may optionally rewrite the wording
(PROHORI_LLM=anthropic + ANTHROPIC_API_KEY): it receives structured facts only (never a customer's
own words), its output is display-only, and it is rejected if it contains any number that is not in
the evidence. Models score, plain rules decide the recommended actions, the analyst approves.
"""
from __future__ import annotations

import json
import os
import re

SECTIONS = ("what_happened", "why_risky", "recommended_action", "confidence_limits")
LLM_MODEL = "claude-opus-5-5"

ACTIONS = {
    "FREEZE_RECIPIENT": ("Temporarily freeze the receiving wallet until the review is finished",
                         "তদন্ত শেষ না হওয়া পর্যন্ত প্রাপকের ওয়ালেট সাময়িকভাবে স্থগিত"),
    "VERIFY_OWNER": ("Call the account owner on the registered number from a known upay line before anything is released",
                     "কিছু ছাড়ার আগে নিবন্ধিত নম্বরে মালিককে upay-এর পরিচিত লাইন থেকে কল করে যাচাই"),
    "CONTACT_SENDERS": ("Contact the people who recently paid this wallet: they may be victims",
                        "সম্প্রতি এই ওয়ালেটে যাঁরা টাকা পাঠিয়েছেন তাঁদের সাথে যোগাযোগ (তাঁরা ভুক্তভোগী হতে পারেন)"),
    "REVIEW_AGENT": ("Open an Agent Watch review of the agent that paid out the cash",
                     "যে এজেন্ট ক্যাশ-আউট দিয়েছেন তাঁর Agent Watch পর্যালোচনা"),
    "RELEASE_TRANSACTION": ("Release the held transfer to the recipient",
                            "আটকে রাখা লেনদেনটি প্রাপকের কাছে ছেড়ে দিন"),
    "WATCHLIST": ("Add the receiving wallet to the watchlist", "প্রাপকের ওয়ালেট নজরদারি তালিকায়"),
    "DISMISS": ("Dismiss as a false alarm and record why", "ভুল সতর্কতা হিসেবে বাতিল (কারণসহ)"),
    "HOLD_DISPUTED_AMOUNT": ("Request a temporary hold of the disputed amount (capped at what the wallet holds)",
                             "বিরোধকৃত পরিমাণ সাময়িকভাবে আটকানোর অনুরোধ (ওয়ালেটে যা আছে তার বেশি নয়)"),
    "ASK_RECIPIENT_CONSENT": ("Ask the recipient to agree to return the money", "প্রাপকের কাছে টাকা ফেরতের সম্মতি চাওয়া"),
    "ASK_CUSTOMER_DETAILS": ("Ask the customer which transfer, how much and when", "গ্রাহকের কাছে লেনদেন, পরিমাণ ও সময় জানতে চাওয়া"),
}
LANG = {"bn": "Bangla", "banglish": "Banglish", "en": "English"}


def _tk(v) -> str:
    return f"Tk {float(v):,.0f}"


def _num(v, nd=1):
    v = float(v)
    return f"{v:.{nd}f}".rstrip("0").rstrip(".") if v != int(v) else f"{int(v)}"


def facts_for(alert: dict, network: dict, context: dict) -> dict:
    """Everything the report may say, as plain values. Nothing else reaches the writer (or an LLM)."""
    ev = alert.get("evidence") or {}
    r, s, t = alert["receiver_id"], alert["sender_id"], alert["ts_sec"]
    edges = [e for e in network.get("edges", []) if not e.get("attempt")]
    into = [e for e in edges if e["target"] == r and e["source"] != s and e["ts"] <= t]
    payers = {e["source"] for e in into}
    cash = [e for e in edges if e["source"] == r and e["type"] == "CASH_OUT" and e["ts"] <= t]
    onward = [e for e in edges if e["source"] == r and e["type"] == "SEND_MONEY" and e["ts"] <= t]
    g = lambda k: ev.get(k)                                                    # noqa: E731
    f = dict(
        alert_id=alert["id"], when=context.get("when"), sender=s, receiver=r, amount=alert["amount"],
        txn_type=alert["txn_type"], risk_score=alert["risk_score"], band=alert["band"],
        policy_override=alert.get("policy_override"), p_fraud_calibrated=alert.get("p_fraud_calibrated"),
        anomaly_percentile=alert.get("anomaly"), graph_score=alert.get("graph"),
        reasons=[x["en"] for x in alert.get("reasons", [])],
        receiver_age_days=None if g("cp_age_days") is None else int(round(g("cp_age_days"))),
        receiver_payers_24h=len(payers), receiver_inflow_24h=round(sum(e["amount"] for e in into), 2),
        receiver_cash_out=round(sum(e["amount"] for e in cash), 2), cash_out_agents=sorted({e["target"] for e in cash}),
        receiver_onward=round(sum(e["amount"] for e in onward), 2), receiver_complaints=g("cp_complaints"),
        first_transfer_to_receiver=g("pair_first") == 1, drain_pct=None if g("drain_ratio") is None else int(round(100 * min(g("drain_ratio"), 1))),
        times_largest_before=None if g("amount_vs_max") is None else round(g("amount_vs_max"), 1),
        hours_since_sim_swap=g("hrs_since_sim_swap") if (g("hrs_since_sim_swap") or 999) < 72 else None,
        hours_on_new_phone=min(g("device_age_hours") or 999, g("hrs_since_dev_change") or 999),
        wallets_on_phone=g("device_n_wallets"), customer_choice=alert.get("customer_choice"),
        status=alert.get("status"), source=alert.get("source"),
        honest_warning_rate_pct=context.get("honest_warning_rate_pct"), helpline="16268",
        suggested=alert.get("suggestion"),
        p_fraud_pct=round(100 * (alert.get("p_fraud_calibrated") or 0)),
        anomaly_pct=None if alert.get("anomaly") is None else round(100 * alert["anomaly"]),
        graph_score_2dp=None if alert.get("graph") is None else round(alert["graph"], 2),
    )
    if f["hours_on_new_phone"] >= 72:
        f["hours_on_new_phone"] = None
    return f


def recommend(f: dict) -> list[str]:
    """Plain rules pick from a fixed list. The analyst can choose any action; these are pre-selected."""
    rec = []
    collector = f["receiver_payers_24h"] >= 5 and (f["receiver_age_days"] is not None and f["receiver_age_days"] < 14)
    takeover = f["hours_since_sim_swap"] is not None or f["hours_on_new_phone"] is not None
    if takeover:
        rec.append("VERIFY_OWNER")
    if collector or (takeover and (f["receiver_age_days"] or 9999) < 30) or (f["wallets_on_phone"] or 0) >= 3:
        rec.append("FREEZE_RECIPIENT")
    if collector or (f["receiver_complaints"] or 0) >= 1:
        rec.append("CONTACT_SENDERS")
    if f["cash_out_agents"] and (collector or f["receiver_cash_out"] > 0.5 * max(f["receiver_inflow_24h"], 1)):
        rec.append("REVIEW_AGENT")
    if not rec:
        rec.append("WATCHLIST")
    return rec


def template_report(f: dict) -> dict:
    what = [f"{f['when']}: {f['sender']} tried to send {_tk(f['amount'])} to {f['receiver']}"
            + (" (first transfer between them)." if f["first_transfer_to_receiver"] else ".")]
    if f["receiver_age_days"] is not None:
        line = f"{f['receiver']} was opened {f['receiver_age_days']} day(s) before."
        if f["receiver_payers_24h"]:
            line += (f" In the 24 hours before, {f['receiver_payers_24h']} other wallet(s) sent it "
                     f"{_tk(f['receiver_inflow_24h'])} in total.")
        if f["receiver_cash_out"]:
            line += f" It cashed out {_tk(f['receiver_cash_out'])} at {', '.join(f['cash_out_agents'])}."
        if f["receiver_onward"]:
            line += f" It sent {_tk(f['receiver_onward'])} on to other wallets."
        what.append(line)
    if f.get("suggested"):
        sg = f["suggested"]
        who = f"{sg['name']} " if sg.get("name") else ""
        what.append(f"Possible keypad slip: the number typed ({sg.get('typed')}) is one slip from {who}({sg['msisdn']}), "
                    f"whom the customer has paid {sg['count']} times.")
    if f["hours_since_sim_swap"] is not None or f["hours_on_new_phone"] is not None:
        parts = []
        if f["hours_since_sim_swap"] is not None:
            parts.append(f"the SIM was replaced {_num(f['hours_since_sim_swap'])} hour(s) earlier")
        if f["hours_on_new_phone"] is not None:
            parts.append(f"the transfer came from a phone first seen on the account {_num(f['hours_on_new_phone'])} hour(s) earlier")
        if (f["wallets_on_phone"] or 0) >= 3:
            parts.append(f"that phone is linked to {int(f['wallets_on_phone'])} wallets")
        what.append("Account signals: " + "; ".join(parts) + ".")
    choice = {"cancelled": "cancelled the transfer", "confirmed": "confirmed after the warning",
              "confirmed_pin": "re-entered the PIN and sent", "used_suggested": "switched to the suggested number",
              None: "has not answered yet"}
    if f["source"] == "live":
        what.append(f"Prohori scored it {_num(f['risk_score'])}/100 ({f['band']}); the customer {choice.get(f['customer_choice'], f['customer_choice'])}.")
    else:
        what.append(f"Historical test-window transaction, scored {_num(f['risk_score'])}/100 ({f['band']}).")

    why = list(f["reasons"])
    if f["policy_override"]:
        why.append(f"Policy rule applied: {f['policy_override'].replace('_', ' ')}.")
    model = f"Model view: LightGBM fraud probability {f['p_fraud_pct']}% (calibrated)"
    if f["anomaly_pct"] is not None:
        model += f", behaviour more unusual than {f['anomaly_pct']}% of transactions"
    if (f["graph_score"] or 0) >= 0.5:
        model += f", network-pattern score {_num(f['graph_score_2dp'], 2)}"
    why.append(model + ".")

    codes = recommend(f)
    act = [ACTIONS[c][0] + "." for c in codes]

    limits = [f"The score ranks risk; it is not proof. Calibrated fraud probability: {f['p_fraud_pct']}%.",
              "The model sees money movements and account signals only. It does not know who owns the receiving "
              "wallet or what the sender was promised.",
              "Network evidence covers the 24 hours before the transfer."]
    if f.get("honest_warning_rate_pct") is not None:
        limits.append(f"On the held-out test days, {_num(f['honest_warning_rate_pct'])}% of honest transactions also got "
                      "a warning, so a busy shop or a family wallet can look like this.")
    limits.append(f"Trained and tested on synthetic data. A person approves every freeze; the customer can call {f['helpline']}.")
    return dict(what_happened=what, why_risky=why, recommended_action=act, confidence_limits=limits,
                actions=codes, generated_by="template")


_NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _numbers(text: str) -> set[str]:
    out = set()
    for m in _NUM.findall(text):
        v = m.replace(",", "")
        out.add(v.rstrip("0").rstrip(".") if "." in v else v)
    return out


def unsupported_numbers(text: str, sources: list[str]) -> list[str]:
    allowed = set().union(*(_numbers(s) for s in sources))
    return sorted(_numbers(text) - allowed)


SYSTEM = (
    "You edit fraud case reports for upay's risk analysts. You receive JSON with `facts` (structured evidence) "
    "and `draft` (four sections, each a list of sentences). Rewrite each section in clear, plain English for an "
    "analyst, keeping every fact. Use only the facts and the draft: add no numbers, names, causes or advice that "
    "are not there, and keep the recommended actions exactly as given. Reply with only a JSON object with the keys "
    "what_happened, why_risky, recommended_action, confidence_limits; each value is a list of short sentences."
)


def polish_with_llm(report: dict, facts: dict) -> dict | None:
    """Optional wording pass. Returns None (keep the template) when disabled, unavailable or ungrounded."""
    if os.environ.get("PROHORI_LLM", "offline").lower() != "anthropic":
        return None
    try:
        import anthropic
    except ImportError:
        return None
    draft = {k: report[k] for k in SECTIONS}
    payload = json.dumps({"facts": facts, "draft": draft}, ensure_ascii=False, default=str)
    try:
        client = anthropic.Anthropic()
        resp = client.beta.messages.create(
            model=LLM_MODEL, max_tokens=4000, system=SYSTEM,
            betas=["server-side-fallback-2026-07-01"], fallbacks="default",
            output_config={"effort": "low"},
            messages=[{"role": "user", "content": payload}],
        )
    except Exception:                                    # network, auth, SDK version: the template stays
        return None
    if resp.stop_reason != "end_turn":
        return None
    text = "".join(b.text for b in resp.content if b.type == "text")
    m = re.search(r"\{.*\}", text, re.S)
    try:
        out = json.loads(m.group(0)) if m else None
    except json.JSONDecodeError:
        return None
    if not isinstance(out, dict) or any(not isinstance(out.get(k), list) for k in SECTIONS):
        return None
    joined = " ".join(str(x) for k in SECTIONS for x in out[k])
    bad = unsupported_numbers(joined, [payload])
    if bad:
        return None
    return dict({k: [str(x) for x in out[k]] for k in SECTIONS}, actions=report["actions"],
                generated_by=f"{LLM_MODEL} (rewrite of the template, numbers checked)")


def complaint_report(a: dict, network: dict, context: dict) -> dict:
    """A wrong-send complaint: what the customer said, which transfer, what kind of case, what to do, what is promised."""
    c = a["complaint"]
    e, t, slip = c["extraction"], c["match"]["transfer"], c.get("slip")
    ev = a.get("evidence") or {}
    f = dict(case_id=a["id"], filed_at=c["filed_at"], claimant=a["sender_id"], language=LANG.get(c["language"], c["language"]),
             problem=c["problem"], amount_read=e.get("amount"), number_read=e.get("number") or e.get("number_last4"),
             day_offset=e.get("day_offset"), hour=e.get("hour"), recipient=a["receiver_id"] or None,
             recipient_age_days=None if ev.get("cp_age_days") is None else int(round(ev["cp_age_days"])),
             recipient_balance=c["recipient_balance"], holdable=c["holdable"], deadline=c["deadline"],
             case_type=c["case_type"], case_label=c["case_label"], model_risk=a.get("risk_score"), model_band=c.get("probe_band"),
             reasons=[r["en"] for r in a.get("reasons", [])][:3], match_how=c["match"]["how"],
             match_confidence=c["match"]["confidence"], helpline="16268", escalation="16236")
    if t:
        f.update(transfer_id=t["id"], transfer_amount=t["amount"], transfer_number=t["number"], transfer_at=t["at"])
    if slip:
        f.update(slip_msisdn=slip["msisdn"], slip_name=slip.get("name"), slip_count=slip["count"])
    words = c["text"] if len(c["text"]) <= 200 else c["text"][:200] + "…"
    what = [f"{f['filed_at'].replace('T', ' ')[:16]}: {f['claimant']} reported, in {f['language']}: “{words}”"]
    read = []
    if f["amount_read"]:
        read.append(f"amount {_tk(f['amount_read'])}")
    if f["number_read"]:
        read.append(f"number {f['number_read']}")
    if f["day_offset"] is not None:
        read.append({0: "today", 1: "yesterday"}.get(f["day_offset"], f"{f['day_offset']} days ago"))
    if f["hour"] is not None:
        read.append(f"about {f['hour']:02d}:00")
    what.append("Read from the words (rules): " + (", ".join(read) if read else "nothing specific") + ".")
    if t:
        what.append(f"Matched transfer {t['id']}: {_tk(t['amount'])} to {t['number']} ({a['receiver_id']}) at "
                    f"{t['at'].replace('T', ' ')[:16]}, {c['match']['how']} (confidence {c['match']['confidence']}).")
        age = f"was opened {f['recipient_age_days']} day(s) before and " if f["recipient_age_days"] is not None else ""
        what.append(f"The receiving wallet {age}now holds {_tk(f['recipient_balance'])}: {_tk(f['holdable'])} of the disputed "
                    f"amount can still be held.")
    else:
        what.append("No transfer in the customer's last 7 days matches the words.")
    case = c["case_type"]
    if case == "genuine_wrong_send":
        why = [f"The number paid ({t['number']}) is one keypad slip from {(slip.get('name') + ' ') if slip.get('name') else ''}"
               f"({slip['msisdn']}), whom the customer has paid {slip['count']} times.",
               f"The receiving wallet does not look like a scam drop: the model scores a transfer to it {_num(a['risk_score'])}/100 "
               f"({c['probe_band']})."]
    elif case == "likely_scam_victim":
        cues = [k for k, v in e["cues"].items() if v and k != "wrong"]
        why = (["The customer says it was a scam."] if c["problem"] == "scam" else []) \
            + ([f"The words mention: {', '.join(cues)}."] if cues else []) + f["reasons"] \
            + [f"Model view of the receiving wallet: {_num(a['risk_score'])}/100 ({c['probe_band']})."]
        why = [x for x in why if x]
    elif case == "needs_review":
        why = ["No keypad slip from a contact the customer pays often, and the receiving wallet does not look like a scam drop "
               f"({_num(a['risk_score'])}/100). It may have been deliberate, or a different mistake."]
    else:
        why = ["The words do not identify a transfer in the last 7 days."]
    codes = {"genuine_wrong_send": ["HOLD_DISPUTED_AMOUNT", "ASK_RECIPIENT_CONSENT"],
             "likely_scam_victim": ["HOLD_DISPUTED_AMOUNT", "FREEZE_RECIPIENT", "CONTACT_SENDERS"],
             "needs_review": ["ASK_RECIPIENT_CONSENT"], "needs_details": ["ASK_CUSTOMER_DETAILS"]}[case]
    if t and f["holdable"] <= 0:
        codes = [x for x in codes if x != "HOLD_DISPUTED_AMOUNT"]
    act = [ACTIONS[x][0] + "." for x in codes]
    if "HOLD_DISPUTED_AMOUNT" in codes:
        act.append(f"Hold at most {_tk(f['holdable'])}: the disputed amount, capped at what the wallet holds now.")
    limits = ["upay's terms (§11.1): the sender is responsible for the number entered. A return needs the recipient's "
              "consent or a legal process; nothing here promises a refund.",
              f"Deadline {f['deadline']}: 10 working days (MFS Regulations 2022 §17.3; Friday and Saturday excluded).",
              "The customer's words were read by rules, not a language model; check the matched transfer before acting.",
              "The case type comes from plain rules and the model's view of the receiving wallet, not a trained complaint classifier.",
              f"A person approves every hold; the customer can escalate to Bangladesh Bank ({f['escalation']})."]
    return dict(what_happened=what, why_risky=why, recommended_action=act, confidence_limits=limits, actions=codes,
                generated_by="template (complaint)", facts=f,
                action_labels={k: {"en": ACTIONS[k][0], "bn": ACTIONS[k][1]} for k in ACTIONS})


def case_report(alert: dict, network: dict, context: dict, use_llm: bool = False) -> dict:
    f = facts_for(alert, network, context)
    rep = template_report(f)
    if use_llm:
        better = polish_with_llm(rep, f)
        if better:
            rep = better
    rep["action_labels"] = {c: {"en": ACTIONS[c][0], "bn": ACTIONS[c][1]} for c in ACTIONS}
    rep["facts"] = f
    return rep
