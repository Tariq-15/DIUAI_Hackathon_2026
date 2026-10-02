"""Ferot HTTP API (FastAPI). OpenAPI docs at /docs.

Customer-facing routes return only what a customer may see. Staff routes check the caller's role.
The built web app (web/dist) is served from the same process, so one URL serves everything.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from ferot import __version__, config
from ferot.api.security import Caller, require, staff
from ferot.llm.provider import get_provider
from ferot.models.extract import extract
from ferot.service import get_service
from ferot.store import audit

app = FastAPI(title="Ferot API", version=__version__,
              description="AI wrong-send and dispute copilot (prototype, synthetic data only, not an upay product).")
app.add_middleware(CORSMiddleware, allow_origins=config.settings().cors_origins, allow_methods=["*"],
                   allow_headers=["*"])
API = "/api/v1"
CHANNELS = {"app", "call", "sms", "email"}  # MFS Regulations §17.3: phone, SMS, IVR and mail


class Consent(BaseModel):
    accepted: bool = Field(description="The customer confirmed the notice: purpose, retention, who sees it, how to withdraw (R8)")
    version: str = "2026-10-01"
    language: str = "bn"


class ComplaintIn(BaseModel):
    claimant: str = Field(pattern=r"^01\d{9}$", description="The complaining customer's wallet number")
    text: str = Field(min_length=3, max_length=4000)
    channel: str = "app"
    problem: str = Field(default="wrong_number", pattern=r"^(wrong_number|scam|failed|agent)$")
    trx_id: str | None = Field(default=None, description="Transaction the customer picked in the app, if any")
    consent: Consent
    as_of_minute: int | None = Field(default=None, description="Demo clock (minutes since the synthetic start)")


class PreviewIn(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


class GuardIn(BaseModel):
    sender: str = Field(pattern=r"^01\d{9}$")
    recipient: str = Field(pattern=r"^01\d{9}$")
    amount: float = Field(gt=0, le=25000, description="upay's Send Money limit is Tk 25,000 per transfer")
    as_of_minute: int | None = None


class GuardDecisionIn(BaseModel):
    decision: str = Field(pattern=r"^(cancelled|sent_anyway|changed_number)$")


class DecisionIn(BaseModel):
    decision: str = Field(pattern=r"^(approve|edit|override)$")
    reason: str = ""
    edited_drafts: dict | None = None


class ContestIn(BaseModel):
    reason: str = Field(min_length=3, max_length=1000)


class ExportIn(BaseModel):
    request_ref: str = Field(min_length=3, description="Reference of the verified request, e.g. a police GD number")


def svc():
    return get_service()


def _case(case_id: str) -> dict:
    case = svc().store.get(case_id)
    if not case:
        raise HTTPException(404, f"case {case_id} not found")
    return case


@app.get(f"{API}/health")
def health():
    s = svc()
    return {"ok": True, "version": __version__, "model_version": s.version, "llm_provider": get_provider().name,
            "cases": s.store.count()}


# ---------- customer ----------
@app.post(f"{API}/complaints", status_code=201)
def create_complaint(body: ComplaintIn):
    if body.channel not in CHANNELS:
        raise HTTPException(422, f"channel must be one of {sorted(CHANNELS)}")
    if not body.consent.accepted:
        raise HTTPException(422, "the customer must confirm the notice before we process the complaint (R8)")
    s = svc()
    minute = body.as_of_minute if body.as_of_minute is not None else s.demo_now()
    case = s.intake(claimant=body.claimant, text=body.text, channel=body.channel, consent=body.consent.model_dump(),
                    complaint_minute=minute, trx_hint=body.trx_id, problem=body.problem)
    return {"case_id": case["case_id"], "status": s.customer_status(case["case_id"])}


@app.post(f"{API}/complaints/preview")
def complaint_preview(body: PreviewIn):
    """What the rules read from the customer's words, shown back before they submit. No model verdict, no LLM."""
    e = extract(body.text, use_llm=False)
    return {"amount": e.amount, "number": e.number, "day_offset": e.day_offset, "hour": e.hour, "trx_id": e.trx_id,
            "language": e.language}


@app.get(f"{API}/cases/{{case_id}}/status")
def case_status(case_id: str):
    try:
        return svc().customer_status(case_id)
    except KeyError:
        raise HTTPException(404, "case not found")


@app.post(f"{API}/cases/{{case_id}}/contest")
def contest(case_id: str, body: ContestIn):
    try:
        svc().contest(case_id, body.reason)
    except KeyError:
        raise HTTPException(404, "case not found")
    return svc().customer_status(case_id)


@app.post(f"{API}/guard/check")
def guard_check_endpoint(body: GuardIn):
    """Score a transfer before it is sent: allow, warn or review. The customer always decides."""
    s = svc()
    if not s.wallet_exists(body.recipient):
        raise HTTPException(404, f"no wallet uses {body.recipient} in the demo data")
    minute = body.as_of_minute if body.as_of_minute is not None else s.demo_now()
    return s.guard(body.sender, body.recipient, body.amount, minute)


