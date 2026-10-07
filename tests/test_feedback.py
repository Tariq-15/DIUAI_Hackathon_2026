import json

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from src.models.metrics import wilson_interval
from src.serve.auth import analyst_identity
from tools.feedback_evaluate import recipient_matrix, aggregate_seed_metrics


def test_intervals_include_boundary_and_empty_samples():
    assert wilson_interval(0, 0) == [None, None]
    assert wilson_interval(0, 100)[0] == 0
    assert wilson_interval(100, 100)[1] == 1
    low, high = wilson_interval(50, 100)
    assert low < .5 < high
    with pytest.raises(ValueError):
        wilson_interval(2, 1)


def test_matrix_contains_unfamiliar_and_negative_cases():
    report = recipient_matrix()
    assert {r['model'] for r in report['rows']} == {'keypad', 'ordinary_edit'}
    unfamiliar = [r for r in report['rows'] if not r['familiar'] and r['intended']]
    assert unfamiliar and not any(r['correct'] for r in unfamiliar)
    assert any(r['false_suggestions'] for r in report['summary'])
    assert aggregate_seed_metrics([]) == {}


def test_verified_actor_and_role(monkeypatch):
    monkeypatch.setenv('PROHORI_INTEGRATION', '1')
    monkeypatch.setenv('PROHORI_ANALYST_TOKENS', json.dumps({
        'secret': {'name': 'verified', 'role': 'risk_analyst'},
        'reader': {'name': 'reader', 'role': 'viewer'}}))
    def request(token):
        return Request({'type': 'http', 'headers': [(b'authorization', f'Bearer {token}'.encode())]})
    assert analyst_identity(request('secret'), 'forged') == 'verified'
    for token, expected in [('reader', 403), ('invalid', 401)]:
        with pytest.raises(HTTPException) as error:
            analyst_identity(request(token), 'forged')
        assert error.value.status_code == expected
    monkeypatch.delenv('PROHORI_ANALYST_TOKENS')
    with pytest.raises(HTTPException) as error:
        analyst_identity(request('secret'), 'forged')
    assert error.value.status_code == 503
