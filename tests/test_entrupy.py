from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import entrupy
from app.auth import AuthPrincipal, require_clerk_user
from app.deps import get_db, get_settings


def client(monkeypatch, owner='seller'):
    app = FastAPI()
    app.include_router(entrupy.router)
    app.dependency_overrides[require_clerk_user] = lambda: AuthPrincipal('clerk', 'seller', {})
    app.dependency_overrides[get_db] = lambda: SimpleNamespace(get_listing_by_id=lambda _: {
        'owner_subject': owner, 'brand': 'Chanel', 'category': 'Bags'})
    app.dependency_overrides[get_settings] = lambda: SimpleNamespace(entrupy_item_namespace='test')
    return TestClient(app)


def payload(result='authentic', final=True, retake=False, flag=None):
    return {'item': {'entrupy_id': 'ent1', 'text_fields': {'customer_item_id': 'test:l1'},
        'status': {'result': {'id': result, 'final': final},
                   'retake': {'retake_required': retake}, 'flag': flag},
        'certificate': {'site': 'https://cert.entrupy.com/ent1'}}}


def test_owner_is_checked_before_provider(monkeypatch):
    monkeypatch.setattr(entrupy, 'provider_request', lambda *a: pytest.fail('provider called'))
    c = client(monkeypatch, owner='other')
    assert c.get('/v1/listings/l1/authentication').status_code == 404
    assert c.post('/v1/listings/l1/authentication/authorize', json={'sdk_authorization_request':'x'}).status_code == 404


def test_authorization_uses_server_identity_and_metadata(monkeypatch):
    calls = []
    def request(*args):
        calls.append(args)
        return {'signed_authorization_request': 'signed'}
    monkeypatch.setattr(entrupy, 'provider_request', request)
    response = client(monkeypatch).post('/v1/listings/l1/authentication/authorize', json={
        'sdk_authorization_request': 'raw', 'unique_user_id': 'victim', 'customer_item_id': 'other'})
    assert response.status_code == 200
    assert response.headers['cache-control'] == 'no-store'
    assert response.json()['metadata']['customer_item_id'] == 'test:l1'
    assert calls[0][3]['unique_user_id'] != 'victim'
    assert calls[0][3]['sdk_authorization_request'] == 'raw'


@pytest.mark.parametrize('result,final,retake,flag,expected', [
    ('authentic',True,False,None,True), ('authentic',False,False,None,False),
    ('unidentified',True,False,None,False), ('authentic',True,True,None,False),
    ('authentic',True,False,{'id':'review'},False)])
def test_only_final_unflagged_authentic_has_certificate(result, final, retake, flag, expected):
    data = entrupy.authentication_summary(payload(result,final,retake,flag), 'test:l1')
    assert data['authenticated'] is expected
    assert bool(data['certificate_url']) is expected


def test_item_mismatch_rejected():
    with pytest.raises(entrupy.HTTPException):
        entrupy.authentication_summary(payload(), 'different')


def test_result_lookup_and_not_submitted(monkeypatch):
    monkeypatch.setattr(entrupy, 'provider_request', lambda *args: payload())
    c = client(monkeypatch)
    assert c.get('/v1/listings/l1/authentication').json()['authenticated'] is True
    monkeypatch.setattr(entrupy, 'provider_request', lambda *args: None)
    assert c.get('/v1/listings/l1/authentication').json()['result'] == 'not_submitted'


def test_disabled_does_not_call_network():
    with pytest.raises(entrupy.HTTPException) as exc:
        entrupy.provider_request(SimpleNamespace(entrupy_enabled=False), 'GET', '/test')
    assert exc.value.status_code == 503


def test_transport_headers_and_safe_errors(monkeypatch):
    def handler(request):
        assert request.headers['authorization'] == 'Token secret'
        return httpx.Response(500, text='secret provider data')
    real_client = httpx.Client
    monkeypatch.setattr(entrupy.httpx, 'Client', lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs))
    settings = SimpleNamespace(entrupy_enabled=True, entrupy_api_token='secret', entrupy_timeout_s=1)
    with pytest.raises(entrupy.HTTPException) as exc:
        entrupy.provider_request(settings, 'GET', '/test')
    assert 'secret' not in exc.value.detail
