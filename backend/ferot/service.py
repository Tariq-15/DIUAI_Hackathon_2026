"""Ferot service: complaint in, case file out. Also decisions, customer status, insights and demo seeding.

The pipeline: M1 extract -> M2 match -> evidence -> M3 intended number -> M4 classify (+ reasons)
-> M5 recoverability -> M6 priority -> policy engine -> M8 drafts. Nothing moves money; every
recommendation waits for a named human (R6) and every step is written to the audit log (R12).
"""

from __future__ import annotations

import csv
import io
from datetime import datetime, timedelta
from functools import lru_cache

from ferot import config
from ferot.features.evidence import CaseHistory, build_evidence
from ferot.features.ledger import Ledger, load_ledger
from ferot.models.classifier import CLASS_LABELS, CLASSES
from ferot.models.drafts import generate_drafts
from ferot.models.extract import Extraction, extract
from ferot.models.guard import check as guard_check
from ferot.models.matcher import match_transaction
from ferot.models.priority import priority_score
from ferot.models.train import load_models
from ferot.policy.engine import recommend
from ferot.policy.sla import sla_status
from ferot.store import audit
from ferot.store.db import CaseStore

ROLES = {"agent", "supervisor", "analyst", "compliance"}
STATUS_ON_APPROVE = {
    "hold_and_request_consent": "hold_requested", "hold_and_fraud_review": "hold_requested",
    "request_consent_only": "consent_requested", "check_auto_reversal": "with_tech_ops",
    "reject_and_flag_claimant": "rejected", "reject_with_explanation": "rejected",
    "route_distributor": "with_distributor", "request_more_info": "awaiting_customer",
}
CUSTOMER_STEPS = ["received", "under_review", "action_taken", "resolved"]