@app.post(f"{API}/guard/{{check_id}}/decision")
def guard_decision(check_id: str, body: GuardDecisionIn):
    try:
        return svc().guard_decision(check_id, body.decision)
    except KeyError:
        raise HTTPException(404, "check not found")


@app.get(f"{API}/guard/alerts")
def guard_alerts(caller: Caller = Depends(staff)):
    """Warned and reviewed sends with the customer's choice. Numbers are masked (R9)."""
    return [{"check_id": c["check_id"], "created_at": c["created_at"], "sender_last4": c["sender"][-4:],
             "recipient_last4": c["recipient"][-4:], "amount": c["amount"], "risk": c["risk"], "band": c["band"],
             "reasons": [r["en"] for r in c["reasons"]], "decision": c.get("decision")}
            for c in svc().store.checks()]


@app.get(f"{API}/cases/{{case_id}}/network")
def case_network(case_id: str, caller: Caller = Depends(staff)):
    try:
        return svc().network(case_id)
    except KeyError:
        raise HTTPException(404, "case not found")


@app.get(f"{API}/demo/customers")
def demo_customers():
    return svc().demo_customers()


# ---------- staff ----------
@app.get(f"{API}/queue")
def queue(caller: Caller = Depends(staff)):
    return svc().queue()


@app.get(f"{API}/cases/{{case_id}}")
def get_case(case_id: str, caller: Caller = Depends(staff)):
    case = _case(case_id)
    case["audit"] = audit.entries(svc().store.conn, case_id)
    return case


@app.post(f"{API}/cases/{{case_id}}/decision")
def decide(case_id: str, body: DecisionIn, caller: Caller = Depends(staff)):
    require(caller, "agent", "supervisor")
    try:
        return svc().decide(case_id, caller.actor, caller.role, body.decision, body.reason, body.edited_drafts)
    except KeyError:
        raise HTTPException(404, "case not found")
    except PermissionError as exc:
        raise HTTPException(403, str(exc))
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@app.post(f"{API}/cases/{{case_id}}/reveal")
def reveal(case_id: str, caller: Caller = Depends(staff)):
    require(caller, "agent", "supervisor", "compliance")
    try:
        return svc().reveal(case_id, caller.actor, caller.role)
    except KeyError:
        raise HTTPException(404, "case not found")


@app.post(f"{API}/cases/{{case_id}}/export")
def export(case_id: str, body: ExportIn, caller: Caller = Depends(staff)):
    try:
        return svc().export(case_id, caller.actor, caller.role, body.request_ref)
    except KeyError:
        raise HTTPException(404, "case not found")
    except PermissionError as exc:
        raise HTTPException(403, str(exc))


@app.get(f"{API}/insights/kpis")
def kpis(caller: Caller = Depends(staff)):
    return svc().kpis()


@app.get(f"{API}/insights/clusters")
def clusters(caller: Caller = Depends(staff)):
    require(caller, "analyst", "supervisor", "compliance")
    return svc().clusters()


@app.get(f"{API}/insights/aml-queue")
def aml_queue(caller: Caller = Depends(staff)):
    require(caller, "compliance", "supervisor")
    return svc().store.aml_queue()


@app.get(f"{API}/insights/dispute-report.csv", response_class=PlainTextResponse)
def dispute_report(caller: Caller = Depends(staff)):
    require(caller, "analyst", "supervisor", "compliance")
    return PlainTextResponse(svc().dispute_report_csv(), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=dispute-report.csv"})


@app.get(f"{API}/insights/metrics")
def metrics(caller: Caller = Depends(staff)):
    path = config.ROOT / "reports" / "metrics.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


@app.get(f"{API}/insights/simulation")
def simulation(caller: Caller = Depends(staff)):
    path = config.ROOT / "reports" / "simulation.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


@app.get(f"{API}/audit/verify")
def verify(caller: Caller = Depends(staff)):
    return audit.verify(svc().store.conn)


@app.post(f"{API}/demo/reset")
def reset(caller: Caller = Depends(staff)):
    require(caller, "supervisor")
    s = svc()
    s.store.reset()
    s.history.__init__(s.ledger.world.cases)
    n = s.seed_demo()
    return {"seeded": n}


# ---------- upay-style wallet app (static pages that call this API) ----------
UPAY_UI = config.ROOT / "upay frontend clone" / "upay_mobile_app_redesign"
if UPAY_UI.exists():
    @app.get("/upay", include_in_schema=False)
    def upay_root():
        return RedirectResponse("/upay/")

    app.mount("/upay", StaticFiles(directory=UPAY_UI, html=True), name="upay")

# ---------- web app ----------
WEB_DIST = config.ROOT / "web" / "dist"
if WEB_DIST.exists():
    app.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        root = WEB_DIST.resolve()
        target = (root / path).resolve()
        if path and root in target.parents and target.is_file():
            return FileResponse(target)
        return FileResponse(root / "index.html")
