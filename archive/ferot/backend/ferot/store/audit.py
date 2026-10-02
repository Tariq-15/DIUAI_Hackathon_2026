"""Tamper-evident audit log (rule R12; MFS Regulations 2022 §12.2 non-repudiation, §17.3 dispute log).

Each entry stores the hash of the previous entry, so editing or deleting any row breaks the chain
from that point on. Every entry names the person (actor) and role behind the action.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone

GENESIS = "0" * 64


def _digest(prev_hash: str, record: dict) -> str:
    payload = json.dumps(record, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256((prev_hash + payload).encode("utf-8")).hexdigest()


def append(conn: sqlite3.Connection, case_id: str | None, actor: str, role: str, action: str,
           detail: dict | None = None, model_version: str | None = None) -> dict:
    last = conn.execute("SELECT hash FROM audit ORDER BY seq DESC LIMIT 1").fetchone()
    prev = last[0] if last else GENESIS
    record = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), "case_id": case_id, "actor": actor,
              "role": role, "action": action, "detail": detail or {}, "model_version": model_version}
    h = _digest(prev, record)
    cur = conn.execute(
        "INSERT INTO audit (ts, case_id, actor, role, action, detail, model_version, prev_hash, hash) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (record["ts"], case_id, actor, role, action, json.dumps(record["detail"], ensure_ascii=False, default=str),
         model_version, prev, h))
    conn.commit()
    return {"seq": cur.lastrowid, **record, "hash": h}


def entries(conn: sqlite3.Connection, case_id: str | None = None) -> list[dict]:
    q = "SELECT seq, ts, case_id, actor, role, action, detail, model_version, prev_hash, hash FROM audit"
    rows = conn.execute(q + (" WHERE case_id = ? ORDER BY seq" if case_id else " ORDER BY seq"),
                        (case_id,) if case_id else ()).fetchall()
    keys = ["seq", "ts", "case_id", "actor", "role", "action", "detail", "model_version", "prev_hash", "hash"]
    out = []
    for r in rows:
        d = dict(zip(keys, r))
        d["detail"] = json.loads(d["detail"]) if d["detail"] else {}
        out.append(d)
    return out


def verify(conn: sqlite3.Connection) -> dict:
    prev = GENESIS
    for e in entries(conn):
        record = {k: e[k] for k in ("ts", "case_id", "actor", "role", "action", "detail", "model_version")}
        if e["prev_hash"] != prev or _digest(prev, record) != e["hash"]:
            return {"ok": False, "broken_at": e["seq"]}
        prev = e["hash"]
    return {"ok": True, "broken_at": None}