class FerotService:
    def __init__(self, ledger: Ledger | None = None, models: dict | None = None, store: CaseStore | None = None):
        s = config.settings()
        self.ledger = ledger or load_ledger()
        m = models or load_models()
        self.clf, self.rec, self.version = m["classifier"], m["recoverability"], m["version"]
        self.guard_model = m.get("guard")
        self.store = store or CaseStore(s.db_path)
        self.history = CaseHistory(self.ledger.world.cases)

    # ---------- time ----------
    def dt(self, minute: int) -> datetime:
        return (self.ledger.start + timedelta(minutes=int(minute))).to_pydatetime()

    def demo_now(self) -> int:
        return self.ledger.world.days * 1440 - 1

    # ---------- intake ----------
    def build_case(self, *, claimant: str, text: str, channel: str, consent: dict, complaint_minute: int,
                   trx_hint: str | None = None, problem: str = "wrong_number", case_id: str | None = None) -> dict:
        case_id = case_id or self.store.next_id()
        e: Extraction = extract(text)
        if trx_hint:
            e.trx_id = trx_hint
            e.sources["trx_id"] = "customer_selected"
        created = self.dt(complaint_minute)
        sla = sla_status(created, created)
        base = {"case_id": case_id, "created_at": created.isoformat(), "complaint_minute": int(complaint_minute),
                "claimant": claimant, "channel": channel, "complaint_text": text, "problem": problem,
                "consent": consent, "extraction": e.to_dict(), "sla": sla, "model_version": self.version,
                "status": "new", "status_history": [{"status": "new", "at": created.isoformat()}],
                "decision": None, "contest": None,
                "labels": {"facts": "Facts", "prediction": "Prediction", "generated": "Generated"}}

        match = match_transaction(self.ledger, claimant, e, complaint_minute)
        if problem == "agent":
            match = self._match_agent_cashout(claimant, e, complaint_minute)
        base["match"] = match
        if not match["trx_id"]:
            probs = {c: 0.0 for c in CLASSES}
            rec = recommend({**probs, "genuine_wrong_send": 0.01}, {"amount": e.amount or 0, "recoverable_now": 0})
            base.update({"facts": {"amount": e.amount or 0, "recipient": e.number or ""}, "trail": [],
                         "intended": {"found": False}, "prediction": None, "recoverability": {"now": 0, "curve": []},
                         "priority": priority_score([{"minutes": 0, "expected": 0.0}, {"minutes": 1440, "expected": 0.0}],
                                                    False, sla),
                         "recommendation": rec})
            base["drafts"] = generate_drafts(rec["drafts"], case_id, base["facts"], sla["deadline"],
                                             self._internal_note(base, rec, []))
            return base

        ev = build_evidence(self.ledger, claimant, match["trx_id"], complaint_minute, e, self.history)
        ev.facts["involves_agent"] = problem == "agent"
        ev.facts["transfer_minute"] = int(self.ledger.row(match["trx_id"])["minute"])
        probs, reasons = self.clf.explain(ev.features)
        top = max(probs, key=probs.get)
        curve = self.rec.curve(ev.features, ev.recoverable_now)
        vulnerable = top == "scam_victim" or bool(ev.features.get("claimant_ussd"))
        prio = priority_score(curve, vulnerable, sla)
        rec = recommend(probs, ev.facts)
        ev.facts["hold_amount"] = rec["hold_amount"]
        base.update({
            "facts": ev.facts, "trail": ev.trail, "intended": ev.intended,
            "prediction": {"probs": probs, "case_type": top, "label": CLASS_LABELS[top],
                           "confidence": probs[top], "reasons": reasons},
            "recoverability": {"now": ev.recoverable_now, "curve": curve},
            "priority": prio, "recommendation": rec,
        })
        base["drafts"] = generate_drafts(rec["drafts"], case_id, ev.facts, sla["deadline"],
                                         self._internal_note(base, rec, reasons))
        base["report"] = self._case_report(base)
        return base

    def _case_report(self, case: dict) -> dict:
        """What happened, why it is risky, what to do next, and the limits. Built only from the case file."""
        f, pred, rec = case["facts"], case.get("prediction"), case["recommendation"]

        def last4(n) -> str:
            return f"…{str(n)[-4:]}" if n else "an unknown number"

        sent = self.dt(int(f["transfer_minute"])) if "transfer_minute" in f else None
        delay = case["complaint_minute"] - int(f.get("transfer_minute", case["complaint_minute"]))
        hours, minutes = divmod(max(delay, 0), 60)
        waited = f"{hours} h {minutes} min" if hours else f"{minutes} min"
        channel = {"app": "in the app", "call": "by phone", "sms": "by SMS", "email": "by email"}.get(case["channel"], "")
        what = (f"Customer {last4(case['claimant'])} sent Tk {f['amount']:,.0f} to {last4(f.get('recipient'))}"
                + (f" at {sent:%H:%M on %d %b}" if sent else "")
                + f" and complained {waited} later {channel}.")
        why = []
        if pred:
            why.append(f"{pred['label']}, {pred['confidence'] * 100:.0f}% confidence.")
            why += [r.get("text") or f"{r['label'][0].upper() + r['label'][1:]}: {r['value']}." for r in pred["reasons"]]
        if f.get("other_complainants_on_recipient"):
            why.append(f"{f['other_complainants_on_recipient']} other customers have complained about the receiving wallet.")
        if f.get("return_flow"):
            why.append("The receiving wallet already sent the same amount back.")
        why.append(f"Tk {f.get('recoverable_now', 0):,.0f} is still in the receiving wallet; about "
                   f"Tk {case['priority']['lost_by_waiting']:,.0f} of it is likely to leave within a day.")
        who = {"agent": "an agent", "supervisor": "a supervisor", "compliance": "compliance"}.get(rec["approval"], rec["approval"])
        nxt = f"{rec['summary']} Needs approval from {who} (rule {rec['rule_id']})."
        if rec["hold_amount"]:
            nxt += f" Hold request: Tk {rec['hold_amount']:,.0f}, capped at what is left of the disputed amount."
        limits = ["Built on synthetic data; the models are not yet validated on upay's records."]
        if pred and pred["confidence"] < 0.8:
            limits.append("Confidence is below 80%, so check the evidence before approving.")
        if case["match"]["confidence"] < 0.6:
            limits.append("The transaction match is uncertain; confirm the TrxID with the customer.")
        if case["extraction"]["disagreements"]:
            limits.append("Rules and the language model disagree on: " + ", ".join(case["extraction"]["disagreements"]) + ".")
        limits.append("Ferot cannot see calls or SMS outside upay, so it cannot prove who contacted the customer.")
        return {"what_happened": what, "why_risky": why, "next_step": nxt, "limits": limits}

    def _match_agent_cashout(self, claimant: str, e: Extraction, minute: int) -> dict:
        idx = self.ledger.outgoing(claimant, minute - 7 * 1440, minute)
        idx = [i for i in idx if self.ledger.type[i] == "cash_out"]
        if not idx:
            return {"trx_id": None, "confidence": 0.0, "candidates": []}
        best = min(idx, key=lambda i: abs(self.ledger.amount[i] - (e.amount or self.ledger.amount[i])))
        return {"trx_id": str(self.ledger.tx.at[best, "trx_id"]), "confidence": 0.6, "candidates": []}

    def _internal_note(self, case: dict, rec: dict, reasons: list[dict]) -> str:
        why = "; ".join(f"{r['label']} ({r['value']})" for r in reasons) or "not enough information"
        pred = case.get("prediction")
        head = f"{pred['label']} ({pred['confidence'] * 100:.0f}%)" if pred else "No matching transaction"
        return (f"Case {case['case_id']}: {head}. Rule {rec['rule_id']}: {rec['summary']} "
                f"Hold request: Tk {rec['hold_amount']:,.0f}. Main evidence: {why}. "
                f"Approval needed from: {rec['approval']}. SLA deadline {case['sla']['deadline']} "
                f"(10 working days, MFS Regulations 2022 s17.3).")

    def intake(self, **kwargs) -> dict:
        if not kwargs.get("consent", {}).get("accepted"):
            raise ValueError("consent required (rule R8)")
        case = self.build_case(**kwargs)
        self.store.save(case)
        audit.append(self.store.conn, case["case_id"], "customer" if case["channel"] == "app" else "call-centre",
                     "intake", "case.created",
                     {"channel": case["channel"], "consent": case["consent"], "rule_id": case["recommendation"]["rule_id"]},
                     self.version)
        if case.get("facts", {}).get("recipient"):
            self.history.add(case["claimant"], case["facts"]["recipient"], case["complaint_minute"])
        return case

    # ---------- decisions ----------
    def decide(self, case_id: str, actor: str, role: str, decision: str, reason: str = "",
               edited_drafts: dict | None = None) -> dict:
        case = self.store.get(case_id)
        if not case:
            raise KeyError(case_id)
        if role not in ("agent", "supervisor"):
            raise PermissionError("only agents and supervisors decide cases")
        rec = case["recommendation"]
        if decision in ("approve", "edit") and rec["approval"] == "supervisor" and role != "supervisor":
            raise PermissionError("this recommendation needs a supervisor (rule R6)")
        if decision == "override" and not reason.strip():
            raise ValueError("an override needs a reason")
        if decision not in ("approve", "edit", "override"):
            raise ValueError("decision must be approve, edit or override")
        now = datetime.now().isoformat(timespec="seconds")
        status = STATUS_ON_APPROVE.get(rec["action"], "in_progress") if decision != "override" else "manual_review"
        case["status"] = status
        case["status_history"].append({"status": status, "at": now, "by": actor})
        case["decision"] = {"decision": decision, "actor": actor, "role": role, "reason": reason, "at": now,
                            "rule_id": rec["rule_id"], "hold_amount": rec["hold_amount"] if decision != "override" else 0}
        if edited_drafts:
            for draft_id, langs in edited_drafts.items():
                if draft_id in case["drafts"]:
                    case["drafts"][draft_id].update({k: v for k, v in langs.items() if k in ("en", "bn")})
                    case["drafts"][draft_id]["source"] = "edited_by_agent"
        if decision != "override" and rec.get("aml_flag"):
            wallet = case["facts"].get("recipient") if rec["aml_flag"] == "recipient" else case["claimant"]
            self.store.flag_aml(case_id, wallet, rec["aml_flag"], now)
        self.store.save(case)
        audit.append(self.store.conn, case_id, actor, role, f"case.{decision}",
                     {"rule_id": rec["rule_id"], "reason": reason, "hold_amount": case["decision"]["hold_amount"],
                      "status": status}, self.version)
        return case

    def contest(self, case_id: str, reason: str) -> dict:
        """The customer asks for a human-only review of the outcome (R6, PDPO 2025)."""
        case = self.store.get(case_id)
        if not case:
            raise KeyError(case_id)
        now = datetime.now().isoformat(timespec="seconds")
        case["contest"] = {"reason": reason, "at": now}
        case["status"] = "human_review"
        case["status_history"].append({"status": "human_review", "at": now, "by": "customer"})
        self.store.save(case)
        audit.append(self.store.conn, case_id, "customer", "customer", "case.contested", {"reason": reason}, self.version)
        return case

    def reveal(self, case_id: str, actor: str, role: str) -> dict:
        """Unmask phone numbers for one case; every reveal is logged (R9)."""
        case = self.store.get(case_id)
        if not case:
            raise KeyError(case_id)
        audit.append(self.store.conn, case_id, actor, role, "pii.reveal", {}, self.version)
        return {"claimant": case["claimant"], "recipient": case.get("facts", {}).get("recipient"),
                "intended": case.get("intended", {}).get("candidate")}

    def export(self, case_id: str, actor: str, role: str, request_ref: str) -> dict:
        """Evidence pack for a verified request (R13, MFS Regulations §18.2). Compliance role only."""
        if role != "compliance":
            raise PermissionError("exports are released only through compliance (rule R13)")
        if not request_ref.strip():
            raise ValueError("a verified request reference is required")
        case = self.store.get(case_id)
        if not case:
            raise KeyError(case_id)
        audit.append(self.store.conn, case_id, actor, role, "case.exported", {"request_ref": request_ref}, self.version)
        return {"case": case, "audit": audit.entries(self.store.conn, case_id), "request_ref": request_ref,
                "exported_at": datetime.now().isoformat(timespec="seconds")}

    # ---------- Ferot Guard (before the money leaves) ----------
    def guard(self, sender: str, recipient: str, amount: float, minute: int) -> dict:
        if not self.guard_model:
            raise RuntimeError("Guard model not trained; run python -m ferot.cli train")
        result = guard_check(self.guard_model, self.ledger, self.history, sender, recipient, amount, minute)
        check_id = f"GC-{self.store.count_checks() + 1:05d}"
        record = {"check_id": check_id, "created_at": self.dt(minute).isoformat(), "sender": sender,
                  "recipient": recipient, "amount": amount, "minute": minute, **result, "decision": None}
        self.store.save_check(record)
        if result["band"] != "allow":
            audit.append(self.store.conn, None, "ferot-guard", "system", f"guard.{result['band']}",
                         {"check_id": check_id, "risk": result["risk"],
                          "reasons": [r["key"] for r in result["reasons"]]}, self.version)
        return record

    def guard_decision(self, check_id: str, decision: str) -> dict:
        record = self.store.get_check(check_id)
        if not record:
            raise KeyError(check_id)
        record["decision"] = decision
        self.store.save_check(record)
        audit.append(self.store.conn, None, "customer", "customer", f"guard.{decision}", {"check_id": check_id},
                     self.version)
        return record

    def network(self, case_id: str) -> dict:
        """The receiving wallet's neighbourhood: who complained about it and where its money went."""
        case = self.store.get(case_id)
        if not case:
            raise KeyError(case_id)
        recipient = case.get("facts", {}).get("recipient")
        if not recipient:
            return {"center": None, "complainants": 0, "nodes": [], "edges": []}
        until = case["complaint_minute"]
        df = self.history.df
        hist = df[(df["recipient"] == recipient) & (df["complaint_minute"] <= until)]
        nodes = {recipient: {"id": recipient, "kind": "center"}}
        edges = []
        for claimant in sorted(set(hist["claimant"]) | {case["claimant"]}):
            kind = "this_customer" if claimant == case["claimant"] else "complainant"
            nodes[claimant] = {"id": claimant, "kind": kind}
            idx = self.ledger.outgoing(claimant, 0, until)
            sent = idx[self.ledger.receiver[idx] == recipient] if len(idx) else idx
            amt = float(self.ledger.amount[sent].sum()) if len(sent) else 0.0
            edges.append({"source": claimant, "target": recipient, "amount": round(amt, 2), "kind": "sent"})
        out = self.ledger.outgoing(recipient, until - 30 * 1440, until)
        flows: dict[tuple[str, str], float] = {}
        for i in out:
            t = str(self.ledger.type[i])
            if t in ("reversal",):
                continue
            key = (str(self.ledger.receiver[i]), t)
            flows[key] = flows.get(key, 0.0) + float(self.ledger.amount[i])
        for (to, t), amt in sorted(flows.items(), key=lambda kv: -kv[1])[:8]:
            if to in nodes:
                continue
            owner = self.ledger.owner_type(to)
            nodes[to] = {"id": to, "kind": owner if owner in ("agent", "merchant", "mno") else "wallet"}
            edges.append({"source": recipient, "target": to, "amount": round(amt, 2), "kind": t})
        return {"center": recipient, "complainants": int(len(set(hist["claimant"]) - {case["claimant"]})),
                "nodes": list(nodes.values()), "edges": edges}

    # ---------- customer view ----------
    def customer_status(self, case_id: str) -> dict:
        case = self.store.get(case_id)
        if not case:
            raise KeyError(case_id)
        status = case["status"]
        step = {"new": 1, "human_review": 1, "manual_review": 1}.get(status, 2)
        if status in ("rejected",):
            step = 3
        lim = config.limits()
        return {
            "case_id": case_id, "status": status, "step": step, "steps": CUSTOMER_STEPS,
            "deadline": case["sla"]["deadline"], "helpline": lim["helpline"],
            "message_en": (f"Your complaint {case_id} is being handled. We will update you by "
                           f"{case['sla']['deadline']}. A return depends on the recipient's consent or legal process."),
            "message_bn": (f"আপনার অভিযোগ {case_id} নিয়ে কাজ চলছে। {case['sla']['deadline']} তারিখের মধ্যে আপনাকে জানানো হবে। "
                           "অর্থ ফেরত পাওয়া প্রাপকের সম্মতি বা আইনি প্রক্রিয়ার উপর নির্ভর করে।"),
            "escalation": "If you are not satisfied, you can complain to Bangladesh Bank's Customers Interest "
                          "Protection Centre (FICSD hotline 16236).",
            "can_contest": status not in ("new", "human_review"),
        }

    # ---------- insights ----------
    def queue(self) -> list[dict]:
        out = []
        for c in self.store.all():
            pred = c.get("prediction") or {}
            out.append({
                "case_id": c["case_id"], "status": c["status"], "created_at": c["created_at"],
                "case_type": pred.get("case_type"), "label": pred.get("label", "Needs information"),
                "confidence": pred.get("confidence"), "amount": c.get("facts", {}).get("amount", 0),
                "recoverable_now": c.get("recoverability", {}).get("now", 0),
                "lost_by_waiting": c.get("priority", {}).get("lost_by_waiting", 0),
                "priority": c.get("priority", {}).get("score", 0), "sla": c["sla"], "channel": c["channel"],
                "language": c.get("extraction", {}).get("language"), "rule_id": c["recommendation"]["rule_id"],
                "approval": c["recommendation"]["approval"],
                "recipient_last4": str(c.get("facts", {}).get("recipient", ""))[-4:],
            })
        open_first = sorted(out, key=lambda r: (r["status"] not in ("new", "human_review"), -r["priority"]))
        return open_first

    def clusters(self) -> list[dict]:
        """M7: receiving wallets named by several complainants, linked through onward transfers."""
        now = self.demo_now()
        hist = self.history.df[self.history.df["complaint_minute"] <= now]
        counts = hist.groupby("recipient")["claimant"].nunique()
        parent: dict[str, str] = {}

        def find(x: str) -> str:
            parent.setdefault(x, x)
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        suspicious = set(counts[counts >= 3].index)
        for w in suspicious:
            find(w)
            for i in self.ledger.outgoing(w, 0, now):
                if self.ledger.type[i] == "send_money" and str(self.ledger.receiver[i]) in suspicious:
                    parent[find(w)] = find(str(self.ledger.receiver[i]))
        groups: dict[str, list[str]] = {}
        for w in suspicious:
            groups.setdefault(find(w), []).append(w)
        out = []
        for members in groups.values():
            complainants = int(hist[hist["recipient"].isin(members)]["claimant"].nunique())
            agents = set()
            for w in members:
                for i in self.ledger.outgoing(w, 0, now):
                    if self.ledger.type[i] == "cash_out":
                        agents.add(str(self.ledger.receiver[i]))
            out.append({"wallets": sorted(members), "complainants": complainants,
                        "cash_out_agents": len(agents),
                        "first_seen": self.dt(int(hist[hist["recipient"].isin(members)]["complaint_minute"].min())).isoformat()})
        return sorted(out, key=lambda c: -c["complainants"])[:25]

    def kpis(self) -> dict:
        cases = self.store.all()
        decided = [c for c in cases if c.get("decision")]
        overrides = [c for c in decided if c["decision"]["decision"] == "override"]
        by_type: dict[str, int] = {}
        for c in cases:
            t = (c.get("prediction") or {}).get("case_type", "needs_information")
            by_type[t] = by_type.get(t, 0) + 1
        return {
            "cases": len(cases), "open": sum(c["status"] in ("new", "human_review") for c in cases),
            "decided": len(decided), "override_rate": round(len(overrides) / len(decided), 3) if decided else 0.0,
            "recoverable_now_total": round(sum(c.get("recoverability", {}).get("now", 0) for c in cases), 2),
            "holds_requested_total": round(sum(c["decision"]["hold_amount"] for c in decided), 2),
            "by_type": by_type, "aml_queue": len(self.store.aml_queue()),
            "guard_alerts": len(self.store.checks()),
            "audit_chain": audit.verify(self.store.conn),
        }

    def dispute_report_csv(self) -> str:
        """Monthly dispute summary for Bangladesh Bank reporting (MFS Regulations 2022 §16.3)."""
        rows: dict[str, dict] = {}
        for c in self.store.all():
            month = c["created_at"][:7]
            r = rows.setdefault(month, {"month": month, "disputes": 0, "decided": 0, "sla_breached": 0,
                                        **{t: 0 for t in CLASSES}, "needs_information": 0})
            r["disputes"] += 1
            r["decided"] += 1 if c.get("decision") else 0
            r["sla_breached"] += 1 if c["sla"].get("breached") else 0
            r[(c.get("prediction") or {}).get("case_type", "needs_information")] += 1
        buf = io.StringIO()
        fields = ["month", "disputes", "decided", "sla_breached", *CLASSES, "needs_information"]
        w = csv.DictWriter(buf, fieldnames=fields)
        w.writeheader()
        for month in sorted(rows):
            w.writerow(rows[month])
        return buf.getvalue()

    # ---------- demo ----------
    def demo_customers(self) -> list[dict]:
        cases = self.ledger.world.cases
        out = []
        for name, label in (("rahim", "Rahim (shop owner, Rajshahi)"), ("shirin", "Shirin (retired teacher, Sylhet)")):
            c = cases[cases["golden"] == name]
            if c.empty:
                continue
            c = c.iloc[0]
            minute = int(c["complaint_minute"])
            idx = self.ledger.outgoing(c["claimant"], minute - 7 * 1440, minute)
            txs = [{"trx_id": str(self.ledger.tx.at[i, "trx_id"]), "type": str(self.ledger.type[i]),
                    "to": str(self.ledger.receiver[i]), "amount": float(self.ledger.amount[i]),
                    "ts": self.ledger.ts(int(self.ledger.minute[i]))}
                   for i in idx if self.ledger.type[i] in ("send_money", "payment", "cash_out")][-20:][::-1]
            send_at = int(c["transfer_minute"]) - 1
            scenarios = [{"key": "risky", "label": "The transfer that went wrong", "recipient": c["recipient"],
                          "amount": float(c["amount"]), "minute": send_at}]
            if name == "rahim":
                scenarios.insert(0, {"key": "usual", "label": "His usual transfer to his brother",
                                     "recipient": c["intended_number"], "amount": 2000.0, "minute": send_at})
            out.append({"key": name, "label": label, "wallet": c["claimant"], "language": c["text_language"],
                        "now_minute": minute, "now": self.dt(minute).isoformat(), "sample_text": c["complaint_text"],
                        "transactions": txs, "send_minute": send_at, "send_scenarios": scenarios})
        return out

    def seed_demo(self, n: int = 36) -> int:
        cases = self.ledger.world.cases
        pool = cases[(cases["split"] == "test") & (cases["golden"] == "")].sort_values("complaint_minute").tail(n)
        for _, c in pool.iterrows():
            self.intake(claimant=c["claimant"], text=c["complaint_text"], channel=c["channel"],
                        consent={"accepted": True, "version": "2026-10-01", "language": c["text_language"]},
                        complaint_minute=int(c["complaint_minute"]), case_id=c["case_id"])
        return len(pool)


@lru_cache
def get_service() -> FerotService:
    svc = FerotService()
    if svc.store.count() == 0:
        svc.seed_demo()
    return svc
