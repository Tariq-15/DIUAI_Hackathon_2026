"""The API without a server: the same routes as src/serve/api.py, answered inside the browser (Pyodide).

ui/pyworker.js loads Pyodide in a Web Worker, unpacks src/ and artifacts/portable/, builds a Dispatcher and calls
`handle(method, path, body_json)` for every request the UI makes. The answers have the same shape and the same
validation as the FastAPI routes, so the pages work unchanged in both modes.
"""
from __future__ import annotations

import json
import math
import re
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import numpy as np

from . import scamcheck
from .live import LiveWorld
from .portable import load_bundle

ACTIONS = ("FREEZE_RECIPIENT", "VERIFY_OWNER", "CONTACT_SENDERS", "REVIEW_AGENT", "RELEASE_TRANSACTION", "WATCHLIST", "DISMISS")


class HTTPError(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status, self.detail = status, detail


def _plain(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return None if math.isnan(o) else float(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, (set, tuple)):
        return list(o)
    return str(o)


class Dispatcher:
    def __init__(self, portable_dir: str | Path):
        t0 = time.time()
        d = Path(portable_dir)
        self.world = LiveWorld.from_snapshot(d / "world.pkl.gz", load_bundle(d))
        self.boot_seconds = round(time.time() - t0, 1)

    # ------------------------------------------------------------------ entry point
    def handle(self, method: str, path: str, body: str | None = None) -> str:
        try:
            data = json.loads(body) if body else {}
            out = self._route(method.upper(), path, data)
            return json.dumps({"status": 200, "data": out}, default=_plain, ensure_ascii=False)
        except HTTPError as e:
            return json.dumps({"status": e.status, "detail": e.detail}, ensure_ascii=False)
        except (KeyError, LookupError) as e:
            return json.dumps({"status": 404, "detail": str(e).strip("'")}, ensure_ascii=False)
        except PermissionError as e:
            return json.dumps({"status": 403, "detail": str(e)}, ensure_ascii=False)
        except ValueError as e:
            return json.dumps({"status": 422, "detail": str(e)}, ensure_ascii=False)

    def _route(self, method: str, path: str, b: dict):
        u = urlparse(path)
        q = {k: v[-1] for k, v in parse_qs(u.query).items()}
        p = u.path.rstrip("/")
        w = self.world
        if method == "GET" and p == "/health":
            e = w.engine
            return {"status": "ok", "wallets_in_state": len(e.store.w), "model_trees": int(e.bundle["lgbm"].best_iteration_),
                    "clock": w.iso(w.clock()), "alerts": len(w.alerts), "llm": "offline",
                    "scorer": "central", "runtime": f"in-browser (Pyodide), started in {self.boot_seconds} s"}
        if method == "GET" and p == "/api/v1/customers":
            return w.customers()
        if method == "POST" and p == "/api/v1/risk-score":
            amount = b.get("amount")
            if not isinstance(amount, (int, float)) or amount <= 0 or amount > 50000:
                raise HTTPError(422, "amount must be more than 0 and at most 50000")
            if not b.get("to"):
                raise HTTPError(422, "to is required")
            if b.get("customer"):
                return w.score(b["customer"], str(b["to"]), float(amount), b.get("device_id"))
            if not b.get("sender_id"):
                raise HTTPError(422, "give customer or sender_id")
            return w.score_raw(str(b["sender_id"]), str(b["to"]), float(amount), b.get("device_id"))
        if method == "POST" and p == "/api/v1/scam-check":
            text = b.get("text") or ""
            if not 3 <= len(text) <= 2000:
                raise HTTPError(422, "text must be 3 to 2000 characters")
            return scamcheck.check(text)
        if method == "GET" and p == "/api/v1/alerts":
            return w.list_alerts(include_allowed=q.get("all") in ("1", "true", "True"))
        if method == "GET" and p == "/api/v1/agent-watch":
            return w.agent_watch()
        if method == "GET" and p == "/api/v1/model":
            return w.model_card()
        if method == "GET" and p == "/api/v1/audit":
            return {"verify": w.verify_audit(), "entries": w.audit[-200:]}
        if method == "POST" and p == "/api/v1/recipient-check":
            if not b.get("customer") or not 3 <= len(str(b.get("to") or "")) <= 20:
                raise HTTPError(422, "customer and to are required")
            return w.recipient_lookup(b["customer"], str(b["to"]))
        if method == "POST" and p == "/api/v1/complaints/preview":
            return w.preview_complaint(str(b.get("text") or "")[:2000])
        if method == "POST" and p == "/api/v1/complaints":
            if b.get("problem", "wrong_number") not in ("wrong_number", "scam", "other"):
                raise HTTPError(422, "problem must be wrong_number, scam or other")
            return w.file_complaint(b.get("customer"), b.get("text") or "", b.get("problem", "wrong_number"),
                                    b.get("transfer_id"), bool(b.get("consent")))
        m = re.fullmatch(r"/api/v1/complaints/([\w-]+)", p)
        if m and method == "GET":
            return w.complaint_status(m.group(1))
        m = re.fullmatch(r"/api/v1/customers/(\w+)/transfers", p)
        if m and method == "GET":
            return w.transfers(m.group(1))
        m = re.fullmatch(r"/api/v1/customers/(\w+)/recharges", p)
        if m and method == "GET":
            return w.recharges_of(m.group(1))
        if method == "POST" and p == "/api/v1/recharge":
            amount = b.get("amount")
            if not isinstance(amount, (int, float)) or amount <= 0 or amount > 1000:
                raise HTTPError(422, "amount must be more than 0 and at most 1000")
            if not b.get("customer") or not 11 <= len(str(b.get("number") or "")) <= 20:
                raise HTTPError(422, "customer and number are required")
            return w.recharge(b["customer"], str(b["number"]), float(amount))
        if method == "GET" and p == "/api/v1/test-kit":
            return w.test_kit()
        if method == "POST" and p == "/api/v1/demo/reset":
            w.reset()
            return {"status": "reset", "clock": w.iso(w.clock())}
        m = re.fullmatch(r"/api/v1/transfers/([\w-]+)", p)
        if m and method == "GET":
            return w.transfer_status(m.group(1))
        m = re.fullmatch(r"/api/v1/alerts/([\w-]+)(/decision|/action)?", p)
        if m:
            aid, tail = m.group(1), m.group(2)
            if method == "GET" and not tail:
                return w.alert_detail(aid, use_llm=False)          # no network calls from the browser build
            if method == "POST" and tail == "/decision":
                if b.get("choice") not in ("cancel", "confirm", "confirm_pin", "use_suggested"):
                    raise HTTPError(422, "choice must be cancel, confirm, confirm_pin or use_suggested")
                return w.decide(aid, b["choice"], b.get("pin"))
            if method == "POST" and tail == "/action":
                analyst = b.get("analyst")
                if not isinstance(analyst, str) or not 1 <= len(analyst) <= 60:
                    raise HTTPError(422, "analyst is required")
                if len(b.get("note") or "") > 500:
                    raise HTTPError(422, "note is too long")
                return w.act(aid, str(b.get("action")), analyst, b.get("note") or "")
        raise HTTPError(404, f"no route {method} {p}")
