"""Case store (SQLite for the prototype).

Production note (rules R5, R11): upay would run this on its own encrypted database inside Bangladesh,
with records kept at least 6 years. There is deliberately no delete endpoint.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS cases (
    case_id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    complaint_minute INTEGER NOT NULL,
    claimant TEXT NOT NULL,
    recipient TEXT,
    channel TEXT NOT NULL,
    status TEXT NOT NULL,
    case_type TEXT,
    priority REAL,
    sla_deadline TEXT,
    payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    case_id TEXT,
    actor TEXT NOT NULL,
    role TEXT NOT NULL,
    action TEXT NOT NULL,
    detail TEXT,
    model_version TEXT,
    prev_hash TEXT NOT NULL,
    hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS guard_checks (
    check_id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    sender TEXT NOT NULL,
    recipient TEXT NOT NULL,
    amount REAL NOT NULL,
    risk INTEGER NOT NULL,
    band TEXT NOT NULL,
    decision TEXT,
    payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS aml_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id TEXT NOT NULL,
    wallet TEXT NOT NULL,
    role TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""

_lock = threading.Lock()


def connect(path: Path | str) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.executescript(SCHEMA)
    return conn


class CaseStore:
    def __init__(self, path: Path | str):
        self.conn = connect(path)

    def save(self, case: dict) -> None:
        with _lock:
            self.conn.execute(
                "INSERT OR REPLACE INTO cases (case_id, created_at, complaint_minute, claimant, recipient, channel, "
                "status, case_type, priority, sla_deadline, payload) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (case["case_id"], case["created_at"], case["complaint_minute"], case["claimant"],
                 case["facts"].get("recipient") if case.get("facts") else None, case["channel"], case["status"],
                 (case.get("prediction") or {}).get("case_type"), (case.get("priority") or {}).get("score"),
                 case.get("sla", {}).get("deadline"), json.dumps(case, ensure_ascii=False, default=str)))
            self.conn.commit()

    def get(self, case_id: str) -> dict | None:
        row = self.conn.execute("SELECT payload FROM cases WHERE case_id = ?", (case_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def all(self) -> list[dict]:
        return [json.loads(r[0]) for r in self.conn.execute("SELECT payload FROM cases ORDER BY priority DESC")]

    def count(self) -> int:
        return int(self.conn.execute("SELECT COUNT(*) FROM cases").fetchone()[0])

    def next_id(self) -> str:
        n = self.count() + 1
        while self.get(f"DC-{n:05d}"):
            n += 1
        return f"DC-{n:05d}"

    def history_rows(self) -> list[tuple[str, str, int]]:
        return [tuple(r) for r in self.conn.execute(
            "SELECT claimant, recipient, complaint_minute FROM cases WHERE recipient IS NOT NULL")]

    def flag_aml(self, case_id: str, wallet: str, role: str, created_at: str) -> None:
        with _lock:
            self.conn.execute("INSERT INTO aml_queue (case_id, wallet, role, created_at) VALUES (?, ?, ?, ?)",
                              (case_id, wallet, role, created_at))
            self.conn.commit()

    def aml_queue(self) -> list[dict]:
        rows = self.conn.execute("SELECT id, case_id, wallet, role, created_at FROM aml_queue ORDER BY id").fetchall()
        return [dict(zip(["id", "case_id", "wallet", "role", "created_at"], r)) for r in rows]

    def save_check(self, check: dict) -> None:
        with _lock:
            self.conn.execute(
                "INSERT OR REPLACE INTO guard_checks (check_id, created_at, sender, recipient, amount, risk, band, "
                "decision, payload) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (check["check_id"], check["created_at"], check["sender"], check["recipient"], check["amount"],
                 check["risk"], check["band"], check.get("decision"),
                 json.dumps(check, ensure_ascii=False, default=str)))
            self.conn.commit()

    def get_check(self, check_id: str) -> dict | None:
        row = self.conn.execute("SELECT payload FROM guard_checks WHERE check_id = ?", (check_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def checks(self, bands: tuple[str, ...] = ("warn", "review")) -> list[dict]:
        marks = ",".join("?" * len(bands))
        q = f"SELECT payload FROM guard_checks WHERE band IN ({marks}) ORDER BY check_id DESC LIMIT 100"
        return [json.loads(r[0]) for r in self.conn.execute(q, bands)]

    def count_checks(self) -> int:
        return int(self.conn.execute("SELECT COUNT(*) FROM guard_checks").fetchone()[0])

    def reset(self) -> None:
        with _lock:
            self.conn.executescript(
                "DELETE FROM cases; DELETE FROM audit; DELETE FROM aml_queue; DELETE FROM guard_checks;")
            self.conn.commit()
