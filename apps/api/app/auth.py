from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Annotated

from fastapi import Depends, Header, HTTPException

from .settings import Settings, get_settings

try:
    import jwt
    from jwt.exceptions import ExpiredSignatureError
    from jwt import PyJWKClient
except Exception:  # pragma: no cover - optional dependency at runtime
    jwt = None
    ExpiredSignatureError = Exception
    PyJWKClient = None


@dataclass
class AuthPrincipal:
    auth_type: str
    subject: str
    claims: dict[str, Any]


def _unauthorized(detail: str = "Unauthorized") -> HTTPException:
    return HTTPException(status_code=401, detail=detail)


def _forbidden(detail: str = "Forbidden") -> HTTPException:
    return HTTPException(status_code=403, detail=detail)


def _value_has_admin_role(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip().casefold() == "admin"
    if isinstance(value, (list, tuple, set)):
        return any(_value_has_admin_role(item) for item in value)
    return False


def principal_has_admin_role(principal: AuthPrincipal) -> bool:
    claims = principal.claims if isinstance(principal.claims, dict) else {}
    candidates: list[Any] = [
        claims.get("role"),
        claims.get("roles"),
        claims.get("org_role"),
        claims.get("organization_role"),
        claims.get("permissions"),
    ]
    for key in ("public_metadata", "private_metadata", "metadata", "unsafe_metadata"):
        metadata = claims.get(key)
        if isinstance(metadata, dict):
            candidates.extend([
                metadata.get("role"),
                metadata.get("roles"),
                metadata.get("permissions"),
            ])
    return any(_value_has_admin_role(candidate) for candidate in candidates)


def _parse_bearer(authorization: str | None) -> str | None:
    if not authorization:
        return None
    parts = authorization.strip().split(" ", 1)
    if len(parts) != 2 or parts[0].casefold() != "bearer":
        return None
    token = parts[1].strip()
    return token or None


@lru_cache(maxsize=8)
def _jwks_client(jwks_url: str):
    if PyJWKClient is None:
        raise RuntimeError("PyJWT with crypto support is required for Clerk JWT verification")
    return PyJWKClient(jwks_url)


def _verify_clerk_token(token: str, settings: Settings) -> dict[str, Any]:
    if not settings.clerk_enabled:
        raise _unauthorized("Clerk authentication is not enabled")
    if jwt is None:
        raise HTTPException(status_code=500, detail="Server missing JWT verification dependency")
    if not settings.clerk_jwks_url or not settings.clerk_issuer:
        raise HTTPException(status_code=500, detail="Clerk auth misconfigured on server")

    try:
        signing_key = _jwks_client(settings.clerk_jwks_url).get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=settings.clerk_issuer,
            audience=settings.clerk_audience or None,
            options={"verify_aud": bool(settings.clerk_audience)},
            leeway=max(0, int(settings.clerk_jwt_leeway_seconds)),
        )
    except ExpiredSignatureError as exc:
        raise _unauthorized("Invalid Clerk token: session expired, please sign in again") from exc
    except Exception as exc:
        raise _unauthorized(f"Invalid Clerk token: {exc}") from exc

    # Optional azp (authorized party) allow-list check
    if settings.clerk_authorized_parties:
        allowed = {p.strip() for p in settings.clerk_authorized_parties.split(",") if p.strip()}
        azp = claims.get("azp")
        if allowed and azp and azp not in allowed:
            raise _forbidden("Token authorized party not allowed")

    return claims


def get_request_principal(
    x_api_key: Annotated[str | None, Header()] = None,
    authorization: Annotated[str | None, Header()] = None,
    settings: Settings = Depends(get_settings),
) -> AuthPrincipal:
    if x_api_key and x_api_key == settings.api_key:
        return AuthPrincipal(auth_type="api_key", subject="api-key", claims={"sub": "api-key"})

    token = _parse_bearer(authorization)
    if token:
        claims = _verify_clerk_token(token, settings)
        sub = str(claims.get("sub") or "")
        if not sub:
            raise _unauthorized("Token missing subject")
        return AuthPrincipal(auth_type="clerk", subject=sub, claims=claims)

    raise _unauthorized("Missing API key or Bearer token")


def require_clerk_user(
    authorization: Annotated[str | None, Header()] = None,
    settings: Settings = Depends(get_settings),
) -> AuthPrincipal:
    token = _parse_bearer(authorization)
    if not token:
        raise _unauthorized("Missing Bearer token")
    claims = _verify_clerk_token(token, settings)
    sub = str(claims.get("sub") or "")
    if not sub:
        raise _unauthorized("Token missing subject")
    return AuthPrincipal(auth_type="clerk", subject=sub, claims=claims)


def require_admin_user(
    principal: AuthPrincipal = Depends(require_clerk_user),
) -> AuthPrincipal:
    if not principal_has_admin_role(principal):
        raise _forbidden("Admin role required")
    return principal


def require_admin_or_api_key(
    principal: AuthPrincipal = Depends(get_request_principal),
) -> AuthPrincipal:
    if principal.auth_type != "api_key" and not principal_has_admin_role(principal):
        raise _forbidden("Admin role required")
    return principal
