from ferot.store import audit
from ferot.store.db import connect


def test_chain_verifies(tmp_path):
    conn = connect(tmp_path / "t.db")
    for i in range(5):
        audit.append(conn, f"C{i}", "tania", "agent", "case.approved", {"i": i}, "v1")
    assert audit.verify(conn) == {"ok": True, "broken_at": None}


def test_tamper_breaks_chain(tmp_path):
    """R12: editing any past entry is detected."""
    conn = connect(tmp_path / "t.db")
    for i in range(5):
        audit.append(conn, f"C{i}", "tania", "agent", "case.approved", {"i": i}, "v1")
    conn.execute("UPDATE audit SET actor = 'someone_else' WHERE seq = 3")
    conn.commit()
    result = audit.verify(conn)
    assert not result["ok"] and result["broken_at"] == 3


def test_every_entry_names_an_actor(tmp_path):
    conn = connect(tmp_path / "t.db")
    e = audit.append(conn, "C1", "tania", "agent", "case.approved")
    assert e["actor"] == "tania" and e["role"] == "agent" and len(e["hash"]) == 64
