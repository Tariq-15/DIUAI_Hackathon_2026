"""Server-owned identities for the integration prototype (demo stays opt-in).

PROHORI_ANALYST_TOKENS is a JSON object mapping bearer tokens to
{name, role}. Provision secrets outside the repository; production should use
the partner's identity provider with short-lived, audience-bound credentials.
"""
import hmac
import json
import os

from fastapi import HTTPException, Request


def analyst_identity(request: Request, entered_name: str) -> str:
    if os.environ.get('PROHORI_INTEGRATION', '0') != '1':
        return entered_name
    try:
        identities = json.loads(os.environ.get('PROHORI_ANALYST_TOKENS', '{}'))
        if not isinstance(identities, dict) or not identities:
            raise ValueError('no identities configured')
    except (ValueError, TypeError):
        raise HTTPException(503, 'analyst authentication unavailable') from None
    header = request.headers.get('authorization', '')
    scheme, _, token = header.partition(' ')
    if scheme.lower() != 'bearer' or not token:
        raise HTTPException(401, 'bearer credential required', headers={'WWW-Authenticate': 'Bearer'})
    identity = next((v for k, v in identities.items()
                     if hmac.compare_digest(k.encode('utf-8'), token.encode('utf-8'))), None)
    if identity is None:
        raise HTTPException(401, 'invalid credential')
    if not isinstance(identity, dict) or identity.get('role') != 'risk_analyst':
        raise HTTPException(403, 'risk_analyst role required')
    name = identity.get('name')
    if not isinstance(name, str) or not name.strip():
        raise HTTPException(503, 'invalid identity configuration')
    return name
