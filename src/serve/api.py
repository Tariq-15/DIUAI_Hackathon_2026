"""Prohori API: the risk score, the customer warning flow and the analyst copilot, plus the web UI.

    uvicorn src.serve.api:app --port 8000          # open http://localhost:8000

Stable contract for an MFS pipeline: POST /api/v1/risk-score. Models score, plain rules pick how strongly
to warn, the customer decides (cancel or send after every warning; no transfer is held for an analyst).
The original inference-only routes (/v1/score, /v1/demo, /v1/agents/top, /v1/metrics) are kept.
"""
from __future__ import annotations

import mimetypes
import os
from contextlib import asynccontextmanager
from functools import lru_cache
from typing import Literal, Optional

import anyio
from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from src.common.config import ROOT
from . import scamcheck
from .live import LiveWorld

@asynccontextmanager
async def lifespan(_app):
    """Build the live world once at start-up, on the main thread, before taking traffic. Building it lazily inside a
    request thread costs a few hundred MB more on Linux (per-thread malloc arenas). A small worker pool keeps that
    bounded too. PROHORI_PRELOAD=0 skips the preload (tests)."""
    anyio.to_thread.current_default_thread_limiter().total_tokens = int(os.environ.get("PROHORI_THREADS", "4"))
    if os.environ.get("PROHORI_PRELOAD", "1") != "0":
        world()
    yield


app = FastAPI(title="Prohori API", version="2.0", lifespan=lifespan,
              description="upay scam shield prototype on synthetic data. Scores a transfer before money leaves the "
                          "wallet, warns in Bangla, and gives risk analysts an evidence-grounded copilot.")


@lru_cache(maxsize=1)
def world() -> LiveWorld:
    return LiveWorld(os.environ.get("PROHORI_ARTIFACTS"))


def _call(fn, *a, **k):
    try:
        return fn(*a, **k)
    except (KeyError, LookupError) as err:
        raise HTTPException(404, str(err).strip("'")) from err
    except PermissionError as err:
        raise HTTPException(403, str(err)) from err
    except ValueError as err:
        raise HTTPException(422, str(err)) from err


# ---------------------------------------------------------------- health + original routes
class Txn(BaseModel):
    sender_id: str = Field(..., description="wallet id (W...) or msisdn (010...)")
    receiver_id: str = Field(..., description="wallet / agent (A...) / merchant (M...) id, or msisdn")
    amount: float = Field(..., gt=0)
    txn_type: Literal["SEND_MONEY", "CASH_OUT", "PAYMENT", "ADD_MONEY"] = "SEND_MONEY"
    device_id: Optional[str] = Field(None, description="omit = the sender's usual phone")
    channel: Literal["APP", "USSD"] = "APP"
    area_id: Optional[str] = None
    ts_sec: Optional[int] = Field(None, description="seconds since simulation start; omit = now")
    commit: bool = Field(False, description="true = also update the feature store (the customer confirmed)")


@app.get("/health")
def health():
    w = world()
    e = w.engine
    return {"status": "ok", "wallets_in_state": len(e.store.w), "model_trees": int(e.bundle["lgbm"].best_iteration_ or 0),
            "clock": w.iso(w.clock()), "alerts": len(w.alerts), "llm": os.environ.get("PROHORI_LLM", "offline"),
            "scorer": "federated" if os.environ.get("PROHORI_SCORER") == "federated" else "central"}


@app.post("/v1/score")
def score(txn: Txn):
    w = world()
    with w.lock:
        return _call(w.engine.score, txn.model_dump(), commit=txn.commit)


@app.get("/v1/demo")
def demo():
    """Planted test-window scenarios (SC = scams, SB = benign look-alikes) with their recorded outcome."""
    return world().engine.state["demo"]


@app.get("/v1/demo/{sid}")
def demo_one(sid: str):
    for d in world().engine.state["demo"]:
        if d["id"].lower() == sid.lower():
            return d
    raise HTTPException(404, f"no scenario {sid}")


@app.get("/v1/agents/top")
def agents_top():
    aw = world().engine.state["agent_watch"]
    return {"sc06": aw.get("sc06"), "top_agents_last_day": aw.get("top_agents_last_day"), "by_split": aw.get("by_split")}


@app.get("/v1/metrics")
def metrics():
    return world().engine.state["metrics"]


# ---------------------------------------------------------------- Layer 1: customer
class RiskIn(BaseModel):
    customer: Optional[str] = Field(None, description="demo customer key (rahim, salma); or give sender_id")
    sender_id: Optional[str] = Field(None, description="wallet id or 010 number of the sender")
    to: str = Field(..., description="recipient wallet id or 010 number")
    amount: float = Field(..., gt=0, le=50000, description="KYC2 Send Money cap is Tk 50,000 per transfer (synthetic config)")
    device_id: Optional[str] = Field(None, description="omit = the sender's usual phone")


class DecisionIn(BaseModel):
    choice: Literal["cancel", "confirm", "confirm_pin", "use_suggested"]
    pin: Optional[str] = Field(None, description="demo PIN for a STEP_UP or HOLD confirmation (any 4 digits)")


@app.get("/api/v1/customers")
def customers():
    return world().customers()


