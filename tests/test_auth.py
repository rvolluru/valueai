from types import SimpleNamespace

import pytest
from fastapi import HTTPException


def _settings() -> SimpleNamespace:
    return SimpleNamespace(
        clerk_enabled=True,
        clerk_jwks_url="https://example.test/.well-known/jwks.json",
        clerk_issuer="https://example.test",
        clerk_audience="",
        clerk_authorized_parties="http://localhost:5173,com.jouft.app.dev://oauth-native-callback",
        clerk_jwt_leeway_seconds=60,
    )


def _patch_jwt(monkeypatch, claims):
    from app import auth

    class StubJwksClient:
        def get_signing_key_from_jwt(self, token):
            return SimpleNamespace(key="public-key")

    class StubJwt:
        def decode(self, *args, **kwargs):
            return claims

    monkeypatch.setattr(auth, "_jwks_client", lambda url: StubJwksClient())
    monkeypatch.setattr(auth, "jwt", StubJwt())


def test_verify_clerk_token_allows_configured_authorized_party(monkeypatch) -> None:
    from app.auth import _verify_clerk_token

    _patch_jwt(monkeypatch, {"sub": "user_123", "azp": "com.jouft.app.dev://oauth-native-callback"})

    claims = _verify_clerk_token("token", _settings())

    assert claims["sub"] == "user_123"


def test_verify_clerk_token_allows_missing_authorized_party_for_native_tokens(monkeypatch) -> None:
    from app.auth import _verify_clerk_token

    _patch_jwt(monkeypatch, {"sub": "user_123"})

    claims = _verify_clerk_token("token", _settings())

    assert claims["sub"] == "user_123"


def test_verify_clerk_token_rejects_unconfigured_authorized_party(monkeypatch) -> None:
    from app.auth import _verify_clerk_token

    _patch_jwt(monkeypatch, {"sub": "user_123", "azp": "https://bad.example"})

    with pytest.raises(HTTPException) as exc:
        _verify_clerk_token("token", _settings())

    assert exc.value.status_code == 403
    assert exc.value.detail == "Token authorized party not allowed"
