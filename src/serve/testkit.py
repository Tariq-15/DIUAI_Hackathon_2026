"""Test kit: real numbers from the 683k-row synthetic dataset to try on the phone, with what Prohori answered.

    python -m src.serve.testkit          # -> artifacts/portable/test_kit.json, data/sample/test_numbers.csv,
                                         #    docs/test_numbers.md   (run by src.serve.portable after the export)

Judges do not have the dataset, so the app carries a short list of numbers to type, picked by rule from the data:
wallets the generator gave a fraud role (collector, scam recipient, fake seller, mule, card-fraud wallet), wallets
already reported to 16268, ordinary wallets, the demo customers' own contacts, a mistyped contact number, the staged
scams, and recharge tests. Every item was run through the same code the app calls (LiveWorld.preview, no alert, no
money moved) on a freshly staged demo world, and the answer is stored next to it. The fraud role comes from the
synthetic ground truth; the model never sees it. Some fraud wallets from earlier weeks are quiet now and pass: the
model scores the transfer and the recipient's recent behaviour, not a label, and the kit shows that too.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np
import pandas as pd

from src.common.config import ROOT, load_config, resolve

AMOUNT = 5000.0
ROLE_GROUPS = [   # (key, roles in wallet_truth, Bangla, English)
    ("collector", ("collector", "aged;collector"), "চাকরি/লটারির টাকা তোলার ওয়ালেট", "Collector wallet (job / lottery scams)"),
    ("scam_recipient", ("scam_recipient", "aged;scam_recipient"), "প্রতারণার টাকা নেওয়া ওয়ালেট", "Scam recipient"),
    ("fake_seller", ("fake_seller", "aged;fake_seller"), "ভুয়া অনলাইন বিক্রেতা", "Fake online seller"),
    ("mule", ("mule", "mule;recruited", "aged;mule"), "মিউল (টাকা পাচারের ওয়ালেট)", "Mule (passes stolen money on)"),
    ("card_fraud", ("card_fraud_wallet", "aged;card_fraud_wallet"), "চুরি করা কার্ডের টাকা নেওয়া ওয়ালেট", "Card-fraud wallet"),
]


def _item(w, persona, to, amount, label_bn, label_en, source, role=None, device=None, wallet=None, note_en=None, note_bn=None):
    r = w.preview(persona, to, amount, device)
    flags = []
    if r["suggestion"]:
        flags.append("wrong_number")
    if r["habit"] and r["habit"]["unusual"]:
        flags.append("unusual_amount")
    return dict(kind="send", persona=persona, number=to, wallet=wallet or r["receiver_id"], amount=amount, device=device,
                label_bn=label_bn, label_en=label_en, source=source, role=role, expected=r["band"],
                risk_score=round(float(r["risk_score"]), 1), flags=flags, policy=r["policy_override"],
                why_en=r["reasons"][0]["en"] if r["reasons"] and r["band"] != "ALLOW" else "No warning: it goes through.",
                why_bn=r["reasons"][0]["bn"] if r["reasons"] and r["band"] != "ALLOW" else "কোনো সতর্কতা নেই: টাকা চলে যায়।",
                note_en=note_en, note_bn=note_bn)


def build(w, data_dir: Path | None = None) -> dict:
    """The kit for a freshly staged LiveWorld `w`. Transfers are previews (nothing moves); the recharge items run
    last and for real, so use a world you throw away afterwards (src.serve.portable saves its snapshot first)."""
    from .live import GANG_PHONE, STAGED
    rahim, salma = w.personas["rahim"], w.personas.get("salma")
    maa, bro = rahim["contacts"][0], rahim["contacts"][1]
    msisdn_of = w.msisdn_of
    groups = []

    g = [_item(w, "rahim", maa["msisdn"], 800, "মা-কে ৳৮০০ (নিয়মিত)", "Tk 800 to Mother (usual)", "persona contact"),
         _item(w, "rahim", bro["msisdn"], 1000, f"{bro['name']}-কে ৳১,০০০", f"Tk 1,000 to {bro['name_en']}", "persona contact")]
    groups.append(dict(key="everyday", title_bn="১. স্বাভাবিক লেনদেন: কোনো বাধা নেই", title_en="1. Everyday transfers: no friction", items=g))

    g = []
    if getattr(w, "typo_number", None):
        g.append(_item(w, "rahim", w.typo_number, 800, "মা-র নম্বর, শেষের দুই ডিজিট উল্টে গেছে", "Mother's number with the last two digits swapped",
                       "dataset wallet (someone else's)", note_en="Type it digit by digit: the warning appears as you type.",
                       note_bn="ডিজিট ধরে ধরে লিখুন: লেখার সময়ই সতর্কতা আসে।"))
    g.append(_item(w, "rahim", maa["msisdn"], 15000, "মা-কে ৳১৫,০০০ (রহিম সাধারণত ৳৬০০ পাঠান)", "Tk 15,000 to Mother (Rahim usually sends about Tk 600)",
                   "persona contact", note_en="Same person, unusual amount: the amount-habit check.",
                   note_bn="একই মানুষ, অস্বাভাবিক পরিমাণ: পরিমাণের অভ্যাস যাচাই।"))
    groups.append(dict(key="mistakes", title_bn="২. ভুল নম্বর ও অস্বাভাবিক পরিমাণ", title_en="2. Wrong number and unusual amount", items=g))

    g = [_item(w, "rahim", msisdn_of[STAGED["collector"]], 15000, "নতুন নম্বরে ৳১৫,০০০ ‘চাকরির জামানত’", "Tk 15,000 'job deposit' to a new number",
               "staged scam", role="collector", note_en="2 days old; 14 strangers paid it in the last 3 hours; part already cashed out.",
               note_bn="২ দিন আগে খোলা; গত ৩ ঘণ্টায় ১৪ জন অপরিচিত টাকা পাঠিয়েছে; কিছু টাকা তোলা হয়ে গেছে।"),
         _item(w, "rahim", msisdn_of[STAGED["seller"]], 4500, "ফেসবুক পেজের বিক্রেতাকে ৳৪,৫০০ অগ্রিম", "Tk 4,500 advance to a Facebook-page seller",
               "staged scam", role="fake_seller", note_en="6 first-time buyers since last night; one already reported it to 16268.",
               note_bn="গত রাত থেকে ৬ জন নতুন ক্রেতা; একজন ইতিমধ্যে ১৬২৬৮-এ অভিযোগ করেছেন।")]
    warn = next((s for s in rahim["scenarios"] if s["key"] == "warn"), None)
    if warn:
        g.append(_item(w, "rahim", warn["to"], warn["amount"], "পরিচিতের দেওয়া নতুন নম্বরে ৳৬,০০০ ধার", "Tk 6,000 loan to a new number",
                       "dataset wallet (found by the model)"))
    if salma:
        sc = next((s for s in salma["scenarios"] if s["key"] == "takeover"), None)
        if sc:
            g.append(_item(w, "salma", sc["to"], sc["amount"], "সালমার অ্যাকাউন্ট: সিম বদল + নতুন ফোন থেকে বড় অঙ্ক",
                           "Salma's account: SIM swap + new phone, large transfer", "staged takeover", role="mule", device=GANG_PHONE,
                           note_en="Switch the customer to Salma (Account tab), then use her 'takeover test' scenario.",
                           note_bn="অ্যাকাউন্ট ট্যাবে গ্রাহক সালমা বেছে নিন, তারপর তাঁর ‘টেকওভার টেস্ট’ পরিস্থিতি।"))
    groups.append(dict(key="staged", title_bn="৩. সাজানো প্রতারণা (আজ সকালের)", title_en="3. Staged scams (this morning)", items=g))

    # ---------------------------------------------------------------- straight from the dataset
    truth = pd.read_parquet(data_dir / "wallet_truth.parquet") if data_dir and (data_dir / "wallet_truth.parquet").exists() else None
    taken = {it["wallet"] for gr in groups for it in gr["items"]} | set(STAGED.values()) | {p["wallet"] for p in w.personas.values()}
    taken |= {c["wallet"] for p in w.personas.values() for c in p["contacts"]}
    store = w.engine.store
    if truth is not None:
        g, quiet = [], []
        for key, roles, bn, en in ROLE_GROUPS:
            cands = sorted(x for x in truth[truth.roles.isin(roles)].wallet_id if x in msisdn_of and x not in taken)
            scored = []
            for x in cands[:120]:
                try:
                    r = w.preview("rahim", msisdn_of[x], AMOUNT)
                except (LookupError, ValueError):
                    continue
                scored.append((r["risk_score"], x, r["band"], bool(store.w[x].complaints) if x in store.w else False))
            scored.sort(reverse=True)
            # one never reported to 16268 (the model has to see it in the money movements), and the top one overall
            quiet_flag = next((s for s in scored if not s[3] and s[2] != "ALLOW"), None)
            picks = ([quiet_flag] if quiet_flag else []) + [s for s in scored if s is not quiet_flag][:2 - bool(quiet_flag)]
            for _, x, _b, rep in picks:
                g.append(_item(w, "rahim", msisdn_of[x], AMOUNT, bn, en, "dataset (fraud role)", role=key, wallet=x,
                               note_en="Already reported to 16268." if rep else "Never reported to 16268: caught from how money moves.",
                               note_bn="আগেই ১৬২৬৮-এ অভিযোগ হয়েছে।" if rep else "কখনো ১৬২৬৮-এ অভিযোগ হয়নি: টাকার চলাচল দেখে ধরা।"))
                taken.add(x)
            if key == "mule" and scored:
                x = next((s[1] for s in reversed(scored) if s[2] == "ALLOW"), scored[-1][1])
                quiet.append(_item(w, "rahim", msisdn_of[x], AMOUNT, "পুরনো মিউল, এখন চুপচাপ", "Old mule wallet, quiet for weeks",
                                   "dataset (fraud role)", role=key, wallet=x,
                                   note_en="The model scores the transfer and the wallet's recent behaviour, not a label: an idle "
                                           "mule from earlier weeks passes. That is the honest limit.",
                                   note_bn="মডেল লেনদেন ও ওয়ালেটের সাম্প্রতিক আচরণ দেখে, লেবেল নয়: কয়েক সপ্তাহ আগের চুপচাপ মিউল পার হয়ে যায়। এটাই সৎ সীমা।"))
                taken.add(x)
        groups.append(dict(key="dataset", title_bn="৪. ডেটাসেটের প্রতারণা-ওয়ালেট (৳৫,০০০ পাঠিয়ে দেখুন)",
                           title_en="4. Fraud wallets from the dataset (try Tk 5,000)", items=g))
        reported = sorted(wl for wl, s in store.w.items() if s.complaints and wl in msisdn_of and wl not in taken)
        scored = sorted(((w.preview("rahim", msisdn_of[x], AMOUNT)["risk_score"], x) for x in reported[:80]), reverse=True)
        rep = [_item(w, "rahim", msisdn_of[x], AMOUNT, "১৬২৬৮-এ আগে অভিযোগ হয়েছে", "Already reported to 16268", "dataset (reported)", wallet=x)
               for _, x in scored[:2]]
        rng = np.random.default_rng(5)
        ordinary = sorted(wl for wl, s in store.w.items() if str(wl).startswith("W") and s.n_txn > 40 and not s.complaints
                          and wl in msisdn_of and wl not in taken and wl not in set(truth.wallet_id))
        plain = [_item(w, "rahim", msisdn_of[x], 1000, "সাধারণ, পুরনো ওয়ালেট (প্রথমবার পাঠানো)", "Ordinary established wallet (first transfer)",
                       "dataset (no fraud role)", wallet=x) for x in rng.choice(ordinary, 2, replace=False)]
        groups.append(dict(key="other", title_bn="৫. অভিযোগ হওয়া, সাধারণ ও চুপচাপ ওয়ালেট", title_en="5. Reported, ordinary and quiet wallets",
                           items=rep + plain + quiet))

    none = next(n for n in (f"0109{i:07d}" for i in range(9_999_999, 0, -7)) if n not in w.engine.state["msisdn"])
    groups[-1]["items"].append(dict(kind="send", persona="rahim", number=none, wallet=None, amount=1000, device=None,
                                    label_bn="কারও নয় এমন নম্বর", label_en="A number no wallet uses", source="none", role=None,
                                    expected="NO_ACCOUNT", risk_score=None, flags=[], policy=None,
                                    why_en="No upay account uses this number (demo data).", why_bn="এই নম্বরে কোনো upay অ্যাকাউন্ট নেই (ডেমো ডেটা)।",
                                    note_en=None, note_bn=None))

    # ---------------------------------------------------------------- recharges (run for real: this world is thrown away)
    rc = []
    h = w.habits.summary(rahim["wallet"], w.clock()).get("recharge", {})
    for n, amt, bn, en in ((rahim["msisdn"], 50.0, "নিজের নম্বরে ৳৫০", "Tk 50 to your own number"),
                           (rahim["msisdn"], 1000.0, f"নিজের নম্বরে ৳১,০০০ (রহিম সাধারণত ৳{int(h.get('usual') or 0)} রিচার্জ করেন)",
                            f"Tk 1,000 to your own number (Rahim usually recharges about Tk {int(h.get('usual') or 0)})")):
        r = w.recharge("rahim", n, amt)
        rc.append(dict(kind="recharge", persona="rahim", number=n, amount=amt, label_bn=bn, label_en=en, source="persona",
                       expected=r["band"], flags=[x["code"] for x in r["reasons"]],
                       why_en=r["reasons"][0]["en"] if r["reasons"] else "No warning: the recharge goes through.",
                       why_bn=r["reasons"][0]["bn"] if r["reasons"] else "কোনো সতর্কতা নেই: রিচার্জ হয়ে যায়।",
                       steps=None))
        if r["alert_id"]:
            w.decide(r["alert_id"], "cancel")
    seq = [maa["msisdn"], bro["msisdn"], rahim["contacts"][2]["msisdn"]]
    outs = [w.recharge("rahim", n, 100.0) for n in seq]
    last = outs[-1]
    rc.append(dict(kind="recharge", persona="rahim", number=seq[-1], amount=100.0, steps=seq,
                   label_bn="এক ঘণ্টায় তিনটি ভিন্ন নম্বরে ৳১০০ করে", label_en="Tk 100 each to three different numbers within an hour",
                   source="persona contacts", expected=last["band"], flags=[x["code"] for x in last["reasons"]],
                   why_en=next((x["en"] for x in last["reasons"] if x["code"] == "recharge_burst"), None),
                   why_bn=next((x["bn"] for x in last["reasons"] if x["code"] == "recharge_burst"), None)))
    groups.append(dict(key="recharge", title_bn="৬. মোবাইল রিচার্জ", title_en="6. Mobile recharge", items=rc))

    n_items = sum(len(gr["items"]) for gr in groups)
    return dict(
        built_for=w.iso(w.clock()), items=n_items, sender=dict(key="rahim", msisdn=rahim["msisdn"], wallet=rahim["wallet"]),
        groups=groups,
        note_en="Each answer was recorded on a freshly staged demo (clock 09:30). Tap ↺ reset demo to get back to it: a transfer "
                "you send changes the next answer (the second transfer to a number is no longer the first).",
        note_bn="প্রতিটি উত্তর নতুন করে সাজানো ডেমোতে (ঘড়ি ০৯:৩০) রেকর্ড করা। আবার সেই অবস্থায় যেতে ↺ ডেমো রিসেট চাপুন: "
                "আপনি যে লেনদেন পাঠান, তা পরের উত্তর বদলে দেয় (একই নম্বরে দ্বিতীয়বার আর প্রথমবার নয়)।",
    )


def write(kit: dict, portable_dir: Path) -> None:
    (portable_dir / "test_kit.json").write_text(json.dumps(kit, ensure_ascii=False), encoding="utf-8")
    rows = [dict(group=g["title_en"], what=it["label_en"], kind=it["kind"], sender=it["persona"], number=it["number"],
                 amount=it["amount"], expected=it["expected"], role=it.get("role") or "", source=it["source"],
                 why=it.get("why_en") or "") for g in kit["groups"] for it in g["items"]]
    with open(ROOT / "data" / "sample" / "test_numbers.csv", "w", newline="", encoding="utf-8") as f:
        wr = csv.DictWriter(f, fieldnames=list(rows[0]))
        wr.writeheader()
        wr.writerows(rows)
    md = ["# Test numbers (from the synthetic dataset)", "",
          "Generated by `python -m src.serve.testkit` from the 683,148-row synthetic dataset. The same list is in the app: "
          "phone → Send Money → **🧪 Test numbers**, and on the showcase header. Sender: Rahim "
          f"({kit['sender']['msisdn']}) unless the row says Salma. *Expected* is what Prohori answered on a freshly staged "
          "demo; press ↺ reset demo to return to it. Fraud roles come from the synthetic ground truth (the model never sees them).", ""]
    for g in kit["groups"]:
        md += [f"## {g['title_en']}", "", "| What | Number | Amount | Expected | Why (first reason) |", "|---|---|---|---|---|"]
        for it in g["items"]:
            num = " → ".join(it["steps"]) if it.get("steps") else it["number"]
            why = (it.get("why_en") or "").replace("|", "/")
            md.append(f"| {it['label_en']}{' (recharge)' if it['kind'] == 'recharge' else ''} | `{num}` | Tk {it['amount']:,.0f} | "
                      f"**{it['expected']}** | {why[:160]} |")
        md.append("")
    (ROOT / "docs" / "test_numbers.md").write_text("\n".join(md), encoding="utf-8")


def main():
    from .live import LiveWorld
    w = LiveWorld(ROOT / "artifacts")
    kit = build(w, resolve(load_config(), "data_dir"))
    write(kit, ROOT / "artifacts" / "portable")
    print(f"[test kit] {kit['items']} items in {len(kit['groups'])} groups -> artifacts/portable/test_kit.json, "
          "data/sample/test_numbers.csv, docs/test_numbers.md")
    for g in kit["groups"]:
        for it in g["items"]:
            print(f"  {it['expected']:<10} {it['number']}  Tk {it['amount']:>7,.0f}  {it['label_en']}")


if __name__ == "__main__":
    main()
