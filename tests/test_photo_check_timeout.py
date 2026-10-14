import asyncio
from io import BytesIO
from types import SimpleNamespace
import httpx
import pytest
from fastapi import HTTPException, UploadFile
from starlette.datastructures import Headers
from app import main
from app.auth import AuthPrincipal


def test_photo_coverage_timeout_is_thirty_seconds_and_logged(monkeypatch):
    logs = []
    class Client:
        def __init__(self, *, timeout):
            assert timeout == 30
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def post(self, *args, **kwargs): raise httpx.ReadTimeout('slow provider')
    monkeypatch.setattr(main.httpx, 'AsyncClient', Client)
    monkeypatch.setattr(main, 'log_json', lambda event, **kwargs: logs.append((event, kwargs)))
    settings = SimpleNamespace(max_images_per_request=6, gemini_api_key='test', gpt_item_profile_gemini_model='test')
    image = UploadFile(file=BytesIO(b'photo'), filename='photo.jpg', headers=Headers({'content-type': 'image/jpeg'}))
    with pytest.raises(HTTPException) as error:
        asyncio.run(main.classify_image_roles([image], 'clothes', settings, AuthPrincipal(auth_type='api_key', subject='owner', claims={})))
    assert error.value.status_code == 504
    assert 'full item and pricing analysis will still run' in error.value.detail
    assert logs[0][0] == 'image_role_classification_timeout'
    assert logs[0][1]['scope'] == 'initial_photo_coverage_only'
    assert logs[0][1]['timeout_seconds'] == 30
