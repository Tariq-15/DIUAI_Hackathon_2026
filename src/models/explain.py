"""SHAP explanations -> evidence-grounded reason codes in English and Bangla.

Every sentence quotes a real feature value (account age, sender count, minutes since the
inflow ...), never a generic "this could be fraud". The model decides nothing here: SHAP
picks WHICH evidence to show, the templates turn values into words.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

BN = str.maketrans("0123456789", "০১২৩৪৫৬৭৮৯")


def bn(x) -> str:
    return str(x).translate(BN)


def _i(v):
    return int(round(float(v))) if v == v else 0


def _f(v, nd=1):
    return round(float(v), nd) if v == v else 0.0


def _hm(h):
    return f"{int(h):02d}:00"


def _money(r):
    return f"{_i(r['amount']):,}"


def _dev_hours(r):
    return min(_nz(r.get("device_age_hours")), _nz(r.get("hrs_since_dev_change")))


# reason key -> (features that trigger it, condition(row), english(row), bangla(row))
REASONS = {
    "new_recipient": (["cp_age_days"], lambda r: r.get("cp_age_days", 9e9) < 60,
                      lambda r: f"Recipient wallet was opened only {max(_i(r['cp_age_days']), 0)} day(s) ago",
                      lambda r: f"এই নম্বরটি মাত্র {bn(max(_i(r['cp_age_days']), 0))} দিন আগে খোলা হয়েছে"),
    "many_senders": (["cp_in_new_24h", "cp_in_uniq_24h", "cp_in_cnt_1h", "g_cp_in_deg", "g_cp_two_hop_in", "g_cp_pagerank"],
                     lambda r: r.get("cp_in_uniq_24h", 0) >= 3,
                     lambda r: f"{_i(r['cp_in_uniq_24h'])} different people sent money to this number in the last 24 hours",
                     lambda r: f"গত ২৪ ঘণ্টায় {bn(_i(r['cp_in_uniq_24h']))} জন ভিন্ন মানুষ এই নম্বরে টাকা পাঠিয়েছেন"),
    "first_time_pair": (["pair_first", "pair_n_prior", "pair_reverse"], lambda r: r.get("pair_first", 0) == 1 and r.get("cp_kind", 0) == 0,
                        lambda r: "You have never sent money to this number before",
                        lambda r: "এই নম্বরে আপনি আগে কখনো টাকা পাঠাননি"),
    "new_device": (["is_new_device", "device_age_hours", "hrs_since_dev_change"],
                   lambda r: _dev_hours(r) < 72,
                   lambda r: f"A phone first seen on this account {_f(_dev_hours(r))} hour(s) ago is being used",
                   lambda r: f"এই অ্যাকাউন্টে মাত্র {bn(_f(_dev_hours(r)))} ঘণ্টা আগে নতুন ফোন থেকে লগইন হয়েছে"),
    "sim_swap": (["hrs_since_sim_swap"], lambda r: r.get("hrs_since_sim_swap", 9e9) < 72,
                 lambda r: f"The SIM was replaced {_f(r['hrs_since_sim_swap'])} hour(s) ago",
                 lambda r: f"{bn(_f(r['hrs_since_sim_swap']))} ঘণ্টা আগে সিম পরিবর্তন করা হয়েছে"),
    "pin_reset": (["hrs_since_pin_reset"], lambda r: r.get("hrs_since_pin_reset", 9e9) < 72,
                  lambda r: f"The PIN was reset {_f(r['hrs_since_pin_reset'])} hour(s) ago",
                  lambda r: f"{bn(_f(r['hrs_since_pin_reset']))} ঘণ্টা আগে পিন রিসেট করা হয়েছে"),
    "drain": (["drain_ratio", "cust_bal_log"], lambda r: r.get("drain_ratio", 0) >= 0.5,
              lambda r: f"This moves {min(_i(100 * r['drain_ratio']), 100)}% of the balance",
              lambda r: f"আপনার ব্যালেন্সের {bn(min(_i(100 * r['drain_ratio']), 100))}% পাঠানো হচ্ছে"),
    "unusual_amount": (["amount", "log_amount", "amount_z", "amount_vs_max", "is_round_1000", "is_round_100"],
                       lambda r: r.get("amount_z", 0) > 1.5 or r.get("amount_vs_max", 0) > 1.5,
                       lambda r: f"Tk {_i(r['amount']):,} is {_f(max(_nz(r.get('amount_vs_max'), 1), 1))}x the largest amount this customer has sent",
                       lambda r: f"৳{bn(_money(r))} আপনার আগের সর্বোচ্চ লেনদেনের {bn(_f(max(_nz(r.get('amount_vs_max'), 1), 1)))} গুণ"),
    "odd_hour": (["hour", "is_night", "hour_surprise"], lambda r: r.get("hour_surprise", 0) > 2.6 or r.get("is_night", 0) == 1,
                 lambda r: f"Unusual time for this customer ({_hm(r['hour'])})",
                 lambda r: f"আপনার জন্য অস্বাভাবিক সময় ({bn(_hm(r['hour']))})"),
    "pass_through": (["passthrough_ratio", "mins_since_last_in", "cust_in_amt_2h"],
                     lambda r: r.get("passthrough_ratio", 0) >= 0.5 and r.get("mins_since_last_in", 9e9) < 120,
                     lambda r: f"Money that arrived {_i(r['mins_since_last_in'])} minute(s) ago is being moved straight on",
                     lambda r: f"{bn(_i(r['mins_since_last_in']))} মিনিট আগে আসা টাকা সাথে সাথে অন্যত্র সরানো হচ্ছে"),
    "chain": (["chain_depth", "g_cust_ff_comp", "g_cp_ff_comp"],
              lambda r: r.get("chain_depth", 0) >= 2 or max(r.get("g_cp_ff_comp", 0), r.get("g_cust_ff_comp", 0)) >= 4,
              lambda r: _chain_en(r), lambda r: _chain_bn(r)),
    "collector_cashout": (["cust_in_new_24h", "cust_in_uniq_24h"], lambda r: r.get("cust_in_new_24h", 0) >= 5,
                          lambda r: f"This wallet was paid by {_i(r['cust_in_new_24h'])} first-time senders in the last 24 hours",
                          lambda r: f"গত ২৪ ঘণ্টায় এই ওয়ালেটে {bn(_i(r['cust_in_new_24h']))} জন নতুন প্রেরক টাকা পাঠিয়েছেন"),
    "reported": (["cp_complaints", "g_cp_nbr_complained", "cust_complaints", "g_cust_nbr_complained"],
                 lambda r: r.get("cp_complaints", 0) >= 1 or r.get("g_cp_nbr_complained", 0) >= 1,
                 lambda r: "Other customers have reported this number (or wallets it trades with) to 16268",
                 lambda r: "অন্য গ্রাহকরা এই নম্বর বা এর সাথে লেনদেনকারী ওয়ালেটের বিরুদ্ধে ১৬২৬৮-এ অভিযোগ করেছেন"),
    "shared_device": (["device_n_wallets", "cp_device_n_wallets"],
                      lambda r: max(_nz(r.get("device_n_wallets"), 0), _nz(r.get("cp_device_n_wallets"), 0)) >= 3,
                      lambda r: f"The phone involved is used by {max(_i(_nz(r.get('device_n_wallets'), 0)), _i(_nz(r.get('cp_device_n_wallets'), 0)))} different wallets",
                      lambda r: f"সংশ্লিষ্ট ফোনটি {bn(max(_i(_nz(r.get('device_n_wallets'), 0)), _i(_nz(r.get('cp_device_n_wallets'), 0))))}টি ভিন্ন ওয়ালেটে ব্যবহার হচ্ছে"),
    "channel_switch": (["channel_switch", "channel"], lambda r: r.get("channel_switch", 0) == 1,
                       lambda r: "A different channel from the customer's usual one (e.g. USSD user now on the app)",
                       lambda r: "সাধারণ মাধ্যমের বদলে ভিন্ন মাধ্যম ব্যবহার (যেমন USSD ব্যবহারকারী হঠাৎ অ্যাপে)"),
    "dormant_wake": (["cust_woke_gap_days", "cp_woke_gap_days", "hours_since_last"],
                     lambda r: max(r.get("cust_woke_gap_days", 0), r.get("cp_woke_gap_days", 0)) >= 14,
                     lambda r: f"A wallet silent for {_i(max(r.get('cust_woke_gap_days', 0), r.get('cp_woke_gap_days', 0)))} days suddenly became active",
                     lambda r: f"{bn(_i(max(r.get('cust_woke_gap_days', 0), r.get('cp_woke_gap_days', 0))))} দিন নিষ্ক্রিয় থাকা ওয়ালেট হঠাৎ সক্রিয়"),
    "agent_spike": (["ag_co_cnt_24h", "ag_co_amt_24h", "ag_co_ratio_7d", "ag_co_new_wallet_share_24h", "ag_night_co_24h"],
                    lambda r: r.get("ag_co_ratio_7d", 0) >= 3,
                    lambda r: f"This agent's cash-outs today are {_f(r['ag_co_ratio_7d'])}x its weekly normal",
                    lambda r: f"এই এজেন্টের আজকের ক্যাশ-আউট তার সাপ্তাহিক গড়ের {bn(_f(r['ag_co_ratio_7d']))} গুণ"),
    "velocity": (["cust_out_cnt_1h", "cust_uniq_cp_1h", "cust_new_cp_24h", "cust_out_cnt_24h", "cust_out_amt_24h"],
                 lambda r: r.get("cust_out_cnt_1h", 0) >= 3 or r.get("cust_new_cp_24h", 0) >= 3,
                 lambda r: f"{_i(r['cust_out_cnt_1h'])} transfers in the last hour, {_i(r['cust_new_cp_24h'])} to new recipients today",
                 lambda r: f"গত ১ ঘণ্টায় {bn(_i(r['cust_out_cnt_1h']))}টি লেনদেন, আজ {bn(_i(r['cust_new_cp_24h']))}টি নতুন নম্বরে"),
    "new_sender_wallet": (["cust_age_days", "cust_n_prior_out"], lambda r: r.get("cust_age_days", 9e9) < 30,
                          lambda r: f"The sending wallet itself is only {max(_i(r['cust_age_days']), 0)} day(s) old",
                          lambda r: f"প্রেরক ওয়ালেটটি মাত্র {bn(max(_i(r['cust_age_days']), 0))} দিন পুরনো"),
}
FEATURE_TO_REASON = {f: k for k, (fs, *_rest) in REASONS.items() for f in fs}


def _nz(v, default=9e9):
    return default if v is None or (isinstance(v, float) and math.isnan(v)) else v


def explainer(bundle):
    import warnings
    import shap
    warnings.filterwarnings("ignore", message=".*TreeExplainer shap values output has changed.*")
    return shap.TreeExplainer(bundle["lgbm"].booster_)


def shap_matrix(expl, X: pd.DataFrame) -> np.ndarray:
    sv = expl.shap_values(X)
    if isinstance(sv, list):
        sv = sv[1]
    sv = np.asarray(sv)
    if sv.ndim == 3:
        sv = sv[:, :, 1]
    return sv


def reasons_for(row: dict, shap_row: dict, extra: dict | None = None, k=3) -> list[dict]:
    """Top-k evidence sentences: positive SHAP contributions whose template condition holds."""
    out, seen = [], set()
    for f, v in sorted(shap_row.items(), key=lambda kv: -kv[1]):
        if v <= 0:
            break
        key = FEATURE_TO_REASON.get(f)
        if key is None or key in seen:
            continue
        _, cond, en, bnf = REASONS[key]
        try:
            if not cond(row):
                continue
            out.append(dict(code=key, feature=f, shap=round(float(v), 4), en=en(row), bn=bnf(row)))
        except (KeyError, TypeError, ValueError):
            continue
        seen.add(key)
        if len(out) >= k:
            break
    if extra:                                            # graph / anomaly evidence when they lift the score
        if extra.get("graph", 0) >= 0.5 and "chain" not in seen and len(out) < k + 1:
            out.append(dict(code="network_pattern", feature="graph_score", shap=None,
                            en="Part of a suspicious money-movement network (graph rules)",
                            bn="সন্দেহজনক টাকা লেনদেন নেটওয়ার্কের অংশ"))
        if extra.get("anomaly", 0) >= 0.98 and len(out) < k + 1:
            out.append(dict(code="behaviour_anomaly", feature="anomaly", shap=None,
                            en="Very unusual for this customer's own past behaviour (top 2% anomaly)",
                            bn="এই গ্রাহকের নিজের আগের আচরণের তুলনায় অত্যন্ত অস্বাভাবিক"))
    return out


def customer_message(band: str, reasons: list[dict]) -> dict:
    """What the sender sees on the Send Money screen. Never accuses the recipient by name."""
    top = [r for r in reasons if r["code"] not in ("agent_spike",)][:2]
    en_r = ". ".join(r["en"] for r in top)
    bn_r = "। ".join(r["bn"] for r in top)
    if band == "NUDGE":
        return dict(en=f"Caution: {en_r}. Do you personally know this person?",
                    bn=f"সতর্কতা: {bn_r}। আপনি কি এই ব্যক্তিকে ব্যক্তিগতভাবে চেনেন?")
    if band == "STEP_UP":
        return dict(en=f"Please confirm with your PIN. {en_r}. upay never asks for your PIN or OTP on a call.",
                    bn=f"নিশ্চিত করতে আবার পিন দিন। {bn_r}। upay কখনো ফোনে পিন বা ওটিপি চায় না।")
    if band == "HOLD":                                   # the strongest warning; the customer still decides
        return dict(en=f"Strong warning: this transfer shows signs of a scam. {en_r}. Sending is your decision; if "
                       "someone is rushing you, cancel and call 16268.",
                    bn=f"জোরালো সতর্কতা: এই লেনদেনে প্রতারণার লক্ষণ আছে। {bn_r}। পাঠাবেন কি না, সিদ্ধান্ত আপনার; কেউ তাড়া "
                       "দিলে বাতিল করুন এবং ১৬২৬৮ নম্বরে কল করুন।")
    return dict(en="", bn="")


def _ring(r):
    return max(_i(_nz(r.get("g_cp_ff_comp"), 0)), _i(_nz(r.get("g_cust_ff_comp"), 0)))


def _chain_en(r):
    """Say what actually fired: a multi-hop chain, or membership of a fast money-movement ring."""
    if r.get("chain_depth", 0) >= 2:
        return f"Money has hopped through {_i(r['chain_depth'])} wallets within 2 hours (mule-chain pattern)"
    return f"Part of a fast money-movement ring of {_ring(r)} wallets (money moved on within 2 hours)"


def _chain_bn(r):
    if r.get("chain_depth", 0) >= 2:
        return f"২ ঘণ্টার মধ্যে টাকা {bn(_i(r['chain_depth']))}টি ওয়ালেট ঘুরে এসেছে"
    return f"{bn(_ring(r))}টি ওয়ালেটের একটি দ্রুত টাকা-সরানো চক্রের অংশ (২ ঘণ্টার মধ্যে টাকা সরানো হয়েছে)"
