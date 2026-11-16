"""Entrupy v2: server-held partner credentials and listing-scoped SDK handoff."""
import hashlib
from urllib.parse import quote, urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from .auth import AuthPrincipal, require_clerk_user
from .db import Database
from .deps import get_db, get_settings
from .settings import Settings

router = APIRouter(prefix="/v1/listings/{listing_id}/authentication", tags=["Entrupy"])


class AuthorizationRequest(BaseModel):
    sdk_authorization_request: str = Field(min_length=1, max_length=32768)


def owned_listing(db, listing_id, principal):
    listing = db.get_listing_by_id(listing_id)
    if not listing or listing["owner_subject"] != principal.subject:
        raise HTTPException(404, "Listing not found")
    return listing


def customer_item_id(settings, listing_id):
    # Separate staging and production even when sharing a partner account.
    return f"{settings.entrupy_item_namespace}:{listing_id}"


def provider_request(settings, method, path, body=None):
    if not settings.entrupy_enabled or not settings.entrupy_api_token:
        raise HTTPException(503, "Item authentication is not configured")
    try:
        with httpx.Client(timeout=settings.entrupy_timeout_s, follow_redirects=False) as client:
            response = client.request(method, "https://api.entrupy.com" + path,
                headers={"Authorization": f"Token {settings.entrupy_api_token}",
                         "Accept": "application/json"}, json=body)
        if response.status_code == 404 and method == "GET":
            return None
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError("Invalid response")
        return data
    except (httpx.HTTPError, ValueError):
        # Provider response bodies can contain account data. Never return them.
        raise HTTPException(502, "Entrupy is temporarily unavailable") from None


@router.post("/authorize")
def authorize(listing_id: str, body: AuthorizationRequest, response: Response,
              principal: AuthPrincipal = Depends(require_clerk_user),
              db: Database = Depends(get_db), settings: Settings = Depends(get_settings)):
    listing = owned_listing(db, listing_id, principal)
    response.headers["Cache-Control"] = "no-store"
    data = provider_request(settings, "POST", "/v2/integrations/authorize-user", {
        "unique_user_id": hashlib.sha256(
            f"{settings.entrupy_item_namespace}:{principal.subject}".encode()).hexdigest(),
        "sdk_authorization_request": body.sdk_authorization_request,
    })
    signed = data.get("signed_authorization_request")
    if not isinstance(signed, str) or not signed:
        raise HTTPException(502, "Invalid Entrupy authorization response")
    return {"signed_authorization_request": signed, "metadata": {
        "customer_item_id": customer_item_id(settings, listing_id),
        "brand": listing["brand"], "item_type": listing["category"],
    }}


def authentication_summary(data, expected_id):
    item = data.get("item")
    if not isinstance(item, dict) or (item.get("text_fields") or {}).get("customer_item_id") != expected_id:
        raise HTTPException(502, "Entrupy item correlation failed")
    status = item.get("status") or {}
    if not isinstance(status, dict) or not isinstance(status.get("result") or {}, dict):
        raise HTTPException(502, "Invalid Entrupy status response")
    result = status.get("result") or {}
    retake = (status.get("retake") or {}).get("retake_required") is True
    authenticated = (result.get("id") == "authentic" and result.get("final") is True
                     and not retake and not status.get("flag"))
    certificate = (item.get("certificate") or {}).get("site")
    parsed = urlparse(certificate) if isinstance(certificate, str) else None
    if not (authenticated and parsed and parsed.scheme == "https" and
            parsed.hostname == "cert.entrupy.com" and not parsed.username and not parsed.password):
        certificate = None
    return {"provider": "entrupy", "entrupy_id": item.get("entrupy_id"),
            "result": result.get("id"), "final": result.get("final") is True,
            "display": result.get("display"), "retake_required": retake,
            "authenticated": authenticated, "certificate_url": certificate}


@router.get("")
def read_authentication(listing_id: str, response: Response,
                        principal: AuthPrincipal = Depends(require_clerk_user),
                        db: Database = Depends(get_db), settings: Settings = Depends(get_settings)):
    owned_listing(db, listing_id, principal)
    response.headers["Cache-Control"] = "no-store"
    identifier = customer_item_id(settings, listing_id)
    data = provider_request(settings, "GET", "/v2/lookup/authentications/" + quote(identifier, safe=""))
    if data is None:
        return {"provider": "entrupy", "result": "not_submitted", "authenticated": False,
                "certificate_url": None, "final": False}
    return authentication_summary(data, identifier)
