"""Who is calling, and may they do this? (rule R11, least privilege)

Prototype: the console sends X-Ferot-Actor and X-Ferot-Role headers chosen on its sign-in screen.
Production: these come from upay's single sign-on, never from the client.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Header, HTTPException

ROLES = {"agent", "supervisor", "analyst", "compliance"}


@dataclass
class Caller:
    actor: str
    role: str


def staff(x_ferot_actor: str = Header(default="demo-agent"), x_ferot_role: str = Header(default="agent")) -> Caller:
    if x_ferot_role not in ROLES:
        raise HTTPException(status_code=403, detail=f"unknown role {x_ferot_role!r}")
    return Caller(actor=x_ferot_actor.strip() or "unknown", role=x_ferot_role)


def require(caller: Caller, *roles: str) -> None:
    if caller.role not in roles:
        raise HTTPException(status_code=403, detail=f"role {caller.role!r} may not do this; needs {' or '.join(roles)}")