@app.post("/api/v1/risk-score")
def risk_score(body: RiskIn):
    """Score a Send Money before it executes. ALLOW goes through; NUDGE/STEP_UP/HOLD return the Bangla warning and
    the customer answers it with /alerts/{id}/decision (HOLD is the strongest warning, not a hold)."""
    w = world()
    if body.customer:
        return _call(w.score, body.customer, body.to, body.amount, body.device_id)
    if not body.sender_id:
        raise HTTPException(422, "give customer or sender_id")
    return _call(w.score_raw, body.sender_id, body.to, body.amount, body.device_id)


@app.post("/api/v1/alerts/{alert_id}/decision")
def decision(alert_id: str, body: DecisionIn):
    return _call(world().decide, alert_id, body.choice, body.pin)


@app.get("/api/v1/transfers/{alert_id}")
def transfer_status(alert_id: str):
    """The customer's view of a warned transfer (status only, no case file)."""
    return _call(world().transfer_status, alert_id)


class RecipientIn(BaseModel):
    customer: str
    to: str = Field(..., min_length=3, max_length=20)


@app.post("/api/v1/recipient-check")
def recipient_check(body: RecipientIn):
    """As the customer types a number: does a wallet use it, and is it one keypad slip from someone they pay often?"""
    return _call(world().recipient_lookup, body.customer, body.to)


@app.get("/api/v1/customers/{key}/transfers")
def customer_transfers(key: str):
    return _call(world().transfers, key)


class RechargeIn(BaseModel):
    customer: str
    number: str = Field(..., min_length=11, max_length=20, description="the mobile number to recharge (01...)")
    amount: float = Field(..., gt=0, le=1000, description="Tk 10 to 1,000 (synthetic limit)")


@app.post("/api/v1/recharge")
def recharge(body: RechargeIn):
    """Mobile recharge: the customer's own recharge habit (federated thresholds) + a rapid-recharge rule. ALLOW goes
    through; NUDGE asks once (answer with /alerts/{id}/decision, like a transfer warning)."""
    return _call(world().recharge, body.customer, body.number, body.amount)


@app.get("/api/v1/customers/{key}/recharges")
def customer_recharges(key: str):
    return _call(world().recharges_of, key)


@app.get("/api/v1/test-kit")
def test_kit():
    """Numbers from the dataset to try on the phone, each with what Prohori answered on a fresh demo."""
    return _call(world().test_kit)


class PreviewIn(BaseModel):
    text: str = Field(..., max_length=2000)


@app.post("/api/v1/complaints/preview")
def complaint_preview(body: PreviewIn):
    """What the rules read from the customer's words (Bangla, Banglish, English), shown back before they submit."""
    return world().preview_complaint(body.text)


class ComplaintIn(BaseModel):
    customer: str
    text: str = Field(..., min_length=3, max_length=2000)
    problem: Literal["wrong_number", "scam", "other"] = "wrong_number"
    transfer_id: Optional[str] = None
    consent: bool = Field(False, description="the customer read the notice: purpose, retention, who sees it, withdrawal")


@app.post("/api/v1/complaints")
def complaint(body: ComplaintIn):
    return _call(world().file_complaint, body.customer, body.text, body.problem, body.transfer_id, body.consent)


@app.get("/api/v1/complaints/{cid}")
def complaint_status(cid: str):
    return _call(world().complaint_status, cid)


class ScamIn(BaseModel):
    text: str = Field(..., min_length=3, max_length=2000)


@app.post("/api/v1/scam-check")
def scam_check(body: ScamIn):
    """'Am I talking to a scammer?' Rule-based cue check; the text is not stored or sent anywhere."""
    return scamcheck.check(body.text)


# ---------------------------------------------------------------- Layer 3: analyst copilot
class ActionIn(BaseModel):
    action: str
    analyst: str = Field(..., min_length=1, max_length=60)
    note: str = Field("", max_length=500)


@app.get("/api/v1/alerts")
def alerts(all: bool = False):
    return world().list_alerts(include_allowed=all)


@app.get("/api/v1/alerts/{alert_id}")
def alert(alert_id: str, llm: bool = False):
    return _call(world().alert_detail, alert_id, use_llm=llm)


@app.post("/api/v1/alerts/{alert_id}/action")
def action(alert_id: str, body: ActionIn):
    return _call(world().act, alert_id, body.action, body.analyst, body.note)


@app.get("/api/v1/agent-watch")
def agent_watch():
    return world().agent_watch()


@app.get("/api/v1/model")
def model_card():
    return world().model_card()


@app.get("/api/v1/audit")
def audit():
    w = world()
    return {"verify": w.verify_audit(), "entries": w.audit[-200:]}


@app.post("/api/v1/demo/reset")
def reset():
    w = world()
    w.reset()
    return {"status": "reset", "clock": w.iso(w.clock())}


# ---------------------------------------------------------------- web UI (customer app, analyst copilot, showcase)
UI = ROOT / "ui"
mimetypes.add_type("font/woff2", ".woff2")      # bundled Noto Sans Bengali


@app.middleware("http")
async def revalidate_ui(request, call_next):
    """The pages, scripts and styles change with every deploy: the browser keeps them but asks first (ETag), so a new
    version is never hidden behind a stale cache. Fonts never change and are cached for a week."""
    res = await call_next(request)
    if request.url.path.startswith("/ui"):
        res.headers["Cache-Control"] = "public, max-age=604800" if request.url.path.endswith(".woff2") else "no-cache"
    return res


if UI.exists():
    @app.get("/", include_in_schema=False)
    def root():
        return RedirectResponse("/ui/")

    app.mount("/ui", StaticFiles(directory=UI, html=True), name="ui")
